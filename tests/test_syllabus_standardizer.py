import unittest

from syllabus.standardizer import standardize_syllabus_text
from syllabus.syllabus_parser import _parse_cited_books, _parse_units


class TestUnitHeaderSynonyms(unittest.TestCase):
    def test_module_synonym_rewritten_to_unit(self):
        text = "MODULE 1 INTRODUCTION 9\nBasics – Overview.\nMODULE-II ADVANCED 9\nDetails.\n"
        standardized, changes = standardize_syllabus_text(text)
        self.assertIn("unit_header_synonym", changes)
        modules = _parse_units(standardized)
        self.assertEqual(len(modules), 2)
        self.assertEqual(modules[0].unit_number, 1)
        self.assertEqual(modules[1].unit_number, 2)

    def test_chapter_synonym_rewritten_to_unit(self):
        text = "CHAPTER I BASICS 9\nTopic A – Topic B.\n"
        standardized, changes = standardize_syllabus_text(text)
        self.assertIn("unit_header_synonym", changes)
        self.assertTrue(standardized.lstrip().upper().startswith("UNIT"))

    def test_already_canonical_unit_header_is_untouched(self):
        text = "UNIT – I KINEMATICS 9\nMechanisms – cams.\n"
        standardized, changes = standardize_syllabus_text(text)
        self.assertNotIn("unit_header_synonym", changes)
        self.assertEqual(standardized, text)


class TestObjectivesSynonyms(unittest.TestCase):
    def test_aim_header_rewritten_to_objectives(self):
        text = "CS3591 SOFTWARE ENGINEERING  L T P C\n3 0 0 3\nAIM:\nTo teach basics.\nUNIT I INTRO 9\n"
        standardized, changes = standardize_syllabus_text(text)
        self.assertIn("objectives_header_synonym", changes)
        self.assertIn("OBJECTIVES:", standardized)

    def test_course_aims_header_rewritten(self):
        text = "COURSE AIMS\nTo teach basics.\n"
        standardized, changes = standardize_syllabus_text(text)
        self.assertIn("objectives_header_synonym", changes)
        self.assertIn("OBJECTIVES:", standardized)


class TestBookSectionSynonyms(unittest.TestCase):
    def test_parenthetical_plural_textbook_header_is_normalized(self):
        text = 'Text Book(s):\n1. "Title One", Author A, Publisher, 2020\n'
        standardized, changes = standardize_syllabus_text(text)
        self.assertIn("book_parenthetical_plural", changes)
        cited = _parse_cited_books(standardized)
        self.assertEqual(len(cited), 1)
        self.assertEqual(cited[0].citation_type, "textbook")

    def test_parenthetical_plural_reference_header_is_normalized(self):
        text = 'Reference Books(s):\n1. "Title Two", Author B, Publisher, 2019\n'
        standardized, changes = standardize_syllabus_text(text)
        self.assertIn("book_parenthetical_plural", changes)
        cited = _parse_cited_books(standardized)
        self.assertEqual(len(cited), 1)
        self.assertEqual(cited[0].citation_type, "reference")

    def test_prescribed_books_rewritten_to_textbooks(self):
        text = 'PRESCRIBED BOOKS:\n1. Author A, "Title One", Publisher, 2020.\n'
        standardized, changes = standardize_syllabus_text(text)
        self.assertIn("textbook_header_synonym", changes)
        cited = _parse_cited_books(standardized)
        self.assertEqual(len(cited), 1)
        self.assertEqual(cited[0].citation_type, "textbook")

    def test_bibliography_rewritten_to_reference_books(self):
        text = 'BIBLIOGRAPHY\n1. Author B, "Title Two", Publisher, 2019.\n'
        standardized, changes = standardize_syllabus_text(text)
        self.assertIn("reference_header_synonym", changes)
        cited = _parse_cited_books(standardized)
        self.assertEqual(len(cited), 1)
        self.assertEqual(cited[0].citation_type, "reference")

    def test_suggested_readings_rewritten_to_reference_books(self):
        text = 'SUGGESTED READINGS:\n1. Author C, "Title Three", Publisher, 2018.\n'
        standardized, _ = standardize_syllabus_text(text)
        cited = _parse_cited_books(standardized)
        self.assertEqual(cited[0].citation_type, "reference")

    def test_recommended_text_books_goes_to_textbook_not_reference(self):
        text = 'RECOMMENDED TEXT BOOKS:\n1. Author D, "Title Four", Publisher, 2021.\n'
        standardized, changes = standardize_syllabus_text(text)
        self.assertIn("textbook_header_synonym", changes)
        self.assertNotIn("reference_header_synonym", changes)
        cited = _parse_cited_books(standardized)
        self.assertEqual(cited[0].citation_type, "textbook")


class TestBulletTopics(unittest.TestCase):
    def test_bullet_markers_become_topic_separators(self):
        text = "UNIT I BASICS 9\n• Overview of X\n• History of Y\n• Basics of Z\n"
        standardized, changes = standardize_syllabus_text(text)
        self.assertIn("bullet_marker", changes)
        modules = _parse_units(standardized)
        self.assertIn("Overview of X", modules[0].topics)
        self.assertIn("History of Y", modules[0].topics)
        self.assertIn("Basics of Z", modules[0].topics)


class TestWhitespaceNoise(unittest.TestCase):
    def test_nbsp_and_formfeed_are_cleaned(self):
        text = "UNIT\xa0I\xa0BASICS 9\x0cTopic A – Topic B.\n"
        standardized, changes = standardize_syllabus_text(text)
        self.assertIn("whitespace_noise", changes)
        self.assertNotIn("\xa0", standardized)
        self.assertNotIn("\x0c", standardized)


class TestIdempotency(unittest.TestCase):
    def test_running_twice_is_stable(self):
        text = 'MODULE 1 INTRO 9\n• Topic A\nPRESCRIBED BOOKS:\n1. X, "Y", Z, 2020.\n'
        once, _ = standardize_syllabus_text(text)
        twice, changes_second_pass = standardize_syllabus_text(once)
        self.assertEqual(once, twice)
        self.assertEqual(changes_second_pass, {})


if __name__ == "__main__":
    unittest.main()
