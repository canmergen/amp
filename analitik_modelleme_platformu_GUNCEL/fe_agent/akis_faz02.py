# -*- coding: utf-8 -*-
"""fe_agent/akis_faz02.py - Veri Profili (Faz 02'nin ilk adimi) ve Faz 03 -
Veri Anlama ve Hazirlama: SFA, stabilite, baz set.

SIRA: Veri Profili ham kolonlarla calisir (kusurlu kolonlardan degisken
uretilmesin diye uretimden once). SFA, stabilite ve baz set ise uretimden
SONRA, eldeki butun degiskenlerle (ham + uretilen; _ENRICHED) calisir.
"""


import json
import math
import re

import numpy as np
import pandas as pd
from fe_agent import aralik as aralik_mod
from fe_agent import sfa as sfa_mod
from fe_agent import sfa_karar
from fe_agent import akis_atif

from fe_agent.akis_durum import (
    SPLIT_KOLON, _dataset_okunur_mu, _df_oku, _liste, _nerede, _ond, _sayi, _yaz,
    bolme_ayarlari, kolon_ozeti_cikar, kolon_ozeti_tamamla, maskeler,
    modelleme_df, setler, set_basligi, sozluk_oku,
)

# SFA'nin aralik onerileri (bkz. aralik.py) calismanin klasorunde; durum
# dosyasini sisirmemek icin ayri JSON. Panel /sfa_aralik ucundan okur.
ARALIK_DOSYA = "sfa_aralik.json"


def aralik_oku(durum):
    """SFA degisken detayi {degisken: detay}; yoksa {}. (Eski ad korunuyor.)"""
    return sfa_detay_oku(durum)


def aralik_yolu(durum):
    from fe_agent.akis_faz01 import amp_klasor_adi
    return "/%s/%s" % (amp_klasor_adi(durum), ARALIK_DOSYA)


def _aciklamalar(durum):
    """{kolon: sozluk aciklamasi}: hassas degisken tespiti icin."""
    try:
        from fe_agent import sozluk_calisma
        sz = sozluk_oku(durum)
        ad_k = sozluk_calisma.degisken_kolonu_bul(sz)
        tanim_k = sozluk_calisma.tanim_kolonu_bul(sz)
        if ad_k is None or tanim_k is None:
            return {}
        return {str(a): str(t) for a, t in zip(sz[ad_k], sz[tanim_k].fillna(""))}
    except Exception:
        return {}


# Plan metinleri her "Geri Dön" tiklamasinda yeniden uretilir; bu yuzden
# plan fonksiyonlari TAM tablo OKUMAZ. Bir sayiya ihtiyac duyulursa
# durum'daki profil bilgisi kullanilir, yoksa asagidaki limitle sema okunur.
# Tam okuma yalnizca "uygula" adimlarinda yapilir.
SEMA_LIMITI = 200


def _adlar(liste, en_fazla=4):
    """"A, B, C +5" ya da "yok": Etiket : Deger satirinin degeri."""
    liste = [str(x) for x in (liste or [])]
    if not liste:
        return "yok"
    ek = " +%s" % _sayi(len(liste) - en_fazla) if len(liste) > en_fazla else ""
    return ", ".join(liste[:en_fazla]) + ek


def _sayi_ad(liste, en_fazla=3):
    """"3 · A, B, C" ya da "0"."""
    liste = list(liste or [])
    if not liste:
        return "0"
    return "%s · %s" % (_sayi(len(liste)), _adlar(liste, en_fazla))


def _kolon_sayisi(durum):
    """Plan metni icin kolon sayisi. Once durum, sonra sinirli sema okumasi."""
    # Teyitten sonra tek kaynak AMP_VERISETI
    amp = (durum.get("amp_cikti") or {}).get("veri") or {}
    if amp.get("kolon"):
        return int(amp["kolon"])
    p = durum.get("profil") or {}
    if p.get("kolon"):
        return int(p["kolon"])
    try:
        return int(modelleme_df(durum, limit=SEMA_LIMITI).shape[1])
    except Exception:
        return 0


def _meta_kolonlar(durum):
    """Baz setten ASLA dusurulmeyecek kolonlar.

    target/id/donem'in yaninda SPLIT_KOLON da korunur: kimlik kolonu yoksa
    (ya da kimlik listesi cok buyukse) gelistirme/test bolmesi veri setine
    bu kolonla KALICI yaziliyor.
"""
    m = durum.get("meta") or {}
    korunan = {x for x in (m.get("target"), m.get("id"), m.get("donem")) if x}
    if ((durum.get("bolme") or {}).get("kalici") == "kolon"
            or SPLIT_KOLON in (durum.get("veri_seti_kolonlari") or [])):
        korunan.add(SPLIT_KOLON)
    else:
        # Kalicilik bicimi bilinmiyorsa da guvenli taraf: kolon varsa koru.
        korunan.add(SPLIT_KOLON)
    return korunan


# Analiz Merkezi tablolarinda gosterilen satir sayisi. TAM tablo oturum
# JSON'una YAZILMAZ (1.000+ kolonda dosya sismesi olur); tam hali her zaman
# dataset'e / yedek CSV'ye yazilir, oturumda yalnizca bu ilk N satir durur.
PANEL_SATIR = 20

# Null oranina gore kova sinirlari (VERI / EKSIK DEGER sekmesi ozeti).
NULL_AZ = 0.05


def _eksik_ozeti(tablo, satir, asiri=None):
    """profil_cikar tablosundan EKSIK DEGER sekmesinin beslendigi ozet.

    Doner: (ilk20, null_ozet, ek_alanlar). tablo NULL_RATIO'ya gore
    zaten azalan sirali geldigi icin ilk N satir "en cok bos" olanlardir.
    """
    ilk20, ozet = [], {"hic_null_yok": 0, "az": 0, "orta": 0, "asiri": 0}
    toplam_null, null_kolon, en_yuksek, en_yuksek_kolon = 0, 0, 0.0, None

    for _, r in tablo.iterrows():
        oran = float(r["NULL_RATIO"] or 0.0)
        adet = int(r["NULL_COUNT"] or 0)
        toplam_null += adet
        if adet:
            null_kolon += 1
        if oran > en_yuksek:
            en_yuksek, en_yuksek_kolon = oran, str(r["FEATURE"])
        if oran <= 0:
            ozet["hic_null_yok"] += 1
        elif oran <= NULL_AZ:
            ozet["az"] += 1
        elif oran <= (sfa_mod.NULL_ESIK if asiri is None else asiri):
            ozet["orta"] += 1
        else:
            ozet["asiri"] += 1

    for _, r in tablo.head(PANEL_SATIR).iterrows():
        ilk20.append({
            "FEATURE": str(r["FEATURE"]),
            "TYPE": str(r["TYPE"]),
            "NULL_COUNT": int(r["NULL_COUNT"] or 0),
            "NULL_RATIO": round(float(r["NULL_RATIO"] or 0.0), 4),
            "UNIQUE": int(r["UNIQUE"] or 0),
            "DURUM": str(r["DURUM"]),
        })

    kolon = int(len(tablo))
    hucre = float(satir) * kolon
    ek = {
        "profil_kolon": kolon,
        "null_oran": round(toplam_null / hucre, 4) if hucre else None,
        "null_kolon_adet": null_kolon,
        "null_maks": round(en_yuksek, 4),
        "null_maks_kolon": en_yuksek_kolon,
        "asiri_null_adet": ozet["asiri"],
    }
    return ilk20, ozet, ek


def _sfa_ilk20(tablo):
    """sfa_calistir tablosunun IV'ye gore ilk N satiri (SFA sekmesi)."""
    if tablo is None or not len(tablo):
        return []
    satirlar = []
    for _, r in tablo.head(PANEL_SATIR).iterrows():
        iv, c = r.get("IV"), r.get("C_VALUE")
        satirlar.append({
            "FEATURE": str(r["FEATURE"]),
            "IV": None if pd.isna(iv) else round(float(iv), 4),
            "C_VALUE": None if pd.isna(c) else round(float(c), 4),
            "SFA_RESULT": str(r.get("SFA_RESULT") or ""),
            "NOT": str(r.get("NOT") or ""),
        })
    return satirlar


def _atlanan_notu(ozet, baslik):
    """sfa/stabilite ciktisindaki ATLANDI degiskenleri gorunur kilar."""
    atlanan = ozet.get("atlanan") or []
    if not atlanan:
        return ""
    return "\n\n%s\n  (ölçüm yapılamadı: bu değişkenler sessizce kaybolmadı, " \
           "baz sette korunuyorlar)" % _liste(baslik, atlanan, 12)


# ===========================================================================
# ANALIZ TABLOSU: ham + uretilen degiskenler
# ===========================================================================
def girmez_dusur(durum, df):
    """02.1 kararlari onaylaninca UPDT veriden cikan kolonlar: uretime
    girmeyenler (eksik orani yuksek, sabit, kimlik benzeri, kardinalite,
    tarih, ayni icerikli kopya) ve Çıkar denenler. Hedef, kimlik, donem ve
    _SPLIT korunur. Cozum kolonlari (ör. IL_GRP, TARIH_GUN) ham kolondan
    ONCE uretilmis olmali (cozum_kolonlari_ekle)."""
    dus = [k for k in kusurlu_kolonlar(durum) if k in df.columns and k not in _meta_kolonlar(durum)]
    return df.drop(columns=dus) if dus else df


def kusurlu_kolonlar(durum):
    """Veri Profili'nin kusurlu buldugu ham kolonlar (asiri bos, sabit,
    kimlik benzeri, kardinalitesi asiri yuksek, ayni icerikli kopya) ve
    kullanicinin 02.1'de cikardigi kolonlar. Bunlardan degisken uretilmez;
    Analitik Baz Set'te duserler."""
    p = durum.get("profil") or {}
    t = p.get("profil_teshis") or {}
    karar = p.get("profil_karar") if isinstance(p.get("profil_karar"), dict) else {}
    return sorted(set(t.get("cok_bos") or []) | set(t.get("sabit") or [])
                  | set(t.get("kimlik_gibi") or [])
                  | set(t.get("yuksek_kardinalite") or [])
                  | set(t.get("tarih") or [])
                  | set(t.get("ayni_icerik") or [])
                  | {k for k, v in karar.items() if v == "cikar"})


# ===========================================================================
# 02.1 COZUMLER (bkz. kolon_cozum.py): "uretime girmez" denen kolon atilmadan
# once cozum onerilir; secilen cozumun kolonlari (IL_GRP, NOT_SKOR ...)
# uretilen degisken gibi sonraki adimlara girer, ham kolon girmez.
# ===========================================================================
COZUM_KAYNAK = "cozum"
COZUM_KONTROLLERI = ("cok_bos", "kimlik_gibi", "yuksek_kardinalite", "tarih")


def cozum_onerileri(durum):
    p = durum.get("profil") or {}
    o = p.get("cozum_oneri")
    return o if isinstance(o, dict) else {}


def cozum_secilebilir(durum):
    """Birden cok secenegi olan (Çıkar disinda cozumu bulunan) kolonlar."""
    return {k: v for k, v in cozum_onerileri(durum).items()
            if len(v.get("secenekler") or []) > 1}


def cozum_secimi(durum):
    """{kolon: cozum kodu}: kullanicinin secimi, yoksa oneri."""
    p = durum.get("profil") or {}
    sec = p.get("cozum_secim") if isinstance(p.get("cozum_secim"), dict) else {}
    return {k: (sec.get(k) if sec.get(k) in v["secenekler"] else v["oneri"])
            for k, v in cozum_onerileri(durum).items()}


def _cozum_ogren(durum):
    """Secilen cozumleri EGITIM satirlarindan ogrenir; p["cozum_bilgi"] =
    {kolon: {"cozum", "kolonlar", "bilgi", "ozet"}} ve uretilen listesine
    yeni kolonlar yazilir (eski cozum kolonlari once silinir)."""
    from fe_agent import kolon_cozum as kc
    p = durum.get("profil") or {}
    eski = set()
    for v in (p.get("cozum_bilgi") or {}).values():
        eski |= set(v.get("kolonlar") or [])
    for a in (p.get("duzeltme_bilgi") or {}).values():
        for v in a.values():
            eski |= set(v.get("kolonlar") or [])
    # Karar kartinda Çıkar denen kolonun cozumu de uretilmez (ör. donemden
    # sonraki tarihi olan tarih kolonunun gun farki).
    karar = p.get("profil_karar") if isinstance(p.get("profil_karar"), dict) else {}
    secim = {k: c for k, c in cozum_secimi(durum).items()
             if c != "cikar" and karar.get(k) != PROFIL_KARAR_CIKAR}
    duz = any(c != "birak" for a in duzeltme_secimi(durum).values() for c in a.values())
    bilgi_hepsi = {}
    p["duzeltme_bilgi"] = {}
    duz_yeni = []
    if secim or duz:
        df = asama_df(durum, "01") if updt_modu(durum) else modelleme_df(durum)
        # Cozum ve duzeltmeler satir cikarildiktan SONRAKI tablodan ogrenilir.
        df = satir_kararlarini_uygula(durum, df)
        target = (durum.get("meta") or {}).get("target")
        tr = setler(durum, df)["egitim"]
        y = df[target] if target in df.columns else pd.Series(np.nan, index=df.index)
        mevcut = set(map(str, df.columns))
        durum["profil"] = p
        duz_yeni = _duzeltme_ogren(durum, df, tr, mevcut)
        for k, c in secim.items():
            if k not in df.columns:
                continue
            o = cozum_onerileri(durum).get(k) or {}
            if c == "gun_farki":
                donem = (durum.get("meta") or {}).get("donem")
                b = {"donem": donem}
                ad = kc.yeni_kolon_adi(k, c, mevcut)
                kolonlar = [ad] if ad else []
                if donem in df.columns:     # ozet ozel tarih kodu duzeltmesinden sonra
                    dx = _duzeltmeleri_uygula(durum, df[[k, donem]])
                    gun = kc.gun_farki(dx[k], dx[donem])
                else:
                    gun = None
                ozet = _gun_ozeti(gun)
            elif c == "metin":
                b = kc.metin_ogren(df[k], y, tr)
                cikti = kc.metin_uygula(df[k], b, tr, y, kolon=k)
                kolonlar = [str(x) for x in cikti.columns]
                ozet = kc.metin_ozeti(b)
            else:
                b = kc.ogren(c, df[k], y, tr, onek=o.get("onek"))
                ad = kc.yeni_kolon_adi(k, c, mevcut)
                kolonlar = [ad] if ad else []
                ozet = kc.grup_ozeti(b) if c != "dolu_bayrak" else "Dolu satır 1, boş satır 0."
            mevcut |= set(kolonlar)
            bilgi_hepsi[k] = {"cozum": c, "kolonlar": kolonlar, "bilgi": _json_uyumlu(b),
                              "ozet": ozet}
    p["cozum_bilgi"] = bilgi_hepsi
    durum["profil"] = p
    yeni = {c for v in bilgi_hepsi.values() for c in v["kolonlar"]} | set(duz_yeni)
    durum["uretilen"] = sorted((set(durum.get("uretilen") or []) - eski) | yeni)
    harita = durum.get("uretilen_kaynak") if isinstance(durum.get("uretilen_kaynak"), dict) else {}
    harita[COZUM_KAYNAK] = sorted(yeni)
    durum["uretilen_kaynak"] = harita
    return bilgi_hepsi


