"""fe_agent/parca.py - 01.2.4.2 AD PARCALARI: kolon adlarindaki rakamsiz
parcalar (kisaltmalar ve sozcukler: TXN, AMT, DAY, TMSNCFRST ...).

Sayili parcalar (30D, M3, 3_M, H00_06 ...) donem.py'de (01.2.4.1 Zaman
Parcalari). Burada kalanlar.

Kaynaklarin ikisine de tam guvenilmez: sozluk tanimlari cogunlukla dogru
ama yer yer yanlis ya da eksik, adlarda da eksik ve yanlis yazilmis
kisaltmalar var. Bu yuzden:
  - anlam once parcanin yapisindan ve yaygin kisaltma bilgisinden kurulur,
    sozlukteki ornek tanimlar KANIT olarak oylanir (llm.parca_yorumla);
  - yazim farki ya da es anlamli olabilecek parcalar (TXN / TRX / TRNS)
    yan yana gosterilir, kullanici ayni mi farkli mi oldugunu soyler;
  - proje hafizasindaki onayli anlamlar oneri olarak dolu gelir (dil
    modeline sorulmaz), kullanici degistirebilir;
  - her parca kullanici tarafindan onaylanir.
Girdi veri seti ve sozluge yazilmaz."""

import hashlib
import json
import re
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from fe_agent import donem as donem_mod
from fe_agent import kisaltma as kisaltma_mod
from fe_agent import llm as llm_mod

ORNEK_ADET = 10           # parca basina modele ve karta giden ornek kolon
TANIM_EN_UZUN = 200       # ornek tanim kirpma
KOMSU_ADET = 3            # parca basina gosterilen en sik komsu
YORUM_PARCA = 12          # dil modeline bir cagrida giden parca
ES_ZAMANLI = 4            # ayni anda en cok bu kadar cagri
ISTEM_SURUMU = 1

# TURLER: parcanin adda tasidigi bilginin turu. Zaman turleri donem
# turleriyle ayni anlamda (pencere, nokta, zaman_birim, sure); kolon adinda
# hepsi "zaman" yerine yazilir (bkz. AD_YERI).
TURLER = [
    ("konu", "Konu", "Ölçümün konusu olan varlık ya da olay (işlem, kredi, müşteri)."),
    ("yon", "Yön", "Hareketin yönü (giriş, çıkış, borç, alacak)."),
    ("nitelik", "Nitelik", "Ölçümü daraltan alt küme ya da özellik (kanal, ürün, taraf)."),
    ("olcu", "Ölçü", "Ölçülen büyüklük (tutar, adet, bakiye, oran)."),
    ("istatistik", "İstatistik", "Uygulanan hesap (toplam, ortalama, en büyük, fark)."),
    ("karsilastirma", "Karşılaştırma", "İki şeyin oranı ya da farkı (önceki döneme göre)."),
    ("pencere", "Zaman Penceresi", "Verinin alındığı süre ya da aralık (son dönem, dönem başından bugüne)."),
    ("nokta", "Zaman Noktası", "Belirli bir an ya da sıra (ay sonu, gözlem tarihi)."),
    ("zaman_birim", "Zaman Birimi", "Sayısız zaman birimi (DAY: gün, MONTH: ay)."),
    ("sure", "Geçen Süre", "Değerin kendisi bir süre (ilk işlemden bu yana geçen süre, yaş, vade)."),
    ("birim", "Birim", "Değerin birimi (TL, USD)."),
    ("diger", "Diğer", "Bayrak, düzey ya da bunlara girmeyen."),
]
TUR_KODLARI = [t for t, _a, _c in TURLER]
# Kolon adinda parcanin yeri (ad standardi bu yerlerin sirasidir).
AD_YERI = {"pencere": "zaman", "nokta": "zaman", "zaman_birim": "zaman", "sure": "zaman"}
# Donem turu -> parca turu (Zaman sekmesindeki kaliplar kolon kartina
# bu turle girer).
DONEM_TURU = {"pencere": "pencere", "nokta": "nokta", "birim": "zaman_birim", "olcu": "sure"}
# Eski kisaltma hafizasindaki tur kodlari.
ESKI_TUR = {"konu": "konu", "yon": "yon", "nitelik": "nitelik", "pencere": "pencere",
            "olcu": "olcu", "istatistik": "istatistik", "diger": "diger"}

