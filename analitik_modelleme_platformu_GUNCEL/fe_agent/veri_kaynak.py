# -*- coding: utf-8 -*-
"""fe_agent/veri_kaynak.py - tablolarin DuckDB'nin okuyacagi PARQUET hali.

TEK MOTOR (kullanici karari): Flow'da recipe / veri seti / klasor
kurulmaz, Spark yok. Tam veriye dokunan her hesap webapp'in icinde DuckDB
ile yapilir; DuckDB bir tabloyu ancak dosyadan (Parquet) okur. Bu modul
o dosyayi hazirlar:

  parquet_yolu(veri_seti)
      Kullanicinin veri seti Dataiku uzerinden PARCA PARCA akitilir ve
      webapp'in yerel diskinde bir Parquet dosyasina yazilir (bellege
      sigmasi gerekmez). Ayni veri seti degismedikce dosya yeniden
      indirilmez: Dataiku'daki dosya listesinin (boyut + tarih) imzasi
      saklanir; imza alinamayan veri setlerinde omur 15 dakika.
      KULLANICININ TABLOSUNA YAZILMAZ, yalnizca okunur.

  klasor_dosyasi(yol) / klasore_yukle(yol, dosya)
      PROJE_HAFIZASI'ndaki Parquet'lerin (AMP_VERISETI vb.) yerel kopyasi.
      Platform kendi yazdigi dosyayi once yerel diske yazar, sonra klasore
      yukler; okurken yerel kopya varsa indirmez.

Yerel dizin: $AMP_ONBELLEK_DIZINI ya da <gecici dizin>/amp_onbellek.
Webapp yeniden baslarsa dizin durur; imza tutuyorsa yeniden indirilmez.
"""

import hashlib
import json
import os
import re
import shutil
import tempfile
import time

import dataiku

PARCA_SATIR = 200000          # Dataiku'dan bir seferde akitilan satir
IMZASIZ_OMUR_SN = 900.0       # dosya imzasi alinamayan veri setinde omur

_TIP = {"string": "string", "int": "int64", "bigint": "int64", "smallint": "int64",
        "tinyint": "int64", "float": "float64", "double": "float64",
        "boolean": "bool", "date": "timestamp"}


def dizin():
    d = os.environ.get("AMP_ONBELLEK_DIZINI") or os.path.join(
        tempfile.gettempdir(), "amp_onbellek")
    os.makedirs(d, exist_ok=True)
    return d


def _guvenli(ad):
    ad = re.sub(r"[^A-Za-z0-9_.-]", "_", str(ad))
    return ad[:120]


def _dosya_adi(onek, ad):
    ozet = hashlib.md5(str(ad).encode("utf-8")).hexdigest()[:8]
    return os.path.join(dizin(), "%s_%s_%s.parquet" % (onek, _guvenli(ad), ozet))


# ===========================================================================
# KULLANICININ VERI SETI
# ===========================================================================
def _imza(ds):
    """Veri setinin Dataiku'daki dosyalarinin imzasi; alinamazsa None."""
    try:
        bilgi = ds.get_files_info() or {}
        parcalar = []
        for d in (bilgi.get("globalPaths") or []):
            parcalar.append("%s|%s|%s" % (d.get("path"), d.get("size"),
                                          d.get("lastModified")))
        if not parcalar:
            return None
        return hashlib.md5("\n".join(sorted(parcalar)).encode("utf-8")).hexdigest()
    except Exception:           # pylint: disable=broad-except
        return None


def _arrow_semasi(ds, ornek):
    """Dataiku semasindan pyarrow semasi. Bilinmeyen tip metin olur."""
    import pyarrow as pa
    tipler = {}
    try:
        for kolon in (ds.read_schema() or []):
            tipler[str(kolon.get("name"))] = _TIP.get(str(kolon.get("type")), "string")
    except Exception:           # pylint: disable=broad-except
        tipler = {}
    alanlar = []
    for kolon in ornek.columns:
        tip = tipler.get(str(kolon))
        if tip is None:
            s = ornek[kolon]
            import pandas as pd
            if pd.api.types.is_bool_dtype(s):
                tip = "bool"
            elif pd.api.types.is_integer_dtype(s):
                tip = "int64"
            elif pd.api.types.is_float_dtype(s):
                tip = "float64"
            elif pd.api.types.is_datetime64_any_dtype(s):
                tip = "timestamp"
            else:
                tip = "string"
        alanlar.append((str(kolon), tip))
    return alanlar


def _arrow_tipi(tip):
    import pyarrow as pa
    return {"string": pa.string(), "int64": pa.int64(), "float64": pa.float64(),
            "bool": pa.bool_(), "timestamp": pa.timestamp("us")}[tip]


def _kolon_dizisi(seri, tip):
    """pandas kolonu -> istenen tipte pyarrow dizisi."""
    import numpy as np
    import pandas as pd
    import pyarrow as pa
    if tip == "timestamp":
        s = pd.to_datetime(seri, errors="coerce")
        if getattr(s.dt, "tz", None) is not None:
            s = s.dt.tz_convert("UTC").dt.tz_localize(None)
        return pa.Array.from_pandas(s.astype("datetime64[us]"), type=pa.timestamp("us"))
    if tip == "string":
        s = seri.astype(object)
        s = s.where(s.notna(), None)
        return pa.array([None if v is None else str(v) for v in s.tolist()], type=pa.string())
    if tip == "bool":
        s = seri.astype(object).where(seri.notna(), None)
        return pa.array([None if v is None else bool(v) for v in s.tolist()], type=pa.bool_())
    if tip == "int64":
        if pd.api.types.is_integer_dtype(seri):
            return pa.Array.from_pandas(seri, type=pa.int64())
        s = pd.to_numeric(seri, errors="raise")
        if pd.api.types.is_float_dtype(s):
            dolu = s.dropna()
            if len(dolu) and not bool((dolu == np.floor(dolu)).all()):
                raise ValueError("tam sayi degil")
        return pa.Array.from_pandas(s, type=pa.int64(), safe=False)
    return pa.Array.from_pandas(pd.to_numeric(seri, errors="raise").astype("float64"),
                                type=pa.float64())


