# -*- coding: utf-8 -*-
"""fe_agent/akis_sohbet.py - Mesaj yonlendirme, adim gecisleri ve serbest soru.

akis.py bolundu; bu dosya o bolumun aynisidir.
"""

import copy
import inspect
import json
from fe_agent import niyet_kural
from fe_agent import validasyon
from fe_agent import llm as llm_mod

from fe_agent.akis_metin import (
    GERI_KALIP, MOD_ADLARI, MOD_KALIP, PLATFORM_TANIMLARI,
    SORU_KALIP,
)
from fe_agent import akis_durum
from fe_agent.akis_durum import AdimHatasi, _secim_ayikla
from fe_agent.akis_kayit import ADIMLAR, SECIMLI, adim_sirasi
from fe_agent.akis_panel import ozet


# Akis bittiginde bekleyen bu degere cekilir: webapp bunu gorunce
# onay/degistir butonlarini gizler, son adim ikinci kez calismaz.
BITTI = "bitti"

# Validasyon sonucunun ait oldugu adim; bundan ONCEKI bir adima
# donuldugunde eski sonuc gecersizdir.
FINAL_ADIMI = "final"


# ===========================================================================
# YARDIMCILAR
# ===========================================================================
def _yeniden_sor_destekli(fn):
    """Girdi fonksiyonu yeni `yeniden_sor` parametresini taniyor mu?"""
    try:
        return "yeniden_sor" in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False


def _girdi_cagir(adim, durum, mesaj, yeniden_sor=False):
    """adim["girdi"](durum, mesaj[, yeniden_sor]) cagrisi.

    `yeniden_sor` akis_faz01'e sonradan eklendi: True verilince adim
    mevcut degerlerle DOLU formu acar ve False doner. Imzasinda henuz
    yoksa eski bicimde cagrilir; cagiran taraf yine de girdi bekler."""
    fn = adim["girdi"]
    if yeniden_sor and _yeniden_sor_destekli(fn):
        return fn(durum, mesaj, yeniden_sor=True)
    return fn(durum, mesaj)


def _uygula(adim, durum, secimli=False, secim=None):
    """Adimi calistirir.

    ONBELLEK TOPTAN BOSALTILMIYOR (kullanici sikayeti: "veri seti ve
    değişken sözlüğü 1.30 dk'dan fazladır çalışmadı").

    Eskiden her `uygula` adimindan sonra veri onbellegi KOMPLE
    bosaltiliyordu; gerekcesi "uygula adimlari veri setini degistirir"
    idi. Ama adimlarin cogu veri setine hic dokunmuyor ve DOKUNANLAR
    zaten kendi iptalini yapiyor:
      - akis_durum._yaz()          -> onbellek_temizle(dataset_adi)
      - akis_faz03 dogrudan yazma  -> onbellek_temizle(hedef)
      - mod degisikligi / birlestirme -> onbellek_temizle()
    Toptan bosaltma bu hedefli iptallerin uzerine biniyordu ve tek
    etkisi, bir sonraki adimin 1.042 kolonluk tabloyu BASTAN okumasiydi.
    Gercek bir Dataiku tablosunda bu adim basina onlarca saniye."""
    return adim["uygula"](durum, secim) if secimli else adim["uygula"](durum)


def _validasyonu_tazele(durum, sira):
    """Final adimindan ONCEKI bir adima donulduyse eski validasyon
    sonucu artik gecerli degildir; ekranda kalmasin."""
    if FINAL_ADIMI not in sira:
        return
    if durum["i"] < sira.index(FINAL_ADIMI):
        validasyon.temizle(durum)


# ===========================================================================
# ANA DONGU
# ===========================================================================
def ilk_soru(durum):
    """Karsilama ile birlikte gosterilecek ilk adim sorusu."""
    return _adima_gir(durum)

