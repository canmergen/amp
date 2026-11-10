# -*- coding: utf-8 -*-
"""fe_agent/akis_faz02.py - Veri Profili (Faz 02'nin ilk adimi) ve Faz 03 -
Veri Anlama ve Hazirlama: SFA, stabilite, baz set.

SIRA: Veri Profili ham kolonlarla calisir (kusurlu kolonlardan degisken
uretilmesin diye uretimden once). SFA, stabilite ve baz set ise uretimden
SONRA, eldeki butun degiskenlerle (ham + uretilen; _ENRICHED) calisir.
"""


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


def _eksik_ozeti(tablo, satir):
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
        elif oran <= sfa_mod.NULL_ESIK:
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


def uretilenler(durum):
    return [str(x) for x in (durum.get("uretilen") or []) if x]


def zengin_adi(durum):
    return "%s_ENRICHED" % durum.get("veri_seti")


def analiz_df(durum):
    """Faz 03'un tablosu: degisken uretildiyse _ENRICHED (ham + uretilen),
    uretilmediyse modelleme tablosu. Uretilen kolondaki sonsuz deger (ornek:
    sifira bolme) bos sayilir; profil onu eksik deger olarak gorur."""
    uretilen = uretilenler(durum)
    zengin = zengin_adi(durum)
    if not uretilen or not _dataset_okunur_mu(zengin):
        return modelleme_df(durum)
    df = _df_oku(zengin).copy(deep=False)
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


def profil_hesapla(durum):
    """Veri profilini tablonun TAMAMINDAN cikarir: dort temel kontrol
    (sfa.profil_cikar) ve ek kontroller (profil_ek). Sonuc durum["profil"]."""
    from fe_agent import profil_ek
    df = modelleme_df(durum)
    m = durum["meta"]
    haric = set(durum.get("haric_kolonlar") or []) | {m.get("target"), m.get("id"), m.get("donem")}

    tablo, teshis = sfa_mod.profil_cikar(df, haric=haric)
    yazildi, yedek = _yaz("%s_PROFIL" % durum["veri_seti"], tablo, "/veri_profili.parquet")

    p = durum.get("profil") or {}
    temel = set(teshis.get("cok_bos") or []) | set(teshis.get("sabit") or []) \
        | set(teshis.get("kimlik_gibi") or []) | set(teshis.get("yuksek_kardinalite") or [])
    adaylar = [str(k) for k in df.columns if k not in haric and k not in temel]
    ek = profil_ek.ek_kontroller(df, adaylar, donem=m.get("donem"), kimlik=m.get("id"),
                                 hedef=m.get("target"), olculer=_kart_olculeri(durum))
    # Sabit kolonun tek degeri (kartta bulgu olarak).
    ek["sabit_deger"] = {}
    for k in teshis.get("sabit") or []:
        dolu = df[k].dropna()
        ek["sabit_deger"][k] = profil_ek.deger_metni(dolu.iloc[0]) if len(dolu) else "boş"
    teshis["ayni_icerik"] = sorted({k for g in ek["ayni_icerik"] for k in g["kopyalar"]})
    p["profil_teshis"] = teshis
    p["profil_ek"] = ek
    p["profil_dataset"] = yazildi
    # Onceki kararlar yalniz hala karar isteyen kolonlar icin gecerli.
    eski_karar = p.get("profil_karar") if isinstance(p.get("profil_karar"), dict) else {}
    p["profil_karar"] = {k: v for k, v in eski_karar.items()
                         if k in set(_karar_adaylari(teshis, ek))}

    # Feature tablosunun kolon ozeti: veri seti secilirken cikarilmisti,
    # burada tekil sayisi ve kesin null orani ile tamamlaniyor. Ozet hic
    # yoksa (eski oturum) su an okunan tablodan uretiliyor.
    if not p.get("kolon_ozet"):
        p["kolon_ozet"] = kolon_ozeti_cikar(df)
    p["kolon_ozet"] = kolon_ozeti_tamamla(p, tablo, df)

    # EKSIK DEGER sekmesi: yalnizca ilk 20 satir + dagilim ozeti oturuma
    # yazilir; tam tablo yukarida dataset'e / yedege yazildi.
    ilk20, null_ozet, ek_alan = _eksik_ozeti(tablo, p.get("satir") or len(df))
    p["eksik_ilk20"] = ilk20
    p["null_ozet"] = null_ozet
    p.update(ek_alan)
    # Kartin satir sayisi ve kayit yeri (02.1 Veri Profili karti).
    p["profil_satir"] = int(len(df))
    p["profil_kayit"] = _kayit_metni(yazildi, yedek)
    durum["profil"] = p
    return p


