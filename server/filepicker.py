"""The host's own file dialog. The server runs on the host's computer, so "Browse…" in the
host's browser can open the system's file dialog right there. A browser's own file picker
does not help: it never reveals the full path of the picked file, and ffmpeg needs it."""

from __future__ import annotations

import os
import threading
from typing import Optional

from .library import VIDEO_EXTS

VIDEO_TYPES = [
    ("Video", " ".join(f"*{ext}" for ext in sorted(VIDEO_EXTS))),
    ("*", "*.*"),
]
_lock = threading.Lock()
_last_dir: Optional[str] = None


class PickerError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def pick_video(title: str) -> Optional[str]:
    """Shows the dialog and blocks until it closes, so run it in a thread. The path picked,
    or None if the dialog was cancelled."""
    global _last_dir
    if not _lock.acquire(blocking=False):
        raise PickerError("picker_busy")  # one is already open, maybe behind a window
    try:
        try:
            import tkinter
            from tkinter import filedialog
        except ImportError:
            raise PickerError("picker_unavailable") from None
        try:
            root = tkinter.Tk()
        except tkinter.TclError:  # no desktop to show it on
            raise PickerError("picker_unavailable") from None
        try:
            root.withdraw()
            root.attributes("-topmost", True)  # in front of the browser
            path = filedialog.askopenfilename(parent=root, title=title[:100], filetypes=VIDEO_TYPES,
                                              initialdir=_last_dir or os.path.expanduser("~"))
        finally:
            root.destroy()
        if not path:
            return None
        path = os.path.normpath(path)  # C:/Films/a.mkv -> C:\Films\a.mkv, as the host would type it
        _last_dir = os.path.dirname(path)
        return path
    finally:
        _lock.release()
