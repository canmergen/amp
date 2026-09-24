# -*- coding: utf-8 -*-
"""fe_agent/sfa.py — veri profili, tek degisken analizi ve stabilite.

Uc ayri fonksiyon, uc ayri kavram:
  profil_cikar()      -> dataset seviyesi: null, unique, cardinality, tip
  sfa_calistir()      -> degisken-hedef iliskisi: IV, C-value
  stabilite_calistir()-> zaman icinde kayma: PSI

SFA bir ELEME kurali DEGILDIR. FAIL alan degisken cok degiskenli modelde
anlamli olabilir; burada yalnizca tek degiskenli guc raporlanir.
"""

import numpy as np
import pandas as pd

IV_ESIK = 0.05
C_ESIK = 0.55
PSI_ESIK = 0.10

NULL_ESIK = 0.50
BIN_SAYISI = 10
KATEGORIK_MAX = 50
MIN_SATIR = 100
SIZINTI_ESIK = 0.95
MIN_BIN = 3              # bu sayinin altina dusen binlemede IV guvenilmez
NULL_BIN = "__EKSIK__"   # PSI'da eksik degerin kendi bin'i
OOF_KAT = 5              # kategorik hedef orani kodlamasi icin fold sayisi


# ===========================================================================
# TEMEL METRIKLER
# ===========================================================================
def _c_value(s, y):
    """Tek degisken AUC (Mann-Whitney rank formu, dongusuz).
    0.5 altina duserse 1'e tamamlanir: yon degil, guc olculuyor."""
    m = s.notna() & y.notna()
    if int(m.sum()) < MIN_SATIR:
        return None
    x, t = s[m], y[m]
    n1 = float((t > 0).sum())
    n0 = float((t <= 0).sum())
    if n1 == 0 or n0 == 0:
        return None
    r = x.rank()
    auc = (float(r[t > 0].sum()) - n1 * (n1 + 1) / 2.0) / (n1 * n0)
    return max(auc, 1.0 - auc)


LAPLACE = 0.5           # sifir hucre icin ekleme (hem paya hem paydaya)

# PSI'da sifir payli hucre icin alt sinir. Duzeltme olmadan log(0)
# tanimsiz, PSI sonsuz olurdu. Adlandirilmis sabit: dokuman bu degeri
# KODDAN okuyup yaziyor, iki yerde elle tutulan bir sayi olmasin.
SIFIR_ORAN_TABAN = 0.0001


def _iv_gruplu(gruplar, y):
    df = pd.DataFrame({"g": gruplar, "y": y}).dropna()
    if len(df) < MIN_SATIR:
        return None
    kotu_t = float((df["y"] > 0).sum())
    iyi_t = float((df["y"] <= 0).sum())
    if kotu_t == 0 or iyi_t == 0:
        return None

    alt_gruplar = list(df.groupby("g", observed=False))
    k = float(len(alt_gruplar))
    if k < 1:
        return None

    # Laplace duzeltmesi: her hucreye LAPLACE eklenir, paydalar da ayni
    # miktarda buyur. Boylece paylar toplami 1 kalir ve sifir hucre
    # duzeltmesi orneklem buyuklugunden bagimsiz tutarli davranir.
    kotu_payda = kotu_t + LAPLACE * k
    iyi_payda = iyi_t + LAPLACE * k

    iv = 0.0
    for _, alt in alt_gruplar:
        kotu = float((alt["y"] > 0).sum())
        iyi = float((alt["y"] <= 0).sum())
        p_kotu = (kotu + LAPLACE) / kotu_payda
        p_iyi = (iyi + LAPLACE) / iyi_payda
        iv += (p_kotu - p_iyi) * np.log(p_kotu / p_iyi)
    return float(iv)


