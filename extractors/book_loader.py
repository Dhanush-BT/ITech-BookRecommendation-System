"""
Orchestrates the per-book extraction pipeline (Phases 2-7 of the design):
  Book PDF -> metadata -> TOC detection -> TOC parsing -> page offset
  resolution -> chapter/section tree -> (fallback to font-based heading
  detection if no usable TOC was found).
"""
from dataclasses import dataclass, field
from typing import List
import os

from extractors.pdf_reader import PDFDocument, get_document
from extractors.metadata_extractor import extract_metadata, BookMetadata
from extractors.toc_detector import detect_toc_pages
from extractors.toc_parser import parse_toc, TOCEntry
from extractors.page_mapper import resolve_page_offsets
from extractors.chapter_builder import build_chapters, Chapter
from extractors.heading_detector import detect_headings_by_font
import config
from utils.logger import log, section


@dataclass
class BookRecord:
    key: str
    path: str
    metadata: BookMetadata
    chapters: List[Chapter] = field(default_factory=list)
    used_fallback_headings: bool = False
    doc: PDFDocument = None


def load_book(path: str) -> BookRecord:
    section(f"Loading book: {os.path.basename(path)}")
    key = os.path.splitext(os.path.basename(path))[0]

    doc = get_document(path)
    log(f"Pages: {doc.num_pages}")

    metadata = extract_metadata(path)

    toc_pages = detect_toc_pages(doc)
    entries: List[TOCEntry] = parse_toc(doc, toc_pages) if toc_pages else []

    used_fallback = False
    if len(entries) < 3 and config.USE_HEADING_FALLBACK:
        log("TOC missing or too sparse - falling back to font/heading detection.", "WARN")
        entries = detect_headings_by_font(doc, start_page=1, end_page=min(doc.num_pages, 40))
        used_fallback = True

    resolved = resolve_page_offsets(doc, entries, toc_pages) if toc_pages else entries
    chapters = build_chapters(doc, resolved)

    record = BookRecord(key=key, path=path, metadata=metadata, chapters=chapters,
                         used_fallback_headings=used_fallback, doc=doc)
    log(f"Book '{key}' ready: {len(chapters)} chapters, "
        f"{sum(len(c.sections) for c in chapters)} sections, fallback={used_fallback}")
    return record
