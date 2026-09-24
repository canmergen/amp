# -*- coding: utf-8 -*-
"""fe_agent/niyet_kural.py — kullanicinin cumlesini LLM'siz cozumler.

Tek isi: bir metinden su ikisini cikarmak
  aksiyon : onay / ret / adim_tekrar / alan_ver / belirsiz
  alanlar : {"veri_seti": "HAVALE_EFT_NTT", "sozluk": "DEGISKENLER"}
"""

import re

# Turkce karakterler 1'e 1 ASCII'ye cevriliyor; metin uzunlugu DEGISMIYOR.
# Bu sayede normalize metinde bulunan konumu ORIJINAL metne uygulayip
# dataset adini buyuk harfleri bozmadan kesebiliyoruz.
_TR_MAP = str.maketrans("ıİşŞğĞüÜöÖçÇ", "iisSgGuUoOcC")


def normalize(metin):
    if not metin:
        return ""
    return metin.translate(_TR_MAP).lower()


# SIRA ONEMLI: ret once kontrol edilir.
#
# Olumsuzluk ekleri (-mi/-ma/-maz/-miyorum) ile niyet eki (-mak istiyorum)
# AYRI ele alinir: "onaylamiyorum" ret, "onaylamak istiyorum" onaydir.
# Gecmiste `\bonaylam\w*` ikisini de ret sayiyordu.
RET_KALIPLARI = [
    # onayla- + olumsuzluk. DIKKAT: "onaylamak" (niyet eki) ve "onaylamadan"
    # (zarf-fiil) buraya GIRMEMELI; ikisi de ret degildir.
    r"\bonaylam(?:iyor|ayacak|ayalim|adim|adik|az)\w*",
    r"\bonaylama\b",
    r"\bonaylanmas(?:in|in)\w*",
    r"\bkabul etmiyor\w*", r"\bkabul etmem\b", r"\bkabul edilmez\b",
    r"\bhayir\b", r"\bolmaz\b", r"\bred\b", r"\breddediyor\w*",
    r"\breddet\w*", r"\bvazgec\w*", r"\bistemiyor\w*", r"\bistemem\b",
    r"\bbosver\w*", r"\bgerek yok\b", r"\bgerekmiyor\b",
    r"\bdurdur\w*", r"\bdurduralim\b",
    r"\bdevam etme(?:yelim|sin)?\b", r"\bdevam etmiyor\w*",
    r"\bgecmeyelim\b", r"\byapmayalim\b", r"\byapma\b",
    # Webapp butonunun ETIKETI "Degistir" (mesaji "hayir"). Kullanici ayni
    # kelimeyi YAZDIGINDA da ayni sey olmali; eskiden LLM'e dusuyordu.
    r"\bdegistir\w*\b", r"\bduzelt\w*\b", r"\bbaska\s+bir\b",
    # "iptal" ancak bir eylemle birlikteyken rettir:
    # "iptal edilen kartlar" bir FILTRE tarifidir, ret degil.
    r"\biptal (?:edelim|edin|ediyorum|ediyoruz|et|edebilir)\b",
    r"\biptal olsun\b",
]

# Uzun cumlede de guvenilen, niyeti acik onay kaliplari.
KESIN_ONAY_KALIPLARI = [
    r"\bonayliyor\w*", r"\bonaylad(?:im|ik)\b", r"\bonaylayalim\b",
    r"\bonayla(?:mak|mayi|maya)\s+istiyor\w*",
    # Emir kipi: kullanicinin en dogal yazimi ve webapp butonunun metni.
    # DIKKAT: olumsuzluk ekleri RET_KALIPLARI'nda once kontrol edildigi icin
    # "onaylama" / "onaylamayalim" buraya DUSMEZ.
    r"\bonayla\b", r"\bonaylay(?:in|iniz)\b", r"\bonaylansin\b",
    r"\bonayla ve uygula\b", r"\buygulayalim\b", r"\buygulayabilirsin\b",
    r"\bonay (?:veriyorum|verdim)\b", r"\bonaylandi\b",
    r"\bkabul (?:ediyorum|edelim|ediyoruz|ettim)\b",
    r"\bdevam (?:edelim|ediyoruz|edebiliriz|edebilirsin|et)\b",
    r"\bbaslayalim\b", r"\bbaslayabilirsin\b", r"\bbaslat\b",
    r"\bgecelim\b", r"\bgecebiliriz\b", r"\btamamdir\b", r"\bhaydi\b",
]

# Yalnizca KISA yanitlarda guvenilen kelimeler. "devam eden kredileri
# filtrele" gibi cumlelerde bunlar bagimsiz gecer; onay sayilmamali. Bu
# yuzden kisa mesajin TUM kelimeleri onay ya da nezaket kelimesi olmali.
ZAYIF_ONAY_KELIMELER = {
    "onay", "tamam", "tamamdir", "evet", "olur", "devam", "kabul", "uygun",
    "basla", "baslayalim", "ok", "okey", "peki", "tabii", "tabi", "elbette",
    "kabulum", "super", "harika", "gecelim", "edelim", "onaylandi",
}

