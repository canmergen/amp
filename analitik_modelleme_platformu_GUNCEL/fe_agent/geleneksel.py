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
    ("yeo", "Yeo-Johnson", "tekli", "Dağılımı normale yaklaştırır; parametre eğitim satırlarından."),
    ("winsor", "Uç kırpma (%1, %99)", "tekli", "Uçlar eğitim satırlarının %1 ve %99'luk değerlerine çekilir."),
    ("rank", "Sıra (yüzdelik)", "tekli", "Değerin eğitim dağılımındaki yüzdeliği (0 ile 1 arası)."),
    ("zskor", "Z-skor", "tekli", "(değer eksi ortalama) bölü standart sapma; eğitim satırlarından."),
    ("robust", "Robust ölçek", "tekli", "(değer eksi medyan) bölü çeyrekler arası açıklık; eğitim satırlarından."),
    ("isaret", "İşaret (eksi 1, 0, 1)", "tekli", "Değerin negatif, sıfır ya da pozitif olması."),
    ("sifir", "Sıfır bayrağı", "tekli", "Değer sıfırsa 1, değilse 0 (hiç işlem yok ile az işlem ayrımı)."),
    ("esik", "Eşik bayrağı", "tekli", "Değer verilen eşiğin üstündeyse (ya da altındaysa) 1."),
    ("dilim", "Eşit frekans dilimi", "tekli", "Eğitim satırlarının 10'luk dilimlerine göre dilim numarası."),
    ("segment", "Segment içi yüzdelik ve sapma", "tekli",
     "Değerin kendi segmenti içindeki yüzdeliği ve z-skoru; segment kolonu seçilir."),
    # Pencere ailesi (mevcut: oran, fark)
    ("oran", "Oran (kısa / uzun pencere)", "aile", "Art arda iki pencerenin oranı; 1'den büyükse son dönemde artış."),
    ("fark", "Fark (kısa eksi uzun pencere)", "aile", "Art arda iki pencerenin farkı."),
    ("norm", "Normalize oran", "aile",
     "Pencerelerin günlük ortalamalarının oranı; pencere uzunluğu farkını giderir."),
    ("buyume", "Büyüme oranı", "aile",
     "Kısa pencerenin, uzun pencerenin geri kalanındaki aynı uzunluktaki döneme göre büyümesi."),
    ("egim", "Eğim", "aile", "Günlük ortalamanın pencere uzunluğuna göre eğimi (en az 3 pencere)."),
    ("dk", "Değişkenlik katsayısı", "aile",
     "Pencerelerin günlük ortalamalarının std / ortalaması (en az 3 pencere)."),
    # Kolon ciftleri
    ("net", "Net (fark)", "cift", "İki kolonun farkı (gelen eksi giden gibi)."),
    ("cift_oran", "Oran", "cift", "İki kolonun oranı (gelen / giden gibi)."),
    ("ort", "Ortalama tutar (tutar / adet)", "cift", "Tutarın adede bölümü."),
    ("pay", "Pay (alt kırılım / toplam)", "cift", "Alt kırılımın toplam içindeki payı."),
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
    "oran": ("Art arda iki pencerenin oranı (kısa / uzun).",
             "Son 7 gün 300, son 30 gün 600 iken 0,5: harcamanın yarısı son haftada.",
             "Son dönemdeki hızlanma ya da yavaşlama."),
    "fark": ("Art arda iki pencerenin farkı (kısa eksi uzun).", "Son 30 gün eksi son 90 gün.",
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
}

# AGAC MODELI: platformun modeli HistGradientBoosting (bkz. model.py). Ağaç
# modeller tek kolonun monoton dönüşümünden etkilenmez (aynı bölünmeyi ham
# kolonla bulur); eşik ve işaret bayraklarını da kendisi bulur. Bu
# dönüşümler ağaç modelinde gereksizdir; doğrusal modelde işe yarar.
AGAC_GEREKSIZ = ("log", "islog", "karekok", "yeo", "winsor", "rank", "zskor", "robust",
                 "dilim", "isaret", "sifir", "esik")
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


def birimleri_kur(durum, df, haric=()):
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
    # Satir duzeyi
    bosu_olan = [k for k in sayisal + kategorik if ozet[k]["bos_pay"] > 0]
    if bosu_olan:
        birimler.append({"id": "satir", "tur": "satir", "kolonlar": sayisal + kategorik,
                         "ad": "Satır düzeyi", "tip": "satir", "bosu_olan": len(bosu_olan)})
    for b in birimler:
        k0 = b["kolonlar"][0]
        b["aciklama"] = str(aciklama.get(k0) or "")
        b["olcu"] = str(olcu.get(k0) or "")
        b["istat"] = _istat(k0, istat)
        b["ozet"] = _birim_ozeti(b, ozet)
        b["mumkun"], b["imkansiz"] = uygunluk(b, hedef_ikili, segmentler)
    return birimler, [{"neden": n, "kolonlar": k} for n, k in girmeyen.items()], segmentler


def _birim_ozeti(b, ozet):
    oz = [ozet.get(k) or {} for k in b["kolonlar"] if b["tur"] != "satir"]
    if b["tur"] == "satir":
        return {"kolon": len(b["kolonlar"]), "bosu_olan": b.get("bosu_olan", 0)}
    if b["tip"] == "kategorik":
        return dict(oz[0])
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
    if b["tur"] == "cift":
        t = b.get("cift")
        ekle("net", t == "yon", "Yalnız gelen ile giden gibi yön çiftinde.")
        ekle("cift_oran", t == "yon", "Yalnız gelen ile giden gibi yön çiftinde.")
        ekle("ort", t == "ort", "Yalnız tutar ile adet çiftinde.")
        ekle("pay", t == "pay", "Yalnız alt kırılım ile toplam çiftinde.")
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
    ekle("segment", bool(segmentler), "Segment olarak kullanılabilecek az değerli kategorik kolon yok.")
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
    return mumkun, imkansiz


