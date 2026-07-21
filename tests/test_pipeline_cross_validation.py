from pathlib import Path

from waybill_ocr.config import AppConfig
from waybill_ocr.image_regions import OcrRegion
from waybill_ocr.models import FileTask, RecognitionSource, RecognitionStatus
from waybill_ocr.ocr.base import OcrResult
from waybill_ocr.pipeline import process_file


class RecordingOcrEngine:
    def __init__(self, texts: dict[tuple[str, int | None] | str, str]) -> None:
        self.texts = texts
        self.calls: list[tuple[str, int | None]] = []

    def recognize_image(self, image_path: Path, cancel_event=None, *, psm: int | None = None) -> OcrResult:
        key = (image_path.name, psm)
        self.calls.append(key)
        text = self.texts.get(key, self.texts.get(image_path.name, ""))
        return OcrResult(text=text, engine_name="fake", elapsed_ms=1)


def _task(source_path: Path) -> FileTask:
    return FileTask(
        source_path=source_path,
        relative_name=source_path.name,
        suffix=source_path.suffix.lower(),
    )


def _region(tmp_path: Path, name: str, region_name: str | None = None) -> OcrRegion:
    path = tmp_path / name
    path.write_bytes(b"fake")
    return OcrRegion(image_path=path, region_name=region_name or path.stem)


def test_balanced_pdf_corrects_single_legal_candidate_after_enhanced_cross_validation(tmp_path, monkeypatch):
    source_path = tmp_path / "waybill.pdf"
    source_path.write_bytes(b"fake")
    page = _region(tmp_path, "page.png", "full")
    priority = _region(tmp_path, "priority.png", "priority-left-middle")
    enhanced_regions = [
        _region(tmp_path, "high-full.png", "enhanced-400dpi-full-middle-plain"),
        _region(tmp_path, "high-left.png", "enhanced-400dpi-left-middle-plain"),
        _region(tmp_path, "base-full.png", "enhanced-base-full-middle-plain"),
    ]
    engine = RecordingOcrEngine(
        {
            "page.png": "no code",
            "priority.png": "TEMU7797904 45G1",
            "high-full.png": "TEMU6779790 45G1",
            "high-left.png": "TEMU6779790 45G1",
            "base-full.png": "TEMU6779790 45G1",
        }
    )
    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [page.image_path])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_priority_ocr_regions", lambda *_args: [priority])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_grid_ocr_regions", lambda *_args: [])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_enhanced_ocr_regions", lambda *_args: enhanced_regions)

    result = process_file(_task(source_path), AppConfig(ocr_speed_mode="balanced"), engine)

    assert result.status is RecognitionStatus.SUCCESS
    assert result.container_code == "TEMU6779790"
    assert result.source is RecognitionSource.OCR_ENHANCED
    assert any(name == "high-full.png" for name, _psm in engine.calls)


def test_balanced_pdf_does_not_accept_unconfirmed_single_legal_candidate(tmp_path, monkeypatch):
    source_path = tmp_path / "waybill.pdf"
    source_path.write_bytes(b"fake")
    page = _region(tmp_path, "page.png", "full")
    priority = _region(tmp_path, "priority.png", "priority-left-middle")
    enhanced = _region(tmp_path, "enhanced.png", "enhanced-400dpi-full-middle-plain")
    engine = RecordingOcrEngine(
        {
            "page.png": "no code",
            "priority.png": "TEMU7797904 45G1",
            "enhanced.png": "TEMU6779790 45G1",
        }
    )
    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [page.image_path])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_priority_ocr_regions", lambda *_args: [priority])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_grid_ocr_regions", lambda *_args: [])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_enhanced_ocr_regions", lambda *_args: [enhanced])

    result = process_file(_task(source_path), AppConfig(ocr_speed_mode="balanced"), engine)

    assert result.status is RecognitionStatus.INVALID
    assert result.review_code == "TEMU7797904"
    assert result.failure_reason == "INSUFFICIENT_CANDIDATE_EVIDENCE"


def test_balanced_pdf_stops_priority_ocr_after_second_base_confirmation(tmp_path, monkeypatch):
    source_path = tmp_path / "waybill.pdf"
    source_path.write_bytes(b"fake")
    page = _region(tmp_path, "page.png", "full")
    first = _region(tmp_path, "priority-first.png", "priority-left-middle")
    unused = _region(tmp_path, "priority-unused.png", "priority-left-upper")
    engine = RecordingOcrEngine(
        {
            "page.png": "GESU5903360 45G1",
            "priority-first.png": "GESU5903360 45G1",
            "priority-unused.png": "must not run",
        }
    )
    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [page.image_path])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_priority_ocr_regions", lambda *_args: [first, unused])
    monkeypatch.setattr(
        "waybill_ocr.pipeline.iter_enhanced_ocr_regions",
        lambda *_args: (_ for _ in ()).throw(AssertionError("enhancement must not run")),
    )

    result = process_file(_task(source_path), AppConfig(ocr_speed_mode="balanced"), engine)

    assert result.status is RecognitionStatus.SUCCESS
    assert result.container_code == "GESU5903360"
    assert engine.calls == [("page.png", None), ("priority-first.png", None)]


