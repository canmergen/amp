# -*- coding: utf-8 -*-
"""fe_agent/akis_durum.py - Oturum durumu, veri okuma/yazma ve bicimleme yardimcilari.

akis.py bolundu; bu dosya o bolumun aynisidir.
"""

import datetime
import io
import json
import math
import re
import time
import dataiku
import numpy as np
import pandas as pd

from fe_agent.akis_metin import ADIM_ADI, MOD_SECENEKLERI, SECIM_KALIP


HAFIZA_FOLDER = "PROJE_HAFIZASI"

OKUMA_LIMITI = None          # None = tam tablo

# Mod A ve B'de uretilen sabit adli ciktilar
BAZ_ADI = "MODELLEME_BAZ"

SOZLUK_ADI = "MODELLEME_SOZLUK"

# ---------------------------------------------------------------------------
# AMP CIKTILARI  -  platformun sozluk teyidinde KAYDETTIGI iki tablo
# ---------------------------------------------------------------------------
# Bir sure sag panelde "Modelleme Tablosu" / "Modelleme Sözlüğü" yaziyordu
# ama bunlar YALNIZCA EKRAN ETIKETIYDI: ortada o adla kaydedilmis hicbir
# sey yoktu, kullanici "bunu bu adla cekebilir miyim" diye sorunca cevap
# hayirdi. Artik gercek ad ve gercek kayit var.
#
#   AMP_VERISETI : modelleme tablosu, TIP DONUSUMLERI UYGULANMIS haliyle.
#                  Kolon DUSURULMEZ - dusurme Hazirlik adiminin isi ve
#                  orada ayrica raporlaniyor; burasi "teyit anindaki tam
#                  tablo" olmali ki sag paneldeki kolon sayisiyla ayni
#                  seyi anlatsin.
#   AMP_SOZLUK   : degisken listesinin teyit anindaki hali - tip, sozluk
#                  tanimi, null orani, tip degisikligi ve SUREC DISI
#                  karari. Excel ciktisinin birebir ayni govdesi.
#
# YAZMA YOLU: once ayni adli DATASET denenir (akista tanimliysa asil
# istenen bu - kullanici Dataiku'da dogrudan kullanabilir); tanimli
# degilse PROJE_HAFIZASI icindeki AMP klasorune CSV olarak yazilir ve
# kullaniciya NEREYE yazildigi soylenir.
AMP_VERI_ADI = "AMP_VERISETI"
AMP_SOZLUK_ADI = "AMP_SOZLUK"

# Yalnizca ESKI kayitlar icin: bu surumden once AMP ciktilari
# "AMP/<tarih>_<oturum>/" altina yaziliyordu. Yeni calismalar
# ciktilarini kendi klasorune yaziyor (bkz. akis_faz01.amp_klasor_adi).
AMP_KLASOR = "AMP"

# ORTAK VERI SETLERININ SAHIBI. AMP_VERISETI ve birlestirme sonucu
# (MODELLEME_BAZ ya da kullanicinin verdigi ad) akista TEK veri setidir;
# butun calismalar ayni veri setine yazar. Hangi veri setine EN SON hangi
# calismanin yazdigi burada tutulur: {veri_seti: calisma}. Bu kayit
# olmadan Calisma 01'e geri donen kullanici Calisma 03'un tablosunu
# okurdu. Sahibi baskasiysa calisma KENDI KLASORUNDEKI kopyayi okur.
SAHIP_DOSYA = "/VERI_SETI_SAHIPLERI.json"

# AMP_SOZLUK tablosunun kolon adlari. Sabit olarak duruyor cunku iki
# yerden kullaniliyor (tabloyu yazan taraf ve gizlilik denetimi yapan
# test) ve ikisinin ayrismamasi gerekiyor. Bunlar PLATFORMUN KENDI
# kolon adlari; baska bir kurumun veri setinden gelmiyorlar.
AMP_SOZLUK_KOLONLARI = ("DEGISKEN", "TIP", "TIP_DEGISIKLIGI", "ACIKLAMA",
                        "NULL_ORANI", "SUREC_DISI")

LINEAGE_ADI = "MODELLEME_LINEAGE"

# Kimlik kolonu yoksa bolme veri setine BU kolonla kalici yazilir.
SPLIT_KOLON = "_SPLIT"

# Kimlik listesi durum JSON'una yaziliyor ve oturum dosyasi her turda
# yeniden yaziliyor; liste cok buyurse dosya sisiyor. Bu esigin ustunde
# kalici _SPLIT kolonuna geciliyor (yaklasik 250 bin satirlik tabloya
# kadar kimlik listesi kullanilir).
TEST_KIMLIK_LIMITI = 50000

# Bolmenin dort seti. Sira ONEMLI degil ama ad birebir sozlesmedeki ad.
SET_ADLARI = ("egitim", "val", "test", "oot")

# KULLANICIYA GORUNEN UC SET. Sektorde kullanilan adlar aynen
# kullaniliyor (kullanici karari): uydurma Turkce karsilik ("sınav",
# "deneme") banka icinde kimsenin konusmadigi bir dil uretiyordu.
#
# "oot" ic anahtari duruyor (hep bos bir maske; bkz. bolme_ayarlari'nda
# oot_var=False) ama AYRI BIR SET DEGIL: zamansal bolmede test setinin
# kendisi zaten zaman disidir. Bu yuzden TEK AD kullaniliyor -
# "OOT / Test" - ve ekranda hicbir yerde ayri bir OOT seti gecmiyor.
SET_BASLIK = {"egitim": "Eğitim", "val": "Doğrulama",
              "test": "OOT / Test", "oot": "OOT / Test"}

# SPLIT kolonuna yazilan etiketler. "train" ETIKETI KORUNUYOR: daha once
# yazilmis veri setlerinde bu deger duruyor ve okunamazsa o oturumun
# bolmesi kaybolur.
SPLIT_ETIKET = {"egitim": "train", "val": "val", "test": "test", "oot": "oot"}

# Bir setin altinda anlamli olcum yapilamayan satir sayisi.
MIN_SET_SATIR = 50

# val da CV de yoksa hiperparametre sececek temiz bir yer kalmaz: egitim
# setinde secim yapmak secilen hiperparametreyi egitim gurultusune uydurur,
# test setinde secim yapmak test setini yakar.
GECERSIZ_BIRLESIM = (
    "Doğrulama seti yok ve çapraz doğrulama kapalı: model ayarlarını "
    "deneyecek temiz bir yer kalmıyor. Algoritma seçimi SABİT ayarlarla "
    "yapılacak (arama yapılmayacak) ve bu durum rapora yazılacak. Arama "
    "istiyorsanız doğrulama setini açın ya da çapraz doğrulamayı "
    "parçalı/zaman sıralı yapın.")


class AdimHatasi(Exception):
    """Adim tamamlanamadi. Akis ILERLEMEMELI; mesaj kullaniciya gosterilir."""


class DurumOkunamadi(Exception):
    """Oturum dosyasi var ama okunamadi (bozuk / yarim yazilmis JSON).

    'Dosya yok' durumundan ayridir: dosya yoksa durum_yukle() yeni durum
    doner, bozuksa BU istisna atilir - bozuk oturum sessizce
    'hic baslamamis oturum' gibi gorunmemeli."""


# ===========================================================================
# DURUM
# ===========================================================================
def _folder():
    return dataiku.Folder(HAFIZA_FOLDER)

def _yol(oturum_id):
    return "/oturum_%s.json" % re.sub(r"[^A-Za-z0-9_-]", "", str(oturum_id))

def yeni_durum():
    return {
        "i": 0, "bekleyen": "girdi",
        "mod": None,                 # "A" | "B" | "C" | "D"
        # Mod harflerinin hangi duzene gore yazildigi (bkz. MOD_GOCU).
        "_mod_surumu": MOD_SURUMU,
        "ham_tablolar": [],          # Mod B ve D
        "baz_adi": None,             # Mod B ve D: birlestirme sonucunun adi
        "kaynak_sozlukler": {},      # Mod B: {kaynak tablo: sozluk}
        "birlestirme": {},           # plan + ozet
        "sozluk_uretim": {},         # ozet
        "veri_seti": None, "sozluk": None,
        "sozluk_yedek": None,        # dataset yazilamazsa CSV yedeginin yolu
        # Train'den ogrenilen donusum parametreleri (winsor sinirlari,
        # rank izgarasi). Uretim koduna gomulur; tekrarlanabilirlik icin.
        "ogrenilen_donusum": {},
        "meta": {}, "bolme": {},
        # HAZIRLIK sekmesinin veri sozlesmesi. Donusumun kendisi henuz
        # yok; liste bos baslar ve panel "henuz donusum tanimlanmadi"
        # der. Sekme bos bir kutu olarak degil, dolmayi bekleyen bir
        # kart olarak gorunsun diye anahtar bastan duruyor.
        "hazirlik": {"adimlar": []},
        "haric_kolonlar": [],
        "profil": {}, "sfa": {}, "stabilite": {},
        "baz": {},
        "plan": [], "hipotez": [],
        "uretilen": [], "kod_bloklari": [],
        "kalite": {}, "secim": {}, "secim_tablo": [],
        "model": {}, "katalog": {},
        "_secenekler": [],
        "_secim_alani": None,
        # --- webapp backend'inin kullandigi alanlar -----------------------
        "_oturum_id": None,
        "_tur_no": 0,
        "_son_cevap": None,
        "_gecmis": [],
    }

def _json_uygun(deger, yol="durum"):
    """Durumu JSON'a yazmadan ONCE tip normalizasyonu.

    numpy sayilari Python sayisina, NaN/NaT None'a, Timestamp ISO metne
    cevrilir. Bilinmeyen tipte SESSIZCE str()'e dusulmez - acik hata verilir;
    aksi halde kayit->yukleme turundan sonra sayisal alanlar metin olarak
    geri geliyor ve siralama bozuluyordu."""
    if deger is None:
        return None
    if isinstance(deger, (bool, np.bool_)):
        return bool(deger)
    if isinstance(deger, str):
        return deger
    if isinstance(deger, (int, np.integer)):
        return int(deger)
    if isinstance(deger, (float, np.floating)):
        d = float(deger)
        return None if (math.isnan(d) or math.isinf(d)) else d
    if isinstance(deger, (datetime.datetime, datetime.date, datetime.time)):
        return deger.isoformat()
    if isinstance(deger, pd.Timestamp):
        return None if pd.isna(deger) else deger.isoformat()
    if isinstance(deger, datetime.timedelta):
        return deger.total_seconds()
    if deger is pd.NaT:
        return None
    if isinstance(deger, np.ndarray):
        return [_json_uygun(x, "%s[]" % yol) for x in deger.tolist()]
    if isinstance(deger, pd.Series):
        return [_json_uygun(x, "%s[]" % yol) for x in deger.tolist()]
    if isinstance(deger, dict):
        return {str(k): _json_uygun(v, "%s.%s" % (yol, k))
                for k, v in deger.items()}
    if isinstance(deger, (list, tuple, set, frozenset)):
        dizi = sorted(deger, key=str) if isinstance(deger, (set, frozenset)) \
            else list(deger)
        return [_json_uygun(x, "%s[%d]" % (yol, i)) for i, x in enumerate(dizi)]
    raise TypeError("Durum JSON'a cevrilemedi: %s -> %s tipi desteklenmiyor "
                    "(deger: %.80r)" % (yol, type(deger).__name__, deger))

# ---------------------------------------------------------------------------
# MOD GOCU
# ---------------------------------------------------------------------------
# Surum 2'de "Veri Seti Hazır Değil, Sözlük Hazır" B olarak araya girdi;
# eski B (veri hazir, sozluk yok) C, eski C (ikisi de yok) D oldu. Harf
# ekranda gorundugu ve kodda moda gore adim listesi sectigi icin, eski bir
# kaydin "B"si okunurken "C"ye cevrilmezse calisma baska bir adim
# listesine dusup bozulurdu. Kayitta "_mod_surumu" yoksa eski duzendir.
MOD_SURUMU = 2
MOD_GOCU = {"B": "C", "C": "D"}


def _mod_goc(durum):
    if durum.get("_mod_surumu", 1) >= MOD_SURUMU:
        return durum
    for alan in ("mod", "_onceki_mod", "_mod_onay"):
        if durum.get(alan) in MOD_GOCU:
            durum[alan] = MOD_GOCU[durum[alan]]
    # Baslangic seciminde bekleyen eski uc kart: yenileri gosterilsin.
    if _eski_mod_kartlari(durum.get("_secenekler")):
        durum["_secenekler"] = [dict(x) for x in MOD_SECENEKLERI]
    # Sohbet gecmisinde cizilen eski kartlar ve isaretli secim: eski
    # calisma acilinca "B" isaretli gorunup yeni B'yi anlatmasin.
    for kayit in durum.get("_gecmis") or []:
        ekran = kayit.get("ekran") if isinstance(kayit, dict) else None
        if not isinstance(ekran, dict) or \
                not _eski_mod_kartlari(ekran.get("secenekler")):
            continue
        ekran["secenekler"] = [dict(x) for x in MOD_SECENEKLERI]
        if ekran.get("secili") in MOD_GOCU:
            ekran["secili"] = MOD_GOCU[ekran["secili"]]
    durum["_mod_surumu"] = MOD_SURUMU
    return durum


def _eski_mod_kartlari(secenekler):
    return (isinstance(secenekler, list) and len(secenekler) == 3 and all(
        isinstance(x, dict) and x.get("deger") in ("A", "B", "C")
        for x in secenekler))


def durum_kaydet(oturum_id, durum):
    temiz = _json_uygun(durum)
    veri = json.dumps(temiz, ensure_ascii=False, indent=2,
                      allow_nan=False).encode("utf-8")
    _folder().upload_stream(_yol(oturum_id), veri)

def durum_var_mi(oturum_id):
    """Bu oturum icin kayitli bir dosya var mi? (webapp backend'i icin)"""
    yol = _yol(oturum_id)
    try:
        return yol in set(_folder().list_paths_in_partition())
    except Exception:
        pass
    try:
        with _folder().get_download_stream(yol):
            return True
    except Exception:
        return False

def durum_yukle(oturum_id):
    """Oturumu yukler.

    Dosya YOKSA yeni_durum() doner. Dosya var ama okunamiyorsa
    DurumOkunamadi atar - bozuk kayit sessizce yutulmaz. Cagiran tarafin
    istisna yakalamak istemedigi yerlerde durum_yukle_guvenli() var.
    """
    yol = _yol(oturum_id)
    try:
        akis = _folder().get_download_stream(yol)
    except Exception:
        # Dosya yok (ya da klasore hic yazilmamis): temiz baslangic.
        durum = yeni_durum()
        durum["_oturum_id"] = oturum_id
        return durum

    try:
        with akis as s:
            ham = s.read()
        durum = json.loads(ham.decode("utf-8"))
    except Exception as e:
        raise DurumOkunamadi(
            "Oturum kaydı okunamadı (%s): %s. Dosya bozuk ya da yarım "
            "yazılmış olabilir." % (yol, str(e)[:160]))

    if not isinstance(durum, dict):
        raise DurumOkunamadi("Oturum kaydı beklenen biçimde değil (%s)." % yol)

    durum["_oturum_id"] = oturum_id
    return _mod_goc(durum)

def durum_yukle_guvenli(oturum_id):
    """(durum, hata) doner. Bozuk kayitta hata metni dolu gelir ve durum
    yeni_durum()'dur; cagiran kullaniciyi uyarabilir."""
    try:
        return durum_yukle(oturum_id), None
    except DurumOkunamadi as e:
        durum = yeni_durum()
        durum["_oturum_id"] = oturum_id
        return durum, str(e)

# ===========================================================================
# YARDIMCILAR
# ===========================================================================
# Ayni istek icinde ayni tablonun iki kez okunmasini engelleyen kucuk
# onbellek. OKUMA_LIMITI None oldugu icin her plan fonksiyonu tam tabloyu
# okuyor; onbelleksiz her "Geri Dön" tiklamasi Flask'i dakikalarca
# bloklar. Anahtar = (dataset adi, limit). Icerik degisebilecegi icin
# kisa omurludur ve yazma adimlarindan sonra onbellek_temizle() ile
# acikca bosaltilir.
#
# DIKKAT: _yaz() kendi dataset'ini otomatik gecersiz kilar. Bir modul
# dataiku.Dataset(...).write_with_schema() ile DOGRUDAN yaziyorsa
# onbellek_temizle(ad) cagirmali; aksi halde omur suresi dolana kadar
# eski icerik okunabilir.
_DF_ONBELLEK = {}
# OMUR INSAN HIZINA GORE. 30 saniyeydi ve asil yavaslik sebebi oydu:
# kullanici formu doldururken, acilir listeden kolon secerken, karti
# okurken 30 saniye rahatlikla geciyor - her adim tabloyu BASTAN
# okuyordu. 10.000 x 1.042'lik gercek bir tabloda tek okuma onlarca
# saniye surdugu icin "Veri Seti ve Sözlük" adimi dakikalarca calisir
# gorunuyordu (kullanici bildirimi: "1.30 dk'dan fazladır çalışmadı").
#
# Kaynak tablo oturum boyunca DEGISMIYOR; platformun kendi yazmalari
# zaten onbellek_temizle(ad) ile kaydi dusuruyor. Disaridan degisirse
# en fazla bu sure kadar eski icerik okunur - "Yeni Çalışma" ya da
# sayfa yenileme yeni bir sureci baslatiyor.
ONBELLEK_OMRU_SN = 900.0
# KAPASITE: omur uzayinca kayitlar daha uzun yasiyor ve 1.042 kolonluk
# bir tablo onlarca MB tutuyor. Alti kayit bu akisi rahat karsiliyor
# (veri seti, sozluk, AMP ciktisi ve birkac sema okumasi) ve dolunca
# artik EN ESKI kayit dusuyor - hepsi birden degil.
ONBELLEK_KAPASITE = 6

