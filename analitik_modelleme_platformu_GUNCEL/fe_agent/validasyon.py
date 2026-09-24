# -*- coding: utf-8 -*-
"""Final model validasyonu: metrik hesaplama ve esik degerlendirmesi.

Akis:
  1) final_uygula icinde metrik_hesapla(...) cagrilir,
  2) sonuc kaydet(durum, ...) ile oturuma yazilir,
  3) webapp her yanitta panel(durum) ile Validasyon sekmesini doldurur.

Skor yonu: p = kotu olma olasiligi (yuksek = riskli), y = 1 kotu.
Ters yonlu skorda Gini NEGATIF cikar; bilerek abs() alinmaz.
"""

import numpy as np

# ---------------------------------------------------------------------------
# ESIKLER - VARSAYILAN degerlerdir. Model Risk / validasyon ekibinin
# kriterleriyle guncelleyin. Sekmedeki her satir bu listeden uretilir.
#   yon "buyuk": deger >= gecer -> gecti, >= uyari -> kosullu, aksi kaldi
#   yon "kucuk": deger <= gecer -> gecti, <= uyari -> kosullu, aksi kaldi
#   bicim: "yuzde" (0.412 -> %41,2), "ondalik" (0.084 -> 0,084),
#          "puan" (0.021 -> +2,1 puan)
# ---------------------------------------------------------------------------
ESIKLER = [
    {"anahtar": "gini_test", "ad": "Gini (test)",
     "yon": "buyuk", "gecer": 0.40, "uyari": 0.30, "bicim": "yuzde",
     "aciklama": "Test kümesinde ayrıştırma gücü"},
    {"anahtar": "gini_oot", "ad": "Gini (zamansal test)",
     "yon": "buyuk", "gecer": 0.40, "uyari": 0.30, "bicim": "yuzde",
     "aciklama": "Zamansal ayrılmış test döneminde ayrıştırma gücü"},
    {"anahtar": "gini_dusus", "ad": "Gini düşüşü (eğitim → test)",
     "yon": "kucuk", "gecer": 0.10, "uyari": 0.20, "bicim": "yuzde",
     "aciklama": "Eğitime göre göreli kayıp; aşırı öğrenme göstergesi"},
    {"anahtar": "ks_test", "ad": "KS (test)",
     "yon": "buyuk", "gecer": 0.30, "uyari": 0.20, "bicim": "yuzde",
     "aciklama": "İyi ve kötü skor dağılımları arasındaki en büyük fark"},
    {"anahtar": "psi_skor", "ad": "Skor PSI",
     "yon": "kucuk", "gecer": 0.10, "uyari": 0.25, "bicim": "ondalik",
     "aciklama": "Eğitim ile zamansal ayrılmış test seti arasındaki skor "
                 "dağılımı farkı; bölme rastgeleyse ölçülmez (eğitim-test "
                 "PSI yapısı gereği daima geçer, anlamlı değil)"},
    {"anahtar": "gini_artis", "ad": "Yeni değişken katkısı",
     "yon": "buyuk", "gecer": 0.02, "uyari": 0.0, "bicim": "puan",
     "aciklama": "Final model ile baz model arasındaki test Gini farkı"},
]

DURUM_SIRASI = {"kaldi": 3, "kosullu": 2, "gecti": 1}

MIN_IC_SINIR = 3         # PSI icin gereken en az ic sinir sayisi


# ===========================================================================
# METRIKLER
# ===========================================================================
def _nan_maske(a):
    """numpy dizisi icin NaN maskesi (object dtype'ta da guvenli)."""
    try:
        return np.isnan(np.asarray(a, dtype=float))
    except Exception:
        return np.zeros(np.asarray(a).shape, dtype=bool)


def nan_sayisi(p):
    """Skor dizisindeki NaN adedi. 'veri yok' ile 'hesaplanamadi' ayrimi
    bu sayiya dayanir."""
    if p is None:
        return 0
    try:
        return int(np.isnan(np.asarray(p, dtype=float)).sum())
    except Exception:
        return 0


def gini(y, p):
    """2*AUC - 1. Tek sinifli hedefte ya da skorda NaN varsa -> None.
    Hangi sebeple None dondugu metrik_hesapla tarafindan ayrica raporlanir."""
    from sklearn.metrics import roc_auc_score
    try:
        return 2.0 * roc_auc_score(np.asarray(y), np.asarray(p, dtype=float)) - 1.0
    except ValueError:
        return None


def ks(y, p):
    """Kolmogorov-Smirnov. Tek sinifli hedefte ya da skorda NaN varsa -> None.

    roc_curve tek sinifta HATA ATMAZ, uyari verip NaN dondurur; bu yuzden
    sinif sayisi ve NaN ayrica kontrol edilir."""
    from sklearn.metrics import roc_curve
    try:
        yy = np.asarray(y)
        pp = np.asarray(p, dtype=float)
    except Exception:
        return None
    if yy.size == 0 or pp.size == 0 or yy.size != pp.size:
        return None
    if len(np.unique(yy[~_nan_maske(yy)])) < 2:
        return None                  # tek sinif -> KS tanimsiz
    try:
        fpr, tpr, _ = roc_curve(yy, pp)
    except ValueError:
        return None
    deger = float(np.max(tpr - fpr))
    return None if np.isnan(deger) else deger


