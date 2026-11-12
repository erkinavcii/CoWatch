"""Subtitle-to-subtitle alignment, in pure Python (no numpy, no alass).

A subtitle from another release is shifted against the film, often stretched too (25 fps
against 23.976), sometimes with a scene cut out. A subtitle known to fit the file (the file's
own, one matched by the file's hash) shows when people speak; when lines start and stop does
not depend on the language, so a Russian subtitle can be fitted onto a Turkish one.

The method:

1. Both subtitles become speech intervals (cues merged where they touch), then a bit string on
   a time grid: bit i is set when someone speaks in [i·step, (i+1)·step). Python's big integers
   do the cross-correlation: the overlap at a lag of k steps is `(ref & (target << k)).bit_count()`,
   a few microseconds for a two-hour film on a 100 ms grid (72 000 bits).
2. For each known frame-rate ratio a (1, 25/23.976 and the others in `RATIOS`) the target's times
   are multiplied by a and every lag within ±`MAX_SHIFT_S` is tried on the 100 ms grid. The best
   ratio is then searched finely (±0.2 %, steps of 0.01 %, around the cues' middle so the offset
   stays put); a finer scale or another ratio must beat 1 (or the ratio) clearly, so a plain shift
   stays a plain shift.
3. The offset is refined on a 10 ms grid around the coarse peak.
4. A split: a release with a scene cut out (or added) needs two offsets. For 49 split points
   between the target's cues, every lag's overlap is cut at the split point, which gives the best
   left and right offsets for all split points in one pass over the lags. A split is only kept when
   it clearly beats the single offset (`SPLIT_GAIN`) and each part has enough cues; the split point
   is then moved cue by cue to the best place, and each part gets its 10 ms refinement.

The result: segments (target time where each begins, scale, offset; t' = a·t + b), a confidence
and the raw overlap. The raw overlap is the share of the shorter speech that overlaps; two
unrelated subtitles that speak 40 % of the time overlap about 40 % by chance, so the confidence
is the overlap above chance: (overlap − chance) / (1 − chance). Below `MIN_SCORE` the result is
not trusted (`align_unsure`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Optional

Cue = tuple[float, float, str]

COARSE_S = 0.1
FINE_S = 0.01
MAX_SHIFT_S = 120.0
MAX_SPAN_S = 6 * 3600.0  # a cue beyond this (a broken file) is left out of the search
RATIOS = (1.0, 25 / 23.976, 23.976 / 25, 24 / 25, 25 / 24, 23.976 / 24, 24 / 23.976)
SCALE_FINE = 0.002  # ±0.2 % around the best ratio
SCALE_STEP = 0.0001
SCALE_GAIN = 1.005  # another scale must beat the plain one by 0.5 %
SPLIT_POINTS = 49
SPLIT_GAIN = 1.05  # a split must give 5 % more overlap than one offset
SPLIT_MIN_CUES = 20
SPLIT_MIN_SHARE = 0.1
MIN_SCORE = 0.35


class AlignError(Exception):
    def __init__(self, message: str, code: str = "align_failed"):
        super().__init__(message)
        self.code = code


@dataclass
class Segment:
    start: float  # the target's own time where this part begins (the first: -inf)
    scale: float
    offset: float

    def map(self, t: float) -> float:
        return self.scale * t + self.offset


@dataclass
class Alignment:
    segments: list[Segment]
    score: float  # the confidence: overlap above chance, 0..1
    overlap: float  # the share of the shorter speech that overlaps, 0..1

    @property
    def scale(self) -> float:
        return self.segments[0].scale

    @property
    def offset(self) -> float:
        return self.segments[0].offset

    def segment_for(self, t: float) -> Segment:
        seg = self.segments[0]
        for s in self.segments[1:]:
            if t >= s.start:
                seg = s
        return seg

    def apply(self, cues: Iterable[Cue]) -> list[Cue]:
        out: list[Cue] = []
        for start, end, text in cues:
            seg = self.segment_for(start)
            s, e = seg.map(start), seg.map(end)
            if e <= 0:
                continue
            out.append((round(max(0.0, s), 3), round(e, 3), text))
        out.sort(key=lambda c: (c[0], c[1]))
        return out

    def summary(self) -> dict:
        return {
            "shift": round(self.offset, 3),
            "scale": round(self.scale, 6),
            "fps": frame_rates(self.scale),
            "segments": len(self.segments),
            "parts": [{"from": None if math.isinf(s.start) else round(s.start, 3),
                       "scale": round(s.scale, 6), "shift": round(s.offset, 3)} for s in self.segments],
            "score": round(self.score, 3),
            "overlap": round(self.overlap, 3),
        }


def frame_rates(scale: float) -> Optional[list[float]]:
    """[25, 23.976] when the scale is (about) a known frame-rate change (a subtitle timed for 25 fps
    put onto a 23.976 fps film); None for 1 and for any other scale."""
    rates = (23.976, 24.0, 25.0)
    for a in rates:
        for b in rates:
            if a != b and abs(scale / (a / b) - 1) < 0.0002:
                return [a, b]
    return None


# ---- speech as bits ---------------------------------------------------------------------------
def intervals(cues: Iterable[Cue]) -> list[tuple[float, float]]:
    """Speech intervals: the cues' times, sorted and merged where they overlap or touch."""
    spans = sorted((float(s), float(e)) for s, e, *_ in cues if e > s and s < MAX_SPAN_S)
    merged: list[list[float]] = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def _bits(spans: Iterable[tuple[float, float]], step: float) -> int:
    spans = [(max(0, round(s / step)), max(0, round(e / step))) for s, e in spans]
    if not spans:
        return 0
    size = max(e for _, e in spans) + 1
    row = bytearray(b"0") * size
    for i, j in spans:
        if j > i:
            row[i:j] = b"1" * (j - i)
    row.reverse()  # int() reads the most significant digit first; bit i = position i
    return int(row, 2)


