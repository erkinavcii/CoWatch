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
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path, PurePath
from typing import Optional

from .addons import subtitle_lang
from .config import Settings

log = logging.getLogger("cowatch.media")

BROWSER_PIX_FMTS = {"yuv420p", "yuvj420p"}
# Subtitles inside a video file that are text (MKV's SRT and ASS, MP4's mov_text): these become
# tracks. Picture subtitles (Blu-ray PGS, DVD) cannot be turned into text.
TEXT_SUBTITLE_CODECS = {"subrip", "srt", "ass", "ssa", "webvtt", "mov_text", "text"}

# encoder -> (extra args, pixel format it wants)
# The graphics card encoders make -force_key_frames frames plain I frames unless told to make
# them IDR; the HLS muxer cuts only at IDR, so segments came out as long as the card's GOP
# (10.4 s with NVENC instead of 4 s): slower start and coarser seeking.
ENCODER_PRESETS: dict[str, tuple[list[str], str]] = {
    "libx264": (["-preset", "veryfast", "-tune", "film", "-profile:v", "high"], "yuv420p"),
    "h264_nvenc": (["-preset", "p5", "-rc", "vbr", "-profile:v", "high", "-forced-idr", "1"], "yuv420p"),
    "h264_qsv": (["-preset", "veryfast", "-profile:v", "high", "-forced_idr", "1"], "nv12"),
    "h264_amf": (["-quality", "balanced", "-profile:v", "high", "-forced_idr", "1"], "nv12"),
    "h264_videotoolbox": (["-profile:v", "high", "-allow_sw", "1"], "nv12"),
}
SOFTWARE_ENCODER = "libx264"
# Tried in this order with VIDEO_ENCODER=auto: NVIDIA, Intel, AMD (Apple's on a Mac).
HARDWARE_ENCODERS = ("h264_videotoolbox",) if sys.platform == "darwin" else ("h264_nvenc", "h264_qsv", "h264_amf")
_encoders: dict[str, str] = {}  # ffmpeg -> the encoder chosen for it
_encoders_lock = threading.Lock()

# Decoding on the graphics card. A 4K HEVC 10-bit film took 30 s of CPU time per 20 s of film to
# decode in software, 6.7 s with NVIDIA's decoder (cuda) and 11.5 s with Windows' own (d3d11va).
# Asked for by name, a decoder ffmpeg cannot open stops ffmpeg with an error (it does not fall
# back by itself): the test at start and the fallback in MediaSession.start_at rely on that. A
# card that opens but cannot decode one particular film's profile is fine: ffmpeg decodes that
# film in software.
HW_DECODE_CODECS = {"h264", "hevc", "av1", "vp9"}
_hwaccels: dict[tuple[str, str], Optional[str]] = {}  # (ffmpeg, encoder) -> decoder, None = CPU

# HDR films converted to SDR (normal colours), else they look grey and washed out on an ordinary
# screen. "libplacebo" does it on the graphics card through Vulkan, also scales there, and reads
# Dolby Vision; "zscale" does it on the CPU (2.4 cores busy for a 1080p picture here), and gets
# only HDR10 and HLG right, not a Dolby Vision-only film (profile 5).
HDR_TRANSFERS = {"smpte2084", "arib-std-b67"}  # PQ (HDR10, Dolby Vision 8.1) and HLG
_tonemaps: dict[str, Optional[str]] = {}  # ffmpeg -> "libplacebo" | "zscale" | None


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
        timeout=timeout, stdin=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
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
    subtitles: list[dict] = field(default_factory=list)  # the text subtitle streams in the file

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
        subtitles=[s for s in streams if s.get("codec_type") == "subtitle"
                   and s.get("codec_name") in TEXT_SUBTITLE_CODECS],
    )


