import importlib.util
import os
from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_data_files

if importlib.util.find_spec("_tkinter") is None:
    raise SystemExit(
        "GUI packaging requires a Python distribution with the _tkinter extension."
    )

ROOT = Path(SPECPATH).parent
SOURCE = ROOT / "packaging" / "gui_entrypoint.py"
profile_path = os.environ.get("THERMEX_PROFILE_PATH")
datas = collect_data_files("certifi")
if profile_path:
    profile_file = Path(profile_path).expanduser()
    if not profile_file.is_absolute():
        profile_file = ROOT / profile_file
    profile_file = profile_file.resolve()
    if not profile_file.is_file():
        raise SystemExit("THERMEX_PROFILE_PATH does not point to a readable profile bundle.")
    datas.append((str(profile_file), "thermex_key_exporter/data"))

a = Analysis(
    [str(SOURCE)],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=["thermex_key_exporter.gui_qr", "tkinter", "tkinter.filedialog"],
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
    name="ThermexKeyExporter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ThermexKeyExporter",
)
if sys.platform == "darwin":
    app = BUNDLE(coll, name="ThermexKeyExporter.app", icon=None)
