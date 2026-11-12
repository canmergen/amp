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
# Kullanicinin 02.1'de onayladigi esikler bu anahtarlarla gelir (yoksa
# varsayilan). Gizli eksik kod listesi ve kopukluk kati sabittir.
SIZINTI_AUC = 0.95
YAKIN_KOR = 0.99
KAYMA_KAT = 10
ESIK_VARSAYILAN = {"baskin": BASKIN_ESIK, "sifir": SIFIR_ESIK, "gizli": GIZLI_EKSIK_ESIK,
                   "donem_min_satir": DONEM_SABIT_MIN_SATIR, "sicrama": DONEM_SICRAMA_ESIK,
                   "uc_kat": UC_DEGER_KAT, "sizinti_auc": SIZINTI_AUC, "yakin_kor": YAKIN_KOR,
                   "kayma_kat": KAYMA_KAT}


def esik_birlestir(esik=None):
    d = dict(ESIK_VARSAYILAN)
    d.update({k: v for k, v in (esik or {}).items() if k in d and v is not None})
    return d


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


def _gizli_eksik(sayim, dolu, en_kucuk, en_buyuk, esik=GIZLI_EKSIK_ESIK):
    """Dolu satirlarin GIZLI_EKSIK_ESIK'inden fazlasinda gecen ve geri
    kalan degerlerden kopuk ozel kod. Doner: (deger, adet) ya da None."""
    aday = None
    for v in GIZLI_EKSIK_DEGERLER:
        n = int(sayim.get(v, 0) or 0)
        if not n or n / dolu <= esik:
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


def kolon_kontrolleri(df, adaylar, olculer=None, esik=None):
    """Kolon basina kontroller. olculer: {kolon: kolon kartinin olcu alani};
    bos ya da None ise negatif kontrolu uygulanmaz."""
    e = esik_birlestir(esik)
    n = len(df)
    sonuc = {"baskin": [], "gizli_eksik": [], "karisik_eksik": [], "sifir": [], "negatif": [],
             "uc": []}
    if not n:
        return sonuc
    olculer = olculer or {}
    for kol in adaylar:
        s = df[kol]
        vc = s.value_counts(dropna=False)
        if not len(vc):
            continue
        ust_deger, ust_adet = vc.index[0], int(vc.iloc[0])
        baskin = ust_adet / n >= e["baskin"]
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
        gizli = _gizli_eksik(sayim, dolu, en_kucuk, en_buyuk, e["gizli"])
        bos = int(s.isna().sum())
        if gizli:
            sonuc["gizli_eksik"].append({"kolon": kol, "deger": deger_metni(gizli[0]),
                                         "adet": gizli[1], "pay": gizli[1] / dolu, "bos": bos})
        elif bos:
            # KARISIK EKSIK KODLAMASI: kolonda bos hucre VAR ve ayni kolonda
            # -1, -99, 9999 gibi kopuk bir ozel kod da var. Payina bakilmaz
            # (tek satir bile olsa): eksik bilgi iki farkli bicimde yazilmis.
            karisik = _gizli_eksik(sayim, dolu, en_kucuk, en_buyuk, 0.0)
            if karisik:
                sonuc["karisik_eksik"].append({"kolon": kol, "deger": deger_metni(karisik[0]),
                                               "adet": karisik[1], "pay": karisik[1] / dolu,
                                               "bos": bos})
        sifir = int(sayim.get(0, 0) or 0)
        if not baskin and sifir / dolu >= e["sifir"]:
            sonuc["sifir"].append({"kolon": kol, "adet": sifir, "pay": sifir / dolu})
        # Uc deger: ust uctaki ozel kod (9999) uc deger sayilmaz.
        ust_gizli = gizli is not None and gizli[0] > 0
        if not ust_gizli:
            p99 = float(sn.quantile(UC_DEGER_YUZDELIK))
            if p99 > 0 and en_buyuk > e["uc_kat"] * p99:
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


def donem_kontrolleri(df, adaylar, donem, esik=None):
    """Doner: (donem_listesi, [{"kolon", "bos": [donem], "sabit": [donem]}],
    [{"kolon", "once", "sonra", "once_oran", "sonra_oran"}]).
    Donem kolonu yoksa ya da tek donem varsa (None, None, None)."""
    if not donem or donem not in df.columns:
        return None, None, None
    g = df[donem]
    donemler = _donem_sirasi([d for d in g.dropna().unique()])
    if len(donemler) < 2:
        return donemler, None, None
    e = esik_birlestir(esik)
    satir = g.value_counts()
    buyuk = {d for d in donemler if int(satir.get(d, 0)) >= e["donem_min_satir"]}
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
                if fark > e["sicrama"] and (en_iyi is None or fark > en_iyi[0]):
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