def test_priority_ocr_stops_after_two_independent_regions_agree(tmp_path, monkeypatch):
    source_path = tmp_path / "waybill.jpg"
    source_path.write_bytes(b"fake")
    first = _region(tmp_path, "priority-first.png", "priority-left-middle")
    second = _region(tmp_path, "priority-second.png", "priority-full-middle")
    unused = _region(tmp_path, "priority-unused.png", "priority-left-lower-middle")
    engine = RecordingOcrEngine(
        {
            "waybill.jpg": "no code",
            "priority-first.png": "GESU5903360 45G1",
            "priority-second.png": "GESU5903360 45G1",
            "priority-unused.png": "must not run",
        }
    )
    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_priority_ocr_regions", lambda *_args: [first, second, unused])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_grid_ocr_regions", lambda *_args: [])

    result = process_file(_task(source_path), AppConfig(ocr_speed_mode="balanced"), engine)

    assert result.status is RecognitionStatus.SUCCESS
    assert ("priority-unused.png", None) not in engine.calls


def test_balanced_enhancement_skips_redundant_psm_and_sibling_variants(tmp_path, monkeypatch):
    source_path = tmp_path / "waybill.pdf"
    source_path.write_bytes(b"fake")
    names = ["high-full", "high-full-sharp", "high-left", "high-left-sharp", "base-full", "unused"]
    paths = {name: _region(tmp_path, f"{name}.png") for name in names}
    enhanced_regions = [
        OcrRegion(paths["high-full"].image_path, "enhanced-400dpi-full-middle-plain"),
        OcrRegion(paths["high-full-sharp"].image_path, "enhanced-400dpi-full-middle-x2sharp"),
        OcrRegion(paths["high-left"].image_path, "enhanced-400dpi-left-middle-plain"),
        OcrRegion(paths["high-left-sharp"].image_path, "enhanced-400dpi-left-middle-x2sharp"),
        OcrRegion(paths["base-full"].image_path, "enhanced-base-full-middle-plain"),
        OcrRegion(paths["unused"].image_path, "enhanced-base-left-middle-plain"),
    ]
    texts = {name + ".png": "GESU5903360 45G1" for name in names}
    texts["waybill.pdf"] = "no code"
    engine = RecordingOcrEngine(texts)
    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_priority_ocr_regions", lambda *_args: [])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_grid_ocr_regions", lambda *_args: [])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_enhanced_ocr_regions", lambda *_args: enhanced_regions)

    result = process_file(_task(source_path), AppConfig(ocr_speed_mode="balanced"), engine)

    assert result.status is RecognitionStatus.SUCCESS
    enhanced_calls = [(name, psm) for name, psm in engine.calls if name != "waybill.pdf"]
    assert enhanced_calls == [
        ("high-full.png", 6),
        ("high-full.png", 11),
        ("high-left.png", 6),
        ("base-full.png", 6),
    ]


def test_balanced_pdf_accepts_two_high_dpi_preprocess_variants_for_legal_override(tmp_path, monkeypatch):
    source_path = tmp_path / "waybill.pdf"
    source_path.write_bytes(b"fake")
    page = _region(tmp_path, "page.png", "full")
    priority = _region(tmp_path, "priority.png", "priority-left-middle")
    plain = _region(tmp_path, "high-full-plain.png", "enhanced-400dpi-full-middle-plain")
    sharpened = _region(tmp_path, "high-full-sharp.png", "enhanced-400dpi-full-middle-x2sharp")
    engine = RecordingOcrEngine(
        {
            "page.png": "no code",
            "priority.png": "TEMU7797904 45G1",
            ("high-full-plain.png", 6): "TEMU6779790 45G1",
            ("high-full-plain.png", 11): "no code",
            ("high-full-sharp.png", 6): "TEMU6779790 45G1",
        }
    )
    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [page.image_path])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_priority_ocr_regions", lambda *_args: [priority])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_grid_ocr_regions", lambda *_args: [])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_enhanced_ocr_regions", lambda *_args: [plain, sharpened])

    result = process_file(_task(source_path), AppConfig(ocr_speed_mode="balanced"), engine)

    assert result.status is RecognitionStatus.SUCCESS
    assert result.container_code == "TEMU6779790"
    assert result.source is RecognitionSource.OCR_ENHANCED
