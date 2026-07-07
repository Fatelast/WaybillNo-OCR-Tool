# OCR 成功率模式分层优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 提高模糊运单 PDF 的自动正确识别率，同时保留快速模式的处理速度和现有安全边界，避免把不可靠猜测直接归为正确识别。

**Architecture:** 在现有 `pipeline` 中增加“候选证据汇总 -> 模式分层二次验证 -> 决策输出”的轻量层。快速模式只收集和展示待确认候选；均衡模式对失败/待确认候选做有限增强验证；稳定模式执行完整增强、多 PSM 和多候选评分。

**Tech Stack:** Python 3.12、Pillow、Tesseract、Poppler、openpyxl、pytest、PyInstaller。

---

## 构思方案

当前输出目录样本统计显示：54 个文件中正确识别 31 个，未识别 19 个，箱号错误 4 个；其中 12 个失败文件已经能生成待确认候选。优先优化方向不是直接放宽识别规则，而是把这些已有候选通过二次 OCR 证据验证后安全转正。

核心思路：

- 快速模式保持轻量：不做高 DPI 增强，不做复杂转正，只保留 `review_code` 和 `-待确认`。
- 均衡模式作为默认：仅对未识别、箱号错误、待确认候选执行有限二次验证。
- 稳定模式追求准确：对模糊件、冲突件执行完整增强、多 PSM、多区域交叉验证。
- 最终正确识别仍必须通过 ISO 6346 校验；`O/0`、`S/5`、`B/8`、`I/1`、`G/6`、`T/7` 等猜测替换不能单独作为转正依据。

## 提请审核

建议确认以下产品边界后再进入编码：

- 快速模式是否明确承诺“只做快速粗筛，不追求最大识别率”。
- 均衡模式是否允许将“同一待确认候选在基础 OCR 与增强 OCR 中重复出现”的文件自动转入正确识别。
- 稳定模式是否允许明显变慢，以换取更多增强 OCR 尝试。
- 预期箱号清单命中是否可作为高权重证据，但不能单独覆盖 OCR 结果。

## File Structure

- Modify: `src/waybill_ocr/pipeline.py`
  - 负责单文件识别编排，接入模式分层二次验证和冲突候选决策。
- Modify: `src/waybill_ocr/container_code/extractor.py`
  - 增加可解释的疑似候选和猜测修正提取结构，保留当前字符串 API 兼容。
- Modify: `src/waybill_ocr/container_code/candidate_selector.py`
  - 增加候选证据评分结构，用于二次验证和多候选排序。
- Modify: `src/waybill_ocr/image_regions.py`
  - 按速度模式控制增强区域、DPI、图像预处理和 PSM 组合。
- Modify: `src/waybill_ocr/ocr/base.py`
  - 如当前协议已支持 `psm`，只补注释；否则补齐协议签名。
- Modify: `src/waybill_ocr/ocr/tesseract_engine.py`
  - 确认 `psm` 参数能传入 Tesseract 命令。
- Modify: `src/waybill_ocr/models.py`
  - 如需要记录证据，可增加内部字段；不新增 Excel 主表列。
- Modify: `src/waybill_ocr/ui/main_window.py`
  - 更新速度模式短说明，让用户理解不同模式的成功率/速度取舍。
- Modify: `tests/test_pipeline.py`
  - 覆盖模式分层、待确认候选转正、多候选冲突、快速模式保守行为。
- Modify: `tests/test_container_extractor.py`
  - 覆盖疑似候选提取和猜测替换证据。
- Modify: `tests/test_candidate_selector.py`
  - 覆盖候选证据评分规则。
- Modify: `tests/test_image_regions.py` 或新增 `tests/test_image_regions_enhanced.py`
  - 覆盖不同模式下增强区域数量和策略。
- Modify: `docs/操作说明.md`
  - 更新速度模式说明。
- Modify: `docs/项目知识快照.md`
  - 更新 OCR 决策链路。

