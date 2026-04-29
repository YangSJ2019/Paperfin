"""URL ingestion: parse paper URLs and download their PDFs.

Responsibilities:

* Recognise arXiv URLs in their common shapes and return the canonical arxiv_id.
* Stream-download a PDF to disk with safeguards against oversized files,
  non-PDF responses, and network hangs.

Everything here is synchronous and thread-safe — the pipeline runs inside a
FastAPI BackgroundTask, which uses its own session anyway.
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from urllib.parse import urlparse

import httpx

log = logging.getLogger(__name__)

# --- Exceptions -------------------------------------------------------------


class UrlIngestError(RuntimeError):
    """Base class for URL ingestion failures."""


class InvalidUrlError(UrlIngestError):
    """URL is not a well-formed http(s) URL we can handle."""


class NotPdfError(UrlIngestError):
    """Remote resource is not a PDF (missing or wrong Content-Type)."""


class OversizePdfError(UrlIngestError):
    """PDF download exceeded the configured size cap."""


class DownloadFailedError(UrlIngestError):
    """Non-retryable transport error while downloading."""


# --- arXiv URL parsing ------------------------------------------------------

# arXiv IDs come in two shapes:
#   new:    2403.12345       (optionally with v2, v3, …)
#   legacy: cs.LG/0701234    (subject class + 7 digits)
# Surrounding URL path segments the site uses: /abs/{id}, /pdf/{id}, /pdf/{id}.pdf
_ARXIV_URL_RE = re.compile(
    r"""
    ^https?://
    (?:www\.)?arxiv\.org/
    (?:abs|pdf|html)/
    (?P<id>
        (?:\d{4}\.\d{4,5})(?:v\d+)?        # new-style, with optional version
        |
        (?:[a-z-]+(?:\.[A-Z]{2})?/\d{7})   # legacy
    )
    (?:\.pdf)?                              # /pdf/… links end in .pdf
    /?                                      # optional trailing slash
    (?:\?.*)?$                              # tolerate query strings
    """,
    re.IGNORECASE | re.VERBOSE,
)


def parse_arxiv_url(url: str) -> str | None:
    """Return the canonical arXiv id for ``url``, or None if it isn't arXiv.

    Examples:
        https://arxiv.org/abs/2403.12345      -> "2403.12345"
        https://arxiv.org/pdf/2403.12345v2    -> "2403.12345v2"
        https://arxiv.org/pdf/cs.LG/0701234   -> "cs.LG/0701234"
        https://example.com/paper.pdf          -> None
    """
    m = _ARXIV_URL_RE.match(url.strip())
    return m.group("id") if m else None


def to_arxiv_pdf_url(arxiv_id: str) -> str:
    """Build the canonical PDF URL for a given arXiv id."""
    return f"https://arxiv.org/pdf/{arxiv_id}.pdf"


# --- Download ---------------------------------------------------------------

_DEFAULT_MAX_BYTES = 100 * 1024 * 1024  # 100 MB — generous even for thesis-sized PDFs
_DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_USER_AGENT = "Paperfin/0.1 (+https://github.com/; local scraper)"
_CHUNK_SIZE = 1 << 15  # 32 KB


def _validate_url(url: str) -> str:
    """Validate the URL is a plausible http(s) URL; return the stripped form."""
    url = url.strip()
    if not url:
        raise InvalidUrlError("URL is empty")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise InvalidUrlError(f"Only http(s) URLs are supported: got {parsed.scheme!r}")
    if not parsed.netloc:
        raise InvalidUrlError(f"URL has no host: {url!r}")
    return url


def _choose_filename(url: str, arxiv_id: str | None) -> str:
    """Pick a deterministic-ish filename for the download.

    Using the arxiv id when available gives us human-readable filenames;
    otherwise hash the URL so repeated imports of the same URL land on the
    same path (pipeline dedup then handles the content-level check).
    """
    if arxiv_id:
        # arxiv_id may contain "/" (legacy style) — flatten it.
        safe = arxiv_id.replace("/", "_")
        return f"{safe}.pdf"
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return f"url_{digest}.pdf"


def download_pdf(
    url: str,
    dest_dir: Path,
    *,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    arxiv_id: str | None = None,
) -> Path:
    """Download a PDF from ``url`` into ``dest_dir`` and return the local path.

    Streams the response so oversized files abort early. Raises a subclass of
    :class:`UrlIngestError` on any failure; the partial file is removed.
    """
    url = _validate_url(url)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / _choose_filename(url, arxiv_id)

    # If we've already got this exact file on disk from a previous attempt,
    # reuse it — pipeline dedup will decide whether to reprocess.
    if dest_path.exists() and dest_path.stat().st_size > 0:
        log.info("Reusing existing file %s for %s", dest_path.name, url)
        return dest_path

    headers = {"User-Agent": _USER_AGENT, "Accept": "application/pdf,*/*;q=0.8"}

    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=_DEFAULT_TIMEOUT,
            headers=headers,
        ) as client:
            with client.stream("GET", url) as resp:
                if resp.status_code >= 400:
                    raise DownloadFailedError(
                        f"HTTP {resp.status_code} from {resp.request.url}"
                    )

                # Content-Type sanity check. arXiv serves application/pdf;
                # reject HTML pages, landing pages, login walls, etc.
                ctype = resp.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if ctype and not ctype.endswith("/pdf") and "pdf" not in ctype:
                    raise NotPdfError(
                        f"Expected a PDF, got Content-Type {ctype!r} from {resp.request.url}"
                    )

                # Try to enforce size early from Content-Length if present.
                cl = resp.headers.get("content-length")
                if cl and cl.isdigit() and int(cl) > max_bytes:
                    raise OversizePdfError(
                        f"Content-Length {cl} exceeds cap {max_bytes}"
                    )

                written = 0
                with dest_path.open("wb") as fh:
                    for chunk in resp.iter_bytes(_CHUNK_SIZE):
                        if not chunk:
                            continue
                        written += len(chunk)
                        if written > max_bytes:
                            raise OversizePdfError(
                                f"Aborted after {written} bytes (cap {max_bytes})"
                            )
                        fh.write(chunk)

                if written == 0:
                    raise DownloadFailedError("Received an empty response body")

                # Magic-byte check: every PDF starts with %PDF-
                with dest_path.open("rb") as fh:
                    header = fh.read(5)
                if header != b"%PDF-":
                    raise NotPdfError(
                        f"File does not start with %PDF- marker (got {header!r})"
                    )

                log.info("Downloaded %s bytes from %s -> %s", written, url, dest_path.name)
                return dest_path
    except UrlIngestError:
        # Clean up partial file, then re-raise the categorised error.
        dest_path.unlink(missing_ok=True)
        raise
    except httpx.HTTPError as exc:
        dest_path.unlink(missing_ok=True)
        raise DownloadFailedError(f"Download failed: {exc}") from exc
