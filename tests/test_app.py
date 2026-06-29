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
