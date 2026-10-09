# -*- coding: utf-8 -*-
"""fe_agent/akis_faz04.py - Faz 04 - Degisken Degerlendirme: sizinti kontrolu ve aday set.

Analitik baz set (ham + uretilen, SFA kararlariyla) uzerinde calisir.
Adim anahtari "kalite" eski calismalar icin korunuyor; adim artik Sizinti
Kontrolu (eksik, sabit ve kararlilik Faz 03'te denetleniyor).
"""

import numpy as np
import pandas as pd
from fe_agent import secim as secim_mod

from fe_agent.akis_durum import (
    _dataset_okunur_mu, _df_oku, _liste, _nerede, _ond, _sayi, _yaz, maskeler,
)


# ===========================================================================
# KAYNAK SECIMI
# ===========================================================================
# Analitik baz set ham ve uretilen degiskenleri birlikte, SFA kararlariyla
# tasir; bu faz onu okur. Baz set yazilamadiysa _ENRICHED, o da yoksa
# modelleme veri seti.
def _kaynak(durum):
    """Doner: (dataset_adi | None, baz_set_mi)"""
    baz = (durum.get("baz") or {}).get("dataset")
    if baz and _dataset_okunur_mu(baz):
        return baz, True
    for ad in ("%s_ENRICHED" % durum.get("veri_seti"), durum.get("veri_seti")):
        if ad and _dataset_okunur_mu(ad):
            return ad, False
    return None, False


_KAYNAK_YOK = ("Bu adımı çalıştıramadım: ne analitik baz set ne de %s veri "
               "seti okunabiliyor. Analitik Baz Set adımına dönüp yeniden "
               "çalıştırabilir ya da bu adımı geçebilirsiniz.")

_BAZ_YOK = ("NOT: Analitik baz set okunamadı; hesaplamayı %s veri seti "
            "üzerinde yaptım (SFA kararları uygulanmamış olabilir).")


def _baz_ayrimi(durum, df):
    """(ham kaynakli kolonlar, uretilen kaynakli kolonlar, {kolon: kaynak}).
    Baz set kaydi yoksa (eski calisma) uretilen adlari dogrudan aranir."""
    bz = durum.get("baz") or {}
    m = durum.get("meta") or {}
    meta = {m.get("target"), m.get("id"), m.get("donem")}
    kaynak = dict(bz.get("kaynak") or {})
    if "uretilen_kolonlar" in bz:
        ham = [c for c in (bz.get("kolonlar") or []) if c in df.columns]
        ur = [c for c in (bz.get("uretilen_kolonlar") or []) if c in df.columns]
        return ham, ur, kaynak
    uretilen = set(durum.get("uretilen") or [])
    ur = [c for c in df.columns if c in uretilen]
    ham = [c for c in (bz.get("kolonlar") or [c for c in df.columns if c not in meta])
           if c in df.columns and c not in uretilen]
    return ham, ur, kaynak


# Hedefle bu esigin ustunde (mutlak) korelasyonu olan degisken sizinti
# supheli sayilir.
SIZINTI_ESIK = 0.95


def kalite_plan(durum):
    bz = durum.get("baz") or {}
    ham = len(bz.get("kolonlar") or [])
    ur = len(bz.get("uretilen_kolonlar") or [])
    return ("Analitik baz setteki %s değişkende (ham %s · üretilen %s) sızıntı "
            "kontrolü yapacağım: Train (MS) satırlarında hedefle korelasyonu "
            "mutlak değerce %s üstünde olan değişken sızıntı şüphelisi sayılır; "
            "aday sete ve modele alınmaz.\n\n"
            "Eksik değer, sabitlik ve kararlılık Veri Anlama ve Hazırlama "
            "fazında bütün değişkenler için zaten denetlendi. Çalıştıralım mı?"
            % (_sayi(ham + ur), _sayi(ham), _sayi(ur), _ond(SIZINTI_ESIK, 2)))