def _bos_metin_yedegi(durum, yedek):
    """Adim metin dondurmediyse ne yazilacak.

    Bir adim BILEREK bos metin donebilir: ekranda zaten kendini anlatan
    bir form ya da secenek karti varsa, ustune bir de balon basmak ayni
    cumleyi iki kere yazmak olur ve kullanici henuz bir sey soylememisken
    asistan cevap veriyormus gibi gorunur. O durumda bos metin DOGRU
    cevaptir; akis ayni sohbette kesintisiz devam eder.

    Ama ekranda hicbir sey yoksa bos metin kullaniciyi bos ekranla basbasa
    birakirdi; yedek cumle yalnizca o durum icin var."""
    if durum.get("_secim_alani") or durum.get("_secenekler"):
        return ""
    return yedek


def _adima_gir(durum, yeniden_sor=False):
    """Yeni adima girilirken: girdi gerekiyorsa formu/secenekleri ac,
    gerekmiyorsa ya da bilgi zaten tamamsa plani goster.

    yeniden_sor=True: kullanici bu adima DEGISTIRMEK icin geldi (geri
    donus ya da "Degistir"). Bilgi durumda tam olsa bile form yeniden
    acilir; aksi halde kullanici onaydan baska cikis bulamiyordu."""
    sira = adim_sirasi(durum.get("mod"))
    adim = ADIMLAR[sira[durum["i"]]]

    if adim.get("girdi") is not None:
        tamam, soru = _girdi_cagir(adim, durum, "", yeniden_sor)
        if not tamam:
            durum["bekleyen"] = "girdi"
            return soru or _bos_metin_yedegi(
                durum, "Devam etmek için seçim yapmanız gerekiyor.")
        # FORMUN KENDISI ONAYDIR. plan=None olan adimda ayri bir "Doğru mu?"
        # asamasi YOK: kullanici formu doldurup onay dugmesine bastiginda
        # zaten onaylamistir. Iki asamali onay, ayni karari iki kez
        # sordurmaktan baska bir sey yapmiyordu ve ozetledigi bilgi sag
        # panelde zaten duruyor.
        # (girdi=None + plan=var olan adimlar bu daldan GECMEZ; onlar
        #  eskisi gibi plan gosterip onay bekler.)
        if not yeniden_sor and adim.get("plan") is None:
            return _onayi_uygula(durum, adim, sira[durum["i"]])
        if yeniden_sor:
            # Girdi fonksiyonu `yeniden_sor`u henuz tanimiyor: bilgi tam
            # oldugu icin True dondu. Yine de girdi bekliyoruz ki
            # kullanici degeri degistirebilsin.
            durum["bekleyen"] = "girdi"
            return soru or _bos_metin_yedegi(
                durum, "Mevcut bilgiyi değiştirmek için yeni değerleri "
                       "yazabilirsiniz.")
        # Girdi fonksiyonu gerekli bilgiyi durumda buldu: dogrudan plana gec

    durum["bekleyen"] = "onay"
    return adim["plan"](durum)

def _adet(durum, anahtar):
    return len(durum.get("plan" if anahtar == "kural" else "hipotez") or [])

def _soru_mu(mesaj, norm):
    """Acikca soru olan mesajlar: adim girdisi denenmeden LLM'e gider."""
    if len(norm) < 3 or MOD_KALIP.match(mesaj):
        return False
    return mesaj.endswith("?") or bool(SORU_KALIP.search(norm))

def _ekran_durumu(durum, anahtar, adim):
    """Kullanicinin su an ekranda gordugu soru ve secenekler.
    Girdi fonksiyonu durumu degistirebildigi icin KOPYA uzerinde calisir."""
    satirlar = ["Şu anki adım: %s" % adim.get("baslik", anahtar)]
    if adim.get("aciklama"):
        satirlar.append("Adımın amacı: " + adim["aciklama"])

    if durum.get("bekleyen") == "girdi" and adim.get("girdi"):
        kopya = copy.deepcopy(durum)
        try:
            _, istem = _girdi_cagir(adim, kopya, "")
        except Exception:
            istem = None
        if istem:
            satirlar.append("Ekrandaki soru: " + istem)

        secenekler = kopya.get("_secenekler") or durum.get("_secenekler") or []
        if secenekler:
            satirlar.append("Ekrandaki seçenekler:")
            for s in secenekler:
                satirlar.append("  %s) %s: %s" % (
                    s.get("deger"), s.get("baslik"), s.get("aciklama", "")))

        alan = kopya.get("_secim_alani") or durum.get("_secim_alani")
        if alan:
            satirlar.append("Ekrandaki form: %s. %s" % (
                alan.get("baslik", ""), alan.get("aciklama", "")))
    elif durum.get("bekleyen") == BITTI:
        satirlar.append("Çalışma tamamlandı; ekranda yeni bir aksiyon yok.")
    else:
        satirlar.append("Ekranda bir öneri var; kullanıcı onaylayabilir, "
                        "değiştirebilir veya geri dönebilir.")

    mod = durum.get("mod")
    if mod in MOD_ADLARI:
        satirlar.append("Seçilen çalışma başlangıcı: %s, %s"
                        % (mod, MOD_ADLARI[mod]))
    return "\n".join(satirlar)

