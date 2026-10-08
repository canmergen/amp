# -*- coding: utf-8 -*-
"""fe_agent/aciklama_duzen.py - ACIKLAMA DUZENLEME (01.2.6).

NE YAPAR
  Her kolonun sozluk aciklamasi ANLAMI DEGISTIRILMEDEN duzeltilir:
  kisaltmalar ve donem acilir, yarim cumle tamamlanir, Turkce duzelir.
  Anlamin kaynagi sirasiyla: kullanicinin notu > aile notu (kardes kolonda
  yazilip aileye uygulanan not) > onayli parca anlamlari (donem bilgisi,
  onayli kisaltmalar, kullanicinin parca cevaplari) > orijinal aciklama.
  Belirsizlik SORU, ad / dagilim celiskisi NOT olarak doner; dil modeli
  aciklamayi tahminle degistirmez (istem: llm.SISTEM_ACIKLAMA_DUZEN).

KOD DENETIMI (denetle)
  Kullanici notundaki sayilar, anlam kartindaki sayilar, Turkce ve yarim
  cumle kodla denetlenir; tutmayan kolon bir kez "DUZELTILECEK" notuyla
  yeniden sorulur, kalan sorun kartta "Kontrol" olarak yazar. Orijinaldeki
  sayinin ve adin donem sayisinin aciklamada olmamasi da kartta yazar.

AILE AKTARIMI (dil modeli cagrisi yok)
  Adi yalniz donem parcalarinin sayisiyla ayrilan kolonlar bir ailedir.
  Ailenin bir kolonu duzenlenince, orijinal aciklamasi o kolonunkinin
  yalniz bu sayilari degistirilmis hali olan kardes ayni duzeltmeyi
  sayilari degistirilerek alir (birebir, kodla). Sartlar tutmazsa kardes
  dil modeline gider.

KAYIT: PROJE_HAFIZASI/<calisma>/ACIKLAMA_DUZENLEME.json
  notlar          {kolon: kullanicinin notu}
  parca_notlari   {PARCA: kullanicinin parca hakkindaki cevabi}
  aile_notlari    {aile: {"kolon", "not"}}
  sonuclar        {kolon: duzenleme sonucu + girdinin imzasi}
  onay            onaylanan son hal (AMP_SOZLUK ve onerilen sozluk buradan)
  yazilan         {kolon: [onceki, son]}: calisma kopyasina yazilanlar
                  (adima ya da oncesine donulunce geri alinir)
Girdi veri setine ve sozluge hicbir kosulda yazilmaz."""

import hashlib
import json
import re
import threading
import time
from collections import OrderedDict
from concurrent import futures

from fe_agent import llm as llm_mod
from fe_agent.akis_durum import _folder

DOSYA_AD = "ACIKLAMA_DUZENLEME.json"
PARCA = 8              # dil modeline tek cagrida giden kolon
PARALEL = 4            # ayni anda calisan cagri (arka plan)
KARDES_ADET = 3        # baglama giden kardes kolon
YAZMA_ARALIGI = 5.0    # sn: kayit dosyasi en cok bu siklikla yazilir
EN_UZUN = 280          # bunun uzerindeki aciklama kartta isaretlenir

_KILIT = threading.RLock()
_DEPOLAR = {}          # klasor -> _Depo
_HAVUZ = futures.ThreadPoolExecutor(max_workers=PARALEL)
# Kullanicinin istedigi tek kolonluk yeniden kontrol arka plan dalgasini
# beklemez: ayri havuz.
_ONCELIK_HAVUZ = futures.ThreadPoolExecutor(max_workers=2)

_SAYI = re.compile(r"(?<!\d)\d+(?!\d)")
_KAYIT_ALANLARI = ("notlar", "parca_notlari", "aile_notlari", "sonuclar", "onay",
                   "yazilan")
METIN_ALANLARI = ("aciklama", "karar", "soru", "ad_notu", "dagilim_notu")


def _norm(metin):
    return re.sub(r"\s+", " ", str(metin or "")).strip()


