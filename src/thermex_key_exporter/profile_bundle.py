"""Private profile bundles used only while building a user-facing release.

The public source tree deliberately contains no Thermex application profile.
Maintainers derive a bundle from a current, user-supplied APK and provide it to
PyInstaller through ``THERMEX_PROFILE_PATH``.  The resulting distribution can
then run without asking its user for an APK.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import fields
from importlib.resources import as_file, files
from pathlib import Path

from .export import _atomic_write
from .profile import SdkProfile

_BUNDLE_SCHEMA_VERSION = 1
_BUNDLE_RELATIVE_PATH = Path("thermex_key_exporter") / "data" / "thermex-profile.json"
_PROFILE_FIELD_NAMES = tuple(field.name for field in fields(SdkProfile))
_PROFILE_FIELD_NAME_SET = frozenset(_PROFILE_FIELD_NAMES)


class ProfileBundleError(RuntimeError):
    """Raised when a private profile bundle is unavailable or invalid."""


def write_profile_bundle(profile: SdkProfile, path: Path) -> None:
    """Write an ignored, permission-restricted profile bundle for a release build."""
    mapping = {
        "schema_version": _BUNDLE_SCHEMA_VERSION,
        "profile": {name: getattr(profile, name) for name in _PROFILE_FIELD_NAMES},
    }
    _atomic_write(path, json.dumps(mapping, ensure_ascii=False, indent=2) + "\n")


def load_profile_bundle(path: Path) -> SdkProfile:
    """Load a profile bundle without logging its app-level material."""
    try:
        value = json.loads(path.expanduser().read_text(encoding="utf-8"))
    except OSError as error:
        raise ProfileBundleError("the bundled Thermex profile could not be read") from error
    except json.JSONDecodeError as error:
        raise ProfileBundleError("the bundled Thermex profile is not valid JSON") from error
    if not isinstance(value, dict) or value.get("schema_version") != _BUNDLE_SCHEMA_VERSION:
        raise ProfileBundleError("the bundled Thermex profile has an unsupported format")
    profile = value.get("profile")
    if not isinstance(profile, dict):
        raise ProfileBundleError("the bundled Thermex profile does not contain profile data")
    unknown = set(profile).difference(_PROFILE_FIELD_NAME_SET)
    if unknown:
        raise ProfileBundleError("the bundled Thermex profile contains unsupported fields")
    try:
        return SdkProfile(**profile)
    except (AttributeError, TypeError, ValueError) as error:
        raise ProfileBundleError("the bundled Thermex profile is invalid") from error


def load_bundled_profile() -> SdkProfile:
    """Load the profile embedded in this distribution or supplied for development.

    ``THERMEX_PROFILE_PATH`` is a maintainer-only override.  End users receive a
    profile from the PyInstaller or Python-package data directory and never need
    an APK file.
    """
    override = os.environ.get("THERMEX_PROFILE_PATH")
    if override:
        return load_profile_bundle(Path(override))
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return load_profile_bundle(Path(frozen_root) / _BUNDLE_RELATIVE_PATH)
    try:
        resource = files("thermex_key_exporter").joinpath("data", "thermex-profile.json")
        with as_file(resource) as profile_path:
            return load_profile_bundle(profile_path)
    except ModuleNotFoundError as error:
        raise ProfileBundleError("the bundled Thermex profile could not be read") from error
