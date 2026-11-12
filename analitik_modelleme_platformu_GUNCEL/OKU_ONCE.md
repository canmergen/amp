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
| `kurum_logo` | `kurum_logo.png` | Sol barın tepesindeki logo |
| `anasayfa` | `anasayfa.png` | Sol bar: ANA SAYFA |
| `model_platformu` | `model_platformu.png` | Sol bar: MODEL PLATFORMU başlığının ikonu |
| `model_akisi` | `model_akisi.png` | Sol bar: Model Akışı |
| `gosterge_paneli` | `gosterge_paneli.png` | Sol bar: Model Gösterge Paneli ve Gösterge Paneli |
| `degiskenler` | `degiskenler.png` | Sol bar: Model Değişkenleri |
| `ozet` | `ozet.png` | Sol bar: Model Özeti |
| `model_sohbeti` | `model_sohbeti.png` | Sol bar ve Ana Sayfa: Model Sohbeti |
| `katiple_sohbet` | `katiple_sohbet.png` | Sol bar ve Ana Sayfa: Asistanla Sohbet |
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

**Model adı kullanıcıya gösterilmez:** arayüzde hiçbir yerde (kart notu,
hata, ipucu) dil modelinin adı ya da bağlantı kimliği geçmez.
`llm.MODEL_ADLARI` yalnız sıra etiketi ("1. dil modeli"); hata ve "cevap
vermedi / ulaşılamadı" notları model saymaz, yalnız nedenleri yazar
(`_orkestra_hatasi`, `Orkestra.notu`); hata metinlerindeki kimlikler
`llm.model_adi_gizle` ile "dil modeli" olur. Ayrıca backend'in her JSON ve
metin cevabı bu süzgeçten geçer (`backend._model_adlarini_gizle`,
`after_request`); desen dar: `openai:` kimlikleri, `MODELLER`'deki
bağlantı ve model adları ve eski ekran adları (kolon adları bozulmaz).
Ön yüzde "Öneren: …" ipuçları kaldırıldı.

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
- Profil sayısal kolonda min, maks, kantiller (0, 0,25, 0,5, 0,75, 1) ve
  ortalamayı (`ortalama`: sonlu değerlerin toplamı / sonlu değer adedi)
  tutar. Spark motoru ortalamayı tekil değer tablosundan adetle ağırlıklı
  toplamla, pandas motoru doğrudan hesaplar (aynı formül).
- Tarih kolonunda min, maks ve medyan (`medyan`; pandas median ile aynı:
  çift adette iki ortadaki tarihin tam ortası, tarih tipinde hesaplanır,
  `profil_kural.tarih_medyani`). Spark motoru ortadaki satırları tekil
  değer tablosundan birikimli adetle bulur.

## Ekran

**01.3 Değişken Listesi ve Tip Kontrolü kartı 01.2.4 sonuçlarıyla.**
Değişken hücresinde 01.2.4.4'te onaylanan yeni ad, altında soluk "Eski
ad: …" (`teyit_satirlari` `yeni_ad`, `akis_panel._uygulanacak_adlar`;
kayıttan sonra kolon zaten yeni adla gelir, eski ad `eski_ad`'da).
Arama iki adla da bulur, sıralama yeni adla. Kararlar (tanım, süreç
dışı, tip dönüşümü) kolonun kayıttaki adıyla gider; liste kaydedilince
AMP_VERISETI ve AMP_SOZLUK yeni adlarla ve 01.2.4.3'te onaylanan
tanımlarla yazılır, sonraki bütün adımlar bu ikisini okur. Sözlük
Tanımı kutusu metnin tamamını gösterir (`dg-teyit-tanim`, yükseklik
metne göre, `boylaPlanla`; Enter yeni satır açmaz). Satır rengi yalnız boş tanımda
(sarı, "Tanım Boş"); öneriyle eklenen tanımlar önceki adımlarda (01.2.3,
01.2.4.3) onaylandığı için 01.3'te ayrıca işaretlenmez (eski "Dil
Modeli Önerisi" mavisi bekleyen iş gibi okunuyordu). Tanımlar 01.2.4.3
onayında sözlüğün çalışma kopyasına yazılan son hâllerdir. Kayıt mesajı
tabloya yazılmayan kolonları nedenine göre ve adlarıyla yazar
(`_dusen_metni`, `amp_cikti.veri.dusen_adlar`): "01.2.3.1'de
çıkardığınız 2 kolon (PERIOD, RN)" ve "süreç dışı N kolon (…)". 01.2.3.1'de
çıkarılan kolon listede olmadığı için tek değerli notunda da anılmaz.

**Veri ve Sözlük sekmesi: 01.2.4 sonuçları hemen görünür.** AMP_VERISETI
ve AMP_SOZLUK dosyaları eskisi gibi 01.3 Değişken Listesi ve Tip
Kontrolü onayında bir kez, her şey uygulanmış olarak yazılır. Sağ paneldeki
Değişken Listesi ise her 01.2.4 onayından hemen sonra güncel hâli
gösterir (`akis_panel.feature_tablo`, `adim_0124_ozeti`):
- **Tanım:** 01.2.4.3 onayında düzeltilen açıklama sözlüğün çalışma
  kopyasına yazıldığı için tabloda güncel.
- **Ad:** 01.2.4.4'te adı değişen kolonda DEĞİŞKEN hücresinde yeni ad,
  altında soluk "eski: …" (`yeni_ad`; `amp.yeniden_ad_esleme` ile, rol ve
  süreç dışı kolonlar hariç). Arama iki adda da çalışır; satırın anahtarı
  (tanım düzeltme, süreç dışı) eski ad kalır.
- **Satır detayı:** adı değiştiyse eski adı; kolon kartı (01.2.4.3
  onayından, `_onayli_kolon_kartlari`): güncel tanımdan farklıysa
  orijinal açıklama, kart alanları ("Kart: Konu" gibi), ek bilgi, notunuz.
- **Tablonun altında "Sözlük ve Kolon Adı Kontrolü sonuçları"**
  (`ozet0124Ciz`; açılır bölümler, açık / kapalı durumu yeniden çizimde
  kalır; yalnız onaylanan bölüm görünür):
  - Dönem Bilgisi ve Ad Parçaları başlıklarında i: bölümün ne olduğu,
    örnekle (i'ye basmak bölümü açıp kapatmaz).
  - Dönem Bilgisi: Kalıp, Anlam, Zaman Türü, Özel Durumlar (değerin
    kendi anlamı, gruptan ayrılan değerler, "Adda RATIO geçerse: …").
  - Ad Parçaları: Parça, Anlam, Tür, Kolon (adında geçen kolon sayısı);
    15'ten çok parçada arama kutusu.
  - Kolon Adları: kaç kolonun adı değişti, Ad Standardı sırası, dönem
    yazılışları, ada eklenen bilgiler (`durum["kolon_ad_eklenen"]`,
    01.2.4.4 onayında yazılır).
  - Kolon Kartları: kaç kolonun kartı olduğu ve satır detayında
    göründüğü.
- **Excel İndir (Değişken Listesi):** iki biçimde de (sağ panel: Değişken,
  Yeni Ad, Tip, Sözlük Tanımı; sohbetteki karar listesi: ayrıca Süreç
  Dışı) "Yeni Ad" kolonu var: AMP_VERISETI'ndeki adı (01.2.4.4'te
  değiştiyse yeni ad, değişmediyse aynı ad; rol ve süreç dışı kolonlar
  kendi adında). "Değişken" ilk (eski) ad kalır; "Filtrelenmiş" sayfası
  ekrandaki satırlarla eski adla eşleşir (`_excel_satirlari`).

**Tablolarda hiza:** her tabloda (Değişken Listesi ızgarası dahil)
başlık ve hücre içeriği ortalı; çip dizileri ve hücredeki düğmeler de
ortada. Tablo hücresindeki yazı alanları (kutu, açılır liste) da
yazısını ortadan yazar. Hiçbir öğe hücresinden taşmaz: kutu ve liste en
çok hücre genişliğinde, seçenek düğmeleri (ör. 01.2.4.1 Değerleri
Düzenle'deki Kalıba Uyar / Kendi Anlamı / Dönem Değil) hücreye sığmazsa
düğme yazısı iki satıra iner. Değer panelinde Durum kolonu 360px, panel
başlığı numaralı kalıpla yazılır ("[sayı 1]D_[sayı 2]D değerleri").
Anahtar ve değeri iki uca dağıtan satırlar (SFA ölçüt satırı, Değişken
Listesi detay satırı) dokunulmaz. Kural `style.css` sonunda tek yerde.

**01.4 Veri Bölme Stratejisi çubuğu** (`bolmeCubukParca`, `.bolme-cubuk`):
setler yüzdeleriyle orantılı renkli parçalar (Train, Test, Validasyon;
zamansal bölmede dönemler ve gap). Parça yazısından dar olmaz; dar
ekranda alt satıra sarılır. Tek satırlı parça en az 34px, hedef oranı
da yazan iki satırlı parça en az 48px (iç boşluk 6px 14px, satır arası
1,35); yükseklik içeriğe göre uzar, sarılan sıralar arasında 3px boşluk.

**Yazı tipi:** tek aile, **Outfit** (geometrik, yuvarlak, sade). Bütün
arayüzde: başlıklar, sol bar, metin, tablolar, düğmeler. Başlıklar ve
vurgu 600 (sol bar satırları ve seçili satır da), metin 400;
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
- **Yazı ölçeği (ekranda görünen boy, her yerde aynı):** ÜÇ BOY, İKİ
  KALINLIK. Tasarım boyları 14 / 12,5 / 16 px; `--ekran-kat` (.9) ile
  ekranda 12,6 / 11,25 / 14,4 px. Metin, ad, başlık, düğme, tablo, sol
  bar satırları, üst şerit ve İş Akışı fazları büyük boyda; küçük yazılar
  (adım sayacı, rozetler, İş Akışı alt açıklamaları ve adımları,
  "Çalışma Alanları" ayracı) küçük boyda; yalnız sohbetteki kart başlığı
  (01.1 ...) en büyük boyda. Ad ve başlıklar boyla değil kalınlıkla
  ayrılır: 600 (sol bar satırlarıyla aynı), metin 400; 700 ve 800
  kullanılmaz. Boylar `calc(14px * var(--ekran-kat) / var(--olcek))`
  biçiminde; sol barda `--sol-ekran`'a bölünür (app.js: solBarOlcekle),
  böylece her pencere boyunda ekranda aynı px. Düğme ve giriş kutusu
  yükseklikleri ekranda 24,3 / 20,7 px. Ana Sayfa'nın tanıtım yazıları
  kendi boylarında (sayfa ölçeğiyle). Grafiklerin eksen yazıları ekranda
  her genişlikte 10,8 px (app.js: EKSEN_YAZI_PX). Bütün boyutu tek
  yerden değiştirmek için `--ekran-kat` (1 = eski %100 görünüm) ile
  `--olcek` ve `--sol-olcek` birlikte değiştirilir.
- **Sol bar seçili satır:** yazısı öbür satırlarla aynı (600);
  seçili olduğunu gri zemin ve soldaki çizgi gösterir.

**Sol bar**
- Tepede ortada logo (`kurum_logo.png`; barın
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
- **Yeni güncelleme nabzı:** görülmemiş güncellemesi olan bölüm varsa
  Model Değişkenleri satırının zemini sayı yerine 2,4 saniyede bir
  yavaşça kırmızılaşıp açılır (`.guncel-nabiz`; Beyaz, Sepya ve Koyu'da
  kendi kırmızısı; hareket azaltma tercihinde sabit hafif kırmızı). Model
  Platformu kapalıyken başlığı nabız atar. Bütün yeni bölümler görülünce
  kalkar. Bölümler: Veri Seti, Sözlük (Veri ve Sözlük), Dağılım, Tek
  Değişken Analizi (Dağılım ve SFA), Eksik Değer (Değişken Kontrolleri).
  Bir bölümün içeriği her sunucu yanıtında bir imzaya indirgenir; imza
  kullanıcının o bölümü en son gördüğü hâlden farklıysa bölüm yenidir
  (ör. veri seti ve sözlük seçilince Veri Seti, Sözlük ve Dağılım).
  Bölümün başlığı ekranda 0,1 saniye görününce görülmüş sayılır. Model
  Değişkenleri içindeki görünüm düğmelerinde (Veri ve Sözlük, Dağılım ve
  SFA, Değişken Kontrolleri) o görünümün görülmemiş bölüm sayısı kırmızı
  yuvarlak içinde durur. Görülenler çalışma başına bu tarayıcıda
  saklanır; çalışma bu tarayıcıda ilk kez açıldığında o anki içerik
  görülmüş sayılır, yalnız sonraki değişiklikler girer.
- Asistanla Sohbet ve Gösterge Paneli (kapalı, hazırlanıyor): kutusuz,
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
    rengin şeffaf tonu. Beyaz modda siyah olan bütün çizgiler (bölmeleri
    ayıran ve uygulamayı çevreleyen kalın ayraç, sol bar ayraçları, Ana
    Sayfa kart kenarları, Görünüm anahtarı) koyu modda beyaz (#E6E8EB);
    mürekkep yazıları da aynı renkte. Grafik mavisi #6EA8FE. Kaydırma çubukları ve form kutuları
    da koyu.
  - **Görsel konturu (her modda):** görseller saydam zeminli; renklerine
    hiç dokunulmaz (ters çevirme, plaka yok). Her görselin dış hattına
    her yönde EŞİT kalınlıkta kontur çizilir (index.html'deki SVG
    filtreleri: görselin saydamlık maskesi bulanıklaştırılıp eşiklenir,
    dış hat yuvarlak genişler; köşe ve çaprazlarda kalınlaşmaz). Kalınlık
    ekranda her görselde 1,2 px (app.js: KONTUR_PX; konturGuncelle
    bulanıklığı sayfa, sol bar ve sol bar satırlarının ölçeğine böler).
    Renk: Beyaz'da siyah (#1A1A1A), Sepya'da sepyanın siyahı
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

Uygulama ekranın tamamını kullanır ve tarayıcıda %71,28 yakınlaştırmadaki
gibi görünür: .88 x .9 x .9; son .9 (`--ekran-kat`) bütün uygulamanın
tarayıcıda %90'daki görünümüdür, yazı ve kontrol boyları da bu katla
çarpılır. style.css'te `--olcek: .7128`, sol bar `--sol-olcek: .72`
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
  üzerine konuşma), Asistanla Sohbet (yüklenen veriyle ya da genel sohbet)
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
  - Asistanla Sohbet ve Gösterge Paneli: başlık ve kısa giriş.
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
  kaybolur. Aynı adımın kartı birden fazla kez gönderildiyse (Geri Dön,
  onayda hata, soru turu) yalnız sonuncusu kararlarla güncellenir;
  yenilemede aynı adımın aynı türden eski karar kartları çizilmez
  (app.js `eskiKararKartlariniAyikla`; metinleri yerinde kalır), yoksa
  eski kopya kararlar kaydolmamış gibi görünürdü. Dönem Bilgisi, Ad
  Parçaları ve Kolon Adları kartları ayrıca geçmişten çizilince
  sunucudaki GÜNCEL kararlardan yeniden kurulur (`/karar_alani`,
  `akis_faz01.karar_alani`; yalnız bitmiş adım; dil modeli işi
  başlatılmaz) ve eski kartın yerine geçer; transkriptteki kopya eski
  kalsa da kararlar görünür. Kurulamazsa kartın altında "Bu kart verilen
  kararlarla yeniden kurulamadı" ve nedeni yazar. Yeni kart eski kartın
  YERİNE konur (`dogrulamaKartiEkle(alan, blok, yerine)`); adımın kabı
  yeniden aranmaz. Önceden kap `adimKabiAl` ile aranıyordu; o sohbetteki
  son bloğa baktığı için yanıt geldiğinde (F5 sonrası aktif adım, ör.
  02.3) kart en alta yeni bir 01.2 bloğunda, yanıtların geliş sırasıyla
  düşüyor ve eski kart da yerinde kalıyordu.
- **Geçilmiş adımın kabı tektir (`gecilmisAdimKabi`):** `adimKabiAl` ve
  `grupKabiAl`, aktif adımdan ÖNCEKİ bir adım için sohbette o adımın
  bloğu (gruplu blokta bölümü) zaten varsa onu döndürür; sohbetin sonuna
  yeni blok açmaz. Böylece yenilemeden sonra geç gelen herhangi bir yanıt
  (kart, metin, rozet) geçilmiş adımın kendi yerine girer. Aktif ve
  sonraki adımlar eski kuralla çalışır (son blok o adımın değilse yeni
  blok). Geri Dön'de hedef adım ve sonrası önce transkriptten silindiği
  için yeni blok yine açılır. `dogrulamaKartiEkle`'ye verilen eski kart
  bu arada ekrandan kalktıysa yeni kart hiçbir yere eklenmez.
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
  tablonun kaydı yenisiyle değişir. Her dosyanın işi ayrı: dönem
  kalıpları, ad parçaları ve ad standardı `KISALTMA_HAFIZASI.json`'da
  (kurum geneli bilgi); 01.2.4 kontrol adımlarının kararları
  `KONTROL_GECMISI.json`'da (veri seti ve sözlük başına, "Önceki Onaylı
  Kontrol Uygulansın"). Bu dosyada dönem kararı tutulmaz; eski dosyadaki
  `donem` alanı ilk okumada düşer (`veri_gecmisi.ALANLAR` = sözlükler,
  roller). 01.2.4.1 yeni çalışmada kalıpları, anlamlarını ve «Ayır» ile
  değerlerine ayrılan grupları hafızadan alır (`degerlerine_ayrildi`,
  iç biçimde `donem_ayrik`; `donem.hafiza_ayrik`, `hafizaya_ayrik_yaz`,
  `kisaltma.donem_ayrik_kaydet`: onayda bu çalışmada görülen grupların
  işareti konur ya da kalkar, görülmeyenlere dokunulmaz; kalıp
  hafızadan silinince işareti de kalkar); bu çalışmada verilmiş karar (geri dönüş ya da önceki onaylı
  kontrol) varsa o geçerlidir. Dosya yoksa ilk açılışta eski
  çalışmaların `ozet.json` dosyalarından bir kez kurulur (segment özette
  olmadığı için boş gelir).
- **01.2.2 Kolon Rolleri önceki seçimle:** adım ilk kez açıldığında
  (henüz hedef ve kimlik seçilmemişken) model tipi, hedef, kimlik, dönem
  ve segment alanları bu tablonun en son onaylanan rolleriyle dolu gelir;
  açıklamanın sonunda "Alanlar bu tablonun en son onaylanan kolon
  rolleriyle dolu geldi; değiştirebilirsiniz." yazar. Yalnız hâlâ o
  alanın listesinde olan değer yazılır (ör. artık 0/1 olmayan hedef
  gelmez). Değerler onaylanana kadar çalışmaya kaydedilmez; kullanıcı
  her alanı değiştirebilir ya da boşaltabilir. B'de baz veri seti
  platformun birleştirme çıktısı olduğu için önceki rol gelmez.
- **01.2.2 Kolon Rolleri:** ilk seçim model tipi (Sınıflandırma
  (Classification), Regresyon (Regression), Zaman Serisi Tahmini (Time
  Series Forecasting), Kümeleme (Clustering)). Şu an seçilebilen tek tip
  Sınıflandırma olduğu için seçili gelir. Hedef listesi tipe göre
  değişir: Sınıflandırmada yalnız 0 ve 1 değeri alan kolonlar; Regresyon
  ve Zaman Serisi Tahmininde ikiden fazla farklı değer alan tam ya da
  ondalıklı sayı kolonları (tam sayı tipindeki kimlik adayları hariç);
  Kümelemede hedef seçilmez. Listeler profilden (tam tablo) çıkar.
  Sonraki adımlar (tek değişken analizi, bölme, model ve başarı
  ölçütleri) şu an yalnız Sınıflandırma için hazır: öbür üç tip kapalı
  (soluk, tıklanmaz, açıklamasının altında "Şu An Kapalı"), yazarak
  girilse de kaydedilmez. Seçim `durum["problem"]`de durur.
  Kartın başlığı önce Türkçe ad, parantezde İngilizcesi; sağ üst köşede
  "i" var: tip nedir, ne için kullanılır ve hiç bilmeyenin anlayacağı bir
  örnek. "i" kartın dışında durduğu için kapalı tiplerde de solmaz ve
  açılır. Metinler `akis_faz01.PROBLEM_TIPLERI`'nde.
- **Model tipi rollerin üstünde yazılır.** Hedef, kimlik ve dönem
  kolonunun yazıldığı her yerde ilk satır model tipidir: Özet sayfasının
  Modelleme Tanımları bölümü, sağ paneldeki Veri Seti kartı, Arşiv'deki
  çalışma özeti, model dokümanı (genel bilgiler, model özeti ve hedef
  bölümü), senaryo konfig JSON'u (`model_tipi`, ilk anahtar; kod:
  `classification`), Değişken Kataloğu (`MODEL_TIPI` kolonu, `HEDEF`'in
  solunda) ve çalışma durumu JSON'u (`problem`, `meta`'nın hemen
  üstünde). Ekrandaki ad tek kaynaktan gelir
  (`akis_metin.MODEL_TIPI_GORUNUR`, `model_tipi_adi`): "Sınıflandırma
  (Classification)". İngilizce ad (`MODEL_TIPI_ADI`) yazarak girilen
  tipi tanımak, eski arşiv özetlerini okumak (`veri_gecmisi._TIP_KODU`
  ikisini de tanır) ve Değişken Kataloğu'nun `MODEL_TIPI` kolonu için
  kalır (tablodaki değer eski satırlarla aynı: "Classification"). Model
  tipi seçimi gelmeden önce hedefi tanımlanmış çalışmalar Sınıflandırma
  sayılır.
