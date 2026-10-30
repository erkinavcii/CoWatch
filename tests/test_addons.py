import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

import server.addons as addons
from server.addons import AddonError, AddonStore, episode_label, magnet, manifest_url, subtitle_key, subtitle_lang
from server.main import app, ctl

KEY = "test-key"
META = "https://meta.example/manifest.json"
STREAMS = "https://streams.example/manifest.json"

MANIFESTS = {
    "meta.example": {
        "id": "test.meta", "name": "Meta", "types": ["movie", "series"], "idPrefixes": ["tt"],
        "resources": ["catalog", "meta"],
        "catalogs": [
            {"type": "movie", "id": "top", "name": "Popular", "extra": [{"name": "search"}, {"name": "skip"}]},
            {"type": "series", "id": "calendar", "extra": [{"name": "calendarVideosIds", "isRequired": True}]},
            {"type": "channel", "id": "yt"},
        ],
    },
    "streams.example": {
        "id": "test.streams", "name": "Streams", "types": ["movie", "series"],
        "resources": [{"name": "stream", "types": ["movie", "series"], "idPrefixes": ["tt"]}, "subtitles"],
        "catalogs": [],
    },
}


def handler(request: httpx.Request) -> httpx.Response:
    host, path = request.url.host, request.url.raw_path.decode()
    if path == "/manifest.json" and host in MANIFESTS:
        return httpx.Response(200, json=MANIFESTS[host])
    if host == "meta.example" and path == "/catalog/movie/top/search=the%20kid&skip=20.json":
        return httpx.Response(200, json={"metas": [
            {"id": "tt0012349", "type": "movie", "name": "The Kid", "poster": "https://img.example/kid.jpg",
             "releaseInfo": "1921", "imdbRating": "8.2"},
            {"id": "tt1", "name": "Bad poster", "poster": "javascript:alert(1)"},
            {"id": "no spaces allowed", "name": "Bad id"},
        ]})
    if host == "meta.example" and path == "/meta/series/tt0903747.json":
        return httpx.Response(200, json={"meta": {
            "id": "tt0903747", "type": "series", "name": "Breaking Bad", "description": "A teacher.",
            "videos": [{"id": "tt0903747:1:1", "season": 1, "episode": 1, "name": "Pilot", "released": "2008-01-20T00:00"}],
        }})
    if host == "streams.example" and path == "/stream/movie/tt0012349.json":
        return httpx.Response(200, json={"streams": [
            {"name": "1080p", "title": "859 MB", "infoHash": "5D640678EAE57C72C0D096904FD7D7405ECE6653",
             "fileIdx": "1", "sources": ["tracker:udp://t.example:80", "dht:5d64"]},
            {"name": "Web", "url": "https://cdn.example/kid.mp4", "behaviorHints": {"filename": "kid.mp4"}},
            {"name": "YouTube", "ytId": "abc"},
            {"name": "Elsewhere", "externalUrl": "https://shop.example"},
        ]})
    if host == "streams.example" and path.startswith("/subtitles/movie/tt0012349/"):
        assert "videoHash=00ff00ff00ff00ff" in path and "videoSize=1234" in path
        return httpx.Response(200, json={"subtitles": [
            {"id": "1", "url": "https://subs.example/1.srt", "lang": "tur"},
            {"id": "2", "url": "ftp://subs.example/2.srt", "lang": "eng"},
            {"id": "3", "url": "https://subs.example/3.srt", "lang": "tur"},
            {"id": "4", "url": "https://subs.example/4.srt", "lang": "eng"},
        ]})
    if host == "subs.example":
        return httpx.Response(200, content="1\n00:00:01,000 --> 00:00:02,000\nMerhaba\n".encode())
    return httpx.Response(404)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(addons, "DEFAULT_ADDONS", (META,))
    return AddonStore(tmp_path / "addons.json", transport=httpx.MockTransport(handler))


def run(coro):
    return asyncio.run(coro)


def test_manifest_addresses():
    assert manifest_url("stremio://x.example/abc/manifest.json") == "https://x.example/abc/manifest.json"
    assert manifest_url(" https://x.example/abc/ ") == "https://x.example/abc/manifest.json"
    with pytest.raises(AddonError):
        manifest_url("file:///etc/passwd")
    assert subtitle_lang("tur") == "tr" and subtitle_lang("pob") == "pt-br" and subtitle_lang("??") == "und"
    assert episode_label("tt0903747:1:2") == "S01E02" and episode_label("tt0012349") == ""


