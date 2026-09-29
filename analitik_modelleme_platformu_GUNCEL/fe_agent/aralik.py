# -*- coding: utf-8 -*-
"""fe_agent/aralik.py - HEDEFE GORE ARALIK (BINLEME) ONERISI.  (SFA'nin parcasi)

AMAC (kullanici karari): degiskenin degerlerini duzeltmek DEGIL, hedef
oranina bakarak daha iyi bir model yapisi onermek. Ornek: yas 18-35 %2,35,
35-40 %2,20, 40+ %1,90 -> "batma orani yasla azaliyor, uc araliga bolunsun".
Hassas degiskenlerde (yas, cinsiyet ...) ham kullanim yerine kaba aralik ya
da modelden cikarma onerilir.

KURALLAR (kullanici karari)
  - Egilim: artan, azalan, U (ortada dusuk, uclarda yuksek) ya da ters U.
    U ancak tek yonlu egilimden belirgin daha fazla bilgi tasiyorsa
    (IV en az %10 fazla) secilir.
  - Her aralikta egitim satirlarinin en az %5'i.
  - Komsu araliklarin oranlari istatistiksel olarak farkli olmali
    (iki oran z-testi, p <= 0,05); degilse birlestirilir. En fazla 8 aralik.
  - Sizinti: araliklar ve oranlar YALNIZCA EGITIM satirlarindan ogrenilir.
    Dogrulama / test setlerinde yalnizca egilimin ayni sirada kalip
    kalmadigi KONTROL edilir (karar icin kullanilmaz).

EKSIK DEGER IKI GORUNUMDE (kullanici karari: "null imp önce sonra")
  ayri    : eksikler kendi araliginda (doldurmadan once).
  dolu    : eksikler egitim medyaniyla doldurulmus; medyanin dustugu
            araliga eklenir (SFA'nin uyguladigi doldurma).
  Eksiklerin orani medyan araligindan belirgin farkliysa bu ayrica yazilir:
  medyanla doldurmak bu farki gizler.

HESAP SAYIM TABLOLARI UZERINDEN: ince araliklarda (en fazla 20) satir ve
hedef sayisi bir kez cikarilir, butun birlestirme bu kucuk tabloda yapilir.
Sayimi ureten taraf pandas (bu dosya) ya da ileride Spark olabilir; karar
kodu ayni kalir.
"""

import math
import re

import numpy as np
import pandas as pd

MIN_PAY = 0.05
INCE_ARALIK = 20
EN_COK_ARALIK = 8
ANLAM_P = 0.05
U_KAZANC = 0.10
LAPLACE = 0.5
KATEGORIK_MAX = 200
TUTARLILIK_ESIK = 0.8
# Araliklarin (eksikler haric) IV'si bunun altindaysa oneri verilmez:
# bilinen "tahmin gucu yok" esigi. Cok sayida karsilastirma yapildigi icin
# gurultu kolonunda da sans eseri "anlamli" iki aralik cikabiliyor.
IV_MIN = 0.02
EKSIK_FARK = 0.30          # eksik orani medyan araligindan %30'dan fazla farkliysa not

# Hassas degisken: adinda ya da sozluk aciklamasinda bu kokler gecerse
HASSAS_KOKLER = {
    "yaş": ("YAS", "AGE", "DOGUM", "BIRTH", "YAŞ", "DOĞUM"),
    "cinsiyet": ("CINSIYET", "CİNSİYET", "GENDER", "SEX"),
    "uyruk": ("UYRUK", "NATIONALITY", "VATANDAS", "VATANDAŞ", "ULKE_DOGUM"),
    "medeni hâl": ("MEDENI", "MEDENİ", "MARITAL"),
    "din": ("DIN", "DİN", "RELIGION", "MEZHEP"),
    "etnik köken": ("ETNIK", "ETNİK", "IRK", "RACE", "ETHNIC"),
    "engellilik": ("ENGELLI", "ENGELLİ", "DISABILITY"),
    "sağlık": ("SAGLIK", "SAĞLIK", "HEALTH"),
}


# ===========================================================================
# YARDIMCILAR
# ===========================================================================
def _oran(b):
    return float(b["kotu"]) / b["n"] if b["n"] else 0.0


