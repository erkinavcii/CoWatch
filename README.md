# Co-Watch

**English** · [Türkçe](README.tr.md)

Watch the same film at the same time with friends far away, while everyone picks their own subtitle language. You can watch with Turkish + English subtitles while your friend sees Russian + English.

Phase 1 (MVP): your own video file or a torrent → streamed in original quality (no re-encoding) → synced playback in everyone's browser + personal dual subtitles.

## How it works

```
local file ────────────────────────────────────┐
magnet ──> torrent helper (Node, webtorrent) ──┴──> ffmpeg (video copy, audio AAC stereo) ──> HLS
                                                                                               │
           Room + sync server (FastAPI, WebSocket) <──── play/pause/seek ──── browsers (hls.js)
```

- Everyone plays the same HLS stream in their own browser: no screen sharing, no quality loss.
- The server is the single source of truth: `playing`, `position`, `updatedAt`. A client that drifts more than 1 s seeks; between 0.1 and 1 s it catches up by changing playback speed by 5%.
- If someone stalls (buffering), the room waits where they stopped, and everyone continues together once they have at least 4 s buffered. A viewer stuck for more than 20 s no longer holds the room.
- Subtitles are never burned into the video: each browser draws its chosen subtitles against the film's clock (`film time = video.currentTime + streamStart`). Offset (±ms), size and height are personal.
- Subtitles are stored by the file's OpenSubtitles hash, so they are ready when the same film is opened again, whether from a torrent or a local file.
- Jumping to a part that is not prepared yet restarts ffmpeg from that point; the torrent downloads that part first.

## Requirements

| | Who | Note |
|---|---|---|
| Python 3.10+ | host | |
| Node.js 22+ | host | torrents only |
| ffmpeg + ffprobe | host | must be on PATH |
| Tailscale | host + viewers | the free personal plan is enough |
| A current browser | everyone | Chrome, Edge, Firefox, Safari |

Quick install on Windows (one command per line):

```powershell
winget install Python.Python.3.12
winget install OpenJS.NodeJS.LTS
winget install Gyan.FFmpeg
winget install Tailscale.Tailscale
```

## Setup

Windows (PowerShell, in the project folder):

```powershell
py -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
cd torrent-helper; npm.cmd install; cd ..
copy .env.example .env      # optional, for developers: settings normally go on the settings page
.\.venv\Scripts\python run.py
```

Python packages go into the project's `.venv` folder. `npm.cmd` instead of `npm` avoids PowerShell's script execution policy. If `py` is not available, use `python` in the first line. On macOS/Linux: `pip install -r requirements.txt`, `cd torrent-helper && npm install && cd ..`, `python3 run.py`.

`run.py` prints two links (its console messages are in Turkish):

```
Bu bilgisayardan:  http://localhost:8000/?k=KEY                  <- this computer
Arkadaşlar için:   https://pc.tail1234.ts.net/?k=KEY              <- send this one to your friend
```

The key in the link is the room's password; the browser stores it as a cookie on first visit. It lives in `data/access_key.txt`; "Make a new room key" under Settings → Advanced replaces it, and old links stop working.

**Share card and settings:** on the host computer the page shows a "Share" card: the friends' link with a Copy button and a QR code, and Tailscale's state with what to do about it (download it, open it, log in, allow Funnel, try again). Its "Settings" button sets how friends come in (Funnel, Serve or plain http), picture quality, film folders, who opens films, the OpenSubtitles account and, under Advanced, the port, the torrent upload limit, STUN servers and a new room key. They are kept in `data/settings.json`. Saving restarts the server for a few seconds (an open film closes; pages reconnect by themselves). A value set in `.env` wins and shows locked on the page. Only the host computer sees the card and the settings.

