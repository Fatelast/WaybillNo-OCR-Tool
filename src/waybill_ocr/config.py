import os
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    tesseract_cmd: Path | None = None
    poppler_path: Path | None = None
    ocr_retries: int = 2
    work_dir: Path | None = None


def default_config(
    base_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
    work_dir: Path | None = None,
) -> AppConfig:
    runtime_base = base_dir or resolve_runtime_base_dir()
    current_env = env if env is not None else os.environ

    return AppConfig(
        tesseract_cmd=_resolve_tesseract_cmd(runtime_base, current_env),
        poppler_path=_resolve_poppler_path(runtime_base, current_env),
        ocr_retries=_resolve_ocr_retries(current_env),
        work_dir=work_dir,
    )


def resolve_runtime_base_dir() -> Path:
    pyinstaller_base = getattr(sys, "_MEIPASS", None)
    if pyinstaller_base:
        return Path(pyinstaller_base)

    return Path(__file__).resolve().parents[2]


def _resolve_tesseract_cmd(base_dir: Path, env: Mapping[str, str]) -> Path | None:
    override = env.get("WAYBILL_OCR_TESSERACT_CMD")
    if override:
        return Path(override)

    bundled_cmd = base_dir / "tools" / "tesseract" / "tesseract.exe"
    if bundled_cmd.exists():
        return bundled_cmd

    return None


def _resolve_poppler_path(base_dir: Path, env: Mapping[str, str]) -> Path | None:
    override = env.get("WAYBILL_OCR_POPPLER_PATH")
    if override:
        return Path(override)

    for candidate in (
        base_dir / "tools" / "poppler",
        base_dir / "tools" / "poppler" / "bin",
        base_dir / "tools" / "poppler" / "Library" / "bin",
    ):
        if (candidate / "pdftoppm.exe").exists():
            return candidate

    return None


def _resolve_ocr_retries(env: Mapping[str, str]) -> int:
    raw_value = env.get("WAYBILL_OCR_RETRIES")
    if raw_value is None:
        return 0

    try:
        retries = int(raw_value)
    except ValueError:
        return 2

    return max(0, retries)

def resolve_default_work_dir(env: Mapping[str, str] | None = None) -> Path:
    current_env = env if env is not None else os.environ
    override = current_env.get("WAYBILL_OCR_WORK_DIR")
    if override:
        return Path(override)

    local_app_data = current_env.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "OCRTool" / "work"

    return Path(tempfile.gettempdir()) / "OCRTool" / "work"
