# -*- coding: utf-8 -*-
"""fe_agent/sozluk_calisma.py - sozlugun OTURUMA OZEL calisma kopyasi.

NEDEN BOYLE BIR KOPYA VAR
  Degisken sozlugu kurumsal bir tablodur: baska ekipler okur, baska
  akislar besler. Analist calisma sirasinda bir kolonun kategorisini
  duzeltmek istiyor. Bu duzeltmeyi kaynak dataset'e yazmak, tek bir
  oturumun gecici kararini herkesin gordugu tanima donusturmek demektir
  ve geri alinamaz. Bu yuzden sozluk baglandiginda bir KOPYA cikarilir;
  oturum boyunca butun okuma ve butun yazma bu kopyaya gider. Orijinal
  sozluk dataset'i HICBIR KOSULDA yazilmaz - bu modulde write_with_schema
  cagrisi yoktur.

NEDEN OTURUM BASINA BIR DOSYA
  Iki analist ayni sozlukle ayni anda calisabilir. Tek bir ortak kopya
  olsaydi birinin kategori duzeltmesi digerinin ekranina duser, kimin
  yazdigi belli olmazdi. Dosya adi oturum anahtarini tasir; oturum
  anahtari zaten kullanici kimligini iceriyor (bkz. backend
  _oturum_anahtari), dolayisiyla iki analist birbirinin kopyasini
  goremez.

NEDEN KATEGORI KOLONU TOLERANSLI ARANIYOR
  Sozluk elle hazirlanmis bir tablodan gelmis olabilir: "Kategori",
  "KATEGORİ" (Turkce noktali I), "kategori" hepsi ayni kolondur. Adi
  birebir arayan kod her seferinde yeni bir KATEGORI kolonu acip
  eskisini gorunmez birakir; kullanici "kategorilerim nereye gitti"
  diye sorar.

NEDEN KOPYA YOKSA ORIJINALE DUSULUYOR
  PROJE_HAFIZASI erisilemiyorsa ya da kopya henuz cikarilmadiysa
  sozlugu hic gostermemek, calismayi durdurmaktan daha kotudur. Okuma
  orijinale duser ama bunu SESSIZCE yapmaz: kaynak etiketi
  "(calisma kopyasi)" ibaresini kaybeder ve panelde kopyanin olmadigi
  yazar. Yazma ise duSMEZ - kopya yoksa kategori yazilamaz.
"""

import io
import re
import time

import pandas as pd

from fe_agent import kutuk as kutuk_mod
from fe_agent.akis_durum import _folder, sozluk_orijinal_oku


DOSYA_ADI = "sozluk_calisma.csv"

# Kopyada kategori tutulan kolonun KANONIK adi. Sozlukte baska bir
# yazimla varsa (Kategori / KATEGORİ) o kolon KULLANILIR, yenisi acilmaz.
KATEGORI_KOLONU = "KATEGORI"

# Kopyada aciklama/tanim tutulan kolonun KANONIK adi. Kategori kolonunda
# oldugu gibi, sozlukte baska bir yazimla varsa o kolon kullanilir.
TANIM_KOLONU = "ACIKLAMA"

# Degisiklik kutugunde KAYNAK alani. Bir sozluk tanimi ya dil modelinin
# onerdigi ve kullanicinin OLDUGU GIBI onayladigi metindir, ya da
# kullanicinin kendi yazdigidir. Denetim acisindan ayni sey degiller:
# TMD'de "bu tanimi kim yazdi" sorusunun cevabi bu alandan okunur.
KAYNAK_LLM = "llm onerisi (kullanici onayladi)"
KAYNAK_KULLANICI = "kullanici yazdi"

# Kategorisi olmayan degiskenin panelde ve kategori listesinde aldigi
# etiket. Sozlukte bu anlama gelen birden fazla yazim var; hepsi tek
# etikete indirgenir, yoksa filtre listesinde "tanımsız" ve
# "(kategorisiz)" yan yana cikip ayni seyi iki kez gosterir.
KATEGORISIZ = "(kategorisiz)"

_BOS_KATEGORI = {"", "-", "-", "nan", "none", "null",
                 "tanimsiz", "tanımsız", "belirsiz", KATEGORISIZ}

# Kategori metni serbest girilir; sinirsiz uzunluk sozluk dosyasini
# sisirir ve panelde satiri tasirir.
KATEGORI_MAKS = 60

