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
Yalniz SAYILI kaliplar burada. Rakamsiz zaman parcalari (DAY, MONTH,
TMSNCFRST) Ad Parcalari'nda (parca.py) butun kisaltmalarla birlikte
yorumlanir; turleri orada zaman turlerinden biri olur.
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


# SAYI YER TUTUCULARI: <N> herhangi bir sayi, <NN> en az iki basamakli,
# <N2>, <N3> ... tam o kadar basamakli sayi (H<N2>: H00, H06, H12; H000
# uymaz). Anlamda <N> ve <Nk> icin "N", <NN> icin "NN" yazilir.
_YT_KALIP = re.compile(r"<NN>|<N\d>|<N>")


def _yt_tur(t):
    """Kalip yer tutucusunun anlamdaki adi: <NN> -> "NN", digerleri "N"."""
    return "NN" if t == "<NN>" else "N"


def _yt_desen(t, yakala=False):
    d = r"\d{2,}" if t == "<NN>" else (r"\d{%s}" % t[2:-1] if t != "<N>" else r"\d+")
    return "(" + d + ")" if yakala else d


def _desen_kur(k, yakala=False):
    """Kalip metni -> duzenli ifade govdesi (yer tutucular sayi, gerisi
    aynen)."""
    parcalar, son = [], 0
    for m in _YT_KALIP.finditer(k):
        parcalar.append(re.escape(k[son:m.start()]))
        parcalar.append(_yt_desen(m.group(0), yakala))
        son = m.end()
    parcalar.append(re.escape(k[son:]))
    return "".join(parcalar)


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
# "Nn", "n") ya da kalipta olmayan yer tutucu hata sayilir. SIRA NUMARALI
# YER TUTUCU <N#k>: kalibin k'inci sayisi (ekranda "[sayı k]"); ayni sayi
# anlamda birden cok kez yazilabilir (<N>D_X<N>: "son <N#1> gün ile ondan
# önceki <N#1> gün").
# Koseli bicim (<N>, <N#1>) kendi sinirini tasir: harfe bitisik de yer
# tutucudur ("<N>gün"); harf siniri yalniz ciplak N / NN icin aranir
# (yoksa "<N>gün" icindeki N tek basina yakalanip "<3>gün" olurdu).
_YT_ADAY = re.compile(r"(<\s*[Nn]\s*#[^<>]{1,60}>|<\s*[Nn]{1,2}\s*>"
                      r"|(?<![0-9A-Za-zÇĞİÖŞÜçğıöşü])[Nn]{1,2}(?![0-9A-Za-zÇĞİÖŞÜçğıöşü]))")
# HESAPLI YER TUTUCU <N#formul>: formulde $k kalibin k'inci sayisi, tam
# sayilar ve + - * (ekranda "[sayı 1 × sayı 2]", "[sayı 1 + sayı 1]");
# <N#k> yalniz k'inci sayi (bas sifirlari korunur).
_FORMUL = re.compile(r"^\s*(\$\d+|\d+)(\s*[-+*]\s*(\$\d+|\d+))*\s*$")


def _yt_icerik(y):
    """<N#...> yer tutucusunun icerigi; degilse None."""
    m = re.match(r"^<\s*[Nn]\s*#(.*)>$", str(y or ""))
    return m.group(1).strip() if m else None


def anlam_duzelt(kalip, anlam):
    """Dil modelinin anlamindaki yer tutucu yazimlarini duzeltir:
    "<NN1>", "<N1>", "<N 1>" gibi sira numarali yazim "<N#1>" olur
    (kalipta ayni bicimde gecen tam basamakli <N2> ise "<N>"); sira
    numaralari kalibin sayilariyla sirayla ve birer kez geciyorsa duz yer
    tutucuya (kalipta <NN> ise "<NN>", degilse "<N>") cevrilir: "<NN1>:00
    ile <NN2>:00 arası" -> "<NN>:00 ile <NN>:00 arası"."""
    a = str(anlam or "")
    if not a:
        return a
    k = _norm(kalip)
    turler = ["<N>"] if aile_mi(k) else _YT_KALIP.findall(k)
    adet = len(turler)

    def cevir(m):
        ham = re.sub(r"\s+", "", m.group(0)).upper()
        if ham in turler and re.fullmatch(r"<N\d>", ham):
            return "<N>"
        n = int(m.group(1))
        return "<N#%d>" % n if 1 <= n <= adet else m.group(0)
    a = re.sub(r"<\s*[Nn]{1,2}\s*#?\s*(\d+)\s*>", cevir, a)
    refs = [int(x) for x in re.findall(r"<N#(\d+)>", a)]
    if refs and refs == list(range(1, adet + 1)) and not re.search(r"<N#[^\d>][^>]*>", a):
        it = iter(turler)
        a = re.sub(r"<N#\d+>", lambda _m: "<NN>" if next(it) == "<NN>" else "<N>", a)
    return a