**HTTPS with Tailscale Serve:** when Tailscale is running, `run.py` starts `tailscale serve` and gives your friends an `https://….ts.net` link; browsers open the camera and microphone only on secure pages. Once, in the [Tailscale admin console](https://login.tailscale.com/admin/dns), turn on MagicDNS and HTTPS Certificates (if something is missing, `tailscale serve` prints a link to enable it). The computer's name ends up in public certificate logs, so rename it first if it contains personal details. Serve stops together with `run.py`. The server then listens only on this computer, so the old `http://100.x.y.z:8000` link no longer works. With "Plain http" under Settings (`TAILSCALE_SERVE=0` in `.env`), or without Tailscale, you get plain http links as before (and Windows asks for firewall permission for Python).

**For your friend:** they install Tailscale and you invite them to your tailnet from the Tailscale admin console (the free personal plan allows 6 users). Sharing only this computer is enough for the film, but then two friends cannot reach each other for camera and voice. Then they open the link, type their name and press "Join".

**Without Tailscale for your friend (Funnel):** with "Anyone with the link (Funnel)" under Settings (`TAILSCALE_FUNNEL=1` in `.env`), `run.py` starts `tailscale funnel` instead: the same `https://….ts.net` link, but open to the whole internet, so your friend needs only a browser. The first time, `tailscale funnel` prints a link to allow Funnel for this computer; the Share card shows it as an "Allow" button. The key in the link is then the room's only lock, so send it only to the people you watch with. Voice and camera then find their way through home routers with Cloudflare's free STUN server; on some networks (strict company or mobile networks) they may still not connect. The film goes through Tailscale's relay servers, which have a bandwidth limit Tailscale does not publish. In one measurement about 7–8 Mbps reached a viewer through Funnel while the home upload itself had about 30 Mbps, so files up to about 5–6 Mbps play comfortably. With picture quality on "Automatic" (the default), heavier files are therefore converted to 4.5 Mbps on Funnel (see "Upload speed").

## Usage

1. **Open a film:** for your own file, press "Browse…" and pick it in the file dialog that opens on the host computer, or type its full path into "File path on this computer" and press "Open file" (for security, both only appear on the host computer). With a film folder set (Settings → Film folders, or `LIBRARY_DIRS` in `.env`), its videos are listed under "Film folder" with a search box; one click opens one. For a torrent, paste the magnet link and press "Add torrent"; if it holds several videos, pick one from the list.
2. **Browse:** the "Browse" card shows catalogs from [Stremio add-ons](https://github.com/Stremio/stremio-addon-sdk/blob/master/docs/protocol.md): posters, search, seasons and episodes, and the sources the add-ons know for a film or episode. "Open" plays a source for everyone. Two add-ons that host no content come built in: Cinemeta (catalogs and details) and Public Domain Movies (films out of copyright). The host can add other add-ons by their `…/manifest.json` address under "Add-ons"; they are kept only on that computer, in `data/addons.json`. For a film opened from an add-on, "Search the add-ons" under "Add subtitles" lists the subtitles those add-ons offer, matched by the film's id and file hash.
3. **Add subtitles:** under "Add subtitles", search OpenSubtitles by language codes (e.g. `tr,en,ru`) or upload an `.srt/.ass/.vtt` file. Old encodings such as Turkish `cp1254` and Russian `cp1251` are fixed automatically.
4. **Pick your own subtitles:** uploaded subtitles go to everyone's list, but each viewer picks what shows on their own screen. The "main subtitle" is the large white line at the bottom. The "second subtitle" is optional and shows as a smaller yellow line above it, for watching in two languages at once (you TR + EN, your friend RU + EN). Timing offset, text size and height are personal too. Preferred languages are remembered, so in a new film a subtitle in that language is selected automatically.
5. **Pointers and pokes:** everyone's pointer shows over the video as a ball with eyes, their name and their colour (it fades after 4 s without movement). Clicking the video makes your ball blink, sends out a ring and plays a short sound for everyone, pitched by colour. The bell on the right turns the sound off. Clicking the video does not pause the film; use space or the button.
6. **Drawing:** draw on the video for everyone with the pen on the right (`d`); strokes appear live and land on the same spot of the film whatever the screen size. While the film plays, strokes fade after a few seconds; while it is paused, they stay. The colour button changes your colour (ball and pen), the bin clears everyone's drawings.
7. **Voice:** the microphone button next to the time (`Ctrl+D`) turns your microphone on and off; it starts off, and red means off. The sound goes straight to the others, not through the server. Off really releases the microphone (the red dot on the tab goes away), and a crossed-out microphone shows next to your name. Whoever talks glows in their colour, at the top and on their ball, and the film gets quieter for a moment. The arrow next to the button picks the microphone and turns that off. Click someone's name at the top to set how loud you hear them. Use headphones until echo has been tested with speakers. Friends need the HTTPS link (see Setup); browsers do not open the microphone over plain http.
8. **Camera:** the camera button (`Ctrl+E`) works the same way; off turns the camera light off. While anyone's camera is on, small tiles appear over the top right of the video, without shrinking the film: the picture of those with their camera on, the coloured ball of the others, your own picture mirrored at the bottom. They stay in fullscreen; on a phone they line up along the top. The arrow next to the button picks the camera and hides your own tile or all tiles. Clicking a tile sets that person's volume. Drag the tiles to any corner; the small button on their corner makes them smaller. A camera sends at most about 0.5 Mbps to each viewer.
9. **Before joining:** the join screen has the same microphone and camera buttons with a preview and a level meter, as in Meet; whatever is on there is on when you join. Both start off.
10. **Trusting a friend:** the host can click a friend's name at the top and press "Let them open the film folder". The friend then sees the "Film folder" list too and can open films from it for everyone, but cannot type paths, reach other files on the disk or change the add-ons. A small "trusted" label shows next to their name; "Take it back" in the same place ends it. The trust belongs to the friend's browser, so it survives a dropped connection, and lasts until the app restarts. Anyone with the link can open torrents and add-on sources and close the film; with "Only you and the friends you trust" under Settings (`MEDIA_CONTROL=trusted` in `.env`), only the host and trusted friends can.
11. **Screen sharing:** the screen button next to the camera shares a window, a browser tab or the whole screen, with its sound when the browser offers it (Chrome and Edge on Windows). The shared screen covers the film for everyone and the film pauses until the share ends; pointers and the pen work on it too. One screen at a time. The host and trusted friends share at once; anyone else first picks what to share, then waits while the host (or a trusted friend) sees "… wants to share their screen" with "Allow" and "Decline". Nothing is sent before that, and without an answer the request lapses after 30 seconds. If someone is already sharing, allowing a new share ends theirs. The host can stop anyone's share from their name at the top. The picture goes straight to the others, like the camera, at up to about 4 Mbps per viewer; DRM-protected sites (Netflix and the like) show black in a share.
12. **Connection drops:** the page reconnects to the room by itself, and voice and camera connections that drop (Wi-Fi change, laptop sleep) are rebuilt by themselves.
13. **Shortcuts:** space play/pause, ← → 10 s, `f` fullscreen, `m` mute the film, `d` pen, `Ctrl+D` microphone, `Ctrl+E` camera, `Esc` pen off. On touch screens, tapping the video only shows the controls; pausing for everyone takes the button.

The interface is available in Turkish, English and Russian.

## Quick test

On one computer, with two browser windows:

1. In the project folder, generate a test video. It runs for 2 minutes, shows the current second as a big number, and like torrent files it has H.264 video and AC3 5.1 audio:
   ```powershell
   ffmpeg -f lavfi -i testsrc=size=1280x720:rate=24 -f lavfi -i "sine=frequency=440" -t 120 -c:v libx264 -g 48 -pix_fmt yuv420p -af volume=0.1 -c:a ac3 -ac 6 samples\test-video.mkv
   ```
2. Start with `.\.venv\Scripts\python run.py`, open the "Bu bilgisayardan" (this computer) link, type your name and press Join.
3. Press "Browse…" and pick `samples\test-video.mkv`, or paste its full path into "File path on this computer". In File Explorer you can right-click the file and choose "Copy as path"; the quotes are fine.
4. Open the same link in a private window and join under another name.
5. Under "Add subtitles", upload `samples\test.tr.srt` with language `tr` in the first window and `samples\test.ru.srt` with `ru` in the second. Both use old encodings (cp1254 and cp1251); Turkish and Russian letters should show correctly.
6. Press play. The second in the subtitle should match the big number on screen, and both windows should stay on the same frame. Try seeking, pausing and the ±0.5 offset.
7. Move the mouse over the video in one window: the other window shows a ball with your name and colour. Click: the ball blinks and both windows play a sound. Press `d` and draw; the stroke appears at the same spot in the other window.

For a real torrent, use Sintel, the Blender Foundation's openly licensed (CC BY) film:

```
magnet:?xt=urn:btih:08ada5a7a6183aae1e09d831df6748d566095a10&dn=Sintel&tr=udp%3A%2F%2Fexplodie.org%3A6969&tr=udp%3A%2F%2Ftracker.coppersurfer.tk%3A6969&tr=udp%3A%2F%2Ftracker.empire-js.us%3A1337&tr=udp%3A%2F%2Ftracker.leechers-paradise.org%3A6969&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337&tr=wss%3A%2F%2Ftracker.btorrent.xyz&tr=wss%3A%2F%2Ftracker.fastcast.nz&tr=wss%3A%2F%2Ftracker.openwebtorrent.com&ws=https%3A%2F%2Fwebtorrent.io%2Ftorrents%2F&xs=https%3A%2F%2Fwebtorrent.io%2Ftorrents%2Fsintel.torrent
```

## Upload speed (per viewer)

Required upload ≈ the file's bitrate × 1.3. If you don't know the bitrate: for a 2-hour film, file size in GB × 1.1 ≈ Mbps.

| Source | Bitrate | Comfortable upload |
|---|---|---|
| Compact 1080p (2-hour film, 2-3 GB) | 2.5-3.5 Mbps | 5 Mbps |
| 1080p WEB-DL (4-7 GB) | 5-8 Mbps | 8-10 Mbps |
| 1080p BluRay encode (8-12 GB) | 9-14 Mbps | 15+ Mbps or convert |
| Phone recording (1080p) | ~15-20 Mbps | convert |
| Converted stream (`TRANSCODE_KBPS=5000`) | 5 Mbps | 8 Mbps |

Multiply by two for two viewers. With a slow upload, choose "Limit by hand" under Settings → Picture quality (e.g. 6 Mbps; `MAX_COPY_KBPS=6000` in `.env`): heavier files are then converted automatically. Videos that are not H.264 (HEVC/x265, 10-bit) are always converted. With a graphics card, `VIDEO_ENCODER=h264_nvenc` (NVIDIA), `h264_qsv` (Intel) or `h264_amf` (AMD) takes the load off the CPU.

## Settings (.env)

Most of these are on the settings page. `.env` is for developers and for the rest; a variable set there wins over the page.

| Variable | Default | Description |
|---|---|---|
| `PORT` | 8000 | Web server port |
| `TAILSCALE_SERVE` | 1 | HTTPS link through Tailscale Serve when Tailscale is running, 0 = plain http links |
| `TAILSCALE_FUNNEL` | 0 | 1 = the HTTPS link through Tailscale Funnel, open to the internet: friends need no Tailscale |
| `LIBRARY_DIRS` | – | Film folders, separated by `;` (e.g. `D:\Films;E:\Series`): their videos are listed under "Film folder" for the host and trusted friends |
| `MEDIA_CONTROL` | everyone | `trusted` = only the host and trusted friends open and close films |
| `ADDONS_BUILTIN` | 1 | 0 = without the built-in add-ons (Cinemeta, Public Domain Movies), only the ones added by hand |
| `ICE_SERVERS` | – | Comma-separated `stun:` addresses for voice and camera; empty = only the viewers' own addresses (through Tailscale), or Cloudflare's STUN with Funnel |
| `TORRENT_UPLOAD_LIMIT` | 64 | Torrent upload limit (KB/s), 0 = unlimited |
| `MAX_COPY_KBPS` | 0 (5500 on Funnel) | H.264 files above this are converted, 0 = always original |
| `TRANSCODE_KBPS` | 5000 (4500 on Funnel) | Target bitrate of a converted stream |
| `VIDEO_ENCODER` | libx264 | Encoder used for conversion |
| `MAX_HEIGHT` | 1080 | Maximum height when converting |
| `AUDIO_FILTER` | dynaudnorm | Evens out loud and quiet parts; leave empty to turn off |
| `OPENSUBTITLES_API_KEY` | – | Get one at [opensubtitles.com/consumers](https://www.opensubtitles.com/consumers) |
| `OPENSUBTITLES_USERNAME` / `_PASSWORD` | – | A free account allows about 20 subtitle downloads a day |

Once ffmpeg is more than 10 minutes ahead of playback, the torrent download slows down by itself, so it does not compete with the stream going to your friend on the same connection.

## Known limitations

- One room, one film. The room is protected by the link key.
- HDR videos look washed out once converted (no tone mapping).
- On iPhone, subtitles do not show in fullscreen (Safari can only make the video itself fullscreen); watch in landscape without fullscreen.
- DRM platforms (Netflix etc.) are not supported in this mode; a browser extension for them is on the roadmap.
- `data/torrents` grows with downloaded films; clean it up by hand.

## Legal note

Co-Watch does not provide, host or distribute any content. It is made for your own files or content you have the right to watch and share. Torrent support is for the protocol itself; using torrents for copyrighted content makes your IP address visible in the swarm, and you upload while you watch. Co-Watch speaks the Stremio add-on protocol; the only add-ons it ships with host no content (Cinemeta for catalogs and details, Public Domain Movies for films out of copyright). Which other add-ons you add is your own choice and responsibility. Users are responsible for how they use it.

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest                      # media tests run too when ffmpeg is installed
python -m playwright install chromium # once, for the browser tests
python tests/e2e/two_viewers.py       # sync, subtitles, pointers, pokes, pen; --headed to watch
python tests/e2e/voice_camera.py      # voice and camera
```

Each browser test starts its own server and test video and opens Chromium windows. `two_viewers.py` checks sync, each viewer's own subtitles, that a pointer lands on the same spot of a letterboxed picture on another screen size, poke sounds, the pen and clearing. `voice_camera.py` joins as a friend coming through Tailscale Serve and checks voice, the camera tiles, a third viewer joining from the preview, and connections rebuilding themselves (with Chromium's fake camera, and synthesised speech as the microphone).

In the browser console, `cowatchDebug()` shows the sync values (film time, expected position, drift).

Layout: `server/` (FastAPI: room, sync, media, subtitles, pointers and drawing, voice and camera signalling, add-ons), `torrent-helper/` (Node: magnet → HTTP stream), `web/` (client; hls.js and the QR code generator live in `web/vendor`).

## Next phases

2. Subtitle automation: language-preference fallback chain, alignment with alass, two-pass LLM translation.
3. Joining with just a link (DataChannel + TURN), automatic conversion when the bitrate does not fit.
4. Voice and camera are in; to try with real devices: echo with speakers, phones, two computers over Tailscale.
5. Two-sided torrent sync and an extension for DRM platforms.

## License

[GNU AGPL v3.0](LICENSE) or later. In short: you can use, modify and share it; if you offer a modified version to others over a network, you have to share its source code with them too. That is why the app's join screen links to the source code.

`web/vendor/hls.light.min.js`: [hls.js](https://github.com/video-dev/hls.js), Apache-2.0 (`web/vendor/hls.js.LICENSE`).
`web/vendor/qrcode.js`: [qrcode-generator](https://github.com/kazuhikoarase/qrcode-generator), MIT (`web/vendor/qrcode.js.LICENSE`).
