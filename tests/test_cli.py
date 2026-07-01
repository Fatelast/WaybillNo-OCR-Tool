from io import StringIO
from pathlib import Path

import waybill_ocr.cli as cli_module
import waybill_ocr.app as app_module
from waybill_ocr.config import AppConfig
from waybill_ocr.diagnostics import DiagnosticResult


class FakeMainWindow:
    ran = False

    def run(self) -> None:
        self.ran = True


def test_run_starts_main_window_without_arguments(monkeypatch):
    window = FakeMainWindow()
    monkeypatch.setattr(app_module, "MainWindow", lambda: window)

    result = app_module.run([])

    assert result is None
    assert window.ran is True


def test_run_delegates_arguments_to_cli(monkeypatch):
    calls = []
    monkeypatch.setattr(app_module, "cli_main", lambda argv: calls.append(argv) or 3)

    assert app_module.run(["diagnose"]) == 3
    assert calls == [["diagnose"]]


def test_cli_diagnose_prints_messages_and_returns_one_when_missing(monkeypatch):
    stdout = StringIO()
    monkeypatch.setattr(cli_module, "default_config", lambda: AppConfig())
    monkeypatch.setattr(
        cli_module,
        "inspect_environment",
        lambda _config: [DiagnosticResult("Tesseract", False, "未找到 Tesseract")],
    )

    exit_code = cli_module.main(["diagnose"], stdout=stdout)

    assert exit_code == 1
    assert stdout.getvalue() == "[缺失] 未找到 Tesseract\n"


def test_cli_batch_processes_directory(monkeypatch, tmp_path: Path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    calls = []
    stdout = StringIO()

    monkeypatch.setattr(cli_module, "default_config", lambda: AppConfig())
    monkeypatch.setattr(cli_module, "TesseractEngine", lambda config: ("engine", config))
    monkeypatch.setattr(
        cli_module,
        "process_directory",
        lambda **kwargs: calls.append(kwargs) or [],
    )

    exit_code = cli_module.main(
        ["batch", "--input", str(input_dir), "--output", str(output_dir)],
        stdout=stdout,
    )

    assert exit_code == 0
    assert calls[0]["input_dir"] == input_dir
    assert calls[0]["output_dir"] == output_dir
    assert calls[0]["ocr_engine"] == ("engine", AppConfig())
    calls[0]["on_progress"]("处理完成")
    assert stdout.getvalue() == "处理完成\n"
