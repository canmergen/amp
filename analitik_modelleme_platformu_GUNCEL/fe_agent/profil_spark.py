# -*- coding: utf-8 -*-
"""fe_agent/profil_spark.py - VERI SETI PROFILI, PySpark MOTORU.

Dataiku'da bir PySpark recipe'i (compute_AMP_PROFIL) olarak calisir;
recipe'i ve AMP_PROFIL klasorunu webapp KENDISI kurar (spark_is.ISLER).
Recipe'in TEK girdisi profili cikarilacak veri seti. Webapp isi baslatir
ve bitince AMP_PROFIL/<veri_seti>/profil.json dosyasini okur.

HESAP (hepsi KESIN; yaklasik sayim ve orneklem yok)
  1. Tekil degerler: her kolonun (deger, satir sayisi) tablosu - ayni
     turdeki kolon grubu (TOPLU_KOLON) bir "uzun" tabloda groupBy.
  2. Birinci gecis (dolu/bos, tekil, min/maks, tam sayi, donem bicimi),
     en sik degerler, kantiller ve 50'den az seviyeli kolonlarin deger
     listesi bu tablodan.
  3. Tekrarlanan satir: satir sayisi - tekil satir sayisi (128 bit ozet).
  4. Deger basina denetim (tip donusumu, kisisel veri deseni, donem
     yazimlari): tekil degerler surucuye alinip profil_kural'in ayni
     fonksiyonlariyla denetlenir; cok tekilli kolonda Spark ifadeleriyle.
     YURUTUCUDE PYTHON CALISMAZ (kurumdaki yurutucu imajinda code env yok).
  Kurallar profil_kural.py'de; ayni kurallar yerel motorda da calisir ve
  iki motorun ayni tabloda ayni sonucu verdigi test ediliyor.
"""

import datetime
import json

from fe_agent import profil_kural as pk

# Tekil deger denetiminde tek seferde islenen deger sayisi (bellek siniri).
PARCA_BOYU = 50000
# Tek "uzun" tekil deger tablosuna giren kolon sayisi (genis tabloda her
# grup ayri islenir; 30.000 kolonda da tek tablo sismez).
TOPLU_KOLON = 150

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
    # Spark 3.4+ saat dilimsiz zaman damgasini TimestampNTZType okur; o da tarih.
    tarih_tipleri = tuple(t for t in (T.DateType, T.TimestampType,
                                      getattr(T, "TimestampNTZType", None)) if t)
    if isinstance(veri_tipi, tarih_tipleri):
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


# ===========================================================================
# 1) BIRINCI GECIS - tekil deger tablosundan
# ===========================================================================
def _bos_ozet(ad, tur, satir):
    return {"ad": ad, "tur": tur, "dolu": 0, "bos": satir, "ornek": None,
            "min": None, "max": None, "hepsi_tam": False, "n_sonlu": 0,
            "n_kesirli": 0, "pozitif": None, "n_pii_aday": 0,
            "ym_degil": None, "ymd_degil": None, "tekil": 0, "degerler": [],
            "ust_degerler": [], "ornek3": [], "kantiller": None, "parca": None,
            "donem_parca": None, "donem_degerleri": None}


def _tt_ozetleri(tt, tur):
    """Birinci gecis sayilari TEKIL DEGER TABLOSUNDAN (k, v, adet): tek
    groupBy. Genis tabloda kolon basina ayri toplam ifadesi Spark'in sorgu
    planini sisiriyordu (1.042 kolonda 119 sn, 10.000 satirda bile); bu
    sorgunun boyutu kolon sayisiyla BUYUMEZ. Sayimlar degere gore adetle
    agirlikli oldugu icin sonuc satir satir sayimla birebir aynidir."""
    from pyspark.sql import functions as F
    w = F.col("adet")
    ifade = [F.sum(w).alias("dolu"), F.count(F.lit(1)).alias("tekil"),
             F.first("v").alias("ornek")]
    if tur in pk.SAYISAL_TURLER:
        v = F.col("v").cast("int").cast("double") if tur == pk.TUR_MANTIKSAL \
            else F.col("v").cast("double")
        sonsuz = (v == float("inf")) | (v == float("-inf"))
        a = F.abs(v)
        ym = v.between(pk.YM_ALT, pk.YM_UST) & (v % 100).between(1, 12)
        ymd = (v.between(pk.YMD_ALT, pk.YMD_UST)
               & (F.floor(v / 100) % 100).between(1, 12)
               & (v % 100).between(1, 31))
        topla = lambda kosul: F.coalesce(F.sum(F.when(kosul, w)), F.lit(0))  # noqa: E731
        ifade += [F.min(v).alias("mn"), F.max(v).alias("mx"),
                  topla(~sonsuz).alias("sonlu"),
                  topla(~sonsuz & ((v % 1) != 0)).alias("kesir"),
                  topla(v > 0).alias("poz"),
                  topla(~sonsuz & ((a % 1) == 0) & (a >= pk.PII_SAYI_ALT)
                        & (a < pk.PII_SAYI_UST)).alias("pii"),
                  topla(~F.coalesce(ym, F.lit(False))).alias("ym"),
                  topla(~F.coalesce(ymd, F.lit(False))).alias("ymd")]
    elif tur == pk.TUR_TARIH:
        ifade += [F.min("v").alias("mn"), F.max("v").alias("mx")]
    return {int(r["k"]): r.asDict() for r in tt.groupBy("k").agg(*ifade).collect()}


