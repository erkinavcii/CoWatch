"""Two viewers in two browser windows of different sizes, end to end: sync, per-viewer
subtitles, shared cursors, pokes, the pen and the chat; then a phone joins.

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
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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


def start_server(port: int, data_dir: Path, extra: dict | None = None) -> subprocess.Popen:
    env = dict(os.environ, ACCESS_KEY=KEY, DATA_DIR=str(data_dir), COWATCH_DOTENV="", ADDONS_BUILTIN="0", **(extra or {}))
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


def start_fake_ai() -> tuple[ThreadingHTTPServer, int]:
    """An OpenAI-compatible provider that "translates" by putting [de] in front of each line."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, data: dict) -> None:
            body = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._send({"data": [{"id": "fake-model"}]})

        def do_POST(self):
            prompt = json.loads(self.rfile.read(int(self.headers["Content-Length"])))["messages"][1]["content"]
            if prompt.startswith("Below are the subtitles"):
                answer = "Summary: a test film."
            else:
                lines = prompt.split("Lines to translate:\n", 1)[1].splitlines()
                answer = "\n".join(f"{line.split(' ', 1)[0]} [de] {line.split(' ', 1)[1]}" for line in lines)
            time.sleep(0.3)  # long enough to see the notice follow the steps
            self._send({"choices": [{"message": {"content": answer}}]})

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


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
    fake_ai, ai_port = start_fake_ai()
    server = start_server(port, tmp / "data", {"AI_PROVIDER": "custom", "AI_PROTOCOL": "openai", "AI_MODEL": "fake-model",
                                                "AI_BASE_URL": f"http://127.0.0.1:{ai_port}/v1", "AI_API_KEY": "test"})
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
                if name == "Masha":
                    page.click("#joinAnimals button[title='Tilki']")
                page.click("#joinForm button[type=submit]")
                pages[name] = page
            a, b = pages["Erkin"], pages["Masha"]

            a.wait_for_function(f"() => {DBG}.members.length === 2 && {DBG}.members.every(m => m.color)")
            color = {m["name"]: m["color"] for m in a.evaluate(f"() => {DBG}.members")}
            check("each viewer gets a colour of their own", color["Erkin"] != color["Masha"], str(color))
            animals = {m["name"]: m["animal"] for m in a.evaluate(f"() => {DBG}.members")}
            check("the animal picked on the join screen reaches the others, the ball wears it",
                  animals == {"Erkin": "ball", "Masha": "fox"}
                  and b.evaluate("() => document.querySelector('.ball.me .face').dataset.animal") == "fox", str(animals))

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
            note = a.evaluate("() => { const n = document.querySelector('#centerMsg'); return n.hidden ? '' : n.textContent; }")
            check("the other window says who paused, the one who did sees nothing",
                  note == "Masha durdurdu" and b.is_hidden("#centerMsg"), repr(note))

            # ---- seek both to 7 s and read the subtitles each window shows
            b.evaluate("() => { const s = document.querySelector('#seekBar'); s.value = '7'; s.dispatchEvent(new Event('change')); }")
            for page in (a, b):
                page.wait_for_function(f"() => Math.abs({DBG}.filmTime - 7) < 0.3", timeout=20000)
            time.sleep(0.5)
            a_main, b_main, b_second = a.inner_text("#subPrimary"), b.inner_text("#subPrimary"), b.inner_text("#subSecondary")
            check("each window shows its own subtitles",
                  "5. saniye" in a_main and "5-я секунда" in b_main and "5. saniye" in b_second,
                  f"A {a_main!r} | B {b_main!r} / {b_second!r}")

            # ---- AI translation: the host translates the Turkish subtitle into German; it joins
            # both windows' lists and becomes the host's main subtitle
            a.select_option("#aiLang", "de")
            source = a.evaluate("() => document.querySelector('#aiSource').selectedOptions[0].textContent")
            a.evaluate("() => document.querySelector('#aiGo').click()")
            notice = ""
            for _ in range(40):
                notice = a.evaluate("() => [...document.querySelectorAll('.toast')].map(t => t.textContent).join(' | ')")
                if "/" in notice:
                    break
                time.sleep(0.1)
            check("the translation shows its progress in one notice", "Almanca" in notice and "/" in notice, notice)
            for page in (a, b):
                page.wait_for_function(f"() => {DBG}.tracks.some(t => t.source === 'ai' && t.lang === 'de')", timeout=20000)
            made = a.evaluate(f"""() => {{ const t = {DBG}.tracks.find(t => t.source === 'ai' && t.lang === 'de');
              return {{label: t.label, primary: {DBG}.primary === t.id, cues: t.cues}}; }}""")
            check("the translation joins both lists and becomes the asker's main subtitle",
                  made["primary"] and made["label"] == "AI · fake-model" and made["cues"] > 0, f"{made} from {source}")
            a.wait_for_function("() => document.querySelector('#subPrimary').textContent.startsWith('[de]')", timeout=5000)
            check("its lines play on the original times", a.inner_text("#subPrimary").startswith("[de]"), a.inner_text("#subPrimary"))

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

            # ---- eraser: A draws a second line lower down; B rubs across the first one only
            a.mouse.move(ra["left"] + 0.2 * ra["w"], ra["top"] + 0.6 * ra["h"])
            a.mouse.down()
            a.mouse.move(ra["left"] + 0.6 * ra["w"], ra["top"] + 0.6 * ra["h"], steps=20)
            a.mouse.up()
            b.wait_for_function(f"() => {DBG}.strokes === 2", timeout=3000)
            rb = b.evaluate(PICTURE_RECT)
            blur(b)
            b.keyboard.press("e")
            b.mouse.move(rb["left"] + 0.4 * rb["w"], rb["top"] + 0.15 * rb["h"])
            b.mouse.down()
            b.mouse.move(rb["left"] + 0.4 * rb["w"], rb["top"] + 0.45 * rb["h"], steps=12)
            b.mouse.up()
            a.wait_for_function(f"() => {DBG}.strokes === 1", timeout=3000)
            time.sleep(0.3)
            gone, kept = a.evaluate(CANVAS_PIXEL, [0.4, 0.3]), a.evaluate(CANVAS_PIXEL, [0.4, 0.6])
            check("the eraser takes the line it crosses for everyone, and leaves the other",
                  b.evaluate(f"() => {DBG}.eraser && {DBG}.strokes === 1") and gone[3] == 0 and kept[3] > 200,
                  f"crossed alpha {gone[3]}, other alpha {kept[3]}")
            b.keyboard.press("e")  # eraser off

            # ---- clear: B clears the drawings for everyone
            b.mouse.move(400, 300)
            b.click("#clearBtn")
            a.wait_for_function(f"() => {DBG}.strokes === 0", timeout=3000)
            toasts = a.evaluate("() => [...document.querySelectorAll('.toast')].map(t => t.textContent).join(' | ')")
            check("clearing removes the drawings for everyone and says who did it", "Masha" in toasts, toasts)

            # ---- chat: A's wide window has it as a column right of the film, B's narrow one over the picture
            blur(a)
            a.keyboard.press("d")  # pen off
            dock = a.evaluate("""() => { const box = document.querySelector('#chatBox');
              const c = box.getBoundingClientRect(), s = document.querySelector('#stage').getBoundingClientRect();
              return {docked: box.parentNode.id === 'chatDock', open: !box.hidden,
                      beside: c.left >= s.right && Math.abs(c.top - s.top) < 2 && Math.abs(c.height - s.height) < 2}; }""")
            check("on a wide screen the chat is an open column right of the film, as tall as it", all(dock.values()), str(dock))
            blur(b)
            b.keyboard.press("c")
            check("on a narrow one c opens it over the picture with the cursor in an empty box",
                  b.evaluate("() => document.querySelector('#chatBox').parentNode.id === 'stage' && !document.querySelector('#chatBox').hidden"
                             " && document.activeElement.id === 'chatInput' && document.querySelector('#chatInput').value === ''"))
            b.keyboard.type("Merhaba <b>herkes</b>")
            b.keyboard.press("Enter")
            a.wait_for_function("() => document.querySelector('#chatLog').textContent.includes('Merhaba')", timeout=3000)
            line = a.evaluate("""() => { const m = document.querySelector('#chatLog .chat-msg:last-child');
              return {text: m.textContent, html: m.querySelector('span').innerHTML, color: m.style.getPropertyValue('--c'),
                      badge: !document.querySelector('#chatBadge').hidden, peek: document.querySelectorAll('#chatPeek .chat-msg').length}; }""")
            check("the message reaches the column as plain text, with the sender's name and colour, nothing unread",
                  line["text"] == "MashaMerhaba <b>herkes</b>" and "<b>" not in line["html"] and line["color"] == color["Masha"]
                  and not line["badge"] and not line["peek"], str(line))

            a.click("#chatClose")
            check("closing the column gives the film its room back",
                  a.evaluate("() => !document.querySelector('#watch').classList.contains('docked')"))
            b.keyboard.type("ikinci")
            b.keyboard.press("Enter")
            a.wait_for_function("() => document.querySelector('#chatPeek .chat-msg')", timeout=3000)
            badge = a.evaluate("() => document.querySelector('#chatBadge').hidden ? '' : document.querySelector('#chatBadge').textContent")
            check("with the column closed a message peeks over the picture and counts", badge == "1", badge)
            dot = a.evaluate("""() => { const stage = document.querySelector('#stage'); const idle = stage.classList.contains('idle');
              stage.classList.add('idle'); const shown = getComputedStyle(document.querySelector('.chat-dot')).display;
              if (!idle) stage.classList.remove('idle'); return {shown, title: document.title}; }""")
            check("with the controls hidden a dot stays in the corner, and the tab counts", dot["shown"] == "grid" and dot["title"].startswith("(1) "), str(dot))
            a.click("#chatBtn")
            time.sleep(0.3)
            seen = a.evaluate("""() => ({docked: document.querySelector('#watch').classList.contains('docked'),
              badge: document.querySelector('#chatBadge').hidden, peek: document.querySelectorAll('#chatPeek .chat-msg').length,
              dot: document.querySelector('#stage').classList.contains('chat-unread'), title: document.title})""")
            check("the button brings the column back and clears the count",
                  seen["docked"] and seen["badge"] and not seen["peek"] and not seen["dot"] and not seen["title"].startswith("("), str(seen))

            a.evaluate("() => document.querySelector('#stage').requestFullscreen()")
            a.wait_for_function("() => document.fullscreenElement && document.querySelector('#chatBox').parentNode.id === 'stage'", timeout=3000)
            check("in fullscreen the chat moves over the picture, closed", a.evaluate("() => document.querySelector('#chatBox').hidden"))
            a.evaluate("() => document.exitFullscreen()")
            a.wait_for_function("() => !document.fullscreenElement && document.querySelector('#chatBox').parentNode.id === 'chatDock'",
                                timeout=3000)

            playing = b.evaluate(f"() => {DBG}.room.playing")
            b.click("#chatLog")
            time.sleep(0.6)
            check("a click in the panel over the picture neither pauses nor pokes", b.evaluate(f"() => {DBG}.room.playing") == playing)
            b.click("#chatInput")
            b.keyboard.press("Escape")
            check("Escape closes the panel", b.evaluate("() => document.querySelector('#chatBox').hidden"))

            # ---- a phone held upright: the chat in a box under the film, the header on one line,
            # and where only a <video> may go fullscreen (the iPhone) the stage fills the window
            phone_ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                            locale="tr-TR")
            # The iPhone's Safari has no fullscreen for anything but a <video>.
            phone_ctx.add_init_script("delete Element.prototype.requestFullscreen; delete Element.prototype.webkitRequestFullscreen;")
            phone = phone_ctx.new_page()
            phone.on("pageerror", lambda exc: errors.append(f"phone pageerror: {exc}"))
            phone.on("console", lambda msg: on_console(msg, "phone"))
            phone.goto(f"{base}/?k={KEY}")
            phone.fill("#nameInput", "Telefon")
            phone.tap("#joinForm button[type=submit]")
            phone.wait_for_function("() => document.querySelector('#video').readyState >= 2", timeout=30000)
            layout = phone.evaluate("""() => { const box = document.querySelector('#chatBox'), s = document.querySelector('#stage');
              const c = box.getBoundingClientRect(), r = s.getBoundingClientRect();
              return {docked: box.parentNode.id === 'chatDock', open: !box.hidden, under: c.top >= r.bottom && c.height >= 200,
                      log: document.querySelector('#chatLog').textContent.includes('Merhaba'),
                      header: document.querySelector('.top').offsetHeight, wide: document.documentElement.scrollWidth}; }""")
            check("on a phone the chat is an open box under the film, with what was said before",
                  layout["docked"] and layout["open"] and layout["under"] and layout["log"], str(layout))
            check("on a phone the header stays one line and nothing is wider than the screen",
                  layout["header"] < 60 and layout["wide"] <= 390, str(layout))
            phone.tap("#fsBtn")
            fill = phone.evaluate("""() => { const s = document.querySelector('#stage').getBoundingClientRect();
              return {fill: document.querySelector('#stage').classList.contains('fill'), w: s.width, h: s.height,
                      chatIn: document.querySelector('#chatBox').parentNode.id === 'stage'}; }""")
            check("without fullscreen the button makes the stage fill the window, the chat goes over it",
                  fill["fill"] and fill["w"] == 390 and fill["h"] == 844 and fill["chatIn"], str(fill))
            phone.tap("#fsBtn")
            check("and the button brings it back",
                  phone.evaluate("() => !document.querySelector('#stage').classList.contains('fill')"
                                 " && document.querySelector('#chatBox').parentNode.id === 'chatDock'"))
            phone_ctx.close()

            # ---- a ghost: a page that loaded but never joined (a phone's entry that did not
            # finish). The host removes it from its name; it stays out until it joins again.
            # Through Tailscale, like a phone: a page on this computer would be a host, and hosts stay.
            ghost_ctx = browser.new_context(locale="tr-TR", extra_http_headers={"Tailscale-User-Login": "ghost@example.com"})
            ghost = ghost_ctx.new_page()
            ghost.on("pageerror", lambda exc: errors.append(f"ghost pageerror: {exc}"))
            ghost.goto(f"{base}/?k={KEY}")
            a.wait_for_function(f"() => {DBG}.members.length === 3")
            ghost_id = ghost.evaluate(f"() => {DBG}.clientId")
            a.evaluate("() => window.scrollTo(0, 0)")
            a.click(f"#members .member[data-id='{ghost_id}']")
            a.click("#peerKick")
            a.wait_for_function(f"() => {DBG}.members.length === 2", timeout=5000)
            ghost.wait_for_selector("#joinNotice:not([hidden])", timeout=5000)
            time.sleep(3)  # longer than a reconnect would take
            check("the host removes a ghost from its name, and it does not come back by itself",
                  a.evaluate(f"() => {DBG}.members.length") == 2 and ghost.is_visible("#joinOverlay"))
            ghost.fill("#nameInput", "Geri")
            ghost.click("#joinForm button[type=submit]")
            a.wait_for_function(f"() => {DBG}.members.some(m => m.name === 'Geri')", timeout=5000)
            check("joining again brings it back", ghost.is_hidden("#joinNotice"))
            ghost_ctx.close()

            check("no errors in either window", not errors, " || ".join(errors))
            browser.close()
    finally:
        fake_ai.shutdown()
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