---

## Task List

### Task 1: 提取候选证据结构

**Files:**
- Modify: `src/waybill_ocr/container_code/extractor.py`
- Test: `tests/test_container_extractor.py`

- [ ] **Step 1: 写失败测试，覆盖疑似候选证据**

```python
def test_extract_guess_repair_evidence_keeps_raw_and_repaired_code():
    from waybill_ocr.container_code.extractor import extract_guess_repair_evidence

    evidence = extract_guess_repair_evidence("OCR UACUSSO2014 UACUS5O2014")

    assert [(item.raw, item.repaired) for item in evidence] == [
        ("UACUSSO2014", "UACU5502014"),
        ("UACUS5O2014", "UACU5502014"),
    ]
    assert all(item.repaired_valid for item in evidence)
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
$env:PYTHONPATH='src'
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest -p no:cacheprovider tests/test_container_extractor.py::test_extract_guess_repair_evidence_keeps_raw_and_repaired_code -q
```

Expected: `ImportError` 或 `AttributeError`，因为 `extract_guess_repair_evidence` 尚不存在。

- [ ] **Step 3: 增加最小实现**

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class GuessRepairEvidence:
    raw: str
    repaired: str
    repaired_valid: bool


def extract_guess_repair_evidence(text: str) -> list[GuessRepairEvidence]:
    evidence: list[GuessRepairEvidence] = []
    for raw, repaired in extract_guess_repair_suggestions(text):
        item = GuessRepairEvidence(raw=raw, repaired=repaired, repaired_valid=is_valid_container_code(repaired))
        if item not in evidence:
            evidence.append(item)
    return evidence
```

- [ ] **Step 4: 保持旧 API 兼容**

确认 `extract_guess_repair_suggestions(text)` 仍返回 `list[tuple[str, str]]`，避免影响 `pipeline.py` 当前调用。

- [ ] **Step 5: 运行测试确认通过**

```powershell
python -m pytest -p no:cacheprovider tests/test_container_extractor.py -q
```

Expected: `passed`。

### Task 2: 增加候选证据评分器

**Files:**
- Modify: `src/waybill_ocr/container_code/candidate_selector.py`
- Test: `tests/test_candidate_selector.py`

- [ ] **Step 1: 写失败测试，覆盖重复证据加分**

```python
def test_score_review_candidate_prefers_repeated_repaired_code():
    from waybill_ocr.container_code.candidate_selector import score_review_candidates

    scores = score_review_candidates(
        base_text="UACUSSO2014 UACUS5O2014",
        enhanced_text="UACU5502014 45G1",
        candidates=["UACU5502014", "UACU5502015"],
        expected_codes=set(),
    )

    assert scores[0].code == "UACU5502014"
    assert scores[0].score > scores[1].score
    assert "enhanced_valid" in scores[0].reasons
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
python -m pytest -p no:cacheprovider tests/test_candidate_selector.py::test_score_review_candidate_prefers_repeated_repaired_code -q
```

Expected: `ImportError` 或 `AttributeError`。

- [ ] **Step 3: 增加评分数据结构和最小函数**

```python
@dataclass(frozen=True)
class ReviewCandidateScore:
    code: str
    score: int
    reasons: tuple[str, ...]


def score_review_candidates(
    base_text: str,
    enhanced_text: str,
    candidates: list[str],
    expected_codes: set[str] | None = None,
) -> list[ReviewCandidateScore]:
    expected_codes = expected_codes or set()
    normalized_base = base_text.upper()
    normalized_enhanced = enhanced_text.upper()
    scored: list[ReviewCandidateScore] = []
    for code in candidates:
        score = 0
        reasons: list[str] = []
        if code in normalized_base:
            score += 30
            reasons.append("base_valid")
        if code in normalized_enhanced:
            score += 50
            reasons.append("enhanced_valid")
        if expected_codes and code in expected_codes:
            score += 40
            reasons.append("expected_match")
        scored.append(ReviewCandidateScore(code=code, score=score, reasons=tuple(reasons)))
    return sorted(scored, key=lambda item: item.score, reverse=True)
