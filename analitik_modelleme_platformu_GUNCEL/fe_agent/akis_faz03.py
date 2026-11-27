# -*- coding: utf-8 -*-
"""fe_agent/akis_faz03.py - Faz 02 - Degisken Muhendisligi: kural tabanli uretim ve AI kesfi.

KAYNAK: Faz 01'in modelleme tablosu (AMP veri seti); Veri Profili'nin
kusurlu buldugu kolonlar (bos, sabit, kimlik benzeri, asiri kardinalite)
uretime girmez. Sonuc _ENRICHED (ham + uretilen); Faz 03 (SFA, stabilite,
baz set) bu tabloyla calisir. Uretim degisince SFA kararlari gecersizdir.
"""

import json
import time

import dataiku
import numpy as np
import pandas as pd
from fe_agent import llm as llm_mod
from fe_agent import ifade as ifade_mod
from fe_agent import akis_atif

from fe_agent.akis_durum import (
    sozluk_oku,
    _dataset_var_mi, _df_oku, _folder, _liste, _sayi, maskeler,
    modelleme_df, modelleme_kaynagi,
)

try:                                     # _df_oku onbellegi (akis_durum)
    from fe_agent.akis_durum import onbellek_temizle
except ImportError:                      # onbellek yoksa: sessiz gecis
    def onbellek_temizle(ad=None):
        return None


# Plan metinleri her gosterimde yeniden uretilir; sozluk tablosu icin
# tam okuma yerine sinirli okuma yeterli (LLM zaten ilk N satiri kullaniyor).
SOZLUK_LIMITI = 1000
SEMA_LIMITI = 100

# Adim anahtarlari — kod_bloklari girdilerindeki 3. alan (kaynak).
KURAL_KAYNAK = "kural"
KESIF_KAYNAK = "kesif"

# Kural tabanli donusumlerin train'den ogrenilen parametreleri
WINSOR_ALT, WINSOR_UST = 0.01, 0.99
RANK_IZGARA = 100        # train yuzdelik izgarasi: 101 nokta


def _meta_yasak(durum):
    """Hedef / kimlik / donem: uretilen kolonlarda da kaynak kolonlarda da
    kullanilmaz. llm.py zaten eliyor; bu ikinci savunma katmani."""
    m = durum.get("meta") or {}
    return {x for x in (m.get("target"), m.get("id"), m.get("donem")) if x}


def _kusurlu(durum):
    from fe_agent.akis_faz02 import kusurlu_kolonlar
    return set(kusurlu_kolonlar(durum))


def _sfa_gecersiz(durum):
    """Uretim degisti: SFA (ve kararlari) eski degisken kumesine aitti;
    Faz 03'e gelince yeniden hesaplanir."""
    eski = (durum.pop("sfa", None) or {}).get("ai_is")
    if eski:
        from fe_agent import sfa_karar
        sfa_karar.ai_durdur(eski)


def _kaynak_ad(durum):
    """Uretim kodunun okudugu tablo: modelleme kaynagi (AMP veri seti)."""
    try:
        ad, _amp = modelleme_kaynagi(durum)
    except Exception:
        ad = None
    return ad or durum["veri_seti"]


def _blok_kaynak(blok):
    return blok[2] if isinstance(blok, (list, tuple)) and len(blok) > 2 else None


def _adim_temizle(durum, *kaynaklar):
    """Adim yeniden calistirildiginda o adima ait kayitlari ONCE siler.

    Boylece "geri dön → yeniden onayla" akisinda durum["uretilen"] ile
    veri setinde gercekten duran kolonlar birbirinden ayrilmaz.
    Doner: silinen kolon adlari kumesi.
    """
    kaynaklar = set(kaynaklar)
    bloklar = durum.get("kod_bloklari") or []
    silinen = set()
    for blok in bloklar:
        if _blok_kaynak(blok) not in kaynaklar:
            continue
        for satir in (blok[1] or []):
            if isinstance(satir, (list, tuple)) and satir and satir[0]:
                silinen.add(satir[0])

    durum["kod_bloklari"] = [b for b in bloklar
                             if _blok_kaynak(b) not in kaynaklar]
    durum["uretilen"] = [a for a in (durum.get("uretilen") or [])
                         if a not in silinen]
    harita = durum.get("uretilen_kaynak")
    if isinstance(harita, dict):
        for k in list(harita):
            harita[k] = [a for a in (harita.get(k) or []) if a not in silinen]
    return silinen


def _kaynaga_yaz(durum, kaynak, adlar):
    """Uretilen degiskeni KIM uretti: kural tabanli mi, AI kesfi mi?

    durum["uretilen"] duz bir ad listesi; ust serit kural / AI dagilimini
    ve finalde kalanlari bu ayrimdan okur."""
    harita = durum.get("uretilen_kaynak")
    if not isinstance(harita, dict):
        harita = {}
    mevcut = set(harita.get(kaynak) or [])
    # Adim yeniden calistirilabilir: _adim_temizle o kaynagin eski
    # adlarini zaten dusurdu, burada yalnizca guncel liste birikir.
    harita[kaynak] = sorted(mevcut | set(adlar))
    durum["uretilen_kaynak"] = harita


def _secimi_uygula(ogeler, secim):
    """secim: 0 tabanli indis listesi ya da None/bos -> hepsi."""
    if not secim:
        return list(ogeler)
    istenen = {int(i) for i in secim}
    return [o for i, o in enumerate(ogeler) if i in istenen]


def _uretim_kodu_yaz(durum, hedef):
    """Biriken TUM bloklarla uretim_kodu.py dosyasini yeniden yazar.

    Hem kural hem kesif adiminin sonunda cagrilir; boylece hangi adim
    calisirsa calissin dosya guncel olur ve kural adiminda uretilen
    bloklar da dosyaya girer.
    Doner: (yazildi_mi, hata_metni)
    """
    bloklar = durum.get("kod_bloklari") or []
    if not bloklar:
        return False, None
    try:
        script = ifade_mod.script_olustur(
            kaynak_dataset=_kaynak_ad(durum),
            hedef_dataset=hedef, doldurma=None,
            # script_olustur 2'li blok bekliyor; kaynak alani atilir.
            bloklar=_profil_blogu(durum) + [(b[0], b[1]) for b in bloklar])
        _folder().upload_stream("/uretim_kodu.py", script.encode("utf-8"))
        return True, None
    except Exception as e:
        return False, str(e)[:120]


def _profil_blogu(durum):
    """URETIM KODUNDA 02.1: 02.2 ve 02.3 kolonlari 02.1'in duzelttigi ve
    cozum kolonu ekledigi tablodan uretildigi icin uretim kodu ayni
    duzeltme ve cozumleri basta uygular (ogrenilen bilgiyle; ayni
    fonksiyon: kolon_cozum.profil_uygula). Tek deyim: kod satiri kurali."""
    p = durum.get("profil") or {}
    spec = {"duzeltme": p.get("duzeltme_bilgi") or {}, "cozum": p.get("cozum_bilgi") or {}}
    if not spec["duzeltme"] and not spec["cozum"]:
        return []
    satir = ('df = __import__("fe_agent.kolon_cozum", fromlist=["profil_uygula"])'
             '.profil_uygula(df, %r)' % (json.loads(json.dumps(spec)),))
    return [("02.1 Veri Profili: düzeltmeler ve çözüm kolonları", [("PROFIL_021", satir)])]


def _uretim_kaynagi(durum):
    """02.2'nin okudugu tablo (02.1 sonu) ve yeni duzen mi."""
    from fe_agent import akis_faz02 as _f2
    from fe_agent.akis_faz02 import cozum_kolonlari_ekle
    yeni_duzen = _f2.updt_modu(durum)
    df = _f2.asama_df(durum, "02.1") if yeni_duzen \
        else cozum_kolonlari_ekle(durum, modelleme_df(durum))
    return df, yeni_duzen


# 02.2 KOLON BAZINDA OLCUM: her donusumun urettigi her kolonun IV'si, artisi,
# kaynakla iliskisi ve dogrusal uyumu. Durum dosyasini sisirmemek icin
# calismanin klasorunde ayri JSON ({birim id: {kod: [[ad, iv, artis, iliski,
# uyum], ...]}}); ekran /geleneksel_kolonlar ucundan ister.
KOLON_DOSYA = "geleneksel_kolonlar.json"
_KOLON_BELLEK = {}                       # yol -> veri (dosya yazilamasa da ayni surecte gecerli)


def _kolon_yolu(durum):
    try:
        from fe_agent.akis_faz01 import amp_klasor_adi
        return "/%s/%s" % (amp_klasor_adi(durum), KOLON_DOSYA)
    except Exception:
        return "/%s" % KOLON_DOSYA


def kolonlari_oku(durum):
    """{birim id: {kod: satirlar}}; yoksa {}."""
    yol = _kolon_yolu(durum)
    if yol in _KOLON_BELLEK:
        return _KOLON_BELLEK[yol]
    try:
        from fe_agent import sfa_karar
        veri = sfa_karar.detay_oku(yol)
    except Exception:
        veri = {}
    return veri if isinstance(veri, dict) else {}


