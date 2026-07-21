import os
import threading
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from waybill_ocr.batch_processor import ProcessingProgressEvent, count_retryable_results
from waybill_ocr.config import (
    OCR_SPEED_BALANCED,
    OCR_SPEED_FAST,
    OCR_SPEED_STABLE,
    default_config,
    resolve_default_work_dir,
)
from waybill_ocr.constants import INVALID_DIR_NAME, RESULT_WORKBOOK_NAME, SUCCESS_DIR_NAME, UNRECOGNIZED_DIR_NAME
from waybill_ocr.container_code.expected_codes import inspect_expected_codes, read_expected_codes
from waybill_ocr.delivery import APP_NAME, CURRENT_VERSION
from waybill_ocr.diagnostics import format_diagnostic_messages, inspect_environment
from waybill_ocr.models import RecognitionStatus
from waybill_ocr.ocr.tesseract_engine import TesseractEngine
from waybill_ocr.sample_verifier import resolve_default_baseline_path, verify_samples
from waybill_ocr.review_confirmation import (
    auto_confirm_expected_candidates,
    confirm_review_candidates,
    scan_review_candidates,
)
from waybill_ocr.ui.preferences import load_preferences, save_preferences
from waybill_ocr.ui.task_runner import DirectoryTask, process_directory_tasks

