from collections.abc import Callable
from pathlib import Path

from waybill_ocr.config import AppConfig
from waybill_ocr.file_scanner import scan_input_files
from waybill_ocr.models import RecognitionResult
from waybill_ocr.ocr.base import OcrEngine
from waybill_ocr.output.classifier import copy_result_file
from waybill_ocr.output.excel_writer import write_results
from waybill_ocr.pipeline import process_file

ProgressCallback = Callable[[str], None]


def process_directory(
    input_dir: Path,
    output_dir: Path,
    config: AppConfig,
    ocr_engine: OcrEngine,
    on_progress: ProgressCallback | None = None,
) -> list[RecognitionResult]:
    tasks = scan_input_files(input_dir)
    _emit(on_progress, f"扫描到 {len(tasks)} 个文件")

    results: list[RecognitionResult] = []
    total = len(tasks)
    for index, task in enumerate(tasks, start=1):
        _emit(on_progress, f"处理中: {index}/{total} {task.relative_name}")
        result = process_file(task, config, ocr_engine)
        copy_result_file(result, output_dir)
        results.append(result)

    write_results(results, output_dir)
    _emit(on_progress, "处理完成")
    return results


def _emit(on_progress: ProgressCallback | None, message: str) -> None:
    if on_progress:
        on_progress(message)