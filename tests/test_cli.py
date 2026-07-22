from io import StringIO
from pathlib import Path

from types import SimpleNamespace
import waybill_ocr.app as app_module
import waybill_ocr.cli as cli_module
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
    monkeypatch.setattr(cli_module, "default_config", lambda **kwargs: AppConfig(**kwargs))
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
    work_dir = tmp_path / "work"
    input_dir.mkdir()
    calls = []
    stdout = StringIO()

    monkeypatch.setattr(cli_module, "resolve_default_work_dir", lambda: work_dir)
    monkeypatch.setattr(cli_module, "default_config", lambda **kwargs: AppConfig(**kwargs))
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
    assert calls[0]["ocr_engine"] == ("engine", AppConfig(work_dir=work_dir))
    calls[0]["on_progress"]("处理完成")
    assert stdout.getvalue() == "处理完成\n"


def test_cli_verify_samples_prints_report_and_returns_status(monkeypatch, tmp_path: Path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "actual"
    work_dir = tmp_path / "work"
    baseline_path = tmp_path / "baseline.csv"
    input_dir.mkdir()
    baseline_path.write_text("filename,expected_code,should_recognize,quality_tag,notes\n", encoding="utf-8")
    stdout = StringIO()
    calls = []

    class FakeReport:
        ok = False
        messages = ["样本验收失败: 0/1", "waybill.png: 未在处理结果中找到该样本"]

    monkeypatch.setattr(cli_module, "resolve_default_work_dir", lambda: work_dir)
    monkeypatch.setattr(cli_module, "default_config", lambda **kwargs: AppConfig(**kwargs))
    monkeypatch.setattr(cli_module, "TesseractEngine", lambda config: ("engine", config))
    monkeypatch.setattr(
        cli_module,
        "verify_samples",
        lambda **kwargs: calls.append(kwargs) or FakeReport(),
    )

    exit_code = cli_module.main(
        [
            "verify-samples",
            "--input",
            str(input_dir),
            "--output",
            str(output_dir),
            "--baseline",
            str(baseline_path),
        ],
        stdout=stdout,
    )

    assert exit_code == 1
    assert calls[0]["input_dir"] == input_dir
    assert calls[0]["output_dir"] == output_dir
    assert calls[0]["baseline_path"] == baseline_path
    assert calls[0]["ocr_engine"] == ("engine", AppConfig(work_dir=work_dir))
    assert stdout.getvalue() == "样本验收失败: 0/1\nwaybill.png: 未在处理结果中找到该样本\n"


def test_cli_batch_accepts_expected_code_list(monkeypatch, tmp_path: Path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    work_dir = tmp_path / "work"
    expected_path = tmp_path / "expected.txt"
    input_dir.mkdir()
    expected_path.write_text("HNKU6331795\n", encoding="utf-8")
    calls = []
    stdout = StringIO()

    monkeypatch.setattr(cli_module, "resolve_default_work_dir", lambda: work_dir)
    monkeypatch.setattr(cli_module, "default_config", lambda **kwargs: AppConfig(**kwargs))
    monkeypatch.setattr(cli_module, "TesseractEngine", lambda config: ("engine", config))
    monkeypatch.setattr(cli_module, "read_expected_codes", lambda path: ["HNKU6331795"])
    monkeypatch.setattr(cli_module, "process_directory", lambda **kwargs: calls.append(kwargs) or [])

    exit_code = cli_module.main(
        ["batch", "--input", str(input_dir), "--output", str(output_dir), "--expected", str(expected_path)],
        stdout=stdout,
    )

    assert exit_code == 0
    assert calls[0]["expected_codes"] == ["HNKU6331795"]



def test_cli_verify_samples_defaults_to_cases_directory():
    assert cli_module.DEFAULT_SAMPLE_INPUT == Path("samples/cases")


def test_cli_prepare_sample_baseline_generates_draft(monkeypatch, tmp_path: Path):
    input_dir = tmp_path / "cases"
    expected_path = tmp_path / "expected.txt"
    output_dir = tmp_path / "actual"
    draft_path = tmp_path / "draft.csv"
    work_dir = tmp_path / "work"
    input_dir.mkdir()
    expected_path.write_text("HNKU6331795\n", encoding="utf-8")
    stdout = StringIO()
    calls = []

    report = SimpleNamespace(total=3, suggested=2, draft_path=draft_path)

    monkeypatch.setattr(cli_module, "resolve_default_work_dir", lambda: work_dir)
    monkeypatch.setattr(cli_module, "default_config", lambda **kwargs: AppConfig(**kwargs))
    monkeypatch.setattr(cli_module, "TesseractEngine", lambda config: ("engine", config))
    monkeypatch.setattr(
        cli_module,
        "prepare_sample_baseline",
        lambda **kwargs: calls.append(kwargs) or report,
    )

    exit_code = cli_module.main(
        [
            "prepare-sample-baseline",
            "--input",
            str(input_dir),
            "--expected",
            str(expected_path),
            "--output",
            str(output_dir),
            "--draft",
            str(draft_path),
        ],
        stdout=stdout,
    )

    assert exit_code == 0
    assert calls[0]["input_dir"] == input_dir
    assert calls[0]["expected_path"] == expected_path
    assert calls[0]["draft_path"] == draft_path
    assert "\u6837\u672c\u57fa\u7ebf\u8349\u7a3f\u5df2\u751f\u6210" in stdout.getvalue()


def test_cli_import_sample_baseline_uses_confirmed_draft(monkeypatch, tmp_path: Path):
    input_dir = tmp_path / "cases"
    draft_path = tmp_path / "draft.csv"
    baseline_path = tmp_path / "baseline.local.csv"
    input_dir.mkdir()
    draft_path.write_text("confirmed\ntrue\n", encoding="utf-8")
    stdout = StringIO()
    calls = []

    report = SimpleNamespace(imported=1, total=4, baseline_path=baseline_path)

    monkeypatch.setattr(
        cli_module,
        "import_sample_baseline",
        lambda **kwargs: calls.append(kwargs) or report,
    )

    exit_code = cli_module.main(
        [
            "import-sample-baseline",
            "--input",
            str(input_dir),
            "--draft",
            str(draft_path),
            "--baseline",
            str(baseline_path),
        ],
        stdout=stdout,
    )

    assert exit_code == 0
    assert calls[0]["baseline_path"] == baseline_path
    assert "\u672c\u6b21\u5bfc\u5165 1 \u6761" in stdout.getvalue()
