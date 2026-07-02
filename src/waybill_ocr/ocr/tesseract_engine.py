import os
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from waybill_ocr.config import AppConfig
from waybill_ocr.ocr.base import OcrResult


TESSERACT_ARGS = [
    "-l",
    "eng",
    "--psm",
    "6",
    "-c",
    "tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
]
CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


class TesseractEngine:
    def __init__(self, config: AppConfig, command_runner: CommandRunner | None = None) -> None:
        self.config = config
        self._command_runner = command_runner or subprocess.run

    def recognize_image(self, image_path: Path) -> OcrResult:
        started = time.perf_counter()
        text = ""
        last_error = ""

        for _ in range(self.config.ocr_retries + 1):
            completed = self._command_runner(
                self._build_command(image_path),
                **self._subprocess_options(),
            )
            text = completed.stdout or ""
            last_error = completed.stderr or ""
            if completed.returncode == 0 and text.strip():
                break

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if not text.strip():
            detail = last_error.strip() or "未输出 OCR 文本"
            raise RuntimeError(f"Tesseract OCR 失败: {detail}")

        return OcrResult(text=text, engine_name="tesseract", elapsed_ms=elapsed_ms)

    def _build_command(self, image_path: Path) -> list[str]:
        executable = self.config.tesseract_cmd or Path("tesseract")
        return [str(executable), str(image_path), "stdout", *self._tessdata_args(), *TESSERACT_ARGS]

    def _subprocess_options(self) -> dict:
        options = {"capture_output": True, "text": True, "timeout": 60, "env": self._subprocess_env()}
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            options["creationflags"] = subprocess.CREATE_NO_WINDOW
        return options

    def _subprocess_env(self) -> dict[str, str]:
        env = os.environ.copy()
        tessdata_dir = self._tessdata_dir()
        if tessdata_dir:
            env["TESSDATA_PREFIX"] = str(tessdata_dir)
        return env

    def _tessdata_args(self) -> list[str]:
        tessdata_dir = self._tessdata_dir()
        if not tessdata_dir:
            return []
        return ["--tessdata-dir", str(tessdata_dir)]

    def _tessdata_dir(self) -> Path | None:
        if not self.config.tesseract_cmd:
            return None

        tessdata_dir = self.config.tesseract_cmd.parent / "tessdata"
        if tessdata_dir.exists():
            return tessdata_dir

        return None