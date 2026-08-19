"""Simple token-overlap (weighted Jaccard) keyword matching."""
from utils.regex_patterns import tokenize

_STOPWORDS = {
    "the", "a", "an", "of", "and", "or", "in", "to", "for", "with", "on",
    "by", "using", "based", "other", "various", "general", "introduction",
    "applications", "application", "concept", "concepts", "study", "types",
}


def _content_tokens(text: str):
    return {t for t in tokenize(text) if t not in _STOPWORDS and len(t) > 2}


def keyword_score(topic_text: str, chunk_title_text: str, chunk_body_text: str = "") -> float:
    topic_tokens = _content_tokens(topic_text)
    if not topic_tokens:
        return 0.0

    title_tokens = _content_tokens(chunk_title_text)
    body_tokens = _content_tokens(chunk_body_text[:3000]) if chunk_body_text else set()

    title_overlap = len(topic_tokens & title_tokens)
    body_overlap = len(topic_tokens & body_tokens)

    # Title overlap is worth more per-token than body overlap.
    score = (title_overlap * 1.0 + body_overlap * 0.4) / max(len(topic_tokens), 1)
    return min(score, 1.0)
