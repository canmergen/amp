# -*- coding: utf-8 -*-
"""fe_agent/akis_faz01.py - Faz 01 - Calisma Kurulumu: mod, veri, sozluk, tanimlar, bolme.

akis.py bolundu; bu dosya o bolumun aynisidir.
"""

import datetime
import re
import threading
import uuid
import numpy as np
import pandas as pd
from fe_agent import niyet_kural
from fe_agent import llm as llm_mod
from fe_agent import birlestirme as birl_mod
from fe_agent import sozluk as sozluk_mod
from fe_agent import sozluk_calisma
from fe_agent import tip_donusum
from fe_agent import xlsx_yaz

from fe_agent.akis_metin import (
    ADIM_ADI, KARSILAMA, MOD_ADLARI, MOD_KALIP, MOD_SECENEKLERI, MOD_SIRA)
from fe_agent.akis_durum import (
    BAZ_ADI, LINEAGE_ADI, SOZLUK_ADI, SPLIT_KOLON, TEST_KIMLIK_LIMITI,
    AdimHatasi, _ad_haritasi,
    _dataset_var_mi, _df_oku, _liste, _nerede, _ond,
    _plan_adlari_cevir, _sayi, _yaz, bolme_ayarlari, bolme_hazirla,
    test_donem_anahtari,
    AMP_KLASOR, AMP_SOZLUK_ADI, AMP_SOZLUK_KOLONLARI, AMP_VERI_ADI,
    BOLME_BOLUMLERI, bolme_kaydet, bolme_onerisi, bolme_ozeti,
    hazir_bolme_bul, kolon_ozeti_cikar, metin_yaz, modelleme_df,
    onbellek_temizle, sozluk_orijinal_oku, yeni_durum, amp_sahibi_yaz,
    dataset_yaz, dosya_yaz, sahip_yaz,
)


# Mod degisince KORUNAN anahtarlar: akis konumu, secilen mod ve webapp
# backend'inin oturum alanlari. Digerleri eski moda ait veridir.
_MOD_KORUNAN = ("i", "mod", "_oturum_id", "_tur_no", "_son_cevap", "_gecmis")

# yeni_durum()'da olmayan ama faz fonksiyonlarinin biraktigi gecici izler.
_MOD_GECICI = ("_donemler", "_aciklamasiz", "_dusurulecek", "_soru_gecmis",
               "_onceki_mod", "_mod_onay", "_tanimsiz_oneri",
               "_tanimsiz_oneri_kolonlar", "_dogrulama_karari",
               # Dusurulen donem kolonu ve platformun yazdirdigi tanim
               # kaydi: ikisi de o veri setine ait, mod degisince tablo
               # da degisir.
               "_donem_dusuruldu", "_sozluge_eklenen", "_bolme_mod",
               "_hazir_bolme",
               # Sozluk teyidi eski moda ait bir denetim kaydidir; mod
               # degisince veri seti de sozluk de degisir, damga
               # tasinmamali.
               "teyit")


# Tarih kolonlarini ayirmak icin kullanilan dtype listesi. Kategorik sayisi
# "kolon - sayisal - tarih" olarak hesaplanir; tarih kolonlari eskiden
# kategorik sayiliyordu ve VERI sekmesinde yanlis goruniyordu.
TARIH_TIPLERI = ["datetime64[ns]", "datetimetz"]


def _tarih_kolon_sayisi(df):
    """Veri setindeki tarih/zaman damgasi kolonu adedi."""
    try:
        return int(df.select_dtypes(include=TARIH_TIPLERI).shape[1])
    except Exception:
        return 0


# Bir kolonun ikili olup olmadigina bakmadan once tekil sayisina bakilir:
# 1.042 kolonun her birinde unique() cagirmak pahali, tekil sayisi zaten
# tek seferde cikiyor. Esik 3: {0,1} ve {0,1,NaN} gecsin, digerleri
# taramaya hic girmesin.
IKILI_TEKIL_ESIGI = 3


def _aday_kolonlar(df):
    """(hedef_adaylari, kimlik_adaylari).

    NEDEN FILTRE VAR
      Form uc alana da veri setinin BUTUN kolonlarini oneriyordu.
      1.042 kolonluk bir sette hedef ile kimlik kolonu yer degistirince
      platform bunu bir hata olarak degil, veri kalitesi bulgusu olarak
      raporluyordu: "Hedefin pozitif orani %0,00", "Kimlik kolonunda
      9.998 satir tekrar ediyor". Ikisi de dogruydu ama asil sorun
      secimin kendisiydi. Artik secilemeyen sey hic listelenmiyor.

    HEDEF: yalnizca 0/1. Sinifladirma yapiliyor; sürekli ya da çok
      sınıflı bir kolon hedef olamaz. Kabul edilen: non-null degerler
      kumesi TAM OLARAK {0, 1} (ya da bool dtype). Sabit kolon (hepsi 0)
      KABUL EDILMEZ — modellenecek bir olay yok.

    KIMLIK: yalnizca tam tekrarsiz kolon. nunique(dropna=False) satir
      sayisina esit olmali; bir tek tekrar bile kimligi kimlik olmaktan
      cikarir (ayni kayit iki sete birden dusebilir).

    ADAY BULUNAMAZSA BOS LISTE doner; cagiran taraf o zaman tum kolon
    listesine duser ve NEDENINI yazar (bkz. _tanimlar_formu). Panel
    verisi bir musteri x donem tablosuysa tekrarsiz kolon gercekten
    olmayabilir; kullaniciyi kilitlemek dogru olmaz."""
    try:
        tekil = df.nunique(dropna=False)
    except Exception:
        return [], []

    satir = int(df.shape[0])
    hedef, kimlik = [], []
    for kolon in df.columns:
        ad = str(kolon)
        try:
            n_tekil = int(tekil[kolon])
        except Exception:
            continue

        if satir and n_tekil == satir:
            kimlik.append(ad)

        s = df[kolon]
        try:
            if s.dtype == bool:
                hedef.append(ad)
                continue
            if n_tekil > IKILI_TEKIL_ESIGI:
                continue
            if not pd.api.types.is_numeric_dtype(s):
                continue
            degerler = {float(v) for v in pd.unique(s.dropna())}
            if degerler == {0.0, 1.0}:
                hedef.append(ad)
        except Exception:
            continue

    return hedef, kimlik


# Donem adayligi icin taranan satir sayisi: bicim kontrolu (YYYYMM,
# YYYYMMDD, tarih) icin ornek yeter; 1.042 kolonu tam tabloda cozmek
# pahali. Tekil sayisi tam tablodan.
DONEM_ORNEK_SATIR = 5000


# Aday olmak icin dolu hucrelerin en az bu kadari donem olarak cozulmeli.
DONEM_COZULME_ORANI = 0.95


def _donem_adaylari(df, kimlik=()):
    """Donem kolonu adaylari (kullanici karari: "tek değeri olan gelmemeli,
    kimlik ve hedef gelmemeli, tarih ya da tarihe benzeyen kolon gelmeli").

    Aday olmak icin:
      - en az iki farkli deger (tek donemlik sette donem kolonu anlamsiz)
      - her satirda farkli DEGIL (kimlik kolonu / zaman damgasi degil)
      - taninan bir donem bicimi: tarih tipi, YYYYMM (202401), YYYYMMDD
        (20240115) ya da tarihe cevrilebilen metin (birlestirme._donem_coz
        ile AYNI kural; zamansal bolme de bu bicimleri cozuyor).
    0/1 hedef kolonlari bicime uymadigi icin zaten elenir."""
    try:
        tekil = df.nunique(dropna=False)
    except Exception:
        return []
    satir = int(df.shape[0])
    ornek = df.head(DONEM_ORNEK_SATIR)
    kimlik = set(kimlik or ())
    cikti = []
    for kolon in df.columns:
        ad = str(kolon)
        try:
            n_tekil = int(tekil[kolon])
        except Exception:
            continue
        if n_tekil <= 1 or ad in kimlik or (satir > 1 and n_tekil == satir):
            continue
        try:
            ay, bicim = birl_mod._donem_coz(ornek[kolon])
            dolu = birl_mod.donem_serisi(ornek[kolon]).notna()
            # Tarih cozucusu tek bir tarihe benzer hucrede bile "tarih"
            # diyebiliyor; aday olmak icin dolu hucrelerin neredeyse
            # tamami donem olarak cozulmeli.
            if bicim and dolu.any():
                oran = float(pd.Series(ay)[dolu.to_numpy()].notna().mean())
                if oran < DONEM_COZULME_ORANI:
                    bicim = None
        except Exception:
            bicim = None
        if bicim:
            cikti.append(ad)
    return cikti


def _donem_adaylarini_hazirla(durum):
    """Profilde donem adaylari yoksa BIR KEZ hesaplayip yazar; profili doner.

    Bu liste veri seti secilirken (_temel_profil) cikariliyor. O surumden
    ONCE baslamis calismalarin profilinde yok; eskiden bu durumda form tum
    kolonlara dusuyordu ve kimlik, hedef, tutar kolonlari donem olarak
    secilebiliyordu (kullanici bildirimi). Artik eksikse tablodan
    hesaplaniyor. Okuma onbellekten gelir; tablo okunamazsa liste bos
    kalir ve form "aday bulunamadi" der - tum kolonlara DUSULMEZ."""
    p = durum.get("profil") or {}
    if isinstance(p.get("donem_adaylari"), list):
        return p
    try:
        df = modelleme_df(durum)
        kimlik = p.get("kimlik_adaylari")
        if not isinstance(kimlik, list):
            _hedef, kimlik = _aday_kolonlar(df)
        p["donem_adaylari"] = _donem_adaylari(df, kimlik)
    except Exception:
        p["donem_adaylari"] = []
    durum["profil"] = p
    return p


def _temel_profil(durum, df):
    """Veri seti secildiginde BIR KEZ hesaplanan temel sayilar.

    kurulum_plan (Mod A/C) ve veri_sec_plan (Mod B) ayni tabloyu zaten
    bastan sona okuyor; duplicate ve tarih sayimi ayni okumadan
    turetildigi icin ek maliyet getirmiyor. Sonuclar durum["profil"]
    icine yazilir; Analiz Merkezi'ndeki VERI sekmesi buradan beslenir.
    """
    p = durum.get("profil") or {}
    p.update({
        "satir": int(df.shape[0]), "kolon": int(df.shape[1]),
        "kolon_baslangic": int(df.shape[1]),
        "sayisal": int(df.select_dtypes(include=[np.number]).shape[1]),
        "tarih": _tarih_kolon_sayisi(df),
        "duplicate": int(df.duplicated().sum()),
        # Feature tablosu bu ozetten uretiliyor; tablo zaten okunmusken
        # cikariliyor ki her /analiz cagrisinda yeniden okunmasin.
        "kolon_ozet": kolon_ozeti_cikar(df),
    })
    # Modelleme tanimlari formunun acilir listeleri. Tablo ZATEN elde
    # oldugu icin burada cikariliyor; form acilirken veri setini yeniden
    # okumak 1.042 kolonluk sette gereksiz bir tur daha demekti.
    hedef_aday, kimlik_aday = _aday_kolonlar(df)
    p["hedef_adaylari"] = hedef_aday
    p["kimlik_adaylari"] = kimlik_aday
    p["donem_adaylari"] = _donem_adaylari(df, kimlik_aday)
    _kimlik_duplicate(durum, df, p)
    durum["profil"] = p
    return p


def _kimlik_duplicate(durum, df, p):
    """Kimlik kolonu belliyse ayrica kimlik bazli tekrar sayisi.

    "Satirin tamami ayni" ile "ayni musteri iki kere" farkli sorunlardir;
    ikincisi panelde ayri satir olarak gosterilir."""
    kimlik = (durum.get("meta") or {}).get("id")
    if kimlik and kimlik in df.columns:
        try:
            p["duplicate_kimlik"] = int(df.duplicated(subset=[kimlik]).sum())
        except Exception:
            pass


def _mod_sifirla(durum):
    """Mod GERCEKTEN degistiginde eski moda ait veri/analiz alanlarini
    sifirlar. Aksi halde Mod C'de birlestirilen tablo, Mod A'ya gecince
    ust seritte gorunmeye devam ediyordu.

    Bilinmeyen anahtarlar (webapp backend'inin kendi alanlari) AYNEN
    korunur; yalnizca bu akisin urettigi alanlar temizlenir."""
    taze = yeni_durum()
    for anahtar, deger in taze.items():
        if anahtar in _MOD_KORUNAN:
            continue
        durum[anahtar] = deger
    for anahtar in _MOD_GECICI:
        durum.pop(anahtar, None)
    onbellek_temizle()


# Mod degistirmek, o ana kadar yapilan her seyi silmek demek: secili veri
# seti, sozluk, profil, SFA, uretilen degiskenler. Eskiden bu tek tikla ve
# SESSIZCE oluyordu — yanlis karta dokunan analist calismasini geri
# alamadan kaybediyordu. Artik arada bir onay var.
MOD_ONAY_SORUSU = ("Mod değiştirirseniz seçili veri seti, sözlük ve yapılmış "
                   "analizler sıfırlanır. Devam edilsin mi?")

MOD_ONAY_SECENEKLERI = [
    {"deger": "evet", "baslik": "Evet, sıfırla",
     "aciklama": "Yeni moda geç; mevcut veri seti, sözlük ve analizler "
                 "silinsin."},
    {"deger": "hayır", "baslik": "Hayır, vazgeç",
     "aciklama": "Mod değişmesin; çalışma olduğu gibi kalsın."},
]


def _mod_onay_istemi(eski_mod, yeni_mod, gecis=True):
    """Onay istemi. gecis=False ise YALNIZCA soru doner.

    NEDEN IKI BICIM: akis_sohbet._mesaj_isle, "bu mesaj bu adima ait
    bilgi icermiyor mu?" sorusunu girdi fonksiyonunu BOS mesajla ikinci
    kez cagirip metinleri karsilastirarak cevapliyor. Iki metin ayni
    cikarsa mesaj serbest soru sayilip dil modeline gidiyor. Onay
    sorusu her iki cagrida da ayni metni dondurdugu icin kullanicinin
    mod secimi soruyu dogurmak yerine LLM'e dusuyordu. Gecis satiri
    (ESKI → YENI) yalnizca kullanicinin bir SECIM yaptigi cagrida
    ekleniyor; ekranin bos-mesaj istemi sade soru."""
    if not gecis:
        return MOD_ONAY_SORUSU
    return ("%s → %s\n\n%s"
            % (MOD_ADLARI.get(eski_mod, eski_mod),
               MOD_ADLARI.get(yeni_mod, yeni_mod), MOD_ONAY_SORUSU))


def _mod_onay_bekle(durum, eski_mod, yeni_mod, gecis=True):
    durum["_mod_onay"] = yeni_mod
    durum["_secenekler"] = MOD_ONAY_SECENEKLERI
    return False, _mod_onay_istemi(eski_mod, yeni_mod, gecis)


def _mod_yerlestir(durum, yeni_mod):
    durum["mod"] = yeni_mod
    durum["_onceki_mod"] = yeni_mod
    durum["_secenekler"] = []
    durum.pop("_mod_onay", None)


def mod_girdi(durum, mesaj):
    m = MOD_KALIP.search(mesaj or "")
    bekleyen_mod = durum.get("_mod_onay")
    # Onay sorulurken mod alani None'a cekilmis olabilir (geri donus);
    # "hangi moddan cikiyoruz" bilgisi _onceki_mod'da duruyor.
    eski_mod = durum.get("mod") or durum.get("_onceki_mod")

    # --- Mod degisikligi onayi bekleniyor --------------------------------
    if bekleyen_mod:
        if m:
            # Kullanici onay yerine baska bir mod kartina dokundu.
            secilen = MOD_SIRA.get(m.group(2).upper(), m.group(2).upper())
            if secilen == eski_mod:
                # Eski moda geri dondu: silinecek bir sey yok, onay gereksiz.
                _mod_yerlestir(durum, secilen)
                return True, None
            return _mod_onay_bekle(durum, eski_mod, secilen)

        karar = niyet_kural.coz(mesaj or "")["aksiyon"]
        if karar == "onay":
            _mod_sifirla(durum)
            _mod_yerlestir(durum, bekleyen_mod)
            return True, None
        if karar == "ret":
            # Vazgecildi: HICBIR SEY silinmedi, eski mod geri konuyor.
            durum.pop("_mod_onay", None)
            if eski_mod:
                durum["mod"] = eski_mod
                durum["_onceki_mod"] = eski_mod
            durum["_secenekler"] = MOD_SECENEKLERI
            return False, ("Mod değişikliğini iptal ettim; çalışmanız olduğu "
                           "gibi duruyor.\n\nBaşka bir seçim yapmak "
                           "isterseniz aşağıdan devam edebilirsiniz.")
        # Ne onay ne ret: soruyu tekrar sor. Bos mesaj ekran istemidir.
        return _mod_onay_bekle(durum, eski_mod, bekleyen_mod,
                               gecis=bool((mesaj or "").strip()))

    if not m:
        # Geri donuldugunde eski secim silinsin; faz agaci sifirlanir.
        # Hangi moddan gelindigi _onceki_mod'da saklanir: kullanici baska
        # bir mod secerse eski moda ait veri temizlenebilsin.
        if durum.get("mod"):
            durum["_onceki_mod"] = durum["mod"]
        durum["mod"] = None
        durum["_secenekler"] = MOD_SECENEKLERI
        # ADIMIN METNI KARSILAMA'DIR.
        # Once "Nereden başlayalım?" donuyordu: ekranda uc secenek karti
        # ve "ÇALIŞMA BAŞLANGICI" basligi varken ayni soruyu ikinci kez
        # sormak oluyordu. Sonra bos donduruldu, bu sefer geri donuste
        # secenekler cerceve metni olmadan tek basina kaldi.
        # Doğrusu: bu adimin metni KARSILAMA. Ilk acilista da geri
        # donuste de AYNI metin cikar ve TEK yerden gelir
        # (backend._karsilama_govdesi artik bu donusu kullaniyor,
        # KARSILAMA'yi ayrica eklemiyor; yoksa ilk ekranda iki kez
        # basiliyordu).
        return False, KARSILAMA

    secim = m.group(2).upper()
    yeni_mod = MOD_SIRA.get(secim, secim)

    if eski_mod and eski_mod != yeni_mod:
        # _mod_sifirla DOGRUDAN CAGRILMAZ: once onay.
        return _mod_onay_bekle(durum, eski_mod, yeni_mod)

    _mod_yerlestir(durum, yeni_mod)
    return True, None

def mod_uygula(durum):
    """Mod secildikten sonra EK METIN YOK — dogrudan sonraki adima gecilir.

    Burada eskiden secilen modu tekrar anlatan, uretilecek dataset adlarini
    sayan bir paragraf donuyordu. Kullanicinin az once tikladigi kartin
    aciklamasini bir kez daha okutuyordu ve asil istenen sey — secim formu —
    o paragrafin altinda kaliyordu. Cikti ne uretilecegini degil, sonraki
    adimin sorusunu gostermeli.

    MODELLEME_BAZ ve MODELLEME_SOZLUK yine her zaman uretiliyor; uretildikleri
    adimda zaten adlariyla raporlaniyorlar."""
    return ""

def mod_plan(durum):
    """OLU KOD — su an hicbir yerden CAGRILMIYOR.

    Baslangic secimi otomatik adim oldugu icin ayri onay plani yok;
    ADIMLAR kaydi bir plan fonksiyonu bekledigi icin ozeti dondurur.
    akis_sohbet._adima_gir() plani yalnizca girdi fonksiyonu True
    dondugunde cagiriyor; mod_girdi ise bos mesajla ASLA True donmuyor
    (mesajda mod deseni yoksa mod=None yapip False donuyor). Dolayisiyla
    bu fonksiyona giden bir yol yok.

    KALDIRILMADI: akis_kayit.ADIMLAR["mod"]["plan"] hala buraya referans
    veriyor. Kaydi duzenleyen taraf ya bu referansi mod_uygula'ya cevirip
    fonksiyonu silmeli ya da adimi 'otomatik' olmayan bir adima
    cevirmelidir."""
    return mod_uygula(durum)

# ===========================================================================
# ADIM 1.2A — HAM TABLOLAR  (Mod A)
# ===========================================================================
# Tablo adi deseni: Turkce harf (\w + re.UNICODE), rakam, alt tire, nokta
# ve tire. Eski desen ([A-Za-z0-9_.]) Turkce karakterli ve tireli adlari
# SESSIZCE atiyordu; kullanici iki tablo secse de soru yeniden aciliyordu.
TABLO_ADI_KALIP = re.compile(r"^[\w.\-]+$", re.UNICODE)


