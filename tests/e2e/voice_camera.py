"""Voice and camera, end to end, against a real server and ffmpeg (two_viewers.py covers sync,
subtitles, pointers, pokes and the pen).

The host opens the localhost link; the guest carries the header Tailscale Serve adds, so the
server sees it as a friend coming through HTTPS and keeps the local file field from it.
Chromium's fake camera stands in for the cameras, synthesised speech for the microphones.
Checks: voice, who is talking, the film getting quieter, a dropped connection, camera tiles,
fullscreen, Ctrl+E; then a third viewer joins from the preview with both on, and the tiles
are dragged, shrunk, and the connections rebuilt.

    .\\.venv\\Scripts\\python -m pip install -r requirements-dev.txt
    .\\.venv\\Scripts\\python -m playwright install chromium
    .\\.venv\\Scripts\\python tests\\e2e\\voice_camera.py            (--headed to watch)

Needs ffmpeg (with flite, as in the Gyan builds). Not part of pytest (no test_ prefix).
"""

from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
KEY = "e2e-key"
FAKE_MEDIA = ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"]
SAMPLES = ROOT / "samples"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_video(work: Path) -> Path:
    """The README's test video: the second in big digits, H.264 with AC3 5.1 sound."""
    existing = SAMPLES / "test-video.mkv"
    if existing.is_file():
        return existing
    out = work / "test-video.mkv"
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=24",
         "-f", "lavfi", "-i", "sine=frequency=440", "-t", "60", "-c:v", "libx264", "-g", "48",
         "-pix_fmt", "yuv420p", "-af", "volume=0.1", "-c:a", "ac3", "-ac", "6", str(out)],
        check=True,
    )
    return out


SPEECH = ("Hello, can you hear me? This scene is great. Wait, who is that man in the red coat? "
          "I think he was in the first part too. Let us watch the next one after this.")


def fake_voice(work: Path) -> Path:
    """Sound for the fake microphone (Chrome loops the file). Chrome's own fake microphone only
    beeps briefly, too short to count as talking, and a steady tone is removed by the noise
    suppressor within half a second; synthesised speech gets through like a real voice."""
    out = work / "voice.wav"
    text = work / "speech.txt"
    text.write_text(SPEECH, encoding="utf-8")
    # The filter graph wants a relative path with forward slashes, hence the working folder.
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "flite=textfile=speech.txt:voice=slt",
         "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", out.name],
        check=True, cwd=work,
    )
    return out


def start_server(port: int, data_dir: Path, library: Path) -> subprocess.Popen:
    env = dict(os.environ, DATA_DIR=str(data_dir), ACCESS_KEY=KEY, OPENSUBTITLES_API_KEY="", COWATCH_DOTENV="",
               ADDONS_BUILTIN="0", LIBRARY_DIRS=str(library))
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server.main:app", "--host", "127.0.0.1", "--port", str(port),
         "--log-level", "warning"],
        cwd=ROOT, env=env, creationflags=flags,
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/static/app.js", timeout=1)
            return proc
        except OSError:
            time.sleep(0.3)
    proc.kill()
    raise RuntimeError("server did not start")


def stop_server(proc: subprocess.Popen) -> None:
    # A gentle stop lets the server's shutdown end ffmpeg too.
    proc.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGINT)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def ok(text: str) -> None:
    print(f"  ok  {text}")


def debug(page: Page) -> dict:
    return page.evaluate("cowatchDebug()")


def join(page: Page, base: str, name: str) -> None:
    page.goto(f"{base}/?k={KEY}")
    page.fill("#nameInput", name)
    page.click("#joinForm button[type=submit]")
    page.wait_for_function("cowatchDebug().members.some(m => m.name && m.name !== '?' && m.id === cowatchDebug().clientId)")


