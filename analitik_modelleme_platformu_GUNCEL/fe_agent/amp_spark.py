# -*- coding: utf-8 -*-
"""fe_agent/amp_spark.py - AMP_VERISETI'ni YAZAN PySpark recipe'i.

Dataiku'da bir PySpark recipe'i olarak calisir. Recipe'leri ve ciktilarini
webapp KENDISI kurar (spark_is.ISLER); kullanici Flow'a bir sey eklemez.

  compute_AMP_VERISETI : girdi baz veri seti -> AMP_VERISETI (Parquet) +
                         AMP_SONUC klasoru          (recete_calistir)
  compute_AMP_BAZ      : girdi ayni kolonlu kaynak tablolar -> alt alta
                         MODELLEME_BAZ (Parquet) + AMP_BAZ_SONUC klasoru
                                                    (baz_recete_calistir)

NE YAPAR (istek proje degiskeninden, bkz. amp.py)
  1. Tip donusumleri - Degisken Kontrolu'nde secilenler. Kolonun tekil
     degeri azsa (ESLEME_SINIRI) donusum pandas'taki AYNI fonksiyonla
     (tip_donusum.cevir) tekil degerler uzerinde hesaplanir ve tabloya
     eslenir: sonuc eski yolla birebir ayni. Tekil degeri cok olan kolonda
     Spark ifadesi kullanilir. Iki yolda da SON KONTROL var: dolu olup
     cevrilemeyen tek bir hucre bile varsa is DURUR (profil "hepsi
     cevrilir" demisti; sessizce bos hucre uretmek kabul edilmez).
  2. Surec disi kolonlar dusurulur (hedef / kimlik / donem haric).
  3. Bolme istenmisse _SPLIT kolonu yazilir (train / val / test /
     disarida). Sonraki butun adimlar setleri bu kolondan okur.
  4. AMP_VERISETI yazilir; set sayilari ve hedef pozitif sayilari
     AMP_SONUC/sonuc.json'a yazilir (kosu kimligiyle).
"""

import datetime
import json

from fe_agent import profil_kural as pk
from fe_agent import tip_donusum

SONUC_DOSYA = "/sonuc.json"
SPLIT_KOLON = "_SPLIT"
ETIKET = {"egitim": "train", "val": "val", "test": "test", "oot": "oot"}
DISARIDA = "disarida"

# Tekil degeri bu sinirin altindaki kolonda donusum surucude, pandas'taki
# ayni fonksiyonla hesaplanir ve Spark haritasiyla eslenir. Ustunde Spark
# ifadesi kullanilir (son kontrol farki yakalar).
ESLEME_SINIRI = 5000


# ===========================================================================
# TIP DONUSUMLERI
# ===========================================================================
_HEDEF_SPARK = {"sayısal": "double", "tarih": "timestamp", "kategorik": "string"}

_TARIH_DESENI = {"tarih_ymd": "yyyy-M-d", "tarih_dmy": "d.M.yyyy",
                 "tarih_ymd8": "yyyyMMdd", "tarih_ym6": "yyyyMM"}


def _metin_ifadesi(c, tur, tam_sayi):
    """tip_donusum._metin karsiligi: kirpilmis metin; tam sayili ondalik
    kolonda .0 kuyrugu yok."""
    from pyspark.sql import functions as F
    if tur == pk.TUR_ONDALIK and tam_sayi:
        return c.cast("long").cast("string")
    return F.trim(c.cast("string"))


