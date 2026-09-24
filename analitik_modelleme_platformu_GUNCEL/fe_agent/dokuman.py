# -*- coding: utf-8 -*-
"""fe_agent/dokuman.py - Teknik Model Dokumani (TMD) govdesi.

NEDEN AYRI BIR MODUL
  akis_panel.detay() ust seridin ve testlerin kullandigi KISA ozettir:
  "su an ne var". Model Risk'e giden dokuman baska bir seydir - sirasi,
  bolum iskeleti ve eksik bolumleri sabittir, kullanici duzenleyebilir ve
  Word olarak disari cikar. Ikisini tek fonksiyona sikistirmak, ozeti
  degistiren her dokunusun dokumani da degistirmesi demekti.

NEDEN BU TURDA LLM YOK
  Govdenin tamami DETERMINISTIK: her sayi, oran ve esik koddan gelir.
  Model Risk'e giden bir dokumanda uydurulmus tek bir metrik butun
  dokumani degersizlestirir. Once dogrulugu garantili govde kurulur;
  yorum paragraflari sonraki turda bunun ETRAFINA yazilir.

NEDEN VERISI OLMAYAN BOLUM ATLANMAZ
  Atlanan bolum "yok" degil "gorunmez"dir. Calismanin neresinin eksik
  oldugu dokumana bakan kisinin ilk sorusu; bolum "bu adim henuz
  calismadi" diye durmali ki eksiklik gorulebilsin.

NEDEN HER BOLUMUN BIR STATUSU VAR
  "Bolum var" ile "bolum tam" ayni sey degil. Statu (TAMAM / KISMI /
  EKSIK / BLOKER) bu ikisini ayirir; BLOKER ise teslim kapisini besler.
  Kapi ETIKETTEDIR: hicbir adimi durdurmaz, Word indirmeyi kapatmaz,
  yalnizca dokumanin final olarak gonderilip gonderilemeyecegini yazar.

NEDEN BEKLENEN ICERIK LISTESI SABIT ORNEK METIN ICERMEZ
  `eksikler` listesi "bu bolum ne icermeli" sorusunu cevaplar. Icine
  ornek bir kurum, veri seti ya da kolon adi yazmak, kullanicinin o
  ornegi kendi calismasi sanip kopyalamasina yol acardi; listedeki her
  madde KAVRAM adidir, veri adi degildir.

VERI KAYNAGI
  Yalnizca `durum` sozlugu. Hicbir dataset OKUNMAZ; gosterilen her sayi
  ilgili plan/uygula adiminda zaten hesaplanip duruma yazilmistir. Alan
  adlari ve bicimleme akis_panel.detay() ile AYNI kaynaktan gelir.
"""

import datetime

from fe_agent import docx_yaz
from fe_agent import kutuk as kutuk_mod
from fe_agent import secim as secim_mod
from fe_agent import sfa as sfa_mod
from fe_agent import validasyon as validasyon_mod
from fe_agent.akis_metin import MOD_ADLARI
from fe_agent.akis_durum import (
    LINEAGE_ADI, TRAIN_KULLANIMI_BASLIK, _ond, _sayi,
    bolme_ayarlari, bolme_ozeti, bolme_uyarilari,
)

BASLIK = "Analitik Modelleme Platformu: Model Geliştirme Dokümanı"

# Degeri henuz uretilmemis alanin isareti - akis_panel.BOS_DEGER ile ayni.
BOS_DEGER = "-"

# (anahtar, no, baslik, kaynak). SIRA BAGLAYICIDIR; ekran ve Word ciktisi
# ayni sirayi kullanir. `no` None olan iki bolum NUMARASIZDIR: kunye bir
# onsoz, ek bir eklentidir; ikisini de numaralamak 22 numarali bir
# dokuman uretir ve "20 bolumluk TMD" ifadesini bozardi.
#
# kaynak: "hesaplanan" (tamami platformdan) · "kullanici" (tamami
# kullanicidan) · "karma" (platform bir kismini hesaplar, kalanini
# kullanici yazar).
BOLUM_TANIMLARI = (
    ("kunye",            None, "Doküman Kontrolü ve Künye",            "karma"),
    ("yonetici_ozeti",      1, "Yönetici Özeti ve Validasyon Hazırlık "
                               "Durumu",                          "hesaplanan"),
    ("amac",                2, "Modelin İş Amacı, Kapsamı ve Kullanım "
                               "Şekli",                            "kullanici"),
    ("veri",                3, "Veri Kaynakları, Population ve Veri "
                               "Lineage",                              "karma"),
    ("hedef",               4, "Hedef Değişken ve Performans Penceresi",
                                                                       "karma"),
    ("bolme",               5, "Örneklem Tasarımı ve MD / OOS / OOT "
                               "Kurgusu",                         "hesaplanan"),
    ("kalite",              6, "Veri Kalitesi ve Ön İşleme",           "karma"),
    ("sfa",                 7, "Tek Değişken Analizi (SFA)",      "hesaplanan"),
    ("stabilite",           8, "Stabilite ve Temsil Yeteneği",    "hesaplanan"),
    ("uretim",              9, "Değişken Üretimi",                "hesaplanan"),
    ("eleme",              10, "Değişken Eleme ve Seçim",         "hesaplanan"),
    ("metodoloji",         11, "Model Geliştirme Metodolojisi",        "karma"),
    ("performans",         12, "Model Performansı ve İstatistiksel "
                               "Belirsizlik",                     "hesaplanan"),
    ("kalibrasyon",        13, "Kalibrasyon, Cut-off ve Karar "
                               "Mekanizması",                      "kullanici"),
    ("aciklanabilirlik",   14, "Açıklanabilirlik, Hassasiyet ve "
                               "Sağlamlık",                            "karma"),
    ("segment",            15, "Segment / Alt Kırılım ve Sezonsallık",
                                                                   "kullanici"),
    ("uygulama",           16, "Uygulama, Üretim Eşdeğerliği ve "
                               "Kontroller",                       "kullanici"),
    ("izleme",             17, "Model İzleme Çerçevesi",           "kullanici"),
    ("kisit",              18, "Kısıtlar, Varsayımlar ve Model Riskleri",
                                                                   "kullanici"),
    ("tekrar",             19, "Tekrarlanabilirlik ve Model Envanteri",
                                                                       "karma"),
    ("teslim",             20, "Validasyon Teslim Paketi ve Açık "
                               "Aksiyonlar",                      "hesaplanan"),
    ("ek",               None, "Ekler",                           "hesaplanan"),
)

BOLUM_ANAHTARLARI = tuple(a for a, _, _, _ in BOLUM_TANIMLARI)
BOLUM_NUMARALARI = {a: n for a, n, _, _ in BOLUM_TANIMLARI}
BOLUM_BASLIKLARI = {a: b for a, _, b, _ in BOLUM_TANIMLARI}

# Kullanicinin yazmasi gereken bolumler bos kalirsa `eksik_bolum`a duser.
KULLANICI_BOLUMLERI = tuple(a for a, _, _, k in BOLUM_TANIMLARI
                            if k == "kullanici")

# ---------------------------------------------------------------------------
# STATU MODELI
# ---------------------------------------------------------------------------
TAMAM, KISMI, EKSIK, BLOKER = "TAMAM", "KISMI", "EKSIK", "BLOKER"
STATULER = (TAMAM, KISMI, EKSIK, BLOKER)

# Yoklugu VALIDASYON TESLIMINI engelleyen bolumler. Liste kapalidir:
# baska hicbir bolum BLOKER olamaz.
#   amac       - modelin ne oldugu bilinmeden hicbir metodoloji
#                degerlendirilemez.
#   hedef      - event tanimi ve performans penceresi yoksa model riskinin
#                tanimi dogrulanamaz.
#   bolme      - sizinti siniri bilinmeden performans kanit degildir.
#   performans - model kurulmadiysa ortada degerlendirilecek bir sey yok.
#   kisit      - bilinen kisitlar yazilmadan artik risk kabul edilemez.
#
# Platformun HIC hesaplamadigi bolumler (13 kalibrasyon, 15 segment,
# 16 uygulama, 17 izleme) bilerek DISARIDA: eksik analizin varligini
# gostermek ayri sey, platformun yapmadigi isi teslim kapisina koymak
# ayri sey. Onlarin eksikligi raporlanir, teslimi kilitlemez.
BLOKER_BOLUMLER = ("amac", "hedef", "bolme", "performans", "kisit")

# Govde kokundeki teslim ozeti alanlari. Tek bolum kaydedildiginde de
# AYNEN bu alanlar geri doner; on yuz damgayi ve sayaclari ikinci bir
# istek atmadan tazeleyebilsin diye tek yerde tanimli.
TESLIM_OZET_ALANLARI = ("teslim_durumu", "teslim_damgasi", "hazir_mi",
                        "bloker_sayisi", "eksik_sayisi", "kismi_sayisi",
                        "eksik_bolum")

TESLIM_HAZIR = "hazir"
TESLIM_TASLAK = "taslak"
DAMGA_HAZIR = "Validasyon teslimine hazır"
DAMGA_TASLAK = "TASLAK: validasyon teslimine hazır değil"

# Eski bolum anahtarlarinin yeni karsiliklari. Gocun yonu TEK YONLUDUR:
# okurken eski anahtar yeniye tasinir, yazarken yalnizca yeni kullanilir.
ESKI_ANAHTAR_GOCU = {
    "model": "metodoloji",
    "validasyon": "performans",
}

BOS_METIN = "Bu adım henüz çalışmadı."
KULLANICI_BOS_METIN = ("Bu bölümü siz yazmalısınız; hesaplanan bir karşılığı "
                       "yok.")
HESAPLANAMADI_METIN = ("Bu bölüm hesaplanamadı: kayıtlı çalışma verisinde "
                       "beklenmeyen bir alan var (%s).")

# Listelerde ve tablolarda gosterilen en fazla satir. 1.042 kolonlu bir
# veri setinde eksik kolon listesi dokumani tek basina yutuyor; kalan
# sayisi acikca yazilir, tam liste ilgili veri setinde durur.
EN_FAZLA_SATIR = 15


