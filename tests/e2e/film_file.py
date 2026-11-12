"""Browser test: what a film file carries. A video with two sound tracks and two subtitles inside
is opened by the host; both windows get the file's subtitles as tracks, the sound track is
switched for the room, and the settings page shows the storage of downloaded torrents. Then a
25-minute film: two subtitles made for other versions of it are aligned by hand in the panel.

    python tests/e2e/film_file.py [--headed]
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



# ---- for the alignment panel: a 25-minute film and two subtitles made for other versions of it.
def _lines(specific: dict[float, str], every: float, avoid: float) -> list[tuple[float, str]]:
    """The given lines at their film times, and filler lines every few seconds away from them."""
    out = dict(specific)
    k = 0
    at = 200.0
    while at < 1490:
        if all(abs(at - f) > avoid for f in specific):
            out[at] = f"Dolgu satırı {k}: hiçbir şey olmuyor."
            k += 1
        at += every
    return sorted(out.items())


# Made 5 s late: each line says film time + 5.
LATE_LINES = [(f + 5, text) for f, text in _lines({
    10: "Evet.", 20: "Hava bu sabah çok soğuk.", 30: "Polis arabası köşeyi döndü.", 40: "Klaus kapıyı açık bıraktı.",
    55: "Evet.", 70: "Mavi bisikletli postacı geldi.", 85: "Öğle yemeği soğudu.", 120: "Kimse bir şey demedi bugün.",
}, 8, 5)]
# Made for the 25 frames a second version of a 23,976 film: every line comes 4 % early, more and more.
PAL_LINES = [(f * 23.976 / 25, text) for f, text in _lines({
    60: "Birinci nokta: Zeynep geldi.", 1260: "Şebnem uzun yoldan döndü.", 1400: "Son satır: Ölçü tamam.",
}, 20, 8)]


def srt(lines: list[tuple[float, str]]) -> str:
    def stamp(sec: float) -> str:
        ms = round(sec * 1000)
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    return "".join(f"{i}\n{stamp(s)} --> {stamp(s + 3)}\n{text}\n\n" for i, (s, text) in enumerate(lines, 1))


def make_long_video(folder: Path) -> Path:
    """25 minutes, small and quick to make: two points of the alignment panel are 20 minutes apart."""
    path = folder / "Uzun.Film.mkv"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=5", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=22050",
        "-t", "1500", "-c:v", "libx264", "-preset", "ultrafast", "-g", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "32k",
        str(path),
    ], check=True)
    return path


def upload_subtitle(page, name: str, text: str) -> dict:
    return page.evaluate("""async ([name, text]) => {
      const form = new FormData();
      form.append('file', new Blob([text], {type: 'text/plain'}), name);
      form.append('lang', 'tr'); form.append('label', name);
      const res = await fetch('/api/subtitles/upload', {method: 'POST', body: form});
      return res.json(); }""", [name, text])


def center(page, selector: str) -> tuple[float, float]:
    box = page.locator(selector).bounding_box()
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def run(headed: bool) -> None:
    tmp = Path(tempfile.mkdtemp(prefix="cowatch-e2e-file-"))
    video = make_video(tmp)
    port = free_port()
    # A port with no torrent helper, even if one runs on this computer.
    server = start_server(port, tmp / "data", {"HELPER_PORT": str(free_port())})
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
            a.evaluate("() => { const s = document.querySelector('#seekBar'); s.max = '8'; s.value = '2'; s.dispatchEvent(new Event('change')); }")
            a.wait_for_function(f"() => Math.abs({DBG}.filmTime - 2) < 0.3", timeout=20000)
            a.wait_for_function("() => document.querySelector('#subPrimary').textContent.includes('Güzel')", timeout=5000)
            check("picked as the main subtitle, the Turkish one shows on the film", True)

            # ---- each subtitle its own timing, for me only
            en = next(t for t in tracks if t["lang"] == "en")
            a.select_option("#secondarySel", en["id"])
            a.wait_for_function("() => document.querySelector('#subSecondary').textContent.includes('Good')", timeout=5000)
            rows = a.eval_on_selector_all("#offsetRows .offset-label", "ls => ls.map(l => l.textContent)")
            a.evaluate("""() => { const b = document.querySelector('#offsetRows [data-slot=secondary] [data-off="500"]');
              for (let i = 0; i < 10; i++) b.click(); }""")
            a.evaluate("() => { const s = document.querySelector('#seekBar'); s.max = '8'; s.value = '2'; s.dispatchEvent(new Event('change')); }")
            a.wait_for_function(f"() => Math.abs({DBG}.filmTime - 2) < 0.3", timeout=20000)
            time.sleep(0.3)
            shown = a.evaluate("""() => ({primary: document.querySelector('#subPrimary').textContent,
              secondary: document.querySelector('#subSecondary').textContent,
              out: [...document.querySelectorAll('#offsetRows output')].map(o => o.textContent)})""")
            align = a.evaluate(f"() => {DBG}.align")
            check("each subtitle has its own offset: five seconds on the second leaves the main one where it was",
                  len(rows) == 2 and rows[0].startswith("Ana altyazı · Türkçe") and rows[1].startswith("İkinci altyazı · İngilizce")
                  and "Güzel" in shown["primary"] and not shown["secondary"] and shown["out"] == ["0,0 s", "+5,0 s"]
                  and align.get(en["id"], {}).get("offset") == 5000 and tr["id"] not in align,
                  f"{rows} {shown} {align}")
            check("an offset is only the one viewer's",
                  b.evaluate(f"() => Object.keys({DBG}.align).length") == 0)
            a.evaluate("() => document.querySelector('#offsetRows [data-slot=secondary] button.ghost').click()")
            a.wait_for_function("() => document.querySelector('#subSecondary').textContent.includes('Good')", timeout=5000)
            check("0 puts that subtitle back", a.evaluate(f"() => !({en['id']!r} in {DBG}.align)"))

            # The one offset of before, for both subtitles, becomes each chosen subtitle's own.
            b.evaluate("""() => { const p = JSON.parse(localStorage.getItem('cowatch.prefs.v1') || '{}');
              Object.assign(p, {offsetMs: 1500, primaryLang: 'tr', secondaryLang: 'en'}); delete p.align;
              localStorage.setItem('cowatch.prefs.v1', JSON.stringify(p)); }""")
            b.reload()
            b.click("#joinForm button[type=submit]")
            b.wait_for_function(f"() => {DBG}.primary && {DBG}.secondary && Object.keys({DBG}.align).length === 2", timeout=20000)
            moved = b.evaluate(f"""() => ({{align: Object.values({DBG}.align).map(a => a.offset),
              old: 'offsetMs' in JSON.parse(localStorage.getItem('cowatch.prefs.v1'))}})""")
            check("the old single offset becomes the chosen subtitles' own, and is gone",
                  moved["align"] == [1500, 1500] and not moved["old"], str(moved))
            b.reload()
            b.click("#joinForm button[type=submit]")
            b.wait_for_function(f"() => {DBG}.primary", timeout=20000)
            check("and it stays after reloading the page",
                  b.evaluate(f"() => document.querySelector('#offsetRows output').textContent") == "+1,5 s")

            # ---- automatic alignment: a shifted copy of the English subtitle, fitted to the file's own
            shifted = tmp / "en.shifted.srt"
            shifted.write_text(SRT_EN.replace("00:00:00,500 --> 00:00:07,500", "00:00:02,800 --> 00:00:09,800"),
                               encoding="utf-8")
            a.evaluate("() => { document.querySelector('details.add-subs').open = true; }")
            a.set_input_files("#subFile", str(shifted))
            a.fill("#subLang", "en")
            a.click("#uploadForm button[type=submit]")
            for page in (a, b):
                page.wait_for_function(f"() => {DBG}.tracks.some(t => t.label === 'en.shifted.srt')", timeout=10000)
            upload = next(t for t in a.evaluate(f"() => {DBG}.tracks") if t["label"] == "en.shifted.srt")
            row = a.locator("#trackList li", has_text="en.shifted.srt")
            row.locator(".align-btn").dispatch_event("click")
            a.wait_for_selector("#trackList .align-pick select")
            default = a.eval_on_selector("#trackList .align-pick select", "s => s.value")
            check("Auto-align offers the file's own subtitle in the same language as the reference",
                  default == en["id"], f"{default} {en['id']}")
            a.locator("#trackList .align-pick .align-go").dispatch_event("click")
            for page in (a, b):
                page.wait_for_function(f"() => {DBG}.tracks.some(t => t.source === 'aligned')", timeout=20000)
                page.wait_for_function("() => [...document.querySelectorAll('#trackList .label')]"
                                       ".some(l => l.textContent === 'en.shifted.srt · hizalı')", timeout=5000)
            made = next(t for t in a.evaluate(f"() => {DBG}.tracks") if t["source"] == "aligned")
            first = a.evaluate(f"async () => (await (await fetch('/api/subtitles/{made['id']}.json')).json()).cues[0][0]")
            notice = b.evaluate("() => [...document.querySelectorAll('#toasts .toast')].map(n => n.textContent).join(' | ')")
            check("the aligned copy joins both windows' lists, its line where the file's own one is",
                  made["fromTrack"] == upload["id"] and made["reference"] == en["id"] and abs(first - 0.5) <= 0.1
                  and "hizalandı (−2,3 sn)" in notice, f"{made} {first} {notice}")

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

            # ---- aligning a subtitle by hand (the panel in the chat's box), for me only
            a.click("#settingsClose")
            a.wait_for_selector("#settingsOverlay", state="hidden")
            long_film = make_long_video(tmp)
            a.evaluate("() => window.scrollTo(0, 0)")
            a.fill("#pathInput", str(long_film))
            a.press("#pathInput", "Enter")
            for page in (a, b):
                page.wait_for_function(
                    f"() => {DBG}.media && {DBG}.media.duration > 1400 && document.querySelector('#video').readyState >= 2",
                    timeout=60000)
            if a.evaluate(f"() => {DBG}.room.playing"):
                a.click("#playBtn")
            a.wait_for_function(f"() => !{DBG}.room.playing", timeout=5000)
            late = upload_subtitle(a, "late5.srt", srt(LATE_LINES))
            pal = upload_subtitle(a, "pal.srt", srt(PAL_LINES))
            for page in (a, b):
                page.wait_for_function(f"() => {DBG}.tracks.length === 2", timeout=10000)
            a.select_option("#primarySel", late["id"])
            b.select_option("#primarySel", late["id"])

            def seek_room(sec: float) -> None:
                a.evaluate(f"() => {{ const s = document.querySelector('#seekBar'); s.value = '{sec}'; s.dispatchEvent(new Event('change')); }}")
                for page in (a, b):
                    page.wait_for_function(f"() => Math.abs({DBG}.filmTime - {sec}) < 0.2 && document.querySelector('#video').readyState >= 2",
                                           timeout=30000)

            def tap_line(query: str, hits: int = 1) -> None:
                a.fill("#alignSearch", query)
                a.wait_for_function(f"() => document.querySelectorAll('#alignRows .align-row').length === {hits}", timeout=5000)
                a.click("#alignRows .align-row")

            def offset_of(page, track) -> dict:
                return page.evaluate(f"() => {DBG}.align[{track['id']!r}] || null")

            seek_room(40)
            a.click(f"#offsetRows [data-slot=primary] .align-open")
            a.wait_for_function("() => !document.querySelector('#alignPane').hidden && document.querySelectorAll('#alignRows .align-row').length > 5",
                                timeout=10000)
            panel = a.evaluate("""() => { const box = document.querySelector('#chatBox');
              return {parent: box.parentNode.id, hidden: box.hidden, tabs: !document.querySelector('#chatTabs').hidden,
                chatHidden: getComputedStyle(document.querySelector('#chatLog')).display === 'none',
                title: document.querySelector('#alignTitle').textContent,
                now: (document.querySelector('#alignRows .align-row.now .align-text') || {}).textContent}; }""")
            check("Hizala opens the panel in the chat's column beside the film, as its second tab, the line of now lit",
                  panel["parent"] == "chatDock" and not panel["hidden"] and panel["tabs"] and panel["chatHidden"]
                  and panel["title"].startswith("Ana altyazı · Türkçe") and panel["now"] == "Polis arabası köşeyi döndü.", str(panel))
            rows = a.evaluate("() => document.querySelectorAll('#alignRows .align-row').length")
            check("a long subtitle puts only the rows around the visible ones in the page",
                  0 < rows < len(LATE_LINES), f"{rows} of {len(LATE_LINES)}")

            # A short, repeated line: it is used, but the panel says to pick a better one.
            tap_line("evet", 2)
            note = a.inner_text("#alignNote")
            check("a short, repeated line gets a hint to pick a more distinctive one",
                  "ayırt edici" in note and a.evaluate("() => document.querySelector('#alignNote').classList.contains('warn')"), note)
            a.click("#alignReset")
            check("Sıfırla takes the subtitle's alignment away", offset_of(a, late) is None)

            # Way 1: find the line, tap it when it is heard (the room is at 40 s, the line says 45 s).
            tap_line("KLAUS")
            got = offset_of(a, late)
            check("search finds the line whatever the case; tapped at 40 s, the subtitle is 5 s earlier",
                  got and abs(got["offset"] + 5000) <= 250 and got["scale"] == 1, str(got))
            seek_room(41)
            a.wait_for_function("() => document.querySelector('#subPrimary').textContent.includes('Klaus')", timeout=5000)
            other = b.evaluate("() => document.querySelector('#subPrimary').textContent")
            check("the line now shows on the film when it is heard; the other window keeps its own timing",
                  "Klaus" not in other and offset_of(b, late) is None, other)
            out = a.inner_text("#offsetRows [data-slot=primary] output")
            check("the card's offset shows the panel's result", out == "-5,0 s", out)

            # Way 2: "Şimdi duydum" at 70 s, the line picked later (at 100 s): the mark's time counts.
            a.click("#alignReset")
            seek_room(70)
            a.click("#alignMark")
            check("the mark is shown", a.is_visible("#alignMarkInfo") and "1:10" in a.inner_text("#alignMarkInfo"))
            seek_room(100)
            tap_line("postaci")  # postacı: ı and i are the same letter for the search
            got = offset_of(a, late)
            check("a line picked after Şimdi duydum takes the mark's time, not the tap's",
                  got and abs(got["offset"] + 5000) <= 250, str(got))
            a.click("#alignNow")
            a.wait_for_function("() => !document.querySelector('#alignSearch').value && document.querySelector('#alignNow').hidden", timeout=3000)
            now_line = a.evaluate("""() => { const n = document.querySelector('#alignRows .align-row.now');
              const l = document.querySelector('#alignList').getBoundingClientRect(); if (!n) return null;
              const r = n.getBoundingClientRect(); return {text: n.querySelector('.align-text').textContent, mid: (r.top + r.bottom) / 2 - l.top,
                want: Math.min(l.height / 2, Number(n.dataset.i) * 46 + 23)}; }""")
            check("Şimdiye dön brings back the whole list, following the line of now in its middle",
                  now_line and now_line["text"] == "Öğle yemeği soğudu." and abs(now_line["mid"] - now_line["want"]) < 30, str(now_line))
            a.mouse.move(*center(a, "#alignList"))
            a.mouse.wheel(0, 600)
            a.wait_for_selector("#alignNow", state="visible", timeout=3000)
            check("scrolling the list by hand stops the following", True)

            # Two points: a subtitle made for 25 frames a second on a 23,976 film.
            title_before = a.inner_text("#alignTitle")
            a.select_option("#primarySel", pal["id"])
            a.wait_for_function(f"() => document.querySelector('#alignTitle').textContent !== {title_before!r}", timeout=5000)
            seek_room(60)
            tap_line("zeynep")
            first = offset_of(a, pal)
            note1 = a.inner_text("#alignNote")
            seek_room(1260)
            tap_line("SEBNEM")  # Şebnem
            second = offset_of(a, pal)
            note2 = a.inner_text("#alignNote")
            state = a.inner_text("#alignState")
            check("one point moves the subtitle and asks for a second one 10 minutes away",
                  first and first["scale"] == 1 and abs(first["offset"] - 2458) <= 250 and "10 dakika" in note1, f"{first} {note1}")
            check("a second point far away finds the speed, snapped to 25 → 23,976",
                  second and abs(second["scale"] - 25 / 23.976) < 1e-9 and abs(second["offset"]) <= 250
                  and "Hız farkı düzeltildi: 25 → 23,976" in note2 and "25 → 23,976" in state, f"{second} {note2} {state}")
            seek_room(1401)
            a.wait_for_function("() => document.querySelector('#subPrimary').textContent.includes('Ölçü tamam')", timeout=5000)
            check("the last line, far from both points, shows when it is heard", True)
            check("the other window has no alignment at all",
                  offset_of(b, late) is None and offset_of(b, pal) is None)

            # The sums themselves, with several point sets.
            sums = a.evaluate(f"""() => {{ const d = window.cowatchDebug, f = d.fitAlignment, add = d.addAlignPoint;
              const pal = 23.976 / 25;
              return {{
                none: f([]),
                one: f([{{s: 45, t: 40}}]),
                oneKeeps: f([{{s: 45, t: 40}}], 25 / 23.976),
                near: f([{{s: 100, t: 90}}, {{s: 400, t: 402}}]),
                pal: f([{{s: 60 * pal, t: 60}}, {{s: 1260 * pal, t: 1260.4}}]),
                ntsc: f([{{s: 100, t: 100 * 24 / 25 + 3}}, {{s: 2000, t: 2000 * 24 / 25 + 3}}]),
                same: f([{{s: 100, t: 102}}, {{s: 2000, t: 2002.3}}]),
                odd: f([{{s: 100, t: 100}}, {{s: 1100, t: 1120}}]),
                bad: f([{{s: 100, t: 100}}, {{s: 1100, t: 400}}]),
                third: add([{{s: 100, t: 1}}, {{s: 2000, t: 2}}], {{s: 1900, t: 3}}).map(p => p.s),
                close: add([{{s: 100, t: 1}}], {{s: 300, t: 2}}).map(p => p.s),
                far: add([{{s: 100, t: 1}}], {{s: 900, t: 2}}).map(p => p.s),
              }}; }}""")
            ok = (sums["none"]["offset"] == 0 and sums["none"]["scale"] == 1
                  and sums["one"]["offset"] == -5000 and sums["one"]["scale"] == 1
                  and abs(sums["oneKeeps"]["scale"] - 25 / 23.976) < 1e-12 and sums["oneKeeps"]["points"] == 1
                  and sums["near"]["points"] == 1 and sums["near"]["offset"] == 2000
                  and sums["pal"]["fps"] == [25, 23.976] and abs(sums["pal"]["offset"]) <= 250 and not sums["pal"]["unusual"]
                  and sums["ntsc"]["fps"] == [24, 25] and abs(sums["ntsc"]["offset"] - 3000) <= 1
                  and sums["same"]["scale"] == 1 and sums["same"]["fps"] is None and not sums["same"]["unusual"]
                  and sums["odd"]["unusual"] and abs(sums["odd"]["scale"] - 1.02) < 1e-9
                  and sums["bad"]["bad"] and sums["bad"]["points"] == 1
                  and sums["third"] == [100, 1900] and sums["close"] == [300] and sums["far"] == [100, 900])
            check("fitAlignment: one point, two points, frame-rate snapping, odd and wrong pairs; a third point replaces the nearer",
                  ok, str(sums))

            # It stays after reloading the page.
            a.reload()
            a.click("#joinForm button[type=submit]")
            a.wait_for_function(f"() => {DBG}.primary && {DBG}.tracks.length === 2", timeout=20000)
            a.select_option("#primarySel", pal["id"])
            out = a.inner_text("#offsetRows [data-slot=primary] output")
            kept = offset_of(a, pal)
            check("after reloading, the subtitle keeps its offset and speed",
                  kept and abs(kept["scale"] - 25 / 23.976) < 1e-9 and "25 → 23,976" in out, f"{kept} {out}")

            # A first anchor that falls at 0.0 s offset must still keep its point for the second match.
            a.wait_for_function("() => document.querySelector('#video').readyState >= 2", timeout=20000)
            seek_room(60)
            t0 = a.evaluate(f"() => Math.round({DBG}.filmTime * 1000) / 1000")
            zero = upload_subtitle(a, "zero.srt", srt([
                (t0, "Sıfır noktası: tam burada."),
                (t0 + 700 * 23.976 / 25, "Uzak nokta: hız burada ölçülür."),
            ]))
            a.wait_for_function(f"() => {DBG}.tracks.some(t => t.id === {zero['id']!r})", timeout=5000)
            a.select_option("#primarySel", zero["id"])
            a.click("#offsetRows [data-slot=primary] .align-open")
            a.wait_for_function(f"() => document.querySelectorAll('#alignRows .align-row').length >= 2", timeout=5000)
            tap_line("Sıfır noktası")
            z1 = offset_of(a, zero)
            seek_room(t0 + 700)
            tap_line("Uzak nokta")
            z2 = offset_of(a, zero)
            check("a first match at 0 ms offset keeps its anchor point so a later point finds the speed",
                  z1 and z1["offset"] == 0 and len(z1.get("pts") or []) == 1
                  and z2 and abs(z2["scale"] - 25 / 23.976) < 1e-9, f"z1={z1} z2={z2}")

            # On a phone held upright the panel is the box under the film, and stays inside its box across mobile sizes.
            b.set_viewport_size({"width": 390, "height": 844})
            b.evaluate("() => window.scrollTo(0, 0)")
            b.click("#offsetRows [data-slot=primary] .align-open")
            b.wait_for_function("() => !document.querySelector('#alignPane').hidden", timeout=5000)
            phone = b.evaluate("""() => { const box = document.querySelector('#chatBox'), s = document.querySelector('#stage');
              return {parent: box.parentNode.id, under: box.getBoundingClientRect().top >= s.getBoundingClientRect().bottom - 1,
                width: box.getBoundingClientRect().width}; }""")
            check("on a phone held upright the panel is in the box under the film",
                  phone["parent"] == "chatDock" and phone["under"] and phone["width"] > 300, str(phone))
            for label, vw, vh, fill in [
                ("390x667 docked", 390, 667, False),
                ("844x390 landscape", 844, 390, False),
                ("844x390 fill", 844, 390, True),
            ]:
                b.set_viewport_size({"width": vw, "height": vh})
                b.evaluate(f"""() => {{
                  const s = document.querySelector('#stage');
                  s.classList.toggle('fill', {str(fill).lower()});
                  document.dispatchEvent(new Event('fullscreenchange'));
                  document.querySelector('#stageWrap').scrollIntoView({{ block: 'start' }});
                }}""")
                b.wait_for_timeout(150)
                fit = b.evaluate("""() => {
                  const box = document.querySelector('#chatBox'), done = document.querySelector('#alignDone');
                  const cb = box.getBoundingClientRect(), db = done.getBoundingClientRect();
                  const cx = db.left + db.width / 2, cy = db.top + db.height / 2;
                  const hit = cy >= 0 && cy < window.innerHeight ? document.elementFromPoint(cx, cy) : null;
                  return {
                    inBox: db.top >= cb.top - 1 && db.bottom <= cb.bottom + 1,
                    inView: db.top >= 0 && db.bottom <= window.innerHeight + 1,
                    clickable: !!(hit && (hit === done || done.contains(hit))),
                    cb: {top: Math.round(cb.top), bottom: Math.round(cb.bottom)},
                    db: {top: Math.round(db.top), bottom: Math.round(db.bottom)},
                  };
                }""")
                check(f"align panel fits inside its box with reachable Bitti button ({label})",
                      fit["inBox"] and fit["inView"] and fit["clickable"], str(fit))
            b.evaluate("() => { document.querySelector('#stage').classList.remove('fill'); document.dispatchEvent(new Event('fullscreenchange')); }")
            b.set_viewport_size({"width": 390, "height": 844})
            b.wait_for_timeout(150)
            b.click("#chatTabChat")
            b.wait_for_function("() => document.querySelector('#alignPane').hidden && !document.querySelector('#chatLog').hidden"
                                " && getComputedStyle(document.querySelector('#chatForm')).display !== 'none'", timeout=3000)
            b.click("#chatTabAlign")
            b.wait_for_function("() => !document.querySelector('#alignPane').hidden", timeout=3000)
            b.click("#alignDone")
            b.wait_for_function("() => document.querySelector('#alignPane').hidden && document.querySelector('#chatTabs').hidden", timeout=3000)
            check("the tabs go between the chat and the panel; Bitti leaves the chat as it was", True)

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