def imza(*parcalar):
    ham = json.dumps(parcalar, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(ham.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# DEPO (calisma basina bir tane; bellekte + calisma klasorunde)
# ---------------------------------------------------------------------------
class _Depo(object):
    def __init__(self, klasor):
        self.klasor = klasor
        self.notlar = {}
        self.parca_notlari = {}
        self.aile_notlari = {}
        self.sonuclar = {}
        self.onay = {}
        self.yazilan = {}
        self.girdiler = {}          # kolon -> son girdi
        self.aileler = {}           # aile -> [kolon]
        self.son_imza = {}          # kolon -> son girdinin imzasi
        self.bekleyen = OrderedDict()
        self.ucusta = {}            # kolon -> islenen girdinin imzasi
        self.sira = {}              # kolon -> son degisikligin sirasi (yoklama farki)
        self.sayac = 0
        self.calisiyor = False
        self.iptal = False
        self.hata = ""
        self.basla = 0.0
        self.biten_is = 0
        self.son_yazma = 0.0

    def dokun(self, kolon):
        self.sayac += 1
        self.sira[kolon] = self.sayac


def _yol(klasor):
    return "/%s/%s" % (str(klasor).strip("/"), DOSYA_AD)


def depo(klasor):
    with _KILIT:
        d = _DEPOLAR.get(klasor)
        if d is None:
            d = _Depo(klasor)
            _yukle(d)
            _DEPOLAR[klasor] = d
        return d


def _yukle(d):
    try:
        with _folder().get_download_stream(_yol(d.klasor)) as akis:
            govde = json.loads(akis.read().decode("utf-8") or "{}")
    except Exception:
        return
    if not isinstance(govde, dict):
        return
    for alan in _KAYIT_ALANLARI:
        deger = govde.get(alan)
        if isinstance(deger, dict):
            setattr(d, alan, deger)


def kaydet(d, zorla=False):
    """Kayit dosyasini yazar (zorla degilse en cok YAZMA_ARALIGI'nda bir).
    Doner: hata metni ya da None."""
    with _KILIT:
        simdi = time.time()
        if not zorla and simdi - d.son_yazma < YAZMA_ARALIGI:
            return None
        d.son_yazma = simdi
        govde = json.dumps({a: getattr(d, a) for a in _KAYIT_ALANLARI},
                           ensure_ascii=False, sort_keys=True)
    try:
        _folder().upload_stream(_yol(d.klasor), govde.encode("utf-8"))
    except Exception as e:
        return "Açıklama düzenleme kaydı yazılamadı (%s)." % str(e)[:120]
    return None


# ---------------------------------------------------------------------------
# AD PARCALARI, AILE, SAYI ESLEMESI
# ---------------------------------------------------------------------------
def toklar(ad):
    from fe_agent import kisaltma_okuma
    return [kisaltma_okuma._ust(p) for p in kisaltma_okuma.parcalar(ad)]


def donem_konumlari(t, desenler=()):
    """Ad parcalarindan onayli donem kalibina uyanlarin sirasi. desenler:
    01.2.5'te onaylanan kaliplarin derlenmis desenleri; aralik kalibi
    (<P><NN>_<NN>) iki parcayi birlikte kapsar."""
    konum = set()
    for i, p in enumerate(t):
        if any(r.match(p) for r in desenler):
            konum.add(i)
        if i + 1 < len(t) and t[i + 1].isdigit() \
                and any(r.match(p + "_" + t[i + 1]) for r in desenler):
            konum.update((i, i + 1))
    return konum


def aile_anahtari(ad):
    """Sayilari "#" yapilmis ad: ayni anahtarli kolonlar yalniz sayilarla
    ayrilir. Aktarim ayrica orijinal aciklamalarin ayni sayilarla
    ayrildigini dogrular (bkz. _aktarilabilir)."""
    return "_".join(re.sub(r"\d+", "#", p) for p in toklar(ad))


def donem_sayilari(ad, desenler=()):
    """Adin onayli donem parcalarindaki sayilar (tam sayi olarak)."""
    t = toklar(ad)
    return [int(x) for i in sorted(donem_konumlari(t, desenler))
            for x in _SAYI.findall(t[i])]


def sayi_haritasi(kaynak_ad, hedef_ad):
    """Ayni ailedeki iki kolonun donem sayilari: {kaynak_sayi: hedef_sayi}.
    Esleme tek anlamli degilse None."""
    a, b = toklar(kaynak_ad), toklar(hedef_ad)
    if len(a) != len(b):
        return None
    harita = {}
    for x, y in zip(a, b):
        if x == y:
            continue
        if re.sub(r"\d+", "#", x) != re.sub(r"\d+", "#", y):
            return None
        for p, q in zip(_SAYI.findall(x), _SAYI.findall(y)):
            if harita.get(p, q) != q:
                return None
            harita[p] = q
    harita = {k: v for k, v in harita.items() if k != v}
    if len(set(harita.values())) != len(harita):
        return None
    return harita


def sayilari_degistir(metin, harita):
    """Sayilari TEK GECISTE degistirir (3->7 ve 7->14 birbirini bozmaz)."""
    if not harita or not metin:
        return metin
    return _SAYI.sub(lambda m: harita.get(m.group(0), m.group(0)), str(metin))


def _aktarilabilir(kaynak, hedef):
    """Kaynak kolonun duzeltmesi hedefe sayilari degistirilerek aktarilabilir
    mi? Doner: sayi haritasi ya da None."""
    if kaynak.get("aile") != hedef.get("aile") or _norm(hedef.get("not")):
        return None
    harita = sayi_haritasi(kaynak["kolon"], hedef["kolon"])
    if harita is None:
        return None
    if _norm(sayilari_degistir(kaynak.get("orijinal"), harita)) != _norm(hedef.get("orijinal")):
        return None
    k_aile = kaynak.get("aile_notu") or {}
    h_aile = hedef.get("aile_notu") or {}
    if _norm(kaynak.get("not")):
        # Kaynagin kendi notu: yalniz kullanici bu notu aileye uyguladiysa.
        if h_aile.get("kolon") != kaynak["kolon"] or _norm(h_aile.get("not")) != _norm(kaynak["not"]):
            return None
    elif _norm(k_aile.get("not")) != _norm(h_aile.get("not")):
        return None
    if list(map(tuple, kaynak.get("parcalar_ozet") or [])) != \
            list(map(tuple, hedef.get("parcalar_ozet") or [])):
        return None
    return harita


def aktar(kaynak, sonuc, hedef):
    """Kaynagin sonucunu hedefe aktarir; olmuyorsa None."""
    harita = _aktarilabilir(kaynak, hedef)
    if harita is None or not sonuc or not sonuc.get("aciklama") or sonuc.get("kaynak") == "hata":
        return None
    yeni = {a: sayilari_degistir(sonuc.get(a) or "", harita) for a in METIN_ALANLARI}
    yeni["parca"] = sonuc.get("parca") or ""
    yeni["kart"] = {a: sayilari_degistir(v or "", harita)
                    for a, v in (sonuc.get("kart") or {}).items()}
    yeni["model"] = sonuc.get("model") or ""
    yeni["kaynak"] = "aile"
    yeni["aile_kaynagi"] = kaynak["kolon"]
    kontrol, kalan = denetle(hedef, yeni)
    if kalan:
        return None
    yeni["kontrol"] = kontrol
    return yeni


# ---------------------------------------------------------------------------
# KOD DENETIMI
# ---------------------------------------------------------------------------
def _sayilar(metin):
    return [int(x) for x in _SAYI.findall(str(metin or ""))]


def denetle(girdi, sonuc):
    """Doner: (kontrol, yeniden). yeniden: dil modeline bir kez daha
    sorulacak sorunlar; kontrol: kartta yazacak bilgi notlari."""
    ack = sonuc.get("aciklama") or ""
    kontrol, yeniden = [], []
    if not ack:
        return kontrol, ["açıklama boş"]
    var = set(_sayilar(ack))
    notu = _norm(girdi.get("not"))
    if notu:
        eksik = [x for x in dict.fromkeys(_sayilar(notu)) if x not in var]
        if eksik:
            yeniden.append("kullanıcı notundaki sayı açıklamada yok: %s"
                           % ", ".join(map(str, eksik)))
    else:
        eksik = [x for x in dict.fromkeys(_sayilar(girdi.get("orijinal"))) if x not in var]
        if eksik:
            kontrol.append("Orijinaldeki sayı açıklamada yok: %s." % ", ".join(map(str, eksik)))
    eksik = [x for x in dict.fromkeys(girdi.get("donem_sayilari") or []) if x not in var]
    if eksik:
        kontrol.append("Adın dönem sayısı açıklamada yok: %s." % ", ".join(map(str, eksik)))
    kart = sonuc.get("kart") or {}
    eksik = [x for x in dict.fromkeys(s for v in kart.values() for s in _sayilar(v)) if x not in var]
    if eksik:
        yeniden.append("anlam kartındaki sayı açıklamada yok: %s" % ", ".join(map(str, eksik)))
    if not any(_norm(v) for v in kart.values()):
        kontrol.append("Anlam kartı boş.")
    for s in llm_mod.aciklama_sorunlari(ack):
        if s.startswith("cümle yarım") or s.startswith("tahmin"):
            yeniden.append(s)
        elif not s.startswith("uzun"):
            kontrol.append(s[:1].upper() + s[1:] + ".")
    if len(ack) > EN_UZUN:
        kontrol.append("Uzun (%d karakter)." % len(ack))
    tr = llm_mod.turkce_sorunu(ack)
    if tr:
        yeniden.append(tr)
    return kontrol, yeniden


def _kontrol_metni(sorun):
    s = str(sorun or "").strip()
    return (s[:1].upper() + s[1:]).rstrip(".") + "."


# ---------------------------------------------------------------------------
# DIL MODELI
# ---------------------------------------------------------------------------
def _llm_girdisi(g, duzeltilecek=None):
    x = {k: g.get(k) for k in ("kolon", "orijinal", "not", "aile_notu", "parcalar",
                               "kardesler", "dagilim", "rol")}
    if duzeltilecek:
        x["duzeltilecek"] = list(duzeltilecek)
    return x


def _bicimle(g, ham):
    r = dict(ham)
    ack = llm_mod.aciklama_temizle(r.get("aciklama") or "")
    if ack:
        ack = llm_mod.tarza_uydur(ack, {"nokta": True, "buyuk_bas": True})
    r["aciklama"] = ack
    if not r.get("karar"):
        if _norm(g.get("not")):
            r["karar"] = "Notunuz işlendi."
        elif _norm(ack) == _norm(g.get("orijinal")):
            r["karar"] = "Aynen alındı."
        else:
            r["karar"] = "Netleştirildi."
    parca = str(r.get("parca") or "").strip().upper()
    gecerli = set(toklar(g["kolon"]))
    r["parca"] = parca if parca in gecerli else ""
    if not r.get("soru"):
        r["parca"] = ""
    r["kaynak"] = "model"
    return r


def _isle(girdiler, ork):
    """Bir grup kolonu dil modeline duzenletir; kod denetiminden gecmeyenler
    bir kez daha sorulur. Doner: ({kolon: sonuc}, hata)."""
    try:
        ham, hata = llm_mod.aciklama_duzenle([_llm_girdisi(g) for g in girdiler], ork)
    except Exception as e:
        ham, hata = {}, "%s: %s" % (type(e).__name__, str(e)[:200])
    sonuc, yeniden = {}, []
    for g in girdiler:
        r = ham.get(g["kolon"])
        if not r:
            if not hata:
                yeniden.append((g, None, ["dil modeli bu kolon için cevap vermedi"]))
            continue
        r = _bicimle(g, r)
        kontrol, yen = denetle(g, r)
        r["kontrol"] = kontrol
        sonuc[g["kolon"]] = r
        if yen:
            yeniden.append((g, r, yen))
    if yeniden and not hata:
        try:
            ham2, _h2 = llm_mod.aciklama_duzenle(
                [_llm_girdisi(g, yen) for g, _r, yen in yeniden], ork)
        except Exception:
            ham2 = {}
        for g, r1, yen1 in yeniden:
            r2 = ham2.get(g["kolon"])
            if r2:
                r2 = _bicimle(g, r2)
                k2, yen2 = denetle(g, r2)
                if r1 is None or len(yen2) <= len(yen1):
                    r2["kontrol"] = k2 + [_kontrol_metni(x) for x in yen2]
                    sonuc[g["kolon"]] = r2
                    continue
            if r1 is not None:
                r1["kontrol"] = r1["kontrol"] + [_kontrol_metni(x) for x in yen1]
    return sonuc, hata


def _hata_sonucu(hata):
    return {"aciklama": "", "karar": "", "kart": {}, "soru": "", "parca": "",
            "ad_notu": "", "dagilim_notu": "", "kontrol": [], "model": "",
            "kaynak": "hata",
            "hata": hata or "Dil modeli bu kolon için açıklama döndürmedi."}


def _sakla(d, girdiler, sonuc, hata):
    with _KILIT:
        for g in girdiler:
            kolon = g["kolon"]
            d.ucusta.pop(kolon, None)
            r = sonuc.get(kolon) or _hata_sonucu(hata)
            r["imza"] = g["imza"]
            # Bu arada girdisi degisen kolonun eski sonucu yazilmaz.
            if d.son_imza.get(kolon) == g["imza"]:
                d.sonuclar[kolon] = r
                d.biten_is += 1
                if d.bekleyen.get(kolon, {}).get("imza") == g["imza"]:
                    d.bekleyen.pop(kolon, None)
            d.dokun(kolon)
        if hata:
            d.hata = hata


# ---------------------------------------------------------------------------
# IS
# ---------------------------------------------------------------------------
def _kaynak_bul(d, g):
    """Ailede, bu kolona aktarilabilecek guncel bir sonuc."""
    adaylar = []
    for k2 in d.aileler.get(g.get("aile"), ()):
        if k2 == g["kolon"]:
            continue
        r = d.sonuclar.get(k2)
        g2 = d.girdiler.get(k2)
        if not r or not g2 or r.get("imza") != d.son_imza.get(k2):
            continue
        adaylar.append((r.get("kaynak") != "model", k2, g2, r))
    for _o, _k2, g2, r in sorted(adaylar, key=lambda x: (x[0], x[1])):
        yeni = aktar(g2, r, g)
        if yeni:
            return yeni
    return None


def _dalga_sec(d):
    """Kilit altinda. Once aile aktarimi; sonra dil modeline gidecekler.
    Aktarilmayi bekleyen kardes, ailesinden bu dalgada giden kolonla
    hizaliysa bekletilir. Doner: (giden girdiler, aktarilan sayisi)."""
    aktarilan = 0
    for kolon, g in list(d.bekleyen.items()):
        if kolon in d.ucusta or len(d.aileler.get(g.get("aile"), ())) < 2:
            continue
        yeni = _kaynak_bul(d, g)
        if yeni:
            yeni["imza"] = g["imza"]
            d.sonuclar[kolon] = yeni
            d.bekleyen.pop(kolon, None)
            d.biten_is += 1
            d.dokun(kolon)
            aktarilan += 1
    secilen, aile_giden = [], {}
    for kolon, g in d.bekleyen.items():
        if len(secilen) >= PARCA * PARALEL:
            break
        if kolon in d.ucusta:
            continue
        giden = aile_giden.get(g.get("aile")) or []
        if any(_aktarilabilir(x, g) is not None for x in giden):
            continue
        secilen.append(g)
        aile_giden.setdefault(g.get("aile"), []).append(g)
    return secilen, aktarilan


def _calis(d):
    ork = llm_mod.Orkestra(arka=True)
    try:
        while True:
            with _KILIT:
                if d.iptal or not d.bekleyen:
                    break
                dalga, aktarilan = _dalga_sec(d)
                for g in dalga:
                    d.bekleyen.pop(g["kolon"], None)
                    d.ucusta[g["kolon"]] = g["imza"]
                    d.dokun(g["kolon"])
                if not dalga and not aktarilan:
                    # Hepsi baska yolda (oncelikli is) isleniyor.
                    bekle = True
                else:
                    bekle = False
            if bekle:
                time.sleep(1.0)
                continue
            if dalga:
                gruplar = [dalga[i:i + PARCA] for i in range(0, len(dalga), PARCA)]
                isler = {_HAVUZ.submit(_isle, grup, ork): grup for grup in gruplar}
                for f in futures.as_completed(isler):
                    grup = isler[f]
                    try:
                        sonuc, hata = f.result()
                    except Exception as e:
                        sonuc, hata = {}, "%s: %s" % (type(e).__name__, str(e)[:200])
                    _sakla(d, grup, sonuc, hata)
            kaydet(d)
    except Exception as e:
        with _KILIT:
            d.hata = "%s: %s" % (type(e).__name__, str(e)[:200])
    finally:
        with _KILIT:
            d.calisiyor = False
        kaydet(d, zorla=True)


def _tek_isle(d, g):
    """Kullanicinin istedigi yeniden kontrol (tek kolon, beklemeden). Bu
    sirada not yeniden degistiyse yeni girdi de hemen islenir."""
    try:
        sonuc, hata = _isle([g], llm_mod.Orkestra())
    except Exception as e:
        sonuc, hata = {}, "%s: %s" % (type(e).__name__, str(e)[:200])
    _sakla(d, [g], sonuc, hata)
    tekrar = None
    with _KILIT:
        g2 = d.bekleyen.get(g["kolon"])
        if g2 is not None and g["kolon"] not in d.ucusta:
            d.bekleyen.pop(g["kolon"], None)
            d.ucusta[g["kolon"]] = g2["imza"]
            d.dokun(g["kolon"])
            tekrar = g2
    if tekrar is not None:
        _ONCELIK_HAVUZ.submit(_tek_isle, d, tekrar)
        return
    kaydet(d, zorla=True)


def girdileri_ver(klasor, girdiler, oncelikli=(), devam=True, hatalari_yenile=False):
    """Kolonlarin guncel girdileri. Sonucu guncel olmayanlar (girdisi
    degismis ya da hic islenmemis) kuyruga girer; oncelikli kolonlar
    beklemeden ayri islenir. devam=True: durdurulmus is yeniden baslar.
    Doner: kuyruga giren kolon sayisi."""
    d = depo(klasor)
    giren = 0
    with _KILIT:
        d.girdiler = {g["kolon"]: g for g in girdiler}
        aileler = {}
        for g in girdiler:
            aileler.setdefault(g.get("aile"), []).append(g["kolon"])
        d.aileler = aileler
        for g in girdiler:
            kolon = g["kolon"]
            d.son_imza[kolon] = g["imza"]
            r = d.sonuclar.get(kolon)
            guncel = bool(r) and r.get("imza") == g["imza"] \
                and not (hatalari_yenile and r.get("kaynak") == "hata")
            if guncel or d.ucusta.get(kolon) == g["imza"]:
                # Guncel ya da ayni girdiyle zaten isleniyor.
                d.bekleyen.pop(kolon, None)
                continue
            if d.bekleyen.get(kolon, {}).get("imza") != g["imza"]:
                d.bekleyen[kolon] = g
                d.dokun(kolon)
                giren += 1
        if devam:
            d.iptal = False
            d.hata = ""
        tek = []
        for kolon in oncelikli:
            g = d.bekleyen.get(kolon)
            if g is not None and kolon not in d.ucusta:
                d.bekleyen.pop(kolon)
                d.ucusta[kolon] = g["imza"]
                d.dokun(kolon)
                tek.append(g)
        if d.bekleyen and not d.calisiyor and not d.iptal:
            d.calisiyor = True
            d.basla = time.time()
            d.biten_is = 0
            threading.Thread(target=_calis, args=(d,), daemon=True).start()
    for g in tek:
        _ONCELIK_HAVUZ.submit(_tek_isle, d, g)
    return giren


def iptal(klasor):
    d = depo(klasor)
    with _KILIT:
        d.iptal = True


def is_durumu(klasor):
    d = depo(klasor)
    with _KILIT:
        calisiyor = d.calisiyor or bool(d.ucusta)
        return {"calisiyor": calisiyor, "bekleyen": len(d.bekleyen),
                "ucusta": len(d.ucusta), "iptal": d.iptal, "hata": d.hata,
                "biten": d.biten_is,
                "toplam": d.biten_is + len(d.bekleyen) + len(d.ucusta),
                "gecen": int(time.time() - d.basla) if calisiyor and d.basla else 0}


def satir_durumu(d, kolon):
    """"isleniyor" / "bekliyor" / "hazir" / "hata" / "yok" (kilit altinda)."""
    if kolon in d.ucusta:
        return "isleniyor"
    if kolon in d.bekleyen:
        return "bekliyor"
    r = d.sonuclar.get(kolon)
    if r and r.get("imza") == d.son_imza.get(kolon):
        return "hata" if r.get("kaynak") == "hata" else "hazir"
    return "yok"


def guncel_sonuc(d, kolon):
    """Kolonun guncel girdisine ait sonuc; yoksa None (kilit altinda)."""
    r = d.sonuclar.get(kolon)
    if r and r.get("imza") == d.son_imza.get(kolon) and r.get("kaynak") != "hata":
        return r
    return None


# ---------------------------------------------------------------------------
# KULLANICI GIRDILERI
# ---------------------------------------------------------------------------
def not_yaz(klasor, kolon, metin):
    d = depo(klasor)
    metin = _norm(metin)
    with _KILIT:
        if metin:
            d.notlar[str(kolon)] = metin
        else:
            d.notlar.pop(str(kolon), None)
        d.dokun(str(kolon))
    return kaydet(d, zorla=True)


def parca_notu_yaz(klasor, parca, cevap):
    d = depo(klasor)
    parca = str(parca or "").strip().upper()
    cevap = _norm(cevap)
    with _KILIT:
        if cevap:
            d.parca_notlari[parca] = cevap
        else:
            d.parca_notlari.pop(parca, None)
    return kaydet(d, zorla=True)


def aile_notu_yaz(klasor, aile, kolon, metin):
    d = depo(klasor)
    metin = _norm(metin)
    with _KILIT:
        if metin:
            d.aile_notlari[str(aile)] = {"kolon": str(kolon), "not": metin}
        else:
            d.aile_notlari.pop(str(aile), None)
    return kaydet(d, zorla=True)