def _soru_baglami(durum, anahtar, adim):
    parcalar = [
        "EKRAN DURUMU\n" + _ekran_durumu(durum, anahtar, adim),
        "TANIMLAR\n" + PLATFORM_TANIMLARI,
    ]
    try:
        parcalar.append("OTURUM ÖZETİ\n" + json.dumps(
            ozet(durum), ensure_ascii=False, default=str)[:1500])
    except Exception:
        pass
    return "\n\n".join(parcalar)

def _soru_isle(durum, mesaj, anahtar, adim):
    """Soruyu LLM'e yanitlatir. Akis ILERLEMEZ ve cevaba hicbir sey
    EKLENMEZ: onceki secenek kartlari ya da form ekranda aktif kalir,
    kullanici oradan devam eder."""
    gecmis = durum.get("_soru_gecmis") or []
    cevap, hata = llm_mod.soru_cevapla(
        mesaj, _soru_baglami(durum, anahtar, adim), gecmis)

    if cevap is None:
        return ("Sorunuzu şu an yanıtlayamadım (dil modeline ulaşılamadı: "
                "%s)." % hata)

    gecmis.append([mesaj, cevap])       # JSON'a yazilacagi icin liste
    durum["_soru_gecmis"] = gecmis[-5:]
    return cevap

def _soru_turu(durum, mesaj, anahtar, adim, secenekler, alan):
    """Serbest soru turu: cevabi doner ve EKRANI korur.

    Cevapla birlikte onceki secenek kartlari / form YENIDEN gonderilir.
    Aksi halde kartlar cevabin yukarisinda kalip (tiklanmissa) kilitli
    kaliyor ve kullanicinin secim yapacak alani kalmiyordu."""
    cevap = _soru_isle(durum, mesaj, anahtar, adim)
    durum["_secenekler"] = secenekler or []
    durum["_secim_alani"] = alan
    return cevap

def adim_anahtari(durum):
    """Durumun SU ANKI adim anahtari ("kurulum", "teyit", ...).

    On yuz her blogu hangi adimin urettigini bilmek zorunda: blogun sag
    ustundeki "Geri Dön" dugmesi o adima donuyor. Sinir disina tasarsa
    (akis bitmisse) son adimi doner, None degil — dugme her zaman bir
    hedef tasimali."""
    sira = adim_sirasi(durum.get("mod"))
    if not sira:
        return None
    i = durum.get("i")
    try:
        i = int(i)
    except (TypeError, ValueError):
        i = 0
    return sira[min(max(i, 0), len(sira) - 1)]


def adim_basligi(anahtar):
    """Adim anahtarinin ekranda gorunen basligi."""
    adim = ADIMLAR.get(anahtar) or {}
    return adim.get("baslik") or ""


