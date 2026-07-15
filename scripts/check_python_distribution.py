#!/usr/bin/env python3
"""Verify release Python artifacts and optionally smoke-test them through pipx."""

from __future__ import annotations

import argparse
import configparser
import os
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from email.parser import BytesParser
from email.policy import default
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "thermex-key-exporter"
PROFILE_WHEEL_PATH = "thermex_key_exporter/data/thermex-profile.json"
FORBIDDEN_PATH_PARTS = frozenset({"private", "secrets", "__pycache__"})
FORBIDDEN_SUFFIXES = (".aab", ".apk", ".dex", ".pcap", ".pcapng")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect a Thermex Python sdist/wheel and smoke-test pipx installation."
    )
    parser.add_argument(
        "--dist-dir",
        type=Path,
        default=ROOT / "dist" / "python",
        help="directory containing exactly one wheel and one sdist",
    )
    parser.add_argument(
        "--expect-profile",
        action="store_true",
        help="require profile-status to pass after each pipx installation",
    )
    parser.add_argument(
        "--pipx",
        action="store_true",
        help="install both artifacts into fresh isolated pipx environments",
    )
    return parser


def _project_version() -> str:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return metadata["project"]["version"]


def _artifacts(dist_dir: Path) -> tuple[Path, Path]:
    dist_dir = dist_dir.expanduser().resolve()
    wheels = sorted(dist_dir.glob("*.whl"))
    sdists = sorted(dist_dir.glob("*.tar.gz"))
    unexpected = [
        path for path in dist_dir.iterdir() if path.is_file() and path not in {*wheels, *sdists}
    ]
    if len(wheels) != 1 or len(sdists) != 1 or unexpected:
        raise ValueError(
            "distribution directory must contain exactly one wheel and one .tar.gz sdist"
        )
    return wheels[0], sdists[0]


def _wheel_members(wheel: Path) -> list[str]:
    with zipfile.ZipFile(wheel) as archive:
        return archive.namelist()


def _sdist_members(sdist: Path) -> list[str]:
    with tarfile.open(sdist, "r:gz") as archive:
        return [member.name for member in archive.getmembers() if member.isfile()]


def _assert_safe_member_paths(members: list[str], *, artifact: Path) -> None:
    for member in members:
        member_path = Path(member)
        if FORBIDDEN_PATH_PARTS.intersection(member_path.parts):
            raise ValueError(f"{artifact.name} contains a forbidden path")
        if member.lower().endswith(FORBIDDEN_SUFFIXES):
            raise ValueError(f"{artifact.name} contains a forbidden binary input")
        if "PIL" in member_path.parts:
            raise ValueError(f"{artifact.name} unexpectedly bundles Pillow")


def _assert_wheel_metadata(wheel: Path, version: str) -> None:
    with zipfile.ZipFile(wheel) as archive:
        metadata_name = next(
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        )
        entry_points_name = next(
            name for name in archive.namelist() if name.endswith(".dist-info/entry_points.txt")
        )
        metadata = BytesParser(policy=default).parsebytes(archive.read(metadata_name))
        entry_points = archive.read(entry_points_name).decode("utf-8")

    if metadata["Name"] != PACKAGE_NAME or metadata["Version"] != version:
        raise ValueError("wheel metadata does not match the project version")
    requirements = metadata.get_all("Requires-Dist", [])
    for dependency in ("certifi", "cryptography", "qrcode"):
        if not any(requirement.lower().startswith(dependency) for requirement in requirements):
            raise ValueError(f"wheel metadata is missing the {dependency} dependency")
    if any(
        requirement.lower().startswith("pillow") and "extra ==" not in requirement.lower()
        for requirement in requirements
    ):
        raise ValueError("wheel metadata makes Pillow a default dependency")

    parser = configparser.ConfigParser()
    parser.read_string(entry_points)
    console_scripts = dict(parser["console_scripts"])
    if console_scripts != {"thermex-key-exporter": "thermex_key_exporter.cli:main"}:
        raise ValueError("wheel exposes unexpected console entry points")
    if parser.has_section("gui_scripts"):
        raise ValueError("wheel exposes a GUI entry point in the CLI distribution")


