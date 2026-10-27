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
