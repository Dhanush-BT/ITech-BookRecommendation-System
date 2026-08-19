"""
For every syllabus topic, scores every book chunk (chapter/section) using
the semantic + keyword + fuzzy + metadata signals, keeps the best-matching
chunk per book, ranks books by coverage, and returns the top N as
RecommendationRow objects ready for the Excel exporter.
"""
from dataclasses import dataclass, field
from typing import List, Dict
import itertools

from extractors.book_loader import BookRecord
from extractors.pdf_reader import PDFDocument, get_document
from indexing.chunk_generator import Chunk, generate_chunks
from indexing.embedding_builder import build_index, EmbeddingIndex
from matcher.semantic_matcher import semantic_scores
from matcher.keyword_matcher import keyword_score
from matcher.fuzzy_matcher import fuzzy_score
from matcher.coverage_calculator import combine_scores, coverage_label
from syllabus.syllabus_parser import SyllabusCourse, SyllabusModule
from utils.regex_patterns import tokenize
from utils.logger import log, section
import config


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
    page_start: int
    page_end: int
    coverage_percent: float
    notes: str


@dataclass
class BookCorpus:
    record: BookRecord
    doc: PDFDocument
    chunks: List[Chunk]


def build_corpus(book_records: List[BookRecord]) -> List[BookCorpus]:
    corpus = []
    for rec in book_records:
        doc = rec.doc if rec.doc is not None else get_document(rec.path)
        chunks = generate_chunks(doc, rec.chapters, rec.key)
        if not chunks:
            log(f"WARNING: book '{rec.key}' produced zero chunks - it will "
                f"never be recommended. Check its TOC/heading extraction.", "WARN")
        corpus.append(BookCorpus(record=rec, doc=doc, chunks=chunks))
    return corpus


def _metadata_bonus(topic_text: str, book_title: str) -> float:
    topic_tokens = set(tokenize(topic_text))
    title_tokens = set(tokenize(book_title))
    if not topic_tokens or not title_tokens:
        return 0.0
    overlap = len(topic_tokens & title_tokens)
    return min(overlap / max(len(topic_tokens), 1), 1.0)


def _best_chunk_per_book(all_chunks: List[Chunk], sims: List[float]) -> Dict[str, tuple]:
    """Returns {book_key: (chunk, semantic_score)} keeping only the single
    highest-scoring chunk for each book."""
    best: Dict[str, tuple] = {}
    for chunk, sim in zip(all_chunks, sims):
        current = best.get(chunk.book_key)
        if current is None or sim > current[1]:
            best[chunk.book_key] = (chunk, sim)
    return best


def rank_books_for_topic(index: EmbeddingIndex, all_chunks: List[Chunk],
                          corpus_by_key: Dict[str, BookCorpus],
                          topic_text: str, subject_hint: str = "") -> List[dict]:
    sims = semantic_scores(index, topic_text)
    best_per_book = _best_chunk_per_book(all_chunks, sims)

    scored = []
    for book_key, (chunk, sem) in best_per_book.items():
        title_text = f"{chunk.chapter_title} {chunk.section_title}".strip()
        kw = keyword_score(topic_text, title_text, chunk.text)
        fz = fuzzy_score(topic_text, title_text)
        book_title = corpus_by_key[book_key].record.metadata.title
        meta = _metadata_bonus(subject_hint or topic_text, book_title)
        coverage = combine_scores(sem, kw, fz, meta)
        scored.append({
            "book_key": book_key, "chunk": chunk, "coverage": coverage,
            "semantic": sem, "keyword": kw, "fuzzy": fz, "metadata": meta,
        })

    scored.sort(key=lambda r: r["coverage"], reverse=True)
    return scored[:config.TOP_N_BOOKS_PER_TOPIC]


def generate_recommendations(courses: List[SyllabusCourse],
                              book_corpus: List[BookCorpus]) -> List[RecommendationRow]:
    section("Matching syllabus topics against book corpus")

    all_chunks = list(itertools.chain.from_iterable(c.chunks for c in book_corpus))
    corpus_by_key = {c.record.key: c for c in book_corpus}

    if not all_chunks:
        log("No book chunks available at all - cannot produce recommendations.", "ERROR")
        return []

    index = build_index(all_chunks)

    rows: List[RecommendationRow] = []
    topic_count = 0
    for course in courses:
        for module in course.modules:
            # Query the granular topics when we have them; only fall back to
            # the coarse unit title itself when no topics were parsed for
            # this module. Querying both (as before) routinely produced two
            # near-duplicate rows - the unit-title query and a topic query -
            # landing on the same book chunk with near-identical coverage
            # whenever a module's topic text closely echoes its own title.
            if module.topics:
                targets = [(module.unit_title, t) for t in module.topics]
            else:
                targets = [("", module.unit_title)]
            for parent_topic, topic_text in targets:
                topic_count += 1
                ranked = rank_books_for_topic(
                    index, all_chunks, corpus_by_key, topic_text,
                    subject_hint=course.name,
                )
                for r in ranked:
                    if r["coverage"] < config.MIN_COVERAGE_PERCENT:
                        continue
                    chunk = r["chunk"]
                    meta = corpus_by_key[r["book_key"]].record.metadata
                    chapter_label = chunk.chapter_label
                    if chunk.section_label:
                        chapter_label = f"{chunk.chapter_label}.{chunk.section_label}" \
                            if chunk.section_label and not chunk.section_label.startswith(chunk.chapter_label) \
                            else chunk.section_label
                    chapter_display = f"{chapter_label} {chunk.section_title or chunk.chapter_title}".strip()

                    rows.append(RecommendationRow(
                        subject_code=course.code,
                        subject_name=course.name,
                        module_number=module.unit_label,
                        module_title=module.unit_title,
                        topic=parent_topic or module.unit_title,
                        sub_topic=topic_text if parent_topic else "",
                        book_title=meta.title,
                        author=meta.authors,
                        edition=meta.edition,
                        publisher=meta.publisher,
                        year=meta.year,
                        book_type=meta.book_type,
                        chapter=chapter_display,
                        page_start=chunk.page_start,
                        page_end=chunk.page_end,
                        coverage_percent=round(r["coverage"], 1),
                        notes=coverage_label(r["coverage"]),
                    ))

    log(f"Evaluated {topic_count} syllabus topics/subtopics -> {len(rows)} recommendation rows "
        f"(coverage >= {config.MIN_COVERAGE_PERCENT}%)")
    return rows
