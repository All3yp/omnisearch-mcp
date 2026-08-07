from __future__ import annotations

import asyncio
import pytest
import respx
import httpx
from unittest.mock import patch

from omnisearch_mcp.server import (
    mcp,
    search_all,
    search_scite,
    search_consensus,
    search_semantic_scholar,
    search_core,
    search_ieee,
    search_arxiv,
    search_acm,
    search_crossref,
    search_google_scholar,
    get_doi_metadata,
    resolve_oa_url,
    download_paper,
    index_pdf_library,
    search_pdf_library,
    read_pdf_text,
    main,
)
from omnisearch_mcp.sources.google_scholar import SerpApiKeyMissingError

@pytest.mark.asyncio
async def test_tools_registered():
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    expected = {
        "search_ieee",
        "search_arxiv",
        "search_acm",
        "search_crossref",
        "search_google_scholar",
        "search_semantic_scholar",
        "search_core",
        "search_scite",
        "search_consensus",
        "search_all",
        "get_doi_metadata",
        "resolve_oa_url",
        "download_paper",
        "read_paper_content",
        "index_pdf_library",
        "search_pdf_library",
        "read_pdf_text",
    }
    missing = expected - names
    assert not missing, f"Missing tools: {missing}"


@pytest.mark.asyncio
async def test_read_paper_content(tmp_path, monkeypatch):
    from omnisearch_mcp import config
    from omnisearch_mcp.server import read_paper_content
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    import io

    # Create a real PDF with text
    pdf_path = tmp_path / "Test_Paper.pdf"
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.drawString(100, 750, "This is a test paper about quantum computing.")
    c.drawString(100, 730, "Quantum computers use qubits.")
    c.save()
    with open(pdf_path, "wb") as f:
        f.write(buffer.getvalue())

    # Mock config
    monkeypatch.setattr(config, "get_config", lambda: config.Config(
        ieee_api_key=None, contact_email="test@example.com", user_agent="agent",
        capes_proxy_url=None, ieee_cookies=None, semantic_scholar_api_key=None,
        core_api_key=None, scite_cookies=None, consensus_cookies=None
    , serpapi_api_key=None))

    # Mock download to use our test PDF (target where it's imported in reader.py)
    async def mock_download(*args, **kwargs):
        return str(pdf_path), "direct", None
    monkeypatch.setattr("omnisearch_mcp.reader.download_with_fallback", mock_download)

    result = await read_paper_content(
        doi="10.1234/test",
        title="Test Paper",
        save_path=str(tmp_path)
    )

    assert result["path"] == str(pdf_path)
    assert result["error"] is None
    assert "quantum" in result["text"].lower()
    assert result["characters"] > 0
    assert result["pages"] == 1


@pytest.mark.asyncio
async def test_search_scite_missing_auth(monkeypatch):
    from omnisearch_mcp import config
    monkeypatch.setattr(config, "get_config", lambda: config.Config(
        ieee_api_key=None, contact_email="a@b.com", user_agent="agent",
        capes_proxy_url=None, ieee_cookies=None, semantic_scholar_api_key=None,
        core_api_key=None, scite_cookies=None, consensus_cookies=None
    , serpapi_api_key=None))
    res = await search_scite("quantum")
    assert "error" in res
    assert res["auth_required"] is True
    assert res["action"] == "human_relogin_required"
    assert res["provider"] == "scite"
    assert "SESSION-level" in res["agent_instruction"]
    assert "not a query problem" in res["agent_instruction"]
    assert res["results"] == []


@pytest.mark.asyncio
async def test_search_consensus_missing_auth(monkeypatch):
    from omnisearch_mcp import config
    monkeypatch.setattr(config, "get_config", lambda: config.Config(
        ieee_api_key=None, contact_email="a@b.com", user_agent="agent",
        capes_proxy_url=None, ieee_cookies=None, semantic_scholar_api_key=None,
        core_api_key=None, scite_cookies=None, consensus_cookies=None
    , serpapi_api_key=None))
    res = await search_consensus("quantum")
    assert "error" in res
    assert res["auth_required"] is True
    assert res["action"] == "human_relogin_required"
    assert res["provider"] == "consensus"
    assert res["results"] == []


