# -*- coding: utf-8 -*-
"""fe_agent/geleneksel.py - 02.2 Geleneksel (kural tabanli) degisken uretimi.

BIRIM: karar kolon ailesi basina verilir. Aile = ayni olcunun farkli
pencereleri (TXN_OUT_AMT_L3D, _L7D, _L30D ...: addaki pencere parcasi
disinda ayni). Aile disindaki her kolon tek basina bir birimdir. Anlamli
kolon ciftleri (gelen / giden, tutar / adet, alt kirilim / toplam) ve satir
duzeyi (satirdaki eksik sayisi) ayri birimlerdir.

KATALOG: her donusum icin kod, ad, grup, uretilen kolonun eki ve sozluk
aciklamasi. Bir donusumun birim icin MUMKUN olup olmadigini kod belirler
(tip, negatif deger, pencere sayisi, hedef turu ...); dil modeli yalniz
mumkun olanlardan secer, sohbet de yalniz mumkun olanlari ekleyebilir.

SIZINTI: ogrenilen her sey (winsor sinirlari, siralama izgarasi, ortalama
ve standart sapma, dilim sinirlari, Yeo-Johnson parametresi, frekans,
WoE ve hedef ortalamasi) yalniz TRAIN (MS) satirlarindan ogrenilir; WoE ve
hedef ortalamasi train satirlarinda kat disi (5 kat) hesaplanir.
"""

import math
import re
import threading
import time

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# KATALOG
# ---------------------------------------------------------------------------
# grup: "tekli" (sayisal kolon basina), "aile" (pencere ailesi), "cift"
# (iki kolon), "kategorik" (metin kolon basina), "satir" (butun satir).
KATALOG = [
    # Tekli sayisal (mevcut: log, rank, winsor)
    ("log", "Log (log1p)", "tekli", "Sağa çarpık ve negatif olmayan değerleri sıkıştırır."),
    ("islog", "İşaretli log", "tekli", "Negatif değer de olan kolonda işaret korunarak log alınır."),
    ("karekok", "Karekök", "tekli", "Logdan yumuşak çarpıklık düzeltmesi; sıfırı korur."),
    ("kare", "Kare terimi", "tekli", "Değerin karesi; eğilim U şeklindeyse doğrusal modelde eğriliği yakalar."),
    ("yeo", "Yeo-Johnson", "tekli", "Dağılımı normale yaklaştırır; parametre eğitim satırlarından."),
    ("winsor", "Uç kırpma (%1, %99)", "tekli", "Uçlar eğitim satırlarının %1 ve %99'luk değerlerine çekilir."),
    ("rank", "Sıra (yüzdelik)", "tekli", "Değerin eğitim dağılımındaki yüzdeliği (0 ile 1 arası)."),
    ("zskor", "Z-skor", "tekli", "(değer eksi ortalama) bölü standart sapma; eğitim satırlarından."),
    ("robust", "Robust ölçek", "tekli", "(değer eksi medyan) bölü çeyrekler arası açıklık; eğitim satırlarından."),
    ("isaret", "İşaret (eksi 1, 0, 1)", "tekli", "Değerin negatif, sıfır ya da pozitif olması."),
    ("sifir", "Sıfır bayrağı", "tekli", "Değer sıfırsa 1, değilse 0 (hiç işlem yok ile az işlem ayrımı)."),
    ("esik", "Eşik bayrağı", "tekli", "Değer verilen eşiğin üstündeyse (ya da altındaysa) 1."),
    ("dilim", "Eşit frekans dilimi", "tekli", "Eğitim satırlarının 10'luk dilimlerine göre dilim numarası."),
    ("kova", "İş kuralı kovaları", "tekli",
     "Değerler verilen sınırlarla kovalara bölünür (gecikme 0, 1 ile 29, 30 ile 59 gibi)."),
    ("segment", "Segment içi yüzdelik ve sapma", "tekli",
     "Değerin kendi segmenti içindeki yüzdeliği ve z-skoru; segment kolonu seçilir."),
    ("grup_oran", "Segment medyanına oran", "tekli",
     "Değerin kendi segmentinin medyanına oranı; segment kolonu seçilir."),
    # Pencere ailesi (mevcut: oran, fark)
    ("oran", "Oran (sıradaki pencere çifti)", "aile",
     "Kısa pencere bölü sıradaki uzun pencere (3/7, 7/14); eski adıyla ratio."),
    ("fark", "Fark (sıradaki pencere çifti)", "aile",
     "Kısa pencere eksi sıradaki uzun pencere (3 eksi 7); eski adıyla delta."),
    ("norm", "Normalize oran", "aile",
     "Pencerelerin günlük ortalamalarının oranı; pencere uzunluğu farkını giderir."),
    ("buyume", "Büyüme oranı", "aile",
     "Kısa pencerenin, uzun pencerenin geri kalanındaki aynı uzunluktaki döneme göre büyümesi."),
    ("egim", "Eğim", "aile", "Günlük ortalamanın pencere uzunluğuna göre eğimi (en az 3 pencere)."),
    ("dk", "Değişkenlik katsayısı", "aile",
     "Pencerelerin günlük ortalamalarının std / ortalaması (en az 3 pencere)."),
    ("ardisik", "Art arda artış sayısı", "aile",
     "Pencereler arasındaki dönemlerde günlük ortalamanın eskiden yeniye kaç kez arttığı."),
    ("oran_tum", "Oran (bütün pencere çiftleri)", "aile",
     "Her kısa pencere bölü her uzun pencere (yalnız sıradaki değil: 3/30, 7/90 gibi)."),
    ("fark_tum", "Fark (bütün pencere çiftleri)", "aile",
     "Her kısa pencere eksi her uzun pencere (yalnız sıradaki değil)."),
    ("donem", "Dönem parçaları", "aile",
     "Pencerelerin arasında kalan her dönemin kendi değeri (7 günlük eksi 3 günlük: 4. ile 7. gün)."),
    ("donem_pay", "Dönem payları", "aile",
     "Her dönemin en uzun pencere toplamındaki payı."),
    ("donem_oran", "Dönem oranları", "aile",
     "Sıradaki iki dönemin günlük ortalamalarının oranı (yeni dönem bölü bir önceki dönem)."),
    ("en_yogun", "En yoğun dönemin payı", "aile",
     "Pencereler arasındaki dönemlerden en yoğun olanın en uzun pencere toplamındaki payı."),
    # Kolon ciftleri
    ("net", "Net (fark)", "cift", "İki kolonun farkı (gelen eksi giden gibi)."),
    ("cift_oran", "Oran", "cift", "İki kolonun oranı (gelen / giden gibi)."),
    ("ort", "Ortalama tutar (tutar / adet)", "cift", "Tutarın adede bölümü."),
    ("pay", "Pay (alt kırılım / toplam)", "cift", "Alt kırılımın toplam içindeki payı."),
    ("carpim", "Çarpım", "cift", "İki kolonun çarpımı; iki etkinin birlikte görülmesi."),
    ("kesisim", "Kategori kesişimi", "cift",
     "İki kategorik kolonun birleşimi; hedef iki sınıflıysa WoE'si, değilse frekansı."),
    ("yogunlasma", "Yoğunlaşma (HHI ve en büyük pay)", "cift",
     "Bir toplamın alt kırılımları arasında payların karelerinin toplamı ve en büyük pay."),
    # Kategorik
    ("frekans", "Frekans kodlama", "kategorik", "Kategorinin eğitim satırlarındaki payı."),
    ("onehot", "One-hot", "kategorik", "Az değerli kolonda her değer için 1/0 kolonu."),
    ("woe", "WoE", "kategorik",
     "Kategorinin olay olmayan / olay payı logaritması; eğitimde kat dışı (5 kat)."),
    ("hedef_ort", "Hedef ortalaması", "kategorik",
     "Kategorinin yumuşatılmış hedef oranı; eğitimde kat dışı (5 kat)."),
    # Satir
    ("eksik_sayi", "Satırdaki eksik sayısı ve oranı", "satir",
     "Satırda boş olan kolon sayısı ve oranı (eksik bilgi profili)."),
]
KATALOG_HARITA = {k: {"kod": k, "ad": a, "grup": g, "aciklama": c} for k, a, g, c in KATALOG}

# Kartin "Dönüşümler ne yapar?" tablosu: ne yapar, örnek, ne zaman işe yarar.
ACIKLAMA_UZUN = {
    "log": ("log(1 + değer). Büyük değerleri sıkıştırır, küçük değerleri ayırır.",
            "İşlem tutarı 10, 100, 10.000 iken log1p 2,4, 4,6, 9,2 olur.",
            "Doğrusal modelde sağa çarpık tutar ve adetlerde."),
    "islog": ("işaret · log(1 + |değer|). Log gibi, ama negatif değerde işaret korunur.",
              "Net akış −5.000 iken −8,5; +5.000 iken +8,5.", "Negatif değeri olan çarpık kolonda."),
    "karekok": ("Değerin karekökü. Logdan daha hafif sıkıştırır.", "100 iken 10, 10.000 iken 100.",
                "Hafif çarpık ve negatif olmayan kolonda."),
    "kare": ("Değerin karesi (polinom terimi); ham değerle birlikte kullanılır.",
             "Yaş 20 iken 400, 60 iken 3.600: risk hem gençte hem yaşlıda yüksekse.",
             "Doğrusal modelde U şekilli ilişki (ağaç kendisi bulur)."),
    "yeo": ("Dağılımı normale yaklaştıran parametreli dönüşüm; parametre eğitim satırlarından.",
            "Çok çarpık bakiye dağılımı simetriğe yakın hâle gelir.", "Doğrusal modelde, log yetmediğinde."),
    "winsor": ("Eğitim satırlarının %1'lik değerinin altı ve %99'luk değerinin üstü bu sınırlara çekilir.",
               "%99'luk değer 50.000 iken 5.000.000 olan değer 50.000 olur.",
               "Doğrusal modelde tek uç değerin katsayıyı bozmasını önler."),
    "rank": ("Değerin eğitim dağılımındaki yüzdeliği (0 ile 1 arası).",
             "Medyandaki müşteri 0,5, en üst %1'deki 0,99 alır.", "Ölçek farkını ve uç değerleri ortadan kaldırır."),
    "zskor": ("(değer eksi ortalama) bölü standart sapma; eğitim satırlarından.",
              "Ortalama 1.000, std 200 iken 1.400, 2 olur.", "Doğrusal modelde ölçekleri eşitler."),
    "robust": ("(değer eksi medyan) bölü çeyrekler arası açıklık; uç değerden etkilenmez.",
               "Medyan 1.000, açıklık 400 iken 1.800, 2 olur.", "Uç değeri çok olan kolonda ölçekleme."),
    "isaret": ("Değer negatifse eksi 1, sıfırsa 0, pozitifse 1.", "Net akış eksiyse eksi 1.",
               "Yönün kendisi bilgi taşıyorsa."),
    "sifir": ("Değer sıfırsa 1, değilse 0.", "Hiç işlem yoksa 1.",
              "Sıfır çok sık ise hiç işlem yok ile az işlem ayrımı için."),
    "esik": ("Değer verilen eşiğin üstündeyse (ya da altındaysa) 1, değilse 0.",
             "Gecikme günü 30 ve üstüyse 1.", "İş kuralı eşiği olan kolonda (skorkart)."),
    "dilim": ("Eğitim satırlarına göre 10 eşit kalabalıklı dilimin numarası.",
              "En düşük %10 dilim 1, en yüksek %10 dilim 10.", "Doğrusal olmayan ilişkiyi kaba gruplarla yakalar."),
    "segment": ("Değerin kendi segmenti (ör. müşteri tipi) içindeki yüzdeliği ve z-skoru.",
                "KOBİ içinde yüksek ama bireyselde sıradan bakiye.", "Segmentler arası ölçek farkı varsa."),
    "oran": ("Kısa pencere bölü gün sırasında bir sonraki uzun pencere (eski 02.2'deki ratio). Yalnız "
             "sıradaki çiftler; bütün çiftler için Oran (bütün pencere çiftleri).",
             "Son 7 gün 300, son 30 gün 600 iken 0,5: harcamanın yarısı son haftada.",
             "Son dönemdeki hızlanma ya da yavaşlama."),
    "fark": ("Kısa pencere eksi gün sırasında bir sonraki uzun pencere (eski 02.2'deki delta). Birikimli "
             "pencerede değer sıfır ya da eksidir: aradaki dönemin eksi işaretlisi.", "Son 30 gün eksi son 90 gün.",
             "Mutlak değişim."),
    "norm": ("Pencerelerin günlük ortalamalarının oranı: (kısa / gün) bölü (uzun / gün).",
             "Son 7 gün günde 50, son 30 gün günde 20 iken 2,5: son hafta normalin 2,5 katı.",
             "Pencere uzunluğu farkı giderilmiş hızlanma; oran'dan daha yorumlanabilir."),
    "buyume": ("Kısa pencere, uzun pencerenin geri kalanında aynı uzunluğa düşen değere göre ne kadar büyüdü.",
               "Son 30 gün 900, önceki 60 gün 1.200 (30 güne 600) iken büyüme 0,5 (%50).",
               "Toplanabilir ölçüde dönemden döneme artış."),
    "egim": ("Günlük ortalamanın pencere uzunluğuna göre eğimi (en az 3 pencere).",
             "Eğim negatifse son dönem daha yoğun, pozitifse azalıyor.", "Eğilimin yönü ve gücü."),
    "dk": ("Pencerelerin günlük ortalamalarının standart sapması bölü ortalaması.",
           "Düzenli harcayan müşteride küçük, ani sıçramada büyük.", "Davranışın düzensizliği."),
    "net": ("İki kolonun farkı.", "Gelen 5.000, giden 7.000 iken net akış eksi 2.000.",
            "Gelen ve giden gibi yön çiftinde."),
    "cift_oran": ("İki kolonun oranı.", "Gelen / giden 0,7.", "Gelen ve giden gibi yön çiftinde."),
    "ort": ("Tutarın adede bölümü.", "30 günde 10 işlem, 3.000 TL iken işlem başına 300.",
            "Tutar ve adet çiftinde."),
    "pay": ("Alt kırılımın toplam içindeki payı.", "Gece işlem adedi / toplam işlem adedi.",
            "Alt kırılım ve toplam çiftinde."),
    "frekans": ("Kategorinin eğitim satırlarındaki payı.", "İstanbul %18 ise 0,18.",
                "Kategorik kolonu sayıya çevirir; nadir ve yaygın kategori ayrımı."),
    "onehot": ("Her değer için ayrı 1/0 kolonu.", "SEGMENT BIREYSEL, KOBI için iki kolon.",
               "Az değerli kategorik kolonda."),
    "woe": ("ln(olay olmayan payı / olay payı); eğitimde kat dışı.", "Riskli ilde eksi, güvenli ilde artı.",
            "Hedef iki sınıflıysa kategorik kolonun risk bilgisini tek sayıya taşır."),
    "hedef_ort": ("Kategorinin yumuşatılmış hedef oranı; eğitimde kat dışı.", "İldeki temerrüt oranı %4.",
                  "Çok değerli kategorik kolonda."),
    "eksik_sayi": ("Satırda boş olan kolon sayısı ve oranı.", "60 kolondan 12'si boşsa 12 ve 0,2.",
                   "Eksik bilgi profili (yeni müşteri, ürünü olmayan)."),
    "kova": ("Değerler iş kuralı sınırlarıyla kovalara bölünür; kova numarası.",
             "Gecikme günü sınırları 1, 30, 60, 90: 0 gün kova 1, 45 gün kova 3.",
             "Skorkartta iş kuralından gelen aralıklar."),
    "grup_oran": ("Değer bölü kendi segmentinin medyanı (eğitim satırlarından).",
                  "KOBİ medyan bakiyesi 50.000 iken 100.000 bakiye 2 olur.",
                  "Segmentler arası ölçek farkı varsa (tek model)."),
    "ardisik": ("Pencerelerin arasında kalan dönemlerde günlük ortalama, en eski dönemden en yeniye "
                "kaç kez arttı.", "90 ile 30, 30 ile 7, 7 ile 3 gün arasında hep artış: 2.",
                "Süreklilik gösteren artış ya da azalış."),
    "oran_tum": ("Ailenin bütün pencere çiftlerinde kısa pencere bölü uzun pencere. Sıradaki çiftler "
                 "Oran ile aynıdır; burada atlanan çiftler de üretilir.",
                 "3, 7, 30, 90 günlük ailede 6 kolon: 3/7, 3/30, 3/90, 7/30, 7/90, 30/90.",
                 "Hızlanmanın hangi ufukta (son günler ya da son aylar) görüldüğü önemliyse."),
    "fark_tum": ("Ailenin bütün pencere çiftlerinde kısa pencere eksi uzun pencere.",
                 "3, 7, 30, 90 günlük ailede 6 kolon.",
                 "Mutlak değişimin hangi ufukta olduğu önemliyse."),
    "donem": ("Birikimli pencerelerin arasında kalan her dönemin kendi değeri: uzun pencere eksi bir önceki "
              "kısa pencere.", "3 ve 7 günlük adet 5 ve 9 ise 4. ile 7. gün arası 4.",
              "Pencereler birbirini içerdiğinde (7 gün 3 günü kapsar) dönemleri ayırmak için."),
    "donem_pay": ("Her dönemin (ilk pencere dahil) en uzun pencere toplamındaki payı.",
                  "90 günlük 100 işlemin 30'u 31. ile 90. gün arasındaysa o dönemin payı 0,3.",
                  "İşlemin hangi döneme yığıldığı."),
    "donem_oran": ("Sıradaki iki dönemin günlük ortalamalarının oranı: yeni dönem bölü bir önceki dönem. "
                   "(3 gün eksi 7 gün) bölü (3 gün eksi 14 gün) gibi farkların oranıyla aynı sırayı verir.",
                   "1. ile 3. gün günde 2, 4. ile 7. gün günde 1 ise oran 2.",
                   "Son dönemin hemen önceki döneme göre hızlanması."),
    "en_yogun": ("Pencerelerin arasında kalan dönemlerden en yoğun olanın en uzun pencere toplamındaki payı.",
                 "90 günlük harcamanın %70'i son 7 günde ise 0,7.", "Tek seferlik sıçrama."),
    "carpim": ("İki kolonun çarpımı.", "Yeni müşteri bayrağı × limit kullanımı.",
               "Doğrusal modelde etkileşim (ağaç kendisi bulur)."),
    "kesisim": ("İki kategorik kolonun birleşik değeri; WoE ya da frekansla sayıya çevrilir.",
                "Ürün × kanal: KART_MOBIL, KART_SUBE.", "İki kategorinin birlikte risk taşıması."),
    "yogunlasma": ("Alt kırılımların paylarının karelerinin toplamı (HHI) ve en büyük pay.",
                   "Harcamanın %90'ı tek kanaldaysa HHI 0,82, en büyük pay 0,9.",
                   "Kanal, ürün, karşı taraf yoğunlaşması."),
}

