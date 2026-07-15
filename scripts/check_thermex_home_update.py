#!/usr/bin/env python3
"""Check the public Thermex Home Google Play version for GitHub Actions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thermex_key_exporter.app_update import (  # noqa: E402
    AppUpdateCheckError,
    check_thermex_home_update,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare the verified Thermex profile with the Google Play listing."
    )
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument(
        "--github-output",
        type=Path,
        help="optional GitHub Actions output file; no profile data is written",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        status = check_thermex_home_update(timeout=args.timeout)
    except (AppUpdateCheckError, OSError, ValueError) as error:
        print(f"Thermex Home update check failed: {error}", file=sys.stderr)
        return 1
    result = {
        "verified_version": status.verified_version,
        "store_version": status.store_version,
        "update_available": status.update_available,
    }
    print(json.dumps(result, ensure_ascii=False))
    if args.github_output:
        _write_github_output(args.github_output, result)
    return 0


def _write_github_output(path: Path, result: dict[str, object]) -> None:
    """Append simple scalar results in GitHub Actions' output-file format."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as output:
        output.write(f"update_available={str(result['update_available']).lower()}\n")
        output.write(f"store_version={result['store_version']}\n")
        output.write(f"verified_version={result['verified_version']}\n")


if __name__ == "__main__":
    raise SystemExit(main())
