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


def test_more_friends_over_funnel_ask_the_host_to_re_encode(monkeypatch, tmp_path):
    """A film plays; friends join over Funnel. Nothing restarts by itself: the host is asked
    once per new, higher number (only when the stream would change), not when someone leaves,
    and the host's answer restarts it where the room is, for the viewers there."""
    import dataclasses

    from server import main
    from server.media import MediaSession, MediaSource, ProbeInfo

    cfg = dataclasses.replace(main.cfg, tailscale_funnel=True, funnel_budget_kbps=6000, transcode_kbps=4500)
    monkeypatch.setattr(main, "cfg", cfg)
    info = ProbeInfo(duration=1440, size=1, start_time=0, format_name="matroska", bitrate_kbps=4200,
                     video={"codec_name": "hevc", "index": 0, "bit_rate": "4000000"},
                     audio=[{"index": 1, "codec_name": "aac", "channels": 2}])
    session = MediaSession(cfg, MediaSource(kind="file", url="x.mkv", title="Film", size=1, media_key="funnel"),
                           info, remote=0)

    class Stream:
        def __init__(self):
            self.mode, self.kbps, self.audio = session.mode, session.target_kbps, session.audio
            self.id, self.running = f"fake{session.target_kbps:08d}", False
            self.out_dir = tmp_path / self.id

        def produced(self):
            return 100.0

        def ended(self):
            return True

        def stop(self):
            pass

    async def start_at(target):
        session.stream = Stream()
        session.stream_start = 0.0

    session.stream = Stream()
    monkeypatch.setattr(session, "start_at", start_at)
    monkeypatch.setattr(main.ctl, "session", session)

    host_headers = {"cookie": f"cw_key={KEY}; cw_viewer=funnel-host", "host": "localhost:8000"}

    def friend(n):  # Funnel's requests come from 127.0.0.1 with a *.ts.net Host
        return {"cookie": f"cw_key={KEY}; cw_viewer=funnel-friend-{n}", "host": "pc.tail1234.ts.net"}

    def hello(ws, name):
        ws.send_json({"type": "hello", "name": name})

    def quiet(ws):
        """Nothing about re-encoding is waiting for this page (a ping's pong comes after it)."""
        ws.send_json({"type": "ping", "t0": 1})
        while (msg := ws.receive_json())["type"] != "pong":
            assert msg["type"] != "retune"

    with TestClient(app, base_url="http://localhost:8000", client=("127.0.0.1", 5)) as client:
        with client.websocket_connect("/ws", headers=host_headers) as hws, \
                client.websocket_connect("/ws", headers=friend(1)) as f1:
            hws.receive_json(), f1.receive_json()
            hello(hws, "Host")
            hello(f1, "One")  # one friend: 4500 kbps fits, nothing to ask
            next_of(hws, "members", lambda m: sum(x["name"] == "One" for x in m["members"]) == 1)
            quiet(hws)
            with client.websocket_connect("/ws", headers=friend(2)) as f2:
                f2.receive_json()
                hello(f2, "Two")
                ask = next_of(hws, "retune")
                assert (ask["count"], ask["kbps"], ask["mode"]) == (2, 3000, "transcode")
                quiet(f1)  # friends are not asked
            next_of(hws, "members", lambda m: len(m["members"]) == 2)
            quiet(hws)  # fewer viewers ask nothing
            with client.websocket_connect("/ws", headers=friend(2)) as f2:
                f2.receive_json()
                hello(f2, "Two")
                next_of(hws, "members", lambda m: sum(x["name"] == "Two" for x in m["members"]) == 1)
                quiet(hws)  # two again: asked about that already
                assert session.stream.kbps == 4500  # and nothing restarted by itself
                friend_post = client.post("/api/media/retune", headers=friend(1))
                assert friend_post.status_code == 403
                resp = client.post("/api/media/retune", headers=host_headers)
                assert resp.json() == {"ok": True, "restarted": True}
                media = next_of(hws, "media", lambda m: m["media"]["targetKbps"] == 3000)["media"]
                assert media["funnelViewers"] == 2
                assert session.stream.kbps == 3000
                again = client.post("/api/media/retune", headers=host_headers).json()
                assert again["restarted"] is False  # made for them already


