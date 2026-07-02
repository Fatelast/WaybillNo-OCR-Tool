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

    try:
        from PIL import Image

        with Image.open(image_path) as image:
            width, height = image.size
            if width < 20 or height < 20:
                return

            with temporary_directory(config) as temp_dir:
                for region_name, box in _grid_regions(width, height):
                    region_path = temp_dir / f"{region_name}.png"
                    image.crop(box).save(region_path)
                    yield OcrRegion(image_path=region_path, region_name=region_name)
    except Exception:
        return


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
