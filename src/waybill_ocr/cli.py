import argparse
import sys
from pathlib import Path
from typing import TextIO

from waybill_ocr.batch_processor import process_directory
from waybill_ocr.config import default_config
from waybill_ocr.diagnostics import format_diagnostic_messages, inspect_environment
from waybill_ocr.ocr.tesseract_engine import TesseractEngine


def main(argv: list[str] | None = None, stdout: TextIO | None = None) -> int:
    output = stdout or sys.stdout
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "diagnose":
        return _run_diagnose(output)

    if args.command == "batch":
        return _run_batch(args, output)

    parser.print_help(output)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="waybill-ocr")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("diagnose", help="检查 OCR 运行环境")

    batch_parser = subparsers.add_parser("batch", help="批量处理输入目录")
    batch_parser.add_argument("--input", required=True, dest="input_dir", help="输入文件夹")
    batch_parser.add_argument("--output", required=True, dest="output_dir", help="输出文件夹")

    return parser


def _run_diagnose(stdout: TextIO) -> int:
    results = inspect_environment(default_config())
    for message in format_diagnostic_messages(results):
        print(message, file=stdout)

    return 0 if all(result.ok for result in results) else 1


def _run_batch(args: argparse.Namespace, stdout: TextIO) -> int:
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    if not input_dir.is_dir():
        print(f"输入文件夹不存在: {input_dir}", file=stdout)
        return 2

    config = default_config()
    engine = TesseractEngine(config)
    process_directory(
        input_dir=input_dir,
        output_dir=output_dir,
        config=config,
        ocr_engine=engine,
        on_progress=lambda message: print(message, file=stdout),
    )
    return 0