def _yerel_ifade(c, kod, tur, tam_sayi):
    """Tekil degeri COK olan kolon icin Spark ifadesi (tip_donusum.cevir'in
    kurallari). Son kontrol ifadeyle pandas arasindaki farki yakalar.

    Yazimi koruyan donusumde (donem_ym6 / donem_ymd8) deger AYNEN kalir;
    gecerli bir yil-ay(-gun) degilse null doner (denetim ve son kontrol
    icin, tip_donusum.cevir ile ayni)."""
    from pyspark.sql import functions as F
    m = _metin_ifadesi(c, tur, tam_sayi)
    if kod in tip_donusum.KORUYAN_KALIP:
        uzunluk = 6 if kod == "donem_ym6" else 8
        desen = "yyyyMM" if kod == "donem_ym6" else "yyyyMMdd"
        gecerli = (F.length(m) == uzunluk) & m.rlike(r"^\d+$") \
            & F.to_timestamp(m, desen).isNotNull()
        return F.when(gecerli, c)
    if kod == "sayisal_nokta":
        ok = ~m.contains(",") | m.rlike(tip_donusum._BINLIK_KALIP[kod])
        return F.when(ok, F.regexp_replace(m, ",", "").cast("double"))
    if kod == "sayisal_virgul":
        ok = ~m.contains(".") | m.rlike(tip_donusum._BINLIK_KALIP[kod])
        return F.when(ok, F.regexp_replace(F.regexp_replace(m, r"\.", ""),
                                           ",", ".").cast("double"))
    if kod in _TARIH_DESENI:
        return F.to_timestamp(m, _TARIH_DESENI[kod])
    if kod == "kategorik_metin":
        return m
    if kod == "kategorik_ay":
        return F.date_format(c.cast("timestamp"), "yyyy-MM")
    if kod == "kategorik_yil":
        return F.date_format(c.cast("timestamp"), "yyyy")
    if kod == "sayisal_ymd8":
        return F.date_format(c.cast("timestamp"), "yyyyMMdd").cast("double")
    raise ValueError("Bilinmeyen dönüşüm: %s" % kod)


def harita_ifadesi(ciftler, anahtar, anahtar_tipi, deger_tipi):
    """Surucudeki (anahtar, deger) ciftleri -> Spark haritasi ile esleme.

    YURUTUCUDE PYTHON YOK (kurumdaki Spark yurutuculerinde code env yok):
    surucu listesinden createDataFrame yurutucude Python istiyor; harita
    ise saf Spark ifadesidir. Eslenemeyen anahtar null doner."""
    from pyspark.sql import functions as F
    if not ciftler:
        return F.lit(None).cast(deger_tipi)
    parca = []
    for a, d in ciftler:
        parca += [F.lit(a).cast(anahtar_tipi), F.lit(d).cast(deger_tipi)]
    return F.create_map(*parca).getItem(anahtar)


def _esleme_ifadesi(df, kolon, kod, tur, tam_sayi, spark_tipi, ham_kolon):
    """Tekil degerler -> tip_donusum.cevir ile donusmus deger (surucude,
    pandas'la AYNI fonksiyon); tabloya Spark haritasiyla eslenir."""
    from pyspark.sql import functions as F
    import pandas as pd
    ham = [r[0] for r in df.select(F.col("`%s`" % kolon)).where(
        F.col("`%s`" % kolon).isNotNull()).distinct().collect()]
    seri = pk.seri_kur(tur, ham)
    yeni, _t, _o = tip_donusum.cevir(seri, kod, tam_sayi=tam_sayi)
    hedef = tip_donusum.hedef_tip(kod)
    ciftler = []
    for h, y in zip(ham, yeni.tolist()):
        try:
            if y is None or pd.isna(y):
                continue
        except (TypeError, ValueError):
            pass
        if hedef == "tarih":
            y = y.to_pydatetime() if hasattr(y, "to_pydatetime") else y
        elif hedef == "sayısal":
            y = float(y)
        else:
            y = str(y)
        ciftler.append((h, y))
    return harita_ifadesi(ciftler, F.col(ham_kolon), spark_tipi,
                          _HEDEF_SPARK[hedef])


def donusumleri_uygula(spark, df, donusumler):
    """donusumler: {kolon: {"kod", "tam_sayi", "tekil"}}.
    Doner: (yeni_df, {kolon: kontrol_ifadesi_adi})."""
    from pyspark.sql import functions as F
    from fe_agent import profil_spark
    tipler = {f.name: f.dataType for f in df.schema.fields}
    kontrol = {}
    for i, (kolon, d) in enumerate(sorted((donusumler or {}).items())):
        if kolon not in tipler:
            continue
        kod = d.get("kod")
        if not tip_donusum.gecerli_kod(kod) or kod in tip_donusum.KORUYAN_KALIP:
            continue
        tur = profil_spark._tur(tipler[kolon])
        tam = d.get("tam_sayi")
        ham = "__ham_%d" % i
        df = df.withColumn(ham, F.col("`%s`" % kolon))
        if int(d.get("tekil") or ESLEME_SINIRI + 1) <= ESLEME_SINIRI:
            yeni = _esleme_ifadesi(df, kolon, kod, tur, tam, tipler[kolon], ham)
        else:
            yeni = _yerel_ifade(F.col(ham), kod, tur, tam) \
                .cast(_HEDEF_SPARK[tip_donusum.hedef_tip(kod)])
        df = df.withColumn(kolon, yeni)
        kontrol[kolon] = ham
    return df, kontrol


