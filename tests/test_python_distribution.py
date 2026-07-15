from __future__ import annotations

import pytest

from scripts import build_python_distribution
from thermex_key_exporter.app_update import VERIFIED_THERMEX_HOME_VERSION
from thermex_key_exporter.profile_bundle import load_profile_bundle


def test_synthetic_distribution_profile_is_valid_and_matches_the_release(tmp_path) -> None:
    profile_path = tmp_path / "thermex-profile.json"

    build_python_distribution._write_synthetic_profile(profile_path)

    assert load_profile_bundle(profile_path).app_version == VERIFIED_THERMEX_HOME_VERSION


def test_distribution_staging_copies_only_declared_public_package_sources(tmp_path) -> None:
    staging_root = tmp_path / "staging"
    staging_root.mkdir()

    build_python_distribution._copy_public_source(staging_root)

    assert (staging_root / "pyproject.toml").is_file()
    assert (staging_root / "src" / "thermex_key_exporter" / "cli.py").is_file()
    assert not (staging_root / "src" / "thermex_key_exporter" / "data").exists()


def test_distribution_clean_removes_only_previous_distribution_artifacts(tmp_path) -> None:
    outdir = tmp_path / "dist"
    outdir.mkdir()
    (outdir / "thermex_key_exporter-0.1.0-py3-none-any.whl").write_text("wheel")
    (outdir / "thermex_key_exporter-0.1.0.tar.gz").write_text("sdist")

    assert build_python_distribution._prepare_outdir(outdir, clean=True) == outdir
    assert not list(outdir.iterdir())


def test_distribution_clean_refuses_to_delete_unexpected_output(tmp_path) -> None:
    outdir = tmp_path / "dist"
    outdir.mkdir()
    (outdir / "notes.txt").write_text("keep")

    with pytest.raises(ValueError, match="refusing"):
        build_python_distribution._prepare_outdir(outdir, clean=True)
