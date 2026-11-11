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
        viewer = client.cookies.get("cw_viewer")  # this browser, for the host's trust
        assert viewer
        client.get("/")
        assert client.cookies.get("cw_viewer") == viewer
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


def test_file_dialog_is_for_the_host_only(monkeypatch):
    import server.filepicker as filepicker
    monkeypatch.setattr(filepicker, "pick_video", lambda title: r"C:\Films\Film.mkv")
    with TestClient(app, cookies={"cw_key": KEY}) as guest:
        assert guest.post("/api/media/pick", json={"title": "x"}).status_code == 403
    with TestClient(app, base_url="http://localhost:8000", cookies={"cw_key": KEY}, client=("127.0.0.1", 5)) as host:
        assert host.post("/api/media/pick", json={"title": "x"}).json() == {"path": r"C:\Films\Film.mkv"}

        def busy(title):
            raise filepicker.PickerError("picker_busy")
        monkeypatch.setattr(filepicker, "pick_video", busy)
        resp = host.post("/api/media/pick", json={"title": "x"})
        assert resp.status_code == 409 and resp.json()["detail"] == "picker_busy"


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


def test_websocket_buffering_after_the_watchdog_lets_the_room_go():
    import time
    from server import main
    from server.room import BUFFER_TIMEOUT_S

    def next_of(ws, kind):
        while True:
            msg = ws.receive_json()
            if msg["type"] == kind:
                return msg

    with TestClient(app, cookies={"cw_key": KEY}) as client:
        with client.websocket_connect("/ws") as ws:
            me = ws.receive_json()["clientId"]
            ws.send_json({"type": "buffering", "value": True})
            assert next_of(ws, "state")["waiting"] == [me]
            main.ctl.room.clients[me].buffering_since = time.monotonic() - BUFFER_TIMEOUT_S - 1
            assert next_of(ws, "state")["waiting"] == []  # the watchdog let the room go
            next_of(ws, "members")
            ws.send_json({"type": "buffering", "value": True})  # stalls again right away: ignored
            ws.send_json({"type": "buffering", "value": False})
            ws.send_json({"type": "ping", "t0": 1})
            assert ws.receive_json()["type"] == "pong"  # no state in between
            main.ctl.room.clients[me].buffering_ignored_until = time.monotonic() - 1
            ws.send_json({"type": "buffering", "value": True})
            assert next_of(ws, "state")["waiting"] == [me]
            ws.send_json({"type": "buffering", "value": False})
            assert next_of(ws, "state")["waiting"] == []


def test_websocket_requires_key():
    with TestClient(app) as client:
        try:
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()
            raised = False
        except Exception:
            raised = True
        assert raised