def ek_kontroller(df, adaylar, donem=None, kimlik=None, hedef=None, olculer=None, esik=None,
                  tarihler=()):
    """Butun ek kontroller. adaylar: dort temel kontrolden gecen kolonlar
    (tablodaki sirasiyla)."""
    adaylar = [k for k in adaylar if k in df.columns]
    sonuc = kolon_kontrolleri(df, adaylar, olculer, esik)
    # Ayni icerikli gruplardan hangisinin kalacagi kullanicinin secimine
    # bagli; bulgular her uye icin hesaplanir, gosterirken kopyalar elenir.
    sonuc["ayni_icerik"] = ayni_icerik(df, adaylar)
    baskin = {x["kolon"] for x in sonuc["baskin"]}
    donemler, bos_sabit, sicrama = donem_kontrolleri(
        df, [k for k in adaylar if k not in baskin], donem, esik)
    sonuc["donemler"] = donemler
    sonuc["donem"] = bos_sabit
    sonuc["sicrama"] = sicrama
    sonuc["tekrar"] = tekrar_satirlar(df, kimlik, donem)
    sonuc["hedef"] = hedef_ozeti(df, hedef, donem)
    sonuc["olcu_var"] = any(str(v or "").strip() for v in (olculer or {}).values())
    # Ikinci set (pencere ve tutar / adet ciftleri kolon kartina ve donem
    # turlerine bagli; akis_faz02.profil_hesapla ekler).
    sonuc["metin_bos"] = metin_bos_kontrol(df, adaylar)
    sonuc["yazim"] = yazim_kontrol(df, adaylar)
    # Tarih tipindeki kolonlar (tarihler) genel kontrollere girmez, tarih
    # kontrollerine girer.
    tarihli = list(adaylar) + [k for k in tarihler or () if k in df.columns and k not in adaylar]
    sonuc["tarih_kod"], sonuc["tarih_kolon"] = tarih_kod_kontrol(df, tarihli)
    sonuc["metin_kolon"] = sum(1 for k in adaylar if _metin_kolonu_mu(df[k]))
    sonuc["tarih_sonra"] = tarih_sonra_kontrol(df, tarihli, donem)
    sonuc["kayma"] = deger_kaymasi(df, [k for k in adaylar if k not in baskin], donem, esik)
    sonuc["birebir"] = hedef_birebir(df, adaylar, hedef, esik)
    kopya = {k for g in sonuc["ayni_icerik"] for k in g["kopyalar"]}
    sonuc["yakin_icerik"] = yakin_kopyalar(df, adaylar, esik, haric=kopya | baskin)
    return sonuc



# ===========================================================================
# 02.1 EK KONTROLLER (ikinci set): metin olarak yazilmis bos, kategori
# yazim tutarsizligi, ozel tarih kodu, donemden sonraki tarih, donemler
# arasi deger kaymasi, hedefle neredeyse birebir, neredeyse ayni kolonlar,
# pencere tutarliligi, tutar / adet uyumsuzlugu. Hepsi tablonun TAMAMINDAN;
# ornekleme yok.
# ===========================================================================
# Metin olarak yazilmis bos: kirpilmis, kucuk harfe cevrilmis karsilastirma.
METIN_BOS_DEGERLER = frozenset((
    "", "null", "none", "nan", "nat", "n/a", "na", "#n/a", "nil", "undefined",
    "-", "--", "---", "?", "??", ".", "boş", "bos", "bilinmiyor", "bilinmeyen",
    "belirtilmemiş", "belirtilmemis", "tanımsız", "tanimsiz"))
# Ozel tarih kodu: yili bu araligin disindaki tarih (1900-01-01, 9999-12-31).
TARIH_YIL_ALT = 1901
TARIH_YIL_UST = 2200
# Deger kaymasi: donemde en az bu kadar sifir disi dolu satir olmali.
KAYMA_MIN_SATIR = 30
# Hedefle birebir: kategorik kolonda en cok bu kadar farkli deger (fazlasi
# hedef oraniyla kodlaninca ezberler, yaniltir).
BIREBIR_KAT_MAX = 50
# Yazim tutarsizligi: kolon basina saklanan en cok esleme.
YAZIM_HARITA_MAX = 5000
_TR_KATLA = str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
                           "â": "a", "î": "i", "û": "u"})


