# -*- coding: utf-8 -*-
"""fe_agent/kisaltma.py - KOLON ADI KISALTMALARI: sozlukten cikarim + onayli
kisaltma hafizasi (proje geneli).

Kullanici karari: "TXN islem, GLN gelen, GDN giden ... bunu anlayabiliyor
mu? Baska veriler / kolonlar kullanirsam ve sozlukleri olmadiginda ya da
yarim yamalak hatali oldugunda komple duzeltebilmem lazim, onaylananlar
bazinda da."

CIKARIM (cikar) - kural tabanli, dil modeli YOK:
  Kolon adi parcalara bolunur (TXN_GLN_BAHIS_180D_AMT -> TXN, GLN, BAHIS,
  AMT; 180D gibi pencereler ve saf sayilar atlanir). Her parca icin,
  adinda o parca gecen tanimli kolonlarin tanimlarinda gecen kelimeler
  (ve iki kelimelik ifadeler) sayilir. Bir kelime ancak o parcayi
  tasiyan tanimlarda SIK (>= DESTEK_ESIK), tasimayanlarda belirgin
  SEYREK ise (fark >= AYIRT_ESIK) parcanin anlami sayilir. Ornek: "islem"
  TXN'li tanimlarin hepsinde gecer ama GLN'li tanimlarin da hepsinde
  gectigi icin GLN'nin anlami olamaz; "gelen" ise yalniz GLN'lilerde.

HAFIZA - PROJE_HAFIZASI/KISALTMA_HAFIZASI.parquet (calisma klasorlerinin
disinda). YALNIZ kullanicinin onayladigi kisaltmalar girer. Sozlugu
olmayan ya da eksik/hatali sozluklu bir veri setinde de oneriler bu
listeyle yazilir. Girdi veri setine ve sozluge hicbir kosulda yazilmaz.

OKUMA HATASI YAZMAYI DURDURUR (tanim_hafiza ile ayni kural): dosya var ama
okunamiyorsa ustune yazilmaz."""

import datetime
import re
import threading
import time
from collections import Counter

import pandas as pd

from fe_agent import tablo_io
from fe_agent.akis_durum import _folder

DOSYA = "/KISALTMA_HAFIZASI.parquet"
KOLONLAR = ["KISALTMA", "ANLAM", "KAYNAK", "KULLANICI", "TARIH"]
KAYNAK_ONAY = "sözlükten çıkarıldı, kullanıcı onayladı"
KAYNAK_KULLANICI = "kullanıcı yazdı"

EN_AZ_KOLON = 3        # parca en az bu kadar tanimli kolonun adinda gecmeli
DESTEK_ESIK = 0.6      # anlam, o kolonlarin tanimlarinin en az bu kadarinda
AYIRT_ESIK = 0.3       # ... ve digerlerinden en az bu kadar daha sik
EN_COK = 300           # kartta gosterilen en cok kisaltma

_TR_KUCUK = str.maketrans({"I": "ı", "İ": "i"})
_TR_SADE = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
_PENCERE = re.compile(r"^\d+[DAMYH]?$", re.I)     # 180D, 3A, 12, 6M
_DURAK = {"ve", "ile", "icin", "olan", "bir", "bu", "da", "de", "gore", "son",
          "gun", "gunde", "gunluk", "ay", "ayda"}

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


def parcalar(ad):
    """Kolon adinin kisaltma adaylari (buyuk harf). Pencereler ve sayilar
    atlanir."""
    cikti = []
    for p in re.split(r"[^A-Za-z0-9ÇĞİÖŞÜçğıöşü]+", str(ad or "")):
        p = p.upper().translate(_TR_SADE)
        if len(p) < 2 or _PENCERE.match(p):
            continue
        cikti.append(p)
    return cikti


def _tanim_kokleri(tanim):
    """Tanimdan {kok: yuzey bicimi} (tekli) ve iki kelimelik ifadeler."""
    kelimeler = [k for k in re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü]+", str(tanim or ""))
                 if len(k) >= 3]
    tekli, ikili = {}, {}
    onceki = None
    for k in kelimeler:
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


def cikar(tanimlar):
    """{kolon: tanim} -> {KISALTMA: {"anlam", "kolon", "destek", "ayirt"}}.

    kolon : adinda kisaltma gecen tanimli kolon sayisi
    destek: o kolonlarin tanimlarinda anlamin gectigi pay
    ayirt : destek - (kisaltma gecmeyen kolonlarda ayni anlamin payi)"""
    satirlar = []
    for ad, tanim in (tanimlar or {}).items():
        if not str(tanim or "").strip():
            continue
        tekli, ikili = _tanim_kokleri(tanim)
        satirlar.append((set(parcalar(ad)), tekli, ikili))
    n = len(satirlar)
    if n < EN_AZ_KOLON:
        return {}

    genel = Counter()
    yuzey = {}
    for _p, tekli, ikili in satirlar:
        for k, y in list(tekli.items()) + list(ikili.items()):
            genel[k] += 1
            yuzey.setdefault(k, Counter())[y] += 1

    parca_say = Counter(p for ps, _t, _i in satirlar for p in ps)
    sonuc = {}
    for parca, adet in parca_say.items():
        if adet < EN_AZ_KOLON or adet == n:
            continue
        icinde = Counter()
        for ps, tekli, ikili in satirlar:
            if parca in ps:
                icinde.update(set(tekli) | set(ikili))
        # Aday puanlari: ayirt = destek - disaridaki pay.
        puan = {}
        for k, say in icinde.items():
            destek = say / float(adet)
            if destek < DESTEK_ESIK:
                continue
            ayirt = destek - (genel[k] - say) / float(max(n - adet, 1))
            if ayirt >= AYIRT_ESIK:
                puan[k] = (ayirt, destek)
        tekli = {k: v for k, v in puan.items() if " " not in k}
        if not tekli:
            continue
        # Esitlikte kisaltmanin harflerini SIRAYLA iceren kelime one gecer
        # (GLN -> gelen, GDN -> giden).
        en_iyi = max(tekli, key=lambda k: (tekli[k][0], tekli[k][1],
                                           _harf_uyumu(parca, k), -len(k)))
        sinir = tekli[en_iyi][0] - 0.05
        # IKI KELIMELIK IFADE yalniz iki kelimesi de bu kisaltmaya ozgu
        # ise secilir ("hafta sonu" -> HS). "islem tutari" AMT icin
        # secilmez: "islem" AMT'ye ozgu degil (CNT'de de geciyor).
        for k, (ayirt, _d) in puan.items():
            if " " in k and ayirt >= sinir and all(
                    (tekli.get(p) or (0, 0))[0] >= sinir for p in k.split(" ")):
                en_iyi = k
                break
        ayirt, destek = puan[en_iyi]
        bicimler = yuzey[en_iyi]
        anlam = min(bicimler, key=lambda y: (len(y), -bicimler[y]))
        # Kendini anlatan parca (BAHIS -> bahis) listeyi kalabaliklastirir.
        if _sade(anlam).replace(" ", "") == parca.lower():
            continue
        sonuc[parca] = {"anlam": anlam,
                        "kolon": int(adet), "destek": round(destek, 3),
                        "ayirt": round(ayirt, 3)}
    return sonuc