def onbellek_temizle(ad=None):
    """Onbellegi bosaltir. ad verilirse yalnizca o dataset'in kayitlari
    silinir. 'uygula' adimlarindan sonra cagrilmali."""
    if ad is None:
        _DF_ONBELLEK.clear()
        return
    for anahtar in [k for k in _DF_ONBELLEK if k[0] == str(ad)]:
        _DF_ONBELLEK.pop(anahtar, None)

def _df_oku(ad, limit=-1, onbellek=True):
    if limit == -1:
        limit = OKUMA_LIMITI
    anahtar = (str(ad), limit)

    if onbellek:
        kayit = _DF_ONBELLEK.get(anahtar)
        if kayit is not None:
            zaman, df = kayit
            if (time.time() - zaman) <= ONBELLEK_OMRU_SN:
                return df.copy()
            _DF_ONBELLEK.pop(anahtar, None)

    ds = dataiku.Dataset(ad)
    df = ds.get_dataframe() if limit is None else ds.get_dataframe(limit=limit)

    if onbellek:
        # EN ESKIYI DUSUR, hepsini degil. Eskiden kapasite dolunca
        # onbellek KOMPLE bosaltiliyordu; kucuk sema okumalari
        # (limit=200, limit=5) birkac kayit acinca pahali TAM tablo da
        # atiliyor ve bir sonraki adim onu bastan okuyordu. Gercek bir
        # Dataiku tablosunda bu, adim basina onlarca saniye demekti.
        while len(_DF_ONBELLEK) >= ONBELLEK_KAPASITE:
            en_eski = min(_DF_ONBELLEK, key=lambda k: _DF_ONBELLEK[k][0])
            _DF_ONBELLEK.pop(en_eski, None)
        _DF_ONBELLEK[anahtar] = (time.time(), df)
        return df.copy()
    return df

def modelleme_kaynagi(durum):
    """Modelleme tablosunun O ANKI kaynagi: (dataset_adi, amp_mi).

    Sozluk teyidi KAYDEDILDIKTEN sonra kaynak AMP_VERISETI'dir; oncesinde
    kullanicinin sectigi tablodur.

    NEDEN AMP'YE GECIYOR (kullanici karari)
      "işlemler de bu veri setleri üzerinden yapılıyor değil mi" -
      evet, olmali. Teyitten sonra ortada kaydedilmis, adi olan, kullanici
      tarafindan da cekilebilen bir tablo var; sonraki fazlarin bundan
      baska bir seyi okumasi "ekranda gordugum tablo ile modelin okudugu
      tablo ayni mi" sorusunu acik birakirdi.

      Ek faydasi: AMP_VERISETI tip donusumleri ISLENMIS halde duruyor,
      yani sonraki her okumada donusumu yeniden uygulamak gerekmiyor.

    AMP yalnizca DATASET olarak yazildiysa kaynak olur. Yazma klasordeki
    CSV yedegine dustuyse orijinale geri donulur: yedek dosya bir
    kurtarma kopyasidir, her fazin okuyacagi yer degil."""
    durum = durum or {}
    kayit = (durum.get("amp_cikti") or {}).get("veri") or {}
    amp = kayit.get("dataset")
    # SAHIPLIK: veri seti baska bir calismanin kaydiyla ezilmisse
    # kullanicinin kendi tablosu okunur; tip donusumleri modelleme_df'de
    # yeniden uygulandigi icin sonuc ayni tablodur.
    if amp and sahibi_mi(amp, durum):
        return str(amp), True
    return durum.get("veri_seti"), False


def _calisma_kimligi(durum):
    return re.sub(r"[^A-Za-z0-9_-]", "", str((durum or {}).get("_oturum_id") or ""))


# Kayit ayni istek icinde defalarca okunuyor (her modelleme_df cagrisi);
# kisa omurlu onbellek. Yazan taraf onbellegi kendisi gunceller.
_SAHIP_ONBELLEK = {"zaman": 0.0, "deger": {}}
SAHIP_OMUR_SN = 10


def _sahipler_oku(taze=False):
    if not taze and time.time() - _SAHIP_ONBELLEK["zaman"] < SAHIP_OMUR_SN:
        return _SAHIP_ONBELLEK["deger"]
    try:
        with _folder().get_download_stream(SAHIP_DOSYA) as s:
            deger = json.loads(s.read().decode("utf-8"))
        if not isinstance(deger, dict):
            deger = {}
    except Exception:
        deger = {}
    _SAHIP_ONBELLEK.update(zaman=time.time(), deger=deger)
    return deger


def sahip_yaz(ad, durum):
    """ad veri setine SON yazan calisma bu. Doner: yazilabildi mi.

    Yazilamazsa zarar yok: sahibi_mi False doner ve calisma kendi
    klasorundeki kopyayi okur."""
    kayit = dict(_sahipler_oku(taze=True))
    kayit[str(ad)] = _calisma_kimligi(durum)
    tamam = metin_yaz(SAHIP_DOSYA, json.dumps(kayit, ensure_ascii=False))
    _SAHIP_ONBELLEK.update(zaman=time.time(), deger=kayit if tamam else {})
    return tamam


def sahibi_mi(ad, durum):
    """ad veri seti su an BU calismanin kaydini mi tasiyor?

    Kayit okunamazsa HAYIR: yanlis calismanin tablosunu okumaktansa
    calismanin kendi kopyasina donmek her zaman dogru sonucu verir."""
    kimlik = _calisma_kimligi(durum)
    return bool(kimlik) and _sahipler_oku().get(str(ad)) == kimlik


def amp_sahibi_yaz(durum):
    """AMP_VERISETI'ni bu calismanin yazdigini kaydeder."""
    return sahip_yaz(AMP_VERI_ADI, durum)


def dataset_yaz(ad, tablo):
    """Yalniz dataset'e yazar (yedege DUSMEZ). Doner: yazildi mi."""
    try:
        dataiku.Dataset(ad).write_with_schema(tablo)
        onbellek_temizle(ad)
        return True
    except Exception:
        return False


def dosya_yaz(yol, tablo):
    """PROJE_HAFIZASI icine CSV. Doner: yazildi mi."""
    try:
        _folder().upload_stream(yol, tablo.to_csv(index=False).encode("utf-8"))
        _DF_ONBELLEK.pop((str(yol), None), None)
        return True
    except Exception:
        return False


def _dosya_oku(yol, limit=None):
    """PROJE_HAFIZASI'ndaki CSV'yi okur; _df_oku ile ayni onbellek."""
    anahtar = (str(yol), limit)
    kayit = _DF_ONBELLEK.get(anahtar)
    if kayit is not None and time.time() - kayit[0] <= ONBELLEK_OMRU_SN:
        return kayit[1].copy()
    with _folder().get_download_stream(yol) as s:
        df = pd.read_csv(io.BytesIO(s.read()), nrows=limit)
    _DF_ONBELLEK[anahtar] = (time.time(), df)
    return df.copy()


def _calisma_kopyasi(durum, ad):
    """Birlestirme sonucu baska bir calismanin kaydiyla EZILDIYSE, bu
    calismanin klasorundeki kopyanin yolu; aksi halde None."""
    b = (durum or {}).get("birlestirme") or {}
    if not b.get("dosya") or ad != b.get("dataset"):
        return None
    return None if sahibi_mi(ad, durum) else b["dosya"]


def modelleme_df(durum, limit=-1, kaynak=False):
    """Modelleme tablosunu, SOZLUK TEYIDINDE SECILEN TIP DONUSUMLERI
    uygulanmis halde okur.

    kaynak=True: AMP_VERISETI yazilmis olsa bile KULLANICININ TABLOSUNU
    okur. AMP ciktisini URETEN kodun kullandigi yol budur - aksi halde
    kendi ciktisini kaynak alirdi.

    NEDEN OKUMADA, YAZMADA DEGIL
      Donusumu tabloya YAZMAK iki sebeple yanlisti. Birincisi: Mod A ve
      B'de `durum["veri_seti"]` kullanicinin KENDI tablosu ve platformun
      degismez kurali onu yazmamak. Ikincisi: yazmanin dogal yeri bolme
      adimi gibi duruyordu ama bolme yalnizca kimlik/donem kolonu YOKSA
      tabloya dokunuyor - zamansal bolmede hicbir sey yazilmiyor, yani
      donusum sessizce kaybolurdu. Okuma tarafinda uygulanınca uc mod da,
      dort bolme yolu da ayni tipi goruyor ve tek bir hucre yazilmiyor.

    Donusum secilmemisse ek maliyet YOK: _df_oku'nun donen tablosu
    oldugu gibi geri verilir."""
    ad, amp_mi = ((durum or {}).get("veri_seti"), False) if kaynak \
        else modelleme_kaynagi(durum)
    kopya = None if amp_mi else _calisma_kopyasi(durum, ad)
    if kopya:
        df = _dosya_oku(kopya, None if limit == -1 else limit)
    else:
        df = _df_oku(ad, limit=limit)
    # AMP_VERISETI donusumleri ZATEN ISLENMIS halde tasiyor; ikinci kez
    # uygulamak (tarih -> tarih gibi) degerleri bozardi.
    if amp_mi:
        return df
    donusumler = (durum or {}).get("tip_donusum")
    if not donusumler:
        return df
    from fe_agent import tip_donusum      # gec import: dongu olmasin
    yeni, _uygulanan, _atlanan = tip_donusum.uygula(df, donusumler)
    # Cevrilemeyen kolon KAYNAK TIPIYLE kaliyor (tip_donusum.uygula).
    # Bu noktada kullaniciya hata gosterilecek bir yuzey yok; teyit
    # adimi zaten hepsini tam veriyle dogrulamisti ve bolme adimi
    # atlananlari acikca yaziyor.
    return yeni


def _dataset_var_mi(ad):
    """Dataset AKISTA TANIMLI mi? (icinde veri olup olmadigini SOYLEMEZ.)

    Dikkat: Dataiku'da get_config(), flow'da tanimli ama hic yazilmamis
    bir dataset icin de basariyla doner. "Okuyabilir miyim" sorusunun
    cevabi icin _dataset_okunur_mu() kullanin.
    """
    if not ad:
        return False
    try:
        dataiku.Dataset(ad).get_config()
        return True
    except Exception:
        return False


def _dataset_okunur_mu(ad):
    """Dataset GERCEKTEN okunabiliyor ve en az bir satir iceriyor mu?

    Faz 03 hic degisken uretmezse _ENRICHED yazilmaz ama flow'da tanimli
    kalabilir; _dataset_var_mi True doner ve okuma aninda adim coker.
    Bu kontrol tek satirlik bir okuma denemesi yapar.
    """
    if not ad:
        return False
    try:
        df = _df_oku(ad, limit=1, onbellek=False)
        return df is not None and len(df.columns) > 0
    except Exception:
        return False

def _sayi(n):
    try:
        return "{:,}".format(int(n)).replace(",", ".")
    except Exception:
        return str(n)

def _ond(x, b=1):
    if x is None:
        return "-"
    try:
        return ("%.*f" % (b, x)).replace(".", ",")
    except Exception:
        return str(x)

def _liste(baslik, satirlar, en_fazla=12):
    if not satirlar:
        return baslik + "\n  (yok)"
    g = "\n".join("  • %s" % s for s in satirlar[:en_fazla])
    if len(satirlar) > en_fazla:
        g += "\n  … ve %d tane daha" % (len(satirlar) - en_fazla)
    return baslik + "\n" + g

def _kisa_ad(tam_ad):
    """PROJE.DATASET -> DATASET. Yalin adlar degismeden doner."""
    return tam_ad.rsplit(".", 1)[-1]

def _ad_haritasi(tam_adlar):
    """LLM'e kisa ad gonderip donen plani tam ada cevirebilmek icin
    iki yonlu harita. Iki projede ayni dataset adi varsa kisa ad
    cakisir; o durumda cakisanlar tam adiyla gonderilir."""
    sayac = {}
    for t in tam_adlar:
        k = _kisa_ad(t)
        sayac[k] = sayac.get(k, 0) + 1

    kisa_to_tam, tam_to_kisa = {}, {}
    for t in tam_adlar:
        k = _kisa_ad(t)
        gosterilecek = t if sayac[k] > 1 else k   # cakisma varsa tam ad
        kisa_to_tam[gosterilecek] = t
        tam_to_kisa[t] = gosterilecek
    return kisa_to_tam, tam_to_kisa

def _plan_adlari_cevir(plan, harita):
    """Plandaki tablo adlarini haritaya gore degistirir.
    LLM'in bazen onek atmasina karsi son care olarak kisa ad eslemesi
    de denenir."""
    def cevir(ad):
        if ad in harita:
            return harita[ad]
        # LLM oneki dusurmus olabilir: kisa ada gore ara
        for anahtar, deger in harita.items():
            if _kisa_ad(anahtar) == _kisa_ad(str(ad)):
                return deger
        return ad

    ana = plan.get("ana_tablo") or {}
    if ana.get("ad"):
        ana["ad"] = cevir(ana["ad"])

    for k in (plan.get("kaynaklar") or []):
        if isinstance(k, dict) and k.get("ad"):
            k["ad"] = cevir(k["ad"])
    return plan

def _secim_ayikla(mesaj, adet):
    numaralar = [int(n) for n in SECIM_KALIP.findall(mesaj or "")]
    gecerli = sorted({n - 1 for n in numaralar if 1 <= n <= adet})
    return gecerli or None

def _yaz(dataset_adi, tablo, yedek_dosya):
    try:
        dataiku.Dataset(dataset_adi).write_with_schema(tablo)
        onbellek_temizle(dataset_adi)
        return dataset_adi, None
    except Exception:
        _folder().upload_stream(yedek_dosya, tablo.to_csv(index=False).encode("utf-8"))
        return None, yedek_dosya

def _nerede(yazildi, yedek):
    return ("%s veri setinde" % yazildi) if yazildi \
        else ("PROJE_HAFIZASI%s dosyasında" % yedek)


def metin_yaz(yol, metin):
    """PROJE_HAFIZASI icine duz metin dosyasi yazar. Doner: basarili mi.

    AMP klasorunun "SON" isaretcisi icin var: hangi calismanin en son
    oldugunu klasor adlarina bakmadan okuyabilmek icin. Hata YUTULUR -
    isaretci yazilamadi diye asil ciktinin kaydi bosa gitmemeli."""
    try:
        _folder().upload_stream(yol, str(metin).encode("utf-8"))
        return True
    except Exception:
        return False

def sozluk_oku(durum):
    """Sozlugu OKUR - once oturumun calisma kopyasindan.

    NEDEN KOPYA ONCE: analist kategori duzeltmesini calisma kopyasina
    yapiyor (bkz. sozluk_calisma.py). Okuma orijinale giderse kullanici
    az once yaptigi duzeltmeyi bir sonraki adimda goremez; iki farkli
    sozluk dolasmaya baslar. Kopya yoksa (henuz cikarilmadi ya da
    PROJE_HAFIZASI erisilemiyor) orijinale duSULUR - calisma durmaz.

    Ic import BILEREK: sozluk_calisma bu modulu import ediyor, tersi
    modul seviyesinde yazilirsa dongu olur."""
    from fe_agent import sozluk_calisma      # dongu kirmak icin gec import
    try:
        kopya = sozluk_calisma.calisma_df(durum)
    except Exception:
        kopya = None
    if kopya is not None:
        return kopya
    return sozluk_orijinal_oku(durum)


def sozluk_orijinal_oku(durum):
    """Sozlugu dataset'ten ya da CSV yedeginden okur (KOPYAYA BAKMAZ).

    sozluk_uret_uygula() dataset yazamadiginda CSV yedegine dusuyor;
    o durumda durum["sozluk"] None, durum["sozluk_yedek"] dolu olur.
    Calisma kopyasi CIKARILIRKEN kaynak olarak bu yol kullanilir;
    baska her yer sozluk_oku()'dan gecmeli."""
    ad = durum.get("sozluk")
    if ad:
        return _df_oku(ad)
    yedek = durum.get("sozluk_yedek")
    if yedek:
        with _folder().get_download_stream(yedek) as s:
            return pd.read_csv(io.BytesIO(s.read()))
    raise AdimHatasi("Değişken sözlüğü bulunamadı; sözlük üretimi adımını "
                     "tamamlamanız gerekiyor.")

# ===========================================================================
# BOLME  -  LEAKAGE SINIRI
# ===========================================================================
# ===========================================================================
# KOLON OZETI  -  feature tablosunun tek kaynagi
# ---------------------------------------------------------------------------
# NEDEN VAR
#   VERİ & SÖZLÜK sekmesindeki feature tablosu veri setinin BUTUN
#   kolonlarini listeler ve her /analiz cagrisinda yeniden uretilir.
#   Tabloyu uretirken veri setini yeniden okumak 1.042 kolonluk bir
#   tabloda her mesajda dakikalar demek. Bu yuzden kolon basina kucuk
#   bir ozet, veri seti ZATEN OKUNURKEN (profil adimlarinda) bir kez
#   cikarilip durum'a yazilir.
#
# NEDEN BU KADAR AZ ALAN
#   Ozet oturum JSON'una giriyor ve her turda yeniden yaziliyor. Kolon
#   basina dort kucuk alan (~100 bayt) 1.042 kolonda ~100 KB eder;
#   dagilim, min/maks, ornek listesi eklemek dosyayi megabaytlara
#   tasirdi. Tekil sayisi burada YOK: nunique tam tarama ister, profil
#   adimi zaten hesapliyor, oradan tamamlaniyor.
#
# NEDEN ORNEK DEGER MASKELENIYOR
#   Ornek deger ekranda gorunur. Kisisel veri iceren kolonlarda gercek
#   deger gostermek, sozluk uretiminde LLM'e gondermemek icin verdigimiz
#   ugrasi bosa cikarir. sozluk.py'nin PII denetimi burada da calisir.
# ===========================================================================
# Ornek deger ararken taranan satir sayisi. Tam tarama 1.042 kolonda
# gereksiz; ilk N satirda hic dolu deger yoksa ornek bos birakilir.
ORNEK_TARAMA = 200
ORNEK_UZUNLUK = 40
ORNEK_MASKE = "•••"


