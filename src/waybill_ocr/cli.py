import argparse
import sys
from pathlib import Path
from typing import TextIO

from waybill_ocr.batch_processor import process_directory
from waybill_ocr.container_code.expected_codes import read_expected_codes
from waybill_ocr.config import default_config, resolve_default_work_dir
from waybill_ocr.diagnostics import format_diagnostic_messages, inspect_environment
from waybill_ocr.ocr.tesseract_engine import TesseractEngine
from waybill_ocr.sample_baseline import import_sample_baseline, prepare_sample_baseline
from waybill_ocr.sample_verifier import resolve_default_baseline_path, verify_samples


DEFAULT_SAMPLE_INPUT = Path("samples/cases")
DEFAULT_SAMPLE_OUTPUT = Path("samples/actual")
DEFAULT_SAMPLE_BASELINE = resolve_default_baseline_path()
DEFAULT_SAMPLE_DRAFT = Path("samples/expected/baseline.draft.csv")


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

    if args.command == "prepare-sample-baseline":
        return _run_prepare_sample_baseline(args, output)

    if args.command == "import-sample-baseline":
        return _run_import_sample_baseline(args, output)

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

    prepare_parser = subparsers.add_parser("prepare-sample-baseline", help="\u751f\u6210\u5f85\u4eba\u5de5\u786e\u8ba4\u7684\u6837\u672c\u57fa\u7ebf\u8349\u7a3f")
    prepare_parser.add_argument("--input", default=str(DEFAULT_SAMPLE_INPUT), dest="input_dir", help="\u6837\u672c\u8f93\u5165\u6587\u4ef6\u5939")
    prepare_parser.add_argument("--expected", required=True, dest="expected_path", help="\u9884\u671f\u7bb1\u53f7\u6e05\u5355")
    prepare_parser.add_argument("--output", default=str(DEFAULT_SAMPLE_OUTPUT), dest="output_dir", help="\u6837\u672c\u8bc6\u522b\u8f93\u51fa\u6587\u4ef6\u5939")
    prepare_parser.add_argument("--draft", default=str(DEFAULT_SAMPLE_DRAFT), dest="draft_path", help="\u57fa\u7ebf\u8349\u7a3f CSV")

    import_parser = subparsers.add_parser("import-sample-baseline", help="\u5bfc\u5165\u5df2\u4eba\u5de5\u786e\u8ba4\u7684\u6837\u672c\u57fa\u7ebf\u8349\u7a3f")
    import_parser.add_argument("--input", default=str(DEFAULT_SAMPLE_INPUT), dest="input_dir", help="\u6837\u672c\u8f93\u5165\u6587\u4ef6\u5939")
    import_parser.add_argument("--draft", default=str(DEFAULT_SAMPLE_DRAFT), dest="draft_path", help="\u57fa\u7ebf\u8349\u7a3f CSV")
    import_parser.add_argument(
        "--baseline",
        default="samples/expected/baseline.local.csv",
        dest="baseline_path",
        help="\u672c\u5730\u6837\u672c\u57fa\u7ebf CSV",
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


def _run_prepare_sample_baseline(args: argparse.Namespace, stdout: TextIO) -> int:
    input_dir = Path(args.input_dir)
    expected_path = Path(args.expected_path)
    if not input_dir.is_dir():
        print(f"\u6837\u672c\u8f93\u5165\u6587\u4ef6\u5939\u4e0d\u5b58\u5728: {input_dir}", file=stdout)
        return 2
    if not expected_path.is_file():
        print(f"\u9884\u671f\u7bb1\u53f7\u6e05\u5355\u4e0d\u5b58\u5728: {expected_path}", file=stdout)
        return 2

    config = default_config(work_dir=resolve_default_work_dir())
    report = prepare_sample_baseline(
        input_dir=input_dir,
        expected_path=expected_path,
        actual_dir=Path(args.output_dir),
        draft_path=Path(args.draft_path),
        config=config,
        ocr_engine=TesseractEngine(config),
    )
    print(f"\u6837\u672c\u57fa\u7ebf\u8349\u7a3f\u5df2\u751f\u6210: {report.draft_path}", file=stdout)
    print(f"\u5171 {report.total} \u4e2a\u6837\u672c\uff0c\u5efa\u8bae\u5339\u914d {report.suggested} \u4e2a\uff1b\u786e\u8ba4\u540e\u5c06 confirmed \u6539\u4e3a true\u3002", file=stdout)
    return 0


def _run_import_sample_baseline(args: argparse.Namespace, stdout: TextIO) -> int:
    input_dir = Path(args.input_dir)
    draft_path = Path(args.draft_path)
    if not input_dir.is_dir():
        print(f"\u6837\u672c\u8f93\u5165\u6587\u4ef6\u5939\u4e0d\u5b58\u5728: {input_dir}", file=stdout)
        return 2
    if not draft_path.is_file():
        print(f"\u6837\u672c\u57fa\u7ebf\u8349\u7a3f\u4e0d\u5b58\u5728: {draft_path}", file=stdout)
        return 2

    try:
        report = import_sample_baseline(
            input_dir=input_dir,
            draft_path=draft_path,
            baseline_path=Path(args.baseline_path),
        )
    except ValueError as exc:
        print(f"\u6837\u672c\u57fa\u7ebf\u5bfc\u5165\u5931\u8d25: {exc}", file=stdout)
        return 2

    print(f"\u6837\u672c\u57fa\u7ebf\u5df2\u66f4\u65b0: {report.baseline_path}", file=stdout)
    print(f"\u672c\u6b21\u5bfc\u5165 {report.imported} \u6761\uff0c\u57fa\u7ebf\u5171 {report.total} \u6761\u3002", file=stdout)
    return 0