def _metin_kolonu_mu(s):
    return not (pd.api.types.is_numeric_dtype(s) or pd.api.types.is_bool_dtype(s)
                or pd.api.types.is_datetime64_any_dtype(s))


def _metin_sayimi(s):
    d = s.dropna()
    if not len(d):
        return pd.Series(dtype="int64")
    return d.astype(str).value_counts()


def metin_bos_normal(v):
    return _tr_kucuk(str(v).strip())


def metin_bos_kontrol(df, adaylar):
    """[{"kolon", "degerler": [{"deger", "adet"}], "adet", "pay"}]: metin
    kolonda "NULL", "-", "?", "" gibi bos anlamina gelen yazilar."""
    sonuc = []
    for kol in adaylar:
        s = df[kol]
        if not _metin_kolonu_mu(s):
            continue
        vc = _metin_sayimi(s)
        if not len(vc):
            continue
        bul = [(v, int(n)) for v, n in vc.items() if metin_bos_normal(v) in METIN_BOS_DEGERLER]
        if bul:
            adet = sum(n for _v, n in bul)
            sonuc.append({"kolon": kol, "degerler": [{"deger": v, "adet": n} for v, n in bul],
                          "adet": adet, "pay": adet / max(int(s.notna().sum()), 1)})
    return sonuc


def yazim_anahtari(v):
    """Ayni degerin farkli yazimlari ayni anahtara duser: bas / son bosluk,
    coklu bosluk, buyuk / kucuk harf, Turkce karakter."""
    t = re.sub(r"\s+", " ", str(v).strip())
    return _tr_kucuk(t).translate(_TR_KATLA)


def yazim_kontrol(df, adaylar):
    """[{"kolon", "gruplar": [{"hedef", "yazimlar": [{"deger", "adet"}]}],
    "anahtar": {yazim anahtari: hedef}, "satir", "grup"}]: ayni degerin
    farkli yazimlari. Hedef yazim grubun en sik gecen yazimidir; satir
    hedeften farkli yazilmis satir sayisi."""
    sonuc = []
    for kol in adaylar:
        s = df[kol]
        if not _metin_kolonu_mu(s):
            continue
        vc = _metin_sayimi(s)
        if len(vc) < 2:
            continue
        gruplar = {}
        for v, n in vc.items():
            if metin_bos_normal(v) in METIN_BOS_DEGERLER:
                continue
            gruplar.setdefault(yazim_anahtari(v), []).append((v, int(n)))
        cok = [g for g in gruplar.values() if len(g) > 1]
        if not cok:
            continue
        anahtar, liste, satir = {}, [], 0
        for g in sorted(cok, key=lambda g: -sum(n for _v, n in g)):
            hedef = g[0][0]          # value_counts sirasi: en sik once
            if len(anahtar) < YAZIM_HARITA_MAX:
                anahtar[yazim_anahtari(hedef)] = hedef
            satir += sum(n for _v, n in g[1:])
            liste.append({"hedef": hedef, "yazimlar": [{"deger": v, "adet": n} for v, n in g]})
        sonuc.append({"kolon": kol, "gruplar": liste[:20], "grup": len(liste),
                      "anahtar": anahtar, "satir": satir})
    return sonuc


_TARIH_METIN = re.compile(r"^\s*(\d{4})-\d{2}-\d{2}")


def _tarih_kodlu(s):
    """Ozel tarih kodu olan hucrelerin maskesi (datetime ya da 'YYYY-AA-GG'
    metni); tarih kolonu degilse None."""
    if pd.api.types.is_datetime64_any_dtype(s):
        yil = s.dt.year
        return (yil < TARIH_YIL_ALT) | (yil > TARIH_YIL_UST)
    if not _metin_kolonu_mu(s):
        return None
    vc = _metin_sayimi(s)
    if not len(vc):
        return None
    tarih = [v for v in vc.index if _TARIH_METIN.match(str(v))]
    if len(tarih) < 0.8 * len(vc):
        return None
    kod = {v for v in tarih if not (TARIH_YIL_ALT <= int(_TARIH_METIN.match(v).group(1))
                                    <= TARIH_YIL_UST)}
    if not kod:
        return pd.Series(False, index=s.index)
    return s.notna() & s.astype(str).isin(kod)


