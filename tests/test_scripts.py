from __future__ import annotations

import json
import os
import httpx
import pytest
import respx
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from omnisearch_mcp.scripts import capes_login, scite_login, consensus_login
from omnisearch_mcp.scripts.session_store import persisted_cookie_header


async def _async_noop(*args, **kwargs):
    pass


async def _async_false(*args, **kwargs):
    return False


async def _async_true(*args, **kwargs):
    return True


def _async_val(val):
    async def _fn(*args, **kwargs):
        return val
    return _fn


async def _async_raise(*args, **kwargs):
    raise RuntimeError("click intercepted")


@pytest.mark.asyncio
async def test_click_first_visible_uses_first_matching_selector():
    hidden = MagicMock()
    hidden.is_visible = _async_false
    visible = MagicMock()
    visible.is_visible = _async_true
    visible.click = AsyncMock()

    page = MagicMock()
    page.locator = MagicMock(side_effect=[MagicMock(first=hidden), MagicMock(first=visible)])

    clicked = await capes_login.click_first_visible(page, ("missing", "button"), "test button")

    assert clicked is True
    visible.click.assert_called_once_with(timeout=5000)


@pytest.mark.asyncio
async def test_current_url_changed_detects_navigation():
    page = MagicMock()
    page.url = "https://acesso-cafe.capes.gov.br/login"
    page.wait_for_timeout = _async_noop

    changed = await capes_login.current_url_changed(page, "https://www.periodicos.capes.gov.br/")

    assert changed is True


@pytest.mark.asyncio
async def test_current_url_changed_rejects_same_page_menu_click():
    page = MagicMock()
    page.url = "https://www.periodicos.capes.gov.br/"
    page.wait_for_timeout = _async_noop

    changed = await capes_login.current_url_changed(page, "https://www.periodicos.capes.gov.br/")

    assert changed is False

@pytest.mark.asyncio
async def test_validate_ieee_proxy_session_requires_json_search_response(monkeypatch):
    proxy_url = "https://ieeexplore-ieee-org.proxy.capes.gov.br"
    captured_calls = []

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/json"}

        def json(self):
            return {"records": []}

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, headers=None, json=None, **kwargs):
            captured_calls.append(
                SimpleNamespace(url=url, headers=headers, json=json, kwargs=kwargs)
            )
            return FakeResponse()

    monkeypatch.setattr(
        "omnisearch_mcp.scripts.capes_login.AsyncSession", lambda *a, **k: FakeSession()
    )

    valid, reason = await capes_login.validate_ieee_proxy_session(
        proxy_url, "session=valid"
    )

    assert valid is True
    assert reason == "validated"
    assert captured_calls[0].headers["Cookie"] == "session=valid"
    assert captured_calls[0].json == {
        "newsearch": True,
        "queryText": "machine learning",
        "returnType": "SEARCH",
        "rowsPerPage": 1,
    }
    assert captured_calls[0].kwargs["impersonate"] == "chrome124"
    # An explicit non-browser User-Agent overrides curl_cffi's impersonation UA
    # while leaving Chrome's sec-ch-ua/TLS fingerprint intact, and Akamai flags
    # that mismatch as a bot (HTTP 418). Let curl_cffi supply a consistent UA.
    assert "User-Agent" not in captured_calls[0].headers

@pytest.mark.asyncio
@pytest.mark.parametrize("status_code, headers, text", [
    (302, {"location": "https://acesso-cafe.capes.gov.br/login"}, ""),
    (403, {}, ""),
    (200, {"content-type": "text/html"}, "<html>login</html>"),
])
async def test_validate_ieee_proxy_session_rejects_invalid_auth_response(status_code, headers, text, monkeypatch):
    proxy_url = "https://ieeexplore-ieee-org.proxy.capes.gov.br"

    class FakeResponse:
        def __init__(self):
            self.status_code = status_code
            self.headers = headers
            self.text = text

        def json(self):
            raise ValueError("not json")

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, headers=None, json=None, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(
        "omnisearch_mcp.scripts.capes_login.AsyncSession", lambda *a, **k: FakeSession()
    )

    valid, reason = await capes_login.validate_ieee_proxy_session(proxy_url, "session=stale")

    assert valid is False
    assert reason != "validated"


