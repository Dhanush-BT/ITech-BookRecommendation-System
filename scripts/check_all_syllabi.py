#!/usr/bin/env python3
"""Bulk sanity check: run the standardizer + parser over every syllabus PDF
under a directory (recursively) and report, per file, how many subjects were
detected and how many of those look incomplete (no UNIT headers matched, or
no TEXT/REFERENCE BOOKS section matched).

Use this after dropping in a new batch of syllabus PDFs to see which ones the
current standardizer already handles and which ones need a new rule --
scripts/standardize_syllabus.py then gives the per-file, per-subject detail
for a single flagged file, and syllabus/standardizer.py is where a new rule
gets added.

Usage:
    venv/bin/python scripts/check_all_syllabi.py syllabi/
    venv/bin/python scripts/check_all_syllabi.py syllabi/ --only-problems
    venv/bin/python scripts/check_all_syllabi.py syllabi/ --csv output/syllabi_check.csv
"""
import argparse
import csv
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from syllabus.standardizer import standardize_syllabus_text
from syllabus.syllabus_parser import _extract_full_text, parse_syllabus_text
from utils.discovery import find_pdfs


def check_one(path: str) -> dict:
    raw = _extract_full_text(path)
    standardized, changes = standardize_syllabus_text(raw)
    courses = parse_syllabus_text(standardized, source_file=path)
    n_no_units = sum(1 for c in courses if not c.modules)
    n_no_books = sum(1 for c in courses if not c.cited_books)
    return {
        "path": path,
        "raw_chars": len(raw),
        "changes": changes,
        "n_subjects": len(courses),
        "n_no_units": n_no_units,
        "n_no_books": n_no_books,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Bulk-check syllabus PDFs under a directory")
    ap.add_argument("dir", help="directory to scan recursively for .pdf files")
    ap.add_argument("--only-problems", action="store_true", help="only print files needing attention")
    ap.add_argument("--csv", help="also write full per-file results to this CSV path")
    args = ap.parse_args()

    paths = find_pdfs(args.dir)
    print(f"found {len(paths)} PDF(s) under {args.dir}\n", flush=True)

    rows = []
    totals = {"ok": 0, "partial": 0, "zero_subjects": 0, "error": 0}
    t0 = time.time()

    for i, path in enumerate(paths, 1):
        rel = os.path.relpath(path, args.dir)
        try:
            r = check_one(path)
        except Exception as e:  # noqa: BLE001 - keep scanning the rest of the batch
            totals["error"] += 1
            print(f"[{i}/{len(paths)}] ERROR   {rel}: {e}", flush=True)
            rows.append({"path": path, "status": "error", "detail": str(e)})
            continue

        if r["n_subjects"] == 0:
            totals["zero_subjects"] += 1
            status = "zero_subjects"
            print(f"[{i}/{len(paths)}] ZERO    {rel}  ({r['raw_chars']} chars, no subject sections detected)", flush=True)
        elif r["n_no_units"] or r["n_no_books"]:
            totals["partial"] += 1
            status = "partial"
            if not args.only_problems:
                print(
                    f"[{i}/{len(paths)}] PARTIAL {rel}  subjects={r['n_subjects']} "
                    f"no_units={r['n_no_units']} no_books={r['n_no_books']}",
                    flush=True,
                )
        else:
            totals["ok"] += 1
            status = "ok"
            if not args.only_problems:
                print(f"[{i}/{len(paths)}] OK      {rel}  subjects={r['n_subjects']}", flush=True)

        rows.append(
            {
                "path": path,
                "status": status,
                "n_subjects": r["n_subjects"],
                "n_no_units": r["n_no_units"],
                "n_no_books": r["n_no_books"],
                "changes": ";".join(f"{k}={v}" for k, v in sorted(r["changes"].items())),
            }
        )

    elapsed = time.time() - t0
    print("\n--- summary ---")
    print(f"total files:      {len(paths)}  ({elapsed:.0f}s)")
    print(f"  fully ok:       {totals['ok']}")
    print(f"  partial issues: {totals['partial']}  (may be legitimate lab/practicum courses)")
    print(f"  zero subjects:  {totals['zero_subjects']}  <- these need a new standardizer rule")
    print(f"  errors:         {totals['error']}")

    if args.csv:
        os.makedirs(os.path.dirname(args.csv) or ".", exist_ok=True)
        fieldnames = ["path", "status", "n_subjects", "n_no_units", "n_no_books", "changes", "detail"]
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for row in rows:
                w.writerow(row)
        print(f"\nwrote {args.csv}")


if __name__ == "__main__":
    main()
