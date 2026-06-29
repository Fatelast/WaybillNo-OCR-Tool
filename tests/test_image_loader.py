from pathlib import Path

from waybill_ocr.config import AppConfig
from waybill_ocr.image_loader import iter_images_for_ocr


def test_iter_images_for_ocr_yields_image_path(tmp_path: Path):
    image_path = tmp_path / "waybill.jpg"
    image_path.write_bytes(b"fake")

    assert list(iter_images_for_ocr(image_path, AppConfig())) == [image_path]


def test_iter_images_for_ocr_converts_pdf_pages(tmp_path: Path, monkeypatch):
    pdf_path = tmp_path / "waybill.pdf"
    pdf_path.write_bytes(b"fake")
    calls = []

    class FakePage:
        def save(self, target_path: Path) -> None:
            Path(target_path).write_bytes(b"page")

    def fake_convert_from_path(**kwargs):
        calls.append(kwargs)
        return [FakePage()]

    monkeypatch.setattr("waybill_ocr.image_loader.convert_from_path", fake_convert_from_path)

    yielded_names = []
    for image_path in iter_images_for_ocr(pdf_path, AppConfig(poppler_path=Path("tools/poppler"))):
        yielded_names.append(image_path.name)
        assert image_path.read_bytes() == b"page"

    assert yielded_names == ["page-1.png"]
    assert calls == [
        {
            "pdf_path": str(pdf_path),
            "dpi": 300,
            "poppler_path": "tools\\poppler",
            "first_page": 1,
        }
    ]
