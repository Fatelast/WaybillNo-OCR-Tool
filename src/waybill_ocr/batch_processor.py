import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from waybill_ocr.cancellation import ProcessingCancelled, raise_if_cancelled
from waybill_ocr.config import AppConfig
from waybill_ocr.constants import RESULT_WORKBOOK_NAME
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
    cancel_event=None,
) -> list[RecognitionResult]:
    tasks = _exclude_output_tasks(scan_input_files(input_dir), output_dir)
    _emit(on_progress, f"扫描到 {len(tasks)} 个文件")

    results: list[RecognitionResult] = []
    workbook_path: Path | None = None
    total = len(tasks)
    try:
        for index, task in enumerate(tasks, start=1):
            raise_if_cancelled(cancel_event)
            _emit(on_progress, f"处理中: {index}/{total} {task.relative_name}")
            result = process_file(task, config, ocr_engine, cancel_event=cancel_event)
            raise_if_cancelled(cancel_event)
            copy_result_file(result, output_dir)
            results.append(result)
            workbook_path = _write_results(results, output_dir, workbook_path, on_progress)
            _emit(on_progress, _format_result_message(result))

        _emit(on_progress, "处理完成")
        return results
    except ProcessingCancelled:
        if results:
            _write_results(results, output_dir, workbook_path, on_progress)
        _emit(on_progress, f"已取消：已处理 {len(results)}/{total}")
        return results
    finally:
        _cleanup_work_dir(config)


def _write_results(
    results: list[RecognitionResult],
    output_dir: Path,
    workbook_path: Path | None,
    on_progress: ProgressCallback | None,
) -> Path:
    try:
        return write_results(results, output_dir, workbook_path=workbook_path)
    except PermissionError:
        if workbook_path is not None:
            raise

        fallback_path = _backup_workbook_path(output_dir)
        _emit(on_progress, f"{RESULT_WORKBOOK_NAME} 被占用，已改写备用结果表: {fallback_path.name}")
        return write_results(results, output_dir, workbook_path=fallback_path)


def _backup_workbook_path(output_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return output_dir / f"识别结果-备份-{timestamp}.xlsx"


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
