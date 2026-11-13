"""Shared pointers and drawings: checks for the small messages viewers exchange about the
picture (cursor positions, pokes, pen strokes), and for the text chat. Coordinates are
fractions of the video picture, not of the window, so they land on the same spot of the film on every screen."""

from __future__ import annotations

import math
import re
from collections import deque
from typing import Optional

# Bright enough for dark text on top, distinct enough to tell people apart.
PALETTE = ("#ff6b6b", "#4dabf7", "#51cf66", "#fcc419", "#cc5de8", "#ff922b", "#22b8cf", "#f06595")
# The face on a viewer's ball and camera tile: ears and a snout over the plain ball (web/style.css).
ANIMALS = ("ball", "cat", "bear", "bunny", "fox", "panda", "mouse", "dog")
POKE_INTERVAL_S = 0.15
MAX_POINTS = 256  # per message; clients send a stroke in small batches
MAX_ERASE = 64  # whole strokes one eraser message may remove

_COLOR = re.compile(r"^#[0-9a-f]{6}$")
_STROKE_ID = re.compile(r"^[a-z0-9]{1,12}$")
_CLIENT_ID = re.compile(r"^[0-9a-f]{8}$")


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
        if msg.get("erase"):
            out["erase"] = True  # rubs out what was drawn before it, where it passes
    if msg.get("end"):
        out["end"] = True
    if not points and not out.get("start") and not out.get("end"):
        return None
    return out


def erase_message(msg: dict, sender_id: str) -> Optional[dict]:
    """The whole-line eraser: strokes, named by their drawer and id, that the sender took away."""
    out: list[list[str]] = []
    raw = msg.get("strokes")
    if isinstance(raw, list):
        for item in raw[:MAX_ERASE]:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                owner, stroke = str(item[0]), str(item[1])
                if _CLIENT_ID.match(owner) and _STROKE_ID.match(stroke) and [owner, stroke] not in out:
                    out.append([owner, stroke])
    if not out:
        return None
    return {"type": "draw_erase", "from": sender_id, "strokes": out}


# ---- text chat ---------------------------------------------------------------------
CHAT_MAX_CHARS = 500
CHAT_HISTORY = 100  # kept in memory for those who join later; gone when the server restarts
CHAT_BURST = 5  # messages in a row before the limit applies
CHAT_REFILL_S = 1.0  # then one message per this many seconds

# A viewer's player tells the server what went wrong in their browser (`report`): written to
# data/playback.log, so a black screen on a friend's side can be read afterwards.
REPORT_KINDS = {"hls_error", "video_error", "frames_stalled", "reloaded", "repaired", "codec_failed"}
REPORT_MAX_CHARS = 300
REPORT_BURST = 5
REPORT_REFILL_S = 10.0

HEVC_PROFILES = ("main", "main10", "uhd")


def no_hevc() -> dict[str, bool]:
    """Conservative HEVC support map used before a viewer joins or after a decode failure."""
    return {k: False for k in HEVC_PROFILES}


def hevc_caps(value) -> dict[str, bool]:
    """Normalise a viewer's HEVC profile claims from `hello`: unknown keys dropped, non-bools are False."""
    if not isinstance(value, dict):
        return no_hevc()
    return {k: value.get(k) is True for k in HEVC_PROFILES}

_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029\u202a-\u202e\u2066-\u2069]+")  # line breaks, direction overrides


def chat_text(value) -> Optional[str]:
    """A chat message as one line of plain text, or None if nothing is left of it."""
    if not isinstance(value, str):
        return None
    text = _CONTROL.sub(" ", value).strip()[:CHAT_MAX_CHARS].strip()
    return text or None


class Bucket:
    """Lets `burst` messages through at once, then one every `refill_s` seconds."""

    def __init__(self, burst: int = CHAT_BURST, refill_s: float = CHAT_REFILL_S) -> None:
        self.burst, self.refill_s = burst, refill_s
        self.tokens = float(burst)
        self.at: Optional[float] = None

    def take(self, now: float) -> bool:
        if self.at is not None:
            self.tokens = min(self.burst, self.tokens + (now - self.at) / self.refill_s)
        self.at = now
        if self.tokens < 1:
            return False
        self.tokens -= 1
        return True


def playback_report(msg: dict) -> Optional[dict]:
    """A player report from a browser, checked: a known kind, short one-line texts, a film time."""
    kind = msg.get("kind")
    if kind not in REPORT_KINDS:
        return None
    out: dict = {"kind": kind}
    for field, limit in (("detail", REPORT_MAX_CHARS), ("ua", 200)):
        text = chat_text(msg.get(field))
        if text:
            out[field] = text[:limit]
    position = msg.get("position")
    if isinstance(position, (int, float)) and not isinstance(position, bool) and math.isfinite(position) and position >= 0:
        out["position"] = round(float(position), 1)
    return out


def number(value, low: float, high: float) -> Optional[float]:
    """A plain finite number from a browser within [low, high], or None (booleans are not numbers)."""
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        return None
    return float(value) if low <= value <= high else None


