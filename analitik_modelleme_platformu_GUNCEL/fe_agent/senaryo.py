# -*- coding: utf-8 -*-
"""fe_agent/senaryo.py — webapp ile Dataiku senaryosu arasindaki el sikisma.

Webapp uzun islemi kendi icinde calistiramaz (Flask timeout). Bunun yerine:
  1) webapp  -> konfigurasyonu PROJE_HAFIZASI'na yazar
  2) webapp  -> senaryoyu tetikler ve bitmesini bekler
  3) senaryo -> ayni folder'dan konfigurasyonu okur, isi yapar
  4) senaryo -> sonucu folder'a yazar
  5) webapp  -> sonucu okur ve kullaniciya gosterir

Iki taraf da bu modulu kullanir; dosya adlari tek yerde tanimli.
"""

import json
import datetime
import re
import threading
import time
import uuid

import dataiku

# Varsayilan adlar — proje degiskeni tanimliysa o kazanir (asagi bak).
HAFIZA_FOLDER = "PROJE_HAFIZASI"

# Senaryo adlari — Dataiku'da olusturdugun senaryolarla AYNI olmali
SENARYO_ALGORITMA = "ALGORITMA_SECIMI"
SENARYO_FINAL = "FINAL_MODEL"

# Proje degiskeni anahtarlari
DEGISKEN_FOLDER = "fe_hafiza_folder"
DEGISKEN_ALGORITMA = "fe_senaryo_algoritma"
DEGISKEN_FINAL = "fe_senaryo_final"

_KONFIG = "/senaryo_%s_konfig.json"
_SONUC = "/senaryo_%s_sonuc.json"
_KONFIG_OTURUM = "/senaryo_%s_%s_konfig.json"
_SONUC_OTURUM = "/senaryo_%s_%s_sonuc.json"

# Senaryo tarafinda konfigi okurken saklanir; sonuc_yaz/hata_yaz ayni
# kosu kimligini sonuca damgalar (webapp bunu dogrular).
_SON_KOSU_ID = {}


class HafizaHatasi(Exception):
    """Proje hafizasi folder'ina hic erisilemedi (dosyanin olmamasi degil)."""


def _proje_degiskenleri():
    try:
        return dataiku.get_custom_variables() or {}
    except Exception:
        return {}


def _degisken(anahtar, varsayilan):
    deger = _proje_degiskenleri().get(anahtar)
    return deger if isinstance(deger, str) and deger.strip() else varsayilan


def hafiza_folder_adi():
    return _degisken(DEGISKEN_FOLDER, HAFIZA_FOLDER)


def senaryo_algoritma_adi():
    return _degisken(DEGISKEN_ALGORITMA, SENARYO_ALGORITMA)


def senaryo_final_adi():
    return _degisken(DEGISKEN_FINAL, SENARYO_FINAL)


def _temiz(deger):
    """Dosya adina girecek kimligi guvenli hale getirir."""
    return re.sub(r"[^A-Za-z0-9_-]", "", str(deger))[:64]


def _yol_uret(sablon, oturum_sablonu, is_adi, oturum_id):
    """Oturum kimligi varsa dosya adina eklenir.

    Boylece iki analist ayni anda calistiginda birbirinin konfigurasyonunu
    ya da sonucunu ezmez.
    """
    is_adi = _temiz(is_adi)
    if oturum_id:
        return oturum_sablonu % (is_adi, _temiz(oturum_id))
    return sablon % is_adi


def konfig_yolu(is_adi, oturum_id=None):
    return _yol_uret(_KONFIG, _KONFIG_OTURUM, is_adi, oturum_id)


def sonuc_yolu(is_adi, oturum_id=None):
    return _yol_uret(_SONUC, _SONUC_OTURUM, is_adi, oturum_id)


def _folder():
    ad = hafiza_folder_adi()
    try:
        return dataiku.Folder(ad)
    except Exception as e:
        raise HafizaHatasi("Proje hafızası klasörü '%s' açılamadı: %s" % (ad, e))


def _oku(yol, varsayilan=None):
    """Dosya yoksa varsayilani doner; folder'a hic erisilemiyorsa
    HafizaHatasi firlatir (bu iki durum ayri mesajlarla yuzeye cikmali)."""
    f = _folder()
    try:
        with f.get_download_stream(yol) as s:
            return json.loads(s.read().decode("utf-8"))
    except Exception:
        return varsayilan


def _yaz(yol, veri):
    govde = json.dumps(veri, ensure_ascii=False, indent=2, default=str)
    _folder().upload_stream(yol, govde.encode("utf-8"))


# ===========================================================================
# WEBAPP TARAFI
# ===========================================================================
def konfig_yaz(is_adi, konfig, oturum_id=None):
    """Senaryoyu tetiklemeden once cagrilir. Doner: kosu_id"""
    konfig = dict(konfig or {})
    konfig["kosu_id"] = konfig.get("kosu_id") or uuid.uuid4().hex
    konfig["oturum_id"] = oturum_id
    konfig["_yazilma"] = datetime.datetime.now().isoformat()
    _yaz(konfig_yolu(is_adi, oturum_id), konfig)
    return konfig["kosu_id"]


def sonuc_temizle(is_adi, oturum_id=None):
    """Eski sonucu gecersiz kilar; senaryo patlarsa bir onceki kosunun
    sonucunu yeni sonuc sanmayalim."""
    _yaz(sonuc_yolu(is_adi, oturum_id),
         {"durum": "bekliyor",
          "_temizlenme": datetime.datetime.now().isoformat()})


# Basarili sayilan senaryo sonuclari
_BASARILI_OUTCOME = ("SUCCESS", "WARNING")