def _binle(s, bin_sayisi=BIN_SAYISI, ogren_maske=None):
    """Bin sinirlari ogren_maske (train) uzerinden ogrenilir, TUM satirlara
    uygulanir. Doner: (gruplar, gerceklesen_bin_sayisi); basarisizsa (None, 0).

    duplicates="drop" ya da yigilmis dagilim yuzunden gerceklesen bin sayisi
    istenenden az olabilir; cagiran taraf bu sayiyi raporlar."""
    if ogren_maske is None:
        ogren = s
    else:
        ogren = s[ogren_maske]
    ogren = pd.to_numeric(ogren, errors="coerce").dropna()
    if len(ogren) < 2:
        return None, 0
    try:
        sinirlar = np.unique(np.nanpercentile(
            ogren, np.linspace(0, 100, bin_sayisi + 1)))
    except Exception:
        return None, 0
    if len(sinirlar) < 2:
        return None, 0
    sinirlar = np.asarray(sinirlar, dtype=float)
    sinirlar[0], sinirlar[-1] = -np.inf, np.inf
    try:
        gruplar = pd.cut(pd.to_numeric(s, errors="coerce"),
                         sinirlar, labels=False, include_lowest=True)
    except Exception:
        return None, 0
    return gruplar, int(len(sinirlar) - 1)


def _oof_hedef_orani(sk, y, tr_index, kat_sayisi=OOF_KAT, seed=42):
    """Kategorik hedef-orani kodlamasi, train icinde OUT-OF-FOLD.

    Her satirin kodu, o satirin DISINDA kalan fold'lardan ogrenilir; boylece
    kodlama ile olcum ayni satirlarda yapilmaz ve C-value sismez.
    Doner: tr_index ile hizali Series (kodlanmis deger)."""
    tr_index = pd.Index(tr_index)
    n = len(tr_index)
    if n < MIN_SATIR:
        return pd.Series(np.nan, index=tr_index, dtype=float)

    sk_tr = sk.loc[tr_index].astype(str)
    y_tr = pd.to_numeric(y.loc[tr_index], errors="coerce")

    k = max(2, min(int(kat_sayisi), n))
    rng = np.random.RandomState(seed)
    fold = rng.permutation(n) % k

    kod = pd.Series(np.nan, index=tr_index, dtype=float)
    genel = float(y_tr.mean()) if y_tr.notna().any() else np.nan
    for f in range(k):
        dis = fold != f          # ogrenme (diger fold'lar)
        ic = fold == f           # olcum (bu fold)
        if not dis.any() or not ic.any():
            continue
        oran = pd.DataFrame(
            {"k": sk_tr[dis], "y": y_tr[dis]}).groupby("k")["y"].mean()
        dis_genel = float(y_tr[dis].mean()) if y_tr[dis].notna().any() else genel
        # Fold'da gorulmeyen seviye -> ogrenme fold'larinin genel ortalamasi
        kod.loc[tr_index[ic]] = pd.to_numeric(
            sk_tr[ic].map(oran), errors="coerce").fillna(dis_genel).values
    return kod


def _psi(dev, oot, kategorik=False):
    """Population Stability Index. Sinirlar GELISTIRME setinden cikarilir.

    Eksik deger AYRI bir bin'dir ve paylar TUM satir sayisi uzerinden
    normalize edilir; boylece null oranindaki kayma PSI'ya girer."""
    if dev is None or oot is None:
        return None
    # Yeterlilik kontrolu dolu satirlar uzerinden yapilir (sinirlar da oyle)
    if int(dev.notna().sum()) < MIN_SATIR or int(oot.notna().sum()) < MIN_SATIR:
        return None

    n_dev = float(len(dev))
    n_oot = float(len(oot))
    if n_dev <= 0 or n_oot <= 0:
        return None

    if kategorik:
        d = dev.where(dev.notna(), NULL_BIN).astype(str).value_counts()
        o = oot.where(oot.notna(), NULL_BIN).astype(str).value_counts()
        etiketler = list(set(d.index) | set(o.index))
        bek = {k: float(d.get(k, 0.0)) / n_dev for k in etiketler}
        ger = {k: float(o.get(k, 0.0)) / n_oot for k in etiketler}
    else:
        try:
            sinirlar = np.unique(np.nanpercentile(
                dev.dropna(), np.linspace(0, 100, BIN_SAYISI + 1)))
        except Exception:
            return None
        if len(sinirlar) < 3:
            return None
        sinirlar = np.asarray(sinirlar, dtype=float)
        sinirlar[0], sinirlar[-1] = -np.inf, np.inf
        d = pd.cut(dev, sinirlar).value_counts(sort=False)
        o = pd.cut(oot, sinirlar).value_counts(sort=False)
        etiketler = list(d.index)
        # Payda = TUM satirlar (NaN dahil), bolunen = bin'deki satir sayisi
        bek = {k: float(d.get(k, 0.0)) / n_dev for k in etiketler}
        ger = {k: float(o.get(k, 0.0)) / n_oot for k in etiketler}
        # Eksik deger ayri bin
        etiketler.append(NULL_BIN)
        bek[NULL_BIN] = float(dev.isna().sum()) / n_dev
        ger[NULL_BIN] = float(oot.isna().sum()) / n_oot

    psi = 0.0
    for k in etiketler:
        e = max(bek[k], SIFIR_ORAN_TABAN)
        g = max(ger[k], SIFIR_ORAN_TABAN)
        psi += (g - e) * np.log(g / e)
    return float(psi)

