# -*- coding: utf-8 -*-
"""fe_agent/profil_kural.py - VERI SETI PROFILININ KURALLARI (motordan bagimsiz).

NEDEN VAR
  Veri setleri tek makinenin bellegine sigmayacak kadar buyuk; tam tabloyu
  webapp'te pandas'a okumak mumkun degil (kullanici karari: "python ile
  çalıştırmamam lazım, pyspark kullanmak zorundayız"). Bu yuzden 1. fazin
  tam veriye bakan butun kontrolleri (tek deger, hedef/kimlik/donem
  adaylari, tip donusumu uygunlugu, kisisel veri deseni, null orani,
  tekrarlanan satir) TEK bir PySpark isinde, bir kez hesaplanip profil
  dosyasina yaziliyor. Webapp yalnizca bu dosyayi okur.

KESIN SAYIM, ORNEKLEM YOK (kullanici karari: "hepsi kesin olmalı, sayımda
1-2 fark bile kabul değil")
  Her kolonun TEKIL DEGERLERI ve her degerin SATIR SAYISI tam tablodan
  cikarilir (Spark'ta groupBy; yaklasik sayim kullanilmaz). Buradaki
  kurallarin hepsi "deger basina" denetimdir: bir kolonda "kac satir
  cevrilemiyor" sorusu, her tekil degerin cevrilip cevrilmedigine ve o
  degerin kac satirda gectigine bakilarak BIREBIR cevaplanir. Kolonun
  tamamina bakan kararlar ("hepsi tam sayi mi", "hepsi YYYYAA mi") bu
  deger basina sayimlarin toplamindan verilir.

IKI MOTOR, TEK KURAL
  - profil_spark.py : Dataiku PySpark recipe'i (asil yol).
  - yerel_profil()  : ayni kurallar pandas uzerinde; yalnizca test ve
    kucuk veri icin. Iki motor ayni tabloda AYNI profili uretmeli; testler
    bunu denetliyor.
  Iki motorun ortak parcalari:
    gorev_plani()       -> birinci geciste cikan sayilara gore hangi deger
                           basina denetimin gerektigi
    parca_degerlendir() -> bir kolonun tekil degerlerinden bir PARCA icin
                           deger basina denetim (Spark'ta her bolumde calisir)
    parca_birlestir()   -> parca sonuclarinin toplanmasi
    profil_kur()        -> toplanmis sonuclardan kolon kararlari
"""

import math
import re

import numpy as np
import pandas as pd

from fe_agent import birlestirme as birl
from fe_agent import sozluk as sozluk_mod
from fe_agent import tip_donusum

PROFIL_SURUMU = 1

# Kolon turleri (Spark semasindan). Kaynak tip, pandas'taki eski ayrimla
# ayni: sayisal (bool dahil, pandas is_numeric_dtype gibi), tarih, kategorik.
TUR_TAM, TUR_ONDALIK, TUR_MANTIKSAL, TUR_METIN, TUR_TARIH = (
    "tam", "ondalik", "mantiksal", "metin", "tarih")
SAYISAL_TURLER = (TUR_TAM, TUR_ONDALIK, TUR_MANTIKSAL)
KAYNAK_TIP = {TUR_TAM: "sayısal", TUR_ONDALIK: "sayısal",
              TUR_MANTIKSAL: "sayısal", TUR_TARIH: "tarih",
              TUR_METIN: "kategorik"}

# Donem adayi olmak icin dolu hucrelerin en az bu kadari donem olarak
# cozulmeli (akis_faz01 de buradan okur).
DONEM_COZULME_ORANI = 0.95

# Tekil deger sayisi bu sinirin altindaysa degerlerin TAMAMI sayilariyla
# profile yazilir (hedef 0/1 denetimi, tek deger metni, kategorik kolonun
# seviyeleri). tip_donusum.KATEGORI_SEVIYE_SINIRI ile ayni sinir.
DEGER_LISTE_SINIRI = tip_donusum.KATEGORI_SEVIYE_SINIRI
# En sik gorulen deger listesi (sozluk uretimi, dil modeli ozeti
# akis_faz01.EN_SIK_ETIKET ile ayni).
UST_DEGER_ADEDI = 10
# Donem adayinin normallestirilmis deger listesi profile en fazla bu kadar
# deger icin yazilir (modelleme tanimlari donem araligini ve bolme test
# donemlerini bu listeden okuyor). Ustu dönem kolonu olamayacak kadar
# cok tekil deger demek (gunluk tarih bile 100 yilda ~36.500 deger).
DONEM_DEGER_SINIRI = 100000
# Donem nedeni metnindeki ornek deger adedi.
ORNEK_UC = 3
# pandas quantile ile ayni noktalar (sozluk.profil_cikar).
KANTIL_NOKTALARI = (0.0, 0.25, 0.5, 0.75, 1.0)

