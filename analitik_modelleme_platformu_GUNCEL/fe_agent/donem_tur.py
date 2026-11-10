"""fe_agent/donem_tur.py - DONEM ANLAM TURLERI (birimli kaliplar).

Sorun: <N>D gibi BIRIMLI bir kalibin (sayi + zaman birimi) anlami kolondan
kolona degisir. 3D yalniz basina belirsizdir: gecmise mi gelecege mi
(ya da ikisine mi) bakar, aralik mi (1., 2., 3. gun) yoksa tek gun mu
(tam 3 gun oncesi) kapsar? Kalibe tek anlam ve tek yeni ad yazilisi
verilirse bazi kolonlar yanlis ad alir ve hafizaya yanlis ogretilir.

Cozum: her tur iki eksenle tanimlanir.
  * YON: gecmis, gelecek, iki (gecmis ve gelecek), yonsuz.
  * BICIM: pencere (araligin tamami), nokta (yalniz uctaki gun), uzunluk
    (yonsuz: tarih araligi degil, bir surenin uzunlugu).
Sabit turler (3D icin; "bugun" referans tarihidir, pencereye dahil degil):
  son      gecmis  pencere  son 3 gün                bugunden onceki 1., 2., 3. gun   L3D
  once     gecmis  nokta    3 gün önce               yalniz 3 gun oncesi             B3D
  sonraki  gelecek pencere  sonraki 3 gün            bugunden sonraki 1., 2., 3. gun N3D
  sonra    gelecek nokta    3 gün sonra              yalniz 3 gun sonrasi            A3D
  cevre    iki     pencere  3 gün öncesi ve sonrası  3 gun oncesinden 3 gun sonrasina PM3D
  sure     yonsuz  uzunluk  3 gün                    bir surenin uzunlugu            aynen
Kullanicinin ekledigi tur de yon ve bicim tasir.

Akis:
  * 01.2.4.1 Donem Bilgisi: birimli kalibin anlami BIRIMdir ("<N> gün",
    yonsuz). Altinda ANLAM TURLERI ve kapsadiklari gunler. Kod butun
    tanimlarda her turun kac kolonda gectigini sayar (kesin sayim;
    tanimda yon yoksa "belirsiz").
  * 01.2.4.3 Kolon Kartlari: her kolonda donemin turu: kullanicinin
    secimi > onayli aciklamadaki ifade (kod) > dil modelinin isareti >
    belirsiz. Belirsiz kolonda tur sorulur.
  * 01.2.4.4 Kolon Adlari: Donem Yazilislari kalip x tur satirlaridir;
    her kolon kendi turunun yazilisiyla adlanir. Belirsiz kolonun donem
    kismi degismez.
  * Hafiza: kalibin anlami birim; turler {tur: {"ad", "anlam",
    "yeni_adda", "yon", "bicim"}}. Bir yazilis bir kalipta yalniz TEK
    ture baglanir. Yeni yazilis (L<N>D) kendi kalibi olarak kesin
    anlamiyla da yazilir.

Kapsam: yalniz birimli kaliplar (<N>D, D<N>, <N>_D, D_<N>; donem.aile_adi
dolu olanlar). Saat araligi (H<NN>_<NN>), iki parcali kaliplar ve harf +
sayi + harf (L<N>D) kaliplari kendi anlamini tasir, bu kurala girmez.
"""

import re

from fe_agent import donem as donem_mod

