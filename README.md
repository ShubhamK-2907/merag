# MeRAG: Adaptive RAG Assistant

An authenticated, multi-tenant **adaptive retrieval-augmented generation** app. Upload your own documents and ask questions; a LangGraph state machine decides, per question, whether to answer from **your documents**, **general knowledge**, or the **web**, then grades its retrieval, rewrites weak queries, and verifies the answer is grounded before returning it. Progress and tokens stream live to the UI.

```
React SPA ──SSE/JSON──▶ FastAPI ──▶ LangGraph pipeline ──▶ free Gemini model chain (+ optional Groq) with automatic fallback
                           │                │
                           │                └──▶ Tavily (optional web search)
                           └──▶ MongoDB Atlas: users · conversations · messages · documents · chunks + $vectorSearch
```

## The pipeline

```
START → contextualize → route+grade ─relevant──▶ generate → verify ─grounded─▶ END
                          │   │                       ▲          └─not grounded─▶ generate (once)
                          │   ├─none─▶ rewrite ─▶ retrieve ─▶ grade (bounded)
                          │   └─still none─▶ web_search ─▶ generate
                          ├─search──▶ web_search ─▶ generate
                          └─general─▶ general ─▶ END
```

| Node | What it does |
|---|---|
| `contextualize` | Rewrites a follow-up ("what about his skills?") into a standalone question using chat history |
| `route` | Retrieves top-k chunks for the user, then **one** structured LLM call picks `index` / `general` / `search` (given a catalog of the user's documents) **and** marks which excerpts are relevant |
| `grade` | After a query rewrite only: one batched LLM call marks which retrieved chunks are relevant (Corrective RAG) |
| `rewrite` | Reformulates the query for better semantic recall when nothing relevant came back |
| `web_search` | Tavily search, used for fresh info or as a fallback when the docs don't cover it |
| `generate` | Answers strictly from numbered context, with inline `[n]` citations |
| `verify` | Checks every claim is supported by the context; regenerates once in stricter mode if not (Self-RAG style) |
| `general` | Plain LLM answer with conversation history |

All loops are bounded (`MAX_REWRITES`, `MAX_REGENERATIONS`), so a bad query can never spin. A document question costs 3 LLM calls (2 with `VERIFY_ANSWERS=false`); a general question costs 2.

## Free-tier LLMs and automatic fallback

Free tiers rate-limit **per model**, so the chat model is a chain (`rag/llm.py`, LangChain `with_fallbacks`): when one model returns a 429, the same request moves to the next. Each model has its own quota, so three Gemini models on one free key roughly triple capacity.

```env
LLM_PROVIDER=gemini                     # primary: gemini-flash-lite-latest
LLM_FALLBACKS=gemini:gemini-3.1-flash-lite,gemini:gemini-2.5-flash-lite,groq:openai/gpt-oss-20b
GROQ_API_KEY=                           # optional second free provider (console.groq.com); skipped if empty
VERIFY_ANSWERS=true                     # false saves one call per document answer
```

Embeddings always use Gemini (`gemini-embedding-001`, its own quota), since Groq has no embedding API.

## Features

- **Auth**: email + password (bcrypt), stateless JWT bearer tokens, rate-limited login/register, timing-safe login (no user enumeration)
- **Multi-tenant RAG**: every vector query is pre-filtered by `user_id` inside Atlas Vector Search
- **Streaming**: Server-Sent Events carry pipeline steps, answer tokens, and a final persisted message
- **Transparency**: each answer shows its route, the steps taken, and source snippets with similarity scores
- **Persistence**: conversations (auto-titled, renamable), messages, documents, all in MongoDB
- **Ingestion**: PDF/TXT/MD → text → recursive chunking (1000/150) → batched embeddings; auto-generated description if none given; all-or-nothing writes
- **Single-origin deploy**: one Docker image serves the API and the built React app

## Tech stack

**Backend:** Python 3.12, FastAPI, LangGraph, LangChain (Google GenAI / Groq / OpenAI, switchable via `LLM_PROVIDER`, with a fallback chain), PyMongo (native async), PyJWT, bcrypt, slowapi, sse-starlette, pypdf
**Frontend:** React 19, TypeScript, Vite, Tailwind CSS v4, React Router, react-markdown
**Infra:** MongoDB Atlas (+ Vector Search), Render (Docker), GitHub Actions CI

## Run locally

```bash
# 1. MongoDB (any of these)
brew services start mongodb-community        # or: docker run -d -p 27017:27017 mongo:7

# 2. Backend
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                         # add GOOGLE_API_KEY (free) or set LLM_PROVIDER=openai + OPENAI_API_KEY
uvicorn app.main:app --reload                # http://localhost:8000/api/docs

# 3. Frontend
cd ../frontend
npm install
npm run dev                                  # http://localhost:5173
```

On a plain local MongoDB (no Atlas Search), retrieval transparently falls back to an exact cosine scan over the user's chunks. On Atlas, the vector index is created automatically at startup.

## Tests

```bash
cd backend
pip install pytest pytest-asyncio httpx ruff
pytest -q          # 14 tests: every graph branch (fake LLM) + API/auth/isolation/SSE against real MongoDB
ruff check app tests
```

## Deploy (Render + MongoDB Atlas)

1. **MongoDB Atlas**: create a free cluster, a database user, and allow network access (`0.0.0.0/0` for Render's free tier). Copy the `mongodb+srv://…` connection string.
2. **Render**: New → Blueprint → select this repo. `render.yaml` defines the service; you'll be prompted for `MONGODB_URI`, `GOOGLE_API_KEY` (free from Google AI Studio), and optionally `TAVILY_API_KEY`. `JWT_SECRET` is generated automatically.
3. Open the service URL. The Atlas vector index builds itself on first boot (takes about a minute; until it's queryable the app uses the exact-scan fallback).

> Everything above runs at $0. Gemini's free tier is rate-limited (each question makes 2–3 LLM calls, spread over a fallback chain of models), and Google may use free-tier inputs to improve its products, so don't upload sensitive documents.
>
> Free-tier note: Render free services sleep after ~15 min idle; the first request after that takes ~30–60 s.

## Project layout

```
backend/app/
  api/routes/      auth.py · chats.py (SSE) · documents.py
  core/            config (pydantic-settings) · security (JWT/bcrypt) · rate_limit · logging
  db/mongo.py      async client, indexes, vector index bootstrap + readiness
  rag/             graph.py (LangGraph) · prompts.py · vectorstore.py · ingestion.py · web_search.py · llm.py
  services/        users · conversations · documents · chat (graph → SSE events)
backend/tests/     test_graph.py (pure) · test_api.py (integration)
frontend/src/
  lib/api.ts       typed API client + SSE-over-fetch parser
  auth/            AuthContext (token lifecycle)
  pages/           AuthPage · AppShell
  components/      Sidebar · ChatView · MessageItem · Composer · KnowledgePanel · ui
```
