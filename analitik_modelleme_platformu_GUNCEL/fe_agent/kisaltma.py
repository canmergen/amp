# -*- coding: utf-8 -*-
"""fe_agent/kisaltma.py - KOLON ADI KISALTMALARI: sozlukten OGRENILEN
anlamlar + onayli kisaltma hafizasi (proje geneli).

Kullanici karari: "kisaltmalari onceden verme kismini begenmedim; kendi
kendine gelisen, guncellenen bir sistem istiyorum. Sozlukteki aciklamalara
bakip 'kullanici bunu yazmis, demek ki bundan bahsediyor' diyebilmeli."
Bu yuzden SABIT KISALTMA LISTESI YOK: her anlam o calismanin sozlugunden
ve onayli tanim hafizasindan ogrenilir. Yeni onaylanan her tanim bir
sonraki cikarimin girdisidir; sistem kullanildikca kendini gunceller.

1) ISTATISTIK (cikar) - butun tanimlar:
   Kolon adi parcalara bolunur (TXN_GLN_BAHIS_180D_AMT -> TXN, GLN, BAHIS,
   AMT; 180D gibi pencereler ve saf sayilar atlanir). Her parca icin
   adinda o parca gecen TUM tanimli kolonlarin tanimlarinda gecen
   kelimeler (ve iki kelimelik ifadeler) sayilir:
     destek: kelime, parcayi tasiyan tanimlarin yuzde kacinda geciyor
     ayirt : destek - (parcayi TASIMAYAN tanimlardaki pay)
   Adaylar en guclu kanittan zayifa dogru ATANIR. Bir parca, kolonlarinin
   yarisindan fazlasinda birlikte gectigi bir parcaya zaten verilmis
   (ya da onayli) anlami alamaz: IN_7D_CP_CNT'de "karsi taraf" once CP'ye
   gider, IN ikinci adayina ("gelen") gecer. Ekli bicim, yalin hali
   sozlukte de geciyorsa yalina iner (adedi -> adet).

2) DIL MODELI (dogrulamayi_baslat) - her kisaltma icin:
   istatistigin en guclu 3 adayi ve yuzdeleri, ornek kolonlarda gecen
   DIGER kisaltmalarin anlamlari ve CESITLI secilmis en cok 8 ornek kolon
   (her yeni ornek, oncekilerde olmayan parcalari getirenlerden secilir)
   iki modele sorulur; anlasamazlarsa hakem karar verir. Emin olunamayan
   anlam bos kalir. Arka planda calisir, sonuc onbellekte tutulur.

3) HAFIZA - PROJE_HAFIZASI/KISALTMA_HAFIZASI.parquet (calisma klasorlerinin
   disinda). YALNIZ kullanicinin onayladigi kisaltmalar girer ve her
   zaman ogrenilenin onune gecer. Girdi veri setine ve sozluge hicbir
   kosulda yazilmaz. OKUMA HATASI YAZMAYI DURDURUR: dosya var ama
   okunamiyorsa ustune yazilmaz.

Dil modeline giden istemde: onayli kisaltmalar KESIN, ogrenilenler
TAHMINI etiketiyle gider."""

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
KAYNAK_ONAY = "sözlükten öğrenildi, kullanıcı onayladı"
KAYNAK_KULLANICI = "kullanıcı yazdı"

EN_AZ_KOLON = 3        # parca en az bu kadar tanimli kolonun adinda gecmeli
DESTEK_ESIK = 0.6      # anlam, o kolonlarin tanimlarinin en az bu kadarinda
AYIRT_ESIK = 0.3       # ... ve digerlerinden en az bu kadar daha sik
BIRLIKTE_ESIK = 0.5    # bu kadar birlikte gecen parcalar ayni anlami alamaz
ADAY_SAYISI = 3        # dil modeline giden istatistik adayi
EN_COK = 300           # kartta gosterilen en cok kisaltma

_TR_KUCUK = str.maketrans({"I": "ı", "İ": "i"})
_TR_SADE = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
_PENCERE = re.compile(r"^\d+[DAMYH]?$", re.I)     # 180D, 3A, 12, 6M
# Anlam tasimayan baglaclar. "gun", "ay" artik DURAK DEGIL: DAY / MONTH
# gibi kisaltmalarin anlami olabilirler; pencereli tanimlarin hepsinde
# gectikleri icin ayirt olcusu onlari zaten eler.
_DURAK = {"ve", "ile", "icin", "olan", "bir", "bu", "da", "de", "gore", "son"}

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