def _kolonlari_yaz(durum, yeni, birimler):
    """Yeni olculen birimlerin kolon satirlarini dosyaya isler; artik
    olmayan birimler duser. Yazilamazsa ayni surecte bellekten okunur."""
    yol = _kolon_yolu(durum)
    var = {b["id"] for b in birimler}
    veri = {i: v for i, v in dict(kolonlari_oku(durum)).items() if i in var}
    veri.update({i: v for i, v in (yeni or {}).items() if i in var})
    _KOLON_BELLEK[yol] = veri
    while len(_KOLON_BELLEK) > 6:
        _KOLON_BELLEK.pop(next(iter(_KOLON_BELLEK)))
    try:
        from fe_agent import sfa_karar
        sfa_karar.detay_yaz(yol, veri)
    except Exception:
        pass
    return veri


def _kolonlari_ayir(katki):
    """Olcum sonucundan kolon satirlarini ayirir (durumda yalniz ozet kalir).
    Doner: {birim id: {kod: satirlar}}."""
    cikti = {}
    for bid, kb in (katki or {}).items():
        for c, olc in ((kb or {}).get("kodlar") or {}).items():
            if isinstance(olc, dict) and "kolonlar" in olc:
                cikti.setdefault(bid, {})[c] = olc.pop("kolonlar")
    return cikti


def geleneksel_kolonlar(durum, istek=None):
    """Ekranin istedigi kolon olcumleri. istek: {birim id: [kod, ...]}; bos
    ise onerilen ve secili butun (birim, kod) ciftleri. Doner: {birim id:
    {kod: [[ad, iv, artis, iliski, uyum, degerli(0 ya da 1)], ...]}}."""
    from fe_agent import geleneksel as G
    g = durum.get("geleneksel") or {}
    veri = kolonlari_oku(durum)
    if not isinstance(istek, dict) or not istek:
        istek = {}
        for b in g.get("birimler") or []:
            kodlar = set(((g.get("oneri") or {}).get(b["id"]) or {}).get("sec") or []) \
                | set(((g.get("karar") or {}).get(b["id"]) or {}).get("sec") or [])
            if kodlar:
                istek[b["id"]] = sorted(kodlar)
    cikti = {}
    for bid, kodlar in istek.items():
        kb = veri.get(str(bid)) or {}
        for c in kodlar if isinstance(kodlar, (list, tuple)) else []:
            satirlar = kb.get(str(c))
            if satirlar:
                cikti.setdefault(str(bid), {})[str(c)] = [list(r)[:5] + [1 if G.kolon_degerli(r) else 0]
                                                         for r in satirlar]
    return cikti


def geleneksel_ornek(durum, birim_id, kod, param=None, adet=8):
    """02.2 «Örnek Satırlar»: bir birimde bir donusumun KODUN URETTIGI
    degerleri, kaynak kolonlarin degerleriyle yan yana, Train'den birkac
    satirda. Kullanici hesabi gozle dogrulasin diye. Donusum uretimde
    kullanilan ayni fonksiyonla (geleneksel.uygula) tablonun tamaminda
    hesaplanir, ogrenilen her sey yalniz Train satirlarindan ogrenilir;
    satirlar uretilen ilk kolonun en kucugunden en buyugune yayilacak
    sekilde secilir (bos uretilen bir satir varsa o da). Hicbir sey
    kaydedilmez. Doner: {"kimlik", "kaynak": [kolon], "uretilen": [kolon],
    "satirlar": [[deger, ...]], "aciklama": {kolon: metin}, "kod_satiri":
    {kolon: metin}, "toplam_uretilen", "train_satir"} ya da {"hata"}."""
    from fe_agent import geleneksel as G
    g = durum.get("geleneksel") or {}
    b = next((x for x in g.get("birimler") or [] if x.get("id") == birim_id), None)
    if b is None or kod not in (b.get("mumkun") or []) or kod not in G.KATALOG_HARITA:
        return {"hata": "Bu birimde bu dönüşüm uygulanamıyor."}
    df, _yd = _uretim_kaynagi(durum)
    tr, _te = maskeler(durum, df)
    tr = pd.Series(tr, index=df.index).fillna(False).astype(bool)
    m = durum.get("meta") or {}
    k = (g.get("karar") or {}).get(birim_id) or {}
    p = param if isinstance(param, dict) and param else \
        (k.get("param") or {}).get(kod) or (((g.get("oneri") or {}).get(birim_id) or {}).get("param") or {}).get(kod) or {}
    yeni, kayit, hatalar = G.uygula(df, [b], {birim_id: {"sec": [kod], "param": {kod: p} if p else {}, "haric": {}}},
                                    tr, m.get("target"))
    if not yeni:
        return {"hata": (hatalar[0] if hatalar else
                         "Bu dönüşüm bu birimde kolon üretmedi. Değer isteyen dönüşümde (eşik, aralık, segment) "
                         "önce değeri girin.")}
    uretilen = list(yeni)[:4]
    kay = {r["ad"]: r for r in kayit}
    kaynak = []
    for u in uretilen:
        for c in (kay.get(u) or {}).get("kaynaklar") or []:
            if c in df.columns and c not in kaynak:
                kaynak.append(c)
    kaynak = kaynak[:6]
    s = yeni[uretilen[0]][tr]
    dolu = s.dropna().sort_values(kind="mergesort")
    sira = []
    if len(dolu):
        for q in (0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0):
            i = dolu.index[int(round(q * (len(dolu) - 1)))]
            if i not in sira:
                sira.append(i)
    for i in s[s.isna()].index[:1]:
        sira.append(i)
    sira = sira[:max(1, int(adet))]

    def yaz(v):
        if v is None or (isinstance(v, float) and v != v) or v is pd.NaT:
            return None
        try:
            if pd.isna(v):
                return None
        except (TypeError, ValueError):
            pass
        if isinstance(v, (int, np.integer)) and not isinstance(v, bool):
            return int(v)
        if isinstance(v, (float, np.floating)):
            return float("%.6g" % float(v))
        return str(v)
    kimlik = m.get("id") if m.get("id") in df.columns else None
    satirlar = [([yaz(df.at[i, kimlik])] if kimlik else [])
                + [yaz(df.at[i, c]) for c in kaynak] + [yaz(yeni[u].at[i]) for u in uretilen] for i in sira]
    return {"kimlik": kimlik, "kaynak": kaynak, "uretilen": uretilen, "satirlar": satirlar,
            "aciklama": {u: (kay.get(u) or {}).get("aciklama") or "" for u in uretilen},
            "kod_satiri": {u: (kay.get(u) or {}).get("kod_satiri") or "" for u in uretilen},
            "toplam_uretilen": len(yeni), "train_satir": int(tr.sum()), "hatalar": hatalar[:3]}


def _oneri_goster(o, k):
    """Onerinin karta giden hali. Dil modelinin asama gerekcesindeki sayilar
    kodun o birim icin olctugu sayilarla tutmuyorsa (baska birimin cumlesi,
    talimattaki ornegin kopyasi, uydurma sayi) gerekce karta GONDERILMEZ;
    "g_tutmuyor" hangi asamalarin gizlendigini soyler. Kayitli (eski)
    onerilerde de her seferinde denetlenir."""
    from fe_agent import geleneksel as G
    c = {x: v for x, v in o.items() if x != "imza"}
    kotu = G.gerekce_denetle(o, k)
    c["g_tutmuyor"] = kotu
    for a in kotu:
        c["g%d" % a] = ""
    if kotu and c.get("gerekce"):
        c["gerekce"] = ""
    return c


def _kolon_aciklamalari(durum, kolonlar):
    """{kolon: sozluk aciklamasi}: verilen kolonlardan aciklamasi olanlar.
    Adi 01'de degisen kolonda aciklama eski adla kayitli olabilir."""
    try:
        from fe_agent import akis_faz02
        a = dict(akis_faz02._aciklamalar(durum) or {})
        for e, y in (durum.get("_amp_yeniden_ad") or {}).items():
            if str(e) in a and str(y) not in a:
                a[str(y)] = a[str(e)]
    except Exception:           # pylint: disable=broad-except
        a = {}
    return {k: str(a[k]) for k in sorted(kolonlar) if a.get(k)}