# ===========================================================================
# BOLME
# ===========================================================================
def _donem_normal(tur, degerler):
    """Ham donem degerleri -> {ham: normallesmis metin} (birlestirme ile ayni)."""
    from fe_agent import birlestirme as birl
    seri = birl.donem_serisi(pk.seri_kur(tur, degerler))
    return {h: n for h, n in zip(degerler, seri.tolist()) if n is not None}


def zamansal_esleme(sayim, test_donemleri, val_var, val_oran, gap):
    """{donem: satir} -> {donem: etiket}. akis_durum._setler_zamansal ile
    AYNI kurallar, satir sayilarindan (tablo okumadan)."""
    from fe_agent import birlestirme as birl
    tum = birl.donem_sirala(list(sayim))
    test = [d for d in test_donemleri if d in set(tum)]
    bosluk = set()
    n = int(gap or 0)
    if n > 0 and test:
        kalan = [d for d in tum if d not in set(test)]
        if len(kalan) > 1:
            bosluk = set(kalan[-min(n, len(kalan) - 1):])
    val = set()
    if val_var and test and test[0] in tum:
        onceki = tum[:tum.index(test[0])]
        if len(onceki) >= 2:
            havuz = sum(sayim[d] for d in onceki)
            secili, toplanan = [], 0
            for d in reversed(onceki[1:]):
                secili.append(d)
                toplanan += sayim[d]
                if havuz and toplanan / float(havuz) >= float(val_oran):
                    break
            val = set(secili) - bosluk
    esleme = {}
    for d in tum:
        if d in set(test):
            esleme[d] = ETIKET["test"]
        elif d in bosluk:
            esleme[d] = DISARIDA
        elif d in val:
            esleme[d] = ETIKET["val"]
        else:
            esleme[d] = ETIKET["egitim"]
    return esleme


def katman_araliklari(boyutlar, oranlar):
    """akis_durum._katmanli_bolum_secimi'nin payi: {katman: boyut} ->
    {katman: [(bas, son, ad), ...]} (sira numarasi araliklari)."""
    cikti = {}
    for katman in sorted(boyutlar, key=str):
        uzunluk = int(boyutlar[katman])
        bas, araliklar = 0, []
        for ad, oran in oranlar:
            n = int(round(uzunluk * float(oran)))
            if uzunluk >= len(oranlar) + 1:
                n = max(n, 1)
            n = min(n, uzunluk - bas - 1) if uzunluk > bas + 1 else 0
            if n <= 0:
                continue
            araliklar.append((bas, bas + n, ad))
            bas += n
        cikti[katman] = araliklar
    return cikti


def _siraya_gore_etiket(spark, tablo, anahtar, katman, oranlar):
    """tablo: (katman, anahtar) sutunlari. Katman icinde anahtara gore
    sirala, payi araliklarla dagit. Doner: tablo + _etiket."""
    from pyspark.sql import Window, functions as F
    boyut = {r["katman"]: int(r["count"]) for r in
             tablo.groupBy(F.col(katman).alias("katman")).count().collect()}
    araliklar = katman_araliklari(boyut, oranlar)
    satir = [(k, int(b), int(s), ETIKET[ad])
             for k, liste in araliklar.items() for b, s, ad in liste]
    w = Window.partitionBy(katman).orderBy(anahtar)
    sirali = tablo.withColumn("__sira", F.row_number().over(w) - 1)
    # Katman x set araliklari az (katman sayisi x set sayisi): when zinciri,
    # yurutucude Python gerektirmez.
    etiket = F.lit(ETIKET["egitim"])
    for k, b, e, ad in reversed(satir):
        etiket = F.when((F.col(katman) == F.lit(k)) & (F.col("__sira") >= b)
                        & (F.col("__sira") < e), F.lit(ad)).otherwise(etiket)
    return sirali.withColumn("_etiket", etiket)


