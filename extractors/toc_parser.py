"""
Parses raw TOC page text into structured TOCEntry objects: number, title,
printed page number, and a nesting level derived from the numbering scheme
(e.g. "4" = level 1, "4.2" = level 2, "4.2.3" = level 3).

Supports: dotted-leader TOCs, plain "title ... page" TOCs, UNIT/PART/Chapter
prefixed entries, Roman numeral parts, and titles that wrap across two (or
occasionally three) physical lines in the source PDF - a single logical
entry like

    "8.1 The Matrix Eigenvalue Problem."
    "Determining Eigenvalues and Eigenvectors 323"

is joined into one entry (label "8.1", page 323) instead of losing the
first line (no trailing page number) and mis-parsing the second line in
isolation.
"""
import re
from dataclasses import dataclass
from typing import List, Optional

from indexing.text_cleaner import repair_spacing
from utils.roman import is_roman_numeral, roman_to_int
from utils.logger import log

# Matches a leading numbering token: "4.2.3", "4", "I", "IV", "Appendix II"
LEAD_NUM_RE = re.compile(
    r"^\s*(Appendix|Chapter|Unit|Part|Module)?\s*"
    r"((?:\d+\.)+\d+|\d+\.?|[IVXLCDM]+)?\s*[:.]?\s*(.*)$",
    re.IGNORECASE,
)
# A TOC line's trailing page number. PDF text extraction occasionally
# inserts a single stray space *inside* a multi-digit number because of
# font kerning (observed for real: "10" extracts as "1 0", "225" as "2 25"
# or "22 5"). Naively matching only a contiguous digit run therefore grabs
# just the last digit and leaves the rest of the number stuck in the title.
# This pattern instead matches up to 4 digits, each optionally followed by
# a single space, and the digits are rejoined (spaces stripped) below.
TRAILING_PAGE_RE = re.compile(r"(?:\d\s?){1,4}$")
_DIGIT_RE = re.compile(r"\d")
MAX_PLAUSIBLE_PAGE = 3000  # sanity ceiling; discards obviously-garbled matches
DOTTED_LEADER_STRIP_RE = re.compile(r"\.{2,}|(?:\s\.){2,}\s?")
MULTI_DOT_RE = re.compile(r"\.\s*(?=\.)")  # collapses ". . . . ." style leaders

# A line that looks like the START of a brand-new TOC entry (real numbering
# or an explicit Chapter/Unit/Part/Appendix/Module prefix). Used to stop the
# line-joining lookahead from swallowing the *next real entry* when the
# current one never finds its page number.
NEW_ENTRY_START_RE = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*\.?\s|Appendix\b|Chapter\b|Unit\b|Part\b|Module\b)",
    re.IGNORECASE,
)
MAX_LOOKAHEAD_LINES = 2       # how many extra lines we'll fold into one entry
MAX_COMBINED_CHARS = 220      # safety cap so we never glue a whole paragraph together


@dataclass
class TOCEntry:
    raw_line: str
    label: str            # e.g. "4.2", "I", "Appendix II", "" if none
    title: str
    page: Optional[int]
    level: int             # 1 = chapter/unit/part, 2 = section, 3 = subsection


def _numbering_level(label: str) -> int:
    if not label:
        return 1
    label = label.strip()
    if re.match(r"^\d+(\.\d+)+$", label):
        return label.count(".") + 1
    return 1


def _clean_leader_dots(line: str) -> str:
    # Collapse "Title . . . . . . 45" and "Title......45" leaders into one space
    line = MULTI_DOT_RE.sub("", line)
    line = DOTTED_LEADER_STRIP_RE.sub(" ", line)
    return line


def _parse_entry_text(combined: str, raw_source: str) -> Optional[TOCEntry]:
    """Turn one already-joined logical TOC line (title + trailing page
    number, leader dots and all) into a TOCEntry, or None if it doesn't
    look like a real entry."""
    page_match = TRAILING_PAGE_RE.search(combined)
    if not page_match:
        return None
    digits = "".join(_DIGIT_RE.findall(page_match.group(0)))
    if not digits:
        return None
    page_num = int(digits)
    if page_num == 0 or page_num > MAX_PLAUSIBLE_PAGE:
        return None  # almost certainly a mis-parsed fragment, not a real page ref

    body = combined[:page_match.start()].strip()
    body = _clean_leader_dots(body)
    if not body:
        return None

    m = LEAD_NUM_RE.match(body)
    prefix_word = (m.group(1) or "").strip() if m else ""
    label_token = (m.group(2) or "").strip().rstrip(".") if m else ""
    title = (m.group(3) or body).strip() if m else body

    # A BARE (no Chapter/Unit/Part/Appendix prefix) single-letter token that
    # happens to be a roman-numeral character (I, V, X, L, C, D, M) is far
    # more often just the first letter of an ordinary title word
    # ("Vector...", "Determining...", "Complex...") than real numbering -
    # only trust an unprefixed roman numeral if it's at least 2 characters.
    if not prefix_word and label_token and re.match(r"^[IVXLCDM]+$", label_token, re.IGNORECASE) \
            and len(label_token) < 2:
        title = (label_token + title).strip() if title else label_token
        label_token = ""

    if prefix_word and label_token:
        label = f"{prefix_word} {label_token}".strip()
    elif prefix_word:
        label = prefix_word
    else:
        label = label_token

    title = repair_spacing(title) if title else title
    title = title.strip(" -:.")
    if not title or len(title) < 2:
        return None

    level = _numbering_level(label_token)
    return TOCEntry(raw_line=raw_source, label=label, title=title, page=page_num, level=level)


def parse_toc_lines(lines: List[str]) -> List[TOCEntry]:
    entries: List[TOCEntry] = []
    cleaned = [l.strip() for l in lines]
    n = len(cleaned)
    i = 0
    while i < n:
        line = cleaned[i]
        if not line or len(line) < 2:
            i += 1
            continue
        if line.lower().startswith(("contents", "table of contents", "index")):
            i += 1
            continue

        combined = line
        raw_source = line
        end_idx = i
        lookahead = 0
        # Keep folding in the next line(s) as long as (a) we haven't found a
        # trailing page number yet, (b) we haven't exceeded our lookahead/
        # length budget, and (c) the next line doesn't itself look like the
        # start of a fresh entry (which would mean THIS line simply never
        # had a page number - e.g. a stray running header - and shouldn't
        # swallow whatever comes next).
        while (TRAILING_PAGE_RE.search(combined) is None
               and lookahead < MAX_LOOKAHEAD_LINES
               and (end_idx + 1) < n
               and len(combined) < MAX_COMBINED_CHARS):
            nxt = cleaned[end_idx + 1]
            if not nxt or NEW_ENTRY_START_RE.match(nxt):
                break
            combined = f"{combined} {nxt}"
            raw_source = f"{raw_source} | {nxt}"
            end_idx += 1
            lookahead += 1

        entry = _parse_entry_text(combined, raw_source)
        if entry is not None:
            entries.append(entry)
            i = end_idx + 1
        else:
            i += 1

    return entries


def parse_toc(doc, toc_pages: List[int]) -> List[TOCEntry]:
    if not toc_pages:
        return []
    all_lines: List[str] = []
    for pn in toc_pages:
        page = doc.get_pages(pn, pn)[0]
        all_lines.extend(page.lines)
    entries = parse_toc_lines(all_lines)
    log(f"Parsed {len(entries)} TOC entries from pages {toc_pages}")
    return entries
