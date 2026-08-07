"""Persistent browser-session storage for login scripts.

Storage state files contain bearer-equivalent session secrets. Keep them local,
gitignored, and never print their contents.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

DEFAULT_SESSION_DIR = ".omnisearch/sessions"


def session_dir() -> Path:
    """Return the directory used for Playwright storage-state files."""
    configured = os.getenv("OMNISEARCH_SESSION_DIR")
    return Path(configured or DEFAULT_SESSION_DIR).expanduser()


def storage_state_path(provider: str) -> Path:
    """Return storage-state path for a provider name."""
    return session_dir() / f"{provider}.storage.json"


def context_options(provider: str) -> dict[str, str]:
    """Return Playwright context options that reuse persisted state when present."""
    path = storage_state_path(provider)
    if not path.exists():
        return {}
    return {"storage_state": str(path)}


async def save_storage_state(context: Any, provider: str) -> Path:
    """Persist Playwright browser context storage_state for future logins."""
    path = storage_state_path(provider)
    path.parent.mkdir(parents=True, exist_ok=True)
    await context.storage_state(path=str(path))
    return path


def cookie_header(cookies: Sequence[Mapping[str, Any]]) -> str:
    """Build an HTTP Cookie header from Playwright cookie dictionaries."""
    pairs = []
    for cookie in cookies:
        name = str(cookie.get("name") or "").strip()
        value = str(cookie.get("value") or "")
        if name:
            pairs.append(f"{name}={value}")
    return "; ".join(pairs)


def persisted_cookie_header(provider: str) -> str | None:
    """Return non-expired cookies from a provider's persisted browser state."""
    path = storage_state_path(provider)
    if not path.exists():
        return None

    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    now = time.time()
    cookies = [
        cookie
        for cookie in state.get("cookies", [])
        if _cookie_is_unexpired(cookie, now)
    ]
    header = cookie_header(cookies)
    return header or None


def _cookie_is_unexpired(cookie: Mapping[str, Any], now: float) -> bool:
    """Return True unless the cookie has a real, past expiry timestamp.

    Playwright's storage_state() represents session cookies (no expiry until
    the browser closes) with expires == -1, not a missing/falsy value. A
    naive `not cookie.get("expires")` check treats 0 the same as missing, but
    `cookie["expires"] > now` then evaluates `-1 > now` as False and drops
    the cookie as if it were expired. Session cookies are exactly the ones
    IEEE/Shibboleth/ezproxy rely on (JSESSIONID, ezproxy, shib_idp_session),
    so this silently strips authentication from every persisted session.
    """
    expires = cookie.get("expires")
    if expires is None or expires == -1:
        return True
    return expires > now


def dotenv_quote(value: str) -> str:
    """Quote a dotenv value without exposing or corrupting cookie characters."""
    escaped = value.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
    return f"'{escaped}'"


def update_env_values(env_path: Path, values: Mapping[str, str]) -> None:
    """Atomically update exact keys in a dotenv file."""
    existing_lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    remaining = dict(values)
    output_lines: list[str] = []

    for line in existing_lines:
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            output_lines.append(line)
            continue

        key = line.split("=", 1)[0].strip()
        if key in remaining:
            output_lines.append(f"{key}={dotenv_quote(remaining.pop(key))}")
        else:
            output_lines.append(line)

    for key, value in remaining.items():
        output_lines.append(f"{key}={dotenv_quote(value)}")

    env_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(env_path.parent or Path(".")),
        delete=False,
    ) as tmp:
        tmp.write("\n".join(output_lines) + "\n")
        tmp_path = Path(tmp.name)

    tmp_path.replace(env_path)


def storage_summary(cookies: Sequence[Mapping[str, Any]]) -> str:
    """Return non-secret cookie summary for logging."""
    domains = sorted({str(cookie.get("domain") or "unknown") for cookie in cookies})
    return f"{len(cookies)} cookies across {len(domains)} domains"
