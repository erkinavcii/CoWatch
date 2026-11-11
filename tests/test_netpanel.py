"""Connection panel: measured speeds, the host's notice about a viewer who keeps stalling, and
the Funnel speed test."""

import dataclasses
import math

import httpx
from fastapi.testclient import TestClient

from server import main, netpanel
from server.main import app
from server.presence import netstat_values
from server.room import Client, STALL_COUNT, STALL_NOTICE_EVERY_S, STALL_WINDOW_S

KEY = "test-key"
HOST = {"cookie": f"cw_key={KEY}; cw_viewer=net-host", "host": "localhost:8000"}
GUEST = {"cookie": f"cw_key={KEY}; cw_viewer=net-guest", "x-forwarded-for": "100.64.0.9"}
GUEST2 = {"cookie": f"cw_key={KEY}; cw_viewer=net-guest2", "x-forwarded-for": "100.64.0.10"}


def next_of(ws, kind, check=lambda msg: True):
    while True:
        msg = ws.receive_json()
        if msg["type"] == kind and check(msg):
            return msg


def test_netstat_values_are_checked():
    assert netstat_values({"mbps": 3.14159, "bufferedAhead": 12.34}) == {"mbps": 3.14, "ahead": 12.3}
    assert netstat_values({"mbps": 5}) == {"mbps": 5.0, "ahead": None}
    assert netstat_values({"mbps": 1e9, "bufferedAhead": 1e9}) == {"mbps": 1000.0, "ahead": 600.0}
    for bad in ({}, {"mbps": "3"}, {"mbps": -1}, {"mbps": math.nan}, {"mbps": math.inf}, {"mbps": True}):
        assert netstat_values(bad) is None
    assert netstat_values({"mbps": 2, "bufferedAhead": "x"})["ahead"] is None


def test_stream_kbps():
    assert netpanel.stream_kbps({"mode": "transcode", "targetKbps": 4500, "bitrateKbps": 20000}, 192) == 4692
    assert netpanel.stream_kbps({"mode": "copy", "targetKbps": None, "bitrateKbps": 4700}, 192) == 4700
    assert netpanel.stream_kbps({"mode": "copy", "bitrateKbps": 0}, 192) is None
    assert netpanel.stream_kbps(None, 192) is None


def test_three_stalls_in_five_minutes_make_one_notice():
    client = Client(None, viewer="masha")
    client.name, client.net = "Masha", {"mbps": 3.1, "ahead": 2.0}
    noticed: dict = {}
    t = 1000.0
    assert netpanel.stall_notice(client, t, noticed, 4700, True) is None
    assert netpanel.stall_notice(client, t + 3, noticed, 4700, True) is None  # the same stall again
    assert netpanel.stall_notice(client, t + 60, noticed, 4700, True) is None
    notice = netpanel.stall_notice(client, t + 120, noticed, 4700, True)
    assert notice == {"type": "net_hint", "id": client.id, "name": "Masha", "mbps": 3.1, "filmKbps": 4700,
                      "stalls": STALL_COUNT, "minutes": 5, "funnel": True}
    # Not again for ten minutes, even after a reconnect (a new Client, the same browser).
    again = Client(None, viewer="masha")
    for i in range(STALL_COUNT):
        assert netpanel.stall_notice(again, t + 200 + i * 20, noticed, 4700, True) is None
    later = t + 120 + STALL_NOTICE_EVERY_S + 1
    for i in range(STALL_COUNT - 1):
        assert netpanel.stall_notice(again, later + i * 20, noticed, 4700, False) is None
    assert netpanel.stall_notice(again, later + 40, noticed, 4700, False)["funnel"] is False


def test_stalls_spread_over_more_than_five_minutes_say_nothing():
    client = Client(None, viewer="slowish")
    noticed: dict = {}
    gap = STALL_WINDOW_S / (STALL_COUNT - 1) + 10
    for i in range(STALL_COUNT * 3):
        assert netpanel.stall_notice(client, 50.0 + i * gap, noticed, None, False) is None


def test_netstat_reaches_everyone_and_the_members_list():
    with TestClient(app, base_url="http://localhost:8000", client=("127.0.0.1", 5)) as tc:
        with tc.websocket_connect("/ws", headers=HOST) as hws, tc.websocket_connect("/ws", headers=GUEST) as gws:
            next_of(hws, "welcome")
            guest = next_of(gws, "welcome")["clientId"]
            gws.send_json({"type": "netstat", "mbps": 3.1, "bufferedAhead": 8})
            msg = next_of(hws, "netstat")
            assert msg == {"type": "netstat", "id": guest, "mbps": 3.1, "ahead": 8.0}
            gws.send_json({"type": "netstat", "mbps": "fast"})  # not a number: dropped
            for _ in range(5):  # three at once, then one every five seconds
                gws.send_json({"type": "netstat", "mbps": 2.0})
            gws.send_json({"type": "ping", "t0": 1})
            next_of(gws, "pong")
            assert main.ctl.room.clients[guest].net == {"mbps": 2.0, "ahead": None}
            gws.send_json({"type": "hello", "name": "Masha"})
            members = next_of(hws, "members", lambda m: any(x["name"] == "Masha" for x in m["members"]))
            assert next(x for x in members["members"] if x["id"] == guest)["net"] == {"mbps": 2.0, "ahead": None}


