"""Validated data models used by the export and UI layers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


def utc_now() -> str:
    """Return an RFC 3339 UTC timestamp suitable for the export schema."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class DeviceRecord:
    """A device record that can be used to configure a local Tuya client."""

    name: str
    device_id: str
    local_key: str
    protocol_version: str | None = None
    product_id: str | None = None
    product_version: str | None = None
    local_ip: str | None = None
    ip_source: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("device name must not be empty")
        if not self.device_id.strip():
            raise ValueError("device_id must not be empty")
        if not self.local_key.strip():
            raise ValueError("local_key must not be empty")
        if self.ip_source not in (None, "local_udp", "manual"):
            raise ValueError("ip_source must be local_udp, manual, or null")
        if self.local_ip is None and self.ip_source is not None:
            raise ValueError("ip_source requires local_ip")

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> DeviceRecord:
        """Build a validated record from an API or JSON mapping."""
        return cls(
            name=str(value.get("name") or "Unnamed Thermex device"),
            device_id=str(value.get("device_id") or value.get("devId") or ""),
            local_key=str(value.get("local_key") or value.get("localKey") or ""),
            protocol_version=_optional_string(
                value.get("protocol_version") or value.get("protocolVersion") or value.get("pv")
            ),
            product_id=_optional_string(value.get("product_id") or value.get("productId")),
            product_version=_optional_string(
                value.get("product_version")
                or value.get("productVersion")
                or value.get("productVer")
            ),
            # Cloud API ``ip`` values are not trustworthy local LAN addresses.
            local_ip=_optional_string(value.get("local_ip")),
            ip_source=_optional_string(value.get("ip_source")),
        )

    def to_mapping(self) -> dict[str, str | None]:
        """Return the stable public JSON representation."""
        return {
            "name": self.name,
            "device_id": self.device_id,
            "local_key": self.local_key,
            "protocol_version": self.protocol_version,
            "product_id": self.product_id,
            "product_version": self.product_version,
            "local_ip": self.local_ip,
            "ip_source": self.ip_source,
        }


@dataclass(frozen=True, slots=True)
class ExportDocument:
    """Top-level versioned export document."""

    devices: tuple[DeviceRecord, ...]
    generated_at: str
    source: str = "Thermex Home"
    schema_version: int = 1

    @classmethod
    def create(cls, devices: list[DeviceRecord] | tuple[DeviceRecord, ...]) -> ExportDocument:
        if not devices:
            raise ValueError("at least one device is required")
        return cls(tuple(devices), utc_now())

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": self.source,
            "generated_at": self.generated_at,
            "devices": [device.to_mapping() for device in self.devices],
        }


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None
