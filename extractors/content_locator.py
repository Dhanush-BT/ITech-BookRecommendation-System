"""Content-based page localization: fallback used only when a book has neither
a usable TOC nor detectable headings (structurally degenerate -- no chapters,
or one chapter spanning the whole book). Slides a fixed page-window across the
book, embeds each window, scores against the topic query, and returns the
contiguous highest-scoring page range as an approximate location. This trades
precision for coverage: it reduces false "Not Found" results caused by
structural-extraction failure rather than the topic genuinely being absent."""
from typing import List, Optional, Tuple

import numpy as np

import config
from indexing.embedding_model import EmbeddingModel
from indexing.text_cleaner import clean_text
from pdfcore.pdf_reader import PDFDocument

_MIN_WINDOW_WORDS = 20


def locate_pages_by_content(
    doc: PDFDocument, topic_text: str, model: EmbeddingModel
) -> Optional[Tuple[int, int, float]]:
    limit = min(config.CONTENT_LOCATOR_MAX_PAGES, doc.num_pages)
    if limit == 0:
        return None

    window_pages = config.CONTENT_LOCATOR_WINDOW_PAGES
    windows: List[Tuple[int, int, str]] = []
    p = 0
    while p < limit:
        end = min(p + window_pages - 1, limit - 1)
        text = clean_text(doc.full_text(p, end))
        windows.append((p, end, text))
        p = end + 1

    eligible_idx = [i for i, (_, _, t) in enumerate(windows) if len(t.split()) >= _MIN_WINDOW_WORDS]
    if not eligible_idx:
        return None

    vectors = model.encode_passages([windows[i][2] for i in eligible_idx])
    qvec = model.encode_query(topic_text)
    sims = vectors @ qvec

    full_sims = np.full(len(windows), -1.0, dtype=np.float32)
    for local_i, global_i in enumerate(eligible_idx):
        full_sims[global_i] = sims[local_i]

    best_idx = int(np.argmax(full_sims))
    best_score = float(full_sims[best_idx])
    threshold = best_score - 0.05

    lo, hi = best_idx, best_idx
    while lo - 1 >= 0 and full_sims[lo - 1] >= threshold:
        lo -= 1
    while hi + 1 < len(windows) and full_sims[hi + 1] >= threshold:
        hi += 1

    page_start = windows[lo][0]
    page_end = windows[hi][1]
    return page_start, page_end, best_score
