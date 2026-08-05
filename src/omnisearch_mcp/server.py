"""FastMCP server exposing research search tools over stdio."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from .downloader import download_with_fallback
from .pdfs.library import index_library, read_pdf, search_library
from .reader import read_paper
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
from .unpaywall import UnpaywallResolver
from .utils import dedupe_papers

log = logging.getLogger("omnisearch_mcp")

mcp = FastMCP("omnisearch-mcp")


def _papers_to_dicts(papers) -> list[dict[str, Any]]:
    return [p.to_dict() for p in papers]


def _auth_error_response(provider: str, command: str, error: Exception) -> dict[str, Any]:
    """Return a structured auth error that tells agents to pause for human relogin."""
    return {
        "error": str(error),
        "auth_required": True,
        "provider": provider,
        "action": "human_relogin_required",
        "command": command,
        "agent_instruction": (
            "Stop retrying this provider. Ask the human to run the command, "
            "wait for login completion, then retry the same tool once."
        ),
        "results": [],
    }


@mcp.tool()
async def search_ieee(query: str, max_results: int = 10) -> dict[str, Any]:
    """Search IEEE Xplore (requires IEEE_XPLORE_API_KEY, CAPES_PROXY_URL or IEEE_COOKIES).

    Returns metadata + abstracts.
    """
    try:
        papers = await _search_ieee(query, max_results=max_results)
    except IEEEKeyMissingError as exc:
        return _auth_error_response("ieee", "uv run omnisearch-capes-login --headless", exc)
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
        return _auth_error_response("scite", "uv run omnisearch-scite-login --headless", exc)
    return {"source": "scite", "query": query, "results": _papers_to_dicts(papers)}


@mcp.tool()
async def search_consensus(query: str, max_results: int = 10) -> dict[str, Any]:
    """Search Consensus.app using logged in cookies."""
    try:
        papers = await _search_consensus(query, max_results=max_results)
    except ConsensusAuthMissingError as exc:
        return _auth_error_response("consensus", "uv run omnisearch-consensus-login --headless", exc)
    return {"source": "consensus", "query": query, "results": _papers_to_dicts(papers)}


@mcp.tool()
async def search_all(query: str, max_results_each: int = 5) -> dict[str, Any]:
    """Search IEEE, arXiv, ACM, Semantic Scholar, CORE, Scite e Consensus in parallel.

    Results are deduplicated by DOI and title+authors.
    """
    # Per-source timeout to prevent one slow source from blocking the entire search
    _SOURCE_TIMEOUT = 15.0

    async def _with_timeout(coro, label: str):
        try:
            return await asyncio.wait_for(coro, timeout=_SOURCE_TIMEOUT)
        except asyncio.TimeoutError:
            log.warning("search_all: %s timed out after %.1fs", label, _SOURCE_TIMEOUT)
            raise TimeoutError(f"{label} timed out after {_SOURCE_TIMEOUT}s")

    ieee_task = _with_timeout(_search_ieee(query, max_results=max_results_each), "ieee")
    arxiv_task = _with_timeout(_search_arxiv(query, max_results=max_results_each), "arxiv")
    acm_task = _with_timeout(_search_acm(query, max_results=max_results_each), "acm")
    s2_task = _with_timeout(_search_semantic_scholar(query, max_results=max_results_each), "semantic_scholar")
    core_task = _with_timeout(_search_core(query, max_results=max_results_each), "core")
    scite_task = _with_timeout(_search_scite(query, max_results=max_results_each), "scite")
    consensus_task = _with_timeout(_search_consensus(query, max_results=max_results_each), "consensus")

    results = await asyncio.gather(
        ieee_task, arxiv_task, acm_task, s2_task, core_task, scite_task, consensus_task, return_exceptions=True
    )

    def _section(label: str, value: Any) -> dict[str, Any]:
        if isinstance(value, IEEEKeyMissingError):
            return _auth_error_response("ieee", "uv run omnisearch-capes-login --headless", value)
        if isinstance(value, SciteAuthMissingError):
            return _auth_error_response("scite", "uv run omnisearch-scite-login --headless", value)
        if isinstance(value, ConsensusAuthMissingError):
            return _auth_error_response("consensus", "uv run omnisearch-consensus-login --headless", value)
        if hasattr(value, "__class__") and "Error" in value.__class__.__name__:
            return {"error": str(value), "results": []}
        if isinstance(value, Exception):
            log.exception("search_all: %s failed", label, exc_info=value)
            return {"error": f"{type(value).__name__}: {value}", "results": []}
        return {"results": _papers_to_dicts(value)}

    ieee_section = _section("ieee", results[0])
    arxiv_section = _section("arxiv", results[1])
    acm_section = _section("acm", results[2])
    semantic_section = _section("semantic_scholar", results[3])
    core_section = _section("core", results[4])
    scite_section = _section("scite", results[5])
    consensus_section = _section("consensus", results[6])

    # Deduplicate all papers across sources
    all_papers = (
        ieee_section.get("results", [])
        + arxiv_section.get("results", [])
        + acm_section.get("results", [])
        + semantic_section.get("results", [])
        + core_section.get("results", [])
        + scite_section.get("results", [])
        + consensus_section.get("results", [])
    )
    deduped_papers = dedupe_papers(all_papers)

    sections = {
        "ieee": ieee_section,
        "arxiv": arxiv_section,
        "acm": acm_section,
        "semantic_scholar": semantic_section,
        "core": core_section,
        "scite": scite_section,
        "consensus": consensus_section,
    }
    auth_required_sources = [
        name for name, section in sections.items() if section.get("auth_required")
    ]

    return {
        "query": query,
        **sections,
        "auth_required_sources": auth_required_sources,
        "agent_instruction": (
            "For sources in auth_required_sources, do not retry in a loop. "
            "Ask the human to relogin with each section's command, wait, then retry once."
            if auth_required_sources
            else None
        ),
        "papers": deduped_papers,
        "total": len(deduped_papers),
    }


@mcp.tool()
async def get_doi_metadata(doi: str) -> dict[str, Any]:
    """Look up a DOI via CrossRef and return normalized metadata."""
    paper = await _get_doi_metadata(doi)
    if paper is None:
        return {"error": f"No CrossRef record found for DOI: {doi}"}
    return paper.to_dict()


@mcp.tool()
async def resolve_oa_url(doi: str) -> dict[str, Any]:
    """Resolve open-access PDF URL for a DOI using Unpaywall.

    Args:
        doi: Paper DOI (e.g., "10.1234/example").

    Returns:
        Dictionary with 'url' (PDF URL or None) and 'source' ('unpaywall' or 'none').
    """
    resolver = UnpaywallResolver()
    if not resolver.has_api_access():
        return {"url": None, "source": "none", "error": "Unpaywall not configured"}

    pdf_url = resolver.resolve_best_pdf_url(doi)
    return {"url": pdf_url, "source": "unpaywall" if pdf_url else "none"}


@mcp.tool()
async def download_paper(
    doi: str,
    title: str = "",
    pdf_url: str | None = None,
    save_path: str = "./downloads",
    use_scihub: bool = False,
) -> dict[str, Any]:
    """Download PDF with fallback chain: direct URL → Unpaywall → Sci-Hub (optional).

    Args:
        doi: Paper DOI.
        title: Paper title (used for filename).
        pdf_url: Known PDF URL (optional).
        save_path: Directory to save PDF (default: ./downloads).
        use_scihub: If True, use Sci-Hub as last resort (default: False).
            WARNING: Sci-Hub operates in legal gray area. Use responsibly.

    Returns:
        Dictionary with 'path' (file path or None) and 'error' (message if failed).
    """
    file_path, source, error = await download_with_fallback(
        doi, title, pdf_url, save_path, use_scihub
    )
    return {"path": file_path, "source": source, "error": error if not file_path else None}


@mcp.tool()
async def read_paper_content(
    doi: str,
    title: str = "",
    pdf_url: str | None = None,
    save_path: str = "./downloads",
    max_chars: int = 50000,
    use_scihub: bool = False,
) -> dict[str, Any]:
    """Download a paper and extract its full text content.

    Args:
        doi: Paper DOI.
        title: Paper title (used for filename and display).
        pdf_url: Known PDF URL (optional, will use fallback chain if None).
        save_path: Directory to save PDF (default: ./downloads).
        max_chars: Maximum characters to extract (default: 50000).
        use_scihub: If True, use Sci-Hub as last resort (default: False).
            WARNING: Sci-Hub operates in legal gray area. Use responsibly.

    Returns:
        Dictionary with:
        - path: Path to saved PDF
        - title: Paper title
        - pages: Number of pages
        - characters: Total characters extracted
        - text: Extracted text content
        - source: How PDF was obtained (direct/unpaywall/scihub/cached)
        - error: Error message if failed
    """
    result = await read_paper(doi, title, pdf_url, save_path, max_chars, use_scihub)
    return result


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
