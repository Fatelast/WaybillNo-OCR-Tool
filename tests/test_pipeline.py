from pathlib import Path

from waybill_ocr.config import AppConfig
from waybill_ocr.image_regions import OcrRegion
from waybill_ocr.models import FileTask, RecognitionSource, RecognitionStatus
from waybill_ocr.ocr.base import OcrResult
from waybill_ocr.pipeline import process_file


class FakeOcrEngine:
    def __init__(self, text_or_texts: str | dict[str, str]) -> None:
        self.text_or_texts = text_or_texts

    def recognize_image(self, image_path: Path, cancel_event=None, *, psm: int | None = None) -> OcrResult:
        if isinstance(self.text_or_texts, dict):
            text = self.text_or_texts.get(image_path.name, "")
        else:
            text = self.text_or_texts
        return OcrResult(text=text, engine_name="fake", elapsed_ms=1)


def test_process_file_returns_success_when_ocr_text_contains_valid_code(tmp_path: Path, monkeypatch):
    source_path = tmp_path / "waybill.jpg"
    source_path.write_bytes(b"fake")
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")

    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])

    result = process_file(task, AppConfig(), FakeOcrEngine("箱号 HNKU6331795"))

    assert result.status == RecognitionStatus.SUCCESS
    assert result.container_code == "HNKU6331795"
    assert result.source == RecognitionSource.OCR
    assert result.failure_reason is None


def test_process_file_falls_back_to_filename_when_ocr_has_no_code(tmp_path: Path, monkeypatch):
    source_path = tmp_path / "HNKU6331795.jpg"
    source_path.write_bytes(b"fake")
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")

    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])

    result = process_file(task, AppConfig(), FakeOcrEngine("no code"))

    assert result.status == RecognitionStatus.SUCCESS
    assert result.container_code == "HNKU6331795"
    assert result.source == RecognitionSource.FILENAME


def test_process_file_returns_unrecognized_when_processing_fails(tmp_path: Path, monkeypatch):
    source_path = tmp_path / "waybill.jpg"
    source_path.write_bytes(b"fake")
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")

    def raise_error(*_args):
        raise RuntimeError("boom")

    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", raise_error)

    result = process_file(task, AppConfig(), FakeOcrEngine(""))

    assert result.status == RecognitionStatus.UNRECOGNIZED
    assert result.container_code is None
    assert result.failure_reason == "PROCESS_FAILED: boom"


def test_process_file_returns_invalid_when_text_contains_bad_check_digit(tmp_path: Path, monkeypatch):
    source_path = tmp_path / "waybill.jpg"
    source_path.write_bytes(b"fake")
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")

    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])

    result = process_file(task, AppConfig(), FakeOcrEngine("箱号 HNKU6331794"))

    assert result.status == RecognitionStatus.INVALID
    assert result.container_code == "HNKU6331794"
    assert result.failure_reason == "INVALID_CHECK_DIGIT"


def test_process_file_prefers_priority_region_candidate_over_full_page_noise(tmp_path: Path, monkeypatch):
    source_path = tmp_path / "waybill.jpg"
    source_path.write_bytes(b"fake")
    region_path = tmp_path / "priority.png"
    region_path.write_bytes(b"fake")
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")
    grid_called = False

    def fake_grid(*_args):
        nonlocal grid_called
        grid_called = True
        return []

    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])
    monkeypatch.setattr(
        "waybill_ocr.pipeline.iter_priority_ocr_regions",
        lambda image_path, config: [OcrRegion(image_path=region_path, region_name="priority-left-middle")],
    )
    monkeypatch.setattr("waybill_ocr.pipeline.iter_grid_ocr_regions", fake_grid)

    result = process_file(
        task,
        AppConfig(),
        FakeOcrEngine(
            {
                "waybill.jpg": "YBXKIKOOMIJIP 5617782 J0YBEXK",
                "priority.png": "GESU5903360P45G130",
            }
        ),
    )

    assert result.status == RecognitionStatus.SUCCESS
    assert result.container_code == "GESU5903360"
    assert result.source == RecognitionSource.OCR
    assert grid_called is False

