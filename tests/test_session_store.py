from __future__ import annotations

import asyncio
from pathlib import Path

import json
import time

from omnisearch_mcp.scripts.session_store import (
    context_options,
    cookie_header,
    dotenv_quote,
    persisted_cookie_header,
    save_storage_state,
    storage_state_path,
    update_env_values,
)


class FakeContext:
    def __init__(self) -> None:
        self.saved_path: str | None = None

    async def storage_state(self, path: str) -> None:
        self.saved_path = path
        Path(path).write_text('{"cookies": []}', encoding="utf-8")


def test_cookie_header_skips_empty_names():
    cookies = [
        {"name": "session", "value": "abc"},
        {"name": "", "value": "ignored"},
        {"name": "token", "value": "xyz"},
    ]
    assert cookie_header(cookies) == "session=abc; token=xyz"


def test_dotenv_quote_escapes_problematic_values():
    assert dotenv_quote("a'b\\c") == "'a\\'b\\\\c'"


def test_update_env_values_replaces_and_appends(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("A=1\nCOOKIE='old'\n", encoding="utf-8")
    update_env_values(env_path, {"COOKIE": "a=b; c=d", "NEW": "value"})
    content = env_path.read_text(encoding="utf-8")
    assert "A=1" in content
    assert "COOKIE='a=b; c=d'" in content
    assert "NEW='value'" in content


def test_context_options_uses_existing_storage_state(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNISEARCH_SESSION_DIR", str(tmp_path))
    path = storage_state_path("scite")
    path.write_text('{"cookies": []}', encoding="utf-8")
    assert context_options("scite") == {"storage_state": str(path)}


def test_save_storage_state_writes_provider_file(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNISEARCH_SESSION_DIR", str(tmp_path))
    context = FakeContext()
    path = asyncio.run(save_storage_state(context, "consensus"))
    assert path.exists()
    assert context.saved_path == str(path)


def test_persisted_cookie_header_keeps_session_cookies(tmp_path, monkeypatch):
    """Playwright uses expires == -1 to mean 'session cookie, no expiry date'.

    These are exactly the cookies IEEE/Shibboleth/ezproxy rely on for an
    authenticated session (JSESSIONID, ezproxy, shib_idp_session, etc).
    Treating -1 as "already expired" silently drops them, so every real
    search request goes out unauthenticated even right after a successful
    login.
    """
    monkeypatch.setenv("OMNISEARCH_SESSION_DIR", str(tmp_path))
    path = storage_state_path("capes_ieee")
    future = time.time() + 3600
    past = time.time() - 3600
    state = {
        "cookies": [
            {"name": "JSESSIONID", "value": "sessval", "expires": -1},
            {"name": "ezproxy", "value": "ezval", "expires": -1},
            {"name": "AWSALB", "value": "albval", "expires": future},
            {"name": "old_token", "value": "oldval", "expires": past},
        ]
    }
    path.write_text(json.dumps(state), encoding="utf-8")

    header = persisted_cookie_header("capes_ieee")

    assert "JSESSIONID=sessval" in header
    assert "ezproxy=ezval" in header
    assert "AWSALB=albval" in header
    assert "old_token" not in header
