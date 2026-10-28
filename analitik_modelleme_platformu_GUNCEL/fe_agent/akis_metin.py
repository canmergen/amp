# -*- coding: utf-8 -*-
"""fe_agent/akis_metin.py - Kullaniciya gosterilen sabit metinler ve mesaj desenleri."""

import re



# ===========================================================================
# KARSILAMA - 01.1 Baslangic Secimi blogunun metni
# ===========================================================================
# Urun duzeyinde, kisiye ya da kuruma baglanmayan metin: platformun ne
# yaptigi, nasil calistigi ve akisin ustteki Is Akisi'ndan izlendigi.
KARSILAMA = (
    "**Hoş geldiniz!**\n"
    "Bu platform, veri hazırlığından nihai modelin oluşturulmasına kadar tüm "
    "model geliştirme sürecini tek bir çalışma alanında bir araya getirir. "
    "Her aşama, alınan kararlar ve elde edilen sonuçlarla birlikte "
    "izlenebilir şekilde yürütülür.\n"
    "**Neler yapabilirsiniz?**\n"
    "Verilerinizi analiz edebilir, yeni değişkenler oluşturup "
    "değerlendirebilir, farklı model denemeleri gerçekleştirebilir ve "
    "değişkenlerin model performansına katkısını ölçebilirsiniz. "
    "Geliştirdiğiniz modelleri karşılaştırabilir ve seçtiğiniz modeli daha "
    "sonra kullanmak üzere kaydedebilirsiniz.\n"
    "**Süreç nasıl ilerler?**\n"
    "Her aşamada yapılacak işlemler ve bunların amacı açıklanır. Analizler ve "
    "hesaplamalar sistem tarafından gerçekleştirilirken önemli kararlar "
    "sizin onayınızla uygulanır. "
    "Değişkenlerin kaynakları, uygulanan dönüşümler, seçim kararları ve "
    "analiz sonuçları çalışma boyunca kayıt altında tutulur. Böylece sürecin "
    "her adımını takip edebilir, sonuçları inceleyebilir ve çalışmanıza "
    "kaldığınız yerden devam edebilirsiniz. "
    "Çalışmanızın ilerleyişini üst bölümdeki **İş Akışı** üzerinden "
    "görüntüleyebilirsiniz.\n\n"
    "**Başlamak için verinizin mevcut durumuna uygun başlangıç seçeneğini "
    "belirleyin.**"
)

# ===========================================================================
# SERBEST SORU
# ===========================================================================
# LLM'in terimleri platformdaki anlamiyla kullanmasi icin sabit tanimlar
PLATFORM_TANIMLARI = """\
- Veri seti: modellemede kullanılan tablo. Her satır bir gözlemdir \
(ör. müşteri-dönem), kolonlar değişkenlerdir; hedef değişken de bu tablodadır.
- Değişken sözlüğü: veri setindeki her değişkenin adını, açıklamasını, \
tipini ve kategorisini içeren tablo. Değişkenlerin ne anlama geldiğini \
belirler ve yeni değişken üretiminde kullanılır.
- Kaynak tablolar: henüz birleştirilmemiş ham tablolar (müşteri, işlem, \
ürün tabloları gibi). Birleştirilerek veri seti oluşturulur.
- Hedef değişken: modelin tahmin edeceği değişken.
- Veri bölme stratejisi: verinin geliştirme ve test kümelerine ayrılma şekli.
- Analitik baz set: Veri Anlama ve Hazırlama fazının sonunda temizlenmiş \
ve sabitlenmiş veri seti; ham ve üretilen değişkenlerin ikisini de içerir.
- Aday değişken: üretilen ve henüz değerlendirilmemiş yeni değişken.
- Değişken seti: modele girecek değişkenlerin listesi.
- Değişken kataloğu: kabul edilen değişkenlerin kaynağı, dönüşümü, kodu \
ve model katkısının kaydı.
- Beş faz: Çalışma Kurulumu, Değişken Mühendisliği, Veri Anlama ve \
Hazırlama, Değişken Değerlendirme, Modelleme ve Finalizasyon."""

