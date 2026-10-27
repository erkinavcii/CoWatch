# Co-Watch

[English](README.md) · **Türkçe**

Uzaktaki arkadaşlarınla aynı filmi aynı anda izle; herkes kendi altyazı dilini seçsin. Sen Türkçe + İngilizce görürken karşı taraf Rusça + İngilizce görebilir.

Faz 1 (MVP): kendi video dosyan ya da bir torrent → orijinal kalitede akış (yeniden encode yok) → herkesin tarayıcısında senkron oynatma + kişiye özel çift altyazı.

## Nasıl çalışıyor

```
yerel dosya ───────────────────────────────────────┐
magnet ──> torrent yardımcısı (Node, webtorrent) ──┴──> ffmpeg (video kopya, ses AAC stereo) ──> HLS
                                                                                                  │
           Oda + senkron sunucusu (FastAPI, WebSocket) <──── play/pause/seek ──── tarayıcılar (hls.js)
```

- Herkes aynı HLS akışını kendi tarayıcısında oynatır; ekran paylaşımı yok, kalite kaybı yok.
- Sunucu tek doğru kaynaktır: `playing`, `position`, `updatedAt`. İstemci farkı 1 sn'yi aşarsa seek yapar, 0,1–1 sn arasında hızı %5 oynatarak yakalar.
- Biri takılırsa (buffer) oda onun durduğu yerde bekler, en az 4 sn'lik tampon oluşunca herkes birlikte devam eder. 20 sn'den uzun takılan izleyici odayı tutamaz.
- Altyazılar videoya gömülmez: her tarayıcı seçtiği altyazıyı filmin saniyesine göre kendisi çizer (`film zamanı = video.currentTime + streamStart`). Kaydırma (±ms), boyut ve yükseklik kişiye özeldir.
- Altyazılar dosyanın OpenSubtitles hash'ine göre saklanır; aynı film tekrar açılınca (torrent ya da yerel dosya fark etmez) hazır gelir.
- Henüz hazırlanmamış bir yere atlanırsa ffmpeg o noktadan yeniden başlatılır; torrent o kısmı öncelikli indirir.

## Gereksinimler

| | Kimde | Not |
|---|---|---|
| Python 3.10+ | host | |
| Node.js 22+ | host | sadece torrent için |
| ffmpeg + ffprobe | host | PATH'te olmalı |
| Tailscale | host + izleyiciler | ücretsiz kişisel plan yeter |
| Güncel tarayıcı | herkes | Chrome, Edge, Firefox, Safari |

Windows'ta hızlı kurulum (her satır ayrı komut):

```powershell
winget install Python.Python.3.12
winget install OpenJS.NodeJS.LTS
winget install Gyan.FFmpeg
winget install Tailscale.Tailscale
```

## Kurulum

Windows (PowerShell, proje klasöründe):

```powershell
py -m pip install -r requirements.txt
cd torrent-helper; npm install; cd ..
copy .env.example .env      # isteğe bağlı: ayarlar ve OpenSubtitles anahtarı
py run.py
```

`py` komutu yoksa yerine `python` yaz. macOS/Linux'ta: `pip install -r requirements.txt`, `cd torrent-helper && npm install && cd ..`, `python3 run.py`.

`run.py` iki linki yazar:

```
Bu bilgisayardan:  http://localhost:8000/?k=ANAHTAR
Tailscale linki:   http://100.x.y.z:8000/?k=ANAHTAR   <- arkadaşına bunu gönder
```

Linkteki anahtar odanın şifresidir; ilk açılışta tarayıcıya çerez olarak kaydedilir. Anahtar `data/access_key.txt` içinde durur; silersen yeni anahtar üretilir ve eski linkler çalışmaz.

Windows ilk çalıştırmada güvenlik duvarı izni sorar; Python'a izin ver. Arkadaşın Tailscale linkiyle bağlanamıyorsa izni "Ortak ağlar" için de ver: Tailscale bağlantısı Windows'ta ortak ağ olarak görünebiliyor.

**Arkadaşın için:** Tailscale'i kursun, sen de bu bilgisayarı Tailscale yönetim panelinden onunla paylaş (ya da onu tailnet'ine davet et). Sonra linki açıp adını yazsın ve "Katıl"a bassın.

## Kullanım

