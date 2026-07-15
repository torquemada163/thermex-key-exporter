from thermex_key_exporter.models import DeviceRecord, ExportDocument


def test_device_record_accepts_tuya_mapping() -> None:
    device = DeviceRecord.from_mapping(
        {
            "name": "Thermex test",
            "devId": "device-1",
            "localKey": "0123456789abcdef",
            "pv": "3.1",
            "productId": "product-1",
            "productVer": "1.0",
        }
    )

    assert device.device_id == "device-1"
    assert device.local_key == "0123456789abcdef"
    assert device.protocol_version == "3.1"


def test_export_document_is_versioned() -> None:
    device = DeviceRecord("Thermex test", "device-1", "0123456789abcdef")
    document = ExportDocument.create([device])

    assert document.to_mapping()["schema_version"] == 1
    assert document.to_mapping()["source"] == "Thermex Home"


def test_cloud_ip_is_not_mistaken_for_a_local_lan_address() -> None:
    device = DeviceRecord.from_mapping(
        {
            "name": "Thermex test",
            "devId": "device-1",
            "localKey": "0123456789abcdef",
            "ip": "203.0.113.1",
        }
    )

    assert device.local_ip is None
