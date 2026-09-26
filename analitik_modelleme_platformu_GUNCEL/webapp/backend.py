# -*- coding: utf-8 -*-
"""Webapp backend — tarayici ile fe_agent.akis arasindaki kopru.

Is mantigi burada YOK; her endpoint akis.py'ye delege eder.
View fonksiyon adlari "_endpoint" sonekli; Flask endpoint adini fonksiyon
adindan uretir ve ayni ad iki kez tanimlanirsa backend hic acilmaz.

Oturum anahtari SUNUCUDA uretilir: kullanici kimligi (Dataiku auth) +
istemcinin gonderdigi calisma kimligi. Istemciden gelen deger tek basina
yetki DEGILDIR; yalnizca ayni kullanicinin birden fazla calismasini ayirir.
"""

import os
import re
import json
import datetime
import time
import uuid
import hashlib
import logging
import unicodedata
import traceback

import dataiku
from flask import request, jsonify, Response

from fe_agent import akis, validasyon

GORSEL_FOLDER = "LLM_WEBAPP_GORSEL"

# Mantiksal ad -> folder'daki gercek dosya adi.
# Gorsel degistirmek istersen SADECE burayi duzenle, JS'e dokunma.
# Dosya adlarindaki "akbank_" oneki KALDIRILDI: gorseller folder'da
# yeniden adlandirildi. Eski adlar da kabul ediliyor (yedek listesi)
# ki folder'i henuz guncellememis bir ortamda gorseller kaybolmasin.
GORSELLER = {
    "banner":     "robot_llm_ust.png",
    "bot":        "robot_llm_chat.png",
    "user":       "robot_llm_person.png",
    "zemin_acik": "llm_chat_light.png",
    "zemin_koyu": "llm_chat_dark.png",
}

GORSEL_YEDEK = {
    "banner":     "akbank_robot_llm_ust.png",
    "bot":        "akbank_robot_llm_chat.png",
    "user":       "akbank_robot_llm_person.png",
    "zemin_acik": "akbank_llm_chat_light.png",
    "zemin_koyu": "akbank_llm_chat_dark.png",
}

_MIME = {".png": "image/png", ".jpg": "image/jpeg",
         ".jpeg": "image/jpeg", ".webp": "image/webp"}

# Dataset listesi onbellegi: (uretim_zamani, liste). Suresiz TUTULMAZ.
ONBELLEK_SURESI = 300.0        # saniye
TAZELE_ARALIGI = 30.0          # ?tazele=1 icin en kisa aralik (hiz siniri)
GECMIS_SINIRI = 80             # oturumda saklanan sohbet balonu sayisi

# EKRAN TRANSKRIPTI BOYUT SINIRLARI.
# Her satir, o turda cizilen kart govdesini de tasiyor; F5'ten sonra
# bloklar birebir yeniden ciziliyor. En buyuk govde girdi dogrulama
# karti (tanimsiz kolon listesi, ust sinir 200 satir) ve yaklasik
# 20-60 KB tutuyor. Siniri asan govde YAZILMAZ; satirin kendisi ve adim
# anahtari her zaman kalir, yani blok ve "Geri Dön" kaybolmaz.
EKRAN_SINIRI = 512 * 1024        # tek kart govdesi
TRANSKRIPT_SINIRI = 4 * 1024 * 1024   # tum transkript

# Mevcut proje disindaki datasetler varsayilan olarak PAYLASILMAZ.
# Gerekirse bu ortam degiskeni ile virgullu proje anahtari listesi verilir.
EK_PROJE_DEGISKENI = "WEBAPP_EK_PROJELER"

# Dataset listesi kapsami:
#   "proje"  -> yalnizca webapp'in bulundugu proje (+ EK_PROJELER)
#   "erisim" -> kullanicinin OKUMA yetkisi olan TUM projeler  <-- varsayilan
# Ortam degiskeni: WEBAPP_DATASET_KAPSAMI
KAPSAM_DEGISKENI = "WEBAPP_DATASET_KAPSAMI"
VARSAYILAN_KAPSAM = "erisim"

# Yetki bilgisi OKUNAMAYAN projeler ne olsun?
#   "goster" (varsayilan) -> listelemeyi DENE; Dataiku kendi yetkilendirmesiyle
#                            zaten reddeder. Kullanici erisebildigi tablolari
#                            gorur, ama liste backend kimligi kadar genis
#                            olabilir; /datasetler yanitinda raporlanir.
#   "gizle"               -> atla (eski davranis). Daha dar ama kullanici
#                            erisebildigi tablolari goremeyebilir.
BELIRSIZ_DEGISKENI = "WEBAPP_BELIRSIZ_YETKI"
VARSAYILAN_BELIRSIZ = "goster"

# Kolon listesi onbellegi: veri seti adi -> (zaman, kolonlar)
KOLON_ONBELLEK_SURESI = 600.0
KOLON_ONBELLEK_KAPASITE = 40

_dosya_haritasi = None
# Dataset listesi onbellegi KULLANICI BAZLIDIR. Tek global onbellek,
# bir kullanicinin gordugu listeyi digerine sizdirirdi.
_dataset_onbellek = {}         # kullanici_ozeti -> (zaman, liste)
_kolon_onbellek = {}           # veri_seti -> (zaman, kolonlar)
_son_tazeleme = {}             # kullanici_ozeti -> zaman

# Kimlik alinamadiginda kullanilan yedek kova icin surec-ozel tuz.
# Kova adinin disaridan tahmin edilmesini engeller.
_YEDEK_TUZ = uuid.uuid4().hex

_LOG = logging.getLogger("fe_webapp")


# ===========================================================================
# HATA YONETIMI
# ===========================================================================
def _hata_kaydet(nerede, e):
    """Tam izi YALNIZCA sunucu loguna yazar; kullaniciya kisa kod doner.

    Iz; dosya yollari, dataset adlari ve baglanti bilgisi icerebilir,
    bu yuzden HTTP govdesine asla konmaz."""
    kod = "HATA-" + uuid.uuid4().hex[:6].upper()
    metin = "[%s] %s -> %s: %s\n%s" % (
        kod, nerede, type(e).__name__, e, traceback.format_exc())
    try:
        _LOG.error(metin)
    except Exception:
        pass
    print(metin)          # Dataiku webapp log sekmesi
    return kod


def _hata_govdesi(nerede, e, metin=None):
    """Istemciye donen yapilandirilmis hata govdesi (HTTP 200).

    JS "HATA:" onekine bakarak hata balonu ciziyor; onek korunuyor."""
    kod = _hata_kaydet(nerede, e)
    cevap = "HATA: %s\n\nHata kodu: %s, bu kodu ilettiğinizde kayıtlardan " \
            "ayrıntıya ulaşılabilir." % (
                metin or "İşlem tamamlanamadı.", kod)
    return {"cevap": cevap, "metin": cevap, "hata": True, "hata_kodu": kod}


# ===========================================================================
# OTURUM KIMLIGI
# ===========================================================================
def _temiz(s, en_fazla=32):
    """akis._yol ile ayni karakter kumesi; once burada sadelestiriyoruz ki
    iki farkli girdi temizlendikten sonra ayni dosyaya dusmesin."""
    return re.sub(r"[^A-Za-z0-9_-]", "", str(s or ""))[:en_fazla]


_KIMLIK_ANAHTARLARI = ("authIdentifier", "login", "identifier",
                       "userId", "user")


def _bilgiden_kimlik(bilgi):
    """Dataiku auth sozlugunden kullanici adini cikarir."""
    if not isinstance(bilgi, dict):
        return None
    for anahtar in _KIMLIK_ANAHTARLARI:
        deger = bilgi.get(anahtar)
        if deger:
            return str(deger)
    return None


def _kullanici_adi():
    """Webapp'i O AN GORUNTULEYEN kullanicinin Dataiku login'i.

    ONEMLI AYRIM. Bir Dataiku webapp backend'inde iki farkli kimlik vardir:

      1) Backend'in KENDI kimligi — webapp sahibi (yani bu webapp'i kuran
         kisi). `api_client().get_auth_info()` BUNU dondurur.
      2) Isteği yapan kullanici — webapp'i tarayicida acan kisi.

    Ikisini karistirmak cok kullanicili kullanimda iki agir soruna yol
    acar: (a) herkesin oturum anahtari AYNI cikar, yani ayni anda calisan
    iki analist birbirinin calismasini ezer; (b) dataset listesi webapp
    sahibinin yetkisine gore uretilir.

    Dogru kimlik icin once tarayici basliklarindan cozumleme denenir
    (`get_auth_info_from_browser_headers`), bulunamazsa backend kimligine
    dusulur. Hangi yolun kullanildigi /tani ucundan gorulebilir.
    """
    istemci = None
    try:
        istemci = dataiku.api_client()
    except Exception as e:
        _hata_kaydet("api_client", e)
        return None, "yok"

    # 1) Tarayici basliklarindan: isteği YAPAN kullanici
    cozucu = getattr(istemci, "get_auth_info_from_browser_headers", None)
    if callable(cozucu):
        try:
            basliklar = dict(request.headers)
        except Exception:
            basliklar = {}
        if basliklar:
            for cagri in (lambda: cozucu(basliklar),
                          lambda: cozucu(headers=basliklar)):
                try:
                    ad = _bilgiden_kimlik(cagri() or {})
                    if ad:
                        return ad, "tarayici"
                except Exception:
                    continue

    # 2) Yedek: backend kimligi (webapp sahibi). Cok kullanicili kullanimda
    #    YETERLI DEGILDIR; /tani bunu acikca uyarir.
    try:
        ad = _bilgiden_kimlik(istemci.get_auth_info() or {})
        if ad:
            return ad, "backend"
    except Exception as e:
        _hata_kaydet("get_auth_info", e)
    return None, "yok"


def _kullanici_kimligi():
    """Oturum anahtari icin kullanilan kimlik dizesi."""
    ad, _ = _kullanici_adi()
    return ("kullanici:%s" % ad) if ad else None


def _yedek_kimlik():
    """Kimlik alinamazsa: istege ve surece bagli YALITILMIS kova.
    Ortak "varsayilan" kovasina DUSULMEZ."""
    parcalar = [_YEDEK_TUZ,
                request.remote_addr or "",
                request.headers.get("User-Agent") or ""]
    ozet = hashlib.sha256("|".join(parcalar).encode("utf-8")).hexdigest()
    _LOG.warning("Kullanici kimligi alinamadi; yedek oturum kovasi kullaniliyor.")
    return "yedek:%s" % ozet


# ---------------------------------------------------------------------------
# CALISMA ADLARI
# ---------------------------------------------------------------------------
# YENI AD: v1, v2, v3 ... (kullanici karari: "v1 v2 gibi basitçe").
# Bir calismanin HER SEYI tek klasorde:
#     PROJE_HAFIZASI/v3/calisma.json        <- kayit
#     PROJE_HAFIZASI/v3/sozluk_calisma.csv
#     PROJE_HAFIZASI/v3/AMP_VERISETI.csv ...
# Numara PROJE GENELINDE tekildir (iki kullanicinin "v1"i olmaz), bu
# yuzden kullanici adi ada girmiyor.
#
# ERISIM. Kimin hangi calismanin sahibi oldugu CALISMA_KAYDI'nda tutulur
# (sahip = kullanici kimliginin ozeti). Istemci "v3" gonderir; v3
# baskasinin ise istek REDDEDILIR. Kayit dosyasinda girdi yoksa
# calismanin kendi dosyasindaki "_sahip" alanina bakilir.
#
# ONCEKI BICIMLER OKUNMAYA DEVAM EDER:
#   "03"        -> oturum_<kullanici>_03.json  (bir onceki tur)
#   "ck2m9x1qz" -> oturum_u<ozet>_ck2m9x1qz.json (ilk bicim)
# Ikisi de "Çalışmalarım" listesinde "Eski Kayıt" olarak gorunur.
_TR_ASCII = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
CALISMA_KAYDI = "/CALISMALAR.json"
V_KALIP = re.compile(r"^v(\d{1,6})$")


class CalismaErisimYok(Exception):
    """Istenen calisma baska bir kullaniciya ait."""


