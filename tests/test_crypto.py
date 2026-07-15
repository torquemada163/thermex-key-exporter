import base64

import pytest

from thermex_key_exporter.crypto import (
    CryptoError,
    decrypt_gcm,
    decrypt_response_base64,
    encrypt_gcm,
)


def test_gcm_round_trip_with_fixed_nonce() -> None:
    key = bytes.fromhex("00112233445566778899aabbccddeeff")
    nonce = bytes.fromhex("000102030405060708090a0b")
    plaintext = b"thermex-test"

    encrypted = encrypt_gcm(key, plaintext, nonce)

    assert encrypted[:12] == nonce
    assert decrypt_gcm(key, encrypted) == plaintext


def test_response_base64_decode_and_gzip() -> None:
    key = bytes.fromhex("00112233445566778899aabbccddeeff")
    nonce = bytes.fromhex("000102030405060708090a0b")
    encrypted = encrypt_gcm(key, b"response", nonce)

    assert decrypt_response_base64(key, base64.b64encode(encrypted).decode()) == b"response"


def test_gcm_rejects_invalid_tag() -> None:
    key = bytes.fromhex("00112233445566778899aabbccddeeff")
    encrypted = encrypt_gcm(key, b"response", bytes.fromhex("000102030405060708090a0b"))
    corrupted = encrypted[:-1] + bytes([encrypted[-1] ^ 1])

    with pytest.raises(CryptoError):
        decrypt_gcm(key, corrupted)
