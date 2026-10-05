# Akıllı Modelleme Platformu — teslim notu

Bu tur: **Kısaltma Sözlüğü açıklaması: ne yaptığı başlık altında, sütunlar i'de**. Değiştir: `fe_agent/akis_faz01.py`, `webapp/app.js`, `webapp/style.css`, `OKU_ONCE.md` (backend yeniden başlatılmalı)

- Başlığın altında yalnız adımın ne yaptığı (düz metin, kartın yazı
  tipiyle). Bir önceki denemedeki madde listesi kaldırıldı.
- Sütunların açıklaması "Kısaltma Sözlüğü" başlığının yanındaki i
  balonunda ("Sütunlar"), her sütun ayrı paragraf.

Önceki tur: **"İkisi aynı" ama farklı anlamlar + takılı kalan i balonu**. Değiştir: `fe_agent/kisaltma.py`, `fe_agent/llm.py`, `webapp/app.js`, `OKU_ONCE.md` (backend yeniden başlatılmalı). Önceki iki turun dosyaları da (özellikle `fe_agent/akis_faz01.py`) kopyalanmış olmalı.

1) Dil modeli "ikisi aynı" dediği hâlde LLM Sözlük ile LLM Genel'in
   yazımı farklıysa satır sarı olur ve uyarı yazar (eş anlamlı mı,
   hangisi doğru). Kod eş anlamlılığı bilemediği için karar kullanıcıda.
   İstemde "aynı" tanımı daraltıldı: yalnız eş anlamlılar; yakın, birlikte
   geçen, biri öbürünü içeren ya da aynı ifadenin parçaları olan anlamlar
   aynı değildir.
2) i balonunda LLM Sözlük'ün kaynağı yazar: dil modeli sözlük anlamını
   vermediyse "kelime sayımı gösteriliyor".
3) i balonu sol üstte takılı kalmıyor: tablo yenilenince (dil modeli
   sonucu gelince) simge silinip gövdeye taşınmış balon kalıyordu; simge
   sayfadan kalkınca balon da kapanır.

Önceki tur: **Önerilen Kısaltma boş kalıyordu: düzeltme**. Değiştir: `fe_agent/llm.py`, `fe_agent/kisaltma.py`, `webapp/app.js`, `OKU_ONCE.md` (backend yeniden başlatılmalı)

Sebep (sahte modelle eski kodda yeniden üretildi): iki model aynı anlamı
farklı kelimelerle yazınca karar hakeme gidiyor, hakem modellerin
önerdiği kısaltmaları görmüyordu; öneri kararı verse de kısaltma
yazmayınca karar "sözlük doğru"ya düşüyordu. Ayrıca boşluklu öneri
("<A> <B>") parçaları bitiştirilip biçim dışı kalıyor ve sessizce
siliniyordu.
1) İki model de aynı öneri kararını (yanlış kısaltma / anlaşılmaz)
   verdiyse anlamın yazımı farklı olsa da hakeme gitmez.
2) Hakem satırında modellerin önerdiği kısaltmalar yazar; hakem öneri
   kararı verip kısaltma yazmazsa aynı kararı veren modelin önerisi
   kullanılır.
3) Boşluk, tire, nokta parça ayıracı sayılır ("_" olur).
4) Biçime yine uymayan öneri silinmez, satırda uyarı olarak yazar.
5) Kartta yoklama sırasında tire içeren anlamlı satır "elle değişti"
   sayılıp gelen önerinin boş değerle ezilmesi düzeltildi.

Önceki tur: **Her parça ayrı kısaltma, birleştirme yalnız öneri; LLM Sözlük gerçekten dil modeli; LLM Karar sütunu**. Değiştir: `fe_agent/kisaltma.py`, `fe_agent/llm.py`, `fe_agent/akis_faz01.py`, `webapp/app.js`, `webapp/style.css`, `OKU_ONCE.md` (backend yeniden başlatılmalı)

1) Kolon adlarında "_" ile ayrılan her parça ayrı kısaltmadır; önceki
   turdaki kendiliğinden birleştirme kaldırıldı. Hep yan yana geçen
   parçalar (her birinin kolonlarının en az %90'ında, en az 3 kolonda)
   yalnız ADAY: iki dil modeline "ayrı anlamlar yan yana okununca anlam
   karışıyor mu" diye sorulur; ikisi de "birleştir" derse kartta
   "Birleştirme Önerileri" bölümünde çıkar. Birleştir kutusu varsayılan
   boş; işaretlenirse bu çalışmada birlikte anlamıyla kullanılır
   (01.2.6'daki ad parçaları) ve hafızaya "<A>_<B>" olarak yazılır.
   İşaretlenmezse parçalar ayrı kalır. Kolon adları değişmez.
2) LLM Sözlük sütunu eskiden sözlükteki kelime sayımını gösteriyordu
   (tek kelimeye inmiş, eksik). Artık karar veren dil modeli, örnek
   tanımlardan okuduğu anlamı ayrıca yazar (sozluk_anlam) ve sütunda o
   görünür. Dil modeli sonucu yoksa kelime sayımı görünür, altında
   "kelime sayımı" yazar. Karar artık bu okunan anlam ile genel anlam
   arasında; kelime sayımı modele yalnız ipucu.
3) Anlam sütununun adı LLM Karar (Excel'de de). Sonucu gelmemiş satırda
   LLM Sözlük ve LLM Karar "bekleniyor…"; önce kelime sayımı görünüp
   sonra değişmiyor.
4) Sayı değerli kalıp (<K><NN>, aralıklı <K><NN>_<MM>): kısaltmanın
   altında adlardaki biçimler, LLM Karar altında sayıyla okunuşu
   (<K><NN> = <anlam> <NN>). 01.2.6'ya giden ad parçalarında sayı
   korunur (aralık "<NN>-<MM>").
5) Kısaltma adı tabloda kırpılmıyor, sığmazsa alt satıra geçiyor.

Önceki tur: **Birlikte geçen parçalar tek kısaltma + "anlaşılmaz kısaltma" kararı**. Değiştir: `fe_agent/kisaltma.py`, `fe_agent/llm.py`, `fe_agent/akis_faz01.py`, `webapp/app.js`, `OKU_ONCE.md` (backend yeniden başlatılmalı)

1) Birlikte geçen parçalar tek kısaltma: iki parça kolon adlarında
   neredeyse hep yan yana geçiyorsa (her birinin geçtiği kolonların en az
   %90'ında, en az 3 kolonda) "<A>_<B>" tek kısaltma sayılır, anlamı
   birlikte verilir. Kolon adı değişmez. Pencere / sayı araya girerse
   birleşmez.
2) Yeni karar "anlam doğru ama kısaltma anlaşılmıyor": ünlüleri atılmış
   uzun birleşik, birden çok okunuşlu ya da yaygın olmayan kısaltmaya
   okunur karşılık önerilir; anlam aynı kalır. Önerilen kısaltma artık
   çok parçalı olabilir: en çok 4 parça ("_" ile), parça başına 8, toplam
   24 karakter. 01.2.5'te kolon adlarına uygulanır (yalnız platform
   kopyalarında). Satır sarı (öneri var); lejant buna göre.
3) Teslim notlarındaki (bu dosya) veri örnekleri genel yer tutucularla
   değiştirildi (<KOLON>, <KISA>, <VERI_SETI>, <anlam>).

Önceki tur: **Kodda ve istemlerde veri içeriği yok**. Değiştir: `fe_agent/llm.py`, `fe_agent/kisaltma.py`, `fe_agent/akis_faz01.py`, `fe_agent/aralik.py`, `fe_agent/birlestirme.py`, `fe_agent/niyet_kural.py`, `webapp/app.js` (backend yeniden başlatılmalı)

- Dil modeli istemlerindeki, gerçek bir sözlükten alınmış kolon adı,
  kısaltma ve tanım örnekleri kaldırıldı; kurallar soyut kalıp olarak
  yazıldı (<KISA>, <X>, A / B pencere). İstemlerin davranışı veriye özgü
  cevaplara yönlendirmez.
- Pencere kalıbı (sayı + birim harfi) artık kesin kural değil: "genelde
  pencere; bu veri setinde geçerliliğini örnek tanımlardan doğrula".
- Kullanılmayan KISALTMA_BILGI metni silindi; Kolon Adı Önerileri yardım
  metnindeki örnek çıkarıldı.
- Yorum ve belge satırlarındaki veri örnekleri genel ifadelerle değişti.
- karsilastir() test yardımcısının girdileri kurgusal (gerçek veri seti
  adı / kolon adı yok).
- Kodda kalan genel bilgiler (veriden değil): yaygın İngilizce ölçü
  kısaltmaları kümesi (dönem adayı elemede), Türkçe dil bilgisi listeleri,
  iki pencereli oran tanımının "A-B arası"na çevrilmesini engelleyen
  kalıp kontrolü.

Önceki tur: **Kısaltma sonuçlarının gözden geçirmesinden çıkan 6 düzeltme**. Değiştir: `fe_agent/kisaltma.py`, `fe_agent/llm.py`, `webapp/app.js` (backend yeniden başlatılmalı)

1) Kendini açıklayan kelime (<KISA>, <KISA>, <KISA>): anlamı kelimenin
   kendisiyse (Türkçe) listeye girmez.
2) "Yanlış kısaltma" kararı yalnız kısaltmanın BİLİNEN bir genel anlamı
   varsa ve bu anlam başka bir kavramsa. Eş anlamlı / yakın anlam (<KISA> =
   giriş / gelen) bu değil. Önerilen yeni kısaltma aynı anlamda zaten
   varsa (<KISA> -> <KISA>) hata sayılmaz: karar "sözlük doğru", uyarı yok.
3) Genel anlam yokken (<KISA>, <KISA>) "yanlış kısaltma" verilmez; anlam
   tam yazılır ("önceki eş dönem", "ilk işlemden bu yana geçen süre").
   <KISA> gibi birleşik İngilizce kalıplar doğru kısaltma sayılır; karşılık
   kısaltmalara tutarlı çift önerilir (<KISA> / <KISA>).
4) Birlikte ifade oluşturan kısaltmalar (<KOLON> = günlük ortalama):
   her birine kendi anlamı (<KISA> = başına, <KISA> = gün); istem kuralı.
5) Renk: sarı yalnız sözlükteki anlam değiştiyse (dil modeli doğru, ikisi
   de yanlış, yanlış kısaltma), boşsa ya da uyarı varsa. "Sözlük doğru" ve
   "ikisi aynı" renksiz. Lejant: Sözlük Doğru / Sözlük Değişti, Boş ya da
   Uyarılı / Düzenlendi.
6) Sözlük istatistiği: parantez içi aday değil ("düzeltilmiş (shrink)");
   iki kelimesi de ekli tamlamada başı alınır ("dağılımı entropisi" ->
   entropi); Türkçe olmayan ifade elenir; tamlayan ekli kelime, yalını
   tanımlarda da geçiyorsa yalına iner ("günün" -> gün).
Excel: LLM Sözlük, LLM Genel, Karar, Gerekçe, Önerilen Kısaltma ayrı
sütunlar; Kaynak sütunu kısaldı.

Önceki tur: **"genel anlamı yok" yerine ∅**. Değiştir: `webapp/app.js` (yalnız sayfa yenileme)

- Kısaltma Sözlüğü'nde LLM Genel sütunu, genel anlamı olmayan (kuruma
  özgü) kısaltmada "genel anlamı yok" yerine ∅ gösterir.
- Dil modeli emin olamadığında da "emin değil" yerine ∅.

Önceki tur: **01.2 kartlarında sade renk**. Değiştir: `webapp/app.js`, `webapp/style.css` (yalnız sayfa yenileme)

01.2 Veri ve Model Tanımları kartlarında (Sözlük Tanımları, Kısaltma
Sözlüğü, Kolon Adı Önerileri, Sözlük Tanım Kontrolü) yalnız üç anlam:
- renksiz: öneri / normal durum (dil modeli önerisi, onaylı tanım, sözlük
  ve genel aynı)
- sarı: dikkat gerektiren (boş, sözlük ve genel farklı, uyarılı, eksik)
- yeşil: sizin yazdığınız / değiştirdiğiniz
Kaldırılanlar: mavi, mor, kırmızı satır, camgöbeği bilgi kutusu (gri
oldu), sarı/kırmızı/mor çipler (ince kenarlıklı, renksiz), yeşil Excel
düğmesi (ikincil düğme gibi), yeşil kapsam çubuğu (tam iken siyah/beyaz).
Karar sonrası seçilmeyen satır kırmızı yerine soluk. Lejantlar buna göre.
Değişken Kontrolü ve sonraki adımlar değişmedi (CSS .dg-kart kapsamında).

Önceki tur: **Kısaltma durum bilgisi tablonun altında, bilgi kutusu olarak**. Değiştir: `webapp/app.js`, `webapp/style.css` (yalnız sayfa yenileme)

- "43 kısaltma; 0 tanesi hafızada onaylı. Dil modeli kontrolü sürüyor …"
  satırı tablonun altına, onay düğmesinin üstüne taşındı.
- Bilgilendirme kutusu: camgöbeği zemin ve sol çizgi (satır renklerinden
  ayrı); açık ve koyu temada ayrı tonlar (--bilgi-zemin, --bilgi-kenar).
  Turuncu "Dil modeli kontrolü bitince onaylanabilir" uyarısı kutunun
  altında kalır.

Önceki tur: **Sütun adları: "Önerilen Kısaltma", "Seç"**. Değiştir: `webapp/app.js`, `webapp/style.css`, `fe_agent/akis_faz01.py` (backend yeniden başlatılmalı; yalnız açıklama metni için)

- Kısaltma Sözlüğü: "Önerilen" -> "Önerilen Kısaltma", "Kaydet" -> "Seç".
- Sözlük Tanımları (01.2.3): "Sözlüğe Ekle" sütun başlığı -> "Seç".
  Düğme metni ("… Kolonu Sözlüğe Ekle ve Devam Et") değişmedi.

Önceki tur: **Kısaltma tablosu sadeleşti**. Değiştir: `fe_agent/akis_faz01.py`, `webapp/app.js`, `webapp/style.css` (backend yeniden başlatılmalı)

- Sütunlar: Kısaltma | LLM Sözlük | LLM Genel | Anlam | Önerilen | Kaydet.
- Not sütunu kaldırıldı; karar, gerekçe, uyarı ve örnek kolonlar
  kısaltmanın yanındaki "i" simgesinde. Uyarılı satırın solunda turuncu
  çizgi kalır.
- "Kısaltma Sözlüğü" başlığının yanındaki "i" kaldırıldı; başlığın altında
  kısa açıklama var (KISALTMA_ACIKLAMA).
- Lejant: "Sözlük ve Genel Aynı" / "Sözlük ve Genel Farklı".

Önceki tur: **<KISA> / <KISA> / <KISA> / <KISA> tek kısaltma: <KISA> = saat**. Değiştir: `fe_agent/kisaltma.py`, `fe_agent/llm.py`, `fe_agent/akis_faz01.py` (backend yeniden başlatılmalı)

- 1-2 harf + en az 2 rakamlı parça (<KISA>, <KISA>, M12) artık "harf kısaltması +
  değer" sayılır: kısaltma <KISA>, anlamı "saat"; sayı değerdir. Kartta dört
  ayrı satır yerine tek <KISA> satırı. <KISA>, <KISA> gibi tek rakamlılar değişmedi.
- İstemlere kural: sayıyla birleşik kısaltmada yalnız harf kısmının anlamı
  ("saat 00" değil "saat"), yeni kısaltma önerilmez.
- Aynı yeni kısaltma birden fazla kısaltmaya önerilirse (<KISA>..<KISA> -> <KISA>)
  ya da kolon adlarında zaten başka bir kısaltmaysa öneri düşürülür,
  satırda uyarı yazar.
- Kolon adı önerisinde kalıp korunur: <KISA> yerine <YENI> kabul edilirse
  <KISA>00 -> <YENI>00.

Önceki tur: **Önerilen kısaltma kolon adlarının dilinde**. Değiştir: `fe_agent/llm.py` (backend yeniden başlatılmalı; bir önceki turun dosyaları kopyalanmadıysa onlar da)

- Dil modeline her parçada "ADLANDIRMA KALIBI" gider: kolon adlarında en
  sık geçen 20 kısaltma (<KISA>, <KISA>, <KISA> ...). Yeni kısaltma aynı dilde ve
  kalıpta önerilir: İngilizce adlarda yaygın İngilizce kısaltma (önceki eş
  dönem -> <KISA>); Türkçe anlamın harflerinden kısaltma üretilmez ("en çok"
  -> <KISA> yanlış). Türkçe adlandırılmış veri setinde Türkçe kısaltma.
- Gerekçe Türkçe karakterlerle yazılır ("Sozlukte" değil "Sözlükte").
- Not: yeni kısaltma yalnız "sözlük doğru ama kolon adında yanlış
  kısaltma" kararında önerilir; ekrandaki <KISA> = <KISA> önerisi bir önceki
  sürümün davranışı (orada her "yanıltıcı" kısaltmaya öneriliyordu).

Önceki tur: **Kısaltma kararı: "sözlük doğru ama kolon adında yanlış kısaltma"**. Değiştir: `fe_agent/llm.py`, `fe_agent/kisaltma.py`, `fe_agent/akis_faz01.py`, `webapp/app.js` (backend yeniden başlatılmalı; bir önceki turun dosyaları da kopyalanmadıysa onlar da: `webapp/style.css`, `webapp/backend.py`)

Karar seçenekleri (Not sütununda gerekçesiyle):
- ikisi aynı (eş anlamlı dahil) -> o anlam
- sözlük doğru, genel anlam uymuyor -> Anlam = sözlükteki (<KISA>: "giriş"
  değil "gelen")
- dil modeli doğru, sözlükteki tanımlar yanlış -> Anlam = genel anlam;
  tanımlar 01.2.6'da düzeltilmeye aday
- sözlük doğru ama kolon adında yanlış kısaltma seçilmiş (YENİ) ->
  <KISA>'nin anlamı genel anlam kalır ("kare"); Önerilen Kısaltma = <KISA>,
  altında "= önceki eş dönem". Onayda kısaltma sözlüğüne <KISA> = kare,
  <KISA> = önceki eş dönem yazılır. 01.2.5 bu kolonları <KISA> ile adlandırır.
  Bu veri setinin kontrollerinde (kolon adı önerileri, 01.2.6) <KISA>'li
  kolonlar "önceki eş dönem" anlamıyla değerlendirilir; 01.2.6'ya kolonun
  yeni adı da gider.
  Önerilen kısaltmayı boşaltırsanız Anlam sözlükteki anlama döner.
- ikisi de yanlış -> dil modelinin yazdığı anlam

Önceki tur: **Arşivden silinen çalışma geri gelmiyor**. Değiştir: `webapp/backend.py` (backend yeniden başlatılmalı)

- Sebep: silme sürerken ya da hemen sonra biten bir istek (adım, öneri,
  kart kaydı) çalışmanın calisma.json dosyasını yeniden yazıyordu; Arşiv
  listesi de klasöründe calisma.json olan ama kayıtta olmayan çalışmayı
  "kayıtsız kalmış" sayıp geri ekliyordu.
- Düzeltme: silmede önce CALISMALAR.json'dan çıkarılır, sonra klasör
  silinir. Kayıtta olmayan çalışmaya kayıt yazılmaz (hata günlüğüne
  "kaydet:silinmis" düşer). Klasör silinemezse kayıt geri yazılır,
  çalışma listede kalır. Liste okunurken silinen çalışmaya özet
  yazılmaz.

Önceki tur: **Kısaltmada açık karar (hangisi doğru) + yanıltıcı kısaltmaya yeni kısaltma**. Değiştir: `fe_agent/llm.py`, `fe_agent/kisaltma.py`, `fe_agent/akis_faz01.py`, `webapp/app.js`, `webapp/style.css` (backend yeniden başlatılmalı)

1) Açık karar
- Dil Modeli sütunu artık SÖZLÜĞE BAKMADAN verilen genel anlam (<KISA> =
  "kare"). Kuruma özgü kısaltmada "genel anlamı yok".
- İki model (anlaşamazsa hakem) örnek kolonlara bakıp karar verir: ikisi
  aynı / sözlük doğru / dil modeli doğru / ikisi de yanlış (doğrusunu
  yazar). Karar ve tek cümle gerekçe Not sütununda.
- İstem kuralları: genel anlam kolon adlarının yapısına uymuyorsa ve
  sözlük tutarlıysa sözlük doğrudur (<KISA> = önceki eş dönem); pencereye
  bağlı anlam sayısız yazılır; adı bilinen ölçüde özel ad (<KISA> =
  <özel adlı ölçü>). Özel adın büyük harfi korunur.
- Renk: model "ikisi aynı" derse (eş anlamlı dahil) mavi.

2) Yeni kısaltma
- Kısaltma anlamına göre yanıltıcıysa dil modeli daha açık bir kısaltma
  önerir: "Önerilen Kısaltma" sütunu (düzenlenebilir, boşaltılabilir;
  büyük harf, 2-8 karakter, A-Z ve 0-9).
- Onayda kontrol: başka anlamda kullanılan kısaltma ya da iki satıra aynı
  öneri adımı durdurur. Kabul edilen yeni kısaltma kısaltma sözlüğüne
  aynı anlamla girer (Hafızaya Kaydet işaretliyse hafızaya da).
- 01.2.5 Kolon Adı Önerileri: eski kısaltmanın geçtiği kolonlar yeni
  kısaltmayla önerilir (<KOLON> ->
  <KOLON>); yalnız AMP kopyalarında uygulanır.
- Kolon Adı Önerileri artık yalnız bu veri setinin kolonlarını listeler
  (eskiden onaylı tanım hafızasındaki başka veri setlerinin kolonları da
  girebiliyordu).

3) Tanım kontrolü (01.2.6): adda pencere varsa göreli ifade ("bir önceki
   döneme göre") o pencereyle somutlaştırılır ("önceki 3 gündeki adede").

Önceki tur: **Kısaltma kartında renk: sözlük ve dil modeli aynı mı farklı mı**. Değiştir: `fe_agent/kisaltma.py`, `webapp/app.js`, `webapp/style.css` (backend yeniden başlatılmalı)

- Mavi: sözlük ile dil modeli aynı anlamı veriyor. Kırmızı: farklı.
  Renksiz: karşılaştırma yok (dil modeli bekliyor / emin değil / sözlükte
  anlam yok). Sarı boş, mor hafızada onaylı, yeşil sizin yazdığınız
  (akışın geri kalanıyla aynı). Anlam'ın kaynağını ✓ gösterir.
- ÖNEMLİ: son iki turun `fe_agent/llm.py` dosyası da kopyalanmalı;
  eski llm.py ile dil modeli kontrolü "unexpected keyword argument 'ara'"
  hatası verip hiç çalışmıyor (Dil Modeli sütunu boş kalır).

Önceki tur: **Kısaltma kartında sözlük ve dil modeli ayrı sütunlarda**. Değiştir: `fe_agent/kisaltma.py`, `fe_agent/akis_faz01.py`, `webapp/app.js`, `webapp/style.css` (backend yeniden başlatılmalı)

- Sütunlar: Kısaltma | Sözlükte | Dil Modeli | Anlam | Not | Hafızaya
  Kaydet. Sözlükte ve Dil Modeli salt okunur; Anlam'a daha mantıklı olan
  yazılır (seçim mantığı aynı), önündeki ✓ hangisinden geldiğini
  gösterir. Dil Modeli sütunu: değer, "bekleniyor…", "emin değil" ya da ∅.
- Renkler akışın geri kalanıyla aynı (Sözlük Tanımları kartı): sarı boş,
  renksiz sözlükten, mavi dil modeli, mor hafızada onaylı, yeşil sizin
  yazdığınız. Anlam'a sözlükteki ya da dil modelindeki değeri yazarsanız
  satır o kaynağın rengine, ✓ da o sütuna geçer.
- Kaynak sütunu "Not" oldu: yalnız ek bilgi (genel anlamla uyum, kolon
  yüzdesi) ve uyarılar. Kaynak adı Excel'in Kaynak sütununda kaldı.

Önceki tur: **Kısaltma sonuçları geldikçe kartta açılıyor**. Değiştir: `fe_agent/llm.py`, `fe_agent/kisaltma.py`, `fe_agent/akis_faz01.py`, `webapp/app.js`, `webapp/style.css` (backend yeniden başlatılmalı)

- Dil modeli kontrolü artık 8'er kısaltmalık parçalar halinde; her parça
  bitince sonucu hemen karta düşer (eskiden 12'lik parçaların hepsi
  bitince geliyordu).
- Sonucu gelen satır düzenlenebilir; sonucu gelmeyen satır soluk ve
  kilitli ("dil modeli kontrolü bekleniyor"), sonuç gelince açılır.
  Düzenlediğiniz satırlar sonraki güncellemelerde ezilmez.
- Not satırında ilerleme: "Dil modeli kontrolü sürüyor: 21 / 42
  kısaltmanın sonucu geldi."
- Kart 3 sn'de bir yoklar (eskiden 5 sn). Onay düğmesi yine kontrolün
  tamamı bitince açılır. Tümünü Seç / Temizle kilitli satırlara dokunmaz.

Önceki tur: **Kısaltmada sözlüğe bakmadan genel anlam + kontrol bitmeden onay yok**. Değiştir: `fe_agent/llm.py`, `fe_agent/kisaltma.py`, `fe_agent/akis_faz01.py`, `webapp/app.js` (backend yeniden başlatılmalı)

1) Sözlüksüz (kör) genel anlam
- Dil modeline önce yalnız kısaltma ve geçtiği en çok 6 kolon adı gider
  (açıklama, sözlük önerisi, istatistik gitmez). Model genel anlamı kendi
  bilgisinden verir; kuruma özgü kısaltmada boş bırakır.
