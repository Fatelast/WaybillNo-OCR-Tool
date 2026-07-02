import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from waybill_ocr.config import default_config, resolve_default_work_dir
from waybill_ocr.diagnostics import format_diagnostic_messages, inspect_environment
from waybill_ocr.ocr.tesseract_engine import TesseractEngine
from waybill_ocr.ui.task_runner import DirectoryTask, process_directory_tasks

MAX_TASKS = 2


class MainWindow:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("运单箱号识别分拣")
        self.root.geometry("900x600")

        self.task_rows = []
        self.progress_var = tk.StringVar(value="待处理")
        self.running = False
        self.cancel_event: threading.Event | None = None

        self._build_layout()

    def run(self) -> None:
        self.root.mainloop()

    def _build_layout(self) -> None:
        frame = ttk.Frame(self.root, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        for index in range(MAX_TASKS):
            row = index * 2
            input_var = tk.StringVar()
            output_var = tk.StringVar()

            ttk.Label(frame, text=f"任务 {index + 1} 输入文件夹").grid(row=row, column=0, sticky=tk.W)
            input_entry = ttk.Entry(frame, textvariable=input_var)
            input_entry.grid(row=row, column=1, sticky=tk.EW, padx=8)
            input_button = ttk.Button(frame, text="选择", command=lambda task_index=index: self._choose_input(task_index))
            input_button.grid(row=row, column=2)

            ttk.Label(frame, text=f"任务 {index + 1} 输出文件夹").grid(row=row + 1, column=0, sticky=tk.W, pady=(4, 8))
            output_entry = ttk.Entry(frame, textvariable=output_var)
            output_entry.grid(row=row + 1, column=1, sticky=tk.EW, padx=8, pady=(4, 8))
            output_button = ttk.Button(frame, text="选择", command=lambda task_index=index: self._choose_output(task_index))
            output_button.grid(row=row + 1, column=2, pady=(4, 8))

            self.task_rows.append(
                {
                    "input_var": input_var,
                    "output_var": output_var,
                    "input_entry": input_entry,
                    "output_entry": output_entry,
                    "input_button": input_button,
                    "output_button": output_button,
                }
            )

        controls_row = MAX_TASKS * 2
        self.start_button = ttk.Button(frame, text="开始处理", command=self._start)
        self.start_button.grid(row=controls_row, column=0, columnspan=2, sticky=tk.EW, pady=8)
        self.stop_button = ttk.Button(frame, text="停止处理", command=self._stop, state=tk.DISABLED)
        self.stop_button.grid(row=controls_row, column=2, sticky=tk.EW, pady=8)

        ttk.Label(frame, textvariable=self.progress_var).grid(row=controls_row + 1, column=0, columnspan=3, sticky=tk.W)

        self.log_text = tk.Text(frame, height=22)
        self.log_text.grid(row=controls_row + 2, column=0, columnspan=3, sticky=tk.NSEW, pady=8)

        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(controls_row + 2, weight=1)

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
            if index > 0 and not input_text and not output_text:
                continue
            if not input_text or not output_text:
                messagebox.showerror("错误", f"请完整填写任务 {index + 1} 的输入和输出文件夹")
                return None

            input_dir = Path(input_text)
            output_dir = Path(output_text)
            if not input_dir.is_dir():
                messagebox.showerror("错误", f"任务 {index + 1} 输入文件夹不存在")
                return None
            if _is_input_inside_output(input_dir, output_dir):
                messagebox.showerror("错误", f"任务 {index + 1} 的输入文件夹不能在输出文件夹内")
                return None
            raw_tasks.append((input_dir, output_dir))

        if not raw_tasks:
            messagebox.showerror("错误", "请至少填写任务 1 的输入和输出文件夹")
            return None

        total = len(raw_tasks)
        return [
            DirectoryTask(input_dir=input_dir, output_dir=output_dir, label=f"任务 {index}/{total}")
            for index, (input_dir, output_dir) in enumerate(raw_tasks, start=1)
        ]

    def _stop(self) -> None:
        if not self.running or self.cancel_event is None:
            return

        self.cancel_event.set()
        self.stop_button.config(state=tk.DISABLED)
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
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        for row in self.task_rows:
            row["input_button"].config(state=tk.DISABLED)
            row["output_button"].config(state=tk.DISABLED)
            row["input_entry"].config(state=tk.DISABLED)
            row["output_entry"].config(state=tk.DISABLED)

    def _set_idle_controls(self) -> None:
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        for row in self.task_rows:
            row["input_button"].config(state=tk.NORMAL)
            row["output_button"].config(state=tk.NORMAL)
            row["input_entry"].config(state=tk.NORMAL)
            row["output_entry"].config(state=tk.NORMAL)

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
