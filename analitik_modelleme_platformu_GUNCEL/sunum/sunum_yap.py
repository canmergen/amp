# -*- coding: utf-8 -*-
"""sunum_yap.py — Platformun tanitim sunumunu (.pptx) ureten betik.

NE YAPAR
  Tanitim sunumunu bastan uretir: kapak, 13 icerik slayti ve kapanis. Butun kutular, oklar ve yazilar PowerPoint'in kendi
  ogeleridir, PowerPoint'te duzenlenebilir. Robot gorselleri platformun kendi
  gorsel klasorunden (LLM_WEBAPP_GORSEL) okunup sunuma gomulur. Her slaytin
  konusmaci notu da yazilir.

GORSELLER
  Hangi dosyanin nerede kullanildigi asagidaki GORSELLER sozlugundedir.
  Dosya adi buyuk kucuk harf, alt cizgi ve
  uzanti (png, jpg) farkina takilmadan bulunur. Bir gorsel
  bulunamazsa sunum yine uretilir: kapakta yerinde resim yer tutucusu kalir,
  son slaytta yeri bos kalir. Calisma sonunda hangi
  gorselin bulundugu ekrana yazilir.
  Pillow (PIL) kuruluysa gorsellerin saydam kenarlari kirpilir ve buyuk
  gorseller kucultulur; kurulu degilse gorseller oldugu gibi gomulur.
  Gorsel yalniz iki yerde kullanilir: kapakta ve son slaytta. KAPANIS ayariyla
  son slayt kapatilabilir.

NEDEN BAGIMLILIKSIZ
  fe_agent/docx_yaz.py ve xlsx_yaz.py ile AYNI sebep: Dataiku kod ortaminda
  python-pptx kurulu OLMAYABILIR ve kurulmasi platform ekibinden gecmeyi
  gerektirir. Bu betik yalniz standart kutuphaneyi kullanir; .pptx paketini
  (OOXML: zip icinde XML parcalari) kendisi yazar. python-pptx YALNIZCA
  testte, uretileni DOGRULAMAK icin kullanildi.

NASIL CALISTIRILIR
  1. Dataiku Python defteri (notebook): dosyanin tamamini bir hucreye
     yapistirip calistirin. Gorseller GORSEL_KLASOR'den okunur. KLASOR bos
     ise ciktida bir indirme baglantisi gorunur.
  2. Dataiku Python recipe ya da baglanti calismazsa: asagidaki KLASOR
     degiskenine bir managed folder adi (ya da kimligi) yazin; dosya o
     klasore yazilir, klasor ekranindan indirilir. Recipe'te bu klasor
     recipe'in CIKTISI, GORSEL_KLASOR de GIRDISI olarak eklenmis olmalidir
     (Dataiku, recipe'in girdisi ya da ciktisi olmayan klasore erisime izin
     vermez).
  3. Proje kutuphanesine (lib/python) konursa, defter ya da recipe'ten:
         import sunum_yap
         sunum_yap.kaydet(sunum_yap.uret(), "KLASOR_ADI")
  4. Bilgisayarda: python sunum_yap.py [cikti.pptx] [gorsel_dizini]
     Gorsel dizini verilmezse betigin yanindaki "gorseller" dizinine bakilir.

DUZENLEME
  Metinler ve yerlesim dosyanin sonundaki SLAYTLAR bolumundedir. Olculer inc
  cinsindendir (slayt 13,333 x 7,5 inc; 16:9). Kutunun yazisi kutudan ayri bir
  metin kutusudur (kutu + ustunde yazi).
"""

import base64
import datetime
import io
import os
import struct
import sys
import unicodedata
import uuid
import zipfile
from xml.sax.saxutils import escape, quoteattr

# ===========================================================================
# AYARLAR
# ===========================================================================
# Dataiku managed folder adi ya da kimligi (or. "SUNUM"). None ise dosya
# calisma dizinine yazilir; defterde ayrica indirme baglantisi gosterilir.
KLASOR = None
DOSYA = "Akilli_Modelleme_Platformu_Sunum.pptx"

# Gorsellerin okundugu Dataiku managed folder (webapp ile ayni klasor).
GORSEL_KLASOR = "LLM_WEBAPP_GORSEL"
# Dataiku disinda calisirken gorsellerin bulundugu dizin. None ise betigin
# yanindaki "gorseller" dizinine bakilir. Dolu ise Dataiku klasoru yerine
# HER ZAMAN bu dizin kullanilir.
GORSEL_DIZIN = None
# Sunumdaki yeri -> dosya adi. Dosyayi degistirmek icin yalniz burayi duzenleyin.
GORSELLER = {
    "kapak": "robot_header.png",          # kapakta, basligin ustunde, ortada ve buyuk
    "kapanis": "robot_alt.png",           # son slaytta, en altta, alt kenara yapisik
}
KAPANIS = True                             # sona tesekkur slaydi eklensin mi

# Renkler (onaltilik, # isareti yok). Kirmizi ve pembe platformun kendi
# renkleridir (webapp/style.css: --kirmizi, --kirmizi-koyu, --pembe-secili).
KIR, KIR2 = "D51115", "A00D10"            # kirmizi, koyu kirmizi
KOYU, GRI, SOLUK = "262626", "595959", "A6A6A6"
ACIK, PEMBE, BEYAZ = "F2F2F2", "FBE4E5", "FFFFFF"

EMU = 914400                               # 1 inc
SLAYT_CX, SLAYT_CY = 12192000, 6858000     # 13,333 x 7,5 inc
NOT_CX, NOT_CY = 6858000, 9144000
DIL = "tr-TR"

_NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
_NS3 = 'xmlns:a="%s" xmlns:r="%s" xmlns:p="%s"' % (_NS_A, _NS_R, _NS_P)
_BAS = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
_ILISKI = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
_ICERIK = "application/vnd.openxmlformats-officedocument.presentationml."
_GRUP = ('<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
         '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
         '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>')
_RENK_ESLEME = ('bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" '
                'accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" '
                'hlink="hlink" folHlink="folHlink"')
_ALAN_NO = "{B6F15528-21DE-4FAA-801E-634DDDAF4B2B}"     # slayt numarasi alani


# ===========================================================================
# METIN GUVENLIGI VE OLCU
# ===========================================================================
def _temiz(metin):
    """XML'e yazilabilir metin: XML 1.0'in kabul etmedigi kontrol
    karakterleri dusurulur (tek bir 0x00 dosyayi "bozuk" yapar)."""
    if metin is None:
        return ""
    if not isinstance(metin, str):
        metin = str(metin)
    return "".join(
        k for k in metin
        if k in "\t\n\r" or (0x20 <= ord(k) <= 0xD7FF)
        or (0xE000 <= ord(k) <= 0xFFFD) or ord(k) >= 0x10000)


def _kacis(metin):
    """Eleman metni icin & < > kacisi. Turkce karakterlere dokunulmaz."""
    return escape(_temiz(metin))


def _oz(metin):
    """Oznitelik degeri, tirnaklariyla."""
    return quoteattr(_temiz(metin))


def _emu(inc):
    return int(round(inc * EMU))


# ===========================================================================
# METIN: PARCA (R), PARAGRAF (P)
# ===========================================================================
class R(object):
    """Metin parcasi. Verilmeyen ozellik kutunun varsayilanindan gelir."""

    def __init__(self, metin, kalin=None, egik=None, renk=None, boy=None, yazitipi=None):
        self.metin = metin
        self.kalin = kalin
        self.egik = egik
        self.renk = renk
        self.boy = boy
        self.yazitipi = yazitipi


class P(object):
    """Paragraf: parcalar (str ya da R). madde=True ise madde imli."""

    def __init__(self, *parcalar, **oz):
        self.parcalar = [p if isinstance(p, R) else R(p) for p in parcalar]
        self.madde = bool(oz.get("madde", False))
        self.hiza = oz.get("hiza")


def maddeler(liste):
    """Her ogesi madde imli bir paragraf."""
    return [P(m, madde=True) for m in liste]


def _paragraflar(icerik):
    """icerik: str | R | P ya da bunlarin listesi. Listenin her ogesi bir
    paragraftir; ogesi liste olan paragraf birden cok parcalidir."""
    if isinstance(icerik, (R, P)) or not isinstance(icerik, (list, tuple)):
        icerik = [icerik]
    sonuc = []
    for oge in icerik:
        if isinstance(oge, P):
            sonuc.append(oge)
        elif isinstance(oge, (list, tuple)):
            sonuc.append(P(*oge))
        else:
            sonuc.append(P(oge))
    return sonuc


def _govde(icerik, boy, renk, kalin, egik, hiza, dikey, yazitipi, bosluk):
    """Metin kutusunun <p:txBody> ogesi. Ic bosluk sifir; paragraf basina
    TEK <a:pPr> yazilir (sema bunu ister)."""
    x = ['<p:txBody><a:bodyPr wrap="square" lIns="0" tIns="0" rIns="0" bIns="0" '
         'rtlCol="0" anchor="%s"/><a:lstStyle/>' % dikey]
    ara = ('<a:spcAft><a:spcPts val="%d"/></a:spcAft>' % int(round(bosluk * 100))) if bosluk else ""
    for p in _paragraflar(icerik):
        h = p.hiza or hiza
        if p.madde:
            x.append('<a:p><a:pPr marL="127000" indent="-127000" algn="%s">%s'
                     '<a:buChar char="&#8226;"/></a:pPr>' % (h, ara))
        else:
            x.append('<a:p><a:pPr marL="0" indent="0" algn="%s">%s<a:buNone/></a:pPr>' % (h, ara))
        son = boy
        for r in p.parcalar:
            b = boy if r.boy is None else r.boy
            k = kalin if r.kalin is None else r.kalin
            e = egik if r.egik is None else r.egik
            yt = r.yazitipi or yazitipi
            oz = ' lang="%s" sz="%d"' % (DIL, int(round(b * 100)))
            if k:
                oz += ' b="1"'
            if e:
                oz += ' i="1"'
            ic = '<a:solidFill><a:srgbClr val="%s"/></a:solidFill>' % (r.renk or renk)
            if yt:
                ic += '<a:latin typeface=%s/><a:cs typeface=%s/>' % (_oz(yt), _oz(yt))
            x.append('<a:r><a:rPr%s dirty="0">%s</a:rPr><a:t>%s</a:t></a:r>' % (oz, ic, _kacis(r.metin)))
            son = b
        x.append('<a:endParaRPr lang="%s" sz="%d" dirty="0"/></a:p>' % (DIL, int(round(son * 100))))
    x.append('</p:txBody>')
    return "".join(x)


def _ilk_metin(icerik):
    p = _paragraflar(icerik)
    return (p[0].parcalar[0].metin if p and p[0].parcalar else "").strip()


# ===========================================================================
# GORSELLER
# ===========================================================================
class Gorsel(object):
    """Sunuma gomulecek bir resim."""

    def __init__(self, veri, uzanti, en, boy, saydam, kaynak, alt_kesik=False):
        self.veri = veri              # dosyanin baytlari
        self.uzanti = uzanti          # "png" ya da "jpeg"
        self.en = en                  # piksel
        self.boy = boy
        self.saydam = saydam          # saydamlik bilgisi var mi
        self.kaynak = kaynak          # okundugu yol (bilgi satiri icin)
        self.alt_kesik = alt_kesik    # cizim gorselin alt kenarinda kesiliyor mu (Pillow varsa bilinir)

    @property
    def oran(self):
        return self.en / float(self.boy)


# Gorsel basina hazirlik: (saydam kenarlar kirpilsin mi, uzun kenarin en cok
# kac piksel olacagi).
_HAZIRLIK = {"kapak": (True, 2200), "kapanis": (True, 2400)}
_UZANTILAR = (".png", ".jpg", ".jpeg")
_onbellek = {}                 # mantiksal ad -> Gorsel ya da None
_neden = {}                    # mantiksal ad -> gorsel neden kullanilamadi
_kaynak_onbellek = []          # [(ad, yollar, okuyucu)] ya da [None]
_gorsel_notlari = []           # okuma sirasinda biriken uyarilar


def gorselleri_sifirla():
    """Gorsel onbellegini bosaltir; ayar degistirip yeniden uretmeden once cagrilir."""
    _onbellek.clear()
    _neden.clear()
    del _kaynak_onbellek[:]
    del _gorsel_notlari[:]


def _resim_bilgi(veri):
    """(uzanti, en, boy, saydam) doner; PNG ve JPEG disindaki tur icin None."""
    if veri[:8] == b"\x89PNG\r\n\x1a\n" and veri[12:16] == b"IHDR":
        en, boy = struct.unpack(">II", veri[16:24])
        saydam = bytearray(veri[25:26])[0] in (4, 6)
        i = 8
        while not saydam and i + 8 <= len(veri):          # paletli PNG'de saydamlik tRNS parcasindadir
            uzunluk = struct.unpack(">I", veri[i:i + 4])[0]
            parca = veri[i + 4:i + 8]
            if parca == b"tRNS":
                saydam = True
            if parca in (b"IDAT", b"IEND"):
                break
            i += 12 + uzunluk
        return "png", en, boy, saydam
    if veri[:2] == b"\xff\xd8":
        bayt = bytearray(veri)
        i = 2
        while i + 9 < len(bayt):
            if bayt[i] != 0xFF:
                i += 1
                continue
            isaret = bayt[i + 1]
            if isaret == 0xFF:
                i += 1
                continue
            if isaret in (0x01, 0xD8) or 0xD0 <= isaret <= 0xD7:
                i += 2
                continue
            if 0xC0 <= isaret <= 0xCF and isaret not in (0xC4, 0xC8, 0xCC):
                boy, en = struct.unpack(">HH", veri[i + 5:i + 9])
                return "jpeg", en, boy, False
            i += 2 + struct.unpack(">H", veri[i + 2:i + 4])[0]
    return None


def _hazirla(veri, kirp, azami):
    """Pillow varsa gorseli sunuma hazirlar ve (veri, alt_kesik) doner: saydamligi
    olmayan saydamlik kanalini atar, kirp ise saydam kenarlari kirpar, uzun kenari
    azami pikseli gecen gorseli kucultur. alt_kesik: cizim gorselin alt kenarina
    kadar iniyor mu (kenarda kesilmis bir cizim). Pillow yoksa ya da bir sorun
    cikarsa veriyi OLDUGU GIBI doner."""
    try:
        from PIL import Image
    except Exception:
        return veri, False
    try:
        resim = Image.open(io.BytesIO(veri))
        bicim = resim.format
        resim.load()
        degisti = False
        alt_kesik = False
        if bicim == "PNG" and resim.mode not in ("RGB", "RGBA"):
            resim = resim.convert("RGBA")
        if resim.mode == "RGBA":
            alfa = resim.split()[-1]
            if alfa.getextrema()[0] == 255:               # kanal var ama gorsel tumuyle opak
                resim = resim.convert("RGB")
                degisti = True
            else:
                kutu = alfa.point(lambda deger: 255 if deger > 8 else 0).getbbox()
                alt_kesik = bool(kutu) and kutu[3] == resim.size[1]
                if kirp and kutu and tuple(kutu) != (0, 0) + resim.size:
                    resim = resim.crop(kutu)
                    degisti = True
        if max(resim.size) > azami:
            olcek = azami / float(max(resim.size))
            resim = resim.resize((max(1, int(round(resim.size[0] * olcek))),
                                  max(1, int(round(resim.size[1] * olcek)))), Image.LANCZOS)
            degisti = True
        if not degisti:
            return veri, alt_kesik
        cikti = io.BytesIO()
        if bicim == "JPEG":
            resim.convert("RGB").save(cikti, "JPEG", quality=90)
        else:
            resim.save(cikti, "PNG", optimize=True)
        return cikti.getvalue(), alt_kesik
    except Exception:
        return veri, False


def _sade(ad):
    """Dosya adinin karsilastirma anahtari: uzanti, buyuk kucuk harf, alt cizgi,
    tire ve bosluk farki elenir ("Robot_Header.PNG" ile "robotheader.png" ayni)."""
    govde = os.path.splitext(os.path.basename(ad.replace("\\", "/")))[0]
    govde = unicodedata.normalize("NFC", govde).casefold()
    return "".join(harf for harf in govde if harf.isalnum())


def _eslesen(yollar, dosya):
    """yollar icinden dosya adina uyan yolu secer: once tam ad, sonra sade ad."""
    hedef = os.path.basename(dosya).casefold()
    for yol in yollar:
        if os.path.basename(yol.replace("\\", "/")).casefold() == hedef:
            return yol
    adaylar = [yol for yol in yollar
               if _sade(yol) == _sade(dosya) and os.path.splitext(yol)[1].lower() in _UZANTILAR]
    adaylar.sort(key=lambda yol: _UZANTILAR.index(os.path.splitext(yol)[1].lower()))
    return adaylar[0] if adaylar else None


