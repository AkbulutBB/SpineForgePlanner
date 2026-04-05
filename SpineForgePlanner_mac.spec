# -*- mode: python -*-
# SpineForgePlanner - macOS Build Spec
import sys
sys.setrecursionlimit(sys.getrecursionlimit() * 5)

block_cipher = None

a = Analysis(
    ['SFP-Ver0.6.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'pydicom',
        'pydicom.encoders',
        'pydicom.encoders.gdcm',
        'pydicom.encoders.pylibjpeg',
        'PIL',
        'PIL._tkinter_finder',
        'scipy',
        'scipy.interpolate',
        'scipy.spatial',
        'scipy.sparse',
        'stl',
        'numpy',
        'numpy.core',
        'numpy.core._multiarray_umath',
        'pyperclip',
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'sphinx',
        'sphinxcontrib',
        'setuptools',
        'paramiko',
        'cryptography',
        'numpy.array_api',
        'matplotlib',
        'IPython',
        'jupyter',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
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
    upx=False,
    console=False,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='SpineForgePlanner',
)

app = BUNDLE(
    coll,
    name='SpineForgePlanner.app',
    icon='assets/spineforge_logo.icns',
    bundle_identifier='org.spineforge.planner',
    info_plist={
        'CFBundleName': 'SpineForgePlanner',
        'CFBundleDisplayName': 'SpineForgePlanner',
        'CFBundleVersion': '0.6.0',
        'CFBundleShortVersionString': '0.6',
        'NSHighResolutionCapable': True,
        'NSRequiresAquaSystemAppearance': False,
        'LSMinimumSystemVersion': '12.0',
        'NSHumanReadableCopyright': 'Dr. Bahadir Akbulut, MD - SpineForge.org',
        'NSPrincipalClass': 'NSApplication',
        'NSAppleScriptEnabled': False,
    },
)