def _ozeti_doldur(oz, tur, r):
    dolu = int(r["dolu"])
    oz.update({"dolu": dolu, "bos": oz["bos"] - dolu, "tekil": int(r["tekil"]),
               "ornek": r.get("ornek")})
    if tur in pk.SAYISAL_TURLER and dolu:
        oz.update({"min": r["mn"], "max": r["mx"], "n_sonlu": int(r["sonlu"]),
                   "n_kesirli": int(r["kesir"]), "pozitif": int(r["poz"]),
                   "n_pii_aday": int(r["pii"]), "ym_degil": int(r["ym"]),
                   "ymd_degil": int(r["ymd"])})
        oz["hepsi_tam"] = (oz["n_sonlu"] == dolu and not oz["n_kesirli"])
    elif tur == pk.TUR_TARIH and dolu:
        oz["min"], oz["max"] = r["mn"], r["mx"]


def _tekrar_sayisi(norm, satir):
    """Tekrarlanan satir sayisi. Butun kolonlarin DISTINCT'i 135 milyon x
    1.040 kolonda butun tabloyu karistirirdi; yerine her satirin iki
    bagimsiz 64 bitlik ozeti (toplam 128 bit) sayilir. Iki farkli satirin
    ayni 128 bitlik ozete dusme olasiligi 135 milyon satirda ~1e-22'dir:
    pratikte kesin sayim."""
    from pyspark.sql import functions as F
    if not satir:
        return 0
    kolonlar = [F.col(c) for c in norm.columns]
    ozet = norm.select(F.xxhash64(*kolonlar, F.lit(1)).alias("h1"),
                       F.xxhash64(*kolonlar, F.lit(2)).alias("h2"))
    return satir - int(ozet.distinct().count())


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


def _kantiller(tt, tur, dolular):
    """Sayisal kolonlarin KESIN kantilleri (pandas quantile ile ayni formul):
    tekil degerler sirali, birikimli satir sayisi ile gereken sira
    numaralarindaki degerler bulunur. Doner: {k: [5 deger]}.

    Gereken sira numaralari Spark icinde, kolonun dolu satir sayisindan
    hesaplanir; surucuden tablo gonderilmez (yurutucude Python gerekmesin)."""
    from pyspark.sql import Window, functions as F
    if not any(dolular.values()):
        return {}
    v = F.col("v").cast("int").cast("double") if tur == pk.TUR_MANTIKSAL \
        else F.col("v").cast("double")
    w = Window.partitionBy("k").orderBy(F.col("vd").asc()) \
              .rowsBetween(Window.unboundedPreceding, Window.currentRow)
    birikim = tt.select("k", v.alias("vd"), "adet") \
                .withColumn("son", F.sum("adet").over(w)) \
                .withColumn("bas", F.col("son") - F.col("adet")) \
                .withColumn("n", F.sum("adet").over(Window.partitionBy("k")))
    kosul = F.lit(False)
    for q in pk.KANTIL_NOKTALARI:
        p = (F.col("n") - 1) * F.lit(float(q))
        for sira in (F.floor(p), F.ceil(p)):
            kosul = kosul | ((F.col("bas") <= sira) & (sira < F.col("son")))
    satirlar = birikim.where(kosul).select("k", "vd", "bas", "son").collect()
    aralik = {}
    for x in satirlar:
        aralik.setdefault(int(x["k"]), []).append(
            (int(x["bas"]), int(x["son"]), float(x["vd"])))
    cikti = {}
    for k, liste in aralik.items():
        n = int(dolular[k])
        sira_deger = {}
        for p in pk.kantil_konumlari(n):
            for b, e, vd in liste:
                if b <= p < e:
                    sira_deger[p] = vd
                    break
        cikti[k] = pk.kantil_hesapla(n, sira_deger)
    return cikti


