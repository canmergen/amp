# -*- coding: utf-8 -*-
"""fe_agent/profil.py - VERI SETI PROFILI, WEBAPP TARAFI.

Webapp tam tabloyu OKUMAZ (kullanici karari: buyuk veride pandas yok,
PySpark var). Veri seti secildiginde bu modul Dataiku'daki PySpark
recipe'ini (profil_spark.recete_calistir) o veri seti icin calistirir,
sonuc dosyasini okur ve calismanin kendi klasorune kopyalar:

    PROJE_HAFIZASI/<calisma>/profil.json

Birinci fazin tam veriye bakan her karari (tek deger, hedef / kimlik /
donem adaylari, tip donusumu uygunlugu, kisisel veri, null orani,
tekrarlanan satir) bu dosyadan okunur.

AYARLAR (proje degiskenleri; tanimli degilse varsayilanlar)
  amp_profil_recete : PySpark recipe'inin adi         (compute_AMP_PROFIL)
  amp_profil_klasor : recipe'in cikti klasorunun adi  (AMP_PROFIL)
  amp_profil_motoru : "spark" (varsayilan) ya da "yerel". "yerel" profili
                      webapp icinde pandas ile cikarir; YALNIZCA kucuk
                      veri ve deneme icindir.
  amp_profil_sure   : isin en fazla bekleneceği saniye (7200)

NASIL CALISIR (spark)
  1. Kilit: ayni anda tek profil isi (recipe'in girdisi degistirildigi
     icin iki calisma ayni anda baslatamaz).
  2. Recipe'in girdisi secilen veri setine cevrilir (girdi zaten oysa
     dokunulmaz).
  3. Kosu kimligi proje degiskenine yazilir; recipe sonuca damgalar.
     Boylece onceki bir kosunun dosyasi yeni sonuc sanilmaz.
  4. Cikti klasoru ZORLA yeniden kurulur (Dataiku isi) ve bitmesi beklenir.
  5. Sonuc okunur, dogrulanir, calisma klasorune yazilir.
"""

import datetime
import json
import threading
import time
import uuid

import dataiku

from fe_agent import profil_kural
from fe_agent.akis_durum import AdimHatasi, _df_oku, _folder, metin_yaz

VARSAYILAN = {
    "amp_profil_recete": "compute_AMP_PROFIL",
    "amp_profil_klasor": "AMP_PROFIL",
    "amp_profil_motoru": "spark",
    "amp_profil_sure": "7200",
}
KILIT_DOSYA = "/_isler/profil_kilit.json"
PROFIL_ADI = "profil.json"

# Calismanin profili ayni istek icinde defalarca okunuyor; dosya degismedikce
# bellekten verilir. Anahtar: dosya yolu; deger: (kosu_id, profil).
_ONBELLEK = {}


def _ayar(anahtar):
    try:
        deger = (dataiku.get_custom_variables() or {}).get(anahtar)
    except Exception:           # pylint: disable=broad-except
        deger = None
    if deger is None or not str(deger).strip():
        return VARSAYILAN[anahtar]
    return str(deger).strip()


def profil_yolu(klasor):
    """Calismanin profil dosyasi: /<calisma>/profil.json."""
    return "/%s/%s" % (klasor, PROFIL_ADI)


# ===========================================================================
# KILIT
# ===========================================================================
def _json_oku(klasor, yol):
    try:
        with klasor.get_download_stream(yol) as s:
            return json.loads(s.read().decode("utf-8"))
    except Exception:           # pylint: disable=broad-except
        return None


