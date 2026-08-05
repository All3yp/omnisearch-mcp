"""Semantic Scholar API adapter.

Docs: https://api.semanticscholar.org/api-docs/graph
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from ..config import get_config
from ..models import Paper

log = logging.getLogger("omnisearch_mcp")

API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"

# Retry config for 429 rate-limit responses
_MAX_RETRIES = 3
_RETRY_BACKOFF = 2.0  # seconds; doubles each attempt


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
    cfg = get_config()
    headers = {"User-Agent": cfg.user_agent}
    if cfg.semantic_scholar_api_key:
        headers["x-api-key"] = cfg.semantic_scholar_api_key

    params = {
        "query": query,
        "limit": max(1, min(max_results, 100)),
        "fields": "title,authors,year,venue,abstract,url,openAccessPdf,externalIds",
    }

    async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
        for attempt in range(_MAX_RETRIES + 1):
            resp = await client.get(API_URL, params=params)
            if resp.status_code == 429 and attempt < _MAX_RETRIES:
                wait = _RETRY_BACKOFF * (2 ** attempt)
                log.warning("semantic_scholar: 429 rate-limited, retrying in %.1fs (attempt %d/%d)", wait, attempt + 1, _MAX_RETRIES)
                await asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            return [_to_paper(item) for item in (data.get("data") or [])]
    return []  # unreachable, but satisfies type checker
