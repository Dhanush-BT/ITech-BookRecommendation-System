# Syllabus ↔ Book Recommendation Engine

Maps university syllabus topics (unit-by-unit) to the textbook chapters/sections
that actually cover them, with a confidence ("coverage %") score, and exports
the result as a formatted Excel workbook.

```
Syllabus PDF(s)            Book PDF(s)
     │                          │
     ▼                          ▼
syllabus_parser.py     book_loader.py
(course/unit/topic)    (metadata → TOC detection → TOC parsing →
     │                  page-offset resolution → chapter/section tree)
     │                          │
     │                          ▼
     │                 chunk_generator.py
     │                 (chapter/section → scorable text chunks)
     │                          │
     │                          ▼
     │                 embedding_builder.py (TF-IDF semantic index)
     │                          │
     └──────────────► recommendation_ranker.py
                       (semantic + keyword + fuzzy + metadata → coverage %)
                                 │
                                 ▼
                       excel_exporter.py → output/recommendations.xlsx
```

## Quick start

```bash
pip install -r requirements.txt

# Individual files:
python3 syllabus_book_mapper.py \
  --syllabus path/to/syllabus1.pdf [path/to/syllabus2.pdf ...] \
  --books    path/to/book1.pdf [path/to/book2.pdf ...] \
  --output   output/recommendations.xlsx \
  --min-coverage 40      # optional, overrides config.MIN_COVERAGE_PERCENT

# Or point at folders instead - every .pdf inside is picked up automatically:
python3 syllabus_book_mapper.py \
  --syllabus ./syllabus_folder \
  --books    ./books_folder \
  --output   output/recommendations.xlsx \
  --recursive             # optional - also search subfolders
```

`--syllabus` and `--books` accept any mix of individual PDF paths and
directory paths in the same run (e.g. `--books mybook.pdf ./more_books/`).
A directory is expanded to every `.pdf` it contains (top-level only unless
`--recursive` is given), duplicates are removed, and a missing path or a
directory with no PDFs is logged and skipped rather than aborting the run.

Each row of the output workbook is one (syllabus topic × recommended book) pair:

`id | subject_code | subject_name | module_number | module_title | topic | sub_topic |
book_title | author | edition | publisher | year | book_type | chapter |
page_start | page_end | coverage_% | notes`

A `Summary` sheet reports totals (rows, distinct topics, subjects, books).

## How matching works

For every syllabus topic, every book is scored on four signals and combined
into a single **coverage %**:

| Signal    | Weight | What it measures                                             |
|-----------|-------:|---------------------------------------------------------------|
| Semantic  | 45%    | TF‑IDF cosine similarity between the topic and the book chunk  |
| Keyword   | 25%    | Weighted token overlap (title words count more than body words)|
| Fuzzy     | 20%    | RapidFuzz string similarity (survives paraphrasing/typos)      |
| Metadata  | 10%    | Overlap between the topic and the book's own title             |

`notes` labels the row **Excellent / Good / Partial / Weak** from the same
score. Only the top 3 books per topic, above `MIN_COVERAGE_PERCENT`
(default **70**), are kept — a topic only makes it into the report if a
book genuinely covers it well.

## Bug fix history

### Patch 2: zero recommendation rows / wrong topic matches

Reported against a real textbook (Kreyszig, *Advanced Engineering
Mathematics*) and a real syllabus (Anna University B.E. Mechanical, 208
courses): the report came back completely empty. Three compounding bugs
were found and fixed:

**(a) Titles wrapping across two physical TOC lines were lost or corrupted.**
A very common real-world TOC layout prints a long entry's title across two
lines with the page number only on the second line, e.g.:
```
8.1 The Matrix Eigenvalue Problem.
Determining Eigenvalues and Eigenvectors 323
```
The old line-by-line parser required *every individual line* to end in a
page number. Line 1 here doesn't, so it was silently dropped — losing the
"8.1" label and half the title. Line 2, parsed alone, starts with the
capital letter "D" from "Determining", which the numbering regex
misidentified as the *Roman numeral* D (=500) and stripped off, corrupting
the title to `"etermining Eigenvalues and Eigenvectors"`.

