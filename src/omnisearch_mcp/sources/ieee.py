"""IEEE Xplore Metadata API adapter.

Docs: https://developer.ieee.org/docs/read/Metadata_API_details

Requires a free API key from https://developer.ieee.org/ (set IEEE_XPLORE_API_KEY).
The key only returns metadata + abstracts; full text still requires an
institutional or personal subscription.
"""
from __future__ import annotations

from html import unescape
from html.parser import HTMLParser
from typing import Any

import httpx
from cloakbrowser import launch_async
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from .. import config
from ..models import Paper
from ..scripts.session_store import context_options, persisted_cookie_header

API_URL = "https://ieeexploreapi.ieee.org/api/v1/search/articles"
IEEE_BASE_URL = "https://ieeexplore.ieee.org"
IEEE_BROWSER_RESULTS_PER_PAGE = 50
IEEE_ACCESS_DENIED_STATUS_CODES = {401, 403, 418}
IEEE_CAPES_TIMEOUT = 10.0


class IEEEKeyMissingError(RuntimeError):
    """Raised when IEEE auth/config is missing or expired."""

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message
            or "IEEE_XPLORE_API_KEY is not set, and no CAPES_PROXY_URL or IEEE_COOKIES "
            "are provided. Please authenticate with CAPES/IEEE or configure an IEEE key."
        )


def _raise_for_ieee_status(response: httpx.Response) -> None:
    if response.status_code in IEEE_ACCESS_DENIED_STATUS_CODES:
        raise IEEEKeyMissingError(
            f"IEEE access was denied with HTTP {response.status_code}. "
            "Please run 'uv run omnisearch-capes-login' and complete IEEE access manually."
        )
    response.raise_for_status()


def _to_paper(item: dict[str, Any]) -> Paper:
    authors_block = (item.get("authors") or {}).get("authors") or []
    authors = [a.get("full_name", "") for a in authors_block if a.get("full_name")]

    year_raw = item.get("publication_year")
    try:
        year = int(year_raw) if year_raw is not None else None
    except (TypeError, ValueError):
        year = None

    article_number = item.get("article_number")
    return Paper(
        source="ieee",
        title=(item.get("title") or "").strip(),
        authors=authors,
        year=year,
        venue=item.get("publication_title"),
        doi=item.get("doi"),
        url=item.get("html_url") or item.get("abstract_url"),
        pdf_url=item.get("pdf_url"),
        abstract=item.get("abstract"),
        identifiers={
            k: str(v)
            for k, v in {
                "article_number": article_number,
                "isbn": item.get("isbn"),
                "issn": item.get("issn"),
                "publisher": item.get("publisher"),
                "content_type": item.get("content_type"),
            }.items()
            if v
        },
    )


def _to_paper_frontend(item: dict[str, Any]) -> Paper:
    authors_block = item.get("authors") or []
    authors = [a.get("preferredName", "") for a in authors_block if a.get("preferredName")]

    year_raw = item.get("publicationYear")
    try:
        year = int(year_raw) if year_raw is not None else None
    except (TypeError, ValueError):
        year = None

    article_number = item.get("articleNumber")
    url = item.get("documentLink")
    if url and not url.startswith("http"):
        url = f"https://ieeexplore.ieee.org{url}"

    pdf_url = item.get("pdfLink")
    if pdf_url and not pdf_url.startswith("http"):
        pdf_url = f"https://ieeexplore.ieee.org{pdf_url}"

    return Paper(
        source="ieee",
        title=(item.get("title") or "").strip(),
        authors=authors,
        year=year,
        venue=item.get("publicationTitle"),
        doi=item.get("doi"),
        url=url,
        pdf_url=pdf_url,
        abstract=item.get("abstract"),
        identifiers={
            k: str(v)
            for k, v in {
                "article_number": article_number,
                "publisher": item.get("publisher"),
                "content_type": item.get("contentType"),
            }.items()
            if v
        },
    )


def parse_ieee_response(payload: dict[str, Any]) -> list[Paper]:
    return [_to_paper(item) for item in (payload.get("articles") or [])]


