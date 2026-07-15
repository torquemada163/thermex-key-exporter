#!/usr/bin/env python3
"""Fail when tracked project text contains forbidden emoji characters."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thermex_key_exporter.text_policy import check_paths  # noqa: E402

TEXT_PATHS = (
    ROOT / ".gitignore",
    ROOT / "README.md",
    ROOT / "CHANGELOG.md",
    ROOT / "LICENSE",
    ROOT / "pyproject.toml",
    ROOT / "private" / "docs",
    ROOT / "src",
    ROOT / "tests",
    ROOT / "scripts",
    ROOT / "packaging",
    ROOT / ".github",
)


def iter_files(path: Path):
    if path.is_file():
        yield path
        return
    if path.is_dir():
        yield from (candidate for candidate in path.rglob("*") if candidate.is_file())


def main() -> int:
    paths = [candidate for root in TEXT_PATHS for candidate in iter_files(root)]
    violations = check_paths(paths)
    if violations:
        for path, characters in violations:
            codes = ", ".join(f"U+{ord(character):04X}" for character in characters)
            print(f"{path.relative_to(ROOT)}: forbidden characters: {codes}")
        return 1
    print(f"Text policy passed for {len(paths)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
