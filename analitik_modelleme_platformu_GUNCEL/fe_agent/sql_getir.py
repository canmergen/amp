# -*- coding: utf-8 -*-
"""fe_agent/sql_getir.py - SQL SORGUSUYLA VERI GETIRME.

Kullanici karari: kaynak tablolar (ve baz veri seti) SQL ile cekilebilir;
"SQL verileri sadece çekilecek ve işlemler yapılacak sonrasında". Sorgu
yalnizca VERI CEKER; birlestirme, profil, donusum gibi her is sonra
platformda yapilir.

KULLANICI FLOW'A BIR SEY EKLEMEZ. Kartta bir ad, bir baglanti ve bir sorgu
verilir; webapp su nesneleri KENDISI kurar:

    <AD>_SQL        sorgu veri seti (baglantida, "query" modu)
    compute_<AD>    Sync recipe'i
    <AD>            sonuc: depo baglantisinda (S3) Parquet veri seti

<AD> bundan sonra normal bir Dataiku veri seti gibi davranir: listede
gorunur, secilir, boyutu olculur (motor secimi), Spark ya da pandas okur.
Ayni adla yeniden getirildiginde sorgu guncellenir ve tablo yeniden
yazilir. Platformun kurmadigi (etiketsiz) ayni adli bir nesne varsa
DOKUNULMAZ; baska ad istenir.

YALNIZCA OKUMA: sorgu SELECT ya da WITH ile baslamali, tek ifade olmali
ve veri degistiren komut (INSERT, UPDATE, DELETE, DROP ...) tasimamali.

IS ARKA PLANDA: cekme dakikalar surebilir. baslat() is kimligi doner,
arayuz durum() ile yoklar.

AYARLAR (proje degiskenleri; tanimli degilse varsayilanlar)
  amp_depo_baglanti : sonuc veri setinin yazilacagi baglanti. Varsayilan:
                      PROJE_HAFIZASI klasorunun baglantisi.
  amp_sql_baglantilari : baglanti listesi okunamazsa elle liste,
                      "AD:TUR, AD2:TUR2" (ornek "DWH:Oracle").
"""

import re
import threading
import time
import uuid

import dataiku

from fe_agent.akis_durum import AdimHatasi, HAFIZA_FOLDER

ETIKET = "AMP_SQL"
SONEK_SORGU = "_SQL"
ONEK_RECETE = "compute_"
AD_KALIP = re.compile(r"^[A-Za-z][A-Za-z0-9_]{1,59}$")
AYRILMIS_ONEKLER = ("AMP_", "MODELLEME_")

# Dataiku'nun SQL baglanti turleri (liste bu turlerle sorgulanir)
# (Dataiku API'sinin sorgudan sema cikarabildigi turler)
SQL_TURLERI = ("Oracle", "Teradata", "PostgreSQL", "SQLServer", "MySQL",
               "Greenplum", "Vertica", "Redshift", "Snowflake", "BigQuery",
               "Synapse", "Netezza", "SAPHANA", "Databricks", "Athena",
               "hiveserver2", "FabricWarehouse", "ClickHouse", "JDBC")

_YASAK = re.compile(r"\b(insert|update|delete|merge|drop|create|alter|truncate|"
                    r"grant|revoke|exec|execute|call|begin|declare|commit|"
                    r"rollback|replace|rename|lock)\b", re.I)


# ===========================================================================
# DENETIM
# ===========================================================================
def _yorumsuz(sorgu):
    sorgu = re.sub(r"/\*.*?\*/", " ", sorgu, flags=re.S)
    return re.sub(r"--[^\n]*", " ", sorgu)


