# -*- coding: utf-8 -*-
"""fe_agent/kutuk.py — degisken kutugu (feature registry).

Kabul edilen her degisken icin: formul, kaynak kolonlar, uretim kodu,
gerekce, kalite sonucu, secim sonucu ve model katkisi tek tabloda.
Bu tablo calismanin kalici ciktisi — sohbet kapansa da kalir.
"""

import datetime
import io
import re

import pandas as pd

from fe_agent.akis_durum import _folder

SUTUNLAR = ["KOSU_ID", "ZAMAN", "FEATURE", "KAYNAK", "IFADE", "KAYNAK_KOLONLAR",
            "GEREKCE", "PYTHON_KODU", "KALITE", "SECIM", "SECIM_GEREKCE", "MI",
            "ONEM", "MODEL_TOPLAM_DELTA_AUC", "VERI_SETI", "HEDEF", "TARIH"]

# Kalite adimi hic calismadiysa ya da degisken hicbir kalite listesinde
# gecmiyorsa kullanilan ucuncu durum. "FAIL (?)" yaziyorduk; elenmemis
# degiskeni elenmis gostermek yaniltiyordu.
KALITE_YOK = "DEGERLENDIRILMEDI"

# SECIM siralama onceligi (alfabetik sira secilenleri en alta atiyordu).
_SECIM_SIRA = {"SECILDI": 0, "ELENDI": 1, "-": 2}


def olustur(durum, oturum_id=None):
    """durum sozlugunden kutuk DataFrame'i uretir.

    oturum_id verilirse her satira KOSU_ID olarak yazilir; boylece ayni
    tabloda birden fazla kosunun satiri ayirt edilebilir.

    Bozuk sekilli girdiler (eksik anahtar / yanlis arite) atlanir ve
    sayilari `tablo.attrs["atlanan_satir"]` icinde doner.
    """
    durum = durum or {}
    atlanan = 0

    kalite = durum.get("kalite") or {}
    if not isinstance(kalite, dict):
        kalite = {}
    kalite_calisti = any(anahtar in kalite
                         for anahtar in ("gecti", "eksik", "sabit", "sizinti"))
    gecenler = set(kalite.get("gecti") or [])
    elenen = {}
    for etiket, anahtar in (("boş değer", "eksik"), ("sabit", "sabit"),
                            ("sızıntı", "sizinti")):
        for k in (kalite.get(anahtar) or []):
            elenen[k] = etiket

    secim = {}
    for r in (durum.get("secim_tablo") or []):
        if not isinstance(r, dict) or not r.get("FEATURE"):
            atlanan += 1
            continue
        secim[r.get("FEATURE")] = r

    model = durum.get("model") or {}
    delta = (model.get("delta") or {}).get("auc") if isinstance(model, dict) else None
    simdi = datetime.datetime.now()
    tarih = simdi.strftime("%Y-%m-%d %H:%M")
    zaman = simdi.isoformat(timespec="seconds")
    kosu_id = str(oturum_id) if oturum_id else "-"

    # Ifade ve kod bilgisi: kural tabanli bloklar + kesif hipotezleri.
    # Blok girdisi: (baslik, satirlar, kaynak) — kaynak "kural" / "kesif".
    # Geriye donuk uyumluluk: (baslik, satirlar) gelirse kaynak "bilinmiyor".
    kaynak_bilgi = {}
    for blok in (durum.get("kod_bloklari") or []):
        if not isinstance(blok, (list, tuple)) or len(blok) < 2:
            atlanan += 1
            continue
        satirlar = blok[1] or []
        etiket = blok[2] if len(blok) > 2 and blok[2] else "bilinmiyor"
        if not isinstance(satirlar, (list, tuple)):
            atlanan += 1
            continue
        for satir in satirlar:
            if not isinstance(satir, (list, tuple)) or len(satir) < 2:
                atlanan += 1
                continue
            ad, kod = satir[0], satir[1]
            gerekce = satir[2] if len(satir) > 2 else ""
            if not ad:
                atlanan += 1
                continue
            kaynak_bilgi[ad] = {"kaynak": str(etiket), "kod": kod,
                                "gerekce": gerekce}

    for h in (durum.get("hipotez") or []):
        if not isinstance(h, dict) or not h.get("ad"):
            atlanan += 1
            continue
        b = kaynak_bilgi.get(h.get("ad"))
        if b is None:
            continue
        b["ifade"] = h.get("ifade")
        b["kolonlar"] = ", ".join(h.get("kolonlar") or [])

    kayitlar = []
    for ad in (durum.get("uretilen") or []):
        if not ad:
            atlanan += 1
            continue
        b = kaynak_bilgi.get(ad) or {}
        s = secim.get(ad) or {}
        if ad in gecenler:
            kalite_sonuc = "PASS"
        elif ad in elenen:
            kalite_sonuc = "FAIL (%s)" % elenen[ad]
        elif kalite_calisti:
            kalite_sonuc = KALITE_YOK   # kalite calisti ama bu degiskeni gormemis
        else:
            kalite_sonuc = KALITE_YOK   # kalite adimi hic calismamis
        kayitlar.append({
            "KOSU_ID": kosu_id,
            "ZAMAN": zaman,
            "FEATURE": ad,
            "KAYNAK": b.get("kaynak", "-"),
            "IFADE": b.get("ifade", "-"),
            "KAYNAK_KOLONLAR": b.get("kolonlar", "-"),
            "GEREKCE": (b.get("gerekce") or "")[:200],
            "PYTHON_KODU": b.get("kod", "-"),
            "KALITE": kalite_sonuc,
            "SECIM": ("SECILDI" if s.get("SECILDI") else
                      ("ELENDI" if s else "-")),
            "SECIM_GEREKCE": s.get("GEREKCE") or "-",
            "MI": s.get("MI"),
            "ONEM": s.get("ONEM"),
            # Tum modelin delta'si — degisken bazli katki DEGIL.
            "MODEL_TOPLAM_DELTA_AUC": delta,
            "VERI_SETI": durum.get("veri_seti"),
            "HEDEF": (durum.get("meta") or {}).get("target"),
            "TARIH": tarih,
        })

    tablo = pd.DataFrame(kayitlar, columns=SUTUNLAR)
    if len(tablo):
        # Acik sira anahtari: SECILDI -> ELENDI -> "-", her grup icinde
        # ONEM azalan.
        tablo = tablo.assign(
            _sira=tablo["SECIM"].map(_SECIM_SIRA).fillna(9)
        ).sort_values(["_sira", "ONEM"], ascending=[True, False],
                      na_position="last").drop(columns=["_sira"]) \
            .reset_index(drop=True)
    tablo.attrs["atlanan_satir"] = atlanan
    return tablo


