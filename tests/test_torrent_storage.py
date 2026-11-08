"""The downloaded torrents: their size and the clean-up, through the Node helper and the API."""

import asyncio
import json
import os
import shutil
import socket
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.main import app, ctl
from server.torrent_client import TorrentHelper

KEY = "test-key"
ROOT = Path(__file__).resolve().parent.parent
HELPER = ROOT / "torrent-helper"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.skipif(not (shutil.which("node") and (HELPER / "node_modules").is_dir()),
                    reason="the torrent helper is not installed (node, npm install)")
def test_the_helper_measures_and_empties_the_download_folder(tmp_path):
    folder = tmp_path / "torrents"
    (folder / "Some.Show.S01").mkdir(parents=True)
    (folder / "Some.Show.S01" / "e01.mkv").write_bytes(b"x" * 3000)
    (folder / "Some.Show.S01" / "e02.mkv").write_bytes(b"x" * 2000)
    (folder / "Film.2024.mkv").write_bytes(b"x" * 1000)
    # A torrent seeded on this computer stands in for the film playing.
    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    (seed_dir / "Playing.Film.mkv").write_bytes(os.urandom(40000))
    seeder_js = tmp_path / "seeder.mjs"
    seeder_js.write_text(
        f"import WebTorrent from {(HELPER / 'node_modules' / 'webtorrent' / 'index.js').as_uri()!r}\n"
        "const client = new WebTorrent({ dht: false, tracker: false, lsd: false })\n"
        f"client.seed({str(seed_dir / 'Playing.Film.mkv')!r}, {{ announce: [] }}, (t) => {{\n"
        "  const port = client.address().port\n"
        "  console.log(JSON.stringify({ magnet: t.magnetURI, hash: t.infoHash, port }))\n"
        "})\n", encoding="utf-8")
    seeder = subprocess.Popen(["node", str(seeder_js)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    port = _free_port()
    env = dict(os.environ, HELPER_PORT=str(port), TORRENT_DIR=str(folder))
    proc = subprocess.Popen(["node", "index.mjs"], cwd=HELPER, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    helper = TorrentHelper(f"http://127.0.0.1:{port}")
    try:
        seed = json.loads(seeder.stdout.readline())

        async def run():
            for _ in range(100):
                if await helper.healthy():
                    break
                await asyncio.sleep(0.1)
            # No torrent is loaded yet: nothing is kept, a made-up hash changes nothing.
            assert await helper.storage(["ab" * 20, "not-a-hash"]) == {"total": 6000, "kept": 0}
            await helper.add(seed["magnet"], peers=[f"127.0.0.1:{seed['port']}"])
            await helper.prepare(seed["hash"], 0)
            for _ in range(100):  # until the whole file is here
                if (await helper.info(seed["hash"]))["progress"] >= 1:
                    break
                await asyncio.sleep(0.1)
            assert await helper.storage([seed["hash"]]) == {"total": 46000, "kept": 40000}
            done = await helper.cleanup([seed["hash"]])
            assert done == {"freed": 6000, "failed": 0, "total": 40000, "kept": 40000}
            # Without it in the list, the film goes too.
            assert (await helper.cleanup([]))["freed"] == 40000

        asyncio.run(run())
        assert folder.is_dir() and list(folder.iterdir()) == []
    finally:
        for p in (proc, seeder):
            p.terminate()
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()


def test_only_the_host_cleans_up_and_the_film_playing_stays(monkeypatch):
    asked = {}

    async def storage(keep):
        asked["storage"] = keep
        return {"total": 10, "kept": 4}

    async def cleanup(keep):
        asked["cleanup"] = keep
        return {"freed": 6, "failed": 0, "total": 4, "kept": 4}

    monkeypatch.setattr(ctl.helper, "storage", storage)
    monkeypatch.setattr(ctl.helper, "cleanup", cleanup)
    monkeypatch.setattr(ctl, "opening_hash", "cd" * 20)
    with TestClient(app, cookies={"cw_key": KEY}) as guest:
        assert guest.get("/api/torrents/storage").status_code == 403
        assert guest.post("/api/torrents/cleanup").status_code == 403
    assert asked == {}
    with TestClient(app, base_url="http://localhost:8000", cookies={"cw_key": KEY}, client=("127.0.0.1", 5)) as host:
        assert host.get("/api/torrents/storage").json() == {"total": 10, "kept": 4}
        assert host.post("/api/torrents/cleanup").json()["freed"] == 6
    assert asked == {"storage": ["cd" * 20], "cleanup": ["cd" * 20]}


def test_a_helper_that_is_not_running_says_so(monkeypatch):
    monkeypatch.setattr(ctl.helper, "base", f"http://127.0.0.1:{_free_port()}")
    with TestClient(app, base_url="http://localhost:8000", cookies={"cw_key": KEY}, client=("127.0.0.1", 5)) as host:
        resp = host.get("/api/torrents/storage")
        assert resp.status_code == 503 and resp.json()["detail"] == "helper_down"
