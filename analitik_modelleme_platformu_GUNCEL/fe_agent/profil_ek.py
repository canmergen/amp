"""02.1 VERI PROFILI EK KONTROLLERI.

sfa.profil_cikar'in dort kontrolune (eksik orani yuksek, sabit, kimlik
benzeri, kardinalite) ek olarak:

  * ayni_icerik   : degerleri satir satir birebir ayni kolonlar
  * baskin        : bir deger satirlarin BASKIN_ESIK'i ya da fazlasinda
  * donem         : kolon bazi donemlerde tamamen bos ya da tek degerli
  * gizli_eksik   : -999, 9999 gibi ozel kod; dagilimin geri kalanindan kopuk
  * sifir         : dolu satirlarin SIFIR_ESIK'i ya da fazlasi sifir
  * negatif       : kolon kartinin olcusu adet, gun, sure iken negatif deger
  * sicrama       : eksik orani art arda iki donem arasinda sicriyor
  * uc            : en buyuk deger, %99'luk degerin UC_DEGER_KAT kati ustunde
  * tekrar        : ayni kimlik ve donemle birden fazla satir, tamamen ayni satir
  * hedef         : sinif dagilimi, hedefi bos satir, donem basina sinif paylari

HEPSI TABLONUN TAMAMINDA, KESIN SAYIMLA: orneklem yok, yaklasik sayim yok.
Ek kontroller yalniz dort temel kontrolden gecen (kusurlu olmayan)
kolonlara uygulanir; kusurlu kolonlar zaten degisken uretimine girmez.
"""
import hashlib
import re

import numpy as np
import pandas as pd

BASKIN_ESIK = 0.99
SIFIR_ESIK = 0.95
GIZLI_EKSIK_ESIK = 0.01
GIZLI_EKSIK_DEGERLER = (-1, -9, -99, -999, -9999, -99999, -999999, -9999999,
                        -99999999, 9999, 99999, 999999, 9999999, 99999999, 999999999)
# Pozitif ozel kod: geri kalan en buyuk deger bunun GIZLI_KOPUK_KAT'inda
# biri altinda kalmali (9999 ile 9.998 ayni dagilimdir, kod sayilmaz).
GIZLI_KOPUK_KAT = 10
DONEM_SICRAMA_ESIK = 0.20
DONEM_SABIT_MIN_SATIR = 100
UC_DEGER_KAT = 100
UC_DEGER_YUZDELIK = 0.99
# Sutun parcasi: donem hesabinda bellek sinirli kalsin.
DONEM_PARCA = 200

# Kolon kartinin olcu alaninda bu kelimeler geciyorsa deger negatif olamaz.
NEGATIF_ON_EKLER = ("adet", "sayı", "sayi", "gün", "gun", "süre", "sure", "yaş", "yas",
                    "kez", "frekans")
NEGATIF_KELIMELER = ("ay", "ayı", "aylar", "yıl", "yılı", "yil", "yili")


def _tr_kucuk(metin):
    return str(metin or "").replace("I", "ı").replace("İ", "i").lower()


def olcu_negatif_olamaz(olcu):
    """Kolon kartinin olcu alani adet, sayi, gun, sure, yas, ay, yil gibi
    negatif olamayacak bir buyukluk mu?"""
    kelimeler = re.findall(r"[a-zçğıöşü]+", _tr_kucuk(olcu))
    return any(k.startswith(NEGATIF_ON_EKLER) or k in NEGATIF_KELIMELER for k in kelimeler)


def deger_metni(v):
    """Ekranda gosterilecek deger: 7.0 -> "7", NaN -> "boş"."""
    if v is None:
        return "boş"
    try:
        if pd.isna(v):
            return "boş"
    except (TypeError, ValueError):
        pass
    if isinstance(v, (bool, np.bool_)):
        return "1" if v else "0"
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    if isinstance(v, (float, np.floating)):
        f = float(v)
        if f == int(f) and abs(f) < 1e15:
            return str(int(f))
        return ("%.6g" % f).replace(".", ",")
    return str(v)


def _sayisal_mi(s):
    return pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s)


