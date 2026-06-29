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
    target_path = target_dir / result.original_name
    shutil.copy2(result.source_path, target_path)
    return target_path
