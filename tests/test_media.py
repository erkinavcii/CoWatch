"""Integration tests: need ffmpeg and ffprobe on PATH."""

import asyncio
import shutil
import subprocess

import pytest

from server.config import get_settings
from server.media import MediaSession, MediaSource, clean_title, decide_mode, probe

pytestmark = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg not installed"
)


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    """20 s, H.264 with a keyframe every 2 s, AC3 5.1 audio, in MKV: a typical torrent file."""
    path = tmp_path_factory.mktemp("media") / "Sample.Film.2024.1080p.WEB.x264.mkv"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24",
        "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000",
        "-t", "20", "-c:v", "libx264", "-preset", "ultrafast", "-g", "48", "-pix_fmt", "yuv420p",
        "-c:a", "ac3", "-ac", "6", str(path),
    ], check=True)
    return path


def _stream_codecs(playlist):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,channels", "-of", "csv=p=0", str(playlist)],
        capture_output=True, text=True, check=True,
    ).stdout
    return {line.strip() for line in out.splitlines() if line.strip()}


async def _wait_finished(session):
    while session.stream.running:
        await asyncio.sleep(0.1)


def test_copy_stream_and_restart(sample):
    cfg = get_settings()

    async def run():
        info = await probe(cfg, str(sample))
        assert decide_mode(info, cfg)[0] == "copy"
        source = MediaSource(kind="file", url=str(sample), title=sample.name, size=info.size, media_key="k")
        session = MediaSession(cfg, source, info)
        assert session.audio["codec_name"] == "ac3"

        await session.start_at(0)
        assert session.stream_start < 0.2
        await _wait_finished(session)
        assert session.stream.ended()
        assert session.produced_end() == pytest.approx(20, abs=0.3)
        assert {"h264", "aac,2"} <= _stream_codecs(session.stream.playlist_path)
        assert session.can_serve(15)

        await session.start_at(13)
        # copy mode starts on the keyframe at or before the target
        assert 10.9 <= session.stream_start <= 13.05
        assert not session.can_serve(5)
        session.stop()

    asyncio.run(run())


def test_transcode_lands_on_target(sample, monkeypatch):
    cfg = get_settings()

    async def run():
        info = await probe(cfg, str(sample))
        source = MediaSource(kind="file", url=str(sample), title=sample.name, size=info.size, media_key="k")
        session = MediaSession(cfg, source, info)
        session.mode = "transcode"
        await session.start_at(7)
        assert session.stream_start == pytest.approx(7, abs=0.1)
        await _wait_finished(session)
        assert session.stream.ended()
        session.stop()

    asyncio.run(run())


def test_clean_title():
    assert clean_title("The.Matrix.1999.1080p.BluRay.x264-GRP.mkv") == "The Matrix 1999"
    assert clean_title("Some_Show_S01E02_720p_WEB-DL.mkv") == "Some Show S01E02"


def test_a_graphics_card_encoder_that_fails_falls_back_to_the_cpu(sample, monkeypatch):
    from server import media

    cfg = get_settings()
    monkeypatch.setattr(media, "pick_encoder", lambda _cfg: "h264_no_such_card")

    async def run():
        info = await probe(cfg, str(sample))
        source = MediaSource(kind="file", url=str(sample), title=sample.name, size=info.size, media_key="k")
        session = MediaSession(cfg, source, info)
        session.mode = "transcode"
        await session.start_at(0)
        assert session.encoder == "libx264" and session.public()["encoder"] == "libx264"
        assert session.stream.encoder == "libx264"
        session.stop()

    asyncio.run(run())


@pytest.fixture(scope="module")
def hdr_sample(tmp_path_factory):
    """6 s of 10-bit H.264 marked as HDR10 (PQ, BT.2020): stands in for an HDR film."""
    path = tmp_path_factory.mktemp("hdr") / "Hdr.Film.2160p.HDR.mkv"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24", "-t", "6",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p10le",
        "-x264-params", "colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc", str(path),
    ], check=True)
    return path


