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

"""Check the OpenViking adapter against the service's HTTP contract."""

import httpx
import pytest
from src.memory import OpenVikingMemory

from amb.contracts.conversation import Session, Turn


def test_commit_then_recall_with_isolated_user(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each sample commits, waits and recalls in its own user namespace."""
    calls = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(
            (request.method, request.url.path, request.headers["X-OpenViking-User"])
        )
        path = request.url.path
        if path.endswith("/commit"):
            result = {"task_id": "task1"}
        elif path == "/api/v1/tasks/task1":
            result = {"status": "completed"}
        elif path == "/api/v1/search/find":
            result = {
                "memories": [{"uri": "viking://user/x/memories/pet.md", "score": 0.8}]
            }
        elif path == "/api/v1/content/read":
            result = "Maya has a tortoise called Saffron."
        else:
            result = {}
        return httpx.Response(200, json={"status": "ok", "result": result})

    original_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: original_client(
            transport=httpx.MockTransport(handle), **kwargs
        ),
    )
    memory = OpenVikingMemory()
    second = OpenVikingMemory()
    memory.setup()
    memory.ingest_session(
        "c",
        Session(
            session_id="s",
            turns=[Turn(turn_id="t", speaker="Maya", text="My tortoise is Saffron.")],
        ),
    )
    hits = memory.search("c", "What is my tortoise called?")
    memory.teardown()

    assert memory.user_id != second.user_id
    assert all(user == memory.user_id for _, _, user in calls)
    assert any(path.endswith("/commit") for _, path, _ in calls)
    assert any(path == "/api/v1/system/wait" for _, path, _ in calls)
    assert hits[0].content == "Maya has a tortoise called Saffron."
    assert hits[0].session_ids == []