def _yerel_dizin():
    try:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "gorseller")
    except NameError:                                     # defterde __file__ yoktur
        return os.path.join(os.getcwd(), "gorseller")


def _kaynak():
    """Gorsellerin okunacagi yer: (ad, yollar, okuyucu) ya da None. GORSEL_DIZIN
    dolu ise o dizin; degilse Dataiku klasoru; o da yoksa yerel "gorseller"."""
    if _kaynak_onbellek:
        return _kaynak_onbellek[0]
    sonuc = None
    if not GORSEL_DIZIN:
        try:
            import dataiku
        except ImportError:
            dataiku = None
        if dataiku is not None:
            try:
                klasor = dataiku.Folder(GORSEL_KLASOR)
                yollar = list(klasor.list_paths_in_partition())

                def klasorden(yol, klasor=klasor):
                    with klasor.get_download_stream(yol) as akis:
                        return akis.read()
                sonuc = ("managed folder %s" % GORSEL_KLASOR, yollar, klasorden)
            except Exception as hata:
                _gorsel_notlari.append("Görsel klasörü okunamadı (%s): %s" % (GORSEL_KLASOR, hata))
    if sonuc is None:
        dizin = GORSEL_DIZIN or _yerel_dizin()
        if os.path.isdir(dizin):
            def dizinden(yol):
                with open(yol, "rb") as f:
                    return f.read()
            sonuc = ("dizin %s" % dizin, [os.path.join(dizin, ad) for ad in sorted(os.listdir(dizin))], dizinden)
        elif GORSEL_DIZIN:
            _gorsel_notlari.append("Görsel dizini bulunamadı: %s" % dizin)
    _kaynak_onbellek.append(sonuc)
    return sonuc


def _gorsel(ad):
    """GORSELLER anahtarini Gorsel nesnesine cevirir; bulunamaz ya da okunamazsa None."""
    if ad in _onbellek:
        return _onbellek[ad]
    sonuc = None
    dosya = GORSELLER.get(ad)
    kaynak = _kaynak()
    neden = "%s bulunamadı" % dosya
    if dosya and kaynak:
        yol = _eslesen(kaynak[1], dosya)
        if yol is None:
            baska = [aday for aday in kaynak[1] if _sade(aday) == _sade(dosya)]
            if baska:
                neden = ("%s desteklenmeyen türde (PNG ya da JPEG olmalı)"
                         % os.path.basename(baska[0].replace("\\", "/")))
        else:
            dosya_adi = os.path.basename(yol.replace("\\", "/"))
            try:
                kirp, azami = _HAZIRLIK.get(ad, (False, 1600))
                veri, alt_kesik = _hazirla(kaynak[2](yol), kirp, azami)
                bilgi = _resim_bilgi(veri)
                if bilgi:
                    sonuc = Gorsel(veri, bilgi[0], bilgi[1], bilgi[2], bilgi[3], yol, alt_kesik)
                else:
                    neden = "%s PNG ya da JPEG olarak okunamadı" % dosya_adi
            except Exception as hata:
                neden = "%s okunamadı (%s)" % (dosya_adi, hata)
    _onbellek[ad] = sonuc
    if sonuc is None:
        _neden[ad] = neden
    return sonuc


