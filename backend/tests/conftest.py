"""Test fixtures.

Graph tests are pure (fake LLM, no network, no DB).
API tests need a MongoDB: set MONGODB_URI (defaults to localhost) and they use a
throwaway database that is dropped afterwards. They are skipped if Mongo is down.
"""

import hashlib
import math
import os
import uuid

import pytest
import pytest_asyncio

os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret")
os.environ["MONGODB_DB"] = f"merag_test_{uuid.uuid4().hex[:8]}"
os.environ.setdefault("OPENAI_API_KEY", "sk-test")


class FakeEmbeddings:
    """Deterministic bag-of-words embeddings: similar text -> similar vectors."""

    dim = 64

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for word in text.lower().split():
            v[int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dim] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    async def aembed_documents(self, texts):
        return [self._vec(t) for t in texts]

    async def aembed_query(self, text):
        return self._vec(text)


@pytest.fixture
def fake_embeddings(monkeypatch):
    emb = FakeEmbeddings()
    import app.rag.ingestion as ingestion
    import app.rag.vectorstore as vectorstore

    monkeypatch.setattr(ingestion, "get_embeddings", lambda: emb)
    monkeypatch.setattr(vectorstore, "get_embeddings", lambda: emb)

    async def _describe(text: str) -> str:
        return "Auto description"

    monkeypatch.setattr(ingestion, "describe", _describe)
    return emb


@pytest_asyncio.fixture
async def client():
    from httpx import ASGITransport, AsyncClient

    from app.core.rate_limit import limiter
    from app.db import mongo
    from app.main import app

    try:
        await mongo.connect()
    except Exception:
        pytest.skip("MongoDB not reachable")
    await mongo.ensure_indexes()
    limiter.enabled = False
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await mongo._client.drop_database(os.environ["MONGODB_DB"])
    await mongo.close()


async def register(client, email: str | None = None, password: str = "correct-horse") -> dict:
    email = email or f"{uuid.uuid4().hex[:8]}@example.com"
    r = await client.post("/api/auth/register", json={"name": "Test", "email": email, "password": password})
    assert r.status_code == 201, r.text
    body = r.json()
    return {"headers": {"Authorization": f"Bearer {body['access_token']}"}, "user": body["user"], "email": email}