def bolme_ekle(spark, df, b):
    """_SPLIT kolonunu ekler. b: webapp'in bolme tarifi (bkz. amp.py)."""
    from pyspark.sql import functions as F
    from fe_agent import profil_spark
    tur = b.get("tur")
    if tur == "hazir":
        if b.get("bicim") == "bayrak":
            es = b.get("esleme") or {}
            def bayrak(ad):
                kol = es.get(ad)
                if not kol:
                    return F.lit(False)
                return F.coalesce(F.col("`%s`" % kol).cast("double"), F.lit(0.0)) != 0
            etiket = (F.when(bayrak("test"), ETIKET["test"])
                       .when(bayrak("oot"), ETIKET["oot"])
                       .when(bayrak("val"), ETIKET["val"])
                       .when(bayrak("egitim"), ETIKET["egitim"])
                       .otherwise(DISARIDA))
        else:
            normal = F.lower(F.trim(F.col("`%s`" % b["kolon"]).cast("string")))
            etiket = F.lit(DISARIDA)
            # Oncelik test > oot > val > egitim (akis_durum._setler_hazir).
            for hedef in ("egitim", "val", "oot", "test"):
                hamlar = [h for h, t in (b.get("esleme") or {}).items() if t == hedef]
                if hamlar:
                    etiket = F.when(normal.isin(hamlar), ETIKET[hedef]).otherwise(etiket)
        return df.withColumn(SPLIT_KOLON, etiket)

    if tur == "zamansal":
        kol = b["kolon"]
        kolon_tur = profil_spark._tur(df.schema[kol].dataType)
        sayim_ham = {r[0]: int(r[1]) for r in
                     df.groupBy(F.col("`%s`" % kol)).count().collect()
                     if r[0] is not None}
        normal = _donem_normal(kolon_tur, list(sayim_ham))
        sayim = {}
        for h, n in sayim_ham.items():
            if h in normal:
                sayim[normal[h]] = sayim.get(normal[h], 0) + n
        esleme = zamansal_esleme(sayim, b.get("test_donemleri") or [],
                                 b.get("val_var"), b.get("val_oran") or 0,
                                 b.get("gap"))
        ciftler = [(h, esleme.get(n, ETIKET["egitim"])) for h, n in normal.items()]
        etiket = harita_ifadesi(ciftler, F.col("`%s`" % kol),
                                df.schema[kol].dataType, "string")
        return df.withColumn(SPLIT_KOLON, F.coalesce(etiket, F.lit(ETIKET["egitim"])))

    # RASTGELE (katmanli): kimlik varsa kimlik duzeyinde, yoksa satir duzeyinde.
    oranlar = [(ad, float(o)) for ad, o in (b.get("oranlar") or [])]
    hedef = b.get("hedef")
    seed = int(b.get("seed") or 42)
    kimlik = b.get("kimlik")
    if kimlik:
        k = F.coalesce(F.col("`%s`" % kimlik).cast("string"), F.lit("__BOS__"))
        if b.get("katmanla") and hedef:
            kt = df.select(k.alias("__id"),
                           F.col("`%s`" % hedef).cast("double").alias("__y")) \
                   .groupBy("__id").agg(F.max("__y").alias("__y"))
            kt = kt.withColumn("__katman", F.coalesce(F.col("__y").cast("string"),
                                                      F.lit("__BOS__")))
        else:
            kt = df.select(k.alias("__id")).distinct() \
                   .withColumn("__katman", F.lit("__TEK__"))
        kt = kt.withColumn("__anahtar", F.xxhash64(F.col("__id"), F.lit(seed)))
        et = _siraya_gore_etiket(spark, kt, "__anahtar", "__katman", oranlar) \
            .select("__id", F.col("_etiket").alias(SPLIT_KOLON))
        df = df.withColumn("__id", k).join(et, "__id", "left").drop("__id")
        return df.withColumn(SPLIT_KOLON, F.coalesce(F.col(SPLIT_KOLON),
                                                     F.lit(ETIKET["egitim"])))

    katman = (F.coalesce(F.col("`%s`" % hedef).cast("string"), F.lit("__BOS__"))
              if b.get("katmanla") and hedef else F.lit("__TEK__"))
    # BELIRLENIMCI ANAHTAR: rand() her eylemde (yazma, sayim) yeniden
    # uretilebilir ve yazilan etiketle raporlanan sayi ayrisabilirdi. Satirin
    # butun kolonlari + seed'in ozeti her seferinde ayni sirayi verir; ayni
    # ozeti tasiyan satirlar birebir ayni satirlardir.
    ozet = F.xxhash64(*[F.col("`%s`" % c) for c in df.columns], F.lit(seed))
    df = df.withColumn("__katman", katman).withColumn("__anahtar", ozet)
    df = _siraya_gore_etiket(spark, df, "__anahtar", "__katman", oranlar)
    return df.withColumnRenamed("_etiket", SPLIT_KOLON) \
             .drop("__katman", "__anahtar", "__sira")


