"""fe_agent/donem_tur.py - DONEM ANLAM TURLERI (birimli kaliplar).

Sorun: <N>D gibi BIRIMLI bir kalibin (sayi + zaman birimi) anlami kolondan
kolona degisir: bir kolonda "son 30 gün", baskasinda "30 gün sonra" ya da
"30 gün önce", baskasinda yalniz "30 gün" (sure). Kalibe tek anlam ve tek
yeni ad yazilisi verilirse bazi kolonlar yanlis ad alir ve hafizaya yanlis
ogretilir.

Cozum:
  * 01.2.4.1 Donem Bilgisi: birimli kalibin anlami BIRIMdir ("<N> gün",
    yonsuz). Altinda ANLAM TURLERI: son, önce, sonra, süre (sabit) ve
    kullanicinin ekledigi turler. Kod butun tanimlarda her turun kac
    kolonda gectigini sayar (kesin sayim; tanimda yon yoksa "belirsiz").
  * 01.2.4.3 Kolon Kartlari: her kolonda donemin hangi turle kullanildigi
    belirlenir: kullanicinin secimi > onayli aciklamadaki ifade (kod) >
    dil modelinin isareti > belirsiz. Belirsiz kolonda tur sorulur.
  * 01.2.4.4 Kolon Adlari: Donem Yazilislari kalip x tur satirlaridir;
    her kolon kendi turunun yazilisiyla adlanir. Belirsiz kolonun donem
    kismi degismez.
  * Hafiza: kalibin anlami birim; turler {tur: {"ad", "anlam",
    "yeni_adda"}}. Bir yazilis bir kalipta yalniz TEK ture baglanir.
    Yeni yazilis (L<N>D) kendi kalibi olarak kesin anlamiyla da yazilir:
    sonraki calismada L30D kesin "son 30 gün", yalin 30D ise belirsizdir.

Kapsam: yalniz birimli kaliplar (<N>D, D<N>, <N>_D, D_<N>; donem.aile_adi
dolu olanlar). Saat araligi (H<NN>_<NN>) ve harf + sayi + harf (L<N>D)
kaliplari kendi anlamini tasir, bu kurala girmez.
"""

import re

from fe_agent import donem as donem_mod

# (kod, ekrandaki ad, varsayilan yeni ad harfi); sira ekrandaki siradir.
SABIT_TURLER = (("son", "Son", "L"), ("once", "Önce", "B"), ("sonra", "Sonra", "N"),
                ("sure", "Süre", ""))
SABIT_KODLAR = tuple(k for k, _a, _h in SABIT_TURLER)
TUR_ADI = {k: a for k, a, _h in SABIT_TURLER}
TUR_HARF = {k: h for k, _a, h in SABIT_TURLER}
BELIRSIZ = "belirsiz"

# Birim anlamindan atilan yon sozcukleri (son 30 gün -> 30 gün).
_YON_SOZCUKLERI = {"son", "önce", "önceki", "öncesi", "öncesine", "önceye", "geçmiş",
                   "sonra", "sonraki", "sonrası", "sonrasına", "gelecek", "boyunca",
                   "süresince", "süreyle"}
_KUCUK = str.maketrans({"I": "ı", "İ": "i"})
_SOZCUK = re.compile(r"[0-9a-zçğıöşüâîû]+")
# Rakamla yazilmamis sayilar (tanimlarda "son üç ay").
_SAYI_SOZCUK = {"bir": 1, "iki": 2, "üç": 3, "dört": 4, "beş": 5, "altı": 6, "yedi": 7,
                "sekiz": 8, "dokuz": 9, "on": 10, "yirmi": 20, "otuz": 30, "kırk": 40,
                "elli": 50, "altmış": 60, "yetmiş": 70, "seksen": 80, "doksan": 90}
OZEL_KOD = re.compile(r"^[a-z][a-z0-9_]{0,23}$")


