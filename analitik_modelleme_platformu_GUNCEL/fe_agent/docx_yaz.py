# -*- coding: utf-8 -*-
"""fe_agent/docx_yaz.py — bagimliliksiz .docx (OOXML) ureticisi.

NEDEN KENDI URETICIMIZ VAR
  Dataiku kod ortaminda python-docx kurulu OLMAYABILIR ve kurulmasi
  platform ekibinden gecmeyi gerektirir. Dokuman indirme bir yan ozellik
  degil, calismanin ciktisi; kurulu olmayan bir pakete bagli kalamaz.
  Uretilen paket minimum ama GECERLI bir OOXML paketidir; Word, LibreOffice
  ve python-docx acar.

NEDEN "VARSA python-docx KULLAN" YOK
  Iki kod yolu iki ayri hata kaynagidir: gelistirici makinesinde paket
  kurulu oldugu icin denenmemis bir yol, uretimde ilk kez calisir. Tek yol
  var: burasi. python-docx YALNIZCA testte, uretileni DOGRULAMAK icin
  kullanilir.

BLOK SOZLUGU (dokuman.py ile AYNI kelimeler)
  {"tur": "belge_basligi", "metin": ...}   belgenin adi (Title)
  {"tur": "baslik",        "metin": ...}   bolum basligi (Heading 1)
  {"tur": "alt_baslik",    "metin": ...}   ara baslik  (Heading 2)
  {"tur": "paragraf",      "metin": ..., "kalin": bool}  duz paragraf
      "kalin" istege baglidir (teslim damgasi); ayri bir blok turu
      DEGILDIR, on yuz bayragi gormezden gelip paragrafi yine cizer.
  {"tur": "liste",         "ogeler": [...]} madde listesi
  {"tur": "tablo",  "baslik":..., "kolonlar": [...], "satirlar": [[...]]}
  {"tur": "bos",           "metin": ...}   paragraf gibi cizilir

Taninmayan tur SESSIZCE ATILMAZ: metni varsa paragraf olarak yazilir.
Dokumanin bir parcasini kaybetmektense bicimsiz gostermek yeglenir.
"""

import datetime
import io
import zipfile
from xml.sax.saxutils import escape, quoteattr

# Word'un cizebilecegi metin genisligi (twip). A4 - 2 cm kenar boslugu.
SAYFA_GENISLIK = 9026

# Tek bir hucreye / paragrafa sigdirilan en uzun metin. Kullanici
# duzenlemesi ya da bozuk bir alan megabaytlarca metin tasiyabilir;
# Word'u kilitleyen bir dosya uretmektense metni acikca kirpiyoruz.
EN_UZUN_METIN = 20000
KIRPMA_ISARETI = " […]"

_NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
       ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/'
       'relationships"')


# ===========================================================================
# METIN GUVENLIGI
# ===========================================================================
def _temiz(metin):
    """XML'e yazilabilir metin.

    XML 1.0 kontrol karakterlerinin cogunu KABUL ETMEZ (yalnizca \\t \\n \\r
    gecerlidir). Veri setinden gelen bir alanda tek bir 0x00 varsa dosya
    Word tarafindan "bozuk" diye reddedilir — hatanin kaynagini bulmak
    imkansiza yakindir. Bu yuzden gecersiz karakterler burada dusuruluyor."""
    if metin is None:
        return ""
    if not isinstance(metin, str):
        metin = str(metin)
    if len(metin) > EN_UZUN_METIN:
        metin = metin[:EN_UZUN_METIN] + KIRPMA_ISARETI
    return "".join(
        k for k in metin
        if k in "\t\n\r" or (0x20 <= ord(k) <= 0xD7FF)
        or (0xE000 <= ord(k) <= 0xFFFD) or ord(k) >= 0x10000)


def _kacis(metin):
    """& < > ve " kacisi. Turkce karakterler DOKUNULMADAN gecer; dosya
    UTF-8 yazildigi icin kacisa gerek yok, kacirmak 'Ã¶' uretirdi."""
    return escape(_temiz(metin), {'"': "&quot;"})


def _kosu(metin, kalin=False):
    """Tek bir <w:r>. Satir sonu <w:br/> olur; aksi halde \\n sessizce
    kaybolur ve iki ayri satir tek satir gibi gorunur."""
    ozellik = "<w:rPr><w:b/></w:rPr>" if kalin else ""
    parcalar = []
    for i, satir in enumerate(_temiz(metin).split("\n")):
        if i:
            parcalar.append("<w:br/>")
        parcalar.append('<w:t xml:space="preserve">%s</w:t>' % _kacis(satir))
    return "<w:r>%s%s</w:r>" % (ozellik, "".join(parcalar))


