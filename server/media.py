"""Probe a video, decide copy vs transcode, and run ffmpeg to produce an HLS (fMP4) stream.

Every client plays the same HLS stream. Timestamps are kept with -copyts, so after a
restart with -ss the stream still knows where it is in the film; we measure the first
segment's start time and send it to clients as `streamStart`:

    film time = video.currentTime + streamStart
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import Settings

log = logging.getLogger("cowatch.media")

BROWSER_PIX_FMTS = {"yuv420p", "yuvj420p"}

# encoder -> (extra args, pixel format it wants)
ENCODER_PRESETS: dict[str, tuple[list[str], str]] = {
    "libx264": (["-preset", "veryfast", "-tune", "film", "-profile:v", "high"], "yuv420p"),
    "h264_nvenc": (["-preset", "p5", "-rc", "vbr", "-profile:v", "high"], "yuv420p"),
    "h264_qsv": (["-preset", "veryfast", "-profile:v", "high"], "nv12"),
    "h264_amf": (["-quality", "balanced", "-profile:v", "high"], "nv12"),
    "h264_videotoolbox": (["-profile:v", "high", "-allow_sw", "1"], "nv12"),
}


class MediaError(Exception):
    pass


def _float(value) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None  # drop NaN


def _run(cmd: list[str], timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, stdin=subprocess.DEVNULL,
    )


@dataclass
class ProbeInfo:
    duration: float
    size: int
    start_time: float
    format_name: str
    bitrate_kbps: int
    video: dict
    audio: list[dict]

    @property
    def video_codec(self) -> str:
        return self.video.get("codec_name", "")


async def probe(cfg: Settings, source: str, timeout: float = 180) -> ProbeInfo:
    cmd = [cfg.ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", source]
    try:
        proc = await asyncio.to_thread(_run, cmd, timeout)
    except subprocess.TimeoutExpired as exc:
        raise MediaError("ffprobe timed out (torrent too slow?)") from exc
    except FileNotFoundError as exc:
        raise MediaError(f"ffprobe not found: {cfg.ffprobe}") from exc
    if proc.returncode != 0:
        raise MediaError((proc.stderr or "ffprobe failed").strip()[-400:])

    data = json.loads(proc.stdout or "{}")
    fmt = data.get("format") or {}
    streams = data.get("streams") or []
    videos = [
        s for s in streams
        if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")
    ]
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    if not videos:
        raise MediaError("no video stream found")

    duration = _float(fmt.get("duration")) or _float(videos[0].get("duration")) or 0.0
    size = int(_float(fmt.get("size")) or 0)
    bitrate = _float(fmt.get("bit_rate"))
    if not bitrate and size and duration:
        bitrate = size * 8 / duration
    return ProbeInfo(
        duration=duration,
        size=size,
        start_time=_float(fmt.get("start_time")) or 0.0,
        format_name=fmt.get("format_name", ""),
        bitrate_kbps=int((bitrate or 0) / 1000),
        video=videos[0],
        audio=audios,
    )


def choose_audio(info: ProbeInfo, preferred: Optional[int] = None) -> Optional[dict]:
    """`preferred` is an index into info.audio; otherwise the default-flagged track, else the first."""
    if not info.audio:
        return None
    if preferred is not None and 0 <= preferred < len(info.audio):
        return info.audio[preferred]
    for stream in info.audio:
        if (stream.get("disposition") or {}).get("default"):
            return stream
    return info.audio[0]


def decide_mode(info: ProbeInfo, cfg: Settings) -> tuple[str, str]:
    codec = info.video_codec
    if codec != "h264":
        return "transcode", f"video codec {codec or '?'} is not H.264"
    pix_fmt = info.video.get("pix_fmt")
    if pix_fmt and pix_fmt not in BROWSER_PIX_FMTS:
        return "transcode", f"pixel format {pix_fmt} does not play in browsers"
    if cfg.max_copy_kbps > 0 and info.bitrate_kbps > cfg.max_copy_kbps:
        return "transcode", f"{info.bitrate_kbps} kbps is above MAX_COPY_KBPS={cfg.max_copy_kbps}"
    return "copy", "H.264 source, sent without re-encoding"


def _video_args(cfg: Settings, mode: str) -> list[str]:
    if mode == "copy":
        return ["-c:v", "copy"]
    encoder = cfg.video_encoder
    extra, pix_fmt = ENCODER_PRESETS.get(encoder, ([], "yuv420p"))
    kbps = max(500, cfg.transcode_kbps)
    return [
        "-c:v", encoder, *extra,
        "-b:v", f"{kbps}k", "-maxrate", f"{int(kbps * 1.25)}k", "-bufsize", f"{kbps * 2}k",
        "-vf", f"scale=-2:'min({cfg.max_height},ih)',format={pix_fmt}",
        # A keyframe at least every segment; -copyts means t does not start at 0.
        "-force_key_frames", f"expr:if(isnan(prev_forced_t),1,gte(t,prev_forced_t+{cfg.hls_time}))",
    ]


def _audio_args(cfg: Settings) -> list[str]:
    args = ["-c:a", "aac", "-b:a", f"{cfg.audio_kbps}k", "-ac", "2"]
    if cfg.audio_filter:
        # Downmix to stereo first, then normalise the final mix.
        args += ["-af", f"aformat=channel_layouts=stereo,{cfg.audio_filter}"]
    return args


def build_command(
    cfg: Settings, source: str, out_dir: Path, start: float, mode: str,
    info: ProbeInfo, audio: Optional[dict],
) -> list[str]:
    cmd = [cfg.ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "warning", "-y"]
    if source.startswith(("http://", "https://")):
        cmd += ["-reconnect", "1", "-reconnect_on_network_error", "1", "-reconnect_delay_max", "10"]
    if start > 0.001:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", source, "-map", f"0:{info.video['index']}"]
    if audio is not None:
        cmd += ["-map", f"0:{audio['index']}"]
    cmd += ["-sn", "-dn", "-map_metadata", "-1", "-map_chapters", "-1"]
    cmd += _video_args(cfg, mode)
    if audio is not None:
        cmd += _audio_args(cfg)
    cmd += [
        "-copyts",
        "-max_muxing_queue_size", "4096",
        "-f", "hls",
        "-hls_time", str(cfg.hls_time),
        "-hls_list_size", "0",
        "-hls_playlist_type", "event",
        "-hls_segment_type", "fmp4",
        "-hls_fmp4_init_filename", "init.mp4",
        "-hls_segment_filename", str(out_dir / "seg_%05d.m4s"),
        "-hls_flags", "independent_segments+temp_file",
        str(out_dir / "index.m3u8"),
    ]
    return cmd


class HlsStream:
    """One ffmpeg run that writes an EVENT playlist starting at `start` seconds."""

    def __init__(self, cfg: Settings, source: str, out_dir: Path, start: float, mode: str,
                 info: ProbeInfo, audio: Optional[dict]):
        self.cfg = cfg
        self.source = source
        self.out_dir = out_dir
        self.id = out_dir.name
        self.start = start
        self.mode = mode
        self.info = info
        self.audio = audio
        self.proc: Optional[subprocess.Popen] = None
        self.first_pts: Optional[float] = None
        self._log_file = None

    @property
    def playlist_path(self) -> Path:
        return self.out_dir / "index.m3u8"

    def start_process(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        cmd = build_command(self.cfg, self.source, self.out_dir, self.start, self.mode, self.info, self.audio)
        log.info("ffmpeg start=%.1f mode=%s -> %s", self.start, self.mode, self.out_dir.name)
        self._log_file = open(self.out_dir / "ffmpeg.log", "w", encoding="utf-8", errors="replace")
        self._log_file.write(" ".join(cmd) + "\n\n")
        self._log_file.flush()
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            self.proc = subprocess.Popen(
                cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=self._log_file,
                creationflags=flags,
            )
        except FileNotFoundError as exc:
            raise MediaError(f"ffmpeg not found: {self.cfg.ffmpeg}") from exc

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    @property
    def returncode(self) -> Optional[int]:
        return self.proc.poll() if self.proc else None

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
        if self._log_file:
            self._log_file.close()
            self._log_file = None

    def read_playlist(self) -> tuple[list[tuple[str, float]], bool]:
        try:
            text = self.playlist_path.read_text(encoding="utf-8", errors="replace")
        except (FileNotFoundError, PermissionError):
            return [], False
        segments: list[tuple[str, float]] = []
        duration: Optional[float] = None
        for raw in text.splitlines():
            line = raw.strip()
            if line.startswith("#EXTINF:"):
                duration = _float(line[8:].split(",")[0])
            elif line and not line.startswith("#") and duration is not None:
                segments.append((line, duration))
                duration = None
        return segments, "#EXT-X-ENDLIST" in text

    def produced(self) -> float:
        segments, _ = self.read_playlist()
        return sum(d for _, d in segments)

    def ended(self) -> bool:
        return self.read_playlist()[1]

    def log_tail(self, lines: int = 12) -> str:
        try:
            text = (self.out_dir / "ffmpeg.log").read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            return ""
        return "\n".join(text.strip().splitlines()[-lines:])

    async def wait_ready(self, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            segments, _ = self.read_playlist()
            if segments:
                return
            if self.proc is not None and self.proc.poll() is not None:
                if self.read_playlist()[0]:
                    return
                raise MediaError("ffmpeg stopped: " + (self.log_tail(6) or f"exit code {self.proc.poll()}"))
            await asyncio.sleep(0.25)
        raise MediaError("timed out waiting for the first video segment")

    async def measure_first_pts(self) -> float:
        """Start time of the first segment in source timestamps (thanks to -copyts)."""
        segments, _ = self.read_playlist()
        if not segments:
            raise MediaError("no segment to measure")
        init = self.out_dir / "init.mp4"
        first = self.out_dir / segments[0][0]
        sample = self.out_dir / "probe-start.mp4"
        sample.write_bytes(init.read_bytes() + first.read_bytes())
        try:
            cmd = [self.cfg.ffprobe, "-v", "error", "-show_entries", "format=start_time",
                   "-of", "default=nw=1:nk=1", str(sample)]
            proc = await asyncio.to_thread(_run, cmd, 30)
        finally:
            sample.unlink(missing_ok=True)
        value = _float((proc.stdout or "").strip())
        if value is None:
            raise MediaError("could not read the stream start time")
        self.first_pts = value
        return value


@dataclass
class MediaSource:
    kind: str  # "torrent" | "file"
    url: str  # what ffmpeg reads
    title: str
    size: int
    media_key: str
    moviehash: Optional[str] = None
    info_hash: Optional[str] = None
    file_index: Optional[int] = None


class MediaSession:
    """The open film: its probe info and the HLS stream currently being produced."""

    def __init__(self, cfg: Settings, source: MediaSource, info: ProbeInfo, audio_index: Optional[int] = None):
        self.cfg = cfg
        self.source = source
        self.info = info
        self.mode, self.mode_reason = decide_mode(info, cfg)
        self.audio = choose_audio(info, audio_index)
        self.stream: Optional[HlsStream] = None
        self.stream_start = 0.0
        self.lock = asyncio.Lock()
        self.auto_restarts = 0

    @property
    def duration(self) -> float:
        return self.info.duration

    async def start_at(self, target: float) -> None:
        """Start a new ffmpeg run at `target` seconds and switch to it once it has a segment."""
        target = max(0.0, min(target, max(0.0, self.duration - 1.0)))
        if self.stream is not None:
            # Stop reading the old position right away: for a torrent, both ffmpeg runs
            # would otherwise compete for the same download bandwidth.
            self.stream.stop()
        out_dir = self.cfg.hls_dir / uuid.uuid4().hex[:12]
        stream = HlsStream(self.cfg, self.source.url, out_dir, target, self.mode, self.info, self.audio)
        stream.start_process()
        try:
            await stream.wait_ready(timeout=240)
            first_pts = await stream.measure_first_pts()
        except Exception:
            stream.stop()
            shutil.rmtree(out_dir, ignore_errors=True)
            raise
        old = self.stream
        self.stream = stream
        self.stream_start = max(0.0, first_pts - self.info.start_time)
        if old is not None:
            old.stop()
            _remove_later(old.out_dir)

    def stop(self) -> None:
        if self.stream is not None:
            self.stream.stop()
            _remove_later(self.stream.out_dir, delay=5)
            self.stream = None

    def produced_end(self) -> float:
        if self.stream is None:
            return 0.0
        return self.stream_start + self.stream.produced()

    def can_serve(self, target: float, slack: float = 10.0) -> bool:
        """True if seeking to `target` works without restarting ffmpeg. A target slightly
        past the produced part is fine (ffmpeg gets there soon); further away, restarting
        at the target is faster than waiting for everything in between."""
        if self.stream is None or target < self.stream_start - 0.5:
            return False
        end = self.produced_end()
        if target <= end:
            return True
        return self.stream.running and not self.stream.ended() and target <= end + slack

    def public(self) -> dict:
        audio = self.audio or {}
        stream = self.stream
        return {
            "streamId": stream.id if stream else None,
            "url": f"/hls/{stream.id}/index.m3u8" if stream else None,
            "streamStart": round(self.stream_start, 3),
            "duration": round(self.duration, 3),
            "title": self.source.title,
            "source": self.source.kind,
            "mediaKey": self.source.media_key,
            "mode": self.mode,
            "modeReason": self.mode_reason,
            "videoCodec": self.info.video_codec,
            "width": self.info.video.get("width"),
            "height": self.info.video.get("height"),
            "bitrateKbps": self.info.bitrate_kbps,
            "audio": {
                "codec": audio.get("codec_name"),
                "channels": audio.get("channels"),
                "language": (audio.get("tags") or {}).get("language"),
            } if audio else None,
        }

    def progress(self) -> dict:
        stream = self.stream
        return {
            "streamId": stream.id if stream else None,
            "producedEnd": round(self.produced_end(), 2),
            "ended": bool(stream and stream.ended()),
        }


def _remove_later(path: Path, delay: float = 60.0) -> None:
    """Delete an old stream folder after clients have had time to switch."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        shutil.rmtree(path, ignore_errors=True)
        return
    loop.call_later(delay, lambda: shutil.rmtree(path, ignore_errors=True))


def clear_hls_dir(cfg: Settings) -> None:
    if cfg.hls_dir.exists():
        shutil.rmtree(cfg.hls_dir, ignore_errors=True)
    cfg.hls_dir.mkdir(parents=True, exist_ok=True)


_TITLE_CUT = re.compile(
    r"\b(2160p|1080p|720p|480p|x264|x265|h\.?264|h\.?265|hevc|web[- .]?dl|webrip|bluray|brrip|"
    r"hdrip|dvdrip|hdtv|remux|proper|repack|10bit|dts|ac3|aac|ddp?5\.1)\b",
    re.IGNORECASE,
)


def clean_title(filename: str) -> str:
    """'The.Matrix.1999.1080p.BluRay.x264-GRP.mkv' -> 'The Matrix 1999'."""
    stem = Path(filename).stem
    text = re.sub(r"[._]+", " ", stem)
    year = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    if year:
        text = text[: year.end()]
    else:
        cut = _TITLE_CUT.search(text)
        if cut:
            text = text[: cut.start()]
    text = re.sub(r"[\[\(].*?[\]\)]", " ", text)
    return re.sub(r"\s+", " ", text).strip(" -") or stem
