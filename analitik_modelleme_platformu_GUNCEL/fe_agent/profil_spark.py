# -*- coding: utf-8 -*-
"""fe_agent/profil_spark.py - VERI SETI PROFILI, PySpark MOTORU.

Dataiku'da bir PySpark recipe'i olarak calisir (kurulum: OKU_ONCE.md).
Recipe'in TEK girdisi profili cikarilacak veri seti, TEK ciktisi AMP_PROFIL
klasorudur. Webapp recipe'in girdisini secilen veri setine cevirir, isi
baslatir ve bitince AMP_PROFIL/<veri_seti>/profil.json dosyasini okur.

Recipe kodu (Dataiku'da PySpark recipe'ine aynen yapistirilir):

    from fe_agent import profil_spark
    profil_spark.recete_calistir()

HESAP (hepsi KESIN; yaklasik sayim ve orneklem yok)
  1. Birinci gecis: kolon basina dolu/bos sayisi, min/maks, tam sayi ve
     donem bicimi sayimlari (tek toplu sorgu, kolon gruplari halinde).
  2. Tekrarlanan satir: satir sayisi - tekil satir sayisi.
  3. Tekil degerler: her kolonun (deger, satir sayisi) tablosu - kolon
     turune gore bir "uzun" tabloda groupBy. Tekil sayisi, en sik degerler,
     kantiller ve 50'den az seviyeli kolonlarin deger listesi buradan.
  4. Deger basina denetim (tip donusumu, kisisel veri deseni, donem
     yazimlari): tekil deger tablosu uzerinde profil_kural fonksiyonlari,
     her bolumde parca parca; parcalar toplanir (reduceByKey).
  Kurallar profil_kural.py'de; ayni kurallar yerel motorda da calisir ve
  iki motorun ayni tabloda ayni sonucu verdigi test ediliyor.
"""

import datetime
import json
import sys

from fe_agent import profil_kural as pk

# Tekil deger denetiminde tek seferde islenen deger sayisi (bellek siniri).
PARCA_BOYU = 50000
# Birinci geciste tek sorguya giren kolon sayisi (cok genis tablolarda
# Spark'in sorgu planini sisirmemek icin gruplar halinde).
TOPLU_KOLON = 60

PROFIL_DOSYA = "profil.json"
ISTEK_DEGISKENI = "amp_profil_istek"


# ===========================================================================
# YARDIMCILAR
# ===========================================================================
def _tur(veri_tipi):
    """Spark veri tipi -> profil_kural kolon turu."""
    from pyspark.sql import types as T
    if isinstance(veri_tipi, T.BooleanType):
        return pk.TUR_MANTIKSAL
    if isinstance(veri_tipi, (T.ByteType, T.ShortType, T.IntegerType, T.LongType)):
        return pk.TUR_TAM
    if isinstance(veri_tipi, (T.FloatType, T.DoubleType, T.DecimalType)):
        return pk.TUR_ONDALIK
    if isinstance(veri_tipi, (T.DateType, T.TimestampType)):
        return pk.TUR_TARIH
    return pk.TUR_METIN


def _normal_kolon(c, tur):
    """Iki motorun ortak bos tanimi: ondalikta NaN, metinde "" bostur."""
    from pyspark.sql import functions as F
    if tur == pk.TUR_ONDALIK:
        c = c.cast("double")
        return F.when(F.isnan(c), F.lit(None).cast("double")).otherwise(c)
    if tur == pk.TUR_METIN:
        c = c.cast("string")
        return F.when(c == "", F.lit(None).cast("string")).otherwise(c)
    if tur == pk.TUR_TARIH:
        return c.cast("timestamp")
    if tur == pk.TUR_TAM:
        return c.cast("long")
    return c


_UZUN_TIP = {pk.TUR_TAM: "long", pk.TUR_ONDALIK: "double",
             pk.TUR_MANTIKSAL: "boolean", pk.TUR_METIN: "string",
             pk.TUR_TARIH: "timestamp"}


def _kod_gonder(spark):
    """Deger basina denetim fonksiyonlari yurutuculerde calisir. Proje
    kutuphanesi yurutuculerde kurulu olmayabilir; modulleri FONKSIYONLARLA
    BIRLIKTE gondermek icin cloudpickle'a "degeriyle paketle" denir
    (Spark 3.3+). Eski surumde yurutucunun fe_agent'i gormesi gerekir."""
    try:
        from pyspark import cloudpickle
        from fe_agent import birlestirme, sozluk, tip_donusum
        for mod in (pk, tip_donusum, sozluk, birlestirme, sys.modules[__name__]):
            cloudpickle.register_pickle_by_value(mod)
    except Exception:           # pylint: disable=broad-except
        pass


