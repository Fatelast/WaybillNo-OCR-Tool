import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from waybill_ocr.batch_processor import process_directory
from waybill_ocr.config import AppConfig
from waybill_ocr.container_code.expected_codes import read_expected_codes
from waybill_ocr.container_code.validator import is_valid_container_code
from waybill_ocr.file_scanner import scan_input_files
from waybill_ocr.models import RecognitionResult, RecognitionStatus
from waybill_ocr.ocr.base import OcrEngine


BASELINE_HEADERS = [
    "filename",
    "expected_code",
    "expected_status",
    "allow_review_code",
    "quality_tag",
    "notes",
]
DRAFT_HEADERS = [
    *BASELINE_HEADERS,
    "confirmed",
    "observed_code",
    "observed_status",
    "observed_review_code",
    "match_basis",
]


@dataclass(frozen=True)
class BaselineDraftReport:
    draft_path: Path
    total: int
    suggested: int


@dataclass(frozen=True)
class BaselineImportReport:
    baseline_path: Path
    imported: int
    total: int


def prepare_sample_baseline(
    input_dir: Path,
    expected_path: Path,
    actual_dir: Path,
    draft_path: Path,
    config: AppConfig,
    ocr_engine: OcrEngine,
) -> BaselineDraftReport:
    results = process_directory(
        input_dir=input_dir,
        output_dir=actual_dir,
        config=config,
        ocr_engine=ocr_engine,
        skip_existing_successes=False,
    )
    expected_codes = read_expected_codes(expected_path)
    return write_baseline_draft(input_dir, expected_codes, results, draft_path)


def write_baseline_draft(
    input_dir: Path,
    expected_codes: list[str],
    results: list[RecognitionResult],
    draft_path: Path,
) -> BaselineDraftReport:
    expected_set = set(expected_codes)
    result_by_relative = {
        result.relative_name or result.original_name: result
        for result in results
    }
    proposed_codes = [_matching_observed_code(result, expected_set) for result in results]
    code_counts = Counter(code for code in proposed_codes if code is not None)

    rows: list[dict[str, str]] = []
    suggested = 0
    for task in scan_input_files(input_dir):
        result = result_by_relative.get(task.relative_name)
        row = _draft_row(task.relative_name, result, expected_set, code_counts)
        if row["expected_code"]:
            suggested += 1
        rows.append(row)

    draft_path.parent.mkdir(parents=True, exist_ok=True)
    _write_csv_atomically(draft_path, DRAFT_HEADERS, rows)
    return BaselineDraftReport(draft_path=draft_path, total=len(rows), suggested=suggested)


def import_sample_baseline(
    input_dir: Path,
    draft_path: Path,
    baseline_path: Path,
) -> BaselineImportReport:
    draft_rows = _read_csv_rows(draft_path)
    confirmed_rows = [row for row in draft_rows if _parse_bool(row.get("confirmed"))]
    normalized_rows = [_validated_baseline_row(input_dir, row) for row in confirmed_rows]

    filenames = [row["filename"] for row in normalized_rows]
    duplicates = sorted({filename for filename in filenames if filenames.count(filename) > 1})
    if duplicates:
        raise ValueError(f"\u8349\u7a3f\u4e2d\u5b58\u5728\u91cd\u590d\u6837\u672c\u8def\u5f84: {', '.join(duplicates)}")

    existing_rows = _read_csv_rows(baseline_path) if baseline_path.is_file() else []
    merged = {
        row.get("filename", "").strip(): _canonical_baseline_row(row)
        for row in existing_rows
        if row.get("filename", "").strip()
    }
    for row in normalized_rows:
        merged[row["filename"]] = row

    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    ordered_rows = [merged[filename] for filename in sorted(merged)]
    _write_csv_atomically(baseline_path, BASELINE_HEADERS, ordered_rows)
    return BaselineImportReport(
        baseline_path=baseline_path,
        imported=len(normalized_rows),
        total=len(ordered_rows),
    )


