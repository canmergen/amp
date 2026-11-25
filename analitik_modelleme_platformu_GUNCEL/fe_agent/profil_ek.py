"""02.1 VERI PROFILI EK KONTROLLERI.

sfa.profil_cikar'in dort kontrolune (eksik orani yuksek, sabit, kimlik
benzeri, kardinalite) ek olarak:

  * ayni_icerik   : degerleri satir satir birebir ayni kolonlar
  * baskin        : bir deger satirlarin BASKIN_ESIK'i ya da fazlasinda
  * donem         : kolon bazi donemlerde tamamen bos ya da tek degerli
  * gizli_eksik   : -999, 9999 gibi ozel kod; dagilimin geri kalanindan kopuk
  * negatif       : kolon kartinin olcusu adet, gun, sure iken negatif deger
  * sicrama       : eksik orani art arda iki donem arasinda sicriyor
  * uc            : en buyuk deger %99'luk degeri ya da en kucuk deger %1'lik
                    degeri, (%99'luk - %1'lik) farkinin UC_DEGER_KAT katindan
                    fazla asiyor (iki yonlu; hatali giris)
  * tekrar        : ayni kimlik ve donemle birden fazla satir, tamamen ayni satir
  * hedef         : sinif dagilimi, hedefi bos satir, donem basina sinif paylari

HEPSI TABLONUN TAMAMINDA, KESIN SAYIMLA: orneklem yok, yaklasik sayim yok.
Ek kontroller yalniz dort temel kontrolden gecen (kusurlu olmayan)
kolonlara uygulanir; kusurlu kolonlar zaten degisken uretimine girmez.
"""
import math
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
# TESADUF OLASILIGI (anlamlilik duzeyi): bir bulgunun tesadufen cikma
# olasiligi bunun altindaysa gercek sayilir. Donemde bos ya da sabit
# kontrolu ve baskin degerin Tut / Cikar onerisi bununla karar verir.
TESADUF = 0.05
# UC DEGER (hatali giris, iki yonlu): yayilim = %99'luk - %1'lik.
# Ust: en buyuk > %99'luk + KAT x yayilim; alt: en kucuk < %1'lik - KAT x
# yayilim. Pozitif kolonda (%1'lik ~ 0) ust kural eski "en buyuk >
# 100 x %99'luk" kuralina denk. Ozel kod (gizli eksik) hesaba girmez;
# negatif olamayan olcude alt uc Beklenmeyen Negatif kontrolunde.
UC_DEGER_KAT = 100
UC_DEGER_YUZDELIK = 0.99
UC_DEGER_ALT_YUZDELIK = 0.01
# Kullanicinin 02.1'de onayladigi esikler bu anahtarlarla gelir (yoksa
# varsayilan). Gizli eksik kod listesi ve kopukluk kati sabittir.
SIZINTI_AUC = 0.85
YAKIN_KOR = 0.99
KAYMA_KAT = 10
ONDALIK_BASAMAK = 4
ESIK_VARSAYILAN = {"baskin": BASKIN_ESIK, "gizli": GIZLI_EKSIK_ESIK,
                   "tesaduf": TESADUF, "sicrama": DONEM_SICRAMA_ESIK,
                   "uc_yayilim": UC_DEGER_KAT, "sizinti_auc": SIZINTI_AUC, "yakin_kor": YAKIN_KOR,
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
            kalan = [float(k) for k in sayim.index if float(k) != v]
            kalan_min = min(kalan, default=None)
            if kalan_min is not None and kalan_min < 0:
                continue
            # -1 / 0 / 1 (yon, artti / azaldi) kolonunda -1 gercek degerdir,
            # eksik kodu degil: oteki degerler yalniz 0 ve 1 ise kod sayilmaz.
            if v == -1 and kalan and set(kalan) <= {0.0, 1.0}:
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
    sonuc = {"baskin": [], "gizli_eksik": [], "karisik_eksik": [], "negatif": [],
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
        kod = gizli
        if gizli:
            sonuc["gizli_eksik"].append({"kolon": kol, "deger": deger_metni(gizli[0]),
                                         "adet": gizli[1], "pay": gizli[1] / dolu, "bos": bos})
        elif bos:
            # KARISIK EKSIK KODLAMASI: kolonda bos hucre VAR ve ayni kolonda
            # -1, -99, 9999 gibi kopuk bir ozel kod da var. Payina bakilmaz
            # (tek satir bile olsa): eksik bilgi iki farkli bicimde yazilmis.
            karisik = _gizli_eksik(sayim, dolu, en_kucuk, en_buyuk, 0.0)
            if karisik:
                kod = karisik
                sonuc["karisik_eksik"].append({"kolon": kol, "deger": deger_metni(karisik[0]),
                                               "adet": karisik[1], "pay": karisik[1] / dolu,
                                               "bos": bos})
        # Uc deger (iki yonlu): ozel kod (-999, 9999) hesaba girmez. Kod,
        # Ozel Kod ya da Ozel Kod ve Bos Hucre kuralinda yakalanan deger:
        # ayni deger bir de uc deger ya da negatif sayilmaz.
        su = sn[sn != kod[0]] if kod is not None else sn
        neg_yok = olcu_negatif_olamaz(olculer.get(kol))
        if len(su):
            p1 = float(su.quantile(UC_DEGER_ALT_YUZDELIK))
            p99 = float(su.quantile(UC_DEGER_YUZDELIK))
            yay = p99 - p1
            if yay > 0:
                kat = float(e["uc_yayilim"])
                mx, mn = float(su.max()), float(su.min())
                ust = mx > p99 + kat * yay
                alt = (not neg_yok) and mn < p1 - kat * yay
                if ust or alt:
                    sonuc["uc"].append({"kolon": kol, "maks": mx, "en_kucuk": mn,
                                        "p1": p1, "p99": p99,
                                        "yon": "iki" if (ust and alt) else ("ust" if ust else "alt")})
        if olcu_negatif_olamaz(olculer.get(kol)):
            negatif = sn < 0
            if kod is not None and kod[0] < 0:
                negatif &= sn != kod[0]
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


def sicrama_tesadufi(p1, n1, p2, n2, alfa):
    """Iki donemin bos orani farki sans eseri olabilir mi (iki oran testi)?
    Az satirli donemde bos orani kendiliginden oynar: 10 satirin 3'u ile
    6'si arasindaki 30 puanlik fark sans eseri cikabilir. Farkin sans
    eseri olma ihtimali alfa ya da ustundeyse True (yakalanmaz)."""
    if n1 <= 0 or n2 <= 0:
        return True
    p = (p1 * n1 + p2 * n2) / float(n1 + n2)
    se = math.sqrt(p * (1 - p) * (1.0 / n1 + 1.0 / n2))
    if se <= 0:
        return False
    return math.erfc(abs(p1 - p2) / se / math.sqrt(2)) >= alfa


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
    # COKLU KARSILASTIRMA: ne kadar cok donem sinanirsa sans eseri bir
    # bulgu cikma ihtimali o kadar artar. Sinir sinama sayisina bolunur
    # (Bonferroni): kolon basina yanlis alarm ihtimali tesaduf sinirini
    # asmaz. Bos / sabit: donem sayisi kadar sinama; sicrama: art arda
    # donem cifti kadar.
    alfa_donem = float(e["tesaduf"]) / len(donemler)
    alfa_cift = float(e["tesaduf"]) / (len(donemler) - 1)
    satir = g.value_counts()
    bos_sabit, sicrama = [], []

    def tesadufi_mi(s, d, deger=None):
        """Donem d'de kolonun tamami bos (deger None) ya da tamami `deger`.
        Oteki donemlerde bu durumun payi p ise, d'nin n satirinin hepsinin
        tesadufen boyle cikma olasiligi p^n. Bu olasilik alfa'dan kucukse
        bulgu gercektir (tesadufi degildir)."""
        dis = g.notna() & (g != d)
        if not bool(dis.any()):
            return True
        p = float(s[dis].isna().mean()) if deger is None else float((s[dis] == deger).mean())
        n = int(satir.get(d, 0))
        return (p ** n) >= alfa_donem
    for i in range(0, len(adaylar), DONEM_PARCA):
        parca = list(adaylar[i:i + DONEM_PARCA])
        alt = df[parca]
        bos_oran = alt.isna().groupby(g).mean().reindex(donemler)
        tekil = alt.groupby(g).nunique(dropna=True).reindex(donemler)
        for kol in parca:
            oran = bos_oran[kol]
            bos = [d for d in donemler if float(oran[d]) >= 1.0]
            sabit = [d for d in donemler if float(oran[d]) == 0.0 and int(tekil[kol][d]) == 1]
            # Butun donemlerde ayni tek deger: kolon sabittir, temel kontrol
            # yakalar; burada yalniz donemden doneme degisen kolon.
            if sabit and len(sabit) == len(donemler):
                sabit = []
            if bos or sabit:
                sk = df[kol]
                bos = [d for d in bos if not tesadufi_mi(sk, d)]
                sabit = [d for d in sabit
                         if not tesadufi_mi(sk, d, sk[g == d].dropna().iloc[0])]
            if bos or sabit:
                bos_sabit.append({"kolon": kol, "bos": [deger_metni(d) for d in bos],
                                  "sabit": [deger_metni(d) for d in sabit]})
                continue
            en_iyi = None
            for a, b in zip(donemler, donemler[1:]):
                fark = abs(float(oran[b]) - float(oran[a]))
                if fark > e["sicrama"] and (en_iyi is None or fark > en_iyi[0]) \
                        and not sicrama_tesadufi(float(oran[a]), int(satir.get(a, 0)),
                                                 float(oran[b]), int(satir.get(b, 0)), alfa_cift):
                    en_iyi = (fark, a, b)
            if en_iyi:
                _f, a, b = en_iyi
                sicrama.append({"kolon": kol, "once": deger_metni(a), "sonra": deger_metni(b),
                                "once_oran": float(oran[a]), "sonra_oran": float(oran[b])})
    return [deger_metni(d) for d in donemler], bos_sabit, sicrama


def tekrar_satirlar(df, kimlik=None, donem=None, haric=()):
    """Doner: {"kimlik": fazla satir sayisi ya da None, "anahtar": [kolonlar],
    "tam": tamamen ayni fazla satir sayisi, "toplam": ikisinden en az birine
    takilan fazla satir sayisi (her satir bir kez)}."""
    tam = _tam_tekrar(df, haric)
    sonuc = {"kimlik": None, "anahtar": [], "tam": int(tam.sum()), "toplam": int(tam.sum())}
    if kimlik and kimlik in df.columns:
        anahtar = [kimlik] + ([donem] if donem and donem in df.columns else [])
        anahtar_tekrar = df.duplicated(anahtar)
        sonuc["anahtar"] = anahtar
        sonuc["kimlik"] = int(anahtar_tekrar.sum())
        # Ayni satir iki kez sayilmaz (tamamen ayni satir anahtarda da tekrardir).
        sonuc["toplam"] = int((anahtar_tekrar | tam).sum())
    return sonuc


def _tam_tekrar(df, haric=()):
    """Butun kolonlari ayni olan fazla satirlar (ilk gorulen kalir). haric
    kolonlar (ör. _SPLIT) karsilastirmaya girmez: ayni satir iki sette
    olsa da kopyadir."""
    if not len(df):
        return pd.Series([], dtype=bool, index=df.index)
    kolonlar = [c for c in df.columns if c not in set(haric or ())]
    return df.duplicated(kolonlar) if kolonlar else pd.Series(False, index=df.index)


def tekrar_maskeleri(df, kimlik=None, donem=None, haric=()):
    """SATIR CIKARMA icin tekrar eden satirlarin maskeleri (ilk gorulen
    satir kalir): {"tam": butun kolonlari ayni olan fazla satirlar,
    "anahtar": ayni kimlik (ve donem) icin icerigi FARKLI fazla satirlar}.
    Iki maske ayriktir; kimlik yoksa yalniz "tam"."""
    tam = _tam_tekrar(df, haric)
    cikti = {"tam": tam}
    if kimlik and kimlik in df.columns:
        anahtar = [kimlik] + ([donem] if donem and donem in df.columns else [])
        cikti["anahtar"] = df.duplicated(anahtar) & ~tam
    return cikti


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


# ===========================================================================
# ETKIN BOS: bos hucre + bos YERINE yazilmis deger (-999 gibi ozel kod,
# "bilinmiyor" gibi yazi). Bos oranina bakan butun kurallar (Bos Hucreler,
# donemlerde bos, bos oraninin sicramasi, Train disinda bos) etkin bosa
# bakar; yoksa butun boslari -1 ile doldurulmus bir kolon "hic bos yok"
# gorunur ve hicbir bos kuralina takilmaz.
# ===========================================================================
def etkin_bos_bilgisi(df, kolonlar, esik=None):
    """{kolon: {"bos" (bos hucre orani), "kod" (ozel kod ya da None),
    "metinler" (bos anlamli yazilar), "ek" (kod / yazi satirlarinin orani),
    "etkin" (bos + ek)}}: yalniz ozel kodu ya da bos anlamli yazisi olan
    kolonlar. Ozel kod kolon_kontrolleri ile ayni kuralla (_gizli_eksik;
    bos hucresi de olan kolonda payina bakilmaz)."""
    e = esik_birlestir(esik)
    n = len(df)
    cikti = {}
    if not n:
        return cikti
    for kol in kolonlar:
        if kol not in df.columns:
            continue
        s = df[kol]
        bos = int(s.isna().sum())
        if _sayisal_mi(s) and not pd.api.types.is_bool_dtype(s):
            sn = pd.to_numeric(s, errors="coerce").dropna()
            if not len(sn):
                continue
            sayim = sn.value_counts()
            kod = _gizli_eksik(sayim, len(sn), float(sn.min()), float(sn.max()), e["gizli"])
            if kod is None and bos:
                kod = _gizli_eksik(sayim, len(sn), float(sn.min()), float(sn.max()), 0.0)
            if kod is None:
                continue
            cikti[kol] = {"bos": bos / float(n), "kod": float(kod[0]), "metinler": [],
                          "ek": int(kod[1]) / float(n), "etkin": (bos + int(kod[1])) / float(n)}
        elif _metin_kolonu_mu(s):
            vc = _metin_sayimi(s)
            bul = [(v, int(a)) for v, a in vc.items() if metin_bos_normal(v) in METIN_BOS_DEGERLER]
            if not bul:
                continue
            adet = sum(a for _v, a in bul)
            cikti[kol] = {"bos": bos / float(n), "kod": None, "metinler": [v for v, _a in bul],
                          "ek": adet / float(n), "etkin": (bos + adet) / float(n)}
    return cikti


def etkin_bos_donustur(df, bilgi):
    """df'in kopyasi: bilgi'deki kolonlarda ozel kod ve bos anlamli yazilar
    bos hucreye cevrilir (oteki kolonlara dokunulmaz)."""
    kolonlar = [k for k in (bilgi or {}) if k in df.columns]
    if not kolonlar:
        return df
    yeni = df.copy(deep=False)
    for k in kolonlar:
        v = bilgi[k]
        s = df[k]
        if v.get("kod") is not None:
            sn = pd.to_numeric(s, errors="coerce")
            yeni[k] = s.where(sn != float(v["kod"]))
        elif v.get("metinler"):
            yeni[k] = s.where(~s.isin(set(v["metinler"])))
    return yeni


def ek_kontroller(df, adaylar, donem=None, kimlik=None, hedef=None, olculer=None, esik=None,
                  tarihler=(), hedef_maske=None, satir_haric=()):
    """Butun ek kontroller. adaylar: dort temel kontrolden gecen kolonlar
    (tablodaki sirasiyla)."""
    adaylar = [k for k in adaylar if k in df.columns]
    sonuc = kolon_kontrolleri(df, adaylar, olculer, esik)
    # Ayni icerikli gruplardan hangisinin kalacagi kullanicinin secimine
    # bagli; bulgular her uye icin hesaplanir, gosterirken kopyalar elenir.
    sonuc["ayni_icerik"] = ayni_icerik(df, adaylar)
    baskin = {x["kolon"] for x in sonuc["baskin"]}
    # DONEM KURALLARI ETKIN BOSA BAKAR: ozel kod ve bos anlamli yazi bos
    # sayilir (kod payi donemle degisiyorsa bos orani degisiyor demektir;
    # kod sayi olarak kalirsa tipik degerleri de kaydirir).
    sonuc["etkin_bos"] = etkin_bos_bilgisi(df, adaylar, esik)
    df_ham, df = df, etkin_bos_donustur(df, sonuc["etkin_bos"])
    donemler, bos_sabit, sicrama = donem_kontrolleri(
        df, [k for k in adaylar if k not in baskin], donem, esik)
    sonuc["donemler"] = donemler
    sonuc["donem"] = bos_sabit
    sonuc["sicrama"] = sicrama
    sonuc["kayma"] = deger_kaymasi(df, [k for k in adaylar if k not in baskin], donem, esik)
    df = df_ham                         # geri kalan kontroller ham degerlerle
    sonuc["tekrar"] = tekrar_satirlar(df, kimlik, donem, haric=satir_haric)
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
    # Hedefle birebir: hedef YALNIZ TRAIN satirlarinda (hedef_maske); val
    # ve test hedefi karara karismaz. Maske yoksa butun satirlar.
    sonuc["birebir"] = hedef_birebir(df[hedef_maske] if hedef_maske is not None else df,
                                     adaylar, hedef, esik)
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
    "belirtilmemiş", "belirtilmemis", "tanımsız", "tanimsiz",
    # "yok" tek basina alinmaz: var / yok gercek bir degerdir.
    "unknown", "missing", "not available", "bilgi yok", "veri yok", "kayıt yok",
    "kayit yok", "girilmemiş", "girilmemis", "mevcut değil", "mevcut degil"))
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
# Gun.ay.yil yazilisi (31.12.2024); yil sondaki dort hane.
_TARIH_METIN_GAY = re.compile(r"^\s*\d{2}\.\d{2}\.(\d{4})")
# Sayi olarak yazilmis tarih (YYYYAAGG): dolu degerlerin en az bu kadari
# gecerli bir takvim gunu olmali (8 haneli kimlik numarasi tarih sanilmasin).
TARIH_SAYI_GECERLI = 0.99