@pytest.mark.asyncio
async def test_search_ieee_missing_auth(monkeypatch):
    from omnisearch_mcp import config
    monkeypatch.setattr(config, "get_config", lambda: config.Config(
        ieee_api_key=None, contact_email="a@b.com", user_agent="agent",
        capes_proxy_url=None, ieee_cookies=None, semantic_scholar_api_key=None,
        core_api_key=None, scite_cookies=None, consensus_cookies=None
    , serpapi_api_key=None))
    res = await search_ieee("quantum")
    assert "error" in res
    assert res["auth_required"] is True
    assert res["provider"] == "ieee"
    assert "omnisearch-capes-login" in res["command"]
    assert res["results"] == []


@pytest.mark.asyncio
async def test_search_core_missing_auth(monkeypatch):
    from omnisearch_mcp import config
    monkeypatch.setattr(config, "get_config", lambda: config.Config(
        ieee_api_key=None, contact_email="a@b.com", user_agent="agent",
        capes_proxy_url=None, ieee_cookies=None, semantic_scholar_api_key=None,
        core_api_key=None, scite_cookies=None, consensus_cookies=None
    , serpapi_api_key=None))
    res = await search_core("quantum")
    assert "error" in res
    assert res["results"] == []


@pytest.mark.asyncio
@respx.mock
async def test_search_arxiv_tool():
    respx.get("https://export.arxiv.org/api/query").mock(
        return_value=httpx.Response(200, text="""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><title>arXiv Paper</title></entry></feed>""")
    )
    res = await search_arxiv("quantum")
    assert res["source"] == "arxiv"
    assert len(res["results"]) == 1


@pytest.mark.asyncio
@respx.mock
async def test_search_acm_tool():
    respx.get("https://api.crossref.org/works").mock(
        return_value=httpx.Response(200, json={"message": {"items": [{"title": ["ACM Paper"]}]}})
    )
    res = await search_acm("quantum")
    assert res["source"] == "acm"
    assert len(res["results"]) == 1


@pytest.mark.asyncio
@respx.mock
async def test_search_crossref_tool():
    respx.get("https://api.crossref.org/works").mock(
        return_value=httpx.Response(200, json={"message": {"items": [{"title": ["CrossRef Paper"]}]}})
    )
    res = await search_crossref("quantum")
    assert res["source"] == "crossref"
    assert len(res["results"]) == 1


@pytest.mark.asyncio
@respx.mock
async def test_search_semantic_scholar_tool(monkeypatch):
    from omnisearch_mcp import config
    monkeypatch.setattr(config, "get_config", lambda: config.Config(
        ieee_api_key=None, contact_email="a@b.com", user_agent="agent",
        capes_proxy_url=None, ieee_cookies=None, semantic_scholar_api_key="s2key",
        core_api_key=None, scite_cookies=None, consensus_cookies=None
    , serpapi_api_key=None))
    respx.get("https://api.semanticscholar.org/graph/v1/paper/search").mock(
        return_value=httpx.Response(200, json={"data": [{"title": "S2 Paper"}]})
    )
    res = await search_semantic_scholar("quantum")
    assert res["source"] == "semantic_scholar"
    assert len(res["results"]) == 1


@pytest.mark.asyncio
@respx.mock
async def test_get_doi_metadata_tool():
    respx.get("https://api.crossref.org/works/10.1234/test").mock(
        return_value=httpx.Response(200, json={"message": {"title": ["Test DOI"]}})
    )
    res = await get_doi_metadata("10.1234/test")
    assert res["title"] == "Test DOI"

    respx.get("https://api.crossref.org/works/10.1234/missing").mock(
        return_value=httpx.Response(404, json={})
    )
    res_missing = await get_doi_metadata("10.1234/missing")
    assert "error" in res_missing


def test_pdf_tools(tmp_path):
    from pypdf import PdfWriter
    pdf_file = tmp_path / "sample.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with open(pdf_file, "wb") as f:
        writer.write(f)

    res_idx = index_pdf_library(str(tmp_path))
    assert "total" in res_idx

    res_search = search_pdf_library(str(tmp_path), "query")
    assert res_search["query"] == "query"

    res_read = read_pdf_text(str(pdf_file))
    assert "text" in res_read or "error" in res_read


