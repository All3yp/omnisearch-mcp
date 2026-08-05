"""Utility functions for DOI extraction and paper deduplication."""
from __future__ import annotations

import re
from typing import Any

# DOI pattern: 10.XXXX/... (G25: named constant)
DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)


def extract_doi(text: str) -> str | None:
    """Extract DOI from text or URL.

    Args:
        text: String potentially containing a DOI.

    Returns:
        Cleaned DOI string or None if not found.
    """
    if not text:
        return None

    match = DOI_PATTERN.search(text)
    if not match:
        return None

    # Strip trailing punctuation (G19: explanatory variable)
    return match.group(0).rstrip(".,;)")


def normalize_key_part(value: Any) -> str:
    """Normalize scalar/list metadata into a stable dedup key part."""
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(str(item).strip() for item in value if item).lower()
    return str(value).strip().lower()


def paper_unique_key(paper: dict[str, Any]) -> str:
    """Generate a unique key for deduplication.

    Priority: DOI > title+authors > paper_id.

    Args:
        paper: Paper dictionary.

    Returns:
        Unique identifier string for deduplication.
    """
    doi = normalize_key_part(paper.get("doi"))
    if doi:
        return f"doi:{doi}"

    title = normalize_key_part(paper.get("title"))
    authors = normalize_key_part(paper.get("authors"))
    if title:
        return f"title:{title}|authors:{authors}"

    paper_id = normalize_key_part(paper.get("paper_id"))
    return f"id:{paper_id}"


def dedupe_papers(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove duplicate papers based on DOI, title+authors, or ID.

    Args:
        papers: List of paper dictionaries.

    Returns:
        Deduplicated list preserving original order.
    """
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()

    for paper in papers:
        key = paper_unique_key(paper)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(paper)

    return deduped