def kalite_uygula(durum):
    kaynak, baz_mi = _kaynak(durum)
    bos = {"eksik": [], "sabit": [], "kararsiz": [], "sfa": [], "sizinti": [],
           "gecti": [], "aday": [], "ham_sizinti": []}
    if kaynak is None:
        durum["kalite"] = bos
        return _KAYNAK_YOK % durum.get("veri_seti")
    not_metni = "" if baz_mi else ("\n\n" + _BAZ_YOK % kaynak)

    df = _df_oku(kaynak)
    y = pd.to_numeric(df[durum["meta"]["target"]], errors="coerce")
    tr, _ = maskeler(durum, df)
    ham, ur, kaynak_ad = _baz_ayrimi(durum, df)

    sizinti = []
    for c in ham + ur:
        if not pd.api.types.is_numeric_dtype(df[c]):
            continue
        s = pd.to_numeric(df[c], errors="coerce").replace([np.inf, -np.inf], np.nan)
        kor = s[tr].corr(y[tr])
        if kor is not None and not pd.isna(kor) and abs(kor) > SIZINTI_ESIK:
            sizinti.append(c)
    sz = set(sizinti)

    # Uretilen degiskenlerin hikayesi KAYNAK ADIYLA (panel ve katalog
    # uretilen adlarla calisir): Faz 03'te dusenler sebebiyle, sizinti
    # supheliler ve gecenler. Aday set baz setteki adlarla kurulur.
    dusen = (durum.get("baz") or {}).get("uretilen_dusen") or {}
    aday = [c for c in ur if c not in sz]
    gecti = sorted({kaynak_ad.get(c, c) for c in aday})
    sizinti_kaynak = sorted({kaynak_ad.get(c, c) for c in ur if c in sz} - set(gecti))
    durum["kalite"] = {
        "eksik": sorted(a for a, n in dusen.items() if n == "eksik"),
        "sabit": sorted(a for a, n in dusen.items() if n == "sabit"),
        "kararsiz": sorted(a for a, n in dusen.items() if n == "kararsiz"),
        "sfa": sorted(a for a, n in dusen.items() if n in ("sfa", "diger")),
        "sizinti": sizinti_kaynak, "gecti": gecti, "aday": aday,
        "ham_sizinti": [c for c in ham if c in sz]}

    return ("Sızıntı kontrolü tamamlandı (Train (MS), |r| > %s).\n"
            "  Ham Değişken : %s · sızıntı şüphelisi %s\n"
            "  Üretilen Değişken : %s · sızıntı şüphelisi %s\n"
            "  Aday Sete Girecek Üretilen : %s\n"
            "Sızıntı şüphelileri aday sete ve modele alınmaz.%s"
            % (_ond(SIZINTI_ESIK, 2), _sayi(len(ham)), _sayi_ad_(sorted(c for c in ham if c in sz)),
               _sayi(len(ur)), _sayi_ad_(sorted(c for c in ur if c in sz)),
               _sayi(len(aday)), not_metni))


def _sayi_ad_(liste, en_fazla=3):
    if not liste:
        return "0"
    ek = " +%s" % _sayi(len(liste) - en_fazla) if len(liste) > en_fazla else ""
    return "%s · %s%s" % (_sayi(len(liste)), ", ".join(liste[:en_fazla]), ek)

def _adaylar(durum):
    k = durum.get("kalite") or {}
    return k.get("aday") if "aday" in k else (k.get("gecti") or [])