def _kullanici_on_eki():
    """ONCEKI TURUN bicimi ("cmergen_03") icin kullanicinin ad kismi.
    Yeni calismalar bunu KULLANMAZ; yalnizca eski kayitlari bulmak icin."""
    ad, _ = _kullanici_adi()
    if not ad:
        return "misafir-" + hashlib.sha256(
            _yedek_kimlik().encode("utf-8")).hexdigest()[:8]
    yerel = str(ad).split("@")[0]
    sade = unicodedata.normalize("NFKD", yerel.translate(_TR_ASCII))
    sade = sade.encode("ascii", "ignore").decode("ascii")
    sade = re.sub(r"[^A-Za-z0-9]+", "-", sade).strip("-").lower()[:24]
    if sade and sade == str(ad).lower():
        return sade
    ozet = hashlib.sha256(str(ad).encode("utf-8")).hexdigest()[:4]
    return ("%s-%s" % (sade, ozet)) if sade else ("k" + ozet)


def _sahip_ozeti():
    """Kullanicinin 16 haneli kimlik ozeti (ilk bicimdeki "u<ozet>" ile ayni)."""
    kimlik = _kullanici_kimligi() or _yedek_kimlik()
    return hashlib.sha256(kimlik.encode("utf-8")).hexdigest()[:16]


def _eski_on_ek():
    """Ilk adlandirmanin kullanici kismi: "u<16 haneli ozet>_"."""
    return "u%s_" % _sahip_ozeti()


def _v_mi(calisma):
    return bool(V_KALIP.match(str(calisma or "")))


def _sayili_mi(calisma):
    """Bir onceki turun bicimi: yalnizca rakam ("03")."""
    return bool(calisma) and str(calisma).isdigit()


def _hafiza():
    return dataiku.Folder(getattr(akis, "HAFIZA_FOLDER", "PROJE_HAFIZASI"))


def _calisma_kaydi_oku():
    try:
        with _hafiza().get_download_stream(CALISMA_KAYDI) as s:
            kayit = json.loads(s.read().decode("utf-8"))
        return kayit if isinstance(kayit, dict) else {}
    except Exception:
        return {}


def _calisma_kaydi_yaz(kayit):
    _hafiza().upload_stream(
        CALISMA_KAYDI,
        json.dumps(kayit, ensure_ascii=False, indent=1).encode("utf-8"))


def _v_silindi_mi(calisma):
    """Calisma "Çalışmalarım"dan silinmis mi? Numara kayitta ISARETLI
    kalir (silindi alani): ayni numara bir daha verilmesin, eski sekmede
    acik kalan kimlik baska bir calismaya denk gelmesin."""
    return bool((_calisma_kaydi_oku().get(calisma) or {}).get("silindi"))


def _v_sahibi(calisma):
    """v-calismanin sahip ozeti; bilinmiyorsa None."""
    sahip = (_calisma_kaydi_oku().get(calisma) or {}).get("sahip")
    if sahip:
        return sahip
    # Kayitta yok: calismanin kendi dosyasina bak (varsa).
    try:
        with _hafiza().get_download_stream("/%s/calisma.json" % calisma) as s:
            return (json.loads(s.read().decode("utf-8")) or {}).get("_sahip")
    except Exception:
        return None


def _oturum_anahtari(istemci_id=None):
    """Sunucu tarafli oturum anahtari.

    v3        -> "v3" (sahibi degilse CalismaErisimYok)
    03        -> <kullanici>_03          (onceki tur)
    ck2m9x1qz -> u<kullanici ozeti>_ck2m9x1qz (ilk bicim)"""
    calisma = _temiz(istemci_id) or "ana"
    if _v_mi(calisma):
        sahip = _v_sahibi(calisma)
        if sahip and sahip != _sahip_ozeti():
            raise CalismaErisimYok("Bu çalışma başka bir kullanıcıya ait.")
        if _v_silindi_mi(calisma):
            raise CalismaErisimYok("Bu çalışma silinmiş.")
        return calisma
    if _sayili_mi(calisma):
        return "%s_%s" % (_kullanici_on_eki(), calisma)
    return "%s%s" % (_eski_on_ek(), calisma)


def _calisma_id(kaynak):
    """Istemciden gelen ham calisma kimligini normalize eder.

    Iki ad da kabul edilir: uygulamanin eski uclari "oturum_id" yolluyor,
    yeni sozluk uclari "calisma_id". Tek ada zorlamak, hangi ucun hangi
    adi kullandigini hatirlamayi gerektiriyor ve yanlis ad sessizce
    "ana" oturumuna dusuyordu — yani kullanici baskasinin degil ama
    KENDI baska oturumunun sozlugunu duzenleyebiliyordu."""
    kaynak = kaynak or {}
    return (_temiz(kaynak.get("oturum_id"))
            or _temiz(kaynak.get("calisma_id"))
            or "ana")


# ===========================================================================
# GORSEL SERVISI
# ===========================================================================
def _sadelestir(ad):
    """Unicode normalizasyon farkini (NFC/NFD) ve buyuk-kucuk harfi eler."""
    return unicodedata.normalize("NFC", (ad or "")).casefold()


def _haritayi_kur(zorla=False):
    global _dosya_haritasi
    if _dosya_haritasi is not None and not zorla:
        return _dosya_haritasi
    harita = {}
    try:
        for yol in dataiku.Folder(GORSEL_FOLDER).list_paths_in_partition():
            harita[_sadelestir(os.path.basename(yol))] = yol
    except Exception:
        harita = {}
    _dosya_haritasi = harita
    return harita


def _dosya_bul(ad):
    anahtar = _sadelestir(os.path.basename(ad))
    harita = _haritayi_kur()
    if anahtar in harita:
        return harita[anahtar]
    # Folder'a yeni dosya eklendiyse haritayi tazele
    return _haritayi_kur(zorla=True).get(anahtar)


@app.route("/gorsel/<anahtar>")
def gorsel_endpoint(anahtar):
    dosya_adi = GORSELLER.get(anahtar)
    if not dosya_adi:
        return Response("tanimsiz gorsel", status=404)

    uzanti = os.path.splitext(dosya_adi)[1].lower()
    if uzanti not in _MIME:
        return Response("gecersiz uzanti", status=404)

    # Once yeni ad, bulunamazsa eski "akbank_" onekli ad denenir. Boylece
    # folder'i yeniden adlandirmis da adlandirmamis ortamda da calisir;
    # gorsel kaybolursa sohbet avatarlari sessizce yok oluyordu.
    yol = _dosya_bul(dosya_adi)
    if not yol:
        eski = GORSEL_YEDEK.get(anahtar)
        if eski:
            yol = _dosya_bul(eski)
            if yol:
                uzanti = os.path.splitext(eski)[1].lower()
    if not yol:
        return Response("gorsel bulunamadi", status=404)

    try:
        with dataiku.Folder(GORSEL_FOLDER).get_download_stream(yol) as s:
            veri = s.read()
    except Exception as e:
        kod = _hata_kaydet("gorsel:%s" % anahtar, e)
        return Response("okuma hatasi (%s)" % kod, status=500)

    return Response(veri, mimetype=_MIME[uzanti],
                    headers={"Cache-Control": "public, max-age=86400"})


# ===========================================================================
# PROJE BILGISI
# ===========================================================================
def _ek_projeler():
    ham = os.environ.get(EK_PROJE_DEGISKENI) or ""
    return [p.strip() for p in ham.split(",") if p.strip()]


def _kapsam():
    """Dataset listesi kapsami: "erisim" (varsayilan) ya da "proje"."""
    deger = (os.environ.get(KAPSAM_DEGISKENI) or "").strip().lower()
    return deger if deger in ("proje", "erisim") else VARSAYILAN_KAPSAM


def _kullanici_gruplari(istemci, login):
    """Kullanicinin gruplari ve admin bayragi. Alinamazsa (None, False)."""
    if not login:
        return None, False
    try:
        ham = istemci.get_user(login).get_settings().get_raw() or {}
    except Exception as e:
        _hata_kaydet("get_user:%s" % login, e)
        return None, False
    gruplar = set(ham.get("groups") or [])
    yonetici = bool(ham.get("admin"))
    return gruplar, yonetici


def _okuyabilir_mi(istemci, proje_key, login, gruplar, yonetici):
    """Kullanicinin BU projenin icerigini okuma yetkisi var mi?

    Doner: True / False / None (BELIRSIZ — yetki bilgisi okunamadi).

    ONEMLI: get_permissions() cogu kurulumda yalnizca proje yoneticisine
    aciktir; backend kimligi o projede yonetici degilse istisna atar.
    Eskiden bu durumda False donuluyordu ve proje SESSIZCE listeden
    dusuyordu — kullanicinin erisebildigi tablolari hic gormemesinin
    sebebi buydu. Artik "belirsiz" olarak isaretlenir; ne yapilacagina
    _dataset_adlari karar verir ve sonuc kullaniciya raporlanir.
    """
    if yonetici:
        return True
    try:
        izin = istemci.get_project(proje_key).get_permissions() or {}
    except Exception:
        return None
    if login and izin.get("ownerLogin") == login:
        return True
    for satir in (izin.get("permissions") or []):
        if not isinstance(satir, dict):
            continue
        if not (satir.get("readProjectContent") or satir.get("admin")):
            continue
        grup = satir.get("group")
        if grup and gruplar and grup in gruplar:
            return True
        if satir.get("user") and login and satir.get("user") == login:
            return True
    return False


def _dataset_adlari(login=None):
    """Kullanicinin ERISEBILDIGI dataset adlari.

    Mevcut projedekiler yalin adla, digerleri PROJE.DATASET biciminde
    doner (akis tarafi noktali adi kabul ediyor).

    Kapsam "erisim" ise TUM projeler taranir ama her proje icin
    KULLANICININ okuma yetkisi dogrulanir — liste backend'in (webapp
    sahibinin) degil, o an bakan kisinin yetkisine gore uretilir.
    """
    istemci = dataiku.api_client()
    varsayilan = istemci.get_default_project()
    varsayilan_key = getattr(varsayilan, "project_key", None)

    adlar = [d["name"] for d in varsayilan.list_datasets()]

    if _kapsam() == "proje":
        hedefler = [p for p in _ek_projeler() if p != varsayilan_key]
        gruplar, yonetici = None, True      # acikca yapilandirilmis: sorma
    else:
        try:
            hepsi = istemci.list_project_keys() or []
        except Exception as e:
            _hata_kaydet("list_project_keys", e)
            hepsi = []
        hedefler = [p for p in hepsi if p != varsayilan_key]
        gruplar, yonetici = _kullanici_gruplari(istemci, login)

    belirsiz, atlanan = [], []
    for p in hedefler:
        if not yonetici:
            izin = _okuyabilir_mi(istemci, p, login, gruplar, yonetici)
            if izin is False:
                atlanan.append(p)
                continue
            if izin is None:
                # Yetki okunamadi. "goster" ise listelemeyi DENERIZ:
                # erisim yoksa Dataiku'nun kendisi zaten hata verir.
                if _belirsiz_davranisi() == "gizle":
                    atlanan.append(p)
                    continue
                belirsiz.append(p)
        try:
            for d in istemci.get_project(p).list_datasets():
                adlar.append("%s.%s" % (p, d["name"]))
        except Exception as e:
            _hata_kaydet("proje:%s" % p, e)
            if p in belirsiz:
                belirsiz.remove(p)
            atlanan.append(p)
    return sorted(set(adlar)), {"belirsiz_yetki": sorted(set(belirsiz)),
                                "atlanan": sorted(set(atlanan))}


def _belirsiz_davranisi():
    d = (os.environ.get(BELIRSIZ_DEGISKENI) or "").strip().lower()
    return d if d in ("goster", "gizle") else VARSAYILAN_BELIRSIZ


def _kolon_adlari(veri_seti):
    """Bir veri setinin kolon adlari. Once sema, olmazsa tek satir okuma."""
    simdi = time.time()
    kayit = _kolon_onbellek.get(veri_seti)
    if kayit and simdi - kayit[0] < KOLON_ONBELLEK_SURESI:
        return kayit[1]

    ds = dataiku.Dataset(veri_seti)
    kolonlar = []
    try:
        sema = ds.read_schema() or []
        kolonlar = [k["name"] for k in sema if isinstance(k, dict) and k.get("name")]
    except Exception:
        kolonlar = []
    if not kolonlar:
        # Sema okunamadi (ya da bos): tek satirlik okumadan cikar.
        df = ds.get_dataframe(limit=1)
        kolonlar = [str(c) for c in df.columns]

    if len(_kolon_onbellek) >= KOLON_ONBELLEK_KAPASITE:
        _kolon_onbellek.clear()
    _kolon_onbellek[veri_seti] = (simdi, kolonlar)
    return kolonlar


