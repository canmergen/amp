# -*- coding: utf-8 -*-
"""KOLON TIPI DEGISTIRME  -  sozluk teyidi adiminda.

NEDEN VAR
  Kaynak tabloda tip cogu zaman yanlis geliyor: tutar kolonu metin
  olarak ("1.234,50"), tarih 20240131 gibi tam sayi olarak, kod alani
  sayisal olarak okunuyor. Bu kolonlar dogru tiple girmezse WOE/IV
  hesabi anlamsiz cikiyor - sayisal sanilan bir kod alani yuzlerce
  "aralik"a bolunuyor, metin sanilan bir tutar tek tek etiket oluyor.
  Kullanici bunu bolmeden ONCE, tek yerde duzeltebilmeli.

TASARIM KARARI - "GUVENLIYSE ONAYLANSIN"
  Kullanici serbestce tip atayamaz; yalnizca VERININ IZIN VERDIGI
  donusumleri secebilir. Iki asamali denetim var:

    1) TEKLIF  (ornekle)  -> bu modulun uygunluk fonksiyonlari kucuk bir
       ornek uzerinde calisir, kart acilirken listeyi hazirlar. Uygun
       olmayan secenek listeden SILINMEZ, kilitli gosterilir ve sebebi
       yazar - "neden yapamiyorum" sorusu ekranda cevaplanmis olur.

    2) ONAY  (tam kolonla) -> kullanici bir donusum secince ug o kolonu
       TAM veriyle cevirir. Tek deger bile cevrilemezse secim kabul
       EDILMEZ ve kac degerin takildigi soylenir. Ornekte gorunmeyen
       bozuk deger boylece sessizce gecmez.

  Donusum VERIYE burada uygulanmaz; yalnizca karar kaydedilir
  (durum["tip_donusum"]). Tabloyu zaten yazan tek adim bolme; donusum
  orada, o tek yazmanin icinde uygulanir (bkz. akis_faz01.bolme_uygula).
  Boylece kaynak tablo fazladan bir kez yazilmis olmuyor.
"""
import numpy as np
import pandas as pd

# ORNEKLEM YOK: teklifler de onay da TAM KOLONLA
# hesaplanir (bkz. akis_faz01._tip_secenekleri).

# Sayisal bir kolonun "kategorik" olarak modellenmesi ancak sinirli
# sayida farkli deger varsa anlamli. Ustunde kalan kolonlar kilitli
# gosterilir.
KATEGORI_SEVIYE_SINIRI = 50

# Kilitli secenegin yaninda gosterilecek ornek deger sayisi.
ORNEK_DEGER = 3


# ---------------------------------------------------------------------------
# DONUSUM KATALOGU
# ---------------------------------------------------------------------------
# Ayni hedef tipe giden birden fazla YOL var ve hangisinin dogru oldugunu
# veri soylemiyor: "1.234" binlik ayraci olan bin iki yuz otuz dort de
# olabilir, ondalikli bir virgul-uc de. Bu yuzden secenek "sayısal" degil,
# "sayısal - ondalık ayırıcı nokta": kullanici hedefi degil, YOLU seciyor.
DONUSUMLER = {
    # BICIM KORUNUR. Degerler DEGISMEZ; yalnizca kolonun tipi
    # "tarih" (donem) olarak isaretlenir ve her degerin gecerli bir yil-ay
    # oldugu tam kolonla denetlenir. tarih_ym6 ise degeri gercek tarihe
    # (2025-01-01) cevirir ve yazimi bozar.
    "donem_ym6": {
        "hedef": "tarih",
        "etiket": "Tarih (dönem) - YYYYAA, yazım korunur (202501)"},
    "donem_ymd8": {
        "hedef": "tarih",
        "etiket": "Tarih - YYYYAAGG, yazım korunur (20250131)"},
    "sayisal_nokta": {
        "hedef": "sayısal",
        "etiket": "Sayısal - ondalık ayırıcı nokta (1234.50)"},
    "sayisal_virgul": {
        "hedef": "sayısal",
        "etiket": "Sayısal - ondalık ayırıcı virgül (1.234,50)"},
    "tarih_ymd": {
        "hedef": "tarih", "etiket": "Tarih - YYYY-AA-GG (2024-01-31)"},
    "tarih_dmy": {
        "hedef": "tarih", "etiket": "Tarih - GG.AA.YYYY (31.01.2024)"},
    "tarih_ymd8": {
        "hedef": "tarih", "etiket": "Tarih - YYYYAAGG (20240131)"},
    "tarih_ym6": {
        "hedef": "tarih", "etiket": "Tarih - YYYYAA (202401)"},
    "kategorik_metin": {
        "hedef": "kategorik", "etiket": "Kategorik - değerler etiket olarak"},
    "kategorik_ay": {
        "hedef": "kategorik", "etiket": "Kategorik - yıl-ay (2024-01)"},
    "kategorik_yil": {
        "hedef": "kategorik", "etiket": "Kategorik - yıl (2024)"},
    "sayisal_ymd8": {
        "hedef": "sayısal", "etiket": "Sayısal - YYYYAAGG tam sayı"},
}

