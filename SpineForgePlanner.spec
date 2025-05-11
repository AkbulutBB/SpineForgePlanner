# -*- mode: python -*-
import sys
sys.setrecursionlimit(sys.getrecursionlimit() * 5)

block_cipher = None

a = Analysis(
    ['FirstDraft.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        'sphinx', 'sphinxcontrib', 'setuptools',
        'paramiko', 'cryptography', 'numpy.array_api'
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SpineForgePlanner',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # ⛔ disable UPX compression to avoid weird hangs
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='SpineForgePlanner'
)
