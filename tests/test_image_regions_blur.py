from contextlib import contextmanager
from pathlib import Path

from PIL import Image

from waybill_ocr.config import AppConfig
from waybill_ocr.image_regions import iter_enhanced_ocr_regions
from waybill_ocr.models import FileTask


def test_balanced_pdf_adds_binary_fallback_for_high_dpi_blurred_regions(tmp_path, monkeypatch):
    source_path = tmp_path / "waybill.pdf"
    source_path.write_bytes(b"fake")
    base_image_path = tmp_path / "page-1.png"
    Image.new("RGB", (240, 180), "white").save(base_image_path)
    high_dpi_page = Image.new("RGB", (320, 240), "white")

    @contextmanager
    def fake_temporary_directory(_config):
        work_dir = tmp_path / "enhanced-work"
        work_dir.mkdir(exist_ok=True)
        yield work_dir

    monkeypatch.setattr("waybill_ocr.image_regions.temporary_directory", fake_temporary_directory)
    monkeypatch.setattr("waybill_ocr.image_regions._convert_pdf_page", lambda *_args, **_kwargs: [high_dpi_page])
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".pdf")

    regions = list(iter_enhanced_ocr_regions(task, base_image_path, AppConfig(ocr_speed_mode="balanced")))
    names = [region.region_name for region in regions]

    assert "enhanced-400dpi-full-middle-x2binary" in names
    assert "enhanced-base-full-middle-x2binary" not in names
