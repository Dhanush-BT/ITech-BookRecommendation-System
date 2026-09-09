import unittest

from matcher.reference_resolver import _extract_title, _match_score
from syllabus.syllabus_parser import _merge_eponym_splits, _parse_cited_books, _parse_units


class TestUnitParsing(unittest.TestCase):
    def test_parse_units_splits_topics_on_dash(self):
        block = (
            "UNIT – I KINEMATICS OF MECHANISMS 9\n"
            "Mechanisms – Terminology and definitions – cams.\n"
            "UNIT – II GEARS 9\n"
            "Spur gear – gear trains.\n"
            "TOTAL: 45 PERIODS\n"
        )
        modules = _parse_units(block)
        self.assertEqual(len(modules), 2)
        self.assertEqual(modules[0].unit_number, 1)
        self.assertIn("Mechanisms", modules[0].topics)
        self.assertIn("Terminology and definitions", modules[0].topics)
        self.assertEqual(modules[1].unit_number, 2)

    def test_parse_units_rejoins_eponymous_compound(self):
        block = (
            "UNIT I MATRICES 9\n"
            "Eigenvalues and Eigenvectors - Cayley - Hamilton theorem - "
            "Diagonalization of matrices.\n"
            "TOTAL: 45 PERIODS\n"
        )
        topics = _parse_units(block)[0].topics
        self.assertIn("Cayley-Hamilton theorem", topics)
        self.assertNotIn("Cayley", topics)
        self.assertNotIn("Hamilton theorem", topics)


class TestEponymMerge(unittest.TestCase):
    def test_merges_surname_then_named_theorem(self):
        self.assertEqual(
            _merge_eponym_splits(["Cayley", "Hamilton theorem", "Diagonalization"]),
            ["Cayley-Hamilton theorem", "Diagonalization"],
        )
        self.assertEqual(
            _merge_eponym_splits(["Gram", "Schmidt orthogonalization process"]),
            ["Gram-Schmidt orthogonalization process"],
        )

    def test_leaves_standalone_single_word_topics_alone(self):
        # "Jacobians" is a real one-word topic, not the head of a compound.
        self.assertEqual(
            _merge_eponym_splits(["Change of variables", "Jacobians", "Partial differentiation of implicit functions"]),
            ["Change of variables", "Jacobians", "Partial differentiation of implicit functions"],
        )


class TestCitedBookParsing(unittest.TestCase):
    def test_separates_textbook_and_reference_sections(self):
        block = (
            'TEXT BOOKS :\n1. Author A, "Title One", Publisher, 2020.\n'
            '2. Author B, "Title Two", Publisher, 2019.\n'
            'REFERENCE BOOKS:\n1. Author C, "Title Three", Publisher, 2018.\n'
            "ASSESSMENT PATTERN\n"
        )
        cited = _parse_cited_books(block)
        textbooks = [c for c in cited if c.citation_type == "textbook"]
        references = [c for c in cited if c.citation_type == "reference"]
        self.assertEqual(len(textbooks), 2)
        self.assertEqual(len(references), 1)
        self.assertIn("Title Three", references[0].raw_line)

    def test_reference_section_does_not_bleed_into_next_header(self):
        block = (
            'TEXT BOOKS :\n1. Author A, "Title One", Publisher, 2020. REFERENCES:\n'
            '1. Author B, "Title Two", Publisher, 2019.\n'
            "OUTCOMES:\n"
        )
        cited = _parse_cited_books(block)
        textbooks = [c for c in cited if c.citation_type == "textbook"]
        self.assertEqual(len(textbooks), 1)
        self.assertNotIn("REFERENCES", textbooks[0].raw_line)


class TestReferenceResolverMatching(unittest.TestCase):
    def test_extract_title_from_quotes(self):
        self.assertEqual(
            _extract_title('Grewal.B.S., "Higher Engineering Mathematics", Khanna, 2017.'),
            "Higher Engineering Mathematics",
        )

    def test_extract_title_from_by_pattern(self):
        self.assertEqual(
            _extract_title("Technical Communication By Meenakshi Raman, Oxford, 2016."),
            "Technical Communication",
        )

    def test_generic_title_without_author_overlap_is_rejected(self):
        # same generic title as a real book, but a completely different author ->
        # the author gate should reject this, not just weight it down
        cited = 'Ramana. B.V., "Higher Engineering Mathematics", McGraw Hill, 2016.'
        score = _match_score(cited, "higher engineering mathematics", "BS Grewal", "grewal.pdf")
        self.assertEqual(score, 0.0)

    def test_matching_title_and_author_scores_highly(self):
        cited = 'Grewal.B.S., "Higher Engineering Mathematics", Khanna, 2017.'
        score = _match_score(cited, "higher engineering mathematics", "BS Grewal", "grewal.pdf")
        self.assertGreater(score, 70.0)


if __name__ == "__main__":
    unittest.main()
