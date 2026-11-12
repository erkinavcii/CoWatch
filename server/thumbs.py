"""Small pictures over the seek bar: sparse frames of the film packed into sprite sheets.

One ffmpeg run per film, in the background after it opens, at low priority:

    -skip_frame nokey -i film  ->  fps=1/interval, scale=160:h, tile=10x10  ->  sheet_000.jpg ...

Only keyframes are decoded (a fraction of the film's frames), so a 50-minute film takes seconds
and does not crowd the encode of the stream being watched. The picture shown for a moment is
the keyframe at or just before it: a few seconds off at most, enough to find a scene.

The sheets live in data/thumbs/<media key>/ with index.json (interval, tile size, count), so
a film opened again later has them at once. The 20 films used last are kept, older ones go.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable, Optional

from .config import Settings
from .media import HW_DECODE_CODECS, MediaSession, ProbeInfo, _ffmpeg_out, pick_encoder, pick_hwaccel

log = logging.getLogger("cowatch.thumbs")

THUMB_W = 160  # px, every tile
COLS, ROWS = 10, 10  # tiles per sheet
MAX_FRAMES = 300  # a long film gets a longer interval instead of more pictures
MIN_INTERVAL_S = 10.0
SHORT_FRAMES = 20  # a clip shorter than 200 s still gets about this many pictures
KEEP = 20  # films whose pictures are kept
START_DELAY_S = 10.0  # after the film opens: the stream's first segments come first
TIMEOUT_S = 1800.0
KEY = re.compile(r"[A-Za-z0-9_-]{1,64}")
SHEET = re.compile(r"sheet_\d{3}\.jpg")
INDEX = "index.json"


def interval_for(duration: float) -> float:
    """Seconds between pictures: 10, longer for a film over 50 minutes (300 pictures at most),
    shorter for a short clip (about 20 pictures, at least 1 s apart)."""
    if duration <= 0:
        return MIN_INTERVAL_S
    short = max(1.0, round(duration / SHORT_FRAMES, 2))
    return max(min(MIN_INTERVAL_S, short), float(math.ceil(duration / MAX_FRAMES)))


def tile_height(info: ProbeInfo) -> int:
    """The tile's height for a 160 px wide tile, by the picture's display aspect (even, for JPEG)."""
    width = int(info.video.get("width") or 16)
    height = int(info.video.get("height") or 9)
    sar = str(info.video.get("sample_aspect_ratio") or "1:1")
    try:
        num, den = (int(x) for x in sar.split(":"))
        ratio = num / den if num > 0 and den > 0 else 1.0
    except ValueError:
        ratio = 1.0
    aspect = width * ratio / max(1, height)
    return max(2, min(4 * THUMB_W, round(THUMB_W / aspect / 2) * 2))


def frame_count(duration: float, interval: float) -> int:
    """fps=1/interval gives a picture for t = 0, interval, 2 interval... below the end."""
    return max(1, math.ceil(duration / interval)) if duration > 0 else 0


def build_command(cfg: Settings, source: str, info: ProbeInfo, out_dir: Path, interval: float,
                  height: int, hwaccel: Optional[str] = None) -> list[str]:
    cmd = [cfg.ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-y"]
    if hwaccel:
        cmd += ["-hwaccel", hwaccel]
    if source.startswith(("http://", "https://")):
        cmd += ["-reconnect", "1", "-reconnect_on_network_error", "1", "-reconnect_delay_max", "10"]
    rate = f"1000/{max(1, round(interval * 1000))}"
    vf = (f"fps={rate},scale={THUMB_W}:{height}:flags=bilinear,setsar=1,format=yuvj420p,"
          f"tile={COLS}x{ROWS}")
    cmd += ["-skip_frame", "nokey", "-threads", "2", "-i", source, "-map", f"0:{info.video['index']}",
            "-an", "-sn", "-dn", "-vf", vf, "-q:v", "5", "-start_number", "0",
            _ffmpeg_out(out_dir / "sheet_%03d.jpg")]
    return cmd


def _creation_flags() -> int:
    if os.name != "nt":
        return 0
    return subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS


def _lower_priority() -> None:  # POSIX: the playing stream's ffmpeg goes first
    try:
        os.nice(10)
    except OSError:
        pass


class ThumbStore:
    """data/thumbs: one folder per film, made by `make`, the oldest beyond KEEP deleted."""

    def __init__(self, root: Path, keep: int = KEEP):
        self.root = root
        self.keep = keep
        self._index: dict[str, dict] = {}
        self.proc: Optional[subprocess.Popen] = None

    def folder(self, key: str) -> Path:
        return self.root / key

    def index(self, key: str) -> Optional[dict]:
        if not KEY.fullmatch(key or ""):
            return None
        if key not in self._index:
            try:
                data = json.loads((self.folder(key) / INDEX).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None
            if not isinstance(data, dict) or not data.get("count"):
                return None
            self._index[key] = data
        return self._index[key]

    def public(self, key: str) -> Optional[dict]:
        """What the page needs, or None until the pictures are made."""
        data = self.index(key)
        if data is None:
            return None
        fields = ("interval", "cols", "rows", "w", "h", "count", "sheets")
        return {"url": f"/api/thumbs/{key}/", **{k: data[k] for k in fields}}

    def file(self, key: str, name: str) -> Optional[Path]:
        """A sheet of a film that has pictures; nothing else (strict names, no other folder)."""
        if not KEY.fullmatch(key or "") or not SHEET.fullmatch(name or ""):
            return None
        data = self.index(key)
        if data is None or int(name[6:9]) >= data["sheets"]:
            return None
        path = self.folder(key) / name
        return path if path.is_file() else None

    def touch(self, key: str) -> None:
        """Opened again: the film's pictures count as used now (KEEP goes by this)."""
        try:
            os.utime(self.folder(key) / INDEX)
        except OSError:
            pass

    def prune(self, current: Optional[str] = None) -> list[str]:
        """Deletes the pictures of all but the KEEP films used last, and leftovers of unfinished runs."""
        if not self.root.is_dir():
            return []
        made: list[tuple[float, Path]] = []
        for path in self.root.iterdir():
            if not path.is_dir():
                continue
            if path.name.startswith(".tmp-"):
                if time.time() - path.stat().st_mtime > TIMEOUT_S:
                    shutil.rmtree(path, ignore_errors=True)
                continue
            try:
                made.append(((path / INDEX).stat().st_mtime, path))
            except OSError:
                shutil.rmtree(path, ignore_errors=True)  # no index: an old run that did not finish
        made.sort(reverse=True)
        removed = []
        for _, path in made[self.keep:]:
            if path.name == current:
                continue
            shutil.rmtree(path, ignore_errors=True)
            self._index.pop(path.name, None)
            removed.append(path.name)
        return removed

    async def make(self, cfg: Settings, source: str, info: ProbeInfo, key: str,
                   hwaccel: Optional[str] = None) -> Optional[dict]:
        """Makes the film's sheets (a few seconds for a local file) and returns its index."""
        if not KEY.fullmatch(key) or info.duration <= 0:
            return None
        interval = interval_for(info.duration)
        height = tile_height(info)
        tmp = self.root / f".tmp-{key}"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        try:
            for accel in ([hwaccel, None] if hwaccel else [None]):
                ok, error = await self._run(build_command(cfg, source, info, tmp, interval, height, accel))
                if ok:
                    break
                log.info("thumbnails%s failed: %s", f" with {accel}" if accel else "", error)
                for old in tmp.glob("sheet_*.jpg"):
                    old.unlink(missing_ok=True)
            sheets = len(list(tmp.glob("sheet_*.jpg")))
            if not sheets:
                return None
            count = min(frame_count(info.duration, interval), sheets * COLS * ROWS)
            data = {"interval": interval, "cols": COLS, "rows": ROWS, "w": THUMB_W, "h": height,
                    "count": count, "sheets": sheets, "duration": round(info.duration, 3)}
            (tmp / INDEX).write_text(json.dumps(data), encoding="utf-8")
            final = self.folder(key)
            shutil.rmtree(final, ignore_errors=True)
            tmp.rename(final)
            self._index[key] = data
            log.info("thumbnails: %d pictures every %gs in %.1f s", count, interval, time.monotonic() - started)
            self.prune(current=key)
            return data
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    async def _run(self, cmd: list[str]) -> tuple[bool, str]:
        try:
            proc = subprocess.Popen(
                cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                creationflags=_creation_flags(), preexec_fn=_lower_priority if os.name != "nt" else None,
            )
        except OSError as exc:
            return False, str(exc)
        self.proc = proc
        try:
            _, err = await asyncio.to_thread(proc.communicate, None, TIMEOUT_S)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return False, "took too long"
        except BaseException:  # cancelled: another film, or the server stops
            proc.kill()
            raise
        finally:
            self.proc = None
        text = (err or b"").decode("utf-8", "replace").strip()
        return proc.returncode == 0, text[-300:]