@pytest.mark.asyncio
@respx.mock
async def test_search_all_aggregated(monkeypatch):
    from omnisearch_mcp import config
    fake_config = config.Config(
        ieee_api_key="key", contact_email="a@b.com", user_agent="agent",
        capes_proxy_url=None, ieee_cookies=None, semantic_scholar_api_key="s2key",
        core_api_key="corekey", scite_cookies="scite=1", consensus_cookies="consensus=1"
    , serpapi_api_key=None)
    monkeypatch.setattr(config, "get_config", lambda: fake_config)

    # Mock endpoints
    respx.get("https://ieeexploreapi.ieee.org/api/v1/search/articles").mock(
        return_value=httpx.Response(200, json={"articles": [{"title": "IEEE Paper", "publication_year": 2023}]})
    )
    respx.get("https://export.arxiv.org/api/query").mock(
        return_value=httpx.Response(200, text="""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><title>arXiv Paper</title></entry></feed>""")
    )
    respx.get("https://api.crossref.org/works").mock(
        return_value=httpx.Response(200, json={"message": {"items": [{"title": ["CrossRef Paper"]}]}})
    )
    respx.get("https://api.semanticscholar.org/graph/v1/paper/search").mock(
        return_value=httpx.Response(200, json={"data": [{"title": "S2 Paper"}]})
    )
    respx.get("https://api.core.ac.uk/v3/search/works").mock(
        return_value=httpx.Response(200, json={"results": [{"title": "CORE Paper"}]})
    )
    respx.get("https://scite.ai/api/search/papers").mock(
        return_value=httpx.Response(200, json={"hits": {"hits": [{"title": "Scite Paper"}]}})
    )
    respx.get("https://consensus.app/api/v1/search/").mock(
        return_value=httpx.Response(200, json={"results": [{"title": "Consensus Paper"}]})
    )

    all_res = await search_all("machine learning", max_results_each=2)
    assert all_res["query"] == "machine learning"
    assert "ieee" in all_res
    assert "arxiv" in all_res
    assert "acm" in all_res
    assert "crossref" in all_res
    assert "semantic_scholar" in all_res
    assert "core" in all_res
    assert "scite" in all_res
    assert "consensus" in all_res
    assert any(paper["title"] == "CrossRef Paper" for paper in all_res["papers"])

@pytest.mark.asyncio
async def test_search_google_scholar_tool(monkeypatch):
    from omnisearch_mcp.models import Paper

    async def scholar_result(*_args, **_kwargs):
        return [Paper(source="google_scholar", title="Scholar Tool Paper")]

    monkeypatch.setattr("omnisearch_mcp.server._search_google_scholar", scholar_result)

    result = await search_google_scholar("tool contract")

    assert result == {
        "source": "google_scholar",
        "query": "tool contract",
        "results": [{"source": "google_scholar", "title": "Scholar Tool Paper"}],
    }


@pytest.mark.asyncio
async def test_search_all_includes_scholar_and_keeps_crossref_on_missing_key(monkeypatch):
    from omnisearch_mcp.models import Paper

    async def no_results(*_args, **_kwargs):
        return []

    async def crossref_result(*_args, **_kwargs):
        return [Paper(source="crossref", title="Working CrossRef Paper")]

    async def scholar_result(*_args, **_kwargs):
        return [Paper(source="google_scholar", title="Working Scholar Paper")]

    monkeypatch.setattr("omnisearch_mcp.server._search_ieee", no_results)
    monkeypatch.setattr("omnisearch_mcp.server._search_arxiv", no_results)
    monkeypatch.setattr("omnisearch_mcp.server._search_acm", no_results)
    monkeypatch.setattr("omnisearch_mcp.server._search_crossref", crossref_result)
    monkeypatch.setattr("omnisearch_mcp.server._search_semantic_scholar", no_results)
    monkeypatch.setattr("omnisearch_mcp.server._search_core", no_results)
    monkeypatch.setattr("omnisearch_mcp.server._search_scite", no_results)
    monkeypatch.setattr("omnisearch_mcp.server._search_consensus", no_results)
    monkeypatch.setattr("omnisearch_mcp.server._search_google_scholar", scholar_result)

    configured = await search_all("aggregation", max_results_each=1)

    assert configured["google_scholar"]["results"][0]["title"] == "Working Scholar Paper"
    assert any(paper["title"] == "Working CrossRef Paper" for paper in configured["papers"])

    async def missing_key(*_args, **_kwargs):
        raise SerpApiKeyMissingError()

    monkeypatch.setattr("omnisearch_mcp.server._search_google_scholar", missing_key)
    missing_key_result = await search_all("aggregation", max_results_each=1)

    assert missing_key_result["google_scholar"]["results"] == []
    assert "SERPAPI_API_KEY" in missing_key_result["google_scholar"]["error"]
    assert any(paper["title"] == "Working CrossRef Paper" for paper in missing_key_result["papers"])