def formul_hatasi(icerik, adet):
    """Hesapli yer tutucunun hatasi; yoksa ""."""
    if re.fullmatch(r"\d+", icerik):
        return "" if 1 <= int(icerik) <= adet else "kalıpta %s. sayı yok" % icerik
    if not _FORMUL.match(icerik):
        return "hesap anlaşılmadı (yalnız sayı, toplama, çıkarma ve çarpma)"
    kotu = [r for r in re.findall(r"\$(\d+)", icerik) if not 1 <= int(r) <= adet]
    return ("kalıpta %s. sayı yok" % kotu[0]) if kotu else ""


def formul_hesapla(icerik, sirali):
    """<N#icerik> -> metin (sirali: degerin sayilari); olmuyorsa None."""
    if re.fullmatch(r"\d+", icerik):
        k = int(icerik)
        return sirali[k - 1] if 1 <= k <= len(sirali) else None
    if not _FORMUL.match(icerik):
        return None
    toklar = re.findall(r"\$\d+|\d+|[-+*]", icerik)

    def deger(t):
        if t.startswith("$"):
            k = int(t[1:])
            if not 1 <= k <= len(sirali):
                raise ValueError(t)
            return int(sirali[k - 1])
        return int(t)
    try:
        terimler, islemler, cur = [], [], deger(toklar[0])
        for op, t in zip(toklar[1::2], toklar[2::2]):
            if op == "*":
                cur *= deger(t)
            else:
                terimler.append(cur)
                islemler.append(op)
                cur = deger(t)
        terimler.append(cur)
        sonuc = terimler[0]
        for op, t in zip(islemler, terimler[1:]):
            sonuc = sonuc + t if op == "+" else sonuc - t
    except (ValueError, IndexError):
        return None
    return str(sonuc)


def _formul_gorunur(icerik):
    """Ic hali ekrandaki gibi: $1*2 -> "[sayı 1 × 2]"; 1 -> "[sayı 1]"."""
    if re.fullmatch(r"\d+", icerik):
        return "[sayı %s]" % icerik
    m = re.sub(r"\$(\d+)", r"sayı \1", icerik.replace(" ", ""))
    return "[%s]" % re.sub(r"\s*([-+*])\s*", lambda x: " %s " % ("×" if x.group(1) == "*" else x.group(1)), m)


