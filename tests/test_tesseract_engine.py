import subprocess
from pathlib import Path

import pytest

from waybill_ocr.config import AppConfig
from waybill_ocr.ocr.tesseract_engine import TesseractEngine


class FakeCompletedProcess:
    def __init__(self, stdout: str, stderr: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def test_tesseract_engine_recognizes_image_with_whitelist_config(tmp_path: Path):
    calls = []
    image_path = tmp_path / "waybill.png"
    image_path.write_bytes(b"fake")
    tesseract_cmd = tmp_path / "tools" / "tesseract" / "tesseract.exe"
    tessdata_dir = tesseract_cmd.parent / "tessdata"
    tessdata_dir.mkdir(parents=True)
    tesseract_cmd.write_bytes(b"exe")

    def fake_runner(command, **kwargs):
        calls.append((command, kwargs))
        return FakeCompletedProcess(stdout="HNKU6331795")

    engine = TesseractEngine(
        AppConfig(tesseract_cmd=tesseract_cmd),
        command_runner=fake_runner,
    )

    result = engine.recognize_image(image_path)

    assert result.text == "HNKU6331795"
    assert result.engine_name == "tesseract"
    assert calls[0][0] == [
        str(tesseract_cmd),
        str(image_path),
        "stdout",
        "--tessdata-dir",
        str(tessdata_dir),
        "-l",
        "eng",
        "--psm",
        "6",
        "-c",
        "tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    ]
    assert calls[0][1]["capture_output"] is True
    assert calls[0][1]["text"] is True
    assert calls[0][1]["timeout"] == 60
    assert calls[0][1]["env"]["TESSDATA_PREFIX"] == str(tessdata_dir)
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        assert calls[0][1]["creationflags"] == subprocess.CREATE_NO_WINDOW


def test_tesseract_engine_reports_failed_command(tmp_path: Path):
    image_path = tmp_path / "waybill.png"
    image_path.write_bytes(b"fake")

    def fake_runner(_command, **_kwargs):
        return FakeCompletedProcess(stdout="", stderr="missing tessdata", returncode=1)

    engine = TesseractEngine(AppConfig(tesseract_cmd=Path("tesseract.exe")), command_runner=fake_runner)

    with pytest.raises(RuntimeError, match="Tesseract OCR 失败"):
        engine.recognize_image(image_path)


def test_tesseract_engine_hides_subprocess_window_on_windows(tmp_path: Path):
    calls = []
    image_path = tmp_path / "waybill.png"
    image_path.write_bytes(b"fake")

    def fake_runner(_command, **kwargs):
        calls.append(kwargs)
        return FakeCompletedProcess(stdout="HNKU6331795")

    engine = TesseractEngine(AppConfig(tesseract_cmd=Path("tesseract.exe")), command_runner=fake_runner)

    engine.recognize_image(image_path)

    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        assert calls[0]["creationflags"] == subprocess.CREATE_NO_WINDOW