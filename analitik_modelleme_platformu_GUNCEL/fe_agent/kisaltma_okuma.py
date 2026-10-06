"""KISALTMA SOZLUGU (01.2.4) ve YENI KOLON ADLARI (01.2.5).

SOZLUK KESIN DOGRUDUR. Kolon adlarindaki kisaltmalarin anlami yalniz
sozlukteki tanimlardan okunur; genel bilgiyle tahmin, aday oylamasi ve
hakem yoktur.

1) OKUMA (arka planda; 01.2.3'te baslar): tanimi olan HER kolon icin dil
   modeli adin her parcasini (ya da yan yana birkac parcayi birlikte)
   tanimdaki ifadeyle esler ve tanimda olup adda karsiligi olmayan
   kavramlari yazar (llm.kisaltma_esle). Kod her eslemeyi dogrular: ifade
   tanimda gecmeli, parca adin ardisik parcalari olmali; dogrulanmayan
   esleme duser. Ornekleme yok: sozlugun tamami okunur.
2) ANLAM TABLOSU: eslemeler ANLAMA gore toplanir. Ayni anlama giden
   kisaltmalar (esanlamli) ayni satirda; iki anlamda kullanilan kisaltma
   iki satirda; tanimda olup adda olmayan kavram da satir olur. Hicbir
   tanimda karsiligi bulunamayan parcalar ayri bolumde; anlam yalniz
   burada hafizadan (baska calismalardan) gelir ve isaretlidir.
3) STANDART: her anlam icin kolon adlarinda kullanilacak tek kisaltma
   (llm.kisaltma_standart); hafizada bu anlam icin daha once secilmis
   standart varsa o gelir.
4) YENI KOLON ADLARI: kolon bazli eslemeden KODLA uretilir.

Okuma ve oneri sonuclari calisma klasorunde KISALTMA_OKUMA.json'da
saklanir; ayni kolon ayni tanimla ikinci kez okunmaz. Girdi veri setine
ve sozluge hicbir kosulda yazilmaz."""

import hashlib
import json
import re
import threading
import time
from collections import Counter
from concurrent import futures

from fe_agent import kisaltma as kisa_mod
from fe_agent import llm as llm_mod
from fe_agent.akis_durum import _folder

OKUMA_PARCA = 15          # dil modeline tek cagrida giden kolon
OKUMA_PARALEL = 3         # ayni anda calisan okuma cagrisi
ONERI_PARCA = 40          # standart onerisinde tek cagridaki anlam
ORNEK_ADET = 3            # satirin "i"sinde gosterilen ornek kolon
KALIP_ADET = 20           # ADLANDIRMA KALIBI'na giden en sik kisaltma

_PARCA = re.compile(r"[A-Za-z0-9ÇĞİÖŞÜçğıöşü]+")
_KELIME = re.compile(r"[0-9A-Za-zÇĞİÖŞÜçğıöşü]+")
_AD_KALIP = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

_KILIT = threading.Lock()
_SONUC = {}               # (kolon, tanim_ozeti) -> {"g": [[parca, ifade, bas, son]], "y": [[ifade, sonra]]}
_ONERI = {}               # oneri anahtari -> [kisaltma, gerekce]
_ISLER = {}               # imza -> is kaydi
_YUKLENEN = set()         # KISALTMA_OKUMA.json'u okunan calisma klasorleri
_HAVUZ = futures.ThreadPoolExecutor(max_workers=OKUMA_PARALEL)


# ---------------------------------------------------------------------------
# METIN
# ---------------------------------------------------------------------------
def parcalar(ad):
    """Kolon adinin parcalari, adda gectigi sirayla (rakamlar dahil)."""
    return _PARCA.findall(str(ad or ""))


def _ust(p):
    return kisa_mod._sade(p).upper()


def _ozet(tanim):
    return hashlib.sha1(str(tanim or "").strip().encode("utf-8")).hexdigest()[:12]


def _kelimeler(metin):
    return _KELIME.findall(str(metin or ""))


