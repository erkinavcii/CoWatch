"""Stremio add-ons: catalogs, film and series details, streams and subtitles from any add-on
that speaks Stremio's protocol (an HTTP address serving JSON, starting at manifest.json).
https://github.com/Stremio/stremio-addon-sdk/blob/master/docs/protocol.md

Only add-ons that host no content themselves ship with Co-Watch (DEFAULT_ADDONS). The ones
the host adds are kept in data/addons.json, which is not in git.

Browsers never give the server an address to fetch: a stream or subtitle is opened by a
short reference to something an add-on returned (`ref`), so a viewer cannot make the server
request arbitrary URLs."""

from __future__ import annotations

import json
import re
import secrets
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import quote, urlencode

import httpx

DEFAULT_ADDONS = (
    "https://v3-cinemeta.strem.io/manifest.json",  # catalogs and details (posters, seasons, episodes)
    "https://caching.stremio.net/publicdomainmovies.now.sh/manifest.json",  # films out of copyright
)
RESOURCES = ("catalog", "meta", "stream", "subtitles")
TYPES = ("movie", "series")
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
CACHE_S = 300
MANIFEST_CACHE_S = 3600
# Public trackers for torrents whose add-on lists none; DHT finds peers too, but slower.
FALLBACK_TRACKERS = (
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.stealth.si:80/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "wss://tracker.openwebtorrent.com",
)
_INFO_HASH = re.compile(r"^[a-f0-9]{40}$")
_ID = re.compile(r"^[\w.:%-]{1,200}$")
# Stremio subtitle languages are ISO 639-2 (three letters); the rest of Co-Watch uses two.
_LANG_2 = {
    "eng": "en", "tur": "tr", "rus": "ru", "ger": "de", "deu": "de", "fre": "fr", "fra": "fr",
    "spa": "es", "ita": "it", "por": "pt", "pob": "pt-br", "ukr": "uk", "ara": "ar", "per": "fa",
    "fas": "fa", "aze": "az", "dut": "nl", "nld": "nl", "pol": "pl", "gre": "el", "ell": "el",
    "jpn": "ja", "kor": "ko", "chi": "zh", "zho": "zh", "swe": "sv", "nor": "no", "dan": "da",
    "fin": "fi", "ces": "cs", "cze": "cs", "hun": "hu", "rum": "ro", "ron": "ro", "bul": "bg",
    "heb": "he", "hin": "hi", "ind": "id", "vie": "vi", "tha": "th",
}


class AddonError(Exception):
    def __init__(self, message: str, code: str = "addon_error"):
        super().__init__(message)
        self.code = code


def subtitle_lang(code) -> str:
    text = str(code or "").strip().lower()
    return _LANG_2.get(text, text[:3] if re.fullmatch(r"[a-z]{2,3}", text) else "und")


def _text(value, limit: int = 300) -> str:
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", str(value or "")).strip()[:limit]


def _web_url(value) -> Optional[str]:
    text = str(value or "").strip()
    return text if re.match(r"^https?://", text) and len(text) < 2000 else None


def manifest_url(text: str) -> str:
    """What the host pasted, as a manifest address. Stremio's install links start with
    stremio://, which is the same address over https."""
    url = str(text or "").strip()
    if url.startswith("stremio://"):
        url = "https://" + url[len("stremio://"):]
    if not re.match(r"^https?://[^\s]+$", url):
        raise AddonError("not an add-on address", "addon_bad_url")
    if not url.endswith("/manifest.json"):
        url = url.rstrip("/") + "/manifest.json"
    return url


