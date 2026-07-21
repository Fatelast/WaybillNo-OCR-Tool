from pathlib import Path

from waybill_ocr.models import FileTask, RecognitionResult, RecognitionSource, RecognitionStatus
from waybill_ocr.recovery_journal import (
    append_recovery_result,
    clear_recovery_journal,
    load_recovery_results,
    recovery_journal_path,
)


def _success_result(source_path: Path) -> RecognitionResult:
    return RecognitionResult(
        source_path=source_path,
        original_name=source_path.name,
        status=RecognitionStatus.SUCCESS,
        container_code="HNKU6331795",
        source=RecognitionSource.OCR,
        failure_reason=None,
        ocr_text="HNKU6331795",
        elapsed_ms=10,
        relative_name=source_path.name,
        output_relative_path="正确识别/HNKU6331795.pdf",
    )


def test_recovery_journal_round_trips_latest_result(tmp_path: Path):
    source_path = tmp_path / "waybill.pdf"
    source_path.write_bytes(b"fake")
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".pdf")
    journal_path = recovery_journal_path(tmp_path / "state", tmp_path / "output")

    append_recovery_result(journal_path, _success_result(source_path))
    recovered = load_recovery_results(journal_path, [task])

    assert recovered[source_path.name].container_code == "HNKU6331795"
    assert recovered[source_path.name].output_relative_path == "正确识别/HNKU6331795.pdf"


def test_clear_recovery_journal_removes_saved_state(tmp_path: Path):
    source_path = tmp_path / "waybill.pdf"
    source_path.write_bytes(b"fake")
    journal_path = recovery_journal_path(tmp_path / "state", tmp_path / "output")
    append_recovery_result(journal_path, _success_result(source_path))

    clear_recovery_journal(journal_path)

    assert not journal_path.exists()