def _ondalikli(s):
    """Seri ondalikli sayi mi? (kimlik olamayacak kadar 'surekli' mi?)

    float dtype tek basina yetmez: tamsayi degerler float olarak da
    saklanabiliyor. Gercekten ondalik kismi olan bir deger ariyoruz.
    """
    if not pd.api.types.is_float_dtype(s):
        return False
    d = s.dropna()
    if d.empty:
        return False
    try:
        return bool((d != d.round()).any())
    except Exception:
        return False


# ===========================================================================
# 1) VERI PROFILI VE KALITE  (dataset seviyesi, hedef iliskisi YOK)
# ===========================================================================
def profil_cikar(df, haric=(), null_esik=NULL_ESIK):
    """Doner: (tablo, teshis)"""
    haric = set(h for h in haric if h)
    satir = float(len(df))

    kayitlar = []
    cok_bos, sabit, kimlik_gibi, yuksek_kardinalite = [], [], [], []

    for kol in df.columns:
        if kol in haric:
            continue
        s = df[kol]
        null_adet = int(s.isna().sum())
        null_oran = null_adet / max(satir, 1.0)
        tekil = int(s.nunique(dropna=True))
        kard_oran = tekil / max(satir, 1.0)
        sayisal = pd.api.types.is_numeric_dtype(s)

        # Teshisler birbirini DISLAMAZ: bir kolon hem asiri null hem sabit
        # olabilir. Hepsi toplanir, hicbiri digerini maskelemez.
        teshisler = []
        if null_oran > null_esik:
            cok_bos.append(kol); teshisler.append("aşırı null")
        if tekil <= 1:
            sabit.append(kol); teshisler.append("sabit")
        # Kimlik benzeri: yuksek tekillik TEK BASINA yetmez. Yuvarlanmamis
        # para alanlari (gelir, bakiye, islem tutari) dogal olarak ~%100
        # tekildir; bunlari kimlik sanip modelden dusurmek kredi riski
        # modelinde dogrudan performans kaybidir. Gercek kimlikler metin
        # ya da tam sayidir, ondalikli degildir.
        if kard_oran > 0.95 and tekil > MIN_SATIR and not _ondalikli(s):
            kimlik_gibi.append(kol); teshisler.append("kimlik benzeri")
        if (not sayisal) and tekil > KATEGORIK_MAX:
            yuksek_kardinalite.append(kol); teshisler.append("yüksek kardinalite")
        durum = " + ".join(teshisler) if teshisler else "OK"

        if sayisal:
            sn = pd.to_numeric(s, errors="coerce")
            enk, enb = sn.min(), sn.max()
        else:
            enk = enb = None

        kayitlar.append({
            "FEATURE": kol,
            "TYPE": "numeric" if sayisal else "categorical",
            "NULL_COUNT": null_adet,
            "NULL_RATIO": round(null_oran, 4),
            "UNIQUE": tekil,
            "MIN": None if enk is None or pd.isna(enk) else round(float(enk), 4),
            "MAX": None if enb is None or pd.isna(enb) else round(float(enb), 4),
            "DURUM": durum,
            "TESHIS_SAYISI": len(teshisler),
        })

    tablo = pd.DataFrame(kayitlar)
    if len(tablo):
        tablo = tablo.sort_values("NULL_RATIO", ascending=False).reset_index(drop=True)

    teshis = {
        "cok_bos": cok_bos, "sabit": sabit,
        "kimlik_gibi": kimlik_gibi, "yuksek_kardinalite": yuksek_kardinalite,
        "temiz": [r["FEATURE"] for r in kayitlar if r["DURUM"] == "OK"],
    }
    return tablo, teshis


