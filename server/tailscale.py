"""Tailscale: is it installed and running, and the HTTPS link for friends (Serve or Funnel).

run.py starts the link; the settings page shows the state and how to fix it.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Optional

CONSENT_URL = re.compile(r"https://login\.tailscale\.com/\S+")
DOWNLOAD_URL = "https://tailscale.com/download"


def exe() -> Optional[str]:
    """On PATH, or where the Windows installer puts it: a console opened before Tailscale was
    installed does not see the new PATH yet."""
    found = shutil.which("tailscale")
    if found or os.name != "nt":
        return found
    default = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tailscale" / "tailscale.exe"
    return str(default) if default.is_file() else None


def tray_app(exe_path: Optional[str]) -> Optional[Path]:
    """The Windows tray app. After a reboot the service can hang in "Starting" until it runs."""
    if not exe_path or os.name != "nt":
        return None
    app = Path(exe_path).parent / "tailscale-ipn.exe"
    return app if app.is_file() else None


def status(exe_path: Optional[str] = None) -> dict:
    """missing · stopped (service down, turned off or stuck starting) · login · running."""
    exe_path = exe_path or exe()
    if not exe_path:
        return {"state": "missing", "downloadUrl": DOWNLOAD_URL}
    can_open = tray_app(exe_path) is not None
    try:
        out = subprocess.run([exe_path, "status", "--json"], capture_output=True, text=True,
                             encoding="utf-8", timeout=10).stdout
        data = json.loads(out)
    except (OSError, subprocess.SubprocessError, ValueError):
        return {"state": "stopped", "canOpen": can_open}
    backend = data.get("BackendState")
    if backend == "Running":
        name = ((data.get("Self") or {}).get("DNSName") or "").rstrip(".")
        return {"state": "running", "dnsName": name or None}
    if backend in ("NeedsLogin", "NeedsMachineAuth"):
        return {"state": "login", "authUrl": data.get("AuthURL") or "", "canOpen": can_open}
    return {"state": "stopped", "canOpen": can_open}


def dns_name(exe_path: str) -> Optional[str]:
    """This computer's name in the tailnet (pc.tail1234.ts.net), if Tailscale is up."""
    return status(exe_path).get("dnsName")


def ip(exe_path: Optional[str]) -> Optional[str]:
    if not exe_path:
        return None
    try:
        out = subprocess.run([exe_path, "ip", "-4"], capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return out.splitlines()[0] if out else None


def open_app() -> bool:
    app = tray_app(exe())
    if app is None:
        return False
    try:
        subprocess.Popen([str(app)], close_fds=True)
    except OSError:
        return False
    return True


class Share:
    """`tailscale serve` or `tailscale funnel` in the foreground, so it stops with us; `--bg`
    would keep forwarding to a closed port after we exit, even across reboots. Its output still
    goes to the console, and is read for the consent link it prints when HTTPS or Funnel is not
    enabled on the tailnet yet; it waits there and goes on by itself once allowed."""

    def __init__(self, exe_path: str, mode: str, port: int, dns: str) -> None:
        self.exe = exe_path
        self.mode = mode  # "serve" or "funnel"
        self.port = port
        self.dns = dns
        self.proc: Optional[subprocess.Popen] = None
        self.lines: list[str] = []
        self.consent_url: Optional[str] = None

    @property
    def link(self) -> str:
        return f"https://{self.dns}"

    def start(self) -> bool:
        """False if it stopped within two seconds (its message is in `lines`)."""
        self.proc = subprocess.Popen(
            [self.exe, self.mode, f"http://127.0.0.1:{self.port}"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
        )
        threading.Thread(target=self._read, daemon=True).start()
        try:
            self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            return True
        return False

    def _read(self) -> None:
        for line in self.proc.stdout:
            print(line, end="", flush=True)
            self.feed(line)

    def feed(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        self.lines = (self.lines + [line])[-20:]
        found = CONSENT_URL.search(line)
        if found:
            self.consent_url = found.group(0)
        elif line.startswith("Available"):  # "Available on the internet:" / "within your tailnet:"
            self.consent_url = None

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    @property
    def state(self) -> str:
        if not self.running:
            return "failed"
        return "consent" if self.consent_url else "ok"

    def public(self) -> dict:
        data = {"state": self.state, "mode": self.mode}
        if self.consent_url:
            data["url"] = self.consent_url
        if not self.running:
            data["lines"] = self.lines[-4:]
        return data

    def stop(self) -> None:
        stop(self.proc)


def stop(proc: Optional[subprocess.Popen]) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
