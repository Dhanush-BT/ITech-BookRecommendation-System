"""Maps a TOC entry's printed page number to the real 0-indexed PDF page by
anchor-searching for the entry's title text near candidate pages, then
resolving a global offset (printed_page - 1 + offset = pdf_index) with a
light per-entry drift allowance for entries that anchor with high confidence."""
from collections import Counter
from dataclasses import dataclass
from typing import List, Optional, Tuple

from rapidfuzz import fuzz

from pdfcore.pdf_reader import PDFDocument
from extractors.toc_parser import TOCEntry
from utils.regex_patterns import normalize_text

_OFFSET_SEARCH_RANGE = range(-3, 46)
_ANCHOR_HEAD_CHARS = 600
_GLOBAL_MATCH_THRESHOLD = 70.0
_DRIFT_MATCH_THRESHOLD = 85.0
_DRIFT_TOLERANCE_PAGES = 3


@dataclass
class ResolvedTOCEntry:
    entry: TOCEntry
    pdf_page: Optional[int]  # 0-indexed, None if unresolved


def _anchor_score(doc: PDFDocument, pdf_index: int, title_norm: str) -> float:
    if not title_norm or not (0 <= pdf_index < doc.num_pages):
        return 0.0
    head = normalize_text(doc.get_page_text(pdf_index)[:_ANCHOR_HEAD_CHARS])
    if not head:
        return 0.0
    return fuzz.partial_ratio(title_norm, head)


def resolve_page_offsets(
    doc: PDFDocument, entries: List[TOCEntry]
) -> Tuple[List[ResolvedTOCEntry], int]:
    per_entry_offset: List[Optional[int]] = [None] * len(entries)
    per_entry_score: List[float] = [0.0] * len(entries)

    for i, e in enumerate(entries):
        if e.page is None:
            continue
        title_norm = normalize_text(e.title)
        if not title_norm:
            continue
        best_offset, best_score = None, 0.0
        for off in _OFFSET_SEARCH_RANGE:
            candidate = e.page - 1 + off
            score = _anchor_score(doc, candidate, title_norm)
            if score > best_score:
                best_score, best_offset = score, off
        per_entry_offset[i] = best_offset
        per_entry_score[i] = best_score

    confident_offsets = [
        off for off, score in zip(per_entry_offset, per_entry_score)
        if off is not None and score >= _GLOBAL_MATCH_THRESHOLD
    ]
    global_offset = Counter(confident_offsets).most_common(1)[0][0] if confident_offsets else 0

    results: List[ResolvedTOCEntry] = []
    for i, e in enumerate(entries):
        if e.page is None:
            results.append(ResolvedTOCEntry(entry=e, pdf_page=None))
            continue
        offset = global_offset
        entry_offset, entry_score = per_entry_offset[i], per_entry_score[i]
        if (
            entry_offset is not None
            and entry_score >= _DRIFT_MATCH_THRESHOLD
            and abs(entry_offset - global_offset) <= _DRIFT_TOLERANCE_PAGES
        ):
            offset = entry_offset
        pdf_index = e.page - 1 + offset
        if not (0 <= pdf_index < doc.num_pages):
            results.append(ResolvedTOCEntry(entry=e, pdf_page=None))
            continue
        results.append(ResolvedTOCEntry(entry=e, pdf_page=pdf_index))

    return results, global_offset
