import unittest

from extractors.chapter_builder import build_chapters
from extractors.page_mapper import ResolvedTOCEntry
from extractors.toc_parser import TOCEntry


class FakeDoc:
    def __init__(self, num_pages):
        self.num_pages = num_pages

    def full_text(self, start, end):
        return ""


def _entry(label, title, page, level):
    return TOCEntry(raw_line=f"{label} {title}", label=label, title=title, page=page, level=level)


def _resolved(pairs):
    # pairs: (label, title, book_page, level, pdf_page)
    return [
        ResolvedTOCEntry(entry=_entry(lbl, ttl, bp, lvl), pdf_page=pdf)
        for lbl, ttl, bp, lvl, pdf in pairs
    ]


class TestChapterSynthesis(unittest.TestCase):
    def test_flat_section_list_gets_synthetic_chapters(self):
        # Stewart-style TOC: no chapter rows at all, only "N.M" sections.
        resolved = _resolved([
            ("1.1", "Four Ways to Represent a Function", 10, 2, 9),
            ("1.2", "Mathematical Models", 23, 2, 22),
            ("2.1", "The Tangent and Velocity Problems", 78, 2, 77),
            ("2.2", "The Limit of a Function", 83, 2, 82),
            ("3.1", "Derivatives of Polynomials", 172, 2, 171),
        ])
        chapters = build_chapters(FakeDoc(400), resolved)
        self.assertEqual([c.label for c in chapters], ["1", "2", "3"])
        self.assertEqual(len(chapters[0].sections), 2)
        self.assertEqual(len(chapters[1].sections), 2)
        self.assertEqual(chapters[0].sections[0].title, "Four Ways to Represent a Function")

    def test_explicit_numbered_chapters_are_not_split(self):
        resolved = _resolved([
            ("Chapter 8", "Matrix Eigenvalue Problems", 322, 1, 321),
            ("8.1", "The Matrix Eigenvalue Problem", 323, 2, 322),
            ("8.2", "Some Applications", 329, 2, 328),
            ("Chapter 9", "Vector Differential Calculus", 354, 1, 353),
            ("9.1", "Vectors in 2-Space and 3-Space", 355, 2, 354),
        ])
        chapters = build_chapters(FakeDoc(500), resolved)
        self.assertEqual([c.label for c in chapters], ["Chapter 8", "Chapter 9"])
        self.assertEqual(chapters[0].title, "Matrix Eigenvalue Problems")
        self.assertEqual(len(chapters[0].sections), 2)

    def test_missing_middle_chapter_row_is_synthesised(self):
        resolved = _resolved([
            ("Chapter 1", "Intro", 1, 1, 0),
            ("1.1", "A", 2, 2, 1),
            ("2.1", "B", 20, 2, 19),  # no "Chapter 2" row
            ("2.2", "C", 25, 2, 24),
        ])
        chapters = build_chapters(FakeDoc(60), resolved)
        self.assertEqual([c.label for c in chapters], ["Chapter 1", "2"])
        self.assertEqual(len(chapters[1].sections), 2)


if __name__ == "__main__":
    unittest.main()
