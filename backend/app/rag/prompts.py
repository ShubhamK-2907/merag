"""Prompt templates for each node of the adaptive RAG graph.

Kept in code (not YAML) so they are type-checked, diffable and versioned with
the logic that fills them.
"""

CONTEXTUALIZE = """Given the conversation so far and a follow-up message, rewrite the follow-up
into a standalone question that can be understood without the conversation.
Do NOT answer it. If it is already standalone, return it unchanged.

Conversation:
{history}

Follow-up: {question}
Standalone question:"""

ROUTE = """You are the router of a retrieval-augmented assistant. Pick exactly one route.

- "index": the user's private knowledge base (their uploaded documents) is relevant
  to the question. Prefer this whenever the retrieved excerpts look related.
- "general": small talk, or a question answerable from stable general knowledge.
- "search": needs fresh, real-time or niche external information that is neither in
  the knowledge base nor reliable from general knowledge (news, prices, recent events).

Knowledge base contents:
{catalog}

Top retrieved excerpts (may be empty or irrelevant):
{excerpts}

Question: {question}

Also return relevant_ids: the ids of the excerpts that contain facts helping to answer
the question, even partially (empty if none)."""

GRADE = """You are grading retrieved excerpts for relevance to a question.
An excerpt is relevant if it contains facts that help answer the question, even partially.

Question: {question}

Excerpts:
{excerpts}

Return the ids of the relevant excerpts (may be empty)."""

REWRITE = """The search below returned nothing relevant from the user's documents.
Rewrite the query to improve semantic retrieval: expand abbreviations, add likely
synonyms and key terms, keep the intent. Return only the rewritten query.

Original query: {question}
Rewritten query:"""

GENERATE = """You are MeRAG, a precise assistant. Answer the question using ONLY the context.
- Cite supporting excerpts inline as [1], [2] matching the context numbers.
- If the context does not contain the answer, say so plainly instead of guessing
  (e.g. "Your documents don't say who approves this.").
- Answer directly. Never open with "Based on the provided context" or similar; the user
  sees the excerpts as "your documents" or "the web", not as "context".
- Use concise Markdown (short paragraphs, bullet lists when helpful).
{strict}
Context:
{context}

Question: {question}
Answer:"""

STRICT_SUFFIX = "- A previous draft contained claims not supported by the context. Be strictly extractive this time.\n"

VERIFY = """You are a strict fact checker. Decide whether every factual claim in the
answer is supported by the context. Ignore style; focus on unsupported facts.

Context:
{context}

Answer:
{answer}"""

GENERAL_SYSTEM = """You are MeRAG, a helpful, concise assistant. Answer from general knowledge.
Use light Markdown. If a question would need the user's own documents, suggest uploading them."""

SUMMARIZE_DOC = """Write a one-sentence description (max 25 words) of what this document is
about, for a catalog used to route questions. Start with the document type.

Excerpt:
{excerpt}

Description:"""
