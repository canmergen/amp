# Katip · Kurumsal Analitik, Tahminleme ve İçgörü Platformu

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
| `katip_logo` | `katip_logo.png` | Sol barın tepesindeki Katip logosu |
| `anasayfa` | `anasayfa.png` | Sol bar: ANA SAYFA |
| `model_platformu` | `model_platformu.png` | Sol bar: MODEL PLATFORMU başlığının ikonu |
| `model_akisi` | `model_akisi.png` | Sol bar: Model Akışı |
| `gosterge_paneli` | `gosterge_paneli.png` | Sol bar: Model Gösterge Paneli ve Gösterge Paneli |
| `degiskenler` | `degiskenler.png` | Sol bar: Model Değişkenleri |
| `ozet` | `ozet.png` | Sol bar: Model Özeti |
| `model_sohbeti` | `model_sohbeti.png` | Sol bar ve Ana Sayfa: Model Sohbeti |
| `katiple_sohbet` | `katiple_sohbet.png` | Sol bar ve Ana Sayfa: Katip'le Sohbet |
| `gorunum` | `gorunum.png` | Sol bar: Görünüm düğmesi |
| `arsiv` | `arsiv.png` | Sol bar: Arşiv |
| `yeni_calisma` | `yeni_calisma.png` | Sol bar: Yeni Çalışma |
| `robot_alt` | `robot_alt.png` | Sol bar: Görünüm'ün üstünde robot, kitaplar ve kupa |
| `anasayfa_aciklama` | `anasayfa_aciklama.png` | Ana Sayfa: üst bölümün görseli (saydam zeminli, geniş; yazının altında tam en) |
| `karsilama` | `robot_welcome.png` | Sohbetteki ilk robot |
| `bot` | `robot_chat.png` | Normal konuşma |
| `dusunme` | `robot_think.png` | Arkada iş sürerken |
| `user` | `robot_llm_person.png` | Kullanıcı balonu |

Görsel bulunamazsa yerinde boşluk kalır, sayfa bozulmaz. Sol bar
ikonlarının yeri görsel gelene kadar boş durur (HTML'deki çizgi ikon
görünmez, yalnız görselle aynı boyda yer tutar); görsel gelince aynı yere
oturur, yazılar kaymaz; bulunamazsa yer boş kalır, sembol görünmez.

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

**Yazı tipi:** tek aile, **Outfit** (geometrik, yuvarlak, sade). Bütün
arayüzde: başlıklar, sol bar, metin, tablolar, düğmeler. Başlıklar ve
vurgu kalın (700), sol bar satırları 600 (seçili satır da), metin 400;
kalın halleri gerçek (yapay kalınlaştırma yok). Rakamlar tablolarda eşit
genişlikte. Değişken font, `style.css` içinde tek dosya olarak gömülü
(yalnız Latin ve Türkçe harfler, noktalama ve oklar; yaklaşık 33 KB);
dış font sunucusuna bağlanmaz. SIL Open Font License. Aile adı "AMP
Outfit"; `--font` ve `--font-baslik` ikisi de onu gösterir. Yüklenemezse
sistemin serifsiz fontu (Segoe UI, Arial) kullanılır.
- **Görünür boy:** CSS'teki px boyları (`--fs-*` ve tek tek verilenler)
  değişmez. Outfit aynı px'te önceki fontlardan küçük çizildiği için font
  yüzünde tek bir `size-adjust` (%108) vardır: her yazı, her ağırlık ve
  her yer aynı oranla büyür, boylar arasındaki ilişkiyi yalnız px
  değerleri belirler. `font-size-adjust` kullanılmaz (`--x-yukseklik:
  none`).
- **Sol bar seçili satır:** yazısı öbür satırlarla aynı (15 px, 600);
  seçili olduğunu gri zemin ve soldaki çizgi gösterir.