# ===========================================================================
# ADIM 1.1 — CALISMA BASLANGICI  (her secimde ilk adim)
# ===========================================================================

# DORT BASLANGIC. Harf = ekranda gorunen harf = ic anahtar.
#   A  veri seti hazir,  sozluk hazir
#   B  veri seti YOK,    kaynak tablolar VE sozlukleri hazir
#                        (tablolar ve sozlukler birlestirilir)
#   C  veri seti hazir,  sozluk YOK
#   D  veri seti YOK,    sozluk YOK
# Eski kayitlardaki B/C degerleri okunurken C/D'ye cevrilir
# (bkz. akis_durum.MOD_GOCU).
# KART METNI: BASLIK elinizde NE MEVCUT, ACIKLAMA neyin
# mevcut OLMADIGI ve bu adimlarla nasil olusturulacagi.
#
# ACIK MODLAR. Buyuk veri (Spark) yoluyla uctan uca
# denenmis baslangiclar acik; digerleri kartta soluk ve tiklanamaz durur,
# yazarak secilmeye calisilirsa da reddedilir. Acmak icin bu listeye ekleyin.
# IKI BASLANGIC. Sozluk her iki baslangicta da
# ISTEGE BAGLI: secilmezse butun kolonlar 01.2.3 Sozluk Tanimlari kartinda
# onayli tanim hafizasi + dil modeli onerileriyle tanimlanir.
# C ve D yalniz eski calismalar icindir (kendi adim listeleriyle
# acilir); yeni calismada secilemez.
ACIK_MODLAR = ("A", "B")

MOD_SECENEKLERI = [
    {"deger": "A", "baslik": "Baz Veri Seti Mevcut",
     "aciklama": "Modellemeye girecek tablo hazır. Sözlüğü varsa onu da "
                 "seçersiniz; tanımı olmayan kolonlar onaylı tanımlardan ve "
                 "yapay zekâ önerilerinden doldurulur."},
    {"deger": "B", "baslik": "Kaynak Tablolar Mevcut",
     "aciklama": "Baz veri seti, seçeceğiniz kaynak tablolar birleştirilerek "
                 "oluşturulur. Tabloların sözlükleri varsa onları da "
                 "seçersiniz; tanımı olmayan kolonlar aynı şekilde doldurulur."},
    # OTOMATIK PILOT (su an kapali). Deger "P": "C" harfi eski
    # calismalarin baslangicina ait; kartta "C" rozetiyle gorunur.
    {"deger": "P", "rozet": "C", "baslik": "Otomatik Pilot",
     "aciklama": "Başta veri setini ve varsa sözlüğünü siz seçersiniz; sonraki "
                 "tüm adımlarda kararları yapay zekâ verir ve hiç durmadan final "
                 "modele kadar uçtan uca ilerler. Her karar gerekçesiyle kayda geçer."},
]
for _s in MOD_SECENEKLERI:
    _s["kapali"] = _s["deger"] not in ACIK_MODLAR

# Mod gruplari: kod "mod == 'C'" gibi tek harfe bakmasin, NE yapildigina
# baksin. Yeni bir mod eklenince yalnizca bu iki satir guncellenir.
BIRLESTIREN_MODLAR = ("B", "D")      # veri seti kaynak tablolardan
SOZLUK_URETEN_MODLAR = ("C", "D")    # sozluk dil modeliyle uretiliyor

# Kart tiklamasi harf ("B") ya da sira ("2") gonderebilir.
MOD_SIRA = {str(i + 1): s["deger"] for i, s in enumerate(MOD_SECENEKLERI)}
# Kartta gorunen rozet harfi ("C") de o secenegi secer.
MOD_SIRA.update({s["rozet"]: s["deger"] for s in MOD_SECENEKLERI if s.get("rozet")})

# LLM baglami ve ozet icin okunur adlar
MOD_ADLARI = {s["deger"]: s["baslik"] for s in MOD_SECENEKLERI}
# Eski calismalarin baslangic adlari (secilemez, ozet / kayit icin).
MOD_ADLARI.update({
    "C": "Baz Veri Seti Mevcut - Baz Sözlük Mevcut Değil (eski)",
    "D": "Kaynak Tablolar Mevcut - Kaynak Sözlükler Mevcut Değil (eski)"})

