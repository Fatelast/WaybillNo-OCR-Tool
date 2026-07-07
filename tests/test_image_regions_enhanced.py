def test_enhanced_regions_are_limited_in_balanced_mode():
    from waybill_ocr.image_regions import _enhanced_regions

    regions = _enhanced_regions(1000, 1000, mode="balanced")

    assert [name for name, _box in regions] == ["full-middle", "left-middle", "left-lower-middle"]


def test_enhanced_regions_include_extra_lines_in_stable_mode():
    from waybill_ocr.image_regions import _enhanced_regions

    regions = _enhanced_regions(1000, 1000, mode="stable")
    names = [name for name, _box in regions]

    assert "full-middle" in names
    assert "full-upper-middle" in names
    assert "left-wide-middle" in names
    assert len(names) > 3