MAX_TASKS = 2
SAMPLE_INPUT_DIR = Path("samples/cases")
SAMPLE_FALLBACK_INPUT_DIR = Path("samples/input")
SAMPLE_OUTPUT_DIR = Path("samples/actual")
SAMPLE_BASELINE_PATH = resolve_default_baseline_path()

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
    OCR_SPEED_STABLE: "稳定模式",
    OCR_SPEED_BALANCED: "均衡模式",
    OCR_SPEED_FAST: "快速模式",
}
SPEED_MODE_VALUES = {label: mode for mode, label in SPEED_MODE_LABELS.items()}
SPEED_MODE_DESCRIPTIONS = {
    OCR_SPEED_STABLE: "适合模糊文件；处理更慢，会尽量复核并提升成功识别率。",
    OCR_SPEED_BALANCED: "默认推荐；兼顾速度和准确率，会对失败件做有限复核。",
    OCR_SPEED_FAST: "适合清晰文件快速粗筛；失败件会保留待确认，不做深度复核。",
}



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
        self.speed_description_var = tk.StringVar(value=_speed_mode_description(OCR_SPEED_BALANCED))
        self.running = False
        self.cancel_event: threading.Event | None = None
        self.preferences = load_preferences()
        self.active_tasks: list[DirectoryTask] = []
        self.active_output_dirs: list[Path] = []
        self.task_progress_states: list[dict] = []

        self._configure_style()
        self._build_layout()
        self._restore_recent_paths()

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
        section.grid(row=1, column=0, sticky=tk.EW, pady=(8, 0))
        section.columnconfigure(0, weight=1)

        for index in range(MAX_TASKS):
            task_frame = tk.Frame(
                section,
                bg=SURFACE_COLOR,
                padx=10,
                pady=6,
                highlightbackground=BORDER_COLOR,
                highlightthickness=1,
            )
            task_frame.grid(row=index, column=0, sticky=tk.EW, pady=(0, 5))
            task_frame.columnconfigure(1, weight=1)

            input_var = tk.StringVar()
            output_var = tk.StringVar()
            expected_var = tk.StringVar()
            badge_text = "\u5fc5\u586b" if index == 0 else "\u53ef\u9009"
            badge_bg = "#dbeafe" if index == 0 else "#eef2f7"
            badge_fg = PRIMARY_COLOR if index == 0 else MUTED_TEXT_COLOR

            header_box = tk.Frame(task_frame, bg=SURFACE_COLOR)
            header_box.grid(row=0, column=0, sticky=tk.W, pady=(0, 4))
            tk.Label(
                header_box,
                text=f"\u4efb\u52a1 {index + 1}",
                bg=SURFACE_COLOR,
                fg=TEXT_COLOR,
                font=(FONT_FAMILY, 10, "bold"),
            ).grid(row=0, column=0, sticky=tk.W)
            tk.Label(
                header_box,
                text=badge_text,
                bg=badge_bg,
                fg=badge_fg,
                padx=7,
                pady=2,
                font=(FONT_FAMILY, 8, "bold"),
            ).grid(row=0, column=1, sticky=tk.W, padx=(8, 0))

            progress_text_var = tk.StringVar(value="\u5f85\u5904\u7406")
            summary_var = tk.StringVar(value="\u5df2\u5904\u7406 0/0 | \u6210\u529f 0 | \u672a\u8bc6\u522b 0 | \u7bb1\u53f7\u9519\u8bef 0")
            progress_cell = tk.Frame(task_frame, bg=SURFACE_COLOR)
            progress_cell.grid(row=0, column=1, sticky=tk.EW, padx=(8, 8), pady=(0, 4))
            progress_cell.columnconfigure(1, weight=1)
            tk.Label(
                progress_cell,
                textvariable=progress_text_var,
                bg=SURFACE_COLOR,
                fg=TEXT_COLOR,
                font=(FONT_FAMILY, 8, "bold"),
                anchor=tk.W,
            ).grid(row=0, column=0, sticky=tk.W)
            tk.Label(
                progress_cell,
                textvariable=summary_var,
                bg=SURFACE_COLOR,
                fg=MUTED_TEXT_COLOR,
                font=(FONT_FAMILY, 8),
                anchor=tk.E,
            ).grid(row=0, column=1, sticky=tk.E)
            progressbar = ttk.Progressbar(progress_cell, mode="determinate", maximum=1, value=0, style="Horizontal.TProgressbar")
            progressbar.grid(row=1, column=0, columnspan=2, sticky=tk.EW, pady=(2, 0))

            result_menu_button = self._build_result_menu(task_frame, index)
            result_menu_button.grid(row=0, column=2, sticky=tk.E, pady=(0, 4))


            input_entry, input_button = self._build_path_field(
                task_frame,
                1,
                "\u8f93\u5165\u6587\u4ef6\u5939",
                input_var,
                lambda task_index=index: self._choose_input(task_index),
            )
            output_entry, output_button = self._build_path_field(
                task_frame,
                2,
                "\u8f93\u51fa\u6587\u4ef6\u5939\uff08\u53ef\u9009\uff09",
                output_var,
                lambda task_index=index: self._choose_output(task_index),
            )
            expected_entry, expected_button = self._build_path_field(
                task_frame,
                3,
                "\u9884\u671f\u7bb1\u53f7\u6e05\u5355\uff08\u975e\u5fc5\u9009\uff09",
                expected_var,
                lambda task_index=index: self._choose_expected(task_index),
            )

            expected_status_var = tk.StringVar(
                value="\u9884\u671f\u6e05\u5355\uff1a\u975e\u5fc5\u9009\uff1b\u652f\u6301 .txt / .csv / .xlsx\uff1b\u5efa\u8bae\u6bcf\u884c\u4e00\u4e2a\u7bb1\u53f7\u3002"
            )
            expected_status_label = tk.Label(
                task_frame,
                textvariable=expected_status_var,
                bg=SURFACE_COLOR,
                fg=MUTED_TEXT_COLOR,
                font=(FONT_FAMILY, 8),
                anchor=tk.W,
            )
            expected_status_label.grid(row=4, column=1, columnspan=2, sticky=tk.W, padx=(8, 0), pady=(0, 1))

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
                    "result_menu_button": result_menu_button,
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

    def _build_result_menu(self, parent: tk.Frame, task_index: int) -> tk.Menubutton:
        button = tk.Menubutton(
            parent,
            text="\u6253\u5f00\u7ed3\u679c",
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
        menu = tk.Menu(button, tearoff=False, font=(FONT_FAMILY, 8))
        menu.add_command(label="\u8f93\u51fa\u6587\u4ef6\u5939", command=lambda: self._open_output_path(task_index, "output"))
        menu.add_command(label="\u8bc6\u522b\u7ed3\u679c.xlsx", command=lambda: self._open_output_path(task_index, "excel"))
        menu.add_separator()
        menu.add_command(label="\u6b63\u786e\u8bc6\u522b", command=lambda: self._open_output_path(task_index, "success"))
        menu.add_command(label="\u672a\u8bc6\u522b", command=lambda: self._open_output_path(task_index, "unrecognized"))
        menu.add_command(label="\u7bb1\u53f7\u9519\u8bef", command=lambda: self._open_output_path(task_index, "invalid"))
        menu.add_separator()
        menu.add_command(label="\u5f85\u786e\u8ba4\u6587\u4ef6", command=lambda: self._open_review_dialog(task_index))
        menu.add_command(label="\u6279\u91cf\u786e\u8ba4\u5e76\u6574\u7406", command=lambda: self._open_review_dialog(task_index))
        menu.add_command(label="\u6309\u9884\u671f\u6e05\u5355\u81ea\u52a8\u6574\u7406", command=lambda: self._auto_confirm_expected(task_index))
        menu.add_separator()
        menu.add_command(label="\u5931\u8d25\u6587\u4ef6\u91cd\u65b0\u8bc6\u522b", command=lambda: self._retry_failed_files(task_index))
        button.configure(menu=menu)
        return button

    def _build_actions(self, parent: tk.Frame) -> None:
        actions = tk.Frame(parent, bg=BG_COLOR)
        actions.grid(row=2, column=0, sticky=tk.EW, pady=(0, 8))
        actions.columnconfigure(0, weight=1)

        hint = tk.Label(
            actions,
            text="运行中会锁定路径选择；输出文件夹不选时自动创建“输入文件夹名_识别输出”。",
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
            command=lambda _selected: self._update_speed_description(),
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
        tk.Label(
            speed_box,
            textvariable=self.speed_description_var,
            bg=BG_COLOR,
            fg=MUTED_TEXT_COLOR,
            font=(FONT_FAMILY, 8),
            anchor=tk.W,
        ).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(3, 0))
        self.sample_button = tk.Button(
            button_box,
            text="样本验收",
            command=self._verify_samples,
            bg="#eef4ff",
            fg=PRIMARY_COLOR,
            activebackground="#dbeafe",
            activeforeground=PRIMARY_HOVER,
            relief=tk.FLAT,
            cursor="hand2",
            padx=14,
            pady=8,
            font=(FONT_FAMILY, 9, "bold"),
        )
        self.sample_button.grid(row=0, column=1, padx=(0, 8))
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
        self.start_button.grid(row=0, column=2, padx=(0, 8))
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
        self.stop_button.grid(row=0, column=3)

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
        path = filedialog.askdirectory(initialdir=self._recent_dir("input_dir"))
        if path:
            self.task_rows[task_index]["input_var"].set(path)
            self._remember_path("input_dir", path)

    def _choose_output(self, task_index: int) -> None:
        if self.running:
            return
        path = filedialog.askdirectory(initialdir=self._recent_dir("output_dir"))
        if path:
            self.task_rows[task_index]["output_var"].set(path)
            self._remember_path("output_dir", path)

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
        if not self._confirm_reusing_existing_results(tasks):
            return

        self._save_recent_task_paths(tasks)
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
            if index > 0 and not input_text and not output_text and not expected_text:
                continue
            if not input_text:
                messagebox.showerror("错误", f"任务 {index + 1} 请先选择输入文件夹；输出文件夹可不选，系统会自动创建")
                return None

            input_dir = Path(input_text)
            expected_path = Path(expected_text) if expected_text else None
            if not input_dir.is_dir():
                messagebox.showerror("错误", f"任务 {index + 1} 输入文件夹不存在")
                return None

            output_dir = Path(output_text) if output_text else _default_output_dir_for(input_dir)
            if not output_text:
                row["output_var"].set(str(output_dir))

            if expected_path is not None and not expected_path.is_file():
                messagebox.showerror("错误", f"任务 {index + 1} 预期箱号清单不存在")
                return None
            if _is_input_inside_output(input_dir, output_dir):
                messagebox.showerror("错误", f"任务 {index + 1} 的输入文件夹不能在输出文件夹内")
                return None
            raw_tasks.append((input_dir, output_dir, expected_path))

        if not raw_tasks:
            messagebox.showerror("错误", "请至少填写任务 1 的输入文件夹")
            return None

        duplicate_output = _duplicate_output_dir(raw_tasks)
        if duplicate_output is not None:
            messagebox.showerror("错误", f"输出文件夹不能重复：{duplicate_output}")
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

    def _retry_failed_files(self, task_index: int) -> None:
        if self.running or task_index >= len(self.active_tasks):
            return

        task = self.active_tasks[task_index]
        try:
            failed_count = count_retryable_results(task.output_dir)
        except Exception as exc:
            messagebox.showerror("\u91cd\u65b0\u8bc6\u522b\u5931\u8d25\u6587\u4ef6", f"\u8bfb\u53d6\u5386\u53f2\u7ed3\u679c\u5931\u8d25\uff1a{exc}")
            return
        if failed_count == 0:
            messagebox.showinfo("\u91cd\u65b0\u8bc6\u522b\u5931\u8d25\u6587\u4ef6", "\u5f53\u524d\u4efb\u52a1\u6ca1\u6709\u672a\u8bc6\u522b\u6216\u7bb1\u53f7\u9519\u8bef\u6587\u4ef6")
            return
        if not messagebox.askyesno(
            "\u91cd\u65b0\u8bc6\u522b\u5931\u8d25\u6587\u4ef6",
            f"\u5c06\u91cd\u65b0\u8bc6\u522b {failed_count} \u4e2a\u5931\u8d25\u6587\u4ef6\uff0c\u5df2\u6b63\u786e\u8bc6\u522b\u7684\u6587\u4ef6\u4f1a\u81ea\u52a8\u8df3\u8fc7\u3002\u662f\u5426\u7ee7\u7eed\uff1f",
        ):
            return

        self._reset_single_task_progress(task_index)
        self.running = True
        self.cancel_event = threading.Event()
        self._set_running_controls()
        self._append_log(f"[{task.label}] \u5f00\u59cb\u91cd\u65b0\u8bc6\u522b {failed_count} \u4e2a\u5931\u8d25\u6587\u4ef6")
        thread = threading.Thread(
            target=self._process,
            args=([task], self.cancel_event, {1: task_index + 1}),
            daemon=True,
        )
        thread.start()


    def _process(
        self,
        tasks: list[DirectoryTask],
        cancel_event: threading.Event,
        task_number_map: dict[int, int] | None = None,
    ) -> None:
        try:
            config = self._config_for_speed(default_config(work_dir=resolve_default_work_dir()))
            for message in format_diagnostic_messages(inspect_environment(config)):
                self._append_log(message)
            progress_handler = self._handle_task_progress_event
            if task_number_map:
                progress_handler = lambda task_number, event: self._handle_task_progress_event(
                    task_number_map.get(task_number, task_number), event
                )
            process_directory_tasks(
                tasks=tasks,
                base_config=config,
                engine_factory=TesseractEngine,
                on_progress=self._append_log,
                cancel_event=cancel_event,
                on_progress_event=progress_handler,
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
        self.sample_button.config(state=tk.DISABLED, bg=DISABLED_BG, fg="#ffffff", cursor="arrow")
        self.stop_button.config(state=tk.NORMAL, bg=DANGER_COLOR, cursor="hand2")
        self.speed_menu.config(state=tk.DISABLED, bg=DISABLED_BG, fg="#ffffff", cursor="arrow")
        for row in self.task_rows:
            row["input_button"].config(state=tk.DISABLED, bg=DISABLED_BG, fg="#ffffff", cursor="arrow")
            row["output_button"].config(state=tk.DISABLED, bg=DISABLED_BG, fg="#ffffff", cursor="arrow")
            row["expected_button"].config(state=tk.DISABLED, bg=DISABLED_BG, fg="#ffffff", cursor="arrow")
            row["result_menu_button"].config(state=tk.DISABLED, bg=DISABLED_BG, fg="#ffffff", cursor="arrow")
            row["input_entry"].config(state=tk.DISABLED, disabledbackground="#eef2f7", disabledforeground=MUTED_TEXT_COLOR)
            row["output_entry"].config(state=tk.DISABLED, disabledbackground="#eef2f7", disabledforeground=MUTED_TEXT_COLOR)
            row["expected_entry"].config(state=tk.DISABLED, disabledbackground="#eef2f7", disabledforeground=MUTED_TEXT_COLOR)

    def _set_idle_controls(self) -> None:
        self.start_button.config(state=tk.NORMAL, bg=PRIMARY_COLOR, cursor="hand2")
        self.sample_button.config(state=tk.NORMAL, bg="#eef4ff", fg=PRIMARY_COLOR, cursor="hand2")
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

        self.root.after(0, append)

    def _handle_task_progress_event(self, task_number: int, event: ProcessingProgressEvent) -> None:
        self.root.after(0, lambda: self._apply_task_progress_event(task_number, event))

    def _apply_task_progress_event(self, task_number: int, event: ProcessingProgressEvent) -> None:
        task_index = task_number - 1
        if task_index < 0 or task_index >= len(self.task_progress_states):
            return

        state = self.task_progress_states[task_index]
        if event.kind == "scanned":
            state["total"] = event.total
        elif event.kind == "result" and event.result is not None:
            self._record_task_result(state, event.result.status)
        elif (
            event.kind == "reclassified"
            and event.result is not None
            and event.previous_status is not None
        ):
            self._replace_task_result_status(state, event.previous_status, event.result.status)
        elif event.kind not in {"complete", "cancelled"}:
            return

        self._render_task_progress(task_index)


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

    def _update_speed_description(self) -> None:
        speed_mode = SPEED_MODE_VALUES.get(self.speed_mode_var.get(), OCR_SPEED_BALANCED)
        self.speed_description_var.set(_speed_mode_description(speed_mode))


    def _update_expected_status(self, task_index: int, expected_path: Path) -> None:
        row = self.task_rows[task_index]
        try:
            inspection = inspect_expected_codes(expected_path)
        except Exception as exc:
            row["expected_status_var"].set(f"清单读取失败: {exc}")
            row["expected_status_label"].config(fg=DANGER_COLOR)
            return

        preview = ", ".join(inspection.valid_codes[:3])
        preview_text = f" | 预览 {preview}" if preview else ""
        row["expected_status_var"].set(
            f"清单校验：有效 {inspection.valid_count} | "
            f"重复 {inspection.duplicate_count} | 无效 {inspection.invalid_count}{preview_text}"
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
        self.active_tasks = list(tasks)
        self.task_progress_states = []
        self.active_output_dirs = [task.output_dir for task in tasks]
        for index, row in enumerate(self.task_rows):
            enabled = index < len(tasks)
            state = {"total": 0, "processed": 0, "success": 0, "unrecognized": 0, "invalid": 0}
            self.task_progress_states.append(state)
            row["progress_text_var"].set("待处理" if enabled else "未启用")
            row["summary_var"].set("已处理 0/0 | 成功 0 | 未识别 0 | 箱号错误 0")
            row["progressbar"].config(maximum=1, value=0)
            row["result_menu_button"].config(state=tk.DISABLED, bg=DISABLED_BG, fg="#ffffff", cursor="arrow")

    def _reset_single_task_progress(self, task_index: int) -> None:
        state = {"total": 0, "processed": 0, "success": 0, "unrecognized": 0, "invalid": 0}
        self.task_progress_states[task_index] = state
        row = self.task_rows[task_index]
        row["progress_text_var"].set("\u5f85\u5904\u7406")
        row["summary_var"].set("\u5df2\u5904\u7406 0/0 | \u6210\u529f 0 | \u672a\u8bc6\u522b 0 | \u7bb1\u53f7\u9519\u8bef 0")
        row["progressbar"].config(maximum=1, value=0)


    def _record_task_result(self, state: dict, status: RecognitionStatus) -> None:
        total = state["total"]
        state["processed"] = min(state["processed"] + 1, total) if total else state["processed"] + 1
        if status == RecognitionStatus.SUCCESS:
            state["success"] += 1
        elif status == RecognitionStatus.INVALID:
            state["invalid"] += 1
        elif status == RecognitionStatus.UNRECOGNIZED:
            state["unrecognized"] += 1

    @staticmethod
    def _replace_task_result_status(
        state: dict,
        previous_status: RecognitionStatus,
        current_status: RecognitionStatus,
    ) -> None:
        counter_keys = {
            RecognitionStatus.SUCCESS: "success",
            RecognitionStatus.UNRECOGNIZED: "unrecognized",
            RecognitionStatus.INVALID: "invalid",
        }
        previous_key = counter_keys[previous_status]
        state[previous_key] = max(0, state[previous_key] - 1)
        state[counter_keys[current_status]] += 1

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
                self.task_rows[index]["result_menu_button"].config(
                    state=tk.NORMAL,
                    bg="#eef4ff",
                    fg=PRIMARY_COLOR,
                    cursor="hand2",
                )

    def _open_output_path(self, task_index: int, target: str) -> None:
        if task_index >= len(self.active_output_dirs):
            return
        output_dir = self.active_output_dirs[task_index]
        targets = {
            "output": output_dir,
            "excel": output_dir / RESULT_WORKBOOK_NAME,
            "success": output_dir / SUCCESS_DIR_NAME,
            "unrecognized": output_dir / UNRECOGNIZED_DIR_NAME,
            "invalid": output_dir / INVALID_DIR_NAME,
        }
        path = targets[target]
        if not path.exists():
            messagebox.showerror("错误", "结果路径不存在")
            return
        os.startfile(path)

    def _open_review_dialog(self, task_index: int) -> None:
        if self.running or task_index >= len(getattr(self, "active_output_dirs", [])):
            return
        output_dir = self.active_output_dirs[task_index]
        candidates = scan_review_candidates(output_dir)
        if not candidates:
            messagebox.showinfo("待确认文件", "当前没有可确认的待确认文件")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("待确认文件")
        dialog.geometry("900x460")
        dialog.minsize(760, 360)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(0, weight=1)

        frame = tk.Frame(dialog, bg=SURFACE_COLOR, padx=12, pady=12)
        frame.grid(row=0, column=0, sticky=tk.NSEW)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        tree = ttk.Treeview(
            frame,
            columns=("selected", "filename", "status", "code", "reason"),
            show="headings",
            selectmode="none",
        )
        headings = {
            "selected": "确认",
            "filename": "文件名",
            "status": "当前目录",
            "code": "待确认箱号",
            "reason": "状态",
        }
        widths = {"selected": 56, "filename": 300, "status": 90, "code": 140, "reason": 240}
        for column, heading in headings.items():
            tree.heading(column, text=heading)
            tree.column(column, width=widths[column], anchor=tk.W)
        tree.grid(row=0, column=0, sticky=tk.NSEW)
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        scrollbar.grid(row=0, column=1, sticky=tk.NS)
        tree.configure(yscrollcommand=scrollbar.set)

        candidate_by_item = {}
        selected_items: set[str] = set()
        for candidate in candidates:
            item_id = tree.insert(
                "",
                tk.END,
                values=(
                    "□",
                    candidate.source_path.name,
                    candidate.source_status.value,
                    candidate.review_code,
                    "可整理" if candidate.valid else candidate.reason or "不可整理",
                ),
            )
            candidate_by_item[item_id] = candidate

        def toggle_item(event) -> str | None:
            if tree.identify_region(event.x, event.y) != "cell":
                return None
            item_id = tree.identify_row(event.y)
            if not item_id or tree.identify_column(event.x) != "#1":
                return None
            candidate = candidate_by_item[item_id]
            if not candidate.valid:
                return "break"
            if item_id in selected_items:
                selected_items.remove(item_id)
                marker = "□"
            else:
                selected_items.add(item_id)
                marker = "✓"
            values = list(tree.item(item_id, "values"))
            values[0] = marker
            tree.item(item_id, values=values)
            return "break"

        def open_item(event) -> None:
            item_id = tree.identify_row(event.y)
            if not item_id:
                return
            try:
                os.startfile(str(candidate_by_item[item_id].source_path))
            except OSError as exc:
                messagebox.showerror("打开失败", f"无法打开文件：{exc}", parent=dialog)

        def open_location(event) -> None:
            item_id = tree.identify_row(event.y)
            if not item_id:
                return
            try:
                os.startfile(str(candidate_by_item[item_id].source_path.parent))
            except OSError as exc:
                messagebox.showerror("打开失败", f"无法打开所在文件夹：{exc}", parent=dialog)

        context_item_id = None

        def open_context_item(open_parent: bool) -> None:
            if context_item_id is None:
                return
            candidate = candidate_by_item[context_item_id]
            path = candidate.source_path.parent if open_parent else candidate.source_path
            try:
                os.startfile(str(path))
            except OSError as exc:
                target = "所在文件夹" if open_parent else "文件"
                messagebox.showerror("打开失败", f"无法打开{target}：{exc}", parent=dialog)

        context_menu = tk.Menu(dialog, tearoff=False, font=(FONT_FAMILY, 8))
        context_menu.add_command(label="打开文件", command=lambda: open_context_item(False))
        context_menu.add_command(label="打开所在文件夹", command=lambda: open_context_item(True))

        def show_context_menu(event) -> str:
            nonlocal context_item_id
            item_id = tree.identify_row(event.y)
            if not item_id:
                return "break"
            context_item_id = item_id
            context_menu.tk_popup(event.x_root, event.y_root)
            return "break"

        tree.bind("<Button-1>", toggle_item)
        tree.bind("<Double-1>", open_item)
        tree.bind("<Button-3>", show_context_menu)

        action_bar = tk.Frame(frame, bg=SURFACE_COLOR)
        action_bar.grid(row=1, column=0, columnspan=2, sticky=tk.EW, pady=(10, 0))
        action_bar.columnconfigure(0, weight=1)
        tk.Label(
            action_bar,
            text="双击文件可用系统默认程序查看；点击“确认”列勾选后再批量整理。",
            bg=SURFACE_COLOR,
            fg=MUTED_TEXT_COLOR,
            font=(FONT_FAMILY, 8),
        ).grid(row=0, column=0, sticky=tk.W)

        def select_all() -> None:
            for item_id, candidate in candidate_by_item.items():
                if not candidate.valid:
                    continue
                selected_items.add(item_id)
                values = list(tree.item(item_id, "values"))
                values[0] = "✓"
                tree.item(item_id, values=values)

        def clear_all() -> None:
            for item_id in list(selected_items):
                values = list(tree.item(item_id, "values"))
                values[0] = "□"
                tree.item(item_id, values=values)
            selected_items.clear()

        def confirm_selected() -> None:
            selected = [candidate_by_item[item_id] for item_id in selected_items]
            if not selected:
                messagebox.showinfo("待确认文件", "请先勾选已人工确认的文件", parent=dialog)
                return
            if not messagebox.askyesno(
                "确认整理",
                f"将整理已勾选的 {len(selected)} 个文件，并移动到“正确识别”目录。是否继续？",
                parent=dialog,
            ):
                return
            summary = confirm_review_candidates(output_dir, selected)
            self._show_review_summary(summary, parent=dialog)
            dialog.destroy()
            self._enable_output_buttons()

        tk.Button(
            action_bar,
            text="全选可整理项",
            command=select_all,
            bg="#eef4ff",
            fg=PRIMARY_COLOR,
            relief=tk.FLAT,
            padx=10,
            pady=5,
            font=(FONT_FAMILY, 8),
        ).grid(row=0, column=1, padx=(8, 4))
        tk.Button(
            action_bar,
            text="取消全选",
            command=clear_all,
            bg="#eef4ff",
            fg=PRIMARY_COLOR,
            relief=tk.FLAT,
            padx=10,
            pady=5,
            font=(FONT_FAMILY, 8),
        ).grid(row=0, column=2, padx=4)
        tk.Button(
            action_bar,
            text="整理已确认文件",
            command=confirm_selected,
            bg=PRIMARY_COLOR,
            fg="#ffffff",
            activebackground=PRIMARY_HOVER,
            relief=tk.FLAT,
            padx=12,
            pady=5,
            font=(FONT_FAMILY, 8, "bold"),
        ).grid(row=0, column=3, padx=(4, 0))

    def _auto_confirm_expected(self, task_index: int) -> None:
        if self.running or task_index >= len(getattr(self, "active_output_dirs", [])):
            return
        expected_text = self.task_rows[task_index]["expected_var"].get().strip()
        if not expected_text:
            messagebox.showinfo("预期清单", "当前任务没有上传预期箱号清单，无法自动整理。请使用“批量确认并整理”。")
            return
        expected_path = Path(expected_text)
        if not expected_path.is_file():
            messagebox.showerror("预期清单", "预期箱号清单不存在")
            return
        output_dir = self.active_output_dirs[task_index]
        try:
            expected_codes = read_expected_codes(expected_path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("预期清单", f"读取预期箱号清单失败：{exc}")
            return
        candidates = scan_review_candidates(output_dir)
        expected_set = {code.strip().upper() for code in expected_codes}
        eligible = [candidate for candidate in candidates if candidate.valid and candidate.review_code in expected_set]
        conflicts = [candidate for candidate in candidates if candidate.review_code in expected_set and not candidate.valid]
        remaining = len(candidates) - len(eligible)
        if not eligible:
            messagebox.showinfo("自动整理", "没有符合唯一预期清单匹配条件的待确认文件")
            return
        prompt = (
            f"可自动整理：{len(eligible)} 个文件\n"
            f"存在冲突：{len(conflicts)} 个文件\n"
            f"仍需人工确认：{remaining} 个文件\n\n"
            "是否继续整理可自动确认的文件？"
        )
        if not messagebox.askyesno("确认自动整理", prompt):
            return
        summary = auto_confirm_expected_candidates(output_dir, expected_codes)
        self._show_review_summary(summary)
        self._enable_output_buttons()

    @staticmethod
    def _show_review_summary(summary, parent=None) -> None:
        message = f"已整理 {summary.moved_count} 个文件，跳过 {summary.skipped_count} 个文件，存在冲突 {summary.conflict_count} 个"
        if summary.failures:
            message += "\n" + "\n".join(summary.failures[:5])
        messagebox.showinfo("整理完成", message, parent=parent)

    def _verify_samples(self) -> None:
        if self.running:
            return
        input_dir = SAMPLE_INPUT_DIR if SAMPLE_INPUT_DIR.exists() else SAMPLE_FALLBACK_INPUT_DIR
        if not input_dir.is_dir() or not SAMPLE_BASELINE_PATH.is_file():
            messagebox.showerror("错误", "样本目录或样本基线文件不存在")
            return

        def run_verify() -> None:
            self._append_log("开始样本验收")
            try:
                config = self._config_for_speed(default_config(work_dir=resolve_default_work_dir()))
                report = verify_samples(input_dir, SAMPLE_OUTPUT_DIR, SAMPLE_BASELINE_PATH, config, TesseractEngine(config))
                for message in report.messages:
                    self._append_log(message)
            except Exception as exc:
                self._append_log(f"样本验收失败: {exc}")

        threading.Thread(target=run_verify, daemon=True).start()

    def _recent_dir(self, key: str) -> str | None:
        value = self.preferences.get(key)
        if not value:
            return None
        path = Path(value)
        return str(path if path.is_dir() else path.parent)

    def _remember_path(self, key: str, value: str) -> None:
        self.preferences[key] = value
        save_preferences(self.preferences)

    def _restore_recent_paths(self) -> None:
        if not self.task_rows:
            return
        first_row = self.task_rows[0]
        if self.preferences.get("input_dir"):
            first_row["input_var"].set(self.preferences["input_dir"])
        if self.preferences.get("output_dir"):
            first_row["output_var"].set(self.preferences["output_dir"])
        if self.preferences.get("expected_path"):
            first_row["expected_var"].set(self.preferences["expected_path"])

    def _save_recent_task_paths(self, tasks: list[DirectoryTask]) -> None:
        if not tasks:
            return
        first = tasks[0]
        self.preferences["input_dir"] = str(first.input_dir)
        self.preferences["output_dir"] = str(first.output_dir)
        if first.expected_codes_path is not None:
            self.preferences["expected_path"] = str(first.expected_codes_path)
        save_preferences(self.preferences)

    def _confirm_reusing_existing_results(self, tasks: list[DirectoryTask]) -> bool:
        reused_outputs = [task.output_dir for task in tasks if (task.output_dir / RESULT_WORKBOOK_NAME).exists()]
        if not reused_outputs:
            return True
        listed = "\n".join(str(path) for path in reused_outputs)
        return messagebox.askyesno(
            "复用历史结果",
            "以下输出目录已有识别结果.xlsx，程序将复用历史结果并跳过已成功识别的文件。\n"
            f"{listed}\n\n是否继续？",
        )


def _speed_mode_description(speed_mode: str) -> str:
    return SPEED_MODE_DESCRIPTIONS.get(speed_mode, SPEED_MODE_DESCRIPTIONS[OCR_SPEED_BALANCED])


def _duplicate_output_dir(raw_tasks) -> Path | None:
    seen: set[Path] = set()
    for _input_dir, output_dir, _expected_path in raw_tasks:
        resolved_output = output_dir.resolve()
        if resolved_output in seen:
            return output_dir
        seen.add(resolved_output)
    return None


def _default_output_dir_for(input_dir: Path) -> Path:
    return input_dir.parent / f"{input_dir.name}_识别输出"

def _is_input_inside_output(input_dir: Path, output_dir: Path) -> bool:
    resolved_input = input_dir.resolve()
    resolved_output = output_dir.resolve()
    return resolved_input == resolved_output or resolved_output in resolved_input.parents
