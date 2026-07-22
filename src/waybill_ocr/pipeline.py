import re
import time
from itertools import combinations, islice

from waybill_ocr.cancellation import ProcessingCancelled, raise_if_cancelled
from waybill_ocr.config import AppConfig, OCR_SPEED_BALANCED, OCR_SPEED_FAST, OCR_SPEED_STABLE
from waybill_ocr.container_code.candidate_selector import (
    CandidateText,
    CandidateSelection,
    has_clear_review_winner,
    score_review_candidates,
    select_best_candidate_with_score,
)
from waybill_ocr.container_code.decision import (
    assess_candidate_conflict,
    build_conflict_review_note,
    invalid_review_note as build_invalid_review_note,
    review_code_for_invalid_candidate as decide_review_code_for_invalid_candidate,
    review_code_from_text as decide_review_code_from_text,
    suspicious_note as build_suspicious_note,
)
from waybill_ocr.container_code.review_candidates import single_digit_check_repairs
from waybill_ocr.container_code.extractor import (
    extract_candidates,
    extract_invalid_candidates,
    extract_suspicious_candidates,
)
from waybill_ocr.container_code.validator import is_valid_container_code
from waybill_ocr.image_loader import iter_images_for_ocr
from waybill_ocr.image_regions import OcrRegion, iter_enhanced_ocr_regions, iter_grid_ocr_regions, iter_priority_ocr_regions
from waybill_ocr.models import FileTask, RecognitionResult, RecognitionSource, RecognitionStatus
from waybill_ocr.ocr.base import OcrEngine


STRONG_CANDIDATE_SCORE = 140
CONFLICTING_CANDIDATES_REASON = "CONFLICTING_CANDIDATES"
INSUFFICIENT_CANDIDATE_EVIDENCE_REASON = "INSUFFICIENT_CANDIDATE_EVIDENCE"
REGION_CROP_FAILURE_MARKER = "\u533a\u57df\u88c1\u526a\u5931\u8d25"
REGION_CROP_SKIP_MARKER = "\u533a\u57df\u88c1\u526a\u8df3\u8fc7"
REGION_CROP_FAILURE_NOTE = "\u533a\u57df\u88c1\u526a\u5931\u8d25/\u8df3\u8fc7\uff0c\u53ef\u80fd\u56fe\u7247\u635f\u574f\u6216\u65e0\u6cd5\u8bfb\u53d6\u533a\u57df"
REGION_OCR_FAILURE_MARKER = "\u533a\u57df OCR \u5931\u8d25"
ENHANCED_PSM_MODES = (6, 11)
GRID_REGION_PATTERN = re.compile(r"cell-r(\d+)-c(\d+)$")
PRIORITY_REGION_BOXES = {
    "priority-left-middle": (0, 420, 580, 660),
    "priority-left-upper": (0, 80, 620, 340),
    "priority-full-middle": (0, 360, 1000, 680),
    "priority-left-lower-middle": (0, 540, 640, 820),
}


