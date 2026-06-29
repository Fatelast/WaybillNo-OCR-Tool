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
        pages = _convert_pdf_pages(file_path, config)
        for index, page in enumerate(pages, start=1):
            image_path = Path(temp_dir) / f"page-{index}.png"
            page.save(image_path)
            yield image_path


def _convert_pdf_pages(file_path: Path, config: AppConfig):
    converter = _load_pdf_converter()
    return converter(
        pdf_path=str(file_path),
        dpi=300,
        poppler_path=str(config.poppler_path) if config.poppler_path else None,
        first_page=1,
    )


def _load_pdf_converter():
    global convert_from_path
    if convert_from_path is None:
        from pdf2image import convert_from_path as pdf2image_convert_from_path

        convert_from_path = pdf2image_convert_from_path

    return convert_from_path