# ===========================================================================
# 1) BIRINCI GECIS
# ===========================================================================
def _ilk_gecis_ifadeleri(i, tur):
    from pyspark.sql import functions as F
    c = F.col("c%d" % i)
    var = c.isNotNull()
    ifade = [F.count(c).alias("dolu_%d" % i),
             F.first(c, ignorenulls=True).alias("ornek_%d" % i)]
    if tur in pk.SAYISAL_TURLER:
        v = c.cast("int").cast("double") if tur == pk.TUR_MANTIKSAL \
            else c.cast("double")
        sonsuz = (v == float("inf")) | (v == float("-inf"))
        a = F.abs(v)
        ym = v.between(pk.YM_ALT, pk.YM_UST) & (v % 100).between(1, 12)
        ymd = (v.between(pk.YMD_ALT, pk.YMD_UST)
               & (F.floor(v / 100) % 100).between(1, 12)
               & (v % 100).between(1, 31))
        ifade += [
            F.min(v).alias("min_%d" % i), F.max(v).alias("max_%d" % i),
            F.count(F.when(var & ~sonsuz, 1)).alias("sonlu_%d" % i),
            F.count(F.when(var & ~sonsuz & ((v % 1) != 0), 1)).alias("kesir_%d" % i),
            F.count(F.when(var & (v > 0), 1)).alias("poz_%d" % i),
            F.count(F.when(var & ~sonsuz & ((a % 1) == 0) & (a >= pk.PII_SAYI_ALT)
                           & (a < pk.PII_SAYI_UST), 1)).alias("pii_%d" % i),
            F.count(F.when(var & ~F.coalesce(ym, F.lit(False)), 1)).alias("ym_%d" % i),
            F.count(F.when(var & ~F.coalesce(ymd, F.lit(False)), 1)).alias("ymd_%d" % i),
        ]
    elif tur == pk.TUR_TARIH:
        ifade += [F.min(c).alias("min_%d" % i), F.max(c).alias("max_%d" % i)]
    return ifade


def _ilk_gecis(df, turler):
    """Doner: (satir, {i: ozet})."""
    from pyspark.sql import functions as F
    satir = None
    ozetler = {}
    sira = list(range(len(turler)))
    for bas in range(0, max(len(sira), 1), TOPLU_KOLON):
        grup = sira[bas:bas + TOPLU_KOLON]
        ifadeler = [F.count(F.lit(1)).alias("_satir")]
        for i in grup:
            ifadeler += _ilk_gecis_ifadeleri(i, turler[i])
        r = df.agg(*ifadeler).collect()[0].asDict()
        satir = int(r["_satir"])
        for i in grup:
            tur = turler[i]
            dolu = int(r["dolu_%d" % i])
            oz = {"tur": tur, "dolu": dolu, "bos": satir - dolu,
                  "ornek": r.get("ornek_%d" % i), "min": None, "max": None,
                  "hepsi_tam": False, "n_sonlu": 0, "n_kesirli": 0,
                  "pozitif": None, "n_pii_aday": 0,
                  "ym_degil": None, "ymd_degil": None}
            if tur in pk.SAYISAL_TURLER and dolu:
                oz.update({
                    "min": r["min_%d" % i], "max": r["max_%d" % i],
                    "n_sonlu": int(r["sonlu_%d" % i]),
                    "n_kesirli": int(r["kesir_%d" % i]),
                    "pozitif": int(r["poz_%d" % i]),
                    "n_pii_aday": int(r["pii_%d" % i]),
                    "ym_degil": int(r["ym_%d" % i]),
                    "ymd_degil": int(r["ymd_%d" % i])})
                oz["hepsi_tam"] = (oz["n_sonlu"] == dolu and not oz["n_kesirli"])
            elif tur == pk.TUR_TARIH and dolu:
                oz["min"], oz["max"] = r["min_%d" % i], r["max_%d" % i]
            ozetler[i] = oz
    if satir is None:
        satir = int(df.count())
    return satir, ozetler