# ===========================================================================
# 3) DEGER BASINA DENETIM - YURUTUCUDE PYTHON YOK
# ===========================================================================
# Kurumdaki Spark yurutuculeri code env'siz imajla aciliyor (Python/pandas
# yok; kullanici: "önceden spark okuyabiliyordum", kendi kodu saf Spark).
# Bu yuzden yurutucude Python calistiran hicbir sey (rdd.map, UDF, surucu
# listesinden createDataFrame) KULLANILMAZ:
#   - Tekil degeri SURUCU_SINIRI'nin altindaki kolon: tekil degerler ve
#     satir sayilari surucuye alinir, profil_kural'in AYNI fonksiyonlariyla
#     denetlenir (sonuc yerel motorla birebir ayni).
#   - Ustundeki kolon: ayni kurallar Spark ifadeleriyle (regex, tip
#     cevirme, tarih kaliplari) tek bir toplu sorguda sayilir.
SURUCU_SINIRI = 200000
# Surucuye bir seferde alinacak toplam tekil deger (bellek siniri).
TOPLU_SATIR = 2000000


def _metin_ifadesi(v, tur):
    """pandas astype(str) karsiligi: tam sayili ondalik deger ".0" ile
    ("12345678901.0"), ustel gosterim olmadan (Spark'in "1.2E10"u degil)."""
    from pyspark.sql import functions as F
    if tur == pk.TUR_ONDALIK:
        tam = (v == F.floor(v)) & (F.abs(v) < 1e18)
        return F.when(tam, F.concat(v.cast("long").cast("string"), F.lit(".0"))) \
                .otherwise(v.cast("string"))
    return v.cast("string")


def _tckn_sezgi(sade):
    """sozluk._tckn_sezgi'nin Spark ifadesi (kontrol basamaklari)."""
    from pyspark.sql import functions as F
    d = [F.substring(sade, i, 1).cast("int") for i in range(1, 12)]
    tek = d[0] + d[2] + d[4] + d[6] + d[8]
    cift = d[1] + d[3] + d[5] + d[7]
    return (sade.rlike(r"^[1-9]\d{10}$")
            & (F.pmod(tek * 7 - cift, F.lit(10)) == d[9])
            & (F.pmod(d[0] + d[1] + d[2] + d[3] + d[4] + d[5] + d[6] + d[7]
                      + d[8] + d[9], F.lit(10)) == d[10]))


_TARIH_KALIPLARI = ("yyyy-M-d", "yyyy/M/d", "yyyy.M.d", "d.M.yyyy", "d/M/yyyy",
                    "d-M-yyyy", "yyyy-M-d H:m:s", "yyyy-M-d'T'H:m:s",
                    "yyyy-M-d H:m:s.SSS", "d.M.yyyy H:m:s", "d/M/yyyy H:m:s",
                    "MMM yyyy", "d MMM yyyy", "MMMM yyyy", "d MMMM yyyy")


def _donem_ifadeleri(v):
    """METIN kolonda birlestirme._donem_coz'un deger basina bayraklari."""
    from pyspark.sql import functions as F
    from fe_agent import birlestirme as birl
    t = F.trim(v.cast("string"))
    bos = F.lower(t).isin(list(birl.DONEM_BOS_YAZIMLAR))
    d = F.when(bos, F.lit(None).cast("string")) \
         .otherwise(F.regexp_replace(t, r"^(-?\d+)\.0+$", "$1"))
    sayi = d.cast("double")
    sayi_ok = sayi.isNotNull() & ~F.isnan(sayi)
    ym = sayi.between(pk.YM_ALT, pk.YM_UST) & (sayi % 100).between(1, 12)
    ymd = (sayi.between(pk.YMD_ALT, pk.YMD_UST)
           & (F.floor(sayi / 100) % 100).between(1, 12)
           & (sayi % 100).between(1, 31))
    yil_ay = F.lit(False)
    for kalip, yil_i, ay_i in ((birl._YIL_AY_KALIP.pattern, 1, 2),
                               (birl._AY_YIL_KALIP.pattern, 2, 1)):
        yil = F.regexp_extract(d, kalip, yil_i).cast("int")
        ay = F.regexp_extract(d, kalip, ay_i).cast("int")
        yil_ay = yil_ay | F.coalesce(yil.between(1900, 2999) & ay.between(1, 12),
                                     F.lit(False))
    tarih = F.coalesce(*[F.to_timestamp(d, k) for k in _TARIH_KALIPLARI])
    benzer = d.rlike(birl._TARIH_YIL_KALIP) & d.rlike(birl._TARIH_AYIRICI_KALIP)
    tarih_ok = tarih.isNotNull() & benzer
    return d, sayi_ok, F.coalesce(ym, F.lit(False)), F.coalesce(ymd, F.lit(False)), \
        yil_ay, tarih_ok


