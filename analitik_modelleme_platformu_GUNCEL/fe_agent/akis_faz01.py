# -*- coding: utf-8 -*-
"""fe_agent/akis_faz01.py - Faz 01 - Calisma Kurulumu: mod, veri, sozluk, tanimlar, bolme.

akis.py bolundu; bu dosya o bolumun aynisidir.
"""

import datetime
import json
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
from fe_agent import profil as profil_mod
from fe_agent import profil_kural
from fe_agent import amp as amp_mod
from fe_agent import spark_is

from fe_agent.akis_metin import (
    ACIK_MODLAR, ADIM_ADI, KARSILAMA, MOD_ADLARI, MOD_KALIP, MOD_SECENEKLERI,
    MOD_SIRA)
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
    donem_degeri, donem_serisi, donem_sirala,
    dataset_yaz, dosya_yaz, sahip_yaz, modelleme_kaynagi,
    ORNEK_MASKE, _ornek_metni, hazir_bolme_bul_profil,
    BOLME_KALICI_ALANLARI, SET_ADLARI, SPLIT_ETIKET, MIN_SET_SATIR,
    _zamansal_test_donemleri, set_basligi,
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
               "_sozluk_esitleme", "_sozluk_esitleme_imza",
               "_hazir_bolme",
               # Sozluk teyidi eski moda ait bir denetim kaydidir; mod
               # degisince veri seti de sozluk de degisir, damga
               # tasinmamali.
               "teyit")


# Aday olmak icin dolu hucrelerin en az bu kadari donem olarak cozulmeli
# (kural profil_kural'da; profil isi ayni esigi kullaniyor).
DONEM_COZULME_ORANI = profil_kural.DONEM_COZULME_ORANI


# Donem adayi hesabinin surumu. Kural degisince eski calismalarin
# profilindeki liste YENIDEN hesaplanir (bkz. _donem_adaylarini_hazirla).
DONEM_ADAY_SURUMU = 4
# Aday cikmadiginda nedeni yazilan kolonlar: ADI donem/tarih olan. Ad
# "_" ile parcalanip PARCA PARCA bakiliyor: TXN_ACTIVE_MONTH_CNT gibi
# sayac kolonlari adinda MONTH gecse de donem kolonu degil (kullanici
# bildirimi: notta bunlar da listeleniyordu). Olcu parcasi tasiyan ad
# (CNT, AMT, SUM ...) hic listelenmez.
_DONEM_AD_PARCALARI = {"DONEM", "DÖNEM", "PERIOD", "PERIYOD", "TARIH", "TARİH",
                       "DATE", "DT", "AY", "YIL", "YEAR", "MONTH", "SNAP",
                       "SNAPSHOT", "YYYYMM", "YYYYMMDD", "REF"}
_OLCU_PARCALARI = {"CNT", "COUNT", "SUM", "AMT", "AVG", "MEAN", "MIN", "MAX",
                   "STD", "RATIO", "ORAN", "ADET", "TUTAR", "SAYI", "NUM",
                   "FLAG", "FLG", "PCT", "DIFF", "CHG", "TOT", "TOTAL"}
_DONEM_AD_KOKLERI = ("DONEM", "DÖNEM", "TARIH", "TARİH", "PERIOD", "PERIYOD", "DATE")
DONEM_NEDEN_EN_FAZLA = 5


def _donem_adli_mi(ad):
    parcalar = {p for p in re.split(r"[^0-9A-Za-zÇĞİÖŞÜçğıöşü]+", str(ad).upper()) if p}
    if parcalar & _OLCU_PARCALARI:
        return False
    # Turkce ekli bicimler de: TARIHI, DONEMI, PERIODU ...
    return bool(parcalar & _DONEM_AD_PARCALARI) or any(
        p.startswith(k) for p in parcalar for k in _DONEM_AD_KOKLERI)


def _donem_neden_maddeleri(nedenler):
    """Aday cikmadiginda, ADI donem olan kolonlarin neden secilemedigi;
    her kolon ayri madde (kullanici karari: "bulunamadı yazsın, bulunan
    varsa neden seçilemeyecekleri ayrı ayrı maddelerde")."""
    return ["%s: %s" % (k, v) for k, v in (nedenler or {}).items()
            if _donem_adli_mi(k)][:DONEM_NEDEN_EN_FAZLA]


def _donem_adaylarini_hazirla(durum):
    """Profilde donem adaylari yoksa BIR KEZ hesaplayip yazar; profili doner.

    Bu liste veri seti secilirken (_temel_profil) cikariliyor. O surumden
    ONCE baslamis calismalarin profilinde yok; eskiden bu durumda form tum
    kolonlara dusuyordu ve kimlik, hedef, tutar kolonlari donem olarak
    secilebiliyordu (kullanici bildirimi). Artik eksikse tablodan
    hesaplaniyor. Okuma onbellekten gelir; tablo okunamazsa liste bos
    kalir ve form "aday bulunamadi" der - tum kolonlara DUSULMEZ."""
    p = durum.get("profil") or {}
    if (isinstance(p.get("donem_adaylari"), list)
            and p.get("donem_adaylari_surum") == DONEM_ADAY_SURUMU):
        return p
    try:
        prof = _profil(durum)
        p = durum.get("profil") or p
        p["donem_adaylari"] = list(prof.get("donem_adaylari") or [])
        p["donem_nedenler"] = _donem_neden_maddeleri(prof.get("donem_nedenler"))
        p["donem_adaylari_surum"] = DONEM_ADAY_SURUMU
        p.pop("donem_hata", None)
    except Exception as e:
        # OKUMA HATASI KALICI YAZILMAZ (surum isareti konmuyor): eskiden
        # bos liste profile yaziliyor ve tablo sonra okunabilse de liste
        # bir daha hesaplanmiyordu. Bir sonraki acilista yeniden denenir.
        p["donem_adaylari"] = []
        p["donem_hata"] = str(e)[:200]
    durum["profil"] = p
    return p


# ===========================================================================
# VERI SETI PROFILI (tam tablo, PySpark) - bkz. fe_agent/profil.py
# ===========================================================================
# Birinci fazin tam veriye bakan kararlari (tek deger, hedef / kimlik /
# donem adaylari, tip donusumu, kisisel veri, null orani, tekrarlanan
# satir) webapp'te pandas ile DEGIL, veri seti secildiginde bir kez
# calisan PySpark isinin profilinden okunur (kullanici karari: buyuk
# veride pandas yok). Profil calismanin klasorunde: /<calisma>/profil.json.
def _profil(durum, taze=False):
    """Secili veri setinin profili. Calismada ayni veri seti icin profil
    varsa o okunur; yoksa (ya da taze=True) PySpark isi calistirilir."""
    veri = durum.get("veri_seti")
    p = durum.get("profil") or {}
    if not taze and p.get("_profil_veri") == veri and p.get("_profil_kosu"):
        prof = profil_mod.profil_oku(amp_klasor_adi(durum), p["_profil_kosu"])
        if prof:
            return prof
    prof = profil_mod.profil_cikar(veri, amp_klasor_adi(durum),
                                   durum.get("_oturum_id") or "")
    _profil_isaretle(durum, prof, veri)
    return prof


def _profil_isaretle(durum, prof, veri):
    p = durum.get("profil") or {}
    p["_profil_veri"] = veri
    p["_profil_kosu"] = prof.get("kosu_id")
    durum["profil"] = p


def _bellekten_profil(durum, df, veri):
    """Tablo zaten bellekteyse (Mod B/D birlestirme sonucu) profil ayni
    kurallarla oradan cikarilir ve calismaya yazilir."""
    prof = profil_kural.yerel_profil(df, veri)
    prof["kosu_id"] = uuid.uuid4().hex
    yol = profil_mod.profil_yolu(amp_klasor_adi(durum))
    metin_yaz(yol, json.dumps(prof, ensure_ascii=False, default=str))
    profil_mod._ONBELLEK[yol] = (prof["kosu_id"], prof)
    _profil_isaretle(durum, prof, veri)
    return prof


def _profil_kolonlari(durum):
    """{kolon: kolon_profili}; profil okunamazsa bos."""
    try:
        return profil_mod.kolonlar(_profil(durum))
    except Exception:
        return {}


def _kolon_ozeti(prof):
    """kolon_ozeti_cikar'in profil karsiligi: {ad, tip, null_oran, tekil,
    ornek}. Kisisel veri tasiyan kolonun ornegi maskelenir."""
    ozet = []
    for k in prof.get("kolonlar") or []:
        ornek = None
        if k.get("dolu"):
            ornek = ORNEK_MASKE if (k.get("pii_ad") or k.get("pii_deger")) \
                else _ornek_metni(k.get("ornek"))
        ozet.append({"ad": k["ad"], "tip": k["kaynak_tip"],
                     "null_oran": k.get("null_oran"),
                     "tekil": k.get("tekil"), "ornek": ornek})
    return ozet


def _temel_profil(durum, prof):
    """Veri seti secildiginde BIR KEZ hesaplanan temel sayilar - PROFILDEN.

    Sonuclar durum["profil"] icine yazilir; Analiz Merkezi'ndeki VERI
    sekmesi ve modelleme tanimlari formu buradan beslenir."""
    p = durum.get("profil") or {}
    hucre = int(prof["satir"]) * int(prof["kolon"])
    bos = sum(int(k.get("bos") or 0) for k in prof.get("kolonlar") or [])
    p.update({
        "satir": int(prof["satir"]), "kolon": int(prof["kolon"]),
        "kolon_baslangic": int(prof["kolon"]),
        # Toplam null orani: tam tablo, butun hucreler (profilden, kesin).
        "null_oran": round(float(bos) / hucre, 4) if hucre else None,
        "sayisal": int(prof["sayisal"]),
        "tarih": int(prof["tarih"]),
        "duplicate": int(prof["duplicate"]),
        "kolon_ozet": _kolon_ozeti(prof),
        # Profili hangi motorun cikardigi ve veri setinin dosya boyutu
        # (bkz. motor.py); sag paneldeki Veri Seti kartinda gorunur.
        "motor": prof.get("motor"),
        "dosya_boyutu": prof.get("dosya_boyutu"),
    })
    p["hedef_adaylari"] = list(prof.get("hedef_adaylari") or [])
    p["kimlik_adaylari"] = list(prof.get("kimlik_adaylari") or [])
    p["donem_adaylari"] = list(prof.get("donem_adaylari") or [])
    p["donem_nedenler"] = _donem_neden_maddeleri(prof.get("donem_nedenler"))
    p["donem_adaylari_surum"] = DONEM_ADAY_SURUMU
    p.pop("donem_hata", None)
    _kimlik_duplicate(durum, prof, p)
    durum["profil"] = p
    return p


