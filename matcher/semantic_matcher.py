"""Wraps the TF-IDF vector index to answer 'how similar is this syllabus
topic to each indexed book chunk' (see indexing/embedding_builder.py for
why TF-IDF is used in place of a downloaded sentence-embedding model)."""
from typing import List
from indexing.vector_index import EmbeddingIndex


def semantic_scores(index: EmbeddingIndex, topic_text: str) -> List[float]:
    return index.query(topic_text)