def test_process_file_closes_image_iterator_when_full_page_candidate_returns_early(tmp_path: Path, monkeypatch):
    source_path = tmp_path / "waybill.jpg"
    source_path.write_bytes(b"fake")
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")
    closed = {"images": False}

    class ClosableIterator:
        def __init__(self, values) -> None:
            self.values = iter(values)

        def __iter__(self):
            return self

        def __next__(self):
            return next(self.values)

        def close(self) -> None:
            closed["images"] = True

    def fake_images(*_args):
        return ClosableIterator([source_path])

    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", fake_images)

    result = process_file(task, AppConfig(), FakeOcrEngine("HNKU6331795 45G1"))

    assert result.status == RecognitionStatus.SUCCESS
    assert closed == {"images": True}


def test_process_file_stops_between_regions_when_cancelled(tmp_path: Path, monkeypatch):
    import threading

    from waybill_ocr.cancellation import ProcessingCancelled

    source_path = tmp_path / "waybill.jpg"
    source_path.write_bytes(b"fake")
    priority_path = tmp_path / "priority.png"
    priority_path.write_bytes(b"fake")
    grid_path = tmp_path / "grid.png"
    grid_path.write_bytes(b"fake")
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")
    cancel_event = threading.Event()

    class CancellingOcrEngine:
        def __init__(self) -> None:
            self.seen = []

        def recognize_image(self, image_path: Path, cancel_event=None, *, psm: int | None = None) -> OcrResult:
            self.seen.append(image_path.name)
            if image_path.name == "priority.png":
                cancel_event.set()
            return OcrResult(text="no code", engine_name="fake", elapsed_ms=1)

    engine = CancellingOcrEngine()
    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])
    monkeypatch.setattr(
        "waybill_ocr.pipeline.iter_priority_ocr_regions",
        lambda image_path, config: [OcrRegion(image_path=priority_path, region_name="priority-left-middle")],
    )
    monkeypatch.setattr(
        "waybill_ocr.pipeline.iter_grid_ocr_regions",
        lambda image_path, config: [OcrRegion(image_path=grid_path, region_name="cell-r1-c1")],
    )

    try:
        process_file(task, AppConfig(), engine, cancel_event=cancel_event)
    except ProcessingCancelled:
        pass

    assert engine.seen == ["waybill.jpg", "priority.png"]


def test_process_file_returns_priority_candidate_without_full_grid(tmp_path: Path, monkeypatch):
    source_path = tmp_path / "waybill.jpg"
    source_path.write_bytes(b"fake")
    priority_path = tmp_path / "priority.png"
    priority_path.write_bytes(b"fake")
    grid_path = tmp_path / "grid.png"
    grid_path.write_bytes(b"fake")
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")
    grid_called = False

    def fake_grid(*_args):
        nonlocal grid_called
        grid_called = True
        return [OcrRegion(image_path=grid_path, region_name="cell-r1-c1")]

    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])
    monkeypatch.setattr(
        "waybill_ocr.pipeline.iter_priority_ocr_regions",
        lambda image_path, config: [OcrRegion(image_path=priority_path, region_name="priority-left-middle")],
    )
    monkeypatch.setattr("waybill_ocr.pipeline.iter_grid_ocr_regions", fake_grid)

    result = process_file(
        task,
        AppConfig(),
        FakeOcrEngine({"waybill.jpg": "no code", "priority.png": "GESU5903360P45G130"}),
    )

    assert result.status == RecognitionStatus.SUCCESS
    assert result.container_code == "GESU5903360"
    assert grid_called is False


def test_process_file_falls_back_to_grid_when_priority_regions_have_no_candidate(tmp_path: Path, monkeypatch):
    source_path = tmp_path / "waybill.jpg"
    source_path.write_bytes(b"fake")
    priority_path = tmp_path / "priority.png"
    priority_path.write_bytes(b"fake")
    grid_path = tmp_path / "grid.png"
    grid_path.write_bytes(b"fake")
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")

    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])
    monkeypatch.setattr(
        "waybill_ocr.pipeline.iter_priority_ocr_regions",
        lambda image_path, config: [OcrRegion(image_path=priority_path, region_name="priority-left-middle")],
    )
    monkeypatch.setattr(
        "waybill_ocr.pipeline.iter_grid_ocr_regions",
        lambda image_path, config: [OcrRegion(image_path=grid_path, region_name="cell-r5-c1")],
    )

    result = process_file(
        task,
        AppConfig(),
        FakeOcrEngine({"waybill.jpg": "no code", "priority.png": "still no code", "grid.png": "GESU5903360P45G130"}),
    )

    assert result.status == RecognitionStatus.SUCCESS
    assert result.container_code == "GESU5903360"



