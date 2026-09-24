# -*- coding: utf-8 -*-
"""fe_agent/ifade.py — kisitli ifade grameri.

LLM Python KODU YAZMAZ. Sadece su gramere uyan bir ifade yazar:
    KOL_A / KOL_B
    log1p(KOL_C) - KOL_D
    clip(KOL_E / (KOL_F + 1), 0, 10)

Ifade ast ile ayristirilip dugum dugum denetlenir. Gecerse:
  - degerlendir() pandas Serisi uretir (eval YOK, kendi yurutucusu var)
  - python_kodu() okunabilir, calistirilabilir Python satiri uretir

Boylece LLM'in hallusinasyonu koda donusemez ama cikti yine de
tekrar uretilebilir gercek Python olur.
"""

import ast
import keyword
import re

import numpy as np
import pandas as pd

# Izinli fonksiyonlar ve argüman sayilari
IZINLI_FONK = {
    "log1p": (1, 1),
    "abs":   (1, 1),
    "sqrt":  (1, 1),
    "rank":  (1, 1),
    "clip":  (3, 3),
    "fark":  (2, 2),
}

# Bu fonksiyonlar ilk argümanda pandas Serisi metodu (.abs/.clip/.rank)
# cagirir; skaler argümanla hem degerlendir() hem uretilen kod AttributeError
# atar. Bu yuzden ilk argümanda EN AZ BIR KOLON sart.
SERI_GEREKTIREN = {"log1p", "abs", "sqrt", "rank", "clip"}

IZINLI_IKILI = (ast.Add, ast.Sub, ast.Mult, ast.Div)
IZINLI_TEKLI = (ast.UAdd, ast.USub)

MAX_UZUNLUK = 160
MAX_DUGUM = 40

# Gomulen metinler icin uzunluk sinirlari
MAX_GEREKCE = 200
MAX_BASLIK = 120
MAX_AD = 128


class IfadeHatasi(Exception):
    pass


# ===========================================================================
# GOMULEN METIN GUVENLIGI
# ===========================================================================
# LLM ciktisindan gelen ad/gerekce/baslik dogrudan kod sablonlarina
# gomuluyor. Satir sonu veya tirnak sablondan kacip keyfi Python satiri
# ekleyebilir; asagidaki iki yardimci bunu engeller.

# Satir sonu, tasima ve diger kontrol karakterleri (Unicode satir
# ayiricilari dahil).
_KONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f  ​﻿]")


def _tek_satir(metin, sinir):
    """Cok satirli/kontrol karakterli metni tek satirlik guvenli metne cevirir."""
    if metin is None:
        return ""
    if not isinstance(metin, str):
        metin = str(metin)
    metin = _KONTROL.sub(" ", metin)
    metin = re.sub(r"\s+", " ", metin).strip()
    if sinir and len(metin) > sinir:
        metin = metin[:sinir].rstrip() + "..."
    return metin


def _yorum(metin, sinir):
    """Python yorum satirina gomulecek metin."""
    return _tek_satir(metin, sinir)


def _alintili(metin, sinir=MAX_AD):
    """Cift tirnakli bir Python metin sabitine gomulecek deger.

    Tirnak ve ters bolu tamamen atilir; boylece sabit hicbir kosulda
    kapanip kod baslatamaz.
    """
    metin = _tek_satir(metin, sinir)
    return metin.replace("\\", "").replace('"', "").replace("'", "")


def ad_dogrula(ad):
    """Uretilecek kolon adini dogrular.

    Ad dogrudan `df["..."] = ...` sablonuna gomuldugu icin gecerli bir
    Python tanimlayicisi olmak ZORUNDA; degilse ValueError firlatilir.
    Cagiran (akis.py) bu hatayi yakalar.
    """
    if not isinstance(ad, str):
        raise ValueError("gecersiz degisken adi: metin degil (%s)"
                         % type(ad).__name__)
    if not ad:
        raise ValueError("gecersiz degisken adi: bos")
    if len(ad) > MAX_AD:
        raise ValueError("gecersiz degisken adi: cok uzun (%d karakter)" % len(ad))
    if not ad.isidentifier():
        raise ValueError("gecersiz degisken adi: %r, sadece harf, rakam ve "
                         "alt cizgi kullanilabilir" % ad[:60])
    if keyword.iskeyword(ad) or keyword.issoftkeyword(ad):
        raise ValueError("gecersiz degisken adi: %r Python anahtar kelimesi" % ad)
    return ad


# ===========================================================================
# DOGRULAMA
# ===========================================================================
def _kolon_iceriyor(dugum):
    """Alt agacta en az bir kolon (ast.Name) var mi?"""
    return any(isinstance(d, ast.Name) for d in ast.walk(dugum))