# KARAR ASAMALARI: once kolonun kendi donusumu, sonra aile ici (pencere ve
# icerik), en son aileler arasi.
ASAMA = {}
for _k in ("log", "islog", "karekok", "kare", "yeo", "winsor", "rank", "zskor", "robust", "isaret",
           "sifir", "esik", "dilim", "kova", "frekans", "onehot", "woe", "hedef_ort"):
    ASAMA[_k] = 1
for _k in ("oran", "fark", "norm", "buyume", "egim", "dk", "ardisik", "en_yogun", "oran_tum", "fark_tum",
           "donem", "donem_pay", "donem_oran"):
    ASAMA[_k] = 2
for _k in ("net", "cift_oran", "ort", "pay", "carpim", "kesisim", "yogunlasma", "segment",
           "grup_oran", "eksik_sayi"):
    ASAMA[_k] = 3
ASAMA_ADI = {1: "1. Kolonun kendi dönüşümü", 2: "2. Aile içi (pencere ve içerik)",
             3: "3. Aileler arası"}

# AGAC MODELI: platformun modeli HistGradientBoosting (bkz. model.py). Ağaç
# modeller tek kolonun monoton dönüşümünden etkilenmez (aynı bölünmeyi ham
# kolonla bulur); eşik ve işaret bayraklarını da kendisi bulur. Bu
# dönüşümler ağaç modelinde gereksizdir; doğrusal modelde işe yarar.
AGAC_GEREKSIZ = ("log", "islog", "karekok", "kare", "yeo", "winsor", "rank", "zskor", "robust",
                 "dilim", "isaret", "sifir", "esik", "kova", "carpim")
AGAC_NEDENI = ("Ağaç modeli (platformda HistGradientBoosting) tek kolonun sıralamayı koruyan "
               "dönüşümünden etkilenmez; aynı bölünmeyi ham kolonla bulur.")
MODEL_TURLERI = {"agac": "Ağaç (HistGradientBoosting)", "dogrusal": "Doğrusal (lojistik, skorkart)"}


def model_mumkun(b, model_turu):
    """Birimde model turune gore secilebilen kodlar."""
    m = list(b.get("mumkun") or [])
    return [c for c in m if not (model_turu == "agac" and c in AGAC_GEREKSIZ)]
GRUP_ADI = {"tekli": "Tek değişkenli", "aile": "Pencere ailesi", "cift": "Kolon çifti",
            "kategorik": "Kategorik", "satir": "Satır düzeyi"}

WINSOR_ALT, WINSOR_UST = 0.01, 0.99
RANK_IZGARA = 100
DILIM_SAYI = 10
ONEHOT_EN_COK = 10           # one-hot en cok bu kadar degerli kolonda
KATEGORIK_EN_COK = 200       # daha cok degerli metin kolon uretime girmez
TEKIL_EN_AZ = 10             # dagilim donusumleri icin en az farkli deger
KAT_SAYISI = 5               # kat disi hedef kodlamalari
HEDEF_YUMUSAK = 20.0         # hedef ortalamasinda yumusatma agirligi
SEGMENT_EN_COK = 20          # segment kolonu en cok bu kadar degerli
CIFT_EN_COK = 400            # kod en cok bu kadar aday cift cikarir

_PENCERE = re.compile(r"^(?:L|N|P|LST|LAST|SON)?(\d+)(D|G|W|M|A|Q|Y)$")
_GUN = {"D": 1, "G": 1, "W": 7, "M": 30, "A": 30, "Q": 91, "Y": 365}
_YON_CIFT = [({"IN", "INC", "INCOMING", "GELEN", "CR", "ALACAK"},
              {"OUT", "OUTGOING", "GIDEN", "DR", "BORC"})]
_ADET = {"CNT", "COUNT", "ADET", "NUM", "SAY", "SAYI", "NB"}
_TUTAR = {"AMT", "AMOUNT", "TUTAR", "SUM", "VOL", "HACIM"}
_TOPLAM = {"TOT", "TOTAL", "TOPLAM", "ALL", "TUM"}
_ORT = {"AVG", "ORT", "MEAN", "ORTALAMA", "MED", "MEDIAN"}
_MAKS = {"MAX", "MAKS"}
_MIN = {"MIN"}


def _toklar(ad):
    try:
        from fe_agent import parca as parca_mod
        return [str(x).upper() for x in parca_mod.toklar(ad)]
    except Exception:
        return [t for t in re.split(r"[^A-Za-z0-9]+", str(ad).upper()) if t]


def guvenli_ad(metin):
    t = re.sub(r"[^A-Za-z0-9]+", "_", str(metin)).strip("_").upper()
    return t or "BOS"


# ---------------------------------------------------------------------------
# KOLON BILGISI VE BIRIMLER
# ---------------------------------------------------------------------------
def _sayisal_mi(s):
    return pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s)


def kolon_ozeti(s):
    """Tek kolonun karar icin sayilari (butun satirlar)."""
    if _sayisal_mi(s):
        x = pd.to_numeric(s, errors="coerce")
        d = x.dropna()
        n = int(len(d))
        oz = {"tip": "sayisal", "dolu": n, "bos_pay": float(x.isna().mean()) if len(x) else 0.0}
        if n:
            oz.update({"min": float(d.min()), "max": float(d.max()),
                       "tekil": int(d.nunique()), "sifir_pay": float((d == 0).mean()),
                       "negatif": bool((d < 0).any())})
            try:
                oz["carpiklik"] = float(d.skew()) if n > 2 else 0.0
            except Exception:
                oz["carpiklik"] = 0.0
            p99 = float(d.quantile(0.99))
            oz["uc_kat"] = (oz["max"] / p99) if p99 > 0 else None
            if not np.isfinite(oz["carpiklik"]):
                oz["carpiklik"] = 0.0
        else:
            oz.update({"tekil": 0, "sifir_pay": 0.0, "negatif": False, "carpiklik": 0.0})
        return oz
    v = s.astype(object).where(s.notna(), None)
    return {"tip": "kategorik", "tekil": int(s.nunique(dropna=True)),
            "bos_pay": float(s.isna().mean()) if len(s) else 0.0,
            "dolu": int(s.notna().sum()), "ornek": [str(x) for x in v.dropna().unique()[:5]]}


def _pencere(kolon, turler=None):
    """(aile anahtari, gun, parca indeksi) ya da None. turler verilmisse
    (01.2.4 donem anlam turleri) yalniz gecmise bakan pencere parcasi."""
    t = _toklar(kolon)
    for i, p in enumerate(t):
        m = _PENCERE.match(p)
        if not m:
            continue
        if turler is not None:
            x = turler.get(p) or turler.get(p.lower())
            if x and (x[1] != "gecmis" or x[2] != "pencere"):
                continue
        gun = int(m.group(1)) * _GUN[m.group(2)]
        if gun <= 0:
            continue
        anahtar = tuple(t[:i]) + ("*" + re.sub(r"\d+", "#", p),) + tuple(t[i + 1:])
        return anahtar, gun, i
    return None


def _istat(kolon, kart_istat=None):
    s_ = (kart_istat or {}).get(kolon) or ""
    if s_:
        return s_
    tok = set(_toklar(kolon))
    if tok & _ORT:
        return "ort"
    if tok & _MAKS:
        return "maks"
    if tok & _MIN:
        return "min"
    if tok & _ADET:
        return "adet"
    if tok & _TUTAR or tok & _TOPLAM:
        return "toplam"
    return ""


def _kod_bilgisi(durum):
    """(donem turleri {kolon: {parca: (tur, yon, bicim)}}, istatistik
    sinifi {kolon: sinif}, olcu {kolon: metin}, aciklama {kolon: metin})."""
    turler, istat, olcu, aciklama = {}, {}, {}, {}
    try:
        from fe_agent import akis_faz01, akis_faz02, donem_tur
        eski = {str(y): str(e) for e, y in (durum.get("_amp_yeniden_ad") or {}).items()}
        try:
            kt = akis_faz01._kolon_donem_turleri(durum) or {}
        except Exception:
            kt = {}
        ozel = {}
        for _k, tt in (durum.get("donem_anlam_turleri") or {}).items():
            if isinstance(tt, dict):
                ozel.update({t: x for t, x in tt.items()
                             if t not in donem_tur.SABIT_KODLAR and isinstance(x, dict)})
        for e, tt in kt.items():
            d = {}
            for parca, tur in (tt or {}).items():
                if tur:
                    yon, bicim = donem_tur.tur_bilgisi(tur, ozel)
                    d[str(parca).upper()] = (tur, yon, bicim)
            turler[str(e)] = d
        for y, e in eski.items():
            if e in turler:
                turler[y] = turler[e]
        istat = {k: akis_faz02._istat_sinifi(v)
                 for k, v in akis_faz02._kart_alani(durum, "ISTATISTIK").items()}
        olcu = akis_faz02._kart_olculeri(durum)
        aciklama = akis_faz02._aciklamalar(durum)
        for y, e in eski.items():
            for d in (istat, olcu, aciklama):
                if e in d and y not in d:
                    d[y] = d[e]
    except Exception:
        pass
    return turler, istat, olcu, aciklama


def _aile_adi(kolonlar, i):
    """Aile icin uretilen kolonlarin koku: pencere parcasi yerine PNC."""
    t = _toklar(kolonlar[0])
    if 0 <= i < len(t):
        t = t[:i] + ["PNC"] + t[i + 1:]
    return guvenli_ad("_".join(t))


def birimleri_kur(durum, df, haric=(), arasi=()):
    """Doner: (birimler, girmeyenler). birim: {"id", "tur", "ad", "kolonlar",
    "gunler", "tip", "aciklama", "olcu", "istat", "ozet", "mumkun",
    "imkansiz"}. girmeyen: {"kolonlar", "neden"} (neden basina gruplu)."""
    m = durum.get("meta") or {}
    meta = {x for x in (m.get("target"), m.get("id"), m.get("donem")) if x} | {"_SPLIT"}
    turler, istat, olcu, aciklama = _kod_bilgisi(durum)
    haric = set(haric)
    hedef = m.get("target")
    hedef_ikili = False
    if hedef and hedef in df.columns:
        yv = set(pd.to_numeric(df[hedef], errors="coerce").dropna().unique().tolist())
        hedef_ikili = bool(yv) and yv <= {0, 1}
    girmeyen = {}

    def dis(k, neden):
        girmeyen.setdefault(neden, []).append(k)

    ozet, sayisal, kategorik = {}, [], []
    for k in df.columns:
        k = str(k)
        if k in meta:
            dis(k, "Hedef, kimlik, dönem ya da bölme kolonu; değişken üretiminde kullanılmaz.")
            continue
        if k in haric:
            dis(k, "Süreç dışı bırakıldı ya da 02.1'de üretime girmez denildi.")
            continue
        s = df[k]
        if pd.api.types.is_datetime64_any_dtype(s):
            dis(k, "Tarih tipinde; tarih kolonundan gün farkı 02.1'de üretilir.")
            continue
        oz = kolon_ozeti(s)
        ozet[k] = oz
        if oz["dolu"] == 0 or oz["tekil"] <= 1:
            dis(k, "Boş ya da tek değerli; dönüşüm bilgi üretmez.")
            continue
        if oz["tip"] == "sayisal":
            if oz["tekil"] == 2 and set(pd.to_numeric(s, errors="coerce").dropna().unique().tolist()) <= {0, 1}:
                dis(k, "İki değerli (0/1 bayrak) kolon; sayısal dönüşüm anlam taşımaz.")
                continue
            sayisal.append(k)
        else:
            if oz["tekil"] > KATEGORIK_EN_COK:
                dis(k, "Çok değerli metin kolon (%s değerden fazla); 02.1 çözümleri kapsar."
                    % KATEGORIK_EN_COK)
                continue
            kategorik.append(k)
    segmentler = [k for k in kategorik if 2 <= ozet[k]["tekil"] <= SEGMENT_EN_COK]

    # Pencere aileleri
    kova = {}
    for k in sayisal:
        p = _pencere(k, turler.get(k) if turler.get(k) else None)
        if p:
            kova.setdefault(p[0], []).append((p[1], k, p[2]))
    aileli = set()
    birimler = []
    for anahtar, uyeler in kova.items():
        uyeler = sorted(set(uyeler))
        gunler = [g for g, _k, _i in uyeler]
        if len(uyeler) < 2 or len(set(gunler)) < len(gunler):
            continue
        kol = [k for _g, k, _i in uyeler]
        aileli.update(kol)
        birimler.append({"id": "aile:" + kol[0], "tur": "aile", "kolonlar": kol, "gunler": gunler,
                         "ad": _aile_adi(kol, uyeler[0][2]), "tip": "sayisal"})
    for k in sayisal:
        if k not in aileli:
            birimler.append({"id": "kolon:" + k, "tur": "kolon", "kolonlar": [k], "ad": k,
                             "tip": "sayisal"})
    for k in kategorik:
        birimler.append({"id": "kolon:" + k, "tur": "kolon", "kolonlar": [k], "ad": k,
                         "tip": "kategorik"})
    # Kolon ciftleri: ayni iki aileden (ya da ayni iki kolondan) gelen
    # ciftler TEK birimde toplanir (gelen ve giden tutarin 8 penceresi gibi).
    aile_kok = {}
    for bb in birimler:
        if bb["tur"] == "aile":
            for k in bb["kolonlar"]:
                aile_kok[k] = bb["ad"]
    cift_kova = {}
    for a, b, tur in aday_ciftler(sayisal, istat, olcu)[:CIFT_EN_COK]:
        anahtar = (tur, aile_kok.get(a, a), aile_kok.get(b, b))
        cift_kova.setdefault(anahtar, []).append((a, b))
    for (tur, ka, kb), ciftler in cift_kova.items():
        kol = list(dict.fromkeys([x for c in ciftler for x in c]))
        birimler.append({"id": "cift:%s|%s|%s" % (tur, ka, kb), "tur": "cift", "kolonlar": kol,
                         "ciftler": [list(c) for c in ciftler],
                         "ad": "%s ile %s" % (ka, kb), "tip": "sayisal", "cift": tur})
    # Yogunlasma: ayni toplamin en az iki alt kirilimi (kanal, urun gibi).
    # Toplamin ailesine gore tek birimde toplanir.
    alt = {}
    for a, b, tur in aday_ciftler(sayisal, istat, olcu):
        if tur == "pay":
            alt.setdefault(b, []).append(a)
    grup_kova = {}
    for top, altlar in alt.items():
        if len(set(altlar)) >= 2:
            grup_kova.setdefault(aile_kok.get(top, top), []).append((top, sorted(set(altlar))))
    for kok, liste in grup_kova.items():
        birimler.append({"id": "grup:" + kok, "tur": "grup", "ad": "%s alt kırılımları" % kok,
                         "kolonlar": list(dict.fromkeys([x for t, al in liste for x in [t] + al])),
                         "gruplar": [al for _t, al in liste],
                         "kok_adlar": {al[0]: t for t, al in liste}, "tip": "sayisal"})
    # Satir duzeyi
    bosu_olan = [k for k in sayisal + kategorik if ozet[k]["bos_pay"] > 0]
    if bosu_olan:
        birimler.append({"id": "satir", "tur": "satir", "kolonlar": sayisal + kategorik,
                         "ad": "Satır düzeyi", "tip": "satir", "bosu_olan": len(bosu_olan)})
    birimler += arasi_birimleri(birimler, arasi, ozet)
    for b in birimler:
        k0 = b["kolonlar"][0]
        b["asama"] = birim_asamasi(b)
        b["aciklama"] = str(b.get("aciklama") or aciklama.get(k0) or "")
        b["olcu"] = str(olcu.get(k0) or "")
        b["istat"] = _istat(k0, istat)
        b["ozet"] = _birim_ozeti(b, ozet)
        b["mumkun"], b["imkansiz"] = uygunluk(b, hedef_ikili, segmentler)
    return birimler, [{"neden": n, "kolonlar": k} for n, k in girmeyen.items()], segmentler