# (kod, ekrandaki ad, varsayilan yeni ad oneki, yon, bicim); sira ekrandaki
# siradir.
SABIT_TURLER = (
    ("son", "Son", "L", "gecmis", "pencere"),
    ("once", "Önce", "B", "gecmis", "nokta"),
    ("sonraki", "Sonraki", "N", "gelecek", "pencere"),
    ("sonra", "Sonra", "A", "gelecek", "nokta"),
    ("cevre", "Çevre", "PM", "iki", "pencere"),
    ("takvim", "Takvim", "C", "takvim", "nokta"),
    ("sure", "Süre", "", "yonsuz", "uzunluk"),
)
SABIT_KODLAR = tuple(x[0] for x in SABIT_TURLER)
TUR_ADI = {x[0]: x[1] for x in SABIT_TURLER}
TUR_HARF = {x[0]: x[2] for x in SABIT_TURLER}
TUR_YON = {x[0]: x[3] for x in SABIT_TURLER}
TUR_BICIM = {x[0]: x[4] for x in SABIT_TURLER}
YON_ADI = {"gecmis": "Geçmiş", "gelecek": "Gelecek", "iki": "İki yönlü", "takvim": "Takvim",
           "yonsuz": "Yönsüz"}
# TAKVIM: sayi bugune gore degil, takvimdeki yeri gosterir (M3: yilin 3.
# ayi). Birime gore kap ve sira eki: birim -> (kap, ekli birim).
_TAKVIM = {"gün": ("ayın", "günü"), "hafta": ("yılın", "haftası"), "ay": ("yılın", "ayı"),
           "çeyrek": ("yılın", "çeyreği"), "saat": ("günün", "saati"),
           "dakika": ("saatin", "dakikası")}
# Takvim anlamindaki ekli birimden yalin birime (ayı -> ay).
_TAKVIM_YALIN = {e: b for b, (_k, e) in _TAKVIM.items()}
_TAKVIM_YALIN.update({"yılı": "yıl"})
# Sira sozcukleri (tanimlarda "üçüncü ay").
_SIRA_SOZCUK = {"birinci": 1, "ikinci": 2, "üçüncü": 3, "dördüncü": 4, "beşinci": 5,
                "altıncı": 6, "yedinci": 7, "sekizinci": 8, "dokuzuncu": 9, "onuncu": 10}
BICIM_ADI = {"pencere": "Pencere", "nokta": "Nokta", "uzunluk": "Uzunluk"}
BELIRSIZ = "belirsiz"
# Onceki surumde "sonra" turunun varsayilan yazilisi N idi (o surumde sonra
# hem nokta hem gelecek pencereyi kapsiyordu). Bicim alani olmayan eski
# "sonra" kaydindaki N yazilisi kullanilmaz (bkz. kalip_turleri).
ESKI_SONRA_HARF = "N"

# Birim anlamindan atilan yon sozcukleri (son 30 gün -> 30 gün).
_YON_SOZCUKLERI = {"son", "önce", "önceki", "öncesi", "öncesine", "önceye", "geçmiş", "geçen",
                   "sonra", "sonraki", "sonrası", "sonrasına", "gelecek", "önümüzdeki",
                   "izleyen", "ileriki", "kadar", "boyunca", "süresince", "süreyle"}
_KUCUK = str.maketrans({"I": "ı", "İ": "i"})
_SOZCUK = re.compile(r"[0-9a-zçğıöşüâîû]+")
# Rakamla yazilmamis sayilar (tanimlarda "son üç ay").
_SAYI_SOZCUK = {"bir": 1, "iki": 2, "üç": 3, "dört": 4, "beş": 5, "altı": 6, "yedi": 7,
                "sekiz": 8, "dokuz": 9, "on": 10, "yirmi": 20, "otuz": 30, "kırk": 40,
                "elli": 50, "altmış": 60, "yetmiş": 70, "seksen": 80, "doksan": 90}
