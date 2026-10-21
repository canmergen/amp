# -*- coding: utf-8 -*-
"""fe_agent/veri_gecmisi.py - Baz veri setinin en son secimleri.

NE ICIN - Ayni tablo yeniden secildiginde onceki secimler hazir gelir;
kullanici degistirebilir:
  * 01.2.1 Baz Sozluk: tablonun en son eslendigi sozluk(ler) secili gelir.
  * 01.2.2 Kolon Rolleri: model tipi, hedef, kimlik, donem ve segment
    kolonu en son onaylanan haliyle dolu gelir.

NEREDE - PROJE_HAFIZASI/VERI_SETI_GECMISI.json, projenin butun
calismalari icin tek dosya. Yalniz tablo basina en son secim durur;
calisma bilgisi tutulmaz:

    {"veri": {"HAVALE_EFT_NTT": {
        "sozlukler": ["DEGISKENLER", "EK_SOZLUK"],
        "roller": {"problem": "classification", "target": "TARGET",
                   "id": "MUSTERI_NO", "donem": "PERIOD", "segment": ""}}}}

NE ZAMAN YAZILIR - 01.2.1 onaylanip veri seti ve sozlukler
dogrulandiginda (akis_faz01.kurulum_girdi) ve 01.2.2 onaylandiginda
(akis_faz01.tanimlar_girdi); ayni tablonun onceki secimi yenisiyle
degisir. Sozluksuz onay sozluk eslesmesini degistirmez. Dosya hic yoksa
ilk okumada eski calismalarin ozet.json dosyalarindan bir kez kurulur
(her tablo icin en son secimler; segment ozette olmadigi icin bos).

Yalniz adlar yazilir; girdi veri setine ve sozluge dokunulmaz. Okuma ya da
yazma hatasi akisi durdurmaz: on doldurma bir kolaylik."""

import json
import re
import threading
from concurrent import futures

from fe_agent.akis_durum import _folder
from fe_agent.akis_metin import MODEL_TIPI_ADI

DOSYA = "/VERI_SETI_GECMISI.json"
ROLLER = ("problem", "target", "id", "donem", "segment")
# Ozet ve form mesajinda birden fazla sozluk bu ayracla yazilir.
AYRAC = " + "
_KILIT = threading.Lock()
_V_OZET = re.compile(r"^/?(v\d{1,6})/ozet\.json$")
# Arsiv ozetindeki etiketler (backend._calisma_secimleri).
_OZET_ROL = {"Hedef Değişken": "target", "Kimlik Kolonu": "id",
             "Dönem Kolonu": "donem"}
_TIP_KODU = {ad: kod for kod, ad in MODEL_TIPI_ADI.items()}


def adlara_ayir(metin):
    """"A + B" -> ["A", "B"]."""
    return [x.strip() for x in str(metin or "").split("+") if x.strip()]


def _fazlasi_var(veri):
    """Dosyada sozlukler ve roller disinda alan var mi?"""
    return set(veri) - {"veri"} or any(
        set(k or {}) - {"sozlukler", "roller"}
        for k in (veri.get("veri") or {}).values())


def _json_oku(yol):
    with _folder().get_download_stream(yol) as s:
        return json.loads(s.read().decode("utf-8"))


def _oku_ham():
    """(icerik, yeni_mi). Dosya once dogrudan okunur; klasor yalniz okuma
    basarisizsa listelenir. Dosya yoksa eski calismalardan kurulur
    (yeni_mi=True); var ama okunamiyorsa hata atar."""
    try:
        return _json_oku(DOSYA), False
    except Exception:
        yollar = {"/" + str(y).lstrip("/")
                  for y in _folder().list_paths_in_partition()}
        if DOSYA in yollar:
            raise
    return _gecmisten_kur(yollar), True


def _yaz(veri):
    """Yalniz tablo basina sozlukler ve roller yazilir; baska alan
    dusurulur."""
    veri = {"veri": {vs: {k: v for k, v in (kayit or {}).items()
                          if k in ("sozlukler", "roller") and v}
                     for vs, kayit in (veri.get("veri") or {}).items()}}
    _folder().upload_stream(
        DOSYA, json.dumps(veri, ensure_ascii=False, indent=1).encode("utf-8"))


