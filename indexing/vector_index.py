"""Thin re-export layer so callers depend on 'the vector index' rather than
on the embedding implementation detail directly (keeps the architecture's
Phase 9 boundary even though embedding_builder currently does both jobs)."""
from indexing.embedding_builder import build_index, EmbeddingIndex  # noqa: F401