async def extract_subtitles(cfg: Settings, source: str, streams: list[dict], timeout: float = 900) -> dict[int, str]:
    """The text of the given subtitle streams (stream index -> SRT or ASS text), in one ffmpeg
    pass. Subtitles are spread over the whole file, so this reads all of it."""
    with tempfile.TemporaryDirectory(prefix="cowatch-subs-") as tmp:
        cmd = [cfg.ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-i", source]
        outputs: dict[int, Path] = {}
        for stream in streams:
            fmt = "ass" if stream.get("codec_name") in ("ass", "ssa") else "srt"  # ASS keeps its line breaks
            out = Path(tmp) / f"{stream['index']}.{fmt}"
            cmd += ["-map", f"0:{stream['index']}", "-c:s", fmt, "-f", fmt, _ffmpeg_out(out)]
            outputs[stream["index"]] = out
        try:
            proc = await asyncio.to_thread(_run, cmd, timeout)
        except subprocess.TimeoutExpired as exc:
            raise MediaError("reading the subtitles took too long") from exc
        except FileNotFoundError as exc:
            raise MediaError(f"ffmpeg not found: {cfg.ffmpeg}") from exc
        texts = {}
        for index, out in outputs.items():
            try:
                text = out.read_text(encoding="utf-8", errors="replace")
            except FileNotFoundError:
                continue
            if text.strip():
                texts[index] = text
        if not texts and proc.returncode != 0:
            raise MediaError((proc.stderr or "ffmpeg failed").strip()[-300:])
        return texts


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


def encoder_works(ffmpeg: str, encoder: str, timeout: float = 20) -> bool:
    """A dozen frames through the encoder: ffmpeg lists the graphics card encoders it was built
    with even when this computer has no such card, or its driver is too old."""
    extra, pix_fmt = ENCODER_PRESETS.get(encoder, ([], "yuv420p"))
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=24",
           "-frames:v", "12", "-vf", f"format={pix_fmt}", "-c:v", encoder, *extra, "-b:v", "2000k", "-f", "null", "-"]
    try:
        return _run(cmd, timeout).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def pick_encoder(cfg: Settings) -> str:
    """The encoder for converting: VIDEO_ENCODER if it names one; with "auto" (the default) the
    first graphics card encoder that works here, else libx264 on the CPU. Tried once per ffmpeg
    (the server does it in the background at start); slow, so not on the event loop."""
    if cfg.video_encoder != "auto":
        return cfg.video_encoder
    with _encoders_lock:
        if cfg.ffmpeg not in _encoders:
            _encoders[cfg.ffmpeg] = next((e for e in HARDWARE_ENCODERS if encoder_works(cfg.ffmpeg, e)), SOFTWARE_ENCODER)
            log.info("video encoder: %s", _encoders[cfg.ffmpeg])
        return _encoders[cfg.ffmpeg]


def give_up_on(cfg: Settings, encoder: str) -> None:
    """A graphics card encoder that passed the test but failed on a real film: libx264 from now on."""
    with _encoders_lock:
        if cfg.video_encoder == "auto" and _encoders.get(cfg.ffmpeg) == encoder:
            _encoders[cfg.ffmpeg] = SOFTWARE_ENCODER


def hwaccel_candidates(encoder: str) -> list[str]:
    if sys.platform == "darwin":
        return ["videotoolbox"]
    if os.name == "nt":
        return (["cuda"] if encoder == "h264_nvenc" else []) + ["d3d11va"]
    return []  # Linux: VAAPI wants a device path; left to the CPU


def hwaccel_works(ffmpeg: str, hwaccel: str, encoder: str, timeout: float = 20) -> bool:
    """Twelve frames made with the working encoder, decoded with `hwaccel`."""
    extra, pix_fmt = ENCODER_PRESETS.get(encoder, ([], "yuv420p"))
    with tempfile.TemporaryDirectory(prefix="cowatch-hw-") as tmp:
        sample = str(Path(tmp) / "sample.mp4")
        make = [ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24",
                "-frames:v", "12", "-vf", f"format={pix_fmt}", "-c:v", encoder, *extra, "-b:v", "1000k", sample]
        decode = [ffmpeg, "-hide_banner", "-loglevel", "error", "-hwaccel", hwaccel, "-i", sample, "-f", "null", "-"]
        try:
            return _run(make, timeout).returncode == 0 and _run(decode, timeout).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False