# Sayisal kolonda kisisel veri deseni ancak 10-19 haneli TAM SAYIDA
# olabilir (sozluk._pii_deger_mi'deki on eleme).
PII_SAYI_ALT, PII_SAYI_UST = 1e9, 1e19

# Sayisal kolonda donem bicimleri (birlestirme._donem_coz ile ayni).
YM_ALT, YM_UST = 190001, 299912
YMD_ALT, YMD_UST = 19000101, 29991231


# ===========================================================================
# YARDIMCILAR
# ===========================================================================
def _sayi(n):
    return "{:,}".format(int(n)).replace(",", ".")


def json_deger(v):
    """Profil dosyasina yazilabilir deger (numpy/zaman tipleri sade)."""
    if v is None:
        return None
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return str(f)
        return f
    if hasattr(v, "isoformat"):
        try:
            return v.isoformat(sep=" ")
        except TypeError:
            return v.isoformat()
    return str(v)


def seri_kur(tur, degerler):
    """Bir parcanin tekil degerleri -> kolonun kaynak tipinde pandas serisi.

    Deger basina denetim (tip_donusum.cevir, donem cozucu) pandas'taki
    eski yol ile ayni tipte seri gormeli: tam sayi int64, ondalik float64,
    mantiksal bool, tarih datetime64, metin object."""
    if tur == TUR_TAM:
        return pd.Series(np.asarray(degerler, dtype="int64"))
    if tur == TUR_ONDALIK:
        return pd.Series(np.asarray(degerler, dtype="float64"))
    if tur == TUR_MANTIKSAL:
        return pd.Series(np.asarray(degerler, dtype=bool))
    if tur == TUR_TARIH:
        return pd.Series(pd.to_datetime(pd.Series(list(degerler), dtype=object),
                                        errors="coerce"))
    return pd.Series(list(degerler), dtype=object)


def _metinler(seri):
    """pandas astype(str) karsiligi (kirpilmamis)."""
    return seri.astype(str)


def _en_kucuk(liste, adet):
    return sorted(set(liste))[:adet]


def _tarih_coz(seri):
    """Metin -> tarih, HER DEGER KENDI BASINA cozulur.

    pandas 2'de bicimsiz to_datetime ilk degerin bicimini tahmin edip
    butun seriye uyguluyor; sonuc satir sirasina bagli kaliyordu. Profil
    parca parca calistigi icin sira sabit degil; deger basina cozum hem
    sirasiz hem de kesin (ayni deger her yerde ayni sonucu verir)."""
    if int(pd.__version__.split(".")[0]) >= 2:
        return pd.to_datetime(seri, errors="coerce", format="mixed")
    return pd.to_datetime(seri, errors="coerce")


# ===========================================================================
# 1) GOREV PLANI - birinci gecisin sayilarindan
# ===========================================================================
def hizli_red(ozet, kod):
    """tip_donusum._hizli_red ile ayni karar; tum kolonun min/maks ve
    "hepsi tam sayi mi" bilgisinden. Sebep ya da None."""
    aralik = tip_donusum._SAYISAL_ARALIK.get(kod)
    if not aralik or ozet["tur"] not in SAYISAL_TURLER:
        return None
    if not ozet["dolu"]:
        return "kolonda dolu değer yok"
    alt, ust = aralik
    try:
        if float(ozet["min"]) < alt or float(ozet["max"]) > ust \
                or not ozet.get("hepsi_tam"):
            return "değerler bu biçimde değil"
    except Exception:
        return None
    return None


def tam_sayi_bayragi(ozet):
    """tip_donusum._metin'in "sonlu degerlerin hepsi tam sayi" karari."""
    if ozet["tur"] != TUR_ONDALIK:
        return None
    return bool(ozet.get("n_sonlu")) and not ozet.get("n_kesirli")


