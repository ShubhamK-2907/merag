"""API integration tests against a real MongoDB (auth, isolation, ingestion, SSE chat)."""

import json

import pytest

from tests.conftest import register

pytestmark = pytest.mark.asyncio


async def test_register_login_me(client):
    acct = await register(client, email="ana@example.com", password="s3cure-pass")
    r = await client.get("/api/auth/me", headers=acct["headers"])
    assert r.status_code == 200 and r.json()["email"] == "ana@example.com"

    r = await client.post("/api/auth/login", json={"email": "ANA@example.com", "password": "s3cure-pass"})
    assert r.status_code == 200 and r.json()["access_token"]


async def test_duplicate_email_and_bad_credentials(client):
    await register(client, email="dup@example.com")
    r = await client.post("/api/auth/register", json={"name": "x", "email": "dup@example.com", "password": "12345678"})
    assert r.status_code == 409
    r = await client.post("/api/auth/login", json={"email": "dup@example.com", "password": "wrong-password"})
    assert r.status_code == 401
    r = await client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "whatever1"})
    assert r.status_code == 401


async def test_protected_routes_require_valid_token(client):
    assert (await client.get("/api/conversations")).status_code == 401
    bad = {"Authorization": "Bearer not-a-jwt"}
    assert (await client.get("/api/documents", headers=bad)).status_code == 401


async def test_users_cannot_see_each_others_conversations(client):
    a, b = await register(client), await register(client)
    conv = (await client.post("/api/conversations", headers=a["headers"], json={})).json()
    assert (await client.get(f"/api/conversations/{conv['id']}/messages", headers=b["headers"])).status_code == 404
    assert (await client.delete(f"/api/conversations/{conv['id']}", headers=b["headers"])).status_code == 404
    assert (await client.get("/api/conversations", headers=b["headers"])).json() == []
    assert (await client.delete("/api/conversations/not-an-id", headers=a["headers"])).status_code == 404


async def test_document_upload_retrieval_isolation_and_delete(client, fake_embeddings):
    from app.rag import vectorstore

    a, b = await register(client), await register(client)
    text = ("Shubham built a retrieval augmented generation system with LangGraph and FastAPI. " * 30).encode()
    r = await client.post("/api/documents", headers=a["headers"], files={"file": ("notes.txt", text, "text/plain")})
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["chunk_count"] >= 2 and doc["description"] == "Auto description"

    hits_a = await vectorstore.search(a["user"]["id"], "LangGraph FastAPI system")
    hits_b = await vectorstore.search(b["user"]["id"], "LangGraph FastAPI system")
    assert hits_a and all(h["document_id"] == doc["id"] for h in hits_a)
    assert hits_b == []  # tenant isolation in retrieval

    assert (await client.delete(f"/api/documents/{doc['id']}", headers=b["headers"])).status_code == 404
    assert (await client.delete(f"/api/documents/{doc['id']}", headers=a["headers"])).status_code == 204
    assert await vectorstore.search(a["user"]["id"], "LangGraph") == []


async def test_upload_rejects_bad_type(client):
    a = await register(client)
    r = await client.post(
        "/api/documents", headers=a["headers"], files={"file": ("x.exe", b"MZ....", "application/octet-stream")}
    )
    assert r.status_code == 422


async def test_chat_streams_and_persists(client, monkeypatch):
    from langchain_core.messages import AIMessageChunk

    import app.services.chat as chat_service

    class FakeGraph:
        async def astream(self, inputs, stream_mode):
            yield "updates", {"route": {"route": "general", "trace": ["Routed to general: hi"]}}
            yield "messages", (AIMessageChunk(content="Hello "), {"langgraph_node": "general"})
            # Gemini 3 streams content blocks (with thought signatures) instead of a plain string.
            blocks = [{"type": "text", "text": "there", "extras": {"signature": "sig"}}]
            yield "messages", (AIMessageChunk(content=blocks), {"langgraph_node": "general"})
            yield "messages", (AIMessageChunk(content="internal"), {"langgraph_node": "grade"})
            yield "updates", {"general": {"route": "general", "answer": "Hello there", "trace": ["Answered"]}}

    monkeypatch.setattr(chat_service, "get_graph", lambda: FakeGraph())
    a = await register(client)
    conv = (await client.post("/api/conversations", headers=a["headers"], json={})).json()

    events = []
    async with client.stream(
        "POST", f"/api/conversations/{conv['id']}/messages", headers=a["headers"], json={"content": "hi there friend"}
    ) as r:
        assert r.status_code == 200
        event = None
        async for line in r.aiter_lines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:") and event:
                events.append((event, json.loads(line.split(":", 1)[1])))

    kinds = [e for e, _ in events]
    assert kinds.count("token") == 2 and kinds[-1] == "done"  # the "grade" chunk is not streamed
    assert "".join(d["text"] for e, d in events if e == "token") == "Hello there"
    final = events[-1][1]["message"]
    assert final["content"] == "Hello there" and final["route"] == "general"

    msgs = (await client.get(f"/api/conversations/{conv['id']}/messages", headers=a["headers"])).json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    convs = (await client.get("/api/conversations", headers=a["headers"])).json()
    assert convs[0]["title"] == "hi there friend"  # auto-titled from first message
