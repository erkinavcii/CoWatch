"""Subtitle-to-subtitle alignment (server/align.py) on made-up films: a reference that fits the
film, and a target from "another release" whose true times are known."""

from __future__ import annotations

import random
import statistics
import time

import pytest

from server import align

CUT_AT, CUT_LEN = 2700.0, 60.0


def film(seed: int, minutes: float = 90) -> list[align.Cue]:
    """Dialogue: lines of 0.8–4.5 s with pauses between them, about half the time spoken."""
    rng = random.Random(seed)
    t, cues = 4.0, []
    while t < minutes * 60:
        t += rng.expovariate(1 / 2.5) + 0.2
        d = rng.uniform(0.8, 4.5)
        cues.append((round(t, 3), round(t + d, 3), f"line {len(cues)}"))
        t += d
    return cues


def release(ref, to_target, seed=0, noise=False, cut=False):
    """The target: each reference line moved by to_target (true time -> the target's time),
    with the true start kept for checking. Noise: lines lost and added, split and merged in
    other places (another language), and times a little off."""
    rng = random.Random(seed)
    pairs = []  # (target cue, true start or None)
    for s, e, text in ref:
        if cut and CUT_AT <= s < CUT_AT + CUT_LEN:
            continue
        if cut and s >= CUT_AT + CUT_LEN:
            s, e = s - CUT_LEN, e - CUT_LEN
            true = s + CUT_LEN
        else:
            true = s
        if noise:
            if rng.random() < 0.08:
                continue
            js, je = rng.gauss(0, 0.06), rng.uniform(-0.3, 0.5)
            if rng.random() < 0.1 and e - s > 2:
                m = (s + e) / 2
                pairs.append(((to_target(s + js), to_target(m - 0.1), text), true))
                pairs.append(((to_target(m + 0.05), to_target(e + je), text), true + (m + 0.05 - s)))
                continue
            s, e = s + js, max(s + js + 0.3, e + je)
        pairs.append(((to_target(s), to_target(e), text), true))
    if noise:
        merged = []
        for pair in pairs:
            if merged and rng.random() < 0.1 and pair[0][0] - merged[-1][0][1] < 1.0:
                (ps, _, pt), ptrue = merged[-1]
                merged[-1] = ((ps, pair[0][1], pt + "\n" + pair[0][2]), ptrue)
            else:
                merged.append(pair)
        pairs = merged
        end = max(c[1] for c, _ in pairs)
        for _ in range(len(pairs) // 20):
            s = rng.uniform(0, end)
            pairs.append(((s, s + rng.uniform(0.8, 3), "extra"), None))
        pairs.sort(key=lambda p: p[0][0])
    return [c for c, _ in pairs], pairs


def residuals(result: align.Alignment, pairs) -> list[float]:
    """How far each aligned line starts from where it should (seconds)."""
    out = []
    for cue, true in pairs:
        if true is None:
            continue
        seg = result.segment_for(cue[0])
        out.append(abs(seg.map(cue[0]) - true))
    return out


CASES = {
    # name: (how the target's times relate to the film, noise, a scene cut out)
    "shift": (lambda t: t + 3.2, False, False),
    "stretch": (lambda t: t * 23.976 / 25, False, False),  # a 25 fps release of a 23.976 film
    "stretch_shift": (lambda t: t * 25 / 23.976 - 7.4, False, False),
    "cut_scene": (lambda t: t + 1.5, False, True),
    "noisy_shift": (lambda t: t - 41.7, True, False),
    "noisy_stretch_shift": (lambda t: t * 24 / 25 + 12.3, True, False),
    "noisy_cut_scene": (lambda t: t * 23.976 / 25 - 2.0, True, True),
}


@pytest.mark.parametrize("name", list(CASES))
def test_aligns_another_release(name):
    to_target, noise, cut = CASES[name]
    ref = film(7)
    target, pairs = release(ref, to_target, seed=3, noise=noise, cut=cut)
    started = time.monotonic()
    result = align.align(ref, target)
    took = time.monotonic() - started
    res = residuals(result, pairs)
    median = statistics.median(res)
    print(f"{name}: median {median * 1000:.0f} ms, p90 {sorted(res)[int(len(res) * 0.9)] * 1000:.0f} ms, "
          f"{result.summary()}, {took:.2f} s")
    assert median < 0.1
    assert result.score >= align.MIN_SCORE
    assert len(result.segments) == (2 if cut else 1)
    assert took < 20


def test_plain_shift_stays_a_plain_shift():
    ref = film(11, minutes=40)
    target, _ = release(ref, lambda t: t + 3.2)
    result = align.align(ref, target)
    assert result.scale == 1.0 and abs(result.offset + 3.2) < 0.02
    assert result.summary()["fps"] is None and result.summary()["segments"] == 1


def test_frame_rate_change_is_named():
    ref = film(12, minutes=40)
    target, _ = release(ref, lambda t: t * 23.976 / 25)
    result = align.align(ref, target)
    assert result.summary()["fps"] == [25.0, 23.976]


def test_apply_moves_the_lines_and_keeps_the_text():
    ref = film(5, minutes=30)
    target, _ = release(ref, lambda t: t + 3.2)
    result = align.align(ref, target)
    moved = result.apply(target)
    assert [c[2] for c in moved] == [c[2] for c in target]
    assert all(abs(m[0] - r[0]) < 0.02 for m, r in zip(moved, ref))


def test_unrelated_subtitles_are_not_trusted():
    for a, b in ((1, 2), (3, 4), (5, 6)):
        result = align.align(film(a), film(b))
        print(f"unrelated {a}/{b}: score {result.score:.3f}, overlap {result.overlap:.3f}")
        assert result.score < align.MIN_SCORE


def test_one_line_subtitle():
    ref = [(0.5, 7.5, "Good, we leave now.")]
    result = align.align(ref, [(2.8, 9.8, "Good, we leave now.")])
    assert result.scale == 1.0 and abs(result.offset + 2.3) < 0.02
    assert result.apply([(2.8, 9.8, "x")])[0][0] == pytest.approx(0.5, abs=0.02)


def test_empty_subtitle():
    with pytest.raises(align.AlignError):
        align.align([(1.0, 2.0, "a")], [])


def test_huge_end_timestamp_is_clamped():
    spans = align.intervals([
        (-5.0, 2.0, "starts negative"),
        (1.0, 359999.0, "99:59:59 broken cue"),
        (align.MAX_SPAN_S + 100.0, 359999.0, "beyond limit"),
    ])
    assert spans == [(0.0, align.MAX_SPAN_S)]
    bits = align._bits([(0.0, 1e9)], align.FINE_S)
    assert bits.bit_length() <= round(align.MAX_SPAN_S * 1.1 / align.FINE_S) + 1
    ref = film(11, minutes=40)
    target, _ = release(ref, lambda t: t + 2.5)
    target.append((500.0, 359999.0, "corrupt end"))
    result = align.align(ref, target)
    assert result.score >= align.MIN_SCORE and abs(result.offset + 2.5) < 0.05
