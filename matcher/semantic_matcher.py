"""Wraps EmbeddingModel + EmbeddingIndex: embeds a topic query, gets each
chunk's raw max-cosine score, and rescales it onto the 0-1 axis coverage
scoring expects."""
from typing import Dict

from indexing.embedding_model import EmbeddingModel
from indexing.vector_index import EmbeddingIndex
from matcher.coverage_calculator import rescale_semantic


def semantic_scores_raw(topic_text: str, index: EmbeddingIndex, model: EmbeddingModel) -> Dict[str, float]:
    qvec = model.encode_query(topic_text)
    return index.query(qvec)


def semantic_scores(topic_text: str, index: EmbeddingIndex, model: EmbeddingModel) -> Dict[str, float]:
    raw = semantic_scores_raw(topic_text, index, model)
    return {chunk_id: rescale_semantic(score) for chunk_id, score in raw.items()}
