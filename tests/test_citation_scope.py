import unittest

from matcher.citation_scope import UNRESTRICTED, parse_citation_scope

_STEWART = (
    'James Stewart, "Calculus: Early Transcendentals", Cengage Learning, 8th '
    "Edition, New Delhi, 2015. [For Units II & IV - Sections 1.1, 2.2, 2.3, 2.5, "
    "2.7 (Tangents problems only), 2.8, 3.1 to 3.6, 3.11, 4.1, 4.3, 5.1 (Area "
    "problems only), 5.2, 5.3, 5.4 (excluding net change theorem), 5.5, 7.1 - "
    "7.4 and 7.8]."
)


class TestCitationScope(unittest.TestCase):
    def test_no_bracket_note_is_unrestricted(self):
        scope = parse_citation_scope(
            'Kreyszig, "Advanced Engineering Mathematics", Wiley, 2011.'
        )
        self.assertIs(scope, UNRESTRICTED)

    def test_non_scope_bracket_is_unrestricted(self):
        self.assertIs(parse_citation_scope('Foo, "Bar", 2020. [reprint]'), UNRESTRICTED)

    def test_units_and_sections_combined(self):
        scope = parse_citation_scope(_STEWART)
        self.assertEqual(scope.units, frozenset({2, 4}))
        self.assertIn("3.4", scope.sections)  # from "3.1 to 3.6"
        self.assertIn("7.3", scope.sections)  # from "7.1 - 7.4"
        self.assertIn("2.7", scope.sections)
        self.assertNotIn("6.1", scope.sections)

    def test_combined_scope_gates_units(self):
        scope = parse_citation_scope(_STEWART)
        self.assertTrue(scope.allows_unit(2))
        self.assertFalse(scope.allows_unit(3))
        self.assertTrue(scope.allows_unit(None))

    def test_units_only_with_word_and(self):
        scope = parse_citation_scope('Foo, "Bar", 2020. [For Units I, III and V]')
        self.assertEqual(scope.units, frozenset({1, 3, 5}))
        self.assertEqual(scope.sections, frozenset())

    def test_units_only_ampersand(self):
        scope = parse_citation_scope('Foo, "Bar", 2020. [For Units II & IV]')
        self.assertEqual(scope.units, frozenset({2, 4}))

    def test_unit_range_is_expanded(self):
        self.assertEqual(
            parse_citation_scope('Foo, "Bar". [For Units I to IV]').units,
            frozenset({1, 2, 3, 4}),
        )
        self.assertEqual(
            parse_citation_scope('Foo, "Bar". [For Units 1 - 3]').units,
            frozenset({1, 2, 3}),
        )

    def test_single_unit(self):
        scope = parse_citation_scope('Foo, "Bar". [For Unit III only]')
        self.assertEqual(scope.units, frozenset({3}))

    def test_sections_only(self):
        scope = parse_citation_scope('Foo, "Bar". [Sections 1.1 to 1.4]')
        self.assertEqual(scope.units, frozenset())
        self.assertEqual(scope.sections, frozenset({"1.1", "1.2", "1.3", "1.4"}))

    def test_allows_section_semantics(self):
        scope = parse_citation_scope('Foo, "Bar". [Sections 1.1, 1.2]')
        self.assertTrue(scope.allows_section("1.1"))
        self.assertFalse(scope.allows_section("9.9"))
        # unrestricted scope allows anything
        self.assertTrue(UNRESTRICTED.allows_section("9.9"))
        self.assertTrue(UNRESTRICTED.allows_unit(7))

    def test_last_bracket_wins(self):
        scope = parse_citation_scope(
            'Foo, "Bar" [2nd printing] , 2019. [For Units I & II]'
        )
        self.assertEqual(scope.units, frozenset({1, 2}))


if __name__ == "__main__":
    unittest.main()
