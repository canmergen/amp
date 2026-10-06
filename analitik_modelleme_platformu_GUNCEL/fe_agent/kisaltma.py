# -*- coding: utf-8 -*-
"""fe_agent/kisaltma.py - KOLON ADI KISALTMALARI: sozlukten OGRENILEN
anlamlar + onayli kisaltma hafizasi (proje geneli).


Bu yuzden SABIT KISALTMA LISTESI YOK: her anlam o calismanin sozlugunden
ve onayli tanim hafizasindan ogrenilir. Yeni onaylanan her tanim bir
sonraki cikarimin girdisidir; sistem kullanildikca kendini gunceller.

1) ISTATISTIK (cikar) - butun tanimlar:
   Kolon adi parcalara bolunur (A_B_C_180D_D -> A, B, C, D; 180D gibi
   pencereler ve saf sayilar atlanir). Her parca icin
   adinda o parca gecen TUM tanimli kolonlarin tanimlarinda gecen
   kelimeler (ve iki kelimelik ifadeler) sayilir:
     destek: kelime, parcayi tasiyan tanimlarin yuzde kacinda geciyor
     ayirt : destek - (parcayi TASIMAYAN tanimlardaki pay)
   Adaylar en guclu kanittan zayifa dogru ATANIR. Bir parca, kolonlarinin
   yarisindan fazlasinda birlikte gectigi bir parcaya zaten verilmis
   (ya da onayli) anlami alamaz: iki kelimelik bir anlam once onu en
   guclu tasiyan parcaya gider, digeri ikinci adayina gecer. Ekli bicim, yalin hali
   sozlukte de geciyorsa yalina iner (adedi -> adet).

2) DIL MODELI (dogrulamayi_baslat) - her kisaltma icin:
   istatistigin en guclu 3 adayi ve yuzdeleri, ornek kolonlarda gecen
   DIGER kisaltmalarin anlamlari ve CESITLI secilmis en cok 8 ornek kolon
   (her yeni ornek, oncekilerde olmayan parcalari getirenlerden secilir)
   iki modele sorulur; anlasamazlarsa hakem karar verir. Emin olunamayan
   anlam bos kalir. Arka planda calisir, sonuc onbellekte tutulur.

3) HAFIZA - PROJE_HAFIZASI/KISALTMA_HAFIZASI.json (calisma klasorlerinin
   disinda; okunur bicim: {"kisaltmalar": {KISA: anlam}, "degisimler":
   {ESKI: YENI}, "notlar": {KISA: not}}). Onerilen kisaltmasi dolu
   onaylanan satirin anlami YENI kisaltmayla yazilir ve ESKI -> YENI
   degisimi not edilir (sonraki calismalarda kolon adlari buna gore
   degisir); bos ise anlam kisaltmanin kendisiyle yazilir.
   YALNIZ kullanicinin onayladigi kisaltmalar girer ve her
   zaman ogrenilenin onune gecer. Girdi veri setine ve sozluge hicbir
   kosulda yazilmaz. OKUMA HATASI YAZMAYI DURDURUR: dosya var ama
   okunamiyorsa ustune yazilmaz.

Dil modeline giden istemde: onayli kisaltmalar KESIN, ogrenilenler
TAHMINI etiketiyle gider."""

import datetime
import json
import re
import threading
import time
from collections import Counter

import pandas as pd

from fe_agent import tablo_io
from fe_agent.akis_durum import _folder

DOSYA = "/KISALTMA_HAFIZASI.json"
ESKI_DOSYA = "/KISALTMA_HAFIZASI.parquet"     # varsa bir kez JSON'a aktarilip silinir
# YENI: kisaltma kolon adlarinda neye cevrildi (degisim); doluysa anlam
# yeni kisaltmanin satirinda durur, bu satirin ANLAM'i bostur.
KOLONLAR = ["KISALTMA", "ANLAM", "KAYNAK", "KULLANICI", "TARIH", "YENI"]
KAYNAK_ONAY = "sözlükten öğrenildi, kullanıcı onayladı"
KAYNAK_KULLANICI = "kullanıcı yazdı"

# Yalniz KELIME SAYIMI (istatistik anlam adayi) ve birlestirme adayi icin:
# 1-2 kolondan sayim anlam vermez. Kartta gorunmeyi ETKILEMEZ; kolon
# adlarindaki her kisaltma karta gelir ve dil modeline sorulur.
EN_AZ_KOLON = 3
DESTEK_ESIK = 0.6      # anlam, o kolonlarin tanimlarinin en az bu kadarinda
AYIRT_ESIK = 0.3       # ... ve digerlerinden en az bu kadar daha sik
BIRLIKTE_ESIK = 0.5    # bu kadar birlikte gecen parcalar ayni anlami alamaz
ADAY_SAYISI = 3        # dil modeline giden istatistik adayi

_TR_KUCUK = str.maketrans({"I": "ı", "İ": "i"})
_TR_SADE = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
# SAYI DEGERLI KALIP:
# 1-2 harf + en az 2 rakam. Harf kismi kisaltma, rakam degerdir.
# Tek rakamlilar kisaltmanin kendisi sayilir.
_SAYILI = re.compile(r"^([A-Z]{1,2})(\d{2,})$")
# Anlam tasimayan baglaclar. "gun", "ay" artik DURAK DEGIL: DAY / MONTH
# gibi kisaltmalarin anlami olabilirler; pencereli tanimlarin hepsinde
# gectikleri icin ayirt olcusu onlari zaten eler.
_DURAK = {"ve", "ile", "icin", "olan", "bir", "bu", "da", "de", "gore", "son",
          "ki", "mi", "ya", "ne", "o", "arasi"}

ONBELLEK_OMRU_SN = 30.0
_ONBELLEK = {"zaman": 0.0, "df": None}
_KILIT = threading.Lock()


def _kucuk(metin):
    return str(metin or "").translate(_TR_KUCUK).lower()


def _sade(kelime):
    return _kucuk(kelime).translate(_TR_SADE)


def _kok(kelime):
    """Kaba Turkce kok: ilk 5 harf (sadelestirilmis). 'islem', 'islemi',
    'islemlerin' ayni kova; 'tutari', 'tutarinin' ayni kova."""
    s = _sade(kelime)
    return s[:5] if len(s) > 5 else s


_YALIN_SAYI = re.compile(r"^\d{2,}$")


def _ham_parcalar(ad):
    """Ham sira: kisaltma adaylari ve aralarindaki pencere / sayi yerine
    None (ifade tespitinde komsuluk bozulmasin). Tek harf, ardindan
    yalniz rakamdan olusan parca geliyorsa sayi degerli kalibin harf
    kismidir (<K>_<NN>; 01.2.4'te sayidan ayrilmis bicim) ve kisaltmadir."""
    ham = [p.upper().translate(_TR_SADE)
           for p in re.split(r"[^A-Za-z0-9ÇĞİÖŞÜçğıöşü]+", str(ad or "")) if p]
    cikti = []
    for i, p in enumerate(ham):
        if len(p) == 1 and p.isalpha() and i + 1 < len(ham) and _YALIN_SAYI.match(ham[i + 1]):
            cikti.append(p)
            continue
        if p.isdigit():
            # Yalniz sayi kisaltma degil; harf iceren her parca (tek harf
            # ve sayi + harf dahil) kisaltmadir.
            cikti.append(None)
            continue
        m = _SAYILI.match(p)
        if m:
            p = m.group(1)
        cikti.append(p)
    return cikti


# HER PARCA AYRI KISALTMA: "_" ile ayrilan her parca
# kendi basina kisaltmadir; kendiliginden birlestirilmez. Kolon adlarinda
# neredeyse hep YAN YANA gecen parcalar (her birinin gectigi kolonlarin en
# az IFADE_PAY kadarinda) yalniz BIRLESTIRME ADAYIDIR: dil modeli ayri
# anlamlarin yan yana okununca anlami karistirip karistirmadigina bakar,
# karisiyorsa birlestirme onerir; oneri kullanici kabul ederse gecerli
# olur (bkz. birlesik_onerileri).
IFADE_PAY = 0.9
BIRLESIK_EN_COK = 40      # dil modeline giden en cok aday cift
BIRLESIK_ORNEK = 3        # kartta birlestirme basina "i"de gosterilen ornek kolon


def ifade_adaylari(adlar, tek_taraf=False):
    """Hep yan yana gecen parca ciftleri: {(A, B): birlikte_gectigi_kolon}.
    tek_taraf: parcalardan BIRININ gectigi kolonlarin IFADE_PAY kadarinda
    yan yana olmasi yeter (dil modeline giden birlestirme adaylari)."""
    tek, cift = Counter(), Counter()
    for ad in adlar or ():
        ham = _ham_parcalar(ad)
        tek.update(set(p for p in ham if p))
        cift.update(set((a, b) for a, b in zip(ham, ham[1:]) if a and b and a != b))
    if tek_taraf:
        return {(a, b): n for (a, b), n in cift.items()
                if n >= EN_AZ_KOLON and (n >= IFADE_PAY * tek[a] or n >= IFADE_PAY * tek[b])}
    return {(a, b): n for (a, b), n in cift.items()
            if n >= EN_AZ_KOLON and n >= IFADE_PAY * tek[a] and n >= IFADE_PAY * tek[b]}


BIRLESIK_EN_COK_PARCA = 4


def birlesik_anahtar(metin):
    """Kullanicinin yazdigi birlestirme ("<A> <B>", "<A>+<B>", "<a>_<b>")
    -> "<A>_<B>". 2-4 parca degilse ""."""
    ps = [p.upper().translate(_TR_SADE)
          for p in re.split(r"[^A-Za-z0-9ÇĞİÖŞÜçğıöşü]+", str(metin or "")) if p]
    return "_".join(ps) if 2 <= len(ps) <= BIRLESIK_EN_COK_PARCA else ""


def yan_yana(ad, anahtar):
    """Birlestirmenin parcalari kolon adinda bitisik ve bu sirayla geciyor mu
    (araya pencere / sayi girmeden)."""
    ps = [p for p in str(anahtar or "").split("_") if p]
    ham = _ham_parcalar(ad)
    n = len(ps)
    return n >= 2 and any(ham[i:i + n] == ps for i in range(len(ham) - n + 1))


def birlesik_hafiza(adlar, onay=None):
    """Hafizadaki birlestirmelerden ("_"li anahtar) bu kolon adlarinda yan
    yana gecenler: {anahtar: kolon_sayisi}."""
    onay = onaylilar() if onay is None else onay
    cikti = {}
    for k in onay:
        if "_" not in k or len(k.split("_")) > BIRLESIK_EN_COK_PARCA:
            continue
        n = sum(1 for ad in adlar if yan_yana(ad, k))
        if n:
            cikti[k] = n
    return cikti


def parcalar(ad):
    """Kolon adinin kisaltma adaylari (buyuk harf). Pencereler ve sayilar
    atlanir; her parca ayri kisaltmadir."""
    return [p for p in _ham_parcalar(ad) if p]


def _ham_bicimler(ad):
    """Kolon adinin parcalari ADDAKI haliyle: [(bicim, kisaltma, sayi)].
    Sayi degerli kalipta (<K><NN> ya da sayidan ayrilmis <K>_<NN>)
    kisaltma harf kismi, sayi deger; ardindan yalniz rakamdan olusan
    parca gelirse aralik sayilir (<K><NN>_<MM> -> sayi "<NN>-<MM>")."""
    ham = [p for p in re.split(r"[^A-Za-z0-9ÇĞİÖŞÜçğıöşü]+", str(ad or "")) if p]
    cikti, i = [], 0
    while i < len(ham):
        p = ham[i]
        u = p.upper().translate(_TR_SADE)
        i += 1
        m = _SAYILI.match(u)
        if m:
            k, sayilar = m.group(1), [m.group(2)]
        elif len(u) == 1 and u.isalpha() and i < len(ham) and _YALIN_SAYI.match(ham[i]):
            k, sayilar = u, [ham[i]]
            p = "%s_%s" % (p, ham[i])
            i += 1
        elif u.isdigit():
            cikti.append((p, None, ""))       # komsulugu bozar (birlestirme yok)
            continue
        else:
            cikti.append((p, u, ""))
            continue
        if i < len(ham) and _YALIN_SAYI.match(ham[i]):
            p, sayilar = "%s_%s" % (p, ham[i]), sayilar + [ham[i]]
            i += 1
        cikti.append((p, k, "-".join(sayilar)))
    return cikti


def ad_anlamlari(ad, anlamlar):
    """Kolon adinin parcalari ve anlamlari (tanim kontrolune giden AD PARCALARI):
    [(addaki bicim, anlam)]. Kabul edilen birlestirme ("<A>_<B>" anahtari)
    yan yana iki parcayi tek anlamla verir; sayi degerli kalipta sayi
    anlamda korunur."""
    anlamlar = anlamlar or {}
    bicim = _ham_bicimler(ad)
    cikti, i = [], 0
    while i < len(bicim):
        b, k, n = bicim[i]
        if k is None:
            i += 1
            continue
        bulundu = False
        for m in range(BIRLESIK_EN_COK_PARCA, 1, -1):
            grup = bicim[i:i + m]
            if len(grup) < m or any(g[1] is None or g[2] for g in grup):
                continue
            ortak = "_".join(g[1] for g in grup)
            if anlamlar.get(ortak):
                cikti.append(("_".join(g[0] for g in grup), anlamlar[ortak]))
                i += m
                bulundu = True
                break
        if bulundu:
            continue
        if anlamlar.get(k):
            cikti.append((b, ("%s %s" % (anlamlar[k], n)) if n else anlamlar[k]))
        i += 1
    return list(dict.fromkeys(cikti))


