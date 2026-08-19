"""RapidFuzz-based fuzzy string similarity between a syllabus topic and a
chapter/section title. Handles the collapsed-spacing / OCR-ish noise that
real scanned/exported PDFs introduce."""
from rapidfuzz import fuzz
from utils.regex_patterns import normalize_text


def fuzzy_score(topic_text: str, chunk_title_text: str) -> float:
    if not chunk_title_text:
        return 0.0
    a = normalize_text(topic_text)
    b = normalize_text(chunk_title_text)
    if not a or not b:
        return 0.0
    # token_set_ratio ignores word order & duplicate words - good for titles
    # that are phrased differently but cover the same ground.
    ratio = fuzz.token_set_ratio(a, b)
    return ratio / 100.0