def _ornek_metni(deger):
    metin = str(deger).strip()
    if len(metin) > ORNEK_UZUNLUK:
        return metin[:ORNEK_UZUNLUK - 1] + "…"
    return metin


def kolon_ozeti_cikar(df):
    """Kolon basina {ad, tip, null_oran, ornek}. Tekil sayisi YOK.

    Veri seti secildiginde, tablo zaten okunmusken cagrilir."""
    from fe_agent import sozluk as sozluk_mod    # PII denetimi tek yerde

    if df is None or not len(df.columns):
        return []

    try:
        null_oranlari = df.isna().mean()
    except Exception:
        null_oranlari = {}
    bas = df.head(ORNEK_TARAMA)

    ozet = []
    for kol in df.columns:
        s = df[kol]
        if pd.api.types.is_numeric_dtype(s):
            tip = "sayısal"
        elif str(s.dtype).startswith("datetime"):
            tip = "tarih"
        else:
            tip = "kategorik"

        try:
            oran = float(null_oranlari[kol])
        except Exception:
            oran = None

        ornek = None
        try:
            dolu = bas[kol].dropna()
            if len(dolu):
                if (sozluk_mod._pii_ad_mi(kol)
                        or sozluk_mod._pii_deger_mi(dolu.head(8))):
                    ornek = ORNEK_MASKE
                else:
                    ornek = _ornek_metni(dolu.iloc[0])
        except Exception:
            ornek = None

        ozet.append({"ad": str(kol), "tip": tip,
                     "null_oran": None if oran is None else round(oran, 4),
                     "tekil": None, "ornek": ornek})
    return ozet


def kolon_ozeti_tamamla(profil, tablo, df=None):
    """Profil adiminin urettigi tablodan tekil sayisi ve null oranini isler.

    sfa.profil_cikar zaten her kolon icin UNIQUE ve NULL_RATIO
    hesapliyor; ikinci kez hesaplamak ayni taramayi tekrarlamak olur.

    Profilde olmayan kolonlar (target/id/donem ve surec disi birakilanlar)
    ozette kalir ama UNIQUE'leri hic olculmemis olur. df verilirse bu
    bosluk TAM TABLODAN kapatilir: kimligin kac tekil degeri oldugu
    "bu tablo musteri bazli mi, musteri-ay bazli mi" sorusunun cevabi
    ve feature tablosunda bos gormek anlamsizdi."""
    ozet = list((profil or {}).get("kolon_ozet") or [])
    if tablo is not None and len(tablo):
        try:
            kayit = {str(r["FEATURE"]): r for _, r in tablo.iterrows()}
        except Exception:
            kayit = {}
        for satir in ozet:
            r = kayit.get(satir.get("ad"))
            if r is None:
                continue
            try:
                satir["tekil"] = int(r["UNIQUE"])
            except Exception:
                pass
            try:
                satir["null_oran"] = round(float(r["NULL_RATIO"]), 4)
            except Exception:
                pass

    # Profilin disinda kalanlar: tek bir nunique() cagrisiyla, ayri bir
    # okuma yapmadan. Tablo zaten cagiranin elinde.
    if df is not None:
        eksik = [s["ad"] for s in ozet
                 if s.get("tekil") is None and s.get("ad") in df.columns]
        if eksik:
            try:
                tekiller = df[eksik].nunique(dropna=True)
                for satir in ozet:
                    if satir.get("ad") in tekiller.index:
                        satir["tekil"] = int(tekiller[satir["ad"]])
            except Exception:
                pass          # olculemezse bos kalir, adim durmaz
    return ozet


def _oran_kirp(deger, yedek=0.20):
    """Oran alanlarini guvenli araliga ceker.

    Durum JSON'dan okunuyor; elle duzeltilmis bir kayitta metin ya da 0
    gelebilir. %0 bir set hic satir birakmaz, %100 karsi tarafi bosaltir."""
    try:
        oran = float(deger)
    except (TypeError, ValueError):
        oran = float(yedek)
    if not (oran > 0):
        oran = float(yedek)
    return min(max(oran, 0.01), 0.90)


def _tam_sayi(deger, yedek, en_az):
    try:
        return max(int(deger), en_az)
    except (TypeError, ValueError):
        return yedek



def bolme_ayarlari(durum):
    """durum["bolme"]'yi varsayilanlariyla tamamlar; durumu DEGISTIRMEZ.

    Bolme IKI ASAMALIDIR ve EN FAZLA UC SET uretir:

      1) test nasil ayrilir  -> test_tanim
           "zamansal": son N donem test olur. OOT ile AYNI SEYDIR; ayrica
                       bir OOT seti ACILMAZ. Donem kolonu varsa varsayilan.
           "rastgele": test_oran kadar rastgele ayrilir.
      2) kalan train nasil kullanilir -> val_var x cv
           full train / train+val / full train+CV / train+val+CV

    NEDEN BOYLE: onceki surumde OOT ucuncu bagimsiz eksendi ve zamansal
    bolmede hem "test" hem "oot" aciliyordu - ayni fikrin iki kopyasi,
    dort setli bir tablo ve kullanicinin istemedigi bir holdout. OOT bir
    set degil, TESTIN TANIMIDIR.

    Eski oturum dosyalarinda bu alanlarin hicbiri yok. Eksik alan burada
    varsayilanina duser: eski oturum ne patlar ne de sessizce baska bir
    bolme uretir."""
    b = dict(durum.get("bolme") or {})
    m = durum.get("meta") or {}
    p = durum.get("profil") or {}

    a = dict(b)

    # test_tanim: eski "tur" alani birebir karsiligidir, gecis icin okunur.
    hazir_var = isinstance(durum.get("_hazir_bolme"), dict)
    ham = b.get("test_tanim") or b.get("tur")
    if ham not in ("rastgele", "zamansal", "hazir"):
        # Donem kolonu varsa zamansal test hem daha dogru hem Model Risk'in
        # bekledigi bicim; yoksa tek secenek rastgele.
        ham = "zamansal" if m.get("donem") else "rastgele"
    if ham == "zamansal" and not m.get("donem"):
        ham = "rastgele"
    # Hazir bolme SECILMIS ama tabloda artik yok (veri seti degistirildi):
    # sessizce rastgeleye dusuluyor, yoksa setler() her cagrida patlardi.
    if ham == "hazir" and not hazir_var:
        ham = "zamansal" if m.get("donem") else "rastgele"
    a["test_tanim"] = ham
    a["tur"] = ham                     # modul ici eski ad, ayni deger

    kimlik = m.get("id")
    birim = b.get("birim") if b.get("birim") in ("satir", "kimlik") else None
    if birim is None:
        birim = "kimlik" if kimlik else "satir"
    # Kimlik kolonu yokken "kimlik" birimi bos bir sozdur: gruplanacak
    # anahtar yok. Alan satira cekiliyor ki panel de gercegi gostersin.
    a["birim"] = birim if kimlik else "satir"

    if "katmanla" in b:
        a["katmanla"] = bool(b["katmanla"])
    else:
        # Surekli hedefte her farkli deger kendi katmani olur; katmanlarin
        # neredeyse tamami tek satirlik kalir ve test seti fiilen bosalir.
        # Bu yuzden katmanlama varsayilan olarak YALNIZCA binary hedefte
        # aciktir. Hedef tipi henuz olculmemisse (profil calismamis) eski
        # davranis korunur: hedef tanimliysa katmanla.
        a["katmanla"] = bool(m.get("target")) and p.get("hedef_tip") != "surekli"

    a["val_var"] = bool(b.get("val_var", False))
    a["val_oran"] = _oran_kirp(b.get("val_oran"), 0.20)
    a["test_oran"] = _oran_kirp(b.get("test_oran"), 0.20)

    a["cv"] = b.get("cv") if b.get("cv") in ("yok", "kfold", "zaman") \
        else "kfold"
    a["kat"] = min(_tam_sayi(b.get("kat"), 5, KAT_EN_AZ), KAT_EN_COK)

    # AYRI BIR OOT SETI YOK. Zamansal testte test zaten OOT'dur; rastgele
    # testte OOT diye bir sey yoktur. Alan yalnizca _oot_maske()'yi bos
    # dondurmek icin duruyor ve DISARIDAN AYARLANAMAZ.
    a["oot_var"] = False

    # Zamansal testte hangi donemler test olacak: son `adet` donem ya da
    # elle secilenler. Eskiden bu alan ayri OOT setini tarif ediyordu.
    t = b.get("oot_tanim") if isinstance(b.get("oot_tanim"), dict) else {}
    a["oot_tanim"] = {
        "tur": t.get("tur") if t.get("tur") in ("son_donem", "secili")
               else "son_donem",
        "deger": t.get("deger"),
        "adet": _tam_sayi(b.get("oot_adet", t.get("adet")), 1, 1),
    }
    a["oot_adet"] = a["oot_tanim"]["adet"]

    # Kullanicinin gordugu tek alan: kalan train nasil kullanilacak.
    a["train_kullanimi"] = _train_kullanimi(a)

    a["seed"] = _tam_sayi(b.get("seed"), 42, 0)

    # SEED STRATEJISI: tek bolme mi, farkli seed'lerle tekrar mi
    # (kullanici istegi: "sadece Seed = 42 yeterli değil").
    a["seed_tur"] = b.get("seed_tur") if b.get("seed_tur") in ("sabit", "coklu") \
        else "sabit"
    a["tekrar"] = min(_tam_sayi(b.get("tekrar"), 1, 1), TEKRAR_EN_COK)
    if a["seed_tur"] == "sabit":
        a["tekrar"] = 1
    elif a["tekrar"] < 2:
        # "Çoklu tekrar" secilip tekrar 1 kalirsa ayar hicbir sey
        # yapmiyor demektir; en az iki tekrar.
        a["tekrar"] = 2

    # ZAMANSAL BOLMEDE BOSLUK (gap): egitim ile OOT/Test donemleri
    # arasinda modele HIC dahil edilmeyen donem sayisi. Performans
    # penceresi yuzunden iki tarafin ayni gozlemi paylasmasini engeller.
    a["gap"] = min(_tam_sayi(b.get("gap"), 0, 0), GAP_EN_COK)
    if a["test_tanim"] != "zamansal":
        a["gap"] = 0
    return a


# Kullanicinin dort secenegi <-> (val_var, cv) esleme. Panelde tek alan,
# kodda iki eksen: ikisini tek yerde eslemek, formun ve motorun ayri
# ayri yorumlamasini engelliyor.
TRAIN_KULLANIMI = {
    "full":    {"val_var": False, "cv": "yok"},
    "val":     {"val_var": True,  "cv": "yok"},
    "full_cv": {"val_var": False, "cv": "kfold"},
    "val_cv":  {"val_var": True,  "cv": "kfold"},
}
# Kisa etiketler TEK YERDEN: BOLME_SECENEK. Bu sozluk eski cagiranlar
# icin duruyor ve ordan turetiliyor, yoksa ayni secenegin iki ayri adi
# olurdu.
TRAIN_KULLANIMI_BASLIK = {}


# ===========================================================================
# BOLME SOZLUGU - ekranda gorunen her secenegin TURKCE adi ve aciklamasi
# ===========================================================================
# NEDEN ACIKLAMA DA VAR: bu alanlarin Turkce karsiliklari kurum ici
# konusma dilinde her zaman kullanilmiyor. "Çapraz doğrulama" yazip
# birakmak, terimi Ingilizcesiyle taniyan ama Turkcesini duymamis
# kullaniciyi ekranda yalniz birakiyordu. Her seceneğin yaninda tek
# cumlelik bir aciklama duruyor ve aciklama, gerektiginde terimin
# sektorde yaygin karsiligini da soyluyor.
#
# TEK KAYNAK: hem sohbet karti hem sag panel hem de adim metinleri bu
# sozlukten okuyor. Etiketi bir yerde degistirip digerini unutmak,
# kullaniciya iki farkli ad gostermek demekti.
# ---------------------------------------------------------------------------
# EKRAN DILI: KISA ETIKET + KISA SATIR; UZUN ANLATIM DETAYDA
# ---------------------------------------------------------------------------
# Kullanici karari: "daha basitçe sadece seçimli yan yana iki kutuda bir
# seçim ... altta da genel olarak açıklamaların olması, eğer detay
# istenirse bakılabilir tarzda açılabilir bir opsiyonlu sekmeyle, eğer
# istenmiyorsa zaten otomatik kapalı".
#
# Onceki surumde her secenegin ve her alanin altinda birkac cumlelik
# aciklama duruyordu. Sonuc: kullanici SECIM yapmadan once METIN OKUMAK
# zorunda kaliyordu - yanlis sira. Simdi:
#   secenek altinda      -> EN FAZLA BIR KISA CUMLE
#   sektor karsiligi     -> "Detayları göster" icindeki TERIMLER listesi
# Terim aciklamalari KAYBOLMADI, ikinci plana alindi.
BOLME_SECENEK = {
    "test_tanim": {
        "zamansal": ("Zamansal",
                     "Eski dönemler geliştirme, yeni dönemler OOT / Test."),
        "rastgele": ("Rastgele", "Kayıtlar rastgele ikiye ayrılır."),
        "hazir":    ("Veri setindeki bölme",
                     "Tablodaki bölme kolonu olduğu gibi kullanılır."),
    },
    "train_kullanimi": {
        "full":    ("Sadece eğitim", "Kalan verinin tamamıyla eğitilir."),
        "val":     ("Eğitim + doğrulama", "Bir parça ayrı tutulur."),
        "full_cv": ("Sadece eğitim + çapraz doğrulama",
                    "Veri parçalara bölünüp sırayla sınanır."),
        "val_cv":  ("Eğitim + doğrulama + çapraz doğrulama",
                    "İkisi birden uygulanır."),
        "ozel":    ("Özel", "Hazır seçeneklerin dışında bir birleşim."),
    },
    "birim": {
        "satir":  ("Satır", "Her satır tek başına dağıtılır."),
        "kimlik": ("Kimlik", "Aynı müşterinin satırları aynı tarafta kalır."),
    },
    "cv": {
        "yok":   ("Yok", "Çapraz doğrulama yapılmaz."),
        "kfold": ("Stratified K-Fold", "Eşit parçalara bölünür."),
        "zaman": ("Zaman sıralı", "Parçalar dönem sırasına göre ayrılır."),
    },
    # Seed stratejisi: tek bolme mi, farkli seed'lerle tekrar mi.
    "seed_tur": {
        "sabit": ("Sabit bölme", "Tek seed; her çalıştırmada aynı bölme."),
        "coklu": ("Çoklu tekrar", "Farklı seed'lerle tekrarlanır."),
    },
    "oot_tur": {
        "son_donem": ("Son dönemler", ""),
        "secili":    ("Belirli dönem", ""),
    },
}

# Alan adlari: kisa ve ekranda okunmaya degecek kadar acik.
BOLME_ALAN_BASLIK = {
    "test_tanim":      "OOT / Test Ayrımı",
    "oot_adet":        "OOT / Test Dönemi",
    "test_oran":       "OOT / Test Büyüklüğü",
    # TEK AD KURALI: satir etiketi de sozluk maddesi de "Ara Dönem
    # (Gap)". Ayni ayar icin iki ad ("Dönemler Arası Boşluk") ekranda
    # iki farkli sey sanilmasina yol aciyordu.
    "gap":             "Ara Dönem (Gap)",
    "train_kullanimi": "Kalan Veri Kullanımı",
    "birim":           "Bölme Birimi",
    "val_var":         "Doğrulama Seti",
    "val_oran":        "Doğrulama Büyüklüğü",
    "cv":              "Çapraz Doğrulama",
    "kat":             "Kat Sayısı",
    "tekrar":          "Tekrar Sayısı",
    "katmanla":        "Hedef Dağılımı",
    "seed_tur":        "Tekrarlanabilirlik",
    "seed":            "Seed",
    "oot_tur":         "OOT / Test Dönemi Seçimi",
    "oot_deger":       "OOT / Test Dönemi",
}

