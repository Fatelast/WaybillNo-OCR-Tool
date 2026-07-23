"""待确认文件扫描、人工确认和预期清单自动整理。"""

from __future__ import annotations

import re
import shutil
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from waybill_ocr.constants import INVALID_DIR_NAME, SUCCESS_DIR_NAME, UNRECOGNIZED_DIR_NAME
from waybill_ocr.container_code.validator import is_valid_container_code
from waybill_ocr.models import RecognitionStatus


_REVIEW_NAME_PATTERN = re.compile(
    r"^(?P<code>[A-Z]{3}U\d{7})-待确认(?:-\d+)?(?P<suffix>\.[^.]+)$",
    re.IGNORECASE,
)
_REVIEW_DIR_NAMES = {
    UNRECOGNIZED_DIR_NAME: RecognitionStatus.UNRECOGNIZED,
    INVALID_DIR_NAME: RecognitionStatus.INVALID,
}


@dataclass(frozen=True)
class ReviewCandidate:
    source_path: Path
    source_status: RecognitionStatus
    review_code: str
    target_path: Path
    valid: bool
    reason: str | None = None


@dataclass(frozen=True)
class ReviewActionSummary:
    moved_count: int
    skipped_count: int
    conflict_count: int
    failures: tuple[str, ...] = ()


def scan_review_candidates(output_dir: Path) -> list[ReviewCandidate]:
    """扫描输出目录中的待确认文件，并预先标记冲突。"""
    output_root = output_dir.resolve()
    success_dir = output_root / SUCCESS_DIR_NAME
    existing_codes = _existing_success_codes(success_dir)
    candidates: list[ReviewCandidate] = []

    for directory_name, status in _REVIEW_DIR_NAMES.items():
        source_dir = output_root / directory_name
        if not source_dir.is_dir():
            continue
        for source_path in sorted(source_dir.iterdir(), key=lambda path: path.name.casefold()):
            if not source_path.is_file():
                continue
            match = _REVIEW_NAME_PATTERN.fullmatch(source_path.name)
            if not match:
                continue
            code = match.group("code").upper()
            target_path = success_dir / f"{code}{match.group('suffix')}"
            valid, reason = _validate_candidate(code, target_path, existing_codes)
            candidates.append(
                ReviewCandidate(
                    source_path=source_path,
                    source_status=status,
                    review_code=code,
                    target_path=target_path,
                    valid=valid,
                    reason=reason,
                )
            )

    counts = defaultdict(int)
    for candidate in candidates:
        counts[candidate.review_code] += 1
    return [
        candidate
        if counts[candidate.review_code] == 1
        else ReviewCandidate(
            source_path=candidate.source_path,
            source_status=candidate.source_status,
            review_code=candidate.review_code,
            target_path=candidate.target_path,
            valid=False,
            reason="同一箱号对应多个待确认文件",
        )
        for candidate in candidates
    ]


def confirm_review_candidates(output_dir: Path, candidates: list[ReviewCandidate]) -> ReviewActionSummary:
    """移动人工确认的候选文件，不覆盖已有文件。"""
    output_root = output_dir.resolve()
    selected_codes = defaultdict(int)
    for candidate in candidates:
        if candidate.valid:
            selected_codes[candidate.review_code] += 1

    moved_count = 0
    skipped_count = 0
    conflict_count = 0
    failures: list[str] = []
    for candidate in candidates:
        if not candidate.valid:
            skipped_count += 1
            conflict_count += 1
            failures.append(f"{candidate.source_path.name}: {candidate.reason or '候选不可整理'}")
            continue
        if selected_codes[candidate.review_code] > 1:
            skipped_count += 1
            conflict_count += 1
            failures.append(f"{candidate.source_path.name}: 同一批次存在重复箱号 {candidate.review_code}")
            continue
        if not _is_safe_candidate(candidate, output_root):
            skipped_count += 1
            conflict_count += 1
            failures.append(f"{candidate.source_path.name}: 文件路径不在当前输出目录内")
            continue
        if candidate.target_path.exists():
            skipped_count += 1
            conflict_count += 1
            failures.append(f"{candidate.source_path.name}: 目标文件已存在")
            continue
        try:
            candidate.target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(candidate.source_path), str(candidate.target_path))
            moved_count += 1
        except OSError as exc:
            skipped_count += 1
            failures.append(f"{candidate.source_path.name}: {exc}")

    return ReviewActionSummary(
        moved_count=moved_count,
        skipped_count=skipped_count,
        conflict_count=conflict_count,
        failures=tuple(failures),
    )


def expected_review_candidates(output_dir: Path, expected_codes: list[str]) -> list[ReviewCandidate]:
    """返回与预期清单匹配且可安全整理的待确认候选。"""
    expected_set = {code.strip().upper() for code in expected_codes if code and code.strip()}
    candidates = scan_review_candidates(output_dir)
    return [candidate for candidate in candidates if candidate.valid and candidate.review_code in expected_set]


def auto_confirm_expected_candidates(output_dir: Path, expected_codes: list[str]) -> ReviewActionSummary:
    """仅整理与预期清单唯一匹配且无冲突的待确认候选。"""
    return confirm_review_candidates(output_dir, expected_review_candidates(output_dir, expected_codes))


def _validate_candidate(code: str, target_path: Path, existing_codes: set[str]) -> tuple[bool, str | None]:
    if not is_valid_container_code(code):
        return False, "箱号格式或 ISO 6346 校验不通过"
    if code in existing_codes:
        return False, "正确识别目录已有同箱号文件"
    if target_path.exists():
        return False, "目标文件已存在"
    return True, None


def _existing_success_codes(success_dir: Path) -> set[str]:
    if not success_dir.is_dir():
        return set()
    codes: set[str] = set()
    for path in success_dir.iterdir():
        if not path.is_file():
            continue
        base_code = path.stem.upper().split("-", 1)[0]
        if is_valid_container_code(base_code):
            codes.add(base_code)
    return codes


def _is_safe_candidate(candidate: ReviewCandidate, output_root: Path) -> bool:
    try:
        source_relative = candidate.source_path.resolve().relative_to(output_root)
        target_relative = candidate.target_path.resolve().relative_to(output_root)
    except ValueError:
        return False
    return (
        len(source_relative.parts) == 2
        and source_relative.parts[0] in _REVIEW_DIR_NAMES
        and len(target_relative.parts) == 2
        and target_relative.parts[0] == SUCCESS_DIR_NAME
        and candidate.target_path.name == f"{candidate.review_code}{candidate.source_path.suffix}"
    )