STANDART_DESEN = re.compile(r"^[A-Z][A-Z0-9]{0,11}$")
_SESLI = set("AEIOUÖÜİI")

_KILIT = threading.Lock()
_ISLER = {}               # imza -> {"durum", "sonuc", "hata", "zaman", "iptal"}


# ---------------------------------------------------------------------------
# PARCALAR
# ---------------------------------------------------------------------------
def toklar(ad):
    return donem_mod._toklar(ad)


def sayili_konumlar(t):
    """Ad parcalarindan sayili kaliplarin (Zaman sekmesi) kapsadiklari:
    yalniz rakam, 30D / M3 gibi sayili parca, 3_M / M_3 ikilisi, H00_06
    araligi (donem.kaliplar ile ayni kurallar)."""
    konum = set()
    i = 0
    while i < len(t):
        p = t[i]
        if donem_mod.ayrik_ikili(t, i):
            konum.update((i, i + 1))
            i += 2
            continue
        if donem_mod._YALIN_SAYI.match(p) or donem_mod._donem_parcasi(p):
            konum.add(i)
            if donem_mod._araligin_basi(t, i):
                konum.add(i + 1)
                i += 2
                continue
        i += 1
    return konum


def _secilmis(liste, adet):
    """Listeden bastan sona esit aralikli en cok `adet` oge (siralama
    korunur; rastgele degil)."""
    if len(liste) <= adet:
        return list(liste)
    adim = len(liste) / float(adet)
    return [liste[int(i * adim)] for i in range(adet)]


def parcalar(adlar, tanimlar, desenler=()):
    """Kolon adlarindaki rakamsiz parcalar: [{"parca", "kolon": gectigi
    kolon sayisi, "ornekler": [(kolon, tanim)], "tanimsiz": tanimi olmayan
    kolon sayisi, "birlikte": [(komsu parca, kolon sayisi)]}], kolon
    sayisina gore (cok olan once). Ornekler tanimi dolu kolonlardan,
    listenin basindan sonuna esit aralikla secilir. desenler: Zaman
    Parcalari'nda onaylanan kaliplarin desenleri; eslesen parca zaman
    parcasidir, burada yer almaz."""
    tanimlar = tanimlar or {}
    kolonlar, komsu = {}, {}
    for ad in adlar:
        t = toklar(ad)
        sayili = sayili_konumlar(t)
        sayili.update(i for i, p in enumerate(t) if any(r.match(p) for r in desenler))
        gorulen = set()
        for i, p in enumerate(t):
            if i in sayili or p in gorulen:
                continue
            gorulen.add(p)
            kolonlar.setdefault(p, []).append(ad)
            c = komsu.setdefault(p, Counter())
            for j in (i - 1, i + 1):
                if 0 <= j < len(t) and j not in sayili and t[j] != p:
                    c[t[j]] += 1
    cikti = []
    for p, liste in kolonlar.items():
        dolu = [a for a in liste if str(tanimlar.get(a) or "").strip()]
        ornek = [(a, str(tanimlar.get(a)).strip()[:TANIM_EN_UZUN])
                 for a in _secilmis(dolu, ORNEK_ADET)]
        if not ornek:
            ornek = [(a, "") for a in _secilmis(liste, 3)]
        cikti.append({"parca": p, "kolon": len(liste), "ornekler": ornek,
                      "tanimsiz": len(liste) - len(dolu),
                      "birlikte": komsu[p].most_common(KOMSU_ADET)})
    cikti.sort(key=lambda x: (-x["kolon"], x["parca"]))
    return cikti


# ---------------------------------------------------------------------------
# YAZIM FARKI / ES ANLAM ADAYLARI
# ---------------------------------------------------------------------------
def _iskelet(p):
    return "".join(h for h in p if h not in _SESLI)


