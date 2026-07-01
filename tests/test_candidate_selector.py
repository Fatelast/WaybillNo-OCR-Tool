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
