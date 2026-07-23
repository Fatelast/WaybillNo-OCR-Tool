from pathlib import Path
from types import SimpleNamespace

def test_main_window_imports_diagnostics_helpers():
    from waybill_ocr.ui import main_window

    assert main_window.inspect_environment is not None
    assert main_window.format_diagnostic_messages is not None



def test_main_window_layout_keeps_task_area_compact_for_log_visibility():
    from waybill_ocr.ui import main_window
    source = (Path(__file__).resolve().parents[1] / "src" / "waybill_ocr" / "ui" / "main_window.py").read_text(encoding="utf-8")

    assert "progress_cell" in source
    assert main_window.WINDOW_DEFAULT_GEOMETRY == "1040x840"
    assert main_window.WINDOW_MIN_SIZE == (920, 800)
    assert main_window.LOG_SECTION_MIN_HEIGHT == 180
    assert "height=16" in source
    assert "speed_controls = tk.Frame(speed_box, bg=BG_COLOR)" in source


def test_button_motion_uses_shared_hover_and_press_feedback():
    from waybill_ocr.ui import main_window

    source = Path(main_window.__file__).read_text(encoding="utf-8")

    assert main_window._blend_hex_color("#000000", "#FFFFFF", 0.5) == "#808080"
    assert main_window._darken_hex_color("#808080") == "#717171"
    assert main_window.BUTTON_MOTION_STEPS == 5
    assert main_window.BUTTON_MOTION_DELAY_MS == 32
    assert "self._animate_fill(self._active_fill)" in source
    assert "self._animate_fill(self._press_fill, steps=2, delay=16)" in source
    assert "RoundedButton(" in source


def test_rounded_menu_buttons_attach_menus_to_inner_controls():
    from waybill_ocr.ui import main_window

    source = Path(main_window.__file__).read_text(encoding="utf-8")

    assert "menu = tk.Menu(button.control, tearoff=False" in source
    assert "tk.Menu(self.advanced_tools_button.control, tearoff=False" in source
    assert "button.configure(menu=menu)" in source
    assert "self.advanced_tools_button.configure(menu=self.advanced_tools_menu)" in source
    assert "self.speed_menu.grid(row=0, column=1)" in source
    assert "输出目录可不选" in source
    assert "\u9009\u62e9\u6587\u4ef6\uff0c\u4e0d\u662f\u6587\u4ef6\u5939" not in source
    assert "\\u975e\\u5fc5\\u9009" not in source
    assert "\\u9884\\u671f\\u7bb1\\u53f7\\u6e05\\u5355\\uff08\\u53ef\\u9009\\uff09" in source


def test_startup_keeps_fields_empty_but_browsers_use_recent_directories(tmp_path: Path):
    from waybill_ocr.ui import main_window

    source = Path(main_window.__file__).read_text(encoding="utf-8")
    recent_input = tmp_path / "recent-input"
    recent_input.mkdir()
    recent_list = tmp_path / "expected.txt"
    recent_list.write_text("GESU5903360\n", encoding="utf-8")
    window = SimpleNamespace(
        preferences={
            "input_dir": str(recent_input),
            "expected_path": str(recent_list),
        }
    )

    assert "_restore_recent_paths" not in source
    assert main_window.MainWindow._recent_dir(window, "input_dir") == str(recent_input)
    assert main_window.MainWindow._recent_dir(window, "expected_path") == str(tmp_path)


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

def test_main_window_uses_structured_progress_events_for_task_state():
    source = (Path(__file__).resolve().parents[1] / "src" / "waybill_ocr" / "ui" / "main_window.py").read_text(encoding="utf-8")

    assert "on_progress_event=progress_handler" in source
    assert "progress_handler = self._handle_task_progress_event" in source
    assert "_update_task_progress_from_message" not in source
    assert "re.match" not in source



