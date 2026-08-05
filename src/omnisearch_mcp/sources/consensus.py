"""Consensus.app API adapter using Web API and cookies."""
from __future__ import annotations

from typing import Any

import httpx

from .. import config
from ..models import Paper

# Note: This uses Consensus internal API which might change.
API_URL = "https://consensus.app/api/v1/search/"


class ConsensusAuthMissingError(RuntimeError):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message
            or "CONSENSUS_COOKIES is not set or expired. Please run `uv run omnisearch-consensus-login` "
            "to authenticate and capture logged-in cookies."
        )


def _to_paper(item: dict[str, Any]) -> Paper:
    authors_raw = item.get("authors") or []
    authors = []
    for a in authors_raw:
        if isinstance(a, str):
            authors.append(a)
        elif isinstance(a, dict):
            authors.append(a.get("name", ""))

    doi = item.get("doi")
    url = item.get("url")
    if doi and not url:
        url = f"https://doi.org/{doi}"

    return Paper(
        source="consensus",
        title=(item.get("title") or "").strip(),
        authors=authors,
        year=item.get("year"),
        venue=item.get("journal") or item.get("venue"),
        doi=doi,
        url=url,
        pdf_url=None,
        abstract=item.get("abstract"),
        identifiers={"consensus_id": str(item.get("id"))} if item.get("id") else {},
    )


async def search_consensus(query: str, max_results: int = 10) -> list[Paper]:
    cfg = config.get_config()
    if not cfg.consensus_cookies:
        raise ConsensusAuthMissingError()

    headers = {
        "User-Agent": cfg.user_agent,
        "Accept": "application/json",
        "Cookie": cfg.consensus_cookies,
    }

    params = {
        "query": query,
        "limit": max(1, min(max_results, 50)),
    }

    async with httpx.AsyncClient(timeout=30.0, headers=headers, follow_redirects=True) as client:
        resp = await client.get(API_URL, params=params)
        if resp.status_code in (301, 302, 401, 403, 404) or "login" in str(resp.url).lower() or "sign-in" in str(resp.url).lower():
            raise ConsensusAuthMissingError()
        resp.raise_for_status()
        try:
            data = resp.json()
        except Exception:
            raise ConsensusAuthMissingError("CONSENSUS_COOKIES is expired or invalid. Received HTML response instead of JSON. Please run 'uv run omnisearch-consensus-login' to authenticate.")

        results = data.get("results", []) or data.get("papers", [])
        return [_to_paper(item) for item in results]
