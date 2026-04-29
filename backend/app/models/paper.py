"""Paper record: the main ORM model backing the poster wall."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlmodel import Field, SQLModel


class PaperStatus(str, Enum):
    """Lifecycle status of a paper entry."""

    PENDING = "pending"       # file recorded, not yet processed
    PROCESSING = "processing"  # pipeline in flight
    READY = "ready"           # metadata + summary + score available
    REJECTED = "rejected"     # failed the quality threshold (PDF may be removed)
    FAILED = "failed"         # pipeline raised an error


class Paper(SQLModel, table=True):
    """A scraped paper with metadata, LLM summary, and quality score."""

    id: int | None = Field(default=None, primary_key=True)

    # --- Identity --------------------------------------------------------
    arxiv_id: str | None = Field(default=None, index=True, unique=False)
    doi: str | None = Field(default=None, index=True)
    ss_paper_id: str | None = Field(default=None, index=True)
    content_hash: str | None = Field(default=None, index=True)

    # --- Metadata --------------------------------------------------------
    title: str = Field(index=True)
    # Comma-separated author list for simple querying; richer data lives in Author table.
    authors: str = Field(default="")
    abstract: str = Field(default="")
    venue: str | None = Field(default=None)
    published_at: datetime | None = Field(default=None)
    tags: str = Field(default="")  # JSON-encoded list

    # --- LLM summary -----------------------------------------------------
    summary_contribution: str = Field(default="")
    summary_method: str = Field(default="")
    summary_result: str = Field(default="")

    # --- Quality score (0-100 composite) --------------------------------
    score: float = Field(default=0.0, index=True)
    score_affiliation: float = Field(default=0.0)
    score_author_fame: float = Field(default=0.0)
    score_venue: float = Field(default=0.0)
    score_llm: float = Field(default=0.0)

    # --- Files -----------------------------------------------------------
    pdf_path: str | None = Field(default=None)
    thumbnail_path: str | None = Field(default=None)

    # --- Provenance ------------------------------------------------------
    source: str = Field(default="local")  # local | arxiv | semantic_scholar
    subscription_id: int | None = Field(default=None, foreign_key="subscription.id", index=True)

    status: PaperStatus = Field(default=PaperStatus.PENDING, index=True)
    error: str | None = Field(default=None)

    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
