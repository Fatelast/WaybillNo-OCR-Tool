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
        "备注",
        "相对路径",
    ]
    assert [cell.value for cell in sheet[2]] == [
        "HNKU6331795.jpg",
        "HNKU6331795",
        "正确识别",
        "OCR",
        None,
        123,
        None,
        None,
    ]


def test_write_results_highlights_non_success_rows(tmp_path: Path):
    success_source = tmp_path / "success.jpg"
    invalid_source = tmp_path / "invalid.jpg"
    unrecognized_source = tmp_path / "unrecognized.jpg"
    results = [
        RecognitionResult(
            source_path=success_source,
            original_name=success_source.name,
            status=RecognitionStatus.SUCCESS,
            container_code="HNKU6331795",
            source=RecognitionSource.OCR,
            failure_reason=None,
            ocr_text="HNKU6331795",
            elapsed_ms=1,
        ),
        RecognitionResult(
            source_path=invalid_source,
            original_name=invalid_source.name,
            status=RecognitionStatus.INVALID,
            container_code="HNKU6331794",
            source=RecognitionSource.OCR,
            failure_reason="INVALID_CHECK_DIGIT",
            ocr_text="HNKU6331794",
            elapsed_ms=2,
        ),
        RecognitionResult(
            source_path=unrecognized_source,
            original_name=unrecognized_source.name,
            status=RecognitionStatus.UNRECOGNIZED,
            container_code=None,
            source=None,
            failure_reason="NO_CONTAINER_CODE",
            ocr_text="",
            elapsed_ms=3,
        ),
    ]

    workbook_path = write_results(results, tmp_path)

    sheet = load_workbook(workbook_path).active
    assert all(cell.fill.fill_type is None for cell in sheet[2])
    for row_number in (3, 4):
        assert all(cell.fill.fill_type == "solid" for cell in sheet[row_number][:6])
        assert all(cell.fill.fgColor.rgb in {"00FFC7CE", "FFFFC7CE"} for cell in sheet[row_number][:6])


def test_write_results_outputs_review_note_and_repaired_source(tmp_path: Path):
    source = tmp_path / "waybill.jpg"
    result = RecognitionResult(
        source_path=source,
        original_name=source.name,
        status=RecognitionStatus.SUCCESS,
        container_code="HNKU6331795",
        source=RecognitionSource.OCR_REPAIRED,
        failure_reason=None,
        ocr_text="OCR HINKU6331795",
        elapsed_ms=123,
        review_note="OCR\u4fee\u6b63\u539f\u59cb\u7247\u6bb5: HINKU6331795",
    )

    workbook_path = write_results([result], tmp_path)

    sheet = load_workbook(workbook_path).active
    assert sheet["G1"].value == "\u5907\u6ce8"
    assert sheet["D2"].value == "OCR\u4fee\u6b63"
    assert sheet["G2"].value == "OCR\u4fee\u6b63\u539f\u59cb\u7247\u6bb5: HINKU6331795"


def test_write_results_outputs_enhanced_source_and_review_note(tmp_path: Path):
    source = tmp_path / "waybill.jpg"
    result = RecognitionResult(
        source_path=source,
        original_name=source.name,
        status=RecognitionStatus.SUCCESS,
        container_code="TEMU6779790",
        source=RecognitionSource.OCR_ENHANCED,
        failure_reason=None,
        ocr_text="TEMU6779790",
        elapsed_ms=123,
        review_note="\u589e\u5f3a\u8bc6\u522b\u8986\u76d6\u4f4e\u6e05\u6670\u5ea6\u5019\u9009: TEMU7797904 -> TEMU6779790",
    )

    workbook_path = write_results([result], tmp_path)

    sheet = load_workbook(workbook_path).active
    assert sheet["D2"].value == "OCR\u589e\u5f3a"
    assert sheet["G2"].value == "\u589e\u5f3a\u8bc6\u522b\u8986\u76d6\u4f4e\u6e05\u6670\u5ea6\u5019\u9009: TEMU7797904 -> TEMU6779790"