def _json_uyumlu(x):
    """Durumda saklanacak: numpy sayilari duz sayiya, ondaliklar 6 haneye."""
    if isinstance(x, dict):
        return {str(k): _json_uyumlu(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_json_uyumlu(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return round(float(x), 6)
    return x


def cozum_kolonlari_ekle(durum, df):
    """Secilen cozumlerin kolonlarini df'e ekler (eksikse). Ogrenilen bilgi
    durumda; hesap tablonun tamaminda. Doner: df (gerekirse kopya)."""
    df = _duzeltmeleri_uygula(durum, df)
    bilgi = (durum.get("profil") or {}).get("cozum_bilgi") or {}
    gerek = [k for k, v in bilgi.items() if k in df.columns
             and any(c not in df.columns for c in v.get("kolonlar") or [])]
    if not gerek:
        return df
    from fe_agent import kolon_cozum as kc
    df = df.copy(deep=False)
    tr = y = None
    for k in gerek:
        v = bilgi[k]
        if v["cozum"] == "metin":
            if tr is None:
                target = (durum.get("meta") or {}).get("target")
                tr = setler(durum, df)["egitim"]
                y = df[target] if target in df.columns else pd.Series(np.nan, index=df.index)
            cikti = kc.metin_uygula(df[k], v["bilgi"], tr, y, kolon=k)
            for c in cikti.columns:
                df[c] = cikti[c]
        elif v["cozum"] == "gun_farki" and v.get("kolonlar"):
            donem = (v.get("bilgi") or {}).get("donem")
            if donem in df.columns:
                df[v["kolonlar"][0]] = kc.gun_farki(df[k], df[donem])
        elif v.get("kolonlar"):
            df[v["kolonlar"][0]] = kc.uygula(v["cozum"], df[k], v["bilgi"])
    return df


def _gun_ozeti(gun):
    """Gun farki kolonunun tek satirlik ozeti (tablonun tamamindan)."""
    if gun is None or not gun.notna().any():
        return "Dönem sonuna gün farkı; değer hesaplanamadı."
    return "Dönem sonuna gün farkı; en küçük %s, en büyük %s gün." % (
        _sayi(int(gun.min())), _sayi(int(gun.max())))


# ===========================================================================
# 02.1 DUZELTMELER: Gizli Eksik, Beklenmeyen Negatif, Uc Deger. Kolon
# uretime girer; secilen duzeltme analiz tablosunda uygulanir (girdi veri
# seti degismez). Gizli eksikte istenirse <KOL>_KOD bayragi uretilir.
# ===========================================================================
# Sifir Yogunlugu ve Ondalik Hassasiyeti kaldirildi: veri hatasi gostermiyor,
# modeli degistirmiyordu (eski kayittaki sonuc ve secimleri yok sayilir).
DUZELTME_KONTROLLERI = ("gizli_eksik", "karisik_eksik", "metin_bos", "yazim",
                        "negatif", "uc")


def _teshis_kusurlu(p):
    t = p.get("profil_teshis") or {}
    return (set(t.get("cok_bos") or []) | set(t.get("sabit") or [])
            | set(t.get("kimlik_gibi") or []) | set(t.get("yuksek_kardinalite") or [])
            | set(t.get("ayni_icerik") or []))


def _duzeltme_ham(ek, kusur):
    """{kontrol: {kolon: {"secenekler", "kural", "kayit"}}}: duzeltme
    secenekleri ve kural onerisi (dil modelinden once)."""
    from fe_agent import kolon_cozum as kc
    cikti = {}
    for a in DUZELTME_KONTROLLERI:
        for x in ek.get(a) or []:
            k = x.get("kolon")
            if not k or k in kusur:
                continue
            kayit, secenek, kural = {}, list(kc.DUZELTME_SECENEK[a]), kc.DUZELTME_ONERI[a]
            if a in KOD_DUZELTMELERI:
                try:
                    kayit["kod"] = float(str(x.get("deger")).replace(",", "."))
                except (TypeError, ValueError):
                    continue
                secenek = _kod_secenekleri(a, x)
                kural = KOD_KURAL_ONERI[a]
            elif a == "yazim":
                kayit["anahtar"] = dict(x.get("anahtar") or {})
            elif a == "uc":
                kayit["yon"] = x.get("yon") or "ust"
                for g in (ek.get("gizli_eksik") or []):
                    if g.get("kolon") == k:
                        try:
                            kayit["kod"] = float(str(g.get("deger")).replace(",", "."))
                        except (TypeError, ValueError):
                            pass
            cikti.setdefault(a, {})[k] = {"secenekler": secenek, "kural": kural, "kayit": kayit}
    return cikti


def duzeltme_onerileri(durum):
    """{kontrol: {kolon: {"secenekler", "oneri", "gerekce", "kayit"}}}.
    Oneri kolon bazinda dil modelinden (p["llm_oneri"]); yoksa kural.
    Uretime girmeyen (kusurlu) kolonlara duzeltme sorulmaz."""
    p = durum.get("profil") or {}
    lo = p.get("llm_oneri") if isinstance(p.get("llm_oneri"), dict) else {}
    cikti = {}
    for a, kolonlar in _duzeltme_ham(p.get("profil_ek") or {}, _teshis_kusurlu(p)).items():
        for k, v in kolonlar.items():
            o = (lo.get(a) or {}).get(k) or {}
            if o.get("kaynak") == "kod" and o.get("oneri") in v["secenekler"]:
                oneri, gerekce = o["oneri"], str(o.get("gerekce") or "")
                kaynak = o["kaynak"]
            else:
                oneri, kaynak = v["kural"], "kural"
                gerekce = KOD_KURAL_GEREKCESI.get(a, "Kural önerisi.")
            cikti.setdefault(a, {})[k] = {"secenekler": v["secenekler"], "oneri": oneri,
                                          "gerekce": gerekce, "kayit": v["kayit"],
                                          "kaynak": kaynak}
    return cikti


# 02.1 KOLON BAZINDA DIL MODELI ONERISI (llm.profil_oneri_sec): Tut / Çıkar
# kararlari, duzeltmeler ve cozumler. p["llm_oneri"] = {kontrol: {kolon:
# {"oneri", "gerekce", "kaynak", "imza"}}}; ayni bulgu ve seceneklerle
# onceden alinmis oneri tekrar sorulmaz. Dil modeline ulasilamazsa kural.
KARAR_KONTROLLERI = ("gelecek_pencere", "birebir", "tarih_sonra", "baskin", "donem",
                     "sicrama", "kayma", "pencere", "tutar_adet")


# ONERI KAYNAGI (karma): kolonun ANLAMINI gerektiren az sayida bulgu dil
# modeline sorulur (ozel kodun anlami, sizinti kontrolleri; ayni icerikli
# gruplar _ayni_gruplari'nda). Gerisini KOD kolonun kendi sayilarina bakarak
# verir (_veri_onerileri, kaynak "kod"); cozumler kolon_cozum testleriyle.
# DIL MODELI 02.1 ONERILERINDE KULLANILMAZ: butun oneriler kural (kolonun
# sayilari ve bulgusu, _veri_onerileri). Eski kayittaki "dil modeli"
# onerileri okunmaz.
LLM_KONTROLLERI = ()
# Baskin deger Tut / Cikar: Cochran kurali (beklenen en az 5 olay), iki oran
# testi (tesadüf olasiligi) ve ayirma gucu (IV en az 0,02).
COCHRAN_EN_AZ = 5
IV_EN_AZ = 0.02
NEGATIF_BOS_PAY = 0.05      # negatif payi bunun altindaysa hatali kayit
METIN_BAYRAK_PAY = 0.05     # bos yazisi payi bunun ustundeyse bayrakla
DONEM_TUT_PAY = 0.35        # yalniz ilk donemler bos ve en cok bu pay: Tut
SICRAMA_CIKAR_PAY = 0.5     # eksik artip bu paya ya da ustune cikti: Çıkar
# Bu sabitler varsayilan; gecerli degerler esik formundan (profil_esikleri).
_KOD_AD_PARCA = {"KOD", "CODE", "CD", "NO", "ID", "KIMLIK", "NUMARA", "NUM"}


def _kat_metni(v):
    v = float(v)
    return _sayi(int(round(v))) if v >= 10 else ("%.1f" % v).replace(".", ",")


def uc_bulgu_metni(x):
    """Uc deger bulgusu: hangi uc, degeri ve sinirlari. Eski kayitta (yalniz
    maks ve p99) ust uc yazilir."""
    p99, maks = float(x["p99"]), float(x["maks"])
    yon = x.get("yon") or "ust"
    parca = []
    if yon in ("ust", "iki"):
        parca.append("en büyük değer %s; oysa satırların %%99'unda değer %s ya da daha küçük"
                     % (_okunur_sayi(maks), _okunur_sayi(p99)))
    if yon in ("alt", "iki") and x.get("en_kucuk") is not None:
        parca.append("en küçük değer %s; oysa satırların %%99'unda değer %s ya da daha büyük" % (
            _okunur_sayi(float(x["en_kucuk"])), _okunur_sayi(float(x["p1"]))))
    m = ". ".join(p[:1].upper() + p[1:] for p in parca)
    return m


def _veri_onerileri(durum, ek, df, egitim):
    """{kontrol: {kolon: {"oneri", "gerekce"}}}: dil modeline sorulmayan
    karar ve duzeltme bulgularinda kolonun kendi sayilarina bakan kural.
    Gerekce sayilarla."""
    m = durum.get("meta") or {}
    hedef = m.get("target")
    cikti = {}
    e = profil_esikleri(durum)
    TESADUF = float(e["tesaduf"])
    DONEM_TUT_PAY, SICRAMA_CIKAR = float(e["donem_tut_pay"]), float(e["sicrama_cikar"])
    NEGATIF_BOS_PAY = float(e["negatif_bos_pay"])
    METIN_BAYRAK_PAY = float(e["metin_bayrak_pay"])

    def yaz(a, k, oneri, gerekce):
        cikti.setdefault(a, {})[k] = {"oneri": oneri, "gerekce": gerekce}

    # NEREDEYSE SABIT: baskin deger disindaki satirlar hedefi ayiriyor mu
    # (egitim satirlari, iki sinifli hedef).
    y, maske = None, None
    if hedef and hedef in df.columns:
        yh = pd.to_numeric(df[hedef], errors="coerce")
        if yh.notna().any() and set(yh.dropna().unique().tolist()) <= {0, 1}:
            maske = yh.notna()
            if egitim is not None:
                maske &= egitim.reindex(df.index).fillna(False).astype(bool)
            y = yh
    for x in ek.get("baskin") or []:
        k = x["kolon"]
        if k not in df.columns:
            continue
        if y is None or not bool(maske.any()):
            yaz("baskin", k, PROFIL_KARAR_TUT, "Hedef yalnız 1 ve 0'dan oluşmadığı için kolonun "
                "işe yarayıp yaramadığı ölçülemedi: Tut.")
            continue
        sx = df.loc[maske, k]
        vc = sx.value_counts(dropna=False)
        ust = vc.index[0]
        bas = sx.isna() if pd.isna(ust) else (sx == ust)
        yy = y[maske]
        n_az, n_bas = int((~bas).sum()), int(bas.sum())
        olay_az, olay_bas = float(yy[~bas].sum()), float(yy[bas].sum())
        genel = (olay_az + olay_bas) / max(n_az + n_bas, 1)
        if n_az == 0 or genel <= 0 or genel >= 1:
            yaz("baskin", k, PROFIL_KARAR_CIKAR, "Eğitim verisinde %s dışında değer yok; kolon "
                "hiçbir şeyi ayırt etmiyor: Çıkar." % x.get("deger"))
            continue
        o_az, o_bas = olay_az / n_az, olay_bas / max(n_bas, 1)
        oranlar = ("Farklı değerdeki %s eğitim satırında hedefi 1 olanların oranı %s; öteki "
                   "satırlarda %s" % (_sayi(n_az), _yuzde_metni(o_az), _yuzde_metni(o_bas)))
        # 1) Cochran: bu satirlarda beklenen hedefi 1 olan satir 5'ten azsa
        #    oran guvenilmez.
        beklenen = n_az * min(genel, 1 - genel)
        if beklenen < COCHRAN_EN_AZ:
            yaz("baskin", k, PROFIL_KARAR_CIKAR, oranlar + ". Bu kadar az satırla güvenilir bir "
                "karşılaştırma yapılamaz (bu satırlarda hedefi %s olan yaklaşık %s satır beklenir, "
                "en az 5 gerekir): Çıkar." % ("1" if genel <= 0.5 else "0",
                                              _sayi_metni(round(beklenen, 1))))
            continue
        # 2) Iki oran testi: fark tesadufen bu kadar buyuk cikabilir mi?
        se = math.sqrt(genel * (1 - genel) * (1.0 / n_az + 1.0 / max(n_bas, 1)))
        z = abs(o_az - o_bas) / se if se > 0 else 0.0
        p = math.erfc(z / math.sqrt(2))
        # 3) Ayirma gucu (IV) iki grupla: en az 0,02.
        B, G = olay_az + olay_bas, (n_az + n_bas) - (olay_az + olay_bas)
        iv = 0.0
        for o, n_ in ((olay_az, n_az), (olay_bas, n_bas)):
            pb, pg = (o + 0.5) / (B + 1.0), (n_ - o + 0.5) / (G + 1.0)
            iv += (pg - pb) * math.log(pg / pb)
        if p < TESADUF and iv >= IV_EN_AZ:
            yaz("baskin", k, PROFIL_KARAR_TUT, oranlar + ". Fark belirgin ve şans eseri olamayacak "
                "kadar büyük (şans eseri olma ihtimali %s): kolon işe yarıyor, Tut." % (
                    _yuzde_metni(p) if p >= 0.0001 else "%0,01'den az"))
        elif p >= TESADUF:
            yaz("baskin", k, PROFIL_KARAR_CIKAR, oranlar + ". Fark şans eseri olabilecek kadar "
                "küçük (şans eseri olma ihtimali %s): kolon bir şey ayırt etmiyor, Çıkar."
                % _yuzde_metni(p))
        else:
            yaz("baskin", k, PROFIL_KARAR_CIKAR, oranlar + ". Fark şans eseri değil ama modele "
                "katkı sağlamayacak kadar küçük: Çıkar.")

    # DONEMDE BOS YA DA SABIT: son donem etkileniyorsa kolon guncel veride
    # yok; yalniz ilk donemlerse kolon sonradan eklenmis.
    D = [str(d) for d in (ek.get("donemler") or [])]
    for x in ek.get("donem") or []:
        P = set(map(str, (x.get("bos") or []) + (x.get("sabit") or [])))
        Ps = [d for d in D if d in P] or sorted(P)
        liste = _donem_listesi(Ps)
        if D and D[-1] in P:
            yaz("donem", x["kolon"], PROFIL_KARAR_CIKAR, "Son dönem (%s) tamamen boş ya da hep "
                "aynı değerde. Kolon güncel veride bilgi taşımıyor; model gerçek kullanımda bu "
                "kolonu boş görür: Çıkar." % D[-1])
        elif D and Ps == D[:len(Ps)] and len(Ps) <= DONEM_TUT_PAY * len(D):
            yaz("donem", x["kolon"], PROFIL_KARAR_TUT, "Yalnız ilk %s dönem (%s) boş ya da hep "
                "aynı değerde. Kolon sonradan eklenmiş, kalan %s dönemde düzgün: Tut." % (
                    _sayi(len(Ps)), liste, _sayi(len(D) - len(Ps))))
        else:
            yaz("donem", x["kolon"], PROFIL_KARAR_CIKAR, "%s dönemin %s tanesi boş ya da hep aynı "
                "değerde (%s). Kolon dönemden döneme tutarsız: Çıkar." % (
                    _sayi(len(D)), _sayi(len(Ps)), liste))

    # EKSIK SICRAMASI
    for x in ek.get("sicrama") or []:
        o1, o2 = float(x["once_oran"]), float(x["sonra_oran"])
        oran = "Boş oranı %s döneminde %s, %s döneminde %s" % (
            x["once"], _yuzde_metni(o1), x["sonra"], _yuzde_metni(o2))
        if o2 > o1 and o2 >= SICRAMA_CIKAR:
            yaz("sicrama", x["kolon"], PROFIL_KARAR_CIKAR, oran + ". Boş oranı %s sınırını geçti; "
                "kolon artık çoğunlukla boş: Çıkar." % _yuzde_metni(SICRAMA_CIKAR))
        elif o2 > o1:
            yaz("sicrama", x["kolon"], PROFIL_KARAR_TUT, oran + ". Boş oranı arttı ama kolonun "
                "çoğu hâlâ dolu: Tut.")
        else:
            yaz("sicrama", x["kolon"], PROFIL_KARAR_TUT, oran + ". Boş oranı azaldı, veri "
                "iyileşmiş: Tut.")

    # DEGER KAYMASI: kat 10'un kuvvetine yakinsa birim degisikligi.
    for x in ek.get("kayma") or []:
        kat = float(x["kat"])
        us = math.log10(kat) if kat > 0 else 0.0
        yakin = round(us)
        med = "Ortadaki değer %s döneminde %s, %s döneminde %s" % (
            x["once"], _okunur_sayi(x["once_deger"]), x["sonra"], _okunur_sayi(x["sonra_deger"]))
        if yakin >= 1 and abs(us - yakin) <= 0.05:
            yaz("kayma", x["kolon"], PROFIL_KARAR_CIKAR, med + ": yaklaşık %s kat. Böyle yuvarlak "
                "bir kat çoğu zaman birim değişikliğidir (TL yerine bin TL gibi); eski ve yeni "
                "dönem aynı ölçüde değil: Çıkar." % _sayi(10 ** yakin))
        else:
            yaz("kayma", x["kolon"], PROFIL_KARAR_TUT, med + ": %s kat. Yuvarlak bir kat değil, "
                "gerçek bir değişim olabilir: Tut." % _kat_metni(kat))

    # UC DEGER
    # Yakalanan uc zaten dogal yayilimin cok disinda (hatali giris): kirp.
    for x in ek.get("uc") or []:
        yaz("uc", x["kolon"], "kirp", uc_bulgu_metni(x) + ". Yanlış yazılmış bir sayıya "
            "benziyor; normal aralığın ucuna çekilir.")

    # BEKLENMEYEN NEGATIF
    for x in ek.get("negatif") or []:
        k = x["kolon"]
        dolu = int(pd.to_numeric(df[k], errors="coerce").notna().sum()) if k in df.columns else 0
        pay = x["adet"] / max(dolu, 1)
        bas = "Ölçü %s; eksi değerli %s satır var (dolu satırların %s), en küçüğü %s" % (
            x.get("olcu"), _sayi(x["adet"]), _yuzde_metni(pay), _okunur_sayi(x["en_kucuk"]))
        if pay < NEGATIF_BOS_PAY:
            yaz("negatif", k, "negatif_bos", bas + ". Az sayıda, yanlış kayıt gibi: boş sayılır.")
        else:
            yaz("negatif", k, "birak", bas + ". Az değil, bir anlamı olabilir (iade ya da "
                "düzeltme kaydı gibi): olduğu gibi bırakılır.")

    # METIN OLARAK YAZILMIS BOS
    for x in ek.get("metin_bos") or []:
        ornek = ", ".join("«%s»" % d["deger"] for d in (x.get("degerler") or [])[:3])
        bas = "«Bilgi yok» anlamındaki yazılar (%s) %s satırda, dolu satırların %s" % (
            ornek, _sayi(x["adet"]), _yuzde_metni(x["pay"]))
        if x["pay"] >= METIN_BAYRAK_PAY:
            yaz("metin_bos", x["kolon"], "metin_bos_bayrak", bas + ". Sık geçiyor: boş sayılır ve "
                "«boş mu, dolu mu» gösteren 1/0 kolonu da üretilir.")
        else:
            yaz("metin_bos", x["kolon"], "metin_bos", bas + ". Az: yalnız boş sayılır.")

    # YAZIM TUTARSIZLIGI
    for x in ek.get("yazim") or []:
        g = (x.get("gruplar") or [{}])[0]
        ornek = ", ".join("«%s»" % y_["deger"] for y_ in (g.get("yazimlar") or [])[:3])
        yaz("yazim", x["kolon"], "tek_yazim", "%s değer farklı biçimlerde yazılmış, %s satırda "
            "(ör. %s). Hepsi tek yazıma çevrilir." % (_sayi(x.get("grup") or 0), _sayi(x.get("satir") or 0),
                                                ornek))

    # SIZINTI: gelecek penceresi ve donemden sonraki tarih Çıkar; hedefle
    # birebir ayirma gucune gore (neredeyse kusursuzsa Çıkar).
    for x in ek.get("gelecek_pencere") or []:
        yaz("gelecek_pencere", x["kolon"], PROFIL_KARAR_CIKAR,
            "Kolonun adı gelecekteki bir dönemi anlatıyor. Tahmin anında gelecek bilinmez: "
            "Çıkar.")
    for x in ek.get("tarih_sonra") or []:
        yaz("tarih_sonra", x["kolon"], PROFIL_KARAR_CIKAR,
            "Satırın döneminden sonraki bir tarih var; tahmin anında bilinmeyen bir bilgi "
            "olabilir: Çıkar. Tarih doğal olarak ilerideyse (vade tarihi gibi) Tut seçin.")
    for x in ek.get("birebir") or []:
        auc = float(x.get("auc") or 0)
        if auc >= SIZINTI_CIKAR_AUC:
            yaz("birebir", x["kolon"], PROFIL_KARAR_CIKAR,
                "Kolon tek başına hedefi %s isabetle biliyor: neredeyse hiç yanılmıyor. Büyük "
                "ihtimalle sonuç belli olduktan sonra doldurulmuş: Çıkar." % _yuzde_metni(auc))
        else:
            yaz("birebir", x["kolon"], PROFIL_KARAR_TUT,
                "Kolon tek başına hedefi %s isabetle biliyor: çok iyi ama kusursuz değil, "
                "gerçekten güçlü bir kolon olabilir: Tut. Tahmin anında bilindiğini kontrol edin."
                % _yuzde_metni(auc))
    # CELISEN KOLON CIFTI (pencere tutarliligi, tutar ve adet): hangi kolonun
    # yanlis oldugu veriden anlasilamaz. Birden fazla kolonla celisen kolon
    # ortak nokta oldugu icin Çıkar; tek kolonla celisen Tut (kullanici
    # tanima bakip karar verir).
    for a_ in ("pencere", "tutar_adet"):
        cift = {}
        for x in ek.get(a_) or []:
            cift.setdefault(x["kolon"], []).append(x)
        for k, xs in cift.items():
            karsi = sorted({x["karsi"] for x in xs})
            enb = max(xs, key=lambda x: x["pay"])
            if len(karsi) >= 2:
                yaz(a_, k, PROFIL_KARAR_CIKAR, "%s ayrı kolonla çelişiyor (%s). Birden fazla "
                    "kolonla çelişen kolon büyük ihtimalle yanlış olandır: Çıkar." % (
                        _sayi(len(karsi)), ", ".join(karsi[:4])))
            else:
                yaz(a_, k, PROFIL_KARAR_TUT, "%s kolonuyla %s satırda (%s) çelişiyor. İkisinden "
                    "hangisinin yanlış olduğu veriden anlaşılamıyor: Tut. İki kolonun nasıl "
                    "hesaplandığına bakın; yanlış olanı Çıkar seçin." % (
                        karsi[0], _sayi(enb["adet"]), _yuzde_metni(enb["pay"])))
    # OZEL KOD: kod bos sayilir, bilgi bayrakta.
    for a_ in ("gizli_eksik", "karisik_eksik"):
        for x in ek.get(a_) or []:
            yaz(a_, x["kolon"], "kod_bos_bayrak", "%s «bilgi yok» anlamında yazılmış: boş "
                "sayılır; hangi satırlarda yazdığı ayrı bir 1/0 kolonunda (_KOD) saklanır."
                % x.get("deger"))
    return cikti


KARAR_KURAL_GEREKCESI = {
    "cikar": "Sızıntı kontrolü: kural önerisi Çıkar.",
    "tut": "Kural önerisi Tut.",
}


def _karar_kurali(a):
    return PROFIL_KARAR_CIKAR if a in KARAR_VARSAYILAN_CIKAR else PROFIL_KARAR_TUT


def _profil_llm_onerileri(durum, p, ek, teshis):
    from fe_agent import kolon_cozum as kc
    onceki = p.get("llm_oneri") if isinstance(p.get("llm_oneri"), dict) else {}
    aciklama = _aciklamalar(durum)
    olcu = _kart_olculeri(durum)
    ozet = {str(o.get("ad")): o for o in (p.get("kolon_ozet") or []) if isinstance(o, dict)}
    kad = {x[0]: x[1] for x in PROFIL_KONTROLLERI}
    bulgu = _ek_bulgulari(p, ek=ek, kopya_suz=False)
    kusur = (set(teshis.get("cok_bos") or []) | set(teshis.get("sabit") or [])
             | set(teshis.get("kimlik_gibi") or []) | set(teshis.get("yuksek_kardinalite") or []))
    ogeler = []      # (kontrol, kolon, oge)

    veri = p.get("veri_oneri") if isinstance(p.get("veri_oneri"), dict) else {}
    kodlu = {}

    def ekle(a, k, metin, secenek, kural, kural_gerekce=""):
        if len(secenek) < 2:
            return
        if a not in LLM_KONTROLLERI:
            # Kod onerisi (kolonun sayilari); dil modeline sorulmaz.
            v = (veri.get(a) or {}).get(k)
            if v and v["oneri"] in secenek:
                kodlu.setdefault(a, {})[k] = {"oneri": v["oneri"], "gerekce": v["gerekce"],
                                              "kaynak": "kod"}
            return
        sec = [{"kod": c, "ad": kc.COZUM_ADI.get(c, {"tut": "Tut", "cikar": "Çıkar"}.get(c, c)),
                "aciklama": kc.COZUM_ACIKLAMA.get(c, {"tut": "Kolon üretime girer.",
                                                       "cikar": "Kolon üretime girmez."}.get(c, ""))}
               for c in secenek]
        o = ozet.get(k) or {}
        ogeler.append((a, k, {
            "id": "%s|%s" % (a, k), "kontrol_kodu": a, "kontrol": kad.get(a, a), "kolon": k,
            "aciklama": aciklama.get(k, ""), "olcu": olcu.get(k, ""), "tip": o.get("tip") or "",
            "bos_orani": (_yuzde_metni(o["null_oran"]) if o.get("null_oran") is not None else ""),
            "bulgu": (metin + ((". " + kural_gerekce) if kural_gerekce else "")).strip(),
            "secenekler": sec, "kural": kural}))
    for a in KARAR_KONTROLLERI:
        for k, metin in (bulgu.get(a) or {}).items():
            ekle(a, k, metin, [PROFIL_KARAR_TUT, PROFIL_KARAR_CIKAR], _karar_kurali(a))
    for a, kolonlar in _duzeltme_ham(ek, kusur).items():
        for k, v in kolonlar.items():
            ekle(a, k, (bulgu.get(a) or {}).get(k, ""), v["secenekler"], v["kural"])
    # Cozumler dil modeline sorulmaz: oneri kolon_cozum testlerinden (kod).
    cikti, sorulacak = {}, []
    for a, k, oge in ogeler:
        imza = json.dumps([oge["bulgu"], [x["kod"] for x in oge["secenekler"]], oge["aciklama"],
                           oge["kural"]], ensure_ascii=False)
        o = (onceki.get(a) or {}).get(k) or {}
        if o.get("kaynak") == "dil modeli" and o.get("imza") == imza:
            cikti.setdefault(a, {})[k] = o
        else:
            sorulacak.append((a, k, imza, oge))
    oneri = {}
    if sorulacak:
        try:
            from fe_agent import llm as llm_mod
            oneri, _hata = llm_mod.profil_oneri_sec([q[3] for q in sorulacak])
        except Exception:       # dil modeli yoksa kural gecerli
            oneri = {}
    p["llm_oneri_sayim"] = {"oge": len(ogeler), "sorulan": len(sorulacak),
                            "alinan": len(oneri), "onbellek": len(ogeler) - len(sorulacak),
                            "kod": sum(len(x) for x in kodlu.values())}
    for a, x in kodlu.items():
        cikti.setdefault(a, {}).update(x)
    for a, k, imza, oge in sorulacak:
        o = oneri.get(oge["id"])
        if o:
            cikti.setdefault(a, {})[k] = {"oneri": o["secim"], "gerekce": o.get("gerekce", ""),
                                          "kaynak": "dil modeli", "imza": imza}
        else:
            cikti.setdefault(a, {})[k] = {"oneri": oge["kural"], "gerekce": "", "kaynak": "kural",
                                          "imza": imza}
    return cikti


# OZEL KOD DUZELTMESI (Gizli Eksik, Karisik Eksik): oneriyi dil modeli
# kolonun anlamina bakip verir (kodu veriyi hazirlayan bilerek koymus
# olabilir). Dil modeline ulasilamazsa kural: gizli eksikte kodu bos say ve
# bayrak, karisik eksikte olduğu gibi birak (bos ile kodun ayni anlama
# geldigi bilinmeden deger degistirilmez).
KOD_DUZELTMELERI = ("gizli_eksik", "karisik_eksik")
KOD_KURAL_ONERI = {"gizli_eksik": "kod_bos_bayrak", "karisik_eksik": "kod_bos_bayrak"}
KOD_KURAL_GEREKCESI = {
    "gizli_eksik": "Kod boş sayılır; kodun olduğu satırlar _KOD bayrağında kalır, bilgi kaybolmaz.",
    "karisik_eksik": "Eksik bilgi iki biçimde yazılmış; kod boş sayılır, kodun olduğu satırlar "
                     "_KOD bayrağında kalır (kod ile boşun farkı bilgi taşıyorsa kaybolmaz).",
}


def _kod_secenekleri(kontrol, x):
    """Kolonun duzeltme secenekleri: bos hucresi varsa "bos_koda" da."""
    from fe_agent import kolon_cozum as kc
    sec = list(kc.DUZELTME_SECENEK[kontrol])
    if x.get("bos") and "bos_koda" not in sec:
        sec.insert(sec.index("birak") if "birak" in sec else len(sec), "bos_koda")
    return sec


def duzeltme_secimi(durum):
    p = durum.get("profil") or {}
    sec = p.get("duzeltme_secim") if isinstance(p.get("duzeltme_secim"), dict) else {}
    return {a: {k: ((sec.get(a) or {}).get(k) if (sec.get(a) or {}).get(k) in v["secenekler"]
                    else v["oneri"]) for k, v in kolonlar.items()}
            for a, kolonlar in duzeltme_onerileri(durum).items()}


def _duzeltme_ogren(durum, df, tr, mevcut):
    """Secilen duzeltmeleri egitimden ogrenir; p["duzeltme_bilgi"]. Doner:
    uretilen bayrak kolonlari."""
    from fe_agent import kolon_cozum as kc
    p = durum.get("profil") or {}
    oneri = duzeltme_onerileri(durum)
    bilgi_hepsi, yeni = {}, []
    for a, kolonlar in duzeltme_secimi(durum).items():
        for k, c in kolonlar.items():
            if c == "birak" or k not in df.columns:
                continue
            b = kc.duzeltme_ogren(a, c, df[k], tr, (oneri[a][k] or {}).get("kayit"))
            kol = []
            if c in kc.BAYRAKLI_DUZELTME:
                ad = kc.yeni_kolon_adi(k, c, mevcut)
                kol = [ad]
                mevcut.add(ad)
            bilgi_hepsi.setdefault(a, {})[k] = {"secim": c, "bilgi": _json_uyumlu(b),
                                                "kolonlar": kol,
                                                "ozet": _duzeltme_ozeti(a, c, b)}
            yeni += kol
    # Tam sayiya cevrilecek kolonda ozel kod bos yapildiysa (ya da negatif
    # bos yapildiysa) bos hucre olusur: kolon ondalik tipte kalir.
    bos_yapan = {k for a_ in ("gizli_eksik", "karisik_eksik", "negatif")
                 for k, v in (bilgi_hepsi.get(a_) or {}).items()
                 if v.get("secim") in ("kod_bos", "kod_bos_bayrak", "negatif_bos")}
    p["duzeltme_bilgi"] = bilgi_hepsi
    return yeni


def _duzeltme_ozeti(kontrol, secim, b):
    if kontrol in ("gizli_eksik", "karisik_eksik") and secim == "bos_koda" and "kod" in b:
        return "Boş hücreler kod %s ile doldurulur." % _sayi_metni(b["kod"])
    if kontrol in ("gizli_eksik", "karisik_eksik") and "kod" in b:
        return "Kod %s boş sayılır." % _sayi_metni(b["kod"])
    if kontrol == "negatif":
        return "Negatif değerler boş sayılır."
    if kontrol == "tarih_kod":
        return "Kod tarihler boş sayılır."
    if kontrol == "metin_bos":
        return "Boş anlamına gelen yazılar boş hücreye çevrilir."
    if kontrol == "ondalik" and secim == "tam_sayi":
        return "Tam sayı tipine çevrilir."
    if kontrol == "ondalik" and secim == "yuvarla":
        return "%s basamağa yuvarlanır." % _sayi(b.get("basamak") or 0)
    if kontrol == "yazim" and b.get("anahtar"):
        return "%s değerin farklı yazımları tek yazıma çevrilir." % _sayi(len(b["anahtar"]))
    if kontrol == "uc" and any(x in b for x in ("ust", "alt", "sinir")):
        p = []
        if b.get("ust", b.get("sinir")) is not None:
            p.append("üst sınır %s" % _sayi_metni(b.get("ust", b.get("sinir"))))
        if b.get("alt") is not None:
            p.append("alt sınır %s" % _sayi_metni(b["alt"]))
        m = ", ".join(p)
        return m[:1].upper() + m[1:] + "; dışındaki değerler sınıra çekilir."
    return ""


def _duzeltmeleri_uygula(durum, df):
    """Secilen duzeltmeleri df'e uygular (kopya). Bayrak kolonu yoksa ham
    degerden hesaplanir; duzeltme tekrar uygulansa da sonuc ayni."""
    db = (durum.get("profil") or {}).get("duzeltme_bilgi") or {}
    if not db:
        return df
    from fe_agent import kolon_cozum as kc
    df = df.copy(deep=False)
    for a in kc.DUZELTME_SIRA:
        for k, v in (db.get(a) or {}).items():
            if k not in df.columns:
                continue
            yeni, bayrak = kc.duzeltme_uygula(a, v["secim"], df[k], v.get("bilgi") or {})
            for ad in v.get("kolonlar") or []:
                if bayrak is not None and ad not in df.columns:
                    df[ad] = bayrak
            df[k] = yeni
    return df


# ===========================================================================
# 02.1 SATIR CIKARMA: Tekrar Eden Satir ve Setler Arasi Cakisma kurallari
# bilgi icin gosterilmez; fazla / cakisan satirlar CALISMA TABLOSUNDAN
# (UPDT veri, 02.1 sonu) cikarilir. Girdi verisi degismez; uretim kodu
# satir silmez (skorlamada satir sayisi degismemeli). Secim Kararlar
# sekmesinde, duzeltmelerle ayni bicimde: {kontrol: {oge adi: kod}}.
# Sira: once setler arasi cakisma (Train'e dokunulmaz), sonra kalan
# satirlarda tekrar.
# ===========================================================================
SATIR_KONTROLLERI = ("set_cakisma", "tekrar")
KURAL_SONUC_ADI = {"tekrar": "Düzeltme önerilir: fazla satırlar çıkar",
                   "set_cakisma": "Düzeltme önerilir: çakışan satırlar Test / OOT'den çıkar"}


def _tekrar_ogeleri(ek):
    """[(oge adi, tur, fazla satir)]: birebir ayni satirlar ve ayni kimlik
    (ve donem) icin icerigi farkli satirlar (ayrik sayim)."""
    tk = ek.get("tekrar") or {}
    tam, toplam = int(tk.get("tam") or 0), int(tk.get("toplam") or 0)
    cikti = []
    if tam:
        cikti.append(("Bütün kolonları aynı satır", "tam", tam))
    if tk.get("kimlik") and toplam - tam > 0:
        cikti.append(("Aynı %s, içeriği farklı" % " ve ".join(tk.get("anahtar") or []),
                      "anahtar", toplam - tam))
    return cikti


def _set_oge_adi(x, b):
    from fe_agent.akis_durum import set_basligi
    return "%s: %s" % (set_basligi(x["set"], (b or {}).get("test_tanim")), SET_TUR_ADI[x["tur"]])


def satir_onerileri(durum):
    """{kontrol: {oge adi: {"secenekler", "oneri", "gerekce", "kaynak",
    "kayit"}}}: satir cikarma secenekleri ve kural onerisi. Yalniz yeni
    duzende (UPDT veri); eski duzende satir cikarilmaz."""
    p = durum.get("profil") or {}
    ek = p.get("profil_ek") or {}
    if not updt_modu(durum) or not ek:
        return {}
    cikti = {}
    for ad, tur, n in _tekrar_ogeleri(ek):
        if tur == "tam":
            cikti.setdefault("tekrar", {})[ad] = {
                "secenekler": ["kopya_kaldir", "birak"], "oneri": "kopya_kaldir", "kaynak": "satir",
                "gerekce": "%s fazla satır başka bir satırın birebir aynısı. Biri kalır, fazlası "
                           "çıkar; içerik aynı olduğu için bilgi kaybı olmaz." % _sayi(n),
                "kayit": {"tur": tur}}
        else:
            cikti.setdefault("tekrar", {})[ad] = {
                "secenekler": ["ilk_tut", "birak"], "oneri": "ilk_tut", "kaynak": "satir",
                "gerekce": "%s fazla satırda aynı kayıt için farklı içerik var. Hangisinin doğru "
                           "olduğu veriden anlaşılamaz; tablodaki ilk satır kalır, ötekiler çıkar. "
                           "Çok satır etkileniyorsa veri hazırlığında birleştirme hatası olabilir."
                           % _sayi(n),
                "kayit": {"tur": tur}}
    sc = ek.get("set_cakisma") or {}
    for x in sc.get("cakisma") or []:
        if x["tur"] not in ("anahtar", "tam"):
            continue
        cikti.setdefault("set_cakisma", {})[_set_oge_adi(x, ek.get("set_bolme"))] = {
            "secenekler": ["satir_cikar", "birak"], "oneri": "satir_cikar", "kaynak": "satir",
            "gerekce": "%s satır Train'deki bir kaydın aynısı. Bu setten çıkarılırsa model "
                       "sınamada daha önce gördüğü kayıtla karşılaşmaz; Train'e dokunulmaz."
                       % _sayi(x["satir"]),
            "kayit": {"set": x["set"], "tur": x["tur"]}}
    return cikti


def satir_secimi(durum):
    """{kontrol: {oge adi: kod}}: kullanicinin secimi, yoksa oneri."""
    p = durum.get("profil") or {}
    sec = p.get("satir_secim") if isinstance(p.get("satir_secim"), dict) else {}
    return {a: {k: ((sec.get(a) or {}).get(k) if (sec.get(a) or {}).get(k) in v["secenekler"]
                    else v["oneri"]) for k, v in ogeler.items()}
            for a, ogeler in satir_onerileri(durum).items()}


def satir_cikarma_var(durum):
    return any(c != "birak" for a in satir_secimi(durum).values() for c in a.values())


def satir_cikar_maskesi(durum, df):
    """(cikacak satirlarin maskesi (numpy bool), {oge adi: cikan satir}).
    Once setler arasi cakisma, sonra KALAN satirlarda tekrar (boylece
    Train'deki satir yerinde kalir)."""
    from fe_agent import profil_ek
    oneri, secim = satir_onerileri(durum), satir_secimi(durum)
    m = durum.get("meta") or {}
    cik = np.zeros(len(df), dtype=bool)
    say = {}
    sc = {ad: oneri["set_cakisma"][ad]["kayit"] for ad, c in (secim.get("set_cakisma") or {}).items()
          if c == "satir_cikar"}
    if sc:
        mk = profil_ek.set_cakisma_maskeleri(df, setler(durum, df), m.get("id"), m.get("donem"),
                                             haric={SPLIT_KOLON})
        for ad, kayit in sc.items():
            x = mk.get((kayit["set"], kayit["tur"]))
            if x is None:
                continue
            x = x.to_numpy(dtype=bool) & ~cik
            say[ad] = int(x.sum())
            cik |= x
    tk = {ad: oneri["tekrar"][ad]["kayit"]["tur"] for ad, c in (secim.get("tekrar") or {}).items()
          if c != "birak"}
    if tk:
        kalan = np.flatnonzero(~cik)
        tm = profil_ek.tekrar_maskeleri(df.iloc[kalan], m.get("id"), m.get("donem"),
                                        haric={SPLIT_KOLON})
        for ad, tur in tk.items():
            if tur not in tm:
                continue
            x = np.zeros(len(df), dtype=bool)
            x[kalan[tm[tur].to_numpy(dtype=bool)]] = True
            x &= ~cik
            say[ad] = int(x.sum())
            cik |= x
    return cik, say


def satir_kararlarini_uygula(durum, df, kaydet=False):
    """Secilen satir cikarma kararlarini df'e (01 sonu tablo) uygular.
    kaydet=True: cikan satir sayilari p["satir_bilgi"]'ye yazilir."""
    if not updt_modu(durum) or not satir_cikarma_var(durum):
        if kaydet:
            (durum.get("profil") or {}).pop("satir_bilgi", None)
        return df
    cik, say = satir_cikar_maskesi(durum, df)
    if kaydet:
        (durum.get("profil") or {})["satir_bilgi"] = {
            "cikan": say, "toplam": int(cik.sum()), "once": int(len(df)),
            "sonra": int(len(df) - cik.sum())}
    if not cik.any():
        return df
    return df.loc[~cik].reset_index(drop=True)


def _satir_duzeltme(durum, kontrol, ad):
    """Kart satirinin duzeltme alani (satir cikarma secimi) ya da None."""
    o = (satir_onerileri(durum).get(kontrol) or {}).get(ad)
    if not o:
        return None
    c = _duzeltme_satiri(o, satir_secimi(durum)[kontrol][ad], None)
    for sec in c["secenekler"]:
        if sec["kod"] == "birak":
            sec["aciklama"] = "Satırlara dokunulmaz; tablo olduğu gibi kalır."
    b = ((durum.get("profil") or {}).get("satir_bilgi") or {}).get("cikan") or {}
    if ad in b and c["secim"] != "birak":
        c["ozet_kisa"] = c["ozet"] = "%s satır çalışma tablosundan çıkarıldı." % _sayi(b[ad])
    return c


# ===========================================================================
# 02.1 YENI KOLONLARIN SOZLUK SATIRLARI: cozum kolonlari (gruplama, dolu
# bayragi, metinden ozellik, gun farki) ve duzeltme bayraklari (_KOD,
# _BOS) UPDT sozluge eklenir. Satirlar 02.1 onayinda UPDT veri yazilirken
# kurulur (bos orani yazilan tablodan, kesin); p["sozluk_ek"].
# ===========================================================================
SOZLUK_EK_KAYNAK = "02.1 Veri Profili ve Kalite adımında üretildi"


def _yeni_kolon_aciklamasi(kolon, kaynak, kaynak_tanim, cozum, ozet, bilgi):
    """Yeni kolonun sozluk aciklamasi (duz Turkce, tek paragraf)."""
    from fe_agent import kolon_cozum as kc
    ref = "%s kolonu" % kaynak + ((" (%s)" % kaynak_tanim.rstrip(".")) if kaynak_tanim else "")
    if cozum == "gun_farki":
        return ("%s ile satırın dönem sonu arasındaki gün sayısı: dönem sonu eksi tarih. "
                "Geçmişteki tarih pozitif, gelecekteki tarih negatif; kod tarihlerde boş."
                % ref)
    if cozum == "dolu_bayrak":
        return "%s dolu ise 1, boş ise 0." % ref
    if cozum in ("hedef_grupla", "seyrek_grupla", "onek_grupla"):
        return "%s değerlerinin gruplanmış hali (%s). %s" % (
            ref, kc.COZUM_ADI.get(cozum, cozum).lower(), ozet or "")
    if cozum == "metin":
        if kolon.endswith("_SOZCUK"):
            return "%s metnindeki sözcük sayısı." % ref
        if kolon.endswith("_SKOR"):
            return ("%s metnindeki sözcüklerin hedefle ilişkisinden hesaplanan skor (eğitim "
                    "satırlarından öğrenildi)." % ref)
        if kolon.endswith("_KONU"):
            return "%s metninin konusu (birlikte geçen sözcüklerden çıkarılan konu grubu)." % ref
        if "_K_" in kolon:
            ek = kolon.split("_K_", 1)[1].rstrip("_")
            soz = next((str(b_.get("sozcuk")) for b_ in (bilgi or {}).get("bayrak") or []
                        if isinstance(b_, dict) and kc._sozcuk_kolon_eki(str(b_.get("sozcuk"))) == ek),
                       ek.lower())
            return "%s metninde hedefle ilişkili «%s» sözcüğü geçiyorsa 1, geçmiyorsa 0." % (
                ref, soz)
        return "%s metninden üretilen özellik." % ref
    if cozum == "kod_bos_bayrak":
        return "%s özel kod %s ise 1, değilse 0 (kod veride boş sayıldı)." % (
            ref, _sayi_metni((bilgi or {}).get("kod")) if (bilgi or {}).get("kod") is not None
            else "")
    if cozum == "metin_bos_bayrak":
        return ("%s boş anlamına gelen bir yazı (NULL, «-», «?» gibi) taşıyorsa 1, değilse 0 "
                "(yazı veride boş hücreye çevrildi)." % ref)
    return "%s kolonundan üretildi." % ref


def _sozluk_tip(s):
    if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
        return "sayısal"
    return "kategorik"


# Uretilen kolonun tipi veri okunmadan: bayraklar, gun farki, sozcuk sayisi
# ve skor sayisal; gruplama ve konu kategorik.
_SAYISAL_COZUM = ("kod_bos_bayrak", "metin_bos_bayrak", "tarih_bos_bayrak", "dolu_bayrak",
                  "gun_farki")


def yeni_kolon_sozlugu(durum, df=None):
    """[{"DEGISKEN", "TIP", "ACIKLAMA", "NULL_ORANI", "KAYNAK_KOLON"}]: 02.1'de
    uretilip `df`'te (UPDT veri) bulunan yeni kolonlar. df verilmezse (eski
    oturumda 02.1 onayinda kaydedilmemis satirlar) tip kolondan tahmin
    edilir, bos orani yazilmaz."""
    p = durum.get("profil") or {}
    tanim = _aciklamalar(durum)
    satirlar, gor = [], set()

    def ekle(kolon, kaynak, cozum, ozet, bilgi):
        if kolon in gor or (df is not None and kolon not in df.columns):
            return
        gor.add(kolon)
        if df is not None:
            tip = _sozluk_tip(df[kolon])
            bos = round(float(df[kolon].isna().mean()), 4) if len(df) else 0.0
        else:
            sayisal = cozum in _SAYISAL_COZUM or str(kolon).endswith(("_SOZCUK", "_SKOR")) \
                or "_K_" in str(kolon)
            tip = "sayısal" if sayisal else "kategorik"
            bos = 0.0 if cozum in _SAYISAL_COZUM and cozum != "gun_farki" else None
        satirlar.append({
            "DEGISKEN": kolon, "TIP": tip,
            "ACIKLAMA": _yeni_kolon_aciklamasi(kolon, kaynak, str(tanim.get(kaynak) or ""),
                                               cozum, ozet, bilgi).strip(),
            "NULL_ORANI": bos, "KAYNAK_KOLON": kaynak})
    for k, v in (p.get("cozum_bilgi") or {}).items():
        for c in v.get("kolonlar") or []:
            ekle(c, k, v.get("cozum"), v.get("ozet") or "", v.get("bilgi"))
    for _a, kolonlar in (p.get("duzeltme_bilgi") or {}).items():
        for k, v in kolonlar.items():
            for c in v.get("kolonlar") or []:
                ekle(c, k, v.get("secim"), v.get("ozet") or "", v.get("bilgi"))
    return satirlar

def uretim_kolonlari(durum):
    """Kural / kesif adimlarinin urettigi kolonlar (cozum kolonlari haric)."""
    cozum = set(((durum.get("uretilen_kaynak") or {}).get(COZUM_KAYNAK)) or [])
    return [k for k in uretilenler(durum) if k not in cozum]


def uretilenler(durum):
    return [str(x) for x in (durum.get("uretilen") or []) if x]


def zengin_adi(durum):
    return "%s_ENRICHED" % durum.get("veri_seti")


# ===========================================================================
# UPDT VERI ASAMALARI (yeni duzen; bkz. amp.py DORT TABLO)
# ---------------------------------------------------------------------------
# UPDT veri her adimda ilerler; durum["updt_asama"] tablonun su an hangi
# adimin sonundaki hali oldugunu soyler:
#   "01.3" teyit (tip, dusen, yeni ad)   "01"   + _SPLIT (01.4)
#   "02.1" + duzeltmeler ve cozum kolonlari
#   "02.2" + kural tabanli uretim        "02.3" + yapay zeka kesfi
#   "03.3" analitik baz set (dusenler cikar, SFA kararlari, doldurma)
# Bir adim ONCEKI asamanin tablosunu ister (asama_df). UPDT zaten o
# asamadaysa (ya da aradaki adimlar bir sey katmadiysa) UPDT okunur; geri
# donulmus ve UPDT ileride kalmissa tablo BAZ veriden kararlar yeniden
# uygulanarak kurulur (girdi verisi hic degismez, karar durumda saklidir).
# Eski calismalar (AMP_VERISETI, _ENRICHED) eski yolla calisir.
# ===========================================================================
UPDT_ASAMALARI = ("01.3", "01", "02.1", "02.2", "02.3", "03.3")
_ASAMA_ONBELLEK = {}
ASAMA_ONBELLEK_SN = 600


def updt_modu(durum):
    """Calisma yeni duzende mi: modelleme tablosu <EK>_UPDT_VERI."""
    k = ((durum or {}).get("amp_cikti") or {}).get("veri") or {}
    return bool(k.get("dataset")) and k.get("istek") is not None \
        and str(k["dataset"]).endswith("_UPDT_VERI")


def updt_adi(durum):
    return ((durum.get("amp_cikti") or {}).get("veri") or {}).get("dataset")


def _asama_katkisi(durum, asama):
    """Asama UPDT veriye bir sey katar mi?"""
    if asama == "02.1":
        p = durum.get("profil") or {}
        return bool(p.get("cozum_bilgi")) or any(
            v for v in (p.get("duzeltme_bilgi") or {}).values()) \
            or bool(set(kusurlu_kolonlar(durum)) - _meta_kolonlar(durum)) \
            or satir_cikarma_var(durum)
    if asama in ("02.2", "02.3"):
        from fe_agent.akis_faz03 import KURAL_KAYNAK, KESIF_KAYNAK
        kaynak = KURAL_KAYNAK if asama == "02.2" else KESIF_KAYNAK
        return any(len(b) > 2 and b[2] == kaynak and b[1]
                   for b in durum.get("kod_bloklari") or [])
    return True


def _asama_imzasi(durum, asama):
    import hashlib
    import json as _json
    kayit = (durum.get("amp_cikti") or {}).get("veri") or {}
    p = durum.get("profil") or {}
    parca = [asama, durum.get("updt_asama"), kayit.get("istek"), kayit.get("bolme_tarif"),
             (durum.get("meta") or {}).get("segment"), p.get("cozum_bilgi"),
             p.get("duzeltme_bilgi"), durum.get("kod_bloklari"), kusurlu_kolonlar(durum),
             satir_secimi(durum)]
    return hashlib.md5(_json.dumps(parca, sort_keys=True, default=str)
                       .encode("utf-8")).hexdigest()


def _updt_01_kur(durum):
    """01 sonu: BAZ veri + teyit istegi + bolme (01.4) - UPDT'nin 01.4
    sonrasi hali, BAZ'dan yeniden."""
    from fe_agent import amp_pandas
    from fe_agent.akis_durum import AdimHatasi
    kayit = (durum.get("amp_cikti") or {}).get("veri") or {}
    istek = dict(kayit.get("istek") or {})
    if kayit.get("bolme_tarif"):
        istek.update(bolme=kayit["bolme_tarif"],
                     segment=(durum.get("meta") or {}).get("segment"))
    tablo, sonuc = amp_pandas.amp_hazirla(_df_oku(kayit.get("kaynak"), onbellek=False), istek)
    if sonuc.get("hata"):
        raise AdimHatasi(sonuc["hata"])
    return tablo


def _kod_bloklarini_uygula(durum, df, kaynak):
    """02.2 / 02.3 kod satirlari (uretim_kodu.py'deki satirlarin aynisi)
    df'e uygulanir. Sonsuz degerler bos sayilir."""
    def _s(d, kol):
        return pd.to_numeric(d[kol], errors="coerce")

    def _bol(a, b):
        if isinstance(b, pd.Series):
            b = b.replace(0, np.nan)
        elif b == 0:
            return np.nan
        return a / b
    df = df.copy()
    ortam = {"np": np, "pd": pd, "_s": _s, "_bol": _bol, "df": df}
    for b in durum.get("kod_bloklari") or []:
        if len(b) < 3 or b[2] != kaynak:
            continue
        for satir in b[1] or []:
            ad, kod = satir[0], satir[1]
            try:
                exec(kod, ortam)              # pylint: disable=exec-used
            except Exception:                 # pylint: disable=broad-except
                continue
            if ad in df.columns and pd.api.types.is_numeric_dtype(df[ad]):
                df[ad] = df[ad].replace([np.inf, -np.inf], np.nan)
    _hedef_kodlarini_kat_disi_yap(durum, df, kaynak)
    return df


def _hedef_kodlarini_kat_disi_yap(durum, df, kaynak):
    """HEDEF SIZINTISI ONLEMI: kod satirlari WoE / hedef ortalamasini tam
    train haritasiyla yazar (uretim kodu boyle olmali). Analiz tablosu bu
    satirlardan yeniden kurulunca train satirlari da tam haritayi alir ve
    kolon olduğundan guclu gorunur. Train satirlari burada 02.2'deki gibi
    KAT DISI degerle yeniden yazilir. Hangi kolonun hedef kodlu oldugu
    ogrenilen bilgisinden (hedef_kodlama); eski kayitta kod satirindan
    (ad __WOE / __TE ile biter, kaynak kolonlar satirdaki df["..."])."""
    if kaynak != "kural":
        return
    from fe_agent import geleneksel as G
    from fe_agent.akis_durum import maskeler
    hedef = (durum.get("meta") or {}).get("target")
    if not hedef or hedef not in df.columns:
        return
    ogr = ((durum.get("ogrenilen_donusum") or {}).get("kural") or {})
    isler = {}
    for b in durum.get("kod_bloklari") or []:
        if len(b) < 3 or b[2] != kaynak:
            continue
        for satir in b[1] or []:
            ad, kod = satir[0], str(satir[1] or "")
            spec = (ogr.get(ad) or {}).get("hedef_kodlama")
            if not spec and (ad.endswith("__WOE") or ad.endswith("__TE")):
                sag = kod.split("=", 1)[1] if "=" in kod else kod
                kay = list(dict.fromkeys(re.findall(r'df\["([^"]+)"\]', sag)))
                if 1 <= len(kay) <= 2:
                    spec = {"tur": "woe" if ad.endswith("__WOE") else "hedef_ort", "kaynaklar": kay}
            if spec and ad in df.columns:
                isler[ad] = spec
    if not isler:
        return
    try:
        tr, _te = maskeler(durum, df)
    except Exception:
        return
    tr = pd.Series(tr, index=df.index).fillna(False).astype(bool)
    for ad, spec in isler.items():
        try:
            seri = G.kat_disi_hedef_kodu(df, list(spec.get("kaynaklar") or []), spec.get("tur"),
                                         hedef, tr)
        except Exception:
            seri = None
        if seri is not None:
            df.loc[tr, ad] = seri[tr].values


def asama_df(durum, asama):
    """UPDT verinin `asama` sonundaki hali (bkz. UPDT_ASAMALARI)."""
    import time as _time
    mevcut = durum.get("updt_asama")
    sira = UPDT_ASAMALARI
    if mevcut in sira and asama in sira:
        i, j = sira.index(mevcut), sira.index(asama)
        if i == j or (i < j and not any(_asama_katkisi(durum, a) for a in sira[i + 1:j + 1])):
            return _df_oku(updt_adi(durum))
    anahtar = (str(durum.get("_oturum_id") or ""), asama)
    imza = _asama_imzasi(durum, asama)
    kayit = _ASAMA_ONBELLEK.get(anahtar)
    if kayit and kayit[0] == imza and _time.time() - kayit[1] < ASAMA_ONBELLEK_SN:
        return kayit[2].copy()
    if asama in ("01.3", "01"):
        df = _updt_01_kur(durum)
    elif asama == "02.1":
        df = girmez_dusur(durum, cozum_kolonlari_ekle(
            durum, satir_kararlarini_uygula(durum, asama_df(durum, "01"))))
    elif asama == "02.2":
        from fe_agent.akis_faz03 import KURAL_KAYNAK
        df = _kod_bloklarini_uygula(durum, asama_df(durum, "02.1"), KURAL_KAYNAK)
    else:
        from fe_agent.akis_faz03 import KESIF_KAYNAK
        df = _kod_bloklarini_uygula(durum, asama_df(durum, "02.2"), KESIF_KAYNAK)
    for k in [k for k in _ASAMA_ONBELLEK if k[0] == anahtar[0]][:-1]:
        _ASAMA_ONBELLEK.pop(k, None)
    _ASAMA_ONBELLEK[anahtar] = (imza, _time.time(), df)
    return df.copy()


def updt_yaz(durum, df, asama):
    """UPDT veriyi `asama` sonundaki haliyle yazar."""
    from fe_agent import amp as amp_mod
    from fe_agent.akis_durum import onbellek_temizle
    ad = updt_adi(durum)
    kayit = (durum.get("amp_cikti") or {}).get("veri") or {}
    amp_mod._pandas_yaz(ad, df, kayit.get("kaynak") or ad)
    onbellek_temizle(ad)
    durum["updt_asama"] = asama
    kayit["kolon"] = int(df.shape[1])
    for k in [k for k in _ASAMA_ONBELLEK if k[0] == str(durum.get("_oturum_id") or "")]:
        _ASAMA_ONBELLEK.pop(k, None)


def updt_ilerlet(durum, asama, onceki):
    """Adim UPDT'ye bir sey katmadi: tablo `onceki` asamanin hali olur
    (UPDT ileride kaldiysa geri kurulup yazilir)."""
    if durum.get("updt_asama") != onceki:
        updt_yaz(durum, asama_df(durum, onceki), asama)
    durum["updt_asama"] = asama


def ara_tablo_kaydet(durum, ek, tablo, eski_yedek):
    """Profil, SFA ve PSI tablolari: yeni duzende Flow'a veri seti olarak
    YAZILMAZ, calisma klasorune iç kayit olarak gider. Doner: (dataset,
    yedek) - _yaz ile ayni bicim."""
    if not updt_modu(durum):
        return _yaz("%s_%s" % (durum["veri_seti"], ek), tablo, eski_yedek)
    from fe_agent.akis_durum import dosya_yaz
    from fe_agent.akis_faz01 import amp_klasor_adi
    return None, dosya_yaz("/%s/%s.parquet" % (amp_klasor_adi(durum), ek.lower()), tablo)


def analiz_df(durum):
    """Faz 03'un tablosu: degisken uretildiyse _ENRICHED (ham + uretilen),
    uretilmediyse modelleme tablosu. Uretilen kolondaki sonsuz deger (ornek:
    sifira bolme) bos sayilir; profil onu eksik deger olarak gorur.
    Yeni duzende UPDT verinin 02.3 sonundaki hali."""
    if updt_modu(durum):
        return asama_df(durum, "02.3")
    # _ENRICHED yalniz kural / kesif adimlari bir sey urettiyse okunur;
    # cozum kolonlari tek basina _ENRICHED gerektirmez (bayat tablo okunmaz).
    uretilen = uretim_kolonlari(durum)
    zengin = zengin_adi(durum)
    if not uretilen or not _dataset_okunur_mu(zengin):
        return cozum_kolonlari_ekle(durum, modelleme_df(durum))
    df = cozum_kolonlari_ekle(durum, _df_oku(zengin).copy(deep=False))
    for k in uretilen:
        if k in df.columns and pd.api.types.is_numeric_dtype(df[k]):
            df[k] = df[k].replace([np.inf, -np.inf], np.nan)
    return df


def _uretilen_profili(durum, df):
    """Uretilen degiskenlerin teshisi: asiri bos ve sabit olanlar olculmez,
    baz sette duser. (Uretilen degisken kimlik ya da kategori olamaz;
    yalniz bu iki teshis gecerli.)"""
    uretilen = [k for k in uretilenler(durum) if k in df.columns]
    if not uretilen:
        return {}
    egitim = egitim_maskesi(durum, df)       # train (MS) satirlari
    _tablo, t = sfa_mod.profil_cikar(df.loc[egitim, uretilen] if egitim is not None
                                     else df[uretilen])
    cok_bos = sorted(set(t.get("cok_bos") or []))
    sabit = sorted(set(t.get("sabit") or []))
    kusur = set(cok_bos) | set(sabit)
    return {"cok_bos": cok_bos, "sabit": sabit,
            "temiz": [k for k in uretilen if k not in kusur]}


def analiz_adaylari(durum):
    """SFA ve stabilitenin olctugu degiskenler: profilde temiz cikan ham
    kolonlar + kusursuz uretilen degiskenler."""
    p = durum.get("profil") or {}
    ham = list((p.get("profil_teshis") or {}).get("temiz") or [])
    ur = list((p.get("uretilen_teshis") or {}).get("temiz") or [])
    gorulen, sonuc = set(), []
    for k in ham + ur:
        if k not in gorulen:
            gorulen.add(k)
            sonuc.append(k)
    return sonuc


# ===========================================================================
# FAZ 02-05 — her modda ayni
# ===========================================================================
def _kayit_metni(yazildi, yedek):
    return ("%s veri seti" % yazildi) if yazildi else ("PROJE_HAFIZASI%s" % yedek)


# 02.1 KARAR GEREKTIREN KONTROLLER: neredeyse sabit ve donemde bos ya da
# sabit kolonlar icin kullanici "Tut" ya da "Çıkar" der. Varsayilan Tut.
PROFIL_KARAR_TUT = "tut"
PROFIL_KARAR_CIKAR = "cikar"


def _kart_olculeri(durum):
    """{kolon: kolon kartinin olcu alani} (01.2.4 Kolon Kartlari). Kart
    yoksa {}: Beklenmeyen Negatif kontrolu uygulanmaz."""
    return _kart_alani(durum, "OLCU")


def _kart_alani(durum, alan):
    """{kolon: kolon kartinin alani} (OLCU, ISTATISTIK ...); yoksa {}."""
    try:
        from fe_agent import sozluk_calisma
        sz = sozluk_oku(durum)
        ad_k = sozluk_calisma.degisken_kolonu_bul(sz)
        harita = {str(c).strip().upper(): c for c in sz.columns}
        olcu_k = harita.get(alan)
        if ad_k is None or olcu_k is None:
            return {}
        return {str(a): str(o) for a, o in zip(sz[ad_k], sz[olcu_k].fillna(""))
                if str(o).strip() and str(o) != "nan"}
    except Exception:
        return {}


# 02.1 ESIKLERI: profil cikarilmadan once kullaniciya sorulur; kontroller
# onaylanan (degistirildiyse degistirilen) esiklerle yapilir. Birim:
# "yuzde" ve "puan" ekranda 100 ile carpilmis yazilir, "sayi" ve "kat"
# oldugu gibi. (anahtar, kontrol, esigin anlami, birim, en kucuk, en buyuk)
PROFIL_ESIKLERI = (
    ("cok_bos", "Eksik Oranı Yüksek",
     "Kolonun boş hücre oranı bu değerin üstündeyse", "yuzde", 0.01, 0.99),
    ("kimlik", "Kimlik Benzeri",
     "Farklı değer sayısının satır sayısına oranı bu değerin üstündeyse", "yuzde", 0.50, 0.9999),
    ("kardinalite", "Kardinalitesi Aşırı Yüksek",
     "Yazı kolonunda farklı değer sayısı bu değerin üstündeyse", "sayi", 2, 1000000),
    ("baskin", "Neredeyse Sabit",
     "En sık görülen değer satırların en az bu kadarında geçiyorsa", "yuzde", 0.50, 0.9999),
    ("gizli", "Gizli Eksik (Özel Kod)",
     "-999, 9999 gibi uydurma bir sayı dolu satırların bu kadarından fazlasında yazıyorsa",
     "yuzde", 0.0001, 0.50),
    ("sicrama", "Dönemler Arası Eksik Sıçraması",
     "Art arda iki dönem arasında boş hücre oranı bu kadar puandan fazla değişiyorsa",
     "puan", 0.01, 0.99),
    ("uc_yayilim", "Uç Değer Yoğunluğu",
     "En büyük ya da en küçük değer, kolonun normal aralığının dışına aralığın genişliğinin "
     "bu katından fazla taşıyorsa", "kat", 2, 1000000000),
    ("yakin_kor", "Neredeyse Aynı Kolonlar",
     "İki sayı kolonu bu kadar ya da daha fazla benzer hareket ediyorsa", "yuzde", 0.90, 0.99999),
    ("sizinti_auc", "Hedefle Neredeyse Birebir",
     "Kolon tek başına hedefi bu isabetle ya da daha iyi biliyorsa",
     "yuzde", 0.70, 0.9999),
    ("kayma_kat", "Dönemler Arası Değer Kayması",
     "Kolondaki tipik değerler art arda iki dönem arasında aynı yönde en az bu kat "
     "değişiyorsa", "kat", 2, 1000000),
)
# ONERI ESIKLERI: kolonun yakalanmasini degil, yakalanan kolona hangi
# secenegin ONERILECEGINI belirler (_veri_onerileri). Formda ayri baslikta.
PROFIL_ONERI_ESIKLERI = (
    ("donem_tut_pay", "Dönemde Boş ya da Sabit: İlk Dönemler",
     "Yalnız ilk dönemler boş ya da tek değerli ve bunlar dönemlerin en çok bu kadarıysa Tut "
     "önerilir", "yuzde", 0.01, 0.99),
    ("sicrama_cikar", "Dönemler Arası Eksik Sıçraması: Çıkarma Sınırı",
     "Eksik oranı artıp bu değere ya da üstüne çıktıysa Çıkar önerilir", "yuzde", 0.01, 1.0),
    ("negatif_bos_pay", "Beklenmeyen Negatif: Boş Sayma Sınırı",
     "Eksi değerli satırlar dolu satırların bundan azıysa boş sayma önerilir", "yuzde", 0.0001, 1.0),
    ("metin_bayrak_pay", "Metin Olarak Yazılmış Boş: Bayrak Sınırı",
     "Boş yerine yazılmış değerler dolu satırların en az bu kadarıysa boş sayıp bayrak üretme "
     "önerilir", "yuzde", 0.0001, 1.0),
)
# GENEL: birden cok kontrolun kullandigi istatistik ayari (formun basinda).
PROFIL_GENEL_ESIKLER = (
    ("tesaduf", "Tesadüf Olasılığı",
     "Bir bulgunun şans eseri olma ihtimali bu değerin altındaysa bulgu gerçek sayılır",
     "yuzde", 0.001, 0.20),
)
GENEL_ESIK_ANAHTARLARI = {x[0] for x in PROFIL_GENEL_ESIKLER}
PROFIL_ESIKLERI = PROFIL_ESIKLERI + PROFIL_ONERI_ESIKLERI + PROFIL_GENEL_ESIKLER
ONERI_ESIK_ANAHTARLARI = {x[0] for x in PROFIL_ONERI_ESIKLERI}
# FORMDA ESIKLER KARTTAKI KONTROLLERIN ALTINDA: eşik, karttaki (birlesik)
# kontrolun adi ve alt eşik adiyla gosterilir; sira karttaki sira. Boylece
# 20 eşik 20 kontrol gibi gorunmez. (kontrol, alt eşik adi)
ESIK_KONTROL = (
    ("cok_bos", "Eksik Oranı Yüksek", "Boş hücre oranı"),
    ("baskin", "Sabit ya da Neredeyse Sabit", "Baskın değer"),
    ("kimlik", "Çok Fazla Farklı Değer", "Kimlik benzeri"),
    ("kardinalite", "Çok Fazla Farklı Değer", "Metinde çok değer"),
    ("yakin_kor", "Aynı ya da Neredeyse Aynı Kolonlar", "Neredeyse aynı"),
    ("sizinti_auc", "Sızıntı Riski", "Hedefle birebir"),
    ("sicrama", "Dönemler Arası Tutarsızlık", "Eksik sıçraması"),
    ("kayma_kat", "Dönemler Arası Tutarsızlık", "Değer kayması"),
    ("donem_tut_pay", "Dönemler Arası Tutarsızlık", "Dönemde boş ya da sabit: ilk dönemler"),
    ("sicrama_cikar", "Dönemler Arası Tutarsızlık", "Eksik sıçraması: çıkarma sınırı"),
    ("gizli", "Gizli Eksik", "Özel kod"),
    ("metin_bayrak_pay", "Gizli Eksik", "Metin olarak boş: bayrak sınırı"),
    ("negatif_bos_pay", "Beklenmeyen Negatif", "Boş sayma sınırı"),
    ("uc_yayilim", "Uç Değer Yoğunluğu", "Uç değer"),
)
_ESIK_KONTROL = {a: (i, k, alt) for i, (a, k, alt) in enumerate(ESIK_KONTROL)}


def esik_adi(anahtar, kontrol=""):
    """Eşigin ekrandaki adi: formdaki satir adi (PROFIL_ESIKLERI)."""
    if kontrol:
        return kontrol
    return {x[0]: x[1] for x in PROFIL_ESIKLERI}.get(anahtar, anahtar)
# Formda her kontrolun duz dille aciklamasi: "kisa" satirda, "bilgi" i
# balonunda (nedir, neden onemli, ornek, yakalanirsa ne olur, onerilen
# degerin gerekcesi), "sonuc" yakalanan kolona ne oldugu (NE_OLACAK ile
# ayni sozler).
def _ac(kisa, nedir, ornek, yakala, neden_etiket=None, neden=None, kapsam=None, sonuc=None,
        sorun=None):
    """Sade aciklama: tek cumle (kisa) ve i balonu (bilgi). GUNDELIK DIL:
    istatistik terimi yok (AUC, korelasyon, yuzdelik, IV yazilmaz), her
    kuralda kucuk sayilarla ornek. Her veri ve her siniflandirma problemi
    icin genel; alana ozel terim yok."""
    p = ["**Nedir?** " + nedir]
    if sorun:
        p.append("**Neden sorun?** " + sorun)
    if kapsam:
        p.append("**Kapsam:** " + kapsam)
    p.append("**Örnek:** " + ornek)
    p.append("**Yakalanırsa:** " + yakala)
    if neden_etiket and neden:
        p.append("**%s** %s" % (neden_etiket, neden))
    d = {"kisa": kisa, "bilgi": "\n\n".join(p)}
    if sonuc:
        d["sonuc"] = sonuc
    return d


_VERIDEN = "Önerilen nereden?"
_KOD_SAKLA = ("bu sayı boş sayılır; hangi satırlarda yazdığı da ayrı bir 1/0 kolonunda (_KOD) "
              "saklanır")
PROFIL_ESIK_ACIKLAMA = {
    "cok_bos": _ac(
        "Büyük kısmı boş olan kolon.",
        "Kolondaki hücrelerin yüzde kaçının boş olduğuna bakar. Boş oranı eşiğin üstündeyse "
        "kolon yakalanır.",
        "100 satırın 85'i boşsa boş oranı %85'tir. Eşik %80 ise kolon yakalanır.",
        "kolon olduğu gibi kullanılmaz. Yerine «bu satırda değer var mı, yok mu» bilgisini "
        "taşıyan 1/0 kolonu önerilir; kabul edip etmemek size kalır.",
        "Neden %80 önerildi?",
        "Kolonun beşte dördü boşsa geriye işe yarar bilgi kalmaz. Daha az boş olan kolon, boşlar "
        "doldurularak kullanılır.",
        sorun="Kolonun çoğu boşsa model o kolondan bir şey öğrenemez.",
        sonuc="Çözüm önerilir; çözüm yoksa üretime girmez"),
    "kimlik": _ac(
        "Neredeyse her satırda başka değer olan kolon (müşteri numarası gibi).",
        "Kolonda kaç farklı değer olduğunu sayar ve satır sayısına böler. Sonuç %100'e yakınsa "
        "neredeyse her satırda başka bir değer var demektir. Sonuç eşiğin üstündeyse kolon "
        "yakalanır.",
        "100 satırda 98 farklı değer varsa oran %98'dir. Eşik %95 ise kolon yakalanır.",
        "kolon olduğu gibi kullanılmaz. Değerler bir kod gibi düzenliyse (örneğin ilk iki harf "
        "şubeyi gösteriyorsa) ilk harflere göre gruplama önerilir.",
        "Neden %95 önerildi?",
        "Numara gibi kolonlarda her satır farklıdır. %95, arada birkaç tekrar olsa bile bunları "
        "yakalar.",
        kapsam="tam sayı ve yazı kolonları. Küsuratlı sayılar (tutar gibi) doğal olarak hep "
               "farklıdır, onlara bakılmaz. Kolon kartında ölçüsü (tutar, adet, süre gibi) yazan "
               "sayı kolonlarına da bakılmaz; onlar numara değil, ölçüdür.",
        sorun="Her satırda farklı olan değer yalnız o satırı tanıtır; model bundan genel bir "
              "kural çıkaramaz.",
        sonuc="Çözüm önerilir; çözüm yoksa üretime girmez"),
    "kardinalite": _ac(
        "Çok fazla farklı değeri olan yazı kolonu.",
        "Yazı kolonunda kaç farklı değer olduğunu sayar. Sayı eşiğin üstündeyse kolon "
        "yakalanır.",
        "Şehir kolonunda 81 farklı şehir var. Eşik 50 ise kolon yakalanır.",
        "kolon olduğu gibi kullanılmaz. Benzer değerleri birleştirip daha az gruba indirmek "
        "önerilir.",
        _VERIDEN,
        "Eğitim verisinde hedefi 1 olan satır sayısı 5'e bölünür. Bir değere bunlardan 5'ten azı "
        "düşerse o değer için güvenilir bir şey söylenemez. Sonuç en az 2, en çok 50 olur; hedef "
        "bilinmiyorsa 50.",
        sorun="Değer çoğaldıkça her birine az satır düşer; az satıra bakarak doğru sonuç "
              "çıkarılamaz.",
        sonuc="Çözüm önerilir; çözüm yoksa üretime girmez"),
    "baskin": _ac(
        "Satırların neredeyse hepsinde aynı değer.",
        "Kolonda en çok görülen değeri bulur ve satırların yüzde kaçında geçtiğine bakar. Bu "
        "pay eşik kadar ya da daha fazlaysa kolon yakalanır. Boş hücre de bir değer sayılır.",
        "100 satırın 99'unda 0 yazıyorsa pay %99'dur. Eşik %99 ise kolon yakalanır.",
        "kolonu tutmak ya da çıkarmak size sorulur. Sistem bir öneri de verir: farklı değerdeki "
        "az sayıdaki satıra bakar. Bu satırlarda hedef, öteki satırlardan belirgin biçimde "
        "farklıysa kolon işe yarıyordur: Tut. Fark yoksa, fark şans eseri olabilecek kadar "
        "küçükse ya da karar verecek kadar satır yoksa: Çıkar.",
        "Neden %99 önerildi?",
        "100 satırın 99'u aynıysa kolon neredeyse hep aynıdır. Sayıyı düşürürseniz daha çok "
        "kolon size sorulur.",
        sorun="Hemen her satırda aynı olan kolon satırları birbirinden ayırt etmez.",
        sonuc="Kararınıza bırakılır"),
    "gizli": _ac(
        "Boş bırakmak yerine -999, 9999 gibi uydurma bir sayı yazılmış.",
        "Kolonun öteki değerlerinden kopuk duran -1, -99, -999, 9999 gibi bir sayı arar. Böyle "
        "bir sayı dolu satırların eşikten fazlasında yazıyorsa kolon yakalanır. Yalnız -1, 0 ve "
        "1 değerlerini alan kolonda (arttı / azaldı gibi) -1 gerçek değerdir, yakalanmaz.",
        "Yaş kolonunda dolu 100 satırın 3'ünde -999 yazıyor: %3. Eşik %1 ise kolon yakalanır.",
        "kolon kullanılır. Öneri: " + _KOD_SAKLA + ".",
        "Neden %1 önerildi?",
        "100 satırda 1'den az görülen sayı gerçek bir değer olabilir. Daha sık görülüyorsa "
        "bilerek yazılmış bir koddur.",
        sorun="Bu sayı gerçek bir değer gibi hesaba girerse ortalamaları ve sonucu bozar.",
        sonuc="Düzeltme önerilir; kolon üretime girer"),
    "sicrama": _ac(
        "Boş oranı bir dönemden sonrakine birden değişen kolon.",
        "Her dönemde (ay gibi) kolonun yüzde kaçının boş olduğunu hesaplar ve art arda gelen "
        "iki dönemi karşılaştırır. Aradaki fark eşikten büyükse kolon yakalanır. Az satırlı "
        "dönemlerde boş oranı kendiliğinden oynar; fark şans eseri olabilecek kadar küçük bir "
        "dönemden geliyorsa yakalanmaz («Tesadüf Olasılığı» sınırı).",
        "Mart'ta 100 satırın 5'i boş, Nisan'da 40'ı boş. Fark 35 puan; eşik 20 puan ise kolon "
        "yakalanır.",
        "kolonu tutmak ya da çıkarmak size sorulur. Öneri: boş oranı artıp «Çıkarma sınırı»nı "
        "geçtiyse Çıkar; geçmediyse ya da azaldıysa Tut.",
        "Neden 20 puan önerildi?",
        "Bir dönemden ötekine birkaç puan oynama normaldir. 20 puan birden değişiyorsa veride "
        "bir şey değişmiştir.",
        sorun="Boş oranı birden değişiyorsa verinin toplanma biçimi değişmiştir; eski ve yeni "
              "dönem aynı şeyi anlatmıyor olabilir.",
        sonuc="Kararınıza bırakılır"),
    "uc_yayilim": _ac(
        "Yanlış yazıldığı belli olan çok büyük ya da çok küçük değer.",
        "Önce kolonun normal aralığı bulunur: en küçük %1 ve en büyük %1'lik değerler dışarıda "
        "bırakılır, kalanların alt ve üst ucu normal aralıktır. En büyük ya da en küçük değer bu "
        "aralığın çok dışındaysa yakalanır. «Çok» şu demek: aralığın genişliğinin eşik katından "
        "fazla. -999 gibi uydurma sayılar bu hesaba katılmaz.",
        "Normal aralık 0 ile 10.000 (genişlik 10.000). Eşik 100 kat ise sınır 10.000 + 100 × "
        "10.000 = 1.010.000. Bir satırda 5.000.000 yazıyorsa kolon yakalanır.",
        "kolon kullanılır. Öneri: yakalanan değer normal aralığın ucuna çekilir (örnekte "
        "5.000.000 yerine 10.000 yazılır).",
        "Neden 100 kat önerildi?",
        "Yüksek tutuldu ki yalnız yanlış yazıldığı belli olan değerler yakalansın. Büyük ama "
        "gerçek olabilecek değerlere sonraki adımda (SFA) bakılır.",
        sorun="Tek bir yanlış yazılmış sayı ortalamayı ve modelin öğrendiğini bozar.",
        sonuc="Düzeltme önerilir; kolon üretime girer"),
    "yakin_kor": _ac(
        "Başka bir kolonla neredeyse aynı şeyi söyleyen kolon.",
        "İki sayı kolonunun birlikte ne kadar aynı hareket ettiğine bakar. Biri artınca öteki de "
        "hep aynı oranda artıyorsa benzerlik %100'dür. Benzerlik eşik kadar ya da daha fazlaysa "
        "kolonlar yakalanır.",
        "Aynı tutar bir kolonda TL, ötekinde bin TL olarak tutulmuş: benzerlik %100.",
        "benzer kolonlardan biri kalır, ötekiler üretime girmez. Hangisinin kalacağını siz "
        "seçersiniz; hedefi daha iyi ayırt eden önerilir.",
        "Neden %99 önerildi?",
        "%99 benzer iki kolon pratikte aynıdır; ikisini de tutmak bir şey kazandırmaz.",
        sorun="Aynı bilgiyi iki kez vermek modele bir şey kazandırmaz, yalnız kalabalık yapar.",
        sonuc="Biri kalır, diğerleri üretime girmez"),
    "sizinti_auc": _ac(
        "Hedefi tek başına şaşırtıcı derecede iyi bilen kolon.",
        "Her kolon için şunu ölçer: hedefi 1 olan bir satırla hedefi 0 olan bir satır yan yana "
        "konsa, yalnız bu kolona bakarak hangisinin 1 olduğu 100 denemenin kaçında doğru "
        "bulunur? 50, yazı tura atmak kadardır; 100, hiç yanılmamaktır. Sonuç eşik kadar ya "
        "da daha yüksekse kolon yakalanır.",
        "«Kapanış nedeni» kolonu yalnız olay gerçekleştikten sonra doluyor; hedefi 100 denemenin "
        "99'unda doğru gösteriyor.",
        "kolonu tutmak ya da çıkarmak size sorulur. Öneri: isabet %95 ve üstüyse Çıkar; "
        "altındaysa Tut, ama kolonun tahmin anında gerçekten bilinip bilinmediğini kontrol edin.",
        "Neden %85 önerildi?",
        "Sıradan bir kolon tek başına bu kadar iyi bilemez. Biliyorsa çoğu zaman sonuç belli "
        "olduktan sonra doldurulmuştur.",
        kapsam="hedef yalnız 1 ve 0 değerlerini alıyorsa; yalnız eğitim satırlarına bakılır.",
        sorun="Bir kolon hedefi bu kadar iyi biliyorsa çoğu zaman sonuç belli olduktan sonra "
              "doldurulmuştur. Sınav kâğıdına cevap anahtarını koymak gibidir: model eğitimde "
              "çok başarılı görünür, gerçek kullanımda o bilgi elinde olmadığı için işe yaramaz.",
        sonuc="Kararınıza bırakılır"),
    "kayma_kat": _ac(
        "Sayıları bir dönemden sonrakine topluca kat kat değişen kolon.",
        "Kolondaki tipik değerlerin (küçük, orta ve büyük değerlerin) art arda iki dönem "
        "arasında kaç kat değiştiğine bakar. Üçü de aynı yönde eşik kadar ya da daha fazla "
        "değiştiyse yakalanır. Sıfırlar hesaba katılmaz.",
        "Tutarlar Mart'a kadar TL, Nisan'dan sonra bin TL yazılmış: ortadaki değer 1.200'den "
        "1,2'ye düşer, 1.000 kat.",
        "kolonu tutmak ya da çıkarmak size sorulur. Öneri: değişim 10, 100, 1.000 gibi yuvarlak "
        "bir katsa (birim değişikliği) Çıkar, değilse Tut.",
        "Neden 10 kat önerildi?",
        "Gerçek değerler bir dönemde 10 katına çıkmaz. Çıktıysa çoğu zaman birim değişmiştir "
        "(TL yerine bin TL gibi).",
        sorun="Sayılar topluca kat kat değişiyorsa çoğu zaman değerin birimi değişmiştir; eski "
              "ve yeni dönem aynı ölçüde değildir.",
        sonuc="Kararınıza bırakılır"),
}
PROFIL_ESIK_ACIKLAMA.update({
    "tesaduf": {
        "kisa": "Sistemin «bu şans eseri olabilir» deme sınırı.",
        "bilgi": "\n\n".join([
            "**Nedir?** Bazı kurallar az sayıda satıra bakarak karar verir. Az satırda görülen "
            "bir şey gerçek bir sorun olabilir, ama şans eseri de olmuş olabilir. Sistem her "
            "seferinde şunu hesaplar: «Ortada bir sorun olmasaydı, bu durumu görme ihtimalim ne "
            "olurdu?» İhtimal bu sınırın altındaysa «şans değil, gerçek» der ve kolonu yakalar. "
            "Üstündeyse «şans olabilir» der, yakalamaz. Çok sayıda dönem tek tek sınandığında "
            "şans eseri bir bulgu çıkma ihtimali artar; bu yüzden dönem kurallarında sınır sınanan "
            "dönem sayısına bölünür.",
            "**Kapsam:** üç yerde kullanılır. 1) «Dönemde boş ya da sabit» kuralı: bir dönemin "
            "tamamen boş ya da hep aynı değerde olması şans mı? 2) «Eksik sıçraması» kuralı: iki "
            "dönemin boş oranı arasındaki fark şans mı? 3) «Baskın değer» kuralının Tut / Çıkar "
            "önerisi: az sayıdaki farklı satırda hedefin farklı çıkması şans mı?",
            "**Örnek:** Bir kolonun genelde 100 satırından 90'ında 0 yazıyor. Bir ayda yalnız 10 "
            "satır var ve hepsinde 0 yazıyor: bu şans eseri olabilir (ihtimal %35), yakalanmaz. "
            "Başka bir ayda 100 satır var ve hepsinde 0 yazıyor: şansla bu neredeyse hiç olmaz "
            "(ihtimal %0,003), o ay kolonda bir sorun vardır, yakalanır.",
            "**Eşik ne yapar?** %5 yerine %1 yazarsanız sistem daha zor ikna olur, daha az kolon "
            "yakalar. %10 yazarsanız daha kolay ikna olur, daha çok kolon yakalar.",
            "**Neden %5 önerildi?** 100 denemede 5'ten az görülecek bir şey şans sayılmaz. "
            "İstatistikte en yaygın kullanılan sınırdır."]),
        "sonuc": "Küçülürse daha az, büyürse daha çok kolon yakalanır"},
    "donem_tut_pay": _ac(
        "Sorun yalnız en baştaki dönemlerdeyse kolon sonradan eklenmiştir.",
        "Kolon «Dönemde boş ya da sabit» kuralına takıldıysa sistem sorunlu dönemlerin nerede "
        "olduğuna bakar. Yalnız en baştaki dönemler sorunluysa kolon sonradan eklenmiştir, "
        "sonrası düzgündür. Baştaki sorunlu dönemler bütün dönemlerin bu sınırını geçmiyorsa "
        "Tut, geçiyorsa Çıkar önerilir. Son dönem sorunluysa sınıra bakılmadan Çıkar önerilir; "
        "çünkü kolon güncel veride yoktur.",
        "24 dönemin ilk 6'sı boş: %25. Sınır %35 ise Tut önerilir.",
        "yalnız sistemin önerisini belirler; kararı siz verirsiniz.",
        "Neden %35 önerildi?",
        "Dönemlerin kabaca üçte biri. Bundan azı sorunluysa kalan dönemler model için yeter.",
        sonuc="Öneri: altındaysa Tut"),
    "sicrama_cikar": _ac(
        "Boş oranı artıp sınırı geçtiyse kolon artık çoğunlukla boştur.",
        "Kolon «Eksik sıçraması» kuralına takıldıysa sistem sıçramadan sonraki dönemin boş "
        "oranına bakar. Boş oranı artmış ve bu sınırı geçmişse Çıkar önerilir. Artmış ama sınırı "
        "geçmemişse ya da azalmışsa Tut önerilir.",
        "Boş oranı %5'ten %55'e çıktı. Sınır %50 ise Çıkar önerilir.",
        "yalnız sistemin önerisini belirler; kararı siz verirsiniz.",
        "Neden %50 önerildi?",
        "Yarısından fazlası boş olan kolon artık çoğunlukla boştur.",
        sonuc="Öneri: üstündeyse Çıkar"),
    "negatif_bos_pay": _ac(
        "Az sayıda eksi değer yanlış kayıttır.",
        "Kolon «Negatif değer» kuralına takıldıysa sistem eksi değerli satırların ne kadar "
        "olduğuna bakar. Bu sınırdan azsa yanlış kayıt sayılır ve boş sayılması önerilir. Sınır "
        "kadar ya da daha çoksa bir anlamı olabilir (iade gibi); olduğu gibi bırakılması "
        "önerilir.",
        "Dolu 100 satırın 1'i eksi: %1. Sınır %5 ise eksi değerlerin boş sayılması önerilir.",
        "yalnız sistemin önerisini belirler; kararı siz verirsiniz.",
        "Neden %5 önerildi?",
        "Yanlış kayıt tek tük olur. 100 satırın 5'inden fazlası eksiyse bu hata değil, bir "
        "anlamı vardır (iade gibi).",
        sonuc="Öneri: altındaysa boş say"),
    "metin_bayrak_pay": _ac(
        "«Bilinmiyor» gibi yazılar çoksa, boş olmak da bir bilgi olabilir.",
        "Kolon «Metin olarak boş» kuralına takıldıysa bu yazılar her durumda boş sayılır. Sistem "
        "ayrıca yazıların ne kadar sık geçtiğine bakar: bu sınır kadar ya da daha çoksa, «boş "
        "mu, dolu mu» bilgisini taşıyan ek bir 1/0 kolonu da önerilir; çünkü çok sayıda satırda "
        "bilginin olmaması kendisi bir bilgi olabilir.",
        "100 satırın 15'inde «Bilinmiyor» yazıyor: %15. Sınır %5 ise ek kolon da önerilir.",
        "yalnız sistemin önerisini belirler; kararı siz verirsiniz.",
        "Neden %5 önerildi?",
        "100 satırın 5'inden azında görülüyorsa ek kolon neredeyse hep 0 olur, işe yaramaz.",
        sonuc="Öneri: bu pay ya da üstündeyse boş say ve bayrak üret"),
})
ESIK_BIRIM_ADI = {"yuzde": "%", "puan": "puan", "sayi": "", "kat": "kat"}
ESIK_METNI = ("Veri profilinde her kolon aşağıdaki kontrollerden geçer. Her kuralın yanında "
              "neye baktığı, bir örnek ve sınırı (eşik) yazar. Sınırlar önerilen değerle dolu "
              "gelir; olduğu gibi onaylayabilir ya da değiştirebilirsiniz.")
ESIK_DUGME = "Eşikleri Onayla ve Profili Çıkar"


def _esik_varsayilan(durum=None):
    """Onerilen esikler; durum verilirse uc esik bu veriden (veriye_gore_onerilen)."""
    from fe_agent import profil_ek as pe
    d = dict(pe.ESIK_VARSAYILAN)
    d.update({"cok_bos": COK_BOS_ESIK, "kimlik": 0.95, "kardinalite": sfa_mod.KATEGORIK_MAX})
    d.update({"donem_tut_pay": DONEM_TUT_PAY, "sicrama_cikar": SICRAMA_CIKAR_PAY,
              "negatif_bos_pay": NEGATIF_BOS_PAY,
              "metin_bayrak_pay": METIN_BAYRAK_PAY})
    if durum:
        try:
            d.update({k: v for k, (v, _m) in veriye_gore_onerilen(durum).items()})
        except Exception:
            pass
    return d


# VERIYE GORE ONERILEN (dil modeli yok): uc esigin onerileni bu veri
# setinin egitim satiri, hedef orani ve donem sayisindan kuralla; bilgi
# yoksa sabit. Kalan esikler is kurali, her veride ayni.
COK_BOS_ESIK = 0.80
# Pencere tutarliligi ve tutar / adet uyumu: celisen satirlar en az bu payda
# ise gosterilir (tek tuk hatali satir buyuk veride her kolonda cikar).
ILISKI_MIN_PAY = 0.01


def _veri_ozeti(durum):
    """(egitim satiri, egitim hedef orani, toplam satir, donem sayisi); bilinmeyen None."""
    durum = durum or {}
    b = durum.get("bolme") or {}
    pr = durum.get("profil") or {}
    n = pr.get("satir")
    egitim = (b.get("satir") or {}).get("egitim") if isinstance(b.get("satir"), dict) else None
    oran = (b.get("hedef_oran") or {}).get("egitim") if isinstance(b.get("hedef_oran"), dict) else None
    if oran is None and pr.get("hedef_tip") == "binary" and pr.get("event_rate") is not None:
        oran = float(pr["event_rate"]) / 100.0
    donem_kol = (durum.get("meta") or {}).get("donem")
    donem_n = None
    for o in pr.get("kolon_ozet") or []:
        if isinstance(o, dict) and donem_kol and o.get("ad") == donem_kol and o.get("tekil"):
            donem_n = int(o["tekil"])
    egitim = int(egitim) if egitim else (int(n) if n else None)
    return egitim, (float(oran) if oran else None), (int(n) if n else None), donem_n


# ONERILEN NEYE GORE: formun Onerilen sutununda degerin altinda. Veriden
# hesaplananlarda hesap (veriye_gore_onerilen), bilgi yoksa sabit degerin
# nedeni; digerlerinde kisa gerekce.
ONERILEN_DAYANAK = {
    "cok_bos": "Kolonun beşte dördü boşsa geriye işe yarar bilgi kalmaz.",
    "kimlik": "Numara gibi kolonlarda her satır farklıdır; %95, arada birkaç tekrar olsa bile "
              "bunları yakalar.",
    "kardinalite": "Hedef bilinmediği için sistemin üst sınırı olan 50 kullanıldı.",
    "baskin": "100 satırın 99'u aynıysa kolon neredeyse hep aynıdır. Düşürürseniz daha çok kolon "
              "size sorulur.",
    "gizli": "100 satırda 1'den az görülen sayı gerçek bir değer olabilir; daha sık görülüyorsa "
             "bilerek yazılmış bir koddur.",
    "sicrama": "Birkaç puan oynama normaldir. 20 puan birden değişiyorsa veride bir şey "
               "değişmiştir.",
    "uc_yayilim": "Yüksek tutuldu ki yalnız yanlış yazıldığı belli olan değerler yakalansın.",
    "yakin_kor": "%99 benzer iki kolon pratikte aynıdır; ikisini de tutmak bir şey kazandırmaz.",
    "sizinti_auc": "Sıradan bir kolon tek başına bu kadar iyi bilemez; biliyorsa çoğu zaman sonuç "
                   "belli olduktan sonra doldurulmuştur.",
    "kayma_kat": "Gerçek değerler bir dönemde 10 katına çıkmaz; çıktıysa çoğu zaman birim "
                 "değişmiştir (TL yerine bin TL gibi).",
    "tesaduf": "100 denemede 5'ten az görülecek bir şey şans sayılmaz. İstatistikte en yaygın "
               "kullanılan sınırdır.",
    "donem_tut_pay": "Dönemlerin kabaca üçte biri. Bundan azı sorunluysa kalan dönemler yeter.",
    "sicrama_cikar": "Yarısından fazlası boş olan kolon artık çoğunlukla boştur.",
    "negatif_bos_pay": "Yanlış kayıt tek tük olur; 100 satırın 5'inden fazlası eksiyse bir anlamı "
                       "vardır (iade gibi).",
    "metin_bayrak_pay": "100 satırın 5'inden azında görülüyorsa ek kolon neredeyse hep 0 olur, işe "
                        "yaramaz.",
}

def veriye_gore_onerilen(durum):
    """{anahtar: (deger, aciklama)}: veriden hesaplanan onerilenler (dil
    modeli yok). Metinde cok deger: Cochran kurali; her degerde beklenen
    en az 5 hedefi 1 olan satir olabilmesi icin en cok (egitimde hedefi 1
    olan satir / 5) deger; SFA en cok 50 degerli kolonla calistigi icin
    ust sinir 50."""
    egitim, oran, n, donem_n = _veri_ozeti(durum)
    cikti = {}
    if oran and 0 < oran < 1 and egitim:
        # Az gorulen sinif: hedef orani %50 ustundeyse az gorulen 0'dir.
        sinif = "1" if oran <= 0.5 else "0"
        tem = int(round(egitim * min(oran, 1 - oran)))
        ham = tem // COCHRAN_EN_AZ
        k = int(min(sfa_mod.KATEGORIK_MAX, max(2, ham)))
        bas = ("Eğitim verisinde hedefi %s olan %s satır var. Bir değere bunlardan 5'ten azı "
               "düşerse o değer için güvenilir bir şey söylenemez." % (sinif, _sayi(tem)))
        if k == ham:
            m = bas + " %s ÷ 5 = %s." % (_sayi(tem), _sayi(k))
        elif k < ham:
            m = bas + " %s ÷ 5 = %s; ama sistemin üst sınırı %s olduğu için %s." % (
                _sayi(tem), _sayi(ham), _sayi(k), _sayi(k))
        else:
            m = ("Eğitim verisinde hedefi %s olan yalnız %s satır var; ikiden fazla değere "
                 "bölünürse her birine 5'ten az düşer." % (sinif, _sayi(tem)))
        cikti["kardinalite"] = (k, m)
    return cikti


def profil_esikleri(durum):
    """Gecerli esikler: varsayilan (veriye gore onerilen dahil) + kullanicinin
    onayladigi."""
    d = _esik_varsayilan(durum)
    kayit = (durum.get("profil") or {}).get("esikler")
    if isinstance(kayit, dict):
        d.update({k: v for k, v in kayit.items() if k in d and v is not None})
    return d


def _esik_ekran(birim, v):
    """Ic deger -> ekrandaki sayi (yuzde ve puan 100 ile carpilir)."""
    x = float(v) * 100 if birim in ("yuzde", "puan") else float(v)
    x = round(x, 4)
    return int(x) if x == int(x) else x


def _esik_ic(birim, v):
    """Ekrandaki sayi -> ic deger. Turkce yazim: 1.000 binlik, 0,5 ondalik."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        x = float(v)
    else:
        t = str(v).replace("%", "").replace(" ", "").strip()
        if "," in t:
            t = t.replace(".", "").replace(",", ".")
        elif re.fullmatch(r"\d{1,3}(\.\d{3})+", t):
            t = t.replace(".", "")
        x = float(t)
    return x / 100.0 if birim in ("yuzde", "puan") else x


def _esik_metni(birim, v):
    x = _esik_ekran(birim, v)
    yazi = _sayi(x) if isinstance(x, int) else ("%s" % x).replace(".", ",")
    if birim == "yuzde":
        return "%" + yazi
    if birim == "puan":
        return yazi + " puan"
    if birim == "kat":
        return yazi + " kat"
    return yazi


def esik_dogrula(gelen):
    """Formdan gelen {anahtar: ekrandaki sayi}. Doner: (esikler, hata)."""
    sonuc, hatalar = {}, []
    gelen = gelen if isinstance(gelen, dict) else {}
    for a, kontrol, _anlam, birim, en_az, en_cok in PROFIL_ESIKLERI:
        if a not in gelen or str(gelen[a]).strip() == "":
            hatalar.append("%s: değer boş" % esik_adi(a, kontrol))
            continue
        try:
            v = _esik_ic(birim, gelen[a])
        except (TypeError, ValueError):
            hatalar.append("%s: sayı değil" % esik_adi(a, kontrol))
            continue
        if birim in ("sayi", "kat"):
            v = int(round(v)) if float(v).is_integer() or birim == "sayi" else v
        if not (en_az <= v <= en_cok):
            hatalar.append("%s: %s ile %s arasında olmalı" % (
                esik_adi(a, kontrol), _esik_metni(birim, en_az), _esik_metni(birim, en_cok)))
            continue
        sonuc[a] = v
    if hatalar:
        return None, "Eşikler kaydedilmedi. " + "; ".join(hatalar) + "."
    return sonuc, None


def esik_formu(durum, hata=None, kilitli=False):
    """02.1 esik formu (tip profil_esik)."""
    simdiki = profil_esikleri(durum)
    varsayilan = _esik_varsayilan(durum)
    satirlar = []
    for a, kontrol, anlam, birim, en_az, en_cok in PROFIL_ESIKLERI:
        ac = PROFIL_ESIK_ACIKLAMA.get(a) or {}
        ek_ = _ESIK_KONTROL.get(a, (99, kontrol, kontrol))
        satirlar.append({"anahtar": a, "kontrol": kontrol, "anlam": anlam, "birim": birim,
                         "kontrol_grup": ek_[1], "alt": ek_[2], "_sira": ek_[0],
                         "kisa": ac.get("kisa", ""), "bilgi": ac.get("bilgi", ""),
                         "sonuc": ac.get("sonuc", ""),
                         "parca": aciklama_parcalari(ac.get("bilgi")),
                         "birim_adi": ESIK_BIRIM_ADI[birim],
                         "deger": _esik_ekran(birim, simdiki[a]),
                         "varsayilan": _esik_ekran(birim, varsayilan[a]),
                         "varsayilan_metni": _esik_metni(birim, varsayilan[a]),
                         "en_az": _esik_ekran(birim, en_az), "en_cok": _esik_ekran(birim, en_cok),
                         "grup": "oneri" if a in ONERI_ESIK_ANAHTARLARI else "yakalama"})
    for r in satirlar:
        r["kontrol_no"] = kontrol_no(r["kontrol_grup"])
    satirlar.sort(key=lambda r: (r["kontrol_no"] or 99, r.pop("_sira")))
    dayanak = {}
    try:
        dayanak = {k: m for k, (_v, m) in veriye_gore_onerilen(durum).items()}
    except Exception:
        pass
    for r in satirlar:
        r["dayanak"] = dayanak.get(r["anahtar"]) or ONERILEN_DAYANAK.get(r["anahtar"], "")
        if r["anahtar"] in ONERI_ESIK_AD:
            r["oneri_ad"] = ONERI_ESIK_AD[r["anahtar"]]
    # NUMARALAR: genel ayar (Tesadüf Olasılığı) formda 1 numaradir; birden
    # cok kuralin kolonu yakalayip yakalamayacagini o belirler. Kontroller
    # 2'den baslar.
    genel = [x[0] for x in PROFIL_GENEL_ESIKLER]
    kontroller, _esiksiz = esik_form_kontrolleri(durum, ilk_no=len(genel) + 1)
    return {"tip": "profil_esik", "adim": "veri_profili", "satirlar": satirlar,
            "kontroller": kontroller,
            # SAYIM: toplam kontrol (kartta gorunen), bunlarin altindaki
            # kural, ayarlanabilir esik; formda gorunen kontrol ve kural.
            "sayim": {"kontrol": gorunur_kontrol_sayisi(), "kural": toplam_kural_sayisi(),
                      "esik": len(PROFIL_ESIKLERI), "esiksiz_kontrol": len(_esiksiz),
                      "esiksiz_kural": sum(1 for k in kontroller for u in k["kurallar"]
                                           if not u["esik"] and not u["oneri"])},
            "genel": genel, "genel_no": 1,
            "hata": hata or "", "kilitli": bool(kilitli), "buton": ESIK_DUGME}


# ESIK FORMU DUZENI: her kontrol bir kart; icinde kurallari (esigi olan ve
# olmayan), esikli kuralin altinda onun oneri esikleri. Esigi olmayan
# kontroller en altta tek satir.
KONTROL_FORM_KISA = {
    "cok_bos": "Büyük kısmı boş olan kolon",
    "g_sabit": "Her satırda ya da neredeyse her satırda aynı değer",
    "g_kardinalite": "O kadar çok farklı değer var ki kolon olduğu gibi kullanılamaz",
    "tarih": "Tarih kolonu olduğu gibi kullanılmaz",
    "g_ayni": "Başka bir kolonla aynı şeyi söyleyen kolon",
    "g_sizinti": "Tahmin anında henüz bilinmeyen bilgiyi taşıyan kolon",
    "g_donem": "Bazı dönemlerde bozulan kolon",
    "g_gizli": "«Bilgi yok» demek için boş bırakmak yerine sayı ya da yazı yazılmış",
    "yazim": "Aynı değer farklı biçimlerde yazılmış",
    "negatif": "Eksi olamayacak kolonda eksi değer",
    "uc": "Yanlış yazıldığı belli olan çok büyük ya da çok küçük değer",
    "g_iliskili": "Birbirine bağlı iki kolon birbirini tutmuyor",
    "tekrar": "Aynı satır birden fazla kez yazılmış",
    "set_cakisma": "Aynı kayıt hem eğitim hem sınama verisinde var",
}
KURAL_FORM_AD = {
    "cok_bos": "Boş hücre oranı", "sabit": "Tek değer", "baskin": "Baskın değer",
    "kimlik_gibi": "Kimlik benzeri", "yuksek_kardinalite": "Metinde çok değer",
    "tarih": "Tarih kolonu", "ayni_icerik": "Birebir aynı", "yakin_icerik": "Neredeyse aynı",
    "gelecek_pencere": "Gelecek penceresi", "birebir": "Hedefle birebir",
    "tarih_sonra": "Dönemden sonraki tarih", "donem": "Dönemde boş ya da sabit",
    "sicrama": "Eksik sıçraması", "kayma": "Değer kayması", "gizli_eksik": "Özel kod",
    "karisik_eksik": "Özel kod ve boş hücre", "metin_bos": "Metin olarak boş",
    "yazim": "Yazım tutarsızlığı", "negatif": "Negatif değer", "uc": "Uç değer",
    "pencere": "Pencere tutarlılığı", "tutar_adet": "Tutar ve adet",
    "tekrar": "Tekrar eden satır", "set_cakisma": "Setler arası çakışma",
}
# Esik -> ait oldugu kural (PROFIL_KONTROLLERI anahtari).
ESIK_KURAL = {
    "cok_bos": "cok_bos", "baskin": "baskin",
    "kimlik": "kimlik_gibi", "kardinalite": "yuksek_kardinalite",
    "yakin_kor": "yakin_icerik", "sizinti_auc": "birebir",
    "donem_tut_pay": "donem", "sicrama": "sicrama", "sicrama_cikar": "sicrama",
    "kayma_kat": "kayma", "gizli": "gizli_eksik", "metin_bayrak_pay": "metin_bos",
    "negatif_bos_pay": "negatif", "uc_yayilim": "uc",
}
ONERI_ESIK_AD = {
    "donem_tut_pay": "İlk dönemler", "sicrama_cikar": "Çıkarma sınırı",
    "metin_bayrak_pay": "Bayrak sınırı", "negatif_bos_pay": "Boş sayma sınırı",
}


def esik_form_kontrolleri(durum, ilk_no=1):
    """([{"no", "ad", "kisa", "kurallar": [{"anahtar", "ad", "olcut", "sonuc",
    "esik", "oneri": [anahtar]}]}], [{"no", "ad"}] esiksiz kontroller)."""
    kurallar_metin = _profil_kurallari(profil_esikleri(durum))
    pk = {x[0]: x for x in PROFIL_KONTROLLERI}
    uyeler = {g[0]: g[3] for g in KONTROL_GRUPLARI}
    esik_of = {}
    for a, k in ESIK_KURAL.items():
        esik_of.setdefault(k, []).append(a)
    sira = [x[0] for x in PROFIL_ESIKLERI]
    kontroller, esiksiz = [], []
    for no, (a, ad) in enumerate(kart_kontrol_sirasi(), ilk_no):
        kurallar = []
        for u in uyeler.get(a, (a,)):
            esikler = sorted(esik_of.get(u, []), key=sira.index)
            yakala = [e for e in esikler if e not in ONERI_ESIK_ANAHTARLARI]
            oneri = [e for e in esikler if e in ONERI_ESIK_ANAHTARLARI]
            ana = yakala[0] if yakala else None
            ac = PROFIL_ESIK_ACIKLAMA.get(ana) or {}
            kurallar.append({
                "anahtar": u, "ad": KURAL_FORM_AD.get(u, pk.get(u, (u, u))[1]),
                "olcut": kurallar_metin.get(u, ""),
                # Formda "Neye bakıyor" ve "Yakalanırsa" bu parcalardan: nedir,
                # onemli (neden sorun), kapsam, ornek, yakalanirsa.
                "parca": kontrol_parcalari(u),
                "sonuc": (ac.get("sonuc") or KURAL_SONUC_ADI.get(u)
                          or NE_OLACAK.get(pk[u][2], "")) if u in pk else "",
                "esik": ana, "oneri": oneri})
        # BUTUN kontroller ve kurallar formda: esigi olmayan da gorunur
        # (satirinda "eşik yok"); esiksiz listesi yalniz sayim icin.
        if not any(k["esik"] or k["oneri"] for k in kurallar):
            esiksiz.append({"no": no, "ad": ad})
        kontroller.append({"no": no, "ad": ad, "kisa": KONTROL_FORM_KISA.get(a, ""),
                           "kurallar": kurallar})
    return kontroller, esiksiz


def esik_degisiklik_notu(durum):
    """Varsayilandan farkli esikler (kartta ve metinde)."""
    simdiki, varsayilan = profil_esikleri(durum), _esik_varsayilan(durum)
    parca = ["%s %s (önerilen %s)" % (esik_adi(a, kontrol), _esik_metni(birim, simdiki[a]),
                                        _esik_metni(birim, varsayilan[a]))
             for a, kontrol, _an, birim, _x, _y in PROFIL_ESIKLERI
             if abs(float(simdiki[a]) - float(varsayilan[a])) > 1e-12]
    return ("Değiştirilen eşikler: " + "; ".join(parca) + ".") if parca else ""


def veri_profili_girdi(durum, mesaj, yeniden_sor=False):
    """02.1'e girilince esik formu acilir. Form gonderilince ({"dogrulama":
    {"adim": "veri_profili", "esikler": {...}}}) esikler dogrulanir ve
    kaydedilir; yazarak onayda mevcut esikler gecerli."""
    karar = durum.get("_dogrulama_karari")
    if not yeniden_sor and isinstance(karar, dict) and karar.get("adim") == "veri_profili" \
            and isinstance(karar.get("esikler"), dict):
        durum.pop("_dogrulama_karari", None)
        esik, hata = esik_dogrula(karar["esikler"])
        if hata:
            durum["_secim_alani"] = esik_formu(durum, hata)
            return False, hata
        p = durum.get("profil") or {}
        p["esikler"] = esik
        durum["profil"] = p
        durum["_secim_alani"] = None
        return True, None
    if not yeniden_sor and (mesaj or "").strip():
        try:
            from fe_agent import niyet_kural
            if niyet_kural.coz(mesaj).get("aksiyon") == "onay":
                durum["_secim_alani"] = None
                return True, None
        except Exception:
            pass
    durum["_secim_alani"] = esik_formu(durum)
    return False, ESIK_METNI


# ===========================================================================
# 02.1 AD TABANLI KONTROLLER: kolon adinin parcalari, 01.2.4'te onaylanan
# donem anlam turleri ve kolon kartlari (OLCU, ISTATISTIK) ile.
#   gelecek_pencere : donem parcasinin turu ileriye bakiyor (sizinti riski)
#   pencere         : ayni olcunun kisa ve uzun "Son" penceresi celisiyor
#   tutar_adet      : adet 0 iken tutar dolu; en buyuk ortalamadan kucuk
# Ciftler adin yalniz bir parcasiyla ayrilan kolonlardir. Ad parcalari
# 01.2.4.4'ten ONCEKI (eski) adlardan okunur: turler eski adla saklidir.
# ===========================================================================
_ADET_PARCA = {"CNT", "COUNT", "ADET", "NUM", "SAY", "SAYI", "NB", "NO_OF"}
_TUTAR_PARCA = {"AMT", "AMOUNT", "TUTAR", "SUM", "TOT", "TOTAL", "TOPLAM", "VOL", "HACIM"}
_MAKS_PARCA = {"MAX", "MAKS", "MAXIMUM", "ENBUYUK"}
_MIN_PARCA = {"MIN", "MINIMUM", "ENKUCUK"}
_ORT_PARCA = {"AVG", "ORT", "MEAN", "ORTALAMA", "MED", "MEDIAN", "AVERAGE"}


def _istat_sinifi(metin):
    """Kolon kartinin ISTATISTIK alanindan: ort, maks, min, toplam, adet."""
    t = profil_ek_kucuk(metin)
    if not t:
        return ""
    if "ortalama" in t or "medyan" in t or "ortanca" in t:
        return "ort"
    if "en büyük" in t or "maks" in t or "en yüksek" in t:
        return "maks"
    if "en küçük" in t or "min" in t or "en düşük" in t:
        return "min"
    if "toplam" in t:
        return "toplam"
    if "adet" in t or "sayı" in t or "sayısı" in t:
        return "adet"
    return ""


def _olcu_sinifi(metin):
    """Kolon kartinin OLCU alanindan: adet ya da tutar."""
    t = profil_ek_kucuk(metin)
    if not t:
        return ""
    if "adet" in t or "sayı" in t:
        return "adet"
    if "tutar" in t or "tl" in t.split() or "para" in t or "bakiye" in t or "₺" in t:
        return "tutar"
    return ""


def profil_ek_kucuk(metin):
    from fe_agent import profil_ek
    return profil_ek._tr_kucuk(str(metin or "").strip())


def _ad_kontrolleri(durum, df, adaylar, ek):
    """ek'e gelecek_pencere, pencere, tutar_adet (ve donem_tur_var,
    pencere_cift, tutar_cift) ekler. Hata olursa kontrol bos kalir."""
    from fe_agent import profil_ek
    ek["gelecek_pencere"], ek["pencere"], ek["tutar_adet"] = [], [], []
    ek["donem_tur_var"], ek["pencere_cift"], ek["tutar_cift"] = False, 0, 0
    try:
        from fe_agent import akis_faz01, donem_tur, parca as parca_mod
        eski = {str(y): str(e) for e, y in (durum.get("_amp_yeniden_ad") or {}).items()}
        try:
            kolon_tur = akis_faz01._kolon_donem_turleri(durum) or {}
        except Exception:
            kolon_tur = {}
        ozel = {}
        for _kalip, turler in (durum.get("donem_anlam_turleri") or {}).items():
            if isinstance(turler, dict):
                ozel.update({t: x for t, x in turler.items()
                             if t not in donem_tur.SABIT_KODLAR and isinstance(x, dict)})
        istat = {k: _istat_sinifi(v) for k, v in _kart_alani(durum, "ISTATISTIK").items()}
        olcu = {k: _olcu_sinifi(v) for k, v in _kart_olculeri(durum).items()}
        sayisal = [k for k in adaylar if pd.api.types.is_numeric_dtype(df[k])
                   and not pd.api.types.is_bool_dtype(df[k])]

        def kart(sozluk, k):
            return sozluk.get(k) or sozluk.get(eski.get(k, k)) or ""

        # Kolon -> (eski ad parcalari, {parca: (tur, yon, bicim)})
        bilgi = {}
        for k in adaylar:
            e = eski.get(k, k)
            turler = kolon_tur.get(e) or kolon_tur.get(k) or {}
            t = {}
            for parca, tur in turler.items():
                if tur:
                    yon, bicim = donem_tur.tur_bilgisi(tur, ozel)
                    t[parca] = (tur, yon, bicim)
            bilgi[k] = ([str(x).upper() for x in parca_mod.toklar(e)], t)
        ek["donem_tur_var"] = any(t for _p, t in bilgi.values())

        # GELECEK PENCERESI
        for k in adaylar:
            parcalar = []
            for parca, (tur, yon, _b) in bilgi[k][1].items():
                if yon in ("gelecek", "iki"):
                    ad = donem_tur.TUR_ADI.get(tur) or str((ozel.get(tur) or {}).get("ad") or tur)
                    parcalar.append({"parca": parca, "tur": tur,
                                     "tur_adi": "%s (%s)" % (ad, donem_tur.YON_ADI.get(yon, yon))})
            if parcalar:
                ek["gelecek_pencere"].append({"kolon": k, "parcalar": parcalar})

        def stat(k):
            """Kolonun istatistik sinifi: kart, yoksa ad parcalari."""
            s_ = kart(istat, k)
            if s_:
                return s_
            tok = set(bilgi[k][0])
            if tok & _ORT_PARCA:
                return "ort"
            if tok & _MAKS_PARCA:
                return "maks"
            if tok & _MIN_PARCA:
                return "min"
            if tok & _TUTAR_PARCA:
                return "toplam"
            if tok & _ADET_PARCA:
                return "adet"
            return ""

        negatifsiz = {}

        def neg_yok(k):
            if k not in negatifsiz:
                negatifsiz[k] = not bool((pd.to_numeric(df[k], errors="coerce") < 0).any())
            return negatifsiz[k]

        # PENCERE TUTARLILIGI: yalniz Son turu (gecmise bakan pencere).
        kova = {}
        for k in sayisal:
            tok, t = bilgi[k]
            for i, parca in enumerate(tok):
                x = t.get(parca) or t.get(parca.lower()) or next(
                    (v for pp, v in t.items() if pp.upper() == parca), None)
                if not x or x[1] != "gecmis" or x[2] != "pencere":
                    continue
                m = re.search(r"\d+", parca)
                if not m:
                    continue
                birim = re.sub(r"\d+", "#", parca)
                anahtar = tuple(tok[:i]) + ("*" + birim,) + tuple(tok[i + 1:])
                kova.setdefault(anahtar, []).append((int(m.group(0)), k))
        ciftler = []
        for uyeler in kova.values():
            uyeler = sorted(set(uyeler))
            for (n1, k1), (n2, k2) in zip(uyeler[:-1], uyeler[1:]):
                if n1 == n2:
                    continue
                s1, s2 = stat(k1), stat(k2)
                if not s1 or s1 != s2 or s1 == "ort":
                    continue
                if s1 in ("toplam", "adet") and not (neg_yok(k1) and neg_yok(k2)):
                    continue
                ciftler.append((k1, k2, "azalan" if s1 == "min" else "artan"))
        ek["pencere_cift"] = len(ciftler)
        ek["pencere"] = _cift_iki_yonlu([x for x in profil_ek.pencere_tutarliligi(df, ciftler)
                                         if x["pay"] >= ILISKI_MIN_PAY])

        # TUTAR / ADET ve EN BUYUK / ORTALAMA: adin tek parcasiyla ayrilan
        # ciftler.
        kova = {}
        for k in sayisal:
            tok = bilgi[k][0]
            for i in range(len(tok)):
                kova.setdefault(tuple(tok[:i]) + ("*",) + tuple(tok[i + 1:]), []).append((tok[i], k))
        adet_tutar, maks_ort = set(), set()
        for uyeler in kova.values():
            if len(uyeler) < 2:
                continue
            for p1, k1 in uyeler:
                for p2, k2 in uyeler:
                    if k1 == k2:
                        continue
                    o1 = kart(olcu, k1) or ("adet" if p1 in _ADET_PARCA else "")
                    o2 = kart(olcu, k2) or ("tutar" if p2 in _TUTAR_PARCA else "")
                    if o1 == "adet" and o2 == "tutar" and (p1 in _ADET_PARCA or p2 in _TUTAR_PARCA):
                        adet_tutar.add((k1, k2))
                    i1 = kart(istat, k1) or ("maks" if p1 in _MAKS_PARCA else "")
                    i2 = kart(istat, k2) or ("ort" if p2 in _ORT_PARCA else "")
                    if i1 == "maks" and i2 == "ort" and (p1 in _MAKS_PARCA or p2 in _ORT_PARCA):
                        maks_ort.add((k1, k2))
        ek["tutar_cift"] = len(adet_tutar) + len(maks_ort)
        ek["tutar_adet"] = _cift_iki_yonlu(
            [x for x in profil_ek.tutar_adet_uyumu(df, sorted(adet_tutar), sorted(maks_ort))
             if x["pay"] >= ILISKI_MIN_PAY])
    except Exception as e:      # ad kontrolleri profili durdurmasin
        ek["ad_kontrol_hata"] = str(e)[:200]
    return ek

def _cift_iki_yonlu(liste):
    """Celisen kolon cifti IKI kolonun da bulgusudur (hangisinin yanlis
    oldugu bilinmez): her bulgu karsi kolon icin de yazilir ("ters")."""
    cikti = []
    for x in liste:
        cikti.append(x)
        t = dict(x)
        t["kolon"], t["karsi"], t["ters"] = x["karsi"], x["kolon"], True
        cikti.append(t)
    return cikti


def egitim_maskesi(durum, df):
    """Train (MS) satirlari (01.4 bolmesi; val, test ve OOT haric). Bolme
    okunamazsa ya da train bossa None: analiz butun satirlarla yapilir."""
    try:
        e = pd.Series(setler(durum, df)["egitim"], index=df.index).fillna(False).astype(bool)
    except Exception:
        return None
    return e if bool(e.any()) else None


def profil_hesapla(durum):
    """Veri profilini TABLONUN TAMAMINDAN (train, val, test ve OOT
    birlikte), orneklemsiz cikarir: dort temel kontrol (sfa.profil_cikar)
    ve ek kontroller (profil_ek). Hedefle ilgili olcumler (Hedefle
    Neredeyse Birebir, neredeyse ayni grupta ayirma gucu) ve ogrenilen her
    sey (cozumler, kirpma siniri) yalniz TRAIN (MS) satirlarindan; kararlar
    ve duzeltmeler butun satirlara uygulanir. Sonuc durum["profil"]."""
    from fe_agent import profil_ek
    import time as _time
    # SURE KAYDI: adim sureleri p["profil_sure"] ve backend log'unda.
    sure, t0 = {}, [_time.time()]

    def _isaret(ad):
        t = _time.time()
        sure[ad] = round(t - t0[0], 1)
        t0[0] = t
    df_tum = asama_df(durum, "01") if updt_modu(durum) else modelleme_df(durum)
    egitim = egitim_maskesi(durum, df_tum)
    df = df_tum
    m = durum["meta"]
    _isaret("veri_okuma")
    # Bolme kolonu (_SPLIT) da hedef, kimlik ve donem gibi incelenmez.
    haric = set(durum.get("haric_kolonlar") or []) | {m.get("target"), m.get("id"), m.get("donem")} \
        | {SPLIT_KOLON}

    esik = profil_esikleri(durum)
    olculer = _kart_olculeri(durum)
    tablo, teshis = sfa_mod.profil_cikar(df, haric=haric, null_esik=esik["cok_bos"],
                                         kimlik_esik=esik["kimlik"],
                                         kategorik_max=esik["kardinalite"],
                                         olcu_kolonlari=[k for k, v in olculer.items()
                                                         if str(v or "").strip()])
    _isaret("temel_kontroller")
    yazildi, yedek = ara_tablo_kaydet(durum, "PROFIL", tablo, "/veri_profili.parquet")
    _isaret("profil_tablosu_yazma")

    p = durum.get("profil") or {}
    p["profil_kapsam"] = {"train": False, "hedef_train": egitim is not None,
                          "satir": int(len(df)), "toplam": int(len(df_tum)),
                          "train_satir": int(egitim.sum()) if egitim is not None else 0}
    temel = set(teshis.get("cok_bos") or []) | set(teshis.get("sabit") or []) \
        | set(teshis.get("kimlik_gibi") or []) | set(teshis.get("yuksek_kardinalite") or [])
    tarihler = [str(k) for k in teshis.get("tarih") or [] if k not in temel]
    temel |= set(teshis.get("tarih") or [])
    adaylar = [str(k) for k in df.columns if k not in haric and k not in temel]
    ek = profil_ek.ek_kontroller(df, adaylar, donem=m.get("donem"), kimlik=m.get("id"),
                                 hedef=m.get("target"), olculer=olculer,
                                 esik=esik, tarihler=tarihler, hedef_maske=egitim,
                                 satir_haric={SPLIT_KOLON})
    _isaret("ek_kontroller")
    # TARIH KOLONLARI: en eski / en yeni tarih (ozel tarih kodlari haric),
    # yazilis bicimi ve kod tarihler (Tarih Kolonu satirinin bulgusu).
    ek["tarih_aralik"], ek["tarih_tur"] = {}, {}
    for k in teshis.get("tarih") or []:
        tur = profil_ek.tarih_turu(df[k])
        ek["tarih_tur"][str(k)] = tur or ""
        d = profil_ek.tarih_serisi(df[k], tur)
        d = d.dropna() if d is not None else pd.Series(dtype="datetime64[ns]")
        if len(d):
            ek["tarih_aralik"][str(k)] = [str(d.min())[:10], str(d.max())[:10]]
    _ad_kontrolleri(durum, df, adaylar, ek)
    # SETLER ARASI CAKISMA (01.4 bolmesi): Train ile val, test ve OOT.
    try:
        st = setler(durum, df_tum)
    except Exception:
        st = None
    ek["set_cakisma"] = (profil_ek.set_cakismasi(df_tum, st, m.get("id"), m.get("donem"),
                                                 haric={SPLIT_KOLON}) if st else None)
    try:
        a_ = bolme_ayarlari(durum)
        ek["set_bolme"] = {"birim": a_.get("birim"), "test_tanim": a_.get("test_tanim")}
    except Exception:
        ek["set_bolme"] = {}
    # Sabit kolonun tek degeri (kartta bulgu olarak).
    ek["sabit_deger"] = {}
    for k in teshis.get("sabit") or []:
        dolu = df[k].dropna()
        ek["sabit_deger"][k] = profil_ek.deger_metni(dolu.iloc[0]) if len(dolu) else "boş"
    # COZUM ONERILERI: uretime girmez denen kolonlar icin (tablo butun
    # satirlarla, olcum ve ogrenme train'de; bolme okunamadiysa butun
    # satirlar). Kolon bazinda oneriyi dil modeli verir (asagida).
    from fe_agent import kolon_cozum as kc
    target = (durum.get("meta") or {}).get("target")
    p["cozum_oneri"] = kc.oneriler(df_tum, teshis, esik["kardinalite"],
                                   y=df_tum[target] if target in df_tum.columns else None,
                                   egitim=egitim)
    p["cozum_oneri"].update(_tarih_onerileri(df_tum, teshis, m.get("donem"),
                                             set(p["cozum_oneri"])))
    _isaret("tarih_ad_set_cozum")
    # KOLON BAZINDA ONERI: kod kolonun sayilarina bakar (veri_oneri);
    # anlam isteyen LLM_KONTROLLERI dil modeline sorulur. p["llm_oneri"]
    # ikisini birlikte tasir (kaynak "kod" / "dil modeli" / "kural").
    for v in p["cozum_oneri"].values():
        v["kaynak"] = "kod"
    try:
        p["veri_oneri"] = _veri_onerileri(durum, ek, df_tum, egitim)
    except Exception as e:      # kural onerisi gecerli
        p["veri_oneri"] = {}
        ek["veri_oneri_hata"] = str(e)[:200]
    p["llm_oneri"] = _profil_llm_onerileri(durum, p, ek, teshis)
    _isaret("dil_modeli_onerileri")
    for k, v in p["cozum_oneri"].items():
        o = (p["llm_oneri"].get(v.get("kontrol")) or {}).get(k) or {}
    ek["ayni_gruplar"] = _ayni_gruplari(durum, ek, p, df_tum)
    _isaret("ayni_gruplar")
    p.pop("kod_oneri", None)
    p["profil_teshis"] = teshis
    p["profil_ek"] = ek
    p["profil_dataset"] = yazildi
    # ONCEKI SECIMLER: profil yeniden cikarilinca kartta her bulguda dil
    # modelinin (yoksa kuralin) YENI onerisi secili gelir. Onceki onaydan
    # yalniz kullanicinin oneriden BILEREK farkli sectikleri (p["secim_sapma"])
    # tasinir; hala gecerli olanlar. Eski oturumda sapma kaydi yoksa hicbir
    # eski secim tasinmaz (eski tam secimler yeni oneriyi ezmesin).
    sapma = p.get("secim_sapma") if isinstance(p.get("secim_sapma"), dict) else {}
    uyeler = {g["id"]: set(g["uyeler"]) for g in ek["ayni_gruplar"]}
    p["ayni_secim"] = {k: v for k, v in (sapma.get("ayni") or {}).items()
                       if v in uyeler.get(k, set())}
    p["profil_karar"] = dict(sapma.get("karar") or {})
    teshis["ayni_icerik"] = _ayni_kopyalar(p)
    # Sapma yalniz hala karar isteyen kolonlar icin gecerli.
    p["profil_karar"] = {k: v for k, v in p["profil_karar"].items()
                         if k in set(_karar_adaylari(p))
                         and v in (PROFIL_KARAR_TUT, PROFIL_KARAR_CIKAR)}
    teshis["ayni_icerik"] = _ayni_kopyalar(p)
    p["cozum_secim"] = {k: v for k, v in (sapma.get("cozum") or {}).items()
                        if v in ((p["cozum_oneri"].get(k) or {}).get("secenekler") or [])}
    durum["profil"] = p
    duz_oneri = duzeltme_onerileri(durum)
    eski_duz = sapma.get("duzeltme") or {}
    p["duzeltme_secim"] = {a: {k: c for k, c in (eski_duz.get(a) or {}).items()
                               if c in ((duz_oneri.get(a) or {}).get(k) or {}).get("secenekler", [])}
                           for a in duz_oneri}

    # Feature tablosunun kolon ozeti: veri seti secilirken cikarilmisti,
    # burada tekil sayisi ve kesin null orani ile tamamlaniyor. Ozet hic
    # yoksa (eski oturum) su an okunan tablodan uretiliyor.
    if not p.get("kolon_ozet"):
        p["kolon_ozet"] = kolon_ozeti_cikar(df)
    p["kolon_ozet"] = kolon_ozeti_tamamla(p, tablo, df)

    # EKSIK DEGER sekmesi: yalnizca ilk 20 satir + dagilim ozeti oturuma
    # yazilir; tam tablo yukarida dataset'e / yedege yazildi.
    ilk20, null_ozet, ek_alan = _eksik_ozeti(tablo, len(df), asiri=esik["cok_bos"])
    p["eksik_ilk20"] = ilk20
    p["null_ozet"] = null_ozet
    p.update(ek_alan)
    # Kartin satir sayisi ve kayit yeri (02.1 Veri Profili karti).
    p["profil_satir"] = int(len(df))
    p["profil_kayit"] = _kayit_metni(yazildi, yedek)
    _isaret("ozet")
    sure["toplam"] = round(sum(sure.values()), 1)
    p["profil_sure"] = sure
    print("02.1 profil süreleri (sn): %s; dil modeli: %s; satır %s, kolon %s" % (
        json.dumps(sure, ensure_ascii=False), json.dumps(p.get("llm_oneri_sayim") or {}),
        len(df), len(df.columns)), flush=True)
    durum["profil"] = p
    return p


TARIH_YAZILIS = {"metin": "Metin olarak yazılmış (YYYY-AA-GG)",
                 "metin_gay": "Metin olarak yazılmış (GG.AA.YYYY)",
                 "sayi": "Sayı olarak yazılmış (YYYYAAGG)"}


def _tarih_onerileri(df, teshis, donem, dolu):
    """Tarih kolonlari icin cozum: donem sonuna gun farki (donem kolonu
    tarih olarak okunabiliyorsa), yoksa yalniz Çıkar. Baska kontrolde
    (eksik orani yuksek) cozumu olan ve sabit tarih kolonu atlanir."""
    from fe_agent import profil_ek
    sabit = set(teshis.get("sabit") or [])
    son = profil_ek.donem_sonu(df[donem]) if donem and donem in df.columns else None
    cikti = {}
    for k in teshis.get("tarih") or []:
        if k in dolu or k in sabit:
            continue
        if son is not None:
            cikti[k] = {"kontrol": "tarih", "secenekler": ["gun_farki", "cikar"],
                        "oneri": "gun_farki",
                        "gerekce": "Ham tarih modelde anlamlı değil; dönem sonuna gün farkı "
                                   "her dönemde aynı ölçüde kalır."}
        else:
            cikti[k] = {"kontrol": "tarih", "secenekler": ["cikar"], "oneri": "cikar",
                        "gerekce": "Dönem kolonu yok ya da tarih olarak okunamadı; gün farkı "
                                   "hesaplanamaz."}
    return cikti


AYNI_KURAL_GEREKCESI = ("Başka kontrolde çıkarılmayan, en az düzeltme ve karar isteyen "
                        "kolon önerildi; eşitse adı kısa olan.")
# Uyenin baska kontrollerdeki durumu (ayni icerikli grupta siralama icin).
_UYE_KARAR = ("tarih_sonra", "baskin", "donem", "sicrama", "kayma")


def _uye_durumlari(ek, p):
    """{kolon: {"cikar": sebep ya da "", "duzeltme": n, "karar": n,
    "bulgular": [metin]}}: ayni icerikli grup uyelerinin profilin oteki
    kontrollerindeki bulgulari. Cikar: varsayilani Çıkar olan sizinti
    kontrolu (kullanici Tut demediyse) ya da kullanicinin onceki Çıkar
    karari."""
    ad = {x[0]: x[1] for x in PROFIL_KONTROLLERI}
    karar = p.get("profil_karar") if isinstance(p.get("profil_karar"), dict) else {}
    b = _ek_bulgulari(p, ek=ek, kopya_suz=False)
    cikti = {}

    def uye(k):
        return cikti.setdefault(k, {"cikar": "", "duzeltme": 0, "karar": 0, "bulgular": []})
    cikar_oneri = _karar_cikar_sebebi(p, ek)
    for a, kolonlar in b.items():
        if a in ("ayni_icerik", "yakin_icerik"):
            continue
        for k, metin in kolonlar.items():
            u = uye(k)
            u["bulgular"].append("%s: %s" % (ad.get(a, a), metin))
            if cikar_oneri.get(k) == a and karar.get(k) != PROFIL_KARAR_TUT:
                u["cikar"] = u["cikar"] or "%s kontrolünde Çıkar önerilir" % ad.get(a, a)
            elif a in DUZELTME_KONTROLLERI and a != "ondalik":
                u["duzeltme"] += 1
            elif a in _UYE_KARAR:
                u["karar"] += 1
    for k, v in karar.items():
        if v == PROFIL_KARAR_CIKAR:
            uye(k)["cikar"] = uye(k)["cikar"] or "Kararınızla çıkarıldı"
    return cikti


def _kural_sirasi(uyeler, durum_):
    """Dil modeli yoksa: once cikarilmayan, sonra az duzeltme ve karar
    isteyen; esitlikte tablodaki sira. Bilgi notlari sirayi etkilemez
    (cogu ad eslesmesine bagli, ayni degerli kopyada da gecerli)."""
    bos = {"cikar": "", "duzeltme": 0, "karar": 0, "bulgular": []}
    return sorted(uyeler, key=lambda u: (
        bool((durum_.get(u) or bos)["cikar"]),
        (durum_.get(u) or bos)["duzeltme"] + (durum_.get(u) or bos)["karar"],
        len(u), uyeler.index(u)))


def _hedef_gucleri(durum, df, kolonlar):
    """{kolon: ayirma gucu}: iki sinifli hedefte EGITIM satirlarinda tek
    degiskenli AUC (ya da 1 eksi AUC; bos deger en kucugun altina). Hedef
    iki sinifli degilse ya da bolme okunamazsa {}."""
    from fe_agent import profil_ek
    target = (durum.get("meta") or {}).get("target")
    if df is None or not target or target not in df.columns:
        return {}
    y = pd.to_numeric(df[target], errors="coerce")
    if not set(y.dropna().unique().tolist()) <= {0, 1} or y.nunique() < 2:
        return {}
    try:
        egitim = pd.Series(setler(durum, df)["egitim"], index=df.index).fillna(False).astype(bool)
    except Exception:
        return {}
    m = egitim & y.notna()
    if not m.any():
        return {}
    yy = y[m].astype(int)
    cikti = {}
    for k in kolonlar:
        if k not in df.columns:
            continue
        x = pd.to_numeric(df.loc[m, k], errors="coerce")
        if not x.notna().any():
            continue
        a = profil_ek._auc(x.fillna(float(x.min()) - 1).to_numpy(dtype=float), yy)
        if a is not None:
            cikti[k] = max(a, 1 - a)
    return cikti


def _ayni_gruplari(durum, ek, p, df=None):
    """Ayni icerikli gruplar ve dil modelinin kalacak kolon onerisi:
    [{"id", "uyeler", "oneri", "gerekce", "kaynak"}]. id: grubun tablodaki
    ilk kolonu. Ayni uyelerle onceden alinmis dil modeli onerisi tekrar
    sorulmaz (esik degisince yeniden hesaplanan profilde)."""
    ham = ek.get("ayni_icerik") or []
    yakin = ek.get("yakin_icerik") or []
    if not ham and not yakin:
        return []
    onceki = {}           # dil modeli onerisi kullanilmaz
    durum_ = _uye_durumlari(ek, p)
    gruplar = [{"id": g["kalan"], "uyeler": [g["kalan"]] + list(g["kopyalar"])} for g in ham]
    # Neredeyse ayni gruplar: id "yakin:<ilk kolon>" (birebir grubun id'siyle
    # cakismasin); iliski ilk kolona gore.
    for g in yakin:
        x = {"id": "yakin:" + g["kalan"], "uyeler": [g["kalan"]] + list(g["kopyalar"]),
             "tur": "yakin", "iliski": g.get("iliski") or {}}
        x["iliski_metni"] = "; ".join(_iliski_cumlesi(x, g["kalan"], k) for k in g["kopyalar"])
        gruplar.append(x)
    aciklama = _aciklamalar(durum)
    # Uyelerin oteki kontrollerdeki durumu: baska yerde cikarilan uye
    # secilmez, en az degisiklik isteyen once gelir. Durum degisince (imza)
    # dil modeline yeniden sorulur.
    for g in gruplar:
        g["elenen"] = {u: (durum_.get(u) or {}).get("cikar") for u in g["uyeler"]
                       if (durum_.get(u) or {}).get("cikar")}
        g["uye_bulgu"] = {u: list((durum_.get(u) or {}).get("bulgular") or [])
                          for u in g["uyeler"] if (durum_.get(u) or {}).get("bulgular")}
        g["imza"] = json.dumps([g["uyeler"], g["elenen"], g["uye_bulgu"],
                                [aciklama.get(u, "") for u in g["uyeler"]]],
                               ensure_ascii=False, sort_keys=True)
    ayni_mi = lambda g: (g["id"] in onceki and onceki[g["id"]].get("uyeler") == g["uyeler"]
                         and onceki[g["id"]].get("imza") == g["imza"]
                         and onceki[g["id"]].get("sira"))
    # NEREDEYSE AYNI gruplarda kalacak kolonu HEDEF belirler: egitim
    # satirlarinda hedefi daha iyi ayiran kolon once (baska kontrolde
    # cikarilan yine sona). Hedef iki sinifli degilse dil modeline sorulur.
    guc = _hedef_gucleri(durum, df, [u for g in gruplar if g.get("tur") == "yakin"
                                      for u in g["uyeler"]])
    for g in gruplar:
        if g.get("tur") == "yakin" and all(u in guc for u in g["uyeler"]):
            g["guc"] = {u: round(guc[u], 6) for u in g["uyeler"]}
            # Ayirma gucleri esitse (ör. biri otekinin sabit kati: sira ayni)
            # hedef karar vermez; anlam ve bulgulara gore dil modeli siralar.
            g["guc_esit"] = max(g["guc"].values()) - min(g["guc"].values()) < 1e-4
    hedefle = lambda g: bool(g.get("guc")) and not g.get("guc_esit")
    oneri = {}
    for g in gruplar:
        if hedefle(g):
            sira = sorted(g["uyeler"], key=lambda u: (-g["guc"][u], g["uyeler"].index(u)))
            ilk = [u for u in sira if u not in g["elenen"]] or sira
            gerekce = ("%s hedefi eğitim satırlarında daha iyi ayırıyor: ayırma gücü (AUC) %s"
                       % (ilk[0], "; ".join("%s %s" % (u, _yuzde_metni(g["guc"][u])) for u in sira)))
            if ilk[0] != sira[0]:
                gerekce += ". %s başka bir kontrolde çıkarıldığı için kalmaz" % sira[0]
            kaynak = "hedef"
        elif ayni_mi(g):
            o = onceki[g["id"]]
            sira, gerekce, kaynak = list(o["sira"]), o.get("gerekce", ""), "dil modeli"
        elif g["id"] in oneri:
            sira, gerekce, kaynak = list(oneri[g["id"]]["sira"]), oneri[g["id"]]["gerekce"], \
                "dil modeli"
        else:
            sira, gerekce, kaynak = _kural_sirasi(g["uyeler"], durum_), AYNI_KURAL_GEREKCESI, \
                "kural"
        # Kod denetimi: baska kontrolde cikarilan uye sona (dil modeli
        # koymadiysa bile).
        sira = [u for u in sira if u not in g["elenen"]] + [u for u in sira if u in g["elenen"]]
        if g.get("guc_esit"):
            gerekce = ("Kolonların hedefi ayırma gücü eşit (AUC %s); karar kurala "
                       "göre. " % _yuzde_metni(list(g["guc"].values())[0])) + (gerekce or "")
        g.update({"sira": sira, "oneri": sira[0], "gerekce": gerekce, "kaynak": kaynak})
    return gruplar


def _ayni_kalan(p, g):
    """Grupta kalan kolon: kullanicinin secimi, yoksa sirada ilk. Secilen
    kolon baska bir kontrolde Çıkar denmisse sirada cikarilmayan ilk kolon
    kalir (cikarilacak kolonu secmek bosa karar olur)."""
    karar = p.get("profil_karar") if isinstance(p.get("profil_karar"), dict) else {}
    cikar = {k for k, v in karar.items() if v == PROFIL_KARAR_CIKAR}
    s = (p.get("ayni_secim") or {}).get(g["id"])
    sira = [u for u in (g.get("sira") or [g.get("oneri")] + list(g["uyeler"]))
            if u in g["uyeler"]]
    aday = ([s] if s in g["uyeler"] else []) + [u for u in sira if u != s]
    for u in aday:
        if u not in cikar:
            return u
    return aday[0] if aday else g["oneri"]


def _ayni_kopyalar(p):
    """Ayni icerikli gruplarda kalmayan (uretime girmeyen) kolonlar."""
    ek = p.get("profil_ek") or {}
    gruplar = ek.get("ayni_gruplar")
    if gruplar is None:      # eski calisma: ilk kolon kalir
        return sorted({k for g in (ek.get("ayni_icerik") or []) for k in g["kopyalar"]})
    return sorted({u for g in gruplar for u in g["uyeler"] if u != _ayni_kalan(p, g)})


def _karar_adaylari(p):
    """Karar isteyen kolonlar (sira korunur): neredeyse sabit, donemde bos
    ya da sabit, donemler arasi eksik sicramasi. Ayni icerikli gruplarda kalmayan kolon karar istemez."""
    ek = p.get("profil_ek") or {}
    kopya = set(_ayni_kopyalar(p))
    ad = []
    for a in KARAR_KONTROLLERI:
        ad += [x["kolon"] for x in (ek.get(a) or [])]
    return [k for k in dict.fromkeys(ad) if k not in kopya]


def _karar_varsayilan(p, ek=None):
    """{kolon: "cikar"}: kullanici karar vermediyse Çıkar onerilen kolonlar.
    Oneri kolon bazinda dil modelinden (p["llm_oneri"]); yoksa kural
    (sizinti kontrollerinde Çıkar, digerlerinde Tut). Kolon birden cok karar
    kontrolundeyse biri Çıkar diyorsa Çıkar."""
    return {k: PROFIL_KARAR_CIKAR for k in _karar_cikar_sebebi(p, ek)}


def _karar_cikar_sebebi(p, ek=None):
    """{kolon: kontrol}: Çıkar onerilen kolon ve onu oneren kontrol."""
    ek = (p.get("profil_ek") or {}) if ek is None else ek
    lo = p.get("llm_oneri") if isinstance(p.get("llm_oneri"), dict) else {}
    cikti = {}
    for a in KARAR_KONTROLLERI:
        for x in ek.get(a) or []:
            k = x["kolon"]
            o = (lo.get(a) or {}).get(k) or {}
            v = o.get("oneri") if (o.get("kaynak") == "kod" and o.get("oneri")
                                   in (PROFIL_KARAR_TUT, PROFIL_KARAR_CIKAR)) \
                else _karar_kurali(a)
            if v == PROFIL_KARAR_CIKAR:
                cikti.setdefault(k, a)
    return cikti


def secim_sapmalari(durum):
    """Kullanicinin oneriden farkli sectikleri: {"karar": {kolon: tut|cikar},
    "cozum": {kolon: kod}, "duzeltme": {kontrol: {kolon: kod}}, "ayni":
    {grup id: kolon}}. Profil yeniden cikarilinca yalniz bunlar tasinir;
    gerisi yeni oneriyi alir."""
    p = durum.get("profil") or {}
    vars_ = _karar_varsayilan(p)
    karar = p.get("profil_karar") if isinstance(p.get("profil_karar"), dict) else {}
    cikti = {"karar": {k: v for k, v in karar.items()
                       if v != vars_.get(k, PROFIL_KARAR_TUT)}}
    oneri = cozum_onerileri(durum)
    cikti["cozum"] = {k: c for k, c in (p.get("cozum_secim") or {}).items()
                      if k in oneri and c != oneri[k].get("oneri")}
    duz = duzeltme_onerileri(durum)
    cikti["duzeltme"] = {}
    for a, kolonlar in (p.get("duzeltme_secim") or {}).items():
        for k, c in (kolonlar or {}).items():
            o = (duz.get(a) or {}).get(k)
            if o and c != o.get("oneri"):
                cikti["duzeltme"].setdefault(a, {})[k] = c
    gruplar = {g["id"]: g for g in ((p.get("profil_ek") or {}).get("ayni_gruplar") or [])}
    cikti["ayni"] = {gid: v for gid, v in (p.get("ayni_secim") or {}).items()
                     if gid in gruplar and v != gruplar[gid].get("oneri")}
    return cikti


def profil_karar_kolonlari(durum):
    return _karar_adaylari(durum.get("profil") or {})


def profil_karar_var(durum):
    """Kartta karar istenecek mi: Tut ya da Çıkar kolonu ya da ayni icerikli
    grup var."""
    p = durum.get("profil") or {}
    return bool(profil_karar_kolonlari(durum) or (p.get("profil_ek") or {}).get("ayni_gruplar")
                or cozum_secilebilir(durum) or duzeltme_onerileri(durum)
                or satir_onerileri(durum))


def _profil_karar_bekliyor(durum):
    p = durum.get("profil") or {}
    karar = p.get("profil_karar") if isinstance(p.get("profil_karar"), dict) else {}
    return any(k not in karar for k in profil_karar_kolonlari(durum))


def veri_profili_plan(durum):
    """Esikler onaylaninca (veri_profili_girdi) profil tablonun tamamindan
    onaylanan esiklerle cikarilir. Karar isteyen kolon yoksa ONAY SORULMAZ,
    ilk durak Kural Tabanli Degisken Uretimi'nin planidir. Varsa kart her
    kolon icin Tut ya da Çıkar ister."""
    profil_hesapla(durum)
    durum["_profil_hazir"] = True
    if profil_karar_var(durum):
        durum["_secim_alani"] = profil_karti(durum, karar=True)
        return profil_metni(durum, karar=True)
    durum["_plan_otomatik"] = True
    return profil_metni(durum)


def veri_profili_uygula(durum):
    """Karar govdesi {"cikar": [kolon, ...]}: listedeki karar kolonlari
    cikar, digerleri tutulur. Govde gelmezse (yazarak onay) onceki karar,
    yoksa Tut."""
    karar = durum.pop("_dogrulama_karari", None)
    if not durum.pop("_profil_hazir", False):
        profil_hesapla(durum)
    p = durum["profil"]
    adaylar = profil_karar_kolonlari(durum)
    onceki = p.get("profil_karar") if isinstance(p.get("profil_karar"), dict) else {}
    if isinstance(karar, dict) and isinstance(karar.get("cikar"), list):
        cikar = {str(k) for k in karar["cikar"]} & set(adaylar)
    else:
        vars_ = _karar_varsayilan(p)
        cikar = {a for a in adaylar if onceki.get(a, vars_.get(a)) == PROFIL_KARAR_CIKAR}
    # Ayni icerikli gruplarda kalacak kolon: {"ayni": {grup id: kolon}}.
    gruplar = (p.get("profil_ek") or {}).get("ayni_gruplar") or []
    if isinstance(karar, dict) and isinstance(karar.get("ayni"), dict):
        uyeler = {g["id"]: set(g["uyeler"]) for g in gruplar}
        p["ayni_secim"] = {str(k): str(v) for k, v in karar["ayni"].items()
                           if str(v) in uyeler.get(str(k), set())}
    p["profil_teshis"]["ayni_icerik"] = _ayni_kopyalar(p)
    # Kalan kolon degisince karar adaylari degisebilir: kartta gosterilmeyen
    # yeni aday varsayilan kararini alir (sizinti kontrolunde Çıkar).
    gosterilen = set(adaylar)
    adaylar = _karar_adaylari(p)
    vars_ = _karar_varsayilan(p)
    cikar |= {a for a in adaylar if a not in gosterilen
              and onceki.get(a, vars_.get(a)) == PROFIL_KARAR_CIKAR}
    p["profil_karar"] = {a: (PROFIL_KARAR_CIKAR if a in cikar else PROFIL_KARAR_TUT)
                         for a in adaylar}
    # Karar sonrasi kalan kolon: secilen kolon Çıkar denmisse siradaki
    # kalir (kopyalar yeniden).
    p["profil_teshis"]["ayni_icerik"] = _ayni_kopyalar(p)
    # COZUMLER: {"cozum": {kolon: kod}}; gelmeyen kolonda onceki secim ya
    # da oneri. Secilenler egitim satirlarindan ogrenilir.
    oneri = cozum_onerileri(durum)
    if isinstance(karar, dict) and isinstance(karar.get("cozum"), dict):
        sec = dict(p.get("cozum_secim") or {})
        for k, c in karar["cozum"].items():
            if c in ((oneri.get(str(k)) or {}).get("secenekler") or []):
                sec[str(k)] = str(c)
        p["cozum_secim"] = sec
    # DUZELTMELER: {"duzeltme": {kontrol: {kolon: kod}}}.
    duz_oneri = duzeltme_onerileri(durum)
    sat_oneri = satir_onerileri(durum)
    if isinstance(karar, dict) and isinstance(karar.get("duzeltme"), dict):
        sec = {a: dict(v) for a, v in (p.get("duzeltme_secim") or {}).items()}
        # Satir cikarma secimleri (Tekrar Eden Satir, Setler Arasi Cakisma)
        # ayni alanla gelir; ayri saklanir (p["satir_secim"]).
        sat = {a: dict(v) for a, v in (p.get("satir_secim") or {}).items()}
        for a, kolonlar in karar["duzeltme"].items():
            if not isinstance(kolonlar, dict):
                continue
            for k, c in kolonlar.items():
                if c in (((duz_oneri.get(str(a)) or {}).get(str(k)) or {}).get("secenekler") or []):
                    sec.setdefault(str(a), {})[str(k)] = str(c)
                elif c in (((sat_oneri.get(str(a)) or {}).get(str(k)) or {}).get("secenekler") or []):
                    sat.setdefault(str(a), {})[str(k)] = str(c)
        p["duzeltme_secim"] = sec
        p["satir_secim"] = sat
    p["secim_sapma"] = secim_sapmalari(durum)
    durum["profil"] = p
    _cozum_ogren(durum)
    # UPDT VERI: duzeltmeler ve cozum kolonlari dogrudan veriye yazilir
    # (02.1 sonu). Kaynak her zaman 01 sonu (geri donulduyse BAZ'dan).
    if updt_modu(durum):
        if _asama_katkisi(durum, "02.1"):
            df21 = girmez_dusur(durum, cozum_kolonlari_ekle(
                durum, satir_kararlarini_uygula(durum, asama_df(durum, "01"), kaydet=True)))
            updt_yaz(durum, df21, "02.1")
            # Yeni kolonlarin UPDT sozluk satirlari (amp.updt_sozluk_suz ekler).
            p["sozluk_ek"] = yeni_kolon_sozlugu(durum, df21)
        else:
            updt_ilerlet(durum, "02.1", "01")
            p["sozluk_ek"] = []
            p.pop("satir_bilgi", None)
    # Profil degisti: SFA ve kararlari eski profile aitti, yeniden hesaplanir.
    eski = (durum.pop("sfa", None) or {}).get("ai_is")
    if eski:
        sfa_karar.ai_durdur(eski)
    # Karar kartli dalda metin ve kart blokta zaten duruyor (kart kilitlenir);
    # tekrar yazilmaz.
    if adaylar or gruplar or cozum_secilebilir(durum) or duz_oneri or sat_oneri:
        return ""
    return profil_metni(durum)


# ===========================================================================
# 02.1 VERI PROFILI KARTI
# ===========================================================================
SONUC_GIRMEZ = "girmez"
SONUC_KARAR = "karar"
SONUC_BILGI = "bilgi"
SONUC_DUZELT = "duzelt"
NE_OLACAK = {SONUC_GIRMEZ: "Üretime girmez",
             SONUC_KARAR: "Kararınıza bırakılır",
             SONUC_BILGI: "Bilgi için gösterilir",
             SONUC_DUZELT: "Düzeltme seçilir; kolon üretime girer"}


def _yuzde_metni(oran):
    """0.5 -> "%50"; 0.055 -> "%5,5" (gereksiz sifir yazilmaz)."""
    v = round(float(oran) * 100, 2)
    return "%" + (("%d" % v) if v == int(v) else ("%s" % v).rstrip("0").replace(".", ","))


def _ilgi_eki(sayi_metni):
    """Sayinin okunusuna gore ilgi eki: "%50" -> "'nin", "%95" -> "'in",
    "%5,5" -> "'in" (son okunan kelimeye bakilir)."""
    rakam = "".join(ch for ch in str(sayi_metni) if ch.isdigit())
    if not rakam:
        return "'in"
    son = rakam.rstrip("0")
    if not son:
        return "'ın"
    sifir = len(rakam) - len(son)
    if sifir == 0:
        return {"1": "'in", "2": "'nin", "3": "'ün", "4": "'ün", "5": "'in", "6": "'nın",
                "7": "'nin", "8": "'in", "9": "'un"}[son[-1]]
    if sifir == 1:
        return {"1": "'un", "2": "'nin", "3": "'un", "4": "'ın", "5": "'nin", "6": "'ın",
                "7": "'in", "8": "'in", "9": "'ın"}[son[-1]]
    if sifir == 2:
        return "'ün"
    return "'in"                                    # bin, milyon: binin


def _yuzde_ekli(oran):
    y = _yuzde_metni(oran)
    return y + _ilgi_eki(y)


def _ondalik_yazi(v):
    """Ondalik ornegi oldugu gibi (us gosterimi yok, virgulle): 1234,5678912."""
    if isinstance(v, int) or (isinstance(v, float) and v == int(v) and abs(v) < 1e15):
        return "%s,0" % int(v) if isinstance(v, float) else str(v)
    t = ("%.12f" % float(v)).rstrip("0").rstrip(".")
    return t.replace(".", ",")


def _okunur_sayi(v):
    """Bulguda sayi: 100 ve ustu tam sayiya yuvarlanir (binlik ayracli),
    alti en cok iki ondalik (us gosterimi yok)."""
    f = float(v)
    if abs(f) >= 100:
        return _sayi(int(round(f)))
    t = ("%.2f" % f).rstrip("0").rstrip(".")
    return t.replace(".", ",")


def _sayi_metni(v):
    """Ekranda sayi: tam sayi binlik ayracli, ondalik virgullu."""
    f = float(v)
    if f == int(f) and abs(f) < 1e15:
        return _sayi(int(f))
    return ("%.4g" % f).replace(".", ",")


def _profil_kurallari(esik=None):
    """Her kontrolun sade kurali (gundelik dil, terim yok); esikler
    kullanicinin onayladigi degerler."""
    e = esik or _esik_varsayilan()
    kat = _sayi(e["kardinalite"])
    return {
        "cok_bos": "Boş hücre oranı %s üstünde." % _yuzde_ekli(e["cok_bos"]),
        "sabit": "Her satırda aynı değer var. Bir değer ve boş hücrelerden oluşan kolon "
                 "sayılmaz.",
        "kimlik_gibi": "Neredeyse her satırda başka değer var: farklı değer sayısı ÷ satır "
                       "sayısı %s üstünde." % _yuzde_ekli(e["kimlik"]),
        "yuksek_kardinalite": "Yazı kolonunda farklı değer sayısı %s üstünde."
                              % (kat + _ilgi_eki(kat)),
        "ayni_icerik": "Bütün satırlarda birbirinin aynısı olan kolonlar.",
        "baskin": "Satırların en az %s kadarında aynı değer var. Boş hücre de değer sayılır."
                  % _yuzde_metni(e["baskin"]),
        "donem": "Kolon bir dönemde tamamen boş ya da hep aynı değerde ve bunun şans eseri olma "
                 "ihtimali %s altında." % _yuzde_ekli(e["tesaduf"]),
        "karisik_eksik": "Kolonda hem boş hücre hem de -1, -99, 999, 9999 gibi uydurma bir sayı "
                         "var. Sayının ne kadar sık geçtiğine bakılmaz.",
        "gizli_eksik": "-1, -99, -999, 9999 gibi uydurma bir sayı dolu satırların %s fazlasında "
                       "yazıyor ve kolonun öteki değerlerinden kopuk." % _yuzde_ekli(e["gizli"]),
        "negatif": "Adet, gün ya da süre tutan kolonda eksi değer var.",
        "sicrama": "Boş oranı art arda iki dönem arasında %s puandan fazla değişiyor ve bu "
                   "fark şans eseri olamayacak kadar çok satıra dayanıyor."
                   % _sayi_metni(round(e["sicrama"] * 100, 2)),
        "uc": "En büyük ya da en küçük değer kolonun normal aralığının çok dışında: aralığın "
              "genişliğinin %s katından fazla (yanlış yazılmış sayı)." % _sayi_metni(e["uc_yayilim"]),
        "tekrar": "Aynı kimlik ve dönemle birden fazla satır ya da bütün kolonları aynı olan "
                  "satırlar.",
        "set_cakisma": "Test (OOS) ya da Validasyon (OOT) setinde, Train'de (MS) de bulunan "
                       "kimlik, kimlik ve dönem ya da birebir aynı satır.",
        "tarih": "Kolon bir tarih (15.03.2024, 2024-03-15 ya da 20240315 gibi). Tarih kolonları "
                 "olduğu gibi model değişkeni olmaz.",
        "yakin_icerik": "İki sayı kolonu %s ya da daha fazla benzer hareket ediyor, ya da biri "
                        "ötekinin sabit bir katı." % _yuzde_metni(e["yakin_kor"]),
        "gelecek_pencere": "Kolonun adındaki dönem ifadesi ileriye bakıyor (Sonraki, Sonra ya da "
                           "Çevre).",
        "birebir": "Kolon tek başına hedefi %s ya da daha yüksek isabetle biliyor (%%50 yazı "
                   "tura, %%100 hiç yanılmıyor)." % _yuzde_metni(e["sizinti_auc"]),
        "tarih_sonra": "Tarih kolonunda, satırın döneminden sonraki bir tarih var.",
        "kayma": "Sıfır dışındaki tipik değerler (küçük, orta, büyük) art arda iki dönem arasında "
                 "aynı yönde en az %s kat değişiyor." % _sayi_metni(e["kayma_kat"]),
        "metin_bos": "Yazı kolonunda «NULL», «-», «?», «Bilinmiyor» ya da yalnız boşluk gibi "
                     "«bilgi yok» anlamına gelen bir yazı var.",
        "yazim": "Aynı değer büyük küçük harf, Türkçe harf ya da fazladan boşluk farkıyla birden "
                 "fazla biçimde yazılmış.",
        "tarih_kod": "Tarih kolonunda yılı 1901'den önce ya da 2200'den sonra olan uydurma bir "
                     "tarih var.",
        "pencere": "Aynı ölçünün kısa süreli hali uzun süreli halinden büyük (toplam, adet, en "
                   "büyük) ya da küçük (en küçük); 100 satırın en az 1'inde.",
        "tutar_adet": "Adet 0 ya da boşken tutar dolu, ya da en büyük değer ortalamadan küçük; "
                      "100 satırın en az 1'inde.",
    }


# KARAR KARTI ACIKLAMALARI: her kontrolun tek cumlesi ("kisa") ve ayrinti
# ("bilgi": nedir, neden onemli, ornek, kapsam, yakalanirsa). Kartta
# ayrinti sutunlara bolunur (kontrol_parcalari): Kontrol, Ölçüt (kural,
# kapsam, ornek), Ne Olacak (yakalanirsa), Neden Bu Değer (gerekce).
# Kural metni kapsam ve yakalanirsa ile tekrar etmez.
_KONTROL_ESIK_ANAHTARI = {"cok_bos": "cok_bos", "kimlik_gibi": "kimlik",
                          "yuksek_kardinalite": "kardinalite", "baskin": "baskin",
                          "gizli_eksik": "gizli",
                          "sicrama": "sicrama", "uc": "uc_yayilim", "yakin_icerik": "yakin_kor",
                          "birebir": "sizinti_auc", "kayma": "kayma_kat"}
_KONTROL_ACIKLAMA_EK = {
    "donem": _ac(
        "Bazı dönemlerde tamamen boş ya da hep aynı değerde olan kolon.",
        "Her dönemde (ay gibi) kolonun tamamen boş ya da hep aynı değerde olup olmadığına bakar. "
        "Çok az satırlı bir dönemde bu şans eseri de olabilir; şans eseri olma ihtimali "
        "«Tesadüf Olasılığı» sınırının altındaysa yakalanır.",
        "Ocak–Mart tamamen boş, Nisan'dan sonra dolu. Bir başka örnek: kolonun genelde %90'ı 0; "
        "100 satırlık bir dönemin tamamı 0 ise yakalanır, 10 satırlık dönemin tamamı 0 ise şans "
        "olabilir, yakalanmaz.",
        "kolonu tutmak ya da çıkarmak size sorulur. Öneri: son dönem sorunluysa Çıkar; sorun "
        "yalnız baştaki birkaç dönemdeyse Tut («İlk dönemler» sınırı); dönemlere dağınıksa Çıkar.",
        sorun="Kolon bazı dönemlerde yoksa model o dönemlerde kolondan bir şey öğrenemez; son "
              "dönemde yoksa güncel veride de yoktur."),
    "sabit": _ac(
        "Her satırında aynı değer olan kolon.",
        "Kolonda tek bir değer mi var diye bakar. Bir değer ve boş hücrelerden oluşan kolon iki "
        "değerli sayılır, yakalanmaz.",
        "Her satırda «TR» yazıyor.",
        "üretime girmez.",
        sorun="Hep aynı olan kolon satırları birbirinden ayırt etmez."),
    "ayni_icerik": _ac(
        "Satır satır birbirinin aynısı olan kolonlar.",
        "İki kolonun bütün satırlarda aynı değeri taşıyıp taşımadığına bakar.",
        "Aynı bilgi tabloya iki farklı adla girmiş.",
        "biri kalır, ötekiler üretime girmez. Hangisinin kalacağını siz seçersiniz. Öneri: başka "
        "bir kontrole takılmayan, en az düzeltme isteyen; eşitlik varsa adı kısa olan.",
        sorun="Aynı bilgiyi iki kez vermek modele bir şey kazandırmaz."),
    "karisik_eksik": _ac(
        "Eksik bilgi bazen boş bırakılmış, bazen -999 gibi bir sayıyla yazılmış.",
        "Aynı kolonda hem boş hücre hem de -1, 9999 gibi uydurma bir sayı var mı diye bakar. Tek "
        "bir satır bile yeter.",
        "Bazı satırlar boş, bazılarında -1 yazıyor.",
        "kolon kullanılır. Öneri: " + _KOD_SAKLA + ".",
        sorun="İkisi de «bilgi yok» demek; ama sayı gerçek değer gibi hesaba girip sonucu bozar."),
    "negatif": _ac(
        "Eksi olamayacak bir kolonda eksi değer.",
        "Adet, gün ya da süre tutan kolonlarda sıfırdan küçük değer arar.",
        "İşlem adedi kolonunda -3.",
        "kolon kullanılır. Öneri: eksi değerler azsa boş sayılır, çoksa olduğu gibi bırakılır "
        "(«Boş sayma sınırı»).",
        sorun="Adet ya da süre eksi olamaz; eksi değer ya yanlış kayıttır ya da özel bir anlamı "
              "vardır (iade gibi)."),
    "tekrar": _ac(
        "Aynı satır birden fazla kez yazılmış.",
        "Aynı kimlik ve aynı dönemle birden fazla satır ya da bütün kolonları aynı olan satır "
        "arar.",
        "Aynı müşteri için aynı ayda iki satır.",
        "fazla satırları çıkarmak size sorulur. Öneri: birebir aynı satırlardan biri kalır, "
        "fazlası çıkar. Aynı kimlik ve dönemde içeriği farklı satırlar varsa hangisinin doğru "
        "olduğu veriden anlaşılamaz; tablodaki ilk satır kalır, ötekiler çıkar. Satırlar çalışma "
        "tablosundan çıkar, girdi verisi değişmez.",
        kapsam="kimlik kolonu seçilmediyse yalnız bütün kolonları aynı olan satırlara bakılır.",
        sorun="İki kez yazılan satır modelde iki kat söz hakkı alır."),
    "set_cakisma": _ac(
        "Aynı kayıt hem eğitim hem sınama verisinde var.",
        "Test (OOS) ya da Validasyon (OOT) setinde, Train'de (eğitim verisi) de bulunan bir "
        "kimlik ya da birebir aynı satır var mı diye bakar.",
        "Aynı müşteri aynı ay için hem Train'de hem Test'te.",
        "çakışan satırları çıkarmak size sorulur. Öneri: aynı kayıt (aynı kimlik ve dönem ya da "
        "birebir aynı satır) Test / OOT setinden çıkar, Train'e dokunulmaz. Yalnız kimlik ortaksa "
        "(aynı müşteri, başka dönem) satır çıkarılmaz: zamana göre bölmede bu normaldir; rastgele "
        "bölmede 01.4'te bölme birimi Kimlik seçilirse aynı müşteri tek sette kalır.",
        sorun="Model sınavda daha önce gördüğü soruyla karşılaşır; başarısı olduğundan iyi "
              "görünür."),
    "tarih": _ac(
        "Tarih kolonu olduğu gibi kullanılmaz.",
        "Kolon tarih mi diye bakar (15.03.2024, 2024-03-15 ya da 20240315 gibi).",
        "Hesap açılış tarihi.",
        "kolon olduğu gibi üretime girmez. Yerine «dönem sonuna göre kaç gün» kolonu "
        "üretilebilir.",
        sorun="Model için tarihin kendisi değil, üzerinden ne kadar zaman geçtiği anlamlıdır."),
    "gelecek_pencere": _ac(
        "Adı gelecekteki bir zamanı anlatan kolon.",
        "Kolon adındaki dönem ifadesinin ileriye bakıp bakmadığına bakar («sonraki», «sonra» "
        "gibi).",
        "«Sonraki 3 ayda yapılan ödeme».",
        "kolonu tutmak ya da çıkarmak size sorulur; öneri Çıkar.",
        sorun="Tahmin yapılırken gelecek bilinmez. Gelecekten bilgi taşıyan kolon modeli "
              "eğitimde başarılı gösterir, gerçek kullanımda işe yaramaz."),
    "tarih_sonra": _ac(
        "Satırın döneminden sonraki bir tarih taşıyan kolon.",
        "Tarih kolonunda, satırın ait olduğu dönem bittikten sonraki bir tarih var mı diye bakar.",
        "Satır Mart 2024'e ait, kolondaki tarih Temmuz 2024.",
        "kolonu tutmak ya da çıkarmak size sorulur; öneri Çıkar. Tarih doğal olarak ilerideyse "
        "(vade tarihi gibi) Tut seçin. Çıkar seçilirse gün farkı kolonu da üretilmez.",
        sorun="Dönemden sonraki tarih, tahmin anında henüz bilinmeyen bir olayı gösteriyor "
              "olabilir."),
    "metin_bos": _ac(
        "Boş bırakmak yerine «NULL», «-», «Bilinmiyor» gibi yazı yazılmış.",
        "Yazı kolonunda «bilgi yok» anlamına gelen yazıları arar.",
        "Meslek kolonunda «Bilinmiyor», «?», «-».",
        "kolon kullanılır; bu yazılar boş sayılır. Çok sık geçiyorlarsa «boş mu, dolu mu» "
        "gösteren 1/0 kolonu da önerilir («Bayrak sınırı»).",
        sorun="Bu yazılar gerçek bir değer gibi sayılırsa boş hücreler gözden kaçar."),
    "yazim": _ac(
        "Aynı değer farklı biçimlerde yazılmış.",
        "Büyük küçük harf, Türkçe harf ya da fazladan boşluk dışında aynı olan değerleri arar.",
        "«İstanbul», «ISTANBUL», «istanbul ».",
        "kolon kullanılır; hepsinin tek bir yazıma çevrilmesi önerilir.",
        sorun="Aynı değer farklı yazılınca ayrı değerlermiş gibi sayılır."),
    "tarih_kod": _ac(
        "Tarih yerine 01.01.1900 ya da 31.12.9999 gibi uydurma tarih yazılmış.",
        "Tarih kolonunda yılı 1901'den önce ya da 2200'den sonra olan tarih arar.",
        "Bitiş tarihi olmayan kayıtlarda 31.12.9999.",
        "öneri: bu tarihler boş sayılır; hangi satırlarda yazdığı ayrı bir 1/0 kolonunda (_KOD) "
        "saklanır.",
        sorun="Bu tarihler gerçek değil, «bilgi yok» ya da «süresiz» demek için yazılmıştır; "
              "gerçek tarih gibi hesaba girerse sonucu bozar."),
    "pencere": _ac(
        "Kısa sürenin değeri uzun süreninkinden büyük çıkıyor.",
        "Aynı ölçünün kısa ve uzun süreli hallerini karşılaştırır. Son 7 günün toplamı son 30 "
        "günün toplamından büyük olamaz; oluyorsa yakalanır. Tek tük satırda değil, 100 satırın "
        "en az 1'inde görülmesi gerekir.",
        "Son 7 gün toplamı 500, son 30 gün toplamı 300.",
        "çelişen iki kolonu tutmak ya da çıkarmak size sorulur. Hangisinin yanlış olduğu veriden "
        "anlaşılamaz. Öneri: kolon birden fazla kolonla çelişiyorsa Çıkar; tek bir kolonla "
        "çelişiyorsa Tut, iki kolonun nasıl hesaplandığına bakıp siz karar verirsiniz.",
        sorun="Bu mümkün olmadığı için veride hata olduğunu gösterir."),
    "tutar_adet": _ac(
        "Adet ile tutar birbirini tutmuyor.",
        "Adet 0 ya da boşken tutar dolu mu, ya da en büyük değer ortalamadan küçük mü diye bakar. "
        "Tek tük satırda değil, 100 satırın en az 1'inde görülmesi gerekir.",
        "İşlem adedi 0, işlem tutarı 500.",
        "çelişen iki kolonu tutmak ya da çıkarmak size sorulur. Hangisinin yanlış olduğu veriden "
        "anlaşılamaz. Öneri: kolon birden fazla kolonla çelişiyorsa Çıkar; tek bir kolonla "
        "çelişiyorsa Tut, iki kolonun nasıl hesaplandığına bakıp siz karar verirsiniz.",
        sorun="Bu mümkün olmadığı için veride hata olduğunu gösterir."),
}

def kontrol_aciklamasi(anahtar):
    """(kisa, bilgi) - karar kartindaki kontrol satiri icin."""
    if anahtar in _KONTROL_ACIKLAMA_EK:
        x = _KONTROL_ACIKLAMA_EK[anahtar]
        return x["kisa"], x["bilgi"]
    x = PROFIL_ESIK_ACIKLAMA.get(_KONTROL_ESIK_ANAHTARI.get(anahtar, "")) or {}
    paragraf = [y for y in str(x.get("bilgi") or "").split("\n\n")
                if not (y.startswith("**Neden ") and "önerildi" in y)]
    return str(x.get("kisa") or ""), "\n\n".join(paragraf)


_PARCA_ETIKET = (("Nedir?", "nedir"), ("Neden önemli?", "onemli"), ("Neden sorun?", "onemli"),
                 ("Örnek:", "ornek"),
                 ("Kapsam:", "kapsam"), ("Eşik ne yapar?", "esik_ne"),
                 ("Yakalanırsa:", "yakalanirsa"), ("Önerilen nereden?", "gerekce"))


def aciklama_parcalari(bilgi):
    """Ayrinti metnini (**Etiket** paragraflari) tablo sutunlarina boler:
    {"nedir", "onemli", "ornek", "kapsam", "esik_ne", "yakalanirsa",
    "gerekce", "onerilen"}. "Neden X önerildi?" paragrafi gerekce olur, X
    onerilen deger metnidir. Bilinmeyen etiketli paragraf atlanmaz:
    nedir'e eklenir."""
    import re as _re
    cikti = {}
    for par in str(bilgi or "").split("\n\n"):
        par = par.strip()
        m = _re.match(r"^\*\*(.+?)\*\*\s*(.*)$", par, _re.S)
        if not m:
            if par:
                cikti["nedir"] = (cikti.get("nedir", "") + " " + par).strip()
            continue
        etiket, metin = m.group(1).strip(), m.group(2).strip()
        g = _re.match(r"^Neden (.+) önerildi\?$", etiket)
        if g:
            cikti["onerilen"], cikti["gerekce"] = g.group(1), metin
            continue
        anahtar = dict(_PARCA_ETIKET).get(etiket)
        if anahtar:
            # Turkce buyuk harf: "iki" -> "İki" (upper() "Iki" yapar).
            ilk = {"i": "İ", "ı": "I"}.get(metin[:1], metin[:1].upper())
            cikti[anahtar] = ilk + metin[1:] if metin else ""
        else:
            cikti["nedir"] = (cikti.get("nedir", "") + " " + metin).strip()
    return cikti