1. **Film aç:** kendi dosyan için "Bu bilgisayardaki dosya yolu"na tam yolu yaz (bu alan güvenlik için sadece host bilgisayarda görünür). Torrent için magnet linkini yapıştırıp "Torrent ekle"ye bas; torrent'te birden fazla video varsa listeden seç.
2. **Altyazı ekle:** "Altyazı ekle" altında dil kodlarını yazıp OpenSubtitles'ta ara (ör. `tr,en,ru`) ya da `.srt/.ass/.vtt` dosyası yükle. Türkçe `cp1254`, Rusça `cp1251` gibi eski kodlamalar otomatik düzeltilir.
3. **Kendi altyazını seç:** herkes ana ve ikinci altyazısını, zaman kaydırmayı, yazı boyutunu ve yüksekliği kendisi ayarlar. Tercih edilen dil hatırlanır; yeni filmde o dilde altyazı varsa otomatik seçilir.
4. **Kısayollar:** boşluk oynat/durdur, ← → 10 sn, `f` tam ekran, `m` ses. Dokunmatik ekranda videoya dokunmak sadece kontrolleri gösterir; herkes için durdurmak buton ister.

Arayüz Türkçe, İngilizce ve Rusça kullanılabiliyor.

## Hızlı deneme

Tek bilgisayarda, iki tarayıcı penceresiyle:

1. Proje klasöründe test videosu üret. 2 dakikalık video, saniyeyi ekranda büyük rakamla gösteriyor; torrent dosyaları gibi H.264 video ve AC3 5.1 ses içeriyor:
   ```powershell
   ffmpeg -f lavfi -i testsrc=size=1280x720:rate=24 -f lavfi -i "sine=frequency=440" -t 120 -c:v libx264 -g 48 -pix_fmt yuv420p -af volume=0.1 -c:a ac3 -ac 6 samples\test-video.mkv
   ```
2. `py run.py` ile başlat, "Bu bilgisayardan" linkini aç, adını yaz ve Katıl'a bas.
3. "Bu bilgisayardaki dosya yolu" alanına `samples\test-video.mkv` dosyasının tam yolunu yapıştır. Dosya Gezgini'nde dosyaya sağ tıklayıp "Yol olarak kopyala" diyebilirsin; tırnaklar sorun değil.
4. Aynı linki gizli pencerede aç ve başka bir adla katıl.
5. "Altyazı ekle" altında ilk pencerede `samples\test.tr.srt` dosyasını `tr` diliyle, ikinci pencerede `samples\test.ru.srt` dosyasını `ru` diliyle yükle. İki dosya da eski kodlamalı (cp1254 ve cp1251); Türkçe ve Rusça harfler düzgün görünmeli.
6. Oynat. Altyazıdaki saniye ekrandaki büyük rakamla aynı olmalı ve iki pencere aynı karede kalmalı. İleri sarmayı, durdurmayı ve ±0.5 kaydırmayı dene.

Gerçek bir torrent için Blender Vakfı'nın açık lisanslı (CC BY) filmi Sintel'i kullanabilirsin:

```
magnet:?xt=urn:btih:08ada5a7a6183aae1e09d831df6748d566095a10&dn=Sintel&tr=udp%3A%2F%2Fexplodie.org%3A6969&tr=udp%3A%2F%2Ftracker.coppersurfer.tk%3A6969&tr=udp%3A%2F%2Ftracker.empire-js.us%3A1337&tr=udp%3A%2F%2Ftracker.leechers-paradise.org%3A6969&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337&tr=wss%3A%2F%2Ftracker.btorrent.xyz&tr=wss%3A%2F%2Ftracker.fastcast.nz&tr=wss%3A%2F%2Ftracker.openwebtorrent.com&ws=https%3A%2F%2Fwebtorrent.io%2Ftorrents%2F&xs=https%3A%2F%2Fwebtorrent.io%2Ftorrents%2Fsintel.torrent
```

## Upload hızı (izleyici başına)

Gereken upload ≈ dosyanın bitrate'i × 1,3. Dosyanın bitrate'ini bilmiyorsan: 2 saatlik filmde dosya boyutu (GB) × 1,1 ≈ Mbps.

| Kaynak | Bitrate | Rahat upload |
|---|---|---|
| Kompakt 1080p (2 saatlik film 2-3 GB) | 2,5-3,5 Mbps | 5 Mbps |
| 1080p WEB-DL (4-7 GB) | 5-8 Mbps | 8-10 Mbps |
| 1080p BluRay encode (8-12 GB) | 9-14 Mbps | 15+ Mbps ya da dönüştür |
| Telefonla çekilmiş video (1080p) | ~15-20 Mbps | dönüştürmek şart |
| Dönüştürülmüş akış (`TRANSCODE_KBPS=5000`) | 5 Mbps | 8 Mbps |

