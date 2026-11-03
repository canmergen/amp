# -*- coding: utf-8 -*-
"""fe_agent/kontrol_gecmisi.py - Sozluk ve Kolon Adi Kontrolu'nun (01.2.4)
proje hafizasindaki kaydi.

NE ICIN - Ayni veri seti ayni sozluk(ler)le yeniden secildiginde 01.2.4'te
"Onceki Onayli Kontrol Uygulansin" secilebilir: onaylanmis alt adimlar
yeniden sorulmadan uygulanir; Kolon Kartlari'nda onaylanan aciklamalar
yeniden onaylanmis gelir. Calisma arsivden silinse de kayit kalir.

NEREDE - PROJE_HAFIZASI/KONTROL_GECMISI.json, TEK DOSYA. Anahtar okunur:
veri seti ve sozlukler ("HAVALE_EFT_NTT | DEGISKENLER + EK_SOZLUK";
sozluksuz: "HAVALE_EFT_NTT | sözlüksüz"). Yalniz onayli kararlar durur
(onaylanmamis taslak tutulmaz):

    {"HAVALE_EFT_NTT | DEGISKENLER": {
        "zaman": "2026-11-03T10:44:00",
        "donem":    {"karar": {...}},
        "parca":    {"karar": {...}},
        "aciklama": {"tamam": true, "karar": {}, "onayli": 340, "toplam": 512,
                     "notlar": {kolon: not}, "parca_notlari": {...},
                     "aile_notlari": {...}, "elle": {kolon: true},
                     "onaylanan": {kolon: {"aciklama": "...", "imza": "...",
                                           "karar", "ek", "ad_eksik"}}},
        "kolon_ad": {"karar": {...}, "adlar": {aile: [[eski, yeni]]}}}}

Kolon Kartlari'nda yalniz onaylanan kolonlarin son aciklamasi (ve onu
gecerli kilan girdi imzasi) yazilir; dil modelinin ara sonuclari
yazilmaz. Imzasi tutan kolon yeni calismada dil modeline gitmeden
onaylanmis gelir; tutmayan (girdisi degismis) yeniden yazilir.

Kodun geri kalani kaydi eski (ic) bicimde gorur: {"veri_seti",
"sozlukler", "zaman", "adimlar": {adim: {...}}}; aciklama adiminda
"depo": {DEPO_ALANLARI}. Dosyaya yazarken ve okurken cevrilir (_diske,
_icten). ESKI KLASOR (PROJE_HAFIZASI/KONTROL_GECMISI/<sha>.json) varsa ve
tek dosya yoksa kayitlar bir kez tek dosyaya tasinir; klasor silinmez.

Girdi veri setine ve sozluge dokunulmaz. Okuma ya da yazma hatasi akisi
durdurmaz: kayit bir kolaylik; uygulanan her karar adimin kendi
denetiminden gecer."""

import datetime
import json
import re
import threading
import time

from fe_agent.akis_durum import _folder

DOSYA = "/KONTROL_GECMISI.json"
ESKI_DIZIN = "/KONTROL_GECMISI"
ADIMLAR = ("donem", "parca", "aciklama", "kolon_ad")
DEPO_ALANLARI = ("notlar", "parca_notlari", "aile_notlari", "sonuclar", "kabul", "elle")
# Onaylanan kolonun saklanan alanlari (aciklama ve imza her zaman).
ONAY_ALANLARI = ("karar", "ek", "ad_eksik")
SOZLUKSUZ = "sözlüksüz"
# Ardisik yazmalar (satir onayi) bu sure icinde tek yazmada birlesir.
BIRLESTIR_SN = 1.0

_KILIT = threading.RLock()     # _yukle tasima yazmasini kilit icinde baslatir
_YAZ_KILIT = threading.Lock()
_DOSYA = {"yuklendi": False, "kayitlar": {}}   # anahtar -> ic kayit
_BEKLIYOR = [False]
# ERTELENEN ALANLAR: buyuk alan (Kolon Kartlari deposu) her tiklamada
# kopyalanmaz; yazmadan (ya da okumadan) hemen once bir kez uretilir.
_URET = {}              # anahtar -> {adim: uret()}


def _simdi():
    return datetime.datetime.now().isoformat(timespec="seconds")


def anahtar(veri_seti, sozlukler):
    """Veri seti ve sozlukler -> okunur anahtar; veri seti yoksa None."""
    if not veri_seti:
        return None
    s = sorted(str(x) for x in (sozlukler or []) if x)
    return "%s | %s" % (veri_seti, " + ".join(s) if s else SOZLUKSUZ)