KAYNAK_TABLO_METNI = (
    "**Veri setini oluşturacak kaynak tabloları seçin.**\n"
    "Müşteri, ürün ve işlem tabloları gibi henüz birleştirilmemiş "
    "tabloların tamamını ekleyin. Seçiminizden sonra tabloların "
    "şemalarını inceleyip bir birleştirme planı önereceğim: hangi tablonun "
    "iskelet olacağı, diğerlerinin hangi anahtarla bağlanacağı ve işlem "
    "tablolarından hangi dönemsel toplamaların üretileceği. Plan, "
    "onayınızdan önce uygulanmaz.")


def ham_veri_girdi(durum, mesaj, yeniden_sor=False):
    metin = (mesaj or "").strip()
    # "tablolar: ..." oneki varsa kullanici ACIKCA tablo listesi veriyor
    # demektir; serbest bir cumleyi tablo listesi sanip uyari basmayalim.
    acik_liste = bool(re.match(r"^\s*tablolar\s*[:=]", metin, flags=re.I))
    ham = re.sub(r"^\s*tablolar\s*[:=]\s*", "", metin, flags=re.I)
    parcalar = [a.strip() for a in re.split(r"[,\n;]+", ham) if a.strip()]
    adaylar = [a for a in parcalar if TABLO_ADI_KALIP.match(a)]
    kabul_edilmeyen = [a for a in parcalar if not TABLO_ADI_KALIP.match(a)]
    if not (acik_liste or adaylar):
        kabul_edilmeyen = []      # serbest metin: adim girdisi degil

    # Kabul edilmeyen ad varsa gecerli olanlarla sessizce DEVAM ETMIYORUZ;
    # kullaniciya hangi adin neden dustugunu soyleyip secimi tazeletiyoruz.
    if yeniden_sor or kabul_edilmeyen or len(adaylar) < 2:
        durum["_secim_alani"] = {
            "tip": "liste",
            "baslik": "Kaynak tablolar",
            "aciklama": "En az iki tablo seçin; seçim sırası önemli değil.",
            "etiket": "Kaynak tablo ara",
            # Dugme etiketi Baslik Buyuk Harfi: her kelime buyuk baslar,
            # baglac ve edatlar ("ve, veya, ile, icin, mi, da, de") kucuk
            # kalir. Ayni kural butun rozet ve dugmelerde gecerli.
            "buton": "Tabloları Onayla",
            "min": 2,
            "sablon": "tablolar: {liste}",
            "secili": adaylar or list(durum.get("ham_tablolar") or []),
        }
        # Adimin metni KARSILAMA ile ayni ozende: ne istendigi ve
        # ardindan ne olacagi. Kisa "Hangi tabloları birleştirelim?"
        # sorusu ne yapilacagini anlatmiyordu (kullanici geri bildirimi).
        soru = KAYNAK_TABLO_METNI
        if kabul_edilmeyen:
            # Sessizce atmak yerine nedenini soyle: eskiden Turkce karakterli
            # ya da tireli adlar hicbir aciklama olmadan dusuyordu.
            soru = ("Şu adları tablo adı olarak kabul edemedim: %s\n\n"
                    "Tablo adında yalnızca harf, rakam, alt tire, nokta ve "
                    "tire olabilir.\n\n%s"
                    % (", ".join(kabul_edilmeyen), soru))
        return False, soru

    eksik = [a for a in adaylar if not _dataset_var_mi(a)]
    if eksik:
        return False, ("Erişemediğim tablolar: %s\n\n"
                       "Adlarını kontrol eder misiniz?" % ", ".join(eksik))

    durum["ham_tablolar"] = adaylar
    durum["_secim_alani"] = None
    return True, None

def ham_veri_plan(durum):
    satirlar = []
    toplam_kolon = 0
    for ad in durum["ham_tablolar"]:
        try:
            df = _df_oku(ad, limit=200)
            satirlar.append("  %s\n      %s kolon"
                            % (ad, _sayi(df.shape[1])))
            toplam_kolon += int(df.shape[1])
        except Exception as e:
            satirlar.append("  %s\n      okunamadı: %s" % (ad, str(e)[:60]))

    return ("%s tablo seçildi, toplam %s kolon:\n\n%s\n\n"
            "Şimdi bu tabloların şemalarını yapay zekâya göstereceğim. "
            "Hangisinin iskelet olacağını, diğerlerinin hangi anahtarla "
            "bağlanacağını ve işlem tablolarından hangi toplamaların "
            "üretileceğini önerecek.\n\n"
            "Planı çıkarayım mı?"
            % (_sayi(len(durum["ham_tablolar"])), _sayi(toplam_kolon),
               "\n\n".join(satirlar)))

def ham_veri_uygula(durum):
    return "Tablolar kaydedildi."

# ===========================================================================
# ADIM 1.3A — BIRLESTIRME PLANI  (Mod B ve D)   <-- LLM
# ===========================================================================
# Sonuc iki yere yazilir (ad SABIT: MODELLEME_BAZ, kullanici degistiremez):
#   1) calismanin kendi klasoru: PROJE_HAFIZASI/v3/MODELLEME_BAZ.csv
#      -> calismanin KALICI kopyasi; baska calisma ezemez.
#   2) akistaki MODELLEME_BAZ veri seti -> sonraki fazlar ve Dataiku
#      senaryolari buradan okur. Veri seti ORTAK oldugu icin sahibi
#      kaydedilir; baska calisma uzerine yazarsa bu calisma (1)'i okur.


def birlestirme_plan(durum):
    # Gercek semalar: anahtar = tam dataset adi
    semalar = {}
    for ad in durum["ham_tablolar"]:
        try:
            semalar[ad] = list(_df_oku(ad, limit=50).columns)
        except Exception:
            continue

    if len(semalar) < 2:
        durum["birlestirme"] = {}
        return ("Seçilen tabloların en az ikisini okuyamadım. Önceki adıma "
                "dönüp tablo seçimini gözden geçirir misiniz?")

    # LLM'e kisa adla gonderiyoruz: uzun proje onekleri hem baglami sisiriyor
    # hem de model oneki atip gecersiz ad uretebiliyor.
    kisa_to_tam, tam_to_kisa = _ad_haritasi(list(semalar.keys()))
    llm_semalar = {tam_to_kisa[t]: k for t, k in semalar.items()}

    # llm.birlestirme_plan_oner artik (plan, hata) donuyor. Hata YUTULMAZ:
    # kullaniciya gosterilir ve adim ilerlemez.
    ham_plan, llm_hata = llm_mod.birlestirme_plan_oner(
        llm_semalar, meta=durum.get("meta", {}))

    if llm_hata or not ham_plan:
        durum["birlestirme"] = {}
        return ("Tabloları inceledim ama kullanılabilir bir birleştirme planı "
                "çıkaramadım.\n\n  Sebep: %s\n\n"
                "Önceki adıma dönüp tablo seçimini değiştirebilirsiniz."
                % (llm_hata or "Model tanımadığı tablo adları önerdi."))

    # Plani gercek adlara cevirip GERCEK semalara karsi dogruluyoruz
    ham_plan = _plan_adlari_cevir(ham_plan, kisa_to_tam)
    plan, hatalar = birl_mod.dogrula(ham_plan, semalar)

    if plan is None:
        durum["birlestirme"] = {}
        return ("Plan doğrulamayı geçemedi:\n%s\n\n"
                "Önceki adıma dönebilirsiniz."
                % "\n".join("  • %s" % h for h in hatalar[:8]))

    durum["birlestirme"] = {"plan": plan}

    uyari = ""
    if hatalar:
        # birl_mod.dogrula gecersiz pencereli toplamalari plandan CIKARIYOR;
        # kullanici neyin dustugunu gormeli.
        uyari = "\n\n%s" % _liste(
            "Plandan çıkarıldı (doğrulamayı geçemedi):", hatalar, 8)

    return ("Birleştirme planı hazır:\n\n%s%s\n\n"
            "ÖNEMLİ: POINT-IN-TIME KURALI\n"
            "İşlem tablolarından toplama yaparken yalnızca gözlem döneminden "
            "ÖNCEKİ kayıtları kullanıyorum. Gözlem ayının kendisi dahil "
            "değil. Aksi halde model geleceği görür ve gerçekte olmayan bir "
            "performans gösterir.\n\n"
            "Planı uygulayayım mı?"
            % (birl_mod.plan_metni(plan), uyari))

def birlestirme_uygula(durum):
    plan = (durum.get("birlestirme") or {}).get("plan")
    if not plan:
        return "Uygulanacak plan yok."

    baz, kutuk, ozet = birl_mod.calistir(plan, lambda ad: _df_oku(ad))

    # Hedef veri seti yoksa write_with_schema patliyordu ve o ana kadarki
    # tum hesap kayboluyordu. Once ozet/kutuk durumda saklanir, tablo CSV
    # yedegine alinir, sonra anlasilir hata verilir.
    durum["birlestirme"]["ozet"] = ozet
    lineage_yazildi, lineage_yedek = _yaz(LINEAGE_ADI, kutuk, "/lineage.csv")
    durum["birlestirme"]["lineage"] = lineage_yazildi

    ad = BAZ_ADI
    kopya = _amp_yolu(durum, ad)
    durum["birlestirme"]["dosya"] = kopya if dosya_yaz(kopya, baz) else None
    if not dataset_yaz(ad, baz):
        durum["veri_seti"] = None
        durum["birlestirme"]["dataset"] = None
        kayit = ("PROJE_HAFIZASI%s dosyasına kaydettim"
                 % kopya if durum["birlestirme"]["dosya"]
                 else "çalışma klasörüne de yazamadım")
        raise AdimHatasi(
            "Birleştirme hesaplandı ama sonucu %s veri setine yazamadım; "
            "büyük olasılıkla akışta bu adda bir veri seti yok.\n\n"
            "Tabloyu %s; köken kütüğü %s.\n\n"
            "Dataiku akışında %s adında bir veri seti oluşturup adımı "
            "yeniden çalıştırın."
            % (ad, kayit, _nerede(lineage_yazildi, lineage_yedek), ad))

    durum["veri_seti"] = ad
    durum["birlestirme"]["dataset"] = ad
    sahip_yaz(ad, durum)
    onbellek_temizle()

    p = durum.get("profil") or {}
    p.update({
        "satir": ozet["satir"],
        "kolon": ozet["kolon"],
        "kolon_baslangic": ozet["kolon"],
        "sayisal": int(baz.select_dtypes(include=[np.number]).shape[1]),
        "tarih": _tarih_kolon_sayisi(baz),
        "duplicate": int(baz.duplicated().sum()),
        # Mod C'de veri seti burada olusuyor; feature tablosunun kolon
        # ozeti de burada cikmali, yoksa VERI & SOZLUK sekmesi profil
        # adimina kadar bos kalir.
        "kolon_ozet": kolon_ozeti_cikar(baz),
    })
    _kimlik_duplicate(durum, baz, p)
    durum["profil"] = p

    # Mod B: kaynak sozluklerden nihai sozluk. Ayri bir adim DEGIL: kaynak
    # sozlukler zaten secildi, kullanicinin verecegi bir karar yok.
    sozluk_not = ""
    if durum.get("mod") == "B":
        sozluk_not = _mod_b_sozlugu(durum, baz, kutuk)

    # birl_mod.calistir ozeti: kismi sonucta kullanici ACIKCA uyarilir.
    hata_not = ""
    if ozet.get("hatalar"):
        hata_not += "\n\n%s" % _liste("Uygulanamayan kaynaklar:",
                                      ozet["hatalar"], 6)
    if ozet.get("uyarilar"):
        hata_not += "\n\n%s" % _liste("Uyarılar:", ozet["uyarilar"], 8)

    if ozet.get("kismi"):
        baslik = ("UYARI: BİRLEŞTİRME KISMİ TAMAMLANDI\n%s\n"
                  "%s kaynağın %s tanesi uygulandı; tablo eksik kolonlarla "
                  "üretildi. Devam etmeden önce eksik kaynakları gözden "
                  "geçirmenizi öneririm.\n"
                  % (ozet.get("durum", ""),
                     _sayi(ozet.get("kaynak_sayisi", 0)),
                     _sayi(ozet.get("basarili_kaynak", 0))))
    else:
        baslik = "Birleştirme tamamlandı. %s\n" % ozet.get("durum", "")

    kopya_satiri = ("  Çalışma kopyası   : PROJE_HAFIZASI%s\n"
                    % durum["birlestirme"]["dosya"]
                    if durum["birlestirme"].get("dosya") else "")
    return ("%s\n"
            "  Modelleme tablosu : %s\n"
            "%s"
            "                      %s satır × %s kolon\n"
            "  İskeletten        : %s kolon\n"
            "  Eklenen           : %s kolon  (%s tanesi point-in-time)\n"
            "  Kaynak sayısı     : %s tablo  (%s başarılı, %s başarısız)\n\n"
            "Her kolonun hangi tablodan, hangi anahtarla ve hangi pencereyle "
            "geldiğini köken kütüğüne yazdım (%s); istediğiniz zaman "
            "denetleyebilirsiniz.%s"
            % (baslik, ad, kopya_satiri, _sayi(ozet["satir"]), _sayi(ozet["kolon"]),
               _sayi(ozet["baslangic_kolon"]), _sayi(ozet["eklenen_kolon"]),
               _sayi(ozet["pit_kolon"]), _sayi(ozet["kaynak_sayisi"]),
               _sayi(ozet.get("basarili_kaynak", 0)),
               _sayi(ozet.get("basarisiz_kaynak", 0)),
               _nerede(lineage_yazildi, lineage_yedek), hata_not)
            + sozluk_not)

# ===========================================================================
# ADIM 1.2B — VERI SETI  (Mod B)
# ===========================================================================
def _veri_sec_formu(durum, veri=None):
    """B secenegi formu. Onceki secim varsa alan dolu gelir."""
    durum["_secim_alani"] = {
        "tip": "form",
        "baslik": "Veri seti",
        "aciklama": "Değişken sözlüğü oluşturulacak veri setini seçin.",
        "buton": "Devam Et",
        "alanlar": [{"ad": "veri_seti", "etiket": "Veri seti",
                     "deger": veri or durum.get("veri_seti") or ""}],
        "sablon": "veri seti {veri_seti}",
    }

def veri_sec_girdi(durum, mesaj, yeniden_sor=False):
    """yeniden_sor=True ('Değiştir'): mevcut degerlerle DOLU form acilir."""
    a = niyet_kural.alanlari_cikar(mesaj) if mesaj else {}
    veri = a.get("veri_seti")

    if yeniden_sor:
        _veri_sec_formu(durum, veri or durum.get("veri_seti"))
        return False, "Hangi veri setiyle çalışalım?"

    if not veri:
        _veri_sec_formu(durum)
        return False, "Hangi veri setiyle çalışalım?"

    if not _dataset_var_mi(veri):
        _veri_sec_formu(durum, veri)
        return False, ("'%s' adında bir tabloya erişemiyorum. "
                       "Adı kontrol edip yeniden seçin." % veri)

    durum["veri_seti"] = veri
    durum["_secim_alani"] = None
    return True, None

def veri_sec_plan(durum):
    df = modelleme_df(durum)
    p = _temel_profil(durum, df)

    return ("Veri setini okudum:\n\n"
            "  %s\n"
            "  %s satır × %s kolon  (%s sayısal, %s kategorik)\n\n"
            "Sözlük bu veri setinden üretilecek. Devam edilsin mi?"
            % (durum["veri_seti"], _sayi(p["satir"]), _sayi(p["kolon"]),
               _sayi(p["sayisal"]), _sayi(p["kolon"] - p["sayisal"])))

def veri_sec_uygula(durum):
    return "Veri seti bağlandı."

# ===========================================================================
# ADIM SOZLUK URETIMI  (Mod A ve B)   <-- LLM
# ===========================================================================
def sozluk_uret_plan(durum):
    p = durum.get("profil") or {}
    return ("Sözlüğü üreteceğim. Her kolon için:\n\n"
            "  • tip, null oranı, tekil değer sayısı\n"
            "  • sayısal kolonlarda dağılım özeti, kategoriklerde en sık "
            "görülen değerler\n"
            "  • bu profile bakarak yazılmış tek cümlelik açıklama\n"
            "  • kategori etiketi (gelir, bakiye, gecikme, davranış …)\n\n"
            "Kimlik benzeri ve uzun metin kolonlarının örnek değerleri "
            "paylaşılmaz; yalnızca kolon adı ve istatistikleri kullanılır.\n\n"
            "%s kolon işlenecek, bu birkaç dakika sürebilir. Başlayalım mı?"
            % _sayi(p.get("kolon", 0)))

def sozluk_uret_uygula(durum):
    df = modelleme_df(durum)

    # NOT: burada ayrica 'haric' listesi VERILMIYOR. Kimlik/PII korumasi tek
    # yerde, sozluk.py icindeki _ornek_guvenli_mi()'de toplanmistir (kolon
    # adi deseni, deger deseni, tekil oran, uzun metin). Eskiden buraya
    # meta["id"] ile bir haric kumesi geciliyordu; sozluk_uret adimi
    # tanimlar adimindan ONCE geldigi icin meta["id"] daima bostu — olu kod.
    profiller = sozluk_mod.profil_cikar(df)

    # llm.sozluk_aciklama_uret artik (aciklamalar, hata) donuyor.
    aciklamalar, llm_hata = llm_mod.sozluk_aciklama_uret(profiller)
    if llm_hata and not aciklamalar:
        # Tek bir aciklama bile uretilemedi: adimi ilerletmiyoruz.
        raise AdimHatasi(
            "Değişken sözlüğü üretilemedi.\n\n  Sebep: %s\n\n"
            "Dil modeline erişim sağlandıktan sonra adımı yeniden "
            "çalıştırabilirsiniz." % llm_hata)

    tablo = sozluk_mod.tablo_olustur(profiller, aciklamalar)

    try:
        yazildi, yedek = _yaz(SOZLUK_ADI, tablo, "/degisken_sozlugu.csv")
    except Exception as e:
        durum["sozluk"], durum["sozluk_yedek"] = None, None
        raise AdimHatasi(
            "Sözlük üretildi ama hiçbir yere yazamadım (%s veri seti yok ve "
            "yedek dosya da yazılamadı: %s). Adımı tamamlamıyorum."
            % (SOZLUK_ADI, str(e)[:140]))

    oz = sozluk_mod.ozet(tablo)

    # Dataset yazilamayip CSV yedegine dusuldugunde durum["sozluk"] None
    # kaliyordu; iki faz sonra _df_oku(None) ile cokuyordu. Yedek yolu da
    # durumda tutuluyor — sozluk okuyan taraf akis_durum.sozluk_oku()
    # uzerinden iki kaynagi da kullanabilir.
    durum["sozluk"] = yazildi or None
    durum["sozluk_yedek"] = yedek
    durum["sozluk_uretim"] = oz

    # Sozluk burada da BAGLANIYOR (Mod B/C). Calisma kopyasi Mod A ile
    # ayni sekilde cikarilmali; aksi halde uretilen sozlukte kategori
    # duzenlenemez ve panel "çalışma kopyası yok" derdi.
    kopya_not = _calisma_kopyasi_kur(durum, tablo)

    p = durum.get("profil") or {}
    p["sozluk_satir"] = oz["toplam"]
    p["eslesen"] = oz["aciklamali"]
    p["kapsam"] = oz["kapsam"]
    durum["profil"] = p

    kirilim = "\n".join("  %-16s %s" % (k, _sayi(v))
                        for k, v in sorted(oz["kategoriler"].items(),
                                           key=lambda x: -x[1])[:8])

    # Kismi LLM hatasi: sonuc kullanilabilir ama sessizce gecilmez.
    llm_not = ("\n\nUYARI: bazı açıklamalar üretilemedi: %s" % llm_hata) \
        if llm_hata else ""
    yedek_not = ("\n\nNOT: %s veri setine yazamadım; sözlük yedek dosyadan "
                 "okunacak." % SOZLUK_ADI) if not yazildi else ""

    return ("Sözlük üretildi: %s kolonun %s tanesi açıklandı (%%%s).\n\n"
            "KATEGORİ DAĞILIMI\n%s\n\n"
            "Tablo %s. Açıklamaları inceleyip düzeltmek isterseniz doğrudan "
            "veri seti üzerinden düzenleyebilirsiniz.%s%s%s"
            % (_sayi(oz["toplam"]), _sayi(oz["aciklamali"]), _ond(oz["kapsam"]),
               kirilim or "  (kategori çıkarılamadı)",
               _nerede(yazildi, yedek), yedek_not, llm_not, kopya_not))