İki izleyici varsa ikiyle çarp. Upload'un düşükse `.env` içinde `MAX_COPY_KBPS` ver (ör. `6000`): bundan ağır dosyalar otomatik dönüştürülür. H.264 olmayan (HEVC/x265, 10-bit) videolar zaten her zaman dönüştürülür. Ekran kartın varsa `VIDEO_ENCODER=h264_nvenc` (NVIDIA), `h264_qsv` (Intel) ya da `h264_amf` (AMD) işlemciyi rahatlatır.

## Ayarlar (.env)

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `PORT` | 8000 | Web sunucusu portu |
| `TORRENT_UPLOAD_LIMIT` | 64 | Torrent'in upload sınırı (KB/s), 0 = sınırsız |
| `MAX_COPY_KBPS` | 0 | Bunun üstündeki H.264 dosyalar dönüştürülür, 0 = hep orijinal |
| `TRANSCODE_KBPS` | 5000 | Dönüştürülen akışın hedef bitrate'i |
| `VIDEO_ENCODER` | libx264 | Dönüştürme encoder'ı |
| `MAX_HEIGHT` | 1080 | Dönüştürmede en fazla yükseklik |
| `AUDIO_FILTER` | dynaudnorm | Ses dengeleme; boş bırakırsan kapanır |
| `OPENSUBTITLES_API_KEY` | – | [opensubtitles.com/consumers](https://www.opensubtitles.com/consumers) adresinden alınır |
| `OPENSUBTITLES_USERNAME` / `_PASSWORD` | – | Ücretsiz hesapla günde ~20 altyazı indirilebilir |

Torrent, ffmpeg playback'in 10 dakikadan fazla önüne geçince indirmeyi kendiliğinden yavaşlatır; böylece indirme, arkadaşına giden akışla aynı hatta yarışmaz.

## Bilinen sınırlar

- Tek oda, tek film. Odayı link anahtarı korur.
- HDR videolar dönüştürülünce renkler soluk görünür (ton eşleme yok).
- iPhone'da tam ekranda altyazı görünmez (Safari sadece videoyu tam ekran yapabiliyor); yatay modda tam ekransız izle.
- DRM'li platformlar (Netflix vb.) bu modda yok; yol haritasında tarayıcı eklentisi olarak duruyor.
- `data/torrents` indirilen filmlerle büyür; işin bitince elle temizle.

## Yasal not

Co-Watch içerik sağlamaz, aramaz ve dağıtmaz. Kendi dosyaların ya da izleme ve paylaşma hakkın olan içerik için tasarlandı. Torrent desteği protokolün kendisi içindir; telifli içerikte torrent kullanmak IP adresini swarm'da görünür kılar ve izlerken yükleme de yapılır. Kullanımdan doğan sorumluluk kullanana aittir.

## Geliştirme

```bash
pip install pytest
python -m pytest            # ffmpeg kuruluysa medya testleri de çalışır
```

Tarayıcı konsolunda `cowatchDebug()` senkron değerlerini gösterir (film zamanı, beklenen konum, fark).

Dosyalar: `server/` (FastAPI: oda, senkron, medya, altyazı), `torrent-helper/` (Node: magnet → HTTP akış), `web/` (istemci; hls.js `web/vendor` içinde, Apache-2.0).

## Sonraki fazlar

2. Altyazı otomasyonu: dil tercihli fallback zinciri, alass ile hizalama, iki aşamalı LLM çevirisi.
3. Sadece link ile katılım (DataChannel + TURN), bitrate yetmezse otomatik dönüştürme.
4. Lazer çizim, kamera ve sesli sohbet.
5. Çift taraflı torrent senkronu ve DRM'li platformlar için eklenti.

## Lisans

[GNU AGPL v3.0](LICENSE) ya da sonraki sürümleri. Kısaca: kullanabilir, değiştirebilir ve dağıtabilirsin; değiştirdiğin bir sürümü başkalarına ağ üzerinden sunarsan kaynak kodunu da onlara açman gerekir. Bu yüzden uygulamanın giriş ekranında kaynak koda link var.

`web/vendor/hls.light.min.js`: [hls.js](https://github.com/video-dev/hls.js), Apache-2.0 (`web/vendor/hls.js.LICENSE`).