def _durum_al(anahtar):
    """Oturum durumunu guvenle yukler.

    akis.durum_yukle bozuk bir kayitta artik DurumOkunamadi firlatiyor
    ("dosya yok" ile "bozuk" ayrildi). Bozuk kayitta calismayi sessizce
    sifirlamak yerine hatayi yukari tasiyoruz; cagiran endpoint kullaniciya
    hata kodu gosterir ve eski kayit silinmez.
    """
    return akis.durum_yukle(anahtar)


@app.route("/datasetler")
def datasetler_endpoint():
    """Kullanicinin erisebildigi dataset adlari.

    Onbellek KULLANICI BAZLIDIR: tek global onbellek, bir kullanicinin
    gordugu listeyi digerine sizdirirdi.
    """
    global _dataset_onbellek, _son_tazeleme

    login, _ = _kullanici_adi()
    kova = hashlib.sha256(("%s" % login).encode("utf-8")).hexdigest()[:16]

    simdi = time.time()
    tazele = bool(request.args.get("tazele"))
    if tazele:
        if simdi - (_son_tazeleme or {}).get(kova, 0.0) < TAZELE_ARALIGI:
            tazele = False              # hiz siniri: onbellekten dondur
        else:
            if not isinstance(_son_tazeleme, dict):
                _son_tazeleme = {}
            _son_tazeleme[kova] = simdi

    kayit = (_dataset_onbellek or {}).get(kova)
    if kayit and not tazele and simdi - kayit[0] < ONBELLEK_SURESI:
        return jsonify({"datasetler": kayit[1], "onbellek": True,
                        "kapsam": _kapsam()})

    try:
        adlar, kapsam_tani = _dataset_adlari(login)
        if not isinstance(_dataset_onbellek, dict):
            _dataset_onbellek = {}
        _dataset_onbellek[kova] = (simdi, adlar)
        govde = {"datasetler": adlar, "onbellek": False,
                 "kapsam": _kapsam()}
        govde.update(kapsam_tani)
        return jsonify(govde)
    except Exception as e:
        kod = _hata_kaydet("datasetler", e)
        return jsonify({"datasetler": [],
                        "hata": "Veri seti listesi alınamadı.",
                        "hata_kodu": kod})


@app.route("/kolonlar")
def kolonlar_endpoint():
    """Bir veri setinin kolon adlari.

    Modelleme tanimlari formu (hedef / kimlik / donem) bu listeden secim
    yaptirir; eskiden dataset listesinde arama yapiyordu ve kullanici
    hedef degiskenini hic secemiyordu.
    """
    veri_seti = (request.args.get("veri_seti") or "").strip()
    if not veri_seti:
        return jsonify({"kolonlar": [], "hata": "Veri seti belirtilmedi."})
    try:
        return jsonify({"kolonlar": _kolon_adlari(veri_seti),
                        "veri_seti": veri_seti})
    except Exception as e:
        kod = _hata_kaydet("kolonlar:%s" % veri_seti, e)
        return jsonify({"kolonlar": [],
                        "hata": "'%s' veri setinin kolonları okunamadı."
                                % veri_seti,
                        "hata_kodu": kod})


@app.route("/tani")
def tani_endpoint():
    """Kurulum tanilama: kimlik hangi yoldan cozuluyor, kapsam ne?

    Cok kullanicili kullanima acmadan ONCE bu ucu iki farkli kullanici
    hesabiyla acip "kullanici" alaninin FARKLI ciktigini dogrulayin.
    Ayni cikiyorsa webapp "her kullanici kendi kimligiyle calissin"
    ayarina alinmali; aksi halde iki analist ayni oturumu paylasir.
    """
    login, yol = _kullanici_adi()
    govde = {
        "kullanici": login,
        "kimlik_yolu": yol,          # "tarayici" | "backend" | "yok"
        "oturum_anahtari": _oturum_anahtari(request.args.get("oturum_id")),
        "kapsam": _kapsam(),
        "belirsiz_yetki_davranisi": _belirsiz_davranisi(),
        "hafiza_folder": getattr(akis, "HAFIZA_FOLDER", None),
    }
    # Dataset kapsaminin gercekte ne dondurdugu: kac proje listelendi,
    # kacinin yetkisi okunamadi, kaci atlandi.
    try:
        adlar, kapsam_tani = _dataset_adlari(login)
        govde["dataset_sayisi"] = len(adlar)
        govde.update(kapsam_tani)
    except Exception as e:
        govde["dataset_hatasi"] = _hata_kaydet("tani:datasetler", e)
    if yol == "tarayici":
        govde["durum"] = ("Kimlik tarayıcı başlıklarından çözülüyor: çok "
                          "kullanıcılı kullanım için doğru yol budur.")
    elif yol == "backend":
        govde["durum"] = ("UYARI: Kimlik backend'in kendi kimliğinden "
                          "alınıyor; bu, webapp'i KURAN kişidir. Bu haliyle "
                          "tüm kullanıcılar aynı oturumu paylaşır ve veri "
                          "seti listesi webapp sahibinin yetkisine göre "
                          "üretilir. Webapp ayarlarında isteğin kullanıcı "
                          "kimliğiyle çalışmasını açın.")
    else:
        govde["durum"] = ("UYARI: Kullanıcı kimliği hiç alınamadı; yalıtılmış "
                          "yedek kovaya düşülüyor. Çalışma kalıcı olmaz.")
    try:
        govde["proje"] = getattr(
            dataiku.api_client().get_default_project(), "project_key", None)
    except Exception:
        govde["proje"] = None
    return jsonify(govde)


@app.route("/fazlar")
def fazlar_endpoint():
    """Sol paneldeki hiyerarsi. Mod secilmemisse yalnizca faz 01 doner;
    mod secildikten sonra faz 01'in alt adimlari moda gore degisir."""
    try:
        anahtar = _oturum_anahtari(request.args.get("oturum_id"))
        durum = _durum_al(anahtar)
        mod = durum.get("mod")
        return jsonify({
            "fazlar": akis.faz_agaci(mod),
            "toplam": len(akis.adim_sirasi(mod)),
            "mod": mod,
        })
    except Exception as e:
        govde = _hata_govdesi("fazlar", e, "İş akışı yüklenemedi.")
        govde.update({"fazlar": [], "toplam": 0, "mod": None})
        return jsonify(govde)


# ===========================================================================
# SOHBET
# ===========================================================================
def _analiz_verisi(durum):
    """Analiz Merkezi sekmeleri. Bir sekmenin hesabi hata verirse
    yalnizca o sekme bos doner; sohbet yaniti etkilenmez."""
    veri = {}
    try:
        veri["validasyon"] = validasyon.panel(durum)
    except Exception as e:
        kod = _hata_kaydet("validasyon.panel", e)
        veri["validasyon"] = {"hata": "Validasyon paneli hesaplanamadı (%s)." % kod}

    # Anahtarlar app.js'teki data-tab degerleriyle AYNI olmali:
    # VERİ & SÖZLÜK sekmesinin anahtari "ozet"tir.
    # "eksik" anahtari KALDIRILDI; icerigi "hazirlik" sekmesine tasindi.
    for anahtar, ad, uretici in (
            ("ozet", "VERİ & SÖZLÜK", akis.veri_sozluk_paneli),
            ("hazirlik", "HAZIRLIK", akis.hazirlik_paneli),
            ("sfa", "SFA", akis.sfa_paneli)):
        try:
            veri[anahtar] = uretici(durum)
        except Exception as e:
            kod = _hata_kaydet("akis.%s" % uretici.__name__, e)
            veri[anahtar] = {"hata": "%s paneli hesaplanamadı (%s)." % (ad, kod)}
    return veri


def _grup(durum):
    """Icinde bulunulan adimin blok grubu: (anahtar, baslik)."""
    try:
        return akis.adim_grubu(akis.adim_anahtari(durum))
    except Exception:
        return None, ""


def _yanit(durum, metin):
    """Her endpoint'in dondugu ortak govde."""
    mod = durum.get("mod")
    return {
        "cevap": metin,
        "mod": mod,
        "secenekler": durum.get("_secenekler") or [],
        "secim_alani": durum.get("_secim_alani"),
        "adim_no": durum["i"],
        # Blogun hangi adima ait oldugu. On yuz her blogun sag ustune o
        # adima donen bir "Geri Dön" dugmesi koyuyor; anahtar olmadan
        # dugmenin hedefi yok.
        "adim_anahtari": akis.adim_anahtari(durum),
        "adim_baslik": akis.adim_basligi(akis.adim_anahtari(durum)),
        # BLOK GRUBU. Ardisik adimlar sohbette tek blok olarak gorunur;
        # her adim blogun icinde kendi ALT BASLIGINI ve kendi "Geri Dön"
        # dugmesini tasir (bkz. akis_kayit.ADIM_GRUPLARI).
        "grup_anahtari": _grup(durum)[0] or "",
        "grup_baslik": _grup(durum)[1],
        "toplam": len(akis.adim_sirasi(mod)),
        # "girdi": form/kart bekleniyor, "onay": plan onay bekliyor.
        # JS alttaki aksiyon butonlarini buna gore gosterir/gizler.
        "bekleyen": durum.get("bekleyen"),
        # Sag panel sekmelerinin verisi
        "analiz": _analiz_verisi(durum),
        # Mod secilince faz agaci degisir; her yanitta guncel halini gonderiyoruz
        "fazlar": akis.faz_agaci(mod),
        "ozet": akis.ozet(durum),
        "detay": akis.detay(durum),
        # Idempotenslik: islenmis son tur numarasi (bkz. mesaj_endpoint)
        "tur_no": int(durum.get("_tur_no") or 0),
    }


def _cerceve_metni_mi(metin):
    """Bu metin bir TRANSKRIPT SATIRI mi, yoksa adimin cercevesi mi?

    Mod adiminin metni KARSILAMA'dir ve adim her yeniden acildiginda
    (F5, "Geri Dön") canli durumdan yeniden ciziliyor. Bir de gecmise
    yazilinca ekranda IKI KEZ beliriyordu: biri gecmisten gelen duz
    balon, biri adim blogunun icinden. Cerceve metni gecmise girmez."""
    return (metin or "").strip() == (akis.KARSILAMA or "").strip()


def _ekran_govdesi(govde):
    """Yanittan EKRANA CIZILEN kisim: secenek kartlari ve secim alani.
    Transkripte bu iki alan yaziliyor; geri kalani (analiz, fazlar,
    ozet) her acilista yeniden uretiliyor, saklanmasi gereksiz."""
    return {"secenekler": govde.get("secenekler") or [],
            "secim_alani": _ekran_sadelestir(govde.get("secim_alani"))}


def _ekran_sadelestir(alan):
    """Saklanacak kart govdesinden YENIDEN URETILEBILIR agir alanlari atar.

    Teyit kartinin her satiri tip donusum TEKLIFLERINI tasiyor (kolon
    basina alti secenek, her biri etiket + sebep). 1.042 kolonda bu tek
    basina yarim megabaytin ustune cikiyor ve butun kart govdesi
    EKRAN_SINIRI'ni asarak saklanmadan atiliyordu — yani F5'ten sonra
    teyit blogu bos kaliyordu. Teklifler YALNIZCA secim yapilirken
    gerekli; gecmisten cizilen kart kilitli ve salt okunur, orada
    secilmis donusumun ETIKETI yetiyor (satirdaki 'donusum_etiket').
    Bu yuzden liste saklanmadan once dusuruluyor."""
    if not isinstance(alan, dict):
        return alan
    dg = alan.get("degiskenler")
    if not isinstance(dg, dict) or not isinstance(dg.get("satirlar"), list):
        return alan
    kopya = dict(alan)
    dg_kopya = dict(dg)
    dg_kopya["satirlar"] = [
        {k: v for k, v in s.items() if k != "donusumler"}
        if isinstance(s, dict) else s
        for s in dg["satirlar"]]
    kopya["degiskenler"] = dg_kopya
    return kopya


def _ekran_boyutu(ekran):
    """Kart govdesinin JSON boyutu (bayt). Olculemezse sinirin ustu."""
    try:
        return len(json.dumps(ekran, ensure_ascii=False).encode("utf-8"))
    except Exception:
        return EKRAN_SINIRI + 1


