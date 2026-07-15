"""Pure-Python request-signing material used by the Thermex OEM API."""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping

from .crypto import md5_hex

FIELD_SEPARATOR = "||"
PAIR_SEPARATOR = "="

# This is the field allow-list used by ThingApiSignManager.generateSignatureSdk.
# The final digest is still produced by the SDK's native security library and is
# intentionally not guessed here.
SIGNATURE_FIELDS = frozenset(
    {
        "a",
        "v",
        "lat",
        "lon",
        "lang",
        "deviceId",
        "appVersion",
        "ttid",
        "isH5",
        "h5Token",
        "os",
        "clientId",
        "postData",
        "time",
        "requestId",
        "et",
        "n4h5",
        "sid",
        "chKey",
        "sp",
    }
)


def swap_sign_string(value: str) -> str:
    """Apply the SDK's 8/8/8/8 MD5 block permutation."""
    if len(value) != 32:
        raise ValueError("sign string must contain exactly 32 characters")
    return value[8:16] + value[0:8] + value[24:32] + value[16:24]


def post_data_md5_hex(value: str) -> str:
    """Return the SDK representation of a non-empty ``post`` value."""
    if not value:
        return ""
    return swap_sign_string(md5_hex(value))


def build_signature_material(params: Mapping[str, object]) -> str:
    """Build the exact pre-native string passed to the SDK digest function.

    Empty values and fields outside the SDK allow-list are omitted. The input
    mapping is never modified; the Android implementation mutates its local
    map while normalizing ``postData``, which is not useful for a portable client.
    """
    pairs: list[str] = []
    for key in sorted(params):
        if key not in SIGNATURE_FIELDS:
            continue
        value = params[key]
        if value is None:
            continue
        text = str(value)
        if not text:
            continue
        if key == "postData":
            text = post_data_md5_hex(text)
        pairs.append(f"{key}{PAIR_SEPARATOR}{text}")
    return FIELD_SEPARATOR.join(pairs)


def build_request_cache_material(params: Mapping[str, object]) -> str:
    """Build the sorted all-field string used for the SDK request cache key."""
    pairs: list[str] = []
    for key in sorted(params):
        value = params[key]
        if value is None:
            continue
        text = str(value)
        if text:
            pairs.append(f"{key}{PAIR_SEPARATOR}{text}")
    return FIELD_SEPARATOR.join(pairs)


def request_cache_key(params: Mapping[str, object]) -> str:
    """Return the SDK request cache key for a parameter mapping."""
    return md5_hex(build_request_cache_material(params))


def build_sdk_master_secret(
    certificate_sha256: str,
    bitmap_token: str,
    app_secret: str,
    *,
    package_name: str | None = None,
) -> str:
    """Build the SDK master-secret string from an app profile.

    Current branded SDK builds prepend the Android package name. Older builds
    omit it, so callers can leave ``package_name`` unset when using that
    profile format. The values are intentionally supplied by the caller and
    are never logged or persisted by this module.
    """
    parts = [certificate_sha256, bitmap_token, app_secret]
    if package_name:
        parts.insert(0, package_name)
    if any(not part for part in parts):
        raise ValueError("SDK master-secret components must be non-empty")
    return "_".join(parts)


def derive_sdk_signing_key(
    certificate_sha256: str,
    bitmap_token: str,
    app_secret: str,
    *,
    package_name: str | None = None,
) -> bytes:
    """Derive the 32-byte HMAC key used by the native SDK signer."""
    master_secret = build_sdk_master_secret(
        certificate_sha256,
        bitmap_token,
        app_secret,
        package_name=package_name,
    )
    return hashlib.sha256(master_secret.encode("utf-8")).digest()


def derive_sdk_ch_key(
    app_id: str,
    certificate_sha256: str,
    package_name: str,
) -> str:
    """Derive the SDK's eight-character ``chKey`` query parameter.

    The native SDK computes an HMAC-SHA256 with the branded app ID as the key
    and ``package_name`` plus the signing-certificate fingerprint as the
    message. Its query parameter is the hexadecimal digest window at offsets
    8 through 15.
    """
    if not app_id or not certificate_sha256 or not package_name:
        raise ValueError("app ID, certificate fingerprint, and package name must be non-empty")
    digest = hmac.new(
        app_id.encode("utf-8"),
        f"{package_name}_{certificate_sha256}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return digest[8:16]


def sign_request_material(material: str, signing_key: bytes) -> str:
    """Return the lowercase HMAC-SHA256 digest for a prepared material string."""
    if not signing_key:
        raise ValueError("signing key must not be empty")
    return hmac.new(signing_key, material.encode("utf-8"), hashlib.sha256).hexdigest()


def sign_request(
    params: Mapping[str, object],
    signing_key: bytes,
) -> str:
    """Build and sign the request material without mutating ``params``."""
    return sign_request_material(build_signature_material(params), signing_key)


def derive_sdk_response_key(
    master_secret: str,
    request_id: str,
    ecode: str | None = None,
) -> bytes:
    """Derive the ASCII AES key used for an encrypted API response."""
    if not master_secret or not request_id:
        raise ValueError("master secret and request ID must not be empty")
    suffix = f"_{ecode}" if ecode else ""
    digest = hmac.new(
        request_id.encode("utf-8"),
        (master_secret + suffix).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest[:16].encode("ascii")
