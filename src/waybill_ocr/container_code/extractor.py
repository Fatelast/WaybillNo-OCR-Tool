import re

from waybill_ocr.container_code.validator import is_valid_container_code


CANDIDATE_PATTERN = re.compile(r"[A-Z]{4}\s*\d{7}")


def extract_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    for candidate in _iter_normalized_candidates(text):
        if is_valid_container_code(candidate) and candidate not in candidates:
            candidates.append(candidate)

    return candidates


def extract_invalid_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    for candidate in _iter_normalized_candidates(text):
        if not is_valid_container_code(candidate) and candidate not in candidates:
            candidates.append(candidate)

    return candidates


def _iter_normalized_candidates(text: str):
    normalized = text.upper().replace("-", " ").replace("_", " ")
    for match in CANDIDATE_PATTERN.finditer(normalized):
        yield re.sub(r"\s+", "", match.group(0))
