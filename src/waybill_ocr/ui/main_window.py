import os
import re
import threading
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from waybill_ocr.config import (
    OCR_SPEED_BALANCED,
    OCR_SPEED_FAST,
    OCR_SPEED_STABLE,
    default_config,
    resolve_default_work_dir,
)
from waybill_ocr.container_code.expected_codes import inspect_expected_codes
from waybill_ocr.delivery import APP_NAME, CURRENT_VERSION
from waybill_ocr.diagnostics import format_diagnostic_messages, inspect_environment
from waybill_ocr.ocr.tesseract_engine import TesseractEngine
from waybill_ocr.ui.task_runner import DirectoryTask, process_directory_tasks

MAX_TASKS = 2

BG_COLOR = "#f4f7fb"
SURFACE_COLOR = "#ffffff"
SURFACE_MUTED = "#f8fafc"
BORDER_COLOR = "#d7dee9"
TEXT_COLOR = "#172033"
MUTED_TEXT_COLOR = "#667085"
PRIMARY_COLOR = "#2563eb"
PRIMARY_HOVER = "#1d4ed8"
DANGER_COLOR = "#dc2626"
DANGER_HOVER = "#b91c1c"
LOG_BG = "#0f172a"
LOG_FG = "#dbeafe"
DISABLED_BG = "#e5e7eb"
FONT_FAMILY = "Microsoft YaHei UI"
SPEED_MODE_LABELS = {
    OCR_SPEED_STABLE: "\u7a33\u5b9a\u6a21\u5f0f",
    OCR_SPEED_BALANCED: "\u5747\u8861\u6a21\u5f0f",
    OCR_SPEED_FAST: "\u5feb\u901f\u6a21\u5f0f",
}
SPEED_MODE_VALUES = {label: mode for mode, label in SPEED_MODE_LABELS.items()}


