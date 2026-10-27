"""Shared pointers and drawings: checks for the small messages viewers exchange about the
picture (cursor positions, pokes, pen strokes). Coordinates are fractions of the video
picture, not of the window, so they land on the same spot of the film on every screen."""

from __future__ import annotations

import math
import re
from typing import Optional

# Bright enough for dark text on top, distinct enough to tell people apart.
PALETTE = ("#ff6b6b", "#4dabf7", "#51cf66", "#fcc419", "#cc5de8", "#ff922b", "#22b8cf", "#f06595")
POKE_INTERVAL_S = 0.15
MAX_POINTS = 256  # per message; clients send a stroke in small batches

_COLOR = re.compile(r"^#[0-9a-f]{6}$")
_STROKE_ID = re.compile(r"^[a-z0-9]{1,12}$")


def coord(value) -> Optional[float]:
    """A coordinate as a fraction of the picture. Slightly outside is fine (letterbox
    bars), far outside or not a number is not."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return round(min(1.5, max(-0.5, number)), 4)


def point(x, y) -> Optional[tuple[float, float]]:
    px, py = coord(x), coord(y)
    if px is None or py is None:
        return None
    return px, py


def pick_color(requested, taken: set[str]) -> str:
    """The requested colour if it is free, else the first free one."""
    color = str(requested or "").lower()
    if color in PALETTE and color not in taken:
        return color
    for candidate in PALETTE:
        if candidate not in taken:
            return candidate
    return PALETTE[len(taken) % len(PALETTE)]


def stroke_message(msg: dict, sender_id: str, fallback_color: str) -> Optional[dict]:
    """A pen stroke batch to pass on, or None if there is nothing valid in it."""
    stroke = str(msg.get("id", ""))
    if not _STROKE_ID.match(stroke):
        return None
    points: list[list[float]] = []
    raw = msg.get("points")
    if isinstance(raw, list):
        for item in raw[:MAX_POINTS]:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                valid = point(item[0], item[1])
                if valid is not None:
                    points.append(list(valid))
    out: dict = {"type": "draw", "from": sender_id, "stroke": stroke, "points": points}
    if msg.get("start"):
        color = str(msg.get("color", "")).lower()
        out["start"] = True
        out["color"] = color if _COLOR.match(color) else fallback_color
    if msg.get("end"):
        out["end"] = True
    if not points and not out.get("start") and not out.get("end"):
        return None
    return out
