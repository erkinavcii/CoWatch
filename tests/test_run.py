import json
import subprocess

import run


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
    monkeypatch.setattr(run, "find_tool", lambda _name: None)
    assert run.start_serve(run.get_settings()) is None
