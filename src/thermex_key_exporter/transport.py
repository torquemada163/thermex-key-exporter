"""Offline request preparation and response decoding for the Thermex OEM API."""

from __future__ import annotations

import base64
import json
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .cloud_api import CloudError, normalize_api_name, parse_json_payload
from .crypto import decrypt_response_base64, encrypt_gcm, md5_hex
from .profile import SdkProfile
from .signing import sign_request


@dataclass(frozen=True, slots=True)
class PreparedRequest:
    """A request ready for an HTTP client or a deterministic unit test."""

    request_id: str
    response_key: bytes
    url: str
    headers: Mapping[str, str]
    params: Mapping[str, str]
    body: bytes


class CloudTransport:
    """Prepare, send, and decode read-only OEM cloud requests."""

    def __init__(
        self,
        profile: SdkProfile,
        *,
        device_id: str,
        now: Callable[[], float] = time.time,
        request_id_factory: Callable[[], str] | None = None,
        timeout: float = 20.0,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        if not device_id.strip():
            raise ValueError("device_id must not be empty")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.profile = profile
        self.device_id = device_id.strip()
        self._now = now
        self._request_id_factory = request_id_factory or (lambda: str(uuid.uuid4()))
        self._timeout = timeout
        self._opener = opener or urlopen

    def prepare(
        self,
        api_name: str,
        version: str,
        *,
        post_data: Mapping[str, object] | None = None,
        sid: str | None = None,
        ecode: str | None = None,
        gzip_response: bool = True,
    ) -> PreparedRequest:
        if not api_name.strip() or not version.strip():
            raise ValueError("API name and version must not be empty")
        api_name = normalize_api_name(api_name)
        request_id = self._request_id_factory()
        if not request_id.strip():
            raise ValueError("request ID factory returned an empty value")
        response_key = self.profile.response_key(request_id, ecode)
        params: dict[str, str] = {
            "a": api_name,
            "v": version,
            "appVersion": self.profile.app_version,
            "clientId": self.profile.app_id,
            "deviceId": self.device_id,
            "deviceCoreVersion": self.profile.device_core_version or self.profile.sdk_version,
            "lang": self.profile.language,
            "os": self.profile.operating_system,
            "osSystem": self.profile.os_system,
            "platform": self.profile.platform,
            "sdkVersion": self.profile.sdk_version,
            "requestId": request_id,
            "timeZoneId": self.profile.time_zone_id,
            "et": "3",
            "channel": self.profile.channel,
            "appRnVersion": self.profile.app_rn_version,
            "nd": "1",
            "bizData": json.dumps(
                {
                    "customDomainSupport": "1",
                    "nd": "1",
                    "sdkInt": self.profile.sdk_int,
                    "brand": self.profile.brand,
                },
                separators=(",", ":"),
            ),
        }
        if gzip_response:
            params["cp"] = "gzip"
        params["ttid"] = self.profile.ttid or ""
        params["chKey"] = self.profile.ch_key or ""
        if sid:
            params["sid"] = sid
        if post_data is not None:
            plaintext = json.dumps(
                post_data,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            params["postData"] = base64.b64encode(encrypt_gcm(response_key, plaintext)).decode(
                "ascii"
            )
        params["time"] = str(int(self._now() * 1000))
        params["sign"] = sign_request(params, self.profile.signing_key)
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": self.profile.user_agent,
            "Connection": "keep-alive",
        }
        return PreparedRequest(
            request_id,
            response_key,
            self.profile.api_url,
            headers,
            params,
            urlencode(params).encode("utf-8"),
        )

    def send(self, prepared: PreparedRequest) -> bytes:
        """Send one POST request with normal TLS verification from ``urllib``."""
        request = Request(
            prepared.url,
            data=prepared.body,
            headers=dict(prepared.headers),
            method="POST",
        )
        try:
            with self._opener(request, timeout=self._timeout) as response:
                return response.read()
        except HTTPError as error:
            raise CloudError(f"cloud API returned HTTP {error.code}") from error
        except URLError as error:
            raise CloudError("could not connect to the Thermex cloud API") from error

    def decode_response(
        self,
        raw: bytes,
        prepared: PreparedRequest,
        *,
        ecode: str | None = None,
    ) -> dict[str, object]:
        """Verify and decode an encrypted or plain API response."""
        envelope = parse_json_payload(raw)
        result = envelope.get("result")
        signature = envelope.get("sign")
        if signature and result is not None:
            if not isinstance(result, str):
                raise CloudError("cloud response result has an invalid type")
            response_key = self.profile.response_key(prepared.request_id, ecode)
            expected = md5_hex(
                f"result={result}||t={envelope.get('t', 0)}||{response_key.decode('ascii')}"
            )
            if str(signature).lower() != expected.lower():
                raise CloudError("cloud response signature verification failed")
            decoded = decrypt_response_base64(response_key, result)
            return parse_json_payload(decoded)
        return envelope
