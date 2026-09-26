# -*- coding: utf-8 -*-
"""fe_agent/bakim.py — PROJE_HAFIZASI klasoru icin bakim araclari.

NEDEN GEREKLI
    Klasorde iki tur dosya BIRIKIR ve hicbiri kendiliginden silinmez:
      /oturum_<anahtar>.json          her kullanicinin calismasi
      /senaryo_<is>_<oturum>_*.json   senaryo konfig/sonuc alisverisi
    Webapp banka geneline acildiginda bunlar suresiz buyur. Ayrica eski
    surumde oturum kimligi her sayfa yuklemesinde YENIDEN uretiliyordu;
    o donemden kalma yetim dosyalar da burada duruyor olabilir.

    CSV yedekleri (/analitik_baz_set.csv gibi) yalnizca dataset yazimi
    BASARISIZ olunca olusur; varlıklari bir sorunun isaretidir, silmeden
    once bakmakta fayda var.

KULLANIM (Dataiku notebook ya da Python recipe):

    from fe_agent import bakim

    bakim.rapor()                       # once BAK: ne var, ne kadar yer tutuyor
    bakim.temizle(gun=30)               # KURU CALISMA - hicbir sey silinmez
    bakim.temizle(gun=30, uygula=True)  # gercekten sil

GUVENLIK
    temizle() varsayilan olarak KURU calisir (uygula=False): yalnizca ne
    silinecegini yazar. Silmek icin uygula=True vermek ZORUNLUDUR.
    Ayrica korumali desenler (uretim_kodu.py, CSV yedekleri) varsayilan
    olarak KAPSAM DISIDIR.
"""

import datetime
import re

import dataiku

from fe_agent.akis_durum import HAFIZA_FOLDER


# Silinebilir kabul edilen desenler ------------------------------------------
# Yeni calismalar (v1, v2 ...) kaydini kendi klasorunde tutar:
# /v3/calisma.json. Onceki bicim kokte: /oturum_<anahtar>.json.
OTURUM_DESENI = re.compile(r"^/(oturum_.+\.json|v\d+/calisma\.json)$")
SENARYO_DESENI = re.compile(r"^/senaryo_.+_(konfig|sonuc)\.json$")

# Bir oturuma ait, oturumla birlikte eskiyen dosyalar. Sozluk calisma
# kopyasi ve kategori degisiklik kutugu klasorun KOKUNDE degil, oturum
# adini tasiyan bir alt klasorde durur: /<oturum_anahtari>/....
#
# NEDEN AYRI DESEN: asagidaki korumali desen butun CSV'leri dokunulmaz
# sayiyor. O kural KOKTEKI yedekler icin konmustu (dataset yazimi
# basarisiz olunca tek kopya o dosyada kaliyor). Oturum alt klasorundeki
# CSV'ler ise her oturumda yeniden uretilir; korumali sayilirsa her
# kullanicinin her oturumu klasorde kalici bir iz birakir ve PROJE_HAFIZASI
# hicbir zaman temizlenemez.
OTURUM_DOSYASI_DESENI = re.compile(r"^/[^/]+/(sozluk_calisma|sozluk_degisiklik)\.csv$")

# Varsayilan olarak DOKUNULMAZ: bunlar bir sorunun kaniti ya da ciktisi
KORUMALI_DESENLER = (
    re.compile(r"^/uretim_kodu\.py$"),
    re.compile(r"^/[^/]+\.csv$"),          # YALNIZCA kokteki CSV yedekleri
)

# Kac gunden eski dosyalar eskimis sayilir (varsayilan)
VARSAYILAN_GUN = 30


def _folder():
    return dataiku.Folder(HAFIZA_FOLDER)


