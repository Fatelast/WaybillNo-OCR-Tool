import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from waybill_ocr.config import AppConfig


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
convert_from_path = None


def iter_images_for_ocr(file_path: Path, config: AppConfig) -> Iterator[Path]:
    suffix = file_path.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        yield file_path
        return

    if suffix != ".pdf":
        return

    with temporary_directory(config) as temp_dir:
        page_number = 1
        while True:
            pages = _convert_pdf_page(file_path, config, page_number)
            if not pages:
                break

            page = pages[0]
            image_path = temp_dir / f"page-{page_number}.png"
            page.save(image_path)
            yield image_path
            page_number += 1


def _convert_pdf_page(file_path: Path, config: AppConfig, page_number: int):
    converter = _load_pdf_converter()
    return converter(
        pdf_path=str(file_path),
        dpi=300,
        poppler_path=str(config.poppler_path) if config.poppler_path else None,
        first_page=page_number,
        last_page=page_number,
    )


def _load_pdf_converter():
    global convert_from_path
    if convert_from_path is None:
        try:
            import pdf2image.pdf2image as pdf2image_module
            from pdf2image import convert_from_path as pdf2image_convert_from_path
        except ModuleNotFoundError as exc:
            raise RuntimeError("缺少 pdf2image 依赖，请先安装 requirements.txt 中的 PDF 转图依赖。") from exc

        _hide_pdf2image_poppler_windows(pdf2image_module)
        convert_from_path = pdf2image_convert_from_path

    return convert_from_path


@contextmanager
def temporary_directory(config: AppConfig) -> Iterator[Path]:
    parent_dir = config.work_dir or Path.cwd() / ".tmp" / "ocr-work"
    parent_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = parent_dir / f"work-{uuid4().hex}"
    temp_dir.mkdir(parents=True, exist_ok=False)
    try:
        yield temp_dir
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def _hide_pdf2image_poppler_windows(pdf2image_module) -> None:
    if not hasattr(subprocess, "STARTUPINFO"):
        return
    if getattr(pdf2image_module, "_waybill_ocr_hidden_popen", False):
        return

    original_popen = pdf2image_module.Popen

    def hidden_popen(*args, **kwargs):
        if "startupinfo" not in kwargs or kwargs["startupinfo"] is None:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            kwargs["startupinfo"] = startupinfo
        return original_popen(*args, **kwargs)

    pdf2image_module.Popen = hidden_popen
    pdf2image_module._waybill_ocr_hidden_popen = True
