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

    # Only credit the heading bonus when "Contents"/"Index" is essentially
    # its OWN short line (a real page heading), not merely present anywhere
    # in the page's prose - searching the whole page text previously made
    # this fire on almost any page (e.g. "...the contents of this section
    # depend on...", a running header mentioning "Index"), which defeated
    # its purpose as a distinguishing signal for real TOC/front-matter pages.
    if any(CONTENTS_HEADER_RE.search(l) and len(l.strip()) <= 40 for l in lines[:6]):
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

    # Group into contiguous (allowing small gaps) runs - a real TOC is a
    # block, not scattered single hits.
    candidates.sort()
    runs: List[List[int]] = [[candidates[0]]]
    for pn in candidates[1:]:
        if pn - runs[-1][-1] <= config.TOC_MAX_CONTIG_GAP:
            runs[-1].append(pn)
        else:
            runs.append([pn])

    # A single low-scoring divider page (title page, "Contents in Brief",
    # a part-opener with almost no text) can split one real TOC into two
    # runs. Anchor on the largest run, then absorb any other run that sits
    # close enough to it - including the low-scoring pages in the gap
    # itself - rather than silently dropping that run's entries (which
    # previously meant losing every chapter/section listed on it).
    best_run = max(runs, key=len)
    merged = set(best_run)
    for run in runs:
        if run is best_run:
            continue
        gap_before = best_run[0] - run[-1]
        gap_after = run[0] - best_run[-1]
        if 0 < gap_before <= config.TOC_MERGE_GAP or 0 < gap_after <= config.TOC_MERGE_GAP:
            merged.update(range(min(run[0], best_run[0]), max(run[-1], best_run[-1]) + 1))

    result = sorted(merged)
    log(f"Selected TOC pages: {result}")
    return result
