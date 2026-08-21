import unittest

from extractors.toc_parser import parse_toc
from pdfcore.pdf_reader import PageText


class FakeDoc:
    def __init__(self, pages_text):
        self._text = pages_text

    def get_pages(self, start, end):
        return [PageText(i, self._text.get(i, "")) for i in range(start, end + 1)]


class TestTocParser(unittest.TestCase):
    def test_simple_dotted_leader(self):
        text = "CONTENTS\n1. Introduction ..... 5\n2. Basics ..... 12\n"
        entries = parse_toc(FakeDoc({0: text}), 0, 0)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].page, 5)
        self.assertEqual(entries[0].label, "1")
        self.assertEqual(entries[1].page, 12)

    def test_wrapped_title_line(self):
        # "Chapter Three" (spelled out, no trailing digit) so it doesn't itself
        # look like a page-numbered entry -- the title wraps onto this line,
        # the page number arrives on the next.
        text = "Chapter Three\nAdvanced Topics In Something 45\n"
        entries = parse_toc(FakeDoc({0: text}), 0, 0)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].page, 45)

    def test_pending_cap_bounds_runaway_accumulation(self):
        junk_lines = "\n".join(
            f"some preface line number {i} without any trailing page reference here"
            for i in range(10)
        )
        text = junk_lines + "\nReal Chapter Title 10\n"
        entries = parse_toc(FakeDoc({0: text}), 0, 0)
        self.assertEqual(len(entries), 1)
        # the cap must prevent all ~130 words of junk from being glommed into one title
        self.assertLess(len(entries[0].title.split()), 30)

    def test_noise_lines_skipped(self):
        text = "CONTENTS\niv\n1. Real Entry 7\n"
        entries = parse_toc(FakeDoc({0: text}), 0, 0)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].page, 7)


if __name__ == "__main__":
    unittest.main()
