"""Font-size/boldness-based heading detector, used only when a book has no
usable TOC (missing or fewer than MIN_TOC_ENTRIES entries). Scans page text
with pdfplumber's char-level font metadata to find short, large/bold lines
near the top of a page as chapter/section heading candidates."""
import statistics
from typing import List

import pdfplumber

import config
from extractors.page_mapper import ResolvedTOCEntry
from extractors.toc_parser import TOCEntry
from pdfcore.pdf_reader import PDFDocument
from utils.logger import log

_LEVEL1_SIZE_RATIO = 1.6
_LEVEL2_SIZE_RATIO = 1.3
_MAX_HEADING_CHARS = 90
_TOP_LINES_CONSIDERED = 4


def _line_groups(chars):
    """Group pdfplumber chars into lines by rounded 'top' position, in reading order."""
    lines = {}
    for ch in chars:
        top = round(ch["top"], 0)
        lines.setdefault(top, []).append(ch)
    ordered_tops = sorted(lines.keys())
    result = []
    for top in ordered_tops:
        line_chars = sorted(lines[top], key=lambda c: c["x0"])
        text = "".join(c["text"] for c in line_chars).strip()
        sizes = [c["size"] for c in line_chars if c.get("size")]
        avg_size = statistics.mean(sizes) if sizes else 0.0
        result.append((text, avg_size))
    return result


def detect_headings_by_font(doc: PDFDocument, path: str) -> List[ResolvedTOCEntry]:
    scan_limit = min(config.MAX_HEADING_SCAN_PAGES, doc.num_pages)
    if scan_limit == 0:
        return []

    try:
        pdf = pdfplumber.open(path)
    except Exception as exc:
        log(f"WARNING: heading_detector could not open {path} with pdfplumber: {exc}")
        return []

    all_sizes = []
    page_lines = []
    try:
        for i in range(scan_limit):
            try:
                page = pdf.pages[i]
                lines = _line_groups(page.chars)
            except Exception:
                lines = []
            page_lines.append(lines)
            all_sizes.extend(sz for _, sz in lines if sz > 0)
    finally:
        pdf.close()

    if not all_sizes:
        return []

    median_size = statistics.median(all_sizes)
    if median_size <= 0:
        return []

    results: List[ResolvedTOCEntry] = []
    for page_index, lines in enumerate(page_lines):
        for line_idx, (text, size) in enumerate(lines[:_TOP_LINES_CONSIDERED]):
            if not text or len(text) > _MAX_HEADING_CHARS or size <= 0:
                continue
            ratio = size / median_size
            if ratio >= _LEVEL1_SIZE_RATIO:
                level = 1
            elif ratio >= _LEVEL2_SIZE_RATIO:
                level = 2
            else:
                continue
            entry = TOCEntry(raw_line=text, label="", title=text, page=page_index + 1, level=level)
            results.append(ResolvedTOCEntry(entry=entry, pdf_page=page_index))

    return results
