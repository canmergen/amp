# KATIB · Akıllı Analitik ve Modelleme Platformu

Ham veriden final modele kadar model geliştirme sürecini tek ve izlenebilir bir
çalışmada yürüten Dataiku webapp'i. Bu belge platformun güncel hâlini anlatır.

## Dosyalar ve Dataiku'daki yerleri

| Dosya | Dataiku'da |
|---|---|
| `fe_agent/*.py` | Library Editor: `python/fe_agent/` |
| `webapp/index.html` | Webapp HTML sekmesi (yalnız gövde işaretlemesi; `<html>`, `<head>`, `<body>` yok) |
| `webapp/style.css` | Webapp CSS sekmesi |
| `webapp/app.js` | Webapp JS sekmesi |
| `webapp/backend.py` | Webapp Python sekmesi |

- `fe_agent/` ya da `backend.py` değişince webapp backend'i yeniden başlatılır.
- Yalnız `index.html`, `style.css` ya da `app.js` değişince sayfayı yenilemek yeter.

## Gerekli Dataiku nesneleri

**`LLM_WEBAPP_GORSEL` (managed folder):** arayüz görselleri.

| Anahtar | Dosya | Kullanıldığı yer |
|---|---|---|
| `katib_logo` | `katib_logo.png` | Sol barın tepesindeki KATIB logosu |
| `anasayfa` | `anasayfa.png` | Sol bar: ANA SAYFA |
| `model_platformu` | `model_platformu.png` | Sol bar: MODEL PLATFORMU başlığının ikonu |
| `model_akisi` | `model_akisi.png` | Sol bar: Model Akışı |
| `gosterge_paneli` | `gosterge_paneli.png` | Sol bar: Model Gösterge Paneli ve Gösterge Paneli |
| `degiskenler` | `degiskenler.png` | Sol bar: Model Değişkenleri |
| `ozet` | `ozet.png` | Sol bar: Model Özeti |
| `model_sohbeti` | `model_sohbeti.png` | Sol bar ve Ana Sayfa: Model Sohbeti |
| `katible_sohbet` | `katible_sohbet.png` | Sol bar ve Ana Sayfa: KATIB'le Sohbet |
| `gorunum` | `gorunum.png` | Sol bar: Görünüm düğmesi |
| `arsiv` | `arsiv.png` | Sol bar: Arşiv |
| `yeni_calisma` | `yeni_calisma.png` | Sol bar: Yeni Çalışma |
| `robot_alt` | `robot_alt.png` | Sol bar: Görünüm'ün üstünde robot, kitaplar ve kupa |
| `anasayfa_aciklama` | `anasayfa_aciklama.png` | Ana Sayfa: üst bölümün görseli (saydam zeminli, geniş; yazının altında tam en) |
| `karsilama` | `robot_welcome.png` | Sohbetteki ilk robot |
| `bot` | `robot_chat.png` | Normal konuşma |
| `dusunme` | `robot_think.png` | Arkada iş sürerken |
| `user` | `robot_llm_person.png` | Kullanıcı balonu |

Görsel bulunamazsa yerinde boşluk kalır, sayfa bozulmaz; sol bar ikonu
bulunamazsa yerinde çizgi ikon kalır.

**`PROJE_HAFIZASI` (managed folder):** çalışma kayıtları (Arşiv), onaylı tanım
hafızası ve veri seti sahipliği.

**Spark işleri:** tam veriye dokunan işler PySpark recipe'leriyle kümede çalışır.
Gereken Flow nesnelerini webapp kendisi kurar; Flow'a elle bir şey eklenmez.

| İş | Recipe | Çıktılar |
|---|---|---|
| Profil | `compute_AMP_PROFIL` | `AMP_PROFIL` (klasör) |
| Alt alta ekleme | `compute_AMP_BAZ` | `MODELLEME_BAZ`, `AMP_BAZ_SONUC` |
| AMP_VERISETI yazma | `compute_AMP_VERISETI` | `AMP_VERISETI`, `AMP_SONUC` |

**LLM:** Dataiku LLM Connections üzerinden. Varsayılan model `fe_agent/llm.py`
içindeki `VARSAYILAN_MODEL`.

## Proje değişkenleri (isteğe bağlı)