# ===========================================================================
# ADIM 1.2C — VERI VE SOZLUK  (Mod C)
# ===========================================================================
def _kurulum_formu(durum, veri=None, sozluk=None):
    """A secenegi formu. Onceki secim varsa alanlar dolu gelir."""
    durum["_secim_alani"] = {
        "tip": "form",
        "baslik": "Veri seti ve değişken sözlüğü",
        "aciklama": "Analiz edilecek veri setini ve değişken sözlüğünü seçin.",
        # Dugme etiketi SONRAKI EKRANIN adini soylemeli: bu form
        # gonderildiginde "Girdi doğrulama tamamlandı" karti aciliyor.
        # Eski etiket analizin burada basladigini ima ediyordu; oysa
        # analiz bu adimdan cok sonra basliyor.
        "buton": "Girdileri Doğrula",
        "alanlar": [
            {"ad": "veri_seti", "etiket": "Veri seti",
             "deger": veri or durum.get("veri_seti") or ""},
            {"ad": "sozluk", "etiket": "Değişken sözlüğü",
             "deger": sozluk or durum.get("sozluk") or ""},
        ],
        "sablon": "veri seti {veri_seti} ve sözlük {sozluk}",
    }

def kurulum_girdi(durum, mesaj, yeniden_sor=False):
    """yeniden_sor=True ('Değiştir'): mevcut degerlerle DOLU form acilir."""
    a = niyet_kural.alanlari_cikar(mesaj) if mesaj else {}
    # Kayitli deger YALNIZCA mesaj en az bir alan iceriyorsa eksigi tamamlar.
    # Bos mesaj ya da "hayır" gibi alan icermeyen mesaj her zaman formu acar.
    veri = a.get("veri_seti") or (durum.get("veri_seti") if a else None)
    sozluk = a.get("sozluk") or (durum.get("sozluk") if a else None)

    # METIN YOK, YALNIZ FORM. Formun kendi basligi ("Veri seti ve değişken
    # sözlüğü") ve aciklamasi ("Analiz edilecek veri setini ve değişken
    # sözlüğünü seçin.") ayni seyi zaten soyluyor; ustune bir de balon
    # basmak ayni cumleyi iki kere yazmakti. Ustelik kullanici bu noktada
    # ekranda henuz bir sey SOYLEMEDI (A/B/C kart tiklamasi sessiz gidiyor),
    # yani asistanin cevap veriyormus gibi balon acmasi yanlis: akis ayni
    # sohbette KESINTISIZ devam etmeli.
    if yeniden_sor:
        _kurulum_formu(durum, veri or durum.get("veri_seti"),
                       sozluk or durum.get("sozluk"))
        return False, ""

    if not veri or not sozluk:
        _kurulum_formu(durum, veri, sozluk)
        return False, ""

    for ad in (veri, sozluk):
        if not _dataset_var_mi(ad):
            _kurulum_formu(durum, veri, sozluk)
            return False, ("'%s' adında bir tabloya erişemiyorum. "
                           "Adı kontrol edip yeniden seçin." % ad)

    durum["veri_seti"], durum["sozluk"] = veri, sozluk
    durum["_secim_alani"] = None
    return True, None

# ===========================================================================
# ADIM KAYNAK SOZLUKLERI  (Mod B)
# ===========================================================================
# Mod B: nihai (baz) veri seti YOK, ama onu olusturacak kaynak tablolar ve
# HER BIRININ SOZLUGU hazir. Burada her tabloya sozlugu eslenir; nihai
# sozluk birlestirmeden SONRA bu sozluklerden otomatik kurulur (bkz.
# kaynak_sozlugunden_kur): kaynak kolon tanimini aynen alir, toplama
# kolonlari kaynak tanim + fonksiyon + pencereyle tarif edilir.
#
# Ayni sozluk birden fazla tabloya secilebilir (ortak sozluk).
KAYNAK_SOZLUK_ONEK = "kaynak sözlükleri:"
KAYNAK_SOZLUK_AYRAC = " | "


def _kaynak_sozluk_formu(durum, secili=None):
    tablolar = list(durum.get("ham_tablolar") or [])
    secili = secili or durum.get("kaynak_sozlukler") or {}
    alanlar = [{"ad": "sozluk_%d" % i, "etiket": t,
                "deger": secili.get(t) or ""}
               for i, t in enumerate(tablolar)]
    durum["_secim_alani"] = {
        "tip": "form",
        "baslik": "Kaynak sözlükleri",
        "aciklama": "Her kaynak tablonun değişken sözlüğünü seçin. Aynı "
                    "sözlük birden fazla tablo için seçilebilir. Nihai "
                    "sözlük birleştirmeden sonra bu sözlüklerden kurulur.",
        "buton": "Sözlükleri Onayla",
        "alanlar": alanlar,
        "sablon": KAYNAK_SOZLUK_ONEK + " " + KAYNAK_SOZLUK_AYRAC.join(
            "{%s}" % a["ad"] for a in alanlar),
    }


def _kaynak_sozluk_coz(durum, mesaj):
    """'kaynak sözlükleri: S1 | S2' -> {tablo: sozluk}; bicim tutmazsa None."""
    metin = (mesaj or "").strip()
    if not metin.lower().startswith(KAYNAK_SOZLUK_ONEK):
        return None
    degerler = [d.strip() for d in
                metin[len(KAYNAK_SOZLUK_ONEK):].split(KAYNAK_SOZLUK_AYRAC.strip())]
    tablolar = list(durum.get("ham_tablolar") or [])
    if len(degerler) != len(tablolar):
        return None
    return dict(zip(tablolar, degerler))


def kaynak_sozluk_girdi(durum, mesaj, yeniden_sor=False):
    """Metin yok, yalniz form (kurulum ile ayni dil)."""
    secim = None if yeniden_sor else _kaynak_sozluk_coz(durum, mesaj)
    if not secim:
        _kaynak_sozluk_formu(durum)
        return False, ""

    bos = [t for t, s in secim.items() if not s]
    if bos:
        _kaynak_sozluk_formu(durum, secim)
        return False, ("Şu tabloların sözlüğü seçilmedi: %s"
                       % ", ".join(bos))

    erisilemeyen = sorted({s for s in secim.values() if not _dataset_var_mi(s)})
    if erisilemeyen:
        _kaynak_sozluk_formu(durum, secim)
        return False, ("Erişemediğim sözlükler: %s\n\n"
                       "Adlarını kontrol eder misiniz?" % ", ".join(erisilemeyen))

    durum["kaynak_sozlukler"] = secim
    durum["_secim_alani"] = None
    return True, None


def kaynak_sozluk_uygula(durum):
    adlar = sorted(set((durum.get("kaynak_sozlukler") or {}).values()))
    return "Kaynak sözlükleri kaydedildi: %s" % ", ".join(adlar)


def _tanim_haritasi(sozluk_df):
    """{kolon_adi_buyuk: (aciklama, kategori)} - bos tanimlar atlanir."""
    ad_k = sozluk_calisma.degisken_kolonu_bul(sozluk_df)
    tanim_k = sozluk_calisma.tanim_kolonu_bul(sozluk_df)
    kat_k = sozluk_calisma.kategori_kolonu_bul(sozluk_df)
    harita = {}
    if ad_k is None or tanim_k is None:
        return harita
    for _, r in sozluk_df.iterrows():
        ad = str(r[ad_k]).strip()
        tanim = r[tanim_k]
        if not ad or tanim is None or (isinstance(tanim, float) and np.isnan(tanim)):
            continue
        tanim = str(tanim).strip()
        if not tanim:
            continue
        kat = r[kat_k] if kat_k is not None else None
        kat = "" if kat is None or (isinstance(kat, float) and np.isnan(kat)) \
            else str(kat).strip()
        harita.setdefault(ad.upper(), (tanim, kat))
    return harita


def _turetilmis_tanim(kayit, kaynak_tanim):
    """Kutuk satirindan kolon tanimi. None: kaynakta tanim yok."""
    tablo = str(kayit.get("KAYNAK_TABLO") or "")
    kolon = str(kayit.get("KAYNAK_KOLON") or "")
    tur = str(kayit.get("TUR") or "")
    pencere = str(kayit.get("PENCERE") or "-")
    if tur == "işlem toplama":
        fonk = str(kayit.get("FONKSIYON") or "")
        m = re.search(r"\(([^)]*)\)", fonk)
        fonk_adi = m.group(1) if m else fonk
        if kolon == "(satır sayısı)":
            return "%s tablosundaki kayıt sayısı, %s." % (tablo, pencere)
        if not kaynak_tanim:
            return None
        return "%s — %s, %s (%s.%s)." % (kaynak_tanim.rstrip("."), fonk_adi,
                                         pencere, tablo, kolon)
    if not kaynak_tanim:
        return None
    if tur == "boyut":
        ek = (" (%s tablosundan, %s)" % (tablo, pencere) if pencere != "-"
              else " (%s tablosundan)" % tablo)
        return kaynak_tanim.rstrip(".") + ek + "."
    return kaynak_tanim


def kaynak_sozlugunden_kur(durum, baz, kutuk):
    """Mod B: nihai sozlugu kaynak sozluklerden ve koken kutugunden kurar.

    Her kolon icin kutuk "hangi tablonun hangi kolonundan, hangi
    fonksiyon ve pencereyle" geldigini soyluyor; tanim o tablonun
    sozlugunden okunuyor. Kaynakta tanimi olmayan kolon sozluge
    YAZILMAZ: "Sözlük Tanımları" adiminda tanimsiz olarak listelenir.
    Doner: (tablo_df, ozet_sozlugu)."""
    esleme = durum.get("kaynak_sozlukler") or {}
    haritalar, okunamayan = {}, []
    for ad in sorted(set(esleme.values())):
        try:
            haritalar[ad] = _tanim_haritasi(_df_oku(ad))
        except Exception as e:
            haritalar[ad] = {}
            okunamayan.append("%s (%s)" % (ad, str(e)[:60]))

    satirlar, gorulen = [], set()
    turetilen = 0
    for _, k in kutuk.iterrows():
        kolon = str(k.get("KOLON"))
        if kolon in gorulen or kolon not in baz.columns:
            continue
        gorulen.add(kolon)
        tablo = str(k.get("KAYNAK_TABLO") or "")
        kaynak_kolon = str(k.get("KAYNAK_KOLON") or "")
        tanim, kat = haritalar.get(esleme.get(tablo), {}).get(
            kaynak_kolon.upper(), (None, ""))
        aciklama = _turetilmis_tanim(k, tanim)
        if not aciklama:
            continue
        toplama = str(k.get("TUR") or "") == "işlem toplama"
        turetilen += int(toplama)
        satirlar.append({
            "DEGISKEN": kolon,
            "ACIKLAMA": aciklama,
            "KATEGORI": kat or "tanımsız",
            "KAYNAK": "%s.%s" % (tablo, kaynak_kolon),
            "URETIM": ("kaynak sözlükten türetildi" if toplama
                       else "kaynak sözlük"),
        })
    tablo_df = pd.DataFrame(satirlar, columns=[
        "DEGISKEN", "ACIKLAMA", "KATEGORI", "KAYNAK", "URETIM"])
    return tablo_df, {"toplam": int(baz.shape[1]), "tanimli": len(satirlar),
                      "turetilen": turetilen, "okunamayan": okunamayan}


def _mod_b_sozlugu(durum, baz, kutuk):
    """Birlestirmeden sonra Mod B'nin sozluk isi. Doner: rapor metni."""
    tablo, oz = kaynak_sozlugunden_kur(durum, baz, kutuk)
    yazildi, yedek = _yaz(SOZLUK_ADI, tablo, "/degisken_sozlugu.csv")
    durum["sozluk"] = yazildi or None
    durum["sozluk_yedek"] = yedek
    durum["sozluk_uretim"] = {"kaynak": "kaynak sözlükleri", **oz}
    kopya_not = _calisma_kopyasi_kur(durum, tablo)
    # Profil + kapsam SIMDI: baz zaten bellekte. Modelleme tanimlari
    # hedef/kimlik adaylarini, sozluk tanimlari tanimsiz listesini
    # buradan okuyor; tablo ikinci kez taranmiyor.
    _kapsam_hesapla(durum, baz, tablo)
    tanimsiz = oz["toplam"] - oz["tanimli"]
    metin = ("\n\nDEĞİŞKEN SÖZLÜĞÜ\n"
             "  %s kolonun %s tanesi kaynak sözlüklerden tanımlandı "
             "(%s toplama kolonu türetildi).\n"
             "  Tablo: %s"
             % (_sayi(oz["toplam"]), _sayi(oz["tanimli"]),
                _sayi(oz["turetilen"]), _nerede(yazildi, yedek)))
    if tanimsiz:
        metin += ("\n  Kaynağında tanımı olmayan %s kolon «Sözlük "
                  "Tanımları» adımında listelenecek." % _sayi(tanimsiz))
    if oz["okunamayan"]:
        metin += "\n\n%s" % _liste("Okunamayan sözlükler:", oz["okunamayan"], 6)
    return metin + kopya_not


# ---------------------------------------------------------------------------
# GIRDI DOGRULAMA  —  tanimsiz kolonlar icin satir satir karar
# ---------------------------------------------------------------------------
# SINIR KALDIRILDI (kullanici karari). Bu deger eskiden kartta tek tek
# karar verilebilecek en fazla kolon sayisiydi; ustunde kalanlar ekranda
# HIC gorunmeden varsayilan isleme (haric) giriyordu. 1.002 tanimsiz
# kolonlu bir sette bu, 802 kolonun kullaniciya gosterilmeden surec
# disina alinmasi demekti. Artik tanimsiz kolonlarin HEPSI listeleniyor.
#
# Sabit, ESKI OTURUMLARI ve disaridan cagiranlari kirmamak icin duruyor;
# sozluk_tanim_plan onu ARTIK KULLANMIYOR.
EN_FAZLA_TANIMSIZ = 200

# Dil modeline TEK cagrida gonderilen kolon sayisi. Kolonlar bu boyda
# gruplara bolunur; bir grup patlarsa yalnizca o grubun kolonlari
# onerisiz kalir, digerleri gelir.
ONERI_GRUP = 25

# Kategorik kolondan modele giden en sik etiket sayisi ve etiket metninin
# kirpildigi uzunluk. Serbest metin tasiyan bir kolonun etiketleri promptu
# sisirir; 40 karakter kolonun ne oldugunu anlamaya yeter.
EN_SIK_ETIKET = 10
EN_UZUN_ETIKET = 40

# Kartin ustunde HER ZAMAN gorunen TEK not satiri.
#
# NEDEN TEK SATIR: burada uc ayri not vardi — varsayilan islemi anlatan
# cumle, "yalnizca tanimsiz kolonlar incelendi" kapsam notu ve "oneriler
# dil modelinden geldi, N kolon incelendi" uyarisi. Ucu de ayni seyi
# soyluyordu ve kartin ustunu uc satir uyari ile dolduruyordu; karar
# tablosu ekranin altina kayiyordu. Uc cumlenin tasidigi bilgi
# (varsayilan haric, kapsam yalnizca tanimsizlar, oneriler dogrulanmamis,
# kac kolon incelendi) tek satirda duruyor.
# Kartin ustundeki TEK not satiri. "yalnizca tanimsiz N kolon
# incelendi" ifadesi EN_FAZLA_TANIMSIZ sinirindan kalmaydi; sinir
# kalkti, tanimsiz kolonlarin HEPSI listeleniyor. Not artik kac kolonun
# karara acildigini yaziyor.
TANIMSIZ_NOT_KALIP = ("Tanımı bulunmayan %s kolon aşağıda listelendi; "
                      "varsayılan olarak analiz dışında tutulurlar. "
                      "Açıklama önerileri dil modeli tarafından üretildi, "
                      "doğrulanmamıştır.")

# Hedef, kimlik ve donem kolonu modelin iskeletidir. Tanimsiz kalirlarsa
# model kartinda "bu kolon neydi" sorusunun cevabi hicbir yerde yazmaz;
# bu yuzden satirlari kilitli isaretli gelir ve aciklama bos birakilamaz.
ZORUNLU_NOT = ("Hedef değişken, kimlik kolonu ve dönem kolonu sözlükte "
               "tanımlı olmak zorundadır. Bu satırların işareti "
               "kaldırılamaz; açıklamaları yazılmadan devam edilemez.")


def _kolon_ozet_haritasi(profil):
    """{kolon_adi: ozet_kaydi}. Profil bozuksa bos sozluk."""
    harita = {}
    for k in ((profil or {}).get("kolon_ozet") or []):
        if isinstance(k, dict) and k.get("ad") is not None:
            harita[str(k["ad"])] = k
    return harita


def _tekil_tamamla(df, kolonlar, profil):
    """Karara konu olan kolonlarin tekil deger sayisini profile isler.

    kolon_ozeti_cikar tekil sayisini BILEREK bos birakiyor: 1.000 kolonlu
    bir tabloda her kolonu tam taramak veri seti secimini yavaslatir.
    Burada yalnizca kullanicinin karar verecegi (en fazla EN_FAZLA_TANIMSIZ)
    kolon icin hesaplaniyor — hem kartta gosteriliyor hem de dil modeline
    giden tek metadata parcalarindan biri."""
    hedef = {str(k) for k in (kolonlar or [])}
    if not hedef:
        return
    for k in (profil.get("kolon_ozet") or []):
        if not isinstance(k, dict) or str(k.get("ad")) not in hedef:
            continue
        if k.get("tekil") is not None:
            continue
        try:
            k["tekil"] = int(df[k["ad"]].nunique(dropna=True))
        except Exception:
            k["tekil"] = None


def _etiket_kirp(deger):
    """Modele giden etiket metni. Uzun etiket promptu sisirir."""
    metin = str(deger).strip()
    if len(metin) > EN_UZUN_ETIKET:
        return metin[:EN_UZUN_ETIKET - 1] + "…"
    return metin


def _sayisal_ozet(seri):
    """Sayisal kolondan min / maks / ceyrekler. TEK TEK DEGER DONMEZ."""
    try:
        sn = pd.to_numeric(seri, errors="coerce").dropna()
    except Exception:
        return {}
    if not len(sn):
        return {}
    try:
        q = sn.quantile([0.0, 0.25, 0.5, 0.75, 1.0]).tolist()
    except Exception:
        return {}
    return {"min": round(float(q[0]), 4),
            "maks": round(float(q[4]), 4),
            "ceyrekler": [round(float(x), 4) for x in q[1:4]]}


def _tarih_ozet(seri):
    """Tarih kolonundan YALNIZ min/maks. Ceyrek de ornek de gitmez:
    bir tarih kolonunun ne oldugunu anlamak icin araligi yeter."""
    try:
        s = seri.dropna()
        if not len(s):
            return {}
        return {"min": str(s.min())[:19], "maks": str(s.max())[:19]}
    except Exception:
        return {}


def _kategorik_ozet(seri, satir, ad):
    """Kategorik kolondan en sik EN_SIK_ETIKET etiket ve orani.

    ETIKETLER BILEREK GIDIYOR: bir kategorik kolonun ne oldugu ancak
    etiketlerinden anlasilir ("A/B/C" ile "EVET/HAYIR" ayni istatistigi
    verir, ayni anlami vermez). Giden sey yine de ham satir degil,
    sayimdan turetilmis bir dagilimdir.

    Kimlik benzeri, kisisel veri ya da uzun metin tasiyan kolonda HIC
    etiket gonderilmez. Bu kapi sozluk._ornek_guvenli_mi'de zaten duruyor;
    ikinci bir kural yazmiyoruz ki iki yerden biri guncellenip digeri
    unutulmasin."""
    try:
        guvenli, neden = sozluk_mod._ornek_guvenli_mi(seri, satir, ad)
    except Exception:
        return {}
    if not guvenli:
        return {"not": neden}
    try:
        sayim = seri.dropna().astype(str).value_counts().head(EN_SIK_ETIKET)
    except Exception:
        return {}
    toplam = max(int(satir or 0), 1)
    return {"en_sik": [[_etiket_kirp(etiket), round(float(adet) / toplam, 4)]
                       for etiket, adet in sayim.items()]}


