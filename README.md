# BookRecommendation — Syllabus-to-Textbook Coverage Mapper

Given a set of **university syllabus PDFs** and a library of **textbook PDFs**, this
tool produces a per-topic recommendation table: for every topic in every subject,
_which cited book covers it, in which chapter/section, on which pages, and how
well_.

There is **no LLM anywhere in the pipeline**. It is pure retrieval and ranking —
sentence-transformer embeddings plus keyword / fuzzy / metadata signals — scoped
per subject to that subject's _own_ cited Text/Reference books.

---

## Table of contents

- [What it does](#what-it-does)
- [Quick start](#quick-start)
- [Running the pipeline](#running-the-pipeline)
- [Output format](#output-format)
- [How it works (pipeline stages)](#how-it-works-pipeline-stages)
- [Project layout](#project-layout)
- [Configuration (`config.py`)](#configuration-configpy)
- [Matching & scoring model](#matching--scoring-model)
- [Helper scripts](#helper-scripts)
- [Adding a new or differently-formatted syllabus](#adding-a-new-or-differently-formatted-syllabus)
- [Tests](#tests)
- [Known limitations](#known-limitations)
- [Troubleshooting](#troubleshooting)

---

## What it does

1. Parses each syllabus PDF into **subjects → units → topics**, plus each subject's
   list of **cited Text Books and Reference Books**.
2. Parses each textbook PDF into a **chapter / section tree** with page ranges,
   using the book's own Table of Contents where possible and falling back to
   font-based heading detection.
3. **Resolves** each syllabus citation ("Kreyszig, *Advanced Engineering
   Mathematics*, 10th ed.") to a local PDF file by fuzzy-matching title + authors.
4. For each topic, searches **only the books that subject cites** and ranks the
   best-covering chunk per book using a blended similarity score.
5. Writes an **Excel workbook** with a full recommendations sheet and a per-subject
   coverage-summary sheet.

---

## Quick start

```bash
# 1. clone / cd into the project
cd BookRecommendation

# 2. create the virtualenv and install deps
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. drop your PDFs in place
#    books/   <- all textbook PDFs
#    syllabi/ <- all syllabus PDFs

# 4. run
python syllabus_book_mapper.py

# 5. open the result
open output/recommendations.xlsx
```

> **Note on the PDFs:** `books/*.pdf` and `syllabi/*.pdf` are git-ignored
> (copyright + size). You must supply your own.

### Requirements

- Python 3.10+ (developed against 3.14)
- See `requirements.txt`:
  `pdfplumber`, `pypdf`, `rapidfuzz`, `openpyxl`, `numpy`,
  `sentence-transformers`, `torch`, `tqdm`
- The embedding model `BAAI/bge-small-en-v1.5` (~130 MB) is downloaded from the
  Hugging Face Hub on first run and cached by `sentence-transformers`.
- Apple Silicon (MPS), CUDA, and CPU are all supported and auto-detected.

---

## Running the pipeline

### Full run (all books, all syllabi)

```bash
source venv/bin/activate
python syllabus_book_mapper.py
```

Defaults come from `config.py`:

| Flag | Default | Meaning |
|------|---------|---------|
| `--books-dir`   | `books`   | directory of textbook PDFs |
| `--syllabi-dir` | `syllabi` | directory of syllabus PDFs |
| `--output`      | `output/recommendations.xlsx` | output workbook path |

### Run in the background (recommended — a full run is slow)

```bash
nohup python syllabus_book_mapper.py > output/full_run.log 2>&1 &
tail -f output/full_run.log
```

The first run pays for embedding every cited book. Re-runs reuse
`output/.embedding_cache/` and are much faster.

### Restrict to a subset of books

The script has no book-filter flag; point `--books-dir` at a folder containing
only the books you want (symlinks are fine, no copying):

```bash
mkdir -p /tmp/subset_books
ln -sf "$PWD/books/advanced-engineering-mathematics.pdf"             /tmp/subset_books/
ln -sf "$PWD/books/Calculus Early Transcendentals_James Stewart.pdf" /tmp/subset_books/
ln -sf "$PWD/books/Calculus_Anton. H, Bivens. I, Davis. S.pdf"       /tmp/subset_books/

python syllabus_book_mapper.py \
  --books-dir /tmp/subset_books \
  --output output/subset_check.xlsx
```

Every subject's citations will then only be able to resolve to that subset;
subjects that cite none of them come back all "Not Found" (expected).

---

## Output format

The workbook has two sheets.

### `Recommendations` sheet — one row per (topic × matched book), up to `TOP_N_BOOKS_PER_TOPIC` per topic

| Column | Notes |
|--------|-------|
| Subject Code / Subject Name | from the syllabus |
| Unit / Unit Title | syllabus unit the topic belongs to |
| Topic / Sub Topic | the syllabus topic text |
| **Status** | `Found` · `Tentative` · `Not Found` (see below) |
| Book Title / Author / Edition / Publisher / Year | resolved book metadata |
| Book Type | `Textbook` or `Reference` (from the citation section) |
| Chapter | matched chapter/section label + title |
| **Book Page Start / End** | page numbers **as printed in the book** |
| **PDF Page Start / End** | 1-indexed page position **within the PDF file** |
| Coverage % | blended similarity score, 0–100 |
| Notes | coverage label, or the reason a topic was not matched |

`Book Page` vs `PDF Page` differ whenever the PDF has front matter (cover, TOC,
preface) before printed page 1. Use **Book Page** to cite, **PDF Page** to jump to
it in a viewer.

### `Status` values

| Status | Meaning |
|--------|---------|
| `Found` | a cited book covers the topic at ≥ `MIN_COVERAGE_PERCENT` (default 70) |
| `Tentative` | nothing cleared 70, but the single best candidate cleared `TENTATIVE_COVERAGE_PERCENT` (default 55) — reported so a real-but-broad chapter reference isn't dropped for a terse one-word topic ("Jacobians") |
| `Not Found` | no cited book (available locally) covers the topic above 55; the Notes column explains why (no citation resolved / covered below threshold / **scanned PDF, needs OCR**) |

### `Summary` sheet — one row per subject

`Found` · `Tentative` · `Not Found` counts, total topics, and a **Coverage Rate**
= (Found + Tentative) / Total.

---

## How it works (pipeline stages)

The console log is split into the same seven sections the code runs:

### 1. Parsing syllabi — `syllabus/syllabus_parser.py` + `syllabus/standardizer.py`

- Before any structural parsing, `standardize_syllabus_text()` rewrites common
  non-canonical phrasings into the vocabulary the parser's regexes expect —
  e.g. `MODULE 1` / `CHAPTER I` → `UNIT I`, `AIM:` / `COURSE AIMS` →
  `OBJECTIVES:`, `PRESCRIBED BOOKS` → `TEXT BOOKS:`, `BIBLIOGRAPHY` /
  `SUGGESTED READINGS` → `REFERENCE BOOKS:`, bullet-pointed topic lists →
  the dash-separated form the topic splitter expects, and institution
  cohort-prefixed course codes (e.g. `PTMA3151` → `MA3151`). This runs
  automatically for every syllabus PDF — see
  [Adding a new or differently-formatted syllabus](#adding-a-new-or-differently-formatted-syllabus)
  below for where new format variants get added when you hit one it doesn't
  cover yet.
- Splits the (now-standardized) syllabus PDF into **subject sections** (course code + name).
- For each subject: extracts **units** (`UNIT I …`, roman or arabic), the unit
  title (stripping the trailing L-T-P-C / period-count tail), and the **topic
  list** (split on the spaced dash `–`).
- Special handling:
  - **Eponymous compounds** split on the same dash are re-joined
    ("Cayley - Hamilton theorem" → `Cayley-Hamilton theorem`,
    "Gram - Schmidt orthogonalization" → `Gram-Schmidt orthogonalization`).
  - `Contents` / roman-numeral page-header leaks are stripped.
- Extracts the **Text Books** and **Reference Books** citation lists, tagging
  each as `textbook` or `reference`.

### 2. Loading books — `extractors/book_loader.py`

Per PDF:

- `metadata_extractor.py` — title, authors, edition, publisher, year from the
  cover / early pages.
- `toc_detector.py` → `toc_parser.py` — find and parse the printed Table of
  Contents into `(label, title, level, printed-page)` entries.
- `page_mapper.py` — resolve the offset between printed page numbers and PDF page
  indices.
- `chapter_builder.py` — build the `Chapter` → `Section` tree; level-1 entries
  become chapters, deeper entries nest as sections; a chapter's page range is
  widened to span its sections. Synthesises chapters for books whose TOC parses
  as a flat `N.M` section list (e.g. Stewart).
- `heading_detector.py` — **fallback** when the TOC is missing or has fewer than
  `MIN_TOC_ENTRIES`: detect headings by font size/weight.
- `content_locator.py` — last-resort page localisation by scanning text.

PDF text extraction (`pdfcore/pdf_reader.py`) normalises **f-ligatures** that some
fonts encode as C0 control characters (`di\x0berential` → `differential`) — left
alone these corrupt tokenization, matching, and the Excel export.

### 3. Resolving cited references — `matcher/reference_resolver.py`

Each citation line is fuzzy-matched (RapidFuzz) against every book's
`title + authors + filename`. Case is normalised first (cover text is often
ALL-CAPS, citations are Title Case). The author list is gated: a citation whose
author fuzz-score is below `_AUTHOR_GATE` is rejected outright. A citation
resolves only if its best score ≥ `REFERENCE_MATCH_THRESHOLD` (default 70).

### 4. Building chunk corpus — `indexing/chunk_generator.py`

Flattens each book's chapter tree into flat `Chunk`s: one per section when a
chapter has parsed sections, otherwise one per chapter. Long chunks are page-
capped (`MAX_CHUNK_PAGES`).

### 5. Building embedding indices — `indexing/`

Only for books that some subject actually cites (strict scoping — no reason to
embed a book nothing will match against).

- `subchunker.py` — splits each chunk into ~350-word overlapping sub-chunks.
- `embedding_model.py` — `BAAI/bge-small-en-v1.5` via sentence-transformers.
- `embedding_cache.py` — caches vectors under `output/.embedding_cache/` keyed by
  book; a content change invalidates the entry.
- `vector_index.py` — in-memory cosine-similarity index over the sub-chunk
  vectors.

### 6. Matching topics to books — `matcher/recommendation_ranker.py`

For each topic, for each cited book:

- **Semantic** (`semantic_matcher.py`) — max cosine similarity between the topic
  query and the book's sub-chunks, rescaled between `SEMANTIC_SIM_FLOOR` and
  `SEMANTIC_SIM_CEILING`. Terse topics ("Jacobians") get the unit title folded
  into the query for context.
- **Keyword** (`keyword_matcher.py`) — stemmed token overlap; title hits count
  double.
- **Fuzzy** (`fuzzy_matcher.py`) — RapidFuzz on the chunk title.
- **Metadata** (`coverage_calculator.py`) — a small prior from book metadata.

These blend (`combine_scores`) into a 0–100 **Coverage %** using the
`WEIGHT_*` weights.

**Citation-scope demotion** (`matcher/citation_scope.py`): some citations carry a
trailing bracket note naming exactly which units/sections a book is assigned,
e.g. `[For Units II & IV — Sections 1.1, 2.2, 3.1 to 3.6 …]`. A match that falls
outside that scope is multiplicatively demoted (`_OUT_OF_UNIT_PENALTY`,
`_OUT_OF_SECTION_PENALTY`) so an in-scope book wins near-ties — but it is **not a
hard filter**: if the scoped-out book is the only local coverage, a demoted match
still beats nothing.

**Textbooks are tried before references.** Only if no textbook clears
`MIN_COVERAGE_PERCENT` does the ranker fall through to reference books.

### 7. Exporting to Excel — `exporter/excel_exporter.py`

Writes both sheets. Illegal XML control characters are sanitised out of cell
values before writing (openpyxl / Excel reject them).

---

## Project layout

```
syllabus_book_mapper.py      CLI entry point — orchestrates the 7 stages
config.py                    all tunables (see below)

syllabus/
  standardizer.py             raw syllabus text -> canonical header/format vocabulary
  syllabus_parser.py         syllabus PDF -> subjects / units / topics / citations

extractors/                  textbook PDF -> chapter/section tree
  book_loader.py               per-book orchestration
  metadata_extractor.py        title / authors / edition / year
  toc_detector.py              locate the printed Table of Contents
  toc_parser.py                parse TOC lines -> entries
  page_mapper.py               printed-page <-> PDF-index offset resolution
  chapter_builder.py           entries -> Chapter/Section tree with page ranges
  heading_detector.py          font-based heading fallback (no/sparse TOC)
  content_locator.py           last-resort text-scan page localisation

pdfcore/
  pdf_reader.py                cached PDFDocument; ligature / control-char cleanup

indexing/                    chunking + embeddings
  chunk_generator.py           chapter tree -> flat Chunks
  subchunker.py                Chunk -> overlapping ~350-word sub-chunks
  text_cleaner.py              text normalisation
  embedding_model.py           BAAI/bge-small-en-v1.5 wrapper
  embedding_cache.py           on-disk vector cache (output/.embedding_cache/)
  vector_index.py              in-memory cosine-similarity index

matcher/                     topic -> book/chapter/page ranking
  reference_resolver.py        citation line -> local PDF (fuzzy title+author)
  citation_scope.py            parse "[For Units … Sections …]" scope notes
  semantic_matcher.py          embedding similarity scoring
  keyword_matcher.py           stemmed token-overlap scoring
  fuzzy_matcher.py             RapidFuzz title scoring
  coverage_calculator.py       score blending + coverage labels
  recommendation_ranker.py     the stage-6 driver; builds RecommendationRows

exporter/
  excel_exporter.py            RecommendationRows -> .xlsx (2 sheets)

utils/
  logger.py                    section()/log() console output
  regex_patterns.py            shared regexes + tokenizer
  roman.py                     roman-numeral parsing (unit numbers)

scripts/                     dev / diagnostic tools (see below)
tests/                       pytest suite
```

---

## Configuration (`config.py`)

| Group | Key | Default | Purpose |
|-------|-----|---------|---------|
| **TOC detection** | `MAX_TOC_SCAN_PAGES` | 60 | how far into a PDF to look for the TOC |
| | `MIN_TOC_SCORE` | 35 | TOC-page detection confidence threshold |
| | `TOC_MAX_CONTIG_GAP` / `TOC_MERGE_GAP` | 2 / 6 | TOC page-run stitching |
| **Extraction** | `MAX_CHUNK_PAGES` | 12 | page cap per chunk |
| | `USE_HEADING_FALLBACK` | `True` | use font-heading detection when TOC fails |
| | `MAX_HEADING_SCAN_PAGES` | 500 | cap for the heading fallback scan |
| | `MIN_TOC_ENTRIES` | 3 | below this, TOC is "too sparse" -> fallback |
| **Content locator** | `CONTENT_LOCATOR_WINDOW_PAGES` | 3 | localisation window |
| | `CONTENT_LOCATOR_MAX_PAGES` | 400 | scan cap for degenerate books |
| **Embeddings** | `EMBEDDING_MODEL_NAME` | `BAAI/bge-small-en-v1.5` | sentence-transformer model |
| | `EMBEDDING_MAX_SEQ_TOKENS` | 512 | model context |
| | `SUBCHUNK_WORDS` / `SUBCHUNK_OVERLAP_WORDS` / `SUBCHUNK_MIN_WORDS` | 350 / 50 / 40 | sub-chunk sizing |
| | `EMBEDDING_QUERY_PREFIX` | *(bge instruction prefix)* | prepended to every query |
| | `EMBEDDING_BATCH_SIZE` | 64 | encode batch size |
| | `EMBEDDING_DEVICE` | `None` | `None` = auto (mps > cuda > cpu) |
| **Score calibration** | `SEMANTIC_SIM_FLOOR` / `SEMANTIC_SIM_CEILING` | 0.45 / 0.85 | raw-cosine -> 0–1 rescale band; **placeholder — recalibrate** (see `scripts/calibrate_semantic_range.py`) |
| **Cache** | `USE_EMBEDDING_CACHE` | `True` | |
| | `EMBEDDING_CACHE_DIR` | `output/.embedding_cache` | |
| **Match weights** (must sum to 1.0) | `WEIGHT_SEMANTIC` | 0.55 | |
| | `WEIGHT_KEYWORD` | 0.20 | |
| | `WEIGHT_FUZZY` | 0.15 | |
| | `WEIGHT_METADATA` | 0.10 | |
| **Thresholds** | `MIN_COVERAGE_PERCENT` | 70 | `Found` bar |
| | `TENTATIVE_COVERAGE_PERCENT` | 55 | `Tentative` bar |
| | `TOP_N_BOOKS_PER_TOPIC` | 3 | max rows emitted per topic |
| **Reference scoping** | `REFERENCE_MATCH_THRESHOLD` | 70 | citation -> local-file resolution score (RapidFuzz 0–100) |
| | `STRICT_REFERENCE_SCOPING` | `True` | only match a topic against its subject's cited books |
| | `PREFER_TEXTBOOKS_OVER_REFERENCES` | `True` | try textbooks before references |
| **Misc** | `LOG_VERBOSE` | `True` | |
| **Paths** | `BOOKS_DIR` / `SYLLABI_DIR` / `OUTPUT_DIR` / `OUTPUT_XLSX` | `books` / `syllabi` / `output` / `output/recommendations.xlsx` | |

---

## Matching & scoring model

```
Coverage% = 100 * ( WEIGHT_SEMANTIC * semantic_rescaled
                  + WEIGHT_KEYWORD  * keyword_overlap
                  + WEIGHT_FUZZY    * fuzzy_title
                  + WEIGHT_METADATA * metadata_prior )

  then, if the book's citation has a scope note:
    * _OUT_OF_UNIT_PENALTY    (0.90)  if the match is outside the cited units
    * _OUT_OF_SECTION_PENALTY (0.94)  if outside the cited sections
```

Coverage label (Notes column, `coverage_calculator.coverage_label`):

| Coverage % | Label |
|-----------|-------|
| ≥ 90 | Excellent |
| ≥ 80 | Good |
| ≥ 70 (`MIN_COVERAGE_PERCENT`) | Moderate |
| ≥ 55 (`TENTATIVE_COVERAGE_PERCENT`) | Tentative |
| < 55 | Weak |

---

## Helper scripts

| Script | Purpose |
|--------|---------|
| `scripts/smoke_test_single_book.py "books/<file>.pdf"` | run **extraction only** on one book and print its chapter/section tree with both PDF and book page ranges — fast sanity check for TOC / heading-detection changes |
| `scripts/standardize_syllabus.py syllabi/<file>.pdf` | preview what the standardizer rewrote and what the parser then extracted (subjects/units/topics/citation counts) for **one** syllabus PDF — the fast sanity check before running the full pipeline on a newly-added or unfamiliar-format syllabus |
| `scripts/calibrate_semantic_range.py` | sample real topic↔chunk cosine similarities to pick `SEMANTIC_SIM_FLOOR` / `SEMANTIC_SIM_CEILING` |
| `scripts/verify_embedding_model.py` | confirm the embedding model loads and encodes on this machine |

### Adding a new or differently-formatted syllabus

Drop the PDF into `syllabi/` like any other syllabus — there's no separate
"raw" folder; `syllabus/standardizer.py` runs automatically for every file
before parsing. To check a newly-added file before committing to a full
pipeline run:

```bash
venv/bin/python scripts/standardize_syllabus.py "syllabi/Your New Syllabus.pdf"
```

This prints which standardization rules fired and, per detected subject, its
unit/topic/citation counts, flagging any subject where **no UNIT headers
matched** or **no TEXT/REFERENCE BOOKS section matched**. Lab/practicum-only
courses (a "LIST OF EXPERIMENTS" instead of UNIT-based theory content, often
with no citations) legitimately hit those flags — that's not a bug.

If a subject is missing or malformed for a real reason, the format uses
wording (or a course-code scheme) `standardizer.py` doesn't recognize yet:
open `syllabus/standardizer.py` and add one rule following the pattern of the
existing ones (each rule is a compiled regex + replacement, with a comment
explaining which real syllabus wording it targets). Keep new vocabulary
normalization there rather than loosening `syllabus_parser.py`'s own
structural regexes — that keeps the parser itself precise and puts all
"which words mean the same thing across formats" knowledge in one place.
`tests/test_syllabus_standardizer.py` has the existing coverage to extend.

```bash
venv/bin/python scripts/smoke_test_single_book.py "books/Calculus_Anton. H, Bivens. I, Davis. S.pdf"
```

---

## Tests

```bash
source venv/bin/activate
python -m pytest -q
```

Covers: syllabus line parsing & eponym merging, TOC parsing, chapter building,
sub-chunking, citation-scope parsing, coverage-label thresholds, PDF text
normalisation, and the recommendation ranker.

---

## Known limitations

- **Scanned / image-only PDFs** have no text layer — extraction yields no
  chapters and no chunks. Affected topics come back `Not Found` with a
  `scanned PDF, needs OCR` note. There is no OCR step; pre-process such books
  externally (e.g. `ocrmypdf`) before adding them.
- **Citation resolution is fuzzy** and tuned conservatively. Books that _are_
  present can fail to resolve when the citation's title/author wording diverges
  (`&` vs `and`, initials-only authors, publisher noise). Lower
  `REFERENCE_MATCH_THRESHOLD` for looser matching at the cost of false positives.
- `SEMANTIC_SIM_FLOOR` / `SEMANTIC_SIM_CEILING` are **placeholders**. Coverage %
  absolute values are only trustworthy after running the calibration script
  against your real corpus.
- Heading-fallback books (no usable TOC) produce coarser chapter boundaries and
  carry no section labels, so citation-scope **section** demotion does not apply
  to them.
- Page numbers are best-effort. For heading-fallback books, `Book Page` == `PDF
  Page` (no printed-page information is recoverable).

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---------|--------------------|
| `no chapter structure found for <book>` | scanned PDF or unparseable TOC; OCR the PDF or accept coarse/no coverage |
| A subject's topics are **all** `Not Found` | none of its citations resolved — check the stage-3 log for the best scores; the book may be missing, misnamed, or scoring under `REFERENCE_MATCH_THRESHOLD` |
| Run is very slow the first time | embedding every cited book; subsequent runs reuse `output/.embedding_cache/` |
| HF Hub rate-limit / download warning | set `HF_TOKEN` in the environment, or ignore — the model caches after first download |
| Coverage % looks systematically high/low | recalibrate `SEMANTIC_SIM_FLOOR` / `SEMANTIC_SIM_CEILING` |
| Excel won't open the file | should not happen — control chars are sanitised; re-run and file a bug with the offending row |


venv/bin/python syllabus_book_mapper.py --syllabi-dir syllabi --books-dir books --output output/recommendations.xlsx