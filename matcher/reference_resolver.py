"""Fuzzy-matches each subject's cited Text/Reference book citations against the
actual book catalog on disk, so matching can be scoped per-subject to only the
books that subject's syllabus entry actually names (see recommendation_ranker).

Citation formatting varies enough across departments that strict field
extraction isn't attempted. But whole-line-vs-whole-candidate fuzzy matching
turned out too weak in practice: a citation's publisher/edition/year noise
("Khanna Publishers, New Delhi, 44 th Edition, 2017") dilutes token-set/sort
ratios enough that even an obviously-correct match scores well under any
reasonable threshold. Instead: pull out the quoted title substring (citations
in this corpus consistently quote the title) and score title-vs-title plus
author-vs-citation separately, which is far less noise-sensitive. Falls back
to whole-line fuzzy matching only when no quoted title can be found (a
minority citation style, e.g. "Title By Author, Publisher...")."""
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from rapidfuzz import fuzz

import config
from extractors.book_loader import BookRecord
from syllabus.syllabus_parser import CitedBook, SyllabusCourse

_QUOTE_RE = re.compile(r"[\"“”‘’']([^\"“”‘’']{4,90})[\"“”‘’']")
_BY_TITLE_RE = re.compile(r"^(.*?)\s+By\s+", re.IGNORECASE)

_TITLE_WEIGHT = 0.65
_AUTHOR_WEIGHT = 0.35
# Engineering-math titles in particular are highly generic ("Higher Engineering
# Mathematics", "Calculus") and several genuinely different books by different
# authors share near-identical titles. A title-only match, however high, is not
# enough evidence on its own -- require some real author-name overlap too, or a
# same-titled-different-author citation ends up silently resolved to the wrong book.
_AUTHOR_GATE = 55.0


@dataclass
class ResolvedReference:
    cited: CitedBook
    book_key: Optional[str]
    match_score: float


def _extract_title(raw_line: str) -> Optional[str]:
    m = _QUOTE_RE.search(raw_line)
    if m:
        return m.group(1).strip()
    m = _BY_TITLE_RE.match(raw_line)
    if m:
        return m.group(1).strip()
    return None


def _match_score(raw_line: str, book_title: str, book_authors: str, filename: str) -> float:
    extracted_title = _extract_title(raw_line)
    if extracted_title and book_title:
        title_score = fuzz.token_set_ratio(extracted_title, book_title)
        author_score = fuzz.partial_ratio(raw_line, book_authors) if book_authors else 0.0
        if author_score < _AUTHOR_GATE:
            return 0.0
        return _TITLE_WEIGHT * title_score + _AUTHOR_WEIGHT * author_score
    candidate = f"{book_title} {book_authors} {filename}"
    return fuzz.WRatio(raw_line, candidate)


def resolve_subject_references(
    course: SyllabusCourse, catalog: List[BookRecord]
) -> List[ResolvedReference]:
    results: List[ResolvedReference] = []
    for cited in course.cited_books:
        best_key, best_score = None, 0.0
        for rec in catalog:
            score = _match_score(
                cited.raw_line, rec.metadata.title, rec.metadata.authors, os.path.basename(rec.path)
            )
            if score > best_score:
                best_score, best_key = score, rec.key
        book_key = best_key if best_score >= config.REFERENCE_MATCH_THRESHOLD else None
        results.append(ResolvedReference(cited=cited, book_key=book_key, match_score=best_score))
    return results


def resolve_all(
    courses: List[SyllabusCourse], catalog: List[BookRecord]
) -> Dict[str, List[ResolvedReference]]:
    return {course.code: resolve_subject_references(course, catalog) for course in courses}


def _dedupe(seq: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def split_resolved_keys(resolved: List[ResolvedReference]) -> Tuple[List[str], List[str]]:
    """Returns (textbook_keys, reference_keys), deduped, resolved-only."""
    textbook_keys, reference_keys = [], []
    for r in resolved:
        if r.book_key is None:
            continue
        if r.cited.citation_type == "textbook":
            textbook_keys.append(r.book_key)
        else:
            reference_keys.append(r.book_key)
    return _dedupe(textbook_keys), _dedupe(reference_keys)