def parse_ieee_frontend_response(payload: dict[str, Any]) -> list[Paper]:
    return [_to_paper_frontend(item) for item in (payload.get("records") or [])]


def _capes_search_payload(query: str, max_results: int) -> dict[str, Any]:
    return {
        "newsearch": True,
        "queryText": query,
        "returnType": "SEARCH",
        "rowsPerPage": max_results,
    }


def _raise_for_capes_response(response: httpx.Response) -> None:
    content_type = response.headers.get("content-type", "").lower()
    if response.is_redirect or response.status_code in IEEE_ACCESS_DENIED_STATUS_CODES:
        raise IEEEKeyMissingError(
            "CAPES/IEEE session is expired or unauthorized. Please run "
            "'uv run omnisearch-capes-login' and complete IEEE access manually."
        )
    if "json" not in content_type:
        raise IEEEKeyMissingError(
            "CAPES/IEEE search did not return JSON. Please run "
            "'uv run omnisearch-capes-login' and complete IEEE access manually."
        )
    response.raise_for_status()


async def search_ieee_with_capes_session(
    query: str,
    max_results: int,
    proxy_url: str,
    cookies: str,
    user_agent: str,
) -> list[Paper]:
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Cookie": cookies,
        "User-Agent": user_agent,
    }
    async with httpx.AsyncClient(follow_redirects=False, timeout=IEEE_CAPES_TIMEOUT) as client:
        response = await client.post(
            f"{proxy_url.rstrip('/')}/rest/search",
            headers=headers,
            json=_capes_search_payload(query, max_results),
        )
    _raise_for_capes_response(response)
    try:
        payload = response.json()
    except ValueError as exc:
        raise IEEEKeyMissingError(
            "CAPES/IEEE search returned invalid JSON. Please run "
            "'uv run omnisearch-capes-login' and complete IEEE access manually."
        ) from exc
    return parse_ieee_frontend_response(payload)


class IEEEAdvancedSearchParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str | None]] = []
        self._active_link: dict[str, str | None] | None = None
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attr_map = dict(attrs)
        href = attr_map.get("href") or ""
        if "/document/" not in href and "/abstract/document/" not in href:
            return
        self._active_link = {"href": href, "title": attr_map.get("aria-label") or attr_map.get("title")}
        self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._active_link is not None:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._active_link is None:
            return
        text = " ".join(part.strip() for part in self._text_parts if part.strip())
        if text and not self._active_link.get("title"):
            self._active_link["title"] = unescape(text)
        self.links.append(self._active_link)
        self._active_link = None
        self._text_parts = []


def parse_ieee_advanced_search_html(html: str, proxy_url: str, max_results: int) -> list[Paper]:
    parser = IEEEAdvancedSearchParser()
    parser.feed(html)
    papers: list[Paper] = []
    seen_document_ids: set[str] = set()
    ignored_titles = {"html", "pdf", "show more"}
    for link in parser.links:
        title = (link.get("title") or "").strip()
        href = link.get("href") or ""
        if not title or not href or title.lower() in ignored_titles:
            continue
        if "/citations" in href or "tabFilter=" in href:
            continue
        href_parts = [part for part in href.split("/") if part]
        try:
            document_id = href_parts[href_parts.index("document") + 1]
        except (ValueError, IndexError):
            continue
        if not document_id.isdigit() or document_id in seen_document_ids:
            continue
        seen_document_ids.add(document_id)
        url = f"{proxy_url.rstrip('/')}/document/{document_id}/"
        papers.append(Paper(source="ieee", title=title, url=url, identifiers={"article_number": document_id}))
        if len(papers) >= max_results:
            break
    return papers


def _append_unique_papers(
    papers: list[Paper],
    page_papers: list[Paper],
    max_results: int,
) -> None:
    seen_document_ids = {paper.identifiers.get("article_number") for paper in papers}
    for paper in page_papers:
        document_id = paper.identifiers.get("article_number")
        if document_id in seen_document_ids:
            continue
        papers.append(paper)
        seen_document_ids.add(document_id)
        if len(papers) >= max_results:
            return


