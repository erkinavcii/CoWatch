"""One TLS context for every outgoing HTTPS client.

httpx builds a new SSL context with the certifi bundle for each AsyncClient: about 200 ms
on Windows, spent on the event loop. With a few status polls a second that stalled the
whole server (the film did not advance, subtitle searches timed out), so the context is
made once and shared. Plain http clients (the torrent helper) pass verify=False instead."""

from __future__ import annotations

import ssl
from functools import lru_cache

import certifi


@lru_cache(maxsize=1)
def tls() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=certifi.where())
