"""The next episode (episodes.py, Controller.find_next, /api/media/next) and resuming where a
film was left (positions.py, Controller.open_media)."""

import asyncio
import dataclasses
import json
import os

import pytest
from fastapi.testclient import TestClient

from server import main
from server.episodes import episode, label, pick_next
from server.media import MediaSession, MediaSource, ProbeInfo
from server.positions import KEEP, PositionStore

KEY = "test-key"


# ---- names --------------------------------------------------------------------------------
@pytest.mark.parametrize("name, expected", [
    ("Marvels Daredevil S01E04 In the Blood (1080p x265 Joy).mkv", (1, 4)),
    ("Daredevil.S01E05.World.On.Fire.1080p.WEB-DL.DDP5.1.x264.mkv", (1, 5)),
    ("show.s2e11.mkv", (2, 11)),
    ("Show.S03.E07.720p.mkv", (3, 7)),
    ("Show.1x05.720p.mkv", (1, 5)),
    ("Show 12x103.mkv", (12, 103)),
    ("[Group] Anime - 07 [1080p].mkv", (1, 7)),
    ("[Group] Anime - 12v2 (BD 1080p).mkv", (1, 12)),
    ("Anime Episode 2.mp4", (1, 2)),
    ("Anime.Ep.03.mp4", (1, 3)),
    ("Show.E02.mkv", (1, 2)),
    ("Show S02/Show.E04.WEB.mkv", (2, 4)),
    ("Season 3/Episode 1.mkv", (3, 1)),
    ("Movie.2019.1080p.x264.mkv", None),
    ("Movie 5.1x264.mkv", None),  # a sound and a codec, not 1x264
    ("Film 1920x1080.mkv", None),
    ("Show - 2019 - Pilot.mkv", None),
    ("Some Film.mkv", None),
])
def test_episode_numbers_come_from_the_name(name, expected):
    assert episode(name) == expected


def test_the_button_says_the_episode_and_its_title():
    assert label("Marvels Daredevil S01E04 In the Blood (1080p x265 Joy).mkv") == "S01E04 In the Blood"
    assert label("Daredevil.S01E05.World.On.Fire.1080p.WEB-DL.mkv") == "S01E05 World On Fire"
    assert label("Show.1x05.720p.mkv") == "S01E05"
    assert label("Pack/Show.S01E06.mkv") == "S01E06"
    assert label("The.Kid.1921.mkv") == "The Kid 1921"


def test_the_next_one_is_the_next_episode_not_the_next_name():
    files = ["Show S01E10.mkv", "Show S01E02.mkv", "Show S01E01.mkv", "Show S02E01.mkv", "Show S01E03 720p.mkv"]
    assert pick_next(files, "Show S01E01.mkv") == "Show S01E02.mkv"
    assert pick_next(files, "Show S01E03 720p.mkv") == "Show S01E10.mkv"  # by number: 10 after 3
    assert pick_next(files, "Show S01E10.mkv") == "Show S02E01.mkv"  # the next season
    assert pick_next(files, "Show S02E01.mkv") is None  # the last one
    # A season pack in folders, a sample and a file without a number on the way.
    pack = ["Daredevil S01/Daredevil S01E01.mkv", "Daredevil S01/Daredevil S01E02.mkv",
            "Daredevil S01/Sample/daredevil.s01e02.sample.mkv", "Daredevil S01/Extras.mkv"]
    assert pick_next(pack, pack[0]) == pack[1]
    assert pick_next(pack, pack[1]) is None


def test_without_numbers_the_order_is_by_name_counting_numbers_as_numbers():
    files = ["Part 10.mkv", "Part 2.mkv", "Part 1.mkv", "part 3.mkv"]
    assert pick_next(files, "Part 2.mkv") == "part 3.mkv"
    assert pick_next(files, "part 3.mkv") == "Part 10.mkv"
    assert pick_next(files, "Part 10.mkv") is None
    assert pick_next(["Film.mkv"], "Film.mkv") is None


# ---- positions --------------------------------------------------------------------------------
def test_a_film_resumes_between_the_first_minute_and_the_last_two(tmp_path):
    store = PositionStore(tmp_path / "positions.json")
    store.note("a", 30, 3000)
    assert "a" not in store.items  # a film just opened is not remembered
    store.note("a", 2530, 3000, "Film")
    assert store.resume_at("a", 3000) == 2530
    store.note("a", 30, 3000)  # started again from the beginning: kept, but nothing to resume
    assert store.resume_at("a", 3000) is None
    store.note("a", 1000, 3000)
    store.note("a", 2900, 3000)  # watched to its last two minutes: forgotten
    assert "a" not in store.items and store.resume_at("a", 3000) is None
    assert store.resume_at("never", 3000) is None