def tanimdan(ifade, tanim):
    """Ifade tanimda (kelime kelime, ayni sirayla) geciyorsa TANIMDAKI
    kelimeler; gecmiyorsa "". Modelin kelime sonundaki eki atmasi kabul
    edilir (tanimdaki kelime onun uzantisiysa); kelime eklemesi, sayi
    degistirmesi ya da baska kelime yazmasi kabul edilmez."""
    iw = [kisa_mod._sade(w) for w in _kelimeler(ifade)]
    tanim = str(tanim or "")
    tm = list(_KELIME.finditer(tanim))
    ts = [kisa_mod._sade(m.group(0)) for m in tm]
    n = len(iw)
    if not n or n > len(ts):
        return ""
    for i in range(len(ts) - n + 1):
        for j in range(n):
            a, b = iw[j], ts[i + j]
            if a == b:
                continue
            if a.isdigit() or b.isdigit() or len(a) < 3 or not b.startswith(a):
                break
        else:
            # Tanimdaki yazilis (araya giren isaretler dahil: "00-06").
            return tanim[tm[i].start():tm[i + n - 1].end()]
    return ""


def anahtar(ifade):
    """Anlamin karsilastirma anahtari: kucuk harf, Turkce harfler sade,
    her kelime yalin (cogul / iyelik / tamlayan eki atilir)."""
    return " ".join(kisa_mod._sade(kisa_mod._yalin_kelime(kisa_mod._kucuk(w)))
                    for w in _kelimeler(ifade))


def _gorunen(ifade, sozcukler=()):
    """Kartta gorunen anlam: kucuk harf; tamami buyuk harfli kisa
    kelimeler (kurum kisaltmalari) oldugu gibi kalir. Kelimenin yalin hali
    tanimlarda tek basina geciyorsa yalin hali yazilir (adedi -> adet)."""
    def kelime(m):
        w = m.group(0)
        if w.isupper() and len(w) <= 6:
            return w
        k = kisa_mod._kucuk(w)
        y = kisa_mod._yalin_kelime(k)
        return y if y != k and y in sozcukler else k
    return _KELIME.sub(kelime, str(ifade or "").strip())


def _ayni_kelimeler(a, b):
    sa, sb = anahtar(a), anahtar(b)
    return bool(sa) and (sa == sb or sa in sb or sb in sa)


# ---------------------------------------------------------------------------
# OKUMA SONUCUNUN DOGRULANMASI
# ---------------------------------------------------------------------------
def _aralik_bul(toklar, hedef, dolu):
    """hedef parca dizisinin toklar icindeki ardisik ve bos (dolu
    olmayan) ilk konumu: (bas, son) ya da None."""
    n = len(hedef)
    for i in range(len(toklar) - n + 1):
        if toklar[i:i + n] == hedef and not any(k in dolu for k in range(i, i + n)):
            return i, i + n - 1
    return None


def esleme_oku(veri, blok):
    """Modelin okuma cevabini dogrular. blok: [(kolon, tanim)].
    Doner: {kolon: {"g": [[parca, ifade, bas, son]], "y": [[ifade, sonra]]}}
    yalniz cevabi gelen kolonlar."""
    tanimlar = dict(blok)
    buyuk = {str(ad).upper(): ad for ad in tanimlar}
    cikti = {}
    for k in ((veri or {}).get("kolonlar") or []):
        if not isinstance(k, dict):
            continue
        ad = tanimlar.get(str(k.get("ad") or "")) and str(k.get("ad")) \
            or buyuk.get(str(k.get("ad") or "").upper())
        if not ad or ad in cikti:
            continue
        tanim = tanimlar[ad]
        toklar_ham = parcalar(ad)
        toklar = [_ust(p) for p in toklar_ham]
        dolu = set()
        gruplar = []
        for p in (k.get("parcalar") or []):
            if not isinstance(p, dict):
                continue
            hedef = [_ust(x) for x in _PARCA.findall(str(p.get("parca") or ""))]
            if not hedef or all(h.isdigit() for h in hedef):
                continue
            yer = _aralik_bul(toklar, hedef, dolu)
            ifade = tanimdan(p.get("ifade"), tanim)
            if not yer or not ifade:
                continue
            bas, son = yer
            dolu.update(range(bas, son + 1))
            gruplar.append(["_".join(toklar[bas:son + 1]), ifade, bas, son])
        eksik = []
        for e in (k.get("adda_yok") or []):
            if not isinstance(e, dict):
                continue
            ifade = tanimdan(e.get("ifade"), tanim)
            if not ifade or any(_ayni_kelimeler(ifade, g[1]) for g in gruplar) \
                    or any(_ayni_kelimeler(ifade, x[0]) for x in eksik):
                continue
            sonra = "_".join(_ust(x) for x in _PARCA.findall(str(e.get("sonra") or "")))
            if sonra and not _aralik_bul(toklar, sonra.split("_"), set()):
                sonra = ""
            eksik.append([ifade, sonra])
        cikti[ad] = {"g": gruplar, "y": eksik}
    return cikti


