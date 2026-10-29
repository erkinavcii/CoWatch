"""The host's film folders (LIBRARY_DIRS). The host and the friends the host trusted (co-hosts)
see the videos in them and open one for everyone. A co-host never sends a path of their own:
only a folder number and a path inside that folder, checked to stay inside it."""

from __future__ import annotations

import os
from pathlib import Path

VIDEO_EXTS = frozenset({
    ".mkv", ".mp4", ".m4v", ".avi", ".mov", ".webm", ".ts", ".m2ts", ".wmv", ".flv", ".mpg", ".mpeg",
})
MAX_FILES = 5000
MAX_DEPTH = 6


class LibraryError(Exception):
    pass


def is_video(name: str) -> bool:
    return os.path.splitext(name)[1].lower() in VIDEO_EXTS


def scan(dirs: tuple[Path, ...]) -> list[dict]:
    """Every video in the folders, sorted by folder and path. Hidden folders are skipped."""
    files: list[dict] = []
    for index, root in enumerate(dirs):
        if not root.is_dir():
            continue
        base_depth = len(root.parts)
        for here, subdirs, names in os.walk(root):
            depth = len(Path(here).parts) - base_depth
            subdirs[:] = sorted(d for d in subdirs if not d.startswith(".") and depth < MAX_DEPTH)
            for name in sorted(names):
                if not is_video(name):
                    continue
                path = Path(here) / name
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                files.append({"dir": index, "path": path.relative_to(root).as_posix(), "name": name, "size": size})
                if len(files) >= MAX_FILES:
                    return files
    return files


def resolve(dirs: tuple[Path, ...], index: int, rel: str) -> Path:
    """The file behind a (folder, path) pair from `scan`; LibraryError for anything outside
    the folder (`..`, an absolute path, a link pointing elsewhere) or not a video."""
    if not 0 <= index < len(dirs):
        raise LibraryError("unknown folder")
    root = dirs[index].resolve()
    path = (root / rel).resolve()
    if not path.is_relative_to(root) or path == root or not is_video(path.name) or not path.is_file():
        raise LibraryError("not in the film folder")
    return path
