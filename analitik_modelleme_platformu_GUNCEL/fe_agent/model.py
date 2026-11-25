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
                egitim_maske=None, grup=None, seedler=None):
    """Doner: sonuc sozlugu. sklearn yoksa {'hata': ...} doner.

    bolme_turu: bolmenin TURU disaridan bildirilir ("zamansal" / "rastgele").
    Etiket maskenin doluluguna bakilarak TAHMIN EDILMEZ; rastgele bolmede de
    dolu bir maske gelebilir.

    egitim_maske: platformun `egitim` seti. Rastgele bolmede tekrarli olcum
    YALNIZCA bu satirlarda yapilir.

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

    # Zamansal bolmede kapsam OOT maskesiyle ciziliyor; egitim maskesi
    # gelse de kullanilmaz. Rastgele bolmede kapsami egitim maskesi cizer.
    # Maske gelmezse tum satirlar kullanilir ve bu sonuca "kapsam" olarak
    # YAZILIR: sizinti sinirinin olmadigi bir olcum sessizce dogru
    # gorunmemeli.
    if _zamansal_mi(bolme_turu):
        kapsam = ("yalnızca eğitim satırları; ölçüm test döneminde" if egitim_maske is not None
                  else "test dönemi dışındaki bütün satırlar (eğitim maskesi bildirilmedi)")
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
    # SAYIYA CEVRILEMEYEN kolon (metin kategori) tamamen bos kalir ve
    # modeli durdurur; disarida birakilir ve raporlanir. (Aralik kolonlari
    # cagiran tarafta sira numarasina cevrilmis gelir.)
    cevrilemeyen = [k for k in kolonlar if not X_tum[k].notna().any()]
    if cevrilemeyen:
        X_tum = X_tum.drop(columns=cevrilemeyen)
        baz = [k for k in baz if k not in cevrilemeyen]
        yeni = [k for k in yeni if k not in cevrilemeyen]
        kolonlar = [k for k in kolonlar if k not in cevrilemeyen]
        if not baz:
            return {"hata": "baz kolonların hiçbiri sayıya çevrilemedi (%s)"
                            % ", ".join(cevrilemeyen[:5])}

    # --- Bolme: TUR disaridan gelir ---
    zamansal = _zamansal_mi(bolme_turu)
    if zamansal:
        if oot_maske is None:
            return {"hata": "zamansal bolme bildirildi ama oot_maske verilmedi"}
        om = pd.Series(oot_maske, index=df.index).fillna(False).astype(bool)
        om = om.loc[X_tum.index]
        # EGITIM YALNIZ TRAIN SATIRLARI: test donemi disinda kalan her satir
        # egitim degildir. Test (OOS) satirlari ve egitim ile test arasinda
        # bosluk (gap) olarak ayrilan donemler modele girmez; girerse model
        # 01.4'te ayrilan bolmeyle kurulmamis olur.
        tr_maske = ~om
        if egitim_maske is not None:
            tr_maske = pd.Series(egitim_maske, index=df.index).fillna(False).astype(bool) \
                .loc[X_tum.index] & ~om
        tr_idx = X_tum.index[tr_maske]
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
    # Tohumlar cagirandan (01.4'te secilen tohum / tohum listesi); verilmezse
    # SEED'den baslayan TEKRAR tohum.
    seedler = [int(x) for x in seedler] if seedler else \
        [SEED + i for i in range(max(int(TEKRAR), 1))]
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
        "seed": seedler[0],
        "seedler": seedler,
        "tekrar": len(kosular),
        "egitim_satir": int(len(tr_idx)),
        "test_satir": int(len(te_idx)),
        "hedef_nan_dusen": hedef_nan,
        "baz_kolon": len(baz),
        "yeni_kolon": len(yeni),
        "cevrilemeyen_kolonlar": list(cevrilemeyen),
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


# ===========================================================================
# COKLU KARSILASTIRMA: ayni satirlar, ayni bolme, birden fazla veri seti
# ---------------------------------------------------------------------------
# Ham / Temizlenmis / + Kural / + AI gibi veri setleri AYNI kuralla olculur:
#   * Model YALNIZ Train satirlariyla kurulur.
#   * Olcum 01.4'te ayrilan sette yapilir (cagiran taraf maskeyi verir);
#     olcum seti yoksa Train icinde capraz dogrulama (katlar cagirandan ya
#     da burada kurulur).
#   * Her veri setinde ayni hazirlik: sayi olmayan kolon Train'deki
#     sikligina gore sira numarasina cevrilir; kolon sayisi siniri asarsa
#     Train'de tek basina ayirma gucu en yuksek kolonlar alinir.
#   * Her tohumda dort model de ayni tohumla kurulur; fark ILK veri setine
#     (Ham) gore, tohumlar uzerinden ortalama, standart sapma ve %95 guven
#     araligiyla raporlanir.
# ===========================================================================
COKLU_EN_COK_KOLON = 300
COKLU_KAT = 5
COKLU_EN_AZ_SATIR = 50


def _sayiya_cevir(X, tr):
    """Sayi olmayan kolonlar Train'deki sikliga gore sira numarasina (en sik
    1); Train'de hic gorulmeyen deger bos kalir. Doner: (X, cevrilen)."""
    cikti, cevrilen = {}, []
    for k in X.columns:
        s_ = X[k]
        if pd.api.types.is_bool_dtype(s_):
            cikti[k] = s_.astype(float)
        elif pd.api.types.is_numeric_dtype(s_):
            cikti[k] = pd.to_numeric(s_, errors="coerce")
        else:
            sn = pd.to_numeric(s_, errors="coerce")
            if sn.notna().sum() >= 0.99 * max(int(s_.notna().sum()), 1):
                cikti[k] = sn                      # metin olarak yazilmis sayi
                continue
            sira = s_[tr].astype("object").value_counts()
            harita = {v: i + 1 for i, v in enumerate(sira.index)}
            cikti[k] = s_.map(harita).astype(float)
            cevrilen.append(k)
    return pd.DataFrame(cikti, index=X.index), cevrilen


