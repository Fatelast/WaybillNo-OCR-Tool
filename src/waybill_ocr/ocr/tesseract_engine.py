import time
from pathlib import Path
from typing import Any

from waybill_ocr.config import AppConfig
from waybill_ocr.ocr.base import OcrResult


TESSERACT_CONFIG = "--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


class TesseractEngine:
    def __init__(self, config: AppConfig, pytesseract_module: Any | None = None) -> None:
        self.config = config
        self._pytesseract = pytesseract_module

        if config.tesseract_cmd:
            pytesseract = self._load_pytesseract()
            pytesseract.pytesseract.tesseract_cmd = str(config.tesseract_cmd)

    def recognize_image(self, image_path: Path) -> OcrResult:
        started = time.perf_counter()
        text = ""
        last_error: Exception | None = None
        pytesseract = self._load_pytesseract()

        for _ in range(self.config.ocr_retries + 1):
            try:
                text = pytesseract.image_to_string(
                    str(image_path),
                    lang="eng",
                    config=TESSERACT_CONFIG,
                )
                if text.strip():
                    break
            except Exception as exc:
                last_error = exc

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if last_error and not text:
            raise RuntimeError(f"Tesseract OCR 失败: {last_error}") from last_error

        return OcrResult(text=text, engine_name="tesseract", elapsed_ms=elapsed_ms)

    def _load_pytesseract(self) -> Any:
        if self._pytesseract is None:
            import pytesseract

            self._pytesseract = pytesseract

        return self._pytesseract
