"""
Extracts Title / Authors / Edition / Publisher / Year for a book PDF.

Priority order (per the design spec):
  1. PDF document metadata (/Title, /Author)
  2. Filename (very reliable in practice - most repositories name files
     "Title_Author1_Author2.pdf")
  3. Cover / copyright page text scan (first 3 pages) via regex heuristics
"""
import os
import re
from dataclasses import dataclass, asdict
from typing import Optional

from pypdf import PdfReader as _PypdfReader
from utils.logger import log

EDITION_RE = re.compile(r"(\d+)(st|nd|rd|th)\s+Edition", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
PUBLISHER_HINTS = [
    "Wiley", "McGraw-Hill", "McGraw Hill", "Pearson", "Springer", "Elsevier",
    "Prentice Hall", "CRC Press", "Cengage", "Oxford", "Cambridge University Press",
    "Taylor & Francis", "PHI Learning", "New Age", "Butterworth",
]


@dataclass
class BookMetadata:
    file_path: str
    title: str = ""
    authors: str = ""
    edition: str = ""
    publisher: str = ""
    year: str = ""
    isbn: str = ""
    book_type: str = "Reference"  # Textbook / Reference - refined later by matcher

    def as_dict(self):
        return asdict(self)


def _title_from_filename(path: str) -> (str, str):
    """Guess (title, authors) from a filename like
    'Additive_manufacturing_technologies_Ian_Gibson__David_Rosen'.
    Convention observed: title words then author names, both underscore
    separated, with a double-underscore acting as an author separator."""
    stem = os.path.splitext(os.path.basename(path))[0]
    # Split on double-underscore first -> author boundaries
    parts = re.split(r"_{2,}", stem)
    parts = [p.strip("_") for p in parts if p.strip("_")]
    words = [p.replace("_", " ").strip() for p in parts]

    if len(words) == 1:
        # No clear author boundary - can't safely split, treat whole as title
        return words[0], ""

    # Heuristic: the first chunk that "looks like a proper title" (multiple
    # words, mostly lowercase-able common words) is the title; remaining
    # chunks - each usually "Firstname Lastname" - are authors.
    title_words = []
    author_words = []
    seen_author_start = False
    for chunk in words:
        tokens = chunk.split()
        # A chunk of exactly 1-3 capitalized short tokens strongly suggests a person's name
        looks_like_name = (1 <= len(tokens) <= 3) and all(t[:1].isupper() for t in tokens if t)
        if not seen_author_start and looks_like_name and title_words:
            seen_author_start = True
        if seen_author_start:
            author_words.append(chunk)
        else:
            title_words.append(chunk)

    title = " ".join(title_words).strip()
    authors = ", ".join(author_words).strip()
    return title, authors


def _scan_first_pages(path: str, num_pages: int = 3) -> str:
    try:
        reader = _PypdfReader(path)
        text_chunks = []
        for i in range(min(num_pages, len(reader.pages))):
            try:
                text_chunks.append(reader.pages[i].extract_text() or "")
            except Exception:
                continue
        return "\n".join(text_chunks)
    except Exception as e:
        log(f"Could not scan front pages of {path}: {e}", "WARN")
        return ""


def extract_metadata(path: str) -> BookMetadata:
    meta = BookMetadata(file_path=path)

    # 1. PDF /Info dictionary
    doc_title, doc_author = "", ""
    try:
        reader = _PypdfReader(path)
        info = reader.metadata or {}
        doc_title = (info.title or "").strip() if hasattr(info, "title") else ""
        doc_author = (info.author or "").strip() if hasattr(info, "author") else ""
    except Exception as e:
        log(f"PDF metadata read failed for {path}: {e}", "WARN")

    # 2. Filename heuristic (used as fallback / cross-check)
    fn_title, fn_authors = _title_from_filename(path)

    meta.title = doc_title if len(doc_title) > 4 else fn_title
    meta.authors = doc_author if doc_author else fn_authors

    # 3. Front-page scan for edition / year / publisher
    front_text = _scan_first_pages(path)
    ed_match = EDITION_RE.search(front_text)
    if ed_match:
        meta.edition = f"{ed_match.group(1)}{ed_match.group(2)}"
    year_matches = YEAR_RE.findall(front_text)
    if year_matches:
        # findall with groups returns only the group; re-search full match instead
        all_years = YEAR_RE.finditer(front_text)
        years = [int(m.group(0)) for m in all_years]
        if years:
            meta.year = str(max(years))  # most recent copyright year on the page
    for pub in PUBLISHER_HINTS:
        if pub.lower() in front_text.lower():
            meta.publisher = pub
            break

    log(f"Metadata for {os.path.basename(path)}: title='{meta.title}' authors='{meta.authors}' "
        f"edition='{meta.edition}' year='{meta.year}' publisher='{meta.publisher}'")
    return meta
