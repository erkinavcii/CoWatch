"""Co-Watch in the tray: the Windows build's CoWatch.exe (see tools/build_windows.ps1).

A double click puts an icon in the tray (next to the clock) and opens the room in the browser.
The server runs as with run.py, in a thread of this process; its menu: open the room, copy
the friends' link, settings, quit. Quitting stops the server, the HTTPS link and the torrent
helper too. Works from the source as well:

    python tray.py
"""

from __future__ import annotations

import ctypes
import os
import socket
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

FROZEN = bool(getattr(sys, "frozen", False))
LOG_LIMIT = 5 * 1024 * 1024

TEXTS = {
    "tr": {"open": "Odayı aç", "copy": "Arkadaş linkini kopyala", "settings": "Ayarlar", "quit": "Çıkış",
           "copied": "Link kopyalandı; arkadaşına gönder.", "no_link": "Arkadaş linki henüz yok; Paylaş kartına bak.",
           "failed": "Co-Watch durdu. Ayrıntı: {log}"},
    "en": {"open": "Open the room", "copy": "Copy the friends' link", "settings": "Settings", "quit": "Quit",
           "copied": "Link copied; send it to your friend.", "no_link": "No friends' link yet; see the Share card.",
           "failed": "Co-Watch stopped. Details: {log}"},
    "ru": {"open": "Открыть комнату", "copy": "Скопировать ссылку для друзей", "settings": "Настройки",
           "quit": "Выход", "copied": "Ссылка скопирована; отправьте её другу.",
           "no_link": "Ссылки для друзей пока нет; см. карточку «Поделиться».",
           "failed": "Co-Watch остановился. Подробности: {log}"},
}


def ui_lang() -> str:
    """Windows' display language, among the app's three."""
    try:
        primary = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
    except (AttributeError, OSError):
        return "en"
    return {0x1F: "tr", 0x19: "ru"}.get(primary, "en")


def prepare() -> Path:
    """The installed app brings its own ffmpeg and Node (tools\\ next to CoWatch.exe) and has no
    console: what the server prints goes to a log file in the data folder."""
    from server.config import default_data_dir

    if FROZEN:
        tools = Path(sys.executable).parent / "tools"
        os.environ["PATH"] = str(tools) + os.pathsep + os.environ.get("PATH", "")
    data_dir = Path(os.environ.get("DATA_DIR") or default_data_dir())
    data_dir.mkdir(parents=True, exist_ok=True)
    log = data_dir / "cowatch.log"
    if sys.stdout is None or not sys.stdout.isatty():
        if log.is_file() and log.stat().st_size > LOG_LIMIT:
            log.replace(log.with_suffix(".old.log"))
        stream = open(log, "a", encoding="utf-8", buffering=1)  # noqa: SIM115 (lives as long as the app)
        sys.stdout = sys.stderr = stream
    return log


def already_running() -> bool:
    """One Co-Watch per user: a second start only opens the room of the first."""
    if os.name != "nt":
        return False
    ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\CoWatchTray")
    return ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


def room_link() -> str:
    from server.config import get_settings

    cfg = get_settings()
    return f"http://localhost:{cfg.port}/?k={cfg.access_key}"


def wait_for_port(port: int, timeout: float = 60) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def copy_text(text: str) -> None:
    subprocess.run(["clip"], input=text.encode("utf-16-le"), check=False,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def draw_icon(size: int = 64):
    """The app's mark: a play sign on the dark panel and a pointer ball with eyes."""
    from PIL import Image, ImageDraw

    scale = 4  # drawn large, then shrunk: smooth edges
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=s // 5, fill="#16181d")
    d.polygon([(s * 0.26, s * 0.2), (s * 0.26, s * 0.74), (s * 0.68, s * 0.47)], fill="#f2b544")
    r = s * 0.17
    cx, cy = s * 0.72, s * 0.72
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill="#ff6b6b", outline="#16181d", width=max(1, s // 40))
    for ex in (cx - r * 0.38, cx + r * 0.38):
        d.ellipse((ex - r * 0.24, cy - r * 0.34, ex + r * 0.24, cy + r * 0.2), fill="white")
        d.ellipse((ex - r * 0.11, cy - r * 0.12, ex + r * 0.11, cy + r * 0.1), fill="#15161a")
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    log = prepare()
    if already_running():
        webbrowser.open(room_link())
        return

    import pystray

    import run

    text = TEXTS[ui_lang()]
    launcher = run.Launcher()
    state = {"opened": False, "failed": False}

    def serve() -> None:
        try:
            launcher.run()
        except Exception:  # keep the tray, so the user can read why and quit
            traceback.print_exc()
            state["failed"] = True
            icon.notify(text["failed"].format(log=log), "Co-Watch")

    def open_when_up() -> None:
        while launcher.local_link is None and not state["failed"]:
            time.sleep(0.2)
        from server.config import get_settings

        if not state["failed"] and wait_for_port(get_settings().port):
            webbrowser.open(launcher.local_link)

    def open_room(_icon=None, _item=None) -> None:
        if launcher.local_link:
            webbrowser.open(launcher.local_link)

    def open_settings(_icon=None, _item=None) -> None:
        if launcher.local_link:
            webbrowser.open(launcher.local_link + "#settings")

    def copy_link(_icon=None, _item=None) -> None:
        if launcher.friend_link:
            copy_text(launcher.friend_link)
            icon.notify(text["copied"], "Co-Watch")
        else:
            icon.notify(text["no_link"], "Co-Watch")

    def quit_app(_icon=None, _item=None) -> None:
        launcher.stop()
        worker.join(timeout=15)
        icon.stop()

    icon = pystray.Icon("CoWatch", draw_icon(64), "Co-Watch", menu=pystray.Menu(
        pystray.MenuItem(text["open"], open_room, default=True),  # also a click on the icon
        pystray.MenuItem(text["copy"], copy_link),
        pystray.MenuItem(text["settings"], open_settings),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(text["quit"], quit_app),
    ))
    worker = threading.Thread(target=serve, name="server", daemon=True)
    worker.start()
    threading.Thread(target=open_when_up, daemon=True).start()
    icon.run()


if __name__ == "__main__":
    main()
