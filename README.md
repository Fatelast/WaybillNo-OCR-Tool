# 运单箱号识别工具源码

本项目用于从运单图片或 PDF 中离线识别集装箱箱号，并按识别结果分类输出文件和 Excel 汇总。

## 当前范围

- Python 项目骨架与 pytest 测试配置。
- ISO 6346 箱号校验、候选提取和非法箱号分类。
- 图片/PDF 输入扫描、Tesseract OCR、PDF 转图。
- 分类输出与 `识别结果.xlsx` 汇总。
- Tkinter 桌面界面。
- CLI 环境诊断、批量处理和样本基线验收。

## 本地验证

```powershell
. .\local-env.ps1
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m waybill_ocr diagnose
.\.venv\Scripts\python.exe -m waybill_ocr verify-samples
```

`verify-samples` 默认读取 `samples/input` 和 `samples/expected/baseline.csv`，输出到 `samples/actual`。
