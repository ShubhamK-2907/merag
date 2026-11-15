"""Adaptive RAG pipeline as an explicit LangGraph state machine.

    START -> contextualize -> route+grade --relevant--> generate -> verify --ok--> END
                                 |   |                     ^          |
                                 |   +--none--> rewrite -> retrieve -> grade (bounded)
                                 |   |                     |          +--unsupported--> generate (bounded)
                                 |   +--still none--> web_search
                                 +--search--> web_search -> generate
                                 +--general--> general -> END

The router grades the excerpts it retrieved in the same structured call, so a typical
document question costs 3 LLM calls (route+grade, generate, verify), or 2 with
VERIFY_ANSWERS=false. The standalone grade node only runs after a query rewrite.

Ideas combined here:
  * Adaptive-RAG: route each query to the cheapest strategy that can answer it.
  * Corrective-RAG: grade retrieved chunks; rewrite / fall back to web when they miss.
  * Self-RAG style check: verify the answer is grounded in the context; regenerate once.
All loops are bounded by settings so a bad query can never spin forever.

Dependencies (LLM, retriever, web search) are injected, which makes every
branch unit-testable with fakes and no network.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal, Protocol

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.rag import prompts
from app.rag.state import Chunk, RAGState, Route, WebResult

Retriever = Callable[[str, str], Awaitable[list[Chunk]]]  # (user_id, query)
WebSearcher = Callable[[str], Awaitable[list[WebResult]]]

_MAX_CHUNK_CHARS = 1500


# ---------- structured LLM outputs ----------
class RouteDecision(BaseModel):
    """Routing and first-pass relevance grading in ONE call (saves an LLM call per question)."""

    route: Route = Field(description="index | general | search")
    reason: str = Field(description="One short sentence explaining the choice.")
    relevant_ids: list[int] = Field(
        default_factory=list, description="Ids of excerpts that help answer the question (may be empty)."
    )


class GradeResult(BaseModel):
    relevant_ids: list[int] = Field(description="Ids of excerpts relevant to the question.")


class VerifyResult(BaseModel):
    faithful: bool = Field(description="True if every claim is supported by the context.")
    reason: str = Field(description="One short sentence.")


class ChatModel(Protocol):
    """What the graph needs from an LLM: a BaseChatModel or app.rag.llm.ChatChain (with fallbacks)."""

    async def ainvoke(self, input: Any, /) -> BaseMessage: ...
    def with_structured_output(self, schema: Any, /) -> Any: ...


@dataclass(frozen=True)
class GraphDeps:
    llm: ChatModel
    retrieve: Retriever
    web_search: WebSearcher | None
    settings: Settings


# ---------- helpers ----------
def _format_history(history: list[BaseMessage]) -> str:
    return "\n".join(f"{'User' if isinstance(m, HumanMessage) else 'Assistant'}: {m.content}" for m in history)


def _format_excerpts(chunks: list[Chunk], limit: int = 400) -> str:
    if not chunks:
        return "(none)"
    return "\n".join(f"[{i}] ({c['filename']}) {c['text'][:limit]}" for i, c in enumerate(chunks))


def _format_context(state: RAGState) -> str:
    if state.get("route") == "search":
        results = state.get("web_results", [])
        return "\n\n".join(f"[{i + 1}] {r['title']} ({r['url']})\n{r['content']}" for i, r in enumerate(results))
    chunks = state.get("chunks", [])
    return "\n\n".join(
        f"[{i + 1}] (source: {c['filename']})\n{c['text'][:_MAX_CHUNK_CHARS]}" for i, c in enumerate(chunks)
    )


def build_graph(deps: GraphDeps):
    llm, s = deps.llm, deps.settings

    # ---------- nodes ----------
    async def contextualize(state: RAGState) -> dict:
        history = state.get("history") or []
        question = state["question"]
        if not history:
            return {"query": question, "trace": []}
        msg = await llm.ainvoke(prompts.CONTEXTUALIZE.format(history=_format_history(history), question=question))
        query = msg.text.strip() or question
        trace = [f"Resolved follow-up into: “{query}”"] if query != question else []
        return {"query": query, "trace": trace}

    async def route(state: RAGState) -> dict:
        catalog = state.get("catalog") or ""
        chunks = await deps.retrieve(state["user_id"], state["query"]) if catalog else []
        router = llm.with_structured_output(RouteDecision)
        decision: RouteDecision = await router.ainvoke(
            prompts.ROUTE.format(
                catalog=catalog or "(no documents uploaded)",
                excerpts=_format_excerpts(chunks, limit=800),
                question=state["query"],
            )
        )
        chosen, note = decision.route, decision.reason
        if chosen == "index" and not catalog:
            chosen, note = "general", "No documents uploaded, answering from general knowledge."
        if chosen == "search" and deps.web_search is None:
            chosen, note = "general", "Web search is not configured, answering from general knowledge."
        trace = [f"Routed to {chosen}: {note}"]
        if chosen == "index":
            # The router graded the excerpts in the same call; keep only the relevant ones.
            keep = sorted({i for i in decision.relevant_ids if 0 <= i < len(chunks)})
            trace.append(f"Graded chunks: {len(keep)}/{len(chunks)} relevant")
            chunks = [chunks[i] for i in keep]
        return {"route": chosen, "chunks": chunks, "rewrites": 0, "generations": 0, "trace": trace}

    async def retrieve(state: RAGState) -> dict:
        chunks = await deps.retrieve(state["user_id"], state["query"])
        return {"chunks": chunks, "trace": [f"Retrieved {len(chunks)} chunks"]}

    async def grade(state: RAGState) -> dict:
        chunks = state.get("chunks", [])
        if not chunks:
            return {"chunks": [], "trace": ["No chunks to grade"]}
        grader = llm.with_structured_output(GradeResult)
        result: GradeResult = await grader.ainvoke(
            prompts.GRADE.format(question=state["query"], excerpts=_format_excerpts(chunks, limit=800))
        )
        keep = sorted({i for i in result.relevant_ids if 0 <= i < len(chunks)})
        relevant = [chunks[i] for i in keep]
        return {"chunks": relevant, "trace": [f"Graded chunks: {len(relevant)}/{len(chunks)} relevant"]}

    async def rewrite(state: RAGState) -> dict:
        msg = await llm.ainvoke(prompts.REWRITE.format(question=state["query"]))
        query = msg.text.strip() or state["query"]
        return {
            "query": query,
            "rewrites": state.get("rewrites", 0) + 1,
            "trace": [f"Rewrote query for retrieval: “{query}”"],
        }

    async def web_search(state: RAGState) -> dict:
        results = await deps.web_search(state["query"]) if deps.web_search else []
        return {"route": "search", "web_results": results, "trace": [f"Searched the web: {len(results)} results"]}

    async def generate(state: RAGState) -> dict:
        n = state.get("generations", 0)
        msg = await llm.ainvoke(
            prompts.GENERATE.format(
                strict=prompts.STRICT_SUFFIX if n > 0 else "",
                context=_format_context(state) or "(no context found)",
                question=state["query"],
            )
        )
        return {
            "answer": msg.text.strip(),
            "generations": n + 1,
            "trace": ["Generated grounded answer" if n == 0 else "Regenerated with stricter grounding"],
        }

    async def verify(state: RAGState) -> dict:
        context = _format_context(state)
        if not context or not s.verify_answers:
            return {"faithful": True, "trace": []}
        checker = llm.with_structured_output(VerifyResult)
        result: VerifyResult = await checker.ainvoke(prompts.VERIFY.format(context=context, answer=state["answer"]))
        label = "passed" if result.faithful else "failed"
        return {"faithful": result.faithful, "trace": [f"Grounding check {label}: {result.reason}"]}

    async def general(state: RAGState) -> dict:
        history = (state.get("history") or [])[-s.history_window :]
        messages = [SystemMessage(prompts.GENERAL_SYSTEM), *history, HumanMessage(state["question"])]
        msg = await llm.ainvoke(messages)
        return {"route": "general", "answer": msg.text.strip(), "trace": ["Answered from general knowledge"]}

    # ---------- conditional edges ----------
    def after_route(state: RAGState) -> Literal["generate", "rewrite", "web_search", "general"]:
        if state["route"] == "index":
            return after_grade(state)  # chunks were already graded inside the route call
        return "web_search" if state["route"] == "search" else "general"

    def after_grade(state: RAGState) -> Literal["generate", "rewrite", "web_search", "general"]:
        if state.get("chunks"):
            return "generate"
        if state.get("rewrites", 0) < s.max_rewrites:
            return "rewrite"
        return "web_search" if deps.web_search else "general"

    def after_verify(state: RAGState) -> Literal["generate", "__end__"]:
        if state.get("faithful", True) or state.get("generations", 0) > s.max_regenerations:
            return END
        return "generate"

    g = StateGraph(RAGState)
    for name, fn in [
        ("contextualize", contextualize),
        ("route", route),
        ("retrieve", retrieve),
        ("grade", grade),
        ("rewrite", rewrite),
        ("web_search", web_search),
        ("generate", generate),
        ("verify", verify),
        ("general", general),
    ]:
        g.add_node(name, fn)

    g.add_edge(START, "contextualize")
    g.add_edge("contextualize", "route")
    g.add_conditional_edges("route", after_route)
    g.add_conditional_edges("grade", after_grade)
    g.add_edge("rewrite", "retrieve")
    g.add_edge("retrieve", "grade")
    g.add_edge("web_search", "generate")
    g.add_edge("generate", "verify")
    g.add_conditional_edges("verify", after_verify)
    g.add_edge("general", END)
    return g.compile()


# Nodes whose LLM output is the user-facing answer (streamed token by token).
ANSWER_NODES = frozenset({"generate", "general"})


@lru_cache
def get_graph():
    """Production graph wired to OpenAI, Mongo vector search and Tavily."""
    from app.rag import vectorstore
    from app.rag import web_search as web
    from app.rag.llm import get_chat_model

    return build_graph(
        GraphDeps(
            llm=get_chat_model(),
            retrieve=vectorstore.search,
            web_search=web.search if web.is_enabled() else None,
            settings=get_settings(),
        )
    )


def history_to_messages(rows: list[dict]) -> list[BaseMessage]:
    return [HumanMessage(r["content"]) if r["role"] == "user" else AIMessage(r["content"]) for r in rows]
