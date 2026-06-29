from pathlib import Path

from waybill_ocr.file_scanner import scan_input_files


def test_scan_supported_files_only(tmp_path: Path):
    (tmp_path / "a.jpg").write_bytes(b"fake")
    (tmp_path / "b.pdf").write_bytes(b"fake")
    (tmp_path / "c.txt").write_text("ignore", encoding="utf-8")

    tasks = scan_input_files(tmp_path)

    assert [task.relative_name for task in tasks] == ["a.jpg", "b.pdf"]