def _birlestir(a, b):
    c = dict(a)
    c["n"] = a["n"] + b["n"]
    c["kotu"] = a["kotu"] + b["kotu"]
    c["min"] = a["min"] if a.get("min") is not None else b.get("min")
    c["max"] = b["max"] if b.get("max") is not None else a.get("max")
    c["ust"] = b.get("ust")
    c["degerler"] = (a.get("degerler") or []) + (b.get("degerler") or [])
    return c


def iv_hesapla(araliklar):
    """IV (sfa._iv_gruplu ile ayni Laplace duzeltmesi)."""
    kotu_t = sum(b["kotu"] for b in araliklar)
    iyi_t = sum(b["n"] - b["kotu"] for b in araliklar)
    if not kotu_t or not iyi_t or not araliklar:
        return None
    k = len(araliklar)
    kp, ip = kotu_t + LAPLACE * k, iyi_t + LAPLACE * k
    iv = 0.0
    for b in araliklar:
        pk = (b["kotu"] + LAPLACE) / kp
        pi = (b["n"] - b["kotu"] + LAPLACE) / ip
        iv += (pk - pi) * math.log(pk / pi)
    return iv


def _woe(b, kotu_t, iyi_t, k):
    pk = (b["kotu"] + LAPLACE) / (kotu_t + LAPLACE * k)
    pi = (b["n"] - b["kotu"] + LAPLACE) / (iyi_t + LAPLACE * k)
    return math.log(pk / pi)


def _p_degeri(a, b):
    """Iki oranin farki icin iki yonlu z-testi p degeri."""
    n1, n2 = a["n"], b["n"]
    if not n1 or not n2:
        return 1.0
    p = float(a["kotu"] + b["kotu"]) / (n1 + n2)
    if p <= 0 or p >= 1:
        return 1.0
    se = math.sqrt(p * (1 - p) * (1.0 / n1 + 1.0 / n2))
    if se == 0:
        return 1.0
    z = abs(_oran(a) - _oran(b)) / se
    return math.erfc(z / math.sqrt(2))


# ===========================================================================
# BIRLESTIRME
# ===========================================================================
def _pav(araliklar, artan):
    """Havuzlama (Pool Adjacent Violators): oran sirasini bozan komsular
    birlestirilir; sonuc tek yonludur."""
    yigin = []
    for b in araliklar:
        yigin.append(dict(b))
        while len(yigin) >= 2:
            o1, o2 = _oran(yigin[-2]), _oran(yigin[-1])
            if (artan and o1 > o2) or (not artan and o1 < o2):
                son = yigin.pop()
                yigin[-1] = _birlestir(yigin[-1], son)
            else:
                break
    return yigin


def _min_pay(araliklar, toplam):
    """Egitim satirlarinin MIN_PAY'inden kucuk aralik, orani en yakin
    komsusuyla birlestirilir."""
    ar = [dict(b) for b in araliklar]
    esik = MIN_PAY * toplam
    while len(ar) > 1:
        kucuk = [i for i, b in enumerate(ar) if b["n"] < esik]
        if not kucuk:
            break
        i = min(kucuk, key=lambda j: ar[j]["n"])
        adaylar = [j for j in (i - 1, i + 1) if 0 <= j < len(ar)]
        j = min(adaylar, key=lambda j: abs(_oran(ar[j]) - _oran(ar[i])))
        a, b = sorted((i, j))
        ar[a:b + 1] = [_birlestir(ar[a], ar[b])]
    return ar


def _anlamli(araliklar):
    """Orani birbirinden anlamli farkli olmayan komsular birlestirilir;
    aralik sayisi EN_COK_ARALIK'i gecmez."""
    ar = [dict(b) for b in araliklar]
    while len(ar) > 1:
        p = [_p_degeri(ar[i], ar[i + 1]) for i in range(len(ar) - 1)]
        i = int(np.argmax(p))
        if p[i] > ANLAM_P or len(ar) > EN_COK_ARALIK:
            ar[i:i + 2] = [_birlestir(ar[i], ar[i + 1])]
        else:
            break
    return ar


