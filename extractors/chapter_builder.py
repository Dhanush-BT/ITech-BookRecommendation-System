"""Converts a flat, page-resolved TOC entry list into a Chapter -> Section tree
with page ranges. Level-1 entries become chapters; level>=2 entries nest under
the nearest preceding chapter as sections. A chapter's page range is extended
to cover all of its sections."""
from dataclasses import dataclass, field
from typing import List, Optional

from pdfcore.pdf_reader import PDFDocument
from extractors.page_mapper import ResolvedTOCEntry


@dataclass
class Section:
    label: str
    title: str
    page_start: int
    page_end: int
    level: int = 2

    def text(self, doc: PDFDocument) -> str:
        return doc.full_text(self.page_start, self.page_end)


@dataclass
class Chapter:
    label: str
    title: str
    page_start: int
    page_end: int
    sections: List[Section] = field(default_factory=list)

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

    for i, r in enumerate(filtered):
        entry = r.entry
        next_page = filtered[i + 1].pdf_page if i + 1 < n else doc.num_pages
        page_end = max(r.pdf_page, next_page - 1)

        if entry.level <= 1:
            current_chapter = Chapter(
                label=entry.label, title=entry.title, page_start=r.pdf_page, page_end=page_end
            )
            chapters.append(current_chapter)
        else:
            section = Section(
                label=entry.label,
                title=entry.title,
                page_start=r.pdf_page,
                page_end=page_end,
                level=entry.level,
            )
            if current_chapter is None:
                current_chapter = Chapter(
                    label=section.label,
                    title=section.title,
                    page_start=section.page_start,
                    page_end=section.page_end,
                )
                chapters.append(current_chapter)
            else:
                current_chapter.sections.append(section)
                current_chapter.page_end = max(current_chapter.page_end, page_end)

    return chapters