def kontrol_parcalari(anahtar):
    """Karar kartindaki kontrol satirinin sutun parcalari (gerekce dahil)."""
    if anahtar in _KONTROL_ACIKLAMA_EK:
        return aciklama_parcalari(_KONTROL_ACIKLAMA_EK[anahtar]["bilgi"])
    x = PROFIL_ESIK_ACIKLAMA.get(_KONTROL_ESIK_ANAHTARI.get(anahtar, "")) or {}
    return aciklama_parcalari(x.get("bilgi"))


# (anahtar, kontrolun adi, sonuc, kolon satirindaki kisa bulgu adi)
PROFIL_KONTROLLERI = (
    ("cok_bos", "Eksik Oranı Yüksek", SONUC_GIRMEZ, "Eksik oranı yüksek"),
    ("sabit", "Sabit ya da Tek Değerli", SONUC_GIRMEZ, "Sabit"),
    ("kimlik_gibi", "Kimlik Benzeri", SONUC_GIRMEZ, "Kimlik benzeri"),
    ("yuksek_kardinalite", "Kardinalitesi Aşırı Yüksek", SONUC_GIRMEZ, "Kardinalite yüksek"),
    ("tarih", "Tarih Kolonu", SONUC_GIRMEZ, "Tarih kolonu"),
    ("ayni_icerik", "Aynı İçerikli Kolonlar", SONUC_GIRMEZ, "Aynı içerik"),
    ("yakin_icerik", "Neredeyse Aynı Kolonlar", SONUC_GIRMEZ, "Neredeyse aynı"),
    ("gelecek_pencere", "Gelecek Penceresi (Sızıntı Riski)", SONUC_KARAR, "Gelecek penceresi"),
    ("birebir", "Hedefle Neredeyse Birebir", SONUC_KARAR, "Hedefle birebir"),
    ("tarih_sonra", "Dönemden Sonraki Tarih", SONUC_KARAR, "Dönemden sonraki tarih"),
    ("baskin", "Neredeyse Sabit", SONUC_KARAR, "Neredeyse sabit"),
    ("donem", "Dönemde Boş ya da Sabit", SONUC_KARAR, "Dönemde boş ya da sabit"),
    ("gizli_eksik", "Gizli Eksik (Özel Kod)", SONUC_DUZELT, "Gizli eksik"),
    ("karisik_eksik", "Karışık Eksik Kodlaması", SONUC_DUZELT, "Karışık eksik"),
    ("metin_bos", "Metin Olarak Yazılmış Boş", SONUC_DUZELT, "Metin olarak boş"),
    ("yazim", "Kategori Yazım Tutarsızlığı", SONUC_DUZELT, "Yazım tutarsızlığı"),
    ("negatif", "Beklenmeyen Negatif", SONUC_DUZELT, "Beklenmeyen negatif"),
    ("sicrama", "Dönemler Arası Eksik Sıçraması", SONUC_KARAR, "Eksik sıçraması"),
    ("kayma", "Dönemler Arası Değer Kayması", SONUC_KARAR, "Değer kayması"),
    ("uc", "Uç Değer Yoğunluğu", SONUC_DUZELT, "Uç değer"),
    ("pencere", "Pencere Tutarlılığı", SONUC_KARAR, "Pencere tutarsız"),
    ("tutar_adet", "Tutar ve Adet Uyumsuzluğu", SONUC_KARAR, "Tutar ve adet uyumsuz"),
    ("tekrar", "Tekrar Eden Satır", SONUC_DUZELT, ""),
    ("set_cakisma", "Setler Arası Çakışma", SONUC_DUZELT, ""),
)
# KARTTA BIRLESIK KONTROLLER: ayni soruyu farkli esikle ya da farkli
# bicimde soran kontroller kartta tek satirdir. Algilama kurallari,
# esikler, kararlar ve duzeltmeler uye kontrol bazinda AYNEN kalir; kart
# grup satirinin altinda uyeleri (uye_kontroller) tasir. Kolon satirinda
# hangi alt bulgudan geldigi yazar; bir kolon iki alt bulguya takilirsa
# tek satirdir. (anahtar, ad, kisa aciklama, uyeler)
KONTROL_GRUPLARI = (
    ("g_sabit", "Sabit ya da Neredeyse Sabit",
     "Her satırda ya da neredeyse her satırda aynı değer var.",
     ("sabit", "baskin")),
    ("g_ayni", "Aynı ya da Neredeyse Aynı Kolonlar",
     "Kolon başka bir kolonla aynı şeyi söylüyor.",
     ("ayni_icerik", "yakin_icerik")),
    ("g_kardinalite", "Çok Fazla Farklı Değer",
     "O kadar çok farklı değer var ki kolon olduğu gibi kullanılamaz.",
     ("kimlik_gibi", "yuksek_kardinalite")),
    ("g_sizinti", "Sızıntı Riski",
     "Kolon, tahmin anında henüz bilinmeyen bir bilgiyi taşıyor olabilir.",
     ("gelecek_pencere", "birebir", "tarih_sonra")),
    ("g_donem", "Dönemler Arası Tutarsızlık",
     "Kolon bazı dönemlerde bozuluyor: tamamen boş ya da hep aynı, boş oranı ya da sayıları birden değişiyor.",
     ("donem", "sicrama", "kayma")),
    ("g_gizli", "Gizli Eksik",
     "«Bilgi yok» demek için boş bırakmak yerine sayı ya da yazı yazılmış.",
     ("gizli_eksik", "karisik_eksik", "metin_bos")),
    ("g_iliskili", "İlişkili Kolonlar Arası Tutarsızlık",
     "Birbirine bağlı iki kolon birbirini tutmuyor.",
     ("pencere", "tutar_adet")),
)
KONTROL_ALT_AD = {
    "sabit": "tek değer", "baskin": "baskın değer",
    "ayni_icerik": "birebir aynı", "yakin_icerik": "neredeyse aynı",
    "kimlik_gibi": "kimlik benzeri", "yuksek_kardinalite": "metinde çok değer",
    "gelecek_pencere": "gelecek penceresi", "birebir": "hedefle birebir",
    "tarih_sonra": "dönemden sonraki tarih",
    "donem": "dönemde boş ya da sabit", "sicrama": "eksik sıçraması", "kayma": "değer kayması",
    "gizli_eksik": "özel kod", "karisik_eksik": "özel kod ve boş hücre", "metin_bos": "metin olarak boş",
    "pencere": "pencere tutarlılığı", "tutar_adet": "tutar ve adet",
}
_SONUC_SIRA = {SONUC_GIRMEZ: 0, SONUC_KARAR: 1, SONUC_DUZELT: 2, SONUC_BILGI: 3}