def _denetle(dugum, kolonlar, kullanilan, sayac):
    sayac[0] += 1
    if sayac[0] > MAX_DUGUM:
        raise IfadeHatasi("ifade fazla karmasik")

    if isinstance(dugum, ast.BinOp):
        if not isinstance(dugum.op, IZINLI_IKILI):
            raise IfadeHatasi("izinsiz operator")
        _denetle(dugum.left, kolonlar, kullanilan, sayac)
        _denetle(dugum.right, kolonlar, kullanilan, sayac)
        return

    if isinstance(dugum, ast.UnaryOp):
        if not isinstance(dugum.op, IZINLI_TEKLI):
            raise IfadeHatasi("izinsiz tekli operator")
        _denetle(dugum.operand, kolonlar, kullanilan, sayac)
        return

    if isinstance(dugum, ast.Call):
        if not isinstance(dugum.func, ast.Name):
            raise IfadeHatasi("izinsiz cagri")
        ad = dugum.func.id
        if ad not in IZINLI_FONK:
            raise IfadeHatasi("bilinmeyen fonksiyon: %s" % ad)
        if dugum.keywords:
            raise IfadeHatasi("anahtar argüman kullanilamaz")
        alt, ust = IZINLI_FONK[ad]
        if not (alt <= len(dugum.args) <= ust):
            raise IfadeHatasi("%s icin argüman sayisi hatali" % ad)
        for a in dugum.args:
            _denetle(a, kolonlar, kullanilan, sayac)
        if ad in SERI_GEREKTIREN and not _kolon_iceriyor(dugum.args[0]):
            raise IfadeHatasi(
                "%s fonksiyonunun ilk argümani en az bir kolon icermeli" % ad)
        return

    if isinstance(dugum, ast.Name):
        if dugum.id not in kolonlar:
            raise IfadeHatasi("tabloda olmayan kolon: %s" % dugum.id)
        kullanilan.add(dugum.id)
        return

    if isinstance(dugum, ast.Constant):
        if not isinstance(dugum.value, (int, float)) or isinstance(dugum.value, bool):
            raise IfadeHatasi("sadece sayisal sabit kullanilabilir")
        return

    raise IfadeHatasi("izinsiz ifade ogesi: %s" % type(dugum).__name__)


def dogrula(ifade, kolonlar):
    """Doner: (gecerli_mi, hata_metni, kullanilan_kolon_listesi)"""
    if not ifade or not isinstance(ifade, str):
        return False, "bos ifade", []
    ifade = ifade.strip()
    if len(ifade) > MAX_UZUNLUK:
        return False, "ifade cok uzun", []
    try:
        agac = ast.parse(ifade, mode="eval")
    except SyntaxError as e:
        return False, "sozdizimi hatasi: %s" % e.msg, []

    kullanilan = set()
    try:
        _denetle(agac.body, set(kolonlar), kullanilan, [0])
    except IfadeHatasi as e:
        return False, str(e), []

    if not kullanilan:
        return False, "hicbir kolon kullanilmamis", []
    return True, None, sorted(kullanilan)


# ===========================================================================
# YURUTME  (eval YOK — agac elle gezilir)
# ===========================================================================
def _seri(df, kol):
    return pd.to_numeric(df[kol], errors="coerce")


def _bol(a, b):
    """Sifira bolmeyi NaN yapar; pandas sonsuz uretmesin diye."""
    if isinstance(b, pd.Series):
        b = b.replace(0, np.nan)
    elif b == 0:
        return np.nan
    return a / b


def _yurut(dugum, df):
    if isinstance(dugum, ast.BinOp):
        sol = _yurut(dugum.left, df)
        sag = _yurut(dugum.right, df)
        if isinstance(dugum.op, ast.Add):  return sol + sag
        if isinstance(dugum.op, ast.Sub):  return sol - sag
        if isinstance(dugum.op, ast.Mult): return sol * sag
        if isinstance(dugum.op, ast.Div):  return _bol(sol, sag)

    if isinstance(dugum, ast.UnaryOp):
        d = _yurut(dugum.operand, df)
        return -d if isinstance(dugum.op, ast.USub) else d

    if isinstance(dugum, ast.Call):
        ad = dugum.func.id
        a = [_yurut(x, df) for x in dugum.args]
        if ad == "log1p": return np.log1p(a[0].clip(lower=0))
        if ad == "abs":   return a[0].abs()
        if ad == "sqrt":  return np.sqrt(a[0].clip(lower=0))
        if ad == "rank":  return a[0].rank(pct=True)
        if ad == "clip":  return a[0].clip(a[1], a[2])
        if ad == "fark":  return a[0] - a[1]

    if isinstance(dugum, ast.Name):
        return _seri(df, dugum.id)

    if isinstance(dugum, ast.Constant):
        return dugum.value

    raise IfadeHatasi("yurutulemeyen oge")


def degerlendir(df, ifade):
    """Dogrulanmis bir ifadeyi df uzerinde hesaplar."""
    agac = ast.parse(ifade.strip(), mode="eval")
    return _yurut(agac.body, df)


