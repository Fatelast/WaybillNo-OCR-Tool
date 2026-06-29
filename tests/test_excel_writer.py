from pathlib import Path

from openpyxl import load_workbook

from waybill_ocr.constants import RESULT_WORKBOOK_NAME
from waybill_ocr.models import RecognitionResult, RecognitionSource, RecognitionStatus
from waybill_ocr.output.excel_writer import write_results


def test_write_results_creates_workbook_with_recognition_rows(tmp_path: Path):
    source = tmp_path / "HNKU6331795.jpg"
    result = RecognitionResult(
        source_path=source,
        original_name=source.name,
        status=RecognitionStatus.SUCCESS,
        container_code="HNKU6331795",
        source=RecognitionSource.OCR,
        failure_reason=None,
        ocr_text="HNKU6331795",
        elapsed_ms=123,
    )

    workbook_path = write_results([result], tmp_path)

    assert workbook_path == tmp_path / RESULT_WORKBOOK_NAME
    workbook = load_workbook(workbook_path)
    sheet = workbook.active
    assert sheet.title == "识别结果"
    assert [cell.value for cell in sheet[1]] == [
        "原始文件名",
        "识别箱号",
        "识别状态",
        "识别来源",
        "失败原因",
        "处理耗时ms",
    ]
    assert [cell.value for cell in sheet[2]] == [
        "HNKU6331795.jpg",
        "HNKU6331795",
        "正确识别",
        "OCR",
        None,
        123,
    ]
