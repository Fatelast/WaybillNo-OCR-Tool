from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class OcrResult:
    text: str
    engine_name: str
    elapsed_ms: int


class OcrEngine(Protocol):
    def recognize_image(self, image_path: Path) -> OcrResult:
        """识别单张图片并返回 OCR 文本。"""
