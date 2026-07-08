from pathlib import Path


def test_source_files_do_not_contain_replacement_characters():
    source_root = Path(__file__).resolve().parents[1] / "src" / "waybill_ocr"
    offenders = []
    for path in source_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "\ufffd" in text:
            offenders.append(str(path.relative_to(source_root)))

    assert offenders == []
