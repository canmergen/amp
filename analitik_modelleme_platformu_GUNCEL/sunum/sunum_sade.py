# -*- coding: utf-8 -*-
"""sunum_sade.py — Platformun KISA tanitim sunumunu (.pptx) ureten betik.

NE YAPAR
  Baska ekiplere anlatilan kisa sunumu bastan uretir: kapak, 6 icerik
  slayti ve kapanis. Ilk uc icerik slayti az yazili ozet, faz slaytlari
  semali kartlardir. Ne yapildigini ve ne kattigini anlatir, yontemin
  ayrintisina girmez. Ayrintili
  sunum icin ayni dizindeki sunum_yap.py kullanilir; iki betik birbirinden
  bagimsizdir. Butun kutular, oklar ve yazilar PowerPoint'in kendi
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
         import sunum_sade
         sunum_sade.kaydet(sunum_sade.uret(), "KLASOR_ADI")
  4. Bilgisayarda: python sunum_sade.py [cikti.pptx] [gorsel_dizini]
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
DOSYA = "Platform_Sunum_Sade.pptx"

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

    def sekil(self, hazir, x, y, w, h, dolgu=None, cizgi=None, ad=None, ayar=None, don=0):
        """PowerPoint'in hazir sekillerinden biri: funnel, gear6, star4, triangle,
        foldedCorner, upArrow ... dolgu: renk ya da None; cizgi: (renk,
        kalinlik, kesik_mi) ya da None; ayar: seklin ayar degeri ya da degerleri
        (AYAR_ADLARI'ndaki sirayla); don: derece."""
        cevir = (' rot="%d"' % int(round(don * 60000))) if don else ""
        if ayar is None:
            geo = _geo(hazir)
        else:
            degerler = tuple(ayar) if isinstance(ayar, (tuple, list)) else (ayar,)
            adlar = AYAR_ADLARI.get(hazir, ())
            if len(degerler) > len(adlar):
                raise ValueError("Sekil ayari taninmiyor: %s icin %d deger verildi, bilinen ayar adlari: %s"
                                 % (hazir, len(degerler), ", ".join(adlar) or "yok"))
            geo = '<a:prstGeom prst="%s"><a:avLst>%s</a:avLst></a:prstGeom>' % (
                hazir, "".join('<a:gd name="%s" fmla="val %d"/>' % (a, d) for a, d in zip(adlar, degerler)))
        self._x.append(_sp(self._id(), ad or hazir, geo, x, y, w, h,
                           _dolgu(dolgu) + _cizgi_xml(cizgi), cevir=cevir))

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

    # ---- bilesik ogeler ---------------------------------------------------
    def daire(self, metin, cx, cy, d, boy=12, ad=None):
        """Icinde beyaz kalin yazi olan kirmizi daire."""
        self.elips(cx, cy, d, KIR, None, "daire " + (ad or str(metin)))
        self.yazi(str(metin), cx - d / 2.0, cy - d / 2.0, d, d, boy=boy, kalin=True, renk=BEYAZ)

    def etiket(self, metin, x, y, w=5):
        self.yazi(metin, x, y, w, 0.26, boy=11, kalin=True, renk=GRI, hiza="l")

    def veri(self, x, y, w, h, baslik, alt=None):
        """Veri ya da cikti kutusu (kirmizi, beyaz yazi)."""
        self.kutu(x, y, w, h, "veri", baslik)
        p = [R(baslik, kalin=True, boy=12.5)]
        if alt:
            p.append(R(alt, boy=10.5))
        self.yazi(p, x + 0.06, y, w - 0.12, h, renk=BEYAZ)

    def sutun_basliklari(self, y, sutunlar, h=0.34, boy=12.5):
        """Sutun basliklari: her biri kendi sutununun ustunde ortali ve kalin;
        altinda sutun eninde kirmizi cizgi. sutunlar: [(x, w, ad), ...]."""
        for x, w, ad in sutunlar:
            self.yazi(ad, x, y, w, h - 0.04, boy=boy, kalin=True, renk=KIR)
            self.hat(x, y + h, x + w, y + h, "başlık çizgisi " + ad, KIR, 1.5)

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
# Kisa sunum BASKA EKIPLERE anlatilir: kapak, alti icerik slayti ve kapanis.
# Ilk uc icerik slayti (amac, roller, is akisi) az yazili ozettir; faz
# slaytlari (01, 02 ve 03 ile 05 arasi) semali kartlardir. NE yapildigini ve
# NE kattigini anlatir, NASIL yapildigini anlatmaz: yontemin ayrintisi
# (esikler, kontrol ve donusum listeleri, alt adimlar) bu sunumda yoktur, o
# ayrinti ayrintili sunumdadir (sunum_yap.py). Slayda sigmayan aciklama
# konusmaci notundadir. Dil olumludur: platformun var olan calismaya ekledigi
# anlatilir.
# YAZIM KURALI: her bilgi TEK slaytta gecer. Slaytlarda ve notlarda iki
# nokta, noktali virgul, orta nokta ve uzun cizgi kullanilmaz. Sekillerin
# hepsi PowerPoint'in kendi sekilleridir. Ornekler gosterim amaclidir.
# Durum: "g" gelistirildi, "s" uzerinde calisiliyor, "r" sirada
B1, B2, B3 = "Giriş", "Fazlar", "Kapanış"
SOL, EN = 0.5, 12.33                        # icerik alaninin sol kenari ve eni (inc)
ORTA_PEMBE, ORTA_GRI = "F08C8F", "C4C4C4"   # sema renkleri (kirmizi ile acik pembe arasi, orta gri)
DURUM_ADI = {"g": "Geliştirildi", "s": "Üzerinde çalışılıyor", "r": "Sırada"}
DURUM_KUTU = {"g": "veri", "s": "onay", "r": "soluk"}      # durumun kutu turu (_TURLER anahtari)


# Hazir sekillerin ayar adlari. PowerPoint her seklin ayarini kendi adiyla bekler;
# yanlis adla yazilan ayar dosyanin "onarilmasi gerekiyor" uyarisiyla acilmasina yol acar.
AYAR_ADLARI = {
    "roundRect": ("adj",), "star4": ("adj",), "foldedCorner": ("adj",), "triangle": ("adj",),
    "rightArrow": ("adj1", "adj2"), "downArrow": ("adj1", "adj2"), "upArrow": ("adj1", "adj2"),
    "gear6": ("adj1", "adj2"),
}


# ---- kucuk ikonlar ve sema parcalari -------------------------------------
def ikon_tablo(s, x, y, w, h, renk=KIR, kesik=False, vurgulu_sutun=None):
    """Tablo ikonu: ustte baslik seridi, altinda izgara. vurgulu_sutun: 0, 1 ya da 2."""
    bh = h * 0.26
    s.sekil("rect", x, y, w, h, BEYAZ, (renk, 1.25, kesik), "tablo")
    if vurgulu_sutun is not None:
        s.sekil("rect", x + w * vurgulu_sutun / 3.0, y + bh, w / 3.0, h - bh, ORTA_PEMBE, None, "yeni sütun")
    if not kesik:
        s.sekil("rect", x, y, w, bh, renk, None, "tablo başlığı")
    else:
        s.hat(x, y + bh, x + w, y + bh, "tablo çizgisi", renk, 0.75, True)
    for i in (1, 2):
        yy = y + bh + (h - bh) * i / 3.0
        s.hat(x, yy, x + w, yy, "tablo çizgisi", renk, 0.75, kesik)
        xx = x + w * i / 3.0
        s.hat(xx, y + bh, xx, y + h, "tablo çizgisi", renk, 0.75, kesik)


def ikon_cubuklar(s, x, y, w, h, degerler, renk=KIR, taban=True):
    """Kucuk cubuk semasi. degerler: 0 ile 1 arasi yukseklikler."""
    n = len(degerler)
    bw = w / (n * 1.5 - 0.5)
    for i, d in enumerate(degerler):
        s.sekil("rect", x + i * bw * 1.5, y + h * (1 - d), bw, h * d, renk, None, "çubuk")
    if taban:
        s.hat(x - 0.05, y + h, x + w + 0.05, y + h, "taban çizgisi", SOLUK, 1)


def ikon_isilti(s, cx, cy, b, renk=KIR):
    """Yapay zeka icin isilti: biri buyuk biri kucuk dort koseli yildiz."""
    s.sekil("star4", cx - b * 0.42, cy - b * 0.45, b * 0.66, b * 0.66, renk, None, "ışıltı", ayar=18000)
    s.sekil("star4", cx + b * 0.1, cy + b * 0.05, b * 0.36, b * 0.36, renk, None, "küçük ışıltı", ayar=18000)


def ikon_onay(s, cx, cy, b, renk=KIR, kalinlik=4.5):
    """Onay isareti: iki cizgi."""
    s.hat(cx - b * 0.3, cy + b * 0.02, cx - b * 0.08, cy + b * 0.24, "onay", renk, kalinlik)
    s.hat(cx - b * 0.08, cy + b * 0.24, cx + b * 0.32, cy - b * 0.22, "onay", renk, kalinlik)


def ikon_disli(s, cx, cy, b, renk=KIR, gobek=BEYAZ):
    s.sekil("gear6", cx - b / 2.0, cy - b / 2.0, b, b, renk, None, "dişli")
    s.elips(cx, cy, b * 0.3, gobek, None, "dişli göbeği")


def ikon_kilit(s, cx, cy, b, renk=KIR):
    s.elips(cx, cy - b * 0.2, b * 0.5, None, (renk, 2.5, False), "kilit halkası")
    s.sekil("roundRect", cx - b * 0.36, cy - b * 0.12, b * 0.72, b * 0.54, renk, None, "kilit gövdesi", ayar=15000)


def ikon_belge(s, x, y, w, h, renk=KIR):
    """Belge (sozluk) ikonu: kosesi kivrik kagit ve uc satir."""
    s.sekil("foldedCorner", x, y, w, h, BEYAZ, (renk, 1.25, False), "belge", ayar=22000)
    for i in range(3):
        yy = y + h * (0.3 + i * 0.2)
        s.hat(x + w * 0.2, yy, x + w * 0.8, yy, "belge satırı", renk, 1)


def ikon_uyari(s, cx, cy, b, renk=KIR):
    s.sekil("triangle", cx - b / 2.0, cy - b * 0.48, b, b * 0.9, renk, None, "uyarı")
    s.yazi("!", cx - b / 2.0, cy - b * 0.25, b, b * 0.65, boy=b * 34, kalin=True, renk=BEYAZ)


def etiketli_cip(s, x, y, w, h, metin, tur="cerceve", boy=13, renk=KOYU, kod=False):
    """Kucuk kutu icinde tek sozcuk. kod=True ise sabit aralikli yazi."""
    s.kutu(x, y, w, h, tur, "çip " + metin)
    s.yazi(metin, x, y, w, h, boy=boy, kalin=True, renk=renk, yazitipi="Courier New" if kod else None)


def islem_rozeti(s, cx, cy, metin, d=0.62, boy=11):
    """Iki parcanin arasindaki islem: kirmizi daire icinde bolu ya da eksi."""
    s.elips(cx, cy, d, KIR, None, "işlem " + metin)
    s.yazi(metin, cx - d / 2.0, cy - d / 2.0, d, d, boy=boy, kalin=True, renk=BEYAZ)


def durum_bicimi(durum):
    """Durumun gorunusu, doner: (dolgu, cizgi, yazi rengi).
    g gelistirildi (dolu kirmizi), s uzerinde calisiliyor (pembe, kirmizi cerceve), r sirada (kesik gri)."""
    if durum == "g":
        return KIR, None, BEYAZ
    if durum == "s":
        return PEMBE, (KIR, 2.5, False), KIR
    return BEYAZ, (SOLUK, 1.5, True), GRI


def hap(s, x, y, w, h, metin, dolgu, cizgi, renk, boy=11, kalin=True):
    """Uclari tam yuvarlak etiket."""
    s.sekil("roundRect", x, y, w, h, dolgu, cizgi, "etiket " + metin, ayar=50000)
    s.yazi(metin, x, y, w, h, boy=boy, kalin=kalin, renk=renk)


def yz_etiketi(s, x, y):
    """Kartin altindaki kucuk etiket: bu adimda yapay zeka oneride bulunur."""
    s.elips(x + 0.18, y + 0.18, 0.36, BEYAZ, None, "yapay zekâ zemini")
    ikon_isilti(s, x + 0.18, y + 0.18, 0.27)
    s.yazi("Yapay zekâ destekli", x + 0.46, y, 2.0, 0.36, boy=11, kalin=True, renk=KIR, hiza="l")


# ---- kapak ve kapanis ------------------------------------------------------
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
    s = Slayt("KAPAK", B1, "Analitik, Tahminleme ve İçgörü Platformu", "Bireysel Krediler Analitik ve Tahsis Bölümü")
    _kapak_gorseli(s)
    s.notlar = "Kapak. Ayrıntılı sunumdaki karşılığı slayt 1."
    return s


def slayt_kapanis():
    s = Slayt("KAPANIS", B3, "Teşekkürler")
    en, boy = SLAYT_CX / float(EMU), SLAYT_CY / float(EMU)
    bos = boy                                         # basligin ortalanacagi yukseklik: gorselin ustunde kalan alan
    g = _gorsel("kapanis")
    if g is not None:
        w, h = en, en / g.oran
        if h > 3.2:
            w, h = 3.2 * g.oran, 3.2
        s._resim("kapanis", (en - w) / 2.0, boy - h, w, h)      # alt kenara yapisik
        bos = boy - h
    s.baslik_kutu = (0.5, 0.0, en - 1.0, bos)
    s.notlar = "Kapanış. Ayrıntılı sunumdaki karşılığı slayt 15. Soruları ve önerileri bu slaytta alabilirsiniz."
    return s


# ---- 1. Amac ve katki ------------------------------------------------------
def slayt_amac():
    """Amac cumlesi ve platformun her calismaya kattiklari, her biri tek satir.
    Dil olumludur: yalniz platformun ekledigi yazar."""
    s = Slayt("AKIS", B1, "Amaç ve Katkı",
              "Platform, mevcut modelleme çalışmalarına ek katkı sağlamak için geliştirilen bir web uygulamasıdır.")
    s.dik(SOL, 1.74, 0.06, 0.84, KIR, "amaç çizgisi")
    s.yazi("Platformun en büyük amacı, hazır tablolardan üretilebilecek en iyi değişken kombinasyonlarını bulmak ve "
           "baz tabloyu kaynak tablolardan kurabilmektir.", SOL + 0.25, 1.74, EN - 0.25, 0.84, boy=15, kalin=True,
           renk=KIR, hiza="l")
    ust = 3.02                                        # tablo basliklarinin y konumu (inc)
    kx, kw = SOL, 2.6
    px = kx + kw + 0.15
    pw = SOL + EN - px
    s.sutun_basliklari(ust, [(kx, kw, "Konu"), (px, pw, "Platformun Kattığı")])
    satirlar = [
        ("Yöntem Birliği", "Her çalışmada aynı adımlar, aynı kontroller ve aynı ölçütler uygulanır."),
        ("Yeniden Kullanım", "Onaylanan tanımlar, adlar ve kararlar sonraki çalışmada hazır gelir."),
        ("Süre", "Hazırlık adımlarının büyük bölümü otomatik yürür, zaman incelemeye ve karara kalır."),
        ("İzlenebilirlik", "Her adımın kararı, gerekçesi ve üretim kodu tek yerde durur."),
    ]
    h, ara = 0.68, 0.1
    for i, (konu, metin) in enumerate(satirlar):
        y = ust + 0.46 + i * (h + ara)
        s.veri(kx, y, kw, h, konu)
        s.kutu(px, y, pw, h, "islem", "katkı " + konu)
        s.yazi(metin, px + 0.25, y, pw - 0.5, h, boy=13.5, hiza="l")
    s.notlar = ("Ayrıntılı sunumdaki karşılığı slayt 2. Platform, mevcut modelleme çalışmalarına ek katkı sağlamak "
                "için geliştirilen bir web uygulamasıdır. En büyük amacı hazır tablolardan üretilebilecek en iyi "
                "değişken kombinasyonlarını bulmak ve baz tabloyu kaynak tablolardan kurabilmektir. Böylece farklı "
                "tablolar da birleştirilir, modele katkı sağlayan yeni değişkenler elde edilir ve model performansı "
                "yükselir. Tabloda platformun her çalışmaya kattıkları yer alıyor.")
    return s


# ---- 2. Calisma prensibi ve roller -----------------------------------------
def slayt_prensip():
    """Uc rol sirayla, her birinde ne yaptigi ve bir ornek. Altta karardan
    sonra ne oldugu ve altyapi."""
    s = Slayt("AKIS", B1, "Çalışma Prensibi ve Roller", "Platformda üç rol vardır ve sıra her adımda aynıdır.")
    roller = [
        ("islem", "Kod ölçer", "Sayımı ve ölçümü yapar. Sayıya dayanan öneriyi de kendisi verir.",
         "Örneğin eksik oranını ve bilgi değerini (IV) hesaplar."),
        ("gri", "Yapay zekâ önerir", "Kolonların anlamını yorumlar ve öneri verir. Veriyi değiştirmez, karar vermez.",
         "Örneğin geleceğe bakan bir kolonu sızıntı riski diye işaretler."),
        ("onay", "Kullanıcı karar verir",
         "Öneriyi kabul eder, değiştirir ya da çıkarır. Onaylamadığı hiçbir şey veriye uygulanmaz.",
         "Örneğin neredeyse sabit bir kolonu tutmaya ya da çıkarmaya karar verir."),
    ]
    rw, rh, ry = 3.75, 2.4, 1.66
    for i, (tur, ad, metin, ornek) in enumerate(roller):
        x = SOL + i * (rw + 0.54)
        s.kutu(x, ry, rw, rh, tur, "rol " + ad)
        s.daire(i + 1, x + 0.48, ry + 0.42, 0.46, boy=15, ad="rol no %d" % (i + 1))
        s.yazi(ad, x + 0.86, ry + 0.19, 2.75, 0.46, boy=16, kalin=True, renk=KIR, hiza="l")
        s.yazi(metin, x + 0.25, ry + 0.84, rw - 0.5, 0.8, boy=12.5, hiza="l", dikey="t")
        s.hat(x + 0.25, ry + 1.72, x + rw - 0.25, ry + 1.72, "örnek çizgisi", SOLUK, 0.75)
        s.yazi(ornek, x + 0.25, ry + 1.78, rw - 0.5, 0.5, boy=11, egik=True, renk=GRI, hiza="l")
        if i < 2:
            s.ok(x + rw + 0.06, ry + rh / 2, x + rw + 0.48, ry + rh / 2, "ok rol %d" % i)
    sy = ry + rh + 0.24                               # karardan sonra seridinin ustu
    s.kutu(SOL, sy, EN, 0.5, "gri", "karardan sonra")
    s.yazi([[R("Karardan sonra", kalin=True, renk=KIR),
             " kod kararı güncel veriye uygular. İstenen adıma geri dönülebilir."]],
           SOL + 0.2, sy, EN - 0.4, 0.5, boy=12)
    s.etiket("Altyapı", SOL, sy + 0.76)
    altyapi = [
        ("Dataiku İçinde", "Tarayıcıdan, Dataiku projesinin içinden açılır."),
        ("Tam Veri", "Sayımlar verinin tamamında yapılır."),
        ("Kaynak Verinin Korunması", "Seçilen veri setine ve sözlüğe yazılmaz."),
    ]
    nw = (EN - 0.5) / 3
    for i, (ad, aciklama) in enumerate(altyapi):
        x = SOL + i * (nw + 0.25)
        s.kutu(x, sy + 1.06, nw, 0.9, "gri", "altyapı " + ad)
        s.yazi([R(ad, kalin=True, boy=12.5, renk=KIR), R(aciklama, boy=11.5)], x + 0.15, sy + 1.06, nw - 0.3, 0.9,
               bosluk=2)
    s.notlar = ("Ayrıntılı sunumdaki karşılığı slayt 3. Sıra her adımda aynıdır. Önce kod veriyi sayar ve ölçer, "
                "sonuçlar karar kartında görünür. Yapay zekâ kolon adlarının ve açıklamalarının anlamını yorumlar, "
                "anlam gerektiren yerde öneri verir. Kullanıcı ölçümü, öneriyi ve gerekçeyi aynı kartta görür ve "
                "kararı verir. Karardan sonra kod kararı veriye uygular. Platform Dataiku içinde çalışır ve yetkili "
                "olunan veri setlerini listeler. Büyük tablolar Spark ile kümede işlenir. Platform seçilen veri "
                "setine yazmaz, kendi kopyalarıyla çalışır.")
    return s


# ---- 3. Is akisi ve bugunku durum ------------------------------------------
def slayt_akis():
    """Bes faz tek bakista: kapsami, ciktisi ve durumu. Adimlar faz
    slaytlarindadir, burada yinelenmez. Altta platformun hangi model tipine
    acik oldugu."""
    s = Slayt("AKIS", B1, "İş Akışı ve Bugünkü Durum", "Beş faz vardır ve her faz bir öncekinin çıktısını kullanır.")
    fazlar = [
        ("01", "Çalışma Kurulumu", "Veri seti, sözlük, kolon rolleri ve örneklem tasarımı", "g",
         "Güncel Veri ve Sözlük", "Geliştirildi"),
        ("02", "Değişken Mühendisliği", "Profil, kural tabanlı ve AI destekli üretim", "s",
         "Yeni Değişkenler", "02.2 üzerinde çalışılıyor"),
        ("03", "Veri Anlama ve Hazırlama", "Tek değişken analizi, stabilite ve analitik baz set", "r",
         "Analitik Baz Set", "Sırada"),
        ("04", "Değişken Değerlendirme", "Sızıntı kontrolü ve aday değişken seti", "r",
         "Aday Değişken Seti", "Sırada"),
        ("05", "Modelleme ve Finalizasyon", "Model seçimi, katkı ölçümü ve doğrulama", "r",
         "Final Model ve Katalog", "Sırada"),
    ]
    ara = 0.2
    w = (EN - 4 * ara) / 5
    for i, (no, ad, ozet, durum, cikti, durum_yazi) in enumerate(fazlar):
        x = SOL + i * (w + ara)
        ana = durum_bicimi(durum)[2]
        ok_rengi = KIR if durum != "r" else SOLUK
        s.kutu(x, 1.7, w, 1.0, DURUM_KUTU[durum], "faz " + no)
        s.yazi([R(no, kalin=True, boy=18, renk=ana), R(ad, kalin=True, boy=12.5, renk=ana)], x + 0.08, 1.7, w - 0.16,
               1.0, bosluk=1)
        if i < 4:
            s.ok(x + w + 0.02, 2.2, x + w + ara - 0.02, 2.2, "ok faz %d" % i, ok_rengi)
        s.yazi(ozet, x + 0.05, 2.84, w - 0.1, 0.6, boy=11.5, egik=True, renk=GRI)
        s.ok(x + w / 2, 3.52, x + w / 2, 3.76, "ok çıktı " + no, ok_rengi)
        s.kutu(x, 3.8, w, 0.56, DURUM_KUTU[durum], "çıktı " + no)
        s.yazi(cikti, x + 0.05, 3.8, w - 0.1, 0.56, boy=12, kalin=True, renk=ana)
        s.yazi(durum_yazi, x, 4.46, w, 0.3, boy=11.5, kalin=(durum == "s"), renk=KIR if durum == "s" else GRI)
    my = 5.62                                         # model tipleri seridinin ustu
    s.etiket("Model Tipleri", SOL, my - 0.3)
    s.kutu(SOL, my, EN, 0.72, "gri", "model tipleri")
    s.yazi("Açık", SOL + 0.3, my, 0.7, 0.72, boy=12.5, kalin=True, renk=KIR, hiza="l")
    hap(s, SOL + 1.0, my + 0.16, 2.2, 0.4, "Sınıflandırma", KIR, None, BEYAZ, boy=12.5)
    s.yazi("Sonraki hedef", SOL + 3.75, my, 1.5, 0.72, boy=12.5, kalin=True, renk=GRI, hiza="l")
    for i, ad in enumerate(["Regresyon", "Segmentasyon", "Zaman Serisi Tahmini"]):
        hap(s, SOL + 5.25 + i * 2.32, my + 0.16, 2.16, 0.4, ad, BEYAZ, (SOLUK, 1.5, True), GRI, boy=12.5)
    s.notlar = ("Ayrıntılı sunumdaki karşılığı slayt 4 ve slayt 14. Sıra web uygulamasındaki İş Akışı ile aynıdır. "
                "01 Çalışma Kurulumu ile 02.1 Veri Profili ve Kalite geliştirildi. Şu an 02.2 Kural Tabanlı Değişken "
                "Üretimi üzerinde çalışılıyor. Profil üretimden önce gelir ki boş, sabit ve kimlik benzeri kolonlardan "
                "değişken üretilmesin. Tek değişken analizi ve stabilite üretimden sonra gelir, böylece ham ve "
                "üretilen değişkenlerin hepsi aynı ölçümden geçer. Platform şu an sınıflandırma modelleri için "
                "açıktır, sınıflandırmada hedef 0 ve 1 değeri alan bir kolondur. Sonraki hedef regresyon, "
                "segmentasyon ve zaman serisi tahmini modelleridir.")
    return s


# ---- 4. 01 Calisma Kurulumu ------------------------------------------------
def slayt_kurulum():
    """01 fazinin dort adimi yan yana: her kartta bir sema ve ne yapildigi.
    Etiket, yapay zekanin oneride bulundugu adimlari gosterir; neyi nasil
    onerdigi bu sunumda anlatilmaz."""
    s = Slayt("AKIS", B2, "01 Çalışma Kurulumu",
              "Değişken üretimi kolonun anlamına dayanır. Bu faz veriyi ve her kolonun anlamını netleştirir.")
    kartlar = [
        ("Veri ve Sözlük",
         "Hazır baz tablo seçilir ya da baz tablo kaynak tablolardan kurulur. Sözlük varsa birlikte seçilir.", True),
        ("Kolon Rolleri ve Tanımlar",
         "Neyin tahmin edileceği belirlenir. Tanımı olmayan kolonların tanımı tamamlanır.", True),
        ("Sözlük ve Kolon Adı Kontrolü",
         "Kısaltmalar çözülür, açıklama netleşir ve ad ortak bir yazılışa getirilir.", True),
        ("Tip Kontrolü ve Bölme",
         "Kolon tipleri düzeltilir. Veri, modelin öğreneceği ve hiç görmeden sınanacağı setlere ayrılır.", False),
    ]
    w = (EN - 0.6) / 4
    ky, kh = 1.6, 4.8
    for i, (ad, metin, yapay_zeka) in enumerate(kartlar):
        x = SOL + i * (w + 0.2)
        s.kutu(x, ky, w, kh, "gri", "kart " + ad)
        s.daire(i + 1, x + 0.45, ky + 0.47, 0.52, boy=16, ad="adım %d" % (i + 1))
        s.yazi(ad, x + 0.85, ky + 0.09, w - 0.98, 0.78, boy=15, kalin=True, hiza="l")
        gx, gy, gw, gh = x + 0.15, ky + 1.0, w - 0.3, 2.2              # sema alani
        s.kutu(gx, gy, gw, gh, "cerceve", "şema " + ad)
        orta = gx + gw / 2
        if i == 0:                                    # hazir tablo ya da kaynak tablolardan kurulan tablo
            s.yazi("Hazır tablo", gx + 0.22, gy + 0.2, 1.15, 0.7, boy=11.5, kalin=True, hiza="l")
            ikon_tablo(s, gx + 1.58, gy + 0.22, 0.9, 0.66, KIR)
            s.hat(gx + 0.22, gy + 1.1, orta - 0.32, gy + 1.1, "ayırıcı", SOLUK, 0.75, True)
            s.hat(orta + 0.32, gy + 1.1, gx + gw - 0.22, gy + 1.1, "ayırıcı", SOLUK, 0.75, True)
            s.yazi("ya da", orta - 0.3, gy + 0.97, 0.6, 0.26, boy=10, egik=True, renk=GRI)
            s.yazi("Kaynak tablolar", gx + 0.22, gy + 1.3, 1.05, 0.72, boy=11.5, kalin=True, hiza="l")
            for j in range(3):
                ikon_tablo(s, gx + 1.4, gy + 1.3 + j * 0.26, 0.3, 0.2, ORTA_GRI)
                s.ok(gx + 1.73, gy + 1.4 + j * 0.26, gx + 1.92, gy + 1.66, "ok birleşme", SOLUK)
            ikon_tablo(s, gx + 1.95, gy + 1.4, 0.53, 0.52, KIR, vurgulu_sutun=2)
        elif i == 1:                                  # dort rol: ikisi zorunlu, ikisi istege bagli
            roller = [("Hedef", KIR, BEYAZ), ("Kimlik", KIR, BEYAZ), ("Dönem", ORTA_PEMBE, KOYU),
                      ("Segment", ORTA_PEMBE, KOYU)]
            cw, ara = 0.58, 0.06
            x0 = gx + (gw - (4 * cw + 3 * ara)) / 2
            for j, (rol, dolgu, yazi_rengi) in enumerate(roller):
                cxx = x0 + j * (cw + ara)
                s.sekil("rect", cxx, gy + 0.25, cw, 0.4, dolgu, None, "rol " + rol)
                s.yazi(rol, cxx, gy + 0.25, cw, 0.4, boy=9.5, kalin=True, renk=yazi_rengi)
                for k in range(4):
                    s.sekil("rect", cxx, gy + 0.7 + k * 0.29, cw, 0.25, ACIK, None, "hücre")
            s.yazi("zorunlu", x0, gy + 1.87, 2 * cw + ara, 0.26, boy=10, renk=GRI)
            s.yazi("isteğe bağlı", x0 + 2 * (cw + ara), gy + 1.87, 2 * cw + ara, 0.26, boy=10, renk=GRI)
        elif i == 2:                                  # bir kolonun adi ve aciklamasi once ve sonra
            etiketli_cip(s, gx + 0.25, gy + 0.18, gw - 0.5, 0.4, "OUT_TRX_30D_AMT", "cerceve", boy=11.5, renk=KOYU,
                         kod=True)
            s.yazi("son 30 gün giden işlem tutar", gx + 0.05, gy + 0.62, gw - 0.1, 0.26, boy=10, egik=True, renk=GRI)
            s.ok(orta, gy + 0.96, orta, gy + 1.22, "ok ad")
            etiketli_cip(s, gx + 0.25, gy + 1.27, gw - 0.5, 0.4, "TXN_OUT_AMT_L30D", "onay", boy=11.5, renk=KIR,
                         kod=True)
            s.yazi("son 30 günde giden işlemlerin tutarı", gx + 0.05, gy + 1.71, gw - 0.1, 0.28, boy=10, egik=True,
                   renk=GRI)
        else:                                         # veri uc sete ayrilir
            bx, bw = gx + 0.15, gw - 0.3
            s.yazi("eski dönemler", bx, gy + 0.38, 1.2, 0.26, boy=10, renk=GRI, hiza="l")
            s.yazi("son dönemler", bx + bw - 1.2, gy + 0.38, 1.2, 0.26, boy=10, renk=GRI, hiza="r")
            setler = [("Train", 0.5, KIR, BEYAZ), ("Test", 0.17, ORTA_PEMBE, KOYU), ("Validasyon", 0.33, KIR2, BEYAZ)]
            sx = bx
            for j, (ad2, pay, dolgu, yazi_rengi) in enumerate(setler):
                sw = bw * pay - (0.04 if j < 2 else 0)
                s.sekil("rect", sx, gy + 0.72, sw, 0.7, dolgu, None, "set " + ad2)
                s.yazi(ad2, sx, gy + 0.72, sw, 0.7, boy=10, kalin=True, renk=yazi_rengi)
                sx += sw + 0.04
            s.yazi("model öğrenir", bx, gy + 1.5, bw * 0.5, 0.26, boy=10, renk=GRI)
            s.yazi("son ölçüm", bx + bw * 0.67, gy + 1.5, bw * 0.33, 0.26, boy=10, renk=GRI)
        s.yazi(metin, x + 0.2, ky + 3.38, w - 0.4, 1.0, boy=12.5, hiza="l", dikey="t")
        if yapay_zeka:
            yz_etiketi(s, x + 0.2, ky + 4.3)
    s.notlar = ("Ayrıntılı sunumdaki karşılığı slayt 5, 6, 7 ve 8. Bu fazda veri ve sözlük seçilir, kolon rolleri "
                "belirlenir, kolonların adı ve açıklaması netleştirilir, veri eğitim ve sınama setlerine ayrılır. Hedef "
                "ve kimlik zorunludur, dönem ve segment isteğe bağlıdır. İlk üç adımda yapay zekâ öneride bulunur. "
                "Örnekler gösterim amaçlıdır.")
    return s


# ---- 5. 02 Degisken Muhendisligi -------------------------------------------
def slayt_uretim():
    """02 fazinin uc adimi: once kalite, sonra bilinen donusumler, sonra yapay
    zekanin kendi onerileri. Ne uretildigi orneklerle gosterilir; donusum
    turleri, olcum yontemi ve denetim adimlari bu sunumda anlatilmaz."""
    s = Slayt("AKIS", B2, "02 Değişken Mühendisliği",
              "Platformun asıl işi bu fazdadır. Yeni değişkenler üç adımda üretilir.")
    yw, ara = 3.25, 0.3
    ow = EN - 2 * yw - 2 * ara
    xa, xb, xc = SOL, SOL + yw + ara, SOL + yw + ara + ow + ara
    by, bh = 2.55, 3.3                                # govdelerin ustu ve boyu
    basliklar = [(xa, yw, "02.1 Veri Profili ve Kalite", "g"), (xb, ow, "02.2 Kural Tabanlı Değişken Üretimi", "s"),
                 (xc, yw, "02.3 AI Değişken Keşfi", "r")]
    for x, w, ad, durum in basliklar:
        dolgu, cizgi, renk = durum_bicimi(durum)
        s.kutu(x, 1.6, w, 0.85, DURUM_KUTU[durum], "başlık " + ad)
        s.yazi([R(ad, kalin=True, boy=15.5), R(DURUM_ADI[durum], boy=11.5)], x + 0.1, 1.6, w - 0.2, 0.85, renk=renk,
               bosluk=1)
    for x in (xb - ara, xc - ara):
        s.sekil("rightArrow", x + 0.04, 1.89, ara - 0.08, 0.27, ORTA_GRI, None, "sonra")

    # 02.1: once kalite. Kusurlu kolonlar ayrilir
    s.kutu(xa, by, yw, bh, "gri", "gövde 02.1")
    s.sekil("funnel", xa + 0.35, by + 0.2, 0.8, 0.85, KIR, None, "kontroller")
    s.yazi([[R("26 ", kalin=True, boy=38, renk=KIR), R("kontrol", kalin=True, boy=16)]], xa + 1.3, by + 0.15,
           yw - 1.4, 0.95, hiza="l")
    kw, kara = 0.3, 0.12                              # kolon semasi: alti kolondan ikisi kusurlu
    kx0 = xa + (yw - (6 * kw + 5 * kara)) / 2
    for j in range(6):
        kx, kusurlu = kx0 + j * (kw + kara), j in (1, 4)
        if kusurlu:
            s.sekil("rect", kx, by + 1.32, kw, 0.72, BEYAZ, (SOLUK, 1, True), "kusurlu kolon")
            s.hat(kx + 0.06, by + 1.5, kx + kw - 0.06, by + 1.86, "çarpı", ORTA_PEMBE, 1.5)
            s.hat(kx + 0.06, by + 1.86, kx + kw - 0.06, by + 1.5, "çarpı", ORTA_PEMBE, 1.5)
        else:
            s.sekil("rect", kx, by + 1.32, kw, 0.72, PEMBE, None, "kolon")
            s.sekil("rect", kx, by + 1.32, kw, 0.16, KIR, None, "kolon başlığı")
    s.yazi([R("Önce verinin kusurları bulunur", kalin=True, boy=12.5),
            R("Örneğin çoğu boş olan ya da hep aynı değeri taşıyan kolon üretime girmez", boy=11, egik=True,
              renk=GRI)], xa + 0.3, by + 2.22, yw - 0.6, 0.95, hiza="l", dikey="t", bosluk=3)

    # 02.2: bilinen donusumler ve uretilen degiskenlerden ornekler
    s.kutu(xb, by, ow, bh, "islem", "gövde 02.2")
    ikon_disli(s, xb + 0.72, by + 0.56, 0.74)
    s.yazi([[R("33 ", kalin=True, boy=38, renk=KIR), R("dönüşüm", kalin=True, boy=16)]], xb + 1.3, by + 0.12, 2.6,
           0.88, hiza="l")
    s.yazi("Dönüşümler denenir, her kolon ölçülür, yeni bilgi katanlar önerilir.", xb + 0.3, by + 1.0,
           ow - 0.6, 0.42, boy=12.5, hiza="l")
    ornekler = [("Oran", "Son 30 gün bölü son 90 gün"), ("Eğilim", "Dönemden döneme artış ya da azalış"),
                ("Net akış", "Giren eksi çıkan")]
    tw = (ow - 0.6 - 0.3) / 3
    for j, (ad, aciklama) in enumerate(ornekler):
        tx, ty = xb + 0.3 + j * (tw + 0.15), by + 1.55
        s.kutu(tx, ty, tw, 1.55, "gri", "örnek " + ad)
        ocx, ocy = tx + tw / 2, ty + 0.42             # semanin ortasi
        if j == 0:                                    # kisa donem bolu uzun donem
            s.sekil("rect", ocx - 0.5, ocy - 0.02, 0.22, 0.26, KIR, None, "kısa dönem")
            islem_rozeti(s, ocx, ocy, "bölü", 0.38, 8)
            s.sekil("rect", ocx + 0.28, ocy - 0.26, 0.22, 0.5, ORTA_GRI, None, "uzun dönem")
        elif j == 1:                                  # donemden doneme artan degerler
            ikon_cubuklar(s, ocx - 0.32, ocy - 0.26, 0.64, 0.5, [0.3, 0.5, 0.75, 1.0], KIR, taban=False)
        else:                                         # giren eksi cikan
            s.sekil("upArrow", ocx - 0.52, ocy - 0.25, 0.3, 0.5, KIR, None, "giren")
            islem_rozeti(s, ocx, ocy, "eksi", 0.38, 8)
            s.sekil("downArrow", ocx + 0.22, ocy - 0.25, 0.3, 0.5, ORTA_GRI, None, "çıkan")
        s.yazi([R(ad, kalin=True, boy=13), R(aciklama, boy=10.5, egik=True, renk=GRI)], tx + 0.08, ty + 0.8,
               tw - 0.16, 0.7, dikey="t", bosluk=2)

    # 02.3: yapay zekanin kendi onerdigi degiskenler
    s.kutu(xc, by, yw, bh, "gri", "gövde 02.3")
    s.elips(xc + 0.75, by + 0.62, 0.85, PEMBE, None, "yapay zekâ zemini")
    ikon_isilti(s, xc + 0.75, by + 0.62, 0.64)
    s.yazi("Yeni fikirler", xc + 1.35, by + 0.15, yw - 1.45, 0.95, boy=19, kalin=True, hiza="l")
    cx0 = xc + (yw - 2.64) / 2                         # ornek bir oneri: iki kolon ve aralarindaki islem
    etiketli_cip(s, cx0, by + 1.42, 1.2, 0.42, "kullanılan limit", "islem", boy=10, renk=KIR)
    islem_rozeti(s, cx0 + 1.43, by + 1.63, "bölü", 0.38, 8)
    etiketli_cip(s, cx0 + 1.66, by + 1.42, 0.98, 0.42, "toplam limit", "islem", boy=10, renk=KIR)
    s.yazi("örnek bir öneri", xc + 0.3, by + 1.88, yw - 0.6, 0.24, boy=10, egik=True, renk=GRI)
    s.yazi([R("Bilinen dönüşümlerin dışında veriye özgü fikirler önerilir", kalin=True, boy=12.5)],
           xc + 0.3, by + 2.22, yw - 0.6, 0.95, hiza="l", dikey="t")

    s.kutu(SOL, 6.03, EN, 0.58, "onay", "öneri nasıl gelir")
    s.yazi("Her öneri, ölçülmüş katkısı ve gerekçesiyle birlikte sunulur", SOL + 0.2, 6.03, EN - 0.4, 0.58, boy=14,
           kalin=True, renk=KIR)
    s.notlar = ("Ayrıntılı sunumdaki karşılığı slayt 9, 10 ve 11. Yeni değişkenler üç adımda üretilir. Önce veri "
                "kalitesi kontrol edilir, bu adım geliştirildi. Sonra bilinen dönüşümler denenir, üretilen her kolon "
                "ayrı ölçülür ve modele yeni bilgi katanlar önerilir, şu an üzerinde çalışılan adım budur. Son adımda "
                "yapay zekâ bilinen dönüşümlerin dışında yeni değişken fikirleri önerir, bu adım sıradadır. Her öneri "
                "ölçülmüş katkısı ve gerekçesiyle "
                "birlikte sunulur, hangisinin üretileceğine kullanıcı karar verir. Örnekler gösterim amaçlıdır.")
    return s


# ---- 6. 03, 04 ve 05 fazlari -----------------------------------------------
def slayt_sonraki():
    """Sirada olan uc faz: her satir bir faz, sagda o fazin adimlari. Altta katkinin nerede olculdugu."""
    s = Slayt("AKIS", B2, "03, 04 ve 05 Fazlarında Ölçme, Eleme ve Modelleme",
              "Bu üç fazın ilk sürümleri kodda var. 02 tamamlandıktan sonra sırayla ele alınacak.")
    fazlar = [
        ("03", "Veri Anlama ve Hazırlama",
         [("03.1", "Tek Değişken Analizi (SFA)", "Her değişkenin hedefle ilişkisi ölçülür"),
          ("03.2", "Stabilite Analizi (PSI)", "Dağılımı zamanla kayan değişken bulunur"),
          ("03.3", "Analitik Baz Set", "Set temizlenir ve dondurulur")]),
        ("04", "Değişken Değerlendirme",
         [("04.1", "Sızıntı Kontrolü", "Hedefi ele veren değişkenler ayrılır"),
          ("04.2", "Aday Değişken Seti", "Aynı bilgiyi taşıyanlar ve katkısı düşük olanlar çıkarılır")]),
        ("05", "Modelleme ve Finalizasyon",
         [("05.1", "Model Karşılaştırması", "Baz model ile yeni değişkenlerin eklendiği model karşılaştırılır"),
          ("05.2", "Algoritma Seçimi", "Dört algoritma aynı koşulda karşılaştırılır"),
          ("05.3", "Model Finalizasyonu", "Model son hâliyle eğitilir, doğrulanır ve kaydedilir"),
          ("05.4", "Değişken Kataloğu", "Her değişken formülü ve koduyla saklanır")]),
    ]
    rw, tx0 = 2.4, SOL + 2.4 + 0.2                    # sol raydaki faz kutusunun eni, adim karolarinin sol kenari
    tw_toplam = SOL + EN - tx0
    th, bosluk, ic_bosluk = 1.0, 0.2, 0.12            # karo boyu, fazlar arasi ve faz ici bosluk
    y = 1.58
    sira = 0
    for i, (no, ad, adimlar) in enumerate(fazlar):
        satir_sayisi = 2 if len(adimlar) == 4 else 1  # dort adimli faz iki satira yayilir
        n = len(adimlar) // satir_sayisi
        fh = satir_sayisi * th + (satir_sayisi - 1) * ic_bosluk
        s.kutu(SOL, y, rw, fh, "soluk", "faz " + no)
        s.yazi(no, SOL + 0.1, y, 0.85, fh, boy=30, kalin=True, renk=SOLUK)
        s.yazi(ad, SOL + 0.95, y, rw - 1.05, fh, boy=12.5, kalin=True, hiza="l")
        if i < 2:
            s.sekil("downArrow", SOL + rw / 2 - 0.15, y + fh + 0.02, 0.3, bosluk - 0.04, ORTA_GRI, None, "sonra")
        tw = (tw_toplam - (n - 1) * 0.18) / n
        for j, (kod, adim, metin) in enumerate(adimlar):
            x = tx0 + (j % n) * (tw + 0.18)
            ty = y + (j // n) * (th + ic_bosluk)
            s.kutu(x, ty, tw, th, "gri", "adım " + kod)
            cx, cy = x + 0.5, ty + th / 2
            s.elips(cx, cy, 0.62, PEMBE, None, "ikon zemini " + kod)
            if sira == 0:
                ikon_cubuklar(s, cx - 0.16, cy - 0.15, 0.32, 0.29, [0.4, 0.7, 1.0], KIR, taban=False)
            elif sira == 1:                           # iki donemin dagilimi, biri kaymis
                ikon_cubuklar(s, cx - 0.2, cy - 0.14, 0.17, 0.28, [0.5, 1.0], ORTA_GRI, taban=False)
                ikon_cubuklar(s, cx + 0.03, cy - 0.14, 0.17, 0.28, [1.0, 0.45], KIR, taban=False)
            elif sira == 2:
                ikon_kilit(s, cx, cy + 0.02, 0.32)
            elif sira == 3:
                ikon_uyari(s, cx, cy, 0.32)
            elif sira == 4:
                s.sekil("funnel", cx - 0.17, cy - 0.17, 0.34, 0.34, KIR, None, "eleme")
            elif sira == 5:                           # baz model ile yeni degiskenli model
                s.sekil("rect", cx - 0.16, cy - 0.01, 0.13, 0.16, ORTA_GRI, None, "baz model")
                s.sekil("rect", cx + 0.03, cy - 0.15, 0.13, 0.3, KIR, None, "yeni model")
            elif sira == 6:
                ikon_cubuklar(s, cx - 0.18, cy - 0.14, 0.36, 0.28, [0.7, 1.0, 0.85, 0.6], KIR, taban=False)
            elif sira == 7:
                ikon_onay(s, cx, cy, 0.42, KIR, 2.5)
            else:
                ikon_belge(s, cx - 0.12, cy - 0.16, 0.24, 0.32)
            s.yazi([[R(kod + "  ", kalin=True, renk=KIR), R(adim, kalin=True)], R(metin, boy=11.5, renk=GRI)],
                   x + 0.98, ty + 0.05, tw - 1.1, th - 0.1, boy=12.5, hiza="l", bosluk=2)
            sira += 1
        y += fh + bosluk
    s.kutu(SOL, 6.26, EN, 0.54, "onay", "katkı ölçümü")
    s.yazi("Yeni değişkenlerin modele kattığı, 05.1 adımında ölçülerek gösterilir", SOL + 0.2, 6.26, EN - 0.4,
           0.54, boy=14, kalin=True, renk=KIR)
    s.notlar = ("Ayrıntılı sunumdaki karşılığı slayt 12 ve 13. Bu üç fazın ilk sürümleri kodda var ve sırayla "
                "ele alınacak. 03 fazında değişkenler ölçülür ve set dondurulur. 04 fazında riskli olan ve aynı bilgiyi "
                "taşıyan değişkenler elenir. 05 fazında model kurulur, yeni değişkenlerin modele kattığı ölçülerek "
                "gösterilir ve değişkenler kataloğa yazılır.")
    return s


# ===========================================================================
# URETIM VE KAYIT
# ===========================================================================
def uret(zaman=None):
    """Sunumun .pptx icerigini bayt olarak doner. Gorseller her cagrida yeniden okunur."""
    gorselleri_sifirla()
    slaytlar = [slayt_kapak(), slayt_amac(), slayt_prensip(), slayt_akis(), slayt_kurulum(),
                slayt_uretim(), slayt_sonraki()]
    if KAPANIS:
        slaytlar.append(slayt_kapanis())
    return paketle(slaytlar, "Analitik, Tahminleme ve İçgörü Platformu", zaman)


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