def geleneksel_karti(durum, kilitli=False):
    """02.2 karti (tip geleneksel): solda birimler ve kararlar, sagda
    sohbet. Kart verisi durum["geleneksel"]'den. Dil modeli isi suruyorsa
    "bekliyor" alani dolu; kart kararlari gostermez, ilerlemeyi gosterir."""
    from fe_agent import geleneksel as G
    g = durum.get("geleneksel") or {}
    birimler = g.get("birimler") or []
    # Katalogdan cikan kodlar (olcek donusumleri) eski kayitlarda kalmis
    # olabilir: birimlerden, oneriden ve karardan ayiklanir.
    var = G.KATALOG_HARITA
    for b in birimler:
        if any(c not in var for c in b.get("mumkun") or []) or any(c not in var for c in b.get("imkansiz") or {}):
            b["mumkun"] = [c for c in b.get("mumkun") or [] if c in var]
            b["imkansiz"] = {c: n for c, n in (b.get("imkansiz") or {}).items() if c in var}

    def _ayikla(kayitlar):
        cikti = {}
        for i, o in (kayitlar or {}).items():
            if not isinstance(o, dict):
                continue
            o = dict(o)
            o["sec"] = [c for c in o.get("sec") or [] if c in var]
            o["param"] = {c: p for c, p in (o.get("param") or {}).items() if c in o["sec"]}
            o["haric"] = {c: list(a) for c, a in (o.get("haric") or {}).items() if c in o["sec"] and a}
            for alan in ("elenen", "kod_ekledi"):
                if o.get(alan):
                    o[alan] = [e for e in o[alan] if e.get("kod") in var]
            cikti[i] = o
        return cikti
    oneri = _ayikla(g.get("oneri"))
    karar = {i: {"sec": k["sec"], "param": k["param"], "haric": k["haric"]} for i, k in _ayikla(g.get("karar")).items()}
    bekliyor = None
    if g.get("oneri_is"):
        d = G.oneri_isi_durumu(g["oneri_is"].get("kimlik")) or {}
        bekliyor = {"biten": d.get("biten", 0), "toplam": d.get("toplam", g["oneri_is"].get("toplam", 0)),
                    "tur": d.get("tur", 1), "evre": d.get("evre", "birim"),
                    "olcum_biten": d.get("olcum_biten", 0), "olcum_toplam": d.get("olcum_toplam", 0),
                    "gecen": int(time.time() - float(g["oneri_is"].get("baslangic") or time.time())),
                    "arasi_sor": bool(g["oneri_is"].get("arasi_sor")),
                    # Ilk acilista kart beklenir; sonraki islerde (model turu
                    # degisimi) kart acik kalir, ustte ilerleme gorunur.
                    "ilk": bool(g["oneri_is"].get("ilk", True)),
                    "model_turu": g["oneri_is"].get("model_turu")}
    kdurum = G.katalog_durumu(birimler, oneri, g.get("katki"))
    return {
        "tip": "geleneksel", "adim": "kural", "kilitli": bool(kilitli), "bekliyor": bekliyor,
        "model_turu": "hepsi", "model_turleri": G.MODEL_TURLERI,
        "agac_gereksiz": list(G.AGAC_GEREKSIZ), "agac_nedeni": G.AGAC_NEDENI,
        "asama_adlari": {str(k): v for k, v in G.ASAMA_ADI.items()},
        "katalog": [dict({"kod": k, "ad": a, "grup": gr, "grup_adi": G.GRUP_ADI[gr], "aciklama": c,
                          "asama": G.ASAMA.get(k, 3), "yer": G.kod_yeri(k), "model_notu": G.MODEL_NOTU.get(k, ""),
                          "bu_veride": G.ornek_bu_veride(k, birimler, g.get("segmentler") or []),
                          "ne_yapar": G.ACIKLAMA_UZUN[k][0], "ornek": G.ACIKLAMA_UZUN[k][1],
                          "ne_zaman": G.ACIKLAMA_UZUN[k][2]}, **kdurum.get(k, {}))
                    for k, a, gr, c in G.KATALOG],
        "birimler": [{"id": b["id"], "tur": b["tur"], "ad": b["ad"], "kolonlar": b["kolonlar"],
                      "gunler": b.get("gunler"), "cift": b.get("cift"), "tip": b.get("tip"),
                      "ciftler": b.get("ciftler"), "gruplar": b.get("gruplar"),
                      "asama": b.get("asama") or G.birim_asamasi(b),
                      "bulan": b.get("bulan") or "kod",
                      "aciklama": b.get("aciklama") or "", "ozet": G.ozet_metni(b),
                      "tekil": (b.get("ozet") or {}).get("tekil"),
                      "mumkun": b.get("mumkun") or [], "imkansiz": b.get("imkansiz") or {},
                      "katki": {k: v for k, v in ((g.get("katki") or {}).get(b["id"]) or {}).items()
                                if k not in ("imza", "surum")} or None}
                     for b in birimler],
        "katki_esik": {"artis": G.KATKI_ARTIS, "iliski": G.KATKI_ILISKI, "dilim": G.KATKI_DILIM,
                       "uyum": G.UYUM_ARTIS},
        "uyum_kodlari": list(G.UYUM_KODLARI), "olcek_notu": G.OLCEK_NOTU,
        "oneri": {i: _oneri_goster(o, (g.get("katki") or {}).get(i)) for i, o in oneri.items()},
        "karar": karar,
        "girmeyen": g.get("girmeyen") or [],
        # Kartin basindaki dagilim grafiginde kolona tiklaninca gosterilen
        # sozluk aciklamalari (yalniz aciklamasi olan kolonlar).
        "kolon_aciklama": _kolon_aciklamalari(
            durum, {str(k) for b in birimler for k in (b.get("kolonlar") or [])}
            | {str(k) for x in (g.get("girmeyen") or []) for k in (x.get("kolonlar") or [])}),
        "segmentler": g.get("segmentler") or [],
        "sohbet": (g.get("sohbet") or [])[-40:],
        "uretilen_sayi": len(g.get("uretilen") or []),
    }


def sapma_hesapla(karar, oneri):
    """Kullanicinin oneriden farki, birim basina FARK olarak: {"ekle",
    "cikar", "param"}. Fark olarak saklanir ki model turu ya da oneri
    degisince de ayni istek uygulanabilsin ("uc kirpma istemiyorum" yeni
    oneride de kaldirilir)."""
    sapma = {}
    for i, k in (karar or {}).items():
        o = oneri.get(i) or {}
        sec, osec = list(k.get("sec") or []), list(o.get("sec") or [])
        ekle = [c for c in sec if c not in osec]
        cikar = [c for c in osec if c not in sec]
        param = {c: v for c, v in (k.get("param") or {}).items()
                 if c in sec and (c in ekle or (o.get("param") or {}).get(c) != v)}
        # Kolon bazinda fark: secili donusumde disarida birakilan kolonlar oneriden farkliysa.
        hk, ho = k.get("haric") or {}, o.get("haric") or {}
        haric = {c: list(hk.get(c) or []) for c in sec
                 if sorted(hk.get(c) or []) != sorted(ho.get(c) or [])}
        if ekle or cikar or param or haric:
            sapma[i] = {"ekle": ekle, "cikar": cikar, "param": param, "haric": haric}
    return sapma


# ---------------------------------------------------------------------------
# 02.2 SOHBET HAFIZASI: her konusma turunun kisa ozeti calismanin klasorunde
# (PROJE_HAFIZASI/<calisma>/geleneksel_sohbet_hafizasi.json). Ozet kodla
# kurulur (dil modeline yazdirilmaz): kullanicinin istegi, cevabin basi,
# onerilen ve uygulanan degisiklikler. "Yeni Sohbet" ekrani temizler, hafiza
# kalir. Dil modeline son kayitlar ve kullanicinin kararlarda yaptigi
# farklar (sapma ozeti) gider.
# ---------------------------------------------------------------------------
SOHBET_HAFIZA_EN_COK = 40


def sohbet_hafiza_yolu(anahtar):
    import re as _re
    temiz = _re.sub(r"[^A-Za-z0-9_-]", "", str(anahtar or "ana"))
    if _re.match(r"^v\d{1,6}$", temiz):
        return "/%s/geleneksel_sohbet_hafizasi.json" % temiz
    return "/oturum_%s_geleneksel_sohbet_hafizasi.json" % temiz


def sohbet_hafiza_oku(anahtar):
    import json as _json
    try:
        with _folder().get_download_stream(sohbet_hafiza_yolu(anahtar)) as akis:
            veri = _json.loads(akis.read().decode("utf-8"))
        return veri if isinstance(veri, dict) else {"kayitlar": []}
    except Exception:
        return {"kayitlar": []}


def sohbet_hafiza_ekle(anahtar, mesaj, cevap, degisiklikler=(), uygulanan=0):
    """Bir konusma turunu hafizaya ekler (en cok SOHBET_HAFIZA_EN_COK kayit;
    eskiler tek satirlik "eski" ozetine katlanir). Yazilamazsa sessiz."""
    import json as _json
    import time as _time
    from fe_agent import geleneksel as G
    h = sohbet_hafiza_oku(anahtar)
    oneriler = []
    for d in degisiklikler or []:
        kod = d.get("cikar") or d.get("ekle") or []
        ad = ", ".join(G.KATALOG_HARITA[c]["ad"] for c in kod if c in G.KATALOG_HARITA)
        if not ad:
            continue
        n = len(d.get("ids") or []) if d.get("toplu") else 1
        oneriler.append("%s: %s birimden %s" % (ad, n, "çıkar" if d.get("cikar") else "ekle")
                        if d.get("cikar") else "%s: %s birime ekle" % (ad, n))
    kayit = {"zaman": _time.strftime("%Y-%m-%d %H:%M"), "kullanici": str(mesaj or "")[:240],
             "cevap": " ".join(str(cevap or "").split())[:240], "oneriler": oneriler[:8]}
    if uygulanan:
        kayit["uygulanan"] = int(uygulanan)
    kayitlar = list(h.get("kayitlar") or []) + [kayit]
    if len(kayitlar) > SOHBET_HAFIZA_EN_COK:
        fazla = kayitlar[:-SOHBET_HAFIZA_EN_COK]
        eski = str(h.get("eski") or "")
        eski = (eski + " " + " ".join("[%s] %s" % (k.get("zaman", ""), k.get("kullanici", "")[:80])
                                      for k in fazla)).strip()
        h["eski"] = eski[-1500:]
        kayitlar = kayitlar[-SOHBET_HAFIZA_EN_COK:]
    h["kayitlar"] = kayitlar
    try:
        _folder().upload_stream(sohbet_hafiza_yolu(anahtar),
                                _json.dumps(h, ensure_ascii=False).encode("utf-8"))
    except Exception:
        pass
    return h


