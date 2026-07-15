from __future__ import annotations

from thermex_key_exporter.cloud_api import QrPollResult, QrState
from thermex_key_exporter.models import DeviceRecord
from thermex_key_exporter.workflow import ExportWorkflow


class FakeClient:
    def __init__(self) -> None:
        self.sid: str | None = None
        self.ecode: str | None = None
        self.polled_token: str | None = None

    def create_qr_token(self) -> str:
        return "one-time-token"

    def poll_qr(self, token: str) -> QrPollResult:
        self.polled_token = token
        self.sid = "sid-value"
        self.ecode = "ecode-value"
        return QrPollResult(QrState.CONFIRMED, self.sid, self.ecode)

    def collect_device_records(self) -> list[DeviceRecord]:
        return [DeviceRecord("Thermex test", "device-1", "0123456789abcdef")]


def test_workflow_keeps_qr_and_session_in_memory_then_discards_them() -> None:
    client = FakeClient()
    workflow = ExportWorkflow(client)  # type: ignore[arg-type]

    challenge = workflow.begin_qr_login()
    result = workflow.poll_qr_login()
    document = workflow.build_export()
    workflow.discard()

    assert challenge.payload.endswith("one-time-token")
    assert client.polled_token == "one-time-token"
    assert result.state == QrState.CONFIRMED
    assert document.devices[0].local_key == "0123456789abcdef"
    assert client.sid is None
    assert client.ecode is None