def yer_tutucu_hatasi(kalip, anlam):
    """Anlamdaki gecersiz yer tutucular icin hata metni; yoksa ""."""
    k = re.sub(r"\s+", "", str(kalip or "")).upper()
    izinli = set()
    if "<NN>" in k:
        izinli.update({"NN", "<NN>"})
    if re.search(r"<N\d?>", k):
        izinli.update({"N", "<N>"})
    adet = 1 if aile_mi(k) else len(_YT_KALIP.findall(k))
    kotu = []
    for m in _YT_ADAY.finditer(str(anlam or "")):
        icerik = _yt_icerik(m.group(1))
        if icerik is not None:
            if not formul_hatasi(icerik, adet):
                continue
            y = _formul_gorunur(icerik)
        else:
            y = re.sub(r"\s+", "", m.group(1))
        if y not in izinli and y not in kotu:
            kotu.append(y)
    # Taninmayan sira numarali yazim (<NN1>, <N3>): anlam_duzelt cevirmediyse hata.
    for m in re.finditer(r"<\s*[Nn]{1,2}\s*\d+\s*>", str(anlam or "")):
        y = re.sub(r"\s+", "", m.group(0))
        if y not in kotu:
            kotu.append(y)
    if not kotu:
        return ""
    if adet > 1:
        izinli.update("[sayı %d]" % i for i in range(1, adet + 1))
    if not izinli:
        return ("Anlamda yer tutucu var (%s) ama kalıpta sayı yer tutucusu yok; "
                "yerine değeri yazın." % ", ".join(kotu))
    gor = ["[sayı %d]" % i for i in range(1, adet + 1)] if adet > 1 else ["[sayı]"]
    return ("Anlamda geçersiz yer tutucu: %s. Bu kalıpta kullanılabilenler: %s."
            % (", ".join(kotu), ", ".join(gor)))


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
    turler = _YT_KALIP.findall(k)
    if not turler or not anlam:
        return anlam
    sayilar = _sayi_eslesmesi(k, deger)
    if sayilar is None:
        return anlam
    sirali = _sirali_sayilar(k, deger) or []
    sayac = Counter()

    def yer(mo):
        icerik = _yt_icerik(mo.group(1))
        if icerik is not None:
            h = formul_hesapla(icerik, sirali)
            return h if h is not None else mo.group(0)
        y = re.sub(r"[\s<>]", "", mo.group(1)).upper()
        liste = sayilar.get(y)
        if not liste:
            return mo.group(0)
        i = sayac[y]
        sayac[y] += 1
        return liste[min(i, len(liste) - 1)]
    return _YT_ADAY.sub(yer, anlam)


def _sirali_sayilar(kalip, deger):
    """Degerin kalibin yer tutucularina dusen sayilari kalipta gectikleri
    sirayla (tur ayrimi yok); uymuyorsa None."""
    k = _norm(kalip)
    d = _norm(deger)
    if aile_mi(k):
        r = kalip_deseni(k)
        return [re.search(r"\d+", d).group(0)] if r is not None and r.match(d) else None
    try:
        m = re.match("^" + _desen_kur(k, yakala=True) + "$", d)
    except re.error:
        return None
    return list(m.groups()) if m else None


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
    turler = _YT_KALIP.findall(k)
    try:
        m = re.match("^" + _desen_kur(k, yakala=True) + "$", d)
    except re.error:
        return None
    if not m:
        return None
    sayilar = {}
    for tur, sayi in zip(turler, m.groups()):
        sayilar.setdefault(_yt_tur(tur), []).append(sayi)
    return sayilar


def kalip_deseni(kalip):
    """Kalip adini derlenmis desene cevirir: <N> sayi, <NN> en az iki
    basamakli sayi, <N2> tam iki basamakli sayi, gerisi aynen. Aile ("<N>M") butun yazilislara uyar
    (3M, M3, 3_M, M_3). Gecersizse None."""
    k = re.sub(r"\s+", "", str(kalip or "")).upper()
    if not k:
        return None
    if aile_mi(k):
        h = re.escape(_AILE.match(k).group(1))
        return re.compile(r"^(?:\d+%s|%s\d+|\d+_%s|%s_\d+)$" % (h, h, h, h))
    try:
        return re.compile("^" + _desen_kur(k) + "$")
    except re.error:
        return None


