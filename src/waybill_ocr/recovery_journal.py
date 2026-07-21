import hashlib
import json
import os
from pathlib import Path

from waybill_ocr.models import FileTask, RecognitionResult, RecognitionSource, RecognitionStatus


def recovery_journal_path(state_dir: Path, output_dir: Path) -> Path:
    output_key = str(output_dir.resolve()).casefold().encode("utf-8")
    digest = hashlib.sha256(output_key).hexdigest()[:20]
    return state_dir / f"{digest}.jsonl"


def append_recovery_result(journal_path: Path, result: RecognitionResult) -> None:
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "original_name": result.original_name,
        "relative_name": result.relative_name,
        "status": result.status.value,
        "container_code": result.container_code,
        "source": result.source.value if result.source else None,
        "failure_reason": result.failure_reason,
        "elapsed_ms": result.elapsed_ms,
        "review_note": result.review_note,
        "review_code": result.review_code,
        "output_relative_path": result.output_relative_path,
    }
    with journal_path.open("a", encoding="utf-8", newline="\n") as file_obj:
        file_obj.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        file_obj.flush()
        os.fsync(file_obj.fileno())


def load_recovery_results(journal_path: Path, tasks: list[FileTask]) -> dict[str, RecognitionResult]:
    if not journal_path.is_file():
        return {}

    tasks_by_relative = {task.relative_name: task for task in tasks}
    recovered: dict[str, RecognitionResult] = {}
    with journal_path.open("r", encoding="utf-8") as file_obj:
        for line in file_obj:
            payload = _parse_payload(line)
            if payload is None:
                continue
            relative_name = _optional_string(payload.get("relative_name"))
            task = tasks_by_relative.get(relative_name or "")
            status = _status(payload.get("status"))
            if task is None or status is None:
                continue
            recovered[task.relative_name] = RecognitionResult(
                source_path=task.source_path,
                original_name=_optional_string(payload.get("original_name")) or task.source_path.name,
                status=status,
                container_code=_optional_string(payload.get("container_code")),
                source=_source(payload.get("source")),
                failure_reason=_optional_string(payload.get("failure_reason")),
                ocr_text="",
                elapsed_ms=_optional_int(payload.get("elapsed_ms")),
                relative_name=task.relative_name,
                review_note=_optional_string(payload.get("review_note")),
                review_code=_optional_string(payload.get("review_code")),
                output_relative_path=_optional_string(payload.get("output_relative_path")),
            )
    return recovered


def clear_recovery_journal(journal_path: Path) -> None:
    try:
        journal_path.unlink()
    except FileNotFoundError:
        return


def _parse_payload(line: str) -> dict | None:
    try:
        payload = json.loads(line)
    except (json.JSONDecodeError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def _status(value) -> RecognitionStatus | None:
    try:
        return RecognitionStatus(str(value))
    except ValueError:
        return None


def _source(value) -> RecognitionSource | None:
    if not value:
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
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
