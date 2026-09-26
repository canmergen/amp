# Analitik Modelleme Platformu — teslim notu

Bu tur: **dönem notu kısa + maddeli**. Yapıştır: `akis_faz01.py`, `app.js`, `style.css`

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
gap + çoklu tekrar. Ayrıca her adım bloğuna ince Akbank kırmızısı çerçeve.

> **Deploy sonrası "Yeni Çalışma"ya bas.**

---

## Kopyala-yapıştır sırası

**Library Editor (`python/fe_agent/`):**
`akis_durum.py` → `akis_panel.py` → `akis_faz01.py`
**Webapp:** `style.css` → `app.js`

---

## 1. Adım bloklarına 3px Akbank kırmızısı çerçeve

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
