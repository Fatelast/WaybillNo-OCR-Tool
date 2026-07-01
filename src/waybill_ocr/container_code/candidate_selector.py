import re
from dataclasses import dataclass

from waybill_ocr.container_code.extractor import CANDIDATE_PATTERN
from waybill_ocr.container_code.validator import is_valid_container_code


CONTAINER_TYPE_PATTERN = re.compile(r"\d{2}[A-Z]\d")
CONTEXT_KEYWORDS = ("CONTAINER", "CNTR", "CTNR", "CONT", "箱号", "柜号")


@dataclass(frozen=True)
class CandidateText:
    text: str
    region_name: str


@dataclass(frozen=True)
class CandidateSelection:
    code: str
    score: int


@dataclass(frozen=True)
class _ScoredCandidate:
    code: str
    score: int
    order: int


def select_best_candidate(texts: list[CandidateText]) -> str | None:
    selection = select_best_candidate_with_score(texts)
    return selection.code if selection else None


def select_best_candidate_with_score(texts: list[CandidateText]) -> CandidateSelection | None:
    scored: dict[str, _ScoredCandidate] = {}
    order = 0
    for item in texts:
        normalized = item.text.upper().replace("-", " ").replace("_", " ")
        for match in CANDIDATE_PATTERN.finditer(normalized):
            code = re.sub(r"\s+", "", match.group(0))
            if not is_valid_container_code(code):
                continue

            context = normalized[max(0, match.start() - 24) : match.end() + 24]
            score = _score_candidate(context, item.region_name)
            current = scored.get(code)
            if current is None:
                scored[code] = _ScoredCandidate(code=code, score=score, order=order)
                order += 1
            else:
                scored[code] = _ScoredCandidate(
                    code=code,
                    score=max(current.score, score) + 5,
                    order=current.order,
                )

    if not scored:
        return None

    best = max(scored.values(), key=lambda item: (item.score, -item.order))
    return CandidateSelection(code=best.code, score=best.score)


def _score_candidate(context: str, region_name: str) -> int:
    score = 100
    if region_name != "full":
        score += 20
    if CONTAINER_TYPE_PATTERN.search(context):
        score += 40
    if any(keyword in context for keyword in CONTEXT_KEYWORDS):
        score += 25
    return score
