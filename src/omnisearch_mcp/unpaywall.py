"""Unpaywall API client for resolving open-access PDF URLs."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from .config import get_config

log = logging.getLogger("omnisearch_mcp")

UNPAYWALL_API_URL = "https://api.unpaywall.org/v2"
USER_AGENT = "omnisearch-mcp/0.1 (https://github.com/all3yp/omnisearch-mcp)"


class UnpaywallResolver:
    """Resolve open-access PDF URLs using the Unpaywall API."""

    def __init__(self) -> None:
        cfg = get_config()
        self.email = cfg.contact_email

    def has_api_access(self) -> bool:
        """Check if Unpaywall API is accessible (requires email)."""
        return bool(self.email)

    def resolve_best_pdf_url(self, doi: str) -> str | None:
        """Find the best open-access PDF URL for a DOI.

        Args:
            doi: DOI string.

        Returns:
            Best PDF URL or None if not available.
        """
        if not self.has_api_access() or not doi:
            return None

        try:
            record = self._fetch_doi_record(doi)
            if not record:
                return None

            # Try best_oa_location first
            best_location = record.get("best_oa_location") or {}
            best_pdf = best_location.get("url_for_pdf") or best_location.get("url")
            if best_pdf:
                return best_pdf

            # Fallback to any oa_location
            for location in record.get("oa_locations", []) or []:
                candidate = location.get("url_for_pdf") or location.get("url")
                if candidate:
                    return candidate

        except Exception as exc:
            log.warning("Unpaywall resolver error for DOI %s: %s", doi, exc)

        return None

    def _fetch_doi_record(self, doi: str) -> dict[str, Any] | None:
        """Fetch Unpaywall metadata for a DOI.

        Args:
            doi: DOI string.

        Returns:
            Unpaywall record or None on failure.
        """
        if not self.email:
            return None

        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.get(
                    f"{UNPAYWALL_API_URL}/{doi}",
                    params={"email": self.email},
                    headers={"User-Agent": USER_AGENT},
                )

            if response.status_code == 404:
                return None

            if response.status_code == 422:
                log.warning("Unpaywall rejected email %s (HTTP 422)", self.email)
                return None

            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as exc:
            log.warning("Unpaywall request failed for DOI %s: %s", doi, exc)
            return None