# ===========================================================================
# BEKLENEN ICERIK - `eksikler` listesinin kaynagi
# ---------------------------------------------------------------------------
# Her madde bir KAVRAMDIR: "ne yazilmali" sorusunu cevaplar, ornek bir
# deger ya da kolon adi tasimaz. Platformun ZATEN hesapladigi madde bu
# listelere girmez; platform tarafinin eksikleri EKSIK_URETICILERI
# icinde, duruma bakilarak uretilir.
# ===========================================================================
BEKLENEN_ICERIK = {
    "kunye": (
        "Model geliştirici: ad ve birim",
        "Model sahibi: ad ve birim",
        "Validasyon ekibi: ad ve birim",
        "Revizyon satırı: sürüm, tarih, değişikliğin özeti",
    ),
    "amac": (
        "Modelin ne tahmin ettiği",
        "Hangi karar anında kullanıldığı",
        "Hangi population üzerinde çalıştığı",
        "Skorun nerede tüketildiği",
        "Model dışı kurallarla ilişkisi",
        "Hariç tutulan population",
        "Yeniden geliştirme tetikleyicileri",
    ),
    "veri": (
        "Kaynak sistemler ve tablolar",
        "Join anahtarları",
        "As-of date mantığı",
        "Inclusion / exclusion kuralları",
        "Her adımda kontrol toplamı (satır ve kimlik sayısı)",
    ),
    "hedef": (
        "Event / bad tanımı",
        "Good tanımı",
        "Observation date",
        "Performance window",
        "Maturity / censoring kuralı",
        "Target exclusion kuralları",
    ),
    "kalite": (
        "Imputation: yöntem, eşik, etkilenen değişken, karar",
        "Outlier treatment: yöntem, eşik, etkilenen değişken, karar",
        "Kategorik kodlama: yöntem, etkilenen değişken, karar",
        "Transformasyon: yöntem, etkilenen değişken, karar",
        "Leakage / post-event kontrolü: yöntem ve sonuç",
    ),
    "metodoloji": (
        "Algoritma seçim gerekçesi",
        "Benchmark / challenger model karşılaştırması",
        "Hiperparametre arama uzayı ve seçim metriği",
        "Class imbalance yaklaşımı",
        "Erken durdurma karar mantığı",
    ),
    "kalibrasyon": (
        "Skorun sıralama mı olasılık mı taşıdığı",
        "Calibration plot",
        "Brier skoru ve reliability değerlendirmesi",
        "Cut-off seçim yöntemi ve iş kısıtı",
        "Reject / accept etkisi",
        "Override ve policy kuralları",
    ),
    "aciklanabilirlik": (
        "Global SHAP değerlendirmesi",
        "Yerel açıklama örnekleri",
        "Feature ablation sonuçları",
        "Hiperparametre duyarlılığı",
        "Veri perturbasyonu ve stres senaryoları",
    ),
    "segment": (
        "Dönem kırılımında population, event rate, AUC, KS, PSI ve yorum",
        "Segment kırılımında aynı ölçüler ve yorum",
        "Ürün / kanal kırılımında aynı ölçüler ve yorum",
        "Genişletilmiş zaman penceresinde AUC / KS karşılaştırması",
    ),
    "uygulama": (
        "Input schema",
        "Feature parity kontrolü",
        "Score parity kontrolü ve kabul toleransı",
        "Fallback davranışı",
        "Versioning",
        "Erişim ve audit kuralları",
    ),
    "izleme": (
        "Ayrıştırma gücü: metrik, periyot, eşik, aksiyon",
        "Population drift (PSI): metrik, periyot, eşik, aksiyon",
        "Skor konsantrasyonu: metrik, periyot, eşik, aksiyon",
        "Kalibrasyon: metrik, periyot, eşik, aksiyon",
        "Veri kalitesi: metrik, periyot, eşik, aksiyon",
        "İş sonucu: metrik, periyot, eşik, aksiyon",
    ),
    "kisit": (
        "Her kısıt ve varsayım için etkisi",
        "Her kısıt için mitigasyon planı",
        "Her kısıt için sahibi",
    ),
    "tekrar": (
        "Run ID",
        "Code version (commit / recipe sürümü)",
        "Data snapshot: as-of tarihi ve veri seti kimliği",
        "Feature list hash",
        "Model artifact hash",
        "Environment lockfile",
        "Config snapshot",
    ),
}

# Statu tablosundaki "aksiyon" sutunu: tek satirlik, emir kipinde.
AKSIYONLAR = {
    "kunye": "Rol ve revizyon bilgisini gir",
    "yonetici_ozeti": "",
    "amac": "Modelin amacını, kapsamını ve kullanım şeklini yaz",
    "veri": "Kaynak sistem, join ve as-of mantığını yaz",
    "hedef": "Event tanımı ve performans penceresi ekle",
    "bolme": "Örneklem bölme adımını çalıştır",
    "kalite": "Ön işleme kararlarını yaz",
    "sfa": "Tek değişken analizi adımını çalıştır",
    "stabilite": "Stabilite adımını çalıştır",
    "uretim": "Değişken üretimi adımını çalıştır",
    "eleme": "Eleme ve seçim adımını çalıştır",
    "metodoloji": "Algoritma seçim gerekçesini ve arama uzayını yaz",
    "performans": "Model adımını çalıştır",
    "kalibrasyon": "Kalibrasyon ve cut-off analizini ekle",
    "aciklanabilirlik": "Açıklanabilirlik analizlerini ekle",
    "segment": "Segment ve sezonsallık analizini ekle",
    "uygulama": "Üretim eşdeğerliği kontrollerini ekle",
    "izleme": "İzleme çerçevesini yaz",
    "kisit": "Kısıt, varsayım ve model risklerini yaz",
    "tekrar": "Sürüm, snapshot ve hash bilgisini gir",
    "teslim": "",
    "ek": "",
}

# BLOKER bolumlerin statu notu: validator dili, tek cumle.
BLOKER_NOTLARI = {
    "amac": "Modelin ne olduğu yazılmadan metodoloji değerlendirilemez.",
    "hedef": "Event tanımı ve performans penceresi yok.",
    "bolme": "Örneklem bölme kararı yok; sızıntı sınırı bilinmiyor.",
    "performans": "Model kurulmadı; değerlendirilecek bir sonuç yok.",
    "kisit": "Bilinen kısıtlar yazılmadan artık risk kabul edilemez.",
}


# ===========================================================================
# KUCUK YARDIMCILAR
# ===========================================================================
def _sz(durum, anahtar):
    """durum[anahtar] sozluk degilse bos sozluk.

    Durum JSON'dan okunur; eski ya da elle duzeltilmis bir kayitta bu
    alanlar metin/None gelebilir ve tek bir bozuk alan butun dokumani
    dusurur."""
    deger = (durum or {}).get(anahtar)
    return deger if isinstance(deger, dict) else {}


def _ls(deger):
    """Liste/demet ise liste, degilse bos liste."""
    return list(deger) if isinstance(deger, (list, tuple)) else []


def _n(deger):
    """Sayiyi Turkce bicimle; deger yoksa '-'. _sayi(None) 'None' yazardi."""
    if deger is None:
        return BOS_DEGER
    try:
        return _sayi(int(float(deger)))
    except (TypeError, ValueError):
        return str(deger)


def _m(deger):
    """Metin alani; bos/None ise '-'."""
    if deger is None or (isinstance(deger, str) and not deger.strip()):
        return BOS_DEGER
    return str(deger)


def _sayisal_mi(deger):
    try:
        float(deger)
        return deger is not None
    except (TypeError, ValueError):
        return False


def _alan_tablosu(satirlar, baslik=None):
    """[(etiket, deger)] -> iki kolonlu tablo blogu. Degeri None olan
    satir ATILIR: 'olcmedik' ile 'olctuk, sonuc bos' ayni sey degil ve
    ikincisi acikca '-' yazar."""
    dolu = [(e, d) for e, d in satirlar if d is not None]
    if not dolu:
        return None
    blok = {"tur": "tablo", "kolonlar": ["Alan", "Değer"],
            "satirlar": [[str(e), str(d)] for e, d in dolu]}
    if baslik:
        blok["baslik"] = baslik
    return blok


def _kisa_liste(ogeler, en_fazla=EN_FAZLA_SATIR):
    """Uzun listeyi kirpar ve KAC TANE kaldigini yazar."""
    ogeler = [str(o) for o in _ls(ogeler)]
    if len(ogeler) <= en_fazla:
        return ogeler
    return ogeler[:en_fazla] + ["… ve %s tane daha" % _sayi(len(ogeler) - en_fazla)]


def _ikili_tablo(ciftler, kolonlar, basamak=3, en_fazla=EN_FAZLA_SATIR):
    """[(ad, sayi)] -> iki kolonlu tablo. Bos liste None doner."""
    ciftler = [c for c in _ls(ciftler)
               if isinstance(c, (list, tuple)) and len(c) >= 2]
    if not ciftler:
        return None
    satirlar = [[str(a), _ond(d, basamak)] for a, d in ciftler[:en_fazla]]
    return {"tur": "tablo", "kolonlar": list(kolonlar), "satirlar": satirlar}


def _bloklar(*adaylar):
    """None olan bloklari eler; hepsi None ise bos liste."""
    return [b for b in adaylar if b]


def _p(metin, kalin=False):
    """Paragraf blogu. `kalin` YENI BIR BLOK TURU DEGILDIR: Word
    ureticisi bu bayragi okur, ekran tanimadigi alani gormezden gelir ve
    paragrafi yine cizer. Besinci bir blok turu on yuzde SESSIZCE
    kaybolurdu."""
    blok = {"tur": "paragraf", "metin": metin}
    if kalin:
        blok["kalin"] = True
    return blok


def _zamansal_mi(durum):
    """Test seti zaman disi mi (OOT) yoksa ayni donemden mi (OOS)?"""
    b = _sz(durum, "bolme")
    if not b.get("tur"):
        return None
    try:
        return bolme_ayarlari(durum)["test_tanim"] == "zamansal"
    except Exception:
        return None


def _model_calisti(durum):
    md = _sz(durum, "model")
    return bool(md) and not md.get("hata")


# ===========================================================================
# DUZ METIN KARSILIGI
# ---------------------------------------------------------------------------
# Kullanici duzenlemeye BUNUN uzerinden basliyor: ekranda gordugu bolum
# textarea'ya bu metinle doluyor. Bu yuzden metin bloklarin TAM karsiligi
# olmali - tabloyu atlarsak kullanici duzenlemeye basladigi anda tablo
# sessizce kayboluyor.
# ===========================================================================
def _blok_metni(blok):
    tur = blok.get("tur")
    if tur == "liste":
        return "\n".join("• %s" % o for o in (blok.get("ogeler") or []))
    if tur == "tablo":
        satirlar = []
        if blok.get("baslik"):
            satirlar.append(str(blok["baslik"]))
        satirlar.append(" | ".join(str(k) for k in (blok.get("kolonlar") or [])))
        for satir in (blok.get("satirlar") or []):
            satirlar.append(" | ".join(str(h) for h in satir))
        return "\n".join(satirlar)
    return str(blok.get("metin") or "")


def duz_metin(bloklar):
    """Blok listesinin duz metin karsiligi."""
    parcalar = [_blok_metni(b) for b in (bloklar or []) if isinstance(b, dict)]
    return "\n\n".join(p for p in parcalar if p)


def _metin_bloklari(metin):
    """Kullanici metnini bloklara cevirir.

    Duzenlenmis bolum de Word'e ayni yoldan gider; ayri bir "duzenlenmis
    bolumu ciz" dali acmak, ekranda gorunen ile dosyaya yazilanin
    ayrisabilecegi ikinci bir kod yolu demekti."""
    return [{"tur": "paragraf", "metin": p}
            for p in str(metin).split("\n\n") if p.strip()]


# ===========================================================================
# BOLUM URETICILERI
# ---------------------------------------------------------------------------
# Her uretici blok LISTESI doner. Bos liste "bu adim henuz calismadi"
# demektir ve cagiran taraf onu "bos" bloguna cevirir.
# ===========================================================================
def _kunye(durum):
    mod = durum.get("mod")
    meta = _sz(durum, "meta")
    bloklar = _bloklar(_alan_tablosu([
        ("Doküman", BASLIK),
        ("Çalışma modu", ("%s - %s" % (mod, MOD_ADLARI.get(mod, mod)))
                         if mod else BOS_DEGER),
        ("Veri seti", _m(durum.get("veri_seti"))),
        ("Sözlük", _m(durum.get("sozluk") or durum.get("sozluk_yedek"))),
        ("Hedef değişken", _m(meta.get("target"))),
        ("Doküman tarihi", _bicimli_zaman(_olusturma(durum))),
    ]))
    # Roller KULLANICI alanidir. Bos hucreye "[TAMAMLANMALI]" yazmak
    # dokumanin icine bir gorev listesi gomerdi; eksiklik `eksikler`
    # listesinde ve statu tablosunda duruyor, tabloda yalnizca "-" var.
    bloklar.append({"tur": "tablo", "baslik": "Roller",
                    "kolonlar": ["Rol", "Ad ve birim"],
                    "satirlar": [["Model geliştirici", BOS_DEGER],
                                 ["Model sahibi", BOS_DEGER],
                                 ["Validasyon", BOS_DEGER]]})
    bloklar.append({"tur": "tablo", "baslik": "Revizyon geçmişi",
                    "kolonlar": ["Sürüm", "Tarih", "Değişiklik"],
                    "satirlar": [[BOS_DEGER, BOS_DEGER, BOS_DEGER]]})
    return bloklar


def _kullanici_bolumu(durum):
    """Hesaplanan karsiligi OLMAYAN bolumler.

    Bos donuyoruz ki eksik_bolum listesine dussun ve ekranda "bu bölümü
    siz yazmalısınız" cagrisi ciksin."""
    return []