def pick_hwaccel(cfg: Settings, encoder: str) -> Optional[str]:
    """HW_DECODE: "auto" (the default) tries the candidates for this encoder once per ffmpeg;
    "off" (or "cpu") decodes in software; anything else is passed to ffmpeg's -hwaccel as is."""
    choice = cfg.hw_decode
    if choice in ("off", "cpu", "none", "0"):
        return None
    if choice != "auto":
        return choice
    key = (cfg.ffmpeg, encoder)
    with _encoders_lock:
        if key not in _hwaccels:
            _hwaccels[key] = next((h for h in hwaccel_candidates(encoder) if hwaccel_works(cfg.ffmpeg, h, encoder)), None)
            log.info("video decoder: %s", _hwaccels[key] or "CPU")
        return _hwaccels[key]


def give_up_on_hwaccel(cfg: Settings, encoder: str) -> None:
    with _encoders_lock:
        if cfg.hw_decode == "auto":
            _hwaccels[(cfg.ffmpeg, encoder)] = None


def hdr_kind(info: ProbeInfo) -> Optional[str]:
    """"pq" or "hlg" for an HDR picture, "dovi" for Dolby Vision without an HDR10 base, else None."""
    transfer = info.video.get("color_transfer")
    if transfer == "smpte2084":
        return "pq"
    if transfer == "arib-std-b67":
        return "hlg"
    for side in info.video.get("side_data_list") or []:
        if side.get("side_data_type") == "DOVI configuration record":
            return "dovi"
    return None


def _tonemap_filter(kind: str, hlg: bool, max_height: int, pix_fmt: str) -> str:
    height = f"'min({max_height},ih)'"
    if kind == "libplacebo":
        return (f"libplacebo=w=-2:h={height}:colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv:"
                f"format={pix_fmt}:tonemapping=auto")
    # zscale needs the input's colours spelled out: frames often reach the filter without them.
    trc = "arib-std-b67" if hlg else "smpte2084"
    return (f"scale=-2:{height},setparams=color_primaries=bt2020:color_trc={trc}:colorspace=bt2020nc:range=tv,"
            "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=hable:desat=0,"
            f"zscale=t=bt709:m=bt709:r=tv,format={pix_fmt}")


def tonemap_works(ffmpeg: str, kind: str, timeout: float = 30) -> bool:
    """A few PQ frames through the filter: the filter may be missing from this ffmpeg build, or
    (libplacebo) there may be no Vulkan graphics card."""
    vf = "format=yuv420p10le," + _tonemap_filter(kind, False, 360, "yuv420p")
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", *_tonemap_device(kind),
           "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24", "-frames:v", "3", "-vf", vf, "-f", "null", "-"]
    try:
        return _run(cmd, timeout).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _tonemap_device(kind: Optional[str]) -> list[str]:
    return ["-init_hw_device", "vulkan=vk", "-filter_hw_device", "vk"] if kind == "libplacebo" else []


def pick_tonemap(cfg: Settings) -> Optional[str]:
    """HDR_TONEMAP: "auto" (the default) takes libplacebo if it works here, else zscale;
    "libplacebo" or "zscale" names one; "off" sends HDR films unconverted."""
    choice = cfg.hdr_tonemap
    if choice in ("off", "none", "0"):
        return None
    if choice in ("libplacebo", "zscale"):
        return choice
    with _encoders_lock:
        if cfg.ffmpeg not in _tonemaps:
            _tonemaps[cfg.ffmpeg] = next((k for k in ("libplacebo", "zscale") if tonemap_works(cfg.ffmpeg, k)), None)
            log.info("HDR tone mapping: %s", _tonemaps[cfg.ffmpeg] or "none")
        return _tonemaps[cfg.ffmpeg]


def give_up_on_tonemap(cfg: Settings, kind: str) -> Optional[str]:
    """libplacebo failed on a real film: zscale from now on (if it works). Returns the next one."""
    nxt = "zscale" if kind == "libplacebo" and tonemap_works(cfg.ffmpeg, "zscale") else None
    with _encoders_lock:
        if cfg.hdr_tonemap == "auto" and _tonemaps.get(cfg.ffmpeg) == kind:
            _tonemaps[cfg.ffmpeg] = nxt
    return nxt


