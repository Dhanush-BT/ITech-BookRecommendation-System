"""Scores front-matter pages heuristically to locate the book's table-of-contents
page range, without relying on any bookmark/outline metadata (often missing or
unreliable in scanned/converted engineering textbooks)."""
import re
from typing import List, Optional, Tuple

import config
from pdfcore.pdf_reader import PDFDocument

_CONTENTS_HEADER_RE = re.compile(r"\bTABLE\s+OF\s+CONTENTS\b|\bCONTENTS\b", re.IGNORECASE)
_TOC_LINE_RE = re.compile(r"^.{3,90}?[\.\s]{2,}\d{1,4}\s*$|^.{3,90}\s\d{1,4}\s*$")


def _score_page(text: str) -> float:
    if not text.strip():
        return 0.0
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if not lines:
        return 0.0

    score = 0.0
    header_region = "\n".join(lines[:3])
    if _CONTENTS_HEADER_RE.search(header_region):
        score += 45.0

    toc_like_lines = sum(1 for ln in lines if _TOC_LINE_RE.match(ln.strip()))
    ratio = toc_like_lines / len(lines)
    score += min(50.0, ratio * 100.0)
    score += min(15.0, toc_like_lines * 1.5)

    return min(100.0, score)


def detect_toc_pages(doc: PDFDocument) -> Optional[Tuple[int, int]]:
    """Returns an inclusive 0-indexed (start, end) page range, or None if not found."""
    scan_limit = min(config.MAX_TOC_SCAN_PAGES, doc.num_pages)
    scores: List[float] = [_score_page(doc.get_page_text(i)) for i in range(scan_limit)]

    hits = [i for i, s in enumerate(scores) if s >= config.MIN_TOC_SCORE]
    if not hits:
        return None

    runs: List[List[int]] = [[hits[0]]]
    for page in hits[1:]:
        if page - runs[-1][-1] <= config.TOC_MAX_CONTIG_GAP:
            runs[-1].append(page)
        else:
            runs.append([page])

    merged: List[List[int]] = [runs[0]]
    for run in runs[1:]:
        if run[0] - merged[-1][-1] <= config.TOC_MERGE_GAP:
            merged[-1].extend(run)
        else:
            merged.append(run)

    best_run = max(merged, key=len)
    return best_run[0], best_run[-1]
