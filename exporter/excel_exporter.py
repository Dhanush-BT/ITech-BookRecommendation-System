"""
Writes the final recommendation rows to an .xlsx file using the exact
column schema from the design spec (Phase 12), one row per
(syllabus topic x recommended book).
"""
import re
from typing import List
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from matcher.recommendation_ranker import RecommendationRow
from utils.logger import log

# XML (and so .xlsx) forbids most ASCII control characters. A book with a
# corrupted font/encoding table (e.g. metadata_extractor misreading a
# garbled author string) can hand us one of these in an otherwise-fine
# string, which previously crashed the entire export - discarding every
# other already-computed row - deep into Phase 12. Stripped, not replaced,
# since these characters carry no legible content anyway.
_ILLEGAL_XML_CHARS_RE = re.compile(
    "[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x84\x86-\x9f\ud800-\udfff￾￿]"
)


def _sanitize(value):
    if isinstance(value, str):
        return _ILLEGAL_XML_CHARS_RE.sub("", value)
    return value


COLUMNS = [
    ("id", 6),
    ("subject_code", 14),
    ("subject_name", 32),
    ("module_number", 12),
    ("module_title", 30),
    ("topic", 34),
    ("sub_topic", 42),
    ("book_title", 34),
    ("author", 24),
    ("edition", 10),
    ("publisher", 16),
    ("year", 8),
    ("book_type", 12),
    ("chapter", 34),
    ("page_start", 10),
    ("page_end", 10),
    ("match_confidence_%", 18),
    ("notes", 10),
]

HEADER_FILL = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
HEADER_FONT = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
BODY_FONT = Font(name="Calibri", size=10)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT_WRAP = Alignment(horizontal="left", vertical="top", wrap_text=True)
THIN_BORDER = Border(*(Side(style="thin", color="D9D9D9"),) * 4)

NOTE_COLORS = {
    "Excellent": "C6EFCE",
    "Good": "FFEB9C",
    "Partial": "FFD966",
    "Weak": "F8CBAD",
}


def export_to_excel(rows: List[RecommendationRow], output_path: str):
    wb = Workbook()
    ws = wb.active
    ws.title = "Recommendations"

    for col_idx, (name, width) in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=name)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER
        ws.column_dimensions[get_column_letter(col_idx)].width = width
    ws.freeze_panes = "A2"

    # sort for a stable, readable report: by subject, module, topic, then coverage desc
    ordered = sorted(
        rows,
        key=lambda r: (r.subject_code, r.module_number, r.topic, -r.coverage_percent),
    )

    for i, row in enumerate(ordered, start=1):
        values = [
            i, row.subject_code, row.subject_name, row.module_number, row.module_title,
            row.topic, row.sub_topic, row.book_title, row.author, row.edition,
            row.publisher, row.year, row.book_type, row.chapter, row.page_start,
            row.page_end, row.coverage_percent, row.notes,
        ]
        excel_row = i + 1
        for col_idx, value in enumerate(values, start=1):
            cell = ws.cell(row=excel_row, column=col_idx, value=_sanitize(value))
            cell.font = BODY_FONT
            cell.border = THIN_BORDER
            col_name = COLUMNS[col_idx - 1][0]
            if col_name in ("page_start", "page_end", "match_confidence_%", "id", "module_number", "year"):
                cell.alignment = CENTER
            else:
                cell.alignment = LEFT_WRAP

        note_cell = ws.cell(row=excel_row, column=len(COLUMNS))
        fill_color = NOTE_COLORS.get(row.notes)
        if fill_color:
            note_cell.fill = PatternFill(start_color=fill_color, end_color=fill_color, fill_type="solid")

    if ordered:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}{len(ordered) + 1}"

    # Summary sheet
    summary = wb.create_sheet("Summary")
    summary.append(["Metric", "Value"])
    for c in summary[1]:
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
    total_topics = len({(r.subject_code, r.module_number, r.topic, r.sub_topic) for r in rows})
    subjects = sorted({r.subject_code for r in rows})
    summary.append(["Total recommendation rows", len(rows)])
    summary.append(["Distinct syllabus topics/subtopics covered", total_topics])
    summary.append(["Distinct subjects covered", len(subjects)])
    summary.append(["Distinct books recommended", len({r.book_title for r in rows})])
    for col, width in zip("AB", (42, 14)):
        summary.column_dimensions[col].width = width
    for r in summary.iter_rows(min_row=2):
        for cell in r:
            cell.font = BODY_FONT

    wb.save(output_path)
    log(f"Wrote {len(ordered)} rows to {output_path}")
