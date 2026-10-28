"""Start Co-Watch: the torrent helper (Node) and the web server (FastAPI) together.

    python run.py
"""

from __future__ import annotations

import json
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


def tailscale_exe() -> str | None:
    """On PATH, or where the Windows installer puts it: a console opened before Tailscale was
    installed does not see the new PATH yet."""
    exe = find_tool("tailscale")
    if exe or os.name != "nt":
        return exe
    default = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tailscale" / "tailscale.exe"
    return str(default) if default.is_file() else None


def tailscale_ip() -> str | None:
    exe = tailscale_exe()
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "ip", "-4"], capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return out.splitlines()[0] if out else None


def tailscale_dns_name(exe: str) -> str | None:
    """This computer's name in the tailnet (pc.tail1234.ts.net), if Tailscale is up."""
    try:
        out = subprocess.run([exe, "status", "--json"], capture_output=True, text=True,
                             encoding="utf-8", timeout=10).stdout
        data = json.loads(out)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if data.get("BackendState") != "Running":
        return None
    return ((data.get("Self") or {}).get("DNSName") or "").rstrip(".") or None


def start_serve(cfg) -> tuple[subprocess.Popen, str] | None:
    """HTTPS for friends through Tailscale: browsers open the camera and microphone only on
    secure pages. Serve opens the link to the tailnet; Funnel (TAILSCALE_FUNNEL=1) to the whole
    internet, so a friend needs only a browser. Either runs in the foreground and stops with
    us; `--bg` would keep forwarding to a closed port after we exit, even across reboots."""
    exe = tailscale_exe()
    if not exe:
        return None
    name = tailscale_dns_name(exe)
    if not name:
        print("! Tailscale çalışmıyor ya da oturum açılmamış: HTTPS linki yok.")
        return None
    mode = "funnel" if cfg.tailscale_funnel else "serve"
    # Shares this console: if HTTPS or Funnel is not enabled on the tailnet yet, it prints the consent link here.
    proc = subprocess.Popen([exe, mode, f"http://127.0.0.1:{cfg.port}"])
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        return proc, name
    print(f"! 'tailscale {mode}' başlatılamadı (mesajı yukarıda): HTTPS linki yok.")
    return None


def stop(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


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
    serve = start_serve(cfg) if cfg.tailscale_serve or cfg.tailscale_funnel else None
    # Behind Serve, friends must come through HTTPS: a plain http link would work for the film
    # but never for their camera and microphone.
    host = cfg.host or ("127.0.0.1" if serve else "0.0.0.0")
    key = cfg.access_key
    print("\nCo-Watch hazır.")
    print(f"  Bu bilgisayardan:  http://localhost:{cfg.port}/?k={key}")
    if serve and cfg.tailscale_funnel:
        print(f"  Arkadaşlar için:   https://{serve[1]}/?k={key}   <- arkadaşına bunu gönder")
        print("  (Funnel: link internete açık, arkadaşın Tailscale kurmadan girer. Odayı sadece linkteki")
        print("   anahtar korur; linki yalnızca izleyeceğin kişilere gönder.)")
    elif serve:
        print(f"  Arkadaşlar için:   https://{serve[1]}/?k={key}   <- arkadaşına bunu gönder")
        print("  (Serve: arkadaşının cihazında Tailscale olmalı. Kurmadan girsin istersen .env'de TAILSCALE_FUNNEL=1.)")
    elif host not in ("127.0.0.1", "localhost", "::1"):
        ts = tailscale_ip()
        if ts:
            print(f"  Tailscale linki:   http://{ts}:{cfg.port}/?k={key}   <- arkadaşına bunu gönder")
        else:
            print("  Tailscale IP'si bulunamadı; 'tailscale ip -4' ile öğrenip linkte localhost yerine yaz.")
        lan = lan_ip()
        if lan:
            print(f"  Aynı ev ağı:       http://{lan}:{cfg.port}/?k={key}")
        print("  (http linklerinde arkadaşın kamerası ve mikrofonu açılmaz; bunun için Tailscale Serve gerekir.)")
    print()

    import uvicorn

    try:
        uvicorn.run("server.main:app", host=host, port=cfg.port, log_level="info",
                    ws_ping_interval=20, ws_ping_timeout=20)
    finally:
        stop(serve[0] if serve else None)
        stop(helper)


if __name__ == "__main__":
    main()
