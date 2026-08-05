"""Tests for utility functions."""
from __future__ import annotations

from omnisearch_mcp.utils import extract_doi, dedupe_papers, paper_unique_key


def test_extract_doi_from_url():
    assert extract_doi("https://doi.org/10.1234/test.2024") == "10.1234/test.2024"


def test_extract_doi_from_text():
    assert extract_doi("See DOI: 10.1000/xyz123 for details") == "10.1000/xyz123"


def test_extract_doi_with_trailing_punctuation():
    assert extract_doi("Check 10.1234/test.") == "10.1234/test"
    assert extract_doi("(10.1234/test)") == "10.1234/test"


def test_extract_doi_not_found():
    assert extract_doi("no doi here") is None
    assert extract_doi("") is None
    assert extract_doi(None) is None


def test_paper_unique_key_doi():
    paper = {"doi": "10.1234/test", "title": "Title", "authors": "Author"}
    assert paper_unique_key(paper) == "doi:10.1234/test"


def test_paper_unique_key_title_authors():
    paper = {"doi": "", "title": "Test Title", "authors": "John Doe"}
    assert paper_unique_key(paper) == "title:test title|authors:john doe"


def test_paper_unique_key_fallback_id():
    paper = {"doi": "", "title": "", "paper_id": "12345"}
    assert paper_unique_key(paper) == "id:12345"


def test_dedupe_papers_by_doi():
    papers = [
        {"doi": "10.1234/a", "title": "Paper A"},
        {"doi": "10.1234/a", "title": "Paper A (duplicate)"},
        {"doi": "10.1234/b", "title": "Paper B"},
    ]
    deduped = dedupe_papers(papers)
    assert len(deduped) == 2
    assert deduped[0]["doi"] == "10.1234/a"
    assert deduped[1]["doi"] == "10.1234/b"


def test_dedupe_papers_by_title():
    papers = [
        {"doi": "", "title": "Same Title", "authors": "Author"},
        {"doi": "", "title": "Same Title", "authors": "Author"},
        {"doi": "", "title": "Different Title", "authors": "Author"},
    ]
    deduped = dedupe_papers(papers)
    assert len(deduped) == 2


def test_dedupe_preserves_order():
    papers = [
        {"doi": "10.1234/a", "title": "First"},
        {"doi": "10.1234/b", "title": "Second"},
        {"doi": "10.1234/c", "title": "Third"},
    ]
    deduped = dedupe_papers(papers)
    assert [p["title"] for p in deduped] == ["First", "Second", "Third"]


def test_paper_unique_key_handles_author_lists():
    paper = {"doi": "", "title": "Test Title", "authors": ["Ada", "Alan"]}
    assert paper_unique_key(paper) == "title:test title|authors:ada; alan"


def test_dedupe_empty_list():
    assert dedupe_papers([]) == []