# ===========================================================================
# ANA FONKSIYON
# ===========================================================================
def amp_hazirla(spark, df, istek):
    """Doner: (yazilacak_df, sonuc_sozlugu). sonuc["hata"] doluysa YAZILMAZ."""
    from pyspark.sql import functions as F
    # Gecersiz tarih metni null olsun, istisna atmasin (Spark 3 ayristiricisi).
    spark.conf.set("spark.sql.legacy.timeParserPolicy", "CORRECTED")
    df, kontrol = donusumleri_uygula(spark, df, istek.get("donusum"))

    b = istek.get("bolme")
    if b:
        df = bolme_ekle(spark, df, b)

    hedef = istek.get("hedef")
    ifade = [F.count(F.lit(1)).alias("__satir")]
    for kolon, ham in kontrol.items():
        ifade.append(F.count(F.when(F.col(ham).isNotNull() & F.col("`%s`" % kolon).isNull(),
                                    1)).alias("__k_" + ham))
    toplam = df.agg(*ifade).collect()[0].asDict()
    takilan = {kolon: int(toplam["__k_" + ham]) for kolon, ham in kontrol.items()
               if int(toplam["__k_" + ham])}
    sonuc = {"satir": int(toplam["__satir"])}
    if takilan:
        sonuc["hata"] = ("Tip dönüşümü tam veride uygulanamadı; çevrilemeyen "
                         "dolu hücre: " + ", ".join("%s (%s)" % (k, n)
                                                   for k, n in sorted(takilan.items())))
        return None, sonuc

    df = df.drop(*kontrol.values())
    dusen = [c for c in (istek.get("dusen") or []) if c in df.columns]
    df = df.drop(*dusen)
    sonuc["dusen"] = dusen
    sonuc["kolon"] = len(df.columns)

    if b:
        y = (F.col("`%s`" % hedef).cast("double") > 0) if hedef and hedef in df.columns \
            else F.lit(False)
        sayim = df.groupBy(SPLIT_KOLON).agg(
            F.count(F.lit(1)).alias("n"),
            F.count(F.when(y, 1)).alias("poz")).collect()
        sonuc["setler"] = {r[SPLIT_KOLON]: {"satir": int(r["n"]), "pozitif": int(r["poz"])}
                           for r in sayim}
    return df, sonuc


def recete_calistir():
    """PySpark recipe'inin tek satiri."""
    import dataiku
    from dataiku import recipe
    from dataiku import spark as dkuspark
    from pyspark import SparkContext
    from pyspark.sql import SQLContext
    from fe_agent import spark_is

    girdiler = recipe.get_input_names_for_role("main")
    ciktilar = recipe.get_output_names_for_role("main")
    if len(girdiler) != 1:
        raise RuntimeError("AMP_VERISETI recipe'inin tek girdisi olmalı.")
    veri_cikti = [c for c in ciktilar if c.split(".")[-1] == "AMP_VERISETI"] or \
        [c for c in ciktilar if "SONUC" not in c.upper()]
    klasor_cikti = [c for c in ciktilar if c not in veri_cikti]
    if not veri_cikti or not klasor_cikti:
        raise RuntimeError("AMP_VERISETI recipe'inin çıktıları AMP_VERISETI "
                           "veri seti ve AMP_SONUC klasörü olmalı.")
    klasor = dataiku.Folder(klasor_cikti[0].split(".")[-1])

    tam_ad = girdiler[0]
    istek = spark_is.istek_oku(spark_is.istek_degiskeni("amp"))
    eslesir = istek.get("veri_seti") in (tam_ad, tam_ad.split(".")[-1])
    sonuc = {"kosu_id": istek.get("kosu_id") if eslesir else None,
             "_baslangic": datetime.datetime.now().isoformat()}
    if not eslesir:
        sonuc["hata"] = ("İstek bu veri setine ait değil (istek: %s, girdi: %s)."
                         % (istek.get("veri_seti"), tam_ad))
        klasor.upload_stream(SONUC_DOSYA, json.dumps(sonuc, ensure_ascii=False).encode("utf-8"))
        raise RuntimeError(sonuc["hata"])

    sc = SparkContext.getOrCreate()
    sql = SQLContext(sc)
    df = dkuspark.get_dataframe(sql, dataiku.Dataset(tam_ad))
    yeni, oz = amp_hazirla(sql.sparkSession, df, istek)
    sonuc.update(oz)
    if yeni is not None:
        dkuspark.write_with_schema(dataiku.Dataset(veri_cikti[0]), yeni)
    sonuc["_bitis"] = datetime.datetime.now().isoformat()
    klasor.upload_stream(SONUC_DOSYA, json.dumps(sonuc, ensure_ascii=False,
                                                 default=str).encode("utf-8"))
    if yeni is None:
        raise RuntimeError(sonuc.get("hata") or "AMP_VERISETI yazılamadı.")