- **01.2.3 Eksik Sözlük Tanımları:** sözlükte tanımı olmayan kolonlar
  listelenir; işaretlenip açıklaması yazılan kolon sözlüğün çalışma
  kopyasına eklenir. İşaretlenmeyen kolon tanımsız kalır ve
  01.2.3.1'de sorulur (düğme "N Kolonu Tanımsız Bırak ve Devam Et").
  - **Hafıza dil modeline kesin bilgi olarak gider** (`_aciklama_baglami`):
    - Parça anlamları: hafızadaki bütün onaylı parçalar (önceki
      çalışmaların 01.2.4.2 onayları, eski onaylı kısaltmalar, DAY gibi
      rakamsız dönem parçaları; `hafiza_parca_anlamlari`) "KISALTMALAR
      (kesin)" bloğunda. Ek türündeki parça (PER: "[parça] başına")
      nasıl okunacağıyla gider.
    - Dönem parçaları: onaylı dönem kalıpları kolonun kendi sayılarıyla,
      kolon bazında "DÖNEM PARÇALARI (onaylı, kesin)" bloğunda
      (`kolon_donem_parcalari`; ör. "TXN_GDN_3D_CNT: 3D = son 3 gün").
      Adda koşul parçası geçerse koşullu anlam (RATIO). Bu çalışmanın
      01.2.4.1 onayı varsa o, yoksa hafıza.
    - Öncelik: aynı veri setinde onaylı tanım (satır doğrudan dolar) >
      bu çalışmanın 01.2.4.2 onayı > hafızadaki onaylı parça ve dönem
      anlamı > sözlükten okunan > tahmini. Bir veri setinde başka anlamda
      kullanıldığı not edilen parça "KISALTMALAR (dikkat)" bloğunda kalır.
    - Her pakete yalnız o paketteki kolon adlarında geçen parçalar gider.
    - Kartın üst notunun sonuna tek cümle eklenir: "Tanımlar yazılırken
      hafızadaki onaylı N parça anlamı ve M dönem kalıbı dil modeline kesin
      bilgi olarak verildi." (yalnız listelenen kolonlarda geçenler).
  - **Öneri önbelleği bağlam imzasıyla** (`oneri_imzalari`,
    `tanim_hafiza.oneri_bul(imzalar=)`): kolon başına, ona giden kesin
    parça, dikkat ve dönem anlamlarının özeti. Önbellekteki öneri yalnız
    aynı imzayla yazıldıysa kullanılır; hafıza değiştiyse o kolon dil
    modeline yeniden sorulur. Hafızanın dokunmadığı kolonun imzası boştur,
    eski önerisi geçerli kalır. Önbellek dosyasına IMZA kolonu eklendi.
  - **Aile düzeni:** adı yalnız sayılarla ayrılan kolonlar bir ailedir
    (`tanim_aileleri`, anahtar `aciklama_duzen.aile_anahtari`; rol
    kolonları aileye girmez).
    - Sıra: zorunlu kolonlar en üstte, gerisi aile aile (`aile_sirasi`);
      tablo ve dil modeli paketleri bu sırayla.
    - Kardeşlerden birinin tanımı hazırsa (önce onaylı tanım, sonra
      önbellekteki öneri) öbürlerine plan anında aktarılır. Kalan ailede
      dil modeli yalnız temsilciyi yazar; tanım gelince kardeşlere
      aktarılır (`_oneri_isi_calis`, `aileler`). Temsilci tanımsız
      kalırsa sıradaki kardeş temsilci olur; aktarılamayan kardeş dil
      modeline kendi başına sorulur. İlerleme sayacı bütün kolonları sayar.
    - Aktarım kuralları (`tanim_aile_aktar`): adlar yalnız sayılarla
      ayrılmalı ve eşleme tek anlamlı olmalı; tanımdaki her sayı adda
      geçmeli (3D_X2 için "6 gün" gibi türetilmiş sayı, bayraktaki 1/0
      aktarılmaz); değişen her sayı tanımda adda geçtiği kadar geçmeli
      ("00:00" gibi tekrar aktarılmaz); dönem parçalarının anlamı da aynı
      değişimle kardeşinkine dönmeli (H00_06 gece, H06_12 sabah gibi değere
      özel anlam aktarılmaz).
    - Aktarılan satır "Aileden" (kaynak `aile`, `aile_kaynagi`): satırda
      çip, açık mavi ton, lejantta "Aileden". Önbelleğe yazılmaz (her
      seferinde temsilciden yeniden türetilir).
    - Tabloda her ailenin üstünde başlık satırı: "Aile · TXN_[sayı]D_CNT ·
      N kolon" ve "i".
    - **Ailenin N kolonuna uygula:** bir aile kolonunun açıklaması
      öneriden farklıysa altında çıkar. `/tanim_aile_uygula`
      (`akis.tanim_aile_uygula`) aynı kurallarla kardeşlerin metnini
      döner; kardeş satırlar dolar (Düzenlendi), kaynak satır sözlüğe
      eklenecekse onlar da işaretlenir. Uygulanamayanlar nedeniyle yazar.
      Kayıt değişmez; karar kartın onayıyla gider.
