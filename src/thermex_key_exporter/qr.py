"""Thermex Home OEM QR payload and terminal rendering helpers."""

from __future__ import annotations

from dataclasses import dataclass

import qrcode
from qrcode.constants import ERROR_CORRECT_Q

OEM_QR_LOGIN_PREFIX = "tuyaSmart--qrLogin?token="


@dataclass(frozen=True, slots=True)
class QrChallenge:
    """Short-lived challenge that must never be persisted."""

    token: str

    def __post_init__(self) -> None:
        if not self.token or any(character.isspace() for character in self.token):
            raise ValueError("QR token must be a non-empty value without whitespace")

    @property
    def payload(self) -> str:
        return f"{OEM_QR_LOGIN_PREFIX}{self.token}"


def render_terminal(challenge: QrChallenge) -> str:
    """Render a QR challenge suitable for a monochrome terminal window."""
    matrix = _make_code(challenge, box_size=1).get_matrix()
    return "\n".join("".join("██" if cell else "  " for cell in row) for row in matrix)


def _make_code(challenge: QrChallenge, box_size: int) -> qrcode.QRCode:
    code = qrcode.QRCode(
        error_correction=ERROR_CORRECT_Q,
        box_size=box_size,
        border=4,
    )
    code.add_data(challenge.payload)
    code.make(fit=True)
    return code