@pytest.mark.asyncio
@respx.mock
async def test_search_all_reports_auth_required_sources(monkeypatch):
    from omnisearch_mcp import config

    monkeypatch.setattr(config, "get_config", lambda: config.Config(
        ieee_api_key=None, contact_email="a@b.com", user_agent="agent",
        capes_proxy_url=None, ieee_cookies=None, semantic_scholar_api_key=None,
        core_api_key=None, scite_cookies=None, consensus_cookies=None
    , serpapi_api_key=None))
    monkeypatch.setattr("omnisearch_mcp.sources.consensus.persisted_cookie_header", lambda _: None)
    respx.get("https://export.arxiv.org/api/query").mock(
        return_value=httpx.Response(200, text="""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>""")
    )
    respx.get("https://api.crossref.org/works").mock(
        return_value=httpx.Response(200, json={"message": {"items": []}})
    )
    respx.get("https://api.semanticscholar.org/graph/v1/paper/search").mock(
        return_value=httpx.Response(200, json={"data": []})
    )

    res = await search_all("quantum", max_results_each=1)
    assert set(res["auth_required_sources"]) == {"ieee", "scite", "consensus"}
    assert "session-level login failure" in res["agent_instruction"]
    assert "other configured" in res["agent_instruction"]
    assert "SESSION-level" in res["ieee"]["agent_instruction"]
    assert res["ieee"]["action"] == "human_relogin_required"


@pytest.mark.asyncio
async def test_search_all_keeps_other_sources_when_ieee_times_out(monkeypatch):
    from omnisearch_mcp.models import Paper

    async def slow_ieee(*_args, **_kwargs):
        await asyncio.sleep(1)
        return []

    async def crossref_result(*_args, **_kwargs):
        return [Paper(source="crossref", title="Fallback Paper")]

    async def empty_result(*_args, **_kwargs):
        return []

    monkeypatch.setattr("omnisearch_mcp.server.SEARCH_ALL_IEEE_TIMEOUT", 0.01)
    monkeypatch.setattr("omnisearch_mcp.server._search_ieee", slow_ieee)
    monkeypatch.setattr("omnisearch_mcp.server._search_arxiv", empty_result)
    monkeypatch.setattr("omnisearch_mcp.server._search_acm", empty_result)
    monkeypatch.setattr("omnisearch_mcp.server._search_crossref", crossref_result)
    monkeypatch.setattr("omnisearch_mcp.server._search_semantic_scholar", empty_result)
    monkeypatch.setattr("omnisearch_mcp.server._search_core", empty_result)
    monkeypatch.setattr("omnisearch_mcp.server._search_scite", empty_result)
    monkeypatch.setattr("omnisearch_mcp.server._search_consensus", empty_result)

    result = await search_all("fallback", max_results_each=1)

    assert result["ieee"]["results"] == []
    assert "timed out after 0.01s" in result["ieee"]["error"]
    assert result["crossref"]["results"][0]["title"] == "Fallback Paper"
    assert result["papers"][0]["title"] == "Fallback Paper"

@pytest.mark.asyncio
@respx.mock
async def test_resolve_oa_url(monkeypatch):
    from omnisearch_mcp import config
    monkeypatch.setattr(config, "get_config", lambda: config.Config(
        ieee_api_key=None, contact_email="test@example.com", user_agent="agent",
        capes_proxy_url=None, ieee_cookies=None, semantic_scholar_api_key=None,
        core_api_key=None, scite_cookies=None, consensus_cookies=None
    , serpapi_api_key=None))
    respx.get("https://api.unpaywall.org/v2/10.1234/test").mock(
        return_value=httpx.Response(200, json={
            "best_oa_location": {"url_for_pdf": "https://example.com/paper.pdf"}
        })
    )
    res = await resolve_oa_url("10.1234/test")
    assert res["url"] == "https://example.com/paper.pdf"
    assert res["source"] == "unpaywall"


