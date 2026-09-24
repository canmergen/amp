# -*- coding: utf-8 -*-
"""fe_agent/model.py — baseline / enhanced karsilastirmasi.

Ayni bolme, ayni algoritma. Tek fark yeni degiskenlerin eklenmis olmasi.
Boylece AUC/Gini/KS farki dogrudan yeni degiskenlerin katkisi olarak
okunabilir.

Tek kosuluk delta gurultu bandinin altinda kalabildigi icin olcum BIRDEN
COK SEED ile TEKRARLANIR; delta'nin ortalamasi, standart sapmasi ve guven
araligi birlikte raporlanir. Tek bir kosunun farki tek basina karar
gerekcesi degildir.

Egitim Flask endpoint'i icinde yapilir; bu yuzden model kucuk ve hizli
tutulur (HistGradientBoosting, erken durdurma acik).
"""

import numpy as np
import pandas as pd

from fe_agent import validasyon

SEED = 42
TEST_ORAN = 0.20
TEKRAR = 5               # delta olcumu kac farkli seed ile tekrarlanir

# Tekrarlanabilirlik icin hiperparametreler tek yerde tutulur ve sonuca yazilir
HIPER = {
    "max_iter": 200,
    "learning_rate": 0.08,
    "max_depth": 6,
    "early_stopping": True,
    "validation_fraction": 0.15,
}

METRIKLER = ("auc", "gini", "ks")

# Zamansal bolmeyi isaretleyen anahtar kelimeler (bolme_turu parametresinde)
ZAMANSAL_ISARET = ("zaman", "oot", "temporal")


def _zamansal_mi(bolme_turu):
    if not bolme_turu:
        return False
    t = str(bolme_turu).lower()
    return any(a in t for a in ZAMANSAL_ISARET)


