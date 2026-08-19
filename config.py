"""
Central configuration for the Syllabus <-> Book recommendation engine.
"""

# --- TOC detection ---
MAX_TOC_SCAN_PAGES = 60          # how many pages (from the front) to scan looking for a TOC
MIN_TOC_SCORE = 35               # a page needs at least this score to be considered part of the TOC
TOC_MAX_CONTIG_GAP = 2           # allow up to N non-scoring pages between TOC pages before we stop

# --- Chunking (kept for architecture completeness / future embedding upgrade) ---
CHUNK_SIZE_WORDS = 500
CHUNK_OVERLAP_WORDS = 50
# Some books have very coarse TOCs (a "chapter" can span hundreds of pages
# with no sub-sections). Reading the whole span into memory for every such
# chunk is both unnecessary (the topic signal is concentrated in the first
# few pages of a chapter) and a real OOM risk on large PDFs, so extraction
# for indexing purposes is capped at this many pages per chunk.
MAX_CHUNK_PAGES = 12

# --- Matching weights (must sum to 1.0) ---
WEIGHT_SEMANTIC = 0.45   # TF-IDF cosine similarity over chapter/section text
WEIGHT_KEYWORD = 0.25    # token overlap between topic and chapter/section titles + text
WEIGHT_FUZZY = 0.20      # RapidFuzz string similarity between topic and chapter/section titles
WEIGHT_METADATA = 0.10   # bonus if book title/subject words appear in the topic

# Rows below this coverage are dropped from the final report. Only topics
# that are genuinely well-covered by a book (>=70%) are considered
# relevant enough to include.
MIN_COVERAGE_PERCENT = 70
TOP_N_BOOKS_PER_TOPIC = 3        # how many candidate books to keep per syllabus topic

# --- Misc ---
USE_HEADING_FALLBACK = True
LOG_VERBOSE = True
