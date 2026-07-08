from waybill_ocr.container_code.decision import (
    build_conflict_review_note,
    has_candidate_conflict,
    review_code_for_invalid_candidate,
    review_code_from_text,
    suspicious_note,
)


def test_has_candidate_conflict_detects_same_owner_suspicious_text():
    assert has_candidate_conflict("TEMU7797904", "TEMU7797904 TEMU6779790")


def test_has_candidate_conflict_allows_single_clear_candidate():
    assert not has_candidate_conflict("HNKU6331795", "CONTAINER HNKU6331795 45G1")


def test_review_code_for_invalid_candidate_does_not_pick_ambiguous_single_digit_repair():
    assert review_code_for_invalid_candidate("YYCU6002610", "YYCU6002610") is None


def test_review_code_from_text_keeps_guess_repair_unique_only():
    assert review_code_from_text("OCR GESU59O3360") == "GESU5903360"


def test_suspicious_note_records_candidates_without_promoting_to_success():
    note = suspicious_note("OCR TEMUG7B1014")

    assert note is not None
    assert "疑似候选" in note or "可能修正" in note


def test_build_conflict_review_note_lists_review_candidates():
    note = build_conflict_review_note("TEMU7797904", "TEMU7797904 TEMU6779790")

    assert "候选冲突" in note
    assert "TEMU7797904" in note