# Sayidan ONCE gelip pencere bildiren sozcukler.
_GECMIS_PENCERE = {"son", "geçmiş", "geçen", "önceki"}
_GELECEK_PENCERE = {"sonraki", "önümüzdeki", "gelecek", "izleyen", "ileriki"}
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
    """Anlamdan yon sozcukleri atilmis hali ("son <N> gün" -> "<N> gün",
    "<N> gün öncesi ve sonrası" -> "<N> gün"); takvim anlami da birime
    doner ("yılın <N>. ayı" -> "<N> ay", "ayın <N>. günü" -> "<N> gün")."""
    metin = re.sub(r"±\s*", "", str(anlam or ""))
    m = re.search(r"(<N\d*>|<NN>)\s*(\.\s*)?([^\s.,;<>]+)", metin)
    if m and _kucuk(m.group(3)) in _TAKVIM_YALIN and (m.group(2) or _kucuk(m.group(3)) == "yılı"):
        return "%s %s" % (m.group(1), _TAKVIM_YALIN[_kucuk(m.group(3))])
    parca = [x for x in re.split(r"(\s+)", metin) if x]
    kalan = [x for x in parca if _kucuk(x.strip(".,;")) not in _YON_SOZCUKLERI]
    metin = re.sub(r"\s+", " ", "".join(kalan)).strip()
    return re.sub(r"^ve\s+|\s+ve$", "", metin).strip()


def tur_bilgisi(tur, ozel=None):
    """(yon, bicim) - sabit turde sabit, ozel turde kaydindan; yoksa ("", "")."""
    if tur in TUR_YON:
        return TUR_YON[tur], TUR_BICIM[tur]
    x = (ozel or {}).get(tur) or {}
    yon = str(x.get("yon") or "")
    yon = yon if yon in YON_ADI else ""
    bicim = "uzunluk" if yon == "yonsuz" else str(x.get("bicim") or "")
    return yon, (bicim if bicim in ("pencere", "nokta", "uzunluk") else "")


def tur_anlami(tur, birim, ozel=None):
    """Turun anlam sablonu: son -> "son <N> gün", önce -> "<N> gün önce",
    sonraki -> "sonraki <N> gün", sonra -> "<N> gün sonra", çevre -> "<N>
    gün öncesi ve sonrası", süre -> "<N> gün"; ozel tur kendi anlamiyla."""
    b = str(birim or "").strip()
    if tur == "son":
        return ("son " + b).strip()
    if tur == "once":
        return (b + " önce").strip()
    if tur == "sonraki":
        return ("sonraki " + b).strip()
    if tur == "sonra":
        return (b + " sonra").strip()
    if tur == "cevre":
        return (b + " öncesi ve sonrası").strip()
    if tur == "sure":
        return b
    if tur == "takvim":
        return takvim_anlami(b)
    return str(((ozel or {}).get(tur) or {}).get("anlam") or "").strip()


def takvim_anlami(birim, sayi=None):
    """Takvimdeki yer: "<N> ay" -> "yılın <N>. ayı", "<N> gün" -> "ayın
    <N>. günü", "<N> yıl" -> "<N> yılı"; bilinmeyen birimde "<N>. birim"."""
    bs = birim_sozcugu(birim)
    n = sayi if isinstance(sayi, int) else "<N>"
    if not bs:
        return ""
    if bs == "yıl":
        return "%s yılı" % n
    if bs in _TAKVIM:
        kap, ek = _TAKVIM[bs]
        return "%s %s. %s" % (kap, n, ek)
    return "%s. %s" % (n, bs)


def _sira_listesi(n, bs):
    """1., 2., 3. gün (n <= 3) ya da 1. ile 30. gün arası."""
    if isinstance(n, int) and n <= 3:
        return "%s %s" % (", ".join("%d." % i for i in range(1, max(n, 1) + 1)), bs)
    return "1. ile %s. %s arası" % (n, bs)