def birim_asamasi(b):
    """1: tek kolon (kendi donusumu), 2: pencere ailesi (once kendi
    donusumu, sonra aile ici), 3: aileler arasi (cift, grup, satir)."""
    return {"kolon": 1, "aile": 2}.get(b["tur"], 3)


ARASI_ISLEM = {"oran": "cift_oran", "fark": "net", "carpim": "carpim", "kesisim": "kesisim"}
ARASI_EN_COK = 60


def arasi_birimleri(birimler, oneriler, ozet=None):
    """Dil modelinin onerdigi aileler arasi birimleri kod dogrular ve
    kurar. oneri: {"islem": oran|fark|carpim|kesisim, "a": birim id,
    "b": birim id, "gerekce"}. Aile ile aile: ayni gunlu pencereler
    eslesir (ortak pencere yoksa olmaz); aile ile tek kolon: her pencere o
    kolonla; tek kolon ile tek kolon: bir cift. Kesisim yalniz iki az
    degerli kategorik kolonda. Kodun zaten buldugu cift tekrar kurulmaz."""
    harita = {b["id"]: b for b in birimler}
    var = {tuple(c) for b in birimler if b["tur"] == "cift" for c in (b.get("ciftler") or [])}
    cikti, sira = {}, []
    for o in oneriler or []:
        if not isinstance(o, dict):
            continue
        islem = ARASI_ISLEM.get(str(o.get("islem") or ""), str(o.get("islem") or ""))
        a, c = harita.get(str(o.get("a") or "")), harita.get(str(o.get("b") or ""))
        if islem not in ARASI_ISLEM.values() or not a or not c or a is c:
            continue
        if a["tur"] not in ("aile", "kolon") or c["tur"] not in ("aile", "kolon"):
            continue
        if islem == "kesisim":
            if not (a.get("tip") == c.get("tip") == "kategorik"):
                continue
            tk = lambda u: ((ozet or {}).get(u["kolonlar"][0]) or u.get("ozet") or {}).get("tekil", 99)
            if tk(a) > SEGMENT_EN_COK or tk(c) > SEGMENT_EN_COK:
                continue
            ciftler = [(a["kolonlar"][0], c["kolonlar"][0])]
            tip = "kategorik"
        else:
            if a.get("tip") != "sayisal" or c.get("tip") != "sayisal":
                continue
            if a["tur"] == "aile" and c["tur"] == "aile":
                gc = dict(zip(c["gunler"], c["kolonlar"]))
                ciftler = [(k, gc[g]) for g, k in zip(a["gunler"], a["kolonlar"]) if g in gc]
            elif a["tur"] == "aile":
                ciftler = [(k, c["kolonlar"][0]) for k in a["kolonlar"]]
            elif c["tur"] == "aile":
                ciftler = [(a["kolonlar"][0], k) for k in c["kolonlar"]]
            else:
                ciftler = [(a["kolonlar"][0], c["kolonlar"][0])]
            ciftler = [x for x in ciftler if x not in var and (x[1], x[0]) not in var]
            tip = "sayisal"
        if not ciftler:
            continue
        bid = "arasi:%s|%s" % (a["id"], c["id"])
        if bid in harita or "arasi:%s|%s" % (c["id"], a["id"]) in harita:
            continue                  # bu iliski zaten bir birim
        if bid not in cikti:
            if len(cikti) >= ARASI_EN_COK:
                continue
            cikti[bid] = {"id": bid, "tur": "cift", "cift": "arasi", "tip": tip,
                          "ad": "%s ile %s" % (a["ad"], c["ad"]),
                          "kolonlar": list(dict.fromkeys([x for p_ in ciftler for x in p_])),
                          "ciftler": [list(x) for x in ciftler], "oneri_islem": [],
                          "gerekce": "", "bulan": "dil modeli",
                          "kaynak_birimler": [a["id"], c["id"]]}
            sira.append(bid)
        u = cikti[bid]
        if islem not in u["oneri_islem"]:
            u["oneri_islem"].append(islem)
        g = str(o.get("gerekce") or "").strip()[:300]
        if g and g not in u["gerekce"]:
            u["gerekce"] = (u["gerekce"] + " " + g).strip()
    return [cikti[i] for i in sira]


def arasi_ekle(birimler, oneriler, segmentler=(), bulan="dil modeli"):
    """Kurulmus birimlere (veri okumadan) aileler arasi birimleri ekler:
    sayilar kaynak birimlerin ozetinden. Doner: yeni birimler."""
    tek = {}
    for b in birimler:
        if b["tur"] in ("kolon", "aile"):
            for k in b["kolonlar"]:
                tek[k] = b.get("ozet") or {}
    harita = {b["id"]: b for b in birimler}
    yeni = arasi_birimleri(birimler, oneriler)
    for b in yeni:
        kb = [harita[i] for i in b["kaynak_birimler"]]
        b["bulan"] = bulan
        b["asama"] = 3
        b["aciklama"] = b.get("gerekce") or ""
        b["olcu"] = " ile ".join(x.get("olcu") or "-" for x in kb)
        b["istat"] = ""
        b["ozet"] = _birim_ozeti(b, tek)
        b["mumkun"], b["imkansiz"] = uygunluk(b, False, segmentler)
    return yeni


def param_temizle(sec, param, segmentler):
    """Secilen kodlarin parametrelerini dogrular; parametresi gecersiz
    kod secimden cikar. Doner: (sec, param)."""
    sec = [c for c in dict.fromkeys(sec or []) if c in KATALOG_HARITA]
    param = param if isinstance(param, dict) else {}
    param = {c: v for c, v in param.items() if c in sec and isinstance(v, dict)}
    for c in ("segment", "grup_oran"):
        if c in sec and str((param.get(c) or {}).get("segment")) not in segmentler:
            sec.remove(c)
            param.pop(c, None)
    if "esik" in sec:
        try:
            v = float(str((param.get("esik") or {}).get("esik")).replace(",", "."))
            yon = (param.get("esik") or {}).get("yon")
            param["esik"] = {"esik": v, "yon": "<=" if yon == "<=" else ">="}
        except (TypeError, ValueError):
            sec.remove("esik")
            param.pop("esik", None)
    if "kova" in sec:
        try:
            sinir = sorted(set(float(str(x).replace(",", ".")) for x in
                               ((param.get("kova") or {}).get("sinirlar") or [])))
        except (TypeError, ValueError):
            sinir = []
        if sinir:
            param["kova"] = {"sinirlar": sinir[:20]}
        else:
            sec.remove("kova")
            param.pop("kova", None)
    return sec, param


def _birim_ozeti(b, ozet):
    oz = [ozet.get(k) or {} for k in b["kolonlar"] if b["tur"] != "satir"]
    if b["tur"] == "satir":
        return {"kolon": len(b["kolonlar"]), "bosu_olan": b.get("bosu_olan", 0)}
    if b["tip"] == "kategorik":
        o = dict(oz[0])
        if len(oz) > 1:
            o["tekil"] = int(np.prod([max(1, x.get("tekil") or 1) for x in oz]))
        return o
    o = {"min": min((x.get("min") for x in oz if x.get("min") is not None), default=None),
         "max": max((x.get("max") for x in oz if x.get("max") is not None), default=None),
         "tekil": min((x.get("tekil") or 0) for x in oz),
         "negatif": any(x.get("negatif") for x in oz),
         "sifir_pay": max((x.get("sifir_pay") or 0) for x in oz),
         "carpiklik": max((x.get("carpiklik") or 0) for x in oz),
         "bos_pay": max((x.get("bos_pay") or 0) for x in oz)}
    uk = [x.get("uc_kat") for x in oz if x.get("uc_kat")]
    o["uc_kat"] = max(uk) if uk else None
    return o


def aday_ciftler(sayisal, istat=None, olcu=None):
    """[(a, b, tur)]: adin tek parcasiyla ayrilan anlamli ciftler. tur:
    "yon" (gelen / giden), "ort" (tutar / adet), "pay" (alt kirilim /
    toplam: b'nin parcalari a'nin parcalarinin bir eksigi)."""
    tok = {k: _toklar(k) for k in sayisal}
    cikti, gor = [], set()
    kova = {}
    for k, t in tok.items():
        for i in range(len(t)):
            kova.setdefault(tuple(t[:i]) + ("*",) + tuple(t[i + 1:]), []).append((t[i], k))
    for uyeler in kova.values():
        if len(uyeler) < 2:
            continue
        for p1, k1 in uyeler:
            for p2, k2 in uyeler:
                if k1 >= k2 or (k1, k2) in gor:
                    continue
                for gelen, giden in _YON_CIFT:
                    if p1 in gelen and p2 in giden:
                        cikti.append((k1, k2, "yon")); gor.add((k1, k2))
                    elif p2 in gelen and p1 in giden:
                        cikti.append((k2, k1, "yon")); gor.add((k1, k2))
                if (p1 in _TUTAR and p2 in _ADET):
                    cikti.append((k1, k2, "ort")); gor.add((k1, k2))
                elif (p2 in _TUTAR and p1 in _ADET):
                    cikti.append((k2, k1, "ort")); gor.add((k1, k2))
    # Alt kirilim / toplam: a'nin parcalari = b'nin parcalari + bir parca
    tset = {k: tuple(t) for k, t in tok.items()}
    ters = {}
    for k, t in tset.items():
        ters.setdefault(t, k)
    for k, t in tset.items():
        for i in range(len(t)):
            ust = t[:i] + t[i + 1:]
            if ust in ters and ters[ust] != k:
                b = ters[ust]
                if (k, b) not in gor and _istat(k, istat) in ("toplam", "adet") \
                        and _istat(k, istat) == _istat(b, istat):
                    cikti.append((k, b, "pay")); gor.add((k, b))
    return cikti


def uygunluk(b, hedef_ikili, segmentler=()):
    """(mumkun kodlar, {kod: neden}) birim icin."""
    oz = b.get("ozet") or {}
    mumkun, imkansiz = [], {}

    def ekle(kod, olur, neden=""):
        if olur:
            mumkun.append(kod)
        else:
            imkansiz[kod] = neden
    if b["tur"] == "satir":
        ekle("eksik_sayi", True)
        return mumkun, imkansiz
    if b["tur"] == "grup":
        ekle("yogunlasma", True)
        return mumkun, imkansiz
    if b["tur"] == "cift":
        t = b.get("cift")
        if t == "kat":
            ekle("kesisim", True)
            return mumkun, imkansiz
        if t == "arasi":
            if b.get("tip") == "kategorik":
                ekle("kesisim", True)
            else:
                ekle("net", True)
                ekle("cift_oran", True)
                ekle("carpim", True)
            return mumkun, imkansiz
        ekle("net", t == "yon", "Yalnız gelen ile giden gibi yön çiftinde.")
        ekle("cift_oran", t == "yon", "Yalnız gelen ile giden gibi yön çiftinde.")
        ekle("ort", t == "ort", "Yalnız tutar ile adet çiftinde.")
        ekle("pay", t == "pay", "Yalnız alt kırılım ile toplam çiftinde.")
        ekle("carpim", True)
        return mumkun, imkansiz
    if b["tip"] == "kategorik":
        tekil = oz.get("tekil") or 0
        ekle("frekans", True)
        ekle("onehot", tekil <= ONEHOT_EN_COK, "%s değer var; one-hot en çok %s değerli kolonda."
             % (tekil, ONEHOT_EN_COK))
        ekle("woe", hedef_ikili, "Hedef iki sınıflı (0 ve 1) değil.")
        ekle("hedef_ort", hedef_ikili, "Hedef iki sınıflı (0 ve 1) değil.")
        return mumkun, imkansiz
    neg = bool(oz.get("negatif"))
    tekil = oz.get("tekil") or 0
    sifir = oz.get("sifir_pay") or 0
    ekle("log", not neg, "Negatif değer var; işaretli log kullanılır.")
    ekle("islog", neg, "Negatif değer yok; log yeterli.")
    ekle("karekok", not neg, "Negatif değer var.")
    ekle("kare", tekil >= 3, "Farklı değer sayısı az (%s); kare terimi yeni bilgi taşımaz." % tekil)
    az = "Farklı değer sayısı az (%s); dağılım dönüşümü anlamsız." % tekil
    ekle("yeo", tekil >= TEKIL_EN_AZ, az)
    ekle("winsor", tekil >= TEKIL_EN_AZ, az)
    ekle("rank", tekil >= TEKIL_EN_AZ, az)
    ekle("zskor", True)
    ekle("robust", tekil >= TEKIL_EN_AZ, az)
    ekle("isaret", neg, "Negatif değer yok; işaret sıfır bayrağıyla aynı bilgiyi verir.")
    ekle("sifir", 0.01 <= sifir <= 0.99, "Sıfırın payı %%%s; bayrak bilgi taşımaz."
         % ("%.1f" % (100 * sifir)).replace(".", ","))
    ekle("esik", True)
    ekle("dilim", tekil >= TEKIL_EN_AZ, az)
    ekle("kova", True)
    ekle("segment", bool(segmentler), "Segment olarak kullanılabilecek az değerli kategorik kolon yok.")
    ekle("grup_oran", bool(segmentler) and not neg,
         "Segment kolonu yok ya da negatif değer var (medyana oran anlamsız).")
    if b["tur"] == "aile":
        n = len(b["kolonlar"])
        ekle("oran", True)
        ekle("fark", True)
        ekle("norm", True)
        topl = b.get("istat") in ("toplam", "adet", "")
        ekle("buyume", topl and not neg,
             "Yalnız toplam ya da adet gibi toplanabilir ve negatif olmayan ölçüde.")
        ekle("egim", n >= 3, "En az 3 pencere gerekir (%s var)." % n)
        ekle("dk", n >= 3, "En az 3 pencere gerekir (%s var)." % n)
        ekle("ardisik", n >= 3 and topl and not neg,
             "En az 3 pencere ve toplanabilir, negatif olmayan ölçü gerekir.")
        ekle("oran_tum", n >= 3, "Bütün çiftler için en az 3 pencere gerekir (2 pencerede Oran ile aynı).")
        ekle("fark_tum", n >= 3, "Bütün çiftler için en az 3 pencere gerekir (2 pencerede Fark ile aynı).")
        dn = "Toplanabilir (toplam ya da adet) ve negatif olmayan birikimli ölçü gerekir."
        ekle("donem", topl and not neg, dn)
        ekle("donem_pay", topl and not neg, dn)
        ekle("donem_oran", topl and not neg, dn)
        ekle("en_yogun", n >= 2 and topl and not neg,
             "Toplanabilir ve negatif olmayan ölçü gerekir.")
    return mumkun, imkansiz


