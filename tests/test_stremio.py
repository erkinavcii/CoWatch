import asyncio
import json
import struct

import httpx
import pytest
from fastapi.testclient import TestClient

import server.addons as addons
from server import main, stremio
from server.addons import AddonStore
from server.main import app, ctl
from tests.test_addons import KEY, META, STREAMS, handler

KEY_NAME = b"_https://app.strem.io\x00\x01addons"
HOST = {"base_url": "http://localhost:8000", "cookies": {"cw_key": KEY}, "client": ("127.0.0.1", 5)}


def varint(n: int) -> bytes:
    out = bytearray()
    while True:
        byte = n & 0x7F
        n >>= 7
        out.append(byte | (0x80 if n else 0))
        if not n:
            return bytes(out)


def value(items) -> bytes:
    return b"\x01" + json.dumps(items).encode()  # Chromium: 1 = UTF-8


def log_file(*batches) -> bytes:
    """A LevelDB log: each batch is (sequence, [(key, value or None for a deletion)])."""
    out = b""
    for sequence, entries in batches:
        record = struct.pack("<QI", sequence, len(entries))
        for key, val in entries:
            record += (b"\x01" if val is not None else b"\x00") + varint(len(key)) + key
            if val is not None:
                record += varint(len(val)) + val
        out += struct.pack("<IHB", 0, len(record), 1) + record  # one full record
    return out


def block(entries) -> bytes:
    out = b""
    for key, val in entries:
        out += varint(0) + varint(len(key)) + varint(len(val)) + key + val
    return out + struct.pack("<II", 0, 1)  # one restart point at 0


def table_file(sequence: int, key: bytes, val: bytes) -> bytes:
    """A LevelDB table (.ldb) with one uncompressed data block."""
    internal = key + ((sequence << 8) | 1).to_bytes(8, "little")
    data = block([(internal, val)])
    out = data + b"\x00" + b"\x00" * 4  # compression type, crc
    index = block([(internal, varint(0) + varint(len(data)))])
    index_offset = len(out)
    out += index + b"\x00" + b"\x00" * 4
    handles = varint(0) + varint(0) + varint(index_offset) + varint(len(index))
    return out + handles.ljust(40, b"\x00") + struct.pack("<Q", stremio._TABLE_MAGIC)


ITEMS = [
    {"transportUrl": "https://one.example/manifest.json", "manifest": {"resources": ["stream"], "types": ["movie"]}},
    {"transportUrl": "https://two.example/abc/", "manifest": {}},  # no embedded manifest: the fetch decides
    {"transportUrl": "https://one.example/manifest.json", "manifest": {}},  # twice
    {"transportUrl": "http://127.0.0.1:11470/manifest.json", "manifest": {"resources": ["stream"]}},  # local
    {"transportUrl": "https://tube.example/manifest.json",
     "manifest": {"resources": ["catalog"], "types": ["channel"]}},  # channels only
    {"transportUrl": "https://old.example/stremio/v1", "manifest": {}},  # the old protocol
    {"transportUrl": "https://user:pw@three.example/manifest.json", "manifest": {}},
    "not an add-on",
]


@pytest.fixture
def stremio_dir(tmp_path, monkeypatch):
    """Stremio's leveldb folder in a temp folder; the real one on this computer stays out."""
    for name in ("LOCALAPPDATA", "APPDATA", "USERPROFILE", "HOME"):
        monkeypatch.setenv(name, str(tmp_path / "home"))
    db = tmp_path / "leveldb"
    db.mkdir()
    monkeypatch.setenv("STREMIO_DATA_DIR", str(db))
    return db


def test_snappy():
    # "abcd" as a literal, then 8 bytes copied from 4 back (overlapping)
    assert stremio._snappy_decompress(bytes([12, 0x0C]) + b"abcd" + bytes([0x1E, 4, 0])) == b"abcd" * 3
    for bad in (bytes([12, 0x0C]) + b"ab", bytes([4, 0x1E, 9, 0]), bytes([9, 0x0C]) + b"abcd"):
        with pytest.raises(ValueError):
            stremio._snappy_decompress(bad)


