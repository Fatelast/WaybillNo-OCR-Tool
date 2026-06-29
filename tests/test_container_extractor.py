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