# ---------------------------------------------------------------------------
# KURAL ONERISI (dil modeline ulasilamazsa)
# ---------------------------------------------------------------------------
def kural_onerisi(b, model_turu="agac", katki=None):
    """{"sec", "param", "gerekce", "secilmeyen"}: veriye bakan varsayilan.
    Katki olcumu varsa: olculen kodlardan IV artisi belirgin ve kaynakla
    ayni sirada olmayanlar secilir, gerekce sayilarla."""
    if katki and katki.get("kodlar"):
        kod = katki["kodlar"]
        aday = sorted([c for c in katki_kodlari(b, model_turu) if katki_degerli(kod.get(c))],
                      key=lambda c: -kod[c]["iv"])
        # Birbiriyle ayni sirada olanlardan (benzer) IV'si yuksek olan kalir.
        sec = []
        for c in aday:
            if not any(x in (kod[c].get("benzer") or {}) for x in sec):
                sec.append(c)
        sec = [c for c in katki_kodlari(b, model_turu) if c in sec and c not in MONOTON]
        for c, ust, _n in TEKRAR_KESIN:
            if c in sec and ust in sec:
                sec.remove(c)
        if model_turu == "dogrusal":
            sec += [c for c in kural_onerisi(b, model_turu)["sec"] if c in MONOTON and c not in sec]
        param = {c: {"segment": kod[c]["segment"]} for c in sec if c in ("segment", "grup_oran")
                 and kod[c].get("segment")}
        g1, g2 = katki_gerekcesi(b, katki, sec, model_turu)
        return {"sec": sec, "param": param, "gerekce": g1 or "Ölçülen dönüşümlerin hiçbiri belirgin IV artışı "
                "getirmedi.", "secilmeyen": g2}
    oz = b.get("ozet") or {}
    mm = set(model_mumkun(b, model_turu))
    sec, neden = [], []
    if b["tur"] == "satir":
        return {"sec": ["eksik_sayi"], "param": {}, "secilmeyen": "",
                "gerekce": "%s kolonda boş hücre var; satırdaki eksik sayısı eksik bilgi profilini taşır."
                % oz.get("bosu_olan", 0)}
    if b["tur"] == "grup":
        return {"sec": ["yogunlasma"], "param": {}, "secilmeyen": "",
                "gerekce": "Aynı toplamın %s alt kırılımı var: dağılımın tek kırılımda toplanıp "
                "toplanmadığı (yoğunlaşma)." % len(b["kolonlar"])}
    if b["tur"] == "cift" and b.get("cift") == "arasi":
        return {"sec": [c for c in b.get("oneri_islem") or [] if c in mm], "param": {},
                "secilmeyen": "", "gerekce": b.get("gerekce") or ""}
    if b["tur"] == "cift":
        t = b.get("cift")
        sec = {"yon": ["net", "cift_oran"], "ort": ["ort"], "pay": ["pay"]}.get(t, [])
        return {"sec": [s for s in sec if s in mm], "param": {}, "secilmeyen": "",
                "gerekce": {"yon": "Gelen ile giden çifti: net akış ve oranı.",
                            "ort": "Tutar ile adet çifti: işlem başına ortalama tutar.",
                            "pay": "Alt kırılım ile toplam: alt kırılımın payı."}.get(t, "")}
    if b["tip"] == "kategorik":
        sec = ["frekans"]
        if "onehot" in mm and (oz.get("tekil") or 0) <= 5:
            sec.append("onehot")
        if "woe" in mm:
            sec.append("woe")
        return {"sec": sec, "param": {}, "secilmeyen": "",
                "gerekce": "%s farklı değer: frekans%s%s." % (
                    oz.get("tekil"), ", one-hot" if "onehot" in sec else "",
                    ", WoE (hedef iki sınıflı)" if "woe" in sec else "")}
    carp = oz.get("carpiklik") or 0
    if b["tur"] == "aile":
        # Normalize oran, oranin sabit katidir (ayni bilgi); yalniz oran.
        sec += ["oran"]
        neden.append("aynı ölçünün %s penceresi: kısa / uzun pencere oranı"
                     % len(b["kolonlar"]))
        if "egim" in mm:
            sec.append("egim")
            neden.append("eğim")
    if carp > 1:
        if "log" in mm:
            sec.append("log")
        elif "islog" in mm:
            sec.append("islog")
        neden.append("sağa çarpık (çarpıklık %s)" % ("%.1f" % carp).replace(".", ","))
    uk = oz.get("uc_kat")
    if uk and uk >= 10 and "winsor" in mm:
        sec.append("winsor")
        neden.append("en büyük değer %%99'luk değerin %s katı" % int(uk))
    if not sec and "rank" in mm:
        sec.append("rank")
        neden.append("dağılımdan bağımsız sıra")
    sec = [s for s in sec if s in mm]
    if not sec and model_turu == "agac" and b["tur"] == "kolon" and b.get("tip") != "kategorik":
        neden = ["ağaç modeli ham kolonu doğrudan kullanır; tek kolon dönüşümü bilgi katmaz"]
    return {"sec": sec, "param": {}, "secilmeyen": "",
            "gerekce": ("; ".join(neden) + ".").capitalize() if neden else ""}


# ---------------------------------------------------------------------------
# UYGULAMA
# ---------------------------------------------------------------------------
def _sayi(s):
    return pd.to_numeric(s, errors="coerce")


def _bol(a, b):
    return a / b.replace(0, np.nan)


def _yj(x, lam):
    x = np.asarray(x, dtype=float)
    y = np.full_like(x, np.nan)
    p = x >= 0
    if abs(lam) > 1e-8:
        y[p] = ((x[p] + 1) ** lam - 1) / lam
    else:
        y[p] = np.log1p(x[p])
    n = ~p & ~np.isnan(x)
    if abs(lam - 2) > 1e-8:
        y[n] = -(((-x[n] + 1) ** (2 - lam)) - 1) / (2 - lam)
    else:
        y[n] = -np.log1p(-x[n])
    return y


