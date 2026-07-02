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