@dataclass
class Addon:
    url: str
    manifest: dict
    builtin: bool

    @property
    def base(self) -> str:
        return self.url[: -len("/manifest.json")]

    @property
    def id(self) -> str:
        return _text(self.manifest.get("id"), 120)

    @property
    def name(self) -> str:
        return _text(self.manifest.get("name"), 80) or self.id

    def _resource(self, name: str) -> Optional[dict]:
        for res in self.manifest.get("resources") or []:
            if res == name:
                return {"name": name}
            if isinstance(res, dict) and res.get("name") == name:
                return res
        return None

    def supports(self, resource: str, kind: str, item_id: str) -> bool:
        res = self._resource(resource)
        if res is None:
            return False
        types = res.get("types") or self.manifest.get("types") or []
        prefixes = res.get("idPrefixes", self.manifest.get("idPrefixes"))
        if types and kind not in types:
            return False
        return not prefixes or any(item_id.startswith(p) for p in prefixes)

    def catalogs(self) -> list[dict]:
        out = []
        for cat in self.manifest.get("catalogs") or []:
            kind, cat_id = cat.get("type"), cat.get("id")
            if kind not in TYPES or not isinstance(cat_id, str):
                continue
            extras = {e.get("name"): e for e in cat.get("extra") or [] if isinstance(e, dict)}
            extras.update({name: {"name": name} for name in cat.get("extraSupported") or []})
            # A catalog that requires an extra other than search (e.g. a list of ids) is not for browsing.
            required = {n for n, e in extras.items() if e.get("isRequired")} | set(cat.get("extraRequired") or [])
            if required - {"search"}:
                continue
            out.append({
                "addon": self.id, "type": kind, "id": cat_id,
                "name": _text(cat.get("name"), 60) or cat_id,
                "search": "search" in extras, "searchOnly": "search" in required,
                "genres": [_text(g, 40) for g in (extras.get("genre") or {}).get("options") or []][:60],
            })
        return out

    def public(self) -> dict:
        return {
            "url": self.url, "id": self.id, "name": self.name, "builtin": self.builtin,
            "description": _text(self.manifest.get("description"), 300),
            "resources": [r for r in RESOURCES if self._resource(r)],
            "catalogs": self.catalogs(),
        }


