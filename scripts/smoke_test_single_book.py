"""Runs extraction-only stages on a single book and prints its chapter/section
tree -- quick sanity check for TOC/heading-detection changes without paying
for the full pipeline.

Usage: venv/bin/python scripts/smoke_test_single_book.py "books/<file>.pdf"
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from extractors.book_loader import load_book


def main() -> None:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <path-to-book.pdf>")
        sys.exit(1)

    path = sys.argv[1]
    rec = load_book(path)

    print(f"key: {rec.key}")
    print(f"pages: {rec.doc.num_pages}")
    print(f"used_fallback_headings: {rec.used_fallback_headings}")
    print(f"title: {rec.metadata.title!r}  authors: {rec.metadata.authors!r}")
    print(f"chapters: {len(rec.chapters)}")
    print()

    for ch in rec.chapters:
        print(f"  {ch.label or '-'} | {ch.title!r} | pdf pages {ch.page_start}-{ch.page_end} | book pages {ch.book_page_start}-{ch.book_page_end} | {len(ch.sections)} sections")
        for sec in ch.sections[:5]:
            print(f"      {sec.label or '-'} | {sec.title!r} | pdf pages {sec.page_start}-{sec.page_end} | book pages {sec.book_page_start}-{sec.book_page_end}")
        if len(ch.sections) > 5:
            print(f"      ... and {len(ch.sections) - 5} more sections")


if __name__ == "__main__":
    main()