def kapsam_metni(yon, bicim, birim, sayi=None):
    """Turun kapsadigi gunler, somut: "bugünden önceki 1., 2., 3. gün",
    "yalnız 3 gün öncesi" ... sayi yoksa yer tutucu (<N>) kalir. Yon ya da
    bicim bilinmiyorsa bos."""
    bs = birim_sozcugu(birim)
    if not bs or not yon:
        return ""
    n = sayi if isinstance(sayi, int) else "<N>"
    if yon == "yonsuz" or bicim == "uzunluk":
        return "tarih aralığı değil, bir sürenin uzunluğu (%s %s)" % (n, bs)
    if yon == "gecmis":
        return ("bugünden önceki " + _sira_listesi(n, bs)) if bicim == "pencere" \
            else "yalnız %s %s öncesi" % (n, bs)
    if yon == "gelecek":
        return ("bugünden sonraki " + _sira_listesi(n, bs)) if bicim == "pencere" \
            else "yalnız %s %s sonrası" % (n, bs)
    if yon == "iki":
        return ("%s %s öncesinden %s %s sonrasına" % (n, bs, n, bs)) if bicim == "pencere" \
            else "yalnız %s %s öncesi ve %s %s sonrası" % (n, bs, n, bs)
    if yon == "takvim":
        if bicim == "pencere" and bs in _TAKVIM:
            kap, ek = _TAKVIM[bs]
            return "bugünden bağımsız; %s 1. ile %s. %s arası" % (kap, n, ek)
        return "bugünden bağımsız; yalnız %s" % takvim_anlami(birim, sayi)
    return ""


def tur_kapsami(tur, birim, ozel=None, sayi=None):
    """kapsam_metni turun yon ve biciminden."""
    yon, bicim = tur_bilgisi(tur, ozel)
    return kapsam_metni(yon, bicim, birim, sayi)


def varsayilan_yazilis(kalip, tur):
    """Turun varsayilan yeni ad yazilisi: onek kalibin onune (<N>D ->
    L<N>D, <N>_D -> L<N>_D, D_<N> -> LD_<N>). Onek bitisince yazilis yine
    sayi + birim kalibi olursa (D<N> -> LD<N>, sonraki calismada yine
    belirsiz) alt cizgiyle ayrilir: L_D<N>. süre ve ozel tur bos (kalip
    aynen)."""
    h = TUR_HARF.get(tur) or ""
    if not h:
        return ""
    y = h + str(kalip)
    return (h + "_" + str(kalip)) if birimli_mi(y) else y


def yazilis_birimli_hatasi(kalip, yazilis):
    """Turun yazilisi da sayi + birim kalibiysa (ör. LD<N>) yeni adda tur
    yine okunamaz: hata metni. Bos ya da kalibin kendisi (aynen) serbest."""
    y = re.sub(r"\s+", "", str(yazilis or "")).upper()
    if not y or y == str(kalip).upper() or not birimli_mi(y):
        return ""
    return ("Bu yazılış da sayı ve zaman biriminden oluşuyor; sonraki çalışmada türü yine "
            "belirsiz olur. Harfi alt çizgiyle ayırın (ör. L_%s)." % kalip)


def birim_sozcugu(birim):
    """Birim anlamindaki ilk birim sozcugu ("<N> gün" -> "gün", "yılın <N>.
    ayı" -> "ay")."""
    for w in _SOZCUK.findall(_kucuk(re.sub(r"<[^<>]*>", " ", birim_anlami(birim)))):
        if not w.isdigit() and w not in _YON_SOZCUKLERI and w != "ve":
            return w
    return ""


def _sayi_mi(sozcuk, sayi):
    if sozcuk.isdigit():
        return int(sozcuk) == sayi
    return _SAYI_SOZCUK.get(sozcuk) == sayi


