"""HLS details that differ on Windows. No ffmpeg needed."""

from pathlib import Path, PureWindowsPath

from server.config import get_settings
from server.main import local_path
from server.media import HlsStream, ProbeInfo, build_command

INFO = ProbeInfo(
    duration=60.0, size=1, start_time=0.0, format_name="matroska", bitrate_kbps=4000,
    video={"index": 0, "codec_name": "h264", "pix_fmt": "yuv420p"}, audio=[],
)
PLAYLIST = '#EXTM3U\n#EXT-X-MAP:URI="init.mp4"\n#EXTINF:4.000000,\nseg_00000.m4s\n'


def test_ffmpeg_output_paths_use_forward_slashes():
    # ffmpeg finds the folder for init.mp4 by the last '/' in the playlist path. With
    # backslashes it wrote init.mp4 to the working directory and playback broke on Windows.
    out = PureWindowsPath(r"C:\Users\me\CoWatch\data\hls\0123456789ab")
    cmd = build_command(get_settings(), r"C:\Films\Film.mkv", out, 0.0, "copy", INFO, None)
    assert cmd[-1] == "C:/Users/me/CoWatch/data/hls/0123456789ab/index.m3u8"
    assert cmd[cmd.index("-hls_segment_filename") + 1] == "C:/Users/me/CoWatch/data/hls/0123456789ab/seg_%05d.m4s"
    assert cmd[cmd.index("-i") + 1] == r"C:\Films\Film.mkv"  # the input is left as given


class _Exited:
    def __init__(self, code: int):
        self.code = code

    def poll(self) -> int:
        return self.code


def _stream(folder: Path, exit_code: int) -> HlsStream:
    stream = HlsStream(get_settings(), "film.mkv", folder, 0.0, "copy", INFO, None)
    stream.proc = _Exited(exit_code)
    return stream


def test_finishes_the_last_playlist_swap(tmp_path):
    # Windows: ffmpeg could not rename index.m3u8.tmp over index.m3u8 while we were reading it.
    (tmp_path / "index.m3u8").write_text(PLAYLIST)
    (tmp_path / "index.m3u8.tmp").write_text(PLAYLIST + "#EXTINF:2.000000,\nseg_00001.m4s\n#EXT-X-ENDLIST\n")
    stream = _stream(tmp_path, 0)
    assert stream.ended()
    assert stream.produced() == 6.0
    assert not (tmp_path / "index.m3u8.tmp").exists()


def test_leaves_the_tmp_playlist_alone_after_a_crash(tmp_path):
    (tmp_path / "index.m3u8").write_text(PLAYLIST)
    (tmp_path / "index.m3u8.tmp").write_text("#EXTM3U\n#EXTINF:4.0")  # cut off mid-write
    stream = _stream(tmp_path, 1)
    assert not stream.ended()
    assert stream.produced() == 4.0
    assert (tmp_path / "index.m3u8.tmp").exists()


def test_local_path_strips_pasted_quotes():
    assert local_path(' "C:\\Films\\My Film.mkv" ') == Path("C:\\Films\\My Film.mkv")
    assert local_path("'/films/a b.mkv'") == Path("/films/a b.mkv")
    assert local_path("samples/test-video.mkv") == Path("samples/test-video.mkv")