def sohbet_hafiza_sil(anahtar):
    """Klasordeki konusma ozetini siler (Hafizayi Sil). Dosya yoksa sessiz."""
    try:
        _folder().delete_path(sohbet_hafiza_yolu(anahtar))
    except Exception:
        try:                                        # silinemezse bos yazilir
            _folder().upload_stream(sohbet_hafiza_yolu(anahtar), b'{"kayitlar": []}')
        except Exception:
            pass


def sapma_ozeti(g):
    """Kullanicinin kararlarda oneriden yaptigi farklar, donusum basina
    (kalici tercih olarak dil modeline gider)."""
    from fe_agent import geleneksel as G
    ek, ck = {}, {}
    for v in (g.get("sapma") or {}).values():
        if not isinstance(v, dict) or "sec" in v:
            continue
        for c in v.get("ekle") or []:
            ek[c] = ek.get(c, 0) + 1
        for c in v.get("cikar") or []:
            ck[c] = ck.get(c, 0) + 1
    par = ["%s %s birimden çıkardı" % (G.KATALOG_HARITA[c]["ad"], n) for c, n in sorted(ck.items(), key=lambda x: -x[1])
           if c in G.KATALOG_HARITA]
    par += ["%s %s birime ekledi" % (G.KATALOG_HARITA[c]["ad"], n) for c, n in sorted(ek.items(), key=lambda x: -x[1])
            if c in G.KATALOG_HARITA]
    return ("Kullanıcı: " + "; ".join(par[:20]) + ".") if par else ""


def sohbet_hafiza_metni(anahtar, g, en_cok=15):
    """Dil modeline giden hafiza: kalici tercihler + son konusma ozetleri."""
    h = sohbet_hafiza_oku(anahtar)
    sat = []
    so = sapma_ozeti(g)
    if so:
        sat.append("Kararlardaki kalıcı değişiklikler: " + so)
    if h.get("eski"):
        sat.append("Daha eski konuşmalar (kısa): " + h["eski"][-600:])
    for k in (h.get("kayitlar") or [])[-en_cok:]:
        t = "[%s] Kullanıcı: %s | Cevap: %s" % (k.get("zaman", ""), k.get("kullanici", ""), k.get("cevap", "")[:160])
        if k.get("oneriler"):
            t += " | Öneriler: " + "; ".join(k["oneriler"])
        if k.get("uygulanan"):
            t += " | %s öneri uygulandı" % k["uygulanan"]
        sat.append(t)
    return "\n".join(sat)


def sapma_birlestir(g, karar, birimler, model_turu):
    """Yeni sapma: bu model turunde gorulebilen kodlarda karttaki fark;
    bu turde secilemeyen kodlardaki onceki istekler (dogrusalda "uc kirpma
    istemiyorum" gibi) korunur, baska ture gecip donunce kaybolmaz."""
    from fe_agent import geleneksel as G
    yeni = sapma_hesapla(karar, g.get("oneri") or {})
    harita = {b["id"]: b for b in birimler}
    for i, v in (g.get("sapma") or {}).items():
        if not isinstance(v, dict) or "sec" in v or i not in harita:
            continue
        mm = set(G.model_mumkun(harita[i], model_turu))
        ek = [c for c in v.get("ekle") or [] if c not in mm]
        ck = [c for c in v.get("cikar") or [] if c not in mm]
        pr = {c: p for c, p in (v.get("param") or {}).items() if c not in mm}
        if ek or ck or pr:
            h = yeni.setdefault(i, {"ekle": [], "cikar": [], "param": {}, "haric": {}})
            h["ekle"] = list(dict.fromkeys(h["ekle"] + ek))
            h["cikar"] = list(dict.fromkeys(h["cikar"] + ck))
            h["param"].update(pr)
    return yeni


def _karar_kur(g, birimler, oneri, segmentler, model_turu, kolonlar=None):
    """Karar = oneri + kullanicinin farklari (sapma). Eski bicimdeki sapma
    ({"sec", "param"}) birimin kararini oldugu gibi degistirir. kolonlar
    (kolon bazinda olcum) verilirse onerilere "haric" (deger tasimayan,
    uretilmeyecek kolonlar) yazilir."""
    from fe_agent import geleneksel as G
    if kolonlar is not None:
        G.haric_ekle(oneri, kolonlar)
    karar = {i: {"sec": list(o.get("sec") or []), "param": dict(o.get("param") or {}),
                 "haric": {c: list(a) for c, a in (o.get("haric") or {}).items()}}
             for i, o in oneri.items()}
    sapma = g.get("sapma") or {}
    eski = {i: v for i, v in sapma.items() if isinstance(v, dict) and "sec" in v}
    for i, v in sapma.items():
        if not isinstance(v, dict) or "sec" in v or i not in karar:
            continue
        k = karar[i]
        k["sec"] = [c for c in k["sec"] if c not in (v.get("cikar") or [])]
        for c in v.get("ekle") or []:
            if c not in k["sec"]:
                k["sec"].append(c)
        k["param"] = {c: p for c, p in k["param"].items() if c in k["sec"]}
        k["param"].update({c: p for c, p in (v.get("param") or {}).items() if c in k["sec"]})
        for c, adlar in (v.get("haric") or {}).items():       # kullanicinin kolon secimi
            if c in k["sec"]:
                k["haric"][c] = list(adlar or [])
        k["haric"] = {c: a for c, a in k["haric"].items() if c in k["sec"] and a}
    karar = G.karar_dogrula(birimler, karar, segmentler, model_turu)
    karar.update(G.karar_dogrula(birimler, eski, segmentler, model_turu))
    for b in birimler:
        karar.setdefault(b["id"], {"sec": [], "param": {}, "haric": {}})
    return karar


def geleneksel_karar_kaydet(durum, karar):
    """Karttaki guncel kararlari sunucuya yazar (her degisiklikte): karar ve
    sapma (oneriden fark). Boylece model turu degisince, kart yeniden
    cizilince ya da sayfa yenilenince secimler kaybolmaz."""
    from fe_agent import geleneksel as G
    g = durum.get("geleneksel") or {}
    birimler = g.get("birimler") or []
    if not birimler or not isinstance(karar, dict):
        return
    model_turu = "hepsi"
    temiz = G.karar_dogrula(birimler, karar, g.get("segmentler") or [], model_turu)
    eski = dict(g.get("karar") or {})
    eski.update(temiz)
    g["karar"] = eski
    g["sapma"] = sapma_birlestir(g, eski, birimler, model_turu)
    durum["geleneksel"] = g
    if (durum.get("_secim_alani") or {}).get("tip") == "geleneksel":
        durum["_secim_alani"]["karar"] = eski


def _veri_al(durum):
    """Arka plan isi icin tembel okuyucu: (02.2 kaynak tablosu, egitim
    maskesi, hedef). Durumun o anki kopyasi kullanilir."""
    d = dict(durum)

    def al():
        df, _y = _uretim_kaynagi(d)
        tr, _te = maskeler(d, df)
        return df, pd.Series(tr, index=df.index), (d.get("meta") or {}).get("target")
    return al


def _oneri_baslat(g, birimler, segmentler, model_turu, onceki, veri_al=None):
    """Onbellekte olmayan birimler icin arka plan isini baslatir (olcum,
    dil modeli, aileler arasi). Doner: oneri (bekleyenlerde gecici kural)."""
    from fe_agent import geleneksel as G
    katki = g.get("katki") or {}
    cikti, sor = G.oneri_onbellek(birimler, onceki, model_turu, katki)
    arasi_imza = G.arasi_imzasi(birimler, model_turu)
    arasi_sor = g.get("arasi_imza") != arasi_imza
    eksik = G.katki_eksik(birimler, katki, model_turu) if veri_al else []
    g.pop("oneri_is", None)
    if sor or arasi_sor or eksik:
        kimlik = G.oneri_isi_baslat(birimler, sor, segmentler, model_turu, arasi_sor, veri_al, katki)
        g["oneri_is"] = {"kimlik": kimlik, "model_turu": model_turu, "arasi_imza": arasi_imza,
                         "arasi_sor": arasi_sor, "baslangic": time.time(), "toplam": len(sor)}
    return G.oneri_birlestir(birimler, cikti, {}, model_turu, [], katki)


