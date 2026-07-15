import json
from collections import deque

import pytest

from thermex_key_exporter.client import ThermexCloudClient
from thermex_key_exporter.cloud_api import CloudError, QrState
from thermex_key_exporter.profile import SdkProfile
from thermex_key_exporter.transport import CloudTransport, PreparedRequest


class FakeTransport(CloudTransport):
    def __init__(self, responses: list[dict[str, object]]) -> None:
        super().__init__(
            SdkProfile(
                app_id="app-id",
                app_secret="app-secret",
                certificate_sha256="AA:BB",
                bitmap_token="token",
                package_name="com.example.app",
                app_version="1.0",
            ),
            device_id="device-id",
            request_id_factory=lambda: "request-id",
        )
        self.responses = deque(responses)
        self.calls: list[tuple[str, str, dict[str, object] | None, str | None]] = []

    def send(self, prepared: PreparedRequest) -> bytes:
        return json.dumps(self.responses.popleft()).encode("utf-8")

    def prepare(self, api_name: str, version: str, **kwargs: object) -> PreparedRequest:
        self.calls.append((api_name, version, kwargs.get("post_data"), kwargs.get("sid")))
        return super().prepare(api_name, version, **kwargs)


def test_qr_client_creates_and_confirms_session_in_memory() -> None:
    transport = FakeTransport(
        [
            {"success": True, "result": "one-time-token"},
            {"success": True, "result": {"sid": "sid-value", "ecode": "ecode-value"}},
        ]
    )
    client = ThermexCloudClient(transport)

    token = client.create_qr_token()
    pending = client.poll_qr(token)

    assert token == "one-time-token"
    assert pending.state == QrState.CONFIRMED
    assert client.sid == "sid-value"
    assert client.ecode == "ecode-value"
    assert transport.calls[1][2] == {"token": "one-time-token"}


def test_qr_client_keeps_pending_state_without_session() -> None:
    client = ThermexCloudClient(FakeTransport([{"success": True, "result": True}]))

    result = client.poll_qr("token")

    assert result.state == QrState.PENDING
    assert client.sid is None


def test_authenticated_operations_require_confirmed_qr_session() -> None:
    client = ThermexCloudClient(FakeTransport([]))

    with pytest.raises(CloudError, match="confirmed QR"):
        client.list_homes()


def test_client_collects_read_only_device_records() -> None:
    transport = FakeTransport(
        [
            {"success": True, "result": [{"gid": 1}]},
            {
                "success": True,
                "result": [
                    {
                        "name": "Thermex test",
                        "devId": "device-1",
                        "productId": "product-1",
                        "productVer": "1.0",
                        "ip": "203.0.113.1",
                    }
                ],
            },
            {"success": True, "result": [{"localKey": "0123456789abcdef"}]},
        ]
    )
    client = ThermexCloudClient(transport)
    client.sid = "sid-value"

    records = client.collect_device_records()

    assert len(records) == 1
    assert records[0].device_id == "device-1"
    assert records[0].local_key == "0123456789abcdef"
    assert records[0].local_ip is None