def gorunur_kontrol_sayisi():
    """Kartta gorunen kontrol sayisi (birlesik kontroller tek sayilir).
    Tesadüf Olasılığı da kontrol sayilir (formda 1 numara): 15 kontrol."""
    uye = {a for g in KONTROL_GRUPLARI for a in g[3]}
    return len([x for x in PROFIL_KONTROLLERI if x[0] not in uye]) + len(KONTROL_GRUPLARI) \
        + len(PROFIL_GENEL_ESIKLER)


def toplam_kural_sayisi():
    """Kontrollerin altindaki kural sayisi; Tesadüf Olasılığı tek kurallidir: 25 kural."""
    return len(PROFIL_KONTROLLERI) + len(PROFIL_GENEL_ESIKLER)


def _genel_kontrol_satirlari(esik):
    """Kartin basindaki genel kontrol satiri (Tesadüf Olasılığı): kolon
    yakalamaz; uc kuralin kolonu yakalayip yakalamayacagini belirleyen
    sinirdir ("ayar": gecerli deger)."""
    cikti = []
    for a, ad, _an, birim, _x, _y in PROFIL_GENEL_ESIKLER:
        ac = PROFIL_ESIK_ACIKLAMA.get(a) or {}
        deger = _esik_metni(birim, esik[a])
        cikti.append({"anahtar": a, "ad": ad, "kural": "Geçerli sınır %s." % deger,
                      "sonuc": SONUC_BILGI, "kisa": ac.get("kisa", ""), "bilgi": ac.get("bilgi", ""),
                      "parca": aciklama_parcalari(ac.get("bilgi")), "ne_olacak": "",
                      "uygulandi": True, "sebep": "", "birim": "kolon", "kolonlar": [], "sayi": 0,
                      "ayar": deger, "oneri_kaynagi": "kod"})
    return cikti