def _tek_guc(X, y):
    """{kolon: |AUC - 0,5|}: kolonun Train'de tek basina ayirma gucu (sira
    tabanli; bos hucreler ortanca siraya)."""
    n1 = float(y.sum())
    n0 = float(len(y) - n1)
    if n1 <= 0 or n0 <= 0:
        return {k: 0.0 for k in X.columns}
    sira = X.rank(method="average", na_option="keep")
    sira = sira.fillna(sira.mean())
    toplam = sira[y.values == 1].sum()
    auc = (toplam - n1 * (n1 + 1) / 2.0) / (n1 * n0)
    return {k: abs(float(v) - 0.5) if np.isfinite(v) else 0.0 for k, v in auc.items()}


def coklu_karsilastir(veriler, target, olcum_adi=None, katlar=None, grup=None,
                      tekrar=None, en_cok_kolon=COKLU_EN_COK_KOLON, seedler=None):
    """veriler: [{"ad", "df", "kolonlar", "egitim" (bool Series), "olcum"
    (bool Series ya da None)}] - ilk eleman karsilastirma tabanidir.
    olcum None ise Train icinde capraz dogrulama: `katlar` ([(egitim_idx,
    dogrulama_idx)] - df.index degerleri) verilmediyse COKLU_KAT katli
    (grup verilirse gruplu) kurulur.
    Doner: {"olcum", "olcum_adi", "ayni_satir", "tekrar", "seedler",
    "setler": [{"ad", "kolon", "kolon_toplam", "egitim_satir", "olcum_satir",
    "auc", "gini", "ks", "delta", "delta_std", "delta_ga" (ILK sete gore),
    "adim_delta", "adim_ga" (bir ONCEKI sete gore), "atlandi"}]} ya da
    {"hata"}."""
    try:
        import sklearn                                       # noqa: F401
        from sklearn.model_selection import StratifiedKFold, GroupKFold
    except Exception as e:
        return {"hata": "sklearn bulunamadi: %s" % e}
    if not veriler:
        return {"hata": "karşılaştırılacak veri seti yok"}
    seedler = [int(x) for x in seedler] if seedler else \
        [SEED + i for i in range(max(int(tekrar or TEKRAR), 1))]
    hazir, satir_imza = [], []
    for v in veriler:
        df = v["df"]
        if target not in df.columns:
            return {"hata": "%s veri setinde hedef kolonu yok" % v["ad"]}
        y_ham = pd.to_numeric(df[target], errors="coerce")
        if int(y_ham.nunique(dropna=True)) > 2:
            return {"hata": "karsilastirma su an yalnizca binary hedef icin"}
        gecerli = y_ham.notna()
        tr = pd.Series(v["egitim"], index=df.index).fillna(False).astype(bool) & gecerli
        ol = None
        if v.get("olcum") is not None:
            ol = pd.Series(v["olcum"], index=df.index).fillna(False).astype(bool) & gecerli & ~tr
        y = (y_ham > 0).astype(int)
        kol = [k for k in dict.fromkeys(v["kolonlar"]) if k in df.columns and k != target]
        X, cevrilen = _sayiya_cevir(df[kol], tr)
        bos = [k for k in X.columns if not X.loc[tr, k].notna().any()]
        X = X.drop(columns=bos)
        toplam = int(X.shape[1])
        if toplam > en_cok_kolon:
            guc = _tek_guc(X.loc[tr], y[tr])
            sec = sorted(X.columns, key=lambda k: (-guc.get(k, 0.0), k))[:en_cok_kolon]
            X = X[sorted(sec)]
        hazir.append({"ad": v["ad"], "X": X, "y": y, "tr": tr, "ol": ol, "toplam": toplam,
                      "cevrilen": cevrilen, "bos": bos})
        satir_imza.append((int(tr.sum()), int(y[tr].sum()),
                           int(ol.sum()) if ol is not None else -1,
                           int(y[ol].sum()) if ol is not None else -1))
    ayni_satir = len(set(satir_imza)) == 1
    ilk = hazir[0]
    if int(ilk["tr"].sum()) < COKLU_EN_AZ_SATIR or int(ilk["y"][ilk["tr"]].nunique()) < 2:
        return {"hata": "Train satırı yetersiz ya da hedefte tek sınıf var (%d satır)"
                        % int(ilk["tr"].sum())}
    cv = ilk["ol"] is None or int(ilk["ol"].sum()) < COKLU_EN_AZ_SATIR \
        or int(ilk["y"][ilk["ol"]].nunique()) < 2
    kat_listesi, kat_kaynagi = None, ""
    if cv:
        if katlar:
            kat_listesi, kat_kaynagi = list(katlar), "01.4 katları"
        else:
            idx = ilk["X"].index[ilk["tr"]]
            yy = ilk["y"][ilk["tr"]]
            try:
                if grup is not None:
                    g = pd.Series(grup, index=ilk["X"].index).astype(str)[ilk["tr"]]
                    bolucu = GroupKFold(n_splits=COKLU_KAT).split(idx, yy, g)
                    kat_kaynagi = "%d katlı, kimliğe göre gruplu" % COKLU_KAT
                else:
                    bolucu = StratifiedKFold(n_splits=COKLU_KAT, shuffle=True,
                                             random_state=seedler[0]).split(idx, yy)
                    kat_kaynagi = "%d katlı" % COKLU_KAT
                kat_listesi = [(idx[a], idx[b]) for a, b in bolucu]
            except Exception as ex:
                return {"hata": "çapraz doğrulama katları kurulamadı: %s" % str(ex)[:120]}
    sonuc_setler, onceki_kolon, onceki = [], None, None
    try:
        for h in hazir:
            kolonlar = list(h["X"].columns)
            kayit = {"ad": h["ad"], "kolon": len(kolonlar), "kolon_toplam": h["toplam"],
                     "egitim_satir": int(h["tr"].sum()),
                     "olcum_satir": int(h["ol"].sum()) if (h["ol"] is not None and not cv) else None,
                     "cevrilen_kolon": len(h["cevrilen"]), "bos_kolon": len(h["bos"])}
            if not kolonlar:
                kayit.update({"atlandi": "kullanılabilir kolon yok"})
                sonuc_setler.append(kayit)
                continue
            # Onceki veri setiyle AYNI kolonlar: model ayni olur, yeniden kurulmaz.
            if onceki is not None and onceki_kolon == kolonlar and h["X"].shape == onceki[0].shape \
                    and bool(h["X"].equals(onceki[0])):
                kayit["kosular"] = [dict(k) for k in onceki[1]]
                kayit["ayni"] = True
            else:
                kosular = []
                for sd in seedler:
                    if cv:
                        olc = []
                        for a_idx, b_idx in kat_listesi:
                            if int(h["y"].loc[b_idx].nunique()) < 2 or int(h["y"].loc[a_idx].nunique()) < 2:
                                continue
                            olc.append(_egit_olc(h["X"].loc[a_idx], h["y"].loc[a_idx],
                                                 h["X"].loc[b_idx], h["y"].loc[b_idx], seed=sd))
                        if not olc:
                            continue
                        kosular.append({m: _ortalama([o[m] for o in olc]) for m in METRIKLER})
                    else:
                        o = _egit_olc(h["X"][h["tr"]], h["y"][h["tr"]],
                                      h["X"][h["ol"]], h["y"][h["ol"]], seed=sd)
                        kosular.append({m: o[m] for m in METRIKLER})
                kayit["kosular"] = kosular
            onceki_kolon, onceki = kolonlar, (h["X"], kayit["kosular"])
            sonuc_setler.append(kayit)
    except Exception as ex:
        return {"hata": str(ex)[:200]}
    taban = next((s_ for s_ in sonuc_setler if s_.get("kosular")), None)
    if taban is None:
        return {"hata": "hicbir kosu tamamlanamadi"}
    son = None
    for s_ in sonuc_setler:
        ks_ = s_.get("kosular") or []
        for m in METRIKLER:
            ort = _ortalama([k[m] for k in ks_])
            s_[m] = None if ort is None else round(float(ort), 4)
        s_["delta"], s_["delta_std"], s_["delta_ga"], s_["adim_delta"] = {}, {}, {}, {}
        s_["adim_ga"] = {}
        for m in METRIKLER:
            if not ks_ or s_ is taban:
                continue
            fark = [float(a[m] - b[m]) for a, b in zip(ks_, taban["kosular"])
                    if a.get(m) is not None and b.get(m) is not None]
            ort, std, ga = _ozetle(fark)
            s_["delta"][m] = None if ort is None else round(float(ort), 4)
            s_["delta_std"][m] = None if std is None else round(float(std), 4)
            s_["delta_ga"][m] = ga
            if son is not None and son.get("kosular"):
                adim = [float(a[m] - b[m]) for a, b in zip(ks_, son["kosular"])
                        if a.get(m) is not None and b.get(m) is not None]
                a_ort, _a_std, a_ga = _ozetle(adim)
                s_["adim_delta"][m] = None if a_ort is None else round(float(a_ort), 4)
                s_["adim_ga"][m] = a_ga
        if ks_:
            son = s_
    return {"olcum": "cv" if cv else "set", "olcum_adi": olcum_adi if not cv else None,
            "kat": len(kat_listesi) if cv else None, "kat_kaynagi": kat_kaynagi,
            "ayni_satir": bool(ayni_satir), "tekrar": len(seedler), "seedler": seedler,
            "en_cok_kolon": int(en_cok_kolon), "taban": taban["ad"],
            "hiperparametreler": dict(HIPER), "algoritma": "HistGradientBoostingClassifier",
            "setler": sonuc_setler}
