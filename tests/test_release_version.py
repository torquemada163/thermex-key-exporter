from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts import check_release_version


def test_release_version_check_accepts_the_matching_current_version(monkeypatch) -> None:
    def run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        if command[:3] == ["git", "cat-file", "-t"]:
            return SimpleNamespace(stdout="tag\n")
        if command[:3] == ["git", "rev-list", "-n"]:
            return SimpleNamespace(stdout="matching-commit\n")
        if command == ["git", "rev-parse", "HEAD"]:
            return SimpleNamespace(stdout="matching-commit\n")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(check_release_version.subprocess, "run", run)

    assert check_release_version.main(["--tag", "v0.1.0"]) == 0


def test_release_version_check_rejects_a_tag_for_a_different_version() -> None:
    assert check_release_version.main(["--tag", "v0.1.1"]) == 1


def test_release_version_check_rejects_a_lightweight_tag(monkeypatch) -> None:
    def run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        if command[:3] == ["git", "cat-file", "-t"]:
            return SimpleNamespace(stdout="commit\n")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(check_release_version.subprocess, "run", run)

    assert check_release_version.main(["--tag", "v0.1.0"]) == 1


def test_release_version_check_rejects_unreleased_changelog_entries() -> None:
    with pytest.raises(ValueError, match="still contains unreleased"):
        check_release_version._assert_no_unreleased_changes(
            "## Unreleased\n\n- Not released yet.\n"
        )
