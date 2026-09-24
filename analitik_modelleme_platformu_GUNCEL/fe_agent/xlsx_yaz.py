# -*- coding: utf-8 -*-
"""fe_agent/xlsx_yaz.py — bagimliliksiz .xlsx (OOXML) ureticisi.

NEDEN KENDI URETICIMIZ VAR
  docx_yaz.py ile AYNI sebep: Dataiku kod ortaminda openpyxl ya da
  xlsxwriter kurulu OLMAYABILIR ve kurulmasi platform ekibinden gecmeyi
  gerektirir. Degisken listesini Excel'e indirmek kullanicinin sozluk
  teyidinden cikardigi ciktinin kendisi; kurulu olmayan bir pakete bagli
  kalamaz.

NEDEN "VARSA openpyxl KULLAN" YOK
  Iki kod yolu iki ayri hata kaynagidir: gelistirici makinesinde paket
  kurulu oldugu icin hic denenmemis yol, uretimde ilk kez calisir.
  Tek yol var: burasi. openpyxl YALNIZCA testte, uretileni DOGRULAMAK
  icin kullanilir.

URETILEN PAKET
  Tek sayfali, minimum ama GECERLI bir SpreadsheetML paketi:
    [Content_Types].xml, _rels/.rels, xl/workbook.xml,
    xl/_rels/workbook.xml.rels, xl/styles.xml, xl/worksheets/sheet1.xml
  Excel, LibreOffice Calc, Google Sheets ve openpyxl acar.

METINLER NEDEN "inlineStr"
  Paylasilan dize tablosu (sharedStrings) yerine satir ici metin
  kullaniliyor. Iki kazanci var: parca sayisi azaliyor ve — onemlisi —
  hicbir hucre FORMUL olarak yorumlanmiyor. '=', '+', '-', '@' ile
  baslayan bir sozluk tanimi, formul hucresi olsaydi Excel'de calisan
  bir ifadeye donusurdu (CSV enjeksiyonunun Excel karsiligi).
"""

import io
import zipfile
from xml.sax.saxutils import escape

# Tek hucreye sigdirilan en uzun metin. Excel'in kendi siniri 32.767;
# bunun altinda kesiyoruz ki dosya her zaman acilsin.
HUCRE_SINIRI = 4000

# Varsayilan ve en genis kolon genisligi (Excel "karakter" birimi).
KOLON_GENISLIK = 18
KOLON_GENISLIK_MAKS = 60

# cellXfs sirasi (styles.xml ile AYNI olmak zorunda)
BICIM_DUZ = 0
BICIM_BASLIK = 1
BICIM_YUZDE = 2

SAYFA_ADI_SINIRI = 31
# Excel'in sayfa adinda yasakladigi karakterler.
SAYFA_YASAK = set(r"[]:*?/\\")

MIME = ("application/vnd.openxmlformats-officedocument."
        "spreadsheetml.sheet")


def _temiz(metin):
    """XML'in kabul etmedigi denetim karakterlerini atar, kirpar, kacirir."""
    s = "" if metin is None else str(metin)
    s = "".join(c for c in s
                if c in "\t\n\r" or ord(c) >= 32)
    if len(s) > HUCRE_SINIRI:
        s = s[:HUCRE_SINIRI - 1] + "…"
    return escape(s)


def _sutun_adi(i):
    """0 -> A, 25 -> Z, 26 -> AA."""
    ad = ""
    i = int(i)
    while True:
        ad = chr(ord("A") + (i % 26)) + ad
        i = i // 26 - 1
        if i < 0:
            return ad


def _sayi_mi(v):
    """Sayisal hucre mi? bool SAYI DEGIL: True'yu 1 diye yazmak,
    'süreç dışı' bayragini tabloda 1/0 olarak gosterirdi."""
    if isinstance(v, bool) or v is None:
        return False
    if isinstance(v, (int, float)):
        # NaN / sonsuz: Excel bunlari kabul etmez, metne duseriz
        return v == v and v not in (float("inf"), float("-inf"))
    return False


def _hucre(sutun, satir_no, deger, yuzde_mi=False):
    ref = "%s%d" % (_sutun_adi(sutun), satir_no)
    if deger is None or deger == "":
        return '<c r="%s"/>' % ref
    if _sayi_mi(deger):
        bicim = BICIM_YUZDE if yuzde_mi else BICIM_DUZ
        return '<c r="%s" s="%d"><v>%s</v></c>' % (ref, bicim, repr(float(deger)))
    return ('<c r="%s" t="inlineStr"><is><t xml:space="preserve">%s</t>'
            '</is></c>' % (ref, _temiz(deger)))


def _baslik_hucresi(sutun, deger):
    return ('<c r="%s1" s="%d" t="inlineStr"><is><t>%s</t></is></c>'
            % (_sutun_adi(sutun), BICIM_BASLIK, _temiz(deger)))


def _sayfa_adi(ad):
    temiz = "".join(c for c in str(ad or "Sayfa1") if c not in SAYFA_YASAK)
    temiz = temiz.strip("'") or "Sayfa1"
    return escape(temiz[:SAYFA_ADI_SINIRI])


def _genislikler(kolonlar, satirlar):
    """Kolon genisligi BASLIK ve ILK SATIRLARA gore. Butun satirlari
    taramak 1.042 satirda gereksiz; ilk 200 satir bicim icin yeterli."""
    gen = []
    for i, bas in enumerate(kolonlar):
        en = len(str(bas or ""))
        for s in satirlar[:200]:
            if i < len(s) and s[i] is not None:
                en = max(en, len(str(s[i])))
        gen.append(min(max(en + 2, KOLON_GENISLIK), KOLON_GENISLIK_MAKS))
    return gen