# ===========================================================================
# 2) TEK DEGISKEN ANALIZI (SFA)  — degisken-hedef iliskisi
# ===========================================================================
def sfa_calistir(df, target, adaylar, train_maske=None):
    """Imputation istatistikleri, BIN SINIRLARI ve IV / C-value SADECE train
    uzerinden hesaplanir (leakage). Ogrenilen sinirlar tum satirlara uygulanir
    ama OLCUM train satirlarindadir: OOT'de guclu ama train'de sinyalsiz bir
    degisken PASS alamaz.
    Doner: (tablo, ozet)"""
    y = pd.to_numeric(df[target], errors="coerce")
    tr = train_maske if train_maske is not None else pd.Series(True, index=df.index)
    tr = pd.Series(tr, index=df.index).fillna(False).astype(bool)
    tr_index = df.index[tr]

    kayitlar, sizinti, atlanan = [], [], []
    for kol in adaylar:
        if kol not in df.columns or kol == target:
            continue
        s = df[kol]
        null_adet = int(s.isna().sum())
        sayisal = pd.api.types.is_numeric_dtype(s)
        not_metni = ""

        if sayisal:
            sn = pd.to_numeric(s, errors="coerce")
            med = sn[tr].median()                       # <-- sadece train
            imp_y = "medyan (train)" if null_adet else "-"
            imp_d = None if pd.isna(med) else round(float(med), 4)
            dolu = sn.fillna(med) if null_adet else sn
            # Sinirlar train'den ogrenilir, tum satirlara uygulanir
            gruplar, bin_adet = _binle(dolu, ogren_maske=tr)
            iv = _iv_gruplu(gruplar[tr], y[tr]) if gruplar is not None else None
            c = _c_value(dolu[tr], y[tr])               # <-- olcum train'de
            enc = "binning (%d)" % bin_adet
            if bin_adet < MIN_BIN:
                enc += ": IV güvenilmez"
                not_metni = ("gerçekleşen bin sayısı %d (<%d); dağılım yığılmış, "
                             "IV güvenilmez" % (bin_adet, MIN_BIN))
        else:
            tekil = int(s.nunique(dropna=True))
            if tekil > KATEGORIK_MAX:
                # Atlanan degisken de tabloda gorunur; sessizce kaybolmaz
                atlanan.append(kol)
                kayitlar.append({
                    "FEATURE": kol,
                    "TYPE": "categorical",
                    "IMPUTATION_METHOD": "-",
                    "IMPUTATION_VALUE": None,
                    "ENCODING": "-",
                    "IV": None,
                    "C_VALUE": None,
                    "SFA_RESULT": "ATLANDI",
                    "NOT": ("kategorik seviye sayısı %d > %d; hedef oranı "
                            "kodlaması güvenilir değil" % (tekil, KATEGORIK_MAX)),
                })
                continue
            sk = s.astype(str).where(s.notna(), "MISSING")
            imp_y = "MISSING kategorisi" if null_adet else "-"
            imp_d = "MISSING" if null_adet else None
            iv = _iv_gruplu(sk[tr], y[tr])
            # Kodlama ile olcum ayni satirlarda yapilmaz: out-of-fold
            oof = _oof_hedef_orani(sk, y, tr_index)
            c = _c_value(oof, y.loc[tr_index])
            enc = "hedef oranı (train, out-of-fold)"

        if c is not None and c > SIZINTI_ESIK:
            sizinti.append(kol)

        gecti = (iv is not None and iv > IV_ESIK and c is not None and c > C_ESIK
                 and not not_metni)
        kayitlar.append({
            "FEATURE": kol,
            "TYPE": "numeric" if sayisal else "categorical",
            "IMPUTATION_METHOD": imp_y,
            "IMPUTATION_VALUE": imp_d,
            "ENCODING": enc,
            "IV": None if iv is None else round(iv, 4),
            "C_VALUE": None if c is None else round(c, 4),
            "SFA_RESULT": "PASS" if gecti else "FAIL",
            "NOT": not_metni,
        })

    tablo = pd.DataFrame(kayitlar)
    if len(tablo):
        tablo = tablo.sort_values("IV", ascending=False,
                                  na_position="last").reset_index(drop=True)

    gecen = tablo[tablo["SFA_RESULT"] == "PASS"] if len(tablo) else tablo
    ozet = {
        "analiz_edilen": int(len(tablo)) - len(atlanan),
        "pass_adet": int(len(gecen)),
        "atlanan": atlanan,
        "sizinti": sizinti,
        "en_iyi": [(r["FEATURE"], r["IV"]) for _, r in tablo.head(15).iterrows()
                   if r["SFA_RESULT"] != "ATLANDI"] if len(tablo) else [],
        # ATLANDI satirlari IV/IMPUTATION kolonlarini NaN yaptigi icin
        # "is not None" yetmez; pd.notna ile suzulur.
        "iv_skorlari": {r["FEATURE"]: r["IV"] for _, r in tablo.iterrows()
                        if pd.notna(r["IV"])} if len(tablo) else {},
        "imputation": {r["FEATURE"]: r["IMPUTATION_VALUE"]
                       for _, r in tablo.iterrows()
                       if pd.notna(r["IMPUTATION_VALUE"])} if len(tablo) else {},
    }
    return tablo, ozet


