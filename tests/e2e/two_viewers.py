"""Two viewers in two browser windows of different sizes, end to end: sync, per-viewer
subtitles, shared cursors, pokes and the pen.

Not part of `pytest`: it needs a browser and takes about a minute. One-time setup:

    .\\.venv\\Scripts\\python -m pip install playwright
    .\\.venv\\Scripts\\python -m playwright install chromium

Run from the project folder (ffmpeg must be on PATH; the script makes its own test video
and starts its own server on a free port):

    .\\.venv\\Scripts\\python tests\\e2e\\two_viewers.py            # headless
    .\\.venv\\Scripts\\python tests\\e2e\\two_viewers.py --headed   # watch the windows
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
KEY = "e2e-key"
DBG = "window.cowatchDebug()"
RESULTS: list[bool] = []

# Where the video picture sits inside the stage (object-fit: contain leaves bars), as in app.js.
PICTURE_RECT = """() => {
  const stage = document.querySelector('#stage').getBoundingClientRect();
  const v = document.querySelector('#video');
  let w = stage.width, h = stage.height;
  if (v.videoWidth && v.videoHeight) {
    const s = Math.min(w / v.videoWidth, h / v.videoHeight); w = v.videoWidth * s; h = v.videoHeight * s;
  }
  return {left: stage.left + (stage.width - w) / 2, top: stage.top + (stage.height - h) / 2, w, h,
          stageLeft: stage.left, stageTop: stage.top};
}"""

# Counts poke sounds: every chirp starts an oscillator.
COUNT_SOUNDS = """window.__sounds = 0;
const start = OscillatorNode.prototype.start;
OscillatorNode.prototype.start = function (...args) { window.__sounds += 1; return start.apply(this, args); };"""

# RGBA of the drawing canvas at a point given as a fraction of the picture.
CANVAS_PIXEL = """([x, y]) => {
  const c = document.querySelector('#drawCanvas');
  const stage = document.querySelector('#stage').getBoundingClientRect();
  const v = document.querySelector('#video');
  let w = stage.width, h = stage.height;
  if (v.videoWidth && v.videoHeight) {
    const s = Math.min(w / v.videoWidth, h / v.videoHeight); w = v.videoWidth * s; h = v.videoHeight * s;
  }
  const dpr = c.width / stage.width;
  const px = Math.round(((stage.width - w) / 2 + x * w) * dpr), py = Math.round(((stage.height - h) / 2 + y * h) * dpr);
  return Array.from(c.getContext('2d').getImageData(px, py, 1, 1).data);
}"""

BALL = r"""() => {
  const n = document.querySelector('.ball:not(.me):not(.gone)');
  const m = /translate3d\(([-\d.]+)px, ([-\d.]+)px/.exec(n.style.transform);
  return {x: Number(m[1]), y: Number(m[2]), name: n.querySelector('.tag').textContent, color: n.style.getPropertyValue('--c')};
}"""


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append(bool(ok))
    print(f"{'PASS' if ok else 'FAIL'} {name}" + (f" :: {detail}" if detail else ""), flush=True)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def make_video(path: Path) -> None:
    """30 s, 2.39:1, so the letterbox bars inside the 16:9 stage are part of the test."""
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=1280x536:rate=24",
        "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000",
        "-t", "30", "-c:v", "libx264", "-preset", "ultrafast", "-g", "48", "-pix_fmt", "yuv420p",
        "-c:a", "aac", str(path),
    ], check=True)


def start_server(port: int, data_dir: Path) -> subprocess.Popen:
    env = dict(os.environ, ACCESS_KEY=KEY, DATA_DIR=str(data_dir), COWATCH_DOTENV="", ADDONS_BUILTIN="0")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server.main:app", "--host", "127.0.0.1",
         "--port", str(port), "--log-level", "warning"],
        cwd=ROOT, env=env,
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/static/app.js", timeout=2):
                return proc
        except OSError:
            if proc.poll() is not None:
                raise RuntimeError("the server exited during startup") from None
            time.sleep(0.3)
    proc.terminate()
    raise RuntimeError("the server did not start within 30 s")


def blur(page) -> None:
    """Keyboard shortcuts are ignored while a form field has focus."""
    page.evaluate("() => document.activeElement && document.activeElement.blur()")


def film_time(page) -> float:
    return page.evaluate(f"() => {DBG}.filmTime")


def run(headed: bool) -> None:
    tmp = Path(tempfile.mkdtemp(prefix="cowatch-e2e-"))
    video = tmp / "wide.mkv"
    make_video(video)
    port = free_port()
    server = start_server(port, tmp / "data")
    base = f"http://127.0.0.1:{port}"
    errors: list[str] = []

    def on_console(msg, name):
        if msg.type == "error" and "favicon" not in msg.text:
            errors.append(f"{name} console: {msg.text}")

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=not headed, args=["--autoplay-policy=no-user-gesture-required"])
            pages = {}
            for name, (width, height) in (("Erkin", (1280, 860)), ("Masha", (900, 760))):
                ctx = browser.new_context(viewport={"width": width, "height": height}, locale="tr-TR")
                ctx.add_init_script(COUNT_SOUNDS)
                page = ctx.new_page()
                page.on("pageerror", lambda exc, n=name: errors.append(f"{n} pageerror: {exc}"))
                page.on("console", lambda msg, n=name: on_console(msg, n))
                page.goto(f"{base}/?k={KEY}")
                page.fill("#nameInput", name)
                page.click("#joinForm button[type=submit]")
                pages[name] = page
            a, b = pages["Erkin"], pages["Masha"]

            a.wait_for_function(f"() => {DBG}.members.length === 2 && {DBG}.members.every(m => m.color)")
            color = {m["name"]: m["color"] for m in a.evaluate(f"() => {DBG}.members")}
            check("each viewer gets a colour of their own", color["Erkin"] != color["Masha"], str(color))

            # ---- open the film from the host window (127.0.0.1 counts as the host)
            a.wait_for_selector("#pathForm:not([hidden])")
            a.fill("#pathInput", str(video))
            a.press("#pathInput", "Enter")
            for page in (a, b):
                page.wait_for_function(
                    f"() => {{ const v = document.querySelector('#video'); return {DBG}.media && v.videoWidth > 0 && v.readyState >= 2; }}",
                    timeout=60000,
                )

            # ---- subtitles: Turkish from one window, Russian from the other; Masha adds Turkish as her second line
            for page, file, lang in ((a, "test.tr.srt", "tr"), (b, "test.ru.srt", "ru")):
                page.click(".add-subs summary")
                # Scrolled down to the subtitle card, the film follows in the corner box; on the
                # smaller window it covers the upload button, so close it as a viewer would.
                if page.is_visible("#miniClose"):
                    page.click("#miniClose")
                page.set_input_files("#subFile", str(ROOT / "samples" / file))
                page.fill("#subLang", lang)
                page.click("#uploadForm button")
                page.wait_for_function(f"() => {DBG}.primary")
            tracks = a.evaluate("() => fetch('/api/subtitles').then(r => r.json())")["tracks"]
            b.select_option("#secondarySel", next(t["id"] for t in tracks if t["lang"] == "tr"))

            # ---- sync: play in one window, pause in the other
            # The host's page is longer (share card): after the subtitle cards it is scrolled far
            # enough that the button would end up under the sticky header.
            a.evaluate("() => window.scrollTo(0, 0)")
            a.wait_for_function("() => !document.querySelector('#stage').classList.contains('mini')")  # back in place
            a.click("#playBtn", force=True)
            time.sleep(4)
            ta, tb = film_time(a), film_time(b)
            check("both windows play the same moment", ta > 2 and abs(ta - tb) < 0.3, f"{ta:.2f} s vs {tb:.2f} s")
            blur(b)
            b.keyboard.press("Space")
            a.wait_for_function(f"() => !{DBG}.room.playing")
            time.sleep(0.8)
            ta, tb = film_time(a), film_time(b)
            check("pausing in one window pauses both", abs(ta - tb) < 0.3, f"{ta:.2f} s vs {tb:.2f} s")

            # ---- seek both to 7 s and read the subtitles each window shows
            b.evaluate("() => { const s = document.querySelector('#seekBar'); s.value = '7'; s.dispatchEvent(new Event('change')); }")
            for page in (a, b):
                page.wait_for_function(f"() => Math.abs({DBG}.filmTime - 7) < 0.3", timeout=20000)
            time.sleep(0.5)
            a_main, b_main, b_second = a.inner_text("#subPrimary"), b.inner_text("#subPrimary"), b.inner_text("#subSecondary")
            check("each window shows its own subtitles",
                  "5. saniye" in a_main and "5-я секунда" in b_main and "5. saniye" in b_second,
                  f"A {a_main!r} | B {b_main!r} / {b_second!r}")

            # ---- cursor: A points at 25% / 75% of the picture; B's ball for A lands on the same spot of B's picture
            for page in (a, b):  # the subtitle forms scrolled the page; the whole picture must be on screen
                page.evaluate("() => window.scrollTo(0, 0)")
            time.sleep(0.2)
            ra = a.evaluate(PICTURE_RECT)
            ax, ay = ra["left"] + 0.25 * ra["w"], ra["top"] + 0.75 * ra["h"]
            a.mouse.move(ax - 60, ay - 40)
            a.mouse.move(ax, ay, steps=8)
            b.wait_for_function("() => document.querySelector('.ball:not(.me):not(.gone)')", timeout=5000)
            time.sleep(0.6)
            ball, rb = b.evaluate(BALL), b.evaluate(PICTURE_RECT)
            ex, ey = rb["left"] - rb["stageLeft"] + 0.25 * rb["w"], rb["top"] - rb["stageTop"] + 0.75 * rb["h"]
            check("a pointer lands on the same spot of the picture on another screen size",
                  abs(ball["x"] - ex) < 2 and abs(ball["y"] - ey) < 2,
                  f"got {ball['x']:.1f},{ball['y']:.1f} want {ex:.1f},{ey:.1f}")
            check("the ball carries the name and colour", ball["name"] == "Erkin" and ball["color"] == color["Erkin"],
                  f"{ball['name']} {ball['color']}")

            # ---- poke: blink, ring and sound for both; the same click plays or pauses for everyone
            sounds = (a.evaluate("() => window.__sounds"), b.evaluate("() => window.__sounds"))
            playing = a.evaluate(f"() => {DBG}.room.playing")
            a.mouse.down()
            a.mouse.up()
            try:
                b.wait_for_function("() => document.querySelector('.ball:not(.me).blink') && document.querySelector('.ripple')", timeout=3000)
                blinked = True
            except PlaywrightTimeout:
                blinked = False
            check("a click blinks the ball and sends a ring to the other window", blinked)
            time.sleep(0.4)
            after = (a.evaluate("() => window.__sounds"), b.evaluate("() => window.__sounds"))
            check("a click plays the poke sound in both windows", after[0] > sounds[0] and after[1] > sounds[1], f"{sounds} -> {after}")
            flipped = f"() => {DBG}.room.playing === {'false' if playing else 'true'}"
            try:
                a.wait_for_function(flipped, timeout=3000)
                b.wait_for_function(flipped, timeout=3000)
                toggled = True
            except PlaywrightTimeout:
                toggled = False
            check("a click on the picture plays or pauses for everyone", toggled)
            time.sleep(0.6)  # past the double-click interval, so this is a click of its own
            a.mouse.down()  # and back, for the checks below
            a.mouse.up()
            a.wait_for_function(f"() => {DBG}.room.playing === {'true' if playing else 'false'}", timeout=3000)
            time.sleep(0.6)
            a.dblclick("#stage", position={"x": 300, "y": 200})
            a.wait_for_function("() => document.fullscreenElement", timeout=3000)
            time.sleep(0.5)
            check("a double click goes fullscreen without playing or pausing",
                  a.evaluate(f"() => {DBG}.room.playing") == playing)
            a.evaluate("() => document.exitFullscreen()")
            a.wait_for_function("() => !document.fullscreenElement")

            # ---- pen: a line drawn in A shows in B at the same place, in A's colour
            blur(a)
            a.keyboard.press("d")
            check("d turns the pen on", a.evaluate(f"() => {DBG}.penMode"))
            a.mouse.move(ra["left"] + 0.2 * ra["w"], ra["top"] + 0.3 * ra["h"])
            a.mouse.down()
            a.mouse.move(ra["left"] + 0.6 * ra["w"], ra["top"] + 0.3 * ra["h"], steps=20)
            a.mouse.up()
            b.wait_for_function(f"() => {DBG}.strokes === 1", timeout=3000)
            time.sleep(0.3)
            on, off = b.evaluate(CANVAS_PIXEL, [0.4, 0.3]), b.evaluate(CANVAS_PIXEL, [0.4, 0.6])
            drawn = "#%02x%02x%02x" % tuple(on[:3])
            check("a stroke shows in the other window at the same spot, in the drawer's colour",
                  on[3] > 200 and drawn == color["Erkin"] and off[3] == 0, f"{drawn} alpha {on[3]}, off-line alpha {off[3]}")

            # ---- clear: B clears the drawings for everyone
            b.mouse.move(400, 300)
            b.click("#clearBtn")
            a.wait_for_function(f"() => {DBG}.strokes === 0", timeout=3000)
            toasts = a.evaluate("() => [...document.querySelectorAll('.toast')].map(t => t.textContent).join(' | ')")
            check("clearing removes the drawings for everyone and says who did it", "Masha" in toasts, toasts)

            check("no errors in either window", not errors, " || ".join(errors))
            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--headed", action="store_true", help="show the browser windows")
    args = parser.parse_args()
    if not shutil.which("ffmpeg"):
        print("ffmpeg is not on PATH")
        return 2
    run(args.headed)
    passed = sum(RESULTS)
    print(f"\n{passed}/{len(RESULTS)} passed")
    return 0 if RESULTS and passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
