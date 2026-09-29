# -*- coding: utf-8 -*-
"""fe_agent/profil.py - VERI SETI PROFILI, WEBAPP TARAFI.

MOTOR VERININ BOYUTUNA GORE (bkz. motor.py). Kucuk veri seti webapp
icinde pandas ile okunup profillenir (profil_kural.yerel_profil; Spark
isiyle ayni kurallar, ayni cikti). Buyuk veri setinde webapp tabloyu
OKUMAZ: compute_AMP_PROFIL recipe'ini o veri seti icin calistirir (bkz.
spark_is; recipe ve klasor yoksa webapp kurar) ve sonuc dosyasini okur.
Iki durumda da profil calismanin kendi klasorune yazilir:

    PROJE_HAFIZASI/<calisma>/profil.json

Birinci fazin tam veriye bakan her karari (tek deger, hedef / kimlik /
donem adaylari, tip donusumu uygunlugu, kisisel veri, null orani,
tekrarlanan satir) bu dosyadan okunur.
"""

import json
import uuid

from fe_agent import motor
from fe_agent import spark_is
from fe_agent.akis_durum import AdimHatasi, _df_oku, _folder, metin_yaz

PROFIL_ADI = "profil.json"

# Calismanin profili ayni istek icinde defalarca okunuyor; dosya degismedikce
# bellekten verilir. Anahtar: dosya yolu; deger: (kosu_id, profil).
_ONBELLEK = {}


def profil_yolu(klasor):
    """Calismanin profil dosyasi: /<calisma>/profil.json."""
    return "/%s/%s" % (klasor, PROFIL_ADI)


def _spark_profil(veri_seti, sahip):
    from fe_agent import profil_spark
    kosu_id = spark_is.calistir("profil", [veri_seti], {}, sahip)
    return spark_is.sonuc_oku("profil", profil_spark.profil_yolu(veri_seti), kosu_id)


def _pandas_profil(veri_seti):
    from fe_agent import profil_kural
    try:
        df = _df_oku(veri_seti)
    except Exception as e:      # pylint: disable=broad-except
        raise AdimHatasi("'%s' veri seti okunamadı: %s" % (veri_seti, str(e)[:200]))
    profil = profil_kural.yerel_profil(df, veri_seti)
    profil["kosu_id"] = uuid.uuid4().hex
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
    secilen, toplam = motor.sec([veri_seti])
    if secilen == motor.PANDAS:
        profil = _pandas_profil(veri_seti)
    else:
        profil = _spark_profil(veri_seti, sahip)
    profil["motor"] = secilen
    profil["dosya_boyutu"] = toplam
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
