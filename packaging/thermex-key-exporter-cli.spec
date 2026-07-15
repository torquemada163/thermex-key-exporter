import os
from pathlib import Path

ROOT = Path(SPECPATH).parent
SOURCE = ROOT / "packaging" / "entrypoint.py"
profile_path = os.environ.get("THERMEX_PROFILE_PATH")
datas = []
if profile_path:
    profile_file = Path(profile_path).expanduser()
    if not profile_file.is_absolute():
        profile_file = ROOT / profile_file
    profile_file = profile_file.resolve()
    if not profile_file.is_file():
        raise SystemExit("THERMEX_PROFILE_PATH does not point to a readable profile bundle.")
    datas = [(str(profile_file), "thermex_key_exporter/data")]

a = Analysis(
    [str(SOURCE)],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=[],
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
    name="thermex-key-exporter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="thermex-key-exporter",
)
