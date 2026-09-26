# -*- coding: utf-8 -*-
"""fe_agent/birlestirme.py — ham tablolari denetlenebilir bicimde birlestirir.

LLM kod yazmaz; kisitli bir BIRLESTIRME PLANI uretir. Bu modul plani
dogrular, Python ile yurutur ve her uretilen kolon icin soy kutugu
(lineage) tutar: hangi tablodan, hangi anahtarla, hangi pencereyle,
hangi fonksiyonla uretildi.

TABLO TURLERI
  ana    : bir satir = bir gozlem (anahtar + donem). Iskeletin kendisi.
  boyut  : anahtar basina TEK satir. As-of (gozlem donemine kadar) baglanir.
  islem  : anahtar basina COK satir. Once toplanir, sonra join edilir.

POINT-IN-TIME KURALI
  Islem tablolarindan toplama yapilirken yalnizca gozlem doneminden
  ONCEKI islemler kullanilir. Pencere [donem - N ay, donem) araligidir;
  donem ayinin kendisi dahil DEGILDIR. "tum" penceresi de donem bazlidir:
  [-sonsuz, donem). Bu kural sizinti onlemenin temelidir ve ihlal edilemez.
  Donem bilgisi olmayan kaynaklarda kural UYGULANAMAZ; bu durum kutukte ve
  ozette acikca isaretlenir.
"""

import hashlib
import re

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# IZINLI GRAMER
# ---------------------------------------------------------------------------
FONKSIYONLAR = {
    "sum":     ("toplam",              lambda s: s.sum()),
    "mean":    ("ortalama",            lambda s: s.mean()),
    "max":     ("maksimum",            lambda s: s.max()),
    "min":     ("minimum",             lambda s: s.min()),
    "std":     ("standart sapma",      lambda s: s.std()),
    "count":   ("kayıt sayısı",        lambda s: s.count()),
    "nunique": ("farklı değer sayısı", lambda s: s.nunique()),
    # DIKKAT: "last" fiziksel satir sirasina bakar. Bu yuzden uygulanmadan
    # ONCE alt kume donem kolonuna gore siralanir (bkz. _islem_birlestir) ve
    # donem kolonu olmayan kaynaklarda dogrulamada yasaklanir.
    "last":    ("son değer",           lambda s: s.iloc[-1] if len(s) else np.nan),
}

# Pencere -> kac ay geriye bakilacak. None = gozlem donemine kadar tum gecmis.
PENCERELER = {
    "son_1a":  1,
    "son_3a":  3,
    "son_6a":  6,
    "son_12a": 12,
    "tum":     None,
}

PENCERE_ADI = {
    "son_1a": "son 1 ay", "son_3a": "son 3 ay", "son_6a": "son 6 ay",
    "son_12a": "son 12 ay", "tum": "tüm geçmiş",
}

TURLER = ("ana", "boyut", "islem")
MAX_KOLON = 4000          # uretilecek toplam kolon tavani

# Donem olcekleri bu kadar aydan fazla ayrisiyorsa bicim/olcek uyusmuyordur.
MAX_OLCEK_FARKI_AY = 120


# ---------------------------------------------------------------------------
# DOGRULAMA
# ---------------------------------------------------------------------------
def _kolonlar(df):
    return set(df.columns)