# Ayni istek icinde panel + ust serit + uc birlikte kopyayi okuyor.
# Kisa omurlu onbellek; her yazmada acikca dusurulur.
ONBELLEK_OMRU_SN = 5.0
_ONBELLEK = {}

# Calisma kopyasi kayipken YENIDEN KURMA denemesinin sikligi. Klasore
# gercekten yazilamiyorsa her panel cizimi bir yazma denemesi yapmasin.
KURTARMA_ARALIGI_SN = 60.0
_KURTARMA_DENEMESI = {}


# ---------------------------------------------------------------------------
# AD NORMALIZASYONU
# ---------------------------------------------------------------------------
# sozluk.py'deki harita ile ayni mantik; burada kopyasi duruyor ki bu
# modul sozluk uretimine bagimli olmasin (kopya, sozluk uretilmeden de
# -Mod A'da hazir sozlukle- cikarilabiliyor).
_TR_HARF = {"Ç": "C", "Ğ": "G", "İ": "I", "Ö": "O", "Ş": "S", "Ü": "U",
            "ç": "C", "ğ": "G", "ı": "I", "ö": "O", "ş": "S", "ü": "U"}


def _normalize_ad(ad):
    s = "".join(_TR_HARF.get(c, c) for c in str(ad)).upper()
    return re.sub(r"[^A-Z0-9]+", "", s)


def _kolon_ara(df, adaylar):
    """Kolonu buyuk/kucuk harf ve Turkce karakter farkindan BAGIMSIZ arar."""
    if df is None or not len(df.columns):
        return None
    harita = {}
    for kol in df.columns:
        harita.setdefault(_normalize_ad(kol), kol)
    for aday in adaylar:
        bulunan = harita.get(_normalize_ad(aday))
        if bulunan is not None:
            return bulunan
    return None


def kategori_kolonu_bul(df):
    """Sozlukteki kategori kolonunun GERCEK adi; yoksa None."""
    return _kolon_ara(df, ("KATEGORI", "KATEGORİ", "Kategori", "CATEGORY"))


def degisken_kolonu_bul(df):
    """Degisken adini tasiyan kolon.

    Sozluk tablosunun ILK kolonu degisken adidir (sozluk.tablo_olustur
    bu sozle yaziyor); yine de bilinen adlar once denenir ki elle
    hazirlanmis, kolon sirasi farkli bir sozlukte de dogru kolon
    bulunsun."""
    if df is None or not len(df.columns):
        return None
    bulunan = _kolon_ara(df, ("DEGISKEN", "DEĞİŞKEN", "FEATURE", "KOLON",
                              "VARIABLE", "ALAN"))
    return bulunan if bulunan is not None else df.columns[0]


def tanim_kolonu_bul(df):
    """Aciklama/tanim kolonu; yoksa None."""
    return _kolon_ara(df, ("ACIKLAMA", "AÇIKLAMA", "TANIM", "DESCRIPTION",
                           "ACIKLAMASI"))


def kategori_sadelestir(deger):
    """Bos sayilan butun yazimlari tek etikete indirger."""
    metin = "" if deger is None else str(deger).strip()
    if metin.lower() in _BOS_KATEGORI or metin in _BOS_KATEGORI:
        return KATEGORISIZ
    return metin


# ---------------------------------------------------------------------------
# DOSYA YOLU VE OKUMA/YAZMA
# ---------------------------------------------------------------------------
def _temiz_anahtar(oturum_anahtari):
    """akis_durum._yol ile AYNI karakter kumesi.

    Iki farkli oturum anahtari temizlendikten sonra ayni klasore
    dusmemeli; bu yuzden temizlik kaynakta degil, anahtarin tamaminda
    yapiliyor ve bos kalirsa yol uretilmiyor."""
    return re.sub(r"[^A-Za-z0-9_-]", "", str(oturum_anahtari or ""))


def kopya_yolu(oturum_anahtari):
    """PROJE_HAFIZASI icindeki yol; anahtar cozulemezse None."""
    temiz = _temiz_anahtar(oturum_anahtari)
    if not temiz:
        return None
    return "/%s/%s" % (temiz, DOSYA_ADI)


def _onbellek_dusur(yol=None):
    if yol is None:
        _ONBELLEK.clear()
        return
    _ONBELLEK.pop(yol, None)


