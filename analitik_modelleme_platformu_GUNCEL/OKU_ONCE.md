# Analitik Modelleme Platformu — teslim notu

Bu tur: **yeni mesajlar platformun yazı standardında**. Yapıştır (fe_agent): `akis_faz01.py`

- Kaynak tablo özeti, alt alta ekleme sonucu, Mod C veri seti özeti ve
  birleştirme hata mesajları madde işaretli düz metin yerine "  Etiket : Değer"
  satırlarıyla yazılıyor; arayüz bunları diğer adımlardaki gibi hizalı
  etiket–değer tablosu olarak çiziyor.
- Hata sebebindeki ":" karakterleri etiket ayıracıyla karışmasın diye " · "
  olarak yazılıyor ("Ana tablo bulunamadı · …").

---

Önceki tur: **seçilen tabloların satır × kolon sayısı**. Yapıştır (fe_agent): `akis_faz01.py`

- Kaynak tablo özeti her tablo için kesin satır ve kolon sayısını yazıyor:
  "• FPD_TXN_FEATS_2025 · 1.234.567 satır × 1.040 kolon". Başlıkta toplam
  satır var; yanıltıcı olan "toplam kolon" kaldırıldı.
- Alt alta ekleme mesajı tablo adlarını tekrar saymıyor; baz veri setinin
  satır × kolon sayısını ve kayıt yerini yazıyor.

---

Önceki tur: **aynı kolonlu tablolar alt alta ekleniyor; birleştirme sonucu klasöre yazılıyor**.
Yapıştır (fe_agent): `akis_faz01.py`, `akis_sohbet.py`, `akis_durum.py`, `veri_kaynak.py` · (webapp) `backend.py`

- Seçilen tabloların hepsi aynı kolonlara sahipse (ör. FPD_TXN_FEATS_2025 ve
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
- Ad eşleşmesi parça parça: MONTH_CNT gibi sayaç/tutar kolonları listelenmez;
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
  parçalarında bir arada tutulur; özet satırı "Aynı SM_ID: bir arada
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
— toplam, son 3 ay (KART_ISLEM.TUTAR)" gibi türetilir; kayıt sayısı
kolonları "KART_ISLEM tablosundaki kayıt sayısı, son 6 ay" olur. Kaynağında
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
