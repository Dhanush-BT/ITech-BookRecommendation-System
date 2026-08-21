"""Orchestrates the per-book extraction pipeline: metadata -> TOC detect/parse
-> page-offset resolution -> chapter/section tree, falling back to font-based
heading detection when the TOC is missing or too sparse."""
import os
from dataclasses import dataclass, field
from typing import List

import config
from extractors.chapter_builder import Chapter, build_chapters
from extractors.heading_detector import detect_headings_by_font
from extractors.metadata_extractor import BookMetadata, extract_metadata
from extractors.page_mapper import resolve_page_offsets
from extractors.toc_detector import detect_toc_pages
from extractors.toc_parser import parse_toc
from pdfcore.pdf_reader import PDFDocument, get_document
from utils.logger import log


@dataclass
class BookRecord:
    key: str
    path: str
    metadata: BookMetadata
    chapters: List[Chapter] = field(default_factory=list)
    used_fallback_headings: bool = False
    doc: PDFDocument = None


def _book_key(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def load_book(path: str) -> BookRecord:
    doc = get_document(path)
    key = _book_key(path)
    metadata = extract_metadata(path, doc)

    chapters: List[Chapter] = []
    used_fallback = False

    toc_range = detect_toc_pages(doc)
    toc_entries = parse_toc(doc, *toc_range) if toc_range else []

    if len(toc_entries) >= config.MIN_TOC_ENTRIES:
        resolved, _offset = resolve_page_offsets(doc, toc_entries)
        chapters = build_chapters(doc, resolved)

    if not chapters and config.USE_HEADING_FALLBACK:
        heading_resolved = detect_headings_by_font(doc, path)
        if heading_resolved:
            chapters = build_chapters(doc, heading_resolved)
            used_fallback = True

    if not chapters:
        log(f"WARNING: no chapter structure found for {key} (num_pages={doc.num_pages})")

    return BookRecord(
        key=key,
        path=path,
        metadata=metadata,
        chapters=chapters,
        used_fallback_headings=used_fallback,
        doc=doc,
    )


def load_books(books_dir: str = config.BOOKS_DIR) -> List[BookRecord]:
    records = []
    paths = sorted(
        os.path.join(books_dir, f) for f in os.listdir(books_dir) if f.lower().endswith(".pdf")
    )
    for i, path in enumerate(paths, 1):
        log(f"[{i}/{len(paths)}] loading {os.path.basename(path)} ...")
        try:
            records.append(load_book(path))
        except Exception as exc:
            log(f"WARNING: failed to load {path}: {exc}")
    return records