# ---- black picture ---------------------------------------------------------------
# Every few seconds each playing page tells how bright its picture is (`luma`, 0-255, from a
# tiny copy of the video) and at which film time. A dark scene is dark for everyone; a picture
# that is black on one page while another is bright at the same film moment is that page's
# trouble: it is written to data/playback.log with what the page knew, and the page is told to
# repair itself (`repair`). Two dark samples in a row, both matched, so that a fade-out next to a
# scene cut does not count.
LUMA_DARK = 10  # below: black
LUMA_BRIGHT = 30  # above: someone else clearly sees a picture
LUMA_MATCH_S = 1.5  # film times this close count as the same moment (pages sample 3 s apart)
LUMA_KEEP_S = 10.0  # samples older than this (server clock) are forgotten
LUMA_DARK_SAMPLES = 2
LUMA_BURST = 4
LUMA_REFILL_S = 2.0
REPAIR_INTERVAL_S = 30.0  # at most one repair per viewer in this time
_STREAM_ID = re.compile(r"^[a-f0-9]{12}$")
_LUMA_INTS = (("ready", 4), ("frames", 1e9), ("dropped", 1e9), ("stateMs", 1e9), ("reconnects", 1e6))


def luma_sample(msg: dict) -> Optional[dict]:
    """A brightness sample, checked: film time and brightness, and whatever of the player's
    numbers are valid (each one dropped on its own if not)."""
    t, luma = number(msg.get("t"), 0, 1e6), number(msg.get("luma"), 0, 255)
    if t is None or luma is None:
        return None
    out: dict = {"t": round(t, 2), "luma": round(luma, 1)}
    for field, high in _LUMA_INTS:
        value = number(msg.get(field), 0, high)
        if value is not None:
            out[field] = int(value)
    ahead = number(msg.get("ahead"), 0, 3600)
    if ahead is not None:
        out["ahead"] = round(ahead, 1)
    for field in ("paused", "streamOk"):
        if isinstance(msg.get(field), bool):
            out[field] = msg[field]
    stream = msg.get("stream")
    if isinstance(stream, str) and _STREAM_ID.match(stream):
        out["stream"] = stream
    return out


class LumaTrack:
    """One viewer's latest samples (server time, film time, brightness) and player numbers."""

    def __init__(self) -> None:
        self.samples: deque[tuple[float, float, float]] = deque(maxlen=4)
        self.bucket = Bucket(LUMA_BURST, LUMA_REFILL_S)
        self.last_repair = -math.inf
        self.diag: dict = {}


def black_viewers(samples: dict[str, list[tuple[float, float, float]]], now: float) -> list[str]:
    """Who sees a black picture while someone else sees the same film moment bright."""
    fresh = {cid: [s for s in items if now - s[0] <= LUMA_KEEP_S] for cid, items in samples.items()}
    out = []
    for cid, items in fresh.items():
        last = items[-LUMA_DARK_SAMPLES:]
        if len(last) < LUMA_DARK_SAMPLES or any(s[2] >= LUMA_DARK for s in last):
            continue
        bright = [s[1] for other, theirs in fresh.items() if other != cid for s in theirs if s[2] > LUMA_BRIGHT]
        if all(any(abs(t - s[1]) <= LUMA_MATCH_S for t in bright) for s in last):
            out.append(cid)
    return out


def describe_luma(diag: dict, server_stream: Optional[str]) -> str:
    """The player's numbers in one short line for the playback log."""
    parts = [f"luma {diag.get('luma', '?')}"]
    if "ready" in diag:
        parts.append(f"readyState {diag['ready']}")
    if "ahead" in diag:
        parts.append(f"ahead {diag['ahead']} s")
    if "paused" in diag:
        parts.append("paused" if diag["paused"] else "playing")
    if "frames" in diag:
        parts.append(f"frames {diag['frames']} (dropped {diag.get('dropped', '?')})")
    stream = diag.get("stream")
    if stream is None:
        parts.append("no stream")
    else:
        parts.append("stream current" if stream == server_stream else f"stream old {stream}")
    if diag.get("streamOk") is False:
        parts.append("player behind its media")
    if "stateMs" in diag:
        parts.append(f"last state {diag['stateMs'] / 1000:.1f} s ago")
    if "reconnects" in diag:
        parts.append(f"reconnects {diag['reconnects']}")
    return ", ".join(parts)


# ---- connection panel --------------------------------------------------------------
# Each player measures how fast its film segments arrive (hls.js fragment statistics) and
# says so every ten seconds (`netstat`): next to the film's bitrate, it tells who is on a link
# that cannot keep up. The host also hears when someone keeps stalling (main.Controller.note_stall).
NETSTAT_BURST = 3
NETSTAT_REFILL_S = 5.0
NETSTAT_MAX_MBPS = 1000.0  # a page on this computer measures a lot; more says nothing more
NETSTAT_MAX_AHEAD_S = 600.0


def _number(value, top: float) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        return None
    return min(float(value), top)


def netstat_values(msg: dict) -> Optional[dict]:
    """A player's measured download speed (Mbps) and the film it has in hand (s), checked.
    None when the speed is missing: the buffer alone says nothing about the link."""
    mbps = _number(msg.get("mbps"), NETSTAT_MAX_MBPS)
    if mbps is None:
        return None
    ahead = _number(msg.get("bufferedAhead"), NETSTAT_MAX_AHEAD_S)
    return {"mbps": round(mbps, 2), "ahead": round(ahead, 1) if ahead is not None else None}
