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
| `katib_arkaplan` | `katib_arkaplan.png` | Logonun arkasındaki İstanbul çizimi (saydam, 3:1; ortası boş) |
| `anasayfa` | `anasayfa.png` | Sol bar: ANA SAYFA |
| `model_platformu` | `model_platformu.png` | Sol bar: MODEL PLATFORMU başlığının ikonu |
| `model_akisi` | `model_akisi.png` | Sol bar: Model Akışı |
| `gosterge_paneli` | `gosterge_paneli.png` | Sol bar: Model Göstergeleri ve Gösterge Paneli |
| `degiskenler` | `degiskenler.png` | Sol bar: Değişkenler |
| `ozet` | `ozet.png` | Sol bar: Özet |
| `katible_sohbet` | `katible_sohbet.png` | Sol bar: Model Sohbeti ve KATIB'le Sohbet |
| `gorunum` | `gorunum.png` | Sol bar: Görünüm düğmesi |
| `arsiv` | `arsiv.png` | Sol bar: Arşiv |
| `yeni_calisma` | `yeni_calisma.png` | Sol bar: Yeni Çalışma |
| `robot_alt` | `robot_alt.png` | Sol bar: ÇALIŞMA ALANLARI başlığının üstünde, çift çizgiye yaslanmış robot, kitaplar ve kupa |
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

**Yazı tipi:** bütün arayüz tek aile, **Newsreader** (New Yorker esintili
editoryal serif; `style.css` içinde gömülü, dış font sunucusuna bağlanmaz,
SIL Open Font License). Gövde 400; başlıklar ve sol bar satırları 600;
vurgu 700. Rakamlar tablolarda eşit genişlikte.

**Sol bar**
- Tepede KATIB logosu; arkasında barın eni boyunca İstanbul çizimi (solda
  Galata, sağda tarihi yarımada ve vapur), logo ortadaki boşlukta.
- Logonun altında ince çizgi, ardından **Ana Sayfa** (kendi sayfasını
  açar; içerik hazırlanıyor).
- Çift çizgiye (masa) yaslanmış robot, kitaplar ve kupa (`robot_alt`);
  çizginin altında **ÇALIŞMA ALANLARI** başlığı, altında Model Platformu
  kümesi ve kilitli alanlar.
- **Model Platformu:**
  - Model Akışı
  - Model Göstergeleri
  - Değişkenler (Veri ve Sözlük, Dağılım ve SFA, Değişken Kontrolleri)
  - Özet
  - Model Sohbeti (kapalı)
- Ayrı bloklar: KATIB'le Sohbet ve Gösterge Paneli (kapalı, hazırlanıyor).
- Altta ince çizgi, altında:
- **Görünüm:** üç renk modu: Beyaz (varsayılan), Sepya (sıcak kâğıt
  tonu), Gri (açık gri zemin, koyu yazı). Anahtar kodla çizilmiş üç
  bölmeli kapsül: güneş (Beyaz), taralı sepya disk (Sepya), ay (Gri);
  simgeye basınca o mod seçilir; seçili bölme açık pembe zeminli, altında
  kırmızı çizgi (sol bardaki seçili satırla aynı dil). Düğmenin
  başka bir yerine basınca sıradaki moda geçilir.
- **Arşiv:** kayıtlı çalışmalar; birine basınca kaldığı yerden açılır.
- **Yeni Çalışma:** yeni çalışma açar; açık çalışma silinmez, Arşiv'de kalır.

Uygulama ekranın tamamını kullanır. Sol bar kaydırmasızdır ve sıkı
ölçüdedir (tasarım eni 300 px, satırlar 32 px, yazılar 11.5 px). Ekran yetmezse içerik sığacak
oranda küçülür, bar eni de aynı oranda daralır; büyük ekranda büyümez.

**Model Akışı**
- Üstte **İş Akışı** barı:
  - solda İş Akışı düğmesi;
  - yanında bulunulan faz ve adım;
  - sağda tamamlanan / toplam adım.
- İş Akışı düğmesi beş fazı ve adımları solda bir bölmede açar. Bölme
  alanın en altına kadar uzanır ve aynı düğmeyle kapanana kadar açık kalır.
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
| `amp_dg_alt` | Değişkenler'de açık görünüm |
| `fe_agent_calisma_id` | Açık çalışmanın kimliği |
