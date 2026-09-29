# -*- coding: utf-8 -*-
"""fe_agent/spark_is.py - tam veriye dokunan isleri Dataiku'da PySpark ile
calistirma (webapp tarafi).

NEDEN SPARK (kullanici karari): gercek veri 135 milyon satir x 1.040 kolon.
Bu hacim webapp'in makinesine indirilemez; veri kumede, oldugu yerde
islenir. Webapp yalnizca sonuc dosyalarini (profil, set sayilari) okur.

KURULUM YOK: gereken Flow nesnelerini webapp KENDISI kurar (kullanici
Flow'a hicbir sey eklemez). Her is icin:
  - bir PySpark recipe'i  (compute_AMP_<IS>, kodu tek satir),
  - ciktilari: sonuc KLASORU ve gerekiyorsa bir veri seti.
Veri seti ve klasor, girdi veri setinin durdugu baglantida (S3 vb.)
acilir; veri seti bicimi Parquet. Dataiku'da bir nesne yalnizca TEK bir
recipe'in ciktisi olabildigi icin her isin kendi sonuc klasoru var.
Kullanicinin girdi tablolarina ve sozlugune YAZILMAZ.

Her calistirmada:
  1. Kilit: ayni turden tek is (ciktilar butun calismalarin ortak nesnesi).
  2. Recipe'in girdileri secilen tablo(lar)a cevrilir, kodu tazelenir.
  3. Istek (kosu kimligi + ayarlar) proje degiskenine JSON olarak yazilir;
     recipe okur ve sonuca kosu kimligini damgalar.
  4. Ciktilar ZORLA yeniden kurulur (Dataiku isi), bitmesi beklenir.

AYARLAR (proje degiskenleri; tanimli degilse varsayilanlar)
  amp_is_sure : bir isin en fazla bekleneceği saniye (10800 = 3 saat)
"""

import json
import threading
import time
import uuid

import dataiku

from fe_agent.akis_durum import AdimHatasi, _folder, metin_yaz

VARSAYILAN_SURE = 10800

# Is tanimlari: recipe adi, kodu ve ciktilari. Ciktinin turu "KLASOR" ya da
# "VERI" (Parquet veri seti). Ilk cikti isin "insa edilen" nesnesidir.
ISLER = {
    "profil": {
        "etiket": "Profil işi",
        "recete": "compute_AMP_PROFIL",
        "kod": "from fe_agent import profil_spark\nprofil_spark.recete_calistir()\n",
        "ciktilar": [("AMP_PROFIL", "KLASOR")],
    },
    "baz": {
        "etiket": "Alt alta ekleme işi",
        "recete": "compute_AMP_BAZ",
        "kod": "from fe_agent import amp_spark\namp_spark.baz_recete_calistir()\n",
        "ciktilar": [("MODELLEME_BAZ", "VERI"), ("AMP_BAZ_SONUC", "KLASOR")],
    },
    "amp": {
        "etiket": "AMP_VERISETI yazma işi",
        "recete": "compute_AMP_VERISETI",
        "kod": "from fe_agent import amp_spark\namp_spark.recete_calistir()\n",
        "ciktilar": [("AMP_VERISETI", "VERI"), ("AMP_SONUC", "KLASOR")],
    },
}


def ayar(anahtar, varsayilan=None):
    try:
        deger = (dataiku.get_custom_variables() or {}).get(anahtar)
    except Exception:           # pylint: disable=broad-except
        deger = None
    if deger is None or not str(deger).strip():
        return varsayilan
    return str(deger).strip()


def sure():
    try:
        return int(float(ayar("amp_is_sure") or VARSAYILAN_SURE))
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


def istek_degiskeni(is_adi):
    return "amp_%s_istek" % is_adi