def in_sync(host: Page, guest: Page, label: str) -> None:
    a, b = debug(host), debug(guest)
    assert abs(a["drift"]) < 0.5 and abs(b["drift"]) < 0.5, f"{label}: drift {a['drift']:.2f} / {b['drift']:.2f}"
    assert abs(a["filmTime"] - b["filmTime"]) < 1.0, f"{label}: {a['filmTime']:.2f} vs {b['filmTime']:.2f}"
    ok(f"{label}: {a['filmTime']:.1f} s / {b['filmTime']:.1f} s")


def peers_connected(page: Page, count: int = 1) -> None:
    page.wait_for_function(
        f"(() => {{ const v = cowatchDebug().voice; return v.peers.length === {count}"
        " && v.peers.every(p => p.state === 'connected' && p.transceivers === 4); })()",
        timeout=20000)


def tile_plays(page: Page, member_id: str) -> None:
    page.wait_for_function(
        f"(() => {{ const v = document.querySelector('.cam.live[data-id=\"{member_id}\"] video');"
        " return !!v && v.videoWidth > 0 && v.currentTime > 0.5; })()", timeout=20000)


def hears(page: Page) -> None:
    """Sound is coming in from the other viewer."""
    page.wait_for_function("cowatchDebug().voice.peers.some(p => p.level > 0.001)", timeout=15000)


def toggle_trust(host: Page, guest_id: str) -> None:
    host.click(f".member.others[data-id='{guest_id}']")
    host.wait_for_selector("#peerGrant", state="visible", timeout=5000)
    host.click("#peerGrant")


def check_library(host: Page, guest: Page, video: Path) -> None:
    """The host trusts the guest with the film folder; the guest opens the film from it."""
    item = f"#libraryList button[title$='/{video.name}']"
    host.wait_for_selector(item, timeout=10000)
    assert guest.locator("#libraryBox").is_hidden(), "guest sees the film folder before the host trusts them"
    guest_id = debug(guest)["clientId"]
    toggle_trust(host, guest_id)
    guest.wait_for_function(f"cowatchDebug().members.some(m => m.id === '{guest_id}' && m.cohost)", timeout=5000)
    guest.wait_for_selector(item, timeout=10000)
    assert guest.locator("#pathForm").is_hidden(), "a trusted guest still must not type paths"
    host.wait_for_selector(f".member[data-id='{guest_id}'] .role", timeout=5000)
    ok("host trusts the guest: the film folder shows up for them, with a badge")
    guest.click(item)
    for page in (host, guest):
        page.wait_for_function("document.querySelector('#video').readyState >= 2", timeout=90000)
    ok("the guest opened the film from the host's folder; stream loaded in both")
    toggle_trust(host, guest_id)
    guest.wait_for_selector("#libraryBox", state="hidden", timeout=10000)
    ok("trust taken back: the film folder is gone for the guest")


def check_voice(host: Page, guest: Page) -> None:
    host_id = debug(host)["clientId"]
    peers_connected(host)
    peers_connected(guest)
    ok("voice connection up, four transceivers each side (sound, camera, screen picture and sound)")

    host.click("#micBtn")
    host.wait_for_function("cowatchDebug().voice.mic")
    guest.wait_for_function(f"cowatchDebug().members.some(m => m.id === '{host_id}' && m.mic)")
    hears(guest)
    ok("the host's microphone reaches the guest")

    guest.wait_for_function(f"cowatchDebug().voice.speaking.includes('{host_id}')", timeout=10000)
    guest.wait_for_function("cowatchDebug().voice.filmVolume < 0.9", timeout=5000)
    assert guest.locator(f".member[data-id='{host_id}']").evaluate("n => n.classList.contains('speaking')")
    ok("the guest sees the host talking and the film gets quieter")

    guest.evaluate("cowatchDebug.reconnect()")
    guest.wait_for_function(f"cowatchDebug().clientId && !cowatchDebug().members.some(m => m.id === '{debug(guest)['clientId']}')"
                            " && cowatchDebug().members.length === 2", timeout=15000)
    peers_connected(guest)
    peers_connected(host)
    hears(guest)
    ok("after the guest's connection drops, sound comes back")

    host.click("#micBtn")
    host.wait_for_function("!cowatchDebug().voice.mic")
    guest.wait_for_function(f"cowatchDebug().members.some(m => m.id === '{host_id}' && !m.mic)")
    guest.wait_for_function("cowatchDebug().voice.filmVolume > 0.99", timeout=5000)
    assert host.locator("#micBtn").evaluate("n => n.classList.contains('off')")
    ok("microphone off: shown to the guest, the film is back to full volume")