# SIRA: once degiskenler uretilir, sonra veri anlama ve
# hazirlama ELDEKI BUTUN degiskenlere (ham + uretilen) yapilir: SFA ve PSI
# final veriye olculur. Veri Profili uretimden once kalir: bos, sabit ve
# kimlik benzeri kolonlardan degisken uretilmesin. Adim anahtarlari
# kayitli calismalarla uyumludur; "kalite" anahtari Sizinti Kontrolu adimidir.
SONRAKI_FAZLAR = [
    {"no": "02", "baslik": "Değişken Mühendisliği",
     "ozet": "Profil, kural tabanlı ve AI destekli üretim",
     "adimlar": ["veri_profili", "kural", "kesif"]},
    {"no": "03", "baslik": "Veri Anlama ve Hazırlama",
     "ozet": "SFA, stabilite ve analitik baz set",
     "adimlar": ["sfa", "stabilite", "baz"]},
    {"no": "04", "baslik": "Değişken Değerlendirme",
     "ozet": "Sızıntı kontrolü ve aday değişken seti",
     "adimlar": ["kalite", "secim"]},
    {"no": "05", "baslik": "Modelleme ve Finalizasyon",
     "ozet": "Model seçimi, katkı ölçümü ve doğrulama",
     "adimlar": ["model", "algoritma", "final", "katalog"]},
]

# Faz 01'in ozeti moddan bagimsiz: karsilama kartiyla ayni tanim
FAZ01_OZET = "Veri seti, sözlük, kolon rolleri ve örneklem tasarımı"

# ===========================================================================
# ADIM ADLARI - TEK KAYNAK
# ===========================================================================
# Ayni ad sol paneldeki is akisinda, sohbet blogunun basliginda, kart
# basliginda ve uyari cumlelerinde geciyor; tutarli kalmasi icin hepsi
# buradan okunur.
ADIM_ADI = {
    "mod":    "Başlangıç Seçimi",
    "teyit":  "Değişken Listesi ve Tip Kontrolü",
    "tanimlar": "Kolon Rolleri",
    "sozluk_tanim": "Eksik Sözlük Tanımları",
    "tanimsiz_karar": "Tanımsız Kolonlar",
    "sozluk_birlestir": "Sözlük Birleştirme",
    "sozluk_kontrol": "Sözlük ve Kolon Adı Kontrolü",
    "donem": "Dönem Bilgisi",
    "parca": "Ad Parçaları",
    "aciklama": "Kolon Kartları",
    "kolon_ad": "Kolon Adları",
    "bolme":  "Örneklem ve Doğrulama Tasarımı",
}
# SOZLUK VE KOLON ADI KONTROLU: baslangic secimi gibi iki kartli secim.
# "yap": Donem Bilgisi, Ad Parcalari, Kolon Kartlari ve Kolon Adlari
# sirayla calisir. "atla": dort adim kendiliginden atlanir;
# aciklamalar ve kolon adlari oldugu gibi kalir. Iki durumda da sonuc
# yalniz AMP_VERISETI ve AMP_SOZLUK'e (Degisken Listesi ve Tip Kontrolu
# onaylaninca) yazilir.
KONTROL_ADIMLARI = ("donem", "parca", "aciklama", "kolon_ad")
KONTROL_SECENEKLERI = [
    {"deger": "yap", "rozet": "A", "baslik": "Sözlük ve Kolon Adları Kontrol Edilsin",
     "aciklama": "Kolon adlarının parçaları, her kolonun kartı ve açıklaması ve "
                 "yeni kolon adları sırayla kontrol edilip onaylanır. Düzeltmeler yalnız platformun "
                 "kopyalarına (AMP_VERISETI, AMP_SOZLUK) yazılır."},
    {"deger": "atla", "rozet": "B", "baslik": "Kontrol Edilmeden Geçilsin",
     "aciklama": "Açıklamalar ve kolon adları olduğu gibi kalır; bu dört adım "
                 "atlanır ve Değişken Listesi ve Tip Kontrolü'ne geçilir."},
]
KONTROL_SORUSU = ("Sözlükteki açıklamalar ve kolon adları kontrol edilsin mi? "
                  "Girdi veri setiniz ve sözlüğünüz iki durumda da değişmez.")