def sayili_degerler(tanimlar, kisa, adet=20):
    """Kisaltmanin kolon adlarinda sayi degeriyle gectigi bicimler ve
    degerleri: [(bicim, deger)], ornegin (<K>00_06, "00-06")."""
    gorulen = {}
    for ad in tanimlar or {}:
        for b, k, n in _ham_bicimler(ad):
            if k and k == kisa and n and b.upper() not in gorulen:
                gorulen[b.upper()] = n
    return sorted(gorulen.items())[:adet]


def sayili_bicimler(tanimlar, kisa, adet=8):
    """Kisaltmanin kolon adlarinda sayi degeriyle gectigi bicimler
    (<K>00, <K>06 ...); kartta kisaltmanin altinda gosterilir."""
    gorulen = []
    for ad in tanimlar or {}:
        for b, k, n in _ham_bicimler(ad):
            if k and k == kisa and n and b.upper() not in gorulen:
                gorulen.append(b.upper())
    return sorted(gorulen)[:adet]


def _tanim_kokleri(tanim):
    """Tanimdan {kok: yuzey bicimi} (tekli) ve iki kelimelik ifadeler."""
    # IKI HARFLI kelimeler de aday ("ay" -> MONTH, "en" -> "en cok"); anlam
    # tasimayan iki harfliler _DURAK'ta.
    # PARANTEZ ICI aday degil: cogunlukla Ingilizce karsilik ya da kisaltma
    # (Ingilizce karsilik, kisaltma); ifade de oradan bolunur.
    metin = re.sub(r"\([^)]*\)", " | ", str(tanim or ""))
    kelimeler = [k for k in re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü]+|\|", metin)
                 if len(k) >= 2 or k == "|"]
    tekli, ikili = {}, {}
    onceki = None
    for k in kelimeler:
        if k == "|":
            onceki = None
            continue
        kk = _kok(k)
        if _sade(k) in _DURAK:
            onceki = None
            continue
        tekli.setdefault(kk, _kucuk(k))
        if onceki is not None:
            ikili.setdefault(onceki[0] + " " + kk, onceki[1] + " " + _kucuk(k))
        onceki = (kk, _kucuk(k))
    return tekli, ikili


def _harf_uyumu(parca, kok):
    """Kisaltmanin harfleri kelimede sirayla geciyor mu (1/0)."""
    it = iter(kok)
    return int(all(h in it for h in parca.lower()))




# ONAYLI TANIM AGIRLIGI: kullanicinin platformda onayladigi tanim (tanim hafizasi),
# sozlugun ham taniminin bu kati sayilir. Zamanla onaylanan dogru bilgi
# baskin hale gelir.
ONAY_AGIRLIK = 3


def _onayli_tanimlar():
    """Sozlukteki tanim dogru kabul edildigi icin onayli tanim ayrica
    agirliklandirilmaz; calismada onaylanan tanimlar zaten sozlugun
    calisma kopyasinda (kisaltma kaynagi) yer alir."""
    return {}


def _parca_istatistigi(tanimlar):
    """Ortak hazirlik: (satirlar, parca_say, genel, yuzey, sozcukler, agirlik).
    satirlar: [(parca_kumesi, tekli, ikili)] - yalniz tanimli kolonlar.
    agirlik : satirlarla ayni sirada; onayli tanim ONAY_AGIRLIK, ham 1.
    parca_say AGIRLIKSIZ kolon sayisidir (kartta gorunen)."""
    onayli = _onayli_tanimlar()
    satirlar, agirlik = [], []
    for ad, tanim in (tanimlar or {}).items():
        if not str(tanim or "").strip():
            continue
        tekli, ikili = _tanim_kokleri(tanim)
        satirlar.append((set(parcalar(ad)), tekli, ikili))
        agirlik.append(ONAY_AGIRLIK if ad in onayli and str(onayli[ad]).strip()
                       == str(tanim).strip() else 1)
    genel = Counter()
    yuzey = {}
    sozcukler = set()
    for (_p, tekli, ikili), w in zip(satirlar, agirlik):
        sozcukler.update(tekli.values())
        for k, y in list(tekli.items()) + list(ikili.items()):
            genel[k] += w
            yuzey.setdefault(k, Counter())[y] += w
    parca_say = Counter(p for ps, _t, _i in satirlar for p in ps)
    return satirlar, parca_say, genel, yuzey, sozcukler, agirlik


def _birlikte(satirlar, parca, parca_say):
    """parca'nin kolonlarinin en az BIRLIKTE_ESIK kadarinda gecen diger
    parcalar (ya da tersine: diger parcanin kolonlarinin o kadarinda
    parca geciyorsa)."""
    say = Counter()
    for ps, _t, _i in satirlar:
        if parca in ps:
            say.update(p for p in ps if p != parca)
    n = float(parca_say.get(parca) or 1)
    return set(p for p, c in say.items()
               if c / n >= BIRLIKTE_ESIK or c / float(parca_say.get(p) or 1) >= BIRLIKTE_ESIK)


def _yasakli(kelimeler, yasak):
    """Kelimelerden biri yasak bir anlamla BASLIYOR mu ("gunun" -> "gun").
"""
    return any(_sade(k).startswith(y) for k in kelimeler for y in yasak if y)


def _anlam_kelimeleri(anlam):
    return set(_sade(k) for k in str(anlam or "").split() if len(k) >= 2)


def adaylar(tanimlar):
    """Her parca icin istatistik adaylari.
    Doner: {KISA: {"kolon": n, "adaylar": [{"anlam", "destek", "ayirt"}]}}
    (en gucluden zayifa; iki kelimelik ifade, kelimesi bu parcaya ozguyse
    tek kelimeden once gelir)."""
    satirlar, parca_say, genel, yuzey, sozcukler, agirlik = _parca_istatistigi(tanimlar)
    n = len(satirlar)
    n_w = float(sum(agirlik))
    cikti = {}
    if n < EN_AZ_KOLON:
        return cikti
    for parca, adet in parca_say.items():
        if adet < EN_AZ_KOLON or adet == n:
            continue
        icinde = Counter()
        adet_w = 0.0
        for (ps, tekli, ikili), w in zip(satirlar, agirlik):
            if parca in ps:
                adet_w += w
                for k in set(tekli) | set(ikili):
                    icinde[k] += w
        puan = {}
        for k, say in icinde.items():
            destek = say / adet_w
            if destek < DESTEK_ESIK:
                continue
            ayirt = destek - (genel[k] - say) / max(n_w - adet_w, 1.0)
            if ayirt >= AYIRT_ESIK:
                puan[k] = (ayirt, destek)
        tekli = {k: v for k, v in puan.items() if " " not in k}
        if not tekli:
            continue
        # Esitlikte kisaltmanin harflerini SIRAYLA iceren kelime one gecer
        # (kisaltma harflerini sirayla tasiyan kelime).
        #
        sirali = sorted(tekli, key=lambda k: (-tekli[k][0], -tekli[k][1],
                                              -_harf_uyumu(parca, k), len(k), k))
        liste = []
        for en_iyi in sirali:
            sinir = tekli[en_iyi][0] - 0.05
            # IKI KELIMELIK IFADE yalniz iki kelimesi de bu kisaltmaya ozgu
            # ise (iki kelimelik kalip ad); tek kelime yedek olarak
            # hemen arkasinda kalir.
            for k in sorted(puan):
                ayirt = puan[k][0]
                if " " in k and en_iyi in k.split(" ") and ayirt >= sinir and all(
                        (tekli.get(p) or (0, 0))[0] >= sinir for p in k.split(" ")):
                    zayif = _ifade_zayif(yuzey[k])
                    if not zayif:
                        liste.append(k)
                    elif zayif == "tamlama" and k.split(" ")[1] in tekli:
                        # Iki kelimesi de ekli tamlama: anlam tamlamanin
                        # BASI, niteleyen degil.
                        liste.append(k.split(" ")[1])
                    break
            liste.append(en_iyi)
        goruldu, adaylar_ = set(), []
        for anahtar in liste:
            if anahtar in goruldu:
                continue
            goruldu.add(anahtar)
            bicimler = yuzey[anahtar]
            anlam = min(bicimler, key=lambda y: (len(y), -bicimler[y]))
            anlam = _korpus_yalin(yalin_anlam(anlam), sozcukler)
            ayirt, destek = puan[anahtar]
            adaylar_.append({"anlam": anlam, "destek": round(destek, 3),
                             "ayirt": round(ayirt, 3), "anahtar": anahtar})
        cikti[parca] = {"kolon": int(adet), "adaylar": adaylar_,
                        "tekli": {k: v[0] for k, v in tekli.items()}}
    return cikti


def _ifade_zayif(bicimler):
    """Iki kelimelik aday ifade kisaltma anlami OLAMAZ mi:
      - kelimelerden biri Turkce degil (shrink)
      - iki kelime de ekli (tamlama: "<A>i <B>si" = <A>in <B>si; bu bir
        aciklamadir, kisaltmanin anlami tek kelimedir)."""
    yuz = max(bicimler, key=lambda y: bicimler[y])
    kelimeler = yuz.split(" ")
    try:
        from fe_agent import llm as llm_mod
        if llm_mod.turkce_sorunu(yuz):
            return "dil"
    except Exception:
        pass
    if len(kelimeler) == 2 and all(_yalin_kelime(k) != k for k in kelimeler):
        return "tamlama"
    return ""


_TAMLAYAN = ("nın", "nin", "nun", "nün", "ın", "in", "un", "ün")


def _korpus_yalin(anlam, sozcukler):
    """Tamlayan ekli tek kelime ("gunun") yalin hali tanimlarda da
    geciyorsa yalina iner ("gun"). Yalnizca korpusta dogrulanan kok
    kullanilir: "yaygin", "butun" gibi kelimeler kesilmez."""
    a = str(anlam or "")
    if not a or " " in a:
        return a
    kume = {str(k).lower() for k in (sozcukler or ())}
    for ek in _TAMLAYAN:
        if a.endswith(ek) and len(a) - len(ek) >= 2 and a[:-len(ek)] in kume:
            return a[:-len(ek)]
    return a


def _harf_guclu(parca, a):
    """Kisaltmanin harfleri anlamda SIRAYLA geciyor ve anlam guclu
    (destek >= %90) mu."""
    return int(a["destek"] >= 0.9 and _harf_uyumu(parca, _sade(a["anlam"]).replace(" ", "")))


def cikar(tanimlar, aday=None):
    """{kolon: tanim} -> {KISALTMA: {"anlam", "kolon", "destek", "ayirt"}}.

    ATAMA BUTUN ADAYLAR UZERINDEN, en guclu kanittan zayifa. Sira: harfleri
    sirayla tutan guclu aday > ayirt (0.05'lik basamak) > ayni kisaltmada
    once gelen (iki kelimelik ifade tek kelimeden once) > kolon sayisi.
    Bir parca, birlikte gectigi parcaya verilmis ya da onayli anlami
    alamaz; aday kalmazsa listede yer almaz."""
    aday = adaylar(tanimlar) if aday is None else aday
    if not aday:
        return {}
    satirlar, parca_say, _g, _y, _s, _a = _parca_istatistigi(tanimlar)
    onay = onaylilar()
    atanan = {k: v for k, v in onay.items()}       # parca -> anlam
    birlikte = {}
    ciftler = []
    for parca, v in aday.items():
        if parca in onay:
            continue
        for sira_, a in enumerate(v["adaylar"]):
            ciftler.append((-_harf_guclu(parca, a), -int(round(a["ayirt"] / 0.05)),
                            sira_, -v["kolon"], parca, a))
    ciftler.sort(key=lambda c: c[:5])
    sonuc, dusen = {}, set()
    for _h, _ay, _sr, _k, parca, a in ciftler:
        if parca in sonuc or parca in dusen:
            continue
        if parca not in birlikte:
            birlikte[parca] = _birlikte(satirlar, parca, parca_say)
        yasak = set()
        for q in birlikte[parca]:
            if q in atanan:
                yasak |= _anlam_kelimeleri(atanan[q])
        if _yasakli(a["anlam"].split(" "), yasak):
            continue
        # IKI KELIMELIK IFADE baska bir kisaltmanin EN GUCLU tek kelime
        # adayini icerirse secilmez (iki kelimeden biri baska bir
        # kisaltmanin en guclu adayi).
        if " " in a.get("anahtar", "") and _baskasinin(a["anahtar"], parca, aday):
            continue
        # Kendini anlatan parca (parcanin kendisi Turkce bir kelime)
        # listeyi kalabaliklastirir: parca duser.
        if parca.lower() in _sade(a["anlam"]).split(" ") \
                or _sade(a["anlam"]).replace(" ", "") == parca.lower():
            dusen.add(parca)
            continue
        sonuc[parca] = {"anlam": a["anlam"], "kolon": aday[parca]["kolon"],
                        "destek": a["destek"], "ayirt": a["ayirt"]}
        atanan[parca] = a["anlam"]
    return sonuc


def _baskasinin(anahtar, parca, aday, pay=0.05):
    """Ifadenin bir kelimesi, baska bir parcanin en guclu TEK kelime
    adayi mi (o parcanin o kelimedeki ayirt'i bu parcanınkinden zayif
    degilse)."""
    benim = aday[parca].get("tekli") or {}
    for k in anahtar.split(" "):
        for q, a in aday.items():
            if q == parca:
                continue
            tekli = a.get("tekli") or {}
            if not tekli:
                continue
            #
            tepe = max(tekli.values())
            if k in tekli and tekli[k] >= tepe - 0.01 \
                    and tekli[k] >= benim.get(k, 0) - pay:
                return True
    return False


