from pathlib import Path

from waybill_ocr.delivery import (
    CURRENT_VERSION,
    current_version_doc_name,
    offline_zip_name,
    required_delivery_doc_names,
    version_notes_text,
)


ROOT = Path(__file__).resolve().parents[1]


def test_delivery_version_and_zip_name_are_canonical():
    assert CURRENT_VERSION == "v1.0.2"
    assert offline_zip_name() == "\u8fd0\u5355\u7bb1\u53f7\u8bc6\u522b\u5206\u62e3_v1.0.2_\u79bb\u7ebf\u7248.zip"
    assert current_version_doc_name() == "\u7248\u672c\u8bf4\u660e_v1.0.2.txt"


def test_delivery_docs_are_current_and_include_startup_troubleshooting():
    delivery_dir = ROOT / "docs" / "delivery"
    names = {path.name for path in delivery_dir.iterdir() if path.is_file()}

    assert set(required_delivery_doc_names()) <= names
    assert "\u7248\u672c\u8bf4\u660e_v1.0.0.txt" not in names

    version_doc = delivery_dir / current_version_doc_name()
    text = version_doc.read_text(encoding="utf-8")
    assert text == version_notes_text()
    assert CURRENT_VERSION in text
    assert "\u901f\u5ea6\u6a21\u5f0f" in text
    assert "\u7591\u4f3c\u5019\u9009" in text

    troubleshooting = delivery_dir / "\u542f\u52a8\u5931\u8d25\u6392\u67e5.txt"
    troubleshooting_text = troubleshooting.read_text(encoding="utf-8")
    assert "Tesseract" in troubleshooting_text
    assert "Poppler" in troubleshooting_text
    assert "\u4e0d\u8981\u5355\u72ec\u79fb\u52a8 exe" in troubleshooting_text


def test_sample_regression_library_has_expected_buckets():
    sample_root = ROOT / "samples" / "input"
    expected_dirs = {
        "clear_pdf",
        "blurred_pdf",
        "variant_position_pdf",
        "invalid_check_digit",
        "no_container_code",
        "image_formats",
    }

    for name in expected_dirs:
        bucket = sample_root / name
        assert bucket.is_dir()
        assert (bucket / ".gitkeep").exists()

    readme = (ROOT / "samples" / "README.md").read_text(encoding="utf-8")
    for name in expected_dirs:
        assert name in readme