def _yj_lambda(x):
    """Yeo-Johnson parametresi: en buyuk olabilirlik, -2 ile 4 arasi izgara."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) < 3:
        return 1.0
    en, en_ll = 1.0, -np.inf
    log_terim = np.sign(x) * np.log1p(np.abs(x))
    for lam in np.linspace(-2, 4, 61):
        y = _yj(x, lam)
        v = np.var(y)
        if not np.isfinite(v) or v <= 0:
            continue
        ll = -len(x) / 2.0 * np.log(v) + (lam - 1) * log_terim.sum()
        if ll > en_ll:
            en, en_ll = float(lam), ll
    return round(en, 3)


def _kat_no(n):
    return np.arange(n) % KAT_SAYISI


def _hedef_kodla(k, y, tr, tur):
    """k: kategori (str), y: hedef (0/1), tr: train maskesi. Doner: (seri,
    tam train haritasi, varsayilan). Train satirlari kat disi."""
    ktr, ytr = k[tr], y[tr]
    gecerli = ytr.notna()
    ktr, ytr = ktr[gecerli], ytr[gecerli].astype(float)

    def harita(kk, yy):
        g = yy.groupby(kk)
        n, olay = g.size(), g.sum()
        if tur == "woe":
            B, G = float(yy.sum()), float(len(yy) - yy.sum())
            olmayan = n - olay
            return (np.log((olmayan + 0.5) / (G + 0.5)) - np.log((olay + 0.5) / (B + 0.5))), 0.0
        onsel = float(yy.mean()) if len(yy) else 0.0
        return (olay + HEDEF_YUMUSAK * onsel) / (n + HEDEF_YUMUSAK), onsel
    tam, vars_ = harita(ktr, ytr)
    sonuc = k.map(tam).astype(float).fillna(vars_)
    # Kat disi: train satiri kendi katinin disindaki satirlardan
    idx = ktr.index
    katlar = pd.Series(_kat_no(len(idx)), index=idx)
    for f in range(KAT_SAYISI):
        ic = katlar.index[katlar == f]
        dis_ = katlar.index[katlar != f]
        h, v = harita(ktr[dis_], ytr[dis_])
        sonuc.loc[ic] = ktr[ic].map(h).astype(float).fillna(v).values
    return sonuc, {str(a): round(float(b), 6) for a, b in tam.items()}, round(float(vars_), 6)


def _kategori(s):
    return s.astype(object).where(s.notna(), "__BOS__").astype(str)


def _kodla(ad, ifade):
    return 'df["%s"] = %s' % (ad, ifade)


def uygula(df, birimler, karar, tr, hedef=None):
    """Kararlari uygular. karar: {birim id: {"sec": [kod], "param": {kod:
    {...}}}}. tr: train maskesi (bool Series). Doner: (yeni {ad: seri},
    kayitlar [{"ad", "kod", "birim", "kaynaklar", "kod_satiri", "aciklama",
    "ogrenilen"}], hatalar [str])."""
    yeni, kayit, hatalar = {}, [], []
    tr = tr.reindex(df.index).fillna(False).astype(bool) if tr is not None \
        else pd.Series(True, index=df.index)
    y = pd.to_numeric(df[hedef], errors="coerce") if hedef and hedef in df.columns else None
    harita = {b["id"]: b for b in birimler}

    def koy(ad, seri, kod, b, kaynaklar, satir, aciklama, ogrenilen=None):
        ad = guvenli_ad(ad) if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", ad) else ad
        if ad in df.columns or ad in yeni:
            return
        seri = pd.Series(seri, index=df.index).astype(float)
        seri = seri.where(np.isfinite(seri))
        yeni[ad] = seri
        kayit.append({"ad": ad, "kod": kod, "birim": b["id"], "kaynaklar": list(kaynaklar),
                      "kod_satiri": satir, "aciklama": aciklama, "ogrenilen": ogrenilen or {}})

    for bid, k in (karar or {}).items():
        b = harita.get(bid)
        if not b:
            continue
        param = k.get("param") or {}
        for kod in k.get("sec") or []:
            if kod not in (b.get("mumkun") or []):
                continue
            try:
                _birim_uygula(df, b, kod, param.get(kod) or {}, tr, y, koy)
            except Exception as e:      # tek donusum hatasi uretimi durdurmasin
                hatalar.append("%s, %s: %s" % (b["ad"], KATALOG_HARITA[kod]["ad"], str(e)[:120]))
    return yeni, kayit, hatalar


def _f(v):
    return repr(float(v))


def _birim_uygula(df, b, kod, param, tr, y, koy):
    kol = b["kolonlar"]
    ad_ = KATALOG_HARITA[kod]["ad"]
    if b["tur"] == "satir":
        alt = df[kol]
        sayi = alt.isna().sum(axis=1).astype(float)
        liste = repr(list(kol))
        koy("SATIR_EKSIK_SAYISI", sayi, kod, b, kol,
            _kodla("SATIR_EKSIK_SAYISI", "df[%s].isna().sum(axis=1).astype(float)" % liste),
            "Satırda boş olan kolon sayısı (%s kolon üzerinden)." % len(kol))
        koy("SATIR_EKSIK_ORANI", sayi / float(len(kol)), kod, b, kol,
            _kodla("SATIR_EKSIK_ORANI", "df[%s].isna().sum(axis=1) / %s" % (liste, float(len(kol)))),
            "Satırda boş olan kolonların oranı (%s kolon üzerinden)." % len(kol))
        return
    if b["tur"] == "grup":
        for grp in b.get("gruplar") or []:
            x = pd.concat([_sayi(df[k]).clip(lower=0) for k in grp], axis=1)
            top = x.sum(axis=1, min_count=1).replace(0, np.nan)
            pay = x.div(top, axis=0)
            kok = guvenli_ad("%s__GRUP%s" % (b["ad"], len(grp)))[:60] if len(grp) else b["ad"]
            kok = b.get("kok_adlar", {}).get(grp[0], kok)
            terim = "pd.concat([%s], axis=1)" % ", ".join('_s(df, "%s").clip(lower=0)' % k for k in grp)
            koy(kok + "__HHI", (pay ** 2).sum(axis=1, min_count=1), kod, b, grp,
                _kodla(kok + "__HHI", "(lambda _t: (_t.div(_t.sum(axis=1, min_count=1).replace(0, np.nan), "
                       "axis=0) ** 2).sum(axis=1, min_count=1))(%s)" % terim),
                "%s kolonlarının toplam içindeki paylarının karelerinin toplamı (HHI): 1'e yakınsa tek "
                "kırılımda yoğunlaşma." % ", ".join(grp))
            koy(kok + "__MAXPAY", pay.max(axis=1), kod, b, grp,
                _kodla(kok + "__MAXPAY", "(lambda _t: _t.div(_t.sum(axis=1, min_count=1).replace(0, np.nan), "
                       "axis=0).max(axis=1))(%s)" % terim),
                "%s kolonlarından en büyüğünün toplam içindeki payı." % ", ".join(grp))
        return
    if b["tur"] == "cift" and kod == "kesisim":
        for a, c in (b.get("ciftler") or [kol[:2]]):
            k2 = _kategori(df[a]) + "|" + _kategori(df[c])
            ad = guvenli_ad("%s__X__%s" % (a, c))
            ifk = ('(df["%s"].astype(object).where(df["%s"].notna(), "__BOS__").astype(str) + "|" + '
                   'df["%s"].astype(object).where(df["%s"].notna(), "__BOS__").astype(str))' % (a, a, c, c))
            if y is not None:
                seri, hm, vars_ = _hedef_kodla(k2, y, tr, "woe")
                koy(ad + "__WOE", seri, kod, b, [a, c],
                    _kodla(ad + "__WOE", "%s.map(%r).fillna(%r)" % (ifk, hm, vars_)),
                    "%s ve %s birleşik değerinin WoE'si (eğitimden, eğitimde kat dışı)." % (a, c),
                    {"harita": hm})
            else:
                h = k2[tr].value_counts(normalize=True)
                hm = {str(a_): round(float(v), 6) for a_, v in h.items()}
                koy(ad + "__FRK", k2.map(hm).fillna(0.0), kod, b, [a, c],
                    _kodla(ad + "__FRK", "%s.map(%r).fillna(0.0)" % (ifk, hm)),
                    "%s ve %s birleşik değerinin eğitim satırlarındaki payı." % (a, c), {"harita": hm})
        return
    if b["tur"] == "cift":
        for a, c in (b.get("ciftler") or [kol[:2]]):
            xa, xc = _sayi(df[a]), _sayi(df[c])
            if kod == "carpim":
                koy("%s__X__%s" % (a, c), xa * xc, kod, b, [a, c],
                    _kodla("%s__X__%s" % (a, c), '_s(df, "%s") * _s(df, "%s")' % (a, c)),
                    "%s çarpı %s." % (a, c))
                continue
            if kod == "net":
                koy("%s__MINUS__%s" % (a, c), xa - xc, kod, b, [a, c],
                    _kodla("%s__MINUS__%s" % (a, c), '_s(df, "%s") - _s(df, "%s")' % (a, c)),
                    "%s eksi %s (%s)." % (a, c, "net akış" if b.get("cift") == "yon" else "fark"))
            else:
                aciklama = {"cift_oran": "%s bölü %s.", "ort": "%s bölü %s: adet başına ortalama tutar.",
                            "pay": "%s bölü %s: alt kırılımın toplam içindeki payı."}[kod] % (a, c)
                koy("%s__DIV__%s" % (a, c), _bol(xa, xc), kod, b, [a, c],
                    _kodla("%s__DIV__%s" % (a, c), '_bol(_s(df, "%s"), _s(df, "%s"))' % (a, c)),
                    aciklama + " Payda sıfırsa boş.")
        return
    if b["tur"] == "aile" and KATALOG_HARITA[kod]["grup"] == "aile":
        g = b["gunler"]
        x = [_sayi(df[k]) for k in kol]
        if kod in ("oran", "fark", "norm", "buyume"):
            for i in range(len(kol) - 1):
                a, c, ga, gc = kol[i], kol[i + 1], g[i], g[i + 1]
                if kod == "oran":
                    koy("%s__DIV__%s" % (a, c), _bol(x[i], x[i + 1]), kod, b, [a, c],
                        _kodla("%s__DIV__%s" % (a, c), '_bol(_s(df, "%s"), _s(df, "%s"))' % (a, c)),
                        "%s bölü %s (kısa / uzun pencere). Payda sıfırsa boş." % (a, c))
                elif kod == "fark":
                    koy("%s__MINUS__%s" % (a, c), x[i] - x[i + 1], kod, b, [a, c],
                        _kodla("%s__MINUS__%s" % (a, c), '_s(df, "%s") - _s(df, "%s")' % (a, c)),
                        "%s eksi %s (kısa ve uzun pencere farkı)." % (a, c))
                elif kod == "norm":
                    koy("%s__NDIV__%s" % (a, c), _bol(x[i] / ga, x[i + 1] / gc), kod, b, [a, c],
                        _kodla("%s__NDIV__%s" % (a, c), '_bol(_s(df, "%s") / %s, _s(df, "%s") / %s)'
                               % (a, float(ga), c, float(gc))),
                        "%s kolonunun günlük ortalamasının (%s gün) %s kolonunun günlük ortalamasına (%s gün) "
                        "oranı." % (a, ga, c, gc))
                elif kod == "buyume" and gc > ga:
                    onceki = (x[i + 1] - x[i]) * (ga / float(gc - ga))
                    koy("%s__GRW__%s" % (a, c), (x[i] - onceki) / onceki.abs().replace(0, np.nan),
                        kod, b, [a, c],
                        _kodla("%s__GRW__%s" % (a, c),
                               '(_s(df, "%s") - (_s(df, "%s") - _s(df, "%s")) * %s) / '
                               '((_s(df, "%s") - _s(df, "%s")) * %s).abs().replace(0, np.nan)'
                               % (a, c, a, _f(ga / float(gc - ga)), c, a, _f(ga / float(gc - ga)))),
                        "%s kolonunun, %s içinde kalan önceki dönemin aynı uzunluğa (%s gün) düşen "
                        "değerine göre büyümesi. Önceki dönem sıfırsa boş." % (a, c, ga))
            return
        if kod in ("oran_tum", "fark_tum"):
            for i in range(len(kol)):
                for j in range(i + 1, len(kol)):
                    a, c = kol[i], kol[j]
                    if kod == "oran_tum":
                        koy("%s__DIV__%s" % (a, c), _bol(x[i], x[j]), kod, b, [a, c],
                            _kodla("%s__DIV__%s" % (a, c), '_bol(_s(df, "%s"), _s(df, "%s"))' % (a, c)),
                            "%s bölü %s (kısa / uzun pencere). Payda sıfırsa boş." % (a, c))
                    else:
                        koy("%s__MINUS__%s" % (a, c), x[i] - x[j], kod, b, [a, c],
                            _kodla("%s__MINUS__%s" % (a, c), '_s(df, "%s") - _s(df, "%s")' % (a, c)),
                            "%s eksi %s (kısa ve uzun pencere farkı)." % (a, c))
            return
        if kod in ("donem", "donem_pay", "donem_oran"):
            # Donemler: 1. donem en kisa pencere; k. donem = x_k eksi x_(k-1),
            # gunleri (g_(k-1), g_k]. Ad: AILE__DNM_<bas>_<son> (gun).
            sinir = [0] + list(g)
            parca, pkod, etiket = [], [], []
            for i, k_ in enumerate(kol):
                if i == 0:
                    parca.append(x[0]); pkod.append('_s(df, "%s")' % k_)
                else:
                    parca.append(x[i] - x[i - 1])
                    pkod.append('(_s(df, "%s") - _s(df, "%s"))' % (k_, kol[i - 1]))
                etiket.append((sinir[i] + 1, sinir[i + 1]))
            ad0 = b["ad"]
            if kod == "donem":
                for i in range(1, len(kol)):
                    a_, z_ = etiket[i]
                    ad = "%s__DNM_%s_%s" % (ad0, a_, z_)
                    koy(ad, parca[i], kod, b, [kol[i], kol[i - 1]], _kodla(ad, pkod[i]),
                        "%s. ile %s. gün arasındaki değer (%s eksi %s)." % (a_, z_, kol[i], kol[i - 1]))
            elif kod == "donem_pay":
                for i in range(len(kol)):
                    a_, z_ = etiket[i]
                    ad = "%s__DPAY_%s_%s" % (ad0, a_, z_)
                    koy(ad, _bol(parca[i], x[-1]), kod, b, sorted({kol[i], kol[-1]} | ({kol[i - 1]} if i else set())),
                        _kodla(ad, '_bol(%s, _s(df, "%s"))' % (pkod[i], kol[-1])),
                        "%s. ile %s. gün arasındaki değerin %s içindeki payı. Payda sıfırsa boş."
                        % (a_, z_, kol[-1]))
            else:
                for i in range(len(kol) - 1):
                    (a1, z1), (a2, z2) = etiket[i], etiket[i + 1]
                    u1, u2 = float(z1 - a1 + 1), float(z2 - a2 + 1)
                    ad = "%s__DORAN_%s_%s__%s_%s" % (ad0, a1, z1, a2, z2)
                    koy(ad, _bol(parca[i] / u1, parca[i + 1] / u2), kod, b, kol[:i + 2],
                        _kodla(ad, '_bol(%s / %s, %s / %s)' % (pkod[i], u1, pkod[i + 1], u2)),
                        "%s. ile %s. gün arasının günlük ortalaması bölü %s. ile %s. gün arasının günlük "
                        "ortalaması (yeni dönem bölü önceki dönem). Payda sıfırsa boş." % (a1, z1, a2, z2))
            return
        if kod in ("ardisik", "en_yogun"):
            # Pencereler arasindaki donemler (kisa pencere en yeni): donem k =
            # x_k - x_(k-1), gun g_k - g_(k-1); x_0 = 0.
            parca, parca_kod = [], []
            onceki, onceki_kod, og = None, None, 0
            for xx, k_, gg in zip(x, kol, g):
                parca.append((xx - onceki) if onceki is not None else xx)
                parca_kod.append(('(_s(df, "%s") - _s(df, "%s"))' % (k_, onceki_kod))
                                 if onceki_kod else '_s(df, "%s")' % k_)
                onceki, onceki_kod = xx, k_
            uzun = [gg - og_ for gg, og_ in zip(g, [0] + list(g[:-1]))]
            if kod == "ardisik":
                hiz = [p_ / float(u) for p_, u in zip(parca, uzun)]
                say = sum(((hiz[i] > hiz[i + 1]).astype(float)) for i in range(len(hiz) - 1))
                bos = pd.concat(hiz, axis=1).isna().any(axis=1)
                terim = " + ".join("((%s / %s) > (%s / %s)).astype(float)" % (
                    parca_kod[i], float(uzun[i]), parca_kod[i + 1], float(uzun[i + 1]))
                    for i in range(len(hiz) - 1))
                koy(b["ad"] + "__ARDISIK", say.where(~bos), kod, b, kol,
                    _kodla(b["ad"] + "__ARDISIK", "(%s).where(~pd.concat([%s], axis=1).isna().any(axis=1))"
                           % (terim, ", ".join('_s(df, "%s")' % k_ for k_ in kol))),
                    "Pencereler (%s gün) arasındaki dönemlerde günlük ortalamanın eskiden yeniye kaç "
                    "kez arttığı." % ", ".join(str(x_) for x_ in g))
            else:
                top = x[-1].replace(0, np.nan)
                en = pd.concat(parca, axis=1).max(axis=1)
                koy(b["ad"] + "__ENYOGUN", en / top, kod, b, kol,
                    _kodla(b["ad"] + "__ENYOGUN", "pd.concat([%s], axis=1).max(axis=1) / _s(df, \"%s\").replace(0, np.nan)"
                           % (", ".join(parca_kod), kol[-1])),
                    "Pencereler (%s gün) arasındaki dönemlerden en yoğun olanın %s içindeki payı."
                    % (", ".join(str(x_) for x_ in g), kol[-1]))
            return
        gun = np.array(g, dtype=float)
        oranlar = pd.concat([xx / gg for xx, gg in zip(x, g)], axis=1).to_numpy(dtype=float)
        if kod == "egim":
            xg = np.log(gun)
            xm = xg - xg.mean()
            egim = np.nansum(oranlar * xm, axis=1) / float((xm ** 2).sum())
            egim = np.where(np.isnan(oranlar).any(axis=1), np.nan, egim)
            terim = " + ".join('_s(df, "%s") / %s * %s' % (k, float(gg), _f(w))
                               for k, gg, w in zip(kol, g, xm / float((xm ** 2).sum())))
            koy(b["ad"] + "__EGIM", egim, kod, b, kol, _kodla(b["ad"] + "__EGIM", terim),
                "Günlük ortalamanın pencere uzunluğuna (%s gün, log ölçek) göre eğimi; negatifse "
                "son dönem daha yoğun." % ", ".join(str(x_) for x_ in g))
        elif kod == "dk":
            ort = np.nanmean(oranlar, axis=1)
            std = np.nanstd(oranlar, axis=1)
            with np.errstate(invalid="ignore", divide="ignore"):
                dk = np.where(ort != 0, std / np.abs(ort), np.nan)
            dk = np.where(np.isnan(oranlar).any(axis=1), np.nan, dk)
            sutun = "pd.concat([%s], axis=1)" % ", ".join(
                '_s(df, "%s") / %s' % (k, float(gg)) for k, gg in zip(kol, g))
            koy(b["ad"] + "__DK", dk, kod, b, kol,
                _kodla(b["ad"] + "__DK", "(lambda _t: _t.std(axis=1, ddof=0) / _t.mean(axis=1).abs()"
                       ".replace(0, np.nan))(%s)" % sutun),
                "Pencerelerin (%s gün) günlük ortalamalarının değişkenlik katsayısı (std / "
                "ortalama)." % ", ".join(str(x_) for x_ in g))
        return
    # Tekli ya da kategorik: her kolona
    for k in kol:
        _tekli_uygula(df, b, k, kod, param, tr, y, koy)


def _tekli_uygula(df, b, k, kod, param, tr, y, koy):
    if KATALOG_HARITA[kod]["grup"] == "kategorik":
        c = _kategori(df[k])
        ifk = 'df["%s"].astype(object).where(df["%s"].notna(), "__BOS__").astype(str)' % (k, k)
        if kod == "frekans":
            h = c[tr].value_counts(normalize=True)
            hm = {str(a): round(float(v), 6) for a, v in h.items()}
            koy(k + "__FRK", c.map(hm).fillna(0.0), kod, b, [k],
                _kodla(k + "__FRK", "%s.map(%r).fillna(0.0)" % (ifk, hm)),
                "%s değerinin eğitim satırlarındaki payı (görülmemiş değer 0)." % k, {"harita": hm})
        elif kod == "onehot":
            for v in c[tr].value_counts().index[:ONEHOT_EN_COK]:
                ad = "%s__OH_%s" % (k, guvenli_ad(v))
                koy(ad, (c == v).astype(float), kod, b, [k],
                    _kodla(ad, "(%s == %r).astype(float)" % (ifk, str(v))),
                    "%s değeri «%s» ise 1, değilse 0." % (k, "boş" if v == "__BOS__" else v))
        elif kod in ("woe", "hedef_ort") and y is not None:
            seri, hm, vars_ = _hedef_kodla(c, y, tr, kod)
            ek = "__WOE" if kod == "woe" else "__TE"
            koy(k + ek, seri, kod, b, [k],
                _kodla(k + ek, "%s.map(%r).fillna(%r)" % (ifk, hm, vars_)),
                ("%s değerinin WoE'si: ln(olay olmayan payı / olay payı), eğitim satırlarından; "
                 "eğitimde kat dışı (%s kat)." if kod == "woe" else
                 "%s değerinin yumuşatılmış hedef oranı, eğitim satırlarından; eğitimde kat dışı "
                 "(%s kat).") % (k, KAT_SAYISI), {"harita": hm, "varsayilan": vars_})
        return
    x = _sayi(df[k])
    xt = x[tr].dropna()
    s_ = '_s(df, "%s")' % k
    if kod == "log":
        koy(k + "__LOG", np.log1p(x.clip(lower=0)), kod, b, [k],
            _kodla(k + "__LOG", "np.log1p(%s.clip(lower=0))" % s_), "log(1 + %s)." % k)
    elif kod == "islog":
        koy(k + "__SLOG", np.sign(x) * np.log1p(x.abs()), kod, b, [k],
            _kodla(k + "__SLOG", "np.sign(%s) * np.log1p(%s.abs())" % (s_, s_)),
            "İşaretli log: işaret(%s) · log(1 + |%s|)." % (k, k))
    elif kod == "karekok":
        koy(k + "__SQRT", np.sqrt(x.clip(lower=0)), kod, b, [k],
            _kodla(k + "__SQRT", "np.sqrt(%s.clip(lower=0))" % s_), "%s kolonunun karekökü." % k)
    elif kod == "kare":
        koy(k + "__KARE", x ** 2, kod, b, [k], _kodla(k + "__KARE", "%s ** 2" % s_),
            "%s kolonunun karesi." % k)
    elif kod == "yeo" and len(xt) > 2:
        lam = _yj_lambda(xt.to_numpy())
        poz = ("np.log1p(%s.clip(lower=0))" % s_) if abs(lam) < 1e-8 else \
            ("((%s.clip(lower=0) + 1) ** %s - 1) / %s" % (s_, _f(lam), _f(lam)))
        neg = ("-np.log1p(-%s.clip(upper=0))" % s_) if abs(lam - 2) < 1e-8 else \
            ("-((-%s.clip(upper=0) + 1) ** %s - 1) / %s" % (s_, _f(2 - lam), _f(2 - lam)))
        koy(k + "__YJ", _yj(x.to_numpy(dtype=float), lam), kod, b, [k],
            _kodla(k + "__YJ", "pd.Series(np.where(%s >= 0, %s, %s), index=df.index).where(%s.notna())"
                   % (s_, poz, neg, s_)),
            "%s kolonunun Yeo-Johnson dönüşümü (λ = %s, eğitim satırlarından)." % (
                k, str(lam).replace(".", ",")), {"lambda": lam})
    elif kod == "winsor" and len(xt) > 1:
        alt, ust = float(xt.quantile(WINSOR_ALT)), float(xt.quantile(WINSOR_UST))
        koy(k + "__WNS", x.clip(alt, ust), kod, b, [k],
            _kodla(k + "__WNS", "%s.clip(%s, %s)" % (s_, _f(alt), _f(ust))),
            "%s, eğitim satırlarının %%1 (%s) ve %%99 (%s) değerlerine kırpılmış." % (
                k, _sayi_yaz(alt), _sayi_yaz(ust)), {"alt": alt, "ust": ust})
    elif kod == "rank" and len(xt) > 1:
        izgara = [round(float(v), 6) for v in np.nanpercentile(
            xt.to_numpy(dtype=float), np.linspace(0, 100, RANK_IZGARA + 1))]
        ref = np.asarray(izgara)
        p = np.searchsorted(ref, x.to_numpy(dtype=float), side="right") / float(len(ref))
        koy(k + "__RANK", pd.Series(p, index=df.index).where(x.notna()), kod, b, [k],
            _kodla(k + "__RANK", 'pd.Series(np.searchsorted(np.array(%r), %s.to_numpy(dtype=float), '
                   'side="right") / %s, index=df.index).where(%s.notna())'
                   % (izgara, s_, float(len(ref)), s_)),
            "%s kolonunun eğitim dağılımındaki yüzdeliği (0 ile 1 arası)." % k, {"izgara": izgara})
    elif kod == "zskor" and len(xt) > 1:
        o, sd = float(xt.mean()), float(xt.std(ddof=0))
        if sd > 0:
            koy(k + "__Z", (x - o) / sd, kod, b, [k],
                _kodla(k + "__Z", "(%s - %s) / %s" % (s_, _f(o), _f(sd))),
                "%s kolonunun z-skoru (ortalama %s, std %s, eğitimden)." % (k, _sayi_yaz(o), _sayi_yaz(sd)),
                {"ortalama": o, "std": sd})
    elif kod == "robust" and len(xt) > 1:
        med = float(xt.median())
        iqr = float(xt.quantile(0.75) - xt.quantile(0.25))
        if iqr > 0:
            koy(k + "__RZ", (x - med) / iqr, kod, b, [k],
                _kodla(k + "__RZ", "(%s - %s) / %s" % (s_, _f(med), _f(iqr))),
                "(%s eksi medyan) bölü çeyrekler arası açıklık (medyan %s, açıklık %s, eğitimden)."
                % (k, _sayi_yaz(med), _sayi_yaz(iqr)), {"medyan": med, "iqr": iqr})
    elif kod == "isaret":
        koy(k + "__ISR", np.sign(x), kod, b, [k], _kodla(k + "__ISR", "np.sign(%s)" % s_),
            "%s negatifse eksi 1, sıfırsa 0, pozitifse 1." % k)
    elif kod == "sifir":
        koy(k + "__SIFIR", (x == 0).astype(float).where(x.notna()), kod, b, [k],
            _kodla(k + "__SIFIR", "(%s == 0).astype(float).where(%s.notna())" % (s_, s_)),
            "%s sıfırsa 1, değilse 0." % k)
    elif kod == "esik":
        try:
            t = float(str(param.get("esik")).replace(",", "."))
        except (TypeError, ValueError):
            raise ValueError("eşik değeri verilmedi")
        alt = str(param.get("yon") or ">=") in ("<=", "<", "alt")
        ad = "%s__%s_%s" % (k, "LE" if alt else "GE", guvenli_ad(("%g" % t).replace("-", "M")))
        seri = (x <= t) if alt else (x >= t)
        koy(ad, seri.astype(float).where(x.notna()), kod, b, [k],
            _kodla(ad, "(%s %s %s).astype(float).where(%s.notna())" % (s_, "<=" if alt else ">=",
                                                                       _f(t), s_)),
            "%s %s %s ise 1, değilse 0." % (k, "≤" if alt else "≥", ("%g" % t).replace(".", ",")),
            {"esik": t, "yon": "<=" if alt else ">="})
    elif kod == "dilim" and len(xt) > 1:
        sinir = sorted(set(round(float(v), 6) for v in
                           np.nanpercentile(xt.to_numpy(dtype=float), np.linspace(0, 100, DILIM_SAYI + 1))[1:-1]))
        koy(k + "__DLM", pd.Series(np.searchsorted(np.array(sinir), x.to_numpy(dtype=float),
                                                   side="right") + 1.0, index=df.index).where(x.notna()),
            kod, b, [k],
            _kodla(k + "__DLM", 'pd.Series(np.searchsorted(np.array(%r), %s.to_numpy(dtype=float), '
                   'side="right") + 1.0, index=df.index).where(%s.notna())' % (sinir, s_, s_)),
            "%s kolonunun eğitim satırlarına göre eşit frekanslı dilim numarası (1 ile %s arası)."
            % (k, len(sinir) + 1), {"sinirlar": sinir})
    elif kod == "kova":
        try:
            sinir = sorted(set(float(str(v).replace(",", ".")) for v in (param.get("sinirlar") or [])))
        except (TypeError, ValueError):
            raise ValueError("kova sınırları sayı değil")
        if not sinir:
            raise ValueError("kova sınırları verilmedi")
        koy(k + "__KOVA", pd.Series(np.searchsorted(np.array(sinir), x.to_numpy(dtype=float), side="right")
                                    + 1.0, index=df.index).where(x.notna()), kod, b, [k],
            _kodla(k + "__KOVA", 'pd.Series(np.searchsorted(np.array(%r), %s.to_numpy(dtype=float), '
                   'side="right") + 1.0, index=df.index).where(%s.notna())' % (sinir, s_, s_)),
            "%s kovası (sınırlar %s; ilk kova 1)." % (k, ", ".join(_sayi_yaz(v) for v in sinir)),
            {"sinirlar": sinir})
    elif kod == "grup_oran":
        seg = str(param.get("segment") or "")
        if seg not in df.columns:
            raise ValueError("segment kolonu verilmedi")
        c = _kategori(df[seg])
        med = pd.DataFrame({"x": x[tr], "c": c[tr]}).dropna().groupby("c")["x"].median()
        hm = {str(a): round(float(v), 6) for a, v in med.items() if v}
        ifs = 'df["%s"].astype(object).where(df["%s"].notna(), "__BOS__").astype(str)' % (seg, seg)
        koy("%s__GRO_%s" % (k, guvenli_ad(seg)), x / c.map(hm).astype(float), kod, b, [k, seg],
            _kodla("%s__GRO_%s" % (k, guvenli_ad(seg)), "%s / %s.map(%r).astype(float)" % (s_, ifs, hm)),
            "%s bölü kendi %s segmentinin medyanı (eğitimden)." % (k, seg), {"medyan": hm})
    elif kod == "segment":
        seg = str(param.get("segment") or "")
        if seg not in df.columns:
            raise ValueError("segment kolonu verilmedi")
        c = _kategori(df[seg])
        g = pd.DataFrame({"x": x[tr], "c": c[tr]}).dropna().groupby("c")["x"]
        ort, std = g.mean(), g.std(ddof=0).replace(0, np.nan)
        ho, hs = {str(a): round(float(v), 6) for a, v in ort.items()}, \
            {str(a): round(float(v), 6) for a, v in std.dropna().items()}
        z = (x - c.map(ho).astype(float)) / c.map(hs).astype(float)
        ifs = 'df["%s"].astype(object).where(df["%s"].notna(), "__BOS__").astype(str)' % (seg, seg)
        koy("%s__ZS_%s" % (k, guvenli_ad(seg)), z, kod, b, [k, seg],
            _kodla("%s__ZS_%s" % (k, guvenli_ad(seg)), "(%s - %s.map(%r).astype(float)) / %s.map(%r)"
                   ".astype(float)" % (s_, ifs, ho, ifs, hs)),
            "%s kolonunun kendi %s segmenti içindeki z-skoru (segment ortalaması ve std eğitimden)."
            % (k, seg), {"ortalama": ho, "std": hs})
        # Segment ici yuzdelik: segment basina 21 noktali izgara
        izg = {}
        for a, grp in pd.DataFrame({"x": x[tr], "c": c[tr]}).dropna().groupby("c")["x"]:
            if len(grp) > 1:
                izg[str(a)] = [round(float(v), 6) for v in np.nanpercentile(grp.to_numpy(dtype=float),
                                                                            np.linspace(0, 100, 21))]
        pct = pd.Series(np.nan, index=df.index)
        for a, ref in izg.items():
            m_ = (c == a) & x.notna()
            pct[m_] = np.searchsorted(np.array(ref), x[m_].to_numpy(dtype=float), side="right") / 21.0
        koy("%s__PCT_%s" % (k, guvenli_ad(seg)), pct, kod, b, [k, seg],
            _kodla("%s__PCT_%s" % (k, guvenli_ad(seg)),
                   "pd.Series([np.searchsorted(np.array(%r.get(_c, [np.nan])), _v, side=\"right\") / 21.0 "
                   "if _c in %r and _v == _v else np.nan for _c, _v in zip(%s, %s)], index=df.index)"
                   % (izg, list(izg), ifs, s_)),
            "%s kolonunun kendi %s segmenti içindeki yüzdeliği (segment dağılımı eğitimden)." % (k, seg),
            {"izgara": izg})


# ---------------------------------------------------------------------------
# DIL MODELI, KART VE SOHBET YARDIMCILARI
# ---------------------------------------------------------------------------
def katalog_metni(uzun=False):
    if uzun:
        return "\n".join("%s: %s (%s). %s Örnek: %s Ne zaman: %s%s" % (
            k, a, GRUP_ADI[g], ACIKLAMA_UZUN[k][0], ACIKLAMA_UZUN[k][1], ACIKLAMA_UZUN[k][2],
            " Ağaç modelinde gereksiz." if k in AGAC_GEREKSIZ else "") for k, a, g, c in KATALOG)
    return "\n".join("%s: %s (%s). %s" % (k, a, GRUP_ADI[g], c) for k, a, g, c in KATALOG)


def _sayi_yaz(v):
    if v is None:
        return "-"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if abs(f) >= 100:
        return "{:,}".format(int(round(f))).replace(",", ".")
    return ("%.3g" % f).replace(".", ",")


def ozet_metni(b):
    oz = b.get("ozet") or {}
    if b["tur"] == "satir":
        return "%s kolon, %s kolonda boş hücre var" % (oz.get("kolon"), oz.get("bosu_olan"))
    if b.get("tip") == "kategorik":
        return "%s farklı değer, boş payı %%%s, örnek: %s" % (
            oz.get("tekil"), _sayi_yaz(100 * (oz.get("bos_pay") or 0)), ", ".join(oz.get("ornek") or [])[:80])
    parca = ["en küçük %s" % _sayi_yaz(oz.get("min")), "en büyük %s" % _sayi_yaz(oz.get("max")),
             "farklı değer %s" % oz.get("tekil"), "sıfır payı %%%s" % _sayi_yaz(100 * (oz.get("sifir_pay") or 0)),
             "çarpıklık %s" % _sayi_yaz(oz.get("carpiklik")), "boş payı %%%s" % _sayi_yaz(100 * (oz.get("bos_pay") or 0))]
    if oz.get("uc_kat"):
        parca.append("en büyük / %%99'luk %s kat" % _sayi_yaz(oz["uc_kat"]))
    if b.get("gunler"):
        parca.append("pencereler (gün): %s" % ", ".join(str(g) for g in b["gunler"]))
    return ", ".join(parca)


# ---------------------------------------------------------------------------
# KATKI OLCUMU: her donusumun urettigi kolonlarin hedefle iliskisi (IV) ve
# kaynak kolonlara benzerligi (Spearman), YALNIZ EGITIM satirlarinda,
# orneklemesiz. Dil modeli kararini ve gerekcesini bu sayilara dayandirir;
# kural onerisi de bunlarla secer.
# IV: 10 esit frekansli aralik (ayni degerler tek aralikta) + bos aralik;
# kategorikte her deger bir aralik. Siralamayi koruyan donusumde aralik
# ayni kalir, IV degismez (agacta gereksiz olmalarinin sayisal karsiligi).
# ---------------------------------------------------------------------------
KATKI_SURUM = 1
# Siralamayi koruyan tek kolon donusumleri: IV'leri kaynakla aynidir. Agacta
# gereksizdir; dogrusal modelde katkilari olcek (dogrusal uyum) ile ilgilidir
# ve IV ile olculemez: olcumle eklenip cikarilmaz.
MONOTON = ("log", "islog", "karekok", "yeo", "winsor", "rank", "zskor", "robust")
KATKI_DILIM = 10
KATKI_ARTIS = 0.02          # IV artisi bundan azsa belirgin katki yok
KATKI_ILISKI = 0.95         # kaynakla sira iliskisi bundan cok ise ayni bilgi
_PARAMLI = ("esik", "kova")  # parametresi kullanicidan / dil modelinden


def iv_hesapla(x, y):
    """x: kolon (egitim satirlari), y: 0/1 (ayni index). IV ya da None."""
    y = np.asarray(y, dtype=float)
    if len(y) == 0:
        return None
    if pd.api.types.is_numeric_dtype(x):
        v = pd.to_numeric(x, errors="coerce").to_numpy(dtype=float)
        dolu = np.isfinite(v)
        if dolu.sum() == 0:
            return None
        tekil = np.unique(v[dolu])
        if len(tekil) <= KATKI_DILIM:
            kod = np.searchsorted(tekil, np.where(dolu, v, tekil[0]))
        else:
            sinir = np.unique(np.quantile(v[dolu], np.linspace(0, 1, KATKI_DILIM + 1)[1:-1]))
            kod = np.searchsorted(sinir, np.where(dolu, v, 0.0), side="left")
        kod = np.where(dolu, kod + 1, 0)
    else:
        kod = pd.factorize(x.astype(object).where(x.notna(), "__BOS__").astype(str))[0]
    k = int(kod.max()) + 1
    n1 = np.bincount(kod, weights=y, minlength=k)
    n = np.bincount(kod, minlength=k).astype(float)
    n0 = n - n1
    t1, t0 = n1.sum(), n0.sum()
    if t1 == 0 or t0 == 0:
        return None
    var = n > 0
    p1 = (n1[var] + 0.5) / (t1 + 0.5 * var.sum())
    p0 = (n0[var] + 0.5) / (t0 + 0.5 * var.sum())
    return float(np.sum((p1 - p0) * np.log(p1 / p0)))


def _sira(x):
    return pd.to_numeric(x, errors="coerce").rank(method="average")


def _iliski(ra, rb):
    m = ra.notna() & rb.notna()
    if m.sum() < 3:
        return None
    a, b = ra[m].to_numpy(dtype=float), rb[m].to_numpy(dtype=float)
    if a.std() == 0 or b.std() == 0:
        return None
    return float(abs(np.corrcoef(a, b)[0, 1]))


def hedef_ikili_mi(df, hedef):
    if not hedef or hedef not in df.columns:
        return False
    yv = set(pd.to_numeric(df[hedef], errors="coerce").dropna().unique().tolist())
    return bool(yv) and yv <= {0, 1}


def katki_kodlari(b, model_turu):
    """Olculecek kodlar: bu model turunde secilebilen, parametresi
    kendiliginden belirlenebilen kodlar."""
    return [c for c in model_mumkun(b, model_turu) if c not in _PARAMLI]


def katki_olc(df, birimler, tr, hedef, model_turu, segmentler=(), onceki=None, ilerleme=None):
    """{birim id: {"imza", "kaynak_iv", "kaynak_kolon", "kodlar": {kod:
    {"iv", "kolon", "artis", "iliski", "kolon_sayisi", "segment"}},
    "olculmeyen": {kod: neden}}}. onceki'de olculmus kodlar tekrar
    olculmez. Yalniz egitim satirlari (tr)."""
    onceki = onceki or {}
    if not hedef_ikili_mi(df, hedef):
        return {}
    tr = pd.Series(tr, index=df.index).fillna(False).astype(bool)
    d = df.loc[tr]
    y = pd.to_numeric(d[hedef], errors="coerce")
    d = d.loc[y.notna()]
    y = y.loc[d.index].astype(float)
    hep = pd.Series(True, index=d.index)
    iv_bel, sira_bel = {}, {}

    def kol_iv(k):
        if k not in iv_bel:
            iv_bel[k] = iv_hesapla(d[k], y) if k in d.columns else None
        return iv_bel[k]

    def kol_sira(k):
        if k not in sira_bel:
            sira_bel[k] = _sira(d[k])
        return sira_bel[k]

    # Segment: hedefle iliskisi en yuksek olan (dil modeli baskasini secebilir)
    seg_iv = sorted(((kol_iv(sg) or 0.0, sg) for sg in segmentler if sg in d.columns), reverse=True)
    seg = seg_iv[0][1] if seg_iv else None
    cikti = {}
    for no, b in enumerate(birimler):
        en_sira = {}                     # kod -> en iyi kolonun sirasi (kodlar arasi benzerlik)
        eski = onceki.get(b["id"]) or {}
        imza = _imza(b)
        if eski.get("imza") != imza or eski.get("surum") != KATKI_SURUM:
            eski = {}
        kodlar = dict(eski.get("kodlar") or {})
        olculmeyen = dict(eski.get("olculmeyen") or {})
        kaynak = [k for k in b["kolonlar"] if k in d.columns] if b["tur"] != "satir" else []
        kiv = [(kol_iv(k), k) for k in kaynak]
        kiv = [(v, k) for v, k in kiv if v is not None]
        kaynak_iv, kaynak_kolon = (max(kiv) if kiv else (None, None))
        for c in katki_kodlari(b, model_turu):
            if c in kodlar or c in olculmeyen:
                continue
            param = {}
            if c in ("segment", "grup_oran"):
                if not seg:
                    olculmeyen[c] = "segment kolonu yok"
                    continue
                param = {c: {"segment": seg}}
            try:
                yeni, _kayit, hata = uygula(d, [b], {b["id"]: {"sec": [c], "param": param}}, hep, hedef)
            except Exception as e:      # pylint: disable=broad-except
                olculmeyen[c] = str(e)[:80]
                continue
            if not len(d):
                olculmeyen[c] = "eğitim satırı yok"
                continue
            if not yeni:
                olculmeyen[c] = (hata[0] if hata else "kolon üretilmedi")[:120]
                continue
            ivs = [(iv_hesapla(sr, y), ad) for ad, sr in yeni.items()]
            ivs = [(v, a) for v, a in ivs if v is not None]
            if not ivs:
                olculmeyen[c] = "IV hesaplanamadı (kolon boş ya da sabit)"
                continue
            en_iv, en_ad = max(ivs)
            iliski = None
            rs = _sira(yeni[en_ad])
            en_sira[c] = rs
            if kaynak and len(kaynak) <= 40:
                il = [_iliski(rs, kol_sira(k)) for k in kaynak]
                il = [v for v in il if v is not None]
                iliski = max(il) if il else None
            # Kategorik kolon modele ancak kodlanarak girer: artis yerine IV'nin kendisi.
            artis_yok = kaynak_iv is None or b.get("tip") == "kategorik" and b["tur"] == "kolon"
            kodlar[c] = {"iv": round(en_iv, 4), "kolon": en_ad, "kolon_sayisi": len(yeni),
                         "artis": None if artis_yok else round(en_iv - kaynak_iv, 4),
                         "iliski": None if iliski is None else round(iliski, 3),
                         "segment": (param.get(c) or {}).get("segment")}
        # Kodlar arasi benzerlik: ayni pencere ciftinde oran, normalize oran
        # ve buyume ayni siradadir; biri yeter.
        ad_ = list(en_sira)
        for i_, c1 in enumerate(ad_):
            for c2 in ad_[i_ + 1:]:
                v = _iliski(en_sira[c1], en_sira[c2])
                if v is not None and v >= KATKI_ILISKI:
                    kodlar[c1].setdefault("benzer", {})[c2] = round(v, 3)
                    kodlar[c2].setdefault("benzer", {})[c1] = round(v, 3)
        cikti[b["id"]] = {"imza": imza, "surum": KATKI_SURUM,
                          "kaynak_iv": None if kaynak_iv is None else round(kaynak_iv, 4),
                          "kaynak_kolon": kaynak_kolon, "kodlar": kodlar, "olculmeyen": olculmeyen}
        if ilerleme:
            ilerleme(no + 1)
    return cikti


def _iv_yaz(v):
    return "-" if v is None else ("%.3f" % v).replace(".", ",")


def _artis_yaz(v):
    if v is None:
        return "-"
    return ("+" if v >= 0 else "eksi ") + ("%.3f" % abs(v)).replace(".", ",")


def katki_satiri(c, m):
    """Bir kodun olcumu tek cumle (sayilarla)."""
    t = "%s: en iyi kolonun IV'si %s" % (KATALOG_HARITA[c]["ad"], _iv_yaz(m.get("iv")))
    if m.get("artis") is not None:
        t += ", kaynağa göre %s" % _artis_yaz(m["artis"])
    if m.get("iliski") is not None:
        t += ", kaynakla sıra ilişkisi %s" % ("%.2f" % m["iliski"]).replace(".", ",")
    return t


def katki_metni(k, model_turu="agac"):
    """Dil modeline giden olcum ozeti (tek satir)."""
    if not k:
        return ""
    par = ["kaynak kolonların en iyi IV'si %s (%s)" % (_iv_yaz(k.get("kaynak_iv")), k.get("kaynak_kolon") or "-")]
    for c, m in (k.get("kodlar") or {}).items():
        par.append("%s: IV %s, artış %s, ilişki %s%s" % (
            c, _iv_yaz(m.get("iv")), _artis_yaz(m.get("artis")),
            "-" if m.get("iliski") is None else ("%.2f" % m["iliski"]).replace(".", ","),
            (", %s ile aynı sıra" % "/".join(sorted(m["benzer"]))) if m.get("benzer") else ""))
    return "; ".join(par)


def katki_degerli(m):
    """Olcume gore yeni bilgi var mi: IV artisi belirgin ve kaynakla ayni
    sira degil. Kaynak IV'si yoksa (satir duzeyi) IV en az KATKI_ARTIS."""
    if not m or m.get("iv") is None:
        return False
    if m.get("iliski") is not None and m["iliski"] >= KATKI_ILISKI:
        return False
    if m.get("artis") is None:
        return m["iv"] >= KATKI_ARTIS
    return m["artis"] >= KATKI_ARTIS