def _kucuk(metin):
    return str(metin or "").translate(_KUCUK).lower()


def birimli_mi(kalip):
    """Sayi + zaman birimi kalibi mi (<N>D, D<N>, <N>_D, D_<N>)?"""
    try:
        return bool(donem_mod.aile_adi(str(kalip or "")))
    except Exception:
        return False


def birim_anlami(anlam):
    """Anlamdan yon sozcukleri atilmis hali ("son <N> gün" -> "<N> gün")."""
    parca = [x for x in re.split(r"(\s+)", str(anlam or "")) if x]
    kalan = [x for x in parca if _kucuk(x.strip(".,;")) not in _YON_SOZCUKLERI]
    return re.sub(r"\s+", " ", "".join(kalan)).strip()


def anlamdaki_tur(anlam):
    """Anlamdaki yon sozcugunden tur (eski hafiza kaydini tasimak icin)."""
    w = [_kucuk(x) for x in _SOZCUK.findall(_kucuk(anlam))]
    if "son" in w or "geçmiş" in w:
        return "son"
    if any(x.startswith("önce") for x in w):
        return "once"
    if any(x.startswith("sonra") for x in w) or "gelecek" in w:
        return "sonra"
    return ""


def tur_anlami(tur, birim, ozel=None):
    """Turun anlam sablonu: son -> "son <N> gün", önce -> "<N> gün önce",
    sonra -> "<N> gün sonra", süre -> "<N> gün"; ozel tur kendi anlamiyla."""
    b = str(birim or "").strip()
    if tur == "son":
        return ("son " + b).strip()
    if tur == "once":
        return (b + " önce").strip()
    if tur == "sonra":
        return (b + " sonra").strip()
    if tur == "sure":
        return b
    return str(((ozel or {}).get(tur) or {}).get("anlam") or "").strip()


def varsayilan_yazilis(kalip, tur):
    """Turun varsayilan yeni ad yazilisi: harf kalibin onune (<N>D ->
    L<N>D, D<N> -> LD<N>); süre ve ozel tur bos (kalip aynen)."""
    h = TUR_HARF.get(tur) or ""
    return (h + str(kalip)) if h else ""


def birim_sozcugu(birim):
    """Birim anlamindaki ilk birim sozcugu ("<N> gün" -> "gün")."""
    for w in _SOZCUK.findall(_kucuk(re.sub(r"<[^<>]*>", " ", str(birim or "")))):
        if not w.isdigit() and w not in _YON_SOZCUKLERI:
            return w
    return ""


def _sayi_mi(sozcuk, sayi):
    if sozcuk.isdigit():
        return int(sozcuk) == sayi
    return _SAYI_SOZCUK.get(sozcuk) == sayi


def metinden_tur(metin, sayi, birim):
    """Tanimda sayinin ve birimin gectigi ifadeden tur: "son 30 gün" son,
    "30 gün önce(ki)" önce, "30 gün sonra(ki)" ya da "önümüzdeki 30 gün"
    sonra, "30 gün boyunca" süre. Ifadede yon yoksa ya da birden fazla tur
    geciyorsa None (belirsiz)."""
    try:
        sayi = int(sayi)
    except (TypeError, ValueError):
        return None
    bs = birim_sozcugu(birim)
    if not bs:
        return None
    w = _SOZCUK.findall(_kucuk(metin))
    bulunan = set()
    for i, x in enumerate(w):
        if not _sayi_mi(x, sayi) or i + 1 >= len(w) or not w[i + 1].startswith(bs):
            continue
        once_ = w[max(0, i - 2):i]
        sonra_ = w[i + 2:i + 4]
        if "son" in once_ or "geçmiş" in once_:
            bulunan.add("son")
        elif any(y.startswith("önce") for y in sonra_):
            bulunan.add("once")
        elif any(y.startswith("sonra") for y in sonra_) or "önümüzdeki" in once_ \
                or "gelecek" in once_:
            bulunan.add("sonra")
        elif any(y in ("boyunca", "süresince", "süreyle") for y in sonra_):
            bulunan.add("sure")
        else:
            bulunan.add(BELIRSIZ)
    # Ayni sayi bir yerde yonlu, bir yerde yonsuz geciyorsa yonlu olan
    # gecerli ("son 30 günde ... 30 günlük ortalama"); iki farkli yon ya da
    # hic yon yoksa belirsiz.
    yonlu = bulunan - {BELIRSIZ}
    return next(iter(yonlu)) if len(yonlu) == 1 else None