# ===========================================================================
# KOD URETIMI  (kullanicinin okuyup calistirabilecegi Python)
# ===========================================================================
def _kod(dugum):
    if isinstance(dugum, ast.BinOp):
        sol, sag = _kod(dugum.left), _kod(dugum.right)
        if isinstance(dugum.op, ast.Div):
            return "_bol(%s, %s)" % (sol, sag)
        op = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*"}[type(dugum.op)]
        return "(%s %s %s)" % (sol, op, sag)

    if isinstance(dugum, ast.UnaryOp):
        return ("-" if isinstance(dugum.op, ast.USub) else "") + _kod(dugum.operand)

    if isinstance(dugum, ast.Call):
        ad = dugum.func.id
        a = [_kod(x) for x in dugum.args]
        if ad == "log1p": return "np.log1p(%s.clip(lower=0))" % a[0]
        if ad == "abs":   return "%s.abs()" % a[0]
        if ad == "sqrt":  return "np.sqrt(%s.clip(lower=0))" % a[0]
        if ad == "rank":  return "%s.rank(pct=True)" % a[0]
        if ad == "clip":  return "%s.clip(%s, %s)" % (a[0], a[1], a[2])
        if ad == "fark":  return "(%s - %s)" % (a[0], a[1])

    if isinstance(dugum, ast.Name):
        return '_s(df, "%s")' % dugum.id

    if isinstance(dugum, ast.Constant):
        return repr(dugum.value)

    raise IfadeHatasi("koda cevrilemeyen oge")


def python_kodu(ad, ifade):
    """Tek satirlik, calistirilabilir pandas atamasi uretir.

    `ad` gecerli bir Python tanimlayicisi degilse ValueError firlatir.
    """
    ad = ad_dogrula(ad)
    agac = ast.parse(ifade.strip(), mode="eval")
    return 'df["%s"] = %s' % (ad, _kod(agac.body))


BASLIK = '''# -*- coding: utf-8 -*-
"""Degisken Kesif Asistani tarafindan uretilen kod.
Bu dosya elle calistirilabilir; asistanin urettigi kolonlarin aynisini uretir."""

import numpy as np
import pandas as pd
import dataiku


def _s(df, kol):
    """Kolonu sayisala cevirir."""
    return pd.to_numeric(df[kol], errors="coerce")


def _bol(a, b):
    """Sifira bolmeyi NaN yapar."""
    if isinstance(b, pd.Series):
        b = b.replace(0, np.nan)
    elif b == 0:
        return np.nan
    return a / b
'''


def _kod_satiri_dogrula(kod):
    """Bloklardan gelen hazir kod satirini denetler.

    Tek bir Python deyimi olmali; cok satirli kod sablondan kacip
    beklenmeyen is yapabilir.
    """
    if not isinstance(kod, str) or not kod.strip():
        raise ValueError("gecersiz kod satiri: bos")
    if _KONTROL.search(kod.replace("\t", " ")):
        raise ValueError("gecersiz kod satiri: satir sonu/kontrol karakteri "
                         "iceriyor: %r" % kod[:60])
    try:
        agac = ast.parse(kod.strip(), mode="exec")
    except SyntaxError as e:
        raise ValueError("gecersiz kod satiri: %s" % e.msg)
    if len(agac.body) != 1:
        raise ValueError("gecersiz kod satiri: tek deyim olmali")
    return kod.strip()


def script_olustur(kaynak_dataset, hedef_dataset, doldurma, bloklar):
    """bloklar: [(baslik, [(ad, kod_satiri, gerekce), ...]), ...]

    Gomulen tum metinler (ad, baslik, gerekce, dataset adlari) temizlenir;
    gecersiz degisken adinda ValueError firlatilir.
    """
    bloklar = list(bloklar or [])
    p = [BASLIK, "",
         'df = dataiku.Dataset("%s").get_dataframe()' % _alintili(kaynak_dataset),
         ""]

    if doldurma == "medyan":
        p += ["# --- Eksik deger doldurma (baz veri setinde uygulandi) ---",
              "for _k in df.select_dtypes(include=[np.number]).columns:",
              "    df[_k] = df[_k].fillna(df[_k].median())", ""]

    toplam = 0
    for blok in bloklar:
        baslik, satirlar = blok[0], (blok[1] or [])
        if not satirlar:
            continue
        p += ["# " + "=" * 68,
              "# %s" % _yorum(baslik, MAX_BASLIK),
              "# " + "=" * 68]
        for i, satir in enumerate(satirlar, 1):
            if len(satir) < 2:
                raise ValueError("gecersiz kod blogu satiri: %r" % (satir,))
            ad, kod = satir[0], satir[1]
            gerekce = satir[2] if len(satir) > 2 else ""
            ad_dogrula(ad)
            kod = _kod_satiri_dogrula(kod)
            gerekce = _yorum(gerekce, MAX_GEREKCE)
            if gerekce:
                p.append("# %02d. %s" % (i, gerekce))
            p.append(kod)
            toplam += 1
        p.append("")

    p += ['dataiku.Dataset("%s").write_with_schema(df)' % _alintili(hedef_dataset),
          'print("Tamamlandi: %d kolon")' % toplam, ""]
    return "\n".join(p)
