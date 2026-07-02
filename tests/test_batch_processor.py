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
        cancel_event=None,
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
    assert (output_dir / "正确识别" / "HNKU6331795.jpg").read_bytes() == b"fake"
    workbook = load_workbook(output_dir / "识别结果.xlsx")
    assert workbook.active["B2"].value == "HNKU6331795"
    assert progress_messages == [
        "扫描到 1 个文件",
        "处理中: 1/1 waybill.jpg",
        "结果: waybill.jpg -> 正确识别 (HNKU6331795)",
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

    def fake_process_file(
        task: FileTask,
        _config: AppConfig,
        _ocr_engine: FakeOcrEngine,
        cancel_event=None,
    ) -> RecognitionResult:
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


def test_process_directory_cleans_configured_work_dir(tmp_path: Path, monkeypatch):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    work_dir = tmp_path / "work"
    input_dir.mkdir()
    source_path = input_dir / "waybill.jpg"
    source_path.write_bytes(b"fake")

    def fake_process_file(
        task: FileTask,
        config: AppConfig,
        _ocr_engine: FakeOcrEngine,
        cancel_event=None,
    ) -> RecognitionResult:
        assert config.work_dir == work_dir
        config.work_dir.mkdir(parents=True, exist_ok=True)
        (config.work_dir / "temp.txt").write_text("temp", encoding="utf-8")
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
        config=AppConfig(work_dir=work_dir),
        ocr_engine=FakeOcrEngine(),
    )

    assert not work_dir.exists()

def test_process_directory_writes_workbook_incrementally_when_later_copy_fails(tmp_path: Path, monkeypatch):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    first_path = input_dir / "first.jpg"
    second_path = input_dir / "second.jpg"
    first_path.write_bytes(b"first")
    second_path.write_bytes(b"second")

    def fake_process_file(
        task: FileTask,
        _config: AppConfig,
        _ocr_engine: FakeOcrEngine,
        cancel_event=None,
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

    def fake_copy_result_file(result: RecognitionResult, _output_dir: Path) -> Path:
        if result.original_name == "second.jpg":
            raise RuntimeError("copy failed")
        return output_dir / "正确识别" / "HNKU6331795.jpg"

    monkeypatch.setattr(batch_module, "process_file", fake_process_file)
    monkeypatch.setattr(batch_module, "copy_result_file", fake_copy_result_file)

    try:
        batch_module.process_directory(
            input_dir=input_dir,
            output_dir=output_dir,
            config=AppConfig(),
            ocr_engine=FakeOcrEngine(),
        )
    except RuntimeError:
        pass

    workbook = load_workbook(output_dir / "识别结果.xlsx")
    assert workbook.active["A2"].value == "first.jpg"
    assert workbook.active["B2"].value == "HNKU6331795"


def test_process_directory_stops_between_files_when_cancelled(tmp_path: Path, monkeypatch):
    import threading

    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    first_path = input_dir / "first.jpg"
    second_path = input_dir / "second.jpg"
    first_path.write_bytes(b"first")
    second_path.write_bytes(b"second")
    cancel_event = threading.Event()
    processed = []
    progress_messages = []

    def fake_process_file(task: FileTask, _config: AppConfig, _ocr_engine: FakeOcrEngine, cancel_event=None) -> RecognitionResult:
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

    def fake_copy_result_file(result: RecognitionResult, _output_dir: Path) -> Path:
        cancel_event.set()
        return _output_dir / "正确识别" / result.original_name

    monkeypatch.setattr(batch_module, "process_file", fake_process_file)
    monkeypatch.setattr(batch_module, "copy_result_file", fake_copy_result_file)

    results = batch_module.process_directory(
        input_dir=input_dir,
        output_dir=output_dir,
        config=AppConfig(),
        ocr_engine=FakeOcrEngine(),
        on_progress=progress_messages.append,
        cancel_event=cancel_event,
    )

    assert [result.original_name for result in results] == ["first.jpg"]
    assert processed == ["first.jpg"]
    assert any(message == "已取消：已处理 1/2" for message in progress_messages)



def test_process_directory_writes_backup_workbook_when_default_workbook_is_locked(tmp_path: Path, monkeypatch):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    source_path = input_dir / "waybill.jpg"
    source_path.write_bytes(b"fake")
    progress_messages = []
    workbook_paths = []

    def fake_process_file(
        task: FileTask,
        _config: AppConfig,
        _ocr_engine: FakeOcrEngine,
        cancel_event=None,
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

    def fake_write_results(results, output_dir: Path, workbook_path: Path | None = None) -> Path:
        workbook_paths.append(workbook_path)
        if workbook_path is None:
            raise PermissionError("workbook is open")
        assert workbook_path.parent == output_dir
        assert workbook_path.name.startswith("识别结果-备份-")
        assert workbook_path.suffix == ".xlsx"
        return workbook_path

    monkeypatch.setattr(batch_module, "process_file", fake_process_file)
    monkeypatch.setattr(batch_module, "write_results", fake_write_results)

    results = batch_module.process_directory(
        input_dir=input_dir,
        output_dir=output_dir,
        config=AppConfig(),
        ocr_engine=FakeOcrEngine(),
        on_progress=progress_messages.append,
    )

    assert [result.original_name for result in results] == ["waybill.jpg"]
    assert workbook_paths[0] is None
    assert workbook_paths[1] is not None
    assert any("识别结果.xlsx 被占用" in message for message in progress_messages)