_YUMUSAK = {"d": "t", "ğ": "k", "b": "p", "c": "ç", "g": "k"}
_UNLU = set("aeıioöuü")
# Sonu i/ı/u/ü ile biten ama EK OLMAYAN kelimeler (kesilmez).
# karsi, arasi, sonu ...: yalin halleri ayri birer kelime.
_YALIN_ISTISNA = {"karşı", "arası", "sonu", "altı", "üstü", "önü", "içi", "dışı",
                  "yanı", "başı", "ortası", "kredi", "bilgi", "yeni", "eski", "ilgili", "ikili", "mali",
                  "resmi", "nakdi", "gayri", "tekli", "ilk", "fiili", "hissi",
                  "ölçü", "süreli", "güncel", "ortalama", "sayı"}
# Bu eklerle biten kelime sifattir ya da yapim ekidir; kesilmez.
_SIFAT_EKI = ("li", "lı", "lu", "lü", "ci", "cı", "cu", "cü", "çi", "çı", "çu",
              "çü", "ki", "si" + "z", "sız", "suz", "süz")


_UYUM = {"a": "ı", "ı": "ı", "e": "i", "i": "i", "o": "u", "u": "u", "ö": "ü", "ü": "ü"}


def _uyumlu_ek(govde, unlu):
    """Iyelik ekinin unlusu govdenin son unlusune uyuyor mu (dortlu unlu
    uyumu)? "skor"+"u" evet; "<kok>"+"i" govdenin son unlusu "o" iken HAYIR:
    kelime zaten yalin
"""
    for h in reversed(govde):
        if h in _UYUM:
            return _UYUM[h] == unlu
    return False


# Sonu c ile yumusayan ç'li kokler: "borcu" -> "borç". "-cı/-ci" sifat eki
# ile ayni yazildigi icin (yolcu, alıcı) yalniz bu kokler cevrilir.
_C_KOK = {"borç", "harç", "amaç", "güç", "kazanç", "sayaç", "ilaç", "ağaç",
          "taç", "uç"}


def _yalin_kelime(k, sozcukler=()):
    """Tek kelimeyi yalin hale getirir (kural tabanli Turkce ek atma):
    bayragi -> bayrak, skoru -> skor, adedi -> adet, orani -> oran,
    tutarinin -> tutar, odemesi -> odeme.
    Yalin hali sozlukte geciyorsa o tercih edilir."""
    k = str(k or "")
    if len(k) < 4 or k in _YALIN_ISTISNA:
        return k
    aday = k
    # 1) cogul + iyelik / tamlayan: "islemlerin", "islemleri", "islemler"
    for ek in ("larının", "lerinin", "ların", "lerin", "ları", "leri", "lar", "ler"):
        if aday.endswith(ek) and len(aday) - len(ek) >= 3:
            aday = aday[:-len(ek)]
            break
    # 2) tamlayan eki unluden sonra: "tutarının" -> "tutarı"
    for ek in ("nın", "nin", "nun", "nün"):
        if aday.endswith(ek) and len(aday) > 5 and aday[-4] in _UNLU:
            aday = aday[:-3]
            break
    # 3) iyelik "-sı" unluden sonra: "ödemesi" -> "ödeme"
    if len(aday) > 5 and aday[-2] == "s" and aday[-1] in "ıiuü" and aday[-3] in _UNLU \
            and _uyumlu_ek(aday[:-2], aday[-1]):
        aday = aday[:-2]
    # 4) "-ğı" -> "k": "bayrağı" -> "bayrak", "yoğunluğu" -> "yoğunluk"
    elif len(aday) >= 4 and aday[-2] == "ğ" and aday[-1] in "ıiuü" \
            and _uyumlu_ek(aday[:-2], aday[-1]):
        aday = aday[:-2] + "k"
    # 5a) "borcu" -> "borç" (bkz. _C_KOK)
    elif len(aday) >= 4 and aday[-2] == "c" and aday[-1] in "ıiuü" \
            and aday[:-2] + "ç" in _C_KOK:
        aday = aday[:-2] + "ç"
    # 5) unsuzden sonra iyelik "-ı": "skoru" -> "skor", "adedi" -> "adet"
    elif len(aday) >= 4 and aday[-1] in "ıiuü" and aday[-2] not in _UNLU \
            and not aday.endswith(_SIFAT_EKI) and aday not in _YALIN_ISTISNA \
            and _uyumlu_ek(aday[:-1], aday[-1]):
        govde = aday[:-1]
        if len(govde) >= 4 and govde[-1] in "bcd":
            govde = govde[:-1] + _YUMUSAK[govde[-1]]
        aday = govde
    return aday if len(aday) >= 2 else k


def _yalin(kelime, sozcukler):
    """Anlam kelimesini yalin hale getirir (bkz. _yalin_kelime)."""
    return _yalin_kelime(kelime, sozcukler)


def yalin_anlam(anlam):
    """Anlam metni: TEK kelimeyse yalina iner. Cok kelimeli anlamlar
    (iki kelimelik kalip adlar) birlesik addir; son
    kelimenin eki anlamin parcasidir, dokunulmaz."""
    a = str(anlam or "").strip()
    if not a or " " in a:
        return a
    return _yalin_kelime(a)




# ---------------------------------------------------------------------------
# ONAYLI KISALTMA HAFIZASI
# ---------------------------------------------------------------------------
def _bos():
    return pd.DataFrame(columns=KOLONLAR)


def _var_mi(dosya=DOSYA):
    klasor = _folder()
    yollar_ = [dosya] if dosya == DOSYA else tablo_io.aday_yollar(dosya)
    for yol in yollar_:
        try:
            if (klasor.get_path_details(yol) or {}).get("exists"):
                return True
            continue
        except Exception:
            pass
        try:
            yollar = set(klasor.list_paths_in_partition())
        except Exception:
            return None
        if yol in yollar or yol.lstrip("/") in yollar:
            return True
    return False


def _oku_ham(dosya=DOSYA, kolonlar=None):
    kolonlar = kolonlar or KOLONLAR
    try:
        df = tablo_io.klasorden_oku(_folder(), dosya)
    except Exception as e:
        if _var_mi(dosya) is False:
            return pd.DataFrame(columns=kolonlar), None
        return None, "Kısaltma hafızası okunamadı (%s)." % str(e)[:120]
    for k in kolonlar:
        if k not in df.columns:
            df[k] = ""
    return df[kolonlar].fillna("").astype(str), None


# YANLIS KISALTMA NOTU: yeni kisaltma kabul edilen
# satir hafizaya kaydedilirken eski kisaltma genel anlamiyla durur; KAYNAK
# sutununa "bu kolonlarda baska anlamda kullanildi" notu yazilir. Sonraki
# calismalarda istemde "kesin" degil "dikkat" olarak gider.
KAYNAK_YANLIS = "yanlış kısaltma"


def _hafiza_yaz(df):
    """Onayli hafiza JSON olarak yazilir: kisaltma -> anlam; KAYNAK'ta not
    varsa "notlar" altinda."""
    if "YENI" not in df.columns:
        df = df.assign(YENI="")
    df = df[(df["ANLAM"].str.strip() != "") | (df["YENI"].str.strip() != "")]
    df = df.sort_values("KISALTMA")
    govde = {"kisaltmalar": {k: a for k, a in zip(df["KISALTMA"], df["ANLAM"])
                             if str(a).strip()},
             "degisimler": {k: y for k, y in zip(df["KISALTMA"], df["YENI"])
                            if str(y).strip()},
             "notlar": {k: kay for k, kay in zip(df["KISALTMA"], df["KAYNAK"])
                        if str(kay).startswith(KAYNAK_YANLIS + ":")}}
    for anahtar in ("degisimler", "notlar"):
        if not govde[anahtar]:
            govde.pop(anahtar)
    _folder().upload_stream(DOSYA, json.dumps(govde, ensure_ascii=False, indent=2,
                                              sort_keys=True).encode("utf-8"))


def _hafiza_oku():
    """Doner: (df[KOLONLAR], hata). JSON yoksa eski Parquet bir kez JSON'a
    aktarilir ve silinir."""
    try:
        with _folder().get_download_stream(DOSYA) as akis:
            govde = json.loads(akis.read().decode("utf-8") or "{}")
    except Exception as e:
        var = _var_mi(DOSYA)
        if var is not False:
            return None, "Kısaltma hafızası okunamadı (%s)." % str(e)[:120]
        eski, hata = _oku_ham(ESKI_DOSYA)
        if eski is None:
            return None, hata
        if not eski.empty:
            try:
                _hafiza_yaz(eski)
                for yol in tablo_io.aday_yollar(ESKI_DOSYA):
                    try:
                        _folder().delete_path(yol)
                    except Exception:
                        pass
            except Exception as e2:
                return None, "Kısaltma hafızası JSON'a aktarılamadı (%s)." % str(e2)[:120]
        return eski, None
    if not isinstance(govde, dict):
        return None, "Kısaltma hafızası okunamadı (biçim)."
    notlar = govde.get("notlar") or {}
    degisim = {str(k).upper(): str(y).strip().upper()
               for k, y in (govde.get("degisimler") or {}).items() if str(y or "").strip()}
    satir = [{"KISALTMA": str(k).upper(), "ANLAM": str(a),
              "KAYNAK": str(notlar.get(k) or KAYNAK_ONAY), "KULLANICI": "", "TARIH": "",
              "YENI": degisim.pop(str(k).upper(), "")}
             for k, a in (govde.get("kisaltmalar") or {}).items() if str(a or "").strip()]
    satir += [{"KISALTMA": k, "ANLAM": "", "KAYNAK": KAYNAK_ONAY, "KULLANICI": "",
               "TARIH": "", "YENI": y} for k, y in degisim.items()]
    return pd.DataFrame(satir, columns=KOLONLAR), None


def onayli_notlar():
    """{KISA: (yeni_kisaltma, o kolonlardaki anlam)}: hafizadaki yanlis
    kisaltma notlari."""
    onaylilar()
    df = _ONBELLEK["df"]
    if df is None or df.empty:
        return {}
    cikti = {}
    for k, kay in zip(df["KISALTMA"].str.upper(), df["KAYNAK"].astype(str)):
        if kay.startswith(KAYNAK_YANLIS + ":"):
            yeni, _, anlam = kay[len(KAYNAK_YANLIS) + 1:].strip().partition("=")
            cikti[k] = (yeni.strip(), anlam.strip())
    return cikti


def yanlis_notu(yeni, anlam):
    return "%s: %s = %s" % (KAYNAK_YANLIS, yeni, anlam)


def _hafiza_df():
    """Onayli hafiza tablosu (onbellekli); okunamazsa son bilinen ya da None."""
    simdi = time.time()
    if _ONBELLEK["df"] is None or simdi - _ONBELLEK["zaman"] > ONBELLEK_OMRU_SN:
        df, _h = _hafiza_oku()
        if df is not None:
            _ONBELLEK.update(zaman=simdi, df=df)
    return _ONBELLEK["df"]


def onaylilar():
    """{KISALTMA: anlam} - onayli kisaltmalar (onbellekli)."""
    df = _hafiza_df()
    if df is None or df.empty:
        return {}
    anlam = df[df["ANLAM"].str.strip() != ""]
    cikti = dict(zip(anlam["KISALTMA"].str.upper(), anlam["ANLAM"]))
    # Degisimi not edilen kisaltma, yeni kisaltmanin anlamiyla onaylidir.
    for k, y in degisimler().items():
        if k not in cikti and cikti.get(y):
            cikti[k] = cikti[y]
    return cikti


def degisimler():
    """{ESKI: YENI} - hafizada not edilen kisaltma degisimleri."""
    df = _hafiza_df()
    if df is None or df.empty or "YENI" not in df.columns:
        return {}
    d = df[df["YENI"].str.strip() != ""]
    return dict(zip(d["KISALTMA"].str.upper(), d["YENI"].str.upper()))


def kaydet(satirlar, kullanici=""):
    """satirlar: [{"kisaltma", "anlam", "kaydet": bool, "kaynak", "yeni"}].
    kaydet=True -> eklenir / guncellenir; False -> hafizada varsa silinir.
    "yeni" doluysa yalniz degisim (kisaltma -> yeni) yazilir; anlam yeni
    kisaltmanin kendi satirindadir.
    Doner: (onayli_sozluk, hata). Istisna firlatmaz."""
    zaman = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _KILIT:
        df, hata = _hafiza_oku()
        if df is None:
            return onaylilar(), hata
        df = df.copy()
        if "YENI" not in df.columns:
            df["YENI"] = ""
        df["KISALTMA"] = df["KISALTMA"].str.upper()
        for s in satirlar or []:
            if not isinstance(s, dict):
                continue
            kisa = str(s.get("kisaltma") or "").strip().upper()
            anlam = str(s.get("anlam") or "").strip()
            yeni = str(s.get("yeni") or "").strip().upper()
            if yeni == kisa:
                yeni = ""
            if not kisa:
                continue
            df = df[df["KISALTMA"] != kisa]
            if s.get("kaydet") and (anlam or yeni):
                df = pd.concat([df, pd.DataFrame([{
                    "KISALTMA": kisa, "ANLAM": "" if yeni else anlam,
                    "KAYNAK": str(s.get("kaynak") or KAYNAK_ONAY),
                    "KULLANICI": str(kullanici or ""), "TARIH": zaman,
                    "YENI": yeni}], columns=KOLONLAR)], ignore_index=True)
        try:
            _hafiza_yaz(df)
        except Exception as e:
            return onaylilar(), "Kısaltma hafızasına yazılamadı (%s)." % str(e)[:120]
        _ONBELLEK.update(zaman=time.time(), df=df)
    return onaylilar(), None




