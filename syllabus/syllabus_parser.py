"""Parses an Anna-University-style syllabus PDF (covering an entire degree
curriculum) into per-subject SyllabusCourse structures: units/topics plus the
subject's own TEXT BOOKS / REFERENCE BOOKS citation lists.

Format observed in this corpus (confirmed by direct inspection of
syllabi/B.E.Mech.pdf): each subject gets a detailed section shaped like

    <CODE> <SUBJECT NAME>              L T P C
                                        3 0 0 3
    COURSE OBJECTIVES: ...
    UNIT – I <UNIT TITLE>              9
    <topic> – <topic> – <topic> – ...
    UNIT – II <UNIT TITLE>             9
    ...
    TOTAL: 45 PERIODS
    OUTCOMES: ...
    TEXT BOOKS:
    1. <citation>
    2. <citation>
    REFERENCE BOOKS:
    1. <citation>
    ...

Citation formatting varies by department (author-first vs title-first), so
this parser deliberately does NOT try to split citations into strict
author/title/publisher fields — it keeps the raw line and leaves matching
to fuzzy string comparison downstream (matcher/reference_resolver.py).
"""
import re
from dataclasses import dataclass, field
from typing import Iterator, List, Optional, Tuple

import pypdf

from utils.logger import log
from utils.regex_patterns import (
    COURSE_CODE_RE,
    NUMBERED_ENTRY_RE,
    REFERENCE_HEADER_RE,
    SECTION_END_HEADER_RE,
    TEXTBOOK_HEADER_RE,
    UNIT_HEADER_RE,
)
from utils.roman import parse_unit_number

_OBJECTIVES_RE = re.compile(r"OBJECTIVES?\s*:?", re.IGNORECASE)
_TOPIC_SPLIT_RE = re.compile(r"\s+[–—-]\s+")
# Unit-header lines carry an L-T-P-C / period-count tail ("MATRICES  9 + 0 + 0
# + 3", "... 9") after the title. Unit titles are alphabetic, so cut at the
# first standalone number (a digit run not glued to a letter, e.g. keep "3D").
_UNIT_TITLE_TAIL_RE = re.compile(r"\s+\d{1,3}(?![A-Za-z]).*$", re.DOTALL)

# Anna-University syllabi use the same spaced dash both as the topic separator
# and, inconsistently, inside hyphenated eponymous names ("Cayley - Hamilton
# theorem", "Gram - Schmidt orthogonalization"). Splitting naively turns those
# into two useless half-topics ("Cayley", "Hamilton theorem"), which then never
# match a book section. Re-join a lone surname fragment to the next one when the
# next fragment opens with another capitalised name and carries an eponymous
# descriptor -- i.e. it reads like "<Name>-<Name> <thing>".
_LONE_NAME_RE = re.compile(r"^[A-Z][A-Za-z’'.]+$")
_EPONYM_HEAD_RE = re.compile(r"^[A-Z][A-Za-z’'.]+\b")
_EPONYM_DESCRIPTOR_RE = re.compile(
    r"\b(theorem|method|rule|equation|equations|formula|series|law|laws|"
    r"criterion|criteria|test|process|algorithm|transformation|elimination|"
    r"iteration|orthogonalization|orthogonalisation|identity|inequality|"
    r"polynomial|polynomials|expansion|approximation)\b",
    re.IGNORECASE,
)
# Capitalised generic words that also pass _LONE_NAME_RE but are never the
# surname half of an eponymous compound.
_NOT_A_SURNAME = frozenset(
    "applications application introduction properties fundamentals basics overview "
    "analysis design types definition definitions examples theory methods method "
    "concepts principles problems problem review summary notes".split()
)


def _merge_eponym_splits(topics: List[str]) -> List[str]:
    merged: List[str] = []
    i = 0
    while i < len(topics):
        cur = topics[i]
        if (
            i + 1 < len(topics)
            and _LONE_NAME_RE.match(cur)
            and cur.lower().rstrip(".") not in _NOT_A_SURNAME
            and _EPONYM_HEAD_RE.match(topics[i + 1])
            and _EPONYM_DESCRIPTOR_RE.search(topics[i + 1])
        ):
            merged.append(f"{cur}-{topics[i + 1]}")
            i += 2
        else:
            merged.append(cur)
            i += 1
    return merged


@dataclass
class CitedBook:
    raw_line: str
    citation_type: str  # "textbook" | "reference"


@dataclass
class SyllabusModule:
    unit_label: str
    unit_number: Optional[int]
    unit_title: str
    topics: List[str] = field(default_factory=list)
    raw_text: str = ""


@dataclass
class SyllabusCourse:
    code: str
    name: str
    modules: List[SyllabusModule] = field(default_factory=list)
    cited_books: List[CitedBook] = field(default_factory=list)
    source_file: str = ""

    def all_topics(self) -> Iterator[Tuple[SyllabusModule, str]]:
        for module in self.modules:
            if module.topics:
                for topic in module.topics:
                    yield module, topic
            else:
                yield module, module.unit_title


