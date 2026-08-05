"""Sci-Hub PDF fetcher (last-resort fallback for paywalled papers).

WARNING: Sci-Hub operates in a legal gray area in many jurisdictions.
Use this only for papers you have legitimate access to (e.g., your own
papers, open-access works, or with institutional permission).
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

import httpx

log = logging.getLogger("omnisearch_mcp")


SCIHUB_BASE_URL = "https://sci-hub.se"
SCIHUB_TIMEOUT = 30.0

# Regex patterns for extracting PDF URLs from Sci-Hub HTML
PDF_PATTERNS = [
    re.compile(r'<iframe[^>]+src="([^"]+\.pdf[^"]*)"', re.IGNORECASE),
    re.compile(r'<embed[^>]+src="([^"]+\.pdf[^"]*)"', re.IGNORECASE),
    re.compile(r'<a[^>]+href="([^"]+\.pdf[^"]*)"', re.IGNORECASE),
    re.compile(r"location\.href\s*=\s*'([^']+\.pdf[^']*)'", re.IGNORECASE),
]


class SciHubFetcher:
    """Fetch PDFs from Sci-Hub (last-resort fallback).

    WARNING: Legal status varies by jurisdiction. Use responsibly.
    """

    def __init__(self, base_url: str = SCIHUB_BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")

    def has_access(self) -> bool:
        """Check if Sci-Hub is accessible."""
        return True  # Public service, no API key needed

    async def fetch_pdf_url(self, doi: str) -> str | None:
        """Resolve PDF URL from Sci-Hub for a given DOI.

        Args:
            doi: Paper DOI.

        Returns:
            PDF URL or None if not found.
        """
        if not doi:
            return None

        scihub_url = f"{self.base_url}/{doi}"

        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=SCIHUB_TIMEOUT,
                headers={"User-Agent": "Mozilla/5.0 (compatible; academic research)"},
            ) as client:
                response = await client.get(scihub_url)

            if response.status_code >= 400:
                log.warning("Sci-Hub returned %d for DOI %s", response.status_code, doi)
                return None

            # Check if response is already a PDF
            content_type = response.headers.get("content-type", "")
            if "pdf" in content_type.lower():
                return scihub_url

            # Parse HTML to find PDF URL
            html = response.text
            pdf_url = self._extract_pdf_url(html)

            if pdf_url:
                # Make absolute URL if relative
                if pdf_url.startswith("/"):
                    pdf_url = urljoin(self.base_url, pdf_url)
                elif not pdf_url.startswith("http"):
                    pdf_url = urljoin(scihub_url, pdf_url)

                log.info("Sci-Hub resolved PDF for DOI %s: %s", doi, pdf_url)
                return pdf_url

            log.warning("Sci-Hub: no PDF URL found in HTML for DOI %s", doi)
            return None

        except Exception as exc:
            log.warning("Sci-Hub fetch failed for DOI %s: %s", doi, exc)
            return None

    def _extract_pdf_url(self, html: str) -> str | None:
        """Extract PDF URL from Sci-Hub HTML response.

        Args:
            html: HTML content from Sci-Hub.

        Returns:
            PDF URL or None.
        """
        for pattern in PDF_PATTERNS:
            match = pattern.search(html)
            if match:
                return match.group(1)
        return None


async def verify_pdf_url(url: str) -> bool:
    """Verify that a URL points to a valid PDF.

    Args:
        url: URL to verify.

    Returns:
        True if URL is a valid PDF.
    """
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=10.0,
        ) as client:
            response = await client.head(url)

        if response.status_code >= 400:
            return False

        content_type = response.headers.get("content-type", "")
        return "pdf" in content_type.lower()

    except Exception:
        return False
