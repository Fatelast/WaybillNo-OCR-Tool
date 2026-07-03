# 样本集说明

`samples/input` 放脱敏后的回归样本，不提交原始敏感运单或大文件。

目录分类：
- `clear_pdf`
- `blurred_pdf`
- `variant_position_pdf`
- `invalid_check_digit`
- `no_container_code`
- `image_formats`

`samples/expected/baseline.csv` 记录样本期望结果。

```powershell
. .\local-env.ps1
.\.venv\Scripts\python.exe -m waybill_ocr verify-samples
```