```

- [ ] **Step 4: 增加安全阈值测试**

```python
def test_score_review_candidates_requires_clear_margin():
    from waybill_ocr.container_code.candidate_selector import has_clear_review_winner, ReviewCandidateScore

    scores = [
        ReviewCandidateScore(code="YYCU6003610", score=80, reasons=("enhanced_valid",)),
        ReviewCandidateScore(code="YYCU6002610", score=75, reasons=("base_valid",)),
    ]

    assert has_clear_review_winner(scores, min_score=80, min_margin=20) is None
```

- [ ] **Step 5: 实现明确胜出判断**

```python
def has_clear_review_winner(
    scores: list[ReviewCandidateScore],
    min_score: int,
    min_margin: int,
) -> str | None:
    if not scores:
        return None
    ordered = sorted(scores, key=lambda item: item.score, reverse=True)
    best = ordered[0]
    if best.score < min_score:
        return None
    if len(ordered) > 1 and best.score - ordered[1].score < min_margin:
        return None
    return best.code
```

### Task 3: 模式分层二次验证决策

**Files:**
- Modify: `src/waybill_ocr/pipeline.py`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: 写快速模式保守测试**

```python
def test_fast_mode_keeps_review_candidate_as_unrecognized(tmp_path, monkeypatch):
    source_path = tmp_path / "waybill.jpg"
    source_path.write_bytes(b"fake")
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")

    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_priority_ocr_regions", lambda *_args: [])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_grid_ocr_regions", lambda *_args: [])

    result = process_file(task, AppConfig(ocr_speed_mode="fast"), FakeOcrEngine("UACUSSO2014 UACUS5O2014"))

    assert result.status == RecognitionStatus.UNRECOGNIZED
    assert result.review_code == "UACU5502014"
```

- [ ] **Step 2: 写均衡模式可转正测试**

```python
def test_balanced_mode_promotes_review_candidate_after_enhanced_confirmation(tmp_path, monkeypatch):
    source_path = tmp_path / "waybill.jpg"
    source_path.write_bytes(b"fake")
    enhanced_path = tmp_path / "enhanced.png"
    enhanced_path.write_bytes(b"fake")
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")

    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_priority_ocr_regions", lambda *_args: [])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_grid_ocr_regions", lambda *_args: [])
    monkeypatch.setattr(
        "waybill_ocr.pipeline.iter_enhanced_ocr_regions",
        lambda *_args: [OcrRegion(image_path=enhanced_path, region_name="enhanced-full-middle")],
    )

    result = process_file(
        task,
        AppConfig(ocr_speed_mode="balanced"),
        FakeOcrEngine({"waybill.jpg": "UACUSSO2014", "enhanced.png": "UACU5502014 45G1"}),
    )

    assert result.status == RecognitionStatus.SUCCESS
    assert result.container_code == "UACU5502014"
    assert result.source == RecognitionSource.OCR_ENHANCED
```

- [ ] **Step 3: 实现模式判断辅助函数**

```python
def _should_promote_review_candidate(config: AppConfig) -> bool:
    return config.ocr_speed_mode in {OCR_SPEED_BALANCED, OCR_SPEED_STABLE}


def _review_promotion_thresholds(config: AppConfig) -> tuple[int, int]:
    if config.ocr_speed_mode == OCR_SPEED_STABLE:
        return 80, 15
    return 90, 25
