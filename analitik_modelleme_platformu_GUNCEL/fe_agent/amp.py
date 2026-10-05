# -*- coding: utf-8 -*-
"""fe_agent/amp.py - AMP_VERISETI'ni ve alt alta eklenen baz veri setini
yazdirma (webapp tarafi).

MOTOR VERININ BOYUTUNA GORE (bkz. motor.py): kucuk veri webapp icinde
pandas ile (amp_pandas), buyuk veri Dataiku'daki PySpark recipe'leriyle
(amp_spark; recipe'leri ve ciktilarini webapp kurar, spark_is.ISLER).
Iki yolun sonuc sozlugu ayni bicimde; cagiran taraf motoru bilmez.

  amp_yaz       : Degisken Kontrolu onayinda tip donusumleri + surec disi
                  kolonlar (KAYNAK TABLODAN, bir kez).
  amp_bolme_yaz : Orneklem ve Dogrulama'da _SPLIT; KAYNAK AMP_VERISETI'nin
                  KENDISI.

CALISMAYA OZEL: pandas yolunda AMP_VERISETI calismanin
PROJE_HAFIZASI klasorune Parquet yazilir (/<calisma>/AMP_VERISETI.parquet).
Spark yolunda Dataiku kurali geregi cikti bir veri setidir; adi calismaya
ozeldir (AMP_VERISETI_V8), baska bir calisma onu ezemez.
  baz_yaz   : Mod B/D'de ayni kolonlu kaynak tablolar alt alta ->
              MODELLEME_BAZ.
"""

import re

from fe_agent import motor
from fe_agent import profil as profil_mod
from fe_agent import profil_kural
from fe_agent import spark_is
from fe_agent import tip_donusum
from fe_agent import tablo_io
from fe_agent.akis_durum import (AdimHatasi, _df_oku, _folder, dataset_yaz,
                                 onbellek_temizle)

SONUC_DOSYA = "/sonuc.json"
DISARIDA = "disarida"      # hicbir sete girmeyen satir (amp_spark ile ayni)
BAZ_VERI_ADI = "MODELLEME_BAZ"
AMP_VERI_ADI = "AMP_VERISETI"


def dusen_kolonlar(durum, adlar):
    """Surec disi kolonlar; hedef / kimlik / donem hicbir zaman dusmez."""
    korunan = {str(v) for v in (durum.get("meta") or {}).values() if v}
    haric = set(map(str, durum.get("haric_kolonlar") or []))
    return [c for c in adlar if str(c) in haric and str(c) not in korunan]


def yeniden_ad_esleme(durum, adlar):
    """Uygulanacak {eski: yeni}: tabloda olan, rol / surec disi olmayan."""
    korunan = {str(v) for v in (durum.get("meta") or {}).values() if v}
    dusen = set(dusen_kolonlar(durum, adlar))
    adlar = set(map(str, adlar))
    return {a: y for a, y in (durum.get("kolon_yeni_ad") or {}).items()
            if a in adlar and a not in korunan and a not in dusen and y and y not in adlar}


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


def _sonuc_ile_calistir(is_adi, girdiler, istek, sahip, ad_eki=None):
    """Isi calistirir ve sonuc.json'u doner. Is basarisiz bittiyse ama
    recipe kendi hatasini (ornegin cevrilemeyen hucre) sonuca yazdiysa o
    daha anlasilir oldugu icin o gosterilir."""
    import uuid
    kosu_id = uuid.uuid4().hex
    try:
        spark_is.calistir(is_adi, girdiler, istek, sahip, kosu_id=kosu_id,
                          ad_eki=ad_eki)
    except AdimHatasi:
        try:
            sonuc = spark_is.sonuc_oku(is_adi, SONUC_DOSYA, kosu_id, ad_eki)
        except AdimHatasi:
            sonuc = None
        if isinstance(sonuc, dict) and sonuc.get("hata"):
            raise AdimHatasi(sonuc["hata"])
        raise
    sonuc = spark_is.sonuc_oku(is_adi, SONUC_DOSYA, kosu_id, ad_eki)
    if sonuc.get("hata"):
        raise AdimHatasi(sonuc["hata"])
    return sonuc


def _pandas_yaz(ad, tablo, kaynak):
    """Pandas yolunun sonucunu Flow'daki veri setine yazar (veri seti yoksa
    kaynak tablonun baglantisinda Parquet olarak kurulur)."""
    spark_is.veri_seti_hazirla(ad, kaynak)
    if not dataset_yaz(ad, tablo):
        raise AdimHatasi("Sonuç %s veri setine yazılamadı." % ad)
    onbellek_temizle(ad)
    motor.unut(ad)


def calisma_eki(durum):
    """Calismanin kisa adi (Spark cikti adlari icin): "V8"."""
    from fe_agent.akis_faz01 import amp_klasor_adi
    ek = re.sub(r"[^A-Za-z0-9]+", "_", str(amp_klasor_adi(durum)).split("/")[-1])
    return ek.strip("_").upper() or "CALISMA"


def amp_dosya_yolu(durum):
    """Pandas yolunda AMP_VERISETI'nin calisma klasorundeki yeri."""
    from fe_agent.akis_faz01 import amp_klasor_adi
    return "/%s/%s.parquet" % (amp_klasor_adi(durum), AMP_VERI_ADI)


