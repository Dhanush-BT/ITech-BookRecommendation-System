import unittest

import config
from indexing.chunk_generator import Chunk
from indexing.subchunker import split_into_subchunks


def make_chunk(word_count, chapter_title="Chapter", section_title="Section"):
    text = " ".join(f"word{i}" for i in range(word_count))
    return Chunk(
        chunk_id="b::c::s",
        book_key="b",
        chapter_label="c",
        chapter_title=chapter_title,
        section_label="s",
        section_title=section_title,
        page_start=0,
        page_end=1,
        text=text,
    )


class TestSubchunker(unittest.TestCase):
    def test_short_chunk_single_subchunk(self):
        subs = split_into_subchunks(make_chunk(50))
        self.assertEqual(len(subs), 1)
        self.assertTrue(subs[0].text.startswith("Chapter. Section. "))

    def test_long_chunk_produces_multiple_windows_within_limit(self):
        subs = split_into_subchunks(make_chunk(1000))
        self.assertGreater(len(subs), 1)
        for sc in subs:
            self.assertLessEqual(sc.word_count, config.SUBCHUNK_WORDS)

    def test_no_subchunk_shorter_than_min_words_when_multiple_exist(self):
        # the merge-short-trailing-window rule should guarantee this invariant
        # regardless of exact total word count
        subs = split_into_subchunks(make_chunk(1000))
        if len(subs) > 1:
            for sc in subs:
                self.assertGreaterEqual(sc.word_count, config.SUBCHUNK_MIN_WORDS)

    def test_empty_text_yields_one_empty_subchunk(self):
        subs = split_into_subchunks(make_chunk(0))
        self.assertEqual(len(subs), 1)
        self.assertEqual(subs[0].word_count, 0)

    def test_subchunk_indices_are_sequential(self):
        subs = split_into_subchunks(make_chunk(1200))
        self.assertEqual([sc.subchunk_index for sc in subs], list(range(len(subs))))


if __name__ == "__main__":
    unittest.main()