def prepare_converting(cfg: Settings) -> None:
    """At start, in the background: find the encoder, the decoder for it and the HDR filter."""
    pick_hwaccel(cfg, pick_encoder(cfg))
    pick_tonemap(cfg)


def tonemap_for(info: ProbeInfo, kind: Optional[str]) -> Optional[str]:
    """The filter this film gets: none for SDR; zscale cannot read a Dolby Vision-only picture."""
    hdr = hdr_kind(info)
    if hdr is None or kind is None or (hdr == "dovi" and kind != "libplacebo"):
        return None
    return kind


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


TRANSCODE_FLOOR_KBPS = 1500  # the least a converted stream gets when the source is small
_BPS_TAG = re.compile(r"^BPS(-\w+)?$", re.IGNORECASE)  # MKV statistics tags: BPS, BPS-eng


def _stream_kbps(stream: dict) -> int:
    """A stream's bitrate: ffprobe's bit_rate, else the BPS tag MKV muxers write; 0 if unknown."""
    rate = _float(stream.get("bit_rate"))
    if not rate:
        rate = next((_float(v) for k, v in (stream.get("tags") or {}).items() if _BPS_TAG.match(str(k)) and _float(v)),
                    None)
    return int((rate or 0) / 1000)


def source_video_kbps(info: ProbeInfo) -> int:
    """The source's video bitrate: the video stream's own, else the whole file's minus its
    sound tracks; 0 if neither is known."""
    own = _stream_kbps(info.video)
    if own > 0:
        return own
    if info.bitrate_kbps <= 0:
        return 0
    return max(0, info.bitrate_kbps - sum(_stream_kbps(a) for a in info.audio))


def target_kbps(cfg: Settings, info: Optional[ProbeInfo]) -> int:
    """A converted stream's video bitrate: TRANSCODE_KBPS, but no more than twice the source
    (at least TRANSCODE_FLOOR_KBPS), so a light x265 episode is not inflated past the uplink."""
    kbps = max(500, cfg.transcode_kbps)
    source = source_video_kbps(info) if info is not None else 0
    if source <= 0:
        return kbps
    return min(kbps, max(TRANSCODE_FLOOR_KBPS, source * 2))


def _video_args(cfg: Settings, mode: str, encoder: str = SOFTWARE_ENCODER, info: Optional[ProbeInfo] = None,
                tonemap: Optional[str] = None) -> list[str]:
    if mode == "copy":
        return ["-c:v", "copy"]
    extra, pix_fmt = ENCODER_PRESETS.get(encoder, ([], "yuv420p"))
    kbps = target_kbps(cfg, info)
    vf = (_tonemap_filter(tonemap, info is not None and hdr_kind(info) == "hlg", cfg.max_height, pix_fmt) if tonemap
          else f"scale=-2:'min({cfg.max_height},ih)',format={pix_fmt}")
    return [
        "-c:v", encoder, *extra,
        "-b:v", f"{kbps}k", "-maxrate", f"{int(kbps * 1.25)}k", "-bufsize", f"{kbps * 2}k",
        "-vf", vf,
        # A keyframe at least every segment; -copyts means t does not start at 0.
        "-force_key_frames", f"expr:if(isnan(prev_forced_t),1,gte(t,prev_forced_t+{cfg.hls_time}))",
    ]


def _audio_args(cfg: Settings) -> list[str]:
    args = ["-c:a", "aac", "-b:a", f"{cfg.audio_kbps}k", "-ac", "2"]
    if cfg.audio_filter:
        # Downmix to stereo first, then normalise the final mix.
        args += ["-af", f"aformat=channel_layouts=stereo,{cfg.audio_filter}"]
    return args


def _ffmpeg_out(path: PurePath) -> str:
    """Output path for ffmpeg, always with '/'. The HLS muxer puts init.mp4 next to the
    playlist by looking for the last '/' in the playlist path; with Windows backslashes it
    finds none and writes init.mp4 to the current directory instead."""
    return path.as_posix()


