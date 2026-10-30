"""Start Co-Watch: the torrent helper (Node), the web server (FastAPI) and the HTTPS link
(Tailscale Serve or Funnel) together. Saving the settings page restarts them.

    python run.py
"""

from __future__ import annotations

import importlib
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from server import tailscale  # noqa: E402
from server.config import get_settings  # noqa: E402

LOOPBACK = ("127.0.0.1", "localhost", "::1")


def find_tool(name: str) -> str | None:
    return shutil.which(name)


def lan_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("10.255.255.255", 1))
            return sock.getsockname()[0]
    except OSError:
        return None


def start_helper(cfg) -> subprocess.Popen | None:
    helper_dir = ROOT / "torrent-helper"
    node = find_tool("node")
    if not node:
        print("! Node.js bulunamadı: torrent özelliği kapalı (yerel dosyalar çalışır).")
        return None
    if not (helper_dir / "node_modules" / "webtorrent").is_dir():
        print("! torrent-helper bağımlılıkları kurulu değil: 'cd torrent-helper && npm install' çalıştır.")
        return None
    env = dict(os.environ)
    env.update({
        "HELPER_PORT": str(cfg.helper_port),
        "TORRENT_DIR": str(cfg.torrent_dir),
        "TORRENT_UPLOAD_LIMIT": str(cfg.torrent_upload_limit),
        "PARENT_PID": str(os.getpid()),
    })
    # Shares this console, so its log lines show up here and Ctrl+C stops it too.
    return subprocess.Popen([node, "index.mjs"], cwd=helper_dir, env=env)


def fresh_settings():
    """The settings as saved right now. The server's modules read them once, when imported,
    so they are imported again too."""
    for name in [n for n in sys.modules if n == "server" or n.startswith("server.")]:
        del sys.modules[name]
    return importlib.import_module("server.config").get_settings()


class Launcher:
    """Runs the server and what it needs. The settings page calls restart(): the server stops,
    the settings are read again and the server starts with them. The torrent helper and the
    HTTPS link keep running when their own settings stayed the same."""

    def __init__(self) -> None:
        self.server = None  # uvicorn.Server
        self.restarting = False
        self.helper: subprocess.Popen | None = None
        self.helper_key = None
        self.share: tailscale.Share | None = None
        self.share_key = None
        self.share_note = "off"  # why there is no Share: off (plain http), missing, stopped
        self.friend_link: str | None = None

    def restart(self) -> None:
        self.restarting = True
        if self.server is not None:
            self.server.should_exit = True

    def share_state(self) -> dict:
        return self.share.public() if self.share is not None else {"state": self.share_note}

    def start_helper(self, cfg) -> None:
        key = (cfg.helper_port, cfg.torrent_upload_limit, str(cfg.torrent_dir))
        if self.helper is not None and self.helper.poll() is None and key == self.helper_key:
            return
        tailscale.stop(self.helper)
        self.helper, self.helper_key = start_helper(cfg), key

    def start_share(self, cfg) -> None:
        """HTTPS for friends through Tailscale: browsers open the camera and microphone only on
        secure pages. Serve opens the link to the tailnet; Funnel to the whole internet, so a
        friend needs only a browser. A failed one is kept for its message and tried again on
        the next restart (the page's "Try again")."""
        key = (cfg.connection, cfg.port)
        if self.share is not None and self.share.running and key == self.share_key:
            return
        if self.share is not None:
            self.share.stop()
        self.share, self.share_key = None, key
        if cfg.connection == "http":
            self.share_note = "off"
            return
        exe = tailscale.exe()
        if not exe:
            self.share_note = "missing"
            print("! Tailscale kurulu değil: HTTPS linki yok.")
            return
        name = tailscale.dns_name(exe)
        if not name:
            self.share_note = "stopped"
            print("! Tailscale çalışmıyor ya da oturum açılmamış: HTTPS linki yok.")
            return
        self.share = tailscale.Share(exe, cfg.connection, cfg.port, name)
        if not self.share.start():
            print(f"! 'tailscale {cfg.connection}' başlatılamadı (mesajı yukarıda): HTTPS linki yok.")

    def links(self, cfg, host: str) -> None:
        key = cfg.access_key
        self.friend_link = None
        print("\nCo-Watch hazır.")
        print(f"  Bu bilgisayardan:  http://localhost:{cfg.port}/?k={key}")
        if self.share is not None and self.share.running:
            self.friend_link = f"{self.share.link}/?k={key}"
            print(f"  Arkadaşlar için:   {self.friend_link}   <- arkadaşına bunu gönder")
            if cfg.tailscale_funnel:
                print("  (Funnel: link internete açık, arkadaşın Tailscale kurmadan girer. Odayı sadece linkteki")
                print("   anahtar korur; linki yalnızca izleyeceğin kişilere gönder.)")
            else:
                print("  (Serve: arkadaşının cihazında Tailscale olmalı. Kurmadan girsin istersen Ayarlar'dan Funnel'ı seç.)")
        elif host not in LOOPBACK:
            ts = tailscale.ip(tailscale.exe())
            lan = lan_ip()
            if ts:
                self.friend_link = f"http://{ts}:{cfg.port}/?k={key}"
                print(f"  Tailscale linki:   {self.friend_link}   <- arkadaşına bunu gönder")
            else:
                print("  Tailscale IP'si bulunamadı; 'tailscale ip -4' ile öğrenip linkte localhost yerine yaz.")
            if lan:
                self.friend_link = self.friend_link or f"http://{lan}:{cfg.port}/?k={key}"
                print(f"  Aynı ev ağı:       http://{lan}:{cfg.port}/?k={key}")
            print("  (http linklerinde arkadaşın kamerası ve mikrofonu açılmaz; bunun için Tailscale Serve gerekir.)")
        print("  Ayarlar ve paylaşım linki: sayfadaki \"Paylaş\" kartında.")
        print()

    def run(self) -> None:
        import uvicorn

        try:
            while True:
                self.restarting = False
                cfg = fresh_settings()
                self.start_helper(cfg)
                self.start_share(cfg)
                # Behind Serve, friends must come through HTTPS: a plain http link would work
                # for the film but never for their camera and microphone.
                serving = self.share is not None and self.share.running
                host = cfg.host or ("127.0.0.1" if serving else "0.0.0.0")
                self.links(cfg, host)
                main = importlib.import_module("server.main")
                main.launcher = self
                self.server = uvicorn.Server(uvicorn.Config(
                    main.app, host=host, port=cfg.port, log_level="info",
                    ws_ping_interval=20, ws_ping_timeout=20, timeout_graceful_shutdown=3,
                ))
                self.server.run()
                if not self.restarting:
                    break
                print("\nAyarlar değişti: yeniden başlatılıyor…")
        finally:
            if self.share is not None:
                self.share.stop()
            tailscale.stop(self.helper)


def main() -> None:
    cfg = get_settings()
    missing = [tool for tool in (cfg.ffmpeg, cfg.ffprobe) if not find_tool(tool)]
    if missing:
        print(f"! Bulunamadı: {', '.join(missing)}. ffmpeg kurup PATH'e ekle (ya da .env'de FFMPEG/FFPROBE ver).")
        sys.exit(1)
    try:
        Launcher().run()
    except KeyboardInterrupt:  # Ctrl+C: uvicorn stops first, then hands the signal on
        pass


if __name__ == "__main__":
    main()
