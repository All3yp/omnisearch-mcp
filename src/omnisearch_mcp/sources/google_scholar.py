"""Google Scholar search via SerpApi.

Requires SERPAPI_API_KEY from https://serpapi.com/
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx

from ..config import get_config
from ..models import Paper

SERPAPI_URL = "https://serpapi.com/search.json"
SERPAPI_MAX_RESULTS = 20
SERPAPI_RETRY_STATUSES = {429, 500, 502, 503, 504}
SERPAPI_MAX_RETRIES = 3


class SerpApiKeyMissingError(RuntimeError):
    """Raised when SERPAPI_API_KEY is not configured."""

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message
            or "SERPAPI_API_KEY is not set. Get a free key from https://serpapi.com/"
        )


def _extract_year(summary: str | None) -> int | None:
    """Extract publication year from Google Scholar summary string."""
    if not summary:
        return None
    match = re.search(r"\b(19|20)\d{2}\b", summary)
    return int(match.group(0)) if match else None


def _extract_venue(summary: str | None) -> str | None:
    """Extract venue/journal from Google Scholar summary string."""
    if not summary:
        return None
    # Pattern: "Authors - Venue, Year"
    parts = summary.split(" - ", maxsplit=1)
    if len(parts) < 2:
        return None
    venue_year = parts[1]
    # Remove trailing year
    venue = re.sub(r",?\s*(19|20)\d{2}\s*$", "", venue_year).strip()
    return venue or None


def _to_paper(item: dict[str, Any]) -> Paper:
    """Convert SerpApi organic_result to Paper."""
    pub_info = item.get("publication_info") or {}
    summary = pub_info.get("summary")
    
    authors_block = pub_info.get("authors") or []
    authors = [a.get("name", "") for a in authors_block if a.get("name")]
    
    year = _extract_year(summary)
    venue = _extract_venue(summary)
    
    resources = item.get("resources") or []
    pdf_url = None
    for res in resources:
        if res.get("file_format", "").upper() == "PDF" and res.get("link"):
            pdf_url = res["link"]
            break
    
    result_id = item.get("result_id")
    
    return Paper(
        source="google_scholar",
        title=(item.get("title") or "").strip(),
        authors=authors,
        year=year,
        venue=venue,
        url=item.get("link"),
        abstract=item.get("snippet"),
        pdf_url=pdf_url,
        identifiers={"result_id": result_id} if result_id else {},
    )


async def search_google_scholar(query: str, max_results: int = 10) -> list[Paper]:
    """Search Google Scholar via SerpApi."""
    cfg = get_config()
    
    if not cfg.serpapi_api_key:
        raise SerpApiKeyMissingError()
    
    params = {
        "engine": "google_scholar",
        "q": query,
        "num": str(min(max_results, SERPAPI_MAX_RESULTS)),
        "api_key": cfg.serpapi_api_key,
    }
    
    headers = {"User-Agent": cfg.user_agent}
    
    last_exception = None
    for attempt in range(SERPAPI_MAX_RETRIES):
        try:
            async with httpx.AsyncClient(headers=headers) as client:
                response = await client.get(SERPAPI_URL, params=params)
                
                if response.status_code in SERPAPI_RETRY_STATUSES:
                    if attempt < SERPAPI_MAX_RETRIES - 1:
                        retry_after = response.headers.get("Retry-After")
                        if retry_after and retry_after.isdigit():
                            await asyncio.sleep(int(retry_after))
                        else:
                            await asyncio.sleep(2 ** attempt)
                        continue
                
                response.raise_for_status()
                payload = response.json()
                organic_results = payload.get("organic_results") or []
                return [_to_paper(item) for item in organic_results]
                
        except httpx.HTTPError as exc:
            last_exception = exc
            if attempt < SERPAPI_MAX_RETRIES - 1:
                await asyncio.sleep(2 ** attempt)
                continue
            raise
    
    if last_exception:
        raise last_exception
    
    return []
