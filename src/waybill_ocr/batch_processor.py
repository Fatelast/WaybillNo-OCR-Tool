import shutil
from collections.abc import Callable
from pathlib import Path

from waybill_ocr.config import AppConfig
from waybill_ocr.file_scanner import scan_input_files
from waybill_ocr.models import FileTask, RecognitionResult
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
    tasks = _exclude_output_tasks(scan_input_files(input_dir), output_dir)
    _emit(on_progress, f"扫描到 {len(tasks)} 个文件")

    results: list[RecognitionResult] = []
    total = len(tasks)
    try:
        for index, task in enumerate(tasks, start=1):
            _emit(on_progress, f"处理中: {index}/{total} {task.relative_name}")
            result = process_file(task, config, ocr_engine)
            copy_result_file(result, output_dir)
            results.append(result)
            write_results(results, output_dir)
            _emit(on_progress, _format_result_message(result))

        _emit(on_progress, "处理完成")
        return results
    finally:
        _cleanup_work_dir(config)


def _exclude_output_tasks(tasks: list[FileTask], output_dir: Path) -> list[FileTask]:
    resolved_output = output_dir.resolve()
    filtered_tasks = []
    for task in tasks:
        resolved_source = task.source_path.resolve()
        if resolved_source == resolved_output or resolved_output in resolved_source.parents:
            continue
        filtered_tasks.append(task)
    return filtered_tasks


def _format_result_message(result: RecognitionResult) -> str:
    detail = result.container_code or result.failure_reason or "无箱号"
    return f"结果: {result.original_name} -> {result.status.value} ({detail})"


def _cleanup_work_dir(config: AppConfig) -> None:
    if config.work_dir:
        shutil.rmtree(config.work_dir, ignore_errors=True)


def _emit(on_progress: ProgressCallback | None, message: str) -> None:
    if on_progress:
        on_progress(message)