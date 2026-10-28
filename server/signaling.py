"""Signalling for voice and camera: the small messages two viewers' browsers exchange to
connect to each other directly (WebRTC). The sound and picture never pass through the server;
it does not read the session descriptions either, it only checks their shape and size and
passes each one to the single viewer it is meant for."""

from __future__ import annotations

import json
import re
from typing import Optional

MAX_RTC_BYTES = 64 * 1024  # an offer with sound and video is a few KB
_DESCRIPTION_TYPES = ("offer", "answer", "pranswer", "rollback")
_ICE_URL = re.compile(r"^(stun|turns?):[^\s,]+$")


def rtc_data(raw) -> Optional[dict]:
    """`{"description": {type, sdp}}`, `{"candidate": {...} | null}` or `{"reset": true}` (the
    sender rebuilt a connection that would not come back; the receiver rebuilds its side), else None."""
    if not isinstance(raw, dict) or len(raw) != 1:
        return None
    if "reset" in raw:
        return {"reset": True} if raw["reset"] is True else None
    if "description" in raw:
        desc = raw["description"]
        if not isinstance(desc, dict) or desc.get("type") not in _DESCRIPTION_TYPES:
            return None
        sdp = desc.get("sdp", "")
        if not isinstance(sdp, str):
            return None
        out = {"description": {"type": desc["type"], "sdp": sdp}}
    elif "candidate" in raw:
        candidate = raw["candidate"]
        if candidate is not None and not isinstance(candidate, dict):
            return None
        out = {"candidate": candidate}  # None: the sender has no more candidates
    else:
        return None
    if len(json.dumps(out)) > MAX_RTC_BYTES:
        return None
    return out


def ice_servers(text: str) -> list[dict]:
    """ICE_SERVERS from .env: comma-separated stun: / turn: addresses. Empty by default, so
    voice and camera go only over the viewers' own addresses (the Tailscale ones among them)."""
    urls = (part.strip() for part in (text or "").split(","))
    return [{"urls": url} for url in urls if _ICE_URL.match(url)]
