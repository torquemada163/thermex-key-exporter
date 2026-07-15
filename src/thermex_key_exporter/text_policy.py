"""Repository text policy checks."""

from __future__ import annotations

from pathlib import Path

FORBIDDEN_RANGES = (
    (0x1F000, 0x1FAFF),
    (0x2600, 0x27BF),
    (0xFE0F, 0xFE0F),
)


def forbidden_characters(text: str) -> list[str]:
    """Return unique forbidden characters in first-seen order."""
    found: list[str] = []
    for character in text:
        codepoint = ord(character)
        if any(start <= codepoint <= end for start, end in FORBIDDEN_RANGES):
            if character not in found:
                found.append(character)
    return found


def check_paths(paths: list[Path]) -> list[tuple[Path, list[str]]]:
    """Return files that violate the no-emoji repository policy."""
    violations: list[tuple[Path, list[str]]] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        found = forbidden_characters(text)
        if found:
            violations.append((path, found))
    return violations
