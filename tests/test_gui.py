from __future__ import annotations

import thermex_key_exporter.gui as gui


def test_gui_reports_a_missing_tkinter_runtime_clearly(monkeypatch, capsys) -> None:
    def missing_tkinter(name: str):
        assert name == "tkinter"
        raise ModuleNotFoundError("No module named '_tkinter'", name="_tkinter")

    monkeypatch.setattr(gui.importlib, "import_module", missing_tkinter)

    assert gui.run() == 2

    captured = capsys.readouterr()
    assert "Tkinter" in captured.err
