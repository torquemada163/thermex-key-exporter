from __future__ import annotations

from pathlib import Path

import thermex_key_exporter.gui as gui


def test_gui_reports_a_missing_tkinter_runtime_clearly(monkeypatch, capsys) -> None:
    def missing_tkinter(name: str):
        assert name == "tkinter"
        raise ModuleNotFoundError("No module named '_tkinter'", name="_tkinter")

    monkeypatch.setattr(gui.importlib, "import_module", missing_tkinter)

    assert gui.run() == 2

    captured = capsys.readouterr()
    assert "Tkinter" in captured.err


def test_gui_import_check_loads_dynamic_tkinter_modules(monkeypatch) -> None:
    imported: list[str] = []

    def import_module(name: str) -> object:
        imported.append(name)
        return object()

    monkeypatch.setattr(gui.importlib, "import_module", import_module)

    assert gui.run(import_check=True) == 0
    assert imported == ["tkinter", "tkinter.filedialog"]


def test_gui_default_output_path_uses_the_home_directory(monkeypatch) -> None:
    monkeypatch.setattr(gui.Path, "home", lambda: Path("/synthetic-home"))

    assert gui._default_output_path() == Path("/synthetic-home/thermex-localtuya.json")
