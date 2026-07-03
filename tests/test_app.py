from pathlib import Path

def test_main_window_imports_diagnostics_helpers():
    from waybill_ocr.ui import main_window

    assert main_window.inspect_environment is not None
    assert main_window.format_diagnostic_messages is not None



def test_main_window_layout_keeps_task_area_compact_for_log_visibility():
    source = (Path(__file__).resolve().parents[1] / "src" / "waybill_ocr" / "ui" / "main_window.py").read_text(encoding="utf-8")

    assert "progress_cell" in source
    assert "height=24" in source
    assert "\u9009\u62e9\u6587\u4ef6\uff0c\u4e0d\u662f\u6587\u4ef6\u5939" not in source
