#!/usr/bin/env python3
"""Extract one version's release notes from CHANGELOG.md."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def extract_release_notes(changelog: str, version: str) -> str:
    heading = re.compile(rf"^## {re.escape(version)}(?:[ \t].*)?$", flags=re.MULTILINE)
    match = heading.search(changelog)
    if match is None:
        raise ValueError(f"CHANGELOG.md does not contain a section for {version}")
    following_heading = re.compile(r"^## ", flags=re.MULTILINE).search(changelog, match.end())
    end = following_heading.start() if following_heading else None
    notes = changelog[match.end() : end].strip()
    if not notes:
        raise ValueError(f"CHANGELOG.md section {version} is empty")
    return f"{notes}\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--changelog", type=Path, default=ROOT / "CHANGELOG.md")
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        notes = extract_release_notes(args.changelog.read_text(encoding="utf-8"), args.version)
    except (OSError, ValueError) as error:
        print(f"Release notes extraction failed: {error}", file=sys.stderr)
        return 1
    if args.output:
        args.output.write_text(notes, encoding="utf-8")
    else:
        print(notes, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