def _dagilim_metni(kayit):
    """Turetilmis ozetin prompta yazilan hali.

    llm.sozluk_aciklama_uret'in arayuzu DEGISMIYOR; o fonksiyon profilden
    yalnizca `dagilim` (ya da `not`) alanini prompta yaziyor. Ozet modele
    bu alandan ulasiyor. Icinde ham satir yok: sayisalda min/maks/ceyrek,
    kategorikte en sik etiket oranlari, tarihte aralik."""
    if kayit.get("ceyrekler"):
        q = kayit["ceyrekler"]
        return ("min %s · q1 %s · medyan %s · q3 %s · maks %s"
                % (kayit.get("min"), q[0], q[1], q[2], kayit.get("maks")))
    if kayit.get("en_sik"):
        return " · ".join("%s %%%s" % (etiket, round(oran * 100, 1))
                          for etiket, oran in kayit["en_sik"])
    if kayit.get("min") is not None:
        return "min %s · maks %s" % (kayit.get("min"), kayit.get("maks"))
    return ""


def _oneri_profilleri(df, kolonlar, profil):
    """Dil modeline gidecek TURETILMIS ozetler.

    Veri seti cagiran tarafta BIR KEZ okunmustur; burada kolon basina
    yeni bir okuma YAPILMAZ, elde duran tablonun yalnizca hedeflenen
    kolonlari taranir. Taranan kolonlar da yalnizca sozlukte tanimi
    bulunmayanlardir: tanimli kolonun serisine hic dokunulmaz."""
    ozet = _kolon_ozet_haritasi(profil)
    satir = int(len(df)) if df is not None else 0
    kayitlar = []
    for ad in kolonlar:
        k = ozet.get(ad) or {}
        tip = k.get("tip") or ""
        try:
            oran = float(k.get("null_oran") or 0.0)
        except (TypeError, ValueError):
            oran = 0.0
        tekil = k.get("tekil")
        kayit = {"ad": ad, "tip": tip, "null_oran": round(oran, 4),
                 "tekil": 0 if tekil is None else int(tekil)}

        seri = None
        try:
            if df is not None and ad in df.columns:
                seri = df[ad]
        except Exception:
            seri = None

        if seri is not None:
            if tip == "sayısal":
                kayit.update(_sayisal_ozet(seri))
            elif tip == "tarih":
                kayit.update(_tarih_ozet(seri))
            else:
                kayit.update(_kategorik_ozet(seri, satir, ad))

        kayit["dagilim"] = _dagilim_metni(kayit)
        kayitlar.append(kayit)
    return kayitlar


def _tanimsiz_oneriler(durum, kolonlar, profil, df=None):
    """Tanimsiz kolonlar icin dil modelinden ACIKLAMA onerisi.

    Doner: {kolon: {"aciklama": ...}}. Oneri alinamayan
    kolon sozlukte HIC GECMEZ; cagiran taraf orayi bos gosterir.

    KATEGORI ISTENMIYOR. Girdi dogrulama kartinda kategori kolonu yok:
    tanimsiz bir kolona kategori atamak, kolonun ne oldugunu bilmeden
    onu bir kovaya koymaktir ve karar ekranini gereksiz genisletiyordu.
    Modelden yalnizca aciklama isteniyor; donen govdedeki kategori alani
    (llm.py'nin kendi semasi) OKUNMUYOR ve hicbir yere yazilmiyor.

    KAPSAM — SOZLUKTE TANIMI OLAN KOLON BURAYA HIC GIRMEZ. Cagiran taraf
    yalnizca tanimsiz kolonlari verir; tanimli kolonun adi da, profili de
    modele gitmez ve aciklamasi degismez. Bu hem maliyet hem guven
    meselesidir: mevcut sozluk kurumun ONAYLADIGI halidir, dil modelinin
    yeniden yazacagi bir metin degil. 1.000 kolonluk bir tabloda tanimli
    kolonlari da gondermek hem parayi hem de onaylanmis tanimlari harcar.

    MODELE NE GIDIYOR — yalniz TURETILMIS ozet: kolon adi, veri tipi,
    null orani, tekil deger sayisi; sayisaldan min/maks/ceyrekler,
    kategorikten en sik etiketler ve oranlari, tarihten min/maks. HAM
    SATIR YA DA TEK TEK DEGER GONDERILMEZ.

    GRUPLAMA — kolonlar ONERI_GRUP'erli bolunur, her grup TEK cagridir.
    Gruplar arasinda baglam TASINMAZ: her cagri kendi kolonlariyla
    baslar, model bir oncekinin izini surmez.

    HATA — grup bazinda yutulur. Bir grup patlarsa yalnizca o grubun
    kolonlari onerisiz kalir (oneri_kaynak "yok"); diger gruplarin
    onerileri gelir ve adim hicbir durumda durmaz. Oneri bir kolaylik,
    bir kapi degil: kullanici aciklamayi kendi yazar ya da kolonu haric
    tutar.

    ONBELLEK — kullanici geri donup adimi tazeledigi zaman ayni kolonlar icin
    modeli ikinci kez beklemek anlamsiz."""
    kolonlar = [str(k) for k in (kolonlar or [])]
    if not kolonlar:
        return {}

    onbellek = durum.get("_tanimsiz_oneri")
    if isinstance(onbellek, dict) \
            and durum.get("_tanimsiz_oneri_kolonlar") == kolonlar:
        return onbellek

    profiller = _oneri_profilleri(df, kolonlar, profil)

    ham = {}
    grup_sayisi = 0
    dusen_grup = 0
    son_hata = ""
    for bas in range(0, len(profiller), ONERI_GRUP):
        grup = profiller[bas:bas + ONERI_GRUP]
        grup_sayisi += 1
        try:
            # parca=len(grup): llm.py'nin kendi parcalamasi devreye
            # girmesin; grup tek cagri olsun. Cagri yalnizca bu grubun
            # profilleriyle kuruluyor, onceki grubun kolonlari
            # gonderilmiyor — baglam tasinmiyor.
            sonuc, _hata = llm_mod.sozluk_aciklama_uret(
                grup, parca=len(grup))
        except Exception as e:
            # Bu grup onerisiz kalir, digerleri gelir. AMA SESSIZ DEGIL:
            # hata tamamen yutulunca imza uyusmazligi ya da kapali bir
            # baglanti "model hicbir sey oneremedi" gibi gorunuyor ve
            # kimse nedenini bilmiyordu. Sayaci kart ustunde yaziyoruz.
            dusen_grup += 1
            son_hata = "%s: %s" % (type(e).__name__, str(e)[:120])
            continue
        if isinstance(sonuc, dict):
            ham.update(sonuc)

    oneriler = {}
    for ad in kolonlar:
        kayit = ham.get(ad)
        if not isinstance(kayit, dict):
            continue
        aciklama = str(kayit.get("aciklama") or "").strip()
        if not aciklama:
            continue
        # YALNIZ ACIKLAMA: modelin donebilecegi kategori alani bilerek
        # okunmuyor (bkz. fonksiyon acikmasi).
        oneriler[ad] = {"aciklama": aciklama[:300]}

    durum["_tanimsiz_oneri"] = oneriler
    durum["_tanimsiz_oneri_kolonlar"] = kolonlar
    durum["_tanimsiz_oneri_hata"] = (
        "" if not dusen_grup else
        "%s gruptan %s tanesi için öneri alınamadı (%s). O kolonların "
        "açıklamasını kendiniz yazabilir ya da hariç tutabilirsiniz."
        % (_sayi(grup_sayisi), _sayi(dusen_grup), son_hata))
    return oneriler


# ---------------------------------------------------------------------------
# ONERI ISI  —  oneriler ARKA PLANDA, grup grup uretilir
# ---------------------------------------------------------------------------
# NEDEN ARKA PLAN: 1.000 tanimsiz kolon ONERI_GRUP'erli bolununce 40
# ayri dil modeli cagrisi eder; hepsini tek istekte beklemek kullaniciyi
# dakikalarca bos ekranda tutar ve istek zaman asimina ugrar. Kart
# HEMEN aciliyor, satirlar oneriler geldikce doluyor.
#
# ACIKLAMA ALANLARI ONERILER BITENE KADAR KILITLI (kullanici karari):
# yaridaki bir listede yazmaya baslayip ustune oneri dusmesi, kullanicinin
# yazdigini kaybetmesi demek olurdu.
#
# DURUM NESNESINE DOKUNULMAZ. Isci yalnizca bu kayda yazar; `durum` istek
# is parcaciginda okunup yaziliyor, ikisi ayni anda ellenirse kayip yazma
# olur. Sonuc, kullanici karti onayladiginda durum'a tasinir.
_ONERI_ISLER = {}
_ONERI_KILIT = threading.Lock()
ONERI_IS_SINIRI = 8          # ayni anda saklanan en fazla is sayisi


def _oneri_isi_kirp():
    """Kayit sinirsiz buyumesin: en eski isler dusurulur."""
    if len(_ONERI_ISLER) <= ONERI_IS_SINIRI:
        return
    sirali = sorted(_ONERI_ISLER.items(), key=lambda p: p[1].get("baslangic", 0))
    for anahtar, _ in sirali[:len(_ONERI_ISLER) - ONERI_IS_SINIRI]:
        _ONERI_ISLER.pop(anahtar, None)


def _oneri_isi_calis(is_id, profiller):
    """Isci: gruplari sirayla isler, her gruptan sonra kaydi tazeler."""
    dusen_grup = 0
    grup_sayisi = 0
    son_hata = ""
    for bas in range(0, len(profiller), ONERI_GRUP):
        with _ONERI_KILIT:
            kayit = _ONERI_ISLER.get(is_id)
            if kayit is None or kayit.get("iptal"):
                return
        grup = profiller[bas:bas + ONERI_GRUP]
        grup_sayisi += 1
        yeni = {}
        try:
            # parca=len(grup): llm.py'nin kendi parcalamasi devreye
            # girmesin; grup TEK cagri olsun. Gruplar arasinda baglam
            # tasinmaz, her cagri kendi kolonlariyla baslar.
            sonuc, _hata = llm_mod.sozluk_aciklama_uret(grup, parca=len(grup))
            if isinstance(sonuc, dict):
                for ad, kayit_s in sonuc.items():
                    if not isinstance(kayit_s, dict):
                        continue
                    aciklama = str(kayit_s.get("aciklama") or "").strip()
                    if aciklama:
                        # YALNIZ ACIKLAMA: modelin donebilecegi kategori
                        # alani bilerek okunmuyor.
                        yeni[str(ad)] = {"aciklama": aciklama[:300]}
        except Exception as e:
            # Bu grup onerisiz kalir, digerleri gelir. AMA SESSIZ DEGIL:
            # sayac ve son hata kart ustunde yaziliyor.
            dusen_grup += 1
            son_hata = "%s: %s" % (type(e).__name__, str(e)[:120])
        with _ONERI_KILIT:
            kayit = _ONERI_ISLER.get(is_id)
            if kayit is None:
                return
            kayit["oneriler"].update(yeni)
            kayit["biten"] = min(bas + len(grup), len(profiller))

    with _ONERI_KILIT:
        kayit = _ONERI_ISLER.get(is_id)
        if kayit is None:
            return
        kayit["durum"] = "bitti"
        kayit["biten"] = len(profiller)
        kayit["hata"] = (
            "" if not dusen_grup else
            "%s gruptan %s tanesi için öneri alınamadı (%s). O kolonların "
            "açıklamasını kendiniz yazabilir ya da hariç tutabilirsiniz."
            % (_sayi(grup_sayisi), _sayi(dusen_grup), son_hata))


def oneri_isi_baslat(kolonlar, profiller):
    """Arka plan onerisini baslatir. Doner: is kimligi."""
    is_id = uuid.uuid4().hex[:12]
    with _ONERI_KILIT:
        _ONERI_ISLER[is_id] = {
            "durum": "calisiyor" if profiller else "bitti",
            "oneriler": {}, "toplam": len(profiller), "biten": 0,
            "hata": "", "kolonlar": list(kolonlar),
            "baslangic": datetime.datetime.now().timestamp(),
        }
        _oneri_isi_kirp()
    if not profiller:
        return is_id
    isci = threading.Thread(
        target=_oneri_isi_calis, args=(is_id, profiller), daemon=True)
    isci.start()
    return is_id


def oneri_isi_durumu(is_id):
    """Ilerleme + o ana kadarki oneriler. Is yoksa None."""
    with _ONERI_KILIT:
        kayit = _ONERI_ISLER.get(str(is_id or ""))
        if kayit is None:
            return None
        return {"durum": kayit["durum"], "toplam": kayit["toplam"],
                "biten": kayit["biten"], "hata": kayit["hata"],
                "oneriler": dict(kayit["oneriler"])}


def oneri_isi_iptal(is_id):
    """Kullanici adimdan ayrildi: isci bir sonraki grupta durur."""
    with _ONERI_KILIT:
        kayit = _ONERI_ISLER.get(str(is_id or ""))
        if kayit is not None:
            kayit["iptal"] = True


def _oneri_sonucunu_tasi(durum):
    """Isin urettigi onerileri durum'a tasir (onay aninda cagrilir).

    Denetim izi icin: hangi aciklama modelden geldi, kullanici neyi
    degistirdi. sozluk_calisma.satir_ekle bunu `oneri` alanina yaziyor."""
    kayit = oneri_isi_durumu(durum.get("_oneri_is"))
    if kayit is None:
        return
    durum["_tanimsiz_oneri"] = kayit["oneriler"]
    durum["_tanimsiz_oneri_kolonlar"] = list(durum.get("_oneri_kolonlar") or [])
    durum["_tanimsiz_oneri_hata"] = kayit["hata"]


def _dogrulama_karti(durum, profil, gosterilen, kalan, oneriler):
    """Adimin ekranda gosterdigi yapilandirilmis karar karti.

    Baslik, sayilar ve karar satirlari kartin ICINDE; adim ayrica metin
    dondurmez (bkz. kurulum_plan)."""
    kolon = int(profil.get("kolon") or 0)
    sayisal = int(profil.get("sayisal") or 0)
    tarih = int(profil.get("tarih") or 0)
    kategorik = max(kolon - sayisal - tarih, 0)
    tip_alt = "%s sayısal · %s kategorik" % (_sayi(sayisal), _sayi(kategorik))
    if tarih:
        tip_alt += " · %s tarih" % _sayi(tarih)

    eslesen = int(profil.get("eslesen") or 0)
    kapsam = profil.get("kapsam")

    alan = {
        "tip": "dogrulama",
        # BASLIK KALDIRILDI (kullanici istegi). Kart artik kendi adimi
        # olan "Sözlük Tanımları" blogunun icinde duruyor ve alt baslik
        # zaten o adin kendisi; kart ayrica "Girdi doğrulama tamamlandı"
        # diye ikinci bir baslik tasirsa ayni sey iki kere yaziliyor.
        "baslik": "",
        # "Hazır" tek basina NEYIN hazir oldugunu soylemiyordu. Rozet,
        # secim formundaki "Girdiler Hazır" ile ayni dili konusur: neyin
        # dogrulandigini yazar. Baslik Buyuk Harfi (bkz. _kurulum_formu).
        "rozet": "Girdiler Doğrulandı",
        "ozet": [
            {"etiket": "Veri seti", "deger": durum.get("veri_seti") or "",
             "alt": ["%s satır · %s kolon"
                     % (_sayi(profil.get("satir") or 0), _sayi(kolon)),
                     tip_alt]},
            {"etiket": "Değişken sözlüğü", "deger": durum.get("sozluk") or "",
             "alt": ["%s tanım" % _sayi(profil.get("sozluk_satir") or 0)]},
        ],
        "kapsam": {"yuzde": kapsam, "tanimli": eslesen, "toplam": kolon,
                   "metin": "%%%s: %s / %s kolon tanımlı"
                            % (_ond(kapsam), _sayi(eslesen), _sayi(kolon))},
        "tanimsiz": None,
        "buton_kalip": {
            "haric": "%s Kolonu Hariç Tut ve Devam Et",
            "ekle": "%s Kolonu Sözlüğe Ekle ve Devam Et",
            "karma": "Seçimleri Uygula ve Devam Et",
            "bos": "Devam Et",
        },
        # "ikincil" ve "ucuncul" KALDIRILDI: ikisi de ayni yere, veri
        # seti secim formuna goturuyordu. Kartta yalnizca birincil dugme
        # kaliyor.
    }

    if not gosterilen:
        # Kapsam %100: karar verilecek bir sey yok, kart yalnizca ozet ve
        # kapsam gosterir.
        return alan

    ozet = _kolon_ozet_haritasi(profil)
    zorunlu_rol = _zorunlu_etiketler(durum)
    satirlar = []
    for ad in gosterilen:
        oneri = (oneriler or {}).get(ad) or {}
        aciklama = str(oneri.get("aciklama") or "")
        rol = zorunlu_rol.get(ad)
        # KATEGORI ALANI YOK. Kart dort kolona iniyor:
        # Degisken | Tip | Aciklama | Sozluge Ekle.
        satir = {
            "kolon": ad,
            "tip": (ozet.get(ad) or {}).get("tip") or "",
            # ZORUNLU SATIR "ekle" ile acilir ve isaret kaldirilamaz:
            # hedef, kimlik ve donem kolonu sozlukte tanimsiz kalamaz.
            "islem": "ekle" if rol else "haric",
            "oneri": aciklama,
            "oneri_kaynak": "llm" if aciklama else "yok",
        }
        if rol:
            satir["zorunlu"] = True
            satir["rol"] = rol
        satirlar.append(satir)

    # Zorunlu satirlar EN USTTE: kullanici onlari gormeden ilerleyemez.
    satirlar.sort(key=lambda s: 0 if s.get("zorunlu") else 1)

    alan["tanimsiz"] = {
        "baslik": "Sözlükte tanımı bulunmayan kolonlar",
        "varsayilan": "haric",
        # TEK NOT. Kac kolon incelendigini de yaziyor ki bekleme suresi
        # anlamli gorunsun (bkz. TANIMSIZ_NOT_KALIP).
        "not": TANIMSIZ_NOT_KALIP % _sayi(len(satirlar)),
        "satirlar": satirlar,
        # Zorunlu kolonlarin acikca yazildigi uyari; on yuz devam
        # dugmesini bu listeye bakarak kapali tutuyor.
        # Uyari YALNIZCA listede gercekten zorunlu satir varsa: hedef
        # kolonu sozlukte zaten tanimliysa ortada bir kural yok.
        "zorunlu_not": (ZORUNLU_NOT
                        if any(x.get("zorunlu") for x in satirlar) else ""),
    }
    if kalan > 0:
        alan["tanimsiz"]["kalan"] = kalan
    # Oneri alinamayan grup varsa NEDENI ekranda yazar. Sessiz kalinca
    # "model hicbir sey oneremedi" ile "model hic cagrilamadi" ayni
    # goruntuyu veriyordu.
    oneri_hata = durum.get("_tanimsiz_oneri_hata") or ""
    if oneri_hata:
        alan["tanimsiz"]["oneri_hata"] = oneri_hata
    return alan


def _kapsami_cikar(durum):
    """Veri seti ve sozlugu okur, profili ve tanimsiz kolon listesini kurar.

    ESKIDEN kurulum_plan'in basindaydi. Artik sozluk tanimlari adimi
    modelleme tanimlarindan SONRA geldigi icin (hedef/kimlik/donem
    kolonlarinin tanimi zorunlu, hangileri oldugu once bilinmeli) profil
    daha erken, veri seti secilir secilmez cikariliyor: `tanimlar` adimi
    hedef ve kimlik adaylarini bu profilden okuyor."""
    # SECIM TAZELENDIGINDE TABLO YENIDEN OKUNUR. Onbellek artik uzun
    # yasiyor (bkz. akis_durum.ONBELLEK_OMRU_SN); kullanici veri setini
    # Dataiku'da yeniden olusturup adimi tekrar calistirdiginda bayat
    # kopyayi okumamak icin bu iki kayit acikca dusuruluyor. Maliyeti
    # YOK: bu fonksiyon zaten profili ilk kez cikaran taraf, tabloyu
    # nasilsa okuyacakti.
    onbellek_temizle(durum.get("veri_seti"))
    onbellek_temizle(durum.get("sozluk"))
    df = modelleme_df(durum)
    # sozluk_orijinal_oku: Mod B'de uretilen sozluk dataset'e yazilamazsa
    # CSV yedeginden okunur (durum["sozluk"] None kalir).
    return _kapsam_hesapla(durum, df, sozluk_orijinal_oku(durum))


