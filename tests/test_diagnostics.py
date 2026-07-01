from pathlib import Path

from waybill_ocr.config import AppConfig
from waybill_ocr.diagnostics import inspect_environment


def test_inspect_environment_reports_ready_tools(tmp_path: Path):
    tesseract_cmd = tmp_path / "tools" / "tesseract" / "tesseract.exe"
    poppler_dir = tmp_path / "tools" / "poppler"
    tesseract_cmd.parent.mkdir(parents=True)
    poppler_dir.mkdir(parents=True)
    tesseract_cmd.write_bytes(b"exe")
    (poppler_dir / "pdftoppm.exe").write_bytes(b"exe")

    results = inspect_environment(
        AppConfig(tesseract_cmd=tesseract_cmd, poppler_path=poppler_dir),
        dependency_checker=lambda name: name in {"pytesseract", "pdf2image"},
    )

    assert [(result.name, result.ok) for result in results] == [
        ("pytesseract", True),
        ("pdf2image", True),
        ("Tesseract", True),
        ("Poppler", True),
    ]
    assert all(result.message.endswith("可用") for result in results)


def test_inspect_environment_reports_missing_dependencies_and_tools():
    results = inspect_environment(
        AppConfig(),
        dependency_checker=lambda _name: False,
    )

    assert [(result.name, result.ok) for result in results] == [
        ("pytesseract", False),
        ("pdf2image", False),
        ("Tesseract", False),
        ("Poppler", False),
    ]
    assert results[0].message == "缺少 pytesseract 依赖，请安装 requirements.txt。"
    assert results[1].message == "缺少 pdf2image 依赖，请安装 requirements.txt。"
    assert results[2].message == "未找到 Tesseract，请放置 tools/tesseract/tesseract.exe 或设置 WAYBILL_OCR_TESSERACT_CMD。"
    assert results[3].message == "未找到 Poppler，请放置 tools/poppler/pdftoppm.exe 或设置 WAYBILL_OCR_POPPLER_PATH。"