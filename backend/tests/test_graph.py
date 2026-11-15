"""Unit tests for every branch of the adaptive RAG graph, using a scripted fake LLM."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.core.config import Settings
from app.rag.graph import GradeResult, GraphDeps, RouteDecision, VerifyResult, build_graph

CHUNK = {"id": "c1", "document_id": "d1", "filename": "resume.pdf", "text": "Shubham knows Python.", "score": 0.9}
WEB = {"title": "News", "url": "https://example.com", "content": "Fresh fact."}


class _Structured:
    def __init__(self, parent, schema):
        self.parent, self.schema = parent, schema

    async def ainvoke(self, _prompt):
        self.parent.structured_calls.append(self.schema.__name__)
        if self.schema is RouteDecision:
            # The router also grades: it consumes the first scripted grade when routing to the index.
            ids = self.parent.grades.pop(0) if self.parent.route == "index" else []
            return RouteDecision(route=self.parent.route, reason="test", relevant_ids=ids)
        if self.schema is GradeResult:
            return GradeResult(relevant_ids=self.parent.grades.pop(0))
        if self.schema is VerifyResult:
            return VerifyResult(faithful=self.parent.verdicts.pop(0), reason="test")
        raise AssertionError(self.schema)


class FakeLLM:
    def __init__(self, route="index", grades=None, verdicts=None):
        self.route = route
        self.grades = grades if grades is not None else [[0]]
        self.verdicts = verdicts if verdicts is not None else [True]
        self.prompts: list = []
        self.structured_calls: list[str] = []

    def with_structured_output(self, schema):
        return _Structured(self, schema)

    async def ainvoke(self, prompt):
        self.prompts.append(prompt)
        text = prompt if isinstance(prompt, str) else ""
        if "Standalone question" in text:
            return AIMessage("What does Shubham know?")
        if "Rewritten query" in text:
            return AIMessage("rewritten query")
        return AIMessage("final answer [1]")


def make(llm, retrieve_results=None, web=True, **overrides):
    calls = {"retrieve": 0, "web": 0}

    async def retrieve(user_id, query):
        calls["retrieve"] += 1
        return list(retrieve_results if retrieve_results is not None else [CHUNK])

    async def web_search(query):
        calls["web"] += 1
        return [WEB]

    settings = Settings(max_rewrites=1, max_regenerations=1, **overrides)
    graph = build_graph(
        GraphDeps(llm=llm, retrieve=retrieve, web_search=web_search if web else None, settings=settings)
    )
    return graph, calls


def inputs(**kw):
    base = {
        "user_id": "u1",
        "question": "What does Shubham know?",
        "history": [],
        "catalog": "- resume.pdf: CV",
        "trace": [],
    }
    return base | kw


@pytest.mark.asyncio
async def test_index_route_happy_path():
    graph, calls = make(FakeLLM(route="index"))
    out = await graph.ainvoke(inputs())
    assert out["route"] == "index"
    assert out["answer"] == "final answer [1]"
    assert out["chunks"] == [CHUNK]
    assert out["generations"] == 1
    assert calls == {"retrieve": 1, "web": 0}  # route node's retrieval is reused, not repeated


@pytest.mark.asyncio
async def test_routing_and_grading_share_one_llm_call():
    llm = FakeLLM(route="index")
    graph, _ = make(llm)
    out = await graph.ainvoke(inputs())
    # route+grade (1 structured call) + generate (1 text call) + verify (1 structured call) = 3 calls
    assert llm.structured_calls == ["RouteDecision", "VerifyResult"]
    assert len(llm.prompts) == 1
    assert "Graded chunks: 1/1 relevant" in out["trace"]


@pytest.mark.asyncio
async def test_verify_can_be_disabled_to_save_a_call():
    llm = FakeLLM(route="index", verdicts=[])
    graph, _ = make(llm, verify_answers=False)
    out = await graph.ainvoke(inputs())
    assert llm.structured_calls == ["RouteDecision"]
    assert out["answer"] == "final answer [1]"


@pytest.mark.asyncio
async def test_irrelevant_chunks_rewrite_then_fall_back_to_web():
    graph, calls = make(FakeLLM(route="index", grades=[[], []]))
    out = await graph.ainvoke(inputs())
    assert out["rewrites"] == 1
    assert out["route"] == "search"
    assert out["web_results"] == [WEB]
    assert calls == {"retrieve": 2, "web": 1}
    assert any("Rewrote query" in t for t in out["trace"])


@pytest.mark.asyncio
async def test_irrelevant_chunks_without_web_fall_back_to_general():
    graph, _ = make(FakeLLM(route="index", grades=[[], []]), web=False)
    out = await graph.ainvoke(inputs())
    assert out["route"] == "general"


@pytest.mark.asyncio
async def test_unfaithful_answer_is_regenerated_once_then_stops():
    llm = FakeLLM(route="index", verdicts=[False, False])
    graph, _ = make(llm)
    out = await graph.ainvoke(inputs())
    assert out["generations"] == 2  # bounded: no infinite loop
    assert any("stricter" in t for t in out["trace"])


@pytest.mark.asyncio
async def test_index_without_documents_becomes_general():
    graph, calls = make(FakeLLM(route="index"))
    out = await graph.ainvoke(inputs(catalog=""))
    assert out["route"] == "general"
    assert calls["retrieve"] == 0


@pytest.mark.asyncio
async def test_search_without_web_tool_becomes_general():
    graph, _ = make(FakeLLM(route="search"), web=False)
    out = await graph.ainvoke(inputs())
    assert out["route"] == "general"


@pytest.mark.asyncio
async def test_follow_up_is_contextualized():
    llm = FakeLLM(route="general")
    graph, _ = make(llm)
    history = [HumanMessage("Tell me about Shubham"), AIMessage("He is an engineer.")]
    out = await graph.ainvoke(inputs(question="what does he know?", history=history))
    assert out["query"] == "What does Shubham know?"
    assert "Standalone question" in llm.prompts[0]


async def test_describe_falls_back_when_llm_fails(monkeypatch):
    """A rate-limited summary call must not fail the upload."""
    from app.rag import ingestion

    class Boom:
        async def ainvoke(self, _):
            raise RuntimeError("429 RESOURCE_EXHAUSTED")

    monkeypatch.setattr(ingestion, "get_chat_model", lambda: Boom())
    out = await ingestion.describe("cv.pdf", "Jane Doe\n  Senior ML Engineer   at Acme")
    assert out == "cv.pdf: Jane Doe Senior ML Engineer at Acme"


def test_rate_limit_errors_get_a_clear_message():
    from app.services.chat import _error_detail

    assert "rate limit" in _error_detail(RuntimeError("429 RESOURCE_EXHAUSTED quota"))
    assert _error_detail(ValueError("boom")) == "The assistant hit an error. Please try again."


async def test_chat_chain_falls_back_when_a_model_is_rate_limited():
    from langchain_core.language_models import FakeListChatModel

    from app.rag.llm import ChatChain

    class RateLimited(FakeListChatModel):
        async def _agenerate(self, *args, **kwargs):
            raise RuntimeError("429 RESOURCE_EXHAUSTED")

    chain = ChatChain([RateLimited(responses=["never"]), FakeListChatModel(responses=["from fallback"])])
    assert (await chain.ainvoke("hi")).text == "from fallback"


def test_llm_fallbacks_setting_is_parsed_and_validated():
    s = Settings(llm_fallbacks="gemini:gemini-3.1-flash-lite, groq:openai/gpt-oss-20b")
    assert s.fallback_models() == [("gemini", "gemini-3.1-flash-lite"), ("groq", "openai/gpt-oss-20b")]
    groq = Settings(llm_provider="groq")
    assert groq.chat_model == "openai/gpt-oss-20b" and groq.embedding_provider == "gemini"
    with pytest.raises(ValueError):
        Settings(llm_fallbacks="gpt-4o")
