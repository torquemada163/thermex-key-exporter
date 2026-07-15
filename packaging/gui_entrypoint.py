"""PyInstaller entry point for the GUI distribution."""

import os

from thermex_key_exporter.gui import run

if __name__ == "__main__":
    raise SystemExit(run(import_check=os.environ.get("THERMEX_GUI_IMPORT_CHECK") == "1"))
