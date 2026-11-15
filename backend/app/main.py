"""FastAPI application factory."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.routes import auth, chats, documents
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.rate_limit import limiter
from app.db import mongo

_DEFAULT_SECRET = "dev-only-secret-change-me-please"  # noqa: S105 - sentinel, not a credential

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    if settings.is_production and settings.jwt_secret == _DEFAULT_SECRET:
        raise RuntimeError("JWT_SECRET must be set in production")
    if not settings.llm_api_key:
        logger.warning("No API key for LLM provider %r: chat and uploads will fail", settings.llm_provider)
    await mongo.connect()
    await mongo.ensure_indexes()
    yield
    await mongo.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=False,  # bearer tokens, not cookies
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    for r in (auth.router, chats.router, documents.router):
        app.include_router(r, prefix="/api")

    @app.get("/api/health", tags=["meta"])
    async def health():
        await mongo.get_db().command("ping")
        return {"status": "ok"}

    _mount_frontend(app, settings.app_name)
    return app


def _mount_frontend(app: FastAPI, name: str) -> None:
    """In the production image the built React app lives in ./static and is served
    from the same origin as the API: one deploy, one URL, no CORS round-trips."""
    static_dir = Path(__file__).resolve().parent.parent / "static"
    if not (static_dir / "index.html").is_file():

        @app.get("/", include_in_schema=False)
        async def root():
            return {"name": name, "docs": "/api/docs"}

        return

    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404, "Not Found")
        candidate = (static_dir / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(static_dir):
            return FileResponse(candidate)
        return FileResponse(static_dir / "index.html")  # client-side routes


app = create_app()