def deger_sayisi(kalip, deger):
    """Degerin sayisi (30D -> 30); uymazsa None."""
    m = re.search(r"\d+", str(deger or ""))
    r = donem_mod.kalip_deseni(kalip)
    if not m or r is None or not r.match(str(deger)):
        return None
    return int(m.group(0))


def hafiza_turleri():
    """{kalip: {tur: {"ad", "anlam", "yeni_adda"}}} hafizadan."""
    try:
        from fe_agent import kisaltma as kisaltma_mod
        return kisaltma_mod.donem_anlam_turleri_hafizasi()
    except Exception:
        return {}


def hafizaya_turler_yaz(kayitlar):
    """Bkz. kisaltma.donem_anlam_turleri_kaydet. Doner: hata ya da None."""
    try:
        from fe_agent import kisaltma as kisaltma_mod
        return kisaltma_mod.donem_anlam_turleri_kaydet(kayitlar)
    except Exception as e:
        return "Dönem anlam türleri hafızaya yazılamadı (%s)." % str(e)[:120]


def kalip_turleri(kalip, birim, ozel=None, haf=None, haf_anlam="", haf_ad=""):
    """Kalibin turleri, ekrandaki sirayla: [{"tur", "ad", "anlam", "ozel",
    "yazilis"}]. yazilis hafizadan (tur kaydi; eski kayitta kalibin tek
    yazilisi, eski anlamindaki yon turune), yoksa varsayilan. ozel: {tur:
    {"ad", "anlam"}} bu calismada eklenenler."""
    haf = (haf if haf is not None else hafiza_turleri()).get(kalip) or {}
    eski_tur = anlamdaki_tur(haf_anlam) if haf_ad else ""
    cikti = []
    for k, ad, _h in SABIT_TURLER:
        y = (haf.get(k) or {}).get("yeni_adda")
        if y is None and k == eski_tur:
            y = haf_ad
        cikti.append({"tur": k, "ad": ad, "anlam": tur_anlami(k, birim), "ozel": False,
                      "yazilis": y if y is not None else varsayilan_yazilis(kalip, k)})
    tum_ozel = {t: x for t, x in haf.items() if t not in SABIT_KODLAR}
    tum_ozel.update({t: x for t, x in (ozel or {}).items() if t not in SABIT_KODLAR})
    for t, x in sorted(tum_ozel.items()):
        cikti.append({"tur": t, "ad": str(x.get("ad") or t), "anlam": str(x.get("anlam") or ""),
                      "ozel": True,
                      "yazilis": str((haf.get(t) or {}).get("yeni_adda") or x.get("yeni_adda") or "")})
    return cikti


def yazilis_cakismasi(kalip, yazilislar):
    """{tur: yazilis}: ayni yazilis iki ture verildiyse hata metni (bos
    yazilis, yani kalip aynen, de tek ture verilebilir)."""
    gor = {}
    for t, y in yazilislar.items():
        anahtar = re.sub(r"\s+", "", str(y or "")).upper() or str(kalip)
        if anahtar in gor:
            return ("%s ve %s türleri aynı yazılışı alamaz (%s); yeni adda iki anlam "
                    "ayırt edilemez." % (gor[anahtar], t, anahtar))
        gor[anahtar] = t
    return ""
