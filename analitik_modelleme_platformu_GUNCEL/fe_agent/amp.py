# -*- coding: utf-8 -*-
"""fe_agent/amp.py - AMP_VERISETI'ni ve alt alta eklenen baz veri setini
yazdirma (webapp tarafi).

MOTOR VERININ BOYUTUNA GORE (bkz. motor.py): kucuk veri webapp icinde
pandas ile (amp_pandas), buyuk veri Dataiku'daki PySpark recipe'leriyle
(amp_spark; recipe'leri ve ciktilarini webapp kurar, spark_is.ISLER).
Iki yolun sonuc sozlugu ayni bicimde; cagiran taraf motoru bilmez.

  amp_ham_yaz   : VERI SETI SECILDIGI AN kullanicinin tablosunun birebir
                  kopyasi (AMP_VERISETI_HAM). Bundan sonra kullanicinin
                  tablosu HIC okunmaz; teyide kadar her okuma bu kopyadan.
  amp_yaz       : Degisken Kontrolu onayinda tip donusumleri + surec disi
                  kolonlar + yeni adlar (AMP_VERISETI_HAM'DAN, bir kez).
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

from fe_agent import akis_atif
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
# Secim anindaki birebir kopya: pandas yolunda /<calisma>/AMP_VERISETI_HAM
# .parquet, Spark yolunda AMP_VERISETI_<V8>_HAM veri seti.
AMP_HAM_EKI = "HAM"


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


def _sonuc_ile_calistir(is_adi, girdiler, istek, sahip, ad_eki=None, cikti_adi=None):
    """Isi calistirir ve sonuc.json'u doner. Is basarisiz bittiyse ama
    recipe kendi hatasini (ornegin cevrilemeyen hucre) sonuca yazdiysa o
    daha anlasilir oldugu icin o gosterilir."""
    import uuid
    kosu_id = uuid.uuid4().hex
    try:
        spark_is.calistir(is_adi, girdiler, istek, sahip, kosu_id=kosu_id,
                          ad_eki=ad_eki, cikti_adi=cikti_adi)
    except AdimHatasi:
        try:
            sonuc = spark_is.sonuc_oku(is_adi, SONUC_DOSYA, kosu_id, ad_eki, cikti_adi)
        except AdimHatasi:
            sonuc = None
        if isinstance(sonuc, dict) and sonuc.get("hata"):
            raise AdimHatasi(sonuc["hata"])
        raise
    sonuc = spark_is.sonuc_oku(is_adi, SONUC_DOSYA, kosu_id, ad_eki, cikti_adi)
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


# ===========================================================================
# DORT TABLO: BAZ VERI, BAZ SOZLUK, UPDT VERI, UPDT SOZLUK
# ---------------------------------------------------------------------------
# Bir calisma Flow'da yalniz dort veri seti yazar, hepsi calismaya ozel
# (onek calisma eki, ornek "V8"):
#   <EK>_BAZ_VERI    : secilen tablonun (Mod B/D'de birlestirmenin) birebir
#                      kopyasi; secimden sonra hic degismez.
#   <EK>_BAZ_SOZLUK  : secilen (birlesik / kaynak / uretilen) sozlugun
#                      birebir kopyasi; hic degismez.
#   <EK>_UPDT_VERI   : verinin her zaman en son hali (01.3'ten itibaren her
#                      adim gunceller).
#   <EK>_UPDT_SOZLUK : sozlugun her zaman en son hali (calisma kopyasi /
#                      AMP_SOZLUK'ün Flow'daki yayini; her adim sonunda).
# Eski calismalar (AMP_VERISETI, AMP_VERISETI_HAM ...) eski adlariyla
# okunmaya devam eder; yeni adlar yalniz yeni yazimlarda kullanilir.
# ===========================================================================
def baz_veri_adi(durum):
    return "%s_BAZ_VERI" % calisma_eki(durum)


def baz_sozluk_adi(durum):
    return "%s_BAZ_SOZLUK" % calisma_eki(durum)


def updt_veri_adi(durum):
    return "%s_UPDT_VERI" % calisma_eki(durum)


def updt_sozluk_adi(durum):
    return "%s_UPDT_SOZLUK" % calisma_eki(durum)


def sozluk_veri_setine_yaz(durum, ad, tablo):
    """Sozluk tablosunu Flow'daki veri setine yazar (yoksa secili veri
    setinin baglantisinda kurulur). Doner: hata metni ya da None."""
    kaynak = durum.get("veri_seti") or (durum.get("amp_ham") or {}).get("kaynak")
    try:
        if kaynak:
            spark_is.veri_seti_hazirla(ad, kaynak)
        if not dataset_yaz(ad, _sozluk_yazilabilir(tablo)):
            return "%s veri setine yazılamadı." % ad
    except Exception as e:      # pylint: disable=broad-except
        return "%s veri seti kurulamadı (%s)." % (ad, str(e)[:160])
    onbellek_temizle(ad)
    return None


def _sozluk_yazilabilir(tablo):
    """Karisik tipli (ornek liste, sozluk) hucreler veri setine metin
    olarak gider."""
    t = tablo.copy()
    for k in t.columns:
        if t[k].dtype == object:
            t[k] = t[k].map(lambda v: v if v is None or isinstance(v, (str, int, float, bool))
                            else str(v))
    return t


def baz_sozluk_yaz(durum, tablo):
    """BAZ sozluk: secilen sozlugun birebir kopyasi (bir kez, secimde).
    Doner: hata metni ya da None."""
    hata = sozluk_veri_setine_yaz(durum, baz_sozluk_adi(durum), tablo)
    if not hata:
        durum["baz_sozluk"] = baz_sozluk_adi(durum)
    return hata


UPDT_DUSMUS_ASAMALAR = ("02.1", "02.2", "02.3", "03.3")
# 01.4 bolmesinden sonra UPDT veride _SPLIT kolonu var.
UPDT_BOLMELI_ASAMALAR = ("01",) + UPDT_DUSMUS_ASAMALAR


def updt_split_var(durum):
    """UPDT veride _SPLIT kolonu var mi (01.4 bolmesi yazildi)."""
    kayit = (durum.get("amp_cikti") or {}).get("veri") or {}
    return durum.get("updt_asama") in UPDT_BOLMELI_ASAMALAR and bool(kayit.get("bolme_tarif"))


def updt_dusen_kolonlar(durum):
    """02.1 onayindan sonra UPDT veriden cikan kolonlar (bkz.
    akis_faz02.girmez_dusur); 02.1 onaylanmadiysa bos kume."""
    if durum.get("updt_asama") not in UPDT_DUSMUS_ASAMALAR:
        return set()
    try:
        from fe_agent import akis_faz02
        return set(akis_faz02.kusurlu_kolonlar(durum)) - akis_faz02._meta_kolonlar(durum)
    except Exception:           # pylint: disable=broad-except
        return set()


def updt_sozluk_ek(durum):
    """02.1'de uretilen yeni kolonlarin sozluk satirlari (bkz.
    akis_faz02.yeni_kolon_sozlugu); 02.1 onaylanmadiysa []."""
    if durum.get("updt_asama") not in UPDT_DUSMUS_ASAMALAR:
        return []
    ek = (durum.get("profil") or {}).get("sozluk_ek")
    ek = [x for x in ek if isinstance(x, dict) and x.get("DEGISKEN")] if isinstance(ek, list) else []
    # EKSIK SATIR TAMAMLANIR: 02.1'de uretilen her kolonun (cozum ve
    # duzeltme bayraklari) satiri olmali. Onayda kaydedilmemis (eski oturum)
    # ya da eksik kalmis satir kolonun bilgisinden kurulur.
    try:
        from fe_agent import akis_faz02
        var = {str(x["DEGISKEN"]) for x in ek}
        ek += [x for x in akis_faz02.yeni_kolon_sozlugu(durum) if str(x["DEGISKEN"]) not in var]
    except Exception:           # pylint: disable=broad-except
        pass
    return ek


def updt_sozluk_suz(durum, tablo):
    """UPDT sozluk UPDT veriyle ayni kolonlari anlatir: 02.1'de cikan
    kolonlarin satirlari yazilmaz, 02.1'de uretilen yeni kolonlarin
    satirlari eklenir (calisma kopyasi degismez). Yeni satir sozlugun kendi
    kolonlarina yazilir: ad, aciklama, varsa TIP, NULL_ORANI, SUREC_DISI ve
    EK_BILGI (nereden uretildigi)."""
    from fe_agent import sozluk_calisma
    ad = sozluk_calisma.degisken_kolonu_bul(tablo)
    if ad is None:
        return tablo
    dus = updt_dusen_kolonlar(durum)
    if dus:
        tablo = tablo[~tablo[ad].astype(str).str.strip().isin(dus)].reset_index(drop=True)
    ek = list(updt_sozluk_ek(durum))
    # 01.4'un ekledigi bolme kolonu (_SPLIT) da sozlukte anlatilir.
    if updt_split_var(durum):
        from fe_agent import amp_pandas
        try:
            from fe_agent.akis_faz01 import SPLIT_ACIKLAMA
        except Exception:       # pylint: disable=broad-except
            SPLIT_ACIKLAMA = "Kaydın örneklem seti: train, val ya da test."
        ek.insert(0, {"DEGISKEN": amp_pandas.SPLIT_KOLON, "TIP": "kategorik",
                      "ACIKLAMA": SPLIT_ACIKLAMA, "NULL_ORANI": 0.0, "KAYNAK_KOLON": "",
                      "_ek_bilgi": "01.4 Örneklem ve Doğrulama Tasarımı adımında eklendi."})
    if not ek:
        return tablo
    import pandas as pd
    var = set(tablo[ad].astype(str).str.strip())
    tanim = sozluk_calisma.tanim_kolonu_bul(tablo)
    buyuk = {str(c).strip().upper(): c for c in tablo.columns}
    try:
        from fe_agent.akis_faz01 import _DISI_METNI
        disi = _DISI_METNI[False]
    except Exception:           # pylint: disable=broad-except
        disi = None
    yeni = []
    # Sozlukte satiri olup aciklamasi bos olan uretilmis kolon: aciklama yazilir.
    if tanim is not None:
        tablo = tablo.copy()
        adlar = tablo[ad].astype(str).str.strip()
        for x in ek:
            m = (adlar == str(x["DEGISKEN"])) & tablo[tanim].isna() | (
                (adlar == str(x["DEGISKEN"])) & (tablo[tanim].astype(str).str.strip() == ""))
            if bool(m.any()):
                tablo.loc[m, tanim] = x.get("ACIKLAMA", "")
    for x in ek:
        if str(x["DEGISKEN"]) in var:
            continue
        r = {ad: x["DEGISKEN"]}
        if tanim is not None:
            r[tanim] = x.get("ACIKLAMA", "")
        if "TIP" in buyuk:
            r[buyuk["TIP"]] = x.get("TIP", "")
        if "NULL_ORANI" in buyuk:
            r[buyuk["NULL_ORANI"]] = x.get("NULL_ORANI")
        if "SUREC_DISI" in buyuk and disi is not None:
            r[buyuk["SUREC_DISI"]] = disi
        if "EK_BILGI" in buyuk:
            r[buyuk["EK_BILGI"]] = x.get("_ek_bilgi") or (
                "02.1 Veri Profili ve Kalite adımında %s kolonundan üretildi."
                % x.get("KAYNAK_KOLON", ""))
        yeni.append(r)
    if not yeni:
        return tablo
    return pd.concat([tablo, pd.DataFrame(yeni).reindex(columns=list(tablo.columns))],
                     ignore_index=True)


def updt_sozluk_yayinla(durum):
    """UPDT sozluk: sozlugun o anki hali (calisma kopyasi ya da AMP_SOZLUK)
    Flow'daki veri setine yazilir. Icerik degismediyse yazilmaz. Doner:
    hata metni ya da None."""
    from fe_agent import sozluk_calisma
    try:
        tablo = sozluk_calisma.calisma_df(durum)
    except Exception:           # pylint: disable=broad-except
        tablo = None
    if tablo is None or not len(tablo.columns):
        return None
    tablo = updt_sozluk_suz(durum, tablo)
    try:
        import pandas as pd
        imza = "%d:%d:%s" % (len(tablo), len(tablo.columns), int(
            pd.util.hash_pandas_object(tablo.astype(str), index=False).sum()))
    except Exception:           # pylint: disable=broad-except
        imza = None
    ad = updt_sozluk_adi(durum)
    if imza and durum.get("_updt_sozluk_imza") == [ad, imza]:
        return None
    hata = sozluk_veri_setine_yaz(durum, ad, tablo)
    if not hata:
        durum["updt_sozluk"] = ad
        durum["_updt_sozluk_imza"] = [ad, imza]
    return hata


def amp_dosya_yolu(durum):
    """Pandas yolunda AMP_VERISETI'nin calisma klasorundeki yeri."""
    from fe_agent.akis_faz01 import amp_klasor_adi
    return "/%s/%s.parquet" % (amp_klasor_adi(durum), AMP_VERI_ADI)


