"""Co-Watch server: one room, one film, everyone with their own subtitles.

HTTP:  /            the web app (needs the access key once: /?k=KEY sets a cookie)
       /api/...     media, torrent and subtitle actions
       /hls/...     the HLS stream produced by ffmpeg
WS:    /ws          sync channel (state, members, clock pings)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import mimetypes
import re
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
import httpx
from pydantic import BaseModel
from starlette.websockets import WebSocketState

from .addons import AddonError, AddonStore, episode_label, magnet
from .config import get_settings
from . import filepicker
from .media import MediaError, MediaSession, MediaSource, clean_title, clear_hls_dir, probe
from .oshash import CHUNK, hash_file, hash_from_chunks
from .presence import PALETTE, POKE_INTERVAL_S, pick_color, point, stroke_message
from .room import Client, Room, now_ms
from .signaling import ice_servers, rtc_data
from .subtitles import (
    MAX_SUBTITLE_BYTES,
    OpenSubtitlesClient,
    OpenSubtitlesError,
    SubtitleError,
    SubtitleStore,
    decode_bytes,
    parse_cues,
    pick_best,
    to_vtt,
)
from .torrent_client import HelperError, TorrentHelper

log = logging.getLogger("cowatch")

COOKIE = "cw_key"
LANG_RE = re.compile(r"^[a-z]{2,3}(-[a-z]{2,4})?$")
LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}
# Set by a reverse proxy in front of us. Tailscale Serve adds Tailscale-User-Login (and drops
# forged copies) and X-Forwarded-For; any of them means the request came from someone else.
PROXY_HEADERS = ("tailscale-user-login", "x-forwarded-for", "forwarded")

cfg = get_settings()


def clean_name(value) -> str:
    text = re.sub(r"[\x00-\x1f\x7f]", "", str(value or "")).strip()
    return text[:24] or "?"


async def url_hash(url: str) -> tuple[int, Optional[str]]:
    """Size and OpenSubtitles hash of a file behind an HTTP address, read with two range
    requests (first and last 64 KB). (0, None) if the server does not say its size or
    does not serve ranges; the film still plays, subtitles are then found by id or name."""
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as http:
            head = await http.head(url)
            size = int(head.headers.get("content-length") or 0)
            if size < CHUNK or head.headers.get("accept-ranges", "").lower() != "bytes":
                return size, None
            first = await http.get(url, headers={"Range": f"bytes=0-{CHUNK - 1}"})
            last = await http.get(url, headers={"Range": f"bytes={size - CHUNK}-{size - 1}"})
    except (httpx.HTTPError, ValueError):
        return 0, None
    if first.status_code != 206 or last.status_code != 206:
        return size, None
    return size, hash_from_chunks(size, first.content[:CHUNK], last.content[:CHUNK])


def local_path(text: Optional[str]) -> Path:
    """A file path typed or pasted by the host. Windows Explorer's "Copy as path" wraps it
    in double quotes; PowerShell users tend to paste single quotes."""
    return Path((text or "").strip().strip("\"'").strip()).expanduser()


class Controller:
    def __init__(self) -> None:
        self.room = Room()
        self.helper = TorrentHelper(cfg.helper_url)
        self.store = SubtitleStore(cfg.subs_dir)
        self.os = OpenSubtitlesClient(cfg.os_api_key, cfg.os_user_agent, cfg.os_username, cfg.os_password)
        self.addons = AddonStore(cfg.data_dir / "addons.json", builtin=cfg.addons_builtin)
        self.session: Optional[MediaSession] = None
        self.opening = False
        self.open_lock = asyncio.Lock()
        self.restart_target: Optional[float] = None
        self.restart_task: Optional[asyncio.Task] = None
        self.last_progress: dict = {}
        self.download_throttled = False
        self.tasks: list[asyncio.Task] = []
        self._relays: set[asyncio.Task] = set()

    # ---- messages -------------------------------------------------------------
    @property
    def ready(self) -> bool:
        return self.session is not None and self.session.stream is not None

    def media_public(self) -> Optional[dict]:
        return self.session.public() if self.ready else None

    def tracks(self) -> list[dict]:
        return self.store.list(self.session.source.media_key) if self.session else []

    async def status(self, key: str, level: str = "info", **params) -> None:
        await self.room.broadcast({"type": "status", "key": key, "level": level, "params": params})

    async def broadcast_state(self) -> None:
        await self.room.broadcast(self.room.state_msg())

    async def broadcast_media(self) -> None:
        await self.room.broadcast({"type": "media", "media": self.media_public()})
        if self.ready:
            self.last_progress = self.session.progress()
            await self.room.broadcast({"type": "progress", **self.last_progress})

    async def broadcast_tracks(self) -> None:
        await self.room.broadcast({"type": "subtitles", "tracks": self.tracks()})

    def welcome(self, client: Client) -> dict:
        return {
            "type": "welcome",
            "clientId": client.id,
            "serverTime": now_ms(),
            "state": self.room.state_msg(),
            "media": self.media_public(),
            "progress": self.session.progress() if self.ready else None,
            "members": self.room.members_msg()["members"],
            "tracks": self.tracks(),
            "osEnabled": self.os.enabled,
            "opening": self.opening,
            "palette": list(PALETTE),
            "iceServers": ice_servers(cfg.ice_servers),
        }

    def _relay(self, sender: Client, msg: dict, lossy: bool = False) -> None:
        """Pass a pointer or drawing message to everyone else without waiting for it, so a
        slow viewer never holds up the sender's own commands (play, pause, seek)."""
        task = asyncio.create_task(self.room.broadcast(msg, exclude=sender, lossy=lossy))
        self._relays.add(task)
        task.add_done_callback(self._relays.discard)

    def _relay_to(self, target: Client, msg: dict) -> None:
        """Like `_relay`, to one viewer. Messages to the same viewer keep their order: each send
        waits for the previous one on that viewer's lock, and the lock serves in turn."""
        task = asyncio.create_task(target.send(msg))
        self._relays.add(task)
        task.add_done_callback(self._relays.discard)

    @staticmethod
    def _set_av(client: Client, msg: dict) -> bool:
        mic, cam = bool(msg.get("mic")), bool(msg.get("cam"))
        changed = (mic, cam) != (client.mic, client.cam)
        client.mic, client.cam = mic, cam
        return changed

    # ---- websocket commands ---------------------------------------------------------
    async def handle(self, client: Client, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "ping":
            await client.send({"type": "pong", "t0": msg.get("t0"), "ts": now_ms()})
        elif kind == "cursor":
            if msg.get("hidden"):
                self._relay(client, {"type": "cursor", "from": client.id, "hidden": True})
            else:
                at = point(msg.get("x"), msg.get("y"))
                if at is not None:
                    self._relay(client, {"type": "cursor", "from": client.id, "x": at[0], "y": at[1]}, lossy=True)
        elif kind == "poke":
            at = point(msg.get("x"), msg.get("y"))
            now = time.monotonic()
            if at is not None and now - client.last_poke >= POKE_INTERVAL_S:
                client.last_poke = now
                self._relay(client, {"type": "poke", "from": client.id, "x": at[0], "y": at[1]})
        elif kind == "draw":
            out = stroke_message(msg, client.id, client.color or PALETTE[0])
            if out is not None:
                self._relay(client, out)
        elif kind == "draw_clear":
            self._relay(client, {"type": "draw_clear", "from": client.id})
        elif kind == "color":
            color = str(msg.get("color", "")).lower()
            if color in PALETTE and color != client.color:
                client.color = color
                await self.room.broadcast(self.room.members_msg())
        elif kind == "rtc":
            target = self.room.clients.get(str(msg.get("to", "")))
            data = rtc_data(msg.get("data"))
            if target is not None and target is not client and data is not None:
                self._relay_to(target, {"type": "rtc", "from": client.id, "data": data})
        elif kind == "av":
            if self._set_av(client, msg):
                await self.room.broadcast(self.room.members_msg())
        elif kind == "hello":
            client.name = clean_name(msg.get("name"))
            client.joined = True
            self._set_av(client, msg)
            taken = {c.color for c in self.room.clients.values() if c is not client and c.color}
            client.color = pick_color(msg.get("color"), taken)
            await self.room.broadcast(self.room.members_msg())
        elif kind == "buffering":
            value = bool(msg.get("value"))
            if self.room.set_buffering(client, value):
                if value:
                    # Pause everyone where the slow viewer stopped, so they miss nothing
                    # (at most 10 s back, in case the reported position is off).
                    try:
                        stalled_at = float(msg.get("position"))
                    except (TypeError, ValueError):
                        stalled_at = math.nan
                    if math.isfinite(stalled_at) and self.room.position - 10 <= stalled_at < self.room.position:
                        self.room.seek(stalled_at)
                await self.broadcast_state()
                await self.room.broadcast(self.room.members_msg())
        elif kind in ("play", "pause", "seek") and self.ready:
            if kind == "play":
                if self.room.current_position() >= self.session.duration - 1.0:
                    await self.seek(0.0)  # play again from the start
                if self.room.play():
                    await self.broadcast_state()
            elif kind == "pause" and self.room.pause():
                await self.broadcast_state()
            elif kind == "seek":
                try:
                    target = float(msg.get("position"))
                except (TypeError, ValueError):
                    return
                if math.isfinite(target):
                    await self.seek(target)

    async def seek(self, target: float) -> None:
        session = self.session
        if session is None:
            return
        target = max(0.0, min(target, max(0.0, session.duration - 0.5)))
        self.room.seek(target)
        if self.restart_task and not self.restart_task.done():
            self.restart_target = target  # picked up when the current restart finishes
            await self.broadcast_state()
            return
        if session.can_serve(target):
            await self.broadcast_state()
            return
        self.room.set_loading(True)
        await self.broadcast_state()
        await self.status("restarting", at=round(target))
        self.restart_target = target
        self.restart_task = asyncio.create_task(self._restart_loop(session))

    async def _restart_loop(self, session: MediaSession) -> None:
        try:
            while self.restart_target is not None and session is self.session:
                target = self.restart_target
                self.restart_target = None
                if session.can_serve(target, slack=0):
                    continue
                try:
                    async with session.lock:
                        await session.start_at(target)
                except Exception as exc:  # keep the room usable whatever happened
                    log.exception("stream restart failed")
                    await self.status("stream_error", "error", detail=str(exc)[:300])
                    break
        finally:
            if session is self.session:
                self.room.set_loading(False)
                await self.broadcast_media()
                await self.broadcast_state()

    # ---- opening media ------------------------------------------------------------
    async def _addon_torrent(self, stream: dict) -> dict:
        """Add an add-on's torrent to the helper and pick the file: the one the add-on named,
        else the largest video."""
        await self.status("torrent_adding")
        info = await self.helper.add(magnet(stream["infoHash"], stream.get("filename") or stream.get("title"),
                                            stream.get("trackers") or []))
        files = info.get("files", [])
        index = stream.get("fileIndex")
        if index is None or not any(f["index"] == index for f in files):
            videos = [f for f in files if f.get("isVideo")] or files
            if not videos:
                raise ValueError("no files in torrent")
            index = max(videos, key=lambda f: f["length"])["index"]
        return {"infoHash": info.get("infoHash", stream["infoHash"]), "fileIndex": index}

    async def _resolve_source(self, torrent: Optional[dict], path: Optional[str],
                              stream: Optional[dict] = None) -> MediaSource:
        if stream and stream["kind"] == "torrent":
            source = await self._resolve_source(await self._addon_torrent(stream), None)
        elif stream:
            await self.status("reading_hash")
            size, moviehash = await url_hash(stream["url"])
            key = moviehash or hashlib.sha1(stream["url"].encode()).hexdigest()[:16]
            source = MediaSource(kind="url", url=stream["url"], title=stream.get("filename") or "", size=size,
                                 media_key=key, moviehash=moviehash)
        if stream:
            source.content_type, source.content_id = stream["type"], stream["id"]
            name = stream.get("title") or ""
            if name:
                episode = episode_label(stream["id"])
                source.title = f"{name} {episode}".strip() if episode and episode not in name else name
            return source
        if torrent:
            info_hash = str(torrent.get("infoHash", "")).lower()
            index = int(torrent.get("fileIndex", -1))
            info = await self.helper.prepare(info_hash, index)
            entry = next((f for f in info.get("files", []) if f["index"] == index), None)
            if entry is None:
                raise ValueError("file not found in torrent")
            size = int(entry["length"])
            moviehash = None
            try:
                await self.status("reading_hash")
                head = await self.helper.read_range(info_hash, index, 0, min(CHUNK, size) - 1, timeout=180)
                tail = await self.helper.read_range(info_hash, index, max(0, size - CHUNK), size - 1, timeout=180)
                moviehash = hash_from_chunks(size, head, tail)
            except HelperError as exc:
                log.warning("could not hash torrent file: %s", exc)
            key = moviehash or hashlib.sha1(f"{info_hash}:{index}".encode()).hexdigest()[:16]
            return MediaSource(
                kind="torrent", url=self.helper.file_url(info_hash, index), title=entry["name"], size=size,
                media_key=key, moviehash=moviehash, info_hash=info_hash, file_index=index,
            )
        file_path = local_path(path)
        if not file_path.is_file():
            raise ValueError(f"file not found: {file_path}")
        moviehash = await asyncio.to_thread(hash_file, file_path)
        return MediaSource(
            kind="file", url=str(file_path.resolve()), title=file_path.name, size=file_path.stat().st_size,
            media_key=moviehash, moviehash=moviehash,
        )

    async def open_media(self, torrent: Optional[dict] = None, path: Optional[str] = None,
                         audio: Optional[int] = None, stream: Optional[dict] = None) -> None:
        async with self.open_lock:
            self.opening = True
            try:
                await self.status("opening")
                source = await self._resolve_source(torrent, path, stream)
                await self.status("probing")
                info = await probe(cfg, source.url, timeout=240)
                session = MediaSession(cfg, source, info, audio)
                await self.status("stream_starting", mode=session.mode, reason=session.mode_reason)
                await session.start_at(0.0)
            except (MediaError, HelperError, OSError, ValueError) as exc:
                log.warning("open failed: %s", exc)
                await self.status("open_failed", "error", detail=str(exc)[:300])
                return
            finally:
                self.opening = False
            old, self.session = self.session, session
            if old is not None:
                old.stop()
            self.restart_target = None
            self.download_throttled = False
            self.room.reset()
            # State first: clients pick their start position from it when the new stream loads.
            await self.broadcast_state()
            await self.broadcast_media()
            await self.broadcast_tracks()
            await self.status("stream_ready", mode=session.mode, title=source.title)

    async def close_media(self) -> None:
        if self.session is not None:
            self.session.stop()
            self.session = None
        self.room.reset()
        await self.broadcast_media()
        await self.broadcast_state()
        await self.broadcast_tracks()

    # ---- subtitles ------------------------------------------------------------------
    def _require_session(self) -> MediaSession:
        if self.session is None:
            raise HTTPException(409, detail="no_media")
        return self.session

    async def add_uploaded_subtitle(self, data: bytes, filename: str, lang: str, label: str) -> dict:
        session = self._require_session()
        cues = parse_cues(decode_bytes(data, lang))
        track = self.store.add(session.source.media_key, lang, label or filename, "upload", cues,
                               extra={"fileName": filename})
        await self.broadcast_tracks()
        return track

    async def search_subtitles(self, languages: list[str]) -> dict:
        session = self._require_session()
        if not self.os.enabled:
            raise HTTPException(400, detail="os_not_configured")
        langs: list[str] = []
        for lang in languages:
            code = lang.strip().lower()
            if LANG_RE.match(code) and code not in langs:
                langs.append(code)
        if not langs:
            raise HTTPException(400, detail="no_languages")
        langs = langs[:5]

        results: list[dict] = []
        if session.source.moviehash:
            results += await self.os.search(langs, moviehash=session.source.moviehash)
        missing = [lang for lang in langs if pick_best(results, lang) is None]
        content_id = session.source.content_id or ""
        if missing and content_id.startswith("tt"):  # opened from an add-on: the film's id beats its title
            results += await self.os.search(missing, imdb_id=content_id)
            missing = [lang for lang in missing if pick_best(results, lang) is None]
        if missing:
            results += await self.os.search(missing, query=clean_title(session.source.title))

        added, not_found = [], []
        for lang in langs:
            best = pick_best(results, lang)
            if best is None:
                not_found.append(lang)
                continue
            attrs = best["attributes"]
            file_id = attrs["files"][0]["file_id"]
            existing = self.store.find(session.source.media_key, fileId=file_id)
            if existing:
                added.append(existing)
                continue
            data, meta = await self.os.download(file_id)
            cues = parse_cues(decode_bytes(data, lang))
            release = (attrs.get("release") or attrs["files"][0].get("file_name") or "").strip()
            track = self.store.add(
                session.source.media_key, lang, release[:80] or "OpenSubtitles", "opensubtitles", cues,
                extra={"fileId": file_id, "hashMatch": bool(attrs.get("moviehash_match")),
                       "remaining": meta.get("remaining")},
            )
            added.append(track)
        await self.broadcast_tracks()
        return {"added": added, "notFound": not_found}

    async def addon_subtitles(self) -> list[dict]:
        """Subtitles the add-ons offer for the open film, found by its id and file hash."""
        session = self._require_session()
        src = session.source
        if not src.content_id:
            return []
        found = await self.addons.subtitles(src.content_type, src.content_id, src.moviehash, src.size, src.title)
        added = {t.get("url") for t in self.tracks()}
        for sub in found:
            item = self.addons.lookup(sub["ref"])
            sub["added"] = bool(item and item["url"] in added)
        return found

    async def add_addon_subtitle(self, ref: str) -> dict:
        session = self._require_session()
        item = self.addons.lookup(ref)
        if not item or item.get("kind") != "subtitle":
            raise HTTPException(404, detail="unknown_subtitle")
        existing = self.store.find(session.source.media_key, url=item["url"])
        if existing:
            return existing
        data = await self.addons.download(item["url"], MAX_SUBTITLE_BYTES)
        cues = parse_cues(decode_bytes(data, item["lang"]))
        track = self.store.add(session.source.media_key, item["lang"], item["addon"], "addon", cues,
                               extra={"url": item["url"]})
        await self.broadcast_tracks()
        return track

    # ---- background loops ---------------------------------------------------------------
    async def progress_loop(self) -> None:
        while True:
            await asyncio.sleep(2)
            try:
                await self._check_progress()
            except Exception:
                log.exception("progress loop")

    async def _check_progress(self) -> None:
        session = self.session
        if session is None or session.stream is None:
            return
        if self.room.running() and session.duration and self.room.current_position() >= session.duration - 0.2:
            # End of the film: stop the clock instead of running past the end.
            self.room.pause()
            self.room.seek(session.duration)
            await self.broadcast_state()
        progress = session.progress()
        if progress != self.last_progress:
            self.last_progress = progress
            await self.room.broadcast({"type": "progress", **progress})
        stream = session.stream
        restarting = self.restart_task is not None and not self.restart_task.done()
        if stream.running or progress["ended"] or restarting:
            return
        # ffmpeg died before the end of the film: restart where the room is.
        if session.auto_restarts < 3:
            session.auto_restarts += 1
            target = self.room.current_position()
            log.warning("ffmpeg exited (%s), restarting at %.1f", stream.returncode, target)
            await self.status("stream_recovering", "error", detail=stream.log_tail(3))
            self.room.seek(target)
            self.room.set_loading(True)
            await self.broadcast_state()
            self.restart_target = target
            self.restart_task = asyncio.create_task(self._restart_loop(session))
        elif session.auto_restarts == 3:
            session.auto_restarts += 1
            await self.status("stream_error", "error", detail=stream.log_tail(4))

    async def watchdog_loop(self) -> None:
        """A client stuck buffering for too long no longer holds the room."""
        while True:
            await asyncio.sleep(1)
            for client in self.room.expired_buffering():
                log.info("ignoring buffering client %s", client.name)
                if self.room.set_buffering(client, False):
                    await self.broadcast_state()
                    await self.room.broadcast(self.room.members_msg())

    async def throttle_loop(self) -> None:
        """Slow the torrent down once ffmpeg is far ahead of playback, so the
        download does not crowd the host's connection (bufferbloat)."""
        while True:
            await asyncio.sleep(5)
            try:
                session = self.session
                if session is None or session.source.kind != "torrent" or session.stream is None:
                    if self.download_throttled:
                        await self.helper.throttle(download_kb=0)
                        self.download_throttled = False
                    continue
                lead = session.produced_end() - self.room.current_position()
                if not self.download_throttled and lead > 600:
                    rate_kb = max(256, int(session.info.bitrate_kbps / 8 * 1.5))
                    await self.helper.throttle(download_kb=rate_kb)
                    self.download_throttled = True
                elif self.download_throttled and lead < 240:
                    await self.helper.throttle(download_kb=0)
                    self.download_throttled = False
            except HelperError:
                pass
            except Exception:
                log.exception("throttle loop")


ctl = Controller()


def _key_ok(value: Optional[str]) -> bool:
    return bool(value) and secrets.compare_digest(value.encode(), cfg.access_key.encode())


def authorized(conn) -> bool:
    return _key_ok(conn.cookies.get(COOKIE)) or _key_ok(conn.query_params.get("k"))


def host_name(value: str) -> str:
    """The name part of a Host header: "localhost:8000" -> "localhost", "[::1]:8000" -> "::1"."""
    value = value.strip().lower()
    if value.startswith("["):
        return value[1:].split("]", 1)[0]
    return value.rsplit(":", 1)[0] if value.count(":") == 1 else value


def is_local(request: Request) -> bool:
    """The host at this computer, opening the localhost link. Tailscale Serve also connects
    from 127.0.0.1, so the address alone is not enough: the Host header must be a local name
    and no proxy header may be present."""
    if not request.client or request.client.host not in LOCAL_HOSTS:
        return False
    if host_name(request.headers.get("host", "")) not in LOCAL_HOSTS:
        return False
    return not any(name in request.headers for name in PROXY_HEADERS)


def _setup_logging() -> None:
    logger = logging.getLogger("cowatch")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%H:%M:%S"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _setup_logging()
    clear_hls_dir(cfg)
    ctl.tasks = [
        asyncio.create_task(ctl.progress_loop()),
        asyncio.create_task(ctl.watchdog_loop()),
        asyncio.create_task(ctl.throttle_loop()),
    ]
    yield
    for task in ctl.tasks:
        task.cancel()
    if ctl.session is not None:
        ctl.session.stop()


app = FastAPI(title="Co-Watch", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def require_key(request: Request, call_next):
    path = request.url.path
    if (path.startswith("/api/") or path.startswith("/hls/")) and not authorized(request):
        return JSONResponse({"detail": "unauthorized"}, status_code=401)
    return await call_next(request)


UNAUTHORIZED_PAGE = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Co-Watch</title><body style="font-family:system-ui;background:#111;color:#ddd;display:grid;place-items:center;height:100vh;margin:0">
<div style="max-width:28rem;padding:1rem"><h2>Co-Watch</h2>
<p>Bu link geçersiz ya da eksik. Davet linkini tekrar aç.</p>
<p>This link is invalid or incomplete. Open the invite link again.</p>
<p>Ссылка недействительна. Откройте ссылку-приглашение ещё раз.</p></div></body>"""


@app.get("/", include_in_schema=False)
async def index(request: Request):
    key = request.query_params.get("k")
    if key is not None:
        if not _key_ok(key):
            return HTMLResponse(UNAUTHORIZED_PAGE, status_code=401)
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(COOKIE, key, max_age=60 * 60 * 24 * 30, httponly=True, samesite="lax")
        return response
    if not authorized(request):
        return HTMLResponse(UNAUTHORIZED_PAGE, status_code=401)
    return FileResponse(cfg.web_dir / "index.html", headers={"Cache-Control": "no-cache"})


# Windows can map .js/.css to odd types through the registry; browsers then refuse them.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")


class FreshStaticFiles(StaticFiles):
    """Without Cache-Control, browsers reuse app.js for a while without asking, so after a
    `git pull` a normal refresh could still run the old client. `no-cache` makes them ask
    every time; unchanged files answer with a quick 304."""

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/static", FreshStaticFiles(directory=cfg.web_dir), name="static")

HLS_FILE = re.compile(r"^(index\.m3u8|init\.mp4|seg_\d{5}\.m4s)$")


@app.get("/hls/{stream_id}/{name}", include_in_schema=False)
async def hls_file(stream_id: str, name: str):
    if not re.fullmatch(r"[a-f0-9]{12}", stream_id) or not HLS_FILE.match(name):
        raise HTTPException(404)
    path = cfg.hls_dir / stream_id / name
    if name.endswith(".m3u8"):
        try:
            data = path.read_bytes()  # ffmpeg replaces this file while we serve it
        except FileNotFoundError:
            raise HTTPException(404) from None
        except PermissionError:  # Windows: caught mid-replace; hls.js simply retries
            raise HTTPException(503) from None
        return Response(data, media_type="application/vnd.apple.mpegurl", headers={"Cache-Control": "no-cache"})
    if not path.is_file():
        raise HTTPException(404)
    media_type = "video/mp4" if name.endswith(".mp4") else "video/iso.segment"
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "private, max-age=3600"})


# ---- API ------------------------------------------------------------------------------------
class MagnetBody(BaseModel):
    magnet: str
    peers: Optional[list[str]] = None


class TorrentRef(BaseModel):
    infoHash: str
    fileIndex: int


class OpenBody(BaseModel):
    torrent: Optional[TorrentRef] = None
    path: Optional[str] = None
    audio: Optional[int] = None
    stream: Optional[str] = None  # a `ref` from /api/addons/streams


class AddonBody(BaseModel):
    url: str


class PickBody(BaseModel):
    title: str = "Co-Watch"


class RefBody(BaseModel):
    ref: str


class SearchBody(BaseModel):
    languages: list[str]


@app.get("/api/status")
async def api_status(request: Request):
    session = ctl.session
    torrent = None
    if session is not None and session.source.kind == "torrent":
        try:
            torrent = await ctl.helper.info(session.source.info_hash)
            torrent.pop("files", None)
        except HelperError:
            torrent = None
    return {
        "media": ctl.media_public(),
        "progress": session.progress() if ctl.ready else None,
        "torrent": torrent,
        "opening": ctl.opening,
        "helper": await ctl.helper.healthy(),
        "osEnabled": ctl.os.enabled,
        "isHost": is_local(request),
        "downloadThrottled": ctl.download_throttled,
    }


@app.post("/api/torrent/add")
async def api_torrent_add(body: MagnetBody):
    try:
        return await ctl.helper.add(body.magnet.strip(), body.peers)
    except HelperError as exc:
        raise HTTPException(exc.status if 400 <= exc.status < 600 else 502, detail=str(exc)) from None


@app.post("/api/media/open", status_code=202)
async def api_media_open(body: OpenBody, request: Request):
    if body.path and not is_local(request):
        raise HTTPException(403, detail="local_files_host_only")
    stream = None
    if body.stream:
        stream = ctl.addons.lookup(body.stream)
        if not stream or stream.get("kind") not in ("torrent", "url"):
            raise HTTPException(404, detail="unknown_stream")
    if not body.path and body.torrent is None and stream is None:
        raise HTTPException(400, detail="nothing_to_open")
    if ctl.opening:
        raise HTTPException(409, detail="already_opening")
    torrent = body.torrent.model_dump() if body.torrent else None
    asyncio.create_task(ctl.open_media(torrent=torrent, path=body.path, audio=body.audio, stream=stream))
    return {"ok": True}


@app.post("/api/media/pick")
async def api_media_pick(body: PickBody, request: Request):
    """Opens the file dialog on the host's screen; the path picked comes back to the host's
    browser, which then opens it like a typed path."""
    if not is_local(request):
        raise HTTPException(403, detail="local_files_host_only")
    try:
        return {"path": await asyncio.to_thread(filepicker.pick_video, body.title)}
    except filepicker.PickerError as exc:
        raise HTTPException(409 if exc.code == "picker_busy" else 501, detail=exc.code) from None


# ---- add-ons: everyone can browse and open; only the host changes the list ----------------------
def _addon_error(exc: AddonError) -> HTTPException:
    status = 400 if exc.code in ("addon_bad_url", "addon_bad_request", "addon_exists") else 502
    return HTTPException(status, detail=exc.code)


@app.get("/api/addons")
async def api_addons(request: Request):
    return {"addons": await ctl.addons.listing(), "canEdit": is_local(request)}


@app.post("/api/addons")
async def api_addon_add(body: AddonBody, request: Request):
    if not is_local(request):
        raise HTTPException(403, detail="addons_host_only")
    try:
        return await ctl.addons.add(body.url)
    except AddonError as exc:
        raise _addon_error(exc) from None


@app.delete("/api/addons")
async def api_addon_remove(url: str, request: Request):
    if not is_local(request):
        raise HTTPException(403, detail="addons_host_only")
    if not ctl.addons.remove(url):
        raise HTTPException(404, detail="unknown_addon")
    return {"ok": True}


@app.get("/api/addons/catalog")
async def api_addon_catalog(addon: str, type: str, id: str, search: str = "", genre: str = "", skip: int = 0):
    try:
        return {"metas": await ctl.addons.catalog(addon, type, id, search, genre, skip)}
    except AddonError as exc:
        raise _addon_error(exc) from None


@app.get("/api/addons/meta")
async def api_addon_meta(type: str, id: str):
    try:
        return {"meta": await ctl.addons.meta(type, id)}  # null: no add-on has details for it
    except AddonError as exc:
        raise _addon_error(exc) from None


@app.get("/api/addons/streams")
async def api_addon_streams(type: str, id: str, name: str = ""):
    try:
        return {"streams": await ctl.addons.streams(type, id, name)}
    except AddonError as exc:
        raise _addon_error(exc) from None


@app.get("/api/addons/subtitles")
async def api_addon_subtitles():
    try:
        return {"subtitles": await ctl.addon_subtitles()}
    except AddonError as exc:
        raise _addon_error(exc) from None


@app.post("/api/addons/subtitles")
async def api_addon_subtitle_add(body: RefBody):
    try:
        return await ctl.add_addon_subtitle(body.ref)
    except AddonError as exc:
        raise _addon_error(exc) from None
    except SubtitleError as exc:
        raise HTTPException(400, detail=f"bad_subtitle: {exc}") from None


@app.post("/api/media/close")
async def api_media_close():
    await ctl.close_media()
    return {"ok": True}


@app.get("/api/subtitles")
async def api_subtitles():
    return {"tracks": ctl.tracks()}


def _cues_or_404(track_id: str):
    session = ctl._require_session()
    try:
        return ctl.store.cues(session.source.media_key, track_id)
    except SubtitleError:
        raise HTTPException(404, detail="unknown_track") from None


@app.get("/api/subtitles/{track_id}.json")
async def api_subtitle_json(track_id: str):
    return {"id": track_id, "cues": _cues_or_404(track_id)}


@app.get("/api/subtitles/{track_id}.vtt")
async def api_subtitle_vtt(track_id: str):
    return Response(to_vtt(_cues_or_404(track_id)), media_type="text/vtt; charset=utf-8")


@app.post("/api/subtitles/upload")
async def api_subtitle_upload(file: UploadFile = File(...), lang: str = Form(...), label: str = Form("")):
    lang = lang.strip().lower()
    if not LANG_RE.match(lang):
        raise HTTPException(400, detail="bad_language")
    data = await file.read(MAX_SUBTITLE_BYTES + 1)
    if len(data) > MAX_SUBTITLE_BYTES:
        raise HTTPException(413, detail="file_too_large")
    try:
        track = await ctl.add_uploaded_subtitle(data, file.filename or "subtitle", lang, label.strip()[:80])
    except SubtitleError as exc:
        raise HTTPException(400, detail=f"bad_subtitle: {exc}") from None
    return track


@app.post("/api/subtitles/search")
async def api_subtitle_search(body: SearchBody):
    try:
        return await ctl.search_subtitles(body.languages)
    except OpenSubtitlesError as exc:
        raise HTTPException(502, detail=exc.code) from None
    except SubtitleError as exc:
        raise HTTPException(502, detail=f"bad_subtitle: {exc}") from None


@app.delete("/api/subtitles/{track_id}")
async def api_subtitle_delete(track_id: str):
    session = ctl._require_session()
    if not ctl.store.delete(session.source.media_key, track_id):
        raise HTTPException(404, detail="unknown_track")
    await ctl.broadcast_tracks()
    return {"ok": True}


# ---- WebSocket ---------------------------------------------------------------------------------
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    if not authorized(ws):
        await ws.close(code=4401)
        return
    await ws.accept()
    client = ctl.room.add(ws)
    await client.send(ctl.welcome(client))
    await ctl.room.broadcast(ctl.room.members_msg())
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if isinstance(msg, dict):
                await ctl.handle(client, msg)
    except WebSocketDisconnect:
        pass
    except Exception:
        # A viewer that vanished (browser closed, network gone) often first fails a send to
        # it; the socket is then marked closed and receiving raises a RuntimeError, not
        # WebSocketDisconnect. That is a normal leave, not an error.
        if WebSocketState.DISCONNECTED not in (ws.client_state, ws.application_state):
            log.exception("websocket error")
    finally:
        changed = ctl.room.remove(client.id)
        await ctl.room.broadcast(ctl.room.members_msg())
        if changed:
            await ctl.broadcast_state()