def check_camera(host: Page, guest: Page) -> None:
    guest_id = debug(guest)["clientId"]
    assert host.locator("#cams .cam").count() == 0, "tiles while every camera is off"

    guest.click("#camBtn")
    guest.wait_for_function("cowatchDebug().voice.camLive")
    tile_plays(host, guest_id)
    assert host.locator(".cam.me:not(.live) .cam-face").is_visible(), "the host's own tile should show the ball"
    guest.wait_for_selector(".cam.me.live", timeout=5000)
    ok("the guest's camera plays in the host's tile; the host's tile shows a ball")

    peer = debug(guest)["voice"]["peers"][0]
    assert peer["sendingVideo"] and peer["videoMaxBitrate"] == 500000, peer
    assert peer["transceivers"] == 4 and debug(host)["voice"]["peers"][0]["transceivers"] == 4
    ok("camera capped at 500 kbps, no new transceivers")

    tile = host.locator(f".cam.others[data-id='{guest_id}']")
    tile.click()
    host.wait_for_selector("#peerPop", state="visible", timeout=3000)
    guest.wait_for_timeout(800)
    assert guest.locator(".ripple").count() == 0, "a click on a tile poked"
    host.keyboard.press("Escape")
    ok("a click on a tile opens the volume, not a poke")

    host.click("#fsBtn")
    host.wait_for_function("document.fullscreenElement && document.fullscreenElement.id === 'stage'", timeout=5000)
    assert tile.is_visible(), "tile gone in fullscreen"
    box = tile.bounding_box()
    viewport = host.viewport_size
    assert box["x"] + box["width"] <= viewport["width"] + 1 and box["y"] >= 0, box
    host.evaluate("document.exitFullscreen()")
    host.wait_for_function("!document.fullscreenElement")
    ok("tiles stay on screen in fullscreen")

    guest.click("#camBtn")
    guest.wait_for_function("!cowatchDebug().voice.cam")
    host.wait_for_function("document.querySelectorAll('#cams .cam').length === 0", timeout=5000)
    ok("camera off: released, and the tiles go away")

    guest.locator("#stage").click(position={"x": 5, "y": 5})  # focus the page, not a field
    guest.keyboard.press("Control+e")
    host.wait_for_function(f"cowatchDebug().members.some(m => m.id === '{guest_id}' && m.cam)", timeout=10000)
    guest.keyboard.press("Control+e")
    host.wait_for_function(f"cowatchDebug().members.some(m => m.id === '{guest_id}' && !m.cam)", timeout=10000)
    assert not debug(guest)["penMode"]
    ok("Ctrl+E turns the camera on and off")


def film_paused(page: Page, paused: bool) -> None:
    page.wait_for_function(f"document.querySelector('#video').paused === {'true' if paused else 'false'}", timeout=15000)


