from __future__ import annotations

import pytest

from thermex_key_exporter.apk_profile import (
    ProfileExtractionError,
    _java_string_hash,
    _parse_android_manifest,
    _select_oem_identity,
)


def test_plain_android_manifest_is_read() -> None:
    manifest = b"""<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="com.example.thermex" android:versionName="1.2.3"/>"""

    assert _parse_android_manifest(manifest) == ("com.example.thermex", "1.2.3")


def test_oem_identity_is_selected_only_when_unambiguous() -> None:
    app_id, app_secret = _select_oem_identity(["ignore", "a" * 20, "b" * 32])

    assert app_id == "a" * 20
    assert app_secret == "b" * 32


def test_oem_identity_rejects_ambiguous_candidates() -> None:
    with pytest.raises(ProfileExtractionError, match="unambiguous"):
        _select_oem_identity(["a" * 20, "c" * 20, "b" * 32])


def test_java_string_hash_matches_java_semantics() -> None:
    assert _java_string_hash("abc") == 96_354
