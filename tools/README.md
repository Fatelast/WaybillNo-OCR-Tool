# 离线工具目录

本目录用于放置离线 OCR 与 PDF 转图组件。

预期结构：

```text
tools/
  tesseract/
    tesseract.exe
    tessdata/
      eng.traineddata
  poppler/
    pdftoppm.exe
```

关键路径：

- `tools/tesseract/tesseract.exe`
- `tools/poppler/pdftoppm.exe`
- 也支持 `tools/poppler/bin/pdftoppm.exe`
- 也支持 `tools/poppler/Library/bin/pdftoppm.exe`

如果不把工具放入本目录，也可以通过环境变量指定：

- `WAYBILL_OCR_TESSERACT_CMD`
- `WAYBILL_OCR_POPPLER_PATH`
