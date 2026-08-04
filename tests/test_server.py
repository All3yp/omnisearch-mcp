from __future__ import annotations

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
    get_doi_metadata,
    index_pdf_library,
    search_pdf_library,
    read_pdf_text,
    main,
)


@pytest.mark.asyncio
async def test_tools_registered():
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    expected = {
        "search_ieee",
        "search_arxiv",
        "search_acm",
        "search_crossref",
        "search_semantic_scholar",
        "search_core",
        "search_scite",
        "search_consensus",
        "search_all",
        "get_doi_metadata",
        "index_pdf_library",
        "search_pdf_library",
        "read_pdf_text",
    }
    missing = expected - names
    assert not missing, f"Missing tools: {missing}"


@pytest.mark.asyncio
async def test_search_scite_missing_auth(monkeypatch):
    from omnisearch_mcp import config
    monkeypatch.setattr(config, "get_config", lambda: config.Config(
        ieee_api_key=None, contact_email="a@b.com", user_agent="agent",
        capes_proxy_url=None, ieee_cookies=None, semantic_scholar_api_key=None,
        core_api_key=None, scite_cookies=None, consensus_cookies=None
    ))
    res = await search_scite("quantum")
    assert "error" in res
    assert res["results"] == []


@pytest.mark.asyncio
async def test_search_consensus_missing_auth(monkeypatch):
    from omnisearch_mcp import config
    monkeypatch.setattr(config, "get_config", lambda: config.Config(
        ieee_api_key=None, contact_email="a@b.com", user_agent="agent",
        capes_proxy_url=None, ieee_cookies=None, semantic_scholar_api_key=None,
        core_api_key=None, scite_cookies=None, consensus_cookies=None
    ))
    res = await search_consensus("quantum")
    assert "error" in res
    assert res["results"] == []


@pytest.mark.asyncio
async def test_search_ieee_missing_auth(monkeypatch):
    from omnisearch_mcp import config
    monkeypatch.setattr(config, "get_config", lambda: config.Config(
        ieee_api_key=None, contact_email="a@b.com", user_agent="agent",
        capes_proxy_url=None, ieee_cookies=None, semantic_scholar_api_key=None,
        core_api_key=None, scite_cookies=None, consensus_cookies=None
    ))
    res = await search_ieee("quantum")
    assert "error" in res
    assert res["results"] == []


@pytest.mark.asyncio
async def test_search_core_missing_auth(monkeypatch):
    from omnisearch_mcp import config
    monkeypatch.setattr(config, "get_config", lambda: config.Config(
        ieee_api_key=None, contact_email="a@b.com", user_agent="agent",
        capes_proxy_url=None, ieee_cookies=None, semantic_scholar_api_key=None,
        core_api_key=None, scite_cookies=None, consensus_cookies=None
    ))
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
    ))
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
    )
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
    assert "semantic_scholar" in all_res
    assert "core" in all_res
    assert "scite" in all_res
    assert "consensus" in all_res


def test_server_main():
    with patch.object(mcp, "run") as mock_run:
        main()
        assert mock_run.called