def _ayrinti(klasor, yol):
    """(boyut, degisim_zamani) doner. Alinamazsa (None, None)."""
    try:
        d = klasor.get_path_details(yol) or {}
    except Exception:
        return None, None
    boyut = d.get("size")
    ms = d.get("lastModified")
    zaman = None
    if ms:
        try:
            zaman = datetime.datetime.fromtimestamp(float(ms) / 1000.0)
        except Exception:
            zaman = None
    return boyut, zaman


def _tur(yol):
    if OTURUM_DESENI.match(yol):
        return "oturum"
    if OTURUM_DOSYASI_DESENI.match(yol):
        return "oturum"
    if SENARYO_DESENI.match(yol):
        return "senaryo"
    for d in KORUMALI_DESENLER:
        if d.match(yol):
            return "korumali"
    return "diger"


def _boyut_yaz(b):
    if b is None:
        return "?"
    if b < 1024:
        return "%d B" % b
    if b < 1024 * 1024:
        return "%.1f KB" % (b / 1024.0)
    return "%.1f MB" % (b / (1024.0 * 1024.0))


def dosyalar():
    """Klasordeki her dosya icin bir sozluk doner."""
    klasor = _folder()
    try:
        yollar = klasor.list_paths_in_partition() or []
    except Exception as e:
        raise RuntimeError("PROJE_HAFIZASI okunamadi: %s" % e)

    simdi = datetime.datetime.now()
    kayitlar = []
    for yol in yollar:
        boyut, zaman = _ayrinti(klasor, yol)
        yas = (simdi - zaman).days if zaman else None
        kayitlar.append({"yol": yol, "tur": _tur(yol), "boyut": boyut,
                         "zaman": zaman, "gun": yas})
    return kayitlar


def rapor():
    """Klasorun ozetini ve en buyuk/eski dosyalari yazdirir."""
    kayitlar = dosyalar()
    if not kayitlar:
        print("PROJE_HAFIZASI bos.")
        return kayitlar

    ozet = {}
    for k in kayitlar:
        d = ozet.setdefault(k["tur"], {"adet": 0, "boyut": 0})
        d["adet"] += 1
        d["boyut"] += (k["boyut"] or 0)

    print("PROJE_HAFIZASI: %d dosya" % len(kayitlar))
    print("%-10s %6s  %10s" % ("tur", "adet", "boyut"))
    for tur in sorted(ozet):
        d = ozet[tur]
        print("%-10s %6d  %10s" % (tur, d["adet"], _boyut_yaz(d["boyut"])))

    eskiler = [k for k in kayitlar if k["gun"] is not None]
    eskiler.sort(key=lambda k: -(k["gun"] or 0))
    if eskiler:
        print("\nEn eski 10 dosya:")
        for k in eskiler[:10]:
            print("  %-46s %4s gun  %8s  %s"
                  % (k["yol"][:46], k["gun"], _boyut_yaz(k["boyut"]), k["tur"]))
    return kayitlar


def temizle(gun=VARSAYILAN_GUN, turler=("oturum", "senaryo"),
            uygula=False, anahtar_iceren=None):
    """Eskimis dosyalari siler.

    gun             : bu gun sayisindan ESKI dosyalar aday olur.
                      gun=0 -> yas gozetmeksizin tum eslesme adaydir.
    turler          : "oturum" ve/veya "senaryo". "korumali" ve "diger"
                      KABUL EDILMEZ; yanlislikla cikti silinmesin diye.
    uygula          : False (varsayilan) -> KURU CALISMA, hicbir sey silinmez.
    anahtar_iceren  : verilirse yalnizca yolu bu metni iceren dosyalar.

    Doner: silinen (ya da kuru calismada silinecek) yollarin listesi.
    """
    izinli = tuple(t for t in turler if t in ("oturum", "senaryo"))
    if not izinli:
        raise ValueError('turler yalnizca "oturum" ve "senaryo" olabilir')

    klasor = _folder()
    adaylar = []
    for k in dosyalar():
        if k["tur"] not in izinli:
            continue
        if anahtar_iceren and anahtar_iceren not in k["yol"]:
            continue
        if gun and (k["gun"] is None or k["gun"] < gun):
            continue
        adaylar.append(k)

    baslik = "SILINECEK" if uygula else "KURU CALISMA: silinmeyecek"
    toplam = sum(k["boyut"] or 0 for k in adaylar)
    print("%s: %d dosya, %s" % (baslik, len(adaylar), _boyut_yaz(toplam)))
    for k in adaylar:
        print("  %-46s %4s gun  %8s"
              % (k["yol"][:46], k["gun"], _boyut_yaz(k["boyut"])))

    if not uygula:
        print("\nGercekten silmek icin: temizle(..., uygula=True)")
        return [k["yol"] for k in adaylar]

    silinen, hatali = [], []
    for k in adaylar:
        try:
            klasor.delete_path(k["yol"])
            silinen.append(k["yol"])
        except Exception as e:
            hatali.append((k["yol"], str(e)[:80]))
    print("\nSilindi: %d" % len(silinen))
    if hatali:
        print("Silinemedi: %d" % len(hatali))
        for yol, hata in hatali:
            print("  %s -> %s" % (yol, hata))
    return silinen


