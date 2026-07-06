# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


APP_NAME = "运单箱号识别分拣"
PYINSTALLER_EXCLUDES = [
    "cv2",
    "opencv",
    "opencv_python",
    "numpy",
    "pytest",
]


def _file_datas(pattern: str, target_dir: str):
    return [(str(path), target_dir) for path in sorted(Path().glob(pattern)) if path.is_file()]


def _recursive_datas(source_dir: str, target_dir: str):
    source = Path(source_dir)
    if not source.exists():
        return []
    datas = []
    for path in sorted(source.rglob("*")):
        if path.is_file():
            relative_parent = path.parent.relative_to(source).as_posix()
            destination = target_dir if relative_parent == "." else f"{target_dir}/{relative_parent}"
            datas.append((str(path), destination))
    return datas


POPPLER_DLL_EXCLUDES = {
    "poppler-cpp.dll",
    "poppler-glib.dll",
}


def _poppler_runtime_dlls():
    return [
        (str(path), "tools/poppler/Library/bin")
        for path in sorted(Path("tools/poppler/Library/bin").glob("*.dll"))
        if path.name.lower() not in POPPLER_DLL_EXCLUDES
    ]


def _runtime_datas():
    datas = [
        ("resources", "resources"),
        ("docs", "docs"),
        ("tools/tesseract/tesseract.exe", "tools/tesseract"),
        ("tools/tesseract/tessdata/eng.traineddata", "tools/tesseract/tessdata"),
        ("tools/poppler/Library/bin/pdfinfo.exe", "tools/poppler/Library/bin"),
        ("tools/poppler/Library/bin/pdftoppm.exe", "tools/poppler/Library/bin"),
    ]
    datas.extend(_file_datas("tools/tesseract/*.dll", "tools/tesseract"))
    datas.extend(_poppler_runtime_dlls())
    datas.extend(_recursive_datas("tools/poppler/Library/share", "tools/poppler/Library/share"))
    return datas


a = Analysis(
    ["src/waybill_ocr/__main__.py"],
    pathex=["src"],
    binaries=[],
    datas=_runtime_datas(),
    hiddenimports=collect_submodules("waybill_ocr"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=PYINSTALLER_EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)
