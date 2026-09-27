# -*- coding: utf-8 -*-
"""fe_agent/profil_duck.py - VERI SETI PROFILI, DuckDB MOTORU (tek motor).

Webapp'in icinde calisir; Flow'da recipe / Spark yok (kullanici karari).
Girdi: veri setinin yerel Parquet kopyasi (veri_kaynak.parquet_yolu).
Cikti: profil_kural.profil_kur sozlugu (profil.json).

HESAP (hepsi KESIN; yaklasik sayim ve orneklem yok)
  1. Tekil degerler: ayni turdeki kolon grubu UNPIVOT ile tek "uzun"
     tabloda (k, v, adet) toplanir (gecici tablo; bellege sigmazsa DuckDB
     diske tasar). Parquet kolon bazli okundugu icin genis tabloda (30.000
     kolon) her grup yalnizca kendi kolonlarini okur.
  2. Birinci gecis: dolu/bos, tekil sayisi, min/maks, tam sayi ve donem
     bicimi sayimlari bu tablodan GROUP BY k ile tek sorguda.
  3. Tekrarlanan satir: satir sayisi - tekil satir sayisi.
  4. Deger basina denetim (tip donusumu, kisisel veri, donem yazimlari):
     tekil degeri SURUCU_SINIRI'nin altindaki kolonlarda tekil degerler
     Python'a alinip profil_kural'in fonksiyonlariyla denetlenir - sonuc
     pandas motoruyla (profil_kural.yerel_profil) BIREBIR ayni. Ustundeki
     kolonlarda ayni kurallar SQL ifadeleriyle sayilir (hata mesajinda 1
     ornek deger; serbest bicimli tarih tanima yaygin kaliplarla sinirli).
"""

import re

from fe_agent import profil_kural as pk
from fe_agent import tip_donusum

MOTOR = "duckdb"
# Birinci geciste tek sorguya giren kolon sayisi.
TOPLU_KOLON = 150
# Tekil degeri bu sinirin altindaki kolon Python'da denetlenir.
SURUCU_SINIRI = 200000
# Python'a bir seferde alinan toplam tekil deger (bellek siniri).
TOPLU_SATIR = 2000000
# Tekil deger denetiminde tek seferde islenen deger sayisi.
PARCA_BOYU = 50000

_TAM_TIPLER = ("TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT", "UTINYINT",
               "USMALLINT", "UINTEGER", "UBIGINT", "UHUGEINT")
_UZUN_TIP = {pk.TUR_TAM: "BIGINT", pk.TUR_ONDALIK: "DOUBLE", pk.TUR_MANTIKSAL: "BOOLEAN",
             pk.TUR_METIN: "VARCHAR", pk.TUR_TARIH: "TIMESTAMP"}


# ===========================================================================
# YARDIMCILAR
# ===========================================================================
def baglan():
    """Yeni DuckDB baglantisi (bellekte); gecici dosyalar onbellek dizininde."""
    import duckdb
    from fe_agent import veri_kaynak
    con = duckdb.connect()
    con.execute("SET temp_directory = '%s'" % veri_kaynak.dizin().replace("'", "''"))
    con.execute("SET preserve_insertion_order = false")
    return con


def q(ad):
    """SQL tanimlayicisi (kolon adi) tirnaklama."""
    return '"' + str(ad).replace('"', '""') + '"'


def s(metin):
    """SQL metin sabiti."""
    return "'" + str(metin).replace("'", "''") + "'"


def kaynak_ifadesi(yol):
    return "read_parquet(%s)" % s(yol)


def _tur(tip):
    t = str(tip).upper()
    if t == "BOOLEAN":
        return pk.TUR_MANTIKSAL
    if t in _TAM_TIPLER:
        return pk.TUR_TAM
    if t in ("FLOAT", "DOUBLE", "REAL") or t.startswith("DECIMAL"):
        return pk.TUR_ONDALIK
    if t == "DATE" or t.startswith("TIMESTAMP"):
        return pk.TUR_TARIH
    return pk.TUR_METIN


