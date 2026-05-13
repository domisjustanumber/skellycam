# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import Tree, collect_all, collect_dynamic_libs, collect_submodules
import cv2
import importlib.util
import os
from pathlib import Path

datas = []
binaries = []
hiddenimports = ["encodings.idna"]

# ── openpnp-capture-python vendored native libs (DLL/.so/.dylib) ──
_spec = importlib.util.find_spec("openpnp_capture")
if _spec and _spec.origin:
    _vendor_openpnp = Path(_spec.origin).parent / "_vendor" / "openpnp_capture"
    if _vendor_openpnp.is_dir():
        datas += Tree(str(_vendor_openpnp), prefix="openpnp_capture/_vendor/openpnp_capture")

# ── OpenCV ──
# Only collect what we need from cv2 instead of collect_all which grabs
# test data, haarcascades, DNN models, and other bloat.
binaries.extend(collect_dynamic_libs('cv2'))
hiddenimports.extend(collect_submodules('cv2'))

# ── setuptools (needed by some vendored deps at runtime) ──
setuptools_datas, _, setuptools_hidden = collect_all('setuptools')
datas.extend(setuptools_datas)
hiddenimports.extend(setuptools_hidden)

# Ensure jaraco.text lorem ipsum file is included
jaraco_text_path = os.path.join(
    os.path.dirname(__import__('setuptools', fromlist=['_vendor']).__file__),
    '_vendor', 'jaraco', 'text'
)
datas.append((os.path.join(jaraco_text_path, '*.txt'), 'setuptools/_vendor/jaraco/text/'))

a = Analysis(
    ['skellycam/__main__.py'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # ── Test frameworks ──
        'pytest',
        'pytest_asyncio',
        '_pytest',

        # ── Dev/build tools ──
        'nuitka',
        'ruff',
        'bumpver',
        'pip_tools',
        'poethepoet',
        'pyinstaller',
        'setuptools',

        # ── scipy is only used in tests ──
        'scipy',

        # ── Heavy unused stdlib/third-party modules ──
        'tkinter',
        '_tkinter',
        'matplotlib',
        'IPython',
        'notebook',
        'sphinx',
        'docutils',

        # ── Debug/profile tools ──
        'pdb',
        'cProfile',
        'profile',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='skellycam_server',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
