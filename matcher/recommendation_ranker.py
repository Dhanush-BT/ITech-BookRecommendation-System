"""Top-level matching orchestrator. For every syllabus topic, matching is
scoped to only the subject's resolved cited books (strict scoping): textbook
citations are tried first, reference citations only if no textbook clears the
coverage threshold, and a topic with no qualifying match anywhere gets an
explicit Not Found row rather than being silently dropped -- every syllabus
topic must produce at least one output row."""
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

import config
from extractors.book_loader import BookRecord
from indexing.chunk_generator import Chunk, generate_chunks
from indexing.embedding_cache import load_or_build_book_embeddings
from indexing.embedding_model import EmbeddingModel
from indexing.vector_index import EmbeddingIndex
from matcher.citation_scope import UNRESTRICTED, CitationScope, parse_citation_scope
from matcher.coverage_calculator import combine_scores, coverage_label, metadata_score
from matcher.fuzzy_matcher import fuzzy_score
from matcher.keyword_matcher import keyword_score
from matcher.reference_resolver import ResolvedReference, split_resolved_keys
from matcher.semantic_matcher import semantic_scores
from pdfcore.pdf_reader import PDFDocument
from syllabus.syllabus_parser import SyllabusCourse, SyllabusModule
from utils.logger import log


# Multiplicative demotions applied to a match that falls outside a citation's
# explicit unit / section scope note. Chosen to reorder near-ties toward the
# in-scope book without, on their own, pushing an otherwise-solid match under
# the Not-Found threshold.
_OUT_OF_UNIT_PENALTY = 0.90
_OUT_OF_SECTION_PENALTY = 0.94


@dataclass
class BookCorpus:
    record: BookRecord
    doc: PDFDocument
    chunks: List[Chunk]


@dataclass
class RecommendationRow:
    syllabus_name: str
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
    page_start: Optional[int]  # printed page number as it appears in the book
    page_end: Optional[int]
    pdf_page_start: Optional[int]  # 1-indexed position within the PDF file
    pdf_page_end: Optional[int]
    coverage_percent: float
    status: str  # "Found" | "Tentative" | "Not Found"
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


def _semantic_query(topic_text: str, module: SyllabusModule) -> str:
    """Terse topics ("Jacobians", "Continuity") give the embedder very little
    to work with. Fold in the unit title as disambiguating context when the
    topic is short; longer topics already carry enough on their own."""
    if len(topic_text.split()) >= 4:
        return topic_text
    unit_title = module.unit_title.strip()
    if unit_title and not unit_title.upper().startswith("UNIT"):
        return f"{topic_text} ({unit_title.title()})"
    return topic_text