def check_screen(host: Page, guest: Page) -> None:
    """The guest asks to share their screen; the host declines, then allows; the film waits."""
    guest_id = debug(guest)["clientId"]
    ask = f".share-ask[data-from='{guest_id}']"
    guest.locator("#stage").hover()
    guest.click("#screenBtn")
    host.wait_for_selector(ask, timeout=10000)
    guest.wait_for_selector(".share-ask[data-mine] video", timeout=5000)
    assert debug(host)["screen"]["owner"] is None
    assert not any(p["sendingScreen"] for p in debug(guest)["voice"]["peers"]), "screen sent before the answer"
    host.click(f"{ask} button.ghost")
    guest.wait_for_function("!cowatchDebug().screen.mine", timeout=5000)
    assert debug(host)["screen"]["owner"] is None
    ok("a guest's request waits for the host, nothing is sent meanwhile; declined, the capture closes")

    host.locator("#stage").hover()
    host.click("#playBtn")
    for page in (host, guest):
        film_paused(page, False)
    guest.locator("#stage").hover()
    guest.click("#screenBtn")
    host.wait_for_selector(f"{ask} button.primary", timeout=10000)
    host.click(f"{ask} button.primary")
    for page in (host, guest):
        page.wait_for_function("cowatchDebug().screen.showing", timeout=20000)
        film_paused(page, True)
    assert all(p["sendingScreen"] for p in debug(guest)["voice"]["peers"])
    assert debug(host)["voice"]["peers"][0]["transceivers"] == 4
    assert host.locator("#screenTag").inner_text().startswith("Misafir")
    ok("allowed: the guest's screen covers the film in both windows, and the film waits")

    host.click(f".member.others[data-id='{guest_id}']")
    host.wait_for_selector("#peerStopShare", state="visible", timeout=5000)
    host.click("#peerStopShare")
    for page in (host, guest):
        page.wait_for_function("!cowatchDebug().screen.owner && !cowatchDebug().screen.mine", timeout=10000)
        film_paused(page, False)
    assert host.locator("#screenVideo").is_hidden()
    ok("the host stops it: the screen goes and the film goes on")

    host.locator("#stage").hover()
    host.click("#screenBtn")  # the host shares without asking
    guest.wait_for_function(f"cowatchDebug().screen.owner === '{debug(host)['clientId']}' && cowatchDebug().screen.showing",
                            timeout=20000)
    host.locator("#stage").hover()
    host.click("#screenBtn")
    guest.wait_for_function("!cowatchDebug().screen.owner", timeout=10000)
    for page in (host, guest):
        film_paused(page, False)
    host.locator("#stage").hover()
    host.click("#playBtn")
    for page in (host, guest):
        film_paused(page, True)
    ok("the host shares at once and stops; the film is paused again for the next checks")


def check_third_viewer(browser, base: str, host: Page, guest: Page) -> None:
    """A third viewer turns the camera and microphone on in the preview before joining."""
    ctx = browser.new_context(viewport={"width": 1100, "height": 720},
                              extra_http_headers={"Tailscale-User-Login": "third@example.com"})
    third = ctx.new_page()
    third.goto(f"{base}/?k={KEY}")
    third.fill("#nameInput", "Üçüncü")
    third.click("#preCamBtn")
    third.click("#preMicBtn")
    third.wait_for_function("(() => { const v = document.querySelector('#previewVideo');"
                            " return document.querySelector('#preview').classList.contains('live') && v.videoWidth > 0; })()",
                            timeout=10000)
    third.wait_for_selector("#previewMeter i.on", state="attached", timeout=10000)
    ok("preview: camera picture and microphone meter before joining")

    third.click("#joinForm button[type=submit]")
    third_id = third.evaluate("cowatchDebug().clientId")
    for page in (host, guest):
        page.wait_for_function(f"cowatchDebug().members.some(m => m.id === '{third_id}' && m.joined && m.mic && m.cam)")
        tile_plays(page, third_id)
    for page in (host, guest, third):
        peers_connected(page, 2)
    hears(host)
    ok("joined with camera and microphone on; three viewers, each connected to the other two")

    # Drag the tiles to the bottom left of the host's picture.
    tile = host.locator(f".cam.others[data-id='{third_id}']")
    box = tile.bounding_box()
    stage = host.locator("#stage").bounding_box()
    host.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    host.mouse.down()
    host.mouse.move(stage["x"] + 80, stage["y"] + stage["height"] - 120, steps=10)
    host.mouse.up()
    host.wait_for_function("document.querySelector('#camsBox').parentNode.id === 'sideLeft'", timeout=3000)
    box = tile.bounding_box()
    assert box["x"] < stage["x"] + stage["width"] / 2 and box["y"] > stage["y"] + stage["height"] / 2, box
    assert host.locator("#peerPop").is_hidden(), "dropping the tiles opened the volume box"
    ok("tiles dragged to the bottom left corner")

    width = tile.bounding_box()["width"]
    tile.hover()
    host.click("#camsSizeBtn")
    host.wait_for_function(f"document.querySelector('.cam.others[data-id=\"{third_id}\"]').getBoundingClientRect().width < {width - 20}")
    host.click("#camsSizeBtn")
    host.wait_for_function(f"document.querySelector('.cam.others[data-id=\"{third_id}\"]').getBoundingClientRect().width > {width - 2}")
    ok("one button shrinks and restores the tiles")

    guest.evaluate("cowatchDebug.resetPeers()")
    peers_connected(guest, 2)
    peers_connected(host, 2)
    peers_connected(third, 2)
    tile_plays(guest, third_id)
    ok("rebuilt connections come back, picture included")

    ctx.close()
    for page in (host, guest):
        peers_connected(page, 1)
        page.wait_for_function("document.querySelector('#camsBox').hidden", timeout=5000)
    ok("the third viewer leaves: connection and tiles go")


