# -*- coding: utf-8 -*-
"""sunum_sade.py — Platformun KISA tanitim sunumunu (.pptx) ureten betik.

NE YAPAR
  Az yazili, semali kisa sunumu bastan uretir: kapak, 14 icerik
  slayti ve kapanis. Her slaytta bir sema ya da sekil vardir. Ana fikir: yapay
  zeka ile degisken uretmek. Ayrintili
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

    def sekil(self, hazir, x, y, w, h, dolgu=None, cizgi=None, ad=None, ayar=None, don=0):
        """PowerPoint'in hazir sekillerinden biri: chevron, homePlate, can, funnel,
        gear6, star4, triangle, upArrow ... dolgu: renk ya da None; cizgi: (renk,
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
# Bu sunum ayrintili sunumla (sunum_yap.py) AYNI SIRADADIR ve basliklari
# aynidir: ayrintili sunumdan anlatilirken bu sunum gosterilir. Tek fark,
# amactan hemen sonra gelen "Yapay Zeka Degiskeni Nerede Uretir" slaytidir.
# Her slaytin notunda ayrintili sunumdaki karsiligi yazar.
# YAZIM KURALI: az yazi, buyuk punto, her slaytta bir sema. Slaytlarda ve
# notlarda iki nokta, noktali virgul, orta nokta ve uzun cizgi kullanilmaz.
# Sekillerin hepsi PowerPoint'in kendi sekilleridir.
B1, B2, B3, B4 = "Giriş", "01 Çalışma Kurulumu", "02 Değişken Mühendisliği", "Sırada ve durum"
SOL, EN = 0.5, 12.33                        # icerik alaninin sol kenari ve eni (inc)
ORTA_PEMBE, ORTA_GRI = "F08C8F", "C4C4C4"   # sema renkleri (kirmizi ile acik pembe arasi, orta gri)


# Hazir sekillerin ayar adlari. PowerPoint her seklin ayarini kendi adiyla bekler;
# yanlis adla yazilan ayar dosyanin "onarilmasi gerekiyor" uyarisiyla acilmasina yol acar.
AYAR_ADLARI = {
    "roundRect": ("adj",), "star4": ("adj",), "chevron": ("adj",), "homePlate": ("adj",),
    "foldedCorner": ("adj",), "can": ("adj",), "triangle": ("adj",),
    "rightArrow": ("adj1", "adj2"), "downArrow": ("adj1", "adj2"), "upArrow": ("adj1", "adj2"),
    "gear6": ("adj1", "adj2"), "wedgeRoundRectCallout": ("adj1", "adj2", "adj3"),
}


def K(metin, boy=12, renk=KIR):
    """Kolon adi gibi kod parcasi: sabit aralikli, kalin."""
    return R(metin, kalin=True, renk=renk, boy=boy, yazitipi="Courier New")


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


def ikon_cubuklar(s, x, y, w, h, degerler, renk=KIR):
    """Kucuk cubuk semasi. degerler: 0 ile 1 arasi yukseklikler."""
    n = len(degerler)
    bw = w / (n * 1.5 - 0.5)
    for i, d in enumerate(degerler):
        s.sekil("rect", x + i * bw * 1.5, y + h * (1 - d), bw, h * d, renk, None, "çubuk")
    s.hat(x - 0.06, y + h, x + w + 0.06, y + h, "taban çizgisi", SOLUK, 1)


def ikon_isilti(s, cx, cy, b, renk=KIR):
    """Yapay zeka icin isilti: biri buyuk biri kucuk dort koseli yildiz."""
    s.sekil("star4", cx - b * 0.42, cy - b * 0.45, b * 0.66, b * 0.66, renk, None, "ışıltı", ayar=18000)
    s.sekil("star4", cx + b * 0.1, cy + b * 0.05, b * 0.36, b * 0.36, renk, None, "küçük ışıltı", ayar=18000)


def ikon_onay(s, cx, cy, b, renk=KIR, kalinlik=4.5):
    """Onay isareti: iki cizgi."""
    s.hat(cx - b * 0.3, cy + b * 0.02, cx - b * 0.08, cy + b * 0.24, "onay", renk, kalinlik)
    s.hat(cx - b * 0.08, cy + b * 0.24, cx + b * 0.32, cy - b * 0.22, "onay", renk, kalinlik)


def ikon_disli(s, cx, cy, b, renk=KIR):
    s.sekil("gear6", cx - b / 2.0, cy - b / 2.0, b, b, renk, None, "dişli")
    s.elips(cx, cy, b * 0.3, BEYAZ, None, "dişli göbeği")


def ikon_saat(s, cx, cy, b, renk=KIR):
    s.elips(cx, cy, b, BEYAZ, (renk, 3, False), "saat")
    s.hat(cx, cy, cx, cy - b * 0.3, "akrep", renk, 3)
    s.hat(cx, cy, cx + b * 0.24, cy + b * 0.12, "yelkovan", renk, 3)


def ikon_kilit(s, cx, cy, b, renk=KIR):
    s.elips(cx, cy - b * 0.2, b * 0.5, None, (renk, 3, False), "kilit halkası")
    s.sekil("roundRect", cx - b * 0.36, cy - b * 0.12, b * 0.72, b * 0.54, renk, None, "kilit gövdesi", ayar=15000)


def ikon_belge(s, x, y, w, h, renk=KIR):
    """Belge (sozluk) ikonu: kosesi kivrik kagit ve uc satir."""
    s.sekil("foldedCorner", x, y, w, h, BEYAZ, (renk, 1.5, False), "belge", ayar=22000)
    for i in range(3):
        yy = y + h * (0.3 + i * 0.2)
        s.hat(x + w * 0.2, yy, x + w * 0.8, yy, "belge satırı", renk, 1.25)


def ikon_uyari(s, cx, cy, b, renk=KIR):
    s.sekil("triangle", cx - b / 2.0, cy - b * 0.48, b, b * 0.9, renk, None, "uyarı")
    s.yazi("!", cx - b / 2.0, cy - b * 0.25, b, b * 0.65, boy=b * 34, kalin=True, renk=BEYAZ)


def ikon_carpi(s, x, y, w, h, renk=GRI):
    """Uzerini cizmek icin capraz iki cizgi."""
    s.hat(x, y, x + w, y + h, "çarpı", renk, 2)
    s.hat(x, y + h, x + w, y, "çarpı", renk, 2)


def ikon_sorun(s, i, cx, cy, d):
    """Dort sorunun ikonu, d capli dairenin icinde. i: 0 ile 3."""
    o = d / 1.6
    s.elips(cx, cy, d, BEYAZ, (KIR, 1.5, False), "ikon zemini")
    if i == 0:                                        # herkes farkli yapiyor: uc ayri sekil
        s.elips(cx - 0.3 * o, cy - 0.22 * o, 0.42 * o, KIR, None, "daire")
        s.sekil("triangle", cx + 0.02 * o, cy - 0.44 * o, 0.48 * o, 0.44 * o, KIR2, None, "üçgen")
        s.sekil("rect", cx - 0.2 * o, cy + 0.12 * o, 0.42 * o, 0.42 * o, ORTA_PEMBE, None, "kare")
    elif i == 1:                                      # modelde kaliyor: kapali kutudaki veri
        s.sekil("roundRect", cx - 0.5 * o, cy - 0.52 * o, 1.0 * o, 1.04 * o, BEYAZ, (KIR, 1.5, True), "kapalı kutu",
                ayar=12000)
        s.sekil("can", cx - 0.27 * o, cy - 0.32 * o, 0.54 * o, 0.64 * o, KIR, None, "veri")
    elif i == 2:                                      # akla gelmeyen tablo
        ikon_tablo(s, cx - 0.48 * o, cy - 0.36 * o, 0.96 * o, 0.72 * o, KIR, kesik=True)
        s.yazi("?", cx - 0.3 * o, cy - 0.24 * o, 0.6 * o, 0.6 * o, boy=26 * o, kalin=True, renk=KIR)
    else:                                             # sure
        ikon_saat(s, cx, cy, 0.95 * o)


def etiketli_cip(s, x, y, w, h, metin, tur="cerceve", boy=13, renk=KOYU, kod=False):
    """Kucuk kutu icinde tek sozcuk. kod=True ise sabit aralikli yazi."""
    s.kutu(x, y, w, h, tur, "çip " + metin)
    s.yazi(metin, x, y, w, h, boy=boy, kalin=True, renk=renk, yazitipi="Courier New" if kod else None)


def islem_rozeti(s, cx, cy, metin, d=0.62):
    """Iki parcanin arasindaki islem: kirmizi daire icinde bolu ya da eksi."""
    s.elips(cx, cy, d, KIR, None, "işlem " + metin)
    s.yazi(metin, cx - d / 2.0, cy - d / 2.0, d, d, boy=11, kalin=True, renk=BEYAZ)


def surec_bandi(s, y, h, adimlar, vurgu=None, boy=17):
    """Yan yana ok bicimli adimlar. vurgu: pembe gosterilecek adimin sirasi."""
    n = len(adimlar)
    bindirme = h * 0.3
    w = (EN + (n - 1) * bindirme) / n
    for i, metin in enumerate(adimlar):
        x = SOL + i * (w - bindirme)
        pembe = (i == vurgu)
        s.sekil("homePlate" if i == 0 else "chevron", x, y, w, h, PEMBE if pembe else KIR,
                (KIR, 1.5, False) if pembe else None, "adım " + metin, ayar=30000)
        s.yazi(metin, x + (0.1 if i == 0 else bindirme + 0.05), y, w - bindirme - (0.2 if i == 0 else bindirme),
               h, boy=boy, kalin=True, renk=KIR if pembe else BEYAZ)
    return w, bindirme


def adim_etiketi(s, x, y, w, kod, ad):
    """Semanin ustundeki adim adi: kirmizi numara ve koyu ad."""
    s.yazi([[R(kod + "  ", kalin=True, renk=KIR), R(ad, kalin=True)]], x, y, w, 0.32, boy=13.5, hiza="l")


def durum_noktasi(s, cx, cy, durum, d=0.22, ad="durum"):
    """Durum noktasi: g gelistirildi (dolu), s uzerinde calisiliyor (halka), r sirada (bos)."""
    if durum == "g":
        s.elips(cx, cy, d, KIR, None, ad)
    elif durum == "s":
        s.elips(cx, cy, d * 1.18, PEMBE, (KIR, 2.5, False), ad)
    else:
        s.elips(cx, cy, d, BEYAZ, (SOLUK, 1.5, False), ad)


def karo(s, x, y, w, h, kod, ad, metin, yatay=False, ek=None):
    """Ikonlu karo (kesik cerceveli). Ikonu cagiran cizer.
    Doner: ikon dairesinin merkezi ve capi (cx, cy, d)."""
    s.sekil("roundRect", x, y, w, h, BEYAZ, (SOLUK, 1.5, True), "karo " + kod, ayar=5000)
    if yatay:
        cx, cy, d = x + 0.95, y + h / 2.0, 1.3
        s.elips(cx, cy, d, PEMBE, None, "ikon zemini")
        s.yazi([R(kod, kalin=True, renk=KIR, boy=13), R(ad, kalin=True, boy=15), R(metin, boy=12.5, renk=GRI)]
               + ([R(ek, boy=11, egik=True, renk=GRI)] if ek else []),
               x + 1.8, y + 0.1, w - 2.0, h - 0.2, hiza="l", bosluk=3)
    else:
        cx, cy, d = x + w / 2.0, y + 1.35, 1.75
        s.elips(cx, cy, d, PEMBE, None, "ikon zemini")
        s.yazi(kod, x + 0.1, y + 2.45, w - 0.2, 0.38, boy=15, kalin=True, renk=KIR)
        s.yazi(ad, x + 0.15, y + 2.83, w - 0.3, 0.8, boy=17, kalin=True)
        s.yazi([R(metin, boy=14)] + ([R(ek, boy=11.5, egik=True)] if ek else []), x + 0.2, y + 3.55, w - 0.4, 1.0,
               renk=GRI, dikey="t", bosluk=3)
    return cx, cy, d


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
    s = Slayt("KAPAK", B1, "Analitik, Tahminleme ve İçgörü Platformu", "Bireysel Krediler Analitik ve Tahsis BI")
    _kapak_gorseli(s)
    s.notlar = "Kapak. Ayrıntılı sunumdaki karşılığı slayt 1."
    return s


def slayt_kapanis():
    s = Slayt("KAPANIS", B4, "Teşekkürler")
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


# ---- giris -----------------------------------------------------------------
def slayt_ihtiyac():
    s = Slayt("AKIS", B1, "İhtiyaç ve Amaç")
    sorunlar = ["Değişken üretimi elle yapılıyor ve kişiye bağlı kalıyor",
                "Bir modelde üretilen değişken o modelde kalıyor",
                "Akla gelmeyen tablolar ve fikirler modele girmiyor", "Hazırlık uzun sürüyor, işler gecikiyor"]
    w = (EN - 0.6) / 4
    for i, metin in enumerate(sorunlar):
        x = SOL + i * (w + 0.2)
        s.kutu(x, 1.42, w, 1.55, "gri", "sorun %d" % (i + 1))
        ikon_sorun(s, i, x + 0.7, 2.195, 1.05)
        s.yazi(metin, x + 1.35, 1.42, w - 1.45, 1.55, boy=12.5, kalin=True, hiza="l")
    s.sekil("downArrow", SOL + EN / 2 - 0.35, 3.02, 0.7, 0.4, ORTA_GRI, None, "bu yüzden")
    s.kutu(SOL, 3.48, EN, 1.3, "veri", "amaç")
    s.yazi([R("Yapay zekâ ile modele katkı sağlayan yeni değişkenler üretmek", kalin=True, boy=25),
            R("Hazır tablolardan en iyi değişken kombinasyonlarını bulmak ve baz tabloyu kaynak tablolardan "
              "kurabilmek", boy=14)], SOL + 0.3, 3.48, EN - 0.6, 1.3, renk=BEYAZ, bosluk=4)
    cy = 5.5                                          # sema: tablolar, yapay zeka, yeni degiskenler, model
    ikon_tablo(s, 1.3, 5.02, 0.9, 0.62, ORTA_GRI)
    ikon_tablo(s, 1.56, 5.19, 0.9, 0.62, ORTA_PEMBE)
    ikon_tablo(s, 1.82, 5.36, 0.9, 0.62, KIR)
    s.elips(5.05, cy, 1.2, PEMBE, (KIR, 1.5, False), "yapay zekâ zemini")
    ikon_isilti(s, 5.05, cy, 0.92)
    for i, ad in enumerate(["oran", "büyüme", "net akış"]):
        etiketli_cip(s, 7.6, 4.95 + i * 0.38, 1.6, 0.32, ad, "islem", boy=12, renk=KIR)
    ikon_cubuklar(s, 10.8, 4.98, 1.3, 1.0, [0.35, 0.55, 0.75, 1.0])
    for x1, x2 in ((2.95, 4.3), (5.8, 7.45), (9.35, 10.55)):
        s.ok(x1, cy, x2, cy, "ok şema")
    for cx, ad in ((2.0, "Tablolar"), (5.05, "Yapay zekâ"), (8.4, "Yeni değişkenler"), (11.45, "Daha iyi model")):
        s.yazi(ad, cx - 1.4, 6.15, 2.8, 0.36, boy=14, kalin=True)
    s.yazi("Platform şu an sınıflandırma modelleri (0 ve 1 değerli hedef) için açıktır. Sonraki hedef regresyon, "
           "segmentasyon ve zaman serisi tahmini modelleridir.", SOL, 6.62, EN, 0.3, boy=11, renk=GRI)
    s.notlar = ("Ayrıntılı sunumdaki karşılığı slayt 2. Üstte dört sorun var. Değişken üretimi elle yapılıyor ve "
                "kişiye bağlı kalıyor. Bir modelde üretilen değişken o modelde kalıyor. Akla gelmeyen tablolar ve "
                "fikirler modele girmiyor. Hazırlık uzun sürüyor. Amaç yapay zekâ ile modele katkı sağlayan yeni "
                "değişkenler üretmektir. Platform şu an sınıflandırma modelleri için açıktır.")
    return s


def slayt_nerede():
    s = Slayt("AKIS", B1, "Yapay Zekâ Değişkeni Nerede Üretir")
    sutunlar = [
        ("Kaynak tablolardan", "01 Çalışma Kurulumu", "Tabloların nasıl birleşeceğini ve dönem toplamlarını önerir",
         "Örneğin işlem tablosundan son 30 günün işlem adedi", "g", "Geliştirildi"),
        ("Bilinen dönüşümlerle", "02.2 Kural Tabanlı Değişken Üretimi",
         "41 dönüşümün katkısı ölçülür, işe yarayanları önerir", "Örneğin son 30 günün son 90 güne oranı", "s",
         "Üzerinde çalışılıyor"),
        ("Yeni fikirlerle", "02.3 AI Değişken Keşfi", "Kalıpların dışında formül önerir, kod denetler ve hesaplar",
         "Örneğin kullanılan limit bölü toplam limit", "r", "Sırada"),
    ]
    w = (EN - 0.6) / 3
    for i, (baslik, adim, metin, ornek, durum, durum_adi) in enumerate(sutunlar):
        x = SOL + i * (w + 0.3)
        s.kutu(x, 1.45, w, 0.95, "veri", "başlık " + baslik)
        s.yazi([R(baslik, kalin=True, boy=19), R(adim, boy=11.5)], x + 0.1, 1.45, w - 0.2, 0.95, renk=BEYAZ, bosluk=2)
        s.kutu(x, 2.5, w, 3.95, "gri", "gövde " + baslik)
        px, pw = x + 0.2, w - 0.4
        s.kutu(px, 2.7, pw, 2.35, "cerceve", "şema " + baslik)
        if i == 0:                                    # uc kucuk tablo tek tabloda birlesir
            for j in range(3):
                ty = 3.1 + j * 0.56
                ikon_tablo(s, px + 0.25, ty, 0.72, 0.42, ORTA_GRI if j else KIR)
                s.ok(px + 1.02, ty + 0.21, px + 1.72, 3.88, "ok birleşme", SOLUK)
            ikon_tablo(s, px + 1.78, 3.3, 1.5, 1.16, KIR, vurgulu_sutun=2)
        elif i == 1:                                  # iki donem bolunur, yeni degisken cikar
            etiketli_cip(s, px + 0.3, 3.05, 1.1, 0.6, "L30D", "islem", boy=14, renk=KIR, kod=True)
            islem_rozeti(s, px + pw / 2, 3.35, "bölü")
            etiketli_cip(s, px + pw - 1.4, 3.05, 1.1, 0.6, "L90D", "islem", boy=14, renk=KIR, kod=True)
            s.ok(px + pw / 2, 3.72, px + pw / 2, 4.08, "ok sonuç")
            etiketli_cip(s, px + pw / 2 - 0.8, 4.12, 1.6, 0.6, "oran", "veri", boy=15, renk=BEYAZ)
        else:                                         # oneri, formul, denetim
            cyy = 3.75
            s.elips(px + 0.62, cyy, 0.86, PEMBE, None, "öneri zemini")
            ikon_isilti(s, px + 0.62, cyy, 0.66)
            s.ok(px + 1.1, cyy, px + 1.36, cyy, "ok formül")
            etiketli_cip(s, px + 1.4, cyy - 0.28, 1.05, 0.56, "formül", "islem", boy=13.5, renk=KIR)
            s.ok(px + 2.49, cyy, px + 2.75, cyy, "ok denetim")
            s.elips(px + 3.12, cyy, 0.7, BEYAZ, (KIR, 2, False), "denetim")
            ikon_onay(s, px + 3.12, cyy, 0.56, KIR, 3)
            s.yazi("yapay zekâ", px + 0.02, 4.3, 1.2, 0.3, boy=10.5, renk=GRI)
            s.yazi("kod denetler", px + 2.5, 4.3, 1.25, 0.3, boy=10.5, renk=GRI)
        s.yazi([R(metin, boy=15), R(ornek, boy=12.5, egik=True, renk=GRI)], x + 0.25, 5.15, w - 0.5, 1.25,
               hiza="l", dikey="t", bosluk=4)
        durum_noktasi(s, x + 0.37, 6.72, durum, ad="durum " + baslik)
        s.yazi(durum_adi, x + 0.6, 6.55, w - 0.8, 0.34, boy=12, renk=GRI, hiza="l")
    s.notlar = ("Bu slaydın ayrıntılı sunumda karşılığı yoktur, amaçtan hemen sonra gösterilir. Yapay zekâ üç yerde "
                "değişken üretimine katkı verir. Kaynak tablolarla başlanırsa birleştirme planını ve dönem toplamlarını "
                "önerir. 02.2 adımında bilinen 41 dönüşümden bu veride işe yarayanları önerir. 02.3 adımında kalıpların "
                "dışında formül önerir. 02.2 üzerinde çalışılıyor, 02.3 sırada. Şemalar gösterim amaçlıdır.")
    return s


def slayt_prensip():
    s = Slayt("AKIS", B1, "Çalışma Prensibi ve Roller",
              "Platform Dataiku içinde çalışan bir web uygulamasıdır. Her adımda sıra aynıdır.")
    adimlar = [
        ("Kod ölçer", "Verinin tamamında sayar ve ölçer", "Örneğin eksik oranı, tekil değer sayısı, bilgi değeri"),
        ("Yapay zekâ önerir", "Ölçüme ve kolonların anlamına bakar",
         "Örneğin bir kolonun geleceğe baktığını açıklamasından anlar"),
        ("Kullanıcı karar verir", "Öneriyi kabul eder ya da değiştirir",
         "Örneğin neredeyse sabit bir kolonu tutar ya da çıkarır"),
        ("Kod üretir", "Kararı uygular ve kodunu kaydeder", "Karar, gerekçe ve üretim kodu kayıtta kalır"),
    ]
    w, bindirme = surec_bandi(s, 1.55, 0.85, [a for a, _m, _o in adimlar], vurgu=2, boy=18)
    for i, (_ad, metin, ornek) in enumerate(adimlar):
        cx = SOL + i * (w - bindirme) + w / 2
        s.elips(cx, 3.15, 1.2, PEMBE, None, "ikon zemini")
        if i == 0:
            ikon_cubuklar(s, cx - 0.34, 2.83, 0.68, 0.62, [0.4, 0.7, 1.0, 0.6])
        elif i == 1:
            ikon_isilti(s, cx, 3.15, 0.9)
        elif i == 2:
            ikon_onay(s, cx, 3.15, 0.9)
        else:
            ikon_disli(s, cx, 3.15, 0.76)
        s.yazi([R(metin, kalin=True, boy=14), R(ornek, boy=12, egik=True, renk=GRI)], cx - 1.4, 3.85, 2.8, 1.1,
               dikey="t", bosluk=4)
    s.kutu(SOL, 5.0, EN, 0.85, "veri", "son karar")
    s.elips(SOL + 0.75, 5.425, 0.58, BEYAZ, None, "onay zemini")
    ikon_onay(s, SOL + 0.75, 5.425, 0.48, KIR, 3)
    s.yazi([R("Son karar her zaman kullanıcınındır", kalin=True, boy=20),
            R("Yapay zekâ sayı hesaplamaz ve karar vermez. Kullanıcının onaylamadığı hiçbir şey veriye uygulanmaz.",
              boy=12.5)], SOL + 1.2, 5.0, EN - 2.4, 0.85, renk=BEYAZ, bosluk=2)
    kurallar = [("Dataiku içinde", "Tarayıcıdan, projenin içinden açılır"),
                ("Tam veri", "Sayımlar örnekleme yapılmadan yapılır"),
                ("Kaynak veri korunur", "Seçilen veriye ve sözlüğe yazılmaz"),
                ("Proje hafızası", "Onaylanan kararlar sonraki çalışmada hazır gelir")]
    kw = (EN - 0.6) / 4
    for i, (ad, metin) in enumerate(kurallar):
        x = SOL + i * (kw + 0.2)
        s.kutu(x, 6.0, kw, 0.72, "gri", "kural " + ad)
        s.yazi([R(ad, kalin=True, boy=12, renk=KIR), R(metin, boy=10.5, renk=GRI)], x + 0.08, 6.0, kw - 0.16, 0.72,
               bosluk=1)
    s.notlar = ("Ayrıntılı sunumdaki karşılığı slayt 3. Platform Dataiku içinde çalışan bir web uygulamasıdır. Sıra her "
                "adımda aynıdır. Kod ölçer, yapay zekâ önerir, "
                "kullanıcı karar verir, kod kararı uygular. Yapay zekâ sayı hesaplamaz ve karar vermez. Kullanıcının "
                "onaylamadığı hiçbir şey veriye uygulanmaz. Seçilen veri setine ve sözlüğe yazılmaz, platform kendi "
                "kopyasıyla çalışır. Sohbet 02.2 adımında açılır.")
    return s


def slayt_akis():
    s = Slayt("AKIS", B1, "İş Akışının Beş Fazı ve Adımları")
    fazlar = [
        ("01", "Çalışma Kurulumu", "g", "Güncel Veri ve Sözlük",
         [("01.1", "Başlangıç Seçimi", "g"), ("01.2", "Veri Seti, Sözlük ve Kolon Rolleri", "g"),
          ("01.3", "Değişken Listesi ve Tip Kontrolü", "g"), ("01.4", "Örneklem ve Doğrulama Tasarımı", "g")]),
        ("02", "Değişken Mühendisliği", "s", "Yeni Değişkenler",
         [("02.1", "Veri Profili ve Kalite", "g"), ("02.2", "Kural Tabanlı Değişken Üretimi", "s"),
          ("02.3", "AI Değişken Keşfi", "r")]),
        ("03", "Veri Anlama ve Hazırlama", "r", "Analitik Baz Set",
         [("03.1", "Tek Değişken Analizi (SFA)", "r"), ("03.2", "Stabilite Analizi (PSI)", "r"),
          ("03.3", "Analitik Baz Set", "r")]),
        ("04", "Değişken Değerlendirme", "r", "Aday Değişken Seti",
         [("04.1", "Sızıntı Kontrolü", "r"), ("04.2", "Aday Değişken Seti", "r")]),
        ("05", "Modelleme ve Finalizasyon", "r", "Final Model ve Katalog",
         [("05.1", "Model Karşılaştırması", "r"), ("05.2", "Algoritma Seçimi", "r"),
          ("05.3", "Model Finalizasyonu", "r"), ("05.4", "Değişken Kataloğu", "r")]),
    ]
    y, h, bindirme = 1.5, 1.15, 0.3
    w = (EN + 4 * bindirme) / 5
    for i, (no, ad, durum, cikti, adimlar) in enumerate(fazlar):
        x = SOL + i * (w - bindirme)
        dolgu = KIR if durum == "g" else (PEMBE if durum == "s" else BEYAZ)
        cizgi = None if durum == "g" else ((KIR, 3, False) if durum == "s" else (SOLUK, 1.5, True))
        ana = BEYAZ if durum == "g" else (KIR if durum == "s" else GRI)
        s.sekil("homePlate" if i == 0 else "chevron", x, y, w, h, dolgu, cizgi, "faz " + no, ayar=26087)
        ic_x = x + (0.15 if i == 0 else bindirme + 0.1)
        ic_w = w - bindirme - (0.25 if i == 0 else bindirme + 0.1)
        s.yazi([R(no, kalin=True, boy=22, renk=ana), R(ad, kalin=True, boy=12, renk=ana)], ic_x, y, ic_w, h, bosluk=1)
        kx, kw = ic_x + 0.05, ic_w - 0.05                    # adimlar: nokta ve ad
        s.hat(kx + 0.11, 3.1, kx + 0.11, 3.1 + (len(adimlar) - 1) * 0.56, "adım çizgisi", SOLUK, 1)
        for j, (kod, adim, d) in enumerate(adimlar):
            ay = 3.1 + j * 0.56
            durum_noktasi(s, kx + 0.11, ay, d, ad="adım " + kod)
            s.yazi([[R(kod + " ", kalin=True, renk=KIR if d != "r" else GRI),
                     R(adim, renk=KOYU if d != "r" else GRI, kalin=(d == "s"))]],
                   kx + 0.32, ay - 0.26, kw - 0.32, 0.52, boy=11, hiza="l")
        s.sekil("downArrow", ic_x + ic_w / 2 - 0.16, 5.18, 0.32, 0.26, KIR if durum != "r" else ORTA_GRI, None,
                "çıktı oku")
        s.kutu(ic_x - 0.05, 5.5, ic_w + 0.05, 0.5, "veri" if durum != "r" else "soluk", "çıktı " + no)
        s.yazi(cikti, ic_x - 0.05, 5.5, ic_w + 0.05, 0.5, boy=12, kalin=True, renk=BEYAZ if durum != "r" else GRI)
    for i, (ad, d) in enumerate((("Geliştirildi", "g"), ("Üzerinde çalışılıyor", "s"), ("Sırada", "r"))):
        lx = 7.6 + i * 1.75                           # gosterim anahtari, basligin saginda
        durum_noktasi(s, lx, 0.62, d, ad="anahtar " + ad)
        s.yazi(ad, lx + 0.2, 0.45, 1.5, 0.34, boy=11, renk=GRI, hiza="l")
    s.kutu(SOL, 6.22, EN, 0.52, "gri", "neden bu sıra")
    s.yazi([[R("Neden bu sıra?", kalin=True, renk=KIR),
             " Profil üretimden önce gelir ki kusurlu kolondan değişken üretilmesin. Ölçüm üretimden sonra gelir, "
             "böylece ham ve üretilen değişkenlerin hepsi birlikte ölçülür."]],
           SOL + 0.2, 6.22, EN - 0.4, 0.52, boy=11.5, hiza="l")
    s.notlar = ("Ayrıntılı sunumdaki karşılığı slayt 4. Web uygulamasındaki İş Akışı ile aynı sıra. Beş faz vardır ve "
                "her faz bir öncekinin çıktısını kullanır. 01 ve 02.1 geliştirildi, 02.2 üzerinde çalışılıyor, gerisi "
                "sırada. Profil üretimden önce gelir ki kusurlu kolonlardan değişken üretilmesin. Tek değişken analizi "
                "ve stabilite üretimden sonra gelir, böylece ham ve üretilen değişkenlerin hepsi birlikte ölçülür.")
    return s


# ---- 01 Calisma Kurulumu ---------------------------------------------------
def slayt_kurulum_veri():
    s = Slayt("AKIS", B2, "01 Çalışma Kurulumunda Veri Seti ve Sözlük",
              "Çalışmanın hangi tabloyla ve hangi sözlükle yürüyeceği belirlenir. Platform kendi kopyalarıyla çalışır.")
    # Sol: baslangic secimi
    adim_etiketi(s, SOL, 1.55, 4.0, "01.1", "Başlangıç Seçimi")
    s.kutu(SOL, 1.95, 4.0, 2.05, "gri", "seçenek hazır tablo")
    ikon_tablo(s, SOL + 0.45, 2.55, 1.15, 0.85, KIR)
    s.yazi([R("Baz veri seti mevcut", kalin=True, boy=15), R("Hazır tablo seçilir", boy=12.5, renk=GRI),
            R("Örneğin tek bir modelleme tablosu varsa", boy=11, egik=True, renk=GRI)],
           SOL + 1.9, 1.95, 2.0, 2.05, hiza="l", bosluk=3)
    s.kutu(SOL, 4.2, 4.0, 2.05, "gri", "seçenek kaynak tablolar")
    for j in range(3):
        ikon_tablo(s, SOL + 0.25, 4.45 + j * 0.53, 0.6, 0.4, ORTA_GRI)
        s.ok(SOL + 0.9, 4.65 + j * 0.53, SOL + 1.2, 5.2, "ok birleşme", SOLUK)
    ikon_tablo(s, SOL + 1.25, 4.9, 0.75, 0.58, KIR)
    s.yazi([R("Kaynak tablolar mevcut", kalin=True, boy=14.5),
            R("Birleştirme planını yapay zekâ önerir, kullanıcı onaylar", boy=12, renk=GRI),
            R("Örneğin müşteri, işlem ve ürün tabloları ayrıysa", boy=11, egik=True, renk=GRI)],
           SOL + 2.2, 4.2, 1.75, 2.05, hiza="l", bosluk=3)
    s.sekil("rightArrow", 4.62, 3.85, 0.5, 0.5, ORTA_GRI, None, "sonra")
    s.yazi("Sözlük iki seçenekte de isteğe bağlıdır", SOL, 6.3, 4.0, 0.3, boy=11, renk=GRI)
    # Sag: baz kopya ve guncel kopya
    x0, pw = 5.25, 7.58
    adim_etiketi(s, x0, 1.55, pw, "01.2.1", "Baz Veri Seti ve Baz Sözlük")
    duraklar = [("Seçilen veri ve sözlük", "Üzerine hiç yazılmaz", ()),
                ("Baz kopya", "Bir kez yazılır, değişmez", ("V8_BAZ_VERI", "V8_BAZ_SOZLUK")),
                ("Güncel kopya", "Her adımda güncellenir", ("V8_UPDT_VERI", "V8_UPDT_SOZLUK"))]
    dw = (pw - 2 * 0.55) / 3
    for i, (ad, alt, ornek) in enumerate(duraklar):
        x = x0 + i * (dw + 0.55)
        s.kutu(x, 1.95, dw, 2.55, "onay" if i == 2 else "gri", "durak " + ad)
        cx = x + dw / 2
        if i == 0:
            ikon_tablo(s, cx - 0.75, 2.2, 0.85, 0.66, KIR)
            ikon_belge(s, cx + 0.2, 2.16, 0.55, 0.72)
            s.elips(cx + 0.78, 2.95, 0.5, BEYAZ, (KIR, 1.25, False), "kilit zemini")
            ikon_kilit(s, cx + 0.78, 2.97, 0.36)
        elif i == 1:
            ikon_tablo(s, cx - 0.5, 2.2, 1.0, 0.75, ORTA_GRI)
        else:
            ikon_tablo(s, cx - 0.5, 2.2, 1.0, 0.75, KIR, vurgulu_sutun=2)
        s.yazi([R(ad, kalin=True, boy=14.5), R(alt, boy=12, renk=GRI)] + [K(o, 10) for o in ornek],
               x + 0.1, 3.15, dw - 0.2, 1.3, bosluk=2)
        if i < 2:
            s.ok(x + dw + 0.06, 3.2, x + dw + 0.49, 3.2, "ok kopya %d" % i)
            s.yazi("kopya" if i == 0 else "adımlar", x + dw - 0.1, 2.82, 0.75, 0.3, boy=10.5, renk=GRI)
    adim_etiketi(s, x0, 4.72, pw, "01.2.1.1", "Sözlük Birleştirme")
    s.kutu(x0, 5.1, pw, 1.15, "gri", "sözlük birleştirme")
    ikon_belge(s, x0 + 0.3, 5.3, 0.5, 0.68, ORTA_GRI)
    ikon_belge(s, x0 + 0.95, 5.3, 0.5, 0.68, ORTA_GRI)
    s.ok(x0 + 1.55, 5.65, x0 + 1.95, 5.65, "ok birleşme")
    ikon_belge(s, x0 + 2.05, 5.3, 0.5, 0.68)
    s.yazi([["Birden çok sözlük tek sözlükte birleşir. Örneğin ", K("BAL_AMT", 11.5),
             " için bir sözlükte bakiye tutarı, öbüründe ay sonu bakiyesi yazıyorsa kalacak olanı kullanıcı seçer."]],
           x0 + 2.85, 5.1, pw - 3.05, 1.15, boy=12.5, hiza="l")
    s.notlar = ("Ayrıntılı sunumdaki karşılığı slayt 5. Başlangıçta iki seçenek açıktır. Ya baz veri seti hazırdır ya "
                "da kaynak tablolardan kurulur. Sözlük isteğe bağlıdır. Seçilen veri setine ve sözlüğe yazılmaz. Platform "
                "önce birebir kopyasını alır, buna baz kopya denir ve değişmez. Bütün değişiklikler güncel kopyaya "
                "yazılır. Birden çok sözlük seçilirse tek sözlükte birleştirilir, aynı kolonun farklı tanımı varsa "
                "kalacak olanı kullanıcı seçer.")
    return s


def slayt_kurulum_rol():
    s = Slayt("AKIS", B2, "01 Çalışma Kurulumunda Kolon Rolleri ve Sözlük Tanımları",
              "Neyin tahmin edileceği ve her kolonun ne anlama geldiği netleştirilir. Bilgi taşımayan kolonlar ayrılır.")
    # Sema: bir tablonun kolonlari. Dort rol, tanimsiz bir kolon, iki olagan kolon, iki sorunlu kolon
    kolonlar = [("Hedef", "rol", KIR, BEYAZ, "DEFAULT_FLAG"), ("Kimlik", "rol", KIR, BEYAZ, "CUSTOMER_ID"),
                ("Dönem", "rol", ORTA_PEMBE, KOYU, "SNAPSHOT_DATE"), ("Segment", "rol", ORTA_PEMBE, KOYU, "PRODUCT_TYPE"),
                ("?", "tanimsiz", BEYAZ, KIR, "TXN_7D_CNT"), ("kolon", "olagan", ORTA_GRI, KOYU, "TXN_3D_CNT"),
                ("kolon", "olagan", ORTA_GRI, KOYU, "BAL_AMT"), ("boş", "sorunlu", BEYAZ, GRI, ""),
                ("tek değer", "sorunlu", BEYAZ, GRI, "7")]
    kw, ara, ky, bh, gh = 1.2, 0.191, 1.75, 0.5, 1.75
    for i, (ad, tur, dolgu, yazi_rengi, ornek) in enumerate(kolonlar):
        x = SOL + i * (kw + ara)
        sorunlu = (tur == "sorunlu")
        cizgi = (KIR, 1.5, True) if tur == "tanimsiz" else ((SOLUK, 1.5, True) if sorunlu else None)
        s.sekil("rect", x, ky, kw, bh, dolgu, cizgi, "kolon başlığı " + ad)
        s.yazi(ad, x, ky, kw, bh, boy=13, kalin=True, renk=yazi_rengi)
        s.sekil("rect", x, ky + bh + 0.05, kw, gh, BEYAZ if sorunlu else ACIK,
                (SOLUK, 1, True) if tur != "rol" and tur != "olagan" else None, "kolon gövdesi " + ad)
        for j in range(1, 4):
            yy = ky + bh + 0.05 + gh * j / 4.0
            s.hat(x, yy, x + kw, yy, "hücre çizgisi", SOLUK if sorunlu else BEYAZ, 0.75 if sorunlu else 1.5, sorunlu)
        if ornek and not sorunlu:                      # ornek kolon adi, ilk hucrede
            s.yazi(ornek, x, ky + bh + 0.05, kw, gh / 4.0, boy=8.5, kalin=True, renk=KIR, yazitipi="Courier New")
        elif ornek:                                   # tek degerli kolon: her satirda ayni deger
            for j in range(4):
                s.yazi(ornek, x, ky + bh + 0.05 + gh * j / 4.0, kw, gh / 4.0, boy=11, renk=GRI)
        if sorunlu:
            ikon_carpi(s, x + 0.2, ky + bh + 0.3, kw - 0.4, gh - 0.5, ORTA_PEMBE)
        if tur == "tanimsiz":
            s.elips(x + kw - 0.1, ky + 0.02, 0.56, PEMBE, (KIR, 1.25, False), "öneri zemini")
            ikon_isilti(s, x + kw - 0.1, ky + 0.02, 0.44)
    s.yazi("zorunlu", SOL, ky + bh + gh + 0.1, 2 * kw + ara, 0.3, boy=11.5, renk=GRI)
    s.yazi("isteğe bağlı", SOL + 2 * (kw + ara), ky + bh + gh + 0.1, 2 * kw + ara, 0.3, boy=11.5, renk=GRI)
    kartlar = [
        (SOL, 4 * kw + 3 * ara, "01.2.2", "Kolon Rolleri",
         "Model tipi, hedef ve kimlik seçilir. Kod adayları çıkarır, kullanıcı seçer. Hedef yalnız 0 ve 1 değeri "
         "alan bir kolon olabilir."),
        (SOL + 4 * (kw + ara), 3 * kw + 2 * ara, "01.2.3", "Eksik Sözlük Tanımları",
         "Tanım önce hafızadan gelir, yoksa yapay zekâ önerir ve kullanıcı onaylar. TXN_3D_CNT tanımı TXN_7D_CNT "
         "kolonuna sayısı değiştirilerek aktarılır."),
        (SOL + 7 * (kw + ara), 2 * kw + ara, "01.2.3.1", "Tanımsız ve Sorunlu Kolonlar",
         "Boş ve tek değerli kolon çıkarılır. Tanımsız kalan için kararı kullanıcı verir."),
    ]
    for x, w, kod, ad, metin in kartlar:
        s.hat(x, 4.55, x + w, 4.55, "grup çizgisi " + kod, KIR, 2)
        s.kutu(x, 4.7, w, 1.7, "gri", "kart " + kod)
        s.yazi([R(kod, kalin=True, renk=KIR, boy=13), R(ad, kalin=True, boy=14), R(metin, boy=12, renk=GRI)],
               x + 0.15, 4.75, w - 0.3, 1.6, bosluk=3)
    s.notlar = ("Ayrıntılı sunumdaki karşılığı slayt 6. Şema bir tablonun kolonlarını gösterir. Hedef ve kimlik "
                "zorunludur, dönem ve segment isteğe bağlıdır. Segment veriyi ürün ya da kanal gibi alt gruplara ayırır. "
                "Sözlükte tanımı olmayan kolona önce hafızadan, yoksa yapay zekâdan tanım önerilir ve kullanıcı "
                "onaylar. Tamamen boş ve tek değerli kolonlar her zaman çıkarılır, tanımsız kalan kolonlar için kararı "
                "kullanıcı verir.")
    return s


def slayt_sozluk():
    s = Slayt("AKIS", B2, "01.2.4 Sözlük ve Kolon Adı Kontrolü",
              "Sözlüğe de kolon adlarına da tam güvenilemez. Bu adım her kolonun kesin olarak anlaşılmasını sağlar.")
    adimlar = [("Dönem Bilgisi", "30D parçası 30 gün demektir", "Yapay zekâ önerir, kullanıcı onaylar"),
               ("Ad Parçaları", "TRX ve TXN aynıdır, TXN yazılır", "Yapay zekâ önerir, kullanıcı onaylar"),
               ("Kolon Kartları", "Açıklama tek ve açık cümle olur", "Yapay zekâ yazar, kullanıcı onaylar"),
               ("Kolon Adları", "Parçalar standart sıraya dizilir", "Kod kurar, kullanıcı onaylar")]
    for i, (ad, alt, rol) in enumerate(adimlar):
        y = 1.8 + i * 1.18
        if i < 3:
            s.hat(SOL + 0.32, y + 0.67, SOL + 0.32, y + 1.31, "adım çizgisi", SOLUK, 1.5)
        s.daire(i + 1, SOL + 0.32, y + 0.4, 0.54, boy=17, ad="alt adım %d" % (i + 1))
        s.yazi([R(ad, kalin=True, boy=17), R(alt, boy=12.5, renk=GRI), R(rol, boy=11, egik=True, renk=GRI)],
               SOL + 0.8, y - 0.1, 3.6, 1.0, hiza="l", bosluk=2)
    # Sema: kolon adinin parcalari yeniden dizilir
    px, pw = 4.9, 7.93
    s.kutu(px, 1.6, pw, 4.85, "gri", "şema zemini")
    cw, ara = 1.5, 0.3
    x0 = px + (pw - (4 * cw + 3 * ara)) / 2
    ust_y, alt_y, ch = 2.2, 4.3, 0.62
    s.yazi([[R("Önce  ", kalin=True, renk=GRI), R("son 30 gün giden işlem tutar", egik=True)]], x0, 1.72, 6.9, 0.4,
           boy=14, hiza="l")
    onceki = ["OUT", "TRX", "30D", "AMT"]
    sonraki = [("TXN", "işlem"), ("OUT", "giden"), ("AMT", "tutar"), ("L30D", "son 30 gün")]
    for i, ad in enumerate(onceki):
        etiketli_cip(s, x0 + i * (cw + ara), ust_y, cw, ch, ad, "cerceve", boy=18, renk=KOYU, kod=True)
    for i, (ad, anlam) in enumerate(sonraki):
        x = x0 + i * (cw + ara)
        etiketli_cip(s, x, alt_y, cw, ch, ad, "onay", boy=18, renk=KIR, kod=True)
        s.yazi(anlam, x, alt_y + ch + 0.04, cw, 0.3, boy=11.5, renk=GRI)
    for ustteki, alttaki in ((0, 1), (1, 0), (2, 3), (3, 2)):      # hangi parca nereye gidiyor
        s.ok(x0 + ustteki * (cw + ara) + cw / 2, ust_y + ch + 0.04, x0 + alttaki * (cw + ara) + cw / 2, alt_y - 0.05,
             "ok parça %d" % ustteki)
    s.yazi([[R("Sonra  ", kalin=True, renk=KIR), R("son 30 günde giden işlemlerin tutarı", egik=True)]], x0, 5.6, 6.9,
           0.4, boy=14, hiza="l")
    s.yazi("Yeni adda L son, A sonra, B önce demektir. Bu adım isteğe bağlıdır ve her satırı kullanıcı onaylar.",
           x0, 6.02, 6.9, 0.34, boy=11.5, renk=GRI, hiza="l")
    s.notlar = ("Ayrıntılı sunumdaki karşılığı slayt 7. Dört alt adım sırayla çalışır ve her satırı kullanıcı onaylar. "
                "Şemada bir kolonun adı ve açıklaması baştan sona değişir. TRX yerine standart yazılış olan TXN yazılır, "
                "parçalar konu, yön, ölçü, zaman sırasına dizilir ve dönem son 30 gün anlamında L30D olur. Sözlük "
                "açıklaması da tek ve açık bir cümleye çevrilir. Bu adım isteğe bağlıdır. Örnek gösterim amaçlıdır.")
    return s


def slayt_kurulum_bolme():
    s = Slayt("AKIS", B2, "01 Çalışma Kurulumunda Tip Kontrolü ve Bölme",
              "Liste ve tipler son kez gözden geçirilir, ardından veri eğitim ve ölçüm setlerine ayrılır.")
    # Sol: tip donusumleri
    lw = 5.6
    adim_etiketi(s, SOL, 1.55, lw, "01.3", "Değişken Listesi ve Tip Kontrolü")
    s.kutu(SOL, 1.95, lw, 4.45, "gri", "tip kontrolü")
    donusumler = [("metin", "1.234,50", "sayı", "1234,5"), ("tam sayı", "20240131", "tarih", "31.01.2024"),
                  ("sayı", "104", "kategori", "şube 104")]
    for i, (tip1, deger1, tip2, deger2) in enumerate(donusumler):
        y = 2.3 + i * 1.12
        s.yazi(tip1, SOL + 0.25, y - 0.02, 1.9, 0.26, boy=11, renk=GRI)
        etiketli_cip(s, SOL + 0.25, y + 0.26, 1.9, 0.56, deger1, "cerceve", boy=14, renk=KOYU, kod=True)
        s.ok(SOL + 2.3, y + 0.54, SOL + 3.3, y + 0.54, "ok tip %d" % i)
        s.yazi(tip2, SOL + 3.45, y - 0.02, 1.9, 0.26, boy=11, kalin=True, renk=KIR)
        etiketli_cip(s, SOL + 3.45, y + 0.26, 1.9, 0.56, deger2, "onay", boy=14, renk=KIR, kod=True)
    s.yazi([R("Yanlış tipli kolonda ölçüm anlamını yitirir", kalin=True, boy=13.5),
            R("Kod dönüşümü kolonun tamamında dener, tek değer bile çevrilemezse kabul etmez", boy=11.5, renk=GRI)],
           SOL + 0.2, 5.5, lw - 0.4, 0.85, bosluk=3)
    # Sag: bolme
    x0 = SOL + lw + 0.33
    rw = EN - lw - 0.33
    adim_etiketi(s, x0, 1.55, rw, "01.4", "Örneklem ve Doğrulama Tasarımı")
    s.kutu(x0, 1.95, rw, 4.45, "gri", "bölme")
    bx, bw = x0 + 0.3, rw - 0.6
    s.sekil("rightArrow", bx, 2.25, bw, 0.34, ORTA_GRI, None, "zaman", ayar=(60000, 50000))
    s.yazi("eski dönemler", bx + 0.05, 2.25, 2.0, 0.34, boy=10.5, kalin=True, renk=KOYU, hiza="l")
    s.yazi("son dönemler", bx + bw - 2.35, 2.25, 2.0, 0.34, boy=10.5, kalin=True, renk=KOYU, hiza="r")
    setler = [("Train", "MS", "Model öğrenir", "", 0.5, KIR, BEYAZ),
              ("Test", "OOS", "Ayar seçilir", "isteğe bağlı", 0.17, ORTA_PEMBE, KOYU),
              ("Validasyon", "OOT", "Son ölçüm", "", 0.33, KIR2, BEYAZ)]
    sx = bx
    for i, (ad, kisa, alt, alt2, pay, dolgu, yazi_rengi) in enumerate(setler):
        w = bw * pay - (0.06 if i < 2 else 0)
        s.sekil("rect", sx, 2.9, w, 1.0, dolgu, None, "set " + ad)
        s.yazi([R(ad, kalin=True, boy=15), R(kisa, boy=10.5)], sx, 2.9, w, 1.0, renk=yazi_rengi, bosluk=1)
        s.yazi([R(alt, boy=11.5)] + ([R(alt2, boy=10, egik=True)] if alt2 else []), sx - 0.1, 3.98, w + 0.2, 0.5,
               renk=GRI, dikey="t", bosluk=1)
        sx += w + 0.06
    sinir = bx + bw * 0.67 - 0.03
    s.hat(sinir, 2.7, sinir, 4.6, "sızıntı sınırı", KOYU, 2, True)
    s.yazi([R("sızıntı sınırı", kalin=True, boy=11.5), R("Validasyon setini model hiç görmez", boy=10.5, renk=GRI)],
           sinir - 1.6, 4.62, 3.2, 0.5, dikey="t", bosluk=1)
    s.yazi([R("Doldurma değerleri ve dönüşümler yalnız Train setinden hesaplanır", kalin=True, boy=13),
            R("Bölme zamana göre ya da rastgele, satır ya da kimlik bazında yapılabilir. Kod bir bölme önerir, "
              "kararı kullanıcı verir.", boy=11.5, renk=GRI)],
           x0 + 0.2, 5.3, rw - 0.4, 1.05, bosluk=3)
    s.notlar = ("Ayrıntılı sunumdaki karşılığı slayt 8. Tip kontrolünde kullanıcı yalnız verinin izin verdiği "
                "dönüşümleri seçebilir. Kod seçimi kolonun tamamında dener, tek bir değer bile çevrilemezse kabul "
                "etmez. Bölmede üç set vardır. Model Train setinde öğrenir, model ayarları isteğe bağlı Test "
                "setinde seçilir, son ölçüm modelin hiç görmediği Validasyon setinde yapılır. Uygulamada bu setlerin "
                "kısa adları MS, OOS ve OOT olarak geçer. Doldurma değerleri ve dönüşümler yalnız Train setinden "
                "hesaplanır. Bölme zamana göre ya da rastgele, satır ya da kimlik bazında yapılabilir. Kod veriye "
                "bakarak bir bölme önerir, kararı kullanıcı verir. Örnekler gösterim amaçlıdır.")
    return s


# ---- 02 Degisken Muhendisligi ----------------------------------------------
def slayt_profil():
    s = Slayt("AKIS", B3, "02.1 Veri Profili ve Kalite",
              "Değişken üretmeden önce verinin kusurları bulunur. Kusurlu kolondan değişken üretilmez.")
    s.sekil("funnel", 0.8, 1.7, 3.2, 3.6, KIR, None, "huni")            # butun kolonlar 26 kontrolden gecer
    s.yazi("26", 0.8, 1.98, 3.2, 0.95, boy=48, kalin=True, renk=KIR)      # huninin beyaz agzinda
    s.yazi("kontrol", 0.8, 3.42, 3.2, 0.5, boy=20, kalin=True, renk=BEYAZ)   # huninin govdesinde
    s.yazi([R("verinin tamamında", boy=15), R("20 eşiği kullanıcı onaylar", boy=12.5)], 0.8, 5.4, 3.2, 0.8,
           renk=GRI, bosluk=3)
    sonuclar = [
        (7, "Üretime girmez", "Boş, sabit ya da kimlik gibi kolonlar", KIR2, BEYAZ,
         "Örneğin çoğu boş olan kolon girmez, yerine boşluk bayrağı önerilir"),
        (7, "Kararınıza bırakılır", "Geleceğe bakan ya da hedefi ele veren kolonlar", KIR, BEYAZ,
         "Örneğin LOAN_DUE_AMT_A30D geleceğe bakar, sızıntı riski diye sorulur"),
        (7, "Düzeltme seçilir", "Gizli eksik ya da uç değer taşıyan kolonlar", ORTA_PEMBE, KOYU,
         "Örneğin boş yerine yazılmış 9999 değeri boşa çevrilir"),
        (5, "Bilgi için gösterilir", "Yorumlarken bilinmesi gerekenler", ORTA_GRI, KOYU,
         "Örneğin son 30 günün toplamı son 90 günden büyükse gösterilir"),
    ]
    x0, w, bosluk = 4.6, 8.23, 0.04
    birim = (w - 3 * bosluk) / 26.0
    x = x0
    for adet, ad, _metin, dolgu, yazi_rengi, _ornek in sonuclar:         # 26 kontrolun dort sonuca dagilimi
        s.sekil("rect", x, 1.75, adet * birim, 0.75, dolgu, None, "pay " + ad)
        s.yazi(str(adet), x, 1.75, adet * birim, 0.75, boy=20, kalin=True, renk=yazi_rengi)
        x += adet * birim + bosluk
    for i, (_adet, ad, metin, dolgu, _yr, ornek) in enumerate(sonuclar):
        y = 2.68 + i * 0.89
        s.sekil("roundRect", x0, y + 0.22, 0.4, 0.4, dolgu, None, "renk " + ad, ayar=20000)
        s.yazi(ad, x0 + 0.6, y, 3.0, 0.84, boy=17, kalin=True, hiza="l")
        s.yazi([R(metin, boy=14), R(ornek, boy=11.5, egik=True, renk=GRI)], x0 + 3.6, y, w - 3.6, 0.84, hiza="l",
               bosluk=2)
    s.kutu(x0, 6.22, w, 0.42, "gri", "öneri kaynağı")
    s.yazi("Yapay zekâ yalnız anlam gerektiren beş kontrolde ve aynı içerikli kolonlarda önerir. Öbür öneriler "
           "koddan gelir.", x0 + 0.1, 6.22, w - 0.2, 0.42, boy=11.5)
    s.notlar = ("Ayrıntılı sunumdaki karşılığı slayt 9. Önce 20 eşik önerilen değeriyle gelir ve kullanıcı onaylar. Kod "
                "26 kontrolü verinin tamamında yapar. Her kontrol dört sonuçtan birine bağlıdır. Yedi kontrol kolonu "
                "üretime sokmaz, yedisi kararı kullanıcıya bırakır, yedisi düzeltme önerir, beşi yalnız bilgi verir. "
                "Yapay zekâ yalnız anlam gerektiren beş kontrolde ve aynı içerikli kolonlarda önerir, öbür öneriler koddan "
                "gelir. Karar kullanıcıdadır.")
    return s


def slayt_uretim():
    s = Slayt("AKIS", B3, "02.2 Kural Tabanlı Değişken Üretimi Nasıl İşler",
              "Var olan kolonlardan bilinen dönüşümlerle yeni değişkenler türetilir. Şu an üzerinde çalışılan adım budur.")
    surec_bandi(s, 1.55, 0.85, ["Hazırlık", "Katkı Ölçümü", "Öneri ve Tamamlama", "Karar ve Üretim"], vurgu=3, boy=16)
    yazilar = [("Kolonlar birimlere ayrılır", "41 dönüşümden hangilerinin yapılabileceği belirlenir."),
               ("Bilgi değeri en az 0,02 artmalı",
                "Kaynağının kopyası olan dönüşüm sayılmaz. Ölçüm Train satırlarında, örnekleme yapılmadan yapılır."),
               ("Yapay zekâ önerir, kod eksiği tamamlar",
                "Yapay zekâ farklı ailelerden anlamlı çiftleri de önerir. Kod değerli olup önerilmeyeni ekler."),
               ("Kullanıcı kartta ve sohbette seçer", "Onaydan sonra kod üretir ve üretim kodunu kaydeder.")]
    w = (EN - 0.75) / 4
    for i, (metin, ek) in enumerate(yazilar):
        x = SOL + i * (w + 0.25)
        cx = x + w / 2
        s.kutu(x, 2.6, w, 3.3, "gri", "aşama %d" % (i + 1))
        if i == 0:                                    # tek kolon ve bir aile
            etiketli_cip(s, cx - 0.6, 2.85, 1.2, 0.42, "kolon", "cerceve", boy=11.5, renk=KOYU, kod=True)
            for j, ad in enumerate(["L30D", "L90D", "L180D"]):
                etiketli_cip(s, x + 0.2 + j * 0.85, 3.55, 0.8, 0.42, ad, "islem", boy=10, renk=KIR, kod=True)
            s.yazi("tek kolon", x, 3.27, w, 0.24, boy=10, renk=GRI)
            s.yazi("aile", x, 3.98, w, 0.24, boy=10, renk=GRI)
        elif i == 1:                                  # kaynak ile donusumun bilgi degeri
            s.sekil("rect", cx - 0.85, 3.38, 0.55, 0.9, ORTA_GRI, None, "kaynak")
            s.sekil("rect", cx + 0.1, 3.02, 0.55, 1.26, KIR, None, "dönüşüm")
            s.hat(cx - 1.05, 4.28, cx + 0.85, 4.28, "taban", SOLUK, 1)
            s.yazi("0,10", cx - 1.05, 3.1, 0.95, 0.26, boy=11, kalin=True, renk=GRI)
            s.yazi("0,14", cx - 0.1, 2.74, 0.95, 0.26, boy=11, kalin=True, renk=KIR)
            s.yazi("kaynak", cx - 1.15, 4.3, 1.15, 0.24, boy=10, renk=GRI)
            s.yazi("dönüşüm", cx - 0.2, 4.3, 1.15, 0.24, boy=10, renk=GRI)
        elif i == 2:                                  # yapay zeka ve kod birlikte
            s.elips(cx - 0.6, 3.6, 0.95, PEMBE, None, "öneri zemini")
            ikon_isilti(s, cx - 0.6, 3.6, 0.72)
            s.yazi("+", cx - 0.2, 3.3, 0.4, 0.6, boy=22, kalin=True, renk=GRI)
            ikon_disli(s, cx + 0.62, 3.6, 0.85)
        else:                                         # karar ve sohbet
            s.elips(cx - 0.6, 3.6, 0.95, BEYAZ, (KIR, 2, False), "karar")
            ikon_onay(s, cx - 0.6, 3.6, 0.75, KIR, 3.5)
            s.sekil("wedgeRoundRectCallout", cx + 0.1, 3.15, 1.1, 0.75, KIR, None, "sohbet")
            s.yazi("sohbet", cx + 0.1, 3.15, 1.1, 0.75, boy=11.5, kalin=True, renk=BEYAZ)
        s.yazi([R(metin, kalin=True, boy=13.5), R(ek, boy=11.5, renk=GRI)], x + 0.15, 4.6, w - 0.3, 1.25,
               dikey="t", bosluk=3)
    s.kutu(SOL, 6.05, EN, 0.5, "onay", "sohbet notu")
    s.yazi("Sohbet platformda bu adımda açılır", SOL, 6.05, EN, 0.5, boy=15, kalin=True, renk=KIR)
    s.notlar = ("Ayrıntılı sunumdaki karşılığı slayt 10. Sıra önemlidir. Kod önce kolonları birimlere ayırır ve her "
                "dönüşümün katkısını Train satırlarında ölçer. Bilgi değeri en iyi kaynağına göre en az 0,02 artıyorsa "
                "ve dönüşüm kaynağının kopyası değilse yeni bilgi sayılır. Yapay zekâ bu ölçüme bakarak önerir, kod "
                "eksik kalanı tamamlar ve tekrarı ayıklar. Kullanıcı kartta ve sohbette seçer, kod üretir ve üretim "
                "kodunu kaydeder. Çubuklardaki sayılar gösterim amaçlıdır.")
    return s


def slayt_asamalar():
    s = Slayt("AKIS", B3, "02.2 Kural Tabanlı Değişken Üretiminde Üç Aşama ve 41 Dönüşüm",
              "Dönüşümler neye bakarak üretildiklerine göre üç aşamada toplanır.")
    asamalar = [
        ("Kolonun kendi dönüşümü", 18, "Büyük tutarların etkisi sıkışır", KIR2, BEYAZ, "tek kolon",
         [[K("TXN_OUT_AMT_L30D", 10), " kolonunun logaritması"]]),
        ("Aile içi üretim", 13, "Harcama hızlanıyor mu?", KIR, BEYAZ, "aynı ölçünün farklı dönemleri",
         [[K("TXN_OUT_AMT_L30D", 10), " bölü ", K("TXN_OUT_AMT_L90D", 10)]]),
        ("Aileler arası üretim", 10, "Giren mi fazla, çıkan mı?", ORTA_PEMBE, KOYU,
         "anlamlı çifti yapay zekâ önerir",
         [[K("TXN_IN_AMT_L30D", 10), " eksi ", K("TXN_OUT_AMT_L30D", 10)]]),
    ]
    w = (EN - 0.6) / 3
    for i, (baslik, sayi, anlam, _d, _y, bakis, ornek) in enumerate(asamalar):
        x = SOL + i * (w + 0.3)
        s.kutu(x, 1.5, w, 0.9, "veri", "aşama " + baslik)
        s.yazi([R(baslik, kalin=True, boy=18), R("%d dönüşüm, %s" % (sayi, bakis), boy=12.5)],
               x + 0.1, 1.5, w - 0.2, 0.9, renk=BEYAZ, bosluk=2)
        s.kutu(x, 2.5, w, 2.7, "gri", "şema " + baslik)
        if i == 0:                                    # carpik dagilim, donusumden sonra dengelenir
            ikon_cubuklar(s, x + 0.45, 2.8, 1.05, 1.15, [0.12, 0.18, 0.26, 1.0], ORTA_GRI)
            s.ok(x + 1.68, 3.45, x + 2.22, 3.45, "ok dönüşüm")
            ikon_cubuklar(s, x + 2.4, 2.8, 1.05, 1.15, [0.45, 0.58, 0.7, 1.0])
            s.yazi("ham", x + 0.45, 4.0, 1.05, 0.28, boy=10.5, renk=GRI)
            s.yazi("logaritma", x + 2.3, 4.0, 1.25, 0.28, boy=10.5, renk=GRI)
        elif i == 1:                                  # kisa donem bolu uzun donem
            s.sekil("rect", x + 0.55, 3.4, 0.5, 0.55, KIR, None, "kısa dönem")
            islem_rozeti(s, x + 1.45, 3.45, "bölü")
            s.sekil("rect", x + 1.85, 2.8, 0.5, 1.15, ORTA_GRI, None, "uzun dönem")
            s.ok(x + 2.5, 3.45, x + 2.82, 3.45, "ok sonuç")
            etiketli_cip(s, x + 2.86, 3.18, 0.9, 0.54, "oran", "veri", boy=14, renk=BEYAZ)
            s.yazi("L30D", x + 0.35, 4.0, 0.9, 0.28, boy=10.5, kalin=True, renk=GRI, yazitipi="Courier New")
            s.yazi("L90D", x + 1.65, 4.0, 0.9, 0.28, boy=10.5, kalin=True, renk=GRI, yazitipi="Courier New")
        else:                                         # giren eksi cikan
            s.sekil("upArrow", x + 0.5, 2.85, 0.6, 1.1, KIR, None, "giren")
            islem_rozeti(s, x + 1.45, 3.45, "eksi")
            s.sekil("downArrow", x + 1.8, 2.85, 0.6, 1.1, ORTA_GRI, None, "çıkan")
            s.ok(x + 2.5, 3.45, x + 2.72, 3.45, "ok sonuç")
            etiketli_cip(s, x + 2.76, 3.18, 1.05, 0.54, "net akış", "veri", boy=13, renk=BEYAZ)
            s.yazi("giren", x + 0.35, 4.0, 0.9, 0.28, boy=10.5, renk=GRI)
            s.yazi("çıkan", x + 1.65, 4.0, 0.9, 0.28, boy=10.5, renk=GRI)
        s.yazi([R(anlam, kalin=True, boy=15)] + ornek, x + 0.1, 4.32, w - 0.2, 0.85, boy=11, bosluk=3)
    s.yazi("41 dönüşüm", SOL, 5.55, 2.2, 0.8, boy=20, kalin=True, renk=KIR, hiza="l")
    x0, bw, bosluk = SOL + 2.3, EN - 2.3, 0.04                           # 41 donusumun uc asamaya dagilimi
    birim = (bw - 2 * bosluk) / 41.0
    x = x0
    for _b, sayi, _a, dolgu, yazi_rengi, _bk, _o in asamalar:
        s.sekil("rect", x, 5.6, sayi * birim, 0.7, dolgu, None, "pay %d" % sayi)
        s.yazi(str(sayi), x, 5.6, sayi * birim, 0.7, boy=20, kalin=True, renk=yazi_rengi)
        x += sayi * birim + bosluk
    s.notlar = ("Ayrıntılı sunumdaki karşılığı slayt 11. 41 dönüşüm üç aşamada toplanır. Birinci aşama tek kolonla, "
                "ikinci aşama aynı ölçünün farklı dönemleriyle, üçüncü aşama birbiriyle ilişkili farklı kolonlarla "
                "çalışır. Bir dönüşüm ancak kaynağından belirgin biçimde fazla bilgi taşıyorsa önerilir. Üstteki "
                "çubuklar gerçek veri değildir, yalnız fikri gösterir. Alttaki 18, 13 ve 10 sayıları gerçektir.")
    return s


# ---- sirada ve durum -------------------------------------------------------
SIRADA_CUMLE = "Bu adımlar sıradadır. İlk sürümleri kodda var, 02.2 tamamlandıktan sonra sırayla ele alınacak."


def slayt_sirada_hazirlama():
    s = Slayt("AKIS", B4, "02.3 AI Değişken Keşfi ile 03 Veri Anlama ve Hazırlama", SIRADA_CUMLE)
    karolar = [
        ("02.3", "AI Değişken Keşfi", "Yapay zekâ formül önerir, kod denetler ve hesaplar",
         "Formülde yalnız var olan kolonlar bulunur, hedef ve kimlik kullanılamaz"),
        ("03.1", "Tek Değişken Analizi (SFA)", "Her değişkenin hedefle ilişkisi ölçülür",
         "Eleme yapılmaz, değişkenin modele hangi hâliyle gireceği önerilir"),
        ("03.2", "Stabilite Analizi (PSI)", "Dağılım zamanla kayıyor mu diye bakılır",
         "Train seti ile Validasyon seti karşılaştırılır"),
        ("03.3", "Analitik Baz Set", "Set temizlenir ve dondurulur",
         "Kalan eksikler Train setinin medyanıyla doldurulur"),
    ]
    w = (EN - 0.75) / 4
    for i, (kod, ad, metin, ek) in enumerate(karolar):
        cx, cy, _d = karo(s, SOL + i * (w + 0.25), 1.75, w, 4.7, kod, ad, metin, ek=ek)
        if i == 0:
            ikon_isilti(s, cx, cy, 1.25)
        elif i == 1:
            ikon_cubuklar(s, cx - 0.48, cy - 0.45, 0.96, 0.88, [0.3, 0.5, 0.75, 1.0])
        elif i == 2:                                  # iki donemin dagilimi yan yana, biri kaymis
            ikon_cubuklar(s, cx - 0.52, cy - 0.38, 0.44, 0.74, [0.5, 1.0, 0.6], ORTA_GRI)
            ikon_cubuklar(s, cx + 0.08, cy - 0.38, 0.44, 0.74, [0.9, 0.55, 0.3])
        else:
            ikon_tablo(s, cx - 0.5, cy - 0.38, 0.8, 0.6, KIR)
            s.elips(cx + 0.38, cy + 0.26, 0.5, BEYAZ, (KIR, 1.25, False), "kilit zemini")
            ikon_kilit(s, cx + 0.38, cy + 0.28, 0.36)
    s.notlar = ("Ayrıntılı sunumdaki karşılığı slayt 12. Bu dört adımın ilk sürümleri kodda var ve henüz yeni düzene "
                "göre ele alınmadı. 02.3 adımında yapay zekâ kalıpların dışında formül önerir, kod formülü denetler ve "
                "hesabı kendisi yapar. 03 fazı üretimden sonra gelir, böylece ham ve üretilen değişkenlerin hepsi aynı "
                "ölçümden geçer. Analitik baz set dondurulduktan sonraki adımlar bu sette çalışır.")
    return s


def slayt_sirada_model():
    s = Slayt("AKIS", B4, "04 Değişken Değerlendirme ile 05 Modelleme ve Finalizasyon", SIRADA_CUMLE)
    karolar = [
        ("04.1", "Sızıntı Kontrolü", "Hedefi ele veren değişkenler ayrılır",
         "Train satırlarında hedefle ilişkisi aşırı yüksek olanlar"),
        ("04.2", "Aday Değişken Seti", "Tekrar eden ve zayıf değişkenler elenir",
         "Dört aşama, yalnız eğitim satırlarında"),
        ("05.1", "Model Karşılaştırması", "Yeni değişkenlerin katkısı ölçülür",
         "Fark yüzde 95 güven aralığıyla raporlanır"),
        ("05.2", "Algoritma Seçimi", "Dört algoritma aynı koşulda yarışır", "ROC-AUC, Gini, KS ve süreye bakılır"),
        ("05.3", "Model Finalizasyonu", "Son eğitim, doğrulama ve kayıt", "Model hiç görmediği sette doğrulanır"),
        ("05.4", "Değişken Kataloğu", "Her değişkenin formülü ve kodu saklanır",
         "Değişken o modelde kalmaz, yeniden üretilebilir"),
    ]
    w, h = (EN - 0.5) / 3, 2.25
    for i, (kod, ad, metin, ek) in enumerate(karolar):
        cx, cy, _d = karo(s, SOL + (i % 3) * (w + 0.25), 1.75 + (i // 3) * (h + 0.2), w, h, kod, ad, metin, yatay=True,
                          ek=ek)
        if i == 0:
            ikon_uyari(s, cx, cy, 0.82)
        elif i == 1:
            s.sekil("funnel", cx - 0.42, cy - 0.42, 0.84, 0.84, KIR, None, "eleme")
        elif i == 2:                                  # baz model ile zengin model
            s.sekil("rect", cx - 0.42, cy - 0.05, 0.34, 0.45, ORTA_GRI, None, "baz model")
            s.sekil("rect", cx + 0.08, cy - 0.38, 0.34, 0.78, KIR, None, "zengin model")
            s.hat(cx - 0.52, cy + 0.4, cx + 0.52, cy + 0.4, "taban", SOLUK, 1)
        elif i == 3:
            ikon_cubuklar(s, cx - 0.42, cy - 0.38, 0.84, 0.78, [0.7, 1.0, 0.85, 0.6])
        elif i == 4:
            ikon_onay(s, cx, cy, 1.0)
        else:
            ikon_belge(s, cx - 0.3, cy - 0.4, 0.6, 0.8)
    s.notlar = ("Ayrıntılı sunumdaki karşılığı slayt 13. Bu altı adımın ilk sürümleri kodda var. 04 fazı dondurulmuş "
                "sette çalışır ve yalnız eğitim satırlarını kullanır. 05.1 adımı asıl soruyu cevaplar ve üretilen "
                "değişkenlerin modele ölçülebilir bir katkı sağlayıp sağlamadığını gösterir. Değişken kataloğu "
                "sayesinde üretilen değişken o modelde kalmaz, başka bir çalışma onu yeniden üretebilir.")
    return s


def slayt_durum():
    s = Slayt("AKIS", B4, "Geliştirilenler ve Sıradakiler",
              "01 ve 02.1 geliştirildi. Şu an 02.2 Kural Tabanlı Değişken Üretimi üzerinde çalışılıyor.")
    s.kutu(SOL, 1.65, EN, 2.75, "gri", "akış bandı")
    adimlar = [("01", "Çalışma Kurulumu", "g", "Veri, sözlük, roller, adlar, tipler ve bölme"),
               ("02.1", "Veri Profili ve Kalite", "g", "20 eşik, 26 kontrol"),
               ("02.2", "Kural Tabanlı Değişken Üretimi", "s", "41 dönüşüm, katkı ölçümü, sohbet"),
               ("02.3", "AI Değişken Keşfi", "r", ""), ("03", "Veri Anlama ve Hazırlama", "r", ""),
               ("04", "Değişken Değerlendirme", "r", ""), ("05", "Modelleme ve Finalizasyon", "r", "")]
    sl, cy = EN / 7, 2.75
    s.hat(SOL + sl / 2, cy, SOL + sl / 2 + sl * 2, cy, "biten yol", KIR, 3)
    s.hat(SOL + sl / 2 + sl * 2, cy, SOL + sl / 2 + sl * 6, cy, "kalan yol", SOLUK, 1.5, True)
    for i, (no, ad, durum, icerik) in enumerate(adimlar):
        cx = SOL + sl * i + sl / 2
        d = 1.0 if durum == "s" else 0.82
        if durum == "g":
            s.elips(cx, cy, d, KIR, None, "adım " + no)
        elif durum == "s":
            s.elips(cx, cy, d, PEMBE, (KIR, 3.5, False), "adım " + no)
        else:
            s.elips(cx, cy, d, BEYAZ, (SOLUK, 1.5, True), "adım " + no)
        s.yazi(no, cx - d / 2, cy - d / 2, d, d, boy=15 if len(no) > 2 else 18, kalin=True,
               renk=BEYAZ if durum == "g" else (KIR if durum == "s" else SOLUK))
        s.yazi([R(ad, kalin=True, boy=12, renk=GRI if durum == "r" else KOYU)]
               + ([R(icerik, boy=10, renk=GRI)] if icerik else []),
               cx - sl / 2 + 0.05, cy + 0.6, sl - 0.1, 1.0, dikey="t", bosluk=3)
        if durum == "s":
            s.sekil("wedgeRoundRectCallout", cx - 0.9, 1.78, 1.8, 0.36, KIR, None, "şu an buradayız")
            s.yazi("Şu an buradayız", cx - 0.9, 1.78, 1.8, 0.36, boy=11, kalin=True, renk=BEYAZ)
    for i, (ad, d) in enumerate((("Geliştirildi", "g"), ("Üzerinde çalışılıyor", "s"), ("Sırada", "r"))):
        lx = 3.6 + i * 2.5
        durum_noktasi(s, lx, 4.72, d, 0.24, "anahtar " + ad)
        s.yazi(ad, lx + 0.24, 4.55, 2.1, 0.34, boy=12.5, renk=GRI, hiza="l")
    s.kutu(SOL, 5.3, EN, 1.05, "gri", "sonraki hedef")
    s.yazi([R("Sonraki hedef", kalin=True, boy=17, renk=KIR),
            R("Sınıflandırma tamamlandıktan sonra", boy=10.5, renk=GRI)],
           SOL + 0.3, 5.3, 2.5, 1.05, hiza="l", bosluk=2)
    for i, ad in enumerate(["Regresyon", "Segmentasyon", "Zaman serisi tahmini"]):
        x = SOL + 2.9 + i * 3.15
        s.sekil("roundRect", x, 5.52, 2.9, 0.6, BEYAZ, (SOLUK, 1.5, True), "hedef " + ad, ayar=30000)
        s.yazi(ad, x, 5.52, 2.9, 0.6, boy=15, kalin=True, renk=GRI)
    s.notlar = ("Ayrıntılı sunumdaki karşılığı slayt 14. Akış beş fazdan oluşur. 01 Çalışma Kurulumu ve 02.1 Veri "
                "Profili ve Kalite geliştirildi. Şu an 02.2 Kural Tabanlı Değişken Üretimi üzerinde çalışılıyor. 02.3 "
                "ve sonrasının ilk sürümleri kodda var ve sırayla ele alınacak. Sınıflandırmadan sonra regresyon, "
                "segmentasyon ve zaman serisi tahmini modellerinin açılması hedefleniyor.")
    return s


# ===========================================================================
# URETIM VE KAYIT
# ===========================================================================
def uret(zaman=None):
    """Sunumun .pptx icerigini bayt olarak doner. Gorseller her cagrida yeniden okunur."""
    gorselleri_sifirla()
    slaytlar = [slayt_kapak(), slayt_ihtiyac(), slayt_nerede(), slayt_prensip(), slayt_akis(),
                slayt_kurulum_veri(), slayt_kurulum_rol(), slayt_sozluk(), slayt_kurulum_bolme(),
                slayt_profil(), slayt_uretim(), slayt_asamalar(), slayt_sirada_hazirlama(),
                slayt_sirada_model(), slayt_durum()]
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