def gorev_plani(ozet, ad_pii):
    """Bir kolonda deger basina hangi denetimlerin gerektigi.

    ozet: birinci gecisin sayilari (tur, dolu, tekil, min, max, ...).
    ad_pii: kolon ADI kisisel veri mi (o zaman deger deseni hic
    denetlenmez; eski yol da once ada bakiyordu).
    Doner: {"donusum": [kod...], "pii": bool, "donem": bool, "metin": bool,
            "tam_sayi": bool|None}"""
    tur = ozet["tur"]
    kaynak = KAYNAK_TIP[tur]
    gorev = {"donusum": [], "pii": False, "donem": False, "metin": False,
             "tam_sayi": tam_sayi_bayragi(ozet)}
    if not ozet["dolu"]:
        return gorev
    for kod in tip_donusum.ADAYLAR.get(kaynak, []):
        if hizli_red(ozet, kod):
            continue
        if kod == "kategorik_metin":
            # Dolu her deger metne cevrilir; takilan olamaz. Tek engel
            # seviye sayisi, o da birinci geciste belli.
            continue
        gorev["donusum"].append(kod)
    # Mantiksal ve tarih kolonun metni ("True", "2024-01-31 00:00:00")
    # hicbir desene uyamaz; denetlemek sonucu degistirmez.
    if not ad_pii and tur not in (TUR_MANTIKSAL, TUR_TARIH):
        if tur in (TUR_TAM, TUR_ONDALIK):
            # KESIN ON ELEME: 10-19 haneli tam sayi orani esigin
            # altindaysa kolon PII olamaz (sozluk._pii_deger_mi).
            gorev["pii"] = (float(ozet.get("n_pii_aday") or 0)
                            / float(ozet["dolu"])) >= sozluk_mod.PII_DESEN_ORAN
        else:
            gorev["pii"] = True
    if tur == TUR_METIN:
        gorev["donem"] = True
        gorev["metin"] = True
    return gorev


# ===========================================================================
# 2) DEGER BASINA DENETIM - bir parca
# ===========================================================================
def _bos_parca():
    return {"donusum": {}, "pii": None, "donem": None, "uzunluk": None,
            "metin": None}


def parca_degerlendir(tur, degerler, adetler, gorev):
    """Bir kolonun tekil degerlerinden bir PARCA; deger basina denetim.

    degerler: bos olmayan tekil degerler (liste). adetler: her degerin
    satir sayisi. Doner: toplanabilir sonuc (bkz. parca_birlestir)."""
    sonuc = _bos_parca()
    if not len(degerler):
        return sonuc
    seri = seri_kur(tur, degerler)
    agirlik = np.asarray(adetler, dtype=float)
    metin = _metinler(seri)

    for kod in gorev.get("donusum") or []:
        kayit = {"takilan": 0.0, "ornek": [], "hata": None}
        try:
            yeni, _takilan, _ornekler = tip_donusum.cevir(
                seri, kod, tam_sayi=gorev.get("tam_sayi"))
            takilan = seri.notna() & yeni.reindex(seri.index).isna()
            kayit["takilan"] = float(agirlik[takilan.to_numpy()].sum())
            if takilan.any():
                kayit["ornek"] = _en_kucuk(
                    [str(v)[:24] for v in seri[takilan].tolist()],
                    tip_donusum.ORNEK_DEGER)
        except Exception as e:          # pylint: disable=broad-except
            kayit["hata"] = str(e)[:60]
        sonuc["donusum"][kod] = kayit

    if gorev.get("pii"):
        sonuc["pii"] = sozluk_mod.pii_sayim(metin.str.strip(), agirlik)

    if gorev.get("metin"):
        kirpik = metin.str.strip()
        sonuc["uzunluk"] = {"toplam": float((metin.str.len().to_numpy()
                                             * agirlik).sum()),
                            "n": float(agirlik.sum())}
        sonuc["metin"] = {
            "kod_gibi": float(agirlik[kirpik.str.match(r"^0\d").to_numpy()].sum()),
            "virgul": float(agirlik[kirpik.str.contains(",", regex=False)
                                    .to_numpy()].sum())}

    if gorev.get("donem"):
        sonuc["donem"] = donem_parcasi(seri, agirlik)
    return sonuc


