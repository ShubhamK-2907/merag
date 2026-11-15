"""Typed state that flows through the LangGraph pipeline."""

import operator
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import BaseMessage

Route = Literal["index", "general", "search"]


class Chunk(TypedDict):
    id: str
    document_id: str
    filename: str
    text: str
    score: float


class WebResult(TypedDict):
    title: str
    url: str
    content: str


class RAGState(TypedDict, total=False):
    # Inputs
    user_id: str
    question: str
    history: list[BaseMessage]
    catalog: str  # one line per uploaded document: "filename: description"

    # Working memory
    query: str  # standalone (and possibly rewritten) query used for retrieval
    route: Route
    chunks: list[Chunk]
    web_results: list[WebResult]
    rewrites: int
    generations: int
    faithful: bool | None

    # Output
    answer: str
    # Append-only human-readable log of the path taken (shown in the UI).
    trace: Annotated[list[str], operator.add]