def _klasore_yaz(yol, tablo):
    try:
        yol = tablo_io.klasore_yaz(_folder(), yol, tablo)
    except Exception as e:
        raise AdimHatasi("Veri çalışma klasörüne yazılamadı (%s)." % str(e)[:200])
    onbellek_temizle(yol)
    return yol


def amp_ham_yolu(durum):
    """Pandas yolunda AMP_VERISETI_HAM'in calisma klasorundeki yeri."""
    from fe_agent.akis_faz01 import amp_klasor_adi
    return "/%s/%s_%s.parquet" % (amp_klasor_adi(durum), AMP_VERI_ADI, AMP_HAM_EKI)


def amp_ham_kaynagi(durum):
    """AMP_VERISETI_HAM'in okunacagi ad (Parquet yolu ya da veri seti);
    yoksa ya da secili veri seti o kopyadan sonra DEGISTIYSE None
    (secim yenilenirken bayat kopya okunmasin)."""
    ham = (durum or {}).get("amp_ham") or {}
    if not ham or ham.get("kaynak") != (durum or {}).get("veri_seti"):
        return None
    return ham.get("dosya") or ham.get("dataset") or None


def amp_ham_yaz(durum, df=None):
    """Secilen veri setinin BIREBIR kopyasini AMP_VERISETI_HAM'a yazar.

    NEDEN: veri seti ve sozluk secildikten sonra yalniz AMP_VERISETI ve
    AMP_SOZLUK kullanilir. Kullanicinin tablosu
    YALNIZ burada, bir kez okunur; profil, onizleme, dagilim, teyit ve
    AMP_VERISETI'nin kendisi bu kopyadan okunur. Donusum, dusurme, ad
    degisikligi YOK (onlar teyitte, amp_yaz).

    df: tablo zaten bellekteyse (Mod B birlestirme) yeniden okunmaz.
    Motor secili tablonun boyutuna gore (pandas: calisma klasorunde
    Parquet; Spark: AMP_VERISETI_<V8>_HAM veri seti).
    Doner ve durum["amp_ham"]'a yazar: {dosya | dataset, kaynak, motor,
    satir, kolon}."""
    veri = durum.get("veri_seti")
    if not veri:
        raise AdimHatasi("Veri seti seçilmeden BAZ veri oluşturulamaz.")
    baz = baz_veri_adi(durum)
    secilen, boyut = motor.sec([veri])
    if veri == baz:
        # Mod B/D: birlestirme sonucu dogrudan BAZ veriye yazildi; kopya yok.
        if df is None:
            df = _df_oku(baz, limit=1)
            satir = ((durum.get("birlestirme") or {}).get("ozet") or {}).get("satir")
        else:
            satir = int(len(df))
        kayit = {"dosya": None, "dataset": baz, "motor": secilen,
                 "satir": satir, "kolon": int(len(df.columns))}
    elif secilen == motor.PANDAS:
        if df is None:
            df = _df_oku(veri, onbellek=False)
        _pandas_yaz(baz, df, veri)
        kayit = {"dosya": None, "dataset": baz, "motor": motor.PANDAS,
                 "satir": int(len(df)), "kolon": int(len(df.columns))}
    else:
        istek = {"donusum": {}, "dusen": [], "hedef": None, "bolme": None,
                 "yeniden_ad": {}}
        sonuc = _sonuc_ile_calistir("amp", [veri], istek, durum.get("_oturum_id") or "",
                                    cikti_adi=baz)
        motor.unut(baz)
        kayit = {"dosya": None, "dataset": baz, "motor": motor.SPARK,
                 "satir": int(sonuc.get("satir") or 0),
                 "kolon": int(sonuc.get("kolon") or 0)}
    # Motor ve boyut SECILEN tablonunki (kopyanin yolu boyut olcmez).
    kayit.update(kaynak=veri, dosya_boyutu=boyut)
    durum["amp_ham"] = kayit
    onbellek_temizle()
    return kayit