DEGER_ORNEK_ADET = 3


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
    hafiza_kume = {_norm(x) for x in (ek or ())}
    bilgi = {}                      # kalip -> {"tur", "deger": Counter, "kolonlar": [], "kd": {}}

    def ekle(kalip, tur, deger, ad):
        b = bilgi.setdefault(kalip, {"tur": tur, "deger": Counter(), "kolonlar": [], "kd": {},
                                     "giris": []})
        b["giris"].append((ad, deger))
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
        atla = set()
        for i, p in enumerate(t):
            if i in atla:
                continue
            ay = ayrik_ikili(t, i)
            if ay:
                # 3_M / M_3: iki parca birlikte tek deger.
                aileye_ekle(ay[1], ad)
                atla.add(i + 1)
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
                # YAN YANA IKI DONEM PARCASI (3D_6D, 7D_X2): birlikte tek
                # zaman bilgisi olabilir (aralik, karsilastirma). Aday olarak
                # eklenir (tur "ikili"; kart Adaylar'a koyar); hafizadaki
                # ayni kalip zaten "hafiza" turuyle gelir.
                if i + 1 < len(t) and not _araligin_basi(t, i):
                    d2 = _donem_parcasi(t[i + 1])
                    if d2 and not ayrik_ikili(t, i + 1):
                        ik = kalip + "_" + d2[1]
                        if _norm(ik) not in hafiza_kume:
                            ekle(ik, "ikili", p + "_" + t[i + 1], ad)
    # HAFIZADAKI KALIPLAR (kullanicinin onceki calismalarda onayladigi ya
    # da kaydettigi): tek parca, <P>_<NN> ikilisi, yan yana iki donem
    # parcasi (3D_6D) ya da rakamsiz kalip (TMSNCFRST). Adlarda gecen her
    # biri "hafiza" turuyle eklenir. Bir kolonda hafiza kalibinin kapsadigi
    # parcalar kendiliginden bulunan kaliplardan dusulur (ayni deger iki
    # satirda sayilmasin: H<N2> kayitliyken H00 <N>H ailesine de girmez).
    # Hafizada olmayan rakamsiz parcalar (DAY, MONTH) burada degil, Ad
    # Parcalari'nda (parca.py) yorumlanir.
    desenler = [(k, kalip_deseni(k)) for k in (ek or []) if k not in bilgi
                and not (aile_adi(k) and not aile_mi(k) and _norm(k) not in ayri)]
    desenler = [(k, r) for k, r in desenler if r is not None]
    kapsanan = {}                   # ad -> hafiza kalibinin kapsadigi parcalar
    if desenler:
        for ad in adlar:
            t = _toklar(ad)
            # Araligin basi olan parca tek basina aday degil (bkz. aralik).
            adaylar = [p for i, p in enumerate(t) if not _araligin_basi(t, i)] + \
                [t[i] + "_" + t[i + 1] for i in range(len(t) - 1)
                 if _YALIN_SAYI.match(t[i + 1])
                 or (_donem_parcasi(t[i]) and _donem_parcasi(t[i + 1]))]
            for k, r in desenler:
                for p in adaylar:
                    if r.match(p):
                        ekle(k, "hafiza", p, ad)
                        kapsanan.setdefault(ad, set()).update(p.split("_"))
    for kalip in list(bilgi):
        b = bilgi[kalip]
        if b["tur"] == "hafiza" or not kapsanan:
            continue
        kalan = [(ad, d) for ad, d in b["giris"]
                 if not set(d.split("_")) <= kapsanan.get(ad, set())]
        if len(kalan) == len(b["giris"]):
            continue
        if not kalan:
            del bilgi[kalip]
            continue
        b.update(giris=kalan, deger=Counter(d for _a, d in kalan), kolonlar=[], kd={})
        for ad, d in kalan:
            if ad not in b["kolonlar"]:
                b["kolonlar"].append(ad)
                b["kd"][ad] = d

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
        # DEGER ORNEKLERI: her degerin adinda gectigi ilk uc kolon ve
        # tanimi (kartta degerin "i"sinde).
        deger_ornek = {}
        for ad, d in b["giris"]:
            liste_ = deger_ornek.setdefault(d, [])
            if len(liste_) < DEGER_ORNEK_ADET and all(a_ != ad for a_, _t in liste_):
                liste_.append((ad, str(tanimlar.get(ad) or "").strip()))
        k = {"kalip": kalip, "tur": b["tur"], "kolon": len(b["kolonlar"]),
             "degerler": degerler, "ornekler": [(ad, t) for ad, t, _d in ornek],
             "deger_ornek": deger_ornek}
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


