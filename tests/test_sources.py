from __future__ import annotations

import httpx
import pytest
import respx
from dataclasses import replace

from omnisearch_mcp.sources.arxiv import API_URL as ARXIV_URL
from omnisearch_mcp.sources.arxiv import parse_arxiv_atom, search_arxiv
from omnisearch_mcp.sources.crossref import (
    API_URL as CR_URL,
    get_doi_metadata,
    search_acm,
    search_crossref,
)
from omnisearch_mcp.sources.ieee import (
    API_URL as IEEE_URL,
    IEEEKeyMissingError,
    _append_unique_papers,
    parse_ieee_advanced_search_html,
    parse_ieee_response,
    parse_ieee_frontend_response,
    search_ieee,
)
from omnisearch_mcp.sources.semantic_scholar import (
    API_URL as S2_URL,
    search_semantic_scholar,
)
from omnisearch_mcp.sources.core import (
    API_URL as CORE_URL,
    CoreKeyMissingError,
    search_core,
)
from omnisearch_mcp.sources.scite import (
    API_URL as SCITE_URL,
    SciteAuthMissingError,
    search_scite,
)
from omnisearch_mcp.sources.consensus import (
    API_URL as CONSENSUS_URL,
    ConsensusAuthMissingError,
    search_consensus,
)
from omnisearch_mcp import config

ARXIV_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2401.00001v1</id>
    <title>Attention Is All You Really Need</title>
    <summary>An abstract about transformers and attention.</summary>
    <published>2024-01-02T00:00:00Z</published>
    <author><name>Ada Lovelace</name></author>
    <author><name>Alan Turing</name></author>
    <link rel="alternate" href="http://arxiv.org/abs/2401.00001v1"/>
    <link title="pdf" href="http://arxiv.org/pdf/2401.00001v1"/>
    <arxiv:doi>10.1234/example.2024.1</arxiv:doi>
    <arxiv:journal_ref>NeurIPS 2024</arxiv:journal_ref>
  </entry>
