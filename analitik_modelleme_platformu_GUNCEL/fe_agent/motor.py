# -*- coding: utf-8 -*-
"""fe_agent/motor.py - TAM VERIYE DOKUNAN ISIN MOTORU: pandas mi, Spark mi.

KURAL (kullanici karari: "her şey sparkta olmasın, verinin yapısına göre
seçelim"): karar veri setinin Dataiku'daki DOSYA BOYUTUNA gore verilir.
Boyut "basic:SIZE" metriginden okunur; Dataiku dosyalari listeleyip
toplar, tabloyu okumaz (kullanicinin ortaminda 24,85 GB'lik veri setinde
0,4 saniye).

  toplam boyut <= sinir  -> pandas  (webapp icinde, saniyeler)
  toplam boyut >  sinir  -> Spark   (Dataiku PySpark recipe'i)
  boyut okunamadi        -> Spark   (buyuk olabilir; guvenli taraf)

Kaynak tablolar alt alta eklenecekse BOYUTLARIN TOPLAMINA bakilir: olusacak
tablo o kadar buyuk olacak.

Satir sayisi karara girmez: Dataiku'da kayitli degil ("records:COUNT_RECORDS"
hesaplanmamis) ve hesaplatmak tabloyu saymak demek. Kesin satir sayisini
profil zaten verir.

AYAR (proje degiskeni; tanimli degilse varsayilan)
  amp_pandas_sinir_gb : pandas'a birakilacak en buyuk toplam boyut (GB).
      Varsayilan 0.25 GB. Parquet sikistirilmis tutuluyor; pandas'ta
      bellekte kapladigi yer genelde bunun 5-10 kati, profil hesabi
      sirasinda da ~3 kati. 0.25 GB, 1.040 kolonlu bir tabloda yaklasik
      200 bin satir demek.
"""

import time

import dataiku

PANDAS = "pandas"
SPARK = "spark"
AD = {PANDAS: "Pandas", SPARK: "Spark"}

VARSAYILAN_SINIR_GB = 0.25
METRIK = "basic:SIZE"

# Ayni istekte ayni veri setinin boyutu birkac kez sorulabiliyor
# (profil, alt alta ekleme, ozet metni). Kisa omurlu onbellek.
_ONBELLEK = {}
ONBELLEK_SN = 30.0


def sinir_bayt():
    try:
        deger = (dataiku.get_custom_variables() or {}).get("amp_pandas_sinir_gb")
        gb = float(str(deger).replace(",", ".")) if deger not in (None, "") \
            else VARSAYILAN_SINIR_GB
    except (TypeError, ValueError):
        gb = VARSAYILAN_SINIR_GB
    return int(max(gb, 0.0) * 1024 ** 3)


def boyut(ad):
    """Veri setinin Dataiku'daki dosya boyutu (bayt); okunamazsa None.

    SQL tablosu gibi dosyasi olmayan veri setlerinde metrik bos doner;
    o zaman None (karar Spark)."""
    if not ad or str(ad).startswith("/"):
        return None
    kayit = _ONBELLEK.get(ad)
    if kayit and time.time() - kayit[0] < ONBELLEK_SN:
        return kayit[1]
    deger = None
    try:
        from fe_agent import spark_is
        proje = dataiku.api_client().get_default_project()
        p, kisa = spark_is._proje_ve_ad(proje, str(ad))
        ds = p.get_dataset(kisa)
        ds.compute_metrics(metric_ids=[METRIK])
        ham = ds.get_last_metric_values().get_global_value(METRIK)
        deger = int(float(ham)) if ham not in (None, "") else None
    except Exception:           # pylint: disable=broad-except
        deger = None
    _ONBELLEK[ad] = (time.time(), deger)
    return deger


def unut(ad=None):
    """Platform veri setini yeniden yazinca boyut bir sonraki soruda
    yeniden olculsun."""
    if ad is None:
        _ONBELLEK.clear()
    else:
        _ONBELLEK.pop(ad, None)


def sec(adlar):
    """Doner: (motor, toplam_bayt ya da None)."""
    adlar = [a for a in (adlar or []) if a]
    if adlar and all(str(a).startswith("/") for a in adlar):
        # Calismanin klasorundeki Parquet (yapay zeka planinin kucuk ciktisi)
        return PANDAS, None
    olcumler = [boyut(a) for a in adlar]
    if not olcumler or any(b is None for b in olcumler):
        return SPARK, None
    toplam = int(sum(olcumler))
    return (PANDAS if toplam <= sinir_bayt() else SPARK), toplam


def boyut_metni(bayt):
    """24850731070 -> "24,85 GB"; bilinmiyorsa "bilinmiyor"."""
    if bayt is None:
        return "bilinmiyor"
    b = float(bayt)
    for birim, carpan in (("GB", 1024 ** 3), ("MB", 1024 ** 2), ("KB", 1024)):
        if b >= carpan:
            return ("%.2f %s" % (b / carpan, birim)).replace(".", ",")
    return "%d bayt" % int(b)


def ozet_satirlari(adlar):
    """Mesajlara eklenen iki satir ("  Etiket : Deger" standardi)."""
    motor, toplam = sec(adlar)
    return ["  Dosya Boyutu : %s" % boyut_metni(toplam),
            "  Motor : %s" % AD[motor]]
