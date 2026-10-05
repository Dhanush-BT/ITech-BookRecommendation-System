"""Normalizes heterogeneous syllabus PDF text into the canonical section-header
vocabulary that syllabus_parser.py's structural regexes expect.

syllabus_parser.py was built against one concrete layout (Anna-University-style:
"UNIT – I ...", "TEXT BOOKS:", "REFERENCE BOOKS:", "OBJECTIVES:"). Syllabus PDFs
from other departments/universities/regulations routinely say the same things
with different words -- "MODULE 1" instead of "UNIT I", "PRESCRIBED BOOKS"
instead of "TEXT BOOKS", "BIBLIOGRAPHY" instead of "REFERENCE BOOKS", bullet
characters instead of the spaced-dash topic separator, etc. Rather than
teaching every downstream regex every synonym, this module runs first and
rewrites the extracted text so the *existing* structural regexes see only the
vocabulary they already know.

This is deliberately a plain text -> text rewrite (no PDF understanding of its
own) so it composes with whatever extraction already produced the text, and so
new synonyms can be added here as one-line rules without touching the parser's
actual structural logic.

Each rule returns how many times it fired; `standardize_syllabus_text` reports
that back so callers (and scripts/standardize_syllabus.py) can see exactly what
was rewritten -- useful for spotting a syllabus format this rule set doesn't
cover yet.

When a genuinely new format shows up (a course-code scheme this doesn't
recognize, a units-as-a-table layout, etc.), add a rule here rather than
loosening the parser's own structural regexes -- that keeps the parser's
matching precise and puts all "which words mean the same thing" knowledge in
one place.
"""
import re
from typing import Dict, Tuple

# --- Rule 0: parenthetical-plural book headers -------------------------------
# TEXTBOOK_HEADER_RE / REFERENCE_HEADER_RE (utils/regex_patterns.py) expect a
# plain trailing "S" ("TEXT BOOKS:"). Some syllabi instead write the plural as
# "Text Book(s):" / "Reference Books(s):" -- the literal "(s)" isn't
# whitespace or a colon, so it falls through the header regex entirely and
# the whole citation section is missed. Collapse it to the plain plural
# before anything else runs.
_BOOK_PAREN_PLURAL_RE = re.compile(r"(?i)\bBOOKS?\(s\)")

# --- Rule 1: whitespace / extraction noise -----------------------------------
# Non-breaking spaces and form-feeds show up from some PDF text layers and
# would otherwise survive the parser's `\s+` collapsing as visually-invisible
# but regex-significant characters.
_WHITESPACE_NOISE_RE = re.compile(r"[\xa0  ]|\x0c")


def _clean_whitespace_noise(text: str) -> Tuple[str, int]:
    return _WHITESPACE_NOISE_RE.subn(lambda m: "\n" if m.group(0) == "\x0c" else " ", text)


# --- Rule 1b: institution cohort prefixes on course codes -------------------
# COURSE_CODE_RE (utils/regex_patterns.py) matches the actual Anna-University
# department-code shape (2-3 letters + 3-4 digits, e.g. "MA3151", "CCS331").
# Some programs prefix every code with a cohort/shift marker that isn't part
# of the department code itself -- observed so far: "PT" (part-time program),
# e.g. "PTMA3151" for the regular "MA3151". Left in place, the extra letters
# push the letter-run past COURSE_CODE_RE's 3-letter cap and the whole subject
# goes undetected. Strip a leading "PT" only when it is immediately followed
# by something that already looks like a real course code, so an unrelated
# "PT" elsewhere in the text is never touched.
_COURSE_CODE_COHORT_PREFIX_RE = re.compile(r"\bPT(?=[A-Z]{2,3}\d{3,4}\b)")

# --- Rule 2: bullet-point topic lists ----------------------------------------
# syllabus_parser splits a unit's topic list on a spaced dash ("A – B – C")
# after collapsing all whitespace (including newlines) to single spaces. A
# syllabus that lists topics one-per-line with a bullet character instead of
# dashes would collapse into one run-on topic. Rewriting the bullet into a
# leading dash makes it fall into the same spaced-dash separator the collapse
# step already produces.
_BULLET_RE = re.compile(r"(?m)^[ \t]*[•◦▪●‣∙·]\s*")

# --- Rule 3: unit-header synonyms --------------------------------------------
# UNIT_HEADER_RE (utils/regex_patterns.py) only recognizes the literal word
# "UNIT". Other common section names for the same concept:
_UNIT_SYNONYM_RE = re.compile(
    r"(?m)^(\s*)(MODULE|CHAPTER|BLOCK)(?=\s*[-–:]?\s*(?:[IVXLCDM]+|\d+)\b)",
    re.IGNORECASE,
)

# --- Rule 4: course-objectives header synonyms -------------------------------
# _find_course_starts() gates a detected course code on the word
# "OBJECTIVE(S)" appearing nearby -- a syllabus that instead says "AIM" /
# "AIMS" / "COURSE AIM" for the same section would otherwise fail that gate
# and the whole subject would go undetected.
_OBJECTIVES_SYNONYM_RE = re.compile(
    r"(?im)^[ \t]*(?:COURSE\s+)?AIMS?\s*:?\s*$"
)

