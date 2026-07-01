from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_packaging_files_exist_and_reference_bundled_resources():
    app_spec = ROOT / "app.spec"
    operation_doc = ROOT / "docs" / "操作说明.md"
    version_doc = ROOT / "docs" / "版本说明.md"

    assert app_spec.exists()
    assert operation_doc.exists()
    assert version_doc.exists()

    spec_text = app_spec.read_text(encoding="utf-8")
    assert "src/waybill_ocr/__main__.py" in spec_text
    assert '("tools", "tools")' in spec_text
    assert '("resources", "resources")' in spec_text
    assert 'name="运单箱号识别分拣"' in spec_text
    assert "console=False" in spec_text