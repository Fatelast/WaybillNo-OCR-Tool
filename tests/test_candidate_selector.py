from waybill_ocr.container_code.candidate_selector import CandidateText, select_best_candidate


def test_select_best_candidate_prefers_candidate_near_container_type_code():
    candidate = select_best_candidate(
        [
            CandidateText(text="噪声 HNKU6331795 随机文字", region_name="full"),
            CandidateText(text="GESU5903360P45G130", region_name="band-1"),
        ]
    )

    assert candidate == "GESU5903360"


def test_select_best_candidate_ignores_non_u_candidate():
    candidate = select_best_candidate(
        [
            CandidateText(text="YBXKIKOOMIJIP 5617782 J0YBEXK", region_name="full"),
            CandidateText(text="GESU5903360P45G130", region_name="band-1"),
        ]
    )

    assert candidate == "GESU5903360"



def test_select_best_candidate_uses_repaired_candidate_only_when_no_clear_candidate():
    candidate = select_best_candidate([CandidateText(text="OCR HINKU6331795", region_name="full")])

    assert candidate == "HNKU6331795"


def test_select_best_candidate_does_not_let_repaired_candidate_override_clear_candidate():
    candidate = select_best_candidate(
        [
            CandidateText(text="OCR HINKU6331795", region_name="priority-left-middle"),
            CandidateText(text="CONTAINER GESU5903360 45G1", region_name="priority-left-middle"),
        ]
    )

    assert candidate == "GESU5903360"

def test_score_review_candidate_prefers_repeated_repaired_code():
    from waybill_ocr.container_code.candidate_selector import score_review_candidates

    scores = score_review_candidates(
        base_text="UACUSSO2014 UACUS5O2014",
        enhanced_text="UACU5502014 45G1",
        candidates=["UACU5502014", "UACU5502015"],
        expected_codes=set(),
    )

    assert scores[0].code == "UACU5502014"
    assert scores[0].score > scores[1].score
    assert "enhanced_valid" in scores[0].reasons


def test_score_review_candidates_requires_clear_margin():
    from waybill_ocr.container_code.candidate_selector import ReviewCandidateScore, has_clear_review_winner

    scores = [
        ReviewCandidateScore(code="YYCU6003610", score=80, reasons=("enhanced_valid",)),
        ReviewCandidateScore(code="YYCU6002610", score=75, reasons=("base_valid",)),
    ]

    assert has_clear_review_winner(scores, min_score=80, min_margin=20) is None