class MainWindow:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} {CURRENT_VERSION}")
        self.root.geometry("1040x740")
        self.root.minsize(920, 680)
        self.root.configure(bg=BG_COLOR)

        self.task_rows = []
        self.progress_var = tk.StringVar(value="待处理")
        self.speed_mode_var = tk.StringVar(value=SPEED_MODE_LABELS[OCR_SPEED_BALANCED])
        self.running = False
        self.cancel_event: threading.Event | None = None

        self._configure_style()
        self._build_layout()

    def run(self) -> None:
        self.root.mainloop()

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Vertical.TScrollbar", background="#cbd5e1", troughcolor="#1e293b", bordercolor="#1e293b")
        style.configure("Horizontal.TProgressbar", troughcolor="#e2e8f0", background=PRIMARY_COLOR, bordercolor="#e2e8f0")

    def _build_layout(self) -> None:
        page = tk.Frame(self.root, bg=BG_COLOR, padx=14, pady=12)
        page.pack(fill=tk.BOTH, expand=True)
        page.columnconfigure(0, weight=1)
        page.rowconfigure(3, weight=1)

        self._build_header(page)
        self._build_task_section(page)
        self._build_actions(page)
        self._build_log_section(page)

    def _build_header(self, parent: tk.Frame) -> None:
        header = tk.Frame(parent, bg=PRIMARY_COLOR, padx=16, pady=12)
        header.grid(row=0, column=0, sticky=tk.EW)
        header.columnconfigure(0, weight=1)

        tk.Label(
            header,
            text=f"{APP_NAME} {CURRENT_VERSION}",
            bg=PRIMARY_COLOR,
            fg="#ffffff",
            font=(FONT_FAMILY, 16, "bold"),
        ).grid(row=0, column=0, sticky=tk.W)
        tk.Label(
            header,
            text="最多两组文件夹并行处理，支持预期箱号清单比对与结果表增量写入",
            bg=PRIMARY_COLOR,
            fg="#dbeafe",
            font=(FONT_FAMILY, 9),
        ).grid(row=1, column=0, sticky=tk.W, pady=(4, 0))

        status = tk.Label(
            header,
            textvariable=self.progress_var,
            bg="#1e40af",
            fg="#ffffff",
            padx=12,
            pady=5,
            font=(FONT_FAMILY, 8, "bold"),
        )
        status.grid(row=0, column=1, rowspan=2, sticky=tk.E, padx=(18, 0))

    def _build_task_section(self, parent: tk.Frame) -> None:
        section = tk.Frame(parent, bg=BG_COLOR)
        section.grid(row=1, column=0, sticky=tk.EW, pady=(10, 0))
        section.columnconfigure(0, weight=1)

        for index in range(MAX_TASKS):
            task_frame = tk.Frame(
                section,
                bg=SURFACE_COLOR,
                padx=12,
                pady=8,
                highlightbackground=BORDER_COLOR,
                highlightthickness=1,
            )
            task_frame.grid(row=index, column=0, sticky=tk.EW, pady=(0, 6))
            task_frame.columnconfigure(1, weight=1)

            input_var = tk.StringVar()
            output_var = tk.StringVar()
            expected_var = tk.StringVar()
            badge_text = "必填" if index == 0 else "可选"
            badge_bg = "#dbeafe" if index == 0 else "#eef2f7"
            badge_fg = PRIMARY_COLOR if index == 0 else MUTED_TEXT_COLOR

            tk.Label(
                task_frame,
                text=f"任务 {index + 1}",
                bg=SURFACE_COLOR,
                fg=TEXT_COLOR,
                font=(FONT_FAMILY, 10, "bold"),
            ).grid(row=0, column=0, sticky=tk.W, pady=(0, 6))
            tk.Label(
                task_frame,
                text=badge_text,
                bg=badge_bg,
                fg=badge_fg,
                padx=7,
                pady=2,
                font=(FONT_FAMILY, 8, "bold"),
            ).grid(row=0, column=1, sticky=tk.W, pady=(0, 6))

            input_entry, input_button = self._build_path_field(
                task_frame,
                1,
                "输入文件夹",
                input_var,
                lambda task_index=index: self._choose_input(task_index),
            )
            output_entry, output_button = self._build_path_field(
                task_frame,
                2,
                "输出文件夹",
                output_var,
                lambda task_index=index: self._choose_output(task_index),
            )
            expected_entry, expected_button = self._build_path_field(
                task_frame,
                3,
                "预期箱号清单（非必选）",
                expected_var,
                lambda task_index=index: self._choose_expected(task_index),
            )
            tk.Label(
                task_frame,
                text="选择文件，不是文件夹。支持 .txt / .csv / .xlsx；推荐每行一个箱号，例如 GESU5903360。",
                bg=SURFACE_COLOR,
                fg=MUTED_TEXT_COLOR,
                font=(FONT_FAMILY, 8),
                anchor=tk.W,
            ).grid(row=4, column=1, columnspan=2, sticky=tk.W, padx=(8, 0), pady=(0, 1))

            expected_status_var = tk.StringVar(value="\u9884\u671f\u6e05\u5355\uff1a\u975e\u5fc5\u9009")
            expected_status_label = tk.Label(
                task_frame,
                textvariable=expected_status_var,
                bg=SURFACE_COLOR,
                fg=MUTED_TEXT_COLOR,
                font=(FONT_FAMILY, 8),
                anchor=tk.W,
            )
            expected_status_label.grid(row=5, column=1, columnspan=2, sticky=tk.W, padx=(8, 0), pady=(0, 3))

            progress_text_var = tk.StringVar(value="\u5f85\u5904\u7406")
            summary_var = tk.StringVar(value="\u5df2\u5904\u7406 0/0 | \u6210\u529f 0 | \u672a\u8bc6\u522b 0 | \u7bb1\u53f7\u9519\u8bef 0")
            tk.Label(
                task_frame,
                textvariable=progress_text_var,
                bg=SURFACE_COLOR,
                fg=TEXT_COLOR,
                font=(FONT_FAMILY, 8, "bold"),
                anchor=tk.W,
            ).grid(row=6, column=0, sticky=tk.W, pady=(3, 1))
            tk.Label(
                task_frame,
                textvariable=summary_var,
                bg=SURFACE_COLOR,
                fg=MUTED_TEXT_COLOR,
                font=(FONT_FAMILY, 8),
                anchor=tk.W,
            ).grid(row=6, column=1, sticky=tk.W, padx=(8, 0), pady=(3, 1))
            progressbar = ttk.Progressbar(task_frame, mode="determinate", maximum=1, value=0, style="Horizontal.TProgressbar")
            progressbar.grid(row=7, column=0, columnspan=2, sticky=tk.EW, pady=(1, 0))
            open_button = tk.Button(
                task_frame,
                text="\u6253\u5f00\u8f93\u51fa",
                command=lambda task_index=index: self._open_output(task_index),
                bg="#eef4ff",
                fg=PRIMARY_COLOR,
                activebackground="#dbeafe",
                activeforeground=PRIMARY_HOVER,
                disabledforeground="#ffffff",
                relief=tk.FLAT,
                cursor="arrow",
                padx=10,
                pady=4,
                font=(FONT_FAMILY, 8, "bold"),
                state=tk.DISABLED,
            )
            open_button.grid(row=7, column=2, sticky=tk.E, pady=(1, 0))

            self.task_rows.append(
                {
                    "input_var": input_var,
                    "output_var": output_var,
                    "expected_var": expected_var,
                    "expected_status_var": expected_status_var,
                    "expected_status_label": expected_status_label,
                    "progress_text_var": progress_text_var,
                    "summary_var": summary_var,
                    "progressbar": progressbar,
                    "open_button": open_button,
                    "input_entry": input_entry,
                    "output_entry": output_entry,
                    "expected_entry": expected_entry,
                    "input_button": input_button,
                    "output_button": output_button,
                    "expected_button": expected_button,
                }
            )

    def _build_path_field(
        self,
        parent: tk.Frame,
        row: int,
        label_text: str,
        variable: tk.StringVar,
        command,
    ) -> tuple[tk.Entry, tk.Button]:
        tk.Label(
            parent,
            text=label_text,
            bg=SURFACE_COLOR,
            fg=MUTED_TEXT_COLOR,
            font=(FONT_FAMILY, 8),
            width=16,
            anchor=tk.W,
        ).grid(row=row, column=0, sticky=tk.W, pady=2)

        entry = tk.Entry(
            parent,
            textvariable=variable,
            bg=SURFACE_MUTED,
            fg=TEXT_COLOR,
            relief=tk.FLAT,
            insertbackground=TEXT_COLOR,
            font=(FONT_FAMILY, 8),
            highlightbackground=BORDER_COLOR,
            highlightcolor=PRIMARY_COLOR,
            highlightthickness=1,
        )
        entry.grid(row=row, column=1, sticky=tk.EW, padx=(8, 8), pady=3, ipady=4)

        button = tk.Button(
            parent,
            text="浏览",
            command=command,
            bg="#eef4ff",
            fg=PRIMARY_COLOR,
            activebackground="#dbeafe",
            activeforeground=PRIMARY_HOVER,
            relief=tk.FLAT,
            cursor="hand2",
            padx=12,
            pady=5,
            font=(FONT_FAMILY, 8, "bold"),
        )
        button.grid(row=row, column=2, sticky=tk.E, pady=3)
        return entry, button

    def _build_actions(self, parent: tk.Frame) -> None:
        actions = tk.Frame(parent, bg=BG_COLOR)
        actions.grid(row=2, column=0, sticky=tk.EW, pady=(0, 8))
        actions.columnconfigure(0, weight=1)

        hint = tk.Label(
            actions,
            text="运行中会锁定路径选择；如需切换目录，请先停止当前任务。",
            bg=BG_COLOR,
            fg=MUTED_TEXT_COLOR,
            font=(FONT_FAMILY, 8),
        )
        hint.grid(row=0, column=0, sticky=tk.W)

        button_box = tk.Frame(actions, bg=BG_COLOR)
        button_box.grid(row=0, column=1, sticky=tk.E)
        speed_box = tk.Frame(button_box, bg=BG_COLOR)
        speed_box.grid(row=0, column=0, padx=(0, 10))
        tk.Label(
            speed_box,
            text="\u901f\u5ea6\u6a21\u5f0f",
            bg=BG_COLOR,
            fg=MUTED_TEXT_COLOR,
            font=(FONT_FAMILY, 8),
        ).grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        self.speed_menu = tk.OptionMenu(
            speed_box,
            self.speed_mode_var,
            SPEED_MODE_LABELS[OCR_SPEED_STABLE],
            SPEED_MODE_LABELS[OCR_SPEED_BALANCED],
            SPEED_MODE_LABELS[OCR_SPEED_FAST],
        )
        self.speed_menu.config(
            bg=SURFACE_COLOR,
            fg=TEXT_COLOR,
            activebackground="#dbeafe",
            activeforeground=PRIMARY_HOVER,
            relief=tk.FLAT,
            cursor="hand2",
            padx=7,
            pady=5,
            font=(FONT_FAMILY, 8),
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
        )
        self.speed_menu["menu"].config(font=(FONT_FAMILY, 8))
        self.speed_menu.grid(row=0, column=1, sticky=tk.E)
        self.start_button = tk.Button(
            button_box,
            text="开始处理",
            command=self._start,
            bg=PRIMARY_COLOR,
            fg="#ffffff",
            activebackground=PRIMARY_HOVER,
            activeforeground="#ffffff",
            relief=tk.FLAT,
            cursor="hand2",
            padx=22,
            pady=8,
            font=(FONT_FAMILY, 9, "bold"),
        )
        self.start_button.grid(row=0, column=1, padx=(0, 8))
        self.stop_button = tk.Button(
            button_box,
            text="停止处理",
            command=self._stop,
            bg=DANGER_COLOR,
            fg="#ffffff",
            activebackground=DANGER_HOVER,
            activeforeground="#ffffff",
            disabledforeground="#ffffff",
            relief=tk.FLAT,
            cursor="hand2",
            padx=18,
            pady=8,
            font=(FONT_FAMILY, 9, "bold"),
            state=tk.DISABLED,
        )
        self.stop_button.grid(row=0, column=2)

    def _build_log_section(self, parent: tk.Frame) -> None:
        panel = tk.Frame(
            parent,
            bg=SURFACE_COLOR,
            padx=10,
            pady=8,
            highlightbackground=BORDER_COLOR,
            highlightthickness=1,
        )
        panel.grid(row=3, column=0, sticky=tk.NSEW)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(1, weight=1)

        tk.Label(
            panel,
            text="处理日志",
            bg=SURFACE_COLOR,
            fg=TEXT_COLOR,
            font=(FONT_FAMILY, 10, "bold"),
        ).grid(row=0, column=0, sticky=tk.W, pady=(0, 6))
        tk.Label(
            panel,
            text="实时显示环境检查、识别进度、失败原因和箱号比对结果",
            bg=SURFACE_COLOR,
            fg=MUTED_TEXT_COLOR,
            font=(FONT_FAMILY, 8),
        ).grid(row=0, column=0, sticky=tk.E, pady=(0, 6))

        log_frame = tk.Frame(panel, bg=LOG_BG, highlightbackground="#1e293b", highlightthickness=1)
        log_frame.grid(row=1, column=0, sticky=tk.NSEW)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(
            log_frame,
            height=24,
            wrap=tk.NONE,
            bg=LOG_BG,
            fg=LOG_FG,
            insertbackground=LOG_FG,
            relief=tk.FLAT,
            padx=10,
            pady=8,
            font=("Consolas", 9),
        )
        log_scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        self.log_text.grid(row=0, column=0, sticky=tk.NSEW)
        log_scrollbar.grid(row=0, column=1, sticky=tk.NS)

    def _choose_input(self, task_index: int) -> None:
        if self.running:
            return
        path = filedialog.askdirectory()
        if path:
            self.task_rows[task_index]["input_var"].set(path)

    def _choose_output(self, task_index: int) -> None:
        if self.running:
            return
        path = filedialog.askdirectory()
        if path:
            self.task_rows[task_index]["output_var"].set(path)

    def _choose_expected(self, task_index: int) -> None:
        if self.running:
            return
        path = filedialog.askopenfilename(
            filetypes=[("清单文件", "*.txt *.csv *.xlsx"), ("所有文件", "*.*")]
        )
        if path:
            self.task_rows[task_index]["expected_var"].set(path)
            self._update_expected_status(task_index, Path(path))

    def _start(self) -> None:
        if self.running:
            return

        tasks = self._collect_tasks()
        if tasks is None:
            return

        self._reset_task_progress(tasks)
        self.running = True
        self.cancel_event = threading.Event()
        self._set_running_controls()
        self._append_log("开始处理")
        thread = threading.Thread(target=self._process, args=(tasks, self.cancel_event), daemon=True)
        thread.start()

    def _collect_tasks(self) -> list[DirectoryTask] | None:
        raw_tasks = []
        for index, row in enumerate(self.task_rows):
            input_text = row["input_var"].get().strip()
            output_text = row["output_var"].get().strip()
            expected_text = row["expected_var"].get().strip()
            if index > 0 and not input_text and not output_text:
                continue
            if not input_text or not output_text:
                messagebox.showerror("错误", f"任务 {index + 1} 已选择输入或输出文件夹，请同时填写另一个文件夹")
                return None

            input_dir = Path(input_text)
            output_dir = Path(output_text)
            expected_path = Path(expected_text) if expected_text else None
            if not input_dir.is_dir():
                messagebox.showerror("错误", f"任务 {index + 1} 输入文件夹不存在")
                return None
            if expected_path is not None and not expected_path.is_file():
                messagebox.showerror("错误", f"任务 {index + 1} 预期箱号清单不存在")
                return None
            if _is_input_inside_output(input_dir, output_dir):
                messagebox.showerror("错误", f"任务 {index + 1} 的输入文件夹不能在输出文件夹内")
                return None
            raw_tasks.append((input_dir, output_dir, expected_path))

        if not raw_tasks:
            messagebox.showerror("错误", "请至少填写任务 1 的输入和输出文件夹")
            return None

        total = len(raw_tasks)
        return [
            DirectoryTask(
                input_dir=input_dir,
                output_dir=output_dir,
                label=f"任务 {index}/{total}",
                expected_codes_path=expected_path,
            )
            for index, (input_dir, output_dir, expected_path) in enumerate(raw_tasks, start=1)
        ]

    def _stop(self) -> None:
        if not self.running or self.cancel_event is None:
            return

        self.cancel_event.set()
        self.stop_button.config(state=tk.DISABLED, bg=DISABLED_BG, cursor="arrow")
        self._append_log("正在停止...")

    def _process(self, tasks: list[DirectoryTask], cancel_event: threading.Event) -> None:
        try:
            config = self._config_for_speed(default_config(work_dir=resolve_default_work_dir()))
            for message in format_diagnostic_messages(inspect_environment(config)):
                self._append_log(message)
            process_directory_tasks(
                tasks=tasks,
                base_config=config,
                engine_factory=TesseractEngine,
                on_progress=self._append_log,
                cancel_event=cancel_event,
                max_workers=self._max_workers_for_speed(),
            )
        except Exception as exc:
            self._append_log(f"处理失败: {exc}")
        finally:
            self.root.after(0, self._finish)

    def _finish(self) -> None:
        self.running = False
        self.cancel_event = None
        self._set_idle_controls()
        self._enable_output_buttons()

    def _set_running_controls(self) -> None:
        self.start_button.config(state=tk.DISABLED, bg=DISABLED_BG, cursor="arrow")
        self.stop_button.config(state=tk.NORMAL, bg=DANGER_COLOR, cursor="hand2")
        self.speed_menu.config(state=tk.DISABLED, bg=DISABLED_BG, fg="#ffffff", cursor="arrow")
        for row in self.task_rows:
            row["input_button"].config(state=tk.DISABLED, bg=DISABLED_BG, fg="#ffffff", cursor="arrow")
            row["output_button"].config(state=tk.DISABLED, bg=DISABLED_BG, fg="#ffffff", cursor="arrow")
            row["expected_button"].config(state=tk.DISABLED, bg=DISABLED_BG, fg="#ffffff", cursor="arrow")
            row["open_button"].config(state=tk.DISABLED, bg=DISABLED_BG, fg="#ffffff", cursor="arrow")
            row["input_entry"].config(state=tk.DISABLED, disabledbackground="#eef2f7", disabledforeground=MUTED_TEXT_COLOR)
            row["output_entry"].config(state=tk.DISABLED, disabledbackground="#eef2f7", disabledforeground=MUTED_TEXT_COLOR)
            row["expected_entry"].config(state=tk.DISABLED, disabledbackground="#eef2f7", disabledforeground=MUTED_TEXT_COLOR)

    def _set_idle_controls(self) -> None:
        self.start_button.config(state=tk.NORMAL, bg=PRIMARY_COLOR, cursor="hand2")
        self.stop_button.config(state=tk.DISABLED, bg=DISABLED_BG, cursor="arrow")
        self.speed_menu.config(state=tk.NORMAL, bg=SURFACE_COLOR, fg=TEXT_COLOR, cursor="hand2")
        for row in self.task_rows:
            row["input_button"].config(state=tk.NORMAL, bg="#eef4ff", fg=PRIMARY_COLOR, cursor="hand2")
            row["output_button"].config(state=tk.NORMAL, bg="#eef4ff", fg=PRIMARY_COLOR, cursor="hand2")
            row["expected_button"].config(state=tk.NORMAL, bg="#eef4ff", fg=PRIMARY_COLOR, cursor="hand2")
            row["input_entry"].config(state=tk.NORMAL, bg=SURFACE_MUTED, fg=TEXT_COLOR)
            row["output_entry"].config(state=tk.NORMAL, bg=SURFACE_MUTED, fg=TEXT_COLOR)
            row["expected_entry"].config(state=tk.NORMAL, bg=SURFACE_MUTED, fg=TEXT_COLOR)

    def _append_log(self, message: str) -> None:
        def append() -> None:
            self.log_text.insert(tk.END, f"{message}\n")
            self.log_text.see(tk.END)
            self.progress_var.set(message)
            self._update_task_progress_from_message(message)

        self.root.after(0, append)


    def _config_for_speed(self, config):
        speed_mode = self._selected_speed_mode()
        if speed_mode == OCR_SPEED_STABLE:
            return replace(config, ocr_speed_mode=speed_mode, ocr_retries=max(config.ocr_retries, 1))
        if speed_mode == OCR_SPEED_FAST:
            return replace(config, ocr_speed_mode=speed_mode, ocr_retries=0)
        return replace(config, ocr_speed_mode=OCR_SPEED_BALANCED)

    def _max_workers_for_speed(self) -> int:
        return 1 if self._selected_speed_mode() == OCR_SPEED_STABLE else 2

    def _selected_speed_mode(self) -> str:
        return SPEED_MODE_VALUES.get(self.speed_mode_var.get(), OCR_SPEED_BALANCED)


    def _update_expected_status(self, task_index: int, expected_path: Path) -> None:
        row = self.task_rows[task_index]
        try:
            inspection = inspect_expected_codes(expected_path)
        except Exception as exc:
            row["expected_status_var"].set(f"清单读取失败: {exc}")
            row["expected_status_label"].config(fg=DANGER_COLOR)
            return

        row["expected_status_var"].set(
            f"清单校验：有效 {inspection.valid_count} | "
            f"重复 {inspection.duplicate_count} | 无效 {inspection.invalid_count}"
        )
        row["expected_status_label"].config(fg=DANGER_COLOR if inspection.invalid_count else MUTED_TEXT_COLOR)

    def _validate_expected_list(self, task_index: int, expected_path: Path) -> bool:
        self._update_expected_status(task_index, expected_path)
        inspection = inspect_expected_codes(expected_path)
        if inspection.valid_count == 0 and inspection.invalid_count > 0:
            messagebox.showerror(
                "错误",
                f"任务 {task_index + 1} 预期箱号清单没有可用箱号，请检查格式或校验位",
            )
            return False
        return True

    def _reset_task_progress(self, tasks: list[DirectoryTask]) -> None:
        self.task_progress_states = []
        self.active_output_dirs = [task.output_dir for task in tasks]
        for index, row in enumerate(self.task_rows):
            enabled = index < len(tasks)
            state = {"total": 0, "processed": 0, "success": 0, "unrecognized": 0, "invalid": 0}
            self.task_progress_states.append(state)
            row["progress_text_var"].set("待处理" if enabled else "未启用")
            row["summary_var"].set("已处理 0/0 | 成功 0 | 未识别 0 | 箱号错误 0")
            row["progressbar"].config(maximum=1, value=0)
            row["open_button"].config(state=tk.DISABLED, bg=DISABLED_BG, fg="#ffffff", cursor="arrow")

    def _update_task_progress_from_message(self, message: str) -> None:
        match = re.match(r"^\[任务 (\d+)/(\d+)\] (.*)$", message)
        if not match:
            return

        task_index = int(match.group(1)) - 1
        if task_index < 0 or task_index >= len(self.task_progress_states):
            return

        detail = match.group(3)
        state = self.task_progress_states[task_index]
        scan_match = re.search(r"扫描到 (\d+) 个文件", detail)
        if scan_match:
            state["total"] = int(scan_match.group(1))
            self._render_task_progress(task_index)
            return

        if detail.startswith("结果:"):
            self._record_task_result(state, detail)
            self._render_task_progress(task_index)
            return

        if detail in {"处理完成", "已取消"}:
            self._render_task_progress(task_index)

    def _record_task_result(self, state: dict, detail: str) -> None:
        total = state["total"]
        state["processed"] = min(state["processed"] + 1, total) if total else state["processed"] + 1
        if "-> 正确识别" in detail:
            state["success"] += 1
        elif "-> 箱号错误" in detail:
            state["invalid"] += 1
        elif "-> 未识别" in detail:
            state["unrecognized"] += 1

    def _render_task_progress(self, task_index: int) -> None:
        row = self.task_rows[task_index]
        state = self.task_progress_states[task_index]
        total = state["total"]
        processed = state["processed"]
        row["progress_text_var"].set(f"进度 {processed}/{total}")
        row["summary_var"].set(
            f"已处理 {processed}/{total} | 成功 {state['success']} | "
            f"未识别 {state['unrecognized']} | 箱号错误 {state['invalid']}"
        )
        row["progressbar"].config(maximum=max(total, 1), value=min(processed, total) if total else processed)

    def _enable_output_buttons(self) -> None:
        for index, output_dir in enumerate(self.active_output_dirs):
            if index >= len(self.task_rows):
                continue
            if output_dir.exists():
                self.task_rows[index]["open_button"].config(state=tk.NORMAL, bg="#eef4ff", fg=PRIMARY_COLOR, cursor="hand2")

    def _open_output(self, task_index: int) -> None:
        if task_index >= len(self.active_output_dirs):
            return
        output_dir = self.active_output_dirs[task_index]
        if not output_dir.exists():
            messagebox.showerror("错误", "输出文件夹不存在")
            return
        os.startfile(output_dir)



def _is_input_inside_output(input_dir: Path, output_dir: Path) -> bool:
    resolved_input = input_dir.resolve()
    resolved_output = output_dir.resolve()
    return resolved_input == resolved_output or resolved_output in resolved_input.parents
