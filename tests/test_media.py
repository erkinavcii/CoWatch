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
