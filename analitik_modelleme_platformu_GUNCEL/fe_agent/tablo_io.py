# -*- coding: utf-8 -*-
"""fe_agent/tablo_io.py - klasore yazilan tablolarin BICIMI (Parquet).

Parquet
tipleri korur (CSV'de "045" geri okununca 45 oluyor, tarih metne donuyor),
sikistirilmis ve kolon bazli okunabilir.

  yaz  : her zaman .parquet. Yol ".csv" ile verilse de ".parquet" yazilir.
         Parquet motoru (pyarrow) kurulu degilse CSV'ye DUSER - uygulama
         durmasin; o durumda code env'e pyarrow eklenmeli.
  oku  : once .parquet, yoksa .csv (bu surumden ONCE yazilmis calismalar).

JSON: yol ".json" ile biterse tablo okunur bicimde (satir basina bir
kayit) JSON yazilir; PROJE_HAFIZASI'ndaki hafiza dosyalari boyledir.
Okurken JSON yoksa ayni adli .parquet / .csv okunur, bir kez JSON'a
aktarilir ve eski dosya silinir.
"""

import io
import json
import re

import numpy as np
import pandas as pd

PARQUET = ".parquet"
JSON = ".json"
CSV = ".csv"


def parquet_yolu(yol):
    yol = str(yol)
    return re.sub(r"\.csv$", PARQUET, yol) if yol.endswith(CSV) else \
        (yol if yol.endswith(PARQUET) else yol + PARQUET)


def csv_yolu(yol):
    return re.sub(r"\.parquet$", CSV, str(yol))


def aday_yollar(yol):
    """Okuma sirasi: once Parquet, sonra (eski calisma) CSV. JSON yolunda
    once JSON, sonra ayni adli Parquet ve CSV."""
    if str(yol).endswith(JSON):
        kok = str(yol)[:-len(JSON)]
        return [str(yol), kok + PARQUET, kok + ".csv"]
    pq = parquet_yolu(yol)
    cs = csv_yolu(pq)
    return [pq, cs]


def _metne(deger):
    if deger is None:
        return None
    if isinstance(deger, float) and np.isnan(deger):
        return None
    return str(deger)


def _parquet_bayt(tablo):
    import pyarrow  # noqa: F401  (yoksa ImportError -> CSV'ye dusulur)
    df = tablo.copy()
    df.columns = [str(c) for c in df.columns]
    df = df.reset_index(drop=True)
    try:
        tampon = io.BytesIO()
        df.to_parquet(tampon, index=False)
        return tampon.getvalue()
    except Exception:
        pass
    # KARISIK TIPLI kolon (ayni kolonda sayi ve metin) Parquet'e yazilamaz;
    # yalnizca o kolonlar metne cevrilir, digerleri tipini korur.
    import pyarrow as pa
    for c in df.columns:
        if df[c].dtype != object:
            continue
        try:
            pa.array(df[c], from_pandas=True)
        except Exception:
            df[c] = df[c].map(_metne)
    tampon = io.BytesIO()
    df.to_parquet(tampon, index=False)
    return tampon.getvalue()


def _json_bayt(tablo):
    df = tablo.copy()
    df.columns = [str(c) for c in df.columns]
    kayit = df.astype(object).where(pd.notna(df), None).to_dict("records")
    return json.dumps(kayit, ensure_ascii=False, indent=2, default=str).encode("utf-8")


def bayta(tablo, yol):
    """Doner: (bayt, gercek_yol)."""
    if str(yol).endswith(JSON):
        return _json_bayt(tablo), str(yol)
    try:
        return _parquet_bayt(tablo), parquet_yolu(yol)
    except ImportError:
        return tablo.to_csv(index=False).encode("utf-8"), csv_yolu(parquet_yolu(yol))


def bayttan(ham, yol, satir=None):
    if str(yol).endswith(JSON):
        veri = json.loads(ham.decode("utf-8") or "[]")
        df = pd.DataFrame(veri if isinstance(veri, list) else [])
        return df.head(satir) if satir else df
    if str(yol).endswith(PARQUET):
        df = pd.read_parquet(io.BytesIO(ham))
        return df.head(satir) if satir else df
    return pd.read_csv(io.BytesIO(ham), nrows=satir)


def klasore_yaz(klasor, yol, tablo):
    """Tabloyu klasore yazar. Doner: gercek yol (istisna yukari cikar)."""
    ham, gercek = bayta(tablo, yol)
    klasor.upload_stream(gercek, ham)
    return gercek


def klasorden_oku(klasor, yol, satir=None):
    """Once Parquet, yoksa CSV. Ikisi de yoksa son hata yukari cikar."""
    hata = None
    for aday in aday_yollar(yol):
        try:
            with klasor.get_download_stream(aday) as s:
                ham = s.read()
        except Exception as e:       # pylint: disable=broad-except
            hata = e
            continue
        df = bayttan(ham, aday, satir)
        if str(yol).endswith(JSON) and aday != str(yol) and satir is None:
            # Eski bicim bir kez JSON'a aktarilir, eski dosya silinir.
            try:
                klasor.upload_stream(str(yol), _json_bayt(df))
                klasor.delete_path(aday)
            except Exception:        # pylint: disable=broad-except
                pass
        return df
    raise hata if hata else IOError(str(yol))
