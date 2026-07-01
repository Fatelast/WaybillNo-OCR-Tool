# 样本集说明

`samples/input` 放真实测试文件，不提交大文件。

`samples/expected/baseline.csv` 记录样本期望结果，字段说明：

- `filename`：样本文件名，需和处理结果中的原始文件名一致。
- `expected_code`：期望识别出的箱号；期望不识别时留空。
- `should_recognize`：`true` 表示必须识别为 `expected_code`，`false` 表示不应识别成功。
- `quality_tag`：样本质量标签，例如 `clear`、`blurred`，用于后续分析。
- `notes`：样本备注。

运行样本基线验收：

```powershell
. .\local-env.ps1
.\.venv\Scripts\python.exe -m waybill_ocr verify-samples
```