def _draft_row(
    relative_name: str,
    result: RecognitionResult | None,
    expected_codes: set[str],
    code_counts: dict[str, int],
) -> dict[str, str]:
    quality_tag = relative_name.split("/", 1)[0] if "/" in relative_name else ""
    if result is None:
        return {
            "filename": relative_name,
            "expected_code": "",
            "expected_status": "",
            "allow_review_code": "false",
            "quality_tag": quality_tag,
            "notes": "",
            "confirmed": "false",
            "observed_code": "",
            "observed_status": "\u672a\u5904\u7406",
            "observed_review_code": "",
            "match_basis": "\u672a\u627e\u5230\u5904\u7406\u7ed3\u679c",
        }

    matched_code = _matching_observed_code(result, expected_codes)
    unique_match = matched_code is not None and code_counts.get(matched_code) == 1
    if unique_match:
        match_basis = "\u6b63\u786e\u8bc6\u522b\u552f\u4e00\u5339\u914d" if result.status is RecognitionStatus.SUCCESS else "\u5f85\u786e\u8ba4\u5019\u9009\u552f\u4e00\u5339\u914d"
        notes = "\u9884\u671f\u6e05\u5355\u552f\u4e00\u5339\u914d\uff1b\u786e\u8ba4\u539f\u6587\u4ef6\u5185\u5bb9\u540e\u5c06 confirmed \u6539\u4e3a true"
    elif matched_code:
        match_basis = "\u5019\u9009\u5728\u591a\u4e2a\u6837\u672c\u4e2d\u91cd\u590d\uff0c\u9700\u4eba\u5de5\u6620\u5c04"
        notes = ""
    else:
        match_basis = "\u672a\u5339\u914d\u9884\u671f\u6e05\u5355"
        notes = ""

    return {
        "filename": relative_name,
        "expected_code": matched_code if unique_match else "",
        "expected_status": result.status.value if unique_match else "",
        "allow_review_code": str(unique_match and result.status is not RecognitionStatus.SUCCESS).lower(),
        "quality_tag": quality_tag,
        "notes": notes,
        "confirmed": "false",
        "observed_code": result.container_code or "",
        "observed_status": result.status.value,
        "observed_review_code": result.review_code or "",
        "match_basis": match_basis,
    }


def _matching_observed_code(result: RecognitionResult, expected_codes: set[str]) -> str | None:
    observed = result.container_code if result.status is RecognitionStatus.SUCCESS else result.review_code
    if observed and observed in expected_codes:
        return observed
    return None


def _validated_baseline_row(input_dir: Path, row: dict[str, str]) -> dict[str, str]:
    filename = row.get("filename", "").strip().replace("\\", "/")
    if not filename:
        raise ValueError("\u5df2\u786e\u8ba4\u8bb0\u5f55\u7f3a\u5c11 filename")

    root = input_dir.resolve()
    sample_path = (root / Path(filename)).resolve()
    try:
        sample_path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"\u6837\u672c\u8def\u5f84\u8d85\u51fa\u8f93\u5165\u76ee\u5f55: {filename}") from exc
    if not sample_path.is_file():
        raise ValueError(f"\u6837\u672c\u6587\u4ef6\u4e0d\u5b58\u5728: {filename}")

    status = row.get("expected_status", "").strip()
    valid_statuses = {item.value for item in RecognitionStatus}
    if status not in valid_statuses:
        raise ValueError(f"\u6837\u672c\u72b6\u6001\u65e0\u6548: {filename}: {status or '\u7a7a'}")

    expected_code = row.get("expected_code", "").strip().upper()
    allow_review = _parse_bool(row.get("allow_review_code"))
    if expected_code and not is_valid_container_code(expected_code):
        raise ValueError(f"\u9884\u671f\u7bb1\u53f7\u65e0\u6548: {filename}: {expected_code}")
    if status == RecognitionStatus.SUCCESS.value and not expected_code:
        raise ValueError(f"\u6b63\u786e\u8bc6\u522b\u6837\u672c\u5fc5\u987b\u586b\u5199\u9884\u671f\u7bb1\u53f7: {filename}")
    if allow_review and not expected_code:
        raise ValueError(f"\u5141\u8bb8\u5f85\u786e\u8ba4\u7684\u6837\u672c\u5fc5\u987b\u586b\u5199\u9884\u671f\u7bb1\u53f7: {filename}")

    return {
        "filename": filename,
        "expected_code": expected_code,
        "expected_status": status,
        "allow_review_code": str(allow_review).lower(),
        "quality_tag": row.get("quality_tag", "").strip(),
        "notes": row.get("notes", "").strip(),
    }


def _canonical_baseline_row(row: dict[str, str]) -> dict[str, str]:
    return {header: row.get(header, "").strip() for header in BASELINE_HEADERS}


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file_obj:
        return list(csv.DictReader(file_obj))


def _write_csv_atomically(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    with temporary_path.open("w", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary_path.replace(path)


def _parse_bool(value: str | None) -> bool:
    return bool(value and value.strip().lower() in {"1", "true", "yes", "y"})
