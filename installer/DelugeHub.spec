# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for DelugeHub
# Run with: pyinstaller installer/DelugeHub.spec

import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

ICON = os.path.join(SPECPATH, 'icon.ico')

# Collect all PySide6 components needed
datas_pyside, binaries_pyside, hiddenimports_pyside = collect_all('PySide6')
datas_lxml,   binaries_lxml,   hiddenimports_lxml   = collect_all('lxml')

a = Analysis(
    ['../main.py'],
    pathex=['..'],
    binaries=binaries_pyside + binaries_lxml,
    datas=datas_pyside + datas_lxml + [(ICON, '.')],
    hiddenimports=(
        hiddenimports_pyside +
        hiddenimports_lxml +
        collect_submodules('app') +
        [
            'PySide6.QtCore',
            'PySide6.QtWidgets',
            'PySide6.QtGui',
            'lxml.etree',
            'lxml._elementpath',
            'pathlib',
            'zipfile',
            'json',
            'shutil',
        ]
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['sounddevice', 'numpy'],   # optional deps — exclude for smaller build
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DelugeHub',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # no console window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DelugeHub',
)
