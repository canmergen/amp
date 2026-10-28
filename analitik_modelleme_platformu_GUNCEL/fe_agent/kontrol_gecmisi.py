# -*- coding: utf-8 -*-
"""fe_agent/kontrol_gecmisi.py - Sozluk ve Kolon Adi Kontrolu'nun (01.2.4)
proje hafizasindaki kaydi.

NE ICIN - Ayni veri seti ayni sozluk(ler)le yeniden secildiginde 01.2.4'te
"Onceki Onayli Kontrol Uygulansin" secilebilir: onaylanmis alt adimlar
yeniden sorulmadan uygulanir, yarim kalan alt adim kaldigi yerden acilir.
Calisma arsivden silinse de kayit kalir.

NEREDE - PROJE_HAFIZASI/KONTROL_GECMISI/<anahtar>.json; anahtar veri
setinin ve sozluklerin adlarindan (sira onemsiz). Calisma bilgisi
tutulmaz; ayni tablo ve sozluk icin yalniz en son durum durur:

    {"veri_seti": "HAVALE_EFT_NTT", "sozlukler": ["DEGISKENLER"],
     "zaman": "...",
     "adimlar": {
        "donem":    {"karar": {...}, "karar_zaman": "...",
                     "taslak": {...}, "taslak_zaman": "..."},
        "parca":    {"karar": {...}, "taslak": {...}},
        "aciklama": {"depo": {"notlar", "parca_notlari", "aile_notlari",
                              "sonuclar", "kabul"},
                     "tamam": true, "onayli": 340, "toplam": 512},
        "kolon_ad": {"karar": {...}, "adlar": {aile: [[eski, yeni]]},
                     "taslak": {...}, "taslak_adlar": {...}}}}

KARAR: adim onaylandiginda kartin gonderdigi govde (onayla yazilir,
taslagi siler). TASLAK: kart acikken kullanicinin son hali (onaylanmamis;
"kaldigi yerden devam" icin). Kolon Kartlari'nda depo, satir onaylari ve
dil modeli sonuclariyla birlikte yazilir.

Girdi veri setine ve sozluge dokunulmaz. Okuma ya da yazma hatasi akisi
durdurmaz: kayit bir kolaylik; uygulanan her karar adimin kendi
denetiminden gecer."""

import datetime
import hashlib
import json
import threading
import time

from fe_agent.akis_durum import _folder

DIZIN = "/KONTROL_GECMISI"
ADIMLAR = ("donem", "parca", "aciklama", "kolon_ad")
DEPO_ALANLARI = ("notlar", "parca_notlari", "aile_notlari", "sonuclar", "kabul")
# Ardisik yazmalar (taslak, satir onayi) bu sure icinde tek yazmada birlesir.
BIRLESTIR_SN = 1.0

_KILIT = threading.Lock()
_BELLEK = {}            # anahtar -> kayit (okunduktan sonra bellekteki esas)
_BEKLEYEN = set()       # yazmasi siraya girmis anahtarlar
_YAZ_KILIT = {}         # anahtar -> yazma kilidi (eski kopya yeniyi ezmesin)
# ERTELENEN ALANLAR: buyuk alan (Kolon Kartlari deposu) her tiklamada
# kopyalanmaz; yazmadan (ya da okumadan) hemen once bir kez uretilir.
_URET = {}              # anahtar -> {adim: uret()}


def _simdi():
    return datetime.datetime.now().isoformat(timespec="seconds")


def anahtar(veri_seti, sozlukler):
    """Veri seti ve sozlukler -> dosya anahtari; veri seti yoksa None."""
    if not veri_seti:
        return None
    ham = json.dumps([str(veri_seti), sorted(str(s) for s in (sozlukler or []) if s)],
                     ensure_ascii=False)
    return hashlib.sha1(ham.encode("utf-8")).hexdigest()[:20]


def _yol(a):
    return "%s/%s.json" % (DIZIN, a)


def _dosyadan(a):
    try:
        with _folder().get_download_stream(_yol(a)) as s:
            k = json.loads(s.read().decode("utf-8") or "{}")
        return k if isinstance(k, dict) else {}
    except Exception:
        return {}


