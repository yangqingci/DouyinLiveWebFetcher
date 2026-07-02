# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

import certifi
import py_mini_racer

PORTABLE_DIR = Path(SPECPATH).resolve()
ROOT = PORTABLE_DIR.parent
PY_MINI_RACER_DIR = Path(py_mini_racer.__file__).resolve().parent


def require_file(path):
    if not path.exists():
        raise FileNotFoundError(f"Required package resource is missing: {path}")
    return str(path)


mini_racer_runtime_files = [
    "mini_racer.dll",
    "icudtl.dat",
    "snapshot_blob.bin",
]

datas = [
    (str(ROOT / "a_bogus.js"), "."),
    (str(ROOT / "sign.js"), "."),
    (str(ROOT / "sign_v0.js"), "."),
    (str(ROOT / "webmssdk.js"), "."),
    (str(ROOT / "platform_ingest.env.example"), "."),
    (str(ROOT / "protobuf" / "douyin.proto"), "protobuf"),
    (require_file(Path(certifi.where())), "certifi"),
    *[
        (require_file(PY_MINI_RACER_DIR / file_name), ".")
        for file_name in mini_racer_runtime_files
    ],
]


a = Analysis(
    [str(PORTABLE_DIR / "forwarder_gui.py")],
    pathex=[str(ROOT), str(PORTABLE_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "betterproto",
        "protobuf",
        "protobuf.douyin",
        "websocket",
        "websocket._abnf",
        "py_mini_racer",
    ],
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
    name="DouyinDanmakuForwarder",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="DouyinDanmakuForwarder",
)
