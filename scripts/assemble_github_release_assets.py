#!/usr/bin/env python3
"""Assemble verified native release assets from GitHub Actions artifacts."""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

CHECKSUM_FILENAME = "SHA256SUMS.txt"


@dataclass(frozen=True)
class PlatformArchive:
    platform: str
    filename: str


PLATFORM_ARCHIVES = (
    PlatformArchive("windows-x64", "thermex-key-exporter-windows-x64.zip"),
    PlatformArchive("macos-arm64", "thermex-key-exporter-macos-arm64.zip"),
    PlatformArchive("linux-x64", "thermex-key-exporter-linux-x64.tar.gz"),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _expected_checksum(manifest: Path, archive: PlatformArchive) -> str:
    lines = manifest.read_text(encoding="ascii").splitlines()
    if len(lines) != 1:
        raise ValueError(f"{manifest} must contain exactly one checksum")
    match = re.fullmatch(r"([0-9a-fA-F]{64})\s+\*?(.+)", lines[0])
    if match is None or match.group(2) != archive.filename:
        raise ValueError(f"{manifest} does not describe {archive.filename}")
    return match.group(1).lower()


def _validated_source(input_dir: Path, archive: PlatformArchive) -> tuple[Path, str]:
    source_dir = input_dir / archive.platform
    if not source_dir.is_dir():
        raise ValueError(f"missing downloaded artifact directory: {source_dir}")
    entries = sorted(source_dir.iterdir())
    expected_names = sorted((CHECKSUM_FILENAME, archive.filename))
    names_match = [entry.name for entry in entries] == expected_names
    if not names_match or not all(entry.is_file() for entry in entries):
        raise ValueError(
            f"{source_dir} must contain only {archive.filename} and {CHECKSUM_FILENAME}"
        )
    archive_path = source_dir / archive.filename
    expected_checksum = _expected_checksum(source_dir / CHECKSUM_FILENAME, archive)
    actual_checksum = _sha256(archive_path)
    if actual_checksum != expected_checksum:
        raise ValueError(f"checksum verification failed for {archive_path}")
    return archive_path, actual_checksum


def assemble_release_assets(input_dir: Path, output_dir: Path) -> tuple[Path, ...]:
    """Copy verified platform archives and create a canonical checksum manifest."""
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"refusing to reuse a non-empty output directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_archives: list[Path] = []
    checksum_rows: list[tuple[str, str]] = []
    for archive in PLATFORM_ARCHIVES:
        source, checksum = _validated_source(input_dir, archive)
        destination = output_dir / archive.filename
        shutil.copyfile(source, destination)
        if _sha256(destination) != checksum:
            raise RuntimeError(f"copied release asset did not preserve checksum: {destination}")
        output_archives.append(destination)
        checksum_rows.append((archive.filename, checksum))

    checksum_manifest = output_dir / CHECKSUM_FILENAME
    checksum_manifest.write_text(
        "".join(f"{checksum}  {filename}\n" for filename, checksum in sorted(checksum_rows)),
        encoding="ascii",
    )
    return (*output_archives, checksum_manifest)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        assets = assemble_release_assets(args.input_dir, args.output_dir)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"GitHub Release asset assembly failed: {error}", file=sys.stderr)
        return 1
    for asset in assets:
        print(asset)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