```

- [ ] **Step 4: 在未识别返回前插入转正尝试**

在 `process_file` 的 `RecognitionStatus.UNRECOGNIZED` 返回前，先计算 `review_code = _review_code_from_text(combined_text)`。如果 `review_code` 存在且模式允许转正，则执行增强 OCR 验证；验证通过返回 `SUCCESS`，否则维持 `UNRECOGNIZED + review_code`。

- [ ] **Step 5: 运行 pipeline 测试**

```powershell
python -m pytest -p no:cacheprovider tests/test_pipeline.py -q
```

Expected: `passed`。

### Task 4: 多候选校验位修正评分

**Files:**
- Modify: `src/waybill_ocr/pipeline.py`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: 写多候选快速模式测试**

```python
def test_fast_mode_does_not_pick_ambiguous_digit_repair(tmp_path, monkeypatch):
    source_path = tmp_path / "waybill.jpg"
    source_path.write_bytes(b"fake")
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")

    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_priority_ocr_regions", lambda *_args: [])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_grid_ocr_regions", lambda *_args: [])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_enhanced_ocr_regions", lambda *_args: [])

    result = process_file(task, AppConfig(ocr_speed_mode="fast"), FakeOcrEngine("YYCU6002610"))

    assert result.status == RecognitionStatus.INVALID
    assert result.review_code is None
```

- [ ] **Step 2: 写稳定模式通过增强证据选中测试**

```python
def test_stable_mode_selects_clear_digit_repair_with_enhanced_evidence(tmp_path, monkeypatch):
    source_path = tmp_path / "waybill.jpg"
    source_path.write_bytes(b"fake")
    enhanced_path = tmp_path / "enhanced.png"
    enhanced_path.write_bytes(b"fake")
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")

    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_priority_ocr_regions", lambda *_args: [])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_grid_ocr_regions", lambda *_args: [])
    monkeypatch.setattr(
        "waybill_ocr.pipeline.iter_enhanced_ocr_regions",
        lambda *_args: [OcrRegion(image_path=enhanced_path, region_name="enhanced-full-middle")],
    )

    result = process_file(
        task,
        AppConfig(ocr_speed_mode="stable"),
        FakeOcrEngine({"waybill.jpg": "YYCU6002610", "enhanced.png": "YYCU6003610 45G1"}),
    )

    assert result.status == RecognitionStatus.SUCCESS
    assert result.container_code == "YYCU6003610"
```

- [ ] **Step 3: 实现多候选修正列表复用**

复用现有 `_single_digit_check_repairs(candidate)`，不要新增第二套校验位修复逻辑。

- [ ] **Step 4: 增加增强证据评分**

把 `_single_digit_check_repairs(candidate)` 的结果传给 `score_review_candidates(...)`。只有 `has_clear_review_winner(...)` 返回箱号时，才允许转正或写入 `review_code`。

- [ ] **Step 5: 运行回归测试**

```powershell
python -m pytest -p no:cacheprovider tests/test_pipeline.py tests/test_candidate_selector.py -q
```

Expected: `passed`。

### Task 5: 模糊图像增强策略按模式分层

**Files:**
- Modify: `src/waybill_ocr/image_regions.py`
- Test: `tests/test_image_regions_enhanced.py`

- [ ] **Step 1: 写区域数量测试**

```python
def test_enhanced_regions_are_limited_in_balanced_mode():
    from waybill_ocr.image_regions import _enhanced_regions

    regions = _enhanced_regions(1000, 1000, mode="balanced")

    assert [name for name, _box in regions] == ["full-middle", "left-middle", "left-lower-middle"]
```

- [ ] **Step 2: 写稳定模式更多区域测试**

```python
def test_enhanced_regions_include_extra_lines_in_stable_mode():
    from waybill_ocr.image_regions import _enhanced_regions

    regions = _enhanced_regions(1000, 1000, mode="stable")
    names = [name for name, _box in regions]

    assert "full-middle" in names
    assert "full-upper-middle" in names
    assert "left-wide-middle" in names
    assert len(names) > 3
