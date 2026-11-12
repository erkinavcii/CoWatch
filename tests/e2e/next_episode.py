"""Browser test: the next episode and resuming where a film was left. Two short episodes in one
folder; the host opens the first, the film card offers the second (only to the host: a file on
the host's computer), and it opens for both windows. Near the end of an episode a card over the
picture offers the next one. The first episode opened again starts paused where it was left,
with a notice in both windows and a button to start from the beginning.

    python tests/e2e/next_episode.py [--headed]
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from two_viewers import DBG, KEY, RESULTS, check, free_port, start_server  # noqa: E402

LENGTH = 300  # s: a resume point needs a minute from the start and two from the end


def make_episodes(folder: Path) -> list[Path]:
    paths = []
    for number, (source, tone, title) in enumerate((("testsrc2", 330, "Pilot"), ("smptebars", 550, "The.Second.One")), 1):
        path = folder / f"Show.S01E0{number}.{title}.720p.mkv"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"{source}=size=320x180:rate=10",
            "-f", "lavfi", "-i", f"sine=frequency={tone}:sample_rate=48000",
            "-t", str(LENGTH), "-c:v", "libx264", "-preset", "ultrafast", "-g", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "48k", str(path),
        ], check=True)
        paths.append(path)
    return paths


def seek(page, target: float) -> None:
    page.evaluate(f"""() => {{ const s = document.querySelector('#seekBar'); s.max = '{LENGTH}'; s.value = '{target}';
      s.dispatchEvent(new Event('change')); }}""")


def run(headed: bool) -> None:
    tmp = Path(tempfile.mkdtemp(prefix="cowatch-e2e-next-"))
    first, second = make_episodes(tmp)
    port = free_port()
    server = start_server(port, tmp / "data", {"HELPER_PORT": str(free_port())})
    base = f"http://127.0.0.1:{port}"
    errors: list[str] = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=not headed, args=["--autoplay-policy=no-user-gesture-required"])
            pages = []
            # The second window is a friend over Tailscale Serve: not the host.
            for name, headers in (("Erkin", None), ("Masha", {"Tailscale-User-Login": "friend@example.com"})):
                ctx = browser.new_context(viewport={"width": 1280, "height": 860}, locale="tr-TR",
                                          extra_http_headers=headers)
                page = ctx.new_page()
                page.on("pageerror", lambda exc, n=name: errors.append(f"{n} pageerror: {exc}"))
                page.on("console", lambda msg, n=name: errors.append(f"{n} console: {msg.text}")
                        if msg.type == "error" and "favicon" not in msg.text else None)
                page.goto(f"{base}/?k={KEY}")
                page.fill("#nameInput", name)
                page.click("#joinForm button[type=submit]")
                pages.append(page)
            a, b = pages

            def loaded(page, title_part: str) -> None:
                page.wait_for_function(
                    f"""() => {{ const v = document.querySelector('#video'); const m = {DBG}.media;
                      return m && m.title.includes({title_part!r}) && v.readyState >= 2; }}""", timeout=60000)

            a.wait_for_selector("#pathForm:not([hidden])")
            a.fill("#pathInput", str(first))
            a.press("#pathInput", "Enter")
            for page in (a, b):
                loaded(page, "S01E01")
            a.wait_for_selector("#nextBtn:not([hidden])", timeout=10000)
            label = a.inner_text("#nextBtn")
            check("the film card offers the next episode by its number and title",
                  label == "Sonraki bölüm: S01E02 The Second One", label)
            check("a file on the host's computer: the friend gets no button, and no path in the message",
                  b.is_hidden("#nextBtn") and b.evaluate(f"() => {DBG}.media.next") == {"label": "S01E02 The Second One", "kind": "local"})
            refused = b.context.request.post(f"{base}/api/media/next", data={}).status
            check("and the server refuses it to the friend", refused == 403, str(refused))

            seek(a, 100)
            a.wait_for_function(f"() => Math.abs({DBG}.room.position - 100) < 1", timeout=20000)
            a.evaluate("() => document.querySelector('#nextBtn').click()")
            for page in (a, b):
                loaded(page, "S01E02")
            check("the next episode opens for both windows, from its beginning",
                  a.evaluate(f"() => {DBG}.room.position") < 1 and b.evaluate(f"() => {DBG}.media.title").startswith("Show.S01E02"))
            check("the last episode has no next one", a.is_hidden("#nextBtn") and a.evaluate(f"() => {DBG}.media.next") is None)

            # ---- the first episode again: where it was left
            a.evaluate("() => window.scrollTo(0, 0)")
            a.fill("#pathInput", str(first))
            a.press("#pathInput", "Enter")
            for page in (a, b):
                loaded(page, "S01E01")
            a.wait_for_selector("#shareAsks [data-resume]", timeout=10000)
            b.wait_for_selector("#shareAsks [data-resume]", timeout=10000)
            notice = b.inner_text("#shareAsks [data-resume]")
            state = b.evaluate(f"() => ({DBG}.room)")
            check("opened again, the first episode starts paused where it was left, with a notice in both windows",
                  abs(state["position"] - 100) < 1 and not state["playing"] and "Kaldığınız yerden: 1:40" in notice
                  and "Baştan başla" in notice, f"{state} {notice!r}")
            b.click("#shareAsks [data-resume] button.primary")
            a.wait_for_function(f"() => {DBG}.room.position < 1", timeout=20000)
            a.wait_for_selector("#shareAsks [data-resume]", state="detached", timeout=5000)
            check("the friend's 'start from the beginning' takes the room to 0 and the notice goes in both windows",
                  a.evaluate(f"() => {DBG}.room.position") < 1 and b.query_selector("#shareAsks [data-resume]") is None)

            # ---- near the end: a card over the picture
            a.evaluate("() => window.scrollTo(0, 0)")  # the stage is not the small box in the corner
            a.wait_for_selector("#stage:not(.mini)")
            seek(a, LENGTH - 30)
            try:
                a.wait_for_selector("#shareAsks [data-next]", timeout=10000)
            except Exception:
                print(a.evaluate(f"() => ({{room: {DBG}.room, next: {DBG}.media.next, asks: document.querySelector('#shareAsks').outerHTML}})"))
                raise
            card = a.inner_text("#shareAsks [data-next]")
            check("in the last minute a card over the picture offers the next episode (not to the friend)",
                  "S01E02 The Second One" in card and b.query_selector("#shareAsks [data-next]") is None, card)
            a.click("#shareAsks [data-next] button.primary")
            for page in (a, b):
                loaded(page, "S01E02")
            check("the card opens it for both windows", a.query_selector("#shareAsks [data-next]") is None)

            check("no errors in the browser console", not errors, "\n".join(errors[:5]))
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--headed", action="store_true")
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