- Sonra bugünkü sözlüklü karar verilir; bu genel anlam da satırda
  modele gider ve model "genel anlamla aynı anlamda mı" der.
- Kaynak sütunu:
  - aynıysa: "sözlüğe bakmadan verilen genel anlamla aynı"
  - farklıysa uyarı: "Sözlüğe bakmadan verilen genel anlam: X; seçilen
    anlam farklı, kontrol edin."
  - genel anlam yoksa: "genel bir anlamı yok (kuruma özgü), sözlükten
    çıkarıldı"
  - sözlükle karar verilemediyse genel anlam gelir ("Dil modelinin genel
    bilgisi"); sözlük istatistiği farklıysa uyarıda yazar.
- Maliyet: 12 kısaltmalık parça başına 1 dil modeli çağrısı daha.

2) Onay kilidi
- 01.2.4'te "Kısaltmaları Onayla ve Devam Et" dil modeli kontrolü bitene
  kadar kapalı; altında sebebi yazar. Kontrol sürerken Kaynak'ta
  "dil modeli kontrolü bekleniyor" yazar. "Kısaltmaları Onaylamadan Devam
  Et" her zaman açık. Kontrol 10 dakikada bitmezse kilit açılır.

3) Yüzde eki düzeltildi: "%86'inde" -> "%86'sında", "%100'ünde".

Önceki tur: **Üst bar eski hâline döndü: "Akıllı Modelleme Platformu"**. Değiştir: `webapp/index.html`, `webapp/style.css`, `webapp/app.js`, `webapp/backend.py` (backend yeniden başlatılmalı)

- KATIB denemesinin üç turu geri alındı; webapp dosyaları o denemeden
  önceki hâliyle birebir aynı. katib_*.png görselleri kullanılmıyor.

Önceki tur: **KATIB görsel yerine metin**. Değiştir: `webapp/index.html`, `webapp/style.css`, `webapp/app.js`, `webapp/backend.py` (backend yeniden başlatılmalı)

- Logonun yanında "KATIB" (kırmızı, kalın, 30 px) ve altında "Bireysel
  Krediler Analitik ve Tahsis BI" (açık temada siyah, koyu temada beyaz)
  METİN olarak yazılıyor. katib_*.png görselleri artık kullanılmıyor;
  önceki iki turun görsel yükleme ve kenar kırpma kodu kaldırıldı.
- Boyut: style.css'te #urun-adi (font-size: 30px) ve #urun-alt
  (font-size: var(--fs-govde)).

Önceki tur: **KATIB görseli büyütüldü (kenar boşluğu kırpılıyor)**. Değiştir: `webapp/app.js`, `webapp/style.css` (yalnız sayfa yenileme; önceki turun dosyaları gerekli)

- PNG'nin etrafındaki boş alan (şeffaf ya da köşe pikseliyle aynı renk)
  tarayıcıda kırpılıyor (`gorselKenarKirp`); klasördeki dosyaya
  dokunulmaz.
- Görsel yüksekliği 56 px'ten 68 px'e çıktı (en çok 420 px genişlik).
  Kırpma yapılamazsa görsel olduğu gibi gösterilir.

Önceki tur: **Üst barda ürün adı yerine KATIB görseli**. Değiştir: `webapp/index.html`, `webapp/style.css`, `webapp/app.js`, `webapp/backend.py` (backend yeniden başlatılmalı)

- "Akıllı Modelleme Platformu" ve "Bireysel Krediler Analitik ve Tahsis
  BI" yazıları kaldırıldı; logonun yanına görsel geldi.
- Açık tema: LLM_WEBAPP_GORSEL/katib_siyah_yazi.png; koyu tema:
  LLM_WEBAPP_GORSEL/katib_beyaz_yazi.png (`/gorsel/katib_acik`,
  `/gorsel/katib_koyu`). Dosya adı değişirse yalnız backend.py
  GORSELLER'i düzenleyin.
- Görsel yüksekliği üst bar - 22 px (56 px). Veri seti / sözlük çipleri
  görselin yanında kalır. Dosya bulunamazsa görsel gizlenir.

Önceki tur: **Şüpheli kısaltma anlamı silinmiyor, uyarıyla gösteriliyor**. Değiştir: `fe_agent/kisaltma.py`, `fe_agent/llm.py`, `fe_agent/akis_faz01.py`, `webapp/app.js`, `webapp/style.css` (backend yeniden başlatılmalı)

- Eskiden anlam sessizce siliniyordu; artık kalıyor ve Kaynak sütununda
  turuncu uyarı yazıyor (satırın solunda turuncu çizgi):
  - anlam, birlikte geçtiği başka bir kısaltmanın anlamını da içeriyor
    (<KISA> "ilk işlemden bu yana geçen süre", <KISA> "işlem")
  - dil modeli emin olamadı: sözlük istatistiğinin anlamı uyarıyla kalır
  - anlam tamamen Türkçe değil ya da 6 kelimeden uzun
- Eş anlamlı kısaltmalar (aynı anlamı veren iki kısaltma, ör. NUM ve <KISA>
  "adet") uyarı almaz.
- Tek boş kalan durum: dil modeli anlam yerine kısaltmanın kendisini
  verdiyse (<KISA> -> "score"); istatistik anlamı varsa o uyarıyla gelir.
- Uyarılı anlamlar kalıcı öğrenmeye girmez; siz onaylarsanız (hafızaya
  kaydederseniz) girer. Excel'de Kaynak sütununa "UYARI: ..." eklenir.
- Yalın hâl: "borcu" -> "borç" (harç, amaç, güç, kazanç, sayaç ... aynı);
  "yolcu", "alıcı" gibi -cı ekli kelimeler kesilmez.

Önceki tur: **01.2 akışı ayrıldı: Kısaltma Sözlüğü, Kolon Adı Önerileri, Sözlük Tanım Kontrolü ayrı adımlar**. Değiştir: `fe_agent/akis_kayit.py`, `fe_agent/akis_durum.py`, `fe_agent/akis_panel.py`, `fe_agent/akis_faz01.py`, `fe_agent/kisaltma.py`, `fe_agent/llm.py`, `webapp/backend.py`, `webapp/app.js` (backend yeniden başlatılmalı)

1) Yeni adım sırası (A ve B modu)
- 01.2.3 Sözlük Tanımları (değişmedi)
- 01.2.4 Kısaltma Sözlüğü: anlamı dolu her satır bu çalışmanın kısaltma
  sözlüğü olur (`durum["kisaltma_sozluk"]`); "Hafızaya Kaydet" işaretli
  olanlar ayrıca proje geneline yazılır. Kısaltma yoksa adım kendiliğinden
  geçer; "Kısaltmaları Onaylamadan Devam Et" ile atlanabilir.
- 01.2.5 Kolon Adı Önerileri: onaylanan anlamlarla açıklamada geçip adda
  olmayan kısaltmalar için yeni ad. Uygula işaretli adlar yalnız AMP
  kopyalarında uygulanır. Geçersiz ad varsa adım geçmez ve sebebi yazar.
  Öneri yoksa adım kendiliğinden geçer; "Ad Değiştirmeden Devam Et" ile
  atlanabilir (bu durumda kayıtlı yeni adlar temizlenir).
- 01.2.6 Sözlük Tanım Kontrolü: kart yalnız tanım kontrolü.
- Kayıtlı çalışmalar: sıra sürümü 3. 01.2.3'ten sonraki bir adımda
  kalmış çalışma 2 adım kaydırılır (sürüm 1'den gelen önce 1, sonra 2).

2) Kısaltma anlamında genel anlam önce
- Dil modeli önce kısaltmanın bankacılık / veri bilimindeki genel
  anlamını verir; sözlük kanıttır, otorite değil. Genel anlam sözlükteki
  kullanımla çelişirse satırda "genel anlam; sözlükteki kullanım farklı"
  yazar.
- Bağlam ifadesi anlam olmaz (gün için "günlük ortalama" değil "gün").
- Yalın hâl düzeltmesi: ünlü uyumu kontrol ediliyor; "entropi" artık
  "entrop" diye kesilmiyor (skoru -> skor, adedi -> adet aynı).

3) Tanım kontrolünde beklenen tanım
- Her satıra ad parçalarının onaylı anlamları gider ("AD PARCALARI
  (onayli): <KISA>=işlem · <KISA>=giden · <KISA>=tutar · <KISA>=ortalama"). Model
  beklenen tanımı bunlarla kurar; bir parçanın anlamı tanımda yoksa ya
  da farklıysa düzeltme önerir ve gerekçede o kısaltmayı yazar.
- Açıklama önerilerine ve kontrole giden "KISALTMALAR (kesin)" listesi
  01.2.4'te onaylananları içerir.
- Geri dönüp kısaltma sözlüğü değiştirilirse tanım kontrolü yeniden
  çalışır (eski sonuç kullanılmaz).

Test edilmedi: gerçek dil modelleri ve Dataiku ortamı (sahte modelle
denendi).

Önceki tur: **Bekleme azaltıldı: kayıtlı tanım ve öneriler doğrudan gelir**. Değiştir: `fe_agent/tanim_hafiza.py`, `fe_agent/akis_faz01.py`, `fe_agent/akis.py`, `webapp/backend.py`, `webapp/app.js` (backend yeniden başlatılmalı)

- Rol kolonu (kimlik, hedef, dönem, segment) AYNI veri setinde onaylanmış
  tanımla doğrudan dolar (<KIMLIK_KOLONU>). Başka veri setinden gelen tanım rol
  kolonuna konmaz.
- Öneri önbelleği: PROJE_HAFIZASI/ONERI_ONBELLEGI.parquet (onaylı değil).
  Dil modelinin bir veri setinin kolonu için verdiği son öneri saklanır;
  aynı veri setinin aynı kolonu tekrar gelince model çağrılmaz, öneri
  "Dil Modeli Önerisi" olarak hemen gelir (rn gibi eklenmeyen kolonlar).
  Başka veri setinde kullanılmaz.
- 01.2.4 Kısaltma Sözlüğü artık dil modelini beklemeden açılır
  (eskiden en çok 25 sn bekliyordu); kontrol sürerse kart 5 sn'de bir
  `/kisaltma_alani`'ndan yoklayıp satırları kendiliğinden günceller.
  Elle değiştirilen satırlar ezilmez.

Önceki tur: **Kısaltma düzeltmeleri + açıklama/kolon adı tutarsızlıkları + kolon yeniden adlandırma**. Değiştir: `fe_agent/kisaltma.py`, `fe_agent/llm.py`, `fe_agent/akis_faz01.py`, `fe_agent/akis.py`, `fe_agent/amp.py`, `fe_agent/amp_pandas.py`, `fe_agent/amp_spark.py`, `fe_agent/xlsx_yaz.py`, `webapp/backend.py`, `webapp/app.js`, `webapp/style.css` (backend yeniden başlatılmalı)

1) Kısaltma çıkarımı
- Atama artık BÜTÜN adaylar üzerinden en güçlüden zayıfa (<KISA>'un zayıf
  "karşı" adayı <KISA>'nin "<anlam>"ından önce atanıyordu).
- İki kelimelik ifade, başka bir kısaltmanın en güçlü tek kelime adayını
  içeriyorsa seçilmez (<KISA> -> yüksek, <KISA> -> banka, <KISA> -> yok, <KISA> ->
  bazında, <KISA> -> aktif).
- Harfleri sırayla tutan güçlü aday öne geçer (<KISA>-<anlam>).
- İki harfli kelimeler aday ("ay", "en çok"); "arası" anlam sayılmaz.
- Yalın hâl: karşı, arası, sonu, altı, üstü ... kesilmez (<KISA> "karş").
- Dil modeli kontrolü: parça 12 kısaltma, parçalar aynı anda; örnek 6,
  açıklama 120 karakter (zaman aşımı riski azaldı). Hata sebebi kartta.

2) Tutarsızlık raporu (`kisaltma.tutarsizliklar`, kod tarafında)
- Adda Yok: açıklamada bir kısaltmanın anlamı geçiyor, adda o kısaltma da
  aynı anlamı veren başka kısaltma da yok (ör. "farklı banka adedi",
  adda <KISA> yok -> <KOLON> önerilir). <KOLON>
  "günlük ortalama" işaretlenmez (<KISA> "ortalama" der). Genel kelimeler
  (tanımların %30'undan fazlası) ve adda aynen geçen parçanın yanındaki
  kelimeler (<KISA> "<anlam>sı hhi") sayılmaz.
- Açıklamada Yok: adda kısaltma var, açıklamada anlamı yok.
- 01.2.4 kontrolüne düzeltme önerisi olarak, Excel'e ikinci sayfa
  ("Tutarsızlıklar") olarak gelir.

3) Kolon yeniden adlandırma
- 01.2.4 kartında "Kolon Adı Önerileri" tablosu: Mevcut Ad | Yeni Ad
  (düzenlenebilir) | Uygula; "Seçilen Adları Kaydet" (`/kolon_ad_kaydet`).
  Kurallar: harfle başlar, yalnız harf/rakam/_; mevcut kolon adı ve iki
  kolona aynı ad olamaz; hedef/kimlik/dönem/segment ve süreç dışı
  kolonlar adlandırılmaz.
- Değişken Kontrolü kaydedilince yalnız platform kopyalarında uygulanır:
  AMP_VERISETI (pandas ve Spark) ve AMP_SOZLUK; eşleme
  PROJE_HAFIZASI/<çalışma>/KOLON_AD_ESLEME.parquet. Girdi veri seti ve
  sözlük değişmez. Sağ panel kolon özeti yeni adları gösterir; AMP
  silinince (teyit öncesine dönüş) eski adlara döner.

