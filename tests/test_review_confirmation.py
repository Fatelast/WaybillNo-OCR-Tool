from pathlib import Path

from waybill_ocr.review_confirmation import (
    auto_confirm_expected_candidates,
    confirm_review_candidates,
    expected_review_candidates,
    scan_review_candidates,
)


VALID_CODE = "GESU5903360"


def _write_review_file(output_dir: Path, directory: str, name: str, content: bytes = b"pdf") -> Path:
    path = output_dir / directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_scan_review_candidates_only_reads_review_directories_and_marks_valid_code(tmp_path: Path):
    output_dir = tmp_path / "output"
    review_path = _write_review_file(output_dir, "未识别", f"{VALID_CODE}-待确认.pdf")
    _write_review_file(output_dir, "正确识别", f"{VALID_CODE}.pdf")
    (output_dir / "识别结果.xlsx").write_bytes(b"xlsx")
    _write_review_file(output_dir, "未识别", "原始文件名.pdf")

    candidates = scan_review_candidates(output_dir)

    assert len(candidates) == 1
    assert candidates[0].source_path == review_path
    assert candidates[0].review_code == VALID_CODE
    assert candidates[0].valid is False
    assert "已有同箱号" in (candidates[0].reason or "")


def test_confirm_review_candidates_moves_and_renames_selected_file(tmp_path: Path):
    output_dir = tmp_path / "output"
    source_path = _write_review_file(output_dir, "箱号错误", f"{VALID_CODE}-待确认.pdf", b"content")
    candidates = scan_review_candidates(output_dir)

    summary = confirm_review_candidates(output_dir, candidates)

    target_path = output_dir / "正确识别" / f"{VALID_CODE}.pdf"
    assert summary.moved_count == 1
    assert summary.skipped_count == 0
    assert not source_path.exists()
    assert target_path.read_bytes() == b"content"


def test_confirm_review_candidates_keeps_invalid_and_unselected_files(tmp_path: Path):
    output_dir = tmp_path / "output"
    source_path = _write_review_file(output_dir, "未识别", "GESU5903361-待确认.pdf")
    candidates = scan_review_candidates(output_dir)

    summary = confirm_review_candidates(output_dir, candidates)

    assert summary.moved_count == 0
    assert summary.conflict_count == 1
    assert source_path.exists()
    assert "校验不通过" in summary.failures[0] or candidates[0].reason == "箱号格式或 ISO 6346 校验不通过"


def test_confirm_review_candidates_does_not_overwrite_existing_target(tmp_path: Path):
    output_dir = tmp_path / "output"
    source_path = _write_review_file(output_dir, "未识别", f"{VALID_CODE}-待确认.pdf", b"review")
    target_path = _write_review_file(output_dir, "正确识别", f"{VALID_CODE}.pdf", b"existing")
    candidates = scan_review_candidates(output_dir)

    summary = confirm_review_candidates(output_dir, candidates)

    assert summary.moved_count == 0
    assert source_path.exists()
    assert target_path.read_bytes() == b"existing"


def test_duplicate_review_codes_are_not_moved_together(tmp_path: Path):
    output_dir = tmp_path / "output"
    first = _write_review_file(output_dir, "未识别", f"{VALID_CODE}-待确认.pdf")
    second = _write_review_file(output_dir, "箱号错误", f"{VALID_CODE}-待确认-1.pdf")
    candidates = scan_review_candidates(output_dir)

    summary = confirm_review_candidates(output_dir, candidates)

    assert summary.moved_count == 0
    assert summary.conflict_count == 2
    assert first.exists()
    assert second.exists()


def test_without_expected_codes_does_not_auto_confirm(tmp_path: Path):
    output_dir = tmp_path / "output"
    source_path = _write_review_file(output_dir, "未识别", f"{VALID_CODE}-待确认.pdf")

    summary = auto_confirm_expected_candidates(output_dir, [])

    assert summary.moved_count == 0
    assert source_path.exists()


def test_auto_confirm_expected_codes_moves_only_unique_expected_candidate(tmp_path: Path):
    output_dir = tmp_path / "output"
    source_path = _write_review_file(output_dir, "未识别", f"{VALID_CODE}-待确认.jpg")

    summary = auto_confirm_expected_candidates(output_dir, [VALID_CODE])

    assert summary.moved_count == 1
    assert not source_path.exists()
    assert (output_dir / "正确识别" / f"{VALID_CODE}.jpg").exists()


def test_auto_confirm_expected_codes_leaves_duplicate_expected_candidates(tmp_path: Path):
    output_dir = tmp_path / "output"
    first = _write_review_file(output_dir, "未识别", f"{VALID_CODE}-待确认.pdf")
    second = _write_review_file(output_dir, "箱号错误", f"{VALID_CODE}-待确认-1.pdf")

    summary = auto_confirm_expected_candidates(output_dir, [VALID_CODE])

    assert summary.moved_count == 0
    assert first.exists()
    assert second.exists()


def test_expected_review_candidates_uses_same_safe_filter_as_auto_confirm(tmp_path: Path):
    output_dir = tmp_path / "output"
    _write_review_file(output_dir, "未识别", f"{VALID_CODE}-待确认.pdf")
    _write_review_file(output_dir, "箱号错误", "GESU5903361-待确认.pdf")

    candidates = expected_review_candidates(output_dir, [VALID_CODE, "GESU5903361"])

    assert [candidate.review_code for candidate in candidates] == [VALID_CODE]