# ---------------------------------------------------------------------------
# DOSYA BICIMI <-> IC BICIM
# ---------------------------------------------------------------------------
def _norm(metin):
    return re.sub(r"\s+", " ", str(metin or "")).strip()


def _aciklama_diske(ac):
    """Ic aciklama adimi -> dosyadaki hali (yalniz onaylananlar)."""
    depo = ac.get("depo") if isinstance(ac.get("depo"), dict) else {}
    cikti = {k: ac[k] for k in ("tamam", "karar", "onayli", "toplam") if k in ac}
    for alan in ("notlar", "parca_notlari", "aile_notlari", "elle"):
        if depo.get(alan):
            cikti[alan] = dict(sorted(depo[alan].items()))
    sonuclar = depo.get("sonuclar") or {}
    onaylanan = {}
    for kolon, metin in sorted((depo.get("kabul") or {}).items()):
        r = sonuclar.get(kolon) or {}
        if not r.get("aciklama") or _norm(r.get("aciklama")) != _norm(metin):
            continue
        kayit = {"aciklama": r["aciklama"], "imza": r.get("imza") or ""}
        kayit.update({a: r[a] for a in ONAY_ALANLARI if r.get(a)})
        onaylanan[kolon] = kayit
    if onaylanan:
        cikti["onaylanan"] = onaylanan
    return cikti


def _aciklama_icten(ac):
    """Dosyadaki aciklama adimi -> ic hali (depo)."""
    depo = {alan: dict(ac.get(alan) or {}) for alan in ("notlar", "parca_notlari",
                                                        "aile_notlari", "elle")}
    depo["sonuclar"], depo["kabul"] = {}, {}
    for kolon, x in (ac.get("onaylanan") or {}).items():
        if not isinstance(x, dict) or not x.get("aciklama"):
            continue
        r = {"imza": str(x.get("imza") or ""), "aciklama": str(x["aciklama"]),
             "karar": str(x.get("karar") or ""),
             "ek": str(x.get("ek") or ""), "ad_eksik": list(x.get("ad_eksik") or []),
             "soru": "", "parca": "", "ad_notu": "", "dagilim_notu": "", "kontrol": [],
             "model": "", "kaynak": "onceki"}
        depo["sonuclar"][kolon] = r
        depo["kabul"][kolon] = _norm(x["aciklama"])
    cikti = {k: ac[k] for k in ("tamam", "karar", "onayli", "toplam") if k in ac}
    cikti["depo"] = depo
    return cikti


def _diske(ic):
    """Ic kayit -> dosyadaki kayit."""
    cikti = {"zaman": str(ic.get("zaman") or "")}
    ad = ic.get("adimlar") or {}
    for adim in ADIMLAR:
        x = ad.get(adim)
        if not isinstance(x, dict):
            continue
        if adim == "aciklama":
            y = _aciklama_diske(x)
        else:
            y = {k: x[k] for k in ("karar", "adlar") if x.get(k) is not None}
        if y:
            cikti[adim] = y
    return cikti


def _icten(a, kayit):
    """Dosyadaki kayit -> ic kayit."""
    vs, _, soz = str(a).partition(" | ")
    sozlukler = [] if soz in ("", SOZLUKSUZ) else [x.strip() for x in soz.split(" + ") if x.strip()]
    adimlar = {}
    for adim in ADIMLAR:
        x = kayit.get(adim)
        if not isinstance(x, dict):
            continue
        adimlar[adim] = _aciklama_icten(x) if adim == "aciklama" else dict(x)
    return {"veri_seti": vs, "sozlukler": sozlukler, "zaman": str(kayit.get("zaman") or ""),
            "adimlar": adimlar}


def _eski_klasorden():
    """Eski klasordeki kayitlar (anahtar -> ic kayit); yoksa {}."""
    try:
        yollar = [y for y in _folder().list_paths_in_partition()
                  if re.match(r"^/?KONTROL_GECMISI/[^/]+\.json$", str(y))]
    except Exception:
        return {}
    cikti = {}
    for y in yollar:
        try:
            with _folder().get_download_stream("/" + str(y).lstrip("/")) as s:
                k = json.loads(s.read().decode("utf-8") or "{}")
        except Exception:
            continue
        if not isinstance(k, dict) or not k.get("veri_seti"):
            continue
        a = anahtar(k["veri_seti"], k.get("sozlukler"))
        # Eski kayit dosya bicimine cevrilip geri okunur: yalniz onaylananlar kalir.
        yeni = _icten(a, _diske(k))
        yeni["zaman"] = str(k.get("zaman") or "")
        if a not in cikti or yeni["zaman"] > cikti[a]["zaman"]:
            cikti[a] = yeni
    return cikti


