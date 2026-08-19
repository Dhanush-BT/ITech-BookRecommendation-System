"""
Low level PDF access layer. Text extraction is backed by pypdf, which -
unlike pdfplumber's rich per-page layout object model (chars/rects/images) -
extracts plain text directly and stays flat in memory even on 900+ page
books (benchmarked on a real 944-page book in this project: pypdf did the
full document in ~29s / ~120MB peak vs pdfplumber's 170s+ / multiple GB).
pdfplumber is kept only as an optional dependency for the font-size-based
heading fallback (extractors/heading_detector.py), which is rarely invoked
and only ever touches the first ~40 pages of a book.

Pages are extracted lazily and cached per-page (not per-document-wide-scan),
so asking for 60 pages of a 900-page book costs ~60 page extractions, not
900. A path-keyed registry (get_document) also ensures every stage of the
pipeline that touches the same file shares one cache instead of re-opening
and re-extracting it from scratch.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from pypdf import PdfReader as _PypdfReader

from utils.logger import log


@dataclass
class PageText:
    page_number: int          # 1-indexed, matches PDF viewer page number
    text: str
    char_count: int = 0
    lines: List[str] = field(default_factory=list)


class PDFDocument:
    """Lazily extracts and caches page text, one page at a time, so partial
    scans (e.g. the first 60 pages of a 900-page book) stay cheap."""

    def __init__(self, path: str):
        self.path = path
        self._page_cache: Dict[int, PageText] = {}
        self._num_pages: Optional[int] = None
        self._bookmarks = None
        self._reader = None  # lazily opened pypdf reader, kept for the object's lifetime

    def _pdf(self):
        if self._reader is None:
            self._reader = _PypdfReader(self.path)
        return self._reader

    def close(self):
        self._reader = None

    @property
    def num_pages(self) -> int:
        if self._num_pages is None:
            self._num_pages = len(self._pdf().pages)
        return self._num_pages

    def _extract_page(self, page_number: int) -> PageText:
        """page_number is 1-indexed."""
        if page_number in self._page_cache:
            return self._page_cache[page_number]
        try:
            page = self._pdf().pages[page_number - 1]
            text = page.extract_text() or ""
        except Exception as e:
            log(f"Page {page_number} extraction failed in {self.path}: {e}", "WARN")
            text = ""
        lines = [l for l in text.split("\n") if l.strip()]
        pt = PageText(page_number=page_number, text=text, char_count=len(text), lines=lines)
        self._page_cache[page_number] = pt
        return pt

    def get_pages(self, start: int = 1, end: Optional[int] = None) -> List[PageText]:
        """1-indexed inclusive page range. Only the requested pages are
        extracted (and only once - subsequent calls reuse the cache)."""
        total = self.num_pages
        end = total if end is None else min(end, total)
        start = max(1, start)
        return [self._extract_page(pn) for pn in range(start, end + 1)]

    def bookmarks(self):
        """Return pypdf outline (bookmarks) flattened as (title, page_number) tuples, or []."""
        if self._bookmarks is not None:
            return self._bookmarks
        result = []
        try:
            reader = _PypdfReader(self.path)
            outline = reader.outline if hasattr(reader, "outline") else []

            def walk(items):
                for item in items:
                    if isinstance(item, list):
                        walk(item)
                    else:
                        try:
                            page_idx = reader.get_destination_page_number(item)
                            result.append((str(item.title), page_idx + 1))
                        except Exception:
                            continue
            walk(outline)
        except Exception as e:
            log(f"No usable bookmarks in {self.path}: {e}", "WARN")
            result = []
        self._bookmarks = result
        return result

    def full_text(self, start: int = 1, end: Optional[int] = None) -> str:
        return "\n".join(p.text for p in self.get_pages(start, end))


_DOCUMENT_REGISTRY: Dict[str, "PDFDocument"] = {}


def get_document(path: str) -> PDFDocument:
    """Path-keyed cache so every pipeline stage that touches the same PDF
    (metadata, TOC, page-mapping, chunking) shares one page-text cache
    instead of re-extracting the file from scratch each time."""
    import os
    key = os.path.abspath(path)
    if key not in _DOCUMENT_REGISTRY:
        _DOCUMENT_REGISTRY[key] = PDFDocument(path)
    return _DOCUMENT_REGISTRY[key]
