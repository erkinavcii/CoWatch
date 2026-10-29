import pytest

from server.library import LibraryError, resolve, scan


def make_folder(root):
    (root / "Sub").mkdir()
    (root / ".hidden").mkdir()
    (root / "a.mp4").write_bytes(b"1234")
    (root / "Sub" / "b.MKV").write_bytes(b"x")
    (root / "notes.txt").write_text("no")
    (root / ".hidden" / "c.mkv").write_bytes(b"x")


def test_scan_lists_videos_with_paths_inside_their_folder(tmp_path):
    films, other = tmp_path / "Films", tmp_path / "Other"
    films.mkdir()
    other.mkdir()
    make_folder(films)
    (other / "d.avi").write_bytes(b"x")
    files = scan((films, other, tmp_path / "missing"))
    assert [(f["dir"], f["path"]) for f in files] == [(0, "a.mp4"), (0, "Sub/b.MKV"), (1, "d.avi")]
    assert files[0]["size"] == 4 and files[1]["name"] == "b.MKV"


def test_resolve_stays_inside_the_folder(tmp_path):
    films = tmp_path / "Films"
    films.mkdir()
    make_folder(films)
    (tmp_path / "outside.mkv").write_bytes(b"x")
    dirs = (films,)
    assert resolve(dirs, 0, "Sub/b.MKV") == (films / "Sub" / "b.MKV").resolve()
    for index, rel in [(1, "a.mp4"), (-1, "a.mp4"), (0, "../outside.mkv"), (0, str(tmp_path / "outside.mkv")),
                       (0, "notes.txt"), (0, ""), (0, "."), (0, "missing.mkv")]:
        with pytest.raises(LibraryError):
            resolve(dirs, index, rel)
