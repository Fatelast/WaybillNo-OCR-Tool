from pathlib import Path

from waybill_ocr.config import AppConfig
from waybill_ocr.models import FileTask, RecognitionSource, RecognitionStatus
from waybill_ocr.ocr.base import OcrResult
from waybill_ocr.pipeline import process_file


class FakeOcrEngine:
    def __init__(self, text: str) -> None:
        self.text = text

    def recognize_image(self, image_path: Path) -> OcrResult:
        return OcrResult(text=self.text, engine_name="fake", elapsed_ms=1)


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
