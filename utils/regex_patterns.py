import re

# A TOC line generally looks like:  "1.2  Some Chapter Title ......... 45"
# or "Chapter 4  Vat Photopolymerization  63"  or "UNIT I  INTRODUCTION  1"
DOTTED_LEADER_RE = re.compile(r"\.{2,}|\s{3,}\.*\s*$")
TRAILING_PAGE_NUM_RE = re.compile(r"(\d{1,4})\s*$")
NUMBERING_RE = re.compile(r"^\s*((?:\d+\.)+\d*|\d+|[IVXLCDM]+)\s+")
CHAPTER_WORD_RE = re.compile(r"^\s*(CHAPTER|UNIT|PART|APPENDIX|MODULE)\b", re.IGNORECASE)
CONTENTS_HEADER_RE = re.compile(r"\b(CONTENTS?|TABLE OF CONTENTS|INDEX)\b", re.IGNORECASE)

MULTI_SPACE_RE = re.compile(r"\s+")
NON_ALNUM_RE = re.compile(r"[^a-z0-9\s]")

# Course-code style tokens e.g. CX4101, MA4154, RM4151, AX4091
COURSE_CODE_RE = re.compile(r"\b[A-Z]{2,4}\d{3,4}\b")

# Unit heading inside a syllabus, e.g. "UNIT I ALGEBRAIC EQUATIONS 12"
SYLLABUS_UNIT_RE = re.compile(
    r"^\s*UNIT\s*[-]?\s*([IVXLCDM0-9]+)\s+(.+?)\s+(\d{1,3})\s*$",
    re.IGNORECASE,
)


def normalize_text(text: str) -> str:
    text = text.lower()
    text = NON_ALNUM_RE.sub(" ", text)
    text = MULTI_SPACE_RE.sub(" ", text)
    return text.strip()


def tokenize(text: str):
    return normalize_text(text).split()