def _oku_yoldan(yol):
    with _folder().get_download_stream(yol) as s:
        ham = s.read()
    return pd.read_csv(io.BytesIO(ham))


def kopya_oku(oturum_anahtari):
    """Calisma kopyasi DataFrame'i; yoksa ya da okunamazsa None."""
    yol = kopya_yolu(oturum_anahtari)
    if not yol:
        return None

    kayit = _ONBELLEK.get(yol)
    if kayit is not None:
        zaman, tablo = kayit
        if (time.time() - zaman) <= ONBELLEK_OMRU_SN:
            return tablo.copy()
        _ONBELLEK.pop(yol, None)

    try:
        tablo = _oku_yoldan(yol)
    except Exception:
        return None
    _ONBELLEK[yol] = (time.time(), tablo)
    return tablo.copy()


def kopya_var_mi(oturum_anahtari):
    return kopya_oku(oturum_anahtari) is not None


def _kopya_yaz(oturum_anahtari, tablo):
    """Kopyayi diske yazar. Doner: (yol, hata_metni)."""
    yol = kopya_yolu(oturum_anahtari)
    if not yol:
        return None, ("Oturum anahtarı çözülemediği için sözlük çalışma "
                      "kopyası oluşturulamadı.")
    try:
        _folder().upload_stream(yol, tablo.to_csv(index=False).encode("utf-8"))
    except Exception as e:
        return None, ("Sözlük çalışma kopyası proje hafızasına yazılamadı "
                      "(%s)." % str(e)[:140])
    _onbellek_dusur(yol)
    return yol, None


def _kategori_kolonu_garanti(tablo):
    """Kategori kolonunu bulur; yoksa ACAR. Doner: (tablo, kolon_adi).

    Sozlukte kategori kolonu hic olmayabilir (elle hazirlanmis iki
    kolonluk bir tablo). Kategori duzenlemesinin calisabilmesi icin
    kolon kopyada olusturulur - orijinal tabloya dokunulmaz.

    KOLON TIPI ZORLANIYOR: kategorisi hic girilmemis bir sozluk CSV'ye
    yazilip geri okundugunda kolon bastan asagi bos oldugu icin float64
    gelir. Pandas o kolona metin yazmayi reddediyor ("Invalid value
    'Finansal' for dtype 'float64'") ve ilk kategori duzenlemesi
    coküyordu."""
    kolon = kategori_kolonu_bul(tablo)
    if kolon is None:
        tablo = tablo.copy()
        kolon = KATEGORI_KOLONU
        tablo[kolon] = ""
    elif tablo[kolon].dtype != object:
        tablo = tablo.copy()
        tablo[kolon] = tablo[kolon].astype(object).where(
            tablo[kolon].notna(), "")
    return tablo, kolon


def _tanim_kolonu_garanti(tablo):
    """Aciklama/tanim kolonunu bulur; yoksa ACAR. Doner: (tablo, kolon_adi).

    Gerekce kategori kolonuyla ayni: sozluk elle hazirlanmis iki kolonluk
    bir tablo olabilir, ya da tanim kolonu bastan asagi bos oldugu icin
    CSV'den float64 gelmis olabilir. Ikinci durumda pandas o kolona metin
    yazmayi reddeder."""
    kolon = tanim_kolonu_bul(tablo)
    if kolon is None:
        tablo = tablo.copy()
        kolon = TANIM_KOLONU
        tablo[kolon] = ""
    elif tablo[kolon].dtype != object:
        tablo = tablo.copy()
        tablo[kolon] = tablo[kolon].astype(object).where(
            tablo[kolon].notna(), "")
    return tablo, kolon


# ---------------------------------------------------------------------------
# KOPYA KURULUMU  (sozluk baglandiginda bir kez)
# ---------------------------------------------------------------------------
def kopya_kur(durum, tablo=None):
    """Sozluk baglandiginda calisma kopyasini cikarir.

    tablo verilmezse orijinal sozluk okunur. Doner: (yol, hata_metni).
    Hata ASLA yukari firlatilmaz: kopya cikarilamasa da calisma devam
    etmeli, yalnizca kaynak etiketi "calisma kopyasi" demez."""
    oturum = (durum or {}).get("_oturum_id")
    if not oturum:
        return None, ("Oturum anahtarı bilinmediği için sözlük çalışma "
                      "kopyası oluşturulamadı.")
    try:
        if tablo is None:
            tablo = _orijinal_oku(durum)
        if tablo is None or not len(tablo.columns):
            return None, "Sözlük okunamadığı için çalışma kopyası çıkarılamadı."
        tablo, _ = _kategori_kolonu_garanti(tablo)
        return _kopya_yaz(oturum, tablo)
    except Exception as e:
        return None, ("Sözlük çalışma kopyası çıkarılamadı (%s)."
                      % str(e)[:140])


