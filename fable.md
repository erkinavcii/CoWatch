# Co-Watch incelemesi: takılmalar, siyah ekran, hatalar, öneriler ve kodlama planı

> 11 Kasım 2026. Bu dosya bir inceleme raporu ve iş planıdır; bu commit'te kod değiştirilmedi, sonraki commit'ler bu planın uygulanmasıdır. Kodlama, sondaki iş paketleriyle alt ajanlara verilecek. Kanıtı olan şeyler "ölçüldü" ya da "kodda doğrulandı" diye, tahminler "tahmin" diye işaretli.

## 1. Kısa özet

1. **Takılmaların sebebi bant genişliği.** Sunucu, 1,1 Mbps'lik bir dosyayı 4,7 Mbps'e şişirip yolluyor; iki uzak izleyici 9,4 Mbps istiyor, Funnel 7–8 Mbps taşıyor (29 Ekim ölçümü). `data/playback.log`'daki 33 hatanın hepsi ağ zaman aşımı.
2. **Yavaş bir izleyici odayı gereğinden fazla durduruyor.** Deneyde bağlantısı filmin %65'i kadar olan tek bir izleyici, odayı 147 saniyede 9 kez durdurdu. Bunun bir kısmı kaçınılmaz, bir kısmı üç ayrı hatadan geliyor (bölüm 4, H1–H3).
3. **Siyah ekranı üretemedim.** Dört deneyde (masaüstü Chromium ve gerçek Android Chrome, yavaş ve kopan bağlantı) resim hiç kararmadı; bağlantı yetmeyince son kare donuyor. Yani siyah ekran yavaş bağlantının kendisi değil, başka bir tetikleyici. En güçlü aday kodda doğruladığım bir açık: **sunucunun bir izleyiciye mesaj göndermeyi sessizce bırakması** (H4). Kesinleştirmek için tanı eklenmesi gerekiyor (İP-4).
4. Bunların dışında 6 hata, 8 iyileştirme ve 9 özellik önerisi var; sonda 10 iş paketi.

## 2. Takılmalar: kanıt

### Kayıt (`data/playback.log`, 9–11 Kasım)

| Ne | Sayı |
| --- | --- |
| Toplam hata | 33 |
| Ağ zaman aşımı (`levelLoadTimeOut`, `fragLoadTimeOut`, `manifestLoadTimeOut`) | 33 |
| Kare donması (`frames_stalled`, eski siyah ekran) | 0 |
| Host'tan gelen hata | 0 |

- Hatalar sadece Funnel'dan gelen iki izleyicide: Marina (Yandex Browser, sonra Opera GX) ve "Tel" (Android Chrome).
- 10 Kasım 03:47:54–55'te ikisi aynı parçada (Daredevil S01E02, 180. saniye) aynı anda zaman aşımına düştü: sorun ortak yolda.
- Telefon 10 Kasım 04:12–04:15 arasında aynı yerde (872,9 sn) 3 dakika, ardından 1040,8'de 2 dakika kaldı.

### Bit hızı (ölçüldü)

| | Mbps |
| --- | --- |
| `Marvels Daredevil S01E05 … (1080p x265 Joy).mkv`, dosyanın tamamı | 1,10 |
| Aynı bölümün sunucunun ürettiği akışı (`data/hls/96ae6116ed74`, 834 parça, 3336 sn) | 4,71 |
| İki uzak izleyici | 9,42 |
| Funnel (29 Ekim, 64 MB indirme, iki deneme) | 7–8 |

Sebep `server/media.py` `_video_args`: çevirirken hedef her zaman `cfg.transcode_kbps` (Funnel'da 4500), kaynağın bit hızına bakılmıyor. Kaynak H.264 değilse (`decide_mode`) her film çevriliyor; x265 dosyalar küçük olduğu için şişme en çok onlarda.

Funnel'ın sınırını iki izleyicinin paylaştığı ölçülmedi; kayıttaki eşzamanlı takılmadan çıkarılan sonuç. Sunucu inceleme sırasında kapalıydı, Funnel yeniden ölçülmedi.

## 3. Deneyler

Betikler oturumun geçici klasöründe (`slowlink.py`, `slowlink2.py`, `emu_slow.py`); İP-2 bunları kalıcı bir tarayıcı testine çevirecek. Film: 1080p, 4,59 Mbps H.264 (kopya kipi), 4 sn'lik parçalar. Her yarım saniyede her sayfanın film zamanı, tamponu, oda durumu ve resmin parlaklığı (videonun küçük bir tuvale çizilip ortalaması; Android'de ekran görüntüsünden) kaydedildi.

| # | Kurulum | Sonuç | Siyah |
| --- | --- | --- | --- |
| 1 | Host + 3 Mbps'e kısılmış izleyici, 147 sn | 93 sn film oynadı; oda 9 kez durdu | Yok |
| 2 | Host + 1,2 Mbps + 5,5 Mbps'lik üçüncü izleyici, 197 sn | 56 sn film; sunucu yavaş izleyiciyi 5 kez "20 sn oldu" diye bıraktı, o hemen yeniden durdurdu | Yok |
| 3 | İzleyicinin bağlantısı 50 sn tamamen kesildi | Resim son karede dondu (parlaklık 127); oda onsuz devam etti; bağlantı gelince 4 sn'de odaya döndü | Yok |
| 4 | Gerçek Android Chrome (Pixel 8a emülatörü), 1,5 Mbps, 147 sn | 48 sn film; beklerken son kare, üstünde karartma (parlaklık 90, normal 126) | Yok |

Deneylerden çıkan hatalar bölüm 4'te (H1, H2, H3).

## 4. Hatalar

Hepsi kodda doğrulandı; H1–H3 deneyde de görüldü.

### H1. Yeniden başlama eşiği parça uzunluğuna eşit (dur-kalkı ikiye katlıyor)

`web/app.js` `syncTick`: bekleyen izleyici "önümde 4 sn var" deyince oda devam ediyor (`ahead >= 4`). Parçalar da 4 sn. İzleyici bir parça sınırında takıldığı için inen ilk parça tamponu 3,99… sn yapıyor, eşik tutmuyor, ikinci parça bekleniyor. Deney 2'de izleyici 8 sn boyunca "4,0 sn hazır" olduğu halde oda bekledi, sonunda 20 sn kuralı devreye girdi.

### H2. 20 sn sonra bırakılan izleyici odayı hemen yeniden durduruyor

`server/room.py` `BUFFER_TIMEOUT_S = 20`, `server/main.py` `watchdog_loop`: 20 sn bekleyen izleyicinin bayrağı siliniyor ve oda devam ediyor. Ama o izleyici birkaç saniye sonra yine `buffering` gönderiyor ve sunucu yine herkesi durduruyor. Deney 2'de bu döngü 30 saniyede bir tekrarlandı. Bırakılan izleyiciden bir süre (öneri: 60 sn ya da odaya yetişene kadar) `buffering` kabul edilmemeli.

### H3. İstemci, sunucunun bayrağı sildiğini bilmiyor

