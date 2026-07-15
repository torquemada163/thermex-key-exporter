"""Pillow-backed QR image rendering used only by the optional GUI."""

from __future__ import annotations

from io import BytesIO

from qrcode.image.pil import PilImage

from .qr import QrChallenge, _make_code


def render_png(challenge: QrChallenge, box_size: int = 10) -> bytes:
    """Render a QR challenge to PNG bytes with a reliable quiet zone."""
    if box_size < 1:
        raise ValueError("box_size must be positive")
    code = _make_code(challenge, box_size)
    image = code.make_image(
        image_factory=PilImage,
        fill_color="black",
        back_color="white",
    )
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()