def _orijinal_oku(durum):
    """Orijinal sozluk; bulunamazsa None.

    akis_durum.sozluk_orijinal_oku KOPYAYA BAKMAZ - kopyayi cikarirken
    kaynak olarak tam da bu gerekiyor, yoksa kopya kendini kaynak alip
    ilk kurulumda bos kalirdi. Orada sozluk hic yoksa AdimHatasi atiliyor;
    burada "kopya cikarilamadi" bir adim hatasi degil, yalnizca kopyasiz
    calismak demektir."""
    try:
        return sozluk_orijinal_oku(durum or {})
    except Exception:
        return None


# ---------------------------------------------------------------------------
# OKUMA - oturum boyunca butun sozluk okumalarinin gectigi yer
# ---------------------------------------------------------------------------
def calisma_df(durum):
    """Calisma kopyasi varsa DataFrame'i, yoksa None.

    akis_durum.sozluk_oku bunu once dener; None gelirse orijinale duser."""
    return kopya_oku((durum or {}).get("_oturum_id"))


def _kopyayi_kurtar(durum):
    """Sozluk BAGLI ama calisma kopyasi yoksa kopyayi yeniden cikarir.

    NEDEN GEREKLI (kullanici bildirimi: "sağ paneldeki değişken sözlük
    tanımlarına bakarken sözlük çalışma kopyası yok, tanım salt okunur
    yazıyor"): kopya yalnizca sozluk baglanirken bir kez cikariliyordu.
    O dosya sonradan kaybolursa (proje hafizasi temizlendi, kopya adimi
    atlanmis eski bir oturum, yazma o anda basarisiz olmustu) panel
    sessizce SALT OKUNUR'a dusuyor ve geri donus yolu kalmiyordu -
    kullanici tanimi duzenleyemiyor ama sebebini de degistiremiyor.

    Kopya ORIJINALDEN yeniden cikariliyor: kaybolan kopyadaki
    duzenlemeler zaten kayip, yeniden kurmak durumu kotulestirmiyor.
    ORIJINAL SOZLUGE YAZILMIYOR - kopya_kur yalnizca okuyor.

    Deneme KURTARMA_ARALIGI_SN'de birden sik tekrarlanmaz: klasore
    gercekten yazilamiyorsa her panel cizimi bir yazma denemesi
    yapmamali."""
    if not sozluk_adi(durum):
        return None                      # sozluk hic baglanmamis
    yol = kopya_yolu((durum or {}).get("_oturum_id"))
    if not yol:
        return None
    son = _KURTARMA_DENEMESI.get(yol)
    if son is not None and (time.time() - son) < KURTARMA_ARALIGI_SN:
        return None
    _KURTARMA_DENEMESI[yol] = time.time()
    yeni, _hata = kopya_kur(durum)
    if not yeni:
        return None
    return kopya_oku((durum or {}).get("_oturum_id"))


def sozluk_tablosu(durum):
    """Doner: (tablo, kopya_mi). Hicbiri okunamazsa (None, False).

    Panel ve feature tablosu bu fonksiyondan gecer; boylece "hangi
    kaynaktan okundu" sorusunun tek bir cevabi olur."""
    tablo = calisma_df(durum)
    if tablo is not None:
        return tablo, True
    # Kopya yok ama sozluk bagli: kurtarmayi dene (bkz. _kopyayi_kurtar).
    tablo = _kopyayi_kurtar(durum)
    if tablo is not None:
        return tablo, True
    try:
        return _orijinal_oku(durum), False
    except Exception:
        return None, False


def sozluk_adi(durum):
    """Kullaniciya gosterilecek sozluk adi (dataset ya da yedek dosya)."""
    durum = durum or {}
    ad = durum.get("sozluk")
    if ad:
        return str(ad)
    yedek = durum.get("sozluk_yedek")
    if yedek:
        return str(yedek).lstrip("/")
    return None


