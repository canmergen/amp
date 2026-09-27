# -*- coding: utf-8 -*-
"""fe_agent/amp.py - AMP_VERISETI'ni Spark ile yazdirma (webapp tarafi).

Kullanici karari: veri buyuk, webapp tabloyu okumaz; AMP_VERISETI Flow'da
PARQUET bicimli bir dataset ve onu PySpark recipe'i (amp_spark) yazar.
CSV yedegi YOK: dataset yazilamazsa adim nedenini soyleyip durur.

Iki yerde calisir:
  - Degisken Kontrolu onayinda : tip donusumleri + surec disi kolonlar
  - Orneklem ve Dogrulama'da   : ayni tablo + _SPLIT (bolme) kolonu

AYARLAR (proje degiskenleri)
  amp_veri_recete  : recipe adi              (compute_AMP_VERISETI)
  amp_sonuc_klasor : recipe'in ikinci ciktisi (AMP_SONUC)
"""

import datetime
import logging
import uuid

import dataiku

from fe_agent import profil as profil_mod
from fe_agent import profil_kural
from fe_agent import spark_is
from fe_agent import spark_oturum
from fe_agent import tip_donusum
from fe_agent.akis_durum import AMP_VERI_ADI, AdimHatasi

VARSAYILAN_RECETE = "compute_AMP_VERISETI"
VARSAYILAN_SONUC = "AMP_SONUC"
ISTEK_DEGISKENI = "amp_veri_istek"
SONUC_DOSYA = "/sonuc.json"
DISARIDA = "disarida"      # hicbir sete girmeyen satir (amp_spark ile ayni)
ETIKET = "AMP_VERISETI yazma işi"

_LOG = logging.getLogger(__name__)


def dusen_kolonlar(durum, adlar):
    """Surec disi kolonlar; hedef / kimlik / donem hicbir zaman dusmez."""
    korunan = {str(v) for v in (durum.get("meta") or {}).values() if v}
    haric = set(map(str, durum.get("haric_kolonlar") or []))
    return [c for c in adlar if str(c) in haric and str(c) not in korunan]


def _donusum_istegi(durum, kolonlar):
    cikti = {}
    for kolon, kod in (durum.get("tip_donusum") or {}).items():
        kp = kolonlar.get(kolon)
        if kp is None or not tip_donusum.gecerli_kod(kod):
            continue
        tam = None
        if kp.get("tur") == profil_kural.TUR_ONDALIK:
            tam = bool(kp.get("dolu")) and not kp.get("ondalikli")
        cikti[kolon] = {"kod": kod, "tam_sayi": tam, "tekil": int(kp.get("tekil") or 0)}
    return cikti


def _oturumda_yaz(durum, istek):
    """Webapp'teki acik oturumda yazar. Doner: sonuc sozlugu ya da None
    (oturum yok / okunamadi / yazilamadi -> recipe ile yapilir).
    Hesabin kendi hatasi (cevrilemeyen hucre) None DEGIL, sonuc["hata"]."""
    spark = spark_oturum.oturum()
    if spark is None:
        return None
    from dataiku import spark as dkuspark
    from fe_agent import amp_spark
    veri_seti = durum.get("veri_seti")
    with spark_is.kilitli("amp", ETIKET, durum.get("_oturum_id") or "", veri_seti):
        sonuc = {"_baslangic": datetime.datetime.now().isoformat(),
                 "_calistigi_yer": "webapp"}
        try:
            df = spark_oturum.veri_oku(spark, veri_seti)
        except Exception:       # pylint: disable=broad-except
            _LOG.exception("AMP: veri seti webapp oturumundan okunamadı; recipe ile devam")
            return None
        try:
            yeni, oz = amp_spark.amp_hazirla(spark, df, istek)
            sonuc.update(oz)
            if yeni is not None:
                dkuspark.write_with_schema(dataiku.Dataset(AMP_VERI_ADI), yeni)
        except Exception:       # pylint: disable=broad-except
            # Yarim kalan yazim sorun degil: recipe tabloyu bastan yazar.
            _LOG.exception("AMP: webapp oturumunda yazılamadı; recipe ile devam")
            return None
    sonuc["_bitis"] = datetime.datetime.now().isoformat()
    return sonuc


def amp_yaz(durum, prof, bolme=None):
    """AMP_VERISETI'ni Spark ile yazar: once webapp'teki acik oturumda,
    olmazsa recipe ile. Doner: {satir, kolon, dusen, setler?}.
    Hata -> AdimHatasi."""
    kolonlar = profil_mod.kolonlar(prof)
    istek = {
        "donusum": _donusum_istegi(durum, kolonlar),
        "dusen": dusen_kolonlar(durum, list(kolonlar)),
        "hedef": (durum.get("meta") or {}).get("target"),
        "bolme": bolme,
    }
    sonuc = _oturumda_yaz(durum, istek)
    if sonuc is not None:
        if sonuc.get("hata"):
            raise AdimHatasi(sonuc["hata"])
        return sonuc

    klasor = spark_is.ayar("amp_sonuc_klasor", VARSAYILAN_SONUC)
    kosu_id = None
    try:
        kosu_id = uuid.uuid4().hex
        spark_is.calistir(
            "amp", ETIKET,
            spark_is.ayar("amp_veri_recete", VARSAYILAN_RECETE),
            AMP_VERI_ADI, "DATASET", durum.get("veri_seti"),
            ISTEK_DEGISKENI, istek, durum.get("_oturum_id") or "", kosu_id=kosu_id)
    except AdimHatasi:
        # Recipe kendi hatasini (ornegin cevrilemeyen hucre) sonuc dosyasina
        # yazdiysa o daha anlasilir; yoksa isin hatasi aynen gider.
        sonuc = spark_is.json_oku(dataiku.Folder(klasor), SONUC_DOSYA)
        if isinstance(sonuc, dict) and sonuc.get("kosu_id") == kosu_id \
                and sonuc.get("hata"):
            raise AdimHatasi(sonuc["hata"])
        raise
    sonuc = spark_is.json_oku(dataiku.Folder(klasor), SONUC_DOSYA)
    if not isinstance(sonuc, dict) or sonuc.get("kosu_id") != kosu_id:
        raise AdimHatasi("AMP_VERISETI yazma işi bitti ama sonucu okunamadı ya "
                         "da bu çalıştırmaya ait değil (%s%s)." % (klasor, SONUC_DOSYA))
    if sonuc.get("hata"):
        raise AdimHatasi(sonuc["hata"])
    return sonuc