def sema(con, kaynak):
    """[(ad, tur)] - kaynak sorgusunun kolonlari ve profil turleri."""
    return [(str(r[0]), _tur(r[1]))
            for r in con.execute("DESCRIBE SELECT * FROM " + kaynak).fetchall()]


def normal_ifade(ad, tur):
    """Iki motorun ortak bos tanimi: ondalikta NaN, metinde "" bostur."""
    c = q(ad)
    if tur == pk.TUR_ONDALIK:
        return "(CASE WHEN isnan(%s::DOUBLE) THEN NULL ELSE %s::DOUBLE END)" % (c, c)
    if tur == pk.TUR_METIN:
        return "NULLIF(CAST(%s AS VARCHAR), '')" % c
    if tur == pk.TUR_TARIH:
        return "CAST(%s AS TIMESTAMP)" % c
    if tur == pk.TUR_TAM:
        return "CAST(%s AS BIGINT)" % c
    return c


def _sayisal(e, tur):
    return "(%s)::INTEGER::DOUBLE" % e if tur == pk.TUR_MANTIKSAL else "(%s)::DOUBLE" % e


# ===========================================================================
# 1) BIRINCI GECIS - tekil deger tablosundan (tt) tek sorguyla
# ===========================================================================
# Kolon basina ayri FILTER toplamlari kolon sayisiyla dogrusal olmayan bir
# planlama maliyeti getiriyordu (30 kolon 0,6 sn, 150 kolon 9,9 sn). tt'de
# butun kolonlar (k, v, adet) satirlari oldugu icin ayni sayimlar GROUP BY k
# ile tek sorguda cikar ve toplam sayisi kolon sayisiyla buyumez.
def _bos_ozet(ad, tur, satir):
    return {"ad": ad, "tur": tur, "dolu": 0, "bos": satir, "tekil": 0, "ornek": None,
            "min": None, "max": None, "hepsi_tam": False, "n_sonlu": 0,
            "n_kesirli": 0, "pozitif": None, "n_pii_aday": 0,
            "ym_degil": None, "ymd_degil": None,
            "degerler": [], "ust_degerler": [], "ornek3": [], "kantiller": None,
            "parca": None, "donem_parca": None, "donem_degerleri": None}


def _tt_ozetleri(con, tur):
    """tt'deki her kolonun (k) birinci gecis sayilari. Doner: {k: sozluk}."""
    w = "adet"
    ifade = ["k", "sum(%s) AS dolu" % w, "count(*) AS tekil", "any_value(v) AS ornek"]
    if tur in pk.SAYISAL_TURLER:
        v = _sayisal("v", tur)
        sonlu = "NOT isinf(%s)" % v
        a = "abs(%s)" % v
        ym = "(%s BETWEEN %s AND %s AND fmod(%s, 100) BETWEEN 1 AND 12)" % (
            v, pk.YM_ALT, pk.YM_UST, v)
        ymd = ("(%s BETWEEN %s AND %s AND fmod(floor(%s / 100), 100) BETWEEN 1 AND 12 "
               "AND fmod(%s, 100) BETWEEN 1 AND 31)" % (v, pk.YMD_ALT, pk.YMD_UST, v, v))
        ifade += [
            "min(%s) AS mn" % v, "max(%s) AS mx" % v,
            "coalesce(sum(%s) FILTER (WHERE %s), 0) AS sonlu" % (w, sonlu),
            "coalesce(sum(%s) FILTER (WHERE %s AND %s <> floor(%s)), 0) AS kesir" % (w, sonlu, v, v),
            "coalesce(sum(%s) FILTER (WHERE %s > 0), 0) AS poz" % (w, v),
            "coalesce(sum(%s) FILTER (WHERE %s AND %s = floor(%s) AND %s >= %s AND %s < %s), 0) AS pii"
            % (w, sonlu, a, a, a, repr(pk.PII_SAYI_ALT), a, repr(pk.PII_SAYI_UST)),
            "coalesce(sum(%s) FILTER (WHERE NOT coalesce(%s, false)), 0) AS ym" % (w, ym),
            "coalesce(sum(%s) FILTER (WHERE NOT coalesce(%s, false)), 0) AS ymd" % (w, ymd),
        ]
    elif tur == pk.TUR_TARIH:
        ifade += ["min(v) AS mn", "max(v) AS mx"]
    cur = con.execute("SELECT %s FROM tt GROUP BY k" % ", ".join(ifade))
    adlar = [d[0] for d in cur.description]
    return {int(r[0]): dict(zip(adlar, r)) for r in cur.fetchall()}