# ---------------------------------------------------------------------------
# KAYIT (calisma klasoru)
# ---------------------------------------------------------------------------
def _dosya(klasor):
    return "/%s/KISALTMA_OKUMA.json" % klasor


def _dosyadan_yukle(klasor):
    if not klasor or klasor in _YUKLENEN:
        return
    _YUKLENEN.add(klasor)
    try:
        with _folder().get_download_stream(_dosya(klasor)) as akis:
            govde = json.loads(akis.read().decode("utf-8") or "{}")
    except Exception:
        return
    for ad, k in (govde.get("kolonlar") or {}).items():
        if isinstance(k, dict) and k.get("t"):
            _SONUC.setdefault((ad, k["t"]), {"g": k.get("g") or [], "y": k.get("y") or []})
    for a, v in (govde.get("oneriler") or {}).items():
        if isinstance(v, list) and len(v) == 2:
            _ONERI.setdefault(a, v)


def _dosyaya_yaz(klasor, girdi):
    if not klasor:
        return
    kolonlar = {}
    for ad, tanim in girdi:
        oz = _ozet(tanim)
        if (ad, oz) in _SONUC:
            kolonlar[ad] = dict(_SONUC[(ad, oz)], t=oz)
    govde = {"kolonlar": kolonlar, "oneriler": dict(_ONERI)}
    try:
        _folder().upload_stream(_dosya(klasor), json.dumps(
            govde, ensure_ascii=False, indent=1, sort_keys=True).encode("utf-8"))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# ARKA PLAN ISI
# ---------------------------------------------------------------------------
def _girdi(kolonlar):
    return sorted((str(ad), str(t).strip()) for ad, t in (kolonlar or {}).items()
                  if str(t or "").strip())


def baslat(kolonlar, klasor="", tum_adlar=()):
    """Okumayi (ve ardindan standart onerilerini) arka planda baslatir.
    kolonlar: {kolon: tanim}; tum_adlar: veri setinin butun kolonlari
    (tanimsizlar dahil). Daha once okunan kolon tekrar okunmaz.
    Doner: is imzasi."""
    girdi = _girdi(kolonlar)
    adlar = sorted(set(map(str, tum_adlar or ())) | {ad for ad, _t in girdi})
    imza = hashlib.sha1(json.dumps([girdi, adlar], ensure_ascii=False)
                        .encode("utf-8")).hexdigest()[:16]
    with _KILIT:
        _dosyadan_yukle(klasor)
        k = _ISLER.get(imza)
        if k and k["durum"] in ("calisiyor", "bitti"):
            return imza
        eksik = [(ad, t) for ad, t in girdi if (ad, _ozet(t)) not in _SONUC]
        _ISLER[imza] = {"durum": "calisiyor", "asama": "okuma", "girdi": girdi,
                        "adlar": adlar, "klasor": klasor, "toplam": len(girdi),
                        "biten": len(girdi) - len(eksik), "oneri_toplam": 0,
                        "oneri_biten": 0, "zaman": time.time(), "iptal": False,
                        "hata": "", "okunmayan": 0}
    threading.Thread(target=_calis, args=(imza, eksik), daemon=True).start()
    return imza