STILLER = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<styleSheet xmlns="http://schemas.openxmlformats.org/'
    'spreadsheetml/2006/main">'
    '<fonts count="2">'
    '<font><sz val="11"/><name val="Calibri"/></font>'
    '<font><b/><sz val="11"/><color rgb="FF1F1F1F"/>'
    '<name val="Calibri"/></font>'
    '</fonts>'
    '<fills count="3">'
    '<fill><patternFill patternType="none"/></fill>'
    '<fill><patternFill patternType="gray125"/></fill>'
    '<fill><patternFill patternType="solid">'
    '<fgColor rgb="FFEFEFEF"/><bgColor indexed="64"/></patternFill></fill>'
    '</fills>'
    '<borders count="1"><border><left/><right/><top/><bottom/>'
    '<diagonal/></border></borders>'
    '<cellStyleXfs count="1">'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>'
    '</cellStyleXfs>'
    # SIRA cellXfs indeksidir: 0 duz, 1 baslik, 2 yuzde (numFmtId 10 = 0.00%)
    '<cellXfs count="3">'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0"'
    ' applyFont="1" applyFill="1"/>'
    '<xf numFmtId="10" fontId="0" fillId="0" borderId="0" xfId="0"'
    ' applyNumberFormat="1"/>'
    '</cellXfs>'
    '<cellStyles count="1">'
    '<cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
    '</styleSheet>'
)

ICERIK_TURLERI = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
    'content-types">'
    '<Default Extension="rels" ContentType="application/'
    'vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" ContentType="application/'
    'vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/'
    'vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    '<Override PartName="/xl/styles.xml" ContentType="application/'
    'vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
    '</Types>'
)

KOK_ILISKI = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
    'relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
    'officeDocument/2006/relationships/officeDocument"'
    ' Target="xl/workbook.xml"/>'
    '</Relationships>'
)

KITAP_ILISKI = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
    'relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
    'officeDocument/2006/relationships/worksheet"'
    ' Target="worksheets/sheet1.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/'
    'officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    '</Relationships>'
)


def _kitap(sayfa_adi):
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/'
        'spreadsheetml/2006/main"'
        ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/'
        'relationships">'
        '<sheets><sheet name="%s" sheetId="1" r:id="rId1"/></sheets>'
        '</workbook>' % sayfa_adi)


def _sayfa(kolonlar, satirlar, yuzde_sutunlari):
    parcalar = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/'
        'spreadsheetml/2006/main">',
        # Baslik satiri kaydirmada sabit kalsin: 1.042 satirda hangi
        # kolona baktigini hatirlamak gerekmiyor.
        '<sheetViews><sheetView workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft"'
        ' state="frozen"/></sheetView></sheetViews>',
    ]
    gen = _genislikler(kolonlar, satirlar)
    if gen:
        parcalar.append('<cols>')
        for i, g in enumerate(gen):
            parcalar.append('<col min="%d" max="%d" width="%d"'
                            ' customWidth="1"/>' % (i + 1, i + 1, g))
        parcalar.append('</cols>')

    parcalar.append('<sheetData>')
    parcalar.append('<row r="1">%s</row>'
                    % "".join(_baslik_hucresi(i, b)
                              for i, b in enumerate(kolonlar)))
    for n, satir in enumerate(satirlar, start=2):
        hucreler = "".join(
            _hucre(i, n, deger, yuzde_mi=(i in yuzde_sutunlari))
            for i, deger in enumerate(satir))
        parcalar.append('<row r="%d">%s</row>' % (n, hucreler))
    parcalar.append('</sheetData>')

    if kolonlar:
        parcalar.append('<autoFilter ref="A1:%s%d"/>'
                        % (_sutun_adi(len(kolonlar) - 1),
                           len(satirlar) + 1))
    parcalar.append('</worksheet>')
    return "".join(parcalar)


def tablo_xlsx(kolonlar, satirlar, sayfa_adi="Sayfa1", yuzde_sutunlari=()):
    """Tek sayfalik .xlsx uretir; bayt dizisi doner.

    kolonlar        : baslik metinleri listesi
    satirlar        : satir listesi; her satir hucre listesi
                      (metin / sayi / None). Eksik hucreler bos kalir.
    yuzde_sutunlari : yuzde bicimiyle yazilacak SUTUN INDISLERI (0 tabanli).
                      Deger 0-1 araligindaki oran olarak verilmeli;
                      Excel %%'yi kendisi ekler.
    """
    kolonlar = list(kolonlar or [])
    satirlar = [list(s) for s in (satirlar or [])]
    yuzde = set(int(i) for i in (yuzde_sutunlari or ()))

    tampon = io.BytesIO()
    # ZIP_DEFLATED: 1.042 satirlik tablo sikistirilmadan gereksiz buyuk.
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ICERIK_TURLERI)
        z.writestr("_rels/.rels", KOK_ILISKI)
        z.writestr("xl/workbook.xml", _kitap(_sayfa_adi(sayfa_adi)))
        z.writestr("xl/_rels/workbook.xml.rels", KITAP_ILISKI)
        z.writestr("xl/styles.xml", STILLER)
        z.writestr("xl/worksheets/sheet1.xml",
                   _sayfa(kolonlar, satirlar, yuzde))
    return tampon.getvalue()
