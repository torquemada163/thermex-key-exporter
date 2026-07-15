"""High-level Thermex cloud operation shapes for a validated future backend."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .cloud_api import (
    CloudError,
    QrPollResult,
    QrState,
    as_record_list,
    parse_qr_poll_result,
    require_success,
)
from .models import DeviceRecord
from .transport import CloudTransport


class ThermexCloudClient:
    """In-memory QR-session logic for read-only Thermex cloud operations."""

    def __init__(self, transport: CloudTransport) -> None:
        self.transport = transport
        self.sid: str | None = None
        self.ecode: str | None = None

    def request(
        self,
        api_name: str,
        version: str,
        *,
        post_data: Mapping[str, object] | None = None,
        authenticated: bool = False,
    ) -> Any:
        if authenticated and not self.sid:
            raise CloudError("authenticated request requires a confirmed QR session")
        prepared = self.transport.prepare(
            api_name,
            version,
            post_data=post_data,
            sid=self.sid if authenticated else None,
            ecode=self.ecode if authenticated else None,
        )
        raw = self.transport.send(prepared)
        response = self.transport.decode_response(
            raw,
            prepared,
            ecode=self.ecode if authenticated else None,
        )
        return require_success(response)

    def create_qr_token(self) -> str:
        """Create a short-lived OEM QR token without persisting it."""
        value = self.request("thing.m.user.qr.token.create", "1.0")
        if not isinstance(value, str) or not value:
            raise CloudError("OEM QR API returned an invalid token")
        return value

    def poll_qr(self, token: str) -> QrPollResult:
        """Poll a QR token and store a confirmed session only in memory."""
        if not token or any(character.isspace() for character in token):
            raise ValueError("QR token must be a non-empty value without whitespace")
        value = self.request(
            "thing.m.user.qr.token.user.get",
            "1.0",
            post_data={"token": token},
        )
        result = parse_qr_poll_result(value)
        if result.state == QrState.CONFIRMED:
            self.sid = result.sid
            self.ecode = result.ecode
        return result

    def list_homes(self) -> list[dict[str, Any]]:
        """Return homes visible to the authenticated account."""
        value = self.request("m.life.group.location.list", "7.0", authenticated=True)
        return as_record_list(value)

    def list_devices(self, home_id: int | str) -> list[dict[str, Any]]:
        """Return devices for one home without issuing control commands."""
        if str(home_id).strip() == "":
            raise ValueError("home ID must not be empty")
        value = self.request(
            "m.life.my.group.device.list",
            "2.2",
            post_data={"gid": int(home_id)},
            authenticated=True,
        )
        return as_record_list(value)

    def get_device_keys(self, device_id: str) -> list[dict[str, Any]]:
        """Return key records for one device without changing device state."""
        if not device_id.strip():
            raise ValueError("device ID must not be empty")
        value = self.request(
            "thing.m.device.key.get",
            "1.0",
            post_data={"gwId": device_id},
            authenticated=True,
        )
        return as_record_list(value)

    def collect_device_records(self) -> list[DeviceRecord]:
        """Read homes, devices, and keys without sending device-control commands."""
        records: list[DeviceRecord] = []
        for home in self.list_homes():
            home_id = home.get("gid") or home.get("id")
            if home_id is None:
                continue
            for device in self.list_devices(home_id):
                device_id = str(device.get("devId") or device.get("gwId") or "").strip()
                if not device_id:
                    continue
                local_key = next(
                    (
                        str(key.get("localKey") or key.get("local_key") or "").strip()
                        for key in self.get_device_keys(device_id)
                        if str(key.get("localKey") or key.get("local_key") or "").strip()
                    ),
                    "",
                )
                if not local_key:
                    continue
                record_data = dict(device)
                record_data["localKey"] = local_key
                try:
                    records.append(DeviceRecord.from_mapping(record_data))
                except ValueError as error:
                    raise CloudError(
                        "cloud device data could not be converted to an export record"
                    ) from error
        if not records:
            raise CloudError("no devices with local keys were returned by Thermex Home")
        return records