def _gecmise_ekle(durum, rol, metin, adim=None, baslik=None, ekran=None):
    """Ekran transkriptine bir satir ekler.

    ADIM ANAHTARI DA SAKLANIR: her blogun sag ustundeki "Geri Dön"
    dugmesi o blogu ureten adima donuyor. Anahtar yalnizca canli yanitta
    dursaydi, F5'ten sonra gecmisten cizilen bloklarda dugme kaybolurdu —
    kullanicinin en cok geri donmek isteyecegi eski bloklarda.

    KART GOVDESI DE SAKLANIR: adimin kartlari (form, dogrulama karti,
    secenek kartlari) yalnizca ekranda yasiyordu; F5'ten sonra blok bos
    kaliyor, kullanici "seçimlerim nereye gitti?" diyordu. Govde burada
    duruyor ve blok yeniden cizilirken AYNEN geri geliyor. Buyuk govdeler
    icin ust sinir var: oturum dosyasi sinirsiz buyumemeli."""
    if rol == "bot" and not adim and _cerceve_metni_mi(metin):
        # Adim anahtari olmayan cerceve metni (eski cagri bicimi):
        # blogu olmadigi icin yazilmasinin anlami yok.
        return
    gecmis = durum.get("_gecmis")
    if not isinstance(gecmis, list):
        gecmis = []
    kayit = {"rol": rol, "metin": metin}
    if adim:
        kayit["adim"] = adim
        kayit["adim_baslik"] = baslik or ""
    if ekran and (ekran.get("secenekler") or ekran.get("secim_alani")):
        if _ekran_boyutu(ekran) <= EKRAN_SINIRI:
            kayit["ekran"] = ekran
        else:
            # Govde cok buyuk: satir yine yazilir (blok ve "Geri Dön"
            # kaybolmamali), yalnizca kart gorseli geri gelmez.
            kayit["ekran_atlandi"] = True
    gecmis.append(kayit)
    durum["_gecmis"] = _gecmisi_kirp_boyuta(gecmis[-GECMIS_SINIRI:])


def _gecmisi_kirp_boyuta(gecmis):
    """Transkript toplam boyutu sinirin ustundeyse EN ESKI kart
    govdelerini duser. Satirlar ve adim anahtarlari KALIR: blok ve
    "Geri Dön" her zaman durur, yalnizca kart gorseli sadelestirilir."""
    if _ekran_boyutu(gecmis) <= TRANSKRIPT_SINIRI:
        return gecmis
    for kayit in gecmis:                    # en eskiden baslayarak
        if "ekran" in kayit:
            kayit.pop("ekran", None)
            kayit["ekran_atlandi"] = True
            if _ekran_boyutu(gecmis) <= TRANSKRIPT_SINIRI:
                break
    return gecmis


def _dogrulama_satirlarini_isle(alan, karar):
    """Girdi dogrulama kartinin SATIR KARARLARINI govdeye yazar.

    Kart 200 satir tasiyor; her satirda bir "sözlüğe ekle" kutusu ve bir
    aciklama kutusu var. Kullanicinin isaretledikleri ve yazdiklari
    yalnizca tarayicida duruyordu: kart govdesi arka uctan CIKTIGI
    haliyle (hepsi isaretsiz, aciklamalar dil modeli onerisi) saklaniyor
    ve F5'ten sonra "hic secim yapmamisim gibi" aciliyordu. Karar
    govdesi ({"haric": [...], "ekle": [{kolon, aciklama}]}) satirlara
    burada isleniyor."""
    tanimsiz = (alan or {}).get("tanimsiz")
    if not isinstance(tanimsiz, dict):
        return
    satirlar = tanimsiz.get("satirlar")
    if not isinstance(satirlar, list):
        return
    ekle = {}
    for e in (karar.get("ekle") or []):
        if isinstance(e, dict) and e.get("kolon"):
            ekle[str(e["kolon"])] = str(e.get("aciklama") or "")
    haric = set(str(k) for k in (karar.get("haric") or []))
    for sat in satirlar:
        if not isinstance(sat, dict):
            continue
        kolon = str(sat.get("kolon") or "")
        if kolon in ekle:
            sat["islem"] = "ekle"
            sat["oneri"] = ekle[kolon]
            # Aciklama artik kullanicinindir; "dil modeli onerisi"
            # etiketi yaniltici olurdu.
            sat["oneri_kaynak"] = "kullanici"
        elif kolon in haric:
            sat["islem"] = "haric"


def _biten_adimi_guncelle(durum, tamam, rozet=None, karar=None):
    """Biten adimin transkriptteki kart govdelerini SON haliyle gunceller.

    Uc sey gonderildikleri an dogru degildir ve karar verilince degisir;
    ucu de tarayicida oluyordu, hicbir yere yazilmiyordu:

      1) FORM DEGERLERI. Form govdesi bos gonderilir, kullanici
         tarayicida doldurur. Akis tarafi adimi bitirirken formu mevcut
         degerlerle yeniden uretiyor (akis_sohbet._biten_ekran).
      2) DOGRULAMA ROZETI. Kart "Girdiler Doğrulandı" ile acilir,
         karardan sonra "2 kolon sözlüğe eklendi" olur. O metin zaten
         kullanicinin gonderdigi mesajdir.
      3) DOGRULAMA SATIRLARI. Isaretlenen kutular ve yazilan aciklamalar
         (bkz. _dogrulama_satirlarini_isle).

    Hepsi ayni adimin transkript satirlarina islenir; blok yeniden
    cizildiginde kart canli akistaki son haliyle gorunur."""
    dolu = tamam.get("dolu")
    secili = tamam.get("secili")
    hedef = tamam.get("adim")
    if not hedef:
        return
    form_bitti = (dolu is None and secili is None)
    dg_bitti = not rozet and not karar
    for kayit in reversed(durum.get("_gecmis") or []):
        if form_bitti and dg_bitti:
            return
        if kayit.get("adim") != hedef:
            continue
        ekran = kayit.get("ekran")
        if not isinstance(ekran, dict):
            continue
        alan = ekran.get("secim_alani")
        if not dg_bitti and isinstance(alan, dict) \
                and alan.get("tip") == "dogrulama":
            if rozet:
                alan["rozet"] = rozet
            if karar:
                _dogrulama_satirlarini_isle(alan, karar)
            dg_bitti = True
            continue
        if form_bitti:
            continue
        if dolu is not None and isinstance(alan, dict) \
                and alan.get("tip") == dolu.get("tip"):
            # _ekran_sadelestir'den GECIRILIYOR: teyit kartinin taze
            # govdesi tip donusum tekliflerini de tasiyor (1.042 kolon x
            # alti secenek), dogrudan yazilsa satir EKRAN_SINIRI'ni asar
            # ve govde hic saklanmazdi.
            ekran["secim_alani"] = _ekran_sadelestir(dolu)
            form_bitti = True
        elif secili is not None and ekran.get("secenekler"):
            ekran["secili"] = secili
            form_bitti = True


def _gecmise_ekle_bolerek(durum, cevap, adim, ekran=None, rozet=None,
                          karar=None):
    """Bir turun cevabini IKI transkript satirina boler.

    Bir tur ilerlerken donen metin iki parcadir: BITEN adimin ozeti ve
    YENI adimin giris metni. Tek satir halinde yeni adimin anahtariyla
    yaziliyordu; sonuc, F5'ten sonra biten adimin hic blogu olmamasiydi
    (bkz. akis_sohbet._tamamlandi_yaz). Blok olmayinca sag ustundeki
    "Geri Dön" de olmuyor ve kullanici yalnizca son adimi goruyordu.

    Metin biten adimin ozetiyle BASLIYORSA ikiye ayrilir; aksi halde
    tek satir olarak yazilir ve ozet kendi satirini alir. Kart govdesi
    (`ekran`) YENI adima aittir: o turda cizilen kart odur."""
    tamam = durum.pop("_tamamlanan", None)
    metin = cevap or ""
    if tamam and tamam.get("adim"):
        # Once biten adimin kart govdeleri son haline getirilir; satirlar
        # transkriptte ONCEKI turlardan duruyor.
        _biten_adimi_guncelle(durum, tamam, rozet, karar)
        ozet = (tamam.get("metin") or "").strip()
        kalan = metin
        if ozet and metin.strip().startswith(ozet):
            kalan = metin.strip()[len(ozet):].lstrip("\n")
        # Ozet bos olsa bile satir YAZILIR: blogun var olmasi, icinde
        # metin olmasindan bagimsiz. Geri donus dugmesi bloga bagli.
        _gecmise_ekle(durum, "bot", ozet, tamam["adim"],
                      tamam.get("baslik") or akis.adim_basligi(tamam["adim"]))
        metin = kalan
    _gecmise_ekle(durum, "bot", metin, adim, akis.adim_basligi(adim), ekran)


def _karsilama_govdesi(durum):
    """Karsilama metni + ilk adimin secenek kartlari.

    ilk_soru() cagrisi SART: A/B/C kartlarini durum["_secenekler"]'e
    yazan o. DONDURDUGU METIN DE KULLANILIR: mod adiminin metni artik
    KARSILAMA'nin kendisi. Eskiden burada KARSILAMA ayrica ekleniyordu;
    adim da kendi metnini dondurunce ayni paragraf IKI KEZ basiliyordu
    (biri gecmisten, biri adim blogundan)."""
    metin = akis.ilk_soru(durum)
    govde = _yanit(durum, metin or akis.KARSILAMA)
    govde["metin"] = govde["cevap"]      # JS karsilamada "metin" bekliyor
    return govde


# Kart tiklamasiyla uretilen, kullanicinin YAZMADIGI mesajlar. Artik
# gecmise hic yazilmiyorlar; ama bu duzeltmeden ONCE kaydedilmis
# oturumlarda duruyorlar ve oturum acilinca ekranda tek harflik "A"
# balonu olarak beliriyorlar. Eski kayitlar icin okuma sirasinda elenir.
_SECIM_JETONLARI = {"a", "b", "c", "d", "1", "2", "3", "4",
                    "evet", "hayir", "hayır", "onayla", "onay", "tamam",
                    "devam", "geri", "geri dön", "değiştir", "degistir",
                    "onayla ve uygula", "analizi başlat", "analizi baslat",
                    "devam et", "tabloları onayla", "tablolari onayla",
                    "vazgeç", "vazgec", "atla", "iptal"}


def _gecmis_temizle(gecmis):
    """Eski oturumlardaki kart tiklamalarini ekran transkriptinden eler.

    ADIM ANAHTARSIZ cerceve metni (KARSILAMA) de elenir: eski
    oturumlarda blogu olmadan duruyor ve F5'ten sonra ikinci bir
    karsilama paragrafi olarak beliriyordu. Anahtarli olani KALIR:
    o, "Çalışma Başlangıcı" blogunun govdesidir ve adim gecildikten
    sonra blok icinde durmasi gerekir; canli cizimle cakismasi
    gecmisiCiz'deki son-satir elemesiyle onleniyor."""
    temiz = []
    for kayit in gecmis or []:
        if kayit.get("rol") == "bot" and not kayit.get("adim") \
                and _cerceve_metni_mi(kayit.get("metin")):
            continue
        if kayit.get("rol") == "kullanici":
            jeton = unicodedata.normalize(
                "NFKC", str(kayit.get("metin") or "")).strip().casefold()
            if jeton in _SECIM_JETONLARI:
                continue
        temiz.append(kayit)
    return temiz


def _surdurme_govdesi(durum):
    """Kayitli oturum: son yanit ve acik form/kartlar yeniden kurulur.
    Adim TEKRAR CALISTIRILMAZ; yalnizca kayitli durum gosterilir."""
    # KARSILAMA'YA DUSULMEZ.
    # Eskiden son yanit bossa KARSILAMA basiliyordu; ama bir adimin bos
    # metin dondurmesi NORMAL (karar kartin ya da secenek takiminin
    # icinde). Sonuc: kullanici "Veri ve Sözlük" adiminda F5 atinca
    # ekrana ikinci bir karsilama paragrafi geliyordu, hem de basliksiz
    # bir balon olarak. Metin yoksa ekrani adimin kendi karti kurar;
    # "kaldigi yerden yuklendi" seridi zaten ayrica basiliyor.
    metin = durum.get("_son_cevap") or ""
    govde = _yanit(durum, metin)
    govde["metin"] = govde["cevap"]
    govde["devam"] = True
    govde["devam_bilgi"] = _devam_bilgi(durum)
    govde["gecmis"] = _gecmis_temizle(durum.get("_gecmis"))
    return govde


def _oturum_var_mi(durum):
    return bool(durum.get("_gecmis") or durum.get("mod")
                or (durum.get("i") or 0) > 0)


