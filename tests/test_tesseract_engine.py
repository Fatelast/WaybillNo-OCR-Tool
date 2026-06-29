from pathlib import Path

import pytest

from waybill_ocr.config import AppConfig
from waybill_ocr.ocr.tesseract_engine import TesseractEngine


class FakePytesseract:
    class pytesseract:
        tesseract_cmd = ""

    calls = []

    @classmethod
    def image_to_string(cls, image_path: str, lang: str, config: str) -> str:
        cls.calls.append((image_path, lang, config))
        return "HNKU6331795"


def test_tesseract_engine_recognizes_image_with_whitelist_config(tmp_path: Path):
    FakePytesseract.calls = []
    image_path = tmp_path / "waybill.png"
    image_path.write_bytes(b"fake")
    engine = TesseractEngine(
        AppConfig(tesseract_cmd=Path("tools/tesseract/tesseract.exe")),
        pytesseract_module=FakePytesseract,
    )

    result = engine.recognize_image(image_path)

    assert result.text == "HNKU6331795"
    assert result.engine_name == "tesseract"
    assert FakePytesseract.pytesseract.tesseract_cmd == "tools\\tesseract\\tesseract.exe"
    assert FakePytesseract.calls == [
        (
            str(image_path),
            "eng",
            "--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        )
    ]


def test_tesseract_engine_reports_missing_pytesseract(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pytesseract":
            raise ModuleNotFoundError("No module named 'pytesseract'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    engine = TesseractEngine(AppConfig())

    with pytest.raises(RuntimeError, match="缺少 pytesseract 依赖"):
        engine.recognize_image(Path("waybill.png"))
