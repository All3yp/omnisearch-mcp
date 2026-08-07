# SerpApi Google Scholar Plan

## Approved design

Use SerpApi's Google Scholar JSON endpoint through existing async `httpx` stack. Do not add `serpapi-python` dependency. Normalize `organic_results` into `Paper` records with source `google_scholar`; expose direct MCP tool; add source to `search_all` without letting absent credentials or provider failure stop other sources.

## Tasks

1. Add focused source and server tests. Run them and record expected red state before production code.
2. Add config, SerpApi adapter, direct tool, aggregate integration, and minimal docs. Run focused tests.
3. Review task scope and quality; delegate fixes if needed.
4. Run full validation and final branch review.

## Constraints

- Endpoint: `https://serpapi.com/search.json`; parameters include `engine=google_scholar`, `q`, `num`, `api_key`.
- Bound retry to 429 and transient 5xx. Honor numeric `Retry-After`; do not retry 401/403.
- `SERPAPI_API_KEY` must be optional and appended to `Config` with a default.
- Missing/failed Scholar must yield a clear Scholar section error and never block other `search_all` sources.
- Preserve existing uncommitted work and direct `search_ieee` contract.

## Ledger

| Task | Status | Validation / ruling |
| --- | --- | --- |
| Workspace verification | complete | User approved current dirty `main`; preserve existing work. |
| Test task | in progress | Pending failing SerpApi tests and red verification. |
| Integration task | pending | Blocked on red tests. |
| Task review | pending | Required after integration. |
| Full validation | pending | Use workspace `.venv` Python. |
| Final branch review | pending | Required before completion. |