def test_process_file_uses_filename_after_first_pdf_page_has_no_code(tmp_path: Path, monkeypatch):
    first_page = tmp_path / "page-1.png"
    second_page = tmp_path / "page-2.png"
    first_page.write_bytes(b"fake")
    second_page.write_bytes(b"fake")
    task = FileTask(source_path=tmp_path / "HNKU6331795.pdf", relative_name="HNKU6331795.pdf", suffix=".pdf")
    seen_pages = []

    def fake_images(*_args):
        for page in [first_page, second_page]:
            seen_pages.append(page.name)
            yield page

    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", fake_images)
    monkeypatch.setattr("waybill_ocr.pipeline.iter_priority_ocr_regions", lambda *_args: [])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_grid_ocr_regions", lambda *_args: [])

    result = process_file(task, AppConfig(), FakeOcrEngine("no code"))

    assert result.status == RecognitionStatus.SUCCESS
    assert result.container_code == "HNKU6331795"
    assert result.source == RecognitionSource.FILENAME
    assert seen_pages == ["page-1.png", "page-2.png"]


def test_process_file_marks_safe_repaired_ocr_source_and_note(tmp_path: Path, monkeypatch):
    source_path = tmp_path / "waybill.jpg"
    source_path.write_bytes(b"fake")
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")

    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])

    result = process_file(task, AppConfig(), FakeOcrEngine("OCR HINKU6331795"))

    assert result.status == RecognitionStatus.SUCCESS
    assert result.container_code == "HNKU6331795"
    assert result.source == RecognitionSource.OCR_REPAIRED
    assert result.review_note == "OCR\u4fee\u6b63\u539f\u59cb\u7247\u6bb5: HINKU6331795"


def test_process_file_records_guess_like_candidate_without_final_replacement(tmp_path: Path, monkeypatch):
    source_path = tmp_path / "waybill.jpg"
    source_path.write_bytes(b"fake")
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")

    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])

    result = process_file(task, AppConfig(), FakeOcrEngine("OCR HNKU633I795"))

    assert result.status == RecognitionStatus.UNRECOGNIZED
    assert result.container_code is None
    assert result.source is None
    assert result.failure_reason == "NO_CONTAINER_CANDIDATE"
    assert result.review_note == "\u7591\u4f3c\u5019\u9009: HNKU633I795\uff1b\u53ef\u80fd\u4fee\u6b63: HNKU6331795\uff08\u672a\u81ea\u52a8\u91c7\u7528\uff09"
    assert result.review_code == "HNKU6331795"


def test_process_file_prefers_region_ocr_candidate_over_filename_fallback(monkeypatch):
    source_path = Path("HNKU6331795.jpg")
    priority_path = Path("priority.png")
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")

    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])
    monkeypatch.setattr(
        "waybill_ocr.pipeline.iter_priority_ocr_regions",
        lambda image_path, config: [OcrRegion(image_path=priority_path, region_name="priority-left-middle")],
    )
    monkeypatch.setattr("waybill_ocr.pipeline.iter_grid_ocr_regions", lambda *_args: [])

    result = process_file(
        task,
        AppConfig(),
        FakeOcrEngine({"HNKU6331795.jpg": "no code", "priority.png": "CONTAINER GESU5903360 45G1"}),
    )

    assert result.status == RecognitionStatus.SUCCESS
    assert result.container_code == "GESU5903360"
    assert result.source == RecognitionSource.OCR






def test_process_file_fast_mode_includes_full_middle_priority_region(tmp_path: Path, monkeypatch):
    source_path = tmp_path / "waybill.jpg"
    source_path.write_bytes(b"fake")
    left_middle = tmp_path / "left-middle.png"
    left_upper = tmp_path / "left-upper.png"
    full_middle = tmp_path / "full-middle.png"
    grid_path = tmp_path / "grid.png"
    for path in (left_middle, left_upper, full_middle, grid_path):
        path.write_bytes(b"fake")
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")
    grid_called = False

    def fake_grid(*_args):
        nonlocal grid_called
        grid_called = True
        return [OcrRegion(image_path=grid_path, region_name="cell-r5-c1")]

    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])
    monkeypatch.setattr(
        "waybill_ocr.pipeline.iter_priority_ocr_regions",
        lambda image_path, config: [
            OcrRegion(image_path=left_middle, region_name="priority-left-middle"),
            OcrRegion(image_path=left_upper, region_name="priority-left-upper"),
            OcrRegion(image_path=full_middle, region_name="priority-full-middle"),
        ],
    )
    monkeypatch.setattr("waybill_ocr.pipeline.iter_grid_ocr_regions", fake_grid)

    result = process_file(
        task,
        AppConfig(ocr_speed_mode="fast"),
        FakeOcrEngine({
            "waybill.jpg": "no code",
            "left-middle.png": "no code",
            "left-upper.png": "no code",
            "full-middle.png": "MLRU7172277P45G130",
            "grid.png": "MLRU7172277P45G130",
        }),
    )

    assert result.status == RecognitionStatus.SUCCESS
    assert result.container_code == "MLRU7172277"
    assert grid_called is False

