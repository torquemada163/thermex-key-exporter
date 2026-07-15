#!/usr/bin/env python3
"""Reject a PyPI release workflow run whose tag does not match project metadata."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify a release tag against project metadata.")
    parser.add_argument(
        "--tag",
        required=True,
        help="annotated or lightweight Git tag, for example v0.1.0",
    )
    return parser


def _project_version() -> str:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return metadata["project"]["version"]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        version = _project_version()
        expected_tag = f"v{version}"
        if args.tag != expected_tag:
            raise ValueError(f"release tag must be {expected_tag}, not {args.tag}")
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        if not re.search(rf"^## {re.escape(version)}(?:\s|$)", changelog, flags=re.MULTILINE):
            raise ValueError("CHANGELOG.md does not contain a section for the release version")
        subprocess.run(
            ["git", "rev-parse", "--verify", f"refs/tags/{args.tag}"],
            check=True,
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        tag_commit = subprocess.run(
            ["git", "rev-list", "-n", "1", args.tag],
            check=True,
            cwd=ROOT,
            text=True,
            capture_output=True,
        ).stdout.strip()
        head_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            cwd=ROOT,
            text=True,
            capture_output=True,
        ).stdout.strip()
        if tag_commit != head_commit:
            raise ValueError("checked-out revision does not match the requested release tag")
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Release version check failed: {error}", file=sys.stderr)
        return 1
    print(f"Release tag {args.tag} matches version {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