def run(headed: bool) -> None:
    work = Path(tempfile.mkdtemp(prefix="cowatch-e2e-"))
    video = test_video(work)
    voice = fake_voice(work)
    port = free_port()
    base = f"http://localhost:{port}"
    server = start_server(port, work / "data", video.parent)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=not headed,
                args=FAKE_MEDIA + [f"--use-file-for-fake-audio-capture={voice}", "--autoplay-policy=no-user-gesture-required"])
            host_ctx = browser.new_context(viewport={"width": 1280, "height": 800})
            guest_ctx = browser.new_context(viewport={"width": 900, "height": 700},
                                            extra_http_headers={"Tailscale-User-Login": "friend@example.com"})
            host, guest = host_ctx.new_page(), guest_ctx.new_page()
            try:
                join(host, base, "Host")
                join(guest, base, "Misafir")
                for page in (host, guest):
                    page.wait_for_function("cowatchDebug().members.length === 2")
                ok("both joined, two members each")

                host.wait_for_selector("#pathForm", state="visible", timeout=10000)
                guest.wait_for_timeout(3500)  # one status poll
                assert guest.locator("#pathForm").is_hidden(), "guest sees the local file field"
                ok("local file field: host only")

                check_library(host, guest, video)

                # Subtitles, pointers, pokes and the pen are in two_viewers.py.
                host.click("#playBtn")
                for page in (host, guest):
                    page.wait_for_function("!document.querySelector('#video').paused && cowatchDebug().filmTime > 3",
                                           timeout=30000)
                in_sync(host, guest, "the guest plays along")

                host.locator("#stage").hover()  # the controls fade out while the film plays and the mouse is still
                host.click("#playBtn")
                for page in (host, guest):
                    page.wait_for_function("document.querySelector('#video').paused", timeout=10000)
                in_sync(host, guest, "paused")

                tracks = guest.evaluate(
                    "navigator.mediaDevices.getUserMedia({audio: true, video: true})"
                    ".then(s => { const n = s.getTracks().length; s.getTracks().forEach(t => t.stop()); return n; })")
                assert tracks == 2
                ok("fake camera and microphone available")

                check_voice(host, guest)
                check_camera(host, guest)
                check_screen(host, guest)
                check_third_viewer(browser, base, host, guest)

                host.click("#closeMedia")
                print("\nall good")
            except Exception:
                for name, page in (("host", host), ("guest", guest)):
                    shot = work / f"{name}.png"
                    page.screenshot(path=str(shot))
                    print(f"  screenshot: {shot}")
                raise
            finally:
                browser.close()
    finally:
        stop_server(server)
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found")
    run(headed="--headed" in sys.argv)
