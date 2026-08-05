# AGENTS.md

## Project Overview
`omnisearch-mcp` is a FastMCP server exposing tools for searching academic papers across multiple search providers (IEEE Xplore, arXiv, ACM, CrossRef, Semantic Scholar, CORE, Scite.ai, Consensus.app) and local PDF libraries.

---

## Agent Usage & Error Recovery Protocol

### 1. How to Use MCP Tools
- Use `search_all` to search all academic sources in parallel.
- Use targeted tools (`search_ieee`, `search_scite`, `search_consensus`, `search_arxiv`, `search_pdf_library`) for provider-specific queries.

### 2. What to do when Cookies / Auth Expire
If an MCP tool returns `auth_required: true`, expired-cookie text, `IEEEKeyMissingError`, `401 Unauthorized`, `403 Forbidden`, a login redirect, or HTML instead of JSON:

1. **Do NOT edit source code.**
2. **Do NOT retry the same provider in a loop.** Stop, report the auth block, and wait for human relogin.
3. Ask the human to run the command returned by the tool's `command` field. Defaults:
   - **CAPES / IEEE (highest priority):** `uv run omnisearch-capes-login` (visible browser recommended; use `--headless` only if it is known to work)
   - **Scite.ai:** `uv run omnisearch-scite-login`
   - **Consensus.app:** `uv run omnisearch-consensus-login`
4. Wait until the login script reports success. The script persists browser state in `.omnisearch/sessions/` and writes derived cookies to `.env`.
5. Retry the MCP tool **once**. If `auth_required: true` persists, stop and ask the human to relogin visibly/manual-complete MFA/CAPTCHA/SSO.

The server dynamically reloads `.env` (`get_config()`) on every request without requiring a server restart.

---

## Commands

### Running the MCP Server
```bash
uv run omnisearch-mcp
```

### Running Tests
```bash
uv run --group dev pytest
```

### Manual / Headless Login Scripts
```bash
uv run omnisearch-login-all [--headless]
uv run omnisearch-capes-login [--headless]
uv run omnisearch-scite-login [--headless]
uv run omnisearch-consensus-login [--headless]
```

---

## Environment Variables (.env)
- `CAFE_INSTITUTION_ID`, `CAFE_USERNAME`, `CAFE_PASSWORD`: CAFe CAPES login credentials.
- `SCITE_EMAIL`, `SCITE_PASS`: Credentials for Scite.ai automation.
- `CONSENSUS_EMAIL`, `CONSENSUS_PASS`: Credentials for Consensus.app automation.
- `PLAYWRIGHT_BROWSER_PATH`: Optional custom browser binary path (e.g., Brave, Chrome).
- `CAPES_PROXY_URL`, `IEEE_COOKIES`, `SCITE_COOKIES`, `CONSENSUS_COOKIES`: Auto-populated by login scripts.

---

## Architecture
- `src/omnisearch_mcp/server.py`: FastMCP server entry point exposing tools.
- `src/omnisearch_mcp/config.py`: Configuration module with dynamic `.env` reloading (`get_config()`).
- `src/omnisearch_mcp/sources/`: Provider-specific HTTP client search adapters.
- `src/omnisearch_mcp/scripts/`: Browser automation login scripts (Playwright & CloakBrowser).
- `src/omnisearch_mcp/pdfs/`: Local PDF text extraction and indexing.
