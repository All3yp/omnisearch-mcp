"""Tests for the omnisearch-check-auth diagnostic script."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from omnisearch_mcp import config
from omnisearch_mcp.scripts import check_auth


def _config(**overrides):
    base = dict(
        ieee_api_key=None,
        contact_email="a@b.com",
        user_agent="agent",
        capes_proxy_url=None,
        ieee_cookies=None,
        semantic_scholar_api_key=None,
        core_api_key=None,
        scite_cookies=None,
        consensus_cookies=None,
        serpapi_api_key=None,
    )
    base.update(overrides)
    return config.Config(**base)


@pytest.mark.asyncio
async def test_check_ieee_auth_reports_no_credentials(monkeypatch):
    monkeypatch.setattr(config, "get_config", lambda: _config())
    monkeypatch.setattr(
        "omnisearch_mcp.scripts.check_auth.persisted_cookie_header", lambda provider: None
    )

    result = await check_auth.check_ieee_auth()

    assert result["ready"] is False
    assert result["provider"] == "IEEE"
    assert "command" in result


@pytest.mark.asyncio
@respx.mock
async def test_check_ieee_auth_api_key_valid(monkeypatch):
    monkeypatch.setattr(
        config, "get_config", lambda: _config(ieee_api_key="fake-key")
    )
    respx.get("https://ieeexploreapi.ieee.org/api/v1/search/articles").mock(
        return_value=httpx.Response(200, json={"articles": []})
    )

    result = await check_auth.check_ieee_auth()

    assert result["ready"] is True
    assert result["method"] == "API key"


@pytest.mark.asyncio
@respx.mock
async def test_check_ieee_auth_api_key_invalid(monkeypatch):
    monkeypatch.setattr(
        config, "get_config", lambda: _config(ieee_api_key="bad-key")
    )
    respx.get("https://ieeexploreapi.ieee.org/api/v1/search/articles").mock(
        return_value=httpx.Response(401)
    )

    result = await check_auth.check_ieee_auth()

    assert result["ready"] is False
    assert result["method"] == "API key"


@pytest.mark.asyncio
async def test_check_ieee_auth_capes_session_valid(monkeypatch):
    proxy_url = "https://ieeexplore-ieee-org.proxy.capes.gov.br"
    monkeypatch.setattr(
        config,
        "get_config",
        lambda: _config(capes_proxy_url=proxy_url, ieee_cookies="session=valid"),
    )
    monkeypatch.setattr(
        "omnisearch_mcp.scripts.check_auth.persisted_cookie_header", lambda provider: None
    )

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/json"}

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, headers=None, json=None, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(
        "omnisearch_mcp.scripts.check_auth.AsyncSession", lambda *a, **k: FakeSession()
    )

    result = await check_auth.check_ieee_auth()

    assert result["ready"] is True
    assert result["method"] == "CAPES proxy"


@pytest.mark.asyncio
async def test_check_ieee_auth_capes_session_expired(monkeypatch):
    proxy_url = "https://ieeexplore-ieee-org.proxy.capes.gov.br"
    monkeypatch.setattr(
        config,
        "get_config",
        lambda: _config(capes_proxy_url=proxy_url, ieee_cookies="session=stale"),
    )
    monkeypatch.setattr(
        "omnisearch_mcp.scripts.check_auth.persisted_cookie_header", lambda provider: None
    )

    class FakeResponse:
        status_code = 403
        headers = {}

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, headers=None, json=None, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(
        "omnisearch_mcp.scripts.check_auth.AsyncSession", lambda *a, **k: FakeSession()
    )

    result = await check_auth.check_ieee_auth()

    assert result["ready"] is False
    assert result["command"] == "uv run omnisearch-capes-login"


@pytest.mark.asyncio
async def test_check_scite_auth_missing_cookies(monkeypatch):
    monkeypatch.setattr(config, "get_config", lambda: _config())
    monkeypatch.setattr(
        "omnisearch_mcp.scripts.check_auth.persisted_cookie_header", lambda provider: None
    )

    result = await check_auth.check_scite_auth()

    assert result["ready"] is False
    assert result["command"] == "uv run omnisearch-scite-login"


@pytest.mark.asyncio
@respx.mock
async def test_check_scite_auth_valid(monkeypatch):
    monkeypatch.setattr(
        config, "get_config", lambda: _config(scite_cookies="session=abc")
    )
    monkeypatch.setattr(
        "omnisearch_mcp.scripts.check_auth.persisted_cookie_header", lambda provider: None
    )
    respx.get("https://scite.ai/api/search/papers").mock(
        return_value=httpx.Response(200, json={"hits": {"hits": []}})
    )

    result = await check_auth.check_scite_auth()

    assert result["ready"] is True


@pytest.mark.asyncio
async def test_check_consensus_auth_missing_cookies(monkeypatch):
    monkeypatch.setattr(config, "get_config", lambda: _config())
    monkeypatch.setattr(
        "omnisearch_mcp.scripts.check_auth.persisted_cookie_header", lambda provider: None
    )

    result = await check_auth.check_consensus_auth()

    assert result["ready"] is False
    assert result["command"] == "uv run omnisearch-consensus-login"


@pytest.mark.asyncio
@respx.mock
async def test_check_consensus_auth_valid(monkeypatch):
    monkeypatch.setattr(
        config, "get_config", lambda: _config(consensus_cookies="session=abc")
    )
    monkeypatch.setattr(
        "omnisearch_mcp.scripts.check_auth.persisted_cookie_header", lambda provider: None
    )
    respx.get("https://consensus.app/api/v1/search/").mock(
        return_value=httpx.Response(200, json={"results": []})
    )

    result = await check_auth.check_consensus_auth()

    assert result["ready"] is True


@pytest.mark.asyncio
async def test_check_all_auth_runs_all_checks_concurrently(monkeypatch):
    monkeypatch.setattr(
        check_auth, "check_ieee_auth", AsyncMock(return_value={"provider": "IEEE", "ready": True})
    )
    monkeypatch.setattr(
        check_auth,
        "check_scite_auth",
        AsyncMock(return_value={"provider": "Scite.ai", "ready": False}),
    )
    monkeypatch.setattr(
        check_auth,
        "check_consensus_auth",
        AsyncMock(return_value={"provider": "Consensus.app", "ready": True}),
    )

    results = await check_auth.check_all_auth()

    assert len(results) == 3
    providers = {r["provider"] for r in results}
    assert providers == {"IEEE", "Scite.ai", "Consensus.app"}
