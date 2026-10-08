"""fe_agent/donem.py - 01.2.4 DONEM BILGISI.

Aciklama duzenlemesinden ONCE kolon adlarindaki donem bilgisi netlesir.
Kod yalniz KALIP bulur, anlam vermez (anlam kodda yazili degil):
  - sayi_harf : sayi + 1-3 harf (<N><H>); kalip adi "<N>" + harf kismi
  - harf_sayi : 1-2 harf + en az 2 rakam (<H><NN>); kalip adi harf + "<NN>"
  - aralik    : harf_sayi parcasinin ardindan yalniz rakam gelirse
                (<H><NN>_<MM>); kalip adi harf + "<NN>_<NN>"
  - komsu     : donem parcasinin hemen yaninda en az KOMSU_EN_AZ kolonda
                gecen, rakamsiz parca; geciklerinin cogu donem parcasinin
                yanindaysa aday olur. Donemle ilgili mi dil modeli soyler.
Anlami dil modeli tanimlardan okuyarak onerir (arka planda), kullanici
onaylar ya da duzeltir. Onaylanan anlam kurum hafizasina
(DONEM_BILGISI.json) yazilir ve sonraki adimlarda (aciklama duzenleme,
kisaltma, kolon adlari) baglam olur. Girdi veri seti ve sozluge yazilmaz."""

import hashlib
import json
import re
import threading
import time
from collections import Counter

from fe_agent import kisaltma_okuma
from fe_agent import llm as llm_mod
from fe_agent.akis_durum import _folder

DOSYA = "/DONEM_BILGISI.json"
ORNEK_ADET = 3            # kalip basina modele ve karta giden ornek kolon
KOMSU_EN_AZ = 3           # komsu aday: en az bu kadar kolonda
KOMSU_PAY = 0.6           # ... ve geciklerinin en az bu kadari donem yaninda

_SAYI_HARF = re.compile(r"^(\d+)([A-Z]{1,3})$")
_HARF_SAYI = re.compile(r"^([A-Z]{1,2})(\d{2,})$")
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
    return None


def kaliplar(adlar, tanimlar):
    """Kolon adlarindan donem kaliplari: [{"kalip", "tur", "kolon",
    "degerler": [(deger, kolon sayisi)], "ornekler": [(kolon, tanim)]}].
    Siralama: kolon sayisi (cok olan once)."""
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


# ---------------------------------------------------------------------------
# KURUM HAFIZASI
# ---------------------------------------------------------------------------
def hafiza():
    """{kalip: {"anlam", "donem", "tarih"}} (yoksa {})."""
    try:
        with _folder().get_download_stream(DOSYA) as akis:
            govde = json.loads(akis.read().decode("utf-8") or "{}")
    except Exception:
        return {}
    return govde if isinstance(govde, dict) else {}


def hafizaya_yaz(kayitlar):
    """kayitlar: {kalip: {"anlam", "donem"}}. Doner: hata ya da None."""
    with _KILIT:
        govde = hafiza()
        tarih = time.strftime("%Y-%m-%d %H:%M")
        for k, v in (kayitlar or {}).items():
            govde[str(k)] = {"anlam": str(v.get("anlam") or ""),
                             "donem": bool(v.get("donem", True)), "tarih": tarih}
        try:
            _folder().upload_stream(DOSYA, json.dumps(
                govde, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"))
        except Exception as e:
            return "Dönem bilgisi hafızaya yazılamadı (%s)." % str(e)[:120]
    return None


# ---------------------------------------------------------------------------
# ARKA PLAN: dil modeli yorumu
# ---------------------------------------------------------------------------
def _imza(liste):
    ham = json.dumps([[k["kalip"], k["degerler"], k["ornekler"]] for k in liste],
                     ensure_ascii=False)
    return hashlib.sha1(ham.encode("utf-8")).hexdigest()[:16]


def baslat(liste):
    """Hafizada olmayan kaliplar icin modeli arka planda calistirir.
    Doner: imza."""
    imza = _imza(liste)
    with _KILIT:
        k = _ISLER.get(imza)
        if k and k["durum"] in ("calisiyor", "bitti"):
            return imza
        _ISLER[imza] = {"durum": "calisiyor", "sonuc": {}, "hata": "", "zaman": time.time()}
    haf = hafiza()
    # Hafizada karari olan kalip (anlami ya da "donem degil") sorulmaz.
    sorulacak = [x for x in liste if x["kalip"] not in haf]

    def calis():
        k = _ISLER[imza]
        try:
            sonuc, hata = llm_mod.donem_yorumla(sorulacak)
            k["sonuc"], k["hata"] = sonuc, hata or ""
            k["durum"] = "bitti"
        except Exception as e:
            k["hata"] = "%s: %s" % (type(e).__name__, str(e)[:200])
            k["durum"] = "hata"
    if sorulacak:
        threading.Thread(target=calis, daemon=True).start()
    else:
        _ISLER[imza]["durum"] = "bitti"
    return imza


def durum(imza):
    k = _ISLER.get(imza or "")
    if not k:
        return {"durum": "yok", "sonuc": {}, "hata": "", "gecen": 0}
    return {"durum": k["durum"], "sonuc": dict(k["sonuc"]), "hata": k["hata"],
            "gecen": int(time.time() - k["zaman"])}