</feed>
"""

CROSSREF_FIXTURE = {
    "message": {
        "items": [
            {
                "DOI": "10.1145/3650200",
                "title": ["A Study of Distributed Systems"],
                "author": [
                    {"given": "Grace", "family": "Hopper"},
                    {"name": "Karen Spärck Jones"},
                ],
                "container-title": ["Proceedings of SOSP"],
                "issued": {"date-parts": [[2024, 6, 1]]},
                "abstract": "<jats:p>An <i>abstract</i> with tags.</jats:p>",
                "URL": "https://doi.org/10.1145/3650200",
                "ISSN": ["1234-5678"],
                "type": "proceedings-article",
            }
        ]
    }
}

IEEE_FIXTURE = {
    "articles": [
        {
            "article_number": "9999999",
            "title": "Some IEEE Paper",
            "publication_year": "2023",
            "publication_title": "IEEE Transactions on Examples",
            "doi": "10.1109/EXAMPLE.2023.9999999",
            "html_url": "https://ieeexplore.ieee.org/document/9999999",
            "pdf_url": "https://ieeexplore.ieee.org/stamp/stamp.jsp?arnumber=9999999",
            "abstract": "An IEEE abstract.",
            "publisher": "IEEE",
            "content_type": "Conferences",
            "authors": {
                "authors": [
                    {"full_name": "Linus Torvalds"},
                    {"full_name": "Ken Thompson"},
                ]
            },
        }
    ]
}

IEEE_FRONTEND_FIXTURE = {
    "records": [
        {
            "articleNumber": "8888888",
            "title": "Frontend IEEE Paper",
            "publicationYear": "2022",
            "publicationTitle": "IEEE Journal Frontend",
            "doi": "10.1109/FRONTEND.2022.8888888",
            "documentLink": "/document/8888888",
            "pdfLink": "/stamp/stamp.jsp?arnumber=8888888",
            "abstract": "Frontend abstract.",
            "publisher": "IEEE",
            "contentType": "Journals",
            "authors": [
                {"preferredName": "Dennis Ritchie"}
            ]
        }
    ]
}


def test_parse_arxiv_atom():
    papers = parse_arxiv_atom(ARXIV_FIXTURE)
    assert len(papers) == 1
    p = papers[0]
    assert p.source == "arxiv"
    assert p.title.startswith("Attention")
    assert p.year == 2024
    assert p.authors == ["Ada Lovelace", "Alan Turing"]
    assert p.doi == "10.1234/example.2024.1"
    assert p.pdf_url and p.pdf_url.endswith("2401.00001v1")
    assert p.identifiers.get("arxiv") == "2401.00001v1"
    assert p.venue == "NeurIPS 2024"


def test_parse_ieee_response():
    papers = parse_ieee_response(IEEE_FIXTURE)
    assert len(papers) == 1
    p = papers[0]
    assert p.source == "ieee"
    assert p.year == 2023
    assert "Linus Torvalds" in p.authors
    assert p.identifiers.get("article_number") == "9999999"


def test_parse_ieee_frontend_response():
    papers = parse_ieee_frontend_response(IEEE_FRONTEND_FIXTURE)
    assert len(papers) == 1
    p = papers[0]
    assert p.source == "ieee"
    assert p.year == 2022
    assert "Dennis Ritchie" in p.authors
    assert p.url == "https://ieeexplore.ieee.org/document/8888888"


@pytest.mark.asyncio
@respx.mock
async def test_search_arxiv():
    respx.get(ARXIV_URL).mock(
        return_value=httpx.Response(200, text=ARXIV_FIXTURE)
    )
    papers = await search_arxiv("transformers", max_results=5)
    assert len(papers) == 1
    assert papers[0].source == "arxiv"


@pytest.mark.asyncio
@respx.mock
async def test_search_crossref_and_acm():
    from urllib.parse import unquote

    route = respx.get(CR_URL).mock(
        return_value=httpx.Response(200, json=CROSSREF_FIXTURE)
    )
    papers = await search_crossref("distributed systems", max_results=5)
    assert len(papers) == 1
    assert papers[0].source == "crossref"
    assert papers[0].abstract and "<" not in papers[0].abstract

    acm = await search_acm("distributed systems", max_results=5)
    assert acm[0].source == "acm"
    assert route.call_count == 2
    last_request = route.calls[-1].request
    assert "member:320" in unquote(str(last_request.url))


@pytest.mark.asyncio
@respx.mock
async def test_get_doi_metadata():
    respx.get(f"{CR_URL}/10.1145/3650200").mock(
        return_value=httpx.Response(
            200, json={"message": CROSSREF_FIXTURE["message"]["items"][0]}
        )
    )
    paper = await get_doi_metadata("https://doi.org/10.1145/3650200")
    assert paper is not None
    assert paper.doi == "10.1145/3650200"


@pytest.mark.asyncio
@respx.mock
async def test_get_doi_metadata_404():
    respx.get(f"{CR_URL}/10.0/missing").mock(
        return_value=httpx.Response(404, json={"message": "not found"})
    )
    paper = await get_doi_metadata("10.0/missing")
    assert paper is None


@pytest.mark.asyncio
async def test_search_ieee_missing_key(monkeypatch):
    monkeypatch.setattr(
        config, "get_config", lambda: config.Config(
            ieee_api_key=None, contact_email="a@b.com", user_agent="agent",
            capes_proxy_url=None, ieee_cookies=None, semantic_scholar_api_key=None,
            core_api_key=None, scite_cookies=None, consensus_cookies=None
        )
    )
    with pytest.raises(IEEEKeyMissingError):
        await search_ieee("anything")


@pytest.mark.asyncio
@respx.mock
async def test_search_ieee_with_key(monkeypatch):
    monkeypatch.setattr(
        config, "get_config", lambda: config.Config(
            ieee_api_key="fake-key", contact_email="a@b.com", user_agent="agent",
            capes_proxy_url=None, ieee_cookies=None, semantic_scholar_api_key=None,
            core_api_key=None, scite_cookies=None, consensus_cookies=None
        )
    )
    respx.get(IEEE_URL).mock(return_value=httpx.Response(200, json=IEEE_FIXTURE))
    papers = await search_ieee("anything", max_results=3)
    assert len(papers) == 1
    assert papers[0].source == "ieee"


def test_parse_ieee_advanced_search_html():
    html = """
    <html><body>
      <a href="/document/1234567" aria-label="Advanced IEEE Paper">ignored</a>
      <a href="/document/1234567" aria-label="Advanced IEEE Paper">duplicate</a>
      <a href="/document/7654321">Second IEEE Paper</a>
    </body></html>
    """

    papers = parse_ieee_advanced_search_html(html, "https://capes.proxy.example.com", 10)

    assert len(papers) == 2
    assert papers[0].title == "Advanced IEEE Paper"
    assert papers[0].url == "https://capes.proxy.example.com/document/1234567/"
    assert papers[0].identifiers["article_number"] == "1234567"
    assert papers[1].title == "Second IEEE Paper"


def test_parse_ieee_advanced_search_html_respects_result_limit():
    html = "".join(
        f'<a href="/document/{number}">Paper {number}</a>'
        for number in range(1000000, 1000004)
    )

    papers = parse_ieee_advanced_search_html(html, "https://capes.proxy.example.com", 2)

    assert [paper.identifiers["article_number"] for paper in papers] == [
        "1000000",
        "1000001",
    ]


def test_append_unique_ieee_papers_stops_at_result_limit():
    first_page = parse_ieee_advanced_search_html(
        ''.join(
            f'<a href="/document/{number}">Paper {number}</a>'
            for number in range(1000000, 1000002)
        ),
        "https://capes.proxy.example.com",
        2,
    )
    next_page = parse_ieee_advanced_search_html(
        ''.join(
            f'<a href="/document/{number}">Paper {number}</a>'
            for number in range(1000001, 1000004)
        ),
        "https://capes.proxy.example.com",
        3,
    )

    _append_unique_papers(first_page, next_page, 3)

    assert [paper.identifiers["article_number"] for paper in first_page] == [
        "1000000",
        "1000001",
        "1000002",
    ]


@pytest.mark.asyncio
async def test_search_ieee_browser_proxy_fallback(monkeypatch):
    proxy_url = "https://capes.proxy.example.com"
    monkeypatch.setattr(
        config, "get_config", lambda: config.Config(
            ieee_api_key=None, contact_email="a@b.com", user_agent="agent",
            capes_proxy_url=proxy_url,
            ieee_cookies="session=123", semantic_scholar_api_key=None,
            core_api_key=None, scite_cookies=None, consensus_cookies=None
        )
    )
    called = {}

    async def fake_browser_search(query, max_results, proxy):
        called["query"] = query
        called["max_results"] = max_results
        called["proxy"] = proxy
        return [parse_ieee_advanced_search_html(
            '<html><body>IEEE Xplore <a href="/document/1234567">Advanced IEEE Paper</a></body></html>',
            proxy,
            max_results,
        )[0]]

    monkeypatch.setattr("omnisearch_mcp.sources.ieee.search_ieee_with_browser", fake_browser_search)

    papers = await search_ieee("proxy test", max_results=3)
    assert called == {"query": "proxy test", "max_results": 3, "proxy": proxy_url}
    assert len(papers) == 1
    assert papers[0].source == "ieee"
    assert papers[0].title == "Advanced IEEE Paper"


def test_ieee_to_paper_invalid_year():
    from omnisearch_mcp.sources.ieee import _to_paper, _to_paper_frontend
    p1 = _to_paper({"title": "T1", "publication_year": "invalid"})
    assert p1.year is None

    p2 = _to_paper_frontend({"title": "T2", "publicationYear": "invalid"})
    assert p2.year is None


@pytest.mark.asyncio
@respx.mock
async def test_search_semantic_scholar(monkeypatch):
    monkeypatch.setattr(
        config, "get_config", lambda: config.Config(
            ieee_api_key=None, contact_email="a@b.com", user_agent="agent",
            capes_proxy_url=None, ieee_cookies=None, semantic_scholar_api_key="s2key",
            core_api_key=None, scite_cookies=None, consensus_cookies=None
        )
    )
    respx.get(S2_URL).mock(return_value=httpx.Response(200, json={
        "data": [
            {
                "title": "S2 Title",
                "authors": [{"name": "Author 1"}],
                "year": 2021,
                "venue": "Nature",
                "abstract": "S2 Abstract",
                "url": "https://semanticscholar.org/123",
                "openAccessPdf": {"url": "https://pdf.url"},
                "externalIds": {"DOI": "10.1000/123"}
            }
        ]
    }))
    papers = await search_semantic_scholar("ai", max_results=5)
    assert len(papers) == 1
    assert papers[0].source == "semantic_scholar"
    assert papers[0].title == "S2 Title"
    assert papers[0].doi == "10.1000/123"


@pytest.mark.asyncio
@respx.mock
async def test_search_semantic_scholar_retries_429(monkeypatch):
    monkeypatch.setattr(
        config, "get_config", lambda: config.Config(
            ieee_api_key=None, contact_email="a@b.com", user_agent="agent",
            capes_proxy_url=None, ieee_cookies=None, semantic_scholar_api_key="s2key",
            core_api_key=None, scite_cookies=None, consensus_cookies=None
        )
    )
    async def no_sleep(*_):
        return None
    monkeypatch.setattr("omnisearch_mcp.sources.semantic_scholar.asyncio.sleep", no_sleep)
    route = respx.get(S2_URL).mock(side_effect=[
        httpx.Response(429, json={"error": "rate limited"}),
        httpx.Response(200, json={"data": [{"title": "Recovered"}]}),
    ])
    papers = await search_semantic_scholar("ai", max_results=5)
    assert len(papers) == 1
    assert papers[0].title == "Recovered"
    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_search_arxiv_retries_429(monkeypatch):
    async def no_sleep(*_):
        return None
    monkeypatch.setattr("omnisearch_mcp.sources.arxiv.asyncio.sleep", no_sleep)
    route = respx.get(ARXIV_URL).mock(side_effect=[
        httpx.Response(429, text="rate limited"),
        httpx.Response(200, text=ARXIV_FIXTURE),
    ])
    papers = await search_arxiv("transformers", max_results=5)
    assert len(papers) == 1
    assert route.call_count == 2


@pytest.mark.asyncio
async def test_search_core_missing_key(monkeypatch):
    monkeypatch.setattr(
        config, "get_config", lambda: config.Config(
            ieee_api_key=None, contact_email="a@b.com", user_agent="agent",
            capes_proxy_url=None, ieee_cookies=None, semantic_scholar_api_key=None,
            core_api_key=None, scite_cookies=None, consensus_cookies=None
        )
    )
    with pytest.raises(CoreKeyMissingError):
        await search_core("anything")


@pytest.mark.asyncio
@respx.mock
async def test_search_core_with_key(monkeypatch):
    monkeypatch.setattr(
        config, "get_config", lambda: config.Config(
            ieee_api_key=None, contact_email="a@b.com", user_agent="agent",
            capes_proxy_url=None, ieee_cookies=None, semantic_scholar_api_key=None,
            core_api_key="corekey", scite_cookies=None, consensus_cookies=None
        )
    )
    respx.get(CORE_URL).mock(return_value=httpx.Response(200, json={
        "results": [
            {
                "title": "CORE Title",
                "authors": [{"name": "Core Author"}],
                "year": 2020,
                "publisher": "CORE Publisher",
                "doi": "10.2000/core",
                "downloadUrl": "https://core.ac.uk/download.pdf",
                "abstract": "CORE Abstract",
                "id": 12345
            }
        ]
    }))
    papers = await search_core("robotics", max_results=5)
    assert len(papers) == 1
    assert papers[0].source == "core"
    assert papers[0].title == "CORE Title"


@pytest.mark.asyncio
async def test_search_scite_missing_cookies(monkeypatch):
    monkeypatch.setattr(
        config, "get_config", lambda: config.Config(
            ieee_api_key=None, contact_email="a@b.com", user_agent="agent",
            capes_proxy_url=None, ieee_cookies=None, semantic_scholar_api_key=None,
            core_api_key=None, scite_cookies=None, consensus_cookies=None
        )
    )
    with pytest.raises(SciteAuthMissingError):
        await search_scite("anything")


@pytest.mark.asyncio
@respx.mock
async def test_search_scite_with_cookies(monkeypatch):
    monkeypatch.setattr(
        config, "get_config", lambda: config.Config(
            ieee_api_key=None, contact_email="a@b.com", user_agent="agent",
            capes_proxy_url=None, ieee_cookies=None, semantic_scholar_api_key=None,
            core_api_key=None, scite_cookies="session=abc", consensus_cookies=None
        )
    )
    respx.get(SCITE_URL).mock(return_value=httpx.Response(200, json={
        "hits": {
            "hits": [
                {
                    "_source": {
                        "title": "Scite Title",
                        "authors": ["Scite Author"],
                        "year": 2023,
                        "journal": "Scite Journal",
                        "doi": "10.3000/scite",
                        "abstract": "Scite Abstract",
                        "id": "scite1"
                    }
                }
            ]
        }
    }))
    papers = await search_scite("biology", max_results=5)
    assert len(papers) == 1
    assert papers[0].source == "scite"
    assert papers[0].title == "Scite Title"


@pytest.mark.asyncio
async def test_search_consensus_missing_cookies(monkeypatch):
    monkeypatch.setattr(
        config, "get_config", lambda: config.Config(
            ieee_api_key=None, contact_email="a@b.com", user_agent="agent",
            capes_proxy_url=None, ieee_cookies=None, semantic_scholar_api_key=None,
            core_api_key=None, scite_cookies=None, consensus_cookies=None
        )
    )
    with pytest.raises(ConsensusAuthMissingError):
        await search_consensus("anything")


@pytest.mark.asyncio
@respx.mock
async def test_search_consensus_with_cookies(monkeypatch):
    monkeypatch.setattr(
        config, "get_config", lambda: config.Config(
            ieee_api_key=None, contact_email="a@b.com", user_agent="agent",
            capes_proxy_url=None, ieee_cookies=None, semantic_scholar_api_key=None,
            core_api_key=None, scite_cookies=None, consensus_cookies="session=xyz"
        )
    )
    respx.get(CONSENSUS_URL).mock(return_value=httpx.Response(200, json={
        "results": [
            {
                "title": "Consensus Title",
                "authors": [{"name": "Consensus Author"}],
                "year": 2024,
                "venue": "Consensus Journal",
                "doi": "10.4000/consensus",
                "url": "https://consensus.app/details/1",
                "abstract": "Consensus Abstract",
                "id": "c1"
            }
        ]
    }))
    papers = await search_consensus("medicine", max_results=5)
    assert len(papers) == 1
    assert papers[0].source == "consensus"
    assert papers[0].title == "Consensus Title"