def test_hdr_kind_reads_the_transfer_and_dolby_vision():
    from server.media import ProbeInfo, hdr_kind, tonemap_for

    def info(video):
        return ProbeInfo(duration=1, size=1, start_time=0, format_name="", bitrate_kbps=1, video=video, audio=[])

    assert hdr_kind(info({"color_transfer": "smpte2084"})) == "pq"
    assert hdr_kind(info({"color_transfer": "arib-std-b67"})) == "hlg"
    dovi = info({"side_data_list": [{"side_data_type": "DOVI configuration record", "dv_profile": 5}]})
    assert hdr_kind(dovi) == "dovi"
    assert hdr_kind(info({"color_transfer": "bt709"})) is None
    # zscale cannot read a Dolby Vision-only picture; libplacebo can.
    assert tonemap_for(dovi, "zscale") is None and tonemap_for(dovi, "libplacebo") == "libplacebo"
    assert tonemap_for(info({"color_transfer": "bt709"}), "libplacebo") is None


def test_the_command_decodes_on_the_card_and_converts_hdr_only_when_converting(hdr_sample):
    from pathlib import PurePath

    from server.media import build_command

    cfg = get_settings()

    async def run():
        info = await probe(cfg, str(hdr_sample))
        cmd = build_command(cfg, str(hdr_sample), PurePath("out"), 0, "transcode", info, None, "libx264",
                            "cuda", "libplacebo")
        assert cmd.index("-hwaccel") < cmd.index("-i") and cmd[cmd.index("-hwaccel") + 1] == "cuda"
        assert "vulkan=vk" in cmd and cmd[cmd.index("-vf") + 1].startswith("libplacebo=")
        zs = build_command(cfg, str(hdr_sample), PurePath("out"), 0, "transcode", info, None, "libx264", None, "zscale")
        assert "-hwaccel" not in zs and "vulkan=vk" not in zs and "tonemap=tonemap=hable" in zs[zs.index("-vf") + 1]
        copy = build_command(cfg, str(hdr_sample), PurePath("out"), 0, "copy", info, None, "libx264", "cuda", "zscale")
        assert "-hwaccel" not in copy and "-vf" not in copy

    asyncio.run(run())


def test_a_decoder_that_fails_falls_back_to_the_cpu(sample, monkeypatch):
    from server import media

    cfg = get_settings()
    monkeypatch.setattr(media, "pick_encoder", lambda _cfg: "libx264")
    monkeypatch.setattr(media, "pick_hwaccel", lambda _cfg, _enc: "no_such_decoder")

    async def run():
        info = await probe(cfg, str(sample))
        source = MediaSource(kind="file", url=str(sample), title=sample.name, size=info.size, media_key="k")
        session = MediaSession(cfg, source, info)
        session.mode = "transcode"
        await session.start_at(0)
        assert session.hwaccel is None and session.public()["decoder"] is None
        assert session.encoder == "libx264"
        session.stop()

    asyncio.run(run())


def test_an_hdr_film_is_converted_and_a_failing_filter_gives_way(hdr_sample, monkeypatch):
    from server import media

    cfg = get_settings()
    monkeypatch.setattr(media, "pick_encoder", lambda _cfg: "libx264")
    monkeypatch.setattr(media, "pick_hwaccel", lambda _cfg, _enc: None)
    monkeypatch.setattr(media, "pick_tonemap", lambda _cfg: "libplacebo")
    # libplacebo cannot start (no such device): zscale takes over if this ffmpeg has it.
    monkeypatch.setattr(media, "_tonemap_device",
                        lambda kind: ["-init_hw_device", "no_such_device=x"] if kind == "libplacebo" else [])

    async def run():
        info = await probe(cfg, str(hdr_sample))
        assert media.hdr_kind(info) == "pq" and decide_mode(info, cfg)[0] == "transcode"
        source = MediaSource(kind="file", url=str(hdr_sample), title=hdr_sample.name, size=info.size, media_key="k")
        session = MediaSession(cfg, source, info)
        await session.start_at(0)
        assert session.tonemap == ("zscale" if media.tonemap_works(cfg.ffmpeg, "zscale") else None)
        assert session.public()["hdr"] == "pq" and session.public()["toneMap"] == session.tonemap
        await _wait_finished(session)
        assert session.stream.ended()
        session.stop()

    asyncio.run(run())