def _uzaklik(a, b):
    """Duzenleme uzakligi (yer degistirme bir islem sayilir)."""
    n, m = len(a), len(b)
    if abs(n - m) > 2:
        return 3
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1,
                          d[i - 1][j - 1] + (a[i - 1] != b[j - 1]))
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[n][m]


def benzer_ciftler(liste):
    """Yazimi birbirine yakin parca ciftleri: [(a, b, neden)]. Nedenler:
    sessiz harf iskeleti ayni (TRX / TRAX), tek harf farki (TXN / TXM;
    uzunluk en az 4), biri otekinin basi (BAL / BALANCE; kisa olan en az 3
    harf). Yalniz harflerden olusan parcalar karsilastirilir."""
    adaylar = sorted({x["parca"] for x in liste
                      if x["parca"].isalpha() and len(x["parca"]) >= 3})
    cikti = []
    iskelet = {}
    for p in adaylar:
        iskelet.setdefault(_iskelet(p), []).append(p)
    gorulen = set()
    for grup in iskelet.values():
        if len(_iskelet(grup[0])) >= 2:
            for i, a in enumerate(grup):
                for b in grup[i + 1:]:
                    gorulen.add((a, b))
                    cikti.append((a, b, "Sessiz harfleri aynı"))
    for i, a in enumerate(adaylar):
        for b in adaylar[i + 1:]:
            if (a, b) in gorulen:
                continue
            kisa, uzun = (a, b) if len(a) <= len(b) else (b, a)
            if len(kisa) >= 4 and _uzaklik(a, b) == 1:
                cikti.append((a, b, "Bir harf farklı"))
            elif len(kisa) >= 3 and uzun.startswith(kisa) and len(uzun) >= len(kisa) + 2:
                cikti.append((a, b, "Biri ötekinin kısaltması olabilir"))
    return cikti


def gruplar(ciftler):
    """Ciftlerden birlesik gruplar (bir parca bir grupta): [[parca, ...]],
    her grup sirali."""
    ust = {}

    def bul(x):
        while ust.setdefault(x, x) != x:
            ust[x] = ust[ust[x]]
            x = ust[x]
        return x
    for a, b, _n in ciftler:
        ra, rb = bul(a), bul(b)
        if ra != rb:
            ust[rb] = ra
    g = {}
    for x in list(ust):
        g.setdefault(bul(x), []).append(x)
    return [sorted(v) for v in g.values() if len(v) > 1]


# ---------------------------------------------------------------------------
# HAFIZA (KISALTMA_HAFIZASI.json): "parcalar" {PARCA: {anlam, tur,
# standart}}, "parca_esler" {"A|B": "ayni" | "farkli"}. Eski kayitlar
# (kisaltmalar, degisimler, turler, rakamsiz donem kaliplari) oneri olarak
# okunur.
# ---------------------------------------------------------------------------
def hafiza():
    """{PARCA: {"anlam", "tur", "standart"}} (yoksa {})."""
    try:
        govde, _h = kisaltma_mod._govde_oku()
    except Exception:
        govde = None
    govde = govde if isinstance(govde, dict) else {}
    cikti = {}
    # Eski kisaltma hafizasi: anlam, standart (degisim), tur (anlam anahtari).
    try:
        from fe_agent import kisaltma_okuma
        eski = kisaltma_mod.onaylilar()
        degisim = kisaltma_mod.degisimler()
        turler = (govde.get("turler") or {}) if isinstance(govde.get("turler"), dict) else {}
        for k, an in eski.items():
            tur = ESKI_TUR.get(str(turler.get(kisaltma_okuma.anahtar(an)) or ""), "")
            cikti[str(k).upper()] = {"anlam": str(an), "tur": tur,
                                     "standart": degisim.get(str(k).upper(), "")}
    except Exception:
        pass
    # Rakamsiz donem kaliplari (DAY, MONTH): zaman turuyle.
    donem = govde.get("donem") if isinstance(govde.get("donem"), dict) else {}
    dtur = govde.get("donem_tur") if isinstance(govde.get("donem_tur"), dict) else {}
    for k, an in donem.items():
        k = str(k).upper()
        if "<" in k or not str(an or "").strip() or not k.isalnum():
            continue
        cikti.setdefault(k, {"anlam": str(an), "tur": DONEM_TURU.get(str(dtur.get(k) or ""), "zaman_birim"),
                             "standart": ""})
    # Yeni bicim en son: ustune yazar.
    yeni = govde.get("parcalar") if isinstance(govde.get("parcalar"), dict) else {}
    for k, v in yeni.items():
        if isinstance(v, dict) and str(v.get("anlam") or "").strip():
            cikti[str(k).upper()] = {"anlam": str(v["anlam"]),
                                     "tur": str(v.get("tur") or "") if str(v.get("tur") or "") in TUR_KODLARI else "",
                                     "standart": str(v.get("standart") or "")}
    return cikti