def process_file(task: FileTask, config: AppConfig, ocr_engine: OcrEngine, cancel_event=None) -> RecognitionResult:
    started = time.perf_counter()
    combined_text = ""
    image_iterator = None

    try:
        raise_if_cancelled(cancel_event)
        image_iterator = iter(iter_images_for_ocr(task.source_path, config))
        for image_path in image_iterator:
            raise_if_cancelled(cancel_event)
            candidate_texts: list[CandidateText] = []

            full_region = OcrRegion(image_path=image_path, region_name="full")
            combined_text = _recognize_region(ocr_engine, full_region, candidate_texts, combined_text, cancel_event)
            full_selection = select_best_candidate_with_score(candidate_texts)
            if (
                full_selection
                and full_selection.score >= STRONG_CANDIDATE_SCORE
                and not _needs_pdf_cross_validation(task, config, full_selection, candidate_texts)
            ):
                result, combined_text = _resolve_valid_selection(
                    task=task,
                    config=config,
                    ocr_engine=ocr_engine,
                    image_path=image_path,
                    selection=full_selection,
                    candidate_texts=candidate_texts,
                    combined_text=combined_text,
                    started=started,
                    cancel_event=cancel_event,
                )
                if result:
                    return result

            combined_text = _recognize_regions(
                ocr_engine=ocr_engine,
                regions=_priority_regions_for_mode(image_path, config),
                candidate_texts=candidate_texts,
                combined_text=combined_text,
                cancel_event=cancel_event,
                stop_on_confirmed_candidate=True,
            )
            selection = select_best_candidate_with_score(candidate_texts)
            if selection:
                result, combined_text = _resolve_valid_selection(
                    task=task,
                    config=config,
                    ocr_engine=ocr_engine,
                    image_path=image_path,
                    selection=selection,
                    candidate_texts=candidate_texts,
                    combined_text=combined_text,
                    started=started,
                    cancel_event=cancel_event,
                )
                if result:
                    return result

            if _should_run_grid(config):
                skip_grid_for_review_signal = (
                    config.ocr_speed_mode == OCR_SPEED_BALANCED
                    and _has_confirmed_review_signal(candidate_texts)
                )
                if not skip_grid_for_review_signal:
                    combined_text = _recognize_regions(
                        ocr_engine=ocr_engine,
                        regions=iter_grid_ocr_regions(image_path, config),
                        candidate_texts=candidate_texts,
                        combined_text=combined_text,
                        cancel_event=cancel_event,
                        stop_on_confirmed_candidate=True,
                        stop_on_review_signal=config.ocr_speed_mode == OCR_SPEED_BALANCED,
                    )
                selection = select_best_candidate_with_score(candidate_texts)
                if selection:
                    result, combined_text = _resolve_valid_selection(
                        task=task,
                        config=config,
                        ocr_engine=ocr_engine,
                        image_path=image_path,
                        selection=selection,
                        candidate_texts=candidate_texts,
                        combined_text=combined_text,
                        started=started,
                        cancel_event=cancel_event,
                    )
                    if result:
                        return result

            invalid_candidates = extract_invalid_candidates(combined_text)
            if invalid_candidates:
                invalid_candidate = _select_invalid_candidate(candidate_texts) or invalid_candidates[0]
                base_text = combined_text
                enhanced_selection, combined_text = _recognize_enhanced_selection(
                    task=task,
                    config=config,
                    ocr_engine=ocr_engine,
                    image_path=image_path,
                    combined_text=combined_text,
                    cancel_event=cancel_event,
                )
                if enhanced_selection and _is_confirmed_invalid_repair(
                    invalid_candidate,
                    enhanced_selection.code,
                    base_text,
                    combined_text,
                    config,
                ):
                    return _build_enhanced_success_result(
                        task=task,
                        selection=enhanced_selection,
                        ocr_text=combined_text,
                        started=started,
                        review_note=f"\u589e\u5f3a\u8bc6\u522b\u4fee\u590d\u65e0\u6548\u5019\u9009: {invalid_candidate} -> {enhanced_selection.code}",
                    )
                return _build_result(
                    task=task,
                    status=RecognitionStatus.INVALID,
                    container_code=invalid_candidate,
                    source=RecognitionSource.OCR,
                    failure_reason="INVALID_CHECK_DIGIT",
                    ocr_text=combined_text,
                    started=started,
                    review_note=_invalid_review_note(invalid_candidate, combined_text),
                    review_code=decide_review_code_for_invalid_candidate(invalid_candidate, combined_text),
                )

            if _should_run_enhancement(config):
                enhanced_selection, combined_text = _recognize_enhanced_selection(
                    task=task,
                    config=config,
                    ocr_engine=ocr_engine,
                    image_path=image_path,
                    combined_text=combined_text,
                    cancel_event=cancel_event,
                )
                if enhanced_selection:
                    return _build_enhanced_success_result(
                        task=task,
                        selection=enhanced_selection,
                        ocr_text=combined_text,
                        started=started,
                        review_note=f"\u589e\u5f3a\u8bc6\u522b\u5019\u9009: {enhanced_selection.code}",
                    )

        filename_result = _filename_fallback_result(task, combined_text, started)
        if filename_result:
            return filename_result

        review_code = decide_review_code_from_text(combined_text)
        return _build_result(
            task=task,
            status=RecognitionStatus.UNRECOGNIZED,
            container_code=None,
            source=None,
            failure_reason="NO_CONTAINER_CANDIDATE",
            ocr_text=combined_text,
            started=started,
            review_note=_final_review_note(combined_text),
            review_code=review_code,
        )
    except ProcessingCancelled:
        raise
    except Exception as exc:
        return _build_result(
            task=task,
            status=RecognitionStatus.UNRECOGNIZED,
            container_code=None,
            source=None,
            failure_reason=f"PROCESS_FAILED: {exc}",
            ocr_text=combined_text,
            started=started,
        )
    finally:
        if image_iterator is not None:
            _close_iterator(image_iterator)


