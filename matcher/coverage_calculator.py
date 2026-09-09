"""Combines the semantic/keyword/fuzzy/metadata signals into a single 0-100
coverage score, and rescales raw BGE cosine similarity onto a comparable 0-1
confidence axis before it enters that combination."""
import config
from extractors.metadata_extractor import BookMetadata


def rescale_semantic(raw_similarity: float) -> float:
    floor, ceiling = config.SEMANTIC_SIM_FLOOR, config.SEMANTIC_SIM_CEILING
    if ceiling <= floor:
        return max(0.0, min(1.0, raw_similarity))
    return max(0.0, min(1.0, (raw_similarity - floor) / (ceiling - floor)))


def metadata_score(metadata: BookMetadata) -> float:
    fields = [metadata.title, metadata.authors, metadata.edition, metadata.year]
    present = sum(1 for f in fields if f)
    return present / len(fields)


def combine_scores(semantic: float, keyword: float, fuzzy: float, metadata: float) -> float:
    raw = (
        config.WEIGHT_SEMANTIC * semantic
        + config.WEIGHT_KEYWORD * keyword
        + config.WEIGHT_FUZZY * fuzzy
        + config.WEIGHT_METADATA * metadata
    )
    return round(max(0.0, min(1.0, raw)) * 100, 1)


def coverage_label(coverage_percent: float) -> str:
    if coverage_percent >= 90:
        return "Excellent"
    if coverage_percent >= 75:
        return "Good"
    if coverage_percent >= config.MIN_COVERAGE_PERCENT:
        return "Moderate"
    if coverage_percent >= config.TENTATIVE_COVERAGE_PERCENT:
        return "Tentative"
    return "Weak"
