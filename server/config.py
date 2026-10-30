"""Settings: the settings page's choices (data/settings.json), overridden by environment
variables and an optional .env file in the project root."""

from __future__ import annotations

import json
import os
import re
import secrets
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Mapping

ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path) -> None:
    """Minimal .env loader: KEY=VALUE lines, # comments. Existing env vars win."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        else:
            value = re.sub(r"\s+#.*$", "", value)  # inline comment
        os.environ.setdefault(key, value)


def _int(values: Mapping[str, str], name: str, default: int) -> int:
    value = values.get(name, "").strip()
    try:
        return int(float(value)) if value else default
    except ValueError:
        return default


def _str(values: Mapping[str, str], name: str, default: str = "") -> str:
    value = values.get(name)
    return value.strip() if value is not None else default


def _paths(values: Mapping[str, str], name: str) -> tuple[Path, ...]:
    """Folders separated by ";", like PATH on Windows (a "C:" drive rules out ":")."""
    return tuple(Path(p.strip().strip("\"'")).expanduser() for p in _str(values, name).split(";") if p.strip())


# ---- the settings page ------------------------------------------------------------------------
# What it saves in data/settings.json. Each choice stands for one or more of the variables
# below; a variable set in the environment or in .env wins, and the page shows the choice locked.
SETTINGS_FILE = "settings.json"
CHOICES = {
    "connection": ("funnel", "serve", "http"),
    "quality": ("auto", "original", "manual"),
    "mediaControl": ("everyone", "trusted"),
}
DEFAULTS = {
    "connection": "serve",  # funnel: link open to the internet · serve: friends with Tailscale · http: plain links
    "quality": "auto",  # auto: Funnel converts heavier files, Serve sends the original · original · manual
    "qualityMbps": 8,  # manual: files above this are converted to 80% of it
    "libraryDirs": [],
    "mediaControl": "everyone",
    "port": 8000,
    "torrentUploadLimit": 64,
    "iceServers": "",
    "osApiKey": "",
    "osUsername": "",
    "osPassword": "",
}
ENV_NAMES = {
    "connection": ("TAILSCALE_SERVE", "TAILSCALE_FUNNEL"),
    "quality": ("MAX_COPY_KBPS", "TRANSCODE_KBPS"),
    "qualityMbps": ("MAX_COPY_KBPS", "TRANSCODE_KBPS"),
    "libraryDirs": ("LIBRARY_DIRS",),
    "mediaControl": ("MEDIA_CONTROL",),
    "port": ("PORT",),
    "torrentUploadLimit": ("TORRENT_UPLOAD_LIMIT",),
    "iceServers": ("ICE_SERVERS",),
    "osApiKey": ("OPENSUBTITLES_API_KEY",),
    "osUsername": ("OPENSUBTITLES_USERNAME",),
    "osPassword": ("OPENSUBTITLES_PASSWORD",),
}
# Funnel's relay passed about 7-8 Mbps to a viewer in our measurement: on "auto", heavier
# files are converted so they play without stalling.
FUNNEL_COPY_KBPS = 5500
FUNNEL_TRANSCODE_KBPS = 4500


def load_saved(data_dir: Path) -> dict:
    """The saved choices on top of DEFAULTS; unknown keys and values of the wrong type are dropped."""
    saved = dict(DEFAULTS)
    try:
        raw = json.loads((data_dir / SETTINGS_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return saved
    if not isinstance(raw, dict):
        return saved
    for key, default in DEFAULTS.items():
        value = raw.get(key)
        if key in CHOICES:
            if value in CHOICES[key]:
                saved[key] = value
        elif isinstance(default, list):
            if isinstance(value, list) and all(isinstance(v, str) for v in value):
                saved[key] = value
        elif isinstance(default, int):
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                saved[key] = value
        elif isinstance(value, str):
            saved[key] = value
    return saved


def save_saved(data_dir: Path, values: dict) -> None:
    path = data_dir / SETTINGS_FILE
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def saved_env(saved: dict) -> dict[str, str]:
    """The saved choices as the variables they stand for. "auto" quality sets nothing: what it
    means depends on Funnel, which may come from .env (see get_settings)."""
    conn = saved["connection"]
    env = {
        "TAILSCALE_SERVE": "0" if conn == "http" else "1",
        "TAILSCALE_FUNNEL": "1" if conn == "funnel" else "0",
        "LIBRARY_DIRS": ";".join(saved["libraryDirs"]),
        "MEDIA_CONTROL": saved["mediaControl"],
        "PORT": str(int(saved["port"])),
        "TORRENT_UPLOAD_LIMIT": str(int(saved["torrentUploadLimit"])),
        "ICE_SERVERS": saved["iceServers"],
        "OPENSUBTITLES_API_KEY": saved["osApiKey"],
        "OPENSUBTITLES_USERNAME": saved["osUsername"],
        "OPENSUBTITLES_PASSWORD": saved["osPassword"],
    }
    if saved["quality"] == "original":
        env["MAX_COPY_KBPS"] = "0"
    elif saved["quality"] == "manual":
        kbps = int(float(saved["qualityMbps"]) * 1000)
        env["MAX_COPY_KBPS"] = str(kbps)
        env["TRANSCODE_KBPS"] = str(kbps * 4 // 5)
    return env


def locked_settings() -> list[str]:
    """Choices the settings page cannot change: their variables come from the environment or .env."""
    return [key for key, names in ENV_NAMES.items() if any(name in os.environ for name in names)]


@dataclass(frozen=True)
class Settings:
    host: str  # empty = decided by run.py: 127.0.0.1 behind Tailscale Serve, else 0.0.0.0
    port: int
    tailscale_serve: bool
    tailscale_funnel: bool  # the HTTPS link open to the whole internet, not only the tailnet
    data_dir: Path
    web_dir: Path
    access_key: str
    # torrent helper (Node)
    helper_host: str
    helper_port: int
    torrent_upload_limit: int  # KB/s, 0 = unlimited
    # media
    ffmpeg: str
    ffprobe: str
    video_encoder: str
    transcode_kbps: int
    max_copy_kbps: int  # 0 = always copy H.264
    max_height: int
    audio_kbps: int
    audio_filter: str
    hls_time: int
    # the host's film folders: the host and co-hosts open videos from them
    library_dirs: tuple[Path, ...]
    media_control: str  # "everyone" changes the film; "trusted" = only the host and co-hosts
    # add-ons
    addons_builtin: bool  # Cinemeta and Public Domain Movies; 0 = only the ones added by hand
    # voice and camera
    ice_servers: str  # comma-separated stun:/turn: URLs, empty = direct addresses only (FUNNEL_STUN with Funnel)
    # OpenSubtitles
    os_api_key: str
    os_username: str
    os_password: str
    os_user_agent: str

    @property
    def connection(self) -> str:
        """The settings page's name for how friends come in: funnel, serve or http."""
        if self.tailscale_funnel:
            return "funnel"
        return "serve" if self.tailscale_serve else "http"

    @property
    def helper_url(self) -> str:
        return f"http://{self.helper_host}:{self.helper_port}"

    @property
    def hls_dir(self) -> Path:
        return self.data_dir / "hls"

    @property
    def subs_dir(self) -> Path:
        return self.data_dir / "subs"

    @property
    def torrent_dir(self) -> Path:
        return self.data_dir / "torrents"


