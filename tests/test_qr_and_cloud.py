import pytest

from thermex_key_exporter.cloud_api import (
    CloudError,
    QrState,
    as_record_list,
    normalize_api_name,
    parse_json_payload,
    parse_qr_poll_result,
    require_success,
    result_value,
)
from thermex_key_exporter.gui_qr import render_png
from thermex_key_exporter.qr import OEM_QR_LOGIN_PREFIX, QrChallenge, render_terminal


def test_qr_payload_and_png() -> None:
    challenge = QrChallenge("short-lived-token")

    assert challenge.payload == f"{OEM_QR_LOGIN_PREFIX}short-lived-token"
    assert render_png(challenge).startswith(b"\x89PNG")
    assert "██" in render_terminal(challenge)


def test_qr_rejects_whitespace() -> None:
    with pytest.raises(ValueError):
        QrChallenge("token with whitespace")


def test_qr_poll_pending_and_confirmed() -> None:
    assert parse_qr_poll_result(True).state == QrState.PENDING
    confirmed = parse_qr_poll_result({"sid": "sid-value", "ecode": "ecode-value"})

    assert confirmed.state == QrState.CONFIRMED
    assert confirmed.sid == "sid-value"
    assert confirmed.ecode == "ecode-value"


def test_qr_poll_rejects_unknown_shape() -> None:
    with pytest.raises(CloudError):
        parse_qr_poll_result(["unexpected"])


def test_cloud_result_and_list_wrappers_are_normalized() -> None:
    response = {"success": True, "result": '{"list":[{"id":"one"}]}'}

    value = require_success(response)

    assert value == {"list": [{"id": "one"}]}
    assert result_value(response) == value
    assert as_record_list(value) == [{"id": "one"}]


def test_cloud_json_payload_requires_a_json_object() -> None:
    assert parse_json_payload(b'{"success":true}') == {"success": True}
    with pytest.raises(CloudError):
        parse_json_payload(b"[]")


def test_cloud_error_is_reported_without_treating_failure_as_empty_result() -> None:
    with pytest.raises(CloudError, match="APP_NEED_UPGRADE"):
        require_success({"success": False, "errorCode": "APP_NEED_UPGRADE", "errorMsg": "upgrade"})


def test_api_name_matches_oem_sdk_aliasing() -> None:
    assert normalize_api_name("thing.m.user.qr.token.create") == (
        "smartlife.m.user.qr.token.create"
    )
    assert normalize_api_name("m.life.group.location.list") == "m.life.group.location.list"