def _ozeti_doldur(oz, tur, r):
    dolu = int(r["dolu"])
    oz.update({"dolu": dolu, "bos": oz["bos"] - dolu, "tekil": int(r["tekil"]),
               "ornek": r.get("ornek")})
    if tur in pk.SAYISAL_TURLER and dolu:
        oz.update({"min": r["mn"], "max": r["mx"], "n_sonlu": int(r["sonlu"]),
                   "n_kesirli": int(r["kesir"]), "pozitif": int(r["poz"]),
                   "n_pii_aday": int(r["pii"]), "ym_degil": int(r["ym"]),
                   "ymd_degil": int(r["ymd"])})
        oz["hepsi_tam"] = (oz["n_sonlu"] == dolu and not oz["n_kesirli"])
    elif tur == pk.TUR_TARIH and dolu:
        oz["min"], oz["max"] = r["mn"], r["mx"]


def _tekrar_sayisi(con, kaynak, adlar, turler, satir):
    if not satir or not adlar:
        return 0
    secim = ", ".join("%s AS c%d" % (normal_ifade(adlar[i], turler[i]), i)
                      for i in range(len(adlar)))
    tekil = con.execute("SELECT count(*) FROM (SELECT DISTINCT %s FROM %s)"
                        % (secim, kaynak)).fetchone()[0]
    return satir - int(tekil)


# ===========================================================================
# 2) TEKIL DEGER TABLOSU (gecici tablo tt: k, v, adet)
# ===========================================================================
def _tekil_tablo(con, kaynak, adlar, turler, indeks, tur):
    con.execute("DROP TABLE IF EXISTS tt")
    secim = ", ".join("CAST(%s AS %s) AS c%d" % (normal_ifade(adlar[i], turler[i]),
                                                  _UZUN_TIP[tur], i) for i in indeks)
    con.execute("CREATE TEMP TABLE tt AS SELECT CAST(substr(k, 2) AS INTEGER) AS k, v, "
                "count(*)::BIGINT AS adet FROM (SELECT %s FROM %s) "
                "UNPIVOT (v FOR k IN (%s)) GROUP BY ALL"
                % (secim, kaynak, ", ".join("c%d" % i for i in indeks)))


def _sirali_listeler(con, ozetler):
    """tt'deki her kolon icin en sik UST_DEGER_ADEDI deger (adet azalan,
    esitlikte deger artan), en kucuk ORNEK_UC deger ve tekil degeri
    DEGER_LISTE_SINIRI'ni asmayan kolonlarin tam listesi - tek sorguda.
    Python'da kolon basina siralama yapmaktan cok daha hizli."""
    r = con.execute(
        "SELECT k, v, adet, s1, s2 FROM (SELECT k, v, adet, "
        "row_number() OVER (PARTITION BY k ORDER BY adet DESC, v ASC) AS s1, "
        "row_number() OVER (PARTITION BY k ORDER BY v ASC) AS s2 FROM tt) "
        "WHERE s1 <= %d OR s2 <= %d ORDER BY k, s1"
        % (pk.DEGER_LISTE_SINIRI, pk.ORNEK_UC)).fetchall()
    ust, ornek = {}, {}
    for k, v, adet, s1, s2 in r:
        if s1 <= pk.DEGER_LISTE_SINIRI:
            ust.setdefault(int(k), []).append((v, int(adet)))
        if s2 <= pk.ORNEK_UC:
            ornek.setdefault(int(k), []).append((s2, v))
    for k, oz in ozetler.items():
        sira = ust.get(k, [])
        oz["degerler"] = sira if oz["tekil"] <= pk.DEGER_LISTE_SINIRI else None
        oz["ust_degerler"] = sira[:pk.UST_DEGER_ADEDI]
        oz["ornek3"] = [v for _s, v in sorted(ornek.get(k, []), key=lambda t: t[0])]


