import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from waybill_ocr.batch_processor import process_directory
from waybill_ocr.config import default_config
from waybill_ocr.diagnostics import format_diagnostic_messages, inspect_environment
from waybill_ocr.ocr.tesseract_engine import TesseractEngine


class MainWindow:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("运单箱号识别分拣")
        self.root.geometry("760x520")

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.progress_var = tk.StringVar(value="待处理")
        self.running = False

        self._build_layout()

    def run(self) -> None:
        self.root.mainloop()

    def _build_layout(self) -> None:
        frame = ttk.Frame(self.root, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="输入文件夹").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(frame, textvariable=self.input_var).grid(row=0, column=1, sticky=tk.EW, padx=8)
        ttk.Button(frame, text="选择", command=self._choose_input).grid(row=0, column=2)

        ttk.Label(frame, text="输出文件夹").grid(row=1, column=0, sticky=tk.W, pady=8)
        ttk.Entry(frame, textvariable=self.output_var).grid(row=1, column=1, sticky=tk.EW, padx=8)
        ttk.Button(frame, text="选择", command=self._choose_output).grid(row=1, column=2)

        self.start_button = ttk.Button(frame, text="开始处理", command=self._start)
        self.start_button.grid(row=2, column=0, columnspan=3, sticky=tk.EW, pady=8)

        ttk.Label(frame, textvariable=self.progress_var).grid(row=3, column=0, columnspan=3, sticky=tk.W)

        self.log_text = tk.Text(frame, height=20)
        self.log_text.grid(row=4, column=0, columnspan=3, sticky=tk.NSEW, pady=8)

        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(4, weight=1)

    def _choose_input(self) -> None:
        path = filedialog.askdirectory()
        if path:
            self.input_var.set(path)

    def _choose_output(self) -> None:
        path = filedialog.askdirectory()
        if path:
            self.output_var.set(path)

    def _start(self) -> None:
        if self.running:
            return

        input_text = self.input_var.get().strip()
        output_text = self.output_var.get().strip()
        input_dir = Path(input_text)
        output_dir = Path(output_text)
        if not input_text or not input_dir.is_dir() or not output_text:
            messagebox.showerror("错误", "请选择有效的输入文件夹和输出文件夹")
            return

        self.running = True
        self.start_button.config(state=tk.DISABLED)
        self._append_log("开始处理")
        thread = threading.Thread(target=self._process, args=(input_dir, output_dir), daemon=True)
        thread.start()

    def _process(self, input_dir: Path, output_dir: Path) -> None:
        try:
            config = default_config()
            for message in format_diagnostic_messages(inspect_environment(config)):
                self._append_log(message)
            engine = TesseractEngine(config)
            process_directory(input_dir, output_dir, config, engine, self._append_log)
        except Exception as exc:
            self._append_log(f"处理失败: {exc}")
        finally:
            self.root.after(0, self._finish)

    def _finish(self) -> None:
        self.running = False
        self.start_button.config(state=tk.NORMAL)

    def _append_log(self, message: str) -> None:
        def append() -> None:
            self.log_text.insert(tk.END, f"{message}\n")
            self.log_text.see(tk.END)
            self.progress_var.set(message)

        self.root.after(0, append)