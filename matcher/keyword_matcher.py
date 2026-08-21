"""Stopword-filtered weighted-Jaccard token overlap between a topic and a
chunk's title + body text -- a cheap lexical guardrail alongside the semantic
score, good at anchoring on exact technical terms/named entities."""
from utils.regex_patterns import tokenize


def keyword_score(topic_text: str, chunk_title: str, chunk_body: str) -> float:
    topic_tokens = set(tokenize(topic_text))
    if not topic_tokens:
        return 0.0

    title_tokens = set(tokenize(chunk_title))
    body_tokens = set(tokenize(chunk_body))

    # title overlap counts double -- a topic word appearing in the chapter/section
    # title is a much stronger signal than appearing somewhere in the body text.
    title_overlap = len(topic_tokens & title_tokens)
    body_overlap = len(topic_tokens & (body_tokens - title_tokens))

    weighted_overlap = title_overlap * 2 + body_overlap
    weighted_total = len(topic_tokens) * 2

    return min(1.0, weighted_overlap / weighted_total) if weighted_total else 0.0