def _kantiller(con, tur, ozetler):
    """Sayisal kolonlarin KESIN kantilleri (pandas quantile ile ayni formul),
    tek sorguda: tekil degerler sirali, birikimli satir sayisi ile gereken
    sira numaralarindaki degerler."""
    vd = "CAST(v AS INTEGER)::DOUBLE" if tur == pk.TUR_MANTIKSAL else "v::DOUBLE"
    kosul = []
    for q_ in pk.KANTIL_NOKTALARI:
        p = "((n - 1) * %s)" % repr(float(q_))
        for sira in ("floor(%s)" % p, "ceil(%s)" % p):
            kosul.append("(bas <= %s AND %s < son)" % (sira, sira))
    r = con.execute(
        "SELECT k, vd, bas, son FROM (SELECT k, %s AS vd, "
        "sum(adet) OVER (PARTITION BY k ORDER BY %s ROWS BETWEEN UNBOUNDED PRECEDING "
        "AND CURRENT ROW) AS son, sum(adet) OVER (PARTITION BY k ORDER BY %s ROWS BETWEEN "
        "UNBOUNDED PRECEDING AND CURRENT ROW) - adet AS bas, "
        "sum(adet) OVER (PARTITION BY k) AS n FROM tt) WHERE %s"
        % (vd, vd, vd, " OR ".join(kosul))).fetchall()
    aralik = {}
    for k, vd_, b, e in r:
        aralik.setdefault(int(k), []).append((int(b), int(e), float(vd_)))
    for k, liste in aralik.items():
        n = int(ozetler[k]["dolu"])
        sira_deger = {}
        for p in pk.kantil_konumlari(n):
            for b, e, vd_ in liste:
                if b <= p < e:
                    sira_deger[p] = vd_
                    break
        ozetler[k]["kantiller"] = pk.kantil_hesapla(n, sira_deger)


def _python_ile(con, liste, tur, ozetler):
    """liste: [(k, gorev)]. Tekil degerleri parti parti Python'a alir ve
    yerel motorla ayni denetim fonksiyonlarini calistirir."""
    import numpy as np
    partiler, parti, toplam = [], [], 0
    for k, gorev in liste:
        n = int(ozetler[k]["tekil"])
        if parti and toplam + n > TOPLU_SATIR:
            partiler.append(parti)
            parti, toplam = [], 0
        parti.append((k, gorev))
        toplam += n
    if parti:
        partiler.append(parti)
    for parti in partiler:
        kova = {}
        for k, v, adet in con.execute(
                "SELECT k, v, adet FROM tt WHERE k IN (%s)"
                % ", ".join(str(k) for k, _g in parti)).fetchall():
            b = kova.setdefault(int(k), ([], []))
            b[0].append(v)
            b[1].append(int(adet))
        for k, gorev in parti:
            degerler, adetler = kova.get(k, ([], []))
            oz = ozetler[k]
            adet_np = np.asarray(adetler, dtype="int64")
            parca = None
            for bas in range(0, max(len(degerler), 1), PARCA_BOYU):
                p = pk.parca_degerlendir(tur, degerler[bas:bas + PARCA_BOYU],
                                         adet_np[bas:bas + PARCA_BOYU], gorev)
                parca = p if parca is None else pk.parca_birlestir(parca, p)
            oz["parca"] = parca
            oz["donem_parca"] = (parca or {}).get("donem")
            if pk.tarih_gecisi_gerekli_mi(oz):
                oz["donem_parca"]["tarih_ok"] = pk.tarih_parcasi(tur, degerler, adet_np)


