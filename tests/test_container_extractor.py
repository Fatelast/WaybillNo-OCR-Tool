from waybill_ocr.container_code.extractor import extract_candidates


def test_extract_valid_container_code_from_text():
    text = "箱号 HNKU6331795 运单信息"
    assert extract_candidates(text) == ["HNKU6331795"]


def test_extract_ignores_invalid_check_digit():
    text = "错误箱号 HNKU6331794"
    assert extract_candidates(text) == []


def test_extract_removes_spaces_and_symbols():
    text = "HNKU 6331795"
    assert extract_candidates(text) == ["HNKU6331795"]


def test_extract_deduplicates_candidates():
    text = "HNKU6331795 HNKU6331795"
    assert extract_candidates(text) == ["HNKU6331795"]


def test_extract_ignores_non_u_category_identifier():
    text = "噪声 IJIP 5617782 真正箱号 GESU5903360P45G130"
    assert extract_candidates(text) == ["GESU5903360"]



def test_extract_repaired_candidate_removes_one_extra_owner_letter_when_valid():
    from waybill_ocr.container_code.extractor import extract_repaired_candidates

    assert extract_repaired_candidates("OCR HINKU6331795") == ["HNKU6331795"]


def test_extract_repaired_candidate_rejects_unvalidated_repairs():
    from waybill_ocr.container_code.extractor import extract_repaired_candidates

    assert extract_repaired_candidates("OCR HINKU6331794") == []


def test_extract_repaired_candidate_does_not_do_digit_letter_guessing():
    from waybill_ocr.container_code.extractor import extract_repaired_candidates

    assert extract_repaired_candidates("OCR HNKU633I795") == []

def test_extract_guess_repair_evidence_keeps_raw_and_repaired_code():
    from waybill_ocr.container_code.extractor import extract_guess_repair_evidence

    evidence = extract_guess_repair_evidence("OCR UACUSSO2014 UACUS5O2014")

    assert [(item.raw, item.repaired) for item in evidence] == [
        ("UACUSSO2014", "UACU5502014"),
        ("UACUS5O2014", "UACU5502014"),
    ]
    assert all(item.repaired_valid for item in evidence)
