# -*- coding: utf-8 -*-
"""fe_agent/amp_duck.py - AMP_VERISETI'ni YAZAN DuckDB motoru (tek motor).

Webapp'in icinde calisir; Flow'da veri seti / recipe yok (kullanici
karari). Kaynak: kullanicinin veri setinin yerel Parquet kopyasi
(veri_kaynak.parquet_yolu). Cikti: PROJE_HAFIZASI/<calisma>/AMP_VERISETI
.parquet - sonraki butun fazlar bu dosyayi okur.

NE YAPAR (istek: bkz. amp_yaz)
  1. Tip donusumleri - Degisken Kontrolu'nde secilenler. Kolonun tekil
     degeri azsa (ESLEME_SINIRI) donusum pandas'taki AYNI fonksiyonla
     (tip_donusum.cevir) tekil degerler uzerinde hesaplanir ve tabloya
     eslenir (join): sonuc eski yolla birebir ayni. Tekil degeri cok olan
     kolonda SQL ifadesi kullanilir. Iki yolda da SON KONTROL var: dolu
     olup cevrilemeyen tek bir hucre bile varsa is DURUR.
  2. Surec disi kolonlar dusurulur (hedef / kimlik / donem haric).
  3. Bolme istenmisse _SPLIT kolonu yazilir (train / val / test /
     disarida). Sonraki butun adimlar setleri bu kolondan okur.
  4. Dosya yerel diske yazilir, klasore yuklenir; set sayilari ve hedef
     pozitif sayilari doner.
"""

import os

from fe_agent import profil_duck as pdk
from fe_agent import profil_kural as pk
from fe_agent import tip_donusum

SPLIT_KOLON = "_SPLIT"
ETIKET = {"egitim": "train", "val": "val", "test": "test", "oot": "oot"}
DISARIDA = "disarida"
# Tekil degeri bu sinirin altindaki kolonda donusum Python'da, pandas'taki
# ayni fonksiyonla hesaplanir ve join ile eslenir.
ESLEME_SINIRI = 5000
_HEDEF_SQL = {"sayısal": "DOUBLE", "tarih": "TIMESTAMP", "kategorik": "VARCHAR"}

q, s = pdk.q, pdk.s


# ===========================================================================
# ISTEK (webapp tarafi)
# ===========================================================================
def dusen_kolonlar(durum, adlar):
    """Surec disi kolonlar; hedef / kimlik / donem hicbir zaman dusmez."""
    korunan = {str(v) for v in (durum.get("meta") or {}).values() if v}
    haric = set(map(str, durum.get("haric_kolonlar") or []))
    return [c for c in adlar if str(c) in haric and str(c) not in korunan]


def _donusum_istegi(durum, kolonlar):
    cikti = {}
    for kolon, kod in (durum.get("tip_donusum") or {}).items():
        kp = kolonlar.get(kolon)
        if kp is None or not tip_donusum.gecerli_kod(kod):
            continue
        tam = None
        if kp.get("tur") == pk.TUR_ONDALIK:
            tam = bool(kp.get("dolu")) and not kp.get("ondalikli")
        cikti[kolon] = {"kod": kod, "tam_sayi": tam, "tekil": int(kp.get("tekil") or 0)}
    return cikti


# ===========================================================================
# TIP DONUSUMLERI
# ===========================================================================
def _esleme_tablosu(con, kaynak, kolon, kod, tur, tam_sayi):
    """Tekil degerler -> tip_donusum.cevir ile donusmus deger (pandas'la
    AYNI fonksiyon). Doner: pandas DataFrame(ham, yeni)."""
    import pandas as pd
    e = pdk.normal_ifade(kolon, tur)
    ham = [r[0] for r in con.execute(
        "SELECT DISTINCT %s FROM %s WHERE %s IS NOT NULL" % (e, kaynak, e)).fetchall()]
    seri = pk.seri_kur(tur, ham)
    yeni, _t, _o = tip_donusum.cevir(seri, kod, tam_sayi=tam_sayi)
    hedef = tip_donusum.hedef_tip(kod)
    hamlar, yeniler = [], []
    for h, y in zip(ham, yeni.tolist()):
        try:
            if y is None or pd.isna(y):
                continue
        except (TypeError, ValueError):
            pass
        if hedef == "tarih":
            y = y.to_pydatetime() if hasattr(y, "to_pydatetime") else y
        elif hedef == "sayısal":
            y = float(y)
        else:
            y = str(y)
        hamlar.append(h)
        yeniler.append(y)
    tablo = pd.DataFrame({"ham": pk.seri_kur(tur, hamlar) if hamlar else pk.seri_kur(tur, []),
                          "yeni": pd.Series(yeniler, dtype=(
                              "datetime64[us]" if hedef == "tarih" else
                              "float64" if hedef == "sayısal" else object))})
    return tablo


