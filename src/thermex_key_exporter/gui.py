"""Cross-platform Tkinter GUI for the QR-only Thermex key export workflow."""

from __future__ import annotations

import base64
import importlib
import queue
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from . import APP_NAME, __version__
from .cloud_api import CloudError, QrState
from .export import write_json, write_report
from .profile_bundle import ProfileBundleError, load_bundled_profile
from .qr import render_png
from .workflow import ExportWorkflow


class ExportWindow:
    """Own the widgets and background worker for one desktop export window."""

    def __init__(self, tk: Any, filedialog: Any) -> None:
        self.tk = tk
        self.filedialog = filedialog
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.minsize(680, 480)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.output_path = tk.StringVar(value=str(Path.cwd() / "thermex-localtuya.json"))
        self.status = tk.StringVar(value="Ready to create a one-time Thermex Home QR login.")
        self._events: queue.SimpleQueue[tuple[str, object]] = queue.SimpleQueue()
        self._cancel = threading.Event()
        self._worker: threading.Thread | None = None
        self._qr_image: Any | None = None
        self._closed = False
        self._build()
        self.root.after(100, self._drain_events)

    def _build(self) -> None:
        tk = self.tk
        frame = tk.Frame(self.root, padx=24, pady=24)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.grid_columnconfigure(1, weight=1)

        tk.Label(frame, text=APP_NAME, font=("TkDefaultFont", 18, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w"
        )
        tk.Label(
            frame,
            text=(
                "This release includes a verified Thermex profile. The application never asks for "
                "or stores your Thermex Home password, and you do not need an APK file."
            ),
            justify=tk.LEFT,
            wraplength=620,
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 20))

        tk.Label(frame, text="Private JSON export").grid(row=2, column=0, sticky="w", pady=4)
        self.output_entry = tk.Entry(frame, textvariable=self.output_path)
        self.output_entry.grid(row=2, column=1, sticky="ew", padx=(12, 8), pady=4)
        self.output_button = tk.Button(frame, text="Choose path", command=self._choose_output)
        self.output_button.grid(row=2, column=2, sticky="e", pady=4)

        button_frame = tk.Frame(frame)
        button_frame.grid(row=3, column=0, columnspan=3, sticky="w", pady=(16, 12))
        self.start_button = tk.Button(
            button_frame,
            text="Create QR and export keys",
            command=self._start,
            width=26,
        )
        self.start_button.pack(side=tk.LEFT)
        self.cancel_button = tk.Button(
            button_frame,
            text="Cancel",
            command=self._cancel_export,
            width=14,
            state=tk.DISABLED,
        )
        self.cancel_button.pack(side=tk.LEFT, padx=(8, 0))

        tk.Label(frame, textvariable=self.status, justify=tk.LEFT, wraplength=620).grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(4, 12)
        )
        self.qr_label = tk.Label(frame, text="The QR code will appear here.")
        self.qr_label.grid(row=5, column=0, columnspan=3, sticky="n", pady=(4, 0))
        tk.Label(frame, text=f"Version: {__version__}").grid(
            row=6, column=0, columnspan=3, sticky="w", pady=(12, 0)
        )

    def _choose_output(self) -> None:
        selected = self.filedialog.asksaveasfilename(
            title="Save private local-key export",
            defaultextension=".json",
            initialfile="thermex-localtuya.json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if selected:
            self.output_path.set(selected)

    def _start(self) -> None:
        output_path = Path(self.output_path.get()).expanduser()
        if not self.output_path.get().strip():
            self.status.set("Choose a private JSON output path first.")
            return
        self._cancel.clear()
        self._set_running(True)
        self.qr_label.configure(image="", text="Preparing a one-time QR code…")
        self._qr_image = None
        self.status.set("Loading the bundled profile and creating a QR login…")
        self._worker = threading.Thread(
            target=self._run_export,
            args=(output_path,),
            daemon=True,
            name="thermex-key-export",
        )
        self._worker.start()

    def _run_export(self, output_path: Path) -> None:
        workflow: ExportWorkflow | None = None
        try:
            profile = load_bundled_profile()
            workflow = ExportWorkflow.connect(profile, device_id=uuid.uuid4().hex)
            challenge = workflow.begin_qr_login()
            self._events.put(("qr", render_png(challenge)))
            self._events.put(("status", "Scan the QR code in Thermex Home and confirm the login."))
            deadline = time.monotonic() + 300.0
            while time.monotonic() < deadline:
                if self._cancel.wait(2.0):
                    self._events.put(("cancelled", None))
                    return
                result = workflow.poll_qr_login()
                if result.state == QrState.CONFIRMED:
                    if self._cancel.is_set():
                        self._events.put(("cancelled", None))
                        return
                    self._events.put(("status", "Reading homes, devices, and local keys…"))
                    document = workflow.build_export()
                    if self._cancel.is_set():
                        self._events.put(("cancelled", None))
                        return
                    report_path = output_path.with_suffix(".report.txt")
                    write_report(document, report_path)
                    if self._cancel.is_set():
                        self._events.put(("cancelled", None))
                        return
                    # Write the redacted companion first, so a failure there
                    # cannot leave a private JSON file as a partial export.
                    write_json(document, output_path)
                    self._events.put(
                        ("complete", (len(document.devices), output_path, report_path))
                    )
                    return
            self._events.put(
                ("error", "Timed out waiting for QR confirmation. No export was written.")
            )
        except (CloudError, ProfileBundleError, OSError, RuntimeError) as error:
            self._events.put(("error", f"Export failed: {error}"))
        finally:
            if workflow is not None:
                workflow.discard()

    def _drain_events(self) -> None:
        while True:
            try:
                event, value = self._events.get_nowait()
            except queue.Empty:
                break
            if event == "qr":
                encoded = base64.b64encode(value).decode("ascii")
                self._qr_image = self.tk.PhotoImage(data=encoded)
                self.qr_label.configure(image=self._qr_image, text="")
            elif event == "status":
                self.status.set(str(value))
            elif event == "complete":
                count, output_path, report_path = value
                self.status.set(
                    f"Exported {count} device(s). Private JSON: {output_path}. "
                    f"Redacted report: {report_path}."
                )
                self._set_running(False)
            elif event == "cancelled":
                self.status.set("Export cancelled. No key export was written.")
                self._set_running(False)
            elif event == "error":
                self.status.set(str(value))
                self._set_running(False)
        if not self._closed:
            self.root.after(100, self._drain_events)

    def _cancel_export(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            self._cancel.set()
            self.status.set("Cancelling the export…")

    def _set_running(self, running: bool) -> None:
        state = self.tk.DISABLED if running else self.tk.NORMAL
        self.start_button.configure(state=state)
        self.output_button.configure(state=state)
        self.output_entry.configure(state=state)
        self.cancel_button.configure(state=self.tk.NORMAL if running else self.tk.DISABLED)

    def _on_close(self) -> None:
        self._closed = True
        self._cancel.set()
        self.root.destroy()

    def run(self) -> int:
        self.root.mainloop()
        return 0


def run() -> int:
    """Start the GUI or return a clear error for Python builds without Tkinter."""
    try:
        tk = importlib.import_module("tkinter")
    except ModuleNotFoundError as error:
        if error.name not in {"tkinter", "_tkinter"}:
            raise
        print(
            "GUI is unavailable because this Python installation does not include Tkinter.",
            file=sys.stderr,
        )
        return 2
    try:
        filedialog = importlib.import_module("tkinter.filedialog")
        return ExportWindow(tk, filedialog).run()
    except tk.TclError as error:
        print(f"GUI could not start: {error}", file=sys.stderr)
        return 2
