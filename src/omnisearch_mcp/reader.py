"""Paper reader: download and extract text from academic papers."""
from __future__ import annotations

import logging
from pathlib import Path

from typing import Any

from .downloader import download_with_fallback, safe_filename
from .pdfs.library import read_pdf

log = logging.getLogger("omnisearch_mcp")

DEFAULT_MAX_CHARS = 50000


async def read_paper(
    doi: str,
    title: str = "",
    pdf_url: str | None = None,
    save_path: str = "./downloads",
    max_chars: int = DEFAULT_MAX_CHARS,
    use_scihub: bool = False,
) -> dict[str, Any]:
    """Download a paper and extract its text content.

    Args:
        doi: Paper DOI.
        title: Paper title (used for filename and display).
        pdf_url: Known PDF URL (optional, will use fallback chain if None).
        save_path: Directory to save PDF (default: ./downloads).
        max_chars: Maximum characters to extract (default: 50000).
        use_scihub: If True, use Sci-Hub as last resort (default: False).

    Returns:
        Dictionary with:
        - path: Path to saved PDF
        - title: Paper title
        - pages: Number of pages
        - characters: Total characters extracted
        - text: Extracted text content
        - source: How PDF was obtained (direct/unpaywall/scihub/cached)
        - error: Error message if failed
    """
    # Check if paper already downloaded
    filename_hint = title or doi or "paper"
    expected_path = Path(save_path) / f"{safe_filename(filename_hint)}.pdf"

    if expected_path.exists():
        log.info("Using cached PDF: %s", expected_path)
        try:
            result = read_pdf(str(expected_path), max_chars=max_chars)
        except Exception as exc:
            log.error("Failed to extract text from cached PDF %s: %s", expected_path, exc)
            return {
                "path": str(expected_path),
                "title": title,
                "pages": 0,
                "characters": 0,
                "text": "",
                "source": "cached",
                "error": f"PDF cached but text extraction failed: {exc}",
            }
        return {
            "path": str(expected_path),
            "title": result.get("title") or title,
            "pages": result.get("pages", 0),
            "characters": result.get("characters", 0),
            "text": result.get("text", ""),
            "source": "cached",
            "error": None,
        }

    # Download with fallback chain
    pdf_path, source, error_msg = await download_with_fallback(
        doi, title, pdf_url, save_path, use_scihub
    )

    if not pdf_path:
        return {
            "path": None,
            "title": title,
            "pages": 0,
            "characters": 0,
            "text": "",
            "source": None,
            "error": error_msg or "Download failed",
        }

    # Extract text from downloaded PDF
    try:
        result = read_pdf(pdf_path, max_chars=max_chars)
        return {
            "path": pdf_path,
            "title": result.get("title") or title,
            "pages": result.get("pages", 0),
            "characters": result.get("characters", 0),
            "text": result.get("text", ""),
            "source": source,
            "error": None,
        }
    except Exception as exc:
        log.error("Failed to extract text from %s: %s", pdf_path, exc)
        return {
            "path": pdf_path,
            "title": title,
            "pages": 0,
            "characters": 0,
            "text": "",
            "source": source,
            "error": f"PDF downloaded but text extraction failed: {exc}",
        }
