from fastapi.testclient import TestClient

from server.main import app

KEY = "test-key"


def test_access_key_flow():
    with TestClient(app) as client:
        assert client.get("/").status_code == 401
        assert client.get("/api/status").status_code == 401
        assert client.get("/?k=wrong", follow_redirects=False).status_code == 401
        resp = client.get(f"/?k={KEY}", follow_redirects=False)
        assert resp.status_code == 303
        assert client.cookies.get("cw_key") == KEY  # later requests use the cookie
        assert client.get("/").status_code == 200
        status = client.get("/api/status").json()
        assert status["media"] is None
        assert status["isHost"] is False  # TestClient is not a loopback address


def test_client_files_are_revalidated_on_every_load():
    with TestClient(app) as client:
        first = client.get("/static/app.js")
        assert first.status_code == 200 and first.headers["cache-control"] == "no-cache"
        again = client.get("/static/app.js", headers={"if-none-match": first.headers["etag"]})
        assert again.status_code == 304


def test_hls_paths_are_restricted():
    with TestClient(app, cookies={"cw_key": KEY}) as client:
        assert client.get("/hls/abc/index.m3u8").status_code == 404
        assert client.get("/hls/0123456789ab/../../access_key.txt").status_code == 404
        assert client.get("/hls/0123456789ab/secret.txt").status_code == 404


def test_guest_cannot_open_local_files_and_needs_media_for_subtitles():
    with TestClient(app, cookies={"cw_key": KEY}) as client:
        resp = client.post("/api/media/open", json={"path": "/etc/passwd"})
        assert resp.status_code == 403
        resp = client.post("/api/subtitles/upload", files={"file": ("a.srt", b"x")}, data={"lang": "tr"})
        assert resp.status_code == 409
        resp = client.post("/api/subtitles/upload", files={"file": ("a.srt", b"x")}, data={"lang": "not a lang"})
        assert resp.status_code == 400


def test_host_is_only_the_localhost_link_on_this_computer():
    local = dict(cookies={"cw_key": KEY}, client=("127.0.0.1", 50000))
    with TestClient(app, base_url="http://localhost:8000", **local) as client:
        assert client.get("/api/status").json()["isHost"] is True
    with TestClient(app, base_url="http://[::1]:8000", cookies={"cw_key": KEY}, client=("::1", 50000)) as client:
        assert client.get("/api/status").json()["isHost"] is True
    # Tailscale Serve: same loopback address, but the tailnet name and its own headers.
    with TestClient(app, base_url="http://pc.tail1234.ts.net", **local) as client:
        assert client.get("/api/status").json()["isHost"] is False
    with TestClient(app, base_url="http://localhost:8000", **local) as client:
        for header in ({"Tailscale-User-Login": "friend@example.com"}, {"X-Forwarded-For": "100.64.0.7"},
                       {"Forwarded": "for=100.64.0.7"}):
            assert client.get("/api/status", headers=header).json()["isHost"] is False
        resp = client.post("/api/media/open", json={"path": "/etc/passwd"},
                           headers={"Tailscale-User-Login": "friend@example.com"})
        assert resp.status_code == 403


def test_websocket_welcome_ping_and_members():
    with TestClient(app, cookies={"cw_key": KEY}) as client:
        with client.websocket_connect("/ws") as ws:
            welcome = ws.receive_json()
            assert welcome["type"] == "welcome" and welcome["media"] is None
            assert ws.receive_json()["type"] == "members"
            ws.send_json({"type": "hello", "name": "Erkin\x00"})
            members = ws.receive_json()
            assert members["members"][0]["name"] == "Erkin"
            ws.send_json({"type": "ping", "t0": 5})
            pong = ws.receive_json()
            assert pong["type"] == "pong" and pong["t0"] == 5
            ws.send_json({"type": "play"})  # ignored: nothing is open
            ws.send_json({"type": "ping", "t0": 6})
            assert ws.receive_json()["type"] == "pong"


def test_websocket_requires_key():
    with TestClient(app) as client:
        try:
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()
            raised = False
        except Exception:
            raised = True
        assert raised
