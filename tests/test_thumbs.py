"""Pictures over the seek bar (server/thumbs.py)."""

import asyncio
import json
import os
import shutil
import subprocess
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from server import thumbs
from server.config import get_settings
from server.media import MediaSession, MediaSource, ProbeInfo, probe
from server.thumbs import ThumbMaker, ThumbStore, interval_for, tile_height

KEY = "test-key"
HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
needs_ffmpeg = pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg not installed")


def _info(width=1920, height=1080, sar=None, duration=3000.0):
    video = {"index": 0, "codec_name": "h264", "width": width, "height": height}
    if sar:
        video["sample_aspect_ratio"] = sar
    return ProbeInfo(duration=duration, size=1, start_time=0, format_name="mkv", bitrate_kbps=1000,
                     video=video, audio=[])


def test_the_interval_keeps_a_film_to_a_few_hundred_pictures():
    assert interval_for(3000) == 10  # 50 minutes: 300 pictures
    assert interval_for(7200) == 24  # 2 hours: still 300
    assert interval_for(65) == 3.25  # a short clip: about 20
    assert interval_for(10) == 1
    assert interval_for(0) == 10
    assert thumbs.frame_count(3000, 10) == 300 and thumbs.frame_count(65, 3.25) == 20


def test_the_tile_keeps_the_pictures_shape():
    assert tile_height(_info()) == 90
    assert tile_height(_info(720, 576, "64:45")) == 90  # PAL widescreen: wide pixels
    assert tile_height(_info(3840, 1600)) == 66
    assert tile_height(_info(1080, 1920)) == 284  # an upright phone video
    assert tile_height(_info(sar="0:1")) == 90


def test_the_command_decodes_keyframes_only_and_writes_with_slashes(tmp_path):
    cmd = thumbs.build_command(get_settings(), "C:\\films\\a.mkv", _info(), tmp_path, 10, 90, "cuda")
    assert cmd[cmd.index("-hwaccel") + 1] == "cuda"
    assert cmd.index("-skip_frame") < cmd.index("-i") and cmd[cmd.index("-skip_frame") + 1] == "nokey"
    assert "fps=1000/10000,scale=160:90" in cmd[cmd.index("-vf") + 1] and "tile=10x10" in cmd[cmd.index("-vf") + 1]
    assert "\\" not in cmd[-1] and cmd[-1].endswith("/sheet_%03d.jpg")


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    """65 s with a keyframe every 2 s."""
    path = tmp_path_factory.mktemp("thumbs") / "Clip.mkv"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=12",
        "-t", "65", "-c:v", "libx264", "-preset", "ultrafast", "-g", "24", "-pix_fmt", "yuv420p", str(path),
    ], check=True)
    return path


@needs_ffmpeg
def test_a_film_gets_sprite_sheets_and_an_index(clip, tmp_path, monkeypatch):
    monkeypatch.setattr(thumbs, "COLS", 4)
    monkeypatch.setattr(thumbs, "ROWS", 2)
    cfg = get_settings()
    store = ThumbStore(tmp_path / "thumbs")

    async def run():
        info = await probe(cfg, str(clip))
        return await store.make(cfg, str(clip), info, "clip0001")

    data = asyncio.run(run())
    assert data == {"interval": 3.25, "cols": 4, "rows": 2, "w": 160, "h": 90, "count": 20, "sheets": 3,
                    "duration": 65.0}
    folder = tmp_path / "thumbs" / "clip0001"
    assert sorted(p.name for p in folder.iterdir()) == ["index.json", "sheet_000.jpg", "sheet_001.jpg", "sheet_002.jpg"]
    assert json.loads((folder / "index.json").read_text(encoding="utf-8")) == data
    size = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0",
                           str(folder / "sheet_002.jpg")], capture_output=True, text=True, check=True).stdout.strip()
    assert size == "640,180"  # the last sheet is padded to the full grid
    assert store.public("clip0001") == {"url": "/api/thumbs/clip0001/", "interval": 3.25, "cols": 4, "rows": 2,
                                        "w": 160, "h": 90, "count": 20, "sheets": 3}
    assert not list((tmp_path / "thumbs").glob(".tmp-*"))
    # Read back by a new store (the server started again).
    assert ThumbStore(tmp_path / "thumbs").public("clip0001")["count"] == 20


def test_only_sheets_of_a_film_with_pictures_are_served(tmp_path):
    store = ThumbStore(tmp_path)
    folder = tmp_path / "film1"
    folder.mkdir()
    (folder / "index.json").write_text(json.dumps({"interval": 10, "cols": 10, "rows": 10, "w": 160, "h": 90,
                                                   "count": 5, "sheets": 1}), encoding="utf-8")
    (folder / "sheet_000.jpg").write_bytes(b"\xff\xd8jpeg")
    (folder / "sheet_001.jpg").write_bytes(b"\xff\xd8left over")
    (folder / "secret.txt").write_text("x")
    assert store.file("film1", "sheet_000.jpg") == folder / "sheet_000.jpg"
    assert store.file("film1", "sheet_001.jpg") is None  # beyond the index's sheets
    for key, name in [("film1", "secret.txt"), ("film1", "index.json"), ("film1", "sheet_0.jpg"),
                      ("film1", "../film1/sheet_000.jpg"), ("..", "sheet_000.jpg"), ("film2", "sheet_000.jpg"),
                      ("film1", "sheet_000.jpg\x00"), ("a/b", "sheet_000.jpg")]:
        assert store.file(key, name) is None, (key, name)


