"""Browser test: HEVC direct copy (hvc1) when everyone can play it, live transcode fallback
when an unsupported browser joins or a failure is cached in localStorage, and return to copy on
the next seek after they leave.

Requires Google Chrome or Microsoft Edge for HEVC decoding; skips cleanly if neither is installed:

    .\\.venv\\Scripts\\python tests\\e2e\\hevc_copy.py [--headed]
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

LENGTH = 30
BLACK = 12

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


def make_hevc_film(path: Path) -> None:
    """30 s, 8-bit x265 Main with open GOP and 10 s keyint, like real episode releases."""
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24",
        "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000",
        "-t", str(LENGTH), "-c:v", "libx265", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-x265-params", "open-gop=1:keyint=240:min-keyint=24", "-c:a", "aac", "-b:a", "96k", str(path),
    ], check=True)


def launch_hevc_browser(pw, headed: bool):
    args = ["--autoplay-policy=no-user-gesture-required"]
    for channel in ("chrome", "msedge"):
        try:
            browser = pw.chromium.launch(channel=channel, headless=not headed, args=args)
            probe_page = browser.new_page()
            ok = probe_page.evaluate(
                '() => (window.ManagedMediaSource || window.MediaSource)?.isTypeSupported(\'video/mp4; codecs="hvc1.1.6.L123.90"\') || false'
            )
            probe_page.close()
            if ok:
                return browser, channel
            browser.close()
        except Exception:
            pass
    return None, None


def attach_error_listeners(page, name: str, errors: list[str]) -> None:
    page.on("pageerror", lambda exc: errors.append(f"{name} pageerror: {exc}"))
    page.on("console", lambda msg: errors.append(f"{name} console: {msg.text}")
            if msg.type == "error" and "favicon" not in msg.text else None)


def join_page(browser, base: str, name: str, errors: list[str]):
    ctx = browser.new_context(viewport={"width": 1280, "height": 860}, locale="tr-TR")
    page = ctx.new_page()
    attach_error_listeners(page, name, errors)
    page.goto(f"{base}/?k={KEY}")
    page.fill("#nameInput", name)
    page.click("#joinForm button[type=submit]")
    return ctx, page


def frames_now(page) -> int:
    return page.evaluate("() => document.querySelector('#video').getVideoPlaybackQuality?.().totalVideoFrames || 0")


def run(headed: bool) -> None:
    tmp = Path(tempfile.mkdtemp(prefix="cowatch-e2e-hevc-"))
    film = tmp / "Episode.S01E01.1080p.x265.mkv"
    make_hevc_film(film)
    port = free_port()
    server = start_server(port, tmp / "data", {"HELPER_PORT": str(free_port())})
    base = f"http://127.0.0.1:{port}"
    errors: list[str] = []
    try:
        with sync_playwright() as pw:
            hevc_browser, channel = launch_hevc_browser(pw, headed)
            if hevc_browser is None:
                print("SKIP: neither Chrome nor Edge with HEVC MSE support is available here", flush=True)
                return
            plain_browser = pw.chromium.launch(headless=not headed, args=["--autoplay-policy=no-user-gesture-required"])
            print(f"using {channel} for HEVC viewers and Chromium for fallback viewer", flush=True)

            ctx_a, a = join_page(hevc_browser, base, "Erkin", errors)
            ctx_b, b = join_page(hevc_browser, base, "Masha", errors)
            a.wait_for_function(f"() => {DBG}.members.length === 2 && {DBG}.members.every(m => m.joined)")
            check("HEVC browsers report Main profile support",
                  a.evaluate(f"() => {DBG}.hevc.main") and b.evaluate(f"() => {DBG}.hevc.main"))

            a.wait_for_selector("#pathForm:not([hidden])")
            a.fill("#pathInput", str(film))
            a.press("#pathInput", "Enter")

            for page in (a, b):
                page.wait_for_function(
                    f"() => {DBG}.media && {DBG}.media.mode === 'copy' && document.querySelector('#video').readyState >= 2",
                    timeout=30000,
                )
            card_copy = a.inner_text("#mediaInfo")
            check("film starts in HEVC copy mode with expected card text",
                  a.evaluate(f"() => {DBG}.media.videoCodec") == "hevc" and "HEVC, herkes oynatabiliyor, çevrilmeden" in card_copy,
                  card_copy)

            a.evaluate("() => document.activeElement && document.activeElement.blur()")
            a.keyboard.press("Space")
            for page in (a, b):
                page.wait_for_function(f"() => {DBG}.room.playing && {DBG}.filmTime > 1.5", timeout=20000)
            for name, page in (("Erkin", a), ("Masha", b)):
                bright = page.evaluate(BRIGHTNESS)
                check(f"{name} decodes bright HEVC copy picture",
                      bright is not None and bright >= BLACK and frames_now(page) > 5, str(bright))

            # Seek past first keyint (10 s) on open-GOP x265 and ensure both keep decoding smoothly.
            a.evaluate(f"""() => {{ const s = document.querySelector('#seekBar'); s.max = '{LENGTH}'; s.value = '14';
              s.dispatchEvent(new Event('change')); }}""")
            for name, page in (("Erkin", a), ("Masha", b)):
                page.wait_for_function(
                    f"() => Math.abs({DBG}.filmTime - 14) < 3 && document.querySelector('#video').readyState >= 3",
                    timeout=20000,
                )
                f0 = frames_now(page)
                time.sleep(1.0)
                bright = page.evaluate(BRIGHTNESS)
                check(f"{name} keeps playing in copy mode after open-GOP seek",
                      page.evaluate(f"() => {DBG}.media.mode") == "copy" and frames_now(page) > f0 and (bright or 0) >= BLACK,
                      f"frames {f0}->{frames_now(page)}, bright={bright}")

            # 3rd viewer joins on Playwright Chromium (no HEVC MSE): switches room live to transcode.
            ctx_c, c = join_page(plain_browser, base, "Misafir", errors)
            check("Playwright Chromium reports no HEVC Main support", not c.evaluate(f"() => {DBG}.hevc.main"))
            for name, page in (("Erkin", a), ("Masha", b), ("Misafir", c)):
                page.wait_for_function(
                    f"() => {DBG}.media && {DBG}.media.mode === 'transcode' && document.querySelector('#video').readyState >= 2",
                    timeout=30000,
                )
                bright = page.evaluate(BRIGHTNESS)
                check(f"{name} plays transcoded fallback with non-black picture",
                      page.evaluate(f"() => {DBG}.media.hevcBlocker") == "Misafir" and (bright or 0) >= BLACK,
                      f"blocker={page.evaluate(f'() => {DBG}.media.hevcBlocker')}, bright={bright}")
            check("film card shows who caused HEVC transcode",
                  "Misafir" in a.inner_text("#mediaInfo") and "HEVC oynatamıyor" in a.inner_text("#mediaInfo"),
                  a.inner_text("#mediaInfo"))

            # Unsupported viewer leaves -> room stays transcoded until next seek, then returns to copy.
            stream_before_leave = a.evaluate(f"() => {DBG}.media.streamId")
            ctx_c.close()
            a.wait_for_function(f"() => {DBG}.members.length === 2", timeout=15000)
            time.sleep(0.5)
            check("leaving does not interrupt playback immediately",
                  a.evaluate(f"() => {DBG}.media.mode") == "transcode"
                  and a.evaluate(f"() => {DBG}.media.streamId") == stream_before_leave)
            a.evaluate(f"""() => {{ const s = document.querySelector('#seekBar'); s.max = '{LENGTH}'; s.value = '5';
              s.dispatchEvent(new Event('change')); }}""")
            for page in (a, b):
                page.wait_for_function(
                    f"() => {DBG}.media.mode === 'copy' && document.querySelector('#video').readyState >= 2",
                    timeout=30000,
                )
            check("next seek after blocker leaves restores HEVC copy mode",
                  a.evaluate(f"() => {DBG}.media.hevcBlocker") is None and b.evaluate(f"() => {DBG}.media.mode") == "copy")

            # Verify 7-day -> 30-day TTL localStorage fallback cache behavior in Chrome/Edge.
            ctx_d, d = join_page(hevc_browser, base, "Deneme", errors)
            now_ms = int(time.time() * 1000)
            ttl_check = d.evaluate(f"""(now) => {{
              const k = 'cowatch.hevcFailed.v1';
              const initial = {DBG}.hevc.main;
              const ua = navigator.userAgent;
              const m = ua.match(/\\b(Edg(?:iOS|A)?|Chrome)\\/(\\d+)/);
              const br = m ? m[1] + '/' + m[2] : ua.slice(0, 60);
              localStorage.setItem(k, JSON.stringify({{ browser: br, fails: 1, until: now + 3600000 }}));
              const blockedActive = {DBG}.hevc.main;
              localStorage.setItem(k, JSON.stringify({{ browser: br, fails: 1, until: now - 1000 }}));
              const unblockedExpired = {DBG}.hevc.main;
              localStorage.setItem(k, JSON.stringify({{ browser: 'OldBrowser/1', fails: 2, until: now + 99999999 }}));
              const unblockedNewMajor = {DBG}.hevc.main;
              return {{ initial, blockedActive, unblockedExpired, unblockedNewMajor }};
            }}""", now_ms)
            check("localStorage HEVC cache respects active TTL, 7d expiry, and major version reset",
                  ttl_check == {"initial": True, "blockedActive": False, "unblockedExpired": True, "unblockedNewMajor": True},
                  str(ttl_check))
            ctx_d.close()
            log_text = (tmp / "data" / "playback.log").read_text(encoding="utf-8") if (tmp / "data" / "playback.log").exists() else ""
            check("honest non-HEVC browser does not trigger false codec_failed reports",
                  "Misafir [codec_failed]" not in log_text and "Misafir [hevc]" in log_text)

            ctx_a.close()
            ctx_b.close()
            plain_browser.close()
            hevc_browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
        shutil.rmtree(tmp, ignore_errors=True)
    check("no page errors or console errors", not errors, "; ".join(errors))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    run(args.headed)
    passed = sum(RESULTS)
    print(f"\n{passed}/{len(RESULTS)} passed")
    sys.exit(0 if passed == len(RESULTS) else 1)