```

- [ ] **Step 3: 修改 `_enhanced_regions` 签名**

```python
def _enhanced_regions(width: int, height: int, mode: str = OCR_SPEED_BALANCED) -> list[tuple[str, tuple[int, int, int, int]]]:
    base_regions = [
        ("full-middle", _box(width, height, 0.00, 0.36, 1.00, 0.68)),
        ("left-middle", _box(width, height, 0.00, 0.42, 0.58, 0.66)),
        ("left-lower-middle", _box(width, height, 0.00, 0.54, 0.64, 0.82)),
    ]
    if mode != OCR_SPEED_STABLE:
        return base_regions
    return base_regions + [
        ("full-upper-middle", _box(width, height, 0.00, 0.22, 1.00, 0.54)),
        ("left-wide-middle", _box(width, height, 0.00, 0.32, 0.72, 0.74)),
    ]
```

- [ ] **Step 4: 修改调用处传入模式**

在 `_iter_enhanced_regions` 中把 `_enhanced_regions(width, height)` 改为 `_enhanced_regions(width, height, config.ocr_speed_mode)`。

- [ ] **Step 5: 运行测试**

```powershell
python -m pytest -p no:cacheprovider tests/test_image_regions_enhanced.py -q
```

Expected: `passed`。

### Task 6: Tesseract PSM 策略按模式分层

**Files:**
- Modify: `src/waybill_ocr/pipeline.py`
- Modify: `src/waybill_ocr/ocr/tesseract_engine.py`
- Test: `tests/test_pipeline.py`
- Test: `tests/test_tesseract_engine.py`

- [ ] **Step 1: 写 PSM 传参测试**

```python
def test_enhanced_ocr_uses_multiple_psm_in_stable_mode(tmp_path, monkeypatch):
    calls = []
    source_path = tmp_path / "waybill.jpg"
    source_path.write_bytes(b"fake")
    enhanced_path = tmp_path / "enhanced.png"
    enhanced_path.write_bytes(b"fake")
    task = FileTask(source_path=source_path, relative_name=source_path.name, suffix=".jpg")

    class RecordingOcrEngine:
        def recognize_image(self, image_path, cancel_event=None, *, psm=None):
            calls.append(psm)
            return OcrResult(text="no code", engine_name="fake", elapsed_ms=1)

    monkeypatch.setattr("waybill_ocr.pipeline.iter_images_for_ocr", lambda *_args: [source_path])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_priority_ocr_regions", lambda *_args: [])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_grid_ocr_regions", lambda *_args: [])
    monkeypatch.setattr("waybill_ocr.pipeline.iter_enhanced_ocr_regions", lambda *_args: [OcrRegion(enhanced_path, "enhanced")])

    process_file(task, AppConfig(ocr_speed_mode="stable"), RecordingOcrEngine())

    assert 6 in calls
    assert 7 in calls
    assert 11 in calls
```

- [ ] **Step 2: 增加 PSM 列表辅助函数**

```python
def _enhanced_psm_values(config: AppConfig) -> tuple[int, ...]:
    if config.ocr_speed_mode == OCR_SPEED_STABLE:
        return (6, 7, 11)
    return (6, 11)
```

- [ ] **Step 3: 修改增强 OCR 调用**

在 `_recognize_enhanced_selection` 中对每个增强区域按 `_enhanced_psm_values(config)` 依次调用 `_recognize_region(..., psm=psm)`。如果当前 `_recognize_region` 不接收 `psm`，先扩展签名并保持默认 `None`。

- [ ] **Step 4: 运行测试**

```powershell
python -m pytest -p no:cacheprovider tests/test_pipeline.py::test_enhanced_ocr_uses_multiple_psm_in_stable_mode tests/test_tesseract_engine.py -q
```

Expected: `passed`。

### Task 7: UI 速度模式说明更新

**Files:**
- Modify: `src/waybill_ocr/ui/main_window.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: 写说明文本测试**