def donusumleri_uygula(con, kaynak, donusumler, tipler):
    """donusumler: {kolon: {"kod", "tam_sayi", "tekil"}}.
    Gecici gorunum `d` kurar: kaynak + donusmus kolonlar + __ham_i kolonlari.
    Doner: {kolon: ham_kolon_adi} (son kontrol icin)."""
    kontrol, degistir, hamlar, joinler = {}, [], [], []
    for i, (kolon, d) in enumerate(sorted((donusumler or {}).items())):
        if kolon not in tipler:
            continue
        kod = d.get("kod")
        if not tip_donusum.gecerli_kod(kod) or kod in tip_donusum.KORUYAN_KALIP:
            continue
        tur, tam = tipler[kolon], d.get("tam_sayi")
        ham = "__ham_%d" % i
        # Bos tanimi profil ile ayni (ondalikta NaN, metinde "" bos): son
        # kontrol profilin "hepsi cevrilir" karariyla ayni hucrelere bakar.
        ham_ifade = pdk.normal_ifade(kolon, tur).replace(q(kolon), "s." + q(kolon))
        hamlar.append("%s AS %s" % (ham_ifade, q(ham)))
        if int(d.get("tekil") or ESLEME_SINIRI + 1) <= ESLEME_SINIRI:
            tablo = _esleme_tablosu(con, kaynak, kolon, kod, tur, tam)
            ad = "m%d" % i
            con.register(ad, tablo)
            joinler.append("LEFT JOIN %s ON %s IS NOT DISTINCT FROM %s.ham" % (ad, ham_ifade, ad))
            yeni = "%s.yeni" % ad
        else:
            yeni = "CAST(%s AS %s)" % (pdk.donusum_ifadesi(ham_ifade, kod, tur, tam),
                                       _HEDEF_SQL[tip_donusum.hedef_tip(kod)])
        degistir.append("%s AS %s" % (yeni, q(kolon)))
        kontrol[kolon] = ham
    secim = "s.*" + (" REPLACE (%s)" % ", ".join(degistir) if degistir else "")
    if hamlar:
        secim += ", " + ", ".join(hamlar)
    con.execute("CREATE OR REPLACE TEMP VIEW d AS SELECT %s FROM %s s %s"
                % (secim, kaynak, " ".join(joinler)))
    return kontrol


# ===========================================================================
# BOLME
# ===========================================================================
def _donem_normal(tur, degerler):
    """Ham donem degerleri -> {ham: normallesmis metin} (birlestirme ile ayni)."""
    from fe_agent import birlestirme as birl
    seri = birl.donem_serisi(pk.seri_kur(tur, degerler))
    return {h: n for h, n in zip(degerler, seri.tolist()) if n is not None}


def zamansal_esleme(sayim, test_donemleri, val_var, val_oran, gap):
    """{donem: satir} -> {donem: etiket}. akis_durum._setler_zamansal ile
    AYNI kurallar, satir sayilarindan."""
    from fe_agent import birlestirme as birl
    tum = birl.donem_sirala(list(sayim))
    test = [d for d in test_donemleri if d in set(tum)]
    bosluk = set()
    n = int(gap or 0)
    if n > 0 and test:
        kalan = [d for d in tum if d not in set(test)]
        if len(kalan) > 1:
            bosluk = set(kalan[-min(n, len(kalan) - 1):])
    val = set()
    if val_var and test and test[0] in tum:
        onceki = tum[:tum.index(test[0])]
        if len(onceki) >= 2:
            havuz = sum(sayim[d] for d in onceki)
            secili, toplanan = [], 0
            for d in reversed(onceki[1:]):
                secili.append(d)
                toplanan += sayim[d]
                if havuz and toplanan / float(havuz) >= float(val_oran):
                    break
            val = set(secili) - bosluk
    esleme = {}
    for d in tum:
        if d in set(test):
            esleme[d] = ETIKET["test"]
        elif d in bosluk:
            esleme[d] = DISARIDA
        elif d in val:
            esleme[d] = ETIKET["val"]
        else:
            esleme[d] = ETIKET["egitim"]
    return esleme


