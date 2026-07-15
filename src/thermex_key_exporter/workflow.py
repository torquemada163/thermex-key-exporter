"""In-memory QR-to-export workflow shared by the GUI and CLI."""

from __future__ import annotations

from .client import ThermexCloudClient
from .cloud_api import QrPollResult
from .models import ExportDocument
from .profile import SdkProfile
from .qr import QrChallenge
from .transport import CloudTransport


class ExportWorkflow:
    """A single-use, read-only export session.

    QR token, session, response encryption material, and app profile remain in
    process memory.  Call :meth:`discard` after success, cancellation, or an
    error to drop the short-lived QR and session references promptly.
    """

    def __init__(self, client: ThermexCloudClient) -> None:
        self.client = client
        self._token: str | None = None

    @classmethod
    def connect(
        cls,
        profile: SdkProfile,
        *,
        device_id: str,
        timeout: float = 20.0,
    ) -> ExportWorkflow:
        return cls(
            ThermexCloudClient(CloudTransport(profile, device_id=device_id, timeout=timeout))
        )

    def begin_qr_login(self) -> QrChallenge:
        """Create the one-time OEM QR challenge without persisting it."""
        if self._token is not None:
            raise RuntimeError("a QR login is already active for this export session")
        self._token = self.client.create_qr_token()
        return QrChallenge(self._token)

    def poll_qr_login(self) -> QrPollResult:
        """Poll the active QR login challenge once."""
        if self._token is None:
            raise RuntimeError("a QR login has not been started")
        return self.client.poll_qr(self._token)

    def build_export(self) -> ExportDocument:
        """Collect local keys and return a versioned export document."""
        return ExportDocument.create(self.client.collect_device_records())

    def discard(self) -> None:
        """Drop short-lived references at the end of the workflow."""
        self._token = None
        self.client.sid = None
        self.client.ecode = None
