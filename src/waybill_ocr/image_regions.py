from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from waybill_ocr.config import AppConfig
from waybill_ocr.image_loader import _convert_pdf_page, temporary_directory


@dataclass(frozen=True)
class OcrRegion:
    image_path: Path
    region_name: str


def iter_ocr_regions(image_path: Path, config: AppConfig) -> Iterator[OcrRegion]:
    yield OcrRegion(image_path=image_path, region_name="full")
    yield from iter_grid_ocr_regions(image_path, config)


def iter_priority_ocr_regions(image_path: Path, config: AppConfig) -> Iterator[OcrRegion]:
    yield from _iter_cropped_regions(image_path, config, _priority_regions)


def iter_grid_ocr_regions(image_path: Path, config: AppConfig) -> Iterator[OcrRegion]:
    yield from _iter_cropped_regions(image_path, config, _grid_regions)



def iter_enhanced_ocr_regions(task, image_path: Path, config: AppConfig) -> Iterator[OcrRegion]:
    yield from _iter_enhanced_regions(task, image_path, config)


def _iter_enhanced_regions(task, image_path: Path, config: AppConfig) -> Iterator[OcrRegion]:
    try:
        from PIL import Image, ImageFilter, ImageOps

        with temporary_directory(config) as temp_dir:
            sources: list[tuple[str, Path]] = [("base", image_path)]
            if task.source_path.suffix.lower() == ".pdf":
                pages = _convert_pdf_page(task.source_path, config, _page_number_from_image_path(image_path), dpi=400)
                if pages:
                    high_dpi_path = temp_dir / "enhanced-400dpi-page.png"
                    pages[0].save(high_dpi_path)
                    sources.insert(0, ("400dpi", high_dpi_path))

            for source_name, source_path in sources:
                with Image.open(source_path) as image:
                    width, height = image.size
                    for region_name, box in _enhanced_regions(width, height):
                        crop = image.crop(box)
                        plain = ImageOps.autocontrast(crop.convert("L"))
                        plain_path = temp_dir / f"enhanced-{source_name}-{region_name}-plain.png"
                        plain.save(plain_path)
                        yield OcrRegion(image_path=plain_path, region_name=f"enhanced-{source_name}-{region_name}-plain")

                        scaled = plain.resize((plain.width * 2, plain.height * 2), Image.Resampling.LANCZOS)
                        sharpened = scaled.filter(ImageFilter.UnsharpMask(radius=1.4, percent=200, threshold=2))
                        sharpened_path = temp_dir / f"enhanced-{source_name}-{region_name}-x2sharp.png"
                        sharpened.save(sharpened_path)
                        yield OcrRegion(
                            image_path=sharpened_path,
                            region_name=f"enhanced-{source_name}-{region_name}-x2sharp",
                        )
    except Exception as exc:
        yield OcrRegion(image_path=image_path, region_name=f"\u533a\u57df\u88c1\u526a\u5931\u8d25: {exc}")


def _enhanced_regions(width: int, height: int) -> list[tuple[str, tuple[int, int, int, int]]]:
    return [
        ("full-middle", _box(width, height, 0.00, 0.36, 1.00, 0.68)),
        ("left-middle", _box(width, height, 0.00, 0.42, 0.58, 0.66)),
        ("left-lower-middle", _box(width, height, 0.00, 0.54, 0.64, 0.82)),
    ]


def _page_number_from_image_path(image_path: Path) -> int:
    stem = image_path.stem
    if stem.startswith("page-"):
        try:
            return max(1, int(stem.split("-", 1)[1]))
        except ValueError:
            return 1
    return 1

def _iter_cropped_regions(image_path: Path, config: AppConfig, region_builder) -> Iterator[OcrRegion]:
    try:
        from PIL import Image

        with Image.open(image_path) as image:
            width, height = image.size
            if width < 20 or height < 20:
                return

            with temporary_directory(config) as temp_dir:
                for region_name, box in region_builder(width, height):
                    region_path = temp_dir / f"{region_name}.png"
                    image.crop(box).save(region_path)
                    yield OcrRegion(image_path=region_path, region_name=region_name)
    except Exception as exc:
        yield OcrRegion(image_path=image_path, region_name=f"区域裁剪失败: {exc}")


def _priority_regions(width: int, height: int) -> list[tuple[str, tuple[int, int, int, int]]]:
    return [
        ("priority-left-middle", _box(width, height, 0.00, 0.42, 0.58, 0.66)),
        ("priority-left-upper", _box(width, height, 0.00, 0.08, 0.62, 0.34)),
        ("priority-full-middle", _box(width, height, 0.00, 0.36, 1.00, 0.68)),
        ("priority-left-lower-middle", _box(width, height, 0.00, 0.54, 0.64, 0.82)),
    ]


def _box(width: int, height: int, left: float, top: float, right: float, bottom: float) -> tuple[int, int, int, int]:
    return (
        max(0, int(width * left)),
        max(0, int(height * top)),
        min(width, int(width * right)),
        min(height, int(height * bottom)),
    )


def _grid_regions(width: int, height: int) -> list[tuple[str, tuple[int, int, int, int]]]:
    cols = 3
    rows = 8
    overlap_x = int(width * 0.04)
    overlap_y = int(height * 0.04)
    regions = []
    for row in range(rows):
        for col in range(cols):
            left = max(0, int(col * width / cols) - overlap_x)
            right = min(width, int((col + 1) * width / cols) + overlap_x)
            top = max(0, int(row * height / rows) - overlap_y)
            bottom = min(height, int((row + 1) * height / rows) + overlap_y)
            if right - left >= 20 and bottom - top >= 20:
                regions.append((f"cell-r{row + 1}-c{col + 1}", (left, top, right, bottom)))
    return regions