def build_command(
    cfg: Settings, source: str, out_dir: PurePath, start: float, mode: str,
    info: ProbeInfo, audio: Optional[dict], encoder: str = SOFTWARE_ENCODER,
    hwaccel: Optional[str] = None, tonemap: Optional[str] = None,
) -> list[str]:
    cmd = [cfg.ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "warning", "-y"]
    if mode == "transcode":
        cmd += _tonemap_device(tonemap)
        if hwaccel and info.video_codec in HW_DECODE_CODECS:
            cmd += ["-hwaccel", hwaccel]
    if source.startswith(("http://", "https://")):
        cmd += ["-reconnect", "1", "-reconnect_on_network_error", "1", "-reconnect_delay_max", "10"]
    if start > 0.001:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", source, "-map", f"0:{info.video['index']}"]
    if audio is not None:
        cmd += ["-map", f"0:{audio['index']}"]
    cmd += ["-sn", "-dn", "-map_metadata", "-1", "-map_chapters", "-1"]
    cmd += _video_args(cfg, mode, encoder, info, tonemap if mode == "transcode" else None)
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
        "-hls_segment_filename", _ffmpeg_out(out_dir / "seg_%05d.m4s"),
        "-hls_flags", "independent_segments+temp_file",
        _ffmpeg_out(out_dir / "index.m3u8"),
    ]
    return cmd