def test_expected_status_preview_shows_sample_codes(monkeypatch):
    from waybill_ocr.container_code.expected_codes import ExpectedCodeInspection
    from waybill_ocr.ui import main_window

    row = {
        "expected_status_var": FakeVar(),
        "expected_status_label": SimpleNamespace(config=lambda **_kwargs: None),
    }
    window = SimpleNamespace(task_rows=[row])
    monkeypatch.setattr(
        main_window,
        "inspect_expected_codes",
        lambda _path: ExpectedCodeInspection(
            valid_codes=["HNKU6331795", "GESU5903360", "MSCU1234566", "YYCU6003610"],
            duplicate_codes=["HNKU6331795"],
            invalid_entries=["BAD"],
        ),
    )

    main_window.MainWindow._update_expected_status(window, 0, Path("expected.txt"))

    value = row["expected_status_var"].get()
    assert "\u6709\u6548 4" in value
    assert "\u9884\u89c8 HNKU6331795, GESU5903360, MSCU1234566" in value


def test_main_window_contains_sample_verify_and_result_entry_labels():
    from waybill_ocr.ui import main_window
    source = (Path(__file__).resolve().parents[1] / "src" / "waybill_ocr" / "ui" / "main_window.py").read_text(encoding="utf-8")

    assert "\u6837\u672c\u9a8c\u6536" in source
    assert "\\u6253\\u5f00\\u7ed3\\u679c" in source
    assert "button = RoundedMenubutton(" in source
    assert "progressbar = ttk.Progressbar(" in source
    assert "entry_shell" not in source
    assert "header = tk.Frame(parent, bg=PRIMARY_COLOR, padx=12, pady=10)" in source
    assert "status = tk.Label(" in source
    assert "task_frame = tk.Frame(" in source
    assert "completion_panel = tk.Frame(" in source
    assert "panel = tk.Frame(" in source


    assert "\\u8bc6\\u522b\\u7ed3\\u679c.xlsx" in source
    assert "\\u6b63\\u786e\\u8bc6\\u522b" in source
    assert "\\u672a\\u8bc6\\u522b" in source
    assert "\\u7bb1\\u53f7\\u9519\\u8bef" in source
    assert "result_buttons" not in source
    assert "继续未完成文件（推荐）" in source
    assert "重新识别当前输入内全部文件" in source
    assert "result_menu_button.grid_remove()" in source
    assert main_window.LOG_PLACEHOLDER in source


def test_main_window_uses_native_card_frames_to_avoid_canvas_layering():
    source = (Path(__file__).resolve().parents[1] / "src" / "waybill_ocr" / "ui" / "main_window.py").read_text(encoding="utf-8")

    assert source.count("RoundedPanel(") == 2
    assert "completion_panel = tk.Frame(" in source
    assert "panel = tk.Frame(" in source
    assert "log_frame = RoundedPanel(" in source

def test_gui_theme_uses_accessible_palette_and_log_tags():
    from waybill_ocr.ui import main_window

    assert main_window.BG_COLOR == "#F4FBF9"
    assert main_window.PRIMARY_COLOR == "#257D80"
    assert main_window.BUTTON_BROWSE == "#96B99E"
    assert main_window.BUTTON_SAMPLE == "#F5B98B"
    assert main_window.BUTTON_START == "#9CD366"
    assert main_window.DANGER_COLOR == "#E3887B"
    assert main_window.SECONDARY_FG == "#FFFFFF"
    assert main_window.LOG_BG == "#262521"
    assert main_window.LOG_FG == "#F1E3CD"
    assert main_window.LOG_ERROR_FG == "#DD8E75"
    assert main_window._log_tag_for_message("\u5904\u7406\u4e2d\uff1a1/10") == "info"
    assert main_window._log_tag_for_message("\u5904\u7406\u5931\u8d25\uff1a\u6587\u4ef6\u65e0\u6cd5\u8bfb\u53d6") == "error"




def test_collapsed_second_task_is_not_collected(monkeypatch):
    from waybill_ocr.ui import main_window

    input_one = Path("D:/OCRTool/test-parent/input-one")
    input_two = Path("D:/OCRTool/test-parent/input-two")
    rows = [_task_row(input_path=input_one), _task_row(input_path=input_two)]
    errors = []
    existing_dirs = {input_one, input_two}
    monkeypatch.setattr(main_window.messagebox, "showerror", lambda title, message: errors.append((title, message)))
    monkeypatch.setattr(main_window.Path, "is_dir", lambda self: self in existing_dirs)
    window = SimpleNamespace(task_rows=rows, task_two_expanded=False)

    tasks = main_window.MainWindow._collect_tasks(window)

    assert errors == []
    assert tasks is not None
    assert len(tasks) == 1
    assert tasks[0].input_dir == input_one


