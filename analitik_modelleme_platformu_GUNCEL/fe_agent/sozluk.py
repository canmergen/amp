# -*- coding: utf-8 -*-
"""fe_agent/sozluk.py — veri setinden degisken sozlugu uretir.

Her kolon icin istatistiksel profil cikarilir (tip, null orani, tekil
sayisi, ornek degerler, dagilim). Bu profil LLM'e verilir, LLM kolonun
ne anlama geldigini yazar. Ciktı sabit adli bir dataset olarak kaydedilir.

GIZLILIK NOTU
  Ornek degerler LLM'e gonderilir. Su kolonlarda HICBIR gercek deger
  (ornek, dagilim, min/maks) prompt'a girmez; yalnizca tip ve istatistik
  SAYILARI (null orani, tekil sayisi) gider:
    - kolon adi kisisel veri sozlugune uyanlar (TCKN, AD_SOYAD, ADRES,
      TELEFON, IBAN, KART_NO …)
    - degerleri kisisel veri desenine uyanlar (11 haneli TC kimlik, IBAN,
      05xx/+90 telefon, 16 haneli kart, e-posta)
    - kimlik benzeri kolonlar (tekil oran cok yuksek — satir sayisindan
      BAGIMSIZ)
    - serbest/uzun metin kolonlari
  PII denetimi sayisal/kategorik ayrimindan BAGIMSIZDIR: tekrar eden
  TCKN'li panel tablosunda da, 100 tekil musteri numarasinda da devrededir.
"""

import re

import numpy as np
import pandas as pd

ORNEK_ADET = 8
KIMLIK_ESIK = 0.85        # tekil oran bunun ustundeyse ornek gonderilmez
UZUN_METIN = 60           # ortalama karakter bunun ustundeyse ornek gonderilmez

PII_ORNEK_ADET = 500      # deseni ararken bakilacak en fazla deger
PII_DESEN_ORAN = 0.30     # degerlerin bu orani desene uyarsa kolon PII sayilir

# --- Turkce karakterden ve buyuk/kucuk harften bagimsiz ad eslesmesi -------
_TR_HARF = {"Ç": "C", "Ğ": "G", "İ": "I", "Ö": "O", "Ş": "S", "Ü": "U",
            "ç": "C", "ğ": "G", "ı": "I", "ö": "O", "ş": "S", "ü": "U"}

# Kolon adinda gecerse tek basina yeterli olan anahtarlar
PII_AD_PARCALARI = (
    "TCKN", "TCKIMLIK", "TCNO", "KIMLIKNO", "VATANDASLIKNO",
    "ADSOYAD", "SOYAD", "UNVAN", "ADRES",
    "TELEFON", "GSM", "CEPTEL", "TELNO",
    "EPOSTA", "EMAIL", "MAILADRES",
    "IBAN", "HESAPNO", "KARTNO", "KREDIKARTI",
)
# Tek basina anlamli PII belirtecleri (tam token eslesmesi)
PII_TOKEN = {"TCKN", "TC", "TCK", "KIMLIK", "AD", "ADI", "ISIM", "ISMI",
             "SOYAD", "SOYADI", "ADSOYAD", "UNVAN", "UNVANI", "ADRES",
             "ADRESI", "TEL", "TELEFON", "GSM", "CEP", "EMAIL", "EPOSTA",
             "MAIL", "IBAN", "HESAPNO", "KARTNO", "NAME", "SURNAME",
             "PHONE", "ADDRESS"}
# "AD/ADI/ISIM" tek basina URUN_ADI, SUBE_ADI gibi kolonlarda da geciyor;
# bunlar PII degil. Kisi baglamı varsa ya da kolon dogrudan AD/ADI ise PII.
ZAYIF_TOKEN = {"AD", "ADI", "ISIM", "ISMI", "NAME"}
KISI_TOKEN = {"MUSTERI", "KISI", "SAHIS", "BASVURAN", "KEFIL", "ES", "ESI",
              "BABA", "ANNE", "YETKILI", "TEMSILCI", "BORCLU", "MUSTERININ"}

