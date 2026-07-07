import shutil
from pathlib import Path

from waybill_ocr.constants import (
    INVALID_DIR_NAME,
    SUCCESS_DIR_NAME,
    UNRECOGNIZED_DIR_NAME,
)
from waybill_ocr.models import RecognitionResult, RecognitionStatus


STATUS_DIR_NAMES = {
    RecognitionStatus.SUCCESS: SUCCESS_DIR_NAME,
    RecognitionStatus.UNRECOGNIZED: UNRECOGNIZED_DIR_NAME,
    RecognitionStatus.INVALID: INVALID_DIR_NAME,
}


def copy_result_file(result: RecognitionResult, output_dir: Path) -> Path:
    target_dir = output_dir / STATUS_DIR_NAMES[result.status]
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = _unique_target_path(target_dir / _target_file_name(result))
    shutil.copy2(result.source_path, target_path)
    return target_path


def _target_file_name(result: RecognitionResult) -> str:
    suffix = Path(result.original_name).suffix
    if result.status == RecognitionStatus.SUCCESS and result.container_code:
        return f"{result.container_code}{suffix}"
    if result.status in {RecognitionStatus.UNRECOGNIZED, RecognitionStatus.INVALID} and result.review_code:
        return f"{result.review_code}-待确认{suffix}"

    return result.original_name


def _unique_target_path(target_path: Path) -> Path:
    if not target_path.exists():
        return target_path

    stem = target_path.stem
    suffix = target_path.suffix
    parent = target_path.parent
    index = 1
    while True:
        candidate = parent / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1