- **01.2.4 Sözlük ve Kolon Adı Kontrolü (A ve B):** sözlüğe de kolon
  adlarına da tam güvenilmez (tanımların bir kısmı yanlış ya da eksik,
  adlarda eksik ve yanlış yazılmış kısaltmalar var). Amaç 02'deki dil
  modelinin de insanın da her kolonu kesin anlaması. Dört alt adım sırayla,
  her biri bir öncekinin onayladığını kesin bilgi olarak kullanır ve her
  satır kullanıcı tarafından onaylanmadan geçilmez:
  1. **01.2.4.1 Dönem Bilgisi** (`donem`): adlardaki SAYILI zaman
     parçaları (30D, M3, 3_M, H00_06).
  2. **01.2.4.2 Ad Parçaları** (`parca`): öbür bütün parçalar
     (kısaltmalar, sözcükler, DAY, MONTH, TMSNCFRST ve 01.2.4.1'de dönem
     diye alınmayan sayılı parçalar, ör. X2): anlam, tür, standart
     yazılış; yazımı farklı aynı parçalar birleşir.
  3. **01.2.4.3 Kolon Kartları** (`aciklama`): her kolonun kartı
     parçalardan kodla kurulur, dil modeli kartı tanımla karşılaştırıp
     açıklamayı yazar.
  4. **01.2.4.4 Kolon Adları** (`kolon_ad`): adlar standart yazılışlarla
     Ad Standardı'na göre kodla kurulur.
  Seçenekler: "Sözlük ve Kolon Adları Kontrol Edilsin" (adım adım; önceki
  kontrol seçeneği varken başlığı "Adım Adım Kontrol Edilsin"),
  "Kontrol Edilmeden Geçilsin" (dördü de atlanır) ve kayıt varsa en üstte
  "Önceki Onaylı Kontrol Uygulansın" (harfler A, B, C; soru "Bu veri seti
  ve sözlük için proje hafızasında önceki bir kontrol var..."). Eski Kısaltma
  Sözlüğü adımı kaldırıldı (göç: `SIRA_SURUMU` 15; eski Açıklama
  Düzenleme / Kısaltma Sözlüğü / Yeni Kolon Adları adımında duran
  çalışma Ad Parçaları'nda yeniden açılır, eski kısaltma kararları
  silinir).
- **Önceki onaylı kontrol** (`fe_agent/kontrol_gecmisi.py`,
  `PROJE_HAFIZASI/KONTROL_GECMISI.json`, TEK DOSYA; anahtar okunur: "VERI
  SETI | SÖZLÜK + SÖZLÜK" (sözlükler sıralı), sözlüksüz "... | sözlüksüz";
  yalnız A ve C, B'de tutulmaz). Yalnız onaylı kararlar durur; çalışma
  Arşiv'den silinse de kalır:
  - `donem`, `parca`: `karar` (onayda kartın gönderdiği gövde);
    `kolon_ad`: `karar` ve onaydaki yeni adlar (`adlar`).
  - `aciklama` (Kolon Kartları): `tamam`, `onayli` / `toplam`, kullanıcı
    notları (`notlar`, `parca_notlari`, `aile_notlari`, `elle`) ve
    yalnız onaylanan kolonların son açıklaması (`onaylanan` {kolon:
    {aciklama, imza, karar, ek, ad_eksik}}). Dil modelinin ara sonuçları
    yazılmaz. Yeni çalışmada imzası tutan kolon dil modeline gitmeden
    onaylı gelir; girdisi değişen yeniden yazılır. Yarım kalan Kolon
    Kartları'nın onaylanan kolonları da gelir.
  - Taslak (onaylanmamış kart hâli) tutulmaz; `/kontrol_taslak` yazmadan
    döner.
  - Kod kaydı içeride eski biçimde görür (`adimlar`, `depo`); okurken
    `_icten`, yazarken `_diske` çevirir. Eski klasör
    (`KONTROL_GECMISI/<sha>.json`) varsa ve tek dosya yoksa kayıtlar bir
    kez tek dosyaya taşınır (taslaklar ve ara sonuçlar düşer); klasör
    silinmez. Yazmalar arka planda, 1 sn içinde birleşir.
  - **"Önceki Onaylı Kontrol Uygulansın"** seçilince seçenek açıklaması
    neyin onaylı ve yarım olduğunu yazar ("Dönem Bilgisi ve Ad Parçaları
    onaylı; Kolon Kartları içinde 340 / 512 kolon onaylı"). Her alt adım
    ilk girişte kaydı dener:
    - Onaylı karar adımın kendi denetiminden yan etkisiz geçerse
      (`_donem_karari_isle`, `_parca_karari_isle`, `_kolon_ad_karari_isle`;
      dil modeli işi başlatılmaz) adım sorulmadan onaylanır; sohbette
      "Önceki onaylı karar uygulandı. ..." yazar ve altında **uygulanan
      kararların kartı kilitli (salt okunur) görünür** (`onceki_karti`:
      Dönem Bilgisi, Ad Parçaları ve Kolon Adları `karar_sonrasi_alan`
      ile kararlı hâliyle; Kolon Kartları satırlarını `/aciklama_alani`
      ile çeker; Kolon Kartları atlandıysa kart yok). Canlı akışta kart
      `tamamlananlar` içinde (`secim_alani`, `onceki: true`) gelir ve
      kilitli çizilir; yenilemede `onceki_gecmisini_tazele` geçmişteki
      özet satırına kartı ekler (kayıtlı transkript değişmez). Dönem'de ayrıca önceki
      kararda olmayan tablo kalıbı ya da artık adlarda olmayan kalıp
      olmamalı; Ad Parçaları'nda önceki kararda olmayan parça olmamalı;
      Kolon Adları'nda her ailenin yeni adları onaydakiyle aynı olmalı;
      Kolon Kartları'nda adım onaylanmış ve bütün kolonlar hâlâ onaylı
      olmalı (girdisi değişen kolonun onayı düşer).
    - Geçmezse kart önceki kararlarla dolu açılır, notta neden yazar
      ("Önceki onaylı karar kendiliğinden uygulanamadı: önceki kararda
      olmayan 1 parça var (MAX). ..."). Kolon Kartları'nda girdisi aynı
      kalan kolonlar yeniden yazılmaz, onayları gelir ("N / M kolon
      onaylı").
    - Deneme alt adım başına bir kez: geri dönüşte kart normal açılır.
      01.2.4'te yeniden seçim yapılınca baştan denenir.
    - Kayıt her durumda tutulur ("adım adım" seçilse de); Dönem'de satır
      Kaydet'leri ayrıca hafızada durur.
- **Yazılışta olmayan yön bilgisi (01.2.4.1, 01.2.4.4, hafıza, 01.2.3):**
  Kalıbın 01.2.4.1'de onaylanan anlamı bu veri setindeki gerçek anlamdır
  ("<N>D" = "son <N> gün"); ama "30D" yazılışı yalnız "30 gün" der. Adın
  bu bilgiyi taşıması 01.2.4.4'teki yeni yazılışla olur (L30D).
  - Yön sözcükleri (`YON_KELIMELERI`): son, önce, önceki, öncesi, geçmiş
    (geri); sonra, sonraki, sonrası, gelecek (ileri). Yalnız sayılı kalıplara
    bakılır ([sayı]D gibi): sayısız kalıpta (TMSNCLST "son işlemden bu yana
    geçen süre", MONTH) "son", "ilk" adın kendi harflerindedir (LST, FRST).
    Kalıp o yönü taşıyan
    bir harf öbeğiyle başlıyorsa (L<N>D) eksik sayılmaz. Harfler hafızadaki
    (kalıp, anlam, yeni yazılış) üçlülerinden öğrenilir (`yon_harfleri`);
    örnek yoksa geri L, ileri N (`YON_VARSAYILAN_HARF`).
  - 01.2.4.1 satırında, anlam yazıldıkça: "Yazılışta yok: «son». [sayı]D
    yazılışı bunu söylemiyor; … 01.2.4.4 Kolon Adları'nda yeni adda
    yazılışı belirleyin (öneri: L[sayı]D)." Hafızada genel anlamı ya da
    başka veri setindeki anlamı varsa: "Hafıza: yazılışın kendi anlamı
    «[sayı] gün» (yön belirtmez); X veri setinde «son [sayı] gün» anlamında
    kullanıldı."
  - 01.2.4.4 Dönem Yazılışları: yazılış boşsa (kullanıcı ya da hafıza
    vermediyse) öneri dolu gelir (`yazilis_onerisi`; "Önerildi: …"). Yeni
    yazılış da yönü taşımıyorsa satırda uyarı ve «Öneriyi Yaz», başlıkta
    sayı. Uyarı onayı engellemez.
  - Hafıza (`donem_yon_hafizaya`, 01.2.4.4 onayında): yeni yazılış kendi
    kalıbı olarak aynı anlam ve türle (L<N>D = "son <N> gün"; hafızada
    başka anlamla varsa üstüne yazılmaz); eski kalıba `genel_anlam` (yön
    sözcükleri çıkarılmış: "<N> gün") ve `veri_seti_anlamlari` ({veri seti:
    anlam}) yazılır. Eski kalıbın `anlam`ı değişmez.
  - 01.2.3 (`kolon_donem_parcalari`): bu çalışmanın 01.2.4.1 onayı varsa
    hepsi kesin. Hafızadan gelen ve yönü yazılışında olmayan kalıp kesin
    değil, "DÖNEM PARÇALARI (dikkat)" bloğunda genel anlamıyla gider
    ("…; uymuyorsa yazılışın kendi anlamını kullan: 3 gün").
- **01.2.4.1 Dönem Bilgisi, kart:** başlığın altında tek satır özet
  ("6 kalıp (3 pencere, 1 zaman noktası) · 2 yorumlanıyor · 4 aday")
  ve yanında "i": yönerge ile sütun açıklamaları orada. Altında üç
  sekme (sayılarıyla): Kalıplar (tablo), Adaylar ve Tüm Parçalar. Adaylar'da kolon
  adlarında bulunup tabloda olmayan BÜTÜN sayılı kalıplar durur (KALIP /
  ADLARDA GEÇEN / OLASILIK / DİL MODELİ); hiçbiri gizlenmez. Olasılık
  rozeti: Orta (dil modeli zaman bilgisi dedi ama emin değil; nedeni
  DİL MODELİ sütununda), Yorumlanmadı (dil modeli bakamadı),
  Düşük (dil modeli zaman bilgisi değil dedi; DİL MODELİ sütununda nedeni,
  ör. "Önceki eşit süreli döneme göre karşılaştırma"). Sıra: olasılık,
  sonra kolon sayısı; üstte süzgeç çipleri (Tümü, Orta, Yorumlanmadı,
  Düşük, sayılarıyla). "Tabloya Al" satırı Kalıplar'a taşır ve o sekmeye
  geçer; Kalıplar'da yeniden Çıkar denen aday Adaylar'a döner. Olasılık
  yalnız dil modelinin kararı ve saydığı örnek tanımlardan gelir
  (uydurma yüzde yok; satırda `olasilik`: yuksek, orta, bakilmadi,
  dusuk).
  - **Tüm Parçalar (üçüncü sekme):** kolon adlarındaki BÜTÜN parçalar
    (yalnız rakamlar hariç; sayılı parçalar ve `P_NN` ikilileri dahil),
    kolon sayısına göre sıralı, arama kutusu ve süzgeç çipleri (Tümü,
    Kalıplarda, Kalıplarda Olmayan), sayfa başına 150 satır ("Daha fazla
    göster"). Sütunlar: PARÇA / KOLON / ÖRNEK KOLON / DURUM / düğme. Durum:
    Kalıp (tablodaki bir kalıbın kendisi), Kalıp değeri (tablodaki bir
    kalıbın değeri), Dönem değil (değer gruptan çıkarılmış), Adaylarda.
    Tek düğme: kalıplardaysa "Kalıplardan Çıkar" (kalıbın kendisiyse satır
    çıkar; bir grubun değeriyse yalnız o değer Dönem Değil olur, grupta
    son değerse satır çıkar), değilse "Kalıplara Al" (Adaylar'daki kalıbı
    tabloya alır; dönem değil işaretli değeri gruba geri alır; hiçbir
    kalıba uymayan parçayı kendisi olarak elle ekler).
  - **Gruplar (kendiliğinden):** yalnız sayıları farklı parçalar bir grup
    (`donem.parca_gruplari`). Sabit genişlik: gruptaki bir sayı başta
    sıfırla yazılıyorsa (00, 06) basamak sayısı anlamlıdır; grup basamak
    sayısına göre bölünür ve kalıbı tam basamaklı yer tutucuyla yazılır
    (H00, H06, H12, H18 → `H<N2>`, ekranda "H[2 haneli sayı]"; H000 ayrı,
    `H<N3>`; H00_06, H06_12 → `H<N2>_<N2>`). Başta sıfır yoksa basamak
    sayısı önemsiz (3D, 7D, 30D → `<N>D`; M3, M12 → `M<N>`). İki ya da daha
    çok üyeli grup Tüm Parçalar'da başlık satırı (grubun kalıbı, "grup · N
    parça", kesin kolon sayısı: üyelerin geçtiği farklı kolonlar,
    `grup_kolon`, üyeler, durum) ve altında üyeleri olarak durur; grup
    aramaya ya da süzgece bir üyesi uyarsa görünür, sayfada bölünmez.
    - Grubu ya da bir üyesini "Kalıplara Al": grup tek satır olarak
      alınır (grubun kalıbı, değerleri bütün üyeler; anlamını dil modeli
      yazar). Üyelerin hepsi tek bir adayın değeriyse o aday tabloya
      alınır.
    - Ayrı satırda kalan aynı grup parçaları (elle yazıldı, hafızadan
      geldi) ve grubun kalıbı tablodayken ayrı satırdaki bir parçası
      kendiliğinden grupta birleşir (`otoGrupla`); altta hangi parçaların
      birleştiği yazar. Ayrı satırların yazılı anlamları değerlerin Kendi
      Anlamı olur (kalıbın anlamından çıkanla aynıysa Kalıba Uyar); en çok
      seçilen tür grubun türü olur.
    - **Ayır:** yer tutuculu satırda (grup ya da sistemin bulduğu aile)
      dönem sayılan iki ya da daha çok değer varsa "Ayır" düğmesi.
      Değerler kendi satırlarına ayrılır (anlamı kendi anlamı ya da
      kalıbın anlamından çıkan, tür satırın türü); satır tablodan kalkar
      (sistemin bulduğu kalıp Çıkarılanlar'a geçer). Ayrılan grup
      kendiliğinden yeniden birleşmez: Kalıplar'da ayrı satırları yan
      yana, üstlerinde "[grup] grubu ayrıldı · Grup Olarak Al" başlığı;
      Tüm Parçalar'da grup "Ayrıldı" ve "Grup Olarak Al", üyeler tek tek
      alınıp çıkarılır. "Grup Olarak Al" yeniden birleştirir. Ayrılan
      gruplar onayla tablonun dönem kararına (`ayrik`) yazılır; yeni
      çalışmada da ayrık gelir.
    - "Grubu Kalıplardan Çıkar": grubun kalıbı tablodaysa ya da bütün
      üyeler kalıplardaysa; grup satırı ve ayrı satırlar çıkar, başka bir
      kalıbın değeri olan üye o kalıpta Dönem Değil olur.
    - Gruptan eklenen satırın kalıbı yazılmaz, etiket olarak durur; kalıbı
      bir grubun kalıbı olan elle satır yoklamayla ya da kayıttan gelse de
      etiket olur ("H[2 haneli sayı]", kutuda "H<N2>" görünmez).
  - **Anlamı dil modeli yazar:** tablodaki bir satırın anlamı boşsa
    (tabloya alındı, Tüm Parçalar'dan eklendi, elle kalıp yazıldı) kart
    `/donem_anlam` ile dil modeline yazdırır (`akis_faz01.donem_anlam_oner`,
    `donem.tek_kalip`: kalıbın adlardaki değerleri ve örnek tanımlar;
    `llm.donem_yorumla(..., zorunlu_anlam=True)`: "dönem değil" bulsa bile
    anlam yazar). Hafızada anlamı olan kalıbın anlamı hafızadan gelir. Satırın
    üstünde "Dil modeli anlamı yazıyor", gelince etiket kalkar. Gelen anlam yalnız kutu hâlâ boşsa yazılır; tür
    kullanıcı değiştirmediyse dil modelininki olur. Kullanıcı anlamı silip
    boş bırakırsa 8 saniye bekler ("Anlam boş: birkaç saniye içinde dil
    modeli yazacak"); o sürede yazmaya başlarsa vazgeçilir. Elle kalıpta
    kalıp yazılıp 1,5 saniye durulunca anlam boşsa yazdırılır. Dil modeli
    yazamazsa satırda nedeni ve "Yeniden dene". Aynı anda en çok 3 istek.
    Çalışma ve oturum dosyası değişmez; anlam onayla kaydedilir.
  - **Tek tek kaydet:** her satırda "Kayıt" sütununda Kaydet (Çıkar'ın
    üstünde). Satırı onayı beklemeden hafızaya yazar (`/donem_kaydet`,
    `akis_faz01.donem_kaydet`: anlam, tür, hariç ikililer, değer
    anlamları, dönem olmayan değerler; anlam boşsa ya da yer tutucusu
    geçersizse kaydetmez). Kaydedilen satırın etiketi yeşil "Kaydedildi",
    düğmesi "Kaydı Geri Al"; satırda bir şey değişince yeniden "Kaydet"
    olur. Hafızadan gelip dokunulmamış satır kaydedilmiş sayılır
    (çizimde düzenleme kaydına kendiliğinden giren ayrılan değerler
    dokunma sayılmaz).
  - **Kaydı Geri Al:** bu kartta kaydedilen satırda hafıza kaydetmeden
    önceki hâline döner (`/donem_kayit_geri`, `akis_faz01.donem_kayit_geri`;
    Kaydet'in döndürdüğü önceki kayıt yazılır, hafızada yoktuysa kalıp
    silinir; karttaki ilk kayıttan önceki hâl). Hafızadan gelip bu kartta
    kaydedilmemiş satırda hafızaya dokunulmaz, satır yeniden açılır. İki
    durumda da satır kaydedilmemiş sayılır.
  - **Hepsini Kabul Et · N:** "+ Dönem Kalıbı Ekle"nin yanında;
    kaydedilmemiş bütün satırlar sırayla kaydedilir (yakın anlamlar
    yeniden yazdırılmaz). Kaydedilemeyenler nedeniyle yazılır.
    Çalışmanın dönem bilgisi yine "Dönem Bilgisini Onayla" ile yazılır.
    Onay için tablodaki her satır kaydedilmiş olmalı: kaydedilmemiş satır
    kaldıkça düğme kapalı, altında "N satır kaydedilmedi: onaylamadan önce
    her satırı «Kaydet» ile kaydedin ya da satırı çıkarın." Kaydedilen
    satır hafızaya yazıldığı için kart yeniden kurulunca "Hafızadan" gelir
    ve kaydedilmiş sayılır. Kart dışında yazarak verilen onayda bu
    denetim yok.
  - **Yakın anlamlar yeniden yazılır:** bir satır kaydedilince
    kaydedilmemiş satırlardan anlamı ona yakın olanlar dil modeline
    yeniden yazdırılır (etiket "Kaydedilen bir anlama yakın: dil modeli
    yeniden yazıyor"). Yakın: iki anlamın kelimelerinin (sayı yer
    tutucusu "#" kelimesi sayılır, kaç kez geçtiği de; rakamlar ve dolgu
    sözcükler sayılmaz) ortak oranı (çoklu küme: ortak / birleşim) %60 ve üstü
    (`ANLAM_YAKIN_ESIGI`); biri öbürünün içinde diye yakın sayılmaz ("gün"
    ile "[sayı] gün boyunca", "saat [sayı]:00" ile "saat [sayı]:00 ile saat
    [sayı]:00 arası" yakın değil). Dil modeline
    kaydedilmiş anlamlar bağlam olarak gider ("bunlarla aynı ya da çok
    yakın anlam verme"; `llm.donem_yorumla(..., kayitli=...)`; bu durumda
    hafıza atlanır). Yeni anlamın altında "Önceki: ... · Geri Al".
    Kaydedilmemiş bir satır kaydedilmiş bir anlama yakın kalırsa anlamın
    altında uyarı durur: hangi kalıbın hangi anlamına benzediği, ne
    yapılacağı (farklıysa bu satırın anlam kutusunu farkı gösterecek
    biçimde düzelt, aynıysa birini çıkar) ve "Farklılar, Uyarıyı Kaldır"
    (o ikili için uyarı bu kartta bir daha çıkmaz). Boş
    anlamı yazdırırken de kaydedilmiş anlamlar bağlam olarak gider. Yalnız sayılı kalıplar burada: rakamsız parçaların
  taraması, komşu adaylar ve hafızadaki rakamsız dönem kayıtları bu
  adımdan kalktı (Ad Parçaları'nda gelir).
  - **[sayı]:** kalıpta ve anlamda sayı yer tutucusu ekranda "[sayı]"
    yazar ("[sayı]D", "[sayı] gün boyunca"). İçeride yer tutucu olarak
    saklanır (app.js `donemAnlamGoster` / `donemAnlamIc`: k'inci [sayı]
    kalıbın k'inci yer tutucusu olur); hafıza ve Kolon Kartları aynı
    kalır. Sayısız kalıpta [sayı] yazılırsa satır "Kontrol edin" olur.
  - **Durum etiketi:** satırlar renksiz; anlam kutusunun üstünde tek
    satır, yalnız durum varsa: "Kaydedildi", "Düzenlendi", "Kontrol edin"
    ya da "Anlam boş" (amber), "Dil modeli yorumluyor" / "anlamı
    yazıyor" / "yazamadı". Önerinin kaynağı (dil modeli, kanıt sayısı,
    hafıza, elle) yazılmaz.
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
    kalır, yorumlanmayanlar Adaylar'a düşer, kartta "Dil modelini
    durdurdunuz" notu çıkar. Süren çağrının sonradan gelen cevabı
    yazılmaz.
- **Kalıp yakalama (`donem.kaliplar`, `parca_listesi`):** sayı içeren
  parçalar kalıba çevrilir (`H00_06` → `H<NN>_<NN>`, `L3M` → `L<N>M`).
  Yer tutucular: `<N>` herhangi bir sayı, `<NN>` en az iki basamaklı,
  `<N2>`, `<N3>` tam o kadar basamaklı sayı (`H<N2>`: H00, H06; H000
  uymaz). Anlamda `<N>` ve `<N2>` için "N", `<NN>` için "NN" yazılır
  (`donem.kalip_deseni`, `deger_anlami`, `yer_tutucu_hatasi`; ön yüzde
  aynı kurallar). Desen sırasında tam basamaklı kalıp önce eşleşir.
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
  - Pencere: sayı bir aralık; veri o aralıktaki bütün zamanlardan
    toplanır (H00_06: 00:00 ile 06:00 arası; L30D: bugünden önceki 1. ile
    30. gün arası). Sayı ve birimden oluşan kalıpta ([sayı]D, D[sayı]) bu
    seçim yoktur; aralık mı tek gün mü olduğu kolonun anlam türünden gelir
    (bkz. "Dönem anlam türleri"). Aynı metin 01.2.4.1 yönergesinde
    (`DONEM_YONERGE`) ve Değişken Listesi'nin dönem bölümünün i balonunda.
  - Zaman Noktası: sayı belirli bir an ya da sıra (M3: yılın 3. ayı ya da
    3 ay önceki ay).
  - Zaman Birimi: sayısız zaman birimi (DAY: gün).
  - Zaman Ölçüsü: değerin kendisi bir süre (TMSNCFRST).
  Kararda `zaman_tur`, durumda `durum["donem_turleri"]` ({kalıp: tür}),
  hafızada `donem_tur`.
- **Hafızadaki kalıplar (önceden kaydedilen ya da onaylanan):** adlarda
  geçen her hafıza kalıbı satır olarak gelir (`donem.kaliplar`, `ek`):
  tek parça, `<P>_<NN>` ikilisi, yan yana iki dönem parçası (3D_6D →
  `<N>D_<N>D`) ve rakamsız kalıp (TMSNCFRST; hafızada değilse Ad
  Parçaları'nda kalır). Bir kolonda hafıza kalıbının kapsadığı parçalar
  kendiliğinden bulunan kalıplardan düşülür (H<N2> kayıtlıyken H00 ve
  H06 `<N>H` ailesinde ikinci kez sayılmaz; 3D_6D'deki 3D `<N>D`
  satırına girmez). Hafıza kalıbı da dil modeline gider, hafızadaki
  anlamla (`hafiza_anlam`, "HAFIZADAKİ ANLAM"): dil modeli yeni anlam
  kurmaz, örnek tanımlardan kaçının bu anlamla uyuştuğunu sayar
  (`donem.ISTEM_SURUMU` 8). Uyuşuyorsa (ya da dil modeli bakamadıysa,
  durdurulduysa) satır tabloya hafızadaki anlamıyla, kaydedilmiş olarak
  gelir. Örneklerin %60'ından azı uyuşuyorsa ya da dil modeli zaman
  bilgisi değil diyorsa Adaylar'a düşer (Orta), nedeni yazar ("Hafızadaki
  anlamla örnek tanımlardan yalnız 0 / 3 tanesi uyuşuyor; anlamı kontrol
  edin."). Bakılana kadar satırda "Dil modeli yorumluyor". Bu çalışmada
  ya da tablonun son kararında verilen karar her zaman geçerlidir.
- **Koşullu anlam** (01.2.4.1; `donem.kosullu_anlam`,
  `hafiza_kosul` / `hafizaya_kosul_yaz`, `kisaltma.donem_kosul_*`): bir
  kalıbın, kolon adında belirli bir parça geçtiğinde kullanılan anlamı.
  Ör. [sayı 1]D_[sayı 2]D varsayılan "[sayı 1] gün önce ile [sayı 2] gün
  önce arası", adda RATIO geçerse "son [sayı 1] gün ile son [sayı 2]
  gün".

  **Koşulları Düzenle** ("Değerleri Düzenle"nin hemen yanında, özetiyle:
  "6 parça · 1 kendi anlamı"). Basınca değer paneliyle aynı düzende ve
  satırın altında "[kalıp] koşulları" paneli açılır (iki panel birlikte
  açıksa üst üste). Panelde:
  - arama kutusu (açılınca odakta);
  - tablo: Parça, Kolon (sayı ve i balonu), Anlam, Durum.

  Durum bölmeli düğmeyle seçilir:
  - **Kalıba Uyar:** kutu kalıbın anlamını gösterir, yazılmaz.
  - **Kendi Anlamı:** kutu kalıbın anlamıyla dolup odaklanır. Altında
    sayı ekle düğmeleri ve örnek ("Ör. 3D_7D → son 3 gün ile son 7 gün")
    ya da hata (yer tutucu kalıbın anlamı gibi denetlenir; geçersizken
    onay kapalı) yazar. Boş bırakılıp çıkılırsa parça Kalıba Uyar'a döner.

  Satırlar: kendi anlamı olanlar önce, sonra çok geçen önce. Adaylar
  `_kosul_adaylari`: kalıbın geçtiği adlardaki harf parçaları ([parça,
  kolon sayısı, örnek değer, örnekler]; en çok 300 parça, örnek kolonlar
  yalnız ilk 60 parçada). Hafızadan gelen ama adlarda bu kalıpla geçmeyen
  parça da listede durur (kolon 0, "Bu parça bu kalıpla birlikte adlarda
  geçmiyor."). Tablo ilk 50 satırı gösterir, gerisi aramayla bulunur.

  i balonunda parçanın ve kalıbın birlikte geçtiği en çok 3 kolon
  (`_kosul_ornekleri`: önce sözlük açıklaması olan ve kalıp değeri farklı
  olanlar), her birinin açıklaması ve o kolonun dönemi (kendi anlamı
  varsa onunla, yoksa kalıbın anlamıyla) yazar. Düğme, adaylar ve koşul
  yoksa gizlidir.

  **Öneriler** (`donem_kosul_onerisi`, `/donem_kosul_oneri`;
  `llm.donem_kosul_denetle`, `SISTEM_DONEM_KOSUL_DENETIM`). Önce koşul
  eklemek gerekmez. Bütün açıklamalarla karşılaştırılan, kalıbın
  **kaydedilmiş anlamıdır** (`KAYIT_ANLAM`):
  - hafızadan gelen satırda hafızadaki anlam;
  - «Kaydet»te kaydedilen anlam;
  - «Kaydı Geri Al»da önceki kayıt (yoksa silinir).

  Kutudaki kaydedilmemiş yazı kullanılmaz; kutu kaydedilenden farklıysa
  panel "Öneriler kaydedilmiş anlama göre: «…»" diye yazar. Kaydedilmiş
  anlamı olmayan satırda öneri istenmez, panel "önce satırı «Kaydet» ile
  kaydedin" der. **Koşulları Düzenle paneli açılınca başlar**; panel hiç
  açılmayan kalıp için istenmez. Kaydedilmiş anlam değişince (Kaydet,
  Kaydı Geri Al) panel açıksa yeniden istenir; kapalıysa eski öneri
  düşer, panel açılınca istenir.
  1. Kalıbın geçtiği ve sözlükte açıklaması olan BÜTÜN kolonlar (örneklem
     yok; kalıp adda daha geniş bir kalıbın içindeyse o kolon sayılmaz)
     25'lik paketlerle (aynı anda 4) dil modeline gider. Her kolon için
     açıklama kalıbın genel anlamıyla aynı dönemi mi anlatıyor: uyumlu,
     uyumsuz ya da belirsiz. Uyumsuzsa doğru dönem anlamı yer tutucuyla
     istenir.
  2. **Kod doğrular ve parçaya bağlar** (`_kosul_denetim_grupla`):
     - Kolonun önerdiği anlam rakamsız olmalı ve yer tutucuları kalıba
       uymalı; doldurulunca sayıları açıklamada aynı sırayla geçmeli.
     - Bir parça için öneri ancak o parçanın geçtiği kontrol edilmiş
       kolonlardan hiçbiri uyumlu değilse çıkar.
     - Anlam, o kolonlarda en çok önerilen anlamdır ve parçanın bütün
       uyumsuz kolonlarının açıklamasıyla sayı sırasıyla tutmalıdır.
     - Aynı kolon kümesini kapsayan parçalardan biri gösterilir (ötekiler
       "Aynı kolonlarda … de geçiyor" diye yazılır). Başka bir önerinin
       kolonlarının alt kümesi olan parça gösterilmez.
     - Hiçbir parçaya bağlanamayan uyumsuz kolonlar ayrıca sayılır (ilk
       10'u i balonunda; kullanıcı elle baksın).
  3. Panelde durum satırı: hazırlanırken "biten / toplam kolon"; bitince
     kaç kolonun karşılaştırıldığı (uyumlu, uyumsuz, belirsiz), kaç parça
     için öneri olduğu ve bağlanamayanlar; hata olursa «Yeniden Dene».
     Düğmenin özetinde (panel bir kez açıldıktan sonra) "· N öneri" ya da
     "· öneriler hazırlanıyor".
  4. Önerili parça, kendi anlamı olanlardan sonra listenin başında durur.
     Alınmamış öneri, anlam hücresinin altında kesik çerçeveli kutuda
     (`kosOneriSatiri`) şunları yazar:
     - "Öneri: adında RATIO geçen kolonlarda bu kalıp «…» demek.";
     - "Neden:" kaç kolonun açıklaması kaydedilmiş anlamla («…»)
       uyuşmuyor, parça toplam kaç kolonda geçiyor, dil modelinin tek
       cümlesi (yer tutucular `donemNedenGoster` ile "[sayı 1]");
     - somut örnek: "Ör. KOLON: açıklaması «…»; öneriyle «…», şimdiki
       anlamla «…»" (öteki dayanak kolonlar i balonunda);
     - «Öneriyi Al».

     **Öneriyi Al:** önerilen yazı Kendi Anlamı olur, durum Kendi Anlamı
     işaretlenir, kutu odaklanır ve imleç yazının sonunda durur (yazı
     seçili gelmez; yazmaya başlamak öneriyi silmez). Kutunun altında
     "Öneri alındı. Yukarıdaki kutuda yazıyı istediğiniz gibi
     değiştirebilirsiniz." yazar. Kutudaki yazı öneriden farklılaşınca
     "Önerilen yazı: «…»" ve **«Tekrar Öner»** çıkar; basınca kutu
     önerilen yazıya döner. Hiçbir öneri kendiliğinden uygulanmaz.

  Sonuç bellekte, (kalıp, anlam, kontrol edilen kolonlar ve açıklamaları)
  imzasıyla tutulur; aynı istek dil modeline yeniden gitmez. Hata kalır,
  yalnız «Yeniden Dene» ile yeniden başlar. Webapp yeniden başlayınca
  bellek boşalır, öneriler yeniden hazırlanır. Karar ve satır `kosullu`
  ({PARÇA: anlam}, içeride yer tutuculu); satırın kayıt imzasına girer.
  Onayda `durum["donem_kosul"]` ve hafızaya (dosyada kalıp kaydında
  `kosullu_anlamlar`; boş bırakılan kalkar; kalıp hafızadan silinince
  o da silinir). Kolon Kartları'nda (`_aciklama_girdileri`) adında koşul
  parçası geçen kolonun kartı ve dil modeline giden dönem satırı koşullu
  anlamla kurulur (değerin kendi anlamı varsa o önce); kart değişince o
  kolonlar yeniden yazılır. Birden çok koşul tutarsa parça adına göre
  ilki.
- **Sayı ekle düğmeleri** (`donemSayiDugmeleri`): 01.2.4.1'de kalıbın
  anlam kutusunun ve Koşulları Düzenle'de her kendi anlamı kutusunun altında "Sayı ekle:
  [sayı 1] [sayı 2]" (tek sayılı kalıpta [sayı]). Basınca imlecin olduğu
  yere eklenir (kutu odakta değilse sona), önüne ve arkasına gerekirse
  boşluk konur; düğme odağı kutudan almaz. Elle satırda kalıp değişince
  düğmeler yenilenir (`dgCiz`). 01.2.4.4 Dönem Yazılışları'nda da her
  "Yeni Adda" kutusunun altında var; orada boşluksuz eklenir (`bitisik`:
  BTWN_[sayı 1]D_[sayı 2]D). Adlar kutudan çıkınca yeniden kurulur;
  düğmeyle yapılan değişiklik "change" doğurmadığı için kutu değişince
  işaretlenir, çıkışta (`blur`) yazılış geçerliyse önizleme istenir.
- **Yer tutucu harfe bitişikse:** "<N>gün" (ekranda "[sayı 1]gün") da yer
  tutucudur (`donem._YT_ADAY`, `DONEM_YT_ADAY`); harf sınırı yalnız çıplak
  N / NN yazımında aranır. Önceden köşeli biçim harfe bitişince içindeki
  N tek başına yakalanıyor, örnek "son <3>gün" çıkıyordu.
- **Çok sayılı kalıpta numaralı [sayı]:** kalıpta birden çok sayı varsa
  ekranda en baştan numaralı yazılır: kalıp "[sayı 1]D_[sayı 2]D"
  (`donemSayiGoster`; tam basamaklıda "[2 haneli sayı 1]"; aile
  yazılışları ayrı ayrı), anlamda düz yer tutucular sırayla "[sayı 1]",
  "[sayı 2]" (`donemAnlamGoster`), yeni adda yazılışta da
  (`donemAdGoster`, 01.2.4.4 Dönem Yazılışları), Kolon Kartları'nda aile
  adlarında (`ackAileAdi`: TXN_[sayı 1]D_[sayı 2]D_RATIO) ve sunucu
  mesajlarında (`akis_faz01._donem_kalip_gorunur`). Tek sayılı kalıpta
  "[sayı]" kalır. İçeride değişiklik yok: numaralar 1, 2, ... sırayla ve
  birer kez geçiyorsa düz yer tutucuya döner (`donemDuzYerTutucu`;
  `donemAnlamIc`, `donemAdIc`), hafızadaki kayıt aynı kalır, satır
  düzenlenmiş sayılmaz. Yer tutucu uyarısında kullanılabilenler ekrandaki
  gibi yazılır ([sayı 1], [sayı 2]; içerideki N, NN yazılmaz).
- **Yeni adda yazılış 01.2.4.1'de değil:** kalıbın yeni addaki yazılışı
  01.2.4.4 Kolon Adları'nda "Dönem Yazılışları" panelinde verilir (adlar
  orada kurulur; 01.2.4.1'de ad değiştiriyormuş gibi görünen kutu yok).
  01.2.4.1 kararı, Kaydet ve Kaydı Geri Al hafızadaki yazılışa (`donem_ad`)
  dokunmaz; eski kararlardaki `ad_yazilis` yok sayılır.
- **Dönem anlam türleri (birimli kalıplar, `fe_agent/donem_tur.py`):**
  sayı + zaman birimi kalıplarının (`<N>D`, `D<N>`, `<N>_D`, `D_<N>`;
  `donem.aile_adi` dolu olanlar) anlamı kolondan kolona değişir. 3D tek
  başına belirsizdir: geçmişe mi geleceğe mi (ya da ikisine mi) bakar,
  aralığın tamamını mı yoksa yalnız uçtaki günü mü kapsar, yoksa takvimde
  bir yeri mi gösterir (yılın 3. ayı)? Her tür bunu iki eksenle
  kesinleştirir: **yön** (geçmiş, gelecek, iki yönlü, takvim, takvimden
  bugüne, yönsüz)
  ve **biçim** (pencere: aralığın tamamı; nokta: yalnız uçtaki gün;
  yönsüzde uzunluk). Sabit türler (3D için; bugün referans tarihidir,
  pencereye dahil değildir):

  | Tür | Yön | Biçim | Anlam | Kapsam | Varsayılan yazılış |
  |---|---|---|---|---|---|
  | Son | geçmiş | pencere | son 3 gün | bugünden önceki 1., 2., 3. gün | L3D |
  | Önce | geçmiş | nokta | 3 gün önce | yalnız 3 gün öncesi | B3D |
  | Sonraki | gelecek | pencere | sonraki 3 gün | bugünden sonraki 1., 2., 3. gün | N3D |
  | Sonra | gelecek | nokta | 3 gün sonra | yalnız 3 gün sonrası | A3D |
  | Çevre | iki yönlü | pencere | 3 gün öncesi ve sonrası | 3 gün öncesinden 3 gün sonrasına | PM3D |
  | Takvim | takvim | nokta | ayın 3. günü (3M: yılın 3. ayı) | bugünden bağımsız; yalnız ayın 3. günü | C3D |
  | Beri | takvimden bugüne | pencere | ayın 3. gününden beri (Y2023: 2023 yılından beri) | ayın 3. gününden bugüne (Y2023: 1 Ocak 2023 tarihinden bugüne) | S3D |
  | Süre | yönsüz | uzunluk | 3 gün | tarih aralığı değil, bir sürenin uzunluğu | aynen |

  Kapsam metni `kapsam_metni` (sunucu) ve `kapsamYaz` (ekran) ile aynı
  kurulur; 3'e kadar günler tek tek, büyük sayıda "1. ile 30. gün arası".
  Takvim anlamı birimden (`takvim_anlami`, ekranda `takvimAnlami`): gün →
  ayın N. günü, hafta → yılın N. haftası, ay → yılın N. ayı, çeyrek →
  yılın N. çeyreği, saat → günün N. saati, dakika → saatin N. dakikası,
  yıl → N yılı. **Yılda takvim yalnız dört haneli takvim yılıdır**
  (`takvim_gecerli`, `TAKVIM_YIL_EN_AZ` 1000): Y2023 → "2023 yılı",
  kapsam "bugünden bağımsız; yalnız 2023 yılı (1 Ocak ile 31 Aralık
  arası)"; tanımdan "2023 yılında", "2023 yılı", "2023 senesinde",
  "2023'te", "2023'teki", "2023'ten", "2023de" okunur; "2023'ten beri,
  itibaren, bu yana" **Beri** türüdür; "2023'ten sonra, önce" belirsiz
  kalır.
  Y3 gibi küçük
  sayıda Takvim seçeneği çıkmaz (01.2.4.3 seçenekleri, dil modelinin
  takvim işareti geçersiz sayılır); "ilişkinin 3. yılı" takvim sayılmaz.
  Beri anlamı `beri_anlami` (ekranda `beriAnlami`), kapsam takvimdeki
  yerin başından bugüne. Takvim ve Beri yönlü türler `TAKVIM_YONLERI`;
  yıl biriminde ikisi de dört haneli yıl ister. Kullanıcı türünde
  Takvimden bugüne yönünde biçim sabit (pencere; `sabit_bicim`), seçim
  kutusu kapalı. Kullanıcı türünde Takvim yönü de seçilebilir; pencere
  biçiminde kapsam "bugünden bağımsız; ayın 1. ile N. günü arası".
  Kalıbın anlamı takvim olarak gelirse ("yılın <N>. ayı", dil modelinden
  ya da eski hafızadan) birime döner ("<N> ay", `birim_anlami`); M<N>
  kalıbının yazılışı birimli olmasın diye C_M<N>.
  Önek bitişince yazılış yine birimli kalıp olursa (D<N> → LD<N>) alt
  çizgiyle ayrılır (L_D<N>); elle yazılan yazılış birimli kalıpsa
  (sonraki çalışmada yine belirsiz olur) hata verir
  (`yazilis_birimli_hatasi`).
  - **01.2.4.1:** kalıbın anlamı birimdir ("[sayı] gün"; anlamdaki son,
    önce, sonraki, önümüzdeki, öncesi ve sonrası, kadar, boyunca gibi
    sözcükler atılır, `birim_anlami`). Birimli satırda kalıp düzeyindeki
    zaman türü seçimi (Pencere, Zaman Noktası) yoktur; "Zaman türü kolona
    göre" yazar, özetteki tür sayımında ve Değişken Listesi'nin dönem
    bölümünde "türü kolona göre" diye geçer.
    Altında **Anlam türleri** tablosu: Tür, Anlam, Kapsam, Kolon. "Tür
    Ekle" ile kullanıcı tür ekler: ad, anlam ([sayı] olmalı), Yön ve Biçim
    (yönsüzde biçim seçilmez); seçince kapsam önizlenir, eksikse hata
    yazar (formdakiler silinmez). Önceki sürümde eklenip yönü ya da biçimi
    olmayan türde satırda iki seçim kutusu çıkar; seçilmeden onay
    sunucuda hata verir (`_ozel_tur_temizle`). Her türün kaç kolonda
    geçtiğini kod bütün tanımlarda sayar (`_donem_tur_sayimi`, örnekleme
    yok; i balonunda örnek kolonlar).
  - **Tanımdan tür (kod, `metinden_tur`):**
    son: "son 3 gün", "geçmiş 3 gün", "geçen 3 gün", "önceki 3 gün",
    "3 gün öncesine kadar", "3 yıldan beri", "3 aydan bu yana", "3 yıldır", "3 aydır işlem
    yapmayan", cümle sonunda da ("Kredi 36 aydır."); önünde vade ya da
    süre olan ("Vadesi 36 aydır.") sayılmaz; önce: "3 gün önce", "3 gün önceki",
    "3 gün öncesi"; sonraki: "sonraki 3 gün", "önümüzdeki 3 gün",
    "gelecek 3 gün", "3 gün sonrasına kadar"; sonra: "3 gün sonra",
    "3 gün sonraki", "3 gün sonrası"; çevre: "3 gün öncesi ve sonrası",
    "3 gün önce ve sonra", "±3 gün"; takvim: sıra sayısı ve birim
    ("yılın 3. ayı", "ayın 15. günü", "3. ay", "3'üncü ay", "üçüncü ay";
    bulunan yer metinden çıkarılır ki "geçen yılın 3. ayı"ndaki "geçen"
    yön sayılmasın); beri: takvimdeki yer + ayrılma eki + beri, itibaren,
    bu yana ("2023'ten beri", "2023 yılından itibaren", "yılın 3. ayından
    bu yana", "ayın 15. gününden beri"; takvimden önce bakılır);
    süre: sayıdan önce "süre" sözcüğü
    ("vade süresi 3 gün"). Yön söylemeyen "3 gün boyunca", "3 günlük",
    "3 gün içinde" belirsizdir, tahminle türe atanmaz. Aynı sayı bir yerde
    türlü bir yerde türsüz geçerse türlü olan; iki farklı tür ya da hiç
    tür yoksa belirsiz.
  - **01.2.4.3:** her kolonda dönemin türü bu sırayla belirlenir
    (`_donem_turu_coz`): kullanıcının seçimi > onaylı açıklamadaki ifade
    (kod) > dil modelinin `donem_turu` alanı > belirsiz. Dil modeli
    kuralı (`SISTEM_ACIKLAMA_DUZEN` "DÖNEM YÖNÜ") altı türü kapsamlarıyla
    yazar; hem yön hem kapsam kaynakta açık değilse "belirsiz" der ve
    açıklamaya yön eklemez. Parça metninde birimli kalıbın zaman türü
    etiketi (zaman penceresi) yazılmaz; seçenekler "son = son 30 gün
    [bugünden önceki 1. ile 30. gün arası]" biçiminde gider. Satırda
    "Dönem: 30D bu kolonda «son 30 gün» (bugünden önceki 1. ile 30. gün
    arası) · Açıklamadan · Değiştir". Belirsiz kolon Cevapsız Soru
    aşamasına girer; sarı kutuda her seçenek bir kart (anlam ve altında
    kapsam) ve "Ailenin dönemi belirsiz öbür kolonlarına da uygula".
    Seçim `/aciklama_islem` `islem: "donem_tur"` ile gider
    (`aciklama_donem_turu`); kolon (ve isteğe göre ailenin dönemi belirsiz,
    aynı yerde aynı kalıbı taşıyan kolonları) "Adındaki 30D bu kolonda
    «son 30 gün» anlamında (bugünden önceki 1. ile 30. gün arası)"
    notuyla yeniden düzenlenir. Kartın Zaman alanı türlü yazılır. Onay
    kaydında `donem_turleri` tutulur. Parça metni değiştiği için açıklama
    imzası değişir: önceki çalışmaların kolonları bir kez yeniden
    düzenlenir.
  - **01.2.4.4 Dönem Yazılışları:** birimli kalıp için kalıp × tür
    satırları (yalnız en az bir kolonda geçen türler; anahtar
    `kalip|tur`); "Anlam" sütununda tür adı, anlamı ve kapsamı. Aynı
    yazılış iki türe verilemez (`yazilis_cakismasi`; hata yalnız çakışan
    türün satırında, onayı durdurur). Belirsiz satırı salt okunur: o
    kolonların adında dönem kısmı aynen kalır. Her kolon kendi türünün
    yazılışıyla adlanır (`_kolon_yazilislari`): TXN_OUT_AMT_30D →
    TXN_OUT_AMT_L30D, LOAN_DUE_AMT_30D (30 gün sonra) → LOAN_DUE_AMT_A30D,
    BAL_30D (30 gün önceki) → BAL_B30D, önümüzdeki 30 gün → N30D, 3 gün
    öncesi ve sonrası → PM3D.
  - **Hafıza:** kalıbın anlamı birim; türler `anlam_turleri` alanında
    (`{tur: {ad, anlam, yeni_adda, yon, bicim}}`;
    `kisaltma.donem_anlam_turleri_kaydet`, `None` türü siler). Bir
    yazılış bir kalıpta yalnız tek türe bağlanır: 01.2.4.4 onayında başka
    türe verilen yazılış eski türünden kalkar. Yeni yazılış (L<N>D) kendi
    kalıbı olarak kesin anlamıyla da yazılır (`_donem_tur_yazilis_hafizaya`;
    zaman türü biçimden: nokta → nokta, uzunluk → ölçü, öbürü pencere);
    yazılış başka türden taşındıysa kalıbın eski anlamı da değişir.
    Sonraki çalışmada L30D kesin "son 30 gün", yalın 30D belirsizdir;
    01.2.3 bu yüzden L30D'yi kesin, 30D'yi dikkat bağlamı olarak verir.
    Eski tek anlamlı kayıt (kalıp düzeyindeki `donem_ad`) eski anlamındaki
    yön ifadesinin türüne taşınır (`kalip_turleri`). Kaldırılan kullanıcı
    türü hafızadan da silinir.
  - **Önceki sürümden göç (N harfi):** önceki sürümde "sonra" türünün
    yazılışı N idi ve o tür hem "3 gün sonra" hem "önümüzdeki 3 gün" için
    kullanılıyordu. Biçim alanı olmayan "sonra" kaydındaki N yazılışı
    kullanılmaz (`eski_sonra_mi`); 01.2.4.1 onayında bu yazılış türden
    kalkar ve hafızaya kendi kalıbı olarak yazılmış N<N>D ("<N> gün
    sonra") silinir. Sonraki onayda sonraki N, sonra A yazılışını alır.
  - **Kapsam dışı:** iki parçalı kalıplar (`<N>D_<N>D`), harf + sayı +
    harf kalıpları (L<N>D) ve saat aralıkları kendi anlamını taşır, bu
    kurala girmez.
- **İki parçalı zaman kalıbı:** yan yana iki sayılı dönem parçası
  (3D_6D) Tüm Parçalar'da ikili olarak da yer alır (grubu `<N>D_<N>D`);
  "Kalıplara Al" ile tek satır olur (ör. anlamı "N ile N gün arası", yeni
  adda BTWN_[sayı]D_[sayı]D).
- **Anlamın kaynağı (dil modeli kuralları, `llm._DONEM_ANLAM_KURALLARI`):**
  önce ad, sonra tanımlar. Anlam parçanın yapısından kurulur (D gün, W
  hafta, M ay, Q çeyrek, Y yıl, H saat; sözcük kısaltmaları harflerinden).
  Sözlük tanımları kesin değil, kanıttır: kalıp başına en çok 10 örnek
  tanım (`donem.ORNEK_ADET`) gider; model her tanımın anlamıyla uyuşup
  uyuşmadığını sayar (`kanit`: bakılan, uyan). Adda karşılığı olmayan
  bilgi (ortalama, toplam) anlama yazılmaz, nota yazılır. **Sayı ve zaman
  birimi parçasında** (30D, 3M, D30, 3_M) anlam yalnız birimdir ("N gün");
  son, önce, sonraki, boyunca gibi yön ve kapsam sözcükleri anlama da nota
  da yazılmaz, takvim sırası ("yılın N. ayı") da yazılmaz, bunun için soru
  sorulmaz, tür "pencere" yazılır (yön, kapsam ve takvim kolon
  kartlarında belirlenir; bkz. "Dönem anlam türleri"). Ad
  ile tanımların çoğu çelişirse adın yapısı geçer, çelişki `celiski`de
  yazar. Diğer sayılı parçalarda aralık mı (pencere) an mı (nokta) olduğu
  tanımların çoğundan çıkar; belli değilse soru iki seçeneği de yazar.
  Anlam tür adını tekrar etmez ("N gün", "N gün zaman penceresi" değil).
  Kurallar değişince `donem.ISTEM_SURUMU` artar (şimdi 12) ve kalıplar
  dil modeline bir kez yeniden yorumlatılır.
- **Arka plan işi (`donem.baslat`):** yorum `YORUM_PARCA` (6) kalıplık
  parçalara bölünür; en çok
  `ES_ZAMANLI` (4) çağrı aynı anda çalışır, her parçanın sonucu gelince
  yazılır.
- **Kolon Kartları'na giden dönem parçası** (`_donem_parca_metni`):
  değerin kendi anlamı ya da kalıbın anlamı, yer tutucu değerin sayısıyla
  doldurulmuş olarak ve yanında türü: "3_M: son 3 ay (zaman penceresi)",
  "MONTH: ay (zaman birimi)". Kalıp adı ve yer tutucu (`<N>`, `N`) dil
  modeline gitmez; sözlüğe yazılan açıklama sayıyla yazılır.
  `donem.ISTEM_SURUMU` 7: önbellekteki eski yorumlar yeniden alınır.
  Dil modeli "dönem değil" dediği kalıp için nedenini "not"a tek
  cümleyle yazar (Adaylar'da görünür).
- **Yan yana iki dönem parçası (aday, `tur` "ikili"; `donem.kaliplar`):**
  bir kolon adında iki dönem parçası yan yana geçiyorsa (3D_6D, 7D_14D,
  7D_X2) ikisi birlikte tek kalıp olarak önerilir (`<N>D_<N>D`,
  `<N>D_X<N>`); dil modeli yorumlar ama kendiliğinden tabloya girmez,
  Adaylar'da (Orta) durur; kullanıcı «Tabloya Al» derse girer.
  Hafızada aynı kalıp varsa "hafiza" türüyle gelir ve önerilmez.
- **Değer örnekleri:** "Adlarda Geçen" sütunundaki her değer çipinde
  "i": o değerin geçtiği ilk üç kolon ve sözlük tanımı
  (`kaliplar` `deger_ornek`, satırda `degerler[].ornek`; `DEGER_ORNEK_ADET`).
- **Tüm Parçalar'da iki parçalı değerin parçaları:** tablodaki bir
  kalıbın iki parçalı değerinin içindeki parça (H00_06'daki H00)
  "Kalıp değerinin parçası: H00_06 (H[sayı]_[sayı])" yazar, "Kalıplarda"
  sayılır, düğmesi yoktur (değer Kalıplar'da yönetilir). Adaylardaki
  değerin parçaları "Adaylarda" sayılır.
- **Tabloya giren kalıplar:** hafızadan gelenler ve dil modelinin
  zaman bilgisi olduğunu bulduğu parçalar Kalıplar'a girer; yalnız
  ikililer içinde geçse de (MONTH). Adaylar'a (Orta) düşenler: dil modelinin
  sorusu olanlar, kanıtı zayıf olanlar (en az 2 örnek tanıma bakıp
  uyuşanlar %60'tan az, `DONEM_KANIT_ESIGI`; nedeni "Örnek tanımlardan
  yalnız 1 / 5 tanesi bu anlamla uyuşuyor"), dil modelinin bakmadığı ya
  da İptal ile yorumlanmayan kalıplar ve hafıza ile modelden gelmeyen
  uyarılı parçalar. Dil modelinin dönem değil dediği kalıplar da
  Adaylar'da (Düşük) durur.
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
    kolonlar hariç bütün kolon adlarının parçaları. Burada olmayanlar
    (`parca.zaman_konumlari`): 01.2.4.1'de onaylanan kalıplara uyanlar
    (tek parça ya da yan yana iki parça: H00_06, 3_M, 14D_28D; gruptan
    "dönem değil" diye ayrılan değer kalıba uymaz) ve yalnız rakamdan
    oluşanlar. Dönem diye alınmayan sayılı parça (X2, çıkarılan 30D)
    burada anlam ve türüyle yorumlanır; kolon kartına ve yeni ada da
    buradan girer. Parça başına
    kaç kolonda geçtiği, tanımsız kolon sayısı, en sık yanında duran 3
    parça ve en çok 10 örnek (ad, tanım; listenin başından sonuna eşit
    aralıkla, rastgele değil).
  - **Anlam** (`llm.parca_yorumla`, istem `SISTEM_PARCA`, rol `parca`:
    düşünen model önce): önce parçanın yazılışı ve yaygın kısaltma
    bilgisi, sözlük tanımları kanıt (oylama, `kanit`); `celiski`, `soru`,
    `not`; tür (12): konu, yön, nitelik, ölçü, istatistik,
    karşılaştırma, pencere, nokta, zaman birimi, geçen süre, birim,
    diğer. Arka planda 12 parçalık çağrılar, en çok 4 aynı anda; İptal
    (`/parca_iptal`) gelenleri tutar. Cevap `{"parcalar": [...]}`:
    `Orkestra.json_cagir(..., anahtar="parcalar")` ile okunur (öbür
    işler `kolonlar`); istem sürümü `parca.ISTEM_SURUMU` 2. Satırda
    önerinin kaynağı (dil modeli, kanıt sayısı, hafıza) yazılmaz; anlamın
    üstünde yalnız durum (Düzenlendi, Kontrol edin, Anlamı siz yazın,
    yorumluyor).
  - **Hafıza dosyasının biçimi** (`kisaltma._diske`, `_diskten`,
    `_dosya_metni`): elle okunup düzeltilebilsin diye her dönem kalıbı ve
    her ad parçası tek kayıtta: `ad_standardi` (yer sırası),
    `donem_kaliplari` {kalıp: {anlam, tur, yeni_adda, deger_anlamlari,
    haric_ikililer, gruptan_ayrilan {değer: {anlam, donem_degil}},
    ayri_yazilis, degerlerine_ayrildi}}, `ad_parcalari` {PARÇA: {anlam, tur, standart}}
    (standart yazılmazsa parçanın kendisi), `ayni_parcalar` ve
    `farkli_parcalar` (her metin bir çift: "ADT, CNT" ADT ile CNT aynı;
    çiftler birbirinden bağımsız). Açıklama ve sürüm alanı yok; yeni
    biçim bu anahtarlardan biri varsa tanınır. Boş alan yazılmaz; metin
    listeleri ve kısa kayıtlar tek satırda. Kod içeride eski biçimle
    çalışır: okurken `_diskten`, yazarken `_diske` çevirir (bütün
    yazmalar `_dosya_yaz`'dan). Eski biçimdeki dosya okunur, ilk yazmada
    yeni biçime geçer; tanınmayan anahtar korunur.
  - **Hafıza** (iç biçim: `parcalar` {PARÇA: {anlam, tür,
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
    ve Onay. **Ek türü** (`ek`): tek başına bilgi taşımayan, arkasındaki
    parçaya bağlanan ek (PER, BY). Anlamda bir kez [parça] yazılır, o
    parçanın yerini tutar: PER "[parça]lık", BY "[parça] tarafından"
    (`parca.ek_hatasi`; başka türün anlamında [parça] olamaz). Kolon
    kartında ek kendi alanını almaz, arkasındaki parçanın anlamıyla
    birleşip onun alanına girer (`parca.ek_uygula`; bitişik ekin ünlüsü ve
    baştaki d/t son sözcüğe uyar: gün → günlük, ay → aylık, saat → saatlik,
    son 30 gün → son 30 günlük; TXN_BY_CUST: nitelik "müşteri tarafından").
    Yeni kolon adında ek arkasındaki birime yapışır ve onun yerini alır
    (`parca._ekleri_bagla`: TXN_CNT_PER_DAY_AVG → TXN_CNT_AVG_PER_DAY);
    sondaki ek Diğer. Dil modeli de Ek önerebilir (`parca.ISTEM_SURUMU` 3).
    Tür açıklamaları (`parca.TURLER`, dil modeli istemleri aynı metni
    kullanır): Nitelik "ölçümü daraltan alt küme ya da özellik (kanal,
    ürün, taraf, yüksek ya da düşük tutarlı)"; Diğer "bayrak (FLAG, IND) ya
    da hiçbir türe girmeyen" (HIGH ve LOW gibi düzey sözcükleri Diğer'e
    itilmesin; `parca.ISTEM_SURUMU` 4).
    **Dil modelinin kural dışı cevabı** (`llm.parca_kural_disi`): türü
    Ek olup anlamında bir kez [parça] ve ek olmayan (BY "tarafından") ya
    da anlamı parçanın kendisi olan (NO "no", PER "per") parçalar bir kez,
    yalnız onlarla ve "ÖNCEKİ CEVABIN / DÜZELTİLECEK" satırlarıyla yeniden
    sorulur. İkinci cevapta da anlamı parçanın kendisi kalırsa kabul edilir
    (parça Türkçe bir sözcük olabilir: KREDI, LIMIT) ve satıra "Anlam
    parçanın kendisi; Türkçe karşılığı varsa yazın." notu düşer (onayı
    durdurmaz). Ek biçimi yine bozuksa ekrandaki onayı durduran hata
    görünür. İstemdeki BY örneği "[parça] bazında ya da [parça]
    tarafından, örnek tanımlara bakarak" oldu (`parca.ISTEM_SURUMU` 5).
    **Tür arka planda** (01.2.4.2'de tür sütunu ve onaydaki tür
    değerlendirmesi kaldırıldı; `/parca_tur_degerlendir` yok): ekranda
    yalnız Parça, Anlam, Standart, Onay. Satırın türü dil modelinin ya da
    hafızanın türüdür. Anlamda [parça] varsa tür Ek'tir; Ek önerilen
    satırın anlamı [parça] olmadan düzenlenirse tür Diğer olur (asıl tür
    01.2.4.4 son kontrolünde düzeltilir). Ek önerilip anlamı [parça]
    içermeyen satırda onayı durduran uyarı ("Anlamı [parça] ile yazın ...
    Ek değilse anlamı kendi sözcüğüyle düzeltin"). Sunucuda
    (`_parca_karari_isle`) boş ya da geçersiz tür Diğer, [parça] içeren
    anlam Ek sayılır; "tür seçilmedi" hatası yok.
    Çiftteki her parçanın yanında "i": geçtiği ilk üç kolon ve
    sözlük tanımı (`ESLER_ORNEK`; eşin `ornek` alanı), aynı mı ve hangi
    yazılış kullanılsın diye karşılaştırmak için. "Aynı" denen gruptaki parçalar adlarda seçilen yazılışı ve
    onun satırındaki anlam ile türü alır (satırları kilitli, "TXN ile
    aynı").
  - **Kurallar:** "Kontrol edin" satırları (soru, çelişki ya da örnek
    tanımların %60'ından azı uyuşuyor) toplu onaylanmaz. Onaylı satırda
    bir şey değişince onay kalkar. Standart: parçanın yeni kolon
    adlarında (01.2.4.4) yazılacağı biçim; çoğunlukla parçanın kendisi,
    aynı şeyi anlatan yazılışları tek yazılışta toplamak için değiştirilir
    (TRX yerine TXN). Başlığın "i"sinde açıklaması var; parçadan farklıysa
    kutu sarı (`dg-parca-std-farkli`) ve altında "Adlarda X yerine Y".
    Büyük harfle başlar, büyük harf ve rakam, en çok 12; anlamı farklı iki
    parça aynı standardı alamaz. Bütün parçalar ve çiftler onaylanmadan geçilmez.
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
    sayılar açıklamada geçmeli (kod denetimi).
  - **Toplu Sorular ve parça cevabı** (`akis_faz01._sorular`,
    `_aciklama_parcalari`): dil modelinin bir parça hakkında sorduğu
    sorular (`parca` alanı) parça başına tek kutuda; farklı sorular ayrı
    satırda, her biri kaç kolondan geldiği ve ilk üç kolonuyla (en çok
    `SORU_GOSTER` = 8 soru, kalanı "ve N farklı soru daha"). Parça adının
    yanında Ad Parçaları'nda onaylanan anlamı ("Onaylı anlamı: oran";
    `_sorular(..., bilgi)` → `anlam`): soru o anlamı değil, anlamın
    yetmediği yeri sorar (ör. hangi dönem hangisine bölünüyor). Kutunun
    altında ne yazılacağı: bütün kolonlarda geçerli bir kural (ör. "adda
    önce gelen dönemin değeri sonrakine bölünür"), dönem ve sayı olmadan;
    kutuda "Cevabınız (bütün RATIO kolonları için geçerli kural)"; tek
    kolona özel bilgi o kolonun «Sizin Düzenlemeniz»inde.
    Cevapta sayı varsa ilk tıklama uyarır ("Cevabınızda sayı var (3, 7)";
    düğme "Yine de Uygula"), ikinci tıklama uygular; cevap değişince uyarı
    kalkar. Kullanıcının cevabı yalnız dil modelinin anlaması
    içindir: o parçanın geçtiği bütün kolonlarda PARÇALAR satırına
    parçanın onaylı anlamının yanında "kullanıcının açıklaması (yalnız
    anlamak için; açıklamaya ve karta kopyalama)" olarak gider; karta ve
    açıklamaya kopyalanmaz, kartta parçanın onaylı anlamı kalır (anlamı
    onaylı değilse kartta o parça yok). Yazar istemi metni kopyalamamasını,
    kolona uyan anlamı kendi cümlesiyle yazmasını söyler. Kutunun altında
    yol gösteren not yazar.
  - **Sıra numaralı yer tutucu** (`donem._YT_ADAY`, `_sirali_sayilar`,
    `deger_anlami`, `yer_tutucu_hatasi`; app.js `donemAnlamIc`,
    `donemAnlamGoster`, `donemDegerAnlami`, `donemYerTutucuHatasi`):
    anlamdaki her "[sayı]" kalıbın sayılarını sırayla alır; aynı sayıyı
    tekrar yazmak için "[sayı 1]", "[sayı 2]" yazılır (içeride `<N#1>`).
    Örnek: `<N>D_X<N>` "son [sayı 1] gün ile ondan önceki [sayı 1] gün" +
    14D_X2 → "son 14 gün ile ondan önceki 14 gün". Kalıpta olmayan sıra
    ("[sayı 3]") hata. Kalıpta birden çok sayı varsa örneğin altında bu
    not yazar; dönem istemi de `<N#k>`yi anlatır.
  - **Hesaplı yer tutucu** (`donem.formul_hatasi`, `formul_hesapla`;
    app.js `donemFormulIc`, `donemFormulHesapla`, `donemFormulGorunur`):
    köşeli parantez içinde sayılarla hesap: "[sayı 1 × sayı 2]", "[sayı 1
    + sayı 1]", "[sayı 1 x 2 - 1]" (toplama, çıkarma, çarpma; çarpma önce).
    İçeride `<N#$1*$2>`. Örnek: `<N>D_X<N>` "son [sayı 1] günden son
    [sayı 1 × sayı 2] gün önceye kadar" + 14D_X2 → "son 14 günden son 28
    gün önceye kadar". Kalıpta olmayan sayı ya da anlaşılmayan hesap hata.
  - **Yeni adda yazılışta da** sıra numaralı ve hesaplı yer tutucu
    (`donem._AD_YT`, `ad_sablonu_hatasi`, `ad_sablonu_doldur`; app.js
    `donemAdIc`, `donemAdGoster`, `donemAdHatasi`, `donemAdDoldur`):
    `<N>D_X<N>` için "L[sayı 1]D_P[sayı 1]D" ile 7D_X2 → L7D_P7D,
    "L[sayı 1]D_L[sayı 1 × sayı 2]D" ile L7D_L14D. Numaralı yer tutucu
    varsa sayı adedi kuralı aranmaz (sıralı [sayı] kalıptakinden çok
    olamaz); yoksa eskisi gibi aynı sayıda olmalı.
  - **Dil modelinin yer tutucu yazımı düzeltilir** (`donem.anlam_duzelt`;
    dil modeli işi ve `donem_anlam_oner` sonucunda): "<NN1>", "<N1>",
    "<N 1>" gibi yazım "<N#1>" olur (kalıpta aynen geçen tam basamaklı
    `<N2>` ise "<N>"); sıra numaraları kalıbın sayılarıyla sırayla ve
    birer kez geçiyorsa düz yer tutucuya çevrilir ("<NN1>:00 ile
    <NN2>:00 arası" → "<NN>:00 ile <NN>:00 arası"). Çevrilemeyen yazım
    yer tutucu hatası olarak görünür. İstem de yalnız N / NN, <N#k> ve
    formülü kullanmasını söyler; `donem.ISTEM_SURUMU` 10.
  - **Hafızadaki anlamın denetimi:** dil modeline hafızadaki anlam bir
    değerle doldurulmuş örneğiyle de gider ("(değerle: 180D_360D -> son
    180 gün önce ile son 360 gün önce arası)"; `hafiza_ornek`); iki
    sayılı kalıpta iki N'yi aynı sayı sanıp yanlış "uyuşmuyor" demesin.
    `donem.ISTEM_SURUMU` 9.
  - **Üç dil modeli çağrısı** (`aciklama_duzen._isle`, `_denetim`): her
    grup (8 kolon) için 1) yazar taslağı yazar (`llm.aciklama_duzenle`,
    rol `aciklama_duzen`); 2) denetçi taslağı kaynaklara göre denetler
    (`llm.aciklama_kontrol`, rol `aciklama_kontrol`, yazardan farklı model
    önce): anlam kaybı, eklenen anlam, karttaki eksik bilgi, anlaşılırlık
    (dizilmiş isimler), gereksiz değişiklik, yazar kurallarına aykırılık;
    cevap: uygun, sorunlar, kendi önerisi; 3) yalnız denetçinin sorun
    bulduğu kolonlarda karar çağrısı (`llm.aciklama_karar`, rol
    `aciklama_karar`, düşünen model önce) taslak, sorunlar ve öneriyi
    kaynaklarla tartıp son açıklamayı yazar (`ilk_aciklama` taslağı
    saklar). Denetçi uygun bulduysa taslak son açıklamadır. Kartta
    satırda "Denetim: uygun bulundu." ya da "Denetim: <sorun>. Son
    açıklama denetimle birlikte yazıldı." (`denetim`; aileye aktarımda
    sayıları değişir). Denetim cevap veremezse "Denetim yapılamadı";
    karar cevap veremezse taslak kalır ve kontrol notu ("Denetçinin bulduğu
    sorun çözülmedi") yazar, satır toplu onaya girmez. Kod denetimi son
    açıklamada çalışır. İptal edilince denetim ve karar çağrılmaz.
  - **Onay:** her satırda Onay kutusu; toplu onay "Aileyi Onayla",
    "Biçim Değişikliklerini Onayla" ve "Hepsini Onayla" ile. Toplu onaya
    yalnız cevapsız sorusu ya da kontrol notu olan satır girmez (`topluOlur`;
    ad ve dağılım notu bilgidir, durdurmaz). Süzgeç düğmeleri ve
    "Görünenleri Onayla" gösterilmez (aşamalar aynı işi görür); arama
    kutusu kalır. Onay çalışma klasöründeki kayda yazılır (`kabul`:
    onaylanan açıklama metni); açıklama sonradan değişirse onay
    kendiliğinden düşer. Bütün kolonlar onaylanmadan geçilmez;
    "değiştirmeden devam" düğmesi yok.
  - **Ada eklenecek bilgi** (`ad_eksik`, `ACIKLAMA_SURUMU` 6): yazar
    (ve karar) açıklamada geçen, kartta ve adda karşılığı olmayan kısa
    bilgiyi anlamı ve türüyle döndürür (`[{"anlam": "ortalama", "tur":
    "istatistik"}]`; türler konu, yon, nitelik, olcu, istatistik,
    karsilastirma, birim; zaman ve uzun bilgi buraya girmez, ek bilgidir;
    `llm.ad_eksik_temizle`, kartta olan anlam atılır `_bicimle`). Denetçi
    bunu da denetler. Kartta kesik çerçeveli çip "İstatistik: ortalama ·
    ada eklenecek" (aile kutusunda kaç kolonda geçtiğiyle). Onay kaydına
    yazılır; 01.2.4.4'te kısaltmasıyla onaylanıp ada eklenir. Elle
    düzenlenen kolonda dil modelinin son bulduğu kalır. Yazar istemindeki
    "kolon adı sonraki adımda açıklamaya göre düzeltilir" cümlesi
    kaldırıldı (öyle bir adım yoktu).
  - **İki parçalı dönem kalıbı kartta:** kolon kartı kurulurken
    (`akis_faz01._aciklama_parcalari`, `aciklama_duzen.donem_konumlari`)
    her yan yana iki parça önce birlikte onaylı dönem kalıplarına bakılır
    (H00_06, 3_M, M_3 ve 14D_28D, `<N>D_<N>D`); uymazsa tek tek. Böylece
    14D_28D kartta "14 gün ile 28 gün arası" olur, "14 gün boyunca, 28 gün
    boyunca" değil. Kart değişen kolonun girdisi değiştiği için dil modeli
    yalnız o kolonları yeniden yazar.
  - **Değişim türü** (`aciklama_duzen.degisim_turu`, satırda `degisim`):
    "aynen"; "yazim" (sözcükler aynı, yalnız büyük / küçük harf,
    noktalama ya da Türkçe karakter); "ek" (sözcüklerin gövdesi ve sırası
    aynı, yalnız ekleri farklı: "günde" / "günlük", "adet" / "adedi",
    "bakiye" / "bakiyesi"; `_ayni_govde`: ortak gövde en az iki harf,
    gövdeden sonra iki tarafta da en çok üç bilinen ek, gövde sonu
    yumuşaması eşitlenir; anlamı değiştiren -siz, -li ek sayılmaz; sıra
    sayısı "3." ayrı sözcüktür, "3 ay" ile "3. ay" aynı değil);
    "degisen" (sözcük eklendi, çıktı ya da değişti). Değişen süzgeci yalnız
    "degisen"i sayar; "Yalnız Yazım" ve "Yalnız Ek" ayrı süzgeç (sayaçta
    `yazim`, `ek_degisim`). Değişen satırda açıklamanın orijinalde karşılığı olmayan
    sözcükleri altı yeşil çizgili (`ackSozcukFarki`, küçük harf ve
    noktalamasız en uzun ortak dizi); bütün metni yeniden okumak gerekmez.
    Sözlüğe yazılan "N kolonun açıklaması düzeltildi" sayısı yine her
    farklı metni sayar.
  - **En az değişiklik (istem, `ACIKLAMA_SURUMU` 6):** dil modeli yalnız
    gereken yeri düzeltir; orijinal anlaşılır ve doğruysa cümleyi yeniden
    kurmaz, anlamı aynı kalan ifadeyi (ek, sözcük sırası, eş anlamlı)
    değiştirmez; dönem orijinalde açıksa ("son 3 günde") dokunmaz, yalnız
    yazmıyorsa ya da belirsizse açar. Tek istisna dizilmiş isimler:
    tamlama kurmadan art arda dizilen isimlerde ("giden işlem ortalama
    tutarı") tamlama kurulur ("giden işlemlerin ortalama tutarı"); yalnız
    ek eklenir ya da değişir, sözcük ve sıra aynı kalır (satır "ek"
    sayılır, 2. aşamaya düşer). İstatistik sözcüğü karttaki gibi yazılır
    ("maksimum", "minimum"; "en yüksek", "en düşük" değil). Yalnız yazım
    düzeltildiyse karar "Yazım düzeltildi.". Sürüm değişince kolonlar bir
    kez yeniden yazılır; açıklaması değişen kolonun onayı düşer (onay
    açıklama metniyle saklanır), elle düzenlenen kolon olduğu gibi kalır.
  - **Biçim Değişikliklerini Onayla · N:** süzgeçlerin yanında; açıklaması
    orijinaliyle aynı ya da yalnız yazımı veya ekleri değişen ("aynen",
    "yazim", "ek"), hazır ve sorusu, notu, kontrol notu olmayan BÜTÜN
    2. aşama satırlarını (görünsün görünmesin) onaylar.
  - **Sizin Düzenlemeniz = önerinin düzenlenebilir hâli:** alan dil
    modelinin önerdiği açıklamayla dolu gelir (sizin düzenlemeniz varsa o;
    app.js `ackTaban`). Kutu metnin tamamını gösterir: yüksekliği metne
    göre ölçülür (`boylaPlanla`, toplu ölçüm; yazarken, öneri gelince ve
    genişlik değişince ya da gizli satır açılınca `BOYLA_GOZCU` ile
    yeniden), kaydırma çubuğu çıkmaz. Değiştirip alandan çıkınca metin aynen kolonun
    açıklaması olur (`islem: "not", tam: true`;
    `aciklama_duzen.elle_yaz`, kayıtta `elle`; `girdileri_ver` bu kolonu
    dil modeline göndermez, sonucu `elle_sonuc`: metin, tarz düzeltmesi,
    kod denetimi; karar "Sizin düzenlemeniz."). Değiştirmeden çıkmak
    kayıt değildir; alanı boşaltmak düzenlemeyi kaldırır ve öneri yeniden
    yazılır. Ailede "Ailedeki N Kolona da Uygula" düzenlemenizi üyelere
    sayıları değiştirerek aynen yazar (`aciklama_duzen.aileye_elle_yaz`;
    sayısı eşlenemeyen üye atlanır, notta yazar; "Geri Al" yalnız hâlâ
    aynı metni taşıyan üyelerden kaldırır). Kaynak kolonun düzenlemesi
    değişince üyeler de güncellenir; her üye ayrıca kendi alanından
    düzeltilebilir. Eski not biçimi (kısa ipucu, dil modeli işler) `tam`
    gelmeyen isteklerde sürer.
  - **Soru evresi (aşamalardan önce):** dil modeli düzenlerken ya da
    cevapsız toplu soru varken kartta yalnız ilerleme, Toplu Sorular ve
    bir not görünür; aşama çubuğu, arama ve düğmeler, tablo gizli (kart
    sınıfı `dg-acik-soru-evresi`; `soruEvresi`, `evreCiz`). Not: "N soru
    cevabınızı bekliyor ... cevaplanınca 1 Aileler açılır", soru kalmayıp
    dil modeli sürerken "Bütün sorular cevaplandı. Dil modeli kolonları
    cevaplarınızla düzenliyor", hiç soru yokken "Dil modeli kolonları
    düzenliyor. Toplu soru çıkarsa burada görünür". Cevapsız soru: soru
    kolonu olan ve cevabı olmayan parça. Cevap verilince ilgili kolonlar
    yeniden düzenlenir; yeni soru çıkarsa evre sürer. Evre bitince 1
    Aileler açılır; onay düğmesi evrede kapalı ("Önce yukarıdaki Toplu
    Sorular: N soru cevap bekliyor"). İptal'de cevapsız soru kalmadıysa
    evre biter. Salt okunur kartta evre yok.
  - **Anlamı Kayan Aileler** (soru evresinde, Toplu Sorular'dan sonra;
    `_kayma_alani`, `_kayma_baslat`, `llm.aciklama_kayma`,
    `SISTEM_ACIKLAMA_KAYMA`): dil modeli bitip cevapsız toplu soru
    kalmayınca arka planda her ailenin bir kolonunda (bütün üyeleri
    yazılmış ailede, orijinali dolu ve dil modelinin yazdığı ilk üye;
    ailesi olmayan kolonda kendisi) orijinal açıklama yeni açıklamayla
    karşılaştırılır: yok / küçük / büyük (8'li paket, aynı anda 4; rol
    aciklama_kontrol). Büyük: dönem, hesap, konu, yön ya da ölçülen şey
    farklı ya da temel bilgi kayıp. Sonuç çalışma kaydında
    (`aciklama_duzen.kaymalar`, imza orijinal ve açıklama): aynı açıklama
    yeniden sorulmaz, açıklama değişince yeniden bakılır. Büyük kayma
    aile başına kutuda sorulur (aile adı, kolon sayısı, dil modelinin tek
    cümle tespiti, örnek kolon, orijinal, yeni açıklama): "Ailenin doğru
    anlamı" + «Cevabı Uygula» ya da «Yeni Açıklama Doğru». Karar
    verilmemiş kutuda "Orijinal" ve "Yeni açıklama" metinleri tıklanabilir
    (yanlarında «Bunu Kullan»): metin "Ailenin doğru anlamı" kutusuna
    yazılır, imleç sonda; olduğu gibi uygulanabilir ya da düzeltilebilir. Cevap
    (`aciklama_kayma_karari`, `/aciklama_islem` islem "kayma";
    `aciklama_duzen.kayma_karari_yaz`) temsilci kolona not, aileye aile
    notu olarak "Sorduğun: <tespit> Cevabım: <cevap>" biçiminde gider; dil
    modeli ailenin hepsini, sayıları her kolonun dönemine uyarlayarak
    yeniden yazar. Karar `kayma_kararlari`'nda; «Kararı Değiştir» kararı
    ve verilmiş cevabın notlarını kaldırır. Karşılaştırma sürerken ya da
    karar bekleyen aile varken kolonlar açılmaz (`soruEvresi`; not ve
    alttaki gerekçe ne beklendiğini yazar); kart karşılaştırma bitene dek
    yoklar. Gerekçedeki ORİJİNAL / YENİ etiketleri küçük harfli adlarıyla
    yazılır (`llm._kayma_nedeni`).
  - **Kayma cevabından koşullu anlam** (`_kosul_onerisi_baslat`,
    `_kosul_onerisi_dogrula`, `aciklama_kosul_karari`, `_kosul_yaz`;
    `llm.aciklama_kosul_cikar`, `SISTEM_KOSUL_CIKAR`; `/aciklama_islem`
    islem "kosul"; kayıt `aciklama_duzen.kosul_onerileri`). Ailenin doğru
    anlamı yazılınca arka planda dil modeline örnek kolonun adı, orijinal
    ve yeni açıklama, soru, cevap, adındaki dönem kalıpları (sıra
    numaralı, ör. <N1>D_<N2>D; değeri, sayıları ve genel anlamın o
    değerdeki hali) ve harf parçaları verilir. Dil modeli cevabın bir
    kalıbın adda belirli bir parça geçince farklı dönem anlattığını
    gösterip göstermediğini söyler; gösteriyorsa kalıp, parça ve
    yer tutuculu anlam yazar. **Kod doğrular:**
    - kalıp ve parça örnek kolonun adında geçmeli;
    - anlamda rakam olmamalı, yer tutucuları kalıba uymalı;
    - örnek kolonun değeriyle doldurulunca çıkan sayılar cevapta (cevapta
      sayı yoksa orijinal açıklamada) aynı sırayla geçmeli;
    - genel anlamdan farklı olmalı.

    Tutmazsa öneri gösterilmez, kutuda nedeni yazar. Tutarsa ailenin
    kutusunda: "Dönem Bilgisi'ne de koşullu anlam olarak kaydedilsin mi?",
    kural ("adında RATIO geçen kolonlarda [sayı 1]D_[sayı 2]D «son [sayı 1]
    gün ile son [sayı 2] gün» demek"), örnek kolonda şimdiki ve
    kaydedilince anlam, etkilenen kolon sayısı (kalıp ve parça birlikte
    geçen kart kolonları; i balonunda 3 örnek), Dönem Bilgisi'nde o parça
    için başka anlam varsa o, sözlük açıklamasındaki sayılar bu anlamla
    sırasıyla tutmayan öteki kolonlar (ilk 5) ve «Kaydet» / «Kaydetme».
    Karar verilmeden kolonlar açılmaz (karar bekleyen sayılır).
    **Kaydet:**
    - çalışmanın `durum["donem_kosul"]`'una, 01.2.4.1 kararına
      (`donem_bilgisi_karari` satırının `kosullu`'su; geri dönülünce
      01.2.4.1'de görünür) ve hafızaya (`kosullu_anlamlar`) yazar;
    - oturum durumu kaydedilir;
    - o kalıbı ve parçayı taşıyan kolonların kartı koşullu anlamla yeniden
      kurulur ve açıklamaları yeniden yazılır.

    «Geri Al» kaydedilen anlam değişmediyse önceki hali yazar. Ailenin
    kararı değişince kararı verilmemiş öneri kalkar; kaydedilmiş olan
    kalır.
  - **Sıra: önce sorunlular, sonra sorunsuzlar.** Aşama çubuğu iki
    grupludur ve bütün aşamalar sırayla açılır (bir aşama, öncekinin
    bütün kolonları onaylanınca ya da listeden çıkınca): "Önce
    sorunlular": Cevapsız Soru (hazır ve sorusu cevapsız; cevabı
    işlenirken de burada), Kontrol Notu (hazır, sorusu yok, kontrol notu
    var); "Sonra sorunsuzlar": Aileler, Biçim Değişiklikleri, Değişenler.
    Kodlar `asamaOf`: 4 soru, 5 kontrol notu, 1 aile, 2 biçim, 3 kalan;
    `ASAMALAR` dizisi görünüm sırasıdır (`asamaBilgi`, `asamaSirasi`).
    Satırı olmayan aşama görünmez; numara görünen sıradır. Sorunlu
    listeler düz listedir (aile kutusu yok), sekmesi amber kenarlı. Aile
    kutusu yalnız Aileler aşamasındaki üyeleri sayar; ayrılan üyeler için
    hangi listede oldukları yazar. Düğme sorunlu listede "Bu Listedekilerin
    Hepsini Onayla · N" (yalnız o liste), sorunsuz aşamalarda
    "Sorunsuzların Hepsini Onayla · N"; ikisi de iki tıklama.
  - **Satırda soruya cevap** (`aciklama_soru_cevapla`, `/aciklama_islem`
    islem "soru"; `aciklama_duzen.soru_cevabi_yaz`): sorulu satırda
    sorunun altında "Cevabınız" kutusu ve «Cevabı Uygula» (Enter da).
    Cevap soruyla birlikte nota yazılır ("Sorduğun: ... Cevabım: ...";
    `soru_notu`), elle açıklama kalkar ve kolon beklemeden yeniden yazılır
    (yazar istemi bu biçimi önceki soru ve cevap olarak okur, soruyu
    kopyalamaz, yeniden sormaz). Soru kalkarsa kolon kendi listesine geçer
    ve satırda "Sorusuna cevabınız: ..." yazar; yine soru gelirse "Önceki
    cevabınız" ile kutu yeniden çıkar. Kart `soru_cevaplari`'ndan
    gösterir (`soru_cevabi`; not hâlâ o cevapsa). Notun sayı denetimi
    yalnız cevap kısmına bakar. "Sizin Düzenlemeniz" yalnız elle notu
    gösterir (`elle` alanı; `ackElleNot`). Yazılan ama uygulanmayan cevap
    yoklamada kaybolmaz (`cevapTaslak`).
  - **Dönem sayısı kontrol notu:** kartta zaman bilgisi varsa
    (`_aciklama_girdileri`) adın dönem sayılarından yalnız kartta da
    geçenler aranır: 3D_X2 "son 3 gün ile son 3 ile 6 gün arası" için 2
    aranmaz. Not sonuçta saklı kalmaz, girdiyle yeniden hesaplanır
    (`aciklama_duzen.guncel_kontrol`; satır ve sayaçlar), eski sonuçlar
    yeniden yazdırılmadan düzelir.
  - **Aşamalar (zorunlu sıra):** kartın üstünde üç aşama, sayılarıyla
    ("1 · Aileler · 120 / 600"): 1 Aileler (adı yalnız sayıyla ayrılan
    kolonlar, aile başlıklarıyla), 2 Biçim Değişiklikleri (aile dışı;
    "aynen", "yazim", "ek"), 3 Değişenler (kalan: "degisen", sorulu,
    düzenlenemeyen). Tablo, süzgeç sayıları ve düğmeler yalnız seçili
    aşamanın satırları için; "Biçim Değişikliklerini Onayla" yalnız 2.
    aşamada. Aşama, öncekinin bütün satırları onaylanınca açılır (kilitli
    aşama soluk, "Önceki aşama bitince açılır"); 2. aşama, dil modeli aile
    dışı satırları bitirmeden bitmiş sayılmaz. Aşama bitince sonraki
    kendiliğinden açılır; önceki bir aşama sonradan eksik kalırsa ona
    dönülür. Biten aşamaya tıklanıp bakılabilir. Onaylanmış (salt okunur)
    kartta aşama yok. Adımın onayı yine bütün kolonların onayını ister.
  - **Kontrol notu ve zaman aralığı:** kod denetimi (`llm.aciklama_sorunlari`)
    "sayı ile sayı arası"nı değer aralığı istatistiği sayar; içinde zaman
    sözcüğü (saat, gün, hafta, ay, yıl, dakika, dönem, gece ...) ya da
    saat biçimi (00:00) olan aralık istatistik değildir ("00-06 saatleri
    arası", "14 gün ile 28 gün arası"). Metin yalnız sona nokta eklenerek
    kaldıysa değişim "aynen" ve karar "Aynen alındı." gösterilir.
  - **Ek bilgi tekrarı:** ek bilginin bütün sözcükleri açıklamada geçiyorsa
    (`aciklama_duzen.ek_acikta`, satırda `ek_acikta`) "Ek bilgi" satırı
    gösterilmez ve Ek Bilgi süzgecinde sayılmaz; ek bilgi veride, Önerilen
    Sözlük'te ve 02'ye giden katalogda kalır.
  - **Aileler (aile kutusu):** adı yalnız sayılarla ayrılan kolonlar (satırda
    `aile`, `aciklama_duzen.aile_anahtari`; iki ya da daha çok üye) 1.
    aşamada tabloda her biri kendi kutusunda (`aileBasKur`, `.dg-acik-aile-kutu`;
    tablo hizası kuralının tek istisnası: kutunun içi soldan hizalı):
    üstte ailenin adı (# yerine [sayı]) ve sağ uçta durum ("N / M kolon
    onaylı" ya da "✓ Onaylandı · M kolon"); altında kolonları ayıran
    değerler (`aileDegerleri`: "4 kolon: 3D · 7D · 30D · 90D"); aile
    açıklaması (sayılar [sayı] yapılınca en çok kolonda aynı olan metin;
    "bütün kolonlarda aynı, yalnız [sayı] değişir" ya da "N / M kolonda
    aynı"); bütün hazır üyelerde aynı kart alanları; toplu onaya girmeyen
    kolonlar adlarıyla (soru, not ya da kalıptan farklı açıklama; hepsi
    kalmışsa "Toplu onaylanacak kolon kalmadı"); düğmeler: "Aileyi Onayla ·
    N kolon" (yalnız henüz onaylanmamış, kalıba uyan, notu olmayan hazır
    kolonlar; kalmadıysa görünmez), "Onayı Kaldır" (onaylı kolonu varsa;
    ailenin onaylarını kaldırır, `aileOnayKaldir`) ve "Kolonları Aç ve Tek
    Tek Bak" / "Kolonları Kapat". Açılan ailenin kolonları kendi sütun
    başlığı satırıyla (`dg-acik-alt-bas`) altında; 1. aşamada tablonun üst
    sütun başlığı gizli. Süzgeç ya da arama varsa aileler açık. Aşama
    notu aile ve kolon sayısını, kaç ailenin tamamen onaylandığını ve ne
    yapılacağını yazar. Sayfa aileyi bölmez; kalan hep aileyse düğme "Daha
    Fazla Aile Göster (N aile daha)".
  - **Hepsini Onayla · N** (Sorunsuzların / Bu Listedekilerin; bkz.
    Sorunsuz ve Ayrılanlar): cevapsız sorusu ya da kontrol notu olan
    kolonlar sorunsuz onaya girmez, kendi listelerinde kalır. İki tıklamalı: birinci tıklama
    düğmeyi "Evet, N Kolonu Onayla" yapar ve altında yazar ("Ayrılan M
    kolon onaylanmaz, listede kalır: X kolonda cevapsız soru, Y kolonda
    kontrol notu; onlara tek tek bakın"; ikisi de olan soru sayılır; dil
    modelinin düzenlediği kolonlar bitince ayrıca onaylanır), «Vazgeç»
    geri alır; ikinci tıklama onaylar (`hepsiDurum`).
  - **Aile kutusunda toplu onaya girmeme sebebi:** her kolonun ilk sebebi
    sayılır (cevapsız soru, kontrol notu, açıklaması kalıptan farklı).
    Hiçbir kolonu toplu onaylanamayan ve onaylısı olmayan ailede "Bu
    ailenin kolonları toplu onaylanamıyor (cevapsız soru: 8)" yazar.
  - **Adım adım yönlendirme:** aşama notu her aşamada yalnız o aşamada
    ne yapılacağını yazar (1. aşamada önce aile ve kolon sayısı, kaç
    ailenin onaylı olduğu). Kartın altındaki gerekçe etkin aşamaya göre
    tek adım yazar (`acikErisim.asama()`): "Aşama 1 / 3 (Aileler): N aile
    onay bekliyor", "Aşama 2 / 3 (Biçim Değişiklikleri): N kolon onay
    bekliyor", "Aşama 3 / 3 (Değişenler): N kolon onay bekliyor"; etkin
    aşamada bekleyen yoksa (2. aşama dil modelini bekliyorsa) toplam onay
    bekleyen sayısı yazılır.
  - **02'ye aile açıklaması:** aile kataloğunda bütün üyelerin açıklaması
    yalnız sayılarla ayrılıyorsa tek örnek yerine "açıklama kalıbı (bütün
    üyelerde aynı; [sayı] üyeye göre değişir)" gider
    (`llm.sozluk_katalogu`).
- **01.2.4.4 Kolon Adları** (`parca.ad_birimleri`, `parca.ad_kur`,
  `akis_faz01._kolon_ad_alani`):
  - Her parça standart yazılışını alır; birimler Ad Standardı'ndaki yer
    sırasına dizilir (aynı yerdekiler adda geçtikleri sırayla). Sayılı
    zaman parçası yazıldığı gibi kalır (3_M, H00_06), yeri Zaman. Dönem
    kalıbının yeni adda yazılışı varsa o yazılır: önce yan yana iki
    zaman birimi (3D_6D, `<N>D_<N>D` → BTWN_3D_6D), sonra tek birim
    (`parca.ad_birimleri(..., yazilislar)`).
  - **Dönem Yazılışları** (Ad Standardı'nın altında;
    `_donem_yazilis_satirlari`, `_donem_ad_yazilislari`). Kolonlar
    hücresinde i balonu (`_donem_yazilis_ornekleri`, `dyOrnekYaz`):
    kalıbın geçtiği 3 kolon (önce açıklaması olan ve değeri farklı
    olanlar); her birinin eski adı, bu kartın kurduğu yeni adı (yazılış,
    Ad Standardı ve eklenecek parçalar uygulanmış; adlar kurulunca
    yenilenir) ve 01.2.4.3'te onaylanan açıklaması (onay yoksa sözlüğün
    çalışma kopyasındaki tanım). Kolon adlarında
    geçen her onaylı dönem kalıbı (yer tutuculu; gruptan ayrılan tek
    değerler hariç) için KALIP / KOLONLAR (kaç kolonda, adlarda ilk geçen
    örnek; iki parçalı kalıp yan yana iki parçayla aranır, onun içindeki
    tek parça tek parçalı kalıba sayılmaz) / YENİ ADDA (kutu; ekranda
    [sayı], içeride `<N>`; boşsa kalıp aynen). Kutunun altında "Ör. 30D →
    L30D" ya da kırmızı hata (`donemAdHatasi`; sunucuda
    `donem.ad_sablonu_hatasi`). Kutudan çıkınca adlar yeniden kurulur
    (`/kolon_ad_onizle` `donem_yazilis`), adı değişen ailenin onayı kalkar;
    geçersiz yazılış onayı durdurur. Kaynak sırası: kartın gönderdiği, bu
    çalışmanın önceki kararı (`_kolon_ad_karari["donem_yazilis"]`; eski
    kayıtta yok), hafıza (`donem_ad`). Onayda `durum["donem_ad_yazilis"]`
    ve hafızaya yazılır (boş olan hafızadan kalkar); onay metninde "N dönem
    yazılışı var". Birimli kalıplarda satırlar kalıp × türdür (bkz.
    "Dönem anlam türleri").
    Varsayılan sıra: Konu, Yön, Nitelik, Ölçü, İstatistik, Zaman,
    Karşılaştırma, Birim, Diğer (TXN_30D_CNT → TXN_CNT_30D); büyük harf,
    ayraç "_".
  - **Ada Eklenecek Parçalar** (`_ada_eklenecekler`, `_ad_ek_satirlari`;
    Ad Standardı'nın altında): Kolon Kartları onayındaki `ad_eksik`
    bilgileri anlam ve türe göre (kaç kolonda, örnek kolonlar). Kısaltma
    önerisi önce bu çalışmanın onaylı ad parçalarından, sonra parça
    hafızasından (anlamı aynı parçanın standart yazılışı, aynı türdeki
    önce; `_ad_ek_bilinen`); yoksa kart açılırken dil modeli önerir
    (`_ad_ek_onerileri`, `llm.kisaltma_tek_oneri`, `durum["_ad_ek_oneri"]`).
    Satırda kısaltma kutusu (büyük harf, harf ve rakam, en çok 12; yazılan
    aynen kalır, geçersizse hata), «Ekle» / «Ekleme» ve Onay. Kısaltma ya
    da karar değişince adlar yeniden kurulur (`/kolon_ad_onizle`,
    `eklenecekler`), adı değişen ailenin onayı kalkar. «Ekle»de kısaltma
    o kolonların adına Ad Standardı'ndaki yerine eklenir (`_ek_birimli`;
    adda zaten varsa eklenmez): TXN_GDN_3D_CNT_PER_DAY →
    TXN_GDN_CNT_AVG_3D_PER_DAY. Hepsi onaylanmadan ve kısaltmalar geçerli
    olmadan adım geçmez (`_kolon_ad_karari_isle`); karar
    `_kolon_ad_karari["eklenecekler"]`.
  - **Ad Standardı paneli:** yerler tutup sürüklenerek sıralanır
    (`surukleBasla`; pointer olayları, fare ve dokunmatik). Sürüklerken
    öteki yerler canlı kayar, numaralar güncellenir; bırakınca sıra
    değiştiyse adlar sunucuda yeniden kurulur (`/kolon_ad_onizle`), adı
    değişen ailenin onayı kalkar. Sürüklemeden tıklamak sırayı
    değiştirmez. Klavye: yere odaklanıp sol / sağ ok tuşu bir öne / arkaya
    taşır; adlar kurulunca odak aynı yerde kalır. Onayda hafızaya yazılır
    (`parca_ad_standardi`).
  - **Son Kontrol: Parça Türleri** (Ad Standardı'nın altında; tür
    01.2.4.2'de seçilmez): kart açılınca arka planda dil modeli Ek
    dışındaki her parçanın türünü denetler (`_ad_tur_girdisi`,
    `_ad_tur_kontrolu`; `parca.tur_baslat` kip "ad", `llm.SISTEM_AD_TUR`).
    Girdi: anlam, şimdiki tür, AD SIRASI ve en çok 3 ailenin ilk kolonu
    "ESKİ → YENİ" ile Kolon Kartları'nda onaylanan açıklaması. Dil modeli
    yalnız açıkça yanlış türü düzeltir, Ek önermez; sonuç parça, anlam ve
    türe göre bellekte (Ad Standardı değişince yeniden sorulmaz).
    Düzeltme kendiliğinden geçerli olur, adlar düzeltilmiş türle kurulur
    (`_aile_adlari` ikinci kez). Panelde satır başına PARÇA ("i": baktığı
    kolonlar) / ANLAM / TÜR (seçim; önceki türün yanında "(önceki)") /
    NEDEN ("Dil modeli: X yerine Y" ve tek cümle). Kullanıcı türü
    değiştirebilir (önceki türe dönmek dahil); "Başka bir parçanın türü
    yanlışsa" ile herhangi bir parçanın türünü değiştirir ("Sizin
    değişikliğiniz", "Değişikliği Kaldır"). Seçimler `turler` ({parça:
    tür}) olarak `/kolon_ad_onizle`'ye ve karara gider; adı değişen
    ailenin onayı kalkar. Kontrol sürerken kart 3 saniyede bir
    `/kolon_ad_onizle` ile yoklar ve onay düğmesi kapalıdır ("Son kontrol
    sürüyor"); sunucu da onaylamaz. Onayda değişen türler parça bilgisine
    ve proje hafızasına yazılır, `durum["kolon_ad_tur_duzeltme"]`
    (parça, anlam, eski, yeni, kaynak, neden) onaylanmış kartta "Onayda
    türü değişen parçalar" tablosu olur. Önceki onaylı kontrol ve
    onaylanmış kart dil modeli işini başlatmaz (`baslat=False`).
  - **Satırlar ailedir** (adı yalnız sayılarla ayrılan kolonlar; adı
    değişenler önce): Yeni Ad / Eski Ad Kalsın ve Onay; "Ailede N kolon"
    bütün ikilileri açar. Sorunlu ad (sayıyla başlıyor, iki kolon aynı
    adı alıyor, rol kolonunun adı) onaylanamaz. Arka uç adları onayda
    kendisi yeniden kurar ve denetler. Sonuç `durum["kolon_yeni_ad"]`.
  - **Toplu onay:** arama ve süzgecin yanındaki düğme BÜTÜN sayfalardaki
    listeye uygulanır (yalnız o sayfaya değil). Süzgeç yoksa
    "Sorunsuzların Hepsini Onayla · N", arama ya da süzgeç varsa "Bu
    Listedekilerin Hepsini Onayla · N". Onaylanmamış ve sorunsuz aileler
    seçili hâliyle (Yeni Ad ya da Eski Ad Kalsın) onaylanır; sorunlu aile
    atlanır (sayısı düğmenin açıklamasında). Ada Eklenecek Parçalar
    başlığında "Hepsini Onayla · N": onaylanmamış satırlar seçili hâliyle
    onaylanır; kısaltması geçersiz satır atlanır ve sayısı başlıkta yazar.
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
- **01.2.3.1 Tanımsız ve Sorunlu Kolonlar** (A ve B; 01.2.3'ün alt adımı,
  numaralar kaymaz). Üç grup, her biri bir başlık satırının altında
  (`SORUNLU_GRUPLAR`; başlıkta kolon sayısı ve "i"):
  - **Tamamen Boş Kolonlar** ve **Tek Değerli Kolonlar**
    (`_sorunlu_kolonlar`, `_tek_degerli_hesapla`): boş hücre ayrı değer
    sayılır (`nunique(dropna=False) <= 1`); tamamen boş kolon ve hiç boşu
    olmayan sabit kolon tek değerlidir, "bir değer ve boş" iki değerlidir.
    Sözlükte tanımları olsa da listelenir, kilitli ve her zaman çıkar
    (AMP_VERISETI'nden ve AMP_SOZLUK'ten); satırın ipucunda nedeni ve tek
    değer yazar ("Bütün satırlarda aynı değer (7) var ve boş hücre yok").
    Sözlükte tanımı da yoksa "Tanımsız" çipi. Rol kolonları (hedef, kimlik
    ...) girmez. Önceden yalnız 01.3'te sessizce süreç dışı kalıyorlardı;
    artık burada çıkarıldıkları için 01.2.4 adımlarına da girmezler.
  - **Sözlükte Tanımı Bulunmayan Kolonlar:** 01.2.3'ten sonra sözlükte
    hâlâ tanımı olmayan kolonlar; satır başına "Çıkar" kutusu (işaretli
    gelir), "Tümünü Seç" ve "Tümünü Temizle".
  - Not satırı sayıları yazar (`tanimsiz_karar_notu`): "1 kolon tamamen boş
    ve 2 kolon tek değerli. Bu kolonlar modele bilgi katmaz; …". Üç grup
    da boşsa adım sorulmadan geçilir. Kolonlar: Değişken, Tip, Boş Oranı, Tekrar Oranı, Tekil
  Değer, En Sık Değerler, Min, Med, Mean, Max, Çıkar
  (`akis_faz01._tanimsiz_bilgi`). Hepsi veri seti profilinden (tam tablo,
  örneklem yok). Genişlikler `<col>` sınıflarından (`tk-*`), başlık ve
  hücre ortalı (bütün tablolardaki kural); kolonlar ince dikey çizgiyle
  ayrılır.
  - Tekrar Oranı: değeri kendinden önceki bir satırla aynı olan satırların
    bütün satırlara oranı, boş hücre de değer sayılır (profil `tekrar` /
    satır; `df[kolon].duplicated().sum()` ile aynı). Adedi ipucunda. Sıfır
    olmayan çok küçük oran ilk anlamlı basamağına kadar yazılır (%0,0
    görünmez). Eski profillerde de var.
  - En Sık Değerler: en sık 10 değer, her biri "değer (adet)" biçiminde,
    adet parantez içinde ve soluk (adet
    azalan, eşitlikte değer artan; profilin `ust_degerler`'i). Tekil
    değeri 10 ve altındaki kolonda bütün değerler görünür. Sayısal değer
    yerel biçimle, saati gece yarısı olan tarih yalnız gün olarak yazılır;
    uzun değer kısaltılmaz, sarar. Tam değer ipucunda.
  - Tarih kolonunda Min, Med ve Max (Mean yok). Tarih medyanı
    profilin `medyan` alanı (aşağıda).
  - Min, Med (medyan), Mean (ortalama), Max sayısal kolonda (mantıksal
    dahil); bu sırayla, Med ve Mean ortada.
    Medyan profilin kantilinden (0,5; çift adette iki ortanın ortalaması),
    ortalama sonlu değerlerin tamamının ortalaması (profil `ortalama`,
    aşağıda). Ekranda 100 ve üstü iki, altı dört ondalık; tam değer
    ipucunda.
  - Kişisel veri taşıyan kolonda (`pii_ad` ya da `pii_deger`) değer ve
    istatistik gösterilmez, "Kişisel veri olduğu için değerler
    gösterilemez." yazar. Boş oranı, tekrar ve tekil sayısı görünür.
  - Profili ortalama ve tarih medyanı eklenmeden önce çıkarılmış
    çalışmada bu hücreler "∅" ve kartın altında bunu söyleyen not durur.
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
  - İlk hal: sözlükte anlamı olmadığı için bütün kutular işaretli gelir
    (değiştirilebilir; `_tanimsiz_varsayilan`). Yazarak onayda da önceki
    karar yoksa kolon çıkar. Tek değerli kolon ve tek değerli dönem
    kolonu işaretli ve kilitli (her durumda çıkar, sebebi kutunun
    ipucunda). Önceki karar (geri dönüş) korunur.
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

**02.1 Veri Profili ve Kalite kartı**
- Önce Kontrol Eşikleri formu (`veri_profili_girdi`, tip `profil_esik`;
  app.js `profilEsikKartiEkle`): dokuz eşik (`akis_faz02.PROFIL_ESIKLERI`)
  Kontrol, Ölçüt, Yakalanırsa, Eşik, Önerilen, Neden Bu Değer
  sütunlarıyla; ayrıntı balonsuz, sütunlara bölünmüş
  (`aciklama_parcalari` bilgi metnini **Etiket** paragraflarından ayırır):
  Kontrol: ad, tek cümle ve "Neden önemli?". Ölçüt: "<eşiğin anlamı>
  kolon yakalanır.", varsa "Eşik ne yapar?", Kapsam ve Örnek.
  Yakalanırsa: renkli kısa sonuç (çözüm önerilir; çözüm yoksa üretime
  girmez / kararınıza bırakılır / bilgi için gösterilir) ve ayrıntısı.
  Neden Bu Değer: önerilen değerin gerekçesi. "Nedir?" paragrafı
  gösterilmez (Kontrol ve Ölçüt aynı şeyi söyler). Metinler
  `akis_faz02.PROFIL_ESIK_ACIKLAMA`'da (kisa, bilgi, sonuc; sonuç sözleri
  `NE_OLACAK` ile aynı). Önerilenden farklı satır amber vurgulu, hatalı
  değer kırmızı ve gönderilmez, "Önerilenlere Dön". Ekranda "varsayılan"
  sözü yok: önerilen değer (ör. "Değiştirilen eşikler: … (önerilen %50)").
- Karar kartının Kontroller tablosu aynı düzende: Kontrol, Ölçüt,
  Bulunan, Ne Olacak, Neden Bu Değer (`kontrol_parcalari`: eşikli
  kontrollerde eşik formunun metni; sabit, aynı içerik, beklenmeyen
  negatif ve tekrar eden satır için `_KONTROL_ACIKLAMA_EK`, bunlarda
  Neden Bu Değer "Eşiği yok, kural sabit"). Ölçüt onaylanan eşikle
  kuraldır (`_profil_kurallari`; kapsam ve yakalanırsa ile tekrar
  etmez), Kapsam ve Örnek altında. Ne Olacak bulgu varsa kısa sonuç ve
  yakalanırsa ayrıntısı; bulgu yoksa "İşlem yok". Yakalanırsa ayrı sütun
  değil, Ne Olacak ile birleşik (iki sütun aynı şeyi söylerdi). Çözüm
  kontrollerinde seçilebilir çözüm yoksa "Üretime girmez; uygun çözüm
  bulunmadı". Bu iki tablo 900 px'ten dar alanda yatay kayar. "Eşikleri Onayla ve Profili Çıkar" `{"dogrulama": {"adim":
  "veri_profili", "esikler": {anahtar: ekrandaki sayı}}}` gönderir;
  `esik_dogrula` aralığı denetler (yüzde ve puan ekranda 100 ile çarpılı,
  Türkçe yazım: 1.000 binlik, 0,5 ondalık), `profil["esikler"]`'e yazar.
  Kontroller, kural metinleri ve eksik değer çubuğunun %50 sınırı bu
  eşiklerle çalışır (`profil_esikleri`; `sfa.profil_cikar` ve
  `profil_ek.ek_kontroller` eşik alır). Değiştirilen eşikler profil
  metninde ve kartta "Değiştirilen eşikler: ..." olarak yazılır.
  Yazarak onayda mevcut eşikler geçerli. Geri Dön ile 02.1'e dönülünce
  form son onaylanan değerlerle açılır.
- Form gönderildikten sonra karar isteyen kolon yoksa adım onay sormadan
  geçer (`akis_sohbet`: girdiden sonra plan `_plan_otomatik` derse
  uygulanır). Yenilemede onaylanmış form kilitli çizilir.
- Profil bölmeden sonra çalışır, tablonun tamamında (örneklem yok, sayımlar
  kesin). `akis_faz02.profil_hesapla`: dört temel kontrol
  (`sfa.profil_cikar`) ve ek kontroller (`fe_agent/profil_ek.py`).
- 13 kontrol, üç sonuç türü (`akis_faz02.PROFIL_KONTROLLERI`):
  - Üretime girmez (kolon `kusurlu_kolonlar`'a girer, 03.3 Analitik Baz
    Set'te düşer): Eksik Oranı Yüksek (%50 üstü), Sabit ya da Tek Değerli,
    Kimlik Benzeri, Kardinalitesi Aşırı Yüksek (metin kolonda 50'den fazla
    değer), Aynı İçerikli Kolonlar (satır satır birebir aynı; gruptan
    tablodaki ilk kolon kalır, kopyalar `profil_teshis.ayni_icerik`).
  - Kararınıza bırakılır: Neredeyse Sabit (en sık değerin payı %99 ya da
    üstü, boş da değer sayılır), Dönemde Boş ya da Sabit (kolon bazı
    dönemlerde tamamen boş ya da en az 100 satırlı bir dönemde tek
    değerli). Her kolon için Tut ya da Çıkar; varsayılan Tut.
  - Bilgi için gösterilir: Gizli Eksik (-1, -99, -999, 9999 gibi kod, dolu
    satırların %1'inden fazlası, geri kalan değerlerden kopuk), Sıfır
    Yoğunluğu (dolu satırların %95'i ya da fazlası sıfır), Beklenmeyen
    Negatif (kolon kartının ölçüsü adet, gün, süre, yaş, ay, yıl iken
    negatif), Dönemler Arası Eksik Sıçraması (art arda iki dönemde 20
    puandan fazla), Uç Değer Yoğunluğu (en büyük değer %99'luk değerin 100
    katından büyük), Tekrar Eden Satır (aynı kimlik ve dönem ya da bütün
    kolonları aynı; her satır bir kez sayılır).
  - Ek kontroller yalnız dört temel kontrolden geçen kolonlara uygulanır.
    Kopya kolonlar başka listede tekrar edilmez; neredeyse sabit kolonlar
    dönem kontrolüne ve sıfır yoğunluğuna girmez.
  - Uygulanamayan kontrol "Uygulanmadı" ve sebebiyle görünür: kategorik
    kolon yok, dönem kolonu seçilmedi, tabloda tek dönem var, kolon
    kartlarında ölçü bilgisi yok.
- Hedef Dağılımı: sınıf başına satır ve pay, hedefi boş satır, dönem
  başına hedef = 1 oranı (ikili) ya da sınıf payları (çok sınıflı).
- Akış: karar isteyen kolon yoksa adım onay sormadan geçer (eskisi gibi),
  kart biten bloğa `tamamlananlar` içinde gelir. Varsa
  `veri_profili_plan` kartı `karar_bekliyor` ile açar, adım bekler; kart
  altındaki "Kararları Onayla ve Devam Et" `{"dogrulama": {"adim":
  "veri_profili", "cikar": [...]}}` gönderir, `veri_profili_uygula`
  kararı `profil["profil_karar"]`'a yazar ({kolon: "tut" ya da "cikar"}).
  Yazarak onayda önceki karar, yoksa Tut geçerli. Çıkarılan kolonlar
  `kusurlu_kolonlar` ve `_dusurulecek_kume`'ye girer; 03.3 planı
  "aynı içerik" ve "profilde çıkarılan" sayılarını ayrı yazar.
- Kart (`akis_faz02.profil_karti`, tip `profil`; app.js
  `profilKartiEkle`):
  - Sayılar: Satır, İncelenen Kolon, Sorunsuz, Bilgi Notu Olan,
    Kararınızı Bekleyen (yalnız karar beklerken), Üretime Girmeyen. Bütün
    karolar aynı görünür; yalnız sayının rengi durumu söyler.
  - Eksik Değer Oranına Göre Kolonlar çubuğu: "Eksik yok" nötr gri, eksik
    arttıkça kırmızı koyulaşır.
  - Kontroller tablosu: Kontrol, Neye Bakıldı (sade kural, eşikler
    koddan), Bulunan ("N kolon" ya da "N satır" düğmesi, "Yok", ya da
    "Uygulanmadı"), Ne Olacak. Bulunan düğmesi kolonları açar: Kolon,
    onaylı Açıklama, Bulgu (ör. "Kod -999, payı %5,18 (311 satır)"),
    karar kontrollerinde Karar (Tut ya da Çıkar; kilitli kartta Tutuldu ya
    da Çıkarıldı). Karar bekleyen kontroller açık gelir, "Hepsini Tut" ve
    "Hepsini Çıkar" düğmeleri var. Bir kolon iki karar kontrolünde
    geçerse iki satır aynı kararı gösterir.
  - "i": incelemenin kapsamı, üç sonuç türünün anlamı, incelemeye
    alınmayanlar, profil tablosunun kayıt yeri.
- Yenilemede `backend._surdurme_govdesi` 02.1 bloğunu güncel metin ve
  kilitli kartla çizer (`profil_gecmisini_tazele`): kart adımın metinli ya
  da ekranlı ilk satırına yazılır, diğer 02.1 satırları boşaltılır (kart
  iki kez çizilmez). Kayıtlı transkript değişmez.
- Yenilemede açık bloğun metni (`_son_cevap`) biten adımların özetiyle
  başlamaz: canlı yanıt ayrıldıktan sonra `_son_cevap` kalan metinle
  kaydedilir; eski kayıtlarda `_biten_ozetleri_ayir` özetleri atar (02.2
  bloğunda 02.1 metni tekrar etmez).

**02.1 kartında onay düğmesi**
- Karar kartı (tip `profil`) ve eşik formu (tip `profil_esik`)
  `KENDI_DUGMELI_KARTLAR` listesinde: blok ayrıca genel "Onayla ve
  Uygula / Değiştir" düğmelerini taşımaz. Onay yalnız kartın en altındaki
  düğmeyle verilir (önceden genel düğmeler metnin altına, kartın üstüne
  düşüyordu).

**02.1 kontrol satırı renkleri ve aynı içerikli kolon seçimi**
- Kontroller tablosunda her satır durumuna göre renkli, sol kenarda kalın
  çizgi: yeşil sorunsuz (bulgu yok, Ne Olacak "İşlem yok"), sarı dikkat
  (kararınıza bırakılan ya da bilgi notu olan bulgu), kırmızı üretime
  girmez, gri uygulanmadı. Açılan liste aynı renkte, girintili; hangi
  listenin hangi kontrole ait olduğu çizgiden görünür.
- Aynı İçerikli Kolonlar: her grup için dil modeli (`llm.ayni_icerik_sec`,
  `SISTEM_AYNI`) kolonların adına ve sözlük açıklamasına bakıp ortak
  değerin anlamını en doğru anlatan kolonu önerir, gerekçesini yazar.
  Kartta grup satırı (kaç kolon, öneri ve gerekçe) ve üyeler; her üyede
  "Kalsın" seçeneği, öneri seçili gelir. Grup varsa 02.1 kararınızı
  bekler; gönderim `{"ayni": {grup id: kolon}}` (grup id: grubun tablodaki
  ilk kolonu), `profil["ayni_secim"]`'e yazılır. Kalmayan kolonlar
  `profil_teshis.ayni_icerik`'e girer (üretime girmez) ve diğer
  kontrollerin listelerinde gösterilmez. Dil modeli öneremezse (hata ya
  da grupta olmayan kolon) tablodaki ilk kolon önerilir ve bu yazılır.
  Eşik değişip profil yeniden çıkarılınca aynı üyeli grupta önceki öneri
  tekrar sorulmaz; seçim korunur.

**02.1 çözüm önerileri (`fe_agent/kolon_cozum.py`)**
- Üretime girmez denen kolon doğrudan atılmaz: düzeltilebiliyorsa çözüm
  önerilir, kullanıcı seçer; çözüm yoksa ya da Çıkar seçilirse kolon
  kullanılmaz. Ham kolon her durumda üretime girmez (`kusurlu_kolonlar`
  ve 03.3'te düşme değişmedi); çözümün ürettiği YENİ kolon uretilen
  değişken gibi sonraki adımlara (02.2, 02.3, SFA, stabilite, baz) girer.
- Kontroller ve seçenekler (`oneriler`; öneri ilk geçerli seçenek):
  - Kardinalitesi Aşırı Yüksek ve Kimlik Benzeri: serbest metinse
    (farklı değerlerin ortalaması 3 sözcük ya da 25 karakter ve üstü)
    "Metinden özellik çıkar". Değilse "Hedef oranına göre grupla",
    "Kodun ilk karakterleriyle grupla" (değerlerin %80'i aynı uzunlukta,
    ilk k karakter 2 ile 200 grup veriyor), "Seyrek değerleri «Diğer»de
    topla" (en sık 20 değer kalır).
  - Eksik Oranı Yüksek: "«Dolu mu» bayrağı üret" (1/0).
  - Sabit ve Aynı İçerikli kolonlarda çözüm yok.
- Bir seçenek yalnız işe yarayacaksa sunulur (ikili hedefte):
  hedef ya da önek gruplaması eğitim satırlarının bir yarısında
  öğrenilir, diğer yarısında hedefi ayırmalıdır (AUC'nin 0,5'ten farkı
  z ≥ 2,58, `_gruplama_tutarli`); rastgele kimlikte sahte gruplar böyle
  elenir. Dolu bayrağında dolu ve boş satırların hedef oranı farkı aynı
  z ile sınanır. Seyrek toplama ikili hedefte yalnız hedef gruplaması
  tuttuysa sunulur. İkili olmayan hedefte hedefe dayalı seçenekler
  yoktur (seyrek toplama ve bayrak kalır). Geçerli seçeneği olmayan
  kolonda kartta "Çözüm yok" ve nedeni yazar.
- Öğrenme yalnız EĞİTİM satırlarından (`setler(...)["egitim"]`),
  uygulama tablonun tamamına; örnekleme yok. Hedef gruplaması `aralik`
  modülünün kategorik birleştirmesini kullanır (en çok 8 grup, grupta en
  az %5 pay); eğitimde 30 satırdan az görülen ya da hiç görülmeyen değer
  "Seyrek" grubuna düşer. Grup etiketi metindir (G1, G2 ...).
- Metinden özellik (dil modeli yok, kodla, bütün satırlarda, sınırsız):
  `<KOL>_SOZCUK` (sözcük sayısı), `<KOL>_SKOR` (sözcüklerin hedef
  WoE ortalaması; eğitim satırlarında 5 katlı katlama dışı, sızıntı
  yok), hedefle anlamlı ilişkili en çok 10 sözcük için `<KOL>_K_<SÖZCÜK>`
  bayrakları, TF-IDF + NMF ile 8 konu ve `<KOL>_KONU` (K1..K8, "Konu
  yok"). Konu için sklearn gerekir; yoksa konu atlanır, not yazılır.
- Yeni kolon adları: `<KOL>_GRP` (hedef ya da seyrek), `<KOL>_ONEK_GRP`,
  `<KOL>_DOLU`; ad çakışırsa sonuna sayı eklenir.
- Durum: `profil.cozum_oneri` (seçenekler, öneri, gerekçe),
  `profil.cozum_secim` (kullanıcının seçimi), `profil.cozum_bilgi`
  (öğrenilen harita, yeni kolonlar, özet). Yeni kolonlar
  `durum["uretilen"]`'e ve `uretilen_kaynak["cozum"]`'a yazılır; seçim
  değişince eski çözüm kolonları silinir. `cozum_kolonlari_ekle` eksik
  çözüm kolonlarını tabloya hesaplar: `analiz_df`, 02.2 `kural_uygula`
  ve 02.3 `kesif_uygula` bunu çağırır. `_ENRICHED` yalnız kural ya da
  keşif bir şey ürettiyse okunur (`uretim_kolonlari`).
- Kart: çözümü olan kontrollerde detay açık gelir, "Çözüm" sütununda
  seçim kutusu ("(önerilen)" işaretli) ve seçilenin açıklaması; Bulgu
  sütununda kolona özgü gerekçe. Gönderim
  `{"dogrulama": {"adim": "veri_profili", ..., "cozum": {kolon: kod}}}`.
  Kilitli halde seçilen çözüm, yeni kolon(lar) ve tek satır özet; grup
  üyeleri, sözcükler ve konular i balonunda.
- Bilinen eksik: çözüm kolonları `PROJE_HAFIZASI/uretim_kodu.py`
  dosyasına yazılmaz; platform içinde (analiz, model) hesaplanır.

**02.2 Kural Tabanlı Değişken Üretimi: plan isteği**
- `llm.gelenekse_plan_oner` kolon kataloğunu (aile ya da kolon satırları)
  `PLAN_PARCA_KARAKTER` (12.000 karakter) parçalarına böler, parçalar
  `PLAN_PARALEL` (3) eşli gider; 1.000 kolonu aşan sözlükte tek çağrı 90
  saniyeyi aşıyordu. Tek parçada en çok 30, çok parçada parça başına
  payı artı 3 yedek şablon istenir (`_parca_siniri`); toplam en
  çok `PLAN_EN_COK` (30), parçalardan sırayla (her parçadan birer)
  alınır, aynı dönüşüm ve kolonlar bir kez girer. Bir kısım parça düşerse
  plan kalanlardan hazırlanır ve plan metninin sonunda not olarak yazılır;
  hepsi düşerse eski hata metni gelir.

**Uzun tablolarda açıklama kutusu yüksekliği (sayfa donması)**
- Çok satırlı açıklama kutuları (01.2.3 Eksik Sözlük Tanımları, tanım
  kontrolü) yüksekliğini `boylaPlanla` ile TOPLU alır: tek karede önce
  hepsine "auto" yazılır, sonra hepsi okunur, sonra hepsine yazılır (tek
  yerleşim hesabı). Genişlik değişimini tek bir ResizeObserver
  (`BOYLA_GOZCU`) izler. Kutu kutu ölçüm 1.038 satırda sayfayı
  saniyelerce kilitliyordu (tarayıcı "Page Unresponsive"); yazarken
  yalnız o kutu hemen ölçülür (`_boylaHemen`).

**Tablo başlıkları**
- `.dg-tablo th` normal yazılır (büyük harfe çevrilmez); bütün kart
  tablolarında başlıklar yazıldığı gibi görünür.

## Tarayıcıda hatırlanan tercihler

| Anahtar | Ne |
|---|---|
| `amp_renk_modu` | Görünüm (renk modu): `acik` (Beyaz), `sepya`, `koyu` (eski `gri` kaydı Koyu açılır) |
| `amp_akis_acik` | İş Akışı bölmesi açık / kapalı |
| `amp_dg_alt` | Model Değişkenleri'nde açık görünüm |
| `fe_agent_calisma_id` | Açık çalışmanın kimliği |
