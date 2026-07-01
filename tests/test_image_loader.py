from pathlib import Path

import pytest

from waybill_ocr.config import AppConfig
import waybill_ocr.image_loader as image_loader
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
        if kwargs["first_page"] > 1:
            return []
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
            "last_page": 1,
        },
        {
            "pdf_path": str(pdf_path),
            "dpi": 300,
            "poppler_path": "tools\\poppler",
            "first_page": 2,
            "last_page": 2,
        },
    ]


def test_iter_images_for_ocr_reports_missing_pdf2image(monkeypatch, tmp_path: Path):
    import builtins

    pdf_path = tmp_path / "waybill.pdf"
    pdf_path.write_bytes(b"fake")
    monkeypatch.setattr(image_loader, "convert_from_path", None)
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pdf2image":
            raise ModuleNotFoundError("No module named 'pdf2image'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError, match="缺少 pdf2image 依赖"):
        list(iter_images_for_ocr(pdf_path, AppConfig()))

def test_iter_images_for_ocr_converts_pdf_one_page_at_a_time(tmp_path: Path, monkeypatch):
    pdf_path = tmp_path / "waybill.pdf"
    pdf_path.write_bytes(b"fake")
    calls = []

    class FakePage:
        def __init__(self, page_number: int) -> None:
            self.page_number = page_number

        def save(self, target_path: Path) -> None:
            Path(target_path).write_text(str(self.page_number), encoding="utf-8")

    def fake_convert_from_path(**kwargs):
        calls.append(kwargs)
        page_number = kwargs["first_page"]
        if page_number > 2:
            return []
        return [FakePage(page_number)]

    monkeypatch.setattr("waybill_ocr.image_loader.convert_from_path", fake_convert_from_path)

    iterator = iter_images_for_ocr(pdf_path, AppConfig())
    first = next(iterator)

    assert first.name == "page-1.png"
    assert first.read_text(encoding="utf-8") == "1"
    assert calls == [
        {
            "pdf_path": str(pdf_path),
            "dpi": 300,
            "poppler_path": None,
            "first_page": 1,
            "last_page": 1,
        }
    ]

    second = next(iterator)

    assert second.name == "page-2.png"
    assert second.read_text(encoding="utf-8") == "2"
    assert calls[-1]["first_page"] == 2
    assert calls[-1]["last_page"] == 2
