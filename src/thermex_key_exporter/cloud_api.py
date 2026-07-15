"""Thermex OEM API constants and response-shape parsing."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

QR_TOKEN_CREATE_API = ("thing.m.user.qr.token.create", "1.0")
QR_TOKEN_POLL_API = ("thing.m.user.qr.token.user.get", "1.0")
DEVICE_HOMES_API = ("m.life.group.location.list", "7.0")
DEVICE_LIST_API = ("m.life.my.group.device.list", "2.2")
DEVICE_KEY_API = ("thing.m.device.key.get", "1.0")
PRODUCT_SCHEMA_API = ("thing.m.product.standard.config.list", "1.0")


def normalize_api_name(api_name: str) -> str:
    """Apply the OEM SDK's ``thing`` to ``smartlife`` API alias."""
    if not api_name.strip():
        raise ValueError("API name must not be empty")
    return api_name.replace("thing", "smartlife", 1) if api_name.startswith("thing") else api_name


class CloudError(RuntimeError):
    """Raised for an API or protocol error."""


class QrState(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"


@dataclass(frozen=True, slots=True)
class QrPollResult:
    state: QrState
    sid: str | None = None
    ecode: str | None = None


def parse_json_payload(raw: bytes) -> dict[str, Any]:
    """Decode a UTF-8 JSON object returned by the cloud endpoint."""
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CloudError("cloud API returned invalid JSON") from error
    if not isinstance(value, dict):
        raise CloudError("cloud API returned a non-object JSON value")
    return value


def result_value(response: Mapping[str, Any]) -> Any:
    """Decode the API's result field when it contains a JSON string."""
    value = response.get("result")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def require_success(response: Mapping[str, Any]) -> Any:
    """Validate an API envelope and return its decoded result."""
    if not response.get("success", False):
        code = response.get("errorCode") or "UNKNOWN"
        message = response.get("errorMsg") or "request failed"
        raise CloudError(f"{code}: {message}")
    return result_value(response)


def as_record_list(value: Any) -> list[dict[str, Any]]:
    """Normalize common list wrappers used by Thermex/Tuya endpoints."""
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ("list", "data", "deviceList", "homeList", "devices", "homes"):
            nested = value.get(key)
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
        if any(key in value for key in ("localKey", "local_key", "devId", "gwId", "gid", "id")):
            return [dict(value)]
    return []


def parse_qr_poll_result(value: Any) -> QrPollResult:
    """Normalize the OEM API's pending and confirmed response shapes."""
    if value in (None, "", {}, False, 0, True):
        return QrPollResult(QrState.PENDING)
    if not isinstance(value, dict):
        raise CloudError("QR polling returned an unknown response shape")
    sid = value.get("sid")
    if not sid:
        raise CloudError("QR polling returned a response without a session")
    ecode = value.get("ecode")
    return QrPollResult(QrState.CONFIRMED, str(sid), str(ecode) if ecode else None)
