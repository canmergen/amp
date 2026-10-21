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
        "sozluk_zaman": "2026-10-21T09:10:00",
        "roller": {"problem": "classification", "target": "TARGET",
                   "id": "MUSTERI_NO", "donem": "PERIOD", "segment": ""},
        "roller_zaman": "2026-10-21T09:12:00"}},
     "surum": 4}

NE ZAMAN YAZILIR - 01.2.1 onaylanip veri seti ve sozlukler
dogrulandiginda (akis_faz01.kurulum_girdi) ve 01.2.2 onaylandiginda
(akis_faz01.tanimlar_girdi); ayni tablonun onceki secimi yenisiyle
degisir. Sozluksuz onay sozluk eslesmesini degistirmez. Dosya hic yoksa
ilk okumada eski calismalarin ozet.json dosyalarindan bir kez kurulur
(her tablo icin en son secimler; segment ozette olmadigi icin bos).

Yalniz adlar yazilir; girdi veri setine ve sozluge dokunulmaz. Okuma ya da
yazma hatasi akisi durdurmaz: on doldurma bir kolaylik."""

import datetime
import json
import re
import threading
from concurrent import futures

from fe_agent.akis_durum import _folder
from fe_agent.akis_metin import MODEL_TIPI_ADI

DOSYA = "/VERI_SETI_GECMISI.json"
# Ayni bilginin ilk surumu (yalniz sozluk eslesmesi); yeni dosya yoksa
# bir kez okunup aktarilir.
ESKI_DOSYA = "/VERI_SOZLUK_GECMISI.json"
SURUM = 4
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


def _simdi():
    return datetime.datetime.now().isoformat(timespec="seconds")


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
    veri = _gecmisten_kur(yollar)
    if ESKI_DOSYA in yollar:
        try:
            _eskiyi_aktar(veri, _json_oku(ESKI_DOSYA))
        except Exception:
            pass
    return veri, True


def _eskiyi_aktar(veri, eski):
    """Ilk surumdeki sozluk eslesmeleri (yeni olanin uzerine, daha
    yeniyse). Eski bicimler: {vs: {"sozlukler", "zaman"}} ve
    {vs: {sozluk: {"calismalar", "son"}}}."""
    for vs, k in ((eski or {}).get("veri") or {}).items():
        if not isinstance(k, dict):
            continue
        if "sozlukler" in k:
            adlar, zaman = list(k.get("sozlukler") or []), k.get("zaman") or ""
        else:
            adlar, zaman = [], ""
            for sz, d in k.items():
                c = (d or {}).get("calismalar")
                z = (max(c.values()) if isinstance(c, dict) and c
                     else (d or {}).get("son") or "")
                if not adlar or z > zaman:
                    adlar, zaman = [sz], z
        kayit = veri["veri"].setdefault(vs, {})
        if adlar and zaman >= (kayit.get("sozluk_zaman") or ""):
            kayit["sozlukler"], kayit["sozluk_zaman"] = adlar, zaman


def _yaz(veri):
    veri["surum"] = SURUM
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
    veri = {"surum": SURUM, "veri": {}}
    for oz in okunan:
        if not isinstance(oz, dict) or not oz.get("veri_seti"):
            continue
        sec = {e: d for e, d in (oz.get("secimler") or []) if d}
        zaman = str(oz.get("zaman") or "")
        kayit = veri["veri"].setdefault(oz["veri_seti"], {})
        if sec.get("Sözlük") and zaman > (kayit.get("sozluk_zaman") or ""):
            kayit["sozlukler"] = adlara_ayir(sec["Sözlük"])
            kayit["sozluk_zaman"] = zaman
        roller = {r: sec[e] for e, r in _OZET_ROL.items() if sec.get(e)}
        if roller.get("target") and zaman > (kayit.get("roller_zaman") or ""):
            roller["problem"] = _TIP_KODU.get(sec.get("Model Tipi"),
                                              "classification")
            kayit["roller"] = {r: roller.get(r, "") for r in ROLLER}
            kayit["roller_zaman"] = zaman
    veri["veri"] = {vs: k for vs, k in veri["veri"].items() if k}
    return veri


def _oku():
    """Dosya (yoksa kurulup yazilir). Okunamazsa None."""
    try:
        with _KILIT:
            veri, yeni = _oku_ham()
            if yeni:
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
                     {"sozlukler": sozlukler, "sozluk_zaman": _simdi()})


def roller_kaydet(veri_seti, problem, meta):
    """Tablonun kolon rolleri (oncekinin yerine). Arka planda."""
    meta = meta or {}
    if veri_seti and meta.get("target"):
        r = {"problem": problem or ""}
        r.update({k: str(meta.get(k) or "") for k in ROLLER if k != "problem"})
        _arka_planda(_guncelle, veri_seti, {"roller": r, "roller_zaman": _simdi()})
