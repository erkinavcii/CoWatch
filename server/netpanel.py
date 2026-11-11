"""Connection panel: whose link keeps up with the film, and how fast the friends' link is.

- Each player measures how fast its film segments arrive and says so every ten seconds
  (`netstat`, checked in presence.netstat_values); the people chips show it next to the film's
  bitrate (`stream_kbps`).
- A viewer who keeps stalling (room.STALL_COUNT times in room.STALL_WINDOW_S): the host and
  co-hosts get one notice (`stall_notice`) with what can be done about it.
- The host measures the Funnel link from Settings: the server downloads random bytes from its
  own public link (`measure`), through Tailscale's relay like a friend would.
"""

from __future__ import annotations

import os
import time
from typing import Optional
from urllib.parse import urlsplit

import httpx

from .net import tls
from .room import STALL_COUNT, STALL_NOTICE_EVERY_S, STALL_WINDOW_S, Client

# A stall this soon after another one is the same stall (the server ignores a viewer's stalls
# for a while after letting the room go on, and the page may report it again), and one this
# soon after a seek or a restart of the stream is everyone loading the new place.
STALL_MIN_GAP_S = 10.0
STALL_CALM_AFTER_SEEK_S = 10.0


def stream_kbps(public: Optional[dict], audio_kbps: int) -> Optional[int]:
    """What the stream needs: a converted one its video target plus the AAC sound, a copied one
    the source file's bitrate. None when unknown."""
    if not public:
        return None
    if public.get("mode") == "transcode" and public.get("targetKbps"):
        return int(public["targetKbps"]) + audio_kbps
    return int(public.get("bitrateKbps") or 0) or None


def stall_notice(client: Client, now: float, noticed: dict[str, float], film_kbps: Optional[int],
                 funnel: bool) -> Optional[dict]:
    """Counts one stall of `client`. The notice for the host when it is the STALL_COUNT-th
    within STALL_WINDOW_S and this viewer has not had one in STALL_NOTICE_EVERY_S, else None.
    `noticed`: viewer -> when its last notice went (monotonic), kept across reconnects."""
    if client.stalls and now - client.stalls[-1] < STALL_MIN_GAP_S:
        return None
    client.stalls.append(now)
    if len(client.stalls) < STALL_COUNT or now - client.stalls[0] > STALL_WINDOW_S:
        return None
    who = client.viewer or client.id
    if now - noticed.get(who, -STALL_NOTICE_EVERY_S) < STALL_NOTICE_EVERY_S:
        return None
    noticed[who] = now
    client.stalls.clear()
    return {
        "type": "net_hint", "id": client.id, "name": client.name,
        "mbps": (client.net or {}).get("mbps"), "filmKbps": film_kbps, "stalls": STALL_COUNT,
        "minutes": round(STALL_WINDOW_S / 60), "funnel": funnel,
    }


# ---- the Funnel speed test ------------------------------------------------------------
SPEEDTEST_DEFAULT_BYTES = 24 * 1024 * 1024
SPEEDTEST_MAX_BYTES = 32 * 1024 * 1024
SPEEDTEST_CHUNK = 64 * 1024
SPEEDTEST_MAX_S = 60.0  # a slower link: measured with what arrived by then
SPEEDTEST_HOLD_S = 120.0  # a download that never finished frees the endpoint after this

TRANSPORT: Optional[httpx.AsyncBaseTransport] = None  # the tests answer in place of the Funnel
DOH_URL = "https://cloudflare-dns.com/dns-query"


class Speedtest:
    """One download at a time, and one measurement at a time: each is 32 MB at most."""

    def __init__(self) -> None:
        self.serving_until = 0.0
        self.measuring = False

    def take_serving(self) -> bool:
        now = time.monotonic()
        if now < self.serving_until:
            return False
        self.serving_until = now + SPEEDTEST_HOLD_S
        return True

    def release_serving(self) -> None:
        self.serving_until = 0.0


speedtest = Speedtest()


def speedtest_bytes(requested: Optional[int]) -> int:
    if not requested or requested <= 0:
        return SPEEDTEST_DEFAULT_BYTES
    return min(int(requested), SPEEDTEST_MAX_BYTES)


async def random_body(size: int):
    """Random bytes (nothing on the way can compress them); frees the endpoint when done."""
    try:
        left = size
        while left > 0:
            chunk = os.urandom(min(SPEEDTEST_CHUNK, left))
            left -= len(chunk)
            yield chunk
    finally:
        speedtest.release_serving()


async def public_address(name: str) -> Optional[str]:
    """The address the internet sees for our name. On this computer MagicDNS answers with the
    Tailscale address, and the test would never leave the computer; a public resolver gives
    the Funnel relay's. None when it cannot be asked."""
    try:
        async with httpx.AsyncClient(timeout=8, verify=tls(), transport=TRANSPORT) as client:
            res = await client.get(DOH_URL, params={"name": name, "type": "A"},
                                   headers={"accept": "application/dns-json"})
            res.raise_for_status()
            for answer in res.json().get("Answer") or []:
                if answer.get("type") == 1 and answer.get("data"):
                    return str(answer["data"])
    except (httpx.HTTPError, ValueError):
        return None
    return None


async def measure(link: str, key: str, size: int = SPEEDTEST_DEFAULT_BYTES) -> dict:
    """Downloads `size` random bytes from our own public link and times it, from the first byte
    to the last. `relay`: whether it went through the public address (the Funnel relay)."""
    parts = urlsplit(link)
    name = parts.hostname or ""
    path = f"/api/speedtest?bytes={size}&k={key}"
    address = await public_address(name)
    url, headers, extensions = f"{parts.scheme}://{parts.netloc}{path}", {}, {}
    if address:
        url = f"{parts.scheme}://{address}{path}"
        headers = {"host": parts.netloc}
        extensions = {"sni_hostname": name}  # the certificate is checked against our name
    got = 0
    async with httpx.AsyncClient(timeout=httpx.Timeout(30, read=30), verify=tls(), transport=TRANSPORT) as client:
        request = client.build_request("GET", url, headers=headers, extensions=extensions)
        res = await client.send(request, stream=True)
        try:
            if res.status_code != 200:
                raise httpx.HTTPStatusError(f"status {res.status_code}", request=request, response=res)
            first = None
            async for chunk in res.aiter_bytes():
                if first is None:
                    first = time.perf_counter()
                got += len(chunk)
                if time.perf_counter() - first > SPEEDTEST_MAX_S:
                    break
            seconds = time.perf_counter() - (first or time.perf_counter())
        finally:
            await res.aclose()
    seconds = max(seconds, 0.001)
    return {"mbps": round(got * 8 / seconds / 1e6, 2), "bytes": got, "seconds": round(seconds, 2),
            "relay": bool(address)}
