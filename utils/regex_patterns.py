"""Shared regexes and text-normalization helpers used across the pipeline."""
import re

# Course code like "ME3491", "HS3152", "GE8291"
COURSE_CODE_RE = re.compile(r"\b([A-Z]{2,3}\d{4})\b")

# Unit header like "UNIT I", "UNIT-4", "UNIT : III", "UNIT – I" (en dash)
UNIT_HEADER_RE = re.compile(
    r"^\s*UNIT\s*[-–:]?\s*([IVXLCDM]+|\d+)\s*[-–:]?\s*(.*)$", re.IGNORECASE | re.MULTILINE
)

# TOC-style dotted leader line: "1.2 Some Title .......... 45"
TOC_DOTTED_LEADER_RE = re.compile(r"^(.*?)[\.…\s]{3,}(\d{1,4})\s*$")

# TOC entry with trailing page number, no dots: "Chapter 3  Thermodynamics   45"
TOC_TRAILING_PAGE_RE = re.compile(r"^(.*\S)\s+(\d{1,4})\s*$")

# Chapter/section label prefix: "1.", "1.2", "Chapter 3", "3.4.1"
LABEL_PREFIX_RE = re.compile(
    r"^(Chapter\s+\d+|Unit\s+\d+|\d+(\.\d+)*)[\.\):]?\s+", re.IGNORECASE
)

# Numbered citation entry: "1. Author, Title, Publisher, Year"
NUMBERED_ENTRY_RE = re.compile(r"^\s*(\d{1,2})[\.\)]\s+(.*\S)\s*$", re.MULTILINE)

# Reference/textbook section headers
TEXTBOOK_HEADER_RE = re.compile(r"^\s*TEXT\s*BOOKS?\s*:?\s*$", re.IGNORECASE | re.MULTILINE)
REFERENCE_HEADER_RE = re.compile(r"^\s*REFERENCE(S)?(\s*BOOKS?)?\s*:?\s*$", re.IGNORECASE | re.MULTILINE)
# Not line-anchored: PDF text extraction sometimes runs a section header onto the
# same extracted line as the end of the preceding citation/topic text, so a strict
# "alone on its own line" match misses real boundaries like "...2019. REFERENCES:".
SECTION_END_HEADER_RE = re.compile(
    r"\b(ASSESSMENT|CO[-\s]{0,3}PO([-\s]{0,3}PSO)?|OUTCOMES?|TOTAL\s*:?\s*\d*\s*PERIODS|COURSE\s+OBJECTIVES?|"
    r"SUGGESTED\s+ACTIVITIES|MODE\s+OF\s+EVALUATION|TEXT\s*BOOKS?|REFERENCE(S)?(\s*BOOKS?)?)\s*:?",
    re.IGNORECASE,
)

_STOPWORDS = frozenset(
    """
    a an the and or of to in on for with without within into onto from by at as is are was were
    be been being this that these those it its it's their his her they he she we you your our
    which who whom what when where why how not no nor but if then than so such can may might
    will would shall should must do does did have has had also etc using use used via each
    """.split()
)


def normalize_text(text: str) -> str:
    """Lowercase, collapse whitespace, strip punctuation noise (keep alnum + spaces)."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize(text: str, drop_stopwords: bool = True) -> list:
    words = normalize_text(text).split()
    if drop_stopwords:
        words = [w for w in words if w not in _STOPWORDS and len(w) > 1]
    return words
