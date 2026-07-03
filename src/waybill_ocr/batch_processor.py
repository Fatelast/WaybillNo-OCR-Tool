import shutil
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from time import perf_counter

from openpyxl import load_workbook

from waybill_ocr.cancellation import ProcessingCancelled, raise_if_cancelled
from waybill_ocr.config import AppConfig
from waybill_ocr.constants import RESULT_WORKBOOK_NAME
from waybill_ocr.container_code.expected_codes import compare_expected_codes
from waybill_ocr.file_scanner import scan_input_files
from waybill_ocr.image_loader import iter_images_for_ocr
from waybill_ocr.models import FileTask, RecognitionResult, RecognitionSource, RecognitionStatus
from waybill_ocr.ocr.base import OcrEngine
from waybill_ocr.output.classifier import copy_result_file
from waybill_ocr.output.excel_writer import write_results
from waybill_ocr.pipeline import process_file

ProgressCallback = Callable[[str], None]
EVIDENCE_DIR_NAME = "\u8bc6\u522b\u8bc1\u636e"


def process_directory(
    input_dir: Path,
    output_dir: Path,
    config: AppConfig,
    ocr_engine: OcrEngine,
    on_progress: ProgressCallback | None = None,
    cancel_event=None,
    expected_codes: list[str] | None = None,
    expected_invalid_entries: list[str] | None = None,
) -> list[RecognitionResult]:
    tasks = _exclude_output_tasks(scan_input_files(input_dir), output_dir)
    existing_results = _load_existing_results(tasks, output_dir, on_progress)
    _emit(on_progress, f"\u626b\u63cf\u5230 {len(tasks)} \u4e2a\u6587\u4ef6")

    results: list[RecognitionResult] = []
    workbook_path: Path | None = None
    total = len(tasks)
    try:
        for index, task in enumerate(tasks, start=1):
            raise_if_cancelled(cancel_event)
            existing_result = existing_results.get(task.source_path.name)
            if existing_result is not None:
                results.append(existing_result)
                _emit(on_progress, f"\u5df2\u8df3\u8fc7\u5df2\u5904\u7406\u6587\u4ef6: {task.relative_name}")
                _emit(on_progress, _format_result_message(existing_result))
                continue

            started_at = perf_counter()
            _emit(on_progress, f"\u5904\u7406\u4e2d: {index}/{total} {task.relative_name}")

            try:
                result = process_file(task, config, ocr_engine, cancel_event=cancel_event)
                raise_if_cancelled(cancel_event)
                copy_result_file(result, output_dir)
            except ProcessingCancelled:
                raise
            except Exception as exc:
                result = _failed_result(task, f"PROCESS_FAILED: {exc}", started_at)
                _emit(on_progress, f"\u6587\u4ef6\u5904\u7406\u5931\u8d25\uff0c\u5df2\u8df3\u8fc7: {task.relative_name} ({exc})")
                _copy_failed_result(result, output_dir, on_progress)

            result = _attach_evidence_if_needed(result, task, output_dir, config, cancel_event, on_progress)
            results.append(result)
            workbook_path = _write_results(
                results, output_dir, workbook_path, on_progress, expected_codes, expected_invalid_entries
            )
            _emit(on_progress, _format_result_message(result))

        _emit_comparison_report(expected_codes, results, on_progress, expected_invalid_entries)
        _emit(on_progress, "\u5904\u7406\u5b8c\u6210")
        return results
    except ProcessingCancelled:
        if results:
            _write_results(results, output_dir, workbook_path, on_progress, expected_codes, expected_invalid_entries)
        _emit(on_progress, f"\u5df2\u53d6\u6d88\uff1a\u5df2\u5904\u7406 {len(results)}/{total}")
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
        _emit(on_progress, f"\u5931\u8d25\u6587\u4ef6\u590d\u5236\u5230\u672a\u8bc6\u522b\u76ee\u5f55\u5931\u8d25\uff0c\u5df2\u7ee7\u7eed: {result.original_name} ({exc})")