def katki_gerekcesi(b, k, sec, model_turu):
    """Kodun sayisal gerekcesi: (secilenler, secilmeyenler) cumleleri."""
    if not k:
        return "", ""
    kod = k.get("kodlar") or {}
    bas = "Kaynak kolonların en iyi IV'si %s (%s). " % (_iv_yaz(k.get("kaynak_iv")), k.get("kaynak_kolon") or "-") \
        if k.get("kaynak_iv") is not None else ""
    secilen = [katki_satiri(c, kod[c]) if c not in MONOTON else
               "%s: sıralamayı koruyan dönüşüm (IV aynı, %s); doğrusal modelde değerin ölçeğini düzeltmek için"
               % (KATALOG_HARITA[c]["ad"], _iv_yaz(kod[c].get("iv"))) for c in sec if c in kod]
    secilmeyen = []
    for c in katki_kodlari(b, model_turu):
        if c in sec or c not in kod:
            continue
        m = kod[c]
        if c in MONOTON:
            secilmeyen.append("%s: sıralamayı koruyan dönüşüm, IV kaynakla aynı (%s); doğrusal modelde katkısı "
                              "ölçekle ilgilidir, IV ile ölçülmez" % (KATALOG_HARITA[c]["ad"], _iv_yaz(m.get("iv"))))
            continue
        ben = [x for x in (m.get("benzer") or {}) if x in sec]
        neden = ("seçilen %s ile aynı sıra (ilişki %s), tekrar olur" % (
                    KATALOG_HARITA[ben[0]]["ad"], ("%.2f" % m["benzer"][ben[0]]).replace(".", ","))
                 if ben else
                 "kaynakla neredeyse aynı sıra, yeni bilgi yok" if (m.get("iliski") or 0) >= KATKI_ILISKI
                 else "IV artışı %s'ten az" % _iv_yaz(KATKI_ARTIS) if m.get("artis") is not None
                 and m["artis"] < KATKI_ARTIS else "")
        secilmeyen.append(katki_satiri(c, m) + (" (%s)" % neden if neden else ""))
    s1 = (bas + "; ".join(secilen) + ".") if secilen else (bas.strip() if bas else "")
    s2 = ("; ".join(secilmeyen) + ".") if secilmeyen else ""
    if model_turu == "agac" and b["tur"] == "kolon" and b.get("tip") != "kategorik":
        s2 = (s2 + " " if s2 else "") + ("Log, kırpma, sıra, ölçekleme gibi sıralamayı koruyan dönüşümler "
                                         "aralıkları değiştirmez; IV aynı kalır (%s), ağaçta yeni kolon gereksiz."
                                         % _iv_yaz(k.get("kaynak_iv")))
    return s1.strip(), s2.strip()


