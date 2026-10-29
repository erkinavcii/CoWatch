# Gelecek planları

> Şimdilik yapılmayacak işler; genel program tamamlandıktan sonra ele alınacak. Her başlık, başlamadan önce ayrı bir plan belgesine dönüşebilir (kamera-ses planı gibi).

## Dağıtım ve paketleme (Windows)

Amaç: teknik bilgisi olmayan biri `run.py`, `.env` ve Tailscale komutlarıyla uğraşmadan filmi yayınlayabilsin. Kurulum dosyasını çalıştırır, masaüstündeki simgeye tıklar, ayarları bir sayfadan değiştirir, arkadaşına linki gönderir. Arkadaşlar için değişen bir şey yok: onlara yine sadece link gider.

### Kararlar (29 Ekim 2026)

| Konu | Karar |
| --- | --- |
| Dağıtım biçimi | Kurulum dosyası (Inno Setup): Başlat menüsü kısayolu ve kaldırıcı |
| İlk açılışta bağlantı | Funnel: arkadaş hiçbir şey kurmaz |
| Daha yüksek kalite isteyenler | Ayarlardan Serve: arkadaş Tailscale kurar, sınır Funnel'ın ≈ 7–8 Mbps'i yerine host'un upload'u olur |
| Torrent desteği pakette | Önerilen: evet (paketi ≈ 90 MB büyütür); başlarken kesinleştirilecek |

### Kullanıcının göreceği

