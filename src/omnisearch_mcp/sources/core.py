"""CORE API adapter.

Docs: https://core.ac.uk/services/api/
"""
from __future__ import annotations

from typing import Any

import httpx

from .. import config
from ..models import Paper

API_URL = "https://api.core.ac.uk/v3/search/works"

class CoreKeyMissingError(RuntimeError):
    """Raised when the CORE API key is not configured."""

    def __init__(self) -> None:
        super().__init__(
            "CORE_API_KEY is not set. Get a free key at https://core.ac.uk/ "
            "and add it to your .env to enable CORE search."
        )


def _to_paper(item: dict[str, Any]) -> Paper:
    authors = [a.get("name", "") for a in item.get("authors") or []]

    year_raw = item.get("publishedDate") or item.get("year")
    year = None
    if isinstance(year_raw, int):
        year = year_raw
    elif isinstance(year_raw, str) and year_raw:
        try:
            year = int(year_raw[:4])
        except ValueError:
            pass

    urls = item.get("sourceFulltextUrls") or []
    url = item.get("downloadUrl") or (urls[0] if urls else None)

    return Paper(
        source="core",
        title=(item.get("title") or "").strip(),
        authors=authors,
        year=year,
        venue=item.get("publisher"),
        doi=item.get("doi"),
        url=url,
        pdf_url=item.get("downloadUrl"),
        abstract=item.get("abstract"),
        identifiers={
            "oai": item.get("oai"),
            "coreId": str(item.get("id")),
        },
    )


async def search_core(query: str, max_results: int = 10) -> list[Paper]:
    cfg = config.get_config()
    if not cfg.core_api_key:
        raise CoreKeyMissingError()

    headers = {
        "User-Agent": cfg.user_agent,
        "Authorization": f"Bearer {cfg.core_api_key}"
    }

    params = {
        "q": query,
        "limit": max(1, min(max_results, 100)),
    }

    async with httpx.AsyncClient(timeout=30.0, headers=headers, follow_redirects=True) as client:
        resp = await client.get(API_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
        return [_to_paper(item) for item in (data.get("results") or [])]
