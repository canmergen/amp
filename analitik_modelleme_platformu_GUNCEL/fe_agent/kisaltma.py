# -*- coding: utf-8 -*-
"""fe_agent/kisaltma.py - KOLON ADI KISALTMALARI: hafiza (proje geneli),
sozluk istatistigi ve ortak yardimcilar.

Kisaltma Sozlugu (01.2.4.3) ve Yeni Kolon Adlari (01.2.4.4) kisaltma_okuma'da:
anlamlar yalniz sozlukteki tanimlardan okunur (SOZLUK KESIN DOGRUDUR).
Bu modulde kalanlar:

1) ISTATISTIK (cikar) - butun tanimlar: kolon adi parcalara bolunur, her
   parca icin adinda o parca gecen tanimli kolonlarin tanimlarinda gecen
   kelimeler sayilir (destek / ayirt). Yalniz TAHMINI baglamdir (tanim
   yazdirma istemleri); Kisaltma Sozlugu'nun anlami degildir.

2) HAFIZA - PROJE_HAFIZASI/KISALTMA_HAFIZASI.json (calisma klasorlerinin
   disinda; okunur bicim: {"kisaltmalar": {KISA: anlam}, "degisimler":
   {ESKI: YENI}, "notlar": {KISA: not}}). Kisaltma Sozlugu'nde secilen
   satirin onerilen kisaltmasi doluysa anlam YENI kisaltmayla yazilir ve
   ESKI -> YENI degisimi not edilir; bos ise anlam kisaltmanin kendisiyle
   yazilir. YALNIZ kullanicinin sectikleri girer. Bu veri setinin sozlugu
   her zaman hafizanin onune gecer; hafiza yalniz sozlugun aciklamadigi
   parcalar ve anlam basina standart kisaltma icin kullanilir. Girdi veri
   setine ve sozluge hicbir kosulda yazilmaz. OKUMA HATASI YAZMAYI
   DURDURUR: dosya var ama okunamiyorsa ustune yazilmaz. Ayni dosyada
   "kalip" / "turler" (ad ilkesi) ve "donem" (01.2.4.1 donem bilgisi) de
   durur.

3) OGRENILEN - PROJE_HAFIZASI/KISALTMA_OGRENILEN.json: her calismada
   sozlukten okunan (tek anlamli) kisaltmalar kendiliginden yazilir
   (onaysiz); sonraki calismalarda tahmini kaynaktir."""

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
    kismidir (<K>_<NN>) ve kisaltmadir."""
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


BIRLESIK_EN_COK_PARCA = 4


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
    # AD ILKESI (kalip ve anlam turleri) ve DONEM BILGISI ayni dosyada;
    # burada korunur.
    govde.update(_ad_ilkesi_ham())
    donem = _donem_ham()
    if donem:
        govde["donem"] = donem
    _folder().upload_stream(DOSYA, json.dumps(govde, ensure_ascii=False, indent=2,
                                              sort_keys=True).encode("utf-8"))


# ---------------------------------------------------------------------------
# AD ILKESI (kurum geneli): kolon adinda parcalarin sirasi (kalip) ve her
# anlamin turu. KISALTMA_HAFIZASI.json'da "kalip" ve "turler" altinda.
# ---------------------------------------------------------------------------
TURLER = [
    ("konu", "Konu"),
    ("yon", "Yön"),
    ("nitelik", "Nitelik"),
    ("pencere", "Pencere"),
    ("olcu", "Ölçü"),
    ("istatistik", "İstatistik"),
    ("diger", "Diğer"),
]
TUR_ACIKLAMA = {
    "konu": "ölçümün konusu olan varlık ya da olay",
    "yon": "hareketin yönü",
    "nitelik": "ölçümü daraltan alt küme ya da özellik (tür, kanal, taraf, zaman dilimi ...)",
    "pencere": "zaman penceresi ya da dönem",
    "olcu": "ölçülen büyüklük (tutar, adet, süre ...)",
    "istatistik": "ölçüme uygulanan hesap (ortalama, en büyük, oran, toplam, fark ...)",
    "diger": "bayrak, düzey ya da yukarıdakilere girmeyen",
}
VARSAYILAN_KALIP = [t for t, _e in TURLER]


def _ad_ilkesi_ham():
    try:
        with _folder().get_download_stream(DOSYA) as akis:
            govde = json.loads(akis.read().decode("utf-8") or "{}")
    except Exception:
        return {}
    if not isinstance(govde, dict):
        return {}
    return {k: govde[k] for k in ("kalip", "turler") if govde.get(k)}


def kalip_temizle(kalip):
    """Gecerli turlerden olusan, her turu bir kez iceren sira; eksik
    turler varsayilan sirayla sona eklenir."""
    gecerli = set(VARSAYILAN_KALIP)
    cikti = []
    for t in kalip or []:
        t = str(t or "").strip()
        if t in gecerli and t not in cikti:
            cikti.append(t)
    return cikti + [t for t in VARSAYILAN_KALIP if t not in cikti]


def ad_ilkesi():
    """{"kalip": [tur, ...], "turler": {anlam_anahtari: tur}}."""
    ham = _ad_ilkesi_ham()
    turler = {str(k): str(v) for k, v in (ham.get("turler") or {}).items()
              if str(v) in VARSAYILAN_KALIP}
    return {"kalip": kalip_temizle(ham.get("kalip")), "turler": turler}


def ad_ilkesi_kaydet(kalip=None, turler=None):
    """Kalibi ve anlam turlerini hafizaya yazar (turler eklenir /
    guncellenir, silinmez). Doner: hata ya da None."""
    with _KILIT:
        try:
            with _folder().get_download_stream(DOSYA) as akis:
                govde = json.loads(akis.read().decode("utf-8") or "{}")
        except Exception:
            govde = {}
        if not isinstance(govde, dict):
            govde = {}
        if kalip:
            govde["kalip"] = kalip_temizle(kalip)
        if turler:
            mevcut = dict(govde.get("turler") or {})
            mevcut.update({str(k): str(v) for k, v in turler.items()
                           if str(k).strip() and str(v) in VARSAYILAN_KALIP})
            govde["turler"] = mevcut
        try:
            _folder().upload_stream(DOSYA, json.dumps(
                govde, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"))
        except Exception as e:
            return "Ad ilkesi hafızaya yazılamadı (%s)." % str(e)[:120]
    return None


# ---------------------------------------------------------------------------
# DONEM BILGISI (kurum geneli): 01.2.4.1'de "Hafizaya Kaydet" isaretli donem
# kaliplarinin anlami. KISALTMA_HAFIZASI.json'da "donem" altinda:
# {kalip: anlam}.
# ---------------------------------------------------------------------------
def _govde_oku():
    """Doner: (govde, hata). Dosya yoksa ({}, None)."""
    try:
        with _folder().get_download_stream(DOSYA) as akis:
            govde = json.loads(akis.read().decode("utf-8") or "{}")
    except Exception as e:
        if _var_mi(DOSYA) is False:
            return {}, None
        return None, "Kısaltma hafızası okunamadı (%s)." % str(e)[:120]
    if not isinstance(govde, dict):
        return None, "Kısaltma hafızası okunamadı (biçim)."
    return govde, None


def _donem_ham():
    govde, _h = _govde_oku()
    donem = (govde or {}).get("donem")
    if not isinstance(donem, dict):
        return {}
    return {str(k): str(v) for k, v in donem.items() if str(v or "").strip()}


def donem_hafizasi():
    """{kalip: anlam} - hafizadaki donem bilgisi."""
    return _donem_ham()


def donem_kaydet(kayitlar):
    """kayitlar: {kalip: anlam}; eklenir / guncellenir, silinmez.
    Dosya var ama okunamiyorsa ustune yazilmaz. Doner: hata ya da None."""
    kayitlar = {str(k).strip(): str(v).strip() for k, v in (kayitlar or {}).items()
                if str(k).strip() and str(v or "").strip()}
    if not kayitlar:
        return None
    with _KILIT:
        govde, hata = _govde_oku()
        if govde is None:
            return "Dönem bilgisi hafızaya yazılamadı: " + hata
        donem = dict(govde.get("donem") or {})
        donem.update(kayitlar)
        govde["donem"] = dict(sorted(donem.items()))
        try:
            _folder().upload_stream(DOSYA, json.dumps(
                govde, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"))
        except Exception as e:
            return "Dönem bilgisi hafızaya yazılamadı (%s)." % str(e)[:120]
    return None


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
        anlamlar = {k: o["anlam"] for k, o in cikar(tanimlar).items() if o["anlam"]}
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



def _ayni_anlam(a, b):
    return _sade(a).strip() == _sade(b).strip()