# Alan altindaki TEK KISA SATIR. Uzunu (sektor karsiligi dahil)
# BOLME_SATIR_ACIKLAMA'da, "Detayları göster" alaninda.
BOLME_ALAN_ACIKLAMA = {
    "test_tanim":      "OOT / Test seti eğitimde hiç kullanılmaz.",
    "oot_adet":        "Hangi dönemler OOT / Test olsun.",
    "test_oran":       "Kayıtların ne kadarı OOT / Test olsun.",
    "train_kullanimi": "OOT / Test ayrıldıktan sonra kalan veri.",
    "birim":           "Satırlar mı müşteriler mi bir arada tutulsun.",
    "val_var":         "Model seçimi için ayrılan ara değerlendirme seti.",
    "val_oran":        "Eğitim verisinin ne kadarı doğrulamaya ayrılsın.",
    "cv":              "Ölçüm tek bir bölmenin şansına bağlı kalmasın.",
    "kat":             "Veri kaç parçaya bölünsün.",
    "katmanla":        "Hedefin oranı her parçada aynı kalsın.",
    "oot_tur":         "Hangi dönemler OOT / Test olsun.",
    "oot_deger":       "OOT / Test için kullanılacak dönem.",
    "gap":             "Atlanacak dönem sayısı.",
    "seed_tur":        "Tek bölme mi, farklı bölmelerle tekrar mı.",
    "tekrar":          "Kaç farklı bölmeyle tekrarlansın.",
    "seed":            "Aynı sayı, her çalıştırmada aynı bölme.",
}

# Not: alan altindaki bu kisa cumle ANA EKRANDA CIZILMIYOR (bkz.
# bolmeSatirCiz). Satirin ne oldugunu "?" ipucu, metodolojiyi
# "Detaylar ve Terimler" anlatiyor. Alan aciklamalari sozlesmede
# duruyor: eski istemci ve HAZIRLIK ozeti hala okuyor.


# BOLME_SECENEK tanimlandiktan SONRA dolduruluyor: sozluk yukarida,
# etiketler burada tek kaynaktan turetiliyor.
TRAIN_KULLANIMI_BASLIK.update(
    {k: v[0] for k, v in BOLME_SECENEK["train_kullanimi"].items()
     if k in TRAIN_KULLANIMI})


def bolme_etiket(alan, deger):
    """Bir bolme secenegi icin kullanicinin gordugu ad. Sozlukte yoksa
    ham deger doner - eski oturumda taninmayan bir deger durabilir ve
    bos bir etiket, ekranda kaybolan bir ayar demekti."""
    secenek = BOLME_SECENEK.get(alan) or {}
    kayit = secenek.get(deger)
    return kayit[0] if kayit else str(deger)


def bolme_aciklama(alan, deger):
    """Bir bolme secenegin tek cumlelik aciklamasi; yoksa bos dize."""
    secenek = BOLME_SECENEK.get(alan) or {}
    kayit = secenek.get(deger)
    return kayit[1] if kayit else ""


def bolme_secenek_listesi(alan, secenekler, kilitliler=()):
    """On yuze gidecek secenek listesi: anahtar + ad + aciklama + kilit.

    Kilit SEBEBI de tasiniyor: pasif bir dugmeyi sebepsiz birakmak
    kullaniciya "bozuk" hissi veriyordu (bkz. akis_panel.bolme_formu)."""
    kilitliler = set(kilitliler or ())
    return [{"anahtar": s,
             "etiket": bolme_etiket(alan, s),
             "aciklama": bolme_aciklama(alan, s),
             "kilitli": s in kilitliler}
            for s in secenekler]


def _train_kullanimi(a):
    """(val_var, cv) ikilisinden kullanicinin gordugu tek etiket.

    cv="zaman" (walk-forward) dort hazir secenegin disinda kaldigi icin
    "ozel" doner; panel o zaman ince ayar alanlarini gosterir."""
    if a.get("cv") == "zaman":
        return "ozel"
    for ad, esleme in TRAIN_KULLANIMI.items():
        if (bool(a.get("val_var")) == esleme["val_var"]
                and a.get("cv") == esleme["cv"]):
            return ad
    return "ozel"


# ===========================================================================
# SETLER - dort ayrik maske
# ===========================================================================
def _bos_maske(df):
    return pd.Series(False, index=df.index)


def _donem_metni(durum, df):
    """Donem kolonu METIN Serisi; kolon yoksa None.

    Donem degerleri her yerde metin olarak siralaniyor (bkz. tanimlar_uygula);
    sayi/metin karisikligi ayni donemi iki farkli deger gibi gostermesin
    diye burada da metne cevriliyor."""
    donem = (durum.get("meta") or {}).get("donem")
    if donem and donem in df.columns:
        return df[donem].astype(str)
    return None


def _oot_donemleri(ds, a):
    """OOT'ye ayrilacak donem degerleri."""
    tum = sorted(pd.unique(ds.dropna()).tolist())
    if not tum:
        return []
    t = a["oot_tanim"]
    if t["tur"] == "secili" and t["deger"] not in (None, "", []):
        d = t["deger"]
        secili = set(str(x) for x in
                     (d if isinstance(d, (list, tuple)) else [d]))
        return [x for x in tum if x in secili]
    return tum[-t["adet"]:]


def _oot_maske(durum, df, a, notlar):
    """Bagimsiz OOT ekseni. ONCE ayrilir; kalan satirlar train/val/test olur.

    OOT donem bazlidir; kimlik bazli bolmede bile ayni musteri hem gelistirme
    hem OOT doneminde gorunebilir. Bu bir sizinti degil, OOT'nin tanimidir:
    olculen sey zaman icindeki dayaniklilik, gorulmemis musteri degil."""
    if not a["oot_var"]:
        return _bos_maske(df)

    ds = _donem_metni(durum, df)
    if ds is None:
        notlar.append("Zamansal test istendi ama dönem kolonu tanımlı "
                      "değil; test dönemlere göre ayrılamadı.")
        return _bos_maske(df)

    donemler = _oot_donemleri(ds, a)
    oot = ds.isin(set(donemler)) if donemler else _bos_maske(df)
    ayrilan, kalan = int(oot.sum()), int((~oot).sum())

    if ayrilan == 0:
        notlar.append("Seçilen test dönemi veride bulunamadı; test "
                      "dönemlere göre ayrılamadı.")
        return _bos_maske(df)
    if kalan < MIN_SET_SATIR:
        # Tek donemli tabloda "son donem" TUM satirlardir; OOT'yi ayirmak
        # gelistirme setini bosaltirdi.
        notlar.append("Test olarak ayrılacak dönem satırların neredeyse "
                      "tamamını kapsıyor (geriye %s satır kalıyor); "
                      "bu ayrım kurulmadı." % _sayi(kalan))
        return _bos_maske(df)
    if ayrilan < MIN_SET_SATIR:
        notlar.append("OOT / Test seti %s satır; %s satırın altındaki sette ölçüm "
                      "güvenilir değil."
                      % (_sayi(ayrilan), _sayi(MIN_SET_SATIR)))
    return oot


def _katman_serisi(df, durum, katmanla):
    """Katmanlama anahtari. Katmanlama kapaliysa tek katman doner."""
    hedef = (durum.get("meta") or {}).get("target")
    if katmanla and hedef and hedef in df.columns:
        return df[hedef].astype(str).fillna("__BOS__")
    return pd.Series(["__TEK__"] * len(df), index=df.index)


def _katmanli_bolum_secimi(katman, oranlar, seed):
    """Katmanli KONUM secimi. Doner: {bolum: [konum, ...]}

    oranlar SIRALIDIR: her katmandan once listenin ilk bolumunun payi
    ayrilir. Sira sabit tutuldugu icin listeye val eklemek test setini
    DEGISTIRMEZ; val'li ve val'siz bolme ayni test satirlarini verir.

    Her katmandan en az bir satir alinir ve en az bir satir egitime
    birakilir; dusuk temerrut oranli portfoyde duz orantili pay test
    setini pozitif kayit acisindan bos birakabiliyor."""
    rng = np.random.RandomState(int(seed))
    secim = {ad: [] for ad, _ in oranlar}
    for _, konumlar in sorted(
            {k: np.flatnonzero((katman == k).to_numpy())
             for k in pd.unique(katman)}.items(), key=lambda x: str(x[0])):
        if len(konumlar) == 0:
            continue
        karisik = konumlar.copy()
        rng.shuffle(karisik)
        bas = 0
        for ad, oran in oranlar:
            n = int(round(len(karisik) * oran))
            if len(karisik) >= len(oranlar) + 1:
                n = max(n, 1)
            n = min(n, len(karisik) - bas - 1) if len(karisik) > bas + 1 else 0
            if n <= 0:
                continue
            secim[ad].extend(karisik[bas:bas + n].tolist())
            bas += n
    return {ad: sorted(v) for ad, v in secim.items()}


def _kimlik_bazli_bolme(df, durum, kimlik, oranlar, a):
    """Kimlik SEVIYESINDE katmanli bolme. Ayni musteri iki sete birden
    dusmez. Doner: {bolum: [kimlik, ...]}"""
    anahtarlar = df[kimlik].astype(str)
    hedef = (durum.get("meta") or {}).get("target")

    if a["katmanla"] and hedef and hedef in df.columns:
        # Kimlik duzeyinde katman: kimligin en yuksek hedef degeri
        yardim = pd.DataFrame({"_k": anahtarlar,
                               "_y": pd.to_numeric(df[hedef], errors="coerce")})
        kimlik_tablo = yardim.groupby("_k", sort=True)["_y"].max().reset_index()
        kimlik_tablo.columns = [kimlik, hedef]
    else:
        kimlik_tablo = pd.DataFrame({kimlik: sorted(anahtarlar.unique())})

    kimlik_tablo = kimlik_tablo.reset_index(drop=True)
    secim = _katmanli_bolum_secimi(
        _katman_serisi(kimlik_tablo, durum, a["katmanla"]), oranlar, a["seed"])
    return {ad: sorted(kimlik_tablo.loc[secim[ad], kimlik].astype(str))
            for ad, _ in oranlar}


def _tamamla(df, oot, val, test, bosluk=None):
    """Dort seti AYRIK hale getirir; egitim geriye kalan satirlardir.

    Oncelik OOT > test > val: cakisma olursa satir egitimin DISINDA kalir.
    Ters oncelik bir cakismayi sessizce egitime sizdirirdi.

    `bosluk`: zamansal bolmede egitim ile OOT/Test arasinda atlanan
    donemlerin maskesi. Bu satirlar HICBIR SETE girmez - ne egitime ne
    teste. Gap'in tanimi budur: atlanan donem modele hic dahil edilmez."""
    oot = oot.astype(bool)
    test = test.astype(bool) & ~oot
    val = val.astype(bool) & ~oot & ~test
    disarda = oot | test | val
    if bosluk is not None:
        disarda = disarda | bosluk.astype(bool)
    return {"egitim": ~disarda, "val": val, "test": test, "oot": oot}


def _zamansal_val(ds, test_donemi, a, oot):
    """Zamansal bolmede val: test doneminden ONCEKI donem(ler).

    Donem degerleri ayrik oldugu icin val_oran birebir tutturulamaz;
    val_oran'i karsilayan en az sayida onceki donem alinir ve egitime en
    az bir donem birakilir. Egitime donem kalmiyorsa val kurulmaz."""
    tum = sorted(pd.unique(ds.dropna()).tolist())
    if test_donemi not in tum:
        return pd.Series(False, index=ds.index)
    onceki = [d for d in tum[:tum.index(test_donemi)]
              if not bool(oot[(ds == d).to_numpy()].any())]
    if len(onceki) < 2:
        return pd.Series(False, index=ds.index)

    havuz = int(ds.isin(set(onceki)).sum())
    secili, toplanan = [], 0
    for d in reversed(onceki[1:]):
        secili.append(d)
        toplanan += int((ds == d).sum())
        if havuz and toplanan / float(havuz) >= a["val_oran"]:
            break
    return ds.isin(set(secili))


def _zamansal_test_donemleri(durum, ds, a):
    """Zamansal testte hangi donemler test olacak.

    Once bolme adiminin sectigi `oot_deger` (tek donem) kullanilir; kullanici
    panelden `oot_adet` ile son N donem derse o kazanir. Ikisi de yoksa son
    donem test olur - donem kolonu varken test'siz kalmak anlamsiz."""
    b = durum.get("bolme") or {}

    # KALICI LISTE ONCE. Donemleri her cagrida o an OKUNAN tablodan
    # turetmek, kisa bir okumada (ornegin tek satir) o satirin donemini
    # "son donem" yapip test'e dusuruyordu; ayni satir bir adimda egitim,
    # digerinde test oluyor ve sizinti siniri kayiyordu. Liste bolme
    # adiminda BIR KEZ hesaplanip duruma yaziliyor.
    kalici = b.get("test_donemleri")
    if kalici:
        return [str(x) for x in kalici]

    adet = int((a.get("oot_tanim") or {}).get("adet") or 1)
    secili = (a.get("oot_tanim") or {}).get("deger")

    if (a.get("oot_tanim") or {}).get("tur") == "secili" and secili:
        return [str(x) for x in (secili if isinstance(secili, (list, tuple))
                                 else [secili])]
    if b.get("oot_deger") is not None and adet <= 1:
        return [str(b["oot_deger"])]
    sirali = sorted(set(ds.dropna().astype(str)))
    return sirali[-adet:] if sirali else []


def _setler_zamansal(durum, df, a, oot):
    """Zamansal bolme deterministiktir: kalici kayit gerekmez, donem
    kolonundan her defasinda ayni setler cikar.

    Buradaki `test` AYNI ZAMANDA OOT'dur; ayrica bir OOT seti acilmaz."""
    ds = _donem_metni(durum, df)
    donemler = _zamansal_test_donemleri(durum, ds, a)
    hedef_donem = donemler[0] if donemler else None
    test = ds.isin(set(donemler)) & ~oot if donemler else _bos_maske(df)
    bosluk = _zamansal_bosluk(ds, donemler, a, df)
    val = _zamansal_val(ds, hedef_donem, a, oot) if a["val_var"] \
        else _bos_maske(df)
    val = val & ~bosluk
    return _tamamla(df, oot, val, test, bosluk)


def _zamansal_bosluk(ds, test_donemleri, a, df):
    """Egitim ile OOT/Test arasinda ATLANAN donemlerin maskesi.

    Kredi riskinde performans penceresi yuzunden son egitim donemi ile
    ilk test donemi ayni musterinin ayni gozlem penceresini
    paylasabiliyor; bu ince bir sizintidir. `gap` kadar donem iki tarafa
    da alinmaz.

    BOSLUK EGITIMI BOSALTAMAZ: atlanacak donem sayisi, egitime en az bir
    donem birakacak kadar kirpilir. Aksi halde bir ayar hatasi butun
    egitim setini sessizce silerdi."""
    n = int(a.get("gap") or 0)
    if n <= 0 or not test_donemleri:
        return _bos_maske(df)
    tum = sorted(set(str(x) for x in pd.unique(ds.dropna())))
    kalan = [d for d in tum if d not in set(test_donemleri)]
    if len(kalan) <= 1:
        return _bos_maske(df)
    n = min(n, len(kalan) - 1)
    return ds.isin(set(kalan[-n:]))


def _setler_kimlik(df, kimlik, listeler, oot):
    """Kalici kimlik listelerinden setler. Ayni kimlik hangi uzunlukta
    okunan tabloda olursa olsun ayni sete duser."""
    anahtar = df[kimlik].astype(str)
    parca = {}
    for ad in ("val", "test"):
        kl = listeler.get(ad)
        parca[ad] = anahtar.isin(set(str(k) for k in kl)) if kl \
            else _bos_maske(df)
    return _tamamla(df, oot, parca["val"], parca["test"])


# ===========================================================================
# VERI SETINDE HAZIR DURAN BOLME
# ---------------------------------------------------------------------------
# Kullanici istegi: "_TRAIN _OOT _VAL varsa ayrılmalı, hepsi orijinal
# korunmalı ama yine seçime göre geri dönmek istersem diye".
#
# Ekipler bolmeyi cogu zaman tabloya ONCEDEN yaziyor. Platformun bunu
# gormezden gelip yeniden rastgele bolmesi, ayni veri uzerinde ikinci ve
# FARKLI bir bolme uretmek demek: daha once uretilmis skorlarla
# karsilastirma imkansizlasiyor.
#
# IKI BICIM taniniyor, cunku ikisi de yayginn:
#   1. TEK ETIKET KOLONU  - degerleri TRAIN / VAL / TEST / OOT olan kolon
#   2. AYRI BAYRAK KOLONLARI - <onek>_TRAIN, <onek>_VAL, <onek>_TEST,
#      <onek>_OOT adli 0/1 kolonlar
#
# KAYNAK TABLOYA DOKUNULMAZ: kolonlar oldugu gibi kalir, yalnizca
# OKUNUR. Kullanici isterse kendi bolmesine (zamansal/rastgele) geri
# donebilir; hazir bolme bir secenek, dayatma degil.
# ===========================================================================

# Etiket kolonundaki deger -> set adi. Turkce karsiliklari da taniniyor:
# tablo bir Dataiku recipe'inden de gelebilir, elle de yazilmis olabilir.
HAZIR_ETIKET = {
    "train": "egitim", "egitim": "egitim", "eğitim": "egitim",
    "development": "egitim", "dev": "egitim", "gelistirme": "egitim",
    "val": "val", "validation": "val", "valid": "val",
    "dogrulama": "val", "doğrulama": "val",
    "test": "test", "holdout": "test",
    "oot": "oot", "out_of_time": "oot", "outoftime": "oot",
    "zaman_disi": "oot", "zaman dışı": "oot",
}

# Bayrak kolonlarinin son eki -> set adi.
HAZIR_SONEK = {
    "_TRAIN": "egitim", "_EGITIM": "egitim",
    "_VAL": "val", "_VALID": "val", "_DOGRULAMA": "val",
    "_TEST": "test",
    "_OOT": "oot",
}

# Bir etiket kolonu icin en cok kac farkli deger kabul edilir. Dorde
# kadar set + birkac yazim farki; ustu, bolme kolonu degil kategorik bir
# degiskendir.
HAZIR_MAX_DEGER = 8