# ===========================================================================
# 3) COK TEKILLI KOLON - SQL IFADELERIYLE
# ===========================================================================
def metin_ifadesi(v, tur):
    """pandas astype(str) karsiligi: tam sayili ondalik deger ".0" ile."""
    if tur == pk.TUR_ONDALIK:
        return ("(CASE WHEN %s = floor(%s) AND abs(%s) < 1e18 "
                "THEN CAST(CAST(%s AS BIGINT) AS VARCHAR) || '.0' "
                "ELSE CAST(%s AS VARCHAR) END)" % (v, v, v, v, v))
    return "CAST(%s AS VARCHAR)" % v


def _kirpik_metin(c, tur, tam_sayi):
    """tip_donusum._metin karsiligi: kirpilmis metin; tam sayili ondalik
    kolonda .0 kuyrugu yok."""
    if tur == pk.TUR_ONDALIK and tam_sayi:
        return "CAST(CAST(%s AS BIGINT) AS VARCHAR)" % c
    return "trim(CAST(%s AS VARCHAR))" % c


_TARIH_KALIBI = {"tarih_ymd": "%Y-%m-%d", "tarih_dmy": "%d.%m.%Y",
                 "tarih_ymd8": "%Y%m%d", "tarih_ym6": "%Y%m"}


def donusum_ifadesi(c, kod, tur, tam_sayi):
    """tip_donusum.cevir'in SQL karsiligi (cok tekilli kolon ve AMP yazimi).
    Cevrilemeyen deger NULL doner; son kontrol farki yakalar."""
    m = _kirpik_metin(c, tur, tam_sayi)
    if kod in tip_donusum.KORUYAN_KALIP:
        uzunluk = 6 if kod == "donem_ym6" else 8
        desen = "%Y%m" if kod == "donem_ym6" else "%Y%m%d"
        return ("(CASE WHEN length(%s) = %d AND regexp_matches(%s, '^[0-9]+$') "
                "AND try_strptime(%s, %s) IS NOT NULL THEN %s END)"
                % (m, uzunluk, m, m, s(desen), c))
    if kod == "sayisal_nokta":
        ok = "(NOT contains(%s, ',') OR regexp_matches(%s, %s))" % (
            m, m, s(tip_donusum._BINLIK_KALIP[kod]))
        return "(CASE WHEN %s THEN try_cast(replace(%s, ',', '') AS DOUBLE) END)" % (ok, m)
    if kod == "sayisal_virgul":
        ok = "(NOT contains(%s, '.') OR regexp_matches(%s, %s))" % (
            m, m, s(tip_donusum._BINLIK_KALIP[kod]))
        return ("(CASE WHEN %s THEN try_cast(replace(replace(%s, '.', ''), ',', '.') "
                "AS DOUBLE) END)" % (ok, m))
    if kod in _TARIH_KALIBI:
        return "try_strptime(%s, %s)" % (m, s(_TARIH_KALIBI[kod]))
    if kod == "kategorik_metin":
        return m
    if kod == "kategorik_ay":
        return "strftime(CAST(%s AS TIMESTAMP), '%%Y-%%m')" % c
    if kod == "kategorik_yil":
        return "strftime(CAST(%s AS TIMESTAMP), '%%Y')" % c
    if kod == "sayisal_ymd8":
        return "CAST(strftime(CAST(%s AS TIMESTAMP), '%%Y%%m%%d') AS DOUBLE)" % c
    raise ValueError("Bilinmeyen dönüşüm: %s" % kod)


