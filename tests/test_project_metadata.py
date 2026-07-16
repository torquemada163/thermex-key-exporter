from __future__ import annotations

import tomllib
from pathlib import Path

from thermex_key_exporter import __version__


def test_runtime_version_matches_the_package_metadata() -> None:
    project_root = Path(__file__).resolve().parents[1]
    metadata = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))

    assert metadata["project"]["version"] == __version__


def test_python_package_exposes_only_the_supported_cli_entry_point() -> None:
    project_root = Path(__file__).resolve().parents[1]
    metadata = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))

    assert metadata["project"]["scripts"] == {
        "thermex-key-exporter": "thermex_key_exporter.cli:main"
    }
    assert "gui-scripts" not in metadata["project"]