def test_default_output_suggestion_preserves_manual_output():
    from waybill_ocr.ui import main_window

    first_input = Path("D:/OCRTool/test-parent/input-one")
    second_input = Path("D:/OCRTool/test-parent/input-two")
    manual_output = Path("D:/OCRTool/test-parent/manual-output")
    row = _task_row()
    row["auto_output_dir"] = None
    window = SimpleNamespace(task_rows=[row])

    suggested = main_window.MainWindow._set_default_output_for_input(window, 0, first_input)
    assert suggested == first_input.parent / "input-one_\u8bc6\u522b\u8f93\u51fa"
    assert row["output_var"].get() == str(suggested)

    row["output_var"].set(str(manual_output))
    row["auto_output_dir"] = None
    selected = main_window.MainWindow._set_default_output_for_input(window, 0, second_input)

    assert selected == manual_output
    assert row["output_var"].get() == str(manual_output)


def test_completion_summary_combines_review_counts():
    from waybill_ocr.ui import main_window

    state = {
        "success": 8,
        "unrecognized": 2,
        "invalid": 1,
        "started_at": 10.0,
        "finished_at": 75.0,
    }

    assert main_window._completion_summary(state) == "\u5904\u7406\u7ed3\u675f\uff1a\u6210\u529f 8 | \u5f85\u590d\u6838 3 | \u7528\u65f6 01:05"


def test_main_window_keeps_expected_list_visible_and_removes_duplicate_review_entry():
    from waybill_ocr.ui import main_window

    source = Path(main_window.__file__).read_text(encoding="utf-8")

    assert "task_two_toggle_button" in source
    assert "advanced_tools_button" in source
    assert "advanced_tools_menu.add_command" in source
    assert "advanced_toggle_button" not in source
    assert "advanced_panel" not in source
    assert "expected_status_label.grid_remove()" not in source
    assert "\\u6279\\u91cf\\u786e\\u8ba4\\u5e76\\u6574\\u7406" not in source
    assert "self.advanced_tools_button.grid(row=0, column=1" in source
    assert 'add_command(label="样本验收"' not in source
    assert 'add_command(label="环境检查"' in source
    assert 'add_command(label="导出诊断信息"' in source

class FakeWidget:
    def __init__(self) -> None:
        self.options = {}
        self.visible = False

    def config(self, **kwargs) -> None:
        self.options.update(kwargs)

    def grid(self, **_kwargs) -> None:
        self.visible = True

    def grid_remove(self) -> None:
        self.visible = False


def _ready_task_row(
    input_path: Path | str = "",
    output_path: Path | str = "",
    expected_path: Path | str = "",
    *,
    input_ready: bool = False,
    supported_file_count: int = 0,
    output_valid: bool = True,
    expected_valid: bool = True,
):
    row = _task_row(input_path, output_path, expected_path)
    row.update(
        {
            "input_ready": input_ready,
            "supported_file_count": supported_file_count,
            "output_valid": output_valid,
            "expected_valid": expected_valid,
            "output_status_var": FakeVar(),
            "output_status_label": FakeWidget(),
        }
    )
    return row


def test_start_readiness_requires_a_scanned_supported_file():
    from waybill_ocr.ui.main_window import _tasks_ready_for_start

    row = _ready_task_row("D:/input", "D:/output")
    assert not _tasks_ready_for_start([row], task_two_expanded=False)

    row["input_ready"] = True
    row["supported_file_count"] = 1
    assert _tasks_ready_for_start([row], task_two_expanded=False)


def test_start_readiness_ignores_collapsed_second_task_but_checks_it_when_expanded():
    from waybill_ocr.ui.main_window import _tasks_ready_for_start

    first = _ready_task_row(
        "D:/input-one",
        "D:/output-one",
        input_ready=True,
        supported_file_count=2,
    )
    incomplete_second = _ready_task_row(output_path="D:/output-two")

    assert _tasks_ready_for_start([first, incomplete_second], task_two_expanded=False)
    assert not _tasks_ready_for_start([first, incomplete_second], task_two_expanded=True)


