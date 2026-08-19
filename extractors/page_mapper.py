"""
Maps the printed page numbers found in a TOC (e.g. "63") to actual PDF
page indices (e.g. PDF page 74), since front matter (preface, TOC itself,
roman-numbered pages) shifts everything.

Strategy: use only long, distinctive chapter-level titles as "anchors" -
short/generic titles ("Introduction", "Summary", a lone letter) are exactly
the kind of text that can produce a false-positive match somewhere else in
the book, and one bad match used to silently poison the page mapping for
every entry after it. For each anchor we require a strict (near-exact,
normalized) substring match rather than a fuzzy ratio, search an
expanding window so real drift (inserted plates, front-matter pages) can
still be found, and reject any match that would imply an implausible jump
in the running offset rather than adopting it. Section-level entries
(non-anchors) are simply offset by the most recently confirmed anchor.
"""
from typing import Dict, List, Optional

from extractors.pdf_reader import PDFDocument
from extractors.toc_parser import TOCEntry
from indexing.text_cleaner import clean_text
from utils.regex_patterns import normalize_text
from utils.logger import log

MIN_ANCHOR_TITLE_LEN = 15     # only fairly long/distinctive titles are trusted as anchors
ANCHOR_PREFIX_LEN = 30        # how much of the normalized title must match verbatim
MIN_ANCHOR_PREFIX_LEN = 10    # don't even try if the usable prefix is too short to be distinctive
INITIAL_WINDOW = 20
MAX_WINDOW = 300              # hard cap on how far we'll search from the guess
WINDOW_GROWTH = 4
MAX_OFFSET_JUMP = 200         # reject an anchor match implying a wildly different offset than before


def _normalized_page_cache(doc: PDFDocument) -> Dict[int, str]:
    cache: Dict[int, str] = {}

    def get(pn: int) -> str:
        if pn not in cache:
            page = doc.get_pages(pn, pn)[0]
            cache[pn] = normalize_text(clean_text(page.text))
        return cache[pn]
    return get


def _find_anchor_page(get_norm_text, prefix: str, guess: int, max_page: int) -> Optional[int]:
    window = INITIAL_WINDOW
    while window <= MAX_WINDOW:
        lo = max(1, guess - window)
        hi = min(max_page, guess + window)
        candidates = [pn for pn in range(lo, hi + 1) if prefix in get_norm_text(pn)]
        if candidates:
            return min(candidates, key=lambda p: abs(p - guess))
        window *= WINDOW_GROWTH
    return None


def resolve_page_offsets(doc: PDFDocument, entries: List[TOCEntry], toc_pages: List[int]) -> List[TOCEntry]:
    """Returns a NEW list of TOCEntry with .page rewritten to the actual PDF page.
    Falls back to printed page + last-good-offset when no confident anchor match
    is found (or when the entry's title is too short/generic to trust as an anchor)."""
    if not entries:
        return []

    last_toc_page = max(toc_pages) if toc_pages else 1
    running_offset = last_toc_page  # first guess: content starts right after TOC
    resolved: List[TOCEntry] = []
    get_norm_text = _normalized_page_cache(doc)
    anchors_confirmed = 0
    anchors_rejected = 0

    for entry in entries:
        guess = entry.page + running_offset
        found_page: Optional[int] = None

        is_anchor_candidate = entry.level == 1 and len(entry.title) >= MIN_ANCHOR_TITLE_LEN
        if is_anchor_candidate:
            prefix = normalize_text(entry.title)[:ANCHOR_PREFIX_LEN]
            if len(prefix) >= MIN_ANCHOR_PREFIX_LEN:
                candidate_page = _find_anchor_page(get_norm_text, prefix, guess, doc.num_pages)
                if candidate_page is not None:
                    implied_offset = candidate_page - entry.page
                    if abs(implied_offset - running_offset) <= MAX_OFFSET_JUMP:
                        found_page = candidate_page
                        running_offset = implied_offset
                        anchors_confirmed += 1
                    else:
                        anchors_rejected += 1
                        log(f"  Rejected implausible anchor '{entry.title[:40]}': "
                            f"would jump offset {running_offset} -> {implied_offset}", "WARN")

        final_page = found_page if found_page is not None else max(1, min(doc.num_pages, guess))
        new_entry = TOCEntry(
            raw_line=entry.raw_line, label=entry.label, title=entry.title,
            page=final_page, level=entry.level,
        )
        resolved.append(new_entry)

    log(f"Resolved page offsets for {len(resolved)} entries "
        f"({anchors_confirmed} anchors confirmed, {anchors_rejected} rejected as implausible, "
        f"final running offset = {running_offset})")
    return resolved
