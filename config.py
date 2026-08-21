"""Central tunables for the syllabus-to-textbook coverage mapper."""

# --- TOC detection ---
MAX_TOC_SCAN_PAGES = 60
MIN_TOC_SCORE = 35
TOC_MAX_CONTIG_GAP = 2
TOC_MERGE_GAP = 6

# --- Section/chapter-level text extraction ---
MAX_CHUNK_PAGES = 12
USE_HEADING_FALLBACK = True
MAX_HEADING_SCAN_PAGES = 500
MIN_TOC_ENTRIES = 3  # below this, TOC is considered too sparse and heading fallback kicks in

# --- Content-based page localization (fallback when TOC + headings both fail) ---
CONTENT_LOCATOR_WINDOW_PAGES = 3
CONTENT_LOCATOR_MAX_PAGES = 400  # cap how much of a degenerate book we'll scan

# --- Sub-chunking for embeddings ---
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_MAX_SEQ_TOKENS = 512
SUBCHUNK_WORDS = 350
SUBCHUNK_OVERLAP_WORDS = 50
SUBCHUNK_MIN_WORDS = 40
EMBEDDING_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
EMBEDDING_BATCH_SIZE = 64
EMBEDDING_DEVICE = None  # None = auto-detect mps > cuda > cpu

# --- Semantic score calibration ---
# Placeholder floor/ceiling; recalibrate against real corpus output via
# scripts/calibrate_semantic_range.py before trusting downstream coverage numbers.
SEMANTIC_SIM_FLOOR = 0.45
SEMANTIC_SIM_CEILING = 0.85

# --- Embedding cache ---
USE_EMBEDDING_CACHE = True
EMBEDDING_CACHE_DIR = "output/.embedding_cache"

# --- Matching weights (must sum to 1.0) ---
WEIGHT_SEMANTIC = 0.55
WEIGHT_KEYWORD = 0.20
WEIGHT_FUZZY = 0.15
WEIGHT_METADATA = 0.10

MIN_COVERAGE_PERCENT = 70
TOP_N_BOOKS_PER_TOPIC = 3

# --- Reference-book scoping ---
REFERENCE_MATCH_THRESHOLD = 70  # RapidFuzz 0-100 score for citation -> local file resolution
STRICT_REFERENCE_SCOPING = True
PREFER_TEXTBOOKS_OVER_REFERENCES = True

LOG_VERBOSE = True

# --- Paths ---
BOOKS_DIR = "books"
SYLLABI_DIR = "syllabi"
OUTPUT_DIR = "output"
OUTPUT_XLSX = "output/recommendations.xlsx"
