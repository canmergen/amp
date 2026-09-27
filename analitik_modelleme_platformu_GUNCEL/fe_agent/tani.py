# -*- coding: utf-8 -*-
"""fe_agent/tani.py - webapp ORTAMININ tanisi (motor secimi icin).

Kullanici karari: Flow'da recipe / veri seti kurulmayacak, her sey webapp
icinde ve PROJE_HAFIZASI klasorunde uretilecek. Bunun icin webapp'in kendi
sureci hakkinda su sorularin cevabi gerekiyor:

  1. Hangi Python, hangi paketler (polars / duckdb / pyarrow / lightgbm ...)?
  2. Sunucuda ne kadar bellek ve cekirdek var (webapp'in tavanı)?
  3. Baz veri seti nerede duruyor, dogrudan Parquet olarak okunabiliyor mu?
  4. Dataiku uzerinden okuma ne kadar suruyor?

Hicbir seye YAZMAZ. Gizli olabilecek degerler (secret / token / password /
key) yildizlanir.
"""

import os
import sys
import time
import platform

_GIZLI = ("secret", "token", "password", "passwd", "credential", "key")


def _surum(modul):
    try:
        m = __import__(modul)
        return getattr(m, "__version__", "var")
    except Exception as e:      # pylint: disable=broad-except
        return "YOK (%s)" % type(e).__name__


def _bellek():
    """MemTotal / MemAvailable (GB) ve varsa cgroup siniri."""
    bilgi = {}
    try:
        with open("/proc/meminfo") as f:
            for satir in f:
                ad, deger = satir.split(":")[0], satir.split()[1]
                if ad in ("MemTotal", "MemAvailable"):
                    bilgi[ad] = round(int(deger) / 1024 / 1024, 1)
    except Exception:           # pylint: disable=broad-except
        pass
    for yol in ("/sys/fs/cgroup/memory.max",
                "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            with open(yol) as f:
                ham = f.read().strip()
            if ham.isdigit() and int(ham) < 1 << 50:
                bilgi["cgroup_sinir_gb"] = round(int(ham) / 1024 ** 3, 1)
            break
        except Exception:       # pylint: disable=broad-except
            continue
    bilgi["cekirdek"] = os.cpu_count()
    return bilgi


def _gizle(nesne):
    if isinstance(nesne, dict):
        return {k: ("***" if any(g in str(k).lower() for g in _GIZLI) else _gizle(v))
                for k, v in nesne.items()}
    if isinstance(nesne, list):
        return [_gizle(v) for v in nesne[:5]]
    return nesne


def _veri_seti(ad, satir_siniri):
    import dataiku
    sonuc = {"ad": ad}
    ds = dataiku.Dataset(ad)
    try:
        sonuc["konum"] = _gizle(ds.get_location_info())
    except Exception as e:      # pylint: disable=broad-except
        sonuc["konum"] = "okunamadı: %s" % str(e)[:200]
    try:
        dosyalar = ds.get_files_info()
        yollar = [d.get("path") for d in (dosyalar.get("globalPaths") or [])]
        sonuc["dosya_sayisi"] = len(yollar)
        sonuc["dosyalar"] = yollar[:3]
        sonuc["toplam_bayt"] = sum(int(d.get("size") or 0)
                                   for d in (dosyalar.get("globalPaths") or []))
    except Exception as e:      # pylint: disable=broad-except
        sonuc["dosyalar"] = "okunamadı: %s" % str(e)[:200]
    # Dataiku uzerinden okuma suresi (pandas). satir_siniri satirla sinirli.
    try:
        t = time.time()
        df = ds.get_dataframe(limit=satir_siniri)
        sonuc["dataiku_okuma"] = {"satir": int(df.shape[0]), "kolon": int(df.shape[1]),
                                  "saniye": round(time.time() - t, 1)}
    except Exception as e:      # pylint: disable=broad-except
        sonuc["dataiku_okuma"] = "okunamadı: %s" % str(e)[:200]
    return sonuc


def _dogrudan_parquet(konum):
    """Baz veri seti S3 / dosya sisteminde Parquet ise polars ile DOGRUDAN
    okunabiliyor mu (Dataiku'ya ugramadan)? Yalnizca semayi okur."""
    try:
        import polars as pl
    except Exception:           # pylint: disable=broad-except
        return "polars yok"
    if not isinstance(konum, dict):
        return "konum bilgisi yok"
    bilgi = konum.get("info") or {}
    tur = konum.get("locationInfoType")
    yol = bilgi.get("path") or ""
    try:
        if tur == "S3":
            kova = bilgi.get("bucket")
            adres = "s3://%s/%s" % (kova, yol.strip("/"))
            t = time.time()
            sema = pl.scan_parquet(adres + "/**/*.parquet").collect_schema()
            return {"adres": adres, "kolon": len(sema), "saniye": round(time.time() - t, 1)}
        if tur in ("FS", "FILESYSTEM", "UPLOAD"):
            t = time.time()
            sema = pl.scan_parquet(os.path.join(yol, "**/*.parquet")).collect_schema()
            return {"adres": yol, "kolon": len(sema), "saniye": round(time.time() - t, 1)}
        return "desteklenmeyen konum türü: %s" % tur
    except Exception as e:      # pylint: disable=broad-except
        return "okunamadı: %s: %s" % (type(e).__name__, str(e)[:300])


def tani(veri_seti=None, satir_siniri=20000):
    sonuc = {
        "python": {"surum": platform.python_version(), "yol": sys.executable},
        "paketler": {p: _surum(p) for p in ("polars", "duckdb", "pyarrow", "pandas",
                                            "numpy", "lightgbm", "xgboost", "sklearn")},
        "bellek": _bellek(),
    }
    try:
        import dataiku
        sonuc["dataiku"] = _surum("dataiku")
        sonuc["kullanici"] = dataiku.api_client().get_auth_info().get("authIdentifier")
    except Exception as e:      # pylint: disable=broad-except
        sonuc["dataiku"] = "hata: %s" % str(e)[:200]
    if veri_seti:
        sonuc["veri_seti"] = _veri_seti(veri_seti, satir_siniri)
        konum = sonuc["veri_seti"].get("konum")
        sonuc["dogrudan_parquet"] = _dogrudan_parquet(konum)
    return sonuc
