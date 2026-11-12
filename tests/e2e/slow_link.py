"""Browser test: a viewer whose link is slower than the film. A 1080p film of about 5 Mbps
(noise, so it does not compress) plays for a host and a viewer whose page is throttled with
the browser's own network emulation (CDP `Network.emulateNetworkConditions`).

- A: the viewer has 3000 kbps, about 65 % of the film (default `wait` mode). For 120 s the room's stops are counted
  (each time `waiting` goes from empty to someone). It used to stop 9 times in 147 s.
- B: the viewer has 1200 kbps, a third viewer a normal link, with the optional 60 s rule on (`BUFFER_WAIT=skip`). The server lets the room go on
  after 20 s of waiting; in the 60 s after that the slow viewer must not stop it again.
- Every half second each page's picture is drawn into a 32 x 18 canvas: while the room runs,
  no picture may be black.
- Connection panel: the slow viewer's chip on the host's page shows a measured speed below the
  film's (red), and after its third stall in five minutes the host gets one notice with a
  "lower the quality" button.

Takes about six minutes; the film is made once (about a minute) and kept in the temp folder.

    python tests/e2e/slow_link.py [--headed] [--case A|B]
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from two_viewers import DBG, KEY, RESULTS, check, free_port, start_server  # noqa: E402

FILM_S = 200
BLACK = 12  # mean brightness (0-255) under which a picture counts as black

BRIGHTNESS = """() => {
  const v = document.querySelector('#video');
  if (v.readyState < 2 || !v.videoWidth) return null;
  const c = window.__probe || (window.__probe = Object.assign(document.createElement('canvas'), {width: 32, height: 18}));
  const g = c.getContext('2d', {willReadFrequently: true});
  g.drawImage(v, 0, 0, 32, 18);
  const d = g.getImageData(0, 0, 32, 18).data;
  let sum = 0;
  for (let i = 0; i < d.length; i += 4) sum += (d[i] + d[i + 1] + d[i + 2]) / 3;
  return sum / (d.length / 4);
}"""

SAMPLE = f"""(probe) => {{
  const d = {DBG}, v = document.querySelector('#video');
  let ahead = 0;
  for (let i = 0; i < v.buffered.length; i++) {{
    if (v.buffered.start(i) <= v.currentTime + 0.1 && v.buffered.end(i) > v.currentTime) ahead = v.buffered.end(i) - v.currentTime;
  }}
  return {{room: d.room, filmTime: d.filmTime, resume: d.resumeAhead, readyState: d.readyState, ahead, bright: probe ? ({BRIGHTNESS})() : null}};
}}"""


# The host's notice (an action toast) and the chips' measured speeds.
HINT = """() => {
  const n = document.querySelector('.toast.with-actions');
  return n ? n.textContent + ' | ' + [...n.querySelectorAll('button')].map(b => b.textContent).join(', ') : null;
}"""
CHIP = """(id) => {
  const c = document.querySelector(`#members [data-id="${id}"]`);
  return c ? {title: c.title, slow: c.classList.contains('net-slow')} : null;
}"""


def check_panel(case: str, watch: "Watch", pages: dict, slow_id: str) -> None:
    chip = pages["host"].evaluate(CHIP, slow_id)
    print(f"{case}: the slow viewer's chip: {chip}; notices: {watch.hints}", flush=True)
    check(f"{case}: the host sees the slow viewer's measured speed below the film's",
          bool(chip) and "film" in chip["title"] and chip["slow"], str(chip))
    stalls = sum(1 for s in watch.stops if slow_id in s["who"])
    if stalls >= 3:
        check(f"{case}: after repeated stalls the host gets one notice with a button",
              len(watch.hints) == 1 and "Mbps" in watch.hints[0] and "Kaliteyi düşür" in watch.hints[0],
              f"{stalls} stalls; {watch.hints}")


def make_film() -> Path:
    """~5 Mbps 1080p H.264 with 4 s keyframes (the server copies it, 4 s segments). Kept between runs."""
    path = Path(tempfile.gettempdir()) / f"cowatch-e2e-slow-{FILM_S}s-v1.mkv"
    if path.exists() and path.stat().st_size > 50_000_000:
        return path
    print("making the film (about a minute)…", flush=True)
    part = path.with_suffix(".part.mkv")
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=24",
        "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000",
        "-t", str(FILM_S), "-vf", "noise=alls=25:allf=t",
        "-c:v", "libx264", "-preset", "ultrafast", "-b:v", "4500k", "-maxrate", "5600k", "-bufsize", "9000k",
        "-g", "96", "-keyint_min", "96", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", str(part),
    ], check=True)
    part.replace(path)
    return path


def throttle(page, kbps: int) -> None:
    cdp = page.context.new_cdp_session(page)
    cdp.send("Network.enable")
    cdp.send("Network.emulateNetworkConditions", {
        "offline": False, "latency": 40,
        "downloadThroughput": kbps * 1000 / 8, "uploadThroughput": 2000 * 1000 / 8,
    })


class Watch:
    """Samples every page each half second: the room's stops (as the host sees them), and how
    bright each page's picture is while the room runs."""

    def __init__(self, pages: dict):
        self.pages = pages
        self.start = time.monotonic()
        self.stops: list[dict] = []  # {at, end, who}
        self.black: list[str] = []
        self.samples = 0
        self.last: dict = {}
        self.hints: list[str] = []  # the host's notices about someone who keeps waiting

    def now(self) -> float:
        return time.monotonic() - self.start

    def tick(self) -> None:
        samples = {name: page.evaluate(SAMPLE, True) for name, page in self.pages.items()}
        self.last = samples
        self.samples += 1
        hint = self.pages["host"].evaluate(HINT)
        if hint and hint not in self.hints:
            self.hints.append(hint)
        room = samples["host"]["room"]
        waiting = room.get("waiting") or []
        t = self.now()
        open_stop = self.stops[-1] if self.stops and self.stops[-1]["end"] is None else None
        if waiting and open_stop is None and room.get("playing"):
            self.stops.append({"at": t, "end": None, "who": list(waiting)})
        elif not waiting and open_stop is not None:
            open_stop["end"] = t
        running = room.get("playing") and not room.get("loading") and not waiting
        if running:
            for name, s in samples.items():
                if s["bright"] is not None and s["bright"] < BLACK:
                    self.black.append(f"{name} at {t:.1f} s: {s['bright']:.1f} (film {s['filmTime']:.1f} s)")

    def run_for(self, seconds: float, until=None) -> None:
        end = self.now() + seconds
        while self.now() < end:
            began = time.monotonic()
            self.tick()
            if until and until():
                return
            time.sleep(max(0.0, 0.5 - (time.monotonic() - began)))

    def stops_between(self, a: float, b: float) -> list[dict]:
        return [s for s in self.stops if a <= s["at"] < b]

    def describe(self) -> str:
        return ", ".join(f"{s['at']:.0f}s+{((s['end'] or self.now()) - s['at']):.0f}" for s in self.stops)