def _parca_istatistigi(tanimlar):
    """Ortak hazirlik: (satirlar, parca_say, genel, yuzey, sozcukler).
    satirlar: [(parca_kumesi, tekli, ikili)] - yalniz tanimli kolonlar."""
    satirlar = []
    for ad, tanim in (tanimlar or {}).items():
        if not str(tanim or "").strip():
            continue
        tekli, ikili = _tanim_kokleri(tanim)
        satirlar.append((set(parcalar(ad)), tekli, ikili))
    genel = Counter()
    yuzey = {}
    sozcukler = set()
    for _p, tekli, ikili in satirlar:
        sozcukler.update(tekli.values())
        for k, y in list(tekli.items()) + list(ikili.items()):
            genel[k] += 1
            yuzey.setdefault(k, Counter())[y] += 1
    parca_say = Counter(p for ps, _t, _i in satirlar for p in ps)
    return satirlar, parca_say, genel, yuzey, sozcukler


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
    Kok 5 harfle kesildigi icin kisa kelimeler esitlikle yakalanmiyordu."""
    return any(_sade(k).startswith(y) for k in kelimeler for y in yasak if y)


def _anlam_kelimeleri(anlam):
    return set(_sade(k) for k in str(anlam or "").split() if len(k) >= 3)


def adaylar(tanimlar):
    """Her parca icin istatistik adaylari.
    Doner: {KISA: {"kolon": n, "adaylar": [{"anlam", "destek", "ayirt"}]}}
    (en gucluden zayifa; iki kelimelik ifade, kelimesi bu parcaya ozguyse
    tek kelimeden once gelir)."""
    satirlar, parca_say, genel, yuzey, sozcukler = _parca_istatistigi(tanimlar)
    n = len(satirlar)
    cikti = {}
    if n < EN_AZ_KOLON:
        return cikti
    for parca, adet in parca_say.items():
        if adet < EN_AZ_KOLON or adet == n:
            continue
        icinde = Counter()
        for ps, tekli, ikili in satirlar:
            if parca in ps:
                icinde.update(set(tekli) | set(ikili))
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
        sirali = sorted(tekli, key=lambda k: (tekli[k][0], tekli[k][1],
                                              _harf_uyumu(parca, k), -len(k)),
                        reverse=True)
        liste = []
        for en_iyi in sirali:
            sinir = tekli[en_iyi][0] - 0.05
            # IKI KELIMELIK IFADE yalniz iki kelimesi de bu kisaltmaya ozgu
            # ise ("hafta sonu", "karsi taraf"); tek kelime yedek olarak
            # hemen arkasinda kalir.
            for k, (ayirt, _d) in puan.items():
                if " " in k and en_iyi in k.split(" ") and ayirt >= sinir and all(
                        (tekli.get(p) or (0, 0))[0] >= sinir for p in k.split(" ")):
                    liste.append(k)
                    break
            liste.append(en_iyi)
        goruldu, adaylar_ = set(), []
        for anahtar in liste:
            if anahtar in goruldu:
                continue
            goruldu.add(anahtar)
            bicimler = yuzey[anahtar]
            anlam = min(bicimler, key=lambda y: (len(y), -bicimler[y]))
            anlam = " ".join(_yalin(k, sozcukler) for k in anlam.split(" "))
            ayirt, destek = puan[anahtar]
            adaylar_.append({"anlam": anlam, "destek": round(destek, 3),
                             "ayirt": round(ayirt, 3)})
        cikti[parca] = {"kolon": int(adet), "adaylar": adaylar_}
    return cikti


def cikar(tanimlar, aday=None):
    """{kolon: tanim} -> {KISALTMA: {"anlam", "kolon", "destek", "ayirt"}}.

    Atama en guclu kanittan baslar; bir parca, birlikte gectigi parcaya
    verilmis ya da onayli anlami alamaz (siradaki adaya gecer, aday
    kalmazsa parca listede yer almaz)."""
    aday = adaylar(tanimlar) if aday is None else aday
    if not aday:
        return {}
    satirlar, parca_say, _g, _y, _s = _parca_istatistigi(tanimlar)
    onay = onaylilar()
    atanan = {k: v for k, v in onay.items()}       # parca -> anlam
    sonuc = {}
    sira = sorted(aday, key=lambda p: (aday[p]["adaylar"][0]["ayirt"],
                                       aday[p]["kolon"]), reverse=True)
    for parca in sira:
        if parca in onay:
            continue
        yasak = set()
        for q in _birlikte(satirlar, parca, parca_say):
            if q in atanan:
                yasak |= _anlam_kelimeleri(atanan[q])
        for a in aday[parca]["adaylar"]:
            if _yasakli(a["anlam"].split(" "), yasak):
                continue
            # Kendini anlatan parca (BAHIS -> bahis, "bahis sirketlerine")
            # listeyi kalabaliklastirir.
            if parca.lower() in _sade(a["anlam"]).split(" ") \
                    or _sade(a["anlam"]).replace(" ", "") == parca.lower():
                break
            sonuc[parca] = {"anlam": a["anlam"], "kolon": aday[parca]["kolon"],
                            "destek": a["destek"], "ayirt": a["ayirt"]}
            atanan[parca] = a["anlam"]
            break
    return sonuc


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




# ---------------------------------------------------------------------------
# DIL MODELI - arka planda, onbellekli
# ---------------------------------------------------------------------------
ORNEK_SAYISI = 8          # kisaltma basina modele giden en cok ornek kolon
DM_BEKLE_SN = 25.0        # kart kurulurken sonucu en cok bu kadar bekler
_DM = {}                  # imza -> {"durum", "sonuc", "zaman"}
_DM_KILIT = threading.Lock()


def _ornekler(tanimlar, parca):
    """CESITLI ornek: her adimda, secilenlerde henuz gecmeyen en cok
    parcayi getiren kolon secilir. Hepsi ayni kaliptan (ayni pencere,
    ayni yon) gelen ornekler modele ortak kelimeyi kisaltmanin kendi
    anlami gibi gosteriyordu."""
    havuz = [(ad, str(t)[:160], set(parcalar(ad)))
             for ad, t in (tanimlar or {}).items()
             if str(t or "").strip() and parca in parcalar(ad)]
    secilen, gorulen = [], set([parca])
    while havuz and len(secilen) < ORNEK_SAYISI:
        en = max(range(len(havuz)), key=lambda i: (len(havuz[i][2] - gorulen), -i))
        ad, t, ps = havuz.pop(en)
        secilen.append((ad, t))
        gorulen |= ps
    return secilen


def _dm_girdisi(tanimlar):
    """Modele sorulacak kisaltmalar: EN_AZ_KOLON kolonda gecen ve onayli
    olmayan her parca (istatistik adayi olsun olmasin)."""
    aday = adaylar(tanimlar)
    cikan = cikar(tanimlar, aday)
    onay = onaylilar()
    say = Counter(p for ad, t in (tanimlar or {}).items() if str(t or "").strip()
                  for p in set(parcalar(ad)))
    girdi = []
    for parca, adet in say.most_common():
        if adet < EN_AZ_KOLON or parca in onay:
            continue
        if parca not in aday and parca.isalpha() and len(parca) > 6:
            continue        # uzun duz kelime (BAHIS, SEHIR...) kisaltma degil
        ornek = _ornekler(tanimlar, parca)
        # Orneklerdeki DIGER kisaltmalarin anlamlari (onayli ya da
        # ogrenilen): model hangi kelimenin baska kisaltmaya ait oldugunu
        # gorsun.
        diger = {}
        for ad, _t in ornek:
            for p in parcalar(ad):
                if p != parca and (onay.get(p) or (cikan.get(p) or {}).get("anlam")):
                    diger[p] = onay.get(p) or cikan[p]["anlam"]
        girdi.append({"kisaltma": parca, "kolon": int(adet),
                      "anlam": (cikan.get(parca) or {}).get("anlam", ""),
                      "adaylar": (aday.get(parca) or {}).get("adaylar", [])[:ADAY_SAYISI],
                      "ornekler": ornek, "bilinen": diger})
    return girdi[:EN_COK]


def _imza(girdi):
    return "|".join("%s=%s" % (g["kisaltma"], g["anlam"]) for g in girdi)


def _dm_calis(imza, girdi):
    try:
        from fe_agent import llm as llm_mod
        sonuc, _hata = llm_mod.kisaltma_dogrula(girdi)
    except Exception:
        sonuc = None
    ornek_say = {g["kisaltma"]: len(g["ornekler"]) for g in girdi}
    for k, v in (sonuc or {}).items():
        v["ornek"] = ornek_say.get(k, 0)
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
    """Doner: (sonuc, durum). sonuc: {KISA: {"anlam", "karar", "ornek"}};
    karar "dogru" / "duzeltildi" / "emin_degil". durum: "yok" /
    "calisiyor" / "bitti" / "hata"."""
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
    """Onayli olmayan kisaltmalarin ogrenilen anlamlari.
    Doner: ({KISA: {"anlam", "kaynak", "kolon", "destek", "ornek"}}, dm_durum)
      kaynak: "sozluk" / "dil_modeli_dogruladi" / "dil_modeli" / "emin_degil"."""
    aday = adaylar(tanimlar)
    cikan = cikar(tanimlar, aday)
    dm, durum = dogrulama_sonucu(tanimlar, bekle)
    satirlar, parca_say, _g, _y, _s = _parca_istatistigi(tanimlar)
    onay = onaylilar()
    cikti = {}
    for kisa, c in cikan.items():
        cikti[kisa] = {"anlam": c["anlam"], "kaynak": "sozluk",
                       "kolon": c["kolon"], "destek": c["destek"], "ornek": 0}
    # Kapi icin: birlikte gectigi parcalarin anlamlari (onayli + ogrenilen
    # + dil modelinin verdigi).
    son_anlam = dict(cikan and {k: v["anlam"] for k, v in cikan.items()})
    for k, d in dm.items():
        if d.get("anlam"):
            son_anlam[k] = d["anlam"]
    son_anlam.update(onay)
    for kisa, d in dm.items():
        if kisa in onay:
            continue
        onceki = cikti.get(kisa) or {"kolon": int(parca_say.get(kisa, 0)),
                                     "destek": None}
        onceki["ornek"] = d.get("ornek", 0)
        if d.get("anlam"):
            yasak = set()
            for q in _birlikte(satirlar, kisa, parca_say):
                if q in son_anlam and not _ayni_anlam(son_anlam[q], d["anlam"]):
                    yasak |= _anlam_kelimeleri(son_anlam[q])
            # KAPI: dil modeli birlikte gectigi kisaltmanin anlamini
            # verdiyse (ADT -> "farkli", DISTINCT'in) kabul edilmez.
            if _yasakli(d["anlam"].split(), yasak) \
                    or _sade(d["anlam"]).replace(" ", "") == kisa.lower():
                d = {"anlam": "", "karar": "emin_degil"}
        if d["karar"] == "dogru" and kisa in cikan:
            onceki["kaynak"] = "dil_modeli_dogruladi"
            cikti[kisa] = onceki
        elif d["karar"] in ("duzeltildi", "dogru") and d.get("anlam"):
            cikti[kisa] = dict(onceki, anlam=d["anlam"], kaynak="dil_modeli",
                               sozlukten=(cikan.get(kisa) or {}).get("anlam", ""))
        elif d["karar"] == "emin_degil" and kisa in cikti:
            # Dil modeli emin olamadi: istatistik tahmini gosterilmez,
            # anlam bos kalir (yanlis anlam bos anlamdan kotu).
            cikti[kisa] = dict(onceki, anlam="", kaynak="emin_degil")
    return cikti, durum


def _ayni_anlam(a, b):
    return _sade(a).strip() == _sade(b).strip()


def birlesik(tanimlar):
    """Isteme giden kisaltmalar: (kesin, tahmini).
      kesin  : kullanicinin ONAYLADIKLARI (her zaman gecerli)
      tahmini: sozlukten ogrenilen / dil modelinin verdigi. Dil modeli
               kontrolu bitmediyse beklemez (o ana kadarki sonuc)."""
    oner, _d = oneriler(tanimlar, 0.0)
    kesin = dict(onaylilar())
    tahmini = {k: o["anlam"] for k, o in oner.items()
               if o["anlam"] and k not in kesin}
    return kesin, tahmini


_KANIT = {
    "sozluk": "Sözlükten öğrenildi",
    "dil_modeli_dogruladi": "Dil modeli doğruladı",
    "dil_modeli": "Dil modeli önerdi",
    "emin_degil": "Dil modeli emin olamadı",
}


def kart_satirlari(tanimlar, bekle=0.0):
    """Kartta gosterilecek satirlar: onaylilar + ogrenilenler.
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
            ad = _KANIT.get(o["kaynak"], "")
            if o.get("ornek") and o["kaynak"] != "sozluk":
                ad += " (%d örnekle)" % o["ornek"]
            parca.append(ad)
            if o.get("sozlukten"):
                parca.append("istatistik: %s" % o["sozlukten"])
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
