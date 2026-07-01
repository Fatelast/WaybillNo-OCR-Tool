import time

from waybill_ocr.config import AppConfig
from waybill_ocr.container_code.extractor import extract_candidates, extract_invalid_candidates
from waybill_ocr.image_loader import iter_images_for_ocr
from waybill_ocr.models import FileTask, RecognitionResult, RecognitionSource, RecognitionStatus
from waybill_ocr.ocr.base import OcrEngine


def process_file(task: FileTask, config: AppConfig, ocr_engine: OcrEngine) -> RecognitionResult:
    started = time.perf_counter()
    combined_text = ""

    try:
        for image_path in iter_images_for_ocr(task.source_path, config):
            ocr_result = ocr_engine.recognize_image(image_path)
            combined_text += "\n" + ocr_result.text
            candidates = extract_candidates(combined_text)
            if candidates:
                return _build_result(
                    task=task,
                    status=RecognitionStatus.SUCCESS,
                    container_code=candidates[0],
                    source=RecognitionSource.OCR,
                    failure_reason=None,
                    ocr_text=combined_text,
                    started=started,
                )

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

        filename_candidates = extract_candidates(task.source_path.stem)
        if filename_candidates:
            return _build_result(
                task=task,
                status=RecognitionStatus.SUCCESS,
                container_code=filename_candidates[0],
                source=RecognitionSource.FILENAME,
                failure_reason=None,
                ocr_text=combined_text,
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
                ocr_text=combined_text,
                started=started,
            )

        return _build_result(
            task=task,
            status=RecognitionStatus.UNRECOGNIZED,
            container_code=None,
            source=None,
            failure_reason="NO_CONTAINER_CANDIDATE",
            ocr_text=combined_text,
            started=started,
        )
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


def _build_result(
    task: FileTask,
    status: RecognitionStatus,
    container_code: str | None,
    source: RecognitionSource | None,
    failure_reason: str | None,
    ocr_text: str,
    started: float,
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
    )