# Kaynak tipten hangi donusumler TEKLIF edilir. Sira ekranda gorunen
# siradir: once en sik ihtiyac duyulan.
ADAYLAR = {
    "kategorik": ["donem_ym6", "donem_ymd8", "sayisal_nokta", "sayisal_virgul",
                  "tarih_ymd", "tarih_dmy", "tarih_ymd8", "tarih_ym6"],
    "sayısal": ["donem_ym6", "donem_ymd8", "kategorik_metin",
                "tarih_ymd8", "tarih_ym6"],
    "tarih": ["kategorik_ay", "kategorik_yil", "sayisal_ymd8"],
}

# Yazimi koruyan donusumlerin denetim kalibi.
KORUYAN_KALIP = {"donem_ym6": "%Y%m", "donem_ymd8": "%Y%m%d"}

TARIH_KALIBI = {
    "tarih_ymd": "%Y-%m-%d",
    "tarih_dmy": "%d.%m.%Y",
    "tarih_ymd8": "%Y%m%d",
    "tarih_ym6": "%Y%m",
}


def hedef_tip(kod):
    """Donusum kodunun urettigi tip; bilinmeyen kod icin None."""
    return (DONUSUMLER.get(kod) or {}).get("hedef")


def gecerli_kod(kod):
    return bool(kod) and kod in DONUSUMLER


# ---------------------------------------------------------------------------
# CEVIRME
# ---------------------------------------------------------------------------
def _metin(seri, tam_sayi=None):
    """Dolu degerleri kirpilmis metin olarak.

    tam_sayi: kolonun TAMAMI icin "sonlu degerlerin hepsi tam sayi mi"
    karari. Verilmezse seriden hesaplanir. Profil isi kolonu PARCA PARCA
    (tekil degerler uzerinden) denetliyor; karar parcaya gore verilseydi
    tam sayili bir parca "20240131", kesirli deger tasiyan kolonun geri
    kalani "20240131.0" uretirdi. Karar tum kolondan bir kez gelir."""
    dolu = seri.dropna()
    if pd.api.types.is_float_dtype(dolu):
        tam = dolu[np.isfinite(dolu)]
        if tam_sayi is None:
            tam_sayi = bool(len(tam)) and bool((tam == tam.astype("int64")).all())
        if tam_sayi:
            dolu = tam.astype("int64")
    return dolu.astype(str).str.strip()


# Binlik ayirici tasiyan sayinin dogru yazimi: ilk grup 1-3 hane, sonraki
# her grup TAM 3 hane, istege bagli ondalik kisim.
_BINLIK_KALIP = {
    "sayisal_nokta": r"^[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?$",
    "sayisal_virgul": r"^[+-]?\d{1,3}(?:\.\d{3})+(?:,\d+)?$",
}