@pytest.mark.asyncio
@respx.mock
async def test_resolve_oa_url_not_found(monkeypatch):
    from omnisearch_mcp import config
    monkeypatch.setattr(config, "get_config", lambda: config.Config(
        ieee_api_key=None, contact_email="test@example.com", user_agent="agent",
        capes_proxy_url=None, ieee_cookies=None, semantic_scholar_api_key=None,
        core_api_key=None, scite_cookies=None, consensus_cookies=None
    , serpapi_api_key=None))
    respx.get("https://api.unpaywall.org/v2/10.1234/missing").mock(
        return_value=httpx.Response(404, json={})
    )
    res = await resolve_oa_url("10.1234/missing")
    assert res["url"] is None
    assert res["source"] == "none"


@pytest.mark.asyncio
@respx.mock
async def test_download_paper_with_direct_url(tmp_path, monkeypatch):
    from omnisearch_mcp import config
    monkeypatch.setattr(config, "get_config", lambda: config.Config(
        ieee_api_key=None, contact_email="test@example.com", user_agent="agent",
        capes_proxy_url=None, ieee_cookies=None, semantic_scholar_api_key=None,
        core_api_key=None, scite_cookies=None, consensus_cookies=None
    , serpapi_api_key=None))
    pdf_content = b"%PDF-1.4\nfake pdf content"
    respx.get("https://example.com/paper.pdf").mock(
        return_value=httpx.Response(200, content=pdf_content, headers={"content-type": "application/pdf"})
    )
    res = await download_paper(
        doi="10.1234/test",
        title="Test Paper",
        pdf_url="https://example.com/paper.pdf",
        save_path=str(tmp_path)
    )
    assert res["path"] is not None
    assert res["source"] == "direct"
    assert res["error"] is None
    assert "Test_Paper.pdf" in res["path"]


@pytest.mark.asyncio
@respx.mock
async def test_download_paper_with_unpaywall_fallback(tmp_path, monkeypatch):
    from omnisearch_mcp import config
    monkeypatch.setattr(config, "get_config", lambda: config.Config(
        ieee_api_key=None, contact_email="test@example.com", user_agent="agent",
        capes_proxy_url=None, ieee_cookies=None, semantic_scholar_api_key=None,
        core_api_key=None, scite_cookies=None, consensus_cookies=None
    , serpapi_api_key=None))
    pdf_content = b"%PDF-1.4\nfake pdf content"
    respx.get("https://api.unpaywall.org/v2/10.1234/test").mock(
        return_value=httpx.Response(200, json={
            "best_oa_location": {"url_for_pdf": "https://example.com/oa-paper.pdf"}
        })
    )
    respx.get("https://example.com/oa-paper.pdf").mock(
        return_value=httpx.Response(200, content=pdf_content, headers={"content-type": "application/pdf"})
    )
    res = await download_paper(
        doi="10.1234/test",
        title="OA Paper",
        pdf_url=None,
        save_path=str(tmp_path)
    )
    assert res["path"] is not None
    assert res["source"] == "unpaywall"
    assert res["error"] is None


@pytest.mark.asyncio
@respx.mock
async def test_download_paper_with_core_repository_fallback(tmp_path, monkeypatch):
    from omnisearch_mcp import config

    monkeypatch.setattr(config, "get_config", lambda: config.Config(
        ieee_api_key=None, contact_email="test@example.com", user_agent="agent",
        capes_proxy_url=None, ieee_cookies=None, semantic_scholar_api_key=None,
        core_api_key="corekey", scite_cookies=None, consensus_cookies=None
    , serpapi_api_key=None))
    respx.get("https://api.unpaywall.org/v2/10.1234/core").mock(
        return_value=httpx.Response(404, json={})
    )
    respx.get("https://api.core.ac.uk/v3/search/works").mock(
        return_value=httpx.Response(200, json={"results": [{
            "title": "Core Paper",
            "downloadUrl": "https://core.example/paper.pdf",
        }]})
    )
    respx.get("https://core.example/paper.pdf").mock(
        return_value=httpx.Response(
            200,
            content=b"%PDF-1.4\nfake",
            headers={"content-type": "application/pdf"},
        )
    )
    res = await download_paper(
        doi="10.1234/core",
        title="Core Paper",
        save_path=str(tmp_path),
    )
    assert res["path"] is not None
    assert res["source"] == "core"
    assert res["error"] is None