# ===========================================================================
# 2) TEKIL DEGER TABLOLARI
# ===========================================================================
def _tekil_tablo(df, indeksler, tur):
    """(k, v, adet): verilen kolonlarin bos olmayan her tekil degeri ve
    satir sayisi. Ayni turdeki kolonlar tek bir uzun tabloda toplanir."""
    from pyspark.sql import functions as F
    tip = _UZUN_TIP[tur]
    yapilar = [F.struct(F.lit(i).alias("k"),
                        F.col("c%d" % i).cast(tip).alias("v"))
               for i in indeksler]
    uzun = df.select(F.explode(F.array(*yapilar)).alias("x")) \
             .select(F.col("x.k").alias("k"), F.col("x.v").alias("v")) \
             .where(F.col("v").isNotNull())
    return uzun.groupBy("k", "v").agg(F.count(F.lit(1)).alias("adet"))


def _sirali_listeler(tt, tur):
    """En sik UST_DEGER_ADEDI deger (adet azalan, esitlikte deger artan)
    ve en kucuk ORNEK_UC deger. Doner: ({k: [(v, n)]}, {k: [v]})."""
    from pyspark.sql import Window, functions as F
    sik = Window.partitionBy("k").orderBy(F.col("adet").desc(), F.col("v").asc())
    kucuk = Window.partitionBy("k").orderBy(F.col("v").asc())
    r = tt.withColumn("s1", F.row_number().over(sik)) \
          .withColumn("s2", F.row_number().over(kucuk)) \
          .where((F.col("s1") <= pk.UST_DEGER_ADEDI) | (F.col("s2") <= pk.ORNEK_UC)) \
          .collect()
    ust, ornek = {}, {}
    for x in r:
        if x["s1"] <= pk.UST_DEGER_ADEDI:
            ust.setdefault(x["k"], []).append((x["s1"], x["v"], int(x["adet"])))
        if x["s2"] <= pk.ORNEK_UC:
            ornek.setdefault(x["k"], []).append((x["s2"], x["v"]))
    return ({k: [(v, n) for _s, v, n in sorted(l, key=lambda t: t[0])]
             for k, l in ust.items()},
            {k: [v for _s, v in sorted(l, key=lambda t: t[0])]
             for k, l in ornek.items()})


def _kantiller(spark, tt, tur, dolular):
    """Sayisal kolonlarin KESIN kantilleri (pandas quantile ile ayni formul):
    tekil degerler sirali, birikimli satir sayisi ile gereken sira
    numaralarindaki degerler bulunur. Doner: {k: [5 deger]}."""
    from pyspark.sql import Window, functions as F
    istek = [(int(k), int(p)) for k, n in dolular.items() if n
             for p in pk.kantil_konumlari(int(n))]
    if not istek:
        return {}
    v = F.col("v").cast("int").cast("double") if tur == pk.TUR_MANTIKSAL \
        else F.col("v").cast("double")
    w = Window.partitionBy("k").orderBy(F.col("vd").asc()) \
              .rowsBetween(Window.unboundedPreceding, Window.currentRow)
    birikim = tt.select("k", v.alias("vd"), "adet") \
                .withColumn("son", F.sum("adet").over(w)) \
                .withColumn("bas", F.col("son") - F.col("adet"))
    konum = spark.createDataFrame(istek, "k int, p long")
    eslesen = birikim.join(F.broadcast(konum), "k") \
                     .where((F.col("bas") <= F.col("p")) & (F.col("p") < F.col("son"))) \
                     .select("k", "p", "vd").collect()
    sira = {}
    for x in eslesen:
        sira.setdefault(int(x["k"]), {})[int(x["p"])] = float(x["vd"])
    return {k: pk.kantil_hesapla(int(dolular[k]), s) for k, s in sira.items()}


# ===========================================================================
# 3) DEGER BASINA DENETIM (yurutuculerde)
# ===========================================================================
def _parca_isleyici(turler, gorevler):
    def isle(satirlar):
        kova = {}
        for x in satirlar:
            k = int(x[0])
            b = kova.setdefault(k, ([], []))
            b[0].append(x[1])
            b[1].append(int(x[2]))
            if len(b[0]) >= PARCA_BOYU:
                yield k, pk.parca_degerlendir(turler[k], b[0], b[1], gorevler[k])
                kova[k] = ([], [])
        for k, (vs, ns) in kova.items():
            if vs:
                yield k, pk.parca_degerlendir(turler[k], vs, ns, gorevler[k])
    return isle


