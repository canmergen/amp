# -*- coding: utf-8 -*-
"""fe_agent/spark_is.py - webapp'ten Dataiku PySpark recipe'i calistirma.

Webapp buyuk tabloyu OKUMAZ (kullanici karari: pandas yok, PySpark var).
Tam veriye dokunan her is Flow'daki bir PySpark recipe'inde calisir:

  profil  : compute_AMP_PROFIL    -> AMP_PROFIL klasoru   (profil_spark)
  AMP     : compute_AMP_VERISETI  -> AMP_VERISETI dataset (amp_spark)

Adimlar (her is icin ayni):
  1. Kilit: ayni turden tek is (recipe'in girdisi degistiriliyor; ayrica
     AMP_VERISETI butun calismalarin ortak veri seti).
  2. Recipe'in girdisi secilen veri setine cevrilir (zaten oysa dokunulmaz).
  3. Istek (kosu kimligi + ayarlar) proje degiskenine JSON olarak yazilir;
     recipe okur ve sonuca kosu kimligini damgalar.
  4. Cikti ZORLA yeniden kurulur (Dataiku isi), bitmesi beklenir.

AYARLAR (proje degiskenleri)
  amp_motor : "spark" (varsayilan) ya da "yerel". "yerel" her seyi webapp
              icinde pandas ile yapar; YALNIZCA kucuk veri ve deneme icin.
              (Eski ad amp_profil_motoru da okunur.)
  amp_is_sure : isin en fazla bekleneceği saniye (7200)
"""

import json
import threading
import time
import uuid

import dataiku

from fe_agent.akis_durum import AdimHatasi, _folder, metin_yaz

VARSAYILAN_SURE = 7200


def ayar(anahtar, varsayilan=None):
    try:
        deger = (dataiku.get_custom_variables() or {}).get(anahtar)
    except Exception:           # pylint: disable=broad-except
        deger = None
    if deger is None or not str(deger).strip():
        return varsayilan
    return str(deger).strip()


def motor():
    """"spark" ya da "yerel"."""
    m = (ayar("amp_motor") or ayar("amp_profil_motoru") or "spark").lower()
    return "yerel" if m == "yerel" else "spark"


def sure():
    try:
        return int(float(ayar("amp_is_sure") or ayar("amp_profil_sure")
                         or VARSAYILAN_SURE))
    except (TypeError, ValueError):
        return VARSAYILAN_SURE


def json_oku(klasor, yol):
    try:
        with klasor.get_download_stream(yol) as s:
            return json.loads(s.read().decode("utf-8"))
    except Exception:           # pylint: disable=broad-except
        return None


def istek_oku(degisken_adi):
    """RECIPE TARAFI: webapp'in yazdigi istek (sozluk; yoksa {})."""
    ham = ayar(degisken_adi)
    if isinstance(ham, dict):
        return ham
    try:
        return json.loads(ham) if ham else {}
    except Exception:           # pylint: disable=broad-except
        return {}


# ===========================================================================
# KILIT
# ===========================================================================
def _kilit_yolu(is_adi):
    return "/_isler/%s_kilit.json" % is_adi