# Kisa onay yanitinda bulunmasi dogal, anlami degistirmeyen kelimeler.
ONAY_YARDIMCI_KELIMELER = {
    "lutfen", "hadi", "haydi", "o", "zaman", "bu", "adim", "adimi", "sen",
    "ben", "biz", "de", "da", "ve", "artik", "simdi", "bence", "olsun",
    "et", "edebilirsin", "gecebiliriz", "tamamen",
}

TEKRAR_KALIPLARI = [
    r"\btekrar\w*", r"\byeniden\b", r"\bbastan\b", r"\bgeri don\w*",
    r"\bbasa don\w*",
]

# Soru cumlesi: kullanici onay VERMIYOR, soru soruyor. Onay adimi dogrudan
# is yaptigi (dataset yazma, senaryo tetikleme) icin soru varsa onay verilmez.
SORU_KALIPLARI = [
    r"\?", r"\bmi\b", r"\bmu\b", r"\bmiyiz\b", r"\bmuyuz\b", r"\bmisin\b",
    r"\bmiyim\b", r"\bneden\b", r"\bnicin\b", r"\bnasil\b", r"\bnedir\b",
    r"\bne zaman\b", r"\bhangi\b", r"\bkac\b", r"\bnerede\b", r"\bkim\b",
    r"\bsoru\w*", r"\bmerak\b", r"\bacaba\b", r"\banlat\w*", r"\bacikla\w*",
    r"\bogrenebilir\w*", r"\bsormak\b", r"\bsorabilir\w*",
]

# Yalnizca kisa mesajda ret sayilan kaliplar. "iptal" tek basina rettir ama
# "iptal edilen kartlar" bir filtre tarifidir.
KISA_RET_KALIPLARI = [
    r"\biptal\b", r"\bgerek yok\b", r"\bbosuna\b",
]

# Kisa yanit siniri (kelime sayisi). Bu sinirin altinda zayif kelimelere de
# guveniyoruz; ustunde temkinli davranip "belirsiz" donuyoruz.
KISA_MESAJ_SINIRI = 4

# Cumleden dataset/sozluk adi cikaran kaliplar. Grup 1 = yakalanacak deger.
# Nokta ve tire de yakalanir: backend adlari PROJE.DATASET biciminde donuyor.
_DEGER = r"([a-z0-9_.\-]+)"
ALAN_KALIPLARI = {
    "veri_seti": [
        r"veri\s*seti\s*[:=]?\s*" + _DEGER,
        r"\bdataset\s*[:=]?\s*" + _DEGER,
        r"\btablo\s*[:=]?\s*" + _DEGER,
    ],
    "sozluk": [
        r"sozluk\s*[:=]?\s*" + _DEGER,
        r"\bsozlugu\s*[:=]?\s*" + _DEGER,
    ],
}

# "sozluk olarak DEGISKENLER" gibi cumlelerde regex "olarak"i yakalayabiliyor.
# Bu kelimeler deger olarak kabul edilmez; bir sonraki kelimeye bakilir.
DOLGU_KELIMELER = {
    "ve", "ile", "olarak", "icin", "da", "de", "ki", "bir",
    "adinda", "adli", "ismi", "isim", "adi", "ad", "ismiyle", "adiyla",
    "su", "bu", "o", "var", "yok", "olsun", "olmali", "olacak",
    "kolonu", "kolon", "seti", "set", "sozluk", "sozlugu", "tablo",
    "dataset", "veri", "aciklama", "bana", "bize", "sana",
    "cok", "az", "biraz", "fazla", "buyuk", "kucuk", "uzun", "kisa",
    "bos", "dolu", "yeni", "eski", "hazir", "dogru", "yanlis",
    "ne", "nedir", "hangi", "kac", "neden", "nasil", "kim", "hic",
    "her", "tum", "tum", "gibi", "kadar", "daha", "en", "ayni", "baska",
    "lazim", "gerek", "mi", "mu", "mantikli", "guzel", "iyi", "kotu",
}

# Deger adayi olabilecek belirtec (noktali/tireli adlar dahil)
_BELIRTEC = re.compile(r"[a-z0-9_.\-]+")

# Deger ile bir sonraki belirtec arasinda yalnizca bunlar olabilir; virgul
# ya da baska noktalama varsa cumle degismistir, atlamayi durdururuz.
_ARA_BOSLUK = re.compile(r"[ \t:=]*")

# Bir dolgu kelimeden sonra en fazla bu kadar kelime ileri bakilir.
# 1 bilincli: "tablo bana mantikli geldi" cumlesinde ucuncu kelimeyi
# dataset adi sanmayalim.
_ATLAMA_SINIRI = 1


def _herhangi_esles(norm, kaliplar):
    for k in kaliplar:
        if re.search(k, norm):
            return True
    return False