def _kapsam_hesapla(durum, df, sz):
    """Profil + kapsam + tanimsiz liste. Tablo elde olan cagiran icin."""
    ad_kolonu = sozluk_calisma.degisken_kolonu_bul(sz)
    sozluk_ad = set(sz[ad_kolonu].astype(str)) if ad_kolonu is not None else set()

    aciklamasiz = [str(c) for c in df.columns if str(c) not in sozluk_ad]
    eslesen = df.shape[1] - len(aciklamasiz)

    p = _temel_profil(durum, df)
    p.update({
        "sozluk_satir": int(sz.shape[0]), "eslesen": eslesen,
        "kapsam": round(100.0 * eslesen / max(df.shape[1], 1), 1),
    })
    # Profilin HANGI girdilerden cikarildigi: sozluk_tanim adimi ayni
    # veri seti ve sozluk icin profili yeniden CIKARMAZ, yalnizca tabloyu
    # okur. Eskiden kapsam iki kez hesaplaniyordu (kurulum + sozluk_tanim)
    # ve 10.000 x 1.042'lik tablo iki kez taraniyordu.
    p["_kaynak"] = [durum.get("veri_seti"), durum.get("sozluk")]
    durum["profil"] = p
    durum["_aciklamasiz"] = aciklamasiz
    return df, p


def _kapsam_hazir(durum):
    """Kapsam bu veri seti ve sozluk icin zaten cikarilmis mi?"""
    p = durum.get("profil") or {}
    return (p.get("_kaynak") == [durum.get("veri_seti"), durum.get("sozluk")]
            and isinstance(durum.get("_aciklamasiz"), list))


def zorunlu_tanimlar(durum):
    """Sozlukte tanimi ZORUNLU olan kolonlar: hedef, kimlik, donem.

    Bu uc kolon modelin iskeletidir; tanimsiz kalirlarsa model kartinda
    "bu kolon neydi" sorusunun cevabi hicbir yerde yazmaz. Kullanici
    secimi yaptiysa tanimi da yazmak zorunda (kullanici karari:
    "sözlükte tanımlı olmadan ilerlenemez"). Doner: sirali liste."""
    meta = durum.get("meta") or {}
    cikti = []
    for anahtar in ("target", "id", "donem"):
        ad = str(meta.get(anahtar) or "").strip()
        if ad and ad not in cikti:
            cikti.append(ad)
    return cikti


ZORUNLU_ETIKET = {"target": "hedef değişken", "id": "kimlik kolonu",
                  "donem": "dönem kolonu"}


def _zorunlu_etiketler(durum):
    """Kolon adi -> "hedef değişken" gibi rol etiketi."""
    meta = durum.get("meta") or {}
    harita = {}
    for anahtar, etiket in ZORUNLU_ETIKET.items():
        ad = str(meta.get(anahtar) or "").strip()
        if ad:
            harita.setdefault(ad, etiket)
    return harita


def sozluk_tanim_plan(durum):
    """Sozlukte tanimi bulunmayan kolonlar. METIN DONDURMEZ.

    Bu adim bir sohbet turu degil, bir KARAR KARTIDIR: kapsam orani ve
    tanimsiz kolonlarin satir satir karari kartin icinde durur. Ustune
    bir de balon basmak ayni bilgiyi iki kere yazmak olurdu; bos metin
    akis_sohbet._bos_metin_yedegi tarafindan zaten destekleniyor
    (ekranda kart varken balon acilmaz).

    MODELLEME TANIMLARINDAN SONRA calisir: hedef, kimlik ve donem
    kolonlari tanimsizsa listenin BASINA alinir ve isaretleri
    kaldirilamaz.

    TANIMSIZ KOLONLARIN HEPSI LISTELENIR (kullanici karari). Eskiden
    EN_FAZLA_TANIMSIZ = 200 sinirinin ustu "kalan" sayisi olarak
    yaziliyor ve gorulmeden varsayilan isleme giriyordu; 1.000 tanimsiz
    kolonlu bir sette bu, 800 kolonun kullaniciya hic gosterilmeden
    surec disina alinmasi demekti.

    ONERILER ARKA PLANDA. Kart HEMEN aciliyor; dil modeli onerileri
    grup grup uretiliyor ve on yuz yoklayarak satirlari dolduruyor
    (bkz. oneri_isi_baslat). Oneriler bitene kadar aciklama alanlari ve
    devam dugmesi kilitli kaliyor."""
    if _kapsam_hazir(durum):
        # Kapsam `kurulum` adiminda cikarildi; tabloyu yalnizca tekil
        # sayimi ve oneri profilleri icin okuyoruz.
        df, p = modelleme_df(durum), durum["profil"]
    else:
        df, p = _kapsami_cikar(durum)
    aciklamasiz = durum.get("_aciklamasiz") or []

    tanimsiz_kume = set(aciklamasiz)
    zorunlu = [k for k in zorunlu_tanimlar(durum) if k in tanimsiz_kume]
    gosterilen = zorunlu + [k for k in aciklamasiz if k not in set(zorunlu)]

    # Onceki is varsa durdurulur: kullanici geri donup adimi tazeledi.
    oneri_isi_iptal(durum.get("_oneri_is"))

    # Ayni kolon kumesi icin zaten TAMAMLANMIS bir is varsa yeniden
    # calistirilmaz; geri donup adimi tazelemek modeli ikinci kez
    # bekletmemeli.
    onceki = oneri_isi_durumu(durum.get("_oneri_is"))
    if onceki and onceki["durum"] == "bitti" \
            and durum.get("_oneri_kolonlar") == gosterilen:
        oneriler = onceki["oneriler"]
        durum["_tanimsiz_oneri_hata"] = onceki["hata"]
    else:
        _tekil_tamamla(df, gosterilen, p)
        # Profil ve dil modeli cagrisi YALNIZCA tanimsiz kolonlar icin;
        # veri seti yukarida bir kez okundu, ayni tablo kullaniliyor.
        profiller = _oneri_profilleri(df, gosterilen, p)
        durum["_oneri_is"] = oneri_isi_baslat(gosterilen, profiller)
        durum["_oneri_kolonlar"] = list(gosterilen)
        durum["_tanimsiz_oneri_hata"] = ""
        oneriler = {}

    durum["_secim_alani"] = _dogrulama_karti(durum, p, gosterilen, 0, oneriler)
    # On yuz bu kimlikle yoklayip satirlari dolduruyor.
    durum["_secim_alani"]["oneri_is"] = durum.get("_oneri_is") or ""
    durum["_secim_alani"]["oneri_toplam"] = len(gosterilen)
    return ""

def _calisma_kopyasi_kur(durum, tablo=None):
    """Sozluk baglandi: oturuma ozel calisma kopyasini cikarir.

    NEDEN BURADA: kategori duzenlemesi ANINDA yaziyor ve orijinal sozluk
    dataset'ine ASLA dokunmuyor. Yazilacak bir kopya, sozluk baglanir
    baglanmaz hazir olmali; ilk duzenlemede olusturulsaydi PROJE_HAFIZASI
    erisilemedigi kullaniciya ancak o an, yaptigi duzenlemeyi
    kaybettirerek belli olurdu.

    Doner: kullaniciya eklenecek not metni ("" ise sorun yok). Kopya
    cikarilamazsa adim BASARISIZ SAYILMAZ — okuma orijinale duSER,
    yalnizca kategori duzenlemesi kapali kalir ve bu acikca yazilir."""
    yol, hata = sozluk_calisma.kopya_kur(durum, tablo)
    if yol:
        return ""
    return ("\n\nNOT: %s Sözlük okumaları orijinal tablodan yapılacak ve "
            "kategori düzenlemesi bu oturumda kapalı kalacak. Orijinal "
            "sözlüğe hiçbir koşulda yazılmaz." % hata)


def _zorunlu_eksikler(durum, karar):
    """Zorunlu tanimlardan aciklamasi yazilmamis olanlar.

    Doner: [(kolon, rol)]. Yalnizca SOZLUKTE TANIMSIZ olanlara bakar;
    zaten tanimli bir hedef kolonu icin ikinci bir aciklama istenmez."""
    tanimsiz = {str(k) for k in (durum.get("_aciklamasiz") or [])}
    roller = _zorunlu_etiketler(durum)
    if not roller:
        return []
    yazilan = {}
    if isinstance(karar, dict):
        for satir in (karar.get("ekle") or []):
            if isinstance(satir, dict) and satir.get("kolon"):
                yazilan[str(satir["kolon"])] = \
                    str(satir.get("aciklama") or "").strip()
    eksik = []
    for ad, rol in roller.items():
        if ad not in tanimsiz:
            continue                       # sozlukte zaten tanimli
        if not yazilan.get(ad):
            eksik.append((ad, rol))
    return sorted(eksik)


def _karar_oku(durum, tanimsiz):
    """On yuzden gelen karar govdesini SUZER. Doner: (haric, ekle).

    Govde istemciden geliyor; bu adimda tanimsiz olmayan hicbir kolon adi
    kabul edilmez. Aciklamasi bos gelen "ekle" satiri da kabul edilmez:
    bos tanimla sozluge girmis bir kolon, tanimsiz kolondan daha kotudur —
    tanimli gorunur ama anlami yoktur.

    Govde HIC gelmezse (eski istemci ya da kullanici yazarak onayladi)
    VARSAYILAN islem uygulanir: hepsi haric. Karar govdesinde adi hic
    gecmeyen kolonlar da (EN_FAZLA_TANIMSIZ sinirinin ustunde kalanlar
    dahil) ayni varsayilana duSER.

    "ekle" satirlari YALNIZ aciklama tasiyor. Kategori kartta artik
    sorulmuyor (tanimsiz bir kolona kategori atamak, kolonun ne oldugunu
    bilmeden onu bir kovaya koymaktir); govdede kategori gelse bile
    okunmuyor ve satir_ekle'ye bos kategori gidiyor."""
    izinli = {str(k) for k in (tanimsiz or [])}
    karar = durum.pop("_dogrulama_karari", None)
    if not isinstance(karar, dict):
        return sorted(izinli), []

    ekle, gorulen = [], set()
    for satir in (karar.get("ekle") or []):
        if not isinstance(satir, dict):
            continue
        ad = str(satir.get("kolon") or "").strip()
        if ad not in izinli or ad in gorulen:
            continue
        aciklama = str(satir.get("aciklama") or "").strip()
        if not aciklama:
            continue
        gorulen.add(ad)
        ekle.append({"kolon": ad, "aciklama": aciklama})

    return sorted(izinli - gorulen), ekle


def kurulum_uygula(durum):
    """Veri seti ve sozluk secildi: kapsami cikar, calisma kopyasini kur.

    ADIM BOLUNDU. Eskiden bu adim tanimsiz kolon kararini da uyguluyordu;
    o is artik `sozluk_tanim` adiminda ve MODELLEME TANIMLARINDAN SONRA
    yapiliyor, cunku hedef/kimlik/donem kolonlarinin tanimi zorunlu ve
    hangileri oldugu once bilinmeli.

    Burada yalnizca profil cikariliyor (tanimlar adimi hedef ve kimlik
    adaylarini buradan okuyor) ve sozluk calisma kopyasi kuruluyor."""
    _kapsami_cikar(durum)
    # Calisma kopyasi sozluk baglanir baglanmaz cikarilir: satir_ekle
    # yalnizca kopyaya yazar, kopya yoksa yazacak yer yoktur.
    return _calisma_kopyasi_kur(durum).strip()


def sozluk_tanim_uygula(durum):
    tanimsiz = [str(k) for k in (durum.get("_aciklamasiz") or [])]
    # Onerileri arka plan isinden durum'a tasi: denetim izi (hangi
    # aciklama modelden geldi) satir_ekle'ye buradan gidiyor.
    _oneri_sonucunu_tasi(durum)
    # ZORUNLU TANIM KAPISI. On yuz devam dugmesini zaten kapali tutuyor;
    # bu, govdeyi elle gonderen ya da eski bir istemci icin ikinci kapi.
    # Kart tekrar acilir, karar KAYBOLMAZ.
    karar = durum.get("_dogrulama_karari")
    eksik = _zorunlu_eksikler(durum, karar)
    if eksik:
        raise AdimHatasi(
            "Şu kolonlar sözlükte tanımlı olmak zorunda; açıklamalarını "
            "yazmadan devam edilemez:\n" +
            "\n".join("  • %s (%s)" % (ad, rol) for ad, rol in eksik))
    haric, ekle = _karar_oku(durum, tanimsiz)

    # Calisma kopyasi kurulum adiminda cikarildi; burada bir kez daha
    # denenmesi zararsiz ve o adim atlanmissa (eski oturum) kurtarici.
    kopya_not = _calisma_kopyasi_kur(durum)

    oneriler = durum.get("_tanimsiz_oneri") or {}
    eklenen, basarisiz = [], []
    for satir in ekle:
        oneri = (oneriler.get(satir["kolon"]) or {}).get("aciklama") or ""
        # Kategori BOS gider: kart kategori sormuyor, uydurma bir kovaya
        # koymaktansa kategorisiz birakmak dogru.
        tamam, neden = sozluk_calisma.satir_ekle(
            durum, satir["kolon"], satir["aciklama"], "", oneri=oneri)
        if tamam:
            eklenen.append(satir["kolon"])
        else:
            # Yazilamayan tanim SESSIZCE surece dahil edilmez: kolon
            # varsayilana duser ve neden yazilamadigi kullaniciya soylenir.
            basarisiz.append((satir["kolon"], neden))
            haric.append(satir["kolon"])

    # ZORUNLU SUREC DISI da ekleniyor: bu adim listeyi TAMAMEN yeniden
    # yaziyor ve tek degerli donem kolonu gibi zorunlu disi kalanlar
    # aradan siyrilip geri donuyordu.
    haric = sorted(set(haric) | platform_disi_kolonlar(durum))
    durum["haric_kolonlar"] = haric
    durum["_aciklamasiz"] = [k for k in tanimsiz if k not in set(eklenen)]
    # PLATFORMUN yazdirdigi tanimlarin kaydi. Kullanicinin kendi
    # sozlugunde bastan duran tanimlardan ayirt edilebilmesi icin
    # tutuluyor: yalnizca bu listedekiler geri alinabilir
    # (bkz. _donem_kolonunu_disla).
    durum["_sozluge_eklenen"] = sorted(
        set(str(k) for k in (durum.get("_sozluge_eklenen") or [])) | set(eklenen))

    # METIN DONDURMEZ. "Veri seti ve sözlük bağlandı. 2 kolon sözlüğe
    # eklendi." diye ayri bir paragraf basmak, hemen ustundeki karttaki
    # kararin tekrariydi; karttaki rozet zaten ne yapildigini yaziyor.
    # Yalnizca ISTENENDEN FARKLI bir sey olduysa (bir tanim yazilamadi,
    # calisma kopyasi kurulamadi) metin doner — sessiz kalirsa kullanici
    # kolonun neden sureç disinda kaldigini bilemez.
    metin = ""
    if basarisiz:
        metin = ("Şu kolonlar sözlüğe eklenemedi ve süreç dışında "
                 "bırakıldı:\n" + "\n".join("  • %s: %s" % (a, n)
                                             for a, n in basarisiz))
    return (metin + kopya_not).strip()

# ===========================================================================
# MODELLEME TANIMLARI  (her modda)
# ===========================================================================
# Kolon listesi icin sema okumasi; tam tablo OKUNMAZ.
SEMA_LIMITI = 200

TANIM_KALIP = {
    "target": r"target\s*[:=]?\s*([a-z0-9_]+)",
    "id": r"\bid\s*[:=]?\s*([a-z0-9_]+)",
    "donem": r"donem\s*[:=]?\s*([a-z0-9_]+)",
}

def _veri_seti_kolonlari(durum):
    """Secili veri setinin kolon adlari. Okunamazsa bos liste.

    ONCE PROFILDEN: kolon listesi `kurulum` adiminda zaten cikarildi
    (profil["kolon_ozet"]). Eskiden bu fonksiyon her cagrildiginda
    veri setine gidiyordu ve modelleme tanimlari formu her acilisinda
    (ilk cizim, yeniden sorma, hata sonrasi) bir okuma daha demekti.
    Gercek bir Dataiku tablosunda her okuma onlarca saniye."""
    ozet = (durum.get("profil") or {}).get("kolon_ozet")
    if isinstance(ozet, list) and ozet:
        return [str(o["ad"]) for o in ozet
                if isinstance(o, dict) and o.get("ad")]
    ad = durum.get("veri_seti")
    if not ad:
        return []
    try:
        return [str(c) for c in _df_oku(ad, limit=SEMA_LIMITI).columns]
    except Exception:
        return []

def _tanimlar_formu(durum, meta=None):
    """Modelleme tanimlari formu. Onceki degerler varsa alanlar dolu gelir.

    Uc alan da SECILI VERI SETININ KOLONLARINDAN secilir. Eskiden bu form
    dataset arama combo'sunu kullaniyordu: kullaniciya hedef degisken
    yerine veri seti adlari oneriliyor ve secim yapilamiyordu.
    """
    m = meta or durum.get("meta") or {}
    kolonlar = _veri_seti_kolonlari(durum)
    p = _donem_adaylarini_hazirla(durum)

    # ADAY LISTELERI. Bos donerse TUM kolonlara dusulur ve nedeni
    # alanin altinda yazilir: veri setinde uygun kolon yoksa kullaniciyi
    # secim yapamaz halde birakmak dogru olmaz.
    hedef_aday = [k for k in (p.get("hedef_adaylari") or []) if k in kolonlar]
    kimlik_aday = [k for k in (p.get("kimlik_adaylari") or []) if k in kolonlar]

    # Kullanicinin onceki secimi listede yoksa yine de gorunmeli, aksi
    # halde form kendi dolu degerini gosteremez.
    def _ekle(liste, deger):
        if deger and deger in kolonlar and deger not in liste:
            return liste + [deger]
        return liste

    # Hedef ve kimlik olarak SECILMIS kolonlar donem listesine hic girmez
    # (bicim kontrolunden gecseler bile).
    secili = {m.get("target"), m.get("id")} - {None, ""}
    donem_aday = [k for k in (p.get("donem_adaylari") or [])
                  if k in kolonlar and k not in secili]
    hedef_liste = _ekle(hedef_aday, m.get("target")) if hedef_aday else kolonlar
    kimlik_liste = _ekle(kimlik_aday, m.get("id")) if kimlik_aday else kolonlar
    # DONEM: yalnizca tarih ya da donem bicimli kolonlar (bkz.
    # _donem_adaylari). Aday yoksa liste bos kalir ve nedeni yazilir;
    # tum kolonlara DUSULMEZ - kimlik ya da hedefin donem secilmesi
    # zamansal bolmeyi sessizce bozardi.
    donem_liste = _ekle(donem_aday, m.get("donem"))
    donem_not = ("" if donem_aday else
                 "Veri setinde dönem bilgisi taşıyan bir kolon "
                 "bulunamadı (202501 gibi sayı ya da metin, 2025-01 ya "
                 "da tarih). Zamansal bölme kurulamaz.")

    hedef_not = ("" if hedef_aday else
                 "Veri setinde 0/1 değerli kolon bulunamadı; tüm kolonlar "
                 "listeleniyor.")
    kimlik_not = ("" if kimlik_aday else
                  "Veri setinde tekrarsız kolon bulunamadı; tüm kolonlar "
                  "listeleniyor.")

    durum["_secim_alani"] = {
        "tip": "form",
        "baslik": "Modelleme tanımları",
        # ACIKLAMA ADIMIN METNINI DE TASIR. Eskiden ayni bilgi once bir
        # sohbet balonunda ("Devam etmek için hedef değişken ve kimlik
        # kolonu bilgisine ihtiyacım var...") sonra kartta yaziyordu;
        # kullanici ayni cumleyi iki kez okuyordu.
        "aciklama": "Hedef değişkeni ve kimlik kolonunu veri setinin "
                    "kolonları arasından seçin. Dönem kolonu zorunlu değil; "
                    "verirseniz zamansal bölme kurulabilir ve stabilite "
                    "ölçülebilir.",
        # "ipucu" KALDIRILDI. Kartta uc acilir liste duruyor; altina bir
        # de "target <kolon> id <kolon>" ornek satiri koymak, formu
        # doldurmanin yaninda bir de yazarak girme yolu varmis izlenimi
        # veriyordu. Yazarak girme yolu DURUYOR (bkz. TANIM_KALIP), yalniz
        # reklami yapilmiyor.
        "buton": "Tanımları Onayla",
        "kolonlar": kolonlar,
        # ALAN BAZLI LISTE. "secenekler" varsa on yuz o alanda YALNIZCA
        # onu gosterir; yoksa ortak "kolonlar" listesine duser (eski
        # istemciyle uyum). Donem kolonu filtrelenmiyor: donem sayisal da
        # olabilir metin de, tek kural "az sayida farkli deger" olurdu ve
        # bu kural yillik/aylik setlerde yaniltici.
        "alanlar": [
            {"ad": "target", "etiket": "Hedef değişken", "kaynak": "kolon",
             "deger": m.get("target") or "", "secenekler": hedef_liste,
             "ipucu": "Yalnızca 0/1 değerli kolonlar", "not": hedef_not},
            {"ad": "id", "etiket": "Kimlik kolonu", "kaynak": "kolon",
             "deger": m.get("id") or "", "secenekler": kimlik_liste,
             "ipucu": "Yalnızca tekrarsız kolonlar", "not": kimlik_not},
            {"ad": "donem", "etiket": "Dönem kolonu (opsiyonel)",
             "kaynak": "kolon", "zorunlu": False,
             "deger": m.get("donem") or "", "secenekler": donem_liste,
             "ipucu": "Dönem bilgisi taşıyan kolonlar: 202501 (sayı, metin ya da kategori), 2025-01, tarih",
             "not": donem_not},
        ],
        "sablon": "target {target} id {id} donem {donem}",
    }


