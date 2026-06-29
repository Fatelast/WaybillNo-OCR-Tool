from pathlib import Path

from waybill_ocr.models import RecognitionResult, RecognitionSource, RecognitionStatus
from waybill_ocr.output.classifier import copy_result_file


def test_copy_result_file_to_success_dir(tmp_path: Path):
    source = tmp_path / "HNKU6331795.jpg"
    source.write_bytes(b"fake")
    output_dir = tmp_path / "output"
    result = RecognitionResult(
        source_path=source,
        original_name=source.name,
        status=RecognitionStatus.SUCCESS,
        container_code="HNKU6331795",
        source=RecognitionSource.OCR,
        failure_reason=None,
        ocr_text="HNKU6331795",
        elapsed_ms=10,
    )

    copied_path = copy_result_file(result, output_dir)

    assert copied_path == output_dir / "正确识别" / source.name
    assert copied_path.read_bytes() == b"fake"