| Değişken | Varsayılan | Anlamı |
|---|---|---|
| `WEBAPP_DATASET_KAPSAMI` | `erisim` | `erisim`: kullanıcının okuma yetkisi olan bütün projelerin veri setleri listelenir. `proje`: yalnız bu proje (+ ek projeler). |
| `WEBAPP_EK_PROJELER` | boş | `proje` kapsamında listeye eklenecek proje anahtarları (virgülle). |
| `WEBAPP_BELIRSIZ_YETKI` | `goster` | Yetkisi okunamayan projeler: `goster` listelemeyi dener, `gizle` atlar. |
| `amp_pandas_sinir_gb` | `0.25` | Bu boyuta (GB) kadar veri pandas ile, üstü Spark ile işlenir. |
| `amp_is_sure` | `10800` | Bir Spark işinin en fazla beklenme süresi (saniye). |

## Veri kuralı

- Kullanıcının seçtiği veri setine ve sözlüğe yazılmaz.
- Seçim yapıldıktan sonra platform yalnız kendi kopyalarıyla çalışır:
  `AMP_VERISETI` ve `AMP_SOZLUK`. Adımlar ilerledikçe bu kopyalar güncellenir.
- Profil ve sayımlar tam veri üzerinden yapılır.

## Ekran

**Yazı tipi:** iki aile.
- **Josefin Sans** (1920'lerin geometrik yazı tipi): platformdaki bütün
  başlıklar ve sol bar seçimleri. Ana Sayfa başlıkları; Model Akışı'nda
  blok ve alt adım adları, iş akışı fazları, seçim ve seçenek kartı
  başlıkları, tablo başlıkları; Model Gösterge Paneli, Model
  Değişkenleri ve Model Özeti'nde bölüm, kart ve tablo başlıkları;
  kilitli sayfaların adı; sol bardaki sayfa satırları, Model Platformu
  başlığı ve alt sayfaları, Çalışma Alanları ayracı, Görünüm, Arşiv,
  Yeni Çalışma. Gömülü kopyada Z ve z harflerinin üst çizgisindeki
  kıvrık kanca kaldırılmıştır (düz köşe); öbür harfler özgün. Başlıklar kalın (700); sol bar satırları 600, seçili
  satır 700. Başlığın içindeki rozet ve bilgi simgesi
  Newsreader kalır.
- **Newsreader** (editoryal serif): geri kalan her şey (gövde metni,
  üst bar, düğmeler, tablolar). Gövde 400; yarı kalın 600; vurgu 700.
  Rakamlar tablolarda eşit genişlikte.

İkisi de `style.css` içinde gömülü, dış font sunucusuna bağlanmaz, SIL
Open Font License. Aileler değişkende: `--font-baslik` (Josefin Sans),
`--font` (Newsreader).

**Sol bar**
- Tepede KATIB logosu, ortada; üstünde ve altındaki çizgiye kadar 20'şer
  px boşluk. Altında ince siyah çizgi.
- **Ana Sayfa** (kendi sayfasını açar; içeriği aşağıda).
- Ortasında **Çalışma Alanları** yazan çizgi; altında Model Platformu
  kümesi ve kilitli alanlar, en altta ince siyah çizgi.
- Sayfa adları normal yazımla (büyük harf değil), alttaki Görünüm, Arşiv
  ve Yeni Çalışma ile aynı yazı: 15 px, yarı kalın; seçili satır kalın.
- **Model Platformu** (başta kapalı; başlığa basınca içindekiler açılır,
  yeniden basınca kapanır):
  - Model Akışı
  - Model Gösterge Paneli
  - Model Değişkenleri (Veri ve Sözlük, Dağılım ve SFA, Değişken Kontrolleri)
  - Model Özeti
  - Model Sohbeti (kapalı)
- Sayfa satırları kartsız, düz liste; satırlarda ok yok (ok yalnız açılıp
  kapanan Model Platformu başlığında ve Arşiv'de). Model Platformu'nun
  alt sayfaları içeride, ağaç çizgisiyle bağlı: başlığın altından inen
  dikey siyah çizgi son alt sayfanın ortasında biter, her alt sayfaya
  çizgi üstündeki küçük boş düğümden kısa yatay kol uzanır; seçili alt
  sayfanın düğümü dolu. Seçili satır köşesiz: hafif zemin (üst düzey
  satırlarda solunda düz siyah çizgi). Kırmızı ya da pembe vurgu yok.
- **Yeni güncelleme rozeti:** Model Değişkenleri satırının sağında kırmızı
  yuvarlak içinde, görülmemiş güncellemesi olan bölüm sayısı (en çok "9+").
  Bölümler: Veri Seti, Sözlük (Veri ve Sözlük), Dağılım, Tek Değişken
  Analizi (Dağılım ve SFA), Eksik Değer (Değişken Kontrolleri). Bir
  bölümün içeriği her sunucu yanıtında bir imzaya indirgenir; imza
  kullanıcının o bölümü en son gördüğü hâlden farklıysa bölüm yenidir
  (ör. veri seti ve sözlük seçilince Veri Seti, Sözlük ve Dağılım).
  Bölümün başlığı ekranda 0,1 saniye görününce görülmüş sayılır; sayı her
  bölümde bir azalır, hepsi görülünce rozet kalkar. Model Değişkenleri
  içindeki görünüm düğmelerinde (Veri ve Sözlük, Dağılım ve SFA, Değişken
  Kontrolleri) o görünümün sayısı ayrıca durur; Model Platformu kapalıyken
  toplam sayı başlığında görünür. Görülenler çalışma başına bu tarayıcıda
  saklanır; çalışma bu tarayıcıda ilk kez açıldığında o anki içerik
  görülmüş sayılır, yalnız sonraki değişiklikler rozete girer.
- KATIB'le Sohbet ve Gösterge Paneli (kapalı, hazırlanıyor): kutusuz,
  soluk yazı ve kilit.
- Altta robot, kitaplar ve kupa (`robot_alt`), altında:
- **Görünüm:** üç renk modu: Beyaz (varsayılan; sayfa zemini, sol bar ve
  yan paneller saf beyaz, kartlar ince kenarla ayrılır), Sepya (sıcak kâğıt
  tonu), Gri (açık gri zemin, koyu yazı). Sepya ve Gri'de yalnız zemin
  tonları değişir; renkler ve görseller Beyaz moddaki gibi kalır. Anahtar üç bölmeli segmentli
  düğme: güneş (Beyaz), kitap (Sepya), yarısı dolu daire (Gri); ince
  siyah çerçeve ve bölme çizgileri; simgeye basınca o mod seçilir; seçili
  bölme mürekkep siyahıyla dolu, simgesi ters baskı. Düğmenin
  başka bir yerine basınca sıradaki moda geçilir.
- **Arşiv:** kayıtlı çalışmalar; birine basınca kaldığı yerden açılır.
  Her satırın sağında çöp kutusu (onaylı, kalıcı silme). Altta "Diğer
  Klasörler": PROJE_HAFIZASI'nda olup listede olmayan kendi v-klasörleriniz
  (çalışma dosyası silinmiş, başlanmamış çalışma ya da silinmiş bir
  çalışmadan kalmış boş klasör), her biri silinebilir. Dataiku boş
  klasörün kendisini silmezse listede bunu söyleyen not çıkar; klasör
  Dataiku'nun klasör ekranından silinebilir, yeni çalışmalara engel olmaz.
  Silinen çalışmanın klasörüne yazma kapanır: silme anında süren arka plan
  işleri (açıklama düzenleme, kısaltma okuma, dönem, SFA kararları, öneri
  önbelleği) bitince klasöre yazamaz, klasör geri gelmez. Webapp dışında
  çalışan Spark işleri yazarsa klasör silmeden 20 sn, 1, 5 ve 15 dk sonra
  yeniden kontrol edilir ve yeniden silinir. Silinen numara backend yeniden
  başlatılana kadar yeni çalışmaya verilmez (geç yazma yeni çalışmaya
  düşmesin). Silmenin bittiği, klasörün ayrıntısı ve PROJE_HAFIZASI'nın
  dosya listesi birlikte kontrol edilerek söylenir; biri bayat dönerse
  kalan dosyalar yine silinir.
- **Çalışma özeti:** her çalışmanın klasöründe `ozet.json` (Arşiv listesi
  için). Bu yolda dosya yerine klasör oluşmuşsa özet yazılırken o klasör
  kaldırılır ve özet yeniden yazılır.
- **Yeni Çalışma:** yeni çalışma açar; açık çalışma silinmez, Arşiv'de kalır.

Uygulama ekranın tamamını kullanır ve tarayıcıda %88 yakınlaştırmadaki
gibi görünür: style.css'te `--olcek: .88` (1 = %100); tarayıcının kendi
yakınlaştırması %100'de kalır. Sol bar kaydırmasızdır (tasarım eni
340 px, satırlar 44 px, yazılar 15 px, çizim ikonları 40 px; %88 ölçekte
ekranda 299 px en). Bar, Model Platformu açıkken yüksekliğine sığacak
oranda büyür ya da küçülür (0,6 ile 1,2 kat arası); yazılar, çizimler
ve logo birlikte büyür, eni de aynı orana gelir. Örnek: 1366x768
pencerede 1,13 kat (yazı ekranda 15 px, çizim 40 px). Ölçek CSS zoom
ile verilir (transform değil): yazı ve görseller bulanıklaşmaz.
Bölmeleri ayıran ve uygulamayı en dışta çevreleyen kalın çizgi her modda
mürekkep siyahı.

**Ana Sayfa** (uygulama bununla açılır; alanın tamamını kaplar, kendi
içinde kayar; zemin kartlarla aynı renk, Beyaz modda beyaz). Yalnız
tanıtır; sayfalar sol bardan açılır.
- Üst bölüm: üstte `anasayfa_aciklama` görseli ortada; boyu kendi
  oranındaki boyun %95'i (dikeyde hafif basık; kırpma yok, yalnız
  saydam kenarları kırpılır).
