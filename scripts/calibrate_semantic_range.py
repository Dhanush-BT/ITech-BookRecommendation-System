"""Calibrates config.SEMANTIC_SIM_FLOOR/CEILING against this real corpus.

Raw BGE cosine similarities cluster in a narrower band than TF-IDF's, so the
floor/ceiling placeholders in config.py are provisional. This script runs the
real syllabus + resolved-book pipeline, collects the best raw (un-rescaled)
semantic similarity per topic across its candidate books, and prints the
percentile distribution -- use the low/high percentiles to set real
SEMANTIC_SIM_FLOOR/CEILING values in config.py.

Usage: venv/bin/python scripts/calibrate_semantic_range.py [--books-dir DIR]
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from extractors.book_loader import load_books
from indexing.embedding_model import EmbeddingModel
from matcher.recommendation_ranker import build_corpus, build_indices_for_keys
from matcher.reference_resolver import resolve_all, split_resolved_keys
from matcher.semantic_matcher import semantic_scores_raw
from syllabus.syllabus_parser import parse_syllabus_pdf
from utils.logger import log, section


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--books-dir", default=config.BOOKS_DIR)
    parser.add_argument("--syllabi-dir", default=config.SYLLABI_DIR)
    args = parser.parse_args()

    section("Loading syllabi + books")
    syllabus_paths = sorted(
        os.path.join(args.syllabi_dir, f)
        for f in os.listdir(args.syllabi_dir)
        if f.lower().endswith(".pdf")
    )
    courses = []
    for path in syllabus_paths:
        courses.extend(parse_syllabus_pdf(path))

    records = load_books(args.books_dir)
    resolved_by_subject = resolve_all(courses, records)
    corpus = build_corpus(records)
    corpus_by_key = {bc.record.key: bc for bc in corpus}

    cited_keys = sorted(
        {r.book_key for resolved in resolved_by_subject.values() for r in resolved if r.book_key}
    )
    model = EmbeddingModel()
    indices = build_indices_for_keys(cited_keys, corpus_by_key, model)

    section("Collecting raw semantic scores")
    best_raw_per_topic = []
    for course in courses:
        resolved = resolved_by_subject.get(course.code, [])
        textbook_keys, reference_keys = split_resolved_keys(resolved)
        candidate_keys = textbook_keys or reference_keys
        if not candidate_keys:
            continue
        for _module, topic_text in course.all_topics():
            best = -1.0
            for book_key in candidate_keys:
                index = indices.get(book_key)
                if index is None:
                    continue
                raw = semantic_scores_raw(topic_text, index, model)
                if raw:
                    best = max(best, max(raw.values()))
            if best >= 0:
                best_raw_per_topic.append(best)

    if not best_raw_per_topic:
        log("No scored topics -- check that some subjects resolved to available books.")
        return

    arr = np.array(best_raw_per_topic)
    section("Raw semantic similarity percentiles (best chunk per topic)")
    for p in (5, 10, 25, 50, 75, 90, 95):
        print(f"  p{p:>2}: {np.percentile(arr, p):.4f}")
    print(f"  min: {arr.min():.4f}  max: {arr.max():.4f}  n={len(arr)}")

    suggested_floor = float(np.percentile(arr, 10))
    suggested_ceiling = float(np.percentile(arr, 90))
    print(f"\nCurrent config: SEMANTIC_SIM_FLOOR={config.SEMANTIC_SIM_FLOOR} SEMANTIC_SIM_CEILING={config.SEMANTIC_SIM_CEILING}")
    print(f"Suggested (p10/p90): SEMANTIC_SIM_FLOOR={suggested_floor:.2f} SEMANTIC_SIM_CEILING={suggested_ceiling:.2f}")
    print("Review before applying -- p10/p90 is a starting heuristic, not a guarantee.")


if __name__ == "__main__":
    main()