# ---------------------------------------------------------------------------
# OGRENILMIS BILGI
# ---------------------------------------------------------------------------
# PROJE_HAFIZASI/KISALTMA_OGRENILEN.json: sozluklu her calismada
# istatistik + dil modeli kontrolunden GECEN anlamlar KENDILIGINDEN yazilir
# (onay istemez; onayli hafizadan ayri). Sozlugu olmayan ya da az tanimli
# sonraki calismalarda "tahmini" olarak kullanilir. Ayni kisaltma baska
# sozlukte farkli anlamla cikarsa DAHA COK KOLONLA ogrenilen kalir.
# Onayli hafiza her zaman bunun onune gecer. Girdi veri setine ve
# sozluge hicbir kosulda yazilmaz.
OGRENILEN_DOSYA = "/KISALTMA_OGRENILEN.json"
OGRENILEN_KOLONLAR = ["KISALTMA", "ANLAM", "KOLON", "VERI_SETI", "KAYNAK", "TARIH"]
_OGR_ONBELLEK = {"zaman": 0.0, "df": None}


def ogrenilenler():
    """{KISA: {"anlam", "kolon", "veri_seti", "tarih"}} (onbellekli)."""
    simdi = time.time()
    if _OGR_ONBELLEK["df"] is None or simdi - _OGR_ONBELLEK["zaman"] > ONBELLEK_OMRU_SN:
        df, _h = _oku_ham(OGRENILEN_DOSYA, OGRENILEN_KOLONLAR)
        if df is not None:
            _OGR_ONBELLEK.update(zaman=simdi, df=df)
    df = _OGR_ONBELLEK["df"]
    if df is None or df.empty:
        return {}
    cikti = {}
    for _i, r_ in df.iterrows():
        if str(r_["ANLAM"]).strip():
            try:
                kolon = int(float(r_["KOLON"] or 0))
            except (TypeError, ValueError):
                kolon = 0
            cikti[str(r_["KISALTMA"]).upper()] = {
                "anlam": r_["ANLAM"], "kolon": kolon,
                "veri_seti": r_["VERI_SETI"], "tarih": r_["TARIH"]}
    return cikti


def ogrenilenleri_kaydet(kayitlar, veri_seti=""):
    """kayitlar: {KISA: {"anlam", "kolon", "kaynak"}}. Var olan kayit
    yalniz yeni kanit en az onun kadar gucluyse (kolon sayisi) ya da anlam
    ayniysa guncellenir. Doner: (yazilan, hata). Istisna firlatmaz."""
    if not kayitlar:
        return 0, None
    zaman = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _KILIT:
        df, hata = _oku_ham(OGRENILEN_DOSYA, OGRENILEN_KOLONLAR)
        if df is None:
            return 0, hata
        mevcut = {}
        for _i, r_ in df.iterrows():
            try:
                mevcut[str(r_["KISALTMA"]).upper()] = (str(r_["ANLAM"]), int(float(r_["KOLON"] or 0)))
            except (TypeError, ValueError):
                mevcut[str(r_["KISALTMA"]).upper()] = (str(r_["ANLAM"]), 0)
        yeni, yazilan = [], 0
        for kisa, k in kayitlar.items():
            kisa = str(kisa).upper()
            anlam = str(k.get("anlam") or "").strip()
            kolon = int(k.get("kolon") or 0)
            if not anlam:
                continue
            eski = mevcut.get(kisa)
            if eski and not _ayni_anlam(eski[0], anlam) and eski[1] > kolon:
                continue                      # daha guclu eski kanit kalir
            if eski and _ayni_anlam(eski[0], anlam):
                kolon = max(kolon, eski[1])
            yeni.append({"KISALTMA": kisa, "ANLAM": anlam, "KOLON": str(kolon),
                         "VERI_SETI": str(veri_seti or ""),
                         "KAYNAK": str(k.get("kaynak") or ""), "TARIH": zaman})
            yazilan += 1
        if not yeni:
            return 0, None
        df = df[~df["KISALTMA"].str.upper().isin([y["KISALTMA"] for y in yeni])]
        df = pd.concat([df, pd.DataFrame(yeni, columns=OGRENILEN_KOLONLAR)],
                       ignore_index=True).sort_values("KISALTMA")
        try:
            tablo_io.klasore_yaz(_folder(), OGRENILEN_DOSYA, df)
        except Exception as e:
            return 0, "Öğrenilen kısaltmalar yazılamadı (%s)." % str(e)[:120]
        _OGR_ONBELLEK.update(zaman=time.time(), df=df)
    return yazilan, None


def kalici_ogren(tanimlar, veri_seti="", bekle=300.0):
    """KENDINI GELISTIRME: Kolon Adi Onerileri tamamlaninca (duzeltmeler uygulandiktan ya da
    kontrol atlandiktan sonra) DUZELTILMIS calisma kopyasi + onayli
    tanimlar uzerinde ogrenme calisir ve dil modeli kontrolunden gecen
    anlamlar (dogrulanan / modellerin anlastigi) ogrenilmis bilgiye yazilir.
    Arka planda calisir; kullaniciyi bekletmez, hata akisi durdurmaz."""
    if not tanimlar:
        return

    def is_():
        try:
            _s, durum = dogrulama_sonucu(tanimlar, bekle, veri_seti)
            if durum != "bitti":
                return
            oner, _d = oneriler(tanimlar, 0.0, veri_seti)
            ogrenilenleri_kaydet(
                {k: {"anlam": o["anlam"], "kolon": o.get("kolon") or 0,
                     "kaynak": o["kaynak"]}
                 for k, o in oner.items()
                 if o["anlam"] and not o.get("uyari")
                 and o["kaynak"] in ("dil_modeli_dogruladi", "dil_modeli")},
                veri_seti)
        except Exception:
            pass
    threading.Thread(target=is_, daemon=True).start()


# ---------------------------------------------------------------------------
# 2) CELISKI - cogunluk azinligi duzeltir (kod tarafinda, dil modeli yok)
# ---------------------------------------------------------------------------
CELISKI_PAY = 0.85     # kisaltmanin kolonlarinin en az bu kadari anlami tasimali
CELISKI_EN_AZ = 5      # ... ve en az bu kadar tanimli kolon olmali


def _anlami_tasir(tanim, anlam):
    """Tanim, anlamin her kelimesini (yalin ya da ekli) iceriyor mu."""
    tk = [_sade(k) for k in re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü]+", str(tanim or ""))]
    for a in str(anlam or "").split():
        a = _sade(a)
        if len(a) < 2:
            continue
        kok = a[:max(3, len(a) - 1)]          # "adet" -> "ade" (adedi de tutsun)
        if not any(k.startswith(kok) for k in tk):
            return False
    return True


GENEL_PAY = 0.30   # tanimlarin bundan fazlasinda gecen kelime genel sayilir (islem, son)


def _kelime_tokenlari(tanim):
    return [_sade(k) for k in re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü]+", str(tanim or ""))]


def _kelime_eslesir(k, a):
    """Tanim kelimesi k, anlam kelimesi a ile eslesir mi (ek payi ile)."""
    a = _sade(a)
    kok = a[:max(2, len(a) - 1)] if len(a) > 3 else a
    return k.startswith(kok)


def _yeni_ad_oner(ad, kisa, anlam, tanim, anlamlar):
    """Kolon adina kisa'yi ekleyen ad onerisi: anlamin tanimda hemen
    ARDINDAN gelen ve adda karsiligi olan kisaltmanin ONUNE eklenir
    (aciklamadaki kelime sirasina gore). Bulunamazsa
    sona eklenir."""
    tok = _kelime_tokenlari(tanim)
    ilk = _sade(anlam.split()[0])
    try:
        yer = next(i for i, k in enumerate(tok) if _kelime_eslesir(k, ilk))
    except StopIteration:
        yer = -1
    parcalar_ = str(ad).split("_")
    if yer >= 0:
        for sonraki in tok[yer + len(anlam.split()):]:
            for i, p in enumerate(parcalar_):
                m = anlamlar.get(p.upper())
                if m and any(_kelime_eslesir(sonraki, a) for a in m.split()):
                    return "_".join(parcalar_[:i] + [kisa] + parcalar_[i:])
    return "_".join(parcalar_ + [kisa])


def tutarsizliklar(tanimlar, anlamlar=None):
    """ACIKLAMA ile KOLON ADI arasindaki tutarsizliklar. Iki yonlu, kod tarafinda:

      tanimda_yok: adda kisaltma var, aciklamada anlami yok (kisaltmanin
                   kolonlarinin en az CELISKI_PAY kadari anlami tasiyorsa)
      adda_yok   : aciklamada bir kisaltmanin anlami geciyor, adda o
                   kisaltma da, ayni anlami veren baska bir kisaltma da
                   yok (anlami adda baska bir kisaltma zaten veriyorsa
                   aranmaz). Genel kelimeler (tanimlarin %30'undan
                   fazlasinda gecen) sayilmaz.

    Doner: {kolon: [{"tur", "kisaltma", "anlam", "gerekce", "yeni_ad"}]}"""
    if anlamlar is None:
        oner, _d = oneriler(tanimlar, 0.0)
        anlamlar = {k: o["anlam"] for k, o in oner.items() if o["anlam"]}
        anlamlar.update(onaylilar())
    tanimli = {ad: t for ad, t in (tanimlar or {}).items() if str(t or "").strip()}
    if not tanimli or not anlamlar:
        return {}
    toklar = {ad: _kelime_tokenlari(t) for ad, t in tanimli.items()}
    adlar_parca = {ad: parcalar(ad) for ad in tanimli}
    # Kelime belge sikligi (genel kelime eleme).
    df_ = Counter()
    for tk in toklar.values():
        df_.update(set(tk))
    n = float(len(tanimli))

    def tasir(ad, anlam):
        return all(any(_kelime_eslesir(k, a) for k in toklar[ad])
                   for a in anlam.split() if len(a) >= 2)

    # Kisaltmanin kalibi guclu mu (kolonlarinin cogu anlami tasiyor mu).
    guclu = {}
    for kisa, anlam in anlamlar.items():
        kolonlar = [ad for ad in tanimli if kisa in adlar_parca[ad]]
        if len(kolonlar) < CELISKI_EN_AZ:
            continue
        tasiyan = sum(1 for ad in kolonlar if tasir(ad, anlam))
        guclu[kisa] = (tasiyan / float(len(kolonlar)), len(kolonlar))

    def genel(anlam):
        return all(max([df_[k] for k in df_ if _kelime_eslesir(k, a)] or [0]) / n > GENEL_PAY
                   for a in anlam.split() if len(a) >= 2)

    cikti = {}
    for ad in tanimli:
        ps = set(adlar_parca[ad])
        for kisa, (pay, adet) in guclu.items():
            anlam = anlamlar[kisa]
            if pay < CELISKI_PAY:
                continue
            if kisa in ps:
                if pay < 1.0 and not tasir(ad, anlam):
                    cikti.setdefault(ad, []).append({
                        "tur": "tanimda_yok", "kisaltma": kisa, "anlam": anlam, "yeni_ad": "",
                        "gerekce": "Kolon adındaki %s, sözlükteki %d kolonun %s '%s' "
                                   "anlamında kullanılmış; bu açıklamada '%s' geçmiyor."
                                   % (kisa, adet, yuzdesinde(pay * 100), anlam, anlam)})
                continue
            if genel(anlam) or not tasir(ad, anlam):
                continue
            # Adda AYNEN tanimda gecen bir parca varsa yanindaki kelimeler o
            # parcanin aciklamasidir; onlar icin baska kisaltma aranmaz.
            tk = toklar[ad]
            yakin = set()
            for i, k in enumerate(tk):
                if k.upper() in ps:
                    yakin.update(tk[max(0, i - 2):i + 3])
            if yakin and all(any(_kelime_eslesir(k, a) for k in yakin)
                             for a in anlam.split() if len(a) >= 2):
                continue
            # Kardes kisaltma adda varsa (ilk 5 harfi ortak iki kisaltma)
            # anlam ondan geliyor olabilir; isaretlenmez.
            if any(len(p) >= 5 and p[:5] == kisa[:5] for p in ps):
                continue
            # Adda ayni anlami veren baska kisaltma var mi (PER "ortalama").
            kelimeler = [a for a in anlam.split() if len(a) >= 2]
            if any(any(_kelime_eslesir(_sade(a2), a) or _kelime_eslesir(_sade(a), a2)
                       for a in kelimeler for a2 in (anlamlar.get(p) or "").split())
                   for p in ps):
                continue
            yeni = _yeni_ad_oner(ad, kisa, anlam, tanimli[ad], anlamlar)
            cikti.setdefault(ad, []).append({
                "tur": "adda_yok", "kisaltma": kisa, "anlam": anlam, "yeni_ad": yeni,
                "gerekce": "Açıklamada '%s' geçiyor (sözlükte %d kolonda %s'nin anlamı); "
                           "kolon adında %s yok. Ya açıklama düzeltilmeli ya da kolon "
                           "adı %s olmalı." % (anlam, adet, kisa, kisa, yeni)})
    return cikti


def celiskiler(tanimlar, anlamlar=None):
    """Tanim kontrolu icin: {kolon: [gerekce, ...]} (bkz. tutarsizliklar)."""
    return {ad: [t["gerekce"] for t in liste]
            for ad, liste in tutarsizliklar(tanimlar, anlamlar).items()}


