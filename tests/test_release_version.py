from __future__ import annotations

from types import SimpleNamespace

from scripts import check_release_version


def test_release_version_check_accepts_the_matching_current_version(monkeypatch) -> None:
    def run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        if command[:3] == ["git", "rev-list", "-n"]:
            return SimpleNamespace(stdout="matching-commit\n")
        if command == ["git", "rev-parse", "HEAD"]:
            return SimpleNamespace(stdout="matching-commit\n")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(check_release_version.subprocess, "run", run)

    assert check_release_version.main(["--tag", "v0.1.0"]) == 0


def test_release_version_check_rejects_a_tag_for_a_different_version() -> None:
    assert check_release_version.main(["--tag", "v0.1.1"]) == 1