def _aday_deger(orijinal, bas, son, gecerli_adlar):
    """Konumdaki adayi temizler ve kabul edilebilir mi diye bakar."""
    deger = orijinal[bas:son].strip()          # ORIJINAL metninden kesiyoruz
    deger = deger.strip(".,;:-_")              # cumle sonu noktasi vb.
    if not deger or len(deger) < 2:
        return None
    if normalize(deger) in DOLGU_KELIMELER:
        return None
    if gecerli_adlar:
        harita = {str(a).upper(): a for a in gecerli_adlar}
        kanonik = harita.get(deger.upper())
        if kanonik is None:
            return None
        return kanonik
    return deger


def _alan_bul(orijinal, norm, kaliplar, gecerli_adlar=None):
    """Kalibin TUM eslesmelerini dener.

    Eskiden ilk eslesmede yakalanan deger dolgu kelime cikinca `continue`
    bir sonraki KALIBA geciyordu ve alan tamamen kayboluyordu. Simdi ayni
    kalibin sonraki eslesmesine, oradan da dolgu kelimenin ardindaki
    kelimeye bakiliyor ("veri seti olarak HAVALE_EFT_NTT").
    """
    for k in kaliplar:
        for m in re.finditer(k, norm):
            bas, son = m.span(1)
            deger = _aday_deger(orijinal, bas, son, gecerli_adlar)
            if deger:
                return deger
            # Yakalanan deger dolgu kelimeydi: hemen ardindaki kelimelere bak.
            imlec = son
            for _ in range(_ATLAMA_SINIRI):
                t = _BELIRTEC.search(norm, imlec)
                if not t:
                    break
                if not _ARA_BOSLUK.fullmatch(norm[imlec:t.start()]):
                    break          # araya virgul/noktalama girdi, vazgec
                deger = _aday_deger(orijinal, t.start(), t.end(), gecerli_adlar)
                if deger:
                    return deger
                imlec = t.end()
    return None


def alanlari_cikar(metin, gecerli_adlar=None):
    """Mesajdan veri_seti / sozluk adlarini cikarir.

    gecerli_adlar verilirse (kume), yakalanan deger o kumede yoksa
    dondurulmez; bulunursa kumedeki kanonik yazim dondurulur.
    """
    orijinal = metin or ""
    norm = normalize(orijinal)
    alanlar = {}
    for alan_adi, kaliplar in ALAN_KALIPLARI.items():
        deger = _alan_bul(orijinal, norm, kaliplar, gecerli_adlar)
        if deger:
            alanlar[alan_adi] = deger
    return alanlar


def _kelimeler(norm):
    return [p for p in re.split(r"[^a-z0-9_]+", norm) if p]


def _kisa_onay(kelimeler):
    """Kisa yanit bastan sona onay mi?

    En az bir onay kelimesi olmali ve TUM kelimeler onay/nezaket kelimesi
    olmali. Boylece "devam eden kredileri filtrele" onay sayilmaz.
    """
    if not kelimeler:
        return False
    if not any(k in ZAYIF_ONAY_KELIMELER for k in kelimeler):
        return False
    return all(k in ZAYIF_ONAY_KELIMELER or k in ONAY_YARDIMCI_KELIMELER
               for k in kelimeler)


def coz(metin, gecerli_adlar=None):
    """Ana fonksiyon.
    Doner: {"aksiyon": "...", "alanlar": {...}, "ham": "..."}

    Kural: emin degilsen "belirsiz" don. Yanlis "onay" pahalidir; cagiran
    onay gelince adimi DOGRUDAN calistiriyor (dataset yazma, senaryo
    tetikleme).
    """
    orijinal = metin or ""
    norm = normalize(orijinal)
    alanlar = alanlari_cikar(orijinal, gecerli_adlar)
    sonuc = {"alanlar": alanlar, "ham": orijinal}

    kelimeler = _kelimeler(norm)
    kisa = len(kelimeler) <= KISA_MESAJ_SINIRI
    soru = _herhangi_esles(norm, SORU_KALIPLARI)

    if _herhangi_esles(norm, RET_KALIPLARI):
        sonuc["aksiyon"] = "ret"
    elif kisa and _herhangi_esles(norm, KISA_RET_KALIPLARI):
        sonuc["aksiyon"] = "ret"
    elif _herhangi_esles(norm, TEKRAR_KALIPLARI):
        sonuc["aksiyon"] = "adim_tekrar"
    elif soru:
        # Soru soran cumle onay degildir; alan verdiyse onu alalim.
        sonuc["aksiyon"] = "alan_ver" if alanlar else "belirsiz"
    elif _herhangi_esles(norm, KESIN_ONAY_KALIPLARI):
        sonuc["aksiyon"] = "onay"
    elif kisa and _kisa_onay(kelimeler):
        sonuc["aksiyon"] = "onay"
    elif alanlar:
        sonuc["aksiyon"] = "alan_ver"
    else:
        sonuc["aksiyon"] = "belirsiz"

    return sonuc