def _devam_bilgi(durum):
    """'Kaldigi yerden yuklendi' mesajinin ayrintisi.

    Kullanici backend'i kapatip actiginda bile eski calismayi goruyor ve
    "sifirdan baslattim, bu nereden geldi?" diye sorabiliyor. Cevap:
    calisma Dataiku'daki managed folder'da, kullanici adina kayitli.
    Mesajin bunu ve en son NE ZAMAN / HANGI ADIMDA kalindigini soylemesi
    icin bu alanlari gonderiyoruz.
    """
    mod = durum.get("mod")
    sira = akis.adim_sirasi(mod)
    i = durum.get("i") or 0
    bilgi = {"adim_no": min(i + 1, len(sira)), "toplam": len(sira)}
    if 0 <= i < len(sira):
        # Sol paneldeki ad (gruplu adimda grubun adi): mesaj "Adım 3/7 -
        # Modelleme Tanımları" deyip listede o satir bulunmuyordu.
        bilgi["adim"] = _adim_gorunen_adi(sira[i])
    if durum.get("_son_islem"):
        bilgi["zaman"] = durum["_son_islem"]
    if durum.get("veri_seti"):
        bilgi["veri_seti"] = durum["veri_seti"]
    return bilgi


def _gecmisi_kirp(durum, hedef):
    """Geri donuste EKRAN GECMISINI de geri sarar.

    On yuz transkripti hedef adimdan itibaren siliyor (app.js
    transkriptiKirp), ama arka uctaki `_gecmis` dokunulmadan kaliyordu:
    F5'ten sonra kullanicinin az once sildigi bloklar geri geliyordu.
    Iki taraf ayni kurali uygular: hedefe ESIT ya da ondan SONRAKI
    adima ait ilk kayittan itibaren her sey duser."""
    sira = akis.adim_sirasi(durum.get("mod"))
    if hedef not in sira:
        return
    esik = sira.index(hedef)
    gecmis = durum.get("_gecmis") or []
    for i, kayit in enumerate(gecmis):
        adim = kayit.get("adim")
        if adim in sira and sira.index(adim) >= esik:
            durum["_gecmis"] = gecmis[:i]
            return


def _kaydet(anahtar, durum):
    """Durumu kaydeder ve son islem zamanini damgalar."""
    durum["_son_islem"] = datetime.datetime.now().isoformat(timespec="seconds")
    akis.durum_kaydet(anahtar, durum)


@app.route("/karsilama")
def karsilama_endpoint():
    """Yeni oturumda karsilama; kayitli oturumda kaldigi yerden devam.

    Istemci calisma kimligi GONDERMEZSE (ilk acilis, tarayici deposu
    engelli ya da temizlenmis) kullanicinin EN SON calismasi acilir;
    hic calismasi yoksa yeni bir numara (v1, v2 ...) ile baslar. Hangi calismanin
    acildigi yanitta "calisma_id" olarak doner, istemci onu saklar."""
    try:
        calisma = _temiz(request.args.get("oturum_id"))
        if not calisma:
            calisma = _son_calisma_id()
        try:
            anahtar = _oturum_anahtari(calisma)
        except CalismaErisimYok:
            # Tarayicida baskasinin calisma kimligi kayitli (ortak
            # bilgisayar): o calisma ACILMAZ, kullanicinin kendi son
            # calismasi acilir.
            calisma = _son_calisma_id()
            anahtar = _oturum_anahtari(calisma)
        durum = _durum_al(anahtar)

        if _oturum_var_mi(durum):
            govde = _surdurme_govdesi(durum)
            if _v_mi(calisma):
                govde["devam_bilgi"]["ad"] = calisma + (
                    " (%s kopyası)" % durum["_kopya_kaynagi"]
                    if durum.get("_kopya_kaynagi") else "")
        else:
            durum = akis.yeni_durum()
            durum["_oturum_id"] = anahtar
            if _v_mi(calisma):
                durum["_sahip"] = _sahip_ozeti()
            govde = _karsilama_govdesi(durum)
            durum["_tur_no"] = 0
            durum["_son_cevap"] = govde["cevap"]
            durum["_gecmis"] = []
            _ilk = akis.adim_anahtari(durum)
            _gecmise_ekle(durum, "bot", govde["cevap"], _ilk,
                          akis.adim_basligi(_ilk), _ekran_govdesi(govde))
            _kaydet(anahtar, durum)
            govde["devam"] = False
            govde["gecmis"] = durum["_gecmis"]

        govde["calisma_id"] = calisma
        return jsonify(govde)
    except Exception as e:
        return jsonify(_hata_govdesi("karsilama", e, "Karşılama yüklenemedi."))


@app.route("/durum")
def durum_endpoint():
    """Mevcut oturum + sohbet gecmisi. Sayfa yenilendiginde JS bunu kullanir."""
    try:
        calisma = _temiz(request.args.get("oturum_id")) or "ana"
        anahtar = _oturum_anahtari(calisma)
        durum = _durum_al(anahtar)

        if not _oturum_var_mi(durum):
            return jsonify({"var": False, "calisma_id": calisma})

        govde = _surdurme_govdesi(durum)
        govde["var"] = True
        govde["calisma_id"] = calisma
        return jsonify(govde)
    except Exception as e:
        govde = _hata_govdesi("durum", e, "Oturum bilgisi okunamadı.")
        govde["var"] = False
        return jsonify(govde)


@app.route("/mesaj", methods=["POST"])
def mesaj_endpoint():
    try:
        istek = request.get_json(force=True) or {}
        calisma = _calisma_id(istek)
        anahtar = _oturum_anahtari(calisma)
        durum = _durum_al(anahtar)

        son_tur = int(durum.get("_tur_no") or 0)
        try:
            gelen_tur = int(istek.get("tur_no") or 0)
        except (TypeError, ValueError):
            gelen_tur = 0

        # Idempotenslik: istemci timeout'ta vazgecip ayni turu tekrar
        # gonderirse adim TEKRAR UYGULANMAZ; kayitli yanit doner.
        if gelen_tur and gelen_tur <= son_tur and durum.get("_son_cevap"):
            govde = _yanit(durum, durum["_son_cevap"])
            govde["tekrar"] = True
            govde["calisma_id"] = calisma
            return jsonify(govde)

        mesaj = istek.get("mesaj", "")
        # Girdi dogrulama karti bir CUMLE degil, yapilandirilmis karar
        # gonderiyor ({"haric": [...], "ekle": [...]}). Govde oldugu gibi
        # akisa gecer; akis onu adimin `uygula` fonksiyonuna tasir. Eski
        # istemci bu alani hic gondermez, adim varsayilanini uygular.
        dogrulama = istek.get("dogrulama")
        # "adim": sohbetteki bir blogun sag ustundeki Geri Dön dugmesi.
        # Dogrudan o adima doner (yalnizca GERIYE; bkz. _hedefe_don).
        hedef_adim = istek.get("adim")
        cevap = akis.mesaj_isle(durum, mesaj,
                                dogrulama if isinstance(dogrulama, dict)
                                else None,
                                hedef_adim if isinstance(hedef_adim, str)
                                else None)

        # Geri donus GERCEKLESTIYSE ekran gecmisi de geri sarilir.
        # Kosul "istendi" degil "oldu": ileri atlama reddediliyor
        # (bkz. akis_sohbet._hedefe_don) ve o durumda gecmise
        # dokunulmamali.
        if isinstance(hedef_adim, str) \
                and akis.adim_anahtari(durum) == hedef_adim:
            _gecmisi_kirp(durum, hedef_adim)

        durum["_tur_no"] = gelen_tur if gelen_tur > son_tur else son_tur + 1
        durum["_son_cevap"] = cevap
        # Kart tiklamasi ("A", "evet", secenek degeri...) sohbet
        # gecmisine YAZILMAZ: canli oturumda kullanici balonu
        # basilmiyor, ama gecmis yeniden cizilince tek harflik balonlar
        # ortaya cikiyordu — kullanicinin hic gormedigi mesajlar.
        # Denetim izi `kutuk`te duruyor; `_gecmis` yalnizca EKRAN
        # transkriptidir.
        if not bool(istek.get("sessiz")):
            _gecmise_ekle(durum, "kullanici", mesaj)
        # Adim anahtari mesaj islendikten SONRA okunur: blok, akisin
        # ulastigi adima aittir ve "Geri Dön" oraya donmelidir.
        _adim = akis.adim_anahtari(durum)
        # Govde gecmisten ONCE kurulur: o turda cizilen kart govdesi
        # (secenekler / secim_alani) transkripte de yaziliyor, boylece
        # F5'ten sonra blok birebir yeniden ciziliyor.
        govde = _yanit(durum, cevap)
        # BITEN ADIMIN METNI KENDI BLOGUNA. Bir tur ilerlerken donen metin
        # iki parcadir: biten adimin ozeti ve yeni adimin giris metni.
        # Canli cizimde bu ayrim yoktu; ornegin "Dönem kolonunda tek değer
        # var" uyarisi MODELLEME TANIMLARI adiminin ciktisiyken SÖZLÜK
        # TANIMLARI blogunun icinde gorunuyordu. Transkript bu ayrimi
        # zaten yapiyor (bkz. _gecmise_ekle_bolerek); on yuz de ayni
        # ayrimla cizsin diye govdeye ekleniyor.
        _tamam = durum.get("_tamamlanan") or {}
        if _tamam.get("adim") and (_tamam.get("metin") or "").strip():
            _ozet = _tamam["metin"].strip()
            govde["tamamlanan"] = {
                "adim": _tamam["adim"],
                "baslik": _tamam.get("baslik")
                          or akis.adim_basligi(_tamam["adim"]),
                "metin": _ozet,
            }
            if (cevap or "").strip().startswith(_ozet):
                govde["cevap"] = (cevap or "").strip()[len(_ozet):].lstrip("\n")
                govde["metin"] = govde["cevap"]
        # Dogrulama karti karardan SONRA rozetini degistiriyor; o metin
        # kullanicinin gonderdigi mesajin ta kendisi.
        _rozet = mesaj if isinstance(dogrulama, dict) and mesaj else None
        _gecmise_ekle_bolerek(durum, cevap, _adim,
                              _ekran_govdesi(govde), _rozet,
                              dogrulama if isinstance(dogrulama, dict) else None)
        # ICINDE BULUNULAN adimin formu da her turda guncellenir.
        # Bir adim birden fazla ekran uretebiliyor (once form, sonra
        # girdi dogrulama karti); form gonderildigi an bostu ve adimin
        # ORTASINDA F5 atilinca o kart bos aciliyordu. Kullanici formu
        # doldurdugu icin degerler artik durumda; forma geri yaziliyor.
        _dolu, _secili = akis.mevcut_ekran(durum)
        _biten_adimi_guncelle(
            durum, {"adim": _adim, "dolu": _dolu, "secili": _secili})
        _kaydet(anahtar, durum)

        govde["tekrar"] = False
        govde["calisma_id"] = calisma
        return jsonify(govde)
    except Exception as e:
        return jsonify(_hata_govdesi("mesaj", e)), 200


@app.route("/oneriler")
def oneriler_endpoint():
    """Sozluk tanimlari kartindaki ACIKLAMA ONERILERININ ilerlemesi.

    1.000 tanimsiz kolon ONERI_GRUP'erli bolununce onlarca dil modeli
    cagrisi eder; hepsini tek istekte beklemek istegi zaman asimina
    ugratir ve kullaniciyi dakikalarca bos ekranda tutar. Kart hemen
    aciliyor, on yuz bu ucu yoklayarak satirlari dolduruyor.

    Oturum dosyasi OKUNMAZ, yazilmaz: is kaydi surec bellegindedir ve
    yalnizca is kimligiyle sorgulanir."""
    try:
        kayit = akis.oneri_isi_durumu(request.args.get("is"))
        if kayit is None:
            # Is bulunamadi (surec yeniden basladi ya da kayit dustu).
            # Hata DEGIL: on yuz kilidi acar, kullanici aciklamalari
            # kendisi yazar.
            return jsonify({"durum": "yok", "oneriler": {},
                            "toplam": 0, "biten": 0, "hata": ""})
        return jsonify(kayit)
    except Exception as e:
        return jsonify(_hata_govdesi("oneriler", e)), 200


