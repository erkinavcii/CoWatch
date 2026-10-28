# CoWatch: Claude için çalışma notları

Bu dosya, Claude Code oturumlarının projeyi hızla tanıması için. Uygulamanın ne olduğu ve nasıl kurulduğu README'de ([EN](README.md) · [TR](README.tr.md)); burada geliştirirken gereken kurallar, bilinen tuzaklar ve sıradaki iş var.

## Kurallar

- **Commit kimliği:** author ve committer `erkinavcii <56629073+erkinavcii@users.noreply.github.com>`. Commit mesajına `Co-Authored-By`, Claude imzası ya da oturum linki ekleme. Mesajlar Türkçe ve önceki commit'lerin üslubunda: kısa bir başlık, gerekirse madde madde ayrıntı.
- **Commit'ten önce testler:** `.\.venv\Scripts\python -m pytest -q` (şu an 42 test; ffmpeg kuruluysa medya testleri de çalışır). Arayüzü ya da WebSocket mesajlarını değiştiren her adımdan sonra tarayıcı testi de: `.\.venv\Scripts\python tests\e2e\two_viewers.py` (izlemek için `--headed`; yaklaşık 1 dakika).
- **İki README birlikte güncellenir:** `README.md` (İngilizce) ve `README.tr.md` (Türkçe) aynı içeriği taşır.
- **Arayüz metinleri üç dilde:** `web/i18n.js` içindeki `tr`, `en` ve `ru` anahtarları birebir aynı olmalı.
- `data/`, `.venv/`, `node_modules/` ve `samples/*.mkv` git'e girmez (`.gitignore`).

## Windows'ta çalıştırma

```powershell
py -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m playwright install chromium
cd torrent-helper; npm.cmd install; cd ..
.\.venv\Scripts\python run.py
```

- PowerShell `npm.ps1`'i engelliyor; `npm` yerine `npm.cmd` kullan.
- Dosyaları PowerShell 5.1'in `Get-Content` / `Set-Content`'i ile düzenleme: BOM'suz UTF-8'i ANSI sanıp Türkçe ve Rusça harfleri bozuyor, yazarken BOM ekliyor. Edit aracı ya da Bash (`sed`) kullan.
- Test videosu komutu ve iki pencereli deneme adımları README'nin "Hızlı deneme" bölümünde.
- Çalışan sunucu kodu hafızada tutar: Python tarafında değişiklik varsa `run.py` yeniden başlatılır.

## Kod haritası

| Yer | Ne yapar |
| --- | --- |
| `server/main.py` | FastAPI uygulaması: WebSocket mesajları (`Controller.handle`), API, erişim anahtarı, HLS dosyaları |
| `server/room.py` | Oda durumu ve senkron kuralları; oynatma durumunun tek doğru kaynağı sunucu |
| `server/media.py` | ffprobe, kopya ya da dönüştürme kararı, ffmpeg ile HLS (fMP4) üretimi |
| `server/presence.py` | İmleç, dürtme ve çizim mesajlarının doğrulanması, renk paleti |
| `server/signaling.py` | Ses ve kamera için WebRTC sinyal mesajlarının (`rtc`) doğrulanması, `ICE_SERVERS` |
| `server/subtitles.py` | Altyazı çözme (cp1254, cp1251 gibi eski kodlamalar), OpenSubtitles, saklama |
| `server/oshash.py`, `server/torrent_client.py` | OpenSubtitles hash'i; Node torrent yardımcısıyla konuşma |
| `torrent-helper/index.mjs` | webtorrent: magnet linkinden HTTP Range akışı |
| `web/app.js` | İstemci: senkron, altyazı çizimi, imleç topları, kalem, ses ve kamera (eş bağlantıları, konuşan göstergesi, film sesini kısma, kamera kutuları) |
| `run.py` | Başlatıcı: torrent yardımcısı, Tailscale Serve (HTTPS linki), Uvicorn |
| `tests/` | pytest testleri |
| `tests/e2e/two_viewers.py` | İki Chromium penceresiyle uçtan uca test (Playwright, sahte kamera ve mikrofon); pytest'e girmez |

## Bilinen tuzaklar