def metinden_tur(metin, sayi, birim):
    """Tanimda sayinin ve birimin gectigi ifadeden tur (kod; tahmin yok):
      son      "son 3 gün", "geçmiş 3 gün", "geçen 3 gün", "önceki 3 gün",
               "3 gün öncesine kadar"
      once     "3 gün önce", "3 gün önceki", "3 gün öncesi"
      sonraki  "sonraki 3 gün", "önümüzdeki 3 gün", "gelecek 3 gün",
               "3 gün sonrasına kadar"
      sonra    "3 gün sonra", "3 gün sonraki", "3 gün sonrası"
      cevre    "3 gün öncesi ve sonrası", "3 gün önce ve sonra", "±3 gün"
      takvim   "yılın 3. ayı", "ayın 3. günü", "3. ay", "3'üncü ay",
               "üçüncü ay" (sayi sira olarak: takvimdeki yer)
      sure     "vade süresi 3 gün" (sayidan once süre sozcugu)
    Yonsuz ifade ("3 gün boyunca", "3 günlük", "3 gün içinde") belirsizdir.
    Ayni sayi bir yerde yonlu, bir yerde yonsuz geciyorsa yonlu olan
    gecerli; iki farkli tur ya da hic tur yoksa None (belirsiz)."""
    try:
        sayi = int(sayi)
    except (TypeError, ValueError):
        return None
    bs = birim_sozcugu(birim)
    if not bs:
        return None
    ham = _kucuk(metin)
    bulunan = set()
    for m in re.finditer(r"(±|\+/-|\+-)\s*([0-9]+)\s*([a-zçğıöşü]+)", ham):
        if int(m.group(2)) == sayi and m.group(3).startswith(bs):
            bulunan.add("cevre")
    # TAKVIM: sira sayisi + birim. Bulunan yer metinden cikarilir ki
    # cevresindeki sozcukler ("geçen yılın 3. ayı") yon sanilmasin.
    takvim_re = re.compile(
        r"(?<![0-9])([0-9]+)\s*(?:\.|'?\s*(?:inci|ıncı|uncu|üncü|nci|ncı|ncu|ncü)\b)\s*(%s[a-zçğıöşü]*)"
        % re.escape(bs))
    for m in takvim_re.finditer(ham):
        if int(m.group(1)) == sayi:
            bulunan.add("takvim")
    ham = takvim_re.sub(" ", ham)
    for sz, n_ in _SIRA_SOZCUK.items():
        if n_ == sayi and re.search(r"\b%s\s+%s" % (sz, re.escape(bs)), ham):
            bulunan.add("takvim")
    w = _SOZCUK.findall(ham)
    for i, x in enumerate(w):
        if not _sayi_mi(x, sayi) or i + 1 >= len(w) or not w[i + 1].startswith(bs):
            continue
        once_ = w[max(0, i - 2):i]
        sonra_ = w[i + 2:i + 6]
        s0 = sonra_[0] if sonra_ else ""
        s1 = sonra_[1] if len(sonra_) > 1 else ""
        if s0.startswith("önce") and any(y.startswith("sonra") for y in sonra_[1:3]):
            bulunan.add("cevre")
        elif s0.startswith("önce"):
            bulunan.add("son" if s1 == "kadar" else "once")
        elif s0.startswith("sonra"):
            bulunan.add("sonraki" if s1 == "kadar" else "sonra")
        elif any(y in _GECMIS_PENCERE for y in once_):
            bulunan.add("son")
        elif any(y in _GELECEK_PENCERE for y in once_):
            bulunan.add("sonraki")
        elif once_ and once_[-1].startswith("süre"):
            bulunan.add("sure")
        else:
            bulunan.add(BELIRSIZ)
    yonlu = bulunan - {BELIRSIZ}
    return next(iter(yonlu)) if len(yonlu) == 1 else None


def anlamdaki_tur(anlam):
    """Anlamdaki yon ifadesinden tur (eski hafiza kaydini tasimak icin)."""
    metin = re.sub(r"<N\d*>|<NN>", "7", str(anlam or ""))
    t = metinden_tur(metin, 7, anlam)
    if t:
        return t
    w = _SOZCUK.findall(_kucuk(anlam))
    if any(x in _GELECEK_PENCERE for x in w):
        return "sonraki"
    if any(x in _GECMIS_PENCERE for x in w):
        return "son"
    if any(x.startswith("önce") for x in w):
        return "once"
    if any(x.startswith("sonra") for x in w):
        return "sonra"
    return ""


