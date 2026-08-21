#!/usr/bin/env python3
"""CLI entry point: syllabus PDFs + book PDFs -> per-topic book/chapter/page
recommendations in an Excel workbook. No LLM anywhere -- pure retrieval and
ranking over sentence-transformer embeddings plus keyword/fuzzy/metadata
signals, scoped per subject to that subject's own cited Text/Reference books.
"""
import argparse
import os

import config
from exporter.excel_exporter import export_to_excel
from extractors.book_loader import load_books
from indexing.embedding_model import EmbeddingModel
from matcher.recommendation_ranker import build_corpus, build_indices_for_keys, generate_recommendations
from matcher.reference_resolver import resolve_all
from syllabus.syllabus_parser import parse_syllabus_pdf
from utils.logger import log, section


def main() -> None:
    parser = argparse.ArgumentParser(description="Syllabus-to-textbook coverage mapper")
    parser.add_argument("--books-dir", default=config.BOOKS_DIR)
    parser.add_argument("--syllabi-dir", default=config.SYLLABI_DIR)
    parser.add_argument("--output", default=config.OUTPUT_XLSX)
    args = parser.parse_args()

    out_dir = os.path.dirname(args.output) or "."
    os.makedirs(out_dir, exist_ok=True)

    section("1. Parsing syllabi")
    syllabus_paths = sorted(
        os.path.join(args.syllabi_dir, f)
        for f in os.listdir(args.syllabi_dir)
        if f.lower().endswith(".pdf")
    )
    courses = []
    for path in syllabus_paths:
        courses.extend(parse_syllabus_pdf(path))
    total_topics = sum(1 for c in courses for _ in c.all_topics())
    log(f"parsed {len(courses)} subjects, {total_topics} topics, from {len(syllabus_paths)} syllabus file(s)")

    section("2. Loading books")
    records = load_books(args.books_dir)
    log(f"loaded {len(records)} books")

    section("3. Resolving cited references")
    resolved_by_subject = resolve_all(courses, records)
    total_citations = sum(len(v) for v in resolved_by_subject.values())
    total_resolved = sum(1 for v in resolved_by_subject.values() for r in v if r.book_key)
    log(f"resolved {total_resolved}/{total_citations} cited books to local files")

    section("4. Building chunk corpus")
    corpus = build_corpus(records)
    corpus_by_key = {bc.record.key: bc for bc in corpus}

    section("5. Building embedding indices for cited books")
    cited_keys = sorted(
        {r.book_key for resolved in resolved_by_subject.values() for r in resolved if r.book_key}
    )
    log(f"{len(cited_keys)} distinct books are cited and available locally")
    model = EmbeddingModel()
    indices = build_indices_for_keys(cited_keys, corpus_by_key, model)

    section("6. Matching topics to books")
    rows = generate_recommendations(courses, resolved_by_subject, corpus_by_key, indices, model)
    found = sum(1 for r in rows if r.status == "Found")
    log(f"generated {len(rows)} rows ({found} found, {len(rows) - found} not found)")

    section("7. Exporting to Excel")
    export_to_excel(rows, args.output)
    log(f"wrote {args.output}")


if __name__ == "__main__":
    main()