def tarih_kod_kontrol(df, adaylar):
    """([{"kolon", "degerler": [{"deger", "adet"}], "adet", "pay"}], tarih
    kolonu sayisi): tarih kolonunda 1900-01-01, 9999-12-31 gibi kod
    tarihler."""
    sonuc, tarih = [], 0
    for kol in adaylar:
        s = df[kol]
        m = _tarih_kodlu(s)
        if m is not None:
            tarih += 1
        if m is None or not bool(m.any()):
            continue
        vc = s[m].astype(str).str[:10].value_counts()
        adet = int(m.sum())
        sonuc.append({"kolon": kol, "degerler": [{"deger": v, "adet": int(n)} for v, n in vc.items()][:10],
                      "adet": adet, "pay": adet / max(int(s.notna().sum()), 1)})
    return sonuc, tarih


def donem_sonu(seri):
    """Donem degerinin son gunu (YYYYAA -> ayin son gunu, YYYYAAGG -> o gun,
    YYYY -> yil sonu). Cozulemeyen None; yarisi cozulemiyorsa None doner."""
    t = seri.astype(str).str.replace(r"\D", "", regex=True)
    sonuc = pd.Series(pd.NaT, index=seri.index, dtype="datetime64[ns]")
    ay = t.str.len() == 6
    gun = t.str.len() == 8
    yil = t.str.len() == 4
    if ay.any():
        sonuc[ay] = (pd.to_datetime(t[ay] + "01", format="%Y%m%d", errors="coerce")
                     + pd.offsets.MonthEnd(0))
    if gun.any():
        sonuc[gun] = pd.to_datetime(t[gun], format="%Y%m%d", errors="coerce")
    if yil.any():
        sonuc[yil] = pd.to_datetime(t[yil] + "1231", format="%Y%m%d", errors="coerce")
    if sonuc.notna().sum() < 0.5 * max(int(seri.notna().sum()), 1):
        return None
    return sonuc


def _tarih_serisi(s):
    if not pd.api.types.is_datetime64_any_dtype(s):
        return None
    try:
        if getattr(s.dt, "tz", None) is not None:
            s = s.dt.tz_localize(None)
    except Exception:
        pass
    return s


def tarih_sonra_kontrol(df, adaylar, donem):
    """[{"kolon", "adet", "pay", "en_gec"}]: tarih kolonunda satirin gozlem
    doneminden SONRAKI tarihler (gelecek bilgisi, sizinti riski)."""
    if not donem or donem not in df.columns:
        return None
    son = donem_sonu(df[donem])
    if son is None:
        return None
    sonuc = []
    for kol in adaylar:
        if kol == donem:
            continue
        t = _tarih_serisi(df[kol])
        if t is None:
            continue
        kod = _tarih_kodlu(t)
        m = t.notna() & son.notna() & (t > son)
        if kod is not None:
            m &= ~kod
        adet = int(m.sum())
        if adet:
            sonuc.append({"kolon": kol, "adet": adet,
                          "pay": adet / max(int((t.notna() & son.notna()).sum()), 1),
                          "en_gec": str(t[m].max())[:10]})
    return sonuc


