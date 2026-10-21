# -*- coding: utf-8 -*-
"""fe_agent/sozluk_gecmisi.py - Baz veri seti ile eslesen sozlukler.

NE ICIN - 01.2.1'de baz veri seti secilince, o veri setinin en son
eslendigi sozluk(ler) Baz Sozluk alanina secili gelir; kullanici
degistirebilir.

NEREDE - PROJE_HAFIZASI/VERI_SOZLUK_GECMISI.json, projenin butun
calismalari icin tek dosya. Yalniz hangi tablonun hangi sozluk(ler)le
eslendigi durur; calisma bilgisi tutulmaz:

    {"veri": {"HAVALE_EFT_NTT": {"sozlukler": ["DEGISKENLER", "EK_SOZLUK"],
                                 "zaman": "2026-10-21T09:10:00"}},
     "surum": 3}

NE ZAMAN YAZILIR - 01.2.1 onaylanip veri seti ve sozlukler
dogrulandiginda (akis_faz01.kurulum_girdi); ayni veri seti icin onceki
eslesmenin yerine gecer. Sozluksuz onay eslesmeyi degistirmez. Dosya hic
yoksa ilk okumada eski calismalarin ozet.json dosyalarindan bir kez
kurulur (her veri seti icin en son eslesme).

Yalniz adlar yazilir; girdi veri setine ve sozluge dokunulmaz. Okuma ya da
yazma hatasi akisi durdurmaz: oneri bir kolaylik."""

import datetime
import json
import re
import threading
from concurrent import futures

from fe_agent.akis_durum import _folder

DOSYA = "/VERI_SOZLUK_GECMISI.json"
SURUM = 3
# Ozet ve form mesajinda birden fazla sozluk bu ayracla yazilir.
AYRAC = " + "
_KILIT = threading.Lock()
_V_OZET = re.compile(r"^/?(v\d{1,6})/ozet\.json$")


def adlara_ayir(metin):
    """"A + B" -> ["A", "B"]."""
    return [x.strip() for x in str(metin or "").split("+") if x.strip()]


def _oku_ham():
    """(icerik, klasor yollari). Dosya once dogrudan okunur; klasor yalniz
    okuma basarisizsa listelenir: dosya yoksa (None, yollar), var ama
    okunamiyorsa hata atar."""
    f = _folder()
    try:
        with f.get_download_stream(DOSYA) as s:
            return _surume_getir(json.loads(s.read().decode("utf-8"))), None
    except Exception:
        yollar = {"/" + str(y).lstrip("/") for y in f.list_paths_in_partition()}
        if DOSYA in yollar:
            raise
        return None, yollar


def _surume_getir(veri):
    """Eski bicim ({veri seti: {sozluk: {calismalar, son}}}): her veri seti
    icin en son kullanilan sozluk kalir."""
    if not isinstance(veri, dict) or veri.get("surum") == SURUM:
        return veri
    yeni = {}
    for vs, sozlukler in (veri.get("veri") or {}).items():
        en_son, zaman = None, ""
        for sz, k in (sozlukler or {}).items():
            c = k.get("calismalar")
            z = max(c.values()) if isinstance(c, dict) and c else (k.get("son") or "")
            if en_son is None or z > zaman:
                en_son, zaman = sz, z
        if en_son:
            yeni[vs] = {"sozlukler": [en_son], "zaman": zaman}
    return {"surum": SURUM, "veri": yeni}


def _yaz(veri):
    _folder().upload_stream(
        DOSYA, json.dumps(veri, ensure_ascii=False, indent=1).encode("utf-8"))


def _gecmisten_kur(yollar):
    """Eski calismalarin ozet.json dosyalarindan: her veri seti icin en son
    eslesme. Ozetteki "Sözlük" secimi kullanicinin sectigi sozluk(ler)dir
    (calisma kopyasi degil)."""
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
        zaman = str(oz.get("zaman") or "")
        onceki = veri["veri"].get(oz["veri_seti"])
        if sozluk and (onceki is None or zaman > onceki["zaman"]):
            veri["veri"][oz["veri_seti"]] = {"sozlukler": adlara_ayir(sozluk),
                                             "zaman": zaman}
    return veri


def harita():
    """{veri seti: [sozluk, ...]} (en son eslesme, secim sirasiyla).
    Okunamazsa bos."""
    try:
        with _KILIT:
            veri, yollar = _oku_ham()
            if veri is None:
                veri = _gecmisten_kur(yollar)
                _yaz(veri)
    except Exception:
        return {}
    return {vs: list(k.get("sozlukler") or [])
            for vs, k in (veri.get("veri") or {}).items() if k.get("sozlukler")}


def kaydet(veri_seti, sozlukler):
    """Veri setinin eslesmesini yazar (oncekinin yerine). Sozluk yoksa bir
    sey yapmaz. Dosya okunamiyorsa ustune yazilmaz (gecmis kaybolmasin)."""
    sozlukler = [str(s) for s in (sozlukler or []) if s]
    if not (veri_seti and sozlukler):
        return
    try:
        with _KILIT:
            veri, yollar = _oku_ham()
            if veri is None:
                veri = _gecmisten_kur(yollar)
            veri.setdefault("veri", {})[str(veri_seti)] = {
                "sozlukler": sozlukler,
                "zaman": datetime.datetime.now().isoformat(timespec="seconds")}
            veri["surum"] = SURUM
            _yaz(veri)
    except Exception:
        pass


def arka_planda_kaydet(veri_seti, sozlukler):
    """kaydet'i istegi bekletmeden calistirir."""
    threading.Thread(target=kaydet, args=(veri_seti, list(sozlukler or [])),
                     daemon=True).start()
