---
name: omnisearch-mcp
description: Use Omnisearch MCP to find academic literature, retrieve normalized paper metadata, resolve legal open-access PDFs, and search local PDF libraries.
---

# Omnisearch MCP Consumer Guide

Use this skill when research requires papers, citations, DOI metadata, open-access
PDF links, or local PDF-library evidence. The MCP returns data only. It does not
create subagents, run a synthesis workflow, or call a `StructuredOutput` tool.
The calling agent is responsible for interpreting results and producing its own
final response in the format required by its orchestration environment.

## Research Workflow

1. Translate the research question into a focused search query. Include the
   relevant subject, method, population, domain, or venue.
2. Start with `search_all(query, max_results_each=5)` for broad discovery.
3. Use a provider-specific search when coverage matters: `search_ieee` for IEEE,
   `search_acm` for ACM, `search_arxiv` for preprints, and `search_crossref` for
   broad publisher metadata.
4. Deduplicate by DOI first. When DOI is absent, compare normalized title and
   authors. `search_all` already returns a cross-provider deduplicated `papers`
   list, while source-specific searches do not.
5. Verify a candidate DOI with `get_doi_metadata(doi)` when accuracy is important.
6. Use `resolve_oa_url(doi)` before requesting a PDF. Only use `download_paper`
   or `read_paper_content` when the article is necessary to answer the question.
7. Cite only metadata or full text actually returned by the MCP. State when a
   conclusion is based only on title or abstract metadata.

## Tool Contract

All search tools accept `query: str` and a positive result limit. Defaults are
10 unless stated otherwise.

| Tool | Purpose | Important limits and response |
|---|---|---|
| `search_all(query, max_results_each=5)` | Runs IEEE, arXiv, ACM, Semantic Scholar, CORE, Scite, and Consensus concurrently. | Returns per-source sections, deduplicated `papers`, and `total`. Each source has a 15-second timeout. |
| `search_ieee(query, max_results=10)` | Searches IEEE Xplore through the official API or the authenticated CAPES browser session. | Official API limit: 200. Browser results are paginated and continue until `max_results` is reached or IEEE has no next page. |
| `search_arxiv(query, max_results=10)` | Searches public arXiv. | Limit: 50. Retries 429/503 twice with backoff. |
| `search_acm(query, max_results=10)` | Searches ACM metadata through CrossRef member 320. | Limit: 50. |
| `search_crossref(query, max_results=10)` | Searches CrossRef metadata. | Limit: 50. |
| `search_semantic_scholar(query, max_results=10)` | Searches Semantic Scholar. | Requires configured API key when the provider requires one. |
| `search_core(query, max_results=10)` | Searches CORE. | Requires `CORE_API_KEY`. |
| `search_scite(query, max_results=10)` | Searches Scite.ai. | Requires a current logged-in session. |
| `search_consensus(query, max_results=10)` | Searches Consensus.app. | Requires a current logged-in session. |
| `get_doi_metadata(doi)` | Fetches normalized CrossRef metadata for one DOI. | Returns an error when no record exists. |
| `resolve_oa_url(doi)` | Finds an open-access PDF URL using Unpaywall. | Does not download the file. |
| `download_paper(doi, title='', pdf_url=None, save_path='./downloads', use_scihub=False)` | Downloads a paper through configured fallbacks. | Keep `use_scihub=False` unless explicitly authorized and legally appropriate. |
| `read_paper_content(doi, title='', pdf_url=None, save_path='./downloads', max_chars=50000, use_scihub=False)` | Downloads then extracts PDF text. | Treat extracted text as source material; do not claim content not present in it. |
| `index_pdf_library(folder_path, force=False)` | Indexes PDFs in a local directory. | Creates or updates the local index. |
| `search_pdf_library(folder_path, query, max_results=10, context_chars=300)` | Searches indexed local PDF text. | Returns ranked snippets. |
| `read_pdf_text(path, max_chars=20000)` | Extracts text from one local PDF. | Returns truncated text. |

## Search Result Shape

Search results contain normalized paper dictionaries with fields such as:

```text
source, title, authors, year, venue, doi, url, pdf_url, abstract, identifiers
```

Fields may be absent or null. Do not invent authors, a venue, a DOI, an abstract,
or full-text claims when a provider omitted them.

## Authentication And Failure Handling

An authenticated provider can return:

```json
{
  "auth_required": true,
  "provider": "ieee",
  "action": "human_relogin_required",
  "command": "uv run omnisearch-capes-login --headless",
  "results": []
}
```

When `auth_required` is true, or a provider returns login HTML, `401`, `403`, or
expired-cookie evidence:

1. Do not modify MCP source code or retry that provider in a loop.
2. Tell the human which `command` to run. Prefer visible login without
   `--headless` for CAPES/IEEE because MFA, CAPTCHA, and SSO may require it.
3. Continue research with unaffected sources.
4. Retry the blocked provider once after the human confirms login succeeded.
5. If it still fails, report the authentication block and exclude that source.

For `search_all`, read `auth_required_sources` and inspect each source section;
successful source results remain usable even when other providers fail.

## Synthesis Requirements

After tool calls, synthesize the returned data in the caller's required format.
When an orchestration workflow requires structured output, the calling agent must
invoke that workflow's `StructuredOutput` mechanism itself after gathering MCP
results. Never assume the MCP performs that final call.

Include the search query, sources searched, selected papers, and evidence limits
in research-oriented output. Report missing access, empty results, rate limits,
and metadata-only limitations instead of silently treating them as negative
findings.

## Confidentiality

Never expose `.env` values, browser storage state, cookies, tokens, passwords, or
session files. These are implementation credentials, not research output.