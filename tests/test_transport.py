from __future__ import annotations

import base64
import json
import socket
import ssl
from urllib.error import URLError

import pytest

import thermex_key_exporter.transport as transport_module
from thermex_key_exporter.cloud_api import CloudError
from thermex_key_exporter.crypto import decrypt_gcm, encrypt_gcm, md5_hex
from thermex_key_exporter.profile import SdkProfile
from thermex_key_exporter.transport import CloudTransport


def profile() -> SdkProfile:
    return SdkProfile(
        app_id="synthetic-app-id",
        app_secret="synthetic-app-secret",
        certificate_sha256="AA:BB:CC:DD",
        bitmap_token="bitmap-token",
        package_name="com.example.thermex",
        app_version="1.0.0",
        ttid="synthetic-ttid",
        ch_key="synthetic-ch-key",
    )


def test_profile_derives_ch_key_when_no_override_is_supplied() -> None:
    derived = SdkProfile(
        app_id="synthetic-app-id",
        app_secret="synthetic-app-secret",
        certificate_sha256="AA:BB:CC:DD",
        bitmap_token="bitmap-token",
        package_name="com.example.thermex",
        app_version="1.0.0",
    )

    assert derived.ch_key == "6dc879c3"
    assert "synthetic-app-secret" not in repr(derived)


def test_prepare_request_is_deterministic_and_does_not_expose_plain_body() -> None:
    transport = CloudTransport(
        profile(),
        device_id="synthetic-device-id",
        now=lambda: 1_700_000_000.123,
        request_id_factory=lambda: "synthetic-request-id",
    )

    prepared = transport.prepare(
        "thing.m.user.qr.token.create",
        "1.0",
        post_data={"countryCode": "+7"},
        gzip_response=True,
    )

    assert prepared.params["time"] == "1700000000123"
    assert prepared.params["requestId"] == "synthetic-request-id"
    assert prepared.params["cp"] == "gzip"
    assert prepared.params["deviceCoreVersion"] == "5.18.0"
    assert prepared.params["nd"] == "1"
    assert prepared.params["bizData"] == (
        '{"customDomainSupport":"1","nd":"1","sdkInt":"34","brand":"Android"}'
    )
    assert prepared.headers["User-Agent"] == "Thing-UA=APP/Android/1.0.0/SDK/5.18.0"
    assert "countryCode" not in prepared.params
    encrypted = base64.b64decode(prepared.params["postData"])
    assert decrypt_gcm(prepared.response_key, encrypted) == b'{"countryCode":"+7"}'
    assert prepared.params["a"] == "smartlife.m.user.qr.token.create"
    assert prepared.params["sign"]


def test_decode_response_verifies_and_decrypts_envelope() -> None:
    transport = CloudTransport(
        profile(),
        device_id="synthetic-device-id",
        request_id_factory=lambda: "synthetic-request-id",
    )
    prepared = transport.prepare("thing.test", "1.0")
    inner = json.dumps({"success": True, "result": {"ok": 1}}, separators=(",", ":")).encode()
    encrypted = base64.b64encode(encrypt_gcm(prepared.response_key, inner)).decode("ascii")
    envelope = {
        "t": 1700000000123,
        "sign": md5_hex(
            f"result={encrypted}||t=1700000000123||{prepared.response_key.decode('ascii')}"
        ),
        "result": encrypted,
    }

    assert transport.decode_response(json.dumps(envelope).encode(), prepared) == {
        "success": True,
        "result": {"ok": 1},
    }


def test_decode_response_rejects_bad_signature() -> None:
    transport = CloudTransport(profile(), device_id="synthetic-device-id")
    prepared = transport.prepare("thing.test", "1.0")
    raw = json.dumps({"sign": "bad", "result": "not-used"}).encode()

    with pytest.raises(CloudError, match="signature"):
        transport.decode_response(raw, prepared)


def test_live_send_uses_a_form_post_without_exposing_params_in_the_url() -> None:
    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"success":true}'

    captured: dict[str, object] = {}

    def opener(request: object, *, timeout: float) -> Response:
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    transport = CloudTransport(profile(), device_id="synthetic-device-id", opener=opener)
    prepared = transport.prepare("thing.test", "1.0")

    assert transport.send(prepared) == b'{"success":true}'
    request = captured["request"]
    assert request.full_url == prepared.url
    assert request.data == prepared.body
    assert captured["timeout"] == 20.0


def test_default_opener_uses_the_certifi_ca_bundle(monkeypatch) -> None:
    request = object()
    context = object()
    response = object()
    captured: dict[str, object] = {}

    monkeypatch.setattr(transport_module.certifi, "where", lambda: "/synthetic/cacert.pem")
    monkeypatch.setattr(
        transport_module.ssl,
        "create_default_context",
        lambda *, cafile: captured.setdefault("cafile", cafile) and context,
    )

    def fake_urlopen(actual_request: object, *, timeout: float, context: object) -> object:
        captured["request"] = actual_request
        captured["timeout"] = timeout
        captured["context"] = context
        return response

    monkeypatch.setattr(transport_module, "urlopen", fake_urlopen)

    assert transport_module._secure_urlopen(request, timeout=12.5) is response
    assert captured == {
        "cafile": "/synthetic/cacert.pem",
        "request": request,
        "timeout": 12.5,
        "context": context,
    }


@pytest.mark.parametrize(
    ("reason", "message"),
    [
        (socket.gaierror(socket.EAI_NONAME, "synthetic"), "could not resolve"),
        (ssl.SSLCertVerificationError(1, "synthetic"), "could not verify"),
        (TimeoutError("synthetic"), "timed out"),
        (OSError("synthetic"), "could not connect"),
    ],
)
def test_send_reports_safe_network_failure_categories(reason: OSError, message: str) -> None:
    def opener(_request: object, *, timeout: float) -> object:
        raise URLError(reason)

    transport = CloudTransport(profile(), device_id="synthetic-device-id", opener=opener)
    prepared = transport.prepare("thing.test", "1.0")

    with pytest.raises(CloudError, match=message):
        transport.send(prepared)
