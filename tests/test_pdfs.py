from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfWriter

from omnisearch_mcp.pdfs.library import (
    index_library,
    read_pdf,
    search_library,
)


def _make_pdf(path: Path, text: str, title: str | None = None) -> None:
    """Create a minimal text-bearing PDF using reportlab if available, else pypdf blank."""
    try:
        from reportlab.pdfgen import canvas  # type: ignore
    except ImportError:
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        with open(path, "wb") as f:
            writer.write(f)
        return
    c = canvas.Canvas(str(path))
    if title:
        c.setTitle(title)
    y = 800
    for line in text.split("\n"):
        c.drawString(72, y, line)
        y -= 14
    c.showPage()
    c.save()


def test_index_and_search(tmp_path: Path):
    pytest.importorskip("reportlab", reason="reportlab needed to build text PDFs")

    a = tmp_path / "a.pdf"
    b = tmp_path / "sub" / "b.pdf"
    b.parent.mkdir(parents=True)
    _make_pdf(a, "Quantum entanglement enables novel cryptographic protocols.", "A")
    _make_pdf(b, "Reinforcement learning agents learn from rewards.", "B")

    result = index_library(str(tmp_path))
    assert result["indexed"] == 2
    assert result["total"] == 2
    assert (tmp_path / ".pdf_index.json").exists()

    # Re-index without changes => all skipped
    result2 = index_library(str(tmp_path))
    assert result2["indexed"] == 0
    assert result2["skipped"] == 2

    matches = search_library(str(tmp_path), "cryptographic")
    assert len(matches) == 1
    assert matches[0]["relative_path"] == "a.pdf"
    assert matches[0]["snippets"]
    assert "cryptographic" in matches[0]["snippets"][0].lower()


def test_corrupt_pdf_indexing(tmp_path: Path):
    corrupt = tmp_path / "bad.pdf"
    corrupt.write_bytes(b"THIS IS NOT A VALID PDF CONTENT")

    result = index_library(str(tmp_path))
    assert len(result["failed"]) == 1
    assert result["failed"][0]["path"] == "bad.pdf"


def test_read_pdf(tmp_path: Path):
    pytest.importorskip("reportlab", reason="reportlab needed to build text PDFs")

    pdf_path = tmp_path / "doc.pdf"
    _make_pdf(pdf_path, "First line of text.\nSecond line of text.", "Doc Title")

    data = read_pdf(str(pdf_path))
    assert data["path"] == str(pdf_path.resolve())
    assert data["title"] == "Doc Title"
    assert data["pages"] >= 1
    assert "First line" in data["text"]


def test_search_without_index(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        search_library(str(tmp_path), "anything")


def test_index_nonexistent_dir(tmp_path: Path):
    missing = tmp_path / "nope"

    with pytest.raises(NotADirectoryError):
        index_library(str(missing))


def test_read_pdf_missing(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        read_pdf(str(tmp_path / "missing.pdf"))
