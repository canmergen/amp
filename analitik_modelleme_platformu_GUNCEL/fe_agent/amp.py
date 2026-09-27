# -*- coding: utf-8 -*-
"""fe_agent/amp.py - AMP_VERISETI'ni ve alt alta eklenen baz veri setini
Spark ile yazdirma (webapp tarafi).

Veri buyuk (135 milyon satir); webapp tabloyu okumaz. Isleri Dataiku'daki
PySpark recipe'leri yapar (amp_spark), recipe'leri ve ciktilarini webapp
kurar (spark_is.ISLER).

  amp_yaz   : Degisken Kontrolu onayinda tip donusumleri + surec disi
              kolonlar; Orneklem ve Dogrulama'da ayni tablo + _SPLIT.
  baz_yaz   : Mod B/D'de ayni kolonlu kaynak tablolar alt alta ->
              MODELLEME_BAZ.
"""

from fe_agent import profil as profil_mod
from fe_agent import profil_kural
from fe_agent import spark_is
from fe_agent import tip_donusum
from fe_agent.akis_durum import AdimHatasi

SONUC_DOSYA = "/sonuc.json"
DISARIDA = "disarida"      # hicbir sete girmeyen satir (amp_spark ile ayni)
BAZ_VERI_ADI = "MODELLEME_BAZ"


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


def amp_yaz(durum, prof, bolme=None):
    """AMP_VERISETI'ni Spark recipe'iyle yazar. Doner: recipe'in sonucu
    ({satir, kolon, dusen, setler?}). Hata -> AdimHatasi."""
    kolonlar = profil_mod.kolonlar(prof)
    istek = {
        "donusum": _donusum_istegi(durum, kolonlar),
        "dusen": dusen_kolonlar(durum, list(kolonlar)),
        "hedef": (durum.get("meta") or {}).get("target"),
        "bolme": bolme,
    }
    return _sonuc_ile_calistir("amp", [durum.get("veri_seti")], istek,
                               durum.get("_oturum_id") or "")


def baz_yaz(durum, tablolar):
    """Ayni kolonlu kaynak tablolari alt alta MODELLEME_BAZ'a yazar.
    Doner: {tablolar: {ad: {satir, kolon}}, satir, kolon}."""
    return _sonuc_ile_calistir("baz", list(tablolar), {},
                               durum.get("_oturum_id") or "")
