# -*- coding: utf-8 -*-
"""fe_agent/akis_faz02.py - Veri Profili (Faz 02'nin ilk adimi) ve Faz 03 -
Veri Anlama ve Hazirlama: SFA, stabilite, baz set.

SIRA: Veri Profili ham kolonlarla calisir (kusurlu kolonlardan degisken
uretilmesin diye uretimden once). SFA, stabilite ve baz set ise uretimden
SONRA, eldeki butun degiskenlerle (ham + uretilen; _ENRICHED) calisir.
"""


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
                  | set(t.get("ayni_icerik") or [])
                  | {k for k, v in karar.items() if v == "cikar"})


# ===========================================================================
# 02.1 COZUMLER (bkz. kolon_cozum.py): "uretime girmez" denen kolon atilmadan
# once cozum onerilir; secilen cozumun kolonlari (IL_GRP, NOT_SKOR ...)
# uretilen degisken gibi sonraki adimlara girer, ham kolon girmez.
# ===========================================================================
COZUM_KAYNAK = "cozum"
COZUM_KONTROLLERI = ("cok_bos", "kimlik_gibi", "yuksek_kardinalite")


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
    secim = {k: c for k, c in cozum_secimi(durum).items() if c != "cikar"}
    bilgi_hepsi = {}
    if secim:
        df = modelleme_df(durum)
        target = (durum.get("meta") or {}).get("target")
        tr = setler(durum, df)["egitim"]
        y = df[target] if target in df.columns else pd.Series(np.nan, index=df.index)
        mevcut = set(map(str, df.columns))
        for k, c in secim.items():
            if k not in df.columns:
                continue
            o = cozum_onerileri(durum).get(k) or {}
            if c == "metin":
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
    yeni = {c for v in bilgi_hepsi.values() for c in v["kolonlar"]}
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
        elif v.get("kolonlar"):
            df[v["kolonlar"][0]] = kc.uygula(v["cozum"], df[k], v["bilgi"])
    return df


def uretim_kolonlari(durum):
    """Kural / kesif adimlarinin urettigi kolonlar (cozum kolonlari haric)."""
    cozum = set(((durum.get("uretilen_kaynak") or {}).get(COZUM_KAYNAK)) or [])
    return [k for k in uretilenler(durum) if k not in cozum]


def uretilenler(durum):
    return [str(x) for x in (durum.get("uretilen") or []) if x]


def zengin_adi(durum):
    return "%s_ENRICHED" % durum.get("veri_seti")