class ThumbMaker:
    """When to make the pictures of the film that opened: a file on this computer after
    START_DELAY_S; a torrent once it has fully downloaded (asked again every 5 s by the
    caller, like the subtitles inside a file); an add-on's web address never (that would read
    the whole film from someone else's server once more). One run at a time, once per film per
    server run; a new film cancels the run for the old one."""

    def __init__(self, cfg: Settings, store: ThumbStore):
        self.cfg = cfg
        self.store = store
        self.tried: set[str] = set()
        self.task: Optional[asyncio.Task] = None
        self.task_key: Optional[str] = None

    def soon(self, session: MediaSession, torrent_done: Callable, on_ready: Callable) -> None:
        key = session.source.media_key
        if self.store.index(key) is not None:
            if key not in self.tried:
                self.tried.add(key)
                self.store.touch(key)
            return
        if key in self.tried or session.source.kind == "url" or not KEY.fullmatch(key):
            return
        if self.task is not None and not self.task.done():
            if self.task_key == key:
                return
            self.task.cancel()  # the old film's run: it can start again when that film opens again
        self.task_key = key
        self.task = asyncio.create_task(self._make(session, torrent_done, on_ready))

    async def _make(self, session: MediaSession, torrent_done: Callable, on_ready: Callable) -> None:
        key = session.source.media_key
        try:
            if session.source.kind == "torrent" and not await torrent_done(session):
                return  # not all of it is here yet: the next look
            self.tried.add(key)
            await asyncio.sleep(START_DELAY_S)
            hwaccel = None
            if session.info.video_codec in HW_DECODE_CODECS:
                encoder = await asyncio.to_thread(pick_encoder, self.cfg)
                hwaccel = await asyncio.to_thread(pick_hwaccel, self.cfg, encoder)
            data = await self.store.make(self.cfg, session.source.url, session.info, key, hwaccel)
        except asyncio.CancelledError:
            self.tried.discard(key)
            raise
        except Exception:
            log.exception("thumbnails")
            return
        if data is not None:
            await on_ready(session)

    def stop(self) -> None:
        if self.task is not None and not self.task.done():
            self.task.cancel()
