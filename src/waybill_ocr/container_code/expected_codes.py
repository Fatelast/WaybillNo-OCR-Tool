from dataclasses import dataclass
from pathlib import Path

from openpyxl import load_workbook

from waybill_ocr.container_code.extractor import extract_candidates
from waybill_ocr.models import RecognitionResult, RecognitionStatus


@dataclass(frozen=True)
class ComparisonReport:
    expected_codes: list[str]
    recognized_codes: list[str]
    matched_codes: list[str]
    missing_codes: list[str]
    extra_codes: list[str]


def read_expected_codes(path: Path) -> list[str]:
    if path.suffix.lower() == ".xlsx":
        return _read_expected_codes_from_workbook(path)

    return _extract_unique_codes(path.read_text(encoding="utf-8-sig", errors="ignore"))


def compare_expected_codes(expected_codes: list[str], results: list[RecognitionResult]) -> ComparisonReport:
    normalized_expected = _dedupe(expected_codes)
    recognized_codes = _recognized_success_codes(results)
    recognized_set = set(recognized_codes)
    expected_set = set(normalized_expected)
    matched_codes = [code for code in normalized_expected if code in recognized_set]
    missing_codes = [code for code in normalized_expected if code not in recognized_set]
    extra_codes = [code for code in recognized_codes if code not in expected_set]
    return ComparisonReport(
        expected_codes=normalized_expected,
        recognized_codes=recognized_codes,
        matched_codes=matched_codes,
        missing_codes=missing_codes,
        extra_codes=extra_codes,
    )


def _read_expected_codes_from_workbook(path: Path) -> list[str]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        values = []
        for row in workbook.active.iter_rows(values_only=True):
            for value in row:
                if value is not None:
                    values.append(str(value))
        return _extract_unique_codes("\n".join(values))
    finally:
        workbook.close()


def _extract_unique_codes(text: str) -> list[str]:
    codes: list[str] = []
    for code in extract_candidates(text):
        if code not in codes:
            codes.append(code)
    return codes


def _recognized_success_codes(results: list[RecognitionResult]) -> list[str]:
    codes: list[str] = []
    for result in results:
        if result.status == RecognitionStatus.SUCCESS and result.container_code and result.container_code not in codes:
            codes.append(result.container_code)
    return codes


def _dedupe(codes: list[str]) -> list[str]:
    unique_codes: list[str] = []
    for code in codes:
        normalized = code.strip().upper()
        if normalized and normalized not in unique_codes:
            unique_codes.append(normalized)
    return unique_codes