`web/app.js` `S.bufferingSent`: sunucu bayrağı 20 sn sonra silince istemcide `true` kalıyor. İstemci `state.waiting` listesinde kendi kimliğinin olmadığını görünce bunu sıfırlamalı; yoksa sonraki takılmada `buffering` gönderme kararı yanlış duruma göre veriliyor.

### H4. Sunucu bir izleyiciye göndermeyi sessizce bırakabiliyor ("zombi bağlantı")

`server/room.py` `Client._send`: bir mesaj 10 sn içinde gönderilemezse `alive = False` oluyor. Bundan sonra o izleyiciye **hiçbir mesaj gitmiyor**, ama:
- bağlantı kapatılmıyor, izleyici odadan çıkarılmıyor (`alive`'a sadece `send` bakıyor);
- istemcide "sunucudan ses gelmiyor" denetimi yok (`ping` gönderiliyor, `pong` gelmezse hiçbir şey olmuyor);
- o izleyicinin gönderdiği mesajlar (örneğin `buffering`) hâlâ işleniyor.

Sonuç: bağlantısı uzun süre takılan bir izleyicinin sayfası açık kalır ama odadan kopar. Durdurma, sarma, devam etme ona ulaşmaz; akış yeniden başlarsa (`media` mesajı, yeni `streamId`) eski akışı istemeye devam eder, o klasör silinince tamponu biter. Sayfayı yenileyene kadar düzelmez. **Kullanıcının anlattığı "bekleme yazısından sonra ikinci kişinin siyah ekrana düşmesi" ile en çok örtüşen açık bu** (tahmin: gerçekte olanın bu olduğu doğrulanmadı; 10 sn'lik gönderme zaman aşımının Funnel takılmasında dolup dolmadığı ölçülmedi).

### H5. Tarayıcı yavaş isteği 10 sn'de kesip baştan istiyor

`web/app.js` `loadStream`: hls.js varsayılan ayarlarla kuruluyor (ilk bayt için 10 sn). Dolu hatta zaman aşımına düşen istek iptal edilip yeniden başlıyor, yarım inen veri çöpe gidiyor. Kayıttaki 33 hatanın tamamı bu zaman aşımları.

### H6. Kaynağa bakmadan sabit bit hızı

Bölüm 2. `server/media.py` `_video_args`.

### H7. Her bağlantıda konsol uyarısı

`web/app.js` `limitSenders`: `setParameters InvalidModificationError: Attempted to set RtpParameters with modified RTCP parameters`. Bütün deneylerde her sayfada bir kez çıktı. `Object.assign(enc, limits)` ya da `degradationPreference` yazımı bazı durumlarda reddediliyor; sınırların (kamera 500 kbps gibi) o bağlantıda uygulanıp uygulanmadığı doğrulanmalı.

## 5. Siyah ekran: elenenler, adaylar, nasıl yakalanır

**Elendi (ölçüldü):** bağlantının filme yetmemesi, bağlantının tamamen kopması, beklemeden dönüşteki sarma. Bu durumlarda masaüstü Chromium ve Android Chrome son kareyi tutuyor.

**Adaylar:**

| Aday | Dayanak | Güven |
| --- | --- | --- |
| H4, zombi bağlantı: izleyici odadan kopuk, tamponu bitiyor | Kodda doğrulandı; belirtiyle örtüşüyor | Orta |
| Tarayıcının kod çözücüsü kare vermeyi bırakıyor (9 Kasım'da düzeltilen durum), ama `watchFrames` görmüyor | `watchFrames` çözülen kare sayısına bakıyor; kareler çözülüp ekrana çizilmiyorsa ya da video duraklamışken kör. Kayıtta 3 günde tek `frames_stalled` yok | Düşük-orta |
| Yandex Browser / Opera GX'e özgü davranış (Marina ikisini de kullandı) | Sadece o tarayıcılarda denenmedi | Bilinmiyor |
| Akış yeniden başlarken (`loadStream`) verinin geç gelmesi | `destroyPlayer` videoyu boşaltıyor, yavaş hatta ilk parça gelene kadar resim boş | Orta: kısa sürmeli, ama Funnel takılıyken uzar |

**Yakalamak için (İP-4):** her izleyici birkaç saniyede bir resmin parlaklığını ve film zamanını sunucuya yollar. Aynı film anında diğerleri aydınlık, biri siyahsa bu karanlık sahne değil, o izleyicinin sorunudur: sunucu kaydeder (tampon, `readyState`, çözülen ve düşen kare, son `state` mesajının yaşı ile birlikte) ve izleyiciye kendini onarmasını söyler. Karanlık sahnede herkes karanlık olduğu için yanlış alarm olmaz.

## 6. İyileştirmeler

| # | Ne | Neden |
| --- | --- | --- |
| G1 | Çevirme bit hızı kaynağa göre: hedef ≤ kaynak videonun ≈ 2 katı (HEVC/AV1 → H.264), alt sınır ≈ 1,5 Mbps | Daredevil 4,7 → ≈ 2,3 Mbps; iki izleyici Funnel'a sığar |
| G2 | Funnel'da bit hızı uzak izleyici sayısına bölünsün (toplam ≈ 6 Mbps bütçe) | 3+ uzak izleyici ya da büyük dosya G1 ile çözülmez. Film ortasında değişirse akış yeniden başlar |
| G3 | Uyarlanan bekleme: üst üste takılan izleyici için eşik büyüsün (4 → 10 → 20 sn tampon) | Çok sayıda kısa duruş yerine az sayıda uzun duruş |
| G5 | Bağlantı paneli: her izleyicinin ölçülen indirme hızı (hls.js parça istatistikleri) ve filmin bit hızı yan yana | "Kimin bağlantısı yetmiyor" sorusu kayda bakmadan cevaplanır |
| G6 | Tekrarlayan takılmada host'a öneri: "Kaliteyi düşür", "Tailscale Serve'e geç" | Bugün takılan kişi için sadece kişi kutusunda "bekleniyor" işareti ve resmin üstünde "… bekleniyor" yazısı var; host'a sebep (yavaş bağlantı mı, sunucu mu) ve ne yapacağı söylenmiyor, sorunu `playback.log`'a bakarak buluyoruz |
| G7 | Ayarlar'da Funnel hız testi | 7–8 Mbps tek ölçüme dayanıyor |
| G8 | `playback.log`'a bekleme olayları (kim, kaç sn, tamponu, hızı) | Bugün sadece hls.js'in ölümcül hataları yazılıyor |

Daha büyük iki iş:
- **HEVC'yi çevirmeden yollama:** odadaki bütün tarayıcılar HEVC oynatabiliyorsa (`MediaSource.isTypeSupported`) kopya kipi. Daredevil 1,1 Mbps'le, orijinal kalitede, ekran kartını yormadan gider. Riskler: tarayıcıya ve donanıma bağlı destek, sonradan katılan desteksiz izleyici (akış çevirmeye dönmeli), HDR HEVC'nin SDR ekranda görünüşü. Önce küçük bir araştırma gerekir.
- **Yavaş izleyiciye ikinci, düşük kalite:** `docs/future-plans.md`'de var.

## 7. Yeni özellik önerileri

| # | Özellik | Not |
| --- | --- | --- |
| Ö1 | **Sonraki bölüm** düğmesi ve bölüm bitince öneri | Torrent paketindeki ve film klasöründeki sıradaki dosya. Diziler bugün her bölümde yeniden aranıp açılıyor |
| Ö2 | **Kaldığın yerden devam** | Film başına son konum sunucuda saklanır; yeniden açınca "42:10'dan devam et?" |
| Ö3 | Telefonda ekran kapanmasın (Wake Lock) | Film oynarken; bugün yok |
| Ö4 | Kilit ekranı ve kulaklık düğmeleri (Media Session) | Başlık, oynat/durdur, ±10 sn |
| Ö5 | Altyazı hizalama paneli (2. ve 3. adım) | Plan hazır: `docs/altyazi-hizalama-plani.md` |
| Ö6 | Otomatik hizalama (`alass`) | Plan: `docs/future-plans.md` |
| Ö7 | İlerleme çubuğunda küçük resim önizlemesi | ffmpeg'le seyrek kareler; sarmayı kolaylaştırır |
| Ö9 | Sürüm denetimi | Kurulu uygulama açılışta GitHub Releases'e bakıp "yeni sürüm var" der |

Altyapı: GitHub Actions'ta kurulum dosyasının otomatik derlenmesi; `web/app.js` 4061 satır tek dosya (modüllere bölmek en sona, çünkü bütün paketlerle çakışır); tarayıcı testleri CI'da yok.

## 8. Kodlama planı (alt ajanlar için iş paketleri)

Ortak kurallar (her ajanın brifine girer): `CLAUDE.md`'deki kurallar geçerli. Commit kimliği `erkinavcii <56629073+erkinavcii@users.noreply.github.com>`, imza satırı yok, mesajlar Türkçe. Push yok; push'u proje sahibi ister. Bitirmeden önce `.\.venv\Scripts\python -m pytest -q` ve arayüz ya da WebSocket değiştiyse üç tarayıcı testi (`PYTHONIOENCODING=utf-8` ile). Arayüz metni eklenirse `web/i18n.js`'de tr, en, ru birlikte. Davranış değişirse iki README ve `CLAUDE.md` birlikte güncellenir.

**Çakışma:** `web/app.js`, `server/main.py` ve `server/room.py` birçok pakette ortak. Aynı dalgadaki paketler ayrı worktree'lerde çalışır ve aşağıdaki sırayla birleştirilir; aynı dalgada aynı fonksiyona dokunan iki paket yok.

### 1. dalga (takılmaları azaltır; birbirinden bağımsız)

**İP-1. Kaynağa göre bit hızı (H6, G1).** Sadece sunucu.
- Dosyalar: `server/media.py` (`_video_args`, gerekiyorsa `ProbeInfo`'ya video akışının bit hızı), `server/config.py`, `tests/test_media.py`.
- Kural: hedef = min(`transcode_kbps`, max(1500, kaynak video kbps × 2)). Kaynak bit hızı bilinmiyorsa (bazı MKV'ler akış başına yazmaz) dosyanın toplamından ses çıkarılır; o da yoksa bugünkü davranış. HDR ve 4K kaynakta çarpan aynı kalır (kaynak zaten büyük).
- Bitti sayılır: 1,1 Mbps'lik HEVC örneğinde komut satırında `-b:v` ≤ 2300k; 20 Mbps'lik kaynakta değişiklik yok; film kartı yeni hedefi yazıyor; pytest.

**İP-2. Beklemenin üç hatası ve sabırlı yükleme (H1, H2, H3, H5, G3).**
- Dosyalar: `web/app.js` (`loadStream`'in hls.js ayarları, `syncTick`'in yeniden başlama kısmı, `waiting`/`playing` dinleyicileri, `state` mesajı), `server/room.py`, `server/main.py` (`buffering` ve `watchdog_loop`), `tests/test_room.py`, yeni `tests/e2e/slow_link.py`.
- Yapılacak: eşik 3,5 sn ve üst üste takılmada büyüsün; bırakılan izleyiciden 60 sn `buffering` alınmasın; istemci `state.waiting`'de kendini görmezse `bufferingSent`'i sıfırlasın; hls.js'te manifest, liste ve parça için ilk bayt süresi 30 sn, yeniden deneme sayıları artırılmış.
- `slow_link.py`: bu rapordaki deney 1 ve 2 (CDP ile `Network.emulateNetworkConditions`). Ölçüt: deney 1'de duruş sayısı 9'dan ≤ 5'e; deney 2'de 20 sn kuralından sonraki 60 sn içinde yeni duruş yok; hiçbir örnekte siyah resim yok.
- Bitti sayılır: pytest, dört tarayıcı testi, `CLAUDE.md`'ye yeni test.

**İP-3. Zombi bağlantı (H4).**
- Dosyalar: `server/room.py` (`Client._send`), `server/main.py` (`ws_endpoint`, `leave`), `web/app.js` (websocket bölümü: `startPings`, `onPong`), `tests/test_api.py` (WebSocket testleri orada).
- Yapılacak: gönderme başarısız olunca sunucu bağlantıyı kapatıp izleyiciyi odadan çıkarsın (istemci 2 sn sonra yeniden bağlanır); istemci 25 sn `pong` almazsa bağlantıyı kendisi kapatıp yeniden bağlansın. Yeniden bağlanınca `media` mesajındaki `streamId` farklıysa oynatıcı zaten yenileniyor (`applyMedia`).
- Bitti sayılır: okumayı bırakan bir test istemcisi 10 sn sonra odadan düşüyor; tarayıcı testinde `pong`'u yutulan sayfa kendiliğinden yeniden bağlanıyor ve oda durumunu alıyor.
- İP-2 ile aynı dosyalar ama farklı fonksiyonlar; birleştirme sırası: İP-2, sonra İP-3.

**İP-5. `setParameters` uyarısı (H7).** Küçük.
- Dosya: `web/app.js` `limitSenders`. Sebebi bul (hangi alan reddediliyor), sınırların uygulandığını `voice_camera.py`'de doğrula. Konsolda uyarı kalmamalı.

### 2. dalga (tanı ve görünürlük; 1. dalga birleştikten sonra)

**İP-4. Siyah resim tanısı ve bekleme kaydı (bölüm 5, G8).**
- Dosyalar: `web/app.js` (yeni küçük bölüm; `report` yanına), `server/presence.py` (yeni mesaj türü, doğrulama, hız sınırı), `server/main.py`, `tests/test_presence.py`, `two_viewers.py`'ye adım.
- Yapılacak: oynarken 3 sn'de bir parlaklık örneği (`{t, luma}`); sunucu aynı film anındaki (±1 sn) örnekleri karşılaştırır; biri < 10, diğerleri > 30 ise `black_picture` kaydı ve o izleyiciye "onar" mesajı (önce odaya sarma, olmazsa `loadStream`, `watchFrames`'in basamakları). Bekleme başlangıç ve bitişleri de `playback.log`'a.
- Bitti sayılır: testte bir sayfanın videosu CSS ile değil, `loadStream` yutularak karartılınca kayıt düşüyor ve sayfa kendini onarıyor; karanlık sahnede (iki sayfa da siyah) kayıt yok.

**İP-6. Bağlantı paneli ve öneriler (G5, G6, G7).**
- Dosyalar: `web/app.js`, `web/index.html`, `web/style.css`, `web/i18n.js`, `server/main.py`.
- Yapılacak: hls.js `FRAG_LOADED` istatistiklerinden izleyici başına indirme hızı; kişi kutusunda "3,1 Mbps · film 4,7 Mbps"; 5 dakikada 3 beklemede host'a tek bildirim ve iki düğme; Ayarlar'da Funnel hız testi (sunucu kendi linkinden bir dosya indirir).

**İP-7. Uzak izleyici sayısına göre bit hızı (G2).**
- Dosyalar: `server/config.py`, `server/media.py`, `server/main.py`, `web/app.js`, `web/i18n.js`.
- Uzak izleyici = `is_local` olmayan ve Funnel'dan gelen. Film açılırken sayıya göre hedef; sayı değişince host'a "kaliteyi yeniden ayarla?" (kendiliğinden yeniden başlatma yok: herkesin filmi kesilir).

### 3. dalga (özellikler; sıra proje sahibinde)

**İP-8. Sonraki bölüm ve kaldığın yerden devam (Ö1, Ö2).** `server/main.py`, `server/library.py`, `server/torrent_client.py`, `web/app.js`, i18n. Bölüm sırası dosya adındaki `SxxEyy`'den, yoksa ada göre.

**İP-9. Telefon: Wake Lock ve Media Session (Ö3, Ö4).** Sadece `web/app.js`; gerçek telefonda ya da emülatörde denenmeli (`CLAUDE.md`, "Android emülatörü").

**İP-10. Araştırma: HEVC'yi çevirmeden yollama.** Kod değil, rapor: hangi tarayıcılar, fMP4'te `hvc1` etiketi, karma odada geri dönüş, HDR. Sonucuna göre ayrı bir plan.
- Rapor (12 Kasım): [docs/hevc-arastirma.md](docs/hevc-arastirma.md). **İP-10a–10d kodlandı (13 Kasım):** kullanıcıya soru ya da ayar yok; tarayıcılar kendi desteğini bildiriyor, herkes oynatabiliyorsa SDR HEVC `-c:v copy -tag:v hvc1` ile gidiyor, desteksiz izleyici gelince ya da çözücü hata verince canlı olarak çevirmeye dönülüyor (`localStorage` tarayıcı ana sürümüne bağlı 7/30 gün ömürlü). Yalnız gerçek film gecesi (`İP-10e`) ve HDR HEVC denemeleri kaldı.

Altyazı hizalama paneli (Ö5) kendi planından yürür: `docs/altyazi-hizalama-plani.md`, 2. adım.

### Önerilen sıra

1. İP-1, İP-2, İP-3, İP-5 birlikte (dört ajan, dört worktree). Birleştirme: İP-1, İP-5, İP-2, İP-3.
2. Gerçek bir film gecesi; `playback.log`'a bakılır.
3. İP-4 ve İP-6 birlikte; ardından İP-7.
4. Özellikler.

**Proje sahibinin kararları (11 Kasım):** G4 ("onu bekleme") ve Ö8 ("hazır mısınız?" sayacı) yapılmayacak; geri kalan her şey bu sırayla uygulanacak. Bu dosyanın commit'i, uygulamadan önceki son nokta.

İlk dalganın beklenen etkisi: Daredevil gibi küçük x265 dosyalarda iki uzak izleyici Funnel'a sığar (4,6 / 7–8 Mbps), kalan takılmalar yarıya yakın azalır, kopan izleyici sayfayı yenilemeden odaya döner. Siyah ekranın kesin sebebi İP-4'ün kaydıyla belli olur.

## 9. Durum (12 Kasım)

Bu dosyanın commit'inden (`921ff81`) sonra plan uygulandı:

| Ne | Durum |
| --- | --- |
| H1–H7, G1–G3, G5–G8 (İP-1…İP-7) | Kodlandı, testlerde; `H2` / **60 sn kuralı** 13 Kasım'da kullanıcı kararıyla varsayılan olmaktan çıkarılıp Ayarlar'da isteğe bağlı yapıldı (bkz. bölüm 11) |
| Ö1–Ö4 (İP-8, İP-9) | Kodlandı; telefon tarafı emülatörde denendi |
| Ö5 Elle hizalama paneli | Kodlandı (planın 2. ve 3. adımı); 4. adım ("odaya öner") proje sahibinin kararıyla yok |
| Ö6 Otomatik hizalama | Altyazıdan altyazıya, saf Python (`server/align.py`); filmin sesine göre hizalama yok, sırada |
| Ö7 İlerleme çubuğunda küçük resim | Kodlandı (`server/thumbs.py`); HDR filmlerin resimleri renk çevrilmeden |
| Ö9 Sürüm denetimi | Kodlandı; etiketle kurulum dosyası derleyen iş akışı (`.github/workflows/release.yml`) hiç çalıştırılmadı |
| İP-10 HEVC'yi çevirmeden yollama | **İP-10a–10d kodlandı (13 Kasım):** SDR HEVC herkeste oynuyorsa `-c:v copy -tag:v hvc1`, karma odada/hatada canlı çevirmeye dönüş (soru/ayar yok; `localStorage` 7/30 gün + ana sürüm ömürlü). Kalan: gerçek film gecesi ve HDR HEVC denemesi (`İP-10e`, [docs/hevc-arastirma.md](docs/hevc-arastirma.md)) |
| G4, Ö8 | Proje sahibinin kararıyla yapılmadı |

Denenmeyenler: gerçek Funnel bağlantısı ve birkaç arkadaş, gerçek telefonlar ve iPhone, arkadaşın tarayıcıları (Yandex Browser, Opera GX), gerçek bir Rusça/Türkçe altyazı çifti, sonraki bölüm için gerçek bir torrent paketi.

## 10. Son kontrol bulguları — Gemini incelemesi ve düzeltmeleri (12 Kasım)

Gemini tarafından `c7e7a2e` üzerinde yapılan kod + canlı tarayıcı denetiminde (`pytest` 196, `two_viewers.py` 58/58, `film_file.py` 31/31, `next_episode.py` 10/10, `slow_link.py` 10/10, `voice_camera.py` tam geçiş) bulunan ek hatalar, **Gemini tarafından yapılan düzeltmeler** ve bekleyen kararlar:

| Önem | Bulgu | Yer | Gemini düzeltmesi ve doğrulama |
| --- | --- | --- | --- |
| Yüksek | `0,0 s` kaymada `pts` siliniyor (`!next.offset && next.scale === 1`) | `web/app.js` (`setAlign`) | `!(next.pts && next.pts.length)` koşulu eklendi; ilk eşleşme `0 ms` olsa bile `pts` korunuyor (`Sıfırla` hâlâ temizliyor). `film_file.py` sıfır kayma → hız ölçümü testiyle doğrulandı. |
| Orta | Kısa dikey ve yatay telefonlarda elle hizalama paneli taşıyor | `web/style.css` (`.align-pane`, `.chat-dock`, `@media (orientation: landscape) and (max-height: 500px)`) | `.align-pane` için `overflow-y: auto`, `max-width: 640px` altında `.chat-dock:has(.chat.aligning)` (`max(360px, 56vh)`) ve `.stage .chat.aligning` için `max-height: calc(100% - 76px)`, kısa yatay ekranda ise sıkılaştırılmış tam sahne yerleşimi eklendi; `390×667` ve `844×390` (normal + tam ekran) `film_file.py` içinde doğrulandı. |
| Orta | Otomatik hizalamada bitiş zamanı `e` sınırlanmıyor | `server/align.py` (`intervals`, `_bits`) | `intervals` ve `_bits` içinde zaman aralığı `MAX_SPAN_S` (`1.1 ×` hız payıyla) ile sınırlandı. `tests/test_align.py` (`test_huge_end_timestamp_is_clamped`) ile doğrulandı. |
| Düşük | Film kapanınca arka plan küçük resim `ffmpeg`’i durdurulmuyor | `server/main.py` (`close_media`), `server/thumbs.py` (`_run`) | `close_media` içine `self.thumbs.stop()` eklendi; iptal sırasında `proc.poll() is None` + `suppress(OSError)` ile güvenli sonlandırma sağlandı. `test_closing_media_stops_thumbnail_job` ve `test_stop_cancels_running_thumbnail_job` ile doğrulandı. |
| Küçük | Medya kapanınca ilerleme çubuğu küçük resmi açık kalabiliyor | `web/app.js` (`applyMedia`, `resetThumb`) | Film kapandığında/değiştiğinde `resetThumb()` ile `THUMB.hover`/`touch`/`loaded` sıfırlanıp kutu gizleniyor; yenileme sonrası erken seek için `renderControls()` içinde `seekBar.max` da anında güncelleniyor. `film_file.py` ile doğrulandı. |
| Küçük | Otomatik hizalamada nadir HTTP/WebSocket yarışı | `web/app.js` (`ALIGN.swap`, `alignControls`, `applyTracks`) | `POST /api/subtitles/{id}/align` dönüşünde yeni iz henüz `S.tracks` içinde yoksa `ALIGN.swap` saklanıyor, WS `subtitles` geldiğinde `applyTracks` etkin yuvayı yeni hizalı ize geçiriyor. |

**Gemini notu (12 Kasım):** Yukarıdaki 6 maddenin tamamı **Gemini tarafından düzenlendi**, ilgili birim ve tarayıcı regresyon testleri eklendi ve son düzenlemelerin ardından tüm testler geçti: `pytest` **199 passed**, `two_viewers.py` **58/58**, `film_file.py` **36/36**, `next_episode.py` **10/10**, `slow_link.py` **10/10**, `voice_camera.py` **all good**.

Karar bekleyen konular: Funnel yeni izleyici / yavaş bağlantı önerilerinin kendiliğinden uygulanıp uygulanmayacağı ve `v0.3.0` sürüm etiketi (`server/version.py`).

## 11. Yavaş izleyiciyi bekleme — kullanıcı kararı (13 Kasım)

- **Proje sahibinin kararı:** Biri takıldığında diğer izleyiciler biraz daha uzun beklenecek olsa bile o kişinin yüklenmesini beklemeyi tercih ediyor; **takılan geride bırakılıp oda devam etmesin, kimse geride kalmasın**.
- **Varsayılan (`BUFFER_WAIT=wait`):** Uygulamada artık **"Kimse geride kalmasın (herkesi bekle)"** varsayılan seçenek (`server/config.py`, `DEFAULTS["bufferWait"] = "wait"`). `watchdog_loop` (`server/main.py`) 20 sn bekleyen izleyiciyi `waiting`'den düşürmüyor; herkes onun yüklenmesini bekliyor (yalnızca bağlantı tamamen koparsa `SEND_TIMEOUT_S = 10 s` / WebSocket kapanışıyla odadan düşüp kalanlar devam eder).
- **Ayarlar'da isteğe bağlı seçenek (`BUFFER_WAIT=skip`):** Eskiden her zaman devrede olan **60 sn kuralı** (`20 sn` sonra odayı devam ettirip sonraki `60 sn` o izleyicinin yeniden durdurmasını yok sayma) **Ayarlar → Biri takılınca → "60 sn kuralı (20 sn bekle, sonra devam et)"** ve `.env` (`BUFFER_WAIT=skip`) üzerinden isteğe bağlı hâle getirildi.

## 12. Tüm proje kapsamlı denetim raporu — Gemini / Argon (14 Kasım)

**Kapsam:** `0436362` (İP-10a–d HEVC doğrudan kopyalama sonrası `main`) üzerinde **Gemini 4 Argon (High)** Swarm ekibiyle (`media-hls`, `server-core`, `subs-infra`, `web-client` ve doğrulayıcı `verifier`) tüm sunucu, istemci, torrent yardımcısı (`torrent-helper/index.mjs`), kurulum betikleri (`tools/`), birim testleri, E2E testleri ve yol haritası belgeleri salt-okunur olarak satır satır incelendi.

> **Önemli durum güncellemesi:** Önceki denetim listelerindeki `ORTA-1` (SDR HEVC doğrudan kopyalama, `İP-10a–d`), Windows kurulum/tepsi (`tray.py`, `tools/`), GPU/HDR zinciri, Stremio eklentileri/LevelDB (`addons.py`, `stremio.py`), saf Python altyazıdan altyazıya hizalama (`align.py`) ve yeni sürüm denetimi (`updates.py`) **zaten kodlanmıştır** (`server/media.py` profil haritası eski tek boolean `allow_hevc` taslağından daha kapsamlıdır). Yalnızca `İP-10e` (gerçek cihaz / HDR HEVC kopya denemesi) açıktır.

### Doğrulanan hatalar, yarış durumları ve güvenlik / güvenilirlik bulguları

| Önem | Bulgu | Yer | Açıklama ve çözüm önerisi |
| --- | --- | --- | --- |
| Yüksek | `_check_progress` içinde `await` sonrası `session` / `stream` kontrolü eksik (`AttributeError` ve kalıcı `loading=True`) | `server/main.py` (`Controller._check_progress` 1104–1135, `_restart_loop` 547–565) | `1112` (`broadcast_state`), `1117` (`broadcast`) ve `1127` (`status`) `await` noktalarında medya kapatılırsa `session.stream = None` olur (`AttributeError`) veya `1128–1132` eski `session` için `set_loading(True)` yapıp `_restart_loop` içindeki `session is self.session` guard'ı nedeniyle `set_loading(False)` hiç çalışmaz. Her `await` sonrası `if session is not self.session or session.stream is None: return` eklenmeli. |
| Yüksek | `open_media` içinde `self.opening = False` erken kapanıyor ve ikinci `start_at` `try/except` dışında | `server/main.py` (`Controller.open_media` 705–755) | `finally: self.opening = False` (`733–735`), `find_next` (`736`) ve HEVC `start_at` (`743`) öncesinde biter. `736` satırında iptal olursa `721`'deki `ffmpeg` kapanmaz (yetim süreç); `736–755` sürerken yeni açılış öncekini iptal etmez; `743` hata verirse oda bozuk `self.session` ile kalır. Hepsi `try/except/finally` içine (`self.session = session` değişiminden önceye) alınmalı. |
| Yüksek | `close_media` / `open_media` / `lifespan` içinde `self.restart_task` (ve `open_task`) iptal edilmiyor | `server/main.py` (547–565, 738–745, 913–924, 1313–1320), `server/media.py` (772–807) | `start_at` `self.stream`'i ancak hazır olunca (`807`) atar; kapatma sırasında `self.restart_task.cancel()` çağrılmadığı için yeni başlayan `ffmpeg` süreci kapanmış oturuma atanarak yetim kalır. Kapatmalarda `restart_task.cancel()` (ve `close_media`'da `cancel_open()`) çağrılmalı. |
| Yüksek | `MediaSession.start_at` GPU fallback zinciri hatalı bileşeni ayırt etmeden `hwaccel` ve HDR `tonemap` önbelleklerini siliyor | `server/media.py` (`MediaSession.start_at` 771–805) | `wait_ready`/`measure_first_pts` hata verince sebebe bakmadan sırayla `give_up_on_hwaccel` → `give_up_on_tonemap` (`libplacebo` → `zscale` → `None`) → `libx264` uygulanır. Kodlayıcı (`NVENC` vb.) hatalıysa `libx264`'e inene dek her iki HDR tonemap filtresi de sunucu ömrü boyunca kalıcı olarak kapatılır ve film tonemap'siz (soluk HDR) oynar. |
| Yüksek | Katılma ekranında (`!S.joined`) `failHevcCodec` çağrısı `S.hevcStreamFailed`'i kilitleyerek sonraki HEVC geri dönüşünü engelliyor | `web/app.js` (`failHevcCodec` 462–469, `loadStream` 524–530) | `464` (`S.hevcStreamFailed = S.streamId`), `465` (`if (!S.joined || !claimedHevc()) return`) kontrolünden önce çalıştığı için katılma ekranında önizlemede `bufferAddCodecError` yaşanırsa `codec_failed` gitmeden akış kilidi konur; "Katıl" sonrası aynı akıştaki tüm HEVC hataları yok sayılır. `464` ataması `465`'in altına alınmalı (veya `!S.joined` iken de `S.hevcFailed = true; recordHevcFail()` çalıştırılmalı). |
| Yüksek | `translate.py` `_LINE` regex'i diyalog tirelerini (`-`) ve üç noktaları (`...`) siliyor | `server/translate.py` (`_LINE` 100, `parse_numbered` 129–136) | `[ \t:.)-]*` tekrarlayıcısı `#12 - Merhaba` ve `#12 ...` başındaki tire/noktaları yutar; yalnız `#12 ...` satırı boş kalıp `missing` sayılır ve gereksiz retry yaptırır. Tekil ayırıcı (`(?:[.):-]\s*|\s+)`) kullanılmalı. |
| Yüksek | Film kapatılınca veya başka filme geçilince önceki torrent tam hızda inmeye devam ediyor | `server/main.py` (738–740, 913–924, 1166–1169), `torrent-helper/index.mjs` (177–215) | `helper.remove` yalnız açılış iptalinde (`_drop_opening_torrent`) çağrılır; aktif film kapatılınca `throttle_loop` `session is None` iken indirme sınırını (`download_kb=0`) da kaldırır ve eski torrent tam hız inmeyi sürdürür. Kapatma/değişimde eski torrent seçimi kaldırılmalı veya durdurulmalı. |
| Orta | `set_viewers_hevc` çalışan akışla (`self.stream.mode`) oturum kipini (`self.mode`) uyumsuz bırakıyor | `server/media.py` (861–866, 888–927), `server/main.py` (624–636) | `transcode` oynarken HEVC destekleyen izleyici katıldığında `check_codecs` `set_viewers_hevc` çağırırsa akış H.264 kalır ama `public()` `"mode": "copy"` bildirir; istemci H.264 akışta kare takılırsa HEVC'yi yanlışlıkla kara listeye alabilir. `public()` aktif `self.stream` kipini yansıtmalı. |
| Orta | `seek()` ve `_check_progress()` içinde `self.restart_task` atanmadan önce `await` bulunuyor | `server/main.py` (524–537, 1121–1132) | `534–535` `await` sırasında gelen ikinci `seek` paralel ikinci `_restart_loop` başlatır. `restart_task` ataması veya yeniden başlatma kilidi ilk `await` öncesinde kurulmalı. |
| Orta | `throttle_loop` ve `open_media` içinde `extract_embedded` çift çalışma yarışı | `server/main.py` (757, 826–875, 1163–1165) | `embedded_tried.add(key)` (`848`), `await helper.info(...)` (`842`) sonrasındadır; bitmiş torrentte iki görev aynı anda `ffmpeg` ile altyazı çıkarıp `SubtitleStore`'a çift kayıt ekleyebilir. |
| Orta | `api_media_next` içinde `cancel_open()` sonrası `NoneType` ve çift tıklama iptal yarışı | `server/main.py` (804–807, 1530–1546) | `await ctl.cancel_open()` (`1544`) sırasında medya kapatılırsa `open_next()` (`805`) `None.get(...)` ile 500 verir; ikinci tıklama da açılmakta olan bölümü sıfırlar. Doğrulanan `item` parametre geçirilmeli ve `opening` hedefine bakılmalı. |
| Orta | Duraklatılmış odada (`playing == False`) `buffering: True` konumu geri sarıyor ve `note_stall` şişiyor | `server/main.py` (467–484) | `note_stall` `set_buffering` kontrolünden önce sayılıyor ve `481–482` duraklatılmış odada bile `room.seek(stalled_at)` yapıyor. |
| Orta | Altyazı silme/arama HTTP uçlarında `require_media_control` yetki kontrolü yok | `server/main.py` (1913–1921, 2016–2048) | `MEDIA_CONTROL=trusted` iken dahi yetkisiz izleyici `DELETE /api/subtitles/{id}` ile herkesin altyazısını/AI çevirisini silebilir, `/api/subtitles/search` ile OpenSubtitles kotasını tüketebilir. |
| Orta | Film değişince `translate_subtitle` iptal edilmiyor ve biten çeviri diske yazılmadan atılıyor | `server/main.py` (1003–1035, 1949–1952) | Görev referansı tutulmadığı için yeni bölümde `409 ai_busy` verir; maliyetle tamamlanan çeviri `1021` `session is not self.session` erken dönüşü yüzünden `store.add()` (`1024`) yapılmadan çöpe gider. |
| Orta | `url_hash` `stream=True` kullanmadığı için `Range` yoksayılırsa tüm video RAM'e iniyor | `server/main.py` (87–103) | `http.get` çağrıları `200 OK` dönen sunucularda gigabaytları RAM'e aldıktan sonra `206` kontrolüne gelir. `http.stream` + bayt uzunluğu doğrulaması gerekli. |
| Orta | `HlsStream.start_process` hata sızıntısı ve `wait_ready`–`measure_first_pts` Windows `PermissionError` yarışı | `server/media.py` (588–607, 693–712, 774–780) | `Popen` hata verirse `_log_file` ve `out_dir` sızar; `measure_first_pts` `read_playlist()`'i ikinci kez okurken Windows `PermissionError` alırsa sağlam akış düşer. |
| Orta | `ThumbStore._run` iptalinde `await proc.wait()` beklenmiyor ve sabit `.tmp-<key>` klasörü çakışıyor | `server/thumbs.py` (188–215, 227–238, 269–271) | Windows'ta `proc.kill()` sonrası `wait()` beklenmediği için `.tmp-<key>` silinmez; hızlı yeniden açılışta eski `finally` yeni `.tmp` klasörünü silebilir. |
| Orta | CRC32 özetleri (`[S1E204F5]`) bölüm numarasını eziyor (`episodes.py`); uzun tek altyazı tüm aralığı birleştiriyor (`align.py`) | `server/episodes.py` (12, 42–47), `server/align.py` (129–139) | `_SEASON_EPISODE` ham ad üzerinde `(?!\d)` ile aradığı için `[S1E204F5]` -> `S01E204` seçer; `align.intervals` tek satıra süre üst sınırı koymadığı için bozuk `(500, 359999)` satırı 500 sn sonrasını tek blok yapar. |
| Orta | `addons.py` SSRF / yerel ağ engeli ve bellek sınırı yok; `library.resolve` `.hidden` klasörü açabiliyor | `server/addons.py` (73–88, 253–263, 446–457), `server/library.py` (36, 49–58) | `addons.py` loopback/özel IP'leri engellemez ve gövde boyutunu `get()` sonrası kontrol eder; `library.resolve` `scan()`'ın gizlediği `.` klasörlerini ve `MAX_DEPTH`'i denetlemez. |
| Orta | `torrent-helper` içinde `client.remove` callback'i beklenmiyor ve 504 zaman aşımında zombi torrent kalıyor | `torrent-helper/index.mjs` (150–159, 173–193, 299) | `webtorrent` `client.remove` sözü `store.close`'u beklemeden çözülür (`cleanup` Windows'ta `EBUSY` yer); 120 sn metadata zaman aşımında `client.remove(t)` yapılmaz. |
| Orta | `tray.py` `already_running()` öncesi log rotasyonu yapıyor ve `GetLastError()` race barındırıyor | `tray.py` (53–77, 122–126) | `cowatch.log` > 5 MB iken kısayola 2. tıklamada `prepare()` açık dosyayı taşımaya çalışıp `WinError 32` ile çöker; `use_last_error=True` + mutex handle saklama gerekli. |
| Orta | İstemcide başka biri beklerken `waiting` yutulması, ekran paylaşımı `muted` kilidi ve PiP pencere olayları | `web/app.js` (573–594, 879–888, 984–1025, 2251–2279, 2375–2394, 2459–2475) | `!roomRunning()` sırasında `waiting` gelirse `syncTick` yeniden `buffering` başlatmaz; `onScreen` erken `return`'ü `el.screenVideo.muted`'ı takılı bırakır (`screen_ended` dalı ölü kod); `PIP.win` içinde `camDrag` ve `#peerPop` ana `window`/`body`'ye gider. |

- **Düşük önem / kenar durum özetleri:** `watchdog_loop` içinde `try/except` eksikliği (`main.py:1137–1154`); `set_remote` içinde `notified_remote` düşüşünün güncellenmemesi (`media.py:857`); `Client.send` kilit uyanma önceliği (`room.py:91`); `leave(client)` screen temizliğinin `await` sonrasına kalması (`main.py:227–235`); `/api/speedtest/run` 429→502 dönüşümü ve port düşmesi (`main.py:1789`, `netpanel.py:139`); `client.stalls` listesinin `viewer` yerine `Client` üstünde tutulması (`room.py:65`); `Controller.luma.clear()` eksikliği; `config.ai_local` portsuz `http://localhost` reddi (`config.py:297`) ve `ai_model_from` anahtar sırası (`main.py:1703`); `hevc_need` boş `profile`/`pix_fmt` kabulü ve `MAX_HEIGHT=0` → `min(0,ih)` (`media.py:281, 354, 499`); `extract_subtitles([])` (`media.py:149`); `ThumbMaker.tried` yüzünden `touch`/`prune` kaybı (`thumbs.py:260`); kütüphane klasörü sezon adı eksikliği (`main.py:795`) ve karışık dizi klasörü (`episodes.py:98`); `PositionStore.flush` `dirty` bayrağı ve `< 60s` temizliği (`positions.py:44, 56, 83`); `LibreTranslate` boş adres ve `MyMemory` 500 bayt sınırı (`translate.py:362, 382`); `SubtitleStore` yazma kilidi ve `OpenSubtitles` 401 yeniden giriş (`subtitles.py:138, 270`); `stremio.py` `_log_records`/`_batch_entries` sınırları (`stremio.py:178, 206`); `run.py` `log` dosya tanıtıcısı ve `fresh_settings()` yan etkileri (`run.py:59, 67`); `tailscale.ip()` `encoding`/`returncode` (`tailscale.py:72`); `cowatch.iss` `[InstallDelete]` `{app}\tools` (`cowatch.iss:52`); `app.js` `welcome` `waitTimer` temizliği (`288`), `applyFilmVolume`/`prefs.muted` sırası (`919–920`), `resetPeer` `renderScreen()` (`1866, 1940`), `finally` `.busy` temizliği ve 5 HTTP hata kodu (`unknown_track`, `bad_audio`, `no_languages`, `nothing_to_open`, `next_moved`) + atıl `err_already_opening` (`web/i18n.js`). *(Not: `web-client` ön raporundaki `unknown_addon` / `err_unknown_title` iddiası `verifier` tarafından koddan elenmiştir; `server/main.py:1877` `unknown_title` fırlatır ve `web/i18n.js:353` bunu karşılar.)*

### Doğrulanan performans ve mimari iyileştirme fırsatları (`OPT` / `ÖZ` / `ORTA`)

| Kod | Yer | Mevcut durum ve kazanım | Uygulama notu |
| --- | --- | --- | --- |
| `OPT-1` | `server/media.py` (`wait_ready`, `measure_first_pts`, `progress`, `can_serve`) | **Yapılmadı:** `0.25s` yoklama + harici `ffprobe` süreci her seek'e 250–450 ms ekler; `progress()` ve `can_serve()` `index.m3u8`'i ikişer kez okur | Saf Python fMP4 okumasında `tfdt` (DTS) tek başına yetmez; B-frame'li akışlarda `trun` ilk `composition_time_offset` eklenmeli |
| `OPT-2` | `torrent-helper/index.mjs` (`streamFile`), `server/main.py` (`683–684`) | **Yapılmadı:** Yalnız açılışta `t.critical` var; seek Range isteklerinde yok; `head`/`tail` sıralı okunuyor | `start > 0` Range isteklerinde 2–4 MB `t.critical()`; `head`/`tail` için `asyncio.gather` |
| `OPT-3` | `server/media.py` (`_audio_args` 509–514) | **Yapılmadı:** 5.1/7.1 downmix düz `-ac 2` kullanıyor | `channels > 2` iken merkez diyalog kanalı `0.5*FC` ağırlıklı `pan=stereo` filtresi |
| `OPT-4` | `server/translate.py`, `torrent_client.py`, `addons.py` | **Yapılmadı:** `BRIEF_PROMPT` 3000 satıra kadar tüm filmi yollar (yerel LLM bağlamı taşar, token 2×); her istekte yeni `AsyncClient`; eklentiler sıralı sorgulanır | `BRIEF_PROMPT` için ~180–240 örnek satır, paylaşılan `httpx.AsyncClient` ve `asyncio.gather` |
| `OPT-5` | `server/translate.py`, `main.py`, `web/app.js`, `align.py` | **Yapılmadı:** Tüm film çevrilmeden iz eklenmiyor ve 1 parça hatası tüm işi yakıyor; `align._split` döngü içinde `_bits()`'i baştan hesaplıyor | `applyTracks` içinde `S.cues` temizlenmediği için canlı güncellemede `S.cues.delete(tr.id)` gerekecek |
| `ORTA-2`, `ÖZ-1..3` | `docs/future-plans.md`, `server/align.py`, `web/app.js` | **Yapılmadı:** Hibrit WebRTC DataChannel HLS (`ORTA-2`), sese göre hizalama (`ÖZ-1`), "aynı dosya bende de var" (`ÖZ-2`) ve otomatik altyazı yedek zinciri (`ÖZ-3`) | Mevcut yol haritası olarak geçerli |

### Belge ve test tutarlılığı notları

- `tests/e2e/hevc_copy.py:192`: Edge üzerinde `ua.match(/\b(Edg(?:iOS|A)?|Chrome)\/(\d+)/)` kullanıldığı için UA'da önde gelen `Chrome/...` eşleşir ve `channel="msedge"` ile TTL testi kırılır (`web/app.js:406` gibi sıralı denenmeli).
- `tests/test_presence.py:152` ve `tests/test_media.py`: `lifespan` `ctl.room.chat` / `cohosts` / `luma`'yı sıfırlamadığından test sırası bağımlılığı var; `test_media.py` kalıcı `data/hls` ve `data/subs/embedded-test` altında artıkları bırakabiliyor (`tmp_path` ve `tests/e2e` ortak video önbelleği önerilir).
- Güncellenmesi gereken belge satırları: `docs/hevc-arastirma.md:3, 5, 79` (üst kutu hâlâ *"Durum: kodlanmadı, eksik kaldı."* yazıyor, aynı dosya `116–130`'da kodlandığı yazılsa da; `79` satırı HDR konusunda `393` satırıyla çelişiyor), `docs/future-plans.md:231` (*"Kodlanmadı"*), `CLAUDE.md:123` (kaldırılmış `OPEN_STEPS` bildirimlerinden söz ediyor; `130` satırı güncel `#loader` / `OPEN_ORDER` yapısını yazıyor).

### Uygulanan 1. dalga — 7 Yüksek Önem Düzeltmesi + OPT-1…OPT-4 Hız Paketi (19 Kasım)

Aşağıdaki maddeler kodlandı ve birim/tarayıcı testleriyle doğrulandı:

- **7 Yüksek Önem düzeltmesi:**
  1. `server/main.py` (`_check_progress`, `seek`): Her `await` sonrası `session is not self.session or session.stream is None` kontrolü eklendi; `restart_task` ilk `await` öncesinde atanıyor.
  2. `server/main.py` (`open_media`): `find_next(session)` ve HEVC `set_viewers_hevc` / ikinci `start_at` adımları `try/except/finally` bloğu içine taşındı; iptal veya hata durumunda yeni `session.stop()` çağrılıyor.
  3. `server/main.py` (`_cancel_restart`, `close_media`, `open_media`, `lifespan`): Kapanış ve film değişiminde `restart_task` ve `open_task` iptal ediliyor; ortak HTTP istemcileri kapatılıyor.
  4. `server/media.py` (`MediaSession.start_at`, `_fallback_candidates`, `HlsStream.start_process`): GPU fallback zinciri hatalı bileşeni izole ederek dener (GPU kodlayıcı düşse bile HDR `tonemap` korunur; bozuk kaynak veya canlı akış zaman aşımı küresel GPU önbelleklerini silmez; `Popen` hatasında `_log_file` kapatılır).
  5. `web/app.js` (`failHevcCodec`): Katılma ekranında (`!S.joined`) erken `S.hevcStreamFailed` kilidi kaldırıldı; önizlemede yalan söyleyen tarayıcı hata verirse `S.hevcFailed` + `recordHevcFail()` kaydedilip katılınca doğrudan `hevc: false` gider, dürüst non-HEVC tarayıcı etkilenmez (`tests/e2e/hevc_copy.py` Edge `browserMajor` regex'i de düzeltildi).
  6. `server/translate.py` (`_LINE`): Diyalog tireleri (`- `) ve üç noktalar (`...`) artık yutulmuyor.
  7. `server/main.py` (`_drop_torrent`, `close_media`, `open_media`) ve `torrent-helper/index.mjs` (`removeTorrent`, `addTorrent`): Film kapanınca veya başka torrente geçilince önceki torrentin indirmesi durduruluyor (`destroyStore: false`), `client.remove` geri çağrısı bekleniyor ve metadata zaman aşımında zombi torrent kaldırılıyor.
- **OPT-1…OPT-4 hız ve kalite paketi:**
  - `OPT-1` (`server/media.py`): `_read_fmp4_start_time` (`sidx` + `mvhd`/`elst`/`mdhd`/`tfdt`/`trun`) ile `ffprobe` süreci olmadan başlangıç PTS okuma (`ffprobe` yedekli), `wait_ready` yoklaması `0.25s → 0.05s` ve ilk segmentin doğrudan aktarımı, `can_serve`/`progress` için tek `read_playlist()` okuması.
  - `OPT-2` (`torrent-helper/index.mjs`, `server/main.py`): `start > 0` seek `Range` isteklerinde `4 MB` `t.critical()` parça önceliklendirmesi ve `head`/`tail` karma okumasının `asyncio.gather` ile paralelleştirilmesi.
  - `OPT-3` (`server/media.py`): `channels > 2` (5.1/7.1) ses izlerinde merkez diyalog kanalını (`FC`) koruyan `SURROUND_DOWNMIX` (`pan=stereo|FL<0.5*FC+...`) filtresi.
  - `OPT-4` (`server/translate.py`, `server/torrent_client.py`, `server/addons.py`): `BRIEF_PROMPT` için `BRIEF_MAX_LINES = 240` (`80` baş + `160` eşit aralıklı örnekleme), çeviri / torrent yardımcısı / eklenti mağazasında paylaşılan `httpx.AsyncClient` ve eklenti sorgularında `asyncio.gather` paralelliği.


