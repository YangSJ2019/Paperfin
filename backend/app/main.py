"""FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import init_db

settings = get_settings()

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("paperfin")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup / shutdown routines."""
    log.info("Paperfin starting up; data_dir=%s", settings.data_dir.resolve())
    init_db()
    yield
    log.info("Paperfin shutting down")


app = FastAPI(
    title="Paperfin",
    version="0.1.0",
    description="Jellyfin-style paper scraper and subscription tool.",
    lifespan=lifespan,
)

# Frontend runs on Vite dev server; allow its default origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    """Liveness probe used by the frontend and health checks."""
    return {"status": "ok", "version": app.version}


# --- Routers ----------------------------------------------------------------
from app.api import papers as papers_api  # noqa: E402

app.include_router(papers_api.router, prefix="/api")