def tanimlar_girdi(durum, mesaj, yeniden_sor=False):
    """yeniden_sor=True ('Değiştir'): mevcut degerlerle DOLU form acilir.

    Eskiden 'Değiştir' cikissiz kaliyordu: bilgi durum["meta"]'dan
    okundugu icin bos mesajla True donuyor, form hic acilmiyordu."""
    if yeniden_sor:
        _tanimlar_formu(durum)
        return False, ""

    norm = niyet_kural.normalize(mesaj)
    meta = dict(durum.get("meta") or {})
    for anahtar, kalip in TANIM_KALIP.items():
        m = re.search(kalip, norm)
        if m:
            meta[anahtar] = mesaj[m.start(1):m.end(1)]

    # Mod A: birlestirme planindan anahtar ve donem otomatik doldurulur
    plan = (durum.get("birlestirme") or {}).get("plan") or {}
    ana = plan.get("ana_tablo") or {}
    if ana and "id" not in meta and ana.get("anahtar"):
        meta["id"] = ana["anahtar"][0]
    if ana and "donem" not in meta and ana.get("donem_kolon"):
        meta["donem"] = ana["donem_kolon"]

    if durum.get("veri_seti") and meta:
        try:
            # Kolon listesi profilden; veri setine gitmeye gerek yok
            # (bkz. _veri_seti_kolonlari).
            kolonlar = set(_veri_seti_kolonlari(durum))
            if not kolonlar:
                kolonlar = set(_df_oku(durum["veri_seti"], limit=5).columns)
            hatali = [(k, v) for k, v in meta.items() if v not in kolonlar]
            if hatali:
                for k, _ in hatali:
                    meta.pop(k, None)
                durum["meta"] = meta
                _tanimlar_formu(durum, meta)
                return False, ("Şu kolonları veri setinde bulamadım: %s"
                               % ", ".join("%s → %s" % x for x in hatali))
        except Exception:
            pass

    # ADAY DISI SECIM REDDEDILIR. Form artik yalnizca uygun kolonlari
    # listeliyor, ama serbest yazarak da girilebiliyor ("target X id Y").
    # Kontrol yalnizca listede olmasi yetmedigi icin burada tekrarlaniyor:
    # kullanicinin hedefle kimligi yer degistirmesi, platformun sonradan
    # "pozitif oran %0,00" diye rapor ettigi asil hataydi.
    p = _donem_adaylarini_hazirla(durum)
    aday_kurali = [
        ("target", p.get("hedef_adaylari"), "hedef değişken",
         "yalnızca 0/1 değerli bir kolon olabilir"),
        ("id", p.get("kimlik_adaylari"), "kimlik kolonu",
         "yalnızca tekrarsız (her satırda farklı) bir kolon olabilir"),
        ("donem", p.get("donem_adaylari"), "dönem kolonu",
         "yalnızca dönem bilgisi taşıyan (202501 gibi sayı, metin ya da "
         "kategori; 2025-01 ya da tarih) ve birden fazla değer taşıyan "
         "bir kolon olabilir"),
    ]
    uygunsuz = []
    for anahtar, adaylar, etiket, kural in aday_kurali:
        deger = meta.get(anahtar)
        # Aday listesi BOSSA kural uygulanmaz: veri setinde uygun kolon
        # yok demektir, secimi engellemek kullaniciyi kilitler.
        if deger and adaylar and deger not in adaylar:
            uygunsuz.append("%s (%s) %s" % (deger, etiket, kural))
            meta.pop(anahtar, None)

    if uygunsuz:
        durum["meta"] = meta
        _tanimlar_formu(durum, meta)
        return False, ("Seçim uygun değil:\n"
                       + "\n".join("  • " + u for u in uygunsuz))

    durum["meta"] = meta
    eksik = [k for k in ("target", "id") if k not in meta]
    if eksik:
        _tanimlar_formu(durum, meta)
        # METIN YOK, YALNIZ FORM: kartin basligi ve aciklamasi ayni seyi
        # zaten soyluyor (bkz. _tanimlar_formu). Hangi alanin eksik oldugu
        # formda bos duran alandan gorulur. Ornek satir hic gosterilmiyor;
        # baska bir calismanin kolon adi hicbir yerde gecmiyor.
        return False, ""
    durum["_secim_alani"] = None
    return True, None

def tanimlar_uygula(durum):
    """Tanimlari uygular ve hedefin tipini/dagilimini cikarir.

    NEDEN BURADA, PLANDA DEGIL: bu adimin ayri bir "plan" asamasi YOK.
    Form doldurulup onaylandiginda karar verilmis oluyor; ustune bir de
    "Modelleme tanımları: ... Doğru mu?" ozeti basmak ayni onayi ikinci
    kez sormaktan baska bir is yapmiyordu ve ozetledigi uc satir
    (hedef, kimlik, donem) sag paneldeki Veri seti kartinda zaten var.

    METIN DONDURMEZ — yalnizca DIKKAT EDILMESI GEREKEN bir sey varsa
    yazar. Sonraki adimin (bolme) dayandigi `_donemler` burada
    hesaplaniyor; hesap kaybolmadi, yalnizca anlatimi kalkti."""
    m = durum["meta"]
    df = modelleme_df(durum)
    p = durum.get("profil") or {}

    y = pd.to_numeric(df[m["target"]], errors="coerce")
    tekil = int(y.nunique(dropna=True))
    if tekil <= 2:
        oran = 100.0 * float((y > 0).mean())
        p["hedef_tip"] = "binary"
        # Event rate hedef_ozet metninin ICINE gomulu; panelin metni geri
        # ayristirmasi gerekmesin diye AYRI sayisal alan olarak da yazilir.
        p["event_rate"] = round(oran, 2)
        p["hedef_ozet"] = "İki sınıflı (0/1) · %%%s pozitif" % _ond(oran, 2)
    else:
        p["hedef_tip"] = "surekli"
        p["event_rate"] = None
        p["hedef_ozet"] = "Sürekli · %s farklı değer" % _sayi(tekil)

    # Donem araligi: VERI sekmesi min/maks donemi buradan okur.
    p.pop("donem_min", None)
    p.pop("donem_maks", None)
    p.pop("donem_adet", None)
    _kimlik_duplicate(durum, df, p)
    durum["profil"] = p

    # VERI SETINDE HAZIR DURAN BOLME. Tablo zaten okunmusken araniyor;
    # ayri bir okuma maliyeti yok. Bulunursa bolme kartinda ucuncu bir
    # secenek olarak cikar - dayatma degil, secenek (kullanici karari:
    # "yine seçime göre geri dönmek istersem diye").
    durum.pop("_hazir_bolme", None)
    try:
        hazir = hazir_bolme_bul(df)
    except Exception:
        hazir = None
    if hazir:
        durum["_hazir_bolme"] = hazir
        # BOLME KOLONLARI MODELE GIRMEZ: "bu satir test" bilgisini
        # tasiyan bir kolon, hedefi dolayli olarak sizdirir ve modelin
        # basarisini olmadigi kadar yuksek gosterir. Otomatik surec
        # disina aliniyor; kullanici isterse isareti kaldirabilir
        # (kilitli DEGIL) ama neden isaretlendigini bolme kartinda
        # okuyor.
        mevcut = {str(k) for k in (durum.get("haric_kolonlar") or [])}
        durum["haric_kolonlar"] = sorted(mevcut | set(hazir["kolonlar"]))

    donem = m.get("donem")
    donem_not = "belirtilmedi"
    durum.pop("_donem_dusuruldu", None)
    if donem and donem in df.columns:
        # Bolmeyle AYNI normallestirme ve ZAMAN sirasi (bkz.
        # birlestirme.donem_degeri / donem_sirala).
        donemler = birl_mod.donem_sirala(
            birl_mod.donem_serisi(df[donem]).dropna().unique().tolist())
        durum["_donemler"] = donemler
        if donemler:
            p["donem_min"] = donemler[0]
            p["donem_maks"] = donemler[-1]
            p["donem_adet"] = len(donemler)
        donem_not = "%s: %s farklı dönem" % (donem, _sayi(len(donemler)))

        # TEK DEGERLI DONEM KOLONU DONEM KOLONU DEGILDIR (kullanici
        # karari). Bir tek degeri olan kolon ne zamansal bolme kurar, ne
        # stabilite olcer, ne de modele bilgi tasir - her satirda ayni
        # sabiti tekrar eder. Tanim olarak birakmak bir seri yanlis
        # sonuca yol aciyordu: bolme karti "Test Dönem Sayısı" soruyor,
        # sari kutu "dönem kolonu tanımlı, zamansal test daha uygun"
        # diye oneriyor ve kolon rol kilidi yuzunden surec disi bile
        # birakilamiyordu.
        #
        # Bu yuzden tanim DUSURULUYOR ve kolon ZORUNLU surec disi
        # oluyor. Sessiz yapilmiyor: _donem_dusuruldu kullaniciya
        # gosterilen uyariyi ve kilidin sebebini tasiyor.
        if len(donemler) < 2:
            durum["_donem_dusuruldu"] = donem
            m.pop("donem", None)
            durum["meta"] = m
            durum["_donemler"] = []
            donem_not = "%s: tek değer taşıdığı için dönem kolonu sayılmadı" % donem
            _donem_kolonunu_disla(durum, donem)
    else:
        durum["_donemler"] = []

    # UYARILAR: sessiz gecilmesi pahaliya patlayacak olanlar. Geri kalan
    # bilgi sag paneldeki Veri seti kartinda duruyor.
    uyari = []
    if p.get("hedef_tip") == "surekli":
        uyari.append("Hedef değişken iki sınıflı (0/1) değil (%s). "
                     "Sınıflandırma adımları bu hedefle "
                     "çalışmayabilir." % p["hedef_ozet"])
    elif p.get("event_rate") is not None:
        oran = float(p["event_rate"])
        if oran < 1.0 or oran > 99.0:
            uyari.append("Hedefin pozitif oranı %%%s: sınıflar çok dengesiz."
                         % _ond(oran, 2))
    # UYARI SIRASI: once dusurme (olduysa), sonra "donem yok" hali.
    # Dusurulen kolonda m["donem"] artik BOS oldugu icin ikisi ayni
    # kosula duser; dusurmeyi ayri yazmak zorunlu, yoksa kullanici
    # sectigi kolonun nereye gittigini goremez.
    dusurulen = durum.get("_donem_dusuruldu")
    if dusurulen:
        uyari.append("%s dönem kolonu olarak seçildi ama tek değer "
                     "taşıyor. Her satırda aynı sabiti tekrar ettiği için "
                     "dönem kolonu sayılmadı ve süreç dışına alındı; "
                     "listede işareti kaldırılamaz. Bölme rastgele "
                     "kurulacak, stabilite ölçümü bu çalışmada "
                     "yapılamayacak." % dusurulen)
    elif not donem:
        uyari.append("Dönem kolonu verilmedi: zamansal bölme ve "
                     "stabilite ölçümü bu çalışmada yapılamaz.")
    tekrar = p.get("duplicate_kimlik")
    if tekrar:
        uyari.append("Kimlik kolonunda %s satır tekrar ediyor; aynı kayıt "
                     "birden fazla satırda görünüyor." % _sayi(int(tekrar)))
    return "\n\n".join(uyari)

# ===========================================================================
# SOZLUK TEYIDI  (bolme oncesi son kontrol)
# ===========================================================================
# NEDEN AYRI BIR ADIM
#   Bolme, sizinti sinirini ceken adimdir: o cizgiden sonra degisken
#   listesi ve sozluk tanimlari artik kolayca degistirilemez. Kullanici o
#   ana kadar sag paneldeki VERI & SOZLUK sekmesini hic acmamis olabilir;
#   bir kolonu surec disina almak ya da bir tanimi duzeltmek icin SON
#   firsat burasi. Adim bir sey HESAPLAMIYOR, bir ani KAYDEDIYOR: neyin,
#   ne zaman ve hangi listeyle teyit edildigini.
#
# NEDEN plan=None
#   Formun kendisi onaydir (bkz. akis_sohbet._adima_gir). Kart zaten
#   "son kez gozden gecirin" diyor; ustune bir de "Doğru mu?" ozeti
#   basmak ayni onayi ikinci kez sormakti.
# TEYIT KARTI ARTIK SOHBETTE (kullanici karari). Eskiden kart kullaniciyi
# sag panele gonderiyordu; karar sohbette, sag panel yalnizca aciklama
# veriyor. Liste kartin icinde: aciklamalar duzenlenebilir, surec disi
# birakilacak kolonlar isaretlenebilir.
TEYIT_ACIKLAMASI = ("Değişken listesini ve sözlük tanımlarını son kez "
                    "gözden geçirin. Açıklamaları buradan düzenleyebilir, "
                    "süreç dışında bırakmak istediğiniz kolonları "
                    "işaretleyebilirsiniz.")


def _teyit_sayilari(durum):
    """(degisken, haric, tanimli).

    VERI SETI OKUNMAZ: kolon listesi profil adiminin biraktigi
    kolon ozetinden, tanimlar sozlugun CALISMA KOPYASINDAN gelir —
    kullanicinin bu oturumda ekledigi/duzelttigi tanimlar da sayilsin.

    "tanimli" = veri setinde olup sozlukte DOLU bir aciklamasi olan
    kolon. Hesap akis_panel.sozluk_kapsami'nda, TEK YERDE duruyor: ayni
    soru sag paneldeki kapsam satirinda, bu ozette ve aciklamasiz
    kolonlarin isaretlenmesinde soruluyor; uc ayri kural ayni ekranda
    uc farkli sayi uretiyordu.

    ONEMLI: sozlukte SATIRI olup aciklamasi BOS olan kolon tanimli
    SAYILMAZ - kullanici icin "tanım yok" demek o kolonun ne oldugunu
    bilmemek demek; bos bir sozluk satiri bunu degistirmiyor."""
    from fe_agent import akis_panel
    p = durum.get("profil") or {}
    kolonlar, tanimli, _tanimsiz = akis_panel.sozluk_kapsami(durum)

    haric = {str(k) for k in (durum.get("haric_kolonlar") or [])}
    degisken = len(kolonlar) or int(p.get("kolon") or 0)
    sayi = len(tanimli) if kolonlar else int(p.get("eslesen") or 0)
    return degisken, len(haric), sayi


def tanimsiz_kolonlari_isaretle(durum):
    """Aciklamasi olmayan kolonlari SUREC DISI olarak isaretler.

    Kullanici karari: "sözlükte açıklaması yoksa droplanacaktır gibi bir
    selection box da otomatik seçili gelsin, istenirse kalsın veri
    setinde, opsiyonlu olsun." Yani varsayilan DUSUR, ama karar
    kullanicinin: kutuyu kaldirirsa kolon veri setinde kalir.

    BIR KEZ CALISIR. Kart her tazelendiginde yeniden isaretleseydi,
    kullanicinin kaldirdigi kutu bir sonraki cizimde geri gelirdi -
    yani kullanicinin karari sessizce geri alinirdi. Damga durumda
    duruyor, "Geri Dön" ile geri gelindiginde de tekrar basmaz.

    Doner: yeni isaretlenen kolon adlari (bos liste = degisiklik yok)."""
    if durum.get("_tanimsiz_haric_uygulandi"):
        return []
    from fe_agent import akis_panel
    kolonlar, _tanimli, tanimsiz = akis_panel.sozluk_kapsami(durum)
    if not kolonlar:
        return []          # kolon ozeti yok: isaretlenecek bir sey bilinmiyor

    # Hedef / kimlik / donem ASLA otomatik dusurulmez: bunlar modelleme
    # tanimlarinda secildi ve tanimlari zaten zorunlu tutuluyor.
    korunan = {v for v in (durum.get("meta") or {}).values() if v}
    mevcut = {str(k) for k in (durum.get("haric_kolonlar") or [])}
    yeni = [a for a in tanimsiz if a not in mevcut and a not in korunan]
    if yeni:
        durum["haric_kolonlar"] = sorted(mevcut | set(yeni))
    durum["_tanimsiz_haric_uygulandi"] = True
    return yeni


def teyit_ozeti(durum):
    """Kartin tek satirlik ozeti: '1.042 değişken · 2 süreç dışı · ...'.

    ACIK ISIM: kart disindan da cagriliyor. Sag panelde bir kolon surec
    disina alininca (/haric_kolonlar) kartin sayilari degisiyor; uc bu
    fonksiyonla tazesini donuyor ki kart eski sayiyi gostermesin."""
    degisken, haric, tanimli = _teyit_sayilari(durum)
    return "%s değişken · %s süreç dışı · %s tanımlı" % (
        _sayi(degisken), _sayi(haric), _sayi(tanimli))


def _tip_ornegi(durum):
    """Donusum tekliflerinin uzerinde hesaplandigi KUCUK ornek.

    Tam tabloyu okumuyor: kart acilirken 1.042 kolonun her biri icin
    alti donusum denenecek; ornek okuma bunu saniyenin altinda tutuyor.
    Ornekte gorunmeyen bozuk deger, secim ANINDA tam kolonla yapilan
    denetimde (tip_secimi_dogrula) yakalaniyor. Okuma basarisiz olursa
    None doner ve kart donusum secenegi gostermez - yanlis teklif
    gostermektense hic gostermemek dogru."""
    ad = durum.get("veri_seti")
    if not ad:
        return None
    try:
        return _df_oku(ad, limit=tip_donusum.ORNEK_SATIR)
    except Exception:
        return None


# Hedef / kimlik / donem kolonlarinin tipi MODELLEME TANIMLARI adiminda
# zaten denetlendi: hedef 0-1 olmak zorunda, kimlik tekil olmak zorunda,
# donem siralanabilir olmak zorunda. Burada tip degistirilirse o
# denetimler gecersizlesir ama kullaniciya hicbir sey soylenmez - hedefi
# "kategorik"e cevirmek event rate hesabini sessizce bozardi. Bu yuzden
# uc kolonun donusumleri kilitli gosteriliyor, sebebiyle birlikte.
# Surec disi kutusunun kilit sebebi (tip kilidinden AYRI metin: orada
# "yalnizca tarihe cevrilebilir" diyoruz, burada hic birakilamiyor).
ROL_KILIT_SEBEBI = {
    "target": "hedef değişken süreç dışı bırakılamaz",
    "id": "kimlik kolonu süreç dışı bırakılamaz",
    "donem": "dönem kolonu süreç dışı bırakılamaz",
}

# Tek degerli donem kolonunun kilit sebebi. Yukaridakilerin TERSI yonde
# bir kilit: bu kolon surec disi birakilmak ZORUNDA, iceri alinamaz.
DONEM_TEK_DEGER_SEBEBI = (
    "dönem kolonu olarak seçildi ama tek değer taşıyor; her satırda aynı "
    "sabiti tekrar ettiği için modele bilgi katmaz ve süreç dışı bırakılır")


