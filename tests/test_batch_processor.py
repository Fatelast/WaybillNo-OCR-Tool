from pathlib import Path

from openpyxl import load_workbook

import waybill_ocr.batch_processor as batch_module
from waybill_ocr.config import AppConfig
from waybill_ocr.models import FileTask, RecognitionResult, RecognitionSource, RecognitionStatus


class FakeOcrEngine:
    pass


def test_process_directory_classifies_files_and_writes_workbook(tmp_path: Path, monkeypatch):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    source_path = input_dir / "waybill.jpg"
    source_path.write_bytes(b"fake")
    progress_messages = []

    def fake_process_file(
        task: FileTask,
        _config: AppConfig,
        _ocr_engine: FakeOcrEngine,
    ) -> RecognitionResult:
        return RecognitionResult(
            source_path=task.source_path,
            original_name=task.source_path.name,
            status=RecognitionStatus.SUCCESS,
            container_code="HNKU6331795",
            source=RecognitionSource.OCR,
            failure_reason=None,
            ocr_text="HNKU6331795",
            elapsed_ms=1,
        )

    monkeypatch.setattr(batch_module, "process_file", fake_process_file)

    results = batch_module.process_directory(
        input_dir=input_dir,
        output_dir=output_dir,
        config=AppConfig(),
        ocr_engine=FakeOcrEngine(),
        on_progress=progress_messages.append,
    )

    assert [result.container_code for result in results] == ["HNKU6331795"]
    assert (output_dir / "正确识别" / "waybill.jpg").read_bytes() == b"fake"
    workbook = load_workbook(output_dir / "识别结果.xlsx")
    assert workbook.active["B2"].value == "HNKU6331795"
    assert progress_messages == [
        "扫描到 1 个文件",
        "处理中: 1/1 waybill.jpg",
        "处理完成",
    ]

def test_process_directory_excludes_output_directory_inside_input(tmp_path: Path, monkeypatch):
    input_dir = tmp_path / "input"
    output_dir = input_dir / "output"
    output_success = output_dir / "正确识别"
    output_success.mkdir(parents=True)
    source_path = input_dir / "waybill.jpg"
    stale_output = output_success / "old.jpg"
    source_path.write_bytes(b"source")
    stale_output.write_bytes(b"old")
    processed = []

    def fake_process_file(task: FileTask, _config: AppConfig, _ocr_engine: FakeOcrEngine) -> RecognitionResult:
        processed.append(task.relative_name)
        return RecognitionResult(
            source_path=task.source_path,
            original_name=task.source_path.name,
            status=RecognitionStatus.SUCCESS,
            container_code="HNKU6331795",
            source=RecognitionSource.OCR,
            failure_reason=None,
            ocr_text="HNKU6331795",
            elapsed_ms=1,
        )

    monkeypatch.setattr(batch_module, "process_file", fake_process_file)

    batch_module.process_directory(
        input_dir=input_dir,
        output_dir=output_dir,
        config=AppConfig(),
        ocr_engine=FakeOcrEngine(),
    )

    assert processed == ["waybill.jpg"]
