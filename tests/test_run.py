import dataclasses
import json
import subprocess
import sys

import pytest

import run
from server import tailscale
from server.config import FUNNEL_STUN, get_settings


def fake_status(monkeypatch, payload):
    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess([], 0, stdout=json.dumps(payload) if payload is not None else "oops")
    monkeypatch.setattr(tailscale.subprocess, "run", fake_run)


def test_tailscale_status(monkeypatch):
    monkeypatch.setattr(tailscale, "tray_app", lambda _exe: None)
    fake_status(monkeypatch, {"BackendState": "Running", "Self": {"DNSName": "pc.tail1234.ts.net."}})
    assert tailscale.dns_name("tailscale") == "pc.tail1234.ts.net"
    fake_status(monkeypatch, {"BackendState": "NeedsLogin", "AuthURL": "https://login.tailscale.com/a/x"})
    assert tailscale.status("tailscale") == {"state": "login", "authUrl": "https://login.tailscale.com/a/x",
                                             "canOpen": False}
    assert tailscale.dns_name("tailscale") is None
    fake_status(monkeypatch, {"BackendState": "Starting"})  # stuck after a reboot until the tray app runs
    assert tailscale.status("tailscale")["state"] == "stopped"
    fake_status(monkeypatch, None)  # not JSON: the service is down
    assert tailscale.status("tailscale")["state"] == "stopped"
    monkeypatch.setattr(tailscale, "exe", lambda: None)
    assert tailscale.status()["state"] == "missing"


def test_no_share_without_tailscale(monkeypatch):
    monkeypatch.setattr(tailscale, "exe", lambda: None)
    launcher = run.Launcher()
    launcher.start_share(get_settings())  # Serve by default
    assert launcher.share is None and launcher.share_state() == {"state": "missing"}
    launcher.start_share(dataclasses.replace(get_settings(), tailscale_serve=False))
    assert launcher.share_state() == {"state": "off"}


class FakeProc:
    started = []

    def __init__(self, args, **_kwargs):
        FakeProc.started.append(args)
        self.stdout = iter(())
        self.code = None

    def wait(self, timeout=None):
        if self.code is None:
            raise subprocess.TimeoutExpired("tailscale", timeout)  # still running: it started
        return self.code

    def poll(self):
        return self.code

    def terminate(self):
        self.code = 0


def test_serve_or_funnel_runs_in_the_foreground(monkeypatch):
    FakeProc.started = []
    monkeypatch.setattr(tailscale, "exe", lambda: "tailscale")
    monkeypatch.setattr(tailscale, "dns_name", lambda _exe: "pc.tail1234.ts.net")
    monkeypatch.setattr(tailscale.subprocess, "Popen", FakeProc)
    cfg = dataclasses.replace(get_settings(), port=8123, tailscale_serve=True, tailscale_funnel=False)
    launcher = run.Launcher()
    launcher.start_share(cfg)
    assert launcher.share.link == "https://pc.tail1234.ts.net"
    assert launcher.share_state() == {"state": "ok", "mode": "serve"}
    launcher.start_share(cfg)  # same choice, still running: kept
    launcher.start_share(dataclasses.replace(cfg, tailscale_funnel=True))
    assert FakeProc.started == [["tailscale", "serve", "http://127.0.0.1:8123"],
                                ["tailscale", "funnel", "http://127.0.0.1:8123"]]


def test_share_reads_the_consent_link():
    share = tailscale.Share("tailscale", "funnel", 8000, "pc.tail1234.ts.net")
    share.proc = FakeProc([])
    share.feed("Funnel is not enabled on your tailnet.\n")
    share.feed("To enable, visit:\n")
    share.feed("         https://login.tailscale.com/f/funnel?node=abc123\n")
    assert share.public() == {"state": "consent", "mode": "funnel",
                              "url": "https://login.tailscale.com/f/funnel?node=abc123"}
    share.feed("Available on the internet:\n")
    assert share.state == "ok"
    share.proc.code = 1
    assert share.public()["state"] == "failed"
    assert share.public()["lines"][-1] == "Available on the internet:"


def test_restart_stops_the_server():
    class FakeServer:
        should_exit = False

    launcher = run.Launcher()
    launcher.server = FakeServer()
    launcher.restart()
    assert launcher.restarting and launcher.server.should_exit


def test_funnel_brings_a_stun_server_unless_one_is_set(monkeypatch):
    monkeypatch.delenv("ICE_SERVERS", raising=False)
    monkeypatch.setenv("TAILSCALE_FUNNEL", "1")
    get_settings.cache_clear()
    try:
        assert get_settings().ice_servers == FUNNEL_STUN
        monkeypatch.setenv("ICE_SERVERS", "stun:own.example:3478")
        get_settings.cache_clear()
        assert get_settings().ice_servers == "stun:own.example:3478"
        monkeypatch.setenv("TAILSCALE_FUNNEL", "0")
        monkeypatch.delenv("ICE_SERVERS")
        get_settings.cache_clear()
        assert get_settings().ice_servers == ""  # Serve: Tailscale addresses only
    finally:
        get_settings.cache_clear()


# Pretending to be Windows (os.name = "nt") elsewhere breaks pathlib itself.
@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_tailscale_found_in_the_default_windows_folder(monkeypatch, tmp_path):
    exe = tmp_path / "Tailscale" / "tailscale.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"")
    monkeypatch.setattr(tailscale.shutil, "which", lambda _name: None)
    monkeypatch.setattr(tailscale.os, "name", "nt")
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    assert tailscale.exe() == str(exe)
    (exe.parent / "tailscale-ipn.exe").write_bytes(b"")
    assert tailscale.tray_app(str(exe)) == exe.parent / "tailscale-ipn.exe"
    exe.unlink()
    assert tailscale.exe() is None