def _oneri_imza(b, model_turu):
    """Onerinin gecerli oldugu durum: birim, model turu ve olcum surumu."""
    return _imza(b) + model_turu + "|k%d" % KATKI_SURUM


def katki_eksik(birimler, katki, model_turu):
    """Olcumu eksik ya da eskimis birimler (bu model turunun kodlariyla)."""
    katki = katki or {}
    eksik = []
    for b in birimler:
        k = katki.get(b["id"]) or {}
        if k.get("imza") != _imza(b) or k.get("surum") != KATKI_SURUM:
            eksik.append(b)
            continue
        bilinen = set(k.get("kodlar") or {}) | set(k.get("olculmeyen") or {})
        if any(c not in bilinen for c in katki_kodlari(b, model_turu)):
            eksik.append(b)
    return eksik


def _sayili(metin):
    return bool(re.search(r"\d", str(metin or "")))


# Donusumun uygulandigi birim turu (katalogdaki "nerede" bilgisi).
_YER_GRUP = {"tekli": "Tek kolon ve pencere ailesinin her penceresi", "aile": "Pencere ailesi (en az 2 pencere)",
             "kategorik": "Kategorik tek kolon", "satir": "Satır düzeyi"}
_YER_KOD = {"net": "Gelen ve giden çifti; aileler arası çift", "cift_oran": "Gelen ve giden çifti; aileler arası çift",
            "ort": "Tutar ve adet çifti", "pay": "Alt kırılım ve toplam çifti", "carpim": "Kolon çiftleri",
            "kesisim": "İki az değerli kategorik kolon", "yogunlasma": "Aynı toplamın en az iki alt kırılımı",
            "oran_tum": "Pencere ailesi (en az 3 pencere)", "fark_tum": "Pencere ailesi (en az 3 pencere)",
            "egim": "Pencere ailesi (en az 3 pencere)", "dk": "Pencere ailesi (en az 3 pencere)",
            "ardisik": "Toplanabilir pencere ailesi (en az 3 pencere)",
            "donem": "Toplanabilir pencere ailesi", "donem_pay": "Toplanabilir pencere ailesi",
            "donem_oran": "Toplanabilir pencere ailesi", "en_yogun": "Toplanabilir pencere ailesi",
            "buyume": "Toplanabilir pencere ailesi"}


def kod_yeri(kod):
    return _YER_KOD.get(kod) or _YER_GRUP.get(KATALOG_HARITA[kod]["grup"], "")


# Ayni bilgiyi veren ciftler (her model turunde): normalize oran, oranin sabit
# katidir; "butun ciftler" sıradaki ciftleri de icerir.
TEKRAR_KESIN = [("norm", "oran", "Normalize oran aynı pencere çiftinde Oran'ın sabit bir katıdır (pencere "
                 "uzunluklarının oranı); aynı bilgi."),
                ("oran", "oran_tum", "Oran (bütün pencere çiftleri) sıradaki çiftleri de üretir."),
                ("fark", "fark_tum", "Fark (bütün pencere çiftleri) sıradaki çiftleri de üretir.")]


def tekrar_ele(o, b, k, model_turu):
    """Secimde ayni bilgiyi veren donusumleri ayiklar (kod): kesin olanlar
    her modelde; agacta olcume gore ayni sirada olanlardan IV'si dusuk olan
    da (agac sira kullanir). Doner: (yeni oneri, elenen [{kod, neden}])."""
    sec = list(o.get("sec") or [])
    elenen = []
    for c, ust, neden in TEKRAR_KESIN:
        if c in sec and ust in sec:
            sec.remove(c)
            elenen.append({"kod": c, "neden": neden})
    kod = (k or {}).get("kodlar") or {}
    if model_turu == "agac" and kod:
        for c in sorted([x for x in sec if x in kod], key=lambda x: (kod[x].get("iv") or 0)):
            ust = [x for x in (kod[c].get("benzer") or {}) if x in sec and x != c
                   and (kod.get(x) or {}).get("iv", 0) >= (kod[c].get("iv") or 0)]
            if ust and c in sec:
                sec.remove(c)
                elenen.append({"kod": c, "neden": "%s ile aynı sırada (ilişki %s); ağaç sırayı kullandığı için aynı bilgi."
                               % (KATALOG_HARITA[ust[0]]["ad"], ("%.2f" % kod[c]["benzer"][ust[0]]).replace(".", ","))})
    if not elenen:
        return o, []
    o = dict(o, sec=sec, param={c: v for c, v in (o.get("param") or {}).items() if c in sec})
    o["elenen"] = elenen
    return o, elenen


def olcum_ekle(o, b, k, model_turu):
    """Oneriye kodun sayisal gerekcesini ekler (olcum, olcum_secilmeyen).
    Dil modelinin gerekcesinde sayi yoksa (genel cumle) gosterilmez."""
    o = dict(o)
    if k:
        o["olcum"], o["olcum_secilmeyen"] = katki_gerekcesi(b, k, o.get("sec") or [], model_turu)
    metin = " ".join(str(o.get(a) or "") for a in ("g1", "g2", "g3", "gerekce"))
    o["sayisiz"] = o.get("kaynak") in ("dil modeli", "sohbet") and not _sayili(metin)
    return o


def _imza(b):
    import json as _json
    return _json.dumps([b["kolonlar"], b.get("mumkun"), ozet_metni(b), b.get("aciklama")],
                       ensure_ascii=False, sort_keys=True)


def llm_ogesi(b, model_turu, katki=None):
    k = (katki or {}).get(b["id"])
    return {"id": b["id"], "tur": b["tur"], "ad": b["ad"], "kolonlar": b["kolonlar"],
            "aciklama": b.get("aciklama"), "olcu": b.get("olcu"), "istat": b.get("istat"),
            "ozet": ozet_metni(b), "mumkun": model_mumkun(b, model_turu), "asama": b.get("asama"),
            "ciftler": len(b.get("ciftler") or []), "gerekce": b.get("gerekce") or "",
            "katki": katki_metni(k), "kural": kural_onerisi(b, model_turu, k)["sec"]}


def oneri_onbellek(birimler, onceki=None, model_turu="agac", katki=None):
    """(cikti, sor): onceki dil modeli onerisi (imza ve model turu ayni)
    olan birimler cikti'da; digerleri dil modeline sorulacak (sor)."""
    onceki = onceki or {}
    cikti, sor = {}, []
    for b in birimler:
        o = onceki.get(b["id"]) or {}
        if not model_mumkun(b, model_turu):
            # Bu model turunde secenek yok: dil modeline sorulacak bir sey yok.
            kk = (katki or {}).get(b["id"])
            k = kural_onerisi(b, model_turu)
            o = dict(k, kaynak="secenek yok", imza=_oneri_imza(b, model_turu),
                     gerekce=k.get("gerekce") or SECENEK_YOK)
            cikti[b["id"]] = olcum_ekle(o, b, kk, model_turu)
        elif o.get("kaynak") in ("dil modeli", "sohbet") and o.get("imza") == _oneri_imza(b, model_turu):
            cikti[b["id"]] = o
        else:
            sor.append(b)
    return cikti, sor


SECENEK_YOK = "Bu model türünde bu birimde uygulanabilen dönüşüm yok."


def oneri_birlestir(birimler, cikti, alinan, model_turu, sorulan=None, katki=None):
    """Dil modelinden alinanlar dil modeli kaynakli; sorulup alinamayanlar
    kural (dm_yok: dil modeli cevap vermedi)."""
    sorulan = set(sorulan or [])
    cikti = dict(cikti)
    for b in birimler:
        if b["id"] in cikti and b["id"] not in alinan:
            continue
        o = alinan.get(b["id"])
        kk = (katki or {}).get(b["id"])
        if o is not None:
            o, _el = tekrar_ele(dict(o), b, kk, model_turu)
            cikti[b["id"]] = olcum_ekle(dict(o, kaynak="dil modeli", imza=_oneri_imza(b, model_turu)),
                                        b, kk, model_turu)
        else:
            k = kural_onerisi(b, model_turu, kk)
            cikti[b["id"]] = olcum_ekle(dict(k, kaynak="kural", imza=_oneri_imza(b, model_turu),
                                             dm_yok=b["id"] in sorulan), b, kk, model_turu)
    return cikti


def arasi_imzasi(birimler, model_turu):
    import hashlib
    # Model turune bagli degil: aileler arasi iliskiler veriye ve anlama bagli.
    t = "|".join(sorted(b["id"] for b in birimler if b["tur"] in ("aile", "kolon")))
    return hashlib.sha1(t.encode("utf-8")).hexdigest()[:16]


# ARKA PLAN ISI: butun birimler dil modeline sorulur (parca parca,
# alinamayanlar daha kucuk parcalarla yeniden); ardindan aileler arasi
# oneriler. Kart is bitince acilir; is durumu bellekte tutulur, sunucu
# yeniden baslarsa kart isi yeniden baslatir.
_ISLER = {}
_IS_KILIT = threading.Lock()
IS_SINIRI = 20


def oneri_isi_baslat(birimler, sor, segmentler, model_turu, arasi_sor=True, veri_al=None,
                     katki=None):
    """Arka plan isi: (1) olcumu eksik birimlerde katki olcumu (veri_al():
    (df, egitim maskesi, hedef)), (2) sorulacak birimler dil modeline
    (olcumle), (3) aileler arasi oneriler ve onlarin olcumu."""
    import uuid
    from fe_agent import llm as llm_mod
    kimlik = uuid.uuid4().hex[:12]
    katki = dict(katki or {})
    eksik = katki_eksik(birimler, katki, model_turu) if veri_al else []
    sor = sorted(sor, key=lambda b: b.get("asama") or 3)
    with _IS_KILIT:
        for k in sorted(_ISLER, key=lambda k: _ISLER[k]["zaman"])[:-IS_SINIRI or None]:
            if _ISLER[k]["durum"] != "calisiyor":
                _ISLER.pop(k, None)
        _ISLER[kimlik] = {"durum": "calisiyor", "zaman": time.time(), "biten": 0,
                          "toplam": len(sor), "tur": 1, "evre": "olcum" if eksik else "birim",
                          "olcum_biten": 0, "olcum_toplam": len(eksik), "sonuc": {},
                          "arasi": None, "hata": None, "model_turu": model_turu, "katki": None,
                          "sorulan": [b["id"] for b in sor], "arasi_sor": bool(arasi_sor)}

    def ilerle(biten, tur):
        with _IS_KILIT:
            _ISLER[kimlik].update(biten=biten, tur=tur)

    def olc_ilerle(n):
        with _IS_KILIT:
            _ISLER[kimlik]["olcum_biten"] = n

    def calis():
        hata = None
        veri = None
        try:
            if eksik:
                # Olcum hatasi isi durdurmaz: dil modeli olcumsuz karar verir.
                try:
                    veri = veri_al()
                    bas = time.time()
                    katki.update(katki_olc(veri[0], eksik, veri[1], veri[2], model_turu, segmentler,
                                           katki, olc_ilerle))
                    print("02.2 katkı ölçümü: %d birim, %.0f sn" % (len(eksik), time.time() - bas),
                          flush=True)
                except Exception as e:      # pylint: disable=broad-except
                    print("02.2 katkı ölçümü yapılamadı: %s: %s" % (type(e).__name__, str(e)[:200]),
                          flush=True)
            with _IS_KILIT:
                _ISLER[kimlik].update(evre="birim", katki=dict(katki))
            ogeler = [llm_ogesi(b, model_turu, katki) for b in sor]
            sonuc, hata = llm_mod.geleneksel_oneri_sec(ogeler, katalog_metni(), list(segmentler),
                                                       model_turu=model_turu, ilerleme=ilerle)
            with _IS_KILIT:
                _ISLER[kimlik]["sonuc"] = sonuc
            if arasi_sor:
                with _IS_KILIT:
                    _ISLER[kimlik]["evre"] = "arasi"
                satirlar = [arasi_satiri(b) for b in birimler if b["tur"] in ("aile", "kolon")]
                mevcut = [b["ad"] for b in birimler if b["tur"] in ("cift", "grup")]
                oneriler, h2 = llm_mod.geleneksel_arasi_oner(satirlar, mevcut, model_turu)
                if oneriler and veri_al:
                    try:
                        yeni = arasi_ekle(birimler, oneriler, segmentler)
                        if yeni:
                            veri = veri or veri_al()
                            katki.update(katki_olc(veri[0], yeni, veri[1], veri[2], model_turu,
                                                   segmentler, katki))
                    except Exception as e:      # pylint: disable=broad-except
                        print("02.2 aileler arası ölçüm yapılamadı: %s" % str(e)[:200], flush=True)
                with _IS_KILIT:
                    _ISLER[kimlik].update(arasi=oneriler, katki=dict(katki))
                hata = hata or h2
        except Exception as e:      # pylint: disable=broad-except
            hata = "%s: %s" % (type(e).__name__, str(e)[:200])
            print("02.2 öneri işi hatası: %s" % hata, flush=True)
        with _IS_KILIT:
            _ISLER[kimlik].update(durum="bitti", hata=hata)

    threading.Thread(target=calis, daemon=True).start()
    return kimlik


def oneri_isi_durumu(kimlik):
    with _IS_KILIT:
        d = _ISLER.get(str(kimlik or ""))
        return None if d is None else dict(d)


def arasi_satiri(b):
    oz = b.get("ozet") or {}
    ek = ("pencereler (gün): %s" % ", ".join(str(g) for g in b["gunler"])) if b.get("gunler") \
        else ("%s değer" % oz.get("tekil") if b.get("tip") == "kategorik" else "")
    return "id=%s | %s | %s | ölçü: %s | istatistik: %s | %s | açıklama: %s" % (
        b["id"], b["ad"], "kategorik" if b.get("tip") == "kategorik" else "sayısal",
        b.get("olcu") or "-", b.get("istat") or "-", ek or "-", (b.get("aciklama") or "-")[:90])


def oneri_hesapla(birimler, segmentler, onceki=None, model_turu="agac"):
    """Eszamanli oneri (testler ve arka plan isi olmayan cagrilar):
    {id: {"sec", "param", "gerekce", "g1", "g2", "g3", "secilmeyen",
    "kaynak", "imza"}}."""
    cikti, sor = oneri_onbellek(birimler, onceki, model_turu)
    alinan = {}
    if sor:
        try:
            from fe_agent import llm as llm_mod
            alinan, _h = llm_mod.geleneksel_oneri_sec(
                [llm_ogesi(b, model_turu) for b in sor], katalog_metni(), segmentler,
                model_turu=model_turu)
        except Exception:
            alinan = {}
    return oneri_birlestir(birimler, cikti, alinan, model_turu, [b["id"] for b in sor])


def karar_dogrula(birimler, karar, segmentler, model_turu=None):
    """Gelen karari birimlerin mumkun kodlariyla (model turu verilmisse ona
    gore) suzer."""
    temiz = {}
    for b in birimler:
        k = (karar or {}).get(b["id"])
        if not isinstance(k, dict):
            continue
        mm = model_mumkun(b, model_turu) if model_turu else (b.get("mumkun") or [])
        sec, param = param_temizle([c for c in (k.get("sec") or []) if c in mm], k.get("param"),
                                   segmentler)
        temiz[b["id"]] = {"sec": sec, "param": param}
    return temiz


