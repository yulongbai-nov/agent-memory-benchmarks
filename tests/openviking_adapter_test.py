"""Check the OpenViking adapter against the service's HTTP contract."""

import httpx
from amb.contracts.conversation import Session, Turn
from src.memory import OpenVikingMemory


def test_commit_then_recall_with_isolated_user(monkeypatch):
    calls = []

    def handle(request):
        calls.append((request.method, request.url.path, request.headers["X-OpenViking-User"]))
        path = request.url.path
        if path.endswith("/commit"):
            result = {"task_id": "task1"}
        elif path == "/api/v1/tasks/task1":
            result = {"status": "completed"}
        elif path == "/api/v1/search/find":
            result = {"memories": [{"uri": "viking://user/x/memories/pet.md", "score": 0.8}]}
        elif path == "/api/v1/content/read":
            result = "Maya has a tortoise called Saffron."
        else:
            result = {}
        return httpx.Response(200, json={"status": "ok", "result": result})

    original_client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original_client(transport=httpx.MockTransport(handle), **kwargs))
    memory = OpenVikingMemory()
    second = OpenVikingMemory()
    memory.setup()
    memory.ingest_session("c", Session(session_id="s", turns=[Turn(turn_id="t", speaker="Maya", text="My tortoise is Saffron.")]))
    hits = memory.search("c", "What is my tortoise called?")
    memory.teardown()

    assert memory.user_id != second.user_id
    assert all(user == memory.user_id for _, _, user in calls)
    assert any(path.endswith("/commit") for _, path, _ in calls)
    assert any(path == "/api/v1/system/wait" for _, path, _ in calls)
    assert hits[0].content == "Maya has a tortoise called Saffron."
    assert hits[0].session_ids == []