```python
def test_speed_mode_descriptions_are_user_scenario_based():
    from waybill_ocr.ui.main_window import SPEED_MODE_DESCRIPTIONS

    assert "清晰文件" in SPEED_MODE_DESCRIPTIONS["fast"]
    assert "默认推荐" in SPEED_MODE_DESCRIPTIONS["balanced"]
    assert "模糊" in SPEED_MODE_DESCRIPTIONS["stable"]
    assert "PSM" not in SPEED_MODE_DESCRIPTIONS["stable"]
```

- [ ] **Step 2: 更新说明文案**

```python
SPEED_MODE_DESCRIPTIONS = {
    "fast": "适合清晰文件快速粗筛；失败件会保留待确认，不做深度复核。",
    "balanced": "默认推荐；兼顾速度和准确率，会对失败件做有限复核。",
    "stable": "适合模糊文件；处理更慢，会尽量复核并提升成功识别率。",
}
```

- [ ] **Step 3: 运行 UI 测试**

```powershell
python -m pytest -p no:cacheprovider tests/test_app.py -q
```

Expected: `passed`。

### Task 8: 文档与样本验收

**Files:**
- Modify: `docs/操作说明.md`
- Modify: `docs/项目知识快照.md`
- Test: `tests/test_packaging_files.py`

- [ ] **Step 1: 更新操作说明速度模式段落**

写入以下用户可理解文本：

```markdown
## 速度模式

- 快速模式：适合清晰文件快速粗筛；不做深度复核，失败件更多保留为待确认或未识别。
- 均衡模式：默认推荐；对失败件做有限复核，兼顾速度和成功率。
- 稳定模式：适合模糊文件；会进行更多增强识别，速度更慢，但更容易识别出低清晰度箱号。
```

- [ ] **Step 2: 更新项目知识快照**

补充：模式分层、候选转正、安全边界、样本回归注意事项。

- [ ] **Step 3: 跑全量测试**

```powershell
$env:PYTHONPATH='src'
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest -p no:cacheprovider --basetemp D:\OCRTool\.pytest-all -q
```

Expected: `128 passed` 或新增测试后的全部测试通过。

- [ ] **Step 4: 手工样本验收**

使用稳定模式重新处理：

```text
C:\Users\MSI\Downloads\505 СОСТАВ МЛ 54 КТК_compressed (1)
```

验收关注：

- `_10.pdf`、`_12.pdf`、`_13.pdf`、`_22.pdf`、`_29.pdf` 等待确认候选是否有一部分升级为正确识别。
- `_16.pdf` 是否仍避免无证据强行转正；如果增强 OCR 明确读到 `YYCU6003610`，才允许转正。
- `_2.pdf`、`_33.pdf`、`_53.pdf` 这类低质量件，即使不能转正，也应在备注里给出更清晰的疑似候选。

- [ ] **Step 5: 本地 dist 构建**

仅在代码实现完成后按既定约定构建本地 `dist`，不生成离线包：

```powershell
.\.venv\Scripts\python.exe -m PyInstaller app.spec --noconfirm
```

Expected: 更新 `D:\OCRTool\dist\运单箱号识别分拣\运单箱号识别分拣.exe`。

---

## Decision Notes

- 不把猜测替换单独作为正确识别依据；必须有增强 OCR、重复区域、上下文或预期清单等额外证据。
- 快速模式不做转正，避免速度退化。
- 均衡模式只处理失败件和待确认候选，不扩大所有成功件的 OCR 成本。
- 稳定模式允许慢，目标是提升模糊样本成功率。
- Excel 主表不新增技术列；必要诊断继续写备注或隐藏索引表。
- 每次业务代码修改后只构建本地 `dist`；离线包只在用户明确要求时生成。

## Self-Review

- Spec coverage：计划覆盖了待确认候选转正、多候选校验位评分、模糊图像增强、模式分层、UI 文案、文档和验收。
- Placeholder scan：没有使用占位式任务描述或“稍后实现”类表达。
- Type consistency：计划中的 `AppConfig.ocr_speed_mode`、`RecognitionStatus`、`RecognitionSource.OCR_ENHANCED`、`review_code` 与当前项目命名一致。