def _gecmisten_kur(yollar):
    """Eski calismalarin ozet.json dosyalarindan: her tablo icin en son
    secimler. Ozetteki "Sözlük" kullanicinin sectigi sozluk(ler)dir
    (calisma kopyasi degil)."""
    ozetler = sorted(y for y in yollar if _V_OZET.match(y))

    def oku(yol):
        try:
            return _json_oku(yol)
        except Exception:
            return None

    with futures.ThreadPoolExecutor(max_workers=8) as havuz:
        okunan = list(havuz.map(oku, ozetler))
    # Eskiden yeniye: ayni tablonun sonraki calismasi oncekinin yerine gecer.
    okunan = sorted((oz for oz in okunan
                     if isinstance(oz, dict) and oz.get("veri_seti")),
                    key=lambda oz: str(oz.get("zaman") or ""))
    veri = {"veri": {}}
    for oz in okunan:
        sec = {e: d for e, d in (oz.get("secimler") or []) if d}
        kayit = veri["veri"].setdefault(oz["veri_seti"], {})
        if sec.get("Sözlük"):
            kayit["sozlukler"] = adlara_ayir(sec["Sözlük"])
        roller = {r: sec[e] for e, r in _OZET_ROL.items() if sec.get(e)}
        if roller.get("target"):
            roller["problem"] = _TIP_KODU.get(sec.get("Model Tipi"),
                                              "classification")
            kayit["roller"] = {r: roller.get(r, "") for r in ROLLER}
    veri["veri"] = {vs: k for vs, k in veri["veri"].items() if k}
    return veri


def _oku():
    """Dosya (yoksa kurulup yazilir). Okunamazsa None."""
    try:
        with _KILIT:
            veri, yeni = _oku_ham()
            # Yeni kurulduysa ya da fazla alan tasiyorsa sade haliyle yazilir.
            if yeni or _fazlasi_var(veri):
                _yaz(veri)
            return veri
    except Exception:
        return None


def sozluk_haritasi():
    """{veri seti: [sozluk, ...]} (en son eslesme, secim sirasiyla)."""
    veri = _oku() or {}
    return {vs: list(k.get("sozlukler") or [])
            for vs, k in (veri.get("veri") or {}).items() if k.get("sozlukler")}


def roller(veri_seti):
    """Tablonun en son onaylanan kolon rolleri: {problem, target, id, donem,
    segment}; yoksa bos sozluk."""
    veri = _oku() or {}
    k = ((veri.get("veri") or {}).get(str(veri_seti or "")) or {}).get("roller")
    return dict(k) if isinstance(k, dict) else {}


def _guncelle(veri_seti, alanlar):
    """Tablonun kaydina alanlari yazar. Dosya okunamiyorsa ustune yazilmaz
    (gecmis kaybolmasin)."""
    try:
        with _KILIT:
            veri, _yeni = _oku_ham()
            veri.setdefault("veri", {}).setdefault(str(veri_seti), {}).update(alanlar)
            _yaz(veri)
    except Exception:
        pass


def _arka_planda(hedef, *args):
    threading.Thread(target=hedef, args=args, daemon=True).start()


def sozluk_kaydet(veri_seti, sozlukler):
    """Tablonun sozluk eslesmesi (oncekinin yerine). Sozluk yoksa yazilmaz.
    Istegi bekletmemek icin arka planda."""
    sozlukler = [str(s) for s in (sozlukler or []) if s]
    if veri_seti and sozlukler:
        _arka_planda(_guncelle, veri_seti,
                     {"sozlukler": sozlukler})


def roller_kaydet(veri_seti, problem, meta):
    """Tablonun kolon rolleri (oncekinin yerine). Arka planda."""
    meta = meta or {}
    if veri_seti and meta.get("target"):
        r = {"problem": problem or ""}
        r.update({k: str(meta.get(k) or "") for k in ROLLER if k != "problem"})
        _arka_planda(_guncelle, veri_seti, {"roller": r})
