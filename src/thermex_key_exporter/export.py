"""Safe JSON and human-readable export helpers."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .models import ExportDocument


def mask_secret(value: str, visible: int = 4) -> str:
    """Mask a local key while retaining enough information for identification."""
    if not value:
        return "<empty>"
    if len(value) <= visible * 2:
        return "*" * len(value)
    return f"{value[:visible]}…{value[-visible:]}"


def render_report(document: ExportDocument) -> str:
    """Render a report that never contains full local keys."""
    lines = [
        "Thermex Key Exporter report",
        f"Generated: {document.generated_at}",
        f"Devices: {len(document.devices)}",
        "",
    ]
    for index, device in enumerate(document.devices, start=1):
        lines.extend(
            [
                f"{index}. {device.name}",
                f"   device_id: {device.device_id}",
                f"   local_key: {mask_secret(device.local_key)}",
                f"   protocol_version: {device.protocol_version or '-'}",
                f"   product_id: {device.product_id or '-'}",
                f"   product_version: {device.product_version or '-'}",
                f"   local_ip: {device.local_ip or '-'}",
                f"   ip_source: {device.ip_source or '-'}",
                "",
            ]
        )
    lines.append("The JSON export contains full local keys and must be kept private.")
    return "\n".join(lines) + "\n"


def write_json(document: ExportDocument, path: Path) -> None:
    """Atomically write a private JSON export with restrictive permissions."""
    _atomic_write(
        path,
        json.dumps(document.to_mapping(), ensure_ascii=False, indent=2) + "\n",
    )


def write_report(document: ExportDocument, path: Path) -> None:
    """Atomically write a redacted report."""
    _atomic_write(path, render_report(document))


def _atomic_write(path: Path, content: str) -> None:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, path)
        os.chmod(path, 0o600)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
