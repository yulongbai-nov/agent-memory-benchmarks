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

"""Send memory operations to an isolated OpenSquilla Python process."""

import json
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import ClassVar

from amb.base import Memory
from amb.contracts.conversation import Session
from amb.contracts.memory import MemoryHit


class OpenSquillaMemory(Memory):
    """Use OpenSquilla without loading its agent or gateway."""

    name: ClassVar[str] = "opensquilla"
    description: ClassVar[str] = "OpenSquilla native session memory"
    embedding_providers: ClassVar[tuple[str, ...]] = ("openai",)
    optional_models: ClassVar[tuple[str, ...]] = ("embedding", "llm")
    usage_coverage: ClassVar[str] = "partial"

    def __init__(
        self,
        model: str | None = None,
        embedding_model: str | None = "openai:text-embedding-3-small",
        **params: object,
    ) -> None:
        """Set the embedding model and prepare a sample-local worker.

        Raises:
            ValueError: If an extraction model is requested.
        """
        super().__init__(**params)
        if model is not None:
            raise ValueError(
                "OpenSquilla session indexing does not use an extraction model"
            )
        self.model = None
        self.embedding_model = embedding_model
        self._embed_name = self.model_name(embedding_model, "embedding")
        self._python = os.environ.get("OPENSQUILLA_PYTHON", sys.executable)
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._temp: tempfile.TemporaryDirectory[str] | None = None
        self._usage: dict[str, int] = {}
        self._stats: dict = {}

    def version(self) -> str:
        """Read the installed version from the separate Python environment."""
        return subprocess.check_output(
            [
                self._python,
                "-c",
                "from importlib.metadata import version; print(version('opensquilla'))",
            ],
            text=True,
            timeout=15,
        ).strip()

    def coverage(self) -> str:
        """Report estimated embedding usage or full coverage for keyword-only mode."""
        return "full" if self._embed_name is None else self.usage_coverage

    def setup(self) -> None:
        """Start one worker with a fresh SQLite index."""
        self._temp = tempfile.TemporaryDirectory(prefix="amb-opensquilla-")
        worker = Path(__file__).with_name("worker.py")
        if not worker.exists():
            worker = Path(__file__).parents[1] / "worker" / "serve.py"
        self._process = subprocess.Popen(
            [self._python, "-u", str(worker)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        self._request(
            "initialize",
            db_path=str(Path(self._temp.name) / "memory.sqlite"),
            embedding_model=self._embed_name,
        )

    def _request(self, op: str, **payload: object) -> dict:
        with self._lock:
            process = self._process
            assert process is not None
            assert process.stdin is not None
            assert process.stdout is not None
            process.stdin.write(json.dumps({"op": op, **payload}) + "\n")
            process.stdin.flush()
            line = process.stdout.readline()
            if not line:
                raise RuntimeError("OpenSquilla memory worker exited")
            result = json.loads(line)
            if "error" in result:
                raise RuntimeError(f"OpenSquilla memory worker: {result['error']}")
            self._stats = result.get("stats", self._stats)
            for key, value in result.get("usage", {}).items():
                self._usage[key] = self._usage.get(key, 0) + value
            return result

    def ingest_session(self, conversation_id: str, session: Session) -> None:
        """Store the dated, speaker-labelled transcript with native session formatting."""
        if session.turns:
            date = session.time()
            self._request(
                "index",
                session_id=session.session_id,
                timestamp=date.timestamp() if date else None,
                turns=[
                    {"id": turn.turn_id, "text": session.dated(turn)}
                    for turn in session.turns
                ],
            )

    def search(self, conversation_id: str, query: str, k: int = 10) -> list[MemoryHit]:
        """Return native ranked session chunks and their mapped source IDs."""
        if k < 1:
            return []
        return [
            MemoryHit.model_validate(hit)
            for hit in self._request("search", query=query, k=k)["hits"]
        ]

    def stats(self) -> dict:
        """Report the latest native memory index observations."""
        return dict(self._stats)

    def usage_counters(self) -> dict:
        """Expose the native store's estimated embedding usage."""
        return dict(self._usage)

    def teardown(self) -> None:
        """Close the worker and delete its sample database."""
        try:
            if self._process is not None:
                process = self._process
                try:
                    if process.stdin is not None:
                        process.stdin.close()
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                finally:
                    if process.stdout is not None:
                        process.stdout.close()
                    self._process = None
        finally:
            if self._temp is not None:
                self._temp.cleanup()
                self._temp = None