def _hedefe_don(durum, hedef):
    """Belirli bir adima DOGRUDAN donus (blok sag ustundeki Geri Dön).

    YALNIZCA GERIYE. Ileri atlamak, atlanan adimlarin durumu hic
    yazilmadan sonraki adimin onlara dayanmasi demek olurdu: bolme
    adimina hedef degisken secilmeden girilebilirdi. Hedef ileride ya da
    tanimsizsa None doner, cagiran taraf mesaji normal isler."""
    sira = adim_sirasi(durum.get("mod"))
    if hedef not in sira:
        return None
    yeni = sira.index(hedef)
    if yeni > int(durum.get("i") or 0):
        return None

    # EKRAN ONCE TEMIZLENIR. Bu fonksiyon _mesaj_isle'den ONCE calisiyor
    # ve her turun basindaki temizligi ATLIYORDU: onceki turun
    # `_secim_alani`/`_secenekler` degerleri durumda kaliyor, donulen
    # adim kendi kartini kurmazsa (ornegin "mod" adimi kart degil SECENEK
    # kullanir) ESKI KART yaniyla birlikte geri gonderiliyordu. Ekranda
    # basligi "Çalışma Başlangıcı" olan bir blogun icinde "Veri seti ve
    # değişken sözlüğü" formu duruyordu; ustelik kart var sayildigi icin
    # adim metni de basliksiz kaliyordu.
    durum["_secenekler"] = []
    durum["_secim_alani"] = None
    # Onceki turun yapilandirilmis karari da tasinmamali.
    durum.pop("_dogrulama_karari", None)

    durum["i"] = yeni
    _validasyonu_tazele(durum, sira)
    # yeniden_sor=True: bilgi durumda tam olsa bile form yeniden acilir.
    # Aksi halde kullanici donduğu adimda degistirecek bir sey bulamiyor,
    # adim kendini uygulayip bir sonrakine geciyordu.
    return _adima_gir(durum, yeniden_sor=True)


def mesaj_isle(durum, mesaj, dogrulama=None, hedef_adim=None):
    """Webapp'in cagirdigi TEK fonksiyon. Cevap metnini doner.

    `uygula` adimlari (dataset yazma, senaryo tetikleme) istisna
    firlatabiliyor. Backend de yakaliyor ama burada yakalayip akis
    konumunu geri almak, kullaniciyi adimin ortasinda birakmiyor.

    dogrulama: girdi dogrulama kartinin YAPILANDIRILMIS karar govdesi
    ({"haric": [...], "ekle": [...]}). Kullanici bir cumle yazmadi, bir
    form doldurdu; govde adimin `uygula` fonksiyonuna durum uzerinden
    gecer. Gelmezse adim varsayilan davranisini uygular.

    hedef_adim: sohbetteki bir blogun sag ustundeki "Geri Dön" dugmesi.
    O blogu ureten adima DOGRUDAN doner. Serbest metin "geri dön"
    yalnizca BIR adim geri gidiyor; transkriptte yukari cikip dort adim
    oncesine donmenin yolu yoktu."""
    yedek_i = durum.get("i")
    yedek_bekleyen = durum.get("bekleyen")
    # Onceki turdan kalan "tamamlandi" isareti bu tura sizmasin: arka uc
    # onu okuyup transkripte satir yaziyor, iki kez yazilmamali.
    durum.pop("_tamamlanan", None)
    try:
        if hedef_adim:
            cevap = _hedefe_don(durum, str(hedef_adim))
            if cevap is not None:
                return cevap
        return _mesaj_isle(durum, mesaj, dogrulama)
    except AdimHatasi as e:
        # ADIM KURALI. Beklenmeyen bir arıza değil, adımın kendi kapısı
        # (ör. hedef kolonunun sözlük tanımı yazılmamış). Mesaj AYNEN
        # gösterilir ve adımın ekranı yeniden kurulur, kullanıcının
        # yaptığı seçimler kaybolmasın.
        durum["i"] = yedek_i
        durum["bekleyen"] = yedek_bekleyen
        return _birlestir(str(e), _adima_gir(durum, yeniden_sor=True))
    except Exception as e:
        durum["i"] = yedek_i
        durum["bekleyen"] = yedek_bekleyen
        return ("Bu adımı tamamlarken beklenmeyen bir hata oluştu:\n\n"
                "    %s: %s\n\n"
                "Akış olduğu yerde duruyor; adımı tekrar deneyebilir, "
                "önceki adıma dönebilir ya da ne yapmak istediğinizi "
                "yazabilirsiniz." % (type(e).__name__, str(e)[:200]))