def kaynak_etiketi(durum):
    """Ust seritte ve panelde gorunen sozluk adi. Sozluk hic baglanmadiysa
    None - cagiran taraf "seçilmedi" yazar.

    NEDEN "(çalışma kopyası)" EKI KALDIRILDI
      Etiket bir sure "<AD>  (çalışma kopyası)" doneruyordu. Kopya bir
      UYGULAMA DETAYI: kullanicinin kartta gormek istedigi sey, uzerinde
      calisilan sozlugun adi ve NEREDEN geldigi. "Orijinal yazilmaz"
      guvencesi sohbetteki adim metninde duruyor; duzenlemenin acik olup
      olmadigini ise feature tablosunun 'duzenlenebilir' alani tasiyor -
      bu etiketin o isi ikinci kez yapmasi gerekmiyordu."""
    return sozluk_adi(durum)


# ---------------------------------------------------------------------------
# KATEGORI YAZMA  -  ANINDA, YALNIZCA KOPYAYA
# ---------------------------------------------------------------------------
def _sonuc(tamam, **ek):
    govde = {"tamam": bool(tamam)}
    govde.update(ek)
    return govde


def _kategori_dogrula(kategori):
    """Doner: (temiz_kategori, hata). Bos birakmak MESRUDUR: kullanici
    yanlis atadigi kategoriyi geri almak isteyebilir; bu durumda deger
    "(kategorisiz)" olarak yazilir."""
    metin = "" if kategori is None else str(kategori).strip()
    if len(metin) > KATEGORI_MAKS:
        return None, ("Kategori adı en fazla %d karakter olabilir."
                      % KATEGORI_MAKS)
    if kategori_sadelestir(metin) == KATEGORISIZ:
        return "", None
    return metin, None


def _yazilacak_tablo(oturum_anahtari):
    """Kopyayi yazilmaya hazir halde doner: (tablo, degisken_kolon,
    kategori_kolon, hata). Kopya yoksa YAZMAYI REDDEDER - orijinale
    dusmek, orijinali yazmak anlamina gelirdi."""
    tablo = kopya_oku(oturum_anahtari)
    if tablo is None:
        return None, None, None, (
            "Sözlüğün oturuma özel çalışma kopyası bulunamadı; kategori "
            "yazılamaz. Orijinal sözlüğe yazmıyorum. Sözlük adımını "
            "yeniden çalıştırırsanız kopya çıkarılır.")
    degisken = degisken_kolonu_bul(tablo)
    if degisken is None:
        return None, None, None, ("Çalışma kopyasında değişken adı kolonu "
                                  "bulunamadı.")
    tablo, kategori = _kategori_kolonu_garanti(tablo)
    return tablo, degisken, kategori, None


def _uygula(tablo, degisken_kolon, kategori_kolon, feature, kategori):
    """Tek bir feature'in kategorisini tabloya isler.

    Doner: (satir_sayisi, eski_deger). Ayni feature sozlukte birden
    fazla satirda geciyorsa HEPSI guncellenir: yarisi eski, yarisi yeni
    kategori tasiyan bir sozluk, hangi satirin okundugu'na gore farkli
    cevap verir."""
    hedef = str(feature).strip()
    maske = tablo[degisken_kolon].astype(str).str.strip() == hedef
    adet = int(maske.sum())
    if not adet:
        return 0, None
    eski = kategori_sadelestir(tablo.loc[maske, kategori_kolon].iloc[0])
    tablo.loc[maske, kategori_kolon] = kategori
    return adet, eski


