import os
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from waybill_ocr.cancellation import ProcessingCancelled, is_cancelled
from waybill_ocr.config import AppConfig, OCR_SPEED_FAST, OCR_SPEED_STABLE
from waybill_ocr.ocr.base import OcrResult


TESSERACT_ARGS = [
    "-l",
    "eng",
    "--psm",
    "6",
    "-c",
    "tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
]
OCR_TIMEOUT_SECONDS = 60
POLL_INTERVAL_SECONDS = 0.05
ProcessFactory = Callable[..., Any]


class TesseractEngine:
    def __init__(self, config: AppConfig, process_factory: ProcessFactory | None = None) -> None:
        self.config = config
        self._process_factory = process_factory or subprocess.Popen

    def recognize_image(self, image_path: Path, cancel_event=None) -> OcrResult:
        started = time.perf_counter()
        text = ""
        last_error = ""

        for _ in range(self._effective_retries() + 1):
            process = self._process_factory(
                self._build_command(image_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=self._subprocess_env(),
                **self._window_options(),
            )
            stdout, stderr, returncode = self._wait_for_process(process, cancel_event)
            text = stdout or ""
            last_error = stderr or ""
            if returncode == 0 and text.strip():
                break

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if not text.strip():
            detail = last_error.strip() or "未输出 OCR 文本"
            raise RuntimeError(f"Tesseract OCR 失败: {detail}")

        return OcrResult(text=text, engine_name="tesseract", elapsed_ms=elapsed_ms)


    def _effective_retries(self) -> int:
        if self.config.ocr_speed_mode == OCR_SPEED_FAST:
            return 0
        if self.config.ocr_speed_mode == OCR_SPEED_STABLE:
            return max(self.config.ocr_retries, 1)
        return self.config.ocr_retries

    def _wait_for_process(self, process, cancel_event) -> tuple[str, str, int | None]:
        deadline = time.perf_counter() + OCR_TIMEOUT_SECONDS
        while process.poll() is None:
            if is_cancelled(cancel_event):
                _terminate_process(process)
                raise ProcessingCancelled()
            if time.perf_counter() >= deadline:
                _kill_process(process)
                raise RuntimeError("Tesseract OCR 超时")
            time.sleep(POLL_INTERVAL_SECONDS)

        stdout, stderr = process.communicate()
        return stdout or "", stderr or "", process.returncode

    def _build_command(self, image_path: Path) -> list[str]:
        executable = self.config.tesseract_cmd or Path("tesseract")
        return [str(executable), str(image_path), "stdout", *self._tessdata_args(), *TESSERACT_ARGS]

    def _subprocess_env(self) -> dict[str, str]:
        env = os.environ.copy()
        tessdata_dir = self._tessdata_dir()
        if tessdata_dir:
            env["TESSDATA_PREFIX"] = str(tessdata_dir)
        return env

    def _window_options(self) -> dict:
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            return {"creationflags": subprocess.CREATE_NO_WINDOW}
        return {}

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


def _terminate_process(process) -> None:
    process.terminate()
    try:
        process.wait(timeout=2)
    except Exception:
        _kill_process(process)


def _kill_process(process) -> None:
    process.kill()
    try:
        process.wait(timeout=2)
    except Exception:
        pass