def analiz_df(durum):
    """Faz 03'un tablosu: degisken uretildiyse _ENRICHED (ham + uretilen),
    uretilmediyse modelleme tablosu. Uretilen kolondaki sonsuz deger (ornek:
    sifira bolme) bos sayilir; profil onu eksik deger olarak gorur."""
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
    _tablo, t = sfa_mod.profil_cikar(df[uretilen])
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
    try:
        from fe_agent import sozluk_calisma
        sz = sozluk_oku(durum)
        ad_k = sozluk_calisma.degisken_kolonu_bul(sz)
        harita = {str(c).strip().upper(): c for c in sz.columns}
        olcu_k = harita.get("OLCU")
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
     "Metin kolonda farklı değer sayısı bu değerin üstündeyse", "sayi", 2, 1000000),
    ("baskin", "Neredeyse Sabit",
     "En sık görülen değer satırların en az bu kadarında geçiyorsa", "yuzde", 0.50, 0.9999),
    ("donem_min_satir", "Dönemde Boş ya da Sabit",
     "Tek değer, yalnız en az bu kadar satırı olan dönemlerde aranır",
     "sayi", 1, 1000000000),
    ("gizli", "Gizli Eksik (Özel Kod)",
     "-999, 9999 gibi özel bir kod dolu satırların bu değerinden fazlasında geçiyorsa",
     "yuzde", 0.0001, 0.50),
    ("sifir", "Sıfır Yoğunluğu",
     "Dolu satırların en az bu kadarı sıfırsa", "yuzde", 0.50, 1.0),
    ("sicrama", "Dönemler Arası Eksik Sıçraması",
     "Art arda iki dönem arasında boş hücre oranı bu kadar puandan fazla değişiyorsa",
     "puan", 0.01, 0.99),
    ("uc_kat", "Uç Değer Yoğunluğu",
     "En büyük değer, değerlerin %99'unun altında kaldığı sınırın bu katından büyükse",
     "kat", 2, 1000000000),
)
# Formda her kontrolun duz dille aciklamasi: "kisa" satirda, "bilgi" i
# balonunda (nedir, neden onemli, ornek, yakalanirsa ne olur, onerilen
# degerin gerekcesi), "sonuc" yakalanan kolona ne oldugu (NE_OLACAK ile
# ayni sozler).
PROFIL_ESIK_ACIKLAMA = {
    "cok_bos": {
        "kisa": "Çoğu boş olan kolonun değerleri güvenilir bilgi taşımaz; dolu olup olmaması "
                "ise bilgi taşıyabilir.",
        "sonuc": "Çözüm önerilir; çözüm yoksa üretime girmez",
        "bilgi": "**Nedir?** Kolonun satırlarının ne kadarının boş olduğuna bakar.\n\n"
                 "**Neden önemli?** Satırların çoğunda boş olan kolon, modele ancak az sayıda "
                 "satırda bilgi verir; boşlukların nasıl doldurulduğu sonucu belirler hale gelir.\n\n"
                 "**Örnek:** 100.000 satırın 60.000'inde boş olan kolonun boş oranı %60'tır; eşik "
                 "%50 ise yakalanır.\n\n"
                 "**Yakalanırsa:** ham kolon değişken üretimine girmez. Yerine kolonun dolu "
                 "olup olmadığını gösteren 1/0 bayrağı önerilir; siz seçersiniz.\n\n"
                 "**Neden %50 önerildi?** Kolonun en az yarısı dolu olsun diye. Daha sıkı (ör. "
                 "%30) seçerseniz daha çok kolon dışarıda kalır; daha gevşek (ör. %80) seçerseniz "
                 "çok boş kolonlar da üretime girer."},
    "kimlik": {
        "kisa": "Neredeyse her satırda farklı değer alan kolon (müşteri no, işlem no gibi) "
                "bir şey öğretmez, yalnız satırı tanır.",
        "sonuc": "Çözüm önerilir; çözüm yoksa üretime girmez",
        "bilgi": "**Nedir?** Kolondaki farklı değer sayısını satır sayısına böler. Bu oran çok "
                 "yüksekse kolon bir kimlik gibi davranır.\n\n"
                 "**Neden önemli?** Kimlik gibi bir kolon her satırda farklı olduğu için model "
                 "ondan genellenebilir bir şey öğrenemez; ezberler.\n\n"
                 "**Örnek:** 100.000 satırda 98.000 farklı değer: oran %98; eşik %95 ise "
                 "yakalanır.\n\n"
                 "**Kapsam:** yalnız tam sayı ve metin kolonlara bakılır. Bakiye, tutar gibi "
                 "ondalıklı kolonlar doğal olarak hep farklıdır, bu kontrole girmez. 100'den az "
                 "farklı değeri olan kolon da girmez.\n\n"
                 "**Yakalanırsa:** ham kolon değişken üretimine girmez. Değerler kod "
                 "yapısındaysa (posta kodu gibi) ve ilk karakterlerle oluşan gruplar hedefi "
                 "ayırıyorsa gruplama, serbest metinse metinden özellik önerilir; gerçek kimlik "
                 "numarasında çözüm yoktur, kolon çıkarılır.\n\n"
                 "**Neden %95 önerildi?** Gerçek kimlik kolonları %100'e çok yakındır; %95, "
                 "küçük tekrarlara rağmen kimlikleri yakalar, gerçek bilgi taşıyan kolonları "
                 "bırakır."},
    "kardinalite": {
        "kisa": "Çok fazla farklı değeri olan metin kolon (il, açık adres, serbest not gibi) "
                "olduğu gibi kullanılamaz; gruplanarak ya da metinden özellik çıkarılarak "
                "kullanılır.",
        "sonuc": "Çözüm önerilir; çözüm yoksa üretime girmez",
        "bilgi": "**Nedir?** Metin (kategorik) kolonda kaç farklı değer olduğunu sayar.\n\n"
                 "**Neden önemli?** Kategorik kolonlar her değer için ayrı grup olarak "
                 "kullanılır. Yüzlerce farklı değer, her biri az satırlı yüzlerce grup demektir; "
                 "model bu küçük gruplardan güvenilir bir şey öğrenemez.\n\n"
                 "**Örnek:** 81 farklı il adı olan kolon, eşik 50 ise yakalanır.\n\n"
                 "**Kapsam:** yalnız metin kolonlar; sayısal kolonlar girmez.\n\n"
                 "**Yakalanırsa:** ham kolon değişken üretimine girmez. Yerine hedef oranına "
                 "göre gruplama, seyrek değerleri «Diğer»de toplama, kodun ilk karakterleriyle "
                 "gruplama ya da metinden özellik önerilir; siz seçersiniz. Hiçbiri işe "
                 "yaramıyorsa kolon çıkarılır.\n\n"
                 "**Neden 50 önerildi?** 50'ye kadar farklı değer, her gruba yeterince satır "
                 "düşecek kadar azdır. Daha fazla değeri olan il gibi kolonlar yakalansa da "
                 "gruplanarak kullanılır."},
    "baskin": {
        "kisa": "Neredeyse bütün satırlarda aynı değeri alan kolon az bilgi taşır.",
        "sonuc": "Kararınıza bırakılır",
        "bilgi": "**Nedir?** Kolonda en sık görülen değerin satırların ne kadarında geçtiğine "
                 "bakar.\n\n"
                 "**Neden önemli?** Satırların %99'unda aynı değer varsa kolon yalnız kalan %1'de "
                 "bilgi taşır; bu bazen değerli (nadir bir durum), çoğu zaman gürültüdür.\n\n"
                 "**Örnek:** 100.000 satırın 99.500'ünde 0 olan bayrak kolonu, eşik %99 ise "
                 "yakalanır.\n\n"
                 "**Yakalanırsa:** kolon tutulsun mu çıkarılsın mı size sorulur.\n\n"
                 "**Neden %99 önerildi?** Yalnız gerçekten neredeyse sabit olanlar sorulsun "
                 "diye; daha düşük seçerseniz daha çok kolon için karar vermeniz gerekir."},
    "donem_min_satir": {
        "kisa": "Bazı dönemlerde tamamen boş ya da tek değerli olan kolon, o dönemde veri "
                "toplanmamış olabilir.",
        "sonuc": "Kararınıza bırakılır",
        "bilgi": "**Nedir?** Kolona dönem dönem bakar: bir dönemde bütün satırlar boşsa ya da "
                 "hepsi aynı değerdeyse işaretler.\n\n"
                 "**Neden önemli?** Bu, o dönemde verinin toplanmadığını ya da kaynağın "
                 "değiştiğini gösterebilir; model o dönemlerde yanlış öğrenir.\n\n"
                 "**Eşik ne yapar?** Az satırlı bir dönemde tek değer tesadüfen çıkabilir. Bu "
                 "yüzden tek değer yalnız en az bu kadar satırı olan dönemlerde aranır. "
                 "Tamamen boş dönem ise satır sayısından bağımsız her zaman işaretlenir.\n\n"
                 "**Örnek:** 2023 Mart'ta 5.000 satırın hepsinde değer 0 ise (eşik 100) "
                 "işaretlenir; 30 satırlık bir dönemde hepsi 0 ise işaretlenmez.\n\n"
                 "**Yakalanırsa:** kolon tutulsun mu çıkarılsın mı size sorulur. Dönem kolonu "
                 "seçilmediyse bu kontrol yapılmaz.\n\n"
                 "**Neden 100 önerildi?** 100 satırda bütün değerlerin tesadüfen aynı çıkması "
                 "çok düşük bir ihtimaldir."},
    "gizli": {
        "kisa": "Boş yerine -999, 9999 gibi bir kodla doldurulmuş hücreler gerçek değer "
                "sanılır.",
        "sonuc": "Bilgi için gösterilir",
        "bilgi": "**Nedir?** Sayısal kolonda -1, -9, -99, -999 ya da 9999, 99999 gibi değerlerin "
                 "dolu satırların ne kadarında geçtiğine bakar. Değer, dağılımın geri "
                 "kalanından kopuksa (ör. öbür değerler 0 ile 500 arasında) özel kod sayılır.\n\n"
                 "**Neden önemli?** Bu kodlar aslında «bilgi yok» demektir; gerçek sayı gibi "
                 "kullanılırsa ortalama, toplam gibi hesaplar bozulur.\n\n"
                 "**Örnek:** bakiye kolonunda dolu satırların %3'ü -999 ise, eşik %1 olduğu "
                 "için gösterilir.\n\n"
                 "**Yakalanırsa:** bilgi için gösterilir, kolon üretime girer.\n\n"
                 "**Neden %1 önerildi?** %1'in altında kalan kod birkaç tesadüfi satır olabilir; "
                 "üstündeyse kolonun dolduruluş biçimidir."},
    "sifir": {
        "kisa": "Dolu satırların çoğu sıfır olan kolon (çoğu müşterinin hiç yapmadığı bir "
                "işlem gibi).",
        "sonuc": "Bilgi için gösterilir",
        "bilgi": "**Nedir?** Sayısal kolonda dolu satırların ne kadarının tam sıfır olduğuna "
                 "bakar.\n\n"
                 "**Neden önemli?** Sıfır yoğun kolonlarda ortalama ve sapma yanıltıcı olur; "
                 "bu kolonlar çoğu zaman «var mı, yok mu» olarak daha iyi kullanılır.\n\n"
                 "**Örnek:** dolu satırların %97'si 0 olan yurt dışı harcama kolonu, eşik %95 "
                 "ise gösterilir.\n\n"
                 "**Yakalanırsa:** bilgi için gösterilir, kolon üretime girer.\n\n"
                 "**Neden %95 önerildi?** Yalnız sıfırın gerçekten baskın olduğu kolonlar "
                 "gösterilsin diye."},
    "sicrama": {
        "kisa": "Bir dönemden ötekine boş oranı birden değişen kolon, veri kaynağında bir "
                "değişikliğe işaret eder.",
        "sonuc": "Bilgi için gösterilir",
        "bilgi": "**Nedir?** Art arda iki dönem arasında kolonun boş hücre oranının kaç puan "
                 "değiştiğine bakar.\n\n"
                 "**Neden önemli?** Ani değişim, verinin bir dönemden sonra farklı "
                 "toplandığını gösterebilir; model eski ve yeni dönemi aynı sanır.\n\n"
                 "**Örnek:** Ocak'ta %5 boş, Şubat'ta %30 boş: fark 25 puan; eşik 20 puan ise "
                 "gösterilir.\n\n"
                 "**Yakalanırsa:** bilgi için gösterilir, kolon üretime girer. Dönem kolonu "
                 "seçilmediyse bu kontrol yapılmaz.\n\n"
                 "**Neden 20 puan önerildi?** Dönemden döneme küçük oynamalar doğaldır; 20 "
                 "puanın üstü genellikle bir değişikliktir."},
    "uc_kat": {
        "kisa": "Diğer değerlerden çok büyük tekil değerler (ör. hatalı girilmiş tutar) "
                "hesapları bozar.",
        "sonuc": "Bilgi için gösterilir",
        "bilgi": "**Nedir?** Kolonun en büyük değerini, değerlerin %99'unun altında kaldığı "
                 "sınırla (99. yüzdelik) karşılaştırır.\n\n"
                 "**Neden önemli?** Birkaç aşırı büyük değer ortalama gibi hesapları tek başına "
                 "çeker; bunlar çoğu zaman hatalı giriştir.\n\n"
                 "**Örnek:** değerlerin %99'u 10.000 TL'nin altında, en büyük değer 5.000.000 "
                 "TL: 500 kat; eşik 100 kat ise gösterilir.\n\n"
                 "**Yakalanırsa:** bilgi için gösterilir, kolon üretime girer.\n\n"
                 "**Neden 100 kat önerildi?** Gelir, tutar gibi kolonlarda doğal olarak büyük "
                 "değerler vardır; 100 katın üstü doğal yayılımın çok dışındadır."},
}
ESIK_BIRIM_ADI = {"yuzde": "%", "puan": "puan", "sayi": "", "kat": "kat"}
ESIK_METNI = ("Veri profilinde her kolon aşağıdaki kontrollerden geçer. Her kontrolün bir "
              "sınırı (eşik) var ve önerilen değerle dolu geliyor. Olduğu gibi onaylayabilir "
              "ya da değiştirebilirsiniz; kontroller onayladığınız değerlerle yapılır. Bir "
              "kontrolün ne yaptığını ve önerilen değerin nedenini adının yanındaki «i»de "
              "okuyabilirsiniz.")