def deger_sayisi(kalip, deger):
    """Degerin sayisi (30D -> 30); uymazsa None."""
    m = re.search(r"\d+", str(deger or ""))
    r = donem_mod.kalip_deseni(kalip)
    if not m or r is None or not r.match(str(deger)):
        return None
    return int(m.group(0))


def hafiza_turleri():
    """{kalip: {tur: {"ad", "anlam", "yeni_adda", "yon", "bicim"}}} hafizadan."""
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


def eski_sonra_mi(kalip, kayit):
    """Onceki surumun "sonra" kaydi mi (bicim alani yok, yazilis N<kalip>)?
    O surumde sonra hem "3 gün sonra" hem "önümüzdeki 3 gün" icin
    kullanildigindan bu yazilis hangi anlamda ogretildigi belli degildir."""
    k = kayit or {}
    return (not k.get("bicim")
            and str(k.get("yeni_adda") or "").upper() == (ESKI_SONRA_HARF + str(kalip)).upper())


def kalip_turleri(kalip, birim, ozel=None, haf=None, haf_anlam="", haf_ad=""):
    """Kalibin turleri, ekrandaki sirayla: [{"tur", "ad", "anlam", "ozel",
    "yazilis", "yon", "bicim", "kapsam"}]. yazilis hafizadan (tur kaydi;
    eski kayitta kalibin tek yazilisi, eski anlamindaki yon turune), yoksa
    varsayilan. ozel: {tur: {"ad", "anlam", "yon", "bicim"}} bu calismada
    eklenenler (hafizadakinin ustune)."""
    haf = (haf if haf is not None else hafiza_turleri()).get(kalip) or {}
    eski_tur = anlamdaki_tur(haf_anlam) if haf_ad else ""
    cikti = []
    for k, ad, _h, yon, bicim in SABIT_TURLER:
        kayit = haf.get(k) or {}
        y = kayit.get("yeni_adda")
        if k == "sonra" and eski_sonra_mi(kalip, kayit):
            y = None
        if y is None and k == eski_tur:
            y = haf_ad
        cikti.append({"tur": k, "ad": ad, "anlam": tur_anlami(k, birim), "ozel": False,
                      "yazilis": y if y is not None else varsayilan_yazilis(kalip, k),
                      "yon": yon, "bicim": bicim, "kapsam": kapsam_metni(yon, bicim, birim)})
    tum_ozel = {t: dict(x) for t, x in haf.items() if t not in SABIT_KODLAR}
    for t, x in (ozel or {}).items():
        if t not in SABIT_KODLAR:
            tum_ozel[t] = dict(tum_ozel.get(t) or {}, **x)
    for t, x in sorted(tum_ozel.items()):
        yon, bicim = tur_bilgisi(t, tum_ozel)
        cikti.append({"tur": t, "ad": str(x.get("ad") or t), "anlam": str(x.get("anlam") or ""),
                      "ozel": True, "yazilis": str(x.get("yeni_adda") or ""),
                      "yon": yon, "bicim": bicim, "kapsam": kapsam_metni(yon, bicim, birim)})
    return cikti


def yazilis_cakismasi(kalip, yazilislar, tur=None):
    """{tur: yazilis}: ayni yazilis iki ture verildiyse hata metni (bos
    yazilis, yani kalip aynen, de tek ture verilebilir). tur verilirse
    yalniz o turun yazilisi baska bir turle cakisiyorsa."""
    gor = {}
    for t, y in yazilislar.items():
        anahtar = re.sub(r"\s+", "", str(y or "")).upper() or str(kalip)
        if anahtar in gor and (tur is None or tur == t):
            return ("%s ve %s türleri aynı yazılışı alamaz (%s); yeni adda iki anlam "
                    "ayırt edilemez." % (gor[anahtar], t, anahtar))
        gor.setdefault(anahtar, t)
    return ""
