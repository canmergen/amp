# -*- coding: utf-8 -*-
"""sunum_sade.py — Platformun KISA tanitim sunumunu (.pptx) ureten betik.

NE YAPAR
  Az yazili, ana fikirleri veren kisa sunumu bastan uretir: kapak, 8 icerik
  slayti ve kapanis. Ana fikir: yapay zeka ile degisken uretmek. Ayrintili
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

    # ---- bilesik ogeler ---------------------------------------------------
    def daire(self, metin, cx, cy, d, boy=12, ad=None):
        """Icinde beyaz kalin yazi olan kirmizi daire."""
        self.elips(cx, cy, d, KIR, None, "daire " + (ad or str(metin)))
        self.yazi(str(metin), cx - d / 2.0, cy - d / 2.0, d, d, boy=boy, kalin=True, renk=BEYAZ)

    def etiket(self, metin, x, y, w=5):
        self.yazi(metin, x, y, w, 0.26, boy=11, kalin=True, renk=GRI, hiza="l")

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
# YAZIM KURALI: az yazi, buyuk punto. Slaytlarda ve notlarda iki nokta,
# noktali virgul, orta nokta ve uzun cizgi kullanilmaz.
B1, B2, B3 = "Giriş", "Değişken üretimi", "Durum"
SOL, EN = 0.5, 12.33                        # icerik alaninin sol kenari ve eni (inc)


def K(metin, boy=12):
    """Kolon adi gibi kod parcasi: sabit aralikli, kirmizi, kalin."""
    return R(metin, kalin=True, renk=KIR, boy=boy, yazitipi="Courier New")


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
    s.notlar = "Kapak."
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
    s.notlar = "Kapanış. Soruları ve önerileri bu slaytta alabilirsiniz."
    return s


def _numarali_kart(s, x, y, w, h, tur, no, baslik, metin, baslik_boy=18, boy=13.5):
    """Sol ustunde numara dairesi olan kart: baslik ve tek kisa cumle."""
    s.kutu(x, y, w, h, tur, "kart " + baslik)
    s.daire(no, x + 0.45, y + 0.48, 0.5, boy=16, ad="no %s" % no)
    s.yazi(baslik, x + 0.85, y + 0.2, w - 1.0, 0.56, boy=baslik_boy, kalin=True, renk=KIR, hiza="l")
    s.yazi(metin, x + 0.25, y + 0.95, w - 0.5, h - 1.1, boy=boy, hiza="l", dikey="t")


def slayt_amac():
    s = Slayt("AKIS", B1, "Amaç")
    s.kutu(SOL, 1.45, EN, 1.7, "veri", "amaç")
    s.yazi("Yapay zekâ ile modele katkı sağlayan yeni değişkenler üretmek", SOL + 0.4, 1.45, EN - 0.8, 1.7, boy=30,
           kalin=True, renk=BEYAZ)
    kartlar = [
        ("Hazır tablodan", "Eldeki kolonlardan üretilebilecek en iyi değişken kombinasyonlarını bulur."),
        ("Kaynak tablolardan", "Baz tabloyu kendisi kurar. Akla gelmeyen tablolar da birleştirilir."),
        ("Ölçerek", "Modele yalnız katkısı ölçülmüş değişkenler girer."),
    ]
    w = (EN - 0.6) / 3
    for i, (baslik, metin) in enumerate(kartlar):
        _numarali_kart(s, SOL + i * (w + 0.3), 3.45, w, 2.55, "gri", i + 1, baslik, metin, baslik_boy=20, boy=17)
    s.yazi("Platform şu an sınıflandırma modelleri için açıktır.", SOL, 6.2, EN, 0.4, boy=14, egik=True, renk=GRI)
    s.notlar = ("Asıl amaç yapay zekâ ile değişken üretmektir. Bunun iki yolu var. Birincisi eldeki hazır tablodan en "
                "iyi değişken kombinasyonlarını bulmaktır. İkincisi baz tabloyu kaynak tablolardan kurmaktır, böylece "
                "akla gelmeyen tablolar da işe katılır. Üretilen her değişkenin katkısı ölçülür.")
    return s


def slayt_neden():
    s = Slayt("AKIS", B1, "Neden Gerekli")
    maddeler_ = [
        "Değişken üretimi elle yapılıyor ve kişiye bağlı kalıyor",
        "Bir modelde üretilen değişken o modelde kalıyor",
        "Akla gelmeyen tablolar ve fikirler modele hiç girmiyor",
        "Hazırlık uzun sürüyor, işler gecikiyor",
    ]
    h = 1.1
    for i, metin in enumerate(maddeler_):
        y = 1.5 + i * (h + 0.2)
        s.kutu(SOL, y, EN, h, "gri", "neden %d" % (i + 1))
        s.daire(i + 1, SOL + 0.65, y + h / 2, 0.56, boy=18, ad="neden no %d" % (i + 1))
        s.yazi(metin, SOL + 1.3, y, EN - 1.6, h, boy=24, hiza="l")
    s.notlar = ("Dört sorun var. Değişken üretimi elle yapılıyor ve kimin yaptığına göre değişiyor. Bir modelde üretilen "
                "değişkenler başka modellerde kullanılmıyor. Akla gelmeyen tablolar ve fikirler dışarıda kalıyor. "
                "Bunların hepsi süreyi uzatıyor.")
    return s


def slayt_nasil():
    s = Slayt("AKIS", B1, "Nasıl Çalışır")
    adimlar = [
        ("islem", "Kod ölçer", "Verinin tamamında sayar ve ölçer."),
        ("gri", "Yapay zekâ önerir", "Ölçüme ve kolonların anlamına bakar."),
        ("onay", "Kullanıcı karar verir", "Öneriyi kabul eder ya da değiştirir."),
        ("islem", "Kod üretir", "Değişkeni üretir ve kodunu kaydeder."),
    ]
    ara = 0.45
    w = (EN - 3 * ara) / 4
    for i, (tur, baslik, metin) in enumerate(adimlar):
        x = SOL + i * (w + ara)
        s.kutu(x, 1.6, w, 2.9, tur, "adım " + baslik)
        s.daire(i + 1, x + w / 2, 2.2, 0.66, boy=22, ad="adım no %d" % (i + 1))
        s.yazi(baslik, x + 0.15, 2.7, w - 0.3, 0.6, boy=20, kalin=True, renk=KIR)
        s.yazi(metin, x + 0.2, 3.35, w - 0.4, 1.0, boy=16, dikey="t")
        if i < 3:
            s.ok(x + w + 0.06, 3.05, x + w + ara - 0.06, 3.05, "ok adım %d" % i)
    s.kutu(SOL, 4.85, EN, 0.95, "veri", "son karar")
    s.yazi("Son karar her zaman kullanıcınındır", SOL, 4.85, EN, 0.95, boy=24, kalin=True, renk=BEYAZ)
    s.yazi("Seçilen veri setine ve sözlüğe yazılmaz. Platform kendi kopyasıyla çalışır.", SOL, 6.0, EN, 0.5, boy=16,
           renk=GRI)
    s.notlar = ("Sıra her adımda aynıdır. Kod ölçer, yapay zekâ önerir, kullanıcı karar verir, kod üretir. Yapay zekâ "
                "sayı hesaplamaz ve karar vermez. Kullanıcının onaylamadığı hiçbir şey veriye uygulanmaz.")
    return s


def slayt_nerede():
    s = Slayt("AKIS", B2, "Yapay Zekâ Değişkeni Nerede Üretir")
    sutunlar = [
        ("Kaynak tablolardan", "01 Çalışma Kurulumu",
         "Tabloların nasıl birleşeceğini ve hangi dönem toplamlarının üretileceğini önerir.",
         ["İşlem tablosundan son 30 günün işlem adedi"]),
        ("Bilinen dönüşümlerle", "02.2 Kural Tabanlı Değişken Üretimi",
         "41 dönüşümün katkısı ölçülür. Yapay zekâ bu veride işe yarayanları önerir.",
         [[K("TXN_OUT_AMT_L30D", 13)], ["bölü ", K("TXN_OUT_AMT_L90D", 13)]]),
        ("Yeni fikirlerle", "02.3 AI Değişken Keşfi",
         "Kalıpların dışında formül önerir. Kod formülü denetler ve hesaplar.",
         ["Kullanılan limit bölü toplam limit"]),
    ]
    w = (EN - 0.6) / 3
    for i, (baslik, adim, metin, ornek) in enumerate(sutunlar):
        x = SOL + i * (w + 0.3)
        s.kutu(x, 1.5, w, 1.05, "veri", "başlık " + baslik)
        s.yazi([R(baslik, kalin=True, boy=20), R(adim, boy=12)], x + 0.1, 1.5, w - 0.2, 1.05, renk=BEYAZ, bosluk=2)
        s.kutu(x, 2.65, w, 3.85, "gri", "gövde " + baslik)
        s.yazi(metin, x + 0.25, 2.85, w - 0.5, 1.7, boy=17, hiza="l", dikey="t")
        s.kutu(x + 0.2, 4.75, w - 0.4, 1.55, "cerceve", "örnek " + baslik)
        s.yazi([R("Örnek", kalin=True, renk=GRI, boy=12)] + ornek, x + 0.35, 4.8, w - 0.7, 1.45, boy=14, bosluk=3)
    s.notlar = ("Yapay zekâ üç yerde değişken üretimine katkı verir. Kaynak tablolarla başlanırsa birleştirme planını ve "
                "dönem toplamlarını önerir. 02.2 adımında bilinen 41 dönüşümden bu veride işe yarayanları önerir. 02.3 "
                "adımında kalıpların dışında formül önerir. 02.2 üzerinde çalışılıyor, 02.3 sırada. Örnekler gösterim "
                "amaçlıdır.")
    return s


def slayt_anlama():
    s = Slayt("AKIS", B2, "Önce Veri Anlaşılır",
              "01 Çalışma Kurulumu. Yapay zekâ kolonu ne kadar iyi anlarsa o kadar iyi değişken önerir.")
    maddeler_ = [
        "Eksik sözlük tanımları tamamlanır",
        "Kısaltmalar ve dönemler tek anlama bağlanır",
        "Kolon adları standart yazılışa çevrilir",
        "Her satırı kullanıcı onaylar",
    ]
    for i, metin in enumerate(maddeler_):
        y = 1.85 + i * 1.2
        s.daire(i + 1, SOL + 0.38, y + 0.4, 0.56, boy=18, ad="madde %d" % (i + 1))
        s.yazi(metin, SOL + 0.95, y, 5.1, 0.8, boy=20, hiza="l")
    x, w = 6.75, 6.08
    s.etiket("Bir kolonun önceki ve sonraki hâli", x, 1.55, w)
    s.kutu(x, 1.9, w, 1.8, "gri", "önce")
    s.yazi([R("Önce", kalin=True, renk=GRI, boy=13), K("OUT_TRX_30D_AMT", 20),
            R("son 30 gün giden işlem tutar", egik=True, boy=16)], x + 0.2, 1.95, w - 0.4, 1.7, bosluk=5)
    s.ok(x + w / 2, 3.76, x + w / 2, 4.14, "ok önce sonra")
    s.kutu(x, 4.2, w, 1.8, "onay", "sonra")
    s.yazi([R("Sonra", kalin=True, renk=KIR, boy=13), K("TXN_OUT_AMT_L30D", 20),
            R("son 30 günde giden işlemlerin tutarı", egik=True, boy=16)], x + 0.2, 4.25, w - 0.4, 1.7, bosluk=5)
    s.yazi("Yazılış, sıra ve dönem düzeldi. Açıklama netleşti.", x, 6.1, w, 0.4, boy=14, renk=GRI)
    s.notlar = ("Yapay zekânın iyi değişken önermesi için önce veriyi anlaması gerekir. Bu yüzden sözlükteki eksik "
                "tanımlar tamamlanır, kısaltmalar ve dönem parçaları tek anlama bağlanır, kolon adları standart "
                "yazılışa çevrilir. Örnekte TRX yerine TXN yazılır, zaman parçası sona gelir ve dönem son 30 gün "
                "anlamında L30D olur. Örnek gösterim amaçlıdır.")
    return s


def slayt_temizlik():
    s = Slayt("AKIS", B2, "Sonra Veri Temizlenir",
              "02.1 Veri Profili ve Kalite. Kusurlu kolondan değişken üretilmez.")
    s.kutu(SOL, 1.6, 3.3, 4.8, "veri", "26 kontrol")
    s.yazi([R("26", kalin=True, boy=72), R("kontrol", kalin=True, boy=26), R("verinin tamamında", boy=16)],
           SOL + 0.1, 1.6, 3.1, 4.8, renk=BEYAZ, bosluk=4)
    sonuclar = [
        ("Üretime girmez", "Boş, sabit ya da kimlik gibi kolonlar"),
        ("Kararınıza bırakılır", "Geleceğe bakan ya da hedefi ele veren kolonlar"),
        ("Düzeltme seçilir", "Gizli eksik ya da uç değer taşıyan kolonlar"),
        ("Bilgi için gösterilir", "Yorumlarken bilinmesi gerekenler"),
    ]
    x, w, h = 4.1, EN - 3.6, 1.08
    for i, (baslik, metin) in enumerate(sonuclar):
        y = 1.6 + i * (h + 0.16)
        s.kutu(x, y, w, h, "gri", "sonuç " + baslik)
        s.yazi(baslik, x + 0.3, y, 3.4, h, boy=20, kalin=True, renk=KIR, hiza="l")
        s.yazi(metin, x + 3.8, y, w - 4.0, h, boy=17, hiza="l")
    s.notlar = ("Değişken üretmeden önce verinin kusurları bulunur. Kod 26 kontrolü verinin tamamında yapar. Her bulgu "
                "dört sonuçtan birine düşer ve karar kullanıcıdadır. Eşikleri de kullanıcı onaylar.")
    return s


def slayt_uretim():
    s = Slayt("AKIS", B2, "Değişkenler Üretilir",
              "02.2 Kural Tabanlı Değişken Üretimi. Bir dönüşüm ancak kaynağından fazla bilgi taşıyorsa önerilir.")
    asamalar = [
        ("Kolonun kendi dönüşümü", "18 dönüşüm", [[K("TXN_OUT_AMT_L30D", 13.5)], "kolonunun logaritması"],
         "Büyük tutarların etkisi sıkışır"),
        ("Aile içi üretim", "13 dönüşüm", [[K("TXN_OUT_AMT_L30D", 13.5)], ["bölü ", K("TXN_OUT_AMT_L90D", 13.5)]],
         "Harcama hızlanıyor mu"),
        ("Aileler arası üretim", "10 dönüşüm", [[K("TXN_IN_AMT_L30D", 13.5)], ["eksi ", K("TXN_OUT_AMT_L30D", 13.5)]],
         "Hesaba giren mi fazla, çıkan mı"),
    ]
    w = (EN - 0.6) / 3
    for i, (baslik, sayi, ornek, anlam) in enumerate(asamalar):
        x = SOL + i * (w + 0.3)
        s.kutu(x, 1.6, w, 1.05, "veri", "aşama " + baslik)
        s.yazi([R(baslik, kalin=True, boy=19), R(sayi, boy=13.5)], x + 0.1, 1.6, w - 0.2, 1.05, renk=BEYAZ, bosluk=2)
        s.kutu(x, 2.75, w, 2.35, "gri", "örnek " + baslik)
        s.yazi(ornek, x + 0.2, 2.85, w - 0.4, 1.3, boy=15, bosluk=4)
        s.yazi(anlam, x + 0.2, 4.2, w - 0.4, 0.75, boy=17, kalin=True)
    akis = ["Kod katkıyı ölçer", "Yapay zekâ önerir", "Kullanıcı seçer", "Kod üretir"]
    ara = 0.4
    cw = (EN - 3 * ara) / 4
    for i, metin in enumerate(akis):
        x = SOL + i * (cw + ara)
        s.kutu(x, 5.45, cw, 0.9, "onay" if i == 2 else "islem", "akış " + metin)
        s.yazi(metin, x, 5.45, cw, 0.9, boy=17, kalin=True, renk=KIR)
        if i < 3:
            s.ok(x + cw + 0.05, 5.9, x + cw + ara - 0.05, 5.9, "ok akış %d" % i)
    s.notlar = ("Şu an üzerinde çalışılan adım budur. 41 dönüşüm üç aşamada toplanır. Kod her dönüşümün katkısını "
                "önce ölçer, yapay zekâ ölçüme bakarak önerir, kullanıcı kartta ya da sohbette seçer, kod üretir. Bir "
                "dönüşüm ancak kaynağından belirgin biçimde fazla bilgi taşıyorsa ve onun kopyası değilse önerilir. "
                "Örnekler gösterim amaçlıdır.")
    return s


def slayt_durum():
    s = Slayt("AKIS", B3, "İş Akışı ve Durum")
    fazlar = [
        ("01", "Çalışma Kurulumu", "Veri ve sözlük hazırlanır", "g", "Geliştirildi"),
        ("02", "Değişken Mühendisliği", "Değişkenler üretilir", "s", "02.2 üzerinde çalışılıyor"),
        ("03", "Veri Anlama ve Hazırlama", "Değişkenler ölçülür, set dondurulur", "r", "Sırada"),
        ("04", "Değişken Değerlendirme", "Zayıf ve riskli değişkenler elenir", "r", "Sırada"),
        ("05", "Modelleme ve Finalizasyon", "Model kurulur, katkı ölçülür", "r", "Sırada"),
    ]
    ara = 0.25
    w = (EN - 4 * ara) / 5
    for i, (no, ad, metin, durum, durum_yazi) in enumerate(fazlar):
        x = SOL + i * (w + ara)
        tur = {"g": "veri", "s": "simdi", "r": "soluk"}[durum]
        ana = BEYAZ if durum == "g" else (KIR if durum == "s" else GRI)
        s.kutu(x, 1.6, w, 3.0, tur, "faz " + no)
        s.yazi([R(no, kalin=True, boy=34, renk=ana), R(ad, kalin=True, boy=16, renk=ana),
                R(metin, boy=13.5, renk=BEYAZ if durum == "g" else GRI)], x + 0.12, 1.6, w - 0.24, 3.0, bosluk=6)
        s.yazi(durum_yazi, x, 4.72, w, 0.4, boy=15, kalin=(durum == "s"), renk=KIR if durum == "s" else GRI)
        if i < 4:
            s.ok(x + w + 0.03, 3.1, x + w + ara - 0.03, 3.1, "ok faz %d" % i, KIR if durum != "r" else SOLUK)
    s.kutu(SOL, 5.45, EN, 0.95, "gri", "sonraki hedef")
    s.yazi([[R("Sonraki hedef", kalin=True, renk=KIR),
             " sınıflandırmadan sonra regresyon, segmentasyon ve zaman serisi tahmini modelleridir."]],
           SOL + 0.3, 5.45, EN - 0.6, 0.95, boy=17)
    s.notlar = ("Akış beş fazdan oluşur. 01 Çalışma Kurulumu ve 02.1 Veri Profili ve Kalite geliştirildi. Şu an 02.2 "
                "Kural Tabanlı Değişken Üretimi üzerinde çalışılıyor. 02.3 ve sonrasının ilk sürümleri kodda var ve "
                "sırayla ele alınacak.")
    return s


# ===========================================================================
# URETIM VE KAYIT
# ===========================================================================
def uret(zaman=None):
    """Sunumun .pptx icerigini bayt olarak doner. Gorseller her cagrida yeniden okunur."""
    gorselleri_sifirla()
    slaytlar = [slayt_kapak(), slayt_amac(), slayt_neden(), slayt_nasil(), slayt_nerede(), slayt_anlama(),
                slayt_temizlik(), slayt_uretim(), slayt_durum()]
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