def tek_kalip(adlar, tanimlar, kalip):
    """KULLANICININ EKLEDIGI tek kalip icin dil modeli girdisi (bkz.
    kaliplar): adlarda kalibin desenine uyan parcalar (tek parca ya da
    <P>_<NN> ikilisi) degerler, tanimi olan kolonlar ornekler; yer
    tutucusuz kalipta birlikte gectigi ikililer de. Adlarda gecmiyorsa
    None."""
    r = kalip_deseni(kalip)
    if r is None:
        return None
    k = _norm(kalip)
    tanimlar = tanimlar or {}
    sayac, kolonlar = Counter(), []
    for ad in adlar:
        t = _toklar(ad)
        adaylar = list(t) + [t[i] + "_" + t[i + 1] for i in range(len(t) - 1)]
        bulunan = [p for p in adaylar if r.match(p)]
        for p in dict.fromkeys(bulunan):
            sayac[p] += 1
        if bulunan:
            kolonlar.append((ad, bulunan[0]))
    if not kolonlar:
        return None
    ornek, gorulen = [], set()
    tanimli = [(a, str(tanimlar.get(a) or "").strip(), d) for a, d in kolonlar]
    tanimli = [x for x in tanimli if x[1]]
    for a, tn, d in tanimli:                      # once farkli degerler
        if len(ornek) < ORNEK_ADET and d not in gorulen:
            ornek.append((a, tn)); gorulen.add(d)
    for a, tn, d in tanimli:
        if len(ornek) >= ORNEK_ADET:
            break
        if (a, tn) not in ornek:
            ornek.append((a, tn))
    cikti = {"kalip": k, "tur": "elle", "kolon": len(kolonlar),
             "degerler": sorted(sayac.items(), key=lambda kv: (-kv[1], kv[0])),
             "ornekler": ornek}
    if "<" not in k:
        b = birlikte_haritasi(adlar, tanimlar).get(k)
        if b:
            cikti.update(birlikte=b["birlikte"], tek=b["tek"], birlikte_ornek=dict(b["ornekler"]))
    return cikti