def test_chromium_values():
    assert stremio._decode_value(b"\x01[1]") == "[1]"
    assert stremio._decode_value(b"\x00" + "[2]".encode("utf-16le")) == "[2]"


def test_addresses_from_stremio(stremio_dir):
    (stremio_dir / "000003.log").write_bytes(log_file((5, [(b"_https://app.strem.io\x00\x01other", b"\x01x"),
                                                          (KEY_NAME, value(ITEMS))])))
    assert stremio.addon_urls() == ["https://one.example/manifest.json", "https://two.example/abc/manifest.json"]


def test_the_newest_list_wins(stremio_dir):
    old = [{"transportUrl": "https://old-list.example/manifest.json"}]
    new = [{"transportUrl": "https://new-list.example/manifest.json"}]
    (stremio_dir / "000005.ldb").write_bytes(table_file(9, KEY_NAME, value(old)))
    (stremio_dir / "000004.log").write_bytes(log_file((3, [(KEY_NAME, value(new))])))
    assert stremio.addon_urls() == ["https://old-list.example/manifest.json"]  # the table's write is newer
    (stremio_dir / "000006.log").write_bytes(log_file((12, [(KEY_NAME, value(new))])))
    assert stremio.addon_urls() == ["https://new-list.example/manifest.json"]
    (stremio_dir / "000007.log").write_bytes(log_file((20, [(KEY_NAME, None)])))
    assert stremio.addon_urls() == []  # cleared in Stremio


def test_no_stremio(stremio_dir, monkeypatch):
    with pytest.raises(stremio.StremioError) as info:
        stremio.addon_urls()  # the folder holds no database files
    assert info.value.code == "stremio_not_found"
    (stremio_dir / "000003.log").write_bytes(log_file((5, [(b"_https://app.strem.io\x00\x01volume", b"\x011")])))
    with pytest.raises(stremio.StremioError) as info:
        stremio.addon_urls()  # a database, but no add-on list in it
    assert info.value.code == "stremio_not_found"
    (stremio_dir / "000004.log").write_bytes(log_file((6, [(KEY_NAME, b"\x01{not json")])))
    with pytest.raises(stremio.StremioError) as info:
        stremio.addon_urls()
    assert info.value.code == "stremio_unreadable"


def test_import_adds_what_answers(tmp_path, monkeypatch):
    monkeypatch.setattr(addons, "DEFAULT_ADDONS", (META,))
    store = AddonStore(tmp_path / "addons.json", transport=httpx.MockTransport(handler))
    result = asyncio.run(store.import_urls([STREAMS, META, "https://missing.example", "ftp://x"]))
    assert [a["name"] for a in result["added"]] == ["Streams"]
    assert [s["error"] for s in result["skipped"]] == ["addon_exists", "addon_unreachable", "addon_bad_url"]
    assert store.user_urls() == [STREAMS]
    again = asyncio.run(store.import_urls([STREAMS]))
    assert again["added"] == [] and again["skipped"][0]["error"] == "addon_exists"


def test_import_is_for_the_host_only(tmp_path, monkeypatch):
    monkeypatch.setattr(addons, "DEFAULT_ADDONS", (META,))
    monkeypatch.setattr(ctl, "addons", AddonStore(tmp_path / "a.json", transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(main.stremio, "addon_urls", lambda: [STREAMS, "https://missing.example/manifest.json"])
    with TestClient(app, cookies={"cw_key": KEY}) as friend:
        assert friend.post("/api/addons/stremio").status_code == 403
    with TestClient(app, **HOST) as host:
        body = host.post("/api/addons/stremio").json()
        assert body["found"] == 2 and [a["name"] for a in body["added"]] == ["Streams"]

        def missing():
            raise stremio.StremioError("no Stremio here")
        monkeypatch.setattr(main.stremio, "addon_urls", missing)
        answer = host.post("/api/addons/stremio")
        assert answer.status_code == 404 and answer.json()["detail"] == "stremio_not_found"