def _kilit_al(sahip, sure):
    kayit = _json_oku(_folder(), KILIT_DOSYA)
    if isinstance(kayit, dict) and kayit.get("sahip") != sahip:
        try:
            yas = time.time() - float(kayit.get("zaman") or 0)
        except (TypeError, ValueError):
            yas = sure + 1
        if yas < sure:
            raise AdimHatasi(
                "Başka bir çalışma (%s) şu an veri seti profili çıkarıyor "
                "(%s veri seti, %d dakikadır). Profil işi aynı anda tek "
                "çalışabiliyor; biraz sonra tekrar deneyin."
                % (kayit.get("sahip") or "?", kayit.get("veri_seti") or "?",
                   int(yas // 60)))
    return {"sahip": sahip, "zaman": time.time()}


def _kilit_yaz(kayit):
    metin_yaz(KILIT_DOSYA, json.dumps(kayit, ensure_ascii=False))


def _kilit_birak(sahip):
    kayit = _json_oku(_folder(), KILIT_DOSYA)
    if isinstance(kayit, dict) and kayit.get("sahip") == sahip:
        try:
            _folder().delete_path(KILIT_DOSYA)
        except Exception:       # pylint: disable=broad-except
            metin_yaz(KILIT_DOSYA, "{}")


# ===========================================================================
# DATAIKU ISI
# ===========================================================================
def _klasor_kimligi(proje, ad):
    for f in proje.list_managed_folders():
        if f.get("name") == ad or f.get("id") == ad:
            return f.get("id")
    raise AdimHatasi(
        "Profil çıktı klasörü (%s) projede bulunamadı. Kurulum adımları "
        "OKU_ONCE.md'de." % ad)


def _girdiyi_ayarla(proje, recete_adi, veri_seti):
    try:
        ayar = proje.get_recipe(recete_adi).get_settings()
    except Exception as e:      # pylint: disable=broad-except
        raise AdimHatasi(
            "Profil recipe'i (%s) açılamadı: %s. Kurulum adımları OKU_ONCE.md'de."
            % (recete_adi, str(e)[:160]))
    girdiler = list(ayar.get_flat_input_refs())
    if girdiler == [veri_seti]:
        return
    # Baska projedeki veri seti ("PROJE.VERI") recipe'e ancak o proje veri
    # setini bu projeye PAYLASTIYSA (Exposed objects) girdi olabilir;
    # degilse Dataiku kaydi reddeder ve mesaj asagida kullaniciya gider.
    if len(girdiler) != 1:
        raise AdimHatasi(
            "Profil recipe'inin (%s) tek girdisi olmalı; şu an %d girdi var."
            % (recete_adi, len(girdiler)))
    try:
        ayar.replace_input(girdiler[0], veri_seti)
        ayar.save()
    except Exception as e:      # pylint: disable=broad-except
        raise AdimHatasi(
            "Profil recipe'inin girdisi %s olarak ayarlanamadı: %s. Veri seti "
            "başka bir projedeyse o projenin veri setini bu projeye "
            "paylaşması (Exposed objects) gerekir." % (veri_seti, str(e)[:160]))


def _istek_yaz(proje, kosu_id, veri_seti):
    degisken = proje.get_variables()
    degisken.setdefault("standard", {})[
        "amp_profil_istek"] = json.dumps({"kosu_id": kosu_id,
                                          "veri_seti": veri_seti})
    proje.set_variables(degisken)


def _isi_calistir(proje, klasor_id, sure):
    """Cikti klasorunu zorla yeniden kurar; bitmesini en fazla `sure`
    saniye bekler. Doner: (durum, gunluk_sonu)."""
    kutu = {}

    def calis():
        try:
            is_ = proje.new_job("NON_RECURSIVE_FORCED_BUILD")
            is_.with_output(klasor_id, object_type="MANAGED_FOLDER")
            kutu["is"] = is_.start_and_wait(no_fail=True)
        except Exception as e:  # pylint: disable=broad-except
            kutu["hata"] = e

    t = threading.Thread(target=calis, name="amp-profil")
    t.daemon = True
    t.start()
    t.join(sure)
    if t.is_alive():
        raise AdimHatasi(
            "Profil işi %d dakikada bitmedi; Dataiku'da çalışmaya devam "
            "ediyor olabilir (Jobs ekranından izleyebilirsiniz). Bittikten "
            "sonra adımı yeniden onaylayın." % (sure // 60))
    if "hata" in kutu:
        raise AdimHatasi("Profil işi başlatılamadı: %s" % str(kutu["hata"])[:300])
    is_ = kutu.get("is")
    try:
        durum = ((is_.get_status() or {}).get("baseStatus") or {}).get("state")
    except Exception:           # pylint: disable=broad-except
        durum = None
    gunluk = ""
    if durum != "DONE":
        try:
            gunluk = "\n".join(str(is_.get_log() or "").splitlines()[-15:])
        except Exception:       # pylint: disable=broad-except
            gunluk = ""
    return durum, gunluk


def _spark_profil(veri_seti, sahip):
    sure = int(float(_ayar("amp_profil_sure")))
    recete = _ayar("amp_profil_recete")
    klasor_ad = _ayar("amp_profil_klasor")
    kilit = _kilit_al(sahip, sure)
    kilit["veri_seti"] = veri_seti
    _kilit_yaz(kilit)
    try:
        proje = dataiku.api_client().get_default_project()
        klasor_id = _klasor_kimligi(proje, klasor_ad)
        _girdiyi_ayarla(proje, recete, veri_seti)
        kosu_id = uuid.uuid4().hex
        _istek_yaz(proje, kosu_id, veri_seti)
        durum, gunluk = _isi_calistir(proje, klasor_id, sure)
        if durum != "DONE":
            raise AdimHatasi(
                "Profil işi başarısız bitti (%s).%s"
                % (durum or "durum okunamadı",
                   ("\n\nİş günlüğünün sonu:\n" + gunluk) if gunluk else ""))
        from fe_agent import profil_spark
        profil = _json_oku(dataiku.Folder(klasor_ad),
                           profil_spark.profil_yolu(veri_seti))
        if not isinstance(profil, dict):
            raise AdimHatasi("Profil işi bitti ama sonuç dosyası okunamadı "
                             "(%s%s)." % (klasor_ad,
                                          profil_spark.profil_yolu(veri_seti)))
        if profil.get("kosu_id") != kosu_id:
            raise AdimHatasi(
                "Profil sonucu bu çalıştırmaya ait değil (beklenen koşu %s, "
                "bulunan %s); kabul edilmedi. Adımı yeniden onaylayın."
                % (kosu_id, profil.get("kosu_id") or "yok"))
        return profil
    finally:
        _kilit_birak(sahip)


# ===========================================================================
# DIS ARAYUZ
# ===========================================================================
def profil_cikar(veri_seti, klasor, sahip):
    """Veri setinin profilini cikarir ve calismanin klasorune yazar.

    klasor: calismanin PROJE_HAFIZASI klasoru ("v3"). sahip: kilitte
    gorunecek calisma adi. Doner: profil sozlugu. Hata -> AdimHatasi."""
    if not veri_seti:
        raise AdimHatasi("Profili çıkarılacak veri seti seçilmedi.")
    motor = _ayar("amp_profil_motoru").lower()
    if motor == "yerel":
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
    profil = _json_oku(_folder(), yol)
    if isinstance(profil, dict):
        _ONBELLEK[yol] = (profil.get("kosu_id"), profil)
        return profil
    return None


def kolonlar(profil):
    """{kolon_adi: kolon_profili}."""
    return {k["ad"]: k for k in ((profil or {}).get("kolonlar") or [])}