def _klasore_yaz(yol, tablo):
    try:
        yol = tablo_io.klasore_yaz(_folder(), yol, tablo)
    except Exception as e:
        raise AdimHatasi("AMP_VERISETI çalışma klasörüne yazılamadı (%s)." % str(e)[:200])
    onbellek_temizle(yol)
    return yol


def amp_yaz(durum, prof):
    """AMP_VERISETI'ni KAYNAK TABLODAN yazar (Degisken Kontrolu onayi).
    Doner: {satir, kolon, dusen, motor, dataset | dosya}. Hata -> AdimHatasi."""
    kolonlar = profil_mod.kolonlar(prof)
    veri = durum.get("veri_seti")
    istek = {
        "donusum": _donusum_istegi(durum, kolonlar),
        "dusen": dusen_kolonlar(durum, list(kolonlar)),
        "hedef": (durum.get("meta") or {}).get("target"),
        "bolme": None,
        # Kullanicinin onayladigi kolon adlari (01.2.4 Kolon Adi Onerileri);
        # rol ve surec disi kolonlar haric. Girdi tabloya dokunulmaz.
        "yeniden_ad": yeniden_ad_esleme(durum, list(kolonlar)),
    }
    if motor.sec([veri])[0] == motor.PANDAS:
        from fe_agent import amp_pandas
        tablo, sonuc = amp_pandas.amp_hazirla(_df_oku(veri), istek)
        if sonuc.get("hata"):
            raise AdimHatasi(sonuc["hata"])
        sonuc.update(motor=motor.PANDAS, dataset=None,
                     dosya=_klasore_yaz(amp_dosya_yolu(durum), tablo))
        return sonuc
    ek = calisma_eki(durum)
    sonuc = _sonuc_ile_calistir("amp", [veri], istek, durum.get("_oturum_id") or "",
                                ad_eki=ek)
    ad = "%s_%s" % (AMP_VERI_ADI, ek)
    motor.unut(ad)
    sonuc.update(motor=motor.SPARK, dataset=ad, dosya=None, taban=ad)
    return sonuc


def amp_bolme_yaz(durum, bolme):
    """_SPLIT kolonunu AMP_VERISETI'NIN KENDISINE ekler; kaynak tabloya
    geri donulmez. Pandas: calisma klasorundeki dosya okunur, eski _SPLIT
    atilir, yenisi eklenip ayni dosyaya yazilir. Spark: bir veri seti ayni
    recipe'in hem girdisi hem ciktisi olamaz; teyitte yazilan AMP veri seti
    girdi, bolunmus hali ayri cikti (AMP_VERISETI_V8_B) olur ve bundan sonra
    AMP_VERISETI odur. Doner: amp_yaz ile ayni bicim + setler."""
    kayit = (durum.get("amp_cikti") or {}).get("veri") or {}
    if not (kayit.get("dosya") or kayit.get("dataset")):
        raise AdimHatasi("AMP_VERISETI henüz oluşturulmadı; önce «Değişken "
                         "Kontrolü» adımını kaydedin.")
    istek = {"donusum": {}, "dusen": [],
             "hedef": (durum.get("meta") or {}).get("target"), "bolme": bolme,
             # Segment kolonu: set x segment sayimi (01.4 segment tablosu)
             "segment": (durum.get("meta") or {}).get("segment")}
    from fe_agent import amp_pandas
    if kayit.get("dosya"):
        df = tablo_io.klasorden_oku(_folder(), kayit["dosya"])
        df = df.drop(columns=[amp_pandas.SPLIT_KOLON], errors="ignore")
        tablo, sonuc = amp_pandas.amp_hazirla(df, istek)
        if sonuc.get("hata"):
            raise AdimHatasi(sonuc["hata"])
        sonuc.update(motor=motor.PANDAS, dataset=None,
                     dosya=_klasore_yaz(kayit["dosya"], tablo))
        return sonuc
    taban = kayit.get("taban") or kayit["dataset"]
    ek = calisma_eki(durum) + "_B"
    sonuc = _sonuc_ile_calistir("amp", [taban], istek, durum.get("_oturum_id") or "",
                                ad_eki=ek)
    ad = "%s_%s" % (AMP_VERI_ADI, ek)
    motor.unut(ad)
    sonuc.update(motor=motor.SPARK, dataset=ad, dosya=None, taban=taban)
    return sonuc


def baz_yaz(durum, tablolar):
    """Ayni kolonlu kaynak tablolari alt alta MODELLEME_BAZ'a yazar.
    Doner: {tablolar: {ad: {satir, kolon}}, satir, kolon, motor}. Motor
    tablolarin TOPLAM boyutuna gore secilir."""
    tablolar = list(tablolar)
    if motor.sec(tablolar)[0] == motor.PANDAS:
        from fe_agent import amp_pandas
        tablo, sonuc = amp_pandas.alt_alta(
            tablolar, lambda ad: _df_oku(ad, onbellek=False))
        if sonuc.get("hata"):
            raise AdimHatasi(sonuc["hata"])
        _pandas_yaz(BAZ_VERI_ADI, tablo, tablolar[0])
        sonuc["motor"] = motor.PANDAS
        return sonuc
    sonuc = _sonuc_ile_calistir("baz", tablolar, {}, durum.get("_oturum_id") or "")
    motor.unut(BAZ_VERI_ADI)
    sonuc["motor"] = motor.SPARK
    return sonuc