def _persistent_key(data_dir: Path) -> str:
    """Keep the access key across restarts so the shared link stays valid."""
    key_file = data_dir / "access_key.txt"
    if key_file.is_file():
        key = key_file.read_text(encoding="utf-8").strip()
        if key:
            return key
    key = secrets.token_urlsafe(18)
    key_file.write_text(key, encoding="utf-8")
    return key


def new_access_key(data_dir: Path) -> str:
    """A new room key, from the next start on: links with the old one stop working."""
    (data_dir / "access_key.txt").unlink(missing_ok=True)
    return _persistent_key(data_dir)


# Friends coming over Funnel are not in the tailnet, so voice and camera cannot use the Tailscale
# addresses; a STUN server tells each browser its public address to get through home routers.
# Cloudflare's is free, with no limit, and sees only addresses, never the sound or picture.
FUNNEL_STUN = "stun:stun.cloudflare.com:3478"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # COWATCH_DOTENV: another settings file, or empty for none (the tests use that, so this
    # computer's own .env does not change what they see).
    dotenv = os.environ.get("COWATCH_DOTENV", str(ROOT / ".env"))
    if dotenv:
        load_dotenv(Path(dotenv))
    data_dir = Path(_str(os.environ, "DATA_DIR") or ROOT / "data").expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    saved = load_saved(data_dir)
    v = {**saved_env(saved), **os.environ}
    funnel = _int(v, "TAILSCALE_FUNNEL", 0) != 0
    auto = funnel and saved["quality"] == "auto"
    return Settings(
        host=_str(v, "HOST"),
        port=_int(v, "PORT", 8000),
        tailscale_serve=_int(v, "TAILSCALE_SERVE", 1) != 0,
        tailscale_funnel=funnel,
        data_dir=data_dir,
        web_dir=ROOT / "web",
        access_key=_str(v, "ACCESS_KEY") or _persistent_key(data_dir),
        helper_host="127.0.0.1",
        helper_port=_int(v, "HELPER_PORT", 8890),
        torrent_upload_limit=_int(v, "TORRENT_UPLOAD_LIMIT", 64),
        ffmpeg=_str(v, "FFMPEG", "ffmpeg"),
        ffprobe=_str(v, "FFPROBE", "ffprobe"),
        video_encoder=_str(v, "VIDEO_ENCODER", "libx264"),
        transcode_kbps=_int(v, "TRANSCODE_KBPS", FUNNEL_TRANSCODE_KBPS if auto else 5000),
        max_copy_kbps=_int(v, "MAX_COPY_KBPS", FUNNEL_COPY_KBPS if auto else 0),
        max_height=_int(v, "MAX_HEIGHT", 1080),
        audio_kbps=_int(v, "AUDIO_KBPS", 192),
        audio_filter=_str(v, "AUDIO_FILTER", "dynaudnorm=f=500:g=15"),
        hls_time=_int(v, "HLS_TIME", 4),
        library_dirs=_paths(v, "LIBRARY_DIRS"),
        media_control="trusted" if _str(v, "MEDIA_CONTROL").lower() == "trusted" else "everyone",
        addons_builtin=_int(v, "ADDONS_BUILTIN", 1) != 0,
        ice_servers=_str(v, "ICE_SERVERS") or (FUNNEL_STUN if funnel else ""),
        os_api_key=_str(v, "OPENSUBTITLES_API_KEY"),
        os_username=_str(v, "OPENSUBTITLES_USERNAME"),
        os_password=_str(v, "OPENSUBTITLES_PASSWORD"),
        os_user_agent=_str(v, "OPENSUBTITLES_USER_AGENT", "CoWatch v0.1"),
    )
