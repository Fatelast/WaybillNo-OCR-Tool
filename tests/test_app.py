from waybill_ocr.app import run


def test_run_placeholder_returns_none():
    assert run() is None