# --- 1. Yonetici ozeti ------------------------------------------------------
def _yonetici_ozeti(durum):
    """Model ozeti tablosu: her satirda MEVCUT BILGI ve TMD'de BEKLENEN
    NETLIK yan yana. Boylece "ne var" ile "ne olmali" ayni bakista
    gorulur; statu tablosu bu bolume ikinci blok olarak eklenir."""
    meta = _sz(durum, "meta")
    p = _sz(durum, "profil")
    md = _sz(durum, "model")
    b = _sz(durum, "bolme")
    duzenli = duzenlemeler(durum)

    def _yazildi(anahtar):
        return ("Kullanıcı tarafından yazıldı" if duzenli.get(anahtar)
                else BOS_DEGER)

    veri_metni = BOS_DEGER
    if durum.get("veri_seti"):
        veri_metni = str(durum["veri_seti"])
        if p.get("satir"):
            veri_metni += " · %s satır" % _n(p.get("satir"))

    perf = BOS_DEGER
    metrikler = _sz(_sz(durum, "validasyon"), "metrikler")
    if metrikler.get("gini_test") is not None:
        perf = "Test Gini %s" % _ond(metrikler.get("gini_test"), 4)
    elif _sz(md, "enhanced").get("auc") is not None:
        perf = "Zengin model AUC %s" % _ond(_sz(md, "enhanced").get("auc"), 4)

    satirlar = [
        ["Amaç", _yazildi("amac"),
         "Karar anı, population ve skorun tüketildiği yer"],
        ["Hedef", _m(meta.get("target")),
         "Event tanımı, observation date ve performans penceresi"],
        ["Veri", veri_metni,
         "Kaynak sistem, join anahtarı ve as-of date mantığı"],
        ["Bölme", (bolme_ozeti(durum) if b.get("tur") else BOS_DEGER),
         "MD / OOS / OOT ayrımı ve sızıntı sınırı"],
        ["Model", _m(md.get("algoritma")),
         "Algoritma seçim gerekçesi ve challenger karşılaştırması"],
        ["Performans", perf,
         "Set bazlı metrikler ve istatistiksel belirsizlik"],
    ]
    return [{"tur": "tablo", "baslik": "Model özeti",
             "kolonlar": ["Konu", "Mevcut bilgi", "TMD'de beklenen netlik"],
             "satirlar": satirlar}]


# --- 3. Veri ----------------------------------------------------------------
def _teyit_satiri(durum):
    """'20.09.2026 19:40 · 2 kolon süreç dışı' - teyit yoksa None.

    Zaman damgasi akis_faz01.teyit_uygula tarafindan ISO olarak yazilir;
    bicimleme dokumanin kendi kurali (bkz. _bicimli_zaman)."""
    t = _sz(durum, "teyit")
    zaman = t.get("zaman")
    if not zaman:
        return None
    return "%s · %s kolon süreç dışı" % (_bicimli_zaman(zaman),
                                         _n(t.get("haric") or 0))


def _veri(durum):
    p = _sz(durum, "profil")
    meta = _sz(durum, "meta")
    kolon = p.get("kolon_baslangic") or p.get("kolon")
    if not (durum.get("veri_seti") or kolon):
        return []

    sayisal = p.get("sayisal")
    kategorik = None
    if kolon is not None and sayisal is not None:
        try:
            kategorik = int(kolon) - int(sayisal) - int(p.get("tarih") or 0)
        except (TypeError, ValueError):
            kategorik = None

    satirlar = [
        ("Veri seti", _m(durum.get("veri_seti"))),
        ("Satır sayısı", _n(p.get("satir")) if p.get("satir") else None),
        ("Kolon sayısı", _n(kolon) if kolon else None),
        ("Sayısal kolon", _n(sayisal) if sayisal is not None else None),
        ("Kategorik kolon", _n(max(kategorik, 0))
                            if kategorik is not None else None),
        ("Tarih kolonu", _n(p.get("tarih")) if p.get("tarih") else None),
        # Kimlik ve donem kolonu VERI bolumune ait: population'in birimi
        # ve zaman ekseni burada tanimlanir, hedef bolumunde degil.
        ("Kimlik kolonu", _m(meta.get("id"))),
        ("Dönem kolonu", meta.get("donem") or "belirtilmedi"),
        ("Dönem aralığı", ("%s-%s" % (p.get("donem_min"), p.get("donem_maks")))
                          if p.get("donem_min") else None),
        ("Sözlük", _m(durum.get("sozluk") or durum.get("sozluk_yedek"))),
        ("Sözlükteki tanım", _n(p.get("sozluk_satir"))
                             if p.get("sozluk_satir") else None),
        ("Sözlük kapsamı", ("%%%s" % _ond(p.get("kapsam"), 1))
                           if p.get("kapsam") is not None else None),
        # Bolme oncesi son teyit DENETIM KAYDIDIR: degisken listesinin ve
        # sozluk tanimlarinin hangi an, kac kolon surec disindayken
        # onaylandigi. Teyit adimi calismadiysa satir hic yazilmaz -
        # olmayan bir onayi rapora sokmak yanlis kanit olurdu.
        ("Sözlük teyidi", _teyit_satiri(durum)),
    ]

    bloklar = _bloklar(_alan_tablosu(satirlar))

    # Mod C: veri seti kaynak tablolardan birlestirilerek uretildi;
    # dokumanin veri bolumu bu kokeni yazmazsa tablo "nereden geldi"
    # sorusu cevapsiz kalir.
    birlestirme = _sz(_sz(durum, "birlestirme"), "ozet")
    if birlestirme:
        bloklar.append(_alan_tablosu([
            ("İskelet tablo", _m(birlestirme.get("ana_tablo"))),
            ("Anahtar", _m(" + ".join(_ls(birlestirme.get("anahtar"))))),
            ("Dönem kolonu", _m(birlestirme.get("donem_kolon"))),
            ("Kaynak tablo sayısı", _n(birlestirme.get("kaynak_sayisi"))),
            ("Eklenen kolon", _n(birlestirme.get("eklenen_kolon"))),
            ("Point-in-time kolon", _n(birlestirme.get("pit_kolon"))),
            ("Soy kütüğü", _m(_sz(durum, "birlestirme").get("lineage")
                              or LINEAGE_ADI)),
        ], baslik="Kaynak tabloların birleştirilmesi"))

    uretim = _sz(durum, "sozluk_uretim")
    if uretim:
        bloklar.append(_alan_tablosu([
            ("Taranan kolon", _n(uretim.get("toplam"))),
            ("Açıklama üretilen", _n(uretim.get("aciklamali"))),
            ("Kapsam", "%%%s" % _ond(uretim.get("kapsam"), 1)),
        ], baslik="Sözlük üretimi"))

    return [b for b in bloklar if b]


# --- 4. Hedef ---------------------------------------------------------------
def _hedef(durum):
    meta = _sz(durum, "meta")
    if not meta.get("target"):
        return []
    p = _sz(durum, "profil")
    return _bloklar(_alan_tablosu([
        ("Hedef değişken", _m(meta.get("target"))),
        ("Hedef tipi", _m(p.get("hedef_tip"))),
        ("Dağılım", _m(p.get("hedef_ozet"))),
        # event_rate durumda ZATEN YUZDE olarak duruyor (8.87 = %8,87);
        # 100 ile carpmak %887 yazardi (bkz. akis_panel._yuzde_dogrudan).
        ("Pozitif sınıf oranı", ("%%%s" % _ond(float(p["event_rate"]), 2))
                                if _sayisal_mi(p.get("event_rate")) else None),
    ]))


# --- 5. Bolme ---------------------------------------------------------------
# Iki cumle bu bolumde ZORUNLUDUR ve kosula baglanmaz:
#   1) algoritmanin ic validation_fraction'i BAGIMSIZ VALIDASYON SETI
#      DEGILDIR - erken durdurma icin egitim verisinden ayrilan bir
#      parcadir, dokumanda "validasyon seti var" izlenimi birakirsa
#      validator yanlis bir kanit gorur;
#   2) ayni donemden bagimsiz bir OOS seti YOKSA bu acikca yazilir.
VALIDATION_FRACTION_NOTU = (
    "Algoritmanın iç validation_fraction parametresi bağımsız validasyon "
    "seti DEĞİLDİR: erken durdurma için eğitim verisinden ayrılan bir "
    "parçadır, model geliştirme setinin içinde kalır ve bağımsız bir "
    "performans kanıtı üretmez.")


def _bolme(durum):
    b = _sz(durum, "bolme")
    # detay() ile AYNI kosul: bolme adimi calismadan bolme_ayarlari()
    # yine de varsayilan bir ayar dondurur; onu "karar verilmis bolme"
    # gibi yazmak olmayan bir kararı rapora sokardi.
    if not b.get("tur"):
        return []

    a = bolme_ayarlari(durum)
    sayim = _sz(b, "satir")
    zamansal = a["test_tanim"] == "zamansal"
    donem_metni = ", ".join(str(x) for x in _ls(b.get("oot_donemleri"))) \
        or (b.get("oot_deger") or BOS_DEGER)

    satirlar = [
        ("Test tanımı", "zamansal (OOT)" if zamansal else "rastgele"),
        ("Bölme birimi", "kimlik bazlı" if a["birim"] == "kimlik"
                         else "satır bazlı"),
        ("Katmanlama", "açık" if a["katmanla"] else "kapalı"),
        ("Train kullanımı", TRAIN_KULLANIMI_BASLIK.get(a["train_kullanimi"],
                                                       a["train_kullanimi"])),
        ("Çapraz doğrulama", ("%s · %s kat" % (a["cv"], _n(a["kat"])))
                             if a["cv"] != "yok" else "yok"),
        ("Test dönemi", donem_metni if zamansal else None),
        ("Test oranı", ("%%%d" % round(100 * float(a["test_oran"])))
                       if not zamansal else None),
        ("Toplam satır", _n(b.get("toplam_satir")) if b.get("toplam_satir")
                         else None),
        ("Geliştirme satırı", _n(sayim.get("egitim") or b.get("train_satir"))),
        ("Doğrulama satırı", _n(sayim.get("val")) if sayim.get("val") else None),
        ("Test satırı", _n(sayim.get("test") or b.get("test_satir"))),
        ("Seed", _n(a["seed"])),
    ]
    bloklar = _bloklar(_alan_tablosu(satirlar),
                       _p("Set özeti - %s" % bolme_ozeti(durum)))

    # MD / OOS / OOT TERMINOLOJI TABLOSU. Platformda AYRI bir OOT seti
    # yoktur: zamansal testte test setinin KENDISI OOT'dur. Bunu tabloda
    # acikca yazmak, "uc set var mi" sorusunu tek bakista cevaplar.
    oos_durum = ("yok - test seti zaman dışı (OOT) olarak tanımlandı"
                 if zamansal else "var (test seti)")
    oot_durum = "var (test seti)" if zamansal else "yok - test rastgele ayrıldı"
    test_satir = _n(sayim.get("test") or b.get("test_satir"))
    bloklar.append({
        "tur": "tablo", "baslik": "MD / OOS / OOT kurgusu",
        "kolonlar": ["Set", "Amaç", "Mevcut durum", "Satır", "Dönem"],
        "satirlar": [
            ["MD (model geliştirme)", "Model bu set üzerinde öğrenir", "var",
             _n(sayim.get("egitim") or b.get("train_satir")),
             "test dışındaki dönemler" if zamansal else "tüm dönemler"],
            ["OOS (aynı dönem, bağımsız)",
             "Öğrenmeye girmemiş satırlarda ayrıştırma gücü", oos_durum,
             BOS_DEGER if zamansal else test_satir,
             BOS_DEGER if zamansal else "tüm dönemler"],
            ["OOT (zaman dışı)", "Sonraki dönemlerde davranış", oot_durum,
             test_satir if zamansal else BOS_DEGER,
             donem_metni if zamansal else BOS_DEGER],
        ]})

    if zamansal:
        bloklar.append(_p(
            "Aynı dönemden ayrılmış bağımsız bir OOS seti YOKTUR: test "
            "seti zaman dışı (OOT) olarak tanımlandığı için ayrıştırma "
            "gücü yalnızca sonraki dönemlerde ölçülmüştür."))
    else:
        bloklar.append(_p(
            "Zaman dışı (OOT) bir test dönemi YOKTUR: test seti rastgele "
            "ayrıldığı için modelin sonraki dönemlerdeki davranışı bu "
            "kurguda ölçülmemiştir."))

    # Ic validasyon parcasi: hiperparametrelerde varsa satir olarak da
    # gosterilir, cumle her hâlükârda yazilir.
    hiper = _sz(_sz(durum, "model"), "hiperparametreler")
    if hiper.get("validation_fraction") is not None:
        bloklar.append(_alan_tablosu([
            ("validation_fraction", str(hiper.get("validation_fraction"))),
            ("early_stopping", str(hiper.get("early_stopping", BOS_DEGER))),
        ], baslik="Algoritmanın iç doğrulama parçası"))
    bloklar.append(_p(VALIDATION_FRACTION_NOTU))

    uyarilar = bolme_uyarilari(durum)
    if uyarilar:
        # Uyarilar dokumandan DUSURULMEZ: bolmenin zayif tarafini
        # Model Risk'in kendisi bulmak zorunda kalmamali.
        bloklar.append({"tur": "liste", "ogeler": _kisa_liste(uyarilar)})
    return bloklar


