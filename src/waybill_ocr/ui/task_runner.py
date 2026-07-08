import inspect
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from pathlib import Path

from waybill_ocr.batch_processor import ProcessingProgressEvent, process_directory
from waybill_ocr.cancellation import ProcessingCancelled
from waybill_ocr.config import AppConfig
from waybill_ocr.container_code.expected_codes import inspect_expected_codes
from waybill_ocr.models import RecognitionResult

ProgressCallback = Callable[[str], None]
TaskProgressCallback = Callable[[int, ProcessingProgressEvent], None]
EngineFactory = Callable[[AppConfig], object]
ProcessDirectoryFunc = Callable[..., list[RecognitionResult]]


@dataclass(frozen=True)
class DirectoryTask:
    input_dir: Path
    output_dir: Path
    label: str
    expected_codes_path: Path | None = None


def process_directory_tasks(
    tasks: list[DirectoryTask],
    base_config: AppConfig,
    engine_factory: EngineFactory,
    on_progress: ProgressCallback | None = None,
    cancel_event=None,
    on_progress_event: TaskProgressCallback | None = None,
    max_workers: int = 2,
    process_directory_func: ProcessDirectoryFunc = process_directory,
) -> list[RecognitionResult]:
    if not tasks:
        return []

    worker_count = min(max_workers, len(tasks))
    results: list[RecognitionResult] = []
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [
            executor.submit(
                _process_one_task,
                task_number,
                task,
                base_config,
                engine_factory,
                on_progress,
                cancel_event,
                on_progress_event,
                process_directory_func,
            )
            for task_number, task in enumerate(tasks, start=1)
        ]
        for future in as_completed(futures):
            results.extend(future.result())

    return results


def _process_one_task(
    task_number: int,
    task: DirectoryTask,
    base_config: AppConfig,
    engine_factory: EngineFactory,
    on_progress: ProgressCallback | None,
    cancel_event,
    on_progress_event: TaskProgressCallback | None,
    process_directory_func: ProcessDirectoryFunc,
) -> list[RecognitionResult]:
    config = _task_config(base_config, task_number)
    engine = engine_factory(config)

    def prefixed_progress(message: str) -> None:
        if on_progress:
            on_progress(f"[{task.label}] {message}")

    def prefixed_progress_event(event: ProcessingProgressEvent) -> None:
        if on_progress_event:
            on_progress_event(task_number, event)

    expected_inspection = inspect_expected_codes(task.expected_codes_path) if task.expected_codes_path else None
    kwargs = {"cancel_event": cancel_event}
    if expected_inspection is not None:
        kwargs["expected_codes"] = expected_inspection.valid_codes
        kwargs["expected_invalid_entries"] = expected_inspection.invalid_entries
    if _accepts_keyword(process_directory_func, "on_progress_event"):
        kwargs["on_progress_event"] = prefixed_progress_event

    try:
        return process_directory_func(
            task.input_dir,
            task.output_dir,
            config,
            engine,
            prefixed_progress,
            **kwargs,
        )
    except ProcessingCancelled:
        prefixed_progress("已取消")
        return []
    except Exception as exc:
        prefixed_progress(f"任务处理失败，已跳过该任务: {exc}")
        return []


def _accepts_keyword(func: ProcessDirectoryFunc, keyword: str) -> bool:
    signature = inspect.signature(func)
    return keyword in signature.parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()
    )


def _task_config(base_config: AppConfig, task_number: int) -> AppConfig:
    if base_config.work_dir is None:
        return base_config

    return replace(base_config, work_dir=base_config.work_dir / f"task-{task_number}")



def _friendly_exception(exc: Exception) -> str:
    message = str(exc)
    if isinstance(exc, PermissionError):
        return f"\u53ef\u80fd\u6b63\u5728\u88ab Excel/WPS \u6253\u5f00\u6216\u76ee\u5f55\u65e0\u5199\u5165\u6743\u9650: {message}"
    if "pdf" in message.lower() or "poppler" in message.lower():
        return f"PDF \u8f6c\u56fe\u5931\u8d25\uff0c\u53ef\u80fd\u6587\u4ef6\u635f\u574f\u6216\u52a0\u5bc6: {message}"
    return message
