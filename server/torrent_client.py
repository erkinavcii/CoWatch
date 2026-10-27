"""HTTP client for the local Node torrent helper (torrent-helper/index.mjs)."""

from __future__ import annotations

from typing import Optional

import httpx


class HelperError(Exception):
    def __init__(self, message: str, status: int = 500):
        super().__init__(message)
        self.status = status


class TorrentHelper:
    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")

    async def _request(self, method: str, path: str, timeout: float = 15, **kwargs) -> dict:
        try:
            async with httpx.AsyncClient(timeout=timeout) as http:
                resp = await http.request(method, f"{self.base}{path}", **kwargs)
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
            async with httpx.AsyncClient(timeout=timeout) as http:
                resp = await http.get(self.file_url(info_hash, file_index),
                                      headers={"Range": f"bytes={start}-{end}"})
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

    async def remove(self, info_hash: str) -> None:
        await self._request("DELETE", f"/torrents/{info_hash}")
