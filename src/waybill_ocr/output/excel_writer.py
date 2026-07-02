from pathlib import Path

from openpyxl import Workbook

from waybill_ocr.constants import RESULT_WORKBOOK_NAME
from waybill_ocr.models import RecognitionResult


HEADERS = ["原始文件名", "识别箱号", "识别状态", "识别来源", "失败原因", "处理耗时ms"]


def write_results(results: list[RecognitionResult], output_dir: Path, workbook_path: Path | None = None) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "识别结果"
    sheet.append(HEADERS)

    for result in results:
        sheet.append(
            [
                result.original_name,
                result.container_code or "",
                result.status.value,
                result.source.value if result.source else "",
                result.failure_reason or "",
                result.elapsed_ms,
            ]
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = workbook_path or output_dir / RESULT_WORKBOOK_NAME
    workbook.save(target_path)
    return target_path