def oturum_yollari(anahtar):
    """Bir oturumun PROJE_HAFIZASI'nda biraktigi BUTUN dosyalar.

    Oturum yalnizca durum JSON'undan ibaret degil: sozluk calisma kopyasi
    ve kategori degisiklik kutugu oturum adini tasiyan alt klasorde durur.
    Sadece JSON silinirse bu ikisi klasorde kalici olarak kaliyor."""
    temiz = re.sub(r"[^A-Za-z0-9_-]", "", str(anahtar or ""))
    if not temiz:
        return []
    kayit = ("/%s/calisma.json" % temiz if re.match(r"^v\d+$", temiz)
             else "/oturum_%s.json" % temiz)
    return [kayit,
            "/%s/sozluk_calisma.csv" % temiz,
            "/%s/sozluk_degisiklik.csv" % temiz]


def oturum_sil(anahtar, uygula=False):
    """Tek bir oturumu siler. anahtar = /tani ucundaki oturum_anahtari.

    Oturuma ait sozluk calisma kopyasi ve degisiklik kutugu de silinir;
    orijinal sozluk dataset'ine bu islem de dokunmaz."""
    yollar = oturum_yollari(anahtar)
    if not yollar:
        print("Anahtar cozulemedi: %r" % (anahtar,))
        return []
    if not uygula:
        for y in yollar:
            print("KURU CALISMA: silinecek: %s" % y)
        return yollar

    silinen = []
    for y in yollar:
        try:
            _folder().delete_path(y)
            print("Silindi: %s" % y)
            silinen.append(y)
        except Exception as e:
            # Dosya hic olusmamis olabilir (kopya cikarilamadiysa); bu bir
            # hata degil, o yuzden digerlerini silmeye devam ediyoruz.
            print("Atlandi: %s -> %s" % (y, e))

    # Sozluk kopyasi surec ici bir onbellekte de duruyor. Dosyayi silip
    # onbellegi birakmak, ayni surecte silinmis bir oturumun sozlugunun
    # okunmaya devam etmesi demek. Gec import: bakim, akis zincirinin
    # disinda durur, tepesinden ice alinca dongu olusuyor.
    try:
        from fe_agent import sozluk_calisma
        sozluk_calisma._onbellek_dusur(sozluk_calisma.kopya_yolu(anahtar))
    except Exception as e:
        print("Onbellek dusurulemedi: %s" % e)
    return silinen


def senaryo_artiklari(uygula=False, gun=1):
    """Senaryo konfig/sonuc dosyalarini temizler.

    Bunlar bir senaryo kosusu icin yazilip okunur; kosu bittikten sonra
    islevi kalmaz. Varsayilan olarak 1 gunden eskiler temizlenir.
    """
    return temizle(gun=gun, turler=("senaryo",), uygula=uygula)