def _scaled(spans: list[tuple[float, float]], scale: float) -> list[tuple[float, float]]:
    return [(s * scale, e * scale) for s, e in spans]


def _overlap(ref: int, target: int, lag: int) -> int:
    return (ref & (target << lag)).bit_count() if lag >= 0 else ((ref << -lag) & target).bit_count()


def _best_lag(ref: int, target: int, lo: int, hi: int) -> tuple[int, int]:
    """(overlap, lag) of the best lag in lo..hi; the lag nearest the middle wins a tie."""
    mid = (lo + hi) / 2
    best = (-1, 0)
    for lag in range(lo, hi + 1):
        value = _overlap(ref, target, lag)
        if value > best[0] or (value == best[0] and abs(lag - mid) < abs(best[1] - mid)):
            best = (value, lag)
    return best


# ---- the search -------------------------------------------------------------------------------
def _fit(ref_c: int, ref_f: int, spans: list[tuple[float, float]], scale: float,
         around: Optional[float] = None, window: float = MAX_SHIFT_S) -> tuple[int, float]:
    """Best offset for these target spans at this scale: (coarse overlap, offset in seconds)."""
    t_c = _bits(_scaled(spans, scale), COARSE_S)
    centre = 0 if around is None else round(around / COARSE_S)
    reach = round(window / COARSE_S)
    count, lag = _best_lag(ref_c, t_c, centre - reach, centre + reach)
    return count, _refine(ref_f, spans, scale, lag * COARSE_S)


def _refine(ref_f: int, spans: list[tuple[float, float]], scale: float, offset: float) -> float:
    t_f = _bits(_scaled(spans, scale), FINE_S)
    centre = round(offset / FINE_S)
    reach = round(1.5 * COARSE_S / FINE_S)
    _, lag = _best_lag(ref_f, t_f, centre - reach, centre + reach)
    return lag * FINE_S


def _coarse_scale(ref_c: int, spans: list[tuple[float, float]]) -> tuple[float, int, int]:
    """(scale, coarse overlap, coarse lag) over the known ratios, then a fine scale search."""
    reach = round(MAX_SHIFT_S / COARSE_S)
    results = []
    for ratio in RATIOS:
        count, lag = _best_lag(ref_c, _bits(_scaled(spans, ratio), COARSE_S), -reach, reach)
        results.append((count, ratio, lag))
    plain = results[0]
    best = max(results, key=lambda r: r[0])
    if best[0] < plain[0] * SCALE_GAIN:
        best = plain
    count0, scale0, lag0 = best
    # Around the cues' middle a small change of scale hardly moves the offset there.
    middle = sum((s + e) / 2 for s, e in spans) / len(spans)
    fine = (count0, scale0, lag0)
    steps = round(SCALE_FINE / SCALE_STEP)
    for i in range(-steps, steps + 1):
        if i == 0:
            continue
        scale = scale0 * (1 + i * SCALE_STEP)
        guess = lag0 + round((scale0 - scale) * middle / COARSE_S)
        count, lag = _best_lag(ref_c, _bits(_scaled(spans, scale), COARSE_S), guess - 20, guess + 20)
        if count > fine[0]:
            fine = (count, scale, lag)
    if fine[0] >= count0 * SCALE_GAIN:
        return fine[1], fine[0], fine[2]
    return scale0, count0, lag0


