#!/usr/bin/env python3
"""Build release-ready Python distributions without adding a profile to Git.

The public source tree intentionally excludes the Thermex profile.  This
maintainer-only tool creates a clean temporary source tree, injects one
validated profile as package data there, and asks PyPA build to create both an
sdist and a wheel.  The original checkout is never modified.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_RELATIVE_PATH = Path("src") / "thermex_key_exporter"
PROFILE_RELATIVE_PATH = PACKAGE_RELATIVE_PATH / "data" / "thermex-profile.json"
ROOT_FILES = ("LICENSE", "MANIFEST.in", "README.md", "pyproject.toml")

sys.path.insert(0, str(ROOT / "src"))

from thermex_key_exporter.app_update import VERIFIED_THERMEX_HOME_VERSION  # noqa: E402
from thermex_key_exporter.profile import SdkProfile  # noqa: E402
from thermex_key_exporter.profile_bundle import (  # noqa: E402
    ProfileBundleError,
    load_profile_bundle,
    write_profile_bundle,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build an sdist and wheel with an injected Thermex profile."
    )
    profile_source = parser.add_mutually_exclusive_group(required=True)
    profile_source.add_argument(
        "--profile",
        type=Path,
        help="validated private profile bundle to embed only in the temporary staging tree",
    )
    profile_source.add_argument(
        "--synthetic-profile",
        action="store_true",
        help="embed a non-working synthetic profile for CI packaging checks",
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=ROOT / "dist" / "python",
        help="directory for the resulting sdist and wheel (default: dist/python)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="remove previous wheel/sdist files from the output directory before building",
    )
    return parser


def _validated_profile(path: Path) -> Path:
    path = path.expanduser().resolve()
    try:
        profile = load_profile_bundle(path)
    except (OSError, ProfileBundleError) as error:
        raise ValueError("the requested release profile is unavailable or invalid") from error
    if profile.app_version != VERIFIED_THERMEX_HOME_VERSION:
        raise ValueError("the requested release profile does not match this release metadata")
    return path


def _write_synthetic_profile(path: Path) -> None:
    """Write a valid but deliberately non-working profile for CI-only checks."""
    write_profile_bundle(
        SdkProfile(
            app_id="synthetic-thermex-app-id",
            app_secret="synthetic-thermex-app-secret",
            certificate_sha256="AA:BB:CC:DD",
            bitmap_token="synthetic-bitmap-token",
            package_name="com.example.thermex",
            app_version=VERIFIED_THERMEX_HOME_VERSION,
        ),
        path,
    )


def _copy_public_source(staging_root: Path) -> None:
    """Copy only declared public build inputs into an otherwise empty staging tree."""
    for filename in ROOT_FILES:
        source = ROOT / filename
        if not source.is_file():
            raise RuntimeError(f"required build input is missing: {filename}")
        shutil.copy2(source, staging_root / filename)

    source_package = ROOT / PACKAGE_RELATIVE_PATH
    destination_package = staging_root / PACKAGE_RELATIVE_PATH
    for source in source_package.rglob("*.py"):
        destination = destination_package / source.relative_to(source_package)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    if not (destination_package / "__init__.py").is_file():
        raise RuntimeError("the public Python package is incomplete")


def _prepare_outdir(path: Path, *, clean: bool) -> Path:
    path = path.expanduser().resolve()
    if path.exists() and clean:
        for candidate in path.iterdir():
            is_distribution = candidate.suffix == ".whl" or candidate.name.endswith(".tar.gz")
            if candidate.is_file() and is_distribution:
                candidate.unlink()
            else:
                raise ValueError(f"refusing to clean an unexpected output path: {candidate}")
    if path.exists() and any(path.iterdir()):
        raise ValueError(f"output directory is not empty: {path}; use --clean to replace it")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _assert_expected_artifacts(outdir: Path) -> list[Path]:
    artifacts = sorted(path for path in outdir.iterdir() if path.is_file())
    wheels = [path for path in artifacts if path.suffix == ".whl"]
    sdists = [path for path in artifacts if path.name.endswith(".tar.gz")]
    if len(artifacts) != 2 or len(wheels) != 1 or len(sdists) != 1:
        raise RuntimeError("build did not produce exactly one wheel and one source distribution")
    return artifacts


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        outdir = _prepare_outdir(args.outdir, clean=args.clean)
        with tempfile.TemporaryDirectory(prefix="thermex-python-build-") as temporary:
            staging_root = Path(temporary) / "source"
            staging_root.mkdir()
            _copy_public_source(staging_root)
            staged_profile = staging_root / PROFILE_RELATIVE_PATH
            if args.synthetic_profile:
                _write_synthetic_profile(staged_profile)
            else:
                profile_path = _validated_profile(args.profile)
                staged_profile.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(profile_path, staged_profile)
            subprocess.run(
                [sys.executable, "-m", "build", "--outdir", str(outdir)],
                check=True,
                cwd=staging_root,
            )
        artifacts = _assert_expected_artifacts(outdir)
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Python distribution build failed: {error}", file=sys.stderr)
        return 1
    print("Built Python distributions:")
    for artifact in artifacts:
        print(artifact)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