def _grup_satiri(g, uyeler):
    """Birlesik kontrolun kart satiri: uyelerin kurallari, bulunan kolonlar
    (kolon basina tek satir, alt bulgu adiyla) ve uyelerin kendisi
    (kararlar sekmesi bunlardan kurulur)."""
    anahtar, ad, kisa, _u = g
    alt = lambda u: KONTROL_ALT_AD.get(u["anahtar"], u["ad"])
    uyg = [u for u in uyeler if u.get("uygulandi") is not False]
    bulunan = [u for u in uyg if u.get("sayi")]
    sonuc = min((u["sonuc"] for u in (bulunan or uyg or uyeler)), key=lambda x: _SONUC_SIRA.get(x, 9))
    kural = []
    for u in uyeler:
        if u.get("uygulandi") is False:
            kural.append("**%s:** uygulanmadı (%s)." % (alt(u).capitalize(), u.get("sebep") or ""))
        else:
            kural.append("**%s:** %s" % (alt(u).capitalize(), u.get("kural") or ""))
    parca = {}
    for alan in ("nedir", "onemli", "kapsam", "ornek", "esik_ne", "yakalanirsa"):
        degerler = [(u, (u.get("parca") or {}).get(alan)) for u in uyg]
        degerler = [(u, v) for u, v in degerler if v]
        if len(degerler) == 1:
            parca[alan] = degerler[0][1]
        elif degerler:
            parca[alan] = " ".join("%s: %s" % (alt(u).capitalize(), v) for u, v in degerler)
    gerekce = [(u, u.get("parca") or {}) for u in uyg if (u.get("parca") or {}).get("gerekce")]
    if gerekce:
        parca["gerekce"] = " ".join(
            "%s%s: %s" % (alt(u).capitalize(), (" (önerilen %s)" % p["onerilen"]) if p.get("onerilen") else "",
                          p["gerekce"]) for u, p in gerekce)
    # Ne olacak: alt bulgularda ayniysa bir kez, farkliysa alt bulgu adiyla.
    ne_ham = [(u, u["ne_olacak"]) for u in bulunan if u.get("ne_olacak")]
    if len({v for _u, v in ne_ham}) <= 1:
        ne = [ne_ham[0][1]] if ne_ham else []
    else:
        ne = ["%s: %s" % (alt(u).capitalize(), v) for u, v in ne_ham]
    kolonlar, sira = {}, []
    for u in bulunan:
        for c in u.get("kolonlar") or []:
            ham = str(c.get("bulgu") or "")
            # Bulgu alt bulgunun adiyla basliyorsa ("Tek değer: 7") tekrar yazilmaz.
            metin = ham if ham.lower().startswith(alt(u).lower()) else "%s: %s" % (alt(u).capitalize(), ham)
            x = kolonlar.get(c["ad"])
            if x is None:
                x = kolonlar[c["ad"]] = {"ad": c["ad"], "aciklama": c.get("aciklama", ""), "bulgu": metin}
                sira.append(c["ad"])
            else:
                x["bulgu"] += "; " + metin
            if c.get("cozum") and len(c["cozum"].get("secenekler") or []) < 2:
                x["cozum_yok"] = True
            if c.get("cozum_baska"):
                x["cozum_baska"] = c["cozum_baska"]
    gruplar = [gr for u in bulunan for gr in (u.get("gruplar") or [])]
    for u in uyeler:
        # Kararlar sekmesinde uye adi birlesik kontrolun adiyla gorunur.
        u["ad"] = "%s (%s)" % (ad, alt(u))
        u["grup"] = anahtar
    satir = {"anahtar": anahtar, "ad": ad, "kural": " ".join(kural), "sonuc": sonuc,
             "kisa": kisa, "bilgi": "\n\n".join(u.get("bilgi") or "" for u in uyg if u.get("bilgi")),
             "parca": parca, "ne_olacak": "; ".join(ne) or ((uyg or uyeler)[0].get("ne_olacak") or ""),
             "uygulandi": bool(uyg),
             "sebep": "" if uyg else "; ".join(dict.fromkeys(u.get("sebep") or "" for u in uyeler)),
             "birim": "kolon", "kolonlar": [kolonlar[a] for a in sira], "sayi": len(sira),
             "oneri_kaynagi": "dil modeli" if any(u.get("oneri_kaynagi") == "dil modeli" for u in bulunan)
             else "kod",
             "alt_kontroller": [{"anahtar": u["anahtar"], "ad": alt(u), "sayi": int(u.get("sayi") or 0),
                                 "uygulandi": u.get("uygulandi") is not False} for u in uyeler],
             "uye_kontroller": uyeler}
    if gruplar:
        satir["gruplar"] = gruplar
    return satir


