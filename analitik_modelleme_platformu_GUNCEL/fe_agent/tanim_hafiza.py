# -*- coding: utf-8 -*-
"""fe_agent/tanim_hafiza.py - ONAYLI TANIM HAFIZASI (calismaya ozel).



NE GIRER - yalnizca bir kullanicinin ONAYLADIGI tanimlar:
  * Sozluk Tanimlari kartinda "Sozluge Ekle" ile onaylanan aciklama
    (dil modeli onerisi ya da kullanicinin yazdigi)
  * Tanim kontrolunde "Uygula" ile onaylanan duzeltme
  * Sag paneldeki Sozluk Tanimi hucresinde kullanicinin yazdigi tanim
Onaylanmamis model onerisi ve kurumun sozlugundeki mevcut tanimlar
GIRMEZ (sozluk zaten ayrica ornek olarak okunuyor).

NEREDE - PROJE_HAFIZASI/<calisma>/TANIM_HAFIZASI.json. Calismaya
ozeldir: tablo degisebilecegi icin bir calismanin onayi baska calismaya
tasinmaz; calisma yeniden acildiginda kullanilir. Girdi veri setine ve
girdi sozlugune hicbir kosulda yazilmaz.

ANAHTAR - (KOLON, VERI_SETI). Ayni veri setinin ayni kolonu yeniden
onaylanirsa satir guncellenir; baska veri setindeki ayni adli kolon ayri
satirdir. Oneride bir kolon icin EN SON onaylanan tanim kullanilir.

OKUMA HATASI YAZMAYI DURDURUR: dosya var ama okunamiyorsa ustune
yazilmaz (bos tabloyla ezip butun hafizayi kaybetmek yerine o onay
hafizaya dusmez ve sebep doner)."""

import datetime
import threading
import time

import pandas as pd

from fe_agent import tablo_io
from fe_agent.akis_durum import _folder

DOSYA_AD = "TANIM_HAFIZASI.json"
KOLONLAR = ["KOLON", "ACIKLAMA", "VERI_SETI", "KAYNAK", "KULLANICI", "TARIH"]

KAYNAK_LLM = "dil modeli önerisi onaylandı"
KAYNAK_KULLANICI = "kullanıcı yazdı"
KAYNAK_DUZELTME = "tanım düzeltmesi onaylandı"
KAYNAK_PANEL = "sağ panelde düzenlendi"
KAYNAK_HAFIZA = "onaylı hafızadan alındı, yeniden onaylandı"

ONBELLEK_OMRU_SN = 30.0
_ONBELLEK = {}            # yol -> {"zaman", "df"}
_KILIT = threading.Lock()


def _bos():
    return pd.DataFrame(columns=KOLONLAR)


def _yol(klasor):
    return "/%s/%s" % (str(klasor).strip("/"), DOSYA_AD)


def _var_mi(dosya):
    """Dosya var mi? Doner: True / False / None (bilinemedi)."""
    klasor = _folder()
    for yol in tablo_io.aday_yollar(dosya):
        try:
            bilgi = klasor.get_path_details(yol) or {}
            if bilgi.get("exists"):
                return True
            continue
        except Exception:
            pass
        try:
            yollar = set(klasor.list_paths_in_partition())
        except Exception:
            return None
        if yol in yollar or yol.lstrip("/") in yollar:
            return True
    return False


def _oku_ham(dosya):
    """Doner: (df, hata). Dosya yoksa bos tablo, hata None."""
    try:
        df = tablo_io.klasorden_oku(_folder(), dosya)
    except Exception as e:
        var = _var_mi(dosya)
        if var is False:
            return _bos(), None
        return None, "Tanım hafızası okunamadı (%s)." % str(e)[:120]
    for k in KOLONLAR:
        if k not in df.columns:
            df[k] = ""
    return df[KOLONLAR].fillna("").astype(str), None


def oku(klasor, taze=False):
    """Calismanin hafiza tablosu (onbellekli). Okunamazsa bos tablo."""
    if not klasor:
        return _bos()
    dosya = _yol(klasor)
    simdi = time.time()
    k = _ONBELLEK.get(dosya)
    if not taze and k and simdi - k["zaman"] <= ONBELLEK_OMRU_SN:
        return k["df"]
    df, hata = _oku_ham(dosya)
    if df is None:
        return k["df"] if k else _bos()
    _ONBELLEK[dosya] = {"zaman": simdi, "df": df}
    return df


