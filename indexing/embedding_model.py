"""Wraps sentence-transformers' BAAI/bge-small-en-v1.5 with correct asymmetric
query/passage handling.

BGE models (bge-small/base/large-en, including -v1.5) are trained for retrieval
with an asymmetric convention: the QUERY side gets prefixed with an instruction
string; the PASSAGE/document side gets no prefix at all. This matters concretely
here because syllabus topics are short, imperative noun phrases while textbook
passages are long descriptive prose -- exactly the query/passage shape the BGE
instruction prefix exists to correct for. Do not "simplify" this by prefixing
both sides or neither; that measurably degrades retrieval for this shape.
"""
from typing import List, Optional

import numpy as np
import torch
from sentence_transformers import SentenceTransformer

import config
from utils.logger import log


def resolve_device(override: Optional[str] = None) -> str:
    if override:
        return override
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


class EmbeddingModel:
    def __init__(self, model_name: str = config.EMBEDDING_MODEL_NAME, device: Optional[str] = None):
        self.device = resolve_device(device or config.EMBEDDING_DEVICE)
        log(f"Loading embedding model {model_name} on device={self.device} ...")
        self.model = SentenceTransformer(model_name, device=self.device)
        self.dim = self.model.get_sentence_embedding_dimension()

    def encode_passages(self, texts: List[str], batch_size: int = config.EMBEDDING_BATCH_SIZE) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        vectors = self.model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=len(texts) > 200,
            convert_to_numpy=True,
        )
        return vectors.astype(np.float32)

    def encode_query(self, text: str) -> np.ndarray:
        prefixed = config.EMBEDDING_QUERY_PREFIX + text
        vector = self.model.encode(prefixed, normalize_embeddings=True, convert_to_numpy=True)
        return vector.astype(np.float32)