def cevir(seri, kod, tam_sayi=None):
    """Doner: (yeni_seri, takilan_sayisi, takilan_ornekler).

    yeni_seri KAYNAKLA AYNI INDEKSTE doner ve orijinalde bos olan
    hucreler bos kalir - "bos deger cevrilemedi" diye sayilmazlar.
    Takilan = doluyken cevrilemeyen deger.

    tam_sayi: bkz. _metin (profil isi tum kolonun kararini verir)."""
    if kod not in DONUSUMLER:
        raise ValueError("Bilinmeyen dönüşüm: %s" % kod)

    dolu_maske = seri.notna()
    kaynak = seri[dolu_maske]
    if not len(kaynak):
        return pd.Series([np.nan] * len(seri), index=seri.index), 0, []

    if kod in ("sayisal_nokta", "sayisal_virgul"):
        m = _metin(seri, tam_sayi)
        binlik = "," if kod == "sayisal_nokta" else "."
        if kod == "sayisal_nokta":
            temiz = m.str.replace(",", "", regex=False)
        else:
            temiz = (m.str.replace(".", "", regex=False)
                      .str.replace(",", ".", regex=False))
        yeni = pd.to_numeric(temiz, errors="coerce")
        # BINLIK AYIRICI UCERLI GRUP OLMALI. Binlik ayirici tasiyan
        # deger ancak 1.234 / 1.234.567,50 gibi dogru gruplanmissa sayidir.
        ayiricili = m.str.contains(binlik, regex=False)
        gecerli = m.str.match(_BINLIK_KALIP[kod])
        yeni = yeni.where(~ayiricili.reindex(yeni.index, fill_value=False)
                          | gecerli.reindex(yeni.index, fill_value=False))
    elif kod in KORUYAN_KALIP:
        # Deger AYNEN kalir; yalnizca gecerli yil-ay(-gun) mu diye bakilir.
        m = _metin(seri, tam_sayi)
        uzunluk = 6 if kod == "donem_ym6" else 8
        cozulen = pd.to_datetime(m.where(m.str.len() == uzunluk),
                                 format=KORUYAN_KALIP[kod], errors="coerce")
        yeni = kaynak.where(cozulen.reindex(kaynak.index).notna())
    elif kod in TARIH_KALIBI:
        m = _metin(seri, tam_sayi)
        yeni = pd.to_datetime(m, format=TARIH_KALIBI[kod], errors="coerce")
    elif kod == "kategorik_metin":
        yeni = _metin(seri, tam_sayi)
    elif kod in ("kategorik_ay", "kategorik_yil", "sayisal_ymd8"):
        tarih = pd.to_datetime(kaynak, errors="coerce")
        kalip = {"kategorik_ay": "%Y-%m", "kategorik_yil": "%Y",
                 "sayisal_ymd8": "%Y%m%d"}[kod]
        yeni = tarih.dt.strftime(kalip)
        yeni = yeni.where(tarih.notna())
        if kod == "sayisal_ymd8":
            yeni = pd.to_numeric(yeni, errors="coerce")
    else:                                     # pragma: no cover - katalog kapali
        raise ValueError("Bilinmeyen dönüşüm: %s" % kod)

    yeni = yeni.reindex(seri.index)
    takilan_maske = dolu_maske & yeni.isna()
    takilan = int(takilan_maske.sum())
    ornekler = []
    if takilan:
        ornekler = [str(v)[:24] for v in
                    seri[takilan_maske].head(ORNEK_DEGER).tolist()]
    return yeni, takilan, ornekler


def _kategori_sebebi(seri):
    """Sayisal -> kategorik icin seviye sayisi engeli; uygunsa None."""
    try:
        tekil = int(seri.nunique(dropna=True))
    except Exception:
        return None
    if tekil > KATEGORI_SEVIYE_SINIRI:
        return ("%d farklı değer var; en fazla %d seviyeye kadar kategorik "
                "yapılabilir" % (tekil, KATEGORI_SEVIYE_SINIRI))
    return None


# Sayisal kolonda tarih/donem kaliplarinin HIZLI on elemesi: deger araligi
# tutmuyorsa tam cevirme denenmez. 1.000 kolonluk sette seceneklerin TAM
# KOLONLA hesaplanabilmesi bunun sayesinde (bkz. secenekler).
_SAYISAL_ARALIK = {
    "donem_ym6": (190001, 299912), "tarih_ym6": (190001, 299912),
    "donem_ymd8": (19000101, 29991231), "tarih_ymd8": (19000101, 29991231),
    "sayisal_ymd8": None,
}


