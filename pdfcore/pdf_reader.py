"""Low-level lazy, per-page-cached PDF text extraction layer, pypdf-backed.

One PDFDocument per file path; use get_document() to reuse the same instance
across the pipeline instead of re-opening/re-parsing the same PDF repeatedly.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional

import pypdf

from utils.logger import log


@dataclass
class PageText:
    page_number: int  # 0-indexed
    text: str


class PDFDocument:
    def __init__(self, path: str):
        self.path = path
        self._reader: Optional[pypdf.PdfReader] = None
        self._page_cache: Dict[int, str] = {}
        self.num_pages = 0
        self._load()

    def _load(self) -> None:
        try:
            self._reader = pypdf.PdfReader(self.path, strict=False)
            self.num_pages = len(self._reader.pages)
        except Exception as exc:  # malformed PDFs are common in a 61-book corpus
            log(f"WARNING: failed to open {self.path}: {exc}")
            self._reader = None
            self.num_pages = 0

    @property
    def metadata(self):
        if self._reader is None:
            return {}
        try:
            return dict(self._reader.metadata or {})
        except Exception:
            return {}

    def get_page_text(self, page_index: int) -> str:
        """0-indexed page access, cached."""
        if page_index in self._page_cache:
            return self._page_cache[page_index]
        text = ""
        if self._reader is not None and 0 <= page_index < self.num_pages:
            try:
                text = self._reader.pages[page_index].extract_text() or ""
            except Exception as exc:
                log(f"WARNING: failed to extract page {page_index} of {self.path}: {exc}")
                text = ""
        self._page_cache[page_index] = text
        return text

    def get_pages(self, start: int, end: int) -> List[PageText]:
        """Inclusive 0-indexed page range."""
        end = min(end, self.num_pages - 1)
        return [PageText(i, self.get_page_text(i)) for i in range(max(0, start), end + 1)]

    def full_text(self, start: int = 0, end: Optional[int] = None) -> str:
        """Concatenated text for an inclusive 0-indexed page range."""
        if end is None:
            end = self.num_pages - 1
        return "\n".join(p.text for p in self.get_pages(start, end))


_REGISTRY: Dict[str, PDFDocument] = {}


def get_document(path: str) -> PDFDocument:
    if path not in _REGISTRY:
        _REGISTRY[path] = PDFDocument(path)
    return _REGISTRY[path]
