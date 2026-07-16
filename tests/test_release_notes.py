from __future__ import annotations

import pytest

from scripts import extract_release_notes


def test_extract_release_notes_returns_only_the_requested_version_section() -> None:
    changelog = """# Changelog

## Unreleased

- Future work.

## 1.2.3 — 2026-07-16

- Added release automation.

## 1.2.2

- Previous release.
"""

    assert extract_release_notes.extract_release_notes(changelog, "1.2.3") == (
        "- Added release automation.\n"
    )


def test_extract_release_notes_rejects_a_missing_or_empty_version_section() -> None:
    with pytest.raises(ValueError, match="does not contain"):
        extract_release_notes.extract_release_notes("# Changelog\n", "1.2.3")
    with pytest.raises(ValueError, match="is empty"):
        extract_release_notes.extract_release_notes("## 1.2.3\n\n## 1.2.2\n", "1.2.3")