def _filename_fallback_result(task: FileTask, ocr_text: str, started: float) -> RecognitionResult | None:
    filename_candidates = extract_candidates(task.source_path.stem)
    if filename_candidates:
        return _build_result(
            task=task,
            status=RecognitionStatus.SUCCESS,
            container_code=filename_candidates[0],
            source=RecognitionSource.FILENAME,
            failure_reason=None,
            ocr_text=ocr_text,
            started=started,
        )

    invalid_filename_candidates = extract_invalid_candidates(task.source_path.stem)
    if invalid_filename_candidates:
        return _build_result(
            task=task,
            status=RecognitionStatus.INVALID,
            container_code=invalid_filename_candidates[0],
            source=RecognitionSource.FILENAME,
            failure_reason="INVALID_CHECK_DIGIT",
            ocr_text=ocr_text,
            started=started,
            review_note=_invalid_review_note(invalid_filename_candidates[0], ocr_text),
            review_code=decide_review_code_for_invalid_candidate(invalid_filename_candidates[0], ocr_text),
        )

    return None


def _resolve_valid_selection(
    task: FileTask,
    config: AppConfig,
    ocr_engine: OcrEngine,
    image_path,
    selection: CandidateSelection,
    candidate_texts: list[CandidateText],
    combined_text: str,
    started: float,
    cancel_event,
) -> tuple[RecognitionResult | None, str]:
    assessment = assess_candidate_conflict(selection.code, candidate_texts)
    has_conflict = assessment.has_strong_conflict
    needs_cross_validation = (
        assessment.requires_cross_validation
        or _needs_pdf_cross_validation(task, config, selection, candidate_texts)
    )
    if not needs_cross_validation:
        return _build_success_result(task, selection, combined_text, started), combined_text

    if _should_run_enhancement(config):
        enhanced_selection, combined_text = _recognize_enhanced_selection(
            task=task,
            config=config,
            ocr_engine=ocr_engine,
            image_path=image_path,
            combined_text=combined_text,
            cancel_event=cancel_event,
            confirmation_code=selection.code,
        )
        if enhanced_selection:
            if enhanced_selection.code == selection.code:
                return _build_success_result(task, selection, combined_text, started), combined_text
            return _build_enhanced_success_result(
                task=task,
                selection=enhanced_selection,
                ocr_text=combined_text,
                started=started,
                review_note=f"增强识别覆盖低清晰度候选: {selection.code} -> {enhanced_selection.code}",
            ), combined_text

    if needs_cross_validation and not has_conflict:
        return _build_insufficient_evidence_result(task, selection.code, combined_text, started), combined_text
    return _build_conflict_result(task, selection.code, combined_text, started), combined_text


def _build_conflict_result(task: FileTask, code: str, ocr_text: str, started: float) -> RecognitionResult:
    review_note = build_conflict_review_note(code, ocr_text)
    return _build_result(
        task=task,
        status=RecognitionStatus.INVALID,
        container_code=code,
        source=RecognitionSource.OCR,
        failure_reason=CONFLICTING_CANDIDATES_REASON,
        ocr_text=ocr_text,
        started=started,
        review_note=review_note,
        review_code=code,
    )


def _build_insufficient_evidence_result(task: FileTask, code: str, ocr_text: str, started: float) -> RecognitionResult:
    return _build_result(
        task=task,
        status=RecognitionStatus.INVALID,
        container_code=code,
        source=RecognitionSource.OCR,
        failure_reason=INSUFFICIENT_CANDIDATE_EVIDENCE_REASON,
        ocr_text=ocr_text,
        started=started,
        review_note=f"合法候选仅有单处 OCR 证据，未通过增强交叉验证: {code}",
        review_code=code,
    )


