from omnisearch_mcp.models import Paper


def test_paper_to_dict():
    paper = Paper(
        source="arxiv",
        title="Test Paper",
        authors=["Author One", "Author Two"],
        year=2024,
        venue="Conference",
        doi="10.1234/test",
        url="https://example.com/test",
        pdf_url=None,
        abstract="Abstract content",
        identifiers={"arxiv": "2401.00001"}
    )
    d = paper.to_dict()
    assert d["source"] == "arxiv"
    assert d["title"] == "Test Paper"
    assert d["authors"] == ["Author One", "Author Two"]
    assert d["year"] == 2024
    assert d["venue"] == "Conference"
    assert d["doi"] == "10.1234/test"
    assert d["url"] == "https://example.com/test"
    assert "pdf_url" not in d  # None values excluded
    assert d["abstract"] == "Abstract content"
    assert d["identifiers"] == {"arxiv": "2401.00001"}


def test_paper_default_fields():
    paper = Paper(source="test", title="Minimal Paper")
    d = paper.to_dict()
    assert d == {"source": "test", "title": "Minimal Paper"}