def klasor(ad):
    """Sonuc klasoru (ad ile)."""
    return dataiku.Folder(ad)


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
                "Başka bir çalışma (%s) şu an %s çalıştırıyor (%s, %d dakikadır). "
                "Bu iş aynı anda tek çalışabiliyor; biraz sonra tekrar deneyin."
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
# FLOW NESNELERINI KURMA (kullanici Flow'a bir sey eklemez)
# ===========================================================================
def _proje_ve_ad(proje, ref):
    """"PROJE.VERI" -> (o projenin handle'i, "VERI")."""
    if "." in ref:
        pk, ad = ref.split(".", 1)
        if pk != proje.project_key:
            return dataiku.api_client().get_project(pk), ad
        return proje, ad
    return proje, ref


def _baglanti(proje, girdi):
    """Ciktilarin acilacagi baglanti ve turu: girdi veri setininki (S3,
    HDFS ...). Girdi bir SQL tablosuysa orada klasor ve Parquet acilamaz;
    o zaman depo baglantisi (bkz. sql_getir)."""
    from fe_agent import sql_getir
    p, ad = _proje_ve_ad(proje, girdi)
    ham = p.get_dataset(ad).get_settings().get_raw()
    if ham.get("type") in sql_getir.SQL_TURLERI:
        return sql_getir.depo_baglantisi(proje)
    return (ham.get("params") or {}).get("connection"), ham.get("type")


def _klasor_kimligi(proje, ad):
    for f in proje.list_managed_folders():
        if f.get("name") == ad or f.get("id") == ad:
            return f.get("id")
    return None


def _veri_seti_var_mi(proje, ad):
    return any(d.get("name") == ad for d in proje.list_datasets())


def _cikti_kur(proje, ad, tur, baglanti, baglanti_turu, etiket):
    """Cikti yoksa olusturur. Doner: recipe'te kullanilacak ref (klasorde id)."""
    if tur == "KLASOR":
        kimlik = _klasor_kimligi(proje, ad)
        if kimlik:
            return kimlik
        try:
            kimlik = proje.create_managed_folder(
                ad, folder_type=baglanti_turu, connection_name=baglanti).id
        except Exception as e:      # pylint: disable=broad-except
            raise AdimHatasi("%s için sonuç klasörü (%s) oluşturulamadı: %s"
                             % (etiket, ad, str(e)[:200]))
        return kimlik
    if _veri_seti_var_mi(proje, ad):
        return ad
    son_hata = None
    for bicim in ("PARQUET_HIVE", None):
        try:
            yardimci = proje.new_managed_dataset(ad)
            yardimci.with_store_into(baglanti, format_option_id=bicim)
            yardimci.create()
            return ad
        except Exception as e:      # pylint: disable=broad-except
            son_hata = e
    raise AdimHatasi("%s için çıktı veri seti (%s) oluşturulamadı: %s"
                     % (etiket, ad, str(son_hata)[:200]))


def _recete_kur(proje, tanim, girdiler, cikti_refleri):
    """Recipe yoksa olusturur; varsa girdilerini ve kodunu tazeler."""
    ad = tanim["recete"]
    try:
        ayarlar = proje.get_recipe(ad).get_settings()
        ayarlar.get_recipe_raw_definition()
        var = True
    except Exception:           # pylint: disable=broad-except
        var = False
    if not var:
        try:
            kurucu = proje.new_recipe("pyspark", ad)
            for g in girdiler:
                kurucu.with_input(g)
            for c in cikti_refleri:
                kurucu.with_output(c)
            kurucu.with_script(tanim["kod"])
            kurucu.create()
        except Exception as e:      # pylint: disable=broad-except
            raise AdimHatasi("%s için PySpark recipe'i (%s) oluşturulamadı: %s"
                             % (tanim["etiket"], ad, str(e)[:200]))
        return
    tanimi = ayarlar.get_recipe_raw_definition()
    girdi_rolu = (tanimi.setdefault("inputs", {})).setdefault("main", {"items": []})
    mevcut = [x.get("ref") for x in girdi_rolu.get("items") or []]
    degisti = False
    if mevcut != list(girdiler):
        girdi_rolu["items"] = [{"ref": g, "deps": []} for g in girdiler]
        degisti = True
    try:
        if (ayarlar.get_payload() or "") != tanim["kod"]:
            ayarlar.set_payload(tanim["kod"])
            degisti = True
    except Exception:           # pylint: disable=broad-except
        pass
    if degisti:
        try:
            ayarlar.save()
        except Exception as e:      # pylint: disable=broad-except
            raise AdimHatasi(
                "%s recipe'inin girdileri %s olarak ayarlanamadı: %s. Tablo başka "
                "bir projedeyse o projenin tabloyu bu projeye paylaşması "
                "(Exposed objects) gerekir."
                % (tanim["etiket"], ", ".join(girdiler), str(e)[:200]))


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
    """Gunlukten ASIL hatayi cikarir (recipe'in Python traceback'i)."""
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
    return "\n".join(dict.fromkeys(p for p in parca if p.strip()))