def _tckn_sezgi(sade):
    """sozluk._tckn_sezgi'nin SQL karsiligi (kontrol basamaklari)."""
    # try_cast: AND kisa devre yapmaz; eslesmeyen metinde CAST patlardi.
    d = ["try_cast(substr(%s, %d, 1) AS INTEGER)" % (sade, i) for i in range(1, 12)]
    tek = "(%s)" % " + ".join(d[i] for i in (0, 2, 4, 6, 8))
    cift = "(%s)" % " + ".join(d[i] for i in (1, 3, 5, 7))
    ilk10 = "(%s)" % " + ".join(d[:10])
    return ("(regexp_matches(%s, '^[1-9][0-9]{10}$') AND "
            "(((%s * 7 - %s) %% 10) + 10) %% 10 = %s AND %s %% 10 = %s)"
            % (sade, tek, cift, d[9], ilk10, d[10]))


# Java kaliplarinin strptime karsiliklari (profil_spark._TARIH_KALIPLARI).
_TARIH_KALIPLARI = ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%d.%m.%Y", "%d/%m/%Y",
                    "%d-%m-%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%d %H:%M:%S.%g", "%d.%m.%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S",
                    "%b %Y", "%d %b %Y", "%B %Y", "%d %B %Y")
# birlestirme._TARIH_YIL_KALIP'in geriye bakissiz (RE2) esdegeri.
_TARIH_YIL_SQL = r"(^|[^0-9])(19|2[0-9])[0-9]{2}($|[^0-9])"


def _donem_ifadeleri(v):
    """METIN kolonda birlestirme._donem_coz'un deger basina bayraklari."""
    from fe_agent import birlestirme as birl
    t = "trim(CAST(%s AS VARCHAR))" % v
    bos = "lower(%s) IN (%s)" % (t, ", ".join(s(x) for x in birl.DONEM_BOS_YAZIMLAR))
    d = "(CASE WHEN %s THEN NULL ELSE regexp_replace(%s, '^(-?[0-9]+)\\.0+$', '\\1') END)" % (bos, t)
    sayi = "try_cast(%s AS DOUBLE)" % d
    sayi_ok = "(%s IS NOT NULL AND NOT isnan(%s))" % (sayi, sayi)
    ym = "coalesce(%s BETWEEN %s AND %s AND fmod(%s, 100) BETWEEN 1 AND 12, false)" % (
        sayi, pk.YM_ALT, pk.YM_UST, sayi)
    ymd = ("coalesce(%s BETWEEN %s AND %s AND fmod(floor(%s / 100), 100) BETWEEN 1 AND 12 "
           "AND fmod(%s, 100) BETWEEN 1 AND 31, false)" % (sayi, pk.YMD_ALT, pk.YMD_UST, sayi, sayi))
    parcalar = []
    for kalip, yil_i, ay_i in ((birl._YIL_AY_KALIP.pattern, 1, 2),
                               (birl._AY_YIL_KALIP.pattern, 2, 1)):
        yil = "try_cast(regexp_extract(%s, %s, %d) AS INTEGER)" % (d, s(kalip), yil_i)
        ay = "try_cast(regexp_extract(%s, %s, %d) AS INTEGER)" % (d, s(kalip), ay_i)
        parcalar.append("coalesce(%s BETWEEN 1900 AND 2999 AND %s BETWEEN 1 AND 12, false)"
                        % (yil, ay))
    yil_ay = "(%s)" % " OR ".join(parcalar)
    tarih = "try_strptime(%s, [%s])" % (d, ", ".join(s(k) for k in _TARIH_KALIPLARI))
    benzer = "(regexp_matches(%s, %s) AND regexp_matches(%s, %s))" % (
        d, s(_TARIH_YIL_SQL), d, s(birl._TARIH_AYIRICI_KALIP))
    tarih_ok = "(%s IS NOT NULL AND %s)" % (tarih, benzer)
    return d, sayi_ok, ym, ymd, yil_ay, tarih_ok