def _donem_kolonunu_disla(durum, kolon):
    """Tek degerli donem kolonunu ZORUNLU surec disi yapar.

    Uc is birden yapiyor:
      1. haric_kolonlar'a ekler (veri setinden duser),
      2. kullanicinin bu kolon icin sectigi tip donusumunu iptal eder -
         disarida kalan bir kolonu cevirmenin anlami yok ve donusum
         dogrulamasi adimi bosuna durdururdu,
      3. PLATFORMUN kendi eklettigi sozluk aciklamasini siler. Kullanici
         "otomatik sözlük açıklaması varsa kaldırılmalı" dedi: surec
         disinda kalan bir kolon icin platformun yazdirdigi tanimi
         sozlukte birakmak, artik kullanilmayan bir degiskeni tarif eden
         bir satir demekti.

         YALNIZCA PLATFORMUN EKLEDIGI SILINIR (durum["_sozluge_eklenen"]
         listesi). Kullanicinin KENDI sozlugunde bastan duran tanima
         DOKUNULMAZ: orijinal sozluk platformun silecegi bir sey degil
         ve calisma kopyasindan silmek de kullanicinin verisini sessizce
         atmak olurdu.

    NORMAL AKISTA 3. MADDE HIC CALISMAZ: "tanimlar" adimi "sozluk_tanim"
    adimindan ONCE gelir, yani dusurme karari tanim yazilmadan once
    verilir. Madde, kullanici geri donup dönem kolonunu sonradan
    degistirdiginde devreye giriyor."""
    kolon = str(kolon or "").strip()
    if not kolon:
        return
    mevcut = {str(k) for k in (durum.get("haric_kolonlar") or [])}
    mevcut.add(kolon)
    durum["haric_kolonlar"] = sorted(mevcut)

    # Surec disi kolonun tip donusumu anlamsiz; secili kalirsa teyit
    # adimindaki dogrulama bosuna calisir ve takilirsa adimi durdurur.
    secilen = dict(durum.get("tip_donusum") or {})
    if secilen.pop(kolon, None) is not None:
        durum["tip_donusum"] = secilen

    eklenen = [str(k) for k in (durum.get("_sozluge_eklenen") or [])]
    if kolon in eklenen:
        try:
            from fe_agent import sozluk_calisma
            sozluk_calisma.tanim_yaz(durum, kolon, "")
        except Exception:
            pass
        durum["_sozluge_eklenen"] = [k for k in eklenen if k != kolon]


def _donem_tek_deger_mi(durum, ad):
    """Bu kolon, tek deger tasidigi icin dusurulen donem kolonu mu?"""
    return bool(durum.get("_donem_dusuruldu")) \
        and str(durum["_donem_dusuruldu"]) == str(ad)


def zorunlu_disi_kolonlar(durum):
    """SUREC DISINDA KALMAK ZORUNDA olan kolonlar (kilitli).

    Su an tek uye: tek deger tasidigi icin dusurulen donem kolonu.
    Ayri bir fonksiyon, cunku haric listesi UC AYRI yerde bastan
    yaziliyor (sozluk tanimlari adimi, /haric_kolonlar ucu, teyit
    karti) ve her birinde tek tek hatirlanmasi gereken bir kural
    sessizce dusuyordu."""
    ad = str((durum or {}).get("_donem_dusuruldu") or "").strip()
    return {ad} if ad else set()


def platform_disi_kolonlar(durum):
    """Platformun KENDI surec disi biraktiklari.

    zorunlu_disi_kolonlar'a EK OLARAK veri setinde hazir duran bolme
    kolonlarini da kapsar. Fark: bunlar KILITLI DEGIL - kullanici
    isterse isareti kaldirabilir. Yine de listede kalmalari gerekiyor,
    cunku "sozluk tanimlari" adimi haric listesini TAMAMEN yeniden
    yaziyor ve aradan siyrilip geri donuyorlardi. O adim kullanicinin
    teyit kartinda isareti kaldirmasindan ONCE calisiyor, dolayisiyla
    burada eklemek kullanicinin kararini ezmiyor."""
    disi = set(zorunlu_disi_kolonlar(durum))
    hazir = (durum or {}).get("_hazir_bolme")
    if isinstance(hazir, dict):
        disi |= {str(k) for k in (hazir.get("kolonlar") or [])}
    return disi

TIP_KILIT_SEBEBI = {
    "target": "hedef değişken - tipi modelleme tanımlarında belirlendi",
    "id": "kimlik kolonu - tipi modelleme tanımlarında belirlendi",
    "donem": "dönem kolonu - yalnızca tarihe çevrilebilir",
}


def _tip_rolu(durum, ad):
    """Kolonun modelleme rolu ("target"/"id"/"donem") ya da None."""
    m = durum.get("meta") or {}
    for rol in ("target", "id", "donem"):
        if m.get(rol) and str(m[rol]) == ad:
            return rol
    return None


def _tip_kilidi(durum, ad, kod):
    """Rol yuzunden kilitliyse sebep, degilse None.

    Donem kolonunda TARIHE cevirmek mesru ve sik gereken bir islem
    (202401 gibi sayisal donemler); kategorige cevirmek bolmeyi
    bozacagi icin kapali."""
    rol = _tip_rolu(durum, ad)
    if not rol:
        return None
    if rol == "donem" and tip_donusum.hedef_tip(kod) == "tarih":
        return None
    return TIP_KILIT_SEBEBI[rol]


def teyit_satirlari(durum):
    """Teyit kartindaki degisken listesi: ad, tip, tanim, surec disi mi,
    tip donusum secenekleri ve secilmis donusum.

    ACIK ISIM: karar verildikten sonra (bir kolon surec disina alinip
    tanimi duzeltilince) kartin tazelenmesi gerekiyor."""
    from fe_agent import akis_panel
    tablo = akis_panel.feature_tablo(durum)
    haric = set(durum.get("haric_kolonlar") or [])
    secilen = durum.get("tip_donusum") or {}
    ornek = _tip_ornegi(durum)
    satirlar = []
    for r in tablo.get("satirlar") or []:
        ad = str(r.get("feature") or "")
        # Secilmis donusum varsa gosterilen tip ZATEN hedef tip olmali;
        # aksi halde kullanici "tarih" sectikten sonra satirda hala
        # "kategorik" goruyor ve secimin tutmadigini saniyordu.
        # (_tip_ozetini_tazele bunu kolon_ozet'e de yaziyor, ama tablo
        # baska bir kaynaktan gelirse diye burada da garanti ediliyor.)
        kod = secilen.get(ad) or ""
        kaynak_tip = _kaynak_tipi(durum, ad) or (r.get("tip") or "")
        tip = (tip_donusum.hedef_tip(kod) or kaynak_tip) if kod else kaynak_tip
        donusumler = []
        if ornek is not None and ad in ornek.columns:
            # Teklifler daima ORIJINAL tip uzerinden uretilir: secim
            # henuz veriye islenmedi, kolon hala kaynak tipinde duruyor.
            donusumler = tip_donusum.secenekler(ornek[ad], kaynak_tip)
            for d in donusumler:
                sebep = _tip_kilidi(durum, ad, d["kod"])
                if sebep:
                    d["uygun"] = False
                    d["sebep"] = sebep
        satirlar.append({
            "kolon": ad,
            "tip": tip,
            "kaynak_tip": kaynak_tip,
            "tanim": r.get("tanim") or "",
            # NULL ORANI KARARIN YANINDA: kullanici surec disi birakma
            # karari verirken cogu zaman tam da bu sayiya bakiyor
            # ("%98 boş kolonu zaten almayayım"). Sag panele bakip
            # geri donmek gerekmesin diye karar satirinda, kutunun
            # hemen solunda duruyor. 0-1 araligindaki oran; bicimleme
            # on yuzde.
            "null_oran": r.get("null_oran"),
            # "disi": isaretli ise kolon SUREC DISI. Dogrulama kartinda
            # kutu "sozluge ekle" demekti; burada tam tersi karar.
            "disi": ad in haric,
            # SUREC DISI BIRAKILAMAZ: hedef / kimlik / donem modelleme
            # tanimlarinda secildi. Hedefi surec disi birakmak modeli
            # hedefsiz, kimligi birakmak bolmeyi kimliksiz birakirdi -
            # kullanici bunu tek tiklamayla yapabiliyordu ve hicbir
            # yerde uyari cikmiyordu.
            # KILIT IKI YONLU: rol kolonlari (hedef/kimlik/donem) DISARI
            # cikarilamaz; tek degerli oldugu icin dusurulen donem
            # kolonu ise ICERI alinamaz. Ikisi de "kutuya dokunma"
            # demek, sebepleri farkli - ipucunda yazan sebep de farkli.
            "disi_kilitli": bool(_tip_rolu(durum, ad))
                            or _donem_tek_deger_mi(durum, ad),
            "disi_kilit_sebebi": (
                DONEM_TEK_DEGER_SEBEBI if _donem_tek_deger_mi(durum, ad)
                else ROL_KILIT_SEBEBI.get(_tip_rolu(durum, ad), "")),
            "donusum": kod,
            # Kilitli (gecmisten cizilen) kartta acilir liste yok; orada
            # secimin ETIKETI yaziyor. Etiket satirda durmazsa, teklif
            # listesi saklanmadigi icin geri gelemezdi.
            "donusum_etiket": ((tip_donusum.DONUSUMLER.get(kod) or {})
                               .get("etiket", "") if kod else ""),
            "donusumler": donusumler,
        })
    return satirlar, bool(tablo.get("duzenlenebilir"))


def teyit_kartini_tazele(durum, kolon=None, tanim=None):
    """ACIK teyit kartinin govdesini durumdaki son kararlarla tazeler.

    NEDEN GEREKLI
      Kartin govdesi durum["_secim_alani"]'nda duruyor ve /durum onu
      OLDUGU GIBI donuyor. Ama karttaki uc karar - tip degisikligi,
      surec disi isareti, sozluk tanimi - kendi uclarindan geliyor;
      arada hic /mesaj gitmiyor, yani govdeyi tazeleyen kod hic
      calismiyordu. Sonuc: kullanici adimin ORTASINDA F5 atinca o
      adimda verdigi butun kararlar ekrandan siliniyordu.

    NEDEN KART BASTAN URETILMIYOR
      _teyit_karti her cagrildiginda 1.042 kolon icin alti donusum
      deniyor. Her onay kutusu tiklamasinda bunu yapmak kartin
      kendisini kullanilmaz hale getirirdi. Burada yalnizca DEGISEN
      alanlar yerinde yamaniyor; donusum TEKLIFLERI (secenek listesi)
      degismedigi icin ellenmiyor."""
    alan = durum.get("_secim_alani")
    if not isinstance(alan, dict) or alan.get("tip") != "teyit":
        return
    dg = alan.get("degiskenler")
    if not isinstance(dg, dict):
        return
    haric = {str(k) for k in (durum.get("haric_kolonlar") or [])}
    secilen = durum.get("tip_donusum") or {}
    hedef = None if kolon is None else str(kolon).strip()
    for s in dg.get("satirlar") or []:
        if not isinstance(s, dict):
            continue
        ad = str(s.get("kolon") or "")
        s["disi"] = ad in haric
        kod = secilen.get(ad) or ""
        s["donusum"] = kod
        s["donusum_etiket"] = ((tip_donusum.DONUSUMLER.get(kod) or {})
                               .get("etiket", "") if kod else "")
        s["tip"] = ((tip_donusum.hedef_tip(kod) or s.get("kaynak_tip") or "")
                    if kod else (s.get("kaynak_tip") or s.get("tip") or ""))
        if hedef and ad == hedef and tanim is not None:
            s["tanim"] = str(tanim)
    alan["ozet"] = teyit_ozeti(durum)


# ---------------------------------------------------------------------------
# EXCEL CIKTISI  -  degisken listesi
# ---------------------------------------------------------------------------
# NEDEN VAR
#   Sozluk teyidi kaydedildikten sonra elde 1.042 satirlik, uzerinde
#   calisilmis bir liste kaliyor: hangi kolon hangi tipte, sozlukte ne
#   yaziyor, hangisi surec disi. Bu liste yalnizca ekranda kalmamali -
#   kullanici onu ekibe gonderiyor, modelleme dokumanina ekliyor,
#   uzerinde offline calisiyor.
#
# IKI AYRI GORUNUM, TEK URETICI
#   Sohbetteki karar tablosu ALTI kolon (tip degisikligi ve surec disi
#   karari orada veriliyor); sag panel yalnizca UC kolon gosteriyor
#   (orada karar yok, aciklama var). Indirilen dosya da bakilan yerle
#   ayni olmali; aksi halde "ekranda gordugum tablo bu degil" denir.
TEYIT_EXCEL_ADI = "degisken_listesi.xlsx"
SOZLUK_EXCEL_ADI = "degisken_sozlugu.xlsx"

TEYIT_EXCEL_KOLONLARI = ["Değişken", "Tip", "Tip Değişikliği",
                         "Sözlük Tanımı", "Null Oranı", "Süreç Dışı"]
SOZLUK_EXCEL_KOLONLARI = ["Değişken", "Tip", "Sözlük Tanımı"]

# Excel'de "evet/hayır" okunur; True/False Turkce bir tabloda yabanci.
_DISI_METNI = {True: "evet", False: "hayır"}


def _excel_satirlari(durum, genis):
    """(kolonlar, satirlar, yuzde_sutunlari) - genis=True ise karar
    tablosu, False ise sag panelin uc kolonu."""
    satirlar, _duzenlenebilir = teyit_satirlari(durum)
    if not genis:
        return (list(SOZLUK_EXCEL_KOLONLARI),
                [[s["kolon"], s["tip"], s["tanim"]] for s in satirlar],
                ())
    govde = []
    for s in satirlar:
        oran = s.get("null_oran")
        govde.append([
            s["kolon"], s["tip"], s.get("donusum_etiket") or "",
            s["tanim"],
            None if oran is None else float(oran),
            _DISI_METNI[bool(s.get("disi"))],
        ])
    # 4: "Null Oranı" sutunu; deger 0-1 oraninda, Excel %%'yi kendi ekler.
    return list(TEYIT_EXCEL_KOLONLARI), govde, (4,)


def teyit_excel(durum, genis=True):
    """Degisken listesini .xlsx olarak uretir; bayt dizisi doner.

    genis=True  : sohbetteki karar tablosunun aynisi (alti kolon)
    genis=False : sag paneldeki aciklama tablosu (uc kolon)"""
    kolonlar, satirlar, yuzde = _excel_satirlari(durum, genis)
    return xlsx_yaz.tablo_xlsx(
        kolonlar, satirlar,
        sayfa_adi="Değişkenler" if genis else "Değişken Sözlüğü",
        yuzde_sutunlari=yuzde)


def amp_klasor_adi(durum):
    """Calismanin kayit klasoru: "v3".

    SADE KAYIT (kullanici karari: "amp içine tarihli garip sayılı bir
    dosya açmak saçma"). Bir calismanin PROJE_HAFIZASI'nda biraktigi her
    sey TEK klasorde: sozluk calisma kopyasi zaten /<calisma>/ altinda
    duruyordu, AMP_VERISETI ve AMP_SOZLUK da artik yaninda:

        PROJE_HAFIZASI/v3/AMP_VERISETI.csv
        PROJE_HAFIZASI/v3/AMP_SOZLUK.csv
        PROJE_HAFIZASI/v3/sozluk_calisma.csv

    Ayri bir AMP klasoru, tarih damgasi ya da SON.txt yok. Klasor adi
    "Çalışmalarım" listesindeki numarayla ayni.

    ESKI KAYITLAR: daha once "AMP/2026-09-21_1809_.../" altina yazmis bir
    calisma (durumda _amp_klasor dolu) ayni yere yazmaya devam eder;
    kullanici dosyalarini iki farkli yerde aramasin."""
    eski = (durum or {}).get("_amp_klasor") if isinstance(durum, dict) else None
    if eski:
        return "%s/%s" % (AMP_KLASOR, eski)
    return re.sub(r"[^A-Za-z0-9_-]", "",
                  str((durum or {}).get("_oturum_id") or "")) or "calisma"


def _amp_yolu(durum, ad):
    """PROJE_HAFIZASI icinde calismanin kendi klasorunde dosya yolu."""
    return "/%s/%s.csv" % (amp_klasor_adi(durum), ad)


def amp_ciktilarini_yaz(durum):
    """AMP_VERISETI ve AMP_SOZLUK'u YAZAR. Doner: {"veri":..., "sozluk":...}

    Her deger: {"ad", "dataset", "dosya"} - "dataset" doluysa akista o
    adla bir veri seti var ve oraya yazildi; degilse "dosya" PROJE
    HAFIZASI icindeki CSV yolu.

    NE ZAMAN: sozluk teyidi KAYDEDILDIGINDE. O an tablo son halini
    aliyor - tip donusumleri secildi, tanimlar yazildi, surec disi
    karari verildi. Daha once yazmak yarim bir tablo kaydetmek olurdu.

    KAYNAK TABLOYA DOKUNULMAZ: AMP_VERISETI platformun KENDI kopyasi;
    Mod A ve B'de kullanicinin orijinal tablosu oldugu gibi kalir."""
    sonuc = {}

    # --- veri seti: tip donusumleri uygulanmis TAM tablo ---------------
    # kaynak=True: KULLANICININ tablosunu okur. Varsayilan yol artik
    # AMP_VERISETI'ne bakiyor; bu fonksiyon onu URETEN taraf oldugu icin
    # kendi ciktisini kaynak alamaz (ikinci kaydette tablo kendi
    # kopyasindan turerdi).
    try:
        df = modelleme_df(durum, kaynak=True)
    except Exception as e:
        sonuc["veri"] = {"ad": AMP_VERI_ADI, "dataset": None, "dosya": None,
                         "hata": str(e)[:120]}
    else:
        yazildi, yedek = _yaz(AMP_VERI_ADI, df, _amp_yolu(durum, AMP_VERI_ADI))
        sonuc["veri"] = {"ad": AMP_VERI_ADI, "dataset": yazildi,
                         "dosya": yedek, "satir": int(len(df)),
                         "kolon": int(df.shape[1])}

    # --- sozluk: teyit tablosunun aynisi -------------------------------
    try:
        kolonlar, satirlar, _yuzde = _excel_satirlari(durum, True)
        tablo = pd.DataFrame(satirlar, columns=list(AMP_SOZLUK_KOLONLARI))
        del kolonlar
    except Exception as e:
        sonuc["sozluk"] = {"ad": AMP_SOZLUK_ADI, "dataset": None,
                           "dosya": None, "hata": str(e)[:120]}
    else:
        yazildi, yedek = _yaz(AMP_SOZLUK_ADI, tablo,
                              _amp_yolu(durum, AMP_SOZLUK_ADI))
        sonuc["sozluk"] = {"ad": AMP_SOZLUK_ADI, "dataset": yazildi,
                           "dosya": yedek, "satir": int(len(tablo))}

    sonuc["klasor"] = amp_klasor_adi(durum)
    # AMP_VERISETI veri seti TEK ve BUTUN calismalarin ortak veri seti.
    # Hangi calismanin en son yazdigi kaydediliyor; sonraki fazlar veri
    # setini yalnizca SAHIBI olan calismada okur (bkz.
    # akis_durum.modelleme_kaynagi). Yazilamazsa sessizce gecilir: o
    # zaman okuma kullanicinin kendi tablosuna duser, sonuc yine dogru.
    if (sonuc.get("veri") or {}).get("dataset"):
        amp_sahibi_yaz(durum)

    durum["amp_cikti"] = sonuc
    return sonuc


def amp_nerede(kayit):
    """Tek satirlik "nereye yazildi" metni; kayit yoksa None."""
    if not isinstance(kayit, dict):
        return None
    if kayit.get("dataset"):
        return "%s veri seti" % kayit["dataset"]
    if kayit.get("dosya"):
        return "PROJE_HAFIZASI%s" % kayit["dosya"]
    return "yazılamadı (%s)" % (kayit.get("hata") or "bilinmeyen hata")


def teyit_kaydedildi_mi(durum):
    """Sozluk teyidi KAYDEDILDI mi? Excel indirme bu kapiya bagli:
    kaydedilmemis bir listeyi indirmek, kullanicinin henuz vermedigi
    karari dosyaya yazmak olurdu."""
    return bool((durum or {}).get("teyit"))


