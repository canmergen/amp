# -*- coding: utf-8 -*-
"""fe_agent/akis_faz04.py - Faz 04 - Degisken Degerlendirme: kalite kontrolu ve aday set.

akis.py bolundu; bu dosya o bolumun aynisidir.
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
# Faz 03 (kural / kesif) plan bos gelirse _ENRICHED HIC olusmaz. Eski kod
# dogrudan onu okuyup yakalanmamis istisna firlatiyordu; kullanici sohbet
# balonunda backend traceback'i goruyordu. Artik kaynak once kontrol edilir.
def _kaynak(durum):
    """Doner: (dataset_adi | None, zenginlestirilmis_mi)"""
    zengin = "%s_ENRICHED" % durum.get("veri_seti")
    if _dataset_okunur_mu(zengin):
        return zengin, True
    baz = (durum.get("baz") or {}).get("dataset") or durum.get("veri_seti")
    if baz and _dataset_okunur_mu(baz):
        return baz, False
    return None, False


_KAYNAK_YOK = ("Bu adımı çalıştıramadım: ne %s_ENRICHED ne de baz veri seti "
               "okunabiliyor.\n\nDeğişken üretimi adımlarında (kural tabanlı "
               "üretim / AI keşfi) hiçbir değişken üretilmediyse "
               "zenginleştirilmiş veri seti oluşmaz. Önceki adıma dönüp "
               "üretim yapabilir ya da bu adımı geçebilirsiniz.")

_ZENGIN_YOK = ("NOT: %s_ENRICHED veri seti bulunamadı (değişken üretimi "
               "yapılmamış olabilir); hesaplamayı %s veri seti üzerinde "
               "yaptım.")


def kalite_plan(durum):
    return ("Üretilen %s değişkeni teknik kalite kontrolünden geçireceğim:\n\n"
            "  • eksik değer ve sonsuz sayı\n"
            "  • sabit ya da neredeyse sabit dağılım\n"
            "  • hedefle aşırı korelasyon: sızıntı riski\n\n"
            "Geçemeyenler aday sete alınmaz. Çalıştıralım mı?"
            % _sayi(len(durum.get("uretilen", []))))

def kalite_uygula(durum):
    kaynak, zengin = _kaynak(durum)
    if kaynak is None:
        durum["kalite"] = {"eksik": [], "sabit": [], "sizinti": [], "gecti": []}
        return _KAYNAK_YOK % durum.get("veri_seti")

    not_metni = "" if zengin else \
        ("\n\n" + _ZENGIN_YOK % (durum.get("veri_seti"), kaynak))

    df = _df_oku(kaynak)
    y = pd.to_numeric(df[durum["meta"]["target"]], errors="coerce")
    yeni = [c for c in durum.get("uretilen", []) if c in df.columns]

    if not yeni:
        durum["kalite"] = {"eksik": [], "sabit": [], "sizinti": [], "gecti": []}
        return ("Kalite kapısından geçirilecek üretilmiş değişken bulamadım; "
                "bu adımda eleme yapılmadı.%s" % not_metni)

    eksik, sabit, sizinti = [], [], []
    for c in yeni:
        s = pd.to_numeric(df[c], errors="coerce").replace([np.inf, -np.inf], np.nan)
        if s.isna().mean() > 0.5:
            eksik.append(c); continue
        if s.nunique(dropna=True) <= 1:
            sabit.append(c); continue
        kor = s.corr(y)
        if kor is not None and not pd.isna(kor) and abs(kor) > 0.95:
            sizinti.append(c)

    elendi = set(eksik) | set(sabit) | set(sizinti)
    durum["kalite"] = {"eksik": eksik, "sabit": sabit, "sizinti": sizinti,
                       "gecti": [c for c in yeni if c not in elendi]}

    return ("Kalite kapısı sonucu: %s değişkenin %s tanesi geçti.\n\n%s\n\n%s\n\n%s%s"
            % (_sayi(len(yeni)), _sayi(len(yeni) - len(elendi)),
               _liste("Eksik değer oranı yüksek:", eksik),
               _liste("Tek değerli:", sabit),
               _liste("Sızıntı şüpheli:", sizinti), not_metni))

def secim_plan(durum):
    aday = len((durum.get("kalite") or {}).get("gecti") or [])
    b = durum.get("bolme") or {}
    bolme_ad = ("zamansal: %s dönemi hariç" % b.get("oot_deger")) \
        if b.get("tur") == "zamansal" else "rastgele bölmenin eğitim payı"
    return ("Kaliteyi geçen %s değişkeni seçim hattından geçireceğim:\n\n"
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
    kaynak, zengin = _kaynak(durum)
    if kaynak is None:
        durum["secim"] = {"secilen": 0, "secilen_liste": []}
        return _KAYNAK_YOK % durum.get("veri_seti")

    not_metni = "" if zengin else \
        ("\n\n" + _ZENGIN_YOK % (durum.get("veri_seti"), kaynak))

    df = _df_oku(kaynak)
    adaylar = [c for c in ((durum.get("kalite") or {}).get("gecti") or [])
               if c in df.columns]
    if not adaylar:
        durum["secim"] = {"secilen": 0, "secilen_liste": []}
        return "Seçim hattına girecek aday değişken kalmadı.%s" % not_metni

    binary = (durum.get("profil") or {}).get("hedef_tip") == "binary"
    # SIZINTI SINIRI: MI ve model onem skoru test/OOT satirlarini gormemeli.
    # train_maske gecilmezse secim modulu tum veriye duser.
    tr, _ = maskeler(durum, df)
    tablo, oz = secim_mod.calistir(
        df, durum["meta"]["target"], adaylar,
        oncelik=(durum.get("sfa") or {}).get("iv_skorlari"), binary=binary,
        train_maske=tr)

    yazildi, yedek = _yaz("%s_SECIM" % durum["veri_seti"], tablo, "/secim_tablosu.csv")
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