def _sql_ile(con, k, tur, gorev, ozet):
    """Tekil degeri cok olan TEK kolon: ayni kurallar SQL ile, tek sorguda."""
    from fe_agent import sozluk as sozluk_mod
    v, w = "v", "adet"
    metin = "trim(%s)" % metin_ifadesi(v, tur)
    ifade = ["sum(%s) AS n" % w]
    parca = {"donusum": {}, "pii": None, "donem": None, "uzunluk": None, "metin": None}
    kodlar = list(gorev.get("donusum") or [])
    for j, kod in enumerate(kodlar):
        yeni = donusum_ifadesi(v, kod, tur, gorev.get("tam_sayi"))
        ifade += ["sum(%s) FILTER (WHERE %s IS NULL) AS t%d" % (w, yeni, j),
                  "min(substr(CAST(%s AS VARCHAR), 1, 24)) FILTER (WHERE %s IS NULL) AS o%d"
                  % (v, yeni, j)]
    adlar = ["e-posta", "IBAN", "telefon", "TC kimlik no", "kart numarası", "tckn_sezgi"]
    if gorev.get("pii"):
        ornek = "regexp_replace(%s, '\\.0$', '')" % metin
        sade = "regexp_replace(%s, '[\\s\\-()]', '', 'g')" % ornek
        desen = [
            "regexp_matches(%s, %s)" % (ornek, s(sozluk_mod._DESEN_EPOSTA.pattern)),
            "regexp_matches(%s, %s, 'i')" % (sade, s(sozluk_mod._DESEN_IBAN.pattern)),
            "regexp_matches(%s, %s)" % (sade, s(sozluk_mod._DESEN_TELEFON.pattern)),
            "regexp_matches(%s, %s)" % (sade, s(sozluk_mod._DESEN_TCKN.pattern)),
            "regexp_matches(%s, %s)" % (sade, s(sozluk_mod._DESEN_KART.pattern)),
            _tckn_sezgi(sade)]
        for j, kosul in enumerate(desen):
            ifade.append("sum(%s) FILTER (WHERE %s) AS p%d" % (w, kosul, j))
    if gorev.get("metin"):
        ifade += ["sum(length(CAST(%s AS VARCHAR)) * %s) AS uz" % (v, w),
                  "sum(%s) FILTER (WHERE regexp_matches(%s, '^0[0-9]')) AS kg" % (w, metin),
                  "sum(%s) FILTER (WHERE contains(%s, ',')) AS vg" % (w, metin)]
    if gorev.get("donem"):
        d, sayi_ok, ym, ymd, yil_ay, tarih_ok = _donem_ifadeleri(v)
        dolu = "%s IS NOT NULL" % d
        ifade += ["sum(%s) FILTER (WHERE %s) AS d_dolu" % (w, dolu),
                  "sum(%s) FILTER (WHERE %s AND NOT %s) AS d_sayi" % (w, dolu, sayi_ok),
                  "sum(%s) FILTER (WHERE %s AND %s AND NOT %s) AS d_ym" % (w, dolu, sayi_ok, ym),
                  "sum(%s) FILTER (WHERE %s AND %s AND NOT %s) AS d_ymd" % (w, dolu, sayi_ok, ymd),
                  "sum(%s) FILTER (WHERE %s AND NOT %s) AS d_yilay" % (w, dolu, yil_ay),
                  "sum(%s) FILTER (WHERE %s AND %s) AS d_tarih" % (w, dolu, tarih_ok)]
    cur = con.execute("SELECT %s FROM tt WHERE k = %d" % (", ".join(ifade), k))
    r = dict(zip([x[0] for x in cur.description], cur.fetchone()))
    f = lambda a: float(r.get(a) or 0.0)      # noqa: E731
    for j, kod in enumerate(kodlar):
        parca["donusum"][kod] = {"takilan": f("t%d" % j),
                                 "ornek": [r["o%d" % j]] if r.get("o%d" % j) else [],
                                 "hata": None}
    if gorev.get("pii"):
        parca["pii"] = dict({ad: f("p%d" % j) for j, ad in enumerate(adlar)}, n=f("n"))
    if gorev.get("metin"):
        parca["uzunluk"] = {"toplam": f("uz"), "n": f("n")}
        parca["metin"] = {"kod_gibi": f("kg"), "virgul": f("vg")}
    if gorev.get("donem"):
        parca["donem"] = {"dolu": f("d_dolu"), "sayi_degil": f("d_sayi"),
                          "ym_degil": f("d_ym"), "ymd_degil": f("d_ymd"),
                          "yil_ay_degil": f("d_yilay"), "tarih_ok": None}
    ozet["parca"] = parca
    ozet["donem_parca"] = parca.get("donem")
    if pk.tarih_gecisi_gerekli_mi(ozet):
        ozet["donem_parca"]["tarih_ok"] = f("d_tarih")