def katman_araliklari(boyutlar, oranlar):
    """akis_durum._katmanli_bolum_secimi'nin payi: {katman: boyut} ->
    {katman: [(bas, son, ad), ...]} (sira numarasi araliklari)."""
    cikti = {}
    for katman in sorted(boyutlar, key=str):
        uzunluk = int(boyutlar[katman])
        bas, araliklar = 0, []
        for ad, oran in oranlar:
            n = int(round(uzunluk * float(oran)))
            if uzunluk >= len(oranlar) + 1:
                n = max(n, 1)
            n = min(n, uzunluk - bas - 1) if uzunluk > bas + 1 else 0
            if n <= 0:
                continue
            araliklar.append((bas, bas + n, ad))
            bas += n
        cikti[katman] = araliklar
    return cikti


def _aralik_case(araliklar, katman, sira):
    parcalar = []
    for k, liste in araliklar.items():
        for b, e, ad in liste:
            parcalar.append("WHEN %s = %s AND %s >= %d AND %s < %d THEN %s"
                            % (katman, s(k), sira, b, sira, e, s(ETIKET[ad])))
    if not parcalar:
        return s(ETIKET["egitim"])
    return "CASE %s ELSE %s END" % (" ".join(parcalar), s(ETIKET["egitim"]))


def bolme_ekle(con, b, tipler, kolonlar):
    """`d` gorunumunden _SPLIT'li `e` gorunumunu kurar. b: bolme tarifi."""
    tur = b.get("tur")
    if tur == "hazir":
        if b.get("bicim") == "bayrak":
            es = b.get("esleme") or {}
            dallar = []
            for ad in ("test", "oot", "val", "egitim"):
                kol = es.get(ad)
                if kol:
                    dallar.append("WHEN coalesce(CAST(%s AS DOUBLE), 0) <> 0 THEN %s"
                                  % (q(kol), s(ETIKET[ad])))
            etiket = "CASE %s ELSE %s END" % (" ".join(dallar), s(DISARIDA)) \
                if dallar else s(DISARIDA)
        else:
            normal = "lower(trim(CAST(%s AS VARCHAR)))" % q(b["kolon"])
            dallar = []
            # Oncelik test > oot > val > egitim (akis_durum._setler_hazir).
            for hedef in ("test", "oot", "val", "egitim"):
                hamlar = [h for h, t in (b.get("esleme") or {}).items() if t == hedef]
                if hamlar:
                    dallar.append("WHEN %s IN (%s) THEN %s" % (
                        normal, ", ".join(s(h) for h in hamlar), s(ETIKET[hedef])))
            etiket = "CASE %s ELSE %s END" % (" ".join(dallar), s(DISARIDA)) \
                if dallar else s(DISARIDA)
        con.execute("CREATE OR REPLACE TEMP VIEW e AS SELECT d.*, %s AS %s FROM d"
                    % (etiket, q(SPLIT_KOLON)))
        return

    if tur == "zamansal":
        import pandas as pd
        kol = b["kolon"]
        kolon_tur = tipler[kol]
        e = pdk.normal_ifade(kol, kolon_tur)
        sayim_ham = {r[0]: int(r[1]) for r in con.execute(
            "SELECT %s, count(*) FROM d WHERE %s IS NOT NULL GROUP BY 1" % (e, e)).fetchall()}
        normal = _donem_normal(kolon_tur, list(sayim_ham))
        sayim = {}
        for h, n in sayim_ham.items():
            if h in normal:
                sayim[normal[h]] = sayim.get(normal[h], 0) + n
        esleme = zamansal_esleme(sayim, b.get("test_donemleri") or [],
                                 b.get("val_var"), b.get("val_oran") or 0, b.get("gap"))
        hamlar = list(normal)
        tablo = pd.DataFrame({"ham": pk.seri_kur(kolon_tur, hamlar),
                              "etiket": [esleme.get(normal[h], ETIKET["egitim"]) for h in hamlar]})
        con.register("z", tablo)
        con.execute("CREATE OR REPLACE TEMP VIEW e AS SELECT d.*, coalesce(z.etiket, %s) AS %s "
                    "FROM d LEFT JOIN z ON %s IS NOT DISTINCT FROM z.ham"
                    % (s(ETIKET["egitim"]), q(SPLIT_KOLON), e.replace(q(kol), "d." + q(kol))))
        return

    # RASTGELE (katmanli): kimlik varsa kimlik duzeyinde, yoksa satir duzeyinde.
    oranlar = [(ad, float(o)) for ad, o in (b.get("oranlar") or [])]
    hedef = b.get("hedef")
    seed = int(b.get("seed") or 42)
    kimlik = b.get("kimlik")
    katmanli = bool(b.get("katmanla") and hedef and hedef in kolonlar)
    if kimlik:
        kid = "coalesce(CAST(%s AS VARCHAR), '__BOS__')" % q(kimlik)
        katman = ("coalesce(CAST(max(CAST(%s AS DOUBLE)) AS VARCHAR), '__BOS__')" % q(hedef)
                  if katmanli else "'__TEK__'")
        con.execute("CREATE OR REPLACE TEMP TABLE kt AS SELECT %s AS __id, %s AS __katman "
                    "FROM d GROUP BY 1" % (kid, katman))
        boyut = {r[0]: int(r[1]) for r in con.execute(
            "SELECT __katman, count(*) FROM kt GROUP BY 1").fetchall()}
        etiket = _aralik_case(katman_araliklari(boyut, oranlar), "__katman", "__sira")
        con.execute("CREATE OR REPLACE TEMP TABLE et AS SELECT __id, %s AS __etiket FROM "
                    "(SELECT __id, __katman, row_number() OVER (PARTITION BY __katman "
                    "ORDER BY hash(__id, %d), __id) - 1 AS __sira FROM kt)" % (etiket, seed))
        con.execute("CREATE OR REPLACE TEMP VIEW e AS SELECT d.*, coalesce(et.__etiket, %s) AS %s "
                    "FROM d LEFT JOIN et ON %s = et.__id"
                    % (s(ETIKET["egitim"]), q(SPLIT_KOLON), kid.replace(q(kimlik), "d." + q(kimlik))))
        return

    katman = ("coalesce(CAST(%s AS VARCHAR), '__BOS__')" % q(hedef)) if katmanli else "'__TEK__'"
    boyut = {r[0]: int(r[1]) for r in con.execute(
        "SELECT %s, count(*) FROM d GROUP BY 1" % katman).fetchall()}
    etiket = _aralik_case(katman_araliklari(boyut, oranlar), "__katman", "__sira")
    # BELIRLENIMCI ANAHTAR: satirin butun kolonlari + seed'in ozeti her
    # seferinde ayni sirayi verir; ayni ozeti tasiyan satirlar birebir aynidir.
    ozet = "hash(%s, %d)" % (", ".join(q(c) for c in kolonlar), seed)
    con.execute("CREATE OR REPLACE TEMP VIEW e AS SELECT * EXCLUDE (__katman, __sira), %s AS %s "
                "FROM (SELECT d.*, %s AS __katman, row_number() OVER (PARTITION BY %s "
                "ORDER BY %s) - 1 AS __sira FROM d)"
                % (etiket, q(SPLIT_KOLON), katman, katman, ozet))