HATA DÜZELTMESİ (mevcut): AMP_SOZLUK hiç yazılamıyordu ("6 columns
passed, passed data had 4 columns"): Değişken Kontrolü Excel'i dört
kolona indirilince AMP_SOZLUK'u besleyen satırlar da dörde inmişti.
AMP_SOZLUK artık doğrudan teyit satırlarından altı alanla yazılır
(TIP_DEGISIKLIGI: tip dönüşümü seçildiyse evet).

Önceki tur: **Kısaltma önerileri örnekleriyle Excel**. Değiştir: `fe_agent/kisaltma.py`, `fe_agent/akis_faz01.py`, `fe_agent/akis.py`, `webapp/backend.py`, `webapp/app.js` (backend yeniden başlatılmalı)

- Kısaltma Sözlüğü kartında "Örnekleriyle Excel Olarak İndir" düğmesi
  (`/kisaltma_excel`). Aynı dosya çalışma klasörüne de yazılır:
  PROJE_HAFIZASI/<çalışma>/KISALTMA_ONERILERI.xlsx.
- Sütunlar: Kısaltma, Önerilen Anlam, Kaynak, Hafızada Onaylı, Geçtiği
  Tanımlı Kolon, Anlamı Taşıyan Kolon, İstatistik Adayları (yüzde ve
  ayırt), 5 örnek (kolon + açıklama; anlamı taşıyan, çeşitli seçilmiş),
  3 çelişen örnek (anlamı taşımayan; sözlükteki olası hata), boş Karar
  sütunu.

Önceki tur: **Kısaltma kartında düzenlenen satır yeşil**. Değiştir: `webapp/app.js` (yalnız sayfa yenileme)

- Kullanıcı anlamı gelen değerden farklı yazınca satır yeşil
  ("Düzenlendi", lejanta eklendi); eski değere geri yazınca önceki
  rengine (Önerilen mavi / Hafızada Onaylı mor) döner.

Önceki tur: **Kısaltma anlamları yalın hâlde**. Değiştir: `fe_agent/kisaltma.py`, `fe_agent/llm.py` (backend yeniden başlatılmalı)

- Tek kelimelik anlamlar kural tabanlı yalına iner (sözlükte yalın hâli
  geçmese de): bayrağı -> bayrak, skoru -> skor, adedi -> adet, oranı ->
  oran, payı -> pay, entropisi -> entropi, tutarının -> tutar, işlemleri
  -> işlem, dönemi -> dönem, hesabı -> hesap. Sıfat / yapım ekleri
  (-li, -ci, -ki, -siz) ve kredi, bilgi, yeni gibi kelimeler kesilmez.
- Çok kelimeli anlamlara dokunulmaz (<anlam>, değişim katsayısı:
  son kelimenin eki birleşik adın parçası).
- Aynı kural dil modelinin verdiği anlamlara da uygulanır; dil modeline
  "doğru ama ekliyse düzelt, yalın yaz" kuralı eklendi.

Önceki tur: **Kısaltma örnekleri "i" simgesinde**. Değiştir: `webapp/app.js`, `webapp/style.css` (yalnız sayfa yenileme; önceki turun `fe_agent/kisaltma.py` dosyası gerekli)

- Ayrı "Örnek Kolon" sütunu kaldırıldı; örnek kolonlar (en çok 3, kolon
  adı + sözlükteki açıklama) kısaltmanın yanındaki "i" simgesinde.

Önceki tur: **Kısaltma kartında örnek kolon**. Değiştir: `fe_agent/kisaltma.py`, `webapp/app.js`, `webapp/style.css` (backend yeniden başlatılmalı)

- Kısaltma Sözlüğü tablosuna "Örnek Kolon" sütunu: anlamı onaylatan bir
  kolon adı ve sözlükteki açıklaması; en çok 2 örnek daha "i"
  simgesinin arkasında. Örnekler, tanımı anlamı taşıyan kolonlardan
  çeşitli seçilir (farklı kısaltmalarla birlikte geçenler); anlamı
  taşıyan yoksa herhangi bir örnek gelir, kullanıcı çelişkiyi görür.

Önceki tur: **Kısaltma kartı geri yüklemede yeniden kuruluyor**. Değiştir: `webapp/backend.py`, `fe_agent/akis.py`, `fe_agent/akis_faz01.py` (+ önceki iki turun `fe_agent/kisaltma.py`, `fe_agent/llm.py` dosyaları kopyalanmadıysa onlar da; backend yeniden başlatılmalı)

- Sorun: açık kart oturumla birlikte kaydediliyor; kod güncellense de
  sayfa yenilenince kart kaydedilmiş eski satırlarla ("Temel sözlük")
  geliyordu.
- Çözüm: kayıtlı oturum yüklenirken (sayfa açılışı / yenileme) Kısaltma
  Sözlüğü bölümü güncel kod ve güncel hafızayla yeniden kurulur
  (`akis.kisaltma_alani_tazele`). Beklemez: dil modeli kontrolü
  sürüyorsa kartta not yazar, sayfa yeniden açılınca sonuç gelir.

Önceki tur: **Öğrenme döngüsü: çelişen tanımlar, düzeltilmiş hâlden kalıcı öğrenme, onaylı ağırlığı**. Değiştir: `fe_agent/kisaltma.py`, `fe_agent/llm.py`, `fe_agent/akis_faz01.py` (backend yeniden başlatılmalı)

- Kalıcı yazma 01.2.4 sonunda: öğrenilen kısaltmalar KISALTMA_OGRENILEN'e
  ancak düzeltmeler uygulandıktan ya da kontrol atlandıktan (ya da adım
  kendiliğinden geçtikten) sonra, DÜZELTİLMİŞ çalışma kopyası + onaylı
  tanımlardan yazılır (arka planda). Ham sözlükten yazılmaz.
- Çoğunluk azınlığı düzeltir (`kisaltma.celiskiler`, kod tarafında): bir
  kısaltmanın anlamı o kısaltmanın geçtiği tanımlı kolonların en az
  %85'inde geçiyorsa (en az 5 kolon), geçmeyen tanım işaretlenir.
  01.2.4 kontrolünde bu tanım denetçiler "uygun" dese bile satır olarak
  gelir; gerekçe: "Kolon adındaki <KISA>, sözlükteki 412 kolonun %99'unda
  'gelen' anlamında kullanılmış; bu tanımda 'gelen' geçmiyor." Düzeltmeyi
  dil modeli yazar (pencere / ölçü korunur); yazamazsa satır mevcut
  tanımla gelir, kullanıcı düzenler.
- Onaylı tanımlar 3 kat ağırlıkla sayılır (tanım hafızasındaki metinle
  aynı olan tanım): zamanla onaylanan doğru bilgi baskın gelir.

Önceki tur: **Kısaltmalar kendiliğinden öğrenilip saklanıyor**. Değiştir: `fe_agent/kisaltma.py`, `fe_agent/akis_faz01.py` (backend yeniden başlatılmalı)

- Yeni dosya: `PROJE_HAFIZASI/KISALTMA_OGRENILEN.parquet` (onaylı
  hafızadan ayrı, onay istemez). Sözlüklü her çalışmada, dil modeli
  kontrolünden geçen (doğrulanan ya da modellerin anlaştığı) anlamlar
  kendiliğinden yazılır: KISALTMA, ANLAM, KOLON (kaç kolondan), VERI_SETI,
  KAYNAK, TARIH. "Emin olamadı" olanlar yazılmaz.
- Aynı kısaltma başka sözlükte farklı anlamla çıkarsa daha çok kolonla
  öğrenilen kalır; aynı anlamsa kolon sayısı büyüğü tutulur.
- Sözlüğü olmayan / az tanımlı çalışmada: bu dosya dil modeline tahmini
  kısaltma olarak gider (<KISA> -> işlem) ve kartta "Önceki sözlüklerden
  öğrenildi · <VERI_SETI>, 908 kolon" diye görünür. Kartta veri
  setinin tanımsız kolon adları da sayılır.
- Öncelik: onaylı hafıza > bu çalışmada öğrenilen > önceki çalışmalardan
  öğrenilen.
- Düzeltme: eşit kanıtlı kısaltmalarda sonuç çalıştırmadan çalıştırmaya
  değişebiliyordu (küme sırası); sıra artık tam belirli.

Önceki tur: **Kısaltmalar sözlükten öğreniliyor (sabit liste yok)**. Değiştir: `fe_agent/kisaltma.py`, `fe_agent/llm.py`, `fe_agent/akis_faz01.py` (backend yeniden başlatılmalı)

- Önceden verilen temel kısaltma listesi KALDIRILDI (kullanıcı kararı:
  "kendi kendine gelişen bir sistem"). Her anlam o çalışmanın
  sözlüğünden ve onaylı tanım hafızasından öğrenilir; yeni onaylanan her
  tanım bir sonraki öğrenmenin girdisi.
- İstatistik bütün tanımlar üzerinden; atama en güçlü kanıttan başlar ve
  bir kısaltma, kolonlarının yarısından fazlasında birlikte geçtiği
  kısaltmaya verilmiş anlamı alamaz (<KISA>, <KISA>'nin "<anlam>"ını almaz,
  "gelen" olur; <KISA>, <KISA>'nin "banka"sını almaz, "adedi" olur).
- Dil modeline her kısaltma için: en güçlü 3 aday ve yüzdeleri, örnek
  kolonlardaki diğer kısaltmaların anlamları ve çeşitli seçilmiş en çok
  8 örnek kolon (her yeni örnek, öncekilerde olmayan kısaltmaları
  getirenlerden). Kural: "kullanıcı bu kısaltmanın geçtiği kolonlarda hep
  şu kelimeyi yazmış, demek ki bundan bahsediyor"; yalın hal; emin
  değilse boş.
- Kart: Kaynak sütunu "Dil modeli doğruladı (8 örnekle)" gibi örnek
  sayısını yazar. İstemde kesin = yalnız onaylı kısaltmalar.
- İstatistiğin tek başına öğrenemedikleri (her tanımda geçen "işlem"
  gibi) dil modeline yine sorulur.

Önceki tur: **Kısaltma: birlikte geçen kısaltmanın anlamı verilmez**. Değiştir: `fe_agent/kisaltma.py`, `fe_agent/llm.py` (backend yeniden başlatılmalı)

- Bir kısaltmanın kolonlarının yarısından fazlasında birlikte geçen ve
  anlamı kesin bilinen (temel / onaylı) kısaltmanın anlamı o kısaltmaya
  verilmez: <KOLON>'de "farklı" <KISA>'in, "banka" <KISA>'nin
  -> <KISA> "adet". Karşılaştırma kelime başıyla (gün -> günün de yakalanır).
- Dil modeline her kısaltma için "bilinen" satırı gider (örnek kolonlardaki
  diğer kısaltmaların kesin anlamları); model bunları kullanamaz.
  Model yine de birinin anlamını verirse kod kapısı onu düşürür.
- Yalın hal: temel sözlükteki kelimeler de kaynak (adedi -> adet,
  sözlükte "adet" geçmese de).

Önceki tur: **Avatar ve adım başlığı bir kademe küçüldü**. Değiştir: `webapp/style.css` (yalnız sayfa yenileme)

- Sohbet avatarı 48px -> 42px; adım bloğu başlığı 15px -> 14px. Alt
  adım başlığı (01.2.1 ...) 13px kaldı.

Önceki tur: **Geçilen adımda metin gri, seçilenler siyah**. Değiştir: `webapp/style.css` (yalnız sayfa yenileme)

- Geçilen adım bloğunda (ve gruplu bloğun geçilen alt bölümünde) bütün
  yazılar gri (#767676). Seçilenler tam renkte kalır: seçilen başlangıç
  kartı, form kutularındaki seçilmiş değerler (veri seti, sözlük,
  hedef ...) ve tablolardaki giriş kutuları. Kırmızı / yeşil durum
  renkleri ve çipler değişmez.

Önceki tur: **Adım başlıkları büyüdü, geçilen adım gri**. Değiştir: `webapp/style.css` (yalnız sayfa yenileme)

- Adım bloğu başlığı (01.1 Başlangıç Seçimi, 01.2 ...) 12px -> 15px
  (48px avatarla orantılı); alt adım başlığı (01.2.1 ...) 12px -> 13px.
- Geçilen adımın başlığı gri (#767676, iki temada aynı; beyazda 4,54:1,
  siyahta 4,6:1). Yanıt bekleyen adım kırmızı kalıyor.

Önceki tur: **Form etiketleri yeniden sola hizalı**. Değiştir: `webapp/style.css` (yalnız sayfa yenileme)

- Baz Veri Seti, Baz Sözlük, Hedef Değişken ... etiketleri kutunun sol
  kenarıyla hizalı. Tek satır düzeni ve iki satıra geçen etiketlerde
  kutuların aynı hizada kalması aynen duruyor.

Önceki tur: **Kısaltma önerileri iyileştirildi**. Değiştir: `fe_agent/kisaltma.py`, `fe_agent/llm.py`, `fe_agent/akis_faz01.py`, `webapp/app.js` (backend yeniden başlatılmalı)

- Temel sözlük (`kisaltma.TEMEL`): <KISA> gelen, <KISA> giden, <KISA> toplam, <KISA>
  gün, <KISA> ay, <KISA> yüksek, <KISA> düşük, <KISA> bazında, <KISA> başına, <KISA> en
  büyük (1. sıradaki), <KISA>/<KISA>... saat dilimi, <KISA>/<KISA> ... sabit
  ve kesin. İki anlamlı olanlar (<KISA>, CURR, MON, VOL) bilerek yok.
- Çıkarım kuralı: temel kısaltmalar yarışmaz; bir anlamı en güçlü
  kanıtla alan kısaltmadan sonrakiler ikinci adaya geçer (yoksa boş);
  bir kısaltmanın her kolonunda birlikte geçen temel kısaltmanın anlamı
  ona verilmez (<KOLON>: "bayrak" <KISA>'in); ekli biçim, yalın hali
  sözlükte de geçiyorsa yalına iner (adedi -> adet).
- Dil modeli kontrolü (`llm.kisaltma_dogrula`): liste, kısaltma başına 4
  örnek kolonla iki modele sorulur, anlaşamazlarsa hakem. 01.2.3'te arka
  planda başlar; 01.2.4 kartı sonucu en çok 25 sn bekler, yetişmezse
  kural tabanlı liste ve not gelir. Emin olunamayan anlam boş kalır.
- Dil modeline giden istemde KISALTMALAR (kesin: onaylı + temel) ve
  KISALTMALAR (tahmini: sözlükten / dil modelinden) ayrı; tahmini anlam
  kolon adı ve örneklerle çelişirse kullanılmaz.
- Kart: lejantta "Sözlükten Çıkarıldı" yerine "Önerilen"; Kaynak sütunu
  anlamın nereden geldiğini yazar (Temel sözlük / Sözlükten / Dil modeli
  doğruladı / Dil modeli önerdi / Dil modeli emin olamadı).

Önceki tur: **Logo ve avatar büyütüldü**. Değiştir: `webapp/style.css` (yalnız sayfa yenileme)

- Sol üst logo 59px -> 72px yükseklik (üst barın neredeyse tamamı).
- Sohbet avatarı 34px -> 48px.

Önceki tur: **Gri yazı kaldırıldı**. Değiştir: `webapp/style.css` (yalnız sayfa yenileme)

- İkincil yazılar (açıklamalar, notlar, tip sütunu, sağ panel etiketleri)
  açık temada siyah, koyu temada beyaz (`--metin-soluk` = ana metin).
- Saydamlıkla grileştirilen üç yazı da tam renk: faz özetleri (sol
  panel), arşivdeki çalışma alt satırı ve boş arşiv notu.
- Bilerek bırakılanlar: boş kutudaki yer tutucu ("Açıklama", "Kolon
  ara…") yarı saydam, yoksa dolu değer gibi okunur; kilitli / pasif /
  süreç dışı öğelerin soluklaşması bir durum göstergesi.

Önceki tur: **Koyu tema düzeltmeleri**. Değiştir: `webapp/style.css` (yalnız sayfa yenileme)

- Sözlük tablosundaki değişken adı koyu temada beyaz: tablo hücrelerinin
  yazı rengi artık açıkça veriliyor (Dataiku sayfasının kendi "td"
  kuralı araya girse de).
- Açık temada gri zeminli olup koyu temada kaybolan yerler (sağ üstteki
  Çalışma / Özet sekmesi, başlangıç kartındaki A / B rozeti) koyu temada
  görünür gri. Otomatik tarama: açık temada gri olup koyu temada siyaha
  düşen başka öğe kalmadı (sohbet zemini bilerek siyah).

Önceki tur: **Koyu tema yenilendi**. Değiştir: `webapp/style.css` (yalnız sayfa yenileme)

- Koyu temada zemin ve kartlar siyah, ayrım kenarlıkla; gri zemin
  isteyen yerler (tablo başlığı, iç kutu, değer çipi) siyahtan görünür
  biçimde ayrışan gri (#141414 / #1F1F1F).
- Vurgu renkleri sakinleştirildi: kırmızı #E5262B (somon değil), yeşil
  #34B86E, kehribar #E8A23A; sözlük satır renkleri daha düşük
  saydamlıkla.
- İkincil (gri) yazı iki temada tek renk: #767676 (beyazda 4,54:1,
  siyahta 4,6:1).
- Açılır seçim listesi iki temada da ince kırmızı çerçeveli.

Önceki tur: **Tanımlar tamamen Türkçe**. Değiştir: `fe_agent/llm.py`, `fe_agent/akis_faz01.py` (backend yeniden başlatılmalı)

- Dil modeli kuralları: tanım her zaman Türkçe karakterle (ç ğ ı İ ö ş ü)
  ve Türkçe kelimelerle yazılır; örnek / onaylı / mevcut tanımlar
  karaktersiz ya da İngilizce olsa bile. Kural içindeki örnekler de
  Türkçe karakterli yazıldı.
- Türkçe kapısı (`llm.turkce_sorunu`): İngilizce kelime ya da Türkçe
  karakteri eksik yazılmış kelime ("musteri", "islem", "gunde" ...)
  bulursa tanım "tamamen Türkçe değil" sayılır. Büyük harfli kısaltmalar
  (<KISA>, <KISA>) sayılmaz. Kelime listesiyle çalışır; listede olmayan bir
  karaktersiz kelimeyi yakalamayabilir.
- 01.2.3 öneriler: Türkçe olmayan öneri ayrı bir çağrıyla anlam
  korunarak Türkçeye çevrilir; çevrilemezse öneri gösterilmez. Türkçe
  olmayan onaylı tanım hafızadan doğrudan doldurulmaz (dil modeli onu
  örnek alıp Türkçe yazar).
- 01.2.4 tanım kontrolü: sözlükteki tanım Türkçe değilse, denetçiler
  "uygun" dese bile Türkçeye çevrilmiş hali öneri olarak gelir
  (gerekçe: "Tanım tamamen Türkçe değil (...)"). Anlam kapıları
  (pencere sayıları, oran / aralık, uzunluk) çeviriye de uygulanır.

Önceki tur: **Form etiketleri ortalı**. Değiştir: `webapp/style.css`

- Seçim formlarında etiket (Hedef Değişken vb.) kutunun ortasına hizalı.
- Dar ekranda etiket "…" ile kesilmek yerine iki satıra geçer; bütün
  etiketler aynı yüksekliği paylaşır (alta yaslı), kutular yine aynı
  hizada (CSS subgrid; güncel Chrome/Edge/Firefox).

Önceki tur: **Form alanları hep tek satırda**. Değiştir: `webapp/app.js`, `webapp/style.css` (önceki turdaki `fe_agent/akis_faz01.py` da kopyalanmadıysa o da)

- Seçim formlarında sütun sayısı alan sayısı kadar sabit (eşit
  genişlik); ekran daralınca alan alt satıra kaymıyor, uzun etiket
  "…" ile kısalıyor (tamamı üzerine gelince görünür).
- 900 / 1250 / 2000 px genişlikte dört alan aynı hizada denendi.

Önceki tur: **Zorunlu alanlarda kırmızı yıldız**. Değiştir: `webapp/app.js`, `webapp/style.css`, `fe_agent/akis_faz01.py`

- Zorunlu alanların etiketinin yanında kırmızı "*". İsteğe bağlı
  alanlardaki "(İsteğe Bağlı)" yazısı kaldırıldı (Baz Sözlük, kaynak
  tablo sözlükleri, Dönem Kolonu, Segment Kolonu).

---

Önceki tur: **Form alanları hizalı**. Değiştir: `webapp/app.js`, `webapp/style.css`

- Form alanları eşit sütunlu ızgarada; genişlik yetmezse 2x2'ye iner.
- Alan etiketi tek satır; "(İsteğe Bağlı)" küçük ve soluk. Sığmazsa "…"
  ile kısalır, tamamı ipucunda. Aynı satırdaki kutular hep aynı hizada.

---

Önceki tur: **Roller dil modeline iletiliyor**. Değiştir: `fe_agent/llm.py`, `fe_agent/akis_faz01.py`

- 01.2.2'de seçilen hedef / kimlik / dönem / segment kolonları açıklama
  önerisinde ve tanım kontrolünde modele "ROL: kimlik kolonu" gibi
  satırla gider. Talimatta her rol için nasıl yazılacağı var (kimlik:
  "Müşteri tekil kimlik numarası" gibi, işlem anlatma; hedef: 1'in neyi
  ifade ettiği; dönem: gözlem dönemi; segment: alt grup).
- Rolü olan kolon onaylı tanım hafızasından DOĞRUDAN doldurulmaz ve aynı
  adlı onaylı tanım ona "esas alınacak tanım" olarak gitmez; tanım rolden
  yeniden yazılır. Onaylanınca hafıza yeni metinle güncellenir.

---

Önceki tur: **Sözlük kartı renk açıklaması kısaltmalı**. Değiştir: `webapp/app.js`

- Sözlükte Boş (SB) · Onaylı Tanım (OT) · Dil Modeli Önerisi (DMÖ) ·
  Sözlüğe Eklendi (SEN) · Sözlüğe Eklenmedi (SENM).

---

Önceki tur: **Sözlük kartı çipleri**. Değiştir: `webapp/app.js`, `webapp/style.css`

- "Onaylı Tanım" çipi kısaldı: "OT" (açılımı ve kaynak veri seti ipucunda);
  renk açıklamasında "Onaylı Tanım (OT)".
- Zorunlu rol çipi Başlık Biçiminde ("Kimlik Kolonu", "Hedef Değişken")
  ve sarı yerine kırmızı.

---

Önceki tur: **Açılır listeler hep yukarı; başlangıç ve form metinleri sadeleşti**. Değiştir: `fe_agent/akis_metin.py`, `fe_agent/akis_faz01.py`, `webapp/app.js`

- Bütün açılır listeler alanın ÜSTÜNE açılır; üstte yer yoksa sohbet
  kaydırılarak yer açılır.
- Metinler: karşılama, iki başlangıç kartı, Baz Veri Seti ve Baz Sözlük
  formu, kaynak sözlük formu, Modelleme Tanımları formu ve alan altı
  açıklamaları yeniden yazıldı; "(Opsiyonel)" → "(İsteğe Bağlı)".

---

Önceki tur: **Başlangıçlar birleşti: A-C → "Baz Veri Seti Mevcut", B-D → "Kaynak Tablolar Mevcut"**. Değiştir: `fe_agent/akis_metin.py`, `fe_agent/akis_faz01.py`, `fe_agent/akis_durum.py`, `fe_agent/akis_panel.py`, `webapp/app.js`

- Başlangıç ekranında iki kart. Sözlük her ikisinde İSTEĞE BAĞLI:
    A: "Baz Sözlük (Opsiyonel)" boş bırakılabilir.
    B: her kaynak tablonun sözlüğü "(Opsiyonel)"; boş alan sözlük yok demek.
- Sözlük seçilmediyse boş bir sözlük tabanı kullanılır; çalışma kopyası
  veri setiyle eşitlenirken bütün kolonlar açıklaması boş eklenir ve
  hepsi 01.2.3 Sözlük Tanımları kartında listelenir: önce onaylı tanım
  hafızası, kalanlar dil modeli. Öneri gelen satırlar "Sözlüğe Ekle"
  İŞARETLİ gelir (sözlük seçildiyse eskisi gibi işaretsiz).
- 01.2.4 Sözlük Tanım Kontrolü: kontrol edilecek mevcut tanım yoksa
  (sözlük seçilmedi) adım kendiliğinden geçer.
- B'de kaynak sözlüklerden kurulan baz sözlük artık ortak
  MODELLEME_SOZLUK veri setine değil, çalışmanın kendi klasörüne
  (/vN/KAYNAK_SOZLUK.parquet) yazılıyor.
- Eski C ve D çalışmaları kendi adım listeleriyle (Sözlük Üretimi dahil)
  açılmaya devam eder; yeni çalışmada C/D seçilemez.

---

Önceki tur: **C başlangıcı açıldı (Baz Veri Seti Mevcut - Baz Sözlük Mevcut Değil)**. Değiştir: `fe_agent/akis_metin.py`

- Adımlar: Başlangıç → Baz Veri Seti → Sözlük Üretimi → Modelleme
  Tanımları → Değişken Kontrolü → Örneklem ve Doğrulama.
- Sözlük üretimi onaylı tanım hafızasını ve onaylı kısaltmaları bağlam
  olarak kullanır.

---

Önceki tur: **Açılır listede fare kaydırma hatası**. Değiştir: `webapp/app.js`

- Veri seti / sözlük seçim listesinde fare yarım görünen bir adın üzerine
  gelince liste kendiliğinden kayıyordu (fare başka adın üzerine düşüyordu).
  Artık fareyle vurgulama listeyi kaydırmıyor; yalnız klavye (ok tuşları,
  Home/End) vurguyu görünür alana getiriyor.

---

Önceki tur: **Hafızada onaylı olanlar mor**. Değiştir: `webapp/app.js`

- Kısaltma Sözlüğü'nde hafızada onaylı satırlar yeşil yerine mor (tanım
  tablolarındaki "Onaylı Tanım" satırlarıyla aynı renk).

---

Önceki tur: **01.2.4 tanım kontrolü önce onaylı tanım hafızasıyla**. Değiştir: `fe_agent/akis_faz01.py`, `webapp/app.js`

- "Tanımları Kontrol Et" basılınca her dolu tanım önce onaylı tanım
  hafızasıyla karşılaştırılır (dil modeli yok):
    aynı   -> kontrol edilmez (zaten onaylı)
    farklı -> onaylı tanım DOĞRUDAN öneri olarak hemen listelenir
              ("Onaylı Tanım" çipi, mor); değiştirip uygularsanız hafıza o
              metinle güncellenir
    yok    -> dil modeli kontrolüne gider
- Durum satırında: kaç tanım hafızayla aynı, kaç tanımda fark var.

---

Önceki tur: **Boş tanımlar önce onaylı tanım hafızasından**. Değiştir: `fe_agent/tanim_hafiza.py`, `fe_agent/akis_faz01.py`, `webapp/app.js`, `webapp/style.css`

- 01.2.3'te sözlükte tanımı olmayan bir kolonun AYNI ADLA onaylı tanımı
  hafızada varsa satır o metinle dolu gelir, dil modeli o kolon için
  çağrılmaz. Aynı veri setinde onaylanmış olan önceliklidir, yoksa en son
  onaylanan. Satırda "Onaylı Tanım" çipi (üzerinde hangi veri setinden
  geldiği), mor zemin; renk açıklamasına "Onaylı Tanımdan" eklendi.
- Hafızada olmayanlar önceki gibi dil modeline gider (onaylı tanımlar,
  kısaltmalar ve sözlük örnekleri bağlamıyla).
- Onaylanınca hafızaya "onaylı hafızadan alındı, yeniden onaylandı"
  kaynağıyla tekrar yazılır (bu veri seti için).

---

Önceki tur: **Kısaltma sözlüğü (<KISA>, <KISA>, <KISA> ...) + onaylı kısaltma hafızası**. Değiştir: `fe_agent/kisaltma.py` (YENİ), `fe_agent/akis_faz01.py`, `fe_agent/akis.py`, `fe_agent/llm.py`, `webapp/backend.py`, `webapp/app.js`, `webapp/style.css`

- Çıkarım (dil modeli yok): kolon adı parçalara bölünür; bir kelime,
  adında o parça geçen kolonların tanımlarında sık (≥ %60), geçmeyenlerde
  belirgin seyrekse (fark ≥ 0,3) parçanın anlamı sayılır. En az 3 kolon.
  İki kelimelik anlam (<KISA> → <anlam>) iki kelimesi de parçaya özgüyse.
  Kaynak: sözlüğün çalışma kopyası + onaylı tanım hafızası.
- 01.2.4 kartının başında "Kısaltma Sözlüğü": Kısaltma | Anlam
  (düzenlenebilir) | Kaynak (ör. "Sözlükten: 120 kolonun %98'inde") |
  Hafızaya Kaydet. "Seçilenleri Hafızaya Kaydet" adım akışından bağımsız;
  işareti kaldırıp kaydedilen hafızadan silinir.
- Hafıza: PROJE_HAFIZASI/KISALTMA_HAFIZASI.parquet (proje geneli; KISALTMA,
  ANLAM, KAYNAK, KULLANICI, TARIH).
- Kullanım: açıklama önerisi (01.2.3), tanım kontrolü (01.2.4) ve sözlüksüz
  modlarda sözlük üretimi (C/D) istemlerine "KISALTMALAR" bloğu gider
  (yalnız o gruptaki kolon adlarında geçenler). Onaylı anlam, çıkarılanın
  önüne geçer. C/D'de onaylı tanım hafızası da örnek olarak gider.

---

Önceki tur: **Sözlük önerileri sade yazılsın**. Değiştir: `fe_agent/llm.py`

- Tüm sözlük istemlerine (açıklama, kontrol, hakem) "SADE YAZ" kuralı:
  kısa, tek anlamlı, tekrarsız, kurumun yazım tarzı uzunluğunda; tanımlar
  sonra değişken üretiminde de dil modeline girdi olacak. Örnek UZUN /
  SADE oran tanımı istemde.
- Kural kapısı: en az 4 kelimelik dolu bir tanım yerine 1,3 katından uzun
  öneri listelenmez (boş / tek kelimelik tanımların düzeltmesi etkilenmez).

---

Önceki tur: **Sol panel İş Akışı alt adımları**. Değiştir: `webapp/app.js`, `webapp/style.css`

- Gruplu satırın (01.2 Veri ve Model Tanımları) altında alt adımlar
  numarasıyla listeleniyor: 01.2.1 … 01.2.4. Tamamlandı / aktif /
  henüz gelinmedi işaretleri ve tıklayıp o adıma dönme her alt adımda ayrı.

---

Önceki tur: **01.2.4 Sözlük Tanım Kontrolü isteğe bağlı**. Değiştir: `fe_agent/akis_faz01.py`, `fe_agent/akis.py`, `webapp/backend.py`, `webapp/app.js`

- Adım açılınca kontrol BAŞLAMAZ; kartta kaç tanımın kontrol
  edilebileceği ve iki düğme: "Tanımları Kontrol Et" / "Kontrol Etmeden
  Devam Et". Basılmadıkça hiçbir dil modeli çağrılmaz.
- "Kontrol Etmeden Devam Et" kontrol sürerken de açık: kontrol durur,
  dolu tanımlara dokunulmaz, 01.3'e geçilir.
- Yeni uç: POST /tanim_kontrol_baslat.

---

Önceki tur: **Tanım kontrolü anlamı korumalı**. Değiştir: `fe_agent/llm.py`

- Kontrol ve hakem istemlerine "ANLAM KORUNUR" kuralı: öneri pencereyi,
  yönü, tutar/adet ayrımını, oranın payını ve paydasını değiştiremez;
  tanım kolon adıyla tutarlıysa yalnızca aynı anlam daha açık yazılır.
  Örnek doğru/yanlış (<KOLON>) istemde.
- Tüm sözlük istemlerine kolon adı kalıpları: <A>D_<B>D_..._RATIO = son A
  günün son B güne oranı (aralık değil); <KISA> tutar, <KISA> adet, <KISA> ortalama.
- Kural tabanlı son kapı: <KISA> kolonunda "A-B gün arası" diyen öneri ve
  kolon adındaki pencere sayısını (180, 360) düşüren öneri listelenmez.
- Mevcut çalışma: 01.2.4'te Geri Dön; kontrol yeni kurallarla baştan çalışır.

---

Önceki tur: **01.2.3 renk açıklaması yazıları**. Değiştir: `webapp/app.js`

- Dört renk: Sözlükte Boş · Dil Modeli Önerisi · Sözlüğe Eklendi ·
  Sözlüğe Eklenmedi.

---

Önceki tur: **01.2.4 "kontrol edilecek tanım bulunmadı" hatası**. Değiştir: `fe_agent/akis_faz01.py`

- Sözlükten tanımlar, sağ paneldeki Sözlük Tanımı ile AYNI kolon
  bulucuyla okunuyor. Eskisi değişken adı kolonunu yalnız DEGISKEN /
  KOLON / AD / VARIABLE / COLUMN / FEATURE adıyla kabul ediyordu; başka
  adla (ör. DEGISKEN_ADI) hiç tanım okumuyor ve "bulunmadı" diyordu. Aynı
  hata açıklama önerisine giden sözlük örneklerini ve yazım tarzını da
  boş bırakıyordu; o da düzeldi.
- Tanım okunamazsa ya da veri seti adlarıyla eşleşmezse artık nedeni
  kartta yazıyor (sözlüğün kolon adları / örnek adlar).
- Mevcut çalışmada: 01.2.4'teki Geri Dön'e basın; adım yeniden açılır ve
  kontrol baştan başlar.

---

Önceki tur: **Tanım kontrolü ayrı adım: 01.2.4 Sözlük Tanım Kontrolü**. Değiştir: `fe_agent/akis_faz01.py`, `fe_agent/akis_kayit.py`, `fe_agent/akis.py`, `fe_agent/akis_panel.py`, `fe_agent/akis_durum.py`, `webapp/app.js`

- Sıra (A ve B modu): 01.2.3 Sözlük Tanımları (yalnız boş tanımlar) →
  onay → 01.2.4 Sözlük Tanım Kontrolü (dolu tanımlar) → 01.3 Değişken
  Kontrolü. Önceki tur kontrol bölümü 01.2.3 kartının altındaydı; artık
  orada yok.
- 01.2.4 açılınca kontrol başlar; düzeltme önerileri geldikçe listeye
  eklenir, kontrol bitene kadar devam düğmesi kapalıdır. 01.2.3'te
  eklediğiniz tanımlar yeniden kontrol edilmez.
- Kontrol grupları 3'erli paralel çalışır (1.000+ tanımda süre kısalır).
- Eski çalışmalar: 01.2.3'ün ilerisindeki çalışmaların adım konumu
  otomatik bir kaydırılır (yeni adım araya girdiği için); o çalışmalarda
  01.2.4 atlanmış sayılır, Geri Dön ile açılabilir.

---

Önceki tur: **Sözlük Tanımları: yeni renkler, mevcut tanımların kontrolü, çoklu model (orkestra), onaylı tanım hafızası**. Değiştir: `fe_agent/llm.py`, `fe_agent/akis_faz01.py`, `fe_agent/sozluk_calisma.py`, `fe_agent/tanim_hafiza.py` (YENİ), `webapp/backend.py`, `webapp/app.js`, `webapp/style.css`

- Renkler: karar öncesi sarı = açıklama boş, mavi = dil modeli önerisi
  (değiştirilmemiş), renksiz = sizin yazdığınız. Onaydan sonra yeşil =
  sözlüğe eklendi / düzeltme uygulandı, kırmızı = eklenmedi. 01.3
  Değişken Kontrolü tablosu da aynı renkleri kullanıyor (sarı / mavi).
- Kartın altında yeni bölüm "Sözlükteki Tanımların Kontrolü": sözlükte
  tanımı olan kolonların tanımları denetlenir, yalnız düzeltilmesi
  önerilenler "Mevcut Tanım / Önerilen Tanım" olarak listelenir; gerekçe
  "i" simgesinde. Uygula işaretlenen düzeltme sözlüğün ÇALIŞMA KOPYASINA
  yazılır, girdi sözlüğü değişmez. Varsayılan işaretsiz. Kontrol önce
  tanımsız kolonların önerileri bittikten sonra başlar ve kartı
  kilitlemez; beklemeden devam ederseniz kalan tanımlar olduğu gibi kalır.
  Geri dönünce önceki kararlar gelir; uygulanmış düzeltmenin işareti
  kaldırılırsa eski tanım geri yazılır.
- Orkestra (llm.py, ORKESTRA sözlüğü):
    açıklama : Llama ve Qwen Flash bağımsız yazar; farklıysa Qwen
               Thinking hakem seçer / birleştirir.
    kontrol  : Qwen Flash tüm tanımları tarar, sorunlu gördüklerine Llama
               ikinci kez bakar, son kararı Qwen Thinking verir; hakem
               cevap veremezse yalnız iki modelin de "düzelt" dediği
               öneriler gelir.
  Bir model iki kez üst üste cevap veremezse o işin geri kalanında
  atlanır ve kartta "… modeline ulaşılamadı" notu çıkar.
- Yazım tarzı: sözlüğünüzdeki tanımlardan sayılıyor (ortanca kelime
  sayısı, sonda nokta var/yok, büyük harfle başlama, tamamı büyük harf);
  modele yazılıyor ve nokta / baş harf çıktıda ayrıca düzeltiliyor.
- Onaylı tanım hafızası: PROJE_HAFIZASI/TANIM_HAFIZASI.parquet (proje
  geneli, çalışma klasörlerinin dışında). Yalnız onaylananlar girer:
  Sözlüğe Ekle ile onaylanan açıklama, uygulanan düzeltme, sağ panelde
  yazdığınız tanım. Kolonlar: KOLON, ACIKLAMA, VERI_SETI, KAYNAK,
  KULLANICI, TARIH. Öneri ve kontrolde modele "ONAYLI TANIMLAR" olarak
  gider: aynı adlı kolon varsa esas alınır, benzer adlılarda kalıp olarak
  kullanılır.
- Maliyet / süre: grup başına (25 kolon) açıklamada 2 paralel çağrı +
  çoğu zaman 1 hakem çağrısı; kontrolde 1 tarama + yalnız sorunlu
  görülenler için 2 çağrı. Hakem düşünen model olduğu için en yavaşı o.
- Doğrulanmadı: gerçek modellerin çıktısı ve QWEN_FLASH kimliği
  (sahte model cevaplarıyla test edildi).

---

Önceki tur: **Arşiv'de "Listede Görünmeyen Klasörler"**. Değiştir: `webapp/backend.py`, `webapp/app.js`, `webapp/style.css`

- PROJE_HAFIZASI'nda olup Arşiv listesinde olmayan v-klasörleri listenin
  altında nedeniyle yazılır: "Boş klasör" (eski silmelerden kalan),
  "Çalışma dosyası yok · N dosya kalmış", "Başlanmamış çalışma".
- Her birinde "Temizle" (onaylı; Sil ile aynı uç, klasörü kalıcı siler).
- Başka kullanıcının çalışması listelenmez.

---

Önceki tur: **yeni dil modeli + model karşılaştırma testi; açıklama önerisine sözlük bağlamı**. Değiştir: `fe_agent/llm.py`, `fe_agent/akis_faz01.py`

- llm.py'ye QWEN_FLASH (qwen38-flash-next-fp8) eklendi. Varsayılan hâlâ
  Llama; değiştirmek için llm.py'de VARSAYILAN_MODEL satırı.
- Karşılaştırma (Dataiku notebook'ta):
      from fe_agent import llm
      llm.karsilastir()            # llama, qwen_thinking, qwen_flash
  Her model aynı 6 kolonluk açıklama ve 4 değişkenlik SFA isteğiyle
  çağrılır; süre, dönen kayıt sayısı, hata ve örnek çıktılar yazılır.
  Model kimliği yanlışsa o modelde "hata" satırı çıkar; doğru kimlik:
      [l["id"] for l in dataiku.api_client().get_default_project().list_llms()]
- Açıklama önerisi (sözlükte tanımı olmayan kolonlar): isteğe veri setinin
  adı ve sözlüğünüzden adı en çok benzeyen 10 tanımlı kolon örnek olarak
  ekleniyor (aynı ön ekli kolon için diğer aynı ön ekli kolonların açıklamaları). Ham veri
  gitmiyor, yalnızca sözlükteki açıklama metinleri. C/D modunda sözlük
  olmadığı için yalnızca veri setinin adı gidiyor.

---

Önceki tur: **robot görselleri duruma göre**. Değiştir: `webapp/backend.py`, `webapp/app.js`, `webapp/style.css`

- LLM_WEBAPP_GORSEL klasöründe bu adlar olmalı:
    robot_header.png   üst bar solu
    robot_welcome.png  sohbetteki ilk (karşılama) robot
    robot_chat.png     normal konuşma
    robot_think.png    arkada iş sürerken: çalışan bloğun başlığındaki
                       robot geçici olarak bu ("İşlem Devam Ediyor"
                       satırında görsel yok)
- İşlem 2,5 saniyeden kısa sürerse düşünen görsel hiç çıkmaz (titreme yok).

---

Önceki tur: **01.4'te ayrı "Segment Dağılımı" ayarı**. Değiştir: `fe_agent/akis_durum.py`, `fe_agent/akis_faz01.py`, `fe_agent/akis_panel.py`, `webapp/app.js`

- Hedef Dağılımı satırının altında "Segment Dağılımı: Korunsun /
  Korunmasın" (yalnızca segment kolonu tanımlıysa ve hedef dağılımı
  korunurken görünür; açıklaması "i" simgesinde).
- Korunsun: katman segment × hedef (her segmentin payı ve hedef oranı her
  sette aynı). Korunmasın: yalnızca genel hedef oranı korunur.
- Varsayılan Korunsun (önceki davranış).

---

Önceki tur: **sözlük tablosu tam okunur, "i" balonu okunur, zorunlu tanım metni**. Değiştir: `webapp/app.js`, `webapp/style.css`, `fe_agent/akis_faz01.py`

- Sağ panel VERİ & SÖZLÜK tablosunda değişken adı ve sözlük tanımı
  kırpılmıyor; alt satıra kayıyor. Satırlar sabit yükseklikte değil;
  1.042 satırın hepsi bir anda çizilmiyor, kaydırdıkça 120'şer satır
  ekleniyor. Düzenlenebilir tanım kutusu da çok satırlı.
- "i" balonu onaylanmış (soluk) kartta saydam görünüyordu; artık sayfa
  gövdesinde, tam opak açılıyor.
- 01.2.3 notu: "Hedef değişken ve kimlik kolonu sözlükte tanımlı olmak
  zorundadır; dönem ve segment kolonu yalnızca seçildiyse."

---

Önceki tur: **01.4 segment güncellemesi; açılır listelerde tam ad**. Değiştir: `fe_agent/akis_durum.py`, `fe_agent/akis_faz01.py`, `fe_agent/akis_panel.py`, `fe_agent/amp.py`, `fe_agent/amp_pandas.py`, `fe_agent/amp_spark.py`, `webapp/app.js`, `webapp/style.css`

- Açılır listeler en uzun ada göre genişliyor (en çok 560px); kolon adları
  kesilmiyor.
- Segment kolonu tanımlıysa 01.4 kartında "Segmentler" tablosu:
  bölme öncesi segment başına satır, pay ve hedef oranı; bölme
  uygulanınca segment × set (Train / Test (OOS) / Validasyon) satır ve
  hedef oranı.
- Hedef Dağılımı "Korunsun" iken rastgele ayırmada katman segment × hedef:
  her segmentin her setteki payı ve hedef oranı aynı kalır.
- Küçük segment uyarısı: bir sette 50 satırın ya da 20 kötünün altında
  kalan segment tabloda sarı, kartta uyarı satırı.
- Spark yolunda bölme öncesi segment hedef oranı yok (yalnızca satır);
  bölme uygulanınca set bazında gelir. Spark yolu yerelde denenemedi.

---

Önceki tur: **01.2.2'ye Segment Kolonu (Opsiyonel)**. Değiştir: `fe_agent/akis_faz01.py`, `fe_agent/akis_panel.py`, `fe_agent/dokuman.py`, `webapp/app.js`, `webapp/style.css`

- Dönem kolonunun yanında "Segment Kolonu (Opsiyonel)": 2–20 farklı değer
  taşıyan kolonlar listelenir; açıklaması "i" simgesinde.
- Seçilen segment kolonu rol kolonu olur: 01.3'te süreç dışı bırakılamaz,
  01.2.3'te sözlük tanımı zorunlu (hedef/kimlik/dönem gibi). Segment
  sayısı ve segment başına satır sayısı profilden alınır; sağ panelde
  "Segment: <kolon> · N segment", model dokümanında "Segment kolonu".
- Formda boş bırakılan opsiyonel alan (dönem, segment) artık eski
  değerinde kalmıyor; temizleniyor.
- Segment kolonu şimdilik modele normal değişken olarak da girebilir;
  01.4 ve modelleme tarafı (segment başına model / tek model + kırılım)
  ayrıca kararlaştırılacak.

---

Önceki tur: **01.4 kartı sadeleşti, hedef oranı çubukta**. Değiştir: `webapp/app.js`, `webapp/style.css`, `fe_agent/akis_faz01.py`, `fe_agent/akis_panel.py`

- Başlık "Veri nasıl bölünecek" → "Veri Bölme Stratejisi".
- "Önerilen ayarlar uygulandı." ve "Bölme ayarları kaydedildi."
  yazıları kaldırıldı.
- Bölme sonrası "Bölme tanımlandı: … Train / Test / Validasyon satır ve
  hedef oranı" metni yazılmıyor; kimlik notu da (kartta "Aynı <kimlik>:
  bir arada tutulur" yazıyor). Yalnızca dikkat isteyen notlar kalıyor
  (çok küçük set, ara dönem, hazır bölme, kimlik bulunamadı).
- Hedef Dağılımı "Korunsun" iken çubuğun her parçasında ikinci satır
  "Hedef %x": bölme öncesi genel hedef oranı, bölme uygulanınca setlerin
  gerçek oranı. "Korunmasın"da yazmaz. Zamansal bölmede dönem setlerinin
  oranı önceden bilinmediği için yalnızca uygulandıktan sonra yazar.

---

Önceki tur: **sohbet artık en alta atmıyor**. Değiştir: `webapp/app.js`

- Yeni içerik gelince ekran yeni içeriğin BAŞINA kaydırılıyor, en alta
  değil. Zincirleme adımlarda (01.4 sonucu → 02.1 çıktısı → 02.2 kartı)
  ilk gelen çıktı ekranda kalıyor.
- Ekran yalnızca aşağı kayar, yukarı çekilmez.
- İstek sürerken kendiniz kaydırdıysanız (tekerlek, dokunma, klavye,
  kaydırma çubuğu) ekran hiç oynatılmaz. Yeni bir onay/mesaj bunu sıfırlar.
- Yanıt sonrası düğmeye odak verilirken tarayıcının kendiliğinden
  kaydırması da kapatıldı.
- Geçmiş yüklenirken (çalışma açılışı) eskisi gibi en alta gider.

---

Önceki tur: **Arşiv'de silme hızlandı**. Değiştir: `webapp/backend.py`, `webapp/app.js`

- Silme ~20 sıralı Dataiku isteğinden 4'e indi: kayıt 1 okuma, klasör tek
  istekle silme, yalnızca o klasöre bakan 1 kontrol, kayıt 1 yazma.
  Veri seti sahiplik temizliği arka planda.
- Klasör tek istekte silinmezse kalan dosyalar paralel siliniyor; yine
  dosya kalırsa çalışma listede kalıyor ve hata kodu gösteriliyor.
- Onayla'ya basınca satır hemen kalkıyor, silme arkada sürüyor; başarısız
  olursa satır hata mesajıyla geri geliyor. Açık çalışma silinirken
  yanıt bekleniyor (ekran başka çalışmaya geçiyor).

---

Önceki tur: **Arşiv hızlandı, silme klasörü de siliyor, kayıp çalışmalar geri geldi**. Değiştir: `webapp/backend.py`, `webapp/app.js`

- Hız: her çalışma kaydedilirken yanına küçük bir özet yazılıyor
  (/vN/ozet.json). Arşiv yalnızca bunları, paralel okuyor; sohbet
  geçmişini taşıyan çalışma dosyası artık okunmuyor. Özeti olmayan eski
  çalışmada ilk açılışta bir kez okunup özet yazılıyor.
- Arşiv ikinci açılıştan itibaren son listeyi anında gösteriyor, taze
  liste arkadan geliyor.
- Sil: dosyalar silindikten sonra klasörün kendisi de siliniyor; sonra
  klasör yeniden listeleniyor. Dosya kalmışsa çalışma listeden düşmüyor,
  hata kodu gösteriliyor (eskiden sessizce "silindi" sayılıyordu).
- Sil sonrası liste yeniden yüklenmiyor; yalnızca o satır kalkıyor.
- Klasörde duran ama CALISMALAR.json'da girdisi olmayan çalışmalar
  (sahibi sizseniz) listeye geri alınıyor; açılabilir ya da silinebilir.
- CALISMALAR.json okunamazsa yeni numara alma ve silme durur (eskiden
  boş kabul edilip üstüne yazılıyordu; kayıttaki çalışmalar kayboluyordu).

---

Önceki tur: **bölme kurgusu eski haline döndü; yalnızca set adları değişti**. Değiştir: `fe_agent/akis_durum.py`, `fe_agent/akis_faz01.py`, `fe_agent/amp_pandas.py`, `fe_agent/amp_spark.py`, `fe_agent/akis_panel.py`, `fe_agent/dokuman.py`, `fe_agent/validasyon.py`, `webapp/app.js`

- Önceki turlardan birinde bölme kurgusu da değiştirilmişti (zamansalda
  Test (OOS) geliştirme döneminden rastgele, rastgelede Test (OOS) seçimi
  kalkmıştı). Geri alındı: kurgu eskisi gibi, yalnızca adlar yeni.
    eğitim            -> Train (MS)
    validasyon (val)  -> Test (OOS)      istege bağlı, model ayarı için
    test              -> Validasyon (OOT) nihai ölçüm; rastgele bölmede de
                                          bu adla gösterilir
- Rastgele bölmede "Test (OOS) Seti" seçimi geri geldi; üst çubuk ve
  bölüm başlıkları aynı adları taşıyor (Validasyon (OOT) Büyüklüğü).
- Zamansal bölmede Test (OOS) yine eğitim dönemlerinden, dönem bazında
  ayrılıyor; varsayılan kapalı.

---

Önceki tur: **tip kararı yalnızca SFA'da**. Değiştir: `fe_agent/sfa_karar.py`, `fe_agent/akis_faz02.py`, `fe_agent/akis_faz01.py`, `fe_agent/llm.py`, `webapp/backend.py`, `webapp/app.js`, `webapp/style.css`

- 01.3 artık model değişkenlerine tip önerisi yapmıyor. Yalnızca dönem
  kolonunun tarih (dönem) işareti kaldı (model değişkeni değil, bölmenin
  anahtarı). Önceden model değişkenlerine yazılmış tip seçimleri, 01.3
  kartı bir kez daha açıldığında temizlenir.
- SFA karar formunun ilk alanı "Tip": Kaynak Tip ya da verinin tam
  kolonla izin verdiği dönüşüm (sayısal → kategorik; metin → sayısal,
  ondalık nokta / virgül). Tarihe çevirme SFA'da yok.
- Kural önerir: metin olup değerlerin tamamı sayı olan kolon → sayısal
  (00123 gibi kodlar hariç); adı KOD/TIP/SEGMENT… olan, tam sayı değerli
  sayısal kolon → kategorik. Öneri varsa SFA o değişkeni yeni tipiyle
  ölçer; gerekçede yazar.
- Tip değişince o değişkenin SFA'sı (IV, C-value, aralıklar, grafik) yeni
  tiple yeniden hesaplanır; diğer karar alanları yeni tipe göre kuraldan
  yeniden önerilir, karar "Sizin Kararınız" olur.
- Yapay zekâ tipi değiştirmez (tipin cevabı verinin kendisinde); diğer
  alanlara yeni tipe göre karar verir.
- Tip kararı Analitik Baz Set'te diğer işlemlerden önce uygulanır. SFA
  onay özetine "Tip Değişikliği" satırı eklendi.

---

Önceki tur: **01.3 Değişken Kontrolü'ne tip süzgeci eklendi**. Değiştir: `webapp/app.js`

- Arama kutusu ile sıralama arasında "Tip: Tümü" açılır listesi; listedeki
  tipler (kategorik, sayısal, tarih…) seçilince yalnızca o tipteki
  satırlar görünür. Arama ve sıralamayla birlikte çalışır; "Görünenleri
  Süreç Dışı Bırak / Sürece Al" sayıları süzgece göre güncellenir.

---

Önceki tur: **01.3 Değişken Kontrolü sadeleşti**. Değiştir: `webapp/app.js`, `webapp/style.css`, `webapp/backend.py`, `fe_agent/akis_faz01.py`

- Tablo dört kolon: Değişken · Tip · Sözlük Tanımı · Süreç Dışı.
  Tip Değişikliği ve Null Oranı kolonları, "null >" eşik kutusu ve
  "Null oranı ↓/↑" sıralamaları kaldırıldı (SFA adımında görülüyor).
- Kaydettikten sonra indirilen Excel listesi de aynı dört kolon.
- Sistemin otomatik tip önerileri (ör. dönem kolonu tarih) arka uçta
  uygulanmaya devam ediyor; yalnızca elle seçim ekranı yok.

---

Önceki tur: **AMP çalışma klasöründe ve tek kaynak; setler Train (MS) / Validasyon (OOT) / Test (OOS)**.
Değiştir (fe_agent): `amp.py`, `amp_pandas.py`, `amp_spark.py`, `spark_is.py`, `akis_durum.py`, `akis_faz01.py`, `akis_faz02.py`, `akis_sohbet.py`, `akis_panel.py`, `sozluk_calisma.py`, `dokuman.py`, `validasyon.py`
Değiştir (webapp): `app.js` (JS)
Kütüphane dosyalarını değiştirdikten sonra webapp backend'ini yeniden başlatın.
Devam eden çalışmada «01.3 Değişken Kontrolü» adımına Geri Dön ile dönüp kaydedin:
AMP bu çalışmanın klasörüne yeniden yazılır ve bölme yeni düzenle yapılır.

- AMP_VERISETI ve AMP_SOZLUK çalışmanın kendi klasörüne yazılır
  (PROJE_HAFIZASI/<çalışma>/AMP_VERISETI.parquet, AMP_SOZLUK.parquet).
  Büyük veride (Spark) Dataiku kuralı gereği çıktı bir veri setidir; adı
  çalışmaya özeldir (AMP_VERISETI_V8, bölünmüş hali AMP_VERISETI_V8_B).
- Değişken Kontrolü kaydedildikten sonra tek kaynak AMP_VERISETI ve
  AMP_SOZLUK: bölme de AMP'den okur, sözlük okumaları ve sağ paneldeki
  düzenlemeler AMP_SOZLUK'a gider; kaynak tabloya ya da sözlüğe dönülmez.
- 01.3 ya da öncesine Geri Dön ile dönülünce AMP_VERISETI, AMP_SOZLUK ve
  sonraki bütün sonuçlar silinir; adımlar oradan yeniden yapılır.
- Setler (kurum düzeni): Train (MS); Validasyon (OOT) = son dönem(ler);
  Test (OOS) = geliştirme döneminden rastgele (hedef oranı korunarak,
  kimlik varsa müşteri bazında) ayrılan pay. Zamansal bölmede Test (OOS)
  varsayılan olarak açık (%20). Dönem kolonu yoksa Validasyon (OOT) yoktur,
  yalnızca Test (OOS) ayrılır.
- Bölme sonucu, bölme kartı, sağ panel, stabilite (Train ↔ Validasyon OOT),
  validasyon kriterleri ve model dokümanı yeni adlarla.

---

Önceki tur: **Sözlük çalışma kopyası veri setiyle eşitleniyor**.
Değiştir (fe_agent): `sozluk_calisma.py`, `akis_faz01.py`, `akis_panel.py`
Kütüphane dosyalarını değiştirdikten sonra webapp backend'ini yeniden başlatın.

- Veri seti ve sözlük seçilince çalışma sözlüğü veri setinin kolonlarına
  eşitlenir: veri setinde olmayan sözlük satırları çıkarılır, sözlükte
  olmayan kolonlar açıklaması boş satır olarak eklenir (Sözlük Tanımları
  adımında tanımsız listelenir), satırlar veri setinin kolon sırasına dizilir.
- Yalnızca büyük/küçük harf ya da Türkçe karakterle farklı yazılmış adlar
  (müşteri_yaş / MUSTERI_YAS) veri setindeki yazıma çevrilir, açıklama korunur.
  Aynı kolon için birden fazla satır varsa açıklaması dolu olan kalır.
- Orijinal sözlük dataset'ine dokunulmaz; değişiklikler denetim kütüğüne
  "veri seti eşitlemesi" kaynağıyla yazılır. Sağ paneldeki sözlük kartında
  "Veri Setiyle Eşitleme" satırı kaç satırın çıkarılıp eklendiğini gösterir.

---

Önceki tur: **Eleme sonuçlarında hedef ve kimlik kolonu "elendi" sayılmıyor**.
Değiştir (fe_agent): `akis_panel.py`
Kütüphane dosyasını değiştirdikten sonra webapp backend'ini yeniden başlatın.

- Huninin başlangıcı tablonun tüm kolonlarıydı (1.042); hedef, kimlik ve
  dönem kolonları aday olmadığı için profilde listeye girmiyor ve "elendi"
  sayılıyordu. Yalnızca PERIOD süreç dışıyken "3 aday elendi" yazıyordu.
  Artık başlangıç aday kolonlar (1.040), sonuç "1.040 → 1.039, 1 aday elendi".

---

Önceki tur: **Ürün adı "Akıllı Modelleme Platformu" oldu**.
Değiştir (fe_agent): `akis_metin.py`, `llm.py`, `dokuman.py`, `docx_yaz.py`, `akis.py`
Değiştir (webapp): `index.html` (HTML)
Kütüphane dosyalarını değiştirdikten sonra webapp backend'ini yeniden başlatın.

- Üst barda, karşılama metninde, model dokümanının başlığında ve Word
  dosyasının "uygulama" bilgisinde ad "Akıllı Modelleme Platformu".
- Ekip adı her yerde "Bireysel Krediler Analitik ve Tahsis BI" (sohbet
  asistanının kendini tanıttığı metinde "BI" eksikti).
- Dataiku'daki webapp adı ("AMP - Analitik Modelleme Platformu") Dataiku'nun
  kendi ayarı; webapp'in Settings / Summary kısmından elle değiştirilmeli.

---

Önceki tur: **SFA yeniden tasarlandı: eleme yok, her değişken için yapay zekâ kararı, çift eksenli grafik**.
Yeni (fe_agent): `sfa_karar.py`
Değiştir (fe_agent): `sfa.py`, `aralik.py`, `llm.py`, `akis_faz02.py`, `akis_faz01.py`, `akis_kayit.py`, `akis_metin.py`, `akis.py`, `akis_panel.py`, `dokuman.py`
Değiştir (webapp): `backend.py`, `app.js` (JS), `style.css` (CSS)
Kütüphane dosyalarını değiştirdikten sonra webapp backend'ini yeniden başlatın.
Devam eden bir çalışmada 02.1 Veri Profili'ne Geri Dön ile dönüp yeniden onaylayın
(adım sırası değişti; SFA yeniden hesaplanır).

- SFA eleme yapmıyor: PASS/FAIL kalktı. IV bilgi amaçlı (etkisiz / zayıf / orta
  / güçlü). Eleme sonuçlarında SFA yalnızca kararlar onaylanınca "modele
  girecek" sayısıyla görünür.
- 02.3 Aralık Önerileri adımı kalktı; aralıklar SFA'nın içinde
  ("Ayrıklaştırma: Önerilen Aralıklar").
- Yapay zekâ her değişken için ayrı karar veriyor (arka planda, 8'erli
  parçalar, 3 paralel): Kullan, Eksik Doldurma, Aykırı Değer (Winsor %5),
  Dönüşüm (Log / Üstel / Sıra), Ayrıklaştırma, gerekçe. Beklerken kural
  tabanlı karar geçerli; kararlar geldikçe listeye düşer.
- Sağ panel (hafif genişledi) Değişken Analizi: değişken listesi (IV, C-value,
  karar, kaynağı). Değişken adına tıklayınca sözlük açıklaması, ölçütler,
  beş dönüşümlü C-value, çift eksenli grafik (çubuk = popülasyon payı, nokta
  = hedef 1 oranı, doğrusal ve log eğilim; Ham / Kırpılmış %5 / Önerilen
  Aralıklar) ve karar formu. Kaydedilen karar "Sizin Kararınız" olur ve
  yapay zekâ onu değiştirmez.
- Sohbette SFA kartı: yapay zekâ ilerlemesi ve "Kararları Onayla".
- Analitik Baz Set kararları uygular: doldurma, kırpma, dönüşüm, aralık;
  yeni hâl yeni adla (ör. GELIR_KIRP_LOG, SKOR_ARALIK), ham kolon çıkar.
- Aralık hesabı düzeltildi: değerleri tek noktada yığılan değişkenlerde
  yüzdelik sınırlar çakışıp 2-3 aralık kalıyordu ("IV güvenilmez" 576).
  Artık yığın kendi aralığını alıyor, kalan değerler eşit bölünüyor.

---

Önceki tur: **Geri Dön ile 01.4 ve öncesine dönülünce bölme kilitli kalmıyor**.
Değiştir (fe_agent): `akis_panel.py`
Kütüphane dosyasını değiştirdikten sonra webapp backend'ini yeniden başlatın.

- SFA çalıştıktan sonra 01.4'e (ya da daha önceki bir adıma dönüp yeniden
  01.4'e) gelindiğinde bölme kartı "Bölme Kilitli" açılıyor ve "Bu Ayarları
  Seç" pasif kalıyordu; akış ancak "Yine de değiştir" düğmesine iki kez
  basılınca ilerliyordu. Artık akış bölme adımında ya da gerisindeyken kilit
  yok: ayar değiştirilebilir ya da aynı ayarla devam edilebilir; Veri
  Profili, SFA ve aralık önerileri kendiliğinden yeniden hesaplanır.
- Kilit yalnızca akış bölmeyi geçmişken, sağdaki Bölme & Validasyon
  sekmesinden bölme değiştirilmek istenirse sorulur (değişmedi).

---

Önceki tur: **Tek Değişken Analizi açıklamalı; aralık detayında öncesi / sonrası grafiği, IV ve C-value, sözlük açıklaması**.
Değiştir (fe_agent): `akis_faz02.py`, `aralik.py`, `sfa.py`, `akis_panel.py`, `akis_sohbet.py`
Değiştir (webapp): `backend.py`, `app.js` (JS), `style.css` (CSS)
Kütüphane dosyalarını değiştirdikten sonra webapp backend'ini yeniden başlatın.

- SFA sonuç mesajı 01 düzeninde: ne yapıldığı (Train satır sayısıyla), her
  satırın ne anlama geldiği, IV ve C-value'nun nasıl okunacağı, eksiklerin
  nasıl doldurulduğu ve FAIL'in çıkarma kararı olmadığı yazıyor.
- Sağ panel SFA kartı: Ölçüm Seti, Geçen / Kalan, IV Güvenilmez, Aralık
  Önerisi, Hassas Değişken satırları ve açıklama notu eklendi; "Tam Tablo"
  artık gerçek yolu gösteriyor.
- Hedefe Göre Aralık Önerileri: değişken adına tıklayınca sözlük açıklaması,
  öneri, IV / C-value tablosu (SFA · önerilen önce · önerilen sonra) ve
  batma oranının doldurmadan önce / sonra grafiği açılıyor. Listeye C-value
  kolonu eklendi; "Eksik Değer" düğmeleri kalktı (grafik ikisini birlikte
  gösteriyor).
- C-value aralık sayımlarından kesin hesaplanıyor (eşit oranlı aralıklar
  yarım sayılır).
- Hata düzeltmesi: art arda biten adımların metinleri yanlış bloğa
  düşüyordu (bölme metni "Aralık Önerileri" bloğunda görünüyordu). Artık her
  adımın metni kendi bloğunda.

---

Önceki tur: **Faz 02 onaysız başlıyor**.
Değiştir (fe_agent): `akis_faz02.py`

- Bölme kaydedilince Veri Profili, SFA ve aralık önerileri kendiliğinden art
  arda çalışır; ilk durak aralık önerileri kartıdır. "Başlayalım mı?" onayı kalktı.
- "Geri Dön" ile Profil, SFA ya da Stabilite adımına dönülürse yeniden
  hesaplamadan önce onay sorulur (eski sonuçlar silineceği için).

---

Önceki tur: **yapay zekâ değerlendirmesi arka planda ve yalnızca karar gerektiren önerilerde; Faz 02 mesajları Faz 01 düzeninde**.
Değiştir (fe_agent): `akis_faz02.py`, `akis_faz01.py`, `akis_kayit.py`, `akis_sohbet.py`, `llm.py`
Değiştir (webapp): `backend.py`, `app.js` (JS)
Kütüphane dosyalarını değiştirdikten sonra webapp backend'ini yeniden başlatın.

- "Yapay Zekâ Değerlendirsin" beklemede kalıyordu: 519 önerinin hepsi sırayla
  ve tek istekte dil modeline gidiyordu; ayrıca seçim mesajı yanlışlıkla soru
  sanılıp bir kez daha dil modeline gönderiliyordu. Şimdi:
  - karta yalnızca aralıklarla IV'si 0,05'i geçen ya da hassas olan öneriler
    ve eksik değer işaretleri girer (diğerleri sağ paneldeki tabloda),
  - değerlendirme arka planda, 3 paralel parçayla çalışır; kart hemen açılır,
    kararlar geldikçe satırlara düşer, bitince düğme açılır,
  - seçim mesajı artık soru sanılmıyor.
- Faz 02'de tek onay faz başında (Veri Profili); SFA ve Stabilite onay
  beklemeden çalışır. Profil, SFA, Stabilite ve Analitik Baz Set mesajları
  "Etiket : Değer" düzeninde; ASCII tablolar ve "%%50" hatası kalktı.

---

Önceki tur: **Aralık Önerileri adımı (yapay zekâ sorusu, satır satır kabul / ret, baz sette yeni kolon); "Karşılama yüklenemedi" hatası**.
Değiştir (fe_agent): `aralik.py`, `akis_faz02.py`, `akis_kayit.py`, `akis_metin.py`, `akis_panel.py`, `llm.py`
Değiştir (webapp): `backend.py`, `app.js` (JS), `style.css` (CSS)
Önceki turdan eksik kaldıysa: webapp `index.html` (HTML sekmesi) ve fe_agent `akis.py`.
Kütüphane dosyalarını değiştirdikten sonra webapp backend'ini yeniden başlatın.

- "Karşılama yüklenemedi": backend yeni panel fonksiyonlarını kütüphanede
  bulamayınca bütün karşılama çöküyordu. Artık yalnızca ilgili panel hata yazar.
- Faz 02'ye SFA'dan sonra "Aralık Önerileri" adımı eklendi. Önce
  "Yapay Zekâ Değerlendirsin / Kural Tabanlı Kalsın" sorulur. Yapay zekâ
  aralık tablolarını ve metrik kontrollerini görür (ham veri yok), her öneri
  için uygula / uygulama ve gerekçe yazar.
- Karar kartı sözlük tanımları kartı gibi: satır başına Uygula kutusu,
  Tümünü Seç / Temizle. Metrik kontrolleri (en az %5, eğilim, IV ≥ 0,02,
  komşu aralık farkı, diğer setlerde sıra, hassas) kodla hesaplanır.
- Kabul edilenler "Planlanan Dönüşümler" kartında görünür ve Analitik Baz
  Set adımında `<KOLON>_ARALIK` / `<KOLON>_EKSIK` kolonları olarak üretilir;
  hassas değişkende ham kolon çıkarılır.
- Analitik Baz Set veri seti Flow'da yoksa webapp kurar.
- SFA veri seti pandas sınırının üstündeyse açık mesajla durur (Spark
  sürümü henüz yok).
- Faz 02'ye adım eklendiği için Faz 02 ve sonrasındaki mevcut çalışmalarda
  adım numaraları bir kayar.

---

Önceki tur: **SFA'ya hedefe göre aralık (binleme) önerileri**.
Yeni ekle (fe_agent): `aralik.py`
Değiştir (fe_agent): `akis_faz02.py`, `akis_panel.py`, `akis_kayit.py`
Değiştir (webapp): `backend.py`, `app.js` (JS), `style.css` (CSS)

- SFA adımı her değişken için batma oranına göre aralık önerir: artan,
  azalan, U ya da ters U (U ancak IV'yi en az %10 artırıyorsa). Her aralıkta
  eğitim satırlarının en az %5'i; oranı anlamlı farklı olmayan komşu
  aralıklar birleşir (en fazla 8). Kategoriklerde oranı benzer kategoriler
  gruplanır. IV 0,02'nin altında kalan değişkene öneri verilmez.
- Aralıklar yalnızca eğitim setinden öğrenilir; validasyon / test setinde
  sıralamanın korunup korunmadığı ayrıca yazılır.
- Hassas değişkenler (yaş, cinsiyet, uyruk, medeni hâl ...) adından ve
  sözlük açıklamasından bulunur, öneride ayrıca belirtilir.
- Eksik değer iki görünümde: doldurmadan önce (ayrı aralık) ve doldurduktan
  sonra (medyanın düştüğü aralıkta). Eksiklerin oranı belirgin farklıysa not düşülür.
- Değişken Analizi sekmesinde "Hedefe Göre Aralık Önerileri" tablosu;
  satıra tıklayınca aralıklar, batma oranları ve WoE açılır.
- Öneriyi kabul edip dönüşüme çevirme sonraki tur.

---

Önceki tur: **sağ panel üç sekme; "Planlanan Dönüşümler" kaldırıldı; hedef oranı sayılarla**.
Değiştir (fe_agent): `akis.py`, `akis_panel.py`, `akis_faz01.py`
Değiştir (webapp): `backend.py`, `app.js` (JS), `index.html` (HTML), `style.css` (CSS)

- Sekmeler: VERİ & SÖZLÜK · DEĞİŞKEN ANALİZİ (Dağılım, SFA, Eksik Değer
  bölümleri alt alta) · BÖLME & VALİDASYON (bölme özeti, validasyon).
  HAZIRLIK, DAĞILIM, SFA, İLİŞKİLER, VALİDASYON sekmeleri kalktı; İLİŞKİLER
  hiç hesaplanmayan bir iskeletti.
- "Planlanan Dönüşümler" kartı kaldırıldı (dolduran adım yoktu).
- Veri Seti kartında hedef iki satır: "Hedef Tipi" ve "Hedef Oranı"
  (ör. %3,21 · 12.345 / 384.567).

---

Önceki tur: **dosya boyutu ve motor sohbette değil, sağdaki Veri Seti kartında**.
Değiştir (fe_agent): `akis_faz01.py`, `akis_panel.py`

- "Baz veri seti ve baz sözlük seçildi" mesajı kaldırıldı; adım eskisi gibi
  mesaj yazmadan modelleme tanımlarına geçer. Kaynak tablo ve alt alta ekleme
  mesajlarındaki boyut / motor satırları da kaldırıldı.
- Sağ paneldeki Veri Seti kartına "Dosya Boyutu" ve "Motor" satırları eklendi.

---

Önceki tur: **boyuta göre motor (küçük veri pandas, büyük veri Spark); başlangıç kartı metinleri**.
Yeni ekle (fe_agent): `motor.py`, `amp_pandas.py`
Değiştir (fe_agent): `amp.py`, `profil.py`, `profil_kural.py`, `akis_faz01.py`, `akis_metin.py`
Webapp dosyalarında değişiklik yok.

- Motor, veri setinin Dataiku'daki dosya boyutuna ("basic:SIZE" metriği,
  tabloyu okumadan) göre seçilir. Toplam boyut 0,25 GB ve altıysa profil,
  alt alta ekleme ve AMP_VERISETI yazımı webapp içinde pandas ile yapılır;
  üstündeyse Spark recipe'leriyle. Boyut okunamazsa Spark.
- Eşik proje değişkeniyle değiştirilebilir: `amp_pandas_sinir_gb`.
- Mesajlarda "Dosya Boyutu" ve "Motor" satırı görünür.
- Başlangıç kartları dört kart olarak kalıyor; başlıklar "X Mevcut - Y Mevcut
  (Değil)" biçiminde, açıklamalar tek düzende yeniden yazıldı.

---

Önceki tur: **başlangıç kartları: açık olanlar seçilebilir, metinler "ne mevcut / ne oluşturulacak"**.
Yapıştır: fe_agent `akis_metin.py`, `akis_faz01.py` · webapp `app.js` (JS), `style.css` (CSS)

- Açık başlangıçlar: A (Baz Veri Seti ve Baz Sözlük Mevcut) ve D (Kaynak
  Tablolar Mevcut). B ve C kartta soluk, "Şu An Kapalı" etiketli ve
  tıklanamaz; yazarak seçilmeye çalışılırsa da reddedilir. Açmak için
  `akis_metin.ACIK_MODLAR` listesine eklenir.
- Kart başlığı elinizde ne mevcut olduğunu, açıklama neyin mevcut olmadığını
  ve bu adımlarla nasıl oluşturulacağını söylüyor.

---

Önceki tur: **tam veriye dokunan işler Spark'ta (kümede); Flow nesnelerini webapp kurar**.

Neden: gerçek veri ~135 milyon satır × 1.040 kolon (<VERI_SETI> ≈ 19,3 M,
_2026 ≈ 116 M). Bu hacim webapp'in makinesine indirilemez; DuckDB yolu kaldırıldı.

Kütüphaneden (fe_agent) SİLİN: `veri_kaynak.py`, `profil_duck.py`, `amp_duck.py`

Yapıştırın:
- fe_agent: `spark_is.py`, `profil_spark.py`, `amp_spark.py`, `amp.py` (dördü de
  YENİDEN geliyor), `profil.py`, `akis_faz01.py`, `akis_durum.py`, `akis_panel.py`,
  `profil_kural.py`
- webapp: `backend.py` (Python), `app.js` (JS)

Flow'a SİZ bir şey eklemiyorsunuz. İlk kullanımda webapp kendisi kurar (girdi
tablosunun bağlantısında, veri setleri Parquet):
- compute_AMP_PROFIL  → AMP_PROFIL klasörü (profil)
- compute_AMP_BAZ     → MODELLEME_BAZ veri seti + AMP_BAZ_SONUC klasörü
                        (aynı kolonlu tabloları alt alta ekler)
- compute_AMP_VERISETI→ AMP_VERISETI veri seti + AMP_SONUC klasörü
Dataiku'da bir nesne tek bir recipe'in çıktısı olabildiği için her işin kendi
sonuç klasörü var. Girdi tablolarınıza ve sözlüğünüze yazılmaz. Recipe'lerin
kodu ve girdileri her çalıştırmada webapp tarafından tazelenir.

Hız:
- Profilin ilk geçişi geniş tabloda artık tek gruplamayla (kolon başına ayrı
  sorgu yok); kolonlar 150'lik gruplar hâlinde, her grup Parquet'ten yalnızca
  kendi kolonlarını okur. Tabloyu bellekte tutma (persist) kaldırıldı.
- Tekrarlanan satır: 128 bitlik satır özetiyle sayılır (135 M satırda çakışma
  olasılığı ~1e-22).
- Yerel ölçüm 10.000 × 1.042: 150 sn → ~85 sn; sonuç pandas referansıyla aynı.
  Kümede 135 M satırda süre dakikalar mertebesindedir.

Bekleme: arayüz 5 dakikada vazgeçmiyor; iş bitene kadar (en fazla 3 saat)
20 saniyede bir sonucu yokluyor ve geçen süreyi gösteriyor. Sunucudaki iş
süresi sınırı `amp_is_sure` (varsayılan 10800 sn).

Bilinen sınır: Faz 2-5 (Dağılım, SFA, eleme, model) AMP_VERISETI'ni hâlâ
webapp'te pandas ile okuyor; 135 M satırda o adımlar da Spark'a taşınmalı.
Yapay zekâ planıyla yan yana birleştirme (kolonları farklı tablolar) da
pandas'ta; küçük tablolar içindir.

---

Önceki tur: **Kaynak Tablolar kartı sadeleşti**. Yapıştır: fe_agent `akis_faz01.py` · webapp `app.js` (JS)

- Adım metni kalın değil, iki cümle: ne seçileceği (en az iki tablo) ve
  sonra ne olacağı (aynı kolonlu tablolar alt alta, farklı olanlar için
  yapay zekâ birleştirme planı). Ayrı gri "En az iki tablo seçin…" satırı
  kaldırıldı.
- Listeye eklenmiş tablolar arama listesinde artık görünmüyor; aynı tablo iki
  kez seçilemez.

---

Önceki tur: **yeni mesajlar platformun yazı standardında**. Yapıştır (fe_agent): `akis_faz01.py`

- Kaynak tablo özeti, alt alta ekleme sonucu, Mod C veri seti özeti ve
  birleştirme hata mesajları madde işaretli düz metin yerine "  Etiket : Değer"
  satırlarıyla yazılıyor; arayüz bunları diğer adımlardaki gibi hizalı
  etiket–değer tablosu olarak çiziyor.
- Hata sebebindeki ":" karakterleri etiket ayıracıyla karışmasın diye " · "
  olarak yazılıyor ("Ana tablo bulunamadı · …").

---

Önceki tur: **seçilen tabloların satır × kolon sayısı**. Yapıştır (fe_agent): `akis_faz01.py`

- Kaynak tablo özeti her tablo için kesin satır ve kolon sayısını yazıyor:
  "• <VERI_SETI> · 1.234.567 satır × 1.040 kolon". Başlıkta toplam
  satır var; yanıltıcı olan "toplam kolon" kaldırıldı.
- Alt alta ekleme mesajı tablo adlarını tekrar saymıyor; baz veri setinin
  satır × kolon sayısını ve kayıt yerini yazıyor.

---

Önceki tur: **aynı kolonlu tablolar alt alta ekleniyor; birleştirme sonucu klasöre yazılıyor**.
Yapıştır (fe_agent): `akis_faz01.py`, `akis_sohbet.py`, `akis_durum.py`, `veri_kaynak.py` · (webapp) `backend.py`

- Seçilen tabloların hepsi aynı kolonlara sahipse (ör. <VERI_SETI> ve
  _2026) yapay zekâya sorulmaz: DuckDB ile alt alta eklenir, onay beklenmez.
  Kolon sırası farklı olabilir; adla eşlenir.
- Birleştirme sonucu (alt alta ya da yapay zekâ planıyla yan yana) Flow'daki
  MODELLEME_BAZ veri setine değil, `PROJE_HAFIZASI/<çalışma>/MODELLEME_BAZ.parquet`
  dosyasına yazılır; sonraki adımlar bu dosyayı okur.
- Yapay zekâ planı çıkaramaz ya da plan doğrulamayı geçemezse "Onayla ve
  Uygula" gösterilmez; hata yazılır ve tablo seçim kartı önceki seçimle açılır.

---

Önceki tur: **seçimden sonra ikinci onay yok; Kaynak Tablolar kartı düzenlendi**.
Yapıştır: fe_agent `akis_faz01.py`, `akis_kayit.py` · webapp `app.js` (JS), `style.css` (CSS)

- Kaynak Tablolar (Mod B/D): "Tabloları Onayla"dan sonra "Planı çıkarayım
  mı?" sorulmuyor; seçim özeti yazılıp birleştirme planı doğrudan çıkarılıyor.
- Baz Veri Seti (Mod C): seçimden sonra "Devam edilsin mi?" sorulmuyor.
- Seçim özeti tek biçimde: "2 tablo seçildi · toplam 2.080 kolon" ve altında
  "• TABLO · 1.040 kolon" maddeleri.
- Liste kartı: seçilen tablolar arama kutusunun ÜSTÜNDE birikiyor; "+"
  düğmesi giriş kutusuyla aynı yükseklikte ve hizada.

---

Önceki tur: **mod değişikliğinde onay sorusu kaldırıldı**. Yapıştır (fe_agent): `akis_faz01.py`

- Başlangıç Seçimi'nde başka bir mod kartı seçilince "Evet, Sıfırla /
  Hayır, Vazgeç" sorusu sorulmuyor; seçilen mod doğrudan uygulanıyor,
  önceki modun verisi (veri seti, sözlük, analizler) sıfırlanıyor.

---

Önceki tur: **TEK MOTOR: DuckDB, webapp içinde. Spark, recipe, Flow kurulumu yok.**

Kütüphaneden (fe_agent) SİLİN: `profil_spark.py`, `amp_spark.py`, `spark_is.py`,
`spark_oturum.py`, `amp.py`, `tani.py`

Yapıştırın (fe_agent): `veri_kaynak.py` (YENİ), `profil_duck.py` (YENİ),
`amp_duck.py` (YENİ), `profil.py`, `akis_faz01.py`, `akis_durum.py`,
`akis_panel.py`, `profil_kural.py`
Yapıştırın (webapp): `backend.py` (Python sekmesi)

Code env'de olması gerekenler: `duckdb`, `pyarrow` (webapp'in code env'inde
yoksa ekleyin; notebook ortamınızda ikisi de vardı).

Flow'da hiçbir şey kurulmaz: AMP_DUMMY, compute_AMP_PROFIL, AMP_PROFIL,
compute_AMP_VERISETI, AMP_SONUC artık kullanılmıyor; silebilirsiniz. Proje
değişkenleri `amp_motor`, `amp_spark_oturum`, `amp_profil_*`, `amp_veri_*`,
`amp_is_sure` okunmuyor.

Nasıl çalışıyor:
- Veri seti seçilince tablo Dataiku'dan parça parça (200.000 satır) webapp'in
  yerel diskine Parquet olarak akıtılır (`veri_kaynak`). Girdi tablonuza
  yazılmaz. Dataiku'daki dosyalar değişmedikçe yeniden indirilmez.
- Profil (`profil_duck`) ve AMP_VERISETI + bölme (`amp_duck`) DuckDB ile
  hesaplanır. Sayımlar kesin, örneklem yok. Kolonlar 150'lik gruplar
  hâlinde işlenir; genişlik (30.000 kolon) bellek sorunu değildir.
- AMP_VERISETI her zaman `PROJE_HAFIZASI/<çalışma>/AMP_VERISETI.parquet`;
  `_SPLIT` kolonu orada. Sonraki fazlar bu dosyayı okur.
- Yerel ölçüm: 10.000 × 1.042 profil 6,6 sn (Spark 150 sn, pandas 18,8 sn);
  pandas referansıyla 0 fark. Zamansal / kimlik / satır / hazır bölme
  sonuçları önceki motorla aynı.
- Sınır: tek makine. Satır sayısında tavan webapp sunucusunun belleği ve
  diski; DuckDB belleğe sığmayan ara sonuçları diske taşar.

---

Önceki tur: **geri çevrilen adımda uyarılar üst üste birikmiyor**. Yapıştır (webapp): `app.js`

- Aynı adım birkaç kez geri çevrilince (ör. "AMP_VERISETI Flow'da tanımlı
  değil") her denemede uyarı bir satır daha ekleniyordu. Artık yalnızca
  son denemenin uyarısı görünüyor.

---

Önceki tur: **Spark oturumu webapp açılınca başlıyor** ve **rastgele bölmede test seti Test (OOS2)**.

Yapıştır:
- fe_agent: `spark_oturum.py` (YENİ), `spark_is.py`, `profil.py`, `amp.py`,
  `akis_durum.py`, `akis_faz01.py`, `dokuman.py`
- webapp: `backend.py` (Python sekmesi), `app.js` (JS sekmesi)

Bir kez yapılacak kurulum:
1. Bu projede, Spark'ı okuyabildiğiniz **PySpark notebook**'unda yeni bir
   hücreye yazıp çalıştırın:
   ```
   from fe_agent import spark_oturum
   spark_oturum.ayarlari_kaydet()
   ```
   Notebook'un Spark ayarlarını proje değişkenine (local >
   `amp_spark_oturum`) yazar. Gizli değer taşıyan ayarlar (token, secret,
   password, credential, access.key) yazılmaz; adları ekrana basılır.
2. Webapp'in backend'ini yeniden başlatın.
3. Kontrol: veri setini seçip adımı onaylayın. Jobs ekranında yeni bir
   `Build_AMP_PROFIL…` işi AÇILMIYORSA profil webapp'teki oturumda
   çıkarılmıştır.

Nasıl çalışıyor:
- Webapp açılırken Spark oturumu arkada açılır (sayfa beklemez) ve açık
  kalır. Profil ve AMP_VERISETI yazımı bu oturumda yapılır: yürütücü açılışı
  ve Dataiku işi beklenmez.
- Hesap değişmedi: aynı `profil_spark` / `amp_spark` fonksiyonları.
- Oturum açılamazsa ya da veri seti oradan okunamazsa iş eskisi gibi
  recipe ile yapılır. Recipe'ler (compute_AMP_PROFIL, compute_AMP_VERISETI)
  bu yüzden Flow'da kalmalı.
- Kaynak: oturum açık kaldıkça yürütücüler (sizde 2 × 32 GB) webapp'te
  tutulur. Kapatmak için proje değişkeni `amp_spark_webapp` = `hayir`.

Test (OOS2):
- Rastgele bölmede OOT yoktur: veri tek dönemmiş gibi ele alınır, test seti
  de validasyon gibi aynı dönemden ayrılır. Bu yüzden ekranda, uyarılarda,
  set seçicide ve dokümanda adı **Test (OOS2)**. Zamansal bölmede
  **Test (OOT)** olarak kalır.

---

Önceki tur: **adım hata verince Değişken Listesi iki kez basılıyordu, düzeltildi**. Yapıştır (webapp): `app.js`

- Değişken Kontrolü onayında bir hata dönünce (ör. "AMP_VERISETI Flow'da
  tanımlı değil") eski kart kilitli hâliyle kalıyor, düzeltilebilir yeni
  kart altına ekleniyordu. Artık eski kart, rozeti ve Excel düğmesi
  kaldırılıyor; hata mesajının altında tek, açık kart duruyor.

---

Önceki tur: **Spark işleri yürütücüde Python istemiyor**. Yapıştır (fe_agent): `profil_spark.py`, `amp_spark.py`

- Sebep: kurumdaki Spark yürütücüleri code env'siz imajla açılıyor ("the
  image for the executors wasn't built for the code env" uyarısı); yürütücüde
  Python/pandas yok. Profil işi değer bazlı kontrolleri yürütücüde Python'la
  yapıyordu, iş orada düşüyordu.
- Artık yürütücüde yalnızca Spark'ın kendi işlemleri çalışıyor (sizin
  notebook'unuzdaki gibi):
  - Tekil değeri 200 binin altındaki kolonlar: tekil değerler sürücüye
    alınıp aynı kurallarla denetleniyor. Sonuç birebir aynı.
  - Daha çok tekil değerli kolonlar: aynı kurallar Spark ifadeleriyle.
    Hata mesajındaki örnek değer sayısı 1. Serbest biçimli tarih tanıma
    (dönem adaylığı) yaygın kalıplarla sınırlı.
  - AMP_VERISETI recipe'inde eşlemeler Spark haritasıyla yapılıyor.
- Saat dilimsiz zaman damgası (TimestampNTZ) kolonları artık tarih olarak
  tanınıyor (eskiden metin sayılıyordu).

---

Önceki tur: **Spark işi başarısız olunca asıl hata gösteriliyor**. Yapıştır (fe_agent): `spark_is.py`

- Eskiden işin genel günlüğünün son satırları ("JOB IS COMPLETE" vb.)
  gösteriliyordu. Artık başarısız recipe'in kendi günlüğünden Python
  hatası (traceback) gösteriliyor.

---

Önceki tur: **mod seçilince bütün fazların "Tamamlandı" basılması düzeltildi**. Yapıştır: `app.js`

- Yanıttaki faz listesi artık bloklar çizilmeden önce güncelleniyor.
  Eskiden A seçilince yeni blok numarasız kalıyor ve beş fazın hepsi
  "Tamamlandı" yazılıyordu.

---

Önceki tur: **Parquet + AMP_VERISETI Spark'ta + bölme tabloda + panel düzeltmeleri**.
Yapıştır (fe_agent): yeni `tablo_io.py`, `spark_is.py`, `amp.py`, `amp_spark.py`;
değişen `profil.py`, `akis_durum.py`, `akis_faz01.py`, `akis_faz02.py`,
`akis_faz04.py`, `akis_faz05.py`, `akis_panel.py`, `sozluk_calisma.py`,
`kutuk.py`, `bakim.py`

Dataiku'da bir kez yapılacak kurulum (profil recipe'ine ek olarak):
1. Yeni **PySpark recipe**:
   - Girdi: baz veri setiniz. Webapp her çalıştırmada girdiyi seçilen
     veri setine çevirir.
   - Çıktı 1: yeni veri seti **AMP_VERISETI**. Bağlantı S3, Settings >
     Format: **Parquet**.
   - Çıktı 2: yeni managed folder **AMP_SONUC**.
   - Recipe adı `compute_AMP_VERISETI` olmalı (Dataiku varsayılan olarak
     bu adı verir). Farklıysa proje değişkeni `amp_veri_recete`'ye yazın.
   - Kodun tamamı:
     ```
     from fe_agent import amp_spark
     amp_spark.recete_calistir()
     ```
2. Webapp'in code env'inde **pyarrow** olmalı (klasöre yazılan tablolar
   Parquet). Yoksa dosyalar geçici olarak CSV'ye düşer.

Ne değişti:
- Platformun klasöre yazdığı her tablo Parquet: sözlük çalışma kopyası,
  değişiklik kütüğü, yedekler. Eski çalışmaların CSV'leri okunmaya devam
  eder.
- AMP_VERISETI'ni artık Spark recipe'i yazıyor (Değişken Kontrolü
  onayında):
  - Tip dönüşümleri uygulanıyor, süreç dışı kolonlar düşürülüyor.
  - Dönüşüm eski yolla birebir aynı sonucu veriyor.
  - Dolu olup çevrilemeyen tek hücre bile varsa iş durur.
  - CSV yedeği yok: AMP_VERISETI Flow'da yoksa adım bunu söyleyip durur.
- Bölme: AMP_VERISETI yeniden yazılıyor ve bölme `_SPLIT` kolonu olarak
  tabloya ekleniyor (hazır, zamansal, kimlik bazlı ve satır bazlı).
  Sonraki adımlar setleri bu kolondan okuyor. Set sayıları ve hedef
  oranları Spark'tan geliyor.
- Veri Seti kartı:
  - Satır × Kolon ve Sayısal / Kategorik / Tarih, Değişken Kontrolü'nden
    sonra kalan kolonlara ve son tiplere göre.
  - Toplam Null Oranı veri seti seçilince doluyor.
  - Hedef Oranı satırı kaldırıldı (Hedef Tipi ve Dağılımı'nda zaten var).
  - Dönem Aralığı: tek değerli dönem için nedenini yazıyor.
  - Kayıt Yeri: Flow'da veri seti yoksa bunu açıkça söylüyor.
- Sözlük kartı: yalnızca süreçte kalan kolonları sayıyor
  ("1.041 · 1 süreç dışı"). Alttaki tabloya dokunulmadı.

Hâlâ pandas ile tam tabloyu okuyanlar (sonraki adımlar): B/D birleştirmesi,
2-5. fazlar (veri profili, SFA, stabilite, seçim, model) ve Dağılım sekmesi.

---

Önceki tur: **sağ panel sekme sırası**. Yapıştır: `index.html`

- Üst satır: VERİ & SÖZLÜK · HAZIRLIK · DAĞILIM. Alt satır: SFA ·
  İLİŞKİLER · VALİDASYON.

---

Önceki tur: **adım numaraları (01.1, 01.2 …) ve faz bitti ayracı**. Yapıştır: `app.js`, `style.css`, `backend.py` (webapp Python)

- İş akışında, sohbet blok başlıklarında, Arşiv'de ve "kaldığı yerden
  yüklendi" mesajında adımlar faz numarasıyla: 01.1 Başlangıç Seçimi,
  01.2 Veri ve Model Tanımları, 01.3 Değişken Kontrolü, 01.4 Örneklem ve
  Doğrulama Tasarımı. Gruplu bloğun içindeki adımlar 01.2.1, 01.2.2, 01.2.3.
  Diğer fazlar da aynı düzende (02.1 …).
- Bir faz bitince sohbette ince bir çizgi ve ortasında kırmızı
  "01 Çalışma Kurulumu Tamamlandı" yazısı çıkıyor. O faza geri dönülürse
  ayraç kalkıyor, faz yeniden bitince tekrar basılıyor.

---

Önceki tur: **iki eski hata düzeltildi**. Yapıştır (fe_agent): `tip_donusum.py`, `birlestirme.py`, `profil_kural.py`

- "15.01.2024" gibi tarihlere artık "Sayısal – ondalık virgül" önerilmiyor.
  Binlik ayırıcı taşıyan değer ancak üçerli gruplanmışsa (1.234 / 1.234.567,50)
  sayı sayılıyor. Bu kolonlar için öneri "Tarih – GG.AA.YYYY" oluyor.
- "045" gibi kodlar artık dönem adayı olmuyor. Metnin tarih sayılması için
  4 haneli bir yıl (1900-2999) ve bir ayırıcı ya da harf taşıması gerekiyor
  ("2024-01-15", "15.01.2024", "Jan 2024" tarih; "045", "12" değil).

---

Önceki tur: **başka projedeki veri setinin profili**. Yapıştır (fe_agent): `profil.py`, `profil_spark.py`

- Başka projeden seçilen veri seti ("PROJE.VERI") için profil kısa adla
  yazılıyor, webapp tam adla arıyordu; sonuç reddedilecekti. Düzeltildi.
- Böyle bir veri seti recipe girdisi olabilmek için bu projeye
  paylaşılmış olmalı (Exposed objects); değilse adım bunu söylüyor.

---

Önceki tur: **PySpark geçişi 1. adım: veri seti profili Spark'ta**. Yapıştır (fe_agent): `profil.py` (yeni), `profil_kural.py` (yeni), `profil_spark.py` (yeni), `akis_faz01.py`, `akis_durum.py`, `sozluk.py`, `tip_donusum.py`

Ne değişti:
- Veri seti seçimi onaylanınca webapp tabloyu artık okumuyor. Dataiku'daki
  PySpark recipe'i tam tablodan tek bir profil çıkarıyor. Sonraki kontrollerin
  hepsi bu profilden okunuyor: tek değerli kolonlar, hedef / kimlik / dönem
  adayları, tip önerileri ve dönüşüm uygunluğu, kişisel veri, null oranı,
  tekrarlanan satır, hazır bölme, dil modeline giden özetler.
- Sayımların hepsi kesin: tekil değerler groupBy ile çıkıyor; yaklaşık sayım
  ya da örneklem yok.
- Spark ve yerel motor aynı test tablosunda birebir aynı profili üretiyor.
  Kararlar eski pandas yoluyla aynı.

Dataiku'da bir kez yapılacak kurulum:
1. Flow'da yeni bir managed folder oluşturun, adı **AMP_PROFIL** (S3 olabilir).
2. **PySpark recipe** oluşturun:
   - Girdi: herhangi bir veri seti (ör. baz veri setiniz; webapp her
     çalıştırmada girdiyi seçilen veri setine çevirir).
   - Çıktı: AMP_PROFIL klasörü. Recipe adı `compute_AMP_PROFIL` olmalı
     (Dataiku varsayılan olarak bu adı verir). Farklıysa proje
     değişkenine `amp_profil_recete` olarak yazın.
   - Kodun tamamı şu iki satır:
     ```
     from fe_agent import profil_spark
     profil_spark.recete_calistir()
     ```
   - Code env: webapp ile aynı (pandas ve numpy yürütücülerde de gerekli).
3. Webapp backend'ini çalıştıran kullanıcının bu projede recipe düzenleme,
   proje değişkeni yazma ve iş (job) başlatma yetkisi olmalı.
4. İsteğe bağlı proje değişkenleri: `amp_profil_klasor` (varsayılan
   AMP_PROFIL), `amp_profil_sure` (en fazla bekleme, sn; varsayılan 7200).

Bilinmesi gerekenler:
- Aynı anda tek profil işi çalışır. Başka bir çalışma o an profil çıkarıyorsa
  adım bunu söyler.
- Metin kolonlarında boş metin ("") artık boş hücre sayılıyor; iki motorda
  aynı tanım.
- Bu adımda hâlâ pandas ile tam tabloyu okuyanlar (sonraki adımlar):
  B/D birleştirmesi, sözlük teyidinde AMP_VERISETI yazımı, bölme, 2-5.
  fazlar ve Dağılım sekmesi.

---

Önceki tur: **"i" açıklamaları kaydırılabiliyor**. Yapıştır: `app.js`, `style.css`

- Uzun açıklama balonun içinde kayıyor (en fazla ekranın %60'ı yükseklik);
  tekerlek balondayken sayfa kaymıyor.
- Fare simgeden balona geçerken balon kapanmıyor (kısa gecikme).
  Tıklanarak açılan balon, başka yere tıklanana kadar açık kalıyor.

---

Önceki tur: **"İşleniyor" yerine "İşlem Devam Ediyor"**. Yapıştır: `app.js`

- Aktif bloğun altındaki satır artık "İşlem Devam Ediyor · 0:12 · İptal".

---

Önceki tur: **Örneklem ve Doğrulama Tasarımı onayı sonraki adıma geçiyor**. Yapıştır: `akis_durum.py`, `akis_faz01.py`

- Sebep: kimlik kolonu yokken bölme `_SPLIT` etiketini AMP_VERISETI veri
  setine yazmak zorundaydı. AMP_VERISETI akışta dataset olarak yoksa
  (klasördeki CSV'ye düşmüşse) adım hata verip kartı yeniden açıyordu.
- Artık o durumda etiketler çalışmanın klasörüne kaydediliyor:
  `PROJE_HAFIZASI/vN/AMP_BOLME.csv`. Girdi tablosuna yine dokunulmuyor.
  AMP_VERISETI dataset olarak varsa `_SPLIT` eskisi gibi oraya yazılıyor.
- Bölmeden sonra tablonun satır sayısı değişirse setler tahmin edilmiyor;
  bölme adımının yeniden çalıştırılması isteniyor.

---

Önceki tur: **onay düğmeleri ve işlem satırı ortada**. Yapıştır: `style.css`

- "İşleniyor · 0:12 · İptal" satırı da ortalı. Bölme kartında
  Önerilene Dön + Bu Ayarları Seç birlikte ortada (denetlendi).

- Kartların ana düğmeleri (Girdileri Doğrula, Tanımları Onayla, Seçimleri
  Uygula ve Devam Et, Kaydet ve Devam Et, Bu Ayarları Seç) ve blok onay
  düğmeleri yatayda ortalı.

---

Önceki tur: **ayrı yükleniyor kartı yok; işlem satırı bloğun içinde**. Yapıştır: `app.js`, `style.css`

- İstek sürerken aktif adımın bloğunun en altında tek satır:
  "İşleniyor · 0:12 · İptal". İlk 2,5 sn görünmez. Durum başlıktaki
  "● Kontrol Ediliyor" etiketinde. Bütün adımlarda aynı.

---

Önceki tur: **Yeni Çalışma onayı tamamen kaldırıldı**. Yapıştır: `app.js`, `index.html`, `style.css`

- "Yeni Çalışma"ya basınca doğrudan yeni çalışma açılır; açık çalışma
  silinmez, Arşiv'den geri açılır. Onay kutusu, süre ve soru kaldırıldı.

---

Önceki tur: **girdi tablosuna _SPLIT yazılmıyor; süreli Yeni Çalışma onayı**. Yapıştır: `akis_faz01.py`, `app.js`

- HATA DÜZELTİLDİ: kimlik kullanılamayan bölmede _SPLIT kolonu kullanıcının
  girdi veri setine yazılıyordu. Artık yalnızca platform kopyasına
  (AMP_VERISETI); kopya yoksa adım nedenini söyleyip durur. Daha önce
  yazılmış _SPLIT kolonu girdi tablosunda duruyor, elle kaldırılmalı.
- Yeni Çalışma onayı 10 saniye bekler ("Onayla (9)" ...), sonra kendiliğinden
  kapanır.

---

Önceki tur: **"Tamamlandı" yerine açıklamalı onay**. Yapıştır: `app.js`

- Geçilmiş blokların yeşil etiketi neyin yapıldığını söylüyor: "✓ A
  Başlangıcı Seçildi", "✓ Modelleme Tanımları Onaylandı", "✓ Bölme
  Uygulandı" ... (app.js BLOK_TAMAM_METNI).

---

Önceki tur: **başlık ve etiketlerde Başlık Büyük Harfi**. Yapıştır: `akis_faz01.py`, `akis_durum.py`, `akis_panel.py`, `app.js`

- Form alanları, kart başlıkları, bölme satırları, sağ panel etiketleri,
  dağılım kutuları: her kelime büyük harfle (ve, veya, ile, için, mi, da,
  de küçük). Açıklama cümleleri değişmedi.

---

Önceki tur: **durum etiketleri açık zemin + koyu yazı**. Yapıştır: `style.css`

- "● Yanıtınız Bekleniyor": açık kırmızı zemin, koyu kırmızı yazı.
- "● Kontrol Ediliyor": açık sarı zemin, koyu sarı yazı.

---

Önceki tur (1): **başlangıç başlıkları baz/kaynak adlarıyla; sarı eski tonunda**. Yapıştır: `akis_metin.py`, `style.css`

- A Baz Veri Seti ve Baz Sözlük Hazır · B Baz Veri Seti Hazır Değil, Kaynak
  Sözlükler Hazır · C Baz Veri Seti Hazır, Baz Sözlük Hazır Değil · D Baz
  Veri Seti ve Baz Sözlük Hazır Değil.
- "Kontrol Ediliyor": açık sarı (#F5C518) üstüne beyaz.

---

Önceki tur: **Analitik Süreç hep açık; baz / kaynak adları**. Yapıştır: `akis_metin.py`, `akis_faz01.py`, `akis_kayit.py`, `akis_panel.py`, `app.js`, `index.html`

- ANALİTİK SÜREÇ açılıp kapatılamaz (başlık düğme değil).
- Terimler: baz veri seti (modellemeye girecek tek tablo), baz sözlük (onun
  açıklamaları), kaynak tablolar, kaynak sözlükler. Formlar, adım adları,
  başlangıç açıklamaları, özet kartı ve yer tutucular bu adlarla; alanların
  altında ne istendiği tek satırda.

---

Önceki tur: **DAĞILIM sekmesi bağlandı; "Kontrol Ediliyor" yeniden sarı**. Yapıştır: `backend.py`, `app.js`, `style.css`

- Yeni uç /dagilim (tam veri): kolon listesi; seçilen kolon + set için
  satır / boş oranı / farklı değer, sayısalda histogram (%1-%99 aralığı,
  dışarıda kalan sayısı yazılır), yüzdelikler, IQR dışı oran, %1-%99
  budama önerisi; kategorikte en sık 15 değer + diğer.
- Set seçici (Tümü / Train / Validasyon / Test) bölme uygulandıktan sonra
  gerçek setleri kullanır; öncesinde Tümü ve not.
- "● Kontrol Ediliyor" etiketi yeniden sarı.

---

Önceki tur: **dönem notu ayrıntısı "i" simgesinde; toplu düğmeler sağda**. Yapıştır: `app.js`, `style.css`

- "Dönem kolonu bulunamadı." yanında i simgesi; kolon kolon nedenler
  üzerine gelince açılır, doğrudan gösterilmez.
- Tümünü Seç / Tümünü Temizle ve Görünenleri Süreç Dışı Bırak / Sürece Al
  satır dar gelip alta kaysa da sağa yaslı.

---

Önceki tur: **"Kontrol Ediliyor" etiketi siyah**. Yapıştır: `style.css`

---

Önceki tur: **tek değer notu sadeleşti**. Yapıştır: `akis_faz01.py`

- Not: "PERIOD tüm veri setinde tek bir değer taşıdığı için modele bilgi
  katmaz; süreç dışı bırakıldı ve kilitlendi." Boş hücre örneği kaldırıldı.

---

Önceki tur: **örneklem tamamen kaldırıldı**. Yapıştır: `akis_durum.py`, `akis_faz01.py`, `sozluk.py`, `secim.py`, `llm.py`, `tip_donusum.py`

- Kolon özeti örnek değeri ve kişisel veri denetimi: tam kolon.
- Dönem adayları: tam tablo (5.000 satır sınırı kalktı).
- Tip önerisi: örnekle ön eleme kalktı, yalnız tam kolon.
- Faz 05: MI ve model önemi (SHAP dahil) tam veriyle; korelasyon elemesi
  TÜM adaylarla (ilk 800 sınırı kalktı).
- Dil modeline giden sözlük listesi kesilmiyor (400 satır sınırı kalktı).
- Hız için sonucu değiştirmeyen kesin ön elemeler ve matris korelasyonu.
- Kalan satır sınırlı okumalar yalnız KOLON ADI için (şema); kalan "ilk N"
  kullanımları ekranda / istemde gösterilen örnek ve listelerdir.

---

Önceki tur: **süreç dışı AMP'den düşüyor, tip seçenekleri tam kolonla, sarı = her değişiklik**. Yapıştır: `akis_faz01.py`, `tip_donusum.py`, `app.js`

- AMP_VERISETI süreç dışı kolonlar olmadan yazılır (hedef/kimlik/dönem
  hariç). 1. faz adımları kullanıcının kendi tablosunu okur (kaynak=True);
  geri dönüp kolon sürece alınırsa teyit kaydıyla AMP yeniden yazılır.
- Tip seçenekleri TAM KOLONLA hesaplanır; uygulanamayan seçenek listede
  hiç görünmez, hiç seçenek yoksa hücrede "-" yazar. Sonuç önbellekte.
- Sarı satır: öneri ya da orijinal değerden farklı her değişiklik.

---

Önceki tur: **tek değer metinleri; kalite kapısında boş hücre kuralı**. Yapıştır: `akis_faz01.py`, `akis_faz04.py`, `sfa.py`

- Kural genel: bir değer + boş hücre (A ve boş, 1 ve boş ...) iki değerdir.
  Metinlerdeki "1 ve boş" örneği kaldırıldı.
- Faz 04 kalite kapısı üretilen değişkeni "bir değer + boş" diye tek
  değerli sayıp eliyordu; artık aynı kurala uyuyor.

---

Önceki tur: **Değişken Kontrolü'nde görünenleri toplu süreç dışı bırakma**. Yapıştır: `app.js`, `style.css`

- Tablonun üstünde "Görünenleri Süreç Dışı Bırak (N)" ve "Görünenleri
  Sürece Al (N)". Arama ve null eşiğiyle süzülen, kilitsiz satırlara
  uygulanır; tek istekle gider.

---

Önceki tur: **"kaldığı yerden yüklendi" satırında da faz içi adım**. Yapıştır: `backend.py`, `app.js`

- Sayfa açılışındaki satır da "01 Çalışma Kurulumu · Adım 3/4 - Değişken
  Kontrolü" biçiminde.

---

Önceki tur: **Arşiv satırında faz içi adım**. Yapıştır: `backend.py`, `app.js`

- Arşiv satırı: "01 Çalışma Kurulumu · Adım 3/4 · Değişken Kontrolü".
  Sayım sol paneldeki gibi faz içinde, gruplu adımlar tek. Veri seti adı
  satırdan kaldırıldı.

---

Önceki tur: **süreç dışı satırlar çizili ve kilitli**. Yapıştır: `app.js`, `style.css`

- Değişken Kontrolü'nde süreç dışı satırın üstü çizili, tip ve tanım
  alanları kapalı. Kilitli (tek değerli, hedef/kimlik) satırda kutu da
  kapalı; kilitsiz satırda işaret kaldırılınca satır geri açılır.

---

Önceki tur: **Tümünü Seç / Tümünü Temizle tablonun hemen üstünde**. Yapıştır: `app.js`, `style.css`

- Sözlük Tanımları kartında toplu düğmeler başlık satırından alındı,
  tablonun hemen üstüne (renk açıklamasıyla aynı satır, sağda) taşındı.

---

Önceki tur: **sohbet arka plan bulanıklığı kapatıldı**. Yapıştır: `style.css`

- --sohbet-bulanik 13px -> 0px. Kaydırmada kare düşüşünün kaynağıydı;
  görsel ve üstündeki yarı saydam örtü duruyor.

---

Önceki tur: **kontrol sırasında çerçeve kırmızı kalıyor**. Yapıştır: `app.js`, `style.css`

- Sarı yalnızca "● Kontrol Ediliyor" etiketinde; blok çerçeveleri kontrol
  sırasında da kırmızı (önceki turdaki sarı çerçeve geri alındı).

---

Önceki tur: **sarı "Kontrol Ediliyor", tüm veri seti tip önerisi, tek değerli kilidi, tablo hizası**. Yapıştır: `akis_faz01.py`, `backend.py`, `app.js`, `style.css` (ve önceki turdan `tip_donusum.py`)

- Yanıt gönderilince blok SARI "● Kontrol Ediliyor" olur; kartın rozeti o
  sırada boş. "Yanıtınız Bekleniyor" yalnızca gerçekten yanıt beklenirken.
- Tip önerisi tüm veri setinde (akis_faz01._tip_onerisi): YYYYAA / YYYYAAGG
  -> tarih (yazım korunur); sayı taşıyan metin -> sayısal; tarih taşıyan
  metin -> tarih; adı kod/tip/segment olan az değerli tam sayı -> kategorik.
  Başında sıfır olan kodlar dönüştürülmez. Öneri nedeni ipucunda.
- Tek değerli kolonlar TÜM VERİ SETİ üzerinden hesaplanır ve KİLİTLİ süreç
  dışıdır: Değişken Kontrolü'nde işaret kaldırılamaz, Sözlük Tanımları'nda
  sözlüğe eklenemez, /haric_kolonlar ucu da geri ekler.
- Değişken Kontrolü tablosunda başlık/değer hizaları eşitlendi.

---

Önceki tur: **sözlük tanımları geri dönüş, dönem tipi önerisi, öneri renkleri**. Yapıştır: `tip_donusum.py`, `akis_faz01.py`, `app.js`, `style.css`

- Sözlük Tanımları geri dönünce ORİJİNAL tanımsız kolonların hepsi, önceki
  karar (ekle + yazılan açıklama / hariç) ile geri gelir. Kartın "Girdiler
  Doğrulandı" rozeti kaldırıldı.
- Yeni tip dönüşümleri: donem_ym6 / donem_ymd8. Tip "tarih" olur, değer
  AYNEN kalır (202501). Tarih - YYYYAA eskisi gibi gerçek tarihe çevirir.
- Değişken Kontrolü açılınca dönem kolonu ve adı dönem/tarih olan kolonlar
  YYYYAA ise donem_ym6 önerilir ve seçili gelir (kurala dayalı, bir kez).
- Öneri renkleri: öneriyi taşıyan satır kırmızı zeminli, kullanıcı öneriyi
  değiştirdiyse sarı. Sözlük Tanımları'nda model açıklaması, Değişken
  Kontrolü'nde tip önerisi ve modelden gelen tanım.

---

Önceki tur: **eski birlestirme.py backend'i düşürmüyor**. Yapıştır: `akis_durum.py`, `akis_faz01.py` (ve güncel `birlestirme.py`)

- akis_durum dönem yardımcılarını birlestirme.py'den alıyor; dosya eski
  kalırsa artık yedek tanımlar devreye giriyor, backend açılıyor.

---

Önceki tur: **kurum adı kaldırıldı**. Yapıştır: `llm.py`, `backend.py`, `style.css`

- Asistan yönergesindeki, stil yorumundaki ve bu nottaki kurum adı kaldırıldı.
- Görsel dosyalarının eski önekli adlarına düşen yedek liste kaldırıldı:
  LLM_WEBAPP_GORSEL klasöründeki görseller robot_llm_ust.png,
  robot_llm_chat.png, robot_llm_person.png, llm_chat_light.png,
  llm_chat_dark.png adlarında olmalı.
- Depoya girmiş __pycache__ dosyaları çıkarıldı, .gitignore eklendi.

---

Önceki tur: **tek değerliler otomatik süreç dışı; arşiv numaraları yeniden kullanılıyor**. Yapıştır: `akis_faz01.py`, `akis_durum.py`, `sfa.py`, `backend.py`, `app.js`

- Değişken Kontrolü açılınca tek değer taşıyan kolonlar süreç dışı işaretli
  gelir (bir kez; kullanıcı kaldırabilir). Boş hücre ayrı değer sayılır:
  "1 ve boş" olan kolon tek değerli değildir. Tamamen boş kolon tek değerlidir.
- SFA'daki "sabit" teşhisi de aynı kurala geçti.
- Arşiv: silinen numara kayıttan çıkar ve yeniden verilir; yeni çalışma en
  küçük boş numarayı alır (hepsi silindiyse v1). Eski sürümün "silindi"
  işaretli girdileri de boş sayılır. Silmede ortak veri seti sahiplikleri
  bırakılır.

---

Önceki tur: **dönem notu kısa + maddeli**. Yapıştır: `akis_faz01.py`, `app.js`, `style.css`

- Aday yoksa not yalnızca "Dönem kolonu bulunamadı." Altında adı dönem/tarih
  olan kolonlar ayrı maddelerde, neden seçilemedikleriyle (en fazla 5).
- Ad eşleşmesi parça parça: <KOLON> gibi sayaç/tutar kolonları listelenmez;
  TARIHI, DONEMI gibi ekli adlar listelenir.
- Alan sözleşmesi: form alanında yeni "not_maddeler" listesi.

---

Önceki tur: **girdiler kontrolden geçmeden onaylanmıyor; Analitik Süreç kapanmıyor**. Yapıştır: `app.js`, `akis_faz01.py`

- Veri seti + sözlük formu gönderilince rozet "Kontrol Ediliyor…" der.
  "✓ Girdiler Onaylandı" yalnızca sunucu kabul edince yazılır.
- Sözlük denetimi (akis_faz01._sozluk_denetle): açıklama kolonu var
  (ACIKLAMA / TANIM / DESCRIPTION), kolon adı kolonu veri setinin
  kolonlarını taşıyor (en az bir eşleşme) ve eşleşenlerden en az birinin
  açıklaması dolu. Mod B'deki kaynak sözlüklere de uygulanıyor.
- Reddedilen girdide eski kart kalkar, uyarı ve dolu yeni form gelir. Kabul
  edilince uyarı da silinir. F5 sonrası reddedilmiş eski formlar geçmişten
  çizilmez.
- Analitik Süreç artık kendiliğinden kapanmıyor. Kullanıcının aç/kapa
  seçimi tarayıcıda saklanıyor.

---

Önceki tur: **blok durum renkleri, "Girdiler Onaylandı"**. Yapıştır: `app.js`, `style.css`, `akis_faz01.py`

- Yanıt bekleyen blok (gruplu blokta o adımın bölümü) kırmızı çerçeve ve
  "● Yanıtınız Bekleniyor" etiketi taşıyor. Geçilmiş bloklar gri çerçeve,
  soluk başlık ve yeşil "✓ Tamamlandı" etiketiyle duruyor.
- Aktif adım sol paneldekiyle aynı kaynaktan (DUZ_ADIMLAR[aktifAdim]).
- Gönderilmiş kart "✓ Girdiler Onaylandı" diyor. Dolu ama gönderilmemiş kart
  "2/2 Seçildi" der ve yeşil olmaz.
- Dönem adayları: tablo okunamazsa boş liste artık kalıcı yazılmıyor, sonraki
  açılışta yeniden deneniyor. Hesap kuralı sürümlü; eski çalışmalar yeni
  kurala göre bir kez yeniden hesaplanıyor. Aday yoksa adı dönem çağrıştıran
  kolonların neden elendiği notta yazıyor.

---

Önceki tur: **dönem kolonu: sayı, metin, kategori**. Yapıştır: `birlestirme.py`, `akis_durum.py`, `akis_faz01.py`

- 202501 sayı, ondalık (202501.0), metin (" 202501 ") ya da kategori olarak
  tutulsa da dönem adayı. Metin kolonda "NULL", boş, "nan" hücreler boş
  sayılıyor; eskiden tek bir tanesi kolonu listeden düşürüyordu.
- Yeni tanınan yazımlar: 2025M01, 2025/01, 01/2025.
- Aday olmak için dolu hücrelerin en az %95'i dönem olarak çözülmeli.
- Bölme dönemleri tek biçime indiriyor (birlestirme.donem_degeri): bu
  yazımların hepsi aynı "202501" metni.
- DÜZELTİLEN HATA: dönem kolonunda boş hücre varsa "nan" metni en son dönem
  sayılıyor ve dönemi boş satırlar test setine gidiyordu. Artık boş dönemli
  satır teste gitmiyor.
- Dönemler zaman sırasına diziliyor (2025M2 < 2025M10, 12/2025 < 01/2026).

---

Önceki tur: **Arşiv adı, sade panel tutamakları**. Yapıştır: `app.js`, `index.html`, `style.css`

- "Çalışmalarım" düğmesinin adı **Arşiv**.
- Üst çubuktaki panel genişliği sıfırlama düğmesi kaldırıldı. Bir paneli
  ilk genişliğine döndürmek için kenarına çift tıklanır.
- Panel kenarı sürüklenirken ya da üzerine gelinince çıkan "... px
  (varsayılan)" etiketi kaldırıldı.
- index.html eski kalsa bile app.js düğmeyi söküyor ve adı Arşiv yazıyor.

---

Önceki tur: **Çalışmalarım'da Aç ve Sil**. Yapıştır: `app.js`, `backend.py`, `style.css`

- Her satırın sağında "Kopyala" yerine **Aç** ve **Sil** var. Açık
  çalışmada Aç "Açık" yazar ve pasiftir.
- Sil'e basınca aynı yerde "Silinsin mi?" + Onayla / Reddet çıkar.
  Onayla, çalışmanın klasöründeki her dosyayı siler (`/vN/...`). Dataiku
  dataset'lerine dokunulmaz (projede ortak).
- Numara `CALISMALAR.json`'da "silindi" işaretiyle kalır: aynı numara
  bir daha verilmez, eski sekmede kalan kimlik açılmaz.
- Açık çalışma silinirse en son çalışmaya, hiç yoksa yeni boş çalışmaya
  geçilir.
- Kopyalama ekrandan kalktı; `/calisma_kopyala` ucu backend'de duruyor.

---

Önceki tur: **dönem kolonu listesi filtreli**. Yapıştır: `akis_faz01.py`

- Modelleme Tanımları'ndaki dönem listesine yalnızca tarih tipi ya da dönem
  biçimli (202401, 20240115, "2024-01-15") kolonlar geliyor; tek değerli,
  kimlik (her satırda farklı) ve 0/1 hedef kolonları gelmiyor. Kural
  zamansal bölmenin dönem çözücüsüyle aynı (`birlestirme._donem_coz`).
- Aday yoksa liste boş kalır ve "tarih ya da dönem biçimli kolon
  bulunamadı; zamansal bölme kurulamaz" notu yazar.
- Serbest yazılan uygunsuz dönem de reddediliyor (hedef/kimlik gibi).
- Adaylar veri seti seçilirken çıkarılıyor; eski çalışmada profilde yoksa
  form ilk açılışta tablodan bir kez hesaplıyor (tüm kolonlara düşmez).

---

Bu tur: **Öneri gerekçesi ve Detaylar ve Terimler düğmeleri kalktı**.
Yapıştır: `akis_durum.py` (fe_agent); `style.css` → `app.js` (webapp)

- Gerekçe: "Önerilen ayarlar" rozetinin yanındaki «i»de ("Neden bu ayarlar
  önerildi").
- Terimler: kartın giriş cümlesinin sonundaki «i»de, soru-cevap listesi.
- Öneri gerekçesindeki gruplama cümlesi yalnızca gruplama gerçekten
  yapılıyorsa yazılıyor (bolme_ayarlari ile aynı kural).

---

Bu tur: **bölme birimi kalktı (otomatik)**, **seed listesi**, **tooltip sabit**.
Yapıştır: `akis_durum.py` → `akis_panel.py` → `akis_faz01.py` (fe_agent);
`style.css` → `app.js` (webapp)

- «Bölme birimi» ve «Bölme kolonu» satırları kalktı. Kural otomatik: kimlik
  kolonu var VE aynı kimliğin birden fazla satırı olabiliyorsa (dönem kolonu
  var ya da kimlik bazlı tekrar ölçüldü) kayıtlar rastgele bölmede ve CV
  parçalarında bir arada tutulur; özet satırı "Aynı <KIMLIK_KOLONU>: bir arada
  tutulur" diye yazar. Aksi halde kimlik = satır, gruplama yok.
- Seed satırı her modda görünür. Çoklu tekrarda yeni «Kullanılacak seed'ler»
  alanı: boşsa ana seed'den türetilir (42 → 42, 43, 44), elle yazılırsa
  (42, 7, 2024) tekrar sayısı listeden gelir. Arka uç `seedler` alanını
  kaydediyor; CV turları bu listeyi kullanıyor.
- «i» açıklaması sabit konumlu (sayfayı oynatmıyor); alta sığmazsa yukarı
  açılır. Bölme yaklaşımı / çoklu tekrar açıklamaları genişletildi.

---

Bu tur: **Örneklem ve Doğrulama Tasarımı kartı yeniden tasarlandı**.
Yapıştır: `akis_durum.py` → `akis_panel.py` → `akis_faz01.py` (fe_agent);
`style.css` → `app.js` (webapp)

- Set adları: **Train (MS) · Validasyon (OOS) · Test (OOT)** — kart, sağ
  panel set seçici, uyarılar ve sözlük dahil her yerde.
- İki sütun (Önerilen / Özel) yerine **tek liste**: önerilen değer seçili
  ve yeşil noktalı gelir; tıklayınca değişir. Sapan satır kehribar, yanında
  "önerilene dön"; üstte "Önerilenden N fark" rozeti ve "Önerilene Dön".
- **"Veri nasıl bölünecek" çubuğu**: üç setin payı (rastgele) ya da dönem
  sırası (zamansal), her tıklamada güncellenir; altında tek satır özet.
- Her satırda **i simgesi**: fareyle açılan, hiç bilmeyen için yazılmış
  açıklama (`akis_durum.BOLME_SATIR_BILGI`). "Detaylar ve Terimler" de
  aynı özende yeniden yazıldı (CV nedir, kat ne yapar…).
- Kısıtlar tek kutuda; kullanılamayan seçenek üstü çizili.
- Arka uç sözleşmesi (`/bolme_kaydet`) değişmedi.

---

Bu tur: **"refresh ekranı boşalttı" düzeltmesi**. Yapıştır (webapp): `app.js`

- Sebep: yeni app.js, eski index.html'de olmayan Onayla/Reddet düğmelerini
  arıyordu; hata atılınca açılışta çalışmayı yükleyen kod hiç çalışmıyordu.
- app.js düğmeler yoksa kendisi kuruyor.
- Yüklemede bir hata olursa ekran artık boş kalmıyor: sohbet alanında
  hatayı ve "dosyaların aynı sürümden yapıştırıldığını kontrol edin"
  uyarısını gösteriyor.

---

Bu tur: **adım metinleri kutusuz**, **Kaynak Tablolar adımı yeniden yazıldı**.
Yapıştır: `akis_faz01.py` → `akis_kayit.py` (fe_agent), `style.css` (webapp)

- Blok içindeki asistan metni (hoş geldiniz, kaynak tablo açıklaması…)
  artık ayrı kutu/çubukla çizilmiyor; düz yazı. Sebep bir CSS öncelik
  hatasıydı. Hata mesajları kutulu kalıyor.
- «Ham Tablolar» → «Kaynak Tablolar». "Hangi tabloları birleştirelim?"
  yerine ne istendiğini ve ardından ne olacağını anlatan paragraf.

---

Bu tur: **Yeni Çalışma onayı aynı yerde**: düğme gizlenir, yerinde solda
Onayla, sağda Reddet. Yapıştır (webapp): `index.html` → `style.css` → `app.js`

---

Bu tur: **Yeni Çalışma onayı düğmenin üzerinde**, sohbette değil.
Yapıştır (webapp): `index.html` → `style.css` → `app.js`

- «Yeni Çalışma»ya basınca düğmenin altında küçük kutu: "Yeni çalışma
  başlatılsın mı? Açık çalışma (v2) silinmez…" [Başlat] [Vazgeç]. Dışarı
  tıklamak ya da Esc kapatır. Açık çalışma boşsa sorulmaz.
- Sohbetteki onay bloğu kaldırıldı.
- «Kopyasıyla Başla» artık Çalışmalarım listesinde her satırın yanında
  («Kopyala»).

---

Bu tur: **açılış sorusu kaldırıldı**, **Yeni Çalışma onayı kart düzeninde**.
Yapıştır (webapp): `app.js`

- Sayfa açılınca soru yok: kayıtlı ya da en son çalışma doğrudan açılır;
  başka çalışmaya «Çalışmalarım» düğmesinden geçilir.
- «Yeni Çalışma» onayı: tek soru cümlesi + açık çalışmanın kartı (numara,
  tarih, adım, kararlar) + üç seçenek kartı.

---

Bu tur: **soru yalnızca yeni açılışta**, **Yeni Çalışma onaylı**.
Yapıştır (webapp): `app.js`

- Aynı sekmede sayfa yenilenince (F5) soru gelmez, açık çalışma doğrudan
  yüklenir. Yeni sekme/pencere yeniden sorar.
- «Yeni Çalışma» düğmesi onay istiyor. Soru açık çalışmanın altına eklenir,
  ekran silinmez: Evet, Yeni Çalışma Başlat / Hayır, Bu Çalışmaya Devam Et /
  Önceki Bir Çalışmayı Aç. Açık çalışma hiç başlamamışsa sorulmaz.

---

Bu tur: **açılışta önce "önceki çalışmanız var, dönmek ister misiniz?"**.
Yapıştır (webapp): `app.js` (önceki turun `backend.py` ve `style.css`'i gerekli)

- Sayfa açılınca başlamış bir çalışma varsa ilk ekran bu soru: en son
  çalışmanın numarası, adımı ve veri seti yazıyor.
  - **Evet** → çalışmalar kararlarıyla listelenir (Devam Et / Kopyasıyla Başla).
  - **Hayır** → yeni çalışma, A/B/C/D.
- Hiç çalışma yoksa soru sorulmaz. Soru ekranında sohbet kutusu kilitli,
  iş akışı başlangıç hâlinde.
- A/B/C/D altındaki liste kaldırıldı (soru onun yerini aldı).

---

Bu tur: **başlangıç ekranında önceki çalışmalar**.
Yapıştır (webapp): `backend.py` → `style.css` → `app.js`

- A/B/C/D kartlarının altında «ÖNCEKİ ÇALIŞMALAR»: her çalışma numarası,
  son işlem zamanı, kaldığı adım ve verilen kararlarla (başlangıç, kaynak
  tablolar, veri seti, sözlük, hedef/kimlik/dönem, süreç dışı sayısı).
- **Devam Et**: çalışma kaldığı yerden açılır; her adımın bloğu ve
  Geri Dön'ü yerinde, düzeltip devam edilir.
- **Kopyasıyla Başla**: aynı kararlar, sohbet geçmişi ve klasördeki
  dosyalarla yeni bir v-numarası açılır; orijinale dokunulmaz. Açık
  çalışma boşsa onun numarası kullanılır.

---

Bu tur: **çalışmalar v1, v2, v3 …** ve **MODELLEME_BAZ adı sabit**.
Yapıştır: `akis_durum.py` → `akis_faz01.py` → `akis_kayit.py` → `akis_faz05.py`
→ `bakim.py` · Webapp: `backend.py`

```
PROJE_HAFIZASI/
  CALISMALAR.json            ← hangi v kimin
  VERI_SETI_SAHIPLERI.json   ← ortak veri setine son kim yazdı
  v3/
    calisma.json             ← çalışmanın kaydı
    sozluk_calisma.csv
    MODELLEME_BAZ.csv        ← (B/D) birleştirme sonucunun kopyası
    AMP_VERISETI.csv / AMP_SOZLUK.csv (akışta veri seti yoksa)
```

- Numara proje genelinde tekil; kullanıcı adı dosya adında yok. Başka
  kullanıcının çalışması açılamaz (CALISMALAR.json'daki sahip kontrolü).
- MODELLEME_BAZ / MODELLEME_SOZLUK adları sabit, sorulmuyor (önceki turdaki
  ad formu kaldırıldı).
- Eski kayıtlar (oturum_*.json) "Çalışmalarım"da "Eski Kayıt" olarak açılır.

---

Bu tur: **birleştirme sonucunun adı soruluyor ve çalışma klasörüne de yazılıyor**.
Yapıştır: `akis_durum.py` → `akis_faz01.py` → `akis_kayit.py` → `akis_faz05.py`

- B ve D'de «Birleştirme Planı» adımı önce "Birleştirme sonucuna ne ad
  verelim?" diye soruyor (varsayılan: son verilen ad ya da MODELLEME_BAZ).
- Tablo iki yere yazılıyor: `PROJE_HAFIZASI/cmergen_03/<AD>.csv` (çalışmanın
  kalıcı kopyası) ve akıştaki `<AD>` veri seti.
- Ortak veri setlerinin son sahibi `VERI_SETI_SAHIPLERI.json`'da
  (AMP_VERISETI_SAHIBI.txt'nin yerini aldı). Başka çalışma aynı veri setinin
  üzerine yazdıysa çalışma kendi klasöründeki kopyayı okur.
- Akışta o adla veri seti yoksa tablo yine klasöre kaydedilir, hata
  mesajı ya veri setini oluşturmayı ya da Geri Dön ile başka ad vermeyi söyler.

---

Bu tur: **sade kayıt yeri** ve **ortak AMP_VERISETI hatası**.
Yapıştır: `akis_durum.py` → `akis_faz01.py`

- Bir çalışmanın her dosyası tek klasörde:
  `PROJE_HAFIZASI/cmergen_03/AMP_VERISETI.csv`, `AMP_SOZLUK.csv`,
  `sozluk_calisma.csv`. AMP klasörü, tarih damgası ve SON.txt yok.
  Eski çalışmalar eski yerlerine yazmaya devam eder.
- AMP_VERISETI veri seti tüm çalışmaların ortak veri seti; en son kimin
  yazdığı `AMP_VERISETI_SAHIBI.txt`'de tutuluyor. Başka çalışma üzerine
  yazdıysa sonraki fazlar kullanıcının kendi tablosunu (tip dönüşümleri
  uygulanmış) okur — eskiden Çalışma 01'e dönen, 03'ün tablosunu okuyordu.

---

Bu tur: **dört başlangıç (A/B/C/D)** ve **rozetler Başlık Büyük Harfi**.

## Kopyala-yapıştır sırası (bu tur)
**Library Editor (`python/fe_agent/`):** `akis_metin.py` → `akis_durum.py`
→ `akis_faz01.py` → `akis_kayit.py` → `akis_panel.py` → `akis_faz05.py`
**Webapp:** `backend.py` → `app.js`

## 1. Dört başlangıç
| Harf | Başlangıç | Adımlar |
|---|---|---|
| A | Veri Seti ve Sözlük Hazır | kurulum → tanımlar → sözlük tanımları |
| **B (yeni)** | Veri Seti Hazır Değil, Sözlük Hazır | ham tablolar → **kaynak sözlükleri** → birleştirme (+ nihai sözlük otomatik) → tanımlar → sözlük tanımları |
| C (eski B) | Veri Seti Hazır, Sözlük Hazır Değil | veri seti → sözlük üretimi → tanımlar |
| D (eski C) | Veri Seti ve Sözlük Hazır Değil | ham tablolar → birleştirme → sözlük üretimi → tanımlar |

Eski kayıtlar okunurken B→C, C→D çevriliyor (`akis_durum.MOD_GOCU`);
yarım kalmış çalışmalar bozulmuyor. Kod artık `mod == "C"` gibi tek
harfe değil `BIRLESTIREN_MODLAR` / `SOZLUK_URETEN_MODLAR` gruplarına bakıyor.

**B nasıl çalışıyor:** Nihai veri seti yok ama kaynak tablolar ve her
birinin sözlüğü hazır. «Kaynak Sözlükleri» adımında her tabloya sözlüğü
seçilir (aynı sözlük birden çok tabloya seçilebilir). Birleştirme bitince
nihai sözlük (MODELLEME_SOZLUK) köken kütüğünden otomatik kurulur:
kaynak kolon tanımını aynen alır; toplama kolonu "Kart işlem tutarı (TL)
— toplam, son 3 ay (<VERI_SETI>.TUTAR)" gibi türetilir; kayıt sayısı
kolonları "<VERI_SETI> tablosundaki kayıt sayısı, son 6 ay" olur. Kaynağında
tanımı olmayan kolonlar «Sözlük Tanımları» adımında listelenir.

## 2. Rozetler
"✓ Girdiler hazır" → "✓ Girdiler Hazır", "0/2 seçildi" → "0/2 Seçildi",
"Değiştir Seçildi", "Geri Dönüldü"; karar sonrası rozet metni de
("2 Kolon Sözlüğe Eklendi") aynı biçime çevriliyor.

## 3. Küçük düzeltme
Birleştirme yapılmadan veri kartında «Köken: Kaynak Tablolardan
Oluşturuldu» yazıyordu; artık satır boş kalıyor.

---

Bu tur: **sağ panel adım adları sol panelle aynı**, **"ve ve ve" cümlesi
düzeldi**, **ANALİTİK SÜREÇ açılır kapanır**, **çalışma adları sade** ve
**"Yeni Çalışma" artık hiçbir şeyi silmiyor — "Çalışmalarım" listesinden
eski çalışmaya dönülüyor**.

> **Deploy sonrası "Yeni Çalışma"ya basmana gerek yok.** Eski çalışman
> "Çalışmalarım" listesinde "Eski Kayıt" olarak duruyor.

## Kopyala-yapıştır sırası

**Library Editor (`python/fe_agent/`):** `akis_panel.py` → `akis_faz01.py`
**Webapp:** `backend.py` → `index.html` → `style.css` → `app.js`

## 1. Sağ panel sol panelde olmayan adım adı söylüyordu
`akis_panel.py`'de dört sabit ad kalmıştı («Veri Seti», «Veri ve Sözlük»,
«Modelleme Tanımları»). Artık ad adım anahtarından, sol panelin kuralıyla
üretiliyor (`sol_panel_adi`): gruplu adım → «Veri ve Model Tanımları».
Mod C'de veri satırları «Birleştirme Planı»nı gösteriyor. «Kayıt Yeri»
satırı AMP tabloları gerçekten yazıldığı adımı («Değişken Kontrolü»)
gösteriyor. `app.js`'teki «Veri Profili» de «Veri Profili ve Kalite» oldu.

## 2. "«A» ve «B» ve «C» ve «D»" → "«A», «B», «C» ve «D»"
Not artık akış sırasıyla dizili (Mod C'de sıra karışıyordu).

## 3. ANALİTİK SÜREÇ açılır kapanır
Başlangıç seçimi ekranında açık; seçim yapılınca kendiliğinden kapanır ve
İŞ AKIŞI yukarı çıkar. Başlığa basınca açılır/kapanır; elle seçim o çalışma
boyunca korunur.

## 4. Çalışma adları
| | Eski | Yeni |
|---|---|---|
| Durum dosyası | `oturum_u3f9a2c41d07be58a_ck2m9x1qz.json` | `oturum_cmergen_03.json` |
| Sözlük kopyası | `u3f9a2c41d07be58a_ck2m9x1qz/` | `cmergen_03/` |
| AMP klasörü | `AMP/2026-09-21_1809_u3f9…_ck2m…/` | `AMP/cmergen_03/` |

`cmergen` = Dataiku login'i; `03` = kullanıcının kaçıncı çalışması (sunucu
veriyor). Login'de nokta/@ gibi karakter varsa 4 haneli özet eklenir
(`can.mergen` → `can-mergen-4f1a`) ki iki kullanıcı aynı ada düşmesin.
Eski dosyalar yeniden adlandırılmadı, olduğu gibi okunuyor.

## 5. Yeni Çalışma silmiyor + Çalışmalarım
- **Yeni Çalışma** yeni bir numara açar; eski çalışma ve sözlük kopyası
  yerinde kalır. Hiç başlanmamış bir çalışmadayken basılırsa aynı numara
  kullanılır (liste boş çalışmalarla dolmasın).
- **Çalışmalarım** (Yeni Çalışma'nın solunda): son işlem zamanı, adım ve
  veri setiyle liste. Birine basınca o çalışma kaldığı yerden açılır.
- Tarayıcıda kayıtlı kimlik yoksa (depolama engelli / temizlenmiş) en son
  çalışılan çalışma açılır — eskiden boş bir "ana" çalışmasına düşülüyordu.

---

## Önceki tur

Bu tur: **Bölme Stratejisi .txt'deki hiyerarşiye getirildi** — koşullu
görünürlük, "?" ipuçları, "Detaylar ve Terimler", tek terim dili,
gap + çoklu tekrar. Ayrıca her adım bloğuna ince marka kırmızısı çerçeve.

> **Deploy sonrası "Yeni Çalışma"ya bas.**

---

## Kopyala-yapıştır sırası

**Library Editor (`python/fe_agent/`):**
`akis_durum.py` → `akis_panel.py` → `akis_faz01.py`
**Webapp:** `style.css` → `app.js`

---

## 1. Adım bloklarına 3px marka kırmızısı çerçeve

`.adim-blok` artık **3px**, markanın **kendi** kırmızısıyla çerçeveli
(`--blok-cerceve: 3px` + `solid var(--kirmizi)`). İş akışının her adımı
nerede başlayıp nerede bittiği belli.

Renk için ara değişken KULLANILMIYOR ve sebebi önemli: `:root` üzerinde
`--kirmizi-cerceve: var(--kirmizi)` yazınca değer **tanımlandığı yerde**
çözülüyor, koyu temanın `#kabuk.koyu` içindeki yeni `--kirmizi`'sini
görmüyor — çerçeve iki temada da açık temanın kırmızısında kalıyordu.
Kural artık doğrudan `var(--kirmizi)` okuyor; açık temada `#D51115`,
koyu temada `#FF4D4F`. İkisini de ölçtüm.

## 2. Koşullu görünürlük — "20 inputlu form" yok

Karşılığı olmayan satır **hiç çizilmiyor** (pasif değil, yok):

| Seçim | Görünen | Kalkan |
|---|---|---|
| Zamansal | Dönem Kolonu, OOT/Test Dönemi, Dönemler Arası Boşluk | OOT/Test Büyüklüğü |
| Rastgele | OOT/Test Büyüklüğü | dönem satırları |
| Doğrulama = Kullanma | — | Doğrulama Büyüklüğü |
| Çapraz Doğrulama = Yok | — | Kat Sayısı |
| Bölme Birimi = Satır | — | Bölme Kolonu |
| Tekrarlanabilirlik = Sabit | Seed | Tekrar Sayısı |
| Tekrarlanabilirlik = Çoklu | Tekrar Sayısı | Seed |

Koşul taslaktan hesaplanıyor: kutuya basıldığı anda satır açılıp
kapanıyor, sunucuya gidip gelmeden.

## 3. Açıklama iki katmanda

- **Satır yanında "?"** → en fazla iki satır, "bu ne işe yarıyor"
- **En altta "Detaylar ve Terimler"** (varsayılan kapalı) → üç bölüm:
  Veri Setleri / Bölme Yöntemleri / Değerlendirme

Ana ekrandaki uzun cümleler kalktı. Kullanıcı üç şey görüyor: ne
seçiyorum → sistem ne öneriyor → ben ne seçtim.

## 4. Tek terim dili

Uydurma karşılıklar ("sınav", "deneme seti", "dönüşümlü deneme") tamamen
kalktı. Ekranda sektör adları var ve her biri sözlükte tanımlı:
**Eğitim Seti · Doğrulama Seti · OOT / Test Seti · Çapraz Doğrulama ·
Kat Sayısı · Tekrar Sayısı · Seed**.

Ayrı bir "Test" + "OOT" kavramı yok — tek ad: **OOT / Test Seti**.
Testi buna göre değiştirdim: eskiden yabancı terim yasağı vardı, şimdi
kural daha sert — ekranda geçen her terim sözlükte tanımlı olmalı.

## 5. İki yeni yetenek

**Dönemler Arası Boşluk (gap).** Zamansal bölmede eğitim ile OOT/Test
arasında modele **hiç dahil edilmeyen** dönem sayısı. Performans
penceresi yüzünden son eğitim dönemi ile ilk test dönemi aynı gözlemi
paylaşabiliyordu. Atlanan satırlar hiçbir sete girmiyor; aşırı boşluk
eğitimi boşaltamıyor (en az bir dönem kalacak şekilde kırpılıyor).

**Çoklu tekrar.** "Tekrarlanabilirlik" artık Sabit bölme / Çoklu tekrar.
Çoklu seçilince Tekrar Sayısı satırı geliyor ve çapraz doğrulama farklı
seed'lerle o kadar kez tekrarlanıyor (3 tekrar × 3 kat = 9 kat). Her
turun seed'i ana seed'den türetiliyor, çalışma yine tekrar üretilebilir.
CV kapalıyken çoklu tekrar seçilirse uyarı çıkıyor.

## 6. Onay kutuları seçim listesi oldu

"Doğrulama Seti" → Kullan / Kullanma, "Hedef Dağılımı" → Korunsun /
Korunmasın. Tek başına bir kare "işaretli ne demek" sorusunu
doğuruyordu.

## 7. Yol üstünde çıkan iki hata

- **`Number(k.en_az) || 2`** — boşluk alanının alt sınırı 0 ve JS'te 0
  yanlış sayılıyor; sınır sessizce 2'ye çıkıyor, "boşluk yok"
  denemiyordu.
- **`bfSecimAlani` değeri arka uçtan okuyordu** — "Kullan" seçip başka
  bir alanı değiştirince doğrulama seti sessizce eski değerine dönüyordu.
  Artık taslaktan okuyor.

---

## Önceki turlardan devam eden notlar


> Zipte yalnız Dataiku'ya yapıştıracağın dosyalar var.

## Kopyala-yapıştır sırası

**Library Editor (`python/fe_agent/`):**
`akis_faz01.py` → `akis_kayit.py` → `akis_sohbet.py` → `akis.py` → `akis_durum.py`
**Webapp:** `style.css` → `app.js`

---

## 1. "Veri seti ve sözlük bağlandı" paragrafı kalktı

Doğrulama kartının hemen altında beliren o paragraf, kartta verdiğin
kararın tekrarıydı. Artık sonuç **kartın rozetine** yazılıyor: karar
verilince rozet `✓ Girdiler doğrulandı` yerine `✓ 2 kolon sözlüğe eklendi`
oluyor. Bilgi kaybolmadı, yeri değişti.

Aynı şekilde sonraki adımın sorusu ("Devam etmek için hedef değişken ve
kimlik kolonu bilgisine ihtiyacım var…") da kalktı — o cümleyi zaten
**Modelleme tanımları kartının açıklaması** söylüyordu; kullanıcı aynı şeyi
iki kez okuyordu. Yazarak girme örneği (`target … id …`) kartın içine, tek
aralıklı bir ipucu satırına taşındı ve yine **senin kendi kolonlarından**
üretiliyor.

`kurulum_uygula` artık yalnızca **istenenden farklı** bir şey olduğunda
konuşuyor: bir tanım sözlüğe yazılamadıysa ya da çalışma kopyası
kurulamadıysa. Sessiz kalırsa kullanıcı kolonun neden süreç dışında
kaldığını bilemez.

## 2. Rozet ne olduğunu söylüyor

`✓ Hazır` → **`✓ Girdiler doğrulandı`**. Tek başına "Hazır" neyin hazır
olduğunu söylemiyordu; rozet artık seçim formundaki "Girdiler hazır" ile
aynı dili konuşuyor.

## 3. Modelleme tanımlarında ikinci onay kalktı

Formu doldurup **Tanımları onayla**'ya bastıktan sonra gelen
*"Modelleme tanımları: … Doğru mu?"* özeti ve **Onayla ve Uygula** satırı
kaldırıldı. Haklıydın: o üç satır sağ paneldeki Veri seti kartında zaten
duruyor ve onayı zaten formda vermiştin.

Bunun için akış makinesine küçük bir kural eklendi: **`plan=None` olan
adımda formun kendisi onaydır.** Form gönderilince `uygula` doğrudan
çalışır. (Girdisi olmayan, planı olan adımlar — bölme, profil, SFA… —
eskisi gibi plan gösterip onay bekliyor.)

**Hesap kaybolmadı:** hedefin tipi/dağılımı, event rate, dönem listesi ve
kimlik tekrarı artık `tanimlar_uygula` içinde hesaplanıyor. Bölme adımı
bunlara dayanıyor ve testte doğrulanıyor.

**Sessiz geçilmesi pahalıya patlayacak şeyler yazılmaya devam ediyor:**
hedef binary değilse, pozitif oran %1'in altında/%99'un üstündeyse, dönem
kolonu verilmemişse ya da tek değer taşıyorsa, kimlik kolonunda tekrar
varsa — bunlar uyarı olarak çıkıyor. Geri kalan bilgi sağ panelde.

## 4. Yan bulgu: "1/3 seçildi"

Modelleme tanımları kartı hiçbir alan doldurulmamışken **"1/3 seçildi"**
yazıyordu: opsiyonel dönem kolonu boşken de "geçerli" sayıldığı için
paydaya giriyordu. Durum göstergesi artık yalnız **zorunlu** alanları
sayıyor — `0/2` → `1/2` → `✓ Girdiler hazır`. Düğmenin etkinliği yine
bütün alanların geçerliliğine bakıyor (opsiyonel alana geçersiz değer
yazılırsa form yine kilitli kalır).

---

## 5. Doğrulama

```
python  20 dosya      hepsi geçti
js       9 dosya      hepsi geçti
uçtan uca                RC=0, istisna yok
```

`test_dogrulama_bagimsiz.py` (38 iddia) ajanın testlerine bakılmadan yazıldı
ve bozulması **en pahalı** üç şeyi sınıyor:

- **Orijinal sözlük ve veri seti gerçekten değişmiyor:** kararı uyguladıktan
  sonra iki DataFrame de `equals` ile birebir karşılaştırılıyor; tanımsız
  kolonların orijinal sözlükte olmadığı ayrıca kontrol ediliyor.
- **Onaylanmadan hiçbir şey yazılmıyor:** kart kurulduğunda çalışma
  kopyasında o kolonlar yok; yalnız onaylanan kolon yazılıyor, hariç tutulan
  yazılmıyor.
- **LLM'e veri sızmıyor:** veri setine ayırt edici damgalı değerler konup
  LLM çağrısı yakalanıyor; çağrının gövdesinde bu damgaların hiçbiri yok,
  ama kolon adı var (istenen bu). LLM patlatıldığında adım yine çalışıyor ve
  her satırın `oneri_kaynak` alanı `"yok"` oluyor.
- Karar gövdesi gelmezse eski davranış: hepsi hariç, kopyaya satır eklenmiyor.
- Yasak üç cümle `fe_agent/` + `webapp/` ağacında hiç geçmiyor.
- AST: `akis_faz01.py` ve `sozluk_calisma.py` içinde dataset yazma çağrısı yok.

**Ekran gerçekten Chromium'da çizilip sürüldü** (jsdom render etmiyor). Kartı
tıklayıp gönderilen gövde okundu: `{haric: [...], ekle: [{kolon, aciklama,
kategori}]}` ve `sessiz: true`. İki hata böyle görüldü ve düzeltildi:

1. **Genel aksiyon satırı kartla birlikte çiziliyordu.** Adım plan/onay
   aşamasında olduğu için "Onayla ve Uygula / Değiştir / Geri Dön" da
   açılıyor, kartın kendi düğmelerinin yanında duruyordu — dış incelemenin
   "birbirini tekrar ediyor" dediği şeyin aynısı.
2. **Düğme etiketi gizli kalan kolonları saymıyordu.** 200 sınırı aşıldığında
   etiket "200 Kolonu Hariç Tut" yazıp 900'ünü hariç tutuyordu.

Ayrıca ön yüz ajanının bildirdiği bir sorunu da kapattım: "Seçimi Düzenle" ve
"Geri" sohbete kullanıcı balonu basıyordu. İkisi de artık sessiz gidiyor —
kullanıcı bir cümle yazmadı, düğmeye bastı.

---

## 6. Bu turda doğrulanan ekstra şeyler

`test_tmd_kapi.py` (125 iddia) diğer testlere bakılmadan yazıldı ve
**kapının bütünlüğünü** sınıyor:

- `bloker_sayisi`, `teslim_durumu`, `hazir_mi` ve `teslim_damgasi` **her
  durumda** birbirini doğruluyor — ilk hâlde, her bloker kapatıldıktan sonra
  tek tek, geri alındığında, boş durumda ve bozuk durumda
- `/dokuman_bolum` teslim özetini de döndürüyor ve tam gövdeyle **aynı**
  değerleri taşıyor (damga tek kayıtta bayatlamıyor)
- bloker geri alınınca **geri geliyor**
- 13/15/16/17 asla bloker değil ve `eksikler` listeleri dolu
- `dokuman.py`'nin metin sabitlerinde **başka bir kurumun veri seti / kolon
  adı yok** (AST taraması; modülün kendi sabitleri ayıklanıyor). Taramanın
  gerçek bir ihlali yakaladığı da ayrıca kanıtlanıyor — yoksa kontrol
  sessizce "hep geçer" hâle gelirdi
- Δ=0 düzeltmesi ve ölçüm kapsamı metni dokümanda duruyor
- `dokuman.py` / `docx_yaz.py` hiçbir dataset'e dokunmuyor
- damga `.docx`'te üç yerde: başlık sayfası, künye satırı, 20. bölüm

**Sayfa gerçekten Chromium'da çizilip bakıldı** (jsdom render etmiyor). İki
kusur böyle görüldü ve düzeltildi:

1. Künyede "Doküman durumu" **başlıksız, tek satırlık ikinci bir tablo**
   olarak sonda duruyordu. Statü tablosuna bağlı olduğu için ancak ikinci
   geçte üretilebiliyor; artık asıl künye tablosuna satır olarak ekleniyor.
   Düzenlenmiş künyede hiçbir şey yapılmıyor.
2. Damga tek bölüm kaydında bayatlıyordu. Uç tam gövdeyi zaten üretiyordu ama
   yalnız bölümü döndürüyordu; teslim özeti de eklendi. Ön yüzdeki "soluk
   damga" ara hâli kaldırıldı — gerekçesi kalmadı.

---

## 7. Sırada

- **Doküman LLM katmanı:** kullanıcı bölümleri için röportaj soruları. Şu an
  o bölümler "Tamamlanması gerekenler" listesiyle ne yazılacağını söylüyor
  ama soruyu soran yok. LLM sayı yazmayacak, yalnız hesaplananı yorumlayacak.
- **Platformun hesaplamadığı analizler:** kalibrasyon, segment performansı,
  SHAP/ablation, MD/OOS/OOT ayrı performans. Bölümler açıldı, yerleri belli;
  her biri ayrı bir adım işi.
- DAĞILIM ve İLİŞKİLER sekmeleri hâlâ iskelet.

## 8. Sende duran işler

- `akis_durum.bolme_ozeti`, `bolme["satir"]` metin gelirse `AttributeError`
  atıyor. Aynı yolu HAZIRLIK paneli de kullanıyor.
- `/tani` çıktısı: `kimlik_yolu == "backend"` ise bütün kullanıcılar tek
  oturumu paylaşıyor.
- Senaryo: `skorlar["oot"]` zamansal modda test seti skorlarını taşımalı;
  `hiperparametre_arama` / `cv_etkin` / `cv_grup_kolon` onurlandırılmazsa
  gruplama düzeltmesi geri alınmış olur; `konfig_al(is_adi, oturum_id)`.
- Model Risk eşikleri hâlâ yer tutucu.
- **Sohbete yapıştırdığın GitHub token'ı hâlâ iptal edilmedi.**