def _playing(key):
    return SimpleNamespace(source=SimpleNamespace(media_key=key), stream=None, stop=lambda: None)


def test_the_route_needs_the_key_and_the_film_playing(tmp_path, monkeypatch):
    from server.main import app, ctl

    store = ThumbStore(tmp_path)
    monkeypatch.setattr(ctl.thumbs, "store", store)
    folder = tmp_path / "abcd1234abcd1234"
    folder.mkdir()
    (folder / "index.json").write_text(json.dumps({"interval": 10, "cols": 10, "rows": 10, "w": 160, "h": 90,
                                                   "count": 5, "sheets": 1}), encoding="utf-8")
    (folder / "sheet_000.jpg").write_bytes(b"\xff\xd8jpeg")
    url = "/api/thumbs/abcd1234abcd1234/sheet_000.jpg"
    with TestClient(app) as client:
        assert client.get(url).status_code == 401
    with TestClient(app, cookies={"cw_key": KEY}) as client:
        assert client.get(url).status_code == 404  # no film playing
        monkeypatch.setattr(ctl, "session", _playing("otherfilm"))
        assert client.get(url).status_code == 404  # an earlier film's pictures stay private
        monkeypatch.setattr(ctl, "session", _playing("abcd1234abcd1234"))
        resp = client.get(url)
        assert resp.status_code == 200 and resp.headers["content-type"] == "image/jpeg"
        assert resp.content == b"\xff\xd8jpeg"
        assert client.get("/api/thumbs/abcd1234abcd1234/index.json").status_code == 404
        assert client.get("/api/thumbs/abcd1234abcd1234/..%2Findex.json").status_code == 404


def test_only_the_films_used_last_keep_their_pictures(tmp_path):
    store = ThumbStore(tmp_path, keep=20)
    now = time.time()
    for n in range(23):
        folder = tmp_path / f"film{n:02d}"
        folder.mkdir()
        (folder / "index.json").write_text("{}", encoding="utf-8")
        os.utime(folder / "index.json", (now - 1000 + n, now - 1000 + n))  # film22 used last
    (tmp_path / "broken").mkdir()  # a run that never wrote its index
    (tmp_path / ".tmp-running").mkdir()  # a run going on now
    removed = store.prune(current="film00")
    assert sorted(removed) == ["film01", "film02"]  # the oldest, but not the film playing
    names = {p.name for p in tmp_path.iterdir()}
    assert len(names) == 22 and "film00" in names and ".tmp-running" in names and "broken" not in names
    store.touch("film03")  # opened again: now the newest
    store.prune()
    assert "film03" in {p.name for p in tmp_path.iterdir()}
    assert "film00" not in {p.name for p in tmp_path.iterdir()}


@needs_ffmpeg
def test_a_local_film_gets_pictures_a_web_address_none(clip, tmp_path, monkeypatch):
    monkeypatch.setattr(thumbs, "START_DELAY_S", 0)
    cfg = get_settings()

    async def run():
        info = await probe(cfg, str(clip))
        maker = ThumbMaker(cfg, ThumbStore(tmp_path))
        ready = []

        async def on_ready(session):
            ready.append(session)

        async def not_done(_session):
            return False

        web = MediaSession(cfg, MediaSource(kind="url", url="https://example.invalid/f.mkv", title="f", size=1,
                                            media_key="webfilm"), info)
        maker.soon(web, not_done, on_ready)
        assert maker.task is None  # never from someone else's server

        torrent = MediaSession(cfg, MediaSource(kind="torrent", url=str(clip), title="t", size=1,
                                                media_key="torrentfilm", info_hash="ab" * 20, file_index=0), info)
        maker.soon(torrent, not_done, on_ready)
        await maker.task
        assert "torrentfilm" not in maker.tried and maker.store.index("torrentfilm") is None  # not all here yet

        local = MediaSession(cfg, MediaSource(kind="file", url=str(clip), title="c", size=1, media_key="localfilm"), info)
        maker.soon(local, not_done, on_ready)
        maker.soon(local, not_done, on_ready)  # asked again while it runs: one run
        await maker.task
        assert ready == [local] and maker.store.public("localfilm")["count"] == 20
        task = maker.task
        maker.soon(local, not_done, on_ready)  # it has them: nothing more to do
        assert maker.task is task

    asyncio.run(run())


def test_stop_cancels_running_thumbnail_job(tmp_path, monkeypatch):
    monkeypatch.setattr(thumbs, "START_DELAY_S", 0)
    cfg = get_settings()

    async def run():
        started = asyncio.Event()
        cancelled = asyncio.Event()

        class SlowStore(ThumbStore):
            async def make(self, *_args, **_kwargs):
                started.set()
                try:
                    await asyncio.sleep(60)
                except asyncio.CancelledError:
                    cancelled.set()
                    raise

        maker = ThumbMaker(cfg, SlowStore(tmp_path))
        session = MediaSession(
            cfg, MediaSource(kind="file", url=str(tmp_path / "f.mkv"), title="f", size=1, media_key="cancelme"),
            ProbeInfo(duration=60.0, size=1, start_time=0.0, format_name="matroska", bitrate_kbps=1000, video={}, audio=[]),
        )
        maker.soon(session, lambda _s: asyncio.sleep(0, result=True), lambda _s: asyncio.sleep(0))
        await asyncio.wait_for(started.wait(), timeout=2)
        maker.stop()
        with pytest.raises(asyncio.CancelledError):
            await maker.task
        assert cancelled.is_set()
        assert "cancelme" not in maker.tried

    asyncio.run(run())
