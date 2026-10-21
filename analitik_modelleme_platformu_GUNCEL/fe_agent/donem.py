"""fe_agent/donem.py - 01.2.4.1 DONEM BILGISI.

Aciklama duzenlemesinden ONCE kolon adlarindaki donem bilgisi netlesir.
Kod yalniz KALIP bulur, anlam vermez (anlam kodda yazili degil):
  - aile      : ayni harf ve sayinin butun yazilislari tek kalip; adi
                "<N>" + harf ("<N>M"). Yazilislar: sayi + 1-3 harf (3M,
                30D), 1-2 harf + sayi (M3, M12; tek basamakta tek harf),
                alt cizgiyle ayrilmis sayi ve tek harf (3_M, M_3). Dil
                modeli tanimlara gore farkli anlamli buldugu yazilisi ayirir
                (bkz. ayri); ayrilan yazilis kendi kalibiyla ("M<N>") ayri
                satirda durur
  - aralik    : harf + en az 2 rakamin ardindan yalniz rakam gelirse
                (<H><NN>_<MM>); kalip adi harf + "<NN>_<NN>". Bu gecis
                aileye AYRICA yazilmaz: aralik kalibi zaten kapsiyor
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
from concurrent.futures import ThreadPoolExecutor

from fe_agent import kisaltma as kisaltma_mod
from fe_agent import kisaltma_okuma
from fe_agent import llm as llm_mod
from fe_agent.akis_durum import _folder

ESKI_DOSYA = "/DONEM_BILGISI.json"   # eski bicim; bir kez hafizaya tasinip silinir
# Sozlukteki tanimlar kesin degil, kanittir: dil modeli anlami adin
# yapisindan kurar, tanimlarin cogunluguyla dogrular (oylama). Bu yuzden
# kalip basina birden cok tanim gider.
ORNEK_ADET = 10           # kalip basina modele ve karta giden ornek kolon
TARAMA_ORNEK = 3          # tarama: kisaltma basina ornek kolon
YORUM_PARCA = 6           # dil modeline bir cagrida giden kalip
ES_ZAMANLI = 4            # ayni anda en cok bu kadar cagri
KOMSU_EN_AZ = 3           # komsu aday: en az bu kadar kolonda
KOMSU_PAY = 0.6           # ... ve geciklerinin en az bu kadari donem yaninda
BIRLIKTE_EN_AZ = 3        # birlikte gecis: ikili en az bu kadar kolonda yan yana
BIRLIKTE_ADET = 3         # parca basina gosterilen en cok ikili

_SAYI_HARF = re.compile(r"^(\d+)([A-Z]{1,3})$")
_HARF_SAYI = re.compile(r"^([A-Z]{1,2})(\d{2,})$")
_HARF_SAYI_HARF = re.compile(r"^([A-Z]{1,3})(\d+)([A-Z]{1,3})$")
# Tek harf + tek basamak (M3, Y1): harf zaman birimi olabilir.
_HARF_TEK = re.compile(r"^([A-Z])(\d)$")
_YALIN_SAYI = re.compile(r"^\d+$")
_TEK_HARF = re.compile(r"^[A-Z]$")

_KILIT = threading.Lock()
_ISLER = {}               # imza -> {"durum", "sonuc", "hata", "zaman"}


# AILE ve YAZILISLAR. Yazilis kaliplari: <N>L, L<N>, <N>_L, L_<N> (L harf
# kismi). "L<NN>" eski bicimdir; L<N> yazilisi sayilir.
_AILE = re.compile(r"^<N>([A-Z]{1,3})$")
_YAZILIS_KALIP = (re.compile(r"^<N>([A-Z]{1,3})$"), re.compile(r"^([A-Z]{1,2})<NN?>$"),
                  re.compile(r"^<N>_([A-Z])$"), re.compile(r"^([A-Z])_<N>$"))
_YAZILIS_DEGER = ((re.compile(r"^\d+([A-Z]{1,3})$"), "<N>%s"),
                  (re.compile(r"^([A-Z]{1,2})\d+$"), "%s<N>"),
                  (re.compile(r"^\d+_([A-Z])$"), "<N>_%s"),
                  (re.compile(r"^([A-Z])_\d+$"), "%s_<N>"))
YAZILIS_SIRASI = ("<N>%s", "%s<N>", "<N>_%s", "%s_<N>")


def _norm(kalip):
    return re.sub(r"\s+", "", str(kalip or "")).upper()


def aile_mi(kalip):
    """Kalip bir aile mi ("<N>M": M ile sayinin butun yazilislari)?"""
    return bool(_AILE.match(_norm(kalip)))


def aile_adi(kalip):
    """Yazilis kalibinin ailesi ("M<N>", "M<NN>", "<N>_M", "M_<N>" ve
    "<N>M" -> "<N>M"); yazilis degilse None."""
    k = _norm(kalip)
    for r in _YAZILIS_KALIP:
        m = r.match(k)
        if m:
            return "<N>" + m.group(1)
    return None


def yazilis(deger):
    """Degerin yazilis kalibi (3M -> "<N>M", M12 -> "M<N>", 3_M -> "<N>_M",
    M_3 -> "M_<N>"); degilse None."""
    d = _norm(deger)
    for r, bicim in _YAZILIS_DEGER:
        m = r.match(d)
        if m:
            return bicim % m.group(1)
    return None


def aile_yazilislari(kalip):
    """Ailenin yazilis kaliplari (sirayla); aile degilse []."""
    m = _AILE.match(_norm(kalip))
    if not m:
        return []
    h = m.group(1)
    # Harften sonra sayi en cok iki harfle, alt cizgili yazilis tek harfle.
    adet = {1: 4, 2: 2}.get(len(h), 1)
    return [b % h for b in YAZILIS_SIRASI[:adet]]


def hafiza_anahtari(kalip, haf, ayri=()):
    """Kalibin hafizadaki anahtari: kendisi; aile hafizada yoksa ayrilmamis
    bir yazilisinin (ya da eski "L<NN>") kaydi. Yoksa None."""
    if kalip in haf:
        return kalip
    if not aile_mi(kalip):
        return None
    h = _AILE.match(_norm(kalip)).group(1)
    for y in aile_yazilislari(kalip)[1:] + [h + "<NN>"]:
        if y in haf and y not in ayri:
            return y
    return None


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
    m = _HARF_TEK.match(t)
    if m:
        return "harf_tek", m.group(1) + "<N>"
    return None


def ayrik_ikili(t, i):
    """Alt cizgiyle ayrilmis sayi ve tek harf (3_M, M_3): t[i] ile t[i+1]
    birlikte bir parca. Doner: (kalip, deger) ya da None. Harf + sayi
    araligin basiysa (H00_06) aralik kalibi gecerlidir."""
    if i + 1 >= len(t):
        return None
    a, b = t[i], t[i + 1]
    if _YALIN_SAYI.match(a) and _TEK_HARF.match(b):
        return "<N>_" + b, a + "_" + b
    if _TEK_HARF.match(a) and _YALIN_SAYI.match(b):
        return a + "_<N>", a + "_" + b
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


def deger_anlami(kalip, anlam, deger):
    """Kalibin anlamindaki yer tutuculari degerin sayilariyla doldurur:
    <N>D "<N> gün boyunca" + 30D -> "30 gün boyunca"; H<NN>_<NN>
    "<NN> - <NN> saatleri arası" + H00_06 -> "00 - 06 saatleri arası".
    Ayni turdeki yer tutucular kalipta gectikleri sirayla eslenir; anlamda
    fazlasi varsa son sayi kullanilir. Deger kaliba uymuyorsa ya da kalipta
    yer tutucu yoksa anlam aynen doner."""
    k = re.sub(r"\s+", "", str(kalip or "")).upper()
    anlam = str(anlam or "")
    turler = re.findall(r"<NN>|<N>", k)
    if not turler or not anlam:
        return anlam
    sayilar = _sayi_eslesmesi(k, deger)
    if sayilar is None:
        return anlam
    sayac = Counter()

    def yer(mo):
        y = re.sub(r"[\s<>]", "", mo.group(1)).upper()
        liste = sayilar.get(y)
        if not liste:
            return mo.group(0)
        i = sayac[y]
        sayac[y] += 1
        return liste[min(i, len(liste) - 1)]
    return _YT_ADAY.sub(yer, anlam)


def _sayi_eslesmesi(kalip, deger):
    """Degerin kalibin yer tutucularina dusen sayilari: {"N": [...],
    "NN": [...]} (kalipta gectikleri sirayla). Uymuyorsa None."""
    k = _norm(kalip)
    d = _norm(deger)
    if aile_mi(k):
        r = kalip_deseni(k)
        if r is None or not r.match(d):
            return None
        return {"N": [re.search(r"\d+", d).group(0)]}
    turler = re.findall(r"<NN>|<N>", k)
    desen = re.escape(k).replace("<NN>", r"(\d{2,})").replace("<N>", r"(\d+)")
    try:
        m = re.match("^" + desen + "$", d)
    except re.error:
        return None
    if not m:
        return None
    sayilar = {}
    for tur, sayi in zip(turler, m.groups()):
        sayilar.setdefault(tur.strip("<>"), []).append(sayi)
    return sayilar


def kalip_deseni(kalip):
    """Kalip adini derlenmis desene cevirir: <N> sayi, <NN> en az iki
    basamakli sayi, gerisi aynen. Aile ("<N>M") butun yazilislara uyar
    (3M, M3, 3_M, M_3). Gecersizse None."""
    k = re.sub(r"\s+", "", str(kalip or "")).upper()
    if not k:
        return None
    if aile_mi(k):
        h = re.escape(_AILE.match(k).group(1))
        return re.compile(r"^(?:\d+%s|%s\d+|\d+_%s|%s_\d+)$" % (h, h, h, h))
    desen = re.escape(k).replace("<NN>", r"\d{2,}").replace("<N>", r"\d+")
    try:
        return re.compile("^" + desen + "$")
    except re.error:
        return None


def kaliplar(adlar, tanimlar, ek=None, ayri=()):
    """Kolon adlarindan donem kaliplari: [{"kalip", "tur", "kolon",
    "degerler": [(deger, kolon sayisi)], "ornekler": [(kolon, tanim)]}];
    ailede ayrica "yazilislar" (adlarda gecen yazilis kaliplari) ve
    "ornek_yazilis" (her ornegin yazilisi). ek: hafizadaki kalip adlari;
    adlarda gecen (yerlesik bicimlerin bulmadigi) her biri "hafiza"
    turuyle eklenir; ailenin ayrilmamis yazilisi eklenmez (aile kapsar).
    ayri: aileden ayrilan yazilis kaliplari ("M<N>"); o yazilistaki
    degerler aileye degil kendi kalibina ("yazilis" turu) girer.
    Siralama: kolon sayisi (cok olan once)."""
    tanimlar = tanimlar or {}
    ayri = {_norm(x) for x in (ayri or ())}
    bilgi = {}                      # kalip -> {"tur", "deger": Counter, "kolonlar": [], "kd": {}}
    toplam = Counter()              # parca -> gectigi kolon sayisi
    komsu = Counter()               # parca -> donem parcasinin yaninda gectigi kolon

    def ekle(kalip, tur, deger, ad):
        b = bilgi.setdefault(kalip, {"tur": tur, "deger": Counter(), "kolonlar": [], "kd": {}})
        b["deger"][deger] += 1
        if ad not in b["kolonlar"]:
            b["kolonlar"].append(ad)
            b["kd"][ad] = deger

    def aileye_ekle(deger, ad):
        y = yazilis(deger)
        if y in ayri:
            ekle(y, "yazilis", deger, ad)
        else:
            ekle(aile_adi(y), "aile", deger, ad)

    for ad in adlar:
        t = _toklar(ad)
        for p in set(t):
            toplam[p] += 1
        yan = set()
        atla = set()
        for i, p in enumerate(t):
            if i in atla:
                continue
            ay = ayrik_ikili(t, i)
            if ay:
                # 3_M / M_3: iki parca birlikte tek deger.
                aileye_ekle(ay[1], ad)
                atla.add(i + 1)
                komsu_yer = (i - 1, i + 2)
            else:
                d = _donem_parcasi(p)
                if not d:
                    continue
                tur, kalip = d
                if _araligin_basi(t, i):
                    # Aralik kalibi bu gecisi kapsiyor; harf_sayi'ya ayrica
                    # yazilirsa ayni degerler iki satirda gorunur.
                    ekle(kalip + "_<NN>", "aralik", p + "_" + t[i + 1], ad)
                elif tur in ("sayi_harf", "harf_sayi", "harf_tek"):
                    aileye_ekle(p, ad)
                else:
                    ekle(kalip, tur, p, ad)
                komsu_yer = (i - 1, i + 1)
            for j in komsu_yer:
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
    desenler = [(k, kalip_deseni(k)) for k in (ek or []) if k not in bilgi
                and not (aile_adi(k) and not aile_mi(k) and _norm(k) not in ayri)]
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
        aile = b["tur"] == "aile"
        sira = aile_yazilislari(kalip) if aile else []
        yazilislar = [y for y in sira if any(yazilis(d) == y for d, _n in degerler)]
        # Ornekler: tanimi olan kolonlardan, farkli degerleri gosterecek
        # sekilde; ailede once her yazilistan bir ornek.
        hedef = ORNEK_ADET
        adaylar = [(ad, str(tanimlar.get(ad) or "").strip(), b["kd"].get(ad, ""))
                   for ad in b["kolonlar"]]
        adaylar = [x for x in adaylar if x[1]]
        ornek, gorulen, secilen = [], set(), set()
        for y in yazilislar:
            x = next((x for x in adaylar if yazilis(x[2]) == y), None)
            if x and len(ornek) < hedef:
                ornek.append(x)
                gorulen.add(x[2])
                secilen.add(x[0])
        for x in adaylar:
            if len(ornek) >= hedef:
                break
            if x[0] in secilen or (x[2] in gorulen and len(gorulen) < len(degerler)):
                continue
            gorulen.add(x[2])
            secilen.add(x[0])
            ornek.append(x)
        k = {"kalip": kalip, "tur": b["tur"], "kolon": len(b["kolonlar"]),
             "degerler": degerler, "ornekler": [(ad, t) for ad, t, _d in ornek]}
        if aile:
            k["yazilislar"] = yazilislar
            k["ornek_yazilis"] = [yazilis(d) or "" for _a, _t, d in ornek]
        cikti.append(k)
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
    kolonlar, ikililer, ayrik_harf = {}, set(), set()
    for ad in adlar:
        t = _toklar(ad)
        gorulen = []
        for i, p in enumerate(t):
            # Sayi + tek harf (3_M): ikili olarak girer, harf donem parcasi.
            ay = ayrik_ikili(t, i)
            if ay and _YALIN_SAYI.match(p):
                gorulen.append(ay[1])
                ikililer.add(ay[1])
                ayrik_harf.add(t[i + 1])
            if _YALIN_SAYI.match(p):
                continue
            gorulen.append(p)
            if i + 1 < len(t) and _YALIN_SAYI.match(t[i + 1]):
                gorulen.append(p + "_" + t[i + 1])
                ikililer.add(p + "_" + t[i + 1])
                if _TEK_HARF.match(p):
                    ayrik_harf.add(p)
        for p in dict.fromkeys(gorulen):
            kolonlar.setdefault(p, []).append(ad)
    cikti = []
    for p, liste in kolonlar.items():
        ornekler = [(a, str(tanimlar.get(a) or "").strip()[:200]) for a in liste[:ornek]]
        b = bh.get(p) or {}
        cikti.append({"parca": p, "kolon": len(liste), "ikili": p in ikililer,
                      "donem": p in ikililer or p in ayrik_harf or bool(_donem_parcasi(p)),
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
    Birlikte gectigi ikilisi varsa ornek tek basina gectigi kolondan.
    "ornekler": tanimi dolu en cok TARAMA_ORNEK kolon (oylama icin)."""
    tanimlar = tanimlar or {}
    kapsanan = {d for k in kalip_listesi for d, _n in k["degerler"]}
    bh = birlikte_haritasi(adlar, tanimlar)
    cikti = []
    for x in parca_listesi(adlar, tanimlar, ornek=TARAMA_ORNEK * 3):
        if x["donem"] or x["parca"] in kapsanan:
            continue
        b = bh.get(x["parca"]) or {}
        dolu = [(a, t) for a, t in x["ornekler"] if t][:TARAMA_ORNEK]
        ornek = dolu[0] if dolu else (x["ornekler"][0] if x["ornekler"] else ("", ""))
        if b.get("ornek_tek"):
            ornek = b["ornek_tek"]
            dolu = [ornek] + [o for o in dolu if o[0] != ornek[0]][:TARAMA_ORNEK - 1]
        cikti.append({"parca": x["parca"], "kolon": x["kolon"], "ornek": ornek,
                      "ornekler": dolu,
                      "birlikte": b.get("birlikte") or [], "tek": b.get("tek", x["kolon"]),
                      "birlikte_ornek": dict(b.get("ornekler") or {})})
    return cikti


