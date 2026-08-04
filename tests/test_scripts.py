from __future__ import annotations

import os
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from omnisearch_mcp.scripts import capes_login, scite_login, consensus_login


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
    page.get_by_test_id = MagicMock(return_value=MagicMock(get_by_role=MagicMock(return_value=MagicMock(first=locator_mock))))
    return page


@pytest.fixture
def mock_playwright(mock_playwright_page):
    browser = MagicMock()
    browser.close = _async_noop
    context = MagicMock()
    context.cookies = _async_val([{"name": "fake_cookie", "value": "abc"}])
    context.new_page = _async_val(mock_playwright_page)
    browser.new_context = _async_val(context)

    return browser


@pytest.mark.asyncio
async def test_capes_login_flow_already_logged_in(mock_playwright, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with patch("omnisearch_mcp.scripts.capes_login.launch_async", return_value=mock_playwright):
        await capes_login.run_login_flow(headless=True)

    env_file = tmp_path / ".env"
    assert env_file.exists()
    content = env_file.read_text()
    assert "IEEE_COOKIES=" in content
    assert "fake_cookie=abc" in content


@pytest.mark.asyncio
async def test_capes_login_flow_auto_fill(mock_playwright_page, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    proxy_url = "https://ieeexplore-ieee-org.proxy.capes.gov.br/"
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
    context.cookies = _async_val([{"name": "capes_sess", "value": "123"}])
    context.new_page = _async_val(mock_playwright_page)
    browser.new_context = _async_val(context)

    with patch("omnisearch_mcp.scripts.capes_login.launch_async", return_value=browser):
        with patch("asyncio.sleep", _async_noop):
            await capes_login.run_login_flow(headless=True)

    env_file = tmp_path / ".env"
    assert env_file.exists()


@pytest.mark.asyncio
async def test_scite_login_flow(mock_playwright, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SCITE_EMAIL", "test@scite.ai")
    monkeypatch.setenv("SCITE_PASS", "password123")

    with patch("omnisearch_mcp.scripts.scite_login.launch_async", return_value=mock_playwright):
        await scite_login.run_login_flow(headless=True)

    env_file = tmp_path / ".env"
    assert env_file.exists()
    content = env_file.read_text()
    assert "SCITE_COOKIES=" in content
    assert "fake_cookie=abc" in content


@pytest.mark.asyncio
async def test_consensus_login_flow(mock_playwright_page, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONSENSUS_EMAIL", "test@consensus.app")
    monkeypatch.setenv("CONSENSUS_PASS", "password123")

    mock_playwright_page.url = "https://consensus.app/search/"

    browser = MagicMock()
    browser.close = _async_noop
    context = MagicMock()
    context.cookies = _async_val([{"name": "consensus_sess", "value": "xyz"}])
    context.new_page = _async_val(mock_playwright_page)
    browser.new_context = _async_val(context)

    with patch("omnisearch_mcp.scripts.consensus_login.launch_async", return_value=browser):
        await consensus_login.run_login_flow(headless=True)

    env_file = tmp_path / ".env"
    assert env_file.exists()
    content = env_file.read_text()
    assert "CONSENSUS_COOKIES=" in content
    assert "consensus_sess=xyz" in content


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
