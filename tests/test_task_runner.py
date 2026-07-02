import threading
from pathlib import Path

from waybill_ocr.config import AppConfig
from waybill_ocr.models import RecognitionResult
from waybill_ocr.ui.task_runner import DirectoryTask, process_directory_tasks


class FakeEngine:
    def __init__(self, config: AppConfig) -> None:
        self.config = config


def test_process_directory_tasks_runs_two_groups_concurrently(tmp_path: Path):
    input_one = tmp_path / "input-one"
    input_two = tmp_path / "input-two"
    output_one = tmp_path / "output-one"
    output_two = tmp_path / "output-two"
    input_one.mkdir()
    input_two.mkdir()
    started = []
    started_lock = threading.Lock()
    both_started = threading.Event()
    release = threading.Event()

    def fake_process_directory(input_dir, output_dir, config, ocr_engine, on_progress, cancel_event=None):
        with started_lock:
            started.append((input_dir, output_dir, config.work_dir, cancel_event))
            if len(started) == 2:
                both_started.set()
        assert release.wait(timeout=5)
        return []

    cancel_event = threading.Event()
    runner_thread = threading.Thread(
        target=process_directory_tasks,
        kwargs={
            "tasks": [
                DirectoryTask(input_dir=input_one, output_dir=output_one, label="任务 1/2"),
                DirectoryTask(input_dir=input_two, output_dir=output_two, label="任务 2/2"),
            ],
            "base_config": AppConfig(work_dir=tmp_path / "work"),
            "engine_factory": FakeEngine,
            "process_directory_func": fake_process_directory,
            "cancel_event": cancel_event,
        },
        daemon=True,
    )

    runner_thread.start()
    assert both_started.wait(timeout=5)
    release.set()
    runner_thread.join(timeout=5)

    assert not runner_thread.is_alive()
    assert {item[0] for item in started} == {input_one, input_two}


def test_process_directory_tasks_uses_independent_work_dirs_and_shared_cancel_event(tmp_path: Path):
    input_one = tmp_path / "input-one"
    input_two = tmp_path / "input-two"
    output_one = tmp_path / "output-one"
    output_two = tmp_path / "output-two"
    input_one.mkdir()
    input_two.mkdir()
    work_dirs = []
    cancel_events = []
    progress_messages = []

    def fake_process_directory(input_dir, output_dir, config, ocr_engine, on_progress, cancel_event=None):
        work_dirs.append(config.work_dir)
        cancel_events.append(cancel_event)
        on_progress("扫描到 0 个文件")
        return []

    cancel_event = threading.Event()

    process_directory_tasks(
        tasks=[
            DirectoryTask(input_dir=input_one, output_dir=output_one, label="任务 1/2"),
            DirectoryTask(input_dir=input_two, output_dir=output_two, label="任务 2/2"),
        ],
        base_config=AppConfig(work_dir=tmp_path / "work"),
        engine_factory=FakeEngine,
        process_directory_func=fake_process_directory,
        on_progress=progress_messages.append,
        cancel_event=cancel_event,
    )

    assert set(work_dirs) == {tmp_path / "work" / "task-1", tmp_path / "work" / "task-2"}
    assert cancel_events == [cancel_event, cancel_event]
    assert any(message.startswith("[任务 1/2]") for message in progress_messages)
    assert any(message.startswith("[任务 2/2]") for message in progress_messages)


def test_process_directory_tasks_isolates_one_group_failure(tmp_path: Path):
    input_one = tmp_path / "input-one"
    input_two = tmp_path / "input-two"
    output_one = tmp_path / "output-one"
    output_two = tmp_path / "output-two"
    input_one.mkdir()
    input_two.mkdir()
    progress_messages = []
    completed = []

    def fake_process_directory(input_dir, output_dir, config, ocr_engine, on_progress, cancel_event=None):
        if input_dir == input_one:
            raise RuntimeError("group failed")
        completed.append(input_dir)
        on_progress("done")
        return []

    results = process_directory_tasks(
        tasks=[
            DirectoryTask(input_dir=input_one, output_dir=output_one, label="task 1/2"),
            DirectoryTask(input_dir=input_two, output_dir=output_two, label="task 2/2"),
        ],
        base_config=AppConfig(work_dir=tmp_path / "work"),
        engine_factory=FakeEngine,
        process_directory_func=fake_process_directory,
        on_progress=progress_messages.append,
    )

    assert results == []
    assert completed == [input_two]
    assert any("group failed" in message for message in progress_messages)


def test_process_directory_tasks_reads_expected_codes_per_task(tmp_path: Path, monkeypatch):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    expected_path = tmp_path / "expected.txt"
    input_dir.mkdir()
    expected_path.write_text("HNKU6331795\n", encoding="utf-8")
    calls = []

    import waybill_ocr.ui.task_runner as task_runner_module

    monkeypatch.setattr(task_runner_module, "read_expected_codes", lambda path: ["HNKU6331795"])

    def fake_process_directory(*args, **kwargs):
        calls.append(kwargs)
        return []

    process_directory_tasks(
        tasks=[DirectoryTask(input_dir=input_dir, output_dir=output_dir, label="task", expected_codes_path=expected_path)],
        base_config=AppConfig(work_dir=tmp_path / "work"),
        engine_factory=FakeEngine,
        process_directory_func=fake_process_directory,
    )

    assert calls[0]["expected_codes"] == ["HNKU6331795"]

