# -*- coding: utf-8 -*-
"""fe_agent/spark_oturum.py - webapp icinde SUREKLI ACIK Spark oturumu.

NEDEN (kullanici karari: "spark webapp çalıştığı zaman aktif olsun direkt
zamandan kazanalım"): her adimda bir Dataiku isi (recipe) baslatmak
Kubernetes'te yurutuculerin acilmasini (30-60 sn) ve isin kurulmasini
bekletiyordu. 10.000 satirlik denemede profil 3 dakika surdu. Webapp
acilirken oturum BIR KEZ acilir, sonraki her adim dogrudan hesaba gecer.

HESAP DEGISMEZ. Profil (profil_spark.spark_profil) ve AMP_VERISETI
(amp_spark.amp_hazirla) ayni fonksiyonlarla hesaplanir; degisen yalnizca
Spark'in NEREDE acildigi. Oturum acilamazsa ya da veri seti bu oturumdan
okunamazsa is eskisi gibi recipe ile yapilir (spark_is).

KURULUM - bir kez: webapp duz bir Python sureci; Dataiku Kubernetes
baglanti ayarlarini yalnizca PySpark notebook'larina ve recipe'lere
veriyor. Ayarlar calisan bir PySpark notebook'undan alinir:

    from fe_agent import spark_oturum
    spark_oturum.ayarlari_kaydet()

Bu satir notebook'un Spark ayarlarini ve ortam degiskenlerini proje
degiskenine (local > amp_spark_oturum) yazar. Adinda token / secret /
password / credential / access.key gecen ayarlar (deger bir dosya yolu
degilse) YAZILMAZ; adlari ekrana basilir. Sonra webapp'in backend'i yeniden baslatilir.

AYARLAR (proje degiskenleri)
  amp_spark_oturum : ayarlari_kaydet()'in yazdigi JSON (local bolumunde)
  amp_spark_webapp : "hayir" -> oturum hic acilmaz, her is recipe ile
"""

import datetime
import glob
import json
import os
import sys
import threading
import traceback

DEGISKEN = "amp_spark_oturum"
KAPALI_DEGISKEN = "amp_spark_webapp"
UYGULAMA_ADI = "AMP webapp"
# Oturum hala aciliyorsa bir is en fazla bu kadar bekler; sonra recipe'e
# gecer. Recipe de ayni acilisi bekleyecegi icin beklemek kayip degil.
BEKLE_SN = 240

# Oturumun kopyalanmayacak ayarlari: o notebook'a / o surece ozgu.
_ATLANAN = (
    "spark.app.id", "spark.app.name", "spark.app.startTime",
    "spark.app.submitTime", "spark.app.initial.jar.urls",
    "spark.app.initial.file.urls", "spark.driver.port",
    "spark.driver.appUIAddress", "spark.executor.id", "spark.ui.proxyBase",
    "spark.submit.pyFiles", "spark.kubernetes.driver.pod.name",
    "spark.kubernetes.executor.podNamePrefix", "spark.repl.local.jars",
)
# Webapp ayni makinede (Dataiku sunucusu) calistigi icin spark.driver.host
# KORUNUR: yurutuculer surucuye bu adresle baglaniyor.
_GIZLI = ("token", "secret", "password", "passwd", "credential", "access.key")
# Kopyalanan ortam degiskenleri (Spark'in JVM'i ve Kubernetes baglantisi).
_ORTAM = ("SPARK_HOME", "SPARK_CONF_DIR", "JAVA_HOME", "HADOOP_HOME",
          "HADOOP_CONF_DIR", "KUBECONFIG", "SPARK_DIST_CLASSPATH")

_KILIT = threading.Lock()
_HAZIR = threading.Event()
_DURUM = {"durum": "kapali", "hata": None, "oturum": None,
          "baslangic": None, "bitis": None, "okuma_hatasi": None}


def _gizli_mi(ad, deger):
    """Gizli deger tasiyan ayar. Deger bir DOSYA YOLUYSA gizli degildir
    (ornegin Kubernetes token dosyasinin yolu); gizli olan dosyanin
    icerigidir ve o kopyalanmiyor."""
    if str(deger or "").startswith("/"):
        return False
    ad = ad.lower()
    return any(g in ad for g in _GIZLI)


# ===========================================================================
# KURULUM (PySpark notebook'unda bir kez)
# ===========================================================================
def ayarlari_kaydet():
    """PySpark NOTEBOOK'UNDA calistirilir. Oturum ayarlarini proje
    degiskenine yazar. Doner: yazilan sozluk."""
    import dataiku
    from pyspark import SparkContext

    sc = SparkContext.getOrCreate()
    ayarlar, atlanan_gizli = {}, []
    for ad, deger in sc.getConf().getAll():
        if ad in _ATLANAN or ad.startswith("spark.ui."):
            continue
        if _gizli_mi(ad, deger):
            atlanan_gizli.append(ad)
            continue
        ayarlar[ad] = deger
    ortam = {ad: os.environ[ad] for ad in _ORTAM if os.environ.get(ad)}
    # pyspark'in kendisi: notebook onu SPARK_HOME/python'dan aliyor; webapp'in
    # code env'inde pyspark yok ("No module named 'pyspark'").
    # Oturuma ozgu gecici klasorler ("/tmp/spark-.../userFiles-...") alinmaz.
    yollar = [y for y in sys.path
              if y and ("spark" in y.lower() or "py4j" in y.lower())
              and "userFiles-" not in y]
    kayit = {"ayarlar": ayarlar, "ortam": ortam, "yollar": yollar,
             "spark_surumu": sc.version,
             "kaydedildi": datetime.datetime.now().isoformat()}

    proje = dataiku.api_client().get_default_project()
    degisken = proje.get_variables()
    degisken.setdefault("local", {})[DEGISKEN] = json.dumps(kayit, ensure_ascii=False)
    proje.set_variables(degisken)

    print("Kaydedildi: %d Spark ayarı, %d ortam değişkeni, %d yol (Spark %s)."
          % (len(ayarlar), len(ortam), len(yollar), sc.version))
    if atlanan_gizli:
        print("Gizli olabileceği için YAZILMAYAN ayarlar: " + ", ".join(sorted(atlanan_gizli)))
    print("Şimdi webapp'in backend'ini yeniden başlatın.")
    return kayit