def hafiza_esler():
    """{"A|B": "ayni" | "farkli"} (A < B)."""
    try:
        govde, _h = kisaltma_mod._govde_oku()
    except Exception:
        return {}
    es = (govde or {}).get("parca_esler")
    return {str(k): str(v) for k, v in es.items()} if isinstance(es, dict) else {}


def es_anahtari(a, b):
    a, b = sorted((str(a).upper(), str(b).upper()))
    return a + "|" + b


def hafizaya_yaz(kayitlar, esler=None):
    """kayitlar: {PARCA: {"anlam", "tur", "standart"}} (eklenir ya da
    guncellenir); esler: {"A|B": "ayni" | "farkli"}. Doner: hata ya da None."""
    return kisaltma_mod.parca_kaydet(kayitlar, esler)


# ---------------------------------------------------------------------------
# ARKA PLAN: dil modeli yorumu
# ---------------------------------------------------------------------------
def _imza(liste):
    ham = json.dumps([ISTEM_SURUMU] + [[x["parca"], x["kolon"], x["ornekler"], x["birlikte"]]
                                       for x in liste], ensure_ascii=False)
    return hashlib.sha1(ham.encode("utf-8")).hexdigest()[:16]


def baslat(liste):
    """Hafizada olmayan parcalari arka planda dil modeline yorumlatir.
    Doner: imza."""
    imza = _imza(liste)
    with _KILIT:
        k = _ISLER.get(imza)
        if k and k["durum"] in ("calisiyor", "bitti"):
            return imza
        _ISLER[imza] = {"durum": "calisiyor", "sonuc": {}, "hata": "", "zaman": time.time(),
                        "biten": 0, "toplam": 0}
    haf = hafiza()
    sorulacak = [x for x in liste if x["parca"] not in haf]
    _ISLER[imza]["toplam"] = len(sorulacak)

    def calis():
        k = _ISLER[imza]
        hatalar = []
        gorevler = [sorulacak[i:i + YORUM_PARCA] for i in range(0, len(sorulacak), YORUM_PARCA)]

        def yap(parca):
            if k.get("iptal"):
                return ""
            sonuc, hata = llm_mod.parca_yorumla(parca)
            with _KILIT:
                if not k.get("iptal"):
                    k["sonuc"].update(sonuc)
                    k["biten"] += len(parca)
            return hata
        try:
            with ThreadPoolExecutor(max_workers=ES_ZAMANLI) as ex:
                for hata in ex.map(yap, gorevler):
                    if hata:
                        hatalar.append(hata)
            if k.get("iptal"):
                return
            k["hata"] = " ".join(hatalar)
            k["durum"] = "bitti"
        except Exception as e:
            if k.get("iptal"):
                return
            k["hata"] = "%s: %s" % (type(e).__name__, str(e)[:200])
            k["durum"] = "hata"
    if sorulacak:
        threading.Thread(target=calis, daemon=True).start()
    else:
        _ISLER[imza]["durum"] = "bitti"
    return imza


def iptal(imza):
    """Suren yorumu durdurur; gelenler kalir."""
    with _KILIT:
        k = _ISLER.get(imza or "")
        if k and k["durum"] == "calisiyor":
            k["iptal"] = True
            k["durum"] = "bitti"


