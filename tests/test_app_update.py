from __future__ import annotations

import pytest

from thermex_key_exporter.app_update import (
    AppUpdateCheckError,
    check_thermex_home_update,
    fetch_google_play_version,
    google_play_url,
    parse_google_play_version,
)

_PLAY_PAGE = """
<script>
AF_initDataCallback({key: 'ds:5', data: [null, [["com.thermex.ru", 7]], null,
[[["1.2.3"]], [[[34]], [[[23, "6.0"]]]]] ]});
</script>
"""


def test_parse_google_play_version_from_the_expected_listing() -> None:
    assert parse_google_play_version(_PLAY_PAGE) == "1.2.3"


def test_parse_google_play_version_rejects_an_unexpected_listing() -> None:
    with pytest.raises(AppUpdateCheckError, match="expected"):
        parse_google_play_version(_PLAY_PAGE.replace("com.thermex.ru", "com.example.other"))


def test_google_play_fetch_and_update_status_use_a_read_only_request() -> None:
    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return _PLAY_PAGE.encode("utf-8")

    captured: dict[str, object] = {}

    def opener(request: object, *, timeout: float) -> Response:
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    assert fetch_google_play_version(opener=opener) == "1.2.3"
    status = check_thermex_home_update(opener=opener)

    assert status.store_version == "1.2.3"
    assert status.update_available
    assert captured["request"].full_url == google_play_url()
    assert captured["timeout"] == 20.0


def test_google_play_url_rejects_an_invalid_package_name() -> None:
    with pytest.raises(ValueError, match="package"):
        google_play_url("not a package")