def test_positions_are_written_now_and_then_and_kept_to_a_limit(tmp_path):
    path = tmp_path / "positions.json"
    store = PositionStore(path)
    store.note("a", 100, 3000, now=1.0)
    store.maybe_save(now=1000.0)
    assert json.loads(path.read_text())["a"]["pos"] == 100
    store.note("a", 110, 3000, now=2.0)
    store.maybe_save(now=1005.0)  # 5 s later: not yet
    assert json.loads(path.read_text())["a"]["pos"] == 100
    store.maybe_save(now=1016.0)
    assert json.loads(path.read_text())["a"]["pos"] == 110
    for n in range(KEEP + 5):
        store.note(f"film{n}", 100, 3000, now=2000.0 + n)
    store.flush()
    kept = json.loads(path.read_text())
    assert len(kept) == KEEP and "a" not in kept and "film4" not in kept and f"film{KEEP + 4}" in kept
    assert PositionStore(path).resume_at(f"film{KEEP + 4}", 3000) == 100  # read back on the next start
    path.write_text("not json")
    assert PositionStore(path).items == {}


# ---- the next file of a torrent, a film folder, a folder on this computer --------------------------
def _session(source, audio=None):
    info = ProbeInfo(duration=3000, size=1, start_time=0, format_name="matroska", bitrate_kbps=2000,
                     video={"codec_name": "h264", "index": 0},
                     audio=audio or [{"index": 1, "codec_name": "aac", "channels": 2}])
    return MediaSession(main.cfg, source, info)


def test_the_next_file_of_a_season_torrent(monkeypatch):
    files = [{"index": i, "name": n.split("/")[-1], "path": n.replace("/", "\\"), "length": 1, "isVideo": n.endswith(".mkv")}
             for i, n in enumerate(["Daredevil S01/Marvels Daredevil S01E04 In the Blood.mkv",
                                    "Daredevil S01/Marvels Daredevil S01E05 World On Fire.mkv",
                                    "Daredevil S01/Marvels Daredevil S01E03 Rabbit in a Snowstorm.mkv",
                                    "Daredevil S01/info.nfo"])]

    async def info(info_hash):
        return {"infoHash": info_hash, "files": files}
    monkeypatch.setattr(main.ctl.helper, "info", info)
    audio = [{"index": 1, "codec_name": "aac", "tags": {"language": "tur"}},
             {"index": 2, "codec_name": "aac", "tags": {"language": "eng"}}]
    source = MediaSource(kind="torrent", url="x", title="E04", size=1, media_key="e04", info_hash="abc", file_index=0,
                         content_type="series", content_id="tt3322312:1:4")
    session = _session(source, audio)
    session.set_audio(1)
    item = asyncio.run(main.ctl.find_next(session))
    assert item == {"kind": "torrent", "label": "S01E05 World On Fire", "torrent": {"infoHash": "abc", "fileIndex": 1},
                    "content": {"type": "series", "id": "tt3322312:1:5"}, "audioLang": "en"}
    source.file_index = 1  # the last episode of the pack
    assert asyncio.run(main.ctl.find_next(_session(source))) is None


def test_the_next_file_in_a_folder_is_a_film_folder_or_the_hosts_own(tmp_path, monkeypatch):
    films = tmp_path / "Films"
    films.mkdir()
    for name in ("Show.S01E01.mkv", "Show.S01E02.mkv", "Show.S01E01.srt", "notes.txt"):
        (films / name).write_bytes(b"x")
    own = tmp_path / "Downloads"
    own.mkdir()
    for name in ("Part 1.mp4", "Part 2.mp4"):
        (own / name).write_bytes(b"x")
    monkeypatch.setattr(main, "cfg", dataclasses.replace(main.cfg, library_dirs=(films,)))

    def find(path):
        source = MediaSource(kind="file", url=str(path), title=path.name, size=1, media_key="k")
        return asyncio.run(main.ctl.find_next(_session(source)))
    assert find(films / "Show.S01E01.mkv") == {"kind": "library", "label": "S01E02",
                                               "path": str(films / "Show.S01E02.mkv")}
    assert find(films / "Show.S01E02.mkv") is None
    assert find(own / "Part 1.mp4") == {"kind": "local", "label": "Part 2", "path": str(own / "Part 2.mp4")}
    url = MediaSource(kind="url", url="https://example.com/a.mkv", title="a", size=1, media_key="u")
    assert asyncio.run(main.ctl.find_next(_session(url))) is None


