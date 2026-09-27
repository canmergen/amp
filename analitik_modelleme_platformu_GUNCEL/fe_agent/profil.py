# -*- coding: utf-8 -*-
"""fe_agent/profil.py - VERI SETI PROFILI, WEBAPP TARAFI.

Webapp tam tabloyu pandas ile OKUMAZ (kullanici karari: buyuk veride
pandas yok, PySpark var). Profil iki yerden biriyle cikarilir; hesap
ikisinde de AYNI fonksiyon (profil_spark.spark_profil):

  1. Webapp'te surekli acik Spark oturumu (spark_oturum). Yurutucu acilisi
     ve Dataiku isi beklenmez; varsayilan yol budur.
  2. Oturum yoksa ya da veri seti oradan okunamazsa Dataiku'daki PySpark
     recipe'i (profil_spark.recete_calistir; bkz. spark_is).

Sonuc calismanin kendi klasorune yazilir:

    PROJE_HAFIZASI/<calisma>/profil.json

Birinci fazin tam veriye bakan her karari (tek deger, hedef / kimlik /
donem adaylari, tip donusumu uygunlugu, kisisel veri, null orani,
tekrarlanan satir) bu dosyadan okunur.

AYARLAR (proje degiskenleri; tanimli degilse varsayilanlar)
  amp_profil_recete : PySpark recipe'inin adi         (compute_AMP_PROFIL)
  amp_profil_klasor : recipe'in cikti klasorunun adi  (AMP_PROFIL)
  amp_motor         : bkz. spark_is ("yerel" = pandas, yalnizca kucuk veri)
"""

import datetime
import json
import logging
import uuid

import dataiku

from fe_agent import profil_kural
from fe_agent import spark_is
from fe_agent import spark_oturum
from fe_agent.akis_durum import AdimHatasi, _df_oku, _folder, metin_yaz

VARSAYILAN_RECETE = "compute_AMP_PROFIL"
VARSAYILAN_KLASOR = "AMP_PROFIL"
ISTEK_DEGISKENI = "amp_profil_istek"
PROFIL_ADI = "profil.json"

# Calismanin profili ayni istek icinde defalarca okunuyor; dosya degismedikce
# bellekten verilir. Anahtar: dosya yolu; deger: (kosu_id, profil).
_ONBELLEK = {}


def profil_yolu(klasor):
    """Calismanin profil dosyasi: /<calisma>/profil.json."""
    return "/%s/%s" % (klasor, PROFIL_ADI)


_LOG = logging.getLogger(__name__)


def _oturumda_profil(veri_seti):
    """Webapp'teki acik oturumda profil; oturum yoksa None."""
    spark = spark_oturum.oturum()
    if spark is None:
        return None
    from fe_agent import profil_spark
    baslangic = datetime.datetime.now().isoformat()
    try:
        df = spark_oturum.veri_oku(spark, veri_seti)
    except Exception:           # pylint: disable=broad-except
        _LOG.exception("Profil: veri seti webapp oturumundan okunamadı; recipe ile devam")
        return None
    try:
        profil = profil_spark.spark_profil(spark, df, veri_seti)
    except Exception:           # pylint: disable=broad-except
        # Oturum ya da kume sorunu olabilir; ayni hesap recipe'te denenir.
        _LOG.exception("Profil: webapp oturumunda hesaplanamadı; recipe ile devam")
        return None
    profil["kosu_id"] = uuid.uuid4().hex
    profil["_baslangic"] = baslangic
    profil["_bitis"] = datetime.datetime.now().isoformat()
    profil["_calistigi_yer"] = "webapp"
    return profil


def _spark_profil(veri_seti, sahip):
    from fe_agent import profil_spark
    profil = _oturumda_profil(veri_seti)
    if profil is not None:
        return profil
    klasor_ad = spark_is.ayar("amp_profil_klasor", VARSAYILAN_KLASOR)
    kosu_id = spark_is.calistir(
        "profil", "Profil işi",
        spark_is.ayar("amp_profil_recete", VARSAYILAN_RECETE),
        klasor_ad, "MANAGED_FOLDER", veri_seti, ISTEK_DEGISKENI, {}, sahip)
    yol = profil_spark.profil_yolu(veri_seti)
    profil = spark_is.json_oku(dataiku.Folder(klasor_ad), yol)
    if not isinstance(profil, dict):
        raise AdimHatasi("Profil işi bitti ama sonuç dosyası okunamadı (%s%s)."
                         % (klasor_ad, yol))
    if profil.get("kosu_id") != kosu_id:
        raise AdimHatasi(
            "Profil sonucu bu çalıştırmaya ait değil (beklenen koşu %s, "
            "bulunan %s); kabul edilmedi. Adımı yeniden onaylayın."
            % (kosu_id, profil.get("kosu_id") or "yok"))
    return profil


# ===========================================================================
# DIS ARAYUZ
# ===========================================================================
def profil_cikar(veri_seti, klasor, sahip):
    """Veri setinin profilini cikarir ve calismanin klasorune yazar.

    klasor: calismanin PROJE_HAFIZASI klasoru ("v3"). sahip: kilitte
    gorunecek calisma adi. Doner: profil sozlugu. Hata -> AdimHatasi."""
    if not veri_seti:
        raise AdimHatasi("Profili çıkarılacak veri seti seçilmedi.")
    if spark_is.motor() == "yerel":
        profil = profil_kural.yerel_profil(_df_oku(veri_seti), veri_seti)
        profil["kosu_id"] = uuid.uuid4().hex
        profil["_bitis"] = datetime.datetime.now().isoformat()
    else:
        profil = _spark_profil(veri_seti, sahip)
    yol = profil_yolu(klasor)
    if not metin_yaz(yol, json.dumps(profil, ensure_ascii=False, default=str)):
        raise AdimHatasi("Profil çalışma klasörüne yazılamadı (PROJE_HAFIZASI%s)."
                         % yol)
    _ONBELLEK[yol] = (profil.get("kosu_id"), profil)
    return profil


def profil_oku(klasor, kosu_id=None):
    """Calismanin profil dosyasi; yoksa None. kosu_id verilirse ve bellek
    ayni kosuyu tutuyorsa dosya yeniden okunmaz."""
    yol = profil_yolu(klasor)
    kayit = _ONBELLEK.get(yol)
    if kayit and (kosu_id is None or kayit[0] == kosu_id):
        return kayit[1]
    profil = spark_is.json_oku(_folder(), yol)
    if isinstance(profil, dict):
        _ONBELLEK[yol] = (profil.get("kosu_id"), profil)
        return profil
    return None


def kolonlar(profil):
    """{kolon_adi: kolon_profili}."""
    return {k["ad"]: k for k in ((profil or {}).get("kolonlar") or [])}