**Sol bar**
- Tepede ortada Katip logosu (`katip_logo.png`; barın
  eninin %63'ü); üstünde ve altındaki çizgiye kadar 20'şer px boşluk.
  Yüklenemezse gizlenir. Altında ince siyah çizgi.
- **Ana Sayfa** (kendi sayfasını açar; içeriği aşağıda).
- Ortasında **Çalışma Alanları** yazan çizgi; altında Model Platformu
  kümesi ve kilitli alanlar, en altta ince siyah çizgi.
- Sayfa adları normal yazımla (büyük harf değil), alttaki Görünüm, Arşiv
  ve Yeni Çalışma ile aynı yazı: 15 px, yarı kalın; seçili satır da aynı (gri zemin ve soldaki çizgiyle belli olur).
- **Model Platformu** (başta kapalı; başlığa basınca içindekiler açılır
  ve Model Akışı seçilir, o an kümenin sayfalarından biri zaten açıksa o
  kalır; yeniden basınca küme kapanır, açık sayfa değişmez). Açılır
  kümeler açık sayfayı izler: kümenin dışındaki bir sayfaya geçilince
  (Ana Sayfa ya da başka bir alan) küme kendiliğinden kapanır; başka bir
  yoldan içindeki bir sayfaya geçilince (Yeni Çalışma, Arşiv'den çalışma
  açma) açılır. Bu yalnız sayfa değişince olur; aynı sayfadayken
  başlıktan kapatılan küme yeniden açılmaz. Kilitli satıra basmak bir
  şey değiştirmez:
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
- Katip'le Sohbet ve Gösterge Paneli (kapalı, hazırlanıyor): kutusuz,
  soluk yazı ve kilit.
- Altta robot, kitaplar ve kupa (`robot_alt`), altında:
- **Görünüm:** üç renk modu. Anahtar üç bölmeli segmentli düğme: güneş
  (Beyaz), kitap (Sepya), yarısı dolu daire (Koyu); ince çerçeve ve
  bölme çizgileri; simgeye basınca o mod seçilir; seçili bölme mürekkeple
  dolu, simgesi ters baskı. Düğmenin başka bir yerine basınca sıradaki
  moda geçilir. Seçim tarayıcıda hatırlanır; eskiden "Gri" seçili olan
  tarayıcıda Koyu açılır.
  - **Beyaz** (varsayılan): sayfa zemini, sol bar ve yan paneller saf
    beyaz, kartlar ince kenarla ayrılır.
  - **Sepya:** sıcak kâğıt tonu (sayfa #F1E9D6, paneller #F6F0E2, kartlar
    #FBF7EE). Yazı, çizgiler ve uygulamayı çevreleyen çerçeve aynı sıcak
    kahve-siyah (#2B2118). Kırmızı kiremit tonunda (#B3261E); kilitli
    satırlar sıcak gri (#7A6B57).
  - **Koyu:** gerçek koyu tema; saf siyah ve saf beyaz yok. Katmanlar
    gölgeyle değil açıklıkla ayrılır: sayfa #121418, paneller #171A1F,
    kartlar #1C2027. Yazı #E6E8EB (kartta 13,3:1); yazı ve çizgi
    kırmızısı #FF5A5F (5,4:1); düğme dolgusu marka kırmızısı (#D51115,
    beyaz yazı). Pembe şerit, seçili satır, yeşil ve sarı rozet zeminleri
    rengin şeffaf tonu. Mürekkep yazıları ana yazı renginde, mürekkep
    çizgileri (sol bar ayraçları, Ana Sayfa kart kenarları) yumuşak gri
    (#555C67). Grafik mavisi #6EA8FE. Kaydırma çubukları ve form kutuları
    da koyu.
  - **Görsel konturu (her modda):** görseller saydam zeminli; renklerine
    hiç dokunulmaz (süzgeç, ters çevirme, plaka yok). Her görselin dış
    hattına 1 px kontur çizilir (art arda dört yönde 1 px gölge; köşeler
    dahil tam): Beyaz'da siyah (#1A1A1A), Sepya'da sepyanın siyahı
    (#2B2118), Koyu'da çizimlerin kâğıt rengi (#EDE6D8; siyah çizgi ve
    dolgular koyu zeminde kaybolmasın). Kapsadığı görseller: sol bar
    çizimleri, alttaki robot, Ana Sayfa'nın üst görseli ve kart
    çizimleri, sohbet avatarları. Logo yalnız Koyu'da konturlu: Beyaz ve
    Sepya'da siyah kontur altındaki küçük siyah yazının harflerini
    doldurup okunmaz yapıyor. Kilitli satırların çizimleri gri ve soluk.
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

Uygulama ekranın tamamını kullanır ve tarayıcıda %79,2 yakınlaştırmadaki
gibi görünür: eski %88 ölçeğin %90'ı. style.css'te `--olcek: .792`
(1 = %100); tarayıcının kendi yakınlaştırması %100'de kalır. Sol bar
kaydırmasızdır (tasarım eni 340 px, yazılar 15 px). Boyu iki adımda
bulunur: önce eski sığdırma oranı (sayfa %88'deyken Model Platformu
açık barın yüksekliğine sığan oran, 0,6 ile 1,2 kat arası), sonra bar
ekranda bunun %80'i boyda gösterilir (`--sol-olcek: .8`). Eni de aynı
orana gelir. Barın eni ve boyu bu ölçekle kalır; içindeki sayfa
satırları ve alttaki Görünüm, Arşiv, Yeni Çalışma düğmeleri (yazı, çizim
ve satır boyu birlikte) ayrıca `--sol-icerik: 1.2` katı büyür. Logo ve
robot barın enine bağlı olduğu için büyümez. Büyümüş içerik barın boyuna
ya da bir satırın yazısı satıra sığmazsa kat sığana kadar düşer (en az
1); 1440x900'de 1,18 kat (sol bar yazısı ekranda yaklaşık 15 px). Ölçek CSS
zoom ile verilir (transform değil): yazı ve görseller yeni boyunda
baştan çizilir, bulanıklaşmaz.
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
  üzerine konuşma), Katip'le Sohbet (yüklenen veriyle ya da genel sohbet)
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
  - Katip'le Sohbet ve Gösterge Paneli: başlık ve kısa giriş.
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
- **Sayfa yenilenince kartlar kararlarla gelir:** biten adımın kartı
  transkriptte son haliyle saklanır (`backend._biten_adimi_guncelle`).
  Formlar dolu haliyle (akis_sohbet._biten_ekran), Eksik Sözlük
  Tanımları satırları ve tanım kontrolü karar gövdesinden; Tanımsız
  Kolonlar, Dönem Bilgisi (değer anlamları ve gruptan ayrılanlar dahil),
  Ad Parçaları (yalnız kararlar) ve Kolon Adları kartları onay anında verilen
  kararlarla yeniden üretilir (`akis_faz01.karar_sonrasi_alan`, Geri Dön
  ile aynı kaynak). Yeni hali kayıt sınırını aşarsa kart ilk haliyle
  kalır. Henüz onaylanmamış kartta yapılan düzenlemeler yenilemede
  kaybolur.
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
    Kolonlar adla (büyük/küçük harf farksız) eşleşir; tanımı yalnız bir
    sözlükte dolu olan kolon o tanımı alır. Kurulum çıktısında her
    sözlükten kaç kolonun tanımı alındığı ve sözlüklerde farklı tanımı
    olan kolonlar adıyla yazılır. Girdi sözlüklerine yazılmaz. Tek
    sözlükte davranış öncekiyle aynı. Ekranda ve kayıtlarda sözlük "A + B"
    diye yazılır.
- **01.2.1.1 Sözlük Birleştirme** (yalnız A; kurulumun alt adımı,
  `sozluk_birlestir`): veri setindeki bir kolonun seçilen sözlüklerde
  birden fazla farklı dolu tanımı varsa (yalnız boşluk farkı sayılmaz)
  kart açılır; yoksa adım sorulmadan geçilir.
  - Seçenekler kurulumda `_sozlukleri_birlestir` ile çıkarılır
    (`durum["_sozluk_birlesim"]["secenekler"]`: {kolon: [{sozluk, tanim}]},
    sözlük sırasıyla).
  - Kart "Farklı Tanımlı Kolonlar": DEĞİŞKEN | TANIM. Tanım hücresinde
    her sözlüğün tanımı sözlük adıyla seçenek olarak, en altta "Kendim
    yazayım" kutusu (yazmak o seçeneği seçer). Başta ilk seçilen
    sözlüğün tanımı seçili. Üstte sözlük başına "Tümünde <sözlük> Tanımı".
    "Kendim yazayım" seçili ve boşsa onay durur.
  - Onay (`sozluk_birlestir_uygula`): seçilen tanım `BIRLESIK_SOZLUK`'e
    yazılır (KAYNAK sözlük adı ya da "Kullanıcı") ve sözlüğün çalışma
    kopyası bu tanımlarla yeniden çıkarılır; AMP_SOZLUK'e buradan gider.
    Karar `durum["sozluk_birlesim_karar"]` ({kolon: {kaynak, metin}});
    geri dönüşte kart bu kararla açılır, yenilemede de kararla gelir.
  - Bu adımdan önce kaydedilmiş A çalışmaları bir adım ileri kaydırılır
    (`SIRA_SURUMU` 14); onlarda farklı tanımlı kolonlar ilk sözlüğün
    tanımıyla kalır.
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
- **01.2.4 Sözlük ve Kolon Adı Kontrolü (A ve B):** sözlüğe de kolon
  adlarına da tam güvenilmez (tanımların bir kısmı yanlış ya da eksik,
  adlarda eksik ve yanlış yazılmış kısaltmalar var). Amaç 02'deki dil
  modelinin de insanın da her kolonu kesin anlaması. Dört alt adım sırayla,
  her biri bir öncekinin onayladığını kesin bilgi olarak kullanır ve her
  satır kullanıcı tarafından onaylanmadan geçilmez:
  1. **01.2.4.1 Dönem Bilgisi** (`donem`): adlardaki SAYILI zaman
     parçaları (30D, M3, 3_M, H00_06).
  2. **01.2.4.2 Ad Parçaları** (`parca`): öbür bütün parçalar
     (kısaltmalar, sözcükler, DAY, MONTH, TMSNCFRST): anlam, tür, standart
     yazılış; yazımı farklı aynı parçalar birleşir.
  3. **01.2.4.3 Kolon Kartları** (`aciklama`): her kolonun kartı
     parçalardan kodla kurulur, dil modeli kartı tanımla karşılaştırıp
     açıklamayı yazar.
  4. **01.2.4.4 Kolon Adları** (`kolon_ad`): adlar standart yazılışlarla
     Ad Standardı'na göre kodla kurulur.
  "Kontrol Edilmeden Geçilsin" seçilirse dördü de atlanır. Eski Kısaltma
  Sözlüğü adımı kaldırıldı (göç: `SIRA_SURUMU` 15; eski Açıklama
  Düzenleme / Kısaltma Sözlüğü / Yeni Kolon Adları adımında duran
  çalışma Ad Parçaları'nda yeniden açılır, eski kısaltma kararları
  silinir).
- **01.2.4.1 Dönem Bilgisi, kart:** başlığın altında tek satır özet
  ("6 kalıp (3 pencere, 1 zaman noktası) · 2 yorumlanıyor · 4 olası")
  ve yanında "i": yönerge ile sütun açıklamaları orada. Altında iki
  sekme (sayılarıyla): Kalıplar (tablo) ve Olası (KALIP / ADLARDA GEÇEN /
  NEDEN EMİN DEĞİL tablosu, "Tabloya Al" satırı Kalıplar'a taşır ve o
  sekmeye geçer). Yalnız sayılı kalıplar burada: rakamsız parçaların
  taraması, komşu adaylar ve hafızadaki rakamsız dönem kayıtları bu
  adımdan kalktı (Ad Parçaları'nda gelir).
  - **[sayı]:** kalıpta ve anlamda sayı yer tutucusu ekranda "[sayı]"
    yazar ("[sayı]D", "[sayı] gün boyunca"). İçeride yer tutucu olarak
    saklanır (app.js `donemAnlamGoster` / `donemAnlamIc`: k'inci [sayı]
    kalıbın k'inci yer tutucusu olur); hafıza ve Kolon Kartları aynı
    kalır. Sayısız kalıpta [sayı] yazılırsa satır "Kontrol edin" olur.
  - **Durum etiketi:** satırlar renksiz; anlam kutusunun üstünde tek
    satır: "Dil modeli · 9 / 10 örnek tanım uyuşuyor", "Hafızadan",
    "Düzenlendi", "Elle eklendi",
    "Kontrol edin" ya da "Anlam boş" (amber), "Dil modeli yorumluyor".
    Dikkat isteyen satırın solunda ince amber çizgi.
  - Altında kısa notlar: Soru, "Ad ile tanımlar çelişiyor: ...", Not ve
    kısa uyarı ("Dikkat: Yalnız PER_DAY içinde geçiyor", uzun açıklaması
    "i"de).
  - **Bekleyen satırlar:** dil modeli çalışırken biçimden bulunan bütün
    kalıplar baştan "Dil modeli yorumluyor" olarak görünür (tür kutusu
    yerine "Tür dil modelinin yorumundan sonra gelir."); yorum geldikçe
    yoklamayla dolar, dönem değilse kalkar. Dil modeli çalışırken bloğun
    robotu düşünen hâlde (`robot_think.png`).
  - **İptal:** ilerleme satırında İptal (`/donem_iptal`,
    `akis_faz01.donem_iptal`, `donem.iptal`): o ana kadar gelen yorumlar
    kalır, yorumlanmayanlar Olası'ya düşer, kartta "Dil modelini
    durdurdunuz" notu çıkar. Süren çağrının sonradan gelen cevabı
    yazılmaz.
- **Kalıp yakalama (`donem.kaliplar`, `parca_listesi`):** sayı içeren
  parçalar kalıba çevrilir (`H00_06` → `H<NN>_<NN>`, `L3M` → `L<N>M`).
  Alt çizgiyle ayrılmış sayı ve tek harf tek parça sayılır (`3_M`, `M_3`;
  `donem.ayrik_ikili`); bu ikililerdeki tek harf ayrıca dönem parçası
  işaretlenir.
- **Yazılış ailesi:** aynı harf ile sayının bütün yazılışları tek kalıptır;
  adı `<N>` + harf (`<N>M`). Yazılışlar (`donem.YAZILIS_SIRASI`): `<N>M`
  (3M, 30D; harf 1-3), `M<N>` (M3, M12; harf 1-2), `<N>_M` ve `M_<N>`
  (yalnız tek harf). `donem.kalip_deseni("<N>M")` hepsine uyar;
  `deger_anlami` sayıyı hangi yazılışta olursa olsun yerine koyar (M_6 →
  "son 6 ay"); app.js `donemKalipDeseni` / `donemSayiEslesmesi` aynı kural.
  - Kartta kalıp hücresinde adlarda geçen yazılışlar yazar ("[sayı]M ·
    M[sayı] · [sayı]_M").
  - Dil modeline aile satırında YAZILIŞLAR (her biri değerleriyle) ve her
    yazılıştan bir örnek gider. Tanımlar bir yazılışın açıkça farklı
    anlamda olduğunu gösteriyorsa model onu "ayri" listesine yazar
    (yazılış, anlam, tür); en az bir yazılış ailede kalır. Ayrılan yazılış
    (`M<N>`) kendi satırında durur, kalıp hücresinde "<N>M ailesinden ayrı
    anlamlı yazılış" yazar; ailenin deseni o yazılışın değerlerini almaz.
  - Hafıza: aile kendi adıyla yazılır. Ayrı satırda onaylanan yazılış
    `donem_ayri_yazilis` listesinde işaretlenir; sonraki çalışmada da
    ayrı gelir. Hafızada yalnız ayrı işaretsiz bir yazılışın kaydı varsa
    (`<N>_M`, eski `M<NN>`) aile o anlamla gelir (`donem.hafiza_anahtari`).
    Aile çıkarılırsa bu yazılış kayıtları da hafızadan silinir (ayrı
    işaretliler kalır).
  - **Aileye Kat:** ayrı yazılış satırında (ailesi tabloda varsa) notun
    yanında "Aileye Kat". Basınca satır tablodan kalkar, değerleri ve
    yazılışı aile satırına geçer; aile satırında "M<N> aileye katıldı ·
    Geri Al" yazar. Kararda satır `{"kalip": "M<N>", "aileye_kat": true}`
    gider: onayda yazılışın değerleri ailenin değeri sayılır (değere kendi
    anlamı yazılabilir), yazılışın hafızadaki kaydı ve ayrı işareti
    silinir; sonraki çalışmada ailesiyle gelir. Geri dönüşte ve yenilemede
    katılmış hâliyle gelir.
  - Kolon Kartları'nda ayrılan yazılışın deseni aileden önce eşleşir.
- **Zaman bilgisi türleri:** dil modeli her kalıba "tur" yazar
  (`llm.ZAMAN_TURLERI`: pencere, nokta, birim, olcu; `llm.zaman_turu`).
  Kartta kalıp hücresinde seçim kutusu ve altında seçili türün açıklaması
  (app.js `DONEM_TURLERI`):
  - Pencere: sayı bir süre; veri o süre boyunca toplanır (30D: 30 gün
    boyunca).
  - Zaman Noktası: sayı belirli bir an ya da sıra (M3: yılın 3. ayı ya da
    3 ay önceki ay).
  - Zaman Birimi: sayısız zaman birimi (DAY: gün).
  - Zaman Ölçüsü: değerin kendisi bir süre (TMSNCFRST).
  Kararda `zaman_tur`, durumda `durum["donem_turleri"]` ({kalıp: tür}),
  hafızada `donem_tur`.
- **Anlamın kaynağı (dil modeli kuralları, `llm._DONEM_ANLAM_KURALLARI`):**
  önce ad, sonra tanımlar. Anlam parçanın yapısından kurulur (D gün, W
  hafta, M ay, Q çeyrek, Y yıl, H saat; sözcük kısaltmaları harflerinden).
  Sözlük tanımları kesin değil, kanıttır: kalıp başına en çok 10 örnek
  tanım (`donem.ORNEK_ADET`) gider; model her tanımın anlamıyla uyuşup
  uyuşmadığını sayar (`kanit`: bakılan, uyan). Adda karşılığı olmayan
  bilgi (son, önceki) anlama yazılmaz, nota yazılır. Ad ile tanımların
  çoğu çelişirse adın yapısı geçer, çelişki `celiski`de yazar. Süre mi
  (pencere) an mı (nokta) olduğu tanımların çoğundan çıkar; belli
  değilse soru iki seçeneği de yazar. Anlam tür adını tekrar etmez ("N
  gün boyunca", "N gün boyunca zaman penceresi" değil).
- **Arka plan işi (`donem.baslat`):** yorum `YORUM_PARCA` (6) kalıplık
  parçalara bölünür; en çok
  `ES_ZAMANLI` (4) çağrı aynı anda çalışır, her parçanın sonucu gelince
  yazılır.
- **Kolon Kartları'na giden dönem parçası** (`_donem_parca_metni`):
  değerin kendi anlamı ya da kalıbın anlamı, yer tutucu değerin sayısıyla
  doldurulmuş olarak ve yanında türü: "3_M: son 3 ay (zaman penceresi)",
  "MONTH: ay (zaman birimi)". Kalıp adı ve yer tutucu (`<N>`, `N`) dil
  modeline gitmez; sözlüğe yazılan açıklama sayıyla yazılır.
  `donem.ISTEM_SURUMU` 6: önbellekteki eski yorumlar yeniden alınır.
- **Tabloya giren kalıplar:** hafızadan gelenler ve dil modelinin
  zaman bilgisi olduğunu bulduğu parçalar Kalıplar'a girer; yalnız
  ikililer içinde geçse de (MONTH). Olası'ya düşenler: dil modelinin
  sorusu olanlar, kanıtı zayıf olanlar (en az 2 örnek tanıma bakıp
  uyuşanlar %60'tan az, `DONEM_KANIT_ESIGI`; nedeni "Örnek tanımlardan
  yalnız 1 / 5 tanesi bu anlamla uyuşuyor"), dil modelinin bakmadığı ya
  da İptal ile yorumlanmayan kalıplar ve hafıza ile modelden gelmeyen
  uyarılı parçalar.
- **01.2.4.1 Dönem Bilgisi, değerler:** sayı yer tutucusu olan kalıpta
  (`<N>D`, `H<NN>_<NN>`) Anlam hücresinde kalıbın anlamının altında bir
  örnek ("Örnek: 30D → 30 gün boyunca") ve "Değerleri Düzenle" bağlantısı
  (yanında özet: "6 değer · 1 kendi anlamı · 1 dönem değil") var.
  Bağlantı, grup satırının hemen altında tablo genişliğinde değer panelini
  açar: başlık ve tek satır ipucu, sonra DEĞER / KOLON / ANLAM / DURUM
  tablosu (kartın `dg-tablo` düzeni).
  - **Durum** her değerde bölmeli düğmeyle seçilir (Görünüm anahtarıyla
    aynı dil: mürekkep çerçeve, seçili bölme ters baskı, `.dg-segment`):
    - Kalıba Uyar: anlam kalıbın anlamından, yer tutucunun yerine değerin
      sayısı konarak gelir (`donem.deger_anlami`, app.js
      `donemDegerAnlami`; aynı türdeki yer tutucular kalıptaki sırayla
      eşlenir). Kalıp değişince değişir.
    - Kendi Anlamı: değere özel anlam (360D: son 1 yıl); kalıp değişse de
      kalır. Yer tutucu içeremez (onay durur).
    - Dönem Değil: değer gruba yanlış girmiş; dönem sayılmaz. Grupta dönem
      olarak en az bir değer kalır (bütün değerler dönem değilse kalıp Çıkar
      ile çıkarılır).
  - **Düzenleme yalnız Kendi Anlamı'nda:** Kalıba Uyar satırında anlam
    düz metin olarak görünür ve yazılamaz (kalıbın anlamı satırın anlam
    kutusundan değişir). Bir değere özel anlam yazmak için önce o satırda
    Kendi Anlamı'na basılır; kutu açılır, odaklanır ve yazılan yalnız o
    değerde kalır, öbür değerler ve kalıbın anlamı değişmez. Kendi anlamı
    boşaltılıp kutudan çıkılırsa değer Kalıba Uyar'a döner. Kalıbın
    anlamıyla aynı kalan kendi anlamı onayda saklanmaz.
  - Adlarda Geçen çipleri durumu gösterir: kendi anlamı yeşil çerçeve,
    dönem değil kesik çerçeve ve üstü çizili.
  - **Kayıt:** kendi anlamları `durum["donem_deger_anlam"]` ({kalıp:
    {değer: anlam}}), dönem olmayanlar `durum["donem_ayrilan"]` ({kalıp:
    [değer]}) ve kararın `ayrilan` alanı ({değer: {anlam, cikar}});
    kısaltma hafızasında `donem_deger` ve `donem_ayrilan` (sonraki
    çalışmalarda aynı kalıbın değerleri bu durumla gelir; kalıp hafızadan
    silinince bunlar da silinir). Kalıbın anlamıyla aynı kalan kendi
    anlamı saklanmaz. Yalnız kolon adlarında geçen değerler kabul edilir.
    Onay mesajı kendi anlamı ve dönem olmayan değer sayısını yazar.
  - **Kolon Kartları'na:** kendi anlamı olan değer o anlamla gider
    ("360D: son 1 yıl (zaman penceresi)"), dönem olmayan değer dönem
    parçası sayılmaz (grubun deseni onu kapsamaz, `_AyrilanliDesen`),
    öbürleri kalıbın anlamıyla.
  - Dönem tablosunun penceresi en çok ekran yüksekliğinin %72'si.
- **01.2.4.3 Kolon Kartları'nın kapsamı:** dil modeline yalnız
  sözlükte zaten tanımı olan ve süreçte kalan kolonlar gider. Girmeyenler:
  01.2.3'te tanımı eklenen kolonlar (kullanıcı yazdı ya da önerisini
  onayladı; `durum["_tanim_kararlari"]` "ekle"), 01.2.3.1'de "kalsın"
  denenler (tanımları boş kalır) ve süreç dışı kolonlar. Bunlar kartta
  da listelenmez; AMP_SOZLUK'e tanımları olduğu gibi yazılır. Kartın
  "Sütunlar" bilgisinde bu yazar.
- **01.2.4.2 Ad Parçaları** (`parca.py`, `akis_faz01._parca_alani`,
  `parca_plan`, `parca_uygula`):
  - **Parçalar** (`parca.parcalar`): rol kolonları ve süreç dışı
    kolonlar hariç bütün kolon adlarının rakamsız parçaları; sayılı
    kalıpların kapsadıkları (`parca.sayili_konumlar`, dönemle aynı kural)
    ve 01.2.4.1'de onaylanan kalıplara uyanlar burada yok. Parça başına
    kaç kolonda geçtiği, tanımsız kolon sayısı, en sık yanında duran 3
    parça ve en çok 10 örnek (ad, tanım; listenin başından sonuna eşit
    aralıkla, rastgele değil).
  - **Anlam** (`llm.parca_yorumla`, istem `SISTEM_PARCA`, rol `parca`:
    düşünen model önce): önce parçanın yazılışı ve yaygın kısaltma
    bilgisi, sözlük tanımları kanıt (oylama, `kanit`); `celiski`, `soru`,
    `not`; tür (12): konu, yön, nitelik, ölçü, istatistik,
    karşılaştırma, pencere, nokta, zaman birimi, geçen süre, birim,
    diğer. Arka planda 12 parçalık çağrılar, en çok 4 aynı anda; İptal
    (`/parca_iptal`) gelenleri tutar.
  - **Hafıza** (`KISALTMA_HAFIZASI.json` `parcalar` {PARÇA: {anlam, tür,
    standart}} ve `parca_esler` {"A|B": "ayni"/"farkli"}; eski
    `kisaltmalar`, `degisimler`, `turler` ve rakamsız `donem` kayıtları
    da öneri olarak okunur): hafızada olan parça dil modeline gitmez,
    "Hafızadan" önerisiyle gelir, değiştirilebilir.
  - **Kart:** özet satırı ve "i"; iki sekme. Parçalar: arama, süzgeç
    (Tümü, Onaylanmadı, Kontrol Edin, Hafızadan, Düzenlendi, Eksik ya da
    Hatalı), "Görünenleri Onayla", 100'lük sayfalar; tablo PARÇA (kolon
    sayısı, yanındakiler, "Örnekler" satırın altında açılır,
    `/parca_ornek`) / ANLAM (üstünde durum etiketi) / TÜR (açıklaması
    altında) / STANDART / ONAY. Yazım Sorunları: kodun bulduğu yakın
    yazılışlar (sessiz harf iskeleti aynı, tek harf farkı, biri
    ötekinin başı) ve önerilen anlamı aynı çıkan parçalar; Aynı / Farklı
    ve Onay. "Aynı" denen gruptaki parçalar adlarda seçilen yazılışı ve
    onun satırındaki anlam ile türü alır (satırları kilitli, "TXN ile
    aynı").
  - **Kurallar:** "Kontrol edin" satırları (soru, çelişki ya da örnek
    tanımların %60'ından azı uyuşuyor) toplu onaylanmaz. Onaylı satırda
    bir şey değişince onay kalkar. Standart: büyük harfle başlar, büyük
    harf ve rakam, en çok 12; anlamı farklı iki parça aynı standardı
    alamaz. Bütün parçalar ve çiftler onaylanmadan geçilmez.
  - **Sonuç:** `durum["parca_bilgisi"]` {PARÇA: {anlam, tür, standart}},
    geri dönüş için `parca_karari` ve `parca_esler`; onaylananlar
    hafızaya yazılır.
- **01.2.4.3 Kolon Kartları** (`aciklama_duzen.py`, `akis_faz01`
  `_aciklama_*`):
  - **Kart** kodla kurulur (`_kolon_karti`): onaylı parçaların anlamları
    türlerine göre alanlara (Konu, Yön, Nitelik, Zaman, Ölçü, İstatistik,
    Karşılaştırma, Birim, Diğer); dönem parçası değerin sayısıyla
    ("30 gün boyunca"). Dil modeline PARÇALAR (anlam ve tür) ve KART
    kesin bilgi olarak gider; model tanımla karşılaştırıp tek açık
    açıklama yazar, tanımda olup adda olmayan bilgiyi `ek` (Ek bilgi)
    olarak ayırır, ad ile tanım çelişkisini `ad_notu`'na yazar. Karttaki
    sayılar açıklamada geçmeli (kod denetimi). `ACIKLAMA_SURUMU` 2.
  - **Onay:** her satırda Onay kutusu ve "Görünenleri Onayla" (soru, ad /
    dağılım notu ya da kontrol notu olan satırı atlar). Onay çalışma
    klasöründeki kayda yazılır (`kabul`: onaylanan açıklama metni);
    açıklama sonradan değişirse onay kendiliğinden düşer. Süzgeçler:
    Onaylanmadı, Ek Bilgi da var. Bütün kolonlar onaylanmadan geçilmez;
    "değiştirmeden devam" düğmesi yok.
- **01.2.4.4 Kolon Adları** (`parca.ad_birimleri`, `parca.ad_kur`,
  `akis_faz01._kolon_ad_alani`):
  - Her parça standart yazılışını alır; birimler Ad Standardı'ndaki yer
    sırasına dizilir (aynı yerdekiler adda geçtikleri sırayla). Sayılı
    zaman parçası yazıldığı gibi kalır (3_M, H00_06), yeri Zaman.
    Varsayılan sıra: Konu, Yön, Nitelik, Ölçü, İstatistik, Zaman,
    Karşılaştırma, Birim, Diğer (TXN_30D_CNT → TXN_CNT_30D); büyük harf,
    ayraç "_".
  - **Ad Standardı paneli:** yerler ← → ile sıralanır; adlar sunucuda
    yeniden kurulur (`/kolon_ad_onizle`), adı değişen ailenin onayı
    kalkar. Onayda hafızaya yazılır (`parca_ad_standardi`).
  - **Satırlar ailedir** (adı yalnız sayılarla ayrılan kolonlar; adı
    değişenler önce): Yeni Ad / Eski Ad Kalsın ve Onay; "Ailede N kolon"
    bütün ikilileri açar. Sorunlu ad (sayıyla başlıyor, iki kolon aynı
    adı alıyor, rol kolonunun adı) onaylanamaz. Arka uç adları onayda
    kendisi yeniden kurar ve denetler. Sonuç `durum["kolon_yeni_ad"]`.
- **02'ye giden sözlük (aile kataloğu, `llm.sozluk_katalogu`):** sözlükte
  kolon kartı varsa Kural Tabanlı Değişken Üretimi'nin ve keşif
  hipotezlerinin dil modeline kolonlar düz "AD: açıklama" listesi yerine
  aile kataloğu olarak gider: aile başına üyeler, ortak kart, üyelerde
  değişen alan (çoğu zaman pencere), bir örnek açıklama ve ek bilgi;
  açıklama kırpılmaz (200 karakter). Dil modeline kartların onaylı ve
  kesin olduğu, gerekçeyi kartın anlamıyla yazması söylenir. Kart yoksa
  (kontrol atlandı ya da eski çalışma) eski düz liste. Üretilen ifadedeki
  kolonlar her durumda gerçek kolonlarla doğrulanır.
- **AMP_SOZLUK kolonları:** DEGISKEN, TIP, TIP_DEGISIKLIGI, ACIKLAMA,
  NULL_ORANI, SUREC_DISI, KATEGORI, ESKI_AD, ACIKLAMA_ORIJINAL, KONU, YON,
  NITELIK, ZAMAN, OLCU, ISTATISTIK, KARSILASTIRMA, BIRIM, DIGER,
  EK_BILGI, AILE (yeni adlarla aile anahtarı, tek kolonlu ailede boş),
  ONAY_KULLANICI, ONAY_ZAMANI (Kolon Kartları onayı).
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
  - İşaretsiz kolon AMP_VERISETI'nde kalır, AMP_SOZLUK'te satırı tanımı
    boş durur. Kolon Kartları'na (01.2.4.3) girmez, tanımı boş kalsın
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
| `amp_renk_modu` | Görünüm (renk modu): `acik` (Beyaz), `sepya`, `koyu` (eski `gri` kaydı Koyu açılır) |
| `amp_akis_acik` | İş Akışı bölmesi açık / kapalı |
| `amp_dg_alt` | Model Değişkenleri'nde açık görünüm |
| `fe_agent_calisma_id` | Açık çalışmanın kimliği |