def _hazir_dogru_mu(sayim):
    """Bulunan bolme KULLANILABILIR mi: en az egitim ve test dolu olmali.

    Yalnizca "train" yazan bir kolon bolme degildir; test seti yoksa
    sizinti siniri cizilemez ve o kolonu bolme diye sunmak kullaniciyi
    ilerleyemeyecegi bir secime goturur."""
    return bool(sayim.get("egitim")) and bool(sayim.get("test"))


def _hazir_etiket_kolonu(df, kol):
    """Kolon bir bolme ETIKETI tasiyor mu? Tasiyorsa tanim, yoksa None."""
    try:
        seri = df[kol].dropna()
    except Exception:
        return None
    if not len(seri):
        return None
    try:
        benzersiz = seri.astype(str).str.strip().str.lower().unique()
    except Exception:
        return None
    if not len(benzersiz) or len(benzersiz) > HAZIR_MAX_DEGER:
        return None

    esleme = {}
    for ham in benzersiz:
        hedef = HAZIR_ETIKET.get(str(ham))
        if hedef is None:
            return None                     # tanimsiz deger -> bolme degil
        esleme[str(ham)] = hedef

    normal = seri.astype(str).str.strip().str.lower()
    sayim = {}
    for ham, hedef in esleme.items():
        sayim[hedef] = sayim.get(hedef, 0) + int((normal == ham).sum())
    if not _hazir_dogru_mu(sayim):
        return None
    return {"tur": "etiket", "kolon": str(kol), "kolonlar": [str(kol)],
            "esleme": esleme, "sayim": sayim}


def _ikili_mi(seri):
    """Seri 0/1 (ya da True/False) bayragi mi?"""
    try:
        dolu = seri.dropna()
        if not len(dolu):
            return False
        benzersiz = set(pd.to_numeric(dolu, errors="coerce").dropna().unique())
    except Exception:
        return False
    return bool(benzersiz) and benzersiz.issubset({0, 1, 0.0, 1.0})


def _hazir_bayrak_kolonlari(df):
    """<onek>_TRAIN / _VAL / _TEST / _OOT ucluleri. Yoksa None."""
    gruplar = {}
    for kol in df.columns:
        ad = str(kol)
        buyuk = ad.upper()
        for sonek, hedef in HAZIR_SONEK.items():
            if buyuk.endswith(sonek) and len(buyuk) > len(sonek):
                on_ek = buyuk[:-len(sonek)]
                gruplar.setdefault(on_ek, {})[hedef] = ad
                break

    for on_ek in sorted(gruplar):
        esleme = gruplar[on_ek]
        if "egitim" not in esleme or "test" not in esleme:
            continue
        if not all(_ikili_mi(df[a]) for a in esleme.values()):
            continue
        sayim = {}
        for hedef, ad in esleme.items():
            try:
                sayim[hedef] = int(pd.to_numeric(df[ad], errors="coerce")
                                   .fillna(0).astype(bool).sum())
            except Exception:
                sayim[hedef] = 0
        if not _hazir_dogru_mu(sayim):
            continue
        return {"tur": "bayrak", "on_ek": on_ek,
                "kolonlar": sorted(esleme.values()),
                "esleme": esleme, "sayim": sayim}
    return None


def hazir_bolme_bul(df):
    """Tabloda ONCEDEN yazilmis bir bolme var mi? Tanim ya da None.

    ONCE BAYRAK KOLONLARI aranir: adlari acikca bolmeyi soyluyor
    (<onek>_TRAIN), yanilma payi neredeyse yok. Etiket kolonu aramasi
    daha genis oldugu icin sonra geliyor."""
    if df is None or not len(getattr(df, "columns", [])):
        return None
    try:
        bayrak = _hazir_bayrak_kolonlari(df)
    except Exception:
        bayrak = None
    if bayrak:
        return bayrak
    for kol in df.columns:
        try:
            bulunan = _hazir_etiket_kolonu(df, kol)
        except Exception:
            bulunan = None
        if bulunan:
            return bulunan
    return None


def _setler_hazir(durum, df, tanim):
    """Tablodaki hazir bolmeden setler. Kolonlar yalnizca OKUNUR."""
    bos = pd.Series(False, index=df.index)
    maske = {"egitim": bos.copy(), "val": bos.copy(),
             "test": bos.copy(), "oot": bos.copy()}

    if tanim.get("tur") == "bayrak":
        for hedef, ad in (tanim.get("esleme") or {}).items():
            if ad in df.columns:
                maske[hedef] = (pd.to_numeric(df[ad], errors="coerce")
                                .fillna(0).astype(bool))
    else:
        kol = tanim.get("kolon")
        if kol not in df.columns:
            raise AdimHatasi(
                "Veri setindeki hazır bölme kolonu (%s) artık tabloda yok; "
                "\"%s\" adımını yeniden çalıştırın."
                % (kol, ADIM_ADI["bolme"]))
        normal = df[kol].astype(str).str.strip().str.lower()
        for ham, hedef in (tanim.get("esleme") or {}).items():
            maske[hedef] = maske[hedef] | (normal == ham)

    # AYRIKLIK: bir satir birden fazla sete isaretliyse (bayraklar elle
    # doldurulmus olabilir) oncelik test > oot > val > egitim. Sessizce
    # iki sete birakmak sizinti demekti.
    test = maske["test"]
    oot = maske["oot"] & ~test
    val = maske["val"] & ~test & ~oot
    egitim = maske["egitim"] & ~test & ~oot & ~val
    # Hicbir bayragi olmayan satir EGITIME degil, HICBIR SETE gitmez:
    # etiketsiz satiri egitime saymak, kullanicinin dahil etmedigi
    # kayitlari modele sokmak olurdu.
    return {"egitim": egitim, "val": val, "test": test, "oot": oot}


def _setler_etiket(seri, df):
    """Veri setine yazilmis SPLIT kolonundan setler. Kolonun KENDISI
    dogruluk kaynagidir; OOT de oradan okunur, yeniden turetilmez."""
    e = seri.astype(str).str.strip().str.lower()
    test = e == SPLIT_ETIKET["test"]
    val = e == SPLIT_ETIKET["val"]
    oot = e == SPLIT_ETIKET["oot"]
    return _tamamla(df, oot, val, test)


def setler(durum, df):
    """Doner: {"egitim": Series[bool], "val": ..., "test": ..., "oot": ...}

    TEK DOGRULUK KAYNAGI: maskeler() de, CV katlari da, model
    karsilastirmasi da setleri buradan okur. Dordu de ayni indekste,
    AYRIK ve birlesimleri tum satirlar.

    Setler ARTIK yeniden rastgelelestirilmez; bolme_hazirla()'nin durumda ya
    da veri setinde biraktigi KALICI bilgiden uretilir. Boylece farkli
    uzunlukta okunan tablolarda bile ayni satir hep ayni sette kalir."""
    b = durum.get("bolme") or {}
    m = durum.get("meta") or {}
    a = bolme_ayarlari(durum)

    # 0) VERI SETINDE HAZIR DURAN BOLME. En basta: kullanici bunu acikca
    # sectiyse tabloda yazan bolme dogruluk kaynagidir ve platformun
    # ureteceği hicbir maske onun yerine gecmemeli.
    if a["test_tanim"] == "hazir":
        tanim = durum.get("_hazir_bolme")
        if isinstance(tanim, dict):
            return _setler_hazir(durum, df, tanim)
        raise AdimHatasi(
            "Veri setinde hazır bölme kullanılacaktı ama bölme kolonu "
            "bulunamadı; \"%s\" adımını yeniden çalıştırın."
            % ADIM_ADI["bolme"])

    oot = _oot_maske(durum, df, a, [])

    # 1) Zamansal bolme: deterministik.
    #
    # KOSUL `oot_deger`E BAGLI DEGIL. Eskiden bolme adiminin sectigi
    # `oot_deger` aranıyordu; o alan yokken zamansal secim sessizce 2.
    # dala (rastgele kimlik listeleri) dusuyor, ozet "son dönem · OOT"
    # yazarken maske rastgele %20 oluyordu - ekranda bir bolme, veride
    # baska bir bolme. Donem kolonu okunabiliyorsa zamansal dal calisir;
    # hangi donemlerin test oldugunu _zamansal_test_donemleri belirler.
    if a["test_tanim"] == "zamansal" and m.get("donem") in df.columns:
        return _setler_zamansal(durum, df, a, oot)

    # 2) Kalici kimlik listeleri
    kimlik = b.get("kimlik_kolon") or m.get("id")
    listeler = b.get("set_kimlikleri")
    if not isinstance(listeler, dict):
        # Eski oturumda yalnizca test kimlikleri var; val/OOT o oturumda
        # hic ayrilmamisti, bos kalmalari dogru davranis.
        eski = b.get("test_kimlikleri")
        listeler = {"test": eski} if eski is not None else None
    if listeler and kimlik and kimlik in df.columns:
        return _setler_kimlik(df, kimlik, listeler, oot)

    # 3) Veri setine yazilmis kalici SPLIT kolonu
    split_kolon = b.get("split_kolon") or SPLIT_KOLON
    if split_kolon in df.columns:
        return _setler_etiket(df[split_kolon], df)

    # 4) Hicbir kalici kayit yok: bolme adimi calismamis ya da durum
    #    eksik yuklenmis demektir. Burada YENIDEN rastgeleleme YAPMIYORUZ;
    #    sessizce sizdirmaktansa acikca durduruyoruz.
    raise AdimHatasi(
        "Geliştirme/test bölmesi henüz kalıcı hale getirilmemiş. "
        "\"%s\" adımını çalıştırın; sızıntı sınırı olmadan "
        "hesaplama yapmıyorum." % ADIM_ADI["bolme"])


def maskeler(durum, df):
    """(egitim_maske, test_maske) - LEAKAGE SINIRI burada ciziliyor.

    setler()'in ince sarmalayicisi. Cagiranlar (SFA, degisken secimi,
    doldurma sinirlari) boylece val ve OOT satirlarini da GORMEZ:
    "egitim" val ve OOT haric kalan satirlardir."""
    s = setler(durum, df)
    return s["egitim"], s["test"]


def bolme_hazirla(durum, df, yazici=None):
    """Bolmeyi BIR KEZ hesaplar ve SATIR KIMLIGI bazinda KALICI yapar.

    Eski surum maskeyi her cagrida okunan DataFrame'in uzunluguna ve satir
    sirasina gore yeniden uretiyordu; farkli adimlar farkli uzunlukta tablo
    okudugu icin "train medyani" ile doldurulan satir sonra test setine
    dusebiliyor, sizinti siniri fiilen kalkiyordu.

    Uc kalici yol desteklenir; ucu de DORT sete birden calisir:
      1. Zamansal bolme  -> donem kolonundan her defasinda ayni setler cikar
      2. Kimlik kolonu   -> set kimlikleri durum["bolme"]["set_kimlikleri"]
      3. Kimlik yoksa    -> veri setine kalici SPLIT_KOLON yazilir
         (yazici: (df) -> yazilan_dataset_adi ya da None)

    Doner: (egitim_maske, test_maske, notlar)  notlar = kullaniciya mesaj listesi
    """
    b = dict(durum.get("bolme") or {})
    m = durum.get("meta") or {}
    notlar = []

    a = bolme_ayarlari(durum)
    # Cozulen ayarlar durumA YAZILIR. Varsayilan turetimi baglama bakiyor
    # (kimlik/donem kolonu, hedef tipi); baglam sonradan degisirse ayni
    # bolme baska satirlari ayirirdi. Kalici bolmenin ayarlari da kalici.
    for k in ("test_tanim", "tur", "birim", "katmanla", "val_var", "val_oran",
              "test_oran", "cv", "kat", "oot_adet", "oot_tanim", "seed",
              "seed_tur", "tekrar", "gap"):
        b[k] = a[k]
    b.pop("oot_var", None)          # ayri OOT ekseni kaldirildi

    # --- Veri setinde HAZIR duran bolme -----------------------------------
    # Hesaplanacak bir sey yok: bolme zaten tabloda yaziyor. Kalici kayit
    # da gerekmiyor, cunku kaynak kolonun kendisi kalici. KAYNAK TABLOYA
    # HICBIR SEY YAZILMAZ.
    if a["test_tanim"] == "hazir":
        tanim = durum.get("_hazir_bolme")
        if not isinstance(tanim, dict):
            raise AdimHatasi(
                "Veri setinde hazır bölme kullanılacaktı ama bölme kolonu "
                "bulunamadı; \"%s\" adımını yeniden çalıştırın."
                % ADIM_ADI["bolme"])
        b["kalici"] = "hazir"
        b["hazir_kolonlar"] = list(tanim.get("kolonlar") or [])
        for k in ("set_kimlikleri", "test_kimlikleri", "split_kolon",
                  "kimlik_kolon", "test_donemleri"):
            b.pop(k, None)
        durum["bolme"] = b
        s = _setler_hazir(durum, df, tanim)
        disarida = int(len(df)) - int(sum(int(s[ad].sum()) for ad in SET_ADLARI))
        if disarida > 0:
            notlar.append(
                "Veri setindeki bölme kullanıldı (%s). %s satır hiçbir sete "
                "işaretlenmemiş; bu satırlar modellemeye girmiyor."
                % (", ".join(b["hazir_kolonlar"]), _sayi(disarida)))
        else:
            notlar.append("Veri setindeki bölme kullanıldı (%s); kolonlara "
                          "dokunulmadı." % ", ".join(b["hazir_kolonlar"]))
        eg, te = _bitir(durum, s, notlar)
        return eg, te, notlar

    # Ayri OOT seti YOK; maske her zaman bos doner. Zamansal testte hangi
    # donemlerin test oldugu ozet ve panel icin ayrica yazilir.
    oot = _oot_maske(durum, df, a, notlar)
    ds = _donem_metni(durum, df)
    # Kalici liste: TAM tablodan bir kez hesaplanir. setler() bundan sonra
    # hangi uzunlukta tablo okursa okusun ayni donemleri test sayar.
    if a["test_tanim"] == "zamansal" and ds is not None:
        b.pop("test_donemleri", None)          # eskisini kullanma, tazele
        durum["bolme"] = b
        b["test_donemleri"] = _zamansal_test_donemleri(durum, ds, a)
    else:
        b["test_donemleri"] = []
    b.pop("oot_donemleri", None)

    oranlar = [("test", a["test_oran"])]
    if a["val_var"]:
        oranlar.append(("val", a["val_oran"]))

    donem = m.get("donem")
    # setler() ile AYNI kosul: `oot_deger` aranirsa zamansal secim sessizce
    # rastgele bolmeye duser ve iki fonksiyon farkli set uretir.
    if a["test_tanim"] == "zamansal" and donem in df.columns:
        b["kalici"] = "zamansal"
        durum["bolme"] = b
        s = _setler_zamansal(durum, df, a, oot)
        if a["val_var"] and not bool(s["val"].any()):
            notlar.append("Zamansal bölmede doğrulama için ayrılabilecek "
                          "dönem kalmadı; eğitime en az bir dönem bırakıldı.")
        eg, te = _bitir(durum, s, notlar)
        return eg, te, notlar

    # --- Rastgele/katmanli: bir kez hesapla, kalici yaz -------------------
    kimlik = m.get("id") if a["birim"] == "kimlik" else None
    if kimlik and kimlik in df.columns:
        listeler = _kimlik_bazli_bolme(df.loc[~oot], durum, kimlik, oranlar, a)
        toplam = sum(len(v) for v in listeler.values())
        if toplam <= TEST_KIMLIK_LIMITI:
            b["kalici"] = "kimlik"
            b["kimlik_kolon"] = kimlik
            b["set_kimlikleri"] = listeler
            # Eski oturumlari okuyan kod yolu icin ayni liste eski adiyla da
            # duruyor; iki yerde tutulmasi degil, tek yerden turetilmesi.
            b["test_kimlikleri"] = listeler["test"]
            b.pop("split_kolon", None)
            notlar.append("Bölme %s kimliği üzerinden sabitlendi; aynı kimlik "
                          "iki sete birden düşmez." % kimlik)
            durum["bolme"] = b
            s = _setler_kimlik(df, kimlik, listeler, oot)
            eg, te = _bitir(durum, s, notlar)
            return eg, te, notlar
        notlar.append("Set kimliği sayısı %s üzerinde olduğu için kimlik "
                      "listesi yerine veri setine kalıcı %s kolonu yazıldı."
                      % (_sayi(TEST_KIMLIK_LIMITI), SPLIT_KOLON))
    elif a["birim"] == "kimlik":
        notlar.append("Kimlik kolonu veri setinde bulunamadığı için bölme "
                      "satır bazında yapıldı.")
    else:
        notlar.append("Bölme veri setine kalıcı %s kolonu olarak yazıldı."
                      % SPLIT_KOLON)

    # --- Kalici _SPLIT kolonu --------------------------------------------
    secim = _katmanli_bolum_secimi(
        _katman_serisi(df.loc[~oot], durum, a["katmanla"]), oranlar, a["seed"])
    etiket = np.full(len(df), SPLIT_ETIKET["egitim"], dtype=object)
    etiket[np.flatnonzero(oot.to_numpy())] = SPLIT_ETIKET["oot"]
    kalan_konum = np.flatnonzero((~oot).to_numpy())
    for ad, _oran in oranlar:
        etiket[kalan_konum[secim[ad]]] = SPLIT_ETIKET[ad]

    b["kalici"] = "kolon"
    b["split_kolon"] = SPLIT_KOLON
    b.pop("test_kimlikleri", None)
    b.pop("set_kimlikleri", None)

    yazilan = None
    if yazici is not None:
        kopya = df.copy()
        kopya[SPLIT_KOLON] = etiket
        try:
            yazilan = yazici(kopya)
        except Exception as e:
            raise AdimHatasi(
                "Bölmeyi kalıcı hale getiremedim: %s kolonu veri setine "
                "yazılamadı (%s). Sızıntı sınırını garanti edemediğim için "
                "adımı tamamlamıyorum." % (SPLIT_KOLON, str(e)[:140]))
    b["split_dataset"] = yazilan
    if not yazilan:
        raise AdimHatasi(
            "Bölmeyi kalıcı hale getiremedim: kimlik kolonu yok ve %s kolonu "
            "veri setine yazılamadı. Modelleme tanımlarında bir kimlik kolonu "
            "belirtirseniz bölme kimlik üzerinden sabitlenebilir."
            % SPLIT_KOLON)

    # _SPLIT bir degisken degildir; degisken havuzunun disinda kalmali.
    durum["haric_kolonlar"] = sorted(
        set(durum.get("haric_kolonlar") or []) | {SPLIT_KOLON})
    durum["bolme"] = b
    s = _setler_etiket(pd.Series(etiket, index=df.index), df)
    eg, te = _bitir(durum, s, notlar)
    return eg, te, notlar