def _sekil(araliklar):
    """Birlestirilmis araliklarin oran sekli."""
    o = [_oran(b) for b in araliklar]
    if len(o) < 2:
        return "düz"
    fark = np.sign(np.diff(o))
    fark = fark[fark != 0]
    if not len(fark):
        return "düz"
    if (fark > 0).all():
        return "artan"
    if (fark < 0).all():
        return "azalan"
    degisim = int((np.diff(fark) != 0).sum())
    if degisim == 1:
        return "U" if fark[0] < 0 else "ters U"
    return "düzensiz"


def _son_adim(ar, toplam):
    return _anlamli(_min_pay(ar, toplam))


def en_iyi_araliklar(ince, toplam):
    """ince: sirali ince araliklar (n, kotu, min, max, ust). Doner:
    (araliklar, sekil). Tek yonlu adaylar ve U / ters U adaylari denenir."""
    adaylar = []
    for artan in (True, False):
        ar = _son_adim(_pav(ince, artan), toplam)
        adaylar.append((iv_hesapla(ar) or 0.0, ar, "tek"))
    tek_iv = max(a[0] for a in adaylar)
    en_iyi_u = None
    for k in range(1, len(ince)):
        for sol_artan in (False, True):
            ar = _pav(ince[:k], sol_artan) + _pav(ince[k:], not sol_artan)
            ar = _son_adim(ar, toplam)
            if _sekil(ar) not in ("U", "ters U"):
                continue
            iv = iv_hesapla(ar) or 0.0
            if en_iyi_u is None or iv > en_iyi_u[0]:
                en_iyi_u = (iv, ar, "u")
    secilen = max(adaylar, key=lambda a: a[0])
    if en_iyi_u and en_iyi_u[0] >= tek_iv * (1 + U_KAZANC) and len(en_iyi_u[1]) >= 3:
        secilen = en_iyi_u
    ar = secilen[1]
    return ar, _sekil(ar)


# ===========================================================================
# INCE ARALIKLAR (pandas)
# ===========================================================================
def _ince_sayisal(x, y):
    """x, y: egitim satirlari, x dolu. Doner: ince araliklar (sirali)."""
    x = pd.to_numeric(x, errors="coerce")
    tekil = np.unique(x.to_numpy())
    if len(tekil) <= INCE_ARALIK:
        kesimler = tekil[:-1]
    else:
        kesimler = np.unique(np.nanpercentile(x, np.linspace(0, 100, INCE_ARALIK + 1))[1:-1])
    kutu = np.searchsorted(kesimler, x.to_numpy(), side="left")
    tablo = pd.DataFrame({"k": kutu, "x": x.to_numpy(), "y": y.to_numpy()})
    g = tablo.groupby("k").agg(n=("y", "size"), kotu=("y", "sum"),
                               mn=("x", "min"), mx=("x", "max"))
    ince = []
    for k, r in g.iterrows():
        ust = float(kesimler[k]) if k < len(kesimler) else None
        ince.append({"n": int(r["n"]), "kotu": int(r["kotu"]),
                     "min": float(r["mn"]), "max": float(r["mx"]), "ust": ust})
    return ince


def _ince_kategorik(x, y):
    """Kategoriler oranlarina gore siralanir; boylece komsu birlestirme
    orani benzer kategorileri gruplar."""
    tablo = pd.DataFrame({"x": x.astype(str).to_numpy(), "y": y.to_numpy()})
    g = tablo.groupby("x").agg(n=("y", "size"), kotu=("y", "sum"))
    g["oran"] = g["kotu"] / g["n"]
    g = g.sort_values(["oran", "n"], ascending=[True, False])
    return [{"n": int(r["n"]), "kotu": int(r["kotu"]), "min": None, "max": None,
             "ust": None, "degerler": [str(k)]} for k, r in g.iterrows()]