def donem_parcasi(seri, agirlik):
    """METIN kolonda birlestirme._donem_coz'un deger basina karsiligi.

    _donem_coz kolonun tamamina "hepsi sayi mi / hepsi YYYYAA mi / hepsi
    yil-ay mi" diye bakiyor; her biri deger basina bir bayrak ve kac
    satirin tutmadigi. Karar donem_karari'nda bu sayilardan verilir."""
    d = birl.donem_serisi(seri)
    dolu = d.notna().to_numpy()
    w = agirlik
    sayisal = pd.to_numeric(d, errors="coerce").astype("float")
    sayi_ok = sayisal.notna().to_numpy()
    ym = (sayisal.between(YM_ALT, YM_UST)
          & (sayisal % 100).between(1, 12)).to_numpy()
    ymd = (sayisal.between(YMD_ALT, YMD_UST)
           & ((sayisal // 100) % 100).between(1, 12)
           & (sayisal % 100).between(1, 31)).to_numpy()
    yil_ay = yil_ay_bayragi(d).to_numpy()
    return {
        "dolu": float(w[dolu].sum()),
        "sayi_degil": float(w[dolu & ~sayi_ok].sum()),
        "ym_degil": float(w[dolu & sayi_ok & ~ym].sum()),
        "ymd_degil": float(w[dolu & sayi_ok & ~ymd].sum()),
        "yil_ay_degil": float(w[dolu & ~yil_ay].sum()),
        # tarih cozumu pahali; yalnizca gerekirse (bkz. tarih_parcasi)
        "tarih_ok": None,
    }


def yil_ay_bayragi(d):
    """birlestirme._yil_ay_coz'un deger basina hali: deger "2025M01",
    "2025/01", "01/2025" gibi bir yil-ay yazimi mi."""
    metin = d.astype(str).str.strip()
    ok = pd.Series(False, index=d.index)
    for kalip, yil_i, ay_i in ((birl._YIL_AY_KALIP, 1, 2),
                               (birl._AY_YIL_KALIP, 2, 1)):
        parca = metin.str.extract(kalip)
        yil = pd.to_numeric(parca[yil_i - 1], errors="coerce")
        a = pd.to_numeric(parca[ay_i - 1], errors="coerce")
        ok = ok | (yil.between(1900, 2999) & a.between(1, 12)).fillna(False)
    return ok & d.notna()


def tarih_parcasi(tur, degerler, adetler):
    """METIN kolonda tarih olarak cozulebilen satir sayisi (donemin son
    yolu). Pahali oldugu icin yalnizca onceki yollar tutmayan kolonlarda
    ikinci bir geciste calisir."""
    if not len(degerler):
        return 0.0
    seri = seri_kur(tur, degerler)
    d = birl.donem_serisi(seri)
    dolu = d.notna()
    tarih = _tarih_coz(d.where(dolu, None))
    # birlestirme._donem_coz ile ayni kapi: yalnizca tarihe BENZEYEN metin.
    ok = (dolu & tarih.notna() & birl.tarih_metni_mi(d)).to_numpy()
    return float(np.asarray(adetler, dtype=float)[ok].sum())


def _topla_sozluk(a, b):
    if a is None:
        return dict(b) if b is not None else None
    if b is None:
        return dict(a)
    c = dict(a)
    for k, v in b.items():
        if v is None:
            continue
        c[k] = (c.get(k) or 0.0) + v
    return c


def parca_birlestir(a, b):
    """Iki parca sonucunu toplar (sira onemsiz, sonuc kesin)."""
    c = _bos_parca()
    for kod in set(a["donusum"]) | set(b["donusum"]):
        x = a["donusum"].get(kod) or {"takilan": 0.0, "ornek": [], "hata": None}
        y = b["donusum"].get(kod) or {"takilan": 0.0, "ornek": [], "hata": None}
        c["donusum"][kod] = {
            "takilan": x["takilan"] + y["takilan"],
            "ornek": _en_kucuk(x["ornek"] + y["ornek"], tip_donusum.ORNEK_DEGER),
            "hata": x["hata"] or y["hata"]}
    c["pii"] = _topla_sozluk(a["pii"], b["pii"])
    c["donem"] = _topla_sozluk(a["donem"], b["donem"])
    c["uzunluk"] = _topla_sozluk(a["uzunluk"], b["uzunluk"])
    c["metin"] = _topla_sozluk(a["metin"], b["metin"])
    return c


# ===========================================================================
# 3) KARARLAR - toplanmis sayilardan
# ===========================================================================
def donusum_karari(ozet, kod, parca):
    """tip_donusum.denetle ile ayni sonuc: (uygun, sebep)."""
    hizli = hizli_red(ozet, kod)
    if hizli:
        return False, hizli
    if kod == "kategorik_metin" and \
            int(ozet["tekil"]) > tip_donusum.KATEGORI_SEVIYE_SINIRI:
        return False, ("%d farklı değer var; en fazla %d seviyeye kadar "
                       "kategorik yapılabilir"
                       % (int(ozet["tekil"]), tip_donusum.KATEGORI_SEVIYE_SINIRI))
    kayit = ((parca or {}).get("donusum") or {}).get(kod) \
        or {"takilan": 0.0, "ornek": [], "hata": None}
    if kayit.get("hata"):
        return False, "çevrilemedi (%s)" % kayit["hata"]
    takilan = int(round(kayit.get("takilan") or 0))
    if not takilan:
        if not ozet["dolu"]:
            return False, "kolonda dolu değer yok"
        return True, None
    ornek = kayit.get("ornek") or []
    return False, ("%s değer çevrilemedi (%s)"
                   % (_sayi(takilan), ", ".join(ornek) if ornek else "örnek yok"))


def donem_karari(ozet):
    """birlestirme._donem_coz'un bicim karari ve donem adayligi icin
    "dolu hucrelerin cozulen orani". Doner: (bicim | None, oran)."""
    tur = ozet["tur"]
    if not ozet["dolu"]:
        return None, 0.0
    if tur == TUR_TARIH:
        return "tarih", 1.0
    if tur == TUR_MANTIKSAL:
        return None, 0.0
    if tur in (TUR_TAM, TUR_ONDALIK):
        if not ozet.get("ym_degil"):
            return "YYYYMM", 1.0
        if not ozet.get("ymd_degil"):
            return "YYYYMMDD", 1.0
        return None, 0.0
    d = ozet.get("donem_parca") or {}
    dolu = float(d.get("dolu") or 0)
    if not dolu:
        return None, 0.0
    if not d.get("sayi_degil"):
        if not d.get("ym_degil"):
            return "YYYYMM", 1.0
        if not d.get("ymd_degil"):
            return "YYYYMMDD", 1.0
    if not d.get("yil_ay_degil"):
        return "YYYYMM", 1.0
    tarih_ok = float(d.get("tarih_ok") or 0)
    if tarih_ok > 0:
        return "tarih", tarih_ok / dolu
    return None, 0.0


def donem_adayi_mi(ozet, satir):
    """Donem adayi kurali (kullanici karari): en az iki deger, kimlik gibi
    her satirda farkli degil, taninan donem bicimi ve dolu hucrelerin en
    az %95'i donem olarak cozuluyor."""
    tekil_bos = int(ozet["tekil"]) + (1 if ozet["bos"] else 0)
    if tekil_bos <= 1 or (satir and tekil_bos == satir):
        return False
    bicim, oran = donem_karari(ozet)
    return bool(bicim) and bool(ozet["dolu"]) and oran >= DONEM_COZULME_ORANI


def donem_degerleri(tur, degerler):
    """Tekil ham degerler -> normallestirilmis donem metinleri (tekil,
    sirasiz). birlestirme.donem_serisi ile AYNI normallestirme; tam
    kolonun tekil degerleri uzerinde ayni sonucu verir."""
    if not len(degerler):
        return []
    seri = birl.donem_serisi(seri_kur(tur, degerler))
    return sorted({str(v) for v in seri.dropna().tolist()})


def tarih_gecisi_gerekli_mi(ozet):
    """Metin kolonda donemin son yoluna (tarih cozumu) ihtiyac var mi."""
    if ozet["tur"] != TUR_METIN or not ozet["dolu"]:
        return False
    d = ozet.get("donem_parca") or {}
    if not d.get("dolu"):
        return False
    if not d.get("sayi_degil") and (not d.get("ym_degil")
                                     or not d.get("ymd_degil")):
        return False
    return bool(d.get("yil_ay_degil"))


def _neden_tek_deger(ozet):
    """Tek degerli kolonun donem nedeni; deger metinde gorunur."""
    deger = None
    liste = ozet.get("degerler") or []
    if liste:
        try:
            deger = birl.donem_degeri(liste[0][0])
        except Exception:
            deger = None
    return ("tüm satırlarda aynı değer%s; veri tek dönemlik"
            % (" (%s)" % deger if deger else ""))


def profil_kur(veri_seti, satir, duplicate, ozetler, motor):
    """Kolon ozetleri (birinci gecis + toplanmis parca sonuclari) ->
    profil sozlugu. Webapp'in okudugu dosyanin icerigi budur."""
    kolonlar = []
    hedef_aday, kimlik_aday, donem_aday, donem_neden = [], [], [], {}
    ozet_ad = {oz["ad"]: oz for oz in ozetler}
    for oz in ozetler:
        ad, tur = oz["ad"], oz["tur"]
        kaynak = KAYNAK_TIP[tur]
        tekil_bos = int(oz["tekil"]) + (1 if oz["bos"] else 0)
        parca = oz.get("parca") or _bos_parca()

        donusum = {}
        for kod in tip_donusum.ADAYLAR.get(kaynak, []):
            uygun, sebep = donusum_karari(oz, kod, parca)
            donusum[kod] = {"uygun": bool(uygun), "sebep": sebep or ""}

        pii_ad = sozluk_mod._pii_ad_mi(ad)
        pii_deger = None if pii_ad else sozluk_mod.pii_karar(parca.get("pii"))

        # HEDEF: yalnizca 0/1; bos disi degerler tam olarak {0, 1}. Sabit
        # kolon (hepsi 0) hedef olamaz: modellenecek olay yok.
        # Mantiksal kolon da iki degeri birden tasimali: hepsi True olan
        # kolonda modellenecek olay yok (eski yol bool kolonda buna
        # bakmiyordu).
        if tur in SAYISAL_TURLER and tekil_bos <= 3 \
                and oz.get("degerler") is not None:
            if {float(v) for v, _n in oz["degerler"]} == {0.0, 1.0}:
                hedef_aday.append(ad)
        # KIMLIK: tam tekrarsiz (bos hucre de deger).
        if satir and tekil_bos == satir:
            kimlik_aday.append(ad)

        bicim, oran = donem_karari(oz)
        kolonlar.append({
            "ad": ad, "tur": tur, "kaynak_tip": kaynak,
            "dolu": int(oz["dolu"]), "bos": int(oz["bos"]),
            "null_oran": round(float(oz["bos"]) / satir, 4) if satir else None,
            "tekil": int(oz["tekil"]), "tekil_bos_dahil": tekil_bos,
            "tekrar": int(satir - tekil_bos),
            "min": json_deger(oz.get("min")), "max": json_deger(oz.get("max")),
            "hepsi_tam": bool(oz.get("hepsi_tam")),
            "ondalikli": bool(oz.get("n_kesirli")),
            "pozitif": oz.get("pozitif"),
            "ornek": json_deger(oz.get("ornek")),
            "ornek3": [str(v) for v in (oz.get("ornek3") or [])],
            "pii_ad": pii_ad, "pii_deger": pii_deger,
            "donusum": donusum,
            "donem_bicim": bicim, "donem_oran": round(float(oran), 6),
            "ort_uzunluk": (float(parca["uzunluk"]["toplam"])
                            / float(parca["uzunluk"]["n"])
                            if parca.get("uzunluk") and parca["uzunluk"].get("n")
                            else None),
            "kod_gibi": bool((parca.get("metin") or {}).get("kod_gibi")),
            "virgul_var": bool((parca.get("metin") or {}).get("virgul")),
            "degerler": ([[json_deger(v), int(n)] for v, n in oz["degerler"]]
                         if oz.get("degerler") is not None else None),
            "ust_degerler": [[json_deger(v), int(n)]
                             for v, n in (oz.get("ust_degerler") or [])],
            "kantiller": [json_deger(v) for v in (oz.get("kantiller") or [])]
                         or None,
            "donem_degerleri": oz.get("donem_degerleri"),
        })

    # DONEM ADAYLARI (donem_adayi_mi) ve secilemeyenlerin nedeni.
    kimlik_kume = set(kimlik_aday)
    for k in kolonlar:
        ad = k["ad"]
        n_tekil = k["tekil_bos_dahil"]
        if n_tekil <= 1 or ad in kimlik_kume or (satir > 1 and n_tekil == satir):
            if n_tekil <= 1:
                donem_neden[ad] = _neden_tek_deger(ozet_ad[ad])
            elif ad in kimlik_kume:
                donem_neden[ad] = "kimlik adayı"
            else:
                donem_neden[ad] = ("her satırda farklı değer; kimlik ya da "
                                   "zaman damgası gibi")
            continue
        if donem_adayi_mi(ozet_ad[ad], satir):
            donem_aday.append(ad)
        else:
            ornek = ", ".join(k["ornek3"])
            donem_neden[ad] = "değerler dönem biçiminde değil" + (
                " (örnek: %s)" % ornek if ornek else "")

    return {
        "surum": PROFIL_SURUMU, "motor": motor, "veri_seti": veri_seti,
        "satir": int(satir), "kolon": len(kolonlar),
        "sayisal": sum(1 for k in kolonlar if k["tur"] in (TUR_TAM, TUR_ONDALIK)),
        "tarih": sum(1 for k in kolonlar if k["tur"] == TUR_TARIH),
        "duplicate": int(duplicate),
        "hedef_adaylari": hedef_aday, "kimlik_adaylari": kimlik_aday,
        "donem_adaylari": donem_aday, "donem_nedenler": donem_neden,
        "kolonlar": kolonlar,
    }


# ===========================================================================
# KESIN KANTIL (tekil deger + satir sayisindan)
# ===========================================================================
def kantil_konumlari(n):
    """pandas quantile (dogrusal) icin gereken sira numaralari (0 tabanli)."""
    konum = set()
    for q in KANTIL_NOKTALARI:
        p = (n - 1) * q
        konum.add(int(math.floor(p)))
        konum.add(int(math.ceil(p)))
    return sorted(k for k in konum if 0 <= k < n)


def kantil_hesapla(n, sira_deger):
    """sira_deger: {sira_no: deger} (kantil_konumlari'ndaki siralar).
    Doner: KANTIL_NOKTALARI sirasinda degerler (pandas ile ayni formul)."""
    cikti = []
    for q in KANTIL_NOKTALARI:
        p = (n - 1) * q
        alt, ust = int(math.floor(p)), int(math.ceil(p))
        a, b = float(sira_deger[alt]), float(sira_deger[ust])
        cikti.append(a + (b - a) * (p - alt) if ust != alt else a)
    return cikti


def siradan_kantil(degerler_sirali, adetler, n):
    """Sirali tekil degerler + adetler -> kantiller (yerel motor)."""
    gerek = kantil_konumlari(n)
    sira_deger, bas, j = {}, 0, 0
    for v, c in zip(degerler_sirali, adetler):
        son = bas + int(c)
        while j < len(gerek) and gerek[j] < son:
            sira_deger[gerek[j]] = v
            j += 1
        bas = son
        if j >= len(gerek):
            break
    return kantil_hesapla(n, sira_deger)


# ===========================================================================
# YEREL MOTOR (pandas) - test ve kucuk veri
# ===========================================================================
def pandas_turu(seri):
    if pd.api.types.is_bool_dtype(seri):
        return TUR_MANTIKSAL
    if pd.api.types.is_integer_dtype(seri):
        return TUR_TAM
    if pd.api.types.is_float_dtype(seri):
        return TUR_ONDALIK
    if pd.api.types.is_datetime64_any_dtype(seri):
        return TUR_TARIH
    return TUR_METIN


def normallestir(seri, tur):
    """Iki motorun ortak bos tanimi: ondalikta NaN, metinde "" bostur."""
    if tur == TUR_ONDALIK:
        return seri.where(~seri.isna(), np.nan)
    if tur == TUR_METIN:
        s = seri.astype(object)
        return s.where(s.notna() & (s.astype(str) != ""), None)
    return seri


def ilk_gecis_ozeti(ad, tur, seri):
    """Bir kolonun birinci gecis sayilari (yerel motor). Spark motoru ayni
    alanlari toplu sorgu ile uretir (profil_spark._ilk_gecis)."""
    dolu = seri.dropna()
    oz = {"ad": ad, "tur": tur, "dolu": int(len(dolu)),
          "bos": int(len(seri) - len(dolu)), "min": None, "max": None,
          "hepsi_tam": False, "n_sonlu": 0, "n_kesirli": 0, "pozitif": None,
          "n_pii_aday": 0, "ym_degil": None, "ymd_degil": None,
          "ornek": dolu.iloc[0] if len(dolu) else None}
    if tur in SAYISAL_TURLER and len(dolu):
        v = dolu.astype(float)
        oz["min"], oz["max"] = float(v.min()), float(v.max())
        sonlu = v[np.isfinite(v)]
        oz["n_sonlu"] = int(len(sonlu))
        oz["n_kesirli"] = int((sonlu != np.floor(sonlu)).sum())
        oz["hepsi_tam"] = bool(np.isfinite(v).all()) and not oz["n_kesirli"]
        oz["pozitif"] = int((v > 0).sum())
        a = v.abs()
        oz["n_pii_aday"] = int(((a % 1 == 0) & (a >= PII_SAYI_ALT)
                                & (a < PII_SAYI_UST)).sum())
        oz["ym_degil"] = int((~(v.between(YM_ALT, YM_UST)
                                & (v % 100).between(1, 12))).sum())
        oz["ymd_degil"] = int((~(v.between(YMD_ALT, YMD_UST)
                                 & ((v // 100) % 100).between(1, 12)
                                 & (v % 100).between(1, 31))).sum())
    elif tur == TUR_TARIH and len(dolu):
        oz["min"], oz["max"] = dolu.min(), dolu.max()
    return oz


def yerel_profil(df, veri_seti=None):
    """Ayni kurallar pandas ile. Yalnizca test ve kucuk veri icindir;
    buyuk veride Spark motoru (profil_spark) kullanilir."""
    satir = int(len(df))
    temiz = {}
    ozetler = []
    for kol in df.columns:
        ad = str(kol)
        tur = pandas_turu(df[kol])
        s = normallestir(df[kol], tur)
        temiz[kol] = s
        oz = ilk_gecis_ozeti(ad, tur, s)
        sayim = s.dropna().value_counts(sort=False)
        oz["tekil"] = int(len(sayim))
        degerler = list(sayim.index)
        adetler = sayim.values.astype("int64")
        # SIRA KURALI (iki motorda ayni): adet azalan, esitlikte deger artan.
        sira = sorted(zip(degerler, adetler), key=lambda x: (-x[1], x[0]))
        oz["degerler"] = ([(v, int(n)) for v, n in sira]
                          if oz["tekil"] <= DEGER_LISTE_SINIRI else None)
        oz["ust_degerler"] = [(v, int(n)) for v, n in sira[:UST_DEGER_ADEDI]]
        # Ornek: en kucuk uc deger (dogal sira).
        oz["ornek3"] = sorted(degerler)[:ORNEK_UC]
        if tur in SAYISAL_TURLER and oz["dolu"]:
            sirali = sorted(zip([float(v) for v in degerler], adetler))
            oz["kantiller"] = siradan_kantil([v for v, _ in sirali],
                                             [c for _, c in sirali], oz["dolu"])
        gorev = gorev_plani(oz, sozluk_mod._pii_ad_mi(ad))
        parca = parca_degerlendir(tur, degerler, adetler, gorev)
        oz["donem_parca"] = parca.get("donem")
        if tarih_gecisi_gerekli_mi(oz):
            oz["donem_parca"]["tarih_ok"] = tarih_parcasi(tur, degerler, adetler)
        oz["parca"] = parca
        oz["donem_degerleri"] = None
        if donem_adayi_mi(oz, satir) and oz["tekil"] <= DONEM_DEGER_SINIRI:
            oz["donem_degerleri"] = donem_degerleri(tur, degerler)
        ozetler.append(oz)
    tablo = pd.DataFrame(temiz)
    duplicate = int(tablo.duplicated().sum()) if satir else 0
    return profil_kur(veri_seti, satir, duplicate, ozetler, "yerel")
