"""Papers REST API: list, detail, scan trigger, file serving."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import engine, get_session
from app.models import Paper, PaperStatus
from app.pipeline import (
    find_existing_by_arxiv_id,
    process_url,
    resummarize_paper,
    scan_local_directory,
)
from app.services import url_ingest

log = logging.getLogger(__name__)

router = APIRouter(prefix="/papers", tags=["papers"])


# --- Response models --------------------------------------------------------


class PaperListItem(BaseModel):
    """Slim projection used by the poster wall grid."""

    id: int
    title: str
    authors: str
    score: float
    status: PaperStatus
    source: str
    tags: list[str]
    has_thumbnail: bool

    @classmethod
    def from_orm_paper(cls, p: Paper) -> "PaperListItem":
        tags: list[str] = []
        if p.tags:
            try:
                tags = json.loads(p.tags)
            except json.JSONDecodeError:
                tags = []
        return cls(
            id=p.id or 0,
            title=p.title,
            authors=p.authors,
            score=p.score,
            status=p.status,
            source=p.source,
            tags=tags,
            has_thumbnail=bool(p.thumbnail_path),
        )


class PaperDetail(BaseModel):
    """Full paper detail for the detail page."""

    id: int
    title: str
    authors: str
    abstract: str
    venue: str | None
    arxiv_id: str | None
    doi: str | None
    summary_contribution: str
    summary_method: str
    summary_result: str
    tags: list[str]
    score: float
    score_affiliation: float
    score_author_fame: float
    score_venue: float
    score_llm: float
    source: str
    status: PaperStatus
    error: str | None
    has_pdf: bool
    has_thumbnail: bool

    @classmethod
    def from_orm_paper(cls, p: Paper) -> "PaperDetail":
        tags: list[str] = []
        if p.tags:
            try:
                tags = json.loads(p.tags)
            except json.JSONDecodeError:
                tags = []
        return cls(
            id=p.id or 0,
            title=p.title,
            authors=p.authors,
            abstract=p.abstract,
            venue=p.venue,
            arxiv_id=p.arxiv_id,
            doi=p.doi,
            summary_contribution=p.summary_contribution,
            summary_method=p.summary_method,
            summary_result=p.summary_result,
            tags=tags,
            score=p.score,
            score_affiliation=p.score_affiliation,
            score_author_fame=p.score_author_fame,
            score_venue=p.score_venue,
            score_llm=p.score_llm,
            source=p.source,
            status=p.status,
            error=p.error,
            has_pdf=bool(p.pdf_path) and Path(p.pdf_path).exists() if p.pdf_path else False,
            has_thumbnail=bool(p.thumbnail_path)
            and Path(p.thumbnail_path).exists() if p.thumbnail_path else False,
        )


class ScanResponse(BaseModel):
    queued: int


# --- Endpoints --------------------------------------------------------------


SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[PaperListItem])
def list_papers(
    session: SessionDep,
    min_score: float = Query(0.0, ge=0, le=100),
    source: str | None = Query(None),
    status_filter: PaperStatus | None = Query(None, alias="status"),
    sort: str = Query("recent", pattern="^(recent|score|title)$"),
    limit: int = Query(200, ge=1, le=1000),
) -> list[PaperListItem]:
    """List papers for the poster wall, with simple filters."""
    stmt = select(Paper).where(Paper.score >= min_score)
    if source:
        stmt = stmt.where(Paper.source == source)
    if status_filter:
        stmt = stmt.where(Paper.status == status_filter)
    else:
        # Hide rejected / failed by default – the wall should only show readable papers.
        stmt = stmt.where(Paper.status == PaperStatus.READY)

    if sort == "score":
        stmt = stmt.order_by(Paper.score.desc())
    elif sort == "title":
        stmt = stmt.order_by(Paper.title.asc())
    else:
        stmt = stmt.order_by(Paper.created_at.desc())

    stmt = stmt.limit(limit)
    papers = session.exec(stmt).all()
    return [PaperListItem.from_orm_paper(p) for p in papers]


@router.get("/{paper_id}", response_model=PaperDetail)
def get_paper(paper_id: int, session: SessionDep) -> PaperDetail:
    paper = session.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return PaperDetail.from_orm_paper(paper)


@router.get("/{paper_id}/pdf")
def get_paper_pdf(paper_id: int, session: SessionDep) -> FileResponse:
    paper = session.get(Paper, paper_id)
    if not paper or not paper.pdf_path or not Path(paper.pdf_path).exists():
        raise HTTPException(status_code=404, detail="PDF not available")
    # NOTE: deliberately NOT passing `filename=` — FastAPI would then set
    # `Content-Disposition: attachment; filename=...`, which forces browsers to
    # download the file instead of rendering it inline. Setting the header
    # ourselves with `inline` keeps it viewable in an <iframe>. The filename
    # hint still applies if the user hits Save.
    import re as _re
    safe_title = _re.sub(r'[^\w\-. ]+', "_", paper.title)[:120] or f"paper-{paper.id}"
    return FileResponse(
        paper.pdf_path,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{safe_title}.pdf"',
            # Cache for an hour — PDFs are immutable once ingested, so this
            # lets the iframe redraw instantly on back/forward navigation.
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.get("/{paper_id}/thumbnail")
def get_paper_thumbnail(paper_id: int, session: SessionDep) -> FileResponse:
    paper = session.get(Paper, paper_id)
    if not paper or not paper.thumbnail_path or not Path(paper.thumbnail_path).exists():
        raise HTTPException(status_code=404, detail="Thumbnail not available")
    return FileResponse(paper.thumbnail_path, media_type="image/jpeg")


@router.delete("/{paper_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_paper(paper_id: int, session: SessionDep) -> None:
    paper = session.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    session.delete(paper)
    session.commit()


class ResummarizeResponse(BaseModel):
    paper_id: int
    status: str  # "queued"


def _run_resummarize_background(paper_id: int) -> None:
    """Re-run the summarizer on one paper. Opens its own session."""
    try:
        with Session(engine) as bg_session:
            paper = bg_session.get(Paper, paper_id)
            if not paper:
                log.warning("Resummarize: paper id=%s disappeared", paper_id)
                return
            resummarize_paper(bg_session, paper)
    except Exception:
        log.exception("Background resummarize failed for paper id=%s", paper_id)


@router.post("/{paper_id}/resummarize", response_model=ResummarizeResponse)
def trigger_resummarize(
    paper_id: int,
    background_tasks: BackgroundTasks,
    session: SessionDep,
) -> ResummarizeResponse:
    """Queue a re-run of the summarizer for one paper.

    The summary prompt has a language setting, so this is how users refresh
    existing papers after the backend's target language changes (or if a
    previous summary came out poorly).
    """
    paper = session.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    if not paper.pdf_path or not Path(paper.pdf_path).exists():
        raise HTTPException(
            status_code=409,
            detail="PDF file for this paper is no longer on disk",
        )
    background_tasks.add_task(_run_resummarize_background, paper_id)
    return ResummarizeResponse(paper_id=paper_id, status="queued")


def _run_scan_background() -> None:
    """BackgroundTasks callback: open its own session (request session is closed by then)."""
    try:
        with Session(engine) as bg_session:
            papers = scan_local_directory(bg_session)
            log.info("Background scan finished: %d papers touched", len(papers))
    except Exception:
        log.exception("Background scan failed")


@router.post("/scan", response_model=ScanResponse)
def trigger_scan(
    background_tasks: BackgroundTasks,
    session: SessionDep,
) -> ScanResponse:
    """Queue a background scan of ``data/papers/``.

    Returns the number of PDFs that will be examined. Processing happens async.
    """
    from app.config import get_settings  # local import to avoid cycles at import time
    settings = get_settings()
    pdf_count = (
        len(list(settings.papers_dir.glob("*.pdf"))) if settings.papers_dir.exists() else 0
    )
    background_tasks.add_task(_run_scan_background)
    return ScanResponse(queued=pdf_count)


# --- URL import -------------------------------------------------------------


class ImportUrlRequest(BaseModel):
    url: str


class ImportUrlResponse(BaseModel):
    """Outcome of a URL import request.

    ``status`` values:

    * ``queued``         — accepted; background task will process it
    * ``deduplicated``   — we already have this paper; ``paper_id`` is set
    * ``failed``         — synchronous rejection (bad URL etc.)
    """

    paper_id: int | None
    status: str
    message: str


def _run_import_background(url: str) -> None:
    """BackgroundTasks callback: download + parse + LLM + persist."""
    try:
        with Session(engine) as bg_session:
            paper = process_url(bg_session, url)
            log.info(
                "Background import finished: url=%s paper_id=%s status=%s",
                url,
                paper.id,
                paper.status,
            )
    except Exception:
        log.exception("Background import failed for %s", url)


@router.post("/import-url", response_model=ImportUrlResponse)
def import_url(
    body: ImportUrlRequest,
    background_tasks: BackgroundTasks,
    session: SessionDep,
) -> ImportUrlResponse:
    """Import a paper by URL (arXiv link or direct PDF URL).

    The download + LLM steps run in a background task. This endpoint returns
    immediately with either ``queued`` or ``deduplicated``. Hard input errors
    (empty / non-http / malformed URL) produce a 400.
    """
    # 1. Cheap URL sanity check: reject obviously bad input synchronously so
    #    the client gets immediate feedback instead of a delayed background
    #    failure it would have to poll for.
    raw_url = (body.url or "").strip()
    if not raw_url:
        raise HTTPException(status_code=400, detail="URL is empty")
    if not raw_url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=400,
            detail="Only http(s) URLs are supported",
        )

    # 2. Early dedup: arXiv URLs let us check without downloading.
    arxiv_id = url_ingest.parse_arxiv_url(raw_url)
    if arxiv_id:
        existing = find_existing_by_arxiv_id(session, arxiv_id)
        if existing is not None:
            return ImportUrlResponse(
                paper_id=existing.id,
                status="deduplicated",
                message=f"Already indexed as '{existing.title}' (paper id {existing.id}).",
            )

    # 3. Fire-and-forget background job.
    background_tasks.add_task(_run_import_background, raw_url)
    return ImportUrlResponse(
        paper_id=None,
        status="queued",
        message=(
            "Download and processing queued. The paper will appear in the library "
            "once the LLM finishes (usually 20–40 seconds)."
        ),
    )