# ===========================================================================
# ETIKET VE METIN
# ===========================================================================
def _sayi_metni(v):
    """Okunur sayi: 10.087 / 20,1 / 0,0021 (bilimsel gosterim yok)."""
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "-"
    v = float(v)
    if v.is_integer() or abs(v) >= 1000:
        return "{:,}".format(int(round(v))).replace(",", ".")
    if abs(v) >= 1:
        metin = "%.2f" % v
    else:
        metin = "%.3g" % v
        if "e" in metin:
            metin = "%.6f" % v
    metin = metin.rstrip("0").rstrip(".") if "." in metin else metin
    return metin.replace(".", ",")


def _etiket(b, kategorik, tam_sayili=True, ilk=False, son=False):
    """Kategorik: kategoriler. Tam sayili kolon: gozlenen en kucuk - en buyuk
    deger ("1 - 2"). Ondalikli kolon: kesim noktalari ("≤ 20,1", "20,1 - 80",
    "> 80")."""
    if kategorik:
        d = b.get("degerler") or []
        return ", ".join(d[:4]) + (" +%d" % (len(d) - 4) if len(d) > 4 else "")
    if tam_sayili:
        if b.get("min") == b.get("max"):
            return _sayi_metni(b.get("min"))
        return "%s - %s" % (_sayi_metni(b.get("min")), _sayi_metni(b.get("max")))
    alt, ust = b.get("alt"), b.get("ust")
    if ilk or alt is None:
        return "≤ %s" % _sayi_metni(ust) if ust is not None else "tümü"
    if son or ust is None:
        return "> %s" % _sayi_metni(alt)
    return "%s - %s" % (_sayi_metni(alt), _sayi_metni(ust))


def _alt_sinirlar(ar):
    """Her araliga bir onceki araligin ust kesimini "alt" olarak yazar."""
    onceki = None
    for b in ar:
        b["alt"] = onceki
        onceki = b.get("ust")
    return ar


def _etiketler(ar, kategorik, tam_sayili):
    return [_etiket(b, kategorik, tam_sayili, ilk=(i == 0), son=(i == len(ar) - 1))
            for i, b in enumerate(ar)]


def _yuzde(o):
    return ("%%%.2f" % (100.0 * o)).replace(".", ",")


def hassas_mi(ad, aciklama=""):
    """Hassas degisken turu ya da None. Ad "_" ile parcalanip parca parca
    bakilir (TXN_AGE_DAYS gibi yanlis eslesmeyi azaltmak icin kok bastan)."""
    parcalar = [p for p in re.split(r"[^0-9A-Za-zÇĞİÖŞÜçğıöşü]+", str(ad).upper()) if p]
    metin = str(aciklama or "").upper()
    for tur, kokler in HASSAS_KOKLER.items():
        for k in kokler:
            if any(p == k or (len(k) >= 4 and p.startswith(k)) for p in parcalar):
                return tur
            if len(k) >= 4 and re.search(r"\b%s" % re.escape(k), metin):
                return tur
    return None


# ===========================================================================
# DEGISKEN BASINA HESAP
# ===========================================================================
def _gorunum(araliklar, eksik, kategorik, etiketler):
    """Aralik listesi -> ekranda gosterilecek satirlar + IV."""
    liste = list(araliklar) + ([eksik] if eksik and eksik["n"] else [])
    etiketler = list(etiketler) + ["Eksik"]
    kotu_t = sum(b["kotu"] for b in liste)
    iyi_t = sum(b["n"] - b["kotu"] for b in liste)
    toplam = sum(b["n"] for b in liste) or 1
    satirlar = []
    for i, b in enumerate(liste):
        satirlar.append({
            "etiket": etiketler[i],
            "n": int(b["n"]), "pay": round(float(b["n"]) / toplam, 4),
            "kotu": int(b["kotu"]), "oran": round(_oran(b), 6),
            "woe": (round(_woe(b, kotu_t, iyi_t, len(liste)), 4)
                    if kotu_t and iyi_t else None),
        })
    iv = iv_hesapla(liste)
    return {"satirlar": satirlar, "iv": None if iv is None else round(iv, 4)}


