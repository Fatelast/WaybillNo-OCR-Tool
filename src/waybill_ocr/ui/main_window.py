import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from waybill_ocr.config import default_config, resolve_default_work_dir
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


class MainWindow:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("运单箱号识别分拣")
        self.root.geometry("1040x760")
        self.root.minsize(920, 660)
        self.root.configure(bg=BG_COLOR)

        self.task_rows = []
        self.progress_var = tk.StringVar(value="待处理")
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

    def _build_layout(self) -> None:
        page = tk.Frame(self.root, bg=BG_COLOR, padx=18, pady=18)
        page.pack(fill=tk.BOTH, expand=True)
        page.columnconfigure(0, weight=1)
        page.rowconfigure(3, weight=1)

        self._build_header(page)
        self._build_task_section(page)
        self._build_actions(page)
        self._build_log_section(page)

    def _build_header(self, parent: tk.Frame) -> None:
        header = tk.Frame(parent, bg=PRIMARY_COLOR, padx=18, pady=16)
        header.grid(row=0, column=0, sticky=tk.EW)
        header.columnconfigure(0, weight=1)

        tk.Label(
            header,
            text="运单箱号识别分拣",
            bg=PRIMARY_COLOR,
            fg="#ffffff",
            font=(FONT_FAMILY, 18, "bold"),
        ).grid(row=0, column=0, sticky=tk.W)
        tk.Label(
            header,
            text="最多两组文件夹并行处理，支持预期箱号清单比对与结果表增量写入",
            bg=PRIMARY_COLOR,
            fg="#dbeafe",
            font=(FONT_FAMILY, 10),
        ).grid(row=1, column=0, sticky=tk.W, pady=(6, 0))

        status = tk.Label(
            header,
            textvariable=self.progress_var,
            bg="#1e40af",
            fg="#ffffff",
            padx=12,
            pady=6,
            font=(FONT_FAMILY, 9, "bold"),
        )
        status.grid(row=0, column=1, rowspan=2, sticky=tk.E, padx=(18, 0))

    def _build_task_section(self, parent: tk.Frame) -> None:
        section = tk.Frame(parent, bg=BG_COLOR)
        section.grid(row=1, column=0, sticky=tk.EW, pady=(14, 0))
        section.columnconfigure(0, weight=1)

        for index in range(MAX_TASKS):
            task_frame = tk.Frame(
                section,
                bg=SURFACE_COLOR,
                padx=16,
                pady=14,
                highlightbackground=BORDER_COLOR,
                highlightthickness=1,
            )
            task_frame.grid(row=index, column=0, sticky=tk.EW, pady=(0, 10))
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
                font=(FONT_FAMILY, 11, "bold"),
            ).grid(row=0, column=0, sticky=tk.W, pady=(0, 10))
            tk.Label(
                task_frame,
                text=badge_text,
                bg=badge_bg,
                fg=badge_fg,
                padx=8,
                pady=3,
                font=(FONT_FAMILY, 8, "bold"),
            ).grid(row=0, column=1, sticky=tk.W, pady=(0, 10))

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
            ).grid(row=4, column=1, columnspan=2, sticky=tk.W, padx=(10, 0), pady=(0, 2))

            self.task_rows.append(
                {
                    "input_var": input_var,
                    "output_var": output_var,
                    "expected_var": expected_var,
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
            font=(FONT_FAMILY, 9),
            width=18,
            anchor=tk.W,
        ).grid(row=row, column=0, sticky=tk.W, pady=5)

        entry = tk.Entry(
            parent,
            textvariable=variable,
            bg=SURFACE_MUTED,
            fg=TEXT_COLOR,
            relief=tk.FLAT,
            insertbackground=TEXT_COLOR,
            font=(FONT_FAMILY, 9),
            highlightbackground=BORDER_COLOR,
            highlightcolor=PRIMARY_COLOR,
            highlightthickness=1,
        )
        entry.grid(row=row, column=1, sticky=tk.EW, padx=(10, 10), pady=5, ipady=7)

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
            padx=14,
            pady=7,
            font=(FONT_FAMILY, 9, "bold"),
        )
        button.grid(row=row, column=2, sticky=tk.E, pady=5)
        return entry, button

    def _build_actions(self, parent: tk.Frame) -> None:
        actions = tk.Frame(parent, bg=BG_COLOR)
        actions.grid(row=2, column=0, sticky=tk.EW, pady=(2, 12))
        actions.columnconfigure(0, weight=1)

        hint = tk.Label(
            actions,
            text="运行中会锁定路径选择；如需切换目录，请先停止当前任务。",
            bg=BG_COLOR,
            fg=MUTED_TEXT_COLOR,
            font=(FONT_FAMILY, 9),
        )
        hint.grid(row=0, column=0, sticky=tk.W)

        button_box = tk.Frame(actions, bg=BG_COLOR)
        button_box.grid(row=0, column=1, sticky=tk.E)
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
            padx=28,
            pady=10,
            font=(FONT_FAMILY, 10, "bold"),
        )
        self.start_button.grid(row=0, column=0, padx=(0, 10))
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
            padx=22,
            pady=10,
            font=(FONT_FAMILY, 10, "bold"),
            state=tk.DISABLED,
        )
        self.stop_button.grid(row=0, column=1)

    def _build_log_section(self, parent: tk.Frame) -> None:
        panel = tk.Frame(
            parent,
            bg=SURFACE_COLOR,
            padx=14,
            pady=12,
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
            font=(FONT_FAMILY, 11, "bold"),
        ).grid(row=0, column=0, sticky=tk.W, pady=(0, 8))
        tk.Label(
            panel,
            text="实时显示环境检查、识别进度、失败原因和箱号比对结果",
            bg=SURFACE_COLOR,
            fg=MUTED_TEXT_COLOR,
            font=(FONT_FAMILY, 9),
        ).grid(row=0, column=0, sticky=tk.E, pady=(0, 8))

        log_frame = tk.Frame(panel, bg=LOG_BG, highlightbackground="#1e293b", highlightthickness=1)
        log_frame.grid(row=1, column=0, sticky=tk.NSEW)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(
            log_frame,
            height=20,
            wrap=tk.NONE,
            bg=LOG_BG,
            fg=LOG_FG,
            insertbackground=LOG_FG,
            relief=tk.FLAT,
            padx=12,
            pady=10,
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

    def _start(self) -> None:
        if self.running:
            return

        tasks = self._collect_tasks()
        if tasks is None:
            return

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
            config = default_config(work_dir=resolve_default_work_dir())
            for message in format_diagnostic_messages(inspect_environment(config)):
                self._append_log(message)
            process_directory_tasks(
                tasks=tasks,
                base_config=config,
                engine_factory=TesseractEngine,
                on_progress=self._append_log,
                cancel_event=cancel_event,
            )
        except Exception as exc:
            self._append_log(f"处理失败: {exc}")
        finally:
            self.root.after(0, self._finish)

    def _finish(self) -> None:
        self.running = False
        self.cancel_event = None
        self._set_idle_controls()

    def _set_running_controls(self) -> None:
        self.start_button.config(state=tk.DISABLED, bg=DISABLED_BG, cursor="arrow")
        self.stop_button.config(state=tk.NORMAL, bg=DANGER_COLOR, cursor="hand2")
        for row in self.task_rows:
            row["input_button"].config(state=tk.DISABLED, bg=DISABLED_BG, fg="#ffffff", cursor="arrow")
            row["output_button"].config(state=tk.DISABLED, bg=DISABLED_BG, fg="#ffffff", cursor="arrow")
            row["expected_button"].config(state=tk.DISABLED, bg=DISABLED_BG, fg="#ffffff", cursor="arrow")
            row["input_entry"].config(state=tk.DISABLED, disabledbackground="#eef2f7", disabledforeground=MUTED_TEXT_COLOR)
            row["output_entry"].config(state=tk.DISABLED, disabledbackground="#eef2f7", disabledforeground=MUTED_TEXT_COLOR)
            row["expected_entry"].config(state=tk.DISABLED, disabledbackground="#eef2f7", disabledforeground=MUTED_TEXT_COLOR)

    def _set_idle_controls(self) -> None:
        self.start_button.config(state=tk.NORMAL, bg=PRIMARY_COLOR, cursor="hand2")
        self.stop_button.config(state=tk.DISABLED, bg=DISABLED_BG, cursor="arrow")
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


def _is_input_inside_output(input_dir: Path, output_dir: Path) -> bool:
    resolved_input = input_dir.resolve()
    resolved_output = output_dir.resolve()
    return resolved_input == resolved_output or resolved_output in resolved_input.parents
