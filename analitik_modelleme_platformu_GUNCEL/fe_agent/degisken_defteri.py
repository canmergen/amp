# -*- coding: utf-8 -*-
"""fe_agent/degisken_defteri.py - calismanin DEGISKEN DEFTERI (JSON).

Baz veri tamamlandigi andan itibaren HER ADIM SONUNDA yeniden yazilir
(PROJE_HAFIZASI/<calisma>/degisken_defteri.json):

  kalan     : o an veri setinde duran her degisken (ham + uretilen):
              anlami, nereden geldigi ve ozet bilgisi (01.2.3.1 tablosundaki
              alanlar: tip, bos orani, tekrar orani, tekil deger, en sik
              degerler, min, medyan, ortalama, max)
  cikarilan : calisma boyunca cikarilan ya da reddedilen her degisken (ham
              kolon ya da uretilip elenen): ayni bilgiler + hangi adimda,
              neden

AMAC: uretilmis ve uretilip reddedilmis butun degiskenler tek yerde durur;
02.3 AI Degisken Kesfi bu defteri okur ve AYNI degiskeni yeniden uretmez
(dil modeline "bunlari onerme" diye verilir; donen oneriler ayrica kodla
ad ve ifade imzasi uzerinden elenir).

KALICI KAYIT durum["defter"]: adimlar yeniden calistirildiginda adimin
kendi kayitlari silinir (akis_faz03._adim_temizle); defter silinmez.
  durum["defter"] = {"uretilen": {ad: kayit}, "red": {anahtar: kayit}}
Ham kolonlar ve sonraki elemeler (kalite, secim) her yazimda durumdan
turetilir; ayrica saklanmaz.
"""

import ast
import datetime
import hashlib
import json
import math
import re

DEFTER_SURUMU = 1
DEFTER_DOSYA = "degisken_defteri.json"
EN_SIK_ADET = 5
# Dil modeline giden liste siniri (istek boyu).
BILINEN_SINIR = 400

KAYNAK_ADI = {"ham": "Ham kolon", "cozum": "02.1 Veri Profili (çözüm)",
              "kural": "02.2 Kural Tabanlı Değişken Üretimi",
              "kesif": "02.3 AI Değişken Keşfi"}
ADIM_ADI = {"cozum": "02.1", "kural": "02.2", "kesif": "02.3"}

_DEGISMELI = (ast.Add, ast.Mult, ast.BitAnd, ast.BitOr, ast.And, ast.Or)
_DEGISMELI_FONK = {"MAX", "MIN", "TOPLA", "SUM", "ORT", "MEAN"}


# ---------------------------------------------------------------------------
# IFADE IMZASI: ayni hesabi yapan iki ifade ayni imzayi verir (bosluk,
# buyuk-kucuk harf, a + b ile b + a, a * b ile b * a farki silinir).
# ---------------------------------------------------------------------------
def _dugum(d):
    if isinstance(d, ast.Expression):
        return _dugum(d.body)
    if isinstance(d, ast.Name):
        return ("ad", d.id.upper())
    if isinstance(d, ast.Constant):
        v = d.value
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return ("sabit", str(v).upper())
        return ("sayi", repr(float(v)))
    if isinstance(d, ast.BinOp):
        sol, sag = _dugum(d.left), _dugum(d.right)
        if isinstance(d.op, _DEGISMELI):
            sol, sag = sorted((sol, sag), key=repr)
        return (type(d.op).__name__, sol, sag)
    if isinstance(d, ast.BoolOp):
        return (type(d.op).__name__,) + tuple(sorted((_dugum(x) for x in d.values), key=repr))
    if isinstance(d, ast.UnaryOp):
        return (type(d.op).__name__, _dugum(d.operand))
    if isinstance(d, ast.Compare):
        return ("kiyas", _dugum(d.left)) + tuple(
            (type(o).__name__, _dugum(c)) for o, c in zip(d.ops, d.comparators))
    if isinstance(d, ast.IfExp):
        return ("eger", _dugum(d.test), _dugum(d.body), _dugum(d.orelse))
    if isinstance(d, ast.Call):
        ad = _dugum(d.func)
        arg = [_dugum(a) for a in d.args]
        if ad[0] == "ad" and ad[1] in _DEGISMELI_FONK:
            arg = sorted(arg, key=repr)
        return ("fonk", ad) + tuple(arg) + tuple(
            (k.arg, _dugum(k.value)) for k in sorted(d.keywords, key=lambda k: str(k.arg)))
    if isinstance(d, ast.Subscript):
        return ("alt", _dugum(d.value), _dugum(d.slice))
    if isinstance(d, ast.Attribute):
        return ("oz", _dugum(d.value), d.attr.upper())
    if isinstance(d, (ast.Tuple, ast.List)):
        return ("liste",) + tuple(_dugum(x) for x in d.elts)
    return ("ham", ast.dump(d).upper())