def _spark_ile_denetle(tt, k, tur, gorev, ozet):
    """Tekil degeri cok olan TEK kolon: ayni kurallar Spark ifadeleriyle,
    tek toplu sorguda. Doner: profil_kural parcasi ile ayni yapi."""
    from pyspark.sql import functions as F
    from fe_agent import amp_spark
    from fe_agent import sozluk as sozluk_mod
    v, w = F.col("v"), F.col("adet")
    t = tt.where(F.col("k") == k)
    metin = F.trim(_metin_ifadesi(v, tur))
    ifade, parca = [F.sum(w).alias("n")], {"donusum": {}, "pii": None,
                                           "donem": None, "uzunluk": None,
                                           "metin": None}
    kodlar = list(gorev.get("donusum") or [])
    for j, kod in enumerate(kodlar):
        yeni = amp_spark._yerel_ifade(v, kod, tur, gorev.get("tam_sayi"))
        takildi = yeni.isNull()
        ifade += [F.sum(F.when(takildi, w)).alias("t%d" % j),
                  F.min(F.when(takildi, F.substring(v.cast("string"), 1, 24))).alias("o%d" % j)]
    if gorev.get("pii"):
        ornek = F.regexp_replace(metin, r"\.0$", "")
        sade = F.regexp_replace(ornek, r"[\s\-()]", "")
        desen = {"e-posta": ornek.rlike(sozluk_mod._DESEN_EPOSTA.pattern),
                 "IBAN": sade.rlike("(?i)" + sozluk_mod._DESEN_IBAN.pattern),
                 "telefon": sade.rlike(sozluk_mod._DESEN_TELEFON.pattern),
                 "TC kimlik no": sade.rlike(sozluk_mod._DESEN_TCKN.pattern),
                 "kart numarası": sade.rlike(sozluk_mod._DESEN_KART.pattern),
                 "tckn_sezgi": _tckn_sezgi(sade)}
        for j, (ad, kosul) in enumerate(desen.items()):
            ifade.append(F.sum(F.when(kosul, w)).alias("p%d" % j))
    if gorev.get("metin"):
        ifade += [F.sum(F.length(v.cast("string")) * w).alias("uz"),
                  F.sum(F.when(metin.rlike(r"^0\d"), w)).alias("kg"),
                  F.sum(F.when(metin.contains(","), w)).alias("vg")]
    if gorev.get("donem"):
        d, sayi_ok, ym, ymd, yil_ay, tarih_ok = _donem_ifadeleri(v)
        dolu = d.isNotNull()
        ifade += [F.sum(F.when(dolu, w)).alias("d_dolu"),
                  F.sum(F.when(dolu & ~sayi_ok, w)).alias("d_sayi"),
                  F.sum(F.when(dolu & sayi_ok & ~ym, w)).alias("d_ym"),
                  F.sum(F.when(dolu & sayi_ok & ~ymd, w)).alias("d_ymd"),
                  F.sum(F.when(dolu & ~yil_ay, w)).alias("d_yilay"),
                  F.sum(F.when(dolu & tarih_ok, w)).alias("d_tarih")]
    r = t.agg(*ifade).collect()[0].asDict()
    f = lambda a: float(r.get(a) or 0.0)
    for j, kod in enumerate(kodlar):
        parca["donusum"][kod] = {"takilan": f("t%d" % j),
                                 "ornek": [r["o%d" % j]] if r.get("o%d" % j) else [],
                                 "hata": None}
    if gorev.get("pii"):
        adlar = ["e-posta", "IBAN", "telefon", "TC kimlik no", "kart numarası",
                 "tckn_sezgi"]
        parca["pii"] = dict({ad: f("p%d" % j) for j, ad in enumerate(adlar)}, n=f("n"))
    if gorev.get("metin"):
        parca["uzunluk"] = {"toplam": f("uz"), "n": f("n")}
        parca["metin"] = {"kod_gibi": f("kg"), "virgul": f("vg")}
    if gorev.get("donem"):
        parca["donem"] = {"dolu": f("d_dolu"), "sayi_degil": f("d_sayi"),
                          "ym_degil": f("d_ym"), "ymd_degil": f("d_ymd"),
                          "yil_ay_degil": f("d_yilay"), "tarih_ok": None}
    ozet["parca"] = parca
    ozet["donem_parca"] = parca.get("donem")
    if pk.tarih_gecisi_gerekli_mi(ozet):
        ozet["donem_parca"]["tarih_ok"] = f("d_tarih")