def deger_kaymasi(df, adaylar, donem, esik=None):
    """[{"kolon", "once", "sonra", "once_deger", "sonra_deger", "kat"}]:
    sayisal kolonun sifir disi mutlak degerlerinin %25, %50 ve %75'lik
    degerleri art arda iki donem arasinda AYNI YONDE en az kayma_kat kat
    degisiyor (birim degisikligi gibi). Uc yuzdelik birlikte aranir: iki
    tepeli dagilimda medyan tek basina zipliyabilir. once_deger /
    sonra_deger medyandir; kat uc oranin en kucugu."""
    if not donem or donem not in df.columns:
        return None
    e = esik_birlestir(esik)
    g = df[donem]
    donemler = _donem_sirasi([d for d in g.dropna().unique()])
    if len(donemler) < 2:
        return None
    sayisal = [k for k in adaylar if k != donem and _sayisal_mi(df[k])
               and not pd.api.types.is_bool_dtype(df[k])]
    sonuc = []
    for i in range(0, len(sayisal), DONEM_PARCA):
        parca = sayisal[i:i + DONEM_PARCA]
        a = df[parca].apply(pd.to_numeric, errors="coerce").abs()
        a = a.where(a != 0)
        grp = a.groupby(g)
        q = {qq: grp.quantile(qq).reindex(donemler) for qq in (0.25, 0.5, 0.75)}
        say = grp.count().reindex(donemler)
        for kol in parca:
            en = None
            for d1, d2 in zip(donemler[:-1], donemler[1:]):
                if say[kol][d1] < KAYMA_MIN_SATIR or say[kol][d2] < KAYMA_MIN_SATIR:
                    continue
                oranlar = []
                for qq in (0.25, 0.5, 0.75):
                    x1, x2 = float(q[qq][kol][d1]), float(q[qq][kol][d2])
                    if not (x1 > 0 and x2 > 0):
                        break
                    oranlar.append(x2 / x1)
                if len(oranlar) < 3:
                    continue
                if all(o > 1 for o in oranlar):
                    kat = min(oranlar)
                elif all(o < 1 for o in oranlar):
                    kat = 1.0 / max(oranlar)
                else:
                    continue
                m1, m2 = float(q[0.5][kol][d1]), float(q[0.5][kol][d2])
                if kat >= e["kayma_kat"] and (en is None or kat > en["kat"]):
                    en = {"kolon": kol, "once": deger_metni(d1), "sonra": deger_metni(d2),
                          "once_deger": m1, "sonra_deger": m2, "kat": kat}
            if en:
                sonuc.append(en)
    return sonuc


