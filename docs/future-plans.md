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

## Diğer gelecek işler

- **Faz 2, altyazı otomasyonu:** dil tercihli yedek zinciri, alass ile hizalama, iki aşamalı LLM çevirisi (README'deki "Sonraki fazlar").
- **Faz 3, sadece link:** film parçaları da eşler arası (WebRTC DataChannel), doğrudan bağlantı olmazsa Cloudflare TURN. Funnel'ın bant sınırını ve host'un Tailscale bağımlılığını kaldırır.
- **Kişi başına %100 üstü ses:** hoparlörle yankı denemesinden sonra gerekirse (`GainNode`); kamera-ses planı, Ses bölümü.
- **İki izleyicinin Funnel sınırını paylaşıp paylaşmadığı:** ölçülmedi; 3 kişilik ilk gerçek denemede bakılacak.