@app.route("/sifirla", methods=["POST"])
def sifirla_endpoint():
    """YENI CALISMA ACAR; MEVCUT CALISMA SILINMEZ.

    Eskiden ayni dosyanin uzerine bos durum yaziliyordu: yanlislikla
    basilan "Yeni Çalışma" saatlerce suren calismayi geri donussuz
    siliyordu. Artik yeni bir sira numarasi aliniyor; eski calisma
    PROJE_HAFIZASI'nda duruyor ve "Çalışmalarım" listesinden kaldigi
    yerden acilabiliyor.

    Tek istisna: mevcut calisma HIC BASLAMAMISSA (baslangic secimi bile
    yapilmamis) ayni numara yeniden kullanilir - art arda basmak listeyi
    bos calismalarla doldurmasin."""
    try:
        istek = request.get_json(force=True) or {}
        calisma = _calisma_id(istek)
        bos_mu = False
        if _v_mi(calisma):
            try:
                bos_mu = not _calisma_basladi_mi(
                    _durum_al(_oturum_anahtari(calisma)))
            except Exception:
                bos_mu = False          # okunamayan kayit: uzerine YAZILMAZ
        if not bos_mu:
            calisma = _yeni_calisma_id()
        anahtar = _oturum_anahtari(calisma)

        # YENI anahtarin sozluk calisma kopyasi ve kategori kutugu
        # temizlenir (normalde yoktur; bakimla silinmis bir calismanin
        # numarasi yeniden verilmisse artik kalmasin). ESKI calismanin
        # kopyasina DOKUNULMAZ: o calisma geri acilabilir durumda.
        akis.calisma_kopyasi_sil(anahtar)

        durum = akis.yeni_durum()
        durum["_oturum_id"] = anahtar
        durum["_sahip"] = _sahip_ozeti()
        govde = _karsilama_govdesi(durum)       # _secenekler burada doluyor
        durum["_tur_no"] = 0
        durum["_son_cevap"] = govde["cevap"]
        durum["_gecmis"] = []
        _ilk = akis.adim_anahtari(durum)
        _gecmise_ekle(durum, "bot", govde["cevap"], _ilk,
                      akis.adim_basligi(_ilk), _ekran_govdesi(govde))
        _kaydet(anahtar, durum)

        govde["devam"] = False
        govde["gecmis"] = durum["_gecmis"]
        govde["calisma_id"] = calisma
        return jsonify(govde)
    except Exception as e:
        return jsonify(_hata_govdesi("sifirla", e, "Oturum sıfırlanamadı."))


# ===========================================================================
# CALISMALARIM
# ---------------------------------------------------------------------------
# Kullanicinin PROJE_HAFIZASI'ndaki butun calismalari. Liste dosya
# adlarindan cikariliyor, ayrintilar (son islem, adim, veri seti) her
# calismanin kendi durum dosyasindan okunuyor. Durum dosyasi sohbet
# gecmisini tasidigi icin buyuk olabilir; en yeni CALISMA_LISTE_SINIRI
# kadari okunur.
# ===========================================================================
CALISMA_LISTE_SINIRI = 30


def _hafiza_yollari():
    try:
        return list(_hafiza().list_paths_in_partition())
    except Exception as e:
        _hata_kaydet("calismalar:liste", e)
        return []


def _calisma_kimlikleri(yollar=None):
    """Bu kullanicinin calismalari: (v_listesi, eski_liste).

    v_listesi CALISMA_KAYDI'ndan (sahibi bu kullanici olanlar, yeniden
    eskiye); eski liste onceki iki bicimin dosya adlarindan."""
    yollar = _hafiza_yollari() if yollar is None else yollar
    ben = _sahip_ozeti()
    v = [k for k, d in _calisma_kaydi_oku().items()
         if _v_mi(k) and (d or {}).get("sahip") == ben
         and not (d or {}).get("silindi")]
    sayili_re = re.compile(r"^/oturum_%s_(\d{1,6})\.json$"
                           % re.escape(_kullanici_on_eki()))
    eski_re = re.compile(r"^/oturum_%s([A-Za-z0-9_-]+)\.json$"
                         % re.escape(_eski_on_ek()))
    eski = []
    for y in yollar:
        m = sayili_re.match(y) or eski_re.match(y)
        if m:
            eski.append(m.group(1))
    return sorted(v, key=lambda k: int(k[1:]), reverse=True), eski


def _calisma_basladi_mi(durum):
    """Baslangic secimi yapildi mi? _oturum_var_mi'dan FARKLI: o, karsilama
    mesaji gecmise yazildigi anda True donuyor; burada soru "kullanici bu
    calismada bir sey yapti mi". Hic baslamamis calisma listede
    gosterilmez ve Yeni Çalışma onun numarasini yeniden kullanir."""
    return bool(durum.get("mod") or (durum.get("i") or 0) > 0)


def _yeni_calisma_id():
    """Siradaki PROJE GENELINDE tekil numara ("v7"); sahipligini kaydeder.

    Iki kullanici ayni anda "Yeni Çalışma"ya basarsa ayni numarayi
    alabilirler; yazdiktan sonra kayit yeniden okunur, numara
    baskasina gectiyse bir sonrakine gecilir."""
    ben = _sahip_ozeti()
    for _deneme in range(5):
        kayit = _calisma_kaydi_oku()
        sayilar = [int(V_KALIP.match(k).group(1)) for k in kayit if _v_mi(k)]
        for y in _hafiza_yollari():
            m = re.match(r"^/v(\d{1,6})/", y)
            if m:
                sayilar.append(int(m.group(1)))
        yeni = "v%d" % (max(sayilar or [0]) + 1)
        kayit[yeni] = {"sahip": ben, "olusturma": datetime.datetime.now()
                       .isoformat(timespec="seconds")}
        _calisma_kaydi_yaz(kayit)
        if (_calisma_kaydi_oku().get(yeni) or {}).get("sahip") == ben:
            return yeni
    raise RuntimeError("Yeni çalışma numarası alınamadı.")


def _adim_gorunen_adi(anahtar):
    """Adimin SOL PANELDEKI adi: gruplu adimda grubun adi."""
    try:
        _grup, grup_baslik = akis.adim_grubu(anahtar)
    except Exception:
        grup_baslik = ""
    return grup_baslik or (akis.ADIMLAR.get(anahtar) or {}).get("baslik") or anahtar


def _calisma_ozeti(calisma, durum):
    mod = durum.get("mod")
    sira = akis.adim_sirasi(mod)
    i = durum.get("i") or 0
    ozet = {
        "calisma_id": calisma,
        "ad": calisma if _v_mi(calisma) else "Eski Kayıt",
        "zaman": durum.get("_son_islem"),
        "baslamis": _calisma_basladi_mi(durum),
        "adim_no": min(i + 1, len(sira)),
        "toplam": len(sira),
        "veri_seti": durum.get("veri_seti"),
        "mod": mod,
    }
    if 0 <= i < len(sira):
        ozet["adim"] = _adim_gorunen_adi(sira[i])
    ozet["secimler"] = _calisma_secimleri(durum)
    if durum.get("_kopya_kaynagi"):
        ozet["kaynak"] = durum["_kopya_kaynagi"]
    return ozet


def _calisma_secimleri(durum):
    """Calismada o ana kadar verilmis kararlar: [[etiket, deger], ...].

    Baslangic ekranindaki "Önceki Çalışmalar" listesi bunlari gosteriyor;
    kullanici hangi calismanin hangisi oldugunu numaradan degil
    kararlarindan taniyor."""
    sec = []
    mod = durum.get("mod")
    if mod:
        sec.append(["Başlangıç", "%s · %s" % (mod, akis.MOD_ADLARI.get(mod, ""))])
    if durum.get("ham_tablolar"):
        sec.append(["Kaynak Tablolar", ", ".join(map(str, durum["ham_tablolar"]))])
    if durum.get("veri_seti"):
        sec.append(["Veri Seti", str(durum["veri_seti"])])
    kaynak_sz = sorted(set((durum.get("kaynak_sozlukler") or {}).values()))
    if kaynak_sz:
        sec.append(["Kaynak Sözlükler", ", ".join(kaynak_sz)])
    elif durum.get("sozluk"):
        sec.append(["Sözlük", str(durum["sozluk"])])
    meta = durum.get("meta") or {}
    for anahtar, etiket in (("target", "Hedef Değişken"), ("id", "Kimlik Kolonu"),
                            ("donem", "Dönem Kolonu")):
        if meta.get(anahtar):
            sec.append([etiket, str(meta[anahtar])])
    haric = durum.get("haric_kolonlar") or []
    if haric:
        sec.append(["Süreç Dışı Kolon", "%d kolon" % len(haric)])
    return sec


def _calismalar(en_fazla=CALISMA_LISTE_SINIRI, aktif=None):
    """Calisma ozetleri, EN SON ISLEM GORENDEN baslayarak.

    Hic baslamamis (bos) calismalar listeye girmez; su an acik olan
    haric - kullanici hangisinde oldugunu gormeli."""
    yeni, eski = _calisma_kimlikleri()
    adaylar = yeni + eski
    cikti = []
    for calisma in adaylar[:max(en_fazla, CALISMA_LISTE_SINIRI)]:
        try:
            durum = _durum_al(_oturum_anahtari(calisma))
        except Exception as e:
            cikti.append({"calisma_id": calisma, "ad": calisma,
                          "hata": "Kayıt okunamadı (%s)."
                                  % _hata_kaydet("calismalar:oku", e)})
            continue
        oz = _calisma_ozeti(calisma, durum)
        if not oz["baslamis"] and calisma != aktif:
            continue
        cikti.append(oz)
    # Zaman ISO bicimde: metin siralamasi zaman siralamasi. Zamani
    # olmayan (okunamayan) kayitlar sona.
    cikti.sort(key=lambda c: c.get("zaman") or "", reverse=True)
    return cikti[:en_fazla]


def _son_calisma_id():
    """Kimliksiz acilista acilacak calisma: en son islem goren. Hicbiri
    baslamamissa en buyuk numarali (bos) calisma yeniden kullanilir -
    her F5'te yeni bos bir calisma acilmasin. Hic yoksa yeni numara."""
    son = _calismalar(en_fazla=1)
    if son:
        return son[0]["calisma_id"]
    yeni, _ = _calisma_kimlikleri()
    return yeni[0] if yeni else _yeni_calisma_id()


@app.route("/calisma_kopyala", methods=["POST"])
def calisma_kopyala_endpoint():
    """Onceki bir calismanin KOPYASIYLA yeni calisma baslatir.

    Orijinale DOKUNULMAZ. Kopya ayni kararlari, sohbet gecmisini ve
    calisma klasorundeki dosyalari (sozluk kopyasi, birlestirme sonucu,
    AMP ciktilari) tasir; kullanici herhangi bir adima geri donup
    duzeltip devam edebilir.

    Hedef: su an acik calisma HIC BASLAMAMISSA onun numarasi (baslangic
    ekranindan secildiginde bos bir numara harcanmasin), degilse yeni
    numara."""
    try:
        istek = request.get_json(force=True) or {}
        kaynak = _temiz(istek.get("kaynak"))
        mevcut = _calisma_id(istek)
        kaynak_anahtar = _oturum_anahtari(kaynak)       # erisim denetimi
        durum = _durum_al(kaynak_anahtar)
        if not _calisma_basladi_mi(durum):
            raise ValueError("Kopyalanacak çalışma henüz başlamamış.")

        hedef = None
        if _v_mi(mevcut) and mevcut != kaynak:
            try:
                if not _calisma_basladi_mi(_durum_al(_oturum_anahtari(mevcut))):
                    hedef = mevcut
            except Exception:
                hedef = None
        hedef = hedef or _yeni_calisma_id()
        hedef_anahtar = _oturum_anahtari(hedef)

        # Kaynak klasordeki dosyalar hedef klasore. Kayit dosyasinin
        # kendisi atlanir; asagida yeni kimlikle yaziliyor.
        hafiza = _hafiza()
        on_ek = "/%s/" % kaynak_anahtar
        for yol in _hafiza_yollari():
            if not yol.startswith(on_ek) or yol.endswith("/calisma.json"):
                continue
            with hafiza.get_download_stream(yol) as akim:
                icerik = akim.read()
            hafiza.upload_stream("/%s/%s" % (hedef_anahtar, yol[len(on_ek):]),
                                 icerik)

        # Durumdaki klasor yollari yeni klasoru gostersin.
        metin = json.dumps(durum, ensure_ascii=False).replace(
            on_ek, "/%s/" % hedef_anahtar)
        yeni = json.loads(metin)
        yeni["_oturum_id"] = hedef_anahtar
        yeni["_sahip"] = _sahip_ozeti()
        yeni["_kopya_kaynagi"] = kaynak
        # Eski bicimli AMP klasoru kaynaga ait: kopya kendi klasorune yazar.
        yeni.pop("_amp_klasor", None)
        yeni.pop("_oneri_is", None)
        _kaydet(hedef_anahtar, yeni)
        return jsonify({"calisma_id": hedef, "kaynak": kaynak})
    except Exception as e:
        return jsonify(_hata_govdesi("calisma_kopyala", e,
                                     "Çalışma kopyalanamadı."))


