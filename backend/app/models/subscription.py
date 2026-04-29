"""Subscription: a saved query against an external paper source."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlmodel import Field, SQLModel


class SubscriptionSource(str, Enum):
    ARXIV = "arxiv"
    SEMANTIC_SCHOLAR = "semantic_scholar"


class Subscription(SQLModel, table=True):
    """A saved search that the scheduler periodically re-runs."""

    id: int | None = Field(default=None, primary_key=True)

    name: str = Field(index=True)
    source: SubscriptionSource = Field(default=SubscriptionSource.ARXIV, index=True)
    query: str = Field(default="")           # native query string for the source
    min_quality: float = Field(default=0.0)   # papers below this score are REJECTED
    max_results_per_run: int = Field(default=20)

    interval_hours: int = Field(default=6)
    enabled: bool = Field(default=True, index=True)

    last_run_at: datetime | None = Field(default=None)
    last_error: str | None = Field(default=None)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