def test_the_host_hears_when_a_viewer_keeps_stalling(monkeypatch):
    with TestClient(app, base_url="http://localhost:8000", client=("127.0.0.1", 5)) as tc:
        with tc.websocket_connect("/ws", headers=HOST) as hws, \
                tc.websocket_connect("/ws", headers=GUEST) as gws, \
                tc.websocket_connect("/ws", headers=GUEST2) as ows:
            next_of(hws, "welcome")
            guest = next_of(gws, "welcome")["clientId"]
            next_of(ows, "welcome")
            gws.send_json({"type": "hello", "name": "Masha"})
            gws.send_json({"type": "netstat", "mbps": 3.1})
            next_of(hws, "netstat")
            main.ctl.room.playing = True
            main.ctl.last_jump = -math.inf
            monkeypatch.setattr(netpanel, "STALL_MIN_GAP_S", 0)  # three stalls at once count as three
            for _ in range(STALL_COUNT):
                main.ctl.room.clients[guest].buffering_ignored_until = 0
                gws.send_json({"type": "buffering", "value": True})
                next_of(gws, "state", lambda m: guest in m["waiting"])
                gws.send_json({"type": "buffering", "value": False})
                next_of(gws, "state", lambda m: guest not in m["waiting"])
            notice = next_of(hws, "net_hint")
            assert notice["id"] == guest and notice["name"] == "Masha" and notice["mbps"] == 3.1
            assert notice["funnel"] is False
            # Only the host (and co-hosts): neither the other guest nor Masha herself.
            for ws in (ows, gws):
                ws.send_json({"type": "ping", "t0": 9})
                seen = []
                while (msg := ws.receive_json())["type"] != "pong":
                    seen.append(msg["type"])
                assert "net_hint" not in seen
            main.ctl.room.playing = False


def test_speedtest_needs_the_key_and_is_capped():
    with TestClient(app) as tc:
        assert tc.get("/api/speedtest?bytes=1000").status_code == 401
        res = tc.get(f"/api/speedtest?bytes=1000&k={KEY}")
        assert res.status_code == 200 and len(res.content) == 1000
        assert netpanel.speedtest_bytes(10**12) == netpanel.SPEEDTEST_MAX_BYTES
        assert netpanel.speedtest_bytes(0) == netpanel.SPEEDTEST_DEFAULT_BYTES
        assert netpanel.speedtest_bytes(-5) == netpanel.SPEEDTEST_DEFAULT_BYTES
        netpanel.speedtest.take_serving()  # one already on its way
        try:
            assert tc.get(f"/api/speedtest?bytes=1000&k={KEY}").status_code == 429
        finally:
            netpanel.speedtest.release_serving()
        assert tc.get(f"/api/speedtest?bytes=1000&k={KEY}").status_code == 200


class FakeLauncher:
    friend_link = "https://cowatch.example.ts.net/?k=test-key"


def test_speedtest_run_is_for_the_host_with_funnel(monkeypatch):
    local = {"cookie": f"cw_key={KEY}", "host": "localhost:8000"}
    with TestClient(app, base_url="http://localhost:8000", client=("127.0.0.1", 5)) as tc:
        assert tc.post("/api/speedtest/run", headers=local).status_code == 409  # no Funnel here
        guest = {"cookie": f"cw_key={KEY}", "x-forwarded-for": "100.64.0.9"}
        assert tc.post("/api/speedtest/run", headers=guest).status_code == 403

        monkeypatch.setattr(main, "launcher", FakeLauncher())
        monkeypatch.setattr(main, "cfg", dataclasses.replace(main.cfg, tailscale_funnel=True))
        asked = []

        async def fake_dns(name):
            asked.append(name)
            return "203.0.113.7"

        seen = []
        inner = httpx.ASGITransport(app=app)

        class Recorder(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                seen.append((str(request.url), request.headers.get("host"), request.extensions.get("sni_hostname")))
                return await inner.handle_async_request(request)

        monkeypatch.setattr(netpanel, "public_address", fake_dns)
        monkeypatch.setattr(netpanel, "TRANSPORT", Recorder())
        monkeypatch.setattr(netpanel, "SPEEDTEST_DEFAULT_BYTES", 200_000)
        res = tc.post("/api/speedtest/run", headers=local)
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["bytes"] == 200_000 and data["mbps"] > 0 and data["relay"] is True
        assert asked == ["cowatch.example.ts.net"]
        url, host, sni = seen[0]
        assert url.startswith("https://203.0.113.7/api/speedtest?bytes=200000&k=")
        assert host == "cowatch.example.ts.net" and sni == "cowatch.example.ts.net"
        assert not netpanel.speedtest.measuring and netpanel.speedtest.take_serving()
        netpanel.speedtest.release_serving()
