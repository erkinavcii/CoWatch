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