def sorgu_denetle(sorgu):
    """Doner: temizlenmis sorgu. Hata -> AdimHatasi."""
    metin = str(sorgu or "").strip()
    while metin.endswith(";"):
        metin = metin[:-1].rstrip()
    if not metin:
        raise AdimHatasi("Sorgu boş.")
    govde = _yorumsuz(metin)
    # Metin sabitleri ('...') icindeki kelimeler komut sayilmaz.
    govde = re.sub(r"'(?:[^']|'')*'", "''", govde)
    if ";" in govde:
        raise AdimHatasi("Tek sorgu yazın; noktalı virgülle ayrılmış birden "
                         "fazla ifade çalıştırılmaz.")
    if not re.match(r"^\s*(select|with)\b", govde, flags=re.I):
        raise AdimHatasi("Sorgu SELECT ya da WITH ile başlamalı; yalnızca "
                         "veri çeken sorgular çalıştırılır.")
    yasak = _YASAK.search(govde)
    if yasak:
        raise AdimHatasi("Sorguda veri değiştiren komut var (%s); yalnızca "
                         "veri çeken sorgular çalıştırılır." % yasak.group(1).upper())
    return metin


def ad_denetle(ad):
    ad = str(ad or "").strip()
    if not AD_KALIP.match(ad):
        raise AdimHatasi("Veri seti adı harfle başlamalı; yalnızca harf, rakam "
                         "ve alt tire içermeli (2-60 karakter).")
    if ad.upper().startswith(AYRILMIS_ONEKLER):
        raise AdimHatasi("AMP_ ve MODELLEME_ ile başlayan adlar platformun "
                         "kendi veri setlerine ayrılmış; başka bir ad verin.")
    return ad


# ===========================================================================
# BAGLANTILAR
# ===========================================================================
_BAGLANTI_ONBELLEK = {"zaman": 0.0, "liste": None}
BAGLANTI_OMUR_SN = 600


def _ayar(anahtar):
    try:
        deger = (dataiku.get_custom_variables() or {}).get(anahtar)
    except Exception:           # pylint: disable=broad-except
        deger = None
    return str(deger).strip() if deger not in (None, "") else ""


def baglantilar(taze=False):
    """Kullanicinin kullanabildigi SQL baglantilari: [{"ad", "tur"}]."""
    if not taze and _BAGLANTI_ONBELLEK["liste"] is not None and \
            time.time() - _BAGLANTI_ONBELLEK["zaman"] < BAGLANTI_OMUR_SN:
        return list(_BAGLANTI_ONBELLEK["liste"])
    liste, gorulen = [], set()
    istemci = dataiku.api_client()
    for tur in SQL_TURLERI:
        try:
            adlar = istemci.list_connections_names(tur) or []
        except Exception:       # pylint: disable=broad-except
            adlar = []
        for ad in adlar:
            if ad not in gorulen:
                gorulen.add(ad)
                liste.append({"ad": str(ad), "tur": tur})
    for parca in _ayar("amp_sql_baglantilari").split(","):
        ad, _, tur = parca.strip().partition(":")
        if ad.strip() and ad.strip() not in gorulen:
            gorulen.add(ad.strip())
            liste.append({"ad": ad.strip(), "tur": tur.strip() or None})
    liste.sort(key=lambda x: x["ad"].lower())
    _BAGLANTI_ONBELLEK.update(zaman=time.time(), liste=liste)
    return list(liste)


def _baglanti_turu(proje, baglanti):
    for b in baglantilar():
        if b["ad"] == baglanti and b.get("tur"):
            return b["tur"]
    try:
        return dataiku.api_client().get_connection(baglanti).get_info().get_type()
    except Exception:           # pylint: disable=broad-except
        pass
    # Projede ayni baglantiyi kullanan bir veri seti varsa onun turu
    try:
        for d in proje.list_datasets():
            if (d.get("params") or {}).get("connection") == baglanti and d.get("type"):
                return d["type"]
    except Exception:           # pylint: disable=broad-except
        pass
    raise AdimHatasi("'%s' bağlantısının türü okunamadı. Proje değişkenlerine "
                     "amp_sql_baglantilari = \"%s:Oracle\" gibi bir satır "
                     "ekleyin (tür Dataiku'daki bağlantı türü)." % (baglanti, baglanti))