ESIK_DUGME = "Eşikleri Onayla ve Profili Çıkar"


def _esik_varsayilan():
    from fe_agent import profil_ek as pe
    d = dict(pe.ESIK_VARSAYILAN)
    d.update({"cok_bos": sfa_mod.NULL_ESIK, "kimlik": 0.95, "kardinalite": sfa_mod.KATEGORIK_MAX})
    return d


def profil_esikleri(durum):
    """Gecerli esikler: varsayilan + kullanicinin onayladigi."""
    d = _esik_varsayilan()
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
            hatalar.append("%s: değer boş" % kontrol)
            continue
        try:
            v = _esik_ic(birim, gelen[a])
        except (TypeError, ValueError):
            hatalar.append("%s: sayı değil" % kontrol)
            continue
        if birim in ("sayi", "kat"):
            v = int(round(v)) if float(v).is_integer() or birim == "sayi" else v
        if not (en_az <= v <= en_cok):
            hatalar.append("%s: %s ile %s arasında olmalı" % (
                kontrol, _esik_metni(birim, en_az), _esik_metni(birim, en_cok)))
            continue
        sonuc[a] = v
    if hatalar:
        return None, "Eşikler kaydedilmedi. " + "; ".join(hatalar) + "."
    return sonuc, None


def esik_formu(durum, hata=None, kilitli=False):
    """02.1 esik formu (tip profil_esik)."""
    simdiki = profil_esikleri(durum)
    varsayilan = _esik_varsayilan()
    satirlar = []
    for a, kontrol, anlam, birim, en_az, en_cok in PROFIL_ESIKLERI:
        ac = PROFIL_ESIK_ACIKLAMA.get(a) or {}
        satirlar.append({"anahtar": a, "kontrol": kontrol, "anlam": anlam, "birim": birim,
                         "kisa": ac.get("kisa", ""), "bilgi": ac.get("bilgi", ""),
                         "sonuc": ac.get("sonuc", ""),
                         "birim_adi": ESIK_BIRIM_ADI[birim],
                         "deger": _esik_ekran(birim, simdiki[a]),
                         "varsayilan": _esik_ekran(birim, varsayilan[a]),
                         "varsayilan_metni": _esik_metni(birim, varsayilan[a]),
                         "en_az": _esik_ekran(birim, en_az), "en_cok": _esik_ekran(birim, en_cok)})
    return {"tip": "profil_esik", "adim": "veri_profili", "satirlar": satirlar,
            "hata": hata or "", "kilitli": bool(kilitli), "buton": ESIK_DUGME}


