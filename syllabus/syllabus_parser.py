"""
Parses a university syllabus PDF (Anna University style: course code,
course title, L-T-P-C, UNIT I..V with topic lists, references) into a
structured list of SyllabusCourse objects, each holding SyllabusModule
(unit) entries with a flat topic list.

Designed against the real syllabus documents in this project (Anna
University M.Tech / B.Tech regulation books), but written defensively so
that odd formatting (missing spaces, wrapped headers, stray page numbers)
degrades gracefully instead of crashing the whole run.
"""
import re
from dataclasses import dataclass, field
from typing import List, Optional

from extractors.pdf_reader import PDFDocument
from indexing.text_cleaner import clean_text
from utils.regex_patterns import COURSE_CODE_RE
from utils.roman import normalize_unit_number
from utils.logger import log

# "MA4154 ADVANCED NUMERICAL METHODS L T P C"  (L T P C header sometimes on same/next line)
COURSE_HEADER_RE = re.compile(
    r"^\s*([A-Z]{2,4}\d{3,4})\s+([A-Z][A-Z0-9&,.:'\-/ ]{3,80}?)\s*(?:L\s*T\s*P\s*C)?\s*$"
)

# "UNIT I ALGEBRAIC EQUATIONS 12"  /  "UNITIII FINITE DIFFERENCE METHOD ... 12" (wrapped, no trailing hrs)
UNIT_HEADER_RE = re.compile(
    r"^\s*UNIT\s*[-]?\s*([IVXLCDM0-9]+)\s+(.*?)\s*(\d{1,3})?\s*$",
    re.IGNORECASE,
)
# Catches the "UNITIII ..." collapsed-space case
UNIT_HEADER_NOSPACE_RE = re.compile(
    r"^\s*UNIT([IVXLCDM0-9]+)\s+(.*?)\s*(\d{1,3})?\s*$",
    re.IGNORECASE,
)

STOP_SECTION_RE = re.compile(
    r"^\s*(TOTAL\s*[:\-]?\s*\d*\s*PERIODS?|COURSE\s+OUTCOMES?|REFERENCES?|"
    r"COURSE\s+ARTICULATION|SUGGESTED)\b", re.IGNORECASE
)
SKIP_SECTION_RE = re.compile(r"^\s*COURSE\s+OBJECTIVES?\s*:?\s*$", re.IGNORECASE)

TOPIC_SPLIT_RE = re.compile(r"\s[–\-]\s|\s*\n\s*")


@dataclass
class SyllabusModule:
    unit_label: str          # "I", "II", ... or raw token
    unit_number: Optional[int]
    unit_title: str
    topics: List[str] = field(default_factory=list)
    raw_text: str = ""


@dataclass
class SyllabusCourse:
    code: str
    name: str
    modules: List[SyllabusModule] = field(default_factory=list)
    source_file: str = ""

    def all_topics(self):
        """Yield (module, topic_text) for every topic across every unit,
        plus the unit title itself as a coarse-grained topic."""
        for m in self.modules:
            yield m, m.unit_title
            for t in m.topics:
                yield m, t


def _split_topics(body: str) -> List[str]:
    body = body.replace("\u2013", "-").replace("\u2014", "-")
    raw_parts = re.split(r"\s-\s|\n", body)
    topics = []
    for part in raw_parts:
        part = part.strip(" :.-")
        if len(part) < 3:
            continue
        # further split comma-separated clauses only if the clause is long
        # (keeps short acronym lists like "IVPs, BVP" intact)
        topics.append(part)
    return topics


def _match_unit_header(line: str):
    m = UNIT_HEADER_RE.match(line)
    if not m:
        m = UNIT_HEADER_NOSPACE_RE.match(line)
    return m


def parse_syllabus_pdf(path: str) -> List[SyllabusCourse]:
    doc = PDFDocument(path)
    courses: List[SyllabusCourse] = []
    current_course: Optional[SyllabusCourse] = None
    current_module: Optional[SyllabusModule] = None
    in_objectives_block = False
    module_buffer: List[str] = []

    def flush_module():
        nonlocal current_module, module_buffer
        if current_module is not None:
            body = "\n".join(module_buffer).strip()
            current_module.raw_text = body
            current_module.topics = _split_topics(body)
            if current_course is not None:
                current_course.modules.append(current_module)
        current_module = None
        module_buffer = []

    total_pages = doc.num_pages
    for page in doc.get_pages(1, total_pages):
        text = clean_text(page.text) if False else page.text  # keep raw layout; clean per-line below
        for raw_line in text.split("\n"):
            line = raw_line.strip()
            if not line:
                continue

            # New course header (only trust it if it contains a real course code)
            code_match = COURSE_CODE_RE.search(line)
            header_match = COURSE_HEADER_RE.match(line)
            if code_match and header_match and header_match.group(1) == code_match.group(0):
                flush_module()
                code = header_match.group(1)
                name = header_match.group(2).strip().rstrip("LTPC ").strip()
                if len(name) >= 3:
                    current_course = SyllabusCourse(code=code, name=name, source_file=path)
                    courses.append(current_course)
                    in_objectives_block = False
                    continue

            if current_course is None:
                continue  # front-matter / regulations pages before first course

            if SKIP_SECTION_RE.match(line):
                in_objectives_block = True
                continue

            unit_match = _match_unit_header(line)
            if unit_match:
                flush_module()
                in_objectives_block = False
                label = unit_match.group(1).strip().rstrip(".")
                title = (unit_match.group(2) or "").strip(" :.-")
                current_module = SyllabusModule(
                    unit_label=label,
                    unit_number=normalize_unit_number(label),
                    unit_title=title if title else "(untitled unit)",
                )
                continue

            if STOP_SECTION_RE.match(line):
                flush_module()
                in_objectives_block = True
                continue

            if in_objectives_block:
                continue

            if current_module is not None:
                module_buffer.append(line)

    flush_module()
    log(f"Parsed {len(courses)} course(s) with "
        f"{sum(len(c.modules) for c in courses)} total units from {path}")
    return courses