def _karar_adaylari(teshis, ek):
    """Karar isteyen kolonlar (sira korunur): neredeyse sabit, donemde bos
    ya da sabit."""
    ad = [x["kolon"] for x in (ek.get("baskin") or [])]
    ad += [x["kolon"] for x in (ek.get("donem") or [])]
    return list(dict.fromkeys(ad))


def profil_karar_kolonlari(durum):
    p = durum.get("profil") or {}
    return _karar_adaylari(p.get("profil_teshis") or {}, p.get("profil_ek") or {})


def _profil_karar_bekliyor(durum):
    p = durum.get("profil") or {}
    karar = p.get("profil_karar") if isinstance(p.get("profil_karar"), dict) else {}
    return any(k not in karar for k in profil_karar_kolonlari(durum))


def veri_profili_plan(durum):
    """Profil tablonun tamamindan cikarilir. Karar isteyen kolon yoksa ONAY
    SORULMAZ, ilk durak Kural Tabanli Degisken Uretimi'nin planidir. Varsa
    kart her kolon icin Tut ya da Çıkar ister.

    Otomatik dalda metin yalnizca "Geri Dön" ile bu adima donulunce
    gorunur."""
    profil_hesapla(durum)
    durum["_profil_hazir"] = True
    if profil_karar_kolonlari(durum):
        durum["_secim_alani"] = profil_karti(durum, karar=True)
        return profil_metni(durum, karar=True)
    durum["_plan_otomatik"] = True
    return ("Veri profili yeniden çıkarıldı. Onaylarsanız değişken üretimi ve SFA bu "
            "profile göre yeniden yapılır, SFA kararları sıfırlanır.")


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
    p["profil_karar"] = {a: (PROFIL_KARAR_CIKAR if a in cikar else PROFIL_KARAR_TUT)
                         for a in adaylar}
    durum["profil"] = p
    # Profil degisti: SFA ve kararlari eski profile aitti, yeniden hesaplanir.
    eski = (durum.pop("sfa", None) or {}).get("ai_is")
    if eski:
        sfa_karar.ai_durdur(eski)
    # Karar kartli dalda metin ve kart blokta zaten duruyor (kart kilitlenir);
    # tekrar yazilmaz.
    if adaylar:
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


def _profil_kurallari():
    """Her kontrolun sade kurali; esikler kodun kullandigi degerlerden."""
    from fe_agent import profil_ek as pe
    return {
        "cok_bos": "Boş hücre oranı %s üstünde." % _yuzde_ekli(sfa_mod.NULL_ESIK),
        "sabit": "Kolonda tek bir değer var. Bir değer ile boş hücrelerden oluşan kolon "
                 "iki değerli sayılır.",
        "kimlik_gibi": "Neredeyse her satırda farklı değer alan tam sayı ya da metin kolon "
                       "(müşteri numarası gibi). Ondalıklı tutarlar bu kurala girmez.",
        "yuksek_kardinalite": "Metin kolonda farklı değer sayısı %s üstünde."
                              % (_sayi(sfa_mod.KATEGORIK_MAX) + _ilgi_eki(_sayi(sfa_mod.KATEGORIK_MAX))),
        "ayni_icerik": "Değerleri satır satır birebir aynı olan kolonlar. Gruptan tablodaki "
                       "ilk kolon kalır.",
        "baskin": "En sık görülen değerin payı %s ya da üstünde. Boş hücre de değer sayılır."
                  % _yuzde_metni(pe.BASKIN_ESIK),
        "donem": "Kolon bazı dönemlerde tamamen boş, ya da en az %s satırı olan bir dönemde "
                 "tek değerli." % _sayi(pe.DONEM_SABIT_MIN_SATIR),
        "gizli_eksik": "-1, -99, -999, 9999 gibi bir değerin dolu satırlardaki payı %s "
                       "üstünde ve değer kolonun geri kalanından kopuk. SFA'da eksik gibi "
                       "ele alınması önerilir." % _yuzde_ekli(pe.GIZLI_EKSIK_ESIK),
        "sifir": "Dolu satırlarda sıfırın payı %s ya da üstünde. Çoğu zaman işlem yok "
                 "anlamına gelir." % _yuzde_metni(pe.SIFIR_ESIK),
        "negatif": "Kolon kartında ölçüsü adet, gün ya da süre olan kolonda negatif değer var.",
        "sicrama": "Eksik oranı art arda iki dönem arasında %s puandan fazla değişiyor."
                   % _sayi(int(round(pe.DONEM_SICRAMA_ESIK * 100))),
        "uc": "En büyük değer, %%99'luk değerin %s katından büyük." % _sayi(pe.UC_DEGER_KAT),
        "tekrar": "Aynı kimlik ve dönemle birden fazla satır, ya da bütün kolonları aynı "
                  "satırlar.",
    }


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