def dogrula(plan, semalar):
    """Plani semalara karsi dogrular.

    semalar: {tablo_adi: [kolon listesi]}
    Doner: (gecerli_plan, hatalar)  — hatali kaynaklar ayiklanir.

    Gecersiz ya da uygulanamaz pencereler SESSIZCE "tum"a cevrilmez; o
    toplama plandan tamamen cikarilir ve nedeni hatalara yazilir.
    """
    hatalar = []

    ana = plan.get("ana_tablo") or {}
    ana_ad = ana.get("ad")
    if not ana_ad or ana_ad not in semalar:
        return None, ["Ana tablo bulunamadı: %s" % ana_ad]

    ana_kol = set(semalar[ana_ad])
    anahtar = [k for k in (ana.get("anahtar") or []) if k]
    if not anahtar:
        return None, ["Ana tabloda anahtar tanımlanmadı."]
    eksik = [k for k in anahtar if k not in ana_kol]
    if eksik:
        return None, ["Ana tabloda bulunmayan anahtar: %s" % ", ".join(eksik)]

    donem = ana.get("donem_kolon")
    if donem and donem not in ana_kol:
        hatalar.append("Ana tabloda dönem kolonu yok: %s, pencereli toplama kapalı" % donem)
        donem = None
        ana["donem_kolon"] = None

    gecerli_kaynaklar = []
    uretilecek = 0
    # Uretilen kolon adlari: ana tablonun kolonlariyla da cakismasin.
    kullanilan_adlar = set(ana_kol)

    for k in (plan.get("kaynaklar") or []):
        ad = k.get("ad")
        if ad not in semalar:
            hatalar.append("%s: tablo projede yok" % ad)
            continue

        tur = k.get("tur")
        if tur not in TURLER:
            hatalar.append("%s: geçersiz tablo türü: %s" % (ad, tur))
            continue

        kol = set(semalar[ad])
        k_anahtar = [a for a in (k.get("anahtar") or []) if a]
        if not k_anahtar:
            hatalar.append("%s: anahtar tanımlanmadı" % ad)
            continue
        eksik = [a for a in k_anahtar if a not in kol]
        if eksik:
            hatalar.append("%s: tabloda bulunmayan anahtar: %s" % (ad, ", ".join(eksik)))
            continue
        # Anahtar ana tabloda da olmali
        eksik = [a for a in k_anahtar if a not in ana_kol]
        if eksik:
            hatalar.append("%s: ana tabloda bulunmayan anahtar: %s" % (ad, ", ".join(eksik)))
            continue

        if tur == "boyut":
            secilen = []
            for c in (k.get("kolonlar") or []):
                if c not in kol or c in k_anahtar:
                    continue
                # Ad cakismasi: merge _x/_y eki uretmesin, kolon sessizce
                # kaybolmasin diye bastan ayikliyoruz.
                if c in kullanilan_adlar:
                    hatalar.append("%s: %s kolonu baz tabloda zaten var, "
                                   "ad çakışması nedeniyle alınmadı" % (ad, c))
                    continue
                kullanilan_adlar.add(c)
                secilen.append(c)
            if not secilen:
                hatalar.append("%s: alınacak geçerli kolon yok" % ad)
                continue
            k["kolonlar"] = secilen
            uretilecek += len(secilen)
            gecerli_kaynaklar.append(k)
            continue

        # tur == "islem"
        t_donem = k.get("donem_kolon")
        if t_donem and t_donem not in kol:
            hatalar.append("%s: dönem kolonu tabloda yok: %s" % (ad, t_donem))
            t_donem = None
            k["donem_kolon"] = None

        gecerli_top = []
        for t in (k.get("toplamalar") or []):
            kaynak_kol = t.get("kolon")
            fn = t.get("fonksiyon")
            pen = t.get("pencere")

            if fn not in FONKSIYONLAR:
                hatalar.append("%s: izinsiz fonksiyon: %s" % (ad, fn)); continue
            if not pen:
                hatalar.append("%s.%s: pencere belirtilmedi, toplama plandan "
                               "çıkarıldı" % (ad, kaynak_kol)); continue
            if pen not in PENCERELER:
                hatalar.append("%s.%s: geçersiz pencere: %s - toplama plandan "
                               "çıkarıldı" % (ad, kaynak_kol, pen)); continue
            # count disinda kolon zorunlu
            if fn != "count" and kaynak_kol not in kol:
                hatalar.append("%s: kolon tabloda yok: %s" % (ad, kaynak_kol)); continue
            # Pencereli toplama icin iki tarafta da donem lazim. "tum"a
            # DUSURMUYORUZ — dusurmek sizinti uretir; toplamayi cikariyoruz.
            if PENCERELER[pen] is not None and not (t_donem and donem):
                hatalar.append("%s.%s: dönem kolonu olmadan '%s' penceresi "
                               "uygulanamaz, bu toplama plandan çıkarıldı"
                               % (ad, kaynak_kol, pen)); continue
            # "last" donem sirasina gore anlamlidir; donem yoksa fiziksel
            # satir sirasi rastgeledir, yasak.
            if fn == "last" and not t_donem:
                hatalar.append("%s.%s: 'last' için dönem kolonu zorunlu "
                               "(sıralama yapılamaz), toplama plandan çıkarıldı"
                               % (ad, kaynak_kol)); continue

            t["pencere"] = pen
            istek_ad = str(t.get("yeni_ad") or "").strip()
            if istek_ad and istek_ad in kullanilan_adlar:
                hatalar.append("%s: istenen kolon adı çakışıyor: %s, ad yeniden "
                               "üretildi" % (ad, istek_ad))
                istek_ad = ""
            if istek_ad:
                kullanilan_adlar.add(istek_ad)
                t["yeni_ad"] = istek_ad
            else:
                t["yeni_ad"] = _ad_uret(ad, kaynak_kol, fn, pen, kullanilan_adlar)
            gecerli_top.append(t)

        if not gecerli_top:
            hatalar.append("%s: geçerli toplama kalmadı" % ad)
            continue

        k["toplamalar"] = gecerli_top
        uretilecek += len(gecerli_top)
        gecerli_kaynaklar.append(k)

    if uretilecek > MAX_KOLON:
        gecerli_kaynaklar, kirpilan = _tavana_kirp(gecerli_kaynaklar, MAX_KOLON)
        hatalar.append("Plan %s kolon üretiyor; tavan %s. Fazlası kırpıldı "
                       "(%s kolon plandan çıkarıldı)."
                       % (uretilecek, MAX_KOLON, kirpilan))

    plan["kaynaklar"] = gecerli_kaynaklar
    return plan, hatalar


