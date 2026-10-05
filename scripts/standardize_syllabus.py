#!/usr/bin/env python3
"""Debug helper: run the syllabus standardizer + parser on ONE PDF and report
what got rewritten and what got extracted -- use this to sanity check a newly
supplied syllabus (possibly in an unfamiliar format) before committing to a
full pipeline run.

Usage:
    venv/bin/python scripts/standardize_syllabus.py syllabi/SomeNewSyllabus.pdf
    venv/bin/python scripts/standardize_syllabus.py syllabi/SomeNewSyllabus.pdf \
        --dump output/standardized_preview.txt

A subject flagged with "no UNIT headers matched" or "no TEXT/REFERENCE BOOKS
section matched" means this syllabus uses wording syllabus/standardizer.py
doesn't recognize yet -- add a rule there (see its module docstring) rather
than loosening syllabus_parser.py's own structural regexes.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from syllabus.standardizer import standardize_syllabus_text
from syllabus.syllabus_parser import _extract_full_text, parse_syllabus_text


def main() -> None:
    ap = argparse.ArgumentParser(description="Preview syllabus standardization + parse for one PDF")
    ap.add_argument("pdf", help="path to the syllabus PDF")
    ap.add_argument("--dump", help="write the standardized text to this path for inspection")
    args = ap.parse_args()

    raw = _extract_full_text(args.pdf)
    standardized, changes = standardize_syllabus_text(raw)

    print(f"raw text: {len(raw)} chars")
    if changes:
        print("standardization changes applied:")
        for name, count in sorted(changes.items()):
            print(f"  {name}: {count}")
    else:
        print("standardization changes applied: none (already canonical, or an unrecognized variant)")

    if args.dump:
        os.makedirs(os.path.dirname(args.dump) or ".", exist_ok=True)
        with open(args.dump, "w", encoding="utf-8") as f:
            f.write(standardized)
        print(f"wrote standardized text to {args.dump}")

    courses = parse_syllabus_text(standardized, source_file=args.pdf)
    print(f"\ndetected {len(courses)} subject section(s):")
    for c in courses:
        n_topics = sum(1 for _ in c.all_topics())
        n_text = sum(1 for b in c.cited_books if b.citation_type == "textbook")
        n_ref = sum(1 for b in c.cited_books if b.citation_type == "reference")
        flags = []
        if not c.modules:
            flags.append("no UNIT headers matched")
        if n_text == 0 and n_ref == 0:
            flags.append("no TEXT/REFERENCE BOOKS section matched")
        flag_str = f"  ⚠ {'; '.join(flags)}" if flags else ""
        print(
            f"  {c.code:8} {c.name[:55]:55} units={len(c.modules):2} topics={n_topics:3} "
            f"textbooks={n_text} references={n_ref}{flag_str}"
        )

    if not courses:
        print(
            "  ⚠ no subject sections detected at all -- the course-code + OBJECTIVES "
            "gate in syllabus_parser._find_course_starts() may not match this syllabus's "
            "header format"
        )


if __name__ == "__main__":
    main()
