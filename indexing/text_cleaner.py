"""Repairs common PDF-extraction artifacts: cid escapes, broken hyphenation across
line breaks, camelCase/digit-boundary word splitting, and whitespace collapse."""
import re

_CID_RE = re.compile(r"\(cid:\d+\)")
_HYPHEN_LINEBREAK_RE = re.compile(r"(\w)-\n(\w)")
_MULTI_NEWLINE_RE = re.compile(r"\n{2,}")
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")
# lowercase immediately followed by uppercase, e.g. "thisIsMashed" -> "this Is Mashed"
_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z])(?=[A-Z])")
# letter immediately followed by digit or vice versa in a run, e.g. "Chapter3Intro"
_ALPHA_DIGIT_BOUNDARY_RE = re.compile(r"(?<=[a-zA-Z])(?=\d)|(?<=\d)(?=[a-zA-Z])")


def _split_mashed_words(text: str) -> str:
    text = _CAMEL_BOUNDARY_RE.sub(" ", text)
    text = _ALPHA_DIGIT_BOUNDARY_RE.sub(" ", text)
    return text


def clean_text(text: str, split_mashed: bool = False) -> str:
    if not text:
        return ""
    text = _CID_RE.sub(" ", text)
    text = _HYPHEN_LINEBREAK_RE.sub(r"\1\2", text)
    if split_mashed:
        text = _split_mashed_words(text)
    text = text.replace("\r", "\n")
    text = _MULTI_SPACE_RE.sub(" ", text)
    text = _MULTI_NEWLINE_RE.sub("\n", text)
    return text.strip()