def _is_confirmed_invalid_repair(
    invalid_candidate: str,
    enhanced_code: str,
    base_text: str,
    enhanced_text: str,
    config: AppConfig,
) -> bool:
    repairs = single_digit_check_repairs(invalid_candidate)
    if not _is_related_enhanced_candidate(invalid_candidate, enhanced_code, repairs):
        return False
    candidates = list(dict.fromkeys([*repairs, enhanced_code]))
    winner = _confirmed_review_winner(base_text, enhanced_text, candidates, config)
    return winner == enhanced_code


def _is_related_enhanced_candidate(invalid_candidate: str, enhanced_code: str, repairs: list[str]) -> bool:
    if enhanced_code in repairs:
        return True
    if len(invalid_candidate) != 11 or len(enhanced_code) != 11:
        return False
    if invalid_candidate[:4] != enhanced_code[:4]:
        return False
    return _longest_common_digit_run(invalid_candidate[4:], enhanced_code[4:]) >= 5


def _longest_common_digit_run(left: str, right: str) -> int:
    longest = 0
    for start in range(len(left)):
        for end in range(start + 1, len(left) + 1):
            segment = left[start:end]
            if segment in right:
                longest = max(longest, len(segment))
    return longest


def _confirmed_review_winner(
    base_text: str,
    enhanced_text: str,
    candidates: list[str],
    config: AppConfig,
) -> str | None:
    if not _should_promote_review_candidate(config):
        return None
    min_score, min_margin = _review_promotion_thresholds(config)
    scores = score_review_candidates(
        base_text=base_text,
        enhanced_text=enhanced_text,
        candidates=candidates,
        expected_codes=set(),
    )
    return has_clear_review_winner(scores, min_score=min_score, min_margin=min_margin)


def _should_promote_review_candidate(config: AppConfig) -> bool:
    return config.ocr_speed_mode in {OCR_SPEED_BALANCED, OCR_SPEED_STABLE}


def _review_promotion_thresholds(config: AppConfig) -> tuple[int, int]:
    if config.ocr_speed_mode == OCR_SPEED_STABLE:
        return 80, 15
    return 90, 25


def _enhanced_psm_values(config: AppConfig, region_name: str) -> tuple[int, ...]:
    if config.ocr_speed_mode == OCR_SPEED_STABLE:
        return (6, 7, 11)
    if _is_secondary_enhanced_variant(region_name):
        return (6,)
    return (6, 11)


def _recognize_enhanced_selection(
    task: FileTask,
    config: AppConfig,
    ocr_engine: OcrEngine,
    image_path,
    combined_text: str,
    cancel_event,
    confirmation_code: str | None = None,
) -> tuple[CandidateSelection | None, str]:
    if not _should_run_enhancement(config):
        return None, combined_text

    enhanced_texts: list[CandidateText] = []
    region_iterator = iter(iter_enhanced_ocr_regions(task, image_path, config))
    resolved_region_keys: set[tuple[str, str]] = set()
    previous_source: str | None = None
    try:
        for region in region_iterator:
            current_source = _enhanced_evidence_source(region.region_name)
            is_resolution_transition = previous_source == "400dpi" and current_source == "base"
            if (
                config.ocr_speed_mode == OCR_SPEED_BALANCED
                and is_resolution_transition
                and confirmation_code is None
                and not _has_actionable_container_signal(enhanced_texts)
            ):
                break
            previous_source = current_source
            region_key = _enhanced_evidence_key(region.region_name)
            if (
                config.ocr_speed_mode == OCR_SPEED_BALANCED
                and _is_secondary_enhanced_variant(region.region_name)
                and region_key in resolved_region_keys
            ):
                continue

            known_codes = _valid_codes(enhanced_texts)
            region_code_hits: dict[str, int] = {}
            for psm_index, psm in enumerate(_enhanced_psm_values(config, region.region_name)):
                raise_if_cancelled(cancel_event)
                combined_text = _recognize_region(
                    ocr_engine=ocr_engine,
                    region=region,
                    candidate_texts=enhanced_texts,
                    combined_text=combined_text,
                    cancel_event=cancel_event,
                    psm=psm,
                )
                current_codes = set(extract_candidates(enhanced_texts[-1].text))
                for code in current_codes:
                    region_code_hits[code] = region_code_hits.get(code, 0) + 1
                if (
                    config.ocr_speed_mode == OCR_SPEED_BALANCED
                    and current_codes
                    and (psm_index > 0 or bool(current_codes & known_codes))
                ):
                    break

            confirmed_region_codes = {
                code
                for code, hit_count in region_code_hits.items()
                if hit_count >= 2 or code in known_codes
            }
            if len(confirmed_region_codes) == 1:
                resolved_region_keys.add(region_key)
            if config.ocr_speed_mode == OCR_SPEED_BALANCED:
                staged_selection = _confirmed_staged_enhanced_selection(
                    enhanced_texts,
                    require_cross_resolution=task.source_path.suffix.lower() == ".pdf",
                )
                if staged_selection is not None and _is_confirmed_enhanced_override(
                    confirmation_code,
                    staged_selection,
                    enhanced_texts,
                ):
                    return staged_selection, combined_text

        selection = select_best_candidate_with_score(enhanced_texts)
        if selection is not None and not _is_confirmed_enhanced_override(
            confirmation_code,
            selection,
            enhanced_texts,
        ):
            selection = None
        return selection, combined_text
    finally:
        _close_iterator(region_iterator)


