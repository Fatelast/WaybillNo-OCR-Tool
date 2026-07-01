import waybill_ocr.app as app_module


class FakeMainWindow:
    ran = False

    def run(self) -> None:
        self.ran = True


def test_run_starts_main_window(monkeypatch):
    window = FakeMainWindow()
    monkeypatch.setattr(app_module, "MainWindow", lambda: window)

    app_module.run()

    assert window.ran is True


def test_main_window_imports_diagnostics_helpers():
    from waybill_ocr.ui import main_window

    assert main_window.inspect_environment is not None
    assert main_window.format_diagnostic_messages is not None
