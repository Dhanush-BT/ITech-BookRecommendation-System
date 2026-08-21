"""Top-level matching orchestrator. For every syllabus topic, matching is
scoped to only the subject's resolved cited books (strict scoping): textbook
citations are tried first, reference citations only if no textbook clears the
coverage threshold, and a topic with no qualifying match anywhere gets an
explicit Not Found row rather than being silently dropped -- every syllabus
topic must produce at least one output row."""
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

import config
from extractors.book_loader import BookRecord
from indexing.chunk_generator import Chunk, generate_chunks
from indexing.embedding_cache import load_or_build_book_embeddings
from indexing.embedding_model import EmbeddingModel
from indexing.vector_index import EmbeddingIndex
from matcher.coverage_calculator import combine_scores, coverage_label, metadata_score
from matcher.fuzzy_matcher import fuzzy_score
from matcher.keyword_matcher import keyword_score
from matcher.reference_resolver import ResolvedReference, split_resolved_keys
from matcher.semantic_matcher import semantic_scores
from pdfcore.pdf_reader import PDFDocument
from syllabus.syllabus_parser import SyllabusCourse, SyllabusModule
from utils.logger import log


@dataclass
class BookCorpus:
    record: BookRecord
    doc: PDFDocument
    chunks: List[Chunk]


@dataclass
class RecommendationRow:
    subject_code: str
    subject_name: str
    module_number: str
    module_title: str
    topic: str
    sub_topic: str
    book_title: str
    author: str
    edition: str
    publisher: str
    year: str
    book_type: str
    chapter: str
    page_start: Optional[int]
    page_end: Optional[int]
    coverage_percent: float
    status: str  # "Found" | "Not Found"
    notes: str = ""


def build_corpus(records: List[BookRecord]) -> List[BookCorpus]:
    corpus = []
    for rec in records:
        chunks = generate_chunks(rec.doc, rec.chapters, rec.key)
        corpus.append(BookCorpus(record=rec, doc=rec.doc, chunks=chunks))
    return corpus


def build_indices_for_keys(
    book_keys: List[str], corpus_by_key: Dict[str, BookCorpus], model: EmbeddingModel
) -> Dict[str, EmbeddingIndex]:
    """Lazily builds (or loads from cache) an EmbeddingIndex per book, only for
    the books actually cited/resolved by some subject -- under strict scoping
    there's no reason to embed books nothing will ever match against."""
    indices: Dict[str, EmbeddingIndex] = {}
    for i, key in enumerate(book_keys, 1):
        bc = corpus_by_key.get(key)
        if bc is None or not bc.chunks:
            continue
        log(f"[{i}/{len(book_keys)}] embedding {key} ({len(bc.chunks)} chunks) ...")
        subchunks, vectors = load_or_build_book_embeddings(bc.record.path, key, bc.chunks, model)
        if subchunks:
            indices[key] = _index_from_encoded(subchunks, vectors)
    return indices


def _index_from_encoded(subchunks, vectors) -> EmbeddingIndex:
    """Builds an EmbeddingIndex from already-encoded (possibly cache-loaded)
    vectors, without re-encoding -- build_index() re-encodes from scratch, which
    would defeat the embedding cache."""
    sorted_pairs = sorted(zip(subchunks, range(len(subchunks))), key=lambda p: (p[0].parent_chunk_id, p[0].subchunk_index))
    order = [i for _, i in sorted_pairs]
    sorted_subchunks = [subchunks[i] for i in order]
    sorted_vectors = vectors[order]

    chunk_ids: List[str] = []
    boundaries: List[int] = []
    last_id = None
    for i, sc in enumerate(sorted_subchunks):
        if sc.parent_chunk_id != last_id:
            chunk_ids.append(sc.parent_chunk_id)
            boundaries.append(i)
            last_id = sc.parent_chunk_id

    return EmbeddingIndex(
        subchunks=sorted_subchunks,
        vectors=sorted_vectors,
        chunk_ids=chunk_ids,
        group_boundaries=np.array(boundaries, dtype=np.int64),
    )