def geleneksel_is_durumu(durum):
    """Dil modeli isinin durumu. Is bittiyse sonuclar birlestirilir (oneri,
    aileler arasi birimler, karar) ve kart yenilenir. Sunucu yeniden
    basladiysa (is bellekte yok) is yeniden baslatilir. Doner: (bitti,
    degisti)."""
    from fe_agent import geleneksel as G
    g = durum.get("geleneksel") or {}
    i = g.get("oneri_is")
    if not i:
        return True, False
    d = G.oneri_isi_durumu(i.get("kimlik"))
    birimler, segmentler = g.get("birimler") or [], g.get("segmentler") or []
    model_turu = i.get("model_turu") or "hepsi"
    if d is None:
        onceki = {k: o for k, o in (g.get("oneri") or {}).items() if o.get("kaynak") == "dil modeli"}
        g["oneri"] = _oneri_baslat(g, birimler, segmentler, model_turu, onceki, _veri_al(durum))
        durum["geleneksel"] = g
        durum["_secim_alani"] = geleneksel_karti(durum)
        return not g.get("oneri_is"), True
    if d.get("durum") != "bitti":
        return False, False
    yeni_kolonlar = None
    if d.get("katki") is not None:
        yeni_kolonlar = _kolonlari_ayir(d["katki"])     # durumda yalniz ozet kalir
        g["katki"] = d["katki"]
    katki = g.get("katki") or {}
    cikti = {k: G.olcum_ekle(G.tekrar_ele(o, b, katki.get(k), model_turu)[0], b, katki.get(k), model_turu)
             for b in birimler for k, o in [(b["id"], (g.get("oneri") or {}).get(b["id"]))]
             if o and o.get("kaynak") in ("dil modeli", "secenek yok", "sohbet")}
    oneri = G.oneri_birlestir(birimler, cikti, d.get("sonuc") or {}, model_turu, d.get("sorulan") or [],
                              katki)
    if i.get("arasi_sor") and d.get("arasi") is not None:
        birimler = [b for b in birimler if b.get("bulan") != "dil modeli"]
        oneri = {k: o for k, o in oneri.items() if k in {b["id"] for b in birimler}}
        yeni = G.arasi_ekle(birimler, d["arasi"], segmentler, "dil modeli")
        for b in yeni:
            mm = set(G.model_mumkun(b, model_turu))
            oneri[b["id"]] = G.olcum_ekle({"sec": [c for c in b.get("oneri_islem") or [] if c in mm],
                                           "param": {}, "gerekce": b.get("gerekce") or "",
                                           "g3": b.get("gerekce") or "", "secilmeyen": "",
                                           "kaynak": "dil modeli", "imza": G._oneri_imza(b, model_turu)},
                                          b, katki.get(b["id"]), model_turu)
        birimler = birimler + yeni
        g["arasi_dm"] = d["arasi"]
        g["arasi_imza"] = i.get("arasi_imza")
    if yeni_kolonlar is not None:        # birim listesi kesinlestikten sonra (aileler arasi dahil)
        _kolonlari_yaz(durum, yeni_kolonlar, birimler)
    g.update({"birimler": birimler, "oneri": oneri,
              "karar": _karar_kur(g, birimler, oneri, segmentler, model_turu, kolonlari_oku(durum)),
              "oneri_hata": d.get("hata")})
    tur = dict(g.get("oneri_tur") or {})
    tur[model_turu] = oneri
    g["oneri_tur"] = tur
    g.pop("oneri_is", None)
    durum["geleneksel"] = g
    if (durum.get("_secim_alani") or {}).get("tip") == "geleneksel":
        durum["_secim_alani"] = geleneksel_karti(durum)
    return True, True


def geleneksel_sohbet_birimleri(durum, yeni):
    """Sohbette dil modelinin onerdigi yeni aileler arasi iliskiler: kod
    dogrular, birimi kurar (karar bos; oneri sohbetten). Doner: [(id,
    oneri_islem, gerekce)]."""
    from fe_agent import geleneksel as G
    g = durum.get("geleneksel") or {}
    birimler = g.get("birimler") or []
    if not yeni or not birimler:
        return []
    model_turu = "hepsi"
    eklenen = G.arasi_ekle(birimler, yeni, g.get("segmentler") or [], "sohbet")
    if not eklenen:
        return []
    oneri = dict(g.get("oneri") or {})
    karar = dict(g.get("karar") or {})
    for b in eklenen:
        oneri[b["id"]] = {"sec": [], "param": {}, "gerekce": b.get("gerekce") or "",
                          "g3": b.get("gerekce") or "", "secilmeyen": "",
                          "kaynak": "sohbet", "imza": G._oneri_imza(b, model_turu)}
        karar[b["id"]] = {"sec": [], "param": {}}
    g["birimler"] = birimler + eklenen
    g["oneri"], g["karar"] = oneri, karar
    g["arasi_sohbet"] = list(g.get("arasi_sohbet") or []) + list(yeni)
    durum["geleneksel"] = g
    return [(b["id"], [c for c in b.get("oneri_islem") or [] if c in G.model_mumkun(b, model_turu)],
             b.get("gerekce") or "") for b in eklenen]


def geleneksel_model_degistir(durum, model_turu, karar=None):
    """Model turu degisti: oneriler o ture gore yeniden alinir (ayni ture
    ait onceki dil modeli onerileri tekrar sorulmaz; gerekirse arka plan
    isi baslar); kullanicinin sapmalari o turde gecerliyse korunur. Doner:
    yeni kart."""
    from fe_agent import geleneksel as G
    model_turu = "hepsi"          # model turu ayrimi kalkti: tek mod
    if karar is not None:
        geleneksel_karar_kaydet(durum, karar)      # once ekrandaki secimler
    g = durum.get("geleneksel") or {}
    if model_turu not in G.MODEL_TURLERI or not g.get("birimler"):
        return geleneksel_karti(durum)
    birimler, segmentler = g["birimler"], g.get("segmentler") or []
    eski = dict(g.get("oneri_tur") or {})
    if not g.get("oneri_is"):
        eski["hepsi"] = g.get("oneri") or {}
    onceki = dict(eski.get(model_turu) or {})
    # Aileler arasi (dil modeli ve sohbet) birimlerin onerisi korunur.
    for b in birimler:
        o = (g.get("oneri") or {}).get(b["id"]) or {}
        if b.get("bulan") in ("dil modeli", "sohbet") and b["id"] not in onceki:
            mm = set(G.model_mumkun(b, model_turu))
            onceki[b["id"]] = dict(o, sec=[c for c in o.get("sec") or [] if c in mm],
                                   imza=G._oneri_imza(b, model_turu))
    oneri = _oneri_baslat(g, birimler, segmentler, model_turu, onceki, _veri_al(durum))
    if g.get("oneri_is"):
        g["oneri_is"]["ilk"] = False
    for b in birimler:
        if b.get("bulan") in ("dil modeli", "sohbet"):
            oneri[b["id"]] = onceki[b["id"]]
    g.update({"model_turu": model_turu, "oneri": oneri, "oneri_tur": eski,
              "karar": _karar_kur(g, birimler, oneri, segmentler, model_turu, kolonlari_oku(durum))})
    durum["geleneksel"] = g
    kart = geleneksel_karti(durum)
    if (durum.get("_secim_alani") or {}).get("tip") == "geleneksel":
        durum["_secim_alani"] = kart
    return kart


def kural_plan(durum):
    """02.2 GELENEKSEL URETIM PLANI: birimler (tek kolon, kolon ailesi,
    kolon cifti ve grubu, satir), her birimde mumkun donusumler (kod) ve
    oneri. Oneriyi dil modeli BUTUN birimler icin verir (arka plan isi;
    kart is bitince acilir); ardindan aileler arasi iliskileri onerir.
    Onceki onayda oneriden farkli secilenler (sapma) korunur."""
    from fe_agent import geleneksel as G
    df, _yeni = _uretim_kaynagi(durum)
    haric = set(durum.get("haric_kolonlar") or []) | _kusurlu(durum)
    birimler, girmeyen, segmentler = G.birimleri_kur(durum, df, haric)
    g = durum.get("geleneksel") or {}
    model_turu = "hepsi"
    onceki = dict(g.get("oneri") or {})
    eklenen = []
    if g.get("arasi_imza") == G.arasi_imzasi(birimler, model_turu):
        eklenen += G.arasi_ekle(birimler, g.get("arasi_dm") or [], segmentler, "dil modeli")
    eklenen += G.arasi_ekle(birimler + eklenen, g.get("arasi_sohbet") or [], segmentler, "sohbet")
    birimler = birimler + eklenen
    for b in eklenen:
        o = onceki.get(b["id"])
        if o:
            onceki[b["id"]] = dict(o, kaynak=o.get("kaynak") or "dil modeli", imza=G._oneri_imza(b, model_turu))
    g.update({"birimler": birimler, "girmeyen": girmeyen, "segmentler": segmentler,
              "model_turu": model_turu})
    # Kolon olcum dosyasi kaybolduysa (klasor temizligi) o birimler yeniden olculur.
    kol = kolonlari_oku(durum)
    for bid, kb in list((g.get("katki") or {}).items()):
        if (kb or {}).get("kodlar") and bid not in kol:
            g["katki"].pop(bid, None)
    tr, _te = maskeler(durum, df)
    hedef = (durum.get("meta") or {}).get("target")
    veri = (df, pd.Series(tr, index=df.index), hedef)
    oneri = _oneri_baslat(g, birimler, segmentler, model_turu, onceki, lambda: veri)
    for b in eklenen:
        if b["id"] in onceki:
            oneri[b["id"]] = onceki[b["id"]]
    g.update({"oneri": oneri,
              "karar": _karar_kur(g, birimler, oneri, segmentler, model_turu, kolonlari_oku(durum))})
    durum["geleneksel"] = g
    durum["plan"] = []            # eski numarali secim yolu kapali
    durum["_secim_alani"] = geleneksel_karti(durum)
    tur = {}
    for b in birimler:
        tur[b["tur"]] = tur.get(b["tur"], 0) + 1
    metin = ("Geleneksel değişken üretimi için %s birim hazırlandı (%s tek kolon, %s pencere ailesi, "
             "%s kolon çifti ve grubu%s). Model türü: %s. "
             % (_sayi(len(birimler)), _sayi(tur.get("kolon", 0)), _sayi(tur.get("aile", 0)),
                _sayi(tur.get("cift", 0) + tur.get("grup", 0)), ", satır düzeyi" if tur.get("satir") else "",
                G.MODEL_TURLERI.get(model_turu, model_turu)))
    if g.get("oneri_is"):
        return metin + ("Dil modeli %s birimi aşama aşama değerlendiriyor (önce kolonun kendi dönüşümü, "
                        "sonra aile içi, en son aileler arası). Bütün kararlar gelince kart açılır."
                        % _sayi(g["oneri_is"].get("toplam") or 0))
    toplam = sum(G.kolon_sayisi(b, (g["karar"].get(b["id"]) or {}).get("sec"),
                                (g["karar"].get(b["id"]) or {}).get("haric")) for b in birimler)
    return metin + ("Önerilen dönüşümlerle yaklaşık %s yeni kolon üretilecek. Kararları "
                    "değiştirebilir, alttaki sohbette tartışabilirsiniz; onayladığınızda üretilir."
                    % _sayi(toplam))