# ===========================================================================
# ANA FONKSIYON
# ===========================================================================
def amp_hazirla(con, kaynak_yol, istek, cikti_yol):
    """Kaynak Parquet -> cikti Parquet. Doner: sonuc sozlugu; sonuc["hata"]
    doluysa dosya YAZILMAZ."""
    kaynak = pdk.kaynak_ifadesi(kaynak_yol)
    kolonlar = pdk.sema(con, kaynak)
    tipler = {ad: tur for ad, tur in kolonlar}
    adlar = [ad for ad, _t in kolonlar]
    kontrol = donusumleri_uygula(con, kaynak, istek.get("donusum"), tipler)

    b = istek.get("bolme")
    if b:
        bolme_ekle(con, b, tipler, adlar)
    else:
        con.execute("CREATE OR REPLACE TEMP VIEW e AS SELECT * FROM d")

    ifade = ["count(*) AS __satir"]
    for kolon, ham in kontrol.items():
        ifade.append("count(*) FILTER (WHERE %s IS NOT NULL AND %s IS NULL) AS %s"
                     % (q(ham), q(kolon), q("__k_" + ham)))
    cur = con.execute("SELECT %s FROM e" % ", ".join(ifade))
    toplam = dict(zip([x[0] for x in cur.description], cur.fetchone()))
    takilan = {kolon: int(toplam["__k_" + ham]) for kolon, ham in kontrol.items()
               if int(toplam["__k_" + ham])}
    sonuc = {"satir": int(toplam["__satir"])}
    if takilan:
        sonuc["hata"] = ("Tip dönüşümü tam veride uygulanamadı; çevrilemeyen "
                         "dolu hücre: " + ", ".join("%s (%s)" % (k, n)
                                                   for k, n in sorted(takilan.items())))
        return sonuc

    dusen = [c for c in (istek.get("dusen") or []) if c in tipler]
    haric = list(kontrol.values()) + dusen
    secim = "*" + (" EXCLUDE (%s)" % ", ".join(q(c) for c in haric) if haric else "")
    con.execute("COPY (SELECT %s FROM e) TO %s (FORMAT PARQUET, COMPRESSION ZSTD)"
                % (secim, s(cikti_yol)))
    sonuc["dusen"] = dusen
    sonuc["kolon"] = len(adlar) - len(dusen) + (1 if b else 0)

    if b:
        hedef = istek.get("hedef")
        y = ("CAST(%s AS DOUBLE) > 0" % q(hedef)) if hedef and hedef in tipler \
            and hedef not in dusen else "false"
        sayim = con.execute(
            "SELECT %s, count(*), count(*) FILTER (WHERE %s) FROM %s GROUP BY 1"
            % (q(SPLIT_KOLON), y, pdk.kaynak_ifadesi(cikti_yol))).fetchall()
        sonuc["setler"] = {r[0]: {"satir": int(r[1]), "pozitif": int(r[2])} for r in sayim}
    return sonuc


