from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import thermex_key_exporter.profile_bundle as profile_bundle
from thermex_key_exporter.profile import SdkProfile
from thermex_key_exporter.profile_bundle import (
    ProfileBundleError,
    load_bundled_profile,
    load_profile_bundle,
    write_profile_bundle,
)


def profile() -> SdkProfile:
    return SdkProfile(
        app_id="synthetic-app-id",
        app_secret="synthetic-app-secret",
        certificate_sha256="AA:BB:CC:DD",
        bitmap_token="bitmap-token",
        package_name="com.example.thermex",
        app_version="1.0.0",
    )


def test_profile_bundle_round_trip_is_private(tmp_path: Path) -> None:
    path = tmp_path / "thermex-profile.json"

    write_profile_bundle(profile(), path)

    assert load_profile_bundle(path) == profile()
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600


def test_bundled_profile_is_loaded_from_the_pyinstaller_data_path(tmp_path, monkeypatch) -> None:
    path = tmp_path / "thermex_key_exporter" / "data" / "thermex-profile.json"
    write_profile_bundle(profile(), path)
    monkeypatch.delenv("THERMEX_PROFILE_PATH", raising=False)
    monkeypatch.setattr(profile_bundle.sys, "_MEIPASS", str(tmp_path), raising=False)

    assert load_bundled_profile().app_version == "1.0.0"


def test_bundled_profile_uses_the_maintainer_override(tmp_path, monkeypatch) -> None:
    path = tmp_path / "maintainer-profile.json"
    write_profile_bundle(profile(), path)
    monkeypatch.setenv("THERMEX_PROFILE_PATH", str(path))

    assert load_bundled_profile() == profile()


def test_profile_bundle_rejects_unknown_fields(tmp_path: Path) -> None:
    path = tmp_path / "thermex-profile.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profile": {"app_id": "unexpected", "untrusted": "value"},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ProfileBundleError, match="unsupported"):
        load_profile_bundle(path)