def test_process_file_fast_mode_skips_full_grid_when_priority_has_no_candidate(tmp_path: Path, monkeypatch):
    source_path = tmp_path / "waybill.jpg"
    source_path.write_bytes(b"fake")
    priority_path = tmp_path / "priority.png"
    priority_path.write_bytes(b"fake")
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")
    grid_called = False

    def fake_grid(*_args):
        nonlocal grid_called
        grid_called = True
        return []

    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])
    monkeypatch.setattr(
        "waybill_ocr.pipeline.iter_priority_ocr_regions",
        lambda image_path, config: [OcrRegion(image_path=priority_path, region_name="priority-left-middle")],
    )
    monkeypatch.setattr("waybill_ocr.pipeline.iter_grid_ocr_regions", fake_grid)

    result = process_file(task, AppConfig(ocr_speed_mode="fast"), FakeOcrEngine("no code"))

    assert result.status == RecognitionStatus.UNRECOGNIZED
    assert grid_called is False


def test_process_file_fast_mode_records_guess_repair_as_review_note_only(tmp_path: Path, monkeypatch):
    source_path = tmp_path / "waybill.jpg"
    source_path.write_bytes(b"fake")
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")

    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_priority_ocr_regions", lambda *_args: [])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_grid_ocr_regions", lambda *_args: [])

    result = process_file(task, AppConfig(ocr_speed_mode="fast"), FakeOcrEngine("OCR HNKU633I795"))

    assert result.status == RecognitionStatus.UNRECOGNIZED
    assert result.container_code is None
    assert result.review_note == "\u7591\u4f3c\u5019\u9009: HNKU633I795\uff1b\u53ef\u80fd\u4fee\u6b63: HNKU6331795\uff08\u672a\u81ea\u52a8\u91c7\u7528\uff09"
    assert result.review_code == "HNKU6331795"



def test_process_file_carries_relative_name(tmp_path: Path, monkeypatch):
    source_path = tmp_path / "nested" / "waybill.jpg"
    source_path.parent.mkdir()
    source_path.write_bytes(b"fake")
    task = FileTask(source_path=source_path, relative_name="nested/waybill.jpg", suffix=".jpg")

    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])

    result = process_file(task, AppConfig(), FakeOcrEngine("HNKU6331795"))

    assert result.relative_name == "nested/waybill.jpg"


def test_process_file_notes_region_crop_failure_when_unrecognized(tmp_path: Path, monkeypatch):
    source_path = tmp_path / "waybill.jpg"
    source_path.write_bytes(b"fake")
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")

    def raise_crop_error(*_args):
        raise RuntimeError("crop failed")

    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_priority_ocr_regions", raise_crop_error)
    monkeypatch.setattr("waybill_ocr.pipeline.iter_grid_ocr_regions", lambda *_args: [])

    result = process_file(task, AppConfig(), FakeOcrEngine("no code"))

    assert result.status == RecognitionStatus.UNRECOGNIZED
    assert result.review_note is not None
    assert "\u533a\u57df\u88c1\u526a\u5931\u8d25" in result.review_note


