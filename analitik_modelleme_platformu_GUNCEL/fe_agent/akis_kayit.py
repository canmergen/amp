# -*- coding: utf-8 -*-
"""fe_agent/akis_kayit.py - Adim kayit defteri ve faz agaci.

akis.py bolundu; bu dosya o bolumun aynisidir.
"""

from fe_agent.akis_metin import (
    ADIM_ADI, FAZ01_OZET, GRUP_ADI_VERI_SOZLUK, SONRAKI_FAZLAR)
from fe_agent.akis_faz01 import (
    birlestirme_plan, birlestirme_uygula, bolme_girdi, bolme_uygula,
    ham_veri_girdi, ham_veri_plan, ham_veri_uygula, kurulum_girdi,
    kurulum_uygula, mod_girdi, mod_plan, mod_uygula,
    sozluk_tanim_plan, sozluk_tanim_uygula,
    sozluk_uret_plan, sozluk_uret_uygula, tanimlar_girdi,
    tanimlar_uygula, teyit_girdi, teyit_uygula, veri_sec_girdi,
    veri_sec_plan, veri_sec_uygula,
)
from fe_agent.akis_faz02 import (
    baz_plan, baz_uygula, sfa_plan, sfa_uygula, stabilite_plan,
    stabilite_uygula, veri_profili_plan, veri_profili_uygula,
)
from fe_agent.akis_faz03 import kesif_plan, kesif_uygula, kural_plan, kural_uygula
from fe_agent.akis_faz04 import kalite_plan, kalite_uygula, secim_plan, secim_uygula
from fe_agent.akis_faz05 import (
    algoritma_plan, algoritma_uygula, final_plan, final_uygula,
    katalog_plan, katalog_uygula, model_plan, model_uygula,
)