def _bitir(durum, s, notlar):
    """Set sayimlarini duruma yazar, kucuk setleri bildirir; (egitim, test).

    bolme_hazirla'nin uc yolu da ayni sayimi ve ayni uyariyi uretmeli; tek
    yerde tutulmazsa yollardan biri sessizce eksik kalir."""
    b = durum["bolme"]
    b["satir"] = {ad: int(s[ad].sum()) for ad in SET_ADLARI}
    # train_satir / test_satir KALIYOR: ust serit, senaryo konfigi ve eski
    # oturum dosyalari bu iki adi okuyor.
    b["train_satir"] = b["satir"]["egitim"]
    b["test_satir"] = b["satir"]["test"]
    for ad in SET_ADLARI:
        n = b["satir"][ad]
        if 0 < n < MIN_SET_SATIR:
            notlar.append("%s seti yalnızca %s satır; %s satırın altındaki "
                          "sette ölçüm güvenilir değil."
                          % (SET_BASLIK[ad], _sayi(n), _sayi(MIN_SET_SATIR)))
    return s["egitim"], s["test"]


# ===========================================================================
# CV KATLARI
# ===========================================================================
def _kfold_katlari(idx, y, gruplar, a, notlar):
    """kfold katlari. Doner: [(egitim_idx, dogrulama_idx), ...] ya da [].

    Gruplu kat GEREKIYORSA ve kurulamiyorsa BOS doner: gruplamayi atlamak
    ayni musteriyi hem kat-egitiminde hem kat-dogrulamasinda birakir ve
    AUC'yi sessizce sisirir. Sessizce gruplamasiz devam EDILMEZ."""
    from sklearn.model_selection import GroupKFold, KFold, StratifiedKFold

    kat = a["kat"]
    katmanli = bool(a["katmanla"]) and y is not None and int(y.nunique()) == 2

    if gruplar is not None:
        benzersiz = int(pd.Series(gruplar).nunique())
        if benzersiz < 2:
            notlar.append("Kimlik bazlı çapraz doğrulama için yeterli farklı kimlik yok "
                          "(%s); çapraz doğrulama kapatıldı." % _sayi(benzersiz))
            return []
        if benzersiz < kat:
            notlar.append("Farklı kimlik sayısı (%s) kat sayısından az; "
                          "kat sayısı %s'e düşürüldü."
                          % (_sayi(benzersiz), _sayi(benzersiz)))
            kat = benzersiz
        if katmanli:
            try:
                from sklearn.model_selection import StratifiedGroupKFold
                bolucu = StratifiedGroupKFold(
                    n_splits=kat, shuffle=True, random_state=a["seed"])
                return [(idx[tr], idx[dg]) for tr, dg
                        in bolucu.split(np.zeros(len(idx)), y, gruplar)]
            except Exception:
                # Katmanlama gruplamadan VAZGECMEK icin gerekce degil:
                # gruplamasiz katmanli kat sizdirir, katmansiz gruplu kat
                # sizdirmaz. Katmanlamadan vazgecip gruplamayi koruyoruz.
                notlar.append("Katmanlı gruplu kat kurulamadı; kat sayısı "
                              "korunarak yalnızca gruplama uygulandı "
                              "(hedef oranı katlar arasında dalgalanabilir).")
        try:
            bolucu = GroupKFold(n_splits=kat)
            return [(idx[tr], idx[dg]) for tr, dg
                    in bolucu.split(np.zeros(len(idx)), y, gruplar)]
        except Exception as e:
            notlar.append("Kimlik bazlı çapraz doğrulama kurulamadı (%s); ÇAPRAZ "
                          "DOĞRULAMA KAPATILDI. "
                          "Gruplamayı atlayıp devam etmek aynı kimliği hem "
                          "parça eğitiminde hem doğrulamasında bırakır ve "
                          "başarımı olduğundan yüksek gösterir."
                          % str(e)[:80])
            return []

    if katmanli:
        en_kucuk = int(y.value_counts().min())
        if en_kucuk < kat:
            notlar.append("Az görülen sınıftan yalnızca %s satır var; "
                          "kat sayısı %s'e düşürüldü."
                          % (_sayi(en_kucuk), _sayi(max(en_kucuk, 2))))
            kat = max(en_kucuk, 2)
        bolucu = StratifiedKFold(n_splits=kat, shuffle=True,
                                 random_state=a["seed"])
        return [(idx[tr], idx[dg]) for tr, dg
                in bolucu.split(np.zeros(len(idx)), y)]

    bolucu = KFold(n_splits=kat, shuffle=True, random_state=a["seed"])
    return [(idx[tr], idx[dg]) for tr, dg in bolucu.split(np.zeros(len(idx)))]


def _zaman_katlari(ds, idx, a, notlar):
    """Walk-forward: her kat onceki donemlerde egitilir, SONRAKI donemde
    dogrulanir. Gelecegi gorup gecmisi tahmin etmek modelin gercek kullanim
    kosulu degildir."""
    donemler = sorted(pd.unique(ds.dropna()).tolist())
    if len(donemler) < 2:
        notlar.append("Zaman sıralı çapraz doğrulama için en az iki dönem gerekiyor; "
                      "eğitim setinde %s dönem var. Çapraz doğrulama kapatıldı."
                      % _sayi(len(donemler)))
        return []

    kat = a["kat"]
    if len(donemler) < kat + 1:
        kat = len(donemler) - 1
        notlar.append("Eğitim setinde %s dönem var; %s parçalı zaman sıralı çapraz "
                      "doğrulama "
                      "kurulamadığı için parça sayısı %s'e düşürüldü."
                      % (_sayi(len(donemler)), _sayi(a["kat"]), _sayi(kat)))

    katlar_ = []
    for i in range(len(donemler) - kat, len(donemler)):
        egitim_d = set(donemler[:i])
        dogrulama_d = {donemler[i]}
        tr = idx[ds.isin(egitim_d).to_numpy()]
        dg = idx[ds.isin(dogrulama_d).to_numpy()]
        if len(tr) and len(dg):
            katlar_.append((tr, dg))
    return katlar_


def katlar(durum, df, y=None):
    """CV katlarini uretir. Doner: (katlar, notlar)

    katlar: [(egitim_idx, dogrulama_idx), ...] - df.index degerleri.
    YALNIZCA `egitim` satirlari uzerinde calisir; val, test ve OOT hicbir
    katta gorunmez.

    Bos liste = CV YOK. Nedeni notlar'da yazar ve durum["bolme"]["cv_etkin"]
    False'a cekilir. `birim="kimlik"` iken gruplu kat kurulamazsa CV
    KAPATILIR; sessizce gruplamasiz devam EDILMEZ, cunku gruplamasiz kat
    ayni musteriyi iki tarafta birden birakip AUC'yi sisirir.

    Kullanicinin sectigi `cv` degeri DEGISTIRILMEZ; form ne sectiyse onu
    gostermeye devam eder, yaninda neden calismadigi yazar."""
    a = bolme_ayarlari(durum)
    b = dict(durum.get("bolme") or {})
    notlar = []

    def _kapat(neden):
        if neden:
            notlar.append(neden)
        b["cv_etkin"] = False
        b["cv_notlari"] = list(notlar)
        durum["bolme"] = b
        return [], notlar

    if a["cv"] == "yok":
        return _kapat(None)

    s = setler(durum, df)
    eg = s["egitim"]
    idx = df.index[eg.to_numpy()]
    if len(idx) < MIN_SET_SATIR:
        return _kapat("Eğitim setinde %s satır var; çapraz doğrulama için yetersiz."
                      % _sayi(len(idx)))

    hedef = (durum.get("meta") or {}).get("target")
    if y is None and hedef and hedef in df.columns:
        y = pd.to_numeric(df[hedef], errors="coerce")
    if y is not None:
        y = pd.Series(y, index=df.index).loc[idx]
        # Hedefi NaN satir katmanlamayi da metrigi de bozar; kat disinda kalir.
        gecerli = y.notna().to_numpy()
        if not gecerli.all():
            idx = idx[gecerli]
            y = y[gecerli]
        if len(idx) < MIN_SET_SATIR:
            return _kapat("Hedefi dolu eğitim satırı sayısı çapraz doğrulama için yetersiz "
                          "(%s)." % _sayi(len(idx)))
        y = (y > 0).astype(int) if int(y.nunique()) <= 2 else y
        if int(y.nunique()) < 2:
            return _kapat("Eğitim setinde hedefin tek sınıfı kaldı; çapraz "
                          "doğrulama kurulamadı.")

    if a["cv"] == "zaman":
        ds = _donem_metni(durum, df)
        if ds is None:
            return _kapat("Zaman sıralı çapraz doğrulama istendi ama dönem "
                          "kolonu tanımlı değil; çapraz doğrulama kapatıldı.")
        sonuc = _zaman_katlari(ds.loc[idx], idx, a, notlar)
        if not sonuc:
            return _kapat(None)
        b["cv_etkin"] = True
        b["cv_notlari"] = list(notlar)
        durum["bolme"] = b
        return sonuc, notlar

    gruplar = None
    if a["birim"] == "kimlik":
        kimlik = b.get("kimlik_kolon") or (durum.get("meta") or {}).get("id")
        if not (kimlik and kimlik in df.columns):
            return _kapat(
                "Bölme kimlik bazlı olduğu halde kimlik kolonu bu tabloda "
                "yok; kimlik bazlı parça üretilemedi ve ÇAPRAZ DOĞRULAMA "
                "KAPATILDI. Gruplamasız "
                "devam etmek aynı kimliği hem kat eğitiminde hem "
                "doğrulamasında bırakır ve başarımı şişirir.")
        gruplar = df[kimlik].astype(str).loc[idx].to_numpy()

    # TEKRARLI CAPRAZ DOGRULAMA: ayni kat sayisiyla FARKLI seed'lerle
    # birkaç tur. Tek bir bolmenin sansina bagli kalmadan olcumun
    # dayanikliligi gorulur (kullanici istegi: "sadece Seed = 42 yeterli
    # değil ... çoklu tekrar").
    tekrar = int(a.get("tekrar") or 1)
    sonuc = []
    try:
        for tur in range(max(tekrar, 1)):
            # Her turun seed'i ana seed'den TURETILIYOR: kullanici tek
            # sayi veriyor, butun calisma yine tekrar uretilebilir
            # kaliyor.
            tur_a = dict(a)
            tur_a["seed"] = int(a["seed"]) + tur
            parca = _kfold_katlari(idx, y, gruplar, tur_a,
                                   notlar if tur == 0 else [])
            if not parca:
                sonuc = parca if tur == 0 else sonuc
                break
            sonuc.extend(parca)
    except Exception as e:
        return _kapat("Çapraz doğrulama parçaları üretilemedi (%s); çapraz "
                      "doğrulama kapatıldı."
                      % str(e)[:100])
    if not sonuc:
        return _kapat(None)
    if tekrar > 1:
        notlar.append("Çapraz doğrulama %s farklı bölmeyle tekrarlandı; "
                      "toplam %s kat üretildi."
                      % (_sayi(tekrar), _sayi(len(sonuc))))

    b["cv_etkin"] = True
    b["cv_notlari"] = list(notlar)
    durum["bolme"] = b
    return sonuc, notlar


# Formdan gelebilecek alanlar. Beyaz liste: gelen govde durum["bolme"]'ye
# oldugu gibi yazilsaydi istemci "kalici" ya da "test_kimlikleri" gonderip
# hic hesaplanmamis bir bolmeyi hesaplanmis gibi gosterebilirdi.
BOLME_FORM_ALANLARI = ("test_tanim", "birim", "katmanla", "val_var",
                       "val_oran", "test_oran", "cv", "kat", "oot_adet",
                       "oot_tanim", "seed", "seed_tur", "tekrar", "gap",
                       "oot_deger", "train_kullanimi")

# Bolme degistiginde kalici kayit GECERSIZDIR; yeniden hesaplanana kadar
# eski setler dolasimda kalmamali.
BOLME_KALICI_ALANLARI = ("kalici", "set_kimlikleri", "test_kimlikleri",
                         "split_kolon", "split_dataset", "kimlik_kolon",
                         "hazir_kolonlar",
                         "satir", "train_satir", "test_satir",
                         "oot_donemleri", "cv_etkin", "cv_notlari")


def bolme_kaydet(durum, gelen):
    """Formdan gelen bolme ayarlarini duruma yazar.

    Doner: {"tamam": bool, "bolme": {...}, "ozet": "...", "uyarilar": [...]}
    ya da {"tamam": False, "hata": "..."}

    Ayar degisince kalici kayit SILINIR: eski kimlik listesi/SPLIT kolonu
    yeni ayarlarin uretecegi setleri tarif etmiyor. Kullanici "Bölme
    Stratejisi" adimini yeniden calistirana kadar setler() acikca durur -
    yeni ayarlarla eski setleri kullanmaktansa hesaplamayi durdurmak dogru.
    """
    if not isinstance(gelen, dict):
        return {"tamam": False, "hata": "Bölme ayarları beklenen biçimde "
                                        "gelmedi."}
    b = dict(durum.get("bolme") or {})
    gelen = dict(gelen)

    # SECIM LISTESI DEGERLERI. On yuz artik ham sayi degil, listeden
    # secilmis bir ANAHTAR gonderiyor ("son:2", "0.20", "5"). Burada
    # tek yerde cozuluyor; asagisi degismedi ve eski istemcinin
    # gonderdigi ham sayilar da aynen calismaya devam ediyor.
    if isinstance(gelen.get("oot_adet"), str) and gelen["oot_adet"]:
        cozum = test_donem_coz(gelen["oot_adet"], durum)
        if cozum is None:
            return {"tamam": False,
                    "hata": "Seçilen test dönemi tanınmadı: %s"
                            % gelen["oot_adet"]}
        gelen["oot_tanim"] = cozum
        gelen["oot_adet"] = cozum["adet"]
    for oran_alani in ("test_oran", "val_oran"):
        if isinstance(gelen.get(oran_alani), str):
            gelen[oran_alani] = _orana_yuvarla(gelen[oran_alani])
    if "kat" in gelen:
        gelen["kat"] = min(_tam_sayi(gelen["kat"], 5, KAT_EN_AZ), KAT_EN_COK)
    if "tekrar" in gelen:
        gelen["tekrar"] = min(_tam_sayi(gelen["tekrar"], 1, 1), TEKRAR_EN_COK)
    if "gap" in gelen:
        gelen["gap"] = min(_tam_sayi(gelen["gap"], 0, 0), GAP_EN_COK)
    # ONAY KUTUSU YERINE IKI SECENEKLI LISTE: on yuz artik "kullan" /
    # "koru" gibi anahtarlar gonderiyor. Eski istemcinin bool'u da
    # calismaya devam ediyor.
    if isinstance(gelen.get("val_var"), str):
        gelen["val_var"] = gelen["val_var"] == "kullan"
    if isinstance(gelen.get("katmanla"), str):
        gelen["katmanla"] = gelen["katmanla"] == "koru"

    for k in BOLME_FORM_ALANLARI:
        if k in gelen:
            b[k] = gelen[k]

    # train_kullanimi kullanicinin gordugu TEK alan; val_var ve cv onun
    # turevi. Ikisi ayni govdede gelirse ACIK olan (val_var/cv) kazanir:
    # panelde ince ayar yapan kullanici hazir secenegi bilerek bozuyordur.
    kul = gelen.get("train_kullanimi")
    if kul in TRAIN_KULLANIMI:
        esleme = TRAIN_KULLANIMI[kul]
        if "val_var" not in gelen:
            b["val_var"] = esleme["val_var"]
        if "cv" not in gelen:
            b["cv"] = esleme["cv"]
    b.pop("train_kullanimi", None)      # turetilir, saklanmaz
    durum["bolme"] = b

    try:
        a = bolme_ayarlari(durum)
    except Exception as e:
        durum["bolme"] = dict(durum.get("bolme") or {})
        return {"tamam": False,
                "hata": "Bölme ayarları okunamadı: %s" % str(e)[:140]}

    # Cozulen degerler yaziliyor: kullanici "kimlik" sectiyse ama kimlik
    # kolonu yoksa formda da uygulamada da "satir" gorunmeli.
    for k in ("test_tanim", "tur", "birim", "katmanla", "val_var", "val_oran",
              "test_oran", "cv", "kat", "oot_adet", "oot_tanim", "seed",
              "seed_tur", "tekrar", "gap"):
        b[k] = a[k]
    b.pop("oot_var", None)
    for k in BOLME_KALICI_ALANLARI:
        b.pop(k, None)
    durum["bolme"] = b

    return {"tamam": True, "bolme": b, "ozet": bolme_ozeti(durum),
            "uyarilar": bolme_uyarilari(durum)}


