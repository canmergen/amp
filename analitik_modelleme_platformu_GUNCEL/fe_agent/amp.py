# -*- coding: utf-8 -*-
"""fe_agent/amp.py - AMP_VERISETI'ni ve alt alta eklenen baz veri setini
yazdirma (webapp tarafi).

MOTOR VERININ BOYUTUNA GORE (bkz. motor.py): kucuk veri webapp icinde
pandas ile (amp_pandas), buyuk veri Dataiku'daki PySpark recipe'leriyle
(amp_spark; recipe'leri ve ciktilarini webapp kurar, spark_is.ISLER).
Iki yolun sonuc sozlugu ayni bicimde; cagiran taraf motoru bilmez.

  amp_yaz   : Degisken Kontrolu onayinda tip donusumleri + surec disi
              kolonlar; Orneklem ve Dogrulama'da ayni tablo + _SPLIT.
  baz_yaz   : Mod B/D'de ayni kolonlu kaynak tablolar alt alta ->
              MODELLEME_BAZ.
"""

from fe_agent import motor
from fe_agent import profil as profil_mod
from fe_agent import profil_kural
from fe_agent import spark_is
from fe_agent import tip_donusum
from fe_agent.akis_durum import AdimHatasi, _df_oku, dataset_yaz, onbellek_temizle

SONUC_DOSYA = "/sonuc.json"
DISARIDA = "disarida"      # hicbir sete girmeyen satir (amp_spark ile ayni)
BAZ_VERI_ADI = "MODELLEME_BAZ"
AMP_VERI_ADI = "AMP_VERISETI"


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


def _sonuc_ile_calistir(is_adi, girdiler, istek, sahip):
    """Isi calistirir ve sonuc.json'u doner. Is basarisiz bittiyse ama
    recipe kendi hatasini (ornegin cevrilemeyen hucre) sonuca yazdiysa o
    daha anlasilir oldugu icin o gosterilir."""
    import uuid
    kosu_id = uuid.uuid4().hex
    try:
        spark_is.calistir(is_adi, girdiler, istek, sahip, kosu_id=kosu_id)
    except AdimHatasi:
        try:
            sonuc = spark_is.sonuc_oku(is_adi, SONUC_DOSYA, kosu_id)
        except AdimHatasi:
            sonuc = None
        if isinstance(sonuc, dict) and sonuc.get("hata"):
            raise AdimHatasi(sonuc["hata"])
        raise
    sonuc = spark_is.sonuc_oku(is_adi, SONUC_DOSYA, kosu_id)
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


def amp_yaz(durum, prof, bolme=None):
    """AMP_VERISETI'ni yazar. Doner: {satir, kolon, dusen, setler?, motor}.
    Hata -> AdimHatasi."""
    kolonlar = profil_mod.kolonlar(prof)
    veri = durum.get("veri_seti")
    istek = {
        "donusum": _donusum_istegi(durum, kolonlar),
        "dusen": dusen_kolonlar(durum, list(kolonlar)),
        "hedef": (durum.get("meta") or {}).get("target"),
        "bolme": bolme,
    }
    if motor.sec([veri])[0] == motor.PANDAS:
        from fe_agent import amp_pandas
        tablo, sonuc = amp_pandas.amp_hazirla(_df_oku(veri), istek)
        if sonuc.get("hata"):
            raise AdimHatasi(sonuc["hata"])
        _pandas_yaz(AMP_VERI_ADI, tablo, veri)
        sonuc["motor"] = motor.PANDAS
        return sonuc
    sonuc = _sonuc_ile_calistir("amp", [veri], istek, durum.get("_oturum_id") or "")
    motor.unut(AMP_VERI_ADI)
    sonuc["motor"] = motor.SPARK
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
