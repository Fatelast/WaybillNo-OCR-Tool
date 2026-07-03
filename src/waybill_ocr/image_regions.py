from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from waybill_ocr.config import AppConfig
from waybill_ocr.image_loader import temporary_directory


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
