from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class RecognitionStatus(str, Enum):
    SUCCESS = "正确识别"
    UNRECOGNIZED = "未识别"
    INVALID = "箱号错误"


class RecognitionSource(str, Enum):
    OCR = "OCR"
    OCR_REPAIRED = "OCR\u4fee\u6b63"
    FILENAME = "文件名"
    MANUAL = "人工修正"


@dataclass(frozen=True)
class FileTask:
    source_path: Path
    relative_name: str
    suffix: str


@dataclass(frozen=True)
class RecognitionResult:
    source_path: Path
    original_name: str
    status: RecognitionStatus
    container_code: str | None
    source: RecognitionSource | None
    failure_reason: str | None
    ocr_text: str
    elapsed_ms: int
    review_note: str | None = None
    evidence_path: Path | None = None
