"""Low-level lazy, per-page-cached PDF text extraction layer, pypdf-backed.

One PDFDocument per file path; use get_document() to reuse the same instance
across the pipeline instead of re-opening/re-parsing the same PDF repeatedly.
"""
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

import pypdf

from utils.logger import log

# Several PDFs in the corpus (Anton, Stewart, ...) use fonts whose f-ligature
# glyphs are encoded at the C0 control-code points 0x0B-0x0F instead of the
# Unicode ligature block, so pypdf hands them back as raw control chars in the
# middle of words ("di\x0berential", "de\x0cned", "in\rection", "\x0crst").
# Left alone these break tokenization, keyword overlap, fuzzy title matching
# and embedding quality alike -- and the Excel exporter later strips them,
# silently welding the word halves together ("dierential"). 0x0C (form feed)
# and 0x0D (CR) also carry real structural meaning, so a control code is only
# read as a ligature when a lowercase letter follows it (mid- or start-of-word);
# a page break / line ending is followed by whitespace or an uppercase heading.
_CTRL_LIGATURES = {
    "\x0b": "ff", "\x0c": "fi", "\x0d": "fl", "\x0e": "ffi", "\x0f": "ffl",
}
_CTRL_LIGATURE_RE = re.compile(r"[\x0b-\x0f](?=[a-z])")
_UNICODE_LIGATURES = {
    "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "ft", "ﬆ": "st",
}


def _normalize_ligatures(text: str) -> str:
    if not text:
        return text
    if _CTRL_LIGATURE_RE.search(text):
        text = _CTRL_LIGATURE_RE.sub(lambda m: _CTRL_LIGATURES[m.group(0)], text)
    for bad, good in _UNICODE_LIGATURES.items():
        if bad in text:
            text = text.replace(bad, good)
    return text


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
                text = _normalize_ligatures(self._reader.pages[page_index].extract_text() or "")
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
