import dataclasses
import json
import subprocess

import run
from server.config import FUNNEL_STUN, get_settings


def fake_status(monkeypatch, payload):
    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess([], 0, stdout=json.dumps(payload) if payload is not None else "oops")
    monkeypatch.setattr(run.subprocess, "run", fake_run)


def test_tailscale_dns_name_from_status(monkeypatch):
    fake_status(monkeypatch, {"BackendState": "Running", "Self": {"DNSName": "pc.tail1234.ts.net."}})
    assert run.tailscale_dns_name("tailscale") == "pc.tail1234.ts.net"
    fake_status(monkeypatch, {"BackendState": "NeedsLogin", "Self": {"DNSName": "pc.tail1234.ts.net."}})
    assert run.tailscale_dns_name("tailscale") is None
    fake_status(monkeypatch, None)  # not JSON
    assert run.tailscale_dns_name("tailscale") is None


def test_no_serve_without_tailscale(monkeypatch):
    monkeypatch.setattr(run, "tailscale_exe", lambda: None)
    assert run.start_serve(run.get_settings()) is None


def test_serve_or_funnel_runs_in_the_foreground(monkeypatch):
    started = []

    class FakeProc:
        def __init__(self, args):
            started.append(args)

        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired("tailscale", timeout)  # still running: it started

    monkeypatch.setattr(run, "tailscale_exe", lambda: "tailscale")
    monkeypatch.setattr(run, "tailscale_dns_name", lambda _exe: "pc.tail1234.ts.net")
    monkeypatch.setattr(run.subprocess, "Popen", FakeProc)
    cfg = dataclasses.replace(get_settings(), port=8123, tailscale_funnel=False)
    assert run.start_serve(cfg)[1] == "pc.tail1234.ts.net"
    assert run.start_serve(dataclasses.replace(cfg, tailscale_funnel=True)) is not None
    assert started == [["tailscale", "serve", "http://127.0.0.1:8123"],
                       ["tailscale", "funnel", "http://127.0.0.1:8123"]]


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


def test_tailscale_found_in_the_default_windows_folder(monkeypatch, tmp_path):
    exe = tmp_path / "Tailscale" / "tailscale.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"")
    monkeypatch.setattr(run, "find_tool", lambda _name: None)
    monkeypatch.setattr(run.os, "name", "nt")
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    assert run.tailscale_exe() == str(exe)
    exe.unlink()
    assert run.tailscale_exe() is None
