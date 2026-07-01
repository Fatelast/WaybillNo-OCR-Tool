from pathlib import Path

from waybill_ocr.config import AppConfig
from waybill_ocr.image_regions import OcrRegion
from waybill_ocr.models import FileTask, RecognitionSource, RecognitionStatus
from waybill_ocr.ocr.base import OcrResult
from waybill_ocr.pipeline import process_file


class FakeOcrEngine:
    def __init__(self, text_or_texts: str | dict[str, str]) -> None:
        self.text_or_texts = text_or_texts

    def recognize_image(self, image_path: Path) -> OcrResult:
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


def test_process_file_prefers_region_candidate_over_full_page_noise(tmp_path: Path, monkeypatch):
    source_path = tmp_path / "waybill.jpg"
    source_path.write_bytes(b"fake")
    region_path = tmp_path / "cell-r5-c1.png"
    region_path.write_bytes(b"fake")
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")

    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])
    monkeypatch.setattr(
        "waybill_ocr.pipeline.iter_ocr_regions",
        lambda image_path: [
            OcrRegion(image_path=image_path, region_name="full"),
            OcrRegion(image_path=region_path, region_name="cell-r5-c1"),
        ],
    )

    result = process_file(
        task,
        AppConfig(),
        FakeOcrEngine(
            {
                "waybill.jpg": "YBXKIKOOMIJIP 5617782 J0YBEXK",
                "cell-r5-c1.png": "GESU5903360P45G130",
            }
        ),
    )

    assert result.status == RecognitionStatus.SUCCESS
    assert result.container_code == "GESU5903360"
    assert result.source == RecognitionSource.OCR
