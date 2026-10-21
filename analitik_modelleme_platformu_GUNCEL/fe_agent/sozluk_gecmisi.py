# -*- coding: utf-8 -*-
"""fe_agent/sozluk_gecmisi.py - Baz veri seti ile kullanilan sozluklerin gecmisi.

NE ICIN - 01.2.1'de baz veri seti secilince, o veri setiyle onceki
calismalarda kullanilan sozluk(ler) Baz Sozluk alanina oneri olarak gelir.

NEREDE - PROJE_HAFIZASI/VERI_SOZLUK_GECMISI.json, projenin butun
calismalari icin tek dosya:

    {"veri": {"HAVALE_EFT_NTT": {"DEGISKENLER": {"calismalar": ["v3", "v7"],
                                                  "son": "2026-10-21T09:10:00"}}},
     "surum": 1}

NE ZAMAN YAZILIR - 01.2.1 onaylanip veri seti ve sozluk dogrulandiginda
(akis_faz01.kurulum_girdi). Dosya hic yoksa ilk okumada eski calismalarin
ozet.json dosyalarindan bir kez kurulur.

Yalniz adlar yazilir; girdi veri setine ve sozluge dokunulmaz. Okuma ya da
yazma hatasi akisi durdurmaz: oneri bir kolaylik."""

import datetime
import json
import re
import threading
from concurrent import futures

from fe_agent.akis_durum import _folder

DOSYA = "/VERI_SOZLUK_GECMISI.json"
SURUM = 1
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


def _ekle(veri, veri_seti, sozluk, calisma, zaman):
    kayit = veri.setdefault("veri", {}).setdefault(str(veri_seti), {}) \
        .setdefault(str(sozluk), {"calismalar": [], "son": ""})
    if calisma and calisma not in kayit["calismalar"]:
        kayit["calismalar"].append(calisma)
    if zaman and zaman > (kayit.get("son") or ""):
        kayit["son"] = zaman


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
        liste = [{"sozluk": sz, "sayi": len(k.get("calismalar") or []) or 1,
                  "son": k.get("son") or ""}
                 for sz, k in (sozlukler or {}).items()]
        liste.sort(key=lambda x: (x["sayi"], x["son"]), reverse=True)
        cikti[vs] = liste
    return cikti


def kaydet(veri_seti, sozluk, calisma):
    """Onaylanan (veri seti, sozluk) ciftini yazar. Dosya okunamiyorsa
    ustune yazilmaz (gecmis kaybolmasin)."""
    if not (veri_seti and sozluk):
        return
    zaman = datetime.datetime.now().isoformat(timespec="seconds")
    try:
        with _KILIT:
            veri, yollar = _oku_ham()
            if veri is None:
                veri = _gecmisten_kur(yollar)
            _ekle(veri, veri_seti, sozluk, calisma or "", zaman)
            _yaz(veri)
    except Exception:
        pass


def arka_planda_kaydet(veri_seti, sozluk, calisma):
    """kaydet'i istegi bekletmeden calistirir."""
    threading.Thread(target=kaydet, args=(veri_seti, sozluk, calisma),
                     daemon=True).start()
