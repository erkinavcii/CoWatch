# CoWatch: Claude için çalışma notları

Bu dosya, Claude Code oturumlarının projeyi hızla tanıması için. Uygulamanın ne olduğu ve nasıl kurulduğu README'de ([EN](README.md) · [TR](README.tr.md)); burada geliştirirken gereken kurallar, bilinen tuzaklar ve sıradaki iş var.

Klasörde `_handoff/` varsa (git'e girmez) `_handoff/HANDOFF.md`'yi de oku: önceki oturumun özeti, kararların gerekçeleri ve bu bilgisayara özel notlar.

## Kurallar

- **Commit kimliği:** author ve committer `erkinavcii <56629073+erkinavcii@users.noreply.github.com>`. Commit mesajına `Co-Authored-By`, Claude imzası ya da oturum linki ekleme. Mesajlar Türkçe ve önceki commit'lerin üslubunda: kısa bir başlık, gerekirse madde madde ayrıntı.
- **Commit'ten önce testler:** `.\.venv\Scripts\python -m pytest -q` (şu an 84 test, Linux'ta biri atlanır; ffmpeg kuruluysa medya testleri de çalışır). Arayüzü ya da WebSocket mesajlarını değiştiren her adımdan sonra tarayıcı testleri de (aşağıda).
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
- ffmpeg winget ile kurulduysa (`Gyan.FFmpeg`) yeni açılan konsollar onu PATH'te bulur; kurulumdan önce açılmış bir kabukta `$LOCALAPPDATA/Microsoft/WinGet/Links`'i PATH'e ekle.

## Tarayıcı testleri

Arayüz, senkron ya da WebSocket mesajları değiştiyse ikisini de koştur. Her biri kendi sunucusunu ve test videosunu açar, bir-iki dakika sürer; `--headed` ile pencereler izlenir.

- `tests/e2e/two_viewers.py`: iki pencerede senkron, kişiye özel altyazı (ikinci satır dahil), imlecin bantlı videoda aynı noktaya düşmesi, dürtme sesi, tıklamanın oynatıp durdurması ve çift tıklamanın durdurmadan tam ekrana geçmesi, kalemin rengi ve yeri, temizleme, sohbet (`c`, mesajın düz metin olarak ötekinin köşesinde görünmesi, okunmamış sayısı, panele tıklamanın filmi durdurmaması), konsol hataları.
- `tests/e2e/voice_camera.py`: misafir Tailscale Serve başlığıyla gelir (yerel dosya alanı ona kapalı); host ona film klasörü yetkisi verir, filmi misafir klasörden açar, yetki geri alınır; Chromium'un sahte kamerası ve mikrofon yerine sentezlenmiş konuşmayla ses, konuşan göstergesi, film sesini kısma, yeniden bağlanma, kamera kutuları, tam ekran, `Ctrl+E`; üçüncü izleyiciyle önizleme, 3 kişilik bağlantı, kutuları sürükleme ve küçültme, bağlantıları yeniden kurma.

```powershell
.\.venv\Scripts\python -m pip install -r requirements-dev.txt  # bir kez
.\.venv\Scripts\python -m playwright install chromium          # bir kez
.\.venv\Scripts\python tests\e2e\two_viewers.py
.\.venv\Scripts\python tests\e2e\voice_camera.py
```

## Kod haritası