# --- Rule 5 & 6: text/reference book section-header synonyms ----------------
# TEXTBOOK_HEADER_RE / REFERENCE_HEADER_RE already tolerate "TEXT BOOK(S)" and
# "REFERENCE(S) (BOOKS)" in most spacings/casings. These cover the other
# common phrasings for the same two sections. Order matters: the textbook rule
# runs first so "RECOMMENDED TEXT BOOKS" (mandatory reading, phrased with
# "recommended") is claimed before the reference rule's bare
# "RECOMMENDED ... BOOKS" alternative can see it.
_TEXTBOOK_SYNONYM_RE = re.compile(
    r"(?im)^[ \t]*(?:"
    r"PRESCRIBED\s+(?:TEXT\s*)?BOOKS?"
    r"|(?:TEXT\s*)?BOOKS?\s+PRESCRIBED"
    r"|RECOMMENDED\s+TEXT\s*BOOKS?"
    r")\s*:?\s*$"
)
_REFERENCE_SYNONYM_RE = re.compile(
    r"(?im)^[ \t]*(?:"
    r"BIBLIOGRAPHY"
    r"|(?:SUGGESTED|FURTHER|ADDITIONAL|RECOMMENDED)\s+(?:READINGS?|BOOKS?)"
    r")\s*:?\s*$"
)

# --- Rule 7: bare (un-numbered) unit headings under a "SYLLABUS" marker ------
# One curriculum (observed in a Mech full-time syllabus) skips "UNIT I/II/..."
# entirely for some subjects: after the CO-PO mapping table's legend line, it
# prints a bare "SYLLABUS" marker followed directly by ALL-CAPS topic headings
# with no numbering at all ("SYLLABUS \nWATER TECHNOLOGY \n<topic text>
# \nELECTROCHEMISTRY... \n<topic text>"). UNIT_HEADER_RE never matches these,
# so every one of that subject's units -- and its topics -- goes undetected.
# The CO-PO legend line is a reliable, narrow anchor for this exact template
# (checked against the whole corpus: it precedes a bare "SYLLABUS" marker only
# in this one curriculum's files), so gating on it keeps this from firing on
# an unrelated "SYLLABUS" title-page mention elsewhere.
#
# This can't be a single regex substitution like the rules above because the
# headings need sequential numbers, and how far the heading run extends
# depends on where the next TEXT BOOKS/REFERENCE/OUTCOMES/etc. header is (see
# SECTION_END_HEADER_RE) -- both open-ended, stateful decisions -- so it runs
# as its own pass over the text.
_BARE_SYLLABUS_TRIGGER_RE = re.compile(
    r"(?im)S-\s*Strong;\s*M-\s*Medium;\s*L-\s*Low\s*\n[ \t]*SYLLABUS\s*:?\s*\n"
)
# A heading line: starts with a letter/digit, holds up only caps/digits/basic
# punctuation, 3-100 chars, and (checked separately) has no lowercase letter --
# distinguishing it from the topic paragraph text that follows it.
_CAPS_HEADING_LINE_RE = re.compile(r"^[A-Z0-9][A-Z0-9 &\-,/().:'ʼ]{1,98}[A-Z0-9).]$")


def _number_bare_syllabus_units(text: str) -> Tuple[str, int]:
    # Local import: utils.regex_patterns has no dependency on this module, so
    # this doesn't create an import cycle.
    from utils.regex_patterns import SECTION_END_HEADER_RE, UNIT_HEADER_RE

    total_hits = 0
    pieces = []
    last_end = 0
    for trig in _BARE_SYLLABUS_TRIGGER_RE.finditer(text):
        block_start = trig.end()
        end_marker = SECTION_END_HEADER_RE.search(text, pos=block_start)
        block_end = end_marker.start() if end_marker else len(text)
        block = text[block_start:block_end]

        if UNIT_HEADER_RE.search(block):
            continue  # this subject already numbers its units; leave it alone

        n = 0
        new_lines = []
        for line in block.split("\n"):
            stripped = line.strip()
            if (
                _CAPS_HEADING_LINE_RE.match(stripped)
                and not any(ch.islower() for ch in stripped)
            ):
                n += 1
                new_lines.append(f"UNIT {n} {stripped}")
            else:
                new_lines.append(line)
        if n == 0:
            continue

        pieces.append(text[last_end:block_start])
        pieces.append("\n".join(new_lines))
        last_end = block_end
        total_hits += n

    if total_hits == 0:
        return text, 0
    pieces.append(text[last_end:])
    return "".join(pieces), total_hits


def standardize_syllabus_text(text: str) -> Tuple[str, Dict[str, int]]:
    """Rewrite `text` so common non-canonical phrasings become the vocabulary
    syllabus_parser's structural regexes already recognize. Returns the
    rewritten text plus a {rule_name: hit_count} dict of what fired, so
    callers can log/inspect exactly what was normalized (empty dict = the text
    was already canonical, or used a variant this rule set doesn't cover yet).
    """
    changes: Dict[str, int] = {}

    text, n = _BOOK_PAREN_PLURAL_RE.subn("BOOKS", text)
    if n:
        changes["book_parenthetical_plural"] = n

    text, n = _clean_whitespace_noise(text)
    if n:
        changes["whitespace_noise"] = n

    text, n = _COURSE_CODE_COHORT_PREFIX_RE.subn("", text)
    if n:
        changes["course_code_cohort_prefix"] = n

    text, n = _BULLET_RE.subn(" – ", text)
    if n:
        changes["bullet_marker"] = n

    text, n = _UNIT_SYNONYM_RE.subn(r"\1UNIT", text)
    if n:
        changes["unit_header_synonym"] = n

    text, n = _OBJECTIVES_SYNONYM_RE.subn("OBJECTIVES:", text)
    if n:
        changes["objectives_header_synonym"] = n

    text, n = _TEXTBOOK_SYNONYM_RE.subn("TEXT BOOKS:", text)
    if n:
        changes["textbook_header_synonym"] = n

    text, n = _REFERENCE_SYNONYM_RE.subn("REFERENCE BOOKS:", text)
    if n:
        changes["reference_header_synonym"] = n

    text, n = _number_bare_syllabus_units(text)
    if n:
        changes["bare_syllabus_unit_numbering"] = n

    return text, changes