def test_added_addons_stay_in_their_own_file(store):
    added = run(store.add(STREAMS))
    assert added["name"] == "Streams" and added["resources"] == ["stream", "subtitles"] and not added["builtin"]
    assert json.loads(store.path.read_text()) == [{"url": STREAMS}]
    with pytest.raises(AddonError) as info:
        run(store.add(STREAMS))
    assert info.value.code == "addon_exists"
    with pytest.raises(AddonError):
        run(store.add("https://missing.example"))  # no manifest there
    listing = run(store.listing())
    assert [a["name"] for a in listing] == ["Meta", "Streams"] and listing[0]["builtin"]
    # Only browsable movie/series catalogs: not the one needing a list of ids, not channels.
    assert listing[0]["catalogs"] == [{"addon": "test.meta", "type": "movie", "id": "top", "name": "Popular",
                                       "search": True, "searchOnly": False, "genres": []}]
    assert store.remove(STREAMS) and not store.remove(META)  # the built-in ones cannot be removed
    assert store.user_urls() == []


def test_catalog_and_meta_are_cleaned(store):
    metas = run(store.catalog("test.meta", "movie", "top", search="the kid", skip=20))
    assert metas[0] == {"id": "tt0012349", "type": "movie", "name": "The Kid",
                        "poster": "https://img.example/kid.jpg", "year": "1921", "rating": "8.2"}
    assert metas[1]["poster"] is None and len(metas) == 2  # unsafe poster dropped, bad id skipped
    meta = run(store.meta("series", "tt0903747"))
    assert meta["name"] == "Breaking Bad" and meta["videos"][0] == {
        "id": "tt0903747:1:1", "season": 1, "episode": 1, "name": "Pilot", "released": "2008-01-20"}
    with pytest.raises(AddonError):
        run(store.catalog("test.meta", "movie", "../../etc"))


def test_streams_come_back_as_references(store):
    run(store.add(STREAMS))
    streams = run(store.streams("movie", "tt0012349", "The Kid"))
    assert [s["kind"] for s in streams] == ["torrent", "url"]  # YouTube and external links left out
    assert all("url" not in s and "infoHash" not in s for s in streams)
    torrent = store.lookup(streams[0]["ref"])
    assert torrent["infoHash"] == "5d640678eae57c72c0d096904fd7d7405ece6653" and torrent["fileIndex"] == 1
    assert torrent["trackers"] == ["udp://t.example:80"] and torrent["title"] == "The Kid"
    assert store.lookup(streams[1]["ref"])["url"] == "https://cdn.example/kid.mp4"
    assert store.lookup("made-up") is None
    link = magnet(torrent["infoHash"], "The Kid", [])
    assert link.startswith("magnet:?xt=urn:btih:5d64") and "dn=The%20Kid" in link and link.count("&tr=") == 4


def test_subtitles_from_addons(store):
    run(store.add(STREAMS))
    subs = run(store.subtitles("movie", "tt0012349", "00ff00ff00ff00ff", 1234, "kid.mkv"))
    # The ftp one is dropped; two in one language are told apart by number, a lone one is not.
    assert [(s["lang"], s["label"]) for s in subs] == [("tr", "Streams #1"), ("tr", "Streams #2"), ("en", "Streams")]
    assert all(s["addon"] == "Streams" for s in subs)
    assert len({s["key"] for s in subs}) == 3 and subs[0]["key"] == subtitle_key("https://subs.example/1.srt")
    item = store.lookup(subs[0]["ref"])
    assert item["label"] == "Streams #1" and "url" not in subs[0]  # the page gets no address
    assert run(store.download(item["url"], 1000)).startswith(b"1\n")
    with pytest.raises(AddonError) as info:
        run(store.download(item["url"], 10))
    assert info.value.code == "file_too_large"


def test_only_the_host_changes_the_list(monkeypatch, tmp_path):
    monkeypatch.setattr(addons, "DEFAULT_ADDONS", (META,))
    monkeypatch.setattr(ctl, "addons", AddonStore(tmp_path / "a.json", transport=httpx.MockTransport(handler)))
    with TestClient(app, cookies={"cw_key": KEY}) as client:
        body = client.get("/api/addons").json()
        assert body["canEdit"] is False and body["addons"][0]["name"] == "Meta"
        assert client.post("/api/addons", json={"url": STREAMS}).status_code == 403
        assert client.request("DELETE", "/api/addons", params={"url": META}).status_code == 403
        assert client.get("/api/addons/catalog", params={"addon": "test.meta", "type": "movie", "id": "top",
                                                         "search": "the kid", "skip": 20}).json()["metas"][0]["name"] == "The Kid"
        assert client.post("/api/media/open", json={"stream": "made-up"}).status_code == 404
    with TestClient(app, base_url="http://localhost:8000", cookies={"cw_key": KEY}, client=("127.0.0.1", 5)) as host:
        assert host.post("/api/addons", json={"url": STREAMS}).json()["name"] == "Streams"
        assert host.get("/api/addons").json()["canEdit"] is True