def _ogrenme_serisi(s, ogren_maske):
    """Parametrelerin ogrenilecegi satirlar. Maske yoksa tum satirlar."""
    if ogren_maske is None:
        return s.dropna()
    try:
        return s[ogren_maske].dropna()
    except Exception:
        return s.dropna()


def _rank_izgarasi(s_ogren):
    """Train dagiliminin 101 noktali yuzdelik izgarasi (rank referansi)."""
    if len(s_ogren) < 2:
        return None
    try:
        izgara = np.nanpercentile(s_ogren.to_numpy(dtype=float),
                                  np.linspace(0, 100, RANK_IZGARA + 1))
    except Exception:
        return None
    izgara = np.asarray(izgara, dtype=float)
    if not np.isfinite(izgara).all():
        return None
    return [round(float(x), 6) for x in izgara]


def _izgara_rank(s, izgara):
    """Degeri TRAIN izgarasina gore yuzdeye cevirir (0, 1]. NaN -> NaN."""
    ref = np.asarray(izgara, dtype=float)
    v = pd.to_numeric(s, errors="coerce")
    p = np.searchsorted(ref, v.to_numpy(dtype=float),
                        side="right") / float(len(ref))
    return pd.Series(p, index=s.index, dtype=float).where(v.notna())


def _tekli(df, kolonlar, d, ogren_maske=None, kayit=None):
    """Tekli donusumler.

    LEAKAGE: winsorize kesim noktalari ve rank referans dagilimi YALNIZCA
    ogren_maske (train) satirlarindan ogrenilir, sonra TUM satirlara
    uygulanir. Maske verilmezse tum satirlar kullanilir.
    kayit verilirse ogrenilen parametreler oraya yazilir.
    """
    y = {}
    for k in kolonlar:
        if k not in df.columns:
            continue
        s = pd.to_numeric(df[k], errors="coerce")
        ogren = _ogrenme_serisi(s, ogren_maske)

        if d == "log":
            y["%s__LOG" % k] = np.log1p(s.clip(lower=0))
        elif d == "rank":
            izgara = _rank_izgarasi(ogren)
            if izgara is None:
                continue
            y["%s__RANK" % k] = _izgara_rank(s, izgara)
            if kayit is not None:
                kayit.setdefault("rank", {})[k] = {
                    "izgara": izgara, "nokta": len(izgara), "kaynak": "train"}
        elif d == "winsor":
            if len(ogren) < 2:
                continue
            alt = float(ogren.quantile(WINSOR_ALT))
            ust = float(ogren.quantile(WINSOR_UST))
            if not (np.isfinite(alt) and np.isfinite(ust)):
                continue
            y["%s__WNS" % k] = s.clip(alt, ust)
            if kayit is not None:
                kayit.setdefault("winsor", {})[k] = {
                    "alt": round(alt, 6), "ust": round(ust, 6),
                    "q": [WINSOR_ALT, WINSOR_UST], "kaynak": "train"}
    return y

def _ikili(df, kolonlar, d, ogren_maske=None, kayit=None):
    """Ikili donusumler: fark ve oran.

    Bu iki donusum satir bazlidir; hicbir GLOBAL istatistik (quantile,
    ortalama, rank) kullanmaz — dolayisiyla train/test sinirini asan bir
    hesap yok. Imza simetri icin ogren_maske/kayit alir.
    """
    y = {}
    for i in range(len(kolonlar) - 1):
        a, b = kolonlar[i], kolonlar[i + 1]
        if a not in df.columns or b not in df.columns:
            continue
        sa = pd.to_numeric(df[a], errors="coerce")
        sb = pd.to_numeric(df[b], errors="coerce")
        if d == "delta":  y["%s__MINUS__%s" % (a, b)] = sa - sb
        elif d == "oran": y["%s__DIV__%s" % (a, b)] = sa / sb.replace(0, np.nan)
    return y

def _rank_kod(k, izgara):
    """Train izgarasini gomen, tek deyimlik ve calistirilabilir rank satiri."""
    ifade_mod.ad_dogrula(k)
    ifade_mod.ad_dogrula("%s__RANK" % k)
    return ('df["%s__RANK"] = pd.Series(np.searchsorted(np.array(%r), '
            '_s(df, "%s").to_numpy(dtype=float), side="right") / %s, '
            'index=df.index).where(_s(df, "%s").notna())'
            % (k, [float(x) for x in izgara], k, float(len(izgara)), k))


def _winsor_kod(k, alt, ust):
    ifade_mod.ad_dogrula(k)
    ifade_mod.ad_dogrula("%s__WNS" % k)
    return ('df["%s__WNS"] = _s(df, "%s").clip(%r, %r)'
            % (k, k, float(alt), float(ust)))


