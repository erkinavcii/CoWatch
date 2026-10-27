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