def _luma_room(stack, client, names):
    """Joined pages of one room, each with its own browser cookie (one TestClient: see CLAUDE.md)."""
    opened = []
    for name in names:
        ws = stack.enter_context(client.websocket_connect(
            "/ws", headers={"cookie": f"cw_key={KEY}; cw_viewer=luma-{name}"}))
        next_of(ws, "welcome")
        ws.send_json({"type": "hello", "name": name})
        opened.append(ws)
    return opened


def _log_lines(kind):
    from server.main import PLAYBACK_LOG, cfg
    path = cfg.data_dir / PLAYBACK_LOG
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    return [line for line in lines if f"[{kind}]" in line]


def _clear_log():
    from server.main import PLAYBACK_LOG, cfg
    (cfg.data_dir / PLAYBACK_LOG).unlink(missing_ok=True)


def _luma_rounds(opened, lumas, rounds, start=100.0):
    for r in range(rounds):
        for ws, luma in zip(opened, lumas):
            ws.send_json({"type": "luma", "t": start + 3 * r, "luma": luma, "ready": 4, "ahead": 0,
                          "paused": False, "frames": 10 * r, "dropped": 0, "stateMs": 1500, "reconnects": 2})
    repaired = []  # which pages were told to repair before their pong
    for n, ws in enumerate(opened):  # every sample before the pong has been handled
        ws.send_json({"type": "ping", "t0": 1})
        while (msg := ws.receive_json())["type"] != "pong":
            if msg["type"] == "repair":
                repaired.append(n)
    return repaired


def test_a_black_picture_on_one_page_is_logged_and_repaired():
    from contextlib import ExitStack
    _clear_log()
    with TestClient(app) as client, ExitStack() as stack:
        black, bright, other = _luma_room(stack, client, ["Kara", "Bir", "Iki"])
        if 0 not in _luma_rounds([black, bright, other], [1, 120, 90], 2):
            next_of(black, "repair")  # sent on its way after the pong
        lines = _log_lines("black_picture")
        assert len(lines) == 1 and "Kara [black_picture]" in lines[0] and "@ 103.0s" in lines[0]
        assert "readyState 4" in lines[0] and "no stream" in lines[0] and "reconnects 2" in lines[0]
        # Still black: no second repair within REPAIR_INTERVAL_S.
        assert _luma_rounds([black, bright, other], [1, 120, 90], 2, start=106.0) == []
        assert len(_log_lines("black_picture")) == 1


def test_a_dark_scene_is_not_a_black_picture():
    from contextlib import ExitStack
    _clear_log()
    with TestClient(app) as client, ExitStack() as stack:
        opened = _luma_room(stack, client, ["Bir", "Iki", "Uc"])
        # Film times of its own: a page of the test before may still be leaving, with its samples.
        _luma_rounds(opened, [2, 4, 0], 2, start=700.0)
        _luma_rounds(opened[:1], [0], 2, start=710.0)  # dark at a moment nobody else has seen
        assert _log_lines("black_picture") == []


def test_buffering_goes_to_the_playback_log():
    _clear_log()
    with TestClient(app, cookies={"cw_key": KEY}) as client:
        with client.websocket_connect("/ws") as ws:
            next_of(ws, "welcome")
            ws.send_json({"type": "hello", "name": "Yavas"})
            ws.send_json({"type": "buffering", "value": True, "position": 42.5, "ahead": 0.2})
            next_of(ws, "state")
            ws.send_json({"type": "buffering", "value": False, "position": 42.6, "ahead": "x"})
            next_of(ws, "state")
    started, ended = _log_lines("buffering"), _log_lines("buffered")
    assert len(started) == 1 and "Yavas [buffering]" in started[0] and "@ 42.5s" in started[0]
    assert "0.2 s in hand" in started[0]
    assert len(ended) == 1 and "waited " in ended[0] and "in hand" not in ended[0]


def _speech(rng, text):
    cues, t = [], 3.0
    while t < 1200:
        t += rng.uniform(0.3, 4)
        d = rng.uniform(1, 4)
        cues.append((round(t, 3), round(t + d, 3), text))
        t += d
    return cues


