"""Quick diagnostic tool to check auth status for all providers.

This is a lightweight check-only tool that does NOT perform login flows.
It validates current cookies/tokens against each provider's endpoints and
reports which providers are ready to use vs. which need relogin.

Usage:
    uv run omnisearch-check-auth
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx
from curl_cffi.requests import AsyncSession

from .. import config
from ..scripts.session_store import persisted_cookie_header


async def check_ieee_auth() -> dict[str, Any]:
    """Check IEEE/CAPES authentication status."""
    cfg = config.get_config()
    
    # Check if we have any credentials at all
    has_api_key = bool(cfg.ieee_api_key)
    has_capes = bool(cfg.capes_proxy_url and (
        persisted_cookie_header("capes_ieee") or cfg.ieee_cookies
    ))
    
    if has_api_key:
        # API key check: try a simple query
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://ieeexploreapi.ieee.org/api/v1/search/articles",
                    params={"apikey": cfg.ieee_api_key, "max_records": 1, "querytext": "test"}
                )
                if resp.status_code == 200:
                    return {
                        "provider": "IEEE",
                        "method": "API key",
                        "status": "✓ valid",
                        "ready": True,
                    }
                else:
                    return {
                        "provider": "IEEE",
                        "method": "API key",
                        "status": f"✘ HTTP {resp.status_code}",
                        "ready": False,
                        "command": "Check your IEEE_XPLORE_API_KEY value",
                    }
        except Exception as e:
            return {
                "provider": "IEEE",
                "method": "API key",
                "status": f"✘ error: {e}",
                "ready": False,
            }
    
    if has_capes:
        # CAPES proxy check: try a test search
        cookies = persisted_cookie_header("capes_ieee") or cfg.ieee_cookies
        proxy_url = cfg.capes_proxy_url
        
        try:
            headers = {
                "Accept": "application/json, text/plain, */*",
                "Cookie": cookies,
            }
            async with AsyncSession() as session:
                response = await session.post(
                    f"{proxy_url.rstrip('/')}/rest/search",
                    headers=headers,
                    json={
                        "newsearch": True,
                        "queryText": "machine learning",
                        "returnType": "SEARCH",
                        "rowsPerPage": 1,
                    },
                    impersonate="chrome124",
                    timeout=10.0,
                    allow_redirects=False,
                )
            
            content_type = (response.headers.get("content-type") or "").lower()
            is_redirect = response.status_code in (301, 302, 303, 307, 308)
            
            if is_redirect or response.status_code in (401, 403, 418):
                return {
                    "provider": "IEEE",
                    "method": "CAPES proxy",
                    "status": f"✘ session expired (HTTP {response.status_code})",
                    "ready": False,
                    "command": "uv run omnisearch-capes-login",
                }
            elif "json" not in content_type:
                return {
                    "provider": "IEEE",
                    "method": "CAPES proxy",
                    "status": "✘ session expired (non-JSON response)",
                    "ready": False,
                    "command": "uv run omnisearch-capes-login",
                }
            elif response.status_code == 200:
                return {
                    "provider": "IEEE",
                    "method": "CAPES proxy",
                    "status": "✓ valid",
                    "ready": True,
                }
            else:
                return {
                    "provider": "IEEE",
                    "method": "CAPES proxy",
                    "status": f"✘ HTTP {response.status_code}",
                    "ready": False,
                    "command": "uv run omnisearch-capes-login",
                }
        except Exception as e:
            return {
                "provider": "IEEE",
                "method": "CAPES proxy",
                "status": f"✘ error: {e}",
                "ready": False,
                "command": "uv run omnisearch-capes-login",
            }
    
    return {
        "provider": "IEEE",
        "method": "none",
        "status": "✘ no credentials configured",
        "ready": False,
        "command": "Set IEEE_XPLORE_API_KEY or run 'uv run omnisearch-capes-login'",
    }


async def check_scite_auth() -> dict[str, Any]:
    """Check Scite.ai authentication status."""
    cfg = config.get_config()
    cookies = persisted_cookie_header("scite") or cfg.scite_cookies
    
    if not cookies:
        return {
            "provider": "Scite.ai",
            "status": "✘ no cookies",
            "ready": False,
            "command": "uv run omnisearch-scite-login",
        }
    
    try:
        headers = {
            "User-Agent": cfg.user_agent,
            "Accept": "application/json",
            "Cookie": cookies,
        }
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(
                "https://scite.ai/api/search/papers",
                params={"q": "test", "size": 1},
                headers=headers,
            )
            
            if resp.status_code in (301, 302, 401, 403) or "login" in str(resp.url).lower():
                return {
                    "provider": "Scite.ai",
                    "status": "✘ session expired",
                    "ready": False,
                    "command": "uv run omnisearch-scite-login",
                }
            elif resp.status_code == 200:
                try:
                    resp.json()
                    return {
                        "provider": "Scite.ai",
                        "status": "✓ valid",
                        "ready": True,
                    }
                except Exception:
                    return {
                        "provider": "Scite.ai",
                        "status": "✘ invalid response",
                        "ready": False,
                        "command": "uv run omnisearch-scite-login",
                    }
            else:
                return {
                    "provider": "Scite.ai",
                    "status": f"✘ HTTP {resp.status_code}",
                    "ready": False,
                    "command": "uv run omnisearch-scite-login",
                }
    except Exception as e:
        return {
            "provider": "Scite.ai",
            "status": f"✘ error: {e}",
            "ready": False,
            "command": "uv run omnisearch-scite-login",
        }


async def check_consensus_auth() -> dict[str, Any]:
    """Check Consensus.app authentication status."""
    cfg = config.get_config()
    cookies = persisted_cookie_header("consensus") or cfg.consensus_cookies
    
    if not cookies:
        return {
            "provider": "Consensus.app",
            "status": "✘ no cookies",
            "ready": False,
            "command": "uv run omnisearch-consensus-login",
        }
    
    try:
        headers = {
            "User-Agent": cfg.user_agent,
            "Accept": "application/json",
            "Cookie": cookies,
        }
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(
                "https://consensus.app/api/v1/search/",
                params={"query": "test", "limit": 1},
                headers=headers,
            )
            
            if resp.status_code in (301, 302, 401, 403, 404) or "login" in str(resp.url).lower():
                return {
                    "provider": "Consensus.app",
                    "status": "✘ session expired",
                    "ready": False,
                    "command": "uv run omnisearch-consensus-login",
                }
            elif resp.status_code == 200:
                try:
                    resp.json()
                    return {
                        "provider": "Consensus.app",
                        "status": "✓ valid",
                        "ready": True,
                    }
                except Exception:
                    return {
                        "provider": "Consensus.app",
                        "status": "✘ invalid response",
                        "ready": False,
                        "command": "uv run omnisearch-consensus-login",
                    }
            else:
                return {
                    "provider": "Consensus.app",
                    "status": f"✘ HTTP {resp.status_code}",
                    "ready": False,
                    "command": "uv run omnisearch-consensus-login",
                }
    except Exception as e:
        return {
            "provider": "Consensus.app",
            "status": f"✘ error: {e}",
            "ready": False,
            "command": "uv run omnisearch-consensus-login",
        }


async def check_all_auth() -> list[dict[str, Any]]:
    """Check authentication for all providers concurrently."""
    results = await asyncio.gather(
        check_ieee_auth(),
        check_scite_auth(),
        check_consensus_auth(),
        return_exceptions=True,
    )
    
    output = []
    for result in results:
        if isinstance(result, Exception):
            output.append({
                "provider": "unknown",
                "status": f"✘ check failed: {result}",
                "ready": False,
            })
        else:
            output.append(result)
    
    return output


def main() -> None:
    """Entry point for omnisearch-check-auth command."""
    print("Checking authentication status for all providers...\n")
    
    results = asyncio.run(check_all_auth())
    
    ready_count = sum(1 for r in results if r.get("ready"))
    total_count = len(results)
    
    for result in results:
        provider = result.get("provider", "unknown")
        method = result.get("method")
        status = result.get("status", "unknown")
        command = result.get("command")
        
        if method:
            print(f"{provider} ({method}): {status}")
        else:
            print(f"{provider}: {status}")
        
        if command and not result.get("ready"):
            print(f"  → {command}")
        print()
    
    print(f"Summary: {ready_count}/{total_count} providers ready")
    
    if ready_count < total_count:
        print("\nRun the suggested commands above to refresh expired sessions.")
        exit(1)
    else:
        print("\nAll providers are authenticated and ready.")
        exit(0)


if __name__ == "__main__":
    main()