def _calis(imza, eksik):
    k = _ISLER[imza]
    try:
        ork = llm_mod.Orkestra(arka=True)

        def oku(blok):
            if k["iptal"]:
                return blok, None, "iptal"
            veri, hata = llm_mod.kisaltma_esle(
                [{"ad": ad, "parcalar": parcalar(ad), "tanim": t} for ad, t in blok], ork)
            return blok, veri, hata

        bloklar = [eksik[i:i + OKUMA_PARCA] for i in range(0, len(eksik), OKUMA_PARCA)]
        for f in futures.as_completed([_HAVUZ.submit(oku, b) for b in bloklar]):
            blok, veri, hata = f.result()
            if hata == "iptal":
                continue
            sonuc = esleme_oku(veri, blok) if not hata else {}
            with _KILIT:
                for ad, t in blok:
                    if ad in sonuc:
                        _SONUC[(ad, _ozet(t))] = sonuc[ad]
                    else:
                        k["okunmayan"] += 1
                k["biten"] += len(blok)
                if hata:
                    k["hata"] = hata
        if not k["iptal"]:
            k["asama"] = "oneri"
            _onerileri_hazirla(k, ork)
        k["durum"] = "bitti"
    except Exception as e:
        k["durum"] = "hata"
        k["hata"] = "%s: %s" % (type(e).__name__, str(e)[:200])
    finally:
        _dosyaya_yaz(k["klasor"], k["girdi"])


def durum(imza):
    k = _ISLER.get(imza or "")
    if not k:
        return {"durum": "yok"}
    return {"durum": k["durum"], "asama": k["asama"], "biten": k["biten"],
            "toplam": k["toplam"], "oneri_biten": k["oneri_biten"],
            "oneri_toplam": k["oneri_toplam"], "gecen": int(time.time() - k["zaman"]),
            "iptal": k["iptal"], "hata": k["hata"], "okunmayan": k["okunmayan"]}


def iptal(imza):
    k = _ISLER.get(imza or "")
    if k and k["durum"] == "calisiyor":
        k["iptal"] = True


# ---------------------------------------------------------------------------
# ANLAM TABLOSU
# ---------------------------------------------------------------------------
def _hafiza():
    """(onayli {KISA: anlam}, ogrenilen {KISA: anlam}, standart {anahtar: KISA})."""
    try:
        onay = kisa_mod.onaylilar()
    except Exception:
        onay = {}
    try:
        ogr = {k: v["anlam"] for k, v in kisa_mod.ogrenilenler().items()}
    except Exception:
        ogr = {}
    try:
        hedefler = set(kisa_mod.degisimler().values())
    except Exception:
        hedefler = set()
    standart = {}
    for kisa, anlam in sorted(onay.items()):
        a = anahtar(anlam)
        if a and (a not in standart or kisa in hedefler):
            standart[a] = kisa
    return onay, ogr, standart


def _oneri_anahtari(satir, dil):
    return "|".join([satir["anahtar"], ",".join(sorted(k["kisaltma"] for k in satir["kisaltmalar"])),
                     ",".join(sorted(satir.get("cok_anlamli") or {})),
                     "1" if satir.get("adda_yok") else "0", dil or ""])


