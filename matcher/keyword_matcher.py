"""Stopword-filtered weighted-Jaccard token overlap between a topic and a
chunk's title + body text -- a cheap lexical guardrail alongside the semantic
score, good at anchoring on exact technical terms/named entities."""
from utils.regex_patterns import tokenize


def _stem(word: str) -> str:
    """Very small suffix stemmer so plural/gerund forms of the same technical
    term still overlap ("Jacobians"~"jacobian", "quadratic forms"~"form",
    "Stretching"~"stretch"). Applied to both sides, so occasional over-stemming
    ("calculus"->"calculu") is harmless -- it just has to be consistent."""
    for suffix, repl, min_stem in (
        ("ies", "y", 1),
        ("ing", "", 3),
        ("ed", "", 3),
        ("es", "", 2),
        ("s", "", 2),
    ):
        if word.endswith(suffix) and len(word) - len(suffix) >= min_stem:
            return word[: len(word) - len(suffix)] + repl
    return word


def _stem_set(tokens) -> set:
    return {_stem(t) for t in tokens}


def keyword_score(topic_text: str, chunk_title: str, chunk_body: str) -> float:
    topic_tokens = _stem_set(tokenize(topic_text))
    if not topic_tokens:
        return 0.0

    title_tokens = _stem_set(tokenize(chunk_title))
    body_tokens = _stem_set(tokenize(chunk_body))

    # title overlap counts double -- a topic word appearing in the chapter/section
    # title is a much stronger signal than appearing somewhere in the body text.
    title_overlap = len(topic_tokens & title_tokens)
    body_overlap = len(topic_tokens & (body_tokens - title_tokens))

    weighted_overlap = title_overlap * 2 + body_overlap
    weighted_total = len(topic_tokens) * 2

    return min(1.0, weighted_overlap / weighted_total) if weighted_total else 0.0