def kart_kontrol_sirasi():
    """Kartta gorunen kontrollerin sirasi: [(anahtar, ad)]; birlesik
    kontrol ilk uyesinin yerinde (kontrolleri_grupla ile ayni). Esik
    formunda iliskili esikler bu siraya gore art arda dizilir."""
    grup_of = {a: g for g in KONTROL_GRUPLARI for a in g[3]}
    sira, eklenen = [], set()
    for a, ad, _s, _k in PROFIL_KONTROLLERI:
        g = grup_of.get(a)
        if g is None:
            sira.append((a, ad))
        elif g[0] not in eklenen:
            eklenen.add(g[0])
            sira.append((g[0], g[1]))
    return sira


def kontrol_no(anahtar_ya_da_ad):
    """Karttaki kontrol numarasi (1'den); anahtar ya da ad ile."""
    for i, (a, ad) in enumerate(kart_kontrol_sirasi(), 1):
        if anahtar_ya_da_ad in (a, ad):
            return i
    return None


def kontrolleri_grupla(kontroller):
    """Uye kontrol satirlarindan kartin satirlari: birlesik kontrol, ilk
    uyesinin yerinde tek satir."""
    harita = {k["anahtar"]: k for k in kontroller}
    grup_of = {a: g for g in KONTROL_GRUPLARI for a in g[3]}
    cikti, eklenen = [], set()
    for k in kontroller:
        g = grup_of.get(k["anahtar"])
        if g is None:
            cikti.append(k)
            continue
        if g[0] in eklenen:
            continue
        eklenen.add(g[0])
        cikti.append(_grup_satiri(g, [harita[a] for a in g[3] if a in harita]))
    return cikti


# Karar isteyen kontrollerden varsayilani Çıkar olanlar (sizinti riski).
KARAR_VARSAYILAN_CIKAR = ("gelecek_pencere", "birebir", "tarih_sonra")
# Hedefle birebir: ayirma gucu bu esik ve ustundeyse Çıkar, altindaysa
# (Sizinti AUC esigi ile bu deger arasi) Tut; kolon incelenmeli.
SIZINTI_CIKAR_AUC = 0.95
# Bilgi icin gosterilen ve islem yapilmayan kontrol kalmadi: Pencere
# Tutarliligi ve Tutar ve Adet karar (Tut / Çıkar), Tekrar Eden Satir ve
# Setler Arasi Cakisma satir cikarma (SATIR_KONTROLLERI).
BILGI_KONTROLLERI = ()
DONEM_LISTE_EN_COK = 6


def _donem_listesi(donemler):
    if len(donemler) <= DONEM_LISTE_EN_COK:
        return ", ".join(donemler)
    return "%s ve %s dönem daha" % (", ".join(donemler[:DONEM_LISTE_EN_COK]),
                                    _sayi(len(donemler) - DONEM_LISTE_EN_COK))