def tablo(kolonlar, tum_adlar=(), dil_kalip=None):
    """Kartin satirlari ve kolon bazli esleme.
    Doner: {"satirlar", "esleme": {kolon: {"g": [[parca, anahtar, bas, son]],
    "y": [[anahtar, sonra]]}}, "okunan", "tanimli", "dil", "kalip"}."""
    girdi = dict(_girdi(kolonlar))
    satir = {}                  # anahtar -> birikim
    kisa_anlam = {}             # KISA -> Counter(anahtar)
    esleme = {}
    for ad, tanim in sorted(girdi.items()):
        r = _SONUC.get((ad, _ozet(tanim)))
        if r is None:
            continue
        e = {"g": [], "y": []}
        for parca, ifade, bas, son in r.get("g") or []:
            a = anahtar(ifade)
            if not a:
                continue
            s = satir.setdefault(a, {"ifade": Counter(), "kisa": {}, "adda_yok": 0,
                                     "ornek": []})
            s["ifade"][ifade] += 1
            s["kisa"].setdefault(parca, set()).add(ad)
            if len(s["ornek"]) < ORNEK_ADET and ad not in [o["kolon"] for o in s["ornek"]]:
                s["ornek"].append({"kolon": ad, "tanim": tanim[:200], "ifade": ifade})
            kisa_anlam.setdefault(parca, Counter())[a] += 1
            e["g"].append([parca, a, bas, son])
        for ifade, sonra in r.get("y") or []:
            a = anahtar(ifade)
            if not a:
                continue
            s = satir.setdefault(a, {"ifade": Counter(), "kisa": {}, "adda_yok": 0,
                                     "ornek": []})
            s["ifade"][ifade] += 1
            s["adda_yok"] += 1
            if len(s["ornek"]) < ORNEK_ADET and ad not in [o["kolon"] for o in s["ornek"]]:
                s["ornek"].append({"kolon": ad, "tanim": tanim[:200], "ifade": ifade})
            e["y"].append([a, sonra])
        esleme[ad] = e

    onay, ogr, standart = _hafiza()

    # Tanimlarda tek basina gecen kelimeler: yalin hali ancak burada
    # geciyorsa yazilir (yanlis ek atma kartta gorunmesin).
    sozcukler = {kisa_mod._kucuk(w) for t in girdi.values() for w in _kelimeler(t)}

    def gorunen(s, a):
        """Ekleri atilmamis (zaten yalin) yazilis varsa o; yoksa en sik."""
        aday = sorted(s["ifade"].items(), key=lambda kv: (-kv[1], len(kv[0])))
        for ifade, _n in aday:
            if " ".join(kisa_mod._sade(w) for w in _kelimeler(ifade)) == a:
                return _gorunen(ifade, sozcukler)
        return _gorunen(aday[0][0], sozcukler)

    satirlar = []
    anlam_adi = {a: gorunen(s, a) for a, s in satir.items()}
    for a, s in satir.items():
        kisalar = sorted(s["kisa"].items(), key=lambda kv: (-len(kv[1]), kv[0]))
        cok = {}
        for kisa, _ in kisalar:
            baska = [b for b in kisa_anlam.get(kisa, {}) if b != a]
            if baska:
                cok[kisa] = [anlam_adi[b] for b in baska]
        satirlar.append({
            "anahtar": a, "anlam": anlam_adi[a], "bolum": "sozluk", "kaynak": "sozluk",
            "kisaltmalar": [{"kisaltma": k, "kolon": len(v)} for k, v in kisalar],
            "adda_yok": s["adda_yok"], "cok_anlamli": cok, "ornekler": s["ornek"]})

    # SOZLUKTE KARSILIGI BULUNAMAYAN PARCALAR: bir kolonun adinda o
    # kolonun eslemesinin kapsamadigi (tanimsiz kolonda hepsi) ve hicbir
    # tanimda TEK BASINA anlami okunmamis parcalar; yalniz rakamdan olusan
    # parca haric. Baska kolonda yalniz bir grubun icinde eslenen parca da
    # (tek basina anlami bilinmiyor) burada. Anlam hafizadan, isaretli.
    adlar = sorted(set(map(str, tum_adlar or ())) | set(girdi))
    say = Counter()
    for ad in adlar:
        toklar = [_ust(x) for x in parcalar(ad)]
        kapsanan = set()
        for _p, _a, bas, son in (esleme.get(ad) or {}).get("g") or []:
            kapsanan.update(range(bas, son + 1))
        for p in {t for i, t in enumerate(toklar) if i not in kapsanan}:
            if not p.isdigit() and p not in kisa_anlam:
                say[p] += 1
    for p, n in say.items():
        anlam, kaynak = "", ""
        if onay.get(p):
            anlam, kaynak = onay[p], "hafiza"
        elif ogr.get(p):
            anlam, kaynak = ogr[p], "ogrenilen"
        satirlar.append({
            "anahtar": "?" + p, "anlam": anlam, "bolum": "bulunamadi", "kaynak": kaynak,
            "kisaltmalar": [{"kisaltma": p, "kolon": n}], "adda_yok": 0,
            "cok_anlamli": {}, "ornekler": []})

    # ADLANDIRMA DILI ve KALIBI bu veri setinin kisaltmalarindan.
    agirlik = Counter()
    anlamlar = {}
    for s in satirlar:
        for k in s["kisaltmalar"]:
            agirlik[k["kisaltma"]] += k["kolon"]
            if s["anlam"] and not s["cok_anlamli"].get(k["kisaltma"]):
                anlamlar[k["kisaltma"]] = s["anlam"]
    dil = llm_mod.adlandirma_dili(anlamlar, agirlik)
    kalip = ", ".join(k for k, _n in agirlik.most_common(KALIP_ADET))

    satirlar.sort(key=lambda s: (s["bolum"] != "bulunamadi",
                                 not s["kisaltmalar"],
                                 -sum(k["kolon"] for k in s["kisaltmalar"]) - s["adda_yok"],
                                 s["anlam"]))
    _onerileri_uygula(satirlar, dil, standart, onay)
    return {"satirlar": satirlar, "esleme": esleme, "okunan": len(esleme),
            "tanimli": len(girdi), "dil": dil, "kalip": kalip}


