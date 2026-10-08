"""fe_agent/donem.py - 01.2.4 DONEM BILGISI.

Aciklama duzenlemesinden ONCE kolon adlarindaki donem bilgisi netlesir.
Kod yalniz KALIP bulur, anlam vermez (anlam kodda yazili degil):
  - sayi_harf : sayi + 1-3 harf (<N><H>); kalip adi "<N>" + harf kismi
  - harf_sayi : 1-2 harf + en az 2 rakam (<H><NN>); kalip adi harf + "<NN>"
  - aralik    : harf_sayi parcasinin ardindan yalniz rakam gelirse
                (<H><NN>_<MM>); kalip adi harf + "<NN>_<NN>"
  - harf_sayi_harf : 1-3 harf + sayi + 1-3 harf (<H><N><H>); kalip adi
                harf + "<N>" + harf
  - hafiza    : kurum hafizasindaki (onceki calismalarda onaylanip
                "Hafizaya Kaydet" ile yazilan) kalip adlarda geciyorsa;
                sistem boylece yeni kaliplari ogrenir
  - komsu     : donem parcasinin hemen yaninda en az KOMSU_EN_AZ kolonda
                gecen, rakamsiz parca; geciklerinin cogu donem parcasinin
                yanindaysa aday olur. Donemle ilgili mi dil modeli soyler.
Rakamsiz donem kisaltmalari bicimden bulunamaz: geri kalan butun
kisaltmalari dil modeli tarar (tarama), donem bilgisi tasiyanlari onerir.
Anlami dil modeli tanimlardan okuyarak onerir (arka planda), kullanici
onaylar ya da duzeltir. Onaylanan anlam bu calismanin donem bilgisi olur
ve sonraki adimlarda (aciklama duzenleme, kisaltma, kolon adlari) baglam
olur; "Hafizaya Kaydet" isaretli olanlar kurum hafizasina
(KISALTMA_HAFIZASI.json, "donem" altinda) yazilir. Girdi veri seti ve
sozluge yazilmaz."""

import hashlib
import json
import re
import threading
import time
from collections import Counter

from fe_agent import kisaltma as kisaltma_mod
from fe_agent import kisaltma_okuma
from fe_agent import llm as llm_mod
from fe_agent.akis_durum import _folder

ESKI_DOSYA = "/DONEM_BILGISI.json"   # onceki surum; bir kez hafizaya tasinip silinir
ORNEK_ADET = 3            # kalip basina modele ve karta giden ornek kolon
KOMSU_EN_AZ = 3           # komsu aday: en az bu kadar kolonda
KOMSU_PAY = 0.6           # ... ve geciklerinin en az bu kadari donem yaninda

_SAYI_HARF = re.compile(r"^(\d+)([A-Z]{1,3})$")
_HARF_SAYI = re.compile(r"^([A-Z]{1,2})(\d{2,})$")
_HARF_SAYI_HARF = re.compile(r"^([A-Z]{1,3})(\d+)([A-Z]{1,3})$")
_YALIN_SAYI = re.compile(r"^\d+$")

_KILIT = threading.Lock()
_ISLER = {}               # imza -> {"durum", "sonuc", "hata", "zaman"}


def _toklar(ad):
    return [kisaltma_okuma._ust(p) for p in kisaltma_okuma.parcalar(ad)]


def _donem_parcasi(t):
    """(tur, kalip) ya da None."""
    m = _SAYI_HARF.match(t)
    if m:
        return "sayi_harf", "<N>" + m.group(2)
    m = _HARF_SAYI.match(t)
    if m:
        return "harf_sayi", m.group(1) + "<NN>"
    m = _HARF_SAYI_HARF.match(t)
    if m:
        return "harf_sayi_harf", m.group(1) + "<N>" + m.group(3)
    return None


def kalip_deseni(kalip):
    """Kalip adini derlenmis desene cevirir: <N> sayi, <NN> en az iki
    basamakli sayi, gerisi aynen. Gecersizse None."""
    k = re.sub(r"\s+", "", str(kalip or "")).upper()
    if not k:
        return None
    desen = re.escape(k).replace("<NN>", r"\d{2,}").replace("<N>", r"\d+")
    try:
        return re.compile("^" + desen + "$")
    except re.error:
        return None


