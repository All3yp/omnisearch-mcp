"""arXiv source adapter — uses the public Atom-based query API.

Docs: https://info.arxiv.org/help/api/user-manual.html
No API key required; please be polite (<= 1 request per ~3 seconds).
"""
from __future__ import annotations

import asyncio
import logging
import re
import xml.etree.ElementTree as ET

import httpx

from ..config import get_config
from ..models import Paper

log = logging.getLogger("omnisearch_mcp")

# Retry config for 429 / 503 rate-limit responses
_MAX_RETRIES = 2
_RETRY_BACKOFF = 3.0  # seconds; arXiv asks for <=1 req/3s

API_URL = "https://export.arxiv.org/api/query"
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


def _text(elem: ET.Element | None) -> str | None:
    if elem is None or elem.text is None:
        return None
    return re.sub(r"\s+", " ", elem.text).strip() or None


def parse_arxiv_atom(xml_text: str) -> list[Paper]:
    root = ET.fromstring(xml_text)
    papers: list[Paper] = []
    for entry in root.findall("atom:entry", NS):
        title = _text(entry.find("atom:title", NS)) or ""
        summary = _text(entry.find("atom:summary", NS))
        published = _text(entry.find("atom:published", NS))
        year = int(published[:4]) if published and published[:4].isdigit() else None

        authors = [
            _text(a.find("atom:name", NS)) or ""
            for a in entry.findall("atom:author", NS)
        ]
        authors = [a for a in authors if a]

        url = None
        pdf_url = None
        for link in entry.findall("atom:link", NS):
            href = link.get("href")
            if not href:
                continue
            if link.get("title") == "pdf" or href.endswith(".pdf"):
                pdf_url = href
            elif link.get("rel") == "alternate":
                url = href

        doi = _text(entry.find("arxiv:doi", NS))
        arxiv_id_full = _text(entry.find("atom:id", NS)) or ""
        arxiv_id = arxiv_id_full.rsplit("/", 1)[-1]

        venue = _text(entry.find("arxiv:journal_ref", NS))

        papers.append(
            Paper(
                source="arxiv",
                title=title,
                authors=authors,
                year=year,
                venue=venue,
                doi=doi,
                url=url,
                pdf_url=pdf_url,
                abstract=summary,
                identifiers={"arxiv": arxiv_id} if arxiv_id else {},
            )
        )
    return papers


async def search_arxiv(query: str, max_results: int = 10) -> list[Paper]:
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": max(1, min(max_results, 50)),
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    cfg = get_config()
    async with httpx.AsyncClient(
        timeout=30.0, headers={"User-Agent": cfg.user_agent}
    ) as client:
        for attempt in range(_MAX_RETRIES + 1):
            resp = await client.get(API_URL, params=params)
            if resp.status_code in (429, 503) and attempt < _MAX_RETRIES:
                wait = _RETRY_BACKOFF * (2 ** attempt)
                log.warning("arxiv: %d rate-limited, retrying in %.1fs (attempt %d/%d)", resp.status_code, wait, attempt + 1, _MAX_RETRIES)
                await asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            return parse_arxiv_atom(resp.text)
    return []  # unreachable, but satisfies type checker
