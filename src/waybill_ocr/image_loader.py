from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator

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

    with TemporaryDirectory() as temp_dir:
        page_number = 1
        while True:
            pages = _convert_pdf_page(file_path, config, page_number)
            if not pages:
                break

            page = pages[0]
            image_path = Path(temp_dir) / f"page-{page_number}.png"
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
            from pdf2image import convert_from_path as pdf2image_convert_from_path
        except ModuleNotFoundError as exc:
            raise RuntimeError("缺少 pdf2image 依赖，请先安装 requirements.txt 中的 PDF 转图依赖。") from exc

        convert_from_path = pdf2image_convert_from_path

    return convert_from_path
