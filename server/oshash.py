"""OpenSubtitles movie hash: file size + the 64-bit little-endian word sums of the first
and last 64 KB, modulo 2**64, as 16 hex digits."""

from __future__ import annotations

import os
import struct
from pathlib import Path

CHUNK = 65536
_MASK = 0xFFFFFFFFFFFFFFFF


def _sum_words(data: bytes) -> int:
    usable = len(data) - len(data) % 8
    total = 0
    for (word,) in struct.iter_unpack("<Q", data[:usable]):
        total = (total + word) & _MASK
    return total


def hash_from_chunks(size: int, head: bytes, tail: bytes) -> str:
    value = (size + _sum_words(head[:CHUNK]) + _sum_words(tail[-CHUNK:])) & _MASK
    return f"{value:016x}"


def hash_file(path: str | os.PathLike) -> str:
    path = Path(path)
    size = path.stat().st_size
    with path.open("rb") as fh:
        head = fh.read(CHUNK)
        fh.seek(max(0, size - CHUNK))
        tail = fh.read(CHUNK)
    return hash_from_chunks(size, head, tail)