# ===========================================================================
# ADIM KAYIT DEFTERI
# ===========================================================================
ADIMLAR = {
    "mod": {
        # Ad TEK KAYNAKTAN (akis_metin.ADIM_ADI): sol panel, sohbet
        # blogu ve kart basligi ayni ifadeyi kullanmali.
        "baslik": ADIM_ADI["mod"],
        "aciklama": "Veri setinin ve değişken sözlüğünün hazır olup "
                    "olmadığına göre başlangıç belirlenir. Sonraki adımlar "
                    "bu seçime göre şekillenir.",
        "otomatik": True,      # secim yapilinca ayrica onay beklemez
        # NOT: "plan" burada BILEREK duruyor ama pratikte CAGRILMIYOR.
        # mod_girdi bos mesajla asla True donmedigi icin _adima_gir plana
        # ulasamiyor; secim yapilinca da "otomatik" bayragi dogrudan
        # uygula'ya gidiyor. Kayit, her adimin plan alani tasidigi
        # varsayimini bozmamak icin birakildi (mod_plan zaten mod_uygula
        # ozetini donuyor, yani yanlislikla cagrilirsa da dogru metni verir).
        "girdi": mod_girdi, "plan": mod_plan, "uygula": mod_uygula},

    "ham_veri": {
        "baslik": "Ham Tablolar",
        "aciklama": "Birleştirilecek ham tablolar seçilir; boyutları ve "
                    "kolon sayıları çıkarılır.",
        "girdi": ham_veri_girdi, "plan": ham_veri_plan, "uygula": ham_veri_uygula},
    "birlestirme": {
        "baslik": "Birleştirme Planı",
        "aciklama": "Yapay zekâ iskelet tabloyu, bağlantı anahtarlarını ve "
                    "işlem tablolarından üretilecek zaman pencereli "
                    "toplamaları önerir. Point-in-time kuralı uygulanır.",
        "girdi": None, "plan": birlestirme_plan, "uygula": birlestirme_uygula},

    "veri_sec": {
        "baslik": "Veri Seti",
        "aciklama": "Analiz edilecek veri seti seçilir; boyut ve tip "
                    "dağılımı çıkarılır.",
        "girdi": veri_sec_girdi, "plan": veri_sec_plan, "uygula": veri_sec_uygula},

    "sozluk_uret": {
        "baslik": "Sözlük Üretimi",
        "aciklama": "Her kolonun tipi, dağılımı ve örnek değerleri "
                    "incelenir; yapay zekâ ne anlama geldiğini yazar. "
                    "Kimlik benzeri kolonların örnekleri paylaşılmaz.",
        "girdi": None, "plan": sozluk_uret_plan, "uygula": sozluk_uret_uygula},

    "kurulum": {
        "baslik": "Veri Seti ve Değişken Sözlüğü",
        "aciklama": "Analiz edilecek veri seti ve değişken sözlüğü "
                    "seçilir; kapsam oranı hesaplanır.",
        # plan=None: FORMUN KENDISI ONAYDIR. Tanimsiz kolon karari artik
        # bu adimda DEGIL, "sozluk_tanim" adiminda ve modelleme
        # tanimlarindan SONRA veriliyor (hedef/kimlik/donem kolonunun
        # tanimi zorunlu, hangileri oldugu once bilinmeli).
        "girdi": kurulum_girdi, "plan": None, "uygula": kurulum_uygula},

    "sozluk_tanim": {
        "baslik": "Sözlük Tanımları",
        "aciklama": "Sözlükte tanımı bulunmayan kolonlar için açıklama "
                    "yazılır ya da kolonlar süreç dışına alınır. Hedef, "
                    "kimlik ve dönem kolonunun tanımı zorunludur.",
        "girdi": None, "plan": sozluk_tanim_plan,
        "uygula": sozluk_tanim_uygula},

    "tanimlar": {
        "baslik": "Modelleme Tanımları",
        "aciklama": "Hedef değişken, kimlik kolonu ve dönem kolonu "
                    "belirlenir; hedefin tipi ve dağılımı çıkarılır.",
        # plan=None: FORMUN KENDISI ONAYDIR. Ayri bir "Doğru mu?" ozeti
        # yok — form doldurulup onaylandiginda karar verilmistir ve o uc
        # satir sag paneldeki Veri seti kartinda zaten duruyor.
        "girdi": tanimlar_girdi, "plan": None, "uygula": tanimlar_uygula},

    "teyit": {
        "baslik": ADIM_ADI["teyit"],
        "aciklama": "Değişken listesi ve sözlük tanımları bölme öncesinde "
                    "son kez gözden geçirilir.",
        # plan=None: FORMUN KENDISI ONAYDIR. Kart "son kez gözden geçirin"
        # diyor ve tek dugmesi var; ayri bir "Doğru mu?" asamasi ayni
        # onayi ikinci kez sormak olurdu.
        "girdi": teyit_girdi, "plan": None, "uygula": teyit_uygula},

    "bolme": {
        "baslik": ADIM_ADI["bolme"],
        "aciklama": "Veri setinin eğitim, doğrulama ve test kullanım "
                    "planı belirlenir. Bu sınır sızıntı sınırıdır: "
                    "doldurma, dönüşüm ve eğitim yalnızca geliştirme "
                    "setinden hesaplanır.",
        # plan=None: KARTIN KENDISI ONAYDIR. Kart iki mod tasiyor
        # (Önerilen Ayarlar / Özel Ayarlar) ve tek dugmesi var; ayri bir
        # "Doğru mu?" asamasi ayni onayi ikinci kez sormak olurdu.
        "girdi": bolme_girdi, "plan": None, "uygula": bolme_uygula},

    "veri_profili": {
        "baslik": "Veri Profili ve Kalite",
        "aciklama": "Dataset seviyesinde inceleme: eksik değer, tekil sayısı, "
                    "kardinalite, sabit ve kimlik benzeri kolonlar.",
        "girdi": None, "plan": veri_profili_plan, "uygula": veri_profili_uygula},
    "sfa": {
        "baslik": "Tek Değişken Analizi (SFA)",
        "aciklama": "Her değişkenin hedefle tek başına ilişkisi ölçülür: "
                    "IV ve C-value. Eleme kuralı değildir.",
        "girdi": None, "plan": sfa_plan, "uygula": sfa_uygula},
    "stabilite": {
        "baslik": "Stabilite Analizi (PSI)",
        "aciklama": "Değişken dağılımlarının zaman içinde kayıp kaymadığı "
                    "ölçülür. Zamansal bölme gerektirir.",
        "girdi": None, "plan": stabilite_plan, "uygula": stabilite_uygula},
    "baz": {
        "baslik": "Analitik Baz Set",
        "aciklama": "Kusurlu kolonlar düşürülür, eksik değerler geliştirme "
                    "setinin istatistikleriyle doldurulur ve set dondurulur.",
        "girdi": None, "plan": baz_plan, "uygula": baz_uygula},

    "kural": {
        "baslik": "Kural Tabanlı Değişken Üretimi",
        "aciklama": "Yapay zekâ hangi aileye fark, oran, log, sıralama veya "
                    "budama uygulanacağını önerir; Python üretir.",
        "girdi": None, "plan": kural_plan, "uygula": kural_uygula},
    "kesif": {
        "baslik": "AI Değişken Keşfi",
        "aciklama": "Kalıpların dışında yeni değişken hipotezleri üretilir; "
                    "güvenlik kontrolünden geçenler çalıştırılır.",
        "girdi": None, "plan": kesif_plan, "uygula": kesif_uygula},

    "kalite": {
        "baslik": "Değişken Kalite Kontrolü",
        "aciklama": "Üretilen değişkenler eksik değer, sonsuz sayı, sabitlik "
                    "ve sızıntı riski açısından denetlenir.",
        "girdi": None, "plan": kalite_plan, "uygula": kalite_uygula},
    "secim": {
        "baslik": "Aday Değişken Seti",
        "aciklama": "Yarı-sabit eleme, fazlalık eleme, karşılıklı bilgi ve "
                    "model önem skoru sırayla uygulanır.",
        "girdi": None, "plan": secim_plan, "uygula": secim_uygula},

    "model": {
        "baslik": "Model Karşılaştırması",
        "aciklama": "Baz ve zenginleştirilmiş set aynı bölme, aynı "
                    "rastgelelik tohumu ve aynı yapılandırma altında "
                    "karşılaştırılır.",
        "girdi": None, "plan": model_plan, "uygula": model_uygula},
    "algoritma": {
        "baslik": "Algoritma Seçimi",
        "aciklama": "Dört algoritma aynı değişken seti, aynı bölme ve aynı "
                    "rastgelelik tohumu ile eğitilir; ayrıştırma gücü ve "
                    "eğitim süresi "
                    "karşılaştırılır. Uzun sürdüğü için Dataiku senaryosunda "
                    "çalışır.",
        "girdi": None, "plan": algoritma_plan, "uygula": algoritma_uygula},
    "final": {
        "baslik": "Model Finalizasyonu",
        "aciklama": "Seçilen model son haliyle eğitilir, test setinde "
                    "doğrulanır ve pickle biçiminde kaydedilir.",
        "girdi": None, "plan": final_plan, "uygula": final_uygula},
    "katalog": {
        "baslik": "Değişken Kataloğu",
        "aciklama": "Kabul edilen her değişkenin formülü, kaynağı, kodu, "
                    "kalite ve seçim sonucu kalıcı kataloğa yazılır.",
        "girdi": None, "plan": katalog_plan, "uygula": katalog_uygula},
}