def _gorevli(gorev):
    return bool(gorev.get("donusum") or gorev.get("pii")
                or gorev.get("donem") or gorev.get("metin"))


# ===========================================================================
# ANA FONKSIYON
# ===========================================================================
def profil(con, yol, veri_seti=None):
    """Parquet dosyasi -> profil sozlugu (profil_kural.profil_kur ciktisi)."""
    from fe_agent import sozluk as sozluk_mod
    kaynak = kaynak_ifadesi(yol)
    kolonlar = sema(con, kaynak)
    adlar = [a for a, _t in kolonlar]
    turler = [t for _a, t in kolonlar]

    satir = int(con.execute("SELECT count(*) FROM " + kaynak).fetchone()[0])
    ozetler = {i: _bos_ozet(adlar[i], turler[i], satir) for i in range(len(adlar))}
    duplicate = _tekrar_sayisi(con, kaynak, adlar, turler, satir)

    for tur in (pk.TUR_TAM, pk.TUR_ONDALIK, pk.TUR_MANTIKSAL, pk.TUR_METIN, pk.TUR_TARIH):
        indeks = [i for i in range(len(adlar)) if turler[i] == tur]
        for bas in range(0, len(indeks), TOPLU_KOLON):
            grup = indeks[bas:bas + TOPLU_KOLON]
            _tekil_tablo(con, kaynak, adlar, turler, grup, tur)
            istatistik = _tt_ozetleri(con, tur)
            for i in grup:
                if i in istatistik:
                    _ozeti_doldur(ozetler[i], tur, istatistik[i])
            # Tamamen bos kolon tt'de yoktur: tekil 0, deger listesi bos.
            grup = [i for i in grup if ozetler[i]["dolu"]]
            grup_ozet = {i: ozetler[i] for i in grup}
            _sirali_listeler(con, grup_ozet)
            if tur in pk.SAYISAL_TURLER:
                _kantiller(con, tur, grup_ozet)
            gorevler = {i: pk.gorev_plani(ozetler[i], sozluk_mod._pii_ad_mi(adlar[i]))
                        for i in grup}
            is_var = [i for i in grup if _gorevli(gorevler[i])]
            az = [(i, gorevler[i]) for i in is_var if ozetler[i]["tekil"] <= SURUCU_SINIRI]
            if az:
                _python_ile(con, az, tur, ozetler)
            for i in is_var:
                if ozetler[i]["tekil"] > SURUCU_SINIRI:
                    _sql_ile(con, i, tur, gorevler[i], ozetler[i])
            # Donem adaylarinin tekil degerleri (normallestirilmis liste).
            aday = [i for i in grup if pk.donem_adayi_mi(ozetler[i], satir)
                    and ozetler[i]["tekil"] <= pk.DONEM_DEGER_SINIRI]
            if aday:
                ham = {}
                for k, v in con.execute("SELECT k, v FROM tt WHERE k IN (%s)"
                                        % ", ".join(str(i) for i in aday)).fetchall():
                    ham.setdefault(int(k), []).append(v)
                for i in aday:
                    ozetler[i]["donem_degerleri"] = pk.donem_degerleri(tur, ham.get(i, []))
            con.execute("DROP TABLE IF EXISTS tt")

    return pk.profil_kur(veri_seti, satir, duplicate,
                         [ozetler[i] for i in range(len(adlar))], MOTOR)