@pytest.mark.asyncio
@respx.mock
async def test_search_all_deduplication(monkeypatch):
    from omnisearch_mcp import config
    fake_config = config.Config(
        ieee_api_key=None, contact_email="a@b.com", user_agent="agent",
        capes_proxy_url=None, ieee_cookies=None, semantic_scholar_api_key=None,
        core_api_key=None, scite_cookies=None, consensus_cookies=None
    , serpapi_api_key=None)
    monkeypatch.setattr(config, "get_config", lambda: fake_config)

    # Same paper in multiple sources with same DOI
    respx.get("https://export.arxiv.org/api/query").mock(
        return_value=httpx.Response(200, text="""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Duplicate Paper</title><id>arXiv:1234.5678</id><published>2024-01-01T00:00:00Z</published></entry></feed>""")
    )
    respx.get("https://api.crossref.org/works").mock(
        return_value=httpx.Response(200, json={"message": {"items": [{"title": ["Duplicate Paper"], "DOI": "10.1234/test"}]}})
    )

    all_res = await search_all("duplicate", max_results_each=1)
    assert "papers" in all_res
    assert "total" in all_res
    # Should have deduplicated papers
    assert all_res["total"] <= 2  # At most 2 unique papers


@pytest.mark.asyncio
@respx.mock
async def test_download_paper_rejects_html(tmp_path):
    respx.get("https://example.com/not-pdf").mock(
        return_value=httpx.Response(
            200,
            text="<html>not a pdf</html>",
            headers={"content-type": "text/html"},
        )
    )
    res = await download_paper(
        doi="",
        title="Not PDF",
        pdf_url="https://example.com/not-pdf",
        save_path=str(tmp_path),
    )
    assert res["path"] is None
    assert res["source"] == "none"
    assert res["error"] is not None


@pytest.mark.asyncio
@respx.mock
async def test_download_paper_with_scihub_fallback(tmp_path, monkeypatch):
    from omnisearch_mcp import config

    monkeypatch.setattr(config, "get_config", lambda: config.Config(
        ieee_api_key=None, contact_email="test@example.com", user_agent="agent",
        capes_proxy_url=None, ieee_cookies=None, semantic_scholar_api_key=None,
        core_api_key=None, scite_cookies=None, consensus_cookies=None
    , serpapi_api_key=None))
    respx.get("https://api.unpaywall.org/v2/10.1234/paywalled").mock(
        return_value=httpx.Response(404, json={})
    )
    respx.get("https://sci-hub.se/10.1234/paywalled").mock(
        return_value=httpx.Response(
            200,
            text='<html><embed src="/downloads/paywalled.pdf"></html>',
            headers={"content-type": "text/html"},
        )
    )
    respx.get("https://sci-hub.se/downloads/paywalled.pdf").mock(
        return_value=httpx.Response(
            200,
            content=b"%PDF-1.4\nfake",
            headers={"content-type": "application/pdf"},
        )
    )
    res = await download_paper(
        doi="10.1234/paywalled",
        title="Paywalled Paper",
        save_path=str(tmp_path),
        use_scihub=True,
    )
    assert res["path"] is not None
    assert res["source"] == "scihub"
    assert res["error"] is None


@pytest.mark.asyncio
async def test_read_paper_content_extraction_failure(tmp_path, monkeypatch):
    from omnisearch_mcp.server import read_paper_content

    bad_pdf = tmp_path / "Bad_Paper.pdf"
    bad_pdf.write_bytes(b"%PDF-bad")

    async def mock_download(*args, **kwargs):
        return str(bad_pdf), "direct", None

    monkeypatch.setattr("omnisearch_mcp.reader.download_with_fallback", mock_download)

    result = await read_paper_content(
        doi="10.1234/bad",
        title="Bad Paper",
        save_path=str(tmp_path),
    )
    assert result["path"] == str(bad_pdf)
    assert result["text"] == ""
    assert result["error"] and "text extraction failed" in result["error"]


def test_scihub_extract_pdf_url():
    from omnisearch_mcp.scihub import SciHubFetcher

    fetcher = SciHubFetcher()
    html = '<html><iframe src="//example.org/paper.pdf?download=true"></iframe></html>'
    assert fetcher._extract_pdf_url(html) == "//example.org/paper.pdf?download=true"


def test_server_main():
    with patch.object(mcp, "run") as mock_run:
        main()
        assert mock_run.called