def _tavana_kirp(kaynaklar, tavan):
    """MAX_KOLON tavanini GERCEKTEN uygular. Doner: (kaynaklar, kirpilan_adet)."""
    kalan = tavan
    kirpilan = 0
    kalanlar = []
    for k in kaynaklar:
        alan = "kolonlar" if k.get("tur") == "boyut" else "toplamalar"
        oge = k.get(alan) or []
        if kalan <= 0:
            kirpilan += len(oge)
            continue
        if len(oge) > kalan:
            kirpilan += len(oge) - kalan
            k[alan] = oge[:kalan]
        kalan -= len(k[alan])
        kalanlar.append(k)
    return kalanlar, kirpilan


def _ad_uret(tablo, kolon, fn, pencere, kullanilan=None):
    """HAVALE_ISLEM + TUTAR + sum + son_3a -> HAVALE__TUTAR_SUM_3A

    Tablo ve kolon adlari kirpildigi icin iki farkli toplama ayni ada
    dusebilir. kullanilan kumesi verilirse cakismada kisa bir hash eki
    verilir; boylece hicbir kolon sessizce ezilmez."""
    t = tablo.replace("_ISLEM", "").replace("_TRX", "")[:14]
    k = (kolon or "KAYIT")[:16]
    p = {"son_1a": "1A", "son_3a": "3A", "son_6a": "6A",
         "son_12a": "12A", "tum": "TUM"}[pencere]
    ad = ("%s__%s_%s_%s" % (t, k, fn.upper(), p))[:120]
    if kullanilan is None:
        return ad
    if ad in kullanilan:
        imza = "%s|%s|%s|%s" % (tablo, kolon, fn, pencere)
        ek = hashlib.md5(imza.encode("utf-8")).hexdigest()[:4].upper()
        aday = "%s_%s" % (ad[:115], ek)
        sayac = 2
        while aday in kullanilan:
            aday = "%s_%s%d" % (ad[:112], ek, sayac)
            sayac += 1
        ad = aday
    kullanilan.add(ad)
    return ad


# ---------------------------------------------------------------------------
# YURUTME
# ---------------------------------------------------------------------------
# Metin kolonlarda "bos" anlamina gelen yazimlar. Dataiku'dan metin ya da
# kategori olarak gelen donem kolonunda tek bir "NULL" hucresi, kolonun
# sayisal donem olarak taninmasini engelliyordu.
DONEM_BOS_YAZIMLAR = frozenset(("", "nan", "none", "null", "na", "n/a",
                                "nat", "-", "?"))
# "2025M01", "2025/01", "2025_1", "2025 01" -> yil + ay
_YIL_AY_KALIP = re.compile(r"^(\d{4})\s*[-/._mM]?\s*(\d{1,2})$")
# "01/2025", "1-2025", "01.2025" -> ay + yil
_AY_YIL_KALIP = re.compile(r"^(\d{1,2})\s*[-/._]\s*(\d{4})$")


def donem_degeri(x):
    """Tek bir donem degerinin METIN karsiligi; bossa None.

    Ayni donem kolonu Dataiku'dan sayi (202501), ondalikli sayi (bos
    hucre yuzunden 202501.0), metin ("202501", " 202501 ") ya da kategori
    olarak gelebilir. Bolme donemleri metin olarak karsilastiriyor; bu
    yazimlarin HEPSI ayni "202501" metnine iner. Bos hucre "nan" metnine
    DONUSMEZ: eskiden "nan" metin siralamasinda en sona dusup "son donem"
    sayiliyor ve donemi bos satirlar test setine gidiyordu."""
    if x is None:
        return None
    try:
        if pd.isna(x):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(x, (bool, np.bool_)):
        return str(x)
    if isinstance(x, (int, np.integer)):
        return str(int(x))
    if isinstance(x, (float, np.floating)):
        return str(int(x)) if float(x).is_integer() else str(x)
    t = str(x).strip()
    if t.lower() in DONEM_BOS_YAZIMLAR:
        return None
    if re.fullmatch(r"-?\d+\.0+", t):
        t = t.split(".")[0]
    return t


def donem_serisi(s):
    """Donem kolonunun donem_degeri ile normallesmis hali (object; bos=None).
    Her farkli deger bir kez cevrilir: milyon satirda da hizli."""
    s = pd.Series(s)
    if pd.api.types.is_datetime64_any_dtype(s):
        # Tarih kolonu ONCEKI metin bicimini korur ("2025-01-15"): kayitli
        # test donemleri bu bicimde, degisirse eslesmez.
        return s.astype(str).where(s.notna(), None).astype(object)
    if isinstance(s.dtype, pd.CategoricalDtype):
        s = s.astype(object)
    esleme = {}
    for deger in pd.unique(s):
        try:
            esleme[deger] = donem_degeri(deger)
        except Exception:
            esleme[deger] = None
    return s.map(lambda d: esleme.get(d, None) if d == d else None).astype(object)