def kategori_yaz(oturum_anahtari, feature, kategori, durum=None):
    """Tek bir degiskenin kategorisini ANINDA calisma kopyasina yazar.

    Doner: {"tamam", "feature", "kategori", "sozluk_kaynak"} ya da
    {"tamam": False, "hata"}. Istisna firlatmaz; uc katmani govdeyi
    oldugu gibi kullanicaya gosterebilsin diye her hata metne cevrilir.

    durum yalnizca KAYNAK ETIKETI icindir: sozlugun gorunen adi durumda
    duruyor, oturum anahtarinda degil. Verilmezse etiket genellesir."""
    ad = "" if feature is None else str(feature).strip()
    if not ad:
        return _sonuc(False, hata="Hangi değişkenin kategorisi "
                                  "güncellenecek belirtilmedi.")

    temiz, hata = _kategori_dogrula(kategori)
    if hata:
        return _sonuc(False, feature=ad, hata=hata)

    tablo, degisken_kolon, kategori_kolon, hata = _yazilacak_tablo(
        oturum_anahtari)
    if hata:
        return _sonuc(False, feature=ad, hata=hata)

    adet, eski = _uygula(tablo, degisken_kolon, kategori_kolon, ad, temiz)
    if not adet:
        return _sonuc(False, feature=ad,
                      hata="'%s' sözlükte bulunamadı; kategori yazılmadı."
                           % ad)

    yeni = kategori_sadelestir(temiz)
    if eski == yeni:
        # Ayni deger yeniden gonderildi (cift tiklama / yeniden deneme).
        # Dosyaya dokunmuyoruz ve kutuge ikinci bir satir dusmuyoruz;
        # islem yine BASARILI sayilir, cunku istenen son durum zaten bu.
        return _sonuc(True, feature=ad, kategori=yeni,
                      sozluk_kaynak=_kaynak_etiketi_yaz(oturum_anahtari, durum))

    yol, hata = _kopya_yaz(oturum_anahtari, tablo)
    if hata:
        return _sonuc(False, feature=ad, hata=hata)

    kutuk_mod.degisiklik_dus(oturum_anahtari, [
        {"ALAN": "KATEGORI", "ANAHTAR": ad, "ESKI": eski, "YENI": yeni,
         "KAYNAK": yol}])
    return _sonuc(True, feature=ad, kategori=yeni,
                  sozluk_kaynak=_kaynak_etiketi_yaz(oturum_anahtari, durum))


def kategori_yaz_toplu(oturum_anahtari, degisiklikler, durum=None):
    """Birden cok kategori degisikligini TEK yazma ile isler.

    Doner: {"tamam", "yazilan", "hatalar", "sozluk_kaynak"}.
    Tek tek kategori_yaz cagirmak her degisiklikte dosyayi yeniden
    yazardi; 300 satirlik bir toplu duzenlemede bu 300 yazma demektir.
    Gecersiz satirlar atlanir ve "hatalar" listesinde raporlanir -
    biri yuzunden digerleri kaybolmaz."""
    kayitlar = list(degisiklikler or [])
    if not kayitlar:
        return _sonuc(True, yazilan=0, hatalar=[],
                      sozluk_kaynak=_kaynak_etiketi_yaz(oturum_anahtari, durum))

    tablo, degisken_kolon, kategori_kolon, hata = _yazilacak_tablo(
        oturum_anahtari)
    if hata:
        return _sonuc(False, yazilan=0, hatalar=[hata],
                      sozluk_kaynak=_kaynak_etiketi_yaz(oturum_anahtari, durum))

    yazilan, hatalar, kutuk_satirlari = 0, [], []
    for kayit in kayitlar:
        if not isinstance(kayit, dict):
            hatalar.append("Beklenmeyen biçimde bir değişiklik atlandı.")
            continue
        ad = str(kayit.get("feature") or "").strip()
        if not ad:
            hatalar.append("Değişken adı boş olan bir satır atlandı.")
            continue
        temiz, kat_hata = _kategori_dogrula(kayit.get("kategori"))
        if kat_hata:
            hatalar.append("%s: %s" % (ad, kat_hata))
            continue
        adet, eski = _uygula(tablo, degisken_kolon, kategori_kolon, ad, temiz)
        if not adet:
            hatalar.append("%s sözlükte bulunamadı." % ad)
            continue
        yeni = kategori_sadelestir(temiz)
        if eski == yeni:
            continue
        yazilan += 1
        kutuk_satirlari.append({"ALAN": "KATEGORI", "ANAHTAR": ad,
                                "ESKI": eski, "YENI": yeni})

    if yazilan:
        yol, hata = _kopya_yaz(oturum_anahtari, tablo)
        if hata:
            return _sonuc(False, yazilan=0, hatalar=hatalar + [hata],
                          sozluk_kaynak=_kaynak_etiketi_yaz(oturum_anahtari, durum))
        for satir in kutuk_satirlari:
            satir["KAYNAK"] = yol
        kutuk_mod.degisiklik_dus(oturum_anahtari, kutuk_satirlari)

    return _sonuc(not hatalar, yazilan=yazilan, hatalar=hatalar,
                  sozluk_kaynak=_kaynak_etiketi_yaz(oturum_anahtari, durum))


