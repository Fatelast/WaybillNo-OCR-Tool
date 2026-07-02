from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from pathlib import Path

from waybill_ocr.batch_processor import process_directory
from waybill_ocr.cancellation import ProcessingCancelled
from waybill_ocr.config import AppConfig
from waybill_ocr.container_code.expected_codes import read_expected_codes
from waybill_ocr.models import RecognitionResult

ProgressCallback = Callable[[str], None]
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
    process_directory_func: ProcessDirectoryFunc,
) -> list[RecognitionResult]:
    config = _task_config(base_config, task_number)
    engine = engine_factory(config)

    def prefixed_progress(message: str) -> None:
        if on_progress:
            on_progress(f"[{task.label}] {message}")

    expected_codes = read_expected_codes(task.expected_codes_path) if task.expected_codes_path else None
    kwargs = {"cancel_event": cancel_event}
    if expected_codes is not None:
        kwargs["expected_codes"] = expected_codes

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


def _task_config(base_config: AppConfig, task_number: int) -> AppConfig:
    if base_config.work_dir is None:
        return base_config

    return replace(base_config, work_dir=base_config.work_dir / f"task-{task_number}")