def _kilit_al(is_adi, etiket, sahip, veri_seti, sure_sn):
    yol = _kilit_yolu(is_adi)
    kayit = json_oku(_folder(), yol)
    if isinstance(kayit, dict) and kayit.get("sahip") \
            and kayit.get("sahip") != sahip:
        try:
            yas = time.time() - float(kayit.get("zaman") or 0)
        except (TypeError, ValueError):
            yas = sure_sn + 1
        if yas < sure_sn:
            raise AdimHatasi(
                "Başka bir çalışma (%s) şu an %s çalıştırıyor (%s veri seti, "
                "%d dakikadır). Bu iş aynı anda tek çalışabiliyor; biraz "
                "sonra tekrar deneyin."
                % (kayit.get("sahip"), etiket.lower(),
                   kayit.get("veri_seti") or "?", int(yas // 60)))
    metin_yaz(yol, json.dumps({"sahip": sahip, "zaman": time.time(),
                               "veri_seti": veri_seti}, ensure_ascii=False))


def _kilit_birak(is_adi, sahip):
    yol = _kilit_yolu(is_adi)
    kayit = json_oku(_folder(), yol)
    if isinstance(kayit, dict) and kayit.get("sahip") == sahip:
        try:
            _folder().delete_path(yol)
        except Exception:       # pylint: disable=broad-except
            metin_yaz(yol, "{}")


# ===========================================================================
# DATAIKU
# ===========================================================================
def _cikti_kimligi(proje, ad, tur, etiket):
    if tur == "MANAGED_FOLDER":
        for f in proje.list_managed_folders():
            if f.get("name") == ad or f.get("id") == ad:
                return f.get("id")
        raise AdimHatasi(
            "%s için çıktı klasörü (%s) projede bulunamadı. Kurulum adımları "
            "OKU_ONCE.md'de." % (etiket, ad))
    try:
        adlar = {d.get("name") for d in proje.list_datasets()}
    except Exception:           # pylint: disable=broad-except
        adlar = None
    if adlar is not None and ad not in adlar:
        raise AdimHatasi(
            "%s için çıktı veri seti (%s) Flow'da tanımlı değil. Kurulum "
            "adımları OKU_ONCE.md'de." % (etiket, ad))
    return ad


def _girdiyi_ayarla(proje, recete_adi, veri_seti, etiket):
    try:
        ayarlar = proje.get_recipe(recete_adi).get_settings()
    except Exception as e:      # pylint: disable=broad-except
        raise AdimHatasi(
            "%s recipe'i (%s) açılamadı: %s. Kurulum adımları OKU_ONCE.md'de."
            % (etiket, recete_adi, str(e)[:160]))
    girdiler = list(ayarlar.get_flat_input_refs())
    if girdiler == [veri_seti]:
        return
    if len(girdiler) != 1:
        raise AdimHatasi("%s recipe'inin (%s) tek girdisi olmalı; şu an %d "
                         "girdi var." % (etiket, recete_adi, len(girdiler)))
    # Baska projedeki veri seti ("PROJE.VERI") ancak o proje bu projeye
    # PAYLASTIYSA (Exposed objects) girdi olabilir.
    try:
        ayarlar.replace_input(girdiler[0], veri_seti)
        ayarlar.save()
    except Exception as e:      # pylint: disable=broad-except
        raise AdimHatasi(
            "%s recipe'inin girdisi %s olarak ayarlanamadı: %s. Veri seti "
            "başka bir projedeyse o projenin veri setini bu projeye "
            "paylaşması (Exposed objects) gerekir."
            % (etiket, veri_seti, str(e)[:160]))


def _istek_yaz(proje, degisken_adi, istek):
    degisken = proje.get_variables()
    degisken.setdefault("standard", {})[degisken_adi] = json.dumps(
        istek, ensure_ascii=False, default=str)
    proje.set_variables(degisken)


def _isi_bekle(proje, cikti_id, cikti_tur, sure_sn, etiket):
    kutu = {}

    def calis():
        try:
            is_ = proje.new_job("NON_RECURSIVE_FORCED_BUILD")
            is_.with_output(cikti_id, object_type=cikti_tur)
            kutu["is"] = is_.start_and_wait(no_fail=True)
        except Exception as e:  # pylint: disable=broad-except
            kutu["hata"] = e

    t = threading.Thread(target=calis, name="amp-" + etiket)
    t.daemon = True
    t.start()
    t.join(sure_sn)
    if t.is_alive():
        raise AdimHatasi(
            "%s %d dakikada bitmedi; Dataiku'da çalışmaya devam ediyor "
            "olabilir (Jobs ekranından izleyebilirsiniz). Bittikten sonra "
            "adımı yeniden onaylayın." % (etiket, sure_sn // 60))
    if "hata" in kutu:
        raise AdimHatasi("%s başlatılamadı: %s" % (etiket, str(kutu["hata"])[:300]))
    is_ = kutu.get("is")
    try:
        durum = ((is_.get_status() or {}).get("baseStatus") or {}).get("state")
    except Exception:           # pylint: disable=broad-except
        durum = None
    if durum != "DONE":
        ozet = hata_ozeti(is_)
        raise AdimHatasi("%s başarısız bitti (%s).%s"
                         % (etiket, durum or "durum okunamadı",
                            ("\n\nHata:\n" + ozet) if ozet else ""))


def _hata_satirlari(metin, en_cok=25):
    """Gunlukten ASIL hatayi cikarir. Isin genel gunlugunun sonu yalnizca
    "JOB IS COMPLETE" gibi kapanis satirlari (kullanici bildirimi); hata
    recipe'in (aktivitenin) gunlugunde, Python traceback'i olarak durur."""
    satirlar = str(metin or "").splitlines()
    bas = None
    for i, s in enumerate(satirlar):
        if "Traceback (most recent call last)" in s:
            bas = i
    if bas is not None:
        return satirlar[bas:bas + en_cok]
    hatali = [s for s in satirlar
              if any(k in s for k in ("Error", "Exception", "FAILED", "failed"))
              and "[DEBUG]" not in s]
    return hatali[-en_cok:]


def hata_ozeti(is_):
    """Basarisiz Dataiku isinin okunur hata ozeti ("" olabilir)."""
    parca = []
    try:
        durum = is_.get_status() or {}
        aktiviteler = (durum.get("baseStatus") or {}).get("activities") or {}
    except Exception:           # pylint: disable=broad-except
        aktiviteler = {}
    for kimlik, akt in (aktiviteler.items() if isinstance(aktiviteler, dict) else []):
        if not isinstance(akt, dict) or akt.get("state") not in ("FAILED", "ABORTED"):
            continue
        hata = akt.get("firstFailure") or {}
        if hata.get("message"):
            parca.append(str(hata.get("message"))[:500])
        try:
            parca.extend(_hata_satirlari(is_.get_log(activity=kimlik)))
        except Exception:       # pylint: disable=broad-except
            pass
    if not parca:
        try:
            parca = _hata_satirlari(is_.get_log())
        except Exception:       # pylint: disable=broad-except
            parca = []
    # Tekrarlari at, sirayi koru.
    return "\n".join(dict.fromkeys(p for p in parca if p.strip()))


class kilitli(object):
    """Ayni turden tek is: webapp'teki oturumda calisan is de recipe ile
    AYNI kilidi tutar (AMP_VERISETI butun calismalarin ortak veri seti).

        with spark_is.kilitli("amp", "AMP_VERISETI yazma işi", sahip, girdi):
            ..."""

    def __init__(self, is_adi, etiket, sahip, girdi):
        self.arg = (is_adi, etiket, sahip, girdi)

    def __enter__(self):
        is_adi, etiket, sahip, girdi = self.arg
        _kilit_al(is_adi, etiket, sahip, girdi, sure())
        return self

    def __exit__(self, *hata):
        _kilit_birak(self.arg[0], self.arg[2])
        return False


def calistir(is_adi, etiket, recete, cikti, cikti_tur, girdi,
             istek_degiskeni, istek, sahip, kosu_id=None):
    """Recipe'i `girdi` icin calistirir. istek'e kosu_id eklenir.
    Doner: kosu_id. Hata -> AdimHatasi (mesaj kullaniciya gider)."""
    sure_sn = sure()
    _kilit_al(is_adi, etiket, sahip, girdi, sure_sn)
    try:
        proje = dataiku.api_client().get_default_project()
        cikti_id = _cikti_kimligi(proje, cikti, cikti_tur, etiket)
        _girdiyi_ayarla(proje, recete, girdi, etiket)
        kosu_id = kosu_id or uuid.uuid4().hex
        istek = dict(istek or {}, kosu_id=kosu_id, veri_seti=girdi)
        _istek_yaz(proje, istek_degiskeni, istek)
        _isi_bekle(proje, cikti_id, cikti_tur, sure_sn, etiket)
        return kosu_id
    finally:
        _kilit_birak(is_adi, sahip)
