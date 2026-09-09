"""Flattens a book's Chapter/Section tree into flat Chunk objects: one per
section when a chapter has parsed sections, otherwise one per chapter."""
from dataclasses import dataclass
from typing import List, Optional

import config
from extractors.chapter_builder import Chapter
from indexing.text_cleaner import clean_text
from pdfcore.pdf_reader import PDFDocument


@dataclass
class Chunk:
    chunk_id: str
    book_key: str
    chapter_label: str
    chapter_title: str
    section_label: str
    section_title: str
    page_start: int  # 0-indexed position within the PDF file
    page_end: int
    text: str
    book_page_start: Optional[int] = None  # printed page number as it appears in the book
    book_page_end: Optional[int] = None


def _bounded_text(doc: PDFDocument, page_start: int, page_end: int) -> str:
    capped_end = min(page_end, page_start + config.MAX_CHUNK_PAGES - 1)
    return clean_text(doc.full_text(page_start, capped_end))


def generate_chunks(doc: PDFDocument, chapters: List[Chapter], book_key: str) -> List[Chunk]:
    chunks: List[Chunk] = []
    for chapter in chapters:
        if chapter.sections:
            for section in chapter.sections:
                text = _bounded_text(doc, section.page_start, section.page_end)
                chunk_id = f"{book_key}::{chapter.label}::{section.label or section.title}"
                chunks.append(
                    Chunk(
                        chunk_id=chunk_id,
                        book_key=book_key,
                        chapter_label=chapter.label,
                        chapter_title=chapter.title,
                        section_label=section.label,
                        section_title=section.title,
                        page_start=section.page_start,
                        page_end=section.page_end,
                        text=text,
                        book_page_start=section.book_page_start,
                        book_page_end=section.book_page_end,
                    )
                )
        else:
            text = _bounded_text(doc, chapter.page_start, chapter.page_end)
            chunk_id = f"{book_key}::{chapter.label}::_"
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    book_key=book_key,
                    chapter_label=chapter.label,
                    chapter_title=chapter.title,
                    section_label="",
                    section_title="",
                    page_start=chapter.page_start,
                    page_end=chapter.page_end,
                    text=text,
                    book_page_start=chapter.book_page_start,
                    book_page_end=chapter.book_page_end,
                )
            )
    return chunks
