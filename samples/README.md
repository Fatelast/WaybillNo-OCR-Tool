# 样本回归目录

`cases/` 用于存放脱敏后的业务样本，建议按以下类型归档：

- `clear`：清晰、应正确识别的样本。
- `blurred`：模糊件，可用于验证增强 OCR 和待确认候选。
- `shifted`：箱号位置不固定或版式变化的样本。
- `invalid-check-digit`：格式完整但校验位错误的样本。
- `no-container`：确认不应识别出箱号的样本。
- `multilingual-name`：文件名含多语言字符的样本。

`expected/baseline.csv` 字段：

可先参考 `expected/baseline.example.csv`，再把真实脱敏样本写入 `expected/baseline.csv`。

```csv
filename,expected_code,expected_status,allow_review_code,quality_tag,notes
```

- `filename` 使用相对样本输入目录的路径，例如 `blurred/sample.pdf`。
- `expected_status` 支持 `正确识别`、`未识别`、`箱号错误`。
- `allow_review_code` 为 `true` 时，允许非成功结果带有匹配的待确认候选。
- 验收报告会按 `quality_tag` 输出分类统计，用于判断某类样本是否被新规则提升或误伤。

运行：

```powershell
.\.venv\Scripts\python.exe -m waybill_ocr verify-samples --input samples/cases
```

## 本地真实样本

真实业务 PDF 和 `expected/baseline.local.csv` 已由 `.gitignore` 排除，不会随代码提交。当前本机基线包含 3 个已知样本；执行验收时会优先读取该本地基线。新增真实样本时应使用泛化文件名，并同步添加对应期望记录。

## 兼容的旧样本目录

旧版 `samples/input` 仍保留以下分类，已有样本可以继续放在这些目录中：

- `clear_pdf`
- `blurred_pdf`
- `variant_position_pdf`
- `invalid_check_digit`
- `no_container_code`
- `image_formats`

