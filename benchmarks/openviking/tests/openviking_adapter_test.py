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

import json

import httpx
import pytest
from src.memory import OpenVikingMemory

from amb.contracts.conversation import Session, Turn


def test_commit_then_recall_with_isolated_user(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each sample commits, waits and recalls in its own user namespace."""
    calls = []
    messages = []
    index_writes = []
    searches = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(
            (request.method, request.url.path, request.headers["X-OpenViking-User"])
        )
        path = request.url.path
        if path.endswith("/messages"):
            messages.append(json.loads(request.content))
        if path == "/api/v1/content/batch-write":
            index_writes.append(json.loads(request.content))
        if path.endswith("/commit"):
            result = {"task_id": "task1"}
        elif path == "/api/v1/tasks/task1":
            result = {"status": "completed"}
        elif path == "/api/v1/search/find":
            searches.append(json.loads(request.content))
            result = {
                "memories": [
                    {
                        "uri": "viking://user/x/memories/pet.md",
                        "score": 0.8,
                        "content": "Maya has a tortoise called Saffron.",
                    },
                    {"uri": "viking://user/x/memories/unreadable.md", "score": 0.95},
                ],
                "resources": [
                    {
                        "uri": index_writes[0]["operations"][0]["uri"],
                        "score": 0.9,
                        "content": index_writes[0]["operations"][0]["content"],
                    },
                    {
                        "uri": "viking://user/other/resources/pet.txt",
                        "score": 1.0,
                        "content": "Unrelated context.",
                    },
                ],
            }
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
    memory = OpenVikingMemory(index_transcripts=True)
    second = OpenVikingMemory()
    memory.setup()
    memory.ingest_session(
        "c",
        Session(
            session_id="s",
            timestamp="2026-11-12",
            turns=[
                Turn(turn_id="t", speaker="Maya", text="My tortoise is Saffron."),
                Turn(turn_id="u", speaker="Alex", text="That is a lovely name."),
            ],
        ),
    )
    hits = memory.search("c", "What is my tortoise called?", k=2)
    limited = memory.search("c", "What is my tortoise called?", k=1)
    memory.teardown()

    assert memory.user_id != second.user_id
    assert all(user == memory.user_id for _, _, user in calls)
    assert any(path.endswith("/commit") for _, path, _ in calls)
    assert any(path == "/api/v1/system/wait" for _, path, _ in calls)
    assert len(messages) == 1
    assert "Maya: My tortoise is Saffron." in messages[0]["content"]
    assert "Alex: That is a lovely name." in messages[0]["content"]
    assert index_writes[0]["wait"] is True
    assert index_writes[0]["processing_mode"] == "vectors_only"
    assert len(index_writes[0]["operations"]) == 2
    assert searches[0]["target_uri"] == ["viking://~/memories", memory.transcript_root]
    assert searches[0]["read_content"] is True
    assert searches[0]["level"] == 2
    assert [hit.content for hit in hits] == [
        "[12 November 2026] Maya: My tortoise is Saffron.",
        "Maya has a tortoise called Saffron.",
    ]
    assert hits[0].session_ids == ["s"]
    assert hits[0].turn_ids == ["t"]
    assert hits[1].session_ids == []
    assert limited == hits[:1]
