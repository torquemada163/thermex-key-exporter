"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
import time
import uuid
from pathlib import Path

from . import APP_NAME, __version__
from .apk_profile import ProfileExtractionError, load_thermex_profile
from .app_update import (
    VERIFIED_THERMEX_HOME_VERSION,
    AppUpdateCheckError,
    check_thermex_home_update,
)
from .cloud_api import CloudError, QrState
from .export import render_report, write_json, write_report
from .models import DeviceRecord, ExportDocument
from .profile_bundle import ProfileBundleError, load_bundled_profile, write_profile_bundle
from .qr import QrChallenge, render_terminal
from .text_policy import forbidden_characters
from .workflow import ExportWorkflow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="thermex-key-exporter",
        description=(
            "Export Thermex Home local keys through a one-time QR confirmation. "
            "The application never requests an account password."
        ),
    )
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("self-test", help="run local checks without network access")
    export = subparsers.add_parser(
        "export",
        help="authorize by Thermex Home QR and write local keys to a private JSON file",
    )
    export.add_argument(
        "--apk",
        type=Path,
        help="maintainer fallback: use this official APK instead of the bundled profile",
    )
    export.add_argument(
        "--output",
        type=Path,
        default=Path("thermex-localtuya.json"),
        help="private JSON output path (default: thermex-localtuya.json)",
    )
    export.add_argument(
        "--report",
        type=Path,
        help="optional redacted report path (default: alongside the JSON output)",
    )
    export.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="seconds to wait for QR confirmation (default: 300)",
    )
    export.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="seconds between QR status checks (default: 2)",
    )
    prepare = subparsers.add_parser(
        "prepare-profile",
        help="maintainer command: derive a private profile bundle from an official APK",
    )
    prepare.add_argument("--apk", type=Path, required=True, help="path to the current official APK")
    prepare.add_argument(
        "--output",
        type=Path,
        default=Path("private/thermex-profile.json"),
        help="ignored private bundle path (default: private/thermex-profile.json)",
    )
    update = subparsers.add_parser(
        "check-app-update",
        help="compare the bundled profile version with the public Google Play listing",
    )
    update.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="Google Play request timeout in seconds (default: 20)",
    )
    subparsers.add_parser(
        "profile-status",
        help="check whether this distribution contains a Thermex profile",
    )
    return parser


def run_self_test() -> int:
    device = DeviceRecord(
        name="Self-test device",
        device_id="test-device-id",
        local_key="0123456789abcdef",
        protocol_version="3.3",
        local_ip="192.0.2.1",
        ip_source="manual",
    )
    document = ExportDocument.create([device])
    encoded = json.dumps(document.to_mapping(), ensure_ascii=False)
    if device.local_key not in encoded:
        raise RuntimeError("JSON export does not contain the local key")
    report = render_report(document)
    if device.local_key in report:
        raise RuntimeError("report exposes the full local key")
    terminal_qr = render_terminal(QrChallenge("self-test-token"))
    if "██" not in terminal_qr:
        raise RuntimeError("QR rendering did not produce terminal output")
    if forbidden_characters(APP_NAME):
        raise RuntimeError("application name violates the text policy")
    print("Self-test passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "self-test":
        return run_self_test()
    if args.command == "export":
        return run_export(args)
    if args.command == "prepare-profile":
        return run_prepare_profile(args)
    if args.command == "check-app-update":
        return run_app_update_check(args)
    if args.command == "profile-status":
        return run_profile_status()
    parser.print_help()
    return 0


def run_export(args: argparse.Namespace) -> int:
    """Run a complete QR-only read-only export without printing full keys."""
    if args.timeout <= 0 or args.poll_interval <= 0:
        print("--timeout and --poll-interval must be positive values")
        return 2
    workflow: ExportWorkflow | None = None
    try:
        if args.apk:
            print("Reading the selected official Thermex Home APK…")
            profile = load_thermex_profile(args.apk)
        else:
            print("Loading the verified Thermex profile bundled with this release…")
            profile = load_bundled_profile()
        workflow = ExportWorkflow.connect(profile, device_id=uuid.uuid4().hex)
        challenge = workflow.begin_qr_login()
        print("Scan this QR code in Thermex Home and confirm the login:")
        print(render_terminal(challenge))
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            result = workflow.poll_qr_login()
            if result.state == QrState.CONFIRMED:
                document = workflow.build_export()
                output = args.output.expanduser()
                report = (
                    args.report.expanduser() if args.report else output.with_suffix(".report.txt")
                )
                write_report(document, report)
                # If the report path cannot be written, do not leave the
                # more sensitive JSON behind as a partial export.
                write_json(document, output)
                print(f"Exported {len(document.devices)} device(s).")
                print(f"Private JSON: {output}")
                print(f"Redacted report: {report}")
                return 0
            time.sleep(args.poll_interval)
        print("Timed out waiting for QR confirmation. No key export was written.")
        return 1
    except (CloudError, ProfileBundleError, ProfileExtractionError, OSError, RuntimeError) as error:
        print(f"Export failed: {error}")
        return 1
    except KeyboardInterrupt:
        print("Export cancelled. No key export was written.")
        return 130
    finally:
        if workflow is not None:
            workflow.discard()


def run_prepare_profile(args: argparse.Namespace) -> int:
    """Derive a private build-time profile from a current official APK."""
    try:
        profile = load_thermex_profile(args.apk)
        output = args.output.expanduser()
        write_profile_bundle(profile, output)
        print(f"Private profile bundle written: {output}")
        return 0
    except (ProfileExtractionError, ProfileBundleError, OSError, RuntimeError) as error:
        print(f"Profile preparation failed: {error}")
        return 1


def run_app_update_check(args: argparse.Namespace) -> int:
    """Check the public listing without downloading an APK or creating a release."""
    try:
        status = check_thermex_home_update(timeout=args.timeout)
    except (AppUpdateCheckError, OSError, ValueError) as error:
        print(f"Update check failed: {error}")
        return 1
    if status.update_available:
        print(
            "Thermex Home update detected: "
            f"Google Play reports {status.store_version}; this build was verified with "
            f"{status.verified_version}."
        )
    else:
        print(f"Thermex Home is up to date: {status.store_version}.")
    return 0


def run_profile_status() -> int:
    """Confirm that a user-facing distribution has a usable embedded profile.

    This intentionally reports no profile fields.  It is primarily a release
    smoke check and also prevents an accidental mismatch between a private
    build bundle and the public version metadata.
    """
    try:
        profile = load_bundled_profile()
    except (ProfileBundleError, OSError, RuntimeError) as error:
        print(f"Bundled profile unavailable: {error}")
        return 1
    if profile.app_version != VERIFIED_THERMEX_HOME_VERSION:
        print("Bundled profile does not match this release metadata.")
        return 1
    print("Bundled Thermex profile is available.")
    return 0
