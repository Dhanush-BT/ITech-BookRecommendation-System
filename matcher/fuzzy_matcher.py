"""RapidFuzz token_set_ratio between the topic text and a chunk's title --
catches near-matches (abbreviations, word-order/plural differences) that
plain token-overlap misses, at the title-string level."""
from rapidfuzz import fuzz


def fuzzy_score(topic_text: str, chunk_title: str) -> float:
    if not topic_text or not chunk_title:
        return 0.0
    return fuzz.token_set_ratio(topic_text, chunk_title) / 100.0
