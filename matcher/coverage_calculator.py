"""
Combines the individual similarity signals (semantic / keyword / fuzzy /
metadata) into the single 'Coverage %' figure the spreadsheet reports, using
the weighted formula from the design spec:

    Coverage = 0.45*Semantic + 0.25*Keyword + 0.20*Fuzzy + 0.10*Metadata

(Weights are configurable in config.py; the design doc's own 5-term formula
also included a standalone "Chapter similarity" term - since our chunks are
already chapter/section-scoped, that signal is folded into Keyword+Fuzzy
rather than duplicated as a separate weight.)
"""
import config


def combine_scores(semantic: float, keyword: float, fuzzy: float, metadata: float) -> float:
    raw = (
        config.WEIGHT_SEMANTIC * semantic +
        config.WEIGHT_KEYWORD * keyword +
        config.WEIGHT_FUZZY * fuzzy +
        config.WEIGHT_METADATA * metadata
    )
    return max(0.0, min(1.0, raw)) * 100.0


def coverage_label(coverage_percent: float) -> str:
    if coverage_percent >= 85:
        return "Excellent"
    if coverage_percent >= 65:
        return "Good"
    if coverage_percent >= config.MIN_COVERAGE_PERCENT:
        return "Partial"
    return "Weak"
