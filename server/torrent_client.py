"""HTTP client for the local Node torrent helper (torrent-helper/index.mjs)."""

from __future__ import annotations

import asyncio
from typing import Optional

import httpx


class HelperError(Exception):
    def __init__(self, message: str, status: int = 500):
        super().__init__(message)
        self.status = status


class TorrentHelper:
    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")
        self._http: Optional[httpx.AsyncClient] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _client(self) -> httpx.AsyncClient:
        loop = asyncio.get_running_loop()
        if self._http is None or self._http.is_closed or self._loop is not loop:
            self._http = httpx.AsyncClient(verify=False)  # plain http on this computer
            self._loop = loop
        return self._http

    async def aclose(self) -> None:
        if self._http is not None and not self._http.is_closed:
            await self._http.aclose()
        self._http = None
        self._loop = None

    async def _request(self, method: str, path: str, timeout: float = 15, **kwargs) -> dict:
        try:
            resp = await self._client().request(method, f"{self.base}{path}", timeout=timeout, **kwargs)
        except httpx.TimeoutException as exc:
            raise HelperError("torrent helper timed out", 504) from exc
        except httpx.HTTPError as exc:
            raise HelperError("torrent helper is not running", 503) from exc
        try:
            data = resp.json()
        except ValueError:
            data = {}
        if resp.status_code >= 400:
            raise HelperError(data.get("error") or f"helper error {resp.status_code}", resp.status_code)
        return data

    async def healthy(self) -> bool:
        try:
            await self._request("GET", "/health", timeout=2)
            return True
        except HelperError:
            return False

    async def add(self, magnet: str, peers: Optional[list[str]] = None) -> dict:
        body: dict = {"magnet": magnet}
        if peers:
            body["peers"] = peers
        return await self._request("POST", "/torrents", timeout=150, json=body)

    async def info(self, info_hash: str) -> dict:
        return await self._request("GET", f"/torrents/{info_hash}", timeout=5)

    async def prepare(self, info_hash: str, file_index: int) -> dict:
        return await self._request("POST", f"/torrents/{info_hash}/prepare", json={"fileIndex": file_index})

    def file_url(self, info_hash: str, file_index: int) -> str:
        return f"{self.base}/torrents/{info_hash}/files/{file_index}"

    async def read_range(self, info_hash: str, file_index: int, start: int, end: int,
                         timeout: float = 90) -> bytes:
        try:
            resp = await self._client().get(self.file_url(info_hash, file_index),
                                            headers={"Range": f"bytes={start}-{end}"}, timeout=timeout)
        except httpx.HTTPError as exc:
            raise HelperError(f"range read failed: {exc}", 504) from exc
        if resp.status_code not in (200, 206):
            raise HelperError(f"range read failed ({resp.status_code})", resp.status_code)
        return resp.content

    async def throttle(self, download_kb: Optional[float] = None, upload_kb: Optional[float] = None) -> None:
        body = {}
        if download_kb is not None:
            body["download"] = download_kb
        if upload_kb is not None:
            body["upload"] = upload_kb
        await self._request("POST", "/throttle", json=body)

    async def storage(self, keep: list[str]) -> dict:
        """Bytes in the download folder: {total, kept} (kept = the torrents in `keep`)."""
        return await self._request("GET", "/storage", params={"keep": ",".join(keep)})

    async def cleanup(self, keep: list[str]) -> dict:
        """Drop every torrent but `keep` and delete their files: {freed, failed, total, kept}."""
        return await self._request("POST", "/cleanup", timeout=120, json={"keep": keep})

    async def remove(self, info_hash: str) -> None:
        await self._request("DELETE", f"/torrents/{info_hash}")
