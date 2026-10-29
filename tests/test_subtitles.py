import asyncio
import json

import httpx
import pytest

from server.subtitles import (
    OpenSubtitlesClient,
    OpenSubtitlesError,
    SubtitleError,
    SubtitleStore,
    decode_bytes,
    parse_cues,
    pick_best,
    to_vtt,
)

TR_TEXT = "1\r\n00:00:01,000 --> 00:00:02,500\r\nŞu ığdır, çok güzel öğün!\r\n"
RU_TEXT = "1\n00:00:01,000 --> 00:00:02,000\nПривет, как дела?\n"


def test_decode_turkish_cp1254():
    assert decode_bytes(TR_TEXT.encode("cp1254"), "tr") == TR_TEXT


def test_decode_russian_cp1251():
    assert decode_bytes(RU_TEXT.encode("cp1251"), "ru") == RU_TEXT


def test_decode_utf8_and_boms():
    assert decode_bytes(TR_TEXT.encode("utf-8"), "ru") == TR_TEXT  # UTF-8 wins over the hint
    assert decode_bytes(b"\xef\xbb\xbf" + RU_TEXT.encode("utf-8"), None) == RU_TEXT
    assert decode_bytes(RU_TEXT.encode("utf-16"), None) == RU_TEXT


def test_decode_without_hint_detects_cyrillic():
    long_text = (RU_TEXT * 20).encode("cp1251")
    assert "Привет" in decode_bytes(long_text, None)


def test_parse_srt_strips_tags_and_sorts():
    srt = (
        "2\n00:00:05,000 --> 00:00:06,000\n<i>Second</i> line\n\n"
        "1\n00:00:01,000 --> 00:00:02,000\nFirst\n<font color=\"red\">two lines</font>\n"
    )
    cues = parse_cues(srt)
    assert cues == [(1.0, 2.0, "First\ntwo lines"), (5.0, 6.0, "Second line")]


def test_parse_ass_drops_override_tags_and_drawings():
    ass = """[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\\an8}Hello\\Nworld
Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\\p1}m 0 0 l 100 0 100 100
Comment: 0,0:00:04.00,0:00:05.00,Default,,0,0,0,,ignored
"""
    assert parse_cues(ass) == [(1.0, 3.0, "Hello\nworld")]


def test_parse_rejects_garbage():
    with pytest.raises(SubtitleError):
        parse_cues("this is not a subtitle file")


def test_vtt_escapes_markup():
    vtt = to_vtt([(1.0, 2.5, "a < b & c"), (3661.0, 3662.0, "x --> y")])
    assert vtt.startswith("WEBVTT\n")
    assert "00:00:01.000 --> 00:00:02.500\na &lt; b &amp; c" in vtt
    assert "01:01:01.000 --> 01:01:02.000\nx --&gt; y" in vtt  # "-->" cannot appear raw in a cue


def test_store_roundtrip(tmp_path):
    store = SubtitleStore(tmp_path)
    track = store.add("abc123", "tr", "film.srt", "upload", [(1.0, 2.0, "Merhaba")], extra={"fileId": 7})
    assert store.list("abc123")[0]["id"] == track["id"]
    assert store.cues("abc123", track["id"]) == [(1.0, 2.0, "Merhaba")]
    assert store.find("abc123", fileId=7)["id"] == track["id"]
    assert store.delete("abc123", track["id"]) is True
    assert store.list("abc123") == []
    with pytest.raises(SubtitleError):
        store.cues("abc123", "../../etc")


def _result(lang, *, hash_match=False, downloads=0, machine=False, file_id=1):
    return {"attributes": {
        "language": lang, "moviehash_match": hash_match, "download_count": downloads,
        "machine_translated": machine, "files": [{"file_id": file_id, "file_name": f"{file_id}.srt"}],
    }}


def test_pick_best_prefers_hash_then_human_then_popular():
    results = [
        _result("tr", downloads=9000, file_id=1),
        _result("tr", hash_match=True, downloads=10, machine=True, file_id=2),
        _result("tr", hash_match=True, downloads=5, file_id=3),
        _result("en", hash_match=True, downloads=99999, file_id=4),
    ]
    assert pick_best(results, "tr")["attributes"]["files"][0]["file_id"] == 3
    assert pick_best(results, "ru") is None


def test_opensubtitles_search_and_download():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/api/v1/subtitles":
            return httpx.Response(200, json={"data": [_result("tr", hash_match=True, file_id=42)]})
        if request.url.path == "/api/v1/login":
            return httpx.Response(200, json={"token": "tok", "base_url": "vip-api.opensubtitles.com"})
        if request.url.path == "/api/v1/download":
            assert request.headers["Authorization"] == "Bearer tok"
            assert json.loads(request.content) == {"file_id": 42}
            return httpx.Response(200, json={"link": "https://dl.example/42.srt", "remaining": 19})
        if request.url.host == "dl.example":
            return httpx.Response(200, content=TR_TEXT.encode("cp1254"))
        return httpx.Response(404)

    client = OpenSubtitlesClient("key", "CoWatch test", "user", "pass", transport=httpx.MockTransport(handler))

    async def run():
        results = await client.search(["TR", "en"], moviehash="00ff00ff00ff00ff")
        best = pick_best(results, "tr")
        data, meta = await client.download(best["attributes"]["files"][0]["file_id"])
        return data, meta

    data, meta = asyncio.run(run())
    assert decode_bytes(data, "tr") == TR_TEXT
    assert meta["remaining"] == 19
    search = seen[0]
    assert search.headers["Api-Key"] == "key"
    assert str(search.url.query, "ascii") == "languages=en%2Ctr&moviehash=00ff00ff00ff00ff"
    assert client.base == "https://vip-api.opensubtitles.com/api/v1"


def test_opensubtitles_search_by_imdb_id_for_films_and_episodes():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url.query, "ascii"))
        return httpx.Response(200, json={"data": []})

    client = OpenSubtitlesClient("key", "CoWatch test", transport=httpx.MockTransport(handler))
    asyncio.run(client.search(["tr"], imdb_id="tt0012349"))
    asyncio.run(client.search(["tr"], imdb_id="tt0903747:1:2"))
    assert seen == ["imdb_id=12349&languages=tr",
                    "episode_number=2&languages=tr&parent_imdb_id=903747&season_number=1"]


def test_opensubtitles_quota_error():
    transport = httpx.MockTransport(lambda request: httpx.Response(406, json={"message": "quota"}))
    client = OpenSubtitlesClient("key", "CoWatch test", transport=transport)
    with pytest.raises(OpenSubtitlesError) as info:
        asyncio.run(client.download(1))
    assert info.value.code == "os_quota"


def test_opensubtitles_disabled_without_key():
    with pytest.raises(OpenSubtitlesError) as info:
        asyncio.run(OpenSubtitlesClient("", "ua").search(["tr"], moviehash="x"))
    assert info.value.code == "os_not_configured"