# --- 6. Kalite --------------------------------------------------------------
def _kalite(durum):
    """VERI kalitesi - ham kolonlarin profil teshisi.

    DIKKAT: durum["kalite"] BASKA bir seydir (uretilen degiskenlerin
    kalite kapisi) ve 10. bolumde raporlanir. Bolum anahtarlarinin
    ikisi de "kalite" kelimesini tasiyor; karistirmamak icin buraya
    yalnizca profil_teshis giriyor."""
    p = _sz(durum, "profil")
    t = _sz(p, "profil_teshis")
    if not t:
        return []

    kusurlu = [("Eksik oranı %50 üstünde", "cok_bos"),
               ("Sabit ya da tek değerli", "sabit"),
               ("Kimlik benzeri", "kimlik_gibi"),
               ("Kardinalitesi aşırı yüksek", "yuksek_kardinalite")]
    satirlar = [("Sorunsuz kolon", _n(len(_ls(t.get("temiz")))))]
    satirlar += [(ad, _n(len(_ls(t.get(k))))) for ad, k in kusurlu]
    if p.get("duplicate") is not None:
        satirlar.append(("Duplicate satır", _n(p.get("duplicate"))))
    if p.get("null_oran") is not None:
        satirlar.append(("Toplam null oranı",
                         "%%%s" % _ond(100.0 * float(p["null_oran"]), 2)))

    bloklar = _bloklar(_alan_tablosu(satirlar))
    for ad, k in kusurlu:
        adlar = _ls(t.get(k))
        if adlar:
            # Etiket ALT BASLIK degil PARAGRAF: sozlesmenin govde bicimi
            # dort blok turu tanimliyor (paragraf/tablo/liste/bos) ve ekran
            # onlari ciziyor. Bes numarali bir tur gondermek, ekranda
            # SESSIZCE kaybolan bir satir demekti.
            bloklar.append(_p("%s:" % ad))
            bloklar.append({"tur": "liste", "ogeler": _kisa_liste(adlar)})

    bloklar.append(_p(
        "Yukarıdaki sayılar ölçümdür, karar değildir. Bir kontrolün "
        "sonucunun temiz çıkması o kontrolün gereksiz olduğu anlamına "
        "gelmez: imputation, outlier, kodlama, transformasyon ve leakage "
        "kontrollerinin her biri için yapılan işlem ve çıkan sonuç ayrı "
        "ayrı yazılmalıdır."))
    return bloklar


# --- 7. SFA -----------------------------------------------------------------
SFA_KAPI_NOTU = (
    "SFA PASS'i model giriş kapısı değildir: SFA tek değişkenli "
    "ayrıştırma gücünü ölçer, modele hangi değişkenlerin gireceğini "
    "belirlemez. FAIL alan bir değişken çok değişkenli modelde anlamlı "
    "olabilir; modele giren liste eleme ve seçim adımında belirlenir.")


def _psi_haritasi(durum):
    """Degisken -> PSI. Stabilite adiminin duruma yazdigi en kotu
    degiskenler; tamami ilgili veri setinde durur."""
    harita = {}
    for cift in _ls(_sz(durum, "stabilite").get("en_kotu")):
        if isinstance(cift, (list, tuple)) and len(cift) >= 2:
            harita[str(cift[0])] = cift[1]
    return harita


def _sfa(durum):
    s = _sz(durum, "sfa")
    if s.get("analiz_edilen") is None:
        return []
    bloklar = _bloklar(_alan_tablosu([
        ("Analiz edilen değişken", _n(s.get("analiz_edilen"))),
        ("PASS", _n(s.get("pass_adet"))),
        ("Ölçülemeyen (ATLANDI)", _n(len(_ls(s.get("atlanan"))))),
        ("Sızıntı şüpheli", _n(len(_ls(s.get("sizinti"))))),
        ("Tam tablo", _m(s.get("tablo_dataset"))),
    ]))

    # PASS ESIGI koddan okunur; dokumana elle yazilan bir esik, modul
    # degistiginde sessizce yalan olurdu.
    bloklar.append(_p(
        "PASS kriteri: bilgi değeri (IV) > %s VE tek değişken ayrıştırma "
        "gücü (C-value) > %s. İkisinden biri sağlanmazsa FAIL; ölçüm "
        "yapılamayan değişken ATLANDI sayılır ve elenmiş gibi "
        "gösterilmez. Sızıntı şüphesi eşiği: C-value > %s."
        % (_ond(sfa_mod.IV_ESIK, 2), _ond(sfa_mod.C_ESIK, 2),
           _ond(sfa_mod.SIZINTI_ESIK, 2))))
    bloklar.append(_p(SFA_KAPI_NOTU))

    # KARAR TABLOSU: platformda hangi alan varsa o doldurulur, olmayan
    # "-" kalir. Bos birakmak yerine "-" yazmak, olculmemis ile sifir
    # olculmusu ayirir.
    psi = _psi_haritasi(durum)
    imput = _sz(s, "imputation")
    satirlar = []
    for kayit in _ls(s.get("ilk20"))[:EN_FAZLA_SATIR]:
        if not isinstance(kayit, dict):
            continue
        ad = str(kayit.get("FEATURE"))
        satirlar.append([
            ad,
            _ond(kayit.get("IV"), 4),
            _ond(kayit.get("C_VALUE"), 4),
            _m(imput.get(ad)),
            _ond(psi.get(ad), 4) if ad in psi else BOS_DEGER,
            _m(kayit.get("SFA_RESULT")),
        ])
    if satirlar:
        bloklar.append({
            "tur": "tablo", "baslik": "Tek değişken karar tablosu",
            "kolonlar": ["Değişken", "IV", "C-value", "Eksik değer işlemi",
                         "PSI", "SFA sonucu"],
            "satirlar": satirlar})
    else:
        en_iyi = _ikili_tablo(s.get("en_iyi"), ["Değişken", "IV"])
        if en_iyi:
            en_iyi["baslik"] = "Bilgi değeri (IV) en yüksek değişkenler"
            bloklar.append(en_iyi)

    if _ls(s.get("sizinti")):
        bloklar.append(_p("Sızıntı şüphelileri:"))
        bloklar.append({"tur": "liste",
                        "ogeler": _kisa_liste(s.get("sizinti"))})
    return bloklar


# --- 8. Stabilite -----------------------------------------------------------
def _stabilite(durum):
    st = _sz(durum, "stabilite")
    if not st:
        return []
    if st.get("atlandi"):
        # ATLANDI, CALISMADI DEGILDIR: adim calisti ve olcum yapilamayacagina
        # KARAR VERDI. Ikisini ayni gostermek, yapilmis bir karari yapilmamis
        # gibi raporlamak olurdu.
        return [_p("Stabilite analizi atlandı: karşılaştırılacak test "
                   "seti ya da ölçülebilir değişken bulunamadı.")]

    bloklar = _bloklar(_alan_tablosu([
        ("Ölçülen değişken", _n(st.get("olculen"))),
        ("Kararlı", _n(st.get("stabil"))),
        ("Kayma gösteren", _n(len(_ls(st.get("kayan"))))),
        ("Ölçülemeyen (ATLANDI)", _n(len(_ls(st.get("atlanan"))))),
        ("Karşılaştırma", _m(st.get("karsilastirma"))),
        ("Ölçümün anlamı", _m(st.get("olcum_turu"))),
        ("Tam tablo", _m(st.get("tablo_dataset"))),
    ]))

    # PSI'nin NASIL hesaplandigi koddan okunur. Yontem yazilmadan bir PSI
    # sayisi karsilastirilabilir degildir: bin sayisi ve eksik degerin
    # nereye konuldugu sonucu dogrudan degistirir.
    bloklar.append(_alan_tablosu([
        ("Bin yaklaşımı",
         "geliştirme setinin yüzdelikleri, %s bin" % _n(sfa_mod.BIN_SAYISI)),
        ("Kategorik değişken",
         "seviyeler doğrudan karşılaştırılır; %s seviyeden fazlası ölçülmez "
         "(ATLANDI)" % _n(sfa_mod.KATEGORIK_MAX)),
        ("Eksik değer",
         "ayrı bir bin'dir; paylar tüm satır sayısı üzerinden normalize "
         "edilir, böylece null oranındaki kayma PSI'ya girer"),
        ("Sıfır oran düzeltmesi",
         "sıfır paylı hücre %s alt sınırına çekilir; düzeltme olmadan "
         "logaritma tanımsız kalır ve PSI sonsuza giderdi"
         % _ond(sfa_mod.SIFIR_ORAN_TABAN, 4)),
        ("Kararlılık eşiği",
         "PSI < %s kararlı sayılır" % _ond(sfa_mod.PSI_ESIK, 2)),
        ("En az satır",
         "%s satırın altında ölçüm yapılmaz" % _n(sfa_mod.MIN_SATIR)),
    ], baslik="PSI hesaplama yöntemi"))

    en_kotu = _ikili_tablo(st.get("en_kotu"), ["Değişken", "PSI"])
    if en_kotu:
        en_kotu["baslik"] = "En çok kayan değişkenler"
        bloklar.append(en_kotu)
    return bloklar


# --- 9. Uretim --------------------------------------------------------------
# Kaynak anahtari -> dokumanda gorunen ad (akis_panel.KAYNAK_ADI ile ayni
# kelimeler; dokuman "AI" yerine acik yazi kullanir).
URETIM_KAYNAKLARI = (("kural", "Kural tabanlı üretim"),
                     ("kesif", "AI keşfi"))


