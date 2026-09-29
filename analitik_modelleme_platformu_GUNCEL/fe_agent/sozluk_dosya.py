# -*- coding: utf-8 -*-
"""fe_agent/sozluk_dosya.py - YUKLENEN SOZLUK DOSYASI (Excel / CSV).

Kullanici karari: "sözlük varsa excel ya da csv formatında vereceğim".
Dosya kartin icinden yuklenir ve calismanin kendi klasorune Parquet
olarak kaydedilir; kullanicinin dosyasina / tablosuna hicbir sey yazilmaz:

    PROJE_HAFIZASI/<calisma>/yuklenen/<DOSYA_ADI>.parquet

Formda deger olarak DOSYA ADI tasinir ("KREDI_SOZLUK.xlsx"); akis onu
bu yola cevirir (bkz. coz). Sonraki adimlar sozlugu yol uzerinden okur
(akis_durum._df_oku "/" ile baslayan adi klasorden okur).

BICIMLER
  .xlsx : bagimliliksiz okuyucu (zip + XML). xlsx_yaz ile ayni sebep:
          Dataiku kod ortaminda openpyxl kurulu olmayabilir. Ilk sayfa
          okunur; ilk dolu satir kolon basligidir.
  .csv  : ayirici otomatik (virgul, noktali virgul, sekme); kodlama
          UTF-8, olmazsa Windows Turkce (cp1254).
  .xls  : eski ikili Excel okunamaz; kullanicidan .xlsx / .csv istenir.

Butun hucreler METIN okunur: sozlukte "045" gibi kodlar sayiya
donmemeli.

TABLO KOLONU: dosyada TABLO (TABLO_ADI, TABLE, TABLE_NAME, KAYNAK_TABLO)
kolonu varsa her satir o tablonun kolonunu tanimlar; Mod B'de kaynak
tablolar bununla eslenir.
"""

import io
import posixpath
import re
import unicodedata
import zipfile
import xml.etree.ElementTree as ET

import pandas as pd

UZANTILAR = (".xlsx", ".csv")
ESKI_UZANTILAR = (".xls",)
EN_BUYUK_BAYT = 50 * 1024 * 1024
KLASOR = "yuklenen"

TABLO_KOLON_ADLARI = ("TABLO", "TABLO_ADI", "TABLOADI", "TABLE", "TABLE_NAME",
                      "KAYNAK_TABLO")

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
       "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
       "pr": "http://schemas.openxmlformats.org/package/2006/relationships"}


class DosyaHatasi(Exception):
    """Kullaniciya aynen gosterilecek hata."""


# ===========================================================================
# AD VE YOL
# ===========================================================================
_TR = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


def temiz_ad(ham):
    """Yuklenen dosyanin adi -> guvenli ad: "Kredi Sözlük.xlsx" ->
    "Kredi_Sozluk.xlsx". Formda ve ekranda bu ad gorunur."""
    ad = posixpath.basename(str(ham or "").replace("\\", "/")).strip()
    ad = unicodedata.normalize("NFC", ad).translate(_TR)
    ad = unicodedata.normalize("NFKD", ad).encode("ascii", "ignore").decode("ascii")
    kok, nokta, uzanti = ad.rpartition(".")
    if not nokta:
        kok, uzanti = ad, ""
    kok = re.sub(r"[^A-Za-z0-9_-]+", "_", kok).strip("_-")[:80] or "sozluk"
    return "%s.%s" % (kok, uzanti.lower()) if uzanti else kok


def yuklenen_mi(deger):
    return str(deger or "").lower().endswith(UZANTILAR)


def yol(klasor, ad):
    """Calismanin klasorunde dosyanin Parquet yolu."""
    return "/%s/%s/%s.parquet" % (klasor, KLASOR, temiz_ad(ad))


def coz(klasor, deger):
    """Formdan gelen deger -> okunacak ad. Dosya adiysa klasor yolu, degilse
    (Dataiku veri seti) aynen."""
    if yuklenen_mi(deger):
        return yol(klasor, deger)
    return deger


# ===========================================================================
# OKUMA
# ===========================================================================
def _sutun_no(ref):
    harf = re.match(r"[A-Z]+", ref or "")
    n = 0
    for c in (harf.group(0) if harf else ""):
        n = n * 26 + (ord(c) - 64)
    return n - 1


def _metin(el):
    return "".join(t.text or "" for t in el.iter("{%s}t" % _NS["m"]))