def esik_degisiklik_notu(durum):
    """Varsayilandan farkli esikler (kartta ve metinde)."""
    simdiki, varsayilan = profil_esikleri(durum), _esik_varsayilan()
    parca = ["%s %s (önerilen %s)" % (kontrol, _esik_metni(birim, simdiki[a]),
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


def profil_hesapla(durum):
    """Veri profilini tablonun TAMAMINDAN cikarir: dort temel kontrol
    (sfa.profil_cikar) ve ek kontroller (profil_ek). Sonuc durum["profil"]."""
    from fe_agent import profil_ek
    df = modelleme_df(durum)
    m = durum["meta"]
    haric = set(durum.get("haric_kolonlar") or []) | {m.get("target"), m.get("id"), m.get("donem")}

    esik = profil_esikleri(durum)
    tablo, teshis = sfa_mod.profil_cikar(df, haric=haric, null_esik=esik["cok_bos"],
                                         kimlik_esik=esik["kimlik"],
                                         kategorik_max=esik["kardinalite"])
    yazildi, yedek = _yaz("%s_PROFIL" % durum["veri_seti"], tablo, "/veri_profili.parquet")

    p = durum.get("profil") or {}
    temel = set(teshis.get("cok_bos") or []) | set(teshis.get("sabit") or []) \
        | set(teshis.get("kimlik_gibi") or []) | set(teshis.get("yuksek_kardinalite") or [])
    adaylar = [str(k) for k in df.columns if k not in haric and k not in temel]
    ek = profil_ek.ek_kontroller(df, adaylar, donem=m.get("donem"), kimlik=m.get("id"),
                                 hedef=m.get("target"), olculer=_kart_olculeri(durum),
                                 esik=esik)
    # Sabit kolonun tek degeri (kartta bulgu olarak).
    ek["sabit_deger"] = {}
    for k in teshis.get("sabit") or []:
        dolu = df[k].dropna()
        ek["sabit_deger"][k] = profil_ek.deger_metni(dolu.iloc[0]) if len(dolu) else "boş"
    ek["ayni_gruplar"] = _ayni_gruplari(durum, ek, p)
    p["profil_teshis"] = teshis
    p["profil_ek"] = ek
    p["profil_dataset"] = yazildi
    # Onceki secim yalniz hala var olan gruplarda ve grubun uyesiyse gecerli.
    eski_secim = p.get("ayni_secim") if isinstance(p.get("ayni_secim"), dict) else {}
    uyeler = {g["id"]: set(g["uyeler"]) for g in ek["ayni_gruplar"]}
    p["ayni_secim"] = {k: v for k, v in eski_secim.items() if v in uyeler.get(k, set())}
    teshis["ayni_icerik"] = _ayni_kopyalar(p)
    # Onceki kararlar yalniz hala karar isteyen kolonlar icin gecerli.
    eski_karar = p.get("profil_karar") if isinstance(p.get("profil_karar"), dict) else {}
    p["profil_karar"] = {k: v for k, v in eski_karar.items()
                         if k in set(_karar_adaylari(p))}
    # COZUM ONERILERI: uretime girmez denen kolonlar icin (onceki secim
    # yalniz hala gecerli secenekse kalir).
    from fe_agent import kolon_cozum as kc
    target = (durum.get("meta") or {}).get("target")
    try:
        egitim = setler(durum, df)["egitim"]
    except Exception:
        egitim = None           # bolme okunamadi: oneri tum satirlardan
    p["cozum_oneri"] = kc.oneriler(df, teshis, esik["kardinalite"],
                                   y=df[target] if target in df.columns else None,
                                   egitim=egitim)
    eski_cozum = p.get("cozum_secim") if isinstance(p.get("cozum_secim"), dict) else {}
    p["cozum_secim"] = {k: v for k, v in eski_cozum.items()
                        if v in ((p["cozum_oneri"].get(k) or {}).get("secenekler") or [])}

    # Feature tablosunun kolon ozeti: veri seti secilirken cikarilmisti,
    # burada tekil sayisi ve kesin null orani ile tamamlaniyor. Ozet hic
    # yoksa (eski oturum) su an okunan tablodan uretiliyor.
    if not p.get("kolon_ozet"):
        p["kolon_ozet"] = kolon_ozeti_cikar(df)
    p["kolon_ozet"] = kolon_ozeti_tamamla(p, tablo, df)

    # EKSIK DEGER sekmesi: yalnizca ilk 20 satir + dagilim ozeti oturuma
    # yazilir; tam tablo yukarida dataset'e / yedege yazildi.
    ilk20, null_ozet, ek_alan = _eksik_ozeti(tablo, p.get("satir") or len(df),
                                             asiri=esik["cok_bos"])
    p["eksik_ilk20"] = ilk20
    p["null_ozet"] = null_ozet
    p.update(ek_alan)
    # Kartin satir sayisi ve kayit yeri (02.1 Veri Profili karti).
    p["profil_satir"] = int(len(df))
    p["profil_kayit"] = _kayit_metni(yazildi, yedek)
    durum["profil"] = p
    return p


AYNI_KURAL_GEREKCESI = "Dil modeli önerisi alınamadı; tablodaki ilk kolon önerildi."


def _ayni_gruplari(durum, ek, p):
    """Ayni icerikli gruplar ve dil modelinin kalacak kolon onerisi:
    [{"id", "uyeler", "oneri", "gerekce", "kaynak"}]. id: grubun tablodaki
    ilk kolonu. Ayni uyelerle onceden alinmis dil modeli onerisi tekrar
    sorulmaz (esik degisince yeniden hesaplanan profilde)."""
    ham = ek.get("ayni_icerik") or []
    if not ham:
        return []
    onceki = {g["id"]: g for g in ((p.get("profil_ek") or {}).get("ayni_gruplar") or [])
              if isinstance(g, dict) and g.get("kaynak") == "dil modeli"}
    gruplar = [{"id": g["kalan"], "uyeler": [g["kalan"]] + list(g["kopyalar"])} for g in ham]
    aciklama = _aciklamalar(durum)
    sorulacak = [g for g in gruplar
                 if not (g["id"] in onceki and onceki[g["id"]].get("uyeler") == g["uyeler"])]
    oneri, hata = {}, None
    if sorulacak:
        try:
            from fe_agent import llm as llm_mod
            oneri, hata = llm_mod.ayni_icerik_sec(
                [{"id": g["id"], "uyeler": [{"ad": u, "aciklama": aciklama.get(u, "")}
                                            for u in g["uyeler"]]} for g in sorulacak])
        except Exception as e:      # dil modeli yoksa kural gecerli
            hata = str(e)[:120]
    for g in gruplar:
        if g["id"] in onceki and onceki[g["id"]].get("uyeler") == g["uyeler"]:
            o = onceki[g["id"]]
            g.update({"oneri": o["oneri"], "gerekce": o.get("gerekce", ""), "kaynak": "dil modeli"})
        elif g["id"] in oneri:
            g.update({"oneri": oneri[g["id"]]["kalan"], "gerekce": oneri[g["id"]]["gerekce"],
                      "kaynak": "dil modeli"})
        else:
            g.update({"oneri": g["uyeler"][0], "gerekce": AYNI_KURAL_GEREKCESI, "kaynak": "kural"})
    return gruplar


def _ayni_kalan(p, g):
    s = (p.get("ayni_secim") or {}).get(g["id"])
    return s if s in g["uyeler"] else g["oneri"]


def _ayni_kopyalar(p):
    """Ayni icerikli gruplarda kalmayan (uretime girmeyen) kolonlar."""
    ek = p.get("profil_ek") or {}
    gruplar = ek.get("ayni_gruplar")
    if gruplar is None:      # eski calisma: ilk kolon kalir
        return sorted({k for g in (ek.get("ayni_icerik") or []) for k in g["kopyalar"]})
    return sorted({u for g in gruplar for u in g["uyeler"] if u != _ayni_kalan(p, g)})


def _karar_adaylari(p):
    """Karar isteyen kolonlar (sira korunur): neredeyse sabit, donemde bos
    ya da sabit. Ayni icerikli gruplarda kalmayan kolon karar istemez."""
    ek = p.get("profil_ek") or {}
    kopya = set(_ayni_kopyalar(p))
    ad = [x["kolon"] for x in (ek.get("baskin") or [])]
    ad += [x["kolon"] for x in (ek.get("donem") or [])]
    return [k for k in dict.fromkeys(ad) if k not in kopya]


def profil_karar_kolonlari(durum):
    return _karar_adaylari(durum.get("profil") or {})


def profil_karar_var(durum):
    """Kartta karar istenecek mi: Tut ya da Çıkar kolonu ya da ayni icerikli
    grup var."""
    p = durum.get("profil") or {}
    return bool(profil_karar_kolonlari(durum) or (p.get("profil_ek") or {}).get("ayni_gruplar")
                or cozum_secilebilir(durum))


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
        cikar = {a for a in adaylar if onceki.get(a) == PROFIL_KARAR_CIKAR}
    # Ayni icerikli gruplarda kalacak kolon: {"ayni": {grup id: kolon}}.
    gruplar = (p.get("profil_ek") or {}).get("ayni_gruplar") or []
    if isinstance(karar, dict) and isinstance(karar.get("ayni"), dict):
        uyeler = {g["id"]: set(g["uyeler"]) for g in gruplar}
        p["ayni_secim"] = {str(k): str(v) for k, v in karar["ayni"].items()
                           if str(v) in uyeler.get(str(k), set())}
    p["profil_teshis"]["ayni_icerik"] = _ayni_kopyalar(p)
    # Kalan kolon degisince karar adaylari degisebilir.
    adaylar = _karar_adaylari(p)
    p["profil_karar"] = {a: (PROFIL_KARAR_CIKAR if a in cikar else PROFIL_KARAR_TUT)
                         for a in adaylar}
    # COZUMLER: {"cozum": {kolon: kod}}; gelmeyen kolonda onceki secim ya
    # da oneri. Secilenler egitim satirlarindan ogrenilir.
    oneri = cozum_onerileri(durum)
    if isinstance(karar, dict) and isinstance(karar.get("cozum"), dict):
        sec = dict(p.get("cozum_secim") or {})
        for k, c in karar["cozum"].items():
            if c in ((oneri.get(str(k)) or {}).get("secenekler") or []):
                sec[str(k)] = str(c)
        p["cozum_secim"] = sec
    durum["profil"] = p
    _cozum_ogren(durum)
    # Profil degisti: SFA ve kararlari eski profile aitti, yeniden hesaplanir.
    eski = (durum.pop("sfa", None) or {}).get("ai_is")
    if eski:
        sfa_karar.ai_durdur(eski)
    # Karar kartli dalda metin ve kart blokta zaten duruyor (kart kilitlenir);
    # tekrar yazilmaz.
    if adaylar or gruplar or cozum_secilebilir(durum):
        return ""
    return profil_metni(durum)


# ===========================================================================
# 02.1 VERI PROFILI KARTI
# ===========================================================================
SONUC_GIRMEZ = "girmez"
SONUC_KARAR = "karar"
SONUC_BILGI = "bilgi"
NE_OLACAK = {SONUC_GIRMEZ: "Üretime girmez",
             SONUC_KARAR: "Kararınıza bırakılır",
             SONUC_BILGI: "Bilgi için gösterilir"}


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


def _sayi_metni(v):
    """Ekranda sayi: tam sayi binlik ayracli, ondalik virgullu."""
    f = float(v)
    if f == int(f) and abs(f) < 1e15:
        return _sayi(int(f))
    return ("%.4g" % f).replace(".", ",")


def _profil_kurallari(esik=None):
    """Her kontrolun sade kurali; esikler kullanicinin onayladigi degerler."""
    e = esik or _esik_varsayilan()
    kat = _sayi(e["kardinalite"])
    return {
        "cok_bos": "Kolonun boş hücre oranı %s üstünde." % _yuzde_ekli(e["cok_bos"]),
        "sabit": "Kolonda tek bir değer var. Bir değer ile boş hücrelerden oluşan kolon "
                 "iki değerli sayılır.",
        "kimlik_gibi": "Farklı değer sayısının satır sayısına oranı %s üstünde olan tam sayı "
                       "ya da metin kolon (müşteri numarası gibi). Ondalıklı tutarlar bu "
                       "kurala girmez." % _yuzde_ekli(e["kimlik"]),
        "yuksek_kardinalite": "Metin kolonda farklı değer sayısı %s üstünde."
                              % (kat + _ilgi_eki(kat)),
        "ayni_icerik": "Değerleri satır satır birebir aynı olan kolonlar. Her gruptan bir "
                       "kolon kalır: dil modeli adına ve açıklamasına bakıp önerir, siz "
                       "seçersiniz.",
        "baskin": "En sık görülen değer satırların en az %s kadarında geçiyor. Boş hücre de "
                  "değer sayılır." % _yuzde_metni(e["baskin"]),
        "donem": "Kolon bazı dönemlerde tamamen boş, ya da en az %s satırı olan bir dönemde "
                 "bütün satırlarda aynı değerde." % _sayi(e["donem_min_satir"]),
        "gizli_eksik": "-1, -99, -999, 9999 gibi bir değer dolu satırların %s fazlasında "
                       "geçiyor ve kolonun geri kalan değerlerinden kopuk. Sonraki "
                       "adımlarda boş gibi ele alınması önerilir." % _yuzde_ekli(e["gizli"]),
        "sifir": "Dolu satırlarda sıfırın payı %s ya da üstünde. Çoğu zaman işlem yok "
                 "anlamına gelir." % _yuzde_metni(e["sifir"]),
        "negatif": "Kolon kartında ölçüsü adet, gün ya da süre olan kolonda negatif değer var.",
        "sicrama": "Eksik oranı art arda iki dönem arasında %s puandan fazla değişiyor."
                   % _sayi_metni(round(e["sicrama"] * 100, 2)),
        "uc": "En büyük değer, değerlerin %%99'unun altında kaldığı sınırın %s katından "
              "büyük." % _sayi_metni(e["uc_kat"]),
        "tekrar": "Aynı kimlik ve dönemle birden fazla satır, ya da bütün kolonları aynı "
                  "satırlar.",
    }


# KARAR KARTI ACIKLAMALARI: her kontrolun tek cumlesi ("kisa") ve "i"
# balonu ("bilgi": nedir, neden onemli, ornek, kapsam, yakalanirsa).
# Esikli kontroller esik formunun metnini kullanir (onerilen degerin
# gerekcesi karar kartinda yazilmaz; esik zaten onaylandi).
_KONTROL_ESIK_ANAHTARI = {"cok_bos": "cok_bos", "kimlik_gibi": "kimlik",
                          "yuksek_kardinalite": "kardinalite", "baskin": "baskin",
                          "donem": "donem_min_satir", "gizli_eksik": "gizli", "sifir": "sifir",
                          "sicrama": "sicrama", "uc": "uc_kat"}
_KONTROL_ACIKLAMA_EK = {
    "sabit": {
        "kisa": "Bütün satırlarda aynı değeri alan kolon hiçbir şey ayırt etmez.",
        "bilgi": "**Nedir?** Kolonda yalnız tek bir değer olup olmadığına bakar. Boş hücre ayrı "
                 "bir değer sayılır: bir değer ve boşlardan oluşan kolon (1 ve boş gibi) iki "
                 "değerlidir, sabit sayılmaz.\n\n"
                 "**Neden önemli?** Her satırda aynı olan bir kolon satırları birbirinden "
                 "ayıramaz; modele hiçbir bilgi katmaz.\n\n"
                 "**Örnek:** bütün satırlarda «TL» yazan para birimi kolonu.\n\n"
                 "**Yakalanırsa:** kolon değişken üretimine girmez."},
    "ayni_icerik": {
        "kisa": "Değerleri satır satır birebir aynı olan kolonların ikisini birden kullanmak "
                "aynı bilgiyi iki kez saymaktır.",
        "bilgi": "**Nedir?** Bütün satırlarda değerleri birebir aynı olan kolonları gruplar.\n\n"
                 "**Neden önemli?** Aynı bilgi iki kolonda olunca model onu iki kez sayar; "
                 "ağırlıklar ve açıklamalar yanıltıcı olur.\n\n"
                 "**Örnek:** biri eski biri yeni adla gelen aynı tutar kolonu.\n\n"
                 "**Yakalanırsa:** her gruptan bir kolon kalır, diğerleri üretime girmez. Hangisinin "
                 "kalacağını dil modeli adlarına ve açıklamalarına bakıp önerir, siz seçersiniz."},
    "negatif": {
        "kisa": "Adet, gün, süre gibi negatif olamayacak bir ölçüde negatif değer veri hatasıdır.",
        "bilgi": "**Nedir?** Kolon kartında ölçüsü adet, sayı, gün, süre, yaş, ay ya da yıl olan "
                 "kolonlarda sıfırdan küçük değer arar.\n\n"
                 "**Neden önemli?** Böyle bir ölçü negatif olamaz; negatif değer çoğu zaman bir "
                 "kodlama ya da hesap hatasıdır.\n\n"
                 "**Örnek:** «son işlemden bu yana geçen gün» kolonunda -3.\n\n"
                 "**Kapsam:** yalnız 01.2.4.3'te kolon kartının Ölçü alanı dolu olan kolonlar. "
                 "Ölçü bilgisi yoksa kontrol yapılmaz.\n\n"
                 "**Yakalanırsa:** bilgi için gösterilir, kolon üretime girer."},
    "tekrar": {
        "kisa": "Aynı kayıt birden fazla satırda geçiyorsa o kayıt modelde fazla ağırlık alır.",
        "bilgi": "**Nedir?** Aynı kimlik ve dönemle birden fazla satır olup olmadığına, ayrıca "
                 "bütün kolonları birebir aynı satırlara bakar. Satır sayar, kolon değil.\n\n"
                 "**Neden önemli?** Tekrar eden kayıt modelde birden fazla sayılır; ayrıca aynı "
                 "kayıt hem eğitim hem test verisine düşerse sonuçlar olduğundan iyi görünür.\n\n"
                 "**Örnek:** aynı müşteri, aynı ay için iki satır.\n\n"
                 "**Kapsam:** kimlik kolonu seçilmediyse yalnız bütün kolonları aynı satırlara "
                 "bakılır.\n\n"
                 "**Yakalanırsa:** bilgi için gösterilir."},
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


# (anahtar, kontrolun adi, sonuc, kolon satirindaki kisa bulgu adi)
PROFIL_KONTROLLERI = (
    ("cok_bos", "Eksik Oranı Yüksek", SONUC_GIRMEZ, "Eksik oranı yüksek"),
    ("sabit", "Sabit ya da Tek Değerli", SONUC_GIRMEZ, "Sabit"),
    ("kimlik_gibi", "Kimlik Benzeri", SONUC_GIRMEZ, "Kimlik benzeri"),
    ("yuksek_kardinalite", "Kardinalitesi Aşırı Yüksek", SONUC_GIRMEZ, "Kardinalite yüksek"),
    ("ayni_icerik", "Aynı İçerikli Kolonlar", SONUC_GIRMEZ, "Aynı içerik"),
    ("baskin", "Neredeyse Sabit", SONUC_KARAR, "Neredeyse sabit"),
    ("donem", "Dönemde Boş ya da Sabit", SONUC_KARAR, "Dönemde boş ya da sabit"),
    ("gizli_eksik", "Gizli Eksik (Özel Kod)", SONUC_BILGI, "Gizli eksik"),
    ("sifir", "Sıfır Yoğunluğu", SONUC_BILGI, "Sıfır yoğun"),
    ("negatif", "Beklenmeyen Negatif", SONUC_BILGI, "Beklenmeyen negatif"),
    ("sicrama", "Dönemler Arası Eksik Sıçraması", SONUC_BILGI, "Eksik sıçraması"),
    ("uc", "Uç Değer Yoğunluğu", SONUC_BILGI, "Uç değer"),
    ("tekrar", "Tekrar Eden Satır", SONUC_BILGI, ""),
)
DONEM_LISTE_EN_COK = 6


def _donem_listesi(donemler):
    if len(donemler) <= DONEM_LISTE_EN_COK:
        return ", ".join(donemler)
    return "%s ve %s dönem daha" % (", ".join(donemler[:DONEM_LISTE_EN_COK]),
                                    _sayi(len(donemler) - DONEM_LISTE_EN_COK))


def _ek_bulgulari(p):
    """{anahtar: {kolon: bulgu metni}} ek kontrollerden. Ayni icerikli
    gruplarda kalmayan kolonlar diger kontrollerde gosterilmez."""
    ek = p.get("profil_ek") or {}
    kopya = set(_ayni_kopyalar(p))
    b = {a: {} for a in ("ayni_icerik", "baskin", "donem", "gizli_eksik", "sifir",
                         "negatif", "sicrama", "uc")}
    for g in ek.get("ayni_gruplar") or []:
        kalan = _ayni_kalan(p, g)
        for k in g["uyeler"]:
            if k != kalan:
                b["ayni_icerik"][k] = "%s ile birebir aynı; %s kalır" % (kalan, kalan)
    for x in ek.get("baskin") or []:
        b["baskin"][x["kolon"]] = "En sık değer %s, payı %s" % (x["deger"], _yuzde_metni(x["pay"]))
    for x in ek.get("donem") or []:
        parca = []
        if x.get("bos"):
            parca.append("Boş dönemler: %s" % _donem_listesi(x["bos"]))
        if x.get("sabit"):
            parca.append("Tek değerli dönemler: %s" % _donem_listesi(x["sabit"]))
        b["donem"][x["kolon"]] = ". ".join(parca)
    for x in ek.get("gizli_eksik") or []:
        b["gizli_eksik"][x["kolon"]] = "Kod %s, payı %s (%s satır)" % (
            x["deger"], _yuzde_metni(x["pay"]), _sayi(x["adet"]))
    for x in ek.get("sifir") or []:
        b["sifir"][x["kolon"]] = "Sıfırın payı %s" % _yuzde_metni(x["pay"])
    for x in ek.get("negatif") or []:
        b["negatif"][x["kolon"]] = "Ölçü: %s. Negatif satır %s, en küçük değer %s" % (
            x["olcu"], _sayi(x["adet"]), _sayi_metni(x["en_kucuk"]))
    for x in ek.get("sicrama") or []:
        b["sicrama"][x["kolon"]] = "Eksik oranı %s dönemi %s, %s dönemi %s" % (
            x["once"], _yuzde_metni(x["once_oran"]), x["sonra"], _yuzde_metni(x["sonra_oran"]))
    for x in ek.get("uc") or []:
        b["uc"][x["kolon"]] = "En büyük değer %s, %%99'luk değer %s" % (
            _sayi_metni(x["maks"]), _sayi_metni(x["p99"]))
    for a, kolonlar in b.items():
        if a != "ayni_icerik":
            for k in [k for k in kolonlar if k in kopya]:
                del kolonlar[k]
    return b


def _profil_ozeti(durum):
    """Kartin ve metnin ortak sayilari."""
    p = durum.get("profil") or {}
    t = p.get("profil_teshis") or {}
    ek = p.get("profil_ek") or {}
    temel = set(t.get("cok_bos") or []) | set(t.get("sabit") or []) \
        | set(t.get("kimlik_gibi") or []) | set(t.get("yuksek_kardinalite") or [])
    incelenen = set(map(str, t.get("temiz") or [])) | temel
    girmez = set(kusurlu_kolonlar(durum))
    karar = p.get("profil_karar") if isinstance(p.get("profil_karar"), dict) else {}
    karar_ad = profil_karar_kolonlari(durum)
    bekleyen = {k for k in karar_ad if k not in karar}
    bilgi = set()
    for a in ("gizli_eksik", "sifir", "negatif", "sicrama", "uc"):
        bilgi |= {x["kolon"] for x in (ek.get(a) or [])}
    bilgi |= {k for k in karar_ad if karar.get(k) == PROFIL_KARAR_TUT}
    bilgi -= girmez | bekleyen
    temiz = incelenen - girmez - bilgi - bekleyen
    return {"incelenen": incelenen, "girmez": girmez, "bilgi": bilgi,
            "bekleyen": bekleyen, "temiz": temiz, "karar": karar}


def profil_metni(durum, karar=False):
    """02.1 bloğunun metni: ne yapildi ve sonuc, tek bakista."""
    oz = _profil_ozeti(durum)
    metin = ("Modelleme tablosundaki %s kolon, tablonun tamamı üzerinden %s kontrolle "
             "incelendi." % (_sayi(len(oz["incelenen"])), _sayi(len(PROFIL_KONTROLLERI))))
    parca = []
    if oz["girmez"]:
        parca.append("%s kolon değişken üretimine girmez; %s adımında veri setinden "
                     "çıkarılır." % (_sayi(len(oz["girmez"])), akis_atif.adim("baz")))
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
        parca.append("%s kolon için kararınız gerekiyor: Neredeyse Sabit ve Dönemde Boş "
                     "ya da Sabit kontrollerinde her kolonu tutun ya da çıkarın."
                     % _sayi(len(oz["bekleyen"])))
    gruplar = ((durum.get("profil") or {}).get("profil_ek") or {}).get("ayni_gruplar") or []
    if karar and gruplar:
        parca.append("Değerleri birebir aynı %s kolon grubunda hangi kolonun kalacağını "
                     "seçin; dil modelinin önerisi seçili gelir." % _sayi(len(gruplar)))
    if oz["bilgi"]:
        parca.append("%s kolonda bilgi notu var; bu kolonlar değişken üretimine girer."
                     % _sayi(len(oz["bilgi"])))
    if not parca:
        parca.append("Hiçbir kolonda sorun bulunmadı; bütün kolonlar değişken üretimine "
                     "girer.")
    notu = esik_degisiklik_notu(durum)
    if notu:
        parca.append(notu)
    tk = ((durum.get("profil") or {}).get("profil_ek") or {}).get("tekrar") or {}
    tekrar = int(tk.get("toplam") or 0)
    if tekrar:
        parca.append("Tabloda %s tekrar eden satır var; Tekrar Eden Satır kontrolünde "
                     "ayrıntısı görünür." % _sayi(tekrar))
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
    donemler = ek.get("donemler")
    kontroller = []
    for a, ad, sonuc, _kisa in PROFIL_KONTROLLERI:
        kisa, bilgi = kontrol_aciklamasi(a)
        k = {"anahtar": a, "ad": ad, "kural": kurallar[a], "sonuc": sonuc,
             "kisa": kisa, "bilgi": bilgi,
             "ne_olacak": NE_OLACAK[sonuc], "uygulandi": True, "sebep": "",
             "birim": "kolon", "kolonlar": []}
        if a == "yuksek_kardinalite" and not turler.get("kategorik"):
            k["uygulandi"], k["sebep"] = False, "Kategorik kolon yok"
        elif a in ("donem", "sicrama") and donemler is None:
            k["uygulandi"], k["sebep"] = False, "Dönem kolonu seçilmedi"
        elif a in ("donem", "sicrama") and len(donemler or []) < 2:
            k["uygulandi"], k["sebep"] = False, "Tabloda tek dönem var"
        elif a == "negatif" and not ek.get("olcu_var"):
            k["uygulandi"], k["sebep"] = False, "Kolon kartlarında ölçü bilgisi yok"
        if a == "ayni_icerik" and ek.get("ayni_gruplar"):
            k["ne_olacak"] = "Biri kalır, diğerleri üretime girmez"
            k["gruplar"] = [{"id": g["id"], "oneri": g["oneri"], "gerekce": g.get("gerekce", ""),
                             "kaynak": g.get("kaynak", ""), "secim": _ayni_kalan(p, g),
                             "uyeler": [{"ad": u, "aciklama": aciklama.get(u, "")}
                                        for u in g["uyeler"]]}
                            for g in ek["ayni_gruplar"]]
        if a == "tekrar":
            tk = ek.get("tekrar") or {}
            k["birim"] = "satır"
            if tk.get("kimlik"):
                k["kolonlar"].append({"ad": "Aynı %s" % " ve ".join(tk.get("anahtar") or []),
                                      "aciklama": "", "bulgu": "%s fazla satır" % _sayi(tk["kimlik"])})
            if tk.get("tam"):
                k["kolonlar"].append({"ad": "Bütün kolonları aynı satır", "aciklama": "",
                                      "bulgu": "%s fazla satır" % _sayi(tk["tam"])})
            k["sayi"] = int(tk.get("toplam") or 0)
            if tk.get("kimlik") is None:
                k["kural"] += " Kimlik kolonu seçilmediği için yalnız bütün kolonları aynı satırlara bakıldı."
            kontroller.append(k)
            continue
        for kol, metin in (bulgu.get(a) or {}).items():
            satir = {"ad": kol, "aciklama": aciklama.get(kol, ""), "bulgu": metin}
            if sonuc == SONUC_KARAR:
                satir["karar"] = karar_deger.get(kol, PROFIL_KARAR_TUT)
            if a in COZUM_KONTROLLERI and (cozum_oneri.get(kol) or {}).get("kontrol") == a:
                satir["cozum"] = _cozum_satiri(kol, cozum_oneri[kol], cozum_sec, cozum_bilgi)
            elif a in COZUM_KONTROLLERI and kol in cozum_oneri \
                    and len(cozum_oneri[kol].get("secenekler") or []) < 2:
                satir["cozum"] = _cozum_satiri(kol, cozum_oneri[kol], cozum_sec, cozum_bilgi)
            elif a in COZUM_KONTROLLERI and kol in cozum_oneri:
                satir["cozum_baska"] = {x[0]: x[1] for x in PROFIL_KONTROLLERI}.get(
                    cozum_oneri[kol]["kontrol"], "")
            k["kolonlar"].append(satir)
        if any(len((s.get("cozum") or {}).get("secenekler") or []) > 1 for s in k["kolonlar"]):
            k["ne_olacak"] = "Çözüm seçilir; ham kolon üretime girmez"
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
        "kontroller": kontroller,
        "hedef": ek.get("hedef"),
        "haric": {"hedef": m.get("target") or "", "kimlik": m.get("id") or "",
                  "donem": m.get("donem") or "",
                  "surec_disi": len(set(durum.get("haric_kolonlar") or []))},
        "kayit": kayit,
        "dusme_atif": akis_atif.adim("baz"),
    }


def _cozum_satiri(kol, oneri, secim, bilgi):
    """Kart satirinin cozum alani: secenekler (ad, aciklama), oneri, secim,
    gerekce; uygulandiysa uretilen kolonlar ve ozet."""
    from fe_agent import kolon_cozum as kc
    c = {"secenekler": [{"kod": x, "ad": kc.COZUM_ADI.get(x, x),
                         "aciklama": kc.COZUM_ACIKLAMA.get(x, "")}
                        for x in oneri.get("secenekler") or []],
         "oneri": oneri.get("oneri"), "secim": secim.get(kol, oneri.get("oneri")),
         "gerekce": oneri.get("gerekce", "")}
    b = bilgi.get(kol)
    if isinstance(b, dict) and b.get("cozum") == c["secim"]:
        c["kolonlar"] = list(b.get("kolonlar") or [])
        c["ozet"] = b.get("ozet") or ""
        c["ozet_kisa"] = _cozum_kisa_ozet(b)
    return c


def _cozum_kisa_ozet(b):
    """Tek satirlik ozet; ayrinti (grup uyeleri, sozcukler) i balonunda."""
    bilgi = b.get("bilgi") or {}
    c = b.get("cozum")
    if c == "dolu_bayrak":
        return "Dolu satır 1, boş satır 0."
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
    if esik_kilit:
        for n in esik_satirlari:
            k = dict(yeni[n])
            k["ekran"] = {"secim_alani": esik_formu(durum, kilitli=True)}
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
    test_tanim = bolme_ayarlari(durum).get("test_tanim")
    return {set_basligi(ad, test_tanim): s[ad] for ad in ("val", "test", "oot")
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
    yazildi, yedek = _yaz("%s_SFA" % durum["veri_seti"], tablo, "/sfa_tablosu.parquet")
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
             "  Winsor (%%5) : %s\n"
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

    yazildi, yedek = _yaz("%s_PSI" % durum["veri_seti"], tablo, "/stabilite.parquet")
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
            "aynı içerik %s · profilde çıkarılan %s · kararsız %s · süreç dışı %s\n"
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
               _sayi(len(t.get("ayni_icerik") or [])), _sayi(len(_profil_cikarilan(p))),
               _sayi(len(st.get("kayan") or [])), _sayi(len(tanimsiz)),
               _sayi(ko["girmeyen"]), _sayi(ko["aralik"]), _sayi(ko["donusum"]),
               _sayi(ko["isaret"]), durum["veri_seti"]))


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

    # Hedef veri seti akista tanimli degilse adim COKMESIN: hesap korunur,
    # tablo yedek dosyaya yazilir ve kullaniciya acik bir uyari verilir.
    baz_ds = "%s_BAZ" % durum["veri_seti"]
    # Veri seti Flow'da yoksa webapp kurar (kullanici Flow'a bir sey eklemez;
    # kaynak tablonun baglantisinda Parquet). Kurulamazsa yedek dosyaya
    # yazilir ve uyari verilir.
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
