from pathlib import Path
from types import SimpleNamespace

def test_main_window_imports_diagnostics_helpers():
    from waybill_ocr.ui import main_window

    assert main_window.inspect_environment is not None
    assert main_window.format_diagnostic_messages is not None



def test_main_window_layout_keeps_task_area_compact_for_log_visibility():
    source = (Path(__file__).resolve().parents[1] / "src" / "waybill_ocr" / "ui" / "main_window.py").read_text(encoding="utf-8")

    assert "progress_cell" in source
    assert "height=24" in source
    assert "\u8f93\u5165\u6587\u4ef6\u5939\u540d_\u8bc6\u522b\u8f93\u51fa" in source
    assert "\u9009\u62e9\u6587\u4ef6\uff0c\u4e0d\u662f\u6587\u4ef6\u5939" not in source


class FakeVar:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


def _collect_tasks_from_rows(rows, monkeypatch, existing_dirs=()):
    from waybill_ocr.ui import main_window

    errors = []
    existing_dir_set = {Path(path) for path in existing_dirs}
    monkeypatch.setattr(main_window.messagebox, "showerror", lambda title, message: errors.append((title, message)))
    monkeypatch.setattr(main_window.Path, "is_dir", lambda self: self in existing_dir_set)
    window = SimpleNamespace(task_rows=rows)

    return main_window.MainWindow._collect_tasks(window), errors


def _task_row(input_path: Path | str = "", output_path: Path | str = "", expected_path: Path | str = ""):
    return {
        "input_var": FakeVar(str(input_path) if input_path else ""),
        "output_var": FakeVar(str(output_path) if output_path else ""),
        "expected_var": FakeVar(str(expected_path) if expected_path else ""),
    }


def test_collect_tasks_uses_default_output_dir_when_output_is_empty(monkeypatch):
    from waybill_ocr.ui.main_window import _default_output_dir_for

    input_dir = Path("D:/OCRTool/test-parent/EBR24063034--\u6e05\u5173\u8fd0\u5355")
    row = _task_row(input_path=input_dir)

    tasks, errors = _collect_tasks_from_rows([row], monkeypatch, existing_dirs=[input_dir])

    assert errors == []
    assert tasks is not None
    assert tasks[0].output_dir == _default_output_dir_for(input_dir)
    assert tasks[0].output_dir == input_dir.parent / "EBR24063034--\u6e05\u5173\u8fd0\u5355_\u8bc6\u522b\u8f93\u51fa"
    assert row["output_var"].get() == str(tasks[0].output_dir)


def test_collect_tasks_skips_empty_second_task_and_defaults_second_output(monkeypatch):
    input_one = Path("D:/OCRTool/test-parent/input-one")
    input_two = Path("D:/OCRTool/test-parent/input-two")
    rows = [_task_row(input_path=input_one), _task_row(input_path=input_two)]

    tasks, errors = _collect_tasks_from_rows(rows, monkeypatch, existing_dirs=[input_one, input_two])

    assert errors == []
    assert tasks is not None
    assert [task.output_dir for task in tasks] == [
        input_one.parent / "input-one_\u8bc6\u522b\u8f93\u51fa",
        input_two.parent / "input-two_\u8bc6\u522b\u8f93\u51fa",
    ]


def test_collect_tasks_keeps_manual_output_dir(monkeypatch):
    input_dir = Path("D:/OCRTool/test-parent/input")
    manual_output = Path("D:/OCRTool/test-parent/manual-output")

    tasks, errors = _collect_tasks_from_rows(
        [_task_row(input_path=input_dir, output_path=manual_output)],
        monkeypatch,
        existing_dirs=[input_dir],
    )

    assert errors == []
    assert tasks is not None
    assert tasks[0].output_dir == manual_output


def test_collect_tasks_rejects_output_without_input(monkeypatch):
    output_dir = Path("D:/OCRTool/test-parent/output")

    tasks, errors = _collect_tasks_from_rows([_task_row(output_path=output_dir)], monkeypatch)

    assert tasks is None
    assert len(errors) == 1
    assert "\u8bf7\u5148\u9009\u62e9\u8f93\u5165\u6587\u4ef6\u5939" in errors[0][1]




def test_collect_tasks_rejects_duplicate_manual_output_dirs(monkeypatch):
    input_one = Path("D:/OCRTool/test-parent/input-one")
    input_two = Path("D:/OCRTool/test-parent/input-two")
    output_dir = Path("D:/OCRTool/test-parent/shared-output")
    rows = [
        _task_row(input_path=input_one, output_path=output_dir),
        _task_row(input_path=input_two, output_path=output_dir),
    ]

    tasks, errors = _collect_tasks_from_rows(rows, monkeypatch, existing_dirs=[input_one, input_two])

    assert tasks is None
    assert len(errors) == 1
    assert "\u8f93\u51fa\u6587\u4ef6\u5939\u4e0d\u80fd\u91cd\u590d" in errors[0][1]


def test_collect_tasks_rejects_duplicate_auto_output_dirs_for_same_input(monkeypatch):
    input_dir = Path("D:/OCRTool/test-parent/input-one")
    rows = [_task_row(input_path=input_dir), _task_row(input_path=input_dir)]

    tasks, errors = _collect_tasks_from_rows(rows, monkeypatch, existing_dirs=[input_dir])

    assert tasks is None
    assert len(errors) == 1
    assert "\u8f93\u51fa\u6587\u4ef6\u5939\u4e0d\u80fd\u91cd\u590d" in errors[0][1]


def test_speed_mode_description_updates_for_fast_mode():
    from waybill_ocr.ui import main_window

    window = SimpleNamespace(
        speed_mode_var=FakeVar(main_window.SPEED_MODE_LABELS[main_window.OCR_SPEED_FAST]),
        speed_description_var=FakeVar(),
    )

    main_window.MainWindow._update_speed_description(window)

    assert "清晰文件" in window.speed_description_var.get()
    assert "待确认" in window.speed_description_var.get()


def test_speed_mode_description_defaults_to_balanced():
    from waybill_ocr.ui import main_window

    assert "默认推荐" in main_window._speed_mode_description(main_window.OCR_SPEED_BALANCED)

def test_speed_mode_descriptions_are_user_scenario_based():
    from waybill_ocr.ui import main_window

    assert "清晰文件" in main_window.SPEED_MODE_DESCRIPTIONS[main_window.OCR_SPEED_FAST]
    assert "默认推荐" in main_window.SPEED_MODE_DESCRIPTIONS[main_window.OCR_SPEED_BALANCED]
    assert "模糊" in main_window.SPEED_MODE_DESCRIPTIONS[main_window.OCR_SPEED_STABLE]
    assert "PSM" not in main_window.SPEED_MODE_DESCRIPTIONS[main_window.OCR_SPEED_STABLE]