# ---------------------------------------------------------------------------
# DIL MODELI - arka planda, onbellekli
# ---------------------------------------------------------------------------
ORNEK_SAYISI = 8          # kisaltma basina modele giden en cok ornek kolon
DM_BEKLE_SN = 25.0        # kart kurulurken sonucu en cok bu kadar bekler
_DM = {}                  # imza -> {"durum", "sonuc", "zaman"}
_DM_KILIT = threading.Lock()


def _ornekler(tanimlar, parca):
    """CESITLI ornek: her adimda, secilenlerde henuz gecmeyen en cok
    parcayi getiren kolon secilir."""
    havuz = [(ad, str(t)[:160], set(parcalar(ad)))
             for ad, t in (tanimlar or {}).items()
             if str(t or "").strip() and parca in parcalar(ad)]
    if not havuz:
        # Yalniz tanimsiz kolonlarda geciyor: adlar baglam olarak gider.
        havuz = [(ad, "(tanım yok)", set(parcalar(ad)))
                 for ad in (tanimlar or {}) if parca in parcalar(ad)]
    secilen, gorulen = [], set([parca])
    while havuz and len(secilen) < ORNEK_SAYISI:
        en = max(range(len(havuz)), key=lambda i: (len(havuz[i][2] - gorulen), -i))
        ad, t, ps = havuz.pop(en)
        secilen.append((ad, t))
        gorulen |= ps
    return secilen


def _dm_girdisi(tanimlar):
    """Modele sorulacak kisaltmalar: kolon adlarinda (tanimli ya da
    tanimsiz) gecen ve onayli olmayan HER parca; esik ve ust sinir yok."""
    aday = adaylar(tanimlar)
    cikan = cikar(tanimlar, aday)
    onay = onaylilar()
    say = Counter(p for ad in (tanimlar or {}) for p in set(parcalar(ad)))
    girdi = []
    for parca, adet in say.most_common():
        if parca in onay:
            continue
        ornek = _ornekler(tanimlar, parca)
        # Orneklerdeki DIGER kisaltmalarin YALNIZ ONAYLI anlamlari
        #
        diger = {}
        for ad, _t in ornek:
            for p in parcalar(ad):
                if p != parca and onay.get(p):
                    diger[p] = onay[p]
        girdi.append({"kisaltma": parca, "kolon": int(adet),
                      "bicimler": sayili_degerler(tanimlar, parca),
                      "anlam": (cikan.get(parca) or {}).get("anlam", ""),
                      "adaylar": (aday.get(parca) or {}).get("adaylar", [])[:ADAY_SAYISI],
                      "ornekler": ornek, "bilinen": diger})
    return girdi


def _imza(girdi):
    return "|".join("%s=%s" % (g["kisaltma"], g["anlam"]) for g in girdi)


def _dm_calis(imza, girdi, tanimlar=None, veri_seti=""):
    hata = ""
    ornek_say_ = {g["kisaltma"]: len(g["ornekler"]) for g in girdi}

    def ara(parca, anahtarlar):
        """Parca bitti: sonuclari hemen yaz, o kisaltmalar artik beklemiyor."""
        with _DM_KILIT:
            k = _DM.get(imza)
            if not k or k.get("durum") != "calisiyor":
                return
            for kisa, v in parca.items():
                v = dict(v, ornek=ornek_say_.get(kisa, 0))
                k["sonuc"][kisa] = v
            k["bekleyen"] = set(k.get("bekleyen") or ()) - set(anahtarlar)
    try:
        from fe_agent import llm as llm_mod
        sonuc, hata = llm_mod.kisaltma_dogrula(girdi, ara=ara)
    except Exception as e:
        sonuc, hata = None, "%s: %s" % (type(e).__name__, str(e)[:160])
    ornek_say = {g["kisaltma"]: len(g["ornekler"]) for g in girdi}
    for k, v in (sonuc or {}).items():
        v["ornek"] = ornek_say.get(k, 0)
    # Kisaltma sonuclari kartta hemen gorunsun; birlestirme sorusu ardindan.
    with _DM_KILIT:
        k_ = _DM.get(imza)
        if k_ and k_.get("durum") == "calisiyor":
            k_["sonuc"] = dict(sonuc or k_.get("sonuc") or {})
            k_["bekleyen"] = set()
    # Birlestirme sorusu BURADA DEGIL: kisaltmalar onaylandiktan sonra
    # ayri adimda, onaylanan anlamlarla (bkz. birlesik_baslat).
    with _DM_KILIT:
        if (_DM.get(imza) or {}).get("iptal"):
            return                      # kullanici durdurdu; o anki sonuc kalir
        _DM[imza] = {"durum": "bitti" if sonuc is not None else "hata",
                     "sonuc": sonuc or {}, "zaman": time.time(),
                     "hata": str(hata or ""), "sure": round(time.time() - _DM.get(imza, {}).get("zaman", time.time()))}
    # KALICI YAZMA BURADA DEGIL: Kolon Adi Onerileri tamamlaninca, DUZELTILMIS calisma
    # kopyasindan yapilir (bkz. kalici_ogren). Ham sozlukten ogrenilen
    # dosyaya yazilmaz.


def _birlesik_girdisi(tanimlar, anlamlar):
    """Hep yan yana gecen ciftler + parcalarin anlamlari + ornek kolonlar."""
    tanimli = {ad: t for ad, t in (tanimlar or {}).items() if str(t or "").strip()}
    aday = ifade_adaylari(list(tanimli), tek_taraf=True)
    girdi = []
    for (a, b), n in sorted(aday.items(), key=lambda x: (-x[1], x[0]))[:BIRLESIK_EN_COK]:
        ornek = []
        for ad, t in tanimli.items():
            ham = _ham_parcalar(ad)
            if any(x == a and y == b for x, y in zip(ham, ham[1:])):
                ornek.append((ad, str(t)[:160]))
            if len(ornek) >= 5:
                break
        girdi.append({"ad": "%s_%s" % (a, b), "parcalar": [a, b], "kolon": int(n),
                      "anlamlar": [anlamlar.get(a, ""), anlamlar.get(b, "")],
                      "ornekler": ornek})
    return girdi


def _birlesik_sor(tanimlar, anlamlar):
    """Dil modeline birlestirme sorusu, KULLANICININ ONAYLADIGI anlamlarla
    (01.2.5.Onaylanmamis anlamlarla birlestirme
    onerilmez). Doner: {"A_B": {"anlam", "yeni_kisaltma", "gerekce", "oy",
    "parcalar", "kolon", "ayri"}} (yalniz birlestirme onerilenler)."""
    ciftler = _birlesik_girdisi(tanimlar, anlamlar)
    if not ciftler:
        return {}
    from fe_agent import llm as llm_mod
    say = Counter(p for ad, t in (tanimlar or {}).items() if str(t or "").strip()
                  for p in set(parcalar(ad)))
    yaygin = [p for p, _n in say.most_common(20)]
    kalip = ("ADLANDIRMA KALIBI (kolon adlarinda en sik gecen kisaltmalar): %s\n"
             % ", ".join(yaygin)) if yaygin else ""
    kalip = llm_mod.dil_satiri(llm_mod.adlandirma_dili(anlamlar, say)) + kalip
    oner, hata = llm_mod.kisaltma_birlesik(ciftler, kalip=kalip)
    if hata:
        raise RuntimeError(hata)
    cikti = {}
    for g in ciftler:
        o = (oner or {}).get(g["ad"])
        if o:
            cikti[g["ad"]] = dict(o, parcalar=list(g["parcalar"]), kolon=g["kolon"],
                                  ayri=" + ".join(x or BOS_ANLAM for x in g["anlamlar"]))
    return cikti


BOS_ANLAM = "?"


_BIR = {}                 # imza -> {"durum", "sonuc", "hata", "zaman"}


def birlesik_adaylari_var(tanimlar):
    tanimli = [ad for ad, t in (tanimlar or {}).items() if str(t or "").strip()]
    return bool(ifade_adaylari(tanimli, tek_taraf=True)) or bool(birlesik_hafiza(tanimli))


def birlesik_baslat(tanimlar, anlamlar):
    """Birlestirme sorusunu arka planda baslatir (ayni anlamlar icin bir
    kez). Doner: imza."""
    anlamlar = {k: v for k, v in (anlamlar or {}).items() if v and "_" not in k}
    tanimli = sorted(ad for ad, t in (tanimlar or {}).items() if str(t or "").strip())
    imza = "%d|%s" % (len(tanimli), "|".join("%s=%s" % kv for kv in sorted(anlamlar.items())))
    with _DM_KILIT:
        k = _BIR.get(imza)
        if k and k["durum"] in ("calisiyor", "bitti"):
            return imza
        _BIR[imza] = {"durum": "calisiyor", "sonuc": {}, "hata": "", "zaman": time.time()}
        if len(_BIR) > 20:
            for eski in sorted(_BIR, key=lambda x: _BIR[x]["zaman"])[:len(_BIR) - 20]:
                if _BIR[eski]["durum"] != "calisiyor":
                    _BIR.pop(eski, None)

    def is_():
        try:
            sonuc, hata = _birlesik_sor(dict(tanimlar or {}), anlamlar), ""
        except Exception as e:
            sonuc, hata = {}, str(e)[:200]
        with _DM_KILIT:
            if (_BIR.get(imza) or {}).get("iptal"):
                return                  # kullanici durdurdu; sonuc kullanilmaz
            _BIR[imza] = {"durum": "bitti" if not hata else "hata", "sonuc": sonuc,
                          "hata": hata, "zaman": time.time()}
    threading.Thread(target=is_, daemon=True).start()
    return imza


# ---------------------------------------------------------------------------
# KOLON ADI TAMAMLAMA (arka plan): tanimda gecen ama adda karsiligi olmayan
# kavram ada eklenir (bkz. llm.kolon_ad_tamamla). Sonuclar parca bittikce
# yazilir; kart yoklayarak alir.
# ---------------------------------------------------------------------------
_KAD = {}                 # imza -> {"durum", "sonuc", "bekleyen", "toplam", ...}


def _kad_imza(girdi, onayli):
    import hashlib
    metin = "|".join("%s=%s" % (g["ad"], g.get("tanim") or "") for g in girdi) \
        + "#" + "|".join("%s=%s" % kv for kv in sorted((onayli or {}).items()))
    return hashlib.md5(metin.encode("utf-8")).hexdigest()


def kolon_ad_baslat(girdi, onayli, kalip=""):
    """Kolon adi tamamlamayi arka planda baslatir (ayni girdi icin bir kez).
    Doner: imza."""
    imza = _kad_imza(girdi, onayli)
    with _DM_KILIT:
        k = _KAD.get(imza)
        if k and k["durum"] in ("calisiyor", "bitti"):
            return imza
        _KAD[imza] = {"durum": "calisiyor", "sonuc": {}, "hata": "", "zaman": time.time(),
                      "toplam": len(girdi), "bekleyen": set(g["ad"] for g in girdi)}
        if len(_KAD) > 10:
            for eski in sorted(_KAD, key=lambda x: _KAD[x]["zaman"])[:len(_KAD) - 10]:
                if _KAD[eski]["durum"] != "calisiyor":
                    _KAD.pop(eski, None)

    def ara(parca, adlar):
        with _DM_KILIT:
            k_ = _KAD.get(imza)
            if not k_ or k_.get("durum") != "calisiyor":
                return
            k_["sonuc"].update(parca)
            k_["bekleyen"] = set(k_.get("bekleyen") or ()) - set(adlar)

    def iptal():
        with _DM_KILIT:
            return (_KAD.get(imza) or {}).get("durum") != "calisiyor"

    def is_():
        try:
            from fe_agent import llm as llm_mod
            sonuc, hata = llm_mod.kolon_ad_tamamla(girdi, onayli, kalip, ara=ara, iptal=iptal)
        except Exception as e:
            sonuc, hata = None, "%s: %s" % (type(e).__name__, str(e)[:160])
        with _DM_KILIT:
            k_ = _KAD.get(imza) or {}
            if k_.get("iptal"):
                return
            _KAD[imza] = {"durum": "bitti" if sonuc is not None else "hata",
                          "sonuc": dict(sonuc or k_.get("sonuc") or {}), "hata": str(hata or ""),
                          "zaman": time.time(), "toplam": len(girdi), "bekleyen": set(),
                          "sure": round(time.time() - k_.get("zaman", time.time()))}
    threading.Thread(target=is_, daemon=True).start()
    return imza


def kolon_ad_durumu(imza):
    """{"durum", "sonuc", "hata", "gecen", "toplam", "biten", "iptal"}."""
    with _DM_KILIT:
        k = dict(_KAD.get(imza) or {})
    calisiyor = k.get("durum") == "calisiyor"
    toplam = int(k.get("toplam") or 0)
    return {"durum": k.get("durum", "yok"), "sonuc": dict(k.get("sonuc") or {}),
            "hata": k.get("hata", ""), "iptal": bool(k.get("iptal")),
            "kalan": int(k.get("kalan") or 0),
            "gecen": int(time.time() - k["zaman"]) if calisiyor and k.get("zaman") else 0,
            "toplam": toplam,
            "biten": toplam - len(k.get("bekleyen") or ()) if calisiyor else toplam}


def kolon_ad_iptal(imza):
    """Suren tamamlamayi durdurur; gelen oneriler kalir."""
    with _DM_KILIT:
        k = _KAD.get(imza)
        if not k or k.get("durum") != "calisiyor":
            return False
        _KAD[imza] = dict(k, durum="bitti", iptal=True, bekleyen=set(),
                          kalan=len(k.get("bekleyen") or ()))
    return True


