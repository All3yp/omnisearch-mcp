"""CrossRef adapter — also used to search ACM Digital Library metadata.

Docs: https://api.crossref.org/swagger-ui/index.html
No API key required, but a polite User-Agent with contact email is expected.
ACM's CrossRef member ID is 320.
"""
from __future__ import annotations

import re
from typing import Any

import httpx

from ..config import CONFIG
from ..models import Paper

API_URL = "https://api.crossref.org/works"
ACM_MEMBER_ID = "320"


def _join_authors(items: list[dict[str, Any]] | None) -> list[str]:
    if not items:
        return []
    out: list[str] = []
    for a in items:
        given = a.get("given", "")
        family = a.get("family", "")
        name = (a.get("name") or f"{given} {family}").strip()
        if name:
            out.append(name)
    return out


def _year_from(item: dict[str, Any]) -> int | None:
    for key in ("published-print", "published-online", "issued", "created"):
        parts = (item.get(key) or {}).get("date-parts") or []
        if parts and parts[0] and isinstance(parts[0][0], int):
            return parts[0][0]
    return None


def _to_paper(item: dict[str, Any], source: str) -> Paper:
    title_list = item.get("title") or []
    container = item.get("container-title") or []
    abstract = item.get("abstract")
    if abstract:
        abstract = re.sub(r"<[^>]+>", "", abstract).strip()

    return Paper(
        source=source,
        title=(title_list[0] if title_list else "").strip(),
        authors=_join_authors(item.get("author")),
        year=_year_from(item),
        venue=(container[0] if container else None),
        doi=item.get("DOI"),
        url=item.get("URL"),
        abstract=abstract,
        identifiers={
            k: v
            for k, v in {
                "issn": ",".join(item.get("ISSN") or []) or None,
                "isbn": ",".join(item.get("ISBN") or []) or None,
                "type": item.get("type"),
            }.items()
            if v
        },
    )


async def _query(params: dict[str, Any]) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(
        timeout=30.0, headers={"User-Agent": CONFIG.user_agent}
    ) as client:
        resp = await client.get(API_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
        return (data.get("message") or {}).get("items") or []


async def search_crossref(query: str, max_results: int = 10) -> list[Paper]:
    items = await _query({"query": query, "rows": max(1, min(max_results, 50))})
    return [_to_paper(item, "crossref") for item in items]


async def search_acm(query: str, max_results: int = 10) -> list[Paper]:
    items = await _query(
        {
            "query": query,
            "rows": max(1, min(max_results, 50)),
            "filter": f"member:{ACM_MEMBER_ID}",
        }
    )
    return [_to_paper(item, "acm") for item in items]


async def get_doi_metadata(doi: str) -> Paper | None:
    doi = doi.strip().removeprefix("https://doi.org/").removeprefix("doi:")
    if not doi:
        return None
    url = f"{API_URL}/{doi}"
    async with httpx.AsyncClient(
        timeout=30.0, headers={"User-Agent": CONFIG.user_agent}
    ) as client:
        resp = await client.get(url)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        item = (resp.json().get("message")) or {}
        return _to_paper(item, "crossref")
