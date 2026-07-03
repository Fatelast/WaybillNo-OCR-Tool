from pathlib import Path

from waybill_ocr.config import AppConfig
from waybill_ocr.image_regions import OcrRegion
from waybill_ocr.models import FileTask, RecognitionSource, RecognitionStatus
from waybill_ocr.ocr.base import OcrResult
from waybill_ocr.pipeline import process_file


class FakeOcrEngine:
    def __init__(self, text_or_texts: str | dict[str, str]) -> None:
        self.text_or_texts = text_or_texts

    def recognize_image(self, image_path: Path, cancel_event=None) -> OcrResult:
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

        def recognize_image(self, image_path: Path, cancel_event=None) -> OcrResult:
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