@pytest.mark.asyncio
async def test_click_first_visible_falls_back_to_dom_click():
    visible = MagicMock()
    visible.is_visible = _async_true
    visible.click = AsyncMock(side_effect=RuntimeError("click intercepted"))
    visible.evaluate = AsyncMock()
    page = MagicMock()
    page.locator = MagicMock(return_value=MagicMock(first=visible))

    clicked = await capes_login.click_first_visible(page, ("button",), "test button")

    assert clicked is True
    visible.evaluate.assert_called_once_with("element => element.click()")


@pytest.fixture
def mock_playwright_page():
    page = MagicMock()
    page.url = os.getenv("CAPES_PROXY_URL", "https://periodicos.capes.gov.br/")
    page.wait_for_timeout = _async_noop
    page.wait_for_selector = _async_noop
    page.wait_for_url = _async_noop
    page.goto = _async_noop
    page.evaluate = _async_false

    # Mock locator helper (synchronous locator call returning async actions)
    locator_mock = MagicMock()
    locator_mock.is_visible = _async_false
    locator_mock.click = _async_noop
    locator_mock.fill = _async_noop
    locator_mock.type = _async_noop
    locator_mock.first = locator_mock

    page.locator = MagicMock(return_value=locator_mock)
    page.get_by_role = MagicMock(return_value=MagicMock(first=locator_mock))
    page.get_by_placeholder = MagicMock(return_value=MagicMock(first=locator_mock))
    page.get_by_text = MagicMock(return_value=MagicMock(first=locator_mock))
    page.get_by_test_id = MagicMock(return_value=MagicMock(get_by_role=MagicMock(return_value=MagicMock(first=locator_mock))))
    return page


@pytest.fixture
def mock_playwright(mock_playwright_page):
    browser = MagicMock()
    browser.close = _async_noop
    context = MagicMock()
    context.cookies = _async_val([{"name": "fake_cookie", "value": "abc", "domain": "example.test"}])
    context.storage_state = _async_noop
    context.pages = [mock_playwright_page]
    context.new_page = _async_val(mock_playwright_page)
    browser.new_context = _async_val(context)
    browser.context = context

    return browser


