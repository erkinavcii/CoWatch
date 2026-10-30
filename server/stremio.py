"""The add-ons installed in Stremio on this computer.

Stremio's desktop app keeps its add-on list in Chromium's local storage: a LevelDB under
its data folder. This module reads that list, so the host can import the add-ons they
already use without copying addresses by hand. Nothing leaves the computer: the list is
read from disk, and only the add-on manifests are fetched, exactly as when adding one by
hand. The Stremio account key is never read or sent anywhere.

The LevelDB files are read directly because Stremio may not be running. A small Snappy
decompressor is included for the blocks Chromium compresses; it is the only format detail
that would otherwise need a native dependency."""

from __future__ import annotations

import json
import os
import struct
import sys
from pathlib import Path
from typing import Iterator, Optional
from urllib.parse import urlsplit

MAX_DB_BYTES = 64 * 1024 * 1024
MAX_VALUE_BYTES = 4 * 1024 * 1024
_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "0.0.0.0"}
_STREMIO_MARK = b"strem.io"
_ADDONS_KEY = b"\x01addons"
_TABLE_MAGIC = 0xDB4775248B80FB57
_LOG_BLOCK = 32 * 1024


class StremioError(Exception):
    def __init__(self, message: str, code: str = "stremio_not_found"):
        super().__init__(message)
        self.code = code


def _varint(data: bytes, pos: int) -> tuple[int, int]:
    value = shift = 0
    while pos < len(data):
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, pos
        shift += 7
        if shift > 63:
            break
    raise ValueError("bad varint")


def _snappy_decompress(data: bytes) -> bytes:
    """A raw Snappy block, as used by LevelDB. Pure Python, so importing add-ons does not
    add a native dependency to every install."""
    length, pos = _varint(data, 0)
    if length > MAX_VALUE_BYTES:
        raise ValueError("snappy block too large")
    out = bytearray()
    while pos < len(data):
        tag = data[pos]
        pos += 1
        kind = tag & 3
        if kind == 0:  # literal
            size = tag >> 2
            if size < 60:
                size += 1
            else:
                extra = size - 59
                if pos + extra > len(data):
                    raise ValueError("bad literal")
                size = int.from_bytes(data[pos:pos + extra], "little") + 1
                pos += extra
            if pos + size > len(data):
                raise ValueError("bad literal")
            out += data[pos:pos + size]
            pos += size
        else:  # copy from the bytes already produced
            if kind == 1:
                size = ((tag >> 2) & 7) + 4
                if pos >= len(data):
                    raise ValueError("bad copy")
                offset = ((tag & 0xE0) << 3) | data[pos]
                pos += 1
            elif kind == 2:
                size = (tag >> 2) + 1
                if pos + 2 > len(data):
                    raise ValueError("bad copy")
                offset = int.from_bytes(data[pos:pos + 2], "little")
                pos += 2
            else:
                size = (tag >> 2) + 1
                if pos + 4 > len(data):
                    raise ValueError("bad copy")
                offset = int.from_bytes(data[pos:pos + 4], "little")
                pos += 4
            if offset < 1 or offset > len(out):
                raise ValueError("bad copy offset")
            for _ in range(size):
                out.append(out[-offset])
        if len(out) > MAX_VALUE_BYTES:
            raise ValueError("snappy block too large")
    if len(out) != length:
        raise ValueError("bad snappy length")
    return bytes(out)


def _block_entries(block: bytes) -> Iterator[tuple[bytes, bytes]]:
    """The key/value pairs in one LevelDB block, with the prefix sharing undone."""
    if len(block) < 4:
        return
    restarts = struct.unpack_from("<I", block, len(block) - 4)[0]
    end = len(block) - 4 - 4 * restarts
    if end < 0:
        return
    pos, key = 0, b""
    while pos < end:
        shared, pos = _varint(block, pos)
        non_shared, pos = _varint(block, pos)
        value_len, pos = _varint(block, pos)
        if shared > len(key) or pos + non_shared + value_len > end:
            return
        key = key[:shared] + block[pos:pos + non_shared]
        pos += non_shared
        value = block[pos:pos + value_len]
        pos += value_len
        yield key, value


def _read_block(data: bytes, offset: int, size: int) -> bytes:
    if offset < 0 or size < 0 or offset + size + 5 > len(data):
        raise ValueError("block outside table")
    block = data[offset:offset + size]
    kind = data[offset + size]
    if kind == 0:
        return block
    if kind == 1:
        return _snappy_decompress(block)
    raise ValueError("unknown block compression")


