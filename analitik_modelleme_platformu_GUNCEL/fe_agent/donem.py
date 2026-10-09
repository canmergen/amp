"""fe_agent/donem.py - 01.2.4.1 DONEM BILGISI.

Aciklama duzenlemesinden ONCE kolon adlarindaki donem bilgisi netlesir.
Kod yalniz KALIP bulur, anlam vermez (anlam kodda yazili degil):
  - sayi_harf : sayi + 1-3 harf (<N><H>); kalip adi "<N>" + harf kismi
  - harf_sayi : 1-2 harf + en az 2 rakam (<H><NN>); kalip adi harf + "<NN>"
  - aralik    : harf_sayi parcasinin ardindan yalniz rakam gelirse
                (<H><NN>_<MM>); kalip adi harf + "<NN>_<NN>". Bu gecis
                harf_sayi kalibina AYRICA yazilmaz: aralik kalibi zaten
                kapsiyor (harf_sayi yalniz adlarda tek basina gecerse cikar)
  - harf_sayi_harf : 1-3 harf + sayi + 1-3 harf (<H><N><H>); kalip adi
                harf + "<N>" + harf
  - hafiza    : kurum hafizasindaki (onceki calismalarda onaylanan)
                kalip adlarda geciyorsa; sistem boylece yeni kaliplari
                ogrenir
  - komsu     : donem parcasinin hemen yaninda en az KOMSU_EN_AZ kolonda
                gecen, rakamsiz parca; geciklerinin cogu donem parcasinin
                yanindaysa aday olur. Donemle ilgili mi dil modeli soyler.
Rakamsiz donem kisaltmalari bicimden bulunamaz: geri kalan butun
kisaltmalari dil modeli tarar (tarama), donem bilgisi tasiyanlari onerir.
Anlami dil modeli tanimlardan okuyarak onerir (arka planda), kullanici
onaylar ya da duzeltir. Onaylanan anlam bu calismanin donem bilgisi olur
ve sonraki adimlarda (aciklama duzenleme, kisaltma, kolon adlari) baglam
olur ve kurum hafizasina (KISALTMA_HAFIZASI.json, "donem" altinda)
yazilir; kullanicinin cikardigi satirlar kullanilmaz. Girdi veri seti ve
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
BIRLIKTE_EN_AZ = 3        # birlikte gecis: ikili en az bu kadar kolonda yan yana
BIRLIKTE_ADET = 3         # parca basina gosterilen en cok ikili

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


def _araligin_basi(t, i):
    """t[i] harf + sayi parcasi ve ardindan yalniz rakam geliyor mu
    (<H><NN>_<MM> araliginin ilk yarisi)?"""
    d = _donem_parcasi(t[i])
    return bool(d and d[0] == "harf_sayi" and i + 1 < len(t)
                and _YALIN_SAYI.match(t[i + 1]))


# YER TUTUCU: anlamda kalibin sayilarini gosteren isaret. <N> icin "N"
# ya da "<N>", <NN> icin "NN" ya da "<NN>" yazilir; baska bicim (ornegin
# "Nn", "n") ya da kalipta olmayan yer tutucu hata sayilir.
_YT_ADAY = re.compile(r"(?<![0-9A-Za-zÇĞİÖŞÜçğıöşü])(<\s*[Nn]{1,2}\s*>|[Nn]{1,2})"
                      r"(?![0-9A-Za-zÇĞİÖŞÜçğıöşü])")


def yer_tutucu_hatasi(kalip, anlam):
    """Anlamdaki gecersiz yer tutucular icin hata metni; yoksa ""."""
    k = re.sub(r"\s+", "", str(kalip or "")).upper()
    izinli = set()
    if "<NN>" in k:
        izinli.update({"NN", "<NN>"})
    if "<N>" in k:
        izinli.update({"N", "<N>"})
    kotu = []
    for m in _YT_ADAY.finditer(str(anlam or "")):
        y = re.sub(r"\s+", "", m.group(1))
        if y not in izinli and y not in kotu:
            kotu.append(y)
    if not kotu:
        return ""
    if not izinli:
        return ("Anlamda yer tutucu var (%s) ama kalıpta sayı yer tutucusu yok; "
                "yerine değeri yazın." % ", ".join(kotu))
    return ("Anlamda geçersiz yer tutucu: %s. Bu kalıpta kullanılabilenler: %s."
            % (", ".join(kotu), ", ".join(sorted(x for x in izinli if not x.startswith("<")))))


# ---------------------------------------------------------------------------
# BIRLIKTE GECIS: harf parcalarinin kolon adlarinda yan yana gectigi ikililer
# (yalniz sayim; anlam yok). Bir kisaltma bir ikilinin icinde baska bir
# anlam tasiyabilir (ornegin ikili birlikte bir birim gosterir). Kullanici
# o ikiliyi "haric" isaretlerse kalip o ikilinin icinde donem sayilmaz;
# tek basina gectigi yerlerde donem kalir.
# ---------------------------------------------------------------------------
def _harf_parcasi(p):
    return bool(p) and not _YALIN_SAYI.match(p) and not _donem_parcasi(p)


def haric_mi(t, i, haric):
    """t[i] haric tutulan bir ikilinin (sol_sag) icinde mi?"""
    if not haric:
        return False
    return ((i > 0 and t[i - 1] + "_" + t[i] in haric)
            or (i + 1 < len(t) and t[i] + "_" + t[i + 1] in haric))


def birlikte_haritasi(adlar, tanimlar=None):
    """{parca: {"birlikte": [[ikili, kolon]], "tek": tek basina gectigi
    kolon, "ornek_tek": (kolon, tanim) | None, "ornekler": {ikili: (kolon,
    tanim)}}}. Yalniz en az BIRLIKTE_EN_AZ kolonda yan yana gectigi ikilisi
    olan harf parcalari; ikili adi soldaki_sagdaki."""
    tanimlar = tanimlar or {}
    toks = [(ad, _toklar(ad)) for ad in adlar]
    cift = {}
    for _ad, t in toks:
        gor = {}
        for i, p in enumerate(t):
            if not _harf_parcasi(p):
                continue
            for j in (i - 1, i + 1):
                if 0 <= j < len(t) and _harf_parcasi(t[j]):
                    gor.setdefault(p, set()).add(t[min(i, j)] + "_" + t[max(i, j)])
        for p, ikililer in gor.items():
            c = cift.setdefault(p, Counter())
            for ik in ikililer:
                c[ik] += 1
    cikti = {}
    for p, c in cift.items():
        sec = [ik for ik, n in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))
               if n >= BIRLIKTE_EN_AZ][:BIRLIKTE_ADET]
        if sec:
            cikti[p] = {"birlikte": [[ik, c[ik]] for ik in sec], "tek": 0,
                        "ornek_tek": None, "ornekler": {}}
    for ad, t in toks:
        tanim = str(tanimlar.get(ad) or "").strip()
        gorulen = set()
        for i, p in enumerate(t):
            b = cikti.get(p)
            if not b or p in gorulen:
                continue
            gorulen.add(p)
            secili = {ik for ik, _n in b["birlikte"]}
            # Kolonda parcanin secili ikililerin disinda bir gecisi varsa tek.
            tek = any(not haric_mi(t, j, secili) for j, q in enumerate(t) if q == p)
            if tek:
                b["tek"] += 1
                if tanim and b["ornek_tek"] is None:
                    b["ornek_tek"] = (ad, tanim)
            for j, q in enumerate(t):
                if q != p:
                    continue
                for ik in sorted(secili):
                    if haric_mi(t, j, {ik}) and tanim and ik not in b["ornekler"]:
                        b["ornekler"][ik] = (ad, tanim)
    return cikti


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
            if _araligin_basi(t, i):
                # Aralik kalibi bu gecisi kapsiyor; harf_sayi'ya ayrica
                # yazilirsa ayni degerler iki satirda gorunur.
                ekle(kalip + "_<NN>", "aralik", p + "_" + t[i + 1], ad)
            else:
                ekle(kalip, tur, p, ad)
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
            # Araligin basi olan parca tek basina aday degil (bkz. aralik).
            adaylar = [p for i, p in enumerate(t) if not _araligin_basi(t, i)] + \
                [t[i] + "_" + t[i + 1] for i in range(len(t) - 1)
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
    # Yer tutucusuz (tek parca) kaliplarin birlikte gectigi ikililer.
    bh = birlikte_haritasi(adlar, tanimlar)
    for k in cikti:
        b = bh.get(k["kalip"]) if "<" not in k["kalip"] else None
        if b:
            k.update(birlikte=b["birlikte"], tek=b["tek"], birlikte_ornek=dict(b["ornekler"]))
    cikti.sort(key=lambda k: (-k["kolon"], k["kalip"]))
    return cikti


def parca_listesi(adlar, tanimlar, ornek=2):
    """Kolon adlarindaki BUTUN parcalar (yalniz rakam haric): [{"parca",
    "kolon", "donem": donem kalibina uyuyor mu, "ikili": aralik ikilisi mi,
    "ornekler": [(kolon, tanim)]}], alfabetik. Ardindan yalniz rakam gelen
    parca ikili olarak da girer (<P>_<NN>; elle yazilan aralik kalibi
    adlarda aranabilsin)."""
    tanimlar = tanimlar or {}
    bh = birlikte_haritasi(adlar, tanimlar)
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
        b = bh.get(p) or {}
        cikti.append({"parca": p, "kolon": len(liste), "ikili": p in ikililer,
                      "donem": p in ikililer or bool(_donem_parcasi(p)),
                      "ornekler": ornekler, "birlikte": b.get("birlikte") or [],
                      "tek": b.get("tek", len(liste))})
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
    haric): [{"parca", "kolon", "ornek": (kolon, tanim), "birlikte":
    [[ikili, kolon]], "tek", "birlikte_ornek": {ikili: (kolon, tanim)}}].
    Birlikte gectigi ikilisi varsa ornek tek basina gectigi kolondan."""
    tanimlar = tanimlar or {}
    kapsanan = {d for k in kalip_listesi for d, _n in k["degerler"]}
    bh = birlikte_haritasi(adlar, tanimlar)
    cikti = []
    for x in parca_listesi(adlar, tanimlar, ornek=1):
        if x["donem"] or x["parca"] in kapsanan:
            continue
        b = bh.get(x["parca"]) or {}
        ornek = x["ornekler"][0] if x["ornekler"] else ("", "")
        if b.get("ornek_tek"):
            ornek = b["ornek_tek"]
        cikti.append({"parca": x["parca"], "kolon": x["kolon"], "ornek": ornek,
                      "birlikte": b.get("birlikte") or [], "tek": b.get("tek", x["kolon"]),
                      "birlikte_ornek": dict(b.get("ornekler") or {})})
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


