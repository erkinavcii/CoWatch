import dataclasses
import json
import time

import pytest
from fastapi.testclient import TestClient

from server import config, main
from server.config import get_settings, load_saved, locked_settings, saved_env
from server.main import app

KEY = "test-key"
HOST = {"base_url": "http://localhost:8000", "cookies": {"cw_key": KEY}, "client": ("127.0.0.1", 5)}
FRIEND = {"base_url": "http://pc.tail1234.ts.net", "cookies": {"cw_key": KEY}, "client": ("127.0.0.1", 5),
          "headers": {"Tailscale-User-Login": "friend@example.com"}}


def form(**changes):
    values = {key: value for key, value in config.DEFAULTS.items() if key != "osPassword"}
    return {**values, **changes}


@pytest.fixture
def data(tmp_path, monkeypatch):
    """A data folder of its own, so the saved settings do not leak into other tests."""
    monkeypatch.setattr(main, "cfg", dataclasses.replace(main.cfg, data_dir=tmp_path))
    return tmp_path


@pytest.fixture
def fresh(tmp_path, monkeypatch):
    """get_settings() reading a data folder of its own."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def test_saved_values_of_the_wrong_kind_are_dropped(tmp_path):
    (tmp_path / "settings.json").write_text(json.dumps({
        "connection": "funnel", "quality": "best", "port": "80", "libraryDirs": ["D:\\Films", 3], "extra": 1,
    }), encoding="utf-8")
    saved = load_saved(tmp_path)
    assert saved["connection"] == "funnel"
    assert saved["quality"] == "auto" and saved["port"] == 8000 and saved["libraryDirs"] == []
    assert "extra" not in saved
    (tmp_path / "settings.json").write_text("not json", encoding="utf-8")
    assert load_saved(tmp_path) == config.DEFAULTS


def test_choices_become_the_variables_they_stand_for():
    env = saved_env({**config.DEFAULTS, "connection": "http", "libraryDirs": ["D:\\Films", "E:\\Series"],
                     "quality": "manual", "qualityMbps": 6})
    assert env["TAILSCALE_SERVE"] == "0" and env["TAILSCALE_FUNNEL"] == "0"
    assert env["LIBRARY_DIRS"] == "D:\\Films;E:\\Series"
    assert env["MAX_COPY_KBPS"] == "6000" and env["TRANSCODE_KBPS"] == "4800"
    assert "MAX_COPY_KBPS" not in saved_env(config.DEFAULTS)  # auto: decided with Funnel


def test_auto_quality_converts_heavy_files_on_funnel_only(fresh, monkeypatch):
    for name in ("TAILSCALE_FUNNEL", "TAILSCALE_SERVE", "MAX_COPY_KBPS", "TRANSCODE_KBPS", "ICE_SERVERS"):
        monkeypatch.delenv(name, raising=False)
    config.save_saved(fresh, {**config.DEFAULTS, "connection": "funnel"})
    cfg = get_settings()
    assert cfg.connection == "funnel"
    assert (cfg.max_copy_kbps, cfg.transcode_kbps) == (config.FUNNEL_COPY_KBPS, config.FUNNEL_TRANSCODE_KBPS)
    config.save_saved(fresh, {**config.DEFAULTS, "connection": "serve"})
    get_settings.cache_clear()
    assert get_settings().max_copy_kbps == 0  # the original
    monkeypatch.setenv("MAX_COPY_KBPS", "9000")  # .env wins, and the page shows it locked
    config.save_saved(fresh, {**config.DEFAULTS, "connection": "funnel"})
    get_settings.cache_clear()
    assert get_settings().max_copy_kbps == 9000
    assert "quality" in locked_settings() and "connection" not in locked_settings()


def test_settings_are_for_the_host_only(data):
    with TestClient(app, **FRIEND) as friend:
        assert friend.get("/api/settings").status_code == 403
        assert friend.post("/api/settings", json=form()).status_code == 403
        assert friend.get("/api/share").status_code == 403
        assert friend.post("/api/settings/key").status_code == 403
        assert friend.post("/api/tailscale/open").status_code == 403


def test_host_saves_settings(data, tmp_path):
    films = tmp_path / "Films"
    films.mkdir()
    with TestClient(app, **HOST) as host:
        page = host.get("/api/settings").json()
        assert page["values"]["connection"] == "serve" and page["values"]["hasPassword"] is False
        assert "osApiKey" in page["locked"]  # the tests set OPENSUBTITLES_API_KEY
        assert page["canRestart"] is False

        missing = host.post("/api/settings", json=form(libraryDirs=[str(tmp_path / "nope")]))
        assert missing.status_code == 400 and missing.json()["detail"].startswith("library_dir_missing")
        assert host.post("/api/settings", json=form(iceServers="stun:a.example:3478, http://x")).status_code == 400
        assert host.post("/api/settings", json=form(port=80)).status_code == 422

        saved = host.post("/api/settings", json=form(
            connection="funnel", libraryDirs=[f'"{films}"', " "], osUsername="me", osPassword="secret",
            osApiKey="ignored", iceServers=" stun:a.example:3478 ,", port=8100))
        assert saved.json() == {"restart": False, "localLink": f"http://localhost:8100/?k={KEY}"}
        stored = json.loads((data / "settings.json").read_text(encoding="utf-8"))
        assert stored["connection"] == "funnel" and stored["libraryDirs"] == [str(films)]
        assert stored["iceServers"] == "stun:a.example:3478" and stored["osPassword"] == "secret"
        assert stored["osApiKey"] == ""  # locked by the environment: not saved

        host.post("/api/settings", json=form(osUsername="me"))  # no password sent: the saved one stays
        assert json.loads((data / "settings.json").read_text(encoding="utf-8"))["osPassword"] == "secret"
        assert host.get("/api/settings").json()["values"]["hasPassword"] is True
        assert "osPassword" not in host.get("/api/settings").json()["values"]


def test_saving_restarts_through_the_launcher(data, monkeypatch):
    class FakeLauncher:
        friend_link = "https://pc.tail1234.ts.net/?k=test-key"
        restarts = 0

        def restart(self):
            FakeLauncher.restarts += 1

        def share_state(self):
            return {"state": "consent", "mode": "funnel", "url": "https://login.tailscale.com/f/funnel?node=1"}

    monkeypatch.setattr(main, "launcher", FakeLauncher())
    monkeypatch.setattr(main.tailscale, "status", lambda: {"state": "running", "dnsName": "pc.tail1234.ts.net"})
    with TestClient(app, **HOST) as host:
        share = host.get("/api/share").json()
        assert share["friendLink"] == FakeLauncher.friend_link
        assert share["share"]["state"] == "consent" and share["tailscale"]["state"] == "running"
        assert host.post("/api/settings", json=form()).json()["restart"] is True
        assert host.post("/api/share/retry").status_code == 200
        time.sleep(1.2)  # restarts go out half a second after the answer
    assert FakeLauncher.restarts == 2


def test_new_room_key(data, monkeypatch):
    with TestClient(app, **HOST) as host:
        assert host.post("/api/settings/key").status_code == 409  # ACCESS_KEY is set for the tests
        monkeypatch.delenv("ACCESS_KEY")
        answer = host.post("/api/settings/key").json()
    key = (data / "access_key.txt").read_text(encoding="utf-8")
    assert key and key != KEY
    assert answer == {"restart": False, "localLink": f"http://localhost:8000/?k={key}"}
