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
  (aynı anda tek kart).
- Açıklamalar yalnız tanıtır. Her biri ortada, iki yanında çizgi olan
  başlıkla ve altında ortalı kısa girişle başlar.
  - Model Platformu Nasıl Çalışır: giriş (beş faz, öneri ve onay);
    ardından dört alt bölüm, her biri ortada çizgili alt başlıkla ve
    aralarında geniş boşlukla:
    - Beş Faz: tek kutu içinde süreç şeridi; her fazda kırmızı numara,
      mürekkep halkalı daire içinde kırmızı simge (daireler kesik çizgiyle
      bağlı), faz adı, özet, kısa kırmızı çizgi ve adımlar; ad, özet ve
      adımlar bütün fazlarda aynı hizada.
    - Katkılar: dört kutu (Akıllı değişken üretimi, Hız ve verimlilik,
      Sade ve güçlü model, Her modele uygun yapı); kırmızı daire içinde
      simge, başlık ve yazı ortada; sayısal iddia yok.
    - Sayfalar: Çalışma Alanları kartlarıyla aynı düzen: solda büyük
      çizim, sağında ad ve tek cümle; üçerli satırlar, son satır ortada;
      Model Sohbeti soluk ve Hazırlanıyor rozetli.
    - Güvenceler: açık zeminli tek kutu, dört bölme ince çizgiyle
      ayrılır; her bölmede kırmızı halka içinde simge, yanında başlık,
      altında kısa açıklama.
    Bütün kutular 2 px mürekkep kenarlı. 1300 px altında fazlar üçerli
    (satır sonunda bağlantı çizgisi yok),
    katkılar ve güvenceler 2x2, sayfalar ikişerli dizilir.
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