def test_host_can_trust_a_friend_with_the_film_folders(tmp_path, monkeypatch):
    import dataclasses
    import server.main as main
    films = tmp_path / "Films"
    (films / "Sub").mkdir(parents=True)
    (films / "Sub" / "b.mkv").write_bytes(b"x")
    (tmp_path / "outside.mkv").write_bytes(b"x")
    monkeypatch.setattr(main, "cfg", dataclasses.replace(main.cfg, library_dirs=(films,)))
    opened = []

    async def fake_open(**kwargs):
        opened.append(kwargs["path"])
    monkeypatch.setattr(main.ctl, "open_media", fake_open)
    ref = {"library": {"dir": 0, "path": "Sub/b.mkv"}}

    def members_until(ws, check):
        while True:
            msg = ws.receive_json()
            if msg["type"] == "members" and check(msg["members"]):
                return msg["members"]

    # One test client (one event loop) for both; the friend comes through Tailscale Serve.
    me = {"cookie": f"cw_key={KEY}; cw_viewer=host-browser"}
    friend_headers = {"cookie": f"cw_key={KEY}; cw_viewer=friend-browser", "x-forwarded-for": "100.64.0.7"}
    with TestClient(app, base_url="http://localhost:8000", client=("127.0.0.1", 5)) as client:
        def host(method, url, **kw):
            return client.request(method, url, headers=me, **kw)

        def guest(method, url, **kw):
            return client.request(method, url, headers=friend_headers, **kw)

        assert host("GET", "/api/library").json()["files"][0]["path"] == "Sub/b.mkv"
        assert guest("GET", "/api/library").status_code == 403
        assert guest("POST", "/api/media/open", json=ref).status_code == 403
        assert guest("GET", "/api/status").json()["canLibrary"] is False

        # The test client's websocket says "Host: testserver" whatever the base URL.
        with client.websocket_connect("/ws", headers={**me, "host": "localhost:8000"}) as hws, \
                client.websocket_connect("/ws", headers=friend_headers) as gws:
            friend = gws.receive_json()["clientId"]
            members = members_until(hws, lambda ms: len(ms) == 2)
            assert [m["host"] for m in members if m["id"] == friend] == [False]
            gws.send_json({"type": "grant", "to": friend, "value": True})  # only the host may
            hws.send_json({"type": "grant", "to": friend, "value": True})
            members = members_until(gws, lambda ms: any(m["cohost"] for m in ms))
            assert [m["id"] for m in members if m["cohost"]] == [friend]

            assert guest("GET", "/api/status").json()["canLibrary"] is True
            assert guest("GET", "/api/library").json()["files"][0]["path"] == "Sub/b.mkv"
            assert guest("POST", "/api/media/open", json=ref).status_code == 202
            assert opened == [str((films / "Sub" / "b.mkv").resolve())]
            bad = {"library": {"dir": 0, "path": "../outside.mkv"}}
            assert guest("POST", "/api/media/open", json=bad).status_code == 404
            assert guest("POST", "/api/media/open", json={"path": str(tmp_path / "outside.mkv")}).status_code == 403
            assert guest("GET", "/api/addons").json()["canEdit"] is False

            hws.send_json({"type": "grant", "to": friend, "value": False})
            members_until(gws, lambda ms: not any(m["cohost"] for m in ms))
            assert guest("GET", "/api/library").status_code == 403


def next_of(ws, kind, check=lambda msg: True):
    while True:
        msg = ws.receive_json()
        if msg["type"] == kind and check(msg):
            return msg


def test_each_viewer_picks_an_animal():
    headers = {"cookie": f"cw_key={KEY}; cw_viewer=animal", "host": "localhost:8000"}
    with TestClient(app, base_url="http://localhost:8000", client=("127.0.0.1", 5)) as client:
        with client.websocket_connect("/ws", headers=headers) as ws:
            me = ws.receive_json()["clientId"]

            def mine(msg):
                return next(m for m in msg["members"] if m["id"] == me)
            ws.send_json({"type": "hello", "name": "Erkin", "animal": "cat"})
            assert mine(next_of(ws, "members", lambda m: mine(m)["joined"]))["animal"] == "cat"
            ws.send_json({"type": "color", "animal": "dragon"})  # not one of ours: ignored
            ws.send_json({"type": "color", "animal": "fox"})
            assert mine(next_of(ws, "members"))["animal"] == "fox"


def test_the_host_removes_a_ghost():
    """A page that never joined (a phone's half-finished entry) leaves at once; it is told so
    and closed with 4003, and only the host may do it."""
    from starlette.websockets import WebSocketDisconnect
    host_headers = {"cookie": f"cw_key={KEY}; cw_viewer=kick-host", "host": "localhost:8000"}
    ghost_headers = {"cookie": f"cw_key={KEY}; cw_viewer=kick-ghost", "x-forwarded-for": "100.64.0.9"}
    with TestClient(app, base_url="http://localhost:8000", client=("127.0.0.1", 5)) as client:
        with client.websocket_connect("/ws", headers=host_headers) as hws,                 client.websocket_connect("/ws", headers=ghost_headers) as gws:
            host = hws.receive_json()["clientId"]
            ghost = gws.receive_json()["clientId"]
            next_of(hws, "members", lambda m: len(m["members"]) == 2)
            gws.send_json({"type": "kick", "to": host})  # a guest cannot
            hws.send_json({"type": "kick", "to": ghost})
            members = next_of(hws, "members", lambda m: len(m["members"]) == 1)["members"]
            assert [m["id"] for m in members] == [host]
            next_of(gws, "kicked")
            try:
                while True:
                    gws.receive_json()
            except WebSocketDisconnect as exc:
                assert exc.code == 4003
            from server.main import ctl
            assert ghost not in ctl.room.clients