SRT_TR = "1\n00:00:01,000 --> 00:00:02,500\nGüzel, şimdi çıkıyoruz.\n\n2\n00:00:03,000 --> 00:00:04,000\nİkinci satır\nalt satır\n"
ASS_EN = r"""[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:02.50,Default,,0,0,0,,Good, {\i1}we leave{\i0} now.\NSecond line
Dialogue: 0,0:00:03.00,0:00:04.00,Default,,0,0,0,,{\p1}m 0 0 l 100 0 100 100{\p0}
"""


@pytest.fixture(scope="module")
def subbed_sample(tmp_path_factory):
    """6 s of video with a Turkish SRT and an English ASS inside, like an anime release."""
    folder = tmp_path_factory.mktemp("subbed")
    (folder / "tr.srt").write_text(SRT_TR, encoding="utf-8")
    (folder / "en.ass").write_text(ASS_EN, encoding="utf-8")
    path = folder / "Show.S01E01.Multi-Subs.mkv"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24", "-i", str(folder / "tr.srt"), "-i", str(folder / "en.ass"),
        "-t", "6", "-map", "0:v", "-map", "1:s", "-map", "2:s", "-c:v", "libx264", "-preset", "ultrafast",
        "-c:s:0", "srt", "-c:s:1", "ass", "-metadata:s:s:0", "language=tur", "-metadata:s:s:0", "title=Türkçe [Fansub]",
        "-metadata:s:s:1", "language=eng", "-disposition:s:1", "forced", str(path),
    ], check=True)
    return path


def test_the_subtitles_inside_a_file_become_tracks_once(subbed_sample):
    from server.main import ctl

    cfg = get_settings()

    async def run():
        info = await probe(cfg, str(subbed_sample))
        assert [s["codec_name"] for s in info.subtitles] == ["subrip", "ass"]
        source = MediaSource(kind="file", url=str(subbed_sample), title=subbed_sample.name, size=info.size,
                             media_key="embedded-test")
        session = MediaSession(cfg, source, info)
        await ctl.extract_embedded(session)
        tracks = ctl.store.list("embedded-test")
        assert [(t["lang"], t["label"], t["source"], t["hashMatch"]) for t in tracks] == [
            ("tr", "Türkçe [Fansub]", "embedded", True), ("en", "#2 (forced)", "embedded", True)]
        tr = ctl.store.cues("embedded-test", tracks[0]["id"])
        assert tr[0] == (1.0, 2.5, "Güzel, şimdi çıkıyoruz.") and tr[1][2] == "İkinci satır\nalt satır"
        en = ctl.store.cues("embedded-test", tracks[1]["id"])
        assert [c[2] for c in en] == ["Good, we leave now.\nSecond line"]  # the drawing is not text
        # Opened again (another run of the server): no second copy.
        ctl.embedded_tried.clear()
        await ctl.extract_embedded(session)
        assert len(ctl.store.list("embedded-test")) == 2

    asyncio.run(run())