def _egit_olc(X_tr, y_tr, X_te, y_te, seed=SEED):
    """Tek kosu. NaN modele BIRAKILIR: HistGradientBoosting eksik degeri
    kendisi isler ve eksiklik sinyali korunur."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import roc_auc_score

    model = HistGradientBoostingClassifier(random_state=seed, **HIPER)
    model.fit(X_tr, y_tr)
    p = model.predict_proba(X_te)[:, 1]
    auc = float(roc_auc_score(y_te, p))
    # KS tek kaynaktan: validasyon.ks (tek sinifli hedefte None doner)
    ks = validasyon.ks(y_te, p)
    return {
        "auc": round(auc, 4),
        "gini": round(2 * auc - 1, 4),
        "ks": None if ks is None else round(float(ks), 4),
        "iterasyon": int(getattr(model, "n_iter_", 0)),
    }


def _ortalama(deger_listesi):
    v = [x for x in deger_listesi if x is not None]
    if not v:
        return None
    return float(np.mean(v))


def _ozetle(deger_listesi):
    """Doner: (ortalama, std, [alt, ust]) — %95 guven araligi."""
    v = [x for x in deger_listesi if x is not None]
    if not v:
        return None, None, None
    ort = float(np.mean(v))
    std = float(np.std(v, ddof=1)) if len(v) > 1 else 0.0
    if len(v) > 1:
        yari = 1.96 * std / float(np.sqrt(len(v)))
    else:
        yari = 0.0
    return ort, std, [round(float(ort - yari), 4), round(float(ort + yari), 4)]


def karsilastir(df, target, baz_kolonlar, yeni_kolonlar,
                oot_maske=None, bolme_turu=None,
                egitim_maske=None, grup=None):
    """Doner: sonuc sozlugu. sklearn yoksa {'hata': ...} doner.

    bolme_turu: bolmenin TURU disaridan bildirilir ("zamansal" / "rastgele").
    Etiket maskenin doluluguna bakilarak TAHMIN EDILMEZ; rastgele bolmede de
    dolu bir maske gelebilir.

    egitim_maske: platformun `egitim` seti. Rastgele bolmede tekrarli olcum
    YALNIZCA bu satirlarda yapilir. Eskiden tum tablo train_test_split ile
    yeniden bolunuyordu; bunun iki sonucu vardi: platformun ayirdigi test ve
    OOT satirlari egitime giriyordu, ve kimlik bazli bolme yok sayildigi icin
    ayni musteri hem egitimde hem testte kalip delta AUC'yi sisiriyordu.

    grup: satir basina grup anahtari (kimlik). Verilirse tekrarli bolme
    GRUPLU yapilir; ayni kimlik iki tarafa birden dusmez."""
    try:
        import sklearn
        from sklearn.model_selection import train_test_split
    except Exception as e:
        return {"hata": "sklearn bulunamadi: %s" % e}

    baz = [k for k in baz_kolonlar if k in df.columns and k != target]
    yeni = [k for k in yeni_kolonlar if k in df.columns and k != target]
    # Kesisimde kolon iki kez girmesin: yeni listesinden baz kolonlari cikar
    baz_kume = set(baz)
    yeni = [k for k in yeni if k not in baz_kume]
    if not baz:
        return {"hata": "baz kolon listesi bos"}

    y_ham = pd.to_numeric(df[target], errors="coerce")
    if int(y_ham.nunique(dropna=True)) > 2:
        return {"hata": "karsilastirma su an yalnizca binary hedef icin"}

    # Hedefi NaN olan satirlar SESSIZCE 0 sinifina yazilmaz; egitimden de
    # testten de dusurulur ve kac satir dustugu raporlanir.
    gecerli = y_ham.notna()

    # Zamansal bolmede kapsam OOT maskesiyle zaten ciziliyor; rastgele
    # bolmede kapsami egitim maskesi cizer. Maske gelmezse eski davranis
    # korunur ama sonuca "kapsam" olarak YAZILIR: sizinti sinirinin
    # olmadigi bir olcum sessizce dogru gorunmemeli.
    # Zamansal bolmede maske GELIR ama kullanilmaz; sinir zaten OOT
    # maskesidir. Eski metin her iki durumda da "maske bildirilmedi"
    # diyordu ve dogru calisan bir olcumu validatore sizinti riski gibi
    # gosteriyordu. Uc durum artik ayri yaziliyor.
    if _zamansal_mi(bolme_turu):
        kapsam = "eğitim satırları (sınır test maskesiyle çiziliyor)"
    elif egitim_maske is None:
        kapsam = "tüm satırlar (eğitim maskesi bildirilmedi)"
    else:
        kapsam = "yalnızca eğitim satırları"
    # NaN sayimi kapsam daraltilmadan ONCE yapiliyor; aksi halde kapsam
    # disinda kalan saglam satirlar "hedefi bos" diye raporlanirdi.
    hedef_nan = int((~gecerli).sum())
    if egitim_maske is not None and not _zamansal_mi(bolme_turu):
        em = pd.Series(egitim_maske, index=df.index).fillna(False).astype(bool)
        gecerli = gecerli & em
    if int(gecerli.sum()) < 50:
        return {"hata": "hedefi dolu satir sayisi yetersiz (%d)"
                        % int(gecerli.sum())}

    y = (y_ham[gecerli] > 0).astype(int)
    if int(y.nunique()) < 2:
        return {"hata": "hedefte tek sinif kaldi"}

    kolonlar = sorted(baz_kume | set(yeni))
    # fillna(0) YOK: eksiklik sinyali modele birakilir
    X_tum = df.loc[gecerli, kolonlar].apply(pd.to_numeric, errors="coerce")

    # --- Bolme: TUR disaridan gelir ---
    zamansal = _zamansal_mi(bolme_turu)
    if zamansal:
        if oot_maske is None:
            return {"hata": "zamansal bolme bildirildi ama oot_maske verilmedi"}
        om = pd.Series(oot_maske, index=df.index).fillna(False).astype(bool)
        om = om.loc[X_tum.index]
        tr_idx = X_tum.index[~om]
        te_idx = X_tum.index[om]
        if len(te_idx) < 50 or len(tr_idx) < 50:
            return {"hata": "Zamansal bolme yetersiz (egitim %d / test %d satir)"
                            % (len(tr_idx), len(te_idx))}
        bolme = "zamansal"
    else:
        tr_idx = te_idx = None       # her tekrarda yeniden bolunur
        # Gruplu tekrarli bolme: ayni kimligin butun satirlari tek tarafta.
        # Gruplamayi atlamak ayni musteriyi hem egitimde hem testte birakir
        # ve modele "yeni degisken" yerine musteriyi ezberletir; delta AUC
        # o zaman degiskenlerin degil, sizintinin olcusu olur.
        g = None
        if grup is not None:
            g = pd.Series(grup, index=df.index).astype(str).loc[X_tum.index]
        pay = "%%%d/%%%d %s" % ((1 - TEST_ORAN) * 100, TEST_ORAN * 100,
                                "gruplu" if g is not None else "stratified")
        if bolme_turu:
            bolme = "%s: %s" % (bolme_turu, pay)
        else:
            bolme = "bölme türü bildirilmedi: rastgele %s" % pay

    # --- TEKRARLI OLCUM: tek kosunun gurultusu delta'yi tasiyamaz ---
    seedler = [SEED + i for i in range(max(int(TEKRAR), 1))]
    kosular = []
    try:
        for sd in seedler:
            if zamansal:
                a_idx, b_idx = tr_idx, te_idx
            elif g is not None:
                from sklearn.model_selection import GroupShuffleSplit
                bolucu = GroupShuffleSplit(n_splits=1, test_size=TEST_ORAN,
                                           random_state=sd)
                a_pos, b_pos = next(bolucu.split(X_tum, y, g))
                a_idx, b_idx = X_tum.index[a_pos], X_tum.index[b_pos]
            else:
                a_idx, b_idx = train_test_split(
                    X_tum.index, test_size=TEST_ORAN, stratify=y,
                    random_state=sd)
            b = _egit_olc(X_tum.loc[a_idx, baz], y.loc[a_idx],
                          X_tum.loc[b_idx, baz], y.loc[b_idx], seed=sd)
            if yeni:
                e = _egit_olc(X_tum.loc[a_idx, baz + yeni], y.loc[a_idx],
                              X_tum.loc[b_idx, baz + yeni], y.loc[b_idx],
                              seed=sd)
            else:
                e = dict(b)
            kosu = {"seed": sd, "egitim_satir": int(len(a_idx)),
                    "test_satir": int(len(b_idx)),
                    "baseline": b, "enhanced": e}
            if not zamansal and g is not None:
                # Gruplamanin TUTTUGU sayiyla kanitlanir; kod okuyarak degil.
                kosu["grup_cakisma"] = int(len(set(g.loc[a_idx]) &
                                               set(g.loc[b_idx])))
            kosular.append(kosu)
            if tr_idx is None:
                tr_idx, te_idx = a_idx, b_idx    # raporlanacak ornek bolme
    except Exception as ex:
        return {"hata": str(ex)[:200]}

    if not kosular:
        return {"hata": "hicbir kosu tamamlanamadi"}

    # --- Toplama ---
    baseline, enhanced, delta, delta_std, delta_ga = {}, {}, {}, {}, {}
    for m in METRIKLER:
        b_deg = [k["baseline"][m] for k in kosular]
        e_deg = [k["enhanced"][m] for k in kosular]
        b_ort = _ortalama(b_deg)
        e_ort = _ortalama(e_deg)
        baseline[m] = None if b_ort is None else round(float(b_ort), 4)
        enhanced[m] = None if e_ort is None else round(float(e_ort), 4)
        farklar = [float(e - b) for e, b in zip(e_deg, b_deg)
                   if e is not None and b is not None]
        ort, std, ga = _ozetle(farklar)
        delta[m] = None if ort is None else round(float(ort), 4)
        delta_std[m] = None if std is None else round(float(std), 4)
        delta_ga[m] = ga

    return {
        "bolme": bolme,
        "bolme_turu": bolme_turu,
        "kapsam": kapsam,
        "kapsam_satir": int(len(X_tum)),
        "gruplu": bool(not zamansal and grup is not None),
        "seed": SEED,
        "seedler": seedler,
        "tekrar": len(kosular),
        "egitim_satir": int(len(tr_idx)),
        "test_satir": int(len(te_idx)),
        "hedef_nan_dusen": hedef_nan,
        "baz_kolon": len(baz),
        "yeni_kolon": len(yeni),
        # KARSILASTIRILABILIR MI: yeni kolon yoksa baz ve zengin model
        # AYNI modeldir. O zaman delta mekanik olarak sifir, guven araligi
        # da [0,0] cikar. Bunu "katki gurultuden ayirt edilemiyor" diye
        # yorumlamak istatistiksel bir iddia uydurmaktir: karsilastirma
        # hic yapilmamistir. Tuketiciler (faz05, panel, dokuman) once
        # BU BAYRAGA bakar, guven araligina sonra.
        "karsilastirilabilir": bool(yeni),
        "karsilastirma_notu": (
            "" if yeni else
            "Baz ve zengin model AYNI değişken kümesini kullanıyor "
            "(seçilen yeni değişken yok). Fark yapısal olarak sıfırdır; "
            "bu bir katkı ölçümü değildir."),
        "baseline": baseline,
        "enhanced": enhanced,
        "delta": delta,
        "delta_std": delta_std,
        "delta_guven_araligi": delta_ga,
        "kosular": kosular,
        # --- tekrarlanabilirlik kaydi ---
        "baz_kolon_listesi": list(baz),
        "yeni_kolon_listesi": list(yeni),
        "kullanilan_kolonlar": list(baz) + list(yeni),
        "hiperparametreler": dict(HIPER),
        "erken_durdurma_iterasyon": {
            "baz": [k["baseline"]["iterasyon"] for k in kosular],
            "zengin": [k["enhanced"]["iterasyon"] for k in kosular],
        },
        "sklearn_surum": sklearn.__version__,
        "algoritma": "HistGradientBoostingClassifier",
    }