def test_process_file_uses_enhanced_candidate_when_base_valid_candidate_conflicts_with_suspicious_text(
    tmp_path: Path, monkeypatch
):
    source_path = tmp_path / "waybill.jpg"
    source_path.write_bytes(b"fake")
    priority_path = tmp_path / "priority-left-middle.png"
    priority_path.write_bytes(b"fake")
    enhanced_path = tmp_path / "enhanced-full-middle.png"
    enhanced_path.write_bytes(b"fake")
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")

    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])
    monkeypatch.setattr(
        "waybill_ocr.pipeline.iter_priority_ocr_regions",
        lambda image_path, config: [OcrRegion(image_path=priority_path, region_name="priority-left-middle")],
    )
    monkeypatch.setattr("waybill_ocr.pipeline.iter_grid_ocr_regions", lambda *_args: [])
    monkeypatch.setattr(
        "waybill_ocr.pipeline.iter_enhanced_ocr_regions",
        lambda task, image_path, config: [OcrRegion(image_path=enhanced_path, region_name="enhanced-full-middle")],
        raising=False,
    )

    result = process_file(
        task,
        AppConfig(ocr_speed_mode="balanced"),
        FakeOcrEngine(
            {
                "waybill.jpg": "noise TEMUGTT9790 45G1",
                "priority-left-middle.png": "TEMU77979045G132500",
                "enhanced-full-middle.png": "TEMU677979045G132500",
            }
        ),
    )

    assert result.status == RecognitionStatus.SUCCESS
    assert result.container_code == "TEMU6779790"
    assert result.source == RecognitionSource.OCR_ENHANCED
    assert result.review_note == "\u589e\u5f3a\u8bc6\u522b\u8986\u76d6\u4f4e\u6e05\u6670\u5ea6\u5019\u9009: TEMU7797904 -> TEMU6779790"


def test_process_file_fast_mode_marks_conflicting_candidate_for_review_without_enhancement(tmp_path: Path, monkeypatch):
    source_path = tmp_path / "waybill.jpg"
    source_path.write_bytes(b"fake")
    priority_path = tmp_path / "priority-left-middle.png"
    priority_path.write_bytes(b"fake")
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")

    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])
    monkeypatch.setattr(
        "waybill_ocr.pipeline.iter_priority_ocr_regions",
        lambda image_path, config: [OcrRegion(image_path=priority_path, region_name="priority-left-middle")],
    )
    monkeypatch.setattr("waybill_ocr.pipeline.iter_grid_ocr_regions", lambda *_args: [])

    result = process_file(
        task,
        AppConfig(ocr_speed_mode="fast"),
        FakeOcrEngine({"waybill.jpg": "noise TEMUGTT9790", "priority-left-middle.png": "TEMU77979045G132500"}),
    )

    assert result.status == RecognitionStatus.INVALID
    assert result.container_code == "TEMU7797904"
    assert result.failure_reason == "CONFLICTING_CANDIDATES"
    assert result.review_note == "\u5019\u9009\u51b2\u7a81\uff0c\u9700\u4eba\u5de5\u590d\u6838: TEMU7797904\uff1b\u7591\u4f3c\u5019\u9009: TEMUGTT9790"


def test_process_file_uses_enhanced_candidate_when_base_candidate_has_invalid_check_digit(tmp_path: Path, monkeypatch):
    source_path = tmp_path / "waybill.jpg"
    source_path.write_bytes(b"fake")
    enhanced_path = tmp_path / "enhanced-full-middle.png"
    enhanced_path.write_bytes(b"fake")
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")

    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_priority_ocr_regions", lambda *_args: [])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_grid_ocr_regions", lambda *_args: [])
    monkeypatch.setattr(
        "waybill_ocr.pipeline.iter_enhanced_ocr_regions",
        lambda task, image_path, config: [OcrRegion(image_path=enhanced_path, region_name="enhanced-full-middle")],
        raising=False,
    )

    result = process_file(
        task,
        AppConfig(ocr_speed_mode="balanced"),
        FakeOcrEngine({"waybill.jpg": "MEDU18591845G132500", "enhanced-full-middle.png": "MEDU418591845G132500"}),
    )

    assert result.status == RecognitionStatus.SUCCESS
    assert result.container_code == "MEDU4185918"
    assert result.source == RecognitionSource.OCR_ENHANCED
    assert result.review_note == "\u589e\u5f3a\u8bc6\u522b\u4fee\u590d\u65e0\u6548\u5019\u9009: MEDU1859184 -> MEDU4185918"


