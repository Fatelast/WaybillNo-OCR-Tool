import re

from waybill_ocr.container_code.validator import is_valid_container_code


CANDIDATE_PATTERN = re.compile(r"[A-Z]{4}\s*\d{7}")


def extract_candidates(text: str) -> list[str]:
    normalized = text.upper().replace("-", " ").replace("_", " ")
    candidates: list[str] = []

    for match in CANDIDATE_PATTERN.finditer(normalized):
        candidate = re.sub(r"\s+", "", match.group(0))
        if is_valid_container_code(candidate) and candidate not in candidates:
            candidates.append(candidate)

    return candidates