def _attach_evidence_if_needed(
    result: RecognitionResult,
    task: FileTask,
    output_dir: Path,
    config: AppConfig,
    cancel_event,
    on_progress: ProgressCallback | None,
) -> RecognitionResult:
    if result.status is RecognitionStatus.SUCCESS or result.evidence_path is not None:
        return result

    try:
        evidence_path = _save_evidence_image(task, output_dir, config, cancel_event)
    except Exception as exc:
        _emit(on_progress, f"\u8bc1\u636e\u622a\u56fe\u4fdd\u5b58\u5931\u8d25\uff0c\u5df2\u7ee7\u7eed: {task.relative_name} ({exc})")
        return result

    if evidence_path is None:
        return result
    return replace(result, evidence_path=evidence_path)


def _save_evidence_image(
    task: FileTask,
    output_dir: Path,
    config: AppConfig,
    cancel_event,
) -> Path | None:
    raise_if_cancelled(cancel_event)
    image_iterator = iter(iter_images_for_ocr(task.source_path, config))
    try:
        try:
            image_path = next(image_iterator)
        except StopIteration:
            return None

        raise_if_cancelled(cancel_event)
        target_dir = output_dir / EVIDENCE_DIR_NAME
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / _evidence_file_name(task)

        from PIL import Image

        with Image.open(image_path) as image:
            image.convert("RGB").save(target_path)
        return target_path
    finally:
        _close_iterator(image_iterator)


def _evidence_file_name(task: FileTask) -> str:
    relative_path = Path(task.relative_name).with_suffix("")
    stem = "__".join(part for part in relative_path.parts if part)
    if not stem:
        stem = task.source_path.stem
    return f"{stem}.png"


def _write_results(
    results: list[RecognitionResult],
    output_dir: Path,
    workbook_path: Path | None,
    on_progress: ProgressCallback | None,
    expected_codes: list[str] | None = None,
    expected_invalid_entries: list[str] | None = None,
) -> Path | None:
    try:
        return write_results(
            results,
            output_dir,
            workbook_path=workbook_path,
            comparison_report=_comparison_report(expected_codes, results, expected_invalid_entries),
        )
    except PermissionError as exc:
        if workbook_path is not None:
            _emit(on_progress, f"\u7ed3\u679c\u8868\u5199\u5165\u5931\u8d25\uff0c\u5df2\u7ee7\u7eed\u5904\u7406: {exc}")
            return workbook_path

        fallback_path = _backup_workbook_path(output_dir)
        _emit(on_progress, f"{RESULT_WORKBOOK_NAME} \u88ab\u5360\u7528\uff0c\u5df2\u6539\u5199\u5907\u7528\u7ed3\u679c\u8868: {fallback_path.name}")
        try:
            return write_results(
                results,
                output_dir,
                workbook_path=fallback_path,
                comparison_report=_comparison_report(expected_codes, results, expected_invalid_entries),
            )
        except PermissionError as fallback_exc:
            _emit(on_progress, f"\u7ed3\u679c\u8868\u5199\u5165\u5931\u8d25\uff0c\u5df2\u7ee7\u7eed\u5904\u7406: {fallback_exc}")
            return None


