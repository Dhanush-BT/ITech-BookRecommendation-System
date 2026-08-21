"""Splits a Chunk's text into ~SUBCHUNK_WORDS windows so nothing exceeds the
embedding model's token limit and gets silently truncated. Every sub-chunk is
prefixed with its chapter/section title so topical identity survives even in
later windows of a long section."""
from dataclasses import dataclass
from typing import List

import config
from indexing.chunk_generator import Chunk


@dataclass
class SubChunk:
    parent_chunk_id: str
    subchunk_index: int
    text: str
    word_count: int


def _title_prefix(chunk: Chunk) -> str:
    parts = [p for p in (chunk.chapter_title, chunk.section_title) if p]
    return (". ".join(parts) + ". ") if parts else ""


def split_into_subchunks(chunk: Chunk) -> List[SubChunk]:
    words = chunk.text.split()
    prefix = _title_prefix(chunk)

    if not words:
        return [SubChunk(parent_chunk_id=chunk.chunk_id, subchunk_index=0, text=prefix.strip(), word_count=0)]

    window = config.SUBCHUNK_WORDS
    step = max(1, window - config.SUBCHUNK_OVERLAP_WORDS)

    raw_windows: List[List[str]] = []
    start = 0
    while start < len(words):
        end = min(start + window, len(words))
        raw_windows.append(words[start:end])
        if end == len(words):
            break
        start += step

    # merge a too-short trailing window into the previous one
    if len(raw_windows) > 1 and len(raw_windows[-1]) < config.SUBCHUNK_MIN_WORDS:
        raw_windows[-2] = raw_windows[-2] + raw_windows[-1]
        raw_windows.pop()

    subchunks = []
    for i, w in enumerate(raw_windows):
        body = " ".join(w)
        subchunks.append(
            SubChunk(
                parent_chunk_id=chunk.chunk_id,
                subchunk_index=i,
                text=(prefix + body).strip(),
                word_count=len(w),
            )
        )
    return subchunks