def _kimlik_duplicate(durum, prof, p):
    """Kimlik kolonu belliyse ayrica kimlik bazli tekrar sayisi.

    "Satirin tamami ayni" ile "ayni musteri iki kere" farkli sorunlardir;
    ikincisi panelde ayri satir olarak gosterilir. Tekrar = satir - bos
    dahil tekil deger sayisi (df.duplicated(subset=[kimlik]) ile ayni)."""
    kimlik = (durum.get("meta") or {}).get("id")
    kp = profil_mod.kolonlar(prof).get(kimlik) if kimlik else None
    if kp is not None:
        p["duplicate_kimlik"] = int(kp.get("tekrar") or 0)


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


# MOD DEGISIKLIGINDE ONAY YOK (kullanici karari: "ne seçersem o olacak").
# Baska bir mod karti secilince o ana kadarki secimler (veri seti, sozluk,
# analizler) sessizce sifirlanir ve yeni mod yerlesir.
def _mod_yerlestir(durum, yeni_mod):
    durum["mod"] = yeni_mod
    durum["_onceki_mod"] = yeni_mod
    durum["_secenekler"] = []
    durum.pop("_mod_onay", None)


def mod_girdi(durum, mesaj):
    m = MOD_KALIP.search(mesaj or "")
    # Eski oturumlarda kalmis onay bekleme alani: artik onay sorulmuyor.
    durum.pop("_mod_onay", None)
    eski_mod = durum.get("mod") or durum.get("_onceki_mod")

    if not m:
        # Geri donuldugunde eski secim silinsin; faz agaci sifirlanir.
        # Hangi moddan gelindigi _onceki_mod'da saklanir: kullanici baska
        # bir mod secerse eski moda ait veri temizlenebilsin.
        if durum.get("mod"):
            durum["_onceki_mod"] = durum["mod"]
        durum["mod"] = None
        durum["_secenekler"] = MOD_SECENEKLERI
        # ADIMIN METNI KARSILAMA'DIR: ilk acilista da geri donuste de ayni
        # metin, tek yerden (backend._karsilama_govdesi bu donusu kullanir).
        return False, KARSILAMA

    secim = m.group(2).upper()
    yeni_mod = MOD_SIRA.get(secim, secim)

    if yeni_mod not in ACIK_MODLAR:
        # Kapali baslangic: kartta zaten tiklanamaz; yazarak da secilemez.
        durum["_secenekler"] = MOD_SECENEKLERI
        return False, ("«%s» başlangıcı şu an kapalı. Açık başlangıçlardan "
                       "birini seçin." % MOD_ADLARI.get(yeni_mod, yeni_mod))

    if eski_mod and eski_mod != yeni_mod:
        # Secilen kart uygulanir; onceki modun verisi sifirlanir.
        _mod_sifirla(durum)

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


# TEK SATIR, KALIN DEGIL (kullanici karari: "yazı bold olmamalı, çok
# gereksiz uzun"). "En az iki tablo" kurali ayri gri satirda degil, ayni
# cumlede.
KAYNAK_TABLO_METNI = (
    "Baz veri setini oluşturacak kaynak tabloları seçin (en az iki tablo). "
    "Kolonları aynı olan tablolar (ör. yıllara bölünmüş aynı tablo) alt alta "
    "eklenir; kolonları farklı olanlar için yapay zekâ hangi tablonun iskelet "
    "olacağını ve diğerlerinin hangi anahtarla bağlanacağını önerir.")


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
            "baslik": "Kaynak Tablolar",
            "etiket": "Kaynak Tablo Ara",
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

def _degerde(metin):
    """Cikti listesi degerinde ":" etiket ayiracina karismasin."""
    return str(metin).replace(": ", " · ").replace(":", " ·")


def _tablo_ozeti(tablolar):
    """Secilen tablolarin ozeti ("  Etiket : Deger"; arayuz hizali tablo
    cizer). Kolon sayisi tek satirlik okumadan. SATIR SAYISI BURADA
    SAYILMAZ: 135 milyon satirlik tabloyu webapp'e cekmek demek; kesin
    satir sayilari birlestirme isinde (Spark) hesaplanip yazilir."""
    satirlar = []
    for ad in tablolar:
        try:
            satirlar.append("  %s : %s kolon" % (ad, _sayi(_df_oku(ad, limit=1).shape[1])))
        except Exception as e:
            satirlar.append("  %s : okunamadı (%s)" % (ad, _degerde(str(e)[:80])))
    return ("%s kaynak tablo seçildi; satır sayıları birleştirmede "
            "hesaplanacak.\n%s" % (_sayi(len(tablolar)), "\n".join(satirlar)))


def ham_veri_plan(durum):
    """Kullanilmiyor (adim plan=None: form onaydir). Eski cagrilar icin."""
    return _tablo_ozeti(durum["ham_tablolar"])


def ham_veri_uygula(durum):
    return _tablo_ozeti(durum["ham_tablolar"])

# ===========================================================================
# ADIM 1.3A — BIRLESTIRME PLANI  (Mod B ve D)   <-- LLM
# ===========================================================================
# Sonuc iki yere yazilir (ad SABIT: MODELLEME_BAZ, kullanici degistiremez):
#   1) calismanin kendi klasoru: PROJE_HAFIZASI/v3/MODELLEME_BAZ.csv
#      -> calismanin KALICI kopyasi; baska calisma ezemez.
#   2) akistaki MODELLEME_BAZ veri seti -> sonraki fazlar ve Dataiku
#      senaryolari buradan okur. Veri seti ORTAK oldugu icin sahibi
#      kaydedilir; baska calisma uzerine yazarsa bu calisma (1)'i okur.


def _alt_alta_mi(semalar):
    """Secilen tablolarin HEPSI ayni kolonlara mi sahip (sira onemsiz)?
    Oyleyse bunlar ayni verinin parcalaridir (yil, donem ...) ve yan yana
    birlestirilmez, ALT ALTA eklenir."""
    kumeler = [frozenset(map(str, k)) for k in semalar.values()]
    return len(kumeler) >= 2 and all(k == kumeler[0] for k in kumeler)


def _alt_alta_uygula(durum, tablolar):
    """Ayni kolonlu tablolari kumede (Spark) alt alta MODELLEME_BAZ veri
    setine yazar. Doner: isin sonucu {tablolar: {ad: {satir, kolon}},
    satir, kolon}."""
    return amp_mod.baz_yaz(durum, tablolar)


