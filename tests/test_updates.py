import asyncio
import logging
import re
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from server import main, updates
from server.config import get_settings
from server.main import app
from server.version import VERSION

KEY = "test-key"
HOST = dict(base_url="http://localhost:8000", cookies={"cw_key": KEY}, client=("127.0.0.1", 5))
ROOT = Path(__file__).resolve().parent.parent


class FakeGitHub(httpx.AsyncBaseTransport):
    def __init__(self, answer=None, error: Exception | None = None):
        self.answer = answer
        self.error = error
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return httpx.Response(200, json=self.answer)


def release(tag, **extra):
    return {"tag_name": tag, "draft": False, "prerelease": False, "html_url": "https://example.com/x", **extra}


def test_versions_compare_as_numbers():
    assert updates.parse("v0.10.0") == (0, 10, 0)
    assert updates.is_newer("v0.10.0", "0.9.1")
    assert updates.is_newer("0.2.1", "0.2.0")
    assert updates.is_newer("v1.0.0", "0.99.99")
    assert not updates.is_newer("v0.9.1", "0.10.0")
    assert not updates.is_newer("v0.2.0", "0.2.0")
    for bad in ("v0.3.0-beta.1", "0.3", "latest", None, 3, "v0.3."):
        assert not updates.is_newer(bad, "0.2.0"), bad


def test_the_version_has_one_source():
    assert re.fullmatch(r"\d+\.\d+\.\d+", VERSION)
    script = (ROOT / "tools" / "build_windows.ps1").read_text(encoding="utf-8")
    assert "server\\version.py" in script
    assert not re.search(r'\$Version = "\d', script)
    assert not re.search(r'#define AppVersion "\d', (ROOT / "tools" / "cowatch.iss").read_text(encoding="utf-8"))


def test_a_newer_release_is_for_the_host_only(monkeypatch):
    fake = FakeGitHub(release("v99.1.0"))
    monkeypatch.setattr(updates, "TRANSPORT", fake)
    monkeypatch.setattr(main, "update_check", updates.UpdateCheck())
    latest = asyncio.run(main.update_check.check())
    assert latest == {"version": "99.1.0", "url": "https://github.com/erkinavcii/CoWatch/releases/tag/v99.1.0"}
    request = fake.requests[0]
    assert str(request.url) == "https://api.github.com/repos/erkinavcii/CoWatch/releases/latest"
    assert request.headers["user-agent"] == f"Co-Watch/{VERSION}"
    assert "authorization" not in request.headers
    with TestClient(app, **HOST) as host:
        assert host.get("/api/status").json()["update"] == latest
        settings = host.get("/api/settings").json()
        assert settings["version"] == VERSION and settings["update"] == latest
    with TestClient(app, cookies={"cw_key": KEY}) as guest:
        assert guest.get("/api/status").json()["update"] is None
        assert guest.get("/api/settings").status_code == 403


def test_the_same_or_a_pre_release_or_a_draft_says_nothing(monkeypatch):
    check = updates.UpdateCheck()
    for answer in (release(f"v{VERSION}"), release("v99.0.0", prerelease=True), release("v99.0.0", draft=True),
                   release("v99.0.0-rc.1"), release("v0.0.1"), ["not", "a", "release"]):
        monkeypatch.setattr(updates, "TRANSPORT", FakeGitHub(answer))
        assert asyncio.run(check.check()) is None, answer


def test_offline_keeps_quiet_and_logs_once(monkeypatch, caplog):
    check = updates.UpdateCheck()
    monkeypatch.setattr(updates, "TRANSPORT", FakeGitHub(error=httpx.ConnectTimeout("timed out")))
    with caplog.at_level(logging.INFO, logger="cowatch"):
        for _ in range(3):
            assert asyncio.run(check.check()) is None
    assert sum("Update check failed" in r.message for r in caplog.records) == 1
    # back online: a newer release shows; a later outage keeps what was known
    monkeypatch.setattr(updates, "TRANSPORT", FakeGitHub(release("v99.0.0")))
    assert asyncio.run(check.check())["version"] == "99.0.0"
    monkeypatch.setattr(updates, "TRANSPORT", FakeGitHub(error=httpx.ConnectError("down")))
    assert asyncio.run(check.check())["version"] == "99.0.0"


def test_update_check_off_sends_nothing(monkeypatch):
    assert get_settings().update_check is False  # conftest: UPDATE_CHECK=0
    fake = FakeGitHub(release("v99.0.0"))
    monkeypatch.setattr(updates, "TRANSPORT", fake)
    monkeypatch.setattr(updates, "FIRST_DELAY_S", 0)
    with TestClient(app, **HOST) as host:
        assert all(getattr(t.get_coro(), "__name__", "") != "loop" for t in main.ctl.tasks)
        assert host.get("/api/status").json()["update"] is None
    assert fake.requests == []
