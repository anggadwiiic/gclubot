# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys

python_root = Path(sys.base_prefix)
tcl_root = python_root / "tcl"

a = Analysis(
    ['app.py'],
    pathex=[str(python_root / "Lib")],
    binaries=[
        (str(python_root / "DLLs" / "_tkinter.pyd"), "."),
        (str(python_root / "DLLs" / "tk86t.dll"), "."),
    ],
    datas=[
        (str(tcl_root / "tcl8.6"), "tcl/tcl8.6"),
        (str(tcl_root / "tk8.6"), "tcl/tk8.6"),
    ],
    hiddenimports=[
        "_tkinter",
        "tkinter",
        "tkinter.filedialog",
        "tkinter.messagebox",
        "tkinter.ttk",
        "selenium.webdriver.chrome.webdriver",
        "selenium.webdriver.chrome.service",
        "selenium.webdriver.common.service",
        "selenium.webdriver.remote.webdriver",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='LU-Automation-Engine',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