def _split(ref_c: int, spans: list[tuple[float, float]], scale: float,
           whole: int) -> Optional[tuple[float, int, int]]:
    """The best split of the target into two offsets: (target time of the split, left lag,
    right lag), or None when one offset is as good."""
    if len(spans) < 2 * SPLIT_MIN_CUES:
        return None
    scaled = _scaled(spans, scale)
    t_c = _bits(scaled, COARSE_S)
    lo_i = max(SPLIT_MIN_CUES, math.ceil(len(spans) * SPLIT_MIN_SHARE))
    hi_i = len(spans) - lo_i
    if hi_i <= lo_i:
        return None
    picks = sorted({lo_i + round(j * (hi_i - lo_i) / (SPLIT_POINTS - 1)) for j in range(SPLIT_POINTS)})
    # The split point between cue i-1 and cue i, on the grid of the scaled target.
    cuts = [round((scaled[i - 1][1] + scaled[i][0]) / 2 / COARSE_S) for i in picks]
    reach = round(MAX_SHIFT_S / COARSE_S)
    left = [(-1, 0)] * len(cuts)
    right = [(-1, 0)] * len(cuts)
    for lag in range(-reach, reach + 1):
        both = (ref_c & (t_c << lag)) if lag >= 0 else ((ref_c << -lag) & t_c)
        total = both.bit_count()
        shift = max(lag, 0)  # the target's position p sits at p + lag when the target was shifted
        for j, cut in enumerate(cuts):
            r = (both >> (cut + shift)).bit_count()
            if r > right[j][0]:
                right[j] = (r, lag)
            if total - r > left[j][0]:
                left[j] = (total - r, lag)
    j = max(range(len(cuts)), key=lambda j: left[j][0] + right[j][0])
    gain = left[j][0] + right[j][0]
    l_lag, r_lag = left[j][1], right[j][1]
    if gain < whole * SPLIT_GAIN or abs(l_lag - r_lag) * COARSE_S < 1.0:
        return None
    # Move the split cue by cue between the neighbouring split points, the two offsets fixed.
    first = picks[max(0, j - 1)]
    last = picks[min(len(picks) - 1, j + 1)]
    best_i, best_v = picks[j], -1
    for i in range(first, last + 1):
        v = (_overlap(ref_c, _bits(scaled[:i], COARSE_S), l_lag)
             + _overlap(ref_c, _bits(scaled[i:], COARSE_S), r_lag))
        if v > best_v:
            best_i, best_v = i, v
    split_at = (spans[best_i - 1][1] + spans[best_i][0]) / 2
    return split_at, l_lag, r_lag


def _confidence(ref: list[tuple[float, float]], moved: list[tuple[float, float]]) -> tuple[float, float]:
    """(confidence above chance, raw overlap share of the shorter speech), on the fine grid."""
    r, t = _bits(ref, FINE_S), _bits(moved, FINE_S)
    nr, nt = r.bit_count(), t.bit_count()
    if not nr or not nt:
        return 0.0, 0.0
    both = (r & t).bit_count()
    lo = min(min(s for s, _ in ref), min(s for s, _ in moved))
    hi = max(max(e for _, e in ref), max(e for _, e in moved))
    length = max(1.0, (hi - lo) / FINE_S)
    shorter = min(nr, nt)
    overlap = both / shorter
    chance = min(0.99, nr * nt / length / shorter)
    return max(0.0, min(1.0, (overlap - chance) / (1 - chance))), overlap


def align(reference: list[Cue], target: list[Cue]) -> Alignment:
    """The transform that puts `target`'s cues onto `reference`'s (see the module's notes)."""
    ref = intervals(reference)
    spans = intervals(target)
    if not ref or not spans:
        raise AlignError("a subtitle has no lines", "align_empty")
    ref_c, ref_f = _bits(ref, COARSE_S), _bits(ref, FINE_S)
    scale, whole, lag = _coarse_scale(ref_c, spans)
    segments = [Segment(-math.inf, scale, _refine(ref_f, spans, scale, lag * COARSE_S))]
    split = _split(ref_c, spans, scale, whole)
    if split is not None:
        at, l_lag, r_lag = split
        left = [s for s in spans if s[0] < at]
        right = [s for s in spans if s[0] >= at]
        segments = [Segment(-math.inf, scale, _refine(ref_f, left, scale, l_lag * COARSE_S)),
                    Segment(at, scale, _refine(ref_f, right, scale, r_lag * COARSE_S))]
    result = Alignment(segments, 0.0, 0.0)
    moved = intervals((result.segment_for(s).map(s), result.segment_for(s).map(e), "") for s, e in spans)
    result.score, result.overlap = _confidence(ref, moved)
    return result