# ---------------------------------------------------------------------------
# ONAYLI KISALTMA HAFIZASI
# ---------------------------------------------------------------------------
def _bos():
    return pd.DataFrame(columns=KOLONLAR)


def _var_mi():
    klasor = _folder()
    for yol in tablo_io.aday_yollar(DOSYA):
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


def _oku_ham():
    try:
        df = tablo_io.klasorden_oku(_folder(), DOSYA)
    except Exception as e:
        if _var_mi() is False:
            return _bos(), None
        return None, "Kısaltma hafızası okunamadı (%s)." % str(e)[:120]
    for k in KOLONLAR:
        if k not in df.columns:
            df[k] = ""
    return df[KOLONLAR].fillna("").astype(str), None


def onaylilar():
    """{KISALTMA: anlam} - onayli kisaltmalar (onbellekli)."""
    simdi = time.time()
    if _ONBELLEK["df"] is None or simdi - _ONBELLEK["zaman"] > ONBELLEK_OMRU_SN:
        df, _h = _oku_ham()
        if df is not None:
            _ONBELLEK.update(zaman=simdi, df=df)
    df = _ONBELLEK["df"]
    if df is None or df.empty:
        return {}
    df = df[df["ANLAM"].str.strip() != ""]
    return dict(zip(df["KISALTMA"].str.upper(), df["ANLAM"]))


def kaydet(satirlar, kullanici=""):
    """satirlar: [{"kisaltma", "anlam", "kaydet": bool, "kaynak"}].
    kaydet=True -> eklenir / guncellenir; False -> hafizada varsa silinir.
    Doner: (onayli_sozluk, hata). Istisna firlatmaz."""
    zaman = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _KILIT:
        df, hata = _oku_ham()
        if df is None:
            return onaylilar(), hata
        df = df.copy()
        df["KISALTMA"] = df["KISALTMA"].str.upper()
        for s in satirlar or []:
            if not isinstance(s, dict):
                continue
            kisa = str(s.get("kisaltma") or "").strip().upper()
            anlam = str(s.get("anlam") or "").strip()
            if not kisa:
                continue
            df = df[df["KISALTMA"] != kisa]
            if s.get("kaydet") and anlam:
                df = pd.concat([df, pd.DataFrame([{
                    "KISALTMA": kisa, "ANLAM": anlam,
                    "KAYNAK": str(s.get("kaynak") or KAYNAK_ONAY),
                    "KULLANICI": str(kullanici or ""), "TARIH": zaman}],
                    columns=KOLONLAR)], ignore_index=True)
        try:
            tablo_io.klasore_yaz(_folder(), DOSYA, df.sort_values("KISALTMA"))
        except Exception as e:
            return onaylilar(), "Kısaltma hafızasına yazılamadı (%s)." % str(e)[:120]
        _ONBELLEK.update(zaman=time.time(), df=df)
    return onaylilar(), None


def birlesik(tanimlar):
    """Isteme giden kisaltma sozlugu: ONAYLILAR once (her zaman gecerli),
    sonra bu sozlukten cikarilanlar (onaylida olmayanlar).
    Doner: {KISALTMA: anlam}."""
    cikti = {k: v["anlam"] for k, v in cikar(tanimlar).items()}
    cikti.update(onaylilar())
    return cikti


def kart_satirlari(tanimlar):
    """Kartta gosterilecek satirlar: onaylilar + cikarilanlar.
    [{kisaltma, anlam, onayli, kanit, cikarilan}] - kolon sayisina gore."""
    cikan = cikar(tanimlar)
    onay = onaylilar()
    satirlar = []
    for kisa in sorted(set(cikan) | set(onay),
                       key=lambda k: (-(cikan.get(k) or {}).get("kolon", 0), k)):
        c = cikan.get(kisa) or {}
        kanit = ("Sözlükten: %d kolonun %%%d'inde" % (c["kolon"], round(c["destek"] * 100))
                 if c else "")
        satirlar.append({"kisaltma": kisa,
                         "anlam": onay.get(kisa) or c.get("anlam") or "",
                         "cikarilan": c.get("anlam") or "",
                         "onayli": kisa in onay, "kanit": kanit})
    return satirlar[:EN_COK]
