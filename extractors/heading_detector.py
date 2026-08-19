"""
Fallback chapter/section detection for books whose TOC couldn't be parsed
(scanned books, missing TOC, non-standard layout). Detects headings using
font size, boldness, and numbering patterns instead of a printed TOC.
"""
from typing import List
import pdfplumber

from extractors.pdf_reader import PDFDocument
from extractors.toc_parser import TOCEntry
from utils.regex_patterns import CHAPTER_WORD_RE, NUMBERING_RE
from utils.logger import log

MIN_HEADING_LEN = 3
MAX_HEADING_LEN = 90


def _page_font_stats(page):
    sizes = [c["size"] for c in page.chars if c.get("size")]
    if not sizes:
        return 0.0
    sizes.sort()
    return sizes[len(sizes) // 2]  # median


def _line_avg_size(page, line_text: str, all_lines_words):
    # pdfplumber doesn't give us text->char mapping directly per extracted line,
    # so we approximate using extract_words() sizes for words that appear in the line.
    matches = [w for w in all_lines_words if w["text"] and w["text"] in line_text]
    if not matches:
        return 0.0
    return sum(w["size"] for w in matches) / len(matches)


def detect_headings_by_font(doc: PDFDocument, start_page: int = 1,
                             end_page: int = None) -> List[TOCEntry]:
    end_page = end_page or doc.num_pages
    entries: List[TOCEntry] = []

    try:
        with pdfplumber.open(doc.path) as pdf:
            for pn in range(start_page, min(end_page, len(pdf.pages)) + 1):
                page = pdf.pages[pn - 1]
                median_size = _page_font_stats(page)
                if median_size == 0:
                    continue
                try:
                    words = page.extract_words(extra_attrs=["size"])
                except Exception:
                    continue

                text_lines = [l for l in (page.extract_text() or "").split("\n") if l.strip()]
                for line in text_lines:
                    stripped = line.strip()
                    if not (MIN_HEADING_LEN <= len(stripped) <= MAX_HEADING_LEN):
                        continue
                    looks_structural = bool(CHAPTER_WORD_RE.match(stripped) or NUMBERING_RE.match(stripped))
                    avg_size = _line_avg_size(page, stripped, words)
                    is_large = avg_size >= median_size * 1.15 if avg_size else False
                    if looks_structural or is_large:
                        level = 1 if CHAPTER_WORD_RE.match(stripped) else 2
                        entries.append(TOCEntry(raw_line=stripped, label="", title=stripped,
                                                 page=pn, level=level))
    except Exception as e:
        log(f"Heading-fallback detection failed for {doc.path}: {e}", "WARN")
        return []

    log(f"Font/heading fallback found {len(entries)} candidate headings "
        f"between pages {start_page}-{end_page}")
    return entries
