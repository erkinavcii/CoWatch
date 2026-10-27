"""Subtitles: decoding (legacy code pages), parsing to cues, a per-film store, and OpenSubtitles."""

from __future__ import annotations

import codecs
import json
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Optional

import httpx
import pysubs2
from charset_normalizer import from_bytes

log = logging.getLogger("cowatch.subtitles")

MAX_SUBTITLE_BYTES = 5 * 1024 * 1024

# Code pages that old subtitle files for a language usually use, tried after UTF-8.
LEGACY_CODEPAGES: dict[str, list[str]] = {
    "tr": ["cp1254"], "az": ["cp1254"],
    "ru": ["cp1251", "koi8_r"], "uk": ["cp1251", "koi8_u"], "be": ["cp1251"],
    "bg": ["cp1251"], "sr": ["cp1251", "cp1250"], "mk": ["cp1251"],
    "pl": ["cp1250"], "cs": ["cp1250"], "sk": ["cp1250"], "hu": ["cp1250"],
    "ro": ["cp1250"], "hr": ["cp1250"], "sl": ["cp1250"], "bs": ["cp1250"],
    "el": ["cp1253"], "he": ["cp1255"], "ar": ["cp1256"], "fa": ["cp1256"],
    "et": ["cp1257"], "lv": ["cp1257"], "lt": ["cp1257"], "vi": ["cp1258"], "th": ["cp874"],
    "zh": ["gb18030", "big5"], "ja": ["cp932"], "ko": ["cp949"],
    "en": ["cp1252"], "de": ["cp1252"], "fr": ["cp1252"], "es": ["cp1252"], "it": ["cp1252"],
    "pt": ["cp1252"], "nl": ["cp1252"], "sv": ["cp1252"], "da": ["cp1252"], "no": ["cp1252"],
    "fi": ["cp1252"],
}

_ASS_DRAWING = re.compile(r"\{[^}]*\\p[1-9]")
_HTML_TAG = re.compile(r"</?[a-zA-Z][^>]*>")


class SubtitleError(Exception):
    pass


def base_lang(lang: Optional[str]) -> str:
    return (lang or "").strip().lower().replace("_", "-").split("-")[0]


def decode_bytes(data: bytes, lang: Optional[str] = None) -> str:
    """UTF-8 first, then the language's legacy code page, then detection."""
    if data.startswith(codecs.BOM_UTF8):
        return data[len(codecs.BOM_UTF8):].decode("utf-8", errors="replace")
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    for encoding in LEGACY_CODEPAGES.get(base_lang(lang), []):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    best = from_bytes(data).best()
    if best is not None:
        return str(best)
    return data.decode("cp1252", errors="replace")


Cue = tuple[float, float, str]


def parse_cues(text: str) -> list[Cue]:
    """Any format pysubs2 understands (SRT, ASS/SSA, VTT, MicroDVD...) -> sorted plain-text cues."""
    try:
        subs = pysubs2.SSAFile.from_string(text, fps=23.976)
    except Exception as exc:  # pysubs2 raises several error types
        raise SubtitleError(f"unreadable subtitle file: {exc}") from exc
    seen: set[Cue] = set()
    cues: list[Cue] = []
    for event in subs.events:
        if event.is_comment or event.end <= event.start or _ASS_DRAWING.search(event.text):
            continue
        plain = _HTML_TAG.sub("", event.plaintext.replace("\r", "")).strip()
        plain = re.sub(r"\n{2,}", "\n", plain)
        if not plain:
            continue
        cue = (round(event.start / 1000, 3), round(event.end / 1000, 3), plain)
        if cue not in seen:
            seen.add(cue)
            cues.append(cue)
    cues.sort(key=lambda c: (c[0], c[1]))
    if not cues:
        raise SubtitleError("no subtitle lines found")
    return cues


def _vtt_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{secs:06.3f}"


def to_vtt(cues: list[Cue]) -> str:
    lines = ["WEBVTT", ""]
    for i, (start, end, text) in enumerate(cues, 1):
        safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        lines += [str(i), f"{_vtt_time(start)} --> {_vtt_time(end)}", safe, ""]
    return "\n".join(lines)