def _uretim(durum):
    uretilen = _ls(durum.get("uretilen"))
    if not uretilen:
        return []

    kaynak = _sz(durum, "uretilen_kaynak")
    satirlar = [("Toplam üretilen değişken", _n(len(uretilen)))]
    for anahtar, ad in URETIM_KAYNAKLARI:
        adlar = _ls(kaynak.get(anahtar))
        if adlar:
            satirlar.append((ad, _n(len(adlar))))
    baz = _sz(durum, "baz")
    if baz.get("dataset"):
        satirlar.append(("Analitik baz set", _m(baz.get("dataset"))))
        satirlar.append(("Baz set değişkeni", _n(len(_ls(baz.get("kolonlar"))))))
        satirlar.append(("Eksik değer doldurma", _m(baz.get("doldurma"))))

    bloklar = _bloklar(_alan_tablosu(satirlar))

    # Kod bloklari: (baslik, satirlar, kaynak). Hangi donusum ailesinden
    # kac degisken cikti - uretimin ic dokumu.
    blok_satirlari = []
    for blok in _ls(durum.get("kod_bloklari")):
        if not isinstance(blok, (list, tuple)) or len(blok) < 2:
            continue
        blok_satirlari.append([str(blok[0]), _n(len(_ls(blok[1])))])
    if blok_satirlari:
        bloklar.append({"tur": "tablo", "baslik": "Dönüşüm aileleri",
                        "kolonlar": ["Aile", "Üretilen değişken"],
                        "satirlar": blok_satirlari[:EN_FAZLA_SATIR]})
    if durum.get("kod_bloklari"):
        bloklar.append(_p(
            "Üretilen değişkenlerin formülleri çalışma hafızasındaki "
            "üretim kodunda durur (PROJE_HAFIZASI/uretim_kodu.py); "
            "üretim ortamında aynı kod çalıştırılmalıdır."))
    return bloklar


# --- 10. Eleme --------------------------------------------------------------
def _soyagaci_metni(durum):
    """MODEL GIRDI SOYAGACI: validatorun ilk soracagi sey "modele giren
    degisken listesi nereden geldi". Platform kurali: girdi = BAZ SET
    ∪ SECILEN. Secim 0 dondurdugunde girdi baz setin kendisidir - bu bir
    tutarsizlik degil, kuralin sonucu. Yazilmazsa dokuman "secim 0 ama
    model 7 degiskenle kurulmus" diye CELISKILI okunuyor."""
    md = _sz(durum, "model")
    if not md or md.get("hata"):
        return None
    baz_n = int(md.get("baz_kolon") or 0)
    yeni_n = int(md.get("yeni_kolon") or 0)
    if yeni_n:
        return ("Modele giren değişken listesi = analitik baz set "
                "(%s değişken) ∪ seçim adımının seçtikleri (%s değişken) "
                "= %s değişken."
                % (_n(baz_n), _n(yeni_n), _n(baz_n + yeni_n)))
    return ("Modele giren değişken listesi = analitik baz set (%s "
            "değişken). Seçim adımı bu çalışmada değişken seçmedi; "
            "platform kuralı gereği model girdisi baz setin kendisidir. "
            "SFA'nın PASS/FAIL sonucu model giriş kapısı DEĞİLDİR; SFA "
            "tek değişken gücünü ölçer, baz seti belirlemez." % _n(baz_n))


def _eleme(durum):
    k = _sz(durum, "kalite")
    sc = _sz(durum, "secim")
    if not k and sc.get("secilen") is None:
        return []

    bloklar = []
    if k:
        gecti = len(_ls(k.get("gecti")))
        elenen = sum(len(_ls(k.get(a))) for a in ("eksik", "sabit", "sizinti"))
        bloklar.append(_alan_tablosu([
            ("Kapıya giren", _n(gecti + elenen)),
            ("Geçen", _n(gecti)),
            ("Eksik değer nedeniyle elenen", _n(len(_ls(k.get("eksik"))))),
            ("Sabit dağılım nedeniyle elenen", _n(len(_ls(k.get("sabit"))))),
            ("Sızıntı şüphesiyle elenen", _n(len(_ls(k.get("sizinti"))))),
        ], baslik="Teknik kalite kapısı"))

    if sc.get("secilen") is not None:
        bloklar.append(_alan_tablosu([
            ("Aday değişken", _n(sc.get("aday"))),
            ("Yarı sabit nedeniyle elenen", _n(sc.get("yari_sabit"))),
            ("Korelasyon nedeniyle elenen", _n(sc.get("korelasyon"))),
            ("Düşük önem nedeniyle elenen", _n(sc.get("dusuk_onem"))),
            ("Seçilen", _n(sc.get("secilen"))),
            ("Önem yöntemi", _m(sc.get("onem_yontemi"))),
            ("Hesaplama kapsamı", _m(sc.get("hesap_kapsami"))),
        ], baslik="Aday değişken seçimi"))
        en_iyi = _ikili_tablo(sc.get("en_iyi"), ["Değişken", "Önem"],
                              basamak=5)
        if en_iyi:
            en_iyi["baslik"] = "Seçilen değişkenler (önem sırasıyla)"
            bloklar.append(en_iyi)

    # ADIM ADIM KARAR IZI: hangi kontrol kac degisken eledi, geriye kac
    # kaldi. Toplam sayilar ayri tablolarda duruyor; izi olmadan "neden
    # bu kadar dustu" sorusu cevapsiz kaliyordu.
    iz = _karar_izi(k, sc)
    if iz:
        bloklar.append({
            "tur": "tablo", "baslik": "Adım adım karar izi",
            "kolonlar": ["Sıra", "Kontrol", "Eşik / yöntem", "Elenen",
                         "Kalan"],
            "satirlar": iz})

    soyagaci = _soyagaci_metni(durum)
    if soyagaci:
        bloklar.append(_p(soyagaci))
    return [b for b in bloklar if b]


def _karar_izi(k, sc):
    """Eleme adimlarinin sirasi, esigi ve kalan sayisi.

    Esikler ilgili modullerin SABITLERINDEN okunur; kalite kapisinin
    esikleri adim kodunda adlandirilmis sabit olarak durmadigi icin
    nitel yazilir ("yarıdan fazla"), uydurma bir sayi yazilmaz."""
    satirlar = []
    if k:
        gecti = len(_ls(k.get("gecti")))
        elenenler = [
            ("Eksik değer", "eksik oranı yarıdan fazla", len(_ls(k.get("eksik")))),
            ("Sabit dağılım", "tek değerli", len(_ls(k.get("sabit")))),
            ("Sızıntı şüphesi", "hedefle aşırı korelasyon",
             len(_ls(k.get("sizinti")))),
        ]
        kalan = gecti + sum(e[2] for e in elenenler)
        for ad, esik, adet in elenenler:
            kalan -= adet
            satirlar.append([str(len(satirlar) + 1), ad, esik, _n(adet),
                             _n(kalan)])

    if sc.get("secilen") is not None:
        kalan = sc.get("aday")
        adimlar = [
            ("Yarı sabit", "tek değerin payı > %s" % _ond(secim_mod.QUASI_ESIK, 2),
             sc.get("yari_sabit")),
            ("Korelasyon", "|r| > %s" % _ond(secim_mod.KORELASYON_ESIK, 2),
             sc.get("korelasyon")),
            ("Düşük önem",
             "toplam önemin %s katından azı" % _ond(secim_mod.ONEM_ORAN, 4),
             sc.get("dusuk_onem")),
        ]
        for ad, esik, adet in adimlar:
            try:
                kalan = int(kalan or 0) - int(adet or 0)
            except (TypeError, ValueError):
                kalan = None
            satirlar.append([str(len(satirlar) + 1), ad, esik, _n(adet),
                             _n(kalan)])
        satirlar.append([str(len(satirlar) + 1), "Seçilen", "-",
                         BOS_DEGER, _n(sc.get("secilen"))])
    return satirlar


# --- 11. Metodoloji ---------------------------------------------------------
def _metodoloji(durum):
    md = _sz(durum, "model")
    if not md:
        return []
    if md.get("hata"):
        return [_p("Model adımı sonuç üretemedi: %s" % md["hata"])]

    bloklar = _bloklar(_alan_tablosu([
        ("Algoritma", _m(md.get("algoritma"))),
        ("Kütüphane sürümü", _m(md.get("sklearn_surum"))),
        ("Tekrar sayısı", _n(md.get("tekrar"))),
        ("Model seed", _n(md.get("seed")) if md.get("seed") is not None
                       else None),
        ("Tekrar seedleri", ", ".join(str(x) for x in _ls(md.get("seedler")))
                            or None),
    ]))

    hiper = _sz(md, "hiperparametreler")
    if hiper:
        bloklar.append({"tur": "tablo", "baslik": "Hiperparametreler",
                        "kolonlar": ["Parametre", "Değer"],
                        "satirlar": [[str(k), str(v)]
                                     for k, v in sorted(hiper.items())]})
        bloklar.append(_p(
            "Hiperparametreler SABİTTİR: bu çalışmada arama yapılmadı, "
            "yukarıdaki değerler platformun varsayılanlarıdır."))

    iterasyon = _sz(md, "erken_durdurma_iterasyon")
    if iterasyon:
        bloklar.append(_alan_tablosu([
            ("Baz model iterasyonları",
             ", ".join(str(x) for x in _ls(iterasyon.get("baz"))) or None),
            ("Zengin model iterasyonları",
             ", ".join(str(x) for x in _ls(iterasyon.get("zengin"))) or None),
        ], baslik="Erken durdurma"))
    return bloklar


# --- 12. Performans ---------------------------------------------------------
# Karsilastirma tablosunda gosterilen metrikler: (etiket, durum anahtari).
MODEL_METRIKLERI = (("ROC-AUC", "auc"), ("Gini", "gini"), ("KS", "ks"))

VALIDASYON_KAPISI_BASLIGI = \
    "Platform validasyon kapısı (bağımsız validasyon DEĞİLDİR)"


def _performans(durum):
    md = _sz(durum, "model")
    if not md:
        return []
    if md.get("hata"):
        # Model adimi COKMEDI, sonuc uretemedi. Sebebi dokumanda kalmali:
        # bos bir "performans" bolumu okuyanin "unutulmus" sanmasina yol acar.
        return [_p("Model karşılaştırması tamamlanamadı: %s" % md["hata"])]

    b, e = _sz(md, "baseline"), _sz(md, "enhanced")
    d, ds = _sz(md, "delta"), _sz(md, "delta_std")
    ga = _sz(md, "delta_guven_araligi")

    satirlar, gurultulu = [], []
    for etiket, anahtar in MODEL_METRIKLERI:
        if b.get(anahtar) is None and e.get(anahtar) is None:
            continue
        aralik = _ls(ga.get(anahtar))
        aralik_metni = BOS_DEGER
        if len(aralik) == 2 and None not in aralik:
            aralik_metni = "[%s ; %s]" % (_ond(aralik[0], 4), _ond(aralik[1], 4))
            try:
                if float(aralik[0]) <= 0.0 <= float(aralik[1]):
                    gurultulu.append(etiket)
            except (TypeError, ValueError):
                pass
        satirlar.append([etiket, _ond(b.get(anahtar), 4),
                         _ond(e.get(anahtar), 4), _ond(d.get(anahtar), 4),
                         _ond(ds.get(anahtar), 4), aralik_metni])

    bloklar = _bloklar(_alan_tablosu([
        ("Baz model değişkeni", _n(md.get("baz_kolon"))),
        ("Zengin model değişkeni",
         _n((md.get("baz_kolon") or 0) + (md.get("yeni_kolon") or 0))),
        ("Eklenen yeni değişken", _n(md.get("yeni_kolon"))),
        ("Ölçüm kapsamı", _m(md.get("kapsam"))),
        ("Eğitim satırı", _n(md.get("egitim_satir"))),
        ("Test satırı", _n(md.get("test_satir"))),
        ("Tekrar sayısı", _n(md.get("tekrar"))),
        ("Hedefi boş olan satır", _n(md.get("hedef_nan_dusen"))
                                  if md.get("hedef_nan_dusen") else None),
    ]))

    if satirlar:
        bloklar.append({
            "tur": "tablo", "baslik": "Baz model ile zengin modelin farkı",
            "kolonlar": ["Metrik", "Baz", "Zengin", "Δ", "Δ std", "%95 GA"],
            "satirlar": satirlar})

    soyagaci = _soyagaci_metni(durum)
    if soyagaci:
        bloklar.append(_p(soyagaci))

    # SIRA ONEMLI: once "karsilastirma yapildi mi", sonra "sonuc anlamli
    # mi". Yeni kolon yoksa baz ve zengin AYNI modeldir; delta mekanik
    # olarak sifir, guven araligi [0,0] cikar. Bunu gurultu yorumuna
    # sokmak, hic yapilmamis bir olcum hakkinda istatistiksel hukum
    # kurmak demekti - validasyona giden bir dokumanda en pahali hata.
    if not md.get("karsilastirilabilir", True):
        bloklar.append(_p((md.get("karsilastirma_notu") or "")
                          + " Tablodaki Δ ve güven aralığı değerleri bu "
                            "nedenle katkı kanıtı olarak okunmamalıdır."))
    # Guven araligi sifiri iceriyorsa katki GURULTUDEN AYIRT EDILEMEZ.
    # Bu cumle dokumanin en kritik cumlesi; ortu bas edilmez.
    elif gurultulu:
        bloklar.append(_p(
            "%s için %%95 güven aralığı sıfırı içeriyor: yeni "
            "değişkenlerin katkısı gürültüden ayırt edilemiyor."
            % " ve ".join(gurultulu)))
    elif ga:
        bloklar.append(_p(
            "Güven aralıklarının hiçbiri sıfırı içermiyor: ölçülen katkı "
            "seed değişiminden ayırt edilebiliyor."))

    bloklar.append(_set_performans_tablosu(durum))
    bloklar.extend(_validasyon_kapisi(durum))
    return [x for x in bloklar if x]