# Veri bu satir sayisinin uzerindeyse capraz dogrulama yerine tek bir
# dogrulama seti oneriliyor: parca sayisi kadar egitim, buyuk tabloda
# adim suresini katlar ve ayri bir dogrulama seti zaten yeterince buyuk
# olur. Altindaki tablolarda capraz dogrulama daha guvenilir cunku tek
# bir dogrulama parcasi cok kucuk kalir.
ONERI_CAPRAZ_SINIRI = 200000

# Zamansal test icin gereken EN AZ donem sayisi: biri teste gidecek,
# geriye egitim icin en az biri kalmali.
ONERI_EN_AZ_DONEM = 2


# ===========================================================================
# SECIM LISTELERI
# ---------------------------------------------------------------------------
# Kullanici istegi: "test dönem sayısı 1 falan diyor çok saçma duruyor;
# benim isteğim daha çok önerilen ayarlar gibi olup kendim seçim
# yapabilmemdi, nasıl veri sözlük seçiyorsam öyle bir selection
# metoduyla, ve yapabileceklerim bazında seçebilmeliyim; başka seçenek
# yoksa fix halde durmalı o selection kısmı."
#
# Ham sayi kutusu ("1") kullaniciya NE anlama geldigini soylemiyordu.
# Yerine SOMUT secenekler geliyor: "Son dönem (202412)". Secenekler
# verinin kendisinden uretiliyor, yani yalnizca YAPILABILIR olanlar
# listede. Tek secenek kaliyorsa acilir liste degil SABIT metin
# gosteriliyor - tiklayinca tek satir cikan bir liste, secim varmis
# izlenimi verir.
# ===========================================================================

def _secenek(anahtar, etiket, aciklama=""):
    return {"anahtar": str(anahtar), "etiket": etiket, "aciklama": aciklama}


def test_donem_secenekleri(durum):
    """Zamansal testte secilebilecek SOMUT donem kumeleri.

    "Son N dönem" secenekleri: N en fazla (donem sayisi - 1) olabilir,
    egitime en az bir donem kalmali. Ustune tek tek donemler eklenmiyor;
    tek bir ortadaki donemi test yapmak zamansal bolmenin amacina
    (gelecegi tahmin) aykiri ve kullanicinin sordugu sey degil."""
    donemler = [str(x) for x in (durum.get("_donemler") or [])]
    if len(donemler) < 2:
        return []
    secenekler = []
    for n in range(1, len(donemler)):
        secilen = donemler[-n:]
        if n == 1:
            etiket = "Son dönem (%s)" % secilen[0]
        elif n <= 3:
            etiket = "Son %d dönem (%s)" % (n, ", ".join(secilen))
        else:
            etiket = "Son %d dönem (%s … %s)" % (n, secilen[0], secilen[-1])
        kalan = len(donemler) - n
        secenekler.append(_secenek(
            "son:%d" % n, etiket,
            "Eğitime %s dönem kalır." % _sayi(kalan)))
    return secenekler


def test_donem_anahtari(a):
    """Cozulmus ayarlardan secim listesinin anahtari."""
    t = a.get("oot_tanim") or {}
    if t.get("tur") == "secili" and t.get("deger") not in (None, ""):
        return "donem:%s" % t["deger"]
    return "son:%d" % int(t.get("adet") or 1)


def test_donem_coz(anahtar, durum):
    """Secim anahtarindan oot_tanim sozlugu. Taninmazsa None."""
    ham = str(anahtar or "").strip()
    donemler = [str(x) for x in (durum.get("_donemler") or [])]
    if ham.startswith("son:"):
        try:
            n = int(ham[4:])
        except ValueError:
            return None
        en_fazla = max(len(donemler) - 1, 1)
        n = max(1, min(n, en_fazla))
        return {"tur": "son_donem", "deger": None, "adet": n}
    if ham.startswith("donem:"):
        deger = ham[6:]
        if donemler and deger not in donemler:
            return None
        return {"tur": "secili", "deger": deger, "adet": 1}
    return None


# Test / deneme payi icin hazir oranlar. Serbest sayi kutusu yerine
# somut secenekler: %17,5 gibi bir oran hicbir calismada anlamli bir
# fark yaratmiyor, ama yanlis yazilmis "0,9" egitim setini bosaltiyordu.
ORAN_SECENEKLERI = (0.10, 0.15, 0.20, 0.25, 0.30)
KAT_SECENEKLERI = (3, 5, 10)
# Parca sayisinin MATEMATIKSEL siniri: 2'den az parca capraz dogrulama
# degil, 20'den fazlasi her katta avuc ici kadar veri birakir.
KAT_EN_AZ = 2
KAT_EN_COK = 20
# Tekrarli capraz dogrulamada en fazla kac tur. Ustu egitim suresini
# carpanla buyutuyor ve olcumu daha dogru yapmiyor.
TEKRAR_EN_COK = 20
# Zamansal bolmede atlanacak en fazla donem.
GAP_EN_COK = 12


# Not: oran_secenekleri() / kat_secenekleri() KALDIRILDI. Oran ve parca
# sayisi artik hazir bir listeden secilmiyor, serbest yaziliyor
# (kullanici karari). Aralik asagidaki sabitlerde.


# Oranin kabul edildigi ARALIK. Hazir listeye (%10/%15/%20/%25/%30)
# sikistirmaktan vazgecildi (kullanici karari: "bu sampling sayısını
# 1-99 arası verebilme özgürlüğüm olmalı ... zorunlu olmadıkça
# özgürlüğümü kısıtlama"). Sinir yalnizca MATEMATIKSEL olan: %0 hic
# sinav birakmaz, %100 hic egitim birakmaz.
ORAN_EN_AZ = 0.01
ORAN_EN_COK = 0.99


def _orana_yuvarla(deger, yedek=0.20):
    """Gelen orani kabul edilen araliga kirpar.

    Listeye OTURTMAZ: kullanici %23 yazdiysa %25'e cekmek, ekranda
    yazdigindan baska bir bolme uygulamak demekti. Yalnizca aralik
    disina tasan ve okunamayan degerler duzeltiliyor."""
    try:
        x = float(deger)
    except (TypeError, ValueError):
        return yedek
    # Yuzde olarak gelmis olabilir ("20" -> 0.20). 1'den buyuk her deger
    # yuzde sayilir; 1.0 zaten gecersiz (egitime satir kalmaz).
    if x > 1.0:
        x = x / 100.0
    return max(ORAN_EN_AZ, min(ORAN_EN_COK, round(x, 4)))


# ===========================================================================
# BOLME SATIRLARI - iki kartin ORTAK iskeleti
# ---------------------------------------------------------------------------
# Kullanici istegi: "seçim kısmı özel ayarlar ve önerilen ayarlar kısmında
# buna benzemeli ama yapı olarak benzemeli".
#
# Iki kart YAN YANA duruyor ve IKISI DE AYNI SATIRLARI tasiyor:
#   sol  (Önerilen) -> satirin DEGERI, salt okunur
#   sag  (Özel)     -> ayni satirin KONTROLU, secilebilir
# Satirlar tek listeden uretildigi icin iki kart HER ZAMAN hizali kalir.
# Ayri ayri yazilsalardi biri degistiginde digeri sessizce kayardi.
#
# "alanlar": o satirin hangi form alanlarindan olustugu. Bir satir birden
# fazla kontrol tasiyabilir (dönüşümlü deneme = yöntem + parça sayısı).
# ---------------------------------------------------------------------------
# BOLME KARTININ ICERIGI
# ---------------------------------------------------------------------------
# Ana ekranda kullanici UC SEYI anlamali: ne seçiyorum -> sistem ne
# öneriyor -> ben ne seçtim. Geri kalan her sey ikinci katmanda
# (kullanici karari).
#
# Bu yuzden:
#   1. Her satirin yaninda "?" -> EN FAZLA IKI SATIRLIK ipucu
#   2. En altta "Detaylar ve Terimler" -> kapsamli anlatim, varsayilan
#      KAPALI
#   3. KOSULLU GORUNURLUK: karsiligi olmayan satir hic cizilmez. Yoksa
#      ekran "20 inputlu form" gibi duruyordu - "Doğrulama Büyüklüğü"
#      dogrulama seti kapaliyken, "OOT / Test Dönemi" rastgele bolmede
#      ekranda duruyor ve ikisi de hicbir seyi degistirmiyordu.
BOLME_BOLUMLERI = (
    {"anahtar": "oot", "baslik": "OOT / Test"},
    {"anahtar": "dogrulama", "baslik": "Doğrulama"},
    {"anahtar": "kural", "baslik": "Bölme Kuralları"},
    {"anahtar": "tekrar", "baslik": "Tekrarlanabilirlik"},
)

# Her satir: anahtar, etiket, bolum, alanlar, (varsa) kosul / salt.
#
# KOSUL: satirin GORUNME kosulu. Karsiligi olmayan satir hic cizilmez -
# "her seyi destekleyip basit gorunmenin" yolu bu (kullanici karari).
# On yuz taslaktan aninda hesapliyor, sunucuya gidip gelmeden.
BOLME_SATIRLARI = (
    {"anahtar": "test_tanim", "etiket": "Ayrım yöntemi",
     "bolum": "oot", "alanlar": ("test_tanim",)},
    {"anahtar": "donem_kolon", "etiket": "Dönem kolonu",
     "bolum": "oot", "alanlar": (), "salt": "donem_kolon",
     "kosul": {"alan": "test_tanim", "degerler": ("zamansal",)}},
    {"anahtar": "test_donem", "etiket": "OOT / Test dönemi",
     "bolum": "oot", "alanlar": ("oot_adet",),
     "kosul": {"alan": "test_tanim", "degerler": ("zamansal",)}},
    {"anahtar": "gap", "etiket": "Ara dönem (gap)",
     "bolum": "oot", "alanlar": ("gap",),
     "kosul": {"alan": "test_tanim", "degerler": ("zamansal",)}},
    {"anahtar": "test_boyut", "etiket": "OOT / Test büyüklüğü",
     "bolum": "oot", "alanlar": ("test_oran",),
     "kosul": {"alan": "test_tanim", "degerler": ("rastgele",)}},

    {"anahtar": "val_var", "etiket": "Doğrulama seti",
     "bolum": "dogrulama", "alanlar": ("val_var",)},
    {"anahtar": "val_oran", "etiket": "Doğrulama büyüklüğü",
     "bolum": "dogrulama", "alanlar": ("val_oran",),
     "kosul": {"alan": "val_var", "degerler": (True,)}},
    {"anahtar": "cv", "etiket": "Çapraz doğrulama",
     "bolum": "dogrulama", "alanlar": ("cv",)},
    {"anahtar": "kat", "etiket": "Kat sayısı",
     "bolum": "dogrulama", "alanlar": ("kat",),
     "kosul": {"alan": "cv", "degerler": ("kfold", "zaman")}},

    {"anahtar": "birim", "etiket": "Bölme birimi",
     "bolum": "kural", "alanlar": ("birim",)},
    {"anahtar": "bolme_kolon", "etiket": "Bölme kolonu",
     "bolum": "kural", "alanlar": (), "salt": "bolme_kolon",
     "kosul": {"alan": "birim", "degerler": ("kimlik",)}},
    {"anahtar": "katmanla", "etiket": "Hedef dağılımı",
     "bolum": "kural", "alanlar": ("katmanla",)},

    {"anahtar": "seed_tur", "etiket": "Bölme yaklaşımı",
     "bolum": "tekrar", "alanlar": ("seed_tur",)},
    {"anahtar": "seed", "etiket": "Seed",
     "bolum": "tekrar", "alanlar": ("seed",),
     "kosul": {"alan": "seed_tur", "degerler": ("sabit",)}},
    {"anahtar": "tekrar", "etiket": "Tekrar sayısı",
     "bolum": "tekrar", "alanlar": ("tekrar",),
     "kosul": {"alan": "seed_tur", "degerler": ("coklu",)}},
)

# "Detaylar ve Terimler" - TEK yerde, panelin altinda, varsayilan
# KAPALI. Satir basina "?" simgesi YOK (kullanici karari: "her satira ?
# koyunca goruntu yardim dokumanina donuyor"). Sorular kullanicinin
# soracagi bicimde yazili.
BOLME_SOZLUK = (
    ("OOT / Test seti nedir?",
     "Modelin geliştirme sırasında hiç görmediği ve nihai performansının "
     "ölçüldüğü veri kümesidir. Bu platformda zamansal bölmede test seti "
     "zaten zaman dışıdır; ayrı bir OOT seti açılmaz."),
    ("Doğrulama seti nedir?",
     "Model seçimi, hiperparametre optimizasyonu veya erken durdurma gibi "
     "işlemler için eğitim verisinden ayrılan bölümdür."),
    ("Çapraz doğrulama nedir?",
     "Eğitim verisinin birden fazla parçaya ayrılarak farklı "
     "eğitim/doğrulama kombinasyonlarıyla değerlendirilmesidir."),
    ("Kat sayısı neyi değiştirir?",
     "Çapraz doğrulamada verinin kaç parçaya ayrılacağını belirler. Kat "
     "arttıkça ölçüm daha kararlı olur ama eğitim süresi de o oranda "
     "uzar."),
    ("Kimlik bazlı bölme neden kullanılır?",
     "Aynı müşteriye ait tüm kayıtların aynı veri setinde tutulmasını "
     "sağlar ve müşteri bazlı veri sızıntısını önler."),
    ("Hedef dağılımını korumak ne demektir?",
     "Hedef sınıf oranlarının bölünen setler arasında benzer tutulmasıdır. "
     "Temerrüt gibi seyrek durumlarda test setinin boş kalmasını önler; "
     "sektörde katmanlı örnekleme olarak geçer."),
    ("Seed nedir?",
     "Rastgele işlemlerin aynı şekilde tekrar üretilebilmesini sağlayan "
     "sayıdır. Aynı seed ile her çalıştırmada tam olarak aynı bölme "
     "elde edilir."),
    ("Çoklu tekrar ne zaman kullanılır?",
     "Ölçümün tek bir bölmenin şansına bağlı kalmasından şüphe "
     "edildiğinde. Çapraz doğrulama farklı seed'lerle birkaç kez "
     "tekrarlanır ve sonuçların dayanıklılığı görülür."),
    ("Zamansal bölme ne zaman tercih edilir?",
     "Modelin zaman içindeki performans değişimini ölçmek gerektiğinde. "
     "Daha eski dönemler geliştirme, daha yeni dönemler OOT / Test için "
     "kullanılır."),
    ("Ara dönem (gap) ne işe yarar?",
     "Eğitim ile OOT / Test dönemleri arasında bırakılan, hiçbir sete "
     "girmeyen boşluktur. Performans penceresi nedeniyle iki tarafın "
     "aynı gözlemi paylaşmasını engeller."),
)


def bolme_satir_degeri(anahtar, a, durum=None):
    """Bir satirin OKUNABILIR degeri. Hem önerilen kartta hem HAZIRLIK
    ozetinde ayni cumle cikiyor: iki yerde ayri yazilirsa biri eskir."""
    m = (durum or {}).get("meta") or {}
    donemler = [str(x) for x in ((durum or {}).get("_donemler") or [])]

    if anahtar == "test_tanim":
        return bolme_etiket("test_tanim", a["test_tanim"])

    if anahtar == "donem_kolon":
        return m.get("donem") or "-"

    if anahtar == "test_donem":
        if a["test_tanim"] == "hazir":
            return "Veri setinde yazılı"
        adet = int((a.get("oot_tanim") or {}).get("adet") or 1)
        if donemler:
            secilen = donemler[-adet:]
            return ("Son dönem (%s)" % secilen[0]) if adet == 1 \
                else "Son %d dönem (%s … %s)" % (adet, secilen[0],
                                                 secilen[-1])
        return "Son %d dönem" % adet

    if anahtar == "gap":
        n = int(a.get("gap") or 0)
        return "Yok" if n <= 0 else "%d dönem" % n

    if anahtar == "test_boyut":
        if a["test_tanim"] == "hazir":
            return "Veri setinde yazılı"
        return "%%%d" % round(100 * float(a.get("test_oran") or 0))

    if anahtar == "train_kullanimi":
        return bolme_etiket("train_kullanimi", a["train_kullanimi"])

    if anahtar == "val_var":
        return "Kullanılıyor" if a.get("val_var") else "Kullanılmıyor"

    if anahtar == "val_oran":
        if not a.get("val_var"):
            return "-"
        return "%%%d" % round(100 * float(a.get("val_oran") or 0))

    if anahtar == "cv":
        return bolme_etiket("cv", a.get("cv"))

    if anahtar == "kat":
        if a.get("cv") == "yok":
            return "-"
        return "%d" % int(a.get("kat") or 5)

    if anahtar == "tekrar":
        return "%d" % int(a.get("tekrar") or 1)

    if anahtar == "birim":
        return "Kimlik" if a.get("birim") == "kimlik" else "Satır"

    if anahtar == "bolme_kolon":
        return m.get("id") or "-"

    if anahtar == "katmanla":
        return "Korunuyor" if a.get("katmanla") else "Korunmuyor"

    if anahtar == "seed_tur":
        return bolme_etiket("seed_tur", a.get("seed_tur"))

    if anahtar == "seed":
        return str(a.get("seed", 42))

    return "-"


