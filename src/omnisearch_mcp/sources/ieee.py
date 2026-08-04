"""IEEE Xplore Metadata API adapter.

Docs: https://developer.ieee.org/docs/read/Metadata_API_details

Requires a free API key from https://developer.ieee.org/ (set IEEE_XPLORE_API_KEY).
The key only returns metadata + abstracts; full text still requires an
institutional or personal subscription.
"""
from __future__ import annotations

from typing import Any

import httpx

from .. import config
from ..models import Paper

API_URL = "https://ieeexploreapi.ieee.org/api/v1/search/articles"


class IEEEKeyMissingError(RuntimeError):
    """Raised when neither IEEE_XPLORE_API_KEY nor CAPES_PROXY_URL/IEEE_COOKIES are configured."""

    def __init__(self) -> None:
        super().__init__(
            "IEEE_XPLORE_API_KEY is not set, and no CAPES_PROXY_URL or IEEE_COOKIES "
            "are provided. Please configure one of these to enable IEEE Xplore search."
        )


def _to_paper(item: dict[str, Any]) -> Paper:
    authors_block = (item.get("authors") or {}).get("authors") or []
    authors = [a.get("full_name", "") for a in authors_block if a.get("full_name")]

    year_raw = item.get("publication_year")
    try:
        year = int(year_raw) if year_raw is not None else None
    except (TypeError, ValueError):
        year = None

    article_number = item.get("article_number")
    return Paper(
        source="ieee",
        title=(item.get("title") or "").strip(),
        authors=authors,
        year=year,
        venue=item.get("publication_title"),
        doi=item.get("doi"),
        url=item.get("html_url") or item.get("abstract_url"),
        pdf_url=item.get("pdf_url"),
        abstract=item.get("abstract"),
        identifiers={
            k: str(v)
            for k, v in {
                "article_number": article_number,
                "isbn": item.get("isbn"),
                "issn": item.get("issn"),
                "publisher": item.get("publisher"),
                "content_type": item.get("content_type"),
            }.items()
            if v
        },
    )


def _to_paper_frontend(item: dict[str, Any]) -> Paper:
    authors_block = item.get("authors") or []
    authors = [a.get("preferredName", "") for a in authors_block if a.get("preferredName")]

    year_raw = item.get("publicationYear")
    try:
        year = int(year_raw) if year_raw is not None else None
    except (TypeError, ValueError):
        year = None

    article_number = item.get("articleNumber")
    url = item.get("documentLink")
    if url and not url.startswith("http"):
        url = f"https://ieeexplore.ieee.org{url}"
        
    pdf_url = item.get("pdfLink")
    if pdf_url and not pdf_url.startswith("http"):
        pdf_url = f"https://ieeexplore.ieee.org{pdf_url}"

    return Paper(
        source="ieee",
        title=(item.get("title") or "").strip(),
        authors=authors,
        year=year,
        venue=item.get("publicationTitle"),
        doi=item.get("doi"),
        url=url,
        pdf_url=pdf_url,
        abstract=item.get("abstract"),
        identifiers={
            k: str(v)
            for k, v in {
                "article_number": article_number,
                "publisher": item.get("publisher"),
                "content_type": item.get("contentType"),
            }.items()
            if v
        },
    )


def parse_ieee_response(payload: dict[str, Any]) -> list[Paper]:
    return [_to_paper(item) for item in (payload.get("articles") or [])]


def parse_ieee_frontend_response(payload: dict[str, Any]) -> list[Paper]:
    return [_to_paper_frontend(item) for item in (payload.get("records") or [])]


async def search_ieee(query: str, max_results: int = 10) -> list[Paper]:
    cfg = config.get_config()
    if not cfg.ieee_api_key and not cfg.capes_proxy_url and not cfg.ieee_cookies:
        raise IEEEKeyMissingError()

    # 1. Use Official API if key is present
    if cfg.ieee_api_key:
        params = {
            "apikey": cfg.ieee_api_key,
            "querytext": query,
            "max_records": max(1, min(max_results, 200)),
            "format": "json",
        }
        async with httpx.AsyncClient(
            timeout=30.0, headers={"User-Agent": cfg.user_agent}
        ) as client:
            resp = await client.get(API_URL, params=params)
            resp.raise_for_status()
            return parse_ieee_response(resp.json())
            
    # 2. Fallback to Frontend API via Proxy or Cookies
    proxy_url = cfg.capes_proxy_url or "https://ieeexplore.ieee.org"
    frontend_api_url = f"{proxy_url.rstrip('/')}/rest/search"
    
    headers = {
        "User-Agent": cfg.user_agent,
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": proxy_url,
        "Referer": f"{proxy_url}/search/searchresult.jsp",
    }
    
    if cfg.ieee_cookies:
        headers["Cookie"] = cfg.ieee_cookies

    payload = {
        "newsearch": True,
        "queryText": query,
        "highlight": True,
        "returnFacets": ["ALL"],
        "returnType": "SEARCH",
        "rowsPerPage": max(1, min(max_results, 100)),
    }
    
    async with httpx.AsyncClient(timeout=30.0, headers=headers, follow_redirects=True) as client:
        resp = await client.post(frontend_api_url, json=payload)
        url_str = str(resp.url).lower()
        if resp.status_code in (301, 302, 401, 403) or "login" in url_str or ("periodicos.capes.gov.br" in url_str and "ieeexplore" not in url_str):
            raise IEEEKeyMissingError("IEEE_COOKIES is expired or missing. Please run 'uv run omnisearch-capes-login' to authenticate.")
        resp.raise_for_status()
        try:
            data = resp.json()
        except Exception:
            raise IEEEKeyMissingError("IEEE_COOKIES is expired or invalid. Received HTML response instead of JSON. Please run 'uv run omnisearch-capes-login' to authenticate.")
        return parse_ieee_frontend_response(data)