def durum(imza):
    k = _ISLER.get(imza or "")
    if not k:
        return {"durum": "yok", "sonuc": {}, "hata": "", "gecen": 0, "iptal": False,
                "biten": 0, "toplam": 0}
    with _KILIT:
        return {"durum": k["durum"], "sonuc": dict(k["sonuc"]), "hata": k["hata"],
                "gecen": int(time.time() - k["zaman"]), "iptal": bool(k.get("iptal")),
                "biten": k.get("biten", 0), "toplam": k.get("toplam", 0)}


# ---------------------------------------------------------------------------
# KOLON ADLARI (01.2.4.4): yeni ad onayli parcalarin standart yazilislariyla
# kurulur; birimler AD STANDARDI'ndaki yer sirasina dizilir (ayni yerdekiler
# adda gectikleri sirayla). Sayili zaman parcalari (30D, H00_06) adda
# yazildigi gibi kalir, yeri "zaman". Standart proje hafizasinda
# ("parca_ad_standardi"); burada olusturulur.
# ---------------------------------------------------------------------------
# Varsayilan sira: zaman olcu ve istatistikten sonra (TXN_CNT_30D); boylece
# konusu olmayan ad da sayiyla baslamaz (AMT_SUM_3M).
AD_YERLERI = [
    ("konu", "Konu"), ("yon", "Yön"), ("nitelik", "Nitelik"), ("olcu", "Ölçü"),
    ("istatistik", "İstatistik"), ("zaman", "Zaman"), ("karsilastirma", "Karşılaştırma"),
    ("birim", "Birim"), ("diger", "Diğer")]
VARSAYILAN_SIRA = [k for k, _a in AD_YERLERI]
AYRAC = "_"


def ad_yeri(tur):
    t = str(tur or "")
    return AD_YERI.get(t, t if t in VARSAYILAN_SIRA else "diger")


def sira_temizle(sira):
    cikti = []
    for k in sira or []:
        k = str(k or "")
        if k in VARSAYILAN_SIRA and k not in cikti:
            cikti.append(k)
    return cikti + [k for k in VARSAYILAN_SIRA if k not in cikti]


def ad_standardi():
    """Hafizadaki Ad Standardi: {"sira": [yer, ...]} (yoksa varsayilan)."""
    try:
        govde, _h = kisaltma_mod._govde_oku()
    except Exception:
        govde = None
    st = (govde or {}).get("parca_ad_standardi")
    st = st if isinstance(st, dict) else {}
    return {"sira": sira_temizle(st.get("sira")), "kayitli": bool(st.get("sira"))}


def ad_standardi_kaydet(sira):
    return kisaltma_mod.parca_ad_standardi_kaydet({"sira": sira_temizle(sira)})


def ad_birimleri(ad, bilgi, desenler=()):
    """Kolon adinin birimleri: [[metin, yer]]. Ardisik sayili parcalar
    (3_M, H00_06) tek birim; onayli parca standart yazilisiyla; bilinmeyen
    parca aynen, yeri "diger"."""
    t = toklar(ad)
    sayili = sayili_konumlar(t)
    sayili.update(i for i, p in enumerate(t) if any(r.match(p) for r in desenler))
    birimler, i = [], 0
    while i < len(t):
        if i in sayili:
            j = i
            while j + 1 < len(t) and j + 1 in sayili and (
                    donem_mod.ayrik_ikili(t, j) or donem_mod._araligin_basi(t, j)):
                j += 1
            birimler.append(["_".join(t[i:j + 1]), "zaman"])
            i = j + 1
            continue
        o = (bilgi or {}).get(t[i]) or {}
        birimler.append([str(o.get("standart") or t[i]).upper(), ad_yeri(o.get("tur"))])
        i += 1
    return birimler


def ad_kur(birimler, sira):
    """Birimleri siraya gore dizip ad yapar (ayni yerdekiler kendi
    sirasinda)."""
    yer = {k: n for n, k in enumerate(sira_temizle(sira))}
    dizili = sorted(enumerate(birimler), key=lambda x: (yer.get(x[1][1], len(yer)), x[0]))
    return AYRAC.join(m for _n, (m, _y) in dizili)