def _tarih_isleyici(turler):
    def isle(satirlar):
        kova = {}
        for x in satirlar:
            k = int(x[0])
            b = kova.setdefault(k, ([], []))
            b[0].append(x[1])
            b[1].append(int(x[2]))
            if len(b[0]) >= PARCA_BOYU:
                yield k, pk.tarih_parcasi(turler[k], b[0], b[1])
                kova[k] = ([], [])
        for k, (vs, ns) in kova.items():
            if vs:
                yield k, pk.tarih_parcasi(turler[k], vs, ns)
    return isle


def _gorevli(gorev):
    return bool(gorev.get("donusum") or gorev.get("pii")
                or gorev.get("donem") or gorev.get("metin"))


# ===========================================================================
# ANA FONKSIYON
# ===========================================================================
def spark_profil(spark, df, veri_seti=None):
    """Spark DataFrame -> profil sozlugu (profil_kural.profil_kur ciktisi)."""
    from pyspark import StorageLevel
    from pyspark.sql import functions as F
    from fe_agent import sozluk as sozluk_mod

    _kod_gonder(spark)
    adlar = [str(f.name) for f in df.schema.fields]
    turler = [_tur(f.dataType) for f in df.schema.fields]
    norm = df.select(*[_normal_kolon(F.col("`%s`" % f.name.replace("`", "``")),
                                     turler[i]).alias("c%d" % i)
                       for i, f in enumerate(df.schema.fields)])
    norm = norm.persist(StorageLevel.MEMORY_AND_DISK)
    try:
        satir, ozet = _ilk_gecis(norm, turler)
        duplicate = satir - int(norm.distinct().count()) if satir else 0

        # Tamamen bos kolon tekil tabloya hic girmez: tekil 0, deger
        # listesi bos (None degil; yerel motorla ayni).
        ozetler = {i: dict(ozet[i], ad=adlar[i], tekil=0, degerler=[],
                           ust_degerler=[], ornek3=[], kantiller=None,
                           parca=None, donem_parca=None, donem_degerleri=None)
                   for i in range(len(adlar))}
        for tur in (pk.TUR_TAM, pk.TUR_ONDALIK, pk.TUR_MANTIKSAL,
                    pk.TUR_METIN, pk.TUR_TARIH):
            indeks = [i for i in range(len(adlar))
                      if turler[i] == tur and ozetler[i]["dolu"]]
            if not indeks:
                continue
            tt = _tekil_tablo(norm, indeks, tur).persist(StorageLevel.MEMORY_AND_DISK)
            try:
                for x in tt.groupBy("k").count().collect():
                    ozetler[int(x["k"])]["tekil"] = int(x["count"])
                az = [i for i in indeks
                      if ozetler[i]["tekil"] <= pk.DEGER_LISTE_SINIRI]
                for i in indeks:
                    if ozetler[i]["tekil"] > pk.DEGER_LISTE_SINIRI:
                        ozetler[i]["degerler"] = None
                if az:
                    liste = {}
                    for x in tt.where(F.col("k").isin(az)).collect():
                        liste.setdefault(int(x["k"]), []).append(
                            (x["v"], int(x["adet"])))
                    for i in az:
                        ozetler[i]["degerler"] = sorted(
                            liste.get(i, []), key=lambda t: (-t[1], t[0]))
                ust, kucuk = _sirali_listeler(tt, tur)
                for i in indeks:
                    ozetler[i]["ust_degerler"] = ust.get(i, [])
                    ozetler[i]["ornek3"] = kucuk.get(i, [])
                if tur in pk.SAYISAL_TURLER:
                    kant = _kantiller(spark, tt, tur,
                                      {i: ozetler[i]["dolu"] for i in indeks})
                    for i, k in kant.items():
                        ozetler[i]["kantiller"] = k

                gorevler = {i: pk.gorev_plani(ozetler[i],
                                              sozluk_mod._pii_ad_mi(adlar[i]))
                            for i in indeks}
                is_var = [i for i in indeks if _gorevli(gorevler[i])]
                if is_var:
                    tur_harita = {i: tur for i in is_var}
                    parcalar = (tt.where(F.col("k").isin(is_var))
                                  .select("k", "v", "adet").rdd
                                  .mapPartitions(_parca_isleyici(tur_harita, gorevler))
                                  .reduceByKey(pk.parca_birlestir)
                                  .collectAsMap())
                    for i in is_var:
                        p = parcalar.get(i)
                        ozetler[i]["parca"] = p
                        ozetler[i]["donem_parca"] = (p or {}).get("donem")
                    tarih = [i for i in is_var
                             if pk.tarih_gecisi_gerekli_mi(ozetler[i])]
                    if tarih:
                        ok = (tt.where(F.col("k").isin(tarih))
                                .select("k", "v", "adet").rdd
                                .mapPartitions(_tarih_isleyici({i: tur for i in tarih}))
                                .reduceByKey(lambda a, b: a + b)
                                .collectAsMap())
                        for i in tarih:
                            ozetler[i]["donem_parca"]["tarih_ok"] = float(ok.get(i, 0.0))

                # Donem adaylarinin tekil degerleri (normallestirilmis liste
                # surucude cikarilir; aday kolonlar az ve tekil degerleri
                # sinirli).
                aday = [i for i in indeks
                        if pk.donem_adayi_mi(ozetler[i], satir)
                        and ozetler[i]["tekil"] <= pk.DONEM_DEGER_SINIRI]
                if aday:
                    ham = {}
                    for x in tt.where(F.col("k").isin(aday)).select("k", "v").collect():
                        ham.setdefault(int(x["k"]), []).append(x["v"])
                    for i in aday:
                        ozetler[i]["donem_degerleri"] = pk.donem_degerleri(
                            tur, ham.get(i, []))
            finally:
                tt.unpersist()
    finally:
        norm.unpersist()

    return pk.profil_kur(veri_seti, satir, duplicate,
                         [ozetler[i] for i in range(len(adlar))], "spark")


