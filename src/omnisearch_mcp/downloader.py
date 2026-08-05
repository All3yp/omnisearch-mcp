"""PDF downloader with fallback chain."""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path

import httpx

from .scihub import SciHubFetcher
from .sources.core import CoreKeyMissingError, search_core
from .unpaywall import UnpaywallResolver

log = logging.getLogger("omnisearch_mcp")

DOWNLOAD_TIMEOUT = 30.0
PDF_SIGNATURE = b"%PDF"
MAX_FILENAME_LENGTH = 120


def safe_filename(filename_hint: str, default: str = "paper") -> str:
    """Create a filesystem-safe filename.

    Args:
        filename_hint: Suggested filename.
        default: Fallback if hint is empty.

    Returns:
        Sanitized filename string.
    """
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", filename_hint).strip("._")
    if not safe:
        return default
    return safe[:MAX_FILENAME_LENGTH]


def is_pdf_content(content: bytes, content_type: str, url: str) -> bool:
    """Verify if content is a PDF by signature, type, or URL.

    Args:
        content: Response body bytes.
        content_type: HTTP Content-Type header.
        url: Original URL.

    Returns:
        True if content appears to be a PDF.
    """
    type_lower = (content_type or "").lower()
    return (
        "pdf" in type_lower
        or content.startswith(PDF_SIGNATURE)
        or url.lower().endswith(".pdf")
    )


async def download_from_url(
    pdf_url: str,
    save_path: str,
    filename_hint: str = "paper",
) -> str | None:
    """Download a PDF from a URL.

    Args:
        pdf_url: URL to download.
        save_path: Directory to save file.
        filename_hint: Suggested filename.

    Returns:
        Path to saved file or None on failure.
    """
    if not pdf_url:
        return None

    os.makedirs(save_path, exist_ok=True)
    output_name = f"{safe_filename(filename_hint)}.pdf"
    output_path = os.path.join(save_path, output_name)

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=DOWNLOAD_TIMEOUT,
        ) as client:
            response = await client.get(pdf_url)

        if response.status_code >= 400 or not response.content:
            return None

        content_type = response.headers.get("content-type", "")
        if not is_pdf_content(response.content, content_type, pdf_url):
            log.warning("URL is not a PDF: %s (content-type=%s)", pdf_url, content_type)
            return None

        Path(output_path).write_bytes(response.content)
        return output_path

    except Exception as exc:
        log.warning("Download failed for %s: %s", pdf_url, exc)
        return None


async def try_core_repository_fallback(
    doi: str,
    title: str,
    save_path: str,
    filename_hint: str,
) -> tuple[str | None, str | None]:
    """Try CORE repository search as an open-access PDF fallback."""
    queries = [value for value in (doi, title) if value]
    for query in queries:
        try:
            papers = await search_core(query, max_results=3)
        except CoreKeyMissingError:
            return None, "CORE_API_KEY is not set"
        except Exception as exc:
            log.warning("CORE repository fallback failed for %s: %s", query, exc)
            continue

        for paper in papers:
            if not paper.pdf_url:
                continue
            downloaded = await download_from_url(paper.pdf_url, save_path, filename_hint)
            if downloaded:
                return downloaded, None

    return None, "No CORE repository PDF found"


async def download_with_fallback(
    doi: str,
    title: str,
    pdf_url: str | None,
    save_path: str,
    use_scihub: bool = False,
) -> tuple[str | None, str, str | None]:
    """Download PDF with fallback chain: direct URL → Unpaywall → CORE → Sci-Hub.

    Returns:
        Tuple of (file_path or None, source, error_message or None).
    """
    filename_hint = title or doi or "paper"

    if pdf_url:
        downloaded = await download_from_url(pdf_url, save_path, filename_hint)
        if downloaded:
            return downloaded, "direct", None

    resolver = UnpaywallResolver()
    if resolver.has_api_access() and doi:
        unpaywall_url = resolver.resolve_best_pdf_url(doi)
        if unpaywall_url:
            downloaded = await download_from_url(unpaywall_url, save_path, filename_hint)
            if downloaded:
                return downloaded, "unpaywall", None

    repository_path, repository_error = await try_core_repository_fallback(
        doi, title, save_path, filename_hint
    )
    if repository_path:
        return repository_path, "core", None

    if use_scihub and doi:
        log.warning("Attempting Sci-Hub fallback for DOI %s (use responsibly)", doi)
        scihub = SciHubFetcher()
        scihub_url = await scihub.fetch_pdf_url(doi)
        if scihub_url:
            downloaded = await download_from_url(scihub_url, save_path, filename_hint)
            if downloaded:
                return downloaded, "scihub", None

    return None, "none", repository_error or "No PDF URL available or download failed"
