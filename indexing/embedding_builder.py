"""
Builds a semantic index over book chunks using TF-IDF + cosine similarity.

Note: the original design doc calls for a SentenceTransformer
(all-MiniLM-L6-v2) embedding model. That requires downloading model weights
from the internet at runtime, which this environment cannot do reliably
offline. TF-IDF cosine similarity is used instead as a fully offline,
dependency-light "semantic index" - it is combined with keyword and fuzzy
scores in the matcher so no single weak signal dominates the final score.
Swapping in real sentence embeddings later only requires replacing this
module; the rest of the pipeline is agnostic to how EmbeddingIndex.query()
produces its similarity scores.
"""
from dataclasses import dataclass
from typing import List
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from indexing.chunk_generator import Chunk
from utils.regex_patterns import normalize_text
from utils.logger import log


@dataclass
class EmbeddingIndex:
    vectorizer: TfidfVectorizer
    matrix: any
    chunks: List[Chunk]

    def query(self, text: str, top_k: int = None) -> List[float]:
        """Returns a similarity score (0..1) for every chunk, in chunk order."""
        vec = self.vectorizer.transform([normalize_text(text)])
        sims = cosine_similarity(vec, self.matrix).flatten()
        return sims.tolist()


def build_index(chunks: List[Chunk]) -> EmbeddingIndex:
    if not chunks:
        raise ValueError("Cannot build an index over zero chunks")
    corpus = [normalize_text((c.chapter_title + " " + c.section_title + " " + c.text)) for c in chunks]
    vectorizer = TfidfVectorizer(
        max_features=40000,
        ngram_range=(1, 2),
        min_df=1,
        stop_words="english",
    )
    matrix = vectorizer.fit_transform(corpus)
    log(f"Built TF-IDF semantic index over {len(chunks)} chunks "
        f"({matrix.shape[1]} vocabulary terms)")
    return EmbeddingIndex(vectorizer=vectorizer, matrix=matrix, chunks=chunks)