def birlestirme_plan(durum):
    # Gercek semalar: anahtar = tam dataset adi
    semalar = {}
    for ad in durum["ham_tablolar"]:
        try:
            semalar[ad] = list(_df_oku(ad, limit=1).columns)
        except Exception:
            continue

    if len(semalar) < 2:
        durum["birlestirme"] = {}
        raise AdimHatasi("Seçilen tabloların en az ikisini okuyamadım; tablo "
                         "seçimini gözden geçirin.")

    # AYNI KOLONLU TABLOLAR ALT ALTA (kullanici bildirimi: iki yillik ayni
    # tablo verildi, yapay zeka yan yana birlestirmeye calisip var olmayan
    # bir tablo adi uydurdu). Karar gerektirmez: onay beklenmeden uygulanir.
    if _alt_alta_mi(semalar):
        durum["birlestirme"] = {"plan": {"tur": "alt_alta",
                                         "tablolar": list(semalar)}}
        durum["_plan_otomatik"] = True
        return ""

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
        raise AdimHatasi("Tabloları inceledim ama kullanılabilir bir birleştirme "
                         "planı çıkaramadım. Tablo seçimini değiştirip yeniden "
                         "deneyebilirsiniz.\n  Sebep : %s"
                         % _degerde(llm_hata or "Model tanımadığı tablo adları önerdi."))

    # Plani gercek adlara cevirip GERCEK semalara karsi dogruluyoruz
    ham_plan = _plan_adlari_cevir(ham_plan, kisa_to_tam)
    plan, hatalar = birl_mod.dogrula(ham_plan, semalar)

    if plan is None:
        durum["birlestirme"] = {}
        raise AdimHatasi("Yapay zekânın önerdiği birleştirme planı doğrulamayı "
                         "geçemedi. Tablo seçimini değiştirip yeniden "
                         "deneyebilirsiniz.\n  Sebep : %s%s"
                         % (_degerde(hatalar[0]) if hatalar else "-",
                            "".join("\n  %s" % _degerde(h) for h in hatalar[1:8])))

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

    if plan.get("tur") == "alt_alta":
        tablolar = list(plan.get("tablolar") or [])
        oz = _alt_alta_uygula(durum, tablolar)
        onbellek_temizle()
        durum["veri_seti"] = BAZ_ADI
        durum["birlestirme"].update({"dataset": BAZ_ADI, "dosya": None,
                                     "ozet": {"satir": oz.get("satir"),
                                              "kolon": oz.get("kolon")}})
        sahip_yaz(BAZ_ADI, durum)
        _temel_profil(durum, _profil(durum, taze=True))
        sozluk_not = ""
        if durum.get("mod") == "B":
            # Koken: her kolon ilk tablodaki ayni adli kolondan (hepsinde ayni).
            ornek = _df_oku(BAZ_ADI, limit=1)
            kutuk = pd.DataFrame([{"KOLON": c, "KAYNAK_TABLO": tablolar[0],
                                   "KAYNAK_KOLON": c, "TUR": "alt alta"}
                                  for c in ornek.columns])
            sozluk_not = _mod_b_sozlugu(durum, ornek, kutuk)
        satirlar = ["  %s : %s satır × %s kolon"
                    % (ad, _sayi(t.get("satir")), _sayi(t.get("kolon")))
                    for ad, t in (oz.get("tablolar") or {}).items()]
        return ("Tablolar alt alta eklendi; kolonları aynı olduğu için yan "
                "yana birleştirilmedi.\n%s\n"
                "  Baz veri seti : %s satır × %s kolon\n"
                "  Kayıt : %s veri seti"
                % ("\n".join(satirlar), _sayi(oz.get("satir")),
                   _sayi(oz.get("kolon")), BAZ_ADI)) + sozluk_not

    baz, kutuk, ozet = birl_mod.calistir(plan, lambda ad: _df_oku(ad))

    # Hedef veri seti yoksa write_with_schema patliyordu ve o ana kadarki
    # tum hesap kayboluyordu. Once ozet/kutuk durumda saklanir, tablo CSV
    # yedegine alinir, sonra anlasilir hata verilir.
    durum["birlestirme"]["ozet"] = ozet
    lineage_yazildi, lineage_yedek = _yaz(LINEAGE_ADI, kutuk, "/lineage.parquet")
    durum["birlestirme"]["lineage"] = lineage_yazildi

    ad = BAZ_ADI
    kopya = dosya_yaz(_amp_yolu(durum, ad), baz)
    durum["birlestirme"]["dosya"] = kopya or None
    # MODELLEME_BAZ Flow'da yoksa webapp kurar (kullanici bir sey eklemez);
    # sonraki Spark isleri (profil, AMP) girdi olarak bu veri setini okur.
    spark_is.veri_seti_hazirla(ad, durum["ham_tablolar"][0])
    if not dataset_yaz(ad, baz):
        durum["veri_seti"] = None
        raise AdimHatasi("Birleştirme hesaplandı ama sonucu %s veri setine "
                         "yazamadım." % ad)
    durum["birlestirme"]["dataset"] = ad
    durum["veri_seti"] = ad
    sahip_yaz(ad, durum)
    onbellek_temizle()

    # Mod B/D'de veri seti burada olusuyor ve tablo zaten bellekte;
    # profil (kolon ozeti, adaylar) ayni kurallarla buradan cikar.
    _temel_profil(durum, _bellekten_profil(durum, baz, ad))

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
        "baslik": "Baz Veri Seti",
        "aciklama": "Modellemeye girecek baz veri setini seçin; baz sözlük "
                    "bu veri setinden oluşturulacak.",
        "buton": "Devam Et",
        "alanlar": [{"ad": "veri_seti", "etiket": "Baz Veri Seti",
                     "placeholder": "Baz veri seti ara…",
                     "ipucu": "Modellemeye girecek tek tablo: hedef, kimlik "
                              "ve tüm değişkenler bu tabloda",
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
    p = _temel_profil(durum, _profil(durum, taze=True))

    return ("Veri setini okudum:\n\n"
            "  %s\n"
            "  %s satır × %s kolon  (%s sayısal, %s kategorik)\n\n"
            "Sözlük bu veri setinden üretilecek. Devam edilsin mi?"
            % (durum["veri_seti"], _sayi(p["satir"]), _sayi(p["kolon"]),
               _sayi(p["sayisal"]), _sayi(p["kolon"] - p["sayisal"])))

def veri_sec_uygula(durum):
    """Form onaydir (plan=None): secimden sonra ozet yazilir, onay sorulmaz."""
    p = _temel_profil(durum, _profil(durum, taze=True))
    return ("Baz veri seti seçildi.\n"
            "  Veri seti : %s\n"
            "  Boyut : %s satır × %s kolon\n"
            "  Tipler : %s sayısal, %s kategorik"
            % (durum["veri_seti"], _sayi(p["satir"]), _sayi(p["kolon"]),
               _sayi(p["sayisal"]), _sayi(p["kolon"] - p["sayisal"])))

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
    prof = _profil(durum)

    # NOT: burada ayrica 'haric' listesi VERILMIYOR. Kimlik/PII korumasi tek
    # yerde, sozluk.py icindeki _ornek_guvenli_mi()'de toplanmistir (kolon
    # adi deseni, deger deseni, tekil oran, uzun metin). Eskiden buraya
    # meta["id"] ile bir haric kumesi geciliyordu; sozluk_uret adimi
    # tanimlar adimindan ONCE geldigi icin meta["id"] daima bostu — olu kod.
    profiller = sozluk_mod.profil_cikar_profilden(prof)

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
        yazildi, yedek = _yaz(SOZLUK_ADI, tablo, "/degisken_sozlugu.parquet")
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
        "baslik": "Baz Veri Seti ve Baz Sözlük",
        "aciklama": "Modellemeye girecek baz veri setini ve bu veri setinin "
                    "değişken açıklamalarını taşıyan baz sözlüğü seçin.",
        # Dugme etiketi SONRAKI EKRANIN adini soylemeli: bu form
        # gonderildiginde "Girdi doğrulama tamamlandı" karti aciliyor.
        # Eski etiket analizin burada basladigini ima ediyordu; oysa
        # analiz bu adimdan cok sonra basliyor.
        "buton": "Girdileri Doğrula",
        "alanlar": [
            {"ad": "veri_seti", "etiket": "Baz Veri Seti",
             "placeholder": "Baz veri seti ara…",
             "ipucu": "Modellemeye girecek tek tablo: hedef, kimlik ve tüm "
                      "değişkenler bu tabloda",
             "deger": veri or durum.get("veri_seti") or ""},
            {"ad": "sozluk", "etiket": "Baz Sözlük",
             "placeholder": "Sözlük tablosu ara…",
             "ipucu": "Baz veri setindeki kolonların adını ve açıklamasını "
                      "taşıyan tablo",
             "deger": sozluk or durum.get("sozluk") or ""},
        ],
        "sablon": "veri seti {veri_seti} ve sözlük {sozluk}",
    }

def _kolon_listesi_metni(kolonlar, en_fazla=8):
    kolonlar = [str(k) for k in kolonlar]
    ek = " …" if len(kolonlar) > en_fazla else ""
    return ", ".join(kolonlar[:en_fazla]) + ek


def _sozluk_denetle(sozluk_ad, veri_ad):
    """Sozlugun girdi olarak KABUL edilip edilemeyecegi. Hata metni ya da
    None doner (kullanici karari: "sözlükte kolon adı ve açıklama kolonu
    olmalı; kontrollerden geçmeden onaylanmamalı").

    Denetimler, sonraki adimlarin sozlugu okurken kullandigi kurallarin
    AYNISI (sozluk_calisma.degisken_kolonu_bul / tanim_kolonu_bul):
      1. Aciklama kolonu var: ACIKLAMA / AÇIKLAMA / TANIM / DESCRIPTION.
      2. Kolon adi kolonu veri setinin kolonlarini gercekten tasiyor: en
         az bir veri kolonu sozlukte geciyor (buyuk/kucuk harf farksiz).
         Ad kolonu bilinen adlardan biri degilse ilk kolon varsayiliyor;
         eslesme yoksa bu varsayim yanlis demektir.
      3. Eslesen kolonlardan en az birinin aciklamasi dolu.
    Hepsi gecmeden adim ilerlemez; kart onayli gorunmez."""
    try:
        sz = _df_oku(sozluk_ad)
    except Exception as e:
        return "'%s' sözlüğü okunamadı: %s" % (sozluk_ad, str(e)[:160])
    try:
        veri_kolonlari = [str(c) for c in _df_oku(veri_ad, limit=5).columns]
    except Exception as e:
        return "'%s' veri seti okunamadı: %s" % (veri_ad, str(e)[:160])
    if sz is None or not len(sz.columns) or not len(sz):
        return "'%s' sözlüğü boş; içinde satır yok." % sozluk_ad

    sozluk_kolonlari = _kolon_listesi_metni(sz.columns)
    tanim_k = sozluk_calisma.tanim_kolonu_bul(sz)
    if tanim_k is None:
        return ("'%s' sözlüğünde açıklama kolonu bulunamadı. Kolonların "
                "açıklamasını taşıyan kolonun adı ACIKLAMA, TANIM ya da "
                "DESCRIPTION olmalı. Sözlüğün kolonları: %s."
                % (sozluk_ad, sozluk_kolonlari))

    ad_k = sozluk_calisma.degisken_kolonu_bul(sz)
    sozluk_adlari = {str(x).strip().upper() for x in sz[ad_k].dropna()}
    eslesen = [c for c in veri_kolonlari if c.strip().upper() in sozluk_adlari]
    if not eslesen:
        return ("'%s' sözlüğünde '%s' veri setinin kolon adlarını taşıyan "
                "bir kolon bulunamadı. Kolon adlarını taşıyan kolonun adı "
                "DEGISKEN, KOLON ya da VARIABLE olmalı (ya da sözlüğün ilk "
                "kolonu olmalı) ve içindeki adlar veri setindekilerle aynı "
                "yazılmalı. Sözlüğün kolonları: %s. Veri setinden örnek "
                "kolonlar: %s."
                % (sozluk_ad, veri_ad, sozluk_kolonlari,
                   _kolon_listesi_metni(veri_kolonlari, 5)))

    tanimlar = sz[tanim_k].fillna("").astype(str).str.strip()
    adlar = sz[ad_k].astype(str).str.strip().str.upper()
    dolu = set(adlar[tanimlar != ""])
    if not any(c.strip().upper() in dolu for c in eslesen):
        return ("'%s' sözlüğünde veri setiyle eşleşen %d kolonun hiçbirinin "
                "açıklaması dolu değil ('%s' kolonu boş)."
                % (sozluk_ad, len(eslesen), tanim_k))
    return None


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

    hata = _sozluk_denetle(sozluk, veri)
    if hata:
        _kurulum_formu(durum, veri, sozluk)
        return False, "Girdiler onaylanmadı. " + hata

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
    alanlar = [{"ad": "sozluk_%d" % i, "etiket": "%s Tablosunun Sözlüğü" % t,
                "placeholder": "Kaynak sözlük ara…",
                "deger": secili.get(t) or ""}
               for i, t in enumerate(tablolar)]
    durum["_secim_alani"] = {
        "tip": "form",
        "baslik": "Kaynak Sözlükler",
        "aciklama": "Her kaynak tablonun kendi sözlüğünü seçin. Aynı "
                    "sözlük birden fazla tablo için seçilebilir. Baz sözlük "
                    "birleştirmeden sonra bu kaynak sözlüklerden kurulur.",
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

    hatalar = []
    for tablo, sozluk in secim.items():
        hata = _sozluk_denetle(sozluk, tablo)
        if hata:
            hatalar.append("• %s: %s" % (tablo, hata))
    if hatalar:
        _kaynak_sozluk_formu(durum, secim)
        return False, ("Sözlükler onaylanmadı:\n" + "\n".join(hatalar))

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
    yazildi, yedek = _yaz(SOZLUK_ADI, tablo, "/degisken_sozlugu.parquet")
    durum["sozluk"] = yazildi or None
    durum["sozluk_yedek"] = yedek
    durum["sozluk_uretim"] = {"kaynak": "kaynak sözlükleri", **oz}
    # Profil + kapsam SIMDI: baz zaten bellekte. Modelleme tanimlari
    # hedef/kimlik adaylarini, sozluk tanimlari tanimsiz listesini
    # buradan okuyor; tablo ikinci kez taranmiyor. Kopyadan ONCE: kopya
    # veri setinin kolon listesine esitleniyor (bkz. sozluk_calisma).
    _kapsam_hesapla(durum, _profil(durum), tablo)
    kopya_not = _calisma_kopyasi_kur(durum, tablo)
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


def _tekil_tamamla(prof, kolonlar, profil):
    """Karara konu olan kolonlarin tekil deger sayisini profile isler
    (kartta gosteriliyor, dil modeline giden metadata'da da var). Sayi
    veri seti profilinden: tam tablo, kesin."""
    hedef = {str(k) for k in (kolonlar or [])}
    if not hedef:
        return
    kol = profil_mod.kolonlar(prof)
    for k in (profil.get("kolon_ozet") or []):
        if not isinstance(k, dict) or str(k.get("ad")) not in hedef:
            continue
        if k.get("tekil") is not None:
            continue
        kp = kol.get(str(k["ad"]))
        k["tekil"] = int(kp["tekil"]) if kp is not None else None


def _etiket_kirp(deger):
    """Modele giden etiket metni. Uzun etiket promptu sisirir."""
    metin = str(deger).strip()
    if len(metin) > EN_UZUN_ETIKET:
        return metin[:EN_UZUN_ETIKET - 1] + "…"
    return metin


def _sayisal_ozet(kp):
    """Sayisal kolondan min / maks / ceyrekler (profilin kesin
    kantilleri). TEK TEK DEGER DONMEZ."""
    q = kp.get("kantiller")
    if not q:
        return {}
    try:
        q = [float(x) for x in q]
    except (TypeError, ValueError):
        return {}
    return {"min": round(q[0], 4),
            "maks": round(q[4], 4),
            "ceyrekler": [round(x, 4) for x in q[1:4]]}


def _tarih_ozet(kp):
    """Tarih kolonundan YALNIZ min/maks. Ceyrek de ornek de gitmez:
    bir tarih kolonunun ne oldugunu anlamak icin araligi yeter."""
    if kp.get("min") is None:
        return {}
    return {"min": str(kp["min"])[:19], "maks": str(kp["max"])[:19]}


def _kategorik_ozet(kp, satir):
    """Kategorik kolondan en sik EN_SIK_ETIKET etiket ve orani.

    ETIKETLER BILEREK GIDIYOR: bir kategorik kolonun ne oldugu ancak
    etiketlerinden anlasilir ("A/B/C" ile "EVET/HAYIR" ayni istatistigi
    verir, ayni anlami vermez). Giden sey yine de ham satir degil,
    sayimdan turetilmis bir dagilimdir.

    Kimlik benzeri, kisisel veri ya da uzun metin tasiyan kolonda HIC
    etiket gonderilmez. Bu kapi sozluk.ornek_guvenli_profil'de (ayni
    kurallar sozluk._ornek_guvenli_mi'de) duruyor."""
    guvenli, neden = sozluk_mod.ornek_guvenli_profil(kp, satir)
    if not guvenli:
        return {"not": neden}
    toplam = max(int(satir or 0), 1)
    return {"en_sik": [[_etiket_kirp(etiket), round(float(adet) / toplam, 4)]
                       for etiket, adet in
                       (kp.get("ust_degerler") or [])[:EN_SIK_ETIKET]]}


def _oneri_profilleri(prof, kolonlar, profil):
    """Dil modeline gidecek TURETILMIS ozetler - veri seti profilinden.

    Tablo OKUNMAZ; her sayi profil isinin tam tablodan cikardigi kesin
    sayilardir. Yalnizca sozlukte tanimi bulunmayan kolonlar icin."""
    ozet = _kolon_ozet_haritasi(profil)
    kol = profil_mod.kolonlar(prof)
    satir = int((prof or {}).get("satir") or 0)
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

        kp = kol.get(ad)
        if kp is not None:
            if tip == "sayısal":
                kayit.update(_sayisal_ozet(kp))
            elif tip == "tarih":
                kayit.update(_tarih_ozet(kp))
            else:
                kayit.update(_kategorik_ozet(kp, satir))

        kayit["dagilim"] = _dagilim_metni(kayit)
        kayitlar.append(kayit)
    return kayitlar


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


def _tanimsiz_oneriler(durum, kolonlar, profil, prof=None):
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

    profiller = _oneri_profilleri(prof if prof is not None else _profil(durum),
                                  kolonlar, profil)

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
        # ROZET YOK (kullanici bildirimi: "girdiler doğrulandı ne alaka,
        # iki tik veriyor"). Girdiler bir onceki adimda onaylandi; bu
        # kart bir karar karti, blok durumu zaten "Yanıtınız Bekleniyor"
        # / "Tamamlandı" diyor.
        "rozet": "",
        "ozet": [
            {"etiket": "Baz Veri Seti", "deger": durum.get("veri_seti") or "",
             "alt": ["%s satır · %s kolon"
                     % (_sayi(profil.get("satir") or 0), _sayi(kolon)),
                     tip_alt]},
            {"etiket": "Baz Sözlük", "deger": durum.get("sozluk") or "",
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
    # Geri donuste ONCEKI KARARLAR: kullanicinin yazdigi aciklama ve
    # ekle/haric secimi kartta aynen geri gelir (bkz. sozluk_tanim_uygula).
    kararlar = durum.get("_tanim_kararlari") or {}
    tek_kume = {str(k) for k in (durum.get("_tek_degerli") or [])}
    satirlar = []
    for ad in gosterilen:
        oneri = (oneriler or {}).get(ad) or {}
        aciklama = str(oneri.get("aciklama") or "")
        rol = zorunlu_rol.get(ad)
        onceki = kararlar.get(ad) if isinstance(kararlar.get(ad), dict) else None
        # KATEGORI ALANI YOK. Kart dort kolona iniyor:
        # Degisken | Tip | Aciklama | Sozluge Ekle.
        satir = {
            "kolon": ad,
            "tip": (ozet.get(ad) or {}).get("tip") or "",
            # ZORUNLU SATIR "ekle" ile acilir ve isaret kaldirilamaz:
            # hedef, kimlik ve donem kolonu sozlukte tanimsiz kalamaz.
            "islem": "ekle" if rol else (
                (onceki or {}).get("islem") or "haric"),
            "oneri": aciklama,
            "oneri_kaynak": "llm" if aciklama else "yok",
        }
        if not rol and ad in tek_kume:
            # TEK DEGERLI: sozluge eklenemez, surec disi kalir (kilitli).
            satir["islem"] = "haric"
            satir["kilitli"] = True
            satir["kilit_sebebi"] = TEK_DEGER_SEBEBI
        if onceki and onceki.get("aciklama"):
            # Kullanicinin daha once onayladigi metin; model onerisi bunu
            # EZMEZ. Oneri ile ayniysa satir "oneri", degilse "degisti".
            satir["onceki"] = str(onceki["aciklama"])
            satir["onceki_oneri"] = str(onceki.get("oneri") or "")
        if rol:
            satir["zorunlu"] = True
            satir["rol"] = rol
        satirlar.append(satir)

    # Zorunlu satirlar EN USTTE: kullanici onlari gormeden ilerleyemez.
    satirlar.sort(key=lambda s: 0 if s.get("zorunlu") else 1)

    alan["tanimsiz"] = {
        "baslik": "Sözlükte Tanımı Bulunmayan Kolonlar",
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


def _kapsami_cikar(durum, taze=False):
    """Veri seti profilini (PySpark isi) ve sozlugu okur, tanimsiz kolon
    listesini kurar. taze=True: profil isi veri seti icin YENIDEN calisir
    (veri seti secimi onaylandiginda: tablo o arada degismis olabilir).

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
    prof = _profil(durum, taze=taze)
    # sozluk_orijinal_oku: Mod B'de uretilen sozluk dataset'e yazilamazsa
    # CSV yedeginden okunur (durum["sozluk"] None kalir).
    return _kapsam_hesapla(durum, prof, sozluk_orijinal_oku(durum))


def _kapsam_hesapla(durum, prof, sz):
    """Profil + kapsam + tanimsiz liste. Doner: (veri seti profili, p)."""
    ad_kolonu = sozluk_calisma.degisken_kolonu_bul(sz)
    sozluk_ad = set(sz[ad_kolonu].astype(str).str.strip()) if ad_kolonu is not None else set()
    # Calisma kopyasi, yalnizca buyuk/kucuk harf ya da Turkce karakterle
    # farkli yazilmis adlari veri setindeki yazima ceviriyor (aciklama
    # korunur); kapsam da ayni esleşmeyi saymali.
    sozluk_normal = {sozluk_calisma._normalize_ad(a) for a in sozluk_ad}

    adlar = [k["ad"] for k in prof.get("kolonlar") or []]
    aciklamasiz = [c for c in adlar if c not in sozluk_ad
                   and sozluk_calisma._normalize_ad(c) not in sozluk_normal]
    eslesen = len(adlar) - len(aciklamasiz)

    p = _temel_profil(durum, prof)
    p.update({
        "sozluk_satir": int(sz.shape[0]), "eslesen": eslesen,
        "kapsam": round(100.0 * eslesen / max(len(adlar), 1), 1),
    })
    # Profilin HANGI girdilerden cikarildigi: sozluk_tanim adimi ayni
    # veri seti ve sozluk icin profili yeniden CIKARMAZ, yalnizca tabloyu
    # okur. Eskiden kapsam iki kez hesaplaniyordu (kurulum + sozluk_tanim)
    # ve 10.000 x 1.042'lik tablo iki kez taraniyordu.
    p["_kaynak"] = [durum.get("veri_seti"), durum.get("sozluk")]
    durum["profil"] = p
    durum["_aciklamasiz"] = aciklamasiz
    # ORIJINAL sozlukte tanimsiz olanlar. _aciklamasiz, sozluk tanimlari
    # uygulaninca eklenenleri dusuyor; geri donuste kart bu ilk listeyle
    # ve kullanicinin onceki kararlariyla yeniden kuruluyor.
    durum["_aciklamasiz_ilk"] = list(aciklamasiz)
    return prof, p


def _tanim_listesi(durum):
    """Sozluk tanimlari kartinin kolonlari: ORIJINAL sozlukte tanimsiz
    olanlarin tamami (sonradan eklenenler dahil).

    Kullanici bildirimi: geri donunce kart "%99,8: 1.040 / 1.042 kolon
    tanımlı" diyor ama tanimsiz iki kolonu LISTELEMIYORDU; cunku liste
    onceki onaydan sonra "hala tanimsiz olanlar"a inmisti. Artik ilk
    liste ve onceki kararlar (eklendi + aciklamasi / haric) geri gelir."""
    ilk = durum.get("_aciklamasiz_ilk")
    if isinstance(ilk, list):
        return [str(k) for k in ilk]
    # Eski calisma: ilk liste yok, eklenenlerden yeniden kurulur.
    kalan = [str(k) for k in (durum.get("_aciklamasiz") or [])]
    eklenen = [str(k) for k in (durum.get("_sozluge_eklenen") or [])]
    birlesik = list(dict.fromkeys(eklenen + kalan))
    sira = [str(o.get("ad")) for o in ((durum.get("profil") or {})
                                       .get("kolon_ozet") or [])
            if isinstance(o, dict)]
    if sira:
        yer = {ad: i for i, ad in enumerate(sira)}
        birlesik.sort(key=lambda a: yer.get(a, len(yer)))
    return birlesik


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
        # Kapsam `kurulum` adiminda cikarildi; tekil sayilari ve oneri
        # ozetleri veri seti profilinden (tablo okunmaz).
        prof, p = _profil(durum), durum["profil"]
    else:
        prof, p = _kapsami_cikar(durum)
    aciklamasiz = _tanim_listesi(durum)

    try:
        _tek_degerli_hesapla(durum, prof)
    except Exception:
        pass
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
        _tekil_tamamla(prof, gosterilen, p)
        # Dil modeli cagrisi YALNIZCA tanimsiz kolonlar icin; ozetler veri
        # seti profilinden.
        profiller = _oneri_profilleri(prof, gosterilen, p)
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
    tek = {str(k) for k in (durum.get("_tek_degerli") or [])}
    karar = durum.pop("_dogrulama_karari", None)
    if not isinstance(karar, dict):
        return sorted(izinli), []

    ekle, gorulen = [], set()
    for satir in (karar.get("ekle") or []):
        if not isinstance(satir, dict):
            continue
        ad = str(satir.get("kolon") or "").strip()
        if ad not in izinli or ad in gorulen or ad in tek:
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
    adaylarini buradan okuyor) ve sozluk calisma kopyasi kuruluyor.
    Profil TAZE cikarilir: veri seti secimi onaylandi, tablo bir onceki
    profilden bu yana degismis olabilir."""
    _kapsami_cikar(durum, taze=True)
    # Calisma kopyasi sozluk baglanir baglanmaz cikarilir: satir_ekle
    # yalnizca kopyaya yazar, kopya yoksa yazacak yer yoktur.
    return _calisma_kopyasi_kur(durum).strip()


def sozluk_tanim_uygula(durum):
    tanimsiz = _tanim_listesi(durum)
    if not isinstance(durum.get("_aciklamasiz_ilk"), list):
        durum["_aciklamasiz_ilk"] = list(tanimsiz)
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
    # KARARLAR SAKLANIR: geri donuste kart bunlarla yeniden kurulur.
    _oneri_harita = durum.get("_tanimsiz_oneri") or {}
    durum["_tanim_kararlari"] = dict(
        [(k, {"islem": "haric"}) for k in haric]
        + [(x["kolon"], {"islem": "ekle", "aciklama": x["aciklama"],
                         "oneri": ((_oneri_harita.get(x["kolon"]) or {})
                                   .get("aciklama") or "")})
           for x in ekle])

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
    # profil_kural.donem_adayi_mi). Aday yoksa liste bos kalir ve nedeni yazilir;
    # tum kolonlara DUSULMEZ - kimlik ya da hedefin donem secilmesi
    # zamansal bolmeyi sessizce bozardi.
    donem_liste = _ekle(donem_aday, m.get("donem"))
    donem_maddeler = []
    if donem_aday:
        donem_not = ""
    elif p.get("donem_hata"):
        donem_not = ("Dönem kolonu aranamadı: tablo okunamadı. Sayfayı "
                     "yenileyince yeniden denenir.")
        donem_maddeler = [str(p["donem_hata"])]
    else:
        donem_not = "Dönem kolonu bulunamadı."
        donem_maddeler = list(p.get("donem_nedenler") or [])

    hedef_not = ("" if hedef_aday else
                 "Veri setinde 0/1 değerli kolon bulunamadı; tüm kolonlar "
                 "listeleniyor.")
    kimlik_not = ("" if kimlik_aday else
                  "Veri setinde tekrarsız kolon bulunamadı; tüm kolonlar "
                  "listeleniyor.")

    durum["_secim_alani"] = {
        "tip": "form",
        "baslik": "Modelleme Tanımları",
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
            {"ad": "target", "etiket": "Hedef Değişken", "kaynak": "kolon",
             "deger": m.get("target") or "", "secenekler": hedef_liste,
             "ipucu": "Yalnızca 0/1 değerli kolonlar", "not": hedef_not},
            {"ad": "id", "etiket": "Kimlik Kolonu", "kaynak": "kolon",
             "deger": m.get("id") or "", "secenekler": kimlik_liste,
             "ipucu": "Yalnızca tekrarsız kolonlar", "not": kimlik_not},
            {"ad": "donem", "etiket": "Dönem Kolonu (Opsiyonel)",
             "kaynak": "kolon", "zorunlu": False,
             "deger": m.get("donem") or "", "secenekler": donem_liste,
             "ipucu": "Dönem bilgisi taşıyan kolonlar: 202501 (sayı, metin ya da kategori), 2025-01, tarih",
             "not": donem_not, "not_maddeler": donem_maddeler},
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

def _hedef_sayilari(kp):
    """Hedef kolonu icin (sayisal tekil deger sayisi, pozitif satir sayisi).

    Eski yol: y = pd.to_numeric(df[hedef]); y.nunique(), (y > 0).sum().
    Sayisal kolonda bu sayilar profilde zaten var. Metin kolonda deger
    listesinden (en fazla 50 seviye) sayiya cevrilerek bulunur; listesi
    olmayan (cok seviyeli) metin kolonu iki sinifli olamaz."""
    if not kp:
        return 0, 0
    if kp.get("tur") in profil_kural.SAYISAL_TURLER:
        return int(kp.get("tekil") or 0), int(kp.get("pozitif") or 0)
    liste = kp.get("degerler")
    if liste is None:
        return int(kp.get("tekil") or 0), 0
    sayi = pd.to_numeric(pd.Series([v for v, _n in liste], dtype=object),
                         errors="coerce")
    tekil = int(sayi.dropna().nunique())
    pozitif = int(sum(n for (v, n), x in zip(liste, sayi.tolist())
                      if x == x and x > 0))
    return tekil, pozitif


def _donem_listesi_profilden(kp):
    """Donem kolonunun normallestirilmis TEKIL degerleri (tam tablo).

    Donem adayinda profil isi listeyi zaten cikariyor. Aday listesi bos
    oldugu icin aday disi bir kolon secildiyse (kural o zaman
    uygulanmiyor) 50 seviyeye kadar deger listesinden kurulur; daha cok
    seviyeli ve donem bicimi tasimayan bir kolon donem olamaz."""
    if kp.get("donem_degerleri") is not None:
        return list(kp["donem_degerleri"])
    if kp.get("degerler") is not None:
        return profil_kural.donem_degerleri(kp["tur"],
                                            [v for v, _n in kp["degerler"]])
    raise AdimHatasi(
        "%s dönem kolonu olarak kullanılamaz: %s farklı değer taşıyor ve "
        "değerleri dönem biçiminde değil (202501, 2025-01 ya da tarih)."
        % (kp.get("ad"), _sayi(kp.get("tekil") or 0)))


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
    prof = _profil(durum)
    kol = profil_mod.kolonlar(prof)
    p = durum.get("profil") or {}

    # HEDEF: tekil deger sayisi ve pozitif orani PROFILDEN (tam tablo,
    # kesin). pd.to_numeric(hedef) karsiligi: sayisal kolonda profilin
    # kendi sayilari; metin kolonda deger listesi sayiya cevrilir.
    tekil, pozitif = _hedef_sayilari(kol.get(m["target"]))
    satir = int(prof.get("satir") or 0)
    if tekil <= 2:
        oran = 100.0 * float(pozitif) / satir if satir else 0.0
        p["hedef_tip"] = "binary"
        # Event rate hedef_ozet metninin ICINE gomulu; panelin metni geri
        # ayristirmasi gerekmesin diye AYRI sayisal alan olarak da yazilir.
        p["event_rate"] = round(oran, 2)
        # Oranin yaninda sayilar da (kullanici karari): "%3,21 pozitif
        # (12.345 / 384.567)".
        p["hedef_pozitif"] = int(pozitif)
        p["hedef_ozet"] = ("İki sınıflı (0/1) · %%%s pozitif (%s / %s)"
                           % (_ond(oran, 2), _sayi(pozitif), _sayi(satir)))
    else:
        p["hedef_tip"] = "surekli"
        p["event_rate"] = None
        p["hedef_ozet"] = "Sürekli · %s farklı değer" % _sayi(tekil)

    # Donem araligi: VERI sekmesi min/maks donemi buradan okur.
    p.pop("donem_min", None)
    p.pop("donem_maks", None)
    p.pop("donem_adet", None)
    _kimlik_duplicate(durum, prof, p)
    durum["profil"] = p

    # VERI SETINDE HAZIR DURAN BOLME. Tablo zaten okunmusken araniyor;
    # ayri bir okuma maliyeti yok. Bulunursa bolme kartinda ucuncu bir
    # secenek olarak cikar - dayatma degil, secenek (kullanici karari:
    # "yine seçime göre geri dönmek istersem diye").
    durum.pop("_hazir_bolme", None)
    try:
        hazir = hazir_bolme_bul_profil(prof)
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
    if donem and donem in kol:
        # Bolmeyle AYNI normallestirme ve ZAMAN sirasi (bkz.
        # birlestirme.donem_degeri / donem_sirala). Degerler profilden.
        donemler = donem_sirala(_donem_listesi_profilden(kol[donem]))
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


TEK_DEGER_SEBEBI = ("Tüm veri setinde tek bir değer taşıyor; modele bilgi "
                    "katmaz, süreç dışı kalmak zorunda.")


def _tek_degerli_hesapla(durum, prof=None):
    """TUM VERI SETINDE tek degerli kolonlar; durum["_tek_degerli"]'ye yazar.

    Bos hucre ayri deger: nunique(dropna=False). Hedef / kimlik / donem
    rolundeki kolonlar listeye girmez (kendi kurallari var). Ayni veri
    seti icin bir kez hesaplanir. Doner: liste."""
    kaynak = [durum.get("veri_seti"), durum.get("sozluk")]
    if durum.get("_tek_degerli_kaynak") == kaynak \
            and isinstance(durum.get("_tek_degerli"), list):
        return durum["_tek_degerli"]
    if prof is None:
        prof = _profil(durum)
    korunan = {str(v) for v in (durum.get("meta") or {}).values() if v}
    # tekil_bos_dahil = nunique(dropna=False): bos hucre ayri deger.
    tek = sorted(str(k["ad"]) for k in prof.get("kolonlar") or []
                 if int(k["tekil_bos_dahil"]) <= 1 and str(k["ad"]) not in korunan)
    durum["_tek_degerli"] = tek
    durum["_tek_degerli_kaynak"] = kaynak
    return tek


def tek_degerlileri_isaretle(durum):
    """TEK DEGERLI kolonlari SUREC DISI isaretler (kullanici karari:
    "değişken kontrolünde süreç dışı otomatik olarak tek değer içerenleri
    seçmeli").

    BOS HUCRE AYRI BIR DEGERDIR: herhangi bir tek deger + bos hucre
    ("A" ve bos, 1 ve bos ...) iki deger sayilir, kolon tek degerli
    DEGILDIR (kullanici karari). Tek degerli = butun satirlarda ayni
    deger ve hic bos yok, ya da butun satirlar bos. Bir bayrak kolonu (1 = var, bos = yok) tam da boyledir ve
    modele bilgi tasir. Bu yuzden nunique(dropna=False).

    tanimsiz_kolonlari_isaretle gibi BIR KEZ calisir ve kilitli DEGILDIR:
    kullanici kutuyu kaldirirsa karar onundur, sonraki cizimde geri
    isaretlenmez. Hedef / kimlik / donem otomatik dusurulmez.

    Doner: yeni isaretlenen kolon adlari."""
    # KILITLI (kullanici karari): her cizimde uygulanir; kullanici kutuyu
    # kaldiramaz. Onceki surumdeki "bir kez, kaldirilabilir" kurali
    # tek degerli PERIOD'un surece alinabilmesine yol aciyordu.
    try:
        tek = _tek_degerli_hesapla(durum)
    except Exception:
        return []          # okunamadi: bir sonraki cizimde yeniden denenir
    mevcut = {str(k) for k in (durum.get("haric_kolonlar") or [])}
    yeni = [a for a in tek if a not in mevcut]
    if yeni:
        durum["haric_kolonlar"] = sorted(mevcut | set(yeni))
    return yeni


TIP_ONERI_SURUMU = 3
# Sayisal bir kolonun KOD oldugunu (kategorik modellenmesi gerektigini)
# gosteren ad parcalari. Yalnizca ad + az sayida tam sayi deger birlikte
# varsa kategorik onerilir; ad tek basina yetmez.
_KOD_AD_PARCALARI = {"KOD", "KODU", "CODE", "CD", "TIP", "TIPI", "TYPE",
                     "SEGMENT", "SEG", "SINIF", "CLASS", "GRUP", "GROUP",
                     "KATEGORI", "CAT", "IL", "ILCE", "SUBE", "BRANCH",
                     "SEKTOR", "SECTOR", "MESLEK", "STATU", "STATUS"}


def _ad_parcalari(ad):
    return {p for p in re.split(r"[^0-9A-Za-zÇĞİÖŞÜçğıöşü]+", str(ad).upper()) if p}


def _tip_onerisi(kp, kaynak_tip, ad):
    """Tek kolon icin (kod, sebep) ya da (None, None).

    KURALLAR (sirasiyla, ilk tutan kazanir):
      1. Sayisal ya da metin, tum degerler YYYYAA  -> donem_ym6
         (tip tarih, yazim korunur). Tekil sayisi 600'u (50 yil) asan
         kolon donem sayilmaz.
      2. Tum degerler YYYYAAGG                     -> donem_ymd8
      3. Metin, tum degerler sayi                  -> sayisal (virgul
         iceren degerde ondalik virgul yolu once denenir). Basinda sifir
         olan deger varsa KOD sayilir (00123), donusturulmez.
      4. Metin, tum degerler tarih (YYYY-AA-GG / GG.AA.YYYY) -> tarih
      5. Sayisal, adi kod/tip/segment gibi ve tam sayi, en fazla 50
         farkli deger                              -> kategorik
    Her kural TAM KOLONLA denetlenir: kp veri seti profilinin kolon
    kaydi; donusumlerin uygunlugu profil isinde tum tablodan kesin
    hesaplandi (tip_donusum.denetle ile ayni kural)."""
    if not kp or not kp.get("dolu"):
        return None, None
    tekil = int(kp.get("tekil") or 0)

    def tutar(kod):
        return bool(((kp.get("donusum") or {}).get(kod) or {}).get("uygun"))

    if kaynak_tip in ("sayısal", "kategorik") and 2 <= tekil <= 600 \
            and tutar("donem_ym6"):
        return "donem_ym6", "Değerlerin tamamı YYYYAA (yıl-ay) biçiminde"
    if kaynak_tip in ("sayısal", "kategorik") and tekil >= 2 \
            and tutar("donem_ymd8"):
        return "donem_ymd8", "Değerlerin tamamı YYYYAAGG (tarih) biçiminde"

    if kaynak_tip == "kategorik":
        kod_gibi = bool(kp.get("kod_gibi"))
        if not kod_gibi:
            virgul_var = bool(kp.get("virgul_var"))
            sira = (("sayisal_virgul", "sayisal_nokta") if virgul_var
                    else ("sayisal_nokta", "sayisal_virgul"))
            for kod in sira:
                if tutar(kod):
                    return kod, "Metin olarak okunmuş ama değerlerin tamamı sayı"
        for kod in ("tarih_ymd", "tarih_dmy"):
            if tutar(kod):
                return kod, "Metin olarak okunmuş ama değerlerin tamamı tarih"

    if kaynak_tip == "sayısal" and (_ad_parcalari(ad) & _KOD_AD_PARCALARI) \
            and 2 <= tekil <= tip_donusum.KATEGORI_SEVIYE_SINIRI:
        tam = bool(kp.get("hepsi_tam"))
        if tam and tutar("kategorik_metin"):
            return ("kategorik_metin",
                    "Adı kod/tip/segment bildiriyor ve %d farklı tam sayı değer "
                    "var; sayı olarak değil kategori olarak modellenmeli" % tekil)
    return None, None


def tip_onerilerini_uygula(durum):
    """TIP ONERILERI - TUM VERI SETI (kullanici karari: "değişken
    kontrolünde kendisi öneride bulunsun; hangi kolonu nasıl değiştirmek
    gerekiyorsa"). Kurallar: _tip_onerisi. Ornek: 202501 tutan PERIOD
    icin tarih (donem) onerilir, deger 202501 kalir.

    Oneriler SECILI gelir ve kartta kirmizi satirla gosterilir;
    kullanici degistirirse satir sari olur. Oneri bir kez uygulanir
    (surum isaretiyle): kullanici "Değişmesin"e cekerse geri gelmez.
    Surec disi, hedef ve kimlik kolonlarina dokunulmaz; donem kolonuna
    yalnizca tarih onerilir.

    Oneri kurala dayanir, dil modeline degil: tipin cevabi verinin
    kendisinde; modelin tahmini yalnizca yanilma payi ekler.

    YALNIZCA DONEM KOLONU (kullanici karari: "tip değişikliği önerisi
    artık burada değil sadece sfa kısmında yapılabiliyor olmalı çünkü
    değişkenlerin bütün durumuna orada karar vereceğiz"). Model
    degiskenlerinin tip karari SFA'da (sfa_karar.tip_onerisi). Donem
    kolonu model degiskeni degil, bolmenin anahtari; onun tarih (donem)
    isareti burada kalir. Surum 3'e gecen calismada daha once model
    degiskenlerine yazilmis tip secimleri temizlenir.
    Doner: {kolon: kod}."""
    if durum.get("_tip_oneri_surum") == TIP_ONERI_SURUMU:
        return {}
    haric = {str(k) for k in (durum.get("haric_kolonlar") or [])}
    secilen = {k: v for k, v in (durum.get("tip_donusum") or {}).items()
               if _tip_rolu(durum, str(k)) == "donem"}
    if secilen != dict(durum.get("tip_donusum") or {}):
        durum["tip_donusum"] = secilen
        _tip_ozetini_tazele(durum)
        durum["_tip_oneri"] = {k: v for k, v in (durum.get("_tip_oneri") or {}).items()
                               if k in secilen}
    try:
        kol = profil_mod.kolonlar(_profil(durum))
    except Exception:
        return {}           # okunamadi: sonraki cizimde yeniden denenir
    oneriler, sebepler = {}, {}
    for ad, kp in kol.items():
        if ad in haric or ad in secilen:
            continue
        rol = _tip_rolu(durum, ad)
        if rol != "donem":
            continue
        kaynak_tip = _kaynak_tipi(durum, ad) or ""
        if kaynak_tip not in ("sayısal", "kategorik"):
            continue
        try:
            kod, sebep = _tip_onerisi(kp, kaynak_tip, ad)
        except Exception:
            kod, sebep = None, None
        if not kod:
            continue
        if rol == "donem" and tip_donusum.hedef_tip(kod) != "tarih":
            continue
        oneriler[ad] = kod
        sebepler[ad] = sebep
    if oneriler:
        secilen.update(oneriler)
        durum["tip_donusum"] = secilen
        _tip_ozetini_tazele(durum)
    # Onceki surumun onerileri korunur (kart onlari da kirmizi gosterir).
    eski = dict(durum.get("_tip_oneri") or {})
    eski.update(oneriler)
    durum["_tip_oneri"] = eski
    eski_s = dict(durum.get("_tip_oneri_sebep") or {})
    eski_s.update(sebepler)
    durum["_tip_oneri_sebep"] = eski_s
    durum["_tip_oneri_surum"] = TIP_ONERI_SURUMU
    return oneriler


def teyit_ozeti(durum):
    """Kartin tek satirlik ozeti: '1.042 değişken · 2 süreç dışı · ...'.

    ACIK ISIM: kart disindan da cagriliyor. Sag panelde bir kolon surec
    disina alininca (/haric_kolonlar) kartin sayilari degisiyor; uc bu
    fonksiyonla tazesini donuyor ki kart eski sayiyi gostermesin."""
    degisken, haric, tanimli = _teyit_sayilari(durum)
    return "%s değişken · %s süreç dışı · %s tanımlı" % (
        _sayi(degisken), _sayi(haric), _sayi(tanimli))


# Tip seceneklerinin TAM KOLONLA hesaplanmis hali; kart her tazelendiginde
# (her kutu isaretlemesinde) 1.000 kolon yeniden taranmasin.
# Anahtar: (veri_seti, kolon, kaynak_tip).


def _tip_secenekleri(durum, kolonlar, ad, kaynak_tip):
    """Kolonun UYGULANABILIR donusumleri (tam kolon, rol kilidi dusulmus).

    Uygunluk veri seti profilinden (tip_donusum.secenekler ile ayni
    liste ve sira; yalnizca uygun olanlar)."""
    donusum = (kolonlar.get(ad) or {}).get("donusum") or {}
    cikti = []
    for kod in tip_donusum.ADAYLAR.get(kaynak_tip, []):
        if not (donusum.get(kod) or {}).get("uygun"):
            continue
        if _tip_kilidi(durum, ad, kod):
            continue
        cikti.append({"kod": kod, "hedef": tip_donusum.DONUSUMLER[kod]["hedef"],
                      "etiket": tip_donusum.DONUSUMLER[kod]["etiket"],
                      "uygun": True, "sebep": ""})
    return cikti


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
    disi = {ad} if ad else set()
    # TEK DEGERLI KOLONLAR da zorunlu disi (kullanici karari: "period tek
    # değer içermesine rağmen hâlâ içeri alabiliyorum"). Liste TUM VERI
    # SETI uzerinden hesaplaniyor (bkz. _tek_degerli_hesapla); bolme
    # henuz yapilmadi, parca bazli bakmak anlamsiz.
    disi |= {str(k) for k in ((durum or {}).get("_tek_degerli") or [])}
    return disi


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
    tek_degerli = set(durum.get("_tek_degerli") or [])
    tip_oneri = durum.get("_tip_oneri") or {}
    # Sozluk tanimlari adiminda MODEL ONERISIYLE eklenen tanimlar.
    tanim_oneri = {k: str(v.get("oneri") or "")
                   for k, v in (durum.get("_tanim_kararlari") or {}).items()
                   if isinstance(v, dict) and v.get("islem") == "ekle"
                   and v.get("oneri")}
    secilen = durum.get("tip_donusum") or {}
    # TAM TABLO (kullanici karari): secenekler ornekle degil tam kolonla
    # hesaplaniyor; uygulanamayan secenek listede HIC gorunmuyor.
    try:
        tam = profil_mod.kolonlar(_profil(durum))
    except Exception:
        tam = None
    # Orijinal sozluk tanimlari: kullanici bir tanimi degistirdiyse satir
    # sari gosterilir (bkz. app.js oneriVurgusu).
    try:
        orijinal = _tanim_haritasi(sozluk_orijinal_oku(durum))
    except Exception:
        orijinal = {}
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
        if tam is not None and ad in tam:
            # Teklifler daima ORIJINAL tip uzerinden uretilir: secim
            # henuz veriye islenmedi, kolon hala kaynak tipinde duruyor.
            donusumler = _tip_secenekleri(durum, tam, ad, kaynak_tip)
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
                            or _donem_tek_deger_mi(durum, ad)
                            or ad in tek_degerli,
            "disi_kilit_sebebi": (
                DONEM_TEK_DEGER_SEBEBI if _donem_tek_deger_mi(durum, ad)
                else TEK_DEGER_SEBEBI if ad in tek_degerli
                else ROL_KILIT_SEBEBI.get(_tip_rolu(durum, ad), "")),
            # Neden isaretli geldigi (kilitli degil, kaldirilabilir).
            "disi_sebebi": "",
            # SISTEM ONERISI: kart satiri oneriyle ayniysa kirmizi,
            # kullanici degistirdiyse sari gosterir.
            "oneri_tip": tip_oneri.get(ad, ""),
            "oneri_tip_sebebi": (durum.get("_tip_oneri_sebep") or {}).get(ad, ""),
            "oneri_tanim": tanim_oneri.get(ad, ""),
            "tanim_orijinal": (orijinal.get(ad.upper()) or ("", ""))[0],
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
#   Sohbetteki karar tablosu DORT kolon (Degisken, Tip, Sozluk Tanimi,
#   Surec Disi; tip degisikligi ve null orani SFA'da goruluyor); sag panel yalnizca UC kolon gosteriyor
#   (orada karar yok, aciklama var). Indirilen dosya da bakilan yerle
#   ayni olmali; aksi halde "ekranda gordugum tablo bu degil" denir.
TEYIT_EXCEL_ADI = "degisken_listesi.xlsx"
SOZLUK_EXCEL_ADI = "degisken_sozlugu.xlsx"

TEYIT_EXCEL_KOLONLARI = ["Değişken", "Tip", "Sözlük Tanımı", "Süreç Dışı"]
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
    govde = [[s["kolon"], s["tip"], s["tanim"], _DISI_METNI[bool(s.get("disi"))]]
             for s in satirlar]
    return list(TEYIT_EXCEL_KOLONLARI), govde, ()


def teyit_excel(durum, genis=True):
    """Degisken listesini .xlsx olarak uretir; bayt dizisi doner.

    genis=True  : sohbetteki karar tablosunun aynisi (dort kolon)
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

        PROJE_HAFIZASI/v3/AMP_SOZLUK.parquet   (Flow'da dataset yoksa)
        PROJE_HAFIZASI/v3/sozluk_calisma.parquet
        PROJE_HAFIZASI/v3/profil.json

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
    return "/%s/%s.parquet" % (amp_klasor_adi(durum), ad)


def amp_ciktilarini_yaz(durum):
    """AMP_VERISETI ve AMP_SOZLUK'u YAZAR. Doner: {"veri":..., "sozluk":...}

    Her deger: {"ad", "dataset", "dosya"} - "dataset" doluysa akista o
    adla bir veri seti var ve oraya yazildi; degilse "dosya" PROJE
    HAFIZASI icindeki Parquet yolu (yalnizca sozluk ve "yerel" motor).

    SPARK (kullanici karari: veri 135 milyon satir): AMP_VERISETI'ni
    kumede compute_AMP_VERISETI recipe'i yazar (amp_spark); recipe'i ve
    veri setini webapp kurar. Sonraki fazlar bu veri setini okur.

    NE ZAMAN: sozluk teyidi KAYDEDILDIGINDE. O an tablo son halini
    aliyor - tip donusumleri secildi, tanimlar yazildi, surec disi
    karari verildi. Daha once yazmak yarim bir tablo kaydetmek olurdu.

    KAYNAK TABLOYA DOKUNULMAZ: AMP_VERISETI platformun KENDI kopyasi;
    Mod A ve B'de kullanicinin orijinal tablosu oldugu gibi kalir."""
    sonuc = {}
    oz = amp_mod.amp_yaz(durum, _profil(durum))
    onbellek_temizle()
    sonuc["veri"] = _amp_veri_kaydi(oz)
    # Tablo _SPLIT'siz yeniden yazildi: onceki bolme artik gecersiz.
    b = durum.get("bolme") or {}
    for k in BOLME_KALICI_ALANLARI:
        b.pop(k, None)
    durum["bolme"] = b
    return _amp_sozluk_ve_kayit(durum, sonuc)


def _amp_veri_kaydi(oz):
    """amp_yaz / amp_bolme_yaz sonucundan durum["amp_cikti"]["veri"]."""
    return {"ad": AMP_VERI_ADI, "dataset": oz.get("dataset"),
            "dosya": oz.get("dosya"), "taban": oz.get("taban"),
            "motor": oz.get("motor"),
            "satir": int(oz.get("satir") or 0), "kolon": int(oz.get("kolon") or 0),
            "dusen_kolon": len(oz.get("dusen") or [])}


def _amp_sozluk_ve_kayit(durum, sonuc):
    """AMP_SOZLUK'u CALISMA KLASORUNE yazar ve durumu kaydeder.

    Bundan sonra sozlugun TEK kaynagi AMP_SOZLUK'tur (kullanici karari):
    okuma da yazma da (sag paneldeki tanim / kategori duzenlemeleri) bu
    dosyaya gider (bkz. sozluk_calisma.kopya_yolu). Kategori de tasinir."""
    try:
        _kolonlar, satirlar, _yuzde = _excel_satirlari(durum, True)
        tablo = pd.DataFrame(satirlar, columns=list(AMP_SOZLUK_KOLONLARI[:6]))
        from fe_agent import akis_panel
        harita, _kat, _adet, _kopya = akis_panel._sozluk_kayitlari(durum)
        tablo["KATEGORI"] = [
            ("" if (harita.get(str(k)) or (None, ""))[1] == sozluk_calisma.KATEGORISIZ
             else (harita.get(str(k)) or (None, ""))[1]) for k in tablo["DEGISKEN"]]
        tablo = tablo[list(AMP_SOZLUK_KOLONLARI)]
    except Exception as e:
        sonuc["sozluk"] = {"ad": AMP_SOZLUK_ADI, "dataset": None,
                           "dosya": None, "hata": str(e)[:120]}
    else:
        yol = sozluk_calisma.amp_sozluk_yaz(durum, tablo)
        sonuc["sozluk"] = {"ad": AMP_SOZLUK_ADI, "dataset": None,
                           "dosya": yol, "satir": int(len(tablo))}
        if not yol:
            sonuc["sozluk"]["hata"] = "çalışma klasörüne yazılamadı"

    sonuc["klasor"] = amp_klasor_adi(durum)
    durum["amp_cikti"] = sonuc
    return sonuc


# Teyitten SONRA uretilen durum alanlari: AMP silinince hepsi gecersiz.
_AMP_SONRASI = ("sfa", "stabilite", "baz", "ogrenilen_donusum", "plan",
                "hipotez", "uretilen", "kod_bloklari", "kalite", "secim",
                "secim_tablo", "model", "katalog")


def _amp_klasoru():
    from fe_agent.akis_durum import _folder
    return _folder()


def amp_gecersiz_kil(durum):
    """Degisken Kontrolu'ne (teyit) ya da oncesine donuldu.

    KULLANICI KARARI: "AMP olustuktan sonra AMP_VERISETI'nin oncesine
    gidilmemeli; gidilecekse islemler en bastan yaptirilmali". AMP_VERISETI
    ve AMP_SOZLUK silinir, teyitten sonra uretilen butun sonuclar (bolme,
    profil teshisi, SFA, stabilite, baz set ve sonrasi) sifirlanir. Adimlar
    yeniden onaylandikca AMP yeniden yazilir ve akis oradan devam eder.
    Kullanicinin kaynak tablosuna ve sozlugune dokunulmaz.

    Doner: kullaniciya yazilacak tek satir ("" = silinecek bir sey yoktu)."""
    kayit = (durum.get("amp_cikti") or {}).get("veri") or {}
    if not durum.get("amp_cikti"):
        return ""
    # Dosyalar: pandas yolunda AMP_VERISETI klasorde; AMP_SOZLUK her zaman.
    if kayit.get("dosya"):
        try:
            _amp_klasoru().delete_path(kayit["dosya"])
        except Exception:
            pass
    sozluk_calisma.amp_sozluk_sil(durum.get("_oturum_id"))
    ai = (durum.get("sfa") or {}).get("ai_is")
    if ai:
        try:
            from fe_agent import sfa_karar
            sfa_karar.ai_durdur(ai)
        except Exception:
            pass
    taze = yeni_durum()
    for anahtar in _AMP_SONRASI:
        durum[anahtar] = taze.get(anahtar, {})
    for anahtar in ("amp_cikti", "_aralik_ai", "donusum_plani", "_dusurulecek"):
        durum.pop(anahtar, None)
    p = durum.get("profil") or {}
    for anahtar in ("profil_teshis", "profil_dataset", "eksik_ilk20", "null_ozet"):
        p.pop(anahtar, None)
    b = durum.get("bolme") or {}
    for anahtar in tuple(BOLME_KALICI_ALANLARI) + ("test_donemleri",):
        b.pop(anahtar, None)
    durum["haric_kolonlar"] = [k for k in (durum.get("haric_kolonlar") or [])
                               if k != SPLIT_KOLON]
    try:
        from fe_agent import validasyon
        validasyon.temizle(durum)
    except Exception:
        pass
    onbellek_temizle()
    return ("AMP_VERISETI ve AMP_SOZLUK silindi; bu adımdan sonraki bütün "
            "sonuçlar yeniden oluşturulacak.")


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
        kol = profil_mod.kolonlar(_profil(durum))
    except Exception as e:
        return {"tamam": False,
                "mesaj": "Veri seti profili okunamadı (%s)." % str(e)[:80]}
    if kolon not in kol:
        return {"tamam": False,
                "mesaj": "'%s' kolonu veri setinde yok." % kolon}

    uygun, sebep = _profil_donusum_karari(kol[kolon], kod)
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
    tek = tek_degerlileri_isaretle(durum)
    tip_onerilerini_uygula(durum)
    satirlar, duzenlenebilir = teyit_satirlari(durum)
    notlar = []
    if otomatik:
        notlar.append("Sözlükte açıklaması bulunmayan %s değişken süreç dışı "
                      "olarak işaretlendi; veri setinde kalmasını istediğiniz "
                      "varsa işareti kaldırın." % _sayi(len(otomatik)))
    tek_hepsi = durum.get("_tek_degerli") or []
    if tek_hepsi:
        adlar = ", ".join(str(k) for k in tek_hepsi[:3]) + (
            " ve %s değişken daha" % _sayi(len(tek_hepsi) - 3)
            if len(tek_hepsi) > 3 else "")
        notlar.append("%s tüm veri setinde tek bir değer taşıdığı için modele "
                      "bilgi katmaz; süreç dışı bırakıldı ve kilitlendi."
                      % adlar)
    durum["_secim_alani"] = {
        "tip": "teyit",
        "baslik": ADIM_ADI["teyit"],
        "aciklama": TEYIT_ACIKLAMASI,
        "ozet": teyit_ozeti(durum),
        # Otomatik isaretleme SESSIZ YAPILMAZ: kullanici kartta neden
        # bazi kutularin isaretli geldigini gormeli, yoksa kendisinin
        # isaretledigini sanir ya da fark etmeden kolon kaybeder.
        "otomatik_not": " ".join(notlar),
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
    dusen = int((cikti.get("veri") or {}).get("dusen_kolon") or 0)
    return ("Değişken listesi kaydedildi.\n"
            "  Modelleme tablosu : %s%s\n"
            "  Değişken sözlüğü  : %s"
            % (amp_nerede(cikti.get("veri")),
               (" (süreç dışı %s kolon tabloya yazılmadı)" % _sayi(dusen))
               if dusen else "",
               amp_nerede(cikti.get("sozluk"))))


def _profil_donusum_karari(kp, kod):
    """(uygun, sebep): donusumun bu kolonda uygulanip uygulanamayacagi,
    profilin tam tablodan kesin sonucu. Kolonun kaynak tipine teklif
    edilmeyen bir donusum uygulanamaz."""
    if not tip_donusum.gecerli_kod(kod):
        return False, "tanınmayan dönüşüm (%s)" % kod
    sonuc = (kp.get("donusum") or {}).get(kod)
    if sonuc is None:
        return False, "bu kolon tipi için sunulan bir dönüşüm değil"
    return bool(sonuc.get("uygun")), sonuc.get("sebep") or None


def _tip_secimlerini_dogrula(durum):
    """Secilen tum donusumleri tam veriyle dogrular; takilan varsa
    AdimHatasi atar. Secim yoksa veri seti OKUNMAZ."""
    secilen = durum.get("tip_donusum") or {}
    if not secilen:
        return
    try:
        kol = profil_mod.kolonlar(_profil(durum))
    except Exception as e:
        raise AdimHatasi(
            "Tip değişiklikleri doğrulanamadı: veri seti profili okunamadı "
            "(%s)." % str(e)[:100])
    atlanan = {}
    for kolon, kod in secilen.items():
        if kolon not in kol:
            atlanan[kolon] = "kolon tabloda yok"
            continue
        uygun, sebep = _profil_donusum_karari(kol[kolon], kod)
        if not uygun:
            atlanan[kolon] = sebep
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
    "Veri üç sete ayrılır: modelin öğrendiği Train (MS), en yeni "
    "dönemlerden ayrılan Validasyon (OOT) ve geliştirme döneminden rastgele "
    "ayrılan Test (OOS). Dönem kolonu yoksa Validasyon (OOT) ayrılamaz. "
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


def _bolme_tarifi(durum, a, b, notlar):
    """Spark recipe'ine giden bolme tarifi (amp_spark.bolme_ekle).

    Kararlar bolme_hazirla ile AYNI kurallarla burada verilir; tablo
    okunmaz. Zamansal bolmenin test donemleri profildeki donem listesinden,
    val ve bosluk donemleri motorda donem basina satir sayisindan cikar."""
    m = durum.get("meta") or {}
    kol = profil_mod.kolonlar(_profil(durum))
    if a["test_tanim"] == "hazir":
        tanim = durum.get("_hazir_bolme")
        if not isinstance(tanim, dict):
            raise AdimHatasi(
                "Veri setinde hazır bölme kullanılacaktı ama bölme kolonu "
                "bulunamadı; \"%s\" adımını yeniden çalıştırın."
                % ADIM_ADI["bolme"])
        b["hazir_kolonlar"] = list(tanim.get("kolonlar") or [])
        return {"tur": "hazir", "bicim": tanim.get("tur"),
                "kolon": tanim.get("kolon"), "esleme": tanim.get("esleme") or {}}
    # Rastgele ayirmanin birimi (kimlik / satir): zamansal bolmedeki Test
    # (OOS) payi da ayni kuralla ayrilir.
    kimlik = m.get("id") if a["birim"] == "kimlik" else None
    if kimlik and kimlik in kol:
        notlar.append("Rastgele ayırma %s kimliği üzerinden yapıldı; aynı kimlik "
                      "iki sete birden düşmez." % kimlik)
    else:
        if a["birim"] == "kimlik":
            notlar.append("Kimlik kolonu veri setinde bulunamadığı için rastgele "
                          "ayırma satır bazında yapıldı.")
        kimlik = None
    rastgele = {"kimlik": kimlik, "katmanla": bool(a["katmanla"]),
                "hedef": m.get("target"), "seed": a["seed"]}

    donem = m.get("donem")
    if a["test_tanim"] == "zamansal" and donem in kol:
        donemler = durum.get("_donemler") or _donem_listesi_profilden(kol[donem])
        durum["bolme"] = b
        test = _zamansal_test_donemleri(durum, pd.Series(donemler, dtype=object), a)
        b["test_donemleri"] = test
        # SET DUZENI (kurum karari): son donem(ler) Validasyon (OOT); geri
        # kalan GELISTIRME donemindeki satirlardan rastgele (katmanli) bir
        # pay Test (OOS); kalani Train (MS). Ic adlar: test = OOT, val = OOS.
        tarif = {"tur": "zamansal", "kolon": donem, "test_donemleri": test,
                 "gap": a.get("gap")}
        if a["val_var"]:
            tarif["oos"] = dict(rastgele, oranlar=[["val", a["val_oran"]]])
        return tarif
    # Donem yoksa OOT yoktur: yalnizca Test (OOS) ayrilir (ic adi test).
    return dict(rastgele, tur="rastgele", oranlar=[["test", a["test_oran"]]])


def _bolme_uygula_spark(durum):
    """Bolmeyi Spark'ta uygular: AMP_VERISETI _SPLIT kolonuyla yeniden
    yazilir; set sayilari recipe'ten gelir. Tablo webapp'te okunmaz."""
    b = dict(durum.get("bolme") or {})
    a = bolme_ayarlari(durum)
    for k in ("test_tanim", "tur", "birim", "katmanla", "val_var", "val_oran",
              "test_oran", "cv", "kat", "oot_adet", "oot_tanim", "seed",
              "seed_tur", "tekrar", "gap"):
        b[k] = a[k]
    b.pop("oot_var", None)
    for k in BOLME_KALICI_ALANLARI:
        b.pop(k, None)
    b.pop("test_donemleri", None)
    notlar = []
    tarif = _bolme_tarifi(durum, a, b, notlar)
    b.setdefault("test_donemleri", [])

    # KAYNAK AMP_VERISETI'nin KENDISI (kullanici karari); kaynak tabloya
    # geri donulmez.
    oz = amp_mod.amp_bolme_yaz(durum, tarif)
    onbellek_temizle()
    setler = oz.get("setler") or {}
    sayi = {ad: int((setler.get(SPLIT_ETIKET[ad]) or {}).get("satir") or 0)
            for ad in SET_ADLARI}
    b.update({"kalici": "kolon", "split_kolon": SPLIT_KOLON,
              "split_dataset": oz.get("dataset") or oz.get("dosya"), "satir": sayi,
              "train_satir": sayi["egitim"], "test_satir": sayi["test"],
              "toplam_satir": int(oz.get("satir") or 0)})
    durum["amp_cikti"] = dict(durum.get("amp_cikti") or {})
    eski = (durum["amp_cikti"].get("veri") or {})
    kayit = _amp_veri_kaydi(oz)
    # Surec disi kolonlar teyitte dustu; bolme yeni kolon dusurmez.
    kayit["dusen_kolon"] = eski.get("dusen_kolon", kayit["dusen_kolon"])
    durum["amp_cikti"]["veri"] = kayit

    disarida = int((setler.get(amp_mod.DISARIDA) or {}).get("satir") or 0)
    if tarif["tur"] == "hazir":
        if disarida:
            notlar.append("Veri setindeki bölme kullanıldı (%s). %s satır hiçbir "
                          "sete işaretlenmemiş; bu satırlar modellemeye girmiyor."
                          % (", ".join(b["hazir_kolonlar"]), _sayi(disarida)))
        else:
            notlar.append("Veri setindeki bölme kullanıldı (%s); kolonlara "
                          "dokunulmadı." % ", ".join(b["hazir_kolonlar"]))
    elif tarif["tur"] == "zamansal" and a["val_var"] and not sayi["val"]:
        notlar.append("Geliştirme döneminde Test (OOS) için ayrılabilecek "
                      "kayıt kalmadı.")
    for ad in SET_ADLARI:
        n = sayi[ad]
        if 0 < n < MIN_SET_SATIR:
            notlar.append("%s seti yalnızca %s satır; %s satırın altındaki "
                          "sette ölçüm güvenilir değil."
                          % (set_basligi(ad, a["test_tanim"]), _sayi(n),
                             _sayi(MIN_SET_SATIR)))

    # _SPLIT bir degisken degildir; degisken havuzunun disinda kalmali.
    durum["haric_kolonlar"] = sorted(
        set(durum.get("haric_kolonlar") or []) | {SPLIT_KOLON})
    durum["bolme"] = b

    ikili = (durum.get("profil") or {}).get("hedef_tip") == "binary"

    def set_satiri(ad):
        st = setler.get(SPLIT_ETIKET[ad]) or {}
        n = int(st.get("satir") or 0)
        metin = "  %s : %s satır" % (set_basligi(ad, a["test_tanim"]), _sayi(n))
        if ikili and n:
            metin += " · hedef oranı %%%s" % _ond(100.0 * float(st.get("pozitif") or 0) / n, 2)
        if ad == "test" and tarif["tur"] == "zamansal" and b.get("test_donemleri"):
            metin += "  (dönem: %s)" % ", ".join(str(x) for x in b["test_donemleri"])
        return metin

    # Sira (kurum duzeni): Train (MS), Validasyon (OOT), Test (OOS)
    sira = ["egitim", "test"] + (["val"] if sayi["val"] else [])
    satirlar = [set_satiri(ad) for ad in sira]
    if disarida and tarif["tur"] != "hazir":
        satirlar.append("  Hiçbir Sete Girmeyen : %s satır  (ara dönem)" % _sayi(disarida))
    ek = ("\n" + "\n".join(notlar)) if notlar else ""
    secilen_tipler = durum.get("tip_donusum") or {}
    if secilen_tipler:
        ek += ("\n%s kolon sözlük teyidindeki seçiminize göre dönüştürülmüş "
               "tiple işleniyor." % _sayi(len(secilen_tipler)))
    return ("Bölme tanımlandı: %s satır AMP_VERISETI içinde setlere ayrıldı.\n%s%s"
            % (_sayi(b["toplam_satir"]), "\n".join(satirlar), ek))


def bolme_uygula(durum):
    """Bolmeyi uygular: AMP_VERISETI _SPLIT kolonuyla yeniden yazilir
    (Spark, bkz. amp_spark); set sayilari recipe'ten gelir."""
    return _bolme_uygula_spark(durum)