def birlesik_bilgisi(tanimlar, anlamlar):
    """{"gecen": calisan sorunun baslangicindan beri gecen sn, "iptal"}."""
    imza = birlesik_baslat(tanimlar, anlamlar)
    with _DM_KILIT:
        k = dict(_BIR.get(imza) or {})
    calisiyor = k.get("durum") == "calisiyor"
    return {"gecen": int(time.time() - k["zaman"]) if calisiyor and k.get("zaman") else 0,
            "iptal": bool(k.get("iptal"))}


def birlesik_iptal(tanimlar, anlamlar):
    """Suren birlestirme sorusunu durdurur; oneri gelmez, elle ekleme acik."""
    imza = birlesik_baslat(tanimlar, anlamlar)
    with _DM_KILIT:
        k = _BIR.get(imza)
        if not k or k.get("durum") != "calisiyor":
            return False
        _BIR[imza] = {"durum": "bitti", "sonuc": {}, "hata": "", "iptal": True,
                      "zaman": time.time()}
    return True


def birlesik_onerileri(tanimlar, anlamlar):
    """Kart icin: (oneriler, durum, hata). durum "calisiyor" / "bitti" /
    "hata". oneriler: [{"kisaltma": "A_B", "parcalar", "ayri", "anlam",
    "yeni_kisaltma", "gerekce", "kolon", "onayli", "ornekler"}]. Hafizada
    onayli birlestirme (hafizada "A_B" anahtari) dil modeli onermese de
    listelenir, isaretli gelir."""
    imza = birlesik_baslat(tanimlar, anlamlar)
    with _DM_KILIT:
        k = dict(_BIR.get(imza) or {})
    oner = dict(k.get("sonuc") or {})
    onay = onaylilar()
    tanimli = [ad for ad, t in (tanimlar or {}).items() if str(t or "").strip()]
    aday = ifade_adaylari(tanimli)
    for (a, b), n in aday.items():
        ad = "%s_%s" % (a, b)
        if ad in onay and ad not in oner:
            oner[ad] = {"anlam": onay[ad], "gerekce": "", "parcalar": [a, b], "kolon": int(n),
                        "ayri": ""}
    # Kullanicinin ELLE ekleyip hafizaya kaydettigi birlestirmeler.
    for ad, n in birlesik_hafiza(tanimli, onay).items():
        if ad not in oner:
            oner[ad] = {"anlam": onay[ad], "gerekce": "", "parcalar": ad.split("_"),
                        "kolon": int(n), "ayri": ""}
    cikti = []
    tanimli_d = {a: str(tanimlar[a]) for a in tanimli}
    for ad, o in sorted(oner.items(), key=lambda x: (-int(x[1].get("kolon") or 0), x[0])):
        # KARAR ICIN ORNEK: parcalarin yan yana gectigi
        # en cok BIRLESIK_ORNEK kolon ve sozlukteki aciklamalari; cesitli
        # secilir (her yeni ornek, oncekilerde olmayan parcalari getirir).
        havuz = [(kol, t, set(parcalar(kol))) for kol, t in tanimli_d.items()
                 if yan_yana(kol, ad)]
        ornek, gorulen = [], set(ad.split("_"))
        while havuz and len(ornek) < BIRLESIK_ORNEK:
            en = max(range(len(havuz)), key=lambda i: (len(havuz[i][2] - gorulen), -i))
            kol, t, ps = havuz.pop(en)
            ornek.append({"kolon": kol, "tanim": t[:200]})
            gorulen |= ps
        cikti.append({"kisaltma": ad, "parcalar": o.get("parcalar") or ad.split("_", 1),
                      "ornekler": ornek,
                      # Hafizada not edilen degisim (A_B -> YENI) once gelir.
                      "yeni_kisaltma": ((degisimler().get(ad) if ad in onay else "")
                                        or o.get("yeni_kisaltma") or ""),
                      "oy": o.get("oy") or 0,
                      "ayri": o.get("ayri") or " + ".join(
                          (anlamlar or {}).get(p) or BOS_ANLAM
                          for p in (o.get("parcalar") or ad.split("_"))),
                      "anlam": onay.get(ad) or o.get("anlam") or "",
                      "oneri_anlam": o.get("anlam") or "",
                      "gerekce": o.get("gerekce") or "", "kolon": int(o.get("kolon") or 0),
                      "onayli": ad in onay})
    return cikti, k.get("durum") or "yok", k.get("hata") or ""


def dogrulamayi_baslat(tanimlar, veri_seti=""):
    """Dil modeli kontrolunu arka planda baslatir (ayni liste icin bir kez).
    Bitince dogrulanan anlamlar ogrenilmis bilgiye yazilir.
    Doner: imza."""
    girdi = _dm_girdisi(tanimlar)
    imza = _imza(girdi)
    if not girdi:
        return imza
    with _DM_KILIT:
        k = _DM.get(imza)
        if k and k["durum"] in ("calisiyor", "bitti"):
            return imza
        _DM[imza] = {"durum": "calisiyor", "sonuc": {}, "zaman": time.time(),
                     "toplam": len(girdi),
                     "bekleyen": set(g["kisaltma"] for g in girdi)}
        if len(_DM) > 20:                       # eski kayitlari kirp
            for eski in sorted(_DM, key=lambda x: _DM[x]["zaman"])[:len(_DM) - 20]:
                if _DM[eski]["durum"] != "calisiyor":
                    _DM.pop(eski, None)
    threading.Thread(target=_dm_calis, args=(imza, girdi, dict(tanimlar or {}), veri_seti),
                     daemon=True).start()
    return imza


def bekleyenler(tanimlar, veri_seti=""):
    """Dil modeli sonucu HENUZ gelmemis kisaltmalar (kontrol suruyorsa)."""
    imza = dogrulamayi_baslat(tanimlar, veri_seti)
    with _DM_KILIT:
        k = _DM.get(imza) or {}
        if k.get("durum") != "calisiyor":
            return set()
        return set(k.get("bekleyen") or ())


def dogrulama_iptal(tanimlar, veri_seti=""):
    """Suren dil modeli kontrolunu durdurur: o ana kadar gelen sonuclar
    kalir, gelmeyen kisaltmalar sozluk sayimiyla gosterilir. Sunucuda
    baslamis cagrilar arka planda bitebilir; sonuclari kullanilmaz.
    Doner: durduruldu mu."""
    imza = _imza(_dm_girdisi(tanimlar))
    with _DM_KILIT:
        k = _DM.get(imza)
        if not k or k.get("durum") != "calisiyor":
            return False
        _DM[imza] = {"durum": "bitti", "sonuc": dict(k.get("sonuc") or {}),
                     "zaman": time.time(), "hata": "", "iptal": True,
                     "kalan": len(k.get("bekleyen") or ()),
                     "sure": round(time.time() - k.get("zaman", time.time()))}
    return True


def dogrulama_bilgisi(tanimlar, veri_seti=""):
    """Kart ve Excel icin: {"durum", "hata", "sure", "gecen"} (gerekiyorsa
    baslatir). gecen: calisan kontrolun baslangicindan beri gecen sn."""
    imza = dogrulamayi_baslat(tanimlar, veri_seti)
    with _DM_KILIT:
        k = dict(_DM.get(imza) or {})
    calisiyor = k.get("durum") == "calisiyor"
    gecen = int(time.time() - k["zaman"]) if calisiyor and k.get("zaman") else None
    return {"durum": k.get("durum", "yok"), "hata": k.get("hata", ""),
            "sure": k.get("sure"), "gecen": gecen,
            "iptal": bool(k.get("iptal")), "kalan": int(k.get("kalan") or 0),
            "toplam": int(k.get("toplam") or 0) if calisiyor else 0,
            "bekleyen": len(k.get("bekleyen") or ()) if calisiyor else 0}


def dogrulama_sonucu(tanimlar, bekle=0.0, veri_seti=""):
    """Doner: (sonuc, durum). sonuc: {KISA: {"anlam", "karar", "ornek"}};
    karar "dogru" / "duzeltildi" / "emin_degil". durum: "yok" /
    "calisiyor" / "bitti" / "hata"."""
    imza = dogrulamayi_baslat(tanimlar, veri_seti)
    son = time.time() + max(0.0, bekle)
    while True:
        with _DM_KILIT:
            k = dict(_DM.get(imza) or {})
        if not k:
            return {}, "yok"
        if k["durum"] != "calisiyor" or time.time() >= son:
            return k["sonuc"], k["durum"]
        time.sleep(0.3)


