# Araştırma: HEVC'yi çevirmeden yollama (İP-10)

> **Durum: kodlanmadı, eksik kaldı.** Bu dosya sadece araştırma ve plan; bugün H.264 olmayan her film hâlâ çevriliyor. Proje sahibinin kararı (12 Kasım): kodlanırken kullanıcıya soru ya da ayar olmayacak (herkes ileri düzey kullanıcı değil); kopya mı çeviri mi kararını program her izleyicinin tarayıcısına bakarak kendisi verir, desteklemeyen biri gelince de kendisi çeviriye döner. Aşağıda geçen `HEVC_COPY` ayarı bu yüzden yok: ilk sürüm kendiliğinden sadece SDR HEVC'yi kopyalar, HDR ve DV 8 gerçek cihazlarda denendikten sonra yine ayarsız açılır.

12 Kasım 2026. Soru: odadaki bütün tarayıcılar HEVC (H.265) oynatabiliyorsa Co-Watch filmi H.264'e çevirmeden, kopya kipiyle yollayabilir mi? Bugün H.264 olmayan her film çevriliyor (`decide_mode`); 1,1 Mbps'lik x265 Daredevil bölümü ≈ 2,2 Mbps H.264 oluyor.

Kısa cevap: **evet, koşullu.** Bu bilgisayarda Chrome 157 ve Edge 157, `-c:v copy -tag:v hvc1` ile yapılmış HLS fMP4'ü hls.js'le oynattı (8-bit, 10-bit, HDR10, Dolby Vision profil 8 dahil); sarma çalıştı, akış ≈ 2,6 kat küçük, ffmpeg'in işlemci zamanı 6–12 kat az. Ama destek tarayıcıya ve donanıma bağlı (Playwright'ın kendi Chromium'u, Firefox'un çoğu kurulumu hayır diyor), bu yüzden karar tarayıcı adına değil, her izleyicinin kendi `isTypeSupported` cevabına bakmalı ve desteklemeyen biri gelince akış çevirmeye dönmeli.

## 1. Tarayıcılar

### Bu bilgisayarda ölçülen (Windows 11 26200, RTX 4060 Ti, "HEVC Video Extensions" 2.5.48 kurulu, SDR ekran)

Aynı sayfa her tarayıcıda `MediaSource.isTypeSupported`, `canPlayType` ve `navigator.mediaCapabilities.decodingInfo` sordu, sonra paketteki hls.js 1.7.3'le akışları oynattı.

| Soru | Playwright Chromium 156 | Chrome 157 | Edge 157 |
| --- | --- | --- | --- |
| `video/mp4; codecs="hvc1.1.6.L120.90"` (Main, 1080p) | false | true | true |
| `hev1.1.6.L120.90` | false | true | true |
| `hvc1.2.4.L120.90` (Main 10) | false | true | true |
| `hvc1.2.4.L153.90` (Main 10, 4K) | false | true | true |
| `dvh1.08.06`, `dvh1.05.06` (Dolby Vision) | false | false | false |
| `avc1.640028` | true | true | true |
| `decodingInfo` 1080p ve 4K PQ: supported / smooth / powerEfficient | hayır | evet / evet / evet | evet / evet / evet |
| hls.js ile oynatma | `bufferAddCodecError` (ölümcül) | oynadı | oynadı |

Oynatılan akışlar (her biri hls.js'le açıldı, 3 sn sonra ortaya sarıldı, 5 sn izlendi; Chrome ve Edge aynı sonucu verdi):

| Akış | Sonuç |
| --- | --- |
| Sentetik 1080p, 8-bit, `hvc1` ve `hev1` | 1920×1080, 5 sn'de 124 kare, düşen yok |
| Sentetik 10-bit; 10-bit + HDR10 (PQ, mastering bilgisi) | oynadı; HDR olanda 2–5 düşen kare |
| Daredevil S01E01 (Joy, x265 Main, 1,1 Mbps), 15:00'ten kopya | oynadı, sarma 53–75 ms |
| Daredevil S01E06 (RARBG, x265 Main 10, MP4, `hev1` etiketli kaynak) | oynadı, sarma 106–122 ms |
| Blade Runner 2049 (4K, 3840×1600, Main 10, PQ, Dolby Vision profil 8.1, 16 Mbps) | oynadı, sarma ≈ 230 ms |

Gerçek dosyalarda hls.js ölümcül olmayan bir `bufferAppendNoProgress` uyarısı verdi (ilk parça; kopyada ilk parça istenen yerden önceki anahtar kareden başlıyor). Oynatmayı bozmadı; bugünkü H.264 kopyasında da olup olmadığına bakılmadı.

Playwright'ın Chromium'u HEVC'siz (Chromium'un kendi derlemesinde HEVC yok, Chrome markalı derlemede var). Yani tarayıcı testleri HEVC kopyasını sadece `channel="chrome"` ya da `"msedge"` ile deneyebilir; CI'da hiç.