# ===========================================================================
# DIS ARAYUZ
# ===========================================================================
def calistir(is_adi, girdiler, istek, sahip, kosu_id=None):
    """ISLER[is_adi] isini `girdiler` (tablo adlari) icin calistirir.
    Doner: kosu_id. Hata -> AdimHatasi (mesaj kullaniciya gider)."""
    tanim = ISLER[is_adi]
    etiket = tanim["etiket"]
    girdiler = [g for g in (girdiler or []) if g]
    if not girdiler:
        raise AdimHatasi("%s için girdi tablosu seçilmedi." % etiket)
    sure_sn = sure()
    _kilit_al(is_adi, etiket, sahip, ", ".join(girdiler), sure_sn)
    try:
        proje = dataiku.api_client().get_default_project()
        try:
            baglanti, baglanti_turu = _baglanti(proje, girdiler[0])
        except Exception as e:      # pylint: disable=broad-except
            raise AdimHatasi("%s tablosunun bağlantısı okunamadı: %s"
                             % (girdiler[0], str(e)[:200]))
        refler = [_cikti_kur(proje, ad, tur, baglanti, baglanti_turu, etiket)
                  for ad, tur in tanim["ciktilar"]]
        _recete_kur(proje, tanim, girdiler, refler)
        kosu_id = kosu_id or uuid.uuid4().hex
        istek = dict(istek or {}, kosu_id=kosu_id, girdiler=girdiler,
                     veri_seti=girdiler[0])
        _istek_yaz(proje, istek_degiskeni(is_adi), istek)
        ilk_ad, ilk_tur = tanim["ciktilar"][0]
        _isi_bekle(proje, refler[0],
                   "MANAGED_FOLDER" if ilk_tur == "KLASOR" else "DATASET",
                   sure_sn, etiket)
        return kosu_id
    finally:
        _kilit_birak(is_adi, sahip)


def veri_seti_hazirla(ad, kaynak_tablo):
    """`ad` veri seti Flow'da yoksa kaynak_tablo'nun baglantisinda (Parquet)
    olusturur. Webapp'in pandas ile yazdigi kucuk sonuclar (yapay zeka
    planiyla yan yana birlestirme) icin; kullanici Flow'a bir sey eklemez."""
    proje = dataiku.api_client().get_default_project()
    if _veri_seti_var_mi(proje, ad):
        return
    baglanti, baglanti_turu = _baglanti(proje, kaynak_tablo)
    _cikti_kur(proje, ad, "VERI", baglanti, baglanti_turu, ad)


def sonuc_oku(is_adi, yol, kosu_id):
    """Isin sonuc klasorundeki JSON; bu kosuya ait degilse AdimHatasi."""
    tanim = ISLER[is_adi]
    klasor_ad = [ad for ad, tur in tanim["ciktilar"] if tur == "KLASOR"][0]
    sonuc = json_oku(klasor(klasor_ad), yol)
    if not isinstance(sonuc, dict):
        raise AdimHatasi("%s bitti ama sonucu okunamadı (%s%s)."
                         % (tanim["etiket"], klasor_ad, yol))
    if sonuc.get("kosu_id") != kosu_id:
        raise AdimHatasi("%s sonucu bu çalıştırmaya ait değil; adımı yeniden onaylayın."
                         % tanim["etiket"])
    return sonuc
