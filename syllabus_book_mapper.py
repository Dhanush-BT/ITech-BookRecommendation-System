#!/usr/bin/env python3
"""
Syllabus <-> Book Recommendation Engine - main entry point.

Usage (individual files):
    python3 syllabus_book_mapper.py --syllabus <path.pdf> [<path2.pdf> ...] \
                                     --books <book1.pdf> [<book2.pdf> ...] \
                                     --output output/recommendations.xlsx

Usage (folders - every .pdf inside is picked up automatically):
    python3 syllabus_book_mapper.py --syllabus ./syllabus_folder \
                                     --books ./books_folder \
                                     --output output/recommendations.xlsx

--syllabus and --books accept any mix of individual PDF paths and directory
paths in the same invocation; directories are expanded to every .pdf file
they contain (add --recursive to also descend into subfolders).
"""
import argparse
import glob
import os
import sys
import traceback

from extractors.book_loader import load_book, BookRecord
from syllabus.syllabus_parser import parse_syllabus_pdf, SyllabusCourse
from matcher.recommendation_ranker import build_corpus, generate_recommendations
from exporter.excel_exporter import export_to_excel
from utils.logger import log, section
import config


def resolve_pdf_paths(inputs: list[str], recursive: bool = False) -> list[str]:
    """Expand a mixed list of file paths and directory paths into a flat,
    de-duplicated, sorted list of .pdf file paths. Directories are searched
    top-level by default; pass recursive=True to also descend into
    subfolders. Non-existent paths and non-PDF files are skipped with a
    warning rather than aborting the whole run."""
    resolved: list[str] = []
    seen = set()

    for raw_path in inputs:
        if not os.path.exists(raw_path):
            log(f"Path not found, skipping: {raw_path}", "ERROR")
            continue

        if os.path.isdir(raw_path):
            pattern = "**/*.pdf" if recursive else "*.pdf"
            found = sorted(glob.glob(os.path.join(raw_path, pattern), recursive=recursive))
            if not found:
                log(f"No .pdf files found in directory: {raw_path}"
                    f"{' (searched recursively)' if recursive else ' (top-level only - try --recursive)'}",
                    "WARN")
            for f in found:
                key = os.path.abspath(f)
                if key not in seen:
                    seen.add(key)
                    resolved.append(f)
            log(f"Expanded directory '{raw_path}' -> {len(found)} PDF file(s)")
        elif os.path.isfile(raw_path):
            if raw_path.lower().endswith(".pdf"):
                key = os.path.abspath(raw_path)
                if key not in seen:
                    seen.add(key)
                    resolved.append(raw_path)
            else:
                log(f"Not a .pdf file, skipping: {raw_path}", "WARN")
        else:
            log(f"Not a file or directory, skipping: {raw_path}", "WARN")

    return resolved


def parse_args():
    p = argparse.ArgumentParser(description="Map syllabus topics to textbook chapters/sections.")
    p.add_argument("--syllabus", nargs="+", required=True,
                   help="One or more syllabus PDF files and/or directories containing PDFs")
    p.add_argument("--books", nargs="+", required=True,
                   help="One or more textbook PDF files and/or directories containing PDFs")
    p.add_argument("--output", default="output/recommendations.xlsx", help="Output .xlsx path")
    p.add_argument("--min-coverage", type=int, default=None,
                   help="Override config.MIN_COVERAGE_PERCENT")
    p.add_argument("--recursive", action="store_true",
                   help="When --syllabus/--books includes a directory, also search its subfolders")
    return p.parse_args()


def main():
    args = parse_args()
    if args.min_coverage is not None:
        config.MIN_COVERAGE_PERCENT = args.min_coverage

    syllabus_paths = resolve_pdf_paths(args.syllabus, recursive=args.recursive)
    book_paths = resolve_pdf_paths(args.books, recursive=args.recursive)
    log(f"Resolved {len(syllabus_paths)} syllabus PDF(s) and {len(book_paths)} book PDF(s) to process")

    if not syllabus_paths:
        log("No syllabus PDFs found from the given --syllabus path(s). Aborting.", "ERROR")
        sys.exit(1)
    if not book_paths:
        log("No book PDFs found from the given --books path(s). Aborting.", "ERROR")
        sys.exit(1)

    section("PHASE 1-2: Loading syllabus documents")
    courses: list[SyllabusCourse] = []
    for path in syllabus_paths:
        try:
            courses.extend(parse_syllabus_pdf(path))
        except Exception as e:
            log(f"Failed to parse syllabus '{path}': {e}", "ERROR")
            traceback.print_exc()

    courses_with_units = [c for c in courses if c.modules]
    log(f"Total courses parsed: {len(courses)} | courses with at least one unit: {len(courses_with_units)}")

    if not courses_with_units:
        log("No syllabus content with units/topics was found. Aborting.", "ERROR")
        sys.exit(1)

    section("PHASE 3-7: Loading book PDFs (metadata, TOC, chapters, sections)")
    book_records: list[BookRecord] = []
    for path in book_paths:
        try:
            book_records.append(load_book(path))
        except Exception as e:
            log(f"Failed to process book '{path}': {e}", "ERROR")
            traceback.print_exc()
            continue  # Phase 14: keep processing remaining books instead of terminating

    book_records = [b for b in book_records if b.chapters]
    if not book_records:
        log("No books could be processed into chapters/sections. Aborting.", "ERROR")
        sys.exit(1)

    section("PHASE 8-9: Building chunk corpus + semantic index")
    corpus = build_corpus(book_records)

    section("PHASE 10-11: Matching + coverage scoring")
    rows = generate_recommendations(courses_with_units, corpus)

    section("PHASE 12: Writing Excel report")
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    export_to_excel(rows, args.output)

    section("DONE")
    log(f"Syllabus PDFs found     : {len(syllabus_paths)}")
    log(f"Book PDFs found         : {len(book_paths)}")
    log(f"Books processed         : {len(book_records)}")
    log(f"Syllabus courses parsed : {len(courses_with_units)}")
    log(f"Recommendation rows     : {len(rows)}")
    log(f"Output file             : {args.output}")


if __name__ == "__main__":
    main()
