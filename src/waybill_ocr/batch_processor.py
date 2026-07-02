import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from time import perf_counter

from waybill_ocr.cancellation import ProcessingCancelled, raise_if_cancelled
from waybill_ocr.config import AppConfig
from waybill_ocr.constants import RESULT_WORKBOOK_NAME
from waybill_ocr.container_code.expected_codes import compare_expected_codes
from waybill_ocr.file_scanner import scan_input_files
from waybill_ocr.models import FileTask, RecognitionResult, RecognitionStatus
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
    expected_codes: list[str] | None = None,
) -> list[RecognitionResult]:
    tasks = _exclude_output_tasks(scan_input_files(input_dir), output_dir)
    _emit(on_progress, f"扫描到 {len(tasks)} 个文件")

    results: list[RecognitionResult] = []
    workbook_path: Path | None = None
    total = len(tasks)
    try:
        for index, task in enumerate(tasks, start=1):
            raise_if_cancelled(cancel_event)
            started_at = perf_counter()
            _emit(on_progress, f"处理中: {index}/{total} {task.relative_name}")

            try:
                result = process_file(task, config, ocr_engine, cancel_event=cancel_event)
                raise_if_cancelled(cancel_event)
                copy_result_file(result, output_dir)
            except ProcessingCancelled:
                raise
            except Exception as exc:
                result = _failed_result(task, f"PROCESS_FAILED: {exc}", started_at)
                _emit(on_progress, f"文件处理失败，已跳过: {task.relative_name} ({exc})")
                _copy_failed_result(result, output_dir, on_progress)

            results.append(result)
            workbook_path = _write_results(results, output_dir, workbook_path, on_progress, expected_codes)
            _emit(on_progress, _format_result_message(result))

        _emit_comparison_report(expected_codes, results, on_progress)
        _emit(on_progress, "处理完成")
        return results
    except ProcessingCancelled:
        if results:
            _write_results(results, output_dir, workbook_path, on_progress, expected_codes)
        _emit(on_progress, f"已取消：已处理 {len(results)}/{total}")
        return results
    finally:
        _cleanup_work_dir(config)


def _failed_result(task: FileTask, reason: str, started_at: float) -> RecognitionResult:
    elapsed_ms = int((perf_counter() - started_at) * 1000)
    return RecognitionResult(
        source_path=task.source_path,
        original_name=task.source_path.name,
        status=RecognitionStatus.UNRECOGNIZED,
        container_code=None,
        source=None,
        failure_reason=reason,
        ocr_text="",
        elapsed_ms=elapsed_ms,
    )


def _copy_failed_result(result: RecognitionResult, output_dir: Path, on_progress: ProgressCallback | None) -> None:
    try:
        copy_result_file(result, output_dir)
    except Exception as exc:
        _emit(on_progress, f"失败文件复制到未识别目录失败，已继续: {result.original_name} ({exc})")


def _write_results(
    results: list[RecognitionResult],
    output_dir: Path,
    workbook_path: Path | None,
    on_progress: ProgressCallback | None,
    expected_codes: list[str] | None = None,
) -> Path | None:
    try:
        return write_results(
            results,
            output_dir,
            workbook_path=workbook_path,
            comparison_report=_comparison_report(expected_codes, results),
        )
    except PermissionError as exc:
        if workbook_path is not None:
            _emit(on_progress, f"结果表写入失败，已继续处理: {exc}")
            return workbook_path

        fallback_path = _backup_workbook_path(output_dir)
        _emit(on_progress, f"{RESULT_WORKBOOK_NAME} 被占用，已改写备用结果表: {fallback_path.name}")
        try:
            return write_results(
                results,
                output_dir,
                workbook_path=fallback_path,
                comparison_report=_comparison_report(expected_codes, results),
            )
        except PermissionError as fallback_exc:
            _emit(on_progress, f"结果表写入失败，已继续处理: {fallback_exc}")
            return None



def _comparison_report(expected_codes: list[str] | None, results: list[RecognitionResult]):
    if expected_codes is None:
        return None
    return compare_expected_codes(expected_codes, results)


def _emit_comparison_report(
    expected_codes: list[str] | None,
    results: list[RecognitionResult],
    on_progress: ProgressCallback | None,
) -> None:
    if expected_codes is None:
        return

    report = compare_expected_codes(expected_codes, results)
    _emit(
        on_progress,
        f"\u7bb1\u53f7\u6bd4\u5bf9: \u5df2\u5339\u914d {len(report.matched_codes)}, \u7f3a\u5931 {len(report.missing_codes)}, \u591a\u4f59 {len(report.extra_codes)}",
    )
    if report.missing_codes:
        _emit(on_progress, f"\u7f3a\u5931\u7bb1\u53f7: {', '.join(report.missing_codes)}")


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
