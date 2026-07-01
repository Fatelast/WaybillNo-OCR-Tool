from pathlib import Path

import waybill_ocr.sample_verifier as verifier_module
from waybill_ocr.models import RecognitionResult, RecognitionSource, RecognitionStatus
from waybill_ocr.sample_verifier import verify_samples


class FakeOcrEngine:
    pass


def _result(
    filename: str,
    status: RecognitionStatus,
    container_code: str | None,
    failure_reason: str | None = None,
) -> RecognitionResult:
    return RecognitionResult(
        source_path=Path(filename),
        original_name=filename,
        status=status,
        container_code=container_code,
        source=RecognitionSource.OCR if container_code else None,
        failure_reason=failure_reason,
        ocr_text=container_code or "",
        elapsed_ms=1,
    )


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
