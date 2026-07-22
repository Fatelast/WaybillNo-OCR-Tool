from pathlib import Path

from openpyxl import load_workbook

from waybill_ocr.container_code.decision import _format_candidates
from waybill_ocr.models import RecognitionResult, RecognitionSource, RecognitionStatus
from waybill_ocr.output import excel_writer
from waybill_ocr.output.excel_writer import write_results
from waybill_ocr.ui import main_window


def test_write_results_limits_visible_review_note_and_keeps_failure_summary(tmp_path: Path):
    result = RecognitionResult(
        source_path=tmp_path / "blurred.pdf",
        original_name="blurred.pdf",
        status=RecognitionStatus.INVALID,
        container_code="YYCU6002610",
        source=RecognitionSource.OCR,
        failure_reason="INVALID_CHECK_DIGIT",
        ocr_text="",
        elapsed_ms=1,
        review_note="疑似候选: " + ", ".join(f"YYCU{i:07d}" for i in range(80)),
    )

    workbook_path = write_results([result], tmp_path)
    workbook = load_workbook(workbook_path)
    displayed_note = workbook["识别结果"]["E2"].value

    assert displayed_note.startswith("疑似候选:")
    assert "其余候选已省略" in displayed_note
    assert "校验位不正确" in displayed_note
    assert len(displayed_note) < 320


def test_task_duration_uses_live_time_then_freezes_at_completion():
    state = {"started_at": 100.0, "finished_at": None}

    assert main_window._task_elapsed_seconds(state, now=165.0) == 65.0
    state["finished_at"] = 170.0
    assert main_window._task_elapsed_seconds(state, now=999.0) == 70.0
    assert main_window._format_task_duration(65.0) == "01:05"
    assert main_window._format_task_duration(3661.0) == "01:01:01"


def test_new_task_progress_state_starts_only_when_task_runs():
    active = main_window._new_task_progress_state(True)
    inactive = main_window._new_task_progress_state(False)

    assert active["started_at"] is None
    main_window._start_task_progress_timer(active, now=123.0)
    main_window._start_task_progress_timer(active, now=999.0)

    assert active["started_at"] == 123.0
    assert active["finished_at"] is None
    assert inactive["started_at"] is None


def test_review_candidate_list_keeps_only_a_small_preview():
    candidates = [f"TEMU{i:07d}" for i in range(12)]

    displayed = _format_candidates(candidates)

    assert candidates[7] in displayed
    assert candidates[8] not in displayed


def test_review_selection_marker_is_explicit_and_accessible():
    assert main_window._review_selection_marker(selected=False, valid=True) == "☐ 选择"
    assert main_window._review_selection_marker(selected=True, valid=True) == "☑ 已选"
    assert main_window._review_selection_marker(selected=True, valid=False) == "不可选"


def test_review_selection_summary_reports_current_and_available_counts():
    assert main_window._review_selection_summary(2, 8) == "已选择 2 个 / 可整理 8 个"