def open_room(browser, base: str, film: Path, viewers: list[tuple[str, int | None]], errors: list[str]) -> dict:
    pages = {}
    for role, kbps in viewers:
        ctx = browser.new_context(viewport={"width": 960, "height": 700}, locale="tr-TR")
        page = ctx.new_page()
        page.on("pageerror", lambda exc, n=role: errors.append(f"{n} pageerror: {exc}"))
        page.on("console", lambda msg, n=role: errors.append(f"{n} console: {msg.text}")
                if msg.type == "error" and "favicon" not in msg.text else None)
        if kbps:
            throttle(page, kbps)
        page.goto(f"{base}/?k={KEY}")
        page.fill("#nameInput", role.capitalize())
        page.click("#joinForm button[type=submit]")
        pages[role] = page
    host = pages["host"]
    host.wait_for_function(f"() => {DBG}.members.length === {len(viewers)} && {DBG}.members.every(m => m.color)")
    host.wait_for_selector("#pathForm:not([hidden])")
    host.fill("#pathInput", str(film))
    host.press("#pathInput", "Enter")
    host.wait_for_function("() => document.querySelector('#video').readyState >= 2", timeout=60000)
    for page in pages.values():
        page.wait_for_function(f"() => {DBG}.media && {DBG}.media.streamId", timeout=30000)
    host.evaluate("() => window.scrollTo(0, 0)")
    host.wait_for_function("() => !document.querySelector('#stage').classList.contains('mini')")
    host.click("#playBtn", force=True)
    host.wait_for_function(f"() => {DBG}.room.playing", timeout=10000)
    return pages