def gorsel_raporu():
    """Hangi gorselin bulundugunu anlatan satirlar (calisma sonunda yazilir)."""
    kaynak = _kaynak()
    satirlar = ["Görsel kaynağı: %s" % (kaynak[0] if kaynak else "yok (Dataiku klasörü ya da görsel dizini bulunamadı)")]
    for ad in sorted(GORSELLER):
        g = _gorsel(ad)
        if g:
            satirlar.append("  %s: %s, %d x %d piksel, %d KB" % (ad, os.path.basename(g.kaynak.replace("\\", "/")),
                                                                g.en, g.boy, len(g.veri) // 1024))
        else:
            satirlar.append("  %s: %s; yeri boş bırakıldı" % (ad, _neden.get(ad, "yok")))
    try:
        from PIL import Image                             # noqa: F401 (yalniz var mi diye bakilir)
    except Exception:
        if any(_gorsel(ad) for ad in GORSELLER):
            satirlar.append("Pillow (PIL) bulunamadı: görseller kırpılmadan ve küçültülmeden gömüldü; dosya büyük olabilir.")
    return satirlar + list(_gorsel_notlari)


# ===========================================================================
# SEKIL XML'I
# ===========================================================================
def _cizgi_xml(cizgi, ucu_ok=False):
    """cizgi: None (cizgi yok) ya da (renk, kalinlik_pt, kesik_mi)."""
    if not cizgi:
        return '<a:ln><a:noFill/></a:ln>'
    renk, kalinlik, kesik = cizgi
    return ('<a:ln w="%d"><a:solidFill><a:srgbClr val="%s"/></a:solidFill><a:prstDash val="%s"/>%s</a:ln>'
            % (int(round(kalinlik * 12700)), renk, "dash" if kesik else "solid",
               '<a:tailEnd type="triangle"/>' if ucu_ok else ""))


_GOLGE = ('<a:effectLst><a:outerShdw blurRad="50800" dist="25400" dir="5400000" algn="bl" '
          'rotWithShape="0"><a:srgbClr val="000000"><a:alpha val="20000"/></a:srgbClr>'
          '</a:outerShdw></a:effectLst>')


def _sp(sid, ad, bicim, x, y, w, h, ic, govde="", metin_kutusu=False, cevir=""):
    """Tek bir <p:sp>. bicim: hazir geometri XML'i; ic: dolgu, cizgi, efekt."""
    return ('<p:sp><p:nvSpPr><p:cNvPr id="%d" name=%s/><p:cNvSpPr%s/><p:nvPr/></p:nvSpPr>'
            '<p:spPr><a:xfrm%s><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm>%s%s</p:spPr>%s</p:sp>'
            % (sid, _oz(ad), ' txBox="1"' if metin_kutusu else "", cevir,
               _emu(x), _emu(y), _emu(w), _emu(h), bicim, ic, govde))


def _geo(ad, ayar=None):
    if ayar is None:
        return '<a:prstGeom prst="%s"><a:avLst/></a:prstGeom>' % ad
    return '<a:prstGeom prst="%s"><a:avLst><a:gd name="adj" fmla="val %d"/></a:avLst></a:prstGeom>' % (ad, ayar)


def _dolgu(renk):
    return '<a:solidFill><a:srgbClr val="%s"/></a:solidFill>' % renk if renk else '<a:noFill/>'


def _resim_xml(sid, ad, rid, x, y, w, h, daire=False, cizgi=None, kirpma=None):
    """Tek bir <p:pic>. rid: slaydin iliski numarasi; kirpma: (sol, ust, sag, alt)
    binde yuz birimiyle kaynak kirpmasi; daire ise resim daire icinde gorunur."""
    kirp = ""
    if kirpma and any(kirpma):
        kirp = '<a:srcRect%s/>' % "".join(' %s="%d"' % (kenar, pay) for kenar, pay in zip("ltrb", kirpma) if pay)
    return ('<p:pic><p:nvPicPr><p:cNvPr id="%d" name=%s/><p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr>'
            '<p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="rId%d"/>%s<a:stretch><a:fillRect/></a:stretch>'
            '</p:blipFill><p:spPr><a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm>%s%s</p:spPr></p:pic>'
            % (sid, _oz(ad), rid, kirp, _emu(x), _emu(y), _emu(w), _emu(h),
               _geo("ellipse" if daire else "rect"), _cizgi_xml(cizgi) if cizgi else ""))


# Kutu turleri: (dolgu, cizgi, golge)
_TURLER = {
    "veri": (KIR, None, True),                       # veri ya da cikti
    "islem": (BEYAZ, (KIR, 1.5, False), False),      # kodun yaptigi islem
    "simdi": (BEYAZ, (KIR, 3.5, False), False),      # uzerinde calisilan
    "onay": (PEMBE, (KIR, 1.5, False), False),       # kullanici onayi
    "gri": (ACIK, None, False),                      # aciklama karti, yapay zeka
    "soluk": (BEYAZ, (SOLUK, 1.5, True), False),     # sirada (kesik gri)
    "cerceve": (BEYAZ, (SOLUK, 1.0, False), False),  # ince gri cerceve
}


# Adim tablosu (Slayt.adim_tablosu): sutun enleri (inc) ve sutunlar arasi bosluk
ADIM_BASLIKLARI = ("Adım", "Ne Yapılır", "Neden Gerekli", "Örnek")
ADIM_ENLER = (1.9, 3.75, 3.1, 3.28)
ADIM_ARA = 0.1


# ===========================================================================
# SLAYT
# ===========================================================================
class Slayt(object):
    """Bir slayt: sekiller sirayla eklenir. Olculer inc."""

    def __init__(self, yerlesim, bolum, baslik, ust=None):
        self.yerlesim = yerlesim          # "KAPAK", "AKIS" ya da "KAPANIS"
        self.bolum = bolum
        self.baslik = baslik
        self.ust = ust                    # AKIS: baslik altindaki cumle (verilmezse yazilmaz); KAPAK: birim satiri
        self.baslik_kutu = None           # (x, y, w, h): baslik yer tutucusunun bu slayttaki yeri (yerlesimdekini ezer)
        self.notlar = ""
        self.gorseller = []               # bu slayttaki gorseller, iliski sirasiyla
        self.kapak_gorseli = False        # KAPAK: gorsel kondu mu (konmadiysa resim yer tutucusu kalir)
        self._x = []
        self._sid = 3 if yerlesim == "AKIS" else 5      # ilk kimlikler yer tutucularin

    def _id(self):
        self._sid += 1
        return self._sid

    # ---- temel sekiller ---------------------------------------------------
    def kutu(self, x, y, w, h, tur, ad):
        """Kosesi yuvarlak kutu. tur: _TURLER anahtari."""
        dolgu, cizgi, golge = _TURLER[tur]
        ayar = min(50000, int(round(0.1 * 100000 / min(w, h))))
        self._x.append(_sp(self._id(), ad, _geo("roundRect", ayar), x, y, w, h,
                           _dolgu(dolgu) + _cizgi_xml(cizgi) + (_GOLGE if golge else "")))

    def dik(self, x, y, w, h, renk, ad):
        """Koseli, cizgisiz dolu dikdortgen."""
        self._x.append(_sp(self._id(), ad, _geo("rect"), x, y, w, h, _dolgu(renk) + _cizgi_xml(None)))

    def elips(self, cx, cy, d, dolgu, cizgi, ad):
        self._x.append(_sp(self._id(), ad, _geo("ellipse"), cx - d / 2.0, cy - d / 2.0, d, d,
                           _dolgu(dolgu) + _cizgi_xml(cizgi)))

    def hat(self, x1, y1, x2, y2, ad, renk=KIR, kalinlik=1.25, kesik=False, ucu_ok=False):
        """Duz cizgi; ucu_ok ise bitis ucunda ok basi."""
        cevir = (' flipH="1"' if x2 < x1 else "") + (' flipV="1"' if y2 < y1 else "")
        self._x.append(_sp(self._id(), ad, _geo("line"), min(x1, x2), min(y1, y2),
                           abs(x2 - x1), abs(y2 - y1),
                           '<a:noFill/>' + _cizgi_xml((renk, kalinlik, kesik), ucu_ok), cevir=cevir))

    def ok(self, x1, y1, x2, y2, ad="ok", renk=KIR):
        self.hat(x1, y1, x2, y2, ad, renk, 1.25, False, True)

    def yazi(self, icerik, x, y, w, h, boy=11, renk=KOYU, kalin=False, egik=False,
             hiza="ctr", dikey="ctr", yazitipi=None, bosluk=0):
        """Metin kutusu. hiza: l, ctr, r; dikey: t, ctr, b; bosluk: paragraf
        sonrasi bosluk (punto)."""
        ad = "yazı " + _ilk_metin(icerik)[:40]
        self._x.append(_sp(self._id(), ad, _geo("rect"), x, y, w, h, '<a:noFill/>',
                           _govde(icerik, boy, renk, kalin, egik, hiza, dikey, yazitipi, bosluk),
                           metin_kutusu=True))

    # ---- gorseller ---------------------------------------------------------
    def _resim(self, g_ad, x, y, w, h, daire=False, cizgi=None, kirpma=None):
        if g_ad not in self.gorseller:
            self.gorseller.append(g_ad)
        # rId1 yerlesim, rId2 not sayfasi; gorseller rId3'ten baslar
        self._x.append(_resim_xml(self._id(), "görsel " + GORSELLER[g_ad], 3 + self.gorseller.index(g_ad),
                                  x, y, w, h, daire, cizgi, kirpma))

    def resim(self, g_ad, x, y, w, h, yatay="ctr", dikey="ctr"):
        """Gorseli kutuya oranini bozmadan sigdirir. yatay: l, ctr, r; dikey: t,
        ctr, b. Gorsel yoksa hicbir sey eklemez ve None doner; varsa gorselin
        yerlestigi (x, y, w, h) doner."""
        g = _gorsel(g_ad)
        if g is None:
            return None
        olcek = min(w / float(g.en), h / float(g.boy))
        rw, rh = g.en * olcek, g.boy * olcek
        rx = x if yatay == "l" else (x + w - rw if yatay == "r" else x + (w - rw) / 2.0)
        ry = y if dikey == "t" else (y + h - rh if dikey == "b" else y + (h - rh) / 2.0)
        self._resim(g_ad, rx, ry, rw, rh)
        return rx, ry, rw, rh

    # ---- bilesik ogeler ---------------------------------------------------
    def daire(self, metin, cx, cy, d, boy=12, ad=None):
        """Icinde beyaz kalin yazi olan kirmizi daire."""
        self.elips(cx, cy, d, KIR, None, "daire " + (ad or str(metin)))
        self.yazi(str(metin), cx - d / 2.0, cy - d / 2.0, d, d, boy=boy, kalin=True, renk=BEYAZ)

    def dipnot(self, metin):
        self.yazi(metin, 0.5, 6.62, 11.7, 0.28, boy=10.5, egik=True, renk=GRI, hiza="l")

    def etiket(self, metin, x, y, w=5):
        self.yazi(metin, x, y, w, 0.26, boy=11, kalin=True, renk=GRI, hiza="l")

    def veri(self, x, y, w, h, baslik, alt=None):
        """Veri ya da cikti kutusu (kirmizi, beyaz yazi)."""
        self.kutu(x, y, w, h, "veri", baslik)
        p = [R(baslik, kalin=True, boy=12.5)]
        if alt:
            p.append(R(alt, boy=10.5))
        self.yazi(p, x + 0.06, y, w - 0.12, h, renk=BEYAZ)

    def kart(self, x, y, w, h, tur, baslik, govde, baslik_boy=13, boy=11):
        """Baslikli kart. govde: duz metin ya da madde listesi."""
        self.kutu(x, y, w, h, tur, "kart " + baslik)
        self.yazi(baslik, x + 0.2, y + 0.1, w - 0.4, 0.34, boy=baslik_boy, kalin=True, renk=KIR, hiza="l")
        if not isinstance(govde, str):
            govde = maddeler(govde)
        self.yazi(govde, x + 0.2, y + 0.48, w - 0.4, h - 0.56, boy=boy, hiza="l", dikey="t", bosluk=3)

    def sutun_basliklari(self, y, sutunlar, h=0.34, boy=12.5):
        """Sutun basliklari: her biri kendi sutununun ustunde ortali ve kalin;
        altinda sutun eninde kirmizi cizgi. sutunlar: [(x, w, ad), ...]."""
        for x, w, ad in sutunlar:
            self.yazi(ad, x, y, w, h - 0.04, boy=boy, kalin=True, renk=KIR)
            self.hat(x, y + h, x + w, y + h, "başlık çizgisi " + ad, KIR, 1.5)

    def adim_tablosu(self, y, satirlar, yukseklik, basliklar=None, enler=None, ara=0.08, boy=10.5):
        """Adim adim anlatim tablosu. Her satir: solda adim kutusu, yaninda ne
        yapilir, neden gerekli ve ornek sutunlari.
        satirlar: [(durum, no, ad, rol, ne, neden, ornek), ...]; durum "g"
        gelistirildi (dolu kirmizi), "s" uzerinde calisiliyor (kalin cerceve),
        "r" sirada (kesik gri cerceve). yukseklik: satir yuksekligi (inc).
        Doner: tablonun bittigi y."""
        basliklar = basliklar or ADIM_BASLIKLARI
        enler = enler or ADIM_ENLER
        xs, x = [], 0.5
        for w in enler:
            xs.append(x)
            x += w + ADIM_ARA
        self.sutun_basliklari(y, [(xs[i], enler[i], basliklar[i]) for i in range(4)])
        sy = y + 0.44
        for durum, no, ad, rol, ne, neden, ornek in satirlar:
            h = yukseklik
            self.kutu(xs[0], sy, enler[0], h, {"g": "veri", "s": "simdi", "r": "soluk"}[durum], "adım " + (no or ad))
            ana = BEYAZ if durum == "g" else (KIR if durum == "s" else GRI)
            p = []
            if no:
                p.append(R(no, kalin=True, boy=13, renk=ana))
            p.append(R(ad, kalin=True, boy=11, renk=ana))
            if rol:
                p.append(R(rol, boy=9, renk=BEYAZ if durum == "g" else GRI))
            self.yazi(p, xs[0] + 0.1, sy + 0.04, enler[0] - 0.2, h - 0.08, bosluk=2)
            self.kutu(xs[1], sy, xs[3] + enler[3] - xs[1], h, "gri", "satır " + (no or ad))
            for i in (2, 3):
                cx = xs[i] - ADIM_ARA / 2.0
                self.hat(cx, sy + 0.1, cx, sy + h - 0.1, "sütun ayracı", SOLUK, 0.75)
            for i, icerik in ((1, ne), (2, neden), (3, ornek)):
                self.yazi(icerik, xs[i] + 0.12, sy + 0.05, enler[i] - 0.24, h - 0.1, boy=boy, hiza="l", bosluk=2)
            sy += h + ara
        return sy - ara

    # ---- XML --------------------------------------------------------------
    def _yer_tutucu(self, sid, ad, ph, metin, kutu=None):
        """kutu verilirse (x, y, w, h, inc) yer tutucunun yerlesimdeki yerini ezer."""
        yer = '<p:spPr/>'
        if kutu:
            yer = ('<p:spPr><a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm></p:spPr>'
                   % tuple(_emu(v) for v in kutu))
        return ('<p:sp><p:nvSpPr><p:cNvPr id="%d" name=%s/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
                '<p:nvPr><p:ph %s/></p:nvPr></p:nvSpPr>%s<p:txBody><a:bodyPr/><a:lstStyle/>'
                '<a:p><a:r><a:rPr lang="%s" dirty="0"/><a:t>%s</a:t></a:r></a:p></p:txBody></p:sp>'
                % (sid, _oz(ad), ph, yer, DIL, _kacis(metin)))

    def xml(self, sira):
        """Slaytin XML'i. sira: 1'den baslayan slayt numarasi."""
        x = [_BAS, '<p:sld %s><p:cSld><p:spTree>' % _NS3, _GRUP,
             self._yer_tutucu(2, "Başlık", 'type="title"', self.baslik, self.baslik_kutu)]
        if self.yerlesim == "KAPAK":
            if self.ust:
                x.append(self._yer_tutucu(3, "Birim", 'type="body" sz="quarter" idx="10"', self.ust))
            if not self.kapak_gorseli:
                # Gorsel bulunamadi: bos resim yer tutucusu kalir, PowerPoint'te tiklaninca resim eklenir.
                x.append('<p:sp><p:nvSpPr><p:cNvPr id="5" name="Kapak Görseli"/><p:cNvSpPr>'
                         '<a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr><p:ph type="pic" sz="quarter" idx="12"/>'
                         '</p:nvPr></p:nvSpPr><p:spPr/></p:sp>')
        elif self.yerlesim == "AKIS" and self.ust:
            x.append(self._yer_tutucu(3, "Özet Cümle", 'type="body" sz="quarter" idx="10"', self.ust))
        x.extend(self._x)
        if self.yerlesim == "AKIS":
            x.append('<p:sp><p:nvSpPr><p:cNvPr id="%d" name="Slayt Numarası"/><p:cNvSpPr>'
                     '<a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr><p:ph type="sldNum" sz="quarter" idx="12"/>'
                     '</p:nvPr></p:nvSpPr><p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p>'
                     '<a:fld id="%s" type="slidenum"><a:rPr lang="%s"/><a:t>%d</a:t></a:fld>'
                     '<a:endParaRPr lang="%s"/></a:p></p:txBody></p:sp>'
                     % (self._id(), _ALAN_NO, DIL, sira, DIL))
        x.append('</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>')
        return "".join(x)


# ===========================================================================
# PAKETIN SABIT PARCALARI: TEMA, ANA SLAYT, YERLESIMLER, NOT ANA SAYFASI
# ===========================================================================
def _tema(ad):
    """Office renkleri, Calibri. Bicim semasi en az ucer oge ister."""
    def renk(etiket, deger):
        return '<a:%s><a:srgbClr val="%s"/></a:%s>' % (etiket, deger, etiket)

    def yazi(etiket):
        return '<a:%s><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:%s>' % (etiket, etiket)

    def gecis(a, b, c):
        return ('<a:gradFill rotWithShape="1"><a:gsLst><a:gs pos="0"><a:schemeClr val="phClr">%s</a:schemeClr></a:gs>'
                '<a:gs pos="50000"><a:schemeClr val="phClr">%s</a:schemeClr></a:gs>'
                '<a:gs pos="100000"><a:schemeClr val="phClr">%s</a:schemeClr></a:gs></a:gsLst>'
                '<a:lin ang="5400000" scaled="0"/></a:gradFill>' % (a, b, c))

    duz = '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
    cizgiler = "".join(
        '<a:ln w="%d" cap="flat" cmpd="sng" algn="ctr">%s<a:prstDash val="solid"/><a:miter lim="800000"/></a:ln>' % (w, duz)
        for w in (6350, 12700, 19050))
    return (_BAS + '<a:theme xmlns:a="%s" name=%s><a:themeElements><a:clrScheme name="Office">'
            '<a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>'
            '<a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>' % (_NS_A, _oz(ad))
            + renk("dk2", "44546A") + renk("lt2", "E7E6E6") + renk("accent1", "4472C4")
            + renk("accent2", "ED7D31") + renk("accent3", "A5A5A5") + renk("accent4", "FFC000")
            + renk("accent5", "5B9BD5") + renk("accent6", "70AD47") + renk("hlink", "0563C1")
            + renk("folHlink", "954F72")
            + '</a:clrScheme><a:fontScheme name="Office">' + yazi("majorFont") + yazi("minorFont")
            + '</a:fontScheme><a:fmtScheme name="Office"><a:fillStyleLst>' + duz
            + gecis('<a:lumMod val="110000"/><a:satMod val="105000"/><a:tint val="67000"/>',
                    '<a:lumMod val="105000"/><a:satMod val="103000"/><a:tint val="73000"/>',
                    '<a:lumMod val="105000"/><a:satMod val="109000"/><a:tint val="81000"/>')
            + gecis('<a:satMod val="103000"/><a:lumMod val="102000"/><a:tint val="94000"/>',
                    '<a:satMod val="110000"/><a:lumMod val="100000"/><a:shade val="100000"/>',
                    '<a:lumMod val="99000"/><a:satMod val="120000"/><a:shade val="78000"/>')
            + '</a:fillStyleLst><a:lnStyleLst>' + cizgiler + '</a:lnStyleLst><a:effectStyleLst>'
            '<a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle>'
            '<a:effectStyle><a:effectLst><a:outerShdw blurRad="57150" dist="19050" dir="5400000" algn="ctr" '
            'rotWithShape="0"><a:srgbClr val="000000"><a:alpha val="63000"/></a:srgbClr></a:outerShdw>'
            '</a:effectLst></a:effectStyle></a:effectStyleLst><a:bgFillStyleLst>' + duz
            + '<a:solidFill><a:schemeClr val="phClr"><a:tint val="95000"/><a:satMod val="170000"/></a:schemeClr></a:solidFill>'
            + gecis('<a:tint val="93000"/><a:satMod val="150000"/><a:shade val="98000"/><a:lumMod val="102000"/>',
                    '<a:tint val="98000"/><a:satMod val="130000"/><a:shade val="90000"/><a:lumMod val="103000"/>',
                    '<a:shade val="63000"/><a:satMod val="120000"/>')
            + '</a:bgFillStyleLst></a:fmtScheme></a:themeElements><a:objectDefaults/><a:extraClrSchemeLst/></a:theme>')


def _duzeyler(boy, yazi="+mn", madde=False, ek=""):
    """lvl1pPr .. lvl9pPr: ana slaydin ve sunumun varsayilan metin stilleri."""
    x = []
    for i in range(1, 10):
        if madde:
            sol = (342900, 742950, 1143000, 1600200, 2057400, 2514600, 2971800, 3429000, 3886200)[i - 1]
            girinti = -342900 if i == 1 else (-285750 if i == 2 else -228600)
            b = (3200, 2800, 2400, 2000)[min(i, 4) - 1]
            ic = ('<a:spcBef><a:spcPct val="20000"/></a:spcBef><a:buFont typeface="Arial" pitchFamily="34" '
                  'charset="0"/><a:buChar char="&#8226;"/>')
            bas = ' marL="%d" indent="%d"' % (sol, girinti)
        else:
            b, ic, bas = boy, ek, ' marL="%d"' % ((i - 1) * 457200)
        x.append('<a:lvl%dpPr%s algn="l" defTabSz="914400" rtl="0" eaLnBrk="1" latinLnBrk="0" hangingPunct="1">%s'
                 '<a:defRPr sz="%d" kern="1200"><a:solidFill><a:schemeClr val="tx1"/></a:solidFill>'
                 '<a:latin typeface="%s-lt"/><a:ea typeface="%s-ea"/><a:cs typeface="%s-cs"/></a:defRPr></a:lvl%dpPr>'
                 % (i, bas, ic, b, yazi, yazi, yazi, i))
    return "".join(x)


def _yt(sid, ad, ph, x, y, w, h, dikey, hiza, boy, renk, kalin, istem):
    """Ana slayt ya da yerlesimdeki metin yer tutucusu: konum, hiza, boy, renk."""
    return ('<p:sp><p:nvSpPr><p:cNvPr id="%d" name=%s/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
            '<p:nvPr><p:ph %s/></p:nvPr></p:nvSpPr><p:spPr><a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/>'
            '</a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr><p:txBody>'
            '<a:bodyPr vert="horz" wrap="square" lIns="0" tIns="0" rIns="0" bIns="0" rtlCol="0" anchor="%s">'
            '<a:noAutofit/></a:bodyPr><a:lstStyle><a:lvl1pPr marL="0" indent="0" algn="%s"><a:buNone/>'
            '<a:defRPr sz="%d" b="%d"><a:solidFill><a:srgbClr val="%s"/></a:solidFill></a:defRPr></a:lvl1pPr>'
            '</a:lstStyle><a:p><a:r><a:rPr lang="%s"/><a:t>%s</a:t></a:r></a:p></p:txBody></p:sp>'
            % (sid, _oz(ad), ph, _emu(x), _emu(y), _emu(w), _emu(h), dikey, hiza,
               int(round(boy * 100)), 1 if kalin else 0, renk, DIL, _kacis(istem)))


def _numara_yt(sid, ph_idx):
    """Slayt numarasi yer tutucusu (sag alt, gri, 10 punto)."""
    return ('<p:sp><p:nvSpPr><p:cNvPr id="%d" name="Slayt Numarası"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
            '<p:nvPr><p:ph type="sldNum" sz="quarter" idx="%d"/></p:nvPr></p:nvSpPr><p:spPr><a:xfrm>'
            '<a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
            '<p:txBody><a:bodyPr vert="horz" rtlCol="0"/>'
            '<a:lstStyle><a:lvl1pPr algn="r"><a:defRPr sz="1000"><a:solidFill><a:srgbClr val="%s"/></a:solidFill>'
            '</a:defRPr></a:lvl1pPr></a:lstStyle><a:p><a:fld id="%s" type="slidenum"><a:rPr lang="%s"/>'
            '<a:t>&#8249;#&#8250;</a:t></a:fld><a:endParaRPr lang="%s"/></a:p></p:txBody></p:sp>'
            % (sid, ph_idx, _emu(12.35), _emu(7.08), _emu(0.5), _emu(0.25), SOLUK, _ALAN_NO, DIL, DIL))


def _duz_cizgi(sid, ad, x, y, w, kalinlik, renk=None):
    """Yerlesimdeki yatay cizgi (varsayilan kirmizi)."""
    return _sp(sid, ad, _geo("line"), x, y, w, 0, '<a:noFill/>' + _cizgi_xml((renk or KIR, kalinlik, False)))


def _ana_slayt():
    """Ana slayt: baslik, govde ve slayt numarasi yer tutuculari, metin stilleri."""
    return (_BAS + '<p:sldMaster %s><p:cSld><p:bg><p:bgRef idx="1001"><a:schemeClr val="bg1"/></p:bgRef></p:bg>'
            '<p:spTree>%s' % (_NS3, _GRUP)
            + _yt(2, "Başlık", 'type="title"', 0.5, 0.28, 12.33, 0.58, "ctr", "l", 24, KIR, True,
                  "Asıl başlık stilini düzenlemek için tıklayın")
            + _yt(3, "Metin", 'type="body" idx="1"', 0.5, 1.5, 12.33, 5.0, "t", "l", 14, KOYU, False,
                  "Asıl metin stillerini düzenlemek için tıklayın")
            + _numara_yt(4, 4)
            + '</p:spTree></p:cSld><p:clrMap %s/><p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/>'
            '<p:sldLayoutId id="2147483650" r:id="rId2"/><p:sldLayoutId id="2147483651" r:id="rId3"/></p:sldLayoutIdLst><p:txStyles><p:titleStyle>'
            '<a:lvl1pPr algn="ctr" defTabSz="914400" rtl="0" eaLnBrk="1" latinLnBrk="0" hangingPunct="1">'
            '<a:spcBef><a:spcPct val="0"/></a:spcBef><a:buNone/><a:defRPr sz="4400" kern="1200"><a:solidFill>'
            '<a:schemeClr val="tx1"/></a:solidFill><a:latin typeface="+mj-lt"/><a:ea typeface="+mj-ea"/>'
            '<a:cs typeface="+mj-cs"/></a:defRPr></a:lvl1pPr></p:titleStyle><p:bodyStyle>' % _RENK_ESLEME
            + _duzeyler(0, madde=True) + '</p:bodyStyle><p:otherStyle><a:defPPr><a:defRPr lang="%s"/></a:defPPr>' % DIL
            + _duzeyler(1800) + '</p:otherStyle></p:txStyles></p:sldMaster>')


def _yerlesim(ad, ogeler, zemin=None):
    """zemin: arka plan dolgusunun XML'i; verilmezse beyaz."""
    return (_BAS + '<p:sldLayout %s preserve="1" userDrawn="1"><p:cSld name=%s><p:bg><p:bgPr>%s'
            '<a:effectLst/></p:bgPr></p:bg><p:spTree>%s%s</p:spTree></p:cSld>'
            '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>'
            % (_NS3, _oz(ad), zemin or _dolgu(BEYAZ), _GRUP, ogeler))




# Kapak olculeri (inc): gorsel alani ustte, baslik ve birim satiri sol altta
KAPAK_GORSEL = (0.5, 0.4, 12.33, 5.6)       # gorselin sigdirildigi alan (x, y, w, h)
KAPAK_BASLIK = (0.5, 6.25, 12.33, 0.6)
KAPAK_BIRIM = (0.5, 6.85, 12.33, 0.4)
KAPANIS_BOY = 54                            # son slayttaki basligin punto boyu


def _yerlesim_kapak():
    """Kapak: beyaz zemin, cizgi yok. Gorsel ustteki alanin ortasinda, sigabildigi
    en buyuk boyda; sol altta kirmizi baslik ve altinda birim satiri. Gorsel
    bulunamazsa ayni alanda resim yer tutucusu kalir."""
    gx, gy, gw, gh = KAPAK_GORSEL
    resim = ('<p:sp><p:nvSpPr><p:cNvPr id="4" name="Kapak Görseli"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
             '<p:nvPr><p:ph type="pic" sz="quarter" idx="12" hasCustomPrompt="1"/></p:nvPr></p:nvSpPr><p:spPr><a:xfrm>'
             '<a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
             '<p:txBody><a:bodyPr vert="horz" rtlCol="0" anchor="ctr"><a:noAutofit/></a:bodyPr><a:lstStyle>'
             '<a:lvl1pPr marL="0" indent="0" algn="ctr"><a:buNone/><a:defRPr sz="1400"><a:solidFill>'
             '<a:srgbClr val="%s"/></a:solidFill></a:defRPr></a:lvl1pPr></a:lstStyle><a:p><a:r><a:rPr lang="%s"/>'
             '<a:t>Kapak görseli</a:t></a:r></a:p></p:txBody></p:sp>'
             % (_emu(gx), _emu(gy), _emu(gw), _emu(gh), GRI, DIL))
    bx, by, bw, bh = KAPAK_BASLIK
    ux, uy, uw, uh = KAPAK_BIRIM
    return _yerlesim("Kapak",
                     _yt(2, "Başlık", 'type="title"', bx, by, bw, bh, "ctr", "l", 28, KIR, True, "Başlık")
                     + _yt(3, "Birim", 'type="body" sz="quarter" idx="10"', ux, uy, uw, uh, "ctr", "l", 16,
                           KOYU, False, "Birim")
                     + resim)


def _yerlesim_kapanis():
    """Kapanis: beyaz zemin, cizgi yok; ortali, buyuk, kirmizi baslik. Basligin
    dikey yeri slaytta, alttaki gorselin boyuna gore ayarlanir."""
    return _yerlesim("Kapanış",
                     _yt(2, "Başlık", 'type="title"', 0.5, 0.5, 12.33, 4.0, "ctr", "ctr", KAPANIS_BOY, KIR, True,
                         "Başlık"))


def _yerlesim_akis():
    """Icerik slayti: kirmizi baslik, altinda cizgi, ozet cumle, slayt numarasi."""
    return _yerlesim("İçerik",
                     _yt(2, "Başlık", 'type="title"', 0.5, 0.28, 12.33, 0.58, "ctr", "l", 24, KIR, True, "Başlık")
                     + _duz_cizgi(3, "başlık çizgisi", 0.5, 0.92, 12.33, 1.0)
                     + _yt(4, "Özet Cümle", 'type="body" sz="quarter" idx="10"', 0.5, 1.0, 12.33, 0.42, "ctr", "l",
                           13.5, GRI, False, "Özet cümle")
                     + _numara_yt(5, 12))


def _not_ana_sayfa():
    """Not sayfalarinin ana sayfasi (PowerPoint'in standart yerlesimi)."""
    def yt(sid, ad, ph, x, y, w, h, ic, ek=""):
        return ('<p:sp><p:nvSpPr><p:cNvPr id="%d" name="%s"/><p:cNvSpPr><a:spLocks noGrp="1"%s/></p:cNvSpPr>'
                '<p:nvPr><p:ph %s/></p:nvPr></p:nvSpPr><p:spPr><a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/>'
                '</a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom>%s</p:spPr>%s</p:sp>'
                % (sid, ad, ' noRot="1" noChangeAspect="1"' if "sldImg" in ph else "", ph, x, y, w, h, ek, ic))

    def govde(hiza, dikey="t", metin=""):
        return ('<p:txBody><a:bodyPr vert="horz" lIns="91440" tIns="45720" rIns="91440" bIns="45720" rtlCol="0" '
                'anchor="%s"/><a:lstStyle><a:lvl1pPr algn="%s"><a:defRPr sz="1200"/></a:lvl1pPr></a:lstStyle>'
                '<a:p>%s<a:endParaRPr lang="%s"/></a:p></p:txBody>' % (dikey, hiza, metin, DIL))

    duzey = "".join('<a:p><a:pPr lvl="%d"/><a:r><a:rPr lang="%s"/><a:t>%s</a:t></a:r></a:p>' % (i, DIL, t)
                    for i, t in enumerate(("Asıl metin stillerini düzenlemek için tıklayın", "İkinci düzey",
                                           "Üçüncü düzey", "Dördüncü düzey", "Beşinci düzey")))
    numara = '<a:fld id="%s" type="slidenum"><a:rPr lang="%s"/><a:t>&#8249;#&#8250;</a:t></a:fld>' % (_ALAN_NO, DIL)
    return (_BAS + '<p:notesMaster %s><p:cSld><p:bg><p:bgRef idx="1001"><a:schemeClr val="bg1"/></p:bgRef></p:bg>'
            '<p:spTree>%s' % (_NS3, _GRUP)
            + yt(2, "Üst Bilgi", 'type="hdr" sz="quarter"', 0, 0, 2971800, 458788, govde("l"))
            + yt(3, "Tarih", 'type="dt" idx="1"', 3884613, 0, 2971800, 458788, govde("r"))
            + yt(4, "Slayt Görüntüsü", 'type="sldImg" idx="2"', 685800, 1143000, 5486400, 3086100, "",
                 '<a:noFill/><a:ln w="12700"><a:solidFill><a:prstClr val="black"/></a:solidFill></a:ln>')
            + yt(5, "Notlar", 'type="body" sz="quarter" idx="3"', 685800, 4400550, 5486400, 3600450,
                 '<p:txBody><a:bodyPr vert="horz" lIns="91440" tIns="45720" rIns="91440" bIns="45720" rtlCol="0"/>'
                 '<a:lstStyle/>%s</p:txBody>' % duzey)
            + yt(6, "Alt Bilgi", 'type="ftr" sz="quarter" idx="4"', 0, 8685213, 2971800, 458787, govde("l", "b"))
            + yt(7, "Slayt Numarası", 'type="sldNum" sz="quarter" idx="5"', 3884613, 8685213, 2971800, 458787,
                 govde("r", "b", numara))
            + '</p:spTree></p:cSld><p:clrMap %s/><p:notesStyle>%s</p:notesStyle></p:notesMaster>'
            % (_RENK_ESLEME, _duzeyler(1200)))


def _not_sayfasi(metin, sira):
    """Bir slaydin konusmaci notu."""
    return (_BAS + '<p:notes %s><p:cSld><p:spTree>%s'
            '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Slayt Görüntüsü"/><p:cNvSpPr><a:spLocks noGrp="1" noRot="1" '
            'noChangeAspect="1"/></p:cNvSpPr><p:nvPr><p:ph type="sldImg"/></p:nvPr></p:nvSpPr><p:spPr/></p:sp>'
            '<p:sp><p:nvSpPr><p:cNvPr id="3" name="Notlar"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
            '<p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr><p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/>'
            '<a:p><a:r><a:rPr lang="%s" dirty="0"/><a:t>%s</a:t></a:r><a:endParaRPr lang="%s" dirty="0"/></a:p>'
            '</p:txBody></p:sp>'
            '<p:sp><p:nvSpPr><p:cNvPr id="4" name="Slayt Numarası"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
            '<p:nvPr><p:ph type="sldNum" sz="quarter" idx="10"/></p:nvPr></p:nvSpPr><p:spPr/><p:txBody><a:bodyPr/>'
            '<a:lstStyle/><a:p><a:fld id="%s" type="slidenum"><a:rPr lang="%s"/><a:t>%d</a:t></a:fld>'
            '<a:endParaRPr lang="%s"/></a:p></p:txBody></p:sp>'
            '</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:notes>'
            % (_NS3, _GRUP, DIL, _kacis(metin), DIL, _ALAN_NO, DIL, sira, DIL))


def _iliskiler(liste):
    """liste: [(tur, hedef), ...] -> .rels icerigi; kimlikler rId1'den baslar."""
    return (_BAS + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join('<Relationship Id="rId%d" Type="%s%s" Target="%s"/>' % (i + 1, _ILISKI, tur, hedef)
                      for i, (tur, hedef) in enumerate(liste))
            + '</Relationships>')


# ===========================================================================
# PAKET
# ===========================================================================
def paketle(slaytlar, baslik, zaman=None):
    """Slayt listesinden .pptx icerigini (bayt) kurar."""
    n = len(slaytlar)
    zaman = zaman or datetime.datetime.now(datetime.timezone.utc)
    damga = zaman.strftime("%Y-%m-%dT%H:%M:%SZ")
    yerlesim_no = {"KAPAK": 1, "AKIS": 2, "KAPANIS": 3}
    p = []                                            # [(ad, icerik)]

    # Gorseller: her gorsel pakete BIR kez girer; slaytlar ona iliskiyle baglanir
    ortam = []                                        # [(gorsel adi, pakette parca adi)]
    for s in slaytlar:
        for g_ad in s.gorseller:
            if g_ad not in [o[0] for o in ortam]:
                ortam.append((g_ad, "ppt/media/image%d.%s" % (len(ortam) + 1, _gorsel(g_ad).uzanti)))
    ortam_yolu = dict(ortam)

    # Icerik turleri
    tur = ['<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
           '<Default Extension="xml" ContentType="application/xml"/>']
    for uzanti in sorted(set(yol.rsplit(".", 1)[1] for _, yol in ortam)):
        tur.append('<Default Extension="%s" ContentType="image/%s"/>' % (uzanti, uzanti))

    def ek(ad, icerik_turu):
        tur.append('<Override PartName="/%s" ContentType="%s"/>' % (ad, icerik_turu))

    ek("ppt/presentation.xml", _ICERIK + "presentation.main+xml")
    ek("ppt/slideMasters/slideMaster1.xml", _ICERIK + "slideMaster+xml")
    for i in (1, 2, 3):
        ek("ppt/slideLayouts/slideLayout%d.xml" % i, _ICERIK + "slideLayout+xml")
    for i in range(1, n + 1):
        ek("ppt/slides/slide%d.xml" % i, _ICERIK + "slide+xml")
    ek("ppt/notesMasters/notesMaster1.xml", _ICERIK + "notesMaster+xml")
    for i in range(1, n + 1):
        ek("ppt/notesSlides/notesSlide%d.xml" % i, _ICERIK + "notesSlide+xml")
    ek("ppt/presProps.xml", _ICERIK + "presProps+xml")
    ek("ppt/viewProps.xml", _ICERIK + "viewProps+xml")
    ek("ppt/tableStyles.xml", _ICERIK + "tableStyles+xml")
    for i in (1, 2):
        ek("ppt/theme/theme%d.xml" % i, "application/vnd.openxmlformats-officedocument.theme+xml")
    ek("docProps/core.xml", "application/vnd.openxmlformats-package.core-properties+xml")
    ek("docProps/app.xml", "application/vnd.openxmlformats-officedocument.extended-properties+xml")
    p.append(("[Content_Types].xml", _BAS + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              + "".join(tur) + '</Types>'))

    # Kok iliskiler ve belge ozellikleri
    p.append(("_rels/.rels", _BAS + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
              '<Relationship Id="rId1" Type="%sofficeDocument" Target="ppt/presentation.xml"/>'
              '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/'
              'core-properties" Target="docProps/core.xml"/>'
              '<Relationship Id="rId3" Type="%sextended-properties" Target="docProps/app.xml"/>'
              '</Relationships>' % (_ILISKI, _ILISKI)))
    p.append(("docProps/core.xml", _BAS + '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/'
              'metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
              'xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
              '<dc:title>%s</dc:title><dc:creator>%s</dc:creator><cp:lastModifiedBy>%s</cp:lastModifiedBy>'
              '<cp:revision>1</cp:revision><dcterms:created xsi:type="dcterms:W3CDTF">%s</dcterms:created>'
              '<dcterms:modified xsi:type="dcterms:W3CDTF">%s</dcterms:modified></cp:coreProperties>'
              % (_kacis(baslik), _kacis(baslik), _kacis(baslik), damga, damga)))
    p.append(("docProps/app.xml", _BAS + '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/'
              'extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
              '<TotalTime>0</TotalTime><Application>Microsoft Office PowerPoint</Application>'
              '<PresentationFormat>Geniş ekran</PresentationFormat><Slides>%d</Slides><Notes>%d</Notes>'
              '<HiddenSlides>0</HiddenSlides><AppVersion>16.0000</AppVersion></Properties>' % (n, n)))

    # Sunum: ana slayt rId1, slaytlar rId2.., sonra not ana sayfasi ve digerleri
    bolumler = []                                     # [(ad, [slayt kimligi, ...])]
    for i, s in enumerate(slaytlar):
        if not bolumler or bolumler[-1][0] != s.bolum:
            bolumler.append((s.bolum, []))
        bolumler[-1][1].append(256 + i)
    bolum_xml = "".join(
        '<p14:section name=%s id="{%s}"><p14:sldIdLst>%s</p14:sldIdLst></p14:section>'
        % (_oz(ad), str(uuid.uuid5(uuid.NAMESPACE_DNS, "bolum-%d-%s" % (j, ad))).upper(),
           "".join('<p14:sldId id="%d"/>' % k for k in kimlikler))
        for j, (ad, kimlikler) in enumerate(bolumler))
    p.append(("ppt/presentation.xml", _BAS + '<p:presentation %s saveSubsetFonts="1" autoCompressPictures="0">'
              '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
              '<p:notesMasterIdLst><p:notesMasterId r:id="rId%d"/></p:notesMasterIdLst><p:sldIdLst>%s</p:sldIdLst>'
              '<p:sldSz cx="%d" cy="%d"/><p:notesSz cx="%d" cy="%d"/><p:defaultTextStyle><a:defPPr><a:defRPr lang="%s"/>'
              '</a:defPPr>%s</p:defaultTextStyle><p:extLst><p:ext uri="{521415D9-36F7-43E2-AB2F-B90AF26B5E84}">'
              '<p14:sectionLst xmlns:p14="http://schemas.microsoft.com/office/powerpoint/2010/main">%s</p14:sectionLst>'
              '</p:ext></p:extLst></p:presentation>'
              % (_NS3, n + 2, "".join('<p:sldId id="%d" r:id="rId%d"/>' % (256 + i, i + 2) for i in range(n)),
                 SLAYT_CX, SLAYT_CY, NOT_CX, NOT_CY, DIL, _duzeyler(1800), bolum_xml)))
    p.append(("ppt/_rels/presentation.xml.rels", _iliskiler(
        [("slideMaster", "slideMasters/slideMaster1.xml")]
        + [("slide", "slides/slide%d.xml" % i) for i in range(1, n + 1)]
        + [("notesMaster", "notesMasters/notesMaster1.xml"), ("presProps", "presProps.xml"),
           ("viewProps", "viewProps.xml"), ("theme", "theme/theme1.xml"), ("tableStyles", "tableStyles.xml")])))
    p.append(("ppt/presProps.xml", _BAS + '<p:presentationPr %s/>' % _NS3))
    p.append(("ppt/viewProps.xml", _BAS + '<p:viewPr %s><p:normalViewPr horzBarState="maximized"><p:restoredLeft sz="15611"/>'
              '<p:restoredTop sz="94610"/></p:normalViewPr><p:slideViewPr><p:cSldViewPr snapToGrid="0" snapToObjects="1">'
              '<p:cViewPr varScale="1"><p:scale><a:sx n="100" d="100"/><a:sy n="100" d="100"/></p:scale>'
              '<p:origin x="0" y="0"/></p:cViewPr><p:guideLst/></p:cSldViewPr></p:slideViewPr>'
              '<p:gridSpacing cx="76200" cy="76200"/></p:viewPr>' % _NS3))
    p.append(("ppt/tableStyles.xml", _BAS + '<a:tblStyleLst xmlns:a="%s" def="{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}"/>' % _NS_A))

    # Tema (slayt ana sayfasi ve not ana sayfasi icin AYRI parca: PowerPoint boyle yazar)
    p.append(("ppt/theme/theme1.xml", _tema("Platform Sunumu")))
    p.append(("ppt/theme/theme2.xml", _tema("Platform Sunumu Notlar")))

    # Ana slayt ve yerlesimler
    p.append(("ppt/slideMasters/slideMaster1.xml", _ana_slayt()))
    p.append(("ppt/slideMasters/_rels/slideMaster1.xml.rels", _iliskiler(
        [("slideLayout", "../slideLayouts/slideLayout1.xml"), ("slideLayout", "../slideLayouts/slideLayout2.xml"),
         ("slideLayout", "../slideLayouts/slideLayout3.xml"), ("theme", "../theme/theme1.xml")])))
    for i, icerik in ((1, _yerlesim_kapak()), (2, _yerlesim_akis()), (3, _yerlesim_kapanis())):
        p.append(("ppt/slideLayouts/slideLayout%d.xml" % i, icerik))
        p.append(("ppt/slideLayouts/_rels/slideLayout%d.xml.rels" % i,
                  _iliskiler([("slideMaster", "../slideMasters/slideMaster1.xml")])))

    # Not ana sayfasi
    p.append(("ppt/notesMasters/notesMaster1.xml", _not_ana_sayfa()))
    p.append(("ppt/notesMasters/_rels/notesMaster1.xml.rels", _iliskiler([("theme", "../theme/theme2.xml")])))

    # Slaytlar ve notlari
    for i, s in enumerate(slaytlar):
        no = i + 1
        p.append(("ppt/slides/slide%d.xml" % no, s.xml(no)))
        p.append(("ppt/slides/_rels/slide%d.xml.rels" % no, _iliskiler(
            [("slideLayout", "../slideLayouts/slideLayout%d.xml" % yerlesim_no[s.yerlesim]),
             ("notesSlide", "../notesSlides/notesSlide%d.xml" % no)]
            + [("image", "../media/" + ortam_yolu[g_ad].rsplit("/", 1)[1]) for g_ad in s.gorseller])))
        p.append(("ppt/notesSlides/notesSlide%d.xml" % no, _not_sayfasi(s.notlar, no)))
        p.append(("ppt/notesSlides/_rels/notesSlide%d.xml.rels" % no, _iliskiler(
            [("notesMaster", "../notesMasters/notesMaster1.xml"), ("slide", "../slides/slide%d.xml" % no)])))

    for g_ad, yol in ortam:
        p.append((yol, _gorsel(g_ad).veri))

    tampon = io.BytesIO()
    tarih = (zaman.year, zaman.month, zaman.day, zaman.hour, zaman.minute, zaman.second)
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as paket:
        for ad, icerik in p:
            bilgi = zipfile.ZipInfo(ad, date_time=tarih)
            bilgi.compress_type = zipfile.ZIP_DEFLATED
            bilgi.external_attr = 0o600 << 16
            paket.writestr(bilgi, icerik if isinstance(icerik, bytes) else icerik.encode("utf-8"))
    return tampon.getvalue()


# ===========================================================================
# SLAYTLAR
# ===========================================================================
B1, B2, B3, B4 = "Giriş", "01 Çalışma Kurulumu", "02 Değişken Mühendisliği", "Sırada ve durum"


def _kapak_gorseli(s):
    """Kapak gorseli: basligin ustundeki alanin ortasinda, sigabildigi en buyuk boyda."""
    g = _gorsel("kapak")
    if g is None:
        return False
    gx, gy, gw, gh = KAPAK_GORSEL
    w, h = gw, gw / g.oran
    if h > gh:
        w, h = gh * g.oran, gh
    s._resim("kapak", gx + (gw - w) / 2.0, gy + (gh - h) / 2.0, w, h)
    s.kapak_gorseli = True
    return True


def slayt_kapak():
    s = Slayt("KAPAK", B1, "Kurumsal Analitik, Tahminleme ve İçgörü Platformu",
              "Bireysel Krediler Analitik ve Tahsis BI")
    _kapak_gorseli(s)
    s.notlar = ("Kapak. Görsel platformun görsel klasöründen gelir; bulunamadıysa yerinde resim yer tutucusu "
                "kalır, tıklayıp resim ekleyebilirsiniz. Sunum, platformu hiç bilmeyen ekiplere göre sıralandı: neden "
                "yapıyoruz, nedir, nasıl çalışır, bugüne kadar hangi adımlar geliştirildi, sırada ne var.")
    return s


def slayt_kapanis():
    s = Slayt("KAPANIS", B4, "Teşekkürler")
    en, boy = SLAYT_CX / float(EMU), SLAYT_CY / float(EMU)
    bos = boy                                         # basligin ortalanacagi yukseklik: gorselin ustunde kalan alan
    g = _gorsel("kapanis")
    if g is not None:
        # En altta, slaydin alt kenarina yapisik; ene sigdirilir
        w, h = en, en / g.oran
        if h > 3.2:
            w, h = 3.2 * g.oran, 3.2
        s._resim("kapanis", (en - w) / 2.0, boy - h, w, h)
        bos = boy - h
    s.baslik_kutu = (0.5, 0.0, en - 1.0, bos)         # baslik bu alanin tam ortasinda durur
    s.notlar = "Kapanış. Soruları ve önerileri bu slaytta alın."
    return s


def K(metin, boy=9.5):
    """Kolon adi gibi kod parcasi: sabit aralikli, kirmizi, kalin."""
    return R(metin, kalin=True, renk=KIR, boy=boy, yazitipi="Courier New")


# Durum: "g" gelistirildi, "s" uzerinde calisiliyor, "r" sirada
SIRADA_CUMLE = ("Sıradaki adımlar: ilk sürümleri kodda var; 02.2 tamamlandıktan sonra bu yapıya göre sırayla ele "
                "alınacak.")


def slayt_ihtiyac():
    s = Slayt("AKIS", B1, "İhtiyaç ve Amaç")
    s.dik(0.5, 1.1, 0.06, 0.78, KIR, "amaç çizgisi")
    s.yazi("Model geliştirmede veri hazırlığı, eleme ve değişken üretimi bugün büyük ölçüde elle ve her modelde farklı "
           "biçimde yürütülüyor; bir modelde yapılan iş o modelde kalıyor, süreler uzuyor. Platform bu adımları tek, "
           "standart ve izlenebilir bir akışta toplar: süreci yapay zekâ desteğiyle hızlandırmayı, modele yalnız "
           "katkısı ölçülen değişkenleri almayı ve emeği katma değeri yüksek işlere yönlendirmeyi amaçlar.",
           0.7, 1.1, 12.13, 0.78, boy=12.5, hiza="l")
    kx, kw, ex, ew, px, pw = 0.5, 2.3, 2.95, 4.6, 7.93, 4.9
    s.sutun_basliklari(2.04, [(kx, kw, "Konu"), (ex, ew, "Elle Yürütülen Süreçte"), (px, pw, "Platformda")])
    satirlar = [
        ("Yöntem birliği",
         "Benzer modellerde bile hazırlık, eleme ve üretim adımları kişiden kişiye farklı uygulanır; sonuçlar "
         "karşılaştırılamaz.",
         "Aynı adımlar, aynı kontroller ve aynı ölçütler her çalışmada aynı sırayla uygulanır."),
        ("Yeniden kullanım",
         "Bir modelde üretilen değişkenler ve yapılan elemeler o modelde kalır; yeni model geliştiren bunlardan "
         "yararlanamaz.",
         "Onaylanan tanımlar, adlar ve kararlar proje hafızasına yazılır; sonraki çalışmada hazır gelir."),
        ("Süre",
         "Sözlük okuma, veri temizliği ve dönüşüm kodu her modelde baştan yapılır; işler gecikir, geliştirme süresi "
         "uzar.",
         "Sayımı ve ölçümü kod yapar, öneriyi yapay zekâ hazırlar; kullanıcı zamanını incelemeye ve karara ayırır."),
        ("Sözlük ve kolon adları",
         "Kısaltmalı adlar ile eksik ya da tutarsız açıklamalar her çalışmada yeniden çözülür.",
         "Adlar ve açıklamalar bir kez kontrol edilip onaylanır; adlar standart yazılışa çevrilir."),
        ("Veri kalitesi ve eleme",
         "Hangi kontrolün yapılacağı kişiye bağlıdır; neyin neden elendiği çoğu zaman kayda geçmez.",
         "Aynı 26 kontrol verinin tamamında yapılır; her eleme kararı gerekçesiyle kaydedilir."),
        ("Değişken üretimi",
         "Dönüşüm kodu elle yazılır; hangi dönüşümlerin deneneceği kişinin deneyimine ve zamanına bağlıdır.",
         "41 dönüşümün katkısı ölçülür; yeni bilgi taşıyanlar önerilir, seçimi kullanıcı yapar, kodu platform yazar."),
        ("İzlenebilirlik",
         "Kararların izi dağınık notlarda ve dosyalarda kalır; çalışmayı devralmak ve denetlemek zordur.",
         "Her adımın kararı, gerekçesi ve üretim kodu tek yerde durur; çalışma kaldığı yerden açılır."),
    ]
    h, ara = 0.5, 0.07
    for i, (konu, elle, platform) in enumerate(satirlar):
        y = 2.5 + i * (h + ara)
        s.veri(kx, y, kw, h, konu)
        s.kutu(ex, y, ew, h, "cerceve", "elle " + konu)
        s.yazi(elle, ex + 0.12, y, ew - 0.24, h, boy=10.5, renk=GRI, hiza="l")
        s.ok(ex + ew + 0.04, y + h / 2, px - 0.04, y + h / 2, "ok " + konu)
        s.kutu(px, y, pw, h, "islem", "platform " + konu)
        s.yazi(platform, px + 0.12, y, pw - 0.24, h, boy=10.5, hiza="l")
    s.dipnot("Platform şu an sınıflandırma modelleri (0 ve 1 değerli hedef) için açıktır; farklı veri setlerinde aynı "
             "akış kullanılır.")
    s.notlar = ("Bu slayt ihtiyacı ve amacı anlatır. Soldaki sütun elle yürütülen bir model geliştirme sürecindeki tipik "
                "durumu, sağdaki sütun platformun bunu nasıl ele aldığını gösterir. Öne çıkan üç sorun: benzer "
                "modellerde bile yöntemin kişiden kişiye değişmesi, bir modelde yapılan üretim ve elemelerin başka "
                "modellerde kullanılamaması ve bunların sonucu olarak sürelerin uzaması. Sağdaki maddeler platformda "
                "bugün çalışan özelliklerdir. Üretilen değişkenlerin kalıcı kataloğu 05.4 adımıdır ve sıradadır. "
                "Soldaki ifadeler genel çerçevedir; kendi ekibinizin durumuna göre düzenleyin.")
    return s


def slayt_prensip():
    s = Slayt("AKIS", B1, "Çalışma Prensibi ve Roller",
              "Dataiku içinde çalışan bir web uygulaması: ham veriden modele giden yolu adım adım yürütür. Her adımda "
              "sıra aynıdır.")
    roller = [
        ("islem", "Kod ölçer",
         ["Sayımı ve ölçümü verinin tamamında, örnekleme yapmadan yapar",
          "Sayıya dayanan öneriyi kendisi verir; gerekçesini ölçtüğü değerle yazar",
          "Yapay zekânın cevabını denetler: sayılar, kolon adları ve formüller kontrol edilir"],
         "Eksik oranı, tekil değer sayısı, bilgi değeri (IV)"),
        ("gri", "Yapay zekâ önerir",
         ["Kolon adlarının ve açıklamalarının anlamını yorumlar",
          "Anlam gerektiren yerde öneri verir; gerekçesini kodun ölçtüğü sayılara dayandırır",
          "Sayı hesaplamaz, veriyi değiştirmez, karar vermez"],
         "Bir kolonun açıklamasından geleceğe baktığını okur ve sızıntı riski olarak işaretler"),
        ("onay", "Kullanıcı karar verir",
         ["Ölçümü, öneriyi ve gerekçeyi aynı kartta görür",
          "Öneriyi kabul eder, değiştirir, ekler ya da çıkarır",
          "Onaylamadığı hiçbir şey veriye uygulanmaz; son karar her zaman kullanıcınındır"],
         "Neredeyse sabit bir kolonu tutar ya da çıkarır"),
    ]
    rw, rh = 3.75, 2.86
    for i, (tur, ad, liste, ornek) in enumerate(roller):
        x = 0.5 + i * (rw + 0.54)
        s.kutu(x, 1.56, rw, rh, tur, "rol " + ad)
        s.daire(i + 1, x + 0.48, 1.96, 0.46, boy=15, ad="rol no %d" % (i + 1))
        s.yazi(ad, x + 0.86, 1.73, 2.75, 0.46, boy=16, kalin=True, renk=KIR, hiza="l")
        s.yazi(maddeler(liste), x + 0.22, 2.34, rw - 0.44, 1.42, boy=11, hiza="l", dikey="t", bosluk=4)
        s.hat(x + 0.22, 3.8, x + rw - 0.22, 3.8, "örnek çizgisi", SOLUK, 0.75)
        s.yazi([[R("Örnek:  ", kalin=True, renk=KIR), ornek]], x + 0.22, 3.84, rw - 0.44, 0.52, boy=10.5, hiza="l")
        if i < 2:
            s.ok(x + rw + 0.06, 2.99, x + rw + 0.48, 2.99, "ok rol %d" % i)
    s.kutu(0.5, 4.56, 12.33, 0.44, "veri", "karardan sonra")
    s.yazi([[R("Karardan sonra  ", kalin=True),
             "kod kararı güncel veriye uygular; karar, gerekçe ve üretim kodu kaydedilir. İstenen adıma geri dönülebilir."]],
           0.7, 4.56, 11.93, 0.44, boy=12, renk=BEYAZ)
    s.etiket("Altyapı", 0.5, 5.12)
    altyapi = [
        ("Dataiku içinde", "Tarayıcıdan, Dataiku projesinin içinden açılır; yetkili olunan veri setleri listelenir"),
        ("Tam veri", "Sayımlar verinin tamamında yapılır; büyük tablolar Spark ile kümede işlenir"),
        ("Kaynak veri korunur", "Seçilen veri setine ve sözlüğe yazılmaz; platform kendi kopyalarıyla çalışır"),
        ("Proje hafızası", "Onaylanan tanımlar, ad parçaları ve kararlar saklanır; sonraki çalışmada hazır gelir"),
    ]
    nw = (12.33 - 0.75) / 4
    for i, (ad, aciklama) in enumerate(altyapi):
        x = 0.5 + i * (nw + 0.25)
        s.kutu(x, 5.4, nw, 1.02, "gri", "altyapı " + ad)
        s.yazi([R(ad, kalin=True, boy=12, renk=KIR), R(aciklama, boy=10.5)], x + 0.12, 5.4, nw - 0.24, 1.02, bosluk=2)
    s.dipnot("Sohbet 02.2 Kural Tabanlı Değişken Üretimi adımında açılır; o ana kadar seçimler kartlarla yapılır, "
             "gerekçe kartın içinde yazar.")
    s.notlar = ("Platformda üç rol vardır ve sıra her adımda aynıdır. Önce kod veriyi sayar ve ölçer. Yapay zekâ (bir dil "
                "modeli) anlam gerektiren yerde öneri verir; gerekçesini kodun ölçtüğü sayılara dayandırır, kendisi sayı "
                "hesaplamaz. Kullanıcı ölçümü, öneriyi ve gerekçeyi aynı kartta görür; kabul eder, değiştirir, ekler ya "
                "da çıkarır. Son karar her zaman kullanıcınındır. Karardan sonra kod kararı veriye uygular ve kaydeder. "
                "Her adımda yapay zekâ olmak zorunda değildir: sayıya dayanan önerileri kod kendisi verir. Sonraki "
                "slaytlarda her adımın kutusunda kimin ne yaptığı ayrıca yazar. Dil modeline Dataiku'nun LLM bağlantısı "
                "üzerinden erişilir.")
    return s


def slayt_akis():
    s = Slayt("AKIS", B1, "İş Akışı · Beş Faz ve Adımları",
              "Web uygulamasındaki İş Akışı ile aynı sıra: beş faz vardır, her faz bir öncekinin çıktısını kullanır.")
    fazlar = [
        ("01", "Çalışma Kurulumu", "Veri seti, sözlük, kolon rolleri ve örneklem tasarımı", "g",
         [("01.1", "Başlangıç Seçimi", "g", 0), ("01.2", "Veri Seti, Sözlük ve Kolon Rolleri", "g", 0),
          ("01.2.1", "Baz Veri Seti ve Baz Sözlük", "g", 1), ("01.2.2", "Kolon Rolleri", "g", 1),
          ("01.2.3", "Eksik Sözlük Tanımları", "g", 1), ("01.2.4", "Sözlük ve Kolon Adı Kontrolü", "g", 1),
          ("01.3", "Değişken Listesi ve Tip Kontrolü", "g", 0),
          ("01.4", "Örneklem ve Doğrulama Tasarımı", "g", 0)],
         "Güncel Veri ve Sözlük", "Geliştirildi"),
        ("02", "Değişken Mühendisliği", "Profil, kural tabanlı ve AI destekli üretim", "s",
         [("02.1", "Veri Profili ve Kalite", "g", "verinin kusurları bulunur"),
          ("02.2", "Kural Tabanlı Değişken Üretimi", "s", "bilinen dönüşümlerle yeni değişkenler"),
          ("02.3", "AI Değişken Keşfi", "r", "yapay zekâ ile yeni değişken fikirleri")],
         "Yeni Değişkenler", "02.2 üzerinde çalışılıyor"),
        ("03", "Veri Anlama ve Hazırlama", "SFA, stabilite ve analitik baz set", "r",
         [("03.1", "Tek Değişken Analizi (SFA)", "r", "her değişkenin hedefle ilişkisi"),
          ("03.2", "Stabilite Analizi (PSI)", "r", "dağılım zamanla kayıyor mu"),
          ("03.3", "Analitik Baz Set", "r", "temizlenmiş ve dondurulmuş set")],
         "Analitik Baz Set", "Sırada"),
        ("04", "Değişken Değerlendirme", "Sızıntı kontrolü ve aday değişken seti", "r",
         [("04.1", "Sızıntı Kontrolü", "r", "hedefi ele veren değişkenler ayrılır"),
          ("04.2", "Aday Değişken Seti", "r", "tekrar eden ve zayıf değişkenler elenir")],
         "Aday Değişken Seti", "Sırada"),
        ("05", "Modelleme ve Finalizasyon", "Model seçimi, katkı ölçümü ve doğrulama", "r",
         [("05.1", "Model Karşılaştırması", "r", "yeni değişkenlerin katkısı ölçülür"),
          ("05.2", "Algoritma Seçimi", "r", "dört algoritma aynı koşulda"),
          ("05.3", "Model Finalizasyonu", "r", "son eğitim, doğrulama, kayıt"),
          ("05.4", "Değişken Kataloğu", "r", "her değişkenin formülü ve kodu")],
         "Final Model ve Katalog", "Sırada"),
    ]
    enler, ara, x = [3.0, 2.2, 2.2, 2.2, 2.2], 0.1325, 0.5
    for i, (no, ad, ozet, durum, adimlar, cikti, durum_yazi) in enumerate(fazlar):
        w = enler[i]
        tur = {"g": "veri", "s": "simdi", "r": "soluk"}[durum]
        ana = BEYAZ if durum == "g" else (KIR if durum == "s" else GRI)
        s.kutu(x, 1.54, w, 0.7, tur, "faz " + no)
        s.yazi([R(no, kalin=True, boy=15, renk=ana), R(ad, kalin=True, boy=12, renk=ana)], x + 0.08, 1.54, w - 0.16, 0.7)
        if i < 4:
            s.ok(x + w + 0.01, 1.89, x + w + ara - 0.01, 1.89, "ok faz %d" % i, KIR if durum != "r" else SOLUK)
        s.yazi(ozet, x + 0.05, 2.28, w - 0.1, 0.42, boy=10, egik=True, renk=GRI)
        s.kutu(x, 2.76, w, 2.2, "cerceve", "adımlar " + no)
        satirlar = []
        for kod, adim, d, ek in adimlar:
            # ek: 1 ise alt adim (girintili); metin ise adimin kisa aciklamasi (alt satirda, soluk)
            bas = u"\u00a0\u00a0\u00a0\u00a0" if ek == 1 else ""
            if d == "g":
                satirlar.append([R(bas + kod + "  ", kalin=True, renk=KIR), adim])
            elif d == "s":
                satirlar.append([R(bas + kod + "  " + adim, kalin=True, renk=KIR)])
            else:
                satirlar.append([R(bas + kod + "  ", kalin=True, renk=GRI), R(adim, renk=GRI)])
            if ek and ek != 1:
                satirlar.append([R(ek, boy=9.5, egik=True, renk=GRI)])
        s.yazi(satirlar, x + 0.12, 2.84, w - 0.24, 2.04, boy=10.5, hiza="l", dikey="t", bosluk=3.5)
        s.ok(x + w / 2, 4.98, x + w / 2, 5.12, "ok çıktı " + no, KIR if durum != "r" else SOLUK)
        s.kutu(x, 5.14, w, 0.44, "veri" if durum != "r" else "soluk", "çıktı " + no)
        s.yazi(cikti, x + 0.05, 5.14, w - 0.1, 0.44, boy=11.5, kalin=True, renk=BEYAZ if durum != "r" else GRI)
        s.yazi(durum_yazi, x, 5.62, w, 0.24, boy=10, kalin=(durum == "s"), renk=KIR if durum == "s" else GRI)
        x += w + ara
    s.kutu(0.5, 5.96, 12.33, 0.56, "gri", "sıra neden böyle")
    s.yazi([[R("Sıra neden böyle:  ", kalin=True, renk=KIR),
             "Profil üretimden önce gelir; boş, sabit ve kimlik benzeri kolonlardan değişken üretilmesin. Tek değişken "
             "analizi ve stabilite üretimden sonra gelir; ham ve üretilen değişkenlerin hepsi aynı ölçümden geçsin."]],
           0.7, 5.96, 11.93, 0.56, boy=10.5, hiza="l")
    s.dipnot("Dolu kırmızı kutu: geliştirildi · kalın çerçeve: üzerinde çalışılıyor · kesik çerçeve: sırada. Sonraki "
             "slaytlar bu sırayı izler.")
    s.notlar = ("Bu slayt web uygulamasının sol tarafındaki İş Akışı ağacının aynısıdır. Beş faz vardır ve her faz bir "
                "öncekinin çıktısını kullanır. 01 Çalışma Kurulumu ve 02.1 Veri Profili ve Kalite geliştirildi; şu an "
                "02.2 Kural Tabanlı Değişken Üretimi üzerinde çalışılıyor. 02.3 ve sonrasının ilk sürümleri kodda var. "
                "Sıranın gerekçesi: kusurlu kolonlardan değişken üretilmesin diye profil üretimden önce gelir; tek "
                "değişken analizi ve stabilite, ham ve üretilen değişkenlerin tamamına birlikte uygulansın diye "
                "üretimden sonra gelir. Sonraki slaytlar her adımı aynı düzende anlatır: ne yapılır, neden gerekli, "
                "örnek. Adım kutusunun altındaki satır kimin ne yaptığını söyler.")
    return s


def slayt_kurulum_veri():
    s = Slayt("AKIS", B2, "01 Çalışma Kurulumu · Veri Seti ve Sözlük",
              "Çalışmanın hangi tabloyla ve hangi sözlükle yürüyeceği belirlenir; platform bundan sonra kendi "
              "kopyalarıyla çalışır.")
    s.adim_tablosu(1.5, [
        ("g", "01.1", "Başlangıç Seçimi", "Karar: kullanıcı",
         "Çalışmanın nereden başlayacağı seçilir. Baz Veri Seti Mevcut: modellemeye girecek tablo hazırdır. Kaynak "
         "Tablolar Mevcut: baz veri seti, seçilen kaynak tablolar birleştirilerek kurulur. Sözlük iki seçenekte de "
         "isteğe bağlıdır.",
         "Her ekibin verisi aynı hazırlıkta gelmez. Sonraki adımlar bu seçime göre şekillenir: tablo hazırsa doğrudan "
         "seçilir, değilse önce birleştirme planı çıkarılır.",
         "Tek modelleme tablosu varsa birinci seçenek; müşteri, işlem ve ürün tabloları ayrı duruyorsa ikinci "
         "seçenek."),
        ("g", "01.2.1", "Baz Veri Seti ve Baz Sözlük", "Kopya ve sayım: kod · Seçim: kullanıcı",
         "Veri seti ve bir ya da birden çok sözlük seçilir. Kod ikisinin birebir kopyasını alır (baz kopya) ve "
         "sözlüğün kolonların ne kadarını tanımladığını hesaplar. Sonraki bütün değişiklikler ayrı bir güncel kopyaya "
         "yazılır.",
         "Seçilen veri setine ve sözlüğe hiçbir zaman yazılmaz. Baz kopya değişmediği için her adım geri alınabilir "
         "ve güncel hâl başlangıçla karşılaştırılabilir.",
         [[K("V8_BAZ_VERI"), " ve ", K("V8_BAZ_SOZLUK"), " bir kez yazılır."],
          [K("V8_UPDT_VERI"), " ve ", K("V8_UPDT_SOZLUK"), " adım adım güncellenir. V8 çalışmanın kısa adıdır."]]),
        ("g", "01.2.1.1", "Sözlük Birleştirme", "Karar: kullanıcı",
         "Birden çok sözlük seçildiyse tek sözlükte birleştirilir. Aynı kolonun sözlüklerde farklı tanımı varsa bu "
         "kolonlar listelenir; kullanıcı kalacak tanımı seçer ya da kendisi yazar. Çakışma yoksa adım sorulmadan "
         "geçilir.",
         "Bir tablonun kolon açıklamaları farklı sözlüklere dağılmış olabilir. Hangi tanımın geçerli olduğu belirsiz "
         "kalırsa sonraki adımlar yanlış anlam üzerine kurulur.",
         [[K("BAL_AMT"), " için bir sözlükte bakiye tutarı, öbüründe ay sonu bakiyesi yazıyor; kullanıcı birini seçer "
                         "ya da doğrusunu yazar."]]),
    ], 1.44)
    s.dipnot("Kaynak tablolarla başlanırsa tablolar ve sözlükleri seçilir; birleştirme planını yapay zekâ önerir, "
             "kullanıcı onaylar. Her satır yalnız kendi tarihinden önceki bilgiyi görür.")
    s.notlar = ("01 fazı geliştirildi. Başlangıçta iki seçenek açıktır: baz veri seti mevcut ya da kaynak tablolar "
                "mevcut. Üçüncü seçenek olan otomatik pilot şu an kapalıdır. Sözlük isteğe bağlıdır; seçilmezse bütün "
                "kolonlar 01.2.3 adımında tanımlanır. Veri kuralı bu adımda başlar: seçilen veri setine ve sözlüğe "
                "yazılmaz. Platform bir çalışma için dört veri seti yazar: baz veri ve baz sözlük (birebir kopya, bir "
                "kez yazılır, değişmez) ile güncel veri ve güncel sözlük (her adımın sonucuyla güncellenir). Bir veri "
                "setiyle daha önce kullanılan sözlük seçili gelir. Örnekteki adlar gösterim amaçlıdır.")
    return s


def slayt_kurulum_rol():
    s = Slayt("AKIS", B2, "01 Çalışma Kurulumu · Kolon Rolleri ve Sözlük Tanımları",
              "Neyin tahmin edileceği ve her kolonun ne anlama geldiği netleştirilir; bilgi taşımayan kolonlar baştan "
              "ayrılır.")
    s.adim_tablosu(1.5, [
        ("g", "01.2.2", "Kolon Rolleri", "Aday listesi: kod · Karar: kullanıcı",
         "Model tipi, hedef, kimlik ve dönem kolonu belirlenir. Kod hedef olabilecek kolonları verinin tamamından "
         "çıkarır (sınıflandırmada yalnız 0 ve 1 değeri alan kolonlar) ve hedefin dağılımını gösterir. Tablonun "
         "önceki onaylı rolleri dolu gelir.",
         "Bütün ölçümler hedefe göre yapılır. Dönem, zamana göre bölmeyi ve dönem kontrollerini; kimlik, aynı "
         "müşterinin satırlarını bir arada tutmayı sağlar. Rol kolonları hiçbir dönüşüme girmez.",
         [["Hedef ", K("DEFAULT_FLAG"), " (0 ve 1)"], ["Kimlik ", K("CUSTOMER_ID")], ["Dönem ", K("SNAPSHOT_DATE")],
          "Şu an açık model tipi: sınıflandırma."]),
        ("g", "01.2.3", "Eksik Sözlük Tanımları", "Öneri: hafıza ve yapay zekâ · Karar: kullanıcı",
         "Sözlükte tanımı olmayan kolonlar listelenir. Tanım önce onaylı tanım hafızasından gelir; yoksa yapay zekâ, "
         "onaylı ad parçalarını kesin bilgi sayarak önerir. Kullanıcı düzeltir; onayladıkları sözlüğe eklenir. Hedef, "
         "kimlik ve dönemin tanımı zorunludur.",
         "Tanımı olmayan kolonu ne insan ne de sonraki adımlardaki yapay zekâ doğru yorumlayabilir; değişken üretimi "
         "kolonun anlamına dayanır.",
         [["Adı yalnız sayıyla ayrılan kolonlar ailedir. ", K("TXN_3D_CNT"), " için son 3 günde işlem adedi yazılır; ",
           K("TXN_7D_CNT"), " tanımı sayı değiştirilerek alır."]]),
        ("g", "01.2.3.1", "Tanımsız ve Sorunlu Kolonlar", "Tespit: kod · Karar: kullanıcı",
         "Kod üç grubu listeler: tamamen boş kolonlar, tek değerli kolonlar ve hâlâ tanımı olmayan kolonlar. İlk iki "
         "grup güncel veriden ve sözlükten her zaman çıkarılır; tanımsız kolonlarda çıkarma kararını kullanıcı verir.",
         "Boş ve tek değerli kolon modele bilgi katmaz; tanımsız kolon yorumlanamaz. Burada ayrıldıkları için sonraki "
         "ad ve sözlük kontrollerinde bunlara zaman harcanmaz.",
         "Kartta nedeni yazar: bütün satırlarda aynı değer (7) var ve boş hücre yok. Kolon yalnız platformun "
         "kopyasından çıkar, kaynak tablo değişmez."),
    ], 1.44)
    s.dipnot("Örneklerdeki kolon adları gösterim amaçlıdır.")
    s.notlar = ("Kolon rollerinde ilk seçim model tipidir; şu an seçilebilen tek tip sınıflandırmadır, öbür tipler "
                "kapalı görünür. Eksik tanımlarda öncelik sırası şöyledir: aynı veri setinde daha önce onaylanan tanım "
                "doğrudan gelir; yoksa yapay zekâ önerir ve önerirken hafızadaki onaylı ad parçalarını ve dönem "
                "kalıplarını kesin bilgi olarak kullanır. Ailede yapay zekâ yalnız bir kolonun tanımını yazar; tanım "
                "kardeş kolonlara sayı değiştirilerek kodla aktarılır. Tanımsız ve sorunlu kolonlar adımında üç grup da "
                "boşsa adım sorulmadan geçilir.")
    return s


def slayt_sozluk():
    s = Slayt("AKIS", B2, "01.2.4 Sözlük ve Kolon Adı Kontrolü",
              "Sözlüğe de kolon adlarına da tam güvenilemez. Amaç, sonraki adımlardaki yapay zekânın da insanın da her "
              "kolonu kesin anlamasıdır.")
    s.adim_tablosu(1.5, [
        ("g", "01.2.4.1", "Dönem Bilgisi", "Öneri: yapay zekâ · Onay: kullanıcı",
         "Adlardaki sayılı zaman parçaları bulunur, anlamları onaylanır. Parça yalnız birimi söyler; dönemin yönü "
         "burada değil, kolon bazında belirlenir.",
         "Aynı parça farklı kolonlarda farklı yöne bakabilir. Yön ada göre varsayılsaydı geleceğe bakan kolon geçmişe "
         "bakıyor sanılırdı.",
         [[K("30D"), ": 30 gün"], [K("M3"), " ve ", K("3_M"), " aynı kalıptır: 3 ay"]]),
        ("g", "01.2.4.2", "Ad Parçaları", "Öneri: yapay zekâ · Onay: kullanıcı",
         "Kalan parçaların (kısaltmalar ve sözcükler) anlamı ve adlarda kullanılacak standart yazılışı onaylanır. Aynı "
         "şeyi anlatan farklı yazılışlar tek yazılışta birleşir.",
         "Aynı kavram farklı kısaltmalarla yazılırsa aynı ölçünün kolonları aile olarak tanınmaz. Onaylanan anlam "
         "hafızada kalır, sonraki çalışmada yeniden sorulmaz.",
         [[K("TRX"), " ve ", K("TXN"), ": işlem; standart yazılış ", K("TXN")],
          [K("AMT"), ": tutar · ", K("CNT"), ": adet"]]),
        ("g", "01.2.4.3", "Kolon Kartları", "Kart: kod · Açıklama: yapay zekâ · Onay: kullanıcı",
         "Her kolonun kartı onaylı parçalardan kodla kurulur. Yapay zekâ kartı sözlükteki tanımla karşılaştırıp tek ve "
         "açık bir açıklama yazar. Dönemin yönü açıklamadan okunur; okunamazsa kullanıcıya sorulur.",
         "Ad ile sözlük tanımı çelişebilir ya da tanım eksik kalabilir. Çelişki kullanıcıya soru olarak gelir, "
         "sessizce geçilmez.",
         [[K("LOAN_DUE_AMT_30D"), ", sözlükte: 30 gün sonra vade tutar. Okunan yön: sonra. Onaylanan açıklama: 30 gün "
                                  "sonra vadesi gelecek tutar."]]),
        ("g", "01.2.4.4", "Kolon Adları", "Ad: kod · Onay: kullanıcı",
         "Yeni adlar standart yazılışlarla ve Ad Standardı sırasıyla kodla kurulur; dönem, kolonun yönüne göre "
         "yazılır. Yeni ad yalnız platformun kopyalarında geçerlidir, eski ad sözlükte saklanır.",
         "Standart ad kolonun ne olduğunu tek bakışta söyler. Geleceğe bakan kolon 02.1'de sızıntı riski olarak "
         "sorulur; 02.2'de aileler bu adlardan kurulur.",
         [[K("TXN_OUT_AMT_30D", 9), u" \u2192 ", K("TXN_OUT_AMT_L30D", 9)],
          [K("LOAN_DUE_AMT_30D", 9), u" \u2192 ", K("LOAN_DUE_AMT_A30D", 9)],
          [K("BAL_30D", 9), u" \u2192 ", K("BAL_B30D", 9)]]),
    ], 1.06)
    s.dipnot("Kontrol isteğe bağlıdır: adım adım yapılır, atlanır ya da aynı veri seti için önceki onaylı kontrol "
             "uygulanır. Yön harfleri: son L, sonra A, önce B. Örnekler gösterim amaçlıdır.")
    s.notlar = ("Dört alt adım sırayla çalışır ve her biri bir öncekinin onayladığını kesin bilgi olarak kullanır; her "
                "satır kullanıcı onaylamadan geçilmez. Kilit nokta dönemdir: 30D adda yalnız 30 gün demektir. Yönü her "
                "kolonda ayrı belirlenir: önce kullanıcının seçimine, sonra açıklamadaki ifadeye (kod okur), sonra "
                "yapay zekânın önerisine bakılır; hiçbiri yoksa kullanıcıya sorulur. Sekiz hazır tür vardır: son (L), "
                "önce (B), sonraki (N), sonra (A), öncesi ve sonrası (PM), takvim (C), beri (S) ve süre. Açıklamayı "
                "yapay zekâ üç aşamada yazar: yazar, denetçi, gerekirse karar; karttaki sayıların açıklamada geçtiğini "
                "kod denetler. Güncel sözlükte yeni ad, eski ad, onaylanan açıklama ve ilk açıklama birlikte durur. "
                "Onaylanan anlamlar hafızaya yazılır; aynı veri seti için önceki onaylı kontrol tek seçimle yeniden "
                "uygulanabilir.")
    return s


def slayt_kurulum_bolme():
    s = Slayt("AKIS", B2, "01 Çalışma Kurulumu · Tip Kontrolü ve Bölme",
              "Kurulumun son iki adımı: liste ve tipler son kez gözden geçirilir, veri eğitim ve ölçüm setlerine "
              "ayrılır.")
    y = s.adim_tablosu(1.5, [
        ("g", "01.3", "Değişken Listesi ve Tip Kontrolü", "Denetim: kod · Karar: kullanıcı",
         "Değişken listesi, tanımlar ve tipler bölmeden önce son kez gözden geçirilir. Kullanıcı yalnız verinin izin "
         "verdiği tip dönüşümlerini seçebilir; kod seçimi kolonun tamamında dener, tek değer bile çevrilemezse kabul "
         "etmez. Onayla güncel veri ve güncel sözlük yazılır.",
         "Kaynak tabloda tip çoğu zaman yanlış gelir. Yanlış tipli kolonda ölçümler anlamsızlaşır: sayı sanılan kod "
         "alanı yüzlerce aralığa bölünür, metin sanılan tutar tek tek etiket olur.",
         "Metin olarak gelen 1.234,50 sayıya, tam sayı olarak gelen 20240131 tarihe çevrilir; sayı gibi görünen şube "
         "kodu kategorik yapılır."),
        ("g", "01.4", "Örneklem ve Doğrulama Tasarımı", "Öneri: kod · Karar: kullanıcı",
         "Verinin nasıl bölüneceği belirlenir: Train, isteğe bağlı Test ve Validasyon. Kod veriye bakarak bir ayar "
         "önerir ve gerekçesini yazar. Kullanıcı öneriyi uygular ya da özel ayar seçer: zamana göre ya da rastgele, "
         "satır ya da kimlik bazında.",
         "Bu sınır sızıntı sınırıdır: doldurma değerleri, dönüşüm ayarları ve eğitim yalnız Train setinden hesaplanır. "
         "Validasyon modelin hiç görmediği veridir; son ölçüm orada yapılır.",
         "Zamana göre bölme: eski dönemler Train, son dönemler Validasyon. Kimlik bazında: aynı müşterinin satırları "
         "aynı tarafta kalır."),
    ], 1.6)
    s.etiket("01 fazının çıktıları", 0.5, y + 0.1)
    ciktilar = [("Baz Kopya", "girdinin değişmeyen kopyası"),
                ("Güncel Veri ve Sözlük", "tipler, tanımlar, yeni adlar"),
                ("Bölme", "her satırın hangi sette olduğu"),
                ("Proje Hafızası", "onaylanan tanımlar ve anlamlar")]
    ow = (12.33 - 0.75) / 4
    for i, (ad, alt) in enumerate(ciktilar):
        s.veri(0.5 + i * (ow + 0.25), y + 0.4, ow, 0.74, ad, alt)
    s.dipnot("Set adları: Train (MS), Test (OOS), Validasyon (OOT).")
    s.notlar = ("Tip kontrolünde kullanıcı serbestçe tip atayamaz; yalnız verinin izin verdiği dönüşümler seçilebilir. "
                "Uygun olmayan seçenek listeden silinmez, kilitli görünür ve nedeni yazar. Sayısal bir kolon ancak en "
                "çok 50 farklı değer alıyorsa kategorik yapılabilir. Bölmede üç set vardır: model Train setinde öğrenir, "
                "ayarlar isteğe bağlı Test setinde seçilir, son ölçüm Validasyon setinde yapılır. Kod öneriyi veriden "
                "çıkarır: dönem kolonu ve yeterli sayıda dönem varsa zamana göre bölme, aynı kimliğin birden çok satırı "
                "varsa kimlik bazında bölme önerir. Zamana göre bölmede iki set arasına boşluk dönemi konabilir. Bölme, "
                "güncel veriye bir set kolonu olarak yazılır.")
    return s


def slayt_profil():
    s = Slayt("AKIS", B3, "02.1 Veri Profili ve Kalite",
              "Değişken üretmeden önce verinin kusurları bulunur; boş, sabit ya da hatalı kolondan değişken "
              "üretilmesin.")
    asamalar = [
        ("1  Kontrol Eşikleri", "onay", "20 eşik önerilen değeriyle gelir; kullanıcı onaylar"),
        ("2  Ölçüm", "islem", "Kod 26 kontrolü verinin tamamında yapar"),
        ("3  Karar Kartı", "onay", "Her bulgu ölçülen değeri, önerisi ve gerekçesiyle"),
        ("4  Uygulama", "islem", "Onaylanan kararlar güncel veriye yazılır"),
    ]
    aw = (12.33 - 3 * 0.3) / 4
    for i, (ad, tur, aciklama) in enumerate(asamalar):
        x = 0.5 + i * (aw + 0.3)
        s.kutu(x, 1.5, aw, 0.6, tur, ad)
        s.yazi([R(ad, kalin=True, renk=KIR, boy=11.5), R(aciklama, boy=9.5, renk=GRI)], x + 0.08, 1.5, aw - 0.16, 0.6)
        if i < 3:
            s.ok(x + aw + 0.03, 1.8, x + aw + 0.27, 1.8, "ok aşama %d" % i)
    s.adim_tablosu(2.2, [
        ("g", "", "Üretime girmez", "7 kontrol · öneri: kod",
         "Eksik oranı yüksek · sabit ya da tek değerli · kimlik benzeri · kardinalitesi aşırı yüksek · tarih kolonu · "
         "aynı içerikli kolonlar · neredeyse aynı kolonlar",
         "Bu kolonlardan üretilen değişken bilgi taşımaz ya da kimliği ezberler. İşe yarayan bir çözüm varsa önerilir.",
         "Çoğu boş kolonda dolu mu bayrağı; çok değerli kolonda gruplama; tarihte dönem sonuna gün farkı."),
        ("g", "", "Kararınıza bırakılır", "7 kontrol · öneri: kod ve yapay zekâ",
         "Gelecek penceresi (sızıntı riski) · hedefle neredeyse birebir · dönemden sonraki tarih · neredeyse sabit · "
         "dönemde boş ya da sabit · dönemler arası eksik sıçraması · dönemler arası değer kayması",
         "Kolon kullanılabilir de olabilir, riskli de; bunu iş bilgisi belirler. Kullanıcı tutar ya da çıkarır.",
         [[K("LOAN_DUE_AMT_A30D"), " geleceğe bakıyor: model kullanılırken bilinmeyecek bir bilgi, sızıntı riski olarak "
                                   "sorulur."]]),
        ("g", "", "Düzeltme seçilir", "7 kontrol · öneri: kod ve yapay zekâ",
         "Gizli eksik (özel kod) · karışık eksik kodlaması · metin olarak yazılmış boş · kategori yazım tutarsızlığı · "
         "beklenmeyen negatif · uç değer yoğunluğu · ondalık hassasiyeti",
         "Kolon değerlidir ama içindeki kusur ölçümü bozar. Kolon düzeltilmiş hâliyle üretime girer.",
         "Boş yerine 9999 yazılmışsa boşa çevrilir. En büyük değer, değerlerin yüzde 99'unun altında kaldığı sınırın "
         "100 katını aşıyorsa kırpma önerilir."),
        ("g", "", "Bilgi için gösterilir", "5 kontrol · işlem yapılmaz",
         "Sıfır yoğunluğu · pencere tutarlılığı · tutar ve adet uyumsuzluğu · tekrar eden satır · setler arası çakışma",
         "Kolonu elemeyi gerektirmez ama sonuçları yorumlarken bilinmesi gerekir.",
         "Son 30 günün toplamı son 90 günün toplamından büyük çıkıyorsa pencere tutarsızlığı olarak gösterilir."),
    ], 0.9, basliklar=("Sonuç", "Kontroller", "Neden Gerekli", "Örnek"))
    s.dipnot("Öneri kaynağı her satırda yazar. Yapay zekâ yalnız anlam gerektiren beş kontrolde ve aynı içerikli "
             "kolonlarda önerir; öbür öneriler koddan gelir. Bu adımda sohbet yoktur.")
    s.notlar = ("02.1 geliştirildi. Önce eşikler sorulur, kullanıcı onaylar; kontroller bu eşiklerle verinin tamamında "
                "çalışır. Karar kartında satırlar renklidir: sorunsuz, dikkat, üretime girmez. Yapay zekânın öneri "
                "verdiği beş kontrol: gelecek penceresi, hedefle neredeyse birebir, dönemden sonraki tarih, gizli eksik "
                "ve karışık eksik kodlaması; bunlar kolonun anlamına bakmayı gerektirir. Çözüm seçeneği yalnız işe "
                "yarayacaksa sunulur. Öğrenilen her şey (gruplar, sınırlar) yalnız Train setinden gelir. Onayla "
                "düzeltmeler ve çözüm kolonları güncel veriye yazılır; üretime girmeyen ve çıkarılan kolonlar güncel "
                "veriden çıkar. Örnekteki değerler gösterim amaçlıdır.")
    return s


def slayt_uretim():
    s = Slayt("AKIS", B3, "02.2 Kural Tabanlı Değişken Üretimi · İşleyiş",
              "Var olan kolonlardan oran, büyüme, eğilim gibi bilinen dönüşümlerle yeni değişkenler türetilir. Şu an "
              "üzerinde çalışılan adım.")
    s.adim_tablosu(1.5, [
        ("s", "", "1. Hazırlık", "Kod",
         "Kolonlar birlikte değerlendirilecek birimlere ayrılır: tek kolon, aynı ölçünün farklı dönemleri (aile) ve "
         "anlamlı kolon çiftleri. 41 dönüşümden hangilerinin her birimde yapılabileceği belirlenir.",
         "Her dönüşüm her kolona uymaz. Uygunluk baştan belli olursa anlamsız değişken üretilmez; kullanıcı neden "
         "yapılamadığını kartta görür.",
         [[K("TXN_OUT_AMT_L30D"), ", ", K("L90D"), " ve ", K("L180D"), " bir ailedir. Logaritma yalnız negatif "
                                                                     "olmayan kolonda kullanılabilir."]]),
        ("s", "", "2. Katkı Ölçümü", "Kod",
         "Yapılabilen her dönüşüm Train satırlarında, örnekleme yapılmadan denenir. Bilgi değeri (IV) en iyi kaynağına "
         "göre en az 0,02 artıyor mu ve kaynaklarıyla aynı sıralamayı mı veriyor (0,95 ve üstü ilişki) ölçülür.",
         "Öneri ve karar izlenime değil sayıya dayansın diye ölçüm öneriden önce yapılır. Kaynağının kopyası olan "
         "değişken modele yeni bilgi katmaz.",
         "Kaynağın bilgi değeri 0,10, oranın 0,14 ise artış 0,04: yeni bilgi sayılır. Artış 0,01 olsaydı sayılmazdı."),
        ("s", "", "3. Öneri ve Tamamlama", "Yapay zekâ, ardından kod",
         "Yapay zekâ ölçüme bakarak her birim için dönüşüm önerir ve gerekçesini sayılarla yazar. Kod, ölçüme göre "
         "değerli olup önerilmeyeni ekler, aynı bilgiyi veren tekrarı ayıklar.",
         "Yapay zekâ kolonun anlamını bilir, kod sayıyı; ikisi birbirinin eksiğini kapatır. Öneriyi kimin verdiği "
         "her satırda görünür.",
         "Farklı ailelerden anlamlı çiftleri de yapay zekâ önerir; bu çiftler de aynı ölçümden geçer."),
        ("s", "", "4. Karar ve Üretim", "Kullanıcı, ardından kod",
         "Kullanıcı ölçümü ve öneriyi görür; kartta tek tıkla ekler ya da çıkarır, Plan Üzerine Sohbet'te soru sorar "
         "ya da toplu değişiklik ister. Onayla kod seçilen dönüşümleri üretir ve üretim kodunu kaydeder.",
         "Son seçim iş bilgisi gerektirir. Kaydedilen üretim kodu, aynı değişkenlerin yeniden üretilebilmesini sağlar.",
         "Sohbette eğim nedir diye sorulabilir ya da bir kolon grubuna dönüşüm eklenmesi istenebilir; öneri gelir, "
         "uygulamak kullanıcıya kalır."),
    ], 1.06, basliklar=("Aşama", "Ne Yapılır", "Neden Gerekli", "Örnek"))
    s.dipnot("Sohbet platformda bu adımda açılır. Örnekteki sayılar gösterim amaçlıdır; eşikler: bilgi değeri artışı "
             "0,02, sıra ilişkisi 0,95.")
    s.notlar = ("Şu an üzerinde çalışılan adım. Birim, birlikte değerlendirilen kolon ya da kolon grubudur; örneğin "
                "aynı ölçünün son 30, 90 ve 180 günlük kolonları bir ailedir. Sıra önemlidir: kod önce her dönüşümün "
                "katkısını ölçer, yapay zekâ bu ölçüme bakarak önerir, kod eksik kalanı tamamlar ve tekrarı ayıklar, "
                "kullanıcı bunların hepsini görerek karar verir. Ölçüm yalnız Train satırlarında yapılır: bilgi değeri "
                "(IV) en iyi kaynağa göre en az 0,02 artıyorsa ve kaynaklarla sıra ilişkisi 0,95'in altındaysa dönüşüm "
                "yeni bilgi sayılır. Kart ve sohbet geri bildirimle güncelleniyor; açık konular üretilen değişken "
                "sayısı ve yeni bilgi eşiğidir.")
    return s


def slayt_asamalar():
    s = Slayt("AKIS", B3, "02.2 Kural Tabanlı Değişken Üretimi · Üç Aşama, 41 Dönüşüm",
              "Dönüşümler neye bakarak üretildiklerine göre üç aşamada toplanır; kartta öneriler bu sırayla gösterilir.")
    s.adim_tablosu(1.5, [
        ("s", "", "1. Kolonun kendi dönüşümü", "18 dönüşüm",
         "Tek kolon kendi içinde dönüştürülür: ölçeği düzeltilir, bayrak ya da dilim üretilir, kategori sayıya "
         "çevrilir. Dönüşümlerden: logaritma, karekök, uç kırpma, sıra, sıfır bayrağı, eşit frekans dilimi, frekans "
         "kodlama, WoE, hedef ortalaması.",
         "Ham kolonun dağılımı çoğu zaman çarpıktır; birkaç çok büyük değer ilişkiyi gizler. Kategorik kolon modele "
         "ancak sayıya çevrilerek girer.",
         [[K("TXN_OUT_AMT_L30D"), " kolonunun logaritması: çok büyük tutarların etkisi sıkışır, küçük farklar "
                                  "korunur."]]),
        ("s", "", "2. Aile içi üretim", "13 dönüşüm",
         "Aynı ölçünün farklı dönemleri birbiriyle karşılaştırılır: kısa dönem bölü uzun dönem, önceki döneme göre "
         "büyüme, eğilim, düzensizlik, en yoğun dönemin payı.",
         "Tek dönemin düzeyinden çok zaman içindeki değişim ayırt edicidir: aynı tutarı harcayan iki müşteriden biri "
         "hızlanıyor, öbürü yavaşlıyor olabilir.",
         [[K("TXN_OUT_AMT_L30D"), " bölü ", K("TXN_OUT_AMT_L90D"), ": son 30 günün son 90 güne oranı; harcama "
                                                                 "hızlanıyor mu, yavaşlıyor mu."]]),
        ("s", "", "3. Aileler arası üretim", "10 dönüşüm",
         "Birbiriyle anlamlı ilişkisi olan farklı kolonlar birleştirilir: net akış, işlem başına ortalama tutar, alt "
         "kırılımın toplamdaki payı, tek kanala yoğunlaşma, segment içindeki yer.",
         "Bazı bilgiler tek kolonda yoktur, iki kolonun ilişkisinde ortaya çıkar. Anlamlı çifti yapay zekâ kolonların "
         "anlamından önerir, katkısını kod ölçer.",
         [[K("TXN_IN_AMT_L30D"), " eksi ", K("TXN_OUT_AMT_L30D"), ": net akış; hesaba giren mi fazla, çıkan mı."]]),
    ], 1.44, basliklar=("Aşama", "Ne Yapılır", "Neden Gerekli", "Örnek"))
    s.dipnot("Kartta 41 dönüşümün her biri sade adı, ne yaptığı, bu verideki örneği ve bu veride neden kullanılabilir "
             "ya da kullanılamaz olduğuyla listelenir.")
    s.notlar = ("Aşama, dönüşümün neye baktığını söyler. Birinci aşama tek kolonla, ikinci aşama aynı ölçünün farklı "
                "dönemleriyle, üçüncü aşama birbiriyle ilişkili farklı kolonlarla çalışır. Hangi dönüşüm önerilir: "
                "türetildiği kolonlardan belirgin biçimde daha fazla bilgi taşıyan ve onların kopyası olmayan. Son seçim "
                "kullanıcınındır. Kolon adları 01 fazında standartlaştırılan adlardır; örnekler gösterim amaçlıdır.")
    return s


def slayt_sirada_hazirlama():
    s = Slayt("AKIS", B4, "02.3 ve 03 · Yapay Zekâ ile Keşif, Veri Anlama ve Hazırlama", SIRADA_CUMLE)
    s.adim_tablosu(1.5, [
        ("r", "02.3", "AI Değişken Keşfi", "Öneri: yapay zekâ · Denetim ve hesap: kod",
         "Bilinen kalıpların dışında yeni değişken fikirleri aranır. Yapay zekâ kod yazmaz, yalnız formül önerir; kod "
         "formülü denetler (var olan kolonlar, izinli işlemler; hedef ve kimlik kullanılamaz) ve hesabı kendisi yapar.",
         "Hazır dönüşümler yaygın kalıpları kapsar, veriye özgü fikirler dışarıda kalır. Denetim, önerinin güvenle "
         "çalıştırılmasını sağlar.",
         "Kullanılan limitin toplam limite oranı gibi, iki kolonun anlamına dayanan bir formül."),
        ("r", "03.1", "Tek Değişken Analizi (SFA)", "Ölçüm: kod · Öneri: yapay zekâ · Onay: kullanıcı",
         "Ham ve üretilen her değişkenin hedefle ilişkisi tek tek ölçülür: bilgi değeri (IV), beş dönüşümle ayırma "
         "gücü, hedefe göre aralıklar. Eleme yapılmaz; değişkenin modele hangi hâliyle gireceği önerilir.",
         "Bir değişken ham hâliyle zayıf, aralıklara bölünmüş ya da dönüştürülmüş hâliyle güçlü olabilir. Doğru hâl "
         "baştan seçilirse sonraki elemeler adil olur.",
         "Yaş kolonu modele ham hâliyle değil, hedefe göre bulunan aralıklarla girer."),
        ("r", "03.2", "Stabilite Analizi (PSI)", "Ölçüm: kod",
         "Değişken dağılımlarının zaman içinde kayıp kaymadığı ölçülür: Train seti ile Validasyon seti karşılaştırılır. "
         "Kararsız kolonlar bir sonraki adımda düşürülecekler arasında gösterilir.",
         "Dağılımı zamanla değişen değişken geçmişte iyi ayırsa da yeni dönemde aynı davranmaz; model kullanımda "
         "bozulur.",
         "Kampanya döneminde sıçrayan bir işlem adedi kolonu kararsız çıkar."),
        ("r", "03.3", "Analitik Baz Set", "Plan: kod · Onay: kullanıcı",
         "Kusurlu ve kararsız kolonlar düşürülür, tek değişken analizindeki kararlar uygulanır, kalan eksikler Train "
         "setinin medyanıyla doldurulur ve set dondurulur.",
         "Sonraki adımların hepsi aynı, değişmeyen veride çalışmalıdır; yoksa sonuçlar karşılaştırılamaz. Doldurma "
         "değerinin yalnız Train setinden gelmesi sızıntıyı önler.",
         "Plan düşecek kolonları sebebiyle sayar: eksik, sabit, kimlik benzeri, kararsız."),
    ], 1.06)
    s.dipnot("Örnekler gösterim amaçlıdır.")
    s.notlar = ("Bu dört adımın ilk sürümleri kodda var; henüz 01 ve 02.1'deki yapıya göre ele alınmadı, ayrıntılar "
                "değişebilir. 02.3'te yapay zekânın yazdığı formül kodla denetlenir; geçersiz formül, olmayan kolon ya "
                "da hedefi kullanan öneri reddedilir. 03 fazı üretimden sonra gelir; böylece ham ve üretilen "
                "değişkenlerin hepsi aynı ölçümden geçer. Analitik baz set dondurulduktan sonra sızıntı kontrolü, aday "
                "değişken seti ve modelleme bu sette yapılır.")
    return s


def slayt_sirada_model():
    s = Slayt("AKIS", B4, "04 ve 05 · Değişken Değerlendirme, Modelleme ve Finalizasyon", SIRADA_CUMLE)
    s.adim_tablosu(1.5, [
        ("r", "04.1", "Sızıntı Kontrolü", "",
         "Train satırlarında hedefle ilişkisi aşırı yüksek olan değişkenler sızıntı şüphelisi sayılır; aday sete ve "
         "modele alınmaz.",
         "Hedefi ele veren değişken başarıyı kâğıt üstünde yükseltir, gerçek kullanımda işe yaramaz.",
         "Olaydan sonra dolan bir takip kolonu hedefle neredeyse birebir çıkar."),
        ("r", "04.2", "Aday Değişken Seti", "",
         "Dört aşama sırayla uygulanır: yarı sabit eleme, fazlalık eleme, karşılıklı bilgi skoru, model önemi. Hepsi "
         "yalnız eğitim satırlarında hesaplanır.",
         "Aynı bilgiyi taşıyan değişkenler modeli şişirir. Her değişkenin hangi aşamada elendiği kayıtta kalır.",
         "Birbiriyle çok yüksek ilişkili iki değişkenden bilgi değeri düşük olan elenir."),
        ("r", "05.1", "Model Karşılaştırması", "",
         "Baz değişkenlerle kurulan model ile yeni değişkenlerin eklendiği model aynı bölme ve aynı ayarlarla "
         "karşılaştırılır; ölçüm birkaç kez tekrarlanır.",
         "Asıl soru: üretilen değişkenler ölçülebilir katkı sağladı mı. Tek koşudaki fark tesadüf olabilir.",
         "Fark yüzde 95 güven aralığıyla raporlanır; aralık sıfırı içeriyorsa katkı kanıtlanmamıştır."),
        ("r", "05.2", "Algoritma Seçimi", "",
         "Dört algoritma aynı değişken seti, aynı bölme ve aynı ayarlarla eğitilir; ayırma gücü ve eğitim süresi "
         "karşılaştırılır.",
         "Tek fark algoritma olursa karşılaştırma adil olur; algoritma ölçülerek seçilir.",
         "Ölçütler: ROC-AUC, Gini, KS ve eğitim süresi. Eğitim Dataiku senaryosunda çalışır."),
        ("r", "05.3", "Model Finalizasyonu", "",
         "Seçilen model son hâliyle eğitilir, modelin hiç görmediği sette doğrulanır ve kaydedilir; ardından "
         "validasyon ölçütlerinden geçirilir.",
         "Model kullanıma hazır ve denetlenebilir olmalıdır.",
         "Ölçütler: Gini, Gini düşüşü, KS, skor kararlılığı, yeni değişken katkısı."),
        ("r", "05.4", "Değişken Kataloğu", "",
         "Kabul edilen her değişkenin formülü, kaynak kolonları, çalıştırılabilir kodu, seçim sonucu ve modele katkısı "
         "kalıcı kataloğa yazılır.",
         "Üretilen değişken o modelde kalmasın: başka bir çalışma aynı değişkeni katalogdaki koduyla yeniden üretebilir.",
         "Katalog satırı: ad, formül, kaynak kolonlar, kod, gerekçe, seçim sonucu."),
    ], 0.69)
    s.dipnot("Bu fazlarda kimin önerdiği ve kimin karar verdiği, adımlar ele alınırken 01 ve 02'deki düzene göre "
             "netleşecek. Örnekler gösterim amaçlıdır.")
    s.notlar = ("Bu altı adımın ilk sürümleri kodda var; henüz 01 ve 02.1'deki yapıya göre ele alınmadı, ayrıntılar "
                "değişebilir. 04 fazı dondurulmuş analitik baz sette çalışır ve yalnız eğitim satırlarını kullanır; "
                "böylece seçim kararına ölçüm verisinden bilgi karışmaz. 05.1 asıl soruyu cevaplar: üretilen "
                "değişkenler modele ölçülebilir katkı sağladı mı. Değişken kataloğu, ihtiyaç slaytındaki yeniden "
                "kullanım sorununun karşılığıdır.")
    return s


def slayt_durum():
    s = Slayt("AKIS", B4, "Durum · Geliştirilenler ve Sıradakiler",
              "01 ve 02.1 geliştirildi; şu an 02.2 Kural Tabanlı Değişken Üretimi üzerinde çalışılıyor.")
    s.kutu(0.5, 1.58, 12.33, 2.5, "gri", "akış bandı")
    adimlar = [("01", "Çalışma Kurulumu", "g"), ("02.1", "Veri Profili ve Kalite", "g"),
               ("02.2", "Kural Tabanlı Değişken Üretimi", "s"), ("02.3", "AI Değişken Keşfi", "r"),
               ("03", "Veri Anlama ve Hazırlama", "r"), ("04", "Değişken Değerlendirme", "r"),
               ("05", "Modelleme ve Finalizasyon", "r")]
    sl, cy = 12.33 / 7, 2.55
    s.hat(0.5 + sl / 2, cy, 0.5 + sl / 2 + sl * 6, cy, "akış çizgisi", SOLUK, 1.5, True)
    for i, (no, ad, durum) in enumerate(adimlar):
        cx = 0.5 + sl * i + sl / 2
        d = 0.95 if durum == "s" else 0.8
        if durum == "g":
            s.elips(cx, cy, d, KIR, (KIR, 1, False), "adım " + no)
        elif durum == "s":
            s.elips(cx, cy, d, PEMBE, (KIR, 3, False), "adım " + no)
        else:
            s.elips(cx, cy, d, BEYAZ, (SOLUK, 1.5, True), "adım " + no)
        s.yazi(no, cx - d / 2, cy - d / 2, d, d, boy=14 if len(no) > 2 else 17, kalin=True,
               renk=BEYAZ if durum == "g" else (KIR if durum == "s" else SOLUK))
        s.yazi(ad, cx - sl / 2 + 0.05, cy + 0.54, sl - 0.1, 0.55, boy=12, kalin=True,
               renk=GRI if durum == "r" else KOYU, dikey="t")
        s.yazi("Geliştirildi" if durum == "g" else ("Üzerinde çalışılıyor" if durum == "s" else "Sırada"),
               cx - sl / 2 + 0.05, cy + 1.1, sl - 0.1, 0.28, boy=10.5, kalin=(durum == "s"),
               renk=KIR if durum == "s" else GRI)
        if durum == "s":
            s.kutu(cx - 0.85, 1.67, 1.7, 0.28, "veri", "şu an buradayız")
            s.yazi("Şu an buradayız", cx - 0.85, 1.67, 1.7, 0.28, boy=10.5, kalin=True, renk=BEYAZ)
    kw = (12.33 - 0.5) / 3
    s.kart(0.5, 4.32, kw, 2.0, "gri", "Geliştirilen",
           ["01 Çalışma Kurulumu: veri seti ve sözlük, kolon rolleri, eksik tanımlar, sözlük ve kolon adı kontrolü, "
            "tip kontrolü, bölme",
            "02.1 Veri Profili ve Kalite: 20 eşik, 26 kontrol, düzeltme ve çözüm önerileri"], baslik_boy=14, boy=11.5)
    s.kart(0.5 + kw + 0.25, 4.32, kw, 2.0, "simdi", "Üzerinde çalışılan",
           ["02.2 Kural Tabanlı Değişken Üretimi: kod 41 dönüşümün katkısını ölçer, yapay zekâ ölçüme bakarak önerir, "
            "kullanıcı kartta ve sohbette karar verir",
            "Açık konular: üretilen değişken sayısı ve yeni bilgi eşiği"],
           baslik_boy=14, boy=11.5)
    s.kart(0.5 + 2 * (kw + 0.25), 4.32, kw, 2.0, "soluk", "Sırada",
           ["02.3 AI Değişken Keşfi",
            "03 Veri Anlama ve Hazırlama, 04 Değişken Değerlendirme, 05 Modelleme ve Finalizasyon: ilk sürümleri "
            "kodda var, bu yapıya göre ele alınacak"], baslik_boy=14, boy=11.5)
    s.notlar = ("Durum slaytı. Akış beş fazdan oluşuyor; 01 ve 02.1 geliştirildi, şu an 02.2 üzerinde çalışılıyor. "
                "02.3 ve sonrasının ilk sürümleri kodda var ama bu yapıya göre henüz ele alınmadı.")
    return s


# ===========================================================================
# URETIM VE KAYIT
# ===========================================================================
def uret(zaman=None):
    """Sunumun .pptx icerigini bayt olarak doner. Gorseller her cagrida yeniden okunur."""
    gorselleri_sifirla()
    slaytlar = [slayt_kapak(), slayt_ihtiyac(), slayt_prensip(), slayt_akis(), slayt_kurulum_veri(),
                slayt_kurulum_rol(), slayt_sozluk(), slayt_kurulum_bolme(), slayt_profil(), slayt_uretim(),
                slayt_asamalar(), slayt_sirada_hazirlama(), slayt_sirada_model(), slayt_durum()]
    if KAPANIS:
        slaytlar.append(slayt_kapanis())
    return paketle(slaytlar, "Kurumsal Analitik, Tahminleme ve İçgörü Platformu", zaman)


def _yaz(metin):
    """Ekrana yazar; cikti kodlamasi Turkce harfleri tasimiyorsa hata vermez."""
    try:
        print(metin)
    except UnicodeEncodeError:
        print(metin.encode("ascii", "replace").decode("ascii"))


def _indirme_baglantisi(veri, dosya):
    """Defterde (notebook) calisiyorsa ciktiya indirme baglantisi koyar."""
    try:
        from IPython import get_ipython
        from IPython.display import HTML, display
        kabuk = get_ipython()
    except Exception:
        return False
    if kabuk is None or not hasattr(kabuk, "kernel"):
        return False
    display(HTML(
        '<a download=%s href="data:application/vnd.openxmlformats-officedocument.presentationml.presentation;'
        'base64,%s" style="display:inline-block;padding:8px 16px;background:#%s;color:#fff;border-radius:6px;'
        'text-decoration:none;font-weight:600">Sunumu indir</a>'
        % (quoteattr(dosya), base64.b64encode(veri).decode("ascii"), KIR)))
    return True


def _rapor_yaz():
    """Hangi gorselin bulundugunu ekrana yazar."""
    for satir in gorsel_raporu():
        _yaz(satir)


def kaydet(veri, klasor=None, dosya=DOSYA):
    """Sunumu yazar: klasor verilirse Dataiku managed folder'a, verilmezse
    calisma dizinine (defterde ayrica indirme baglantisi gosterir)."""
    if klasor:
        try:
            import dataiku
        except ImportError:
            raise RuntimeError("KLASOR verildi ama dataiku modülü bulunamadı. Betik Dataiku dışında çalışıyorsa "
                               "KLASOR = None yapın.")
        yol = "/" + dosya.lstrip("/")
        try:
            dataiku.Folder(klasor).upload_stream(yol, veri)
        except Exception as hata:
            raise RuntimeError("Managed folder'a yazılamadı (%s). Klasörün adını ya da kimliğini ve yazma yetkinizi "
                               "kontrol edin. Hata: %s" % (klasor, hata))
        _yaz("Sunum yazıldı. Managed folder: %s, dosya: %s, boyut: %d bayt." % (klasor, yol, len(veri)))
        _rapor_yaz()
        return
    baglanti = _indirme_baglantisi(veri, os.path.basename(dosya))
    try:
        with open(dosya, "wb") as f:
            f.write(veri)
        _yaz("Sunum yazıldı: %s, boyut: %d bayt." % (os.path.abspath(dosya), len(veri)))
    except (IOError, OSError) as hata:
        if not baglanti:
            raise
        _yaz("Yerel dosya yazılamadı (%s)." % hata)
    if baglanti:
        _yaz("İndirmek için yukarıdaki bağlantıya basın. Bağlantı çalışmazsa KLASOR değişkenine bir managed "
             "folder adı yazıp yeniden çalıştırın.")
    _rapor_yaz()


def calistir():
    global GORSEL_DIZIN
    hedef = DOSYA
    for arguman in sys.argv[1:]:
        if arguman.lower().endswith(".pptx"):
            hedef = arguman
        elif os.path.isdir(arguman):
            GORSEL_DIZIN = arguman
    kaydet(uret(), KLASOR, hedef)


if __name__ == "__main__":
    calistir()
