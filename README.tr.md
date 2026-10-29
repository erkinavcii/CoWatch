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
py -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
cd torrent-helper; npm.cmd install; cd ..
copy .env.example .env      # isteğe bağlı: ayarlar ve OpenSubtitles anahtarı
.\.venv\Scripts\python run.py
```

Python paketleri proje içindeki `.venv` klasörüne kurulur. `npm` yerine `npm.cmd` yazmak, PowerShell'in script çalıştırma kısıtına takılmamak için. `py` komutu yoksa ilk satırda `python` yaz. macOS/Linux'ta: `pip install -r requirements.txt`, `cd torrent-helper && npm install && cd ..`, `python3 run.py`.

`run.py` iki linki yazar:

```
Bu bilgisayardan:  http://localhost:8000/?k=ANAHTAR
Arkadaşlar için:   https://pc.tail1234.ts.net/?k=ANAHTAR   <- arkadaşına bunu gönder
```

Linkteki anahtar odanın şifresidir; ilk açılışta tarayıcıya çerez olarak kaydedilir. Anahtar `data/access_key.txt` içinde durur; silersen yeni anahtar üretilir ve eski linkler çalışmaz.

**Tailscale Serve ile HTTPS:** Tailscale çalışıyorsa `run.py` `tailscale serve`'ü başlatır ve arkadaşlarına `https://….ts.net` linki verir; tarayıcılar kamerayı ve mikrofonu sadece güvenli sayfalarda açıyor. Bir kereliğine [Tailscale yönetim panelinde](https://login.tailscale.com/admin/dns) MagicDNS ve HTTPS Certificates'ı aç (eksik bir şey varsa `tailscale serve` açma linkini kendisi yazar). Bilgisayarın adı herkese açık sertifika kayıtlarına düşer; adda kişisel bilgi varsa önce değiştir. Serve, `run.py` ile birlikte kapanır. Sunucu bu durumda sadece bu bilgisayarı dinler, eski `http://100.x.y.z:8000` linki artık çalışmaz. `.env`'de `TAILSCALE_SERVE=0` verirsen ya da Tailscale yoksa eskisi gibi düz http linkleri gelir (Windows da Python için güvenlik duvarı izni sorar).

**Arkadaşın için:** Tailscale'i kursun, sen de onu Tailscale yönetim panelinden tailnet'ine davet et (ücretsiz kişisel plan 6 kullanıcıya kadar). Sadece bu bilgisayarı paylaşmak film için yeter, ama o zaman iki arkadaş kamera ve ses için birbirine ulaşamaz. Sonra linki açıp adını yazsın ve "Katıl"a bassın.

**Arkadaşın Tailscale kurmadan (Funnel):** `.env`'de `TAILSCALE_FUNNEL=1` verirsen `run.py` bunun yerine `tailscale funnel`'ı başlatır: aynı `https://….ts.net` linki, ama bütün internete açık; arkadaşına sadece tarayıcı yeter. İlk seferde `tailscale funnel` bu bilgisayar için Funnel'a izin verme linkini yazar. Odayı o zaman sadece linkteki anahtar korur; linki yalnızca birlikte izleyeceğin kişilere gönder. Ses ve kamera ev modemlerini Cloudflare'in ücretsiz STUN sunucusuyla aşar; bazı ağlarda (sıkı şirket ya da mobil ağlar) yine de bağlanamayabilir. Film Tailscale'in aktarıcı sunucularından geçer, bunların Tailscale'in açıklamadığı bir bant sınırı var. Bir ölçümde evin upload'u yaklaşık 30 Mbps iken Funnel üzerinden izleyiciye yaklaşık 7–8 Mbps ulaştı; yani yaklaşık 5–6 Mbps'e kadar dosyalar rahat oynar. Daha ağır dosyalar için `.env`'de `MAX_COPY_KBPS=5500` ver, dönüştürülsünler ("Upload hızı" bölümüne bak).

## Kullanım