def _confirmed_staged_enhanced_selection(
    texts: list[CandidateText],
    *,
    require_cross_resolution: bool,
) -> CandidateSelection | None:
    selection = select_best_candidate_with_score(texts)
    if selection is None or selection.is_repaired:
        return None

    evidence_regions: set[str] = set()
    evidence_sources: set[str] = set()
    for item in texts:
        item_codes = set(extract_candidates(item.text))
        if selection.code in item_codes:
            evidence_regions.add(_enhanced_evidence_region(item.region_name))
            evidence_sources.add(_enhanced_evidence_source(item.region_name))

    assessment = assess_candidate_conflict(
        selection.code,
        texts,
        region_key=_enhanced_evidence_region,
    )
    if assessment.requires_cross_validation:
        return None
    if len(evidence_regions) < 2:
        return None
    if require_cross_resolution and not {"400dpi", "base"}.issubset(evidence_sources):
        return None
    return selection


def _enhanced_evidence_region(region_name: str) -> str:
    normalized = region_name.removeprefix("enhanced-")
    for source in ("400dpi-", "base-"):
        if normalized.startswith(source):
            normalized = normalized[len(source) :]
            break
    for suffix in ("-plain", "-x2sharp", "-x2binary"):
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)]
    return normalized


def _enhanced_evidence_source(region_name: str) -> str:
    if region_name.startswith("enhanced-400dpi-"):
        return "400dpi"
    if region_name.startswith("enhanced-base-"):
        return "base"
    return "other"


def _enhanced_evidence_key(region_name: str) -> tuple[str, str]:
    return _enhanced_evidence_source(region_name), _enhanced_evidence_region(region_name)


def _is_secondary_enhanced_variant(region_name: str) -> bool:
    return region_name.endswith(("-x2sharp", "-x2binary"))


def _has_actionable_container_signal(texts: list[CandidateText]) -> bool:
    if any(extract_candidates(item.text) or extract_invalid_candidates(item.text) for item in texts):
        return True

    suspicious_supports: dict[tuple[str, str], set[str]] = {}
    for item in texts:
        region = _enhanced_evidence_region(item.region_name)
        for candidate in extract_suspicious_candidates(item.text):
            digits = "".join(character for character in candidate[4:] if character.isdigit())
            if len(digits) < 5:
                continue
            signature = candidate[:4], digits[-5:]
            suspicious_supports.setdefault(signature, set()).add(region)
    return any(len(regions) >= 2 for regions in suspicious_supports.values())


def _has_confirmed_review_signal(texts: list[CandidateText]) -> bool:
    supports: dict[str, set[str]] = {}
    for item in texts:
        invalid_candidates = extract_invalid_candidates(item.text)
        for candidate in invalid_candidates:
            repairs = single_digit_check_repairs(candidate)
            signal = repairs[0] if len(repairs) == 1 else candidate
            supports.setdefault(signal, set()).add(item.region_name)

        guessed_review_code = decide_review_code_from_text(item.text)
        if guessed_review_code:
            supports.setdefault(guessed_review_code, set()).add(item.region_name)

    repeated_signals = [
        signal
        for signal, regions in supports.items()
        if _has_independent_review_regions(regions)
    ]
    return len(repeated_signals) == 1