# ---------------------------------------------------------------------------
# KURUM HAFIZASI: KISALTMA_HAFIZASI.json "donem" bolumu ({kalip: anlam})
# ---------------------------------------------------------------------------
_TASINDI = []


def _eskiyi_tasi():
    """Eski DONEM_BILGISI.json dosyasi varsa anlamli kayitlari bir kez
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


def hafiza_deger():
    """{kalip: {deger: anlam}}: hafizada kalibin anlamindan farkli yazilmis
    deger anlamlari."""
    try:
        return kisaltma_mod.donem_deger_hafizasi()
    except Exception:
        return {}


def hafiza_ayrilan():
    """{kalip: {deger: {"anlam", "cikar"}}}: hafizada kalibin grubundan
    ayrilan degerler."""
    try:
        return kisaltma_mod.donem_ayrilan_hafizasi()
    except Exception:
        return {}


def hafiza_tur():
    """{kalip: tur}: hafizada kalibin zaman bilgisi turu."""
    try:
        return kisaltma_mod.donem_tur_hafizasi()
    except Exception:
        return {}


def hafiza_ayri():
    """{kalip}: ailesinden ayri anlamla onaylanmis yazilis kaliplari."""
    try:
        return kisaltma_mod.donem_ayri_hafizasi()
    except Exception:
        return set()


def aile_uyeleri(kalip):
    """Ailenin kendi adi disindaki yazilis kaliplari ve eski "L<NN>" bicimi
    (hafizada aile adina katilan kayitlar)."""
    if not aile_mi(kalip):
        return []
    h = _AILE.match(_norm(kalip)).group(1)
    return aile_yazilislari(kalip)[1:] + [h + "<NN>"]


def hafizaya_yaz(kayitlar, haric=None, degerler=None, ayrilan=None, turler=None,
                 ayri=None):
    """kayitlar: {kalip: anlam}; haric: {kalip: [ikili]}, degerler:
    {kalip: {deger: anlam}} ve ayrilan: {kalip: {deger: {"anlam", "cikar"}}}
    (bu kaliplarin hafizadaki haric listesi, deger anlamlari ve gruptan
    ayrilan degerleri bununla degisir); turler: {kalip: tur}; ayri:
    ailesinden ayrilmis yazilis kaliplari. Doner: hata ya da None."""
    return kisaltma_mod.donem_kaydet(kayitlar, haric, degerler, ayrilan, turler, ayri)


def hafizadan_sil(kaliplar):
    """Cikarilan kaliplari hafizadan siler (yalniz bunlari).
    Doner: (silinen sayisi, hata ya da None)."""
    return kisaltma_mod.donem_sil(kaliplar)


# ---------------------------------------------------------------------------
# ARKA PLAN: dil modeli yorumu
# ---------------------------------------------------------------------------
# Istem ya da kalip kurallari degisince eski yorumlar yeniden uretilsin.
ISTEM_SURUMU = 6


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
    ayri = hafiza_ayri()
    # Hafizada anlami olan kalip (aile icin bir yazilisinin kaydi da) sorulmaz.
    sorulacak = [x for x in liste if not hafiza_anahtari(x["kalip"], haf, ayri)]

    def calis():
        # Yorum ve tarama parcalara bolunur, parcalar ayni anda calisir;
        # her parcanin sonucu gelince yazilir (kart yoklamada dolar).
        # Iptal edilen isin sonradan gelen cevabi yazilmaz.
        k = _ISLER[imza]
        hatalar = []
        gorevler = [("sonuc", llm_mod.donem_yorumla, sorulacak[i:i + YORUM_PARCA])
                    for i in range(0, len(sorulacak), YORUM_PARCA)]
        gorevler += [("bulunan", llm_mod.donem_tara, tara[i:i + llm_mod.TARAMA_PARCA])
                     for i in range(0, len(tara), llm_mod.TARAMA_PARCA)]

        def yap(g):
            alan, f, parca = g
            sonuc, hata = f(parca)
            with _KILIT:
                if not k.get("iptal"):
                    k[alan].update(sonuc)
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
    if sorulacak or tara:
        threading.Thread(target=calis, daemon=True).start()
    else:
        _ISLER[imza]["durum"] = "bitti"
    return imza


def iptal(imza):
    """Suren yorumu durdurur: o ana kadar gelen sonuclar kalir, is bitmis
    sayilir (yorumlanmayan kaliplar Olasi'ya duser). Dil modelinin suren
    cagrisi kesilemez; cevabi gelince yazilmaz."""
    with _KILIT:
        k = _ISLER.get(imza or "")
        if k and k["durum"] == "calisiyor":
            k["iptal"] = True
            k["durum"] = "bitti"


def durum(imza):
    k = _ISLER.get(imza or "")
    if not k:
        return {"durum": "yok", "sonuc": {}, "bulunan": {}, "hata": "", "gecen": 0,
                "iptal": False}
    with _KILIT:                  # parcalar yazilirken kopyalanmasin
        return {"durum": k["durum"], "sonuc": dict(k["sonuc"]),
                "bulunan": dict(k.get("bulunan") or {}), "hata": k["hata"],
                "gecen": int(time.time() - k["zaman"]), "iptal": bool(k.get("iptal"))}