def test_process_file_continues_after_single_region_ocr_failure(tmp_path: Path, monkeypatch):
    source_path = tmp_path / "waybill.jpg"
    source_path.write_bytes(b"fake")
    priority_path = tmp_path / "priority-left-middle.png"
    priority_path.write_bytes(b"fake")
    grid_path = tmp_path / "cell-r5-c1.png"
    grid_path.write_bytes(b"fake")
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")

    class FailingRegionOcrEngine:
        def recognize_image(self, image_path: Path, cancel_event=None, *, psm: int | None = None) -> OcrResult:
            if image_path.name == "priority-left-middle.png":
                raise RuntimeError("empty OCR text")
            text = "GESU5903360P45G130" if image_path.name == "cell-r5-c1.png" else "no code"
            return OcrResult(text=text, engine_name="fake", elapsed_ms=1)

    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])
    monkeypatch.setattr(
        "waybill_ocr.pipeline.iter_priority_ocr_regions",
        lambda image_path, config: [OcrRegion(image_path=priority_path, region_name="priority-left-middle")],
    )
    monkeypatch.setattr(
        "waybill_ocr.pipeline.iter_grid_ocr_regions",
        lambda image_path, config: [OcrRegion(image_path=grid_path, region_name="cell-r5-c1")],
    )

    result = process_file(task, AppConfig(), FailingRegionOcrEngine())

    assert result.status == RecognitionStatus.SUCCESS
    assert result.container_code == "GESU5903360"
    assert "\u533a\u57df OCR \u5931\u8d25" in result.ocr_text



def test_process_file_does_not_set_review_code_for_ambiguous_single_digit_repair(tmp_path: Path, monkeypatch):
    source_path = tmp_path / "waybill.jpg"
    source_path.write_bytes(b"fake")
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")

    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_priority_ocr_regions", lambda *_args: [])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_grid_ocr_regions", lambda *_args: [])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_enhanced_ocr_regions", lambda *_args: [], raising=False)

    result = process_file(task, AppConfig(), FakeOcrEngine("OCR YYCU6002610"))

    assert result.status == RecognitionStatus.INVALID
    assert result.container_code == "YYCU6002610"
    assert result.failure_reason == "INVALID_CHECK_DIGIT"
    assert result.review_code is None
    assert result.review_note is not None
    assert "多个疑似校验修正候选" in result.review_note
    assert "YYCU6003610" in result.review_note

def test_fast_mode_keeps_review_candidate_as_unrecognized(tmp_path: Path, monkeypatch):
    source_path = tmp_path / "waybill.jpg"
    source_path.write_bytes(b"fake")
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")

    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_priority_ocr_regions", lambda *_args: [])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_grid_ocr_regions", lambda *_args: [])

    result = process_file(task, AppConfig(ocr_speed_mode="fast"), FakeOcrEngine("UACUSSO2014 UACUS5O2014"))

    assert result.status == RecognitionStatus.UNRECOGNIZED
    assert result.review_code == "UACU5502014"


def test_balanced_mode_promotes_review_candidate_after_enhanced_confirmation(tmp_path: Path, monkeypatch):
    source_path = tmp_path / "waybill.jpg"
    source_path.write_bytes(b"fake")
    enhanced_path = tmp_path / "enhanced.png"
    enhanced_path.write_bytes(b"fake")
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")

    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_priority_ocr_regions", lambda *_args: [])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_grid_ocr_regions", lambda *_args: [])
    monkeypatch.setattr(
        "waybill_ocr.pipeline.iter_enhanced_ocr_regions",
        lambda *_args: [OcrRegion(image_path=enhanced_path, region_name="enhanced-full-middle")],
    )

    result = process_file(
        task,
        AppConfig(ocr_speed_mode="balanced"),
        FakeOcrEngine({"waybill.jpg": "UACUSSO2014", "enhanced.png": "UACU5502014 45G1"}),
    )

    assert result.status == RecognitionStatus.SUCCESS
    assert result.container_code == "UACU5502014"
    assert result.source == RecognitionSource.OCR_ENHANCED


def test_fast_mode_does_not_pick_ambiguous_digit_repair(tmp_path: Path, monkeypatch):
    source_path = tmp_path / "waybill.jpg"
    source_path.write_bytes(b"fake")
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")

    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_priority_ocr_regions", lambda *_args: [])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_grid_ocr_regions", lambda *_args: [])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_enhanced_ocr_regions", lambda *_args: [])

    result = process_file(task, AppConfig(ocr_speed_mode="fast"), FakeOcrEngine("YYCU6002610"))

    assert result.status == RecognitionStatus.INVALID
    assert result.review_code is None


def test_stable_mode_selects_clear_digit_repair_with_enhanced_evidence(tmp_path: Path, monkeypatch):
    source_path = tmp_path / "waybill.jpg"
    source_path.write_bytes(b"fake")
    enhanced_path = tmp_path / "enhanced.png"
    enhanced_path.write_bytes(b"fake")
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")

    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_priority_ocr_regions", lambda *_args: [])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_grid_ocr_regions", lambda *_args: [])
    monkeypatch.setattr(
        "waybill_ocr.pipeline.iter_enhanced_ocr_regions",
        lambda *_args: [OcrRegion(image_path=enhanced_path, region_name="enhanced-full-middle")],
    )

    result = process_file(
        task,
        AppConfig(ocr_speed_mode="stable"),
        FakeOcrEngine({"waybill.jpg": "YYCU6002610", "enhanced.png": "YYCU6003610 45G1"}),
    )

    assert result.status == RecognitionStatus.SUCCESS
    assert result.container_code == "YYCU6003610"