# Faz 01'in alt adimlari moda gore degisir.
# "teyit" UC MODDA DA "tanimlar" ile "bolme" arasindadir: bolme sizinti
# sinirini cektigi icin degisken listesi ve sozluk tanimlari en son orada
# degistirilebilir.
FAZ01_ADIMLARI = {
    None: ["mod"],
    # SOZLUK TANIMLARI, MODELLEME TANIMLARINDAN SONRA. Hedef, kimlik ve
    # donem kolonunun sozlukte tanimli olmasi zorunlu; hangi kolonlar
    # oldugu tanimlar adiminda belli oluyor.
    "A":  ["mod", "kurulum", "tanimlar", "sozluk_tanim", "teyit", "bolme"],
    # B ve C'de sozluk VERIDEN URETILIYOR: her kolon tanim aliyor, yani
    # tanimsiz kolon kalmiyor ve ayri bir "sozluk_tanim" adimina gerek
    # yok. Zorunlu tanim kurali orada yapisi geregi saglaniyor.
    "B":  ["mod", "veri_sec", "sozluk_uret", "tanimlar", "teyit", "bolme"],
    "C":  ["mod", "ham_veri", "birlestirme", "sozluk_uret", "tanimlar",
           "teyit", "bolme"],
}

# ===========================================================================
# BLOK GRUPLARI
# ===========================================================================
# Ardisik adimlar sohbette TEK BLOK olarak gorunur; her adim blogun
# icinde kendi ALT BASLIGINI ve kendi "Geri Dön" dugmesini tasir. Sol
# paneldeki is akisinda adimlar AYRI kalir (kullanici karari): boylece
# yalnizca modelleme tanimlarina donmek mumkun oluyor.
#
# Gruplama yalnizca GORSELDIR; adim sirasi, sayimi ve geri donus hedefi
# degismez.
ADIM_GRUPLARI = {
    "kurulum":     "veri_sozluk",
    "tanimlar":    "veri_sozluk",
    "sozluk_tanim": "veri_sozluk",
    # B modu: veri seti secimi + sozluk uretimi + modelleme tanimlari
    "veri_sec":    "veri_sozluk",
    "sozluk_uret": "veri_sozluk",
    # C modunda ham tablolar ve birlestirme AYRI kalir: onlar veri
    # hazirlama isi, sozluk ve tanimlar ayri bir karar kumesi.
}