def test_another_sound_track_needs_a_new_stream(tmp_path):
    cfg = get_settings()
    path = tmp_path / "Dual.Audio.mkv"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24",
        "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000",
        "-f", "lavfi", "-i", "sine=frequency=550:sample_rate=48000",
        "-t", "6", "-map", "0:v", "-map", "1:a", "-map", "2:a", "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "aac", "-metadata:s:a:0", "language=tur", "-metadata:s:a:0", "title=Dublaj",
        "-metadata:s:a:1", "language=jpn", "-disposition:a:0", "default", "-disposition:a:1", "0", str(path),
    ], check=True)

    async def run():
        info = await probe(cfg, str(path))
        session = MediaSession(cfg, MediaSource(kind="file", url=str(path), title=path.name, size=info.size,
                                                media_key="k"), info)
        pub = session.public()
        assert pub["audioIndex"] == 0
        assert [(a["lang"], a["title"]) for a in pub["audioTracks"]] == [("tr", "Dublaj"), ("ja", "")]
        await session.start_at(0)
        await _wait_finished(session)
        assert session.can_serve(2)
        assert not session.set_audio(5) and session.audio_index == 0
        assert session.set_audio(1) and session.public()["audioIndex"] == 1
        assert not session.can_serve(2)  # the stream so far carries the other sound
        await session.start_at(2)
        assert session.stream.audio is info.audio[1] and session.can_serve(3)
        session.stop()

    asyncio.run(run())


def test_the_sound_track_is_chosen_by_those_who_may_change_the_film():
    from fastapi.testclient import TestClient

    from server.main import app

    with TestClient(app, cookies={"cw_key": "test-key"}) as client:
        assert client.post("/api/media/audio", json={"index": 1}).status_code == 400  # no film open
        assert client.post("/api/media/audio", json={"index": -1}).status_code == 422


def _kbps_args(transcode_kbps, video, audio=(), bitrate_kbps=0):
    """-b:v, -maxrate and -bufsize (in kbps) for a source with these streams."""
    from dataclasses import replace

    from server.media import ProbeInfo, _video_args

    cfg = replace(get_settings(), transcode_kbps=transcode_kbps)
    info = ProbeInfo(duration=1440, size=1, start_time=0, format_name="matroska", bitrate_kbps=bitrate_kbps,
                     video={"codec_name": "hevc", **video}, audio=list(audio))
    args = _video_args(cfg, "transcode", "libx264", info)
    return tuple(int(args[args.index(flag) + 1].rstrip("k")) for flag in ("-b:v", "-maxrate", "-bufsize"))


def test_a_light_source_is_not_inflated():
    # A 1.1 Mbps x265 episode: twice that, not TRANSCODE_KBPS.
    rate, maxrate, bufsize = _kbps_args(4500, {"bit_rate": "1100000"})
    assert rate <= 2300 and rate == 2200 and maxrate == 2750 and bufsize == 4400
    # MKV often has no bit_rate on the stream, only the BPS tag.
    assert _kbps_args(4500, {"tags": {"BPS-eng": "1100000"}})[0] == 2200
    assert _kbps_args(4500, {"tags": {"BPS": "1100000"}})[0] == 2200
    # Neither: the file's total minus its sound tracks (1230 - 130 = 1100).
    audio = [{"codec_type": "audio", "tags": {"BPS-eng": "130000"}}]
    assert _kbps_args(4500, {}, audio, bitrate_kbps=1230)[0] == 2200


def test_a_heavy_or_unknown_source_keeps_transcode_kbps():
    assert _kbps_args(4500, {"bit_rate": "20000000"})[0] == 4500
    assert _kbps_args(4500, {}, bitrate_kbps=0)[0] == 4500
    assert _kbps_args(5000, {"tags": {"BPS-eng": "not a number"}})[0] == 5000


def test_a_tiny_source_still_gets_the_floor():
    assert _kbps_args(4500, {"bit_rate": "300000"})[0] == 1500
    # TRANSCODE_KBPS below the floor wins.
    assert _kbps_args(1000, {"bit_rate": "300000"})[0] == 1000