def kural_uygula(durum, secim=None):
    """Kartta onaylanan kararlar ({"dogrulama": {"adim": "kural", "karar":
    {birim id: {"sec", "param"}}}}) uygulanir; govde yoksa karttaki son
    karar. Ogrenilen her sey train satirlarindan."""
    from fe_agent import akis_faz02 as _f2
    from fe_agent import geleneksel as G
    g = durum.get("geleneksel") or {}
    if not g.get("birimler"):
        kural_plan(durum)
        g = durum.get("geleneksel") or {}
    birimler, segmentler = g.get("birimler") or [], g.get("segmentler") or []
    govde = durum.get("_dogrulama_karari")
    model_turu = "hepsi"
    if isinstance(govde, dict) and govde.get("adim") == "kural" and isinstance(govde.get("karar"), dict):
        karar = G.karar_dogrula(birimler, govde["karar"], segmentler, model_turu)
    else:
        karar = G.karar_dogrula(birimler, g.get("karar") or {}, segmentler, model_turu)
    oneri = g.get("oneri") or {}
    g["karar"] = karar
    g["sapma"] = sapma_birlestir(g, karar, birimler, model_turu)
    durum["geleneksel"] = g
    yeni_duzen = _f2.updt_modu(durum)
    hedef = _f2.updt_adi(durum) if yeni_duzen else "%s_ENRICHED" % durum["veri_seti"]

    silinen_kural = _adim_temizle(durum, KURAL_KAYNAK)
    silinen_kesif = _adim_temizle(durum, KESIF_KAYNAK)
    _sfa_gecersiz(durum)
    # DEGISKEN DEFTERI: 02.3 kolonlari tablo yeniden kuruldugu icin dustu
    # (reddedilmedi; yeniden onerilebilir).
    from fe_agent import degisken_defteri as _defter
    if silinen_kesif:
        _defter.adim_silindi(durum, KESIF_KAYNAK)
    if not any(k.get("sec") for k in karar.values()):
        _defter.adim_yenilendi(durum, KURAL_KAYNAK, [])
        g["uretilen"], g["sozluk_ek"] = [], []
        if yeni_duzen:
            _f2.updt_ilerlet(durum, "02.2", "02.1")
        return ("Bu adımda üretim yapılmadı." + _yeniden_notu(silinen_kural, silinen_kesif))

    df, _yd = _uretim_kaynagi(durum)
    tr, _te = maskeler(durum, df)            # LEAKAGE SINIRI
    yasak = _meta_yasak(durum) | _kusurlu(durum)
    hedef_kolon = (durum.get("meta") or {}).get("target")
    yeni, kayit, hatalar = G.uygula(df, birimler, karar, pd.Series(tr, index=df.index), hedef_kolon)
    kod_satirlari, elenen, sozluk = [], [], []
    for r in kayit:
        if r["ad"] in yasak:
            continue
        try:
            ifade_mod.ad_dogrula(r["ad"])
            ifade_mod._kod_satiri_dogrula(r["kod_satiri"])
        except Exception as e:
            elenen.append((r["ad"], str(e)[:60]))
            continue
        df[r["ad"]] = yeni[r["ad"]]
        kod_satirlari.append((r["ad"], r["kod_satiri"],
                              "%s: %s" % (G.KATALOG_HARITA[r["kod"]]["ad"], r["aciklama"])[:200]))
        sozluk.append({"DEGISKEN": r["ad"], "TIP": "sayısal", "ACIKLAMA": r["aciklama"],
                       "NULL_ORANI": round(float(yeni[r["ad"]].isna().mean()), 4) if len(df) else 0.0,
                       "KAYNAK_KOLON": ", ".join(r["kaynaklar"]),
                       "_ek_bilgi": "02.2 Kural Tabanlı Değişken Üretimi adımında %s kolonundan "
                                    "üretildi (%s)." % (", ".join(r["kaynaklar"]),
                                                       G.KATALOG_HARITA[r["kod"]]["ad"]),
                       "_uretilen": "02.2 adımında %s kolonundan üretildi (%s)"
                                    % (", ".join(r["kaynaklar"]), G.KATALOG_HARITA[r["kod"]]["ad"])})
    uretilen = [a for a, _k, _g in kod_satirlari]
    try:
        if yeni_duzen:
            _f2.updt_yaz(durum, df, "02.2")
        else:
            dataiku.Dataset(hedef).write_with_schema(df)
    except Exception as e:
        return ("Üretilen %s kolon hesaplandı ama '%s' veri setine YAZILAMADI: %s\n\n"
                "Bu adımda hiçbir değişken kaydedilmedi." % (_sayi(len(uretilen)), hedef, str(e)[:120]))
    onbellek_temizle(hedef)
    durum["uretilen"] = sorted(set(durum.get("uretilen") or []) | set(uretilen))
    _kaynaga_yaz(durum, KURAL_KAYNAK, uretilen)
    durum["kod_bloklari"] = (durum.get("kod_bloklari") or []) + \
        [["Kural tabanlı üretim", kod_satirlari, KURAL_KAYNAK]]
    ogr = durum.get("ogrenilen_donusum") or {}
    ogr["kural"] = {r["ad"]: r["ogrenilen"] for r in kayit if r["ogrenilen"] and r["ad"] in uretilen}
    durum["ogrenilen_donusum"] = ogr
    g["uretilen"], g["sozluk_ek"] = uretilen, sozluk
    durum["geleneksel"] = g
    # DEGISKEN DEFTERI: uretilenler (ozetleriyle); onceki turda uretilip bu
    # turda uretilmeyenler reddedilenlere gecer.
    try:
        _ur = set(uretilen)
        _defter.uretim_kaydet(durum, KURAL_KAYNAK, [
            {"ad": r["ad"], "anlam": r["aciklama"], "kaynak_kolonlar": r["kaynaklar"],
             "ifade": "", "ozet": _defter.ozet_cikar(df[r["ad"]])}
            for r in kayit if r["ad"] in _ur and r["ad"] in df.columns])
        _defter.adim_yenilendi(durum, KURAL_KAYNAK, uretilen)
    except Exception:
        pass
    _yazildi, kod_hata = _uretim_kodu_yaz(durum, hedef)
    birim_sayi = sum(1 for k in karar.values() if k.get("sec"))
    notlar = []
    if hatalar:
        notlar.append(_liste("Uygulanamayan %s dönüşüm:" % _sayi(len(hatalar)), hatalar, 6))
    if elenen:
        notlar.append(_liste("Geçersiz ad nedeniyle elenen %s kolon:" % _sayi(len(elenen)),
                             ["%s: %s" % e for e in elenen], 6))
    notlar.append(("Üretim kodu dosyası yazılamadı: %s" % kod_hata) if kod_hata else
                  "Tüm üretimin Python kodu PROJE_HAFIZASI/uretim_kodu.py dosyasında.")
    return ("%s birimde %s yeni kolon üretildi ve %s veri setine yazıldı. Öğrenilen her şey "
            "(kırpma sınırları, sıra ızgarası, ortalama ve standart sapma, dilim sınırları, "
            "frekans, WoE ve hedef ortalaması) yalnız geliştirme satırlarından öğrenildi; WoE ve "
            "hedef ortalaması geliştirme satırlarında kat dışı hesaplandı.%s\n\n%s"
            % (_sayi(birim_sayi), _sayi(len(uretilen)), hedef,
               _yeniden_notu(silinen_kural, silinen_kesif), "\n\n".join(notlar)))


def _yeniden_notu(silinen_kural, silinen_kesif):
    """Adim yeniden calistirildiginda neyin gectigini kullaniciya yaz."""
    parcalar = []
    if silinen_kural:
        parcalar.append("Bu adım yeniden çalıştırıldı: önceki turda üretilen "
                        "%s kural tabanlı kolonun kaydı silindi ve yerine "
                        "yenisi yazıldı." % _sayi(len(silinen_kural)))
    if silinen_kesif:
        kesif = akis_atif.adim("kesif")
        parcalar.append("Tablo yeniden kurulduğu için %s "
                        "adımında üretilen %s kolon veri setinden düştü; "
                        "kayıtları da temizlendi. %s adımına gelince "
                        "yeniden üretilecekler."
                        % (kesif, _sayi(len(silinen_kesif)), kesif))
    return ("\n\n" + "\n".join(parcalar)) if parcalar else ""

def kesif_plan(durum):
    # Kusurlu ham kolonlar (Veri Profili) dil modeline gitmez; ifadede
    # gecerse dogrulamada reddedilir. SFA henuz yok (uretimden sonra).
    kusurlu = _kusurlu(durum)
    # Yeni duzende UPDT veri uretilen kolonlari da tasir; dil modeline
    # eskisi gibi yalniz modelleme tablosunun kendi kolonlari gider.
    from fe_agent.akis_faz02 import uretilenler
    uretilmis = set(uretilenler(durum))
    kolonlar = [k for k in modelleme_df(durum, limit=SEMA_LIMITI).columns
                if k not in kusurlu and k not in uretilmis]
    sz = sozluk_oku(durum)   # CSV yedegini de okur
    yasak = _meta_yasak(durum)

    # DEGISKEN DEFTERI: daha once uretilen ve uretilip / onerilip reddedilen
    # degiskenler dil modeline "bunlari onerme" diye gider; donen oneriler
    # ayrica kodla (ad ve ifade imzasi) elenir.
    from fe_agent import degisken_defteri as _defter
    try:
        bilinen = _defter.bilinenler(durum)
        red_satir, ure_satir = _defter.kesif_notu(durum)
    except Exception:
        bilinen, red_satir, ure_satir = None, [], []

    ham, hata = llm_mod.kesif_ifade_oner(
        sozluk_df=sz, kolonlar=kolonlar, meta=durum.get("meta", {}),
        onceki_uretilen=ure_satir, onceki_reddedilen=red_satir)

    if hata:
        # Hatayi yutma: kullaniciya goster, adimi ilerletme.
        durum["hipotez"] = []
        return ("Keşif önerilerini alamadım.\n\n  %s\n\n"
                "Tekrar denemek için onaylayın, bu adımı geçebilir ya da "
                "önceki adıma dönebilirsiniz." % hata)

    gecerli, reddedilen, ad_elenen = [], [], 0
    tekrar = []
    for o in (ham or []):
        # Daha once uretilmis ya da reddedilmis: yeniden onerilmez.
        neden_ = _defter.tekrar_mi(durum, o.get("ad"), o.get("ifade"), bilinen) if bilinen else ""
        if neden_:
            tekrar.append((o.get("ad", "?"), neden_))
            continue
        ok, dogrulama_hatasi, kullanilan = ifade_mod.dogrula(o["ifade"], kolonlar)
        if not ok:
            reddedilen.append((o.get("ad", "?"), dogrulama_hatasi))
            _defter.red_kaydet(durum, KESIF_KAYNAK, [o], "Denetimden geçemedi: %s" % dogrulama_hatasi)
            continue
        if o.get("ad") in yasak or (set(kullanilan) & yasak):
            reddedilen.append((o.get("ad", "?"), "hedef/kimlik kolonu kullanılamaz"))
            _defter.red_kaydet(durum, KESIF_KAYNAK, [o], "Hedef ya da kimlik kolonunu kullanıyor")
            continue
        # LLM'in urettigi ad sablona enjeksiyon yapabilir; ifade.py
        # gecersiz adda ValueError firlatir. Oneriyi atla, sayisini bildir.
        try:
            o["kod"] = ifade_mod.python_kodu(o["ad"], o["ifade"])
        except Exception as e:
            ad_elenen += 1
            reddedilen.append((o.get("ad", "?"), str(e)[:60]))
            continue
        o["kolonlar"] = kullanilan
        gecerli.append(o)

    # ONCEKI TURDA 02.3'TE URETILENLER listeye tasinir (basta): adim
    # yeniden calisinca eski kolonlar tablodan silinir; secilmeyen
    # reddedilenlere gecer. Sonraki adimlarda elenmis olanlar tasinmaz.
    tasinan = []
    try:
        for o in _defter.kesif_tasinacaklar(durum):
            ok, _h, kullanilan = ifade_mod.dogrula(o["ifade"], kolonlar)
            if not ok or o["ad"] in yasak or (set(kullanilan) & yasak):
                continue
            o["kod"] = ifade_mod.python_kodu(o["ad"], o["ifade"])
            o["kolonlar"] = kullanilan
            o["onceki"] = True
            tasinan.append(o)
    except Exception:
        tasinan = []
    gecerli = tasinan + gecerli
    durum["hipotez"] = gecerli
    durum["_kesif_ad_elenen"] = ad_elenen
    durum["_kesif_tekrar"] = len(tekrar)
    tekrar_not = ("\n\nDeğişken defterine göre %s öneri daha önce üretilmiş ya da reddedilmiş "
                  "değişkenin aynısıydı; listeye alınmadı (%s)."
                  % (_sayi(len(tekrar)), ", ".join(a for a, _n in tekrar[:5]))) if tekrar else ""
    if not gecerli:
        return ("Bu turda geçerli bir hipotez üretilemedi.\n\n%s%s\n\n"
                "Adımı geçebilirsiniz."
                % (_liste("Kontrolden geçemeyen öneriler:",
                          ["%s: %s" % r for r in reddedilen], 6), tekrar_not))

    satirlar = []
    for i, o in enumerate(gecerli, 1):
        satirlar.append("  %2d. %s%s" % (i, o["ad"], "  (önceki turda üretildi)" if o.get("onceki") else ""))
        satirlar.append("      %s" % o["ifade"])
        if o.get("gerekce"):
            satirlar.append("      %s" % o["gerekce"][:88])

    red_not = ("\n\n%s" % _liste("Güvenlik kontrolünden geçemeyenler:",
                                 ["%s: %s" % r for r in reddedilen], 5)) if reddedilen else ""
    ad_not = ("\n\nBunların %s tanesi geçersiz değişken adı yüzünden elendi."
              % _sayi(ad_elenen)) if ad_elenen else ""

    bilinen_not = ""
    if bilinen and (bilinen["uretilen"] or bilinen["reddedilen"]):
        bilinen_not = ("\n\nDaha önce üretilen %s ve reddedilen %s değişken dil modeline "
                       "«bunları yeniden önerme» diye verildi (değişken defteri)."
                       % (_sayi(len(bilinen["uretilen"])), _sayi(len(bilinen["reddedilen"]))))
    return ("Klasik kalıpların dışına çıkarak %s yeni değişken hipotezi "
            "üretildi. Her ifade denetimden geçti.\n\n%s%s%s%s%s\n\n"
            "Tümünü uygulamak için onaylayın; seçmek için numaralarını belirtin."
            % (_sayi(len(gecerli)), "\n".join(satirlar), red_not, ad_not, tekrar_not, bilinen_not))