# ===========================================================================
# WEBAPP TARAFI
# ===========================================================================
def _kayit_oku():
    import dataiku
    ham = (dataiku.get_custom_variables() or {}).get(DEGISKEN)
    if isinstance(ham, dict):
        return ham
    return json.loads(ham) if ham else None


def _kapali_mi():
    import dataiku
    try:
        deger = (dataiku.get_custom_variables() or {}).get(KAPALI_DEGISKEN)
    except Exception:           # pylint: disable=broad-except
        return False
    return str(deger or "").strip().lower() in ("hayir", "hayır", "no", "false", "0")


def _spark_yolunu_kur(kayit):
    for ad, deger in (kayit.get("ortam") or {}).items():
        os.environ.setdefault(ad, deger)
    yollar = list(kayit.get("yollar") or [])
    ev = os.environ.get("SPARK_HOME")
    if ev:
        yollar.append(os.path.join(ev, "python"))
        yollar.extend(glob.glob(os.path.join(ev, "python", "lib", "py4j-*.zip")))
    for y in reversed(yollar):
        if y and os.path.exists(y) and y not in sys.path:
            sys.path.insert(0, y)


def _baslat():
    try:
        kayit = _kayit_oku()
        if not kayit:
            _DURUM.update(durum="ayar_yok", hata=(
                "Spark oturum ayarları kaydedilmemiş. Bir PySpark notebook'unda "
                "`from fe_agent import spark_oturum; spark_oturum.ayarlari_kaydet()` "
                "çalıştırıp backend'i yeniden başlatın."))
            return
        _spark_yolunu_kur(kayit)
        from pyspark.sql import SparkSession
        kurucu = SparkSession.builder.appName(UYGULAMA_ADI)
        for ad, deger in (kayit.get("ayarlar") or {}).items():
            kurucu = kurucu.config(ad, deger)
        spark = kurucu.getOrCreate()
        spark.conf.set("spark.sql.legacy.timeParserPolicy", "CORRECTED")
        # Yurutuculer ilk iste acilir; ilk kullanici beklemesin diye simdi.
        spark.range(1).count()
        _DURUM.update(durum="hazir", oturum=spark, hata=None,
                      bitis=datetime.datetime.now().isoformat())
    except Exception as e:      # pylint: disable=broad-except
        _DURUM.update(durum="hata", oturum=None,
                      hata="%s: %s" % (type(e).__name__, str(e)[:500]),
                      bitis=datetime.datetime.now().isoformat())
        traceback.print_exc()
    finally:
        _HAZIR.set()


def baslat_arkada():
    """Webapp backend'i yuklenirken cagrilir; beklemez."""
    with _KILIT:
        if _DURUM["durum"] in ("basliyor", "hazir"):
            return
        if _kapali_mi():
            _DURUM.update(durum="kapali", hata="amp_spark_webapp = hayır")
            _HAZIR.set()
            return
        _HAZIR.clear()
        _DURUM.update(durum="basliyor", hata=None, okuma_hatasi=None,
                      baslangic=datetime.datetime.now().isoformat(), bitis=None)
        t = threading.Thread(target=_baslat, name="amp-spark-oturum")
        t.daemon = True
        t.start()


def oturum(bekle_sn=BEKLE_SN):
    """Acik oturum ya da None (acilamadi / kapali / okuma yolu calismiyor).
    Oturum aciliyorsa en fazla bekle_sn bekler."""
    if _DURUM["durum"] == "basliyor":
        _HAZIR.wait(bekle_sn)
    if _DURUM["durum"] != "hazir" or _DURUM["okuma_hatasi"]:
        return None
    spark = _DURUM["oturum"]
    try:
        # Kapanmis oturum (JVM dustu) bir daha kullanilmaz.
        if spark.sparkContext._jsc is None:      # pylint: disable=protected-access
            raise RuntimeError("SparkContext kapanmış")
    except Exception as e:      # pylint: disable=broad-except
        _DURUM.update(durum="hata", oturum=None, hata=str(e)[:300])
        return None
    return spark


def veri_oku(spark, veri_seti):
    """Veri setini bu oturumda Spark tablosu olarak acar. Okuma yolu
    calismiyorsa (Dataiku baglantisi recipe disinda kurulamiyor) bunu
    kaydeder ve bundan sonra her is recipe ile yapilir."""
    import dataiku
    from dataiku import spark as dkuspark
    from pyspark.sql import SQLContext
    try:
        return dkuspark.get_dataframe(SQLContext(spark.sparkContext),
                                      dataiku.Dataset(veri_seti))
    except Exception as e:
        _DURUM["okuma_hatasi"] = "%s: %s" % (type(e).__name__, str(e)[:500])
        raise


def durum():
    """Ekran / tani icin: oturumun durumu (oturum nesnesi haric)."""
    return {k: v for k, v in _DURUM.items() if k != "oturum"}