def hafiza_haric():
    """{kalip: [ikili]}: hafizada kalibin donem sayilmadigi ikililer."""
    try:
        return kisaltma_mod.donem_haric_hafizasi()
    except Exception:
        return {}


def hafizaya_yaz(kayitlar, haric=None):
    """kayitlar: {kalip: anlam}; haric: {kalip: [ikili]} (bu kaliplarin
    hafizadaki haric listesi bununla degisir). Doner: hata ya da None."""
    return kisaltma_mod.donem_kaydet(kayitlar, haric)


def hafizadan_sil(kaliplar):
    """Cikarilan kaliplari hafizadan siler (yalniz bunlari).
    Doner: (silinen sayisi, hata ya da None)."""
    return kisaltma_mod.donem_sil(kaliplar)


# ---------------------------------------------------------------------------
# ARKA PLAN: dil modeli yorumu
# ---------------------------------------------------------------------------
# Istem ya da kalip kurallari degisince eski yorumlar yeniden uretilsin.
ISTEM_SURUMU = 3


def _imza(liste, tara):
    ham = json.dumps([ISTEM_SURUMU] + [[k["kalip"], k["degerler"], k["ornekler"],
                                         k.get("birlikte") or []] for k in liste]
                     + [[x["parca"], x.get("birlikte") or []] for x in tara],
                     ensure_ascii=False)
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