def kesif_uygula(durum, secim=None):
    tum_hipotez = list(durum.get("hipotez") or [])
    hipotez = _secimi_uygula(durum.get("hipotez") or [], secim)
    from fe_agent import degisken_defteri as _defter
    from fe_agent import akis_faz02 as _f2
    yeni_duzen = _f2.updt_modu(durum)
    hedef = _f2.updt_adi(durum) if yeni_duzen else "%s_ENRICHED" % durum["veri_seti"]

    # Adimin onceki kayitlari once silinir; aksi halde secim degisince eski
    # kolonlar tabloda kalir, durum["uretilen"] ile tablo birbirini tutmaz.
    silinen = _adim_temizle(durum, KESIF_KAYNAK)
    _sfa_gecersiz(durum)

    if not hipotez:
        mesaj = "Bu adımda üretim yapılmadı."
        # Onerilip secilmeyenler ve onceki turun kolonlari reddedilenlere.
        try:
            _defter.red_kaydet(durum, KESIF_KAYNAK, tum_hipotez, "Önerildi; seçmediniz")
            _defter.adim_yenilendi(durum, KESIF_KAYNAK, [])
        except Exception:
            pass
        if yeni_duzen:
            _f2.updt_ilerlet(durum, "02.3", "02.2")
        if silinen:
            mesaj += ("\n\nÖnceki turda üretilen %s keşif kolonunun kaydı "
                      "silindi." % _sayi(len(silinen)))
        # Kural adiminin bloklari duruyorsa uretim kodu yine guncel kalsin
        _uretim_kodu_yaz(durum, hedef)
        return mesaj

    # Kural adimi bir sey urettiyse _ENRICHED ustune eklenir; yoksa
    # modelleme tablosundan kurulur.
    from fe_agent.akis_faz02 import cozum_kolonlari_ekle
    from fe_agent.akis_faz02 import uretim_kolonlari
    if yeni_duzen:
        df = _f2.asama_df(durum, "02.2")
    else:
        df = _df_oku(hedef) if (uretim_kolonlari(durum) and _dataset_var_mi(hedef)) \
            else modelleme_df(durum)
        df = cozum_kolonlari_ekle(durum, df)
    eski = [c for c in silinen if c in df.columns]
    if eski:
        df = df.drop(columns=eski)

    yasak = _meta_yasak(durum)
    uretilen, kod_satirlari, hatali = [], [], []
    for h in hipotez:
        if h.get("ad") in yasak:
            hatali.append((h.get("ad", "?"), "hedef/kimlik kolonu üretilemez"))
            continue
        try:
            kod = h.get("kod") or ifade_mod.python_kodu(h["ad"], h["ifade"])
            df[h["ad"]] = ifade_mod.degerlendir(df, h["ifade"])
            uretilen.append(h["ad"])
            kod_satirlari.append((h["ad"], kod,
                                  "%s  |  %s" % (h["ifade"], h.get("gerekce", ""))))
        except Exception as e:
            hatali.append((h["ad"], str(e)[:60]))

    try:
        if yeni_duzen:
            _f2.updt_yaz(durum, df, "02.3")
        else:
            dataiku.Dataset(hedef).write_with_schema(df)
    except Exception as e:
        return ("Üretilen %s kolon hesaplandı ama '%s' veri setine "
                "YAZILAMADI: %s\n\n"
                "Dataiku akışında bu veri setini oluşturup adımı yeniden "
                "çalıştırın. Bu adımda hiçbir değişken kaydedilmedi."
                % (_sayi(len(uretilen)), hedef, str(e)[:120]))
    # Bu yazma _yaz() uzerinden GECMIYOR (hedef dataset yoksa farkli bir
    # hata metni gerekiyor), dolayisiyla onbellek iptalini kendisi yapar.
    onbellek_temizle(hedef)      # tablo degisti; bayat kopya okunmasin

    durum["uretilen"] = sorted(set(durum.get("uretilen") or []) | set(uretilen))
    _kaynaga_yaz(durum, KESIF_KAYNAK, uretilen)
    durum["kod_bloklari"] = (durum.get("kod_bloklari") or []) + \
        [["AI değişken keşfi", kod_satirlari, KESIF_KAYNAK]]
    # DEGISKEN DEFTERI: uretilenler (ozetleriyle); onerilip secilmeyenler,
    # hesaplanamayanlar ve onceki turda uretilip bu turda uretilmeyenler
    # reddedilenlere gecer (02.3 bunlari yeniden onermez).
    try:
        _ur = set(uretilen)
        _secili = {h.get("ad") for h in hipotez}
        _defter.uretim_kaydet(durum, KESIF_KAYNAK, [
            dict(h, kaynak_kolonlar=h.get("kolonlar") or [], ozet=_defter.ozet_cikar(df[h["ad"]]))
            for h in hipotez if h.get("ad") in _ur])
        _defter.red_kaydet(durum, KESIF_KAYNAK, [h for h in tum_hipotez if h.get("ad") not in _secili],
                           "Önerildi; seçmediniz")
        _defter.red_kaydet(durum, KESIF_KAYNAK, [h for h in hipotez if h.get("ad") not in _ur],
                           {a: "Hesaplanamadı: %s" % n for a, n in hatali})
        _defter.adim_yenilendi(durum, KESIF_KAYNAK, uretilen)
    except Exception:
        pass

    _yazildi, kod_hata = _uretim_kodu_yaz(durum, hedef)

    hata_not = ("\n\n%s" % _liste("Hesaplanamayanlar:",
                                  ["%s: %s" % h for h in hatali], 5)) if hatali else ""
    yeniden_not = ("\n\nBu adım yeniden çalıştırıldı: önceki turun %s kolonu "
                   "hem kayıttan hem veri setinden kaldırıldı."
                   % _sayi(len(silinen))) if silinen else ""
    kod_not = ("\n\nÜretim kodu dosyası yazılamadı: %s" % kod_hata) if kod_hata \
        else ("\n\nTüm üretimin (kural + keşif) Python kodu "
              "PROJE_HAFIZASI/uretim_kodu.py dosyasında.")

    return ("%s hipotez üretildi ve %s veri setine yazıldı.%s%s%s"
            % (_sayi(len(uretilen)), hedef, hata_not, yeniden_not, kod_not))
