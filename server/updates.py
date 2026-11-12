"""Is there a newer Co-Watch? Once, about 30 s after the start, and then once a day, the server
asks GitHub for the latest release. If it is newer than this one, the host (and only the host)
sees a small notice with a link to the release page: no question, no automatic update.

The request carries nothing about the user: a generic User-Agent with the version, no token.
UPDATE_CHECK=0 turns it off (the tests run with it off); UPDATE_URL points it elsewhere (the
browser test answers from a local server)."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

import httpx

from .net import tls
from .version import VERSION

log = logging.getLogger("cowatch")

REPO = "erkinavcii/CoWatch"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASE_PAGE = f"https://github.com/{REPO}/releases/tag/"
FIRST_DELAY_S = 30
EVERY_S = 24 * 3600
TIMEOUT_S = 10
TRANSPORT: Optional[httpx.AsyncBaseTransport] = None  # tests: an httpx transport in place of GitHub

_SEMVER = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")


def parse(tag: object) -> Optional[tuple[int, int, int]]:
    """"v0.10.0" -> (0, 10, 0). A pre-release ("v0.3.0-beta.1") or anything else -> None."""
    if not isinstance(tag, str):
        return None
    m = _SEMVER.fullmatch(tag.strip())
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def is_newer(tag: object, current: str = VERSION) -> bool:
    latest, mine = parse(tag), parse(current)
    return latest is not None and mine is not None and latest > mine


class UpdateCheck:
    def __init__(self, url: str = LATEST_URL, current: str = VERSION) -> None:
        self.url = url
        self.current = current
        self.latest: Optional[dict] = None  # {"version", "url"} when a newer release is out
        self.failing = False  # an unreachable GitHub is logged once, not every day

    async def check(self) -> Optional[dict]:
        headers = {"User-Agent": f"Co-Watch/{self.current}", "Accept": "application/vnd.github+json"}
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_S, verify=tls(), transport=TRANSPORT,
                                         headers=headers, follow_redirects=True) as client:
                res = await client.get(self.url)
                res.raise_for_status()
                data = res.json()
        except (httpx.HTTPError, ValueError) as exc:
            if not self.failing:
                log.info("Update check failed: %s", exc or type(exc).__name__)
            self.failing = True
            return self.latest
        self.failing = False
        if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
            return self.latest
        tag = data.get("tag_name")
        if is_newer(tag, self.current):
            version = "%d.%d.%d" % parse(tag)
            if not self.latest or self.latest["version"] != version:
                log.info("Co-Watch %s is out (this is %s)", version, self.current)
            self.latest = {"version": version, "url": RELEASE_PAGE + tag.strip()}
        else:
            self.latest = None
        return self.latest

    async def loop(self, first_delay: float = FIRST_DELAY_S) -> None:
        await asyncio.sleep(first_delay)
        while True:
            await self.check()
            await asyncio.sleep(EVERY_S)