def _onerileri_uygula(satirlar, dil, standart, onay):
    """Her satirin onerisini (hafiza standardi ya da dil modeli) denetleyip
    yazar. Oneri baska bir anlamin kullandigi kisaltma olamaz; iki anlam ayni
    kisaltmayi alamaz (buyuk satir once)."""
    sahip = {}                                   # KISA -> mevcut anlamlari
    for s in satirlar:
        for k in s["kisaltmalar"]:
            sahip.setdefault(k["kisaltma"], set()).add(s["anahtar"])
    verilen = set()
    for s in sorted(satirlar, key=lambda s: -sum(k["kolon"] for k in s["kisaltmalar"])):
        mevcut = [k["kisaltma"] for k in s["kisaltmalar"]]
        kullanilan = {k for k, a in sahip.items() if a - {s["anahtar"]}} | verilen
        adaylar_ = []
        if s["anlam"] and standart.get(anahtar(s["anlam"])):
            adaylar_.append((standart[anahtar(s["anlam"])],
                             "Önceki çalışmalarda bu anlam için seçilen kısaltma.", "hafiza"))
        o = _ONERI.get(_oneri_anahtari(s, dil))
        if o and o[0]:
            adaylar_.append((o[0], o[1], "dil_modeli"))
        oneri, gerekce, kaynak = "", "", ""
        for aday, ger, kay in adaylar_:
            if llm_mod.oneri_gecerli(aday, s["anlam"], kullanilan, dil, mevcut):
                oneri, gerekce, kaynak = aday, ger, kay
                break
        if oneri:
            verilen.add(oneri)
        # Tek kisaltma ve o kalacak: degisiklik yok.
        if oneri and mevcut == [oneri]:
            oneri = ""
        s["oneri"], s["oneri_gerekce"], s["oneri_kaynak"] = oneri, gerekce, kaynak
        s["onayli"] = bool(s["anlam"]) and (
            (s["bolum"] == "bulunamadi" and s["kaynak"] == "hafiza")
            or (bool(mevcut) and not oneri
                and all(anahtar(onay.get(k, "")) == s["anahtar"] for k in mevcut)))


def _onerileri_hazirla(k, ork):
    """Okuma bitince: onerisi olmayan anlamlar icin dil modeli (parca
    parca). Hafizada standardi olan satir sorulmaz."""
    t = tablo(dict(k["girdi"]), k["adlar"])
    _onay, _ogr, standart = _hafiza()
    sor = [s for s in t["satirlar"]
           if s["anlam"] and not standart.get(anahtar(s["anlam"]))
           and _oneri_anahtari(s, t["dil"]) not in _ONERI]
    k["oneri_toplam"] = len(sor)
    for i in range(0, len(sor), ONERI_PARCA):
        if k["iptal"]:
            return
        grup = sor[i:i + ONERI_PARCA]
        istek = [{"no": j + 1, "anlam": s["anlam"],
                  "mevcut": [(x["kisaltma"], x["kolon"]) for x in s["kisaltmalar"]],
                  "baska": [(kisa, ", ".join(a)) for kisa, a in s["cok_anlamli"].items()],
                  "adda_yok": s["adda_yok"]} for j, s in enumerate(grup)]
        cevap, hata = llm_mod.kisaltma_standart(istek, t["dil"], t["kalip"], ork)
        with _KILIT:
            for j, s in enumerate(grup):
                kisa, gerekce = cevap.get(j + 1, ("", ""))
                if not hata:
                    _ONERI[_oneri_anahtari(s, t["dil"])] = [kisa, gerekce]
            k["oneri_biten"] += len(grup)
            if hata:
                k["hata"] = hata