# ---- Funnel's relay shared by the viewers coming over it (FUNNEL_BUDGET_KBPS)
def _funnel(budget=6000, transcode_kbps=4500, max_copy_kbps=5500):
    from dataclasses import replace
    return replace(get_settings(), tailscale_funnel=True, funnel_budget_kbps=budget,
                   transcode_kbps=transcode_kbps, max_copy_kbps=max_copy_kbps)


def _info(codec="hevc", video_kbps=4000, total_kbps=None):
    from server.media import ProbeInfo
    return ProbeInfo(duration=1440, size=1, start_time=0, format_name="matroska",
                     bitrate_kbps=total_kbps if total_kbps is not None else video_kbps + 200,
                     video={"codec_name": codec, "index": 0, "bit_rate": str(video_kbps * 1000)},
                     audio=[{"index": 1, "codec_name": "aac", "channels": 2}])


def test_the_funnel_budget_is_split_between_remote_viewers():
    from server.media import funnel_share, target_kbps
    cfg, info = _funnel(), _info(video_kbps=4000)  # alone: min(4500, 2 × 4000) = 4500
    assert [target_kbps(cfg, info, n) for n in (0, 1, 2, 3)] == [4500, 4500, 3000, 2000]
    assert target_kbps(cfg, info, 6) == 1500 and target_kbps(cfg, info, 10) == 1500  # the floor
    assert funnel_share(cfg, 0) == 0 and funnel_share(cfg, 4) == 1500
    # A light source stays at twice its own rate while that fits.
    assert target_kbps(cfg, _info(video_kbps=900), 3) == 1800
    # Without Funnel (no budget) the number changes nothing.
    from dataclasses import replace
    assert target_kbps(replace(cfg, funnel_budget_kbps=0), info, 5) == 4500


def test_copies_adding_up_past_the_budget_are_converted():
    cfg = _funnel()
    h264 = _info("h264", video_kbps=2300, total_kbps=2500)
    assert decide_mode(h264, cfg, 2)[0] == "copy"  # 5000 kbps in all
    mode, reason = decide_mode(h264, cfg, 3)  # 7500
    assert mode == "transcode" and "3 × 2500" in reason and "FUNNEL_BUDGET_KBPS=6000" in reason
    from dataclasses import replace
    assert decide_mode(h264, replace(cfg, funnel_budget_kbps=0), 3)[0] == "copy"
    session = MediaSession(cfg, MediaSource(kind="file", url="x.mkv", title="x", size=1, media_key="k"), h264,
                           remote=3)
    assert session.mode == "transcode" and session.target_kbps == 2000
    pub = session.public()
    assert pub["funnelViewers"] == 3 and pub["targetKbps"] == 2000
    alone = MediaSession(cfg, MediaSource(kind="file", url="x.mkv", title="x", size=1, media_key="k"), h264,
                         remote=1)
    assert alone.mode == "copy" and alone.public()["funnelViewers"] is None


class _Stream:
    """Just enough of an HlsStream for can_serve: 100 s made, finished."""

    def __init__(self, session):
        self.mode, self.kbps, self.audio = session.mode, session.target_kbps, session.audio
        self.id, self.running = "fake00000001", False

    def produced(self):
        return 100.0

    def ended(self):
        return True

    def stop(self):
        pass


def test_a_stream_made_for_another_number_of_viewers_is_not_served():
    session = MediaSession(_funnel(), MediaSource(kind="file", url="x.mkv", title="x", size=1, media_key="k"),
                           _info(video_kbps=4000), remote=1)
    session.stream = _Stream(session)
    assert session.can_serve(50)
    assert not session.set_remote(1) and session.can_serve(50)  # the same: nothing to do
    assert session.plan_for(2) == ("transcode", 3000)
    assert session.set_remote(2) and not session.can_serve(50)  # 4500 kbps made, 3000 wanted
    assert session.notified_remote == 2
    session.stream = _Stream(session)
    assert session.can_serve(50) and session.stream.kbps == 3000
    # Down again: a restart would give the better picture back.
    assert session.set_remote(0) and session.target_kbps == 4500
