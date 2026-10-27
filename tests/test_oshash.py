import os
import struct

from server.oshash import CHUNK, hash_file, hash_from_chunks


def reference_hash(data: bytes) -> str:
    value = len(data)
    for chunk in (data[:CHUNK], data[-CHUNK:]):
        for (word,) in struct.iter_unpack("<Q", chunk[: len(chunk) // 8 * 8]):
            value = (value + word) & 0xFFFFFFFFFFFFFFFF
    return f"{value:016x}"


def test_zero_file_hash_is_its_size(tmp_path):
    path = tmp_path / "zeros.bin"
    path.write_bytes(bytes(300_000))
    assert hash_file(path) == f"{300_000:016x}"


def test_random_file_matches_reference(tmp_path):
    data = os.urandom(512 * 1024 + 13)
    path = tmp_path / "random.bin"
    path.write_bytes(data)
    expected = reference_hash(data)
    assert hash_file(path) == expected
    assert hash_from_chunks(len(data), data[:CHUNK], data[-CHUNK:]) == expected
