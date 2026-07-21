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
    expected_status: RecognitionStatus | None = None
    allow_review_code: bool = False
    quality_tag: str = ""
    notes: str = ""


def resolve_default_baseline_path(expected_dir: Path = Path("samples/expected")) -> Path:
    local_path = expected_dir / "baseline.local.csv"
    if local_path.is_file():
        return local_path
    return expected_dir / "baseline.csv"


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
    results_by_relative = {result.relative_name: result for result in results if result.relative_name}
    results_by_name = {result.original_name: result for result in results}

    failures: list[str] = []
    category_totals: dict[str, int] = {}
    category_passed: dict[str, int] = {}
    passed = 0
    for expectation in expectations:
        category = _quality_category(expectation)
        if category:
            category_totals[category] = category_totals.get(category, 0) + 1

        result = results_by_relative.get(expectation.filename) or results_by_name.get(expectation.filename)
        if result is None:
            failures.append(f"{expectation.filename}: \u672a\u5728\u5904\u7406\u7ed3\u679c\u4e2d\u627e\u5230\u8be5\u6837\u672c")
            continue

        failure = _compare_result(expectation, result)
        if failure:
            failures.append(failure)
            continue

        passed += 1
        if category:
            category_passed[category] = category_passed.get(category, 0) + 1

    total = len(expectations)
    status_message = (
        f"\u6837\u672c\u9a8c\u6536\u5931\u8d25: {passed}/{total}"
        if failures
        else f"\u6837\u672c\u9a8c\u6536\u901a\u8fc7: {passed}/{total}"
    )
    messages = [status_message, *_category_summary_messages(expectations, category_totals, category_passed)]
    if failures:
        return SampleVerificationReport(ok=False, messages=[*messages, *failures])

    return SampleVerificationReport(ok=True, messages=messages)

def _read_baseline(baseline_path: Path) -> list[BaselineExpectation]:
    with baseline_path.open("r", encoding="utf-8", newline="") as file_obj:
        rows = csv.DictReader(file_obj)
        return [_expectation_from_row(row) for row in rows]


def _quality_category(expectation: BaselineExpectation) -> str:
    return expectation.quality_tag.strip()


def _category_summary_messages(
    expectations: list[BaselineExpectation],
    category_totals: dict[str, int],
    category_passed: dict[str, int],
) -> list[str]:
    if not _uses_structured_baseline(expectations) or not category_totals:
        return []

    messages = ["\u5206\u7c7b\u7edf\u8ba1:"]
    for category in sorted(category_totals):
        messages.append(f"- {category}: {category_passed.get(category, 0)}/{category_totals[category]}")
    return messages


def _uses_structured_baseline(expectations: list[BaselineExpectation]) -> bool:
    return any(expectation.expected_status is not None or "/" in expectation.filename for expectation in expectations)


def _expectation_from_row(row: dict[str, str]) -> BaselineExpectation:
    expected_status = _parse_status(row.get("expected_status", ""))
    should_recognize = _parse_bool(row.get("should_recognize", ""))
    if expected_status is not None:
        should_recognize = expected_status == RecognitionStatus.SUCCESS
    return BaselineExpectation(
        filename=row["filename"],
        expected_code=row.get("expected_code") or None,
        should_recognize=should_recognize,
        expected_status=expected_status,
        allow_review_code=_parse_bool(row.get("allow_review_code", "")),
        quality_tag=row.get("quality_tag", ""),
        notes=row.get("notes", ""),
    )


def _parse_bool(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y"}


def _parse_status(value: str | None) -> RecognitionStatus | None:
    if not value or not value.strip():
        return None
    normalized = value.strip().lower()
    status_aliases = {
        "success": RecognitionStatus.SUCCESS,
        "recognized": RecognitionStatus.SUCCESS,
        RecognitionStatus.SUCCESS.value.lower(): RecognitionStatus.SUCCESS,
        "unrecognized": RecognitionStatus.UNRECOGNIZED,
        RecognitionStatus.UNRECOGNIZED.value.lower(): RecognitionStatus.UNRECOGNIZED,
        "invalid": RecognitionStatus.INVALID,
        RecognitionStatus.INVALID.value.lower(): RecognitionStatus.INVALID,
    }
    return status_aliases.get(normalized)


def _compare_result(expectation: BaselineExpectation, result: RecognitionResult) -> str | None:
    if expectation.expected_status is not None:
        return _compare_result_by_status(expectation, result)

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


def _compare_result_by_status(expectation: BaselineExpectation, result: RecognitionResult) -> str | None:
    if result.status != expectation.expected_status:
        return (
            f"{expectation.filename}: 期望状态 {expectation.expected_status.value}，"
            f"实际状态为 {result.status.value}"
        )

    if result.status == RecognitionStatus.SUCCESS and result.container_code != expectation.expected_code:
        return (
            f"{expectation.filename}: 期望识别 {expectation.expected_code or ''}，"
            f"实际为 {result.container_code or ''}"
        )

    if result.status != RecognitionStatus.SUCCESS and result.review_code:
        if not expectation.allow_review_code:
            return f"{expectation.filename}: 不允许待确认候选，实际为 {result.review_code}"
        if expectation.expected_code and result.review_code != expectation.expected_code:
            return (
                f"{expectation.filename}: 期望待确认 {expectation.expected_code}，"
                f"实际为 {result.review_code}"
            )

    return None
