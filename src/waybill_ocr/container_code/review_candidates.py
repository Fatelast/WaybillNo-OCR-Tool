from dataclasses import replace

from waybill_ocr.container_code.extractor import (
    extract_candidates,
    extract_guess_repair_suggestions,
    extract_invalid_candidates,
)
from waybill_ocr.container_code.validator import is_valid_container_code
from waybill_ocr.models import RecognitionResult, RecognitionStatus

REVIEWABLE_STATUSES = {RecognitionStatus.UNRECOGNIZED, RecognitionStatus.INVALID}


def apply_expected_review_code(result: RecognitionResult, expected_codes: list[str] | None) -> RecognitionResult:
    if not expected_codes or result.review_code or result.status not in REVIEWABLE_STATUSES:
        return result

    expected_set = {code.strip().upper() for code in expected_codes if code and code.strip()}
    if not expected_set:
        return result

    candidates = collect_review_candidates(result.ocr_text, result.container_code)
    matches = [candidate for candidate in candidates if candidate in expected_set]
    if len(matches) == 1:
        return replace(
            result,
            review_code=matches[0],
            review_note=_append_review_note(result.review_note, f"预期清单唯一匹配待确认: {matches[0]}"),
        )
    if len(matches) > 1:
        return replace(
            result,
            review_note=_append_review_note(
                result.review_note,
                f"多个预期清单候选命中（未自动采用）: {', '.join(matches)}",
            ),
        )
    return result


def collect_review_candidates(ocr_text: str, container_code: str | None = None) -> list[str]:
    candidates: list[str] = []
    _extend_unique(candidates, extract_candidates(ocr_text))
    _extend_unique(candidates, [repaired for _raw, repaired in extract_guess_repair_suggestions(ocr_text)])

    invalid_candidates: list[str] = []
    if container_code:
        invalid_candidates.append(container_code)
    invalid_candidates.extend(extract_invalid_candidates(ocr_text))
    for invalid_candidate in invalid_candidates:
        _extend_unique(candidates, single_digit_check_repairs(invalid_candidate))

    return candidates


def single_digit_check_repair(candidate: str) -> str | None:
    repairs = single_digit_check_repairs(candidate)
    if len(repairs) == 1:
        return repairs[0]
    return None


def single_digit_check_repairs(candidate: str) -> list[str]:
    candidate = candidate.strip().upper()
    if len(candidate) != 11 or not candidate[:3].isalpha() or candidate[3] != "U" or not candidate[4:].isdigit():
        return []

    repairs: list[str] = []
    for index in range(4, 10):
        original_digit = candidate[index]
        for digit in "0123456789":
            if digit == original_digit:
                continue
            repaired = f"{candidate[:index]}{digit}{candidate[index + 1:]}"
            if is_valid_container_code(repaired) and repaired not in repairs:
                repairs.append(repaired)
    return repairs


def _extend_unique(target: list[str], values) -> None:
    for value in values:
        normalized = value.strip().upper()
        if normalized and normalized not in target:
            target.append(normalized)


def _append_review_note(current: str | None, addition: str) -> str:
    if current:
        return f"{current}；{addition}"
    return addition