### Kaynaklardan (bu bilgisayarda denenmedi)

- **Chrome (Windows, Mac, Android, Linux):** 107'den beri donanımla HEVC çözme varsayılan açık; yazılımla çözme yok, yani kartı ya da işlemcisi HEVC çözemeyen bilgisayarda hayır der. Windows'ta Chrome D3D11VA'yı doğrudan kullanır, "HEVC Video Extensions" gerekmez; Edge Windows'un Media Foundation çözücüsünü kullandığı için uzantı gerekir (bu bilgisayarda kurulu). Main, Main 10 desteklenir; HDR10 ve HLG, HDR10+ HDR10'a düşer; Dolby Vision profil 8 ve 9 sadece `hvc1`/`hev1` diye sorulursa oynar, `dvh1`/`dvhe` "desteklenmiyor" der (bizim ölçümle aynı). Android'de Chrome 112'den beri cevap cihaza göre gerçek. Kaynak: [StaZhu/enable-chromium-hevc-hardware-decoding](https://github.com/StaZhu/enable-chromium-hevc-hardware-decoding), [Chrome 107 haberi (Neowin)](https://www.neowin.net/news/chrome-107-is-landing-today-with-hevc-decoding-support-despite-pushback-from-mozilla/), [caniuse: HEVC](https://caniuse.com/hevc).
- **Safari (macOS 11+, iOS 11+):** HEVC'yi donanımla oynatır (caniuse: Safari 13+ ve iOS 11+ "destekli"). Apple'ın oynatıcısı fMP4'te `hvc1` etiketini istiyor; `hev1` tartışmalı. hls.js 1.5'ten beri iOS 17.1+'da ManagedMediaSource ile çalışıyor, yani iPhone'da da bizim hls.js yolumuz kullanılır (`loadStream`'in ilk dalı); daha eski iOS'ta yerel HLS (ikinci dal). Kaynak: [Apple HLS yazım belirtimi](https://developer.apple.com/documentation/http-live-streaming/hls-authoring-specification-for-apple-devices), [Apple geliştirici forumu: hvc1/hev1](https://developer.apple.com/forums/thread/132293), [FFmpeg bileti #10775](https://trac.ffmpeg.org/ticket/10775), [Bitmovin: hvc1 ve hev1 farkı](https://community.bitmovin.com/t/whats-the-difference-between-hvc1-and-hev1-hevc-codec-tags-for-fmp4/101), [hls.js 1.5.0 notları](https://github.com/video-dev/hls.js/releases/tag/v1.5.0).
- **Firefox:** Windows'ta 134'ten beri donanımla HEVC (Windows 11 22H2+ ya da Microsoft'un uzantısı), Mac'te 136, Linux'ta 137. Ama MSE'de durum belirsiz: Windows 11 26200'de Firefox'un uzantı kurulu olduğu hâlde `isTypeSupported` için `hvc1` ve `hev1`'e false döndüğü bir destek sorusu var. Firefox'ta HDR yok. Kaynak: [Bugzilla 1941945](https://bugzilla.mozilla.org/show_bug.cgi?id=1941945), [Firefox 134 (Neowin)](https://www.neowin.net/news/firefox-134-finally-gets-windows-hardware-h265-support-improves-popup-blocking-and-more/), [Mozilla destek sorusu 1588979](https://support.mozilla.org/de/questions/1588979), [Bugzilla 1950032](https://bugzilla.mozilla.org/show_bug.cgi?id=1950032).
- **Opera GX:** resmî bilgi yok; forumlarda Opera'nın tescilli kodekler için işletim sistemine (Media Foundation) dayandığı ve sonuçların karışık olduğu yazıyor. caniuse Opera 94+ için "kısmi". Kaynak: [Opera forumu](https://forums.opera.com/post/394612).
- **Yandex Browser:** hiçbir kaynakta açık bilgi bulunamadı (resmî yardımda sadece dosya türleri var). Chromium tabanlı olduğu için büyük ihtimalle Chrome gibi davranır, ama denenmeden bilinemez. Kaynak: [Yandex yardım: video](https://yandex.ru/support/browser/ru/working-with-files/video).

Sonuç: Chrome ve Edge (Windows'ta çözebilen kart ya da işlemci), Safari ve çoğu Android Chrome evet; Firefox ve çatallar belirsiz. Tarayıcı adına göre karar verilemez; her sayfa kendisi sormalı.

### `hvc1` ve `hev1`

İkisi de fMP4'teki HEVC örnek girişinin adı. `hvc1`'de parametre kümeleri (VPS/SPS/PPS) sadece `init.mp4`'teki `hvcC` kutusunda; `hev1`'de akışın içinde de olabilir. Chrome ve Edge ikisini de oynattı (ölçüldü). Apple'ın oynatıcıları `hvc1` istiyor. ffmpeg'in mp4/HLS muxer'ı kopyada varsayılan olarak `hev1` yazıyor ve kendisi uyarıyor: "Stream HEVC is not hvc1, you should use tag:v hvc1 to set it." Bu yüzden her zaman `-tag:v hvc1`. Bir not: bazı kodlamalar (Blade Runner'da `repeat-headers`) parametre kümelerini her anahtar karede tekrarlar; `hvc1` etiketiyle bu kümeler akışta kalır. Chrome bunu sorun etmedi; Safari'nin edip etmediği denenmedi (gerekirse `-bsf:v filter_units=remove_types=32|33|34`).

## 2. ffmpeg tarafı

Denenen komut, `build_command`'ın kopya kipiyle aynı, sadece `-tag:v hvc1` eklendi:

```
ffmpeg -ss <yer> -i <dosya> -map 0:v:0 -map 0:a:0 -sn -dn -map_metadata -1 -map_chapters -1
  -c:v copy -tag:v hvc1 -c:a aac -b:a 192k -ac 2 -copyts -max_muxing_queue_size 4096
  -f hls -hls_time 4 -hls_list_size 0 -hls_playlist_type event -hls_segment_type fmp4
  -hls_fmp4_init_filename init.mp4 -hls_segment_filename .../seg_%05d.m4s
  -hls_flags independent_segments+temp_file .../index.m3u8
```

- **10-bit:** sorun yok. `init.mp4`'te Main 10, `yuv420p10le`; tarayıcı oynattı. Bugünkü `BROWSER_PIX_FMTS` kontrolü (sadece 8-bit) HEVC için `yuv420p10le`'yi de kabul etmeli; H.264 10-bit (High 10) tarayıcılarda oynamaz, o yine çevrilmeli.
- **HDR10:** renk bilgisi `colr` kutusunda (PQ, BT.2020) ve akışın SEI'lerinde kalıyor; `mdcv`/`clli` kutuları yazılmıyor. Chrome ve Edge SDR ekranda PQ'yu kendileri SDR'ye çevirdi: aynı karede tarayıcının resmi (ortalama parlaklık 34) bizim `zscale` + `hable` çevirimize (46) yakın renklerde, biraz daha karanlık; çevrilmemiş PQ'nun soluk, gri görüntüsüne (54, doygunluk düşük) benzemiyor (ekran görüntüleriyle karşılaştırıldı). Yani "soluk renk" Chrome ve Edge'de yok. HLG denenmedi.
- **Dolby Vision profil 8.1 (Blade Runner):** kopyada `dvcC` kutusu yazılmıyor, akış tarayıcıya düz HDR10 HEVC görünüyor ve oynuyor (temel katman HDR10 uyumlu). RPU NAL'larını `-bsf:v dovi_rpu=strip=1` ile silmek fark etmedi (ikisi de oynadı). **Profil 5** (HDR10 uyumlu temel katmanı yok, IPT renkleri) kopyalanırsa yeşil-mor renk verir; bugünkü `hdr_kind() == "dovi"` filmleri gibi çevrilmeye devam etmeli. Profil 7 (iki katmanlı BD) denenmedi; temel katman HDR10 olduğu için büyük ihtimalle profil 8 gibi.
- **Anahtar kareler ve parça boyu:** kopyada `-force_key_frames` yok (bugünkü H.264 kopyası da öyle); HLS muxer parçayı `hls_time`'dan (4 sn) sonraki ilk anahtar karede keser. Ölçülen: Daredevil (x265 `keyint=240`) parçaları 0,1–9,3 sn, RARBG (`keyint=250`) 0,8–10,4 sn, Blade Runner 0,5–10,4 sn; 120 sn'de 17–30 parça. Yani en uzun parça ≈ 10,4 sn (x265'in varsayılanı ≈ 10 sn; başka kodlamalarda daha uzun olabilir). Etkisi: sarmada ffmpeg istenen yerden 10 sn'ye kadar önce başlar (`measure_first_pts` ve `stream_start` bunu zaten hesaba katıyor), ilk parça biraz daha geç gelir; `RESUME` eşiği (3,5 sn) parçadan bağımsız. Parça boyu Funnel'da önemli: bir parça tek istekle iner, 10 sn'lik parça yavaş bağlantıda 30 sn ilk bayt sınırına (`HLS_LOAD_POLICIES`) yaklaşmaz (1 Mbps'lik akışta ≈ 1,3 MB).
- **Açık GOP:** dosyalardaki x265 ayarları okundu: Daredevil ve RARBG'nin hepsi `open-gop` (Blade Runner `no-open-gop`). Açık GOP'ta parça CRA karesiyle başlar, hemen ardından gelen RASL kareleri önceki parçaya bakar; sarmadan ya da akış yeniden başlayınca ilk parçanın birkaç karesi çözülemez ve atlanır. Ölçümde Daredevil sarmadan sonraki 5 sn'de 94–102 kare verdi (beklenen ≈ 120), sentetik kapalı GOP örnekler 124. Göze çarpan bir şey görülmedi ama `watchFrames`'in (4 sn kare gelmezse) yanlış alarmına yol açıp açmadığı gerçek oynatıcıda denenmeli.
- **`-copyts`:** sorun yok; hls.js zamanı ilk parçadan sayıyor, bizim `streamStart` düzeni aynı kalıyor. Not: `-t` gibi çıkış süreleri `-copyts` ile kaynağın zamanına göre okunur (deneyde çıkışa konan `-t 90` boş dosya verdi, girişe konunca çalıştı); kodda böyle bir seçenek yok, sadece deneyler için.
- **Ses** kopyada da AAC'ye çevriliyor (ucuz, değişmez).
- **4K:** kopya çözünürlüğü değiştiremez; `MAX_HEIGHT` (1080) kopyada uygulanamaz. 4K kaynak ya çevrilmeli ya da `MAX_HEIGHT`'ı aşan kaynak kopyalanmamalı.

## 3. Karma oda tasarımı

**İzleyici ne yollar:** `hello`'ya `hevc` alanı: `{main: bool, main10: bool, uhd: bool}`. Sorulacak yer hls.js'in kullanacağı MediaSource: `window.ManagedMediaSource || window.MediaSource` (iPhone'da ilki). Sorular: `hvc1.1.6.L123.90` (Main, 1080p), `hvc1.2.4.L123.90` (Main 10), `hvc1.2.4.L153.90` (4K). hls.js yoksa ve yerel HLS varsa (eski iOS) `video.canPlayType` ile aynı sorular. İsteğe bağlı: `mediaCapabilities.decodingInfo`'nun `smooth` cevabı da (zayıf telefonda 10-bit 1080p "var ama akıcı değil" olabilir).

**Sunucu nasıl karar verir:** `decide_mode(info, cfg, remote, viewers)`: kaynak HEVC ise, profil Main/Main 10, `hdr_kind` `None`, `pq` ya da `hlg` (`dovi` = profil 5 hayır), yükseklik ≤ `MAX_HEIGHT`, ve odadaki **bütün katılmış izleyiciler** (`joined`, host dahil) o profili destekliyorsa `"copy"`. Bit hızı kuralları (`MAX_COPY_KBPS`, `FUNNEL_BUDGET_KBPS × remote`) H.264 kopyası gibi aynen geçerli. Kimse katılmamışsa (film açılırken oda boş) güvenli taraf: çevir. Sebep film kartında: "HEVC, herkes oynatabiliyor, çevrilmeden".

**Sonradan desteksiz biri katılırsa:** retune'dan farklı olarak host'a sormak yetmez, çünkü o kişi hiçbir şey göremez. `hello`'da yeni bir `check_codecs`: akış HEVC kopyasıysa ve yeni izleyici desteklemiyorsa oturumun kipi çevirmeye döner ve `seek(şimdiki yer)` akışı yeniden başlatır (`can_serve` / `stream_fits` kip tutmayınca zaten hayır der). Herkes birkaç saniyelik bir duraklama görür; karta "Ahmet'in tarayıcısı HEVC oynatamıyor, film çevriliyor" yazılır. Desteksiz izleyici ayrılınca kendiliğinden geri dönülmez (retune'daki gibi: herkesin filmini kesmeye değmez); sonraki sarma ya da film kopyayı yeniden seçer.

**Yalan söyleyen tarayıcı:** `isTypeSupported` true deyip çözemeyen bir tarayıcı olabilir (sürücü, uzantı, 10-bit). hls.js'te `bufferAddCodecError` ya da HEVC akışında `watchFrames`'in kare gelmiyor kararı, o izleyiciyi sunucuda "HEVC yok" yapan bir `report` olur (`codec_failed`) ve yukarıdaki gibi çevirmeye dönülür. O tarayıcı `localStorage`'da hatırlanır, sonraki `hello`'da `hevc: false` gider. Ancak bu not tarayıcıyı sonsuza kadar kilitlememeli: tarayıcı sürümü/profilleri değiştiğinde ya da belirli bir süre sonunda sıfırlanıp yeniden denenebilmeli; ayrıca hata veren izleyici odadan çıkınca sonraki sarma ya da filmde oda yeniden kopya kipine geçebilmeli.

**Bekleyen ve yeniden bağlanan:** yeniden bağlanan sayfa yeni `hello` yollar; aynı cevabı verir, bir şey değişmez. Katılmamış ("?") sayfalar sayılmaz.

**HDR HEVC ve SDR ekran:** Chrome ve Edge SDR'ye kendileri çeviriyor (ölçüldü); Safari ekranına göre gösteriyor. Firefox HDR göstermiyor ama büyük ihtimalle HEVC'ye de hayır dediği için kopyaya girmez. İlk sürümde temkinli yol: sadece SDR HEVC kopyalansın, HDR HEVC (PQ, HLG, DV 8) birkaç gerçek cihazda bakıldıktan sonra açılsın; kullanıcıya sorulan bir ayar olmadan (en üstteki karar). Zaten 4K HDR kaynaklar genelde 15–20 Mbps ve `MAX_HEIGHT` ile bit hızı kuralları onları kopyadan çıkarır.

## 4. Beklenen kazanç (bu bilgisayardaki dosyalarla ölçüldü)

`data/torrents`'teki dosyalar sadece `ffprobe` ile okundu ve sadece okunan bir ffmpeg girişi oldular. Çevirme Co-Watch'un kendi `build_command`'ıyla (NVENC + `cuda` çözme, HDR'de `libplacebo`, hedef `target_kbps`), kopya aynı komutla `copy` + `-tag:v hvc1`; ikisi de filmin 15:00'inden 120 sn. Bit hızı parçaların toplamı (ses dahil, 192 kbps AAC).

| Dosya (kaynak video) | Çevirme: akış | Kopya: akış | Çevirme: süre / ffmpeg işlemci zamanı | Kopya: süre / işlemci |
| --- | --- | --- | --- | --- |
| Daredevil S01E01, Joy (x265 Main, 1,1 Mbps toplam) | 2495 kbps (hedef 2188k) | 946 kbps | 10,4 sn / 15,9 sn | 2,6 sn / 2,8 sn |
| Daredevil S01E06, RARBG (Main 10, 2,0 Mbps) | 3806 kbps (hedef 3996k) | 1426 kbps | 11,7 sn / 25,2 sn | 2,2 sn / 2,0 sn |
| Blade Runner 2049 (4K DV 8, 16 Mbps) | 5188 kbps, 1080p'ye inmiş (hedef 5000k) | 19360 kbps, 4K | 30,9 sn / 36,9 sn | 2,4 sn / 3,0 sn |

- Küçük x265 bölümlerinde akış ≈ 2,6 kat küçülüyor ve görüntü orijinal (çevirmenin kaybı yok). Funnel'ın ≈ 6 Mbps bütçesinde çevrilmiş Daredevil'e iki uzak izleyici sığıyor, kopyaya beş-altı.
- ffmpeg'in işlemci zamanı 6–12 kat az; ekran kartının kodlayıcısı ve çözücüsü hiç kullanılmıyor. Kopya 120 sn'lik filmi 2–3 sn'de üretiyor (≈ 50 kat gerçek zaman), yani açılış ve sarma sonrası ilk parça da daha erken.
- 4K HDR filmde kopya kazanç değil: 19 Mbps Funnel'a sığmaz ve 1080p'ye inemez. Bu filmler çevrilmeye devam etmeli.
- Daredevil dosyalarının yarısı (Joy) MKV'de akış bit hızı yazmıyor; bugünkü `source_video_kbps` toplamdan sesi çıkararak 1094 kbps buluyor, ölçülen kopyayla uyumlu.
- Torrent klasöründeki dört dosya yarım indiği için okunamadı (`moov atom not found`, EBML hatası); sayıları etkilemez.

## 5. Öneri: koşullu evet

Yapmaya değer: Daredevil gibi küçük x265 dizilerinde (bu bilgisayardaki dosyaların hepsi böyle) akış 2,6 kat küçülüyor, kalite orijinal, ekran kartı boşta, açılış ve sarma hızlanıyor. Koşullar:

1. Karar her izleyicinin kendi cevabıyla, herkes evet derse; boş odada ve bilinmeyende çevir.
2. Desteksiz izleyici gelince ya da bir tarayıcı çözemeyince akış kendiliğinden çevirmeye döner.
3. İlk sürüm sadece SDR HEVC, yükseklik ≤ `MAX_HEIGHT`, bit hızı kuralları aynı; HDR ve DV 8 denendikten sonra, ayarsız. DV profil 5 hiç.
4. Kalan elle denemeler 1. adımda yapılır: bir arkadaşın Yandex ya da Opera GX'i, bir Android telefon, bir iPhone (Safari), bir Firefox.

### Adımlar (fable.md 8. bölümün üslubunda)

**İP-10a. Tarayıcı ne oynatabiliyor.**
- Dosyalar: `web/app.js` (`hello`'ya `hevc`; `codecSupport()` küçük bir fonksiyon, `ManagedMediaSource || MediaSource`, yoksa `canPlayType`), `server/main.py` (`hello`'da `client.hevc`), `server/room.py` (`Client.hevc`, `members_msg`'de göstermeye gerek yok), `tests/test_api.py`.
- Bitti sayılır: `hello` alanı doğrulanıyor (bilinmeyen anahtar ya da bool olmayan değer `False`); pytest.

**İP-10b. Kopya kararı ve komut.**
- Dosyalar: `server/media.py` (`decide_mode`'a izleyicilerin desteği; `_video_args` kopyada HEVC için `-tag:v hvc1`; HEVC'de `yuv420p10le` kabul; `hevc_need(info)`: Main / Main 10 / 4K ve HDR türü), `server/main.py` (`Controller` film açarken ve `seek`'te izleyicilerin desteğini verir), `tests/test_media.py`.
- Kural: HEVC + profil uygun + SDR (`hdr_kind` yok; HDR sonra, `dovi` asla) + yükseklik ≤ `MAX_HEIGHT` + bütün katılmış izleyiciler evet + bit hızı kuralları → `copy`. `media` mesajında `codec: "hevc"`; film kartı sebebi yazar.
- Bitti sayılır: Daredevil benzeri örnekte (testteki gibi küçük sentetik x265, ffmpeg varsa) komutta `-c:v copy -tag:v hvc1` ve `init.mp4`'te `hvc1`; desteksiz bir izleyici varken `transcode`; DV profil 5 ve 4K'da `transcode`; pytest.

**İP-10c. Karma odada geri dönüş.**
- Dosyalar: `server/main.py` (`check_codecs`, `hello`'da `check_remote`'un yanında; `report`'ta `codec_failed`), `server/media.py` (`MediaSession.set_viewers_codec` → `stream_fits`'e kip), `web/app.js` (`loadStream`'in hata dalında `bufferAddCodecError` ve HEVC akışında `watchFrames` → `report('codec_failed')`, `localStorage`'da tarayıcı sürümüyle/süreli sıfırlanabilir biçimde hatırla), `web/i18n.js` (kart metni, tr/en/ru), `tests/test_api.py`.
- Bitti sayılır: HEVC kopyası oynarken `hevc: false` izleyici katılınca akış çevirmeye dönüyor ve herkese yeni `streamId` gidiyor; `codec_failed` aynı şeyi yapıyor; ayrılınca geri dönülmüyor.

**İP-10d. Tarayıcı testi.**
- Yeni `tests/e2e/hevc_copy.py`: iki sayfa `channel="chrome"` (yoksa `msedge`, ikisi de yoksa atla), sentetik 8-bit x265 film (açık GOP, `keyint=240`). Ölçüt: kopya kipinde iki sayfa da oynuyor, sarma çalışıyor, siyah resim yok (`sampleLuma`), konsolda ölümcül hata yok. Sonra Playwright'ın kendi Chromium'uyla üçüncü sayfa katılıyor: akış çevirmeye dönüyor, üç sayfa da oynuyor. `CLAUDE.md`'deki tarayıcı testleri listesine ekle.
- Not: HEVC'li tarayıcı CI'da yok; bu test sadece bu bilgisayarda.

**İP-10e. Elle deneme ve HDR.** Gerçek bir film gecesinde Daredevil'le: arkadaşların tarayıcıları (Yandex, Opera GX, telefon) ne cevap veriyor (`playback.log`'a `hello`'daki `hevc` yazılsın), açık GOP'ta `watchFrames` yanlış alarm veriyor mu. Sonra bir HDR10 film ve DV 8 (geliştirme sırasında kodda açılarak, kullanıcı ayarı olmadan); SDR ekranda renkler, iPhone'da Safari.

Sıra: 10a ve 10b birlikte, sonra 10c, sonra 10d; 10e elle. `web/app.js` ve `server/main.py` İP-8 ile ortak; aynı dalgaya konmamalı.

## Ölçülmeyenler ve bilinmeyenler

- Yandex Browser, Opera GX, Firefox, Safari (macOS, iOS) ve Android Chrome bu bilgisayarda denenmedi; satırlar kaynaklardan.
- HEVC çözemeyen bir Windows bilgisayarındaki Chrome (eski kart) denenmedi; kaynağa göre hayır der.
- HLG, DV profil 7, HDR ekranda görüntü denenmedi.
- `bufferAppendNoProgress` uyarısının bugünkü H.264 kopyasında da olup olmadığı.
- Açık GOP'un sarmadan sonra birkaç kare atlatması göze görünür mü, `watchFrames`'i tetikler mi.
- Ekran kartının ne kadar boşaldığı (sadece ffmpeg'in işlemci zamanı ve süresi ölçüldü, kartın kullanımı değil).

Deneylerin betikleri ve görüntüleri git'e girmedi (geçici klasörde: örnek x265 dosyaları, kopya HLS akışları, Playwright ile `isTypeSupported` ve oynatma, maliyet ölçümü).