# ===========================================================================
# DEGISIKLIK KUTUGU
# ---------------------------------------------------------------------------
# NEDEN AYRI BIR DOSYA
#   olustur() yukaridaki kutugu her cagrida durum'dan YENIDEN uretir; o
#   tablo "su an ne var" sorusunu cevaplar. Analistin sozluk calisma
#   kopyasinda yaptigi kategori duzeltmesi ise bir OLAY: kim, ne zaman,
#   neyi neye cevirdi. Yeniden uretilebilir bir ozete sigmaz; ustune
#   yazilirsa da izi kaybolur. Bu yuzden ekleme-yalnizca (append-only)
#   bir CSV olarak PROJE_HAFIZASI'nda, oturum klasorunde durur.
#
# NEDEN SESSIZ
#   Kutuge yazamamak, kullanicinin yapmak istedigi duzeltmeyi
#   engellemek icin gecerli bir sebep degil. Yazma basarisiz olursa
#   False doner; cagiran taraf isterse bildirir, akis durmaz.
# ===========================================================================
DEGISIKLIK_DOSYASI = "sozluk_degisiklik.csv"
DEGISIKLIK_SUTUNLARI = ["ZAMAN", "KOSU_ID", "ALAN", "ANAHTAR",
                        "ESKI", "YENI", "KAYNAK"]


def _degisiklik_yolu(oturum_anahtari):
    temiz = re.sub(r"[^A-Za-z0-9_-]", "", str(oturum_anahtari or ""))
    if not temiz:
        return None
    return "/%s/%s" % (temiz, DEGISIKLIK_DOSYASI)


def degisiklik_oku(oturum_anahtari):
    """Bu oturumda kaydedilmis degisiklikler; yoksa bos DataFrame."""
    yol = _degisiklik_yolu(oturum_anahtari)
    if not yol:
        return pd.DataFrame(columns=DEGISIKLIK_SUTUNLARI)
    try:
        with _folder().get_download_stream(yol) as s:
            ham = s.read()
        return pd.read_csv(io.BytesIO(ham))
    except Exception:
        return pd.DataFrame(columns=DEGISIKLIK_SUTUNLARI)


def degisiklik_dus(oturum_anahtari, kayitlar):
    """Degisiklik satirlarini kutuge EKLER (ustune yazmaz).

    kayitlar: [{"ALAN", "ANAHTAR", "ESKI", "YENI", "KAYNAK"}]
    Doner: True/False. Istisna firlatmaz."""
    satirlar = [k for k in (kayitlar or []) if isinstance(k, dict)]
    if not satirlar:
        return False
    yol = _degisiklik_yolu(oturum_anahtari)
    if not yol:
        return False

    zaman = datetime.datetime.now().isoformat(timespec="seconds")
    yeni = pd.DataFrame([{
        "ZAMAN": zaman,
        "KOSU_ID": str(oturum_anahtari),
        "ALAN": k.get("ALAN") or "-",
        "ANAHTAR": k.get("ANAHTAR") or "-",
        "ESKI": k.get("ESKI"),
        "YENI": k.get("YENI"),
        "KAYNAK": k.get("KAYNAK") or "-",
    } for k in satirlar], columns=DEGISIKLIK_SUTUNLARI)

    try:
        eski = degisiklik_oku(oturum_anahtari)
        tablo = pd.concat([eski, yeni], ignore_index=True) \
            if len(eski) else yeni
        _folder().upload_stream(yol, tablo.to_csv(index=False).encode("utf-8"))
        return True
    except Exception:
        return False