def psi(beklenen, gercek, bin_sayisi=10):
    """Beklenen (egitim) dagiliminin yuzdeliklerine gore PSI.

    Yigilmis skorda ic sinirlar tek noktaya inebilir; boyle bir durumda PSI
    yapisi geregi 0'a yakin cikar ve YANLIS bir 'gecti' uretir. Bu yuzden
    en az MIN_IC_SINIR ic sinir yoksa None donulur (= olculemedi)."""
    beklenen = np.asarray(beklenen, dtype=float)
    gercek = np.asarray(gercek, dtype=float)
    beklenen = beklenen[~np.isnan(beklenen)]
    gercek = gercek[~np.isnan(gercek)]
    if len(beklenen) == 0 or len(gercek) == 0:
        return None

    # Ic sinirlar; tekrar eden yuzdelikler (yigilmis skor) tek sinira iner
    ic = np.unique(np.quantile(beklenen, np.linspace(0, 1, bin_sayisi + 1)[1:-1]))
    if len(ic) < MIN_IC_SINIR:
        return None                  # anlamli bin kurulamadi

    b = np.bincount(np.digitize(beklenen, ic), minlength=len(ic) + 1) / len(beklenen)
    g = np.bincount(np.digitize(gercek, ic), minlength=len(ic) + 1) / len(gercek)

    b = np.clip(b, 1e-6, None)       # bos bin log(0) uretmesin
    g = np.clip(g, 1e-6, None)
    return float(np.sum((g - b) * np.log(g / b)))


def metrik_hesapla(y_egitim, p_egitim, y_test, p_test,
                   y_oot=None, p_oot=None, baz_gini_test=None):
    """ESIKLER'deki anahtarlarla metrik sozlugu doner (JSON'a yazilabilir).

    Iki ayri None sebebi vardir ve KARISTIRILMAZ:
      - 'veri yok'      : girdi hic verilmedi (OOT yok, baz model yok)
      - 'hesaplanamadi' : girdi var ama metrik uretilemedi (skorda NaN,
                          tek sinifli hedef, yigilmis skor)
    Ikincisi 'hesaplanamadi' listesine yazilir; panel bunu ayri gosterir."""
    g_eg = gini(y_egitim, p_egitim)
    g_te = gini(y_test, p_test)

    m = {
        "gini_egitim": g_eg,
        "gini_test": g_te,
        "ks_test": ks(y_test, p_test),
        "gini_oot": None,
        "gini_dusus": None,
        "gini_artis": None,
    }
    if g_eg is not None and g_te is not None and g_eg > 0:
        m["gini_dusus"] = (g_eg - g_te) / g_eg

    oot_var = y_oot is not None and p_oot is not None
    if oot_var:
        m["gini_oot"] = gini(y_oot, p_oot)

    # OOT yoksa skor PSI OLCULMEZ: egitim-test PSI yapisi geregi daima gecer
    m["psi_skor"] = psi(p_egitim, p_oot) if oot_var else None

    if baz_gini_test is not None and g_te is not None:
        m["gini_artis"] = g_te - float(baz_gini_test)

    nan_sayilari = {
        "egitim": nan_sayisi(p_egitim),
        "test": nan_sayisi(p_test),
        "oot": nan_sayisi(p_oot) if oot_var else 0,
    }

    # Girdisi VAR ama uretilemeyen metrikler
    hesaplanamadi = []
    if g_te is None:
        hesaplanamadi.append("gini_test")
    if m["ks_test"] is None:
        hesaplanamadi.append("ks_test")
    if oot_var and m["gini_oot"] is None:
        hesaplanamadi.append("gini_oot")
    # Egitim ve test girdileri zorunlu argumandir: girdi her zaman VARDIR,
    # dolayisiyla uretilemeyen gini_dusus 'veri yok' degil 'hesaplanamadi'dir
    if m["gini_dusus"] is None:
        hesaplanamadi.append("gini_dusus")
    if oot_var and m["psi_skor"] is None:
        hesaplanamadi.append("psi_skor")
    if baz_gini_test is not None and m["gini_artis"] is None:
        hesaplanamadi.append("gini_artis")

    sonuc = {k: (None if v is None else round(float(v), 4)) for k, v in m.items()}
    sonuc["hesaplanamadi"] = hesaplanamadi
    sonuc["nan_skor"] = nan_sayilari
    sonuc["oot_var"] = bool(oot_var)
    return sonuc