def _yukle():
    """Dosya bir kez okunur (kilit altinda cagrilir)."""
    if _DOSYA["yuklendi"]:
        return
    kayitlar, tasindi = {}, False
    try:
        with _folder().get_download_stream(DOSYA) as s:
            ham = json.loads(s.read().decode("utf-8") or "{}")
        if isinstance(ham, dict):
            kayitlar = {a: _icten(a, k) for a, k in ham.items() if isinstance(k, dict)}
    except Exception:
        kayitlar = _eski_klasorden()
        tasindi = bool(kayitlar)
    _DOSYA.update(yuklendi=True, kayitlar=kayitlar)
    if tasindi:
        _yaz_arka()


def _uret_uygula():
    """Bekleyen ertelenmis alanlari uretip bellekteki kayitlara yazar."""
    with _KILIT:
        bekleyen = dict(_URET)
        _URET.clear()
    for a, adimlar in bekleyen.items():
        for adim, uret in adimlar.items():
            try:
                alanlar = uret()
            except Exception:
                continue
            if not isinstance(alanlar, dict):
                continue
            kopya = json.loads(json.dumps(alanlar, ensure_ascii=False, default=str))
            with _KILIT:
                k = _DOSYA["kayitlar"].get(a)
                if k is not None:
                    k.setdefault("adimlar", {}).setdefault(adim, {}).update(kopya)


def oku(a):
    """Kayit (ic bicim; yoksa bos sozluk)."""
    if not a:
        return {}
    with _KILIT:
        _yukle()
    _uret_uygula()
    with _KILIT:
        k = _DOSYA["kayitlar"].get(a)
        return json.loads(json.dumps(k, ensure_ascii=False)) if k else {}


def _dosya_metni():
    with _KILIT:
        govde = {a: _diske(k) for a, k in sorted(_DOSYA["kayitlar"].items())}
    return json.dumps(govde, ensure_ascii=False, indent=1)


def _yaz_arka():
    with _KILIT:
        if _BEKLIYOR[0]:
            return
        _BEKLIYOR[0] = True

    def is_():
        time.sleep(BIRLESTIR_SN)
        with _YAZ_KILIT:
            _uret_uygula()
            with _KILIT:
                _BEKLIYOR[0] = False
            try:
                _folder().upload_stream(DOSYA, _dosya_metni().encode("utf-8"))
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
    with _KILIT:
        _yukle()
        if uret is not None:
            _URET.setdefault(a, {})[adim] = uret
        k = _DOSYA["kayitlar"].setdefault(a, {"veri_seti": str(veri_seti), "sozlukler": [],
                                               "zaman": "", "adimlar": {}})
        k["veri_seti"] = str(veri_seti)
        k["sozlukler"] = sorted(str(s) for s in (sozlukler or []) if s)
        k["zaman"] = _simdi()
        ad = k.setdefault("adimlar", {}).setdefault(adim, {})
        for alan in sil:
            ad.pop(alan, None)
        ad.update(json.loads(json.dumps(alanlar, ensure_ascii=False, default=str)))
    _yaz_arka()


def karar_yaz(a, veri_seti, sozlukler, adim, karar, **ek):
    """Onaylanan karar."""
    alanlar = {"karar": karar, "karar_zaman": _simdi()}
    alanlar.update(ek)
    adim_yaz(a, veri_seti, sozlukler, adim, alanlar)


def taslak_yaz(a, veri_seti, sozlukler, adim, taslak, **ek):
    """Onaylanmamis taslak tutulmaz (yalniz onayli kararlar durur)."""
    return None


def ozet(k):
    """Kaydin kisa ozeti: {"tamam": [adim], "taslak": [adim], "aciklama":
    (onayli, toplam) ya da None, "zaman"}. "taslak": yalniz yarim kalan
    Kolon Kartlari (onaylanan kolonlari var, adim onaylanmadi)."""
    ad = (k or {}).get("adimlar") or {}
    tamam = [a for a in ADIMLAR if a != "aciklama" and isinstance((ad.get(a) or {}).get("karar"), dict)]
    ac = ad.get("aciklama") or {}
    if ac.get("tamam"):
        tamam.append("aciklama")
    tamam = [a for a in ADIMLAR if a in tamam]
    taslak = ["aciklama"] if "aciklama" not in tamam and (ac.get("depo") or {}).get("kabul") else []
    return {"tamam": tamam, "taslak": taslak,
            "aciklama": (int(ac.get("onayli") or 0), int(ac.get("toplam") or 0))
            if ac.get("depo") else None,
            "zaman": str((k or {}).get("zaman") or "")}
