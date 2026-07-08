from waybill_ocr.container_code.extractor import (
    extract_candidates,
    extract_guess_repair_suggestions,
    extract_suspicious_candidates,
)
from waybill_ocr.container_code.review_candidates import single_digit_check_repair, single_digit_check_repairs


def has_candidate_conflict(code: str, ocr_text: str) -> bool:
    valid_candidates = [candidate for candidate in extract_candidates(ocr_text) if candidate != code]
    if valid_candidates:
        return True

    prefix = code[:4]
    return any(candidate[:4] == prefix and candidate != code for candidate in extract_suspicious_candidates(ocr_text))


def build_conflict_review_note(code: str, ocr_text: str) -> str:
    suspicious = extract_suspicious_candidates(ocr_text)
    parts = [f"候选冲突，需人工复核: {code}"]
    if suspicious:
        parts.append(f"疑似候选: {', '.join(suspicious)}")
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
        displayed = ", ".join(repairs[:8])
        suffix = "..." if len(repairs) > 8 else ""
        return f"多个疑似校验修正候选（未自动采用）: {displayed}{suffix}"
    return None


def suspicious_note(ocr_text: str) -> str | None:
    candidates = extract_suspicious_candidates(ocr_text)
    suggestions = extract_guess_repair_suggestions(ocr_text)
    if not candidates and not suggestions:
        return None

    parts = []
    if candidates:
        parts.append(f"疑似候选: {', '.join(candidates)}")
    if suggestions:
        suggestion_text = ", ".join(f"{raw}->{repaired}" for raw, repaired in suggestions)
        if len(suggestions) == 1:
            suggestion_text = suggestions[0][1]
        parts.append(f"可能修正: {suggestion_text}（未自动采用）")
    return "；".join(parts)