- İlk ekran sayfaya tam sığar: üst bölüm ve Çalışma Alanları kartları
  sayfa yüksekliğini doldurur, kaydırma çubuğu açılmaz, altta boşluk
  kalmaz (F11 ile ya da Dataiku içinde). app.js (anaSayfaSigdir) görselin
  enini bloğun iç eninin %30'u ile %100'ü arasında buna göre ayarlar;
  görsel tam ende de yer artarsa başlık en çok 1,15 kat büyür, kalan
  boşluk üst bölüme eklenir (içerik ortada). Kart açıklaması açılınca
  sayfa aşağı kayar. Dar ekranda (1100 px altı) yapılmaz. Altında ortada iki satır başlık:
  "Veriyle Yapacağınız Her Şey," siyah, "Yapay Zekâ Desteğiyle Tek
  Platformda." kırmızı (kalın, harf aralığı .01em). Görsel
  yüklenemezse yalnız başlık kalır. Başlık boyu ve boşluklar blok
  enine bağlı: yakınlaştırınca blok tek parça büyür, hiçbir ekranda
  yana taşmaz. Tanıtım yazısı burada yok; Çalışma Alanları kartlarına
  dağıtılmıştır.
- Çalışma Alanları (başlık ortada, iki yanında 2 px siyah çizgi; üç ayrı iş,
  her kartta kendi tanıtımı): Model Platformu (model kurma, izleme ve
  üzerine konuşma), KATIB'le Sohbet (yüklenen veriyle ya da genel sohbet)
  ve Gösterge Paneli (modellerden bağımsız veri analizi ve durum izleme);
  son ikisi hazırlanıyor. Kartta solda büyük görsel (sol barın çizimi,
  kartın içinin %34'ü), sağında üstte başlık, altında açıklama (16,5 px). Üst
  bölümün, kartların, faz ve sayfa kutularının kenarı 2 px mürekkep
  siyahı. Kartlarda düğme yok: karta basınca (klavyede Enter / Boşluk)
  kart seçilir (kırmızı kalın kenar, hafif pembe zemin) ve kartların
  altında o alanın açıklaması açılır; yeniden basınca ikisi de kalkar
  (aynı anda tek kart). Açıklama açılınca sayfa, üst kenarı kartlarla
  açıklama başlığı arasındaki boşluğun ortasına gelecek şekilde kayar.
- Açıklamalar yalnız tanıtır. Her biri ortada, iki yanında çizgi olan
  başlıkla ve altında ortalı kısa girişle başlar.
  - Model Platformu Nasıl Çalışır: platformu hiç bilmeyen birine baştan
    sona anlatır. Giriş paragrafından sonra alt bölümler, her biri ortada
    çizgili alt başlıkla:
    - Genel Bakış: Ne yapar, Nasıl ilerler (öneri, onay, Geri Dön,
      Arşiv), Ne üretir (analitik baz set, aday set, final model,
      değişken kataloğu, model dokümanı).
    - Beş Faz: tek kutuda süreç şeridi (numara, simgeli daire, faz adı;
      daireler kesik çizgiyle bağlı).
    - Fazlar Adım Adım: her faz bir kutu; solda faz başlığı ve amacı,
      sağda numaralı adımlar (1.1 ile 5.4 arası), her adımda ne
      yapıldığı. Metinler `akis_kayit.py` ve `akis_metin.py`'deki adım
      tanımlarına dayanır; adım değişirse burası da güncellenir.
    - Yapay Zekâ ve Kod: yapay zekânın önerdikleri ve kodun hesapladıkları
      iki kutuda madde madde.
    - Katkılar: dört kutu, simge, başlık ve yazı ortada; sayısal iddia yok.
    - Sayfalar: Çalışma Alanları kartları düzeninde beş kutu (solda büyük
      çizim, sağda ad ve açıklama).
    - Güvenceler: açık zeminli tek kutu, dört bölme.
    Bütün kutular 2 px mürekkep kenarlı. 1300 px altında Genel Bakış,
    faz ayrıntıları ve Yapay Zekâ ve Kod tek sütun; katkılar ve
    güvenceler 2x2, sayfalar ikişerli.
  - KATIB'le Sohbet ve Gösterge Paneli: başlık ve kısa giriş.
- Faz ve adım adları koddan (`akis_metin.py`, `akis_kayit.py`) alınmıştır;
  biri değişirse `index.html`'deki Ana Sayfa da güncellenir.
- Açılışta Model Akışı arka planda yüklenir; akış bir kart için analiz
  alanını kendisi açarsa kullanıcı Ana Sayfa'dan koparılmaz, Model
  Akışı'na geçince açık görünür.

**Model Akışı**
- Üstte **İş Akışı** barı:
  - solda İş Akışı düğmesi;
  - yanında bulunulan faz ve adım;
  - sağda tamamlanan / toplam adım.
- İş Akışı düğmesi beş fazı ve adımları solda bir bölmede açar. Bölme
  alanın en altına kadar uzanır ve aynı düğmeyle kapanana kadar açık kalır.
  Fazın adımları (ve grup adımlarının alt adımları) sol bardaki Model
  Platformu alt sayfaları gibi ağaç çizgisiyle bağlı: dikey siyah çizgi,
  her adıma küçük düğümden kısa yatay kol, çizgi son adımda biter.
- Listede görülmüş bir adıma basınca sohbet o adımın bloğuna kayar.
- Adımlar sohbet alanında blok blok ilerler. Her blok kendi kararını ve
  "Geri Dön" düğmesini taşır.
- **Adım atıfları:** bir işin hangi adımda yapılacağını ya da yapıldığını
  söyleyen her metin (sohbet mesajları, kart açıklamaları, sağ panel
  notları, "i" açıklamaları, hata mesajları, sohbet kutusunun kilit notu)
  adımı iş akışındaki numarası ve adıyla, kalın yazar: "kolon tanımları
  **01.2.3 Eksik Sözlük Tanımları** adımında oluşturulur", "Sohbet,
  **02. Değişken Mühendisliği** adımında açılır". Faz 01'in adım listesi
  başlangıca göre değiştiği için numara da değişir (A'da Kolon Rolleri
  01.2.2, B'de 01.5.1); numara iş akışı listesiyle aynı kuralla
  hesaplanır (`akis_kayit.adim_kodu`, mesajlarda `akis_atif.adim`).
  Arka uç adımı `**…**` ile işaretler, ön yüz kalın yazar; düz metin
  alanlarında (title) işaret düşer.
- **01.2.1 Baz Sözlük (birden fazla):** bir tablonun kolon açıklamaları
  farklı sözlüklerde olabileceği için Baz Sözlük çoklu seçimlidir.
  Seçilenler kutunun içinde etiket olarak durur, × ile çıkar; kutuya
  basınca sözlük listesi açılır, seçilen eklenir (seçilmiş olanlar listede
  görünmez). Boş kutuda Backspace son etiketi siler. Hiç seçilmezse
  sözlüksüz devam edilir (bütün kolonlar 01.2.3'te tanımlanır).
  - **Birleştirme:** birden fazla sözlük seçilirse her biri ayrı ayrı
    doğrulanır, sonra çalışma klasöründe tek sözlükte birleşir
    (`BIRLESIK_SOZLUK`, kolonlar DEGISKEN, ACIKLAMA, KATEGORI, KAYNAK).
    Kolonlar adla (büyük/küçük harf farksız) eşleşir; bir kolonun tanımı
    seçim sırasındaki ilk sözlükten, tanımı dolu olandan alınır (ilkinde
    boşsa sonrakinden). Kurulum çıktısında her sözlükten kaç kolonun
    tanımı alındığı ve iki sözlükte farklı tanımı olan kolonlar adıyla
    yazılır. Girdi sözlüklerine yazılmaz. Tek sözlükte davranış öncekiyle
    aynı. Ekranda ve kayıtlarda sözlük "A + B" diye yazılır.
  - **Eşleşme:** Baz Veri Seti seçilince o tablonun en son eşlendiği
    sözlük(ler) kutuda seçili gelir; alanın altında "Bu veri setiyle daha
    önce kullanıldığı için seçildi" yazar. Kutu boşsa ya da içindekiler de
    kendiliğinden gelmişse doldurulur; kullanıcının eklediği ya da
    çıkardığı seçim ezilmez, form dolu açıldığında da dokunulmaz. Projede
    artık olmayan tablo seçilmez. Sözlüksüz onay eşleşmeyi değiştirmez.
    Başlangıç B'nin kaynak sözlükleri buna girmez.
- **Tablonun önceki seçimleri** (`fe_agent/veri_gecmisi.py`,
  `PROJE_HAFIZASI/VERI_SETI_GECMISI.json`): her tablo için yalnız en son
  onaylanan Baz Sözlük ve kolon rolleri durur (çalışma bilgisi ve sayım
  yok; Arşiv'den silme etkilemez). 01.2.1 ve 01.2.2 onaylanınca o
  tablonun kaydı yenisiyle değişir. Dosya yoksa ilk açılışta eski
  çalışmaların `ozet.json` dosyalarından bir kez kurulur (segment özette
  olmadığı için boş gelir). Dosyada tablo başına yalnız sözlükler ve
  roller durur; başka alan yazılmaz.
- **01.2.2 Kolon Rolleri önceki seçimle:** adım ilk kez açıldığında
  (henüz hedef ve kimlik seçilmemişken) model tipi, hedef, kimlik, dönem
  ve segment alanları bu tablonun en son onaylanan rolleriyle dolu gelir;
  açıklamanın sonunda "Alanlar bu tablonun en son onaylanan kolon
  rolleriyle dolu geldi; değiştirebilirsiniz." yazar. Yalnız hâlâ o
  alanın listesinde olan değer yazılır (ör. artık 0/1 olmayan hedef
  gelmez). Değerler onaylanana kadar çalışmaya kaydedilmez; kullanıcı
  her alanı değiştirebilir ya da boşaltabilir. B'de baz veri seti
  platformun birleştirme çıktısı olduğu için önceki rol gelmez.
- **01.2.2 Kolon Rolleri:** ilk seçim model tipi (Classification,
  Regression, Time Series Forecasting, Clustering). Şu an seçilebilen tek
  tip Classification olduğu için seçili gelir. Hedef listesi tipe göre
  değişir: Classification'da yalnız 0 ve 1 değeri alan kolonlar;
  Regression ve Time Series Forecasting'de ikiden fazla farklı değer alan
  tam ya da ondalıklı sayı kolonları (tam sayı tipindeki kimlik adayları
  hariç); Clustering'de hedef seçilmez. Listeler profilden (tam tablo)
  çıkar. Sonraki adımlar (tek değişken analizi, bölme, model ve başarı
  ölçütleri) şu an yalnız Classification için hazır: öbür üç tip kapalı
  (soluk, tıklanmaz, açıklamasının altında "Şu An Kapalı"), yazarak
  girilse de kaydedilmez. Seçim `durum["problem"]`de durur.
  Her kartta adın altında Türkçe karşılığı (Sınıflandırma, Regresyon,
  Zaman Serisi Tahmini, Kümeleme) ve sağ üst köşede "i" var: tip nedir,
  ne için kullanılır ve hiç bilmeyenin anlayacağı bir örnek. "i" kartın
  dışında durduğu için kapalı tiplerde de solmaz ve açılır. Metinler
  `akis_faz01.PROBLEM_TIPLERI`'nde, Türkçe adlar
  `akis_metin.MODEL_TIPI_TURKCE`'de.
- **Model tipi rollerin üstünde yazılır.** Hedef, kimlik ve dönem
  kolonunun yazıldığı her yerde ilk satır model tipidir: Özet sayfasının
  Modelleme Tanımları bölümü, sağ paneldeki Veri Seti kartı, Arşiv'deki
  çalışma özeti, model dokümanı (genel bilgiler, model özeti ve hedef
  bölümü), senaryo konfig JSON'u (`model_tipi`, ilk anahtar), Değişken
  Kataloğu (`MODEL_TIPI` kolonu, `HEDEF`'in solunda) ve çalışma durumu
  JSON'u (`problem`, `meta`'nın hemen üstünde). Ad tek kaynaktan gelir
  (`akis_metin.MODEL_TIPI_ADI`). Model tipi seçimi gelmeden önce hedefi
  tanımlanmış çalışmalar Classification sayılır.
- **01.2.3 Eksik Sözlük Tanımları:** sözlükte tanımı olmayan kolonlar
  listelenir; işaretlenip açıklaması yazılan kolon sözlüğün çalışma
  kopyasına eklenir. İşaretlenmeyen kolon tanımsız kalır ve
  01.2.3.1'de sorulur (düğme "N Kolonu Tanımsız Bırak ve Devam Et").
- **01.2.3.1 Tanımsız Kolonlar** (A ve B; 01.2.3'ün alt adımı, numaralar
  kaymaz): 01.2.3'ten sonra sözlükte hâlâ tanımı olmayan kolonlar tip ve
  boş oranıyla listelenir; satır başına "Çıkar" kutusu, "Tümünü Seç" ve
  "Tümünü Temizle".
  - İşaretli kolon karar verildiği anda çıkar: Veri ve Sözlük
    sayfasındaki veri önizlemesinde, sözlük tablosunda, 01.3 Değişken
    Listesi ve Tip Kontrolü'nün listesinde ve sayılarında yer almaz,
    "süreç dışı" sayısına girmez; sağ paneldeki sözlük kartının Tanım
    Sayısı satırında "N kolon çıkarıldı" yazar
    (`akis_durum.cikarilan_kolonlar`). `haric_kolonlar`'da durur, bu
    yüzden AMP_VERISETI ve AMP_SOZLUK fiziksel olarak 01.3'te yazılırken
    ikisine de girmez. Süreç dışı listesini değiştiren istek
    (`/haric_kolonlar`) bu kolonları listeden düşürmez. Baz Veri Seti'nin
    kendi kolon sayısı (girdi tablosu) değişmez.
  - İşaretsiz kolon AMP_VERISETI'nde kalır, AMP_SOZLUK'ta satırı tanımı
    boş durur. Açıklama Düzenleme'ye (01.2.4.2) girmez, tanımı boş kalsın
    diye. 01.3 Değişken Listesi ve Tip Kontrolü'ndeki "açıklaması olmayan kolonu süreç dışı işaretle" kuralı
    bu kolonlara uygulanmaz.
  - İlk hal: kutular boş; veri setinde hazır duran bölme kolonu işaretli
    gelir (değiştirilebilir); tek değerli kolon ve tek değerli dönem
    kolonu işaretli ve kilitli (her durumda çıkar, sebebi kutunun
    ipucunda).
  - Düğme: "N Kolonu Çıkar ve Devam Et", hiç işaret yoksa "Hepsi Veri
    Setinde Kalsın ve Devam Et". Karar `durum["tanimsiz_karar"]`
    ({kolon: "cikar" | "kalsin"}); geri dönüşte kart bu kararla açılır.
    Tanımsız kolon yoksa adım sorulmadan geçilir.
  - Girdi veri seti ve sözlük değişmez. Bu adımdan önce kaydedilmiş çalışmalar bir adım
    ileri kaydırılır (`SIRA_SURUMU` 13); onlarda tanımsız kolonlar önceki
    gibi süreç dışı kalır.

**Başlangıçlar (01.1)**
- **A:** Baz Veri Seti Mevcut.
- **B:** Kaynak Tablolar Mevcut.
- **C:** Otomatik Pilot (şu an kapalı).

**Fazlar**
1. Çalışma Kurulumu
2. Değişken Mühendisliği
3. Veri Anlama ve Hazırlama
4. Değişken Değerlendirme
5. Modelleme ve Finalizasyon

## Tarayıcıda hatırlanan tercihler

| Anahtar | Ne |
|---|---|
| `amp_renk_modu` | Görünüm (renk modu): `acik` (Beyaz), `sepya`, `gri` |
| `amp_akis_acik` | İş Akışı bölmesi açık / kapalı |
| `amp_dg_alt` | Model Değişkenleri'nde açık görünüm |
| `fe_agent_calisma_id` | Açık çalışmanın kimliği |