_DESEN_EPOSTA = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
_DESEN_IBAN = re.compile(r"^TR\d{24}$", re.I)
_DESEN_TELEFON = re.compile(r"^(?:\+?90)?0?5\d{9}$")
_DESEN_KART = re.compile(r"^\d{16}$")
_DESEN_TCKN = re.compile(r"^[1-9]\d{10}$")


def _normalize_ad(ad):
    s = "".join(_TR_HARF.get(c, c) for c in str(ad)).upper()
    return re.sub(r"[^A-Z0-9]+", "", s)


def _tokenler(ad):
    s = "".join(_TR_HARF.get(c, c) for c in str(ad)).upper()
    return [p for p in re.split(r"[^A-Z0-9]+", s) if p]


def _tckn_sezgi(d):
    """TC kimlik kontrol basamagi sezgisi (kesin dogrulama degil)."""
    if not _DESEN_TCKN.match(d):
        return False
    r = [int(x) for x in d]
    if (sum(r[0:9:2]) * 7 - sum(r[1:8:2])) % 10 != r[9]:
        return False
    return sum(r[:10]) % 10 == r[10]


def _pii_ad_mi(kol):
    """Kolon ADINA gore kisisel veri denetimi."""
    if not kol:
        return None
    duz = _normalize_ad(kol)
    for parca in PII_AD_PARCALARI:
        if parca in duz:
            return parca
    tokenler = _tokenler(kol)
    kume = set(tokenler)
    for t in tokenler:
        if t not in PII_TOKEN:
            continue
        if t in ZAYIF_TOKEN and not (kume & KISI_TOKEN) and len(tokenler) > 1:
            continue          # URUN_ADI, SUBE_ADI … PII degil
        return t
    return None


def _pii_deger_mi(s):
    """Kolon DEGERLERINE gore kisisel veri denetimi (tip bagimsiz)."""
    ornek = s.dropna()
    if not len(ornek):
        return None
    ornek = ornek.head(PII_ORNEK_ADET).astype(str).str.strip()
    # 12345678901.0 gibi float gosterimlerini sadelestir
    ornek = ornek.str.replace(r"\.0$", "", regex=True)
    sade = ornek.str.replace(r"[\s\-()]", "", regex=True)
    n = float(len(ornek))

    denetimler = (
        ("e-posta", ornek.map(lambda v: bool(_DESEN_EPOSTA.match(v)))),
        ("IBAN", sade.map(lambda v: bool(_DESEN_IBAN.match(v)))),
        ("telefon", sade.map(lambda v: bool(_DESEN_TELEFON.match(v)))),
        ("TC kimlik no", sade.map(lambda v: bool(_DESEN_TCKN.match(v)))),
        ("kart numarası", sade.map(lambda v: bool(_DESEN_KART.match(v)))),
    )
    for ad, isaret in denetimler:
        if isaret.sum() / n >= PII_DESEN_ORAN:
            if ad == "TC kimlik no" and sade.map(_tckn_sezgi).sum() / n >= PII_DESEN_ORAN:
                return "TC kimlik no (kontrol basamağı uyumlu)"
            return ad
    return None

def _ondalikli_mi(s):
    """Ondalik kismi olan sayisal seri mi? (kimlik olamaz.)"""
    if not pd.api.types.is_float_dtype(s):
        return False
    d = s.dropna()
    if d.empty:
        return False
    try:
        return bool((d != d.round()).any())
    except Exception:
        return False


