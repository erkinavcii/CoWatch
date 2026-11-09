# Kaymış altyazıyı elle hizalama planı

> 9 Kasım 2026. 1. adım (altyazı başına kayma) aynı gün kodlandı; panel ve hız henüz yok. Kararlar en sonda; cevap gelmediyse önerilenlerle ilerlenir. Otomatik hizalama (filmin sesine ya da başka bir altyazıya göre) ayrı bir iş: [future-plans.md](future-plans.md), "Altyazıyı otomatik hizalama".

## Sorun

Popüler olmayan bir film ya da dizide her dilde bir iki altyazı bulunuyor, ama hepsi başka bir sürüm için yapılmış (Blu-ray, WEB, TV kaydı). 8 Kasım'daki gerçek örnek: biri Rusça biri Türkçe iki altyazı, biri OpenSubtitles'tan biri bir eklentiden. İkisi de filme göre kaymıştı, birbirinden de türetilmemişlerdi, birbirlerine göre de kaymışlardı.

Kayma iki türlü olur:

1. **Sabit kayma:** altyazı baştan sona aynı miktarda erken ya da geç (sürümün başında fazladan ya da eksik birkaç saniye).
2. **Büyüyen kayma:** altyazı başka bir kare hızındaki sürüm için yapılmış (25 kare ↔ 23,976 kare, yaklaşık %4). Başta tutar, filmin sonunda saniyelerce kaçar. Tek bir kaydırma bunu hiçbir ayarda düzeltemez.

Bugün elimizde sadece `prefs.offsetMs` var:
- Kişiye özel ("sadece seni etkiler"); bu doğru, öyle kalacak.
- **Ama iki altyazıya birden** uygulanıyor. Ana ve ikinci altyazı ayrı ayrı kaymışsa ikisini birden tutturmak imkânsız; 8 Kasım'da olan buydu.
- Filmden filme taşınıyor: bir bölüm için yapılan kaydırma, sonrakinde yanlış kalıyor.
- Doğru yeri bulmak zor: ±0,1 / ±0,5 düğmeleriyle deneme yanılma. Altyazıda özel bir ismi bulup onu duyduğun anla eşleştirmek en iyi yol, ama altyazının satırları görünmeden yapılamıyor.

## Kullanıcının göreceği

### Hizalama paneli

Altyazı kartında, ana ve ikinci altyazı seçimlerinin yanında küçük bir **"Hizala"** düğmesi. Panel, sohbetin durduğu yerde açılır, böylece film görünür kalır:
- Geniş ekranda filmin sağındaki sütunda. Sohbetin yerini alır, başlıkta "Sohbet | Hizala" sekmeleri.
- Dik telefonda filmin altındaki kutuda.
- Aradaki ekranlarda ve tam ekranda videonun üstünde, sohbet gibi.

Panelin içi:

> **Türkçe · OpenSubtitles #2 hizalanıyor** · [Ana ▾ / İkinci]
> [🔍 Altyazıda ara…]
> [ **Şimdi duydum** ] ·  Kayma: +2,4 sn · Hız: aynı
> ─────────────────────
> 41:58  Evet, ama Klaus geldiğinde…
> 42:03  ▶ **Bunu ona söyleme.** ← şu an ekranda olacak satır
> 42:07  Neden?
> …
> [Sıfırla]  [Bitti]

- **Liste** altyazının bütün satırları, o anki hizalamayla zamanlarıyla birlikte. Kendiliğinden kayar; o an gösterilecek satır vurgulu, ortada durur. Biri listeyi elle kaydırınca ya da arama yapınca kayma durur, "Şimdiye dön" düğmesi çıkar.
- **Arama**, altyazının tamamında satır içinde arar (büyük küçük harf ve Türkçe/Rusça harf farkı gözetmez). "Klaus" yazınca o isimli satırlar çıkar.

### İki yol, ikisi de çalışır

1. **Önce satırı bul, duyunca dokun:** aramayla özel bir ismin geçtiği satırı bulursun, filmde o replik gelince satıra dokunursun. Dokunduğun an o satırın başladığı an olur. 8 Kasım'da istenen buydu.
2. **Önce "Şimdi duydum", sonra satırı seç:** repliği duyunca düğmeye basarsın, o an kaydedilir (kaydedilen an bir süre panelde görünür). Sonra acele etmeden listeden o satırı seçersin. Dokunarak yakalamanın tepki gecikmesi yoktur; satırı önceden bulamayanlar için.

Kural: son 60 saniyede "Şimdi duydum"a basıldıysa o an, yoksa dokunma anı kullanılır.

Kimseye filmi durdurtmaz. Durdurmak bütün oda için olduğu için hizalama durdurma gerektirmeyecek şekilde tasarlandı.

### Bir nokta: kayma; iki nokta: kayma ve hız

- **İlk eşleşme** sabit kaymayı düzeltir. Altyazının bütün satırları o kadar kayar.
- **İkinci eşleşme** (en az 10 dakika ötede bir satır) iki noktadan doğruyu çizer: hem kaymayı hem hızı bulur. Panel "Hız farkı düzeltildi: 25 → 23,976 kare" gibi yazar.
  - Bulunan hız bilinen bir kare hızı oranına %0,3'ten yakınsa tam o orana oturtulur (25/23,976, 23,976/25, 24/25, 25/24, 23,976/24, 24/23,976). Elin titremesi hızı bozmaz.
  - Hiçbirine yakın değilse ölçülen değer kalır ve panel bunu "alışılmadık hız farkı" diye belirtir. Çoğunlukla yanlış eşleşmedir.
