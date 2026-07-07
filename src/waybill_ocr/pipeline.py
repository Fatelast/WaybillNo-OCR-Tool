import time
from itertools import islice

from waybill_ocr.cancellation import ProcessingCancelled, raise_if_cancelled
from waybill_ocr.config import AppConfig, OCR_SPEED_FAST
from waybill_ocr.container_code.candidate_selector import (
    CandidateText,
    CandidateSelection,
    select_best_candidate_with_score,
)
from waybill_ocr.container_code.extractor import (
    extract_candidates,
    extract_guess_repair_suggestions,
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
REGION_CROP_FAILURE_MARKER = "\u533a\u57df\u88c1\u526a\u5931\u8d25"
REGION_CROP_SKIP_MARKER = "\u533a\u57df\u88c1\u526a\u8df3\u8fc7"
REGION_CROP_FAILURE_NOTE = "\u533a\u57df\u88c1\u526a\u5931\u8d25/\u8df3\u8fc7\uff0c\u53ef\u80fd\u56fe\u7247\u635f\u574f\u6216\u65e0\u6cd5\u8bfb\u53d6\u533a\u57df"
REGION_OCR_FAILURE_MARKER = "\u533a\u57df OCR \u5931\u8d25"
ENHANCED_PSM_MODES = (6, 11)


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
            if full_selection and full_selection.score >= STRONG_CANDIDATE_SCORE:
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
                combined_text = _recognize_regions(
                    ocr_engine=ocr_engine,
                    regions=iter_grid_ocr_regions(image_path, config),
                    candidate_texts=candidate_texts,
                    combined_text=combined_text,
                    cancel_event=cancel_event,
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
                        review_note=f"\u589e\u5f3a\u8bc6\u522b\u4fee\u590d\u65e0\u6548\u5019\u9009: {invalid_candidates[0]} -> {enhanced_selection.code}",
                    )
                return _build_result(
                    task=task,
                    status=RecognitionStatus.INVALID,
                    container_code=invalid_candidates[0],
                    source=RecognitionSource.OCR,
                    failure_reason="INVALID_CHECK_DIGIT",
                    ocr_text=combined_text,
                    started=started,
                    review_note=_invalid_review_note(invalid_candidates[0], combined_text),
                    review_code=_review_code_for_invalid_candidate(invalid_candidates[0], combined_text),
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

        return _build_result(
            task=task,
            status=RecognitionStatus.UNRECOGNIZED,
            container_code=None,
            source=None,
            failure_reason="NO_CONTAINER_CANDIDATE",
            ocr_text=combined_text,
            started=started,
            review_note=_final_review_note(combined_text),
            review_code=_review_code_from_text(combined_text),
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
            review_code=_review_code_for_invalid_candidate(invalid_filename_candidates[0], ocr_text),
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
    if not _has_candidate_conflict(selection.code, combined_text):
        return _build_success_result(task, selection, combined_text, started), combined_text

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
            if enhanced_selection.code == selection.code:
                return _build_success_result(task, selection, combined_text, started), combined_text
            return _build_enhanced_success_result(
                task=task,
                selection=enhanced_selection,
                ocr_text=combined_text,
                started=started,
                review_note=f"\u589e\u5f3a\u8bc6\u522b\u8986\u76d6\u4f4e\u6e05\u6670\u5ea6\u5019\u9009: {selection.code} -> {enhanced_selection.code}",
            ), combined_text

    return _build_conflict_result(task, selection.code, combined_text, started), combined_text


def _has_candidate_conflict(code: str, ocr_text: str) -> bool:
    valid_candidates = [candidate for candidate in extract_candidates(ocr_text) if candidate != code]
    if valid_candidates:
        return True

    prefix = code[:4]
    return any(candidate[:4] == prefix and candidate != code for candidate in extract_suspicious_candidates(ocr_text))


def _build_conflict_result(task: FileTask, code: str, ocr_text: str, started: float) -> RecognitionResult:
    suspicious = extract_suspicious_candidates(ocr_text)
    parts = [f"\u5019\u9009\u51b2\u7a81\uff0c\u9700\u4eba\u5de5\u590d\u6838: {code}"]
    if suspicious:
        parts.append(f"\u7591\u4f3c\u5019\u9009: {', '.join(suspicious)}")
    return _build_result(
        task=task,
        status=RecognitionStatus.INVALID,
        container_code=code,
        source=RecognitionSource.OCR,
        failure_reason=CONFLICTING_CANDIDATES_REASON,
        ocr_text=ocr_text,
        started=started,
        review_note="\uff1b".join(parts),
        review_code=code,
    )


def _recognize_enhanced_selection(
    task: FileTask,
    config: AppConfig,
    ocr_engine: OcrEngine,
    image_path,
    combined_text: str,
    cancel_event,
) -> tuple[CandidateSelection | None, str]:
    if not _should_run_enhancement(config):
        return None, combined_text

    enhanced_texts: list[CandidateText] = []
    region_iterator = iter(iter_enhanced_ocr_regions(task, image_path, config))
    try:
        for region in region_iterator:
            for psm in ENHANCED_PSM_MODES:
                raise_if_cancelled(cancel_event)
                combined_text = _recognize_region(
                    ocr_engine=ocr_engine,
                    region=region,
                    candidate_texts=enhanced_texts,
                    combined_text=combined_text,
                    cancel_event=cancel_event,
                    psm=psm,
                )
        return select_best_candidate_with_score(enhanced_texts), combined_text
    finally:
        _close_iterator(region_iterator)


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


def _recognize_regions(
    ocr_engine: OcrEngine,
    regions,
    candidate_texts: list[CandidateText],
    combined_text: str,
    cancel_event,
) -> str:
    region_iterator = iter(regions)
    try:
        for region in region_iterator:
            raise_if_cancelled(cancel_event)
            combined_text = _recognize_region(ocr_engine, region, candidate_texts, combined_text, cancel_event)
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
    repair = _single_digit_check_repair(candidate)
    note = _final_review_note(ocr_text)
    if repair:
        repair_note = f"疑似校验修正: {candidate} -> {repair}（待人工确认）"
        return f"{repair_note}；{note}" if note else repair_note
    return note


def _review_code_for_invalid_candidate(candidate: str, ocr_text: str) -> str | None:
    repair = _single_digit_check_repair(candidate)
    if repair:
        return repair
    return _review_code_from_text(ocr_text)


def _review_code_from_text(ocr_text: str) -> str | None:
    repaired_codes = {repaired for _raw, repaired in extract_guess_repair_suggestions(ocr_text)}
    if len(repaired_codes) == 1:
        return next(iter(repaired_codes))
    return None


def _single_digit_check_repair(candidate: str) -> str | None:
    if len(candidate) != 11 or not candidate[:3].isalpha() or candidate[3] != "U" or not candidate[4:].isdigit():
        return None

    repairs: list[str] = []
    for index in range(4, 10):
        original_digit = candidate[index]
        for digit in "0123456789":
            if digit == original_digit:
                continue
            repaired = f"{candidate[:index]}{digit}{candidate[index + 1:]}"
            if is_valid_container_code(repaired) and repaired not in repairs:
                repairs.append(repaired)
    if len(repairs) == 1:
        return repairs[0]
    return None

def _final_review_note(ocr_text: str) -> str | None:
    suspicious_note = _suspicious_note(ocr_text)
    if suspicious_note:
        return suspicious_note
    if REGION_CROP_FAILURE_MARKER in ocr_text or REGION_CROP_SKIP_MARKER in ocr_text:
        return REGION_CROP_FAILURE_NOTE
    if REGION_OCR_FAILURE_MARKER in ocr_text:
        return "\u90e8\u5206\u533a\u57df OCR \u5931\u8d25\uff0c\u5df2\u8df3\u8fc7\u5931\u8d25\u533a\u57df\u5e76\u7ee7\u7eed\u8bc6\u522b"
    return None


def _suspicious_note(ocr_text: str) -> str | None:
    candidates = extract_suspicious_candidates(ocr_text)
    suggestions = extract_guess_repair_suggestions(ocr_text)
    if not candidates and not suggestions:
        return None

    parts = []
    if candidates:
        parts.append(f"\u7591\u4f3c\u5019\u9009: {', '.join(candidates)}")
    if suggestions:
        suggestion_text = ", ".join(f"{raw}->{repaired}" for raw, repaired in suggestions)
        if len(suggestions) == 1:
            suggestion_text = suggestions[0][1]
        parts.append(f"\u53ef\u80fd\u4fee\u6b63: {suggestion_text}\uff08\u672a\u81ea\u52a8\u91c7\u7528\uff09")
    return "\uff1b".join(parts)


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
