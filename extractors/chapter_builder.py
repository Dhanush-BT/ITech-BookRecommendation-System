"""Converts a flat, page-resolved TOC entry list into a Chapter -> Section tree
with page ranges. Level-1 entries become chapters; level>=2 entries nest under
the nearest preceding chapter as sections. A chapter's page range is extended
to cover all of its sections."""
import re
from dataclasses import dataclass, field
from typing import List, Optional

from pdfcore.pdf_reader import PDFDocument
from extractors.page_mapper import ResolvedTOCEntry

_SECTION_LABEL_RE = re.compile(r"^(\d+)\.\d")
_CHAPTER_LABEL_RE = re.compile(r"(\d+)\s*$")


def _chapter_number(label: str) -> Optional[str]:
    """The leading integer of a '3' / 'Chapter 3' chapter label."""
    m = _CHAPTER_LABEL_RE.search(label or "")
    return m.group(1) if m else None


def _section_chapter_number(label: str) -> Optional[str]:
    """The chapter part of a '3.4' / '14.2.1' section label."""
    m = _SECTION_LABEL_RE.match(label or "")
    return m.group(1) if m else None


@dataclass
class Section:
    label: str
    title: str
    page_start: int  # 0-indexed position within the PDF file
    page_end: int
    level: int = 2
    book_page_start: Optional[int] = None  # printed page number as it appears in the book
    book_page_end: Optional[int] = None

    def text(self, doc: PDFDocument) -> str:
        return doc.full_text(self.page_start, self.page_end)


@dataclass
class Chapter:
    label: str
    title: str
    page_start: int
    page_end: int
    sections: List[Section] = field(default_factory=list)
    book_page_start: Optional[int] = None
    book_page_end: Optional[int] = None

    def text(self, doc: PDFDocument) -> str:
        return doc.full_text(self.page_start, self.page_end)


def build_chapters(doc: PDFDocument, resolved: List[ResolvedTOCEntry]) -> List[Chapter]:
    valid = [r for r in resolved if r.pdf_page is not None]

    filtered: List[ResolvedTOCEntry] = []
    last_page = -1
    for r in valid:
        if r.pdf_page < last_page:
            continue
        filtered.append(r)
        last_page = r.pdf_page

    if not filtered:
        return []

    n = len(filtered)
    chapters: List[Chapter] = []
    current_chapter: Optional[Chapter] = None
    current_chapter_number: Optional[str] = None
    current_chapter_is_explicit = False  # came from a real level<=1 TOC row

    # Some books (Stewart's Calculus, ...) print each chapter as a bare, styled
    # numeral that pypdf drops entirely, so the TOC parses as a flat list of
    # "N.M" section entries with no chapter rows at all -- which would collapse
    # the whole book into one Chapter. The section branch below synthesises a
    # chapter each time the section number's integer part changes.
    for i, r in enumerate(filtered):
        entry = r.entry
        next_page = filtered[i + 1].pdf_page if i + 1 < n else doc.num_pages
        page_end = max(r.pdf_page, next_page - 1)

        # entry.page is the page number as printed in the book's own TOC (or,
        # for heading-fallback books with no TOC, just the PDF page number --
        # the best available stand-in). Its END is bounded by the next
        # entry's book-page number when known, falling back to spanning the
        # same page count as the resolved PDF range for a trailing entry.
        book_page_start = entry.page
        next_entry = filtered[i + 1].entry if i + 1 < n else None
        if next_entry is not None:
            book_page_end = max(book_page_start, next_entry.page - 1)
        else:
            book_page_end = book_page_start + (page_end - r.pdf_page)

        if entry.level <= 1:
            current_chapter = Chapter(
                label=entry.label,
                title=entry.title,
                page_start=r.pdf_page,
                page_end=page_end,
                book_page_start=book_page_start,
                book_page_end=book_page_end,
            )
            current_chapter_number = _chapter_number(entry.label)
            current_chapter_is_explicit = True
            chapters.append(current_chapter)
        else:
            section = Section(
                label=entry.label,
                title=entry.title,
                page_start=r.pdf_page,
                page_end=page_end,
                level=entry.level,
                book_page_start=book_page_start,
                book_page_end=book_page_end,
            )
            sec_chapter_number = _section_chapter_number(entry.label)
            # "N.M" section whose chapter part isn't the chapter we're in -> the
            # real chapter row for N was dropped from the TOC; start one. Don't
            # do this when we're sitting in a real, titled (but unnumbered)
            # level-1 chapter -- there the title is the better grouping.
            crossed_chapter_boundary = (
                sec_chapter_number is not None
                and sec_chapter_number != current_chapter_number
                and not (current_chapter_is_explicit and current_chapter_number is None)
            )

            if current_chapter is None or crossed_chapter_boundary:
                if sec_chapter_number is not None:
                    current_chapter = Chapter(
                        label=sec_chapter_number,
                        title="",  # real chapter title isn't recoverable from the TOC here
                        page_start=section.page_start,
                        page_end=section.page_end,
                        book_page_start=section.book_page_start,
                        book_page_end=section.book_page_end,
                        sections=[section],
                    )
                    current_chapter_number = sec_chapter_number
                    current_chapter_is_explicit = False
                else:
                    current_chapter = Chapter(
                        label=section.label,
                        title=section.title,
                        page_start=section.page_start,
                        page_end=section.page_end,
                        book_page_start=section.book_page_start,
                        book_page_end=section.book_page_end,
                    )
                    current_chapter_number = None
                    current_chapter_is_explicit = False
                chapters.append(current_chapter)
            else:
                current_chapter.sections.append(section)
                current_chapter.page_end = max(current_chapter.page_end, page_end)
                current_chapter.book_page_end = max(current_chapter.book_page_end, book_page_end)

    return chapters
