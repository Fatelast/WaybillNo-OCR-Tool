import re
from dataclasses import dataclass

from waybill_ocr.container_code.extractor import (
    CANDIDATE_PATTERN,
    REPAIRABLE_EXTRA_OWNER_LETTER_PATTERN,
    repair_extra_owner_letter,
)
from waybill_ocr.container_code.validator import is_valid_container_code


CONTAINER_TYPE_PATTERN = re.compile(r"\d{2}[A-Z]\d")
CONTEXT_KEYWORDS = ("CONTAINER", "CNTR", "CTNR", "CONT", "箱号", "柜号")
REPAIRED_CANDIDATE_PENALTY = 30


@dataclass(frozen=True)
class CandidateText:
    text: str
    region_name: str


@dataclass(frozen=True)
class CandidateSelection:
    code: str
    score: int
    is_repaired: bool = False
    raw_candidate: str | None = None


@dataclass(frozen=True)
class _ScoredCandidate:
    code: str
    score: int
    order: int
    is_repaired: bool
    raw_candidate: str | None


def select_best_candidate(texts: list[CandidateText]) -> str | None:
    selection = select_best_candidate_with_score(texts)
    return selection.code if selection else None


def select_best_candidate_with_score(texts: list[CandidateText]) -> CandidateSelection | None:
    clear_selection = _select_clear_candidate(texts)
    if clear_selection:
        return clear_selection

    return _select_repaired_candidate(texts)


def _select_clear_candidate(texts: list[CandidateText]) -> CandidateSelection | None:
    return _select_candidates(texts, _iter_clear_matches)


def _select_repaired_candidate(texts: list[CandidateText]) -> CandidateSelection | None:
    return _select_candidates(texts, _iter_repaired_matches)


def _select_candidates(texts: list[CandidateText], match_iter):
    scored: dict[str, _ScoredCandidate] = {}
    order = 0
    for item in texts:
        normalized = item.text.upper().replace("-", " ").replace("_", " ")
        for code, start, end, penalty, raw_candidate, is_repaired in match_iter(normalized):
            context = normalized[max(0, start - 24) : end + 24]
            score = _score_candidate(context, item.region_name) - penalty
            current = scored.get(code)
            if current is None:
                scored[code] = _ScoredCandidate(
                    code=code,
                    score=score,
                    order=order,
                    is_repaired=is_repaired,
                    raw_candidate=raw_candidate,
                )
                order += 1
            else:
                scored[code] = _ScoredCandidate(
                    code=code,
                    score=max(current.score, score) + 5,
                    order=current.order,
                    is_repaired=current.is_repaired,
                    raw_candidate=current.raw_candidate,
                )

    if not scored:
        return None

    best = max(scored.values(), key=lambda item: (item.score, -item.order))
    return CandidateSelection(
        code=best.code,
        score=best.score,
        is_repaired=best.is_repaired,
        raw_candidate=best.raw_candidate,
    )


def _iter_clear_matches(normalized: str):
    for match in CANDIDATE_PATTERN.finditer(normalized):
        code = re.sub(r"\s+", "", match.group(0))
        if is_valid_container_code(code):
            yield code, match.start(), match.end(), 0, code, False


def _iter_repaired_matches(normalized: str):
    for match in REPAIRABLE_EXTRA_OWNER_LETTER_PATTERN.finditer(normalized):
        raw_code = re.sub(r"\s+", "", match.group(0))
        repaired = repair_extra_owner_letter(raw_code)
        if repaired:
            yield repaired, match.start(), match.end(), REPAIRED_CANDIDATE_PENALTY, raw_code, True


def _score_candidate(context: str, region_name: str) -> int:
    score = 100
    if region_name != "full":
        score += 20
    if CONTAINER_TYPE_PATTERN.search(context):
        score += 40
    if any(keyword in context for keyword in CONTEXT_KEYWORDS):
        score += 25
    return score
