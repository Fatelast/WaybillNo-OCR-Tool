from pathlib import Path

from waybill_ocr.config import default_config, resolve_default_work_dir, resolve_runtime_base_dir


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

def test_resolve_default_work_dir_uses_local_app_data():
    work_dir = resolve_default_work_dir(env={"LOCALAPPDATA": "C:/Users/Test/AppData/Local"})

    assert work_dir == Path("C:/Users/Test/AppData/Local") / "OCRTool" / "work"


def test_resolve_default_work_dir_allows_environment_override(tmp_path: Path):
    custom_work_dir = tmp_path / "custom-work"

    work_dir = resolve_default_work_dir(env={"WAYBILL_OCR_WORK_DIR": str(custom_work_dir)})

    assert work_dir == custom_work_dir


def test_default_config_defaults_to_zero_ocr_retries(tmp_path: Path):
    config = default_config(base_dir=tmp_path, env={})

    assert config.ocr_retries == 0



def test_default_config_reads_valid_ocr_speed_mode(tmp_path: Path):
    config = default_config(base_dir=tmp_path, env={"WAYBILL_OCR_SPEED_MODE": "fast"})

    assert config.ocr_speed_mode == "fast"


def test_default_config_ignores_invalid_ocr_speed_mode(tmp_path: Path):
    config = default_config(base_dir=tmp_path, env={"WAYBILL_OCR_SPEED_MODE": "unknown"})

    assert config.ocr_speed_mode == "balanced"