Fixed in `extractors/toc_parser.py` with two changes: (1) a bounded
lookahead now joins a title-only line with the next 1-2 lines until a page
number is found — but only when the next line doesn't itself look like the
start of a fresh entry, so a genuinely missing page number can't
accidentally swallow the *next real entry*; (2) a bare (unprefixed) single
Roman-numeral-looking letter is no longer trusted as a label at all — real
numbering is either digit-based (`8.1`) or has an explicit prefix
(`Chapter`/`Unit`/`Part`/`Appendix`), so a lone `I`/`V`/`X`/`L`/`C`/`D`/`M`
is now correctly treated as just the first letter of the title.

**(b) The printed-page → PDF-page offset resolver could drift to an
impossible negative offset.** The previous version re-anchored only on
chapter-level titles, in a fixed ±8-page window, using a lenient
fuzzy-ratio match. On a 1283-page book with widely-spaced chapters, one
false-positive match (a short/generic title matching *something* elsewhere
in the window) would silently move the running offset, and every entry
after it inherited the error — compounding until the final offset was
**-12** (i.e. claiming chapter content appears *before* its own printed
page number, which is impossible for a real book). This meant the text
actually extracted for scoring often belonged to a completely different
part of the book than the title claimed, so even a topic with a genuinely
matching chapter scored low.

Rewritten in `extractors/page_mapper.py`: only titles of >=15 characters
are trusted as anchors (short/generic titles are just carried forward from
the last confirmed anchor, never used to move the offset themselves); a
match now requires a strict 30-character *verbatim* (normalized) substring,
not a fuzzy ratio; the search window expands (20 → 80 → 300 pages) so real
drift can still be found; and any match implying an implausible offset jump
(>200 pages) is rejected outright rather than adopted. Verified against the
real book: `8.1 The Matrix Eigenvalue Problem. Determining Eigenvalues and
Eigenvectors` now resolves to PDF page 349, which literally opens with
`"SEC. 8.1 The Matrix Eigenvalue Problem. Determining Eigenvalues and
Eigenvectors 323"` — confirmed by reading the actual page.

**(c) Some syllabus PDFs use a course-header layout the parser didn't
recognize**, e.g. wide inter-word spacing (`"MA3151         MATRICES AND
CALCULUS         L   T   P   C"`). `syllabus/syllabus_parser.py`'s regexes
already tolerated this correctly - confirmed 152 of 244 courses (the rest
being labs/seminars with no unit structure, which is expected) parsed
correctly from the B.E. Mechanical syllabus once (a) and (b) above stopped
masking it downstream.

