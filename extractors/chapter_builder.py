"""
Turns a flat, page-resolved TOC entry list into a Chapter -> Section tree,
each node carrying a concrete PDF page range so its body text can be pulled
on demand for indexing/matching.
"""
from dataclasses import dataclass, field
from typing import List, Optional

from extractors.pdf_reader import PDFDocument
from extractors.toc_parser import TOCEntry
from indexing.text_cleaner import clean_text
from utils.logger import log


@dataclass
class Section:
    label: str
    title: str
    page_start: int
    page_end: int
    level: int = 2

    def text(self, doc: PDFDocument) -> str:
        if self.page_end < self.page_start:
            return ""
        raw = doc.full_text(self.page_start, self.page_end)
        return clean_text(raw)


@dataclass
class Chapter:
    label: str
    title: str
    page_start: int
    page_end: int
    sections: List[Section] = field(default_factory=list)

    def text(self, doc: PDFDocument) -> str:
        if self.page_end < self.page_start:
            return ""
        raw = doc.full_text(self.page_start, self.page_end)
        return clean_text(raw)


def build_chapters(doc: PDFDocument, resolved_entries: List[TOCEntry]) -> List[Chapter]:
    if not resolved_entries:
        return []

    ordered = sorted(resolved_entries, key=lambda e: (e.page, e.level))
    last_page = doc.num_pages

    # compute page_end for every entry as (next entry's page - 1)
    ranges = []
    for i, e in enumerate(ordered):
        if i + 1 < len(ordered):
            end = max(e.page, ordered[i + 1].page - 1)
        else:
            end = last_page
        ranges.append((e, e.page, end))

    chapters: List[Chapter] = []
    current_chapter: Optional[Chapter] = None

    for entry, start, end in ranges:
        if entry.level <= 1:
            current_chapter = Chapter(label=entry.label or str(len(chapters) + 1),
                                       title=entry.title, page_start=start, page_end=end)
            chapters.append(current_chapter)
        else:
            sec = Section(label=entry.label, title=entry.title, page_start=start,
                           page_end=end, level=entry.level)
            if current_chapter is None:
                # Orphan section before any chapter heading was seen - promote it
                current_chapter = Chapter(label=entry.label or str(len(chapters) + 1),
                                           title=entry.title, page_start=start, page_end=end)
                chapters.append(current_chapter)
            else:
                current_chapter.sections.append(sec)
                # keep the chapter's own page_end in sync with its last section
                current_chapter.page_end = max(current_chapter.page_end, end)

    log(f"Built {len(chapters)} chapters "
        f"({sum(len(c.sections) for c in chapters)} sections total)")
    return chapters