def _sayi_tarih_gecerli(v):
    import datetime as _dt
    try:
        v = int(v)
        _dt.date(v // 10000, (v // 100) % 100, v % 100)
        return True
    except (ValueError, OverflowError, TypeError):
        return False


def tarih_turu(s):
    """Kolon tarih mi: "tip" (tarih tipinde), "metin" (dolu degerlerin
    cogu YYYY-AA-GG), "metin_gay" (cogu GG.AA.YYYY), "sayi" (YYYYAAGG
    sekiz haneli tam sayi) ya da None."""
    if pd.api.types.is_datetime64_any_dtype(s):
        return "tip"
    if pd.api.types.is_bool_dtype(s):
        return None
    if pd.api.types.is_numeric_dtype(s):
        d = pd.to_numeric(s, errors="coerce").dropna()
        if not len(d) or float(d.min()) < 10000101 or float(d.max()) > 99991231:
            return None
        if not bool((d == d.round()).all()):
            return None
        tekil = pd.unique(d.astype("int64"))
        gecerli = sum(1 for v in tekil if _sayi_tarih_gecerli(v))
        return "sayi" if gecerli >= TARIH_SAYI_GECERLI * len(tekil) else None
    vc = _metin_sayimi(s)
    if not len(vc):
        return None
    iso = sum(1 for v in vc.index if _TARIH_METIN.match(str(v)))
    if iso >= 0.8 * len(vc):
        return "metin"
    gay = sum(1 for v in vc.index if _TARIH_METIN_GAY.match(str(v)))
    return "metin_gay" if gay >= 0.8 * len(vc) else None


def _tarih_yili(s, tur):
    """Her hucrenin yili (cevrilemeyen NaN); kod tarihler dahil."""
    if tur == "tip":
        return s.dt.year.astype("float64")
    if tur == "sayi":
        return (pd.to_numeric(s, errors="coerce") // 10000).astype("float64")
    desen = _TARIH_METIN_GAY.pattern if tur == "metin_gay" else _TARIH_METIN.pattern
    return pd.to_numeric(s.astype(str).str.extract(desen)[0],
                         errors="coerce").where(s.notna())


def tarih_serisi(s, tur=None):
    """Kolonu tarih serisine cevirir (tip, metin YYYY-AA-GG ya da
    GG.AA.YYYY, sayi YYYYAAGG); tarih degilse None. Ozel tarih kodlari (yil 1901'den once
    ya da 2200'den sonra) bos (NaT) doner."""
    tur = tur or tarih_turu(s)
    if tur is None:
        return None
    if tur == "tip":
        t = s
        try:
            if getattr(t.dt, "tz", None) is not None:
                t = t.dt.tz_localize(None)
        except Exception:
            pass
    elif tur == "sayi":
        d = pd.to_numeric(s, errors="coerce")
        metin = d.dropna().astype("int64").astype(str)
        t = pd.to_datetime(metin, format="%Y%m%d", errors="coerce").reindex(s.index)
    else:
        t = pd.to_datetime(s.where(s.notna()).astype(str).str.strip().str[:10],
                           format="%d.%m.%Y" if tur == "metin_gay" else "%Y-%m-%d",
                           errors="coerce")
    yil = _tarih_yili(s, tur)
    kod = (yil < TARIH_YIL_ALT) | (yil > TARIH_YIL_UST)
    return pd.to_datetime(t, errors="coerce").where(~kod.fillna(False))


def _tarih_kodlu(s, tur=None):
    """Ozel tarih kodu olan hucrelerin maskesi; tarih kolonu degilse None."""
    tur = tur or tarih_turu(s)
    if tur is None:
        return None
    yil = _tarih_yili(s, tur)
    return ((yil < TARIH_YIL_ALT) | (yil > TARIH_YIL_UST)).fillna(False)


def tarih_kod_kontrol(df, adaylar):
    """([{"kolon", "degerler": [{"deger", "adet"}], "adet", "pay"}], tarih
    kolonu sayisi): tarih kolonunda 1900-01-01, 9999-12-31 gibi kod
    tarihler."""
    sonuc, tarih = [], 0
    for kol in adaylar:
        s = df[kol]
        tur = tarih_turu(s)
        m = _tarih_kodlu(s, tur) if tur is not None else None
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
        t = tarih_serisi(df[kol])          # kod tarihler bos (sayilmaz)
        if t is None:
            continue
        m = t.notna() & son.notna() & (t > son)
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


def set_cakismasi(df, setler, kimlik=None, donem=None, haric=()):
    """Train (MS) ile val, test ve OOT setleri arasindaki cakisma (01.4
    bolmesi). setler: {"egitim", "val", "test", "oot": bool Series}. Doner:
    {"setler": {ad: satir}, "cakisma": [{"set", "tur", "kimlik", "satir",
    "pay"}]} ya da Train yoksa None. tur: "kimlik" (ayni kimlik Train'de
    de var), "anahtar" (ayni kimlik ve donem Train'de de var), "tam" (butun
    kolonlari ayni satir Train'de de var; haric kolonlar, ör. _SPLIT,
    karsilastirmaya girmez). Butun satirlar, kesin sayim (tam satir 64
    bitlik satir ozetiyle)."""
    eg = setler.get("egitim")
    if eg is None or not bool(pd.Series(eg).any()):
        return None
    eg = pd.Series(eg, index=df.index).fillna(False).astype(bool)
    diger = {}
    for ad in ("val", "test", "oot"):
        m = setler.get(ad)
        if m is None:
            continue
        m = pd.Series(m, index=df.index).fillna(False).astype(bool) & ~eg
        if bool(m.any()):
            diger[ad] = m
    # test ve oot ayni satirlari gosterebilir (rastgele bolmede); bir kez.
    if "test" in diger and "oot" in diger and bool((diger["test"] == diger["oot"]).all()):
        diger.pop("oot")
    sonuc = {"setler": {"egitim": int(eg.sum())}, "cakisma": []}
    sonuc["setler"].update({a: int(m.sum()) for a, m in diger.items()})
    if not diger:
        return sonuc
    kimlik_var = bool(kimlik) and kimlik in df.columns
    anahtar = ([kimlik] + ([donem] if donem and donem in df.columns else [])) if kimlik_var else []
    kolonlar = [c for c in df.columns if c not in set(haric)]
    ozet = pd.util.hash_pandas_object(df[kolonlar], index=False) if kolonlar else None
    tr_ozet = set(ozet[eg].tolist()) if ozet is not None else set()
    if kimlik_var:
        tr_kimlik = set(df.loc[eg, kimlik].dropna().tolist())
        if len(anahtar) > 1:
            tr_anahtar = set(map(tuple, df.loc[eg, anahtar].dropna().itertuples(index=False,
                                                                               name=None)))
    for ad, m in diger.items():
        n = int(m.sum())
        if kimlik_var:
            k = df.loc[m, kimlik]
            ortak = k.isin(tr_kimlik)
            if bool(ortak.any()):
                sonuc["cakisma"].append({"set": ad, "tur": "kimlik",
                                         "kimlik": int(k[ortak].nunique()),
                                         "satir": int(ortak.sum()), "pay": int(ortak.sum()) / n})
            if len(anahtar) > 1:
                cift = pd.Series([tuple(x) in tr_anahtar for x in
                                  df.loc[m, anahtar].itertuples(index=False, name=None)],
                                 index=k.index)
                if bool(cift.any()):
                    sonuc["cakisma"].append({"set": ad, "tur": "anahtar",
                                             "kimlik": int(k[cift].nunique()),
                                             "satir": int(cift.sum()), "pay": int(cift.sum()) / n})
        if ozet is not None:
            tam = ozet[m].isin(tr_ozet)
            if bool(tam.any()):
                sonuc["cakisma"].append({"set": ad, "tur": "tam", "kimlik": None,
                                         "satir": int(tam.sum()), "pay": int(tam.sum()) / n})
    return sonuc



def set_disi_bozulma(df, setler, adaylar, esik=None, etkin_bos=None):
    """[{"kolon", "set", "tur", "train_oran", "set_oran", "deger"}]: TRAIN'de
    saglam gorunup Train disindaki bir sette (val, test, oot) bozuk olan
    kolonlar. Kontroller train'de yapildigi icin bu durum baska hicbir
    kuralda gorunmez; model o kolonu sinamada / canlida bozuk gorur.
      tur "bos": sette tamamen bos (train'de degil)
      tur "sabit": sette hep ayni deger (train'de birden fazla deger)
      tur "bos_fark": bos orani train'e gore sicrama esiginden fazla farkli
    Az satirli sette bu sans eseri olabilir: sans eseri olma ihtimali
    tesaduf sinirinin (sinanan set sayisina bolunmus) altindaysa bulgu.
    Kolon ve set basina tek bulgu (once bos, sonra sabit, sonra fark)."""
    e = esik_birlestir(esik)
    # ETKIN BOS: Train'de bulunan ozel kod / bos anlamli yazi bos sayilir
    # (etkin_bos: etkin_bos_bilgisi ciktisi).
    df = etkin_bos_donustur(df, etkin_bos)
    eg = setler.get("egitim")
    if eg is None:
        return []
    eg = pd.Series(eg, index=df.index).fillna(False).astype(bool)
    if not bool(eg.any()):
        return []
    diger = {}
    for ad in ("val", "test", "oot"):
        m = setler.get(ad)
        if m is None:
            continue
        m = pd.Series(m, index=df.index).fillna(False).astype(bool) & ~eg
        if bool(m.any()):
            diger[ad] = m
    if "test" in diger and "oot" in diger and bool((diger["test"] == diger["oot"]).all()):
        diger.pop("oot")
    if not diger:
        return []
    alfa = float(e["tesaduf"]) / len(diger)
    n_tr = int(eg.sum())
    sonuc = []
    for kol in adaylar:
        if kol not in df.columns:
            continue
        s_ = df[kol]
        tr = s_[eg]
        p_bos = float(tr.isna().mean())
        tr_dolu = tr.dropna()
        tr_tekil = int(tr_dolu.nunique())
        for ad, m in diger.items():
            x = s_[m]
            n = int(len(x))
            oran = float(x.isna().mean())
            if oran >= 1.0:
                if p_bos < 1.0 and (p_bos ** n) < alfa:
                    sonuc.append({"kolon": kol, "set": ad, "tur": "bos", "train_oran": p_bos,
                                  "set_oran": oran, "deger": None})
                continue
            dolu = x.dropna()
            if oran == 0.0 and int(dolu.nunique()) == 1 and tr_tekil > 1:
                deger = dolu.iloc[0]
                p = float((tr == deger).mean())
                if (p ** n) < alfa:
                    sonuc.append({"kolon": kol, "set": ad, "tur": "sabit", "train_oran": p_bos,
                                  "set_oran": oran, "deger": deger_metni(deger)})
                    continue
            if abs(oran - p_bos) > e["sicrama"] and not sicrama_tesadufi(p_bos, n_tr, oran, n, alfa):
                sonuc.append({"kolon": kol, "set": ad, "tur": "bos_fark", "train_oran": p_bos,
                              "set_oran": oran, "deger": None})
    return sonuc


def _train_disi_setler(df, setler):
    """(train maskesi, {set: maske}): Train disindaki dolu setler (val,
    test, oot); test ile oot ayni satirlarsa tek set. Train yoksa (None, {})."""
    eg = setler.get("egitim")
    if eg is None:
        return None, {}
    eg = pd.Series(eg, index=df.index).fillna(False).astype(bool)
    if not bool(eg.any()):
        return None, {}
    diger = {}
    for ad in ("val", "test", "oot"):
        m = setler.get(ad)
        if m is None:
            continue
        m = pd.Series(m, index=df.index).fillna(False).astype(bool) & ~eg
        if bool(m.any()):
            diger[ad] = m
    if "test" in diger and "oot" in diger and bool((diger["test"] == diger["oot"]).all()):
        diger.pop("oot")
    return eg, diger


def set_disi_deger(df, setler, adaylar, esik=None, olculer=None):
    """Train'de GORULMEYEN ama Train disindaki bir sette (val, test, oot)
    gorulen DEGER sorunlari. Kontroller train'de yapildigi icin bunlar
    baska hicbir kuralda cikmaz. Doner {"kod": [...], "uc": [...],
    "kayma": [...]}; her bulgu "set" tasir.
      kod  : sette bos yerine yazilmis ozel kod (-999 gibi); train'de bu
             kod yok ya da gizli esiginin altinda. Bicim gizli_eksik ile
             ayni (kolon, deger, adet, pay, bos): ayni duzeltme uygulanir.
      uc   : sette, train'in normal araliginin (p1 - kat x yayilim,
             p99 + kat x yayilim) disinda deger; train'de boyle deger yok.
             Bicim uc ile ayni (maks, en_kucuk, p1, p99, yon); p1 / p99
             train'den, maks / en_kucuk setten.
      kayma: sifir disi mutlak degerlerin %25, %50, %75'i train ile set
             arasinda ayni yonde en az kayma_kat kat farkli (birim
             degisikligi gibi). Bicim set_disi ile ayni (tur "kayma").
    Kod payi az satirli sette sans eseri olabilir: iki oran testi, sinir
    sinanan set sayisina bolunur. Kolon ve set basina tek bulgu (once kod,
    sonra uc, sonra kayma)."""
    e = esik_birlestir(esik)
    sonuc = {"kod": [], "uc": [], "kayma": []}
    eg, diger = _train_disi_setler(df, setler)
    if not diger:
        return sonuc
    alfa = float(e["tesaduf"]) / len(diger)
    olculer = olculer or {}
    kat = float(e["uc_yayilim"])
    for kol in adaylar:
        if kol not in df.columns:
            continue
        s_ = df[kol]
        if not _sayisal_mi(s_) or pd.api.types.is_bool_dtype(s_):
            continue
        sn = pd.to_numeric(s_, errors="coerce")
        trn = sn[eg].dropna()
        if not len(trn):
            continue
        # Train'in kendi ozel kodu (varsa) aralik hesabina girmez.
        tr_kod = _gizli_eksik(trn.value_counts(), len(trn), float(trn.min()), float(trn.max()),
                              e["gizli"])
        tsu = trn[trn != tr_kod[0]] if tr_kod is not None else trn
        if not len(tsu):
            continue
        p1, p99 = float(tsu.quantile(UC_DEGER_ALT_YUZDELIK)), float(tsu.quantile(UC_DEGER_YUZDELIK))
        yay = p99 - p1
        tr_mx, tr_mn = float(tsu.max()), float(tsu.min())
        neg_yok = olcu_negatif_olamaz(olculer.get(kol))
        ta = tsu.abs()
        ta = ta[ta != 0]
        for ad, m in diger.items():
            x = sn[m].dropna()
            if not len(x):
                continue
            # 1) OZEL KOD: sette var, train'de yok / esigin altinda.
            kod = _gizli_eksik(x.value_counts(), len(x), float(x.min()), float(x.max()), e["gizli"])
            if kod is not None and (tr_kod is None or tr_kod[0] != kod[0]):
                p_tr = float((trn == kod[0]).mean())
                p_set = kod[1] / float(len(x))
                if p_tr <= e["gizli"] and not sicrama_tesadufi(p_tr, len(trn), p_set, len(x), alfa):
                    sonuc["kod"].append({"kolon": kol, "deger": deger_metni(kod[0]), "adet": int(kod[1]),
                                         "pay": p_set, "bos": int(s_[m].isna().sum()), "set": ad,
                                         "train_pay": p_tr})
                    continue
            xs = x[x != kod[0]] if kod is not None else x
            if not len(xs):
                continue
            # 2) DEV DEGER: train'in normal araliginin cok disinda; train'in
            # kendisinde boyle deger yok (olsaydi Asiri Degerler yakalardi).
            if yay > 0:
                ust_s, alt_s = p99 + kat * yay, p1 - kat * yay
                mx, mn = float(xs.max()), float(xs.min())
                ust = mx > ust_s and tr_mx <= ust_s
                alt = (not neg_yok) and mn < alt_s and tr_mn >= alt_s
                if ust or alt:
                    sonuc["uc"].append({"kolon": kol, "maks": mx, "en_kucuk": mn, "p1": p1, "p99": p99,
                                        "yon": "iki" if (ust and alt) else ("ust" if ust else "alt"),
                                        "set": ad,
                                        "adet": int(((xs > ust_s) if ust else (xs < alt_s)).sum())})
                    continue
            # 3) DAGILIM KAYMASI (birim degisikligi gibi): uc ceyreklik de
            # ayni yonde en az kayma_kat kat.
            xa = xs.abs()
            xa = xa[xa != 0]
            if len(ta) < KAYMA_MIN_SATIR or len(xa) < KAYMA_MIN_SATIR:
                continue
            oranlar = []
            for qq in (0.25, 0.5, 0.75):
                a1, a2 = float(ta.quantile(qq)), float(xa.quantile(qq))
                if not (a1 > 0 and a2 > 0):
                    break
                oranlar.append(a2 / a1)
            if len(oranlar) < 3:
                continue
            if all(o > 1 for o in oranlar):
                k_ = min(oranlar)
            elif all(o < 1 for o in oranlar):
                k_ = 1.0 / max(oranlar)
            else:
                continue
            if k_ >= e["kayma_kat"]:
                sonuc["kayma"].append({"kolon": kol, "set": ad, "tur": "kayma", "kat": k_,
                                       "train_deger": float(ta.quantile(0.5)),
                                       "set_deger": float(xa.quantile(0.5)),
                                       "train_oran": float(s_[eg].isna().mean()),
                                       "set_oran": float(s_[m].isna().mean()), "deger": None})
    return sonuc


def set_cakisma_maskeleri(df, setler, kimlik=None, donem=None, haric=()):
    """SATIR CIKARMA icin: {(set, tur): bool Series} - Train disindaki
    sette (val, test, oot) Train'de de bulunan AYNI KAYIT. tur "anahtar":
    ayni kimlik ve donem; "tam": butun kolonlari ayni satir (haric
    kolonlar karsilastirmaya girmez). Yalniz kimligi ortak olan satir
    (ayni musteri, baska donem) ayni kayit degildir, maskeye girmez.
    Sayimlar set_cakismasi ile aynidir."""
    eg = setler.get("egitim")
    if eg is None or not bool(pd.Series(eg).any()):
        return {}
    eg = pd.Series(eg, index=df.index).fillna(False).astype(bool)
    diger = {}
    for ad in ("val", "test", "oot"):
        m = setler.get(ad)
        if m is None:
            continue
        m = pd.Series(m, index=df.index).fillna(False).astype(bool) & ~eg
        if bool(m.any()):
            diger[ad] = m
    if "test" in diger and "oot" in diger and bool((diger["test"] == diger["oot"]).all()):
        diger.pop("oot")
    cikti = {}
    kimlik_var = bool(kimlik) and kimlik in df.columns
    anahtar = ([kimlik] + [donem]) if kimlik_var and donem and donem in df.columns else []
    kolonlar = [c for c in df.columns if c not in set(haric)]
    ozet = pd.util.hash_pandas_object(df[kolonlar], index=False) if kolonlar else None
    tr_ozet = set(ozet[eg].tolist()) if ozet is not None else set()
    tr_anahtar = set(map(tuple, df.loc[eg, anahtar].dropna().itertuples(index=False, name=None))) \
        if anahtar else set()
    for ad, m in diger.items():
        if anahtar:
            cift = pd.Series([tuple(x) in tr_anahtar for x in
                              df.loc[m, anahtar].itertuples(index=False, name=None)],
                             index=df.index[m.to_numpy()])
            cikti[(ad, "anahtar")] = cift.reindex(df.index, fill_value=False)
        if ozet is not None:
            cikti[(ad, "tam")] = (m & ozet.isin(tr_ozet))
    return cikti


# Ondalik hassasiyeti: bir kolonda en cok bu kadar basamak (kucuk degerli
# kolonda bile).
ONDALIK_EN_COK = 12
# Kucuk degerli kolonda sifir disi kucuk degerlerin (%1'lik deger)
# korunacak anlamli hanesi (0,000012345 -> 0,000012).
ONDALIK_ANLAMLI = 2


def ondalik_basamagi(x, basamak):
    """Kolonun yuvarlanacagi basamak: en az `basamak`; kucuk degerli
    kolonda sifir disi mutlak degerlerin %1'lik degerinin ilk
    ONDALIK_ANLAMLI hanesi korunacak kadar (tek bir cok kucuk deger butun
    kolonu etkilemesin; en cok ONDALIK_EN_COK). Ör. %1'lik deger 0,0123
    ise 3 basamak yeter, esik 4 ise 4; 0,0000093 ise 7 basamak (0,0000093)."""
    a = x.abs()
    a = a[(a > 0) & np.isfinite(a)]
    if not len(a):
        return int(basamak)
    kucuk = float(np.quantile(a.to_numpy(dtype=float), 0.01))
    gerek = ONDALIK_ANLAMLI - 1 - int(np.floor(np.log10(kucuk)))
    return int(min(max(int(basamak), gerek), ONDALIK_EN_COK))


def ondalik_kontrol(df, adaylar, basamak=ONDALIK_BASAMAK):
    """[{"kolon", "tur": "tam" | "uzun", "basamak", "ornek", "ornek_yeni"}]:
    ondalik (float) tipteki kolonlar. "tam": bos hucresi yok ve butun
    degerleri tam sayi (12.0) -> tam sayi tipine cevrilebilir. "uzun":
    degerlerin en az biri `basamak`tan fazla ondalik hane tasiyor ->
    yuvarlanabilir. Butun satirlar, kesin."""
    sonuc = []
    for kol in adaylar:
        s = df[kol]
        if not pd.api.types.is_float_dtype(s):
            continue
        d = s.dropna()
        d = d[np.isfinite(d)]
        if not len(d):
            continue
        tam = d == np.floor(d)
        if bool(tam.all()):
            if len(d) == len(s):
                ornek = float(d.iloc[0])
                sonuc.append({"kolon": kol, "tur": "tam", "basamak": 0,
                              "ornek": ornek, "ornek_yeni": int(ornek)})
            continue
        b = ondalik_basamagi(d, basamak)
        degisen = d.round(b) != d
        if bool(degisen.any()):
            v = float(d[degisen].iloc[0])
            sonuc.append({"kolon": kol, "tur": "uzun", "basamak": b,
                          "ornek": v, "ornek_yeni": round(v, b)})
    return sonuc