def _kolon_python(oz, tur, degerler, adetler, gorev):
    """Tekil degerleri surucude olan kolonun butun alanlari - yerel motorla
    (profil_kural.yerel_profil) AYNI fonksiyonlar."""
    import numpy as np
    sira = sorted(zip(degerler, adetler), key=lambda x: (-x[1], x[0]))
    oz["degerler"] = ([(v, int(n)) for v, n in sira]
                      if oz["tekil"] <= pk.DEGER_LISTE_SINIRI else None)
    oz["ust_degerler"] = [(v, int(n)) for v, n in sira[:pk.UST_DEGER_ADEDI]]
    oz["ornek3"] = sorted(degerler)[:pk.ORNEK_UC]
    if tur in pk.SAYISAL_TURLER and oz["dolu"]:
        sirali = sorted(zip([float(v) for v in degerler], adetler))
        oz["kantiller"] = pk.siradan_kantil([v for v, _ in sirali],
                                            [c for _, c in sirali], oz["dolu"])
    if gorev is not None and _gorevli(gorev):
        adet_np = np.asarray(adetler, dtype="int64")
        parca = None
        for bas in range(0, max(len(degerler), 1), PARCA_BOYU):
            p = pk.parca_degerlendir(tur, degerler[bas:bas + PARCA_BOYU],
                                     adet_np[bas:bas + PARCA_BOYU], gorev)
            parca = p if parca is None else pk.parca_birlestir(parca, p)
        oz["parca"] = parca
        oz["donem_parca"] = (parca or {}).get("donem")
        if pk.tarih_gecisi_gerekli_mi(oz):
            oz["donem_parca"]["tarih_ok"] = pk.tarih_parcasi(tur, degerler, adet_np)


def _partiler(indeks, ozetler):
    """Surucuye bir seferde alinacak toplam tekil deger TOPLU_SATIR'i
    asmayacak sekilde kolon partileri."""
    partiler, parti, toplam = [], [], 0
    for i in indeks:
        n = int(ozetler[i]["tekil"])
        if parti and toplam + n > TOPLU_SATIR:
            partiler.append(parti)
            parti, toplam = [], 0
        parti.append(i)
        toplam += n
    if parti:
        partiler.append(parti)
    return partiler


