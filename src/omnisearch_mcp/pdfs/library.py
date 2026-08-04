"""Local PDF library: extract text with pypdf, cache to JSON, search.

Index file lives at ``<folder>/.pdf_index.json`` and is keyed by relative
path + mtime so re-indexing skips unchanged files.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PdfReadError

INDEX_FILENAME = ".pdf_index.json"
INDEX_VERSION = 1


@dataclass
class PdfEntry:
    path: str  # relative to library root
    mtime: float
    pages: int
    text: str
    title: str | None = None


@dataclass
class PdfMatch:
    path: str
    title: str | None
    pages: int
    snippets: list[str] = field(default_factory=list)


def _load_index(root: Path) -> dict[str, PdfEntry]:
    index_path = root / INDEX_FILENAME
    if not index_path.exists():
        return {}
    try:
        raw = json.loads(index_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if raw.get("version") != INDEX_VERSION:
        return {}
    out: dict[str, PdfEntry] = {}
    for path, e in (raw.get("entries") or {}).items():
        try:
            out[path] = PdfEntry(
                path=path,
                mtime=float(e["mtime"]),
                pages=int(e["pages"]),
                text=str(e.get("text", "")),
                title=e.get("title"),
            )
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _save_index(root: Path, entries: dict[str, PdfEntry]) -> None:
    payload = {
        "version": INDEX_VERSION,
        "entries": {
            path: {
                "mtime": e.mtime,
                "pages": e.pages,
                "text": e.text,
                "title": e.title,
            }
            for path, e in entries.items()
        },
    }
    (root / INDEX_FILENAME).write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def _extract_pdf(path: Path) -> tuple[str, int, str | None]:
    reader = PdfReader(str(path))
    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    text = "\n".join(pages)
    title = None
    try:
        meta = reader.metadata or {}
        title = (meta.get("/Title") or "").strip() or None
    except Exception:
        title = None
    return text, len(reader.pages), title


def index_library(folder_path: str, force: bool = False) -> dict[str, Any]:
    root = Path(folder_path).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    existing = {} if force else _load_index(root)
    new_entries: dict[str, PdfEntry] = dict(existing)
    pdfs = sorted(p for p in root.rglob("*.pdf") if p.is_file())

    indexed = 0
    skipped = 0
    failed: list[dict[str, str]] = []

    for pdf in pdfs:
        rel = str(pdf.relative_to(root))
        mtime = pdf.stat().st_mtime
        prev = new_entries.get(rel)
        if prev and abs(prev.mtime - mtime) < 1e-6 and not force:
            skipped += 1
            continue
        try:
            text, pages, title = _extract_pdf(pdf)
        except (PdfReadError, OSError, Exception) as exc:
            failed.append({"path": rel, "error": str(exc)})
            continue
        new_entries[rel] = PdfEntry(
            path=rel, mtime=mtime, pages=pages, text=text, title=title
        )
        indexed += 1

    on_disk = {str(p.relative_to(root)) for p in pdfs}
    new_entries = {k: v for k, v in new_entries.items() if k in on_disk}

    _save_index(root, new_entries)
    return {
        "root": str(root),
        "indexed": indexed,
        "skipped": skipped,
        "total": len(new_entries),
        "failed": failed,
    }


def _snippets(text: str, query: str, context: int, max_snippets: int = 3) -> list[str]:
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    out: list[str] = []
    for m in pattern.finditer(text):
        start = max(0, m.start() - context)
        end = min(len(text), m.end() + context)
        snippet = re.sub(r"\s+", " ", text[start:end]).strip()
        if start > 0:
            snippet = "…" + snippet
        if end < len(text):
            snippet = snippet + "…"
        out.append(snippet)
        if len(out) >= max_snippets:
            break
    return out


def search_library(
    folder_path: str,
    query: str,
    max_results: int = 10,
    context_chars: int = 300,
) -> list[dict[str, Any]]:
    root = Path(folder_path).expanduser().resolve()
    entries = _load_index(root)
    if not entries:
        raise FileNotFoundError(
            f"No PDF index found in {root}. Run index_pdf_library first."
        )
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    scored: list[tuple[int, PdfEntry, list[str]]] = []
    for entry in entries.values():
        if not entry.text:
            continue
        matches = pattern.findall(entry.text)
        if not matches:
            continue
        snippets = _snippets(entry.text, query, context_chars)
        scored.append((len(matches), entry, snippets))
    scored.sort(key=lambda x: x[0], reverse=True)
    out: list[dict[str, Any]] = []
    for hits, entry, snippets in scored[:max_results]:
        out.append(
            {
                "path": str(root / entry.path),
                "relative_path": entry.path,
                "title": entry.title,
                "pages": entry.pages,
                "match_count": hits,
                "snippets": snippets,
            }
        )
    return out


def read_pdf(path: str, max_chars: int = 20000) -> dict[str, Any]:
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise FileNotFoundError(f"PDF not found: {p}")
    text, pages, title = _extract_pdf(p)
    truncated = len(text) > max_chars
    return {
        "path": str(p),
        "title": title,
        "pages": pages,
        "characters": len(text),
        "truncated": truncated,
        "text": text[:max_chars],
    }