def _tutarlilik(araliklar, x, y, kategorik):
    """Egitimde bulunan araliklarin oran sirasi baska sette korunuyor mu?
    Spearman sira korelasyonu; en az 2 aralik ve her aralikta gozlem lazim."""
    if len(araliklar) < 2 or not len(x):
        return None
    if kategorik:
        harita = {d: i for i, b in enumerate(araliklar) for d in (b.get("degerler") or [])}
        kutu = x.astype(str).map(harita)
    else:
        kesimler = [b["ust"] for b in araliklar[:-1]]
        kutu = pd.Series(np.searchsorted(kesimler, pd.to_numeric(x, errors="coerce").to_numpy(),
                                         side="left"), index=x.index)
    t = pd.DataFrame({"k": kutu.to_numpy(), "y": y.to_numpy()}).dropna()
    g = t.groupby("k")["y"].agg(["size", "mean"])
    if len(g) < len(araliklar) or (g["size"] < 30).any():
        return None
    egitim = pd.Series([_oran(b) for b in araliklar])
    diger = g["mean"].reindex(range(len(araliklar))).reset_index(drop=True)
    r = egitim.rank().corr(diger.rank())
    return None if pd.isna(r) else round(float(r), 3)


def degisken_araligi(ad, s, y, tr, diger_setler, aciklama="", ham_iv=None):
    """Tek degiskenin aralik onerisi. s: tum satirlar; tr: egitim maskesi;
    diger_setler: {"Validasyon (OOS)": maske, ...}. Doner: sozluk ya da None."""
    kategorik = not pd.api.types.is_numeric_dtype(s) or pd.api.types.is_bool_dtype(s)
    yb = (pd.to_numeric(y, errors="coerce") > 0).astype(int)
    gecerli = pd.to_numeric(y, errors="coerce").notna()
    trm = tr & gecerli
    x_tr, y_tr = s[trm], yb[trm]
    dolu = x_tr.notna()
    if int(dolu.sum()) < 100 or y_tr.nunique() < 2:
        return None
    if kategorik and int(x_tr[dolu].nunique()) > KATEGORIK_MAX:
        return None
    toplam = int(len(x_tr))
    ince = (_ince_kategorik(x_tr[dolu], y_tr[dolu]) if kategorik
            else _ince_sayisal(x_tr[dolu], y_tr[dolu]))
    if kategorik:
        ar = _son_adim(ince, toplam)
        sekil = "gruplama" if len(ar) > 1 else "düz"
    else:
        ar, sekil = en_iyi_araliklar(ince, toplam)
    # Zayif iliski: oneri yok (tek aralik).
    if len(ar) > 1 and (iv_hesapla(ar) or 0.0) < IV_MIN:
        tek = ar[0]
        for b in ar[1:]:
            tek = _birlestir(tek, b)
        ar, sekil = [tek], "düz"
    _alt_sinirlar(ar)
    tam_sayili = (not kategorik) and bool(
        np.all(np.mod(pd.to_numeric(x_tr[dolu], errors="coerce").to_numpy(), 1) == 0))
    etiketler = _etiketler(ar, kategorik, tam_sayili)

    eksik = {"n": int((~dolu).sum()), "kotu": int(y_tr[~dolu].sum()),
             "min": None, "max": None, "ust": None}
    ayri = _gorunum(ar, eksik, kategorik, etiketler)

    # Medyanla doldurulmus gorunum (yalniz sayisal; kategorik eksik zaten
    # kendi "MISSING" kategorisi).
    dolu_gor, medyan, medyan_aralik = None, None, None
    if not kategorik and eksik["n"]:
        medyan = float(pd.to_numeric(x_tr[dolu], errors="coerce").median())
        kesimler = [b["ust"] for b in ar[:-1]]
        medyan_aralik = int(np.searchsorted(kesimler, medyan, side="left"))
        ar2 = [dict(b) for b in ar]
        ar2[medyan_aralik] = _birlestir(ar2[medyan_aralik], eksik)
        ar2[medyan_aralik].update(min=ar[medyan_aralik]["min"],
                                  max=ar[medyan_aralik]["max"],
                                  ust=ar[medyan_aralik]["ust"])
        dolu_gor = _gorunum(ar2, None, kategorik, etiketler)

    tutarlilik = {}
    for set_adi, m in (diger_setler or {}).items():
        mm = m & gecerli & s.notna()
        r = _tutarlilik(ar, s[mm], yb[mm], kategorik)
        if r is not None:
            tutarlilik[set_adi] = r

    hassas = hassas_mi(ad, aciklama)
    notlar = []
    if eksik["n"] and medyan_aralik is not None:
        o_eksik, o_med = _oran(eksik), _oran(ar[medyan_aralik])
        if o_med and abs(o_eksik - o_med) / o_med > EKSIK_FARK and \
                eksik["n"] >= MIN_PAY * toplam / 2:
            yakin = min(range(len(ar)), key=lambda i: abs(_oran(ar[i]) - o_eksik))
            if len(ar) == 1:
                notlar.append("Eksiklerin batma oranı %s, dolu değerlerin %s. Medyanla "
                              "doldurmak bu farkı gizler; eksik olup olmadığını "
                              "gösteren ayrı bir işaret kolonu önerilir."
                              % (_yuzde(o_eksik), _yuzde(o_med)))
            else:
                notlar.append("Eksiklerin batma oranı %s; medyanın düştüğü aralık "
                          "(%s) %s. Medyanla doldurmak bu farkı gizler; eksikleri "
                          "ayrı aralıkta tutmak ya da oranı en yakın aralığa "
                          "(%s, %s) atamak önerilir."
                          % (_yuzde(o_eksik), etiketler[medyan_aralik],
                             _yuzde(o_med), etiketler[yakin], _yuzde(_oran(ar[yakin]))))

    return {
        "ad": str(ad), "tur": "kategorik" if kategorik else "sayısal",
        "sekil": sekil, "aralik_sayisi": len(ar),
        "ham_iv": ham_iv, "ayri": ayri, "dolu": dolu_gor,
        "medyan": medyan, "kesimler": None if kategorik else [b["ust"] for b in ar[:-1]],
        "gruplar": [b.get("degerler") for b in ar] if kategorik else None,
        "tutarlilik": tutarlilik, "hassas": hassas, "etiketler": etiketler,
        "oneri": oneri_metni(ar, sekil, kategorik, hassas, tutarlilik, ham_iv,
                             ayri["iv"], etiketler),
        "notlar": notlar,
    }