def _extract_full_text(path: str) -> str:
    reader = pypdf.PdfReader(path, strict=False)
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    return "\n".join(pages)


def _find_course_starts(text: str) -> List[Tuple[int, str, str]]:
    """Locate detailed course-syllabus section headers (not curriculum-table rows)."""
    starts = []
    seen_codes = set()
    for match in COURSE_CODE_RE.finditer(text):
        code = match.group(1)
        idx = match.start()
        window = text[idx: idx + 500]
        obj_match = _OBJECTIVES_RE.search(window)
        if not obj_match or obj_match.start() > 450:
            continue
        if code in seen_codes:
            continue
        # course name: rest of the header line(s) up to "L T P C" or the first blank line
        after_code = text[match.end(): idx + 300]
        header_end = re.search(r"L\s*T\s*P\s*C|\n\s*\n", after_code)
        name_region = after_code[: header_end.start()] if header_end else after_code[:80]
        name = re.sub(r"\s+", " ", name_region).strip(" -:–")
        if not name:
            name = code
        starts.append((idx, code, name))
        seen_codes.add(code)
    return starts


def _parse_units(block: str) -> List[SyllabusModule]:
    unit_matches = list(UNIT_HEADER_RE.finditer(block))
    modules = []
    for i, m in enumerate(unit_matches):
        unit_label = f"UNIT {m.group(1)}"
        unit_number = parse_unit_number(unit_label)
        rest_of_line = m.group(2).strip()

        body_start = m.end()
        body_end = unit_matches[i + 1].start() if i + 1 < len(unit_matches) else len(block)
        body = block[body_start:body_end]

        end_marker = SECTION_END_HEADER_RE.search(body)
        if end_marker:
            body = body[: end_marker.start()]

        # unit title is often on the header line, followed by an L-T-P-C tail
        title_line = _UNIT_TITLE_TAIL_RE.sub("", rest_of_line).strip(" -:–")
        title_line = re.sub(r"\s+", " ", title_line)
        body_norm = re.sub(r"\s+", " ", body).strip()

        if not title_line and body_norm:
            # title wrapped onto the next line before the topic dashes start
            first_dash = body_norm.find("–")
            if first_dash == -1:
                first_dash = body_norm.find(" - ")
            title_line = body_norm[: first_dash if first_dash > 0 else len(body_norm)].strip()
            body_norm = body_norm[len(title_line):].strip(" -:–")

        topics = [t.strip(" .") for t in _TOPIC_SPLIT_RE.split(body_norm) if t.strip(" .")]
        # drop a pure-numeric leftover ("9" hour count) if it slipped into the split
        topics = [t for t in topics if not re.fullmatch(r"\d{1,3}", t)]
        topics = _merge_eponym_splits(topics)

        modules.append(
            SyllabusModule(
                unit_label=unit_label,
                unit_number=unit_number,
                unit_title=title_line or unit_label,
                topics=topics,
                raw_text=body_norm,
            )
        )
    return modules


def _parse_cited_books(block: str) -> List[CitedBook]:
    cited: List[CitedBook] = []
    for header_re, citation_type in ((TEXTBOOK_HEADER_RE, "textbook"), (REFERENCE_HEADER_RE, "reference")):
        header_match = header_re.search(block)
        if not header_match:
            continue
        section_start = header_match.end()
        end_marker = SECTION_END_HEADER_RE.search(block, pos=section_start)
        section_end = end_marker.start() if end_marker else len(block)
        section = block[section_start:section_end]

        entries = list(NUMBERED_ENTRY_RE.finditer(section))
        for i, m in enumerate(entries):
            entry_start = m.start()
            entry_end = entries[i + 1].start() if i + 1 < len(entries) else len(section)
            raw_full = re.sub(r"\s+", " ", section[entry_start:entry_end]).strip()
            raw = re.sub(r"^\d{1,2}[\.\)]\s*", "", raw_full)
            if raw:
                cited.append(CitedBook(raw_line=raw, citation_type=citation_type))
    return cited


def parse_syllabus_pdf(path: str) -> List[SyllabusCourse]:
    text = _extract_full_text(path)
    starts = _find_course_starts(text)
    log(f"syllabus_parser: found {len(starts)} subject sections in {path}")

    courses = []
    for i, (idx, code, name) in enumerate(starts):
        block_end = starts[i + 1][0] if i + 1 < len(starts) else len(text)
        block = text[idx:block_end]
        modules = _parse_units(block)
        cited_books = _parse_cited_books(block)
        courses.append(
            SyllabusCourse(
                code=code,
                name=name,
                modules=modules,
                cited_books=cited_books,
                source_file=path,
            )
        )
    return courses
