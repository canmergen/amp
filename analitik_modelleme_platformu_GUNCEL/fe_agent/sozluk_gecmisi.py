# -*- coding: utf-8 -*-
"""fe_agent/sozluk_gecmisi.py - Baz veri seti ile kullanilan sozluklerin gecmisi.

NE ICIN - 01.2.1'de baz veri seti secilince, o veri setiyle onceki
calismalarda kullanilan sozluk(ler) Baz Sozluk alanina oneri olarak gelir.

NEREDE - PROJE_HAFIZASI/VERI_SOZLUK_GECMISI.json, projenin butun
calismalari icin tek dosya:

    {"veri": {"HAVALE_EFT_NTT": {"DEGISKENLER": {"calismalar": {
         "v3": "2026-10-12T14:02:00", "v7": "2026-10-21T09:10:00"}}}},
     "surum": 2}

SAYIM KESIN: her calisma yalniz SON onayladigi (veri seti, sozluk)
ciftinde sayilir. Calisma 01.2.1'e donup baska bir sozluk ya da veri seti
secerse eski ciftten cikar; calisma silinince her yerden cikar (numara
yeniden verildiginde yeni calisma eskisinin sayimini devralmaz).

NE ZAMAN YAZILIR - 01.2.1 onaylanip veri seti ve sozluk dogrulandiginda
(akis_faz01.kurulum_girdi) ve calisma silindiginde (backend calisma_sil).
Dosya hic yoksa ilk okumada eski calismalarin ozet.json dosyalarindan bir
kez kurulur.

Yalniz adlar yazilir; girdi veri setine ve sozluge dokunulmaz. Okuma ya da
yazma hatasi akisi durdurmaz: oneri bir kolaylik."""

import datetime
import json
import re
import threading
from concurrent import futures

from fe_agent.akis_durum import _folder

DOSYA = "/VERI_SOZLUK_GECMISI.json"
SURUM = 2
_KILIT = threading.Lock()
_V_OZET = re.compile(r"^/?(v\d{1,6})/ozet\.json$")


def _oku_ham():
    """(icerik, klasor yollari). Dosya once dogrudan okunur; klasor yalniz
    okuma basarisizsa listelenir: dosya yoksa (None, yollar), var ama
    okunamiyorsa hata atar."""
    f = _folder()
    try:
        with f.get_download_stream(DOSYA) as s:
            return json.loads(s.read().decode("utf-8")), None
    except Exception:
        yollar = {"/" + str(y).lstrip("/") for y in f.list_paths_in_partition()}
        if DOSYA in yollar:
            raise
        return None, yollar


def _yaz(veri):
    _folder().upload_stream(
        DOSYA, json.dumps(veri, ensure_ascii=False, indent=1).encode("utf-8"))


def _calismalar(kayit):
    """Ciftin {calisma: zaman} sozlugu. Surum 1'de liste + tek "son" vardi."""
    c = kayit.get("calismalar")
    if isinstance(c, list):
        c = {k: kayit.get("son") or "" for k in c}
        kayit["calismalar"] = c
        kayit.pop("son", None)
    return c if isinstance(c, dict) else kayit.setdefault("calismalar", {})


def _cikar(veri, calisma):
    """Calismayi butun ciftlerden cikarir; bos kalan cift ve veri seti silinir."""
    tum = veri.setdefault("veri", {})
    for vs in list(tum):
        for sz in list(tum[vs] or {}):
            _calismalar(tum[vs][sz]).pop(calisma, None)
            if not tum[vs][sz]["calismalar"]:
                del tum[vs][sz]
        if not tum[vs]:
            del tum[vs]


def _ekle(veri, veri_seti, sozluk, calisma, zaman):
    kayit = veri.setdefault("veri", {}).setdefault(str(veri_seti), {}) \
        .setdefault(str(sozluk), {"calismalar": {}})
    _calismalar(kayit)[calisma or "?"] = zaman or ""


def _gecmisten_kur(yollar):
    """Eski calismalarin ozet.json dosyalarindan (veri seti, sozluk) ciftleri.
    Ozetteki "Sözlük" secimi kullanicinin sectigi sozluktur (calisma kopyasi
    degil)."""
    f = _folder()
    ozetler = sorted(y for y in yollar if _V_OZET.match(y))

    def oku(yol):
        try:
            with f.get_download_stream(yol) as s:
                return json.loads(s.read().decode("utf-8"))
        except Exception:
            return None

    with futures.ThreadPoolExecutor(max_workers=8) as havuz:
        okunan = list(havuz.map(oku, ozetler))
    veri = {"surum": SURUM, "veri": {}}
    for oz in okunan:
        if not isinstance(oz, dict) or not oz.get("veri_seti"):
            continue
        sozluk = next((d for e, d in (oz.get("secimler") or [])
                       if e == "Sözlük" and d), None)
        if sozluk:
            _ekle(veri, oz["veri_seti"], sozluk, oz.get("calisma_id") or "",
                  str(oz.get("zaman") or ""))
    return veri


def harita():
    """{veri seti: [{"sozluk", "sayi", "son"}]}. Siralama: en cok calismada
    kullanilan once, esitlikte en son kullanilan. Okunamazsa bos."""
    try:
        with _KILIT:
            veri, yollar = _oku_ham()
            if veri is None:
                veri = _gecmisten_kur(yollar)
                _yaz(veri)
    except Exception:
        return {}
    cikti = {}
    for vs, sozlukler in (veri.get("veri") or {}).items():
        liste = []
        for sz, k in (sozlukler or {}).items():
            c = _calismalar(k)
            if c:
                liste.append({"sozluk": sz, "sayi": len(c),
                              "son": max(c.values()) or ""})
        liste.sort(key=lambda x: (x["sayi"], x["son"]), reverse=True)
        cikti[vs] = liste
    return cikti


def kaydet(veri_seti, sozluk, calisma):
    """Calismanin onayladigi (veri seti, sozluk) ciftini yazar; calismanin
    onceki cifti silinir. Sozluksuz onayda calisma yalniz cikarilir. Dosya
    okunamiyorsa ustune yazilmaz (gecmis kaybolmasin)."""
    if not veri_seti:
        return
    zaman = datetime.datetime.now().isoformat(timespec="seconds")
    try:
        with _KILIT:
            veri, yollar = _oku_ham()
            if veri is None:
                veri = _gecmisten_kur(yollar)
            if calisma:
                _cikar(veri, calisma)
            if sozluk:
                _ekle(veri, veri_seti, sozluk, calisma, zaman)
            veri["surum"] = SURUM
            _yaz(veri)
    except Exception:
        pass


def calisma_cikar(calisma):
    """Silinen calismayi gecmisten cikarir. Dosya yoksa bir sey yapmaz
    (kurulurken silinen calismanin ozeti zaten yok)."""
    if not calisma:
        return
    try:
        with _KILIT:
            veri, _yollar = _oku_ham()
            if veri is None:
                return
            _cikar(veri, calisma)
            veri["surum"] = SURUM
            _yaz(veri)
    except Exception:
        pass


def arka_planda_kaydet(veri_seti, sozluk, calisma):
    """kaydet'i istegi bekletmeden calistirir."""
    threading.Thread(target=kaydet, args=(veri_seti, sozluk, calisma),
                     daemon=True).start()
