from dataclasses import dataclass
from typing import Callable

from waybill_ocr.container_code.candidate_selector import CandidateText, rank_valid_candidates
from waybill_ocr.container_code.extractor import (
    extract_candidates,
    extract_guess_repair_suggestions,
    extract_suspicious_candidates,
)
from waybill_ocr.container_code.review_candidates import single_digit_check_repair, single_digit_check_repairs


@dataclass(frozen=True)
class CandidateConflictAssessment:
    selected_code: str
    selected_support_count: int
    competing_valid_codes: tuple[str, ...]
    repeated_suspicious_candidates: tuple[str, ...]
    requires_cross_validation: bool
    has_strong_conflict: bool


def assess_candidate_conflict(
    code: str,
    texts: list[CandidateText],
    *,
    region_key: Callable[[str], str] | None = None,
) -> CandidateConflictAssessment:
    normalize_region = region_key or (lambda value: value)
    valid_supports: dict[str, set[str]] = {}
    suspicious_supports: dict[str, set[str]] = {}
    prefix = code[:4]

    for item in texts:
        evidence_region = normalize_region(item.region_name)
        for candidate in set(extract_candidates(item.text)):
            valid_supports.setdefault(candidate, set()).add(evidence_region)
        for candidate in set(extract_suspicious_candidates(item.text)):
            if candidate != code and candidate[:4] == prefix:
                suspicious_supports.setdefault(candidate, set()).add(evidence_region)

    scores = {selection.code: selection.score for selection in rank_valid_candidates(texts)}
    selected_support_count = len(valid_supports.get(code, set()))
    selected_score = scores.get(code, 0)
    competing_codes = sorted(candidate for candidate in valid_supports if candidate != code)
    strong_competing_codes = [
        candidate
        for candidate in competing_codes
        if (
            len(valid_supports[candidate]) >= 2
            or selected_support_count <= 1
            or scores.get(candidate, 0) >= selected_score
        )
    ]
    repeated_suspicious = sorted(
        candidate
        for candidate, regions in suspicious_supports.items()
        if len(regions) >= 2
    )
    has_same_prefix_suspicion = bool(suspicious_supports)
    single_candidate_suspicion = selected_support_count <= 1 and has_same_prefix_suspicion
    has_strong_conflict = bool(strong_competing_codes or repeated_suspicious or single_candidate_suspicion)
    requires_cross_validation = has_strong_conflict
    return CandidateConflictAssessment(
        selected_code=code,
        selected_support_count=selected_support_count,
        competing_valid_codes=tuple(competing_codes),
        repeated_suspicious_candidates=tuple(repeated_suspicious),
        requires_cross_validation=requires_cross_validation,
        has_strong_conflict=has_strong_conflict,
    )


def has_candidate_conflict(code: str, ocr_text: str) -> bool:
    assessment = assess_candidate_conflict(
        code,
        [CandidateText(text=ocr_text, region_name="combined")],
    )
    return assessment.requires_cross_validation


def build_conflict_review_note(code: str, ocr_text: str) -> str:
    suspicious = extract_suspicious_candidates(ocr_text)
    parts = [f"候选冲突，需人工复核: {code}"]
    if suspicious:
        parts.append(f"疑似候选: {_format_candidates(suspicious)}")
    return "；".join(parts)


def review_code_for_invalid_candidate(candidate: str, ocr_text: str) -> str | None:
    repair = single_digit_check_repair(candidate)
    if repair:
        return repair
    return review_code_from_text(ocr_text)


def review_code_from_text(ocr_text: str) -> str | None:
    repaired_codes = {repaired for _raw, repaired in extract_guess_repair_suggestions(ocr_text)}
    if len(repaired_codes) == 1:
        return next(iter(repaired_codes))
    return None


def invalid_review_note(candidate: str, fallback_note: str | None = None) -> str | None:
    repair_note = format_single_digit_repair_note(candidate)
    if repair_note:
        return f"{repair_note}；{fallback_note}" if fallback_note else repair_note
    return fallback_note


def format_single_digit_repair_note(candidate: str) -> str | None:
    repairs = single_digit_check_repairs(candidate)
    if len(repairs) == 1:
        return f"疑似校验修正: {candidate} -> {repairs[0]}（待人工确认）"
    if len(repairs) > 1:
        return f"多个疑似校验修正候选（未自动采用）: {_format_candidates(repairs)}"
    return None


def suspicious_note(ocr_text: str) -> str | None:
    candidates = extract_suspicious_candidates(ocr_text)
    suggestions = extract_guess_repair_suggestions(ocr_text)
    if not candidates and not suggestions:
        return None

    parts = []
    if candidates:
        parts.append(f"疑似候选: {_format_candidates(candidates)}")
    if suggestions:
        suggestion_text = _format_candidates([f"{raw}->{repaired}" for raw, repaired in suggestions])
        if len(suggestions) == 1:
            suggestion_text = suggestions[0][1]
        parts.append(f"可能修正: {suggestion_text}（未自动采用）")
    return "；".join(parts)


def _format_candidates(values: list[str], limit: int = 8) -> str:
    unique_values = list(dict.fromkeys(values))
    displayed = ", ".join(unique_values[:limit])
    if len(unique_values) <= limit:
        return displayed
    return f"{displayed} 等 {len(unique_values)} 个"