def _ozet_anahtari(s):
    """Kolonun icerik ozeti (ayni icerik gruplamasi icin). Sayisal kolonlar
    float64'e cevrilir: 1 ile 1.0 ayni deger sayilir."""
    if _sayisal_mi(s):
        a = pd.to_numeric(s, errors="coerce").to_numpy(dtype="float64") + 0.0
        bos = np.isnan(a)
        return ("s", hashlib.md5(bos.tobytes() + np.where(bos, 0.0, a).tobytes()).hexdigest())
    o = s.astype(object).where(s.notna(), None)
    return ("m", hashlib.md5(pd.util.hash_pandas_object(o, index=False)
                             .to_numpy().tobytes()).hexdigest())


def _ayni_mi(s1, s2):
    """Ozet esitse KESIN karsilastirma (ozet carpismasina guvenilmez)."""
    if _sayisal_mi(s1) and _sayisal_mi(s2):
        a = pd.to_numeric(s1, errors="coerce").to_numpy(dtype="float64")
        b = pd.to_numeric(s2, errors="coerce").to_numpy(dtype="float64")
        return bool(np.array_equal(a, b, equal_nan=True))
    if _sayisal_mi(s1) != _sayisal_mi(s2):
        return False
    a = s1.astype(object).where(s1.notna(), None).tolist()
    b = s2.astype(object).where(s2.notna(), None).tolist()
    return a == b


def ayni_icerik(df, adaylar):
    """Doner: [{"kalan": kolon, "kopyalar": [kolon, ...]}]. Gruptan
    tablodaki sirasi ilk olan kolon kalir."""
    gruplar = {}
    for kol in adaylar:
        gruplar.setdefault(_ozet_anahtari(df[kol]), []).append(kol)
    sonuc = []
    for uyeler in gruplar.values():
        if len(uyeler) < 2:
            continue
        kalanlar = list(uyeler)
        while len(kalanlar) > 1:
            ilk, digerleri = kalanlar[0], kalanlar[1:]
            kopya = [k for k in digerleri if _ayni_mi(df[ilk], df[k])]
            if kopya:
                sonuc.append({"kalan": ilk, "kopyalar": kopya})
            kalanlar = [k for k in digerleri if k not in kopya]
    return sonuc


def _gizli_eksik(sayim, dolu, en_kucuk, en_buyuk):
    """Dolu satirlarin GIZLI_EKSIK_ESIK'inden fazlasinda gecen ve geri
    kalan degerlerden kopuk ozel kod. Doner: (deger, adet) ya da None."""
    aday = None
    for v in GIZLI_EKSIK_DEGERLER:
        n = int(sayim.get(v, 0) or 0)
        if not n or n / dolu <= GIZLI_EKSIK_ESIK:
            continue
        if v < 0:
            # Kolonda bu koddan baska negatif deger yok.
            kalan_min = min((float(k) for k in sayim.index if float(k) != v), default=None)
            if kalan_min is not None and kalan_min < 0:
                continue
            if en_kucuk != v:
                continue
        else:
            kalan_max = max((float(k) for k in sayim.index if float(k) != v), default=None)
            if kalan_max is not None and kalan_max * GIZLI_KOPUK_KAT >= v:
                continue
            if en_buyuk != v:
                continue
        if aday is None or n > aday[1]:
            aday = (v, n)
    return aday