def test_a_subtitle_is_aligned_to_another_once_for_everyone(monkeypatch, tmp_path):
    import dataclasses
    import random

    import server.main as main
    from server.subtitles import SubtitleStore

    class Session:
        def __init__(self):
            self.source = type("Source", (), {"media_key": "film1", "title": "Test Film", "kind": "file"})()
            self.stream = None

        def stop(self):
            pass

    rng = random.Random(4)
    ref = _speech(rng, "line")
    other = _speech(rng, "another film")
    monkeypatch.setattr(main, "cfg", dataclasses.replace(main.cfg, ai_translate="trusted", data_dir=tmp_path))
    monkeypatch.setattr(main.ctl, "store", SubtitleStore(tmp_path / "subs"))
    monkeypatch.setattr(main.ctl, "session", Session())
    monkeypatch.setattr(main.ctl, "aligning", None)
    store = main.ctl.store
    embedded = store.add("film1", "en", "#2", "embedded", ref, extra={"stream": 2, "hashMatch": True})
    shifted = store.add("film1", "ru", "OpenSubtitles #1", "addon", [(s + 3.2, e + 3.2, x) for s, e, x in ref])
    wrong = store.add("film1", "tr", "upload.srt", "upload", other)
    host = {"base_url": "http://localhost:8000", "cookies": {"cw_key": KEY}, "client": ("127.0.0.1", 5)}
    friend = {"base_url": "http://pc.tail1234.ts.net", "cookies": {"cw_key": KEY}, "client": ("127.0.0.1", 5),
              "headers": {"Tailscale-User-Login": "friend@example.com"}}
    url = f"/api/subtitles/{shifted['id']}/align"
    with TestClient(app, **friend) as client:
        assert client.get("/api/status").json()["canAlign"] is False
        assert client.post(url, json={"reference": embedded["id"]}).json()["detail"] == "align_trusted_only"
    monkeypatch.setattr(main, "cfg", dataclasses.replace(main.cfg, ai_translate="everyone"))
    with TestClient(app, **friend) as client:
        assert client.get("/api/status").json()["canAlign"] is True
    monkeypatch.setattr(main, "cfg", dataclasses.replace(main.cfg, ai_translate="trusted"))
    with TestClient(app, **host) as client:
        assert client.post(url, json={"reference": shifted["id"]}).json()["detail"] == "align_same"
        assert client.post(url, json={"reference": "0123456789"}).status_code == 404
        with client.websocket_connect("/ws", headers={"host": "localhost:8000"}) as ws:
            next_of(ws, "welcome")
            res = client.post(url, json={"reference": embedded["id"]})
            assert res.status_code == 200, res.text
            body = res.json()
            assert body["cached"] is False and body["alignment"]["segments"] == 1
            assert abs(body["alignment"]["shift"] + 3.2) < 0.02
            assert next_of(ws, "status")["key"] == "aligning"
            assert next_of(ws, "subtitles")["tracks"][-1]["id"] == body["track"]
            done = next_of(ws, "status")
            assert done["key"] == "aligned" and done["params"]["track"] == body["track"]
            assert done["params"]["lang"] == "ru" and done["params"]["segments"] == 1
        made = store.find("film1", source="aligned")
        assert made["id"] == body["track"] and made["fromTrack"] == shifted["id"]
        assert made["reference"] == embedded["id"] and made["lang"] == "ru"
        assert made["label"] == "OpenSubtitles #1" and made["cues"] == len(ref)
        assert abs(store.cues("film1", made["id"])[0][0] - ref[0][0]) < 0.02
        again = client.post(url, json={"reference": embedded["id"]}).json()
        assert again["cached"] is True and again["track"] == made["id"]
        # Two different films: not trusted, nothing stored.
        res = client.post(f"/api/subtitles/{wrong['id']}/align", json={"reference": embedded["id"]})
        assert res.status_code == 422 and res.json()["detail"] == "align_unsure"
        assert len([t for t in store.list("film1") if t["source"] == "aligned"]) == 1
        assert main.ctl.aligning is None


def test_closing_media_stops_thumbnail_job(monkeypatch):
    import server.main as main

    calls = []
    monkeypatch.setattr(main.ctl.thumbs, "stop", lambda: calls.append(True))
    host = {"base_url": "http://localhost:8000", "cookies": {"cw_key": KEY}, "client": ("127.0.0.1", 5)}
    with TestClient(app, **host) as client:
        assert client.post("/api/media/close").status_code == 200
        assert calls == [True]
    assert calls == [True, True]  # lifespan stop() on shutdown too