def tanimlar(klasor):
    """{kolon: aciklama} - her kolon icin EN SON onaylanan tanim."""
    df = oku(klasor)
    if df.empty:
        return {}
    df = df[df["ACIKLAMA"].str.strip() != ""].sort_values("TARIH")
    return dict(zip(df["KOLON"], df["ACIKLAMA"]))


def bul(adlar, veri_seti, klasor):
    """Kolon adlari icin ONAYLI tanim (dogrudan doldurma icin).

    Doner: {kolon: {"aciklama", "veri_seti", "tarih"}}. Ayni veri setinde
    onaylanmis tanim varsa o, yoksa baska veri setinde EN SON onaylanan.
    Ad eslesmesi birebir; bulunamayan kolon donmez."""
    df = oku(klasor)
    if df.empty or not adlar:
        return {}
    istenen = set(str(a) for a in adlar)
    df = df[(df["ACIKLAMA"].str.strip() != "") & df["KOLON"].isin(istenen)]
    if df.empty:
        return {}
    df = df.assign(_ayni=(df["VERI_SETI"] == str(veri_seti or "")).astype(int))
    df = df.sort_values(["_ayni", "TARIH"])
    cikti = {}
    for _i, r in df.iterrows():          # son yazilan (en uygun) kazanir
        cikti[r["KOLON"]] = {"aciklama": r["ACIKLAMA"], "veri_seti": r["VERI_SETI"],
                             "tarih": r["TARIH"]}
    return cikti


def ekle(kayitlar, veri_seti="", kullanici="", klasor=""):
    """Onaylanan tanimlari hafizaya yazar.

    kayitlar: [{"kolon", "aciklama", "kaynak"}]. Bos aciklama atlanir.
    Doner: (yazilan_sayi, hata). Istisna firlatmaz."""
    temiz = []
    for k in kayitlar or []:
        if not isinstance(k, dict):
            continue
        ad = str(k.get("kolon") or "").strip()
        ack = str(k.get("aciklama") or "").strip()
        if ad and ack:
            temiz.append((ad, ack, str(k.get("kaynak") or KAYNAK_KULLANICI)))
    if not temiz or not klasor:
        return 0, None
    dosya = _yol(klasor)
    veri_seti = str(veri_seti or "")
    zaman = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _KILIT:
        df, hata = _oku_ham(dosya)
        if df is None:
            return 0, hata
        anahtar = set((ad, veri_seti) for ad, _a, _k in temiz)
        tut = [(a, v) not in anahtar for a, v in zip(df["KOLON"], df["VERI_SETI"])]
        df = df[tut]
        yeni = pd.DataFrame([{"KOLON": ad, "ACIKLAMA": ack, "VERI_SETI": veri_seti,
                              "KAYNAK": kaynak, "KULLANICI": str(kullanici or ""),
                              "TARIH": zaman} for ad, ack, kaynak in temiz],
                            columns=KOLONLAR)
        df = pd.concat([df, yeni], ignore_index=True)
        try:
            tablo_io.klasore_yaz(_folder(), dosya, df)
        except Exception as e:
            return 0, "Tanım hafızasına yazılamadı (%s)." % str(e)[:120]
        _ONBELLEK[dosya] = {"zaman": time.time(), "df": df}
    return len(temiz), None


def arka_planda_ekle(kayitlar, veri_seti="", kullanici="", klasor=""):
    """ekle'yi istek is parcacigini bekletmeden calistirir. Hafiza bir
    kolaylik: yazilamazsa kullanicinin onayi (sozluk calisma kopyasi)
    etkilenmez."""
    if not kayitlar:
        return
    threading.Thread(target=ekle, args=(list(kayitlar), veri_seti, kullanici, klasor),
                     daemon=True).start()