def _table_entries(path: Path) -> Iterator[tuple[bytes, Optional[bytes], int]]:
    data = path.read_bytes()
    if len(data) < 48:
        return
    footer = data[-48:]
    if struct.unpack_from("<Q", footer, 40)[0] != _TABLE_MAGIC:
        return
    pos = 0
    _meta_offset, pos = _varint(footer, pos)
    _meta_size, pos = _varint(footer, pos)
    index_offset, pos = _varint(footer, pos)
    index_size, pos = _varint(footer, pos)
    index = _read_block(data, index_offset, index_size)
    for _last_key, handle in _block_entries(index):
        offset, handle_pos = _varint(handle, 0)
        size, _handle_pos = _varint(handle, handle_pos)
        block = _read_block(data, offset, size)
        for key, value in _block_entries(block):
            if len(key) < 8:
                continue
            trailer = int.from_bytes(key[-8:], "little")  # sequence << 8 | type; type 0 = deletion
            sequence = trailer >> 8
            deleted = trailer & 0xFF == 0
            yield key[:-8], None if deleted else value, sequence


def _log_records(path: Path) -> Iterator[bytes]:
    """The complete write batches in a LevelDB log file, reassembled across blocks."""
    data = path.read_bytes()
    pending = b""
    for start in range(0, len(data), _LOG_BLOCK):
        block = data[start:start + _LOG_BLOCK]
        pos = 0
        while pos + 7 <= len(block):
            _crc, length, kind = struct.unpack_from("<IHB", block, pos)
            pos += 7
            if kind == 0 or length == 0 or pos + length > len(block):
                break
            fragment = block[pos:pos + length]
            pos += length
            if kind == 1:  # full record
                pending = b""
                yield fragment
            elif kind == 2:  # first fragment
                pending = fragment
            elif kind == 3:  # middle fragment
                pending += fragment
            elif kind == 4:  # last fragment
                pending += fragment
                yield pending
                pending = b""
            else:
                pending = b""


def _batch_entries(record: bytes) -> Iterator[tuple[bytes, Optional[bytes], int]]:
    if len(record) < 12:
        return
    sequence = int.from_bytes(record[:8], "little")
    count = int.from_bytes(record[8:12], "little")
    if count > 10000:
        return
    pos = 12
    for index in range(count):
        if pos >= len(record):
            return
        tag = record[pos]
        pos += 1
        key_len, pos = _varint(record, pos)
        key = record[pos:pos + key_len]
        pos += key_len
        if tag == 1:
            value_len, pos = _varint(record, pos)
            value = record[pos:pos + value_len]
            pos += value_len
            yield key, value, sequence + index
        elif tag == 0:
            yield key, None, sequence + index
        else:
            return


def _db_entries(db_dir: Path) -> Iterator[tuple[bytes, Optional[bytes], int]]:
    for path in sorted(db_dir.iterdir()):
        try:
            if path.stat().st_size > MAX_DB_BYTES:
                continue
            suffix = path.suffix.lower()
            if suffix in (".ldb", ".sst"):
                yield from _table_entries(path)
            elif suffix == ".log":
                for record in _log_records(path):
                    yield from _batch_entries(record)
        except (OSError, ValueError, struct.error):
            continue


def _decode_value(raw: bytes) -> str:
    """Chromium's local storage value: 0 = UTF-16LE, 1 = UTF-8, then the text."""
    if not raw:
        return ""
    if raw[0] == 0:
        return raw[1:].decode("utf-16le", errors="replace")
    if raw[0] == 1:
        return raw[1:].decode("utf-8", errors="replace")
    return raw.decode("utf-8", errors="replace")


def _latest_addons(db_dir: Path) -> Optional[object]:
    """The newest `addons` value in the database, or None when it has never been written."""
    best_sequence = -1
    best_value: Optional[bytes] = None
    for key, value, sequence in _db_entries(db_dir):
        if sequence < best_sequence:
            continue
        if key.endswith(_ADDONS_KEY) and _STREMIO_MARK in key.lower():
            best_sequence, best_value = sequence, value
    if best_sequence < 0:
        return None
    if best_value is None:
        return []  # the list was cleared in Stremio
    if len(best_value) > MAX_VALUE_BYTES:
        raise StremioError("Stremio's add-on list is too large", "stremio_unreadable")
    try:
        return json.loads(_decode_value(best_value))
    except (UnicodeError, ValueError):
        raise StremioError("Stremio's add-on list could not be read", "stremio_unreadable") from None


