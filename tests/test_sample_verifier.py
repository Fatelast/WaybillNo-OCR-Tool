from pathlib import Path

import waybill_ocr.sample_verifier as verifier_module
from waybill_ocr.models import RecognitionResult, RecognitionSource, RecognitionStatus
from waybill_ocr.sample_verifier import resolve_default_baseline_path, verify_samples


class FakeOcrEngine:
    pass


def _result(
    filename: str,
    status: RecognitionStatus,
    container_code: str | None,
    failure_reason: str | None = None,
    review_code: str | None = None,
    relative_name: str | None = None,
) -> RecognitionResult:
    return RecognitionResult(
        source_path=Path(filename),
        original_name=Path(filename).name,
        status=status,
        container_code=container_code,
        source=RecognitionSource.OCR if container_code else None,
        failure_reason=failure_reason,
        ocr_text=container_code or "",
        elapsed_ms=1,
        review_code=review_code,
        relative_name=relative_name,
    )


def test_default_sample_baseline_prefers_local_private_baseline(tmp_path: Path):
    expected_dir = tmp_path / "expected"
    expected_dir.mkdir()
    tracked = expected_dir / "baseline.csv"
    local = expected_dir / "baseline.local.csv"
    tracked.write_text("tracked", encoding="utf-8")
    local.write_text("local", encoding="utf-8")

    assert resolve_default_baseline_path(expected_dir) == local


def test_default_sample_baseline_falls_back_to_tracked_baseline(tmp_path: Path):
    expected_dir = tmp_path / "expected"
    expected_dir.mkdir()
    tracked = expected_dir / "baseline.csv"
    tracked.write_text("tracked", encoding="utf-8")

    assert resolve_default_baseline_path(expected_dir) == tracked

def test_verify_samples_passes_when_results_match_baseline(tmp_path: Path, monkeypatch):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "actual"
    baseline_path = tmp_path / "baseline.csv"
    input_dir.mkdir()
    baseline_path.write_text(
        "filename,expected_code,should_recognize,quality_tag,notes\n"
        "waybill.png,HNKU6331795,true,clear,fixture\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        verifier_module,
        "process_directory",
        lambda **_kwargs: [_result("waybill.png", RecognitionStatus.SUCCESS, "HNKU6331795")],
    )

    report = verify_samples(
        input_dir=input_dir,
        output_dir=output_dir,
        baseline_path=baseline_path,
        config=object(),
        ocr_engine=FakeOcrEngine(),
    )

    assert report.ok is True
    assert report.messages == ["样本验收通过: 1/1"]


def test_verify_samples_reports_code_mismatch(tmp_path: Path, monkeypatch):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "actual"
    baseline_path = tmp_path / "baseline.csv"
    input_dir.mkdir()
    baseline_path.write_text(
        "filename,expected_code,should_recognize,quality_tag,notes\n"
        "waybill.png,HNKU6331795,true,clear,fixture\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        verifier_module,
        "process_directory",
        lambda **_kwargs: [_result("waybill.png", RecognitionStatus.SUCCESS, "MSCU1234566")],
    )

    report = verify_samples(
        input_dir=input_dir,
        output_dir=output_dir,
        baseline_path=baseline_path,
        config=object(),
        ocr_engine=FakeOcrEngine(),
    )

    assert report.ok is False
    assert report.messages == [
        "样本验收失败: 0/1",
        "waybill.png: 期望识别 HNKU6331795，实际为 MSCU1234566",
    ]