# ---------------------------------------------------------------------------
# ONERI ONBELLEGI. ONAYLI DEGIL: dil modelinin bir kolon icin verdigi SON
# oneri. CALISMAYA OZELDIR: calismanin kendi klasorunde durur; ayni
# calisma yeniden acildiginda dil modeli tekrar cagrilmaz, oneri "Dil
# Modeli Onerisi" olarak gelir. Calismalar arasi bilgi yalniz onayli
# tanim hafizasindadir (TANIM_HAFIZASI).
# ---------------------------------------------------------------------------
ONERI_AD = "ONERI_ONBELLEGI.json"
ONERI_KOLONLAR = ["KOLON", "VERI_SETI", "ACIKLAMA", "MODELLER", "TARIH"]
_ONERI_ONBELLEK = {}      # yol -> {"zaman", "df"}


def _oneri_yolu(klasor):
    return "/%s/%s" % (str(klasor).strip("/"), ONERI_AD)


def _oneri_oku(yol):
    try:
        df = tablo_io.klasorden_oku(_folder(), yol)
    except Exception:
        return pd.DataFrame(columns=ONERI_KOLONLAR)
    for k in ONERI_KOLONLAR:
        if k not in df.columns:
            df[k] = ""
    return df[ONERI_KOLONLAR].fillna("").astype(str)


def oneri_bul(adlar, veri_seti, klasor):
    """{kolon: {"aciklama", "modeller"}} - bu calismanin, AYNI veri setinin
    onerileri. klasor: calismanin PROJE_HAFIZASI icindeki klasoru."""
    if not adlar or not veri_seti or not klasor:
        return {}
    yol = _oneri_yolu(klasor)
    simdi = time.time()
    k = _ONERI_ONBELLEK.get(yol)
    if not k or simdi - k["zaman"] > ONBELLEK_OMRU_SN:
        k = _ONERI_ONBELLEK[yol] = {"zaman": simdi, "df": _oneri_oku(yol)}
    df = k["df"]
    if df is None or df.empty:
        return {}
    df = df[(df["VERI_SETI"] == str(veri_seti)) & df["KOLON"].isin(set(map(str, adlar)))
            & (df["ACIKLAMA"].str.strip() != "")]
    return {r["KOLON"]: {"aciklama": r["ACIKLAMA"], "modeller": r["MODELLER"]}
            for _i, r in df.iterrows()}


def oneri_ekle(oneriler, veri_seti, klasor):
    """oneriler: {kolon: {"aciklama", "modeller"}}. Ayni (kolon, veri seti)
    guncellenir; calismanin klasorune yazilir. Arka planda; hata akisi
    durdurmaz."""
    temiz = {str(k): v for k, v in (oneriler or {}).items()
             if isinstance(v, dict) and str(v.get("aciklama") or "").strip()}
    if not temiz or not veri_seti or not klasor:
        return
    yol = _oneri_yolu(klasor)

    def is_():
        with _KILIT:
            try:
                df = _oneri_oku(yol)
                df = df[~((df["VERI_SETI"] == str(veri_seti)) & df["KOLON"].isin(set(temiz)))]
                zaman = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                yeni = pd.DataFrame([{"KOLON": k, "VERI_SETI": str(veri_seti),
                                      "ACIKLAMA": str(v["aciklama"]),
                                      "MODELLER": str(v.get("modeller") or ""),
                                      "TARIH": zaman} for k, v in temiz.items()],
                                    columns=ONERI_KOLONLAR)
                df = pd.concat([df, yeni], ignore_index=True)
                tablo_io.klasore_yaz(_folder(), yol, df)
                _ONERI_ONBELLEK[yol] = {"zaman": time.time(), "df": df}
            except Exception:
                pass
            _kok_onbellegi_sil()
    threading.Thread(target=is_, daemon=True).start()


def _kok_onbellegi_sil():
    """PROJE_HAFIZASI kokunde kalmis eski oneri onbellegi (calismaya ozel
    olmayan bicim) bir kez silinir; onbellek onayli bilgi tasimaz."""
    if _KOK_SILINDI:
        return
    _KOK_SILINDI.append(True)
    try:
        klasor = _folder()
        for yol in ("/" + ONERI_AD, "/ONERI_ONBELLEGI.parquet", "/ONERI_ONBELLEGI.csv"):
            try:
                klasor.delete_path(yol)
            except Exception:
                pass
    except Exception:
        pass


_KOK_SILINDI = []
