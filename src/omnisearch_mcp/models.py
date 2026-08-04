"""Normalized data models shared across source adapters."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Paper:
    """Normalized representation of a research paper across sources."""

    source: str  # "ieee" | "arxiv" | "acm" | "crossref" | "pdf"
    title: str
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    url: str | None = None
    pdf_url: str | None = None
    abstract: str | None = None
    identifiers: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: v for k, v in d.items() if v not in (None, "", [], {})}