**Net effect**, verified end-to-end on the real files: `MA3151`'s "Eigenvalues
and Eigenvectors of a real matrix" topic now correctly matches Chapter 8.1
of the math book (was previously matching an unrelated inner-product
section at 32% before this patch; after the fix it's the top match). Across
two syllabi and two books together, coverage scores up to **76%** were
produced with every one manually spot-checked against the real book content.

### Patch 1: page number correctness + relevance threshold

**Corrupted page numbers.** Some PDFs' font kerning inserts a stray space
*inside* a multi-digit page number when text is extracted (e.g. a printed
"10" comes out as `"1 0"`). The trailing-page regex only captured the digits
after the last space, so `"...Machining . . . 1 0"` was read as page **0**,
and because chapter/section page ranges are computed by sorting all TOC
entries by page number, that one mis-read number could scramble everything
after it. Fixed by making the trailing-page pattern tolerate an optional
stray space between digits and rejoining them (`"1 0"` → `10`), with a
plausibility ceiling that discards anything still garbled.

**Relevance threshold.** `MIN_COVERAGE_PERCENT` raised to **70** (default) —
only topics a book genuinely covers well are included in the report.

> **Coverage scales with library size.** With few books indexed against a
> large syllabus, most subjects genuinely have no good match — raise or
> lower `--min-coverage` (now confirmed accurate after Patch 2) to trade off
> report size vs. strictness while your library is still small.

### Why TF-IDF instead of a neural embedding model?

The original design called for `SentenceTransformer('all-MiniLM-L6-v2')`.
That requires downloading model weights from the internet at runtime, which
this environment cannot do reliably offline. TF-IDF + cosine similarity is
used instead — it needs no network access, no GPU, and no model download,
while still capturing genuine topical overlap. **Swapping in real sentence
embeddings later only requires rewriting `indexing/embedding_builder.py`**
(`build_index` / `EmbeddingIndex.query`); every other module is agnostic to
how the semantic score is produced.

## Known limitations (by design, not bugs)

- **Match quality scales with library size.** With few books indexed against
  a large syllabus, most subjects genuinely have no good match in the
  corpus. This is expected — coverage reflects genuine content overlap, and
  the number of qualifying rows grows with the size of your book library.
- **Collapsed word-spacing.** Some PDFs extract with no spaces between words
  (`WhatIsAdditiveManufacturing`). `indexing/text_cleaner.py` repairs this
  well enough for scoring/display, but the odd word boundary can still land
  in the wrong place.
- **Font-based heading fallback** (`extractors/heading_detector.py`) is
  intentionally simple (font-size + numbering-pattern heuristics) since it
  only fires when a book has no usable TOC at all.
- **Syllabus layouts that separate a course's code/title from its own unit
  content** (e.g. code/title only ever appear in a semester summary table,
  never paired with that course's "UNIT I..." content on the same or a
  linked page) aren't handled — `syllabus_parser.py` is built around the
  common convention of a `CODE   TITLE   L T P C` header directly above
  that course's own objectives/units. If your syllabus uses the
  table-only-reference layout, flag it for a summary-table-mapping pass.

## Performance notes

Text extraction is backed by **pypdf**, not pdfplumber. pdfplumber builds a
full per-page layout object model (character boxes, rects, images) that is
both far slower and far more memory-hungry than plain text extraction needs
to be — benchmarked on the 944-page sample book in this project: pypdf
extracted the whole document in ~29s / ~120MB peak RSS, versus pdfplumber's
170s+ and multiple GB (which OOM-killed the process during development).
pdfplumber is kept only as an optional, rarely-invoked dependency for the
font-size heading fallback.

A single `PDFDocument` instance per file is shared across every pipeline
stage (metadata, TOC, page-offset resolution, chunking) via a path-keyed
registry (`extractors.pdf_reader.get_document`), and pages are extracted
and cached lazily one at a time, so scanning the first 60 pages of a
900-page book costs 60 page-extractions, not 900.

Per Phase 14/15 of the design: a book or syllabus file that fails to parse
is logged and skipped rather than aborting the whole run, and each PDF is
parsed at most once.

## Project layout

```
syllabus_book_mapper.py     Main entry point (CLI). resolve_pdf_paths() expands
                             any --syllabus/--books directory argument to its PDFs.
config.py                   Tunable weights/thresholds

extractors/                 Book-side pipeline
  pdf_reader.py                Lazy, cached, pypdf-backed page access
  metadata_extractor.py        Title/author/edition/publisher/year
  toc_detector.py              Scores pages to find the Table of Contents
  toc_parser.py                Parses TOC lines into (label, title, page)
  page_mapper.py                Printed-page → actual-PDF-page offset resolution
  chapter_builder.py           Builds the Chapter → Section tree + page ranges
  heading_detector.py          Font-size fallback when no TOC is found
  book_loader.py               Orchestrates all of the above per book

syllabus/
  syllabus_parser.py          Course/Unit/Topic parser for syllabus PDFs

indexing/
  text_cleaner.py              Fixes collapsed spacing, cid artifacts
  chunk_generator.py            Chapter/Section → scorable text chunks
  embedding_builder.py          TF-IDF semantic index (see note above)
  vector_index.py                Thin query-facing wrapper

matcher/
  keyword_matcher.py, fuzzy_matcher.py, semantic_matcher.py
  coverage_calculator.py        Combines the four signals into coverage %
  recommendation_ranker.py      Top-N ranking + row assembly

exporter/
  excel_exporter.py            Formatted .xlsx + Summary sheet

utils/
  logger.py, roman.py, regex_patterns.py
```
