"""On-disk cache of sub-chunk embeddings, keyed per book, so repeated pipeline
runs don't re-encode all 61 books every time. Invalidated automatically if the
book file changes (size/mtime fingerprint) or the resulting sub-chunk texts
differ from what's cached (covers config/logic changes to chunking too)."""
import os
import re
from typing import List, Tuple

import numpy as np

import config
from indexing.chunk_generator import Chunk
from indexing.embedding_model import EmbeddingModel
from indexing.subchunker import SubChunk, split_into_subchunks
from utils.logger import log


def _cache_path(book_key: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", book_key)
    return os.path.join(config.EMBEDDING_CACHE_DIR, f"{safe}.npz")


def _book_fingerprint(path: str) -> str:
    stat = os.stat(path)
    return f"{stat.st_size}:{int(stat.st_mtime)}"


def load_or_build_book_embeddings(
    book_path: str, book_key: str, chunks: List[Chunk], model: EmbeddingModel
) -> Tuple[List[SubChunk], np.ndarray]:
    subchunks: List[SubChunk] = []
    for chunk in chunks:
        subchunks.extend(split_into_subchunks(chunk))

    if not subchunks:
        return subchunks, np.zeros((0, model.dim), dtype=np.float32)

    if not config.USE_EMBEDDING_CACHE:
        return subchunks, model.encode_passages([sc.text for sc in subchunks])

    os.makedirs(config.EMBEDDING_CACHE_DIR, exist_ok=True)
    cache_file = _cache_path(book_key)
    fingerprint = _book_fingerprint(book_path)
    current_texts = [sc.text for sc in subchunks]

    if os.path.exists(cache_file):
        try:
            data = np.load(cache_file, allow_pickle=True)
            if (
                str(data["fingerprint"]) == fingerprint
                and str(data["model_name"]) == config.EMBEDDING_MODEL_NAME
                and data["texts"].tolist() == current_texts
            ):
                log(f"embedding_cache: hit for {book_key} ({len(subchunks)} sub-chunks)")
                return subchunks, data["vectors"]
        except Exception as exc:
            log(f"WARNING: embedding_cache read failed for {book_key}: {exc}")

    vectors = model.encode_passages(current_texts)
    try:
        np.savez_compressed(
            cache_file,
            fingerprint=fingerprint,
            model_name=config.EMBEDDING_MODEL_NAME,
            texts=np.array(current_texts, dtype=object),
            vectors=vectors,
        )
    except Exception as exc:
        log(f"WARNING: embedding_cache write failed for {book_key}: {exc}")

    return subchunks, vectors