def kolon_kontrolleri(df, adaylar, olculer=None):
    """Kolon basina kontroller. olculer: {kolon: kolon kartinin olcu alani};
    bos ya da None ise negatif kontrolu uygulanmaz."""
    n = len(df)
    sonuc = {"baskin": [], "gizli_eksik": [], "sifir": [], "negatif": [], "uc": []}
    if not n:
        return sonuc
    olculer = olculer or {}
    for kol in adaylar:
        s = df[kol]
        vc = s.value_counts(dropna=False)
        if not len(vc):
            continue
        ust_deger, ust_adet = vc.index[0], int(vc.iloc[0])
        baskin = ust_adet / n >= BASKIN_ESIK
        if baskin:
            sonuc["baskin"].append({"kolon": kol, "deger": deger_metni(ust_deger),
                                    "pay": ust_adet / n})
        if not _sayisal_mi(s):
            continue
        sn = pd.to_numeric(s, errors="coerce").dropna()
        dolu = len(sn)
        if not dolu:
            continue
        sayim = sn.value_counts()
        en_kucuk, en_buyuk = float(sn.min()), float(sn.max())
        gizli = _gizli_eksik(sayim, dolu, en_kucuk, en_buyuk)
        if gizli:
            sonuc["gizli_eksik"].append({"kolon": kol, "deger": deger_metni(gizli[0]),
                                         "adet": gizli[1], "pay": gizli[1] / dolu})
        sifir = int(sayim.get(0, 0) or 0)
        if not baskin and sifir / dolu >= SIFIR_ESIK:
            sonuc["sifir"].append({"kolon": kol, "adet": sifir, "pay": sifir / dolu})
        # Uc deger: ust uctaki ozel kod (9999) uc deger sayilmaz.
        ust_gizli = gizli is not None and gizli[0] > 0
        if not ust_gizli:
            p99 = float(sn.quantile(UC_DEGER_YUZDELIK))
            if p99 > 0 and en_buyuk > UC_DEGER_KAT * p99:
                sonuc["uc"].append({"kolon": kol, "maks": en_buyuk, "p99": p99})
        if olcu_negatif_olamaz(olculer.get(kol)):
            negatif = sn < 0
            if gizli is not None and gizli[0] < 0:
                negatif &= sn != gizli[0]
            adet = int(negatif.sum())
            if adet:
                sonuc["negatif"].append({"kolon": kol, "adet": adet,
                                         "en_kucuk": float(sn[negatif].min()),
                                         "olcu": str(olculer.get(kol))})
    return sonuc


def _donem_sirasi(degerler):
    def anahtar(v):
        try:
            return (0, float(v), "")
        except (TypeError, ValueError):
            return (1, 0.0, str(v))
    return sorted(degerler, key=anahtar)


def donem_kontrolleri(df, adaylar, donem):
    """Doner: (donem_listesi, [{"kolon", "bos": [donem], "sabit": [donem]}],
    [{"kolon", "once", "sonra", "once_oran", "sonra_oran"}]).
    Donem kolonu yoksa ya da tek donem varsa (None, None, None)."""
    if not donem or donem not in df.columns:
        return None, None, None
    g = df[donem]
    donemler = _donem_sirasi([d for d in g.dropna().unique()])
    if len(donemler) < 2:
        return donemler, None, None
    satir = g.value_counts()
    buyuk = {d for d in donemler if int(satir.get(d, 0)) >= DONEM_SABIT_MIN_SATIR}
    bos_sabit, sicrama = [], []
    for i in range(0, len(adaylar), DONEM_PARCA):
        parca = list(adaylar[i:i + DONEM_PARCA])
        alt = df[parca]
        bos_oran = alt.isna().groupby(g).mean().reindex(donemler)
        tekil = alt.groupby(g).nunique(dropna=True).reindex(donemler)
        for kol in parca:
            oran = bos_oran[kol]
            bos = [d for d in donemler if float(oran[d]) >= 1.0]
            sabit = [d for d in donemler if d in buyuk and float(oran[d]) == 0.0
                     and int(tekil[kol][d]) == 1]
            # Butun donemlerde ayni tek deger: kolon sabittir, temel kontrol
            # yakalar; burada yalniz donemden doneme degisen kolon.
            if sabit and len(sabit) == len(donemler):
                sabit = []
            if bos or sabit:
                bos_sabit.append({"kolon": kol, "bos": [deger_metni(d) for d in bos],
                                  "sabit": [deger_metni(d) for d in sabit]})
                continue
            en_iyi = None
            for a, b in zip(donemler, donemler[1:]):
                fark = abs(float(oran[b]) - float(oran[a]))
                if fark > DONEM_SICRAMA_ESIK and (en_iyi is None or fark > en_iyi[0]):
                    en_iyi = (fark, a, b)
            if en_iyi:
                _f, a, b = en_iyi
                sicrama.append({"kolon": kol, "once": deger_metni(a), "sonra": deger_metni(b),
                                "once_oran": float(oran[a]), "sonra_oran": float(oran[b])})
    return [deger_metni(d) for d in donemler], bos_sabit, sicrama


