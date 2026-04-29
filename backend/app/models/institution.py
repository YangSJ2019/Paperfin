"""Institution registry used for quality scoring."""

from __future__ import annotations

from enum import Enum

from sqlmodel import Field, SQLModel


class InstitutionTier(str, Enum):
    """Tiers used by the affiliation scorer."""

    TOP = "top"        # e.g. MIT, Stanford, Google, OpenAI, DeepMind
    MAJOR = "major"    # solid R1 universities and major industry labs
    OTHER = "other"    # default


class Institution(SQLModel, table=True):
    """Known institution and its tier for scoring."""

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    tier: InstitutionTier = Field(default=InstitutionTier.OTHER, index=True)
    aliases: str = Field(default="")  # JSON-encoded list of alt names
