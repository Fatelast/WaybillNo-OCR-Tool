from waybill_ocr.container_code.candidate_selector import CandidateText

from waybill_ocr.container_code.decision import (
    build_conflict_review_note,
    assess_candidate_conflict,
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


def test_evidence_assessment_allows_repeated_candidate_with_single_low_score_noise():
    texts = [
        CandidateText("HNKU6331795", "full"),
        CandidateText("CONTAINER GESU5903360 45G1", "priority-left-middle"),
        CandidateText("GESU5903360 45G1", "priority-full-middle"),
    ]

    assessment = assess_candidate_conflict("GESU5903360", texts)

    assert assessment.selected_support_count == 2
    assert assessment.competing_valid_codes == ("HNKU6331795",)
    assert assessment.requires_cross_validation is False
    assert assessment.has_strong_conflict is False


def test_evidence_assessment_cross_validates_single_candidate_with_same_prefix_suspicion():
    texts = [
        CandidateText("TEMU7797904", "full"),
        CandidateText("TEMU67I9790", "priority-left-middle"),
    ]

    assessment = assess_candidate_conflict("TEMU7797904", texts)

    assert assessment.selected_support_count == 1
    assert assessment.requires_cross_validation is True
    assert assessment.has_strong_conflict is True


def test_evidence_assessment_keeps_repeated_valid_competitor_as_strong_conflict():
    texts = [
        CandidateText("GESU5903360", "priority-left-middle"),
        CandidateText("GESU5903360", "priority-full-middle"),
        CandidateText("HNKU6331795", "cell-r1-c1"),
        CandidateText("HNKU6331795", "cell-r1-c2"),
    ]

    assessment = assess_candidate_conflict("GESU5903360", texts)

    assert assessment.requires_cross_validation is True
    assert assessment.has_strong_conflict is True


def test_evidence_assessment_collapses_duplicate_variants_by_region_key():
    texts = [
        CandidateText("GESU5903360", "enhanced-400dpi-left-middle-plain"),
        CandidateText("GESU5903360", "enhanced-400dpi-left-middle-x2sharp"),
        CandidateText("GESU59O3360", "enhanced-base-full-middle-plain"),
        CandidateText("GESU59O3360", "enhanced-base-full-middle-x2sharp"),
    ]

    assessment = assess_candidate_conflict(
        "GESU5903360",
        texts,
        region_key=lambda name: name.rsplit("-", 1)[0],
    )

    assert assessment.selected_support_count == 1
    assert assessment.repeated_suspicious_candidates == ()