1. **Film aç:** kendi dosyan için "Bu bilgisayardaki dosya yolu"na tam yolu yaz (bu alan güvenlik için sadece host bilgisayarda görünür). Torrent için magnet linkini yapıştırıp "Torrent ekle"ye bas; torrent'te birden fazla video varsa listeden seç.
2. **Göz at:** "Göz at" kartı [Stremio eklentilerinin](https://github.com/Stremio/stremio-addon-sdk/blob/master/docs/protocol.md) kataloglarını gösterir: afişler, arama, sezonlar ve bölümler, eklentilerin bir film ya da bölüm için bildiği kaynaklar. "Aç" bir kaynağı herkes için oynatır. İçerik barındırmayan iki eklenti hazır gelir: Cinemeta (katalog ve bilgiler) ve Public Domain Movies (telif süresi dolmuş filmler). Host, "Eklentiler" altından başka eklentileri `…/manifest.json` adresiyle ekleyebilir; bunlar sadece o bilgisayarda, `data/addons.json`'da durur. Eklentiden açılan bir film için "Altyazı ekle" altındaki "Eklentilerde ara", o eklentilerin sunduğu altyazıları filmin kimliği ve dosya hash'iyle listeler.
3. **Altyazı ekle:** "Altyazı ekle" altında dil kodlarını yazıp OpenSubtitles'ta ara (ör. `tr,en,ru`) ya da `.srt/.ass/.vtt` dosyası yükle. Türkçe `cp1254`, Rusça `cp1251` gibi eski kodlamalar otomatik düzeltilir.
4. **Kendi altyazını seç:** yüklenen altyazılar odadaki herkesin listesine gelir ama kimin ekranında ne görüneceğini herkes kendisi seçer. "Ana altyazı" alttaki büyük beyaz satırdır. "İkinci altyazı" isteğe bağlıdır ve üstte küçük sarı satır olarak çıkar; iki dili aynı anda izlemek içindir (sen TR + EN, arkadaşın RU + EN gibi). Zaman kaydırma, yazı boyutu ve yükseklik de kişiye özel. Tercih edilen dil hatırlanır; yeni filmde o dilde altyazı varsa otomatik seçilir.
5. **İmleç ve dürtme:** videonun üstünde herkesin imleci, adı ve rengiyle gözlü bir top olarak görünür (4 sn kıpırdamayınca kaybolur). Videoya tıklamak topun gözlerini kırptırır, bir halka yayar ve herkese kısa bir ses çalar; ses her renkte farklı perdede. Sesi sağdaki çan kapatır. Videoya tıklamak filmi durdurmaz; oynat/durdur için boşluk tuşu ya da buton.
6. **Çizim:** sağdaki kalemle (`d`) video üstüne çiz; herkes canlı görür, çizgiler ekran boyutundan bağımsız olarak filmin aynı yerine düşer. Film oynarken çizgiler birkaç saniyede silinir, durdurulmuşken kalır. Renk düğmesi rengini değiştirir (top ve kalem aynı renk), çöp kutusu herkesin çizimini temizler.
7. **Ses:** zamanın yanındaki mikrofon tuşu (`Ctrl+D`) mikrofonunu açıp kapatır; kapalı başlar, kırmızıysa kapalıdır. Ses sunucudan geçmeden doğrudan diğerlerine gider. Kapatınca mikrofon gerçekten bırakılır (sekmedeki kırmızı nokta söner), adının yanında üstü çizili mikrofon görünür. Konuşan kişi üstte ve topunda kendi renginde parlar, film sesi o sırada kısılır. Tuşun yanındaki ok mikrofonu seçtirir ve kısmayı kapatır. Üstte birinin adına tıklayıp onu ne kadar yüksek duyacağını ayarlayabilirsin. Yankı hoparlörle denenene kadar kulaklık kullan. Arkadaşların için HTTPS linki gerekir (Kurulum'a bak); tarayıcılar düz http'de mikrofonu açmıyor.
8. **Kamera:** kamera tuşu (`Ctrl+E`) aynı şekilde çalışır; kapatınca kameranın ışığı söner. Birinin kamerası açıkken videonun sağ üstünde, filmi küçültmeden küçük kutular çıkar: kamerası açık olanın görüntüsü, kapalı olanın renkli topu, en altta ayna gibi çevrilmiş kendi görüntün. Kutular tam ekranda da kalır; telefonda üstte yan yana dizilir. Tuşun yanındaki ok kamerayı seçtirir, kendi kutunu ya da bütün kutuları gizler. Bir kutuya tıklayınca o kişinin ses seviyesi açılır. Kutuları sürükleyip istediğin köşeye taşıyabilirsin; köşelerindeki küçük tuş onları küçültür. Kamera her izleyiciye en fazla yaklaşık 0,5 Mbps gönderir.
9. **Girmeden önce:** giriş ekranında Meet'teki gibi önizlemeli mikrofon ve kamera tuşları ve ses göstergesi var; orada açtığın şey odaya girince de açık kalır. İkisi de kapalı başlar.
10. **Bağlantı koparsa:** sayfa odaya kendiliğinden yeniden bağlanır; kopan ses ve kamera bağlantıları (Wi-Fi değişimi, dizüstünün uykuya geçmesi) kendiliğinden yeniden kurulur.
11. **Kısayollar:** boşluk oynat/durdur, ← → 10 sn, `f` tam ekran, `m` film sesi, `d` kalem, `Ctrl+D` mikrofon, `Ctrl+E` kamera, `Esc` kalemi kapat. Dokunmatik ekranda videoya dokunmak sadece kontrolleri gösterir; herkes için durdurmak buton ister.

Arayüz Türkçe, İngilizce ve Rusça kullanılabiliyor.

## Hızlı deneme

Tek bilgisayarda, iki tarayıcı penceresiyle:

1. Proje klasöründe test videosu üret. 2 dakikalık video, saniyeyi ekranda büyük rakamla gösteriyor; torrent dosyaları gibi H.264 video ve AC3 5.1 ses içeriyor:
   ```powershell
   ffmpeg -f lavfi -i testsrc=size=1280x720:rate=24 -f lavfi -i "sine=frequency=440" -t 120 -c:v libx264 -g 48 -pix_fmt yuv420p -af volume=0.1 -c:a ac3 -ac 6 samples\test-video.mkv
   ```
2. `.\.venv\Scripts\python run.py` ile başlat, "Bu bilgisayardan" linkini aç, adını yaz ve Katıl'a bas.
3. "Bu bilgisayardaki dosya yolu" alanına `samples\test-video.mkv` dosyasının tam yolunu yapıştır. Dosya Gezgini'nde dosyaya sağ tıklayıp "Yol olarak kopyala" diyebilirsin; tırnaklar sorun değil.
4. Aynı linki gizli pencerede aç ve başka bir adla katıl.
5. "Altyazı ekle" altında ilk pencerede `samples\test.tr.srt` dosyasını `tr` diliyle, ikinci pencerede `samples\test.ru.srt` dosyasını `ru` diliyle yükle. İki dosya da eski kodlamalı (cp1254 ve cp1251); Türkçe ve Rusça harfler düzgün görünmeli.
6. Oynat. Altyazıdaki saniye ekrandaki büyük rakamla aynı olmalı ve iki pencere aynı karede kalmalı. İleri sarmayı, durdurmayı ve ±0.5 kaydırmayı dene.
7. Fareyi bir pencerede videonun üstünde gezdir: diğer pencerede adın ve renginle top görünür. Tıkla: top göz kırpar, iki pencerede de ses çalar. `d` ile kalemi açıp çiz; çizgi diğer pencerede aynı yerde belirir.

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
| `TAILSCALE_SERVE` | 1 | Tailscale çalışıyorsa Tailscale Serve ile HTTPS linki, 0 = düz http linkleri |
| `TAILSCALE_FUNNEL` | 0 | 1 = HTTPS linki Tailscale Funnel ile, internete açık: arkadaşların Tailscale kurmaz |
| `ADDONS_BUILTIN` | 1 | 0 = hazır eklentiler (Cinemeta, Public Domain Movies) olmadan, sadece elle eklenenler |
| `ICE_SERVERS` | – | Ses ve kamera için virgülle ayrılmış `stun:` adresleri; boş = sadece izleyicilerin kendi adresleri (Tailscale üzerinden), Funnel'da Cloudflare'in STUN'u |
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

Co-Watch içerik sağlamaz, barındırmaz ve dağıtmaz. Kendi dosyaların ya da izleme ve paylaşma hakkın olan içerik için tasarlandı. Torrent desteği protokolün kendisi içindir; telifli içerikte torrent kullanmak IP adresini swarm'da görünür kılar ve izlerken yükleme de yapılır. Co-Watch Stremio eklenti protokolünü destekler; hazır gelen eklentiler içerik barındırmaz (katalog ve bilgiler için Cinemeta, telif süresi dolmuş filmler için Public Domain Movies). Başka hangi eklentileri eklediğin senin seçimin ve sorumluluğun. Kullanımdan doğan sorumluluk kullanana aittir.

## Geliştirme

```bash
pip install -r requirements-dev.txt
python -m pytest                      # ffmpeg kuruluysa medya testleri de çalışır
python -m playwright install chromium # bir kere, tarayıcı testleri için
python tests/e2e/two_viewers.py       # senkron, altyazı, imleç, dürtme, kalem; izlemek için --headed
python tests/e2e/voice_camera.py      # ses ve kamera
```

Her tarayıcı testi kendi sunucusunu ve test videosunu başlatıp Chromium pencereleri açar. `two_viewers.py` senkronu, herkesin kendi altyazısını, imlecin bantlı videoda başka ekran boyutunda da aynı noktaya düştüğünü, dürtme sesini, kalemi ve temizlemeyi dener. `voice_camera.py` Tailscale Serve'den gelen bir arkadaş olarak katılır; sesi, kamera kutularını, önizlemeden katılan üçüncü bir izleyiciyi ve bağlantıların kendiliğinden yeniden kurulmasını dener (Chromium'un sahte kamerası, mikrofon yerine sentezlenmiş konuşma).

Tarayıcı konsolunda `cowatchDebug()` senkron değerlerini gösterir (film zamanı, beklenen konum, fark).

Dosyalar: `server/` (FastAPI: oda, senkron, medya, altyazı, imleç ve çizim, ses ve kamera sinyalleri, eklentiler), `torrent-helper/` (Node: magnet → HTTP akış), `web/` (istemci; hls.js `web/vendor` içinde, Apache-2.0).

## Sonraki fazlar

2. Altyazı otomasyonu: dil tercihli fallback zinciri, alass ile hizalama, iki aşamalı LLM çevirisi.
3. Sadece link ile katılım (DataChannel + TURN), bitrate yetmezse otomatik dönüştürme.
4. Ses ve kamera eklendi; gerçek cihazlarla denenecek: hoparlörle yankı, telefon, Tailscale üzerinden iki bilgisayar.
5. Çift taraflı torrent senkronu ve DRM'li platformlar için eklenti.

## Lisans

[GNU AGPL v3.0](LICENSE) ya da sonraki sürümleri. Kısaca: kullanabilir, değiştirebilir ve dağıtabilirsin; değiştirdiğin bir sürümü başkalarına ağ üzerinden sunarsan kaynak kodunu da onlara açman gerekir. Bu yüzden uygulamanın giriş ekranında kaynak koda link var.

`web/vendor/hls.light.min.js`: [hls.js](https://github.com/video-dev/hls.js), Apache-2.0 (`web/vendor/hls.js.LICENSE`).
