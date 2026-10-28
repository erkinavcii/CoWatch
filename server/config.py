"""Settings, read from environment variables and an optional .env file in the project root."""

from __future__ import annotations

import os
import re
import secrets
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

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


def _int(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    try:
        return int(float(value)) if value else default
    except ValueError:
        return default


def _str(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    return value.strip() if value is not None else default


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
    # voice and camera
    ice_servers: str  # comma-separated stun:/turn: URLs, empty = direct addresses only (FUNNEL_STUN with Funnel)
    # OpenSubtitles
    os_api_key: str
    os_username: str
    os_password: str
    os_user_agent: str

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


# Friends coming over Funnel are not in the tailnet, so voice and camera cannot use the Tailscale
# addresses; a STUN server tells each browser its public address to get through home routers.
# Cloudflare's is free, with no limit, and sees only addresses, never the sound or picture.
FUNNEL_STUN = "stun:stun.cloudflare.com:3478"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv(ROOT / ".env")
    data_dir = Path(_str("DATA_DIR") or ROOT / "data").expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    funnel = _int("TAILSCALE_FUNNEL", 0) != 0
    return Settings(
        host=_str("HOST"),
        port=_int("PORT", 8000),
        tailscale_serve=_int("TAILSCALE_SERVE", 1) != 0,
        tailscale_funnel=funnel,
        data_dir=data_dir,
        web_dir=ROOT / "web",
        access_key=_str("ACCESS_KEY") or _persistent_key(data_dir),
        helper_host="127.0.0.1",
        helper_port=_int("HELPER_PORT", 8890),
        torrent_upload_limit=_int("TORRENT_UPLOAD_LIMIT", 64),
        ffmpeg=_str("FFMPEG", "ffmpeg"),
        ffprobe=_str("FFPROBE", "ffprobe"),
        video_encoder=_str("VIDEO_ENCODER", "libx264"),
        transcode_kbps=_int("TRANSCODE_KBPS", 5000),
        max_copy_kbps=_int("MAX_COPY_KBPS", 0),
        max_height=_int("MAX_HEIGHT", 1080),
        audio_kbps=_int("AUDIO_KBPS", 192),
        audio_filter=_str("AUDIO_FILTER", "dynaudnorm=f=500:g=15"),
        hls_time=_int("HLS_TIME", 4),
        ice_servers=_str("ICE_SERVERS") or (FUNNEL_STUN if funnel else ""),
        os_api_key=_str("OPENSUBTITLES_API_KEY"),
        os_username=_str("OPENSUBTITLES_USERNAME"),
        os_password=_str("OPENSUBTITLES_PASSWORD"),
        os_user_agent=_str("OPENSUBTITLES_USER_AGENT", "CoWatch v0.1"),
    )
