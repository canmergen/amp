# -*- coding: utf-8 -*-
"""fe_agent/amp_pandas.py - AMP_VERISETI ve alt alta eklemenin PANDAS yolu.

Veri seti kucukse (bkz. motor.py) is Spark'a gonderilmez; webapp icinde
pandas ile yapilir. Sonuc sozlugu Spark recipe'inin (amp_spark) yazdigi
sonuc.json ile AYNI bicimdedir; cagiran taraf (amp.py) motoru bilmez.

KURALLAR SPARK YOLUYLA AYNI
  - Tip donusumu tip_donusum.cevir ile (Spark yolunun kucuk kolonlarda
    kullandigi fonksiyonun kendisi). Dolu olup cevrilemeyen tek hucre
    bile varsa tablo YAZILMAZ.
  - Yazimi koruyan donusumler (donem_ym6 / donem_ymd8) tabloya dokunmaz.
  - Bolme kurallari amp_spark'taki saf Python fonksiyonlardan
    (zamansal_esleme, katman_araliklari, _donem_normal) okunur.
  - Rastgele bolmede sira anahtari bir ozet (hash) + seed: her
    calistirmada ayni setler. Ozet fonksiyonu Spark'inkiyle ayni degil;
    ayni seed iki motorda ayni satirlari secmez (ikisi de kendi icinde
    tekrarlanabilir).
"""

import numpy as np
import pandas as pd

from fe_agent import amp_spark as ak
from fe_agent import profil_kural as pk
from fe_agent import tip_donusum

SPLIT_KOLON = ak.SPLIT_KOLON
ETIKET = ak.ETIKET
DISARIDA = ak.DISARIDA


# ===========================================================================
# TIP DONUSUMLERI
# ===========================================================================
def donusumleri_uygula(df, donusumler):
    """Doner: (yeni_df, {kolon: cevrilemeyen_hucre_sayisi})."""
    takilan = {}
    df = df.copy(deep=False)
    for kolon, d in sorted((donusumler or {}).items()):
        if kolon not in df.columns:
            continue
        kod = d.get("kod")
        if not tip_donusum.gecerli_kod(kod) or kod in tip_donusum.KORUYAN_KALIP:
            continue
        yeni, n, _ornek = tip_donusum.cevir(df[kolon], kod, tam_sayi=d.get("tam_sayi"))
        if n:
            takilan[kolon] = int(n)
            continue
        df[kolon] = yeni
    return df, takilan


# ===========================================================================
# BOLME
# ===========================================================================
def _sayi(seri):
    if pd.api.types.is_bool_dtype(seri):
        return seri.astype(float)
    return pd.to_numeric(seri, errors="coerce")


def _metin(seri):
    """Spark'taki lower(trim(cast string)) karsiligi; bos hucre bos kalir."""
    dolu = seri.notna()
    m = seri.astype(object).where(dolu).map(
        lambda v: str(v).strip().lower(), na_action="ignore")
    return m.where(dolu)


def _hash_anahtari(seed):
    return ("%016d" % (int(seed) % 10 ** 16))[-16:]


def _siraya_gore_etiket(katman, anahtar, oranlar):
    """katman, anahtar: ayni indeksli seriler. Katman icinde anahtara gore
    sira; pay araliklari amp_spark.katman_araliklari ile."""
    tablo = pd.DataFrame({"k": katman.values, "a": anahtar.values},
                         index=katman.index)
    boyut = tablo["k"].value_counts().to_dict()
    araliklar = ak.katman_araliklari(boyut, oranlar)
    tablo = tablo.sort_values(["k", "a"], kind="mergesort")
    tablo["sira"] = tablo.groupby("k").cumcount()
    etiket = pd.Series(ETIKET["egitim"], index=tablo.index, dtype=object)
    for k, liste in araliklar.items():
        ayni = tablo["k"] == k
        for b, e, ad in liste:
            etiket[ayni & (tablo["sira"] >= b) & (tablo["sira"] < e)] = ETIKET[ad]
    return etiket.reindex(katman.index)


def bolme_ekle(df, b):
    """_SPLIT kolonunu ekler (amp_spark.bolme_ekle ile ayni tarif)."""
    tur = b.get("tur")
    if tur == "hazir":
        if b.get("bicim") == "bayrak":
            es = b.get("esleme") or {}

            def bayrak(ad):
                kol = es.get(ad)
                if not kol or kol not in df.columns:
                    return np.zeros(len(df), dtype=bool)
                return (_sayi(df[kol]).fillna(0.0) != 0).to_numpy()
            etiket = np.select(
                [bayrak("test"), bayrak("oot"), bayrak("val"), bayrak("egitim")],
                [ETIKET["test"], ETIKET["oot"], ETIKET["val"], ETIKET["egitim"]],
                default=DISARIDA)
        else:
            normal = _metin(df[b["kolon"]])
            etiket = pd.Series(DISARIDA, index=df.index, dtype=object)
            for hedef in ("egitim", "val", "oot", "test"):
                hamlar = [h for h, t in (b.get("esleme") or {}).items() if t == hedef]
                if hamlar:
                    etiket[normal.isin(hamlar)] = ETIKET[hedef]
            etiket = etiket.to_numpy()
        df = df.copy(deep=False)
        df[SPLIT_KOLON] = etiket
        return df

    if tur == "zamansal":
        kol = b["kolon"]
        sayim_ham = df[kol].value_counts(dropna=True).to_dict()
        normal = ak._donem_normal(pk.pandas_turu(df[kol]), list(sayim_ham))
        sayim = {}
        for h, n in sayim_ham.items():
            if h in normal:
                sayim[normal[h]] = sayim.get(normal[h], 0) + int(n)
        esleme = ak.zamansal_esleme(sayim, b.get("test_donemleri") or [],
                                    b.get("val_var"), b.get("val_oran") or 0,
                                    b.get("gap"))
        harita = {h: esleme.get(n, ETIKET["egitim"]) for h, n in normal.items()}
        df = df.copy(deep=False)
        df[SPLIT_KOLON] = df[kol].map(harita).fillna(ETIKET["egitim"]).astype(object)
        return df

    return rastgele_ekle(df, b)