- **Üçüncü bir eşleşme** en yakın iki noktanın yerine geçer. Sahne kesilmiş ya da reklam arası olan sürümlerde (kayma ortada bir yerde birden değişiyor) parçalı hizalama v1'de yok; otomatik hizalamanın işi.
- Hizalamadan sonra ±0,1 / ±0,5 düğmeleri o altyazının kaymasına eklenir, kaldırılmaz.

### Kişiye ve altyazıya özel

- Hizalama **kişiye özel** (o tarayıcının `localStorage`'ında) ve **altyazıya özel**: altyazının kimliğine bağlı. Kimlik sunucunun her altyazıya verdiği, filmin altyazılarıyla diske kaydedilen kimlik (`subtitles.py`, `uuid` 10 hane); film yeniden açılınca da aynı. Ana ve ikinci altyazı ayrı ayrı hizalanır.
- Aynı altyazıyı izleyen diğerleri etkilenmez. İkinci adımda isteğe bağlı: "Bu hizalamayı odaya öner": aynı altyazıyı seçmiş diğerlerine "Erkin bu altyazıyı +2,4 sn hizaladı, sen de kullan?" bildirimi. Kimseye zorla uygulanmaz.
- Eski `prefs.offsetMs` taşınır: geçişte şu an seçili ana ve ikinci altyazının kendi kayması olur, sonra silinir. Bundan sonra kart, seçili altyazının kendi kaymasını gösterir.
- `localStorage`'da en çok 300 altyazının hizalaması tutulur; en eski kullanılan silinir.

## Teknik

| Yer | Ne değişir |
| --- | --- |
| `web/app.js` `prefs` | `offsetMs` yerine `align: {[trackId]: {offset, scale, used}}`, `alignOf(trackId)` → `{offset: 0, scale: 1}` varsayılanı |
| `drawFrame` | Altyazıya göre zaman: `(filmTime() − offset) / scale`; ana ve ikinci için ayrı ayrı hesaplanır, `activeText` aynı kalır |
| Yeni `alignPanel` | Liste (sanal kaydırma: 1500 satırlık altyazıda bütün satırları DOM'a koymadan, görünen ±60 satır), arama, işaret, eşleşmeler |
| `placeChat` | Panel sohbetle aynı kutunun içinde ikinci sekme; yerini değiştiren kod ortak kalır |
| Hesap | 1 nokta: `offset = T − start × scale` (önceki hızı korur). 2 nokta: `scale = (T₂ − T₁) / (s₂ − s₁)`, oranlara yakınsa oturt, `offset = T₁ − s₁ × scale` |
| `web/i18n.js` | Panelin metinleri üç dilde |
| Sunucu | Değişmez: satırlar zaten `/api/subtitles/{id}.json`'dan geliyor |

Sunucuda değişiklik olmadığı için pytest'e iş yok; hesap kısmı küçük, saf bir fonksiyon (`fitAlignment(points)`), tarayıcı testinden çağrılarak denenir.

### Tarayıcı testi (`two_viewers.py`'ye yeni adım)

- 5 sn geç yapılmış bir altyazı: "Hizala", aramayla satırı bul, film o satıra gelince dokun → altyazı doğru anda görünür. Öteki pencerede kayma yok.
- "Şimdi duydum" sonra seçim: aynı sonuç.
- %4 hızlı (25 → 23,976) yapılmış altyazı, iki nokta → filmin sonundaki satır da doğru anda; panel "25 → 23,976" yazar.
- Ana ve ikinci altyazı ayrı ayrı hizalanır; biri ötekini bozmaz.
- Sayfa yenilenince hizalama durur; başka bir altyazıya geçince o altyazının kendi hizalaması gelir.
- Telefonda panel filmin altındaki kutuda.

## Adımlar

1. **Altyazı başına kayma:** `prefs.align`, eski `offsetMs`'in taşınması, kartın seçili altyazının kaymasını göstermesi. Tek başına da işe yarar: 8 Kasım'daki ana ve ikinci altyazı sorununu çözer.
2. **Panel:** liste, arama, kendiliğinden kayma, tek noktayla hizalama, iki yol.
3. **İkinci nokta ve hız:** oranlara oturtma, panelde sonuç.
4. **(İsteğe bağlı) odaya öner.**

Her adımdan sonra tarayıcı testleri.

## Kararlar

| Konu | Önerilen |
| --- | --- |
| Kime uygulanır | Kişiye ve altyazıya özel (proje sahibinin isteği, 9 Kasım) |
| Panelin yeri | Sohbetin kutusu, "Sohbet \| Hizala" sekmeleri |
| Satıra dokunmak | Son 60 sn'de işaret varsa işaretin anı, yoksa dokunma anı |
| Hız farkı | İki noktayla; bilinen kare oranlarına %0,3 içinde oturtma |
| Parçalı hizalama (kesilmiş sahneler) | v1'de yok; otomatik hizalamaya kalır |
| Odaya önerme | 4. adım, sonra |

## Bilinenler ve riskler

- **Yanlış satır seçmek:** aynı replik iki kez geçiyorsa ("Evet.") yanlış eşleşme olur. Panel kısa satırlarda "daha ayırt edici bir satır seç" der; ikinci noktada hız tuhaf çıkarsa uyarır.
- **Tepki gecikmesi:** dokunma yolunda 0,2–0,4 sn gecikme olur. İnce ayar düğmeleri kalır; "Şimdi duydum" yolunda da aynı gecikme var ama satırın kendisini aramakla kaybedilmez.
- **Yan tutulan telefonda** panel filmin üstüne gelir, resmin bir kısmını örter. Dik tutmak önerilir.