# ---- who may move on ----------------------------------------------------------------------------
def test_who_may_open_the_next_episode(monkeypatch):
    opened = []
    monkeypatch.setattr(main.ctl, "open_next", lambda: opened.append(main.ctl.next_item["kind"]))
    source = MediaSource(kind="file", url="x.mkv", title="x", size=1, media_key="now-playing")
    monkeypatch.setattr(main.ctl, "session", _session(source))
    host = {"cookie": f"cw_key={KEY}; cw_viewer=next-host"}
    friend = {"cookie": f"cw_key={KEY}; cw_viewer=next-friend", "x-forwarded-for": "100.64.0.7"}
    body = {"after": "now-playing"}
    with TestClient(main.app, base_url="http://localhost:8000", client=("127.0.0.1", 5)) as client:
        def post(headers, json=body):
            return client.post("/api/media/next", json=json, headers=headers)

        monkeypatch.setattr(main.ctl, "next_item", None)
        assert post(host).status_code == 404
        monkeypatch.setattr(main.ctl, "next_item", {"kind": "local", "label": "Part 2", "path": "y.mkv"})
        assert post(friend).json()["detail"] == "local_files_host_only"
        assert post(host, {"after": "an-older-film"}).json()["detail"] == "next_moved"
        assert post(host).status_code == 202
        monkeypatch.setattr(main.ctl, "next_item", {"kind": "library", "label": "S01E02", "path": "y.mkv"})
        assert post(friend).json()["detail"] == "library_not_allowed"
        main.ctl.room.cohosts.add("next-friend")
        try:
            assert post(friend).status_code == 202  # a co-host may
        finally:
            main.ctl.room.cohosts.discard("next-friend")
        monkeypatch.setattr(main.ctl, "next_item", {"kind": "torrent", "label": "S01E05", "torrent": {}})
        assert post(friend).status_code == 202  # a torrent: whoever may change the film
        monkeypatch.setattr(main, "cfg", dataclasses.replace(main.cfg, media_control="trusted"))
        assert post(friend).json()["detail"] == "media_trusted_only"
    assert opened == ["local", "library", "torrent"]


# ---- opening: the sound track's language, and where the film was left -----------------------------------
def test_a_film_opened_again_starts_where_it_was_left(tmp_path, monkeypatch):
    film = tmp_path / "Show.S01E01.mkv"
    film.write_bytes(os.urandom(200_000))
    (tmp_path / "Show.S01E02.mkv").write_bytes(b"x")
    info = ProbeInfo(duration=3000, size=1, start_time=0, format_name="matroska", bitrate_kbps=2000,
                     video={"codec_name": "h264", "index": 0},
                     audio=[{"index": 1, "codec_name": "aac", "tags": {"language": "eng"}},
                            {"index": 2, "codec_name": "aac", "tags": {"language": "tur"}}])
    started = []

    class Stream:
        id, running, mode = "0123456789ab", True, "copy"
        out_dir = tmp_path / "hls"

        def produced(self):
            return 10.0

        def ended(self):
            return False

        def stop(self):
            pass

    async def start_at(self, target):
        started.append(target)
        self.stream, self.stream_start = Stream(), target

    async def probe(cfg, url, timeout=0):
        return info
    monkeypatch.setattr(main, "probe", probe)
    monkeypatch.setattr(MediaSession, "start_at", start_at)
    monkeypatch.setattr(main.ctl, "session", None)
    monkeypatch.setattr(main.ctl, "positions", PositionStore(tmp_path / "positions.json"))
    with TestClient(main.app, cookies={"cw_key": KEY}) as client, client.websocket_connect("/ws") as ws:
        ws.receive_json()
        client.portal.call(lambda: main.ctl.open_media(path=str(film), audio_lang="fr"))  # no such track: default
        assert started == [0.0] and main.ctl.session.audio_index == 0
        assert main.ctl.media_public()["next"] == {"label": "S01E02", "kind": "local"}
        main.ctl.room.seek(2530 - 1000)  # watched to 25:30
        client.portal.call(main.ctl.close_media)
        assert [v["pos"] for v in json.loads((tmp_path / "positions.json").read_text()).values()] == [1530]
        client.portal.call(lambda: main.ctl.open_media(path=str(film), audio_lang="tr"))
        assert started[-1] == 1530 and main.ctl.session.audio_index == 1
        assert main.ctl.room.position == 1530 and not main.ctl.room.playing
        while (msg := ws.receive_json())["type"] != "resumed":
            pass
        assert msg["at"] == 1530 and msg["mediaKey"] == main.ctl.session.source.media_key
        client.portal.call(main.ctl.close_media)