def _score_book_candidates(
    topic_text: str,
    book_keys: List[str],
    corpus_by_key: Dict[str, BookCorpus],
    indices: Dict[str, EmbeddingIndex],
    model: EmbeddingModel,
    unit_number: Optional[int] = None,
    scope_by_book_key: Optional[Dict[str, CitationScope]] = None,
    query_text: Optional[str] = None,
) -> List[Tuple[str, Chunk, float]]:
    """Best (book_key, chunk, coverage_percent) per book, sorted best-first.

    When a book's citation carries an explicit unit/section restriction (see
    matcher.citation_scope), that's a strong ranking signal -- a match in a
    unit or section the syllabus didn't assign this book to is demoted (see
    _OUT_OF_UNIT_PENALTY / _OUT_OF_SECTION_PENALTY), so an in-scope book wins
    when both are viable. It is deliberately NOT a hard filter: if the
    scoped-out book is the only one that covers the topic at all, a demoted
    match still beats leaving the topic with nothing."""
    scope_by_book_key = scope_by_book_key or {}
    query_text = query_text or topic_text
    results = []
    for book_key in book_keys:
        scope = scope_by_book_key.get(book_key, UNRESTRICTED)
        unit_ok = scope.allows_unit(unit_number)
        index = indices.get(book_key)
        bc = corpus_by_key.get(book_key)
        if index is None or bc is None or not bc.chunks:
            continue
        sem = semantic_scores(query_text, index, model)
        chunk_by_id = {c.chunk_id: c for c in bc.chunks}
        md_score = metadata_score(bc.record.metadata)

        # A section restriction is only meaningful if this book's chunks
        # actually carry labels that line up with it -- heading-fallback books
        # (and any book whose TOC didn't parse into numbered sections) carry
        # none, so the section demotion is simply not applied to them.
        section_scope_usable = scope.sections and any(
            scope.allows_section(c.section_label) for c in bc.chunks
        )

        best_chunk, best_cov = None, -1.0
        for chunk_id, sem_score in sem.items():
            chunk = chunk_by_id.get(chunk_id)
            if chunk is None:
                continue
            title = f"{chunk.chapter_title} {chunk.section_title}".strip()
            kw = keyword_score(topic_text, title, chunk.text)
            fz = fuzzy_score(topic_text, title)
            cov = combine_scores(sem_score, kw, fz, md_score)
            if not unit_ok:
                cov *= _OUT_OF_UNIT_PENALTY
            if section_scope_usable and not scope.allows_section(chunk.section_label):
                cov *= _OUT_OF_SECTION_PENALTY
            if cov > best_cov:
                best_cov, best_chunk = cov, chunk
        if best_chunk is not None:
            results.append((book_key, best_chunk, round(best_cov, 1)))

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
            syllabus_name=os.path.basename(course.source_file),
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
            pdf_page_start=None,
            pdf_page_end=None,
            coverage_percent=0.0,
            status="Not Found",
            notes=notes or "No cited book available locally covers this topic above threshold",
        )

    meta = corpus_by_key[book_key].record.metadata
    chapter_label = chunk.section_label or chunk.chapter_label
    chapter_title = chunk.section_title or chunk.chapter_title
    return RecommendationRow(
        syllabus_name=os.path.basename(course.source_file),
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
        page_start=chunk.book_page_start if chunk.book_page_start is not None else chunk.page_start + 1,
        page_end=chunk.book_page_end if chunk.book_page_end is not None else chunk.page_end + 1,
        pdf_page_start=chunk.page_start + 1,  # 1-indexed position within the PDF file
        pdf_page_end=chunk.page_end + 1,
        coverage_percent=coverage,
        status="Found" if coverage >= config.MIN_COVERAGE_PERCENT else "Tentative",
        notes=notes or coverage_label(coverage),
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

        scope_by_book_key: Dict[str, CitationScope] = {}
        for r in resolved:
            if r.book_key is None:
                continue
            scope = parse_citation_scope(r.cited.raw_line)
            existing = scope_by_book_key.get(r.book_key)
            if existing is None or existing is UNRESTRICTED:
                scope_by_book_key[r.book_key] = scope

        # Cited books that resolved to a local file but yielded no usable text
        # (scanned-image PDFs with no text layer) -- worth calling out on a
        # Not Found row so the gap is understood as "needs OCR", not "wrong".
        unreadable = sorted(
            corpus_by_key[k].record.metadata.title or k
            for k in set(textbook_keys) | set(reference_keys)
            if k in corpus_by_key and not corpus_by_key[k].chunks
        )

        for module, topic_text in course.all_topics():
            unit_number = module.unit_number
            query_text = _semantic_query(topic_text, module)

            textbook_candidates = _score_book_candidates(
                topic_text, textbook_keys, corpus_by_key, indices, model,
                unit_number, scope_by_book_key, query_text,
            ) if textbook_keys else []
            reference_candidates = _score_book_candidates(
                topic_text, reference_keys, corpus_by_key, indices, model,
                unit_number, scope_by_book_key, query_text,
            ) if reference_keys else []

            # Textbooks first: only fall through to references if no textbook
            # clears the full coverage bar.
            for pool in (textbook_candidates, reference_candidates):
                passing = [c for c in pool if c[2] >= config.MIN_COVERAGE_PERCENT]
                if passing:
                    for book_key, chunk, cov in passing[: config.TOP_N_BOOKS_PER_TOPIC]:
                        rows.append(_make_row(course, module, topic_text, book_key, chunk, cov, corpus_by_key))
                    break
            else:
                # Nothing cleared MIN_COVERAGE_PERCENT. Report the single best
                # candidate as "Tentative" rather than "Not Found" when it at
                # least clears the weaker bar, so a real (if broad) chapter
                # reference isn't dropped for a terse topic.
                best = max(
                    textbook_candidates + reference_candidates,
                    key=lambda c: c[2],
                    default=None,
                )
                if best is not None and best[2] >= config.TENTATIVE_COVERAGE_PERCENT:
                    book_key, chunk, cov = best
                    rows.append(_make_row(course, module, topic_text, book_key, chunk, cov, corpus_by_key))
                else:
                    if not textbook_keys and not reference_keys:
                        notes = "No cited textbook/reference for this subject was found among the local books"
                    else:
                        notes = "Cited books available locally, but none covered this topic above the coverage threshold"
                    if unreadable:
                        notes += f" (no extractable text in: {', '.join(unreadable)} -- scanned PDF, needs OCR)"
                    rows.append(_make_row(course, module, topic_text, None, None, 0.0, corpus_by_key, notes=notes))

    return rows
