"""Extract {title, authors, abstract} from the first pages of a paper PDF.

Strategy:

1. Try cheap regex-based pulls first (arXiv ID in the margin, DOI, an obvious
   first-line title, an "Abstract" block). These cover the vast majority of
   arXiv preprints and cost nothing.
2. Send the first-page text to the LLM to fill in whatever regex missed. The
   LLM sees the *raw* text, not the regex result, so it is free to overrule us.

The public entry point is :func:`extract_metadata`.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from pydantic import BaseModel, Field

from app.services.llm import chat_json

log = logging.getLogger(__name__)

# arXiv IDs come in two shapes: new style "2403.12345" (w/ optional version) and
# the legacy "cs.LG/0701234".
ARXIV_ID_RE = re.compile(
    r"\b(?:arXiv:\s*)?(?P<id>(?:\d{4}\.\d{4,5})(?:v\d+)?|(?:[a-z-]+(?:\.[A-Z]{2})?/\d{7}))",
    re.IGNORECASE,
)
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
ABSTRACT_RE = re.compile(
    r"\babstract\b[\s:\-—]*\n?(?P<body>.{80,3000}?)(?=\n\s*\n|\bintroduction\b|\b1\s)",
    re.IGNORECASE | re.DOTALL,
)


@dataclass
class RegexHints:
    arxiv_id: str | None
    doi: str | None
    abstract: str | None


def regex_hints(text: str) -> RegexHints:
    """Fast, deterministic extraction of easy-to-spot fields."""
    arxiv_match = ARXIV_ID_RE.search(text)
    doi_match = DOI_RE.search(text)
    abstract_match = ABSTRACT_RE.search(text)
    return RegexHints(
        arxiv_id=arxiv_match.group("id") if arxiv_match else None,
        doi=doi_match.group(0) if doi_match else None,
        abstract=(abstract_match.group("body").strip() if abstract_match else None),
    )


# --- LLM schema -------------------------------------------------------------


class LLMMetadata(BaseModel):
    """Schema the LLM is asked to return."""

    title: str = Field(..., description="Paper title, exactly as printed on page 1.")
    authors: list[str] = Field(
        default_factory=list,
        description="Ordered list of author full names.",
    )
    abstract: str = Field(
        default="",
        description="The paper abstract, verbatim if possible; empty string if absent.",
    )


@dataclass
class PaperMetadata:
    title: str
    authors: list[str]
    abstract: str
    arxiv_id: str | None
    doi: str | None


SYSTEM_PROMPT = (
    "You are an expert research librarian. Given the first pages of an academic paper, "
    "extract the title, the ordered list of authors, and the abstract. "
    "Keep fidelity to the source text; do not paraphrase or translate."
)


def _build_user_prompt(text: str) -> str:
    # Trim to first ~8k characters – comfortably covers page 1 and the abstract.
    trimmed = text[:8000]
    return (
        "Here is the extracted text from the first pages of a PDF paper. "
        "Return JSON with keys: title, authors (list of strings), abstract.\n\n"
        "--- PAPER TEXT START ---\n"
        f"{trimmed}\n"
        "--- PAPER TEXT END ---"
    )


def extract_metadata(text: str) -> PaperMetadata:
    """Extract structured metadata for a paper given its first-pages text.

    Regex runs first for IDs/abstract; the LLM is the source of truth for
    title and authors (hard to regex reliably).
    """
    hints = regex_hints(text)

    llm = chat_json(
        system=SYSTEM_PROMPT,
        user=_build_user_prompt(text),
        schema=LLMMetadata,
    )

    abstract = llm.abstract.strip() or (hints.abstract or "")
    return PaperMetadata(
        title=llm.title.strip(),
        authors=[a.strip() for a in llm.authors if a.strip()],
        abstract=abstract,
        arxiv_id=hints.arxiv_id,
        doi=hints.doi,
    )
