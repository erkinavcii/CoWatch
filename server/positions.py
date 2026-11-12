"""Where each film was left (data/positions.json), to start there next time it is opened.

Keyed by the film's `media_key` (the same key its subtitles use). A film watched to its last
two minutes is forgotten. At most `KEEP` films; the one not watched for longest goes first.
Written at most every `SAVE_EVERY_S` while a film plays, and at once when it is closed or
another film is opened (`flush`)."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger("cowatch")

RESUME_MIN_S = 60  # less than this into the film: it simply starts again
END_MARGIN_S = 120  # this close to the end: watched, forgotten
KEEP = 200
SAVE_EVERY_S = 15


class PositionStore:
    def __init__(self, path: Path):
        self.path = path
        self.items: dict[str, dict] = {}
        self.dirty = False
        self.saved_at = -float("inf")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self.items = {str(k): v for k, v in data.items()
                              if isinstance(v, dict) and isinstance(v.get("pos"), (int, float))}
        except (OSError, ValueError):
            pass

    def resume_at(self, key: str, duration: float) -> Optional[float]:
        """The position to start this film at, or None (never opened, near the start, or finished)."""
        item = self.items.get(key)
        if not item or duration <= 0:
            return None
        pos = float(item["pos"])
        if RESUME_MIN_S < pos < duration - END_MARGIN_S:
            return pos
        return None

    def note(self, key: str, position: float, duration: float, title: str = "",
             now: Optional[float] = None) -> None:
        if not key or duration <= 0:
            return
        if position >= duration - END_MARGIN_S:
            self.forget(key)
            return
        if key not in self.items and position < RESUME_MIN_S:
            return  # just opened: nothing worth remembering yet
        item = self.items.get(key)
        position = round(max(0.0, position), 1)
        if item and item["pos"] == position:
            return
        self.items[key] = {"pos": position, "duration": round(duration, 1), "title": str(title)[:120],
                           "at": round(now if now is not None else time.time())}
        if len(self.items) > KEEP:
            oldest = sorted(self.items, key=lambda k: self.items[k].get("at", 0))
            for gone in oldest[:len(self.items) - KEEP]:
                del self.items[gone]
        self.dirty = True

    def forget(self, key: str) -> None:
        if self.items.pop(key, None) is not None:
            self.dirty = True

    def maybe_save(self, now: Optional[float] = None) -> None:
        now = time.monotonic() if now is None else now
        if self.dirty and now - self.saved_at >= SAVE_EVERY_S:
            self.flush(now)

    def flush(self, now: Optional[float] = None) -> None:
        if not self.dirty:
            return
        self.saved_at = time.monotonic() if now is None else now
        self.dirty = False
        tmp = self.path.with_suffix(".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(self.items, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError as exc:
            log.warning("film positions could not be saved: %s", exc)
