"""Extracts book metadata (title/authors/edition/publisher/year) from the PDF's
own info dict where available, falling back to filename heuristics (observed
convention in this corpus: "Title_Author One, Author Two.pdf") and a light
regex scan of the first couple of pages for edition/publisher/year."""
import os
import re
from dataclasses import dataclass

from pdfcore.pdf_reader import PDFDocument

_EDITION_RE = re.compile(r"(\d+)(?:st|nd|rd|th)\s+Edition", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_GENERIC_TITLES = {"", "untitled", "microsoft word", "document"}


@dataclass
class BookMetadata:
    file_path: str
    title: str = ""
    authors: str = ""
    edition: str = ""
    publisher: str = ""
    year: str = ""
    isbn: str = ""
    book_type: str = "Reference"


def _title_authors_from_filename(path: str):
    stem = os.path.splitext(os.path.basename(path))[0]
    stem = stem.replace("_", "_")  # no-op, keeps intent explicit
    if "_" in stem:
        title, _, authors = stem.partition("_")
    else:
        title, authors = stem, ""
    title = re.sub(r"[-_]+", " ", title).strip()
    authors = authors.replace("_", ", ").strip(" ,")
    return title, authors


def extract_metadata(path: str, doc: PDFDocument) -> BookMetadata:
    filename_title, filename_authors = _title_authors_from_filename(path)

    pdf_meta = doc.metadata
    pdf_title = str(pdf_meta.get("/Title", "") or "").strip()
    pdf_author = str(pdf_meta.get("/Author", "") or "").strip()

    title = pdf_title if pdf_title.lower() not in _GENERIC_TITLES and len(pdf_title) > 3 else filename_title
    authors = pdf_author if pdf_author else filename_authors

    front_text = doc.full_text(0, min(4, doc.num_pages - 1)) if doc.num_pages else ""
    edition_match = _EDITION_RE.search(front_text)
    edition = edition_match.group(0) if edition_match else ""

    year_candidates = _YEAR_RE.findall(front_text)
    year = ""
    if year_candidates:
        # findall with groups returns the group, not the full match; re-search properly
        all_years = _YEAR_RE.finditer(front_text)
        years = [int(m.group(0)) for m in all_years]
        if years:
            year = str(max(y for y in years if 1900 <= y <= 2100))

    return BookMetadata(
        file_path=path,
        title=title or filename_title or os.path.basename(path),
        authors=authors,
        edition=edition,
        publisher="",
        year=year,
        isbn="",
        book_type="Reference",
    )