def kaliplar(adlar, tanimlar, ek=None):
    """Kolon adlarindan donem kaliplari: [{"kalip", "tur", "kolon",
    "degerler": [(deger, kolon sayisi)], "ornekler": [(kolon, tanim)]}].
    ek: hafizadaki kalip adlari; adlarda gecen (yerlesik bicimlerin
    bulmadigi) her biri "hafiza" turuyle eklenir. Siralama: kolon sayisi
    (cok olan once)."""
    tanimlar = tanimlar or {}
    bilgi = {}                      # kalip -> {"tur", "deger": Counter, "kolonlar": set}
    toplam = Counter()              # parca -> gectigi kolon sayisi
    komsu = Counter()               # parca -> donem parcasinin yaninda gectigi kolon

    def ekle(kalip, tur, deger, ad):
        b = bilgi.setdefault(kalip, {"tur": tur, "deger": Counter(), "kolonlar": []})
        b["deger"][deger] += 1
        if ad not in b["kolonlar"]:
            b["kolonlar"].append(ad)

    for ad in adlar:
        t = _toklar(ad)
        for p in set(t):
            toplam[p] += 1
        yan = set()
        for i, p in enumerate(t):
            d = _donem_parcasi(p)
            if not d:
                continue
            tur, kalip = d
            ekle(kalip, tur, p, ad)
            if tur == "harf_sayi" and i + 1 < len(t) and _YALIN_SAYI.match(t[i + 1]):
                ekle(kalip + "_<NN>", "aralik", p + "_" + t[i + 1], ad)
            for j in (i - 1, i + 1):
                if 0 <= j < len(t):
                    q = t[j]
                    if len(q) > 1 and not _YALIN_SAYI.match(q) and not _donem_parcasi(q):
                        yan.add(q)
        for q in yan:
            komsu[q] += 1
    for q, n in komsu.items():
        if n >= KOMSU_EN_AZ and n >= KOMSU_PAY * toplam[q]:
            for ad in adlar:
                if q in _toklar(ad):
                    ekle(q, "komsu", q, ad)
    # Hafizadaki kaliplar (tek parca ya da <P>_<NN> ikilisi olarak).
    desenler = [(k, kalip_deseni(k)) for k in (ek or []) if k not in bilgi]
    desenler = [(k, r) for k, r in desenler if r is not None]
    if desenler:
        for ad in adlar:
            t = _toklar(ad)
            adaylar = list(t) + [t[i] + "_" + t[i + 1] for i in range(len(t) - 1)
                                 if _YALIN_SAYI.match(t[i + 1])]
            for k, r in desenler:
                for p in adaylar:
                    if r.match(p):
                        ekle(k, "hafiza", p, ad)

    cikti = []
    for kalip, b in bilgi.items():
        degerler = sorted(b["deger"].items(), key=lambda kv: (-kv[1], kv[0]))
        # Ornekler: tanimi olan kolonlardan, farkli degerleri gosterecek sekilde.
        ornek, gorulen = [], set()
        for ad in b["kolonlar"]:
            if len(ornek) >= ORNEK_ADET:
                break
            tanim = str(tanimlar.get(ad) or "").strip()
            if not tanim:
                continue
            deger = next((d for d, _n in degerler if d.split("_")[0] in _toklar(ad)), "")
            if deger in gorulen and len(gorulen) < len(degerler):
                continue
            gorulen.add(deger)
            ornek.append((ad, tanim))
        cikti.append({"kalip": kalip, "tur": b["tur"], "kolon": len(b["kolonlar"]),
                      "degerler": degerler, "ornekler": ornek})
    cikti.sort(key=lambda k: (-k["kolon"], k["kalip"]))
    return cikti


def parca_listesi(adlar, tanimlar, ornek=2):
    """Kolon adlarindaki BUTUN parcalar (yalniz rakam haric): [{"parca",
    "kolon", "donem": donem kalibina uyuyor mu, "ikili": aralik ikilisi mi,
    "ornekler": [(kolon, tanim)]}], alfabetik. Ardindan yalniz rakam gelen
    parca ikili olarak da girer (<P>_<NN>; elle yazilan aralik kalibi
    adlarda aranabilsin)."""
    tanimlar = tanimlar or {}
    kolonlar, ikililer = {}, set()
    for ad in adlar:
        t = _toklar(ad)
        gorulen = []
        for i, p in enumerate(t):
            if _YALIN_SAYI.match(p):
                continue
            gorulen.append(p)
            if i + 1 < len(t) and _YALIN_SAYI.match(t[i + 1]):
                gorulen.append(p + "_" + t[i + 1])
                ikililer.add(p + "_" + t[i + 1])
        for p in dict.fromkeys(gorulen):
            kolonlar.setdefault(p, []).append(ad)
    cikti = []
    for p, liste in kolonlar.items():
        ornekler = [(a, str(tanimlar.get(a) or "").strip()[:200]) for a in liste[:ornek]]
        cikti.append({"parca": p, "kolon": len(liste), "ikili": p in ikililer,
                      "donem": p in ikililer or bool(_donem_parcasi(p)),
                      "ornekler": ornekler})
    cikti.sort(key=lambda x: x["parca"])
    return cikti


def kalip_adlarda(kalip, parcalar):
    """Elle yazilan kalibin kolon adlarindaki karsiliklari: [(parca,
    kolon sayisi)]. parcalar: parca_listesi ciktisi."""
    r = kalip_deseni(kalip)
    if r is None:
        return []
    return [(x["parca"], x["kolon"]) for x in parcalar if r.match(x["parca"])]