def _set_performans_tablosu(durum):
    """Metrik x set tablosu. Platformun HESAPLAMADIGI hucre '-' kalir;
    bos birakmak "olculdu, sifir cikti" gibi okunurdu."""
    m = _sz(_sz(durum, "validasyon"), "metrikler")

    def _deger(anahtar):
        d = m.get(anahtar)
        return BOS_DEGER if d is None else _ond(d, 4)

    # Zamansal bolmede test setinin KENDISI OOT'dur; ayni sayiyi hem OOS
    # hem OOT sutununa yazmak olmayan bir seti var gostermek olurdu.
    # Bolme bilinmiyorsa test seti OOS sayilir: "ayni donem" daha zayif
    # iddia, olmayan bir zaman disi olcum uydurmaktan yegdir.
    oot_testi = _zamansal_mi(durum) is True

    def _test(anahtar):
        """Test setinin degerini dogru sutuna koyar: (OOS, OOT)."""
        d = _deger(anahtar)
        return (BOS_DEGER, d) if oot_testi else (d, BOS_DEGER)

    gini_oos, gini_oot = _test("gini_test")
    if m.get("gini_oot") is not None:
        gini_oot = _ond(m.get("gini_oot"), 4)
    ks_oos, ks_oot = _test("ks_test")

    satirlar = [
        ["Gini", _deger("gini_egitim"), gini_oos, gini_oot],
        ["KS", BOS_DEGER, ks_oos, ks_oot],
        # Skor PSI yalnizca egitim-OOT karsilastirmasinda olculur:
        # egitim-test PSI yapisi geregi daima gecer, anlamli degildir.
        ["Skor PSI", BOS_DEGER, BOS_DEGER, _deger("psi_skor")],
    ]
    return {"tur": "tablo", "baslik": "Set bazlı performans",
            "kolonlar": ["Metrik", "MD / CV", "OOS", "OOT"],
            "satirlar": satirlar}


def _validasyon_kapisi(durum):
    """Eski 'Validasyon Sonuclari' bolumunun icerigi.

    AYRI BIR BOLUM DEGIL, performansin ALT BLOGU: "validasyon" adli bir
    bolum, bagimsiz validasyonun yapilmis oldugu izlenimini veriyordu.
    Platformun esik kontrolu GELISTIRICININ kendi kontrolu; validatorun
    isini yapmaz."""
    kayit = _sz(durum, "validasyon")
    if not kayit.get("metrikler"):
        return [_p("%s - final model metrikleri henüz üretilmedi; "
                   "platformun eşik kontrolü çalışmadı."
                   % VALIDASYON_KAPISI_BASLIGI)]
    # Esikler ve gecti/kosullu/kaldi karari TEK yerde duruyor: validasyon
    # modulu. Burada yeniden yorumlamak, sekmede "geçti" yazarken
    # dokumanda "kaldı" yazmanin yolunu acardi.
    panel = validasyon_mod.panel(durum)
    satirlar = [[s.get("ad"), s.get("deger"), s.get("esik"), s.get("durum")]
                for s in _ls(panel.get("satirlar"))]
    bloklar = [_p("%s. Aşağıdaki eşikler platformun varsayılanlarıdır ve "
                  "geliştiricinin kendi kontrolüdür; bağımsız validasyon "
                  "ekibinin kriterleri ayrıca uygulanmalıdır."
                  % VALIDASYON_KAPISI_BASLIGI)]
    bloklar.append(_alan_tablosu([
        ("Final model", _m(kayit.get("model"))),
        ("Genel sonuç", _m(panel.get("genel"))),
        ("Özet", _m(panel.get("ozet"))),
    ]))
    if satirlar:
        bloklar.append({"tur": "tablo", "baslik": VALIDASYON_KAPISI_BASLIGI,
                        "kolonlar": ["Kriter", "Değer", "Eşik", "Sonuç"],
                        "satirlar": satirlar})
    return [b for b in bloklar if b]


# --- 14. Aciklanabilirlik ---------------------------------------------------
def _aciklanabilirlik(durum):
    md = _sz(durum, "model")
    sc = _sz(durum, "secim")
    if not md and not sc:
        return []

    bloklar = _bloklar(_alan_tablosu([
        ("Tekrar sayısı", _n(md.get("tekrar")) if md.get("tekrar") else None),
        ("Tekrar seedleri", ", ".join(str(x) for x in _ls(md.get("seedler")))
                            or None),
        ("Seed duyarlılığı ölçümü",
         "aynı kurgu farklı seedlerle tekrarlandı; metrik farkının standart "
         "sapması performans bölümünde raporlanır" if md.get("seedler")
         else None),
        ("Değişken önem yöntemi", _m(sc.get("onem_yontemi"))
                                  if sc.get("onem_yontemi") else None),
    ], baslik="Seed ve yeniden örnekleme duyarlılığı"))

    en_iyi = _ikili_tablo(sc.get("en_iyi"), ["Değişken", "Önem"], basamak=5)
    if en_iyi:
        en_iyi["baslik"] = "Değişken önemleri (seçim adımından)"
        bloklar.append(en_iyi)
        bloklar.append(_p(
            "Değişken önemleri seçim adımının ürettiği sıralamadır; SHAP "
            "ya da ablation tabanlı bir açıklama DEĞİLDİR."))
    return [b for b in bloklar if b]


# --- 19. Tekrarlanabilirlik -------------------------------------------------
def _tekrar(durum):
    """Calismanin YENIDEN URETILEBILMESI icin gereken her sey."""
    md = _sz(durum, "model")
    b = _sz(durum, "bolme")
    ogrenilen = _sz(durum, "ogrenilen_donusum")
    if not (md or b.get("tur") or ogrenilen):
        return []

    a = bolme_ayarlari(durum) if b.get("tur") else {}
    satirlar = [
        ("Bölme seed", _n(a.get("seed")) if a else None),
        ("Bölme birimi", (("kimlik bazlı" if a["birim"] == "kimlik"
                           else "satır bazlı") if a else None)),
        ("Model seed", _n(md.get("seed")) if md.get("seed") is not None
                       else None),
        ("Tekrar seedleri", ", ".join(str(x) for x in _ls(md.get("seedler")))
                            or None),
        ("Algoritma", md.get("algoritma")),
        ("scikit-learn sürümü", md.get("sklearn_surum")),
        ("Modele giren kolon",
         _n(len(_ls(md.get("kullanilan_kolonlar"))))
         if md.get("kullanilan_kolonlar") else None),
        ("Öğrenilen dönüşüm parametreleri",
         ", ".join(sorted(str(k) for k in ogrenilen)) or None),
        ("Üretim kodu", "PROJE_HAFIZASI/uretim_kodu.py"
                        if durum.get("kod_bloklari") else None),
    ]
    return _bloklar(_alan_tablosu(satirlar))


# --- Ekler ------------------------------------------------------------------
# Calisma boyunca yazilan tablolar: (durum yolu, dokumandaki ad).
EK_TABLOLARI = ((("profil", "profil_dataset"), "Veri profili"),
                (("sfa", "tablo_dataset"), "SFA tablosu"),
                (("stabilite", "tablo_dataset"), "Stabilite (PSI) tablosu"),
                (("baz", "dataset"), "Analitik baz set"),
                (("katalog", "dataset"), "Değişken kataloğu"))


def _ek(durum):
    satirlar = []
    for (ust, alt), ad in EK_TABLOLARI:
        deger = _sz(durum, ust).get(alt)
        if deger:
            satirlar.append([ad, str(deger)])

    kt = _sz(durum, "katalog")
    bloklar = []
    if satirlar:
        bloklar.append({"tur": "tablo", "baslik": "Üretilen veri setleri",
                        "kolonlar": ["İçerik", "Veri seti"],
                        "satirlar": satirlar})
    if kt.get("satir") is not None:
        katalog = _alan_tablosu([
            ("Katalog kaydı", _n(kt.get("satir"))),
            ("Seçili değişken", _n(kt.get("secilen"))),
            ("Biçimi bozuk olduğu için atlanan kayıt",
             _n(kt.get("atlanan")) if kt.get("atlanan") else None),
        ], baslik="Değişken kataloğu")
        if katalog:
            bloklar.append(katalog)
    return bloklar


# 1. ve 20. bolum butun bolumlerin statusunden uretilir; govdeleri ikinci
# gecste tamamlanir (bkz. dokuman()).
URETICILER = {
    "kunye": _kunye,
    "yonetici_ozeti": _yonetici_ozeti,
    "amac": _kullanici_bolumu,
    "veri": _veri,
    "hedef": _hedef,
    "bolme": _bolme,
    "kalite": _kalite,
    "sfa": _sfa,
    "stabilite": _stabilite,
    "uretim": _uretim,
    "eleme": _eleme,
    "metodoloji": _metodoloji,
    "performans": _performans,
    "kalibrasyon": _kullanici_bolumu,
    "aciklanabilirlik": _aciklanabilirlik,
    "segment": _kullanici_bolumu,
    "uygulama": _kullanici_bolumu,
    "izleme": _kullanici_bolumu,
    "kisit": _kullanici_bolumu,
    "tekrar": _tekrar,
    "teslim": _kullanici_bolumu,
    "ek": _ek,
}


# ===========================================================================
# EKSIKLER - platform tarafinin durumdan turetilen eksikleri
# ===========================================================================
def _eksik_veri(durum):
    if _sz(durum, "profil").get("satir") or durum.get("veri_seti"):
        return []
    return ["Veri seti profili - veri profili adımı henüz çalışmadı"]


def _eksik_hedef(durum):
    if _sz(durum, "meta").get("target"):
        return []
    return ["Hedef değişken tanımı - tanımlar adımı henüz çalışmadı"]


def _eksik_bolme(durum):
    if not _sz(durum, "bolme").get("tur"):
        return ["MD / OOS / OOT kurgusu - örneklem bölme adımı henüz "
                "çalışmadı"]
    zamansal = _zamansal_mi(durum)
    if zamansal:
        return ["Aynı dönemden ayrılmış bağımsız OOS seti"]
    return ["Zaman dışı (OOT) test dönemi"]


def _eksik_kalite(durum):
    if _sz(_sz(durum, "profil"), "profil_teshis"):
        return []
    return ["Veri kalitesi profili - veri profili adımı henüz çalışmadı"]


def _eksik_sfa(durum):
    if _sz(durum, "sfa").get("analiz_edilen") is not None:
        return []
    return ["Tek değişken analizi - SFA adımı henüz çalışmadı"]


def _eksik_stabilite(durum):
    if _sz(durum, "stabilite"):
        return []
    return ["Değişken bazlı PSI ölçümü - stabilite adımı henüz çalışmadı"]


