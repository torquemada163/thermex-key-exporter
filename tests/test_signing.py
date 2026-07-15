import pytest

from thermex_key_exporter.signing import (
    build_request_cache_material,
    build_sdk_master_secret,
    build_signature_material,
    derive_sdk_ch_key,
    derive_sdk_response_key,
    derive_sdk_signing_key,
    post_data_md5_hex,
    request_cache_key,
    sign_request,
    sign_request_material,
    swap_sign_string,
)


def test_swap_sign_string_matches_sdk_block_permutation() -> None:
    value = "0123456789abcdef0123456789abcdef"

    assert swap_sign_string(value) == "89abcdef0123456789abcdef01234567"


def test_swap_sign_string_requires_a_md5_length_value() -> None:
    with pytest.raises(ValueError):
        swap_sign_string("short")


def test_post_data_md5_hex_has_a_stable_golden_vector() -> None:
    assert post_data_md5_hex("abc") == "3cd24fb09001509828e17f72d6963f7d"
    assert post_data_md5_hex("") == ""


def test_signature_material_filters_sorts_and_does_not_mutate() -> None:
    params = {
        "time": "123",
        "ignored": "not-signed",
        "postData": "abc",
        "clientId": "client",
        "a": "1",
        "empty": "",
    }

    assert build_signature_material(params) == (
        "a=1||clientId=client||postData=3cd24fb09001509828e17f72d6963f7d||time=123"
    )
    assert params["postData"] == "abc"


def test_request_cache_key_uses_all_non_empty_sorted_fields() -> None:
    params = {"z": "last", "a": "first", "empty": ""}

    assert build_request_cache_material(params) == "a=first||z=last"
    assert request_cache_key(params) == "1dde398e3a9da37c7164ab177312cefd"


def test_sdk_signing_key_and_hmac_have_a_golden_vector() -> None:
    key = derive_sdk_signing_key(
        "AA:BB:CC:DD",
        "bitmap-token",
        "app-secret",
        package_name="com.example.thermex",
    )

    assert key.hex() == "f674ce1cc33e3dada8386dbf23f308d3b7c38145f397a4bbff49e65bb432c98a"
    assert sign_request_material("a=1||time=123", key) == (
        "1b0b2fa1a9bb9615d1c13d2bd2a8f6ee0bac06ef6ac1dc1174ec5fc1056a39be"
    )


def test_sdk_ch_key_has_a_native_verified_hmac_window() -> None:
    assert (
        derive_sdk_ch_key(
            "synthetic-app-id",
            "AA:BB:CC:DD",
            "com.example.thermex",
        )
        == "6dc879c3"
    )


def test_sign_request_uses_prepared_material() -> None:
    key = b"synthetic-signing-key"
    params = {"time": "123", "a": "1", "postData": "abc"}

    assert sign_request(params, key) == (
        "ff0f69f724fe6352eafec717f08aa905f15d6ddcf178114b44b2d43900cc3e83"
    )
    assert params["postData"] == "abc"


def test_sdk_response_key_has_a_golden_vector() -> None:
    master_secret = build_sdk_master_secret(
        "AA:BB:CC:DD",
        "bitmap-token",
        "app-secret",
        package_name="com.example.thermex",
    )

    assert derive_sdk_response_key(master_secret, "request-id", "ecode") == (b"6da056bfd9173682")
    assert derive_sdk_response_key(master_secret, "request-id") == (b"a82a8b50bae63fa6")
