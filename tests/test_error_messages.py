from waybill_ocr.error_messages import humanize_failure_reason, merge_review_note_with_failure_reason


def test_humanize_failure_reason_maps_common_codes():
    assert humanize_failure_reason("INVALID_CHECK_DIGIT") == "识别到疑似箱号，但校验位不正确，需要人工复核"
    assert humanize_failure_reason("CONFLICTING_CANDIDATES") == "同一文件出现多个候选箱号，需要人工确认"
    assert humanize_failure_reason("DUPLICATE_CONTAINER_CODE") == "\u591a\u4e2a\u6587\u4ef6\u8bc6\u522b\u4e3a\u540c\u4e00\u7bb1\u53f7\uff0c\u9700\u8981\u9010\u4e00\u6838\u5bf9"
    assert humanize_failure_reason("INSUFFICIENT_CANDIDATE_EVIDENCE") == "识别到合法候选，但交叉验证证据不足，需要人工确认"
    assert humanize_failure_reason("NO_CONTAINER_CANDIDATE") == "未找到符合箱号格式的文本"


def test_humanize_failure_reason_maps_runtime_failures():
    assert "Excel/WPS" in humanize_failure_reason("PROCESS_FAILED: Permission denied")
    assert "PDF 转图片失败" in humanize_failure_reason("PROCESS_FAILED: poppler error")
    assert "OCR 组件处理失败" in humanize_failure_reason("Tesseract OCR 失败: cannot load language")


def test_merge_review_note_with_failure_reason_keeps_existing_note():
    assert merge_review_note_with_failure_reason("原备注", "INVALID_CHECK_DIGIT") == (
        "原备注；识别到疑似箱号，但校验位不正确，需要人工复核"
    )