def _grup_isle(tt, indeks, tur, adlar, ozetler, satir):
    """Bir kolon grubunun (ayni tur) tekil deger tablosundan butun profil
    alanlari.

    IS SAYISI AZ: tekil degeri SURUCU_SINIRI'nin altindaki kolonlarin
    (tipik tabloda neredeyse hepsi) degerleri partiler halinde TEK
    sorguyla surucuye alinir; listeler, kantiller, deger denetimleri ve
    donem degerleri yerel motorla ayni Python fonksiyonlariyla hesaplanir.
    Kolon basina ayri Spark isi calistirmak genis tabloda her isin sabit
    maliyetini binlerce kez odetiyordu. Yalnizca cok tekilli kolonlar
    Spark ifadeleriyle islenir."""
    from pyspark.sql import functions as F
    from fe_agent import sozluk as sozluk_mod
    istatistik = _tt_ozetleri(tt, tur)
    for i in indeks:
        if i in istatistik:
            _ozeti_doldur(ozetler[i], tur, istatistik[i])
    # Tamamen bos kolon tekil tabloya hic girmez: tekil 0, deger listesi bos.
    indeks = [i for i in indeks if ozetler[i]["dolu"]]
    if not indeks:
        return
    gorevler = {i: pk.gorev_plani(ozetler[i], sozluk_mod._pii_ad_mi(adlar[i]))
                for i in indeks}

    az = [i for i in indeks if ozetler[i]["tekil"] <= SURUCU_SINIRI]
    for parti in _partiler(az, ozetler):
        kova = {}
        for x in tt.where(F.col("k").isin(parti)).select("k", "v", "adet").collect():
            b = kova.setdefault(int(x["k"]), ([], []))
            b[0].append(x["v"])
            b[1].append(int(x["adet"]))
        for i in parti:
            degerler, adetler = kova.get(i, ([], []))
            _kolon_python(ozetler[i], tur, degerler, adetler, gorevler[i])
            if pk.donem_adayi_mi(ozetler[i], satir) \
                    and ozetler[i]["tekil"] <= pk.DONEM_DEGER_SINIRI:
                ozetler[i]["donem_degerleri"] = pk.donem_degerleri(tur, degerler)

    cok = [i for i in indeks if ozetler[i]["tekil"] > SURUCU_SINIRI]
    if not cok:
        return
    tc = tt.where(F.col("k").isin(cok))
    # Deger listesi ve donem degerleri yalnizca AZ tekilli kolonda gerekir;
    # SURUCU_SINIRI bunlarin ustunde oldugu icin normalde bu dala dusmezler,
    # sinir dusuk ayarlanirsa da ayni sonuc cikmali.
    kisa = [i for i in cok if ozetler[i]["tekil"] <= pk.DEGER_LISTE_SINIRI]
    donem = [i for i in cok if ozetler[i]["tekil"] <= pk.DONEM_DEGER_SINIRI
             and pk.donem_adayi_mi(ozetler[i], satir)]
    ham = {}
    if kisa or donem:
        for x in tc.where(F.col("k").isin(sorted(set(kisa) | set(donem)))) \
                   .select("k", "v", "adet").collect():
            ham.setdefault(int(x["k"]), []).append((x["v"], int(x["adet"])))
    for i in cok:
        ozetler[i]["degerler"] = (sorted(ham.get(i, []), key=lambda t: (-t[1], t[0]))
                                  if i in kisa else None)
    for i in donem:
        ozetler[i]["donem_degerleri"] = pk.donem_degerleri(
            tur, [v for v, _n in ham.get(i, [])])
    ust, kucuk = _sirali_listeler(tc, tur)
    for i in cok:
        ozetler[i]["ust_degerler"] = ust.get(i, [])
        ozetler[i]["ornek3"] = kucuk.get(i, [])
    if tur in pk.SAYISAL_TURLER:
        kant = _kantiller(tc, tur, {i: ozetler[i]["dolu"] for i in cok})
        for i, k in kant.items():
            ozetler[i]["kantiller"] = k
    for i in cok:
        if _gorevli(gorevler[i]):
            _spark_ile_denetle(tt, i, tur, gorevler[i], ozetler[i])


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

    # Gecersiz tarih metni null olsun, istisna atmasin (Spark 3 ayristiricisi).
    spark.conf.set("spark.sql.legacy.timeParserPolicy", "CORRECTED")
    adlar = [str(f.name) for f in df.schema.fields]
    turler = [_tur(f.dataType) for f in df.schema.fields]
    norm = df.select(*[_normal_kolon(F.col("`%s`" % f.name.replace("`", "``")),
                                     turler[i]).alias("c%d" % i)
                       for i, f in enumerate(df.schema.fields)])
    # NORM TABLO SAKLANMAZ (persist yok): 135 milyon x 1.040 kolonu bellege /
    # diske almak kumeyi zorlar. Her kolon grubu Parquet'ten YALNIZCA kendi
    # kolonlarini okur; boylece genis tabloda da okuma grup basina kucuk.
    try:
        satir = int(norm.count())
        duplicate = _tekrar_sayisi(norm, satir)
        ozetler = {i: _bos_ozet(adlar[i], turler[i], satir) for i in range(len(adlar))}
        for tur in (pk.TUR_TAM, pk.TUR_ONDALIK, pk.TUR_MANTIKSAL,
                    pk.TUR_METIN, pk.TUR_TARIH):
            turdekiler = [i for i in range(len(adlar)) if turler[i] == tur]
            # Kolon GRUPLARI halinde: 30.000 kolonluk tabloda da her uzun
            # tablo en fazla TOPLU_KOLON kolonun degerlerini tasir.
            for bas in range(0, len(turdekiler), TOPLU_KOLON):
                grup = turdekiler[bas:bas + TOPLU_KOLON]
                tt = _tekil_tablo(norm, grup, tur).persist(StorageLevel.MEMORY_AND_DISK)
                try:
                    _grup_isle(tt, grup, tur, adlar, ozetler, satir)
                finally:
                    tt.unpersist()
    finally:
        pass

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
