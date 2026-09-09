import unittest

import config
from matcher.coverage_calculator import combine_scores, coverage_label, rescale_semantic


class TestCoverageCalculator(unittest.TestCase):
    def test_weights_sum_to_one(self):
        total = (
            config.WEIGHT_SEMANTIC + config.WEIGHT_KEYWORD + config.WEIGHT_FUZZY + config.WEIGHT_METADATA
        )
        self.assertAlmostEqual(total, 1.0, places=6)

    def test_combine_scores_all_ones_is_100(self):
        self.assertEqual(combine_scores(1.0, 1.0, 1.0, 1.0), 100.0)

    def test_combine_scores_all_zeros_is_0(self):
        self.assertEqual(combine_scores(0.0, 0.0, 0.0, 0.0), 0.0)

    def test_combine_scores_clamped_to_0_100(self):
        self.assertEqual(combine_scores(2.0, 2.0, 2.0, 2.0), 100.0)
        self.assertEqual(combine_scores(-1.0, -1.0, -1.0, -1.0), 0.0)

    def test_coverage_label_thresholds(self):
        self.assertEqual(coverage_label(95), "Excellent")
        self.assertEqual(coverage_label(80), "Good")
        self.assertEqual(coverage_label(config.MIN_COVERAGE_PERCENT), "Moderate")
        self.assertEqual(coverage_label(config.MIN_COVERAGE_PERCENT - 1), "Tentative")
        self.assertEqual(coverage_label(config.TENTATIVE_COVERAGE_PERCENT), "Tentative")
        self.assertEqual(coverage_label(config.TENTATIVE_COVERAGE_PERCENT - 1), "Weak")

    def test_rescale_semantic_floor_and_ceiling(self):
        self.assertEqual(rescale_semantic(config.SEMANTIC_SIM_FLOOR), 0.0)
        self.assertEqual(rescale_semantic(config.SEMANTIC_SIM_CEILING), 1.0)
        self.assertEqual(rescale_semantic(config.SEMANTIC_SIM_FLOOR - 1), 0.0)
        self.assertEqual(rescale_semantic(config.SEMANTIC_SIM_CEILING + 1), 1.0)

    def test_rescale_semantic_midpoint(self):
        mid = (config.SEMANTIC_SIM_FLOOR + config.SEMANTIC_SIM_CEILING) / 2
        self.assertAlmostEqual(rescale_semantic(mid), 0.5, places=6)


if __name__ == "__main__":
    unittest.main()