- **ffmpeg çıktı yolları `/` ile verilir** (`media._ffmpeg_out`). HLS muxer `init.mp4`'ün klasörünü playlist yolundaki son `/` karakterinden buluyor; Windows'un `\` yolunda dosyayı çalışma klasörüne yazıyordu.
- **Film zamanı** = `video.currentTime + streamStart`. ffmpeg `-copyts` ile çalışır; akış yeniden başlatılınca ilk parçanın zamanı ölçülür.
- **İmleç ve çizim konumları** pencereye değil, video görüntüsüne göre orandır (0–1); `object-fit: contain`'in bıraktığı bantlar hesaba katılır.
- **İmleç ve çizim mesajları** sunucuda arka planda iletilir (`Controller._relay`); yavaş bir izleyici oynat/durdur komutlarını bekletmesin diye.
- **Yerel dosya açma** sadece host'a açık (`is_local`): loopback adresi, `Host` başlığı yerel bir ad ve vekil başlığı (`Tailscale-User-Login`, `X-Forwarded-For`, `Forwarded`) yok. Tailscale Serve istekleri de `127.0.0.1`'den getirdiği için tek başına adres yetmez. Tarayıcı testi misafiri bu başlıkla taklit eder.
- **Tailscale Serve** `run.py`'nin alt süreci olarak ön planda çalışır; `--bg` kullanma (yeniden başlatmalardan sonra da açık kalır). Serve açıkken `HOST` boşsa `127.0.0.1` olur, düz http linkleri yazılmaz.
- **Statik dosyalar** `no-cache` ile sunulur; tarayıcı her açılışta yeni sürümü sorar.
- **Eş bağlantıları:** kimliği küçük olan taraf teklif eder ve iki transceiver'ı (ses, görüntü) o ekler; diğeri teklifteki transceiver'ları `sendrecv` yapar. İki taraf da eklerse dört olur. Mikrofon ve kamera aç/kapa sadece `replaceTrack`; yeniden pazarlık yok. Gönderici sınırları (`SENDER_LIMITS`: kamera 500 kbps, 24 kare) bağlantı kurulunca `setParameters` ile verilir; öncesinde `encodings` boş.
- **Kamera kutuları** `#stage` içindeki `.side` sütununda, çizim araç çubuğunun üstünde; tam ekranda bu yüzden kalırlar. Biri kamerasını açınca görünürler (kapalı olanlar renkli topla). `isUi` kutuları da sayar: tıklamak dürtme değil, ses seviyesi.
- **WebSocket yeniden bağlanınca** sunucu yeni `clientId` verir; istemci `welcome`'da bütün eş bağlantılarını kapatır, `members` gelince yeniden kurar. Aynı eşe giden `rtc` mesajları sunucuda sırayla iletilir (`Controller._relay_to`), istemcide de eş başına sırayla işlenir (`peer.queue`).
- **Konuşan tespiti:** karşı tarafın seviyesi `getSynchronizationSources()`'tan okunur, uzak ses WebAudio'ya bağlanmaz (Chrome'da sessizlik verir). Film sesini kısma kaydırıcıyı oynatmaz: `video.volume = prefs.volume × duck`.
- **Kısayollar:** değiştirici tuşlu basışlar (`Ctrl`, `Cmd`, `Alt`) tek harfli kısayolları tetiklemez; `Ctrl+D` mikrofon, `Ctrl+E` kamera, `d` kalem.
- **Tarayıcı testindeki sahte mikrofon** ffmpeg'in `flite` filtresiyle sentezlenmiş konuşma çalar. Chrome'un kendi sahte mikrofonu kısa bipler çıkarıyor, düz bir tonu da gürültü bastırma yarım saniyede siliyor; ikisiyle de konuşan göstergesi güvenilir denenemiyor.

## Durum (28 Ekim 2026)

- Faz 1 Windows'ta denendi: yerel dosya, iki pencerede senkron, kişiye özel altyazı (TR + EN).
- İmleç topu, dürtme sesi ve çizim eklendi; iki tarayıcı penceresiyle denendi.
- Henüz denenmedi: Windows'ta torrent (README'deki Sintel magnet'i) ve Tailscale üzerinden arkadaşla izleme. Tailscale bu bilgisayarda kurulu değil.
- Kamera-ses 1. adımının kodu bitti: `is_local`, `run.py`'de Tailscale Serve, tarayıcı testi (Playwright kuruldu, test geçiyor). Tailscale olmadan eski http davranışı denendi. Serve'ün kendisi (WebSocket'in geçmesi dahil) Tailscale kurulunca denenecek.

## Sıradaki iş: kamera ve ses

Plan: [docs/kamera-ses-plani.md](docs/kamera-ses-plani.md). Plandaki beş karar proje sahibinde; cevap gelmediyse önerilen varsayılanlarla ilerle.

- 1. adımda kalan: Tailscale'i kurup Serve üzerinden oda ve WebSocket'i denemek (elle).
- 2. adım (ses) kodlandı; tarayıcı testinde sahte mikrofonla bağlantı, konuşan göstergesi, film sesini kısma ve yeniden bağlanma geçiyor. Kalan elle deneme: hoparlörle yankı (Chrome ve Edge) ve iki ayrı bilgisayar.
- 3. adım (kamera) kodlandı; tarayıcı testinde iki yönlü görüntü, bant sınırı, tam ekran, kutuya tıklama ve `Ctrl+E` geçiyor. Kalan elle deneme: gerçek kamerayla ışığın sönmesi, telefon.
- Sıradaki: 4. adım, cila (girişte önizleme, kutuları sürükleme ve küçültme, kendiliğinden yeniden bağlanma).
