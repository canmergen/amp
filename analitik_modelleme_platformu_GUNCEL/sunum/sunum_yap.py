# -*- coding: utf-8 -*-
"""sunum_yap.py — Akilli Modelleme Platformu tanitim sunumunu (.pptx) ureten betik.

NE YAPAR
  Tanitim sunumunu bastan uretir: kurumsal kirmizi zeminli kapak, 12 icerik
  slayti ve kapanis. Butun kutular, oklar ve yazilar PowerPoint'in kendi
  ogeleridir, PowerPoint'te duzenlenebilir. Robot gorselleri platformun kendi
  gorsel klasorunden (LLM_WEBAPP_GORSEL) okunup sunuma gomulur. Her slaytin
  konusmaci notu da yazilir.

GORSELLER
  Hangi dosyanin nerede kullanildigi asagidaki GORSELLER sozlugundedir.
  robot_header.png disindakiler uygulamanin da kullandigi dosyalardir
  (webapp/backend.py: GORSELLER). Dosya adi buyuk kucuk harf, alt cizgi ve
  uzanti (png, jpg) farkina takilmadan bulunur. Bir gorsel
  bulunamazsa sunum yine uretilir: o gorselin yeri bos kalir ya da eski
  gorunum (numara dairesi, yer tutucu) kullanilir. Calisma sonunda hangi
  gorselin bulundugu ekrana yazilir.
  Pillow (PIL) kuruluysa gorsellerin saydam kenarlari kirpilir ve buyuk
  gorseller kucultulur; kurulu degilse gorseller oldugu gibi gomulur.
  KAPANIS ve BASLIK_AVATARI ayarlariyla kapanis slaydi ve basliklardaki kucuk
  robot kapatilabilir.

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
    "kapak": "robot_header.png",          # kapaktaki robot (beyaz panelin icinde)
    "karsilama": "robot_welcome.png",     # ilk icerik slaydinin basligi ve kapanis
    "bot": "robot_chat.png",              # yapay zeka: baslik avatari, rol karti, ekran semasi
    "user": "robot_llm_person.png",       # kullanici: rol karti
    "dusunme": "robot_think.png",         # uzerinde calisilan adim
    "robot_alt": "robot_alt.png",         # sonunda hedeflenen (kitaplar ve kupa)
}
KAPANIS = True                             # sona tesekkur slaydi eklensin mi
BASLIK_AVATARI = True                      # icerik slaytlarinda basligin solunda kucuk robot olsun mu

# Renkler (onaltilik, # isareti yok). Kirmizi ve pembe platformun kendi
# renkleridir (webapp/style.css: --kirmizi, --kirmizi-koyu, --pembe-secili).
KIR, KIR2 = "D51115", "A00D10"            # kirmizi, koyu kirmizi
KIR_PARLAK = "E3231C"                      # kapak zemininin ortasi
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
# kac piksel olacagi). Avatarlar KIRPILMAZ: uygulamadaki gibi tuvalin tamami
# ortadan daireye alinir (kirpmak robotun basini ya da antenini kesebilir).
_HAZIRLIK = {
    "kapak": (True, 1400), "robot_alt": (True, 1100), "karsilama": (False, 800),
    "bot": (False, 320), "user": (False, 320), "dusunme": (False, 320),
}
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
            satirlar.append("  %s: %s; yeri boş bırakıldı ya da eski görünüm kullanıldı" % (ad, _neden.get(ad, "yok")))
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
    "sirada": (BEYAZ, (KIR, 1.5, True), False),      # istege bagli (kesik kirmizi)
    "gri": (ACIK, None, False),                      # aciklama karti, yapay zeka
    "soluk": (BEYAZ, (SOLUK, 1.5, True), False),     # sirada (kesik gri)
    "cerceve": (BEYAZ, (SOLUK, 1.0, False), False),  # ince gri cerceve
}


# ===========================================================================
# SLAYT
# ===========================================================================
class Slayt(object):
    """Bir slayt: sekiller sirayla eklenir. Olculer inc."""

    def __init__(self, yerlesim, bolum, baslik, ust=None, alt=None, avatar="bot"):
        self.yerlesim = yerlesim          # "KAPAK" ya da "AKIS"
        self.bolum = bolum
        self.baslik = baslik
        self.ust = ust                    # AKIS: baslik altindaki cumle; KAPAK: birim satiri
        self.alt = alt                    # KAPAK: tarih satiri
        self.notlar = ""
        self.gorseller = []               # bu slayttaki gorseller, iliski sirasiyla
        self.kapak_gorseli = False        # KAPAK: banda gorsel kondu mu (konmadiysa yer tutucu kalir)
        self._x = []
        self._sid = 3 if yerlesim == "AKIS" else 5      # ilk kimlikler yer tutucularin
        if yerlesim == "AKIS" and avatar and baslik_avatari_var():
            # Basligin solundaki kucuk robot: uygulamadaki sohbet bloklarinin basligi gibi
            self.avatar(avatar if _gorsel(avatar) else "bot", 0.9, 0.55, 0.8)

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

    def avatar(self, g_ad, cx, cy, d, halka=1.5):
        """Daire icinde gorsel (uygulamadaki sohbet avatari gibi): tuval ortadan
        kareye kirpilir, altina pembe zemin gelir. Zemini dolu gorselin cevresine
        kirmizi halka cizilir; saydam zeminli gorsele cizilmez (hazir kesilmis
        avatarin kendi halkasi varsa cift halka olmasin). Gorsel yoksa hicbir sey
        eklemez ve False doner."""
        g = _gorsel(g_ad)
        if g is None:
            return False
        kirpma = None
        if g.en > g.boy:
            pay = int(round((g.en - g.boy) / 2.0 / g.en * 100000))
            kirpma = (pay, 0, pay, 0)
        elif g.boy > g.en:
            pay = int(round((g.boy - g.en) / 2.0 / g.boy * 100000))
            kirpma = (0, pay, 0, pay)
        self.elips(cx, cy, d, PEMBE, None, "avatar zemini")
        self._resim(g_ad, cx - d / 2.0, cy - d / 2.0, d, d, True, None if g.saydam else (KIR, halka, False), kirpma)
        return True

    # ---- bilesik ogeler ---------------------------------------------------
    def daire(self, metin, cx, cy, d, boy=12, ad=None):
        """Icinde beyaz kalin yazi olan kirmizi daire."""
        self.elips(cx, cy, d, KIR, None, "daire " + (ad or str(metin)))
        self.yazi(str(metin), cx - d / 2.0, cy - d / 2.0, d, d, boy=boy, kalin=True, renk=BEYAZ)

    def lejant(self, ogeler):
        """Sag ustte gosterim anahtari: [(tur, ad), ...]."""
        for i, (tur, ad) in enumerate(ogeler):
            x, y = 9.2 + (i % 2) * 1.85, 0.22 + (i // 2) * 0.32
            self.kutu(x, y + 0.04, 0.42, 0.2, tur, "lejant " + ad)
            self.yazi(ad, x + 0.5, y, 1.32, 0.28, boy=10, renk=GRI, hiza="l")

    def dipnot(self, metin):
        self.yazi(metin, 0.5, 6.62, 11.7, 0.28, boy=10.5, egik=True, renk=GRI, hiza="l")

    def etiket(self, metin, x, y, w=5):
        self.yazi(metin, x, y, w, 0.26, boy=11, kalin=True, renk=GRI, hiza="l")

    def onay_pill(self, cx, y, ad):
        self.kutu(cx - 0.4, y, 0.8, 0.26, "onay", "onay " + ad)
        self.yazi("onay", cx - 0.4, y, 0.8, 0.26, boy=10, kalin=True, renk=KIR)

    def islem(self, x, y, w, h, baslik, kim="", aciklama="", tur="islem", renk=None):
        """Islem kutusu: baslik, kimin yaptigi, aciklama."""
        self.kutu(x, y, w, h, tur, baslik)
        p = [R(baslik, kalin=True, renk=renk or KIR, boy=12.5)]
        if kim:
            p.append(R(kim, boy=9.5, kalin=True, renk=GRI))
        if aciklama:
            p.append(R(aciklama, boy=10.5, renk=GRI if renk else KOYU))
        self.yazi(p, x + 0.06, y + 0.04, w - 0.12, h - 0.08, bosluk=2)

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

    # ---- XML --------------------------------------------------------------
    def _yer_tutucu(self, sid, ad, ph, metin):
        return ('<p:sp><p:nvSpPr><p:cNvPr id="%d" name=%s/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
                '<p:nvPr><p:ph %s/></p:nvPr></p:nvSpPr><p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/>'
                '<a:p><a:r><a:rPr lang="%s" dirty="0"/><a:t>%s</a:t></a:r></a:p></p:txBody></p:sp>'
                % (sid, _oz(ad), ph, DIL, _kacis(metin)))

    def xml(self, sira):
        """Slaytin XML'i. sira: 1'den baslayan slayt numarasi."""
        x = [_BAS, '<p:sld %s><p:cSld><p:spTree>' % _NS3, _GRUP,
             self._yer_tutucu(2, "Başlık", 'type="title"', self.baslik)]
        if self.yerlesim == "KAPAK":
            if self.ust:
                x.append(self._yer_tutucu(3, "Birim", 'type="body" sz="quarter" idx="10"', self.ust))
            if self.alt:
                x.append(self._yer_tutucu(4, "Tarih Satırı", 'type="body" sz="quarter" idx="11"', self.alt))
            if not self.kapak_gorseli:
                # Gorsel bulunamadi: bos resim yer tutucusu kalir, PowerPoint'te tiklaninca resim eklenir.
                x.append('<p:sp><p:nvSpPr><p:cNvPr id="5" name="Kapak Görseli"/><p:cNvSpPr>'
                         '<a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr><p:ph type="pic" sz="quarter" idx="12"/>'
                         '</p:nvPr></p:nvSpPr><p:spPr/></p:sp>')
        else:
            x.append(self._yer_tutucu(3, "Özet Cümle", 'type="body" sz="quarter" idx="10"', self.ust or ""))
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
            '<p:sldLayoutId id="2147483650" r:id="rId2"/></p:sldLayoutIdLst><p:txStyles><p:titleStyle>'
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


# Kapaktaki beyaz panel (inc): gorsel bunun icinde durur. Metinlerin sol kenari
# panelin sol kenariyla ayni hizadadir.
PANEL_X, PANEL_Y, PANEL_W, PANEL_H = 0.6, 2.55, 12.133, 3.6


def _yerlesim_kapak():
    """Kapak ve kapanis: kurumsal kapak gibi kirmizi zemin (ortasi parlak,
    kenarlari koyu), ustte beyaz baslik ve birim satiri, ortada kosesi yuvarlak
    beyaz panel (gorsel bunun icinde durur), altta tarih satiri."""
    zemin = ('<a:gradFill rotWithShape="1"><a:gsLst><a:gs pos="0"><a:srgbClr val="%s"/></a:gs>'
             '<a:gs pos="55000"><a:srgbClr val="%s"/></a:gs><a:gs pos="100000"><a:srgbClr val="%s"/></a:gs>'
             '</a:gsLst><a:path path="circle"><a:fillToRect l="50000" t="50000" r="50000" b="50000"/></a:path>'
             '</a:gradFill>' % (KIR_PARLAK, KIR, KIR2))
    golge = ('<a:effectLst><a:outerShdw blurRad="101600" dist="38100" dir="5400000" algn="t" rotWithShape="0">'
             '<a:srgbClr val="000000"><a:alpha val="28000"/></a:srgbClr></a:outerShdw></a:effectLst>')
    panel = _sp(3, "beyaz panel", _geo("roundRect", 5000), PANEL_X, PANEL_Y, PANEL_W, PANEL_H,
                _dolgu(BEYAZ) + _cizgi_xml(None) + golge)
    resim = ('<p:sp><p:nvSpPr><p:cNvPr id="7" name="Kapak Görseli"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
             '<p:nvPr><p:ph type="pic" sz="quarter" idx="12" hasCustomPrompt="1"/></p:nvPr></p:nvSpPr><p:spPr><a:xfrm>'
             '<a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
             '<p:txBody><a:bodyPr vert="horz" rtlCol="0" anchor="ctr"><a:noAutofit/></a:bodyPr><a:lstStyle>'
             '<a:lvl1pPr marL="0" indent="0" algn="ctr"><a:buNone/><a:defRPr sz="1400"><a:solidFill>'
             '<a:srgbClr val="%s"/></a:solidFill></a:defRPr></a:lvl1pPr></a:lstStyle><a:p><a:r><a:rPr lang="%s"/>'
             '<a:t>Kapak görseli</a:t></a:r></a:p></p:txBody></p:sp>'
             % (_emu(PANEL_X + (PANEL_W - 5.0) / 2.0), _emu(PANEL_Y + 0.25), _emu(5.0), _emu(PANEL_H - 0.5), GRI, DIL))
    return _yerlesim("Kapak",
                     panel
                     + _yt(2, "Başlık", 'type="title"', PANEL_X, 0.4, PANEL_W, 0.8, "b", "l", 32, BEYAZ, False,
                           "Başlık")
                     + _duz_cizgi(4, "başlık çizgisi", PANEL_X, 1.33, 1.6, 2.25, BEYAZ)
                     + _yt(5, "Birim", 'type="body" sz="quarter" idx="10"', PANEL_X, 1.45, PANEL_W, 0.42, "t", "l", 20,
                           BEYAZ, False, "Birim")
                     + _yt(6, "Tarih Satırı", 'type="body" sz="quarter" idx="11"', PANEL_X, 6.48, 8.0, 0.4, "ctr", "l",
                           14, BEYAZ, True, "Tarih")
                     + resim, zemin)


def baslik_avatari_var():
    """Icerik slaytlarinda basligin soluna kucuk robot konacak mi (ayar acik ve gorseli varsa)."""
    return bool(BASLIK_AVATARI) and _gorsel("bot") is not None


def _yerlesim_akis():
    """Icerik slayti: kirmizi baslik, altinda cizgi, ozet cumle, slayt numarasi.
    Baslik avatari varsa baslik ona yer acmak icin saga kayar."""
    bx, bw = (1.42, 7.6) if baslik_avatari_var() else (0.5, 8.5)
    return _yerlesim("İçerik",
                     _yt(2, "Başlık", 'type="title"', bx, 0.28, bw, 0.58, "ctr", "l", 24, KIR, True, "Başlık")
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
    yerlesim_no = {"KAPAK": 1, "AKIS": 2}
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
    for i in (1, 2):
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
    p.append(("ppt/theme/theme1.xml", _tema("Akıllı Modelleme")))
    p.append(("ppt/theme/theme2.xml", _tema("Akıllı Modelleme Notlar")))

    # Ana slayt ve yerlesimler
    p.append(("ppt/slideMasters/slideMaster1.xml", _ana_slayt()))
    p.append(("ppt/slideMasters/_rels/slideMaster1.xml.rels", _iliskiler(
        [("slideLayout", "../slideLayouts/slideLayout1.xml"), ("slideLayout", "../slideLayouts/slideLayout2.xml"),
         ("theme", "../theme/theme1.xml")])))
    for i, icerik in ((1, _yerlesim_kapak()), (2, _yerlesim_akis())):
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
B1, B2, B3, B4 = "Giriş", "Nasıl çalışır", "Yapılanlar", "Sırada ve durum"
LEJANT = [("veri", "Veri / Çıktı"), ("islem", "İşlem (kod)"), ("onay", "Kullanıcı onayı"), ("sirada", "İsteğe bağlı")]


def _panele_gorsel(s, g_ad):
    """Kapaktaki beyaz panele gorsel yerlestirir, panelin ortasina hizalar.
    Saydam zeminli gorsel panelin ustune tasar (robotun basi panelin disina
    cikar); zemini dolu gorsel panelin icinde kalir. Alt kenarinda kesilmis
    cizim panelin alt kenarina oturur, digerleri biraz yukarida durur. En boy
    orani ne olursa olsun sigar: genis gorsel ene, dar gorsel boya gore
    olceklenir. Gorsel yoksa False doner."""
    g = _gorsel(g_ad)
    if g is None:
        return False
    tasma, alt_bosluk, azami_en = 0.45, (0 if g.alt_kesik else 0.18), PANEL_W - 0.8
    h = PANEL_H - alt_bosluk + tasma if g.saydam else PANEL_H - 0.5
    w = h * g.oran
    daraldi = w > azami_en                            # cok genis gorsel: ene gore olceklenir
    if daraldi:
        w, h = azami_en, azami_en / g.oran
    if g.saydam and (g.alt_kesik or not daraldi):
        taban = PANEL_Y + PANEL_H - alt_bosluk        # panelin tabanina oturur, ustten tasar
    else:
        taban = PANEL_Y + (PANEL_H + h) / 2.0         # panelin icinde, dikeyde ortada
    s._resim(g_ad, PANEL_X + (PANEL_W - w) / 2.0, taban - h, w, h)
    s.kapak_gorseli = True
    return True


def slayt_kapak():
    s = Slayt("KAPAK", B1, "Kurumsal Analitik, Tahminleme ve İçgörü Platformu",
              "Perakende Krediler Analitik ve Tahsis İş Birimi", "Ekiplere tanıtım · Kasım 2026")
    _panele_gorsel(s, "kapak")
    s.notlar = ("Kapak. Robot görseli platformun görsel klasöründen gelir; bulunamadıysa beyaz panelin içinde resim yer "
                "tutucusu kalır, tıklayıp resim ekleyebilirsiniz. Sunum, platformu hiç bilmeyen ekiplere göre sıralandı: "
                "neden yapıyoruz, nedir, nasıl çalışır, bugüne kadar hangi adımlar geliştirildi, sırada ne var.")
    return s


def slayt_kapanis():
    s = Slayt("KAPAK", B4, "Teşekkürler", "Sorularınız ve önerileriniz için")
    if s.avatar("karsilama", PANEL_X + PANEL_W / 2.0, PANEL_Y + PANEL_H / 2.0, 3.0, halka=2.25):
        s.kapak_gorseli = True
    else:
        _panele_gorsel(s, "kapak")
    s.notlar = "Kapanış. Soruları ve önerileri bu slaytta alın."
    return s


def slayt_neden():
    s = Slayt("AKIS", B1, "Akıllı Modelleme Platformu · Neden Yapıyoruz",
              "Model geliştirmenin tekrar eden işleri bugün büyük ölçüde elle yürüyor; platform bu işleri tek akışta "
              "toplamayı amaçlıyor.", avatar="karsilama")
    s.yazi("Projenin Amacı", 0.5, 1.52, 1.6, 0.66, boy=15, egik=True, renk=KIR, hiza="l")
    s.kutu(2.15, 1.52, 10.68, 0.66, "islem", "amaç")
    s.yazi("Model geliştirme sürecini yapay zekâ ile hızlandırmak, modele yalnız katkısı ölçülen değişkenleri almak ve "
           "harcanan emeği katma değeri yüksek işlere yönlendirmek.", 2.3, 1.52, 10.38, 0.66, boy=13)
    s.etiket("Konu", 0.5, 2.36, 2.4)
    s.etiket("Elle yürütülen süreçte", 3.15, 2.36, 4.3)
    s.etiket("Platformda", 7.9, 2.36, 4.93)
    neden = [
        ("Sözlük ve kolon adları",
         "Kısaltmalı kolon adları ve eksik ya da tutarsız açıklamalar her çalışmada yeniden çözülür.",
         "Adlar ve açıklamalar bir kez onaylanır, hafızada kalır; sonraki çalışmaya hazır gelir."),
        ("Veri kalitesi",
         "Kontroller kişiden kişiye değişir; neyin neden çıkarıldığı her zaman kayda geçmez.",
         "Aynı 26 kontrol her çalışmada verinin tamamında yapılır; her karar gerekçesiyle kaydedilir."),
        ("Değişken üretimi",
         "Dönüşümler için kod elle yazılır; hangilerinin denendiği kişinin deneyimine bağlıdır.",
         "Dönüşümleri yapay zekâ önerir, katkısını kod ölçer, kullanıcı seçer; kod yazmak gerekmez."),
        ("İzlenebilirlik",
         "Kararların izi dağınık notlarda ve dosyalarda kalır; çalışmayı devralmak zordur.",
         "Her adımın kararı, gerekçesi ve üretim kodu tek yerde durur; çalışma kaldığı yerden açılır."),
    ]
    for i, (konu, bugun, platform) in enumerate(neden):
        y = 2.66 + i * 0.92
        s.veri(0.5, y, 2.4, 0.82, konu)
        s.kutu(3.15, y, 4.3, 0.82, "cerceve", "bugün " + konu)
        s.yazi(bugun, 3.27, y, 4.06, 0.82, boy=11.5, renk=GRI, hiza="l")
        s.ok(7.48, y + 0.41, 7.87, y + 0.41, "ok " + konu)
        s.kutu(7.9, y, 4.93, 0.82, "islem", "platform " + konu)
        s.yazi(platform, 8.02, y, 4.69, 0.82, boy=11.5, hiza="l")
    s.dipnot("Platform şu an sınıflandırma modelleri (0 ve 1 değerli hedef) için açık; farklı veri setlerinde aynı "
             "akış kullanılır.")
    s.notlar = ("Bu slayt neden sorusunu cevaplar. Soldaki sütun elle yürütülen bir model geliştirme sürecindeki tipik "
                "durumu, sağdaki sütun platformun bunu nasıl ele aldığını gösterir. Soldaki ifadeler genel çerçevedir; "
                "kendi ekibinizin durumuna göre düzenleyin. Sağdaki maddelerin hepsi platformda bugün çalışan "
                "özelliklerdir.")
    return s


def slayt_nedir():
    s = Slayt("AKIS", B1, "Akıllı Modelleme Platformu · Nedir, Nasıl Çalışır",
              "Dataiku içinde çalışan bir web uygulaması: ham veriden modele giden yolu adım adım yürütür; her adımda "
              "önerir, onayla ilerler.")
    roller = [
        ("gri", "Yapay zekâ önerir",
         ["Kolon adlarının ve açıklamalarının anlamı", "Kalite kontrollerinde anlam gerektiren kararlar",
          "Hangi kolona hangi dönüşümün uygulanacağı, gerekçesiyle", "Kullanıcının sorularına cevap"]),
        ("onay", "Kullanıcı onaylar",
         ["Her öneriyi gerekçesiyle görür", "Değiştirir, ekler ya da çıkarır", "Onaylamadığı hiçbir şey uygulanmaz",
          "İstediği adıma geri dönebilir"]),
        ("islem", "Kod hesaplar",
         ["Bütün sayım ve ölçümleri verinin tamamında yapar", "Onaylanan düzeltmeleri ve değişkenleri üretir",
          "Yapay zekânın cevabını denetler", "Kararı, gerekçeyi ve üretim kodunu kaydeder"]),
    ]
    # Uygulamadaki avatarlar: yapay zeka (bot) ve kullanici (user); kod icin kod
    # isareti. Iki gorselden biri yoksa uc kartta da numara dairesi kullanilir.
    gorselli = _gorsel("bot") is not None and _gorsel("user") is not None
    for i, (tur, ad, liste) in enumerate(roller):
        x = 0.5 + i * (3.75 + 0.54)
        s.kutu(x, 1.6, 3.75, 3.0, tur, "rol " + ad)
        if gorselli and i < 2:
            s.avatar(("bot", "user")[i], x + 0.56, 2.05, 0.68)
        elif gorselli:
            s.elips(x + 0.56, 2.05, 0.68, KIR, None, "rol kod")
            s.yazi("</>", x + 0.22, 1.71, 0.68, 0.68, boy=14, kalin=True, renk=BEYAZ, yazitipi="Courier New")
        else:
            s.daire(i + 1, x + 0.5, 2.05, 0.5, boy=16, ad="rol no %d" % (i + 1))
        s.yazi(ad, x + (1.05 if gorselli else 0.9), 1.8, 2.6, 0.5, boy=17, kalin=True, renk=KIR, hiza="l")
        s.yazi(maddeler(liste), x + 0.25, 2.5, 3.3, 2.0, boy=12.5, hiza="l", dikey="t", bosluk=8)
        if i < 2:
            s.ok(x + 3.75 + 0.06, 3.1, x + 3.75 + 0.48, 3.1, "ok rol %d" % i)
    s.etiket("Nerede çalışır", 0.5, 4.88)
    nerede = [
        ("Dataiku içinde", "Tarayıcıdan, Dataiku projesinin içinden açılır"),
        ("Veri Dataiku'dan", "Yetkiniz olan veri setleri listeden seçilir"),
        ("Büyük veri kümede", "Büyük tablolar Spark ile işlenir; örnekleme yapılmaz"),
        ("Kayıt ve hafıza", "Çalışmalar ve onaylanan bilgiler proje klasöründe saklanır"),
    ]
    nw = (12.33 - 0.75) / 4
    for i, (ad, aciklama) in enumerate(nerede):
        x = 0.5 + i * (nw + 0.25)
        s.kutu(x, 5.18, nw, 1.0, "gri", "nerede " + ad)
        s.yazi([R(ad, kalin=True, boy=12.5, renk=KIR), R(aciklama, boy=11)], x + 0.12, 5.18, nw - 0.24, 1.0, bosluk=2)
    s.dipnot("Yapay zekâ yalnız önerir; sayılar her zaman koddan gelir, karar her zaman kullanıcınındır.")
    s.notlar = ("Platformun çalışma ilkesi üç role dayanır. Yapay zekâ (bir dil modeli) öneri ve gerekçe üretir. "
                "Kullanıcı her öneriyi görür ve onaylar. Hesaplamayı, üretimi ve kaydı kod yapar; yapay zekânın cevabı "
                "da kodla denetlenir. Dil modeline Dataiku'nun LLM bağlantısı üzerinden erişilir.")
    return s


def slayt_akis():
    s = Slayt("AKIS", B2, "Akıllı Modelleme Platformu · Uçtan Uca Akış",
              "Beş faz; her faz bir öncekinin çıktısını kullanır. Her fazda yapay zekâ önerir, kullanıcı onaylar, "
              "kod uygular.")
    s.lejant([("veri", "Veri / Çıktı"), ("islem", "İşlem (kod)"), ("onay", "Kullanıcı onayı"), ("soluk", "Sırada")])
    px, pw = 2.35, 1.85
    pg = (12.83 - px - 5 * pw) / 4
    s.kutu(px, 1.52, 12.83 - px, 0.4, "islem", "yapay zekâ bandı")
    s.yazi([[R("Yapay Zekâ ve Sohbet  ", kalin=True, renk=KIR),
             "her adımda öneriyi gerekçesiyle sunar, soruları yanıtlar"]], px, 1.52, 12.83 - px, 0.4, boy=11.5)
    s.avatar("bot", px + 0.02, 1.72, 0.6)
    s.veri(0.5, 2.47, 1.5, 1.45, "Girdi", "Veri seti ve sözlük; hiç değişmez")
    s.ok(2.0, 3.2, px - 0.02, 3.2, "ok girdi")
    fazlar = [
        ("01 Çalışma Kurulumu", "Veri ve sözlük seçilir; kolonların anlamı ve adları onaylanır; veri bölünür",
         "Güncel Veri ve Sözlük", "g", "Geliştirildi"),
        ("02 Değişken Mühendisliği",
         "Kalite kontrol edilir; bilinen dönüşümlerle ve yapay zekâ ile yeni değişkenler üretilir",
         "Yeni Değişkenler", "s", "02.1 geliştirildi · 02.3 sırada"),
        ("03 Veri Anlama ve Hazırlama",
         "Değişkenlerin hedefle ilişkisi ve zamandaki kararlılığı ölçülür; set sabitlenir",
         "Analitik Baz Set", "r", "Sırada"),
        ("04 Değişken Değerlendirme", "Hedefi ele veren şüpheli değişkenler ayıklanır; katkısı zayıf olanlar elenir",
         "Aday Değişken Seti", "r", "Sırada"),
        ("05 Modelleme ve Finalizasyon",
         "Modeller aynı koşullarda karşılaştırılır; final model doğrulanır ve belgelenir",
         "Final Model ve Doküman", "r", "Sırada"),
    ]
    for i, (ad, aciklama, cikti, durum, durum_yazi) in enumerate(fazlar):
        x = px + i * (pw + pg)
        cx = x + pw / 2
        sirada = durum == "r"
        renk = SOLUK if sirada else KIR
        s.ok(cx, 1.92, cx, 2.02, "ok bant %d" % i, renk)
        s.onay_pill(cx, 2.03, ad)
        s.ok(cx, 2.29, cx, 2.45, "ok onay %d" % i, renk)
        s.islem(x, 2.47, pw, 1.45, ad, "", aciklama, "soluk" if sirada else ("simdi" if durum == "s" else "islem"),
                GRI if sirada else None)
        if i < 4:
            s.ok(x + pw + 0.02, 3.2, x + pw + pg - 0.02, 3.2, "ok faz %d" % i, SOLUK if i >= 1 else KIR)
        s.ok(cx, 3.92, cx, 4.06, "ok çıktı %d" % i, renk)
        if sirada:
            s.kutu(x, 4.08, pw, 0.52, "soluk", "çıktı " + cikti)
            s.yazi(cikti, x, 4.08, pw, 0.52, boy=11, kalin=True, renk=GRI)
        else:
            s.veri(x, 4.08, pw, 0.52, cikti)
        if durum == "s":
            s.kutu(x + 0.1, 4.7, pw - 0.2, 0.26, "veri", "şu an")
            s.yazi("Şu an: 02.2 üzerinde çalışılıyor", x + 0.1, 4.7, pw - 0.2, 0.26, boy=9, kalin=True, renk=BEYAZ)
            s.yazi(durum_yazi, x, 4.98, pw, 0.24, boy=9.5, renk=GRI)
        else:
            s.yazi(durum_yazi, x, 4.7, pw, 0.26, boy=10, renk=GRI, kalin=(durum == "g"))
    s.kutu(px, 5.36, 12.83 - px, 0.4, "veri", "proje hafızası")
    s.yazi([[R("Proje Hafızası  ", kalin=True),
             "onaylanan tanımlar, ad parçaları ve kararlar burada tutulur; aynı şey iki kez sorulmaz"]],
           px, 5.36, 12.83 - px, 0.4, boy=11.5, renk=BEYAZ)
    s.kutu(0.5, 5.95, 12.33, 0.55, "gri", "hedef")
    s.yazi([[R("Sonunda hedeflenen:  ", kalin=True, renk=KIR),
             "kod yazmadan, onaylarla ilerleyen bir süreçle doğrulanmış final model, değişken kataloğu ve model "
             "dokümanı."]], 0.7, 5.95, 11.93, 0.55, boy=12)
    s.notlar = ("Bütün yolun haritası. Girdi kullanıcının seçtiği veri seti ve sözlüğüdür; platform ona dokunmaz. "
                "Kırmızı kutular her fazın çıktısıdır. Düz çerçeveli fazlar geliştirildi, kalın çerçeveli faz üzerinde "
                "çalışılıyor, kesik gri çerçeveliler sırada. 02'nin içinde 02.1 Veri Profili ve Kalite geliştirildi, "
                "şu an 02.2 Geleneksel Değişken Üretimi üzerinde çalışıyoruz.")
    return s


def slayt_adim():
    s = Slayt("AKIS", B2, "Akıllı Modelleme Platformu · Bir Adım Nasıl İlerler",
              "Her adım aynı sırayı izler; kullanıcı onaylamadan veriye hiçbir şey uygulanmaz.")
    s.etiket("Adımın akışı", 0.5, 1.47)
    dongu = [
        ("Analiz", "kod", "Veri ve önceki kararlar okunur; sayımlar verinin tamamında yapılır.", "islem"),
        ("Öneri", "yapay zekâ ve kod", "Sonuç ve öneri, gerekçesiyle bir kartta gösterilir.", "gri"),
        ("İnceleme", "kullanıcı", "Kartta seçer, değiştirir; isterse sohbetle sorar.", "onay"),
        ("Onay", "kullanıcı", "Onay düğmesi kararı kesinleştirir.", "onay"),
        ("Uygulama ve kayıt", "kod", "Karar veriye uygulanır; gerekçe ve üretim kodu kaydedilir.", "islem"),
    ]
    for i, (ad, kim, aciklama, tur) in enumerate(dongu):
        y = 1.78 + i * 0.84
        s.daire(i + 1, 0.72, y + 0.36, 0.38, boy=13, ad="adım no %d" % (i + 1))
        if i < 4:
            s.ok(0.72, y + 0.57, 0.72, y + 0.99, "ok döngü %d" % i)
        s.kutu(1.1, y, 5.4, 0.72, tur, "döngü " + ad)
        s.yazi([R(ad, kalin=True, renk=KIR, boy=12.5), R(kim, boy=9.5, kalin=True, renk=GRI)],
               1.2, y, 1.75, 0.72, hiza="l")
        s.yazi(aciklama, 3.0, y, 3.4, 0.72, boy=11, hiza="l")
    s.kutu(1.1, 6.02, 5.4, 0.46, "sirada", "geri dön")
    s.yazi([[R("Geri Dön  ", kalin=True, renk=KIR), "önceki bir adıma dönülür, oradan yeniden ilerlenir"]],
           1.2, 6.02, 5.2, 0.46, boy=11, hiza="l")
    # Ekranin semasi
    s.etiket("Ekran (şematik)", 6.95, 1.47)
    x0, y0, w0, h0 = 6.95, 1.78, 5.88, 4.7
    s.kutu(x0, y0, w0, h0, "cerceve", "ekran çerçevesi")
    s.dik(x0 + 0.04, y0 + 0.04, 1.5, h0 - 0.08, ACIK, "sol bar")
    menu = [("Ana Sayfa", 0.22, False, False), ("Model Platformu", 0.62, True, False),
            ("Model Akışı", 0.92, False, True), ("Model Gösterge Paneli", 1.2, False, False),
            ("Model Değişkenleri", 1.48, False, False), ("Model Özeti", 1.76, False, False),
            ("Arşiv", 3.95, False, False), ("Yeni Çalışma", 4.23, False, False)]
    for ad, dy, kalin, secili in menu:
        if secili:
            s.dik(x0 + 0.04, y0 + dy, 0.05, 0.26, KIR, "seçili işaret")
        s.yazi(ad, x0 + (0.28 if 0.7 < dy < 2 else 0.16), y0 + dy, 1.3, 0.26, boy=9, kalin=(kalin or secili),
               renk=KIR if secili else KOYU, hiza="l")
    mx, mw = x0 + 1.7, w0 - 1.86
    s.kutu(mx, y0 + 0.16, mw, 0.42, "cerceve", "iş akışı barı")
    s.kutu(mx + 0.08, y0 + 0.23, 0.8, 0.28, "gri", "iş akışı düğmesi")
    s.yazi("İş Akışı", mx + 0.08, y0 + 0.23, 0.8, 0.28, boy=9, kalin=True)
    s.yazi("bulunulan faz ve adım", mx + 0.98, y0 + 0.16, 1.7, 0.42, boy=9, renk=GRI, hiza="l")
    s.yazi("tamamlanan / toplam adım", mx + mw - 1.75, y0 + 0.16, 1.67, 0.42, boy=9, renk=GRI, hiza="r")
    s.kutu(mx, y0 + 0.74, mw, 3.0, "islem", "adım bloğu")
    blok_x = mx + 0.58 if s.avatar("bot", mx + 0.32, y0 + 0.96, 0.34, halka=1) else mx + 0.15
    s.yazi("Adım bloğu", blok_x, y0 + 0.82, 2.4, 0.28, boy=11.5, kalin=True, renk=KIR, hiza="l")
    s.yazi("sonuç ve öneri, gerekçesiyle", mx + 0.15, y0 + 1.1, 2.8, 0.24, boy=9, renk=GRI, hiza="l")
    for k in range(4):
        yy = y0 + 1.48 + k * 0.36
        s.dik(mx + 0.15, yy, 1.3, 0.22, "E3E3E3", "satır kolon %d" % k)
        s.dik(mx + 1.55, yy, 1.45 - (k % 2) * 0.3, 0.22, ACIK, "satır bulgu %d" % k)
        s.kutu(mx + mw - 0.95, yy - 0.02, 0.8, 0.26, "onay", "satır karar %d" % k)
        s.yazi("karar", mx + mw - 0.95, yy - 0.02, 0.8, 0.26, boy=8.5, renk=KIR)
    s.kutu(mx + 0.15, y0 + 3.28, 0.95, 0.32, "cerceve", "geri dön düğmesi")
    s.yazi("Geri Dön", mx + 0.15, y0 + 3.28, 0.95, 0.32, boy=9.5)
    s.kutu(mx + mw - 1.1, y0 + 3.28, 0.95, 0.32, "veri", "onayla düğmesi")
    s.yazi("Onayla", mx + mw - 1.1, y0 + 3.28, 0.95, 0.32, boy=9.5, kalin=True, renk=BEYAZ)
    s.kutu(mx, y0 + 3.9, mw, 0.42, "cerceve", "sohbet kutusu")
    s.yazi("Soru ya da istek yazılır", mx + 0.15, y0 + 3.9, 2.6, 0.42, boy=9.5, egik=True, renk=GRI, hiza="l")
    s.daire(2, mx + mw - 0.3, y0 + 1.02, 0.3, boy=10.5, ad="işaret 2")
    s.daire(3, mx + mw - 0.3, y0 + 4.11, 0.3, boy=10.5, ad="işaret 3")
    s.daire(4, mx + mw - 1.3, y0 + 3.44, 0.3, boy=10.5, ad="işaret 4")
    s.dipnot("Her model için bir çalışma açılır; çalışma her adımda kaydedilir ve Arşiv'den kaldığı yerden "
             "sürdürülür.")
    s.notlar = ("Kullanıcının platformda gördüğü şey budur: adımlar alt alta bloklar hâlinde ilerler. Her blokta analiz "
                "sonucu, öneri ve gerekçesi, kullanıcının karar verdiği alanlar ve onay düğmesi bulunur. Sağdaki çizim "
                "ekranın şemasıdır; gerçek ekran görüntüsüyle değiştirilebilir. Şemadaki 2, 3 ve 4 numaraları soldaki "
                "adımlara karşılık gelir.")
    return s


def slayt_veri_kurali():
    s = Slayt("AKIS", B2, "Akıllı Modelleme Platformu · Veri Kuralı ve Güvenceler",
              "Seçilen veri setine ve sözlüğe dokunulmaz; platform kendi kopyalarıyla çalışır.")
    s.veri(0.5, 1.62, 3.3, 1.0, "Seçilen Veri Seti ve Sözlük", "kullanıcının verisi; hiçbir şey yazılmaz")
    s.ok(3.82, 2.12, 4.48, 2.12, "ok kopya")
    s.veri(4.5, 1.62, 3.3, 1.0, "Baz Kopya", "birebir kopya; bir kez yazılır, değişmez")
    s.ok(7.82, 2.12, 8.48, 2.12, "ok güncel")
    s.veri(8.5, 1.62, 4.33, 1.0, "Güncel Kopya", "verinin ve sözlüğün en son hâli; her adımda güncellenir")
    s.yazi("Dataiku'daki adı: <Çalışma>_BAZ_VERI, <Çalışma>_BAZ_SOZLUK", 4.5, 2.66, 3.3, 0.4, boy=9.5, renk=GRI,
           dikey="t")
    s.yazi("Dataiku'daki adı: <Çalışma>_UPDT_VERI, <Çalışma>_UPDT_SOZLUK", 8.5, 2.66, 4.33, 0.4, boy=9.5, renk=GRI,
           dikey="t")
    s.etiket("Güncel kopya adım adım zenginleşir", 0.5, 3.3)
    s.yazi("kalın çerçeve: üzerinde çalışılan adım · kesik çerçeve: sırada", 6.5, 3.3, 6.33, 0.26, boy=10, renk=GRI,
           hiza="r")
    zen = [("01", "tipler, yeni adlar, bölme", "islem"), ("02.1", "düzeltmeler, çözüm kolonları", "islem"),
           ("02.2", "yeni değişkenler", "simdi"), ("02.3", "yapay zekâ keşfi", "soluk"),
           ("03", "analitik baz set", "soluk")]
    zw = (12.33 - 4 * 0.3) / 5
    for i, (no, ad, tur) in enumerate(zen):
        x = 0.5 + i * (zw + 0.3)
        sr = tur == "soluk"
        s.kutu(x, 3.62, zw, 0.66, tur, "zenginleşme " + no)
        s.yazi([[R(no + "  ", kalin=True, renk=GRI if sr else KIR, boy=12),
                 R(ad, boy=10.5, renk=GRI if sr else KOYU)]], x + 0.05, 3.62, zw - 0.1, 0.66)
        if i < 4:
            s.ok(x + zw + 0.03, 3.95, x + zw + 0.27, 3.95, "ok zenginleşme %d" % i, SOLUK if i >= 2 else KIR)
    guvenceler = [
        ("Girdi değişmez", "Seçilen veri setine ve sözlüğe hiçbir şey yazılmaz. Düzeltmeler ve yeni adlar yalnız "
                           "platformun kopyalarında geçerlidir."),
        ("Tam veri, örneklem yok", "Sayımlar ve ölçümler verinin tamamında yapılır. Büyük tablolar kümede işlenir."),
        ("Sızıntıya karşı sınır", "Doldurma değerleri ve dönüşüm ayarları yalnız eğitim setinden öğrenilir. Geleceğe "
                                  "bakan ya da hedefi ele veren kolonlar ayıklanır."),
        ("Her karar kayıtlı", "Her adımın kararı, gerekçesi ve üretim kodu çalışmanın kaydında durur."),
    ]
    gw = (12.33 - 0.75) / 4
    for i, (ad, aciklama) in enumerate(guvenceler):
        s.kart(0.5 + i * (gw + 0.25), 4.62, gw, 1.8, "gri", ad, aciklama, boy=11.5)
    s.dipnot("Sızıntı: modelin gerçek kullanımda bilemeyeceği bir bilginin eğitim verisine karışması; model kâğıt "
             "üstünde iyi, gerçekte kötü çıkar.")
    s.notlar = ("Başka ekiplerin ilk sorusu genellikle veriye ne olduğudur. Seçilen tablo ve sözlük yalnız okunur. "
                "Platform bir kez birebir kopya alır (baz kopya) ve bütün değişiklikleri güncel kopyaya yazar. Geri "
                "dönülürse güncel kopya, baz kopyadan kararlar yeniden uygulanarak kurulur. Çalışma adı Dataiku'daki "
                "veri seti adlarının önüne gelir.")
    return s


def slayt_kurulum():
    s = Slayt("AKIS", B3, "01 Çalışma Kurulumu · Veri ve Sözlük Hazırlığı",
              "Hangi tabloyla çalışılacağı, kolonların ne anlama geldiği, neyin tahmin edileceği ve verinin nasıl "
              "bölüneceği bu fazda belirlenir.")
    s.lejant(LEJANT)
    s.veri(0.5, 1.92, 1.5, 0.95, "Veri Seti ve Sözlük", "Dataiku'dan seçilir")
    bx, bw = 2.3, 1.57
    bg = (12.83 - bx - 6 * bw) / 5
    s.ok(2.0, 2.4, bx - 0.02, 2.4, "ok girdi")
    adimlar = [
        ("Başlangıç ve Veri Seçimi", "Hazır tablo seçilir ya da kaynak tablolar birleştirilir"),
        ("Kolon Rolleri", "Hedef, kimlik ve dönem kolonu belirlenir"),
        ("Eksik Sözlük Tanımları", "Açıklaması olmayan kolonlara öneri getirilir"),
        ("Sözlük ve Kolon Adı Kontrolü", "Adlar ve açıklamalar düzeltilir; sonraki sayfada"),
        ("Değişken Listesi ve Tip Kontrolü", "Liste, tipler ve tanımlar son kez onaylanır"),
        ("Örneklem ve Doğrulama Tasarımı", "Veri eğitim ve ölçüm setlerine ayrılır"),
    ]
    for i, (ad, aciklama) in enumerate(adimlar):
        x = bx + i * (bw + bg)
        s.onay_pill(x + bw / 2, 1.5, ad)
        s.ok(x + bw / 2, 1.76, x + bw / 2, 1.9, "ok onay %d" % i)
        s.kutu(x, 1.92, bw, 0.95, "sirada" if i == 3 else "islem", ad)
        s.yazi(ad, x + 0.05, 1.92, bw - 0.1, 0.95, boy=12, kalin=True, renk=KIR)
        s.yazi(aciklama, x, 2.92, bw, 0.52, boy=10, renk=GRI, dikey="t")
        if i < 5:
            s.ok(x + bw + 0.02, 2.4, x + bw + bg - 0.02, 2.4, "ok adım %d" % i)
    cw = (12.33 - 0.5) / 3
    s.kart(0.5, 3.6, cw, 1.7, "gri", "Kolon rolleri nedir",
           ["Hedef: modelin tahmin edeceği kolon", "Kimlik: müşteriyi ya da kaydı gösteren kolon",
            "Dönem: kaydın ait olduğu tarih", "Bu üç kolon hiçbir dönüşüme girmez"])
    s.kart(0.5 + cw + 0.25, 3.6, cw, 1.7, "gri", "Sözlük ve eksik tanımlar",
           ["Sözlük: her kolonun ne anlama geldiğini yazan tablo",
            "Tanımı olmayan kolona önce onaylı tanım, yoksa yapay zekâ önerisi getirilir",
            "Tamamen boş ve tek değerli kolonlar çıkarılır"])
    x3 = 0.5 + 2 * (cw + 0.25)
    s.kutu(x3, 3.6, cw, 1.7, "gri", "kart bölme")
    s.yazi("Veri neden bölünür", x3 + 0.2, 3.7, cw - 0.4, 0.34, boy=13, kalin=True, renk=KIR, hiza="l")
    sx = x3 + 0.2
    for ad, pay, renk in (("Train", 0.5, KIR), ("Test", 0.22, KIR2), ("Validasyon", 0.28, GRI)):
        w = (cw - 0.4) * pay
        s.dik(sx, 4.1, w - 0.03, 0.3, renk, "set " + ad)
        s.yazi(ad, sx, 4.1, w - 0.03, 0.3, boy=10, kalin=True, renk=BEYAZ)
        sx += w
    s.yazi("Model Train setinde öğrenir, ayarlar Test setinde seçilir, son ölçüm zamanda sonraki Validasyon setinde "
           "yapılır. Başarı böylece modelin görmediği veride ölçülür.", x3 + 0.2, 4.46, cw - 0.4, 0.8, boy=10.5,
           hiza="l", dikey="t")
    s.etiket("Bu fazın çıktıları", 0.5, 5.4)
    ciktilar = [("Baz Kopya", "girdinin değişmeyen kopyası"), ("Güncel Veri ve Sözlük", "tipler, tanımlar, yeni adlar"),
                ("Bölme", "her satırın hangi sette olduğu"), ("Proje Hafızası", "onaylanan tanımlar ve anlamlar")]
    ckw = (12.33 - 0.75) / 4
    for i, (ad, aciklama) in enumerate(ciktilar):
        s.veri(0.5 + i * (ckw + 0.25), 5.68, ckw, 0.72, ad, aciklama)
    s.dipnot("Kaynak tablolarla başlanırsa birleştirme planını yapay zekâ önerir; her satır yalnız kendi tarihinden "
             "önceki bilgiyi görür.")
    s.notlar = ("01 fazı geliştirildi. Sözlük, her kolonun ne anlama geldiğini yazan tablodur; seçilmesi zorunlu "
                "değildir, eksik tanımlar bu fazda tamamlanır. Kolon rollerinde şu an sınıflandırma (0 ve 1 değerli "
                "hedef) açıktır. Tablonun daha önce onaylanan rolleri yeni çalışmada hazır gelir. Eksik tanımda yapay "
                "zekâ, kolon adındaki onaylı parçalara ve benzer kolonların tanımlarına bakarak öneri yazar. Çubuktaki "
                "genişlikler oran göstermez; bölme oranlarını platform önerir, kullanıcı değiştirebilir.")
    return s


def slayt_sozluk():
    s = Slayt("AKIS", B3, "01 Çalışma Kurulumu · Sözlük ve Kolon Adı Kontrolü",
              "Yapay zekâ da insan da kolonu adından ve açıklamasından tanır; bu adım her kolonun kesin anlaşılmasını "
              "sağlar.")
    s.yazi("Örnek kolon adı (gösterim amaçlı)", 0.5, 1.6, 2.9, 0.55, boy=11, kalin=True, renk=GRI, hiza="l")
    for i, parca in enumerate(("TXN", "OUT", "30D", "AMT")):
        x = 3.45 + i * 1.25
        s.kutu(x, 1.6, 1.13, 0.55, "onay" if parca == "30D" else "islem", "parça " + parca)
        s.yazi(parca, x, 1.6, 1.13, 0.55, boy=15, kalin=True, yazitipi="Courier New", renk=KIR)
    s.ok(8.5, 1.875, 8.95, 1.875, "ok anlam")
    s.yazi("Son 30 günde giden işlemlerin tutarı", 9.05, 1.6, 3.78, 0.55, boy=13, kalin=True, hiza="l")
    kontroller = [
        ("1. Dönem Bilgisi", "Adlardaki zaman parçalarının anlamı ve yönü onaylanır. Geleceğe bakan parça sızıntı "
                             "adayıdır.", "30D = son 30 gün"),
        ("2. Ad Parçaları", "Kısaltmaların anlamı ve standart yazılışı onaylanır. Farklı yazılan aynı parçalar "
                            "birleşir.", "TXN işlem · OUT giden · AMT tutar"),
        ("3. Kolon Kartları", "Onaylı parçalardan her kolonun kartı kurulur, sözlükteki tanımla karşılaştırılır; tek "
                              "ve açık bir açıklama yazılır.", "Son 30 günde giden işlemlerin tutarı"),
        ("4. Kolon Adları", "Yeni ad standart yazılışlarla ve belirlenen sırayla kurulur. Eski ad saklanır.",
         ["TXN_OUT_30D_AMT", "→ TXN_OUT_AMT_L30D"]),
    ]
    kw = (12.33 - 3 * 0.35) / 4
    for i, (ad, aciklama, ornek) in enumerate(kontroller):
        x = 0.5 + i * (kw + 0.35)
        s.kutu(x, 2.5, kw, 2.15, "islem", "kontrol " + ad)
        s.yazi(ad, x + 0.15, 2.58, kw - 0.3, 0.34, boy=13, kalin=True, renk=KIR, hiza="l")
        s.yazi(aciklama, x + 0.15, 2.95, kw - 0.3, 1.0, boy=11.5, hiza="l", dikey="t")
        s.kutu(x + 0.12, 3.98, kw - 0.24, 0.55, "gri", "örnek " + ad)
        s.yazi(ornek, x + 0.15, 3.98, kw - 0.3, 0.55, boy=9.5 if i == 3 else 10.5, kalin=True,
               yazitipi="Courier New" if i == 3 else None)
        if i < 3:
            s.ok(x + kw + 0.03, 3.57, x + kw + 0.32, 3.57, "ok kontrol %d" % i)
    s.kart(0.5, 4.95, 6.04, 1.5, "gri", "Kullanıcıyı yormadan",
           ["Sorular toplu sorulur; bir cevap ilgili bütün kolonlara uygulanır",
            "Adı yalnız sayılarla ayrılan kolonlar aile olarak birlikte onaylanır",
            "Daha önce onaylanan kontrol yeni çalışmada yeniden uygulanabilir"])
    s.etiket("Sonuç", 6.79, 4.95)
    sw = (6.04 - 0.4) / 3
    for i, ad in enumerate(("Açık ve tek tip açıklamalar", "Standart kolon adları", "Hafızada kalan anlamlar")):
        s.veri(6.79 + i * (sw + 0.2), 5.28, sw, 1.17, ad)
    s.dipnot("Bu adım isteğe bağlıdır. Düzeltmeler yalnız platformun kopyalarına yazılır; kaynak tablo ve sözlük "
             "değişmez.")
    s.notlar = ("Bu adım geliştirildi ve platformun en çok emek verilen kısımlarından biridir. Sözlüklerde tanımların "
                "bir kısmı eksik ya da hatalı, adlarda kısaltmalar tutarsız olabilir. Dört alt adım sırayla çalışır ve "
                "her biri bir öncekinin onayladığını kesin bilgi olarak kullanır. Onaylanan anlamlar hafızaya yazılır; "
                "aynı parça bir sonraki çalışmada sorulmaz. Örnek kolon adı ve anlamları gösterim amaçlıdır.")
    return s


def slayt_kalite():
    s = Slayt("AKIS", B3, "02.1 Veri Profili ve Kalite · Verinin Kusurlarını Bulma",
              "Değişken üretmeden önce verinin kusurları bulunur; her bulgu için öneri sunulur, karar kullanıcıda "
              "kalır.")
    s.lejant(LEJANT[:3])
    s.veri(0.5, 1.6, 1.7, 0.95, "Güncel Veri", "01'in çıktısı")
    px, pw, pg = 2.5, 1.75, 0.3
    s.ok(2.2, 2.08, px - 0.02, 2.08, "ok girdi")
    adimlar = [
        ("Kontrol Eşikleri", "onay", "Eşikler önerilen değer ve gerekçesiyle sorulur"),
        ("26 Kontrol", "islem", "Verinin tamamında, örneklemesiz"),
        ("Karar Kartı", "onay", "Her bulguya öneri: tut, çıkar, düzelt ya da çözüm"),
        ("Uygulama", "islem", "Kararlar veriye uygulanır ve kaydedilir"),
    ]
    for i, (ad, tur, aciklama) in enumerate(adimlar):
        x = px + i * (pw + pg)
        s.kutu(x, 1.6, pw, 0.95, tur, ad)
        s.yazi(ad, x, 1.6, pw, 0.95, boy=13, kalin=True, renk=KIR)
        s.yazi(aciklama, x, 2.6, pw, 0.5, boy=10, renk=GRI, dikey="t")
        s.ok(x + pw + 0.02, 2.08, x + pw + pg - 0.02, 2.08, "ok adım %d" % i)
    son = px + 4 * (pw + pg)
    s.veri(son, 1.6, 12.83 - son, 0.95, "Güncel Veri", "düzeltilmiş kolonlar, çözüm kolonları")
    s.etiket("Ne aranır, bulununca ne olur", 0.5, 3.22)
    gruplar = [
        ("Üretime girmez", "7 kontrol · önce çözüm aranır",
         "Çoğu boş, sabit, kimlik benzeri, çok kategorili ya da birbirinin kopyası kolonlar. Atmak yerine çözüm "
         "önerilir: gruplama, “dolu mu” bayrağı, metinden özellik, tarihten gün farkı."),
        ("Karar kullanıcıda", "7 kontrol · tut ya da çıkar",
         "Sızıntı şüphesi (geleceğe bakan pencere, hedefi neredeyse birebir veren kolon), neredeyse sabit kolon, bir "
         "dönemde boş kolon, dönemler arasında sıçrayan değer."),
        ("Düzeltme", "7 kontrol · kolon yerinde düzeltilir",
         "-999 gibi özel kodlar, “NULL” diye yazılmış boşlar, aynı kategorinin farklı yazımları, beklenmeyen "
         "negatifler, uç değerler."),
        ("Bilgi", "5 kontrol · işlem yapılmaz",
         "Sıfır yoğunluğu, pencereler arası tutarsızlık, tekrar eden satır, eğitim ve ölçüm setleri arasında çakışma."),
    ]
    gw = (12.33 - 0.75) / 4
    for i, (ad, alt, aciklama) in enumerate(gruplar):
        x = 0.5 + i * (gw + 0.25)
        s.kutu(x, 3.5, gw, 1.72, "gri", "grup " + ad)
        s.yazi([R(ad, kalin=True, renk=KIR, boy=13), R(alt, kalin=True, boy=10.5, renk=GRI), R(aciklama, boy=10.5)],
               x + 0.15, 3.56, gw - 0.3, 1.62, hiza="l", dikey="t", bosluk=3)
    alt_kutular = [
        ("Öneriyi kim verir",
         "Çoğunu kod verir, kolonun kendi sayılarına bakarak; gerekçe sayıyla yazılır. Yapay zekâ yalnız anlam "
         "gerektiren yerde devreye girer, örneğin aynı içerikli iki kolondan hangisinin kalacağında."),
        ("Sonuç ne olur",
         "Onaylanan düzeltmeler güncel veriye uygulanır. Üretime girmeyen kolonlardan yeni değişken üretilmez; "
         "çözümün ürettiği yeni kolon sonraki adımlara girer."),
    ]
    for i, (ad, aciklama) in enumerate(alt_kutular):
        x = 0.5 + i * (6.04 + 0.25)
        s.kutu(x, 5.42, 6.04, 1.05, "islem", ad)
        s.yazi([R(ad, kalin=True, renk=KIR, boy=12.5), R(aciklama, boy=10.5)], x + 0.15, 5.44, 5.74, 1.01, hiza="l",
               bosluk=2)
    s.dipnot("Kontroller verinin tamamında yapılır; eşikler önerilen değerle gelir, kullanıcı değiştirebilir.")
    s.notlar = ("02.1 geliştirildi. Kontroller dört grupta toplanır. Karar kartında satırlar renklidir: sorunsuz, "
                "dikkat, üretime girmez. Çözüm seçeneği yalnız işe yarayacaksa sunulur: eğitim setinin bir yarısında "
                "öğrenilir, öbür yarısında hedefi ayırıp ayırmadığına bakılır. Öğrenilen her şey (gruplar, sınırlar) "
                "yalnız eğitim setinden gelir.")
    return s


def slayt_uretim():
    s = Slayt("AKIS", B3, "02.2 Geleneksel Değişken Üretimi · Nasıl Çalışıyor",
              "Var olan kolonlardan oran, fark, eğilim gibi bilinen dönüşümlerle yeni değişkenler türetilir; "
              "hangisinin işe yaradığını ölçüm söyler.")
    s.lejant([("veri", "Veri / Çıktı"), ("islem", "İşlem (kod)"), ("onay", "Kullanıcı onayı"), ("gri", "Yapay zekâ")])
    r1y, r2y, bw, bh = 1.62, 3.3, 2.3, 1.34
    xs = [2.95, 5.45, 7.95, 10.5]
    s.veri(0.5, r1y, 2.1, bh, "Güncel Veri ve Onaylı Sözlük", "01 ve 02.1'in çıktısı")
    ust = [
        ("1. Birimler", "kod", "Kolonlar birlikte değerlendirilecek gruplara ayrılır: tek kolon, aynı ölçünün farklı "
                               "dönemleri, anlamlı çiftler", "islem"),
        ("2. Uygunluk", "kod", "41 dönüşümden hangileri bu grupta yapılabilir; yapılamıyorsa nedeni yazılır", "islem"),
        ("3. Seçim", "yapay zekâ", "Her grup için dönüşümleri seçer ve gerekçesini yazar", "gri"),
        ("4. Katkı Ölçümü", "kod", "Yeni değişken, türetildiği kolonlardan daha fazla bilgi taşıyor mu ölçülür",
         "islem"),
    ]
    s.ok(2.6, r1y + bh / 2, xs[0] - 0.02, r1y + bh / 2, "ok girdi")
    for i, (ad, kim, aciklama, tur) in enumerate(ust):
        s.islem(xs[i], r1y, bw, bh, ad, kim, aciklama, tur)
        if i < 3:
            s.ok(xs[i] + bw + 0.02, r1y + bh / 2, xs[i + 1] - 0.02, r1y + bh / 2, "ok üst %d" % i)
    s.ok(xs[3] + bw / 2, r1y + bh + 0.02, xs[3] + bw / 2, r2y - 0.02, "ok aşağı")
    alt = [
        ("5. Tamamlama", "kod", "Değer katan ama seçilmemiş dönüşüm eklenir; aynı bilgiyi veren ayıklanır", "islem",
         xs[3]),
        ("6. Karar", "kullanıcı", "Kartta ve sohbette ekler, çıkarır, sorar; son sözü söyler", "onay", xs[2]),
        ("7. Üretim", "kod", "Onayla birlikte değişkenler üretilir, üretim kodu kaydedilir", "islem", xs[1]),
    ]
    for i, (ad, kim, aciklama, tur, x) in enumerate(alt):
        s.islem(x, r2y, bw, bh, ad, kim, aciklama, tur)
        sonraki = alt[i + 1][4] if i < 2 else xs[0]
        s.ok(x - 0.02, r2y + bh / 2, sonraki + bw + 0.02, r2y + bh / 2, "ok alt %d" % i)
    s.veri(xs[0], r2y, bw, bh, "Güncel Veri", "yeni değişkenler ve üretim kodu")
    s.kart(0.5, 4.95, 6.04, 1.5, "gri", "Karar kartında",
           ["Her dönüşüm sade adı, ne yaptığı ve örneğiyle; bu veride kullanılabilir mi, neden",
            "Her öneride kimin önerdiği ve ölçümün ne dediği",
            "Her değişiklik anında görünür ve geri alınabilir"])
    s.kart(6.79, 4.95, 6.04, 1.5, "gri", "Plan üzerine sohbette",
           ["“Bütün oranları kaldır” gibi toplu istekler yazılabilir",
            "Cevaplar ölçüme dayanır; değişikliği kod kurar, kullanıcı onaylar",
            "Önceki konuşmalar kısa bir özetle hatırlanır"])
    s.dipnot("Bu adım üzerinde çalışılıyor; kart ve sohbet geri bildirimle güncelleniyor.")
    s.notlar = ("Şu an üzerinde çalıştığımız adım. Birim, birlikte değerlendirilen kolon ya da kolon grubudur; örneğin "
                "aynı ölçünün son 30, 90 ve 180 günlük kolonları bir pencere ailesidir. Katkı ölçümü yalnız eğitim "
                "satırlarında yapılır: bilgi değeri (IV) en iyi kaynağa göre en az 0,02 artıyorsa ve kaynaklarla sıra "
                "ilişkisi 0,95'in altındaysa dönüşüm yeni bilgi sayılır. Ağaç ve doğrusal model ayrımı yoktur; iki "
                "modelde de kullanılabilecek dönüşümler tek seferde değerlendirilir.")
    return s


def slayt_asamalar():
    s = Slayt("AKIS", B3, "02.2 Geleneksel Değişken Üretimi · Üç Aşama",
              "Toplam 41 dönüşüm, neye bakarak üretildiklerine göre üç aşamada toplanır.")
    asamalar = [
        ("1. Kolonun kendi dönüşümü", "18 dönüşüm",
         "Tek bir kolon kendi içinde dönüştürülür: ölçeği düzeltilir, bayrak ya da dilim üretilir.",
         "Logaritma · uç değerleri kırpma · sıraya çevirme · sıfır mı bayrağı · ondalık dilim · kategorinin risk puanı",
         "TXN_OUT_AMT_L30D → logaritması", "Çok büyük tutarların etkisini sıkıştırır, küçük farkları korur."),
        ("2. Aile içi üretim", "13 dönüşüm", "Aynı ölçünün farklı dönemleri birbiriyle karşılaştırılır.",
         "Kısa dönem bölü uzun dönem · önceki döneme göre büyüme · eğilim · düzensizlik · en yoğun dönemin payı",
         "TXN_OUT_AMT_L30D bölü TXN_OUT_AMT_L90D",
         "Son 30 günün son 90 güne oranı: harcama hızlanıyor mu, yavaşlıyor mu."),
        ("3. Aileler arası üretim", "10 dönüşüm", "Birbiriyle anlamlı ilişkisi olan farklı kolonlar birleştirilir.",
         "Net akış · işlem başına ortalama tutar · alt kırılımın toplamdaki payı · tek kanala yoğunlaşma · segment "
         "içindeki yeri",
         "TXN_IN_AMT_L30D eksi TXN_OUT_AMT_L30D", "Net akış: hesaba giren mi fazla, çıkan mı."),
    ]
    aw = (12.33 - 0.6) / 3
    for i, (ad, sayi, ne_yapar, donusumler, ornek, anlam) in enumerate(asamalar):
        x = 0.5 + i * (aw + 0.3)
        s.veri(x, 1.58, aw, 0.72, ad, sayi)
        s.kutu(x, 2.42, aw, 0.78, "islem", "ne yapar %d" % i)
        s.yazi(ne_yapar, x + 0.12, 2.42, aw - 0.24, 0.78, boy=11.5, hiza="l")
        s.etiket("Dönüşümlerden örnekler", x, 3.3, aw)
        s.kutu(x, 3.58, aw, 0.95, "gri", "dönüşümler %d" % i)
        s.yazi(donusumler, x + 0.12, 3.58, aw - 0.24, 0.95, boy=11, hiza="l")
        s.etiket("Örnek (gösterim amaçlı)", x, 4.63, aw)
        s.kutu(x, 4.91, aw, 0.52, "islem", "örnek %d" % i)
        s.yazi(ornek, x + 0.06, 4.91, aw - 0.12, 0.52, boy=10.5, yazitipi="Courier New", kalin=True, renk=KIR)
        s.yazi(anlam, x, 5.47, aw, 0.42, boy=10.5, renk=GRI, hiza="l", dikey="t")
    s.kutu(0.5, 5.95, 12.33, 0.55, "gri", "hangi dönüşüm kalır")
    s.yazi([[R("Hangi dönüşüm kalır:  ", kalin=True, renk=KIR),
             "türetildiği kolonlardan belirgin biçimde daha fazla bilgi taşıyan ve onların kopyası olmayan. Ölçek "
             "dönüşümleri yalnız çarpık ya da uç değerli kolonlarda önerilir."]],
           0.7, 5.95, 11.93, 0.55, boy=11.5, hiza="l")
    s.dipnot("Kolon adları 01'de standartlaştırılan adlardır; örnekler gösterim amaçlıdır.")
    s.notlar = ("Aşama, dönüşümün neye baktığını söyler. Birinci aşama tek kolonla, ikinci aşama aynı ölçünün farklı "
                "dönemleriyle, üçüncü aşama birbiriyle ilişkili farklı kolonlarla çalışır. Kartta 41 dönüşümün her biri "
                "sade adı, ne yaptığı, bu verideki örneği ve bu veride neden kullanılabilir ya da kullanılamaz "
                "olduğuyla listelenir.")
    return s


def slayt_sirada():
    s = Slayt("AKIS", B4, "Sırada · 02.3 ile 05 Arası",
              "Bu adımların ilk sürümleri kodda var; 02.2 tamamlandıktan sonra bu yapıya göre sırayla ele alınacak.")
    s.lejant([("veri", "Veri / Çıktı"), ("soluk", "Sırada")])
    s.veri(0.5, 1.75, 1.65, 2.2, "Güncel Veri", "02.2'nin çıktısı")
    sx, sw = 2.5, 2.36
    sg = (12.83 - sx - 4 * sw) / 3
    siradakiler = [
        ("02.3 AI Değişken Keşfi", "Bilinen kalıpların dışında yeni değişken fikirleri aranır. Yapay zekâ kod yazmaz, "
                                   "yalnız denetlenen bir formül yazar; hesabı kod yapar.", "Yeni değişkenler"),
        ("03 Veri Anlama ve Hazırlama", "Her değişkenin hedefle ilişkisi ve zaman içindeki kararlılığı ölçülür. Eksik "
                                        "değerler doldurulur, set sabitlenir.", "Analitik baz set"),
        ("04 Değişken Değerlendirme", "Hedefi ele veren şüpheli değişkenler ayıklanır. Birbirinin tekrarı olan ve "
                                      "katkısı zayıf değişkenler elenir.", "Aday değişken seti"),
        ("05 Modelleme ve Finalizasyon", "Yalnız ham kolonlarla kurulan model ile yeni değişkenli model aynı "
                                         "koşullarda karşılaştırılır; algoritmalar denenir, seçilen model doğrulanır.",
         "Final model, katalog, doküman"),
    ]
    s.ok(2.15, 2.85, sx - 0.02, 2.85, "ok girdi", SOLUK)
    for i, (ad, aciklama, cikti) in enumerate(siradakiler):
        x = sx + i * (sw + sg)
        s.kutu(x, 1.75, sw, 2.2, "soluk", ad)
        s.yazi(ad, x + 0.12, 1.83, sw - 0.24, 0.6, boy=13, kalin=True, hiza="l")
        s.yazi(aciklama, x + 0.12, 2.47, sw - 0.24, 1.45, boy=11.5, hiza="l", dikey="t")
        if i < 3:
            s.ok(x + sw + 0.02, 2.85, x + sw + sg - 0.02, 2.85, "ok sıra %d" % i, SOLUK)
        s.ok(x + sw / 2, 3.97, x + sw / 2, 4.2, "ok çıktı %d" % i, SOLUK)
        s.kutu(x, 4.22, sw, 0.58, "soluk", "çıktı " + cikti)
        s.yazi(cikti, x, 4.22, sw, 0.58, boy=11.5, kalin=True, renk=GRI)
    s.yazi("Çıktı", 0.5, 4.22, 1.65, 0.58, boy=11, kalin=True, renk=GRI, hiza="r")
    s.kutu(0.5, 5.2, 12.33, 1.15, "gri", "hedef")
    gorsel_var = s.resim("robot_alt", 9.2, 5.3, 3.45, 0.95, yatay="r") is not None
    s.yazi([R("Sonunda hedeflenen", kalin=True, renk=KIR, boy=13),
            R("Yeni değişkenlerin modele katkısı ölçülmüş, her kararı izlenebilen ve belgelenmiş bir final model; "
              "yanında değişken kataloğu ve model dokümanı.", boy=12)],
           0.7, 5.2, 8.3 if gorsel_var else 11.93, 1.15, hiza="l", bosluk=3)
    s.notlar = ("Bu adımlar henüz bu yapıya göre ele alınmadı; ilk sürümleri kodda duruyor. Anlatırken hedeflenen akış "
                "olarak sunun. 02.3'te yapay zekâ serbest kod değil, yalnız izinli işlemlerden oluşan bir formül yazar; "
                "formül kodla denetlenir. 05'te yeni değişkenlerin katkısı, aynı bölme ve aynı ayarlarla kurulan iki "
                "modelin karşılaştırılmasıyla ölçülür.")
    return s


def slayt_durum():
    s = Slayt("AKIS", B4, "Akıllı Modelleme Platformu · Nerede Kaldık",
              "01 ve 02.1 geliştirildi; şu an 02.2 Geleneksel Değişken Üretimi üzerinde çalışıyoruz.")
    s.kutu(0.5, 1.58, 12.33, 2.5, "gri", "akış bandı")
    adimlar = [("01", "Çalışma Kurulumu", "g"), ("02.1", "Veri Profili ve Kalite", "g"),
               ("02.2", "Geleneksel Değişken Üretimi", "s"), ("02.3", "AI Değişken Keşfi", "r"),
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
            kayma = 0.25 if s.avatar("dusunme", cx - 0.85, 1.81, 0.5, halka=1.25) else 0
            s.yazi("Şu an buradayız", cx - 0.85 + kayma, 1.67, 1.7 - kayma, 0.28, boy=10.5, kalin=True, renk=BEYAZ)
    kw = (12.33 - 0.5) / 3
    s.kart(0.5, 4.32, kw, 2.0, "gri", "Geliştirilen",
           ["01 Çalışma Kurulumu: veri seti ve sözlük, kolon rolleri, eksik tanımlar, sözlük ve kolon adı kontrolü, "
            "bölme",
            "02.1 Veri Profili ve Kalite: 26 kontrol, düzeltme ve çözüm önerileri"], baslik_boy=14, boy=11.5)
    s.kart(0.5 + kw + 0.25, 4.32, kw, 2.0, "simdi", "Üzerinde çalışılan",
           ["02.2 Geleneksel Değişken Üretimi: yapay zekâ dönüşüm seçer, kod katkısını ölçer, kullanıcı kart ve "
            "sohbetle karar verir",
            "Açık konular: üretilen değişken sayısı ve yeni bilgi eşiği; kart ve sohbet geri bildirimle güncelleniyor"],
           baslik_boy=14, boy=11.5)
    s.kart(0.5 + 2 * (kw + 0.25), 4.32, kw, 2.0, "soluk", "Sırada",
           ["02.3 AI Değişken Keşfi",
            "03 Veri Anlama, 04 Değişken Değerlendirme, 05 Modelleme: ilk sürümleri kodda var, bu yapıya göre ele "
            "alınacak"], baslik_boy=14, boy=11.5)
    s.notlar = ("Kapanış slaytı. Akış beş fazdan oluşuyor; 01 ve 02.1 geliştirildi, şu an 02.2 üzerinde çalışıyoruz. "
                "02.3 ve sonrasının ilk sürümleri kodda var ama bu yapıya göre henüz ele alınmadı.")
    return s


# ===========================================================================
# URETIM VE KAYIT
# ===========================================================================
def uret(zaman=None):
    """Sunumun .pptx icerigini bayt olarak doner. Gorseller her cagrida yeniden okunur."""
    gorselleri_sifirla()
    slaytlar = [slayt_kapak(), slayt_neden(), slayt_nedir(), slayt_akis(), slayt_adim(), slayt_veri_kurali(),
                slayt_kurulum(), slayt_sozluk(), slayt_kalite(), slayt_uretim(), slayt_asamalar(), slayt_sirada(),
                slayt_durum()]
    if KAPANIS:
        slaytlar.append(slayt_kapanis())
    return paketle(slaytlar, "Akıllı Modelleme Platformu", zaman)


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