def ifade_imza(ifade):
    """Ifadenin kanonik imzasi (metin). Ayristirilamazsa bosluksuz, buyuk
    harfli metin. Bos ifade: ""."""
    metin = str(ifade or "").strip()
    if not metin:
        return ""
    try:
        return repr(_dugum(ast.parse(metin, mode="eval")))
    except Exception:           # pylint: disable=broad-except
        return re.sub(r"\s+", "", metin).upper()


# ---------------------------------------------------------------------------
# OZET: 01.2.3.1 tablosundaki alanlar.
# ---------------------------------------------------------------------------
def _json_sayi(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _deger(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return bool(v)
    if isinstance(v, (int, float)):
        return _json_sayi(v)
    try:
        import numpy as np
        if isinstance(v, np.generic):
            return _deger(v.item())
    except Exception:           # pylint: disable=broad-except
        pass
    return str(v)[:120]


def ozet_cikar(seri):
    """Bir kolonun (pandas Series) ozeti: uretilen degiskenler icin, ham
    kolonlarin profil ozetiyle ayni alanlar."""
    import pandas as pd
    n = int(len(seri))
    bos = int(seri.isna().sum())
    dolu = seri.dropna()
    sayisal = pd.api.types.is_numeric_dtype(seri) and not pd.api.types.is_bool_dtype(seri)
    oz = {"tip": "sayısal" if sayisal else ("mantıksal" if pd.api.types.is_bool_dtype(seri) else "kategorik"),
          "satir": n, "bos_oran": (bos / float(n)) if n else None,
          "tekil": int(dolu.nunique()),
          "tekrar_oran": (float(seri.duplicated().sum()) / n) if n else None,
          "en_sik": [[_deger(v), int(a)] for v, a in dolu.value_counts().head(EN_SIK_ADET).items()]}
    if sayisal and len(dolu):
        x = pd.to_numeric(dolu, errors="coerce").dropna()
        x = x[x.map(math.isfinite)] if len(x) else x
        if len(x):
            oz.update({"min": _json_sayi(x.min()), "medyan": _json_sayi(x.median()),
                       "ortalama": _json_sayi(x.mean()), "max": _json_sayi(x.max())})
    return oz


def _profil_ozeti(kp):
    """Veri seti profilindeki kolon kaydindan (profil_kural) ozet."""
    if not isinstance(kp, dict):
        return {}
    dolu, bos = int(kp.get("dolu") or 0), int(kp.get("bos") or 0)
    satir = dolu + bos
    tekrar = kp.get("tekrar")
    oz = {"tip": kp.get("tip") or kp.get("tur") or "", "satir": satir,
          "bos_oran": kp.get("null_oran") if kp.get("null_oran") is not None
          else ((bos / float(satir)) if satir else None),
          "tekil": kp.get("tekil"),
          "tekrar_oran": (float(tekrar) / satir) if tekrar is not None and satir else None}
    if kp.get("pii_ad") or kp.get("pii_deger"):
        # Kisisel veri tasiyan kolonun degerleri ve istatistikleri yazilmaz
        # (01.2.3.1'deki kural).
        oz["gizli"] = True
        return oz
    oz["en_sik"] = [[_deger(v), int(a)] for v, a in (kp.get("ust_degerler") or [])[:EN_SIK_ADET]]
    q = kp.get("kantiller") or []
    for ad, v in (("min", kp.get("min")), ("medyan", q[2] if len(q) > 2 else kp.get("medyan")),
                  ("ortalama", kp.get("ortalama")), ("max", kp.get("max"))):
        if v is not None:
            oz[ad] = _deger(v)
    return oz


# ---------------------------------------------------------------------------
# KALICI KAYIT (durum["defter"])
# ---------------------------------------------------------------------------
def _defter(durum):
    d = durum.get("defter")
    if not isinstance(d, dict):
        d = {}
    d.setdefault("uretilen", {})
    d.setdefault("red", {})
    # Uretilip SONRAKI adimlarda (03, 04) elenenler: {ad: {"adim", "neden"}}.
    # Kalicidir: geri donulup o adimlarin kaydi silinse de 02.3 bu
    # degiskenleri yeniden onermez / tasimaz.
    d.setdefault("elenen", {})
    durum["defter"] = d
    return d


def _simdi():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _kayit(kaynak, k):
    ifade = str(k.get("ifade") or "").strip()
    return {"ad": str(k.get("ad") or "").strip(), "kaynak": kaynak,
            "ifade": ifade[:400], "imza": ifade_imza(ifade) if kaynak == "kesif" else "",
            "anlam": str(k.get("anlam") or k.get("gerekce") or k.get("aciklama") or "").strip()[:400],
            "kaynak_kolonlar": [str(x) for x in (k.get("kaynak_kolonlar") or k.get("kolonlar") or [])],
            "ozet": k.get("ozet") if isinstance(k.get("ozet"), dict) else {},
            "adim": ADIM_ADI.get(kaynak, ""), "zaman": _simdi()}


def _red_anahtari(kayit):
    return "%s|%s" % (kayit["kaynak"], kayit.get("imza") or kayit["ad"].upper())


def uretim_kaydet(durum, kaynak, kayitlar):
    """Bir adimin urettigi degiskenler: [{"ad", "ifade", "anlam" /
    "gerekce", "kaynak_kolonlar", "ozet"}]. Ayni degisken onceden
    reddedildiyse red kaydi silinir (yeniden uretildi)."""
    d = _defter(durum)
    for k in kayitlar or []:
        r = _kayit(kaynak, k)
        if not r["ad"]:
            continue
        d["uretilen"][r["ad"]] = r
        d["red"].pop(_red_anahtari(r), None)
        for a in [a for a, x in d["red"].items() if x.get("ad") == r["ad"] and x.get("kaynak") == kaynak]:
            d["red"].pop(a, None)


def red_kaydet(durum, kaynak, kayitlar, neden):
    """Onerilip / uretilip REDDEDILEN degiskenler. neden: metin ya da
    {ad: metin}."""
    d = _defter(durum)
    for k in kayitlar or []:
        r = _kayit(kaynak, k)
        if not r["ad"] or r["ad"] in d["uretilen"]:
            continue
        r["neden"] = str((neden.get(r["ad"]) if isinstance(neden, dict) else neden) or "")[:300]
        d["red"][_red_anahtari(r)] = r


def adim_yenilendi(durum, kaynak, uretilen_adlar, neden=None):
    """Adim yeniden calistirildi: o adimin onceden urettigi ama bu turda
    uretmedigi degiskenler reddedilenlere tasinir."""
    d = _defter(durum)
    yeni = set(map(str, uretilen_adlar or []))
    for ad in [a for a, r in d["uretilen"].items() if r.get("kaynak") == kaynak and a not in yeni]:
        r = d["uretilen"].pop(ad)
        r["neden"] = neden or "Adım yeniden çalıştırıldı; bu turda üretilmedi (seçilmedi)."
        r["zaman"] = _simdi()
        d["red"][_red_anahtari(r)] = r


def adim_silindi(durum, kaynak):
    """Adimin kolonlari BASKA bir adim yeniden calistigi icin dustu (02.2
    yenilenince 02.3 kolonlari tablodan duser): kayitlari silinir ama
    reddedilmis SAYILMAZ; ayni degisken yeniden onerilebilir."""
    d = _defter(durum)
    for ad in [a for a, r in d["uretilen"].items() if r.get("kaynak") == kaynak]:
        d["uretilen"].pop(ad)


def kural_secilmeyenler(durum):
    """02.2'de OLCULUP SECILMEYEN donusumler (birim x donusum): durumdaki
    olcum ozetinden (geleneksel.katki) turetilir, ayrica saklanmaz.
    [{"ad" (olcumdeki en iyi kolon), "kaynak": "kural", "anlam",
    "kaynak_kolonlar", "olcum": {"iv", "kolon_sayisi", "degerli"}, "neden"}]."""
    g = durum.get("geleneksel") if isinstance(durum.get("geleneksel"), dict) else {}
    katki = g.get("katki") if isinstance(g.get("katki"), dict) else {}
    if not katki or "karar" not in g:
        return []
    karar = g.get("karar") if isinstance(g.get("karar"), dict) else {}
    birim = {b.get("id"): b for b in (g.get("birimler") or []) if isinstance(b, dict)}
    try:
        from fe_agent import geleneksel as G
        kod_adi = {k: v["ad"] for k, v in G.KATALOG_HARITA.items()}
    except Exception:           # pylint: disable=broad-except
        kod_adi = {}
    uretilen = set(map(str, g.get("uretilen") or []))
    cikti = []
    for bid, kb in katki.items():
        secili = set((karar.get(bid) or {}).get("sec") or [])
        b = birim.get(bid) or {}
        for kod, olc in ((kb or {}).get("kodlar") or {}).items():
            if kod in secili or not isinstance(olc, dict) or not olc.get("kolon"):
                continue
            if str(olc["kolon"]) in uretilen:
                continue
            degerli = bool(olc.get("degerli"))
            cikti.append({
                "ad": str(olc["kolon"]), "kaynak": "kural", "ifade": "", "imza": "",
                "anlam": "%s dönüşümü (%s)" % (kod_adi.get(kod, kod),
                                               ", ".join(map(str, (b.get("kolonlar") or [])[:4])) or bid),
                "kaynak_kolonlar": [str(x) for x in (b.get("kolonlar") or [])][:8],
                "ozet": {}, "adim": "02.2",
                "olcum": {"iv": olc.get("iv"), "kolon_sayisi": olc.get("kolon_sayisi"),
                          "degerli": degerli},
                "neden": ("Ölçüldü ama seçilmedi" if degerli
                          else "Ölçüldü, katkısı sınırın altında kaldı; seçilmedi")})
    return cikti


def bilinenler(durum):
    """02.3 icin: {"uretilen": [kayit], "reddedilen": [kayit], "adlar":
    {AD}, "imzalar": {imza: ad}}. Uretilenlerde 02.1 cozum ve 02.2 kural
    kolonlari da vardir (defterde kaydi olmayanlar sozluk satirindan)."""
    d = _defter(durum)
    uretilen = dict(d["uretilen"])
    # Defterden once uretilmis (eski calisma) kolonlar: ad ve sozluk aciklamasi.
    try:
        ek = {str(x.get("DEGISKEN")): x
              for x in (list(((durum.get("geleneksel") or {}).get("sozluk_ek")) or [])
                        + list(((durum.get("profil") or {}).get("sozluk_ek")) or []))
              if isinstance(x, dict) and x.get("DEGISKEN")}
    except Exception:           # pylint: disable=broad-except
        ek = {}
    kaynaklar = durum.get("uretilen_kaynak") if isinstance(durum.get("uretilen_kaynak"), dict) else {}
    for ad in [str(a) for a in (durum.get("uretilen") or []) if a]:
        if ad in uretilen:
            continue
        kaynak = next((k for k, v in kaynaklar.items() if ad in (v or [])), "kural")
        x = ek.get(ad) or {}
        uretilen[ad] = {"ad": ad, "kaynak": kaynak, "ifade": "", "imza": "",
                        "anlam": str(x.get("ACIKLAMA") or "")[:400],
                        "kaynak_kolonlar": [s.strip() for s in str(x.get("KAYNAK_KOLON") or "").split(",") if s.strip()],
                        "ozet": {}, "adim": ADIM_ADI.get(kaynak, ""), "zaman": ""}
    red = list(d["red"].values()) + kural_secilmeyenler(durum)
    # Uretilip sonraki adimlarda elenenler de reddedilmis sayilir.
    for ad, e in d["elenen"].items():
        r = uretilen.pop(ad, None)
        if r is not None:
            red.append(dict(r, neden=e.get("neden") or "", eleme_adim=e.get("adim") or ""))
    imzalar = {}
    for r in list(uretilen.values()) + red:
        if r.get("imza"):
            imzalar.setdefault(r["imza"], r["ad"])
    return {"uretilen": list(uretilen.values()), "reddedilen": red,
            "adlar": {r["ad"].upper() for r in list(uretilen.values()) + red},
            "imzalar": imzalar}


def kesif_tasinacaklar(durum):
    """02.3 yeniden acildiginda listeye TASINACAK degiskenler: onceki turda
    02.3'te uretilmis, sonradan elenmemis ve ifadesi kayitli olanlar.
    [{"ad", "ifade", "gerekce"}]."""
    d = _defter(durum)
    return [{"ad": r["ad"], "ifade": r["ifade"], "gerekce": r.get("anlam") or ""}
            for r in d["uretilen"].values()
            if r.get("kaynak") == "kesif" and r.get("ifade") and r["ad"] not in d["elenen"]]


def kesif_notu(durum, sinir=BILINEN_SINIR):
    """Dil modeline giden satirlar: once reddedilenler (yeniden onerilmesi
    en olasi olanlar), sonra uretilenler. Satir: "AD = ifade | anlam"."""
    b = bilinenler(durum)

    def satir(r, ek=""):
        govde = r["ad"]
        if r.get("ifade"):
            govde += " = " + r["ifade"][:120]
        elif r.get("kaynak_kolonlar"):
            govde += " (kaynak: %s)" % ", ".join(r["kaynak_kolonlar"][:4])
        if r.get("anlam"):
            govde += " | " + r["anlam"][:100]
        return govde + ek
    red = [satir(r, " | reddedildi: %s" % (r.get("neden") or "-")[:80]) for r in b["reddedilen"]]
    ure = [satir(r) for r in b["uretilen"]]
    return red[:sinir], ure[:max(sinir - len(red), 0)]


def tekrar_mi(durum, ad, ifade, bilinen=None):
    """Oneri daha once uretilmis ya da reddedilmis mi? Doner: neden metni
    ya da ""."""
    b = bilinen or bilinenler(durum)
    if str(ad or "").upper() in b["adlar"]:
        return "aynı adla daha önce üretildi ya da reddedildi"
    onceki = b["imzalar"].get(ifade_imza(ifade))
    if onceki:
        return "aynı hesap daha önce %s adıyla üretildi ya da reddedildi" % onceki
    return ""


# ---------------------------------------------------------------------------
# DEFTERIN TAMAMI (durumdan turetilir) ve dosyaya yazim
# ---------------------------------------------------------------------------
def _anlamlar(durum):
    try:
        from fe_agent import akis_faz02
        return akis_faz02._aciklamalar(durum)      # pylint: disable=protected-access
    except Exception:           # pylint: disable=broad-except
        return {}


def _ham_cikarilanlar(durum):
    """{kolon: (adim, neden)}: ham kolonlarin ciktigi yer ve nedeni."""
    cikti = {}
    meta = {str(v) for v in (durum.get("meta") or {}).values() if v}
    # 02.1: uretime girmeyenler ve Çıkar denenler.
    try:
        from fe_agent import akis_faz02 as f2
        p = durum.get("profil") or {}
        t = p.get("profil_teshis") or {}
        karar = p.get("profil_karar") if isinstance(p.get("profil_karar"), dict) else {}
        neden = {}
        for anahtar, metin in (("cok_bos", "çoğu boş"), ("sabit", "hep aynı değer"),
                               ("kimlik_gibi", "numara gibi (her satırda farklı)"),
                               ("yuksek_kardinalite", "çok fazla farklı değer"),
                               ("tarih", "tarih kolonu (türevleri üretildi)"),
                               ("ayni_icerik", "başka bir kolonun aynısı")):
            for k in t.get(anahtar) or []:
                neden.setdefault(str(k), metin)
        if durum.get("updt_asama") in getattr(f2, "UPDT_ASAMALARI", ())[2:] or not f2.updt_modu(durum):
            for k in f2.kusurlu_kolonlar(durum):
                k = str(k)
                if k in meta:
                    continue
                cikti[k] = ("02.1", "Veri profili: " + (
                    neden.get(k) or ("kararınızla çıkarıldı" if karar.get(k) == f2.PROFIL_KARAR_CIKAR
                                     else "üretime girmez")))
    except Exception:           # pylint: disable=broad-except
        pass
    # 01.3: surec disi (haric_kolonlar; 01.2.3.1'de cikanlar ayri).
    try:
        from fe_agent.akis_durum import cikarilan_kolonlar, SPLIT_KOLON
        tanimsiz = cikarilan_kolonlar(durum)
    except Exception:           # pylint: disable=broad-except
        tanimsiz, SPLIT_KOLON = set(), "_SPLIT"
    for k in durum.get("haric_kolonlar") or []:
        k = str(k)
        if k in meta or k == SPLIT_KOLON:
            continue
        cikti[k] = (("01.2.3.1", "Tanımsız ya da bilgi taşımayan kolon (boş / tek değerli / "
                                 "sözlükte tanımı yok)") if k in tanimsiz
                    else ("01.3", "Süreç dışı bırakıldı"))
    return cikti


def _sonraki_elemeler(durum):
    """{degisken: (adim, neden)}: 03 ve 04'te elenenler (kalite, secim)."""
    cikti = {}
    kalite = durum.get("kalite") if isinstance(durum.get("kalite"), dict) else {}
    for etiket, anahtar in (("boş değer", "eksik"), ("sabit", "sabit"), ("kararsız (stabilite)", "kararsiz"),
                            ("SFA kararı", "sfa"), ("sızıntı", "sizinti")):
        for k in kalite.get(anahtar) or []:
            cikti.setdefault(str(k), ("03", "Elendi: " + etiket))
    kaynak_ad = (durum.get("baz") or {}).get("kaynak") or {}
    kaynak_ad = kaynak_ad if isinstance(kaynak_ad, dict) else {}
    secim = {}
    for r in durum.get("secim_tablo") or []:
        if isinstance(r, dict) and r.get("FEATURE"):
            ad = str(kaynak_ad.get(r["FEATURE"], r["FEATURE"]))
            if ad not in secim or (r.get("SECILDI") and not secim[ad].get("SECILDI")):
                secim[ad] = r
    for ad, r in secim.items():
        if not r.get("SECILDI"):
            cikti.setdefault(ad, ("04", "Aday sete seçilmedi: %s" % (r.get("GEREKCE") or "-")))
    return cikti


def kur(durum):
    """Defterin tamami (dict). Baz veri profili yoksa None."""
    profil = durum.get("profil") or {}
    ham = [k for k in (profil.get("kolon_ozet") or []) if isinstance(k, dict) and k.get("ad") is not None]
    if not ham:
        return None
    anlam = _anlamlar(durum)
    yeni_ad = durum.get("kolon_yeni_ad") if isinstance(durum.get("kolon_yeni_ad"), dict) else {}
    meta = {str(v): k for k, v in (durum.get("meta") or {}).items() if v}
    rol_adi = {"target": "hedef", "id": "kimlik", "donem": "dönem", "segment": "segment"}
    ham_cikan = _ham_cikarilanlar(durum)
    sonra = _sonraki_elemeler(durum)
    b = bilinenler(durum)
    kalan, cikarilan = [], []
    ham_adlar = set()
    for kp in ham:
        eski = str(kp["ad"])
        ad = str(yeni_ad.get(eski) or eski)
        ham_adlar |= {eski, ad}
        kayit = {"ad": ad, "kaynak": "ham", "kaynak_adi": KAYNAK_ADI["ham"],
                 "anlam": str(anlam.get(ad) or anlam.get(eski) or "")[:600],
                 "ozet": _profil_ozeti(kp)}
        if ad != eski:
            kayit["eski_ad"] = eski
        if eski in meta or ad in meta:
            kayit["rol"] = rol_adi.get(meta.get(eski) or meta.get(ad), "")
        yer = ham_cikan.get(eski) or ham_cikan.get(ad) or sonra.get(ad) or sonra.get(eski)
        if yer and not kayit.get("rol"):
            kayit["adim"], kayit["neden"] = yer
            cikarilan.append(kayit)
        else:
            kalan.append(kayit)

    def uretilen_kaydi(r):
        return {"ad": r["ad"], "kaynak": r.get("kaynak") or "", "kaynak_adi": KAYNAK_ADI.get(r.get("kaynak"), ""),
                "anlam": r.get("anlam") or "", "ifade": r.get("ifade") or "",
                "kaynak_kolonlar": r.get("kaynak_kolonlar") or [], "ozet": r.get("ozet") or {},
                "uretildigi_adim": r.get("adim") or ""}
    for r in b["uretilen"]:
        if r["ad"] in ham_adlar:
            continue
        kayit = uretilen_kaydi(r)
        yer = sonra.get(r["ad"])
        if yer:
            kayit["adim"], kayit["neden"] = yer
            cikarilan.append(kayit)
        else:
            kalan.append(kayit)
    for r in b["reddedilen"]:
        kayit = uretilen_kaydi(r)
        kayit["adim"], kayit["neden"] = r.get("eleme_adim") or r.get("adim") or "", r.get("neden") or ""
        if r.get("olcum"):
            kayit["olcum"] = r["olcum"]
        cikarilan.append(kayit)

    def say(liste, kaynak):
        return sum(1 for x in liste if x.get("kaynak") == kaynak)
    return {
        "surum": DEFTER_SURUMU,
        "aciklama": "Değişken defteri: veri setinde kalan ve çalışma boyunca çıkarılan ya da "
                    "reddedilen bütün değişkenler. Her adım sonunda yeniden yazılır.",
        "veri_seti": durum.get("veri_seti"),
        "hedef": (durum.get("meta") or {}).get("target"),
        "guncelleme": _simdi(),
        "asama": durum.get("updt_asama") or "",
        "sayim": {"kalan": len(kalan), "cikarilan": len(cikarilan),
                  "kalan_ham": say(kalan, "ham"),
                  "kalan_uretilen": len(kalan) - say(kalan, "ham"),
                  "cikarilan_ham": say(cikarilan, "ham"),
                  "cikarilan_uretilen": len(cikarilan) - say(cikarilan, "ham")},
        "kalan": kalan,
        "cikarilan": cikarilan,
    }


def dosya_yolu(durum):
    from fe_agent.akis_faz01 import amp_klasor_adi
    return "/%s/%s" % (str(amp_klasor_adi(durum)).strip("/"), DEFTER_DOSYA)


def guncelle(durum):
    """Defteri kurar ve calisma klasorune yazar. Doner: (yol, sayim) ya da
    (None, None) (baz veri profili henuz yok). Icerik degismediyse yazmaz."""
    # Uretilen degiskenlerden sonraki adimlarda elenenler kalici kayda.
    try:
        d = _defter(durum)
        for ad, (adim, neden) in _sonraki_elemeler(durum).items():
            if ad in d["uretilen"]:
                d["elenen"][ad] = {"adim": adim, "neden": neden}
    except Exception:           # pylint: disable=broad-except
        pass
    defter = kur(durum)
    if defter is None:
        return None, None
    govde = dict(defter)
    govde.pop("guncelleme", None)
    imza = hashlib.md5(json.dumps(govde, ensure_ascii=False, sort_keys=True,
                                  default=str).encode("utf-8")).hexdigest()
    yol = dosya_yolu(durum)
    if durum.get("_defter_imza") == imza:
        return yol, defter["sayim"]
    from fe_agent.akis_durum import _folder
    _folder().upload_stream(yol, json.dumps(defter, ensure_ascii=False, indent=1, default=str).encode("utf-8"))
    durum["_defter_imza"] = imza
    durum["defter_dosya"] = {"yol": yol, "sayim": defter["sayim"], "zaman": defter["guncelleme"]}
    return yol, defter["sayim"]
