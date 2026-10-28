# CoWatch: Claude için çalışma notları

Bu dosya, Claude Code oturumlarının projeyi hızla tanıması için. Uygulamanın ne olduğu ve nasıl kurulduğu README'de ([EN](README.md) · [TR](README.tr.md)); burada geliştirirken gereken kurallar, bilinen tuzaklar ve sıradaki iş var.

## Kurallar

- **Commit kimliği:** author ve committer `erkinavcii <56629073+erkinavcii@users.noreply.github.com>`. Commit mesajına `Co-Authored-By`, Claude imzası ya da oturum linki ekleme. Mesajlar Türkçe ve önceki commit'lerin üslubunda: kısa bir başlık, gerekirse madde madde ayrıntı.
- **Commit'ten önce testler:** `.\.venv\Scripts\python -m pytest -q` (şu an 36 test; ffmpeg kuruluysa medya testleri de çalışır).
- **İki README birlikte güncellenir:** `README.md` (İngilizce) ve `README.tr.md` (Türkçe) aynı içeriği taşır.
- **Arayüz metinleri üç dilde:** `web/i18n.js` içindeki `tr`, `en` ve `ru` anahtarları birebir aynı olmalı.
- `data/`, `.venv/`, `node_modules/` ve `samples/*.mkv` git'e girmez (`.gitignore`).

## Windows'ta çalıştırma

```powershell
py -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt pytest
cd torrent-helper; npm.cmd install; cd ..
.\.venv\Scripts\python run.py
```

- PowerShell `npm.ps1`'i engelliyor; `npm` yerine `npm.cmd` kullan.
- Test videosu komutu ve iki pencereli deneme adımları README'nin "Hızlı deneme" bölümünde.
- Çalışan sunucu kodu hafızada tutar: Python tarafında değişiklik varsa `run.py` yeniden başlatılır.

## Kod haritası

| Yer | Ne yapar |
| --- | --- |
| `server/main.py` | FastAPI uygulaması: WebSocket mesajları (`Controller.handle`), API, erişim anahtarı, HLS dosyaları |
| `server/room.py` | Oda durumu ve senkron kuralları; oynatma durumunun tek doğru kaynağı sunucu |
| `server/media.py` | ffprobe, kopya ya da dönüştürme kararı, ffmpeg ile HLS (fMP4) üretimi |
| `server/presence.py` | İmleç, dürtme ve çizim mesajlarının doğrulanması, renk paleti |
| `server/subtitles.py` | Altyazı çözme (cp1254, cp1251 gibi eski kodlamalar), OpenSubtitles, saklama |
| `server/oshash.py`, `server/torrent_client.py` | OpenSubtitles hash'i; Node torrent yardımcısıyla konuşma |
| `torrent-helper/index.mjs` | webtorrent: magnet linkinden HTTP Range akışı |
| `web/app.js` | İstemci: senkron, altyazı çizimi, imleç topları, kalem |
| `tests/` | pytest testleri |

## Bilinen tuzaklar

- **ffmpeg çıktı yolları `/` ile verilir** (`media._ffmpeg_out`). HLS muxer `init.mp4`'ün klasörünü playlist yolundaki son `/` karakterinden buluyor; Windows'un `\` yolunda dosyayı çalışma klasörüne yazıyordu.
- **Film zamanı** = `video.currentTime + streamStart`. ffmpeg `-copyts` ile çalışır; akış yeniden başlatılınca ilk parçanın zamanı ölçülür.
- **İmleç ve çizim konumları** pencereye değil, video görüntüsüne göre orandır (0–1); `object-fit: contain`'in bıraktığı bantlar hesaba katılır.
- **İmleç ve çizim mesajları** sunucuda arka planda iletilir (`Controller._relay`); yavaş bir izleyici oynat/durdur komutlarını bekletmesin diye.
- **Yerel dosya açma** sadece loopback'ten gelen isteklere açık (`is_local`). Tailscale Serve istekleri de `127.0.0.1`'den getirdiği için bu kontrol `Host` başlığına ve `Tailscale-User-Login` / `X-Forwarded-For` başlıklarına da bakmalı (kamera-ses planı, 1. adım).
- **Statik dosyalar** `no-cache` ile sunulur; tarayıcı her açılışta yeni sürümü sorar.

## Durum (28 Ekim 2026)

- Faz 1 Windows'ta denendi: yerel dosya, iki pencerede senkron, kişiye özel altyazı (TR + EN).
- İmleç topu, dürtme sesi ve çizim eklendi; iki tarayıcı penceresiyle denendi.
- Henüz denenmedi: Windows'ta torrent (README'deki Sintel magnet'i) ve Tailscale üzerinden arkadaşla izleme. Tailscale bu bilgisayarda kurulu değil.
- Tarayıcı testi (`tests/e2e/two_viewers.py`) ilk oturumda yazıldı ama depoya girmedi; Playwright da kurulu değil. Kamera-ses planının 1. adımında yeniden yazılacak.

## Sıradaki iş: kamera ve ses

Plan: [docs/kamera-ses-plani.md](docs/kamera-ses-plani.md). Plandaki beş karar proje sahibinde; cevap gelmediyse önerilen varsayılanlarla ilerle. İlk adım HTTPS (Tailscale Serve), host kontrolünün düzeltilmesi ve tarayıcı testi.