def _has_independent_review_regions(region_names: set[str]) -> bool:
    boxes = [box for name in region_names if (box := _review_region_box(name)) is not None]
    return any(_boxes_do_not_overlap(left, right) for left, right in combinations(boxes, 2))


def _review_region_box(region_name: str) -> tuple[int, int, int, int] | None:
    priority_box = PRIORITY_REGION_BOXES.get(region_name)
    if priority_box is not None:
        return priority_box

    match = GRID_REGION_PATTERN.fullmatch(region_name)
    if match is None:
        return None

    row = int(match.group(1)) - 1
    column = int(match.group(2)) - 1
    if row not in range(8) or column not in range(3):
        return None

    overlap = 40
    return (
        max(0, int(column * 1000 / 3) - overlap),
        max(0, int(row * 1000 / 8) - overlap),
        min(1000, int((column + 1) * 1000 / 3) + overlap),
        min(1000, int((row + 1) * 1000 / 8) + overlap),
    )


def _boxes_do_not_overlap(
    left: tuple[int, int, int, int],
    right: tuple[int, int, int, int],
) -> bool:
    return (
        left[2] <= right[0]
        or right[2] <= left[0]
        or left[3] <= right[1]
        or right[3] <= left[1]
    )


def _select_invalid_candidate(texts: list[CandidateText]) -> str | None:
    supports: dict[str, set[str]] = {}
    order: list[str] = []
    for item in texts:
        for candidate in extract_invalid_candidates(item.text):
            if candidate not in supports:
                supports[candidate] = set()
                order.append(candidate)
            supports[candidate].add(item.region_name)

    if not supports:
        return None
    order_index = {candidate: index for index, candidate in enumerate(order)}
    return max(
        supports,
        key=lambda candidate: (len(supports[candidate]), -order_index[candidate]),
    )


def _valid_codes(texts: list[CandidateText]) -> set[str]:
    return {code for item in texts for code in extract_candidates(item.text)}


def _enhanced_variant(region_name: str) -> str:
    for variant in ("plain", "x2sharp", "x2binary"):
        if region_name.endswith(f"-{variant}"):
            return variant
    return "other"


def _candidate_supports(texts: list[CandidateText]) -> dict[str, set[tuple[str, str, str]]]:
    supports: dict[str, set[tuple[str, str, str]]] = {}
    for item in texts:
        support_key = (
            _enhanced_evidence_source(item.region_name),
            _enhanced_evidence_region(item.region_name),
            _enhanced_variant(item.region_name),
        )
        for code in set(extract_candidates(item.text)):
            supports.setdefault(code, set()).add(support_key)
    return supports


def _is_confirmed_enhanced_override(
    confirmation_code: str | None,
    selection: CandidateSelection,
    texts: list[CandidateText],
) -> bool:
    if confirmation_code is None:
        return True

    supports = _candidate_supports(texts)
    selected_supports = supports.get(selection.code, set())
    other_support_count = max(
        (len(items) for code, items in supports.items() if code != selection.code),
        default=0,
    )
    if selection.code == confirmation_code:
        return bool(selected_supports) and len(selected_supports) > other_support_count

    selected_regions = {region for _source, region, _variant in selected_supports}
    high_dpi_variants: dict[str, set[str]] = {}
    for source, region, variant in selected_supports:
        if source == "400dpi":
            high_dpi_variants.setdefault(region, set()).add(variant)
    has_high_dpi_transform_confirmation = any(len(variants) >= 2 for variants in high_dpi_variants.values())
    has_independent_confirmation = len(selected_regions) >= 2 or has_high_dpi_transform_confirmation
    if _has_authoritative_high_dpi_override(confirmation_code, selection, texts):
        return True
    return has_independent_confirmation and len(selected_supports) > other_support_count


def _has_authoritative_high_dpi_override(
    confirmation_code: str,
    selection: CandidateSelection,
    texts: list[CandidateText],
) -> bool:
    authoritative = _authoritative_high_dpi_selection(confirmation_code, texts)
    return authoritative is not None and authoritative.code == selection.code