def depo_baglantisi(proje=None):
    """Sonuc veri setlerinin yazilacagi dosya baglantisi: (ad, tur)."""
    proje = proje or dataiku.api_client().get_default_project()
    ad = _ayar("amp_depo_baglanti")
    tur = _ayar("amp_depo_turu")
    if ad:
        return ad, (tur or "S3")
    for f in proje.list_managed_folders():
        if f.get("name") == HAFIZA_FOLDER:
            ham = proje.get_managed_folder(f.get("id")).get_settings().get_raw()
            return (ham.get("params") or {}).get("connection"), ham.get("type")
    raise AdimHatasi("Sonucun yazılacağı bağlantı bulunamadı. Proje "
                     "değişkenlerine amp_depo_baglanti ekleyin.")


# ===========================================================================
# FLOW NESNELERI
# ===========================================================================
def _veri_seti(proje, ad):
    for d in proje.list_datasets():
        if d.get("name") == ad:
            return d
    return None


def _bizim_mi(kayit):
    return kayit is None or ETIKET in (kayit.get("tags") or [])


def _etiketle(ds):
    ayar = ds.get_settings()
    ham = ayar.get_raw()
    if ETIKET not in (ham.get("tags") or []):
        ham["tags"] = list(ham.get("tags") or []) + [ETIKET]
        ayar.save()


def _sorgu_veri_seti_kur(proje, ad, baglanti, tur, sorgu):
    params = {"connection": baglanti, "mode": "query", "query": sorgu}
    if _veri_seti(proje, ad) is None:
        ds = proje.create_dataset(ad, tur, params=params)
    else:
        ds = proje.get_dataset(ad)
        ayar = ds.get_settings()
        ham = ayar.get_raw()
        ham.setdefault("params", {}).update(params)
        ham["type"] = tur
        ayar.save()
    _etiketle(ds)
    # Sema sorgudan cikarilir (Dataiku sorguyu calistirip kolonlari okur).
    try:
        ds.autodetect_settings().save()
    except Exception as e:      # pylint: disable=broad-except
        raise AdimHatasi("Sorgunun kolonları okunamadı; sorguyu kontrol edin.\n"
                         "  Hata : %s" % str(e)[:300].replace(":", " ·"))
    return ds


def _cikti_kur(proje, ad):
    if _veri_seti(proje, ad) is not None:
        ds = proje.get_dataset(ad)
        _etiketle(ds)
        return ds
    baglanti, _tur = depo_baglantisi(proje)
    son = None
    for bicim in ("PARQUET_HIVE", None):
        try:
            yardimci = proje.new_managed_dataset(ad)
            yardimci.with_store_into(baglanti, format_option_id=bicim)
            ds = yardimci.create()
            ds = ds if ds is not None else proje.get_dataset(ad)
            _etiketle(ds)
            return ds
        except Exception as e:  # pylint: disable=broad-except
            son = e
    raise AdimHatasi("Sonuç veri seti (%s) oluşturulamadı: %s" % (ad, str(son)[:200]))


def _recete_kur(proje, recete, girdi, cikti):
    try:
        r = proje.get_recipe(recete)
        r.get_settings()
        var = True
    except Exception:           # pylint: disable=broad-except
        var = False
    if not var:
        kurucu = proje.new_recipe("sync", recete)
        kurucu.with_input(girdi)
        kurucu.with_existing_output(cikti)
        r = kurucu.create()
        r = r if r is not None else proje.get_recipe(recete)
    # Cikti semasi sorgunun kolonlarina esitlenir (sorgu degismis olabilir).
    try:
        guncelleme = r.compute_schema_updates()
        if guncelleme.any_action_required():
            guncelleme.apply()
    except Exception as e:      # pylint: disable=broad-except
        raise AdimHatasi("Sonuç veri setinin kolonları ayarlanamadı: %s" % str(e)[:200])
    return r