def _ek_bulgulari(p, ek=None, kopya_suz=True):
    """{anahtar: {kolon: bulgu metni}} ek kontrollerden. Ayni icerikli
    gruplarda kalmayan kolonlar diger kontrollerde gosterilmez
    (kopya_suz=False: hepsi; ek verilirse p'deki yerine o)."""
    ek = (p.get("profil_ek") or {}) if ek is None else ek
    kopya = set(_ayni_kopyalar(p)) if kopya_suz else set()
    b = {a: {} for a in ("ayni_icerik", "yakin_icerik", "gelecek_pencere", "birebir",
                         "tarih_sonra", "baskin", "donem", "gizli_eksik", "karisik_eksik",
                         "tarih_kod", "metin_bos", "yazim", "negatif", "sicrama",
                         "kayma", "uc", "pencere", "tutar_adet")}
    for g in ek.get("ayni_gruplar") or []:
        kalan = _ayni_kalan(p, g)
        for k in g["uyeler"]:
            if k == kalan:
                continue
            if g.get("tur") == "yakin":
                b["yakin_icerik"][k] = "%s ile neredeyse aynı (%s); %s kalır" % (
                    kalan, _yakin_iliski_metni(g, kalan, k), kalan)
            else:
                b["ayni_icerik"][k] = "%s ile birebir aynı; %s kalır" % (kalan, kalan)
    for x in ek.get("gelecek_pencere") or []:
        b["gelecek_pencere"][x["kolon"]] = "; ".join(
            "Ad parçası %s: %s" % (t["parca"], t["tur_adi"]) for t in x["parcalar"])
    for x in ek.get("birebir") or []:
        b["birebir"][x["kolon"]] = "Tek başına ayırma gücü (AUC) %s" % _yuzde_metni(x["auc"])
    for x in ek.get("tarih_sonra") or []:
        b["tarih_sonra"][x["kolon"]] = "%s satırda (payı %s); en geç %s" % (
            _sayi(x["adet"]), _yuzde_metni(x["pay"]), x["en_gec"])
    for x in ek.get("kayma") or []:
        b["kayma"][x["kolon"]] = "Ortanca %s dönemi %s, %s dönemi %s (%s kat)" % (
            x["once"], _okunur_sayi(x["once_deger"]), x["sonra"], _okunur_sayi(x["sonra_deger"]),
            _okunur_sayi(x["kat"]))
    for x in ek.get("tarih_kod") or []:
        b["tarih_kod"][x["kolon"]] = "%s; toplam %s satır (payı %s)" % (
            ", ".join("%s: %s" % (d["deger"], _sayi(d["adet"])) for d in x["degerler"][:3]),
            _sayi(x["adet"]), _yuzde_metni(x["pay"]))
    for x in ek.get("metin_bos") or []:
        b["metin_bos"][x["kolon"]] = "%s; toplam %s satır (payı %s)" % (
            ", ".join("«%s»: %s" % (d["deger"], _sayi(d["adet"])) for d in x["degerler"][:4]),
            _sayi(x["adet"]), _yuzde_metni(x["pay"]))
    for x in ek.get("yazim") or []:
        g0 = x["gruplar"][0]
        b["yazim"][x["kolon"]] = "%s değer farklı yazılmış, %s satır çevrilir. Ör. %s" % (
            _sayi(x["grup"]), _sayi(x["satir"]),
            ", ".join("«%s»" % y["deger"] for y in g0["yazimlar"][:4]))
    for x in ek.get("pencere") or []:
        buyuk = (x["yon"] == "artan") != bool(x.get("ters"))
        metin = "%s satırda %s kolonundan %s (payı %s)" % (
            _sayi(x["adet"]), x["karsi"], "büyük" if buyuk else "küçük", _yuzde_metni(x["pay"]))
        onceki = b["pencere"].get(x["kolon"])
        b["pencere"][x["kolon"]] = (onceki + ". " + metin) if onceki else metin
    for x in ek.get("tutar_adet") or []:
        if x["tur"] == "adet_tutar" and x.get("ters"):
            metin = "%s satırda 0 ya da boşken %s dolu (payı %s)" % (
                _sayi(x["adet"]), x["karsi"], _yuzde_metni(x["pay"]))
        elif x["tur"] == "adet_tutar":
            metin = "%s satırda %s 0 ya da boşken dolu (payı %s)" % (
                _sayi(x["adet"]), x["karsi"], _yuzde_metni(x["pay"]))
        else:
            metin = "%s satırda %s kolonundan %s (payı %s)" % (
                _sayi(x["adet"]), x["karsi"], "büyük" if x.get("ters") else "küçük",
                _yuzde_metni(x["pay"]))
        onceki = b["tutar_adet"].get(x["kolon"])
        b["tutar_adet"][x["kolon"]] = (onceki + ". " + metin) if onceki else metin
    for x in ek.get("baskin") or []:
        b["baskin"][x["kolon"]] = "En sık değer %s, payı %s" % (x["deger"], _yuzde_metni(x["pay"]))
    for x in ek.get("donem") or []:
        parca = []
        if x.get("bos"):
            parca.append("Boş dönemler: %s" % _donem_listesi(x["bos"]))
        if x.get("sabit"):
            parca.append("Tek değerli dönemler: %s" % _donem_listesi(x["sabit"]))
        b["donem"][x["kolon"]] = ". ".join(parca)
    for x in ek.get("karisik_eksik") or []:
        b["karisik_eksik"][x["kolon"]] = "Kod %s: %s satır (payı %s); boş hücre: %s satır" % (
            x["deger"], _sayi(x["adet"]), _yuzde_metni(x["pay"]), _sayi(x.get("bos") or 0))
    for x in ek.get("gizli_eksik") or []:
        b["gizli_eksik"][x["kolon"]] = ("Boş hücre de var: %s satır. " % _sayi(x["bos"])
                                        if x.get("bos") else "") + "Kod %s, payı %s (%s satır)" % (
            x["deger"], _yuzde_metni(x["pay"]), _sayi(x["adet"]))
    for x in ek.get("negatif") or []:
        b["negatif"][x["kolon"]] = "Ölçü: %s. Negatif satır %s, en küçük değer %s" % (
            x["olcu"], _sayi(x["adet"]), _sayi_metni(x["en_kucuk"]))
    for x in ek.get("sicrama") or []:
        b["sicrama"][x["kolon"]] = "Eksik oranı %s dönemi %s, %s dönemi %s" % (
            x["once"], _yuzde_metni(x["once_oran"]), x["sonra"], _yuzde_metni(x["sonra_oran"]))
    for x in ek.get("uc") or []:
        b["uc"][x["kolon"]] = uc_bulgu_metni(x)
    for a, kolonlar in b.items():
        if a not in ("ayni_icerik", "yakin_icerik"):
            for k in [k for k in kolonlar if k in kopya]:
                del kolonlar[k]
    return b


def _yakin_iliski_metni(g, kalan, k):
    """Neredeyse ayni grupta k'nin kalanla iliskisi: "1.000 katı" ya da
    "korelasyon %99,99". Iliski grubun ilk kolonuna gore saklanir."""
    il = (g.get("iliski") or {})
    ilk = g["uyeler"][0]

    def kat(a, b):
        """b = a * kat (a, b uye)."""
        if a == b:
            return 1.0
        if a == ilk and (il.get(b) or {}).get("tur") == "kat":
            return il[b]["kat"]
        if b == ilk and (il.get(a) or {}).get("tur") == "kat":
            return 1.0 / il[a]["kat"]
        if (il.get(a) or {}).get("tur") == "kat" and (il.get(b) or {}).get("tur") == "kat":
            return il[b]["kat"] / il[a]["kat"]
        return None
    c = kat(kalan, k)
    if c:
        return "%s katı" % _sayi_metni(round(c, 6) if abs(c) < 1 else round(c, 4))
    x = il.get(k) if k != ilk else il.get(kalan)
    if isinstance(x, dict) and x.get("tur") == "kor":
        return "korelasyon %s" % _yuzde_metni(abs(x["kor"]))
    return "korelasyon çok yüksek"


def _iliski_cumlesi(g, kalan, k):
    """"B, A kolonunun 100 katı" ya da "A ile B arasında korelasyon %99,5"."""
    m = _yakin_iliski_metni(g, kalan, k)
    if m.startswith("korelasyon"):
        return "%s ile %s arasında %s" % (kalan, k, m)
    return "%s, %s kolonunun %s" % (k, kalan, m)


def _profil_ozeti(durum):
    """Kartin ve metnin ortak sayilari."""
    p = durum.get("profil") or {}
    t = p.get("profil_teshis") or {}
    ek = p.get("profil_ek") or {}
    temel = set(t.get("cok_bos") or []) | set(t.get("sabit") or []) \
        | set(t.get("kimlik_gibi") or []) | set(t.get("yuksek_kardinalite") or []) \
        | set(t.get("tarih") or [])
    incelenen = set(map(str, t.get("temiz") or [])) | temel
    girmez = set(kusurlu_kolonlar(durum))
    karar = p.get("profil_karar") if isinstance(p.get("profil_karar"), dict) else {}
    karar_ad = profil_karar_kolonlari(durum)
    bekleyen = {k for k in karar_ad if k not in karar}
    bilgi = set()
    for a in DUZELTME_KONTROLLERI + BILGI_KONTROLLERI:
        bilgi |= {x["kolon"] for x in (ek.get(a) or [])}
    bilgi |= {k for k in karar_ad if karar.get(k) == PROFIL_KARAR_TUT}
    bilgi -= girmez | bekleyen
    temiz = incelenen - girmez - bilgi - bekleyen
    return {"incelenen": incelenen, "girmez": girmez, "bilgi": bilgi,
            "bekleyen": bekleyen, "temiz": temiz, "karar": karar}


def profil_metni(durum, karar=False):
    """02.1 bloğunun metni: ne yapildi ve sonuc, tek bakista."""
    oz = _profil_ozeti(durum)
    kap = (durum.get("profil") or {}).get("profil_kapsam") or {}
    metin = ("Modelleme tablosundaki %s kolon, tablonun tamamı (train, val, test ve OOT "
             "birlikte) üzerinden %s kontrolle (bunların altında toplam %s kural) incelendi." % (
                 _sayi(len(oz["incelenen"])), _sayi(gorunur_kontrol_sayisi()),
                 _sayi(toplam_kural_sayisi())))
    if kap.get("hedef_train"):
        metin += (" Hedefle ilgili ölçümler ve öğrenilen her şey (çözümler, kırpma sınırı) "
                  "yalnız Train (MS) satırlarından; kararlar ve düzeltmeler onayınızla bütün "
                  "satırlara aynı şekilde uygulanır.")
    parca = []
    if oz["girmez"]:
        if karar or not updt_modu(durum):
            parca.append("%s kolon değişken üretimine girmez; %s." % (
                _sayi(len(oz["girmez"])),
                "kararlarınızı onaylayınca UPDT veriden çıkarılır" if updt_modu(durum)
                else "%s adımında veri setinden çıkarılır" % akis_atif.adim("baz")))
        else:
            parca.append("%s kolon değişken üretimine girmez ve UPDT veriden çıkarıldı."
                         % _sayi(len(oz["girmez"])))
        sec = cozum_secimi(durum)
        cozumlu = [k for k, c in sec.items() if c != "cikar" and k in oz["girmez"]]
        secilebilir = cozum_secilebilir(durum)
        if karar and secilebilir:
            parca.append("Bunlardan %s kolon için çözüm önerildi; her birinde çözümü seçin. "
                         "Ham kolon yerine çözümün ürettiği yeni kolon değişken üretimine "
                         "girer, Çıkar seçilirse kolon kullanılmaz." % _sayi(len(secilebilir)))
        elif cozumlu:
            yeni = sum(len(v.get("kolonlar") or []) for k, v in
                       ((durum.get("profil") or {}).get("cozum_bilgi") or {}).items()
                       if k in cozumlu)
            parca.append("Bunlardan %s kolonun yerine çözümle üretilen %s kolon değişken "
                         "üretimine girer." % (_sayi(len(cozumlu)), _sayi(yeni)))
    if oz["bekleyen"]:
        parca.append("%s kolon için kararınız gerekiyor: Ne Olacak sütununda Kararınıza "
                     "bırakılır yazan kontrollerde her kolonu tutun ya da çıkarın. Her kolonda "
                     "kuralın kolon bazında önerisi seçili gelir."
                     % _sayi(len(oz["bekleyen"])))
    duz = duzeltme_secimi(durum)
    n_duz = sum(len(v) for v in duz.values())
    if karar and n_duz:
        parca.append("Düzeltme seçilen kontrollerde %s kolon için düzeltme seçin; önerilen "
                     "seçili gelir. Bu kolonlar üretime girer." % _sayi(n_duz))
    elif n_duz:
        uyg = sum(1 for v in duz.values() for c in v.values() if c != "birak")
        parca.append(("%s kolonda düzeltme uygulandı" % _sayi(uyg) if uyg else
                      "Düzeltme uygulanmadı")
                     + ((", %s kolon olduğu gibi kullanılır." % _sayi(n_duz - uyg))
                        if n_duz - uyg else "."))
    gruplar = ((durum.get("profil") or {}).get("profil_ek") or {}).get("ayni_gruplar") or []
    if karar and gruplar:
        parca.append("Değerleri birebir ya da neredeyse aynı %s kolon grubunda hangi kolonun "
                     "kalacağını seçin; kuralın önerisi seçili gelir." % _sayi(len(gruplar)))
    if oz["bilgi"]:
        parca.append("%s kolonda bilgi notu var; bu kolonlar değişken üretimine girer."
                     % _sayi(len(oz["bilgi"])))
    if not parca:
        parca.append("Hiçbir kolonda sorun bulunmadı; bütün kolonlar değişken üretimine "
                     "girer.")
    notu = esik_degisiklik_notu(durum)
    if notu:
        parca.append(notu)
    sizinti, _top = set_cakisma_sayilari((durum.get("profil") or {}).get("profil_ek") or {})
    if sizinti:
        parca.append("Test (OOS) ya da Validasyon (OOT) setinde %s satır Train'deki bir kaydın aynısı (aynı "
                     "kimlik ve dönem ya da aynı satır); test sonucu olduğundan iyi görünebilir. "
                     "Ayrıntısı Setler Arası Çakışma kontrolünde." % _sayi(sizinti))
    tk = ((durum.get("profil") or {}).get("profil_ek") or {}).get("tekrar") or {}
    tekrar = int(tk.get("toplam") or 0)
    if tekrar:
        parca.append("Tabloda %s tekrar eden satır var; Tekrar Eden Satır kontrolünde "
                     "ayrıntısı görünür." % _sayi(tekrar))
    sb = (durum.get("profil") or {}).get("satir_bilgi") or {}
    if sb.get("toplam"):
        parca.append("Kararlarınızla %s satır çalışma tablosundan çıkarıldı (%s); tabloda %s satır "
                     "kaldı. Girdi verisi değişmedi." % (
                         _sayi(sb["toplam"]),
                         "; ".join("%s: %s" % (a, _sayi(n)) for a, n in (sb.get("cikan") or {}).items() if n),
                         _sayi(sb.get("sonra") or 0)))
    return metin + " " + " ".join(parca)


def profil_karti(durum, karar=False):
    """02.1 Veri Profili karti (sohbette adimin blogunda). Butun sayilar
    tablonun TAMAMINDAN; orneklem yok. karar=True: neredeyse sabit ve
    donemde bos ya da sabit kolonlar icin Tut ya da Çıkar istenir.
    Profil yoksa None."""
    p = durum.get("profil") or {}
    t = p.get("profil_teshis")
    if not isinstance(t, dict):
        return None
    ek = p.get("profil_ek") or {}
    ozet = {str(s.get("ad")): s for s in (p.get("kolon_ozet") or []) if isinstance(s, dict)}
    oz = _profil_ozeti(durum)
    incelenen = sorted(oz["incelenen"])
    aciklama = _aciklamalar(durum)

    turler = {"sayısal": 0, "kategorik": 0, "tarih": 0}
    for k in incelenen:
        tur = (ozet.get(k) or {}).get("tip") or "kategorik"
        turler[tur] = turler.get(tur, 0) + 1

    bulgu = _ek_bulgulari(p)
    for k in t.get("cok_bos") or []:
        bulgu.setdefault("cok_bos", {})[k] = "Eksik oranı %s" % _yuzde_metni(
            (ozet.get(k) or {}).get("null_oran") or 0)
    for k in t.get("sabit") or []:
        deger = (ek.get("sabit_deger") or {}).get(k)
        bulgu.setdefault("sabit", {})[k] = ("Bütün hücreler boş" if deger == "boş"
                                            else "Tek değer: %s" % deger if deger
                                            else "Tek değerli")
    tarih_kod = {x["kolon"]: x for x in ek.get("tarih_kod") or []}
    for k in t.get("tarih") or []:
        ar = (ek.get("tarih_aralik") or {}).get(k)
        parca = [("En eski %s, en yeni %s" % (ar[0], ar[1])) if ar else "Geçerli tarih yok"]
        tur = (ek.get("tarih_tur") or {}).get(k)
        if tur in TARIH_YAZILIS:
            parca.append(TARIH_YAZILIS[tur])
        x = tarih_kod.get(k)
        if x:
            parca.append("Kod tarih %s satır (%s); gün farkında boş" % (
                _sayi(x["adet"]), ", ".join(d["deger"] for d in x["degerler"][:3])))
        bulgu.setdefault("tarih", {})[k] = ". ".join(parca)
    for a in ("kimlik_gibi", "yuksek_kardinalite"):
        for k in t.get(a) or []:
            tekil = (ozet.get(k) or {}).get("tekil")
            bulgu.setdefault(a, {})[k] = ("%s farklı değer" % _sayi(tekil)) if tekil is not None \
                else "Farklı değer sayısı yüksek"

    esik = profil_esikleri(durum)
    kurallar = _profil_kurallari(esik)
    karar_deger = oz["karar"]
    cozum_oneri = cozum_onerileri(durum)
    cozum_sec = cozum_secimi(durum)
    cozum_bilgi = p.get("cozum_bilgi") or {}
    duz_oneri = duzeltme_onerileri(durum)
    duz_sec = duzeltme_secimi(durum)
    duz_bilgi = p.get("duzeltme_bilgi") or {}
    donemler = ek.get("donemler")
    karar_vars = _karar_varsayilan(p)
    kontroller = []
    for a, ad, sonuc, _kisa in PROFIL_KONTROLLERI:
        kisa, bilgi = kontrol_aciklamasi(a)
        k = {"anahtar": a, "ad": ad, "kural": kurallar[a], "sonuc": sonuc,
             "kisa": kisa, "bilgi": bilgi, "parca": kontrol_parcalari(a),
             "ne_olacak": NE_OLACAK[sonuc], "uygulandi": True, "sebep": "",
             "birim": "kolon", "kolonlar": []}
        if a == "yuksek_kardinalite" and not turler.get("kategorik"):
            k["uygulandi"], k["sebep"] = False, "Kategorik kolon yok"
        elif a in ("donem", "sicrama", "kayma", "tarih_sonra") and donemler is None:
            k["uygulandi"], k["sebep"] = False, "Dönem kolonu seçilmedi"
        elif a in ("donem", "sicrama", "kayma") and len(donemler or []) < 2:
            k["uygulandi"], k["sebep"] = False, "Tabloda tek dönem var"
        elif a == "tarih" and not t.get("tarih"):
            k["uygulandi"], k["sebep"] = False, "Tarih tipinde kolon yok"
        elif a == "tarih_sonra" and ek.get("tarih_sonra") is None:
            k["uygulandi"], k["sebep"] = False, "Dönem değerleri tarih olarak okunamadı"
        elif a == "tarih_sonra" and not ek.get("tarih_kolon"):
            k["uygulandi"], k["sebep"] = False, "Tarih kolonu yok"
        elif a == "tarih_kod" and not ek.get("tarih_kolon"):
            k["uygulandi"], k["sebep"] = False, "Tarih kolonu yok"
        elif a in ("metin_bos", "yazim") and not ek.get("metin_kolon", 1):
            k["uygulandi"], k["sebep"] = False, "Metin kolon yok"
        elif a == "negatif" and not ek.get("olcu_var"):
            k["uygulandi"], k["sebep"] = False, "Kolon kartlarında ölçü bilgisi yok"
        elif a == "birebir" and ek.get("birebir") is None:
            k["uygulandi"], k["sebep"] = False, "Hedef iki sınıflı (0 ve 1) değil"
        elif a == "gelecek_pencere" and not ek.get("donem_tur_var"):
            k["uygulandi"], k["sebep"] = False, "Kolon adlarında anlam türü onaylı dönem parçası yok"
        elif a == "pencere" and not ek.get("pencere_cift"):
            k["uygulandi"], k["sebep"] = False, "Aynı ölçünün farklı pencereli kolonu yok"
        elif a == "tutar_adet" and not ek.get("tutar_cift"):
            k["uygulandi"], k["sebep"] = False, "Eşleşen adet ve tutar ya da en büyük ve ortalama kolonu yok"
        if a in BILGI_KONTROLLERI:
            k["ne_olacak"] = "Bilgi için gösterilir; işlem yapılmaz"
        # Onerinin kaynagi (kartta bolum basliginda): dil modeli ya da kod.
        k["oneri_kaynagi"] = "kod"
        if a in ("ayni_icerik", "yakin_icerik"):
            gr = [g for g in ek.get("ayni_gruplar") or []
                  if (g.get("tur") == "yakin") == (a == "yakin_icerik")]
            if gr:
                k["ne_olacak"] = "Biri kalır, diğerleri üretime girmez"
                k["gruplar"] = [{"id": g["id"], "oneri": g["oneri"],
                                 "gerekce": g.get("gerekce", ""),
                                 "kaynak": g.get("kaynak", ""), "secim": _ayni_kalan(p, g),
                                 "iliski": g.get("iliski_metni", ""),
                                 "uyeler": [{"ad": u, "aciklama": aciklama.get(u, ""),
                                             "cikar": (g.get("elenen") or {}).get(u, ""),
                                             "guc": (g.get("guc") or {}).get(u),
                                             "bulgular": (g.get("uye_bulgu") or {}).get(u, [])}
                                            for u in (g.get("sira") or g["uyeler"])]}
                                for g in gr]
        if a == "set_cakisma":
            _set_cakisma_satiri(k, ek, durum)
            kontroller.append(k)
            continue
        if a == "tekrar":
            tk = ek.get("tekrar") or {}
            k["birim"] = "satır"
            for oge, _tur, n_ in _tekrar_ogeleri(ek):
                satir = {"ad": oge, "aciklama": "", "bulgu": "%s fazla satır" % _sayi(n_)}
                dz = _satir_duzeltme(durum, "tekrar", oge)
                if dz:
                    satir["duzeltme"] = dz
                k["kolonlar"].append(satir)
            k["sayi"] = int(tk.get("toplam") or 0)
            k["ne_olacak"] = KURAL_SONUC_ADI["tekrar"] if updt_modu(durum) \
                else "Bilgi için gösterilir"
            if tk.get("kimlik") is None:
                k["kural"] += " Kimlik kolonu seçilmediği için yalnız bütün kolonları aynı satırlara bakıldı."
            kontroller.append(k)
            continue
        for kol, metin in (bulgu.get(a) or {}).items():
            satir = {"ad": kol, "aciklama": aciklama.get(kol, ""), "bulgu": metin}
            if sonuc == SONUC_KARAR:
                satir["karar"] = karar_deger.get(kol, karar_vars.get(kol, PROFIL_KARAR_TUT))
                o = ((p.get("llm_oneri") or {}).get(a) or {}).get(kol) or {}
                llm_var = o.get("kaynak") == "kod" \
                    and o.get("oneri") in (PROFIL_KARAR_TUT, PROFIL_KARAR_CIKAR)
                # Bu kontrolun onerisi (kolon birden cok kontroldeyse biri
                # Çıkar diyorsa kolonun onerisi Çıkar: karar_oneri_kolon).
                satir["karar_oneri"] = o["oneri"] if llm_var else _karar_kurali(a)
                satir["karar_oneri_kolon"] = karar_vars.get(kol, PROFIL_KARAR_TUT)
                satir["karar_kaynak"] = o["kaynak"] if llm_var else "kural"
                satir["karar_gerekce"] = (o.get("gerekce") or "") if llm_var else (
                    KARAR_KURAL_GEREKCESI.get(_karar_kurali(a), "Kural önerisi."))
            if a in COZUM_KONTROLLERI and (cozum_oneri.get(kol) or {}).get("kontrol") == a:
                satir["cozum"] = _cozum_satiri(kol, cozum_oneri[kol], cozum_sec, cozum_bilgi)
            elif a in DUZELTME_KONTROLLERI and kol in (duz_oneri.get(a) or {}):
                satir["duzeltme"] = _duzeltme_satiri(duz_oneri[a][kol], duz_sec[a][kol],
                                                     (duz_bilgi.get(a) or {}).get(kol))
            elif a in COZUM_KONTROLLERI and kol in cozum_oneri \
                    and len(cozum_oneri[kol].get("secenekler") or []) < 2:
                satir["cozum"] = _cozum_satiri(kol, cozum_oneri[kol], cozum_sec, cozum_bilgi)
            elif a in COZUM_KONTROLLERI and kol in cozum_oneri:
                satir["cozum_baska"] = {x[0]: x[1] for x in PROFIL_KONTROLLERI}.get(
                    cozum_oneri[kol]["kontrol"], "")
            k["kolonlar"].append(satir)
        if any(len((s.get("cozum") or {}).get("secenekler") or []) > 1 for s in k["kolonlar"]):
            k["ne_olacak"] = "Çözüm seçilir; ham kolon üretime girmez"
        elif a in COZUM_KONTROLLERI and k["kolonlar"]:
            k["ne_olacak"] = "Üretime girmez; uygun çözüm bulunmadı"
        k["sayi"] = len(k["kolonlar"])
        kontroller.append(k)

    m = durum.get("meta") or {}
    kayit = p.get("profil_kayit") or (
        ("%s veri seti" % p["profil_dataset"]) if p.get("profil_dataset")
        else "PROJE_HAFIZASI/veri_profili.parquet")
    n = p.get("null_ozet") or {}
    return {
        "tip": "profil",
        "adim": "veri_profili",
        "karar_bekliyor": bool(karar and profil_karar_var(durum)),
        "satir": p.get("profil_satir") if p.get("profil_satir") is not None else p.get("satir"),
        "kapsam": p.get("profil_kapsam") or {},
        "kolon": len(incelenen),
        "temiz": len(oz["temiz"]),
        "kusurlu": len(oz["girmez"]),
        "bilgi": len(oz["bilgi"]),
        "bekleyen": len(oz["bekleyen"]) if karar else 0,
        "karar_sayi": len(profil_karar_kolonlari(durum)),
        "turler": turler,
        "eksik": {"yok": int(n.get("hic_null_yok") or 0), "az": int(n.get("az") or 0),
                  "orta": int(n.get("orta") or 0), "asiri": int(n.get("asiri") or 0)},
        "eksik_esik": {"az": NULL_AZ, "asiri": esik["cok_bos"]},
        "esik_notu": esik_degisiklik_notu(durum),
        "eksik_kolon": p.get("null_kolon_adet"),
        "eksik_maks": p.get("null_maks"),
        "eksik_maks_kolon": p.get("null_maks_kolon"),
        "kontroller": _genel_kontrol_satirlari(esik) + kontrolleri_grupla(kontroller),
        "hedef": ek.get("hedef"),
        "haric": {"hedef": m.get("target") or "", "kimlik": m.get("id") or "",
                  "donem": m.get("donem") or "",
                  "surec_disi": len(set(durum.get("haric_kolonlar") or []))},
        "kayit": kayit,
        "dusme_atif": akis_atif.adim("baz"),
        "dusme_metni": ("kararlarınızı onayladığınızda UPDT veriden çıkarılır"
                        if updt_modu(durum) else
                        "%s adımında veri setinden çıkarılır" % akis_atif.adim("baz")),
    }


SET_TUR_ADI = {"kimlik": "aynı kimlik", "anahtar": "aynı kimlik ve dönem",
               "tam": "bütün kolonları aynı satır"}


def set_cakisma_sayilari(ek):
    """(sizinti satiri, toplam cakisan satir): sizinti = ayni kimlik ve
    donem ya da ayni satir; toplam = herhangi bir cakismasi olan satir
    (set basina en buyuk sayim; kimlik cakismasi digerlerini kapsar)."""
    sc = ek.get("set_cakisma") or {}
    toplam, sizinti = {}, {}
    for x in sc.get("cakisma") or []:
        toplam[x["set"]] = max(toplam.get(x["set"], 0), x["satir"])
        if x["tur"] in ("anahtar", "tam"):
            sizinti[x["set"]] = max(sizinti.get(x["set"], 0), x["satir"])
    return sum(sizinti.values()), sum(toplam.values())


def _set_cakisma_satiri(k, ek, durum=None):
    """Setler Arasi Cakisma kontrol satirinin bulgu satirlari; ayni kayit
    (ayni kimlik ve donem ya da ayni satir) icin satir cikarma secimi."""
    from fe_agent.akis_durum import set_basligi
    sc = ek.get("set_cakisma")
    b = ek.get("set_bolme") or {}
    k["birim"] = "satır"
    k["ne_olacak"] = "Bilgi için gösterilir"
    if sc is None:
        k["uygulandi"], k["sebep"] = False, "Bölme okunamadı"
        k["sayi"] = 0
        return
    if len(sc.get("setler") or {}) < 2:
        k["uygulandi"], k["sebep"] = False, "Train dışında set yok"
        k["sayi"] = 0
        return
    zamansal = b.get("test_tanim") == "zamansal"
    for x in sc.get("cakisma") or []:
        ad = "%s: %s" % (set_basligi(x["set"], b.get("test_tanim")), SET_TUR_ADI[x["tur"]])
        if x["tur"] == "kimlik":
            metin = "Train'de de geçen %s kimlik, %s satır (setin %s)" % (
                _sayi(x["kimlik"]), _sayi(x["satir"]), _yuzde_metni(x["pay"]))
            if zamansal and x["set"] in ("test", "oot"):
                metin += ". Zamansal bölmede aynı kaydın sonraki dönemlerde olması beklenir"
            elif b.get("birim") == "satir":
                metin += (". Bölme birimi Satır; Kimlik seçilirse aynı kimlik tek sette "
                          "kalır")
        elif x["tur"] == "anahtar":
            metin = ("Aynı kimlik ve dönem Train'de de var: %s satır (setin %s). Aynı kayıt "
                     "iki sette, test sonucu olduğundan iyi görünür" % (
                         _sayi(x["satir"]), _yuzde_metni(x["pay"])))
        else:
            metin = ("Bütün kolonları Train'deki bir satırla aynı: %s satır (setin %s)"
                     % (_sayi(x["satir"]), _yuzde_metni(x["pay"])))
        satir = {"ad": ad, "aciklama": "", "bulgu": metin}
        dz = _satir_duzeltme(durum, "set_cakisma", ad) if durum is not None else None
        if dz:
            satir["duzeltme"] = dz
        k["kolonlar"].append(satir)
    sizinti, toplam = set_cakisma_sayilari(ek)
    k["sayi"] = toplam
    if sizinti:
        k["ne_olacak"] = KURAL_SONUC_ADI["set_cakisma"] if (durum is not None and updt_modu(durum)) \
            else ("Bilgi için gösterilir; aynı kayıt iki sette, bölmeyi 01.4'te "
                  "değiştirebilirsiniz")


def _cozum_satiri(kol, oneri, secim, bilgi):
    """Kart satirinin cozum alani: secenekler (ad, aciklama), oneri, secim,
    gerekce; uygulandiysa uretilen kolonlar ve ozet."""
    from fe_agent import kolon_cozum as kc
    c = {"secenekler": [{"kod": x, "ad": kc.COZUM_ADI.get(x, x),
                         "aciklama": kc.COZUM_ACIKLAMA.get(x, "")}
                        for x in oneri.get("secenekler") or []],
         "oneri": oneri.get("oneri"), "secim": secim.get(kol, oneri.get("oneri")),
         "gerekce": oneri.get("gerekce", ""), "kaynak": oneri.get("kaynak") or "kod"}
    b = bilgi.get(kol)
    if isinstance(b, dict) and b.get("cozum") == c["secim"]:
        c["kolonlar"] = list(b.get("kolonlar") or [])
        c["ozet"] = b.get("ozet") or ""
        c["ozet_kisa"] = _cozum_kisa_ozet(b)
    return c


def _duzeltme_satiri(oneri, secim, bilgi):
    """Kart satirinin duzeltme alani (cozum alaniyla ayni bicim)."""
    from fe_agent import kolon_cozum as kc
    c = {"secenekler": [{"kod": x, "ad": kc.COZUM_ADI.get(x, x),
                         "aciklama": kc.COZUM_ACIKLAMA.get(x, "")}
                        for x in oneri.get("secenekler") or []],
         "oneri": oneri.get("oneri"), "secim": secim, "gerekce": oneri.get("gerekce") or "",
         "kaynak": oneri.get("kaynak") or "kural"}
    if isinstance(bilgi, dict) and bilgi.get("secim") == secim:
        c["kolonlar"] = list(bilgi.get("kolonlar") or [])
        c["ozet_kisa"] = c["ozet"] = bilgi.get("ozet") or ""
    return c


def _cozum_kisa_ozet(b):
    """Tek satirlik ozet; ayrinti (grup uyeleri, sozcukler) i balonunda."""
    bilgi = b.get("bilgi") or {}
    c = b.get("cozum")
    if c == "dolu_bayrak":
        return "Dolu satır 1, boş satır 0."
    if c == "gun_farki":
        return b.get("ozet") or "Dönem sonuna gün farkı."
    if c == "metin":
        nb = len(bilgi.get("bayrak") or [])
        nk = len(((bilgi.get("konu") or {}).get("adlar")) or [])
        parca = ["sözcük sayısı ve skor"]
        if nb:
            parca.append("%d hedefle ilişkili sözcük bayrağı" % nb)
        if nk:
            parca.append("%d konu" % nk)
        return "Üretilenler: " + ", ".join(parca) + "."
    gruplar = bilgi.get("gruplar") or []
    if c == "seyrek_grupla":
        return "%d sık değer korunur, kalanlar «Diğer»." % len(gruplar)
    oran = [g.get("oran") for g in gruplar if isinstance(g.get("oran"), (int, float))]
    if not gruplar:
        return ""
    metin = "%d grup" % len(gruplar)
    if oran:
        yz = lambda v: "%" + ("%.1f" % (v * 100)).replace(".", ",")
        metin += "; hedef oranı %s ile %s arası" % (yz(min(oran)), yz(max(oran)))
    return metin + "."


def _esik_satiri_mi(kayit):
    alan = ((kayit.get("ekran") or {}).get("secim_alani") or {}) if isinstance(kayit, dict) else {}
    return alan.get("tip") == "profil_esik"


def acik_esik_tazele(durum):
    """Kayitli oturum yuklenirken ACIK (onay bekleyen) esik formu guncel
    koddan yeniden kurulur: eski kayitta kalan form (eski adlar, sayilar
    yok) gosterilmez. Girilmis hata mesaji korunur; esik degerleri zaten
    durumdan (profil_esikleri) gelir."""
    alan = durum.get("_secim_alani")
    if not (isinstance(alan, dict) and alan.get("tip") == "profil_esik") or alan.get("kilitli"):
        return False
    try:
        durum["_secim_alani"] = esik_formu(durum, alan.get("hata") or None)
        return True
    except Exception:
        return False


def profil_gecmisini_tazele(durum, gecmis):
    """Yenilemede 02.1 blogu guncel haliyle cizilir. Transkript degismez:
    doner yeni liste.
      * Esik formu satiri: esikler onaylandiysa (adim gecildi ya da karar
        kartinda bekliyor) formun onaylanan esiklerle KILITLI hali.
      * Profil karti: adim gecildiyse esik satiri disindaki metinli ya da
        ekranli ILK 02.1 satirina yazilir; diger 02.1 satirlari kartsiz ve
        metinsiz kalir (kart iki kez cizilmez)."""
    from fe_agent.akis_kayit import adim_sirasi
    sira = adim_sirasi(durum.get("mod"))
    if "veri_profili" not in sira:
        return gecmis
    i = int(durum.get("i") or 0)
    adim_i = sira.index("veri_profili")
    gecti = adim_i < i
    esik_kilit = gecti or (adim_i == i and durum.get("bekleyen") == "onay")
    satirlar = [n for n, k in enumerate(gecmis or [])
                if isinstance(k, dict) and k.get("rol") == "bot" and k.get("adim") == "veri_profili"]
    if not satirlar:
        return gecmis
    yeni = list(gecmis)
    esik_satirlari = [n for n in satirlar if _esik_satiri_mi(gecmis[n])]
    # Kilitli degilse (form acik) eski kayittaki form da guncel koddan.
    for n in esik_satirlari:
        k = dict(yeni[n])
        eski_ = ((k.get("ekran") or {}).get("secim_alani") or {})
        k["ekran"] = {"secim_alani": esik_formu(durum, kilitli=True) if esik_kilit
                      else esik_formu(durum, eski_.get("hata") or None)}
        yeni[n] = k
    if not gecti:
        return yeni
    kart = profil_karti(durum)
    if not kart:
        return yeni
    digerleri = [n for n in satirlar if n not in esik_satirlari]
    if not digerleri:
        return yeni
    hedef = next((n for n in digerleri
                  if str(gecmis[n].get("metin") or "").strip() or gecmis[n].get("ekran")),
                 digerleri[-1])
    for n in digerleri:
        k = dict(yeni[n])
        if n == hedef:
            k["metin"] = profil_metni(durum)
            k["ekran"] = {"secim_alani": kart}
            k.pop("ekran_atlandi", None)
        else:
            k["metin"] = ""
            k.pop("ekran", None)
        yeni[n] = k
    return yeni

