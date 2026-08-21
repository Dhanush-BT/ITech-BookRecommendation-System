"""In-memory numpy cosine-similarity index over sub-chunk embeddings, with
per-parent-chunk max-score aggregation (a section's semantic score = the best
of its sub-chunks). Plain exact search is sufficient here -- even a generous
estimate of 10k-30k sub-chunks across 61 books is tiny for brute-force cosine
(a few tens of MB, sub-second query time), so no FAISS/ANN index is warranted."""
from dataclasses import dataclass
from typing import Dict, List

import numpy as np

from indexing.embedding_model import EmbeddingModel
from indexing.subchunker import SubChunk
from utils.logger import log


@dataclass
class EmbeddingIndex:
    subchunks: List[SubChunk]
    vectors: np.ndarray  # (N, dim), L2-normalized, grouped by parent_chunk_id
    chunk_ids: List[str]  # unique parent chunk ids, in group order
    group_boundaries: np.ndarray  # int64, start index of each group within vectors

    def query_raw(self, qvec: np.ndarray) -> np.ndarray:
        if self.vectors.shape[0] == 0:
            return np.zeros((0,), dtype=np.float32)
        return self.vectors @ qvec

    def max_score_per_chunk(self, sims: np.ndarray) -> Dict[str, float]:
        if len(self.chunk_ids) == 0:
            return {}
        reduced = np.maximum.reduceat(sims, self.group_boundaries)
        return dict(zip(self.chunk_ids, reduced.tolist()))

    def query(self, qvec: np.ndarray) -> Dict[str, float]:
        return self.max_score_per_chunk(self.query_raw(qvec))


def build_index(subchunks: List[SubChunk], model: EmbeddingModel) -> EmbeddingIndex:
    if not subchunks:
        return EmbeddingIndex(
            subchunks=[], vectors=np.zeros((0, model.dim), dtype=np.float32),
            chunk_ids=[], group_boundaries=np.zeros((0,), dtype=np.int64),
        )

    sorted_subchunks = sorted(subchunks, key=lambda sc: (sc.parent_chunk_id, sc.subchunk_index))
    texts = [sc.text for sc in sorted_subchunks]
    log(f"Encoding {len(texts)} sub-chunks ...")
    vectors = model.encode_passages(texts)

    chunk_ids: List[str] = []
    boundaries: List[int] = []
    last_id = None
    for i, sc in enumerate(sorted_subchunks):
        if sc.parent_chunk_id != last_id:
            chunk_ids.append(sc.parent_chunk_id)
            boundaries.append(i)
            last_id = sc.parent_chunk_id

    return EmbeddingIndex(
        subchunks=sorted_subchunks,
        vectors=vectors,
        chunk_ids=chunk_ids,
        group_boundaries=np.array(boundaries, dtype=np.int64),
    )
