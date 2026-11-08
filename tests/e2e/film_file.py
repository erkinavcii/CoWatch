"""Browser test: what a film file carries. A video with two sound tracks and two subtitles inside
is opened by the host; both windows get the file's subtitles as tracks, the sound track is
switched for the room, and the settings page shows the storage of downloaded torrents.

    python tests/e2e/film_file.py [--headed]
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

SRT_TR = "1\n00:00:00,500 --> 00:00:07,500\nGüzel, şimdi çıkıyoruz.\n"
SRT_EN = "1\n00:00:00,500 --> 00:00:07,500\nGood, we leave now.\n"


def make_video(folder: Path) -> Path:
    """8 s, a dubbed Turkish and an original Japanese sound track, Turkish and English subtitles."""
    (folder / "tr.srt").write_text(SRT_TR, encoding="utf-8")
    (folder / "en.srt").write_text(SRT_EN, encoding="utf-8")
    path = folder / "Film.Dual.Audio.Multi.Subs.mkv"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24",
        "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000",
        "-f", "lavfi", "-i", "sine=frequency=550:sample_rate=48000",
        "-i", str(folder / "tr.srt"), "-i", str(folder / "en.srt"),
        "-t", "8", "-map", "0:v", "-map", "1:a", "-map", "2:a", "-map", "3:s", "-map", "4:s",
        "-c:v", "libx264", "-preset", "ultrafast", "-g", "48", "-pix_fmt", "yuv420p", "-c:a", "aac", "-c:s", "srt",
        "-metadata:s:a:0", "language=tur", "-metadata:s:a:0", "title=Dublaj", "-metadata:s:a:1", "language=jpn",
        "-metadata:s:s:0", "language=tur", "-metadata:s:s:1", "language=eng", "-metadata:s:s:1", "title=English",
        str(path),
    ], check=True)
    return path


def run(headed: bool) -> None:
    tmp = Path(tempfile.mkdtemp(prefix="cowatch-e2e-file-"))
    video = make_video(tmp)
    port = free_port()
    server = start_server(port, tmp / "data")
    base = f"http://127.0.0.1:{port}"
    errors: list[str] = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=not headed, args=["--autoplay-policy=no-user-gesture-required"])
            pages = []
            for name in ("Erkin", "Masha"):
                ctx = browser.new_context(viewport={"width": 1280, "height": 860}, locale="tr-TR")
                page = ctx.new_page()
                page.on("pageerror", lambda exc, n=name: errors.append(f"{n} pageerror: {exc}"))
                # 503: the storage request, with no torrent helper in this test (checked below).
                page.on("console", lambda msg, n=name: errors.append(f"{n} console: {msg.text}")
                        if msg.type == "error" and "favicon" not in msg.text and "503" not in msg.text else None)
                page.goto(f"{base}/?k={KEY}")
                page.fill("#nameInput", name)
                page.click("#joinForm button[type=submit]")
                pages.append(page)
            a, b = pages

            a.wait_for_selector("#pathForm:not([hidden])")
            a.fill("#pathInput", str(video))
            a.press("#pathInput", "Enter")
            for page in (a, b):
                page.wait_for_function(
                    f"() => {{ const v = document.querySelector('#video'); return {DBG}.media && v.videoWidth > 0 && v.readyState >= 2; }}",
                    timeout=60000)

            # ---- the subtitles inside the file
            for page in (a, b):
                page.wait_for_function(f"() => {DBG}.tracks.filter(t => t.source === 'embedded').length === 2", timeout=20000)
            tracks = a.evaluate(f"() => {DBG}.tracks")
            tr = next(t for t in tracks if t["lang"] == "tr")
            options = a.eval_on_selector_all("#primarySel option", "os => os.map(o => o.textContent)")
            check("the file's own subtitles join the list in both windows, marked as from the file",
                  {t["lang"] for t in tracks} == {"tr", "en"} and all(t["hashMatch"] for t in tracks)
                  and "Türkçe · dosyanın içinden ✓" in options
                  and any(o == "İngilizce · dosyanın içinden ✓" for o in options), str(options))
            a.select_option("#primarySel", tr["id"])
            a.evaluate("() => { const s = document.querySelector('#seekBar'); s.value = '2'; s.dispatchEvent(new Event('change')); }")
            a.wait_for_function(f"() => Math.abs({DBG}.filmTime - 2) < 0.3", timeout=20000)
            a.wait_for_function("() => document.querySelector('#subPrimary').textContent.includes('Güzel')", timeout=5000)
            check("picked as the main subtitle, the Turkish one shows on the film", True)

            # ---- the sound track, for everyone
            a.evaluate("() => window.scrollTo(0, 0)")
            labels = a.eval_on_selector_all("#audioSel option", "os => os.map(o => o.textContent)")
            stream_before = a.evaluate(f"() => {DBG}.media.streamId")
            a.select_option("#audioSel", "1")
            for page in (a, b):
                page.wait_for_function(
                    f"() => {DBG}.media.audioIndex === 1 && {DBG}.media.streamId !== '{stream_before}'"
                    " && document.querySelector('#video').readyState >= 2", timeout=30000)
            check("two sound tracks to pick from; the switch reaches both windows with a new stream",
                  a.is_visible("#audioField") and len(labels) == 2 and labels == ["Türkçe · Dublaj (AAC 1ch)", "Japonca (AAC 1ch)"] and b.eval_on_selector("#audioSel", "s => s.value") == "1",
                  str(labels))

            # ---- storage on the settings page (no torrent helper in this test: it says so)
            a.click("#settingsBtn")
            a.wait_for_selector("#settingsOverlay:not([hidden])")
            a.wait_for_function("() => document.querySelector('#storageInfo').textContent !== '…'", timeout=10000)
            info = a.inner_text("#storageInfo")
            check("the settings page has the storage of downloaded torrents",
                  a.is_visible("#storageSet") and "Torrent yardımcısı çalışmıyor" in info
                  and a.is_disabled("#storageClean"), info)

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