def _uret_uygula(a):
    """Bekleyen ertelenmis alanlari uretip bellekteki kayda yazar."""
    with _KILIT:
        bekleyen = _URET.pop(a, {})
    for adim, uret in bekleyen.items():
        try:
            alanlar = uret()
        except Exception:
            continue
        if not isinstance(alanlar, dict):
            continue
        kopya = json.loads(json.dumps(alanlar, ensure_ascii=False, default=str))
        with _KILIT:
            _BELLEK.setdefault(a, {}).setdefault("adimlar", {}).setdefault(adim, {}).update(kopya)


def oku(a):
    """Kayit (yoksa bos sozluk). Bir kez dosyadan okunur, sonra bellekte."""
    if not a:
        return {}
    with _KILIT:
        var = a in _BELLEK
    if not var:
        k = _dosyadan(a)
        with _KILIT:
            _BELLEK.setdefault(a, k)
    _uret_uygula(a)
    with _KILIT:
        return json.loads(json.dumps(_BELLEK[a]))


def _yaz_arka(a):
    with _KILIT:
        if a in _BEKLEYEN:
            return
        _BEKLEYEN.add(a)
        kilit = _YAZ_KILIT.setdefault(a, threading.Lock())

    def is_():
        time.sleep(BIRLESTIR_SN)
        with kilit:
            _uret_uygula(a)
            with _KILIT:
                _BEKLEYEN.discard(a)
                govde = json.dumps(_BELLEK.get(a) or {}, ensure_ascii=False)
            try:
                _folder().upload_stream(_yol(a), govde.encode("utf-8"))
            except Exception:
                pass

    threading.Thread(target=is_, daemon=True).start()


def adim_yaz(a, veri_seti, sozlukler, adim, alanlar, sil=(), uret=None):
    """Alt adimin kaydina alanlari yazar, sil'dekileri kaldirir. Arka
    planda yazilir; bellekteki kopya hemen guncellenir. uret: buyuk
    alanlari doner; yazmadan hemen once cagrilir (ardisik cagrilarda
    yalniz sonuncusu)."""
    if not a or adim not in ADIMLAR:
        return
    oku(a)
    with _KILIT:
        if uret is not None:
            _URET.setdefault(a, {})[adim] = uret
        k = _BELLEK.setdefault(a, {})
        k["veri_seti"] = str(veri_seti)
        k["sozlukler"] = sorted(str(s) for s in (sozlukler or []) if s)
        k["zaman"] = _simdi()
        ad = k.setdefault("adimlar", {}).setdefault(adim, {})
        for alan in sil:
            ad.pop(alan, None)
        ad.update(json.loads(json.dumps(alanlar, ensure_ascii=False, default=str)))
    _yaz_arka(a)


def karar_yaz(a, veri_seti, sozlukler, adim, karar, **ek):
    """Onaylanan karar: taslak silinir."""
    alanlar = {"karar": karar, "karar_zaman": _simdi()}
    alanlar.update(ek)
    adim_yaz(a, veri_seti, sozlukler, adim, alanlar,
             sil=("taslak", "taslak_zaman", "taslak_adlar"))


def taslak_yaz(a, veri_seti, sozlukler, adim, taslak, **ek):
    alanlar = {"taslak": taslak, "taslak_zaman": _simdi()}
    alanlar.update(ek)
    adim_yaz(a, veri_seti, sozlukler, adim, alanlar)


def ozet(k):
    """Kaydin kisa ozeti: {"tamam": [adim], "taslak": [adim], "aciklama":
    (onayli, toplam) ya da None, "zaman"}."""
    ad = (k or {}).get("adimlar") or {}
    tamam = [a for a in ADIMLAR if a != "aciklama" and isinstance((ad.get(a) or {}).get("karar"), dict)]
    ac = ad.get("aciklama") or {}
    if ac.get("tamam"):
        tamam.append("aciklama")
    tamam = [a for a in ADIMLAR if a in tamam]
    taslak = [a for a in ADIMLAR if a not in tamam and (
        isinstance((ad.get(a) or {}).get("taslak"), dict)
        or (a == "aciklama" and (ac.get("depo") or {}).get("kabul")))]
    return {"tamam": tamam, "taslak": taslak,
            "aciklama": (int(ac.get("onayli") or 0), int(ac.get("toplam") or 0))
            if ac.get("depo") else None,
            "zaman": str((k or {}).get("zaman") or "")}
