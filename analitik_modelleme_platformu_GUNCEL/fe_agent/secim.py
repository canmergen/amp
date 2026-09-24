# -*- coding: utf-8 -*-
"""fe_agent/secim.py — degisken secim hatti.

Sira: yari-sabit -> korelasyon -> mutual information -> model onemi

Her adim kendi elemesini yapar ve elenen degiskenin HANGI adimda, NEDEN
elendigi tabloda kalir. Eleme bir ONERIDIR; kullanici tabloyu gorup
karsi cikabilir.
"""

import numpy as np
import pandas as pd

KORELASYON_ESIK = 0.95
QUASI_ESIK = 0.99        # tek degerin payi bunu asarsa yari-sabit
ONEM_ORAN = 0.0005       # toplam onemin bu payindan azi zayif sayilir
MAX_KOLON_KOR = 800      # korelasyon matrisi maliyetli; ust sinir
MI_ORNEK = 5000          # MI icin satir orneklemesi


def _sayisal(df, kolonlar):
    return df[list(kolonlar)].apply(pd.to_numeric, errors="coerce")


# ===========================================================================
# 1) YARI-SABIT
# ===========================================================================
def yari_sabit_ele(df, adaylar, esik=QUASI_ESIK):
    dusur = {}
    for k in adaylar:
        vc = df[k].value_counts(normalize=True, dropna=False)
        if len(vc) and float(vc.iloc[0]) > esik:
            dusur[k] = "tek değer payı %%%s" % ("%.1f" % (float(vc.iloc[0]) * 100))
    return dusur


# ===========================================================================
# 2) KORELASYON
# ===========================================================================
def korelasyon_ele(df, adaylar, oncelik=None, esik=KORELASYON_ESIK):
    """Birbirine cok benzeyen ciftlerden dusuk oncelikli olani duser.
    oncelik: {kolon: skor} — yuksek skorlu tutulur (orn. IV)."""
    adaylar = list(adaylar)[:MAX_KOLON_KOR]
    if len(adaylar) < 2:
        return {}, len(adaylar)

    X = _sayisal(df, adaylar)
    kor = X.corr().abs()
    ust = kor.where(np.triu(np.ones(kor.shape), k=1).astype(bool))

    ciftler = ust.stack()
    ciftler = ciftler[ciftler > esik].sort_values(ascending=False)

    oncelik = oncelik or {}
    dusur = {}
    tutulan = {}          # dusen kolon -> gerekcede adi gecen kolon

    # DONGUSEL eleme: her turda hayatta kalanlar arasindaki EN GUCLU cift
    # ele alinir, biri dusurulur ve kalan ciftler yeniden suzulur. Boylece
    # dusen bir degiskenin diger esleri sessizce atlanmaz.
    kalan_ciftler = list(ciftler.items())
    while True:
        secili = None
        for (a, b), v in kalan_ciftler:
            if a in dusur or b in dusur:
                continue
            secili = ((a, b), v)
            break
        if secili is None:
            break
        (a, b), v = secili
        if float(oncelik.get(a, 0) or 0) >= float(oncelik.get(b, 0) or 0):
            at, tut = b, a
        else:
            at, tut = a, b
        dusur[at] = "%s ile korelasyon %s" % (tut, ("%.3f" % v).replace(".", ","))
        tutulan[at] = tut
        # Dusen kolonun icinde oldugu ciftler listeden cikar
        kalan_ciftler = [(p, w) for p, w in kalan_ciftler
                         if at not in p]

    # Gerekce zinciri: "tutuldu" denilen kolonun kendisi sonradan dustuyse,
    # gerekceyi HAYATTA KALAN en yakin eslesmeye gore yeniden yaz.
    hayatta = [k for k in adaylar if k not in dusur]
    if hayatta:
        for k, tut in tutulan.items():
            if tut not in dusur:
                continue
            e = pd.to_numeric(kor.loc[k, hayatta], errors="coerce").dropna()
            if not len(e):
                continue
            dusur[k] = "%s ile korelasyon %s (zincir: %s)" % (
                e.idxmax(), ("%.3f" % float(e.max())).replace(".", ","), tut)

    return dusur, len(adaylar)


# ===========================================================================
# 3) MUTUAL INFORMATION
# ===========================================================================
def mi_skorla(df, adaylar, y, binary=True):
    """Doner: {kolon: mi_skoru}. sklearn yoksa bos doner."""
    try:
        from sklearn.feature_selection import mutual_info_classif, mutual_info_regression
    except Exception:
        return {}

    X = _sayisal(df, adaylar).fillna(0)
    t = pd.to_numeric(y, errors="coerce").fillna(0)

    if len(X) > MI_ORNEK:
        idx = X.sample(MI_ORNEK, random_state=42).index
        X, t = X.loc[idx], t.loc[idx]

    try:
        fonk = mutual_info_classif if binary else mutual_info_regression
        skor = fonk(X.values, (t > 0).astype(int) if binary else t.values,
                    random_state=42)
    except Exception:
        return {}
    return {k: round(float(v), 5) for k, v in zip(X.columns, skor)}