def _buyuk_veri_engeli(durum, adim):
    """SFA ve aralik hesabi su an pandas'ta: tablo webapp'e tam okunur.
    Veri seti motor esiginin (bkz. motor.py) ustundeyse bellek tasmasin
    diye adim acik bir mesajla durur."""
    from fe_agent import motor
    from fe_agent.akis_durum import AdimHatasi, modelleme_kaynagi
    ad, _amp = modelleme_kaynagi(durum)
    secilen, toplam = motor.sec([ad])
    if secilen == motor.SPARK:
        raise AdimHatasi(
            "%s bu veri setinde henüz çalıştırılamıyor: veri seti büyük "
            "(%s) ve bu adımın Spark sürümü hazır değil. Pandas sınırı "
            "amp_pandas_sinir_gb proje değişkeniyle yükseltilebilir, ama "
            "webapp belleği yetmezse adım yarıda kalır."
            % (adim, motor.boyut_metni(toplam)))


# ===========================================================================
# ADIM - TEK DEGISKEN ANALIZI (SFA)
# ===========================================================================
#   - SFA eleme yeri DEGIL; soru "degisken modele en iyi hangi haliyle
#     girer". Metrikleri kod hesaplar, her degisken icin YAPAY ZEKA karar
#     verir (arka planda, degisken basina ayri karar); kullanici sagdaki
#     Değişken Analizi sekmesinde her karari degistirebilir.
#   - Aralik onerileri SFA'nin icinde.
#   - Onay sorulmaz; adim karar kartinda durur, "Kararları Onayla" ile gecer.
SFA_KARAR_ONEK = "sfa kararları:"
SFA_ONAY_MESAJI = SFA_KARAR_ONEK + " onaylandı"


def karar_yolu(durum):
    from fe_agent.akis_faz01 import amp_klasor_adi
    return "/%s/%s" % (amp_klasor_adi(durum), sfa_karar.KARAR_DOSYA)


def sfa_detay_oku(durum):
    """{degisken: detay} (aralik onerisi + metrikler + grafik tablolari)."""
    a = (durum.get("sfa") or {}).get("aralik") or {}
    return sfa_karar.detay_oku(a["dosya"]) if a.get("dosya") else {}


def sfa_kararlari_oku(durum):
    yol = (durum.get("sfa") or {}).get("karar_dosya")
    return sfa_karar.kararlar_oku(yol) if yol else {}


def _diger_setler(durum, s):
    """Aralik onerisinin SIRA TUTARLILIGI yalniz Test (OOS) setinde olculur.
    Validasyon (OOT) son sinama setidir: hedefi SFA kararina (dil modeli
    girdisi, oneri metni) girerse temiz sinama olmaktan cikar."""
    test_tanim = bolme_ayarlari(durum).get("test_tanim")
    return {set_basligi(ad, test_tanim): s[ad] for ad in ("val",)
            if ad in s and bool(s[ad].any())}


def _detay_kur(kol, r, tablo, ar, df, target, tr, acik, sizinti, tip):
    """Tek degiskenin SFA detayi (aralik onerisi + metrikler + grafik +
    tip bilgisi). r: SFA tablosunun o degiskene ait satiri."""
    c_ler = {k: (None if pd.isna(r.get(ad)) else float(r.get(ad)))
             for k, ad in sfa_mod.C_DONUSUMLERI if ad in tablo.columns}
    iv = None if pd.isna(r.get("IV")) else float(r["IV"])
    d = dict(ar.get(kol) or {
        "ad": kol, "tur": "kategorik" if r.get("TYPE") == "categorical" else "sayısal",
        "sekil": None, "aralik_sayisi": 1, "ham_iv": iv,
        "ham_c": c_ler.get("ham"), "ayri": None, "dolu": None,
        "kesimler": None, "gruplar": None, "tutarlilik": {},
        "hassas": aralik_mod.hassas_mi(kol, acik.get(kol, "")),
        "etiketler": None, "oneri": "", "notlar": []})
    d.update(sfa_karar.degisken_detayi(df[kol], df[target], tr, c_ler))
    d["aciklama"] = acik.get(kol, "")
    d["sizinti"] = kol in sizinti
    d["iv_bandi"] = r.get("IV_BANDI")
    d["sfa_not"] = str(r.get("NOT") or "")
    d.update(tip or {"tip_kaynak": (d.get("sfa") or {}).get("tip"),
                     "tip_secenekleri": [], "tip_uygulanan": None, "tip_sebebi": ""})
    return d


def sfa_tip_degistir(durum, kol, kod):
    """SFA panelinde bir degiskenin tipi degisti: o degiskenin SFA'si yeni
    tiple YENIDEN hesaplanir (IV, C-value, aralik, grafik) ve karari yeni
    tipe gore kuraldan kurulur. Doner: (detay, kural_karari)."""
    from fe_agent.akis_durum import AdimHatasi
    detay = dict(sfa_detay_oku(durum))
    eski = detay.get(kol)
    if not eski:
        raise AdimHatasi("'%s' için SFA sonucu yok." % kol)
    kodlar = [o["kod"] for o in (eski.get("tip_secenekleri") or [])]
    kod = kod if kod in kodlar else None
    target = durum["meta"]["target"]
    df = analiz_df(durum)
    s = setler(durum, df)
    tr = s["egitim"]
    alt = df[[kol, target]].copy()
    if kod:
        yeni = sfa_karar.tip_uygula(alt[kol], kod)
        if yeni is alt[kol]:
            raise AdimHatasi("'%s' bu tipe çevrilemedi." % kol)
        alt[kol] = yeni
    tablo, ozet = sfa_mod.sfa_calistir(alt, target, [kol], train_maske=tr)
    if not len(tablo):
        raise AdimHatasi("'%s' yeni tipiyle ölçülemedi." % kol)
    acik = _aciklamalar(durum)
    ar = aralik_mod.hesapla(alt, target, [kol], tr, _diger_setler(durum, s), acik,
                            ozet.get("iv_skorlari"), ozet.get("c_skorlari"))
    tip = {"tip_kaynak": eski.get("tip_kaynak"),
           "tip_secenekleri": eski.get("tip_secenekleri") or [],
           "tip_uygulanan": kod,
           "tip_sebebi": "Sizin seçiminiz" if kod else ""}
    d = _detay_kur(kol, tablo.iloc[0], tablo, ar, alt, target, tr, acik,
                   set(ozet.get("sizinti") or []), tip)
    detay[kol] = d
    a = (durum.get("sfa") or {}).get("aralik") or {}
    sfa_karar.detay_yaz(a.get("dosya") or aralik_yolu(durum), detay)
    sf = durum.get("sfa") or {}
    if isinstance(sf.get("iv_skorlari"), dict):
        sf["iv_skorlari"][kol] = d.get("ham_iv")
    k = sfa_karar.kural_karari(d, d["sizinti"])
    return d, k


def _sfa_hesapla(durum):
    """SFA tablosu + aralik onerileri + degisken detayi + kural kararlari;
    ardindan yapay zeka karar isi arka planda baslar."""
    _buyuk_veri_engeli(durum, akis_atif.adim("sfa"))
    eski = (durum.get("sfa") or {}).get("ai_is")
    if eski:
        sfa_karar.ai_durdur(eski)
    # Eldeki BUTUN degiskenler: ham + uretilen (_ENRICHED). Uretilenler
    # burada profillenir; bos ya da sabit olanlar olculmez.
    df = analiz_df(durum)
    p = durum.get("profil") or {}
    p["uretilen_teshis"] = _uretilen_profili(durum, df)
    durum["profil"] = p
    target = durum["meta"]["target"]
    s = setler(durum, df)
    tr = s["egitim"]
    adaylar = analiz_adaylari(durum)

    # TIP KARARI SFA'DA: secenekler ve kural onerisi AMP kolonunun TAM
    # verisiyle; oneri varsa SFA o degiskeni yeni tipiyle olcer.
    tip_bilgi = {}
    df = df.copy(deep=False)
    for kol in adaylar:
        if kol not in df.columns or kol == target:
            continue
        sec = sfa_karar.tip_secenekleri(df[kol])
        kod, sebep = sfa_karar.tip_onerisi(kol, df[kol], sec)
        tip_bilgi[kol] = {"tip_kaynak": sfa_karar.seri_tipi(df[kol]),
                          "tip_secenekleri": sec, "tip_uygulanan": None,
                          "tip_sebebi": ""}
        if kod:
            yeni = sfa_karar.tip_uygula(df[kol], kod)
            if yeni is not df[kol]:
                df[kol] = yeni
                tip_bilgi[kol].update(tip_uygulanan=kod, tip_sebebi=sebep)

    tablo, ozet = sfa_mod.sfa_calistir(df, target, adaylar, train_maske=tr)
    diger = _diger_setler(durum, s)
    acik = _aciklamalar(durum)
    ar = aralik_mod.hesapla(df, target, adaylar, tr, diger, acik,
                            ozet.get("iv_skorlari"), ozet.get("c_skorlari"))
    sizinti = set(ozet.get("sizinti") or [])

    detay = {}
    for _, r in tablo.iterrows():
        kol = str(r["FEATURE"])
        if kol not in df.columns:
            continue
        detay[kol] = _detay_kur(kol, r, tablo, ar, df, target, tr, acik,
                                sizinti, tip_bilgi.get(kol))

    yol = aralik_yolu(durum)
    sfa_karar.detay_yaz(yol, detay)
    kyol = karar_yolu(durum)
    kararlar = {k: sfa_karar.kural_karari(d, d["sizinti"]) for k, d in detay.items()}
    sfa_karar.kararlari_yaz(kyol, kararlar)

    if len(tablo):
        tablo["EGILIM"] = tablo["FEATURE"].map(lambda k: (detay.get(str(k)) or {}).get("sekil"))
        tablo["ARALIK_SAYISI"] = tablo["FEATURE"].map(
            lambda k: (detay.get(str(k)) or {}).get("aralik_sayisi"))
    yazildi, yedek = ara_tablo_kaydet(durum, "SFA", tablo, "/sfa_tablosu.parquet")
    ozet.pop("iv_skorlari_tam", None)
    ozet.update({
        "tablo_dataset": yazildi, "tablo_yedek": None if yazildi else yedek,
        "train_satir": int(tr.sum()), "karar_dosya": kyol,
        "aralik": {"dosya": yol, "degisken": len(detay),
                   "onerilen": sum(1 for d in detay.values() if (d.get("aralik_sayisi") or 1) > 1),
                   "hassas": sorted(k for k, d in detay.items() if d.get("hassas"))},
        "hassas": sorted(k for k, d in detay.items() if d.get("hassas")),
        "onaylandi": False,
    })
    ozet["ilk20"] = _sfa_ilk20(tablo)
    ozet["ai_is"] = sfa_karar.ai_baslat(kyol, sfa_karar.ai_girdisi(detay, kararlar))
    durum["sfa"] = ozet


def _sfa_ozet_metni(durum):
    """01 Calisma Kurulumu yazim duzeni: tek cumle, Etiket : Deger satirlari,
    ne yapilacagi. Ayrinti sagdaki Değişken Analizi sekmesinde."""
    s = durum.get("sfa") or {}
    b = s.get("iv_bantlari") or {}
    ut = (durum.get("profil") or {}).get("uretilen_teshis") or {}
    ur_satir = ""
    if uretilenler(durum):
        kusur = sorted(set(ut.get("cok_bos") or []) | set(ut.get("sabit") or []))
        ur_satir = ("  Üretilen Değişken : %s ölçüldü · boş ya da sabit olduğu için "
                    "ölçülmeyen %s\n" % (_sayi(len(ut.get("temiz") or [])), _sayi_ad(kusur)))
    return ("Tek değişken analizi tamamlandı. Train (MS) setindeki %s satırda ham "
            "ve üretilen her değişkenin hedefle ilişkisi ölçüldü; eleme yapılmadı.\n"
            "  Ölçülen Değişken : %s\n"
            "%s"
            "  IV Dağılımı : güçlü %s · orta %s · zayıf %s · etkisiz %s\n"
            "  Sızıntı Şüphesi : %s\n"
            "  Hassas Değişken : %s\n"
            "Yapay zekâ her değişkenin modele hangi hâliyle gireceğine karar "
            "veriyor. Kararlar Değişkenler > Dağılım ve SFA bölümünde; değişken adına "
            "tıklayınca grafik, ölçütler ve karar formu açılır, istediğinizi "
            "değiştirebilirsiniz."
            % (_sayi(s.get("train_satir") or 0), _sayi(s.get("analiz_edilen") or 0),
               ur_satir, _sayi(b.get("güçlü", 0)), _sayi(b.get("orta", 0)),
               _sayi(b.get("zayıf", 0)), _sayi(b.get("etkisiz", 0)),
               _sayi_ad(s.get("sizinti")), _adlar(s.get("hassas"))))


def _sfa_karti(durum):
    s = durum.get("sfa") or {}
    durum["_secim_alani"] = {
        "tip": "sfa_karar",
        "baslik": "SFA Kararları",
        "ai_is": s.get("ai_is"),
        "toplam": (s.get("aralik") or {}).get("degisken") or 0,
        "buton": "Kararları Onayla",
        "sablon": SFA_ONAY_MESAJI,
    }


def sfa_girdi(durum, mesaj, yeniden_sor=False):
    """Adim karar kartinda durur. SFA henuz hesaplanmadiysa (ya da profil /
    bolme degistigi icin silindiyse) once hesaplanir; "Geri Dön" ile
    donuldugunde yeniden HESAPLANMAZ, kararlar yerinde durur."""
    from fe_agent.akis_durum import AdimHatasi
    m = (mesaj or "").strip().lower()
    if m.startswith(SFA_KARAR_ONEK) and not yeniden_sor and durum.get("sfa"):
        durum["_secim_alani"] = None
        return True, None
    if not (durum.get("sfa") or {}).get("karar_dosya"):
        try:
            _sfa_hesapla(durum)
        except AdimHatasi as e:
            durum["_secim_alani"] = None
            return False, str(e)
    _sfa_karti(durum)
    return False, _sfa_ozet_metni(durum)


def sfa_uygula(durum):
    """Kart onaylandi: kararlar sabitlenir (yapay zeka isi durur)."""
    s = durum.get("sfa") or {}
    if s.get("ai_is"):
        sfa_karar.ai_durdur(s["ai_is"])
    kararlar = sfa_kararlari_oku(durum)
    girmeyen = sorted(k for k, v in kararlar.items() if v.get("kullan") == "hayir")
    say = lambda alan, deger: sum(1 for v in kararlar.values()
                                  if v.get("kullan") != "hayir" and v.get(alan) == deger)
    kaynak = {k: sum(1 for v in kararlar.values() if v.get("kaynak") == k)
              for k in ("yapay_zeka", "kullanici", "kural")}
    s["onaylandi"] = True
    s["kullanilan"] = len(kararlar) - len(girmeyen)
    s["kararlar_ozet"] = {"girmeyen": girmeyen, "kaynak": kaynak}
    durum["sfa"] = s
    tip_say = sum(1 for v in kararlar.values()
                  if v.get("kullan") != "hayir" and v.get("tip") not in (None, "", "yok"))
    metin = ("SFA kararları kaydedildi.\n"
             "  Modele Girecek : %s\n"
             "  Girmeyecek : %s\n"
             "  Tip Değişikliği : %s\n"
             "  Önerilen Aralıklarla : %s\n"
             "  Dönüşüm : log %s · üstel %s · sıra %s\n"
             "  Winsor (%%1) : %s\n"
             "  Eksik İşareti : %s\n"
             "  Karar Kaynağı : yapay zekâ %s · sizin %s · kural %s\n"
             "Kararlar %s adımında uygulanır."
             % (_sayi(s["kullanilan"]), _sayi_ad(girmeyen), _sayi(tip_say),
                _sayi(say("ayriklastirma", "onerilen")), _sayi(say("donusum", "log")),
                _sayi(say("donusum", "ustel")), _sayi(say("donusum", "sira")),
                _sayi(say("aykiri", "winsor")), _sayi(say("eksik", "isaret")),
                _sayi(kaynak["yapay_zeka"]), _sayi(kaynak["kullanici"]),
                _sayi(kaynak["kural"]), akis_atif.adim("baz")))
    if kaynak["kural"] and s.get("ai_is"):
        metin += ("\nYapay zekâ kararı gelmeyen %s değişkende kural tabanlı karar "
                  "kullanıldı." % _sayi(kaynak["kural"]))
    return metin


def _psi_olculur_mu(durum):
    """PSI hangi sete karsi olculecek? Doner: "test" | None.

    Ayri bir OOT seti YOK: zamansal testte test ZATEN OOT'dur. Bu yuzden
    karsilastirma her zaman gelistirme ↔ test.

    Iki bolmede ayni hesap FARKLI soruyu cevaplar ve ikisi de degerlidir:
      zamansal -> test ileri donemdir; olculen sey ZAMAN kaymasidir.
      rastgele -> test ayni donemden gelir; olculen sey BOLMENIN
                  dengesizligidir ve ~0 beklenir. Sifirdan uzak cikmasi
                  bolmenin kendisinde bir sorun oldugunu soyler.
    Iki durumda da olculur; rapor hangi soruyu cevapladigini yazar."""
    b = durum.get("bolme") or {}
    # Zamansal bolme deterministiktir, kalici kayit bile gerektirmez. Test setinin fiilen
    # bos olup olmadigi maske hesaplandiktan SONRA denetleniyor.
    if (bolme_ayarlari(durum)["test_tanim"] == "zamansal"
            or b.get("kalici") or (b.get("satir") or {}).get("test")):
        return "test"
    return None


def stabilite_plan(durum):
    """Onay sorulmaz: olcum karar gerektirmiyor; sonuc baz set onayinda
    (dusurulecek kararsiz kolonlar) gorunur. Metin yalnizca "Geri Dön"
    ile donulunce gorunur."""
    durum["_plan_otomatik"] = True
    return "Stabilite yeniden ölçülecek. Onaylıyor musunuz?"

def stabilite_uygula(durum):
    hedef_set = _psi_olculur_mu(durum)
    if hedef_set is None:
        durum["stabilite"] = {"atlandi": True}
        return "Stabilite atlandı: karşılaştırılacak Validasyon (OOT) / Test (OOS) seti yok."

    df = analiz_df(durum)
    s = setler(durum, df)
    if not int(s["test"].sum()):
        durum["stabilite"] = {"atlandi": True}
        return ("Stabilite analizi atlandı; %s setinde satır yok."
                % set_basligi("test", bolme_ayarlari(durum)["test_tanim"]))
    # Ham + uretilen (SFA ile ayni kume).
    adaylar = analiz_adaylari(durum)

    tablo, ozet = sfa_mod.stabilite_calistir(df, adaylar, s["egitim"],
                                             s[hedef_set])
    if tablo is None:
        durum["stabilite"] = {"atlandi": True}
        return "Stabilite analizi yapılamadı."

    yazildi, yedek = ara_tablo_kaydet(durum, "PSI", tablo, "/stabilite.parquet")
    ozet["tablo_dataset"] = yazildi
    karsi = set_basligi("test", bolme_ayarlari(durum)["test_tanim"])
    ozet["karsilastirma"] = "Train (MS) ↔ %s" % karsi
    # Olcumun NE ANLAMA geldigi bolmeye gore degisir; rapor bunu yazmali
    # yoksa rastgele bolmedeki ~0 PSI "model saglam" diye okunur.
    ozet["olcum_turu"] = ("zaman kayması"
                          if bolme_ayarlari(durum)["test_tanim"] == "zamansal"
                          else "bölme dengesi")
    durum["stabilite"] = ozet

    en_kotu = " · ".join("%s %s" % (c, _ond(v, 3)) for c, v in (ozet.get("en_kotu") or [])[:3])
    return ("Stabilite ölçüldü (PSI, " + ozet["karsilastirma"] + "; %s).\n"
            "  Ölçülen Değişken : %s\n"
            "  Kararlı : %s  (PSI < %s)\n"
            "  Kayan : %s\n"
            "  En Yüksek PSI : %s\n"
            "  Kayıt : %s\n"
            "Kayan değişkenler %s adımında düşürülür."
            % (ozet["olcum_turu"], _sayi(ozet["olculen"]), _sayi(ozet["stabil"]),
               _ond(sfa_mod.PSI_ESIK, 2), _sayi_ad(ozet.get("kayan")),
               en_kotu or "-", _kayit_metni(yazildi, yedek), akis_atif.adim("baz")))

def _profil_cikarilan(p):
    """02.1'de kullanicinin Çıkar dedigi kolonlar."""
    karar = p.get("profil_karar") if isinstance(p.get("profil_karar"), dict) else {}
    return [k for k, v in karar.items() if v == "cikar"]


def _dusurulecek_kume(durum):
    """Baz sette DUSURULECEK kolonlarin tam kumesi.

    Teshis listelerine ek olarak durum["haric_kolonlar"] da buraya girer:
    surec disinda tutulan (Mod A'da sozlukte karsiligi olmayan) kolonlar
    profilden de haric tutuldugu icin hicbir teshis listesinde gorunmez;
    Hedef / kimlik / donem kolonlari asla dusurulmez. Uretilen
    degiskenlerden bos ve sabit olanlar da duser (SFA adiminda bulunur).
    Doner: (tum_dusurulecek, teshis_kaynakli, sozlukte_tanimsiz)
"""
    p = durum.get("profil") or {}
    t = p.get("profil_teshis") or {}
    ut = p.get("uretilen_teshis") or {}
    st = durum.get("stabilite") or {}
    korunan = _meta_kolonlar(durum)

    teshis = set(
        (t.get("cok_bos") or []) + (t.get("sabit") or []) +
        (t.get("kimlik_gibi") or []) + (t.get("yuksek_kardinalite") or []) +
        (t.get("tarih") or []) +
        (ut.get("cok_bos") or []) + (ut.get("sabit") or []) +
        (t.get("ayni_icerik") or []) + _profil_cikarilan(p) +
        (st.get("kayan") or [])) - korunan
    tanimsiz = set(durum.get("haric_kolonlar") or []) - korunan - teshis
    return sorted(teshis | tanimsiz), sorted(teshis), sorted(tanimsiz)


def _karar_ozeti(durum):
    """SFA kararlarindan baz sette yapilacaklar (sayilar)."""
    k = sfa_kararlari_oku(durum)
    kul = [v for v in k.values() if v.get("kullan") != "hayir"]
    return {
        "girmeyen": sum(1 for v in k.values() if v.get("kullan") == "hayir"),
        "aralik": sum(1 for v in kul if v.get("ayriklastirma") == "onerilen"),
        "donusum": sum(1 for v in kul if v.get("ayriklastirma") != "onerilen"
                       and (v.get("donusum") not in (None, "yok") or v.get("aykiri") == "winsor")),
        "isaret": sum(1 for v in kul if v.get("eksik") == "isaret"),
    }


def baz_plan(durum):
    p = durum.get("profil") or {}
    t = p.get("profil_teshis") or {}
    ut = p.get("uretilen_teshis") or {}
    st = durum.get("stabilite") or {}

    dusur, _teshis, tanimsiz = _dusurulecek_kume(durum)
    durum["_dusurulecek"] = dusur
    ko = _karar_ozeti(durum)
    return ("Analitik baz set ham ve üretilen değişkenlerle oluşturulacak; "
            "sızıntı kontrolü, aday değişken seti ve modelleme bu dondurulmuş "
            "sette yapılır.\n"
            "  Düşürülecek : %s kolon\n"
            "  Düşürme Sebebi : eksik %s · sabit %s · kimlik %s · kardinalite %s · "
            "tarih %s · aynı içerik %s · profilde çıkarılan %s · kararsız %s · "
            "süreç dışı %s\n"
            "  SFA Kararları : %s değişken modele girmeyecek · %s aralıkla · "
            "%s dönüşümle · %s eksik işaretiyle\n"
            "  Doldurma : SFA kararına göre; kararı olmayan sayısal kolonlar "
            "Train (MS) medyanıyla\n"
            "  Kayıt : %s_BAZ veri seti\n"
            "Oluşturayım mı?"
            % (_sayi(len(dusur)),
               _sayi(len(set(t.get("cok_bos") or []) | set(ut.get("cok_bos") or []))),
               _sayi(len(set(t.get("sabit") or []) | set(ut.get("sabit") or []))),
               _sayi(len(t.get("kimlik_gibi") or [])),
               _sayi(len(t.get("yuksek_kardinalite") or [])),
               _sayi(len(t.get("tarih") or [])),
               _sayi(len(t.get("ayni_icerik") or [])), _sayi(len(_profil_cikarilan(p))),
               _sayi(len(st.get("kayan") or [])), _sayi(len(tanimsiz)),
               _sayi(ko["girmeyen"]), _sayi(ko["aralik"]), _sayi(ko["donusum"]),
               _sayi(ko["isaret"]), durum["veri_seti"]))


def hedefe_gore_sirala(etiketler, seri, y, tr):
    """Aralik etiketleri egitimdeki hedef oranina gore (artan); egitimde
    gorulmeyen etiket sona (eski sirasiyla)."""
    et = [str(e) for e in etiketler]
    oran = y[tr].groupby(seri[tr].astype(str)).mean()
    return sorted(et, key=lambda e: (e not in oran.index or pd.isna(oran.get(e)),
                                     float(oran.get(e, 0) or 0), et.index(e)))


def aralik_siralari(durum):
    """{baz setteki aralik kolonu: [etiket, ...]}: modelin ve secimin
    etiketleri sira numarasina cevirmesi icin. Baz set kaydinda yoksa
    (eski calisma) SFA detayindan kurulur."""
    bz = durum.get("baz") or {}
    if isinstance(bz.get("aralik_sira"), dict):
        return bz["aralik_sira"]
    detay = sfa_detay_oku(durum)
    kaynak = bz.get("kaynak") or {}
    sira = {}
    for kol in (bz.get("kolonlar") or []) + (bz.get("uretilen_kolonlar") or []):
        if not str(kol).endswith("_ARALIK"):
            continue
        ad = kaynak.get(kol) or str(kol)[:-len("_ARALIK")]
        et = (detay.get(ad) or {}).get("etiketler")
        if et:
            sira[kol] = [str(e) for e in et]
    return sira


def _uretilen_dusus_sebebi(durum, ad, sfa_dusen):
    """Uretilen degisken baz sete neden girmedi (katalog ve panel icin)."""
    p = durum.get("profil") or {}
    ut = p.get("uretilen_teshis") or {}
    if ad in (ut.get("cok_bos") or []):
        return "eksik"
    if ad in (ut.get("sabit") or []):
        return "sabit"
    if ad in ((durum.get("stabilite") or {}).get("kayan") or []):
        return "kararsiz"
    if ad in sfa_dusen:
        return "sfa"
    return "diger"


def baz_uygula(durum):
    df = analiz_df(durum)
    tr, _ = maskeler(durum, df)

    # Plan adimi atlanmis olabilir; kumeyi burada da hesapla (savunma).
    tum, _teshis, tanimsiz = _dusurulecek_kume(durum)
    tum = sorted((set(tum) | set(durum.get("_dusurulecek") or []))
                 - _meta_kolonlar(durum))
    dusur = [c for c in tum if c in df.columns]

    df = df.drop(columns=dusur)
    # SFA KARARLARI: her degisken kararindaki haliyle (doldurma, kirpma,
    # donusum, aralik). Parametreler gelistirme setinden. Kararla "modele
    # girmeyecek" denenler duser; yeni hali uretilen degiskenin ham kolonu
    # cikar (model degiskenin tek bir halini gorur).
    kararlar = {k: v for k, v in sfa_kararlari_oku(durum).items()
                if k not in _meta_kolonlar(durum)}
    df, rapor = sfa_karar.uygula(df, tr, kararlar, sfa_detay_oku(durum))
    yeni_kolonlar = rapor["uretilen"]
    dusur = sorted(set(dusur) | set(rapor["dusen"]))

    doldurma = {}
    for k in df.select_dtypes(include=[np.number]).columns:
        med = df.loc[tr, k].median()
        if not pd.isna(med):
            df[k] = df[k].fillna(med)
            doldurma[k] = round(float(med), 4)

    m = durum["meta"]
    # Bolme etiketi (_SPLIT) baz sette KORUNUR ama degisken degildir;
    # modelin degisken listesine girmez.
    tum_kolonlar = [c for c in df.columns
                    if c not in (m.get("target"), m.get("id"), m.get("donem"), SPLIT_KOLON)]
    # KAYNAK: baz setteki her kolonun SFA donusumunden onceki adi. Ham ve
    # uretilen ayri tutulur: Faz 05 baz modeli hamdan gelenlerle kurar,
    # uretilenler aday setten girer.
    kaynak = {c: rapor.get("kaynak", {}).get(c, c) for c in tum_kolonlar}
    uretilen = set(uretilenler(durum))
    baz_kolonlar = [c for c in tum_kolonlar if kaynak[c] not in uretilen]
    uretilen_kolonlar = [c for c in tum_kolonlar if kaynak[c] in uretilen]
    kalan = {kaynak[c] for c in uretilen_kolonlar}
    sfa_dusen = set(rapor["dusen"])
    uretilen_dusen = {a: _uretilen_dusus_sebebi(durum, a, sfa_dusen)
                      for a in sorted(uretilen - kalan)}
    # ARALIK SIRASI: aralik kolonlari metin etiket tasir ("0 - 1", "2 - 8");
    # model ve secim bunlari bu siraya gore sayiya cevirir.
    detay = sfa_detay_oku(durum)
    aralik_sira = {}
    for c in tum_kolonlar:
        if str(c).endswith("_ARALIK"):
            et = (detay.get(kaynak[c]) or {}).get("etiketler")
            if et:
                aralik_sira[c] = [str(e) for e in et]
    # SIRA = EGITIMDEKI HEDEF ORANI (artan): aralik kodu degerin sirasi
    # degil, hedef oranini izler; U seklindeki iliski dogrusal modelde de
    # kaybolmaz. Egitimde gorulmeyen etiket sona.
    try:
        _hedef = (durum.get("meta") or {}).get("target")
        if aralik_sira and _hedef in df.columns:
            _tr = pd.Series(maskeler(durum, df)[0], index=df.index).fillna(False).astype(bool)
            _y = pd.to_numeric(df[_hedef], errors="coerce")
            for c, et in list(aralik_sira.items()):
                if c in df.columns:
                    aralik_sira[c] = hedefe_gore_sirala(et, df[c], _y, _tr)
    except Exception:
        pass

    # Hedef veri seti akista tanimli degilse adim COKMESIN: hesap korunur,
    # tablo yedek dosyaya yazilir ve kullaniciya acik bir uyari verilir.
    if updt_modu(durum):
        # YENI DUZEN: baz set UPDT verinin 03.3 sonundaki halidir.
        baz_ds = updt_adi(durum)
        try:
            updt_yaz(durum, df, "03.3")
            yazildi, yedek = baz_ds, None
        except Exception as e:                # pylint: disable=broad-except
            yazildi, yedek = None, str(e)[:160]
    else:
        baz_ds = "%s_BAZ" % durum["veri_seti"]
        # Veri seti Flow'da yoksa webapp kurar (kullanici Flow'a bir sey
        # eklemez; kaynak tablonun baglantisinda Parquet). Kurulamazsa yedek
        # dosyaya yazilir ve uyari verilir.
        try:
            from fe_agent import spark_is
            spark_is.veri_seti_hazirla(baz_ds, durum["veri_seti"])
        except Exception:
            pass
        yazildi, yedek = _yaz(baz_ds, df, "/analitik_baz_set.parquet")

    # Dusen kolonlar durum["haric_kolonlar"]'a YAZILMAZ: o liste Faz 01'in
    # (AMP veri seti) ve uretimin girdisi; geri donulup uretim yeniden
    # yapilinca kararsiz ya da SFA'da dusen ham kolonlar uretimden
    # sessizce cikmasin. Dusenler burada, "dusen"de.
    durum["baz"] = {"yeni_kolonlar": yeni_kolonlar, "sfa_degisen": rapor["degisen"],
                    "dataset": yazildi, "doldurma": "medyan (Train (MS))",
                    "doldurma_degerleri": doldurma, "dusen": dusur,
                    "kolon": int(df.shape[1]), "kolonlar": baz_kolonlar,
                    "uretilen_kolonlar": uretilen_kolonlar, "kaynak": kaynak,
                    "uretilen_dusen": uretilen_dusen, "aralik_sira": aralik_sira}

    if not yazildi:
        durum["baz"]["hata"] = ("'%s' veri setine yazılamadı" % baz_ds)
        return ("Analitik baz set hesaplandı ama %s veri setine yazılamadı.\n"
                "  Yedek : PROJE_HAFIZASI%s\n"
                "  Düşürülen : %s kolon\n"
                "  Doldurulan : %s kolon\n"
                "Sonraki adımlar kaynak veri setiyle devam eder; bu temizlik "
                "uygulanmamış olur. Adımı yeniden çalıştırmayı deneyin."
                % (baz_ds, yedek, _sayi(len(dusur)), _sayi(len(doldurma))))

    return ("Analitik baz set hazır.\n"
            "  Kolon : %s  (ham %s · üretilen %s)\n"
            "  Düşürülen : %s kolon\n"
            "  Doldurulan : %s kolon  (Train (MS) medyanı)\n"
            "  SFA Kararıyla Girmeyen : %s\n"
            "  Yeni Hâliyle Giren : %s\n"
            "  Kayıt : %s veri seti"
            % (_sayi(df.shape[1]), _sayi(len(baz_kolonlar)), _sayi(len(uretilen_kolonlar)),
               _sayi(len(dusur)), _sayi(len(doldurma)),
               _sayi_ad(rapor["dusen"]), _sayi_ad(yeni_kolonlar), baz_ds))
