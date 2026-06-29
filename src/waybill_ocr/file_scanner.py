from pathlib import Path

from waybill_ocr.constants import SUPPORTED_SUFFIXES
from waybill_ocr.models import FileTask


def scan_input_files(input_dir: Path) -> list[FileTask]:
    tasks: list[FileTask] = []
    for path in sorted(input_dir.rglob("*")):
        if not path.is_file():
            continue

        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            continue

        tasks.append(
            FileTask(
                source_path=path,
                relative_name=str(path.relative_to(input_dir)),
                suffix=suffix,
            )
        )

    return tasks
