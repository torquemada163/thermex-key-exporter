from __future__ import annotations

import hashlib

import pytest

from scripts import assemble_github_release_assets


def _write_source_artifact(root, archive, payload: bytes) -> None:
    source = root / archive.platform
    source.mkdir()
    archive_path = source / archive.filename
    archive_path.write_bytes(payload)
    checksum = hashlib.sha256(payload).hexdigest()
    (source / "SHA256SUMS.txt").write_text(f"{checksum}  {archive.filename}\n", encoding="ascii")


def _write_all_source_artifacts(root) -> None:
    for archive in assemble_github_release_assets.PLATFORM_ARCHIVES:
        _write_source_artifact(root, archive, archive.filename.encode("ascii"))


def test_assemble_release_assets_verifies_and_combines_all_platform_archives(tmp_path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    _write_all_source_artifacts(input_dir)
    output_dir = tmp_path / "output"

    assets = assemble_github_release_assets.assemble_release_assets(input_dir, output_dir)

    assert [path.name for path in assets] == [
        "thermex-key-exporter-windows-x64.zip",
        "thermex-key-exporter-macos-arm64.zip",
        "thermex-key-exporter-linux-x64.tar.gz",
        "SHA256SUMS.txt",
    ]
    checksum_lines = (output_dir / "SHA256SUMS.txt").read_text(encoding="ascii").splitlines()
    assert [line.rsplit("  ", maxsplit=1)[1] for line in checksum_lines] == sorted(
        archive.filename for archive in assemble_github_release_assets.PLATFORM_ARCHIVES
    )
    assert len(checksum_lines) == 3


def test_assemble_release_assets_rejects_a_missing_platform_artifact(tmp_path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    for archive in assemble_github_release_assets.PLATFORM_ARCHIVES[:2]:
        _write_source_artifact(input_dir, archive, archive.filename.encode("ascii"))

    with pytest.raises(ValueError, match="missing downloaded artifact directory"):
        assemble_github_release_assets.assemble_release_assets(input_dir, tmp_path / "output")


def test_assemble_release_assets_rejects_an_archive_with_the_wrong_checksum(tmp_path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    _write_all_source_artifacts(input_dir)
    archive = assemble_github_release_assets.PLATFORM_ARCHIVES[0]
    (input_dir / archive.platform / archive.filename).write_bytes(b"corrupted")

    with pytest.raises(ValueError, match="checksum verification failed"):
        assemble_github_release_assets.assemble_release_assets(input_dir, tmp_path / "output")