def baglam_kisaltmalari(kolonlar):
    """Tanim yazdirma istemlerine giden kisaltmalar (bekletmez):
    (kesin, tahmini). Kesin: bu sozlukten okunmus, tek anlamli
    kisaltmalar. Tahmini: sozluk istatistigi ve hafiza (baska
    calismalar); kesinde olmayanlar."""
    kesin = {}
    try:
        t = tablo(kolonlar)
        for s in t["satirlar"]:
            if s["bolum"] != "sozluk":
                continue
            for k in s["kisaltmalar"]:
                if not s["cok_anlamli"].get(k["kisaltma"]):
                    kesin[k["kisaltma"]] = s["anlam"]
    except Exception:
        pass
    tahmini = {}
    try:
        tahmini.update({k: v["anlam"] for k, v in kisa_mod.ogrenilenler().items()})
    except Exception:
        pass
    try:
        tahmini.update({k: v["anlam"] for k, v in kisa_mod.cikar(kolonlar).items()})
    except Exception:
        pass
    try:
        tahmini.update(kisa_mod.onaylilar())
    except Exception:
        pass
    return kesin, {k: v for k, v in tahmini.items() if k not in kesin and v}


# ---------------------------------------------------------------------------
# YENI KOLON ADLARI
# ---------------------------------------------------------------------------
def _ayrac_parcalar(ad):
    """ad = ayrac[0] + parca[0] + ayrac[1] + ... + parca[-1] + ayrac[-1]."""
    toklar, ayrac, yer = [], [], 0
    for m in _PARCA.finditer(str(ad)):
        ayrac.append(str(ad)[yer:m.start()])
        toklar.append(m.group(0))
        yer = m.end()
    ayrac.append(str(ad)[yer:])
    return toklar, ayrac


def yeni_ad(ad, esleme, kararlar, genel):
    """Tek kolonun yeni adi ve degisiklikler.
    esleme: bu kolonun {"g", "y"} kaydi (yoksa None: tanimsiz kolon).
    kararlar: {anahtar: {"kisa": standart ya da "", "anlam"}} (yalniz
    secilenler). genel: {KISA: (YENI, anlam)} tek anlamli kisaltmalarin
    degisimi; eslenmemis parcalara uygulanir. Doner: (yeni_ad,
    [degisiklik])."""
    toklar, ayrac = _ayrac_parcalar(ad)
    ust = [_ust(t) for t in toklar]
    degistir = {}                         # bas -> (son, yeni, etiket)
    ekle = {}                             # sonra gelecegi parca indeksi -> [(yeni, etiket)]
    if esleme:
        for parca, a, bas, son in esleme.get("g") or []:
            karar = kararlar.get(a)
            if not karar or not karar["kisa"] or karar["kisa"] == parca:
                continue
            if bas >= len(ust) or "_".join(ust[bas:son + 1]) != parca:
                continue
            degistir[bas] = (son, karar["kisa"], "%s → %s (%s)" % (parca, karar["kisa"], karar["anlam"]))
        for a, sonra in esleme.get("y") or []:
            karar = kararlar.get(a)
            if not karar or not karar["kisa"]:
                continue
            hedef = karar["kisa"].split("_")
            if _aralik_bul(ust, hedef, set()):
                continue                    # zaten adda
            yer = -1
            if sonra:
                aralik = _aralik_bul(ust, sonra.split("_"), set())
                if aralik:
                    yer = aralik[1]
            if yer == -1 and sonra:
                yer = len(ust) - 1
            ekle.setdefault(yer, []).append(
                (karar["kisa"], "+ %s (%s)" % (karar["kisa"], karar["anlam"])))
    # Tanimi olmayan kolonda (ya da tanimli kolonun eslenmeyen
    # parcalarinda) yalniz tek anlamli kisaltmalarin degisimi uygulanir.
    dolu = set()
    for _p, _a, bas, son in (esleme or {}).get("g") or []:
        dolu.update(range(bas, son + 1))
    for kisa in sorted(genel, key=lambda x: -len(x.split("_"))):
        yeni, anlam = genel[kisa]
        hedef = kisa.split("_")
        while True:
            aralik = _aralik_bul(ust, hedef, dolu)
            if not aralik:
                break
            dolu.update(range(aralik[0], aralik[1] + 1))
            degistir[aralik[0]] = (aralik[1], yeni, "%s → %s (%s)" % (kisa, yeni, anlam))
    if not degistir and not ekle:
        return ad, []
    kucuk = str(ad) == str(ad).lower()

    def yaz(metin):
        return metin.lower() if kucuk else metin

    parcala_ = [ayrac[0]]
    etiketler = []
    for yeni_, etiket in ekle.get(-1, []):
        parcala_.append(yaz(yeni_) + "_")
        etiketler.append(etiket)
    i = 0
    while i < len(toklar):
        if i in degistir:
            son, yeni_, etiket = degistir[i]
            parcala_.append(yaz(yeni_))
            etiketler.append(etiket)
        else:
            son = i
            parcala_.append(toklar[i])
        for idx in range(i, son + 1):
            for yeni_, etiket in ekle.get(idx, []):
                parcala_.append("_" + yaz(yeni_))
                etiketler.append(etiket)
        parcala_.append(ayrac[son + 1])
        i = son + 1
    return "".join(parcala_), etiketler


