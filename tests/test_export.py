import json

from thermex_key_exporter.export import mask_secret, render_report, write_json, write_report
from thermex_key_exporter.models import DeviceRecord, ExportDocument


def make_document() -> ExportDocument:
    return ExportDocument.create(
        [
            DeviceRecord(
                name="Thermex test",
                device_id="device-1",
                local_key="0123456789abcdef",
                protocol_version="3.1",
                local_ip="192.0.2.1",
                ip_source="manual",
            )
        ]
    )


def test_mask_secret() -> None:
    assert mask_secret("0123456789abcdef") == "0123…cdef"
    assert mask_secret("") == "<empty>"


def test_report_does_not_expose_full_key() -> None:
    document = make_document()
    report = render_report(document)

    assert document.devices[0].local_key not in report
    assert "0123…cdef" in report


def test_json_and_report_are_atomic_private_files(tmp_path) -> None:
    document = make_document()
    json_path = tmp_path / "export.json"
    report_path = tmp_path / "report.txt"

    write_json(document, json_path)
    write_report(document, report_path)

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["devices"][0]["local_key"] == "0123456789abcdef"
    assert json_path.stat().st_mode & 0o777 == 0o600
    assert report_path.stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob("*.tmp"))
