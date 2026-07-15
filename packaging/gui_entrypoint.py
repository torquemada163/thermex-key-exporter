"""PyInstaller entry point for the GUI distribution."""

import os
import sys

from thermex_key_exporter.gui import run_desktop

if __name__ == "__main__":
    raise SystemExit(
        run_desktop(
            sys.argv[1:],
            import_check=os.environ.get("THERMEX_GUI_IMPORT_CHECK") == "1",
        )
    )
