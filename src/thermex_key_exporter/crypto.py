"""Portable cryptographic primitives used by the Thermex cloud protocol."""

from __future__ import annotations

import base64
import gzip
import hashlib
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class CryptoError(ValueError):
    """Raised when an encrypted Thermex value cannot be decoded."""


def md5_hex(value: str | bytes) -> str:
    """Return the lowercase MD5 digest used by the legacy API."""
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.md5(data).hexdigest()


def encrypt_gcm(key: bytes, plaintext: bytes, nonce: bytes | None = None) -> bytes:
    """Encrypt bytes using the Android-compatible nonce || ciphertext format."""
    if len(key) not in (16, 24, 32):
        raise CryptoError("AES-GCM key must be 16, 24, or 32 bytes")
    if nonce is None:
        nonce = secrets.token_bytes(12)
    if len(nonce) != 12:
        raise CryptoError("AES-GCM nonce must be 12 bytes")
    return nonce + AESGCM(key).encrypt(nonce, plaintext, None)


def decrypt_gcm(key: bytes, encrypted: bytes) -> bytes:
    """Decrypt bytes in the Android-compatible nonce || ciphertext format."""
    if len(key) not in (16, 24, 32):
        raise CryptoError("AES-GCM key must be 16, 24, or 32 bytes")
    if len(encrypted) < 12 + 16:
        raise CryptoError("encrypted value is too short")
    nonce, payload = encrypted[:12], encrypted[12:]
    try:
        return AESGCM(key).decrypt(nonce, payload, None)
    except InvalidTag as error:
        raise CryptoError("AES-GCM authentication failed") from error


def decrypt_response_base64(key: bytes, value: str) -> bytes:
    """Decode, decrypt, and optionally gunzip a Thermex response value."""
    try:
        encrypted = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as error:
        raise CryptoError("response is not valid base64") from error
    plaintext = decrypt_gcm(key, encrypted)
    if plaintext[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(plaintext)
        except OSError as error:
            raise CryptoError("gzip response could not be decompressed") from error
    return plaintext
