"""Focused batch run: the full matching pipeline for a chosen set of subjects
only (by course code), against a chosen set of books -- e.g. validating page
numbers / coverage for MA3151 against the three math texts without paying for
a whole-catalogue run.

Citation resolution only needs book metadata, so every book gets a cheap
metadata-only record; full chapter extraction + embedding happens only for
the books the chosen subjects actually cite.

Usage:
    venv/bin/python scripts/batch_subject.py \
        --subjects MA3151 \
        --books "advanced-engineering-mathematics.pdf" \
                "Calculus Early Transcendentals_James Stewart.pdf" \
                "Calculus_Anton. H, Bivens. I, Davis. S.pdf" \
        --syllabus syllabi/B.E.Mech.pdf \
        --output output/ma3151_check.xlsx

--books may be bare filenames (resolved under config.BOOKS_DIR) or paths.
Omit --books to consider the whole books/ directory.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from exporter.excel_exporter import export_to_excel
from extractors.book_loader import BookRecord, _book_key, load_book
from extractors.metadata_extractor import extract_metadata
from indexing.embedding_model import EmbeddingModel
from matcher.recommendation_ranker import (
    build_corpus,
    build_indices_for_keys,
    generate_recommendations,
)
from matcher.reference_resolver import resolve_all
from pdfcore.pdf_reader import get_document
from syllabus.syllabus_parser import parse_syllabus_pdf
from utils.logger import log, section


def main() -> None:
    ap = argparse.ArgumentParser(description="Focused per-subject batch run")
    ap.add_argument("--subjects", nargs="+", required=True, help="course codes, e.g. MA3151 MA3351")
    ap.add_argument("--books", nargs="*", default=None, help="book filenames or paths; default = all of books/")
    ap.add_argument("--syllabus", default=os.path.join(config.SYLLABI_DIR, "B.E.Mech.pdf"))
    ap.add_argument("--output", default="output/batch_subject.xlsx")
    args = ap.parse_args()

    want = {c.upper() for c in args.subjects}

    section("1. Parsing syllabus (filtered)")
    courses = [c for c in parse_syllabus_pdf(args.syllabus) if c.code.upper() in want]
    if not courses:
        sys.exit(f"no subject in {args.syllabus} matched {sorted(want)}")
    for c in courses:
        log(f"{c.code} {c.name}: {sum(1 for _ in c.all_topics())} topics, {len(c.cited_books)} citations")

    section("2. Book candidate set")
    if args.books:
        book_paths = [
            b if os.path.isabs(b) or os.path.sep in b else os.path.join(config.BOOKS_DIR, b)
            for b in args.books
        ]
    else:
        book_paths = sorted(
            os.path.join(config.BOOKS_DIR, f)
            for f in os.listdir(config.BOOKS_DIR)
            if f.lower().endswith(".pdf")
        )
    for p in book_paths:
        if not os.path.exists(p):
            sys.exit(f"book not found: {p}")
    log(f"{len(book_paths)} candidate book(s)")

    section("3. Metadata-only records")
    meta_records = []
    for p in book_paths:
        doc = get_document(p)
        meta_records.append(
            BookRecord(key=_book_key(p), path=p, metadata=extract_metadata(p, doc), chapters=[], doc=doc)
        )

    section("4. Resolving citations")
    resolved_by_subject = resolve_all(courses, meta_records)
    for code, resolved in resolved_by_subject.items():
        for r in resolved:
            log(f"  {code}: {r.cited.citation_type:9} score={r.match_score:5.1f} -> {r.book_key}")
    needed = sorted({r.book_key for v in resolved_by_subject.values() for r in v if r.book_key})
    log(f"{len(needed)} book(s) to fully load: {needed}")

    section("5. Full extraction of cited books")
    path_by_key = {_book_key(p): p for p in book_paths}
    full_records = [load_book(path_by_key[k]) for k in needed]

    section("6. Corpus + embeddings")
    corpus = build_corpus(full_records)
    corpus_by_key = {bc.record.key: bc for bc in corpus}
    model = EmbeddingModel()
    indices = build_indices_for_keys(needed, corpus_by_key, model)

    section("7. Matching")
    rows = generate_recommendations(courses, resolved_by_subject, corpus_by_key, indices, model)
    counts = {}
    for r in rows:
        counts[r.status] = counts.get(r.status, 0) + 1
    log(f"{len(rows)} rows: {counts}")

    section("8. Export")
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    export_to_excel(rows, args.output)
    log(f"wrote {args.output}")


if __name__ == "__main__":
    main()
