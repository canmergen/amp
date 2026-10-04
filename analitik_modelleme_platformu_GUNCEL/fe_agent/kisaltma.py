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
okunamiyorsa ustune yazilmaz.

IYILESTIRME (kullanici karari: "daha duzgun onermesini saglayamaz miyim,
kendisi de iyilesemez mi" -> hepsi):
  1) TEMEL SOZLUK: standart Ingilizce kisaltmalar (IN, OUT, SUM, DAY,
     MONTH, HIGH, LOW, BY, PER, TOP1 ...) sabit ve kesin; tahmin edilmez.
  2) CIKARIM KURALI: bir anlami en guclu kanitla bir kisaltma aldiysa
     baska kisaltmaya verilmez (IN / OUT / SUM, CP'nin "karsi taraf"ini
     kapiyordu); ikinci aday yoksa anlam bos kalir. Ekli bicim sozlukte
     yalin hali de geciyorsa yalina indirilir (adedi -> adet).
  3) DIL MODELI KONTROLU: kural tabanli liste, her kisaltmanin gectigi
     ornek kolon adlari ve tanimlariyla dil modellerine sorulur (iki
     model, anlasamazlarsa hakem). Arka planda calisir, sonuc
     onbellekte tutulur; emin olunamayan anlam bos birakilir.
  4) KESIN / TAHMINI: dil modeline "kesin" diye yalniz ONAYLI ve TEMEL
     kisaltmalar gider; cikarilanlar "tahmini" etiketiyle gider."""

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

# ---------------------------------------------------------------------------
# 1) TEMEL SOZLUK - standart (cogunlukla Ingilizce) kisaltmalar. Yalniz
# ANLAMI TEK OLANLAR: NO (sayi / yok), CURR (para birimi / guncel), MON,
# VOL gibi iki anlamli kisaltmalar BILEREK yok; onlari sozluk ve dil
# modeli belirler.
# ---------------------------------------------------------------------------
TEMEL = {
    "IN": "gelen", "INC": "gelen", "OUT": "giden", "OUTG": "giden",
    "SUM": "toplam", "TOTAL": "toplam", "TOT": "toplam",
    "AVG": "ortalama", "MEAN": "ortalama", "MEDIAN": "medyan", "MED": "medyan",
    "MAX": "maksimum", "MIN": "minimum", "STD": "standart sapma",
    "STDDEV": "standart sapma", "VAR": "varyans", "CV": "değişim katsayısı",
    "CNT": "adet", "COUNT": "adet", "AMT": "tutar", "AMOUNT": "tutar",
    "RATIO": "oran", "PCT": "yüzde", "PERC": "yüzde", "SHR": "pay", "SHARE": "pay",
    "DAY": "gün", "DAYS": "gün", "WEEK": "hafta", "WK": "hafta",
    "MONTH": "ay", "MONTHS": "ay", "MTH": "ay", "YEAR": "yıl", "YR": "yıl",
    "HOUR": "saat", "HR": "saat", "WEEKEND": "hafta sonu", "WEEKDAY": "hafta içi",
    "NIGHT": "gece",
    "PER": "başına", "BY": "bazında", "FLAG": "bayrak (0/1)", "FLG": "bayrak (0/1)",
    "HIGH": "yüksek", "LOW": "düşük", "TOP": "en büyük",
    "FIRST": "ilk", "FRST": "ilk", "LAST": "son", "LST": "son",
    "PREV": "önceki", "NEW": "yeni", "OLD": "eski",
    "ACTIVE": "aktif", "PASSIVE": "pasif", "DISTINCT": "farklı",
    "UNIQUE": "tekil", "UNQ": "tekil", "ENTROPY": "entropi",
    "HHI": "Herfindahl-Hirschman yoğunlaşma endeksi", "CONC": "yoğunlaşma",
    "SCORE": "skor", "SCR": "skor", "RAW": "ham", "LOG": "logaritma",
    "DIFF": "fark", "CHG": "değişim", "CHANGE": "değişim", "GROWTH": "büyüme",
    "TREND": "eğilim", "SLOPE": "eğim", "TXN": "işlem", "TRX": "işlem",
    "CUST": "müşteri", "CUSTOMER": "müşteri", "ACC": "hesap", "ACCT": "hesap",
    "BAL": "bakiye", "BALANCE": "bakiye", "LMT": "limit", "LIMIT": "limit",
    "BNK": "banka", "BANK": "banka", "CP": "karşı taraf",
    "SUPPORT": "destek", "SHRUNK": "büzülmüş (shrinkage ile düzeltilmiş)",
    "EFFECTIVE": "etkin", "TMSNC": "bu yana geçen süre",
    "TMSNCFRST": "ilkten bu yana geçen süre",
    "TMSNCLST": "sondan bu yana geçen süre",
}
# Kalipli temel kisaltmalar: TOP1, TOP3 ... ve H00, H06 ... (saat dilimi).
_TOP_N = re.compile(r"^TOP(\d+)$")
_SAAT = re.compile(r"^H([01]\d|2[0-3])$")


def temel_anlam(parca):
    """Temel sozlukteki (ya da kalipli) anlam; yoksa ''."""
    p = str(parca or "").upper()
    if p in TEMEL:
        return TEMEL[p]
    m = _TOP_N.match(p)
    if m:
        return "en büyük %s" % m.group(1) if m.group(1) != "1" \
            else "en büyük (1. sıradaki)"
    m = _SAAT.match(p)
    if m:
        return "saat %s:00'da başlayan zaman dilimi" % m.group(1)
    return ""


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
    satirlar_ad = [ps for ps, _t, _i in satirlar]
    onay = onaylilar()
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
    # Sozlukte gecen butun kelimeler (yalin hal kontrolu icin).
    sozcukler = set()
    for _p, tekli, _i in satirlar:
        sozcukler.update(tekli.values())
    # Temel sozluk anlamlari da yalin bicim kaynagi: "adedi" -> "adet"
    # sozlukte "adet" hic gecmese de.
    for v in TEMEL.values():
        sozcukler.update(_kucuk(k) for k in v.split())
    # Temel kisaltmalarin anlam kokleri (FLAG -> bayrak, TXN -> islem):
    # IKI KELIMELIK ifadeye giremez ("yoksa bayragi" NO icin secilmesin;
    # "bayrak" FLAG'in). Tek kelime olarak serbest: GLN "gelen" olabilir,
    # IN de "gelen" olsa bile (es anlamli kisaltmalar).
    temel_kok = set()
    for ps, _t, _i in satirlar:
        for p in ps:
            for k in temel_anlam(p).split():
                temel_kok.add(_kok(k))
    adaylar = {}                      # parca -> (adet, [(puan, anlam)...])
    for parca, adet in parca_say.items():
        if adet < EN_AZ_KOLON or adet == n or temel_anlam(parca):
            # Temel sozlukteki kisaltma yarismaz: anlami sabit; ayrica
            # baskasinin anlamini kapmasin (IN, CP'nin "karsi taraf"ini).
            continue
        icinde = Counter()
        for ps, tekli, ikili in satirlar:
            if parca in ps:
                icinde.update(set(tekli) | set(ikili))
        # Kolonlarinin YARISINDAN FAZLASINDA birlikte gectigi bilinen
        # (temel / onayli) kisaltmanin anlami bu parcanin anlami olamaz:
        # NO_TXN_FLAG'de "bayrak" FLAG'in; DISTINCT_BNK_ADT'de "farkli"
        # DISTINCT'in, "banka" BNK'nin (kullanici bildirimi: ADT "farkli"
        # geliyordu).
        yasak = yasak_kokler(satirlar_ad, parca, onay)
        # Aday puanlari: ayirt = destek - disaridaki pay.
        puan = {}
        for k, say in icinde.items():
            if _yasakli(k.split(" "), yasak):
                continue
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
        # (GLN -> gelen, GDN -> giden). Aday SIRASI korunur: cakisma
        # kuralinda ilk aday alinmissa ikinciye gecilir.
        sirali = sorted(tekli, key=lambda k: (tekli[k][0], tekli[k][1],
                                              _harf_uyumu(parca, k), -len(k)),
                        reverse=True)
        liste = []
        for en_iyi in sirali:
            sinir = tekli[en_iyi][0] - 0.05
            secilen = en_iyi
            # IKI KELIMELIK IFADE yalniz iki kelimesi de bu kisaltmaya ozgu
            # ise secilir ("hafta sonu" -> HS). "islem tutari" AMT icin
            # secilmez: "islem" AMT'ye ozgu degil (CNT'de de geciyor).
            for k, (ayirt, _d) in puan.items():
                if " " in k and en_iyi in k.split(" ") and ayirt >= sinir \
                        and not any(p in temel_kok for p in k.split(" ")) and all(
                        (tekli.get(p) or (0, 0))[0] >= sinir for p in k.split(" ")):
                    secilen = k
                    break
            liste.append((puan[secilen], secilen))
        adaylar[parca] = (adet, liste)

    # 2) CAKISMA KURALI: guclu kanittan zayifa dogru atanir; bir anlam
    # (koku) alindiysa sonraki kisaltma kendi siradaki adayina gecer.
    alinan = set()
    sonuc = {}
    sira = sorted(adaylar, key=lambda p: (adaylar[p][1][0][0][0],
                                          adaylar[p][0]), reverse=True)
    for parca in sira:
        adet, liste = adaylar[parca]
        for (ayirt, destek), anahtar in liste:
            if anahtar in alinan or any(k in alinan for k in anahtar.split(" ")):
                continue
            bicimler = yuzey[anahtar]
            anlam = min(bicimler, key=lambda y: (len(y), -bicimler[y]))
            anlam = " ".join(_yalin(k, sozcukler) for k in anlam.split(" "))
            alinan.add(anahtar)
            # Kendini anlatan parca (BAHIS -> bahis, BAHIS -> "bahis
            # sirketlerine") listeyi kalabaliklastirir.
            if _sade(anlam).replace(" ", "") == parca.lower() \
                    or parca.lower() in _sade(anlam).split(" "):
                break
            sonuc[parca] = {"anlam": anlam,
                            "kolon": int(adet), "destek": round(destek, 3),
                            "ayirt": round(ayirt, 3)}
            break
    return sonuc


BIRLIKTE_ESIK = 0.5


def bilinen_anlam(parca, onay=None):
    """Kesin bilinen anlam: onayli hafiza, yoksa temel sozluk."""
    onay = onaylilar() if onay is None else onay
    return onay.get(parca) or temel_anlam(parca)


def birlikte_bilinenler(parca_kumeleri, parca, esik=BIRLIKTE_ESIK, onay=None):
    """parca'nin kolonlarinin en az esik kadarinda birlikte gecen ve
    anlami KESIN bilinen kisaltmalar: {KISA: anlam}."""
    onay = onaylilar() if onay is None else onay
    icinde = [ps for ps in parca_kumeleri if parca in ps]
    if not icinde:
        return {}
    say = Counter(p for ps in icinde for p in ps if p != parca)
    return {p: bilinen_anlam(p, onay) for p, n in say.items()
            if n / float(len(icinde)) >= esik and bilinen_anlam(p, onay)}


def yasak_kokler(parca_kumeleri, parca, onay=None):
    """Bu parcaya verilemeyecek anlam kokleri (birlikte gecen bilinen
    kisaltmalarin anlamlari)."""
    return set(_sade(k) for a in birlikte_bilinenler(parca_kumeleri, parca, onay=onay).values()
               for k in a.split() if len(k) >= 3)


def _yasakli(kelimeler, yasak):
    """Kelimelerden biri yasak bir anlamla BASLIYOR mu ("gunun" -> "gun",
    "adedi" -> "adet" degil). Kok 5 harfle kesildigi icin kisa kelimeler
    ("gun") esitlikle yakalanmiyordu."""
    return any(_sade(k).startswith(y) for k in kelimeler for y in yasak)


_YUMUSAK = {"d": "t", "ğ": "k", "b": "p", "c": "ç", "g": "k"}


def _yalin(kelime, sozcukler):
    """Ekli bicimi YALNIZ yalin hali sozlukte de geciyorsa yalina indirir
    (adedi -> adet, orani -> oran, bayragi -> bayrak, entropisi ->
    entropi). Sozlukte yalin hali yoksa dokunulmaz: "kredi" -> "kred"
    gibi bozulmalar boylece olmaz; kalanlari dil modeli kontrolu duzeltir."""
    k = str(kelime or "")
    adaylar = []
    if len(k) > 5 and k[-3:-2] and k.endswith(("sı", "si", "su", "sü")):
        adaylar.append(k[:-2])
    if len(k) >= 4 and k.endswith(("ı", "i", "u", "ü")):
        govde = k[:-1]
        adaylar.append(govde)
        if govde and govde[-1] in _YUMUSAK:
            adaylar.append(govde[:-1] + _YUMUSAK[govde[-1]])
    for a in adaylar:
        if a in sozcukler:
            return a
    # Yumusama: "adedi" -> "adet" sozlukte hic gecmese de, "adet" yalin
    # bicimi baska bir kokle (ade) ayni ise kabul edilmez; bilerek kati.
    return k


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


def _temel_satirlar(tanimlar):
    """Kaynaktaki kolon adlarinda gecen TEMEL kisaltmalar: {KISA: adet}."""
    say = Counter()
    for ad in (tanimlar or {}):
        for p in set(parcalar(ad)):
            if temel_anlam(p):
                say[p] += 1
    return say


# ---------------------------------------------------------------------------
# 3) DIL MODELI KONTROLU - arka planda, onbellekli
# ---------------------------------------------------------------------------
ORNEK_SAYISI = 4          # kisaltma basina modele giden ornek kolon
DM_BEKLE_SN = 25.0        # kart kurulurken sonucu en cok bu kadar bekler
_DM = {}                  # imza -> {"durum", "sonuc", "zaman"}
_DM_KILIT = threading.Lock()


def _ornekler(tanimlar, parca):
    cikti = []
    for ad, t in (tanimlar or {}).items():
        if str(t or "").strip() and parca in parcalar(ad):
            cikti.append((ad, str(t)[:160]))
            if len(cikti) >= ORNEK_SAYISI:
                break
    return cikti


def _dm_girdisi(tanimlar):
    """Kontrol edilecek kisaltmalar: kural tabanli cikarilanlar + anlami
    bulunamayan ama EN_AZ_KOLON kolonda gecen kisaltmalar. Temel ve
    onayli olanlar sorulmaz."""
    cikan = cikar(tanimlar)
    onay = onaylilar()
    say = Counter(p for ad, t in (tanimlar or {}).items() if str(t or "").strip()
                  for p in set(parcalar(ad)))
    girdi = []
    for parca, adet in say.most_common():
        if adet < EN_AZ_KOLON or temel_anlam(parca) or parca in onay:
            continue
        if parca not in cikan and parca.isalpha() and len(parca) > 6:
            continue        # uzun duz kelime (BAHIS, SEHIR...) kisaltma degil
        ornek = _ornekler(tanimlar, parca)
        # Orneklerdeki DIGER kisaltmalarin kesin anlamlari: model hangi
        # kelimenin baska kisaltmaya ait oldugunu gorsun.
        bilinen = {}
        for ad, _t in ornek:
            for p in parcalar(ad):
                if p != parca and bilinen_anlam(p, onay):
                    bilinen[p] = bilinen_anlam(p, onay)
        girdi.append({"kisaltma": parca,
                      "anlam": (cikan.get(parca) or {}).get("anlam", ""),
                      "ornekler": ornek, "bilinen": bilinen})
    return girdi[:EN_COK]


def _imza(girdi):
    return "|".join("%s=%s" % (g["kisaltma"], g["anlam"]) for g in girdi)


def _dm_calis(imza, girdi):
    try:
        from fe_agent import llm as llm_mod
        sonuc, _hata = llm_mod.kisaltma_dogrula(girdi)
    except Exception:
        sonuc = None
    with _DM_KILIT:
        _DM[imza] = {"durum": "bitti" if sonuc is not None else "hata",
                     "sonuc": sonuc or {}, "zaman": time.time()}


def dogrulamayi_baslat(tanimlar):
    """Dil modeli kontrolunu arka planda baslatir (ayni liste icin bir kez).
    Doner: imza."""
    girdi = _dm_girdisi(tanimlar)
    imza = _imza(girdi)
    if not girdi:
        return imza
    with _DM_KILIT:
        k = _DM.get(imza)
        if k and k["durum"] in ("calisiyor", "bitti"):
            return imza
        _DM[imza] = {"durum": "calisiyor", "sonuc": {}, "zaman": time.time()}
        if len(_DM) > 20:                       # eski kayitlari kirp
            for eski in sorted(_DM, key=lambda x: _DM[x]["zaman"])[:len(_DM) - 20]:
                if _DM[eski]["durum"] != "calisiyor":
                    _DM.pop(eski, None)
    threading.Thread(target=_dm_calis, args=(imza, girdi), daemon=True).start()
    return imza


def dogrulama_sonucu(tanimlar, bekle=0.0):
    """Doner: (sonuc, durum). sonuc: {KISA: {"anlam", "karar"}} — karar
    "dogru" / "duzeltildi" / "emin_degil". durum: "yok" / "calisiyor" /
    "bitti" / "hata"."""
    imza = dogrulamayi_baslat(tanimlar)
    son = time.time() + max(0.0, bekle)
    while True:
        with _DM_KILIT:
            k = dict(_DM.get(imza) or {})
        if not k:
            return {}, "yok"
        if k["durum"] != "calisiyor" or time.time() >= son:
            return k["sonuc"], k["durum"]
        time.sleep(0.3)


def oneriler(tanimlar, bekle=0.0):
    """Onayli olmayan kisaltmalarin onerilen anlamlari.
    Doner: ({KISA: {"anlam", "kaynak", "kolon", "destek"}}, dm_durum)
      kaynak: "temel" / "sozluk" / "dil_modeli" / "dil_modeli_dogruladi"."""
    cikan = cikar(tanimlar)
    dm, durum = dogrulama_sonucu(tanimlar, bekle)
    cikti = {}
    for kisa, adet in _temel_satirlar(tanimlar).items():
        cikti[kisa] = {"anlam": temel_anlam(kisa), "kaynak": "temel",
                       "kolon": int(adet), "destek": None}
    for kisa, c in cikan.items():
        cikti[kisa] = {"anlam": c["anlam"], "kaynak": "sozluk",
                       "kolon": c["kolon"], "destek": c["destek"]}
    say = Counter(p for ad, t in (tanimlar or {}).items() if str(t or "").strip()
                  for p in set(parcalar(ad)))
    kumeler = [set(parcalar(ad)) for ad, t in (tanimlar or {}).items()
               if str(t or "").strip()]
    onay = onaylilar()
    for kisa, d in dm.items():
        # KAPI: dil modeli de birlikte gectigi bilinen kisaltmanin anlamini
        # verdiyse (ADT -> "farkli", DISTINCT'in) kabul edilmez.
        if d.get("anlam") and _yasakli(d["anlam"].split(),
                                       yasak_kokler(kumeler, kisa, onay)):
            d = {"anlam": "", "karar": "emin_degil"}
        if kisa in cikti and cikti[kisa]["kaynak"] == "temel":
            continue
        onceki = cikti.get(kisa) or {"kolon": int(say.get(kisa, 0)), "destek": None}
        if d["karar"] == "dogru" and kisa in cikan:
            onceki["kaynak"] = "dil_modeli_dogruladi"
            cikti[kisa] = onceki
        elif d["karar"] == "duzeltildi" and d.get("anlam") \
                and _sade(d["anlam"]).replace(" ", "") == kisa.lower():
            continue            # kendini anlatan kelime (TARIH -> tarih)
        elif d["karar"] == "duzeltildi" and d.get("anlam"):
            cikti[kisa] = dict(onceki, anlam=d["anlam"], kaynak="dil_modeli",
                               sozlukten=(cikan.get(kisa) or {}).get("anlam", ""))
        elif d["karar"] == "emin_degil" and kisa in cikti:
            # Dil modeli emin olamadi: kural tabanli tahmin gosterilmez,
            # anlam bos kalir (yanlis anlam bos anlamdan kotu).
            cikti[kisa] = dict(onceki, anlam="", kaynak="emin_degil")
    return cikti, durum


def birlesik(tanimlar):
    """Isteme giden kisaltmalar: (kesin, tahmini).
      kesin  : ONAYLI + TEMEL (her zaman gecerli)
      tahmini: sozlukten cikarilan / dil modelinin onerdigi (onayli ya da
               temel olmayanlar). Dil modeli kontrolu bitmediyse beklemez."""
    oner, _d = oneriler(tanimlar, 0.0)
    kesin = dict(TEMEL)
    for kisa, o in oner.items():
        if o["kaynak"] == "temel":
            kesin[kisa] = o["anlam"]
    kesin.update(onaylilar())
    tahmini = {k: o["anlam"] for k, o in oner.items()
               if o["anlam"] and k not in kesin}
    return kesin, tahmini


_KANIT = {
    "temel": "Temel sözlük",
    "sozluk": "Sözlükten",
    "dil_modeli_dogruladi": "Dil modeli doğruladı",
    "dil_modeli": "Dil modeli önerdi",
    "emin_degil": "Dil modeli emin olamadı",
}


def kart_satirlari(tanimlar, bekle=0.0):
    """Kartta gosterilecek satirlar: onaylilar + oneriler.
    Doner: (satirlar, dm_durum). satir: {kisaltma, anlam, onayli, kanit,
    cikarilan, kaynak} - kolon sayisina gore."""
    oner, durum = oneriler(tanimlar, bekle)
    onay = onaylilar()
    satirlar = []
    for kisa in sorted(set(oner) | set(onay),
                       key=lambda k: (-(oner.get(k) or {}).get("kolon", 0), k)):
        o = oner.get(kisa) or {}
        parca = []
        if o:
            parca.append(_KANIT.get(o["kaynak"], ""))
            if o.get("sozlukten"):
                parca.append("sözlükten çıkan: %s" % o["sozlukten"])
            if o.get("destek") is not None:
                parca.append("%d kolonun %%%d'inde" % (o["kolon"], round(o["destek"] * 100)))
            elif o.get("kolon"):
                parca.append("%d kolonda" % o["kolon"])
        satirlar.append({"kisaltma": kisa,
                         "anlam": onay.get(kisa) or o.get("anlam") or "",
                         "cikarilan": o.get("anlam") or "",
                         "kaynak": o.get("kaynak") or "",
                         "onayli": kisa in onay, "kanit": " · ".join(p for p in parca if p)})
    return satirlar[:EN_COK], durum
