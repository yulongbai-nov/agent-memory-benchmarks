# MIT License
#
# Copyright (c) 2026 René-Jean Corneille
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Adapter for an isolated OpenViking HTTP server in trusted mode."""

import os
import time
import uuid
from typing import ClassVar

import httpx
from loguru import logger

from amb.base import Memory
from amb.contracts.conversation import Session
from amb.contracts.memory import MemoryHit


class OpenVikingMemory(Memory):
    """Commit each conversation session and search its extracted memories."""

    name: ClassVar[str] = "openviking"
    description: ClassVar[str] = "OpenViking session memory"
    usage_coverage: ClassVar[str] = "none"
    llm_providers: ClassVar[tuple[str, ...]] = ("openai",)
    embedding_providers: ClassVar[tuple[str, ...]] = ("openai",)

    def __init__(
        self,
        model: str = "openai:gpt-6-luna",
        embedding_model: str = "openai:text-embedding-3-small",
        **params: object,
    ) -> None:
        """Set the expected server models and an isolated benchmark identity.

        Raises:
            ValueError: If models differ from the smoke server configuration.
        """
        super().__init__(**params)
        self.model_name(model, "llm")
        self.model_name(embedding_model, "embedding")
        if (
            model != "openai:gpt-6-luna"
            or embedding_model != "openai:text-embedding-3-small"
        ):
            raise ValueError(
                "The OpenViking smoke server is configured for GPT-6 Luna and text-embedding-3-small"
            )
        self.model = model
        self.embedding_model = embedding_model
        self.user_id = "amb-" + uuid.uuid4().hex
        self.session_id = "amb-" + uuid.uuid4().hex
        self.client: httpx.Client | None = None

    def version(self) -> str | None:
        """Read the version of the server actually being benchmarked."""
        url = os.environ.get("OPENVIKING_BASE_URL", "http://localhost:1933")
        response = httpx.get(
            f"{url}/health",
            headers={
                "X-API-Key": os.environ.get(
                    "OPENVIKING_BENCHMARK_KEY", "amb-local-only"
                )
            },
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json().get("version")

    def setup(self) -> None:
        """Create a session in a unique OpenViking user namespace."""
        self.client = httpx.Client(
            base_url=os.environ.get("OPENVIKING_BASE_URL", "http://localhost:1933"),
            headers={
                "X-API-Key": os.environ.get(
                    "OPENVIKING_BENCHMARK_KEY", "amb-local-only"
                ),
                "X-OpenViking-Account": "amb",
                "X-OpenViking-User": self.user_id,
            },
            timeout=300.0,
        )
        self._request("POST", "/api/v1/sessions", json={"session_id": self.session_id})

    def _request(self, method: str, path: str, **kwargs: object) -> object:
        assert self.client is not None
        response = self.client.request(method, path, **kwargs)
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") == "error":
            raise RuntimeError(f"OpenViking request failed: {payload.get('error')}")
        return payload.get("result")

    def ingest_session(self, conversation_id: str, session: Session) -> None:
        """Archive the source session and wait for memory extraction.

        Raises:
            RuntimeError: If extraction or background indexing fails.
            TimeoutError: If extraction does not complete in time.
        """
        for turn in session.turns:
            self._request(
                "POST",
                f"/api/v1/sessions/{self.session_id}/messages",
                json={"role": "user", "content": session.dated(turn)},
            )
        if not session.turns:
            return
        result = self._request(
            "POST", f"/api/v1/sessions/{self.session_id}/commit", json={}
        )
        assert isinstance(result, dict)
        task_id = result.get("task_id")
        if not task_id:
            raise RuntimeError("OpenViking did not return an extraction task")
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            task = self._request("GET", f"/api/v1/tasks/{task_id}")
            assert isinstance(task, dict)
            if task.get("status") == "completed":
                logger.info(
                    "OpenViking extraction counts: {}",
                    (task.get("result") or {}).get("memories_extracted"),
                )
                queues = self._request("POST", "/api/v1/system/wait", json={})
                assert isinstance(queues, dict)
                if any(
                    queue.get("error_count") or queue.get("errors")
                    for queue in queues.values()
                ):
                    raise RuntimeError("OpenViking background indexing reported errors")
                return
            if task.get("status") in {"failed", "cancelled"}:
                raise RuntimeError(
                    f"OpenViking extraction {task['status']}: {task.get('error')}"
                )
            time.sleep(1)
        raise TimeoutError("OpenViking memory extraction timed out")

    def search(self, conversation_id: str, query: str, k: int = 10) -> list[MemoryHit]:
        """Retrieve memory contents without inventing source-session attribution."""
        result = self._request(
            "POST",
            "/api/v1/search/find",
            json={"query": query, "target_uri": "viking://~/memories", "limit": k},
        )
        assert isinstance(result, dict)
        logger.info(
            "OpenViking memory search returned {} hits", len(result.get("memories", []))
        )
        hits = []
        for item in result.get("memories", []):
            uri = item["uri"]
            content = self._request("GET", "/api/v1/content/read", params={"uri": uri})
            hits.append(
                MemoryHit(
                    content=str(content), score=item.get("score"), metadata={"uri": uri}
                )
            )
        return hits

    def teardown(self) -> None:
        """Close the HTTP client; the isolated server volume owns all data."""
        if self.client is not None:
            self.client.close()
            self.client = None