def _eksik_uretim(durum):
    if _ls(durum.get("uretilen")):
        return []
    return ["Üretilen değişken listesi ve formülleri",
            "Üretim gerekçesi",
            "As-of-date / leakage kuralı",
            "Null, sıfır payda ve sonsuz değer davranışı",
            "Üretim ortamında nasıl hesaplanacağı"]


def _eksik_eleme(durum):
    if _sz(durum, "kalite") or _sz(durum, "secim").get("secilen") is not None:
        return []
    return ["Eleme ve seçim karar izi - ilgili adımlar henüz çalışmadı"]


def _eksik_metodoloji(durum):
    if _model_calisti(durum):
        return []
    return ["Algoritma ve hiperparametreler - model adımı henüz çalışmadı"]


def _eksik_performans(durum):
    if not _model_calisti(durum):
        return ["Model performansı - model adımı henüz çalışmadı"]
    eksik = []
    if not _sz(_sz(durum, "validasyon"), "metrikler"):
        eksik.append("Final model metrikleri - final adımı henüz çalışmadı")
    zamansal = _zamansal_mi(durum)
    if zamansal is True:
        eksik.append("Aynı dönemde bağımsız OOS setinde ölçülmüş performans")
    elif zamansal is False:
        eksik.append("Zaman dışı (OOT) dönemde ölçülmüş performans")
    return eksik


def _eksik_aciklanabilirlik(durum):
    if _model_calisti(durum) or _sz(durum, "secim"):
        return []
    return ["Seed ve yeniden örnekleme duyarlılığı - model adımı henüz "
            "çalışmadı"]


def _eksik_tekrar(durum):
    if _model_calisti(durum) or _sz(durum, "bolme").get("tur"):
        return []
    return ["Seed, algoritma ve sürüm kaydı - model adımı henüz çalışmadı"]


EKSIK_URETICILERI = {
    "veri": _eksik_veri,
    "hedef": _eksik_hedef,
    "bolme": _eksik_bolme,
    "kalite": _eksik_kalite,
    "sfa": _eksik_sfa,
    "stabilite": _eksik_stabilite,
    "uretim": _eksik_uretim,
    "eleme": _eksik_eleme,
    "metodoloji": _eksik_metodoloji,
    "performans": _eksik_performans,
    "aciklanabilirlik": _eksik_aciklanabilirlik,
    "tekrar": _eksik_tekrar,
}


def eksikler(anahtar, durum):
    """Bir bolumde HALA YAZILMASI GEREKEN maddeler.

    Once platform tarafinin eksikleri (duruma bakarak), sonra bu bolumun
    kullanici tarafindan beklenen sabit maddeleri."""
    try:
        platform = list(EKSIK_URETICILERI.get(anahtar, lambda d: [])(durum))
    except Exception:
        # Bozuk durum alani eksik listesini dusurmez: liste bir yardimci,
        # bolumu kaybettirecek kadar kritik degil.
        platform = []
    return platform + list(BEKLENEN_ICERIK.get(anahtar, ()))


# ===========================================================================
# STATU
# ===========================================================================
def _bloker_kosulu(anahtar, durum):
    """BLOKER bolumun KENDI kosulu. "Bolum bos" tek olcu degildir:
    hedef bolumunde platform hedef kolonunu bilir ama event tanimini
    ASLA bilemez; "kolon adi yazili" diye kapiyi acmak blokeri
    islevsiz kilardi."""
    if anahtar in ("amac", "hedef", "kisit"):
        # Bu uc bolumun bloklayan icerigini YALNIZCA kullanici yazabilir.
        return True
    if anahtar == "bolme":
        return not _sz(durum, "bolme").get("tur")
    if anahtar == "performans":
        return not _model_calisti(durum)
    return False


def _statu(anahtar, durum, duzenlendi, icerik_var, hesaplanamadi, eksik):
    """Doner: (statu, statu_notu, eksikler)."""
    if duzenlendi:
        # Platform kullanicinin yazdiginin ICERIGINI denetlemez ve
        # denetledigini IDDIA DA ETMEZ. "Yazildi" bir tamlik kaniti degil,
        # sorumlulugun kullaniciya gectiginin kaydidir.
        return TAMAM, "Kullanıcı tarafından yazıldı.", []

    if hesaplanamadi:
        # "Hesaplanamadi" bir ANALIZ eksigi degil, platform tarafinda bir
        # arizadir. BLOKER diye isaretlemek, gelistiriciyi yapmadigi bir
        # eksikten sorumlu tutardi; EKSIK + acik not dogruyu soyler.
        return EKSIK, ("Bölüm hesaplanamadı: kayıtlı çalışma verisinde "
                       "beklenmeyen bir alan var."), eksik

    if anahtar in BLOKER_BOLUMLER and _bloker_kosulu(anahtar, durum):
        return BLOKER, BLOKER_NOTLARI.get(anahtar, "Teslimi engelliyor."), eksik

    if not icerik_var:
        return EKSIK, "Bu bölümde içerik yok.", eksik

    if eksik:
        return KISMI, ("Platformun hesapladığı kısım var; %s madde "
                       "tamamlanmalı." % _sayi(len(eksik))), eksik

    return TAMAM, "Beklenen içeriğin tamamı var.", []


# ===========================================================================
# GOVDE
# ===========================================================================
def _olusturma(durum):
    """Dokumanin olusturma zamani (ISO).

    durum["dokuman"]["olusturma"] varsa O kullanilir: kullanici bir bolumu
    duzenledigi anda dokuman "var olmus" sayilir ve tarihi artik her
    yenilemede degismez."""
    kayit = _sz(durum, "dokuman").get("olusturma")
    if isinstance(kayit, str) and kayit.strip():
        return kayit
    return datetime.datetime.now().isoformat(timespec="seconds")


def _bicimli_zaman(iso):
    """ISO damgasi -> '20.09.2026 14:12'. Cozulemezse ham damga."""
    try:
        return datetime.datetime.fromisoformat(iso).strftime("%d.%m.%Y %H:%M")
    except (TypeError, ValueError):
        return str(iso)


def goc_uygula(durum):
    """Eski bolum anahtarlarini yeni anahtarlara TASIR (tek yonlu).

    Kullanicinin yazdigi metin sessizce kaybolmaz: hedef anahtarda zaten
    bir duzenleme varsa eski metin UZERINE YAZILMAZ, dusurulur ve kutuge
    kaydedilir - "bir seyler kayboldu" sorusu kayitlardan cevaplanabilsin.

    Durumu YERINDE degistirir; bir sonraki durum_kaydet ile kalici olur.
    Doner: tasinan + dusen kayit sayisi (0 ise hicbir sey degismedi)."""
    kayit = durum.get("dokuman")
    if not isinstance(kayit, dict):
        return 0
    duzenli = kayit.get("duzenlemeler")
    if not isinstance(duzenli, dict):
        return 0
    if not any(a in duzenli for a in ESKI_ANAHTAR_GOCU):
        return 0

    degisiklikler, sayac = [], 0
    for eski, yeni in ESKI_ANAHTAR_GOCU.items():
        deger = duzenli.pop(eski, None)
        if not (isinstance(deger, str) and deger.strip()):
            continue
        sayac += 1
        hedef = duzenli.get(yeni)
        if isinstance(hedef, str) and hedef.strip():
            degisiklikler.append({
                "ALAN": "dokuman", "ANAHTAR": eski,
                "ESKI": deger, "YENI": None,
                "KAYNAK": "bolum gocu - %s bolumunde zaten duzenleme var, "
                          "eski metin dusuruldu" % yeni})
            continue
        duzenli[yeni] = deger
        degisiklikler.append({
            "ALAN": "dokuman", "ANAHTAR": yeni,
            "ESKI": None, "YENI": deger,
            "KAYNAK": "bolum gocu - eski '%s' bolumunden tasindi" % eski})

    if degisiklikler:
        try:
            kutuk_mod.degisiklik_dus(durum.get("_oturum_id"), degisiklikler)
        except Exception:
            # Kutuk yazilamadiysa goc yine de gecerlidir: kullanicinin
            # metnini kaybetmemek, kaydi tutmaktan onceliklidir.
            pass
    return sayac


def duzenlemeler(durum):
    """durum["dokuman"]["duzenlemeler"] - anahtar -> kullanici metni."""
    goc_uygula(durum)
    ham = _sz(_sz(durum, "dokuman"), "duzenlemeler")
    return {k: v for k, v in ham.items()
            if k in BOLUM_ANAHTARLARI and isinstance(v, str) and v.strip()}


def _bolum(durum, anahtar, no, baslik, kaynak, duzenleme):
    if duzenleme is not None:
        # Duzenlenmis bolum YENIDEN URETIMDE EZILMEZ: kullanicinin yazdigi
        # metin hesaplanandan onceliklidir. Hesaplanan hali kaybolmaz,
        # "özgün hâline dön" (bos metin gondermek) onu geri getirir.
        bloklar, hesaplanamadi = _metin_bloklari(duzenleme), False
    else:
        hesaplanamadi = False
        try:
            bloklar = URETICILER[anahtar](durum) or []
        except Exception as e:
            # BIR BOLUM BUTUN DOKUMANI DUSURMEZ. Durum JSON'dan okunuyor;
            # bozuk yazilmis ya da elle duzeltilmis tek bir alan (orn. sayi
            # beklenen yerde metin) bir uretici fonksiyonunu patlatabilir.
            # Yirmi iki bolumun tamamini kaybetmektense o bolum neden
            # hesaplanamadigini soyler; kullanici digerlerini gorur ve
            # eksigin nerede oldugu yine belli olur.
            bloklar = [{"tur": "bos",
                        "metin": HESAPLANAMADI_METIN % type(e).__name__}]
            hesaplanamadi = True

    icerik_var = bool(bloklar) and not hesaplanamadi
    if not bloklar:
        bloklar = [{"tur": "bos",
                    "metin": (KULLANICI_BOS_METIN if kaynak == "kullanici"
                              else BOS_METIN)}]

    statu, notu, eksik = _statu(anahtar, durum, duzenleme is not None,
                                icerik_var, hesaplanamadi,
                                eksikler(anahtar, durum))

    return {"anahtar": anahtar, "no": no, "baslik": baslik,
            "kaynak": kaynak, "statu": statu, "statu_notu": notu,
            "eksikler": eksik, "duzenlendi": duzenleme is not None,
            "bloklar": bloklar,
            "metin": (duzenleme if duzenleme is not None
                      else duz_metin(bloklar))}


def _bolum_etiketi(bolum):
    """Statu tablosunda ve Word basliginda gorunen ad."""
    return ("%d. %s" % (bolum["no"], bolum["baslik"]) if bolum.get("no")
            else bolum["baslik"])


def _statu_tablosu(bolumler):
    return [{"no": b["no"], "anahtar": b["anahtar"], "baslik": b["baslik"],
             "statu": b["statu"], "not": b["statu_notu"],
             "aksiyon": ("" if b["statu"] == TAMAM
                         else AKSIYONLAR.get(b["anahtar"], ""))}
            for b in bolumler]


def _statu_blogu(tablo, baslik):
    return {"tur": "tablo", "baslik": baslik,
            "kolonlar": ["Bölüm", "Statü", "Not", "Aksiyon"],
            "satirlar": [["%s%s" % (("%d. " % s["no"]) if s["no"] else "",
                                    s["baslik"]),
                          s["statu"], s["not"], s["aksiyon"] or BOS_DEGER]
                         for s in tablo]}


def _blok_ekle(bolum, yeni, bos_blogu_at=True):
    """Ikinci gecte uretilen bloklari bolume ekler.

    `metin` duzenlenmis bolumde DOKUNULMAZ: o alan duzenleme kutusunun
    kaynagi; otomatik tabloyu icine yazarsak kullanici bir sonraki
    kaydedisinde platformun tablosunu kendi metni sanip dondururdu."""
    yeni = [b for b in yeni if b]
    if not yeni:
        return
    mevcut = bolum["bloklar"]
    if bos_blogu_at:
        mevcut = [b for b in mevcut if b.get("tur") != "bos"]
    bolum["bloklar"] = mevcut + yeni
    if not bolum["duzenlendi"]:
        bolum["metin"] = duz_metin(bolum["bloklar"])