class HlsStream:
    """One ffmpeg run that writes an EVENT playlist starting at `start` seconds."""

    def __init__(self, cfg: Settings, source: str, out_dir: Path, start: float, mode: str,
                 info: ProbeInfo, audio: Optional[dict], encoder: str = SOFTWARE_ENCODER,
                 hwaccel: Optional[str] = None, tonemap: Optional[str] = None):
        self.cfg = cfg
        self.encoder = encoder
        self.hwaccel = hwaccel
        self.tonemap = tonemap
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
        cmd = build_command(self.cfg, self.source, self.out_dir, self.start, self.mode, self.info, self.audio,
                            self.encoder, self.hwaccel, self.tonemap)
        how = ", ".join(x for x in (self.hwaccel and f"decode {self.hwaccel}", self.encoder,
                                     self.tonemap and f"HDR {self.tonemap}") if x)
        log.info("ffmpeg start=%.1f mode=%s%s -> %s", self.start, self.mode,
                 f" ({how})" if self.mode == "transcode" else "", self.out_dir.name)
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

    def _finish_playlist_swap(self) -> None:
        """ffmpeg writes index.m3u8.tmp, then renames it over index.m3u8. On Windows that
        rename fails if we are reading the old file at that moment. For the last playlist
        ffmpeg then exits with the finished version (and its ENDLIST) still in the .tmp
        file, so finish the swap ourselves once it has exited cleanly."""
        if self.proc is None or self.proc.poll() != 0:
            return
        tmp = self.playlist_path.with_name(self.playlist_path.name + ".tmp")
        if tmp.exists():
            try:
                os.replace(tmp, self.playlist_path)
            except OSError:
                pass  # the old file is still open somewhere; the next read tries again

    def read_playlist(self) -> tuple[list[tuple[str, float]], bool]:
        self._finish_playlist_swap()
        text = None
        for _ in range(3):
            try:
                text = self.playlist_path.read_text(encoding="utf-8", errors="replace")
                break
            except FileNotFoundError:
                return [], False
            except PermissionError:  # Windows: ffmpeg is swapping the file in right now
                time.sleep(0.02)
        if text is None:
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
    kind: str  # "torrent" | "file" | "url" (a stream address from an add-on)
    url: str  # what ffmpeg reads
    title: str
    size: int
    media_key: str
    moviehash: Optional[str] = None
    info_hash: Optional[str] = None
    file_index: Optional[int] = None
    # Opened from an add-on: which film or episode it is (Stremio type and id, e.g.
    # "series", "tt0903747:1:2"), for finding its subtitles by id.
    content_type: Optional[str] = None
    content_id: Optional[str] = None


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
        self.encoder: Optional[str] = None  # converting: the encoder in use, picked at the first start
        self.hwaccel: Optional[str] = None  # converting: the graphics card decoder, None = the CPU
        self.tonemap: Optional[str] = None  # converting an HDR film: the filter making it SDR

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
        if self.mode == "transcode" and self.encoder is None:
            self.encoder = await asyncio.to_thread(pick_encoder, self.cfg)
            if self.info.video_codec in HW_DECODE_CODECS:
                self.hwaccel = await asyncio.to_thread(pick_hwaccel, self.cfg, self.encoder)
            if hdr_kind(self.info):
                self.tonemap = tonemap_for(self.info, await asyncio.to_thread(pick_tonemap, self.cfg))
        while True:
            out_dir = self.cfg.hls_dir / uuid.uuid4().hex[:12]
            stream = HlsStream(self.cfg, self.source.url, out_dir, target, self.mode, self.info, self.audio,
                               self.encoder or SOFTWARE_ENCODER, self.hwaccel, self.tonemap)
            stream.start_process()
            try:
                await stream.wait_ready(timeout=240)
                first_pts = await stream.measure_first_pts()
                break
            except BaseException as exc:  # a cancelled open too: no ffmpeg may be left running
                if not isinstance(exc, Exception):
                    stream.stop()
                    shutil.rmtree(out_dir, ignore_errors=True)
                    raise
                stream.stop()
                tail = stream.log_tail(3)
                shutil.rmtree(out_dir, ignore_errors=True)
                # The graphics card can still fail on a real film (a size or format it does not
                # take): once more without its decoder, then with the next HDR filter, then
                # encoding on the CPU.
                if self.mode == "transcode" and self.hwaccel:
                    log.warning("decoding with %s failed, on the CPU instead: %s", self.hwaccel, tail)
                    give_up_on_hwaccel(self.cfg, self.encoder or SOFTWARE_ENCODER)
                    self.hwaccel = None
                    continue
                if self.mode == "transcode" and self.tonemap:
                    nxt = await asyncio.to_thread(give_up_on_tonemap, self.cfg, self.tonemap)
                    log.warning("HDR with %s failed, %s instead: %s", self.tonemap, nxt or "unconverted", tail)
                    self.tonemap = tonemap_for(self.info, nxt)
                    continue
                if self.mode != "transcode" or self.encoder in (None, SOFTWARE_ENCODER):
                    raise
                log.warning("%s failed, converting with %s instead: %s", self.encoder, SOFTWARE_ENCODER, tail)
                give_up_on(self.cfg, self.encoder)
                self.encoder = SOFTWARE_ENCODER
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
        if self.stream is None or target < self.stream_start - 0.5 or self.stream.audio is not self.audio:
            return False
        end = self.produced_end()
        if target <= end:
            return True
        return self.stream.running and not self.stream.ended() and target <= end + slack

    @property
    def audio_index(self) -> Optional[int]:
        return next((i for i, a in enumerate(self.info.audio) if a is self.audio), None)

    def set_audio(self, index: int) -> bool:
        """Another sound track of the file (dubbed / original): the next stream carries it."""
        if not 0 <= index < len(self.info.audio):
            return False
        self.audio = self.info.audio[index]
        return True

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
            "content": {"type": self.source.content_type, "id": self.source.content_id}
            if self.source.content_id else None,
            "mode": self.mode,
            "modeReason": self.mode_reason,
            "encoder": self.encoder if self.mode == "transcode" else None,
            "decoder": self.hwaccel if self.mode == "transcode" else None,
            "toneMap": self.tonemap if self.mode == "transcode" else None,
            "hdr": hdr_kind(self.info),
            "videoCodec": self.info.video_codec,
            "width": self.info.video.get("width"),
            "height": self.info.video.get("height"),
            "bitrateKbps": self.info.bitrate_kbps,
            "targetKbps": target_kbps(self.cfg, self.info) if self.mode == "transcode" else None,
            "audio": {
                "codec": audio.get("codec_name"),
                "channels": audio.get("channels"),
                "language": (audio.get("tags") or {}).get("language"),
            } if audio else None,
            "audioIndex": self.audio_index,
            "audioTracks": [{
                "lang": subtitle_lang((a.get("tags") or {}).get("language")),
                "title": str((a.get("tags") or {}).get("title") or "")[:60],
                "codec": a.get("codec_name"),
                "channels": a.get("channels"),
            } for a in self.info.audio],
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