def _score_book_candidates(
    topic_text: str,
    book_keys: List[str],
    corpus_by_key: Dict[str, BookCorpus],
    indices: Dict[str, EmbeddingIndex],
    model: EmbeddingModel,
) -> List[Tuple[str, Chunk, float]]:
    """Best (book_key, chunk, coverage_percent) per book, sorted best-first."""
    results = []
    for book_key in book_keys:
        index = indices.get(book_key)
        bc = corpus_by_key.get(book_key)
        if index is None or bc is None or not bc.chunks:
            continue
        sem = semantic_scores(topic_text, index, model)
        chunk_by_id = {c.chunk_id: c for c in bc.chunks}
        md_score = metadata_score(bc.record.metadata)

        best_chunk, best_cov = None, -1.0
        for chunk_id, sem_score in sem.items():
            chunk = chunk_by_id.get(chunk_id)
            if chunk is None:
                continue
            title = f"{chunk.chapter_title} {chunk.section_title}".strip()
            kw = keyword_score(topic_text, title, chunk.text)
            fz = fuzzy_score(topic_text, title)
            cov = combine_scores(sem_score, kw, fz, md_score)
            if cov > best_cov:
                best_cov, best_chunk = cov, chunk
        if best_chunk is not None:
            results.append((book_key, best_chunk, best_cov))

    results.sort(key=lambda r: -r[2])
    return results


def _make_row(
    course: SyllabusCourse,
    module: SyllabusModule,
    topic_text: str,
    book_key: Optional[str],
    chunk: Optional[Chunk],
    coverage: float,
    corpus_by_key: Dict[str, BookCorpus],
    notes: str = "",
) -> RecommendationRow:
    if book_key is None or chunk is None:
        return RecommendationRow(
            subject_code=course.code,
            subject_name=course.name,
            module_number=str(module.unit_number) if module.unit_number else module.unit_label,
            module_title=module.unit_title,
            topic=topic_text,
            sub_topic="",
            book_title="",
            author="",
            edition="",
            publisher="",
            year="",
            book_type="",
            chapter="",
            page_start=None,
            page_end=None,
            coverage_percent=0.0,
            status="Not Found",
            notes=notes or "No cited book available locally covers this topic above threshold",
        )

    meta = corpus_by_key[book_key].record.metadata
    chapter_label = chunk.section_label or chunk.chapter_label
    chapter_title = chunk.section_title or chunk.chapter_title
    return RecommendationRow(
        subject_code=course.code,
        subject_name=course.name,
        module_number=str(module.unit_number) if module.unit_number else module.unit_label,
        module_title=module.unit_title,
        topic=topic_text,
        sub_topic="",
        book_title=meta.title,
        author=meta.authors,
        edition=meta.edition,
        publisher=meta.publisher,
        year=meta.year,
        book_type=meta.book_type,
        chapter=f"{chapter_label} {chapter_title}".strip(),
        page_start=chunk.page_start + 1,  # report as 1-indexed printed-style pages
        page_end=chunk.page_end + 1,
        coverage_percent=coverage,
        status="Found",
        notes=coverage_label(coverage),
    )


def generate_recommendations(
    courses: List[SyllabusCourse],
    resolved_by_subject: Dict[str, List[ResolvedReference]],
    corpus_by_key: Dict[str, BookCorpus],
    indices: Dict[str, EmbeddingIndex],
    model: EmbeddingModel,
) -> List[RecommendationRow]:
    rows: List[RecommendationRow] = []

    for course in courses:
        resolved = resolved_by_subject.get(course.code, [])
        textbook_keys, reference_keys = split_resolved_keys(resolved)

        for module, topic_text in course.all_topics():
            candidates: List[Tuple[str, Chunk, float]] = []
            if textbook_keys:
                candidates = _score_book_candidates(topic_text, textbook_keys, corpus_by_key, indices, model)
                passing = [c for c in candidates if c[2] >= config.MIN_COVERAGE_PERCENT]
                if passing:
                    for book_key, chunk, cov in passing[: config.TOP_N_BOOKS_PER_TOPIC]:
                        rows.append(_make_row(course, module, topic_text, book_key, chunk, cov, corpus_by_key))
                    continue

            if reference_keys:
                candidates = _score_book_candidates(topic_text, reference_keys, corpus_by_key, indices, model)
                passing = [c for c in candidates if c[2] >= config.MIN_COVERAGE_PERCENT]
                if passing:
                    for book_key, chunk, cov in passing[: config.TOP_N_BOOKS_PER_TOPIC]:
                        rows.append(_make_row(course, module, topic_text, book_key, chunk, cov, corpus_by_key))
                    continue

            if not textbook_keys and not reference_keys:
                notes = "No cited textbook/reference for this subject was found among the local books"
            else:
                notes = "Cited books available locally, but none covered this topic above the coverage threshold"
            rows.append(_make_row(course, module, topic_text, None, None, 0.0, corpus_by_key, notes=notes))

    return rows
