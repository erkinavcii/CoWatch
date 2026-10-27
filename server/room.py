"""Room state and sync rules. The server is the single source of truth for playback:
clients send requests (play/pause/seek/buffering) and follow the broadcast state."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Optional

from starlette.websockets import WebSocket

log = logging.getLogger("cowatch.room")

BUFFER_TIMEOUT_S = 20.0


def now_ms() -> float:
    return time.monotonic() * 1000.0


class Client:
    def __init__(self, ws: Optional[WebSocket]):
        self.id = uuid.uuid4().hex[:8]
        self.ws = ws
        self.name = "?"
        self.color = ""
        self.last_poke = 0.0
        self.buffering_since: Optional[float] = None
        self.alive = True
        self._lock = asyncio.Lock()

    @property
    def buffering(self) -> bool:
        return self.buffering_since is not None

    async def send(self, msg: dict, lossy: bool = False) -> bool:
        """`lossy`: skip the message if one is still on its way to this client. For cursor
        positions, where only the newest one matters and a slow link should not pile up."""
        if not self.alive or self.ws is None:
            return False
        if lossy and self._lock.locked():
            return False
        try:
            async with self._lock:
                await asyncio.wait_for(self.ws.send_json(msg), timeout=10)
            return True
        except Exception:  # closed socket, timeout...
            self.alive = False
            return False


class Room:
    def __init__(self) -> None:
        self.clients: dict[str, Client] = {}
        self.playing = False
        self.position = 0.0  # film seconds at `updated_at`
        self.updated_at = now_ms()
        self.rate = 1.0
        self.loading = False  # server is restarting the stream
        self.seq = 0

    # ---- time -------------------------------------------------------------
    def waiting(self) -> list[str]:
        return [c.id for c in self.clients.values() if c.buffering]

    def running(self) -> bool:
        return self.playing and not self.loading and not self.waiting()

    def current_position(self) -> float:
        if not self.running():
            return self.position
        return self.position + (now_ms() - self.updated_at) / 1000.0 * self.rate

    def _freeze(self) -> None:
        """Snapshot the position before any change that affects whether time runs."""
        self.position = self.current_position()
        self.updated_at = now_ms()

    def _changed(self) -> bool:
        self.seq += 1
        return True

    # ---- commands (return True when the state changed) ----------------------
    def play(self) -> bool:
        if self.playing:
            return False
        self._freeze()
        self.playing = True
        return self._changed()

    def pause(self) -> bool:
        if not self.playing:
            return False
        self._freeze()
        self.playing = False
        return self._changed()

    def seek(self, position: float) -> bool:
        self._freeze()
        self.position = max(0.0, position)
        return self._changed()

    def set_loading(self, value: bool) -> bool:
        if self.loading == value:
            return False
        self._freeze()
        self.loading = value
        return self._changed()

    def set_buffering(self, client: Client, value: bool) -> bool:
        if client.buffering == value:
            return False
        self._freeze()
        client.buffering_since = time.monotonic() if value else None
        return self._changed()

    def reset(self) -> None:
        self.playing = False
        self.position = 0.0
        self.updated_at = now_ms()
        self.loading = False
        for client in self.clients.values():
            client.buffering_since = None
        self._changed()

    # ---- members ------------------------------------------------------------
    def add(self, ws: Optional[WebSocket]) -> Client:
        client = Client(ws)
        self.clients[client.id] = client
        return client

    def remove(self, client_id: str) -> bool:
        """Returns True if removing the client changed the playback state."""
        client = self.clients.get(client_id)
        if client is None:
            return False
        was_buffering = client.buffering
        if was_buffering:
            self._freeze()
        del self.clients[client_id]
        return self._changed() if was_buffering else False

    def expired_buffering(self) -> list[Client]:
        limit = time.monotonic() - BUFFER_TIMEOUT_S
        return [c for c in self.clients.values() if c.buffering_since is not None and c.buffering_since < limit]

    # ---- messages -------------------------------------------------------------
    def state_msg(self) -> dict:
        return {
            "type": "state",
            "playing": self.playing,
            "position": round(self.position, 3),
            "updatedAt": self.updated_at,
            "rate": self.rate,
            "loading": self.loading,
            "waiting": self.waiting(),
            "seq": self.seq,
        }

    def members_msg(self) -> dict:
        return {
            "type": "members",
            "members": [
                {"id": c.id, "name": c.name, "color": c.color, "buffering": c.buffering}
                for c in self.clients.values()
            ],
        }

    async def broadcast(self, msg: dict, exclude: Optional[Client] = None, lossy: bool = False) -> None:
        clients = [c for c in self.clients.values() if c is not exclude]
        if clients:
            await asyncio.gather(*(c.send(msg, lossy=lossy) for c in clients))