def amp_yaz(durum, prof):
    """AMP_VERISETI'ni AMP_VERISETI_HAM'DAN yazar (Degisken Kontrolu onayi).
    Eski calismada (HAM kopyasi yok) kaynak tablodan.
    Doner: {satir, kolon, dusen, motor, dataset | dosya}. Hata -> AdimHatasi."""
    kolonlar = profil_mod.kolonlar(prof)
    veri = amp_ham_kaynagi(durum) or durum.get("veri_seti")
    istek = {
        "donusum": _donusum_istegi(durum, kolonlar),
        "dusen": dusen_kolonlar(durum, list(kolonlar)),
        "hedef": (durum.get("meta") or {}).get("target"),
        "bolme": None,
        # Kullanicinin onayladigi kolon adlari (01.2.4.4 Yeni Kolon Adlari);
        # rol ve surec disi kolonlar haric. Girdi tabloya dokunulmaz.
        "yeniden_ad": yeniden_ad_esleme(durum, list(kolonlar)),
    }
    updt = updt_veri_adi(durum)
    if motor.sec([veri])[0] == motor.PANDAS:
        from fe_agent import amp_pandas
        tablo, sonuc = amp_pandas.amp_hazirla(_df_oku(veri), istek)
        if sonuc.get("hata"):
            raise AdimHatasi(sonuc["hata"])
        _pandas_yaz(updt, tablo, veri)
        sonuc.update(motor=motor.PANDAS, dataset=updt, dosya=None, istek=istek, kaynak=veri)
        return sonuc
    sonuc = _sonuc_ile_calistir("amp", [veri], istek, durum.get("_oturum_id") or "",
                                cikti_adi=updt)
    motor.unut(updt)
    sonuc.update(motor=motor.SPARK, dataset=updt, dosya=None, taban=updt,
                 istek=istek, kaynak=veri)
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
        raise AdimHatasi("UPDT veri henüz oluşturulmadı; önce %s adımını "
                         "kaydedin." % akis_atif.adim("teyit", durum))
    istek = {"donusum": {}, "dusen": [],
             "hedef": (durum.get("meta") or {}).get("target"), "bolme": bolme,
             # Segment kolonu: set x segment sayimi (01.4 segment tablosu)
             "segment": (durum.get("meta") or {}).get("segment")}
    from fe_agent import amp_pandas
    if kayit.get("dataset") and kayit.get("istek") is not None \
            and kayit["dataset"] == updt_veri_adi(durum):
        # UPDT VERI: ayni veri setine yazilir. Pandas: UPDT okunur, eski
        # _SPLIT atilir, yenisi eklenir. Spark: bir veri seti ayni recipe'in
        # hem girdisi hem ciktisi olamaz; UPDT BAZ veriden teyit istegi +
        # bolme ile yeniden kurulur (sonuc ayni: teyit + _SPLIT).
        updt = kayit["dataset"]
        tam = dict(kayit["istek"], bolme=bolme,
                   segment=(durum.get("meta") or {}).get("segment"))
        if kayit.get("motor") == motor.PANDAS:
            # UPDT sonraki adimlarla ilerlemis olabilir (geri donus): bolme
            # her zaman BAZ veriden teyit istegiyle kurulur.
            tablo, sonuc = amp_pandas.amp_hazirla(
                _df_oku(kayit.get("kaynak"), onbellek=False), tam)
            if sonuc.get("hata"):
                raise AdimHatasi(sonuc["hata"])
            _pandas_yaz(updt, tablo, kayit.get("kaynak") or updt)
            sonuc.update(motor=motor.PANDAS, dataset=updt, dosya=None,
                         istek=kayit["istek"], kaynak=kayit.get("kaynak"),
                         bolme_tarif=bolme)
            return sonuc
        sonuc = _sonuc_ile_calistir("amp", [kayit.get("kaynak")], tam,
                                    durum.get("_oturum_id") or "", cikti_adi=updt)
        motor.unut(updt)
        sonuc.update(motor=motor.SPARK, dataset=updt, dosya=None, taban=updt,
                     istek=kayit["istek"], kaynak=kayit.get("kaynak"), bolme_tarif=bolme)
        return sonuc
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
    """Ayni kolonlu kaynak tablolari alt alta BAZ veriye (<EK>_BAZ_VERI) yazar.
    Doner: {tablolar: {ad: {satir, kolon}}, satir, kolon, motor}. Motor
    tablolarin TOPLAM boyutuna gore secilir."""
    tablolar = list(tablolar)
    baz = baz_veri_adi(durum)
    if motor.sec(tablolar)[0] == motor.PANDAS:
        from fe_agent import amp_pandas
        tablo, sonuc = amp_pandas.alt_alta(
            tablolar, lambda ad: _df_oku(ad, onbellek=False))
        if sonuc.get("hata"):
            raise AdimHatasi(sonuc["hata"])
        _pandas_yaz(baz, tablo, tablolar[0])
        sonuc.update(motor=motor.PANDAS, dataset=baz)
        return sonuc
    sonuc = _sonuc_ile_calistir("baz", tablolar, {}, durum.get("_oturum_id") or "",
                                cikti_adi=baz)
    motor.unut(baz)
    sonuc.update(motor=motor.SPARK, dataset=baz)
    return sonuc