def getir(ad, baglanti, sorgu):
    """Sorguyu calistirir, sonucu <AD> veri setine yazar. Doner: ozet.
    Hata -> AdimHatasi."""
    from fe_agent import motor, spark_is
    ad = ad_denetle(ad)
    sorgu = sorgu_denetle(sorgu)
    if not baglanti:
        raise AdimHatasi("Bağlantı seçilmedi.")
    proje = dataiku.api_client().get_default_project()
    sorgu_ad = ad + SONEK_SORGU
    recete = ONEK_RECETE + ad
    for nesne in (ad, sorgu_ad):
        if not _bizim_mi(_veri_seti(proje, nesne)):
            raise AdimHatasi("Projede %s adında platformun kurmadığı bir veri seti "
                             "var; ona dokunulmaz. Başka bir ad verin." % nesne)
    tur = _baglanti_turu(proje, baglanti)
    bas = time.time()
    _sorgu_veri_seti_kur(proje, sorgu_ad, baglanti, tur, sorgu)
    _cikti_kur(proje, ad)
    _recete_kur(proje, recete, sorgu_ad, ad)
    spark_is._isi_bekle(proje, ad, "DATASET", spark_is.sure(), "SQL çekme işi")
    motor.unut(ad)
    from fe_agent.akis_durum import onbellek_temizle
    onbellek_temizle(ad)
    return {"ad": ad, "sure_sn": int(time.time() - bas),
            "boyut": motor.boyut(ad), "boyut_metni": motor.boyut_metni(motor.boyut(ad))}


# ===========================================================================
# ARKA PLAN ISI
# ===========================================================================
_ISLER = {}
_KILIT = threading.Lock()
IS_SINIRI = 20


def baslat(ad, baglanti, sorgu):
    """Ad ve sorguyu hemen denetler (hatali giris beklemeden doner), isi
    arka planda baslatir. Doner: is kimligi."""
    ad_denetle(ad)
    sorgu_denetle(sorgu)
    with _KILIT:
        for kayit in _ISLER.values():
            if kayit.get("ad") == ad and not kayit.get("bitti"):
                raise AdimHatasi("%s için çekme işi zaten sürüyor." % ad)
        if len(_ISLER) >= IS_SINIRI:
            for k in sorted(_ISLER, key=lambda k: _ISLER[k]["zaman"])[:5]:
                if _ISLER[k].get("bitti"):
                    _ISLER.pop(k, None)
        kimlik = uuid.uuid4().hex[:12]
        _ISLER[kimlik] = {"ad": ad, "zaman": time.time(), "bitti": False}

    def calis():
        try:
            sonuc = getir(ad, baglanti, sorgu)
            _ISLER[kimlik].update(bitti=True, sonuc=sonuc)
        except AdimHatasi as e:
            _ISLER[kimlik].update(bitti=True, hata=str(e))
        except Exception as e:  # pylint: disable=broad-except
            _ISLER[kimlik].update(bitti=True, hata="SQL çekme işi başarısız: %s"
                                  % str(e)[:300])

    t = threading.Thread(target=calis, name="amp-sql-" + ad)
    t.daemon = True
    t.start()
    return kimlik


def durum(kimlik):
    kayit = _ISLER.get(kimlik)
    if not kayit:
        return {"bitti": True, "hata": "İş bulunamadı (webapp yeniden başlamış olabilir)."}
    cikti = {"bitti": bool(kayit.get("bitti")), "ad": kayit.get("ad"),
             "gecen_sn": int(time.time() - kayit["zaman"])}
    if kayit.get("hata"):
        cikti["hata"] = kayit["hata"]
    if kayit.get("sonuc"):
        cikti["sonuc"] = kayit["sonuc"]
    return cikti
