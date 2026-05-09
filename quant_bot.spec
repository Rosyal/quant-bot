# -*- mode: python ; coding: utf-8 -*-
# Windows 一键可执行文件: pyinstaller quant_bot.spec
# 产物 dist/quant-bot.exe；请在含 config / data 目录下运行或设置工作目录

import os

block_cipher = None
_root = os.path.normpath(SPECPATH)

datas = [
    (os.path.join(_root, "web", "templates"), "web" + os.sep + "templates"),
    (os.path.join(_root, "web", "static"), "web" + os.sep + "static"),
]

a = Analysis(
    [os.path.join(_root, "main.py")],
    pathex=[_root],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "config",
        "data_fetcher",
        "data_fetcher_cn",
        "deliverables",
        "deliverables.dossier",
        "deliverables.runner",
        "deliverables.pdf_export",
        "deliverables.executive_brief",
        "deliverables.edge_diagnostics",
        "deliverables.governance",
        "deliverables.wf_chapter",
        "jinja2",
        "werkzeug",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="quant-bot",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
