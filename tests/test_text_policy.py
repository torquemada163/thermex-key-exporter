from pathlib import Path

from thermex_key_exporter.text_policy import check_paths, forbidden_characters


def test_text_policy_rejects_emoji_ranges() -> None:
    assert forbidden_characters("plain text") == []
    assert forbidden_characters("bad \U0001f600 text") == ["\U0001f600"]


def test_text_policy_reports_files(tmp_path: Path) -> None:
    clean = tmp_path / "clean.md"
    dirty = tmp_path / "dirty.md"
    clean.write_text("plain", encoding="utf-8")
    dirty.write_text("bad \U0001f600", encoding="utf-8")

    violations = check_paths([clean, dirty])

    assert violations == [(dirty, ["\U0001f600"])]