# ---------------------------------------------------------------------------
# KURAL ONERISI (dil modeline ulasilamazsa)
# ---------------------------------------------------------------------------
def kural_onerisi(b, model_turu="agac"):
    """{"sec", "param", "gerekce", "secilmeyen"}: veriye bakan varsayilan."""
    oz = b.get("ozet") or {}
    mm = set(model_mumkun(b, model_turu))
    sec, neden = [], []
    if b["tur"] == "satir":
        return {"sec": ["eksik_sayi"], "param": {}, "secilmeyen": "",
                "gerekce": "%s kolonda boş hücre var; satırdaki eksik sayısı eksik bilgi profilini taşır."
                % oz.get("bosu_olan", 0)}
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
        sec += ["oran", "norm"]
        neden.append("aynı ölçünün %s penceresi: kısa / uzun oran ve günlük ortalama oranı"
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
    if b["tur"] == "cift":
        for a, c in (b.get("ciftler") or [kol[:2]]):
            xa, xc = _sayi(df[a]), _sayi(df[c])
            if kod == "net":
                koy("%s__MINUS__%s" % (a, c), xa - xc, kod, b, [a, c],
                    _kodla("%s__MINUS__%s" % (a, c), '_s(df, "%s") - _s(df, "%s")' % (a, c)),
                    "%s eksi %s (net akış)." % (a, c))
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


def _imza(b):
    import json as _json
    return _json.dumps([b["kolonlar"], b.get("mumkun"), ozet_metni(b), b.get("aciklama")],
                       ensure_ascii=False, sort_keys=True)


def oneri_hesapla(birimler, segmentler, onceki=None, model_turu="agac"):
    """{id: {"sec", "param", "gerekce", "secilmeyen", "kaynak", "imza"}}.
    Ayni birim icin onceki dil modeli onerisi (imza ayni) tekrar sorulmaz;
    alinamayan birimde kural onerisi."""
    onceki = onceki or {}
    cikti, sor = {}, []
    for b in birimler:
        o = onceki.get(b["id"]) or {}
        if o.get("kaynak") == "dil modeli" and o.get("imza") == _imza(b) + model_turu:
            cikti[b["id"]] = o
        else:
            sor.append(b)
    alinan = {}
    if sor:
        try:
            from fe_agent import llm as llm_mod
            alinan, _h = llm_mod.geleneksel_oneri_sec(
                [{"id": b["id"], "tur": b["tur"], "ad": b["ad"], "kolonlar": b["kolonlar"],
                  "aciklama": b.get("aciklama"), "olcu": b.get("olcu"), "istat": b.get("istat"),
                  "ozet": ozet_metni(b), "mumkun": model_mumkun(b, model_turu),
                  "ciftler": len(b.get("ciftler") or []),
                  "kural": kural_onerisi(b, model_turu)["sec"]} for b in sor],
                katalog_metni(), segmentler, model_turu=model_turu)
        except Exception:
            alinan = {}
    for b in sor:
        o = alinan.get(b["id"])
        if o is not None:
            cikti[b["id"]] = dict(o, kaynak="dil modeli", imza=_imza(b) + model_turu)
        else:
            k = kural_onerisi(b, model_turu)
            cikti[b["id"]] = dict(k, kaynak="kural", imza=_imza(b) + model_turu)
    return cikti


def karar_dogrula(birimler, karar, segmentler, model_turu=None):
    """Gelen karari birimlerin mumkun kodlariyla (model turu verilmisse ona
    gore) suzer."""
    temiz = {}
    for b in birimler:
        k = (karar or {}).get(b["id"])
        if not isinstance(k, dict):
            continue
        mm = model_mumkun(b, model_turu) if model_turu else (b.get("mumkun") or [])
        sec = [c for c in (k.get("sec") or []) if c in mm]
        param = k.get("param") if isinstance(k.get("param"), dict) else {}
        param = {c: v for c, v in param.items() if c in sec and isinstance(v, dict)}
        if "segment" in sec and str((param.get("segment") or {}).get("segment")) not in segmentler:
            sec.remove("segment")
        if "esik" in sec:
            try:
                float(str((param.get("esik") or {}).get("esik")).replace(",", "."))
            except (TypeError, ValueError):
                sec.remove("esik")
        temiz[b["id"]] = {"sec": list(dict.fromkeys(sec)), "param": param}
    return temiz


def plan_satirlari(birimler, karar, model_turu="agac", mesaj="", en_cok=900):
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
                ayrinti.append("%s | %s | açıklama: %s | sayılar: %s | mümkün: %s" % (
                    b["id"], b["ad"], (b.get("aciklama") or "")[:120], ozet_metni(b),
                    ", ".join(model_mumkun(b, model_turu))))
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
        elif g == "cift":
            t += len(b.get("ciftler") or [1])
        elif c in ("oran", "fark", "norm", "buyume"):
            t += n - 1
        elif c in ("egim", "dk"):
            t += 1
        elif c == "onehot":
            t += min((b.get("ozet") or {}).get("tekil") or 0, ONEHOT_EN_COK)
        elif c == "segment":
            t += 2 * n
        else:
            t += n
    return t
