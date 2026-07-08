from pathlib import Path

from waybill_ocr.models import RecognitionResult, RecognitionSource, RecognitionStatus


def _result(
    *,
    status: RecognitionStatus = RecognitionStatus.UNRECOGNIZED,
    container_code: str | None = None,
    ocr_text: str = "",
    review_code: str | None = None,
    review_note: str | None = None,
) -> RecognitionResult:
    source = Path("waybill.pdf")
    return RecognitionResult(
        source_path=source,
        original_name=source.name,
        status=status,
        container_code=container_code,
        source=RecognitionSource.OCR if container_code else None,
        failure_reason="NO_CONTAINER_CANDIDATE" if status is RecognitionStatus.UNRECOGNIZED else "INVALID_CHECK_DIGIT",
        ocr_text=ocr_text,
        elapsed_ms=1,
        review_code=review_code,
        review_note=review_note,
    )


def test_expected_list_sets_review_code_from_unique_matching_candidate():
    from waybill_ocr.container_code.review_candidates import apply_expected_review_code

    result = _result(ocr_text="OCR HNKU6331795 GESU5903360")

    updated = apply_expected_review_code(result, ["GESU5903360"])

    assert updated.status is RecognitionStatus.UNRECOGNIZED
    assert updated.review_code == "GESU5903360"
    assert "预期清单唯一匹配待确认: GESU5903360" in updated.review_note


def test_expected_list_sets_review_code_from_invalid_single_digit_repair():
    from waybill_ocr.container_code.review_candidates import apply_expected_review_code

    result = _result(
        status=RecognitionStatus.INVALID,
        container_code="YYCU6002610",
        ocr_text="OCR YYCU6002610",
    )

    updated = apply_expected_review_code(result, ["YYCU6003610"])

    assert updated.status is RecognitionStatus.INVALID
    assert updated.container_code == "YYCU6002610"
    assert updated.review_code == "YYCU6003610"


def test_expected_list_does_not_override_existing_review_code():
    from waybill_ocr.container_code.review_candidates import apply_expected_review_code

    result = _result(ocr_text="OCR HNKU6331795", review_code="UACU5502014")

    updated = apply_expected_review_code(result, ["HNKU6331795"])

    assert updated is result
    assert updated.review_code == "UACU5502014"


def test_expected_list_does_not_choose_when_multiple_candidates_match():
    from waybill_ocr.container_code.review_candidates import apply_expected_review_code

    result = _result(ocr_text="OCR HNKU6331795 GESU5903360")

    updated = apply_expected_review_code(result, ["HNKU6331795", "GESU5903360"])

    assert updated.review_code is None
    assert "多个预期清单候选命中" in updated.review_note
    assert "HNKU6331795" in updated.review_note
    assert "GESU5903360" in updated.review_note


def test_expected_list_leaves_result_unchanged_without_matching_candidate():
    from waybill_ocr.container_code.review_candidates import apply_expected_review_code

    result = _result(ocr_text="OCR HNKU6331795")

    updated = apply_expected_review_code(result, ["GESU5903360"])

    assert updated is result
    assert updated.review_code is None