GRUP_BASLIKLARI = {
    "veri_sozluk": GRUP_ADI_VERI_SOZLUK,
}


def adim_grubu(anahtar):
    """Adimin blok grubu. Gruplu degilse (None, "")."""
    grup = ADIM_GRUPLARI.get(anahtar or "")
    if not grup:
        return None, ""
    return grup, GRUP_BASLIKLARI.get(grup, "")

SECIMLI = {"kural", "kesif"}

def adim_sirasi(mod=None):
    """Moda gore duz adim listesi."""
    return FAZ01_ADIMLARI.get(mod, FAZ01_ADIMLARI[None]) + \
        [a for f in SONRAKI_FAZLAR for a in f["adimlar"]]

def fazlar(mod=None):
    """Sol paneldeki hiyerarsi."""
    return [{"no": "01", "baslik": "Çalışma Kurulumu",
             "ozet": FAZ01_OZET,
             "adimlar": FAZ01_ADIMLARI.get(mod, FAZ01_ADIMLARI[None])}] + \
        SONRAKI_FAZLAR

def faz_agaci(mod=None):
    cikti, sayac = [], 0
    for f in fazlar(mod):
        adimlar = []
        for a in f["adimlar"]:
            sayac += 1
            grup, grup_baslik = adim_grubu(a)
            adimlar.append({"anahtar": a, "sira": sayac - 1,
                            "no": "%s.%d" % (f["no"].lstrip("0"), len(adimlar) + 1),
                            "baslik": ADIMLAR[a]["baslik"],
                            "aciklama": ADIMLAR[a].get("aciklama", ""),
                            # Blok grubu: on yuz ardisik adimlari tek
                            # blokta, alt basliklarla ciziyor.
                            "grup": grup or "",
                            "grup_baslik": grup_baslik})
        cikti.append({"no": f["no"], "baslik": f["baslik"],
                      "ozet": f["ozet"], "adimlar": adimlar})
    return cikti
