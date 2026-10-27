"""Start Co-Watch: the torrent helper (Node) and the web server (FastAPI) together.

    python run.py
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from server.config import get_settings  # noqa: E402


def find_tool(name: str) -> str | None:
    return shutil.which(name)


def tailscale_ip() -> str | None:
    exe = find_tool("tailscale")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "ip", "-4"], capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return out.splitlines()[0] if out else None


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


def main() -> None:
    cfg = get_settings()
    missing = [tool for tool in (cfg.ffmpeg, cfg.ffprobe) if not find_tool(tool)]
    if missing:
        print(f"! Bulunamadı: {', '.join(missing)}. ffmpeg kurup PATH'e ekle (ya da .env'de FFMPEG/FFPROBE ver).")
        sys.exit(1)

    helper = start_helper(cfg)
    key = cfg.access_key
    print("\nCo-Watch hazır.")
    print(f"  Bu bilgisayardan:  http://localhost:{cfg.port}/?k={key}")
    ts = tailscale_ip()
    if ts:
        print(f"  Tailscale linki:   http://{ts}:{cfg.port}/?k={key}   <- arkadaşına bunu gönder")
    else:
        print("  Tailscale IP'si bulunamadı; 'tailscale ip -4' ile öğrenip linkte localhost yerine yaz.")
    lan = lan_ip()
    if lan:
        print(f"  Aynı ev ağı:       http://{lan}:{cfg.port}/?k={key}")
    print()

    import uvicorn

    try:
        uvicorn.run("server.main:app", host=cfg.host, port=cfg.port, log_level="info",
                    ws_ping_interval=20, ws_ping_timeout=20)
    finally:
        if helper is not None and helper.poll() is None:
            helper.terminate()
            try:
                helper.wait(timeout=5)
            except subprocess.TimeoutExpired:
                helper.kill()


if __name__ == "__main__":
    main()