def yeni_adlar(adlar, esleme, kararlar, genel, korunan=(), haric=()):
    """Degisen kolonlar: [{"kolon", "yeni_ad", "degisim": [..], "sorun"}].
    Sorunlu satir (gecersiz ad, ayni adi alan iki kolon, baska kolonun
    adi) isaretli gelmez."""
    korunan, haric = set(map(str, korunan)), set(map(str, haric))
    mevcut = set(map(str, adlar))
    satirlar = []
    for ad in adlar:
        ad = str(ad)
        if ad in korunan or ad in haric:
            continue
        yeni, degisim = yeni_ad(ad, (esleme or {}).get(ad), kararlar, genel)
        if yeni != ad:
            satirlar.append({"kolon": ad, "yeni_ad": yeni, "degisim": degisim, "sorun": ""})
    kalan = mevcut - {s["kolon"] for s in satirlar}
    say = Counter(s["yeni_ad"] for s in satirlar)
    for s in satirlar:
        if not _AD_KALIP.match(s["yeni_ad"]):
            s["sorun"] = "Geçersiz ad: harfle başlamalı; yalnız harf, rakam ve _ içerebilir."
        elif s["yeni_ad"] in kalan:
            s["sorun"] = "Veri setinde bu adda başka bir kolon var."
        elif say[s["yeni_ad"]] > 1:
            s["sorun"] = "Bu adı birden fazla kolon alıyor."
    return satirlar


# ---------------------------------------------------------------------------
# EXCEL
# ---------------------------------------------------------------------------
EXCEL_SOZLUK = ["Anlam (Sözlükten)", "Kısaltmalar (Kolon Sayısı)", "Adda Yok (Kolon)",
                "Önerilen Kısaltma", "Öneri Gerekçesi", "Durum"]
EXCEL_ESLEME = ["Kolon", "Tanım", "Parça", "Tanımdaki İfade"]
EXCEL_EKSIK = ["Kolon", "Tanım", "Tanımda Olup Adda Olmayan", "Hangi Parçadan Sonra"]


def excel_sayfalari(kolonlar, tum_adlar=()):
    t = tablo(kolonlar, tum_adlar)
    durum_adi = {"sozluk": "Sözlükten", "hafiza": "Başka Çalışmadan (onaylı)",
                 "ogrenilen": "Başka Çalışmadan (öğrenilen)", "": "Sözlükte Bulunamadı"}
    s1 = [[s["anlam"] or None,
           ", ".join("%s (%d)" % (k["kisaltma"], k["kolon"]) for k in s["kisaltmalar"]) or None,
           s["adda_yok"] or None, s["oneri"] or None, s["oneri_gerekce"] or None,
           durum_adi.get(s["kaynak"], "")] for s in t["satirlar"]]
    girdi = dict(_girdi(kolonlar))
    s2, s3 = [], []
    for ad, tanim in sorted(girdi.items()):
        r = _SONUC.get((ad, _ozet(tanim))) or {}
        for parca, ifade, _b, _s in r.get("g") or []:
            s2.append([ad, tanim[:300], parca, ifade])
        for ifade, sonra in r.get("y") or []:
            s3.append([ad, tanim[:300], ifade, sonra or None])
    return [("Kısaltma Sözlüğü", EXCEL_SOZLUK, s1), ("Kolon Eşlemeleri", EXCEL_ESLEME, s2),
            ("Adda Olmayan Kavramlar", EXCEL_EKSIK, s3)]
