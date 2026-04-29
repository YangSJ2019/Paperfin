"""PDF parsing helpers: text extraction and cover thumbnail rendering.

We use two libraries in tandem:

* ``pypdf`` – fast, pure-Python text extraction. Good enough for arXiv PDFs.
* ``PyMuPDF`` (``fitz``) – renders the first page to a JPEG thumbnail for the poster wall.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF
from pypdf import PdfReader

log = logging.getLogger(__name__)

# How many pages of text to hand to the LLM. First 3 pages reliably contain the
# title, authors, affiliations, and abstract for any reasonably formatted paper.
MAX_TEXT_PAGES = 3

# Target thumbnail width in pixels. 600px renders crisply on retina grids while
# keeping JPEGs ~50-100 KB.
THUMBNAIL_WIDTH = 600


@dataclass
class ParsedPdf:
    """Result of parsing a single PDF file."""

    text: str
    thumbnail_path: Path | None
    content_hash: str
    page_count: int


def _hash_file(path: Path, chunk_size: int = 1 << 20) -> str:
    """Return a sha256 hex digest of ``path`` without loading it into memory."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def extract_text(pdf_path: Path, max_pages: int = MAX_TEXT_PAGES) -> tuple[str, int]:
    """Extract plain text from the first ``max_pages`` pages.

    Returns ``(text, total_page_count)``.
    """
    reader = PdfReader(str(pdf_path))
    total_pages = len(reader.pages)
    chunks: list[str] = []
    for page in reader.pages[:max_pages]:
        try:
            chunks.append(page.extract_text() or "")
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("pypdf failed on a page of %s: %s", pdf_path.name, exc)
    return "\n".join(chunks).strip(), total_pages


def render_thumbnail(pdf_path: Path, output_path: Path, width: int = THUMBNAIL_WIDTH) -> Path:
    """Render the first page of ``pdf_path`` as a JPEG at ``output_path``."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with fitz.open(pdf_path) as doc:
        if doc.page_count == 0:
            raise ValueError(f"PDF has no pages: {pdf_path}")
        page = doc.load_page(0)
        # Compute zoom so the rendered pixmap matches the desired width.
        zoom = width / page.rect.width
        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        pix.save(str(output_path), jpg_quality=85)
    return output_path


def parse_pdf(pdf_path: Path, thumbnails_dir: Path) -> ParsedPdf:
    """Full parse: text + thumbnail + content hash.

    Thumbnail filename is derived from the content hash so reprocessing the
    same file is idempotent.
    """
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)

    content_hash = _hash_file(pdf_path)
    text, page_count = extract_text(pdf_path)

    thumbnail_path: Path | None = None
    try:
        thumbnail_path = render_thumbnail(
            pdf_path, thumbnails_dir / f"{content_hash}.jpg"
        )
    except Exception as exc:
        log.warning("Thumbnail rendering failed for %s: %s", pdf_path.name, exc)

    return ParsedPdf(
        text=text,
        thumbnail_path=thumbnail_path,
        content_hash=content_hash,
        page_count=page_count,
    )