def test_enhanced_ocr_does_not_promote_unrelated_valid_code_for_invalid_candidate(tmp_path: Path, monkeypatch):
    source_path = tmp_path / "waybill.jpg"
    source_path.write_bytes(b"fake")
    enhanced_path = tmp_path / "enhanced.png"
    enhanced_path.write_bytes(b"fake")
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")

    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_priority_ocr_regions", lambda *_args: [])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_grid_ocr_regions", lambda *_args: [])
    monkeypatch.setattr(
        "waybill_ocr.pipeline.iter_enhanced_ocr_regions",
        lambda *_args: [OcrRegion(image_path=enhanced_path, region_name="enhanced-full-middle")],
    )

    result = process_file(
        task,
        AppConfig(ocr_speed_mode="stable"),
        FakeOcrEngine({"waybill.jpg": "YYCU6002610", "enhanced.png": "HNKU6331795 45G1"}),
    )

    assert result.status == RecognitionStatus.INVALID
    assert result.container_code == "YYCU6002610"
    assert result.failure_reason == "INVALID_CHECK_DIGIT"

def test_enhanced_ocr_uses_multiple_psm_in_stable_mode(tmp_path: Path, monkeypatch):
    calls = []
    source_path = tmp_path / "waybill.jpg"
    source_path.write_bytes(b"fake")
    enhanced_path = tmp_path / "enhanced.png"
    enhanced_path.write_bytes(b"fake")
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")

    class RecordingOcrEngine:
        def recognize_image(self, image_path, cancel_event=None, *, psm=None):
            calls.append(psm)
            return OcrResult(text="no code", engine_name="fake", elapsed_ms=1)

    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_priority_ocr_regions", lambda *_args: [])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_grid_ocr_regions", lambda *_args: [])
    monkeypatch.setattr(
        "waybill_ocr.pipeline.iter_enhanced_ocr_regions",
        lambda *_args: [OcrRegion(image_path=enhanced_path, region_name="enhanced")],
    )

    process_file(task, AppConfig(ocr_speed_mode="stable"), RecordingOcrEngine())

    assert 6 in calls
    assert 7 in calls
    assert 11 in calls


def test_balanced_pdf_enhanced_ocr_stops_after_cross_resolution_confirmation(tmp_path: Path, monkeypatch):
    source_path = tmp_path / "waybill.pdf"
    source_path.write_bytes(b"fake")
    region_paths = []
    for name in ("full-middle", "left-middle", "left-lower-middle", "fallback"):
        region_path = tmp_path / f"{name}.png"
        region_path.write_bytes(b"fake")
        region_paths.append(region_path)
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".pdf")
    calls: list[str] = []

    class RecordingOcrEngine:
        def recognize_image(self, image_path, cancel_event=None, *, psm=None):
            calls.append(image_path.name)
            text = "no code" if image_path == source_path else "GESU5903360 45G1"
            return OcrResult(text=text, engine_name="fake", elapsed_ms=1)

    regions = [
        OcrRegion(image_path=region_paths[0], region_name="enhanced-400dpi-full-middle-plain"),
        OcrRegion(image_path=region_paths[1], region_name="enhanced-400dpi-left-middle-plain"),
        OcrRegion(image_path=region_paths[2], region_name="enhanced-400dpi-left-lower-middle-plain"),
        OcrRegion(image_path=region_paths[3], region_name="enhanced-base-full-middle-plain"),
    ]
    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_priority_ocr_regions", lambda *_args: [])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_grid_ocr_regions", lambda *_args: [])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_enhanced_ocr_regions", lambda *_args: regions)

    result = process_file(task, AppConfig(ocr_speed_mode="balanced"), RecordingOcrEngine())

    assert result.status == RecognitionStatus.SUCCESS
    assert result.container_code == "GESU5903360"
    assert calls.count("full-middle.png") == 2
    assert calls.count("left-middle.png") == 2
    assert calls.count("left-lower-middle.png") == 2
    assert calls.count("fallback.png") == 2


