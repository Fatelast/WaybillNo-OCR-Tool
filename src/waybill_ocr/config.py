from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    tesseract_cmd: Path | None = None
    poppler_path: Path | None = None
    ocr_retries: int = 2


def default_config() -> AppConfig:
    return AppConfig()
