"""Author records, cached from Semantic Scholar."""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel


class Author(SQLModel, table=True):
    """Canonical author record with bibliometric cache."""

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)

    # Semantic Scholar author ID when resolved
    ss_author_id: str | None = Field(default=None, index=True)

    affiliation: str | None = Field(default=None)
    h_index: int | None = Field(default=None)
    citation_count: int | None = Field(default=None)
    is_famous: bool = Field(default=False)

    enriched_at: datetime | None = Field(default=None)