def _compatible(manifest: dict) -> bool:
    """Whether CoWatch can use anything in this manifest: catalogs, details, sources or
    subtitles for films and series. Stremio also has channel-only add-ons."""
    if not manifest:
        return True  # no embedded manifest: the fetch will tell
    names = set()
    for resource in manifest.get("resources") or []:
        if isinstance(resource, str):
            names.add(resource)
        elif isinstance(resource, dict) and isinstance(resource.get("name"), str):
            names.add(resource["name"])
    if not names & {"catalog", "meta", "stream", "subtitles"}:
        return False
    types = {value for value in manifest.get("types") or [] if isinstance(value, str)}
    return not types or bool(types & {"movie", "series"})


def _usable_url(text: str) -> bool:
    try:
        parts = urlsplit(text)
    except ValueError:
        return False
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    if parts.hostname.lower() in _LOCAL_HOSTS or parts.username or parts.password:
        return False
    if parts.query or parts.fragment:
        return False
    # Stremio's old add-ons answer at /stremio/v1, not at /stremio/v1/manifest.json.
    return not parts.path.rstrip("/").endswith("/stremio/v1")


def _urls_from_collection(items) -> list[str]:
    if not isinstance(items, list):
        return []
    out: list[str] = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        manifest = item.get("manifest") if isinstance(item.get("manifest"), dict) else {}
        if not _compatible(manifest):
            continue
        url = str(item.get("transportUrl") or item.get("manifestUrl") or item.get("url") or "").strip()
        if not _usable_url(url):
            continue
        if not url.endswith("/manifest.json"):
            url = url.rstrip("/") + "/manifest.json"
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _looks_like_db(path: Path) -> bool:
    if not path.is_dir():
        return False
    return any(path.glob("*.ldb")) or any(path.glob("*.sst")) or any(path.glob("*.log"))


def _leveldb_dirs() -> list[Path]:
    """Where Stremio keeps Chromium's local storage on this system. STREMIO_DATA_DIR can
    point at the leveldb folder or at the Stremio data folder around it."""
    candidates: list[Path] = []
    override = os.environ.get("STREMIO_DATA_DIR", "").strip()
    if override:
        path = Path(override).expanduser()
        candidates += [path, path / "Local Storage" / "leveldb"]
    home = Path.home()
    if os.name == "nt":
        local = Path(os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local")
        roaming = Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming")
        candidates += [
            local / "Smart Code ltd" / "Stremio" / "QtWebEngine" / "Default" / "Local Storage" / "leveldb",
            roaming / "Smart Code ltd" / "Stremio" / "QtWebEngine" / "Default" / "Local Storage" / "leveldb",
        ]
    elif sys.platform == "darwin":
        candidates.append(home / "Library" / "Application Support" / "Smart Code ltd" / "Stremio"
                          / "QtWebEngine" / "Default" / "Local Storage" / "leveldb")
    else:
        candidates += [
            home / ".local" / "share" / "Smart Code ltd" / "Stremio" / "QtWebEngine" / "Default"
            / "Local Storage" / "leveldb",
            home / ".config" / "Smart Code ltd" / "Stremio" / "QtWebEngine" / "Default"
            / "Local Storage" / "leveldb",
        ]
    out: list[Path] = []
    seen = set()
    for path in candidates:
        try:
            key = os.path.normcase(str(path.resolve()))
        except OSError:
            continue
        if key not in seen and _looks_like_db(path):
            seen.add(key)
            out.append(path)
    return out


def addon_urls() -> list[str]:
    """Manifest addresses of the add-ons installed in Stremio, ready to import. Raises
    StremioError when Stremio's data or add-on list cannot be found."""
    dirs = _leveldb_dirs()
    if not dirs:
        raise StremioError("Stremio's data folder was not found", "stremio_not_found")
    error: Optional[StremioError] = None
    for db_dir in dirs:
        try:
            items = _latest_addons(db_dir)
        except StremioError as exc:
            error = exc
            continue
        if items is not None:
            return _urls_from_collection(items)
    if error is not None:
        raise error
    raise StremioError("Stremio has no saved add-on list", "stremio_not_found")