def parca_listesi(adlar, tanimlar, ornek=2):
    """Kolon adlarindaki BUTUN parcalar (yalniz rakam haric): [{"parca",
    "kolon", "donem": donem kalibina uyuyor mu, "ikili": aralik ikilisi mi,
    "ornekler": [(kolon, tanim)], "grup": grubun kalibi (parca_gruplari),
    "grup_kolon": grubun farkli kolon sayisi}], alfabetik. Ardindan yalniz rakam gelen
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
            # Yan yana iki sayili donem parcasi (3D_6D) ikili olarak da
            # girer: "<N>D_<N>D" gibi bir kalip (ör. arasinda) alinabilsin.
            elif i + 1 < len(t) and _donem_parcasi(p) and _donem_parcasi(t[i + 1]):
                gorulen.append(p + "_" + t[i + 1])
                ikililer.add(p + "_" + t[i + 1])
        for p in dict.fromkeys(gorulen):
            kolonlar.setdefault(p, []).append(ad)
    # GRUPLAR: grubun kolon sayisi uyelerin gectigi FARKLI kolonlar (bir
    # kolon adinda iki uye gecerse bir kez sayilir).
    gruplar = parca_gruplari(kolonlar.keys())
    grup_kolon = {}
    for p, liste in kolonlar.items():
        g = gruplar.get(p)
        if g:
            grup_kolon.setdefault(g, set()).update(liste)
    cikti = []
    for p, liste in kolonlar.items():
        ornekler = [(a, str(tanimlar.get(a) or "").strip()[:200]) for a in liste[:ornek]]
        b = bh.get(p) or {}
        g = gruplar.get(p)
        cikti.append({"parca": p, "kolon": len(liste), "ikili": p in ikililer,
                      "donem": p in ikililer or p in ayrik_harf or bool(_donem_parcasi(p)),
                      "ornekler": ornekler, "birlikte": b.get("birlikte") or [],
                      "tek": b.get("tek", len(liste)), "grup": g,
                      "grup_kolon": len(grup_kolon[g]) if g else None})
    cikti.sort(key=lambda x: x["parca"])
    return cikti


_SAYI_KOSU = re.compile(r"\d+")


def parca_gruplari(parcalar):
    """{parca: grup kalibi}. Yalniz sayilari farkli parcalar bir grup
    (H00, H06, H12 -> ayni grup; 3D, 30D -> ayni grup). SABIT GENISLIK:
    gruptaki bir sayi basta sifirla yaziliyorsa (00, 06) sayilarin basamak
    sayisi anlamlidir; grup basamak sayisina gore bolunur ve kalip tam
    basamakli yer tutucuyla yazilir (H00, H06, H12 -> "H<N2>"; H000 ayri,
    "H<N3>"). Basta sifir yoksa basamak sayisi onemsiz (3D, 30D -> "<N>D").
    Sayisiz ya da yalniz sayi olan parca gruba girmez."""
    kaba = {}
    for p in parcalar:
        k = _norm(p)
        if not _SAYI_KOSU.search(k) or _YALIN_SAYI.match(k.replace("_", "")):
            continue
        kaba.setdefault(_SAYI_KOSU.sub("<N>", k), []).append(k)
    cikti = {}
    for anahtar, uyeler in kaba.items():
        sabit = any(len(x) > 1 and x.startswith("0")
                    for u in uyeler for x in _SAYI_KOSU.findall(u))
        for u in uyeler:
            cikti[u] = (_SAYI_KOSU.sub(lambda m: "<N%d>" % len(m.group(0)), u)
                        if sabit else anahtar)
    return cikti


def parca_grubu(p, parcalar=None):
    """Tek parcanin grubu (parcalar: ayni listedeki obur parcalar; sabit
    genislik karari listeye gore verilir). Bkz. parca_gruplari."""
    return parca_gruplari(list(parcalar or []) + [p]).get(_norm(p))


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


def hafiza_ayrik():
    """{grup}: «Ayır» ile degerlerine ayrilmis gruplar."""
    try:
        return kisaltma_mod.donem_ayrik_hafizasi()
    except Exception:
        return set()


def hafizaya_ayrik_yaz(gruplar, ayrik):
    """Bu calismada gorulen gruplarin «Ayır» isareti. Doner: hata ya da None."""
    try:
        return kisaltma_mod.donem_ayrik_kaydet(gruplar, ayrik)
    except Exception as e:
        return "Ayrılan gruplar hafızaya yazılamadı (%s)." % str(e)[:120]


def hafiza_ayri():
    """{kalip}: ailesinden ayri anlamla onaylanmis yazilis kaliplari."""
    try:
        return kisaltma_mod.donem_ayri_hafizasi()
    except Exception:
        return set()


def hafiza_kosul():
    """{kalip: {PARCA: anlam}}: adda PARCA gecerse kalibin anlami."""
    try:
        return kisaltma_mod.donem_kosul_hafizasi()
    except Exception:
        return {}


def hafizaya_kosul_yaz(kosullar):
    """{kalip: {PARCA: anlam}} (bos: kalibin kosullu anlamlari kalkar)."""
    return kisaltma_mod.donem_kosul_kaydet(kosullar)


def kosullu_anlam(anlam, kosullar, toklar):
    """Kolonun adinda (toklar) gecen ilk kosul parcasinin anlami; yoksa
    kalibin anlami. Kosullar parca adina gore sirali denenir."""
    t = {str(x).upper() for x in toklar or ()}
    for p in sorted(kosullar or {}):
        if p in t and str(kosullar[p] or "").strip():
            return kosullar[p]
    return anlam


def hafiza_ad():
    """{kalip: yeni adda yazilis sablonu}."""
    try:
        return kisaltma_mod.donem_ad_hafizasi()
    except Exception:
        return {}


def hafizaya_ad_yaz(sablonlar):
    """{kalip: sablon} (bos: kaydi kaldir). Doner: hata ya da None."""
    return kisaltma_mod.donem_ad_kaydet(sablonlar)


# YENI ADDA YAZILIS: kalibin yeni kolon adlarinda nasil yazilacagi (ör.
# <N>D_<N>D -> BTWN_<N>D_<N>D). Sablondaki yer tutucular kalibinkilerle
# ayni sayida ve sirada; harf, rakam, alt cizgi.
_AD_SABLON = re.compile(r"^(?:[A-Z0-9_]|<NN>|<N\d?>)+$")
# Yeni adda yazilista sira numarali ve hesapli yer tutucu da (<N#1>,
# <N#$1*$2>; ekranda [sayı 1], [sayı 1 × sayı 2]).
_AD_YT = re.compile(r"<N#[^<>]{1,60}>|<NN>|<N\d>|<N>")


def ad_sablonu_hatasi(kalip, sablon):
    """Sablon gecersizse hata metni; bos sablon gecerlidir (kalip aynen)."""
    s = _norm(sablon)
    if not s:
        return ""
    if not _AD_SABLON.match(re.sub(r"<N#[^<>]{1,60}>", "<N>", s)) or not re.match(r"^[A-Z<]", s):
        return ("yeni adda yazılış yalnız büyük harf, rakam, alt çizgi ve [sayı] "
                "içerebilir; harfle ya da [sayı] ile başlar.")
    k = _norm(kalip)
    n_kalip = 1 if aile_mi(k) else len(_YT_KALIP.findall(k))
    numarali = [_yt_icerik(m) for m in re.findall(r"<N#[^<>]{1,60}>", s)]
    for ic in numarali:
        h = formul_hatasi(ic, n_kalip)
        if h:
            return "yeni adda yazılışta %s: %s." % (_formul_gorunur(ic), h)
    n_sablon = len(_YT_KALIP.findall(re.sub(r"<N#[^<>]{1,60}>", "", s)))
    if numarali:
        # Numarali yer tutucu varsa her sayi istendigi kadar kullanilir.
        if n_sablon > n_kalip:
            return ("yeni adda yazılışta %d sıralı [sayı] var, kalıpta %d."
                    % (n_sablon, n_kalip))
        return ""
    if n_sablon != n_kalip:
        return ("yeni adda yazılışta %d [sayı] var, kalıpta %d; aynı sayıda olmalı."
                % (n_sablon, n_kalip))
    return ""


def ad_sablonu_doldur(kalip, sablon, deger):
    """Degerin sayilari sablonun yer tutucularina sirayla yazilir (3D_6D +
    BTWN_<N>D_<N>D -> BTWN_3D_6D). Uymazsa deger aynen."""
    k, s, d = _norm(kalip), _norm(sablon), _norm(deger)
    if not s:
        return d
    if aile_mi(k):
        r = kalip_deseni(k)
        if r is None or not r.match(d):
            return d
        sayilar = [re.search(r"\d+", d).group(0)]
    else:
        try:
            m = re.match("^" + _desen_kur(k, yakala=True) + "$", d)
        except re.error:
            return d
        if not m:
            return d
        sayilar = list(m.groups())
    if not sayilar:
        return s
    i = [0]

    def yer(m):
        ic = _yt_icerik(m.group(0))
        if ic is not None:
            h = formul_hesapla(ic, sayilar)
            return h if h is not None else m.group(0)
        v = sayilar[min(i[0], len(sayilar) - 1)]
        i[0] += 1
        return v
    return _AD_YT.sub(yer, s)


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
ISTEM_SURUMU = 10


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
    # Hafizada anlami olan kalip (aile icin bir yazilisinin kaydi da) da
    # sorulur: dil modeli hafizadaki anlamin bu veri setinin tanimlariyla
    # uyusup uyusmadigini sayar (kart uyusmayani Adaylar'a koyar).
    sorulacak = []
    for x in liste:
        hk = hafiza_anahtari(x["kalip"], haf, ayri)
        if hk and haf.get(hk):
            # Ornek deger dolu haliyle de gider: dil modeli yer tutuculari
            # (her N kendi sayisi) yanlis okumasin.
            d0 = (x.get("degerler") or [[""]])[0][0]
            sorulacak.append(dict(x, hafiza_anlam=haf[hk],
                                  hafiza_ornek=(d0, deger_anlami(x["kalip"], haf[hk], d0)) if d0 else None))
        else:
            sorulacak.append(x)

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
            # Yer tutucu yazimi (<NN1> gibi) duzeltilir.
            for kk, m in (sonuc or {}).items():
                if isinstance(m, dict) and m.get("anlam"):
                    m["anlam"] = anlam_duzelt(kk, m["anlam"])
                for a_ in (m or {}).get("ayri") or [] if isinstance(m, dict) else []:
                    if isinstance(a_, dict) and a_.get("anlam") and a_.get("yazilis"):
                        a_["anlam"] = anlam_duzelt(a_["yazilis"], a_["anlam"])
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
