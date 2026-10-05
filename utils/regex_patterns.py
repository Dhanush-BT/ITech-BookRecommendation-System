"""Shared regexes and text-normalization helpers used across the pipeline."""
import re

# Course code like "ME3491", "HS3152", "GE8291", "CCS331" (a shorter 3-digit
# numbering some elective/skill-course series use), "22BST102" (some programs
# prefix the department letters with a 1-2 digit admission-year code),
# "HS23111" (a 2-letter dept code + a 5-digit year+serial number), or
# "HS1101A" (a trailing single-letter revision/section suffix after the
# digits). A second, structurally different shape covers institutions with a
# fully-numeric internal course-id scheme carrying a single category letter,
# e.g. "34121H83" / "344213D01". A false positive here is cheap --
# _find_course_starts() only keeps a match that also has an OBJECTIVES-like
# header within the next ~500 chars -- so this stays deliberately permissive
# about digit-run lengths rather than hardcoding one institution's exact
# scheme. The one exclusion that IS needed: CO-PO/PSO outcome-correlation
# tables (present in essentially every one of these syllabi) use
# "CO1".."CO6", "PO1".."PO12", "PSO1".."PSO3" as fixed column/row labels,
# which fit the first shape -- exclude them by name rather than narrowing the
# digit range back down for everyone.
COURSE_CODE_RE = re.compile(
    r"\b(?!(?:CO|PO|PSO)\d)(\d{0,2}[A-Z]{2,4}\d{2,5}[A-Z]?|\d{4,6}[A-Z]\d{1,3})\b"
)

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

# Numbered citation entry: "1. Author, Title, Publisher, Year". The
# "."/")" after the number is optional -- some syllabi number their citation
# list with just "1 Author, Title, ..." (a bare number + space). This is only
# ever applied within an already-bounded TEXT BOOKS / REFERENCE BOOKS section
# (see _parse_cited_books), so the wider match doesn't risk misreading
# unrelated numbered content elsewhere in the document.
NUMBERED_ENTRY_RE = re.compile(r"^\s*(\d{1,2})[\.\)]?\s+(.*\S)\s*$", re.MULTILINE)

# Reference/textbook section headers
TEXTBOOK_HEADER_RE = re.compile(r"^\s*TEXT\s*BOOKS?\s*:?\s*$", re.IGNORECASE | re.MULTILINE)
REFERENCE_HEADER_RE = re.compile(r"^\s*REFERENCE(S)?(\s*BOOKS?)?\s*:?\s*$", re.IGNORECASE | re.MULTILINE)
# Not line-anchored: PDF text extraction sometimes runs a section header onto the
# same extracted line as the end of the preceding citation/topic text, so a strict
# "alone on its own line" match misses real boundaries like "...2019. REFERENCES:".
#
# The UNIT alternative guards a different failure: when the *next* subject in
# the document isn't recognized as its own course start (e.g. it has no
# OBJECTIVES-like header of its own -- "Heritage of Tamils"-style mandatory
# courses, or a faculty/course-designer table sits between two subjects), the
# current subject's TEXT BOOKS / REFERENCE BOOKS section has no other end
# marker to stop at and silently swallows that next subject's entire unit
# content as bogus citation entries. Requiring a number/roman-numeral right
# after "UNIT" (mirroring UNIT_HEADER_RE's own shape) keeps this from matching
# the word "unit" used generically inside real topics/citations ("Unit
# Vectors", "unit cell", "Unit injector").
#
# COURSE DESIGNERS / RECOMMENDED BY BOARD (OF STUDIES) are boilerplate
# trailers some curricula print right after REFERENCES (a faculty-name table,
# an approval line) with no other recognizable header before the next
# subject -- without a marker for them, that table's own numbered rows
# ("1. Dr. X ...", "2. Dr. Y ...") get read as citation entries. "s?" on
# CO/PO/PSO tolerates a column-header written as the plural "COs POs PSOs".
SECTION_END_HEADER_RE = re.compile(
    r"\b(ASSESSMENT|COs?[-\s]{0,3}POs?([-\s]{0,3}PSOs?)?|OUTCOMES?|"
    r"TOTAL\s*[:\-]?\s*(CONTACT\s+)?\d*\s*(PERIODS|HOURS)|COURSE\s+OBJECTIVES?|"
    r"COURSE\s+DESIGNERS?|RECOMMENDED\s+BY\s+BOARD|SPECIAL\s+POINTS\s+APPLICABLE|"
    r"SUGGESTED\s+ACTIVITIES|MODE\s+OF\s+EVALUATION|TEXT\s*BOOKS?|REFERENCE(S)?(\s*BOOKS?)?|"
    r"UNIT\s*[-–:]?\s*(?:[IVXLCDM]+|\d+)\b)\s*:?",
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
