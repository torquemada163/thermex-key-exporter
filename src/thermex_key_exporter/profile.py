"""Configuration for a branded Thermex/Tuya SDK profile."""

from __future__ import annotations

from dataclasses import dataclass

from .signing import (
    build_sdk_master_secret,
    derive_sdk_ch_key,
    derive_sdk_response_key,
    derive_sdk_signing_key,
)


@dataclass(frozen=True, slots=True, repr=False)
class SdkProfile:
    """Non-user configuration required to prepare OEM cloud requests.

    A profile contains app-level material only. User credentials, QR tokens,
    sessions, and device keys must never be put in this object or persisted by
    it.
    """

    app_id: str
    app_secret: str
    certificate_sha256: str
    bitmap_token: str
    package_name: str
    app_version: str
    sdk_version: str = "5.18.0"
    device_core_version: str | None = None
    app_rn_version: str = "5.88"
    api_url: str = "https://a1.tuyaeu.com/api.json"
    language: str = "ru"
    operating_system: str = "Android"
    os_system: str = "14"
    platform: str = "Thermex Key Exporter"
    time_zone_id: str = "UTC"
    sdk_int: str = "34"
    brand: str = "Android"
    channel: str = "oem"
    ttid: str | None = None
    ch_key: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "app_id",
            "app_secret",
            "certificate_sha256",
            "bitmap_token",
            "package_name",
            "app_version",
            "sdk_version",
            "app_rn_version",
            "api_url",
            "language",
            "operating_system",
            "os_system",
            "platform",
            "time_zone_id",
            "sdk_int",
            "brand",
            "channel",
        ):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        if self.device_core_version is not None and not self.device_core_version.strip():
            raise ValueError("device_core_version must be non-empty when provided")
        if self.ttid is not None and not self.ttid.strip():
            raise ValueError("ttid must be non-empty when provided")
        if self.ch_key is not None and not self.ch_key.strip():
            raise ValueError("ch_key must be non-empty when provided")
        if self.ch_key is None:
            object.__setattr__(
                self,
                "ch_key",
                derive_sdk_ch_key(self.app_id, self.certificate_sha256, self.package_name),
            )
        if self.device_core_version is None:
            object.__setattr__(self, "device_core_version", self.sdk_version)
        if self.ttid is None:
            object.__setattr__(self, "ttid", f"sdk_international@{self.app_id}")

    def __repr__(self) -> str:
        """Avoid including app-level credentials in diagnostic output."""
        return (
            "SdkProfile("
            f"package_name={self.package_name!r}, app_version={self.app_version!r}, "
            "app_id=<redacted>, app_secret=<redacted>)"
        )

    @property
    def master_secret(self) -> str:
        """Return the derived SDK master-secret string in memory only."""
        return build_sdk_master_secret(
            self.certificate_sha256,
            self.bitmap_token,
            self.app_secret,
            package_name=self.package_name,
        )

    @property
    def signing_key(self) -> bytes:
        """Return the derived HMAC key in memory only."""
        return derive_sdk_signing_key(
            self.certificate_sha256,
            self.bitmap_token,
            self.app_secret,
            package_name=self.package_name,
        )

    def response_key(self, request_id: str, ecode: str | None = None) -> bytes:
        """Derive the per-request response encryption key."""
        return derive_sdk_response_key(self.master_secret, request_id, ecode)

    @property
    def user_agent(self) -> str:
        """Return the User-Agent format used by the branded Android SDK."""
        return f"Thing-UA=APP/Android/{self.app_version}/SDK/{self.sdk_version}"