def tip_secimi_dogrula(durum, kolon, kod):
    """Kullanici bir donusum secti: TAM KOLONLA dogrula ve kaydet.

    Doner: {tamam, tip, mesaj}. tamam=False ise secim KAYDEDILMEZ ve
    mesaj neyin takildigini soyler; ug eski secime geri doner.

    Bos kod ("") secimi geri almak demektir ve daima kabul edilir."""
    kolon = str(kolon or "").strip()
    if not kolon:
        return {"tamam": False, "mesaj": "Kolon belirtilmedi."}

    secilen = dict(durum.get("tip_donusum") or {})
    if not (kod or "").strip():
        secilen.pop(kolon, None)
        durum["tip_donusum"] = secilen
        _tip_ozetini_tazele(durum)
        teyit_kartini_tazele(durum)
        return {"tamam": True, "tip": _kaynak_tipi(durum, kolon), "mesaj": ""}

    if not tip_donusum.gecerli_kod(kod):
        return {"tamam": False, "mesaj": "Tanınmayan dönüşüm: %s" % kod}

    # Rol kilidi UC'TA da denetleniyor: karttaki kilit yalnizca gorsel,
    # istek dogrudan da gonderilebilir.
    kilit = _tip_kilidi(durum, kolon, kod)
    if kilit:
        return {"tamam": False,
                "mesaj": "'%s' bu şekilde çevrilemiyor: %s." % (kolon, kilit)}

    try:
        df = _df_oku(durum["veri_seti"])
    except Exception as e:
        return {"tamam": False,
                "mesaj": "Veri seti okunamadı (%s)." % str(e)[:80]}
    if kolon not in df.columns:
        return {"tamam": False,
                "mesaj": "'%s' kolonu veri setinde yok." % kolon}

    uygun, sebep = tip_donusum.denetle(df[kolon], kod)
    if not uygun:
        return {"tamam": False,
                "mesaj": "'%s' bu şekilde çevrilemiyor: %s." % (kolon, sebep)}

    secilen[kolon] = kod
    durum["tip_donusum"] = secilen
    _tip_ozetini_tazele(durum)
    teyit_kartini_tazele(durum)
    return {"tamam": True, "tip": tip_donusum.hedef_tip(kod), "mesaj": ""}


def _kaynak_tipi(durum, kolon):
    """Kolonun DONUSUMSUZ (profilden gelen) tipi.

    '_tip_kaynak' once bakilir: 'tip' alani secim yapildiktan sonra
    hedef tipi tasiyor, kaynak tip orada saklaniyor."""
    for o in ((durum.get("profil") or {}).get("kolon_ozet") or []):
        if isinstance(o, dict) and str(o.get("ad")) == kolon:
            return o.get("_tip_kaynak") or o.get("tip") or ""
    return ""


def _tip_ozetini_tazele(durum):
    """kolon_ozet'teki 'tip' alanini secilen donusumlere gore gunceller.

    NEDEN kolon ozetine yaziliyor: sag paneldeki feature tablosu, tip dagilimi karti
    ve sonraki fazlarin tip okumalari hep buradan besleniyor. Tek yerde
    guncellenince uc yuzey birden dogru tipi gosteriyor. Orijinal tip
    '_tip_kaynak'ta saklaniyor ki secim geri alinabilsin."""
    p = durum.get("profil") or {}
    ozet = p.get("kolon_ozet")
    if not isinstance(ozet, list):
        return
    secilen = durum.get("tip_donusum") or {}
    for o in ozet:
        if not isinstance(o, dict):
            continue
        ad = str(o.get("ad") or "")
        if "_tip_kaynak" not in o:
            o["_tip_kaynak"] = o.get("tip") or ""
        kod = secilen.get(ad)
        o["tip"] = (tip_donusum.hedef_tip(kod) if kod
                    else o["_tip_kaynak"]) or o.get("tip") or ""
    p["kolon_ozet"] = ozet
    durum["profil"] = p


def _teyit_karti(durum):
    """Degisken listesini TASIYAN teyit karti.

    Kullanici bolme oncesi son kez tanimlari gozden geciriyor; liste
    kartin icinde. Sag panele yonlendirme YOK: karar sohbette veriliyor,
    sag panel yalnizca aciklama gosteriyor."""
    # Aciklamasi olmayan kolonlar SUREC DISI isaretli acilir; kullanici
    # kutuyu kaldirip veri setinde tutabilir (bkz.
    # tanimsiz_kolonlari_isaretle). Kart kurulmadan ONCE calismali ki
    # satirlarin "disi" bayragi ile durumdaki liste ayni olsun.
    otomatik = tanimsiz_kolonlari_isaretle(durum)
    satirlar, duzenlenebilir = teyit_satirlari(durum)
    durum["_secim_alani"] = {
        "tip": "teyit",
        "baslik": ADIM_ADI["teyit"],
        "aciklama": TEYIT_ACIKLAMASI,
        "ozet": teyit_ozeti(durum),
        # Otomatik isaretleme SESSIZ YAPILMAZ: kullanici kartta neden
        # bazi kutularin isaretli geldigini gormeli, yoksa kendisinin
        # isaretledigini sanir ya da fark etmeden kolon kaybeder.
        "otomatik_not": (
            "Sözlükte açıklaması bulunmayan %s değişken süreç dışı olarak "
            "işaretlendi; bunlar analitik baz sete alınmaz. Veri setinde "
            "kalmasını istediğiniz varsa işareti kaldırın."
            % _sayi(len(otomatik))) if otomatik else "",
        # "Kaydet" (kullanici karari): dugme bir onay degil, bir YAZMA
        # islemi yapiyor - tanimlar, tip secimleri ve surec disi karari
        # kaydediliyor ve ancak kaydedildikten sonra Excel'e indirilebilir
        # hale geliyor. "Teyit Et" bu isi anlatmiyordu.
        "buton": "Kaydet ve Devam Et",
        "degiskenler": {
            "baslik": "Değişkenler ve Sözlük Tanımları",
            "not": ("İşaretlenen kolonlar süreç dışında bırakılır. "
                    "Açıklamalar sözlüğün çalışma kopyasına yazılır; "
                    "orijinal sözlük değişmez."),
            "satirlar": satirlar,
            "duzenlenebilir": duzenlenebilir,
        },
    }


def teyit_girdi(durum, mesaj, yeniden_sor=False):
    """Kart bos mesajla acilir; herhangi bir onay mesaji adimi gecirir.

    Bu adimda DOLDURULACAK alan yok — tek dugme var. Mesaj geldiyse
    kullanici o dugmeye basmistir (ya da "onayla" yazmistir); ikisi de
    ayni karardir."""
    if yeniden_sor or not (mesaj or "").strip():
        _teyit_karti(durum)
        return False, ""
    durum["_secim_alani"] = None
    return True, None


def teyit_uygula(durum):
    """Teyit ANINI kaydeder ve AMP ciktilarini YAZAR.

    Eskiden sessizdi (bos metin donuyordu) cunku ortada kaydedilen bir
    sey yoktu, yalnizca damga vuruluyordu. Artik AMP_VERISETI ve
    AMP_SOZLUK gercekten yaziliyor; nereye yazildigi kullaniciya
    soylenmeli - "kaydedildi" deyip yeri sylememek, dosyayi aramaya
    birakmak olurdu.

    durum["teyit"] denetim kaydidir: TMD'nin veri bolumu bu satiri
    "Sözlük teyidi | <zaman> · N kolon süreç dışı" olarak yazar. Kullanici
    geri donup yeniden teyit ederse damga tazelenir — gecerli olan son
    teyittir."""
    # SON KAPI: secimler tek tek secildiklerinde tam veriyle dogrulandi,
    # ama arada veri seti degismis olabilir (Mod C'de birlestirme yeniden
    # calistirilabiliyor). Adimi gecmeden once hepsi bir kez daha
    # denetleniyor; takilan varsa adim GECMEZ - bolme sirasinda sessizce
    # atlanan bir donusum, kullanicinin gordugu tiple modelin gordugu
    # tipin ayrismasi demekti.
    _tip_secimlerini_dogrula(durum)

    degisken, haric, tanimli = _teyit_sayilari(durum)
    durum["teyit"] = {
        "zaman": datetime.datetime.now().isoformat(timespec="seconds"),
        "degisken": degisken, "haric": haric, "tanimli": tanimli,
        "tip_degisen": len(durum.get("tip_donusum") or {}),
    }

    # KAYDET: adin adi "Kaydet ve Devam Et" - gercekten bir sey
    # kaydediliyor. AMP_VERISETI ve AMP_SOZLUK bu noktada yaziliyor;
    # kullanici sonradan bu adlarla cekebilsin diye.
    cikti = amp_ciktilarini_yaz(durum)
    return ("Değişken listesi kaydedildi.\n"
            "  Modelleme tablosu : %s\n"
            "  Değişken sözlüğü  : %s"
            % (amp_nerede(cikti.get("veri")),
               amp_nerede(cikti.get("sozluk"))))


def _tip_secimlerini_dogrula(durum):
    """Secilen tum donusumleri tam veriyle dogrular; takilan varsa
    AdimHatasi atar. Secim yoksa veri seti OKUNMAZ."""
    secilen = durum.get("tip_donusum") or {}
    if not secilen:
        return
    try:
        df = _df_oku(durum["veri_seti"])
    except Exception as e:
        raise AdimHatasi(
            "Tip değişiklikleri doğrulanamadı: veri seti okunamadı (%s)."
            % str(e)[:100])
    _, _uygulanan, atlanan = tip_donusum.uygula(df, secilen)
    if atlanan:
        raise AdimHatasi(
            "Seçtiğiniz tip değişikliklerinden bazıları artık "
            "uygulanamıyor; düzeltmeden devam edemem:\n"
            + "\n".join("  • %s - %s" % (k, s)
                        for k, s in sorted(atlanan.items())))


# ===========================================================================
# BOLME STRATEJISI
# ===========================================================================
# EKRAN SIRASI (kullanici karari): once SEC, sonra ozeti gor, istersen
# detayi ac. Eskiden once uc paragraf metin, sonra secim geliyordu.
# TEK PARAGRAF, KART ICINDE DUZ METIN. Balon ya da ikinci bir kutu
# YOK (kullanici karari: "şu blok saçmalığını ... bloksuz yazı yazar
# hale getir"); iki cumle arasindaki bos satir da kalkti.
# BASLIK ALTINDA TEK CUMLE (kullanici karari: "uzun yönlendirmelerin
# hiçbirine gerek yok"). Ekranin geri kalani secimin kendisi.
BOLME_ACIKLAMA = (
    "Veri üç sete ayrılır: modelin öğrendiği Train (MS), model ayarlarının "
    "seçildiği Validasyon (OOS) ve nihai ölçümün yapıldığı Test (OOT). "
    "Aşağıdaki ayarlar veri yapınıza göre önerilen değerlerle dolu; "
    "değiştirmek için satırdaki seçeneğe tıklayın, açıklama için «i» "
    "simgesine gelin.")

# SUTUN BASLIKLARI. Mod SECIMI DEGIL: iki sutun ayni anda ekranda
# duruyor (kullanici karari: "yanyana durmaları, birine basınca
# değişmesi değil; kullanıcı önerilen ne, ben ne yapabilirim görmeli").
# IKI ALTERNATIF: birbirinin gercek alternatifi iki panel. "Sizin
# seçiminiz" ve "Tavsiye edilir" rozeti KALKTI - adi zaten "Önerilen
# Ayarlar", ikinci kez soylemek gereksizdi (kullanici karari).
BOLME_PANELLERI = (
    {"anahtar": "oneri", "etiket": "Önerilen Ayarlar",
     "aciklama": "Veri yapısına göre hazırlandı."},
    {"anahtar": "ozel", "etiket": "Özel Ayarlar",
     "aciklama": "Ayarları kendiniz belirleyin."},
)

BOLME_BUTON = "Bu Ayarları Seç"
BOLME_GEREKCE_ETIKET = "Öneri gerekçesi"
BOLME_SOZLUK_ETIKET = "Detaylar ve Terimler"


def _oneri_ayarlari(durum, ek):
    """Onerinin HAM degerleri, on yuzun gonderdigi bicimle ayni."""
    a = dict(bolme_ayarlari(durum))
    if isinstance(ek, dict):
        a.update(ek)
    return {
        "test_tanim": a.get("test_tanim"),
        "oot_adet": test_donem_anahtari(a),
        "test_oran": round(float(a.get("test_oran") or 0.20), 4),
        "gap": int(a.get("gap") or 0),
        "train_kullanimi": a.get("train_kullanimi"),
        "birim": a.get("birim"),
        "val_var": "kullan" if a.get("val_var") else "kullanma",
        "val_oran": round(float(a.get("val_oran") or 0.20), 4),
        "cv": a.get("cv"),
        "kat": int(a.get("kat") or 5),
        "seedler": ", ".join(str(x) for x in (a.get("seedler") or [])),
        "katmanla": "koru" if a.get("katmanla") else "koruma",
        "seed_tur": a.get("seed_tur") or "sabit",
        "tekrar": int(a.get("tekrar") or 1),
        "seed": int(a.get("seed") or 42),
    }


def bolme_karti(durum, mod=None):
    """Bolme Stratejisi karti.

    EKRAN DUZENI: IKI ESIT SECILEBILIR PANEL

        baslik + tek cumle
        ┌ ● ÖNERİLEN AYARLAR ┐  ┌ ○ ÖZEL AYARLAR ┐
        │  ayni gruplar,     │  │  ayni gruplar,  │
        │  salt okunur cip   │  │  secilebilir cip│
        │  ▸ Öneri gerekçesi │  │                 │
        │  ▸ Detaylar...     │  │  ▸ Detaylar...  │
        │  [Bu Ayarları Seç] │  │ [Bu Ayarları Seç]│
        └────────────────────┘  └─────────────────┘

    SECIM EKRANI, FORM DEGIL (kullanici karari). Iki panel surekli yan
    yana ve karsilastirilabilir duruyor; secili olan tam opaklikta ve
    kirmizi cerceveli, digeri soluk ve kontrolleri pasif. Panele
    herhangi bir yerden basmak onu secer. Panel kaybolmuyor, icerik
    degismiyor, accordion'a donusmuyor.

    Acilir listeler mumkun oldugunca CIP'lere cevrildi; acilir liste
    yalnizca secenek sayisi gercekten fazla oldugunda (kolon secimi).

    "Bu plan neden önerildi" ust taraftan kalkti: ekranin dortte birini
    metin yiyordu. Simdi sol panelin altinda, kapali bir acilir alanda.

    Oneri durum["bolme"]'ye BAKMAZ (bkz. akis_durum.bolme_onerisi)."""
    oneri = bolme_onerisi(durum)
    secili = mod if mod in ("oneri", "ozel") else (
        durum.get("_bolme_mod") or "oneri")
    durum["_bolme_mod"] = secili

    from fe_agent import akis_panel
    form = akis_panel.bolme_formu(durum)
    satirlar = akis_panel.bolme_satirlari(durum, oneri["ayarlar"])

    durum["_secim_alani"] = {
        "tip": "bolme",
        "baslik": ADIM_ADI["bolme"],
        "aciklama": BOLME_ACIKLAMA,
        "mod": secili,
        "paneller": [dict(x) for x in BOLME_PANELLERI],
        "bolumler": [dict(b) for b in BOLME_BOLUMLERI],
        "satirlar": satirlar,
        "oneri": {
            "etiket": BOLME_GEREKCE_ETIKET,
            "ozet": oneri["ozet"],
            "gerekce": oneri["detaylar"],
            "ayarlar": _oneri_ayarlari(durum, oneri["ayarlar"]),
        },
        "form": form,
        "sozluk": {"etiket": BOLME_SOZLUK_ETIKET,
                   "sorular": akis_panel.bolme_sozlugu()},
        "kisitlar": oneri["kisitlar"],
        "uyarilar": form.get("uyarilar") or [],
        "buton": BOLME_BUTON,
    }
    return durum["_secim_alani"]


def bolme_kartini_tazele(durum):
    """Acik bolme kartini YERINDE gunceller.

    /bolme_kaydet bir ayari degistirdiginde kartin ozeti, uyarilari ve
    kisitlari da degisir. Kart tazelenmezse kullanici kaydettigi ayari
    ekranda goremiyor ve ikinci kez kaydetmeye calisiyordu."""
    alan = durum.get("_secim_alani")
    if not isinstance(alan, dict) or alan.get("tip") != "bolme":
        return None
    return bolme_karti(durum, alan.get("mod"))


def bolme_oneriyi_uygula(durum):
    """Onerilen ayarlari durum["bolme"]'ye YAZAR. Doner: bolme_kaydet sonucu.

    Oneri bir metin degil, uygulanabilir bir ayar kumesi: "Önerilen
    Ayarları Uygula" dugmesi bu ayarlari gercekten kaydediyor. Eskiden
    oneri yalnizca bir cumleydi ve kullanici onayladiginda arka planda
    baska varsayilanlar uygulanabiliyordu."""
    sonuc = bolme_kaydet(durum, dict(bolme_onerisi(durum)["ayarlar"]))
    if sonuc.get("tamam"):
        durum["_bolme_mod"] = "oneri"
        bolme_kartini_tazele(durum)
    return sonuc


def bolme_girdi(durum, mesaj, yeniden_sor=False):
    """Kart bos mesajla acilir; onay mesaji adimi gecirir.

    Adimda DOLDURULACAK zorunlu alan yok: oneri zaten gecerli bir bolme
    tarif ediyor ve kullanici hic dokunmadan devam edebilir. Kartin
    dugmesine basmak da "onayla" yazmak da ayni karardir."""
    if yeniden_sor or not (mesaj or "").strip():
        bolme_karti(durum)
        return False, ""
    durum["_secim_alani"] = None
    return True, None


def bolme_uygula(durum):
    # TAM tablo okunuyor: eskiden limit=100000 ile okunup satir sayilari bu
    # KESILMIS tablodan hesaplaniyordu; diger adimlar tam tabloyu okudugu
    # icin kullaniciya yanlis satir sayisi gosteriliyordu.
    veri_seti = durum["veri_seti"]
    df = modelleme_df(durum)

    # TIP DONUSUMLERI ZATEN UYGULANMIS GELIYOR: modelleme_df, sozluk
    # teyidinde secilen donusumleri OKUMADA uyguluyor (bkz.
    # akis_durum.modelleme_df). Burada yalnizca kullaniciya kac kolonun
    # farkli tiple devam ettigi soyleniyor - bolmeden sonraki butun
    # fazlar ayni okuma yolundan gectigi icin tip her yerde ayni.
    secilen_tipler = durum.get("tip_donusum") or {}
    tip_notu = ("%s kolon sözlük teyidindeki seçiminize göre dönüştürülmüş "
                "tiple işleniyor." % _sayi(len(secilen_tipler))
                if secilen_tipler else "")

    def _split_yaz(kopya):
        yazildi, _ = _yaz(veri_seti, kopya, "/bolme_split.csv")
        return yazildi

    # Bolme BIR KEZ hesaplanip kalici hale getiriliyor; maskeler() bundan
    # sonra hep ayni satirlari ayni sete koyuyor.
    tr, te, notlar = bolme_hazirla(durum, df, yazici=_split_yaz)
    onbellek_temizle(veri_seti)

    # Set sayimlarini bolme_hazirla yaziyor (dort yolun da ayni sayimi
    # uretmesi icin); burada yalnizca toplam ekleniyor.
    b = durum["bolme"]
    b["toplam_satir"] = int(len(df))
    durum["bolme"] = b

    hedef = (durum.get("meta") or {}).get("target")
    oran_not = ""
    if hedef and hedef in df.columns:
        try:
            y = pd.to_numeric(df[hedef], errors="coerce")
            if int(y.nunique(dropna=True)) <= 2:
                oran_not = ("\nHedef oranı: geliştirme %%%s, test %%%s."
                            % (_ond(100.0 * float((y[tr] > 0).mean()), 2),
                               _ond(100.0 * float((y[te] > 0).mean()), 2)))
        except Exception:
            oran_not = ""

    # Val ya da OOT acikken iki sayi tabloyu artik anlatmiyor; dort setin
    # tamami tek satirda gosteriliyor.
    dort = b.get("satir") or {}
    if dort.get("val") or dort.get("oot"):
        notlar = list(notlar) + ["Setler: %s." % bolme_ozeti(durum)]

    ek = ("\n" + "\n".join(notlar)) if notlar else ""
    if tip_notu:
        ek += "\n" + tip_notu
    return ("Bölme tanımlandı: %s satırın %s satırı geliştirme, %s satırı "
            "test.%s%s"
            % (_sayi(b["toplam_satir"]), _sayi(b["train_satir"]),
               _sayi(b["test_satir"]), oran_not, ek))
