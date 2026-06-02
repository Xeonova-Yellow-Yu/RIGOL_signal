# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

APP_VERSION = (0, 2, 0, 0)
APP_VERSION_STR = "0.2.0"

version_info = VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=APP_VERSION,
        prodvers=APP_VERSION,
        mask=0x3F,
        flags=0x0,
        OS=0x40004,
        fileType=0x1,
        subtype=0x0,
        date=(0, 0),
    ),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    "040904B0",
                    [
                        StringStruct("CompanyName", "NBI"),
                        StringStruct(
                            "FileDescription",
                            "RIGOL DG1022Z Waveform Generator Control",
                        ),
                        StringStruct("FileVersion", f"{APP_VERSION_STR}.0"),
                        StringStruct("InternalName", "RigolDG1022Z"),
                        StringStruct("OriginalFilename", "RigolDG1022Z.exe"),
                        StringStruct("ProductName", "RIGOL DG1022Z Control"),
                        StringStruct("ProductVersion", f"{APP_VERSION_STR}.0"),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)

datas = []
binaries = []
hiddenimports = ['pyvisa', 'pyvisa_py', 'pyvisa_py.protocols']
tmp_ret = collect_all('PySide6')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=['src'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    [],
    exclude_binaries=True,
    name='RigolDG1022Z',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=version_info,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='RigolDG1022Z',
)
