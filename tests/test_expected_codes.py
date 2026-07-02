from pathlib import Path

from waybill_ocr.container_code.expected_codes import compare_expected_codes, read_expected_codes
from waybill_ocr.models import RecognitionResult, RecognitionSource, RecognitionStatus


def _result(code: str | None) -> RecognitionResult:
    return RecognitionResult(
        source_path=Path("sample.pdf"),
        original_name="sample.pdf",
        status=RecognitionStatus.SUCCESS if code else RecognitionStatus.UNRECOGNIZED,
        container_code=code,
        source=RecognitionSource.OCR if code else None,
        failure_reason=None if code else "NO_CONTAINER_CANDIDATE",
        ocr_text=code or "",
        elapsed_ms=1,
    )


def test_read_expected_codes_extracts_unique_valid_codes_from_text(tmp_path: Path):
    list_path = tmp_path / "expected.txt"
    list_path.write_text("HNKU6331795\ninvalid\nHNKU6331795\nGESU5903360 45G1\n", encoding="utf-8")

    assert read_expected_codes(list_path) == ["HNKU6331795", "GESU5903360"]


def test_compare_expected_codes_reports_matched_missing_and_extra():
    report = compare_expected_codes(
        expected_codes=["HNKU6331795", "GESU5903360"],
        results=[_result("HNKU6331795"), _result("MSKU1234565"), _result(None)],
    )

    assert report.matched_codes == ["HNKU6331795"]
    assert report.missing_codes == ["GESU5903360"]
    assert report.extra_codes == ["MSKU1234565"]