@app.route("/calisma_sil", methods=["POST"])
def calisma_sil_endpoint():
    """Bir calismayi "Çalışmalarım"dan KALICI olarak siler.

    Silinen: calismanin klasorundeki her dosya (/v3/...: calisma kaydi,
    sozluk kopyasi, birlestirme sonucu, AMP ciktilari). Eski bicimli
    kayitta tek dosya (/oturum_<anahtar>.json).
    SILINMEYEN: Dataiku dataset'leri. Onlar projede ortak; baska bir
    calisma ya da kullanici ayni dataset'i kullaniyor olabilir.

    Numara CALISMA_KAYDI'nda "silindi" isaretiyle kalir (bkz.
    _v_silindi_mi). Yalnizca sahibi silebilir: _oturum_anahtari baskasinin
    calismasinda CalismaErisimYok atar.

    Silinen calisma su an ACIK olansa yanit "sonraki"yi tasir: istemci
    kullanicinin en son calismasina (yoksa yeni bos bir calismaya) gecer."""
    try:
        istek = request.get_json(force=True) or {}
        hedef = _temiz(istek.get("calisma"))
        if not hedef:
            raise ValueError("Silinecek çalışma belirtilmedi.")
        mevcut = _calisma_id(istek)
        anahtar = _oturum_anahtari(hedef)              # erisim denetimi

        hafiza = _hafiza()
        if _v_mi(hedef):
            on_ek = "/%s/" % anahtar
            silinecek = [y for y in _hafiza_yollari() if y.startswith(on_ek)]
        else:
            silinecek = [akis._yol(anahtar)]
        for yol in silinecek:
            try:
                hafiza.delete_path(yol)
            except Exception as e:
                _hata_kaydet("calisma_sil:dosya", e)

        if _v_mi(hedef):
            kayit = _calisma_kaydi_oku()
            girdi = dict(kayit.get(hedef) or {"sahip": _sahip_ozeti()})
            girdi["silindi"] = datetime.datetime.now().isoformat(timespec="seconds")
            kayit[hedef] = girdi
            _calisma_kaydi_yaz(kayit)

        govde = {"tamam": True, "silinen": hedef}
        if hedef == mevcut:
            govde["sonraki"] = _son_calisma_id()
        return jsonify(govde)
    except CalismaErisimYok as e:
        return jsonify({"hata": True, "metin": str(e)})
    except Exception as e:
        return jsonify(_hata_govdesi("calisma_sil", e,
                                     "Çalışma silinemedi."))


@app.route("/calismalar")
def calismalar_endpoint():
    """Çalışmalarım listesi. Hicbir calismayi DEGISTIRMEZ; secilen
    calisma istemci tarafinda /karsilama?oturum_id=<sira> ile acilir."""
    try:
        aktif = _temiz(request.args.get("oturum_id"))
        return jsonify({"calismalar": _calismalar(aktif=aktif),
                        "aktif": aktif,
                        "klasor": getattr(akis, "HAFIZA_FOLDER", None)})
    except Exception as e:
        return jsonify(_hata_govdesi("calismalar", e,
                                     "Çalışma listesi okunamadı."))


# ===========================================================================
# BOLME AYARLARI
# ---------------------------------------------------------------------------
# NEDEN AYRI UC
#   Bolme bir sohbet adimi degil, HAZIRLIK sekmesindeki bir form.
#   /mesaj'dan gecirmek akis konumunu oynatir ve her kaydetmede butun
#   panelleri yeniden hesaplamayi gerektirirdi.
#
# NEDEN KILIT ONAYA BAGLI
#   Bolme uygulandiktan sonra SFA, baz, secim gibi adimlar o bolmenin
#   uzerinde calisti. Bolmeyi sessizce degistirmek o analizleri yanlis
#   yapmaz, GECERSIZ yapar; kullanici neyi gecersiz kildigini gormeden
#   onaylamamali. Bu yuzden kilitli formda "onay": true beklenir.
# ===========================================================================
@app.route("/bolme_kaydet", methods=["POST"])
def bolme_kaydet_endpoint():
    try:
        istek = request.get_json(force=True) or {}
        anahtar = _oturum_anahtari(_calisma_id(istek))
        durum = _durum_al(anahtar)

        form = akis.bolme_formu(durum)
        if form.get("kilitli") and not istek.get("onay"):
            return jsonify({"tamam": False,
                            "onay_gerekli": True,
                            "hata": form.get("kilit_nedeni")
                                    or "Bölme kilitli."})

        # "oneri": true -> formdan gelen degerler DEGIL, sistemin onerisi
        # kaydedilir ("Önerilen Ayarları Uygula" dugmesi). Oneri bir
        # metin degil uygulanabilir bir ayar kumesi; on yuzun onu
        # yeniden kurup gondermesi, iki tarafin ayri oneri hesaplamasi
        # demekti (bkz. akis_durum.bolme_onerisi).
        if istek.get("oneri"):
            sonuc = akis.bolme_oneriyi_uygula(durum)
        else:
            sonuc = akis.bolme_kaydet(durum, istek.get("bolme"))
        if not sonuc.get("tamam"):
            return jsonify({"tamam": False,
                            "hata": sonuc.get("hata")
                                    or "Bölme ayarları kaydedilemedi."})

        # Sohbetteki bolme karti ACIKSA yerinde tazeleniyor: ozet,
        # uyarilar ve kisitlar ayara bagli. Tazelenmezse kullanici
        # kaydettigi ayari kartta goremiyor ve ikinci kez kaydetmeye
        # calisiyordu (bkz. akis_faz01.bolme_kartini_tazele).
        mod = istek.get("mod")
        if mod in ("oneri", "ozel"):
            durum["_bolme_mod"] = mod
        kart = akis.bolme_kartini_tazele(durum)

        _kaydet(anahtar, durum)
        return jsonify({"tamam": True,
                        "bolme": sonuc.get("bolme") or {},
                        "ozet": sonuc.get("ozet") or "",
                        "uyarilar": list(sonuc.get("uyarilar") or []),
                        "secim_alani": kart,
                        "bolme_formu": akis.bolme_formu(durum)})
    except Exception as e:
        kod = _hata_kaydet("bolme_kaydet", e)
        return jsonify({"tamam": False,
                        "hata": "Bölme ayarları kaydedilemedi (%s)." % kod})


# ===========================================================================
# MODEL GELISTIRME DOKUMANI
# ---------------------------------------------------------------------------
# NEDEN AYRI UC, /karsilama VE /mesaj GOVDESINE EKLENMIYOR
#   Dokuman on bes bolum, tablolar ve her bolumun duz metin karsiligiyla
#   birlikte gelen BUYUK bir govdedir. Her sohbet turunde gondermek,
#   kullanici OZET sayfasini hic acmasa bile her yanitin uzerine onlarca
#   kilobayt bindirirdi. OZET sayfasi acildiginda bir kez istenir.
#
# NEDEN /dokuman_bolum DURUMU KAYDEDIYOR
#   Duzenleme durum dosyasinda yasar (durum["dokuman"]["duzenlemeler"]).
#   Yalnizca bellekte tutulup bir sonraki /mesaj turunu beklemek,
#   kullanicinin yazdigi metni sekme kapaninca yok ederdi.
# ===========================================================================
@app.route("/dokuman")
def dokuman_endpoint():
    """OZET sayfasinin cizdigi doküman gövdesi."""
    try:
        anahtar = _oturum_anahtari(request.args.get("oturum_id"))
        durum = _durum_al(anahtar)
        # Eski bolum anahtarlarinin yeni bolumlere gocu OKURKEN yapilir.
        # Burada KAYDEDIYORUZ: goc kalici olmazsa her acilista yeniden
        # calisir ve dusen metin kutuge her seferinde yeniden yazilirdi.
        if akis.dokuman_goc_uygula(durum):
            _kaydet(anahtar, durum)
        return jsonify({"dokuman": akis.dokuman(durum)})
    except Exception as e:
        kod = _hata_kaydet("dokuman", e)
        return jsonify({"dokuman": None,
                        "hata": "Doküman hazırlanamadı (%s)." % kod,
                        "hata_kodu": kod})


@app.route("/dokuman_bolum", methods=["POST"])
def dokuman_bolum_endpoint():
    """Bir bölümün kullanıcı metnini kaydeder. Boş metin düzenlemeyi SİLER."""
    try:
        istek = request.get_json(force=True) or {}
        anahtar = _oturum_anahtari(_calisma_id(istek))
        durum = _durum_al(anahtar)

        sonuc = akis.dokuman_bolum_kaydet(durum, istek.get("anahtar"),
                                          istek.get("metin"))
        if not sonuc.get("tamam"):
            return jsonify({"tamam": False,
                            "hata": sonuc.get("hata")
                                    or "Bölüm kaydedilemedi."})
        _kaydet(anahtar, durum)
        return jsonify({"tamam": True, "bolum": sonuc.get("bolum")})
    except Exception as e:
        kod = _hata_kaydet("dokuman_bolum", e)
        return jsonify({"tamam": False,
                        "hata": "Bölüm kaydedilemedi (%s)." % kod})


# Word'un beklediği MIME. Yanlış tip gönderilirse tarayıcı dosyayı .zip
# diye indirir ve kullanıcı açamaz.
DOCX_MIME = ("application/vnd.openxmlformats-officedocument."
             "wordprocessingml.document")


@app.route("/dokuman_word")
def dokuman_word_endpoint():
    """Dokümanı .docx olarak indirir.

    Hata hâlinde JSON DEĞİL düz metin döner: tarayıcı bu adrese bir
    indirme olarak gidiyor, JSON gövdesi kullanıcıya bozuk bir dosya
    olarak inerdi."""
    try:
        anahtar = _oturum_anahtari(request.args.get("oturum_id"))
        durum = _durum_al(anahtar)
        veri = akis.dokuman_word(durum)
    except Exception as e:
        kod = _hata_kaydet("dokuman_word", e)
        return Response(
            "Doküman Word olarak oluşturulamadı (hata kodu: %s). Bu kodu "
            "ilettiğinizde kayıtlardan ayrıntıya ulaşılabilir." % kod,
            status=500, mimetype="text/plain; charset=utf-8")

    return Response(veri, mimetype=DOCX_MIME, headers={
        "Content-Disposition": 'attachment; filename="%s"'
                               % akis.DOKUMAN_DOSYA_ADI,
        # Doküman her çağrıda durumdan yeniden üretilir; ara katmanın
        # eski bir kopyayı sunması "düzenledim ama dosyada yok" demektir.
        "Cache-Control": "no-store",
    })


# ===========================================================================
# SOZLUK KATEGORI DUZENLEME
# ---------------------------------------------------------------------------
# NEDEN AYRI UC
#   Kategori duzeltmesi bir sohbet adimi degil; tabloda bir hucreyi
#   degistirmek. /mesaj'dan gecirmek, akis konumunu oynatmadan durum
#   kaydetmeyi ve her duzenlemede butun panelleri yeniden hesaplamayi
#   gerektirirdi.
#
# NEDEN TUR NUMARASI YOK
#   /mesaj'daki idempotenslik sayaci, ADIM IKI KEZ UYGULANMASIN diye
#   var. Kategori yazmak dogasi geregi idempotent: ayni feature'a ayni
#   kategoriyi ikinci kez yazmak dosyayi degistirmez ve kutuge ikinci
#   satir dusurmez (bkz. sozluk_calisma.kategori_yaz). Bu yuzden
#   sozlesmedeki govdeye sayac alani EKLENMEDI.
#
# NEDEN ORIJINAL SOZLUK YAZILMIYOR
#   fe_agent.sozluk_calisma yalnizca PROJE_HAFIZASI'ndaki oturum
#   kopyasina yazar. Kopya yoksa yazmayi REDDEDER; backend orijinale
#   dusurecek bir yol sunmaz.
# ===========================================================================
def _kategori_durumu(istek):
    """(oturum_anahtari, durum) — durum yalnizca KAYNAK ETIKETI icin.

    Sozlugun gorunen adi durumda duruyor; oturum anahtarinda degil.
    Durum okunamazsa yazma yine de yapilir, etiket genellesir."""
    anahtar = _oturum_anahtari(_calisma_id(istek))
    try:
        return anahtar, _durum_al(anahtar)
    except Exception as e:
        _hata_kaydet("sozluk_kategori:durum", e)
        return anahtar, None


