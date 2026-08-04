# AGENTS.md

## Project Overview
`omnisearch-mcp` is a FastMCP server exposing tools for searching academic papers across multiple search providers (IEEE Xplore, arXiv, ACM, CrossRef, Semantic Scholar, CORE, Scite.ai, Consensus.app) and local PDF libraries.

---

## Agent Usage & Error Recovery Protocol

### 1. How to Use MCP Tools
- Use `search_all` to search all academic sources in parallel.
- Use targeted tools (`search_ieee`, `search_scite`, `search_consensus`, `search_arxiv`, `search_pdf_library`) for provider-specific queries.

### 2. What to do when Cookies / Auth Expire
If an MCP tool returns an authentication or expired cookie error (e.g. `SCITE_COOKIES is not set or expired`, `IEEEKeyMissingError`, `401 Unauthorized`, or `302 Redirect`):

1. **Do NOT edit source code.**
2. **Run the corresponding login script** via terminal to refresh cookies in `.env`:
   - **Scite.ai:** `uv run omnisearch-scite-login --headless`
   - **Consensus.app:** `uv run omnisearch-consensus-login --headless`
   - **CAPES / IEEE:** `uv run omnisearch-capes-login --headless`
3. **Retry the MCP tool call immediately.** The server dynamically reloads `.env` (`get_config()`) on every request without requiring a server restart.

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