def donem_sirala(degerler):
    """Donem metinlerini ZAMAN sirasina dizer.

    Metin siralamasi "2025M10"u "2025M2"den, "02/2025"i "01/2026"dan once
    koyamaz. Degerler donem olarak cozulebiliyorsa (_donem_coz) aya gore,
    ayni ay icinde metne gore; cozulemiyorsa duz metin sirasi."""
    liste = sorted({str(d) for d in degerler if d is not None})
    if len(liste) < 2:
        return liste
    try:
        ay, _bicim = _donem_coz(pd.Series(liste, dtype=object))
    except Exception:
        ay = None
    if ay is None or pd.Series(ay).isna().any():
        return liste
    sira = sorted(zip(pd.Series(ay).astype(float).tolist(), liste))
    return [d for _a, d in sira]


def _yil_ay_coz(s):
    """"2025M01", "2025/01", "01/2025" gibi yazimlar -> (ay serisi, "YYYYMM").
    Butun dolu degerler bu kaliplardan birine uymali ve ay 1-12 olmali."""
    metin = s.astype(str).str.strip()
    ay = pd.Series(np.nan, index=s.index)
    for kalip, yil_i, ay_i in ((_YIL_AY_KALIP, 1, 2), (_AY_YIL_KALIP, 2, 1)):
        parca = metin.str.extract(kalip)
        if parca.isna().all().all():
            continue
        yil = pd.to_numeric(parca[yil_i - 1], errors="coerce")
        a = pd.to_numeric(parca[ay_i - 1], errors="coerce")
        uygun = yil.between(1900, 2999) & a.between(1, 12)
        ay = ay.where(ay.notna() | ~uygun, yil * 12 + a)
    dolu = s.notna()
    if dolu.any() and ay[dolu].notna().all():
        return ay, "YYYYMM"
    return None, None


