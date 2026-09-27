# -*- coding: utf-8 -*-
"""fe_agent/profil.py - VERI SETI PROFILI, WEBAPP TARAFI.

TEK MOTOR (kullanici karari): Flow'da recipe / Spark yok. Veri seti
secildiginde tablo Dataiku'dan parca parca yerel bir Parquet dosyasina
akitilir (veri_kaynak) ve profil DuckDB ile cikarilir (profil_duck). Sonuc
calismanin kendi klasorune yazilir:

    PROJE_HAFIZASI/<calisma>/profil.json

Birinci fazin tam veriye bakan her karari (tek deger, hedef / kimlik /
donem adaylari, tip donusumu uygunlugu, kisisel veri, null orani,
tekrarlanan satir) bu dosyadan okunur.
"""

import datetime
import json
import uuid

from fe_agent import profil_duck
from fe_agent import veri_kaynak
from fe_agent.akis_durum import AdimHatasi, _folder, metin_yaz

PROFIL_ADI = "profil.json"

# Calismanin profili ayni istek icinde defalarca okunuyor; dosya degismedikce
# bellekten verilir. Anahtar: dosya yolu; deger: (kosu_id, profil).
_ONBELLEK = {}


def profil_yolu(klasor):
    """Calismanin profil dosyasi: /<calisma>/profil.json."""
    return "/%s/%s" % (klasor, PROFIL_ADI)


def _json_oku(klasor, yol):
    try:
        with klasor.get_download_stream(yol) as s:
            return json.loads(s.read().decode("utf-8"))
    except Exception:           # pylint: disable=broad-except
        return None


# ===========================================================================
# DIS ARAYUZ
# ===========================================================================
def profil_cikar(veri_seti, klasor, sahip=None):
    """Veri setinin profilini cikarir ve calismanin klasorune yazar.

    klasor: calismanin PROJE_HAFIZASI klasoru ("v3"). Doner: profil
    sozlugu. Hata -> AdimHatasi."""
    if not veri_seti:
        raise AdimHatasi("Profili çıkarılacak veri seti seçilmedi.")
    baslangic = datetime.datetime.now().isoformat()
    try:
        yol = veri_kaynak.parquet_yolu(veri_seti)
    except Exception as e:      # pylint: disable=broad-except
        raise AdimHatasi("Veri seti okunamadı (%s): %s: %s"
                         % (veri_seti, type(e).__name__, str(e)[:300]))
    con = profil_duck.baglan()
    try:
        profil = profil_duck.profil(con, yol, veri_seti)
    finally:
        con.close()
    profil["kosu_id"] = uuid.uuid4().hex
    profil["_baslangic"] = baslangic
    profil["_bitis"] = datetime.datetime.now().isoformat()
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
    profil = _json_oku(_folder(), yol)
    if isinstance(profil, dict):
        _ONBELLEK[yol] = (profil.get("kosu_id"), profil)
        return profil
    return None


def kolonlar(profil):
    """{kolon_adi: kolon_profili}."""
    return {k["ad"]: k for k in ((profil or {}).get("kolonlar") or [])}