def _assert_artifact_contents(wheel: Path, sdist: Path) -> None:
    version = _project_version()
    expected_wheel_name = f"thermex_key_exporter-{version}-py3-none-any.whl"
    if wheel.name != expected_wheel_name:
        raise ValueError("wheel is not the expected pure-Python project artifact")
    if sdist.name != f"thermex_key_exporter-{version}.tar.gz":
        raise ValueError("source distribution filename does not match the project version")

    wheel_members = _wheel_members(wheel)
    sdist_members = _sdist_members(sdist)
    _assert_safe_member_paths(wheel_members, artifact=wheel)
    _assert_safe_member_paths(sdist_members, artifact=sdist)
    if wheel_members.count(PROFILE_WHEEL_PATH) != 1:
        raise ValueError("wheel does not contain exactly one bundled Thermex profile")
    profile_sdist_members = [
        member for member in sdist_members if member.endswith(f"/{PROFILE_WHEEL_PATH}")
    ]
    if len(profile_sdist_members) != 1:
        raise ValueError("source distribution does not contain exactly one bundled Thermex profile")
    required_sdist_members = ("LICENSE", "MANIFEST.in", "README.md", "pyproject.toml")
    missing_sdist_members = [
        name
        for name in required_sdist_members
        if not any(member.endswith(f"/{name}") for member in sdist_members)
    ]
    if missing_sdist_members:
        raise ValueError("source distribution is missing a required public build input")
    _assert_wheel_metadata(wheel, version)


def _run(command: list[str], *, env: dict[str, str], cwd: Path, check: bool = True) -> None:
    result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, check=False)
    if check and result.returncode:
        raise RuntimeError(
            f"command failed ({' '.join(command)}):\n{result.stdout}{result.stderr}".rstrip()
        )
    if not check and result.returncode == 0:
        raise RuntimeError(f"command unexpectedly succeeded: {' '.join(command)}")


def _pipx_executable(bin_dir: Path) -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    return bin_dir / f"thermex-key-exporter{suffix}"


def _smoke_test_pipx(artifact: Path, *, expect_profile: bool) -> None:
    with tempfile.TemporaryDirectory(prefix="thermex-pipx-") as temporary:
        temporary_path = Path(temporary)
        home = temporary_path / "home"
        bin_dir = temporary_path / "bin"
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment.pop("THERMEX_PROFILE_PATH", None)
        environment["PIPX_HOME"] = str(home)
        environment["PIPX_BIN_DIR"] = str(bin_dir)
        environment["PIPX_MAN_DIR"] = str(temporary_path / "man")
        environment["PIPX_DEFAULT_BACKEND"] = "pip"
        environment["PIP_CACHE_DIR"] = str(temporary_path / "pip-cache")
        environment["UV_CACHE_DIR"] = str(temporary_path / "uv-cache")
        _run(
            [
                sys.executable,
                "-m",
                "pipx",
                "install",
                "--force",
                "--python",
                sys.executable,
                str(artifact),
            ],
            env=environment,
            cwd=temporary_path,
        )
        executable = _pipx_executable(bin_dir)
        if not executable.is_file():
            raise RuntimeError("pipx did not expose the thermex-key-exporter command")
        _run([str(executable), "--version"], env=environment, cwd=temporary_path)
        _run([str(executable), "self-test"], env=environment, cwd=temporary_path)
        if expect_profile:
            _run([str(executable), "profile-status"], env=environment, cwd=temporary_path)
        _run(
            [sys.executable, "-m", "pipx", "runpip", PACKAGE_NAME, "check"],
            env=environment,
            cwd=temporary_path,
        )
        _run(
            [sys.executable, "-m", "pipx", "runpip", PACKAGE_NAME, "show", "Pillow"],
            env=environment,
            cwd=temporary_path,
            check=False,
        )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        wheel, sdist = _artifacts(args.dist_dir)
        _assert_artifact_contents(wheel, sdist)
        _run(
            [sys.executable, "-m", "twine", "check", "--strict", str(wheel), str(sdist)],
            env=os.environ.copy(),
            cwd=ROOT,
        )
        if args.pipx:
            _smoke_test_pipx(wheel, expect_profile=args.expect_profile)
            _smoke_test_pipx(sdist, expect_profile=args.expect_profile)
    except (
        OSError,
        RuntimeError,
        StopIteration,
        ValueError,
        zipfile.BadZipFile,
        tarfile.TarError,
    ) as error:
        print(f"Python distribution check failed: {error}", file=sys.stderr)
        return 1
    print("Python distribution checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
