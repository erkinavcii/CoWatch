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
copy .env.example .env      # optional: settings and OpenSubtitles key
.\.venv\Scripts\python run.py
```

Python packages go into the project's `.venv` folder. `npm.cmd` instead of `npm` avoids PowerShell's script execution policy. If `py` is not available, use `python` in the first line. On macOS/Linux: `pip install -r requirements.txt`, `cd torrent-helper && npm install && cd ..`, `python3 run.py`.

`run.py` prints two links (its console messages are in Turkish):

```
Bu bilgisayardan:  http://localhost:8000/?k=KEY     <- this computer
Tailscale linki:   http://100.x.y.z:8000/?k=KEY     <- send this one to your friend
```

The key in the link is the room's password; the browser stores it as a cookie on first visit. It lives in `data/access_key.txt`; delete that file to generate a new key, and old links stop working.

On first run, Windows asks for firewall permission; allow Python. If your friend cannot connect through the Tailscale link, allow it on public networks too: Windows can list the Tailscale connection as a public network.

**For your friend:** they install Tailscale, and you share this computer with them from the Tailscale admin console (or invite them to your tailnet). Then they open the link, type their name and press "Join".

## Usage

1. **Open a film:** for your own file, type its full path into "File path on this computer" (for security, this field only appears on the host computer). For a torrent, paste the magnet link and press "Add torrent"; if it holds several videos, pick one from the list.
2. **Add subtitles:** under "Add subtitles", search OpenSubtitles by language codes (e.g. `tr,en,ru`) or upload an `.srt/.ass/.vtt` file. Old encodings such as Turkish `cp1254` and Russian `cp1251` are fixed automatically.
3. **Pick your own subtitles:** everyone sets their own main and second subtitle, timing offset, text size and height. Preferred languages are remembered, so in a new film a subtitle in that language is selected automatically.
4. **Shortcuts:** space play/pause, ← → 10 s, `f` fullscreen, `m` mute. On touch screens, tapping the video only shows the controls; pausing for everyone takes the button.

The interface is available in Turkish, English and Russian.

## Quick test

On one computer, with two browser windows:

1. In the project folder, generate a test video. It runs for 2 minutes, shows the current second as a big number, and like torrent files it has H.264 video and AC3 5.1 audio:
   ```powershell
   ffmpeg -f lavfi -i testsrc=size=1280x720:rate=24 -f lavfi -i "sine=frequency=440" -t 120 -c:v libx264 -g 48 -pix_fmt yuv420p -af volume=0.1 -c:a ac3 -ac 6 samples\test-video.mkv
   ```
2. Start with `.\.venv\Scripts\python run.py`, open the "Bu bilgisayardan" (this computer) link, type your name and press Join.
3. Paste the full path of `samples\test-video.mkv` into "File path on this computer". In File Explorer you can right-click the file and choose "Copy as path"; the quotes are fine.
4. Open the same link in a private window and join under another name.
5. Under "Add subtitles", upload `samples\test.tr.srt` with language `tr` in the first window and `samples\test.ru.srt` with `ru` in the second. Both use old encodings (cp1254 and cp1251); Turkish and Russian letters should show correctly.
6. Press play. The second in the subtitle should match the big number on screen, and both windows should stay on the same frame. Try seeking, pausing and the ±0.5 offset.

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

Multiply by two for two viewers. With a slow upload, set `MAX_COPY_KBPS` in `.env` (e.g. `6000`): heavier files are then converted automatically. Videos that are not H.264 (HEVC/x265, 10-bit) are always converted. With a graphics card, `VIDEO_ENCODER=h264_nvenc` (NVIDIA), `h264_qsv` (Intel) or `h264_amf` (AMD) takes the load off the CPU.

## Settings (.env)

| Variable | Default | Description |
|---|---|---|
| `PORT` | 8000 | Web server port |
| `TORRENT_UPLOAD_LIMIT` | 64 | Torrent upload limit (KB/s), 0 = unlimited |
| `MAX_COPY_KBPS` | 0 | H.264 files above this are converted, 0 = always original |
| `TRANSCODE_KBPS` | 5000 | Target bitrate of a converted stream |
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

Co-Watch does not provide, search for or distribute any content. It is made for your own files or content you have the right to watch and share. Torrent support is for the protocol itself; using torrents for copyrighted content makes your IP address visible in the swarm, and you upload while you watch. Users are responsible for how they use it.

## Development

```bash
pip install pytest
python -m pytest            # media tests run too when ffmpeg is installed
```

In the browser console, `cowatchDebug()` shows the sync values (film time, expected position, drift).

Layout: `server/` (FastAPI: room, sync, media, subtitles), `torrent-helper/` (Node: magnet → HTTP stream), `web/` (client; hls.js lives in `web/vendor`, Apache-2.0).

## Next phases

2. Subtitle automation: language-preference fallback chain, alignment with alass, two-pass LLM translation.
3. Joining with just a link (DataChannel + TURN), automatic conversion when the bitrate does not fit.
4. Laser drawing, camera and voice chat.
5. Two-sided torrent sync and an extension for DRM platforms.

## License

[GNU AGPL v3.0](LICENSE) or later. In short: you can use, modify and share it; if you offer a modified version to others over a network, you have to share its source code with them too. That is why the app's join screen links to the source code.

`web/vendor/hls.light.min.js`: [hls.js](https://github.com/video-dev/hls.js), Apache-2.0 (`web/vendor/hls.js.LICENSE`).