async def search_ieee_with_browser(query: str, max_results: int, proxy_url: str) -> list[Paper]:
    browser = await launch_async(headless=False, humanize=True)
    context = await browser.new_context(**context_options("capes_ieee"))
    page = await context.new_page()
    try:
        await page.goto(f"{proxy_url.rstrip('/')}/search/advanced", wait_until="domcontentloaded", timeout=30_000)
        search_box = page.locator(
            'input[type="search"], input[placeholder*="Search" i], input[aria-label*="Search" i], input[name="queryText"], input[name="query"]'
        ).first
        if not await search_box.is_visible():
            await page.goto(f"{proxy_url.rstrip('/')}/search/advanced", wait_until="domcontentloaded", timeout=30_000)
            search_box = page.locator(
                'input[type="search"], input[placeholder*="Search" i], input[aria-label*="Search" i], input[name="queryText"], input[name="query"], textarea[name="queryText"]'
            ).first
        if not await search_box.is_visible():
            raise IEEEKeyMissingError("IEEE search box was not found in the CAPES browser session. Please run 'uv run omnisearch-capes-login' and complete IEEE access manually.")
        await search_box.fill(query)
        search_button = page.locator(
            'button[type="submit"], button[aria-label*="Search" i], input[type="submit"], [role="button"][aria-label*="Search" i]'
        ).first
        if await search_button.is_visible():
            await search_button.click()
        else:
            await search_box.press("Enter")
        try:
            await page.wait_for_url("**/search/**", timeout=15_000)
        except PlaywrightTimeoutError:
            pass
        try:
            await page.wait_for_selector('a[href*="/document/"]', timeout=30_000)
        except PlaywrightTimeoutError:
            pass
        if max_results > 25:
            items_per_page = page.get_by_role("button", name="Items Per Page")
            if await items_per_page.is_visible():
                await items_per_page.click()
                fifty_items = page.locator("button.dropdown-item", has_text="50").first
                if await fifty_items.is_visible():
                    await fifty_items.click()
                    try:
                        await page.wait_for_function(
                            """() => document.querySelectorAll('a[href*='/document/']').length >= 50""",
                            timeout=10_000,
                        )
                    except PlaywrightTimeoutError:
                        pass
        result_limit = max(1, max_results)
        papers: list[Paper] = []
        while len(papers) < result_limit:
            html = await page.content()
            _append_unique_papers(
                papers,
                parse_ieee_advanced_search_html(html, proxy_url, result_limit - len(papers)),
                result_limit,
            )
            if len(papers) >= result_limit:
                break

            next_page = page.locator(
                'button[aria-label*="Next" i], a[aria-label*="Next" i], button:has-text("Next")'
            ).first
            if not await next_page.is_visible() or await next_page.get_attribute("aria-disabled") == "true":
                break

            await next_page.click()
            try:
                await page.wait_for_function(
                    "previousHtml => document.documentElement.innerHTML !== previousHtml",
                    arg=html,
                    timeout=15_000,
                )
            except PlaywrightTimeoutError:
                break
        return papers
    finally:
        await browser.close()


async def search_ieee(query: str, max_results: int = 10) -> list[Paper]:
    cfg = config.get_config()
    if not cfg.ieee_api_key and not cfg.capes_proxy_url and not cfg.ieee_cookies:
        raise IEEEKeyMissingError()

    # 1. Use Official API if key is present
    if cfg.ieee_api_key:
        params = {
            "apikey": cfg.ieee_api_key,
            "querytext": query,
            "max_records": max(1, min(max_results, 200)),
            "format": "json",
        }
        async with httpx.AsyncClient(
            timeout=30.0, headers={"User-Agent": cfg.user_agent}
        ) as client:
            resp = await client.get(API_URL, params=params)
            _raise_for_ieee_status(resp)
            return parse_ieee_response(resp.json())

    proxy_url = cfg.capes_proxy_url or IEEE_BASE_URL
    cookies = persisted_cookie_header("capes_ieee") or cfg.ieee_cookies
    if cookies:
        return await search_ieee_with_capes_session(
            query, max_results, proxy_url, cookies, cfg.user_agent
        )

    # 2. Browser fallback is reserved for an existing CAPES browser session.
    return await search_ieee_with_browser(query, max_results, proxy_url)