def _tablo(parca, alanlar):
    import pyarrow as pa
    diziler, adlar = [], []
    for ad, tip in alanlar:
        diziler.append(_kolon_dizisi(parca[ad], tip))
        adlar.append(ad)
    return pa.Table.from_arrays(diziler, names=adlar)


def _parquet_yaz(ds, hedef):
    """Veri setini parca parca hedef Parquet dosyasina yazar."""
    import pyarrow.parquet as pq
    gecici = hedef + ".yaziliyor"
    yazici, alanlar = None, None
    try:
        for parca in ds.iter_dataframes(chunksize=PARCA_SATIR, infer_with_pandas=True):
            if alanlar is None:
                alanlar = _arrow_semasi(ds, parca)
                # Ilk parcada cevrilemeyen kolon METIN olarak yazilir.
                for j, (ad, tip) in enumerate(alanlar):
                    try:
                        _kolon_dizisi(parca[ad], tip)
                    except Exception:   # pylint: disable=broad-except
                        alanlar[j] = (ad, "string")
                import pyarrow as pa
                sema = pa.schema([(ad, _arrow_tipi(tip)) for ad, tip in alanlar])
                yazici = pq.ParquetWriter(gecici, sema, compression="zstd")
            tablo = _tablo(parca, alanlar)
            yazici.write_table(tablo)
        if yazici is None:
            # Bos veri seti: yalnizca sema.
            import pandas as pd
            import pyarrow as pa
            ornek = ds.get_dataframe(limit=1)
            alanlar = _arrow_semasi(ds, ornek)
            sema = pa.schema([(ad, _arrow_tipi(tip)) for ad, tip in alanlar])
            yazici = pq.ParquetWriter(gecici, sema, compression="zstd")
            yazici.write_table(_tablo(ornek.iloc[0:0], alanlar))
    finally:
        if yazici is not None:
            yazici.close()
    os.replace(gecici, hedef)


def parquet_yolu(veri_seti, taze=False):
    """Kullanicinin veri setinin yerel Parquet kopyasinin yolu."""
    ds = dataiku.Dataset(veri_seti)
    hedef = _dosya_adi("kaynak", veri_seti)
    meta_yol = hedef + ".json"
    imza = _imza(ds)
    if not taze and os.path.exists(hedef):
        try:
            with open(meta_yol) as f:
                meta = json.load(f)
        except Exception:       # pylint: disable=broad-except
            meta = {}
        if imza and meta.get("imza") == imza:
            return hedef
        if not imza and time.time() - float(meta.get("zaman") or 0) < IMZASIZ_OMUR_SN:
            return hedef
    _parquet_yaz(ds, hedef)
    with open(meta_yol, "w") as f:
        json.dump({"imza": imza, "zaman": time.time(), "veri_seti": veri_seti}, f)
    return hedef


def kaynak_dusur(veri_seti):
    """Yerel kopyayi siler (bir sonraki okuma yeniden indirir)."""
    hedef = _dosya_adi("kaynak", veri_seti)
    for y in (hedef, hedef + ".json"):
        try:
            os.remove(y)
        except OSError:
            pass


# ===========================================================================
# PROJE_HAFIZASI DOSYALARI
# ===========================================================================
def yerel_yol(klasor_yolu):
    """PROJE_HAFIZASI'ndaki dosyanin yerel kopyasinin yolu (var olmayabilir)."""
    return _dosya_adi("klasor", klasor_yolu)


def klasor_dosyasi(klasor, klasor_yolu):
    """Klasordeki Parquet'in yerel yolu; yerel kopya yoksa indirir."""
    hedef = yerel_yol(klasor_yolu)
    if os.path.exists(hedef):
        return hedef
    gecici = hedef + ".iniyor"
    with klasor.get_download_stream(klasor_yolu) as kaynak, open(gecici, "wb") as f:
        shutil.copyfileobj(kaynak, f)
    os.replace(gecici, hedef)
    return hedef


def klasore_yukle(klasor, klasor_yolu, dosya):
    """Yerel dosyayi klasore yukler ve yerel kopya olarak saklar."""
    with open(dosya, "rb") as f:
        klasor.upload_stream(klasor_yolu, f)
    hedef = yerel_yol(klasor_yolu)
    if os.path.abspath(dosya) != os.path.abspath(hedef):
        shutil.copyfile(dosya, hedef)
    return hedef


def klasor_dosyasini_dusur(klasor_yolu):
    try:
        os.remove(yerel_yol(klasor_yolu))
    except OSError:
        pass


def gecici_dosya(onek):
    """Motorun yazacagi gecici cikti dosyasi."""
    return os.path.join(dizin(), "%s_%d_%d.parquet" % (_guvenli(onek), os.getpid(),
                                                       int(time.time() * 1000)))