def test_write_results_sets_original_name_column_width(tmp_path: Path):
    source = tmp_path / "long-original-file-name.pdf"
    result = RecognitionResult(
        source_path=source,
        original_name=source.name,
        status=RecognitionStatus.SUCCESS,
        container_code="HNKU6331795",
        source=RecognitionSource.OCR,
        failure_reason=None,
        ocr_text="HNKU6331795",
        elapsed_ms=1,
    )

    workbook_path = write_results([result], tmp_path)

    sheet = load_workbook(workbook_path).active
    assert sheet.column_dimensions["A"].width >= 48


def test_write_results_adds_comparison_sheet(tmp_path: Path):
    from waybill_ocr.container_code.expected_codes import ComparisonReport

    source = tmp_path / "waybill.pdf"
    result = RecognitionResult(
        source_path=source,
        original_name=source.name,
        status=RecognitionStatus.SUCCESS,
        container_code="HNKU6331795",
        source=RecognitionSource.OCR,
        failure_reason=None,
        ocr_text="HNKU6331795",
        elapsed_ms=1,
    )
    report = ComparisonReport(
        expected_codes=["HNKU6331795", "GESU5903360"],
        recognized_codes=["HNKU6331795", "MSKU1234565"],
        matched_codes=["HNKU6331795"],
        missing_codes=["GESU5903360"],
        extra_codes=["MSKU1234565"],
        invalid_expected_entries=["BAD-CODE"],
    )

    workbook_path = write_results([result], tmp_path, comparison_report=report)

    workbook = load_workbook(workbook_path)
    sheet = workbook["\u7bb1\u53f7\u6bd4\u5bf9"]
    assert [cell.value for cell in sheet[1]] == [
        "\u5df2\u5339\u914d\u7bb1\u53f7",
        "\u7f3a\u5931\u7bb1\u53f7",
        "\u591a\u4f59\u8bc6\u522b\u7bb1\u53f7",
        "\u683c\u5f0f\u65e0\u6548",
    ]
    assert [cell.value for cell in sheet[2]] == ["HNKU6331795", "GESU5903360", "MSKU1234565", "BAD-CODE"]


def test_write_results_omits_evidence_path_column(tmp_path: Path):
    source = tmp_path / "waybill.jpg"
    evidence = tmp_path / "识别证据" / "waybill.png"
    result = RecognitionResult(
        source_path=source,
        original_name=source.name,
        status=RecognitionStatus.UNRECOGNIZED,
        container_code=None,
        source=None,
        failure_reason="NO_CONTAINER_CANDIDATE",
        ocr_text="",
        elapsed_ms=1,
        evidence_path=evidence,
        relative_name="nested/waybill.jpg",
    )

    workbook_path = write_results([result], tmp_path)

    sheet = load_workbook(workbook_path).active
    headers = [cell.value for cell in sheet[1]]
    assert "证据截图" not in headers
    assert sheet["H1"].value == "相对路径"
    assert sheet["H2"].value == "nested/waybill.jpg"


def test_write_results_outputs_relative_name_column(tmp_path: Path):
    source = tmp_path / "nested" / "waybill.pdf"
    result = RecognitionResult(
        source_path=source,
        original_name=source.name,
        relative_name="nested/waybill.pdf",
        status=RecognitionStatus.SUCCESS,
        container_code="HNKU6331795",
        source=RecognitionSource.OCR,
        failure_reason=None,
        ocr_text="HNKU6331795",
        elapsed_ms=1,
    )

    workbook_path = write_results([result], tmp_path)

    sheet = load_workbook(workbook_path).active
    assert sheet["H1"].value == "相对路径"
    assert sheet["H2"].value == "nested/waybill.pdf"
    assert sheet["A1"].value == "原始文件名"
    assert sheet["A2"].value == "waybill.pdf"
