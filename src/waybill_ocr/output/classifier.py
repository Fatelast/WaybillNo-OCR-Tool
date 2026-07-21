import os
import shutil
from pathlib import Path
from uuid import uuid4

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


def copy_result_file(
    result: RecognitionResult,
    output_dir: Path,
    previous_output_relative_path: str | None = None,
) -> Path:
    target_dir = output_dir / STATUS_DIR_NAMES[result.status]
    target_dir.mkdir(parents=True, exist_ok=True)
    desired_path = target_dir / _target_file_name(result)
    previous_path = _safe_previous_output_path(output_dir, previous_output_relative_path)
    target_path = previous_path if previous_path == desired_path.resolve() else _unique_target_path(desired_path)

    if result.source_path.resolve() != target_path.resolve():
        _copy_atomically(result.source_path, target_path)
    if previous_path is not None and previous_path != target_path.resolve() and previous_path.exists():
        previous_path.unlink()
    return target_path


def _safe_previous_output_path(output_dir: Path, relative_path: str | None) -> Path | None:
    if not relative_path:
        return None
    relative = Path(relative_path)
    if relative.is_absolute() or len(relative.parts) != 2 or relative.parts[0] not in STATUS_DIR_NAMES.values():
        return None
    output_root = output_dir.resolve()
    candidate = (output_root / relative).resolve()
    try:
        candidate.relative_to(output_root)
    except ValueError:
        return None
    return candidate


def _copy_atomically(source_path: Path, target_path: Path) -> None:
    temporary_path = target_path.with_name(f".{target_path.name}.{uuid4().hex}.tmp")
    try:
        shutil.copy2(source_path, temporary_path)
        os.replace(temporary_path, target_path)
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


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