def _load_existing_results(
    tasks: list[FileTask],
    output_dir: Path,
    on_progress: ProgressCallback | None,
) -> dict[str, RecognitionResult]:
    workbook_path = output_dir / RESULT_WORKBOOK_NAME
    if not workbook_path.exists():
        return {}

    tasks_by_name = {task.source_path.name: task for task in tasks}
    workbook = None
    try:
        workbook = load_workbook(workbook_path, read_only=True, data_only=True)
        sheet = workbook.active
        rows = sheet.iter_rows(values_only=True)
        headers = {name: index for index, name in enumerate(next(rows, [])) if name}
        results: dict[str, RecognitionResult] = {}
        for row in rows:
            original_name = _row_value(row, headers, "\u539f\u59cb\u6587\u4ef6\u540d")
            if not original_name or original_name not in tasks_by_name:
                continue

            task = tasks_by_name[original_name]
            status = _recognition_status(_row_value(row, headers, "\u8bc6\u522b\u72b6\u6001"))
            if status is None:
                continue

            results[original_name] = RecognitionResult(
                source_path=task.source_path,
                original_name=original_name,
                status=status,
                container_code=_optional_string(_row_value(row, headers, "\u8bc6\u522b\u7bb1\u53f7")),
                source=_recognition_source(_row_value(row, headers, "\u8bc6\u522b\u6765\u6e90")),
                failure_reason=_optional_string(_row_value(row, headers, "\u5931\u8d25\u539f\u56e0")),
                ocr_text="",
                elapsed_ms=_optional_int(_row_value(row, headers, "\u5904\u7406\u8017\u65f6ms")),
                review_note=_optional_string(_row_value(row, headers, "\u5907\u6ce8")),
                evidence_path=_resolve_evidence_path(output_dir, _row_value(row, headers, "\u8bc1\u636e\u622a\u56fe")),
            )
        return results
    except Exception as exc:
        _emit(on_progress, f"\u5386\u53f2\u7ed3\u679c\u8bfb\u53d6\u5931\u8d25\uff0c\u5df2\u91cd\u65b0\u5904\u7406\u5168\u90e8\u6587\u4ef6: {exc}")
        return {}
    finally:
        if workbook is not None:
            workbook.close()


def _row_value(row, headers: dict[str, int], name: str):
    index = headers.get(name)
    if index is None or index >= len(row):
        return None
    return row[index]


def _recognition_status(value) -> RecognitionStatus | None:
    if value is None:
        return None
    try:
        return RecognitionStatus(str(value))
    except ValueError:
        return None


def _recognition_source(value) -> RecognitionSource | None:
    if value is None or value == "":
        return None
    try:
        return RecognitionSource(str(value))
    except ValueError:
        return None


def _optional_string(value) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _optional_int(value) -> int:
    if value is None or value == "":
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _resolve_evidence_path(output_dir: Path, value) -> Path | None:
    if value is None or value == "":
        return None
    path = Path(str(value))
    if path.is_absolute():
        return path
    return output_dir / path


def _comparison_report(
    expected_codes: list[str] | None,
    results: list[RecognitionResult],
    expected_invalid_entries: list[str] | None = None,
):
    if expected_codes is None and not expected_invalid_entries:
        return None
    return compare_expected_codes(expected_codes or [], results, expected_invalid_entries)


def _emit_comparison_report(
    expected_codes: list[str] | None,
    results: list[RecognitionResult],
    on_progress: ProgressCallback | None,
    expected_invalid_entries: list[str] | None = None,
) -> None:
    if expected_codes is None and not expected_invalid_entries:
        return

    report = compare_expected_codes(expected_codes or [], results, expected_invalid_entries)
    _emit(
        on_progress,
        f"\u7bb1\u53f7\u6bd4\u5bf9: \u5df2\u5339\u914d {len(report.matched_codes)}, \u7f3a\u5931 {len(report.missing_codes)}, "
        f"\u591a\u4f59 {len(report.extra_codes)}, \u683c\u5f0f\u65e0\u6548 {len(report.invalid_expected_entries)}",
    )
    if report.missing_codes:
        _emit(on_progress, f"\u7f3a\u5931\u7bb1\u53f7: {', '.join(report.missing_codes)}")
    if report.invalid_expected_entries:
        _emit(on_progress, f"\u683c\u5f0f\u65e0\u6548\u6e05\u5355\u9879: {', '.join(report.invalid_expected_entries)}")


def _backup_workbook_path(output_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return output_dir / f"\u8bc6\u522b\u7ed3\u679c-\u5907\u4efd-{timestamp}.xlsx"


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
    detail = result.container_code or result.failure_reason or "\u65e0\u7bb1\u53f7"
    return f"\u7ed3\u679c: {result.original_name} -> {result.status.value} ({detail})"


def _cleanup_work_dir(config: AppConfig) -> None:
    if config.work_dir:
        shutil.rmtree(config.work_dir, ignore_errors=True)


def _close_iterator(iterator) -> None:
    close = getattr(iterator, "close", None)
    if close:
        close()


def _emit(on_progress: ProgressCallback | None, message: str) -> None:
    if on_progress:
        on_progress(message)