# Kartta gorunen harf ("A", "B") ya da sira ("1", "2") da secer.
KONTROL_SIRA = {"a": "yap", "1": "yap", "b": "atla", "2": "atla",
                "yap": "yap", "atla": "atla"}
# ONCEKI ONAYLI KONTROL: ayni veri seti ve sozluk(ler) icin proje
# hafizasinda kayit varsa ilk secenek olarak gelir (harfler kayar). Onayli
# alt adimlar denetlenip yeniden sorulmadan uygulanir; yarim kalan alt adim
# kaldigi yerden acilir (bkz. akis_faz01, kontrol_gecmisi).
KONTROL_ONCEKI_BASLIK = "Önceki Onaylı Kontrol Uygulansın"
# Onceki secenegi varken "yap"in basligi (ikisinin farki acik olsun).
KONTROL_ADIM_ADIM_BASLIK = "Adım Adım Kontrol Edilsin"
KONTROL_SORUSU_ONCEKI = (
    "Bu veri seti ve sözlük için proje hafızasında önceki bir kontrol var. "
    "Önceki onaylı kontrol mü uygulansın, adım adım yeniden mi kontrol "
    "edilsin? Girdi veri setiniz ve sözlüğünüz her durumda değişmez.")

# Gruplu blogun ortak basligi: kurulum + kolon rolleri + sozluk adimlari.
GRUP_ADI_VERI_SOZLUK = "Veri Seti, Sözlük ve Kolon Rolleri"

# MODEL TIPI (Kolon Rolleri'nin ilk secimi). Ad, rollerin yazildigi her
# yerde (Ozet, Veri Seti karti, Arsiv ozeti, dokuman, senaryo konfigi,
# katalog) hedef degiskenin ustunde gecer.
MODEL_TIPI_ADI = {
    "classification": "Classification",
    "regression": "Regression",
    "time_series": "Time Series Forecasting",
    "clustering": "Clustering",
}
MODEL_TIPI_TURKCE = {
    "classification": "Sınıflandırma",
    "regression": "Regresyon",
    "time_series": "Zaman Serisi Tahmini",
    "clustering": "Kümeleme",
}


def model_tipi(durum):
    """Secilen model tipinin kodu. Model tipi secimi gelmeden once
    hedefi tanimlanmis calismalarda hedef 0/1 oldugu icin
    "classification"; hic tanim yoksa bos dize."""
    durum = durum or {}
    if durum.get("problem"):
        return durum["problem"]
    return "classification" if (durum.get("meta") or {}).get("target") else ""


def model_tipi_adi(durum):
    """Ekranda ve kayitlarda gorunen ad: "Classification"; secim yoksa bos."""
    return MODEL_TIPI_ADI.get(model_tipi(durum), "")

# norm (kucuk harf, Turkce karaktersiz) uzerinde calisir.
# "onceki adim\w*": akisin kendi onerdigi "önceki adıma dön" cumlesi
# normalize edilince "onceki adima don" oluyor.
GERI_KALIP = re.compile(r"\b(geri|onceki adim\w*|bir onceki|geri don\w*)\b")

SECIM_KALIP = re.compile(r"\d+")

# Yalnizca tek basina "A", "mod b", "3" gibi girdiler mod secimi sayilir.
MOD_KALIP = re.compile(r"^\s*(mod\s*)?([abcdp1234])\s*$", re.I)

# norm (kucuk harf, Turkce karaktersiz) uzerinde calisir
SORU_KALIP = re.compile(
    r"\b(neden|niye|nicin|nasil|nedir|ne|ne demek|hangisi|kac|"
    r"fark\w*|acikla\w*|anlat\w*|mi|mu|misin|musun|miyim|muyum)\b")
