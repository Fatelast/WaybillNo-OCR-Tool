import time

from waybill_ocr.cancellation import ProcessingCancelled, raise_if_cancelled
from waybill_ocr.config import AppConfig
from waybill_ocr.container_code.candidate_selector import (
    CandidateText,
    select_best_candidate_with_score,
)
from waybill_ocr.container_code.extractor import (
    extract_candidates,
    extract_invalid_candidates,
    extract_suspicious_candidates,
)
from waybill_ocr.image_loader import iter_images_for_ocr
from waybill_ocr.image_regions import OcrRegion, iter_grid_ocr_regions, iter_priority_ocr_regions
from waybill_ocr.models import FileTask, RecognitionResult, RecognitionSource, RecognitionStatus
from waybill_ocr.ocr.base import OcrEngine


STRONG_CANDIDATE_SCORE = 140


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
                return _build_success_result(task, full_selection, combined_text, started)
            combined_text = _recognize_regions(
                ocr_engine=ocr_engine,
                regions=iter_priority_ocr_regions(image_path, config),
                candidate_texts=candidate_texts,
                combined_text=combined_text,
                cancel_event=cancel_event,
            )
            selection = select_best_candidate_with_score(candidate_texts)
            if selection:
                return _build_success_result(task, selection, combined_text, started)

            combined_text = _recognize_regions(
                ocr_engine=ocr_engine,
                regions=iter_grid_ocr_regions(image_path, config),
                candidate_texts=candidate_texts,
                combined_text=combined_text,
                cancel_event=cancel_event,
            )
            selection = select_best_candidate_with_score(candidate_texts)
            if selection:
                return _build_success_result(task, selection, combined_text, started)

            invalid_candidates = extract_invalid_candidates(combined_text)
            if invalid_candidates:
                return _build_result(
                    task=task,
                    status=RecognitionStatus.INVALID,
                    container_code=invalid_candidates[0],
                    source=RecognitionSource.OCR,
                    failure_reason="INVALID_CHECK_DIGIT",
                    ocr_text=combined_text,
                    started=started,
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
            review_note=_suspicious_note(combined_text),
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
        )

    return None


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
) -> str:
    ocr_result = ocr_engine.recognize_image(region.image_path, cancel_event=cancel_event)
    candidate_texts.append(CandidateText(text=ocr_result.text, region_name=region.region_name))
    return f"{combined_text}\n[{region.region_name}]\n{ocr_result.text}"


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


def _selection_source(selection) -> RecognitionSource:
    if selection.is_repaired:
        return RecognitionSource.OCR_REPAIRED
    return RecognitionSource.OCR


def _selection_review_note(selection) -> str | None:
    if selection.is_repaired and selection.raw_candidate:
        return f"OCR\u4fee\u6b63\u539f\u59cb\u7247\u6bb5: {selection.raw_candidate}"
    return None


def _suspicious_note(ocr_text: str) -> str | None:
    candidates = extract_suspicious_candidates(ocr_text)
    if not candidates:
        return None
    return f"\u7591\u4f3c\u5019\u9009: {', '.join(candidates)}"


def _build_result(
    task: FileTask,
    status: RecognitionStatus,
    container_code: str | None,
    source: RecognitionSource | None,
    failure_reason: str | None,
    ocr_text: str,
    started: float,
    review_note: str | None = None,
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
        review_note=review_note,
    )


def _close_iterator(iterator) -> None:
    close = getattr(iterator, "close", None)
    if close:
        close()
