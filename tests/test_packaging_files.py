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
    assert '("tools/tesseract/tesseract.exe", "tools/tesseract")' in spec_text
    assert '("tools/tesseract/tessdata/eng.traineddata", "tools/tesseract/tessdata")' in spec_text
    assert '("tools/poppler/Library/bin/pdftoppm.exe", "tools/poppler/Library/bin")' in spec_text
    assert '("resources", "resources")' in spec_text
    assert 'APP_NAME = "运单箱号识别分拣"' in spec_text
    assert "name=APP_NAME" in spec_text
    assert "console=False" in spec_text

def test_tools_directory_documents_required_binaries():
    tools_readme = (ROOT / "tools" / "README.md").read_text(encoding="utf-8")

    assert "tools/tesseract/tesseract.exe" in tools_readme
    assert "tools/poppler" in tools_readme
    assert "pdftoppm.exe" in tools_readme

def test_cleanup_script_documents_safe_generated_targets():
    cleanup_script = ROOT / "scripts" / "cleanup_workspace.ps1"

    assert cleanup_script.exists()
    script_text = cleanup_script.read_text(encoding="utf-8")
    assert "[switch]$Apply" in script_text
    assert "[switch]$IncludeDist" in script_text
    assert ".tmp" in script_text
    assert "pytest-cache-files-*" in script_text
    assert "build" in script_text
    assert "__pycache__" in script_text
    assert "加 -Apply 执行删除" in script_text