def oneriler(tanimlar, bekle=0.0, veri_seti=""):
    """Onayli olmayan kisaltmalarin ogrenilen anlamlari.
    Doner: ({KISA: {"anlam", "kaynak", "kolon", "destek", "ornek"}}, dm_durum)
      kaynak: "sozluk" / "dil_modeli_dogruladi" / "dil_modeli" / "emin_degil"."""
    aday = adaylar(tanimlar)
    cikan = cikar(tanimlar, aday)
    dm, durum = dogrulama_sonucu(tanimlar, bekle, veri_seti)
    satirlar, parca_say, _g, _y, _s, _a = _parca_istatistigi(tanimlar)
    onay = onaylilar()
    cikti = {}
    for kisa, c in cikan.items():
        cikti[kisa] = {"anlam": c["anlam"], "kaynak": "sozluk",
                       "kolon": c["kolon"], "destek": c["destek"], "ornek": 0,
                       # IKI KAYNAK AYRI.
                       "istatistik": c["anlam"]}
    # Kapi icin: birlikte gectigi parcalarin anlamlari (onayli + ogrenilen
    # + dil modelinin verdigi).
    son_anlam = dict(cikan and {k: v["anlam"] for k, v in cikan.items()})
    for k, d in dm.items():
        if d.get("anlam"):
            son_anlam[k] = d["anlam"]
    son_anlam.update(onay)
    # Kolon adlarindaki HER parca (tanimsiz kolonlar dahil) ve kolon sayisi.
    tum_say = Counter(p for ad in (tanimlar or {}) for p in set(parcalar(ad)))
    kendini = set()
    for kisa, d in dm.items():
        if kisa in onay:
            continue
        # KENDINI ACIKLAYAN KELIME: anlami kelimenin kendisiyse listeye
        # girmez.
        if _kendini_aciklar(kisa, d.get("anlam") or d.get("genel") or ""):
            cikti.pop(kisa, None)
            kendini.add(kisa)
            continue
        # SOZLUKSUZ GENEL ANLAM (llm.SISTEM_KISALTMA_KOR): None = sorulmadi,
        # "" = model genel bir anlam bilmiyor (kuruma ozgu).
        genel = d.get("genel")
        genel_uyumlu = d.get("genel_uyumlu")
        d0_secim, d0_gerekce = d.get("secim") or "", d.get("gerekce") or ""
        d0_yeni = d.get("yeni_kisaltma") or ""
        d0_yeni_anlam = d.get("yeni_anlam") or ""
        d0_sozluk = d.get("sozluk_anlam") or ""
        d0_red = d.get("yeni_red") or ""
        d0_oneri_g = d.get("oneri_gerekce") or ""
        d0_bicim = d.get("bicim_oneri") or {}
        if d.get("anlam"):
            d = dict(d, anlam=yalin_anlam(d["anlam"]))
        onceki = cikti.get(kisa) or {"kolon": int(tum_say.get(kisa, 0)),
                                     "destek": None}
        onceki["ornek"] = d.get("ornek", 0)
        # BOS BIRAKILMAZ, SOYLENIR: Artik anlam kalir,
        # satirda uyari yazar; karari kullanici verir.
        uyari = []
        if d.get("anlam"):
            if _sade(d["anlam"]).replace(" ", "") == kisa.lower():
                # Anlam yerine kisaltmanin kendisi: anlam degil, bos kalir.
                d = {"anlam": "", "karar": "emin_degil"}
                uyari.append("Dil modeli anlam yerine kısaltmanın kendisini verdi.")
        if d.get("anlam"):
            # Birlikte gectigi kisaltmanin anlamini iceriyor. Es anlamli
            # (ayni anlam) uyari almaz.
            for q in sorted(_birlikte(satirlar, kisa, parca_say)):
                if q in son_anlam and not _ayni_anlam(son_anlam[q], d["anlam"]) \
                        and _yasakli(d["anlam"].split(), _anlam_kelimeleri(son_anlam[q])):
                    uyari.append("Anlam, birlikte geçtiği %s kısaltmasının anlamını "
                                 "(\"%s\") da içeriyor; yalnız bu kısaltmanın anlamı mı, "
                                 "kontrol edin." % (q, son_anlam[q]))
            uyari += _metin_uyarilari(d["anlam"])
        if d["karar"] == "dogru" and kisa in cikan:
            onceki["kaynak"] = "dil_modeli_dogruladi"
            cikti[kisa] = onceki
        elif d["karar"] in ("duzeltildi", "dogru") and d.get("anlam"):
            cikti[kisa] = dict(onceki, anlam=d["anlam"], kaynak="dil_modeli",
                               sozlukten=(cikan.get(kisa) or {}).get("anlam", ""))
        # GENEL ANLAM ONCE: dil modeli kisaltmanin genel
        # anlaminin sozlukteki kullanimla celistigini soylediyse kartta
        # yazar; o kolonlarin tanimlari sozlukle uyusmuyor.
        if d.get("sozluk_uyumsuz") and kisa in cikti and cikti[kisa].get("anlam"):
            cikti[kisa]["sozluk_uyumsuz"] = True
        elif d["karar"] == "emin_degil" and genel:
            # Sozlukle karar verilemedi ama genel anlam var: genel anlam
            # gelir (genel anlam once), sozluk istatistigi uyarida.
            istat = (cikan.get(kisa) or {}).get("anlam", "")
            cikti[kisa] = dict(onceki, anlam=yalin_anlam(genel), kaynak="genel",
                               sozlukten=istat)
            # Sozluk istatistigi genel anlamla AYNIYSA iki bagimsiz kaynak
            # uyusuyor: uyari yok.
            if not (istat and _ayni_anlam(yalin_anlam(istat), yalin_anlam(genel))):
                uyari.append("Sözlükteki kullanımla doğrulanamadı; anlam, sözlüğe "
                             "bakmadan verilen genel anlam"
                             + (" (sözlük istatistiği: \"%s\")" % istat if istat else "")
                             + ", kontrol edin.")
        elif d["karar"] == "emin_degil" and kisa in cikti:
            # Dil modeli emin olamadi: istatistik tahmini UYARIYLA kalir
            #
            cikti[kisa] = dict(onceki, kaynak="emin_degil")
            if cikti[kisa].get("anlam"):
                uyari.append("Dil modeli emin olamadı; anlam yalnız sözlük "
                             "istatistiğinden, kontrol edin.")
        # Secilen anlam SOZLUKSUZ genel anlamla karsilastirilir.
        if kisa in cikti and genel is not None:
            cikti[kisa]["genel"] = yalin_anlam(genel) if genel else ""
            mevcut = cikti[kisa].get("anlam") or ""
            if genel and mevcut and cikti[kisa].get("kaynak") != "genel":
                if genel_uyumlu is None or _ayni_anlam(yalin_anlam(genel), mevcut):
                    genel_uyumlu = _ayni_anlam(yalin_anlam(genel), mevcut) or bool(genel_uyumlu)
                cikti[kisa]["genel_uyumlu"] = bool(genel_uyumlu)
                if not genel_uyumlu and not d0_secim:
                    uyari.append("Sözlüğe bakmadan verilen genel anlam: \"%s\"; "
                                 "seçilen anlam farklı, kontrol edin." % yalin_anlam(genel))
        # "IKISI AYNI" AMA YAZIMLAR FARKLI: model es anlamli saymis olabilir; kod
        # es anlamliligi bilemez, satir sarı olur ve soylenir.
        soz_ = d0_sozluk or (cikan.get(kisa) or {}).get("anlam", "")
        ayni_farkli = bool(d0_secim == "ayni" and genel and soz_
                           and not _ayni_anlam(yalin_anlam(soz_), yalin_anlam(genel)))
        if ayni_farkli:
            uyari.append("Dil modeli iki anlamı aynı saydı ama farklılar (sözlük: \"%s\", "
                         "genel: \"%s\"); eş anlamlı mı, hangisi doğru, kontrol edin."
                         % (yalin_anlam(soz_), yalin_anlam(genel)))
        if d0_red and not d0_yeni:
            # Bicime uymayan oneri gizli dusmez, soylenir.
            uyari.append("Dil modelinin önerdiği kısaltma (%s) biçime uymadığı için "
                         "kullanılmadı (en çok 4 parça, parça başına 8, toplam 24 "
                         "karakter); isterseniz Önerilen Kısaltma'ya kendiniz yazın." % d0_red)
        if kisa not in cikti:
            # Anlam cikmadi: satir yine kartta, anlam bos (kullanici yazar).
            cikti[kisa] = dict(onceki, anlam="", kaynak="emin_degil")
        if uyari and kisa in cikti:
            cikti[kisa]["uyari"] = " ".join(dict.fromkeys(uyari))
        # Kartta Dil Modeli sutunu: SOZLUGE BAKMADAN verilen genel anlam
        # (kor). Kor cevap yoksa karar anlami. Karar (secim / gerekce /
        # yeni kisaltma) ayrica tasinir.
        if kisa in cikti:
            if genel is not None:
                dm_anlam = yalin_anlam(genel) if genel else ""
            else:
                dm_anlam = d.get("anlam") or ""
            cikti[kisa]["dm_anlam"] = dm_anlam
            cikti[kisa]["dm_karar"] = d.get("karar") if d.get("anlam") else (
                "genel" if dm_anlam else "emin_degil")
            cikti[kisa]["genel_bilinmiyor"] = genel == ""
            cikti[kisa]["secim"] = d0_secim
            cikti[kisa]["gerekce"] = d0_gerekce
            cikti[kisa]["yeni_kisaltma"] = d0_yeni
            cikti[kisa]["yeni_anlam"] = yalin_anlam(d0_yeni_anlam) if d0_yeni_anlam else ""
            cikti[kisa]["oneri_gerekce"] = d0_oneri_g
            cikti[kisa]["bicim_oneri"] = d0_bicim
            # LLM SOZLUK: modelin tanimlardan okudugu anlam.
            cikti[kisa]["dm_sozluk"] = yalin_anlam(d0_sozluk) if d0_sozluk else ""
            cikti[kisa]["ayni_farkli"] = ayni_farkli
    # AYNI YENI KISALTMA BIRDEN FAZLA KISALTMAYA onerildiyse (ayri anlamlar
    # tek kisaltmaya inemez) ya da zaten kolon adlarinda baska bir kisaltma
    # olarak geciyorsa oneri dusurulur, satirda uyari yazar.
    say_yeni = Counter(o.get("yeni_kisaltma") for o in cikti.values() if o.get("yeni_kisaltma"))
    for kisa, o in cikti.items():
        y = o.get("yeni_kisaltma")
        if not y:
            continue
        ya = o.get("yeni_anlam") or o.get("istatistik") or ""
        if parca_say.get(y) and son_anlam.get(y) and _ayni_anlam(son_anlam[y], ya):
            # AYNI ANLAMDA BASKA KISALTMA ZATEN VAR (iki kisaltma ayni
            # anlamda): hata degil; sozlukteki anlam dogru, oneri yok,
            # uyari yok.
            o.update(yeni_kisaltma="", yeni_anlam="", secim="sozluk", anlam=ya,
                     gerekce=(o.get("gerekce") or "")
                     + (" %s ile aynı anlamda; ikisi de kullanılabilir." % y))
            continue
        neden = ("%s birden fazla kısaltma için önerildi" % y if say_yeni[y] > 1 else
                 "%s kolon adlarında zaten başka bir kısaltma" % y if parca_say.get(y) else "")
        if neden:
            # Oneri dusunce bu kolonlardaki anlam (sozluk) gecerli olur.
            o.update(yeni_kisaltma="", yeni_anlam="", secim="sozluk", anlam=ya or o.get("anlam"))
            o["uyari"] = " ".join(x for x in (o.get("uyari"), "Önerilen kısaltma kullanılmadı (%s)."
                                              % neden) if x)
    # ONCEKI CALISMALARDAN OGRENILEN: bu sozlukten ogrenilemeyen (ya da
    # anlami bos kalan) kisaltma, kolon adlarinda geciyorsa ogrenilmis
    # bilgiden doldurulur.
    ogr = ogrenilenler()
    # Tanimsiz kolonlar da sayilir: sozlugu olmayan veri setinde kolon
    # adinda daha once ogrenilmis bir kisaltma geciyorsa anlami buradan gelir.
    for kisa, adet in tum_say.items():
        if kisa in onay or kisa not in ogr or kisa in kendini:
            continue
        if kisa in cikti and cikti[kisa]["anlam"]:
            continue
        o = ogr[kisa]
        cikti[kisa] = {"anlam": o["anlam"], "kaynak": "onceki", "kolon": int(adet),
                       "istatistik": o["anlam"],
                       "destek": None, "ornek": 0,
                       "onceki": "%s, %d kolon" % (o["veri_seti"] or "önceki sözlük", o["kolon"])}
    # Henuz sonucu olmayan (ya da hicbir kaynaktan anlam cikmayan) parca da
    # kartta: kolon adlarindaki her kisaltma gorunur.
    for kisa, adet in tum_say.items():
        if kisa in onay or kisa in kendini or kisa in cikti:
            continue
        cikti[kisa] = {"anlam": "", "kaynak": "", "kolon": int(adet), "destek": None,
                       "ornek": 0, "istatistik": ""}
    return cikti, durum


_BIRLER_EK = {1: "inde", 2: "sinde", 3: "ünde", 4: "ünde", 5: "inde", 6: "sında",
              7: "sinde", 8: "inde", 9: "unda"}
_ONLAR_EK = {1: "unda", 2: "sinde", 3: "unda", 4: "ında", 5: "sinde", 6: "ında",
             7: "inde", 8: "inde", 9: "ında"}