def xlsx_oku(ham):
    """Ilk sayfa -> satir listesi (her satir metin listesi)."""
    try:
        z = zipfile.ZipFile(io.BytesIO(ham))
    except zipfile.BadZipFile:
        raise DosyaHatasi("Dosya geçerli bir .xlsx dosyası değil.")
    adlar = set(z.namelist())
    paylasilan = []
    if "xl/sharedStrings.xml" in adlar:
        kok = ET.fromstring(z.read("xl/sharedStrings.xml"))
        paylasilan = [_metin(si) for si in kok.findall("m:si", _NS)]
    # Ilk sayfanin dosyasi: workbook.xml'deki ilk <sheet> + iliskisi
    sayfa = "xl/worksheets/sheet1.xml"
    try:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        ilk = wb.find("m:sheets/m:sheet", _NS)
        rid = ilk.get("{%s}id" % _NS["r"]) if ilk is not None else None
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        for r in rels.findall("pr:Relationship", _NS):
            if r.get("Id") == rid:
                hedef = r.get("Target").lstrip("/")
                sayfa = hedef if hedef.startswith("xl/") else "xl/" + hedef
    except Exception:           # pylint: disable=broad-except
        pass
    if sayfa not in adlar:
        raise DosyaHatasi("Excel dosyasında sayfa bulunamadı.")
    satirlar = []
    for row in ET.fromstring(z.read(sayfa)).iter("{%s}row" % _NS["m"]):
        hucreler = {}
        sira = 0
        for c in row.findall("m:c", _NS):
            i = _sutun_no(c.get("r")) if c.get("r") else sira
            sira = i + 1
            tur = c.get("t")
            if tur == "inlineStr":
                deger = _metin(c)
            else:
                v = c.find("m:v", _NS)
                deger = v.text if v is not None else None
                if tur == "s" and deger is not None:
                    deger = paylasilan[int(deger)]
                elif tur == "b" and deger is not None:
                    deger = "TRUE" if deger == "1" else "FALSE"
                elif deger is not None and re.fullmatch(r"-?\d+\.0+", deger):
                    deger = deger.split(".")[0]
            if deger is not None:
                hucreler[i] = str(deger)
        if hucreler:
            genislik = max(hucreler) + 1
            satirlar.append([hucreler.get(i) for i in range(genislik)])
    return satirlar


def _csv_oku(ham):
    son = None
    for kod in ("utf-8-sig", "cp1254", "latin-1"):
        try:
            metin = ham.decode(kod)
        except UnicodeDecodeError as e:
            son = e
            continue
        try:
            return pd.read_csv(io.StringIO(metin), sep=None, engine="python",
                               dtype=str, keep_default_na=False)
        except Exception as e:      # pylint: disable=broad-except
            son = e
    raise DosyaHatasi("CSV dosyası okunamadı: %s" % str(son)[:160])


def tabloya(satirlar):
    """Satir listesi -> DataFrame; ilk dolu satir baslik."""
    satirlar = [s for s in satirlar if any((x or "").strip() for x in s)]
    if not satirlar:
        raise DosyaHatasi("Dosya boş; içinde satır yok.")
    baslik = [str(x or "").strip() for x in satirlar[0]]
    genislik = max(len(s) for s in satirlar)
    baslik += [""] * (genislik - len(baslik))
    baslik = [b or "KOLON_%d" % (i + 1) for i, b in enumerate(baslik)]
    govde = [list(s) + [None] * (genislik - len(s)) for s in satirlar[1:]]
    return pd.DataFrame(govde, columns=baslik)


def oku(ham, ad):
    """Yuklenen dosya -> DataFrame (butun hucreler metin, bos hucre None)."""
    ad_kucuk = str(ad or "").lower()
    if ad_kucuk.endswith(ESKI_UZANTILAR):
        raise DosyaHatasi("Eski .xls biçimi okunamıyor. Dosyayı Excel'de "
                          ".xlsx ya da .csv olarak kaydedip yükleyin.")
    if not ad_kucuk.endswith(UZANTILAR):
        raise DosyaHatasi("Yalnızca .xlsx ve .csv dosyası yüklenebilir.")
    if not ham:
        raise DosyaHatasi("Dosya boş.")
    if len(ham) > EN_BUYUK_BAYT:
        raise DosyaHatasi("Dosya çok büyük (en fazla 50 MB).")
    df = tabloya(xlsx_oku(ham)) if ad_kucuk.endswith(".xlsx") else _csv_oku(ham)
    df.columns = [str(c).strip() for c in df.columns]
    for c in df.columns:
        df[c] = df[c].map(lambda v: None if v is None or not str(v).strip()
                          else str(v).strip())
    return df.dropna(how="all").reset_index(drop=True)


# ===========================================================================
# TABLO KOLONU
# ===========================================================================
def tablo_kolonu_bul(df):
    from fe_agent import sozluk_calisma
    return sozluk_calisma._kolon_ara(df, TABLO_KOLON_ADLARI)


def _kisa(ad):
    return str(ad or "").split(".")[-1].strip().upper()


def tabloya_ait(df, tablo):
    """Sozlukte bu tabloya ait satirlar. TABLO kolonu yoksa ya da tabloya
    ait satir yoksa (None, ...) doner; cagiran butun sozluge duser.
    Tablo adi PROJE onekinden bagimsiz, buyuk/kucuk harf farksiz eslenir."""
    k = tablo_kolonu_bul(df)
    if k is None:
        return None
    maske = df[k].map(_kisa) == _kisa(tablo)
    return df[maske] if maske.any() else None
