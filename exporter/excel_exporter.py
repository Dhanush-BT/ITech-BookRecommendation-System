"""Writes RecommendationRow list to a formatted .xlsx: a Recommendations sheet
plus a Summary sheet with per-subject Found/Not-Found counts. Sanitizes
illegal XML control characters -- raw PDF-extracted text can contain bytes
openpyxl/Excel's XML format rejects outright, which previously broke exports."""
import re
from collections import defaultdict
from typing import List

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from matcher.recommendation_ranker import RecommendationRow

# XML 1.0 disallows most C0 control chars (keep tab/newline/CR) and the
# surrogate range; anything else here raises an openpyxl write error.
_ILLEGAL_XML_RE = re.compile(
    "[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\ud800-\udfff￾￿]"
)

_HEADER_FILL = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
_HEADER_FONT = Font(color="FFFFFF", bold=True)

_COLUMNS = [
    ("subject_code", "Subject Code"),
    ("subject_name", "Subject Name"),
    ("module_number", "Unit"),
    ("module_title", "Unit Title"),
    ("topic", "Topic"),
    ("sub_topic", "Sub Topic"),
    ("status", "Status"),
    ("book_title", "Book Title"),
    ("author", "Author"),
    ("edition", "Edition"),
    ("publisher", "Publisher"),
    ("year", "Year"),
    ("book_type", "Book Type"),
    ("chapter", "Chapter"),
    ("page_start", "Page Start"),
    ("page_end", "Page End"),
    ("coverage_percent", "Coverage %"),
    ("notes", "Notes"),
]


def _sanitize(value) -> object:
    if isinstance(value, str):
        return _ILLEGAL_XML_RE.sub("", value)
    return value


def _write_recommendations_sheet(wb: Workbook, rows: List[RecommendationRow]) -> None:
    ws = wb.active
    ws.title = "Recommendations"

    for col_idx, (_, header) in enumerate(_COLUMNS, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for row_idx, row in enumerate(rows, 2):
        for col_idx, (attr, _) in enumerate(_COLUMNS, 1):
            value = getattr(row, attr)
            ws.cell(row=row_idx, column=col_idx, value=_sanitize(value))

    widths = [14, 28, 8, 24, 30, 20, 12, 34, 22, 10, 18, 8, 12, 24, 10, 10, 11, 34]
    for col_idx, width in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def _write_summary_sheet(wb: Workbook, rows: List[RecommendationRow]) -> None:
    ws = wb.create_sheet("Summary")

    per_subject = defaultdict(lambda: {"found": 0, "not_found": 0, "name": ""})
    for row in rows:
        stats = per_subject[row.subject_code]
        stats["name"] = row.subject_name
        if row.status == "Found":
            stats["found"] += 1
        else:
            stats["not_found"] += 1

    headers = ["Subject Code", "Subject Name", "Found", "Not Found", "Total", "Coverage Rate"]
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT

    row_idx = 2
    total_found = total_not_found = 0
    for subject_code in sorted(per_subject):
        stats = per_subject[subject_code]
        total = stats["found"] + stats["not_found"]
        rate = f"{(stats['found'] / total * 100):.0f}%" if total else "0%"
        ws.cell(row=row_idx, column=1, value=subject_code)
        ws.cell(row=row_idx, column=2, value=_sanitize(stats["name"]))
        ws.cell(row=row_idx, column=3, value=stats["found"])
        ws.cell(row=row_idx, column=4, value=stats["not_found"])
        ws.cell(row=row_idx, column=5, value=total)
        ws.cell(row=row_idx, column=6, value=rate)
        total_found += stats["found"]
        total_not_found += stats["not_found"]
        row_idx += 1

    row_idx += 1
    ws.cell(row=row_idx, column=1, value="TOTAL").font = Font(bold=True)
    ws.cell(row=row_idx, column=3, value=total_found).font = Font(bold=True)
    ws.cell(row=row_idx, column=4, value=total_not_found).font = Font(bold=True)
    ws.cell(row=row_idx, column=5, value=total_found + total_not_found).font = Font(bold=True)

    for col_idx, width in enumerate([14, 30, 10, 12, 10, 14], 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = width


def export_to_excel(rows: List[RecommendationRow], output_path: str) -> None:
    wb = Workbook()
    _write_recommendations_sheet(wb, rows)
    _write_summary_sheet(wb, rows)
    wb.save(output_path)