def tarama_listesi(adlar, tanimlar, kalip_listesi):
    """Dil modelinin taracagi kisaltmalar: kolon adlarindaki, bicimi donem
    olmayan ve hicbir kalibin degeri olmayan butun parcalar (yalniz rakam
    haric): [{"parca", "kolon", "ornek": (kolon, tanim)}]."""
    tanimlar = tanimlar or {}
    kapsanan = {d for k in kalip_listesi for d, _n in k["degerler"]}
    cikti = []
    for x in parca_listesi(adlar, tanimlar, ornek=1):
        if x["donem"] or x["parca"] in kapsanan:
            continue
        cikti.append({"parca": x["parca"], "kolon": x["kolon"],
                      "ornek": x["ornekler"][0] if x["ornekler"] else ("", "")})
    return cikti


# ---------------------------------------------------------------------------
# KURUM HAFIZASI: KISALTMA_HAFIZASI.json "donem" bolumu ({kalip: anlam})
# ---------------------------------------------------------------------------
_TASINDI = []


def _eskiyi_tasi():
    """Onceki surumun DONEM_BILGISI.json'u varsa anlamli kayitlari bir kez
    kisaltma hafizasina tasinir, dosya silinir. Yazilamazsa dosya kalir."""
    if _TASINDI:
        return
    try:
        with _folder().get_download_stream(ESKI_DOSYA) as akis:
            govde = json.loads(akis.read().decode("utf-8") or "{}")
    except Exception:
        _TASINDI.append(True)
        return
    kayit = {}
    for k, v in (govde.items() if isinstance(govde, dict) else []):
        if isinstance(v, dict) and v.get("donem", True) and str(v.get("anlam") or "").strip():
            kayit[str(k)] = str(v["anlam"]).strip()
    if kayit and kisaltma_mod.donem_kaydet(kayit):
        return
    try:
        _folder().delete_path(ESKI_DOSYA)
    except Exception:
        pass
    _TASINDI.append(True)


def hafiza():
    """{kalip: anlam} (yoksa {})."""
    try:
        _eskiyi_tasi()
    except Exception:
        pass
    try:
        return kisaltma_mod.donem_hafizasi()
    except Exception:
        return {}


def hafizaya_yaz(kayitlar):
    """kayitlar: {kalip: anlam}. Doner: hata ya da None."""
    return kisaltma_mod.donem_kaydet(kayitlar)


# ---------------------------------------------------------------------------
# ARKA PLAN: dil modeli yorumu
# ---------------------------------------------------------------------------
def _imza(liste, tara):
    ham = json.dumps([[k["kalip"], k["degerler"], k["ornekler"]] for k in liste]
                     + [x["parca"] for x in tara], ensure_ascii=False)
    return hashlib.sha1(ham.encode("utf-8")).hexdigest()[:16]


def baslat(liste, tara=None):
    """Arka planda: hafizada olmayan kaliplari dil modeline yorumlatir ve
    kalan kisaltmalari donem bilgisi icin taratir. Doner: imza."""
    tara = tara or []
    imza = _imza(liste, tara)
    with _KILIT:
        k = _ISLER.get(imza)
        if k and k["durum"] in ("calisiyor", "bitti"):
            return imza
        _ISLER[imza] = {"durum": "calisiyor", "sonuc": {}, "bulunan": {}, "hata": "",
                        "zaman": time.time()}
    haf = hafiza()
    # Hafizada anlami olan kalip sorulmaz.
    sorulacak = [x for x in liste if x["kalip"] not in haf]

    def calis():
        k = _ISLER[imza]
        hatalar = []
        try:
            if sorulacak:
                sonuc, hata = llm_mod.donem_yorumla(sorulacak)
                k["sonuc"] = sonuc
                if hata:
                    hatalar.append(hata)
            if tara:
                bulunan, hata = llm_mod.donem_tara(tara)
                k["bulunan"] = bulunan
                if hata:
                    hatalar.append(hata)
            k["hata"] = " ".join(hatalar)
            k["durum"] = "bitti"
        except Exception as e:
            k["hata"] = "%s: %s" % (type(e).__name__, str(e)[:200])
            k["durum"] = "hata"
    if sorulacak or tara:
        threading.Thread(target=calis, daemon=True).start()
    else:
        _ISLER[imza]["durum"] = "bitti"
    return imza


def durum(imza):
    k = _ISLER.get(imza or "")
    if not k:
        return {"durum": "yok", "sonuc": {}, "bulunan": {}, "hata": "", "gecen": 0}
    return {"durum": k["durum"], "sonuc": dict(k["sonuc"]),
            "bulunan": dict(k.get("bulunan") or {}), "hata": k["hata"],
            "gecen": int(time.time() - k["zaman"])}