def test_verify_samples_reports_missing_result(tmp_path: Path, monkeypatch):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "actual"
    baseline_path = tmp_path / "baseline.csv"
    input_dir.mkdir()
    baseline_path.write_text(
        "filename,expected_code,should_recognize,quality_tag,notes\n"
        "missing.png,HNKU6331795,true,clear,fixture\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(verifier_module, "process_directory", lambda **_kwargs: [])

    report = verify_samples(
        input_dir=input_dir,
        output_dir=output_dir,
        baseline_path=baseline_path,
        config=object(),
        ocr_engine=FakeOcrEngine(),
    )

    assert report.ok is False
    assert report.messages == [
        "样本验收失败: 0/1",
        "missing.png: 未在处理结果中找到该样本",
    ]


def test_verify_samples_accepts_expected_unrecognized_sample(tmp_path: Path, monkeypatch):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "actual"
    baseline_path = tmp_path / "baseline.csv"
    input_dir.mkdir()
    baseline_path.write_text(
        "filename,expected_code,should_recognize,quality_tag,notes\n"
        "blurred.png,,false,blurred,fixture\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        verifier_module,
        "process_directory",
        lambda **_kwargs: [
            _result(
                "blurred.png",
                RecognitionStatus.UNRECOGNIZED,
                None,
                "NO_CONTAINER_CANDIDATE",
            )
        ],
    )

    report = verify_samples(
        input_dir=input_dir,
        output_dir=output_dir,
        baseline_path=baseline_path,
        config=object(),
        ocr_engine=FakeOcrEngine(),
    )

    assert report.ok is True
    assert report.messages == ["样本验收通过: 1/1"]




def test_verify_samples_new_baseline_accepts_allowed_review_code(tmp_path: Path, monkeypatch):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "actual"
    baseline_path = tmp_path / "baseline.csv"
    input_dir.mkdir()
    baseline_path.write_text(
        "filename,expected_code,expected_status,allow_review_code,quality_tag,notes\n"
        "blurred.png,GESU5903360,未识别,true,blurred,fixture\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        verifier_module,
        "process_directory",
        lambda **_kwargs: [
            _result(
                "blurred.png",
                RecognitionStatus.UNRECOGNIZED,
                None,
                "NO_CONTAINER_CANDIDATE",
                review_code="GESU5903360",
            )
        ],
    )

    report = verify_samples(
        input_dir=input_dir,
        output_dir=output_dir,
        baseline_path=baseline_path,
        config=object(),
        ocr_engine=FakeOcrEngine(),
    )

    assert report.ok is True
    assert report.messages == ["\u6837\u672c\u9a8c\u6536\u901a\u8fc7: 1/1", "\u5206\u7c7b\u7edf\u8ba1:", "- blurred: 1/1"]


def test_verify_samples_new_baseline_rejects_unallowed_review_code(tmp_path: Path, monkeypatch):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "actual"
    baseline_path = tmp_path / "baseline.csv"
    input_dir.mkdir()
    baseline_path.write_text(
        "filename,expected_code,expected_status,allow_review_code,quality_tag,notes\n"
        "blurred.png,GESU5903360,未识别,false,blurred,fixture\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        verifier_module,
        "process_directory",
        lambda **_kwargs: [
            _result(
                "blurred.png",
                RecognitionStatus.UNRECOGNIZED,
                None,
                "NO_CONTAINER_CANDIDATE",
                review_code="GESU5903360",
            )
        ],
    )

    report = verify_samples(
        input_dir=input_dir,
        output_dir=output_dir,
        baseline_path=baseline_path,
        config=object(),
        ocr_engine=FakeOcrEngine(),
    )

    assert report.ok is False
    assert "\u4e0d\u5141\u8bb8\u5f85\u786e\u8ba4\u5019\u9009" in report.messages[-1]


def test_verify_samples_matches_by_relative_name_for_categorized_samples(tmp_path: Path, monkeypatch):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "actual"
    baseline_path = tmp_path / "baseline.csv"
    input_dir.mkdir()
    baseline_path.write_text(
        "filename,expected_code,expected_status,allow_review_code,quality_tag,notes\n"
        "clear/waybill.pdf,HNKU6331795,\u6b63\u786e\u8bc6\u522b,false,clear,fixture\n"
        "blurred/waybill.pdf,GESU5903360,\u672a\u8bc6\u522b,true,blurred,fixture\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        verifier_module,
        "process_directory",
        lambda **_kwargs: [
            _result("waybill.pdf", RecognitionStatus.SUCCESS, "HNKU6331795", relative_name="clear/waybill.pdf"),
            _result(
                "waybill.pdf",
                RecognitionStatus.UNRECOGNIZED,
                None,
                "NO_CONTAINER_CANDIDATE",
                review_code="GESU5903360",
                relative_name="blurred/waybill.pdf",
            ),
        ],
    )

    report = verify_samples(
        input_dir=input_dir,
        output_dir=output_dir,
        baseline_path=baseline_path,
        config=object(),
        ocr_engine=FakeOcrEngine(),
    )

    assert report.ok is True
    assert report.messages == [
        "\u6837\u672c\u9a8c\u6536\u901a\u8fc7: 2/2",
        "\u5206\u7c7b\u7edf\u8ba1:",
        "- blurred: 1/1",
        "- clear: 1/1",
    ]


def test_verify_samples_category_summary_counts_failures(tmp_path: Path, monkeypatch):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "actual"
    baseline_path = tmp_path / "baseline.csv"
    input_dir.mkdir()
    baseline_path.write_text(
        "filename,expected_code,expected_status,allow_review_code,quality_tag,notes\n"
        "clear/ok.pdf,HNKU6331795,\u6b63\u786e\u8bc6\u522b,false,clear,fixture\n"
        "blurred/fail.pdf,GESU5903360,\u6b63\u786e\u8bc6\u522b,false,blurred,fixture\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        verifier_module,
        "process_directory",
        lambda **_kwargs: [
            _result("ok.pdf", RecognitionStatus.SUCCESS, "HNKU6331795", relative_name="clear/ok.pdf"),
            _result("fail.pdf", RecognitionStatus.UNRECOGNIZED, None, relative_name="blurred/fail.pdf"),
        ],
    )

    report = verify_samples(
        input_dir=input_dir,
        output_dir=output_dir,
        baseline_path=baseline_path,
        config=object(),
        ocr_engine=FakeOcrEngine(),
    )

    assert report.ok is False
    assert report.messages[:4] == [
        "\u6837\u672c\u9a8c\u6536\u5931\u8d25: 1/2",
        "\u5206\u7c7b\u7edf\u8ba1:",
        "- blurred: 0/1",
        "- clear: 1/1",
    ]
    assert "blurred/fail.pdf: \u671f\u671b\u72b6\u6001 \u6b63\u786e\u8bc6\u522b\uff0c\u5b9e\u9645\u72b6\u6001\u4e3a \u672a\u8bc6\u522b" in report.messages