def test_a_viewer_that_stops_hearing_leaves_and_is_closed(monkeypatch):
    """A send that hangs (a link gone quiet) must not leave a zombie: a page in the room that
    receives nothing. The viewer leaves at once, the others hear it, and its connection is
    closed with 4000 so the page reconnects."""
    import asyncio

    from starlette.websockets import WebSocketDisconnect

    from server import room as room_mod
    from server.main import DEAD_CLOSE, ctl
    monkeypatch.setattr(room_mod, "SEND_TIMEOUT_S", 0.3)
    host_headers = {"cookie": f"cw_key={KEY}; cw_viewer=dead-host", "host": "localhost:8000"}
    quiet_headers = {"cookie": f"cw_key={KEY}; cw_viewer=dead-quiet", "x-forwarded-for": "100.64.0.9"}
    with TestClient(app, base_url="http://localhost:8000", client=("127.0.0.1", 5)) as client:
        with client.websocket_connect("/ws", headers=host_headers) as hws,                 client.websocket_connect("/ws", headers=quiet_headers) as qws:
            host = hws.receive_json()["clientId"]
            quiet = qws.receive_json()["clientId"]
            next_of(hws, "members", lambda m: len(m["members"]) == 2)

            async def hang(msg):
                await asyncio.sleep(3600)
            monkeypatch.setattr(ctl.room.clients[quiet].ws, "send_json", hang)
            hws.send_json({"type": "hello", "name": "Host"})  # a members message to everyone
            members = next_of(hws, "members", lambda m: len(m["members"]) == 1)["members"]
            assert [m["id"] for m in members] == [host]
            assert quiet not in ctl.room.clients
            try:
                while True:
                    qws.receive_json()
            except WebSocketDisconnect as exc:
                assert exc.code == DEAD_CLOSE == 4000
            hws.send_json({"type": "ping", "t0": 1})  # the room goes on for the others
            assert next_of(hws, "pong")["t0"] == 1


def test_screen_share_waits_for_the_host():
    host_headers = {"cookie": f"cw_key={KEY}; cw_viewer=screen-host", "host": "localhost:8000"}
    friend_headers = {"cookie": f"cw_key={KEY}; cw_viewer=screen-friend", "x-forwarded-for": "100.64.0.8"}
    with TestClient(app, base_url="http://localhost:8000", client=("127.0.0.1", 5)) as client:
        with client.websocket_connect("/ws", headers=host_headers) as hws, \
                client.websocket_connect("/ws", headers=friend_headers) as gws:
            host = hws.receive_json()["clientId"]
            welcome = gws.receive_json()
            friend = welcome["clientId"]
            assert welcome["screen"] == {"type": "screen", "owner": None, "pending": []}

            gws.send_json({"type": "share_request"})
            msg = next_of(hws, "screen")
            assert msg["owner"] is None and msg["pending"] == [friend]
            gws.send_json({"type": "share_answer", "to": friend, "allow": True})  # not theirs to answer
            hws.send_json({"type": "share_answer", "to": friend, "allow": False})
            assert next_of(gws, "screen", lambda m: not m["pending"])["owner"] is None

            gws.send_json({"type": "share_request"})
            next_of(hws, "screen", lambda m: m["pending"])
            hws.send_json({"type": "share_answer", "to": friend, "allow": True})
            assert next_of(gws, "screen", lambda m: m["owner"])["owner"] == friend

            hws.send_json({"type": "share_request"})  # the host takes the screen without asking
            next_of(gws, "screen", lambda m: m["owner"] == host)
            gws.send_json({"type": "share_stop", "to": host})  # only the host and co-hosts stop others
            hws.send_json({"type": "share_stop"})
            assert next_of(gws, "screen") == {"type": "screen", "owner": None, "pending": []}

            gws.send_json({"type": "share_request"})
            next_of(hws, "screen", lambda m: m["pending"])
            gws.send_json({"type": "share_stop"})  # changed their mind before the answer
            assert next_of(hws, "screen")["pending"] == []


