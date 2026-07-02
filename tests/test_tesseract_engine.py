import subprocess
from pathlib import Path

import pytest

from waybill_ocr.cancellation import ProcessingCancelled
from waybill_ocr.config import AppConfig
from waybill_ocr.ocr.tesseract_engine import TesseractEngine


class FakeProcess:
    def __init__(self, stdout: str = "HNKU6331795", stderr: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.returncode

    def communicate(self, timeout=None):
        return self.stdout, self.stderr

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


def test_tesseract_engine_recognizes_image_with_whitelist_config(tmp_path: Path):
    calls = []
    image_path = tmp_path / "waybill.png"
    image_path.write_bytes(b"fake")
    tesseract_cmd = tmp_path / "tools" / "tesseract" / "tesseract.exe"
    tessdata_dir = tesseract_cmd.parent / "tessdata"
    tessdata_dir.mkdir(parents=True)
    tesseract_cmd.write_bytes(b"exe")

    def fake_process_factory(command, **kwargs):
        calls.append((command, kwargs))
        return FakeProcess(stdout="HNKU6331795")

    engine = TesseractEngine(
        AppConfig(tesseract_cmd=tesseract_cmd),
        process_factory=fake_process_factory,
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
    assert calls[0][1]["stdout"] == subprocess.PIPE
    assert calls[0][1]["stderr"] == subprocess.PIPE
    assert calls[0][1]["text"] is True
    assert calls[0][1]["env"]["TESSDATA_PREFIX"] == str(tessdata_dir)
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        assert calls[0][1]["creationflags"] == subprocess.CREATE_NO_WINDOW


def test_tesseract_engine_reports_failed_command(tmp_path: Path):
    image_path = tmp_path / "waybill.png"
    image_path.write_bytes(b"fake")

    def fake_process_factory(_command, **_kwargs):
        return FakeProcess(stdout="", stderr="missing tessdata", returncode=1)

    engine = TesseractEngine(AppConfig(tesseract_cmd=Path("tesseract.exe")), process_factory=fake_process_factory)

    with pytest.raises(RuntimeError, match="Tesseract OCR 失败"):
        engine.recognize_image(image_path)


def test_tesseract_engine_terminates_process_when_cancelled(tmp_path: Path):
    import threading

    image_path = tmp_path / "waybill.png"
    image_path.write_bytes(b"fake")
    cancel_event = threading.Event()
    process = FakeProcess(stdout="", returncode=None)

    def fake_process_factory(_command, **_kwargs):
        cancel_event.set()
        return process

    engine = TesseractEngine(AppConfig(tesseract_cmd=Path("tesseract.exe")), process_factory=fake_process_factory)

    with pytest.raises(ProcessingCancelled):
        engine.recognize_image(image_path, cancel_event=cancel_event)

    assert process.terminated is True
