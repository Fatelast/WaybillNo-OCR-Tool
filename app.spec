# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules


a = Analysis(
    ["src/waybill_ocr/__main__.py"],
    pathex=["src"],
    binaries=[],
    datas=[
        ("tools", "tools"),
        ("resources", "resources"),
        ("docs", "docs"),
    ],
    hiddenimports=collect_submodules("waybill_ocr"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="运单箱号识别分拣",
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
    name="运单箱号识别分拣",
)