SEKIL_METNI = {"artan": "artıyor", "azalan": "azalıyor", "U": "U şeklinde (ortada düşük, uçlarda yüksek)",
               "ters U": "ters U şeklinde (ortada yüksek, uçlarda düşük)"}


def oneri_metni(ar, sekil, kategorik, hassas, tutarlilik, ham_iv, yeni_iv, etiketler):
    """Tek cumlelik oneri (ekranda "Öneri" kolonu)."""
    parca = []
    if len(ar) < 2:
        if hassas:
            return ("Hassas değişken (%s) ve hedefle anlamlı bir ilişkisi yok; "
                    "modelden çıkarılması önerilir." % hassas)
        return "Hedefle anlamlı bir ilişki bulunmadı; aralıklara bölmek fayda sağlamıyor."
    if hassas:
        parca.append("Hassas değişken (%s): ham hâliyle kullanılmaması; bu kaba "
                     "aralıklarla kullanılması ya da modelden çıkarılması önerilir."
                     % hassas)
    oranlar = " → ".join("%s %s" % (e, _yuzde(_oran(b))) for e, b in zip(etiketler, ar))
    if kategorik:
        parca.append("Kategoriler batma oranına göre %d gruba toplanabilir: %s." % (len(ar), oranlar))
    else:
        parca.append("%d aralığa bölünmesi önerilir; batma oranı %s: %s."
                     % (len(ar), SEKIL_METNI.get(sekil, "düzensiz"), oranlar))
    if yeni_iv is not None:
        iv = ("%.3f" % yeni_iv).replace(".", ",")
        parca.append(("IV %s (10 eşit aralıkla %s)." % (iv, ("%.3f" % ham_iv).replace(".", ",")))
                     if ham_iv is not None else "IV %s." % iv)
    zayif = [s for s, r in tutarlilik.items() if r < TUTARLILIK_ESIK]
    if zayif:
        parca.append("Uyarı: sıralama %s setinde korunmuyor." % ", ".join(zayif))
    elif tutarlilik:
        parca.append("Sıralama %s setinde de korunuyor." % ", ".join(tutarlilik))
    return " ".join(parca)