def case_a(browser, base: str, film: Path, errors: list[str]) -> None:
    pages = open_room(browser, base, film, [("host", None), ("slow", 3000)], errors)
    slow_id = pages["slow"].evaluate(f"() => {DBG}.clientId")
    watch = Watch(pages)
    watch.run_for(120)
    played = watch.last["host"]["filmTime"]
    stops = len(watch.stops)
    print(f"A: {stops} stops in 120 s, {played:.0f} s of film played; stops (start+length): {watch.describe()}; "
          f"the slow viewer now gathers {watch.last['slow'].get('resume')} s", flush=True)
    check("A: a viewer at 3000 kbps (~65 % of the film) stops the room at most 5 times in 120 s",
          stops <= 5, f"{stops} stops, {played:.0f} s of film")
    check("A: the film still moves on", played > 40, f"{played:.0f} s")
    check("A: no black picture while the room runs", not watch.black and watch.samples > 200,
          "; ".join(watch.black[:5]) or f"{watch.samples} samples")
    check_panel("A", watch, pages, slow_id)
    for page in pages.values():
        page.context.close()


def case_b(browser, base: str, film: Path, errors: list[str]) -> None:
    pages = open_room(browser, base, film, [("host", None), ("slow", 1200), ("third", 8000)], errors)
    slow_id = pages["slow"].evaluate(f"() => {DBG}.clientId")
    watch = Watch(pages)

    def released() -> bool:  # a stop by the slow viewer that the server ended after its 20 s
        return any(s["end"] is not None and s["end"] - s["at"] >= 18 and slow_id in s["who"] for s in watch.stops)

    watch.run_for(150, until=released)
    if not released():
        check("B: the server lets the room go on after 20 s of waiting", False, watch.describe())
        return
    release = next(s for s in watch.stops if s["end"] is not None and s["end"] - s["at"] >= 18)["end"]
    watch.run_for(58)
    again = watch.stops_between(release, release + 58)
    print(f"B: released at {release:.0f} s; stops in the 58 s after: {len(again)}; all stops: {watch.describe()}", flush=True)
    check("B: after the server let the room go on, the slow viewer does not stop it again within 60 s",
          not again, watch.describe())
    behind = watch.last["host"]["filmTime"] - watch.last["slow"]["filmTime"]
    check("B: the others played on", watch.last["host"]["filmTime"] - watch.last["third"]["filmTime"] < 2
          and watch.last["host"]["room"]["playing"], f"slow is {behind:.0f} s behind")
    check("B: no black picture while the room runs", not watch.black, "; ".join(watch.black[:5]))
    check_panel("B", watch, pages, slow_id)
    for page in pages.values():
        page.context.close()


def run(headed: bool, cases: str) -> None:
    film = make_film()
    tmp = Path(tempfile.mkdtemp(prefix="cowatch-e2e-slow-"))
    errors: list[str] = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=not headed, args=["--autoplay-policy=no-user-gesture-required"])
            for name, case in (("A", case_a), ("B", case_b)):
                if name not in cases:
                    continue
                port = free_port()  # a fresh server, so a fresh room, for each case
                extra = {"HELPER_PORT": str(free_port())}
                if name == "B":
                    extra["BUFFER_WAIT"] = "skip"
                server = start_server(port, tmp / f"data-{name}", extra)
                try:
                    case(browser, f"http://127.0.0.1:{port}", film, errors)
                finally:
                    server.terminate()
                    server.wait(timeout=10)
            check("no errors in the browser console", not errors, "\n".join(errors[:5]))
            browser.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--case", default="AB", help="A, B or AB (default)")
    args = parser.parse_args()
    if not shutil.which("ffmpeg"):
        print("ffmpeg is not on PATH")
        return 2
    run(args.headed, args.case.upper())
    passed = sum(RESULTS)
    print(f"\n{passed}/{len(RESULTS)} passed")
    return 0 if RESULTS and passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