def test_duplicate_output_paths_are_reported_inline(tmp_path: Path):
    from types import MethodType

    import tkinter as tk

    from waybill_ocr.ui import main_window

    input_one = tmp_path / "input-one"
    input_two = tmp_path / "input-two"
    shared_output = tmp_path / "shared-output"
    input_one.mkdir()
    input_two.mkdir()
    rows = [
        _ready_task_row(input_one, shared_output, input_ready=True, supported_file_count=1),
        _ready_task_row(input_two, shared_output, input_ready=True, supported_file_count=1),
    ]
    start_button = FakeWidget()
    window = SimpleNamespace(
        task_rows=rows,
        task_two_expanded=True,
        running=False,
        start_button=start_button,
    )
    window._set_output_error = MethodType(main_window.MainWindow._set_output_error, window)
    window._refresh_start_button_state = MethodType(main_window.MainWindow._refresh_start_button_state, window)

    main_window.MainWindow._validate_output_paths(window)

    assert all(not row["output_valid"] for row in rows)
    assert all(row["output_status_label"].visible for row in rows)
    assert all("\u8f93\u51fa\u6587\u4ef6\u5939\u4e0d\u80fd\u76f8\u540c" in row["output_status_var"].get() for row in rows)
    assert start_button.options["state"] == tk.DISABLED


def test_expected_list_hint_explains_that_results_are_not_overwritten():
    from waybill_ocr.ui import main_window

    assert "\u7f3a\u5931\u6838\u5bf9" in main_window.EXPECTED_LIST_HINT
    assert "\u5f85\u786e\u8ba4\u8f85\u52a9\u6574\u7406" in main_window.EXPECTED_LIST_HINT
    assert "\u4e0d\u4f1a\u76f4\u63a5\u6539\u4e3a\u6b63\u786e\u8bc6\u522b" in main_window.EXPECTED_LIST_HINT


def test_start_readiness_reports_scanning_empty_invalid_and_ready_states():
    from waybill_ocr.ui.main_window import _start_readiness_state

    row = _ready_task_row("D:/input", "D:/output")
    row["input_scanning"] = True
    ready, message = _start_readiness_state([row], task_two_expanded=False)
    assert not ready
    assert "正在检查任务 1" in message

    row["input_scanning"] = False
    row["last_scanned_input"] = "D:/input"
    ready, message = _start_readiness_state([row], task_two_expanded=False)
    assert not ready
    assert "未发现可处理文件" in message

    row["input_ready"] = True
    row["supported_file_count"] = 3
    row["expected_valid"] = False
    ready, message = _start_readiness_state([row], task_two_expanded=False)
    assert not ready
    assert "红色提示" in message

    row["expected_valid"] = True
    ready, message = _start_readiness_state([row], task_two_expanded=False)
    assert ready
    assert "准备就绪，共 3 个文件" in message


def test_existing_result_outputs_only_returns_tasks_with_workbooks(tmp_path: Path):
    from waybill_ocr.constants import RESULT_WORKBOOK_NAME
    from waybill_ocr.ui.main_window import _existing_result_outputs
    from waybill_ocr.ui.task_runner import DirectoryTask

    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / RESULT_WORKBOOK_NAME).write_bytes(b"xlsx")
    tasks = [
        DirectoryTask(tmp_path / "input-one", first, "task one"),
        DirectoryTask(tmp_path / "input-two", second, "task two"),
    ]

    assert _existing_result_outputs(tasks) == [first]


def test_safe_organize_button_uses_shared_candidate_count(tmp_path: Path):
    from waybill_ocr.ui import main_window
    from waybill_ocr.ui.task_runner import DirectoryTask

    output_dir = tmp_path / "output"
    review_dir = output_dir / "未识别"
    review_dir.mkdir(parents=True)
    (review_dir / "GESU5903360-待确认.pdf").write_bytes(b"pdf")
    expected_path = tmp_path / "expected.txt"
    expected_path.write_text("GESU5903360\n", encoding="utf-8")
    button = FakeWidget()
    row = {"safe_organize_button": button}
    task = DirectoryTask(tmp_path / "input", output_dir, "task", expected_path)
    window = SimpleNamespace(task_rows=[row], active_tasks=[task])

    main_window.MainWindow._refresh_safe_organize_button(window, 0, output_dir)

    assert button.visible
    assert button.options["text"] == "安全整理（1）"

    invalid_dir = output_dir / "箱号错误"
    invalid_dir.mkdir()
    (invalid_dir / "GESU5903360-待确认-1.pdf").write_bytes(b"pdf")
    main_window.MainWindow._refresh_safe_organize_button(window, 0, output_dir)

    assert not button.visible


