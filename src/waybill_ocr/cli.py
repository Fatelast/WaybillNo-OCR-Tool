import argparse
import sys
from pathlib import Path
from typing import TextIO

from waybill_ocr.batch_processor import process_directory
from waybill_ocr.container_code.expected_codes import read_expected_codes
from waybill_ocr.config import default_config, resolve_default_work_dir
from waybill_ocr.diagnostics import format_diagnostic_messages, inspect_environment
from waybill_ocr.ocr.tesseract_engine import TesseractEngine
from waybill_ocr.sample_verifier import resolve_default_baseline_path, verify_samples


DEFAULT_SAMPLE_INPUT = Path("samples/cases")
DEFAULT_SAMPLE_OUTPUT = Path("samples/actual")
DEFAULT_SAMPLE_BASELINE = resolve_default_baseline_path()


def main(argv: list[str] | None = None, stdout: TextIO | None = None) -> int:
    output = stdout or sys.stdout
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "diagnose":
        return _run_diagnose(output)

    if args.command == "batch":
        return _run_batch(args, output)

    if args.command == "verify-samples":
        return _run_verify_samples(args, output)

    parser.print_help(output)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="waybill-ocr")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("diagnose", help="检查 OCR 运行环境")

    batch_parser = subparsers.add_parser("batch", help="批量处理输入目录")
    batch_parser.add_argument("--input", required=True, dest="input_dir", help="输入文件夹")
    batch_parser.add_argument("--output", required=True, dest="output_dir", help="输出文件夹")
    batch_parser.add_argument("--expected", dest="expected_path", help="预期箱号清单（txt/csv/xlsx，可选）")

    sample_parser = subparsers.add_parser("verify-samples", help="按样本基线验收 OCR 结果")
    sample_parser.add_argument("--input", default=str(DEFAULT_SAMPLE_INPUT), dest="input_dir", help="样本输入文件夹")
    sample_parser.add_argument("--output", default=str(DEFAULT_SAMPLE_OUTPUT), dest="output_dir", help="样本输出文件夹")
    sample_parser.add_argument(
        "--baseline",
        default=str(DEFAULT_SAMPLE_BASELINE),
        dest="baseline_path",
        help="样本期望结果 CSV",
    )

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

    expected_codes = None
    if args.expected_path:
        expected_path = Path(args.expected_path)
        if not expected_path.is_file():
            print(f"预期箱号清单不存在: {expected_path}", file=stdout)
            return 2
        expected_codes = read_expected_codes(expected_path)

    config = default_config(work_dir=resolve_default_work_dir())
    engine = TesseractEngine(config)
    process_directory(
        input_dir=input_dir,
        output_dir=output_dir,
        config=config,
        ocr_engine=engine,
        on_progress=lambda message: print(message, file=stdout),
        expected_codes=expected_codes,
    )
    return 0


def _run_verify_samples(args: argparse.Namespace, stdout: TextIO) -> int:
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    baseline_path = Path(args.baseline_path)
    if not input_dir.is_dir():
        print(f"样本输入文件夹不存在: {input_dir}", file=stdout)
        return 2
    if not baseline_path.is_file():
        print(f"样本基线文件不存在: {baseline_path}", file=stdout)
        return 2

    config = default_config(work_dir=resolve_default_work_dir())
    engine = TesseractEngine(config)
    report = verify_samples(
        input_dir=input_dir,
        output_dir=output_dir,
        baseline_path=baseline_path,
        config=config,
        ocr_engine=engine,
    )
    for message in report.messages:
        print(message, file=stdout)

    return 0 if report.ok else 1