# ---------------------------------------------------------------------------
# YENI TANIM EKLEME  -  ANINDA, YALNIZCA KOPYAYA
# ---------------------------------------------------------------------------
def _tanimi_isle(oturum, ad, tanim, kat):
    """Tanimi calisma kopyasina isler ve dosyaya yazar.

    Doner: (True, eski_tanim) ya da (False, neden). Kolon kopyada ZATEN
    VARSA aciklamasi guncellenir, ikinci satir ACILMAZ: ayni degiskenin
    iki tanimi olan bir sozlukte hangi satirin okundugu'na gore farkli
    cevap cikar.

    satir_ekle ile tanim_yaz ayni govdeyi paylassin diye ayrildi; iki
    yerde iki kopya olursa biri duzeltilip digeri unutuluyor. Fark yalniz
    kutuge dusen KAYNAK alaninda."""
    try:
        tablo = kopya_oku(oturum)
        if tablo is None:
            return False, ("Sözlüğün oturuma özel çalışma kopyası "
                           "bulunamadı; tanım yazılamadı. Orijinal sözlüğe "
                           "hiçbir koşulda yazılmaz.")

        degisken = degisken_kolonu_bul(tablo)
        if degisken is None:
            return False, ("Çalışma kopyasında değişken adı kolonu "
                           "bulunamadı.")

        tablo, kategori_kolon = _kategori_kolonu_garanti(tablo)
        tablo, tanim_kolon = _tanim_kolonu_garanti(tablo)

        maske = tablo[degisken].astype(str).str.strip() == ad
        if int(maske.sum()):
            ham = tablo.loc[maske, tanim_kolon].iloc[0]
            eski = "" if pd.isna(ham) else str(ham)
            tablo.loc[maske, tanim_kolon] = tanim
            if kat:
                tablo.loc[maske, kategori_kolon] = kat
        else:
            eski = ""
            satir = {c: "" for c in tablo.columns}
            satir[degisken] = ad
            satir[tanim_kolon] = tanim
            satir[kategori_kolon] = kat
            tablo = pd.concat([tablo, pd.DataFrame([satir])],
                              ignore_index=True)
    except Exception as e:
        return False, ("Sözlük çalışma kopyasına tanım işlenemedi (%s)."
                       % str(e)[:140])

    yol, hata = _kopya_yaz(oturum, tablo)
    if hata:
        return False, hata
    return True, eski


def tanim_yaz(durum, kolon, tanim):
    """Bir kolonun sozluk tanimini ANINDA calisma kopyasina yazar.

    Sag paneldeki "SÖZLÜK TANIMI" hucresi buraya baglidir: panel bolme
    oncesi son teyit yuzeyi oldugu icin kullanici orada yanlis ya da
    eksik bir tanimi duzeltebilmeli.

    ORIJINAL SOZLUGE ASLA YAZILMAZ - satir_ekle ile ayni kural. Yazma
    _kopya_yaz'dan gecer; kopya yoksa (False, neden) doner ve cagiran
    taraf hucreyi eski degerine geri alir.

    BOS TANIM MESRUDUR: kullanici yanlis bir tanimi silmek isteyebilir.
    Bos deger kopyaya oldugu gibi yazilir, kolon o anda "sözlükte tanımı
    yok" durumuna doner. Reddetmek, hucreyi sikismis gosterirdi.

    Kutuge her zaman KAYNAK_KULLANICI ile duSER: bu metni kullanici
    yazdi, dil modeli onermedi.

    Doner: (True, "") ya da (False, "<neden>"). Istisna firlatmaz."""
    oturum = (durum or {}).get("_oturum_id")
    ad = "" if kolon is None else str(kolon).strip()
    if not ad:
        return False, "Hangi kolonun tanımı yazılacağı belirtilmedi."

    metin = "" if tanim is None else str(tanim).strip()

    # Kopya kayipsa once KURTAR: okuma yolu bunu zaten yapiyor
    # (sozluk_tablosu), ama panel cizilmeden dogrudan yazma gelirse
    # yazma "kopya bulunamadi" diye reddedilirdi. Ayni kurtarma,
    # ayni sinirlarla; orijinal sozluge yine yazilmiyor.
    if kopya_oku(oturum) is None:
        _kopyayi_kurtar(durum)

    tamam, sonuc = _tanimi_isle(oturum, ad, metin, "")
    if not tamam:
        return False, sonuc
    if sonuc == metin:
        # Ayni deger yeniden gonderildi (odak kaybinda ikinci istek):
        # kutuge bos bir satir dusurmuyoruz, islem yine BASARILI.
        return True, ""

    kutuk_mod.degisiklik_dus(oturum, [
        {"ALAN": "sozluk", "ANAHTAR": ad, "ESKI": sonuc, "YENI": metin,
         "KAYNAK": KAYNAK_KULLANICI}])
    return True, ""


