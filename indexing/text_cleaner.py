"""
Many PDFs (Springer titles especially) extract with word-spaces collapsed,
e.g. "WhatIsAdditiveManufacturing" instead of "What Is Additive Manufacturing".
This module detects that condition and repairs it well enough for tokenizing,
fuzzy matching, and display.
"""
import re

_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_DIGIT_LETTER_RE = re.compile(r"(?<=[a-zA-Z])(?=\d)|(?<=\d)(?=[A-Za-z])")
_WS_RE = re.compile(r"\s+")


def looks_space_collapsed(text: str, sample_chars: int = 2000) -> bool:
    """Heuristic: real English text has roughly 1 space per 5-6 characters.
    If a text sample has far fewer spaces than that, word boundaries were lost."""
    sample = text[:sample_chars]
    letters = sum(1 for c in sample if c.isalpha())
    spaces = sample.count(" ")
    if letters < 40:
        return False
    ratio = spaces / max(letters, 1)
    return ratio < 0.08  # normal English prose is usually > 0.15


def repair_spacing(text: str) -> str:
    """Insert spaces at lower->UPPER and letter<->digit boundaries.
    Not perfect (can't split 'aB' from run-on lowercase words) but recovers
    the overwhelming majority of word boundaries in headings/titles."""
    text = _CAMEL_BOUNDARY_RE.sub(" ", text)
    text = _DIGIT_LETTER_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text)
    return text.strip()


def clean_text(text: str) -> str:
    """Full cleaning pass: fix ligature/cid artifacts, repair spacing if needed,
    normalize whitespace."""
    if not text:
        return ""
    # Drop stray (cid:129) style artifacts left by broken font maps (seen as bullets)
    text = re.sub(r"\(cid:\d+\)", " ", text)
    if looks_space_collapsed(text):
        text = repair_spacing(text)
    text = _WS_RE.sub(" ", text)
    return text.strip()
