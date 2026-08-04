"""Semantic Scholar API adapter.

Docs: https://api.semanticscholar.org/api-docs/graph
"""
from __future__ import annotations

from typing import Any

import httpx

from ..config import get_config
from ..models import Paper

API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"


def _to_paper(item: dict[str, Any]) -> Paper:
    authors = [a.get("name", "") for a in item.get("authors") or []]
    
    url = item.get("url")
    pdf_url = None
    open_access = item.get("openAccessPdf")
    if open_access:
        pdf_url = open_access.get("url")
        
    external_ids = item.get("externalIds") or {}
    doi = external_ids.get("DOI")

    return Paper(
        source="semantic_scholar",
        title=(item.get("title") or "").strip(),
        authors=authors,
        year=item.get("year"),
        venue=item.get("venue"),
        doi=doi,
        url=url,
        pdf_url=pdf_url,
        abstract=item.get("abstract"),
        identifiers={k: str(v) for k, v in external_ids.items() if v},
    )


async def search_semantic_scholar(query: str, max_results: int = 10) -> list[Paper]:
    config = get_config()
    headers = {"User-Agent": config.user_agent}
    if config.semantic_scholar_api_key:
        headers["x-api-key"] = config.semantic_scholar_api_key
        
    params = {
        "query": query,
        "limit": max(1, min(max_results, 100)),
        "fields": "title,authors,year,venue,abstract,url,openAccessPdf,externalIds",
    }
    
    async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
        resp = await client.get(API_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
        return [_to_paper(item) for item in (data.get("data") or [])]