def _authoritative_high_dpi_selection(
    confirmation_code: str,
    texts: list[CandidateText],
) -> CandidateSelection | None:
    high_dpi_texts = [
        item
        for item in texts
        if _enhanced_evidence_source(item.region_name) == "400dpi"
    ]
    high_dpi_codes = _valid_codes(high_dpi_texts)
    if len(high_dpi_codes) != 1:
        return None

    high_dpi_selection = select_best_candidate_with_score(high_dpi_texts)
    if high_dpi_selection is None or high_dpi_selection.score < STRONG_CANDIDATE_SCORE:
        return None
    if high_dpi_selection.code == confirmation_code:
        return None
    if high_dpi_selection.code[:4] != confirmation_code[:4]:
        return None
    if not _has_base_suspicious_support(high_dpi_selection.code, texts):
        return None
    return high_dpi_selection


def _has_base_suspicious_support(code: str, texts: list[CandidateText]) -> bool:
    high_dpi_regions = _related_suspicious_regions(code, texts, source="400dpi")
    base_regions = _related_suspicious_regions(code, texts, source="base")
    if len(high_dpi_regions) < 2 or not base_regions:
        return False

    competing_regions: dict[str, set[str]] = {}
    for item in texts:
        if _enhanced_evidence_source(item.region_name) != "base":
            continue
        region = _enhanced_evidence_region(item.region_name)
        for candidate in extract_candidates(item.text):
            if candidate != code:
                competing_regions.setdefault(candidate, set()).add(region)
    return all(len(regions) < 2 for regions in competing_regions.values())


def _related_suspicious_regions(
    code: str,
    texts: list[CandidateText],
    *,
    source: str,
) -> set[str]:
    code_digits = code[4:]
    regions: set[str] = set()
    for item in texts:
        if _enhanced_evidence_source(item.region_name) != source:
            continue
        for candidate in extract_suspicious_candidates(item.text):
            if not candidate.startswith(code[:4]):
                continue
            candidate_digits = "".join(character for character in candidate[4:] if character.isdigit())
            if len(candidate_digits) >= 6 and candidate_digits in code_digits:
                regions.add(_enhanced_evidence_region(item.region_name))
    return regions


def _priority_regions_for_mode(image_path, config: AppConfig):
    try:
        regions = iter_priority_ocr_regions(image_path, config)
    except Exception as exc:
        return [OcrRegion(image_path=image_path, region_name=f"{REGION_CROP_FAILURE_MARKER}: {exc}")]
    if config.ocr_speed_mode == OCR_SPEED_FAST:
        return islice(regions, 3)
    return regions


def _should_run_grid(config: AppConfig) -> bool:
    return config.ocr_speed_mode != OCR_SPEED_FAST


def _should_run_enhancement(config: AppConfig) -> bool:
    return config.ocr_speed_mode != OCR_SPEED_FAST


def _needs_pdf_cross_validation(
    task: FileTask,
    config: AppConfig,
    selection: CandidateSelection,
    candidate_texts: list[CandidateText],
) -> bool:
    if config.ocr_speed_mode == OCR_SPEED_FAST or task.source_path.suffix.lower() != ".pdf":
        return False
    return selection.is_repaired or len(_base_candidate_evidence_regions(selection.code, candidate_texts)) < 2


def _base_candidate_evidence_regions(code: str, texts: list[CandidateText]) -> set[str]:
    return {item.region_name for item in texts if code in set(extract_candidates(item.text))}


def _has_confirmed_base_candidate(texts: list[CandidateText], combined_text: str) -> bool:
    selection = select_best_candidate_with_score(texts)
    if selection is None or selection.is_repaired:
        return False
    assessment = assess_candidate_conflict(selection.code, texts)
    if assessment.requires_cross_validation:
        return False
    return len(_base_candidate_evidence_regions(selection.code, texts)) >= 2


def _recognize_regions(
    ocr_engine: OcrEngine,
    regions,
    candidate_texts: list[CandidateText],
    combined_text: str,
    cancel_event,
    stop_on_confirmed_candidate: bool = False,
    stop_on_review_signal: bool = False,
) -> str:
    region_iterator = iter(regions)
    try:
        for region in region_iterator:
            raise_if_cancelled(cancel_event)
            combined_text = _recognize_region(ocr_engine, region, candidate_texts, combined_text, cancel_event)
            if stop_on_confirmed_candidate and _has_confirmed_base_candidate(candidate_texts, combined_text):
                break
            if stop_on_review_signal and _has_confirmed_review_signal(candidate_texts):
                break
        return combined_text
    finally:
        _close_iterator(region_iterator)


