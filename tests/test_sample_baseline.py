import csv
from pathlib import Path

import pytest
import waybill_ocr.sample_baseline as baseline_module

from waybill_ocr.models import RecognitionResult, RecognitionSource, RecognitionStatus
from waybill_ocr.sample_baseline import (
    DRAFT_HEADERS,
    import_sample_baseline,
    write_baseline_draft,
)


def _result(
    path: Path,
    status: RecognitionStatus,
    *,
    code: str | None = None,
    review_code: str | None = None,
    relative_name: str | None = None,
) -> RecognitionResult:
    return RecognitionResult(
        source_path=path,
        original_name=path.name,
        status=status,
        container_code=code,
        source=RecognitionSource.OCR if code else None,
        failure_reason=None,
        ocr_text=code or review_code or "",
        elapsed_ms=1,
        relative_name=relative_name or path.name,
        review_code=review_code,
    )


def test_write_baseline_draft_suggests_only_unique_expected_matches(tmp_path: Path):
    input_dir = tmp_path / "cases"
    clear_dir = input_dir / "clear"
    blurred_dir = input_dir / "blurred"
    clear_dir.mkdir(parents=True)
    blurred_dir.mkdir()
    clear_path = clear_dir / "clear.pdf"
    blurred_path = blurred_dir / "blurred.pdf"
    unmatched_path = blurred_dir / "unmatched.pdf"
    for path in (clear_path, blurred_path, unmatched_path):
        path.write_bytes(b"pdf")

    draft_path = tmp_path / "baseline.draft.csv"
    results = [
        _result(
            clear_path,
            RecognitionStatus.SUCCESS,
            code="HNKU6331795",
            relative_name="clear/clear.pdf",
        ),
        _result(
            blurred_path,
            RecognitionStatus.UNRECOGNIZED,
            review_code="GESU5903360",
            relative_name="blurred/blurred.pdf",
        ),
        _result(
            unmatched_path,
            RecognitionStatus.UNRECOGNIZED,
            relative_name="blurred/unmatched.pdf",
        ),
    ]

    report = write_baseline_draft(
        input_dir,
        ["HNKU6331795", "GESU5903360"],
        results,
        draft_path,
    )

    with draft_path.open("r", encoding="utf-8-sig", newline="") as file_obj:
        rows = {row["filename"]: row for row in csv.DictReader(file_obj)}

    assert report.total == 3
    assert report.suggested == 2
    assert rows["clear/clear.pdf"]["expected_code"] == "HNKU6331795"
    assert rows["clear/clear.pdf"]["expected_status"] == RecognitionStatus.SUCCESS.value
    assert rows["clear/clear.pdf"]["confirmed"] == "false"
    assert rows["blurred/blurred.pdf"]["expected_code"] == "GESU5903360"
    assert rows["blurred/blurred.pdf"]["allow_review_code"] == "true"
    assert rows["blurred/unmatched.pdf"]["expected_code"] == ""


def test_write_baseline_draft_does_not_suggest_duplicate_observed_code(tmp_path: Path):
    input_dir = tmp_path / "cases"
    input_dir.mkdir()
    paths = [input_dir / "first.pdf", input_dir / "second.pdf"]
    for path in paths:
        path.write_bytes(b"pdf")

    results = [
        _result(path, RecognitionStatus.SUCCESS, code="HNKU6331795")
        for path in paths
    ]
    draft_path = tmp_path / "draft.csv"

    report = write_baseline_draft(input_dir, ["HNKU6331795"], results, draft_path)

    with draft_path.open("r", encoding="utf-8-sig", newline="") as file_obj:
        rows = list(csv.DictReader(file_obj))
    assert report.suggested == 0
    assert all(row["expected_code"] == "" for row in rows)
    assert all("\u591a\u4e2a\u6837\u672c" in row["match_basis"] for row in rows)


def test_import_sample_baseline_merges_confirmed_rows_only(tmp_path: Path):
    input_dir = tmp_path / "cases"
    input_dir.mkdir()
    confirmed_path = input_dir / "confirmed.pdf"
    skipped_path = input_dir / "skipped.pdf"
    confirmed_path.write_bytes(b"pdf")
    skipped_path.write_bytes(b"pdf")
    draft_path = tmp_path / "draft.csv"
    baseline_path = tmp_path / "baseline.local.csv"

    rows = [
        {
            "filename": "confirmed.pdf",
            "expected_code": "GESU5903360",
            "expected_status": RecognitionStatus.INVALID.value,
            "allow_review_code": "true",
            "quality_tag": "blurred",
            "notes": "\u4eba\u5de5\u786e\u8ba4",
            "confirmed": "true",
        },
        {
            "filename": "skipped.pdf",
            "expected_code": "HNKU6331795",
            "expected_status": RecognitionStatus.SUCCESS.value,
            "allow_review_code": "false",
            "quality_tag": "clear",
            "notes": "",
            "confirmed": "false",
        },
    ]
    with draft_path.open("w", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=DRAFT_HEADERS)
        writer.writeheader()
        writer.writerows(rows)
    baseline_path.write_text(
        "filename,expected_code,expected_status,allow_review_code,quality_tag,notes\n"
        "existing.pdf,HNKU6331795,\u6b63\u786e\u8bc6\u522b,false,clear,existing\n",
        encoding="utf-8",
    )

    report = import_sample_baseline(input_dir, draft_path, baseline_path)

    with baseline_path.open("r", encoding="utf-8-sig", newline="") as file_obj:
        imported = {row["filename"]: row for row in csv.DictReader(file_obj)}
    assert report.imported == 1
    assert report.total == 2
    assert set(imported) == {"confirmed.pdf", "existing.pdf"}
    assert imported["confirmed.pdf"]["allow_review_code"] == "true"


def test_import_sample_baseline_rejects_confirmed_missing_sample(tmp_path: Path):
    input_dir = tmp_path / "cases"
    input_dir.mkdir()
    draft_path = tmp_path / "draft.csv"
    with draft_path.open("w", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=DRAFT_HEADERS)
        writer.writeheader()
        writer.writerow(
            {
                "filename": "missing.pdf",
                "expected_code": "HNKU6331795",
                "expected_status": RecognitionStatus.SUCCESS.value,
                "allow_review_code": "false",
                "confirmed": "true",
            }
        )

    with pytest.raises(ValueError, match="\u6837\u672c\u6587\u4ef6\u4e0d\u5b58\u5728"):
        import_sample_baseline(input_dir, draft_path, tmp_path / "baseline.csv")


def test_prepare_sample_baseline_disables_success_result_reuse(tmp_path: Path, monkeypatch):
    input_dir = tmp_path / "cases"
    actual_dir = tmp_path / "actual"
    expected_path = tmp_path / "expected.txt"
    draft_path = tmp_path / "baseline.draft.csv"
    input_dir.mkdir()
    source_path = input_dir / "sample.pdf"
    source_path.write_bytes(b"pdf")
    expected_path.write_text("HNKU6331795\n", encoding="utf-8")
    calls: list[dict] = []
    results = [
        _result(
            source_path,
            RecognitionStatus.SUCCESS,
            code="HNKU6331795",
        )
    ]

    monkeypatch.setattr(
        baseline_module,
        "process_directory",
        lambda **kwargs: calls.append(kwargs) or results,
    )

    baseline_module.prepare_sample_baseline(
        input_dir=input_dir,
        expected_path=expected_path,
        actual_dir=actual_dir,
        draft_path=draft_path,
        config=object(),
        ocr_engine=object(),
    )

    assert calls[0]["skip_existing_successes"] is False
