"""Parses per-citation scope-restriction notes: the common Anna-University
citation footnote style that names exactly which units and/or sections of a
book a subject's syllabus actually assigns, e.g.:

    James Stewart, "Calculus: Early Transcendentals", Cengage Learning,
    8th Edition, New Delhi, 2015. [For Units II & IV - Sections 1.1, 2.2,
    2.3, 2.5, 2.7 (Tangents problems only), 2.8, 3.1 to 3.6, 3.11, 4.1, 4.3,
    5.1 (Area problems only), 5.2, 5.3, 5.4 (excluding net change theorem),
    5.5, 7.1 - 7.4 and 7.8].

When present, this is a strong ranking signal: it tells us directly which
units this book applies to and which of its sections were actually assigned,
so a match in an out-of-scope unit (e.g. this book's Chapter 14/15 content
against a Unit III topic) is demoted in favour of a book the syllabus did
assign there. The demotion (matcher.recommendation_ranker) is deliberately
soft, not a hard filter -- if the scoped-out book is the only local coverage
of a topic, a demoted match still beats leaving it unmatched. Most citations
carry no such note; those get an unrestricted (empty) scope.
"""
import re
from dataclasses import dataclass, field
from typing import FrozenSet, Optional, Set

from utils.roman import is_roman_numeral, roman_to_int

_BRACKET_RE = re.compile(r"\[([^\[\]]*)\]")
_UNITS_AND_SECTIONS_RE = re.compile(
    r"Units?\s+(.+?)\s*[-–—:]\s*Sections?\s+(.+)$", re.IGNORECASE | re.DOTALL
)
# Units-only notes ("[For Units I, III and V]", "[For Units II & IV]"): capture
# everything after "Unit(s)" up to an explicit "Sections" keyword or the end,
# then let the token scanner in _parse_units pick out the numerals -- a tight
# character class here would choke on connectives like the word "and".
_UNITS_ONLY_RE = re.compile(r"Units?\s+(.+?)(?:\bSections?\b|$)", re.IGNORECASE | re.DOTALL)
_SECTIONS_ONLY_RE = re.compile(r"Sections?\s+(.+)$", re.IGNORECASE | re.DOTALL)
_PAREN_RE = re.compile(r"\([^)]*\)")
_RANGE_RE = re.compile(r"^(\d+(?:\.\d+)*)\s*(?:to|[-–—])\s*(\d+(?:\.\d+)*)$", re.IGNORECASE)
_UNIT_TOKEN_RE = re.compile(r"[IVXLCDM]+|\d+")
_UNIT_RANGE_GAP_RE = re.compile(r"^\s*(?:to|through|thru|[-–—])\s*$", re.IGNORECASE)
_MAX_RANGE_SPAN = 30


@dataclass(frozen=True)
class CitationScope:
    units: FrozenSet[int] = field(default_factory=frozenset)
    sections: FrozenSet[str] = field(default_factory=frozenset)

    def allows_unit(self, unit_number: Optional[int]) -> bool:
        return not self.units or unit_number is None or unit_number in self.units

    def allows_section(self, section_label: str) -> bool:
        return not self.sections or section_label in self.sections


UNRESTRICTED = CitationScope()


def _expand_range(lo: str, hi: str) -> Set[str]:
    lo_parts, hi_parts = lo.split("."), hi.split(".")
    if len(lo_parts) != 2 or len(hi_parts) != 2 or lo_parts[0] != hi_parts[0]:
        return {lo, hi}
    chapter = lo_parts[0]
    try:
        start, end = int(lo_parts[1]), int(hi_parts[1])
    except ValueError:
        return {lo, hi}
    if start > end or end - start > _MAX_RANGE_SPAN:
        return {lo, hi}
    return {f"{chapter}.{n}" for n in range(start, end + 1)}


def _unit_token_value(tok: str) -> Optional[int]:
    if tok.isdigit():
        return int(tok)
    if is_roman_numeral(tok):
        return roman_to_int(tok)
    return None


def _parse_units(text: str) -> Set[int]:
    matches = list(_UNIT_TOKEN_RE.finditer(text))
    values = [(m, _unit_token_value(m.group(0))) for m in matches]
    values = [(m, v) for m, v in values if v is not None]

    units: Set[int] = set()
    for i, (m, v) in enumerate(values):
        units.add(v)
        if i + 1 < len(values):
            next_m, next_v = values[i + 1]
            gap = text[m.end() : next_m.start()]
            # "Units I to IV" / "Units II-V" means every unit in the span, not
            # just the two endpoints -- otherwise a book cited "For Units I to
            # IV" would be wrongly skipped for Units II and III.
            if _UNIT_RANGE_GAP_RE.match(gap) and v < next_v <= v + _MAX_RANGE_SPAN:
                units.update(range(v, next_v + 1))
    return units


def _parse_sections(text: str) -> Set[str]:
    text = _PAREN_RE.sub("", text).rstrip(" .")
    text = re.sub(r"\s+and\s+", ",", text, flags=re.IGNORECASE)
    sections: Set[str] = set()
    for raw_tok in text.split(","):
        tok = raw_tok.strip(" .")
        if not tok:
            continue
        m = _RANGE_RE.match(tok)
        if m:
            sections |= _expand_range(m.group(1), m.group(2))
        elif re.fullmatch(r"\d+(\.\d+)*", tok):
            sections.add(tok)
    return sections


def parse_citation_scope(raw_line: str) -> CitationScope:
    """Extracts an authoritative unit/section restriction from a citation's
    trailing bracket note, if present. Returns UNRESTRICTED when no such note
    is found (the common case) or nothing usable could be parsed from it."""
    content = None
    for bracket_match in _BRACKET_RE.finditer(raw_line):
        content = bracket_match.group(1)  # last bracket wins
    if content is None:
        return UNRESTRICTED

    combined = _UNITS_AND_SECTIONS_RE.search(content)
    if combined:
        units = _parse_units(combined.group(1))
        sections = _parse_sections(combined.group(2))
    else:
        units_match = _UNITS_ONLY_RE.search(content)
        units = _parse_units(units_match.group(1)) if units_match else set()
        sections_match = _SECTIONS_ONLY_RE.search(content)
        sections = _parse_sections(sections_match.group(1)) if sections_match else set()

    if not units and not sections:
        return UNRESTRICTED
    return CitationScope(units=frozenset(units), sections=frozenset(sections))