def _ornek_guvenli_mi(s, satir, kol=None):
    """Doner: (guvenli_mi, neden). Guvenli degilse HICBIR gercek deger
    prompt'a girmez; yalnizca tip ve istatistik sayilari paylasilir."""
    # 1) PII katmani — sayisal/kategorik ayrimindan BAGIMSIZ
    ad_eslesme = _pii_ad_mi(kol)
    if ad_eslesme:
        return False, "kişisel veri (kolon adı: %s)" % ad_eslesme
    deger_eslesme = _pii_deger_mi(s)
    if deger_eslesme:
        return False, "kişisel veri (değer deseni: %s)" % deger_eslesme

    # 2) Kimlik benzeri — tekil oran, satir sayisindan bagimsiz.
    # ONDALIKLI sayilar haric: bakiye/gelir/tutar alanlari dogal olarak
    # ~%100 tekildir ama kimlik degildir. Bunlarin DAGILIM OZETI (min,
    # p25, medyan, maks) sozluk aciklamasi icin degerli ve kisisel veri
    # icermez; engellenmesi LLM'i bu kolonlarda korlestiriyordu.
    tekil = int(s.nunique(dropna=True))
    if satir and tekil / max(satir, 1) > KIMLIK_ESIK and not _ondalikli_mi(s):
        return False, "kimlik benzeri"

    # 3) Serbest/uzun metin
    if not pd.api.types.is_numeric_dtype(s):
        try:
            ort = s.dropna().astype(str).str.len().mean()
            if ort and ort > UZUN_METIN:
                return False, "uzun metin"
        except Exception:
            pass
    return True, ""


def profil_cikar(df, haric=()):
    """Her kolon icin LLM'e gidecek profili hazirlar.
    Doner: [{ad, tip, null_oran, tekil, ornekler, dagilim, not}]"""
    haric = set(h for h in haric if h)
    satir = int(len(df))
    kayitlar = []

    for kol in df.columns:
        if kol in haric:
            continue
        s = df[kol]
        sayisal = pd.api.types.is_numeric_dtype(s)
        null_oran = float(s.isna().mean())
        tekil = int(s.nunique(dropna=True))

        guvenli, neden = _ornek_guvenli_mi(s, satir, kol)
        ornekler, dagilim = [], ""

        if guvenli:
            if sayisal:
                sn = pd.to_numeric(s, errors="coerce").dropna()
                if len(sn):
                    q = sn.quantile([0, .25, .5, .75, 1]).round(3).tolist()
                    dagilim = ("min %s · p25 %s · medyan %s · p75 %s · maks %s"
                               % tuple(q))
                    ornekler = [round(float(x), 3) for x in sn.head(ORNEK_ADET)]
            else:
                sayim = s.astype(str).value_counts().head(ORNEK_ADET)
                ornekler = [str(i) for i in sayim.index]
                dagilim = " · ".join("%s (%s)" % (k, v) for k, v in
                                     list(sayim.items())[:5])

        kayitlar.append({
            "ad": kol,
            "tip": "sayısal" if sayisal else "kategorik",
            "null_oran": round(null_oran, 4),
            "tekil": tekil,
            "ornekler": ornekler,
            "dagilim": dagilim,
            "not": neden,
        })
    return kayitlar


def tablo_olustur(profiller, aciklamalar):
    """Profil + LLM aciklamasini tek tabloda birlestirir.

    aciklamalar: {kolon_adi: {"aciklama": ..., "kategori": ...}}
    Sozluk tablosunun ILK kolonu degisken adi olmali — akis.py bu
    varsayimla sozluk kapsamini hesapliyor.
    """
    satirlar = []
    for p in profiller:
        a = aciklamalar.get(p["ad"]) or {}
        satirlar.append({
            "DEGISKEN": p["ad"],
            "ACIKLAMA": (a.get("aciklama") or "").strip() or "(açıklama üretilemedi)",
            "KATEGORI": (a.get("kategori") or "").strip() or "tanımsız",
            "TIP": p["tip"],
            "NULL_ORANI": p["null_oran"],
            "TEKIL_DEGER": p["tekil"],
            "DAGILIM": p["dagilim"],
            "URETIM": "yapay zekâ" if a.get("aciklama") else "üretilemedi",
            "NOT": p["not"],
        })
    return pd.DataFrame(satirlar)


def ozet(tablo):
    if not len(tablo):
        return {"toplam": 0, "aciklamali": 0, "kapsam": 0.0, "kategoriler": {}}
    aciklamali = int((tablo["URETIM"] == "yapay zekâ").sum())
    kirilim = tablo["KATEGORI"].value_counts().to_dict()
    return {
        "toplam": int(len(tablo)),
        "aciklamali": aciklamali,
        "kapsam": round(100.0 * aciklamali / len(tablo), 1),
        "kategoriler": {str(k): int(v) for k, v in list(kirilim.items())[:12]},
    }