def _hizli_red(seri, kod):
    """Kesin uygun OLMAYAN durumu ucuz yoldan yakalar; sebep ya da None."""
    if kod in _SAYISAL_ARALIK and _SAYISAL_ARALIK[kod] \
            and pd.api.types.is_numeric_dtype(seri):
        dolu = seri.dropna()
        if not len(dolu):
            return "kolonda dolu değer yok"
        alt, ust = _SAYISAL_ARALIK[kod]
        try:
            if float(dolu.min()) < alt or float(dolu.max()) > ust \
                    or not bool((dolu % 1 == 0).all()):
                return "değerler bu biçimde değil"
        except Exception:
            return None
    return None


def denetle(seri, kod):
    """Tek donusumun bu kolonda uygun olup olmadigi.

    Doner: (uygun_mu, sebep). Uygunsa sebep None."""
    hizli = _hizli_red(seri, kod)
    if hizli:
        return False, hizli
    if kod == "kategorik_metin":
        sebep = _kategori_sebebi(seri)
        if sebep:
            return False, sebep
    try:
        _, takilan, ornekler = cevir(seri, kod)
    except Exception as e:
        return False, ("çevrilemedi (%s)" % str(e)[:60])
    if not takilan:
        dolu = int(seri.notna().sum())
        if not dolu:
            return False, "kolonda dolu değer yok"
        return True, None
    return False, ("%s değer çevrilemedi (%s)"
                   % ("{:,}".format(takilan).replace(",", "."),
                      ", ".join(ornekler) if ornekler else "örnek yok"))


def secenekler(seri, tip, yalniz_uygun=False):
    """Bir kolonun donusum listesi.

    yalniz_uygun=True: YALNIZCA uygulanabilir secenekler. Seri TAM
    KOLON olmali."""
    cikti = []
    for kod in ADAYLAR.get(tip, []):
        uygun, sebep = denetle(seri, kod)
        if yalniz_uygun and not uygun:
            continue
        cikti.append({"kod": kod,
                      "hedef": DONUSUMLER[kod]["hedef"],
                      "etiket": DONUSUMLER[kod]["etiket"],
                      "uygun": bool(uygun),
                      "sebep": sebep or ""})
    return cikti


def uygula(df, donusumler):
    """Secilen donusumleri DataFrame uzerinde uygular (yerinde degil).

    donusumler: {kolon: kod}. Doner: (yeni_df, uygulanan, atlanan)
    - uygulanan: {kolon: kod}
    - atlanan:   {kolon: sebep}   (kolon yok ya da cevrilemedi)

    Cevrilemeyen kolon DEGISTIRILMEZ: yarim cevrilmis bir kolon,
    hic cevrilmemis kolondan daha tehlikeli."""
    uygulanan, atlanan = {}, {}
    if not donusumler:
        return df, uygulanan, atlanan
    # SIG KOPYA: yalnizca butun kolonlar degistiriliyor, hucre ici
    # yazma yok. Derin kopya, her okumada 1.042 kolonluk tabloyu
    # bastan olusturmak demekti - bu fonksiyon artik her modelleme
    # okumasinda calisiyor (bkz. akis_durum.modelleme_df).
    yeni_df = df.copy(deep=False)
    for kolon, kod in donusumler.items():
        if kolon not in yeni_df.columns:
            atlanan[kolon] = "kolon tabloda yok"
            continue
        if not gecerli_kod(kod):
            atlanan[kolon] = "tanınmayan dönüşüm (%s)" % kod
            continue
        try:
            seri, takilan, ornekler = cevir(yeni_df[kolon], kod)
        except Exception as e:
            atlanan[kolon] = str(e)[:80]
            continue
        if takilan:
            atlanan[kolon] = ("%d değer çevrilemedi (%s)"
                              % (takilan, ", ".join(ornekler)))
            continue
        yeni_df[kolon] = seri
        uygulanan[kolon] = kod
    return yeni_df, uygulanan, atlanan