# ===========================================================================
# DATAIKU RECIPE GIRISI
# ===========================================================================
def _istek():
    """Webapp'in isi baslatmadan once yazdigi proje degiskeni."""
    import dataiku
    try:
        ham = (dataiku.get_custom_variables() or {}).get(ISTEK_DEGISKENI)
    except Exception:           # pylint: disable=broad-except
        return {}
    if isinstance(ham, dict):
        return ham
    try:
        return json.loads(ham) if ham else {}
    except Exception:           # pylint: disable=broad-except
        return {}


def profil_yolu(veri_seti):
    return "/%s/%s" % (veri_seti, PROFIL_DOSYA)


def recete_calistir():
    """PySpark recipe'inin tek satiri. Girdi: profili cikarilacak veri seti.
    Cikti: AMP_PROFIL klasoru (profil /<veri_seti>/profil.json'a yazilir)."""
    import dataiku
    from dataiku import recipe
    from dataiku import spark as dkuspark
    from pyspark import SparkContext
    from pyspark.sql import SQLContext

    girdiler = recipe.get_input_names_for_role("main")
    ciktilar = recipe.get_output_names_for_role("main")
    if len(girdiler) != 1 or len(ciktilar) != 1:
        raise RuntimeError("AMP profil recipe'inin tek girdisi (veri seti) ve "
                           "tek çıktısı (AMP_PROFIL klasörü) olmalı.")
    tam_ad = girdiler[0]
    kisa_ad = tam_ad.split(".")[-1]
    klasor = dataiku.Folder(ciktilar[0].split(".")[-1])

    sc = SparkContext.getOrCreate()
    sql = SQLContext(sc)
    df = dkuspark.get_dataframe(sql, dataiku.Dataset(tam_ad))

    # Webapp veri setini kendi projesindeyse kisa adla ("VERI"), baska
    # projedeyse tam adla ("PROJE.VERI") istiyor. Dataiku girdiyi her zaman
    # tam adla veriyor; iki yazim da ayni veri setidir. Profil webapp'in
    # istedigi adla yazilir ki orada aradigi yerde bulsun.
    istek = _istek()
    eslesir = istek.get("veri_seti") in (tam_ad, kisa_ad)
    veri_ad = istek["veri_seti"] if eslesir else kisa_ad
    baslangic = datetime.datetime.now().isoformat()
    profil = spark_profil(sql.sparkSession, df, veri_ad)
    profil["kosu_id"] = istek.get("kosu_id") if eslesir else None
    profil["_baslangic"] = baslangic
    profil["_bitis"] = datetime.datetime.now().isoformat()
    govde = json.dumps(profil, ensure_ascii=False, default=str).encode("utf-8")
    klasor.upload_stream(profil_yolu(veri_ad), govde)
