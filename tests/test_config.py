from pathlib import Path

from waybill_ocr.config import default_config, resolve_runtime_base_dir


def test_default_config_discovers_tools_from_base_dir(tmp_path: Path):
    tesseract_cmd = tmp_path / "tools" / "tesseract" / "tesseract.exe"
    poppler_cmd = tmp_path / "tools" / "poppler" / "pdftoppm.exe"
    tesseract_cmd.parent.mkdir(parents=True)
    poppler_cmd.parent.mkdir(parents=True)
    tesseract_cmd.write_bytes(b"exe")
    poppler_cmd.write_bytes(b"exe")

    config = default_config(base_dir=tmp_path, env={})

    assert config.tesseract_cmd == tesseract_cmd
    assert config.poppler_path == poppler_cmd.parent


def test_default_config_uses_environment_overrides(tmp_path: Path):
    tesseract_cmd = tmp_path / "custom" / "tesseract.exe"
    poppler_dir = tmp_path / "custom" / "poppler"
    tesseract_cmd.parent.mkdir(parents=True)
    poppler_dir.mkdir(parents=True)
    tesseract_cmd.write_bytes(b"exe")

    config = default_config(
        base_dir=tmp_path,
        env={
            "WAYBILL_OCR_TESSERACT_CMD": str(tesseract_cmd),
            "WAYBILL_OCR_POPPLER_PATH": str(poppler_dir),
            "WAYBILL_OCR_RETRIES": "4",
        },
    )

    assert config.tesseract_cmd == tesseract_cmd
    assert config.poppler_path == poppler_dir
    assert config.ocr_retries == 4


def test_resolve_runtime_base_dir_prefers_pyinstaller_meipass(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("sys._MEIPASS", str(tmp_path), raising=False)

    assert resolve_runtime_base_dir() == tmp_path
