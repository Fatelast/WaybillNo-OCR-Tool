from pathlib import Path

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
