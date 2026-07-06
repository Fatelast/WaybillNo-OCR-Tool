from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC_TEXT = (ROOT / "app.spec").read_text(encoding="utf-8")


def test_app_spec_does_not_bundle_entire_tools_directory():
    assert '("tools", "tools")' not in SPEC_TEXT


def test_app_spec_excludes_unused_heavy_dependencies():
    for module_name in ("cv2", "opencv", "opencv_python", "numpy", "pytest"):
        assert module_name in SPEC_TEXT



def test_app_spec_bundles_pdfinfo_and_pdftoppm_for_pdf2image():
    assert "tools/poppler/Library/bin/pdfinfo.exe" in SPEC_TEXT
    assert "tools/poppler/Library/bin/pdftoppm.exe" in SPEC_TEXT