class SubtitleStore:
    """data/subs/<media_key>/index.json + one JSON file of cues per track."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _dir(self, media_key: str) -> Path:
        safe = re.sub(r"[^a-zA-Z0-9_-]", "_", media_key)[:64]
        return self.root / safe

    def _index_path(self, media_key: str) -> Path:
        return self._dir(media_key) / "index.json"

    def list(self, media_key: str) -> list[dict]:
        try:
            return json.loads(self._index_path(media_key).read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _write_index(self, media_key: str, tracks: list[dict]) -> None:
        path = self._index_path(media_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(tracks, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(path)

    def add(self, media_key: str, lang: str, label: str, source: str, cues: list[Cue],
            extra: Optional[dict] = None) -> dict:
        track_id = uuid.uuid4().hex[:10]
        folder = self._dir(media_key)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{track_id}.json").write_text(json.dumps(cues, ensure_ascii=False), encoding="utf-8")
        track = {
            "id": track_id,
            "lang": lang,
            "label": label,
            "source": source,
            "cues": len(cues),
            "created": int(time.time()),
            **(extra or {}),
        }
        tracks = self.list(media_key)
        tracks.append(track)
        self._write_index(media_key, tracks)
        return track

    def cues(self, media_key: str, track_id: str) -> list[Cue]:
        if not re.fullmatch(r"[a-f0-9]{10}", track_id):
            raise SubtitleError("bad track id")
        path = self._dir(media_key) / f"{track_id}.json"
        try:
            return [tuple(c) for c in json.loads(path.read_text(encoding="utf-8"))]
        except FileNotFoundError as exc:
            raise SubtitleError("unknown track") from exc

    def delete(self, media_key: str, track_id: str) -> bool:
        tracks = self.list(media_key)
        remaining = [t for t in tracks if t["id"] != track_id]
        if len(remaining) == len(tracks):
            return False
        self._write_index(media_key, remaining)
        (self._dir(media_key) / f"{track_id}.json").unlink(missing_ok=True)
        return True

    def find(self, media_key: str, **match) -> Optional[dict]:
        for track in self.list(media_key):
            if all(track.get(k) == v for k, v in match.items()):
                return track
        return None


class OpenSubtitlesError(Exception):
    def __init__(self, message: str, code: str = "os_error"):
        super().__init__(message)
        self.code = code


class OpenSubtitlesClient:
    """Small client for the OpenSubtitles REST API (api.opensubtitles.com/api/v1)."""

    DEFAULT_BASE = "https://api.opensubtitles.com/api/v1"

    def __init__(self, api_key: str, user_agent: str, username: str = "", password: str = "",
                 transport: Optional[httpx.AsyncBaseTransport] = None):
        self.api_key = api_key
        self.user_agent = user_agent
        self.username = username
        self.password = password
        self.base = self.DEFAULT_BASE
        self.token: Optional[str] = None
        self.transport = transport  # tests inject a mock transport here

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict:
        headers = {
            "Api-Key": self.api_key,
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def _login(self, http: httpx.AsyncClient) -> None:
        if self.token or not (self.username and self.password):
            return
        resp = await http.post(f"{self.base}/login", headers=self._headers(),
                               json={"username": self.username, "password": self.password})
        if resp.status_code != 200:
            raise OpenSubtitlesError(f"login failed ({resp.status_code})", "os_login_failed")
        data = resp.json()
        self.token = data.get("token")
        if data.get("base_url"):
            self.base = f"https://{data['base_url']}/api/v1"

    async def search(self, languages: list[str], moviehash: Optional[str] = None,
                     query: Optional[str] = None) -> list[dict]:
        if not self.enabled:
            raise OpenSubtitlesError("OpenSubtitles API key missing", "os_not_configured")
        # The API wants lower-case values and alphabetically sorted parameters.
        params: dict[str, str] = {"languages": ",".join(sorted({l.lower() for l in languages}))}
        if moviehash:
            params["moviehash"] = moviehash
        if query:
            params["query"] = query.lower()
        params = dict(sorted(params.items()))
        async with httpx.AsyncClient(timeout=30, follow_redirects=True, transport=self.transport) as http:
            resp = await http.get(f"{self.base}/subtitles", headers=self._headers(), params=params)
        if resp.status_code == 401:
            raise OpenSubtitlesError("API key rejected", "os_bad_key")
        if resp.status_code == 429:
            raise OpenSubtitlesError("too many requests", "os_rate_limited")
        if resp.status_code != 200:
            raise OpenSubtitlesError(f"search failed ({resp.status_code})")
        return resp.json().get("data") or []

    async def download(self, file_id: int) -> tuple[bytes, dict]:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True, transport=self.transport) as http:
            await self._login(http)
            resp = await http.post(f"{self.base}/download", headers=self._headers(), json={"file_id": file_id})
            if resp.status_code == 406:
                raise OpenSubtitlesError("daily download quota used up", "os_quota")
            if resp.status_code == 401 and self.token:
                self.token = None
                raise OpenSubtitlesError("session expired, try again", "os_login_failed")
            if resp.status_code != 200:
                raise OpenSubtitlesError(f"download failed ({resp.status_code})")
            meta = resp.json()
            link = meta.get("link")
            if not link:
                raise OpenSubtitlesError("no download link returned")
            file_resp = await http.get(link)
            if file_resp.status_code != 200:
                raise OpenSubtitlesError(f"file download failed ({file_resp.status_code})")
            if len(file_resp.content) > MAX_SUBTITLE_BYTES:
                raise OpenSubtitlesError("subtitle file too large")
            return file_resp.content, meta


def _score(item: dict) -> tuple:
    attrs = item.get("attributes") or {}
    machine = attrs.get("ai_translated") or attrs.get("machine_translated")
    return (
        1 if attrs.get("moviehash_match") else 0,
        0 if machine else 1,
        0 if attrs.get("hearing_impaired") else 1,
        attrs.get("download_count") or 0,
    )


def pick_best(results: list[dict], lang: str) -> Optional[dict]:
    wanted = lang.lower()
    candidates = [
        r for r in results
        if ((r.get("attributes") or {}).get("language") or "").lower() == wanted
        and (r.get("attributes") or {}).get("files")
    ]
    return max(candidates, key=_score) if candidates else None
