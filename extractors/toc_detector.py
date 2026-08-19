"""
Locates the Table-of-Contents pages inside a book PDF using a scoring
heuristic rather than a single brittle regex (per design Phase 3).
"""
import re
from typing import List, Tuple

from extractors.pdf_reader import PDFDocument
from utils.regex_patterns import CONTENTS_HEADER_RE, NUMBERING_RE, CHAPTER_WORD_RE
from utils.logger import log
import config

TRAILING_NUM_RE = re.compile(r"\d{1,4}\s*$")
DOTTED_LEADER_RE = re.compile(r"\.\s?\.\s?\.+")


def _score_page(text: str) -> int:
    if not text or len(text.strip()) < 10:
        return 0
    score = 0
    lines = [l for l in text.split("\n") if l.strip()]
    if not lines:
        return 0

    if CONTENTS_HEADER_RE.search(text):
        score += 40

    lines_with_trailing_num = sum(1 for l in lines if TRAILING_NUM_RE.search(l.strip()))
    frac_trailing = lines_with_trailing_num / len(lines)
    if frac_trailing > 0.4:
        score += 20

    if DOTTED_LEADER_RE.search(text):
        score += 20

    lines_with_numbering = sum(1 for l in lines if NUMBERING_RE.match(l) or CHAPTER_WORD_RE.match(l))
    frac_numbered = lines_with_numbering / len(lines)
    if frac_numbered > 0.3:
        score += 10

    # repeated short-line entries (typical of a listing page rather than prose)
    avg_len = sum(len(l) for l in lines) / len(lines)
    if avg_len < 90 and len(lines) >= 5:
        score += 10

    return score


def detect_toc_pages(doc: PDFDocument) -> List[int]:
    """Return a sorted list of 1-indexed page numbers that make up the TOC."""
    scan_end = min(config.MAX_TOC_SCAN_PAGES, doc.num_pages)
    pages = doc.get_pages(1, scan_end)
    scores = [(p.page_number, _score_page(p.text)) for p in pages]

    for pn, sc in scores:
        if sc:
            log(f"  TOC candidate scoring: page {pn} -> score {sc}")

    candidates = [pn for pn, sc in scores if sc >= config.MIN_TOC_SCORE]
    if not candidates:
        log("No TOC pages found by scoring heuristic.", "WARN")
        return []

    # Keep the largest contiguous (allowing small gaps) run of candidate pages -
    # a real TOC is a block, not scattered single hits.
    candidates.sort()
    runs: List[List[int]] = [[candidates[0]]]
    for pn in candidates[1:]:
        if pn - runs[-1][-1] <= config.TOC_MAX_CONTIG_GAP:
            runs[-1].append(pn)
        else:
            runs.append([pn])
    best_run = max(runs, key=len)
    log(f"Selected TOC pages: {best_run}")
    return best_run
