from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import PatternFill

from waybill_ocr.constants import RESULT_WORKBOOK_NAME
from waybill_ocr.container_code.expected_codes import ComparisonReport
from waybill_ocr.models import RecognitionResult, RecognitionStatus


HEADERS = [
    "原始文件名",
    "识别箱号",
    "识别状态",
    "识别来源",
    "失败原因",
    "处理耗时ms",
    "备注",
    "相对路径",
]
ERROR_ROW_FILL = PatternFill(fill_type="solid", fgColor="FFC7CE")
COLUMN_WIDTHS = {"A": 52, "B": 18, "C": 14, "D": 14, "E": 28, "F": 14, "G": 42, "H": 36}
COMPARISON_HEADERS = ["已匹配箱号", "缺失箱号", "多余识别箱号", "格式无效"]


def write_results(
    results: list[RecognitionResult],
    output_dir: Path,
    workbook_path: Path | None = None,
    comparison_report: ComparisonReport | None = None,
) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "识别结果"
    sheet.append(HEADERS)
    _apply_result_sheet_widths(sheet)

    for result in results:
        sheet.append(
            [
                result.original_name,
                result.container_code or "",
                result.status.value,
                result.source.value if result.source else "",
                result.failure_reason or "",
                result.elapsed_ms,
                result.review_note or "",
                result.relative_name or "",
            ]
        )
        if result.status is not RecognitionStatus.SUCCESS:
            _highlight_row(sheet[sheet.max_row][: len(HEADERS)])

    if comparison_report is not None:
        _append_comparison_sheet(workbook, comparison_report)

    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = workbook_path or output_dir / RESULT_WORKBOOK_NAME
    workbook.save(target_path)
    return target_path


def _highlight_row(cells) -> None:
    for cell in cells:
        cell.fill = ERROR_ROW_FILL


def _apply_result_sheet_widths(sheet) -> None:
    for column, width in COLUMN_WIDTHS.items():
        sheet.column_dimensions[column].width = width


def _append_comparison_sheet(workbook, report: ComparisonReport) -> None:
    sheet = workbook.create_sheet("箱号比对")
    sheet.append(COMPARISON_HEADERS)
    sheet.column_dimensions["A"].width = 18
    sheet.column_dimensions["B"].width = 18
    sheet.column_dimensions["C"].width = 18
    sheet.column_dimensions["D"].width = 28
    row_count = max(
        len(report.matched_codes),
        len(report.missing_codes),
        len(report.extra_codes),
        len(report.invalid_expected_entries),
    )
    for index in range(row_count):
        sheet.append(
            [
                _item_at(report.matched_codes, index),
                _item_at(report.missing_codes, index),
                _item_at(report.extra_codes, index),
                _item_at(report.invalid_expected_entries, index),
            ]
        )


def _item_at(items: list[str], index: int) -> str:
    if index >= len(items):
        return ""
    return items[index]