def _ek_bulgulari(ek):
    """{anahtar: {kolon: bulgu metni}} ek kontrollerden."""
    b = {a: {} for a in ("ayni_icerik", "baskin", "donem", "gizli_eksik", "sifir",
                         "negatif", "sicrama", "uc")}
    for g in ek.get("ayni_icerik") or []:
        for k in g["kopyalar"]:
            b["ayni_icerik"][k] = "%s ile birebir aynı; %s kalır" % (g["kalan"], g["kalan"])
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
    if oz["bekleyen"]:
        parca.append("%s kolon için kararınız gerekiyor: Neredeyse Sabit ve Dönemde Boş "
                     "ya da Sabit kontrollerinde her kolonu tutun ya da çıkarın."
                     % _sayi(len(oz["bekleyen"])))
    if oz["bilgi"]:
        parca.append("%s kolonda bilgi notu var; bu kolonlar değişken üretimine girer."
                     % _sayi(len(oz["bilgi"])))
    if not parca:
        parca.append("Hiçbir kolonda sorun bulunmadı; bütün kolonlar değişken üretimine "
                     "girer.")
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

    bulgu = _ek_bulgulari(ek)
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

    kurallar = _profil_kurallari()
    karar_deger = oz["karar"]
    donemler = ek.get("donemler")
    kontroller = []
    for a, ad, sonuc, _kisa in PROFIL_KONTROLLERI:
        k = {"anahtar": a, "ad": ad, "kural": kurallar[a], "sonuc": sonuc,
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
            k["kolonlar"].append(satir)
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
        "karar_bekliyor": bool(karar and profil_karar_kolonlari(durum)),
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
        "eksik_esik": {"az": NULL_AZ, "asiri": sfa_mod.NULL_ESIK},
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


def profil_gecmisini_tazele(durum, gecmis):
    """Yenilemede 02.1 blogu guncel kart ve metinle cizilir (eski calismada
    metin tablosu yerine de). Kart, adimin transkriptteki metinli ya da
    ekranli ILK kaydina yazilir; adimin diger kayitlari (karar kartli dalda
    bos tamamlama satiri) kartsiz ve metinsiz kalir, kart iki kez cizilmez.
    Adim gecilmemisse (Geri Dön ile onay bekliyor) dokunulmaz.
    Transkript degismez: doner yeni liste."""
    from fe_agent.akis_kayit import adim_sirasi
    sira = adim_sirasi(durum.get("mod"))
    if "veri_profili" not in sira or sira.index("veri_profili") >= int(durum.get("i") or 0):
        return gecmis
    satirlar = [i for i, k in enumerate(gecmis or [])
                if isinstance(k, dict) and k.get("rol") == "bot" and k.get("adim") == "veri_profili"]
    if not satirlar:
        return gecmis
    kart = profil_karti(durum)
    if not kart:
        return gecmis
    hedef = next((i for i in satirlar
                  if str(gecmis[i].get("metin") or "").strip() or gecmis[i].get("ekran")),
                 satirlar[-1])
    yeni = list(gecmis)
    for i in satirlar:
        k = dict(yeni[i])
        if i == hedef:
            k["metin"] = profil_metni(durum)
            k["ekran"] = {"secim_alani": kart}
            k.pop("ekran_atlandi", None)
        else:
            k["metin"] = ""
            k.pop("ekran", None)
        yeni[i] = k
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