def _outcome(kosu):
    try:
        return ((kosu.get_info() or {}).get("result") or {}).get("outcome")
    except Exception:
        return None


def _kosuyu_bekle(senaryo_adi, zaman_asimi):
    """Senaryoyu tetikler ve en fazla `zaman_asimi` saniye izler.

    Doner: (kosu, hata_metni)
    """
    kutu = {}

    def _calis():
        try:
            proje = dataiku.api_client().get_default_project()
            kutu["kosu"] = proje.get_scenario(senaryo_adi).run_and_wait(
                no_fail=True)
        except Exception as e:      # pylint: disable=broad-except
            kutu["hata"] = e

    is_parcacigi = threading.Thread(target=_calis,
                                    name="senaryo-%s" % senaryo_adi)
    is_parcacigi.daemon = True
    is_parcacigi.start()

    bitis = time.time() + max(1, int(zaman_asimi or 1))
    while is_parcacigi.is_alive() and time.time() < bitis:
        is_parcacigi.join(min(5.0, max(0.1, bitis - time.time())))

    if is_parcacigi.is_alive():
        return None, ("'%s' senaryosu %s saniyede bitmedi; zaman aşımı. "
                      "Senaryo Dataiku'da çalışmaya devam ediyor olabilir."
                      % (senaryo_adi, zaman_asimi))
    if "hata" in kutu:
        return None, ("'%s' senaryosu çalıştırılamadı: %s"
                      % (senaryo_adi, kutu["hata"]))
    return kutu.get("kosu"), None


def calistir(senaryo_adi, is_adi, konfig, oturum_id=None, zaman_asimi=1800):
    """Konfigurasyonu yazar, senaryoyu tetikler, biter bitmez sonucu okur.

    Dosya adlari oturum kimligini tasir ve sonuc dosyasindaki `kosu_id`
    bu cagrinin yazdigi kimlikle karsilastirilir; boylece baska bir
    analistin kosusundan kalan sonuc kendi sonucumuz sanilmaz.

    Doner: (sonuc_sozlugu, hata_metni)
    """
    try:
        kosu_id = konfig_yaz(is_adi, konfig, oturum_id)
        sonuc_temizle(is_adi, oturum_id)
    except HafizaHatasi as e:
        return None, str(e)
    except Exception as e:          # pylint: disable=broad-except
        return None, ("Senaryo konfigürasyonu yazılamadı: %s" % e)

    kosu, hata = _kosuyu_bekle(senaryo_adi, zaman_asimi)
    if hata:
        return None, hata

    # Sonuc dosyasina BAKMADAN once kosunun sonucunu acikca kontrol et.
    outcome = _outcome(kosu)
    if outcome is None:
        return None, ("'%s' senaryosunun sonucu okunamadı; Dataiku'da çalışma "
                      "geçmişini kontrol eder misiniz?" % senaryo_adi)
    if outcome not in _BASARILI_OUTCOME:
        return None, ("'%s' senaryosu başarısız bitti (outcome: %s)."
                      % (senaryo_adi, outcome))

    try:
        sonuc = _oku(sonuc_yolu(is_adi, oturum_id), {})
    except HafizaHatasi as e:
        return None, str(e)
    durum = (sonuc or {}).get("durum")

    if durum == "hata":
        return None, ("Senaryo bir hatayla durdu: %s"
                      % sonuc.get("mesaj", "ayrıntı yok"))
    if durum != "tamam":
        return None, ("Senaryo çalıştı ama sonuç dosyası yazılmamış. "
                      "Senaryo adımının kodunu kontrol eder misiniz?")

    sonuc_kosu = sonuc.get("kosu_id")
    if sonuc_kosu != kosu_id:
        return None, ("Sonuç dosyası bu çalıştırmaya ait değil "
                      "(beklenen koşu kimliği %s, bulunan %s). Başka bir "
                      "koşunun sonucu olabilir; kabul edilmedi."
                      % (kosu_id, sonuc_kosu or "yok"))
    return sonuc, None


# ===========================================================================
# SENARYO TARAFI
# ===========================================================================
def konfig_al(is_adi, oturum_id=None):
    """Senaryo icinde cagrilir; webapp'in biraktigi konfigurasyonu okur.

    Okunan kosu kimligi saklanir; sonuc_yaz/hata_yaz ayni kimligi sonuca
    damgalar, webapp de bunu dogrular.
    """
    yol = konfig_yolu(is_adi, oturum_id)
    k = _oku(yol)
    if not k:
        raise RuntimeError(
            "Konfigürasyon bulunamadı: %s%s. "
            "Senaryo webapp'ten tetiklenmemiş olabilir."
            % (hafiza_folder_adi(), yol))
    _SON_KOSU_ID[(is_adi, oturum_id)] = k.get("kosu_id")
    return k


def _kosu_damgala(sonuc, is_adi, oturum_id):
    if not sonuc.get("kosu_id"):
        kimlik = _SON_KOSU_ID.get((is_adi, oturum_id))
        if kimlik:
            sonuc["kosu_id"] = kimlik
    return sonuc


def sonuc_yaz(is_adi, sonuc, oturum_id=None):
    sonuc = dict(sonuc or {})
    sonuc["durum"] = "tamam"
    sonuc["_bitis"] = datetime.datetime.now().isoformat()
    _kosu_damgala(sonuc, is_adi, oturum_id)
    _yaz(sonuc_yolu(is_adi, oturum_id), sonuc)


def hata_yaz(is_adi, mesaj, oturum_id=None):
    sonuc = {"durum": "hata", "mesaj": str(mesaj)[:2000],
             "_bitis": datetime.datetime.now().isoformat()}
    _kosu_damgala(sonuc, is_adi, oturum_id)
    _yaz(sonuc_yolu(is_adi, oturum_id), sonuc)