def secim_plan(durum):
    aday = len(_adaylar(durum) or [])
    b = durum.get("bolme") or {}
    bolme_ad = ("zamansal: %s dönemi hariç" % b.get("oot_deger")) \
        if b.get("tur") == "zamansal" else "rastgele bölmenin eğitim payı"
    return ("Sızıntı kontrolünü geçen %s üretilen değişkeni seçim hattından geçireceğim:\n\n"
            "  1. Yarı-sabit eleme: tek değerin payı %%%s üstündeyse düşer\n"
            "  2. Fazlalık eleme: |r| > %s olan çiftte IV'si düşük düşer\n"
            "  3. Karşılıklı bilgi: skor hesaplanır, eleme yapılmaz\n"
            "  4. Model önemi: toplam önemin %%%s'inden azı düşer\n\n"
            "HESAPLAMA KAPSAMI\n"
            "Dört aşamanın tamamı YALNIZCA eğitim satırlarında hesaplanır "
            "(%s). Test satırları seçim kararına karışmaz; aksi halde "
            "elenen/tutulan değişken listesi test verisinden bilgi taşır ve "
            "model performansı olduğundan iyi görünür.\n\n"
            "Her değişkenin hangi aşamada elendiği tabloda kalacak.\n\n"
            "Çalıştıralım mı?"
            % (_sayi(aday), _ond(secim_mod.QUASI_ESIK * 100),
               _ond(secim_mod.KORELASYON_ESIK, 2),
               _ond(secim_mod.ONEM_ORAN * 100, 2), bolme_ad))

def secim_uygula(durum):
    kaynak, baz_mi = _kaynak(durum)
    if kaynak is None:
        durum["secim"] = {"secilen": 0, "secilen_liste": []}
        return _KAYNAK_YOK % durum.get("veri_seti")

    not_metni = "" if baz_mi else ("\n\n" + _BAZ_YOK % kaynak)

    df = _df_oku(kaynak)
    adaylar = [c for c in (_adaylar(durum) or []) if c in df.columns]
    if not adaylar:
        durum["secim"] = {"secilen": 0, "secilen_liste": []}
        return "Seçim hattına girecek aday değişken kalmadı.%s" % not_metni

    binary = (durum.get("profil") or {}).get("hedef_tip") == "binary"
    # SIZINTI SINIRI: MI ve model onem skoru test/OOT satirlarini gormemeli.
    # train_maske gecilmezse secim modulu tum veriye duser.
    tr, _ = maskeler(durum, df)
    # IV'ler SFA donusumunden onceki adla; baz setteki ada tasinir.
    iv = (durum.get("sfa") or {}).get("iv_skorlari") or {}
    kaynak_ad = (durum.get("baz") or {}).get("kaynak") or {}
    oncelik = {c: iv.get(kaynak_ad.get(c, c)) for c in adaylar
               if iv.get(kaynak_ad.get(c, c)) is not None}
    tablo, oz = secim_mod.calistir(
        df, durum["meta"]["target"], adaylar,
        oncelik=oncelik or None, binary=binary, train_maske=tr)

    yazildi, yedek = _yaz("%s_SECIM" % durum["veri_seti"], tablo, "/secim_tablosu.parquet")
    durum["secim"] = oz
    durum["secim_tablo"] = tablo.to_dict("records")

    en_iyi = ["  %-34s %s" % (c[:34], _ond(v, 5)) for c, v in (oz["en_iyi"] or [])[:10]]

    return ("Aday değişken seti oluşturuldu: %s adaydan %s değişken seçildi.\n\n"
            "HESAPLAMA KAPSAMI\n"
            "  Skorlar ve elemeler %s üzerinde hesaplandı.\n\n"
            "ELEME KIRILIMI\n"
            "  Yarı-sabit : %s\n  Fazlalık   : %s   (%s kolon incelendi)\n"
            "  Düşük önem : %s\n\n"
            "EN YÜKSEK ÖNEM SKORLU 10  (%s)\n%s\n\nTam tablo %s.%s"
            % (_sayi(oz["aday"]), _sayi(oz["secilen"]),
               oz.get("hesap_kapsami") or "eğitim satırları",
               _sayi(oz["yari_sabit"]), _sayi(oz["korelasyon"]),
               _sayi(oz["korelasyon_bakilan"]), _sayi(oz["dusuk_onem"]),
               oz["onem_yontemi"], "\n".join(en_iyi) or "  (yok)",
               _nerede(yazildi, yedek), not_metni))