def _recognize_region(
    ocr_engine: OcrEngine,
    region: OcrRegion,
    candidate_texts: list[CandidateText],
    combined_text: str,
    cancel_event,
    psm: int | None = None,
) -> str:
    if _is_region_diagnostic(region.region_name):
        candidate_texts.append(CandidateText(text="", region_name=region.region_name))
        return f"{combined_text}\n[{region.region_name}]"

    try:
        ocr_result = ocr_engine.recognize_image(region.image_path, cancel_event=cancel_event, psm=psm)
    except ProcessingCancelled:
        raise
    except Exception as exc:
        marker = f"{REGION_OCR_FAILURE_MARKER}: {region.region_name}: {exc}"
        candidate_texts.append(CandidateText(text="", region_name=region.region_name))
        return f"{combined_text}\n[{region.region_name}]\n{marker}"

    candidate_texts.append(CandidateText(text=ocr_result.text, region_name=region.region_name))
    label = region.region_name if psm is None else f"{region.region_name}:psm{psm}"
    return f"{combined_text}\n[{label}]\n{ocr_result.text}"


def _is_region_diagnostic(region_name: str) -> bool:
    return region_name.startswith(REGION_CROP_FAILURE_MARKER) or region_name.startswith(REGION_CROP_SKIP_MARKER)


def _build_success_result(task: FileTask, selection, ocr_text: str, started: float) -> RecognitionResult:
    return _build_result(
        task=task,
        status=RecognitionStatus.SUCCESS,
        container_code=selection.code,
        source=_selection_source(selection),
        failure_reason=None,
        ocr_text=ocr_text,
        started=started,
        review_note=_selection_review_note(selection),
    )


def _build_enhanced_success_result(
    task: FileTask,
    selection,
    ocr_text: str,
    started: float,
    review_note: str | None,
) -> RecognitionResult:
    return _build_result(
        task=task,
        status=RecognitionStatus.SUCCESS,
        container_code=selection.code,
        source=RecognitionSource.OCR_ENHANCED,
        failure_reason=None,
        ocr_text=ocr_text,
        started=started,
        review_note=review_note,
    )


def _selection_source(selection) -> RecognitionSource:
    if selection.is_repaired:
        return RecognitionSource.OCR_REPAIRED
    return RecognitionSource.OCR


def _selection_review_note(selection) -> str | None:
    if selection.is_repaired and selection.raw_candidate:
        return f"OCR\u4fee\u6b63\u539f\u59cb\u7247\u6bb5: {selection.raw_candidate}"
    return None


def _invalid_review_note(candidate: str, ocr_text: str) -> str | None:
    return build_invalid_review_note(candidate, _final_review_note(ocr_text))


def _final_review_note(ocr_text: str) -> str | None:
    suspicious_note = build_suspicious_note(ocr_text)
    if suspicious_note:
        return suspicious_note
    if REGION_CROP_FAILURE_MARKER in ocr_text or REGION_CROP_SKIP_MARKER in ocr_text:
        return REGION_CROP_FAILURE_NOTE
    if REGION_OCR_FAILURE_MARKER in ocr_text:
        return "\u90e8\u5206\u533a\u57df OCR \u5931\u8d25\uff0c\u5df2\u8df3\u8fc7\u5931\u8d25\u533a\u57df\u5e76\u7ee7\u7eed\u8bc6\u522b"
    return None


def _build_result(
    task: FileTask,
    status: RecognitionStatus,
    container_code: str | None,
    source: RecognitionSource | None,
    failure_reason: str | None,
    ocr_text: str,
    started: float,
    review_note: str | None = None,
    review_code: str | None = None,
) -> RecognitionResult:
    return RecognitionResult(
        source_path=task.source_path,
        original_name=task.source_path.name,
        status=status,
        container_code=container_code,
        source=source,
        failure_reason=failure_reason,
        ocr_text=ocr_text,
        elapsed_ms=int((time.perf_counter() - started) * 1000),
        relative_name=task.relative_name,
        review_note=review_note,
        review_code=review_code,
    )


def _close_iterator(iterator) -> None:
    close = getattr(iterator, "close", None)
    if close:
        close()
