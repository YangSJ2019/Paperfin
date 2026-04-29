"""Core scraping pipeline.

Two entry points share a common "finish" stage (LLM metadata + summary + persist):

* :func:`process_local_pdf` — for PDFs already on disk (``/data/papers/`` scan)
* :func:`process_url` — for arXiv links and plain PDF URLs

Both are synchronous: PDF parsing is CPU-bound and LLM calls block on network,
so running them on a thread from a FastAPI BackgroundTask is a better fit than
async for now.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from sqlmodel import Session, select

from app.config import get_settings
from app.models import Paper, PaperStatus
from app.services import metadata_extractor, pdf_parser, quality, summarizer, url_ingest

log = logging.getLogger(__name__)


class PipelineError(RuntimeError):
    """Non-fatal failure during processing of a single paper."""


# --- Dedup lookups ----------------------------------------------------------


def find_existing_by_hash(session: Session, content_hash: str) -> Paper | None:
    stmt = select(Paper).where(Paper.content_hash == content_hash)
    return session.exec(stmt).first()


def find_existing_by_arxiv_id(session: Session, arxiv_id: str) -> Paper | None:
    """Look up a paper by arxiv id, ignoring version suffix.

    ``2403.12345`` should dedup against any ``2403.12345vN`` already in the DB
    (and vice-versa). We don't require exact version equality.
    """
    base = arxiv_id.split("v", 1)[0] if "v" in arxiv_id else arxiv_id
    # Match both the bare id and any versioned variants.
    stmt = select(Paper).where(
        (Paper.arxiv_id == arxiv_id) | (Paper.arxiv_id == base) | (Paper.arxiv_id.like(f"{base}v%"))
    )
    return session.exec(stmt).first()


# --- Shared finish stage ----------------------------------------------------


def _apply_summary_and_score(paper: Paper, text: str) -> None:
    """Run summarizer + quality scorer on ``text`` and mutate ``paper`` in-place.

    Raised exceptions propagate to the caller; the caller owns the transaction.
    """
    summary = summarizer.summarize(text, title=paper.title)
    paper.summary_contribution = summary.contribution
    paper.summary_method = summary.method
    paper.summary_result = summary.result
    paper.tags = json.dumps(summary.tags, ensure_ascii=False)

    # Quality scoring. For now score_llm == score (no institution/venue
    # signals yet); we still populate all columns so the UI radar renders.
    qs = quality.score_paper(text, title=paper.title)
    paper.score = qs.score
    paper.score_llm = qs.score_llm
    paper.score_affiliation = qs.score_affiliation
    paper.score_author_fame = qs.score_author_fame
    paper.score_venue = qs.score_venue


def _finish_paper(
    session: Session,
    pdf_path: Path,
    parsed: pdf_parser.ParsedPdf,
    *,
    source: str,
    arxiv_id_hint: str | None = None,
    subscription_id: int | None = None,
) -> Paper:
    """Given a parsed PDF on disk, run the LLM stages and persist a Paper.

    Assumes the caller has already checked content-hash dedup and decided this
    file warrants processing. Handles the create → PROCESSING → READY/FAILED
    lifecycle and the final commit.
    """
    paper = Paper(
        pdf_path=str(pdf_path.resolve()),
        thumbnail_path=str(parsed.thumbnail_path.resolve()) if parsed.thumbnail_path else None,
        content_hash=parsed.content_hash,
        title=pdf_path.stem,  # placeholder until metadata extraction
        source=source,
        subscription_id=subscription_id,
        arxiv_id=arxiv_id_hint,
        status=PaperStatus.PROCESSING,
    )
    session.add(paper)
    session.commit()
    session.refresh(paper)

    try:
        meta = metadata_extractor.extract_metadata(parsed.text)
        paper.title = meta.title or paper.title
        paper.authors = ", ".join(meta.authors)
        paper.abstract = meta.abstract
        # Prefer the URL-supplied arxiv_id (more reliable than PDF regex) but
        # fall back to whatever the metadata extractor found.
        paper.arxiv_id = arxiv_id_hint or meta.arxiv_id
        paper.doi = meta.doi

        _apply_summary_and_score(paper, parsed.text)

        paper.status = PaperStatus.READY
        paper.error = None
    except Exception as exc:
        log.exception("Pipeline failed for %s", pdf_path.name)
        paper.status = PaperStatus.FAILED
        paper.error = str(exc)[:500]
    finally:
        paper.updated_at = datetime.utcnow()
        session.add(paper)
        session.commit()
        session.refresh(paper)

    return paper


# --- Entry points -----------------------------------------------------------


def resummarize_paper(session: Session, paper: Paper) -> Paper:
    """Re-run summarizer + quality scorer on an existing paper, preserving metadata.

    Useful after changing the summarizer prompt or scoring weights. The PDF
    must still exist on disk. Metadata (title/authors/abstract) is untouched;
    only the summary text, tags, and score_* columns are refreshed.
    """
    if not paper.pdf_path or not Path(paper.pdf_path).exists():
        raise PipelineError(f"PDF for paper id={paper.id} is missing on disk")

    settings = get_settings()
    log.info("Resummarizing + rescoring paper id=%s (%s)", paper.id, paper.title)
    parsed = pdf_parser.parse_pdf(
        Path(paper.pdf_path), thumbnails_dir=settings.thumbnails_dir
    )

    try:
        _apply_summary_and_score(paper, parsed.text)
        paper.status = PaperStatus.READY
        paper.error = None
    except Exception as exc:
        log.exception("Resummarize failed for paper id=%s", paper.id)
        paper.error = str(exc)[:500]
        # Keep the old summary; don't wipe the paper to FAILED state just
        # because a reprocess attempt crashed.
    finally:
        paper.updated_at = datetime.utcnow()
        session.add(paper)
        session.commit()
        session.refresh(paper)

    return paper


def process_local_pdf(session: Session, pdf_path: Path) -> Paper:
    """Process a single local PDF file and persist a Paper row."""
    settings = get_settings()
    log.info("Processing %s", pdf_path.name)

    parsed = pdf_parser.parse_pdf(pdf_path, thumbnails_dir=settings.thumbnails_dir)

    existing = find_existing_by_hash(session, parsed.content_hash)
    if existing is not None:
        log.info("Skipping %s: already indexed as paper id=%s", pdf_path.name, existing.id)
        return existing

    return _finish_paper(session, pdf_path, parsed, source="local")


def process_url(session: Session, url: str) -> Paper:
    """Download a paper by URL and run the full pipeline on it.

    Dedup strategy:

    1. **Early** — if the URL is an arXiv link and we already have that paper,
       return the existing row without downloading. Saves bandwidth + an LLM
       round-trip on repeat imports.
    2. **Late** — after download, hash the file; if the SHA-256 matches an
       existing paper, delete the just-downloaded file and return the existing
       row. Catches cases where the same paper was imported via different URLs
       (abs vs pdf, mirrors, etc.).
    """
    settings = get_settings()

    arxiv_id = url_ingest.parse_arxiv_url(url)
    log.info("Importing URL %s (arxiv_id=%s)", url, arxiv_id)

    # Step 1: early dedup by arxiv id
    if arxiv_id:
        existing = find_existing_by_arxiv_id(session, arxiv_id)
        if existing is not None:
            log.info(
                "URL already indexed as paper id=%s (arxiv_id=%s), skipping download",
                existing.id,
                arxiv_id,
            )
            return existing

    # Step 2: download. For arXiv links, canonicalise to /pdf/{id}.pdf so we
    # don't fetch the HTML abstract page.
    fetch_url = url_ingest.to_arxiv_pdf_url(arxiv_id) if arxiv_id else url
    pdf_path = url_ingest.download_pdf(
        fetch_url, dest_dir=settings.papers_dir, arxiv_id=arxiv_id
    )

    # Step 3: parse + late dedup by content hash
    parsed = pdf_parser.parse_pdf(pdf_path, thumbnails_dir=settings.thumbnails_dir)
    existing = find_existing_by_hash(session, parsed.content_hash)
    if existing is not None:
        log.info(
            "Downloaded file matched existing paper id=%s by hash; removing %s",
            existing.id,
            pdf_path.name,
        )
        # Keep the indexed copy if it still exists; drop the dup.
        if existing.pdf_path and Path(existing.pdf_path).resolve() != pdf_path.resolve():
            pdf_path.unlink(missing_ok=True)
        return existing

    source = "arxiv" if arxiv_id else "url"
    return _finish_paper(
        session, pdf_path, parsed, source=source, arxiv_id_hint=arxiv_id
    )


def scan_local_directory(session: Session, *, directory: Path | None = None) -> list[Paper]:
    """Process every PDF under ``directory`` that is not already indexed.

    Defaults to ``settings.papers_dir``.
    """
    settings = get_settings()
    directory = directory or settings.papers_dir

    if not directory.exists():
        log.warning("Papers directory does not exist: %s", directory)
        return []

    results: list[Paper] = []
    for pdf_path in sorted(directory.glob("*.pdf")):
        try:
            paper = process_local_pdf(session, pdf_path)
            results.append(paper)
        except Exception:
            log.exception("Failed to process %s", pdf_path)
    return results