def _tabloya_satir(bolum, kolonlar, satir):
    """Bolumun ilk uygun tablosuna satir EKLER; yoksa yeni tablo acar.

    NEDEN: "Doküman durumu" satiri statu tablosuna bagli oldugu icin ancak
    ikinci gecte uretilebiliyor. Ayri bir blok olarak eklenince kunyenin
    sonunda BASLIKSIZ, tek satirlik ikinci bir "Alan | Değer" tablosu
    olusuyordu - ekranda kopuk, Word'de de oyle. Satir asil kunye
    tablosuna ait; oraya yaziyoruz.

    Duzenlenmis bolumde hicbir sey yapilmaz: o bolumun govdesi artik
    kullanicinin metni."""
    if bolum["duzenlendi"]:
        return False
    for blok in bolum["bloklar"]:
        if blok.get("tur") == "tablo" and blok.get("kolonlar") == kolonlar:
            blok["satirlar"] = list(blok["satirlar"]) + [list(satir)]
            bolum["metin"] = duz_metin(bolum["bloklar"])
            return True
    return False


def dokuman(durum):
    """Teknik Model Dokumani govdesi: kunye + 20 numarali bolum + ek.

    Verisi olmayan bolum ATLANMAZ; "bos" blogu ile yerinde durur ve
    statusu bunu soyler."""
    durum = durum or {}
    duzenli = duzenlemeler(durum)

    bolumler = [_bolum(durum, a, no, b, k, duzenli.get(a))
                for a, no, b, k in BOLUM_TANIMLARI]
    harita = {b["anahtar"]: b for b in bolumler}

    # 1. ve 20. bolumun govdesi DIGER bolumlerin statusunden uretilir;
    # eksik kalabilecek bir parcalari yok, bu yuzden statuleri her zaman
    # TAMAM. (Kullanici duzenlediyse zaten TAMAM.)
    for anahtar in ("yonetici_ozeti", "teslim"):
        bolum = harita[anahtar]
        if not bolum["duzenlendi"]:
            bolum["statu"] = TAMAM
            bolum["statu_notu"] = "Platform tarafından üretildi."
            bolum["eksikler"] = []

    tablo = _statu_tablosu(bolumler)
    bloker = [s for s in tablo if s["statu"] == BLOKER]
    eksik_sayisi = sum(1 for s in tablo if s["statu"] == EKSIK)
    kismi_sayisi = sum(1 for s in tablo if s["statu"] == KISMI)
    hazir = not bloker
    damga = DAMGA_HAZIR if hazir else DAMGA_TASLAK

    # --- ikinci gec: statu tablosuna bagimli bloklar -----------------------
    # Satir kunyenin ASIL tablosuna girer. Tablo bulunamazsa (bicim
    # degistiyse) eski davranisa duseriz: ayri blok, ama hic yazmamaktan
    # iyi - teslim damgasi kunyede gorunmeli.
    if not _tabloya_satir(harita["kunye"], ["Alan", "Değer"],
                          ["Doküman durumu", damga]):
        _blok_ekle(harita["kunye"],
                   [_alan_tablosu([("Doküman durumu", damga)])],
                   bos_blogu_at=False)

    _blok_ekle(harita["yonetici_ozeti"], [
        _statu_blogu(tablo, "Bölüm bazında hazırlık durumu"),
        _p(_teslim_karari(len(bloker), eksik_sayisi, kismi_sayisi))])

    _blok_ekle(harita["teslim"], [
        _p(damga, kalin=True),
        _statu_blogu(tablo, "Bölüm bazında hazırlık durumu"),
        _p(_teslim_karari(len(bloker), eksik_sayisi, kismi_sayisi))])

    # 18. bolum: platformun KENDI buldugu bloker ve eksikler ayri bir blok
    # olarak eklenir - kullanicinin yazdigi ezilmez. Her bloker bir model
    # riskidir; risk bolumunde gorunmezse validator onu aramak zorunda
    # kalir. Kullanici cagrisinin ("bu bölümü siz yazmalısınız") silinmemesi
    # icin bos blogu KORUNUR.
    acik = [s for s in tablo if s["statu"] in (BLOKER, EKSIK)]
    if acik:
        _blok_ekle(harita["kisit"],
                   [_statu_blogu(acik,
                                 "Platformun bulduğu açık maddeler "
                                 "(otomatik - her bloker bir model riskidir)")],
                   bos_blogu_at=False)

    eksik_bolum = [b["anahtar"] for b in bolumler
                   if b["anahtar"] in KULLANICI_BOLUMLERI
                   and not b["duzenlendi"]]

    return {
        "baslik": BASLIK,
        "olusturma": _bicimli_zaman(_olusturma(durum)),
        "bolumler": bolumler,
        "statu_tablosu": tablo,
        "teslim_durumu": TESLIM_HAZIR if hazir else TESLIM_TASLAK,
        "teslim_damgasi": damga,
        "bloker_sayisi": len(bloker),
        "eksik_sayisi": eksik_sayisi,
        "kismi_sayisi": kismi_sayisi,
        # Eski alanlar KORUNUR: on yuz ve testler bunlari okuyor.
        "eksik_bolum": eksik_bolum,
        "hazir_mi": hazir,
    }


def _teslim_karari(bloker, eksik, kismi):
    """20. (ve 1.) bolumun kapanis paragrafi."""
    if bloker:
        return ("Bu doküman bu hâliyle validasyon teslimi için FİNAL "
                "olarak gönderilmemelidir: %s bölümde teslimi engelleyen "
                "eksik var. Kapı yalnızca etikettedir; çalışma devam "
                "edebilir ve Word çıktısı alınabilir, ancak doküman "
                "TASLAK sayılır." % _sayi(bloker))
    kalan = eksik + kismi
    if kalan:
        return ("Teslimi engelleyen bölüm yok; teslim paketi validasyona "
                "gönderilebilir. Kalan %s bölüm eksik ya da kısmidir ve "
                "validasyon sürecinde tamamlanmalıdır." % _sayi(kalan))
    return ("Teslimi engelleyen bölüm yok ve bütün bölümlerin beklenen "
            "içeriği tamamlanmış görünüyor; teslim paketi eksiksizdir.")


# ===========================================================================
# DUZENLEME VE KALICILIK
# ===========================================================================
def _dokuman_kaydi(durum):
    kayit = durum.get("dokuman")
    if not isinstance(kayit, dict):
        kayit = {}
    if not isinstance(kayit.get("duzenlemeler"), dict):
        kayit["duzenlemeler"] = {}
    if not isinstance(kayit.get("olusturma"), str) or not kayit["olusturma"]:
        kayit["olusturma"] = datetime.datetime.now().isoformat(
            timespec="seconds")
    durum["dokuman"] = kayit
    return kayit


def dokuman_bolum_kaydet(durum, anahtar, metin):
    """Bir bolumun kullanici metnini durum'a yazar.

    BOS METIN DUZENLEMEYI SILER ve bolum hesaplanan haline doner; ayri bir
    "sifirla" ucu acmak, ayni isi yapan ikinci bir yol demekti.

    Doner: {"tamam": bool, "bolum": {...}} ya da {"tamam": False, "hata": ...}
    Kaydetmez - cagiran taraf durum_kaydet ile kalici hale getirir."""
    if anahtar not in BOLUM_ANAHTARLARI:
        return {"tamam": False,
                "hata": "Bilinmeyen doküman bölümü: %s" % anahtar}

    kayit = _dokuman_kaydi(durum)
    goc_uygula(durum)
    duzenli = kayit["duzenlemeler"]
    eski = duzenli.get(anahtar)
    eski = eski if isinstance(eski, str) else None

    yeni = metin.strip() if isinstance(metin, str) else ""

    if yeni:
        duzenli[anahtar] = yeni
    else:
        duzenli.pop(anahtar, None)

    # Ayni metin yeniden gonderildi (cift tiklama / yeniden deneme):
    # kutuge ikinci bir satir dusurmuyoruz, islem yine BASARILI sayilir -
    # istenen son durum zaten bu. (bkz. sozluk_calisma.kategori_yaz)
    if (eski or "") != yeni:
        kutuk_mod.degisiklik_dus(durum.get("_oturum_id"), [{
            "ALAN": "dokuman", "ANAHTAR": anahtar,
            "ESKI": eski, "YENI": yeni or None,
            "KAYNAK": "ozet sayfasi"}])

    # Bolum TAM DOKUMANDAN alinir: 18. bolumun risk tablosu ve 1./20.
    # bolumun statu tablosu butun bolumlerin statusune bagli; tek bolumu
    # tek basina uretmek, ekranda eskimis bir tablo birakirdi.
    govde = dokuman(durum)
    bolum = next((b for b in govde["bolumler"] if b["anahtar"] == anahtar),
                 None)
    # TESLIM OZETI DE DONER: tam govde zaten uretildi, teslim durumu da
    # onunla birlikte hesaplandi. Gondermeyince on yuz son blokeri kapatan
    # kaydin ardindan "Bloker: 0" yazarken damgayi hala "TASLAK" gosteriyor
    # ve kullanici dokumani tazeleyene kadar yanlis okuyordu. Bolumleri
    # tekrar gondermiyoruz; yalniz kok ozet alanlari.
    return {"tamam": True, "bolum": bolum,
            "teslim": {a: govde.get(a) for a in TESLIM_OZET_ALANLARI}}


# ===========================================================================
# WORD CIKTISI
# ===========================================================================
DOSYA_ADI = "model_gelistirme_dokumani.docx"


def dokuman_word(durum):
    """Dokumanin .docx karsiligi (ham baytlar).

    Bolum numarasi basliga YAZILIR: ekranda numara ayri bir sutunda
    duruyor, Word'de o sutun yok ve numarasiz basliklar sirayi
    kaybettiriyordu. Kunye ve Ek numarasizdir, basligi oldugu gibi gider.

    Damga BASLIK SAYFASININ hemen altinda kalin bir paragraftir ve 20.
    bolumde tekrarlanir: dokumanin ilk sayfasini goren de son bolumunu
    okuyan da taslak mi final mi oldugunu bilmeli."""
    govde = dokuman(durum)
    bloklar = [{"tur": "belge_basligi", "metin": govde["baslik"]},
               _p("Oluşturma: %s" % govde["olusturma"]),
               _p(govde["teslim_damgasi"], kalin=True),
               _p("Bloker: %s · Eksik: %s · Kısmi: %s"
                  % (_sayi(govde["bloker_sayisi"]),
                     _sayi(govde["eksik_sayisi"]),
                     _sayi(govde["kismi_sayisi"])))]

    if govde["eksik_bolum"]:
        eksik_adlari = [_bolum_etiketi(b) for b in govde["bolumler"]
                        if b["anahtar"] in govde["eksik_bolum"]]
        bloklar.append(_p("Kullanıcının yazması gereken ve hâlâ boş olan "
                          "bölümler: %s." % ", ".join(eksik_adlari)))

    for bolum in govde["bolumler"]:
        bloklar.append({"tur": "baslik", "metin": _bolum_etiketi(bolum)})
        if bolum["statu"] != TAMAM:
            bloklar.append(_p("Statü: %s - %s"
                              % (bolum["statu"], bolum["statu_notu"])))
        bloklar.extend(bolum["bloklar"])
        if bolum["eksikler"]:
            # Beslik bir blok turu EKLENMEZ: baslik paragraf, maddeler
            # liste olarak gider. Ekran da ayni iki turu ciziyor.
            bloklar.append(_p("Tamamlanması gerekenler:"))
            bloklar.append({"tur": "liste", "ogeler": list(bolum["eksikler"])})

    return docx_yaz.belge_yaz(govde["baslik"], bloklar)
