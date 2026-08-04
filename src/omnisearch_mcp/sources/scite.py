"""Scite.ai API adapter using Web API and cookies."""
from __future__ import annotations

from typing import Any

import httpx

from .. import config
from ..models import Paper

# Note: This uses Scite's internal API which might change. 
# Typical structure for their search endpoint:
API_URL = "https://scite.ai/api/search/papers"


class SciteAuthMissingError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            "SCITE_COOKIES is not set or expired. Please run `uv run omnisearch-scite-login` to authenticate "
            "e capturar os cookies logados."
        )


def _to_paper(item: dict[str, Any]) -> Paper:
    # Handles both list of dicts or list of strings for authors
    authors_raw = item.get("authors") or []
    authors = []
    for a in authors_raw:
        if isinstance(a, str):
            authors.append(a)
        elif isinstance(a, dict):
            authors.append(a.get("name", ""))

    return Paper(
        source="scite",
        title=(item.get("title") or "").strip(),
        authors=authors,
        year=item.get("year"),
        venue=item.get("journal") or item.get("venue"),
        doi=item.get("doi"),
        url=f"https://scite.ai/reports/{item.get('doi')}" if item.get('doi') else None,
        pdf_url=None,
        abstract=item.get("abstract"),
        identifiers={"scite_id": str(item.get("id"))} if item.get("id") else {},
    )


async def search_scite(query: str, max_results: int = 10) -> list[Paper]:
    cfg = config.get_config()
    if not cfg.scite_cookies:
        raise SciteAuthMissingError()

    headers = {
        "User-Agent": cfg.user_agent,
        "Accept": "application/json",
        "Cookie": cfg.scite_cookies,
    }

    params = {
        "q": query,
        "size": max(1, min(max_results, 50)),
    }

    async with httpx.AsyncClient(timeout=30.0, headers=headers, follow_redirects=True) as client:
        resp = await client.get(API_URL, params=params)
        if resp.status_code in (301, 302, 401, 403) or "login" in str(resp.url).lower() or "sign-in" in str(resp.url).lower():
            raise SciteAuthMissingError()
        resp.raise_for_status()
        try:
            data = resp.json()
        except json.JSONDecodeError:
            raise SciteAuthMissingError("SCITE_COOKIES is expired or invalid. Received HTML response instead of JSON. Please run 'uv run omnisearch-scite-login' to authenticate.")
        
        results = data.get("hits", {}).get("hits", []) if "hits" in data else data.get("papers", [])
        # Extract internal document representations depending on scite API response shape
        papers = []
        for r in results:
            item = r.get("_source", r)
            papers.append(_to_paper(item))
            
        return papers