def bolme_kisitlari(durum):
    """Veriden dogan ve SECIMI SINIRLAYAN kosullar.

    Doner: [{"alan", "secenek", "metin"}] - hangi alanin hangi secenegi
    neden kapali. On yuz bu listeyle secenegi pasif cizip SEBEBINI
    yanina yaziyor: sebepsiz pasif bir dugme kullaniciya "bozuk" hissi
    veriyordu (kullanici geri bildirimi).

    Uyarilardan (bkz. bolme_uyarilari) FARKI: uyari yapilan bir secimin
    sonucunu anlatir, kisit ise yapilamayacak bir secimi anlatir."""
    m = durum.get("meta") or {}
    p = durum.get("profil") or {}
    donemler = list(durum.get("_donemler") or [])
    kisitlar = []

    if not m.get("donem"):
        kisitlar.append({
            "alan": "test_tanim", "secenek": "zamansal",
            "metin": "Dönem kolonu tanımlı olmadığı için zamansal bölme "
                     "kurulamıyor; test rastgele ayrılacak."})
    elif donemler and len(donemler) < ONERI_EN_AZ_DONEM:
        kisitlar.append({
            "alan": "test_tanim", "secenek": "zamansal",
            "metin": "Dönem kolonunda tek değer var; zamansal bölme "
                     "kurulamıyor, test rastgele ayrılacak."})

    if not m.get("donem"):
        kisitlar.append({
            "alan": "cv", "secenek": "zaman",
            "metin": "Zaman sıralı çapraz doğrulama dönem kolonu gerektirir."})

    if not m.get("id"):
        kisitlar.append({
            "alan": "birim", "secenek": "kimlik",
            "metin": "Kimlik kolonu tanımlı olmadığı için bölme yalnızca "
                     "satır bazında yapılabilir."})

    if m.get("target") and p.get("hedef_tip") == "surekli":
        kisitlar.append({
            "alan": "katmanla", "secenek": None,
            "metin": "Hedef sürekli bir değişken; hedefe göre katmanlama "
                     "her farklı değeri ayrı bir katman yapar ve test "
                     "setini boşaltır. Katmanlama kapalı öneriliyor."})
    return kisitlar


def bolme_onerisi(durum):
    """Verinin kendisinden cikan ONERILEN bolme + gerekce + ozet satirlari.

    durum["bolme"]'YE BAKMAZ. Oneri, kullanicinin onceki duzenlemesinin
    yankisi olmamali: "Özel Ayarlar"da bir seyi bozan kullanici oneriye
    geri dondugunde ayni oneriyi gormeli, kendi bozdugu ayari degil.

    Doner: {"ayarlar": {...}, "satirlar": [...], "gerekce": "...",
            "kisitlar": [...]}
    "ayarlar" dogrudan bolme_kaydet()'e verilebilir bicimdedir."""
    m = durum.get("meta") or {}
    p = durum.get("profil") or {}
    donemler = [str(x) for x in (durum.get("_donemler") or [])]
    satir = int(p.get("satir") or 0)
    kisitlar = bolme_kisitlari(durum)
    hazir = durum.get("_hazir_bolme") if isinstance(
        durum.get("_hazir_bolme"), dict) else None

    zamansal = bool(m.get("donem")) and len(donemler) >= ONERI_EN_AZ_DONEM
    kimlik = bool(m.get("id"))
    katmanla = bool(m.get("target")) and p.get("hedef_tip") != "surekli"
    buyuk = satir >= ONERI_CAPRAZ_SINIRI
    kullanim = "val" if buyuk else "full_cv"

    # HAZIR BOLME VARSA ONERI ODUR. Tabloda zaten bir bolme duruyorsa
    # platformun ikinci ve farkli bir bolme uretmesi, daha once uretilmis
    # skorlarla karsilastirmayi imkansiz kilar.
    if hazir:
        tur = "hazir"
    elif zamansal:
        tur = "zamansal"
    else:
        tur = "rastgele"

    ayarlar = {
        "test_tanim": tur,
        "oot_adet": 1,
        "test_oran": 0.20,
        "train_kullanimi": kullanim,
        "birim": "kimlik" if kimlik else "satir",
        "katmanla": katmanla,
        "val_oran": 0.20,
        "kat": 5,
        "oot_tanim": {"tur": "son_donem", "deger": None, "adet": 1},
        "seed": 42,
    }
    ayarlar.update(TRAIN_KULLANIMI[kullanim])

    # ---- ozet satirlari: SADECE etiket + deger --------------------------
    # Her satirin altinda bir aciklama cumlesi VARDI; kullanici oneriyi
    # okumak icin yedi paragraf gecmek zorunda kaliyordu. Aciklamalar
    # "Detayları göster" alanina tasindi (kullanici karari).
    def _satir(alan, deger, deger_metni=None):
        return {"etiket": BOLME_ALAN_BASLIK.get(alan, alan),
                "deger": deger_metni if deger_metni is not None
                         else bolme_etiket(alan, deger)}

    satirlar = [_satir("test_tanim", tur)]
    if tur == "hazir":
        sayim = hazir.get("sayim") or {}
        parcalar = []
        for ad, gorunen in (("egitim", "eğitim"), ("val", "doğrulama"),
                            ("test", "test"), ("oot", "test")):
            if sayim.get(ad):
                parcalar.append("%s %s" % (gorunen, _sayi(int(sayim[ad]))))
        satirlar.append({"etiket": "Bölme Kolonu",
                         "deger": ", ".join(hazir.get("kolonlar") or [])})
        satirlar.append({"etiket": "Setler",
                         "deger": " · ".join(parcalar) if parcalar else "-"})
    elif tur == "zamansal":
        satirlar.append(_satir(
            "oot_adet", None,
            "Son dönem%s" % ((" (%s)" % donemler[-1]) if donemler else "")))
        satirlar.append({"etiket": "Eğitim Dönemleri",
                         "deger": "%s dönem" % _sayi(max(len(donemler) - 1, 0))})
    else:
        satirlar.append(_satir(
            "test_oran", None,
            "%%%d" % round(100 * ayarlar["test_oran"])))
    if tur != "hazir":
        satirlar.append(_satir("train_kullanimi", kullanim))
        if ayarlar["cv"] != "yok":
            satirlar.append(_satir("kat", None, "%d" % ayarlar["kat"]))
        if ayarlar["val_var"]:
            satirlar.append(_satir("val_oran", None,
                                   "%%%d" % round(100 * ayarlar["val_oran"])))
        satirlar.append(_satir("birim", ayarlar["birim"]))
        satirlar.append(_satir("katmanla", None,
                               "Açık" if katmanla else "Kapalı"))
        satirlar.append(_satir("seed", None, str(ayarlar["seed"])))

    # ---- TEK CUMLELIK ozet + DETAYDA madde madde gerekce --------------
    ozet_cumlesi = ("Bu plan; veri büyüklüğü, dönem kolonunun durumu, "
                    "hedefin dağılımı ve aynı müşterinin kaç satırda "
                    "geçtiği dikkate alınarak önerildi.")

    detaylar = []
    if tur == "hazir":
        detaylar.append(
            "Tablonuzda bölmeyi gösteren kolon zaten var (%s); yeni bir "
            "bölme üretmek yerine o kullanılıyor. Kolonlara dokunulmuyor."
            % ", ".join(hazir.get("kolonlar") or []))
    elif zamansal:
        detaylar.append(
            "Dönem kolonunda %s farklı dönem var; test en son dönemden "
            "ayrılıyor." % _sayi(len(donemler)))
    elif m.get("donem"):
        detaylar.append(
            "Dönem kolonu tek değer taşıdığı için tarihe göre ayrılamadı; "
            "test rastgele seçiliyor.")
    else:
        detaylar.append(
            "Tarih bilgisi taşıyan bir kolon olmadığı için test rastgele "
            "seçiliyor.")
    if tur != "hazir":
        if katmanla:
            detaylar.append(
                "Hedef 0/1 olduğu için hedefin oranı her iki tarafta da "
                "aynı tutuluyor.")
        if kimlik:
            detaylar.append(
                "Bölme %s üzerinden yapılıyor: bir müşterinin bütün "
                "satırları aynı tarafta kalıyor." % m["id"])
        if buyuk:
            detaylar.append(
                "Tablo %s satır; bu büyüklükte ayrı bir doğrulama seti "
                "yeterli, çapraz doğrulama eğitim süresini birkaç katına "
                "çıkarır." % _sayi(satir))
        elif satir:
            detaylar.append(
                "Tablo %s satır; bu büyüklükte tek bir doğrulama parçası çok "
                "küçük kalacağı için çapraz doğrulama öneriliyor."
                % _sayi(satir))

    return {"ayarlar": ayarlar, "satirlar": satirlar,
            "ozet": ozet_cumlesi, "detaylar": detaylar,
            # Eski cagiranlar icin: tek paragraf hali.
            "gerekce": " ".join([ozet_cumlesi] + detaylar),
            "kisitlar": kisitlar}


def _bolme_oran_ozeti(durum):
    """Henuz bolunmemisken BEKLENEN dagilim.

    Uc bolme turu uc ayri cumle gerektiriyor:
      hazir    - setler tabloda yazili, oran diye bir sey yok
      zamansal - test DONEM bazli ayrilir; orani onceden bilinmiyor,
                 "eğitim %100" yazmak yanlisti (kullanici bildirimi)
      rastgele - oranlar biliniyor, yaklasik satir yazilabilir"""
    a = bolme_ayarlari(durum)
    satir = (durum.get("profil") or {}).get("satir")

    if a["test_tanim"] == "hazir":
        return "Setler veri setindeki bölme kolonundan okunacak."

    val = float(a.get("val_oran") or 0.0) if a.get("val_var") else 0.0

    if a["test_tanim"] == "zamansal":
        adet = int((a.get("oot_tanim") or {}).get("adet") or 1)
        donemler = [str(x) for x in (durum.get("_donemler") or [])]
        kalan = max(len(donemler) - adet, 0)
        parcalar = ["test: son %d dönem" % adet]
        if kalan:
            parcalar.insert(0, "eğitim: %s dönem" % _sayi(kalan))
        if val:
            parcalar.append("doğrulama: eğitimin %%%d'i" % round(100 * val))
        return " · ".join(parcalar) + "   (satır sayıları bölme uygulanınca)"

    test = float(a.get("test_oran") or 0.0)
    egitim = max(1.0 - test - val, 0.0)

    def parca(ad, oran):
        yuzde = "%%%d" % int(round(100 * oran))
        if not oran:
            return "%s -" % ad
        if not satir:
            return "%s %s" % (ad, yuzde)
        return "%s ~%s (%s)" % (ad, _sayi(int(round(satir * oran))), yuzde)

    parcalar = [parca("eğitim", egitim), parca("doğrulama", val),
                parca("test", test)]
    return " · ".join(parcalar) + "   (satır sayıları bölme uygulanınca)"


def bolme_ozeti(durum):
    """Tek satirlik set ozeti: "eğitim 6.400 · doğrulama - · test 1.600".

    Hem adim mesaji hem panel formu ayni satiri gosteriyor; iki yerde ayri
    kurulursa biri digerinden baska bir sayi yazar."""
    b = durum.get("bolme") or {}
    sayim = b.get("satir")
    # ESKI OTURUM KORUMASI: "satir" eskiden metin de olabiliyordu ve
    # sayim.get(...) AttributeError atiyordu - ozet satiri bir yana, o
    # oturumun TUM paneli patliyordu. Sozluk degilse sayim YOK sayilir ve
    # oransal ozete dusulur.
    if not isinstance(sayim, dict):
        sayim = {}
    if not sayim:
        # Ayar DEGISTIRILDIGINDE kalici bolme silinir, yani sayim kalmaz.
        # Eskiden burada bos dize donuyordu ve kullanici "Kaydet"e basinca
        # ozet satiri gozunun onunde bosaliyordu - kaydetmek bir seyi
        # bozmus gibi gorunuyordu. Sayim yoksa ORANDAN beklenen dagilim
        # yazilir ve bunun bir tahmin oldugu acikca soylenir.
        return _bolme_oran_ozeti(durum)
    a = bolme_ayarlari(durum)
    etiket = {"egitim": "eğitim", "val": "doğrulama", "test": "OOT / Test"}
    parcalar = []
    for ad in ("egitim", "val", "test"):
        n = sayim.get(ad)
        parcalar.append("%s %s" % (etiket[ad],
                                   _sayi(int(n)) if n else "-"))
    metin = " · ".join(parcalar)

    # Testin NASIL ayrildigi ozetin parcasi: ayni sayilar zamansal ve
    # rastgele bolmede bambaska anlam tasiyor.
    if a["test_tanim"] == "zamansal":
        donem = b.get("oot_donemleri") or b.get("test_donemleri")
        if donem:
            metin += "   (test dönemi: %s)" % ", ".join(str(x) for x in donem)
        else:
            adet = int(a["oot_tanim"]["adet"])
            metin += "   (test: son %d dönem)" % adet
    else:
        metin += "   (%%%d rastgele)" % round(100 * float(a["test_oran"]))
    return metin


def bolme_uyarilari(durum):
    """Bolme ayarlarindan dogan uyarilar (veri OKUMADAN).

    Panel formu ve algoritma adimi ayni listeyi kullanir; iki yerde ayri
    uretilirse biri sessizce eskir."""
    a = bolme_ayarlari(durum)
    m = durum.get("meta") or {}
    b = durum.get("bolme") or {}
    uyarilar = []

    if not a["val_var"] and a["cv"] == "yok":
        uyarilar.append(GECERSIZ_BIRLESIM)

    # Oranlar TEK TEK kirpiliyordu ama TOPLAMINA bakilmiyordu: val %50 +
    # test %60 gibi bir ayar her iki kirpmadan da gecip egitim setini
    # bosaltiyor, hata ancak model adiminda "satir yetersiz" diye
    # cikiyordu. Kullanici bunu kaydederken gormeli.
    # Zamansal testte test_oran KULLANILMIYOR (test donem bazli ayriliyor);
    # toplama katmak, kullaniciya hic uygulanmayacak bir oran yuzunden
    # uyari gosteriyordu.
    test_o = (0.0 if a["test_tanim"] == "zamansal"
              else float(a.get("test_oran") or 0.0))
    val_o = float(a.get("val_oran") or 0.0) if a.get("val_var") else 0.0
    if test_o + val_o >= 1.0:
        uyarilar.append(
            "OOT / Test (%%%d) ve doğrulama (%%%d) paylarının toplamı tüm "
            "veriyi kaplıyor; eğitim setine satır kalmaz."
            % (round(100 * test_o), round(100 * val_o)))
    elif test_o + val_o > 0.6:
        uyarilar.append(
            "Eğitim setine verinin yalnızca %%%d'i kalıyor; ölçüm güvenilir "
            "olmayabilir." % round(100 * (1.0 - test_o - val_o)))
    if a["birim"] == "kimlik" and not m.get("id"):
        uyarilar.append("Bölme kimlik bazlı seçilmiş ama kimlik kolonu "
                        "tanımlı değil; satır bazına düşüldü.")
    # DONEM KOLONU VAR DIYE ZAMANSAL ONERILMEZ: kolon tanimli ama TEK
    # DEGER tasiyorsa zamansal bolme kurulamiyor (bkz. bolme_kisitlari) ve
    # bu uyari ekranda kisitla CELISIYORDU - ust tarafta "dönem kolonunda
    # tek değer var, zamansal kurulamıyor", altta "zamansal daha uygun".
    if (a["test_tanim"] == "rastgele" and m.get("donem")
            and len(durum.get("_donemler") or []) >= ONERI_EN_AZ_DONEM):
        uyarilar.append("Öneri: Dönem kolonu tanımlı görünüyor. Zaman "
                        "etkisini ve olası performans bozulmasını ölçmek "
                        "için zamansal test bölmesi daha uygun olabilir.")
    if a["test_tanim"] == "zamansal" and not m.get("donem"):
        uyarilar.append("Zamansal test istendi ama dönem kolonu tanımlı "
                        "değil; rastgele teste düşüldü.")
    # "Çoklu tekrar" CAPRAZ DOGRULAMAYA BAGLI: cv kapaliyken tekrar
    # sayisinin hicbir etkisi yok, ayar sessizce bosa gidiyordu.
    if a.get("seed_tur") == "coklu" and a["cv"] == "yok":
        uyarilar.append("Çoklu tekrar seçili ama çapraz doğrulama kapalı; "
                        "tekrar sayısının bir etkisi olmaz.")
    if int(a.get("gap") or 0) > 0 and a["test_tanim"] != "zamansal":
        uyarilar.append("Dönemler arası boşluk yalnızca zamansal bölmede "
                        "kullanılır; bu ayar uygulanmayacak.")
    if a["cv"] == "zaman" and not m.get("donem"):
        uyarilar.append("Zaman sıralı çapraz doğrulama istendi ama dönem kolonu "
                        "tanımlı değil; çapraz doğrulama kurulamaz.")
    for not_ in (b.get("cv_notlari") or []):
        if not_ not in uyarilar:
            uyarilar.append(not_)
    for ad in SET_ADLARI:
        n = (b.get("satir") or {}).get(ad)
        if n is not None and 0 < int(n) < MIN_SET_SATIR:
            uyarilar.append("%s seti yalnızca %s satır; %s satırın altındaki "
                            "sette ölçüm güvenilir değil."
                            % (SET_BASLIK[ad], _sayi(int(n)),
                               _sayi(MIN_SET_SATIR)))
    return uyarilar