1. **`CoWatch.exe`:** Çift tıklayınca tepsiye (sağ alt köşe) bir simge yerleşir ve tarayıcıda oda açılır. Tepsi menüsü: Odayı aç · Arkadaş linkini kopyala · Ayarlar · Çıkış.
2. **Ayarlar sayfası:** Web arayüzünün içinde, sadece host'a görünür; `.env`'in yerini alır. Kaydedince sunucu kendini yeniden başlatır.
   - **Bağlantı:** "Linki olan herkes" (Funnel, varsayılan) · "Tailscale'i olan arkadaşlar" (Serve, daha yüksek kalite) · "Sadece ev ağı".
   - **Kalite:** Otomatik (Funnel'da 5,5 Mbps üstü dosyalar 4,5 Mbps'e küçültülür; Serve'de orijinal) · Her zaman orijinal · Elle Mbps.
   - **Ekran kartı:** Açılışta NVENC, QSV ve AMF kısa bir kodlamayla denenir, çalışan seçilir; hiçbiri çalışmazsa libx264. Kullanıcıya görünmez.
   - **İsteğe bağlı:** OpenSubtitles anahtarı; "Gelişmiş" altında port, torrent upload sınırı, `ICE_SERVERS`; "Yeni oda anahtarı üret" düğmesi.
3. **Paylaşım kartı:** Arkadaş linki, kopyala düğmesi, telefonla okutmak için QR kodu.
4. **Tailscale durumu**, trafik ışığı gibi:
   - Kurulu değil → "İndir" düğmesi (tailscale.com'a).
   - Kurulu ama kapalı → "Tailscale'i aç" (`tailscale-ipn.exe`'yi başlatır; yeniden başlatmadan sonra takılma sorunu buydu).
   - Oturum açılmamış → giriş yönlendirmesi.
   - Funnel ya da HTTPS izni yok → `tailscale funnel`'ın yazdığı onay linki düğme olarak; onaydan sonra Funnel kendiliğinden yeniden denenir.

### Paket içeriği

| Parça | Nasıl | Yaklaşık boyut |
| --- | --- | --- |
| Python ve sunucu | PyInstaller, klasör modu (tek dosya modu antivirüslere daha sık takılıyor) | 40 MB |
| ffmpeg ve ffprobe | Klasöre konur; yolları ayarlardan değil paketten gelir | 150 MB |
| Torrent yardımcısı | Taşınabilir `node.exe` ve `torrent-helper/node_modules` (node-datachannel'ın Windows ikilisi dahil) | 90 MB |
| Tailscale | **Paketlenmez:** kendi servisi ve sürücüsü var, hesabıyla girilmesi gerekiyor. Uygulama durumunu gösterip yönlendirir. | — |
| Ayarlar ve veriler | `%APPDATA%\CoWatch` (ayarlar, oda anahtarı, altyazılar, HLS geçici dosyaları); program klasörüne yazılmaz | — |

### Adımlar

1. **Ayarlar sayfası, paylaşım kartı ve Tailscale durumu.** Exe olmadan da işe yarar; `run.py` kullananlar da faydalanır.
   - Ayarlar `settings.json`'da; `.env` ve ortam değişkenleri varsa onlar kazanır (geliştiriciler için).
   - Ayarlar API'si sadece `is_local` isteklere açık.
   - Arayüz metinleri üç dilde; pytest ve tarayıcı testleri.
2. **Tepsi başlatıcısı.** `pystray` ile simge ve menü; sunucuyu alt süreç olarak başlatır, ayar değişince yeniden başlatır, çıkışta Funnel ve torrent yardımcısını da kapatır. Ekran kartı seçimi burada yapılır.
3. **Paketleme.**
   - Derleme betiği `tools/build_windows.ps1`: PyInstaller, ffmpeg ve Node'u indirip klasöre koyma, Inno Setup ile kurulum dosyası.
   - İsteğe bağlı: GitHub Actions her sürüm etiketinde kurulum dosyasını kendisi üretip Releases'e koyar.
4. **Güncelleme.** İlk sürümde yok: yeni kurulum dosyası eskisinin üstüne kurulur, ayarlar `%APPDATA%`'da kaldığı için korunur. Sonra: açılışta yeni sürüm var mı diye GitHub Releases'e bakıp haber vermek.

### Bilinenler ve riskler

- **SmartScreen:** İmzasız exe ilk açılışta "Windows bilgisayarınızı korudu" uyarısı verir ("Ek bilgi → Yine de çalıştır"). Kod imzalama sertifikası ücretli; arkadaş çevresi için şart değil.
- **Antivirüs:** PyInstaller paketleri bazen yanlışlıkla işaretleniyor; klasör modu bu riski azaltır.
- **Lisanslar:** Kullanılan ffmpeg derlemesi GPL. Pakete lisans metinleri ve kaynakların nereden alınacağı konur; projenin AGPL-3.0 lisansıyla uyumlu. hls.js (Apache-2.0) ve Node modüllerinin lisansları da aynı klasöre.
- **Tailscale bağımlılığı:** Host yine Tailscale kurmak zorunda. Bundan tamamen kurtulmak aşağıdaki "sadece link" işinin konusu.
- **macOS ve Linux:** Bu planın dışında. Aynı yapı (tepsi ve ayarlar sayfası) oralara da taşınabilir; paketleme ayrı iş.

## Eklentiler (Stremio protokolü)

> **Durum (29 Ekim 2026):** 1, 3 ve 4. adımlar kodlandı (`server/addons.py`, "Göz at" kartı, eklentilerden altyazı, film kimliğiyle OpenSubtitles araması). 2. adımdan şimdilik "Göz at" içindeki basit eklenti listesi var (ekle, kaldır); ayarlar sayfası dağıtım planıyla gelecek. OpenSubtitles anahtarının nasıl alınacağı şimdilik altyazı kartındaki ipucunda ve linkte.

Amaç: film ve dizileri afişli bir katalogdan seçip açmak; altyazıları da film kimliği ve dosya hash'iyle kendiliğinden bulmak. Stremio'nun eklenti protokolü açık ve basit (HTTP üzerinden JSON), bu yüzden Stremio eklentileri olduğu gibi kullanılabilir.

### Kararlar (29 Ekim 2026)

| Konu | Karar |
| --- | --- |
| Destek biçimi | **Genel eklenti desteği:** bir eklenti `manifest.json` adresiyle eklenir; kod hiçbir eklentiye özel değil |
| Depoda hazır gelenler | Sadece yasal ve içerik barındırmayanlar: **Cinemeta** (katalog, afiş, sezon ve bölüm bilgisi), **Public Domain Movies** (telifsiz filmler) |
| Diğer eklentiler (torrent katalogları vb.) | **Kişisel kalır, depoya girmez.** Kullanıcı adresini kendi ayarlarına ekler; liste git'e girmeyen bir dosyada durur (`data/addons.json` ya da `.env`). Depoda, README'de ve testlerde bu tür eklentilerin adı ya da adresi geçmez. README'deki "Co-Watch içerik sağlamaz, aramaz ve dağıtmaz" ilkesi böylece korunur. |
| OpenSubtitles | Stremio'nun OpenSubtitles eklentisi **kullanılmaz** (ilk tasarımdaki karar: kota başka servislerin sunucuları üzerinden aşılmaz). Bugünkü doğrudan OpenSubtitles bağlantısı kalır; ayarlar sayfası kullanıcıya **kendi API anahtarını ve hesabını** nasıl alacağını adım adım gösterir. İsteğe bağlı: anahtar yoksa altyazı elle yüklenir. |
| YouTube | Sonraya: oynatmak için yt-dlp gerekir ve YouTube'un kullanım koşullarına takılır |
| DRM'li platformlar (WatchHub gibi) | Sadece "şurada izlenebilir" linki gösterilir; bu filmler oynatılamaz (DRM) |

### OpenSubtitles anahtarı: ayarlar sayfasında gösterilecek yol

1. [opensubtitles.com](https://www.opensubtitles.com)'da ücretsiz hesap aç.
2. [opensubtitles.com/consumers](https://www.opensubtitles.com/consumers) sayfasında bir "API consumer" oluştur; verilen **API anahtarını** kopyala.
3. Ayarlar sayfasına API anahtarını, kullanıcı adını ve şifreyi gir (bugün `.env`'deki `OPENSUBTITLES_API_KEY`, `OPENSUBTITLES_USERNAME`, `OPENSUBTITLES_PASSWORD`).
4. Kota: girişsiz IP başına günde yaklaşık 5 indirme; hesapla daha fazla; VIP üyelikte günde 1000. Ücretsiz hesabın sınırı kaynaklarda farklı geçiyor (20 ve 200), bu yüzden sayfada sabit bir sayı yazılmaz. OpenSubtitles her indirmede kalan hakkı döndürüyor (bugün de saklanıyor, `remaining`); ayarlar sayfası bunu gösterir.
5. Altyazılar dosya hash'iyle önbelleğe alındığı için aynı film için ikinci kez hak harcanmaz.

### Protokol ve bizdeki karşılığı

| Kaynak | İstek | Döner | Bizde |
| --- | --- | --- | --- |
| Katalog | `/catalog/{tür}/{id}.json`, arama için `/catalog/{tür}/{id}/search={metin}.json` | Afişli liste | Yeni "Göz at" paneli |
| Bilgi | `/meta/{tür}/{id}.json` | Özet, sezonlar, bölümler | Bölüm seçimi |
| Akış | `/stream/{tür}/{id}.json` | `infoHash` + `fileIdx` (torrent), `url` (HTTP), `ytId`, `externalUrl` | `infoHash` + `fileIdx` bugünkü torrent yardımcısıyla açılır (magnet `infoHash` ve `sources`'taki tracker'lardan kurulur); `url`'yi ffmpeg doğrudan okur; `ytId` ve `externalUrl` oynatılmaz |
| Altyazı | `/subtitles/{tür}/{id}/videoHash={hash}&videoSize={boyut}.json` | Dil ve dosya adresi listesi | Bugünkü altyazı deposu ve kodlama düzeltmesi |

### Adımlar

1. **Sunucu, `server/addons.py`:** manifest okuma ve doğrulama, katalog, bilgi, akış ve altyazı sorguları, kısa süreli önbellek, zaman aşımı. Akışlar mevcut `/api/media/open`'a bağlanır. pytest'te sahte bir eklenti sunucusuyla.
2. **Ayarlar:** eklenti listesi (ekle, kaldır, sırala). Hazır gelenler depodan; kullanıcının ekledikleri git'e girmeyen dosyada. Dağıtım planındaki ayarlar sayfasıyla birleşir; o sayfa yoksa önce basit bir liste.
3. **Arayüz:** afişli göz atma ve arama, dizide sezon ve bölüm seçimi, akış listesi (kalite, boyut, kaynak). Seçilen akış herkes için açılır. Arayüz metinleri üç dilde.
4. **Altyazı:** film açılınca altyazı veren eklentilere ve OpenSubtitles'a film kimliği ve dosya hash'iyle sorulur, bulunanlar listeye düşer. Faz 2'deki otomatik altyazının ilk adımı.

### Bilinenler ve riskler

- **Hukuki duruş:** Depodaki kod ve hazır eklentiler yasal içerikle sınırlı; kişisel eklentilerin sorumluluğu ekleyende. README'deki yasal not buna göre güncellenir: "Co-Watch eklenti protokolünü destekler; hangi eklentiyi eklediğin senin sorumluluğun."
- **Torrent akışlarında bant:** Eklentiden gelen torrent de bugünkü torrent ile aynı yoldan geçer; Funnel'da 5,5 Mbps üstü dosyalar dönüştürülür (bkz. `.env` notları ve README).
- **Eklentilerin güvenilirliği:** Üçüncü taraf eklentiler kapanabilir, yavaşlayabilir; sorgular zaman aşımıyla yapılır, biri cevap vermezse diğerleri gösterilir.
- **Kimin ne açabileceği:** Bugün torrent eklemek herkese açık. Eklentiden film açmak da öyle kalabilir; eklenti listesini değiştirmek sadece host'a.

## Diğer gelecek işler

- **Faz 2, altyazı otomasyonu:** dil tercihli yedek zinciri, alass ile hizalama, iki aşamalı LLM çevirisi (README'deki "Sonraki fazlar").
- **Faz 3, sadece link:** film parçaları da eşler arası (WebRTC DataChannel), doğrudan bağlantı olmazsa Cloudflare TURN. Funnel'ın bant sınırını ve host'un Tailscale bağımlılığını kaldırır.
- **Kişi başına %100 üstü ses:** hoparlörle yankı denemesinden sonra gerekirse (`GainNode`); kamera-ses planı, Ses bölümü.
- **İki izleyicinin Funnel sınırını paylaşıp paylaşmadığı:** ölçülmedi; 3 kişilik ilk gerçek denemede bakılacak.