# ===========================================================================
# 3) STABILITE ANALIZI (PSI)  — zaman/populasyon kaymasi
# ===========================================================================
def stabilite_calistir(df, adaylar, dev_maske, oot_maske):
    """Doner: (tablo, ozet). Maske yoksa (None, None) doner."""
    if dev_maske is None or oot_maske is None:
        return None, None

    kayitlar, kayan, atlanan = [], [], []
    for kol in adaylar:
        if kol not in df.columns:
            continue
        s = df[kol]
        sayisal = pd.api.types.is_numeric_dtype(s)
        if sayisal:
            sn = pd.to_numeric(s, errors="coerce")
            psi = _psi(sn[dev_maske], sn[oot_maske])
        else:
            tekil = int(s.nunique(dropna=True))
            if tekil > KATEGORIK_MAX:
                # Atlanan degisken de tabloda gorunur; sessizce kaybolmaz
                atlanan.append(kol)
                kayitlar.append({
                    "FEATURE": kol,
                    "TYPE": "categorical",
                    "PSI": None,
                    "DURUM": "ATLANDI",
                    "NOT": ("kategorik seviye sayısı %d > %d; bin bazlı PSI "
                            "anlamlı değil" % (tekil, KATEGORIK_MAX)),
                })
                continue
            sk = s.astype(str).where(s.notna(), "MISSING")
            psi = _psi(sk[dev_maske], sk[oot_maske], kategorik=True)

        if psi is None:
            continue
        stabil = psi < PSI_ESIK
        if not stabil:
            kayan.append(kol)
        kayitlar.append({
            "FEATURE": kol,
            "TYPE": "numeric" if sayisal else "categorical",
            "PSI": round(psi, 4),
            "DURUM": "STABIL" if stabil else "KAYMA",
            "NOT": "",
        })

    tablo = pd.DataFrame(kayitlar)
    if len(tablo):
        tablo = tablo.sort_values("PSI", ascending=False,
                                  na_position="last").reset_index(drop=True)

    olculen = int(len(tablo)) - len(atlanan)
    ozet = {
        "olculen": olculen,
        "stabil": max(olculen - len(kayan), 0),
        "kayan": kayan,
        "atlanan": atlanan,
        "en_kotu": [(r["FEATURE"], r["PSI"]) for _, r in tablo.head(10).iterrows()
                    if r["DURUM"] != "ATLANDI"] if len(tablo) else [],
    }
    return tablo, ozet