def kaydet(durum, metrikler, model_adi=None):
    """final_uygula sonunda cagrilir; sonuc oturumla birlikte saklanir."""
    durum["validasyon"] = {"metrikler": metrikler, "model": model_adi}


def temizle(durum):
    """Model yeniden kurulacaksa (geri donus vb.) eski sonucu siler."""
    durum.pop("validasyon", None)


# ===========================================================================
# PANEL
# ===========================================================================
def _sayi(x, basamak):
    """Turkce ondalik; tam sayiysa ondalik yazilmaz: 40.0 -> '40', 41.25 -> '41,2'"""
    if basamak and abs(x - round(x)) < 1e-9:
        return "%d" % round(x)
    return (("%." + str(basamak) + "f") % x).replace(".", ",")


def _bicimle(deger, bicim):
    if deger is None:
        return "-"
    if bicim == "yuzde":
        return "%" + _sayi(deger * 100, 1)
    if bicim == "puan":
        return ("+" if deger > 0 else "") + _sayi(deger * 100, 1) + " puan"
    # Ondalik: en fazla 3 basamak, sondaki sifirlar atilir (0.100 -> 0,1)
    return ("%.3f" % deger).rstrip("0").rstrip(".").replace(".", ",")


def _esik_metni(e):
    isaret = "≥" if e["yon"] == "buyuk" else "≤"
    return "Geçer %s %s · koşullu %s %s" % (
        isaret, _bicimle(e["gecer"], e["bicim"]),
        isaret, _bicimle(e["uyari"], e["bicim"]))


def _degerlendir(e, deger, hesaplanamadi=()):
    if deger is None:
        # Girdi vardi ama metrik uretilemedi -> sessizce 'veri yok' sayma
        return "hesaplanamadi" if e["anahtar"] in hesaplanamadi else "veri_yok"
    if e["yon"] == "buyuk":
        if deger >= e["gecer"]:
            return "gecti"
        return "kosullu" if deger >= e["uyari"] else "kaldi"
    if deger <= e["gecer"]:
        return "gecti"
    return "kosullu" if deger <= e["uyari"] else "kaldi"


def panel(durum):
    """Validasyon sekmesinin JSON govdesi."""
    kayit = durum.get("validasyon") or {}
    metrikler = kayit.get("metrikler")
    hesaplanamadi = set((metrikler or {}).get("hesaplanamadi") or [])
    nan_skor = (metrikler or {}).get("nan_skor") or {}
    nan_toplam = int(sum(int(v or 0) for v in nan_skor.values()))

    satirlar = []
    for e in ESIKLER:
        deger = (metrikler or {}).get(e["anahtar"])
        d = _degerlendir(e, deger, hesaplanamadi) if metrikler else "bekliyor"
        satirlar.append({
            "ad": e["ad"],
            "aciklama": e["aciklama"],
            "deger": ("hesaplanamadı" if d == "hesaplanamadi"
                      else _bicimle(deger, e["bicim"])),
            "esik": _esik_metni(e),
            "durum": d,
        })

    if not metrikler:
        return {
            "genel": "bekliyor",
            "model": None,
            "ozet": "Final model oluşturulduğunda aşağıdaki kriterlere göre "
                    "otomatik değerlendirilir.",
            "satirlar": satirlar,
        }

    olculen = [s for s in satirlar if s["durum"] in DURUM_SIRASI]
    if not olculen:
        genel = "bekliyor"
    else:
        genel = max((s["durum"] for s in olculen), key=DURUM_SIRASI.get)

    # Girdisi olup hesaplanamayan kriter varsa "gecti" sessizce verilmez
    if any(s["durum"] == "hesaplanamadi" for s in satirlar) and genel == "gecti":
        genel = "kosullu"

    gecen = sum(1 for s in olculen if s["durum"] == "gecti")
    ozet = "%d kriterden %d tanesi geçti." % (len(olculen), gecen)

    # 'veri yok' ile 'hesaplanamadı' AYRI raporlanir
    veri_yok = sum(1 for s in satirlar if s["durum"] == "veri_yok")
    olculemedi = sum(1 for s in satirlar if s["durum"] == "hesaplanamadi")
    if veri_yok:
        ozet += " %d kriter için veri yok." % veri_yok
    if olculemedi:
        ozet += (" %d kriter hesaplanamadı (girdi vardı, metrik üretilemedi)."
                 % olculemedi)
    if nan_toplam:
        ozet += (" Skorlarda %d NaN değer var (eğitim %d / test %d / OOT %d)."
                 % (nan_toplam, int(nan_skor.get("egitim") or 0),
                    int(nan_skor.get("test") or 0),
                    int(nan_skor.get("oot") or 0)))

    return {
        "genel": genel,
        "model": kayit.get("model"),
        "ozet": ozet,
        "satirlar": satirlar,
        "nan_skor": nan_skor,
        "nan_skor_toplam": nan_toplam,
        "hesaplanamadi": sorted(hesaplanamadi),
    }
