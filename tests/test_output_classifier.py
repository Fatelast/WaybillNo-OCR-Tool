from pathlib import Path

from waybill_ocr.models import RecognitionResult, RecognitionSource, RecognitionStatus
from waybill_ocr.output.classifier import copy_result_file


def test_copy_result_file_to_success_dir_with_container_code_name(tmp_path: Path):
    source = tmp_path / "waybill.jpg"
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

    assert copied_path == output_dir / "正确识别" / "HNKU6331795.jpg"
    assert copied_path.read_bytes() == b"fake"


def test_copy_result_file_keeps_original_name_for_unrecognized_file(tmp_path: Path):
    source = tmp_path / "waybill.jpg"
    source.write_bytes(b"fake")
    output_dir = tmp_path / "output"
    result = RecognitionResult(
        source_path=source,
        original_name=source.name,
        status=RecognitionStatus.UNRECOGNIZED,
        container_code=None,
        source=None,
        failure_reason="NO_CONTAINER_CANDIDATE",
        ocr_text="",
        elapsed_ms=10,
    )

    copied_path = copy_result_file(result, output_dir)

    assert copied_path == output_dir / "未识别" / source.name
    assert copied_path.read_bytes() == b"fake"


def test_copy_result_file_uses_review_code_for_unrecognized_file(tmp_path: Path):
    source = tmp_path / "waybill.jpg"
    source.write_bytes(b"fake")
    output_dir = tmp_path / "output"
    result = RecognitionResult(
        source_path=source,
        original_name=source.name,
        status=RecognitionStatus.UNRECOGNIZED,
        container_code=None,
        source=None,
        failure_reason="NO_CONTAINER_CANDIDATE",
        ocr_text="",
        elapsed_ms=10,
        review_code="UACU5502014",
    )

    copied_path = copy_result_file(result, output_dir)

    assert copied_path == output_dir / "未识别" / "UACU5502014-待确认.jpg"
    assert copied_path.read_bytes() == b"fake"


def test_copy_result_file_uses_review_code_for_invalid_file(tmp_path: Path):
    source = tmp_path / "waybill.pdf"
    source.write_bytes(b"fake")
    output_dir = tmp_path / "output"
    result = RecognitionResult(
        source_path=source,
        original_name=source.name,
        status=RecognitionStatus.INVALID,
        container_code="YYCU6002610",
        source=RecognitionSource.OCR,
        failure_reason="INVALID_CHECK_DIGIT",
        ocr_text="YYCU6002610",
        elapsed_ms=10,
        review_code="YYCU6003610",
    )

    copied_path = copy_result_file(result, output_dir)

    assert copied_path == output_dir / "箱号错误" / "YYCU6003610-待确认.pdf"
    assert copied_path.read_bytes() == b"fake"


def test_copy_result_file_keeps_existing_file_when_names_collide(tmp_path: Path):
    first = tmp_path / "first" / "waybill.jpg"
    second = tmp_path / "second" / "waybill.jpg"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    output_dir = tmp_path / "output"

    first_result = RecognitionResult(
        source_path=first,
        original_name=first.name,
        status=RecognitionStatus.SUCCESS,
        container_code="HNKU6331795",
        source=RecognitionSource.OCR,
        failure_reason=None,
        ocr_text="HNKU6331795",
        elapsed_ms=10,
    )
    second_result = RecognitionResult(
        source_path=second,
        original_name=second.name,
        status=RecognitionStatus.SUCCESS,
        container_code="HNKU6331795",
        source=RecognitionSource.OCR,
        failure_reason=None,
        ocr_text="HNKU6331795",
        elapsed_ms=10,
    )

    first_copy = copy_result_file(first_result, output_dir)
    second_copy = copy_result_file(second_result, output_dir)

    assert first_copy.name == "HNKU6331795.jpg"
    assert second_copy.name == "HNKU6331795-1.jpg"
    assert first_copy.read_bytes() == b"first"
    assert second_copy.read_bytes() == b"second"
