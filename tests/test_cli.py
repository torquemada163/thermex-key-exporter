from __future__ import annotations

from types import SimpleNamespace

import thermex_key_exporter.cli as cli
from thermex_key_exporter.app_update import VERIFIED_THERMEX_HOME_VERSION, AppUpdateStatus
from thermex_key_exporter.cloud_api import QrPollResult, QrState
from thermex_key_exporter.models import DeviceRecord, ExportDocument
from thermex_key_exporter.qr import QrChallenge


def test_cli_without_a_subcommand_prints_help(capsys) -> None:
    assert cli.main([]) == 0

    captured = capsys.readouterr()
    assert "self-test" in captured.out
    assert "one-time QR" in captured.out


def test_cli_export_writes_private_files_without_printing_the_key(
    tmp_path, monkeypatch, capsys
) -> None:
    class FakeWorkflow:
        def __init__(self) -> None:
            self.discarded = False

        def begin_qr_login(self) -> QrChallenge:
            return QrChallenge("one-time-token")

        def poll_qr_login(self) -> QrPollResult:
            return QrPollResult(QrState.CONFIRMED, "sid-value", "ecode-value")

        def build_export(self) -> ExportDocument:
            return ExportDocument.create(
                [DeviceRecord("Thermex test", "device-1", "0123456789abcdef")]
            )

        def discard(self) -> None:
            self.discarded = True

    workflow = FakeWorkflow()
    monkeypatch.setattr(cli, "load_thermex_profile", lambda _path: object())
    monkeypatch.setattr(
        cli.ExportWorkflow,
        "connect",
        lambda _profile, *, device_id: workflow,
    )
    monkeypatch.setattr(cli.webbrowser, "open", lambda _url: True)
    output = tmp_path / "thermex-localtuya.json"

    assert cli.main(["export", "--apk", "official.apk", "--output", str(output)]) == 0

    report = output.with_suffix(".report.txt")
    captured = capsys.readouterr()
    assert output.is_file()
    assert report.is_file()
    assert output.stat().st_mode & 0o777 == 0o600
    assert report.stat().st_mode & 0o777 == 0o600
    assert "0123456789abcdef" not in captured.out
    assert "0123456789abcdef" not in report.read_text(encoding="utf-8")
    assert workflow.discarded


def test_cli_does_not_write_private_json_when_the_redacted_report_fails(
    tmp_path, monkeypatch, capsys
) -> None:
    class FakeWorkflow:
        def begin_qr_login(self) -> QrChallenge:
            return QrChallenge("one-time-token")

        def poll_qr_login(self) -> QrPollResult:
            return QrPollResult(QrState.CONFIRMED, "sid-value", "ecode-value")

        def build_export(self) -> ExportDocument:
            return ExportDocument.create(
                [DeviceRecord("Thermex test", "device-1", "0123456789abcdef")]
            )

        def discard(self) -> None:
            return None

    monkeypatch.setattr(cli, "load_thermex_profile", lambda _path: object())
    monkeypatch.setattr(
        cli.ExportWorkflow,
        "connect",
        lambda _profile, *, device_id: FakeWorkflow(),
    )
    monkeypatch.setattr(cli.webbrowser, "open", lambda _url: True)

    def fail_report(*_args: object) -> None:
        raise OSError("report location is not writable")

    monkeypatch.setattr(cli, "write_report", fail_report)
    output = tmp_path / "thermex-localtuya.json"

    assert cli.main(["export", "--apk", "official.apk", "--output", str(output)]) == 1

    captured = capsys.readouterr()
    assert not output.exists()
    assert "0123456789abcdef" not in captured.out


def test_cli_export_uses_the_bundled_profile_when_no_apk_is_provided(tmp_path, monkeypatch) -> None:
    class FakeWorkflow:
        def begin_qr_login(self) -> QrChallenge:
            return QrChallenge("one-time-token")

        def poll_qr_login(self) -> QrPollResult:
            return QrPollResult(QrState.CONFIRMED, "sid-value", "ecode-value")

        def build_export(self) -> ExportDocument:
            return ExportDocument.create(
                [DeviceRecord("Thermex test", "device-1", "0123456789abcdef")]
            )

        def discard(self) -> None:
            return None

    bundled_profile = object()
    captured: dict[str, object] = {}
    monkeypatch.setattr(cli, "load_bundled_profile", lambda: bundled_profile)

    def connect(profile: object, *, device_id: str) -> FakeWorkflow:
        captured["profile"] = profile
        return FakeWorkflow()

    monkeypatch.setattr(
        cli.ExportWorkflow,
        "connect",
        connect,
    )
    monkeypatch.setattr(cli.webbrowser, "open", lambda _url: True)

    assert cli.main(["export", "--output", str(tmp_path / "keys.json")]) == 0

    assert captured["profile"] is bundled_profile


def test_cli_reports_when_google_play_has_a_new_version(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "check_thermex_home_update",
        lambda *, timeout: AppUpdateStatus("1.0.8", "1.1.0"),
    )

    assert cli.main(["check-app-update"]) == 0

    captured = capsys.readouterr()
    assert "update detected" in captured.out


def test_cli_profile_status_does_not_print_profile_data(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "load_bundled_profile",
        lambda: SimpleNamespace(app_version=VERIFIED_THERMEX_HOME_VERSION),
    )

    assert cli.main(["profile-status"]) == 0

    captured = capsys.readouterr()
    assert captured.out == "Bundled Thermex profile is available.\n"


def test_cli_profile_status_rejects_mismatched_release_metadata(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "load_bundled_profile",
        lambda: SimpleNamespace(app_version="synthetic-version"),
    )

    assert cli.main(["profile-status"]) == 1

    captured = capsys.readouterr()
    assert captured.out == "Bundled profile does not match this release metadata.\n"
