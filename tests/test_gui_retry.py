from pathlib import Path
from types import SimpleNamespace

from waybill_ocr.models import RecognitionStatus
from waybill_ocr.ui import main_window
from waybill_ocr.ui.task_runner import DirectoryTask


def test_replace_task_result_status_corrects_counters_without_incrementing_processed():
    state = {"total": 2, "processed": 1, "success": 1, "unrecognized": 0, "invalid": 0}

    main_window.MainWindow._replace_task_result_status(
        state,
        RecognitionStatus.SUCCESS,
        RecognitionStatus.INVALID,
    )

    assert state == {"total": 2, "processed": 1, "success": 0, "unrecognized": 0, "invalid": 1}


def test_retry_failed_files_starts_only_selected_task(monkeypatch, tmp_path: Path):
    task = DirectoryTask(
        input_dir=tmp_path / "input",
        output_dir=tmp_path / "output",
        label="task 2/2",
    )
    calls = []

    class FakeThread:
        def __init__(self, *, target, args, daemon):
            calls.append(("thread", target, args, daemon))

        def start(self):
            calls.append(("started",))

    monkeypatch.setattr(main_window, "count_retryable_results", lambda _path: 3)
    monkeypatch.setattr(main_window.messagebox, "askyesno", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(main_window.threading, "Thread", FakeThread)

    window = SimpleNamespace(
        running=False,
        active_tasks=[task],
        cancel_event=None,
        _process=lambda *_args: None,
        _reset_single_task_progress=lambda index: calls.append(("reset", index)),
        _set_running_controls=lambda: calls.append(("locked",)),
        _append_log=lambda message: calls.append(("log", message)),
    )

    main_window.MainWindow._retry_failed_files(window, 0)

    assert window.running is True
    assert calls[0] == ("reset", 0)
    thread_call = next(call for call in calls if call[0] == "thread")
    assert thread_call[2][0] == [task]
    assert thread_call[2][2] == {1: 1}
    assert calls[-1] == ("started",)