# Geleneksel Değişken Üretimi: Sınıflandırma Modelleri İçin Kapsamlı Liste

Bu belge, sınıflandırma modellerinde (ikili, çok sınıflı, segmentli ve tek
model) veri bilimcilerin elle ya da kural tabanlı ürettiği "geleneksel"
değişkenleri maddeler. Amaç, platformun **02.2 Kural Tabanlı Değişken
Üretimi** adımının neyi kapsadığını ve neyi kapsayabileceğini tek yerde
görmek.

## Nasıl okunur

Her maddenin sonunda iki etiket var:

- **Uygun:** hangi model türünde kullanıldığı.
  - **İkili:** iki sınıflı hedef (temerrüt var / yok, fraud var / yok).
  - **Çok sınıflı:** üç ve daha fazla sınıf (ürün tercihi, risk sınıfı,
    kayıp nedeni). Sınıflar sıralıysa (A < B < C) ayrıca **sıralı**
    denir.
  - **Segmentli:** her segment için ayrı model (bireysel / KOBİ, yeni /
    mevcut müşteri gibi).
  - **Tek model:** bütün nüfus tek modelde; segment varsa değişken olarak
    girer.
  - **Hepsi:** dört türün hepsinde.
- **Platformda:**
  - **Var (02.2):** Kural Tabanlı Değişken Üretimi bugün üretiyor (delta,
    oran, log, rank, winsor).
  - **Var (SFA):** Tek Değişken Analizi kararlarında seçenek olarak var
    (eksik değer, aykırı, dönüşüm, ayrıklaştırma).
  - **Yok:** bugün üretilmiyor.

Örneklerdeki kolon adları kurgusaldır, yalnız yapıyı göstermek içindir.

---

## 0. Bütün maddeler için geçerli kurallar

Bunlar değişken değil, değişkenin güvenilir olmasının şartıdır.

1. **Gözlem tarihi sınırı.** Her değişken yalnız gözlem tarihinden
   (skorlama anından) önceki veriyle hesaplanır. Hedef penceresine düşen
   tek bir gün bile sızıntıdır.
2. **Yalnız eğitim setinden öğren.** Kesim noktaları (winsor, binning),
   ortalama ve medyan (doldurma), sıra ızgarası (rank), hedef kodlama
   oranları yalnız train (MS) satırlarından öğrenilir; test (OOS) ve
   validasyon (OOT) satırlarına aynen uygulanır. Platform 02.2'de bunu
   yapıyor.
3. **Hedefi kullanan kodlamalar kat dışı (out of fold) hesaplanır.** Hedef
   kodlama ve WoE, satırın kendi hedefini görmemeli; yoksa model ezberler.
4. **Sıfıra bölme.** Oran değişkenlerinde payda sıfırsa sonuç boş (NaN)
   olur, ayrıca "payda sıfır" işareti eklenebilir. Sonsuz değer
   bırakılmaz. Platform 02.2'de bunu yapıyor.
5. **Ad ve açıklama.** Üretilen her değişkenin adı kaynağını ve işlemini
   söylemeli (TXN_OUT_AMT_L30D__DIV__TXN_OUT_AMT_L90D), açıklaması
   sözlüğe yazılmalı.
6. **Kararlılık.** Üretilen değişken dönemler arasında kararlı olmalı
   (PSI). Kararsız değişken, iyi ayrıştırsa da modelde risktir.

---

## 1. Tek değişkenli sayısal dönüşümler

Bir kolondan bir kolon üretir. Dağılımı modele uygun hâle getirir.

1. **Logaritma (log1p).** Sağa çarpık tutar ve adet değişkenleri için
   (işlem tutarı, bakiye). Negatif değer varsa önce kaydırma ya da işaretli
   log (sign(x) · log1p(|x|)). Uygun: hepsi, özellikle doğrusal modeller.
   Platformda: Var (02.2), Var (SFA).
2. **Karekök, küp kök.** Logdan yumuşak çarpıklık düzeltmesi; sıfırı
   korur. Uygun: hepsi. Platformda: Yok.
3. **Box-Cox / Yeo-Johnson.** Dağılımı normale yaklaştıran parametreli
   dönüşüm; parametre train'den öğrenilir. Yeo-Johnson negatif değeri de
   kabul eder. Uygun: doğrusal modeller, çok sınıflı lojistik. Platformda:
   Yok.
4. **Üstel / kare / polinom terimler.** Eğilim eğriyse (U şekli) x² gibi
   terimler. Uygun: doğrusal modeller. Platformda: Var (SFA, "ustel").
5. **Winsorize (uç kırpma).** %1 ile %99 ya da %5 ile %95 dışındaki
   değerler sınıra çekilir; sınırlar train'den. Uygun: hepsi. Platformda:
   Var (02.2), Var (SFA).
6. **Sıra / yüzdelik (rank, percentile).** Değerin train dağılımındaki
   yüzdeliği (0 ile 1 arası). Uç değerlere dayanıklı. Uygun: hepsi.
   Platformda: Var (02.2), Var (SFA, "sira").
7. **Ölçekleme.** z-skor ((x − ortalama) / std), min-max, robust ölçek
   ((x − medyan) / çeyrekler arası açıklık). Ağaç modellerde gereksiz;
   lojistik, SVM, sinir ağında gerekli. Uygun: doğrusal ve çok sınıflı
   softmax. Platformda: Yok.
8. **İşaret değişkenleri.** x > 0, x = 0, x < 0 bayrakları; "hiç işlem
   yok" ile "az işlem var" ayrımı için. Uygun: hepsi. Platformda: Yok.
9. **Eşik bayrakları.** İş kuralından gelen eşikler: gecikme gün sayısı ≥
   30, limit kullanımı ≥ %90, bakiye < 0. Uygun: hepsi, özellikle kural
   tabanlı skorkartlar. Platformda: Yok.
10. **Yuvarlama ve birim düzeltme.** Kuruşu liraya, günü aya çevirme;
    tutarı enflasyon ya da kur ile reel hâle getirme (çok dönemli veride
    önemli). Uygun: hepsi. Platformda: Yok.

## 2. Eksik değer değişkenleri

1. **Eksik işareti.** Kolon boşsa 1. Eksikliğin kendisi bilgi taşıyorsa
   (bilgi verilmemiş, ürün yok) çok güçlüdür. Uygun: hepsi. Platformda:
   Var (SFA, "isaret").
2. **Doldurma.** Medyan, sıfır ya da sabit; hangisi anlamlıysa (işlem yoksa
   0, bilinmiyorsa medyan). Değer train'den. Uygun: hepsi. Platformda:
   Var (SFA, "medyan", "sabit").
3. **Kategorik eksik.** Boş değer ayrı bir kategori ("Bilinmiyor").
   Uygun: hepsi. Platformda: Var (SFA, "missing").
4. **Satırdaki eksik sayısı / oranı.** Bir müşterinin kaç alanı boş;
   eksik bilgi profili. Uygun: hepsi. Platformda: Yok.
5. **Grup bazlı doldurma.** Eksik değeri segmentin ya da benzer grubun
   medyanıyla doldurma. Uygun: segmentli, tek model. Platformda: Yok.

## 3. Ayrıklaştırma (binning)

Sürekli değişkeni aralıklara böler.

1. **Eşit aralık / eşit frekans (çeyrek, ondalık dilim).** Basit; hedefe
   bakmaz. Uygun: hepsi. Platformda: Yok (ayrı değişken olarak).
2. **Hedefe göre aralıklar (supervised binning).** Karar ağacı ya da
   ki-kare birleştirme (ChiMerge) ile hedef oranı farklı aralıklar.
   Uygun: ikili; çok sınıflıda sınıf başına ya da çok sınıflı entropiyle.
   Platformda: Var (SFA, "onerilen" aralıklar).
3. **Monoton aralıklar.** Hedef oranı aralıklar boyunca tek yönde artan
   ya da azalan aralıklar; skorkartın açıklanabilirliği için. Uygun:
   ikili, sıralı çok sınıflı. Platformda: Yok.
4. **İş kuralı aralıkları.** Yaş grupları, gelir dilimleri, gecikme
   kovaları (0, 1 ile 29, 30 ile 59, 60 ile 89, 90 ve üstü). Uygun: hepsi.
   Platformda: Yok.
5. **Aralık başına en az nüfus.** Her aralıkta yeterli gözlem ve yeterli
   hedef sayısı (ör. en az %5 nüfus, en az 30 olay); segmentli modelde
   bu her segment için ayrı kontrol edilir.

## 4. Hedefe dayalı kodlamalar

Hedefi kullanır; kat dışı hesaplanmazsa sızıntı yaratır.

1. **WoE (Weight of Evidence).** Her aralık ya da kategori için
   ln(olay olmayan payı / olay payı). Lojistik skorkartın standart girdisi.
   Uygun: ikili. Platformda: Yok (aralıklar SFA'da var, WoE kolonu yok).
2. **Sınıf başına WoE (bire karşı hepsi).** Çok sınıflıda her sınıf için
   "bu sınıf mı, değil mi" WoE'si; K sınıf için K kolon. Uygun: çok
   sınıflı. Platformda: Yok.
3. **Hedef ortalaması kodlaması (target / mean encoding).** Kategorinin
   hedef oranı; nadir kategoriler genel orana doğru yumuşatılır
   (smoothing). Yüksek kardinaliteli kategorilerde (il, meslek, işyeri
   kategorisi) çok etkili. Uygun: ikili. Platformda: Yok.
4. **Sınıf başına hedef kodlaması.** Çok sınıflıda kategori başına her
   sınıfın olasılığı; K sınıf için K − 1 kolon (biri gereksiz). Uygun: çok
   sınıflı. Platformda: Yok.
5. **Birikimli hedef kodlaması.** Sıralı çok sınıflıda (A < B < C) "en az
   B olma oranı", "en az C olma oranı". Sıralı yapıyı korur. Uygun:
   sıralı çok sınıflı. Platformda: Yok.
6. **Segment içi hedef kodlaması.** Oranlar segment içinde hesaplanır;
   tek modelde segment × kategori etkileşimini yakalar. Uygun: segmentli,
   tek model. Platformda: Yok.

## 5. Kategorik kodlamalar (hedefe bakmayan)

1. **One-hot (gölge değişken).** Az kategorili kolonlar için; biri
   referans bırakılır. Uygun: hepsi. Platformda: Yok.
2. **Sıralı kodlama.** Doğal sırası olan kategoriler (eğitim düzeyi, risk
   notu). Uygun: hepsi. Platformda: Yok.
3. **Frekans / sayım kodlaması.** Kategorinin nüfustaki payı. Uygun:
   hepsi. Platformda: Yok.
4. **Nadir kategorileri birleştirme.** Payı belli bir eşiğin altındaki
   kategoriler "Diğer" altında; eşik train'den. Uygun: hepsi. Platformda:
   Var (SFA, kategorik gruplama önerisiyle sınırlı).
5. **Hiyerarşi kodlaması.** İl → bölge, meslek → meslek grubu, işyeri
   kodu → sektör. Uygun: hepsi. Platformda: Yok.
6. **Kategori kesişimi.** İki kategorinin birleşimi (ürün × kanal).
   Uygun: hepsi, dikkatli (kardinalite patlar). Platformda: Yok.

## 6. Zaman pencereli davranış değişkenleri

Bankacılıkta en çok değişken buradan çıkar. Pencere seti örneği: son 3,
7, 14, 30, 60, 90, 180, 360 gün ya da son 1, 3, 6, 12 ay.

### 6.1 Toplama (aggregation)

1. **Toplam, adet, ortalama, medyan, en büyük, en küçük, standart sapma**
   her pencerede (TXN_OUT_AMT_L30D, TXN_OUT_CNT_L30D, TXN_OUT_AMT_AVG_L30D).
   Uygun: hepsi. Platformda: Yok (kaynak tabloda hazır geliyorsa
   kullanılıyor; üretilmiyor).
2. **Ayrı değer sayısı.** Farklı karşı taraf, farklı işyeri, farklı kanal,
   farklı gün sayısı. Uygun: hepsi. Platformda: Yok.
3. **Aktif gün / aktif ay sayısı.** Pencerede işlem olan gün ya da ay.
   Uygun: hepsi. Platformda: Yok.

### 6.2 Pencereler arası karşılaştırma

1. **Oran (hızlanma / yavaşlama).** Son 30 gün / son 90 gün, son 3 ay /
   son 12 ay. 1'den büyükse son dönemde artış. Uygun: hepsi. Platformda:
   Var (02.2, "oran").
2. **Fark (delta).** Son 30 gün − önceki 30 gün. Uygun: hepsi. Platformda:
   Var (02.2, "delta").
3. **Büyüme oranı.** (son − önceki) / önceki. Uygun: hepsi. Platformda:
   Yok (oran ve delta ayrı var, büyüme oranı yok).
4. **Ortalamaya göre normalize.** Son 30 günün aylık ortalaması / son 12
   ayın aylık ortalaması (pencere uzunluğu farkını giderir). Uygun: hepsi.
   Platformda: Yok.

### 6.3 Eğilim ve oynaklık

1. **Eğim (trend).** Aylık seriye doğru uydurup eğimi (son 6 ya da 12
   ay). Uygun: hepsi. Platformda: Yok.
2. **Değişkenlik katsayısı.** std / ortalama; düzensiz davranış. Uygun:
   hepsi. Platformda: Yok.
3. **Art arda artış / azalış sayısı.** Kaç ay üst üste arttı. Uygun:
   hepsi. Platformda: Yok.
4. **En yüksek ayın payı.** En büyük aylık tutar / toplam; tek seferlik
   sıçrama. Uygun: hepsi. Platformda: Yok.

### 6.4 Zamanlama (recency, tenure, frequency)

1. **Son olaydan bu yana geçen süre.** Son işlem, son gecikme, son
   başvuru, son limit artışı (TMSNCLST). Uygun: hepsi. Platformda: Yok
   (kaynakta hazırsa kullanılıyor).
2. **İlk olaydan bu yana geçen süre.** Müşteri ya da ürün yaşı (TMSNCFRST).
   Uygun: hepsi. Platformda: Yok.
3. **Olaylar arası ortalama süre, en uzun boşluk.** Uygun: hepsi.
   Platformda: Yok.
4. **RFM.** Yakınlık, sıklık, tutar; ayrı ayrı ya da birleşik skor.
   Uygun: hepsi. Platformda: Yok.

### 6.5 Takvim ve gün içi davranış

1. **Saat dilimi payları.** Gece (00 ile 06), sabah, öğleden sonra, akşam
   işlemlerinin payı (H00_06 adedi / toplam adet). Uygun: hepsi, özellikle
   fraud. Platformda: Yok (adetler hazırsa oran 02.2 ile üretilebilir).
2. **Hafta sonu / hafta içi payı.** Uygun: hepsi. Platformda: Yok.
3. **Ay sonu / maaş günü yoğunluğu.** Maaş yatışından sonraki 3 günde
   harcama payı. Uygun: hepsi. Platformda: Yok.
4. **Mevsimsellik.** Aynı ayın geçen yıla oranı. Uygun: hepsi.
   Platformda: Yok.

### 6.6 Akış ve yön

1. **Net akış.** Gelen − giden tutar; gelen / giden oranı. Uygun: hepsi.
   Platformda: Var (02.2, delta ve oran ile, kolonlar hazırsa).
2. **Kanal / ürün payı.** Mobil, internet, şube, ATM payı; havale, kart,
   fatura payı. Uygun: hepsi. Platformda: Yok.
3. **Karşı taraf yoğunlaşması.** En büyük karşı tarafın payı, HHI
   (payların karelerinin toplamı), entropi. Uygun: hepsi. Platformda: Yok.
4. **Kendi hesapları arası transfer payı.** Uygun: hepsi. Platformda: Yok.

## 7. Kredi riskine özgü değişkenler

1. **Limit kullanım oranı.** Bakiye / limit; son, ortalama, en yüksek;
   pencere karşılaştırmaları. Uygun: hepsi. Platformda: Yok.
2. **Gecikme değişkenleri.** En büyük gecikme gün sayısı, gecikmeli ay
   sayısı, son gecikmeden bu yana süre, 30+ / 60+ / 90+ gecikme adetleri
   pencere başına. Uygun: hepsi. Platformda: Yok.
3. **Ödeme davranışı.** Ödenen / ekstre borcu, asgari ödeme oranı, tam
   ödeme yapılan ay sayısı. Uygun: hepsi. Platformda: Yok.
4. **Borç yükü.** Toplam borç / gelir, taksit / gelir, borç artış hızı.
   Uygun: hepsi. Platformda: Yok.
5. **Nakit kullanımı.** Nakit avans payı, nakit çekim sıklığı. Uygun:
   hepsi. Platformda: Yok.
6. **Kredi büro değişkenleri.** Sorgu sayısı (son 1, 3, 6, 12 ay), yeni
   açılan ürün sayısı, aktif ürün sayısı, kapanan ürün payı. Uygun:
   hepsi. Platformda: Yok.
7. **Ürün sahipliği.** Ürün sayısı, ürün çeşitliliği, maaş müşterisi mi.
   Uygun: hepsi. Platformda: Yok.
8. **Teminat ve oran.** Kredi / teminat değeri (LTV), vade, kalan vade
   payı. Uygun: hepsi. Platformda: Yok.

## 8. Etkileşim ve oran değişkenleri

1. **İki değişkenin oranı ve farkı.** Anlamı olan çiftler (gelen / giden,
   kullanım / limit). Uygun: hepsi. Platformda: Var (02.2).
2. **Çarpım.** İki etkinin birlikte görülmesi (yeni müşteri × yüksek
   kullanım). Uygun: doğrusal modeller (ağaçlar kendisi bulur).
   Platformda: Yok.
3. **Koşullu değişkenler.** Bir değişken yalnız belli bir durumda anlamlı
   (kredi kartı varsa limit kullanımı; yoksa ayrı işaret). Uygun: hepsi.
   Platformda: Yok.
4. **Aralık × aralık etkileşimi.** İki ayrıklaştırılmış değişkenin
   kesişim hücreleri. Uygun: ikili skorkartlar. Platformda: Yok.

## 9. Grup ve segmente göre göreli değişkenler

1. **Grup içi yüzdelik.** Müşterinin değeri, kendi segmenti (yaş grubu,
   gelir dilimi, il) içinde hangi yüzdelikte. Uygun: tek model (segment
   farkını değişken içinde taşır), segmentli. Platformda: Yok.
2. **Grup ortalamasından sapma.** (x − grup ortalaması) / grup std
   (benzerlerine göre z-skor). Uygun: tek model, segmentli. Platformda:
   Yok.
3. **Grup oranı.** Müşteri değeri / grup medyanı. Uygun: tek model,
   segmentli. Platformda: Yok.
4. **Segment göstergesi.** Segment kodu değişken olarak (one-hot ya da
   hedef kodlama). Uygun: tek model. Segmentli modelde segment içinde
   sabit olduğu için anlamsız. Platformda: Yok.
5. **Segment × değişken etkileşimi.** Bir değişkenin etkisi segmente göre
   değişiyorsa (gelirin etkisi bireyselde ve KOBİ'de farklı). Uygun: tek
   model. Platformda: Yok.

## 10. Model türüne göre farklar

### 10.1 İkili sınıflandırma

- Skorkart (lojistik) kullanılıyorsa: hedefe göre monoton aralıklar + WoE
  standarttır; her değişken açıklanabilir, işaretleri iş mantığıyla uyumlu
  olmalı.
- Ağaç modellerde (gradient boosting): ölçekleme ve WoE gerekmez; ham
  değer, oran, pencere değişkenleri ve eksik işareti yeter. Hedef
  kodlaması yüksek kardinaliteli kategorilerde yine işe yarar.
- Seçim ölçüleri: IV, Gini, KS, C-value. Platform SFA'da IV ve C-value
  ölçüyor.
- Dengesiz hedef (olay oranı %1 ile %3): aralık başına en az olay sayısı
  kuralı daha önemli; hedef kodlamada yumuşatma şart.

### 10.2 Çok sınıflı sınıflandırma

- WoE ve hedef kodlama sınıf başınadır (bire karşı hepsi); kolon sayısı
  sınıf sayısıyla çarpılır, seçim daha önemli hâle gelir.
- Sıralı sınıflarda (risk notu A, B, C) birikimli kodlama ve sıralı
  modeller (ordinal lojistik) sırayı korur; sırasız sınıflarda (ürün
  tercihi) korumaz.
- Çok sınıflı lojistikte (softmax) ölçekleme ve çarpıklık düzeltmesi
  gerekir.
- Sınıf dengesizliği: küçük sınıflar için aralık ve kategori başına yeterli
  gözlem kontrolü ayrı yapılır; nadir kategorileri birleştirme daha sık
  gerekir.
- Seçim ölçüleri: sınıf başına IV, çok sınıflı karşılıklı bilgi (mutual
  information), ANOVA F / ki-kare.

### 10.3 Segmentli modeller

- Her segment için ayrıklaştırma, WoE, winsor sınırları ve doldurma
  değerleri ayrı öğrenilir; bir segmentin kesim noktası öbürüne
  uygulanmaz.
- Bir segmentte sabit ya da çok boş olan değişken o segmentin modelinden
  çıkar, öbüründe kalabilir.
- Segment içi kararlılık (PSI) ayrı ölçülür; küçük segmentte değişken
  sayısı nüfusa göre sınırlı tutulur.
- Segment göstergesi değişken olarak kullanılmaz.

### 10.4 Tek model (segmentsiz)

- Segment farkı değişkenlerle taşınır: segment göstergesi, segment ×
  değişken etkileşimi, grup içi yüzdelik ve sapma (bölüm 9).
- Ölçek farkı büyük olan nüfuslarda (bireysel ve kurumsal tutarlar) oran
  ve yüzdelik değişkenleri ham tutardan daha kararlıdır.
- Kesim noktaları bütün nüfustan öğrenilir; küçük grupların davranışı
  bastırılabilir, bu yüzden grup içi göreli değişkenler önemlidir.

## 11. Üretimden sonra eleme ve kalite

1. **Boş ve sabit.** Eksik oranı çok yüksek ya da tek değerli üretilmiş
   değişken çıkar. Platformda: Var (02.1 ve 01.2.3.1).
2. **Yüksek korelasyon.** Birbirine çok benzeyen değişken çiftlerinden
   (aynı pencerenin toplamı ve ortalaması gibi) daha güçlü ve daha kararlı
   olan kalır; VIF ile çoklu doğrusallık kontrolü. Platformda: korelasyon
   eleme var (04 Aday Değişken Seti), VIF yok.
3. **Ayrıştırma gücü.** IV, Gini, KS, C-value. Platformda: Var (SFA).
4. **Kararlılık.** PSI (değişken dağılımı), CSI; dönemler arası WoE ve
   hedef oranı tutarlılığı. Platformda: PSI var (03 Stabilite), CSI ve
   dönemler arası WoE tutarlılığı yok.
5. **Sızıntı kontrolü.** Hedefle aşırı yüksek ilişki, adında ya da
   açıklamasında hedef döneminden bilgi taşıyan değişken. Platformda:
   Var (04 Sızıntı Kontrolü: train satırlarında hedefle mutlak korelasyonu
   0,95 üstü olan değişken aday sete alınmaz); ad ve açıklama taraması yok.
6. **İş mantığı kontrolü.** Etki yönü beklenene uyuyor mu (gecikme arttıkça
   risk artmalı). Skorkartta ters işaretli değişken çıkar ya da
   aralıkları yeniden birleştirilir. Platformda: Yok.

---

## Özet: platformda bugün olan ve olmayan

| Grup | Bugün var | Eklenebilir (öncelik önerisi sırayla) |
|---|---|---|
| Tek değişkenli dönüşüm | log, rank, winsor (02.2); log, üstel, sıra, winsor (SFA) | işaret bayrakları, eşik bayrakları, Yeo-Johnson, ölçekleme |
| Eksik değer | medyan, sabit, işaret, kategorik eksik (SFA) | satırdaki eksik sayısı, grup bazlı doldurma |
| Ayrıklaştırma | hedefe göre önerilen aralıklar (SFA) | monoton aralıklar, iş kuralı kovaları |
| Hedef kodlama | yok | WoE (ikili), sınıf başına WoE ve hedef kodlama (çok sınıflı), birikimli (sıralı) |
| Kategorik kodlama | nadir kategori gruplama (SFA, sınırlı) | frekans kodlama, one-hot, hiyerarşi |
| Pencere karşılaştırma | oran, delta (02.2) | büyüme oranı, normalize oran |
| Eğilim ve oynaklık | yok | eğim, değişkenlik katsayısı, art arda artış |
| Zamanlama ve takvim | kaynakta hazırsa | saat dilimi ve hafta sonu payları (adetlerden oranla) |
| Kredi riskine özgü | kaynakta hazırsa | limit kullanımı, gecikme kovaları, ödeme oranları |
| Göreli (grup içi) | yok | grup içi yüzdelik ve sapma (tek model için önemli) |
| Etkileşim | oran, delta (02.2) | koşullu değişkenler, segment × değişken |

Notlar:

- Bölüm 6 ve 7'deki değişkenlerin çoğu işlem düzeyinde (satır başına bir
  işlem) veri gerektirir. Platform bugün müşteri düzeyinde hazır bir
  tabloyla çalışıyor. Hazır tabloda pencere kolonları varsa (TXN_..._L30D
  gibi) oran, delta, büyüme ve eğim değişkenleri onlardan üretilebilir;
  yoksa önce kaynak tablolardan toplama gerekir.
- Hedef kodlamaları (bölüm 4) kat dışı hesaplama ve train'den öğrenme
  kuralıyla birlikte eklenmeli; aksi hâlde validasyon sonuçları gerçekte
  olduğundan iyi görünür.
