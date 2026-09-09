"""Parses raw TOC page text into structured TOCEntry objects, handling wrapped
title lines (title on one line, page number on the next) and dotted leaders."""
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from pdfcore.pdf_reader import PDFDocument
from utils.regex_patterns import TOC_DOTTED_LEADER_RE, TOC_TRAILING_PAGE_RE

_NUMERIC_LABEL_RE = re.compile(r"^(\d+(?:\.\d+)*)[\.\):]?\s+(.*)$")
_CHAPTER_LABEL_RE = re.compile(r"^(Chapter|Unit|Part)\s+(\d+|[IVXLCDM]+)[\.\):]?\s*(.*)$", re.IGNORECASE)
_NOISE_LINE_RE = re.compile(r"^(CONTENTS?|TABLE OF CONTENTS|[ivxlcdm]+|\d{1,4})$", re.IGNORECASE)
# A running "Contents" / "iv Contents" / "Contents ix" page header often gets
# glued onto the first real TOC line of a page by the extractor -- strip that
# leak so it doesn't become (part of) an entry title.
_CONTENTS_HEADER_RE = re.compile(
    r"^(?:[ivxlcdm]{1,6}\s+)?contents\s+(?:[ivxlcdm]{1,6}\s+)?", re.IGNORECASE
)

# Front-matter TOC lines (Preface, Acknowledgments, ...) are often paginated with
# roman numerals, which never match a digit-page pattern below and would otherwise
# accumulate into `pending` indefinitely. Cap it so an unresolvable run of lines
# gets dropped instead of glomming onto whatever entry resolves next.
_MAX_PENDING_WORDS = 25


@dataclass
class TOCEntry:
    raw_line: str
    label: str
    title: str
    page: Optional[int]
    level: int


def _split_label(text: str) -> Tuple[str, str, int]:
    m = _NUMERIC_LABEL_RE.match(text)
    if m:
        label = m.group(1)
        title = m.group(2).strip(" .-")
        level = label.count(".") + 1
        return label, title or label, level

    m = _CHAPTER_LABEL_RE.match(text)
    if m:
        label = f"{m.group(1)} {m.group(2)}"
        title = m.group(3).strip(" .-")
        return label, title or label, 1

    # no numeric/chapter prefix: only trust ALL-CAPS as a genuine chapter-level
    # heading signal. Short Title-Case fragments ("Problems", "Exercises") are
    # usually per-chapter boilerplate entries, not new chapters — default those
    # to level 2 so they nest under the preceding chapter instead of fragmenting
    # the tree into spurious top-level chapters.
    is_headingish = text.isupper() and len(text.split()) >= 2
    return "", text, 1 if is_headingish else 2


def parse_toc(doc: PDFDocument, start_page: int, end_page: int) -> List[TOCEntry]:
    raw_lines: List[str] = []
    for page in doc.get_pages(start_page, end_page):
        raw_lines.extend(page.text.split("\n"))

    entries: List[TOCEntry] = []
    pending = ""

    for raw in raw_lines:
        line = raw.strip()
        if not line:
            continue
        if _NOISE_LINE_RE.match(line):
            continue

        m = TOC_DOTTED_LEADER_RE.match(line) or TOC_TRAILING_PAGE_RE.match(line)
        if m:
            title_part = m.group(1).strip(" .")
            try:
                page_num = int(m.group(2))
            except ValueError:
                continue
            if not (0 < page_num < 5000):
                continue
            full_title = f"{pending} {title_part}".strip() if pending else title_part
            pending = ""
            full_title = _CONTENTS_HEADER_RE.sub("", full_title).strip()
            if not full_title:
                continue
            label, title, level = _split_label(full_title)
            entries.append(TOCEntry(raw_line=raw, label=label, title=title, page=page_num, level=level))
        else:
            pending = f"{pending} {line}".strip() if pending else line
            if len(pending.split()) > _MAX_PENDING_WORDS:
                pending = line

    return entries