| Yer | Ne yapar |
| --- | --- |
| `server/main.py` | FastAPI uygulaması: WebSocket mesajları (`Controller.handle`), API, erişim anahtarı, HLS dosyaları, ayarlar ve paylaşım API'si (`/api/settings`, `/api/share`) |
| `server/config.py` | Ayarlar: ayarlar sayfasının seçimleri (`data/settings.json`, `DEFAULTS`, `saved_env`) ve üstüne ortam değişkenleri ile `.env` |
| `server/tailscale.py` | Tailscale'in durumu (`status`: missing, stopped, login, running), tepsi uygulamasını açma, Serve/Funnel süreci (`Share`: çıktısından izin linkini okur) |
| `server/room.py` | Oda durumu ve senkron kuralları; oynatma durumunun tek doğru kaynağı sunucu |
| `server/media.py` | ffprobe, kopya ya da dönüştürme kararı, ffmpeg ile HLS (fMP4) üretimi |
| `server/presence.py` | İmleç, dürtme, çizim ve sohbet mesajlarının doğrulanması (`chat_text`, hız sınırı `Bucket`), renk paleti |
| `server/signaling.py` | Ses ve kamera için WebRTC sinyal mesajlarının (`rtc`) doğrulanması, `ICE_SERVERS` |
| `server/filepicker.py` | "Gözat…": host'un ekranında sistemin dosya ya da klasör penceresi (tkinter); tarayıcının kendi seçicisi dosyanın tam yolunu vermez |
| `server/library.py` | Film klasörleri (`LIBRARY_DIRS`): videoları listeleme, klasör numarası ve iç yoldan dosyayı bulma (klasörden çıkamaz) |
| `server/addons.py` | Stremio eklentileri: manifest, katalog, bilgi, akış, altyazı; hazır eklentiler (`DEFAULT_ADDONS`), host'un ekledikleri `data/addons.json`'da |
| `server/stremio.py` | "Stremio'dan içe aktar": Stremio masaüstünün eklenti listesini Chromium'un LevelDB'sinden (`Local Storage\leveldb`) okur; Snappy çözücüsü içinde, yerel bir bağımlılık yok |
| `server/subtitles.py` | Altyazı çözme (cp1254, cp1251 gibi eski kodlamalar), OpenSubtitles, saklama |
| `server/oshash.py`, `server/torrent_client.py` | OpenSubtitles hash'i; Node torrent yardımcısıyla konuşma |
| `torrent-helper/index.mjs` | webtorrent: magnet linkinden HTTP Range akışı |
| `web/app.js` | İstemci: senkron, altyazı çizimi, imleç topları, kalem, ses ve kamera (eş bağlantıları, konuşan göstergesi, film sesini kısma, kamera kutuları) |
| `run.py` | Başlatıcı (`Launcher`): torrent yardımcısı, Tailscale Serve/Funnel (HTTPS linki), Uvicorn; ayarlar kaydedilince hepsini yeni ayarlarla yeniden başlatır; `stop()` hepsini kapatır |
| `tray.py` | Kurulu uygulamanın `CoWatch.exe`'si: tepsi simgesi ve menüsü (`pystray`), `Launcher`'ı bir iş parçacığında çalıştırır, odayı tarayıcıda açar |
| `tools/build_windows.ps1`, `tools/cowatch.iss` | Kurulum dosyası: PyInstaller (klasör modu), ffmpeg (BtbN GPL shared) ve Node `tools\` klasörüne, Inno Setup; çıktı `dist\` |
| `tests/` | pytest testleri; `tests/e2e/` tarayıcı testleri (pytest toplamaz) |

## Bilinen tuzaklar

- **ffmpeg çıktı yolları `/` ile verilir** (`media._ffmpeg_out`). HLS muxer `init.mp4`'ün klasörünü playlist yolundaki son `/` karakterinden buluyor; Windows'un `\` yolunda dosyayı çalışma klasörüne yazıyordu.
- **Film zamanı** = `video.currentTime + streamStart`. ffmpeg `-copyts` ile çalışır; akış yeniden başlatılınca ilk parçanın zamanı ölçülür.
- **İmleç ve çizim konumları** pencereye değil, video görüntüsüne göre orandır (0–1); `object-fit: contain`'in bıraktığı bantlar hesaba katılır.
- **İmleç ve çizim mesajları** sunucuda arka planda iletilir (`Controller._relay`); yavaş bir izleyici oynat/durdur komutlarını bekletmesin diye. İmleç konumları `lossy`: o izleyiciye önceki mesaj hâlâ yoldaysa yenisi bekler, aynı göndericiden daha yenisi gelince onun yerini alır ve yol açılınca gider (`Client._waiting`). Önceden düşürülüyordu; düşen farenin son konumu olunca top bir önceki yerde kalıyordu (`two_viewers.py`'deki ara ara düşen denetim buydu).
- **CI:** `.github/workflows/tests.yml` her push'ta `pytest`'i Ubuntu ve Windows'ta, ffmpeg'le koşturur. Tarayıcı testleri CI'da yok. Bir testte `os.name`'i `nt` yapmak Linux'ta `pathlib`'i bozar; öyle testler `skipif(sys.platform != "win32")` alır.
- **Yerel dosya açma** sadece host'a açık (`is_local`): loopback adresi, `Host` başlığı yerel bir ad ve vekil başlığı (`Tailscale-User-Login`, `X-Forwarded-For`, `Forwarded`) yok. Tailscale Serve istekleri de `127.0.0.1`'den getirdiği için tek başına adres yetmez. `voice_camera.py` misafiri bu başlıkla taklit eder.
- **Tailscale Serve** `run.py`'nin alt süreci olarak ön planda çalışır; `--bg` kullanma (yeniden başlatmalardan sonra da açık kalır). Serve açıkken `HOST` boşsa `127.0.0.1` olur, düz http linkleri yazılmaz. `TAILSCALE_FUNNEL=1` aynı şeyi `tailscale funnel` ile yapar: link internete açık, arkadaş Tailscale kurmaz. Funnel istekleri de `127.0.0.1`'den ve `*.ts.net` `Host`'uyla gelir, kimlik başlığı yoktur; `is_local`'ı `Host` kontrolü korur. Funnel'da `ICE_SERVERS` boşsa Cloudflare STUN'u kullanılır (`config.FUNNEL_STUN`), çünkü misafirin Tailscale adresi yok.
- **Statik dosyalar** `no-cache` ile sunulur; tarayıcı her açılışta yeni sürümü sorar.
- **Eş bağlantıları:** kimliği küçük olan taraf teklif eder ve dört transceiver'ı (`SLOTS`: ses, kamera, ekranın görüntüsü, ekranın sesi) bu sırayla o ekler; diğeri teklifteki transceiver'ları sırasına göre alır ve `sendrecv` yapar. İki taraf da eklerse sekiz olur. `ontrack` gelen izin hangi yuva olduğunu `getTransceivers()` içindeki sırasından anlar (polite tarafta `adoptTransceivers`'tan önce çalışır). Mikrofon, kamera ve ekran aç/kapa sadece `replaceTrack`; yeniden pazarlık yok. Gönderici sınırları (`SENDER_LIMITS`: kamera 500 kbps, 24 kare) bağlantı kurulunca `setParameters` ile verilir; öncesinde `encodings` boş.
- **Kamera kutuları** (`#camsBox`) `#stage` içindeki iki `.side` sütunundan birinde: sağdakinde çizim araç çubuğunun üstünde ya da altında, soldakinde tek başına (`placeCams`, `prefs.camCorner`). Tam ekranda bu yüzden kalırlar. Biri kamerasını açınca görünürler (kapalı olanlar renkli topla). `isUi` kutuları da sayar: tıklamak dürtme değil, ses seviyesi; 6 px'ten fazla kayan basış sürüklemedir.
- **Kendiliğinden onarım:** WebSocket koparsa 2 sn sonra, ağ geri gelince (`online`) hemen yeniden bağlanır. Eş bağlantısı düşerse önce `restartIce`; 20 sn'de gelmezse teklif eden taraf bağlantıyı atıp yeniden kurar ve karşıya `{reset: true}` gönderir (`peerWatch`, `resetPeer`).
- **WebSocket yeniden bağlanınca** sunucu yeni `clientId` verir; istemci `welcome`'da bütün eş bağlantılarını kapatır, `members` gelince yeniden kurar. Aynı eşe giden `rtc` mesajları sunucuda sırayla iletilir (`Controller._relay_to`), istemcide de eş başına sırayla işlenir (`peer.queue`).
- **Konuşan tespiti:** karşı tarafın seviyesi `getSynchronizationSources()`'tan okunur, uzak ses WebAudio'ya bağlanmaz (Chrome'da sessizlik verir). Film sesini kısma kaydırıcıyı oynatmaz: `video.volume = prefs.volume × duck`.
- **Kısayollar:** değiştirici tuşlu basışlar (`Ctrl`, `Cmd`, `Alt`) tek harfli kısayolları tetiklemez; `Ctrl+D` mikrofon, `Ctrl+E` kamera, `d` kalem, `c` sohbet.
- **Sohbet:** `chat` mesajı sadece `hello` göndermiş (`joined`) izleyiciden kabul edilir; sunucu metni tek satıra indirir (kontrol ve yön karakterleri boşluk olur, 500 karakter), `Bucket` ile art arda 5'ten sonra saniyede bir mesaja izin verir (aşınca o kişiye `status: chat_slow`), mesajı ad ve renkle birlikte gönderen dahil herkese yollar ve son 100'ü `Room.chat`'te tutar (`welcome`'da `chat`). Gönderene de gittiği için herkes aynı sırayı görür. Sadece hafızada; diske yazılmaz. Tek bir `#chatBox` iki yer arasında taşınır (`placeChat`): en az 1100 px genişlikte, tam ekran ve PiP yokken filmin sağındaki `#chatDock` sütununa (`#watch` ızgarası, `.docked`; açık/kapalı `prefs.chatDock`, varsayılan açık), yoksa `#stage` içine videonun üstüne (açık/kapalı `CHAT.overlay`, varsayılan kapalı). Sütun hücresine mutlak konumla oturur, uzun sohbet satırı ve filmi uzatmasın diye. Sahne içindeyken `isUi` onu da sayar. Mobil düzen ayrıca ele alınacak. PiP penceresi tuşları ana sayfaya kopyalarken yazı alanlarındaki tuşları atlar; yoksa sohbete yazılan boşluk filmi durdururdu.
- **Eklenti akışları ve altyazıları referansla açılır:** sunucu eklentiden gelen her akışı ve altyazıyı hafızada tutar, istemciye sadece kısa bir `ref` verir (`AddonStore.refs`). Tarayıcı sunucuya hiçbir zaman çekilecek bir adres göndermez; böylece misafir sunucuyu rastgele adreslere istek attırmak için kullanamaz. Eklenti eklemek ve kaldırmak sadece `is_local`.
- **Stremio'dan içe aktarma:** LevelDB'de anahtarın son 8 baytı `sıra << 8 | tür` (little-endian); tür (0 = silindi) bu sayının en düşük baytı, yani `key[-8]`. Önce `key[-1]` okunuyordu ve tablolardaki (`.ldb`) neredeyse her değer silinmiş sayılıyordu. En yüksek sıra numaralı `addons` değeri kazanır; silinmişse liste boştur. Yerel adresler (`127.0.0.1`, Stremio'nun kendi akış sunucusu), sadece kanal veren ve eski `/stremio/v1` eklentileri alınmaz. Testler `STREMIO_DATA_DIR`, `LOCALAPPDATA`, `APPDATA` ve `USERPROFILE`'ı geçici klasöre çevirir, yoksa bu bilgisayardaki gerçek Stremio okunurdu.
- **Film seni izler:** `#stageWrap` sahnenin sayfadaki yerini tutar. Bir `IntersectionObserver` onun görünmediğini görünce sahne `.mini` olur (sağ altta sabit kutu; sarmalayıcıya o anki yüksekliği yazılır, sayfa zıplamaz; `body.has-mini` bildirimleri yukarı alır ve sayfanın sonuna boşluk ekler). Pencere düğmesi Chrome'un Document Picture-in-Picture'ı: `#stage` öğesi küçük pencerenin belgesine taşınır, stil dosyaları kopyalanır, kapanınca (`pagehide`) geri gelir. Ana sayfanın `requestAnimationFrame`'i pencere örtülünce durduğu için o sırada çizimi küçük pencerenin karesi yapar (`pipFrame`). Tarayıcı başka belgeye taşınan videoyu durdurabilir; `resumeAfterMove` oda oynuyorsa hemen devam ettirir. Tarayıcı testlerinde sayfa aşağı kayınca kutu bazı düğmelerin üstüne gelir; testler onu kapatır ya da yukarı kaydırıp `.mini`'nin gitmesini bekler.
- **Eklenti altyazıları ve odadaki altyazılar** `key` ile eşleşir (adresin SHA-1'inin ilk 12 hanesi, `addons.subtitle_key`): listedeki her altyazıda ve eklentiden yapılmış her altyazıda (`Controller.tracks` adresten hesaplar) aynı değer var. Liste düğmelerini bu yüzden tarayıcı o anki altyazılardan çizer (`applyTracks` listeyi yeniden çizer); önceden eklenince tarayıcıda konan bir işaret silindikten sonra da kalıyor, altyazı yeniden eklenemiyordu. Eklentiler ad vermediği için aynı dildekiler `#1`, `#2` diye numaralanır; altyazının adı da bu olur.
- **Yetkili arkadaş (ortak host):** host, kişi kutusundaki "Film klasörü yetkisi ver" ile (`grant` mesajı, sadece `client.host` gönderebilir) arkadaşın tarayıcısına film klasörü yetkisi verir. Yetki `clientId`'ye değil `cw_viewer` çerezine bağlı (`Room.cohosts`), çünkü yeniden bağlanınca kimlik değişir; sadece hafızada, sunucu yeniden başlayınca biter. Yetkili sadece `LIBRARY_DIRS` içinden, klasör numarası ve iç yolla açar (`is_trusted`); yol yazmak, Gözat… ve eklenti ayarları host'ta kalır. `MEDIA_CONTROL=trusted` film açmayı ve kapatmayı da host ile yetkililere bırakır (`require_media_control`); varsayılan `everyone`.
- **Ekran paylaşımı:** aynı anda tek ekran (`Room.screen`). Host ve yetkililer `share_request` ile hemen alır; diğerleri `Room.share_asks`'e girer, host ya da yetkili `share_answer` ile cevaplar, 30 sn'de düşer (`watchdog_loop`). Odada onaylayan kimse yoksa onaysız verilir. Durum hep tek mesajla yayılır: `{type: "screen", owner, pending}`; istemci reddedildiğini kendi kimliğinin `pending`'den sahiplik almadan çıkmasından anlar (`screen.asking` cevap gelene kadar bunu bekletir). `getDisplayMedia` sadece tıklamanın hemen ardından açılabildiği için yakalama tıklamada açılır ama ekran sunucuda o kişinin olana kadar gönderilmez (`applyLocalTracks`). Paylaşım başlarken film oynuyorsa sunucu durdurur, bitince devam ettirir (`set_screen`, `screen_paused`). Playwright'ın Chromium'u sahte bayraklarla sahte bir ekran ve ses veriyor.
- **Test istemcisinin WebSocket'i** `base_url` ne olursa olsun `Host: testserver` gönderir; host'u taklit eden bir WebSocket testi `host: localhost:…` başlığını kendisi verir. İki ayrı `TestClient` iki ayrı olay döngüsü açar ve aynı odada mesajlar takılır; host ve misafiri tek istemcide başlıklarla ayır.
- **Testler bu bilgisayarın ayarlarını görmez:** pytest ve tarayıcı testleri `COWATCH_DOTENV=""` (`.env` okunmaz) ve `ADDONS_BUILTIN=0` (Stremio'nun eklentilerine istek gitmez) ile çalışır. Yeni bir ayar ekleyince testlerin ona `.env`'den bağımlı olmadığına bak.
- **Ayarlar sayfası:** seçimler `data/settings.json`'da, `.env` ve ortam değişkenlerinin altında (`get_settings`'te `{**saved_env(saved), **os.environ}`). Bir seçimin değişkeni ortamda varsa sayfada kilitli (`locked_settings`, `ENV_NAMES`) ve sunucu kaydederken onu eskisi gibi bırakır. Kaydedilenler asla `os.environ`'a yazılmaz; yazılsa kendilerini kilitlerlerdi. "Otomatik" kalite bir değişken yazmaz: Funnel açıksa (`.env`'den gelse de) 5500/4500, değilse 0/5000. Ayarlar ve paylaşım API'si sadece `is_local`.
- **Yeniden başlatma:** `main.launcher`'ı `run.py` koyar (testlerde ve düz uvicorn'da `None`; API o zaman `restart: false` döner). `restart()` uvicorn'a `should_exit` verir; döngü `server.*` modüllerini `sys.modules`'tan silip yeniden içe aktarır, çünkü `cfg` ve `ctl` içe aktarılırken kurulur. Torrent yardımcısı ve Serve/Funnel kendi ayarları değişmediyse çalışmaya devam eder; çökmüş bir Serve her yeniden başlatmada yeniden denenir (sayfadaki "Yeniden dene"). Port ya da anahtar değişince sayfa eski sunucunun gidip yenisinin gelmesini bekleyip yeni adrese geçer (`goWhenUp`).
- **Serve/Funnel çıktısı** artık konsola doğrudan değil, `Share._read` üzerinden gider (satırlar yine konsola yazılır). `https://login.tailscale.com/…` görülürse durum `consent`, ardından `Available…` satırı gelince `ok`. 30 Ekim'de Tailscale 1.104.4'le denendi: Funnel `Available on the internet:` yazıyor ve durum `ok` oluyor. İzin linki satırı henüz gerçek çıktıyla görülmedi (tailnet'te Funnel zaten açıktı).
- **Kurulu uygulama (`CoWatch.exe`):** `config.FROZEN` iken veri `%APPDATA%\CoWatch`'ta (`default_data_dir`, `.env` de orada) ve bağlantı varsayılanı Funnel. ffmpeg ve Node exe'nin yanındaki `tools\` klasöründen gelir: `tray.prepare` onu PATH'in başına koyar. Konsol yok: `sys.stdout` `cowatch.log`'a çevrilir (5 MB'ı geçince `.old.log`), torrent yardımcısının çıktısı `torrent-helper.log`'a; her alt süreç `CREATE_NO_WINDOW` ile açılır (`tailscale.NO_WINDOW`), yoksa siyah pencereler yanıp söner. Uvicorn tepsinin yanında ayrı bir iş parçacığında çalışır (sinyal yakalamayı kendisi atlar). Kullanıcı başına tek kopya (`Local\CoWatchTray` mutex'i); ikinci açılış sadece odayı açar. Tepsinin "Ayarlar"ı odayı `#settings` ile açar, sayfa host'a ayarları açar. Kurulum ve kaldırma `taskkill /IM CoWatch.exe /T` ile çalışan uygulamayı alt süreçleriyle (Funnel dahil) kapatır. Geliştirme sürümü 8000'de çalışırken kurulu sürümü denemek için `PORT`, `HELPER_PORT` ve `TAILSCALE_SERVE=0` ortamdan verilir; kaydedilmiş Funnel varsayılanı yine denenir ama 443'ü tutan Funnel varken başlamaz, var olana dokunmaz.
- **Tarayıcı testindeki sahte mikrofon** ffmpeg'in `flite` filtresiyle sentezlenmiş konuşma çalar. Chrome'un kendi sahte mikrofonu kısa bipler çıkarıyor, düz bir tonu da gürültü bastırma yarım saniyede siliyor; ikisiyle de konuşan göstergesi güvenilir denenemiyor.

## Durum (30 Ekim 2026)

- Faz 1 Windows'ta denendi: yerel dosya, iki pencerede senkron, kişiye özel altyazı (TR + EN).
- İmleç topu, dürtme sesi ve çizim eklendi; iki tarayıcı penceresiyle denendi.
- Henüz denenmedi: Windows'ta torrent (README'deki Sintel magnet'i) ve Tailscale üzerinden arkadaşla izleme. Tailscale bu bilgisayarda kurulu ve açık (MagicDNS, HTTPS sertifikası hazır); `run.py` onu PATH'te yoksa `C:\Program Files\Tailscale`'de de arar.
- Funnel (`TAILSCALE_FUNNEL=1`) bu bilgisayarda açık (tailnet'te Funnel izni verildi; ilk seferde onay linki çıkıyor ve onaydan sonra `run.py`'yi yeniden başlatmak gerekebiliyor). `https://….ts.net` linki internetten erişiliyor (anahtarsız 401). Linkle açılan sayfa güvenli sayılıyor, WebSocket Tailscale'in HTTPS vekilinden geçiyor, misafir host sayılmıyor, mikrofon açılıyor (Playwright ile, 28 Ekim). 28 Ekim: telefondan mobil veriyle linke girildi, oda açıldı. 29 Ekim ölçüm: Funnel aktarıcısı üzerinden 64 MB indirme ≈ 7–8 Mbps (iki deneme); aynı anda evin upload'u ≈ 28–31 Mbps, download'u ≈ 68–71 Mbps. Yani darboğaz Funnel. İki izleyicinin bu sınırı paylaşıp paylaşmadığı bilinmiyor. Denenmedi: gerçek bir filmle baştan sona, ses ve kamera STUN ile dışarıdaki bir cihazla.
- 30 Ekim: proje yeni bir bilgisayara klonlandı (Python 3.11, Node 22, ffmpeg ve Tailscale 1.104.4 winget'ten; aynı tailnet'e katıldı, adı `desktop-jljklrm`). Funnel linki açılır açılmaz internetteki tarayıcı botları denemeye başlıyor (`/.env`, `/wp-admin` gibi); hepsi 401 ya da 404 alıyor. `two_viewers.py`'nin "a pointer lands on the same spot" denetimi bu bilgisayarda ara ara düşüyordu; sebep sunucunun son imleç konumunu atlamasıydı, düzeltildi.
- Bilgisayar yeniden başlayınca Tailscale tepsi uygulaması açılmazsa servis "starting" durumunda kalıyor ve `run.py` HTTPS linki veremiyor; `tailscale-ipn.exe`'yi açmak yetiyor.
- Masaüstü uygulamasının yerleşik tarayıcısı bu sitenin betiklerini engelliyor (`ERR_BLOCKED_BY_CLIENT`); denemeler Playwright'la ya da gerçek bir tarayıcıyla yapılmalı.
- Kamera-ses 1. adımının kodu bitti: `is_local`, `run.py`'de Tailscale Serve, ses ve kamera tarayıcı testi (Playwright kuruldu, iki test de geçiyor). Tailscale olmadan eski http davranışı denendi. Serve'ün kendisi (WebSocket'in geçmesi dahil) Tailscale kurulunca denenecek.

## Sıradaki iş: kamera ve ses

Plan: [docs/kamera-ses-plani.md](docs/kamera-ses-plani.md). Plandaki beş karar proje sahibinde; cevap gelmediyse önerilen varsayılanlarla ilerle.

- 1. adım tamam: HTTPS linkinde oda ve WebSocket çalışıyor (Funnel üzerinden denendi; Serve aynı vekili kullanıyor).
- 2. adım (ses) kodlandı; tarayıcı testinde sahte mikrofonla bağlantı, konuşan göstergesi, film sesini kısma ve yeniden bağlanma geçiyor. Kalan elle deneme: hoparlörle yankı (Chrome ve Edge) ve iki ayrı bilgisayar.
- 3. adım (kamera) kodlandı; tarayıcı testinde iki yönlü görüntü, bant sınırı, tam ekran, kutuya tıklama ve `Ctrl+E` geçiyor. Kalan elle deneme: gerçek kamerayla ışığın sönmesi, telefon.
- 4. adım (cila) kodlandı: girişte önizleme, kutuları sürükleme ve küçültme, kendiliğinden onarım. Tarayıcı testi üçüncü bir izleyiciyle 3 kişilik bağlantıyı da deniyor. Kişi başına %100 üstü ses yapılmadı (yankı denemesinden sonra gerekirse).
- Kalan: plandaki ölçüt, Tailscale üzerinden arkadaşlarla gerçek cihazlarda başından sonuna bir film (elle).

Sonraki işler (önce genel program tamamlanacak): [docs/future-plans.md](docs/future-plans.md). Dağıtım ve paketleme (kurulum dosyası, tepsi başlatıcısı; ilk açılışta Funnel, daha yüksek kalite için Serve), Faz 2 ve 3.

- Dağıtımın 1. adımı (30 Ekim) kodlandı: Paylaş kartı (arkadaş linki, kopyala, QR, Tailscale'in durumu ve ne yapılacağı), ayarlar sayfası (bağlantı, kalite, film klasörleri, film kontrolü, OpenSubtitles, port, torrent upload sınırı, STUN, yeni oda anahtarı), kaydedince `run.py` içinde yeniden başlatma. Playwright'la denendi: kaydetme, yeniden başlayıp bağlanma, port ve anahtar değişince yeni adrese geçme, telefon genişliği. Gerçek Tailscale'le denendi: kurulu değil → kurulup oturum açılınca "Yeniden dene" Funnel'ı başlattı, kart `ok` gösterdi; linkten gelen misafir host sayılmıyor, ayarlara 403 alıyor; Funnel kendi ayarı değişmeyen bir yeniden başlatmada açık kaldı. Kalan: izin linki durumu ve dışarıdan (mobil veri) gerçek bir cihazla ses ve kamera. Varsayılan bağlantı hâlâ Serve; planın "ilk açılışta Funnel" kararı kurulum dosyasıyla birlikte verilecek.

- Eklentiler (29 Ekim) kodlandı: "Göz at" kartı (katalog, arama, sezon ve bölüm, kaynaklar), eklenti listesi, eklentilerden altyazı, film kimliğiyle OpenSubtitles araması. Gerçek Cinemeta ve Public Domain Movies ile denendi: arama, Breaking Bad'in sezonları, "The Kid" torrent'i açılıp oynadı. Kalan: ayarlar sayfası (dağıtım planıyla birlikte).

- Yazılı sohbet (30 Ekim) kodlandı, küçük sürüm: videonun sol altında panel, kapalıyken köşede birkaç saniye görünen mesajlar ve okunmamış sayısı, son 100 mesaj hafızada. Playwright'la masaüstü, tam ekran ve telefon genişliğinde denendi; telefonda kontrol çubuğu sığsın diye dar ekranda düğmeler küçüldü, pencere düğmesi ve (ekranı yakalayamayan tarayıcıda) ekran düğmesi gizleniyor. Bilerek yapılmayanlar: emoji tepkileri, videonun üstünden akan yorumlar, kalıcı geçmiş, yeni mesaj sesi.

- Dağıtımın 2. ve 3. adımı (31 Ekim) kodlandı: tepsi başlatıcısı (`tray.py`) ve kurulum dosyası (`tools/build_windows.ps1`). Kurulum dosyası ≈ 100 MB, kurulunca ≈ 350 MB (çoğu ffmpeg'in kitaplıkları ve Node). Bu bilgisayarda denendi: sessiz kurulum (yönetici istemedi, Başlat menüsü kısayolu), açılınca tarayıcıda oda, paketteki Node ile torrent yardımcısı, paketteki ffmpeg'le x264 dönüştürme, konsol penceresi yok, kaldırınca süreçler ve klasör gitti, ayarlar kaldı. Denenmedi: tepsi menüsü elle (özellikle Çıkış), kurulu uygulamadan Funnel, başka bir bilgisayarda SmartScreen ve antivirüs. Releases'e henüz sürüm konmadı.

- **Eklentilerde kural:** depoya sadece yasal ve içerik barındırmayan eklentiler girer (Cinemeta, Public Domain Movies). Kullanıcının kişisel eklentileri git'e girmeyen dosyada durur; depoda, README'de ve testlerde adları ya da adresleri geçmez.
