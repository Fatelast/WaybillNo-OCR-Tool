def test_main_window_imports_diagnostics_helpers():
    from waybill_ocr.ui import main_window

    assert main_window.inspect_environment is not None
    assert main_window.format_diagnostic_messages is not None