# ===========================================================================
# 4) MODEL ONEMI  (SHAP varsa SHAP, yoksa agac onemi)
# ===========================================================================
def onem_skorla(df, adaylar, y, binary=True):
    """Doner: ({kolon: onem}, yontem_adi)"""
    try:
        from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
    except Exception:
        return {}, "yok (sklearn bulunamadi)"

    X = _sayisal(df, adaylar).fillna(0)
    t = pd.to_numeric(y, errors="coerce").fillna(0)
    if binary:
        t = (t > 0).astype(int)

    if len(X) > MI_ORNEK:
        idx = X.sample(MI_ORNEK, random_state=42).index
        X, t = X.loc[idx], t.loc[idx]

    Model = RandomForestClassifier if binary else RandomForestRegressor
    model = Model(n_estimators=150, max_depth=8, n_jobs=-1, random_state=42)
    try:
        model.fit(X.values, t.values)
    except Exception as e:
        return {}, "hesaplanamadi (%s)" % str(e)[:40]

    # SHAP varsa tercih edilir — yon ve buyukluk bilgisi daha guvenilir
    try:
        import shap
        ornek = X.sample(min(500, len(X)), random_state=42)
        deger = shap.TreeExplainer(model).shap_values(ornek.values)
        if isinstance(deger, list):
            # Eski shap: sinif basina liste -> pozitif sinif
            deger = deger[-1]
        deger = np.asarray(deger)
        if deger.ndim == 3:
            # shap >= 0.45 ikili siniflandirici: (satir, degisken, sinif)
            deger = deger[:, :, -1]
        if deger.ndim != 2:
            raise ValueError("beklenmeyen SHAP boyutu: %s" % (deger.shape,))
        onem = np.abs(deger).mean(axis=0)
        # float cevrimi de try ICINDE: uyumsuz yapida TypeError yakalansin
        onem = [float(v) for v in np.asarray(onem).ravel()]
        if len(onem) != len(X.columns):
            raise ValueError("SHAP onem uzunlugu kolon sayisiyla uyusmuyor")
        yontem = "SHAP (ortalama |değer|)"
    except Exception:
        onem = [float(v) for v in np.asarray(model.feature_importances_).ravel()]
        yontem = "Random Forest önem skoru"

    return {k: round(v, 6) for k, v in zip(X.columns, onem)}, yontem


# ===========================================================================
# ANA FONKSIYON
# ===========================================================================
def calistir(df, target, adaylar, oncelik=None, binary=True, train_maske=None):
    """Doner: (tablo_df, ozet_sozlugu)

    train_maske verilirse TUM adimlar (yari-sabit, korelasyon, MI, model
    onemi) YALNIZCA o satirlarda hesaplanir. Aksi halde test/OOT satirlari
    secim kararina karisir ve sizinti olusur."""
    adaylar = [k for k in adaylar if k in df.columns and k != target]

    if train_maske is not None:
        tr = pd.Series(train_maske, index=df.index).fillna(False).astype(bool)
        df_tr = df.loc[tr]
        kapsam = "train (%d satır)" % int(len(df_tr))
    else:
        df_tr = df
        kapsam = "tüm satırlar (train maskesi verilmedi)"
    y = df_tr[target]

    kayit = {k: {"FEATURE": k, "ELENDI_ADIM": None, "GEREKCE": None,
                 "MI": None, "ONEM": None, "SECILDI": True} for k in adaylar}

    # --- 1) yari-sabit ---
    d1 = yari_sabit_ele(df_tr, adaylar)
    for k, g in d1.items():
        kayit[k].update({"ELENDI_ADIM": "yarı-sabit", "GEREKCE": g, "SECILDI": False})

    kalan = [k for k in adaylar if kayit[k]["SECILDI"]]

    # --- 2) korelasyon ---
    d2, bakilan = korelasyon_ele(df_tr, kalan, oncelik=oncelik)
    for k, g in d2.items():
        kayit[k].update({"ELENDI_ADIM": "korelasyon", "GEREKCE": g, "SECILDI": False})

    kalan = [k for k in adaylar if kayit[k]["SECILDI"]]

    # --- 3) MI (skor yazilir, eleme YAPILMAZ) ---
    mi = mi_skorla(df_tr, kalan, y, binary) if kalan else {}
    for k, v in mi.items():
        kayit[k]["MI"] = v

    # --- 4) model onemi ---
    onem, yontem = onem_skorla(df_tr, kalan, y, binary) if kalan else ({}, "atlandı")
    zayif = []
    if onem:
        toplam = sum(onem.values()) or 1.0
        for k, v in onem.items():
            kayit[k]["ONEM"] = v
            if v / toplam < ONEM_ORAN:
                zayif.append(k)
        for k in zayif:
            kayit[k].update({"ELENDI_ADIM": "düşük önem",
                             "GEREKCE": "toplam önemin %%%s'inden az"
                                        % ("%.2f" % (ONEM_ORAN * 100)),
                             "SECILDI": False})

    tablo = pd.DataFrame(list(kayit.values()))
    if len(tablo):
        tablo = tablo.sort_values("ONEM", ascending=False, na_position="last")
        tablo = tablo.reset_index(drop=True)

    secilen = [k for k in adaylar if kayit[k]["SECILDI"]]
    ozet = {
        "aday": len(adaylar),
        "yari_sabit": len(d1),
        "korelasyon": len(d2),
        "dusuk_onem": len(zayif),
        "secilen": len(secilen),
        "secilen_liste": secilen,
        "onem_yontemi": yontem,
        "hesap_kapsami": kapsam,
        "korelasyon_bakilan": bakilan,
        "en_iyi": [(r["FEATURE"], r["ONEM"]) for _, r in tablo.head(15).iterrows()
                   if r["SECILDI"]],
    }
    return tablo, ozet
