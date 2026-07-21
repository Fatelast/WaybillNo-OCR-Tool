def humanize_failure_reason(reason: str | None) -> str:
    if not reason:
        return ""

    message = str(reason)
    lowered = message.lower()
    if "permission" in lowered or "denied" in lowered:
        return f"结果表可能正在被 Excel/WPS 打开，或输出目录无写入权限: {message}"
    if "poppler" in lowered or "pdf" in lowered:
        return f"PDF 转图片失败，可能文件损坏、加密或格式异常: {message}"
    if "tesseract" in lowered or "ocr" in lowered:
        return f"OCR 组件处理失败，可能图片无法读取或 OCR 依赖异常: {message}"

    mapped = {
        "INVALID_CHECK_DIGIT": "识别到疑似箱号，但校验位不正确，需要人工复核",
        "CONFLICTING_CANDIDATES": "同一文件出现多个候选箱号，需要人工确认",
        "DUPLICATE_CONTAINER_CODE": "\u591a\u4e2a\u6587\u4ef6\u8bc6\u522b\u4e3a\u540c\u4e00\u7bb1\u53f7\uff0c\u9700\u8981\u9010\u4e00\u6838\u5bf9",
        "INSUFFICIENT_CANDIDATE_EVIDENCE": "识别到合法候选，但交叉验证证据不足，需要人工确认",
        "NO_CONTAINER_CANDIDATE": "未找到符合箱号格式的文本",
        "NO_CONTAINER_CODE": "未找到符合箱号格式的文本",
    }
    for code, humanized in mapped.items():
        if code in message:
            return humanized
    return message


def merge_review_note_with_failure_reason(review_note: str | None, failure_reason: str | None) -> str | None:
    humanized = humanize_failure_reason(failure_reason)
    if not humanized:
        return review_note
    if review_note:
        if humanized in review_note:
            return review_note
        return f"{review_note}；{humanized}"
    return humanized