def _paragraf(metin, stil=None, kalin=False):
    ozellik = ('<w:pPr><w:pStyle w:val=%s/></w:pPr>' % quoteattr(stil)) \
        if stil else ""
    return "<w:p>%s%s</w:p>" % (ozellik, _kosu(metin, kalin))


def _madde(metin):
    return ('<w:p><w:pPr><w:pStyle w:val="ListParagraph"/>'
            '<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>'
            '</w:pPr>%s</w:p>' % _kosu(metin))


def _hucre(metin, genislik, kalin=False):
    return ('<w:tc><w:tcPr><w:tcW w:w="%d" w:type="dxa"/></w:tcPr>%s</w:tc>'
            % (genislik, _paragraf(metin, kalin=kalin)))


def _tablo(blok):
    """Basit tablo: baslik satiri + veri satirlari.

    Duzensiz satirlar (kolon sayisindan kisa/uzun) BOZUK TABLO uretir;
    Word bunlari cizemez. Satirlar kolon sayisina gore doldurulur/kirpilir —
    eksik veri bos hucre olur, fazlasi dusurulur."""
    kolonlar = [str(k) for k in (blok.get("kolonlar") or [])]
    if not kolonlar:
        return ""
    genislik = max(SAYFA_GENISLIK // len(kolonlar), 400)

    parcalar = []
    baslik = blok.get("baslik")
    if baslik:
        # Tablonun basligi bir ARA BASLIKTIR: bolum basliginin altinda,
        # kendi basina bir alt bolum acar. Ayri bir "tablo basligi" stili
        # tanimlamak ayni isi yapan ikinci bir seviye demekti.
        parcalar.append(_paragraf(baslik, stil=_STILLER["alt_baslik"]))

    izgara = "".join('<w:gridCol w:w="%d"/>' % genislik for _ in kolonlar)
    satirlar = [
        # tblHeader: tablo sayfa asarsa baslik satiri her sayfada tekrarlar.
        '<w:tr><w:trPr><w:tblHeader/></w:trPr>%s</w:tr>'
        % "".join(_hucre(k, genislik, kalin=True) for k in kolonlar)]

    for satir in (blok.get("satirlar") or []):
        if not isinstance(satir, (list, tuple)):
            satir = [satir]
        hucreler = list(satir[:len(kolonlar)])
        hucreler += [""] * (len(kolonlar) - len(hucreler))
        satirlar.append("<w:tr>%s</w:tr>"
                        % "".join(_hucre(h, genislik) for h in hucreler))

    parcalar.append(
        '<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/>'
        '<w:tblW w:w="%d" w:type="dxa"/></w:tblPr>'
        '<w:tblGrid>%s</w:tblGrid>%s</w:tbl>'
        % (SAYFA_GENISLIK, izgara, "".join(satirlar)))
    # Tablodan hemen sonra bos paragraf: iki tablo pes pese gelirse Word
    # onlari tek tablo olarak birlestirir.
    parcalar.append("<w:p/>")
    return "".join(parcalar)


_STILLER = {"belge_basligi": "Title", "baslik": "Heading1",
            "alt_baslik": "Heading2"}


def _blok_xml(blok):
    if not isinstance(blok, dict):
        return _paragraf(blok)
    tur = blok.get("tur")
    if tur == "tablo":
        return _tablo(blok)
    if tur == "liste":
        return "".join(_madde(o) for o in (blok.get("ogeler") or []))
    # "kalin" YENI BIR BLOK TURU DEGIL, paragrafin bir bayragidir: teslim
    # damgasi Word'de goze carpmali ama ekranda paragraf olarak cizilmeye
    # devam etmeli. Besinci bir blok turu on yuzde SESSIZCE kaybolurdu.
    return _paragraf(blok.get("metin"), stil=_STILLER.get(tur),
                     kalin=bool(blok.get("kalin")))


# ===========================================================================
# PAKET PARCALARI
# ===========================================================================
_ICERIK_TIPLERI = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>"""

_KOK_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""

_BELGE_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>
</Relationships>"""

_NUMARALAMA = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering %s>
<w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="hybridMultilevel"/>
<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/>
<w:lvlText w:val="•"/><w:lvlJc w:val="left"/>
<w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr></w:lvl>
</w:abstractNum>
<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
</w:numbering>""" % _NS


def _stil(kimlik, ad, tur="paragraph", ek="", varsayilan=False):
    """Tek bir <w:style>.

    varsayilan=True (Normal stili) SART: hicbir stil varsayilan
    isaretlenmezse pStyle tasimayan paragraflarin stili cozulemiyor ve
    okuyucular (python-docx dahil) stil alanini None goruyor."""
    return ('<w:style w:type="%s"%s w:styleId=%s><w:name w:val=%s/>%s'
            '</w:style>'
            % (tur, ' w:default="1"' if varsayilan else "",
               quoteattr(kimlik), quoteattr(ad), ek))


_STIL_TANIMLARI = ("""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles %s><w:docDefaults><w:rPrDefault><w:rPr>
<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/>
<w:sz w:val="22"/></w:rPr></w:rPrDefault></w:docDefaults>""" % _NS
    + _stil("Normal", "Normal", varsayilan=True)
    + _stil("Title", "Title",
            ek='<w:pPr><w:spacing w:after="240"/></w:pPr>'
               '<w:rPr><w:b/><w:sz w:val="48"/></w:rPr>')
    + _stil("Heading1", "heading 1",
            ek='<w:pPr><w:outlineLvl w:val="0"/>'
               '<w:spacing w:before="360" w:after="120"/></w:pPr>'
               '<w:rPr><w:b/><w:sz w:val="32"/></w:rPr>')
    + _stil("Heading2", "heading 2",
            ek='<w:pPr><w:outlineLvl w:val="1"/>'
               '<w:spacing w:before="240" w:after="80"/></w:pPr>'
               '<w:rPr><w:b/><w:sz w:val="26"/></w:rPr>')
    + _stil("ListParagraph", "List Paragraph",
            ek='<w:pPr><w:ind w:left="720"/></w:pPr>')
    + _stil("TableGrid", "Table Grid", tur="table",
            ek='<w:tblPr><w:tblBorders>'
               + "".join('<w:%s w:val="single" w:sz="4" w:color="BFBFBF"/>' % k
                         for k in ("top", "left", "bottom", "right",
                                   "insideH", "insideV"))
               + '</w:tblBorders></w:tblPr>')
    + "</w:styles>")

_UYGULAMA = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
<Application>Analitik Modelleme Platformu</Application>
</Properties>"""


def _cekirdek(baslik, zaman):
    damga = zaman.strftime("%Y-%m-%dT%H:%M:%SZ")
    return ("""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/\
metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" \
xmlns:dcterms="http://purl.org/dc/terms/" \
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<dc:title>%s</dc:title>
<dcterms:created xsi:type="dcterms:W3CDTF">%s</dcterms:created>
<dcterms:modified xsi:type="dcterms:W3CDTF">%s</dcterms:modified>
</cp:coreProperties>""" % (_kacis(baslik), damga, damga))


def _belge(bloklar):
    govde = "".join(_blok_xml(b) for b in (bloklar or []))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<w:document %s><w:body>%s'
            '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
            '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" '
            'w:left="1134"/></w:sectPr></w:body></w:document>'
            % (_NS, govde))


# ===========================================================================
# GIRIS NOKTASI
# ===========================================================================
def belge_yaz(baslik, bloklar):
    """Blok listesinden .docx dosyasinin HAM BAYTLARINI uretir.

    baslik yalnizca dosya ozelligine (Word'un "Baslik" alani) yazilir;
    belgenin gorunen adi icin listeye "belge_basligi" blogu koyun."""
    zaman = datetime.datetime.now()
    parcalar = [
        ("[Content_Types].xml", _ICERIK_TIPLERI),
        ("_rels/.rels", _KOK_RELS),
        ("docProps/core.xml", _cekirdek(baslik, zaman)),
        ("docProps/app.xml", _UYGULAMA),
        ("word/_rels/document.xml.rels", _BELGE_RELS),
        ("word/styles.xml", _STIL_TANIMLARI),
        ("word/numbering.xml", _NUMARALAMA),
        ("word/document.xml", _belge(bloklar)),
    ]

    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as paket:
        for ad, icerik in parcalar:
            paket.writestr(ad, icerik.encode("utf-8"))
    return tampon.getvalue()