def baz_recete_calistir():
    """compute_AMP_BAZ: ayni kolonlu kaynak tablolar ALT ALTA -> MODELLEME_BAZ.
    Kolonlar adla eslenir (sira farkli olabilir); tipler Spark'in birlesim
    kurallariyla genisletilir. Tablo basina satir sayisi sonuca yazilir."""
    import functools
    import dataiku
    from dataiku import recipe
    from dataiku import spark as dkuspark
    from pyspark import SparkContext
    from pyspark.sql import SQLContext
    from fe_agent import spark_is

    girdiler = recipe.get_input_names_for_role("main")
    ciktilar = recipe.get_output_names_for_role("main")
    veri_cikti = [c for c in ciktilar if c.split(".")[-1] == "MODELLEME_BAZ"]
    klasor_cikti = [c for c in ciktilar if c not in veri_cikti]
    if len(girdiler) < 2 or not veri_cikti or not klasor_cikti:
        raise RuntimeError("compute_AMP_BAZ recipe'inin en az iki girdisi, "
                           "MODELLEME_BAZ veri seti ve bir sonuç klasörü çıktısı olmalı.")
    klasor = dataiku.Folder(klasor_cikti[0].split(".")[-1])
    istek = spark_is.istek_oku(spark_is.istek_degiskeni("baz"))
    kisa = lambda ad: str(ad).split(".")[-1]         # noqa: E731
    eslesir = sorted(map(kisa, istek.get("girdiler") or [])) == sorted(map(kisa, girdiler))
    sonuc = {"kosu_id": istek.get("kosu_id") if eslesir else None,
             "_baslangic": datetime.datetime.now().isoformat()}

    sc = SparkContext.getOrCreate()
    sql = SQLContext(sc)
    tablolar, parcalar, kolonlar = {}, [], None
    # Istekteki sira (kullanicinin secim sirasi) korunur.
    sira = [g for k in (istek.get("girdiler") or []) for g in girdiler
            if kisa(g) == kisa(k)] or list(girdiler)
    for g in sira:
        df = dkuspark.get_dataframe(sql, dataiku.Dataset(g))
        ad_kumesi = set(df.columns)
        if kolonlar is None:
            kolonlar = list(df.columns)
        elif ad_kumesi != set(kolonlar):
            sonuc["hata"] = ("%s tablosunun kolonları diğer tablolarla aynı değil; "
                             "alt alta eklenemez." % kisa(g))
            break
        tablolar[kisa(g)] = {"satir": int(df.count()), "kolon": len(df.columns)}
        parcalar.append(df.select(*kolonlar))
    if not sonuc.get("hata"):
        birlesik = functools.reduce(lambda a, b: a.unionByName(b), parcalar)
        dkuspark.write_with_schema(dataiku.Dataset(veri_cikti[0]), birlesik)
        sonuc.update({"tablolar": tablolar, "kolon": len(kolonlar),
                      "satir": sum(t["satir"] for t in tablolar.values())})
    sonuc["_bitis"] = datetime.datetime.now().isoformat()
    klasor.upload_stream(SONUC_DOSYA, json.dumps(sonuc, ensure_ascii=False,
                                                 default=str).encode("utf-8"))
    if sonuc.get("hata"):
        raise RuntimeError(sonuc["hata"])