def test_balanced_pdf_enhanced_ocr_does_not_stop_before_base_resolution_conflict(tmp_path: Path, monkeypatch):
    source_path = tmp_path / "waybill.pdf"
    source_path.write_bytes(b"fake")
    region_paths = []
    for name in ("high-first", "high-second", "high-third", "base-confirm", "base-fallback"):
        region_path = tmp_path / f"{name}.png"
        region_path.write_bytes(b"fake")
        region_paths.append(region_path)
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".pdf")
    calls: list[str] = []

    class ConflictingResolutionOcrEngine:
        def recognize_image(self, image_path, cancel_event=None, *, psm=None):
            calls.append(image_path.name)
            if image_path.name.startswith("high-"):
                text = "TEMU7797904 45G1"
            elif image_path.name.startswith("base-"):
                text = "TEMU6779790 45G1"
            else:
                text = "no code"
            return OcrResult(text=text, engine_name="fake", elapsed_ms=1)

    regions = [
        OcrRegion(image_path=region_paths[0], region_name="enhanced-400dpi-full-middle-plain"),
        OcrRegion(image_path=region_paths[1], region_name="enhanced-400dpi-left-middle-plain"),
        OcrRegion(image_path=region_paths[2], region_name="enhanced-400dpi-left-lower-middle-plain"),
        OcrRegion(image_path=region_paths[3], region_name="enhanced-base-full-middle-plain"),
        OcrRegion(image_path=region_paths[4], region_name="enhanced-base-left-middle-plain"),
    ]
    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_priority_ocr_regions", lambda *_args: [])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_grid_ocr_regions", lambda *_args: [])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_enhanced_ocr_regions", lambda *_args: regions)

    process_file(task, AppConfig(ocr_speed_mode="balanced"), ConflictingResolutionOcrEngine())

    assert calls.count("base-confirm.png") == 2
    assert calls.count("base-fallback.png") == 2


def test_balanced_enhanced_ocr_keeps_full_fallback_on_candidate_conflict(tmp_path: Path, monkeypatch):
    source_path = tmp_path / "waybill.jpg"
    source_path.write_bytes(b"fake")
    region_paths = []
    for name in ("first", "second", "third", "fallback"):
        region_path = tmp_path / f"{name}.png"
        region_path.write_bytes(b"fake")
        region_paths.append(region_path)
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")
    calls: list[str] = []

    class ConflictingOcrEngine:
        def recognize_image(self, image_path, cancel_event=None, *, psm=None):
            calls.append(image_path.name)
            texts = {
                "first.png": "GESU5903360 45G1",
                "second.png": "HNKU6331795 45G1",
                "third.png": "GESU5903360 45G1",
                "fallback.png": "GESU5903360 45G1",
            }
            return OcrResult(text=texts.get(image_path.name, "no code"), engine_name="fake", elapsed_ms=1)

    regions = [
        OcrRegion(image_path=path, region_name=f"enhanced-400dpi-{path.stem}-plain")
        for path in region_paths
    ]
    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_priority_ocr_regions", lambda *_args: [])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_grid_ocr_regions", lambda *_args: [])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_enhanced_ocr_regions", lambda *_args: regions)

    process_file(task, AppConfig(ocr_speed_mode="balanced"), ConflictingOcrEngine())

    assert calls.count("fallback.png") == 2


def test_stable_enhanced_ocr_never_uses_staged_early_stop(tmp_path: Path, monkeypatch):
    source_path = tmp_path / "waybill.jpg"
    source_path.write_bytes(b"fake")
    region_paths = []
    for name in ("first", "second", "third", "fallback"):
        region_path = tmp_path / f"{name}.png"
        region_path.write_bytes(b"fake")
        region_paths.append(region_path)
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")
    calls: list[str] = []

    class RecordingOcrEngine:
        def recognize_image(self, image_path, cancel_event=None, *, psm=None):
            calls.append(image_path.name)
            text = "no code" if image_path == source_path else "GESU5903360 45G1"
            return OcrResult(text=text, engine_name="fake", elapsed_ms=1)

    regions = [
        OcrRegion(image_path=path, region_name=f"enhanced-400dpi-{path.stem}-plain")
        for path in region_paths
    ]
    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_priority_ocr_regions", lambda *_args: [])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_grid_ocr_regions", lambda *_args: [])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_enhanced_ocr_regions", lambda *_args: regions)

    process_file(task, AppConfig(ocr_speed_mode="stable"), RecordingOcrEngine())

    assert calls.count("fallback.png") == 3