@dataclass
class AddonStore:
    path: Path  # data/addons.json: the add-ons the host added
    transport: Optional[httpx.AsyncBaseTransport] = None  # tests inject a mock transport here
    builtin: bool = True  # ADDONS_BUILTIN=0: without DEFAULT_ADDONS (the browser tests stay offline)
    _manifests: dict = field(default_factory=dict)  # url -> (time, manifest or None, error)
    _cache: dict = field(default_factory=dict)  # url -> (time, data)
    refs: "OrderedDict[str, dict]" = field(default_factory=OrderedDict)  # ref -> stream or subtitle

    # ---- the list ----------------------------------------------------------------
    def user_urls(self) -> list[str]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return []
        return [item["url"] for item in data if isinstance(item, dict) and isinstance(item.get("url"), str)]

    def _save(self, urls: list[str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps([{"url": u} for u in urls], indent=2), encoding="utf-8")

    def urls(self) -> list[tuple[str, bool]]:
        seen, out = set(), []
        defaults = DEFAULT_ADDONS if self.builtin else ()
        for url, builtin in [(u, True) for u in defaults] + [(u, False) for u in self.user_urls()]:
            if url not in seen:
                seen.add(url)
                out.append((url, builtin))
        return out

    async def addons(self) -> list[Addon]:
        out = []
        for url, builtin in self.urls():
            manifest, _error = await self._manifest(url)
            if manifest is not None:
                out.append(Addon(url, manifest, builtin))
        return out

    async def listing(self) -> list[dict]:
        out = []
        for url, builtin in self.urls():
            manifest, error = await self._manifest(url)
            if manifest is None:
                out.append({"url": url, "id": "", "name": url, "builtin": builtin, "error": error,
                            "resources": [], "catalogs": []})
            else:
                out.append(Addon(url, manifest, builtin).public())
        return out

    async def add(self, text: str) -> dict:
        url = manifest_url(text)
        if url in dict(self.urls()):
            raise AddonError("already added", "addon_exists")
        self._manifests.pop(url, None)
        manifest, error = await self._manifest(url)
        if manifest is None:
            raise AddonError(error or "manifest could not be read", "addon_unreachable")
        self._save(self.user_urls() + [url])
        return Addon(url, manifest, False).public()

    def remove(self, url: str) -> bool:
        urls = self.user_urls()
        if url not in urls:
            return False
        self._save([u for u in urls if u != url])
        self._manifests.pop(url, None)
        return True

    # ---- requests -------------------------------------------------------------------
    async def _fetch(self, url: str) -> dict:
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True, transport=self.transport,
                                         headers={"User-Agent": "CoWatch"}) as http:
                resp = await http.get(url)
        except httpx.HTTPError as exc:
            raise AddonError(f"request failed: {exc.__class__.__name__}", "addon_unreachable") from None
        if resp.status_code != 200:
            raise AddonError(f"add-on answered {resp.status_code}", "addon_unreachable")
        if len(resp.content) > MAX_RESPONSE_BYTES:
            raise AddonError("add-on answer too large", "addon_unreachable")
        try:
            data = resp.json()
        except ValueError:
            raise AddonError("add-on did not answer with JSON", "addon_unreachable") from None
        if not isinstance(data, dict):
            raise AddonError("add-on did not answer with an object", "addon_unreachable")
        return data

    async def _manifest(self, url: str) -> tuple[Optional[dict], Optional[str]]:
        cached = self._manifests.get(url)
        if cached and time.monotonic() - cached[0] < (MANIFEST_CACHE_S if cached[1] else 60):
            return cached[1], cached[2]
        try:
            manifest = await self._fetch(url)
            if not manifest.get("id") or not isinstance(manifest.get("resources"), list):
                raise AddonError("not a Stremio add-on manifest", "addon_unreachable")
            result = (manifest, None)
        except AddonError as exc:
            result = (None, str(exc))
        self._manifests[url] = (time.monotonic(), *result)
        return result

    async def _get(self, addon: Addon, resource: str, kind: str, item_id: str, extra: Optional[dict] = None) -> dict:
        path = f"/{resource}/{kind}/{quote(item_id, safe=':')}"
        extra = {k: v for k, v in (extra or {}).items() if v not in (None, "", 0)}
        if extra:
            path += "/" + urlencode(extra, quote_via=quote)
        url = f"{addon.base}{path}.json"
        cached = self._cache.get(url)
        if cached and time.monotonic() - cached[0] < CACHE_S:
            return cached[1]
        data = await self._fetch(url)
        self._cache[url] = (time.monotonic(), data)
        if len(self._cache) > 500:
            for old in sorted(self._cache, key=lambda k: self._cache[k][0])[:100]:
                del self._cache[old]
        return data

    def _remember(self, item: dict) -> str:
        ref = secrets.token_urlsafe(9)
        self.refs[ref] = item
        while len(self.refs) > 2000:
            self.refs.popitem(last=False)
        return ref

    def lookup(self, ref: str) -> Optional[dict]:
        return self.refs.get(str(ref or ""))

    # ---- resources --------------------------------------------------------------------
    @staticmethod
    def _check(kind: str, item_id: str) -> None:
        if kind not in TYPES or not _ID.match(item_id or ""):
            raise AddonError("bad type or id", "addon_bad_request")

    async def catalog(self, addon_id: str, kind: str, catalog_id: str, search: str = "", genre: str = "",
                      skip: int = 0) -> list[dict]:
        self._check(kind, catalog_id)
        addon = next((a for a in await self.addons() if a.id == addon_id), None)
        if addon is None:
            raise AddonError("unknown add-on", "addon_bad_request")
        data = await self._get(addon, "catalog", kind, catalog_id,
                               {"search": _text(search, 100), "genre": _text(genre, 40), "skip": max(0, int(skip))})
        out = []
        for meta in data.get("metas") or []:
            if isinstance(meta, dict) and _ID.match(str(meta.get("id", ""))):
                out.append(self._meta_card(meta, kind))
        return out[:200]

    @staticmethod
    def _meta_card(meta: dict, kind: str) -> dict:
        return {
            "id": str(meta["id"]), "type": meta.get("type") if meta.get("type") in TYPES else kind,
            "name": _text(meta.get("name"), 120), "poster": _web_url(meta.get("poster")),
            "year": _text(meta.get("releaseInfo") or meta.get("year"), 20),
            "rating": _text(meta.get("imdbRating"), 6),
        }

    async def meta(self, kind: str, item_id: str) -> Optional[dict]:
        self._check(kind, item_id)
        for addon in await self.addons():
            if not addon.supports("meta", kind, item_id):
                continue
            try:
                data = await self._get(addon, "meta", kind, item_id)
            except AddonError:
                continue
            meta = data.get("meta")
            if not isinstance(meta, dict):
                continue
            card = self._meta_card({**meta, "id": item_id}, kind)
            card["description"] = _text(meta.get("description"), 1500)
            card["background"] = _web_url(meta.get("background"))
            card["runtime"] = _text(meta.get("runtime"), 20)
            card["genres"] = [_text(g, 40) for g in (meta.get("genres") or meta.get("genre") or [])][:8]
            videos = []
            for video in meta.get("videos") or []:
                if not isinstance(video, dict) or not _ID.match(str(video.get("id", ""))):
                    continue
                season, episode = video.get("season"), video.get("episode", video.get("number"))
                videos.append({
                    "id": str(video["id"]),
                    "season": season if isinstance(season, int) else None,
                    "episode": episode if isinstance(episode, int) else None,
                    "name": _text(video.get("name") or video.get("title"), 120),
                    "released": _text(video.get("released") or video.get("firstAired"), 10),
                })
            card["videos"] = videos
            return card
        return None

    async def streams(self, kind: str, item_id: str, title: str = "") -> list[dict]:
        """Every playable stream any add-on knows for this film or episode. Each comes back
        with a `ref` for opening it; the address itself stays on the server."""
        self._check(kind, item_id)
        out = []
        for addon in await self.addons():
            if not addon.supports("stream", kind, item_id):
                continue
            try:
                data = await self._get(addon, "stream", kind, item_id)
            except AddonError:
                continue
            for stream in (data.get("streams") or [])[:200]:
                item = self._playable(stream)
                if item is None:
                    continue
                item.update({"addon": addon.name, "type": kind, "id": item_id, "title": _text(title, 150)})
                label = _text(stream.get("name"), 80)
                detail = _text(stream.get("title") or stream.get("description"), 300)
                out.append({"ref": self._remember(item), "addon": addon.name, "name": label,
                            "detail": detail, "kind": item["kind"]})
        return out

    @staticmethod
    def _playable(stream) -> Optional[dict]:
        if not isinstance(stream, dict):
            return None
        info_hash = str(stream.get("infoHash") or "").lower()
        if _INFO_HASH.match(info_hash):
            try:
                file_index = int(stream["fileIdx"]) if stream.get("fileIdx") is not None else None
            except (TypeError, ValueError):
                file_index = None
            trackers = [s[len("tracker:"):] for s in stream.get("sources") or []
                        if isinstance(s, str) and s.startswith("tracker:")]
            filename = _text((stream.get("behaviorHints") or {}).get("filename"), 200)
            return {"kind": "torrent", "infoHash": info_hash, "fileIndex": file_index,
                    "trackers": trackers[:20], "filename": filename}
        url = _web_url(stream.get("url"))
        if url:
            return {"kind": "url", "url": url,
                    "filename": _text((stream.get("behaviorHints") or {}).get("filename"), 200)}
        return None  # ytId, externalUrl: not something ffmpeg can play

    async def subtitles(self, kind: str, item_id: str, video_hash: Optional[str], video_size: int,
                        filename: str = "") -> list[dict]:
        self._check(kind, item_id)
        out = []
        extra = {"videoHash": video_hash or "", "videoSize": video_size or 0, "filename": _text(filename, 200)}
        for addon in await self.addons():
            if not addon.supports("subtitles", kind, item_id):
                continue
            try:
                data = await self._get(addon, "subtitles", kind, item_id, extra)
            except AddonError:
                continue
            for sub in (data.get("subtitles") or [])[:300]:
                url = _web_url(sub.get("url")) if isinstance(sub, dict) else None
                if not url:
                    continue
                lang = subtitle_lang(sub.get("lang"))
                ref = self._remember({"kind": "subtitle", "url": url, "lang": lang, "addon": addon.name})
                out.append({"ref": ref, "lang": lang, "addon": addon.name})
        return out

    async def download(self, url: str, limit: int) -> bytes:
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True, transport=self.transport,
                                         headers={"User-Agent": "CoWatch"}) as http:
                resp = await http.get(url)
        except httpx.HTTPError as exc:
            raise AddonError(f"download failed: {exc.__class__.__name__}", "addon_unreachable") from None
        if resp.status_code != 200:
            raise AddonError(f"download failed ({resp.status_code})", "addon_unreachable")
        if len(resp.content) > limit:
            raise AddonError("file too large", "file_too_large")
        return resp.content


def magnet(info_hash: str, name: str, trackers: list[str]) -> str:
    parts = [f"magnet:?xt=urn:btih:{info_hash}"]
    if name:
        parts.append("dn=" + quote(name))
    parts += ["tr=" + quote(t, safe="") for t in (trackers or list(FALLBACK_TRACKERS))]
    return "&".join(parts)


def episode_label(item_id: str) -> str:
    """tt0903747:1:2 -> S01E02, for the film title shown to everyone."""
    m = re.match(r"^[^:]+:(\d+):(\d+)$", item_id)
    return f"S{int(m.group(1)):02d}E{int(m.group(2)):02d}" if m else ""