def rastgele_ekle(df, b):
    """RASTGELE (katmanli) _SPLIT: kimlik varsa kimlik duzeyinde, yoksa satir
    duzeyinde (amp_spark.rastgele_ekle ile ayni tarif)."""
    oranlar = [(ad, float(o)) for ad, o in (b.get("oranlar") or [])]
    hedef = b.get("hedef")
    seed = int(b.get("seed") or 42)
    anahtar_tuzu = _hash_anahtari(seed)
    kimlik = b.get("kimlik")
    df = df.copy(deep=False)
    if kimlik:
        k = df[kimlik].astype(object).where(df[kimlik].notna())
        k = k.map(str, na_action="ignore").fillna("__BOS__")
        if b.get("katmanla") and hedef:
            y = _sayi(df[hedef])
            kt = pd.DataFrame({"id": k, "y": y}).groupby("id", sort=True)["y"].max()
            katman = kt.map(lambda v: "__BOS__" if pd.isna(v) else str(float(v)))
        else:
            katman = pd.Series("__TEK__", index=pd.Index(sorted(k.unique()), name="id"))
        idler = pd.Series(katman.index, index=katman.index)
        anahtar = pd.util.hash_pandas_object(idler, index=False, hash_key=anahtar_tuzu)
        etiket = _siraya_gore_etiket(katman, anahtar, oranlar)
        df[SPLIT_KOLON] = k.map(etiket).fillna(ETIKET["egitim"]).astype(object).to_numpy()
        return df

    if b.get("katmanla") and hedef:
        katman = df[hedef].astype(object).where(df[hedef].notna())
        katman = katman.map(lambda v: str(float(v)) if isinstance(v, (int, float, np.number))
                            and not isinstance(v, bool) else str(v),
                            na_action="ignore").fillna("__BOS__")
    else:
        katman = pd.Series("__TEK__", index=df.index)
    anahtar = pd.util.hash_pandas_object(df, index=False, hash_key=anahtar_tuzu)
    df[SPLIT_KOLON] = _siraya_gore_etiket(katman, anahtar, oranlar).to_numpy()
    return df


# ===========================================================================
# ANA FONKSIYONLAR
# ===========================================================================
def amp_hazirla(df, istek):
    """amp_spark.amp_hazirla'nin pandas karsiligi.
    Doner: (yazilacak_df ya da None, sonuc_sozlugu)."""
    satir = int(len(df))
    df, takilan = donusumleri_uygula(df, istek.get("donusum"))
    sonuc = {"satir": satir}
    if takilan:
        sonuc["hata"] = ("Tip dönüşümü tam veride uygulanamadı; çevrilemeyen "
                         "dolu hücre: " + ", ".join("%s (%s)" % (k, n)
                                                   for k, n in sorted(takilan.items())))
        return None, sonuc

    b = istek.get("bolme")
    if b:
        df = bolme_ekle(df, b)

    dusen = [c for c in (istek.get("dusen") or []) if c in df.columns]
    df = df.drop(columns=dusen)
    sonuc["dusen"] = dusen
    sonuc["kolon"] = int(len(df.columns))

    if b:
        hedef = istek.get("hedef")
        if hedef and hedef in df.columns:
            y = (_sayi(df[hedef]) > 0).to_numpy()
        else:
            y = np.zeros(len(df), dtype=bool)
        tablo = pd.DataFrame({"s": df[SPLIT_KOLON].to_numpy(), "y": y})
        sayim = tablo.groupby("s")["y"].agg(["size", "sum"])
        sonuc["setler"] = {str(s): {"satir": int(r["size"]), "pozitif": int(r["sum"])}
                           for s, r in sayim.iterrows()}
    return df, sonuc


def alt_alta(tablolar, oku):
    """Ayni kolonlu tablolari alt alta ekler. oku(ad) -> DataFrame.
    Doner: (birlesik_df ya da None, sonuc). Kolonlar ilk tablonun
    sirasinda; sonuc Spark isininkiyle ayni bicimde."""
    kisa = lambda ad: str(ad).split(".")[-1]          # noqa: E731
    parcalar, bilgi, kolonlar = [], {}, None
    for ad in tablolar:
        df = oku(ad)
        if kolonlar is None:
            kolonlar = list(df.columns)
        elif set(df.columns) != set(kolonlar):
            return None, {"hata": "%s tablosunun kolonları diğer tablolarla aynı "
                                  "değil; alt alta eklenemez." % kisa(ad)}
        bilgi[kisa(ad)] = {"satir": int(len(df)), "kolon": int(len(df.columns))}
        parcalar.append(df[kolonlar])
    birlesik = pd.concat(parcalar, ignore_index=True)
    return birlesik, {"tablolar": bilgi, "kolon": len(kolonlar),
                      "satir": int(len(birlesik))}
