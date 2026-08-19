"""
Flattens a book's Chapter -> Section tree into a flat list of Chunk objects
that the matcher can score against syllabus topics. We index at section
granularity when sections exist (finer, more precise matches) and fall back
to chapter granularity otherwise.
"""
from dataclasses import dataclass
from typing import List

from extractors.chapter_builder import Chapter
from extractors.pdf_reader import PDFDocument
from indexing.text_cleaner import clean_text
import config


@dataclass
class Chunk:
    book_key: str
    chapter_label: str
    chapter_title: str
    section_label: str      # "" if this chunk IS the chapter (no finer section)
    section_title: str
    page_start: int
    page_end: int
    text: str


def _truncate_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words])


def _bounded_text(doc: PDFDocument, page_start: int, page_end: int) -> str:
    """Extract text for indexing purposes only, capped to MAX_CHUNK_PAGES so a
    chapter that (legitimately) spans hundreds of pages doesn't blow up memory
    or extraction time. The chunk's reported page_start/page_end stays the
    true full range - only the text used for scoring is capped."""
    capped_end = min(page_end, page_start + config.MAX_CHUNK_PAGES - 1)
    raw = doc.full_text(page_start, capped_end)
    return clean_text(raw)


def generate_chunks(doc: PDFDocument, chapters: List[Chapter], book_key: str) -> List[Chunk]:
    chunks: List[Chunk] = []
    for ch in chapters:
        if ch.sections:
            for sec in ch.sections:
                text = _bounded_text(doc, sec.page_start, sec.page_end)
                text = _truncate_words(text, config.CHUNK_SIZE_WORDS * 3)
                chunks.append(Chunk(
                    book_key=book_key, chapter_label=ch.label, chapter_title=ch.title,
                    section_label=sec.label, section_title=sec.title,
                    page_start=sec.page_start, page_end=sec.page_end, text=text,
                ))
        else:
            text = _bounded_text(doc, ch.page_start, ch.page_end)
            text = _truncate_words(text, config.CHUNK_SIZE_WORDS * 3)
            chunks.append(Chunk(
                book_key=book_key, chapter_label=ch.label, chapter_title=ch.title,
                section_label="", section_title="",
                page_start=ch.page_start, page_end=ch.page_end, text=text,
            ))
    return chunks