@pytest.mark.asyncio
async def test_capes_login_flow_already_logged_in(mock_playwright, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CAFE_INSTITUTION_ID", raising=False)
    monkeypatch.delenv("CAFE_USERNAME", raising=False)
    monkeypatch.delenv("CAFE_PASSWORD", raising=False)
    mock_playwright.context.pages[0].url = "https://ieeexplore-ieee-org.proxy.capes.gov.br/"

    with patch("omnisearch_mcp.scripts.capes_login.launch_async", return_value=mock_playwright):
        with patch("omnisearch_mcp.scripts.capes_login.validate_ieee_browser_session", _async_val((True, "validated"))):
            with patch("omnisearch_mcp.scripts.capes_login.validate_ieee_proxy_session", _async_val((True, "validated"))):
                await capes_login.run_login_flow(headless=True)

    env_file = tmp_path / ".env"
    assert env_file.exists()
    content = env_file.read_text()
    assert "IEEE_COOKIES=" in content
    assert "fake_cookie=abc" in content


@pytest.mark.asyncio
async def test_capes_login_flow_uses_env_proxy_for_validation(mock_playwright, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CAFE_INSTITUTION_ID", raising=False)
    monkeypatch.delenv("CAFE_USERNAME", raising=False)
    monkeypatch.delenv("CAFE_PASSWORD", raising=False)
    proxy_url = "https://ieeexplore-ieee-org.proxy.capes.gov.br"
    monkeypatch.setenv("CAPES_PROXY_URL", proxy_url)
    (tmp_path / ".env").write_text(f"CAPES_PROXY_URL={proxy_url}\n", encoding="utf-8")
    mock_playwright.context.pages[0].url = "https://www.periodicos.capes.gov.br/"

    with patch("omnisearch_mcp.scripts.capes_login.launch_async", return_value=mock_playwright):
        with patch("omnisearch_mcp.scripts.capes_login.validate_ieee_browser_session", _async_val((True, "validated"))):
            with patch("omnisearch_mcp.scripts.capes_login.validate_ieee_proxy_session", _async_val((True, "validated"))):
                await capes_login.run_login_flow(headless=True)

    content = (tmp_path / ".env").read_text()
    assert f"CAPES_PROXY_URL='{proxy_url}'" in content
    assert "IEEE_COOKIES=" in content


@pytest.mark.asyncio
async def test_capes_login_flow_auto_fill(mock_playwright_page, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    proxy_url = "https://ieeexplore-ieee-org.proxy.capes.gov.br/"
    (tmp_path / ".env").write_text(f"CAPES_PROXY_URL='{proxy_url}'\n", encoding="utf-8")
    monkeypatch.setenv("CAPES_PROXY_URL", proxy_url)
    monkeypatch.setenv("CAFE_INSTITUTION_ID", "IFCE")
    monkeypatch.setenv("CAFE_USERNAME", "user123")
    monkeypatch.setenv("CAFE_PASSWORD", "pass123")

    locator_mock = MagicMock()
    locator_mock.is_visible = _async_true
    locator_mock.click = _async_noop
    locator_mock.fill = _async_noop
    locator_mock.type = _async_noop
    locator_mock.first = locator_mock
    mock_playwright_page.locator = MagicMock(return_value=locator_mock)

    urls = [
        "https://www.periodicos.capes.gov.br/",
        "https://acesso-cafe.capes.gov.br/login",
        "https://proxy.capes.gov.br/logged",
        "https://ieeexplore-ieee-org.proxy.capes.gov.br/",
    ]
    url_idx = 0
    def get_url():
        nonlocal url_idx
        u = urls[min(url_idx, len(urls) - 1)]
        url_idx += 1
        return u

    type(mock_playwright_page).url = property(lambda self: get_url())

    browser = MagicMock()
    browser.close = _async_noop
    context = MagicMock()
    context.cookies = _async_val([{"name": "capes_sess", "value": "123", "domain": "capes.gov.br"}])
    context.storage_state = _async_noop
    context.pages = [mock_playwright_page]
    context.new_page = _async_val(mock_playwright_page)
    browser.new_context = _async_val(context)
    respx.get("https://ieeexplore-ieee-org.proxy.capes.gov.br/Xplore/home.jsp").mock(
        return_value=httpx.Response(200, text="IEEE Xplore search results")
    )

    with patch("omnisearch_mcp.scripts.capes_login.launch_async", return_value=browser):
        with patch("omnisearch_mcp.scripts.capes_login.validate_ieee_proxy_session", _async_val((True, "validated"))):
            with patch("asyncio.sleep", _async_noop):
                await capes_login.run_login_flow(headless=True)

    env_file = tmp_path / ".env"
    assert env_file.exists()


@pytest.mark.asyncio
async def test_validate_ieee_browser_session_finds_search_ui():
    page = MagicMock()
    page.url = "https://ieeexplore-ieee-org.proxy.capes.gov.br/Xplore/home.jsp"
    page.goto = _async_noop
    page.wait_for_timeout = _async_noop
    marker = MagicMock()
    marker.is_visible = _async_true
    page.locator = MagicMock(return_value=MagicMock(first=marker))

    valid, reason = await capes_login.validate_ieee_browser_session(
        page,
        "https://ieeexplore-ieee-org.proxy.capes.gov.br",
    )

    assert valid is True
    assert reason == "validated"


@pytest.mark.asyncio
async def test_validate_ieee_browser_session_rejects_418():
    page = MagicMock()
    page.url = "https://ieeexplore-ieee-org.proxy.capes.gov.br/Xplore/home.jsp"
    page.goto = _async_noop
    page.wait_for_timeout = _async_noop
    marker = MagicMock()
    marker.is_visible = _async_false
    page.locator = MagicMock(return_value=MagicMock(first=marker))
    page.content = _async_val("Unusual Traffic Detected (Error 418)")

    valid, reason = await capes_login.validate_ieee_browser_session(
        page,
        "https://ieeexplore-ieee-org.proxy.capes.gov.br",
    )

    assert valid is False
    assert "418" in reason


@pytest.mark.asyncio
async def test_scite_login_flow(mock_playwright, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SCITE_EMAIL", "test@scite.ai")
    monkeypatch.setenv("SCITE_PASS", "password123")
    mock_playwright.context.cookies = _async_val([
        {"name": "userSession", "value": "abc", "domain": "scite.ai"}
    ])

    with patch("omnisearch_mcp.scripts.scite_login.launch_async", return_value=mock_playwright):
        await scite_login.run_login_flow(headless=True)

    env_file = tmp_path / ".env"
    assert env_file.exists()
    content = env_file.read_text()
    assert "SCITE_COOKIES=" in content
    assert "userSession=abc" in content


@pytest.mark.asyncio
async def test_consensus_login_flow(mock_playwright_page, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSENSUS_EMAIL", "test@consensus.app")
    monkeypatch.setenv("CONSENSUS_PASS", "password123")

    mock_playwright_page.url = "https://consensus.app/search/"

    browser = MagicMock()
    browser.close = _async_noop
    context = MagicMock()
    context.cookies = _async_val([{"name": "consensus_sess", "value": "xyz", "domain": "consensus.app"}])
    context.storage_state = _async_noop
    context.pages = [mock_playwright_page]
    context.new_page = _async_val(mock_playwright_page)
    browser.new_context = _async_val(context)

    with patch("omnisearch_mcp.scripts.consensus_login.launch_async", return_value=browser):
        await consensus_login.run_login_flow(headless=True)

    env_file = tmp_path / ".env"
    assert env_file.exists()
    content = env_file.read_text()
    assert "CONSENSUS_COOKIES=" in content
    assert "consensus_sess=xyz" in content


def test_persisted_cookie_header_ignores_expired_cookies(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    session_path = tmp_path / ".omnisearch" / "sessions" / "consensus.storage.json"
    session_path.parent.mkdir(parents=True)
    session_path.write_text(
        # Playwright uses expires == -1 for session cookies (no expiry until the
        # browser closes), not 0. A cookie with expires == 0 legitimately expired
        # at the Unix epoch and must be filtered out.
        '{"cookies": ['
        '{"name":"expired","value":"old","expires":1},'
        '{"name":"active","value":"new","expires":-1}'
        ']}',
        encoding="utf-8",
    )

    assert persisted_cookie_header("consensus") == "active=new"


def test_main_cli_args(monkeypatch):
    from omnisearch_mcp.scripts import login_all

    with patch("omnisearch_mcp.scripts.scite_login.run_login_flow", side_effect=_async_noop):
        with patch("asyncio.run") as mock_run:
            monkeypatch.setattr("sys.argv", ["script", "--headless"])
            scite_login.main()
            assert mock_run.called

    with patch("omnisearch_mcp.scripts.consensus_login.run_login_flow", side_effect=_async_noop):
        with patch("asyncio.run") as mock_run:
            monkeypatch.setattr("sys.argv", ["script", "--headless"])
            consensus_login.main()
            assert mock_run.called

    with patch("omnisearch_mcp.scripts.capes_login.run_login_flow", side_effect=_async_noop):
        with patch("asyncio.run") as mock_run:
            monkeypatch.setattr("sys.argv", ["script", "--headless"])
            capes_login.main()
            assert mock_run.called

    with patch("omnisearch_mcp.scripts.login_all.run_all_logins", side_effect=_async_noop):
        with patch("asyncio.run") as mock_run:
            monkeypatch.setattr("sys.argv", ["script", "--headless"])
            login_all.main()
            assert mock_run.called


@pytest.mark.asyncio
async def test_login_all_flow():
    from omnisearch_mcp.scripts import login_all
    with patch("omnisearch_mcp.scripts.capes_login.run_login_flow", side_effect=_async_noop) as m1:
        with patch("omnisearch_mcp.scripts.scite_login.run_login_flow", side_effect=_async_noop) as m2:
            with patch("omnisearch_mcp.scripts.consensus_login.run_login_flow", side_effect=_async_noop) as m3:
                await login_all.run_all_logins(headless=True)
                assert m1.called
                assert m2.called
                assert m3.called
