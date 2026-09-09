import unittest

from matcher.recommendation_ranker import _semantic_query
from syllabus.syllabus_parser import SyllabusModule


def _module(title):
    return SyllabusModule(unit_label="UNIT I", unit_number=1, unit_title=title)


class TestSemanticQuery(unittest.TestCase):
    def test_short_topic_gets_unit_title_context(self):
        self.assertEqual(
            _semantic_query("Jacobians", _module("FUNCTIONS OF SEVERAL VARIABLES")),
            "Jacobians (Functions Of Several Variables)",
        )

    def test_long_topic_left_untouched(self):
        topic = "Applications of maxima and minima of functions of two variables"
        self.assertEqual(_semantic_query(topic, _module("MULTIPLE INTEGRALS")), topic)

    def test_no_usable_unit_title(self):
        self.assertEqual(_semantic_query("Jacobians", _module("UNIT I")), "Jacobians")
        self.assertEqual(_semantic_query("Jacobians", _module("")), "Jacobians")


if __name__ == "__main__":
    unittest.main()