def _auc(skor, y):
    """Tek degiskenli AUC (sira tabanli; esitlikler ortalama sira)."""
    n1 = int(y.sum())
    n0 = int(len(y) - n1)
    if not n1 or not n0:
        return None
    r = pd.Series(skor).rank(method="average").to_numpy()
    return float((r[y.to_numpy() == 1].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def hedef_birebir(df, adaylar, hedef, esik=None):
    """[{"kolon", "auc"}]: tek basina hedefi neredeyse kusursuz ayiran kolon
    (AUC ya da 1 - AUC >= sizinti_auc). Bos deger kendi grubudur. Yalniz
    iki sinifli hedefte; kategorik kolonda en cok BIREBIR_KAT_MAX deger."""
    if not hedef or hedef not in df.columns:
        return None
    yh = pd.to_numeric(df[hedef], errors="coerce")
    sinif = set(yh.dropna().unique().tolist())
    if not sinif or not sinif <= {0, 1}:
        return None
    e = esik_birlestir(esik)
    gecerli = yh.notna()
    y = yh[gecerli].astype(int)
    sonuc = []
    for kol in adaylar:
        if kol == hedef:
            continue
        s = df.loc[gecerli, kol]
        if _sayisal_mi(s) and not pd.api.types.is_bool_dtype(s):
            x = pd.to_numeric(s, errors="coerce")
            if x.nunique() < 2 and not x.isna().any():
                continue
            alt = (x.min() if x.notna().any() else 0) - 1
            skor = x.fillna(alt).to_numpy(dtype=float)
        else:
            k = s.astype(object).where(s.notna(), "__BOS__").astype(str)
            if k.nunique() > BIREBIR_KAT_MAX or k.nunique() < 2:
                continue
            skor = k.map(y.groupby(k).mean()).to_numpy(dtype=float)
        a = _auc(skor, y)
        if a is None:
            continue
        a = max(a, 1 - a)
        if a >= e["sizinti_auc"]:
            sonuc.append({"kolon": kol, "auc": a})
    return sonuc


def yakin_kopyalar(df, adaylar, esik=None, haric=()):
    """[{"kalan", "kopyalar", "iliski"}]: birebir ayni olmayan ama neredeyse
    ayni sayisal kolonlar (korelasyon >= yakin_kor) ya da biri otekinin
    sabit kati (birim farki). Aday cifti bos ve sifir sayisi ile olceklenmis
    dagilimi ayni olan kolonlardan; kesin olcum tum satirlarla."""
    e = esik_birlestir(esik)
    haric = set(haric)
    kova = {}
    for kol in adaylar:
        if kol in haric:
            continue
        s = df[kol]
        if not _sayisal_mi(s) or pd.api.types.is_bool_dtype(s):
            continue
        x = pd.to_numeric(s, errors="coerce")
        d = x.dropna()
        if d.nunique() < 3:
            continue
        sd = float(d.std())
        if not sd:
            continue
        z = (d - float(d.mean())) / sd
        q = np.round(np.quantile(z.to_numpy(), [0.1, 0.25, 0.5, 0.75, 0.9]), 1)
        qn = np.round(-q[::-1], 1)
        imza = min(tuple(q.tolist()), tuple(qn.tolist()))
        anahtar = (int(x.isna().sum()), int((x == 0).sum()), imza)
        kova.setdefault(anahtar, []).append(kol)
    sonuc = []
    for uyeler in kova.values():
        if len(uyeler) < 2:
            continue
        kalan = list(uyeler)
        while len(kalan) > 1:
            ilk, digerleri = kalan[0], kalan[1:]
            a = pd.to_numeric(df[ilk], errors="coerce")
            grup, iliski = [], {}
            for k in digerleri:
                b = pd.to_numeric(df[k], errors="coerce")
                ikisi = a.notna() & b.notna()
                if int(ikisi.sum()) < 3:
                    continue
                r = float(np.corrcoef(a[ikisi], b[ikisi])[0, 1])
                if not np.isfinite(r) or abs(r) < e["yakin_kor"]:
                    continue
                grup.append(k)
                sifirsiz = ikisi & (a != 0)
                oran = (b[sifirsiz] / a[sifirsiz]) if sifirsiz.any() else pd.Series(dtype=float)
                if len(oran) and float(oran.std() or 0) <= 1e-9 * max(abs(float(oran.mean())), 1):
                    iliski[k] = {"tur": "kat", "kat": float(oran.mean())}
                else:
                    iliski[k] = {"tur": "kor", "kor": r}
            if grup:
                sonuc.append({"kalan": ilk, "kopyalar": grup, "iliski": iliski})
            kalan = [k for k in digerleri if k not in grup]
    return sonuc


def pencere_tutarliligi(df, ciftler):
    """ciftler: [(kisa, uzun, yon)] - ayni olcunun kisa ve uzun penceresi;
    yon "artan": kisa <= uzun beklenir, "azalan": kisa >= uzun. Doner:
    [{"kolon", "karsi", "yon", "adet", "pay"}]."""
    sonuc = []
    for kisa, uzun, yon in ciftler:
        if kisa not in df.columns or uzun not in df.columns:
            continue
        a = pd.to_numeric(df[kisa], errors="coerce")
        b = pd.to_numeric(df[uzun], errors="coerce")
        ikisi = a.notna() & b.notna()
        tol = 1e-9 * (b.abs() + 1)
        m = ikisi & ((a > b + tol) if yon == "artan" else (a < b - tol))
        adet = int(m.sum())
        if adet:
            sonuc.append({"kolon": kisa, "karsi": uzun, "yon": yon, "adet": adet,
                          "pay": adet / max(int(ikisi.sum()), 1)})
    return sonuc


def tutar_adet_uyumu(df, adet_tutar, maks_ort):
    """adet_tutar: [(adet, tutar)] - adet 0 iken tutar 0 disi ya da adet bos
    iken tutar dolu; maks_ort: [(maks, ort)] - en buyuk ortalamadan kucuk.
    Doner: [{"kolon", "karsi", "tur", "adet", "pay"}]."""
    sonuc = []
    for adet_k, tutar_k in adet_tutar:
        if adet_k not in df.columns or tutar_k not in df.columns:
            continue
        a = pd.to_numeric(df[adet_k], errors="coerce")
        t = pd.to_numeric(df[tutar_k], errors="coerce")
        m = ((a == 0) & t.notna() & (t != 0)) | (a.isna() & t.notna() & (t != 0))
        adet = int(m.sum())
        if adet:
            sonuc.append({"kolon": tutar_k, "karsi": adet_k, "tur": "adet_tutar", "adet": adet,
                          "pay": adet / max(int(t.notna().sum()), 1)})
    for maks_k, ort_k in maks_ort:
        if maks_k not in df.columns or ort_k not in df.columns:
            continue
        mx = pd.to_numeric(df[maks_k], errors="coerce")
        ort = pd.to_numeric(df[ort_k], errors="coerce")
        ikisi = mx.notna() & ort.notna()
        m = ikisi & (mx < ort - 1e-9 * (ort.abs() + 1))
        adet = int(m.sum())
        if adet:
            sonuc.append({"kolon": maks_k, "karsi": ort_k, "tur": "maks_ort", "adet": adet,
                          "pay": adet / max(int(ikisi.sum()), 1)})
    return sonuc