def _birlestir(*parcalar):
    """Bos olmayan parcalari bos satirla birlestirir."""
    return "\n\n".join(p.strip() for p in parcalar if p and p.strip())


def _biten_ekran(durum, anahtar, adim):
    """Biten adimin DOLU formu ve secilen secenek.

    F5'ten sonra adimin kartlari yeniden kurulamiyordu: kart govdeleri
    EKRANDA yasiyor, oturumda degil. Arka uc her turda gonderdigi kart
    govdesini transkripte de yaziyor (backend._gecmise_ekle), ama form
    govdesi GONDERILDIGI AN bostur; degerleri kullanici tarayicida
    dolduruyor. Bu fonksiyon adimin formunu MEVCUT DEGERLERLE yeniden
    uretir; arka uc o satirdaki bos formu bununla degistirir, boylece
    yeniden cizilen kartta kullanicinin secimleri durur.

    `girdi(..., yeniden_sor=True)` Geri Dön yolunun kullandigi, zaten
    calisan mekanizmadir. Kopya uzerinde calisilir; gercek durum
    degismez. Doner: (dolu_form, secilen_secenek_degeri)."""
    try:
        if adim.get("girdi") is None:
            return None, None
        kopya = copy.deepcopy(durum)
        kopya["_secim_alani"] = None
        kopya["_secenekler"] = []
        _girdi_cagir(adim, kopya, "", yeniden_sor=True)

        alan = kopya.get("_secim_alani")
        # Secenek kartli adimda (calisma baslangici) secilen kartin degeri
        # durumda adimla AYNI ADLA duruyor: durum["mod"] <- "mod" adimi.
        secili = durum.get(anahtar)
        varsa = [s.get("deger") for s in kopya.get("_secenekler") or []]
        if secili not in varsa:
            secili = None
        return alan, secili
    except Exception:
        # Ekran kaydi BILGIDIR, akisin sarti degil. Uretilemezse adim
        # yine de ilerlemeli.
        return None, None


def mevcut_ekran(durum):
    """ICINDE BULUNULAN adimin dolu formu + secilen secenek.

    Bir adim birden fazla ekran uretebiliyor (once form, sonra girdi
    dogrulama karti). Kullanici formu doldurdugunda degerler tarayicida
    kaliyor; transkriptteki form satiri bos gonderildigi haliyle
    duruyordu ve F5'ten sonra o kart bos aciliyordu. Arka uc her turda
    bunu cagirip transkriptteki formu guncelliyor, yani adimin ORTASINDA
    yenilense bile kart dolu geri geliyor."""
    anahtar = adim_anahtari(durum)
    if not anahtar:
        return None, None
    return _biten_ekran(durum, anahtar, ADIMLAR.get(anahtar, {}))


def _tamamlandi_yaz(durum, anahtar, cikti):
    """Biten adimin ozetini KENDI anahtariyla isaretler.

    Bir tur ilerlerken donen metin iki parcadir: biten adimin ozeti ve
    yeni adimin giris metni. Ikisi tek dizede birlesip EKRAN
    TRANSKRIPTINE yeni adimin anahtariyla yaziliyordu. Sonuc: F5'ten
    sonra biten adimin blogu hic olusmuyor, dolayisiyla sag ustundeki
    "Geri Dön" de kaybolup kullanici geriye donemez hale geliyordu.
    Arka uc bu isareti okuyup iki AYRI transkript satiri yaziyor."""
    dolu, secili = _biten_ekran(durum, anahtar, ADIMLAR.get(anahtar, {}))
    durum["_tamamlanan"] = {
        "adim": anahtar,
        "baslik": ADIMLAR.get(anahtar, {}).get("baslik", ""),
        "metin": (cikti or "").strip(),
        "dolu": dolu,
        "secili": secili,
    }


