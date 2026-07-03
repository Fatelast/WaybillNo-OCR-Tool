import re

from waybill_ocr.container_code.validator import is_valid_container_code


CANDIDATE_PATTERN = re.compile(r"[A-Z]{3}U\s*\d{7}")
REPAIRABLE_EXTRA_OWNER_LETTER_PATTERN = re.compile(r"[A-Z]{4}U\s*\d{7}")
SUSPICIOUS_CANDIDATE_PATTERN = re.compile(r"[A-Z0-9]{3}U\s*[A-Z0-9]{7}")


GUESS_REPLACEMENTS = {
    "O": "0",
    "I": "1",
    "L": "1",
    "B": "8",
    "S": "5",
    "Z": "2",
}


def extract_guess_repair_suggestions(text: str) -> list[tuple[str, str]]:
    suggestions: list[tuple[str, str]] = []
    for candidate in _iter_suspicious_candidates(text):
        repaired = _guess_repair_candidate(candidate)
        if repaired and (candidate, repaired) not in suggestions:
            suggestions.append((candidate, repaired))
    return suggestions


def extract_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    for candidate in _iter_normalized_candidates(text):
        if is_valid_container_code(candidate) and candidate not in candidates:
            candidates.append(candidate)

    return candidates


def extract_repaired_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    for candidate in _iter_repairable_candidates(text):
        repaired = repair_extra_owner_letter(candidate)
        if repaired and repaired not in candidates:
            candidates.append(repaired)

    return candidates


def extract_invalid_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    for candidate in _iter_normalized_candidates(text):
        if not is_valid_container_code(candidate) and candidate not in candidates:
            candidates.append(candidate)

    return candidates



def extract_suspicious_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    for candidate in _iter_suspicious_candidates(text):
        if _needs_guess_replacement(candidate) and candidate not in candidates:
            candidates.append(candidate)

    return candidates


def _iter_normalized_candidates(text: str):
    normalized = text.upper().replace("-", " ").replace("_", " ")
    for match in CANDIDATE_PATTERN.finditer(normalized):
        yield re.sub(r"\s+", "", match.group(0))


def _iter_repairable_candidates(text: str):
    normalized = text.upper().replace("-", " ").replace("_", " ")
    for match in REPAIRABLE_EXTRA_OWNER_LETTER_PATTERN.finditer(normalized):
        yield re.sub(r"\s+", "", match.group(0))


def repair_extra_owner_letter(candidate: str) -> str | None:
    if len(candidate) != 12 or candidate[1] != "I":
        return None

    repaired = f"{candidate[0]}{candidate[2:]}"
    return repaired if is_valid_container_code(repaired) else None


def _iter_suspicious_candidates(text: str):
    normalized = text.upper().replace("-", " ").replace("_", " ")
    for match in SUSPICIOUS_CANDIDATE_PATTERN.finditer(normalized):
        yield re.sub(r"\s+", "", match.group(0))


def _needs_guess_replacement(candidate: str) -> bool:
    owner = candidate[:3]
    category = candidate[3:4]
    serial = candidate[4:]
    if category != "U":
        return False
    return not owner.isalpha() or not serial.isdigit()



def _guess_repair_candidate(candidate: str) -> str | None:
    if len(candidate) != 11 or candidate[3] != "U":
        return None
    owner = candidate[:3]
    serial = candidate[4:]
    if not owner.isalpha():
        return None
    repaired_serial = "".join(_guess_digit(char) for char in serial)
    if not repaired_serial.isdigit() or repaired_serial == serial:
        return None
    repaired = f"{owner}U{repaired_serial}"
    return repaired if is_valid_container_code(repaired) else None


def _guess_digit(char: str) -> str:
    if char.isdigit():
        return char
    return GUESS_REPLACEMENTS.get(char, char)