def _donem_coz(s):
    """Donem kolonunu karsilastirilabilir aylik sayiya cevirir.

    Doner: (ay_serisi, bicim). Bicim: "YYYYMM", "YYYYMMDD", "tarih" ya da
    None — None ise kolon taninan bir donem bicimi DEGILDIR ve tahmine
    zorlanmaz (nanosaniye epoch gibi yanlis yorumlar boylece onlenir)."""
    if s is None:
        return None, None

    if not pd.api.types.is_numeric_dtype(s):
        # Kategori ve metin: bos yazimlar ("", "NULL", "nan") gercekten bos
        # sayilir, " 202501 " kirpilir, "202501.0" -> "202501".
        if not pd.api.types.is_datetime64_any_dtype(s):
            s = donem_serisi(s)
            if not s.notna().any():
                return None, None
        # "202401" gibi metin donemler once sayisal olarak denenir
        sayisal = pd.to_numeric(s, errors="coerce")
        if sayisal.notna().any() and sayisal.notna().sum() == int(s.notna().sum()):
            ay, bicim = _donem_coz(sayisal)
            if ay is not None:
                return ay, bicim
        ay, bicim = _yil_ay_coz(s)
        if ay is not None:
            return ay, bicim
        d = pd.to_datetime(s, errors="coerce")
        if d.notna().any():
            return d.dt.year * 12 + d.dt.month, "tarih"
        return None, None

    v = pd.to_numeric(s, errors="coerce").astype("float")
    gecerli = v.dropna()
    if not len(gecerli):
        return None, None

    # YYYYMM  (202401)
    if gecerli.between(190001, 299912).all() and (gecerli % 100).between(1, 12).all():
        return (v // 100) * 12 + (v % 100), "YYYYMM"

    # YYYYMMDD  (20240115)
    if gecerli.between(19000101, 29991231).all():
        ay = (gecerli // 100) % 100
        gun = gecerli % 100
        if ay.between(1, 12).all() and gun.between(1, 31).all():
            return (v // 10000) * 12 + ((v // 100) % 100), "YYYYMMDD"

    # Gercek datetime kolonu sayisala dusmus olabilir
    if pd.api.types.is_datetime64_any_dtype(s):
        d = pd.to_datetime(s, errors="coerce")
        if d.notna().any():
            return d.dt.year * 12 + d.dt.month, "tarih"

    return None, None


def _donem_sayisal(s):
    """Geriye donuk uyumluluk: yalnizca ay serisini doner (cozulemezse None)."""
    ay, _ = _donem_coz(s)
    return ay


def _ay_metni(ay):
    """24289.0 -> '202401'"""
    try:
        ay = int(ay)
    except Exception:
        return "?"
    yil = (ay - 1) // 12
    a = ay - 12 * yil
    return "%04d%02d" % (yil, a)


def _aralik_metni(ay):
    g = ay.dropna()
    if not len(g):
        return "boş"
    return "%s-%s" % (_ay_metni(g.min()), _ay_metni(g.max()))


def _olcek_uyumlu(a, b):
    """Iki donem serisinin ayni olcekte olup olmadigini denetler.

    Islem tablosu gecmisi tamamen gozlem donemlerinden once olabilir; bu
    yuzden tam ortusme sart degil, ama araliklar MAX_OLCEK_FARKI_AY'dan
    fazla ayrisiyorsa iki taraf farkli olcektedir (bicim yanlis cozulmus)."""
    if a is None or b is None:
        return False
    aa, bb = a.dropna(), b.dropna()
    if not len(aa) or not len(bb):
        return False
    if aa.max() < bb.min():
        return (bb.min() - aa.max()) <= MAX_OLCEK_FARKI_AY
    if bb.max() < aa.min():
        return (aa.min() - bb.max()) <= MAX_OLCEK_FARKI_AY
    return True


def _merge_cakisma_denetle(sol, sag, anahtarlar, kaynak_ad):
    """Merge oncesi ad cakismasi denetimi.

    suffixes verilmedigi icin cakisan adlar _x/_y'ye donusur ve sonraki
    adimlar kolonu bulamaz. Cakisma varsa kaynagi reddediyoruz."""
    ortak = (set(sol.columns) & set(sag.columns)) - set(anahtarlar)
    if ortak:
        raise ValueError("üretilen kolon adı baz tabloda zaten var: %s, "
                         "merge eki (_x/_y) oluşmasın diye kaynak reddedildi"
                         % ", ".join(sorted(ortak))[:120])


_DONEM_IPUCU = ("DONEM", "TARIH", "SNAPSHOT", "GECERL", "PERIOD", "PERIYOT",
                "YILAY", "AYYIL", "VERITARIH", "RAPORTARIH")
_DONEM_TOKEN = {"AY", "DT", "DATE", "MONTH", "YIL_AY", "VALID_FROM"}

_TR_HARF = {"Ç": "C", "Ğ": "G", "İ": "I", "Ö": "O", "Ş": "S", "Ü": "U",
            "ç": "C", "ğ": "G", "ı": "I", "ö": "O", "ş": "S", "ü": "U"}


def _normalize_ad(ad):
    """Turkce karakter ve buyuk/kucuk harften bagimsiz ad normalizasyonu."""
    s = "".join(_TR_HARF.get(c, c) for c in str(ad)).upper()
    return re.sub(r"[^A-Z0-9]+", "", s)


def _boyut_donem_kolon(kaynak, df, anahtar):
    """Boyut tablosunda donem/gecerlilik kolonunu tespit eder.
    Doner: kolon adi ya da None."""
    istek = kaynak.get("donem_kolon")
    if istek and istek in df.columns:
        return istek
    for c in df.columns:
        if c in anahtar:
            continue
        n = _normalize_ad(c)
        if any(ip in n for ip in _DONEM_IPUCU):
            return c
        parcalar = set(re.split(r"[^A-Za-z0-9]+", str(c).upper()))
        if parcalar & _DONEM_TOKEN:
            return c
    return None


def _boyut_birlestir(ana, df, kaynak, ana_donem=None, kutuk=None, uyarilar=None):
    """Boyut tablosunu baglar.

    Boyut tablosunda donem/gecerlilik kolonu varsa AS-OF join yapilir:
    gozlem donemine ESIT ya da ondan KUCUK en son kayit alinir. Zaman
    bilgisi yoksa duz join yapilir ve bunun point-in-time OLMADIGI
    ozette acikca belirtilir."""
    kutuk = kutuk if kutuk is not None else []
    uyarilar = uyarilar if uyarilar is not None else []
    anahtar = kaynak["anahtar"]
    kolonlar = kaynak["kolonlar"]
    ad = kaynak["ad"]

    b_donem = _boyut_donem_kolon(kaynak, df, anahtar)
    asof = False
    not_metni = ""
    tekrar = 0

    ana_ay = b_ay = None
    if b_donem and ana_donem and ana_donem in ana.columns:
        ana_ay, _ = _donem_coz(ana[ana_donem])
        b_ay, b_bicim = _donem_coz(df[b_donem])
        if ana_ay is None or b_ay is None:
            uyarilar.append("%s: '%s' kolonu tanınan bir dönem biçiminde değil; "
                            "as-of join yapılamadı, bu tablo POINT-IN-TIME DEĞİL"
                            % (ad, b_donem))
        elif not _olcek_uyumlu(ana_ay, b_ay):
            uyarilar.append("%s: dönem ölçekleri uyuşmuyor (ana %s, boyut %s); "
                            "as-of join yapılamadı, bu tablo POINT-IN-TIME DEĞİL"
                            % (ad, _aralik_metni(ana_ay), _aralik_metni(b_ay)))
        else:
            asof = True
    elif not b_donem:
        uyarilar.append("%s: bu tablo zaman bilgisi taşımıyor (dönem/geçerlilik "
                        "kolonu bulunamadı); birebir join yapıldı, POINT-IN-TIME "
                        "DEĞİL. Değerler gözlem tarihinden sonra güncellenmiş "
                        "olabilir." % ad)
    else:
        uyarilar.append("%s: ana tabloda dönem kolonu olmadığı için '%s' ile "
                        "as-of join yapılamadı; POINT-IN-TIME DEĞİL"
                        % (ad, b_donem))

    if asof:
        alt = df.assign(_AY=b_ay)[anahtar + kolonlar + ["_AY"]].copy()
        alt = alt[alt["_AY"].notna()].sort_values("_AY", kind="mergesort")
        toplu = []
        for ay in sorted(pd.Series(ana_ay).dropna().unique()):
            gecerli = alt[alt["_AY"] <= ay]
            if not len(gecerli):
                continue
            son = gecerli.drop_duplicates(subset=anahtar, keep="last").copy()
            son["_AY"] = ay
            toplu.append(son)
        if toplu:
            hepsi = pd.concat(toplu, ignore_index=True)
            _merge_cakisma_denetle(ana, hepsi, anahtar + ["_AY"], ad)
            ana = ana.assign(_AY=ana_ay).merge(
                hepsi, on=anahtar + ["_AY"], how="left").drop(columns=["_AY"])
            not_metni = "as-of join: gözlem dönemine kadarki son kayıt alındı"
        else:
            uyarilar.append("%s: gözlem dönemlerinden önce kayıt yok, kolon "
                            "üretilemedi" % ad)
            return ana
    else:
        alt = df[anahtar + kolonlar].copy()
        tekrar = int(alt.duplicated(subset=anahtar).sum())
        if tekrar:
            # Boyut tablosunda tekrar varsa ilk kaydi alip uyari birakiyoruz
            alt = alt.drop_duplicates(subset=anahtar, keep="first")
        _merge_cakisma_denetle(ana, alt, anahtar, ad)
        ana = ana.merge(alt, on=anahtar, how="left")
        not_metni = "zaman bilgisi yok: birebir join, point-in-time DEĞİL"
        if tekrar:
            not_metni += ("; kaynakta %s tekrar eden anahtar vardı, ilk kayıt "
                          "alındı" % tekrar)

    for c in kolonlar:
        if c not in ana.columns:      # uretilemedi: kutuge YAZMA
            uyarilar.append("%s: %s kolonu üretilemedi" % (ad, c))
            continue
        kutuk.append({
            "KOLON": c,
            "KAYNAK_TABLO": ad,
            "KAYNAK_KOLON": c,
            "TUR": "boyut",
            "ANAHTAR": " + ".join(anahtar),
            "FONKSIYON": "-",
            "PENCERE": ("gözlem dönemine kadar (as-of)" if asof else "-"),
            "POINT_IN_TIME": "evet" if asof else "hayır",
            "GEREKCE": kaynak.get("gerekce", ""),
            "NOT": not_metni,
        })
    return ana


def _islem_birlestir(ana, df, kaynak, ana_donem, kutuk=None, uyarilar=None):
    """Point-in-time toplama.

    Her gozlem donemi icin islem tablosu [donem-N, donem) araliginda
    filtrelenir, anahtara gore toplanir ve o doneme baglanir. "tum"
    penceresi de donem bazlidir: (-sonsuz, donem). Gozlem doneminin
    KENDISI hicbir pencereye dahil DEGILDIR."""
    kutuk = kutuk if kutuk is not None else []
    uyarilar = uyarilar if uyarilar is not None else []
    anahtar = kaynak["anahtar"]
    t_donem = kaynak.get("donem_kolon")
    toplamalar = kaynak["toplamalar"]
    ad = kaynak["ad"]

    # ---- Donem cozumu: bicimler ayri ayri tanınır, olcek denetlenir ----
    ana_ay = kay_ay = None
    donemli = False
    if t_donem and ana_donem and ana_donem in ana.columns:
        ana_ay, ana_bicim = _donem_coz(ana[ana_donem])
        kay_ay, kay_bicim = _donem_coz(df[t_donem])
        if ana_ay is None:
            raise ValueError("ana tablo dönem kolonu '%s' tanınan bir dönem "
                             "biçiminde değil (YYYYMM / YYYYMMDD / tarih)"
                             % ana_donem)
        if kay_ay is None:
            raise ValueError("dönem kolonu '%s' tanınan bir dönem biçiminde "
                             "değil (YYYYMM / YYYYMMDD / tarih)" % t_donem)
        if not _olcek_uyumlu(ana_ay, kay_ay):
            raise ValueError("dönem aralıkları uyuşmuyor: ana tablo %s (%s), "
                             "kaynak %s (%s); kaynak reddedildi"
                             % (_aralik_metni(ana_ay), ana_bicim,
                                _aralik_metni(kay_ay), kay_bicim))
        donemli = True

    if not donemli:
        uyarilar.append("%s: dönem bilgisi yok, toplamalar tüm tablo üzerinden "
                        "yapıldı; bu kolonlar POINT-IN-TIME DEĞİL" % ad)

    # ---- Donem bazli: "tum" dahil her pencere [.., gozlem ayi) ----
    if donemli:
        df = df.assign(_AY=kay_ay)
        toplu = []
        for ay in sorted(pd.Series(ana_ay).dropna().unique()):
            satir_parcalari = {}
            for t in toplamalar:
                n = PENCERELER[t["pencere"]]
                # (ay - n, ay) ya da (-sonsuz, ay) — gozlem ayi dahil DEGIL
                maske = df["_AY"] < ay
                if n is not None:
                    maske = maske & (df["_AY"] >= ay - n)
                alt = df[maske]
                if not len(alt):
                    continue
                fn = t["fonksiyon"]
                if fn == "last":
                    alt = _donem_sirala(alt, t_donem)
                if fn == "count":
                    seri = alt.groupby(anahtar, observed=False).size()
                else:
                    kol = pd.to_numeric(alt[t["kolon"]], errors="coerce") \
                        if fn not in ("nunique", "last") else alt[t["kolon"]]
                    seri = kol.groupby([alt[a] for a in anahtar],
                                       observed=False).agg(FONKSIYONLAR[fn][1])
                satir_parcalari[t["yeni_ad"]] = seri

            if not satir_parcalari:
                continue
            blok = pd.DataFrame(satir_parcalari).reset_index()
            blok.columns = anahtar + [c for c in blok.columns if c not in anahtar]
            blok["_AY"] = ay
            toplu.append(blok)

        if toplu:
            hepsi = pd.concat(toplu, ignore_index=True)
            _merge_cakisma_denetle(ana, hepsi, anahtar + ["_AY"], ad)
            ana = ana.assign(_AY=ana_ay).merge(
                hepsi, on=anahtar + ["_AY"], how="left").drop(columns=["_AY"])

    # ---- Donem bilgisi yok: yalnizca "tum" kalmis olabilir ----
    else:
        parcalar = {}
        for t in toplamalar:
            if PENCERELER[t["pencere"]] is not None:
                # Dogrulamadan gecmis bir planda olmamali; yine de pencereli
                # toplamayi donemsiz yurutmuyoruz — sizinti uretir.
                uyarilar.append("%s: %s: dönem bilgisi olmadan '%s' penceresi "
                                "uygulanamaz, kolon üretilmedi"
                                % (ad, t["yeni_ad"], t["pencere"]))
                continue
            fn = t["fonksiyon"]
            kaynak_df = _donem_sirala(df, t_donem) if fn == "last" else df
            if fn == "count":
                parcalar[t["yeni_ad"]] = kaynak_df.groupby(
                    anahtar, observed=False).size()
            else:
                seri = pd.to_numeric(kaynak_df[t["kolon"]], errors="coerce") \
                    if fn not in ("nunique", "last") else kaynak_df[t["kolon"]]
                parcalar[t["yeni_ad"]] = seri.groupby(
                    [kaynak_df[a] for a in anahtar], observed=False).agg(
                    FONKSIYONLAR[fn][1])
        if parcalar:
            ozet = pd.DataFrame(parcalar).reset_index()
            ozet.columns = anahtar + [c for c in ozet.columns if c not in anahtar]
            _merge_cakisma_denetle(ana, ozet, anahtar, ad)
            ana = ana.merge(ozet, on=anahtar, how="left")

    # ---- Kutuk: YALNIZCA gercekten uretilen kolonlar ----
    for t in toplamalar:
        if t["yeni_ad"] not in ana.columns:
            uyarilar.append("%s: %s kolonu üretilemedi (pencerede kayıt yok)"
                            % (ad, t["yeni_ad"]))
            continue
        pit = donemli
        if pit:
            notu = ("gözlem dönemi hariç, yalnızca geçmiş kullanıldı"
                    if PENCERELER[t["pencere"]] is not None else
                    "gözlem döneminden önceki tüm geçmiş kullanıldı")
        else:
            notu = "dönem bilgisi yok: tüm tablo kullanıldı, POINT-IN-TIME DEĞİL"
        kutuk.append({
            "KOLON": t["yeni_ad"],
            "KAYNAK_TABLO": ad,
            "KAYNAK_KOLON": t.get("kolon") or "(satır sayısı)",
            "TUR": "işlem toplama",
            "ANAHTAR": " + ".join(anahtar),
            "FONKSIYON": "%s (%s)" % (t["fonksiyon"], FONKSIYONLAR[t["fonksiyon"]][0]),
            "PENCERE": PENCERE_ADI[t["pencere"]],
            "POINT_IN_TIME": "evet" if pit else "hayır",
            "GEREKCE": t.get("gerekce") or kaynak.get("gerekce", ""),
            "NOT": notu,
        })

    return ana


def _donem_sirala(alt, t_donem):
    """'last' uygulanmadan once alt kumeyi donem sirasina sokar."""
    sirala = []
    if "_AY" in alt.columns:
        sirala.append("_AY")
    if t_donem and t_donem in alt.columns and (
            pd.api.types.is_numeric_dtype(alt[t_donem])
            or pd.api.types.is_datetime64_any_dtype(alt[t_donem])):
        sirala.append(t_donem)
    if not sirala:
        return alt
    return alt.sort_values(by=sirala, kind="mergesort")


def calistir(plan, tablo_okuyucu):
    """Plani yurutur.

    tablo_okuyucu: ad -> DataFrame donduren fonksiyon
    Doner: (baz_df, kutuk_df, ozet)
    """
    ana_spec = plan["ana_tablo"]
    ana = tablo_okuyucu(ana_spec["ad"]).copy()
    ana_donem = ana_spec.get("donem_kolon")
    baslangic_kolon = int(ana.shape[1])

    kutuk = []
    # Ana tablonun kendi kolonlari da kutuge girsin
    for c in ana.columns:
        kutuk.append({
            "KOLON": c, "KAYNAK_TABLO": ana_spec["ad"], "KAYNAK_KOLON": c,
            "TUR": "ana tablo", "ANAHTAR": " + ".join(ana_spec["anahtar"]),
            "FONKSIYON": "-", "PENCERE": "-", "POINT_IN_TIME": "-",
            "GEREKCE": ana_spec.get("gerekce", "iskelet tablo"), "NOT": "",
        })

    hatalar = []
    uyarilar = []
    basarili = 0
    kaynaklar = plan.get("kaynaklar", [])
    for kaynak in kaynaklar:
        try:
            df = tablo_okuyucu(kaynak["ad"])
            if kaynak["tur"] == "boyut":
                ana = _boyut_birlestir(ana, df, kaynak, ana_donem, kutuk, uyarilar)
            else:
                ana = _islem_birlestir(ana, df, kaynak, ana_donem, kutuk, uyarilar)
            basarili += 1
        except Exception as e:
            hatalar.append("%s: %s" % (kaynak["ad"], str(e)[:160]))

    kutuk_df = pd.DataFrame(kutuk)
    ozet = {
        "ana_tablo": ana_spec["ad"],
        "anahtar": ana_spec["anahtar"],
        "donem_kolon": ana_donem,
        "satir": int(ana.shape[0]),
        "kolon": int(ana.shape[1]),
        "baslangic_kolon": baslangic_kolon,
        "eklenen_kolon": int(ana.shape[1]) - baslangic_kolon,
        "kaynak_sayisi": len(kaynaklar),
        "basarili_kaynak": basarili,
        "basarisiz_kaynak": len(hatalar),
        "kismi": bool(hatalar),
        "pit_kolon": int((kutuk_df["POINT_IN_TIME"] == "evet").sum()) if len(kutuk_df) else 0,
        "hatalar": hatalar,
        "uyarilar": uyarilar,
    }
    if hatalar:
        # Kismi sonuc basari gibi gorunmesin.
        ozet["durum"] = ("KISMİ SONUÇ: %s kaynaktan %s tanesi uygulanamadı; "
                         "tablo eksik kolonlarla üretildi."
                         % (len(kaynaklar), len(hatalar)))
    else:
        ozet["durum"] = "Tüm kaynaklar uygulandı."
    return ana, kutuk_df, ozet


def plan_metni(plan):
    """Plani kullaniciya gosterilecek okunakli metne cevirir."""
    a = plan["ana_tablo"]
    satirlar = ["İSKELET",
                "  %s: anahtar: %s" % (a["ad"], " + ".join(a["anahtar"]))]
    if a.get("donem_kolon"):
        satirlar.append("  dönem kolonu: %s" % a["donem_kolon"])
    if a.get("gerekce"):
        satirlar.append("  %s" % a["gerekce"][:100])

    for i, k in enumerate(plan.get("kaynaklar", []), 1):
        satirlar.append("")
        if k["tur"] == "boyut":
            satirlar.append("%2d. %s: birebir eşleşme (%s kolon)"
                            % (i, k["ad"], len(k["kolonlar"])))
            satirlar.append("    anahtar : %s" % " + ".join(k["anahtar"]))
            satirlar.append("    kolonlar: %s" % ", ".join(k["kolonlar"][:8])
                            + (" …" if len(k["kolonlar"]) > 8 else ""))
        else:
            satirlar.append("%2d. %s: işlem toplama (%s değişken)"
                            % (i, k["ad"], len(k["toplamalar"])))
            satirlar.append("    anahtar : %s" % " + ".join(k["anahtar"]))
            satirlar.append("    dönem   : %s" % (k.get("donem_kolon") or "yok"))
            for t in k["toplamalar"][:6]:
                satirlar.append("      %-34s %s · %s"
                                % (t["yeni_ad"][:34],
                                   FONKSIYONLAR[t["fonksiyon"]][0],
                                   PENCERE_ADI[t["pencere"]]))
            if len(k["toplamalar"]) > 6:
                satirlar.append("      … ve %d değişken daha" % (len(k["toplamalar"]) - 6))
        if k.get("gerekce"):
            satirlar.append("    %s" % k["gerekce"][:100])

    return "\n".join(satirlar)