# ---------------------------------------------------------------------------
# SOHBETTE TOPLU DEGISIKLIK: "uc kirpma istemiyorum" gibi genel istekler
# birim birim degil, kapsamla gelir; kod kapsama uyan butun birimlere
# genisletir. Dil modeli bir sey uretmezse ya da cevabi bos kalirsa kod
# mesajdan niyeti okur (donusum adi + istemiyorum / cikar / ekle gibi).
# ---------------------------------------------------------------------------
_ES_AD = {"winsor": ["uç kırpma", "uc kirpma", "kırpma", "winsor", "winsorize"],
          "log": ["log1p", "logaritma"], "islog": ["işaretli log"], "karekok": ["karekök", "karekok"],
          "kare": ["kare terimi", "polinom"], "yeo": ["yeo-johnson", "yeo johnson", "box-cox"],
          "rank": ["sıra", "rank", "yüzdelik"], "zskor": ["z-skor", "z skor", "zskor", "standartlaştırma"],
          "robust": ["robust"], "isaret": ["işaret"], "sifir": ["sıfır bayrağı"], "esik": ["eşik"],
          "dilim": ["dilim", "eşit frekans"], "kova": ["kova"], "oran": ["ratio"], "fark": ["delta"],
          "norm": ["normalize oran", "normalize"], "buyume": ["büyüme"], "egim": ["eğim", "trend"],
          "dk": ["değişkenlik"], "onehot": ["one-hot", "onehot", "gölge değişken"], "woe": ["woe"],
          "hedef_ort": ["hedef ortalaması", "target encoding"], "frekans": ["frekans"],
          "oran_tum": ["bütün pencere çiftleri", "bütün çiftler"], "donem": ["dönem parçaları"],
          "donem_pay": ["dönem payları"], "donem_oran": ["dönem oranları"], "eksik_sayi": ["eksik sayısı"],
          "yogunlasma": ["yoğunlaşma", "hhi"], "segment": ["segment içi"], "grup_oran": ["segment medyanı"]}
_HAYIR = ("istemiyorum", "istemem", "olmasın", "olmasin", "çıkar", "cikar", "kaldır", "kaldir", "sil",
          "kullanma", "gerek yok", "gereksiz", "yapma", "iptal")
_EVET = ("ekle", "istiyorum", "olsun", "kullan", "uygula", "yap")


def _kucuk(t):
    return str(t or "").replace("I", "ı").replace("İ", "i").lower()


_EK = r"(?:y?[ıiuü]|[ıiuü]n|y?[ae]|d[ae]n|t[ae]n|l[ae]r[ıi]?|s[ıi]n[ıi]?|n[ıi]n|y[ıi]|n[ıi])?"
_HARF = "a-zçğıöşü"


_YAPILDI = re.compile(r"(eklen(di|miştir|mistir)|kaldırıl(dı|mıştır)|çıkarıl(dı|mıştır)|uygulan(dı|mıştır)|"
                      r"silin(di|miştir)|değiştiril(di|miştir)|ekledim|kaldırdım|çıkardım|uyguladım)", re.I)
_ONAY = re.compile(r"^\s*(evet|olur|tamam|tamamdır|kabul|onayla|onaylıyorum|uygula|uygulayalım|ekle|ekleyelim|"
                   r"çıkar|çıkaralım|kaldır|yap|yapalım|katılıyorum|aynen)\b.{0,25}$", re.I | re.S)


def yapildi_der(metin):
    """Cevap bir degisikligin YAPILDIGINI soyluyor mu."""
    return bool(_YAPILDI.search(str(metin or "")))


def eylem_mi(mesaj):
    """Mesaj bir ekleme ya da cikarma istiyor mu."""
    m = _kucuk(mesaj)
    return any(re.search("(?<![%s])%s" % (_HARF, x), m) for x in _HAYIR + _EVET)


def onay_mi(mesaj):
    """Kisa onay mesaji mi ("evet", "ekle bence de")."""
    return bool(_ONAY.match(_kucuk(mesaj)))


def niyet_bul(mesaj, coklu=False):
    """Mesajdan kod ile toplu niyet: [{"islem", "kodlar", "kapsam", "neden"}]
    ya da []. Yalniz TEK bir donusum adi ve acik bir fiil (istemiyorum,
    cikar, ekle gibi) birlikte gecerse; birden cok ad ya da karisik istek
    dil modeline birakilir."""
    m = _kucuk(mesaj)
    eslesme = {}                      # ifade -> ilk kod (katalog sirasi)
    for k, a, _g, _c in KATALOG:
        adlar = [_kucuk(re.sub(r"\s*\(.*?\)", "", a))] + [_kucuk(x) for x in _ES_AD.get(k, [])]
        for x in adlar:
            if len(x) >= 3 and re.search("(?<![%s])%s%s(?![%s])" % (_HARF, re.escape(x), _EK, _HARF), m):
                eslesme.setdefault(x, k)
    # Baska bir eslesen ifadenin parcasi olan ifade sayilmaz ("oran" ve "normalize oran").
    ifadeler = [x for x in eslesme if not any(x != y and x in y for y in eslesme)]
    kodlar = list(dict.fromkeys(eslesme[x] for x in ifadeler))
    if not kodlar or (len(kodlar) != 1 and not coklu):
        return []
    hayir = any(re.search("(?<![%s])%s" % (_HARF, x), m) for x in _HAYIR)
    evet = any(re.search("(?<![%s])%s" % (_HARF, x), m) for x in _EVET)
    if hayir == evet:
        return []
    return [{"islem": "cikar" if hayir else "ekle", "kodlar": kodlar, "kapsam": {}, "param": {},
             "neden": "Mesajınızdan okundu."}]


def toplu_genislet(birimler, karar, toplu, model_turu, segmentler=()):
    """Toplu kayitlari birim degisikliklerine cevirir. Doner: [{"toplu":
    True, "ids", "ekle", "cikar", "param", "neden", "kapsam_metni",
    "atlanan"}]; yalniz etkisi olan birimler."""
    cikti = []
    for t in toplu or []:
        kap = t.get("kapsam") or {}
        turler = set(kap.get("tur") or [])
        asamalar = {int(x) for x in (kap.get("asama") or []) if str(x).isdigit()}
        ad = _kucuk(kap.get("ad") or "")
        tip = kap.get("tip")
        ids, atlanan = [], 0
        for b in birimler:
            if turler and b["tur"] not in turler:
                continue
            if asamalar and (b.get("asama") or birim_asamasi(b)) not in asamalar:
                continue
            if ad and ad not in _kucuk(b["ad"]) and not any(ad in _kucuk(k) for k in b["kolonlar"]):
                continue
            if tip and b.get("tip") != tip:
                continue
            sec = set(((karar or {}).get(b["id"]) or {}).get("sec") or [])
            mm = set(model_mumkun(b, model_turu))
            if t["islem"] == "cikar":
                if sec & set(t["kodlar"]):
                    ids.append(b["id"])
            else:
                ekle_ = [c for c in t["kodlar"] if c in mm and c not in sec]
                ekle_, _p = param_temizle(ekle_, t.get("param"), segmentler)
                if ekle_:
                    ids.append(b["id"])
                elif any(c in (b.get("mumkun") or []) and c not in mm for c in t["kodlar"]):
                    atlanan += 1             # birimde olur ama bu model turunde gereksiz
        if not ids and not atlanan:
            continue
        ks = []
        if turler and turler < set(_TUR_ADI):
            ks.append(", ".join(_TUR_ADI[x] for x in sorted(turler) if x in _TUR_ADI))
        if asamalar and asamalar < {1, 2, 3}:
            ks.append("%s. aşama" % " ve ".join(str(x) for x in sorted(asamalar)))
        if ad:
            ks.append("adında «%s»" % kap.get("ad"))
        if tip:
            ks.append(tip)
        cikti.append({"toplu": True, "ids": ids, "ekle": t["kodlar"] if t["islem"] == "ekle" else [],
                      "cikar": t["kodlar"] if t["islem"] == "cikar" else [],
                      "param": t.get("param") or {}, "neden": t.get("neden") or "",
                      "kapsam_metni": ", ".join(ks) or "bütün birimler", "atlanan": atlanan})
    return cikti


_TUR_ADI = {"kolon": "tek kolonlar", "aile": "pencere aileleri", "cift": "kolon çiftleri",
            "grup": "kolon grupları", "satir": "satır düzeyi"}


def _ort(v):
    return sum(v) / len(v) if v else None


def katki_etkisi(d, katki):
    """Toplu degisikligin olcume gore etkisi (tek cumle, sayilarla)."""
    katki = katki or {}
    kodlar = d.get("cikar") or d.get("ekle") or []
    if kodlar and all(c in MONOTON for c in kodlar):
        return ("%s sıralamayı korur: IV'yi değiştirmez, ölçüm bu yüzden katkısını gösteremez. Doğrusal "
                "modelde işi ölçeği düzeltmektir (uç değerin ya da çarpıklığın katsayıyı bozmasını önler); "
                "çıkarınca bu koruma kalkar, ağaç modelinde zaten gerekmez."
                % ", ".join(KATALOG_HARITA[c]["ad"] for c in kodlar))
    deg, art = [], []
    for i in d.get("ids") or []:
        for c in kodlar:
            m = ((katki.get(i) or {}).get("kodlar") or {}).get(c)
            if not m:
                continue
            if m.get("artis") is not None:
                art.append((m["artis"], i))
            if katki_degerli(m):
                deg.append((m.get("artis") if m.get("artis") is not None else m.get("iv") or 0, i))
    if not art and not deg:
        return "Bu birimlerde bu dönüşüm ölçülmedi."
    olculen = len({i for _a, i in art}) or len({i for _a, i in deg})
    t = "Ölçüm (eğitim satırları): %s birimde ölçüldü" % olculen
    if art:
        en = max(art)
        t += ", kaynağa göre IV artışı ortalama %s, en çok %s" % (_artis_yaz(_ort([a for a, _i in art])),
                                                                 _artis_yaz(en[0]))
    if d.get("cikar"):
        if deg:
            t += ". Dikkat: %s birimde ölçüme göre yeni bilgi taşıyor (en çok %s); çıkarınca bu bilgi kaybolur." % (
                len(deg), _artis_yaz(max(deg)[0]))
        else:
            t += ". Hiçbir birimde ölçüme göre yeni bilgi taşımıyor; çıkarmak bilgi kaybettirmez."
    else:
        t += ". %s birimde ölçüme göre yeni bilgi taşıyor." % len(deg) if deg else \
            ". Hiçbir birimde belirgin katkı ölçülmedi; eklemek kolon sayısını artırır."
    return t


def katki_tara(birimler, karar, katki, model_turu, segmentler=(), yon="ekle", sapma=None):
    """Olcume gore toplu oneriler, donusum basina bir kayit.
    yon "ekle": secili olmayan ama yeni bilgi tasiyan (secili bir
    donusumle ayni sirada olmayan) kodlar. yon "cikar": secili ama olcume
    gore yeni bilgi tasimayan ya da secili baska bir donusumle ayni sirada
    olan (IV'si dusuk olan) kodlar."""
    katki = katki or {}
    grup = {}
    for b in birimler:
        k = (katki.get(b["id"]) or {}).get("kodlar") or {}
        if not k:
            continue
        sec = list(((karar or {}).get(b["id"]) or {}).get("sec") or [])
        mm = set(katki_kodlari(b, model_turu)) - set(MONOTON)
        if yon == "ekle":
            # Kullanicinin bu birimden cikardigi donusum yeniden onerilmez.
            cikan = set(((sapma or {}).get(b["id"]) or {}).get("cikar") or [])
            adaylar = sorted([c for c in mm if c not in sec and c not in cikan and katki_degerli(k.get(c))],
                             key=lambda c: -(k[c].get("iv") or 0))
            tut = [c for c in sec if c in k]
            for c in adaylar:
                if any(x in (k[c].get("benzer") or {}) for x in tut):
                    continue                     # secili biriyle ayni bilgi
                tut.append(c)
                grup.setdefault(c, []).append((b["id"], k[c]))
        else:
            for c in sec:
                m = k.get(c)
                if not m or c in MONOTON:
                    continue
                ust = [x for x in (m.get("benzer") or {}) if x in sec and (k.get(x) or {}).get("iv", 0) > m.get("iv", 0)]
                if ust or not katki_degerli(m):
                    grup.setdefault(c, []).append((b["id"], m))
    cikti = []
    for c, lst in sorted(grup.items(), key=lambda x: -len(x[1])):
        art = [m.get("artis") for _i, m in lst if m.get("artis") is not None]
        ivs = [m.get("iv") for _i, m in lst if m.get("iv") is not None]
        if yon == "ekle":
            neden = "Ölçüme göre yeni bilgi: IV artışı ortalama %s, en çok %s." % (
                _artis_yaz(_ort(art)), _artis_yaz(max(art))) if art else \
                "Ölçüme göre hedefle ilişkili: IV ortalama %s." % _iv_yaz(_ort(ivs))
        else:
            neden = "Ölçüme göre yeni bilgi yok ya da seçili başka bir dönüşümle aynı sırada: IV artışı ortalama %s." % (
                _artis_yaz(_ort(art)) if art else "-")
        cikti.append({"toplu": True, "ids": [i for i, _m in lst], "ekle": [c] if yon == "ekle" else [],
                      "cikar": [c] if yon != "ekle" else [], "param": {}, "neden": neden,
                      "kapsam_metni": "ölçüme göre seçilen birimler", "atlanan": 0})
    return cikti


_TARA_EKLE = ("değer kat", "deger kat", "katkı", "katki", "fayda", "iyileştir", "ekstra", "eksik kal",
              "işe yarayan", "bilgi taşıyan", "bilgi katan")
_TARA_CIKAR = ("değer katmayan", "katkısız", "gereksiz", "işe yaramayan", "bilgi katmayan", "tekrar eden",
               "aynı bilgi")


def analiz_niyeti(mesaj):
    """Olcume dayali tarama istegi: "ekle" (deger katanlari ekle), "cikar"
    (deger katmayanlari cikar) ya da None."""
    m = _kucuk(mesaj)
    if any(x in m for x in _TARA_CIKAR) and any(x in m for x in ("çıkar", "kaldır", "ele", "temizle", "sil")):
        return "cikar"
    if any(x in m for x in _TARA_EKLE) and any(x in m for x in ("ekle", "bak", "var mı", "öner", "bul", "neler")):
        return "ekle"
    return None


def toplu_cevap(degisiklikler, katki=None):
    """Dil modelinin cevabi yoksa degisikliklerden kisa cevap."""
    par = []
    for d in degisiklikler:
        adlar = ", ".join(KATALOG_HARITA[c]["ad"] for c in (d.get("cikar") or d.get("ekle") or []))
        if not d.get("toplu"):
            continue
        atla = ("%s birimde bu model türünde gereksiz olduğu için eklenmez" % d["atlanan"]) \
            if d.get("atlanan") else ""
        if not d["ids"]:
            par.append("%s hiçbir birime eklenemiyor: %s." % (adlar, atla or "uygun birim yok"))
            continue
        par.append("Öneri: %s %s %s (%s)%s. %s" % (
            adlar, "%s birimden" % len(d["ids"]) if d.get("cikar") else "%s birime" % len(d["ids"]),
            "çıkarılsın" if d.get("cikar") else "eklensin", d["kapsam_metni"], ("; " + atla) if atla else "",
            katki_etkisi(d, katki) if katki is not None else ""))
    if not par:
        return ""
    yap = any(d.get("toplu") and d["ids"] for d in degisiklikler)
    return "\n".join(p_.strip() for p_ in par) + (
        "\nPlan henüz değişmedi; Uygula'ya basınca sola aktarılır." if yap else "")


def plan_satirlari(birimler, karar, model_turu="agac", mesaj="", en_cok=900, katki=None):
    """Sohbet icin plan: butun birimler kisa (id | ad | secili); mesajda
    adi ya da kolonu gecen birimler ayrintili (aciklama, sayilar, mumkun)."""
    m = str(mesaj or "").upper()
    tok = set(re.findall(r"[A-Z0-9_]{3,}", m))
    satirlar, ayrinti = [], []
    for b in birimler[:en_cok]:
        k = (karar or {}).get(b["id"]) or {}
        satirlar.append("%s | %s | seçili: %s" % (b["id"], b["ad"], ", ".join(k.get("sec") or []) or "yok"))
        if b["ad"].upper() in m or any(x.upper() in tok for x in b["kolonlar"][:40]) \
                or any(t in b["ad"].upper() for t in tok if len(t) >= 5):
            if len(ayrinti) < 40:
                ayrinti.append("%s | %s | açıklama: %s | sayılar: %s | mümkün: %s | ölçüm: %s" % (
                    b["id"], b["ad"], (b.get("aciklama") or "")[:120], ozet_metni(b),
                    ", ".join(model_mumkun(b, model_turu)),
                    katki_metni((katki or {}).get(b["id"])) or "yok"))
    if len(birimler) > en_cok:
        satirlar.append("(+%d birim daha)" % (len(birimler) - en_cok))
    return satirlar, ayrinti


def kolon_sayisi(b, sec):
    """Birimde secilen donusumlerin uretecegi kolon sayisi (tahmin)."""
    n = len(b["kolonlar"])
    t = 0
    for c in sec or []:
        g = KATALOG_HARITA[c]["grup"]
        if b["tur"] == "satir":
            t += 2
        elif c == "yogunlasma":
            t += 2 * len(b.get("gruplar") or [1])
        elif g == "cift":
            t += len(b.get("ciftler") or [1])
        elif c in ("oran", "fark", "norm", "buyume"):
            t += n - 1
        elif c in ("egim", "dk", "ardisik", "en_yogun"):
            t += 1
        elif c in ("oran_tum", "fark_tum"):
            t += n * (n - 1) // 2
        elif c in ("donem", "donem_oran"):
            t += n - 1
        elif c == "donem_pay":
            t += n
        elif c == "onehot":
            t += min((b.get("ozet") or {}).get("tekil") or 0, ONEHOT_EN_COK)
        elif c == "segment":
            t += 2 * n
        elif c == "grup_oran":
            t += n
        else:
            t += n
    return t