def tekrar_satirlar(df, kimlik=None, donem=None):
    """Doner: {"kimlik": fazla satir sayisi ya da None, "anahtar": [kolonlar],
    "tam": tamamen ayni fazla satir sayisi, "toplam": ikisinden en az birine
    takilan fazla satir sayisi (her satir bir kez)}."""
    tam = df.duplicated() if len(df) else pd.Series([], dtype=bool)
    sonuc = {"kimlik": None, "anahtar": [], "tam": int(tam.sum()), "toplam": int(tam.sum())}
    if kimlik and kimlik in df.columns:
        anahtar = [kimlik] + ([donem] if donem and donem in df.columns else [])
        anahtar_tekrar = df.duplicated(anahtar)
        sonuc["anahtar"] = anahtar
        sonuc["kimlik"] = int(anahtar_tekrar.sum())
        # Ayni satir iki kez sayilmaz (tamamen ayni satir anahtarda da tekrardir).
        sonuc["toplam"] = int((anahtar_tekrar | tam).sum())
    return sonuc


def hedef_ozeti(df, hedef, donem=None):
    """Sinif dagilimi, hedefi bos satir ve donem basina sinif paylari.
    Hedef yoksa None."""
    if not hedef or hedef not in df.columns:
        return None
    y = df[hedef]
    bos = int(y.isna().sum())
    dolu = y.dropna()
    vc = dolu.value_counts()
    siniflar = [{"deger": deger_metni(v), "satir": int(vc[v]),
                 "pay": int(vc[v]) / len(dolu) if len(dolu) else 0.0}
                for v in _donem_sirasi(list(vc.index))]
    ikili = len(vc) == 2 and {deger_metni(v) for v in vc.index} == {"0", "1"}
    sonuc = {"kolon": hedef, "bos": bos, "satir": int(len(df)), "siniflar": siniflar,
             "ikili": ikili, "donemler": []}
    if donem and donem in df.columns and len(dolu):
        g = df[donem]
        donemler = _donem_sirasi([d for d in g.dropna().unique()])
        if len(donemler) >= 2:
            tablo = pd.crosstab(g, y).reindex(donemler).fillna(0)
            for d in donemler:
                satir = tablo.loc[d]
                toplam = int(satir.sum())
                paylar = {deger_metni(k): (int(satir[k]) / toplam if toplam else 0.0)
                          for k in tablo.columns}
                sonuc["donemler"].append({"donem": deger_metni(d), "satir": toplam,
                                          "paylar": paylar})
    return sonuc


def ek_kontroller(df, adaylar, donem=None, kimlik=None, hedef=None, olculer=None):
    """Butun ek kontroller. adaylar: dort temel kontrolden gecen kolonlar
    (tablodaki sirasiyla)."""
    adaylar = [k for k in adaylar if k in df.columns]
    sonuc = kolon_kontrolleri(df, adaylar, olculer)
    sonuc["ayni_icerik"] = ayni_icerik(df, adaylar)
    kopya = {k for g in sonuc["ayni_icerik"] for k in g["kopyalar"]}
    baskin = {x["kolon"] for x in sonuc["baskin"]}
    donemler, bos_sabit, sicrama = donem_kontrolleri(
        df, [k for k in adaylar if k not in kopya and k not in baskin], donem)
    sonuc["donemler"] = donemler
    sonuc["donem"] = bos_sabit
    sonuc["sicrama"] = sicrama
    sonuc["tekrar"] = tekrar_satirlar(df, kimlik, donem)
    sonuc["hedef"] = hedef_ozeti(df, hedef, donem)
    sonuc["olcu_var"] = any(str(v or "").strip() for v in (olculer or {}).values())
    # Kopya kolonlar ayrica bilgi listelerinde tekrar gosterilmez.
    for anahtar in ("baskin", "gizli_eksik", "sifir", "negatif", "uc"):
        sonuc[anahtar] = [x for x in sonuc[anahtar] if x["kolon"] not in kopya]
    return sonuc