def _onayi_uygula(durum, adim, anahtar, secim=None):
    """Onay geldi: adimi calistir ve siradakine gec.

    Hem metin onayi hem de yapilandirilmis karar govdesi buradan gecer;
    iki yolun adim ilerletme mantigi AYNI olmali."""
    if durum.get("bekleyen") == BITTI:
        return ("Çalışma tamamlandı; son adım yeniden çalıştırılmayacak. "
                "Önceki adımlara dönerek sonuçları gözden geçirebilir "
                "ya da yeni bir çalışma başlatabilirsiniz.")
    cikti = _uygula(adim, durum, anahtar in SECIMLI, secim)
    sira = adim_sirasi(durum.get("mod"))
    if durum["i"] >= len(sira) - 1:
        durum["bekleyen"] = BITTI
        return _birlestir(cikti, "Çalışma tamamlandı.")
    durum["i"] += 1
    _tamamlandi_yaz(durum, anahtar, cikti)
    # BOS PARCALAR ATILIR. Adimlar artik bilerek "" donebiliyor (sonuc
    # zaten kartta ya da sag panelde gorunuyor); duz birlestirme o
    # durumda bos satirlardan ibaret bir balon uretiyordu.
    return _birlestir(cikti, _adima_gir(durum))


def _mesaj_isle(durum, mesaj, dogrulama=None):
    mesaj = (mesaj or "").strip()
    norm = niyet_kural.normalize(mesaj)

    # Yapilandirilmis karar govdesi her turun BASINDA tazelenir; eski bir
    # turun karari sonraki adima sizmamali.
    durum.pop("_dogrulama_karari", None)
    if isinstance(dogrulama, dict):
        durum["_dogrulama_karari"] = dogrulama

    # Ekrandaki kartlar/form: soru turunda AYNEN geri gonderilecek.
    onceki_secenekler = durum.get("_secenekler") or []
    onceki_alan = durum.get("_secim_alani")
    durum["_secenekler"] = []          # her tur basinda temizle
    durum["_secim_alani"] = None

    sira = adim_sirasi(durum.get("mod"))
    anahtar = sira[durum["i"]]
    adim = ADIMLAR[anahtar]

    # 0) Yapilandirilmis karar govdesi bir FORM GONDERIMIDIR, cumle degil.
    # Niyet cozumlemesine sokulursa ("2 kolon hariç tutuldu") hicbir onay
    # kalibina uymaz, mesaj serbest soru sanilir ve adim hic ilerlemez.
    if durum.get("_dogrulama_karari") is not None \
            and durum.get("bekleyen") == "onay":
        return _onayi_uygula(durum, adim, anahtar)

    # 1) Acik soru: geri/onay/girdi kontrollerinden ONCE LLM'e.
    if _soru_mu(mesaj, norm):
        return _soru_turu(durum, mesaj, anahtar, adim,
                          onceki_secenekler, onceki_alan)

    # 2) Geri donus: her an gecerli
    if GERI_KALIP.search(norm):
        if durum["i"] == 0:
            return "Zaten ilk adımdayız.\n\n" + _adima_gir(durum)
        durum["i"] -= 1
        sira = adim_sirasi(durum.get("mod"))
        _validasyonu_tazele(durum, sira)
        return ("\"%s\" adımına dönüyorum.\n\n"
                % ADIMLAR[sira[durum["i"]]]["baslik"]) \
            + _adima_gir(durum, yeniden_sor=True)

    sonuc = niyet_kural.coz(mesaj)

    # 3) Girdi bekleniyor
    if durum["bekleyen"] == "girdi":
        tamam, uyari = _girdi_cagir(adim, durum, mesaj)
        if not tamam:
            # Adimin bos-mesaj istemi (kopya uzerinde: durumu degistirmesin)
            _, bos_istem = _girdi_cagir(adim, copy.deepcopy(durum), "")

            if uyari == bos_istem:
                # Mesaj bu adima ait bilgi icermiyor. Ekrandaki form/kartlar
                # AYNEN yeniden gonderilir: yukaridaki kopya tiklanmissa
                # kilitli ve kullanicinin secim alani kalmiyor.
                ekran_secenekler = durum.get("_secenekler") or onceki_secenekler
                ekran_alan = durum.get("_secim_alani") or onceki_alan
                durum["_secenekler"] = ekran_secenekler
                durum["_secim_alani"] = ekran_alan
                if sonuc["aksiyon"] in ("onay", "ret"):
                    return ("Bu adımda henüz seçim yapılmadı. Seçiminizi "
                            "aşağıdaki alandan yapabilirsiniz.")
                if mesaj:
                    return _soru_turu(durum, mesaj, anahtar, adim,
                                      ekran_secenekler, ekran_alan)
            # Gercek hata (erisilemeyen tablo vb.): uyari + yeniden form
            return uyari

        # Otomatik adimlar (baslangic secimi): secim zaten karardir
        if adim.get("otomatik"):
            cikti = _uygula(adim, durum)
            sira = adim_sirasi(durum.get("mod"))   # secim degisti, sirayi tazele
            if durum["i"] >= len(sira) - 1:
                durum["bekleyen"] = BITTI
                return cikti
            durum["i"] += 1
            _tamamlandi_yaz(durum, anahtar, cikti)
            sonraki = _adima_gir(durum)
            # Cikti bos olabilir (mod secimi): bos dizeyi "\n\n" ile
            # birlestirmek balonun basina bos satir koyuyordu.
            return (cikti + "\n\n" + sonraki) if (cikti or "").strip() \
                else sonraki

        # FORMUN KENDISI ONAYDIR (plan=None). Kullanici formu doldurdu ve
        # onay dugmesine basti; ayri bir "Doğru mu?" asamasi yok.
        # _adima_gir'deki ayni kural, girdinin MESAJLA geldigi bu yolda da
        # gecerli olmali — yoksa form doldurulunca adim plan=None'a
        # carpiyor ve "beklenmeyen hata" veriyordu.
        if adim.get("plan") is None:
            return _onayi_uygula(durum, adim, anahtar)

        durum["bekleyen"] = "onay"
        return adim["plan"](durum)

    # 4) SECIMLI adimda numara vermek ONAYDIR.
    # Plan metni "bir kismini secmek icin numaralarini belirtin (ornegin
    # 1, 3, 5)" diyor; bu mesaj hicbir onay kalibiyla eslesmedigi icin
    # LLM'e dusuyor ve adim hic ilerlemiyordu.
    secim = None
    if (durum.get("bekleyen") == "onay" and anahtar in SECIMLI
            and sonuc["aksiyon"] not in ("ret", "adim_tekrar")):
        secim = _secim_ayikla(mesaj, _adet(durum, anahtar))
        if secim:
            sonuc = dict(sonuc, aksiyon="onay")

    # 5) Onay bekleniyor
    if sonuc["aksiyon"] == "onay":
        return _onayi_uygula(durum, adim, anahtar, secim)

    if sonuc["aksiyon"] == "ret":
        # Girdili adimda "Değiştir": ayni adimin formunu dolu haliyle yeniden
        # ac. bekleyen HER KOSULDA "girdi"ye cekilir; aksi halde form
        # acilmadan onay bekleniyor gorunup kullanici cikissiz kaliyordu.
        if adim.get("girdi") is not None:
            durum["bekleyen"] = "girdi"
            _, istem = _girdi_cagir(adim, durum, "", yeniden_sor=True)
            return "Seçimi güncelleyebilirsiniz.\n\n" + (
                istem or "Yeni değerleri yazabilirsiniz.")
        # Girdisi OLMAYAN adimda (plan + onay) "Değiştir": adimin plani
        # yeniden gosterilir. Eskiden "yazabilirsiniz" diyordu; ama
        # sohbet kutusu Degisken Muhendisligi'ne kadar KAPALI, yani
        # kullaniciya yapamayacagi bir sey soyleniyordu. Cikis yolu
        # blogun sag ustundeki Geri Dön ve sag paneldeki ayar ekrani.
        return _adima_gir(durum, yeniden_sor=True)

    # 6) "tekrar / yeniden / bastan": ayni adimi yeniden goster
    if sonuc["aksiyon"] == "adim_tekrar":
        return "Bu adımı yeniden gösteriyorum.\n\n" + _adima_gir(durum)

    # 7) Tanimadigimiz her mesaj serbest sorudur
    return _soru_turu(durum, mesaj, anahtar, adim,
                      onceki_secenekler, onceki_alan)