def yuzdesinde(n):
    """%86 -> "%86'sında", %100 -> "%100'ünde" (Turkce bulunma eki sayinin
    okunusuna gore."""
    n = int(round(n))
    if n == 0:
        ek = "ında"
    elif n % 10:
        ek = _BIRLER_EK[n % 10]
    elif n % 100:
        ek = _ONLAR_EK[(n // 10) % 10]
    else:
        ek = "ünde"                       # yuz
    return "%%%d'%s" % (n, ek)


def _kendini_aciklar(kisa, anlam):
    """Parca, anlaminin kendisi (Turkce kelime; parca = anlami).
    Ingilizce kelimenin kopyasi sayilmaz; o Turkce kontrolune takilir."""
    a = str(anlam or "").strip()
    if not a or _sade(a).replace(" ", "") != kisa.lower():
        return False
    try:
        from fe_agent import llm as llm_mod
        return not llm_mod.turkce_sorunu(a)
    except Exception:
        return True


def _metin_uyarilari(anlam):
    """Dil modelinin anlamindaki bicim sorunlari: Turkce degil ya da cok uzun."""
    cikti = []
    try:
        from fe_agent import llm as llm_mod
        sebep = llm_mod.turkce_sorunu(anlam)
    except Exception:
        sebep = None
    if sebep:
        cikti.append("Anlam tamamen Türkçe değil (%s); düzeltin." % sebep)
    if len(str(anlam or "").split()) > 6:
        cikti.append("Anlam 6 kelimeden uzun; kısaltmanın kendi anlamı mı, kontrol edin.")
    return cikti


def _ayni_anlam(a, b):
    return _sade(a).strip() == _sade(b).strip()


def birlesik(tanimlar):
    """Isteme giden kisaltmalar: (kesin, tahmini).
      kesin  : kullanicinin ONAYLADIKLARI (her zaman gecerli)
      tahmini: sozlukten ogrenilen / dil modelinin verdigi. Dil modeli
               kontrolu bitmediyse beklemez (o ana kadarki sonuc)."""
    oner, _d = oneriler(tanimlar, 0.0)
    kesin = dict(onaylilar())
    # Onceki calismalardan ogrenilenlerin HEPSI (istem yalniz o gruptaki
    # kolon adlarinda gecenleri koyar): sozlugu olmayan veri setinde de
    # ogrenilmis kisaltma bilinir. Bu calismada ogrenilen onun ustune yazar.
    tahmini = {k: o["anlam"] for k, o in ogrenilenler().items() if k not in kesin}
    tahmini.update({k: o["anlam"] for k, o in oner.items()
                    if o["anlam"] and k not in kesin})
    return kesin, tahmini


_KANIT = {
    "sozluk": "Sözlükten öğrenildi",
    "dil_modeli_dogruladi": "Dil modeli doğruladı",
    "dil_modeli": "Dil modeli önerdi",
    "emin_degil": "Dil modeli emin olamadı",
    "onceki": "Önceki sözlüklerden öğrenildi",
    "genel": "Dil modelinin genel bilgisi",
}


KANIT_ORNEK = 3          # kartta kisaltma basina gosterilen ornek kolon


def kanit_ornekleri(tanimlar, kisa, anlam, adet=KANIT_ORNEK):
    """Kartta anlami ONAYLATAN ornekler:
    adinda kisaltma gecen ve tanimi anlami tasiyan kolonlardan CESITLI
    secilmis en cok adet tane. Anlami tasiyan yoksa (dil modeli farkli
    anlam verdiyse) herhangi uc ornek gelir: kullanici celiskiyi gorur.
    Doner: [{"kolon", "tanim", "tasiyor"}]"""
    havuz = [(ad, str(t), set(parcalar(ad)))
             for ad, t in (tanimlar or {}).items()
             if str(t or "").strip() and kisa in parcalar(ad)]
    if anlam:
        tasiyan = [h for h in havuz if _anlami_tasir(h[1], anlam)]
        if tasiyan:
            havuz = tasiyan
    secilen, gorulen = [], set([kisa])
    while havuz and len(secilen) < adet:
        en = max(range(len(havuz)), key=lambda i: (len(havuz[i][2] - gorulen), -i))
        ad, t, ps = havuz.pop(en)
        secilen.append({"kolon": ad, "tanim": t[:200],
                        "tasiyor": bool(anlam) and _anlami_tasir(t, anlam)})
        gorulen |= ps
    return secilen


_KARAR_AD = {"ayni": "ikisi aynı", "sozluk": "sözlük doğru, genel anlam uymuyor",
             "genel": "tanımlardan anlam çıkmadı, genel anlam kullanıldı",
             "kisaltma_yanlis": "sözlük doğru ama kolon adında yanlış kısaltma seçilmiş",
             "anlasilmaz": "anlam doğru ama kısaltma anlaşılmıyor",
             "yeni": "tanımlara göre düzeltildi",
             "emin_degil": "karar verilemedi"}


def _uyum(o, bekliyor):
    """"ayni" / "farkli" / "" : sozlukteki anlam ile dil modelinin karari."""
    soz, dm = o.get("dm_sozluk") or o.get("istatistik") or "", o.get("dm_anlam") or ""
    if bekliyor:
        return ""
    # Modelin acik karari varsa o belirler (es anlamlilar "ayni").
    # SARI YALNIZ SOZLUK DEGISTIYSE: "ikisi ayni" ve
    # "sozluk dogru" kararlarinda yapacak bir sey yok, renksiz. Sozlukte
    # anlam yoksa degisen bir sey de yok.
    secim = o.get("secim")
    if secim == "ayni" and o.get("ayni_farkli"):
        return "farkli"           # yazimlar farkli: kontrol (sari)
    if secim in ("ayni", "sozluk"):
        return "ayni"
    if secim in ("genel", "yeni", "kisaltma_yanlis"):
        return "farkli" if soz else ""
    if secim == "anlasilmaz":
        return "farkli"           # oneri var: karar sizde (sari)
    if not soz or not dm:
        return ""
    if o.get("dm_karar") == "dogru" or _ayni_anlam(yalin_anlam(soz), yalin_anlam(dm)):
        return "ayni"
    return "farkli"


def kart_satirlari(tanimlar, bekle=0.0, veri_seti=""):
    """Kartta gosterilecek satirlar: onaylilar + ogrenilenler.
    Doner: (satirlar, dm_durum). satir: {kisaltma, anlam, onayli, kanit,
    cikarilan, kaynak} - kolon sayisina gore."""
    oner, durum = oneriler(tanimlar, bekle, veri_seti)
    onay = onaylilar()
    degisim = degisimler()
    # Kartta yalniz BU kolon adlarinda gecen kisaltmalar (hafizadaki
    # digerleri gelmez).
    tum_parca = set(p for ad in (tanimlar or {}) for p in parcalar(ad))
    # Sonucu henuz gelmeyen kisaltmalar kartta kilitli.
    bekleyen = bekleyenler(tanimlar, veri_seti) if durum == "calisiyor" else set()
    # Hafizadaki BIRLESTIRMELER ("<A>_<B>") ayri bolumde (birlesik_onerileri).
    tanimli = [ad for ad, t in (tanimlar or {}).items() if str(t or "").strip()]
    ciftler = {"%s_%s" % ab for ab in ifade_adaylari(tanimli)} \
        | set(birlesik_hafiza(tanimli, onay))
    satirlar = []
    for kisa in sorted((set(oner) | (set(onay) & tum_parca)) - ciftler,
                       key=lambda k: (-(oner.get(k) or {}).get("kolon", 0), k)):
        o = oner.get(kisa) or {}
        parca = []
        kaynak_ad = ""
        if o:
            # Kaynak adi kartta AYRI sutunlarda (Sozlukte / Dil Modeli)
            # gorundugu icin Not'a yazilmaz; Excel'de kullanilir.
            kaynak_ad = _KANIT.get(o["kaynak"], "")
            if o.get("ornek") and o["kaynak"] != "sozluk":
                kaynak_ad += " (%d örnekle)" % o["ornek"]
            if o.get("secim"):
                # ACIK KARAR: hangisi dogru + gerekce.
                parca.append("Karar: %s%s" % (_KARAR_AD.get(o["secim"], o["secim"]),
                                              (". " + o["gerekce"]) if o.get("gerekce") else ""))
                if o.get("yeni_kisaltma"):
                    parca.append("Önerilen: %s = %s%s; seçilirse bu kısaltmanın geçtiği "
                                 "kolon adları %s ile değişir"
                                 % (o["yeni_kisaltma"], o.get("yeni_anlam") or "",
                                    (" (%s)" % o["oneri_gerekce"]) if o.get("oneri_gerekce") else "",
                                    o["yeni_kisaltma"]))
            else:
                if o.get("genel_uyumlu"):
                    parca.append("sözlüğe bakmadan verilen genel anlamla aynı")
                elif o.get("genel") == "" and o["kaynak"] not in ("sozluk", "onceki"):
                    parca.append("genel bir anlamı yok (kuruma özgü), sözlükten çıkarıldı")
                if o.get("sozluk_uyumsuz"):
                    parca.append("genel anlam; sözlükteki kullanım farklı")
            if o.get("onceki"):
                parca.append(o["onceki"])
            if o.get("sozlukten"):
                parca.append("istatistik: %s" % o["sozlukten"])
            elif o.get("dm_sozluk") and o.get("istatistik") \
                    and not _ayni_anlam(o["dm_sozluk"], o["istatistik"]):
                parca.append("kelime sayımı: %s" % o["istatistik"])
            # LLM Sozluk sutununun kaynagi acikca: model cevap verdi ama
            # sozluk anlamini yazmadiysa sutunda kelime sayimi var.
            if not o.get("dm_sozluk") and o.get("dm_karar") is not None:
                parca.append("LLM Sözlük: dil modeli sözlük anlamı vermedi, kelime sayımı gösteriliyor")
            if o.get("destek") is not None:
                parca.append("%d kolonun %s" % (o["kolon"], yuzdesinde(o["destek"] * 100)))
            elif o.get("kolon"):
                parca.append("%d kolonda" % o["kolon"])
        anlam = onay.get(kisa) or o.get("anlam") or ""
        if kisa in onay and degisim.get(kisa):
            parca.append("Hafızada: %s yerine %s kullanılıyor; seçili kalırsa bu kısaltmanın "
                         "geçtiği kolon adları %s ile değişir" % (kisa, degisim[kisa], degisim[kisa]))
        satirlar.append({"kisaltma": kisa, "anlam": anlam,
                         "cikarilan": o.get("anlam") or "",
                         "kaynak": o.get("kaynak") or "",
                         "onayli": kisa in onay, "kanit": " · ".join(p for p in parca if p),
                         "kaynak_ad": kaynak_ad,
                         "sozluk_uyumsuz": bool(o.get("sozluk_uyumsuz")),
                         # Onayli satirda uyari gosterilmez (kullanici karar verdi).
                         "uyari": "" if kisa in onay else (o.get("uyari") or ""),
                         "bekliyor": kisa in bekleyen and kisa not in onay,
                         # Kartta iki kaynak ayri sutunda; Anlam'a hangisinin
                         # yazildigi "secilen" (renk de buna gore).
                         # LLM Sozluk: modelin tanimlardan okudugu; model
                         # sonucu yoksa kelime sayimi (kartta belirtilir).
                         "sozlukten": o.get("dm_sozluk") or o.get("istatistik") or "",
                         "sozluk_kaynak": ("dil_modeli" if o.get("dm_sozluk") else
                                           "istatistik" if o.get("istatistik") else ""),
                         "istatistik": o.get("istatistik") or "",
                         # Sayi degerli kalip: kolon adlarindaki bicimler
                         # (<K>00 ...); anlam kartta sayiyla gosterilir.
                         "sayili": sayili_bicimler(tanimlar, kisa),
                         "onceki_sozluk": o.get("kaynak") == "onceki",
                         "dil_modeli": o.get("dm_anlam") or "",
                         "dm_durum": ("bekliyor" if kisa in bekleyen else
                                      ("yok" if "dm_karar" not in o else
                                       ("bilinmiyor" if o.get("genel_bilinmiyor") else
                                        ("emin_degil" if not o.get("dm_anlam") else "var")))),
                         # YANILTICI KISALTMA icin dil modelinin onerdigi daha
                         # acik kisaltma (01.2.6'da kolon adina uygulanir).
                         # Onayli satirda hafizadaki degisim (ESKI -> YENI).
                         "yeni_kisaltma": (degisim.get(kisa, "") if kisa in onay
                                           else (o.get("yeni_kisaltma") or "")),
                         "yeni_anlam": ((anlam if degisim.get(kisa) else "") if kisa in onay
                                        else (o.get("yeni_anlam") or "")),
                         "secim": o.get("secim") or "",
                         "gerekce": o.get("gerekce") or "",
                         # Sozluk ile dil modeli AYNI mi (kartta satir rengi;
                         # kullanici karari). Biri yoksa karsilastirma yok.
                         "uyum": _uyum(o, kisa in bekleyen),
                         "secilen": ("hafiza" if kisa in onay else
                                     "" if not anlam else
                                     "dil_modeli" if o.get("kaynak") in
                                     ("dil_modeli", "dil_modeli_dogruladi", "genel") else "sozluk"),
                         "ornekler": kanit_ornekleri(tanimlar, kisa, anlam)})
        # SAYI DEGERLI BICIMLER AYRI SATIR: her biri kendi anlamiyla
        # (<anlam> <deger>) ve dil modelinin ona ozel onerdigi kisaltmayla.
        bo = o.get("bicim_oneri") or {}
        for b, n in sayili_degerler(tanimlar, kisa):
            e = bo.get(b) or {}
            # Hafizada bu bicim icin not edilen degisim once gelir, secili.
            hafizada = degisim.get(b.upper(), "")
            satirlar.append({"kisaltma": b, "bicim": kisa, "deger": n,
                             "secili": bool(hafizada),
                             "anlam": ("%s %s" % (anlam, n)).strip() if anlam else "",
                             "cikarilan": "", "kaynak": "bicim", "onayli": False,
                             "kanit": ("%s kısaltmasının %s değeri." % (kisa, n))
                                      + ((" Önerilen kısaltma: " + e["gerekce"])
                                         if e.get("gerekce") else ""),
                             "kaynak_ad": "", "sozluk_uyumsuz": False, "uyari": "",
                             "bekliyor": kisa in bekleyen and kisa not in onay,
                             "sozlukten": "", "sozluk_kaynak": "", "istatistik": "",
                             "sayili": [], "onceki_sozluk": False, "dil_modeli": "",
                             "dm_durum": "yok",
                             "yeni_kisaltma": hafizada or e.get("yeni_kisaltma") or "",
                             "yeni_anlam": "", "secim": "", "gerekce": "", "uyum": "",
                             "secilen": "", "ornekler": []})
    return satirlar, durum


# ---------------------------------------------------------------------------
# RAPOR
# ---------------------------------------------------------------------------
RAPOR_ORNEK = 5          # anlami tasiyan ornek kolon
RAPOR_CELISEN = 3        # anlami TASIMAYAN ornek kolon (sozluk hatasi adayi)

RAPOR_KOLONLARI = (
    ["Kısaltma", "LLM Karar", "LLM Sözlük", "LLM Genel", "Karar", "Gerekçe",
     "Önerilen Kısaltma", "Kaynak", "Onaylı Tanım",
     "Geçtiği Tanımlı Kolon", "Anlamı Taşıyan Kolon", "İstatistik Adayları"]
    + sum([["Örnek %d Kolon" % i, "Örnek %d Açıklama" % i]
           for i in range(1, RAPOR_ORNEK + 1)], [])
    + sum([["Çelişen Örnek %d Kolon" % i, "Çelişen Örnek %d Açıklama" % i]
           for i in range(1, RAPOR_CELISEN + 1)], [])
    + ["Karar (Doğru / Düzeltilmiş Anlam)"])


def rapor_satirlari(tanimlar, veri_seti=""):
    """Kisaltma karti + kanit: her kisaltma icin onerilen anlam, kaynagi,
    istatistik adaylari, anlami tasiyan cesitli ornekler ve anlami
    TASIMAYAN ornekler (sozlukteki olasi hata). Son sutun bos: kullanici
    kararini yazar. Doner: satir listesi (RAPOR_KOLONLARI sirasiyla)."""
    satirlar_k, _d = kart_satirlari(tanimlar, 0.0, veri_seti)
    aday = adaylar(tanimlar)
    tanimli = {ad: str(t) for ad, t in (tanimlar or {}).items() if str(t or "").strip()}
    cikti = []
    for r_ in satirlar_k:
        kisa, anlam = r_["kisaltma"], r_["anlam"]
        kolonlar = [ad for ad in tanimli if kisa in parcalar(ad)]
        tasiyan = [ad for ad in kolonlar if anlam and _anlami_tasir(tanimli[ad], anlam)]
        ornek = kanit_ornekleri(tanimlar, kisa, anlam, RAPOR_ORNEK)
        celisen = [{"kolon": ad, "tanim": tanimli[ad][:300]}
                   for ad in kolonlar if ad not in tasiyan][:RAPOR_CELISEN] if anlam else []
        ist = "; ".join("%s (%%%d, ayırt %%%d)" % (a["anlam"], round(a["destek"] * 100),
                                                  round(a["ayirt"] * 100))
                        for a in (aday.get(kisa) or {}).get("adaylar", [])[:ADAY_SAYISI])
        # KARAR VE GEREKCE AYRI SUTUNDA (Kaynak sutunu cok uzundu).
        parca_ = [x for x in str(r_["kanit"] or "").split(" · ")
                  if x and not x.startswith(("Karar:", "Önerilen:"))]
        kanit = " · ".join(x for x in [r_.get("kaynak_ad")] + parca_ if x) \
            + ((" · UYARI: " + r_["uyari"]) if r_.get("uyari") else "")
        yeni_k = ("%s = %s" % (r_["yeni_kisaltma"], r_.get("yeni_anlam") or "")
                  if r_.get("yeni_kisaltma") else None)
        satir = [kisa, anlam, r_.get("sozlukten") or None, r_.get("dil_modeli") or None,
                 _KARAR_AD.get(r_.get("secim") or "", None), r_.get("gerekce") or None,
                 yeni_k, kanit, "Evet" if r_["onayli"] else "Hayır",
                 len(kolonlar), len(tasiyan) if anlam else None, ist]
        for i in range(RAPOR_ORNEK):
            o = ornek[i] if i < len(ornek) else None
            satir += [o["kolon"], o["tanim"]] if o else [None, None]
        for i in range(RAPOR_CELISEN):
            o = celisen[i] if i < len(celisen) else None
            satir += [o["kolon"], o["tanim"]] if o else [None, None]
        satir.append(None)
        cikti.append(satir)
    return cikti
