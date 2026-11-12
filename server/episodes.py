"""The next episode: which file comes after the one playing, among the videos of the same
torrent or folder. Episode numbers come from the file name (S01E04, 1x05, "Episode 2", E02,
an anime's "- 07"); a file without one is ordered by name, numbers counted as numbers."""

from __future__ import annotations

import re
from typing import Optional

# Season and episode in the name.
_SEASON_EPISODE = (
    re.compile(r"(?<![a-z0-9])s(\d{1,2})[ ._-]?e(\d{1,3})(?!\d)", re.I),  # S01E04, s1e4, S01.E04
    re.compile(r"(?<![a-z0-9])(\d{1,2})x(?!26[45](?!\d))(\d{2,3})(?!\d)", re.I),  # 1x05 (not x264)
)
# Only the episode: the season from a folder ("Season 2", "Show.S02"), else 1.
_EPISODE_ONLY = (
    re.compile(r"(?<![a-z])(?:episode|ep)[ ._-]*(\d{1,3})(?!\d)", re.I),  # Episode 2, Ep.02
    re.compile(r"(?<![a-z0-9])e(\d{2,3})(?![a-z0-9])", re.I),  # E02
    re.compile(r"\s-\s(\d{1,3})(?:v\d)?(?=[\s.\[(]|$)"),  # [Group] Anime - 07 [1080p]
)
_SEASON = re.compile(r"(?<![a-z0-9])(?:season[ ._-]*|s)(\d{1,2})(?![0-9])", re.I)
_SAMPLE = re.compile(r"(?<![a-z])(sample|trailer)(?![a-z])", re.I)
# Where a release name stops being the episode's title.
_JUNK = re.compile(
    r"[\[(]|(?<![a-z0-9])(2160p|1080p|720p|576p|480p|4k|uhd|x26[45]|h[ .]?26[45]|hevc|avc|av1|xvid|web|webrip|"
    r"web[ -]?dl|bluray|blu[ -]?ray|brrip|bdrip|hdtv|dvdrip|hdrip|remux|proper|repack|10bit|8bit|hdr|dv|"
    r"aac|ac3|eac3|ddp?|dts|atmos|nf|amzn|dsnp|hmax|multi|dual)(?![a-z0-9])", re.I)
_EXT = re.compile(r"\.[a-z0-9]{2,4}$", re.I)


def _parts(path: str) -> list[str]:
    return [p for p in re.split(r"[\\/]", path) if p]


def _name(path: str) -> str:
    parts = _parts(path)
    return _EXT.sub("", parts[-1] if parts else path)


def _find(path: str) -> Optional[tuple[int, int, int]]:
    """(season, episode, where the marker ends in the name), or None."""
    name = _name(path)
    for pattern in _SEASON_EPISODE:
        match = pattern.search(name)
        if match:
            return int(match.group(1)), int(match.group(2)), match.end()
    clean = re.sub(r"\[[^\]]*\]|\([^)]*\)", lambda m: " " * len(m.group(0)), name)  # [Group], (1080p)
    for pattern in _EPISODE_ONLY:
        match = pattern.search(clean)
        if match:
            season = 1
            for folder in reversed(_parts(path)[:-1]):
                found = _SEASON.search(folder)
                if found:
                    season = int(found.group(1))
                    break
            return season, int(match.group(1)), match.end()
    return None


def episode(path: str) -> Optional[tuple[int, int]]:
    found = _find(path)
    return (found[0], found[1]) if found else None


def natural_key(path: str) -> list:
    """"Part 10" after "Part 9": digits compare as numbers."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", path.replace("\\", "/"))]


def is_sample(path: str) -> bool:
    return bool(_SAMPLE.search(path))


def label(path: str) -> str:
    """What the button says: "S01E05 World On Fire", or the file's name."""
    name = _name(path)
    found = _find(path)
    if not found:
        return re.sub(r"[._]+", " ", name).strip()[:80]
    season, number, end = found
    rest = re.sub(r"[._]+", " ", name[end:])
    junk = _JUNK.search(rest)
    if junk:
        rest = rest[:junk.start()]
    rest = re.sub(r"\s+", " ", rest).strip(" -–—:,")
    return f"S{season:02d}E{number:02d} {rest[:60]}".strip()


def pick_next(paths: list[str], current: str) -> Optional[str]:
    """The file after `current` among `paths` (relative paths or names, `current` among them).
    With an episode number: the smallest later (season, episode); without: the next by name.
    Samples and trailers are skipped (unless a sample is playing)."""
    if not is_sample(current):
        paths = [p for p in paths if not is_sample(p)]
    here = episode(current)
    if here is not None:
        later = [(ep, natural_key(p), p) for p in paths if p != current and (ep := episode(p)) and ep > here]
        return min(later)[2] if later else None
    order = sorted(set(paths) | {current}, key=natural_key)
    at = order.index(current)
    return order[at + 1] if at + 1 < len(order) else None
