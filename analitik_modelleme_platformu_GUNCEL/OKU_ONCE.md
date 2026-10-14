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
| `karsilama` | `robot_welcome.png` | Sohbetteki ilk robot |
| `bot` | `robot_chat.png` | Normal konuşma |
| `dusunme` | `robot_think.png` | Arkada iş sürerken |
| `user` | `robot_llm_person.png` | Kullanıcı balonu |

Görsel bulunamazsa yerinde boşluk kalır, sayfa bozulmaz.

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

Uygulama ekranın tamamını kullanır. Alanlar (sol bar, İş Akışı bölmesi,
çalışma alanı) zeminden boşlukla ayrılan yuvarlak köşeli kartlardır. Açık
ve koyu tema aynı düzeni kullanır.

**Sol bar**
- Açık temada beyaz, koyu temada siyah; altta kırmızı çizgi dalgaları.
  Dalgalar ve bütün çizimler kodla (SVG) çizilir, görsel dosyası yoktur.
- Tepede KATIB logosu.
- **MODEL PLATFORMU:**
  - Model Akışı
  - Gösterge Paneli
  - Değişkenler (Veri ve Sözlük, Dağılım ve SFA, Değişken Kontrolleri)
  - Özet
  - KATIB'le Sohbet (kapalı)
- **YAKINDA:** KATIB'le Sohbet ve Gösterge Paneli (kapalı, hazırlanıyor).
- Seçili satır açık pembe zeminli, solunda kırmızı çizgi, ikonu kırmızı
  kutuda.
- **Renk Modu:** açık / koyu tema anahtarı.
- **Arşiv:** kayıtlı çalışmalar; birine basınca kaldığı yerden açılır.
- **Yeni Çalışma:** yeni çalışma açar; açık çalışma silinmez, Arşiv'de kalır.

Sol bar kaydırmasızdır. Tasarım eni 248 px; ekran kısaysa içerik sığacak
oranda küçülür, bar eni de aynı oranda daralır.

**Model Akışı**
- Solda **İş Akışı** bölmesi: beş faz numaralı daireli dikey çizelge
  olarak. Çalışılan faz pembe kutuda, geçilen faz yeşil. Faza basınca
  adımları açılır; görülmüş bir adıma basınca sohbet o adımın bloğuna
  kayar.
- Bölme, çalışma alanının üstündeki barda bulunan **İş Akışı** düğmesiyle
  açılıp kapanır. Seçim hatırlanır; seçim yoksa geniş ekranda (en az
  1180 px) açık, dar ekranda kapalı başlar.
- Çalışma alanının üstündeki bar: İş Akışı düğmesi, bulunulan yer
  (İş Akışı › faz › adım), sağda ilerleme çubuğu ve tamamlanan / toplam adım.
- Adımlar blok blok ilerler. Blok başlığı: küçük kırmızı adım numarası,
  adım adı, altında adımın kısa açıklaması; sağda durum rozeti ve
  "Geri Dön". Yanıt bekleyen blok kırmızı kenarlıdır.
- Sohbet açılana kadar yazı kutusunun yerinde bilgi notu durur.

**Başlangıç Seçimi (01.1)**
- Karşılama metni (`fe_agent/akis_metin.py` → `KARSILAMA`) kartlı bölüm
  olarak çizilir: ilk kalın başlık ve altındaki metin tanıtım kartı,
  sonraki kalın başlıklı bölümler yan yana bilgi kutuları, gövdesi
  olmayan son kalın satır başlangıç kartlarının üstündeki çağrı.
  Yalnız `**...**` satırları başlık sayılır.
- Başlangıç kartları yan yana; her kartta ikon, açıklama ve üç madde
  (`MOD_SECENEKLERI` → `ikon`, `maddeler`):
  - **A:** Baz Veri Seti Mevcut.
  - **B:** Kaynak Tablolar Mevcut.
  - **C:** Otomatik Pilot (şu an kapalı, "Yakında").

**Fazlar**
1. Çalışma Kurulumu
2. Değişken Mühendisliği
3. Veri Anlama ve Hazırlama
4. Değişken Değerlendirme
5. Modelleme ve Finalizasyon

## Tarayıcıda hatırlanan tercihler

| Anahtar | Ne |
|---|---|
| `amp_renk_modu` | Açık / koyu tema |
| `amp_akis_acik` | İş Akışı bölmesi açık / kapalı |
| `amp_dg_alt` | Değişkenler'de açık görünüm |
| `fe_agent_calisma_id` | Açık çalışmanın kimliği |
