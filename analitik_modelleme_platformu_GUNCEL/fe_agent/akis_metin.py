# -*- coding: utf-8 -*-
"""fe_agent/akis_metin.py - Kullaniciya gosterilen sabit metinler ve mesaj desenleri.

akis.py bolundu; bu dosya o bolumun aynisidir.
"""

import re



KARSILAMA = """**Akıllı Modelleme Platformu'na hoş geldiniz.**
Çalışma, soldaki iş akışındaki beş fazda adım adım ilerler. Her adımda önce ne yapılacağı açıklanır, onayınızla uygulanır ve sonucu kayda geçer. Başlamak için verinizin durumuna uygun başlangıcı seçin."""

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
ve sabitlenmiş veri seti.
- Aday değişken: üretilen ve henüz değerlendirilmemiş yeni değişken.
- Değişken seti: modele girecek değişkenlerin listesi.
- Değişken kataloğu: kabul edilen değişkenlerin kaynağı, dönüşümü, kodu \
ve model katkısının kaydı.
- Beş faz: Çalışma Kurulumu, Veri Anlama ve Hazırlama, Değişken \
Mühendisliği, Değişken Değerlendirme, Modelleme ve Finalizasyon."""

# ===========================================================================
# ADIM 1.1 — CALISMA BASLANGICI  (her secimde ilk adim)
# ===========================================================================

# DORT BASLANGIC. Harf = ekranda gorunen harf = ic anahtar.
#   A  veri seti hazir,  sozluk hazir
#   B  veri seti YOK,    kaynak tablolar VE sozlukleri hazir (yeni:
#                        tablolar ve sozlukler birlestirilir)
#   C  veri seti hazir,  sozluk YOK     (eski B)
#   D  veri seti YOK,    sozluk YOK     (eski C)
# Eski kayitlardaki B/C, okunurken C/D'ye cevriliyor
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
# C ve D YALNIZ ESKI CALISMALAR icin duruyor (kendi adim listeleriyle
# acilmaya devam eder); yeni calismada secilemez.
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
]
for _s in MOD_SECENEKLERI:
    _s["kapali"] = _s["deger"] not in ACIK_MODLAR

# Mod gruplari: kod "mod == 'C'" gibi tek harfe bakmasin, NE yapildigina
# baksin. Yeni bir mod eklenince yalnizca bu iki satir guncellenir.
BIRLESTIREN_MODLAR = ("B", "D")      # veri seti kaynak tablolardan
SOZLUK_URETEN_MODLAR = ("C", "D")    # sozluk dil modeliyle uretiliyor

# Kart tiklamasi harf ("B") ya da sira ("2") gonderebilir.
MOD_SIRA = {str(i + 1): s["deger"] for i, s in enumerate(MOD_SECENEKLERI)}

# LLM baglami ve ozet icin okunur adlar
MOD_ADLARI = {s["deger"]: s["baslik"] for s in MOD_SECENEKLERI}
# Eski calismalarin baslangic adlari (secilemez, ozet / kayit icin).
MOD_ADLARI.update({
    "C": "Baz Veri Seti Mevcut - Baz Sözlük Mevcut Değil (eski)",
    "D": "Kaynak Tablolar Mevcut - Kaynak Sözlükler Mevcut Değil (eski)"})

SONRAKI_FAZLAR = [
    {"no": "02", "baslik": "Veri Anlama ve Hazırlama",
     "ozet": "Profil, kalite, SFA ve stabilite",
     "adimlar": ["veri_profili", "sfa", "stabilite", "baz"]},
    {"no": "03", "baslik": "Değişken Mühendisliği",
     "ozet": "Kural tabanlı ve AI destekli üretim",
     "adimlar": ["kural", "kesif"]},
    {"no": "04", "baslik": "Değişken Değerlendirme",
     "ozet": "Kalite, ilişkiler ve aday değişken seti",
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
# basliginda ve uyari cumlelerinde geciyor. Ayri ayri yazilinca biri
# degisip otekiler eskidigi icin hepsi buradan okunuyor (kullanici
# karari: is akisi ve sohbet ayni ifadeleri kullanmali).
ADIM_ADI = {
    "mod":    "Başlangıç Seçimi",
    "teyit":  "Değişken Listesi ve Tip Kontrolü",
    "tanimlar": "Kolon Rolleri",
    "sozluk_tanim": "Eksik Sözlük Tanımları",
    "kisaltma": "Kısaltmalar ve Kolon Adları",
    "kolon_ad": "Kolon Adı Tamamlama",
    "bolme":  "Örneklem ve Doğrulama Tasarımı",
}
# Gruplu blogun ortak basligi: kurulum + kolon rolleri + sozluk adimlari.
GRUP_ADI_VERI_SOZLUK = "Veri Seti, Sözlük ve Kolon Rolleri"

# norm (kucuk harf, Turkce karaktersiz) uzerinde calisir.
# "onceki adim\w*": akisin kendi onerdigi "önceki adıma dön" cumlesi
# normalize edilince "onceki adima don" oluyor.
GERI_KALIP = re.compile(r"\b(geri|onceki adim\w*|bir onceki|geri don\w*)\b")

SECIM_KALIP = re.compile(r"\d+")

# Yalnizca tek basina "A", "mod b", "3" gibi girdiler mod secimi sayilir.
MOD_KALIP = re.compile(r"^\s*(mod\s*)?([abcd1234])\s*$", re.I)

# norm (kucuk harf, Turkce karaktersiz) uzerinde calisir
SORU_KALIP = re.compile(
    r"\b(neden|niye|nicin|nasil|nedir|ne|ne demek|hangisi|kac|"
    r"fark\w*|acikla\w*|anlat\w*|mi|mu|misin|musun|miyim|muyum)\b")