@app.route("/sozluk_kategori", methods=["POST"])
def sozluk_kategori_endpoint():
    """Tek bir degiskenin kategorisini calisma kopyasina ANINDA yazar."""
    try:
        istek = request.get_json(force=True) or {}
        anahtar, durum = _kategori_durumu(istek)
        sonuc = akis.kategori_yaz(anahtar, istek.get("feature"),
                                  istek.get("kategori"), durum=durum)
        if not sonuc.get("tamam"):
            return jsonify({"tamam": False,
                            "hata": sonuc.get("hata")
                                    or "Kategori yazılamadı."})
        return jsonify({"tamam": True,
                        "feature": sonuc.get("feature"),
                        "kategori": sonuc.get("kategori"),
                        "sozluk_kaynak": sonuc.get("sozluk_kaynak")})
    except Exception as e:
        kod = _hata_kaydet("sozluk_kategori", e)
        return jsonify({"tamam": False,
                        "hata": "Kategori yazılamadı (%s)." % kod})


@app.route("/sozluk_kategori_toplu", methods=["POST"])
def sozluk_kategori_toplu_endpoint():
    """Birden cok kategori degisikligini TEK yazma ile isler."""
    try:
        istek = request.get_json(force=True) or {}
        degisiklikler = istek.get("degisiklikler")
        if not isinstance(degisiklikler, list):
            return jsonify({"tamam": False, "yazilan": 0,
                            "hatalar": ["Değişiklik listesi beklenen "
                                        "biçimde gelmedi."]})
        anahtar, durum = _kategori_durumu(istek)
        sonuc = akis.kategori_yaz_toplu(anahtar, degisiklikler, durum=durum)
        return jsonify({"tamam": bool(sonuc.get("tamam")),
                        "yazilan": int(sonuc.get("yazilan") or 0),
                        "hatalar": list(sonuc.get("hatalar") or [])})
    except Exception as e:
        kod = _hata_kaydet("sozluk_kategori_toplu", e)
        return jsonify({"tamam": False, "yazilan": 0,
                        "hatalar": ["Kategoriler yazılamadı (%s)." % kod]})


# ===========================================================================
# BOLME ONCESI SON TEYIT — SOZLUK TANIMI VE SUREC DISI KOLONLAR
# ---------------------------------------------------------------------------
# Sag paneldeki VERI & SOZLUK sekmesi bolme oncesi son teyit yuzeyidir:
# kullanici bir kolonun tanimini duzeltir ya da kolonu surec disina alir.
# Ikisi de sohbet adimi degil, tabloda bir hucre/kutu degisikligidir; bu
# yuzden /mesaj'dan degil kendi uclarindan gecer (bkz. /sozluk_kategori
# ustundeki gerekce — ayni gerekce).
#
# ORIJINAL SOZLUK YAZILMAZ: tanim yazma fe_agent.sozluk_calisma.tanim_yaz
# uzerinden yalnizca oturumun CALISMA KOPYASINA gider; kopya yoksa yazma
# reddedilir.
# ===========================================================================
@app.route("/sozluk_tanim", methods=["POST"])
def sozluk_tanim_endpoint():
    """Tek bir degiskenin sozluk tanimini calisma kopyasina ANINDA yazar."""
    try:
        istek = request.get_json(force=True) or {}
        anahtar = _oturum_anahtari(_calisma_id(istek))
        durum = _durum_al(anahtar)
        tamam, neden = akis.sozluk_tanim_yaz(
            durum, istek.get("kolon"), istek.get("tanim"))
        if not tamam:
            return jsonify({"tamam": False,
                            "hata": neden or "Sözlük tanımı yazılamadı."})
        # Acik teyit kartinin govdesi durumda duruyor; tazelenmezse
        # kullanici adimin ortasinda F5 atinca yazdigi tanim kayboluyor
        # (tanim calisma kopyasina yazildi ama ekranda eski hali kalir).
        akis.teyit_kartini_tazele(durum, istek.get("kolon"),
                                  str(istek.get("tanim") or "").strip())
        _kaydet(anahtar, durum)
        return jsonify({"tamam": True,
                        "kolon": str(istek.get("kolon") or "").strip(),
                        "tanim": str(istek.get("tanim") or "").strip(),
                        "sozluk_kaynak": akis.sozluk_kaynak_etiketi(durum)})
    except Exception as e:
        kod = _hata_kaydet("sozluk_tanim", e)
        return jsonify({"tamam": False,
                        "hata": "Sözlük tanımı yazılamadı (%s)." % kod})


XLSX_MIME = ("application/vnd.openxmlformats-officedocument."
             "spreadsheetml.sheet")


@app.route("/degisken_excel")
def degisken_excel_endpoint():
    """Değişken listesini .xlsx olarak indirir.

    tur=liste  -> sohbetteki karar tablosunun aynısı (altı kolon)
    tur=sozluk -> sağ paneldeki açıklama tablosu (üç kolon)

    KAPI: sözlük teyidi KAYDEDİLMEDEN indirilemez. Kaydedilmemiş bir
    liste, kullanıcının henüz vermediği kararı dosyaya yazmak olurdu;
    o dosya da ekibe gidip "karar buydu" diye okunurdu.

    Hata hâlinde JSON DEĞİL düz metin döner (bkz. /dokuman_word):
    tarayıcı buraya bir indirme olarak geliyor."""
    tur = (request.args.get("tur") or "liste").strip()
    genis = tur != "sozluk"
    try:
        anahtar = _oturum_anahtari(request.args.get("oturum_id"))
        durum = _durum_al(anahtar)
        if not akis.teyit_kaydedildi_mi(durum):
            return Response(
                "Değişken listesi henüz kaydedilmedi. Sohbetteki Sözlük "
                "Teyidi adımında listeyi kaydettikten sonra indirebilirsiniz.",
                status=409, mimetype="text/plain; charset=utf-8")
        veri = akis.teyit_excel(durum, genis=genis)
    except Exception as e:
        kod = _hata_kaydet("degisken_excel", e)
        return Response(
            "Değişken listesi Excel olarak oluşturulamadı (hata kodu: %s). "
            "Bu kodu ilettiğinizde kayıtlardan ayrıntıya ulaşılabilir." % kod,
            status=500, mimetype="text/plain; charset=utf-8")

    return Response(veri, mimetype=XLSX_MIME, headers={
        "Content-Disposition": 'attachment; filename="%s"'
                               % (akis.TEYIT_EXCEL_ADI if genis
                                  else akis.SOZLUK_EXCEL_ADI),
        # Liste her çağrıda durumdan yeniden üretiliyor; ara katmanın eski
        # bir kopyayı sunması "tanımı düzelttim ama dosyada yok" demektir.
        "Cache-Control": "no-store",
    })


@app.route("/tip_degistir", methods=["POST"])
def tip_degistir_endpoint():
    """Sozluk teyidinde secilen tip donusumunu TAM VERIYLE dogrular.

    Karttaki liste kucuk bir ornekle hazirlaniyor; burada ayni donusum
    kolonun TAMAMINA uygulaniyor. Tek deger bile takilirsa secim
    kaydedilmez ve ug eski degere doner - kullanicinin ekranda gordugu
    tip ile veri setindeki tip hicbir anda ayrismiyor.

    Bos kod secimi geri almak demektir ve daima kabul edilir."""
    try:
        istek = request.get_json(force=True) or {}
        anahtar = _oturum_anahtari(_calisma_id(istek))
        durum = _durum_al(anahtar)
        sonuc = akis.tip_secimi_dogrula(
            durum, istek.get("kolon"), istek.get("kod"))
        if not sonuc.get("tamam"):
            return jsonify({"tamam": False,
                            "hata": sonuc.get("mesaj")
                            or "Tip değiştirilemedi."})
        _kaydet(anahtar, durum)
        return jsonify({"tamam": True,
                        "kolon": str(istek.get("kolon") or "").strip(),
                        "kod": str(istek.get("kod") or "").strip(),
                        "tip": sonuc.get("tip") or "",
                        "ozet": akis.teyit_ozeti(durum)})
    except Exception as e:
        kod = _hata_kaydet("tip_degistir", e)
        return jsonify({"tamam": False,
                        "hata": "Tip değiştirilemedi (%s)." % kod})


@app.route("/haric_kolonlar", methods=["POST"])
def haric_kolonlar_endpoint():
    """Surec disinda birakilacak kolon listesini durumda gunceller.

    Liste TAMAMEN DEGISTIRILIR, eklenmez: ekrandaki onay kutulari o anki
    tam kararı tasiyor. Isaretin kaldirilmasi da bir karardir ve ancak
    tam liste yazilirsa geri alinabilir.

    Kolon adlari istemciden geliyor; veri setinde GERCEKTEN bulunan
    adlarla sinirlaniyor. Olmayan bir adi surec disi listesine koymak,
    sonraki adimlarda hicbir sey yapmayan ama raporda gorunen bir kayit
    birakirdi."""
    try:
        istek = request.get_json(force=True) or {}
        kolonlar = istek.get("kolonlar")
        if not isinstance(kolonlar, list):
            return jsonify({"tamam": False,
                            "hata": "Kolon listesi beklenen biçimde gelmedi."})
        anahtar = _oturum_anahtari(_calisma_id(istek))
        durum = _durum_al(anahtar)

        ozet = (durum.get("profil") or {}).get("kolon_ozet")
        bilinen = {str(o["ad"]) for o in (ozet if isinstance(ozet, list) else [])
                   if isinstance(o, dict) and o.get("ad")}
        istenen = [str(k).strip() for k in kolonlar if str(k).strip()]
        secili = sorted({k for k in istenen if not bilinen or k in bilinen})

        # HEDEF / KİMLİK / DÖNEM ASLA SÜREÇ DIŞI BIRAKILAMAZ. Karttaki
        # kutu kilitli ama kilit yalnızca görsel; istek doğrudan da
        # gönderilebilir. Hedefi süreç dışı bırakmak modeli hedefsiz,
        # kimliği bırakmak bölmeyi kimliksiz bırakırdı ve bu, hiçbir
        # uyarı vermeden birkaç adım sonra patlardı.
        korunan = {str(v) for v in (durum.get("meta") or {}).values() if v}
        reddedilen = sorted(korunan & set(secili))
        secili = [k for k in secili if k not in korunan]

        # TERS YONDE ZORUNLU: tek deger tasidigi icin dusurulen donem
        # kolonu surec disinda KALMAK zorunda. Karttaki kutu kilitli ama
        # kilit yalnizca gorsel; istek dogrudan da gonderilebilir ve o
        # kolon geri alinirsa modele her satirda ayni sabiti tasiyan bir
        # degisken girerdi.
        zorunlu_disi = str((durum.get("_donem_dusuruldu") or "")).strip()
        geri_alinan = ""
        if zorunlu_disi and zorunlu_disi not in secili:
            secili = sorted(set(secili) | {zorunlu_disi})
            geri_alinan = zorunlu_disi

        durum["haric_kolonlar"] = secili
        # Kart govdesi de tazelenir: aksi halde adimin ortasinda F5
        # atilinca isaretlenen kutular bosalmis gorunuyordu.
        akis.teyit_kartini_tazele(durum)
        _kaydet(anahtar, durum)
        # Teyit kartinin ozet satiri ("N değişken · M süreç dışı · ...")
        # bu listeden besleniyor. Tazesini burada donmezsek kart, kullanici
        # kutulari isaretledikten sonra bile eski sayiyi gosterir.
        return jsonify({"tamam": True, "kolonlar": secili,
                        "haric": len(secili),
                        # Reddedilenler SESSIZ DUSURULMEZ: on yuz kutuyu
                        # geri alip sebebini yaziyor.
                        "reddedilen": reddedilen
                                      + ([geri_alinan] if geri_alinan else []),
                        "hata": ("%s süreç dışı bırakılamaz: modelleme "
                                 "tanımlarında seçilen hedef / kimlik / "
                                 "dönem kolonu." % ", ".join(reddedilen))
                                if reddedilen else
                                ("%s süreç dışında kalmak zorunda: dönem "
                                 "kolonu olarak seçildi ama tek değer "
                                 "taşıyor." % geri_alinan)
                                if geri_alinan else "",
                        "ozet": akis.teyit_ozeti(durum)})
    except Exception as e:
        kod = _hata_kaydet("haric_kolonlar", e)
        return jsonify({"tamam": False,
                        "hata": "Süreç dışı kolonlar yazılamadı (%s)." % kod})