def hesapla(df, target, adaylar, tr, diger_setler, aciklamalar=None, ham_ivler=None):
    """Butun adaylar icin aralik onerisi. Doner: {degisken: sonuc}."""
    y = df[target]
    cikti = {}
    for kol in adaylar:
        if kol not in df.columns or kol == target:
            continue
        try:
            r = degisken_araligi(kol, df[kol], y, tr, diger_setler,
                                 (aciklamalar or {}).get(kol, ""),
                                 (ham_ivler or {}).get(kol))
        except Exception:       # pylint: disable=broad-except
            r = None
        if r:
            cikti[str(kol)] = r
    return cikti


# ===========================================================================
# METRIK KONTROLLERI  (karar kartinda ve yapay zeka degerlendirmesinde)
# ===========================================================================
def kontroller(sonuc):
    """Kayitli sonuctan kesin kontroller: [{"ad", "gecti", "deger"}].
    Sayilar kodla hesaplanir; yapay zeka bunlari yorumlar, hesaplamaz."""
    satirlar = [s for s in ((sonuc.get("ayri") or {}).get("satirlar") or [])
                if s.get("etiket") != "Eksik"]
    toplam = sum(s["n"] for s in satirlar) or 1
    min_pay = min((float(s["n"]) / toplam for s in satirlar), default=0.0)
    p_enbuyuk = max((_p_degeri(satirlar[i], satirlar[i + 1])
                     for i in range(len(satirlar) - 1)), default=None)
    iv = (sonuc.get("ayri") or {}).get("iv")
    tut = sonuc.get("tutarlilik") or {}
    cikti = [
        {"ad": "Her aralıkta en az %5", "gecti": min_pay >= MIN_PAY - 1e-9,
         "deger": _yuzde(min_pay)},
        {"ad": "Eğilim", "gecti": sonuc.get("sekil") in ("artan", "azalan", "U", "ters U", "gruplama"),
         "deger": sonuc.get("sekil")},
        {"ad": "IV en az 0,02", "gecti": iv is not None and iv >= IV_MIN,
         "deger": "-" if iv is None else ("%.3f" % iv).replace(".", ",")},
        {"ad": "Komşu aralıklar anlamlı farklı", "gecti": p_enbuyuk is not None and p_enbuyuk <= ANLAM_P,
         "deger": "-" if p_enbuyuk is None else ("p %.3f" % p_enbuyuk).replace(".", ",")},
    ]
    if tut:
        cikti.append({"ad": "Sıra diğer setlerde korunuyor",
                      "gecti": all(r >= TUTARLILIK_ESIK for r in tut.values()),
                      "deger": ", ".join("%s %s" % (k, ("%.2f" % r).replace(".", ","))
                                         for k, r in tut.items())})
    cikti.append({"ad": "Hassas değişken değil", "gecti": not sonuc.get("hassas"),
                  "deger": sonuc.get("hassas") or "-"})
    return cikti


def uygula_seri(s, plan):
    """Planlanan donusumu bir seriye uygular. plan["tur"]:
      "aralik" -> aralik etiketi (metin); eksik -> "Eksik"
      "eksik"  -> eksik isareti (1 eksik, 0 dolu)"""
    if plan.get("tur") == "eksik":
        return s.isna().astype(int)
    etiketler = plan.get("etiketler") or []
    if plan.get("gruplar") is not None:
        harita = {d: etiketler[i] for i, g in enumerate(plan["gruplar"]) for d in (g or [])}
        # Egitimde gorulmemis kategori: "Diğer"
        cikti = s.astype(str).map(harita).fillna("Diğer")
    else:
        kesimler = [float(k) for k in plan.get("kesimler") or []]
        x = pd.to_numeric(s, errors="coerce")
        kutu = np.searchsorted(kesimler, x.to_numpy(), side="left")
        cikti = pd.Series([etiketler[i] if i < len(etiketler) else None for i in kutu],
                          index=s.index)
    return cikti.where(s.notna(), "Eksik").astype(object)
