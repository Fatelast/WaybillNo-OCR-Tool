import csv
from dataclasses import dataclass
from pathlib import Path

from waybill_ocr.batch_processor import process_directory
from waybill_ocr.config import AppConfig
from waybill_ocr.models import RecognitionResult, RecognitionStatus
from waybill_ocr.ocr.base import OcrEngine


@dataclass(frozen=True)
class SampleVerificationReport:
    ok: bool
    messages: list[str]


@dataclass(frozen=True)
class BaselineExpectation:
    filename: str
    expected_code: str | None
    should_recognize: bool


def verify_samples(
    input_dir: Path,
    output_dir: Path,
    baseline_path: Path,
    config: AppConfig,
    ocr_engine: OcrEngine,
) -> SampleVerificationReport:
    expectations = _read_baseline(baseline_path)
    results = process_directory(
        input_dir=input_dir,
        output_dir=output_dir,
        config=config,
        ocr_engine=ocr_engine,
    )
    results_by_name = {result.original_name: result for result in results}

    failures: list[str] = []
    passed = 0
    for expectation in expectations:
        result = results_by_name.get(expectation.filename)
        if result is None:
            failures.append(f"{expectation.filename}: 未在处理结果中找到该样本")
            continue

        failure = _compare_result(expectation, result)
        if failure:
            failures.append(failure)
            continue

        passed += 1

    total = len(expectations)
    if failures:
        return SampleVerificationReport(
            ok=False,
            messages=[f"样本验收失败: {passed}/{total}", *failures],
        )

    return SampleVerificationReport(ok=True, messages=[f"样本验收通过: {passed}/{total}"])


def _read_baseline(baseline_path: Path) -> list[BaselineExpectation]:
    with baseline_path.open("r", encoding="utf-8", newline="") as file_obj:
        rows = csv.DictReader(file_obj)
        return [
            BaselineExpectation(
                filename=row["filename"],
                expected_code=row["expected_code"] or None,
                should_recognize=_parse_bool(row["should_recognize"]),
            )
            for row in rows
        ]


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}


def _compare_result(expectation: BaselineExpectation, result: RecognitionResult) -> str | None:
    if expectation.should_recognize:
        if result.status != RecognitionStatus.SUCCESS:
            return (
                f"{expectation.filename}: 期望识别 {expectation.expected_code or ''}，"
                f"实际状态为 {result.status.value}"
            )
        if result.container_code != expectation.expected_code:
            return (
                f"{expectation.filename}: 期望识别 {expectation.expected_code or ''}，"
                f"实际为 {result.container_code or ''}"
            )
        return None

    if result.status == RecognitionStatus.SUCCESS:
        return f"{expectation.filename}: 期望不识别，实际识别为 {result.container_code or ''}"

    return None