def test_task_section_expands_without_internal_scrollbar():
    from waybill_ocr.ui import main_window

    source = Path(main_window.__file__).read_text(encoding="utf-8")

    assert "section = tk.Frame(parent, bg=BG_COLOR)" in source
    assert "section.grid(row=1, column=0, sticky=tk.EW, pady=(12, 0))" in source
    assert "self.task_viewport" not in source
    assert "Task.Vertical.TScrollbar" not in source


def test_stop_and_advanced_tools_controls_follow_processing_state():
    import tkinter as tk

    from waybill_ocr.ui import main_window

    row = {
        key: FakeWidget()
        for key in (
            "input_button",
            "output_button",
            "expected_button",
            "result_menu_button",
            "input_entry",
            "output_entry",
            "expected_entry",
        )
    }
    window = SimpleNamespace(
        start_button=FakeWidget(),
        advanced_tools_button=FakeWidget(),
        stop_button=FakeWidget(),
        speed_menu=FakeWidget(),
        task_two_toggle_button=FakeWidget(),
        action_hint_var=FakeVar(),
        task_rows=[row],
    )
    window._refresh_start_button_state = lambda: None

    main_window.MainWindow._set_idle_controls(window)

    assert window.stop_button.options["state"] == tk.DISABLED
    assert window.stop_button.options["bg"] == main_window.DISABLED_BG
    assert window.stop_button.options["fg"] == main_window.DISABLED_FG
    assert window.advanced_tools_button.options["state"] == tk.NORMAL

    main_window.MainWindow._set_running_controls(window)

    assert window.stop_button.options["state"] == tk.NORMAL
    assert window.stop_button.options["bg"] == main_window.DANGER_COLOR
    assert window.stop_button.options["fg"] == "#FFFFFF"
    assert window.advanced_tools_button.options["state"] == tk.DISABLED


def test_screen_center_geometry_clamps_and_centers_dialog():
    from waybill_ocr.ui.main_window import _screen_center_geometry

    assert _screen_center_geometry(
        width=400, height=300, screen_width=1920, screen_height=1080
    ) == "400x300+760+390"
    assert _screen_center_geometry(
        width=2000, height=1000, screen_width=1280, screen_height=720
    ) == "1280x720+0+0"


def test_secondary_dialogs_are_centered_before_modal_grab():
    from waybill_ocr.ui import main_window

    source = Path(main_window.__file__).read_text(encoding="utf-8")

    assert source.count("dialog.withdraw()") == 2


def test_review_button_visibility_follows_candidate_count(monkeypatch, tmp_path: Path):
    from waybill_ocr.ui import main_window

    output_dir = tmp_path / "output"
    button = FakeWidget()
    window = SimpleNamespace(task_rows=[{"review_button": button}])

    monkeypatch.setattr(main_window, "scan_review_candidates", lambda _output: [])
    main_window.MainWindow._refresh_review_button(window, 0, output_dir)
    assert not button.visible

    monkeypatch.setattr(main_window, "scan_review_candidates", lambda _output: [object(), object()])
    main_window.MainWindow._refresh_review_button(window, 0, output_dir)
    assert button.visible


def test_diagnostic_report_contains_environment_and_log_details():
    from waybill_ocr.config import AppConfig
    from waybill_ocr.ui.main_window import _diagnostic_report_text

    report = _diagnostic_report_text(
        AppConfig(
            tesseract_cmd=Path("D:/runtime/tools/tesseract/tesseract.exe"),
            poppler_path=Path("D:/runtime/tools/poppler"),
        ),
        ["[OK] Pillow 可用", "[缺失] Poppler 不可用"],
        "开始处理\n处理失败: 示例",
        "2026-07-23 17:05:00",
    )

    assert "诊断信息" in report
    assert f"Tesseract 路径: {Path('D:/runtime/tools/tesseract/tesseract.exe')}" in report
    assert "[缺失] Poppler 不可用" in report
    assert "处理失败: 示例" in report
