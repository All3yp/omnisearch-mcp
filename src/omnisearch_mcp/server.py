"""FastMCP server exposing research search tools over stdio."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from .pdfs.library import index_library, read_pdf, search_library
from .sources.arxiv import search_arxiv as _search_arxiv
from .sources.crossref import (
    get_doi_metadata as _get_doi_metadata,
)
from .sources.crossref import (
    search_acm as _search_acm,
)
from .sources.crossref import (
    search_crossref as _search_crossref,
)
from .sources.ieee import IEEEKeyMissingError
from .sources.ieee import search_ieee as _search_ieee
from .sources.semantic_scholar import search_semantic_scholar as _search_semantic_scholar
from .sources.core import CoreKeyMissingError, search_core as _search_core
from .sources.scite import SciteAuthMissingError, search_scite as _search_scite
from .sources.consensus import ConsensusAuthMissingError, search_consensus as _search_consensus

log = logging.getLogger("omnisearch_mcp")

mcp = FastMCP("omnisearch-mcp")


def _papers_to_dicts(papers) -> list[dict[str, Any]]:
    return [p.to_dict() for p in papers]


@mcp.tool()
async def search_ieee(query: str, max_results: int = 10) -> dict[str, Any]:
    """Search IEEE Xplore (requires IEEE_XPLORE_API_KEY, CAPES_PROXY_URL or IEEE_COOKIES).

    Returns metadata + abstracts.
    """
    try:
        papers = await _search_ieee(query, max_results=max_results)
    except IEEEKeyMissingError as exc:
        return {"error": str(exc), "results": []}
    return {"source": "ieee", "query": query, "results": _papers_to_dicts(papers)}


@mcp.tool()
async def search_arxiv(query: str, max_results: int = 10) -> dict[str, Any]:
    """Search arXiv (open access, no API key required)."""
    papers = await _search_arxiv(query, max_results=max_results)
    return {"source": "arxiv", "query": query, "results": _papers_to_dicts(papers)}


@mcp.tool()
async def search_acm(query: str, max_results: int = 10) -> dict[str, Any]:
    """Search ACM Digital Library metadata via CrossRef (member 320).

    Returns metadata + abstracts where available. Full text still requires
    institutional or personal ACM access.
    """
    papers = await _search_acm(query, max_results=max_results)
    return {"source": "acm", "query": query, "results": _papers_to_dicts(papers)}


@mcp.tool()
async def search_crossref(query: str, max_results: int = 10) -> dict[str, Any]:
    """Search all of CrossRef (covers most academic publishers' metadata)."""
    papers = await _search_crossref(query, max_results=max_results)
    return {"source": "crossref", "query": query, "results": _papers_to_dicts(papers)}


@mcp.tool()
async def search_semantic_scholar(query: str, max_results: int = 10) -> dict[str, Any]:
    """Search Semantic Scholar Academic Graph API."""
    papers = await _search_semantic_scholar(query, max_results=max_results)
    return {"source": "semantic_scholar", "query": query, "results": _papers_to_dicts(papers)}


@mcp.tool()
async def search_core(query: str, max_results: int = 10) -> dict[str, Any]:
    """Search CORE (core.ac.uk) API."""
    try:
        papers = await _search_core(query, max_results=max_results)
    except CoreKeyMissingError as exc:
        return {"error": str(exc), "results": []}
    return {"source": "core", "query": query, "results": _papers_to_dicts(papers)}


@mcp.tool()
async def search_scite(query: str, max_results: int = 10) -> dict[str, Any]:
    """Search Scite.ai using logged in cookies."""
    try:
        papers = await _search_scite(query, max_results=max_results)
    except SciteAuthMissingError as exc:
        return {"error": str(exc), "results": []}
    return {"source": "scite", "query": query, "results": _papers_to_dicts(papers)}


@mcp.tool()
async def search_consensus(query: str, max_results: int = 10) -> dict[str, Any]:
    """Search Consensus.app using logged in cookies."""
    try:
        papers = await _search_consensus(query, max_results=max_results)
    except ConsensusAuthMissingError as exc:
        return {"error": str(exc), "results": []}
    return {"source": "consensus", "query": query, "results": _papers_to_dicts(papers)}


@mcp.tool()
async def search_all(query: str, max_results_each: int = 5) -> dict[str, Any]:
    """Search IEEE, arXiv, ACM, Semantic Scholar, CORE, Scite e Consensus in parallel."""
    ieee_task = _search_ieee(query, max_results=max_results_each)
    arxiv_task = _search_arxiv(query, max_results=max_results_each)
    acm_task = _search_acm(query, max_results=max_results_each)
    s2_task = _search_semantic_scholar(query, max_results=max_results_each)
    core_task = _search_core(query, max_results=max_results_each)
    scite_task = _search_scite(query, max_results=max_results_each)
    consensus_task = _search_consensus(query, max_results=max_results_each)

    results = await asyncio.gather(
        ieee_task, arxiv_task, acm_task, s2_task, core_task, scite_task, consensus_task, return_exceptions=True
    )

    def _section(label: str, value: Any) -> dict[str, Any]:
        if hasattr(value, "__class__") and "Error" in value.__class__.__name__:
            return {"error": str(value), "results": []}
        if isinstance(value, Exception):
            log.exception("search_all: %s failed", label, exc_info=value)
            return {"error": f"{type(value).__name__}: {value}", "results": []}
        return {"results": _papers_to_dicts(value)}

    return {
        "query": query,
        "ieee": _section("ieee", results[0]),
        "arxiv": _section("arxiv", results[1]),
        "acm": _section("acm", results[2]),
        "semantic_scholar": _section("semantic_scholar", results[3]),
        "core": _section("core", results[4]),
        "scite": _section("scite", results[5]),
        "consensus": _section("consensus", results[6]),
    }


@mcp.tool()
async def get_doi_metadata(doi: str) -> dict[str, Any]:
    """Look up a DOI via CrossRef and return normalized metadata."""
    paper = await _get_doi_metadata(doi)
    if paper is None:
        return {"error": f"No CrossRef record found for DOI: {doi}"}
    return paper.to_dict()


@mcp.tool()
def index_pdf_library(folder_path: str, force: bool = False) -> dict[str, Any]:
    """Walk a folder of PDFs, extract text, and cache to .pdf_index.json.

    Set ``force=True`` to re-index files regardless of mtime.
    """
    return index_library(folder_path, force=force)


@mcp.tool()
def search_pdf_library(
    folder_path: str,
    query: str,
    max_results: int = 10,
    context_chars: int = 300,
) -> dict[str, Any]:
    """Substring-search the indexed PDF library and return ranked snippets."""
    matches = search_library(
        folder_path,
        query,
        max_results=max_results,
        context_chars=context_chars,
    )
    return {"query": query, "folder": folder_path, "results": matches}


@mcp.tool()
def read_pdf_text(path: str, max_chars: int = 20000) -> dict[str, Any]:
    """Extract text from a single PDF file (truncated to ``max_chars``)."""
    return read_pdf(path, max_chars=max_chars)


def main() -> None:
    """Console entry point — runs the MCP server over stdio."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    mcp.run()


if __name__ == "__main__":
    main()
