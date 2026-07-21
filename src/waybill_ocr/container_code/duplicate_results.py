from collections import defaultdict
from dataclasses import replace

from waybill_ocr.models import RecognitionResult, RecognitionStatus


DUPLICATE_CONTAINER_CODE_REASON = "DUPLICATE_CONTAINER_CODE"
DUPLICATE_NOTE_PREFIX = "\u91cd\u590d\u7bb1\u53f7\u51b2\u7a81\uff1a"


def mark_duplicate_container_results(
    results: list[RecognitionResult],
) -> tuple[list[RecognitionResult], tuple[int, ...]]:
    """Mark every repeated successful code as requiring manual review."""
    grouped_indices: dict[str, list[int]] = defaultdict(list)
    for index, result in enumerate(results):
        code = _tracked_code(result)
        if code:
            grouped_indices[code].append(index)

    updated = list(results)
    changed_indices: list[int] = []
    for code, indices in grouped_indices.items():
        if len(indices) < 2:
            continue
        note = (
            f"{DUPLICATE_NOTE_PREFIX}\u540c\u4e00\u6279\u6b21\u6709 {len(indices)} \u4e2a\u6587\u4ef6"
            f"\u8bc6\u522b\u4e3a {code}\uff0c\u9700\u4eba\u5de5\u786e\u8ba4"
        )
        for index in indices:
            result = updated[index]
            review_note = _replace_duplicate_note(result.review_note, note)
            replacement = replace(
                result,
                status=RecognitionStatus.INVALID,
                failure_reason=DUPLICATE_CONTAINER_CODE_REASON,
                review_code=code,
                review_note=review_note,
            )
            if replacement != result:
                updated[index] = replacement
                changed_indices.append(index)

    return updated, tuple(changed_indices)


def _tracked_code(result: RecognitionResult) -> str | None:
    if result.status is RecognitionStatus.SUCCESS:
        return result.container_code
    if result.failure_reason == DUPLICATE_CONTAINER_CODE_REASON:
        return result.review_code or result.container_code
    return None


def _replace_duplicate_note(current_note: str | None, duplicate_note: str) -> str:
    parts = [
        part.strip()
        for part in (current_note or "").split("; ")
        if part.strip() and not part.strip().startswith(DUPLICATE_NOTE_PREFIX)
    ]
    parts.append(duplicate_note)
    return "; ".join(parts)
