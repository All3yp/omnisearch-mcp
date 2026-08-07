"""Environment-based configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    ieee_api_key: str | None
    contact_email: str
    user_agent: str
    capes_proxy_url: str | None
    ieee_cookies: str | None
    semantic_scholar_api_key: str | None
    core_api_key: str | None
    scite_cookies: str | None
    consensus_cookies: str | None
    serpapi_api_key: str | None = None

    @classmethod
    def from_env(cls) -> "Config":
        contact = os.getenv("CONTACT_EMAIL", "anonymous@example.com")
        return cls(
            ieee_api_key=os.getenv("IEEE_XPLORE_API_KEY") or None,
            contact_email=contact,
            user_agent=(
                f"omnisearch-mcp/0.1 "
                f"(+https://github.com/all3yp/omnisearch-mcp; "
                f"mailto:{contact})"
            ),
            capes_proxy_url=os.getenv("CAPES_PROXY_URL") or None,
            ieee_cookies=os.getenv("IEEE_COOKIES") or None,
            semantic_scholar_api_key=os.getenv("SEMANTIC_SCHOLAR_API_KEY") or None,
            core_api_key=os.getenv("CORE_API_KEY") or None,
            scite_cookies=os.getenv("SCITE_COOKIES") or None,
            consensus_cookies=os.getenv("CONSENSUS_COOKIES") or None,
            serpapi_api_key=os.getenv("SERPAPI_API_KEY") or None,
        )


def get_config() -> Config:
    load_dotenv(override=True)
    return Config.from_env()


CONFIG = Config.from_env()