def amp_yaz(durum, prof, klasor_yolu, bolme=None):
    """AMP_VERISETI'ni yazar: kaynak yerel Parquet -> DuckDB -> yerel dosya
    -> PROJE_HAFIZASI/<klasor_yolu>. Doner: {satir, kolon, dusen, dosya,
    setler?}. Hata -> AdimHatasi."""
    from fe_agent import profil as profil_mod
    from fe_agent import veri_kaynak
    from fe_agent.akis_durum import AdimHatasi, _folder
    kolonlar = profil_mod.kolonlar(prof)
    istek = {
        "donusum": _donusum_istegi(durum, kolonlar),
        "dusen": dusen_kolonlar(durum, list(kolonlar)),
        "hedef": (durum.get("meta") or {}).get("target"),
        "bolme": bolme,
    }
    kaynak = veri_kaynak.parquet_yolu(durum.get("veri_seti"))
    cikti = veri_kaynak.gecici_dosya("amp")
    con = pdk.baglan()
    try:
        sonuc = amp_hazirla(con, kaynak, istek, cikti)
    finally:
        con.close()
    if sonuc.get("hata"):
        raise AdimHatasi(sonuc["hata"])
    try:
        veri_kaynak.klasore_yukle(_folder(), klasor_yolu, cikti)
    except Exception as e:      # pylint: disable=broad-except
        raise AdimHatasi("AMP_VERISETI çalışma klasörüne yazılamadı (PROJE_HAFIZASI%s): %s"
                         % (klasor_yolu, str(e)[:200]))
    finally:
        try:
            os.remove(cikti)
        except OSError:
            pass
    sonuc["dosya"] = klasor_yolu
    return sonuc