def satir_ekle(durum, kolon, aciklama, kategori="", oneri=None):
    """Sozlukte tanimi olmayan bir kolona tanim yazar.

    NEDEN YALNIZCA KOPYA: kullanici girdi dogrulama ekraninda bir kolonu
    "sozluge ekle" diye isaretledigi anda bu tanim OTURUMUN tanimidir,
    kurumun tanimi degil. Orijinal sozluk dataset'ine yazmak, tek bir
    analistin o anki kararini herkesin gordugu tanima cevirmek olurdu.
    Bu yuzden yazma _kopya_yaz'dan gecer; bu modulde orijinali yazan
    hicbir cagri yoktur.

    Kolon kopyada ZATEN VARSA aciklamasi guncellenir, ikinci satir
    ACILMAZ: ayni degiskenin iki tanimi olan bir sozlukte hangi satirin
    okundugu'na gore farkli cevap cikar.

    oneri: dil modelinin onerdigi metin. Kullanicinin onayladigi aciklama
    bu metinle BIREBIR ayniysa kutuge "llm onerisi (kullanici onayladi)",
    degilse "kullanici yazdi" dusulur - bkz. KAYNAK_LLM.

    Doner: (True, "") ya da (False, "<neden>"). Istisna firlatmaz;
    CAGIRAN False gelince kolonu haric tutar."""
    oturum = (durum or {}).get("_oturum_id")
    ad = "" if kolon is None else str(kolon).strip()
    if not ad:
        return False, "Hangi kolonun tanımı ekleneceği belirtilmedi."

    tanim = "" if aciklama is None else str(aciklama).strip()
    if not tanim:
        return False, "Sözlüğe eklenecek kolonun açıklaması boş olamaz."

    kat, hata = _kategori_dogrula(kategori)
    if hata:
        return False, hata

    tamam, sonuc = _tanimi_isle(oturum, ad, tanim, kat)
    if not tamam:
        return False, sonuc
    eski = sonuc

    kaynak = KAYNAK_LLM if (oneri and str(oneri).strip() == tanim) \
        else KAYNAK_KULLANICI
    kutuk_mod.degisiklik_dus(oturum, [
        {"ALAN": "sozluk", "ANAHTAR": ad, "ESKI": eski, "YENI": tanim,
         "KAYNAK": kaynak}])
    return True, ""


def _kaynak_etiketi_yaz(oturum_anahtari, durum):
    """Yazma yanitinda gosterilecek kaynak etiketi.

    durum verildiyse sozlugun gercek adi kullanilir
    ("DEGISKENLER  (çalışma kopyası)"). Verilmediyse yalnizca kopyanin
    var olup olmadigi bilinir; uydurma ad yazmaktansa genel etiket
    doner."""
    if durum is not None:
        etiket = kaynak_etiketi(durum)
        if etiket:
            return etiket
    if kopya_oku(oturum_anahtari) is None:
        return None
    return "sözlük çalışma kopyası"


def calisma_kopyasi_sil(oturum_anahtari):
    """Oturumun sozluk calisma kopyasini ve degisiklik kutugunu siler.

    "Yeni calisma" durumu sifirliyor ama kopya diskte kaliyordu; yeni
    calisma ayni sozlugu bagladigi anda onceki calismanin kategori
    duzenlemelerini sessizce devraliyordu. Surec ici onbellek de
    dusurulur, aksi halde silinen dosya okunmaya devam ederdi.

    Doner: silinen yol listesi. Dosya hic olusmamis olabilir; bu bir
    hata degildir, o yuzden sessizce gecilir."""
    yol = kopya_yolu(oturum_anahtari)
    if not yol:
        return []

    silinen = []
    for hedef in (yol, kutuk_mod._degisiklik_yolu(oturum_anahtari)):
        if not hedef:
            continue
        try:
            _folder().delete_path(hedef)
            silinen.append(hedef)
        except Exception:
            pass                      # yoksa silinecek bir sey de yok
    _onbellek_dusur(yol)
    return silinen