def test_screen_share_without_anyone_to_ask():
    friend_headers = {"cookie": f"cw_key={KEY}; cw_viewer=lonely-friend", "x-forwarded-for": "100.64.0.9"}
    with TestClient(app, base_url="http://localhost:8000", client=("127.0.0.1", 5)) as client:
        with client.websocket_connect("/ws", headers=friend_headers) as ws:
            friend = ws.receive_json()["clientId"]
            ws.send_json({"type": "share_request"})
            assert next_of(ws, "screen")["owner"] == friend
        with client.websocket_connect("/ws", headers=friend_headers) as ws:
            assert ws.receive_json()["screen"]["owner"] is None  # leaving ended the share


def test_media_control_trusted_keeps_the_film_to_the_host(monkeypatch):
    import dataclasses
    import server.main as main
    guest = {"cookie": f"cw_key={KEY}; cw_viewer=guest-browser", "x-forwarded-for": "100.64.0.7"}
    me = {"cookie": f"cw_key={KEY}; cw_viewer=host-browser"}
    with TestClient(app, base_url="http://localhost:8000", client=("127.0.0.1", 5)) as client:
        assert client.get("/api/status", headers=guest).json()["canChangeMedia"] is True
        assert client.post("/api/media/close", headers=guest).status_code == 200  # everyone, by default
        monkeypatch.setattr(main, "cfg", dataclasses.replace(main.cfg, media_control="trusted"))
        assert client.get("/api/status", headers=guest).json()["canChangeMedia"] is False
        for path, body in (("/api/media/close", None), ("/api/torrent/add", {"magnet": "magnet:?xt=x"}),
                           ("/api/media/open", {"stream": "nope"})):
            resp = client.post(path, json=body, headers=guest)
            assert resp.status_code == 403 and resp.json()["detail"] == "media_trusted_only", path
        assert client.post("/api/media/close", headers=me).status_code == 200


def test_an_open_that_hangs_can_be_cancelled_or_replaced(monkeypatch):
    """A torrent without peers can take many minutes to open: Cancel stops it, and opening
    another film replaces it, instead of "already opening"."""
    import asyncio
    import time

    from server import main

    started, removed = [], []

    async def hang(torrent, path, stream=None):
        started.append(path)
        main.ctl.opening_hash = f"hash-{path}"
        await asyncio.sleep(3600)  # like waiting for peers that never come

    async def remove(info_hash):
        removed.append(info_hash)

    monkeypatch.setattr(main.ctl, "_resolve_source", hang)
    monkeypatch.setattr(main.ctl.helper, "remove", remove)

    def wait(check):
        deadline = time.monotonic() + 5
        while not check() and time.monotonic() < deadline:
            time.sleep(0.02)
        return check()

    host = {"base_url": "http://localhost:8000", "cookies": {"cw_key": KEY}, "client": ("127.0.0.1", 5)}
    with TestClient(app, **host) as client:
        with client.websocket_connect("/ws", headers={"host": "localhost:8000"}) as ws:
            ws.receive_json()  # welcome
            assert client.post("/api/media/open", json={"path": "first.mkv"}).status_code == 202
            assert wait(lambda: started == ["first.mkv"])
            # Another film while the first still opens: the first is dropped, not an error.
            assert client.post("/api/media/open", json={"path": "second.mkv"}).status_code == 202
            assert wait(lambda: started == ["first.mkv", "second.mkv"])
            assert removed == ["hash-first.mkv"]  # its torrent stops downloading
            assert client.post("/api/media/cancel").status_code == 200
            assert wait(lambda: not main.ctl.opening) and removed == ["hash-first.mkv", "hash-second.mkv"]
            keys = []
            for _ in range(30):
                msg = ws.receive_json()
                if msg["type"] == "status":
                    keys.append(msg["key"])
                if keys.count("open_cancelled") == 2:
                    break
            assert keys.count("opening") == 2 and keys.count("open_cancelled") == 2 and "open_failed" not in keys
