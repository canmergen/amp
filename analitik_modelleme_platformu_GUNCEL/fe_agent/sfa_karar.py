# -*- coding: utf-8 -*-
"""fe_agent/sfa_karar.py - SFA: DEGISKEN DETAYI, KARARLAR, YAPAY ZEKA KARARI.

KULLANICI KARARLARI
  - SFA bir ELEME yeri degildir: IV ya da C-value dusuk diye degisken
    elenmez. SFA'nin sorusu "degisken modele EN IYI hangi haliyle girer".
  - Metrikleri KOD hesaplar; her degisken icin nasil girecegine YAPAY ZEKA
    karar verir (degisken basina ayri karar). Kullanici her karari panelde
    degistirebilir; kullanicinin karari yapay zekanin ustundedir.
  - C-value bes donusumle olculur: ham, kirpilmis (%5), log, ustel, sira.
  - Aralik onerileri SFA'nin icindedir: "Ayrıklaştırma: Önerilen Aralıklar".

KARAR ALANLARI (her degisken)
  tip            "yok" | tip_donusum kodu ("kategorik_metin", "sayisal_nokta",
                   "sayisal_virgul"). TIP KARARI YALNIZCA SFA'DA. Kural onerir, kullanici degistirir; dil
                   modeli tipi degistirmez (tipin cevabi verinin kendisinde).
                   Tip degisince degiskenin SFA detayi yeni tiple yeniden
                   hesaplanir (akis_faz02.sfa_tip_degistir).
  kullan         "evet" | "hayir"   (hayir yalnizca sizinti / hassas icin)
  eksik          "yok" | "medyan" | "sabit" | "isaret" | "missing"
                   isaret : eksik isareti kolonu (<K>_EKSIK) + medyan
                   missing: kategorikte eksikler ayri "MISSING" kategorisi
  eksik_deger    sabit doldurma degeri
  aykiri         "yok" | "winsor"   (train %5 - %95, kullanici karari)
  donusum        "yok" | "log" | "ustel" | "sira"
  ayriklastirma  "yok" | "onerilen" (SFA'nin hedefe gore araliklari)
  yorum, gerekce, kaynak ("kural" | "yapay_zeka" | "kullanici")

DOSYALAR (calismanin klasorunde)
  sfa_aralik.json    degisken detayi: aralik onerisi + "sfa" metrikleri +
                     "dagilim" (grafik aralik tablolari). SFA her calistiginda
                     yeniden yazilir.
  sfa_kararlar.json  kararlar. Kural varsayilanlariyla yazilir, yapay zeka
                     ve kullanici guncelledikce degisir.
"""

import json
import threading
import time
import uuid

import numpy as np
import pandas as pd

import re

from fe_agent import aralik as aralik_mod
from fe_agent import tip_donusum

KARAR_DOSYA = "sfa_kararlar.json"
GRAFIK_ARALIK = 20          # grafikteki ince aralik sayisi (ornek ekranla ayni)
KATEGORI_GOSTER = 19        # grafikte en cok kategori; gerisi "Diğer"
KIRPMA = 0.05               # winsor: train %5 ve %95
CARPIK_ESIK = 2.0           # varsayilan log donusumu icin carpiklik esigi
AYKIRI_ESIK = 0.005         # uc cit disindaki pay bunu gecerse winsor

KULLAN = ("evet", "hayir")
EKSIK = ("yok", "medyan", "sabit", "isaret", "missing")
AYKIRI = ("yok", "winsor")
DONUSUM = ("yok", "log", "ustel", "sira")
AYRIKLASTIRMA = ("yok", "onerilen")

ETIKET = {
    "kullan": {"evet": "Evet", "hayir": "Hayır"},
    "eksik": {"yok": "Yok", "medyan": "Medyan", "sabit": "Sabit Değer",
              "isaret": "Eksik İşareti + Medyan", "missing": "MISSING Kategorisi"},
    "aykiri": {"yok": "Yok", "winsor": "Winsor (%5)"},
    "donusum": {"yok": "Yok", "log": "Log", "ustel": "Üstel", "sira": "Sıra"},
    "ayriklastirma": {"yok": "Yok", "onerilen": "Önerilen Aralıklar"},
}
KARAR_ALANLARI = ("tip", "kullan", "eksik", "eksik_deger", "aykiri", "donusum",
                  "ayriklastirma", "yorum")

# SFA'da teklif edilen tip donusumleri: yalnizca modelde anlamli hedefler
# (sayisal <-> kategorik). Tarihe cevirmek bir model degiskeni icin
# anlamsiz; donem kolonunun tarih isareti 01.3'te kaliyor.
TIP_ADAYLARI = {
    "kategorik": ("sayisal_nokta", "sayisal_virgul"),
    "sayısal": ("kategorik_metin",),
}
# Sayisal bir kolonun KOD oldugunu gosteren ad parcalari (01.3'teki
# eski kuralin aynisi). Ad + az sayida tam sayi deger birlikte varsa
# kategorik onerilir; ad tek basina yetmez.
KOD_AD_PARCALARI = {"KOD", "KODU", "CODE", "CD", "TIP", "TIPI", "TYPE",
                    "SEGMENT", "SEG", "SINIF", "CLASS", "GRUP", "GROUP",
                    "KATEGORI", "CAT", "IL", "ILCE", "SUBE", "BRANCH",
                    "SEKTOR", "SECTOR", "MESLEK", "STATU", "STATUS"}


def seri_tipi(s):
    return ("kategorik" if (not pd.api.types.is_numeric_dtype(s)
                            or pd.api.types.is_bool_dtype(s)) else "sayısal")


def tip_secenekleri(s):
    """Kolonun TAM VERIYLE uygulanabilir tip donusumleri (AMP kolonu).
    Doner: [{"kod", "hedef", "etiket"}]."""
    if pd.api.types.is_bool_dtype(s):
        return []
    cikti = []
    for kod in TIP_ADAYLARI.get(seri_tipi(s), ()):
        try:
            uygun, _sebep = tip_donusum.denetle(s, kod)
        except Exception:        # pylint: disable=broad-except
            uygun = False
        if uygun:
            cikti.append({"kod": kod, "hedef": tip_donusum.hedef_tip(kod),
                          "etiket": tip_donusum.DONUSUMLER[kod]["etiket"]})
    return cikti


def tip_onerisi(ad, s, secenekler):
    """Kural tabanli tip onerisi: (kod, sebep) ya da (None, None).
      - Metin kolon, tum degerler sayi (basinda sifirli kod yoksa) -> sayisal
      - Sayisal kolon, adi kod/tip/segment bildiriyor, tam sayi ve en cok
        50 farkli deger -> kategorik"""
    kodlar = [o["kod"] for o in secenekler]
    if not kodlar:
        return None, None
    if seri_tipi(s) == "kategorik":
        m = s.dropna().astype(str).str.strip()
        if bool(m.str.match(r"^[+-]?0\d").any()):
            return None, None          # 00123 gibi kodlar sayi degil
        sira = (("sayisal_virgul", "sayisal_nokta") if bool(m.str.contains(",", regex=False).any())
                else ("sayisal_nokta", "sayisal_virgul"))
        for kod in sira:
            if kod in kodlar:
                return kod, "Metin olarak okunmuş ama değerlerin tamamı sayı"
        return None, None
    parca = {p for p in re.split(r"[^0-9A-Za-zÇĞİÖŞÜçğıöşü]+", str(ad).upper()) if p}
    if "kategorik_metin" in kodlar and parca & KOD_AD_PARCALARI:
        dolu = pd.to_numeric(s.dropna(), errors="coerce")
        tekil = int(dolu.nunique())
        if 2 <= tekil and bool((dolu % 1 == 0).all()):
            return ("kategorik_metin",
                    "Adı kod/tip/segment bildiriyor ve %d farklı tam sayı değer var; "
                    "sayı olarak değil kategori olarak modellenmeli" % tekil)
    return None, None


def tip_uygula(s, kod):
    """Tip kararini seriye uygular; cevrilemezse seri AYNEN doner."""
    if not kod or kod == "yok" or not tip_donusum.gecerli_kod(kod):
        return s
    yeni, takilan, _ = tip_donusum.cevir(s, kod)
    return s if takilan else yeni


# ===========================================================================
# DEGISKEN DETAYI (grafik ve metrikler)
# ===========================================================================
def _yuvarla(v, b=6):
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return round(v, b) if np.isfinite(v) else None


def _etiket_araligi(mn, mx):
    if mn is None:
        return "-"
    if mx is None or mn == mx:
        return aralik_mod._sayi_metni(mn)
    return "%s - %s" % (aralik_mod._sayi_metni(mn), aralik_mod._sayi_metni(mx))


def _sayisal_tablo(x, y, toplam):
    """x dolu train degerleri, y 0/1. Doner: grafik aralik tablosu."""
    kesimler = aralik_mod.esit_frekans_kesimleri(x, GRAFIK_ARALIK)
    kutu = np.searchsorted(kesimler, x.to_numpy(), side="left")
    t = pd.DataFrame({"k": kutu, "x": x.to_numpy(), "y": y.to_numpy()})
    g = t.groupby("k").agg(n=("y", "size"), kotu=("y", "sum"),
                           mn=("x", "min"), mx=("x", "max"), ort=("x", "mean"))
    return [{"etiket": _etiket_araligi(float(r["mn"]), float(r["mx"])),
             "alt": _yuvarla(r["mn"]), "ust": _yuvarla(r["mx"]),
             "ort": _yuvarla(r["ort"]), "n": int(r["n"]),
             "pay": _yuvarla(r["n"] / toplam), "kotu": int(r["kotu"]),
             "oran": _yuvarla(r["kotu"] / r["n"])} for _k, r in g.iterrows()]


def _kategorik_tablo(x, y, toplam):
    t = pd.DataFrame({"x": x.astype(str).to_numpy(), "y": y.to_numpy()})
    g = t.groupby("x").agg(n=("y", "size"), kotu=("y", "sum")).sort_values(
        "n", ascending=False)
    ust = g.iloc[:KATEGORI_GOSTER]
    satirlar = [{"etiket": str(k), "n": int(r["n"]), "pay": _yuvarla(r["n"] / toplam),
                 "kotu": int(r["kotu"]), "oran": _yuvarla(r["kotu"] / r["n"])}
                for k, r in ust.iterrows()]
    kalan = g.iloc[KATEGORI_GOSTER:]
    if len(kalan):
        n, k = int(kalan["n"].sum()), int(kalan["kotu"].sum())
        satirlar.append({"etiket": "Diğer (%d kategori)" % len(kalan), "n": n,
                         "pay": _yuvarla(n / toplam), "kotu": k,
                         "oran": _yuvarla(k / n) if n else None})
    # Hedef oranina gore sirali: egilim grafikte okunur
    satirlar.sort(key=lambda r: (r["oran"] is None, r["oran"] or 0))
    return satirlar


def degisken_detayi(s, y, tr, c_ler=None):
    """SFA ekrani icin metrikler ve grafik tablolari. Hepsi TRAIN satirlari.
    Doner: {"sfa": metrikler, "dagilim": {"ham": [...], "kirpik": [...],
    "eksik": {...} | None}}"""
    kategorik = not pd.api.types.is_numeric_dtype(s) or pd.api.types.is_bool_dtype(s)
    yb = pd.to_numeric(y, errors="coerce")
    m = tr & yb.notna()
    x, t = s[m], (yb[m] > 0).astype(int)
    toplam = float(len(x)) or 1.0
    bos = x.isna()
    dolu_x, dolu_t = x[~bos], t[~bos]
    metrik = {
        "tip": "kategorik" if kategorik else "sayısal",
        "satir": int(len(x)),
        "eksik_sayisi": int(bos.sum()),
        "eksik_orani": _yuvarla(bos.mean()) if len(x) else None,
        "eksik_hedef_orani": _yuvarla(t[bos].mean()) if bos.any() else None,
        "hedef_orani": _yuvarla(t.mean()) if len(t) else None,
        "c": {k: _yuvarla(v, 4) for k, v in (c_ler or {}).items()},
    }
    eksik = None
    if bos.any():
        eksik = {"etiket": "Eksik", "n": int(bos.sum()),
                 "pay": _yuvarla(bos.sum() / toplam), "kotu": int(t[bos].sum()),
                 "oran": _yuvarla(t[bos].mean())}
    dagilim = {"eksik": eksik}
    if kategorik:
        metrik.update(tekil=int(dolu_x.nunique()))
        dagilim["ham"] = _kategorik_tablo(dolu_x, dolu_t, toplam) if len(dolu_x) else []
        return {"sfa": metrik, "dagilim": dagilim}

    xn = pd.to_numeric(dolu_x, errors="coerce")
    if not len(xn):
        dagilim["ham"] = dagilim["kirpik"] = []
        return {"sfa": metrik, "dagilim": dagilim}
    q = np.nanpercentile(xn, [1, 5, 25, 50, 75, 95, 99])
    iqr = q[4] - q[2]
    cit_alt, cit_ust = q[2] - 3 * iqr, q[4] + 3 * iqr
    metrik.update(
        min=_yuvarla(xn.min()), max=_yuvarla(xn.max()), medyan=_yuvarla(q[3]),
        ortalama=_yuvarla(xn.mean()), q05=_yuvarla(q[1]), q95=_yuvarla(q[5]),
        carpiklik=_yuvarla(xn.skew(), 3) if len(xn) > 2 else None,
        aykiri_payi=_yuvarla(((xn < cit_alt) | (xn > cit_ust)).mean(), 4),
        tekil=int(xn.nunique()))
    dagilim["ham"] = _sayisal_tablo(xn, dolu_t, toplam)
    dagilim["kirpik"] = _sayisal_tablo(xn.clip(q[1], q[5]), dolu_t, toplam)
    return {"sfa": metrik, "dagilim": dagilim}


# ===========================================================================
# KURAL TABANLI VARSAYILAN KARAR (yapay zeka gelene kadar ve yedek)
# ===========================================================================
def kural_karari(d, sizinti=False):
    """d: degisken detayi (aralik + "sfa"). Kararin gerekcesi de yazilir."""
    m = d.get("sfa") or {}
    kategorik = m.get("tip") == "kategorik"
    k = {"tip": d.get("tip_uygulanan") or "yok",
         "kullan": "evet", "eksik": "yok", "eksik_deger": None, "aykiri": "yok",
         "donusum": "yok", "ayriklastirma": "yok", "yorum": "", "kaynak": "kural"}
    neden = []
    if k["tip"] != "yok" and d.get("tip_sebebi"):
        neden.append("tip %s olarak alındı (%s)" % (
            m.get("tip") or "", d["tip_sebebi"][0].lower() + d["tip_sebebi"][1:]))
    if sizinti:
        k["kullan"] = "hayir"
        neden.append("C-value 0,95'in üstünde: hedefi neredeyse birebir veriyor, "
                     "sızıntı şüphesi")
    hassas = d.get("hassas")
    aralik_var = (d.get("aralik_sayisi") or 1) > 1
    if hassas:
        if aralik_var:
            k["ayriklastirma"] = "onerilen"
            neden.append("hassas değişken (%s): ham hâli yerine kaba aralıklar" % hassas)
        else:
            k["kullan"] = "hayir"
            neden.append("hassas değişken (%s) ve hedefle anlamlı ilişki yok" % hassas)
    if m.get("eksik_sayisi"):
        if kategorik:
            k["eksik"] = "missing"
        elif d.get("notlar"):
            k["eksik"] = "isaret"
            neden.append("eksiklerin hedef oranı doluların belirgin farklı")
        else:
            k["eksik"] = "medyan"
    if not kategorik:
        if d.get("sekil") in ("U", "ters U") and aralik_var:
            k["ayriklastirma"] = "onerilen"
            neden.append("ilişki %s şeklinde; doğrusal girişte kaybolur" % d.get("sekil"))
        if k["ayriklastirma"] == "yok":
            if (m.get("aykiri_payi") or 0) > AYKIRI_ESIK:
                k["aykiri"] = "winsor"
                neden.append("uç değer payı %%%s" % aralik_mod._sayi_metni(
                    100 * m["aykiri_payi"]))
            if (m.get("carpiklik") or 0) > CARPIK_ESIK and (m.get("min") or 0) >= 0:
                k["donusum"] = "log"
                neden.append("sağa çarpık dağılım (çarpıklık %s)"
                             % aralik_mod._sayi_metni(m["carpiklik"]))
    elif aralik_var:
        k["ayriklastirma"] = "onerilen"
        neden.append("kategoriler hedef oranına göre %d gruba toplanıyor"
                     % d.get("aralik_sayisi"))
    k["gerekce"] = ("; ".join(neden) + ".") if neden else \
        "Ek işlem gerekmiyor; değişken olduğu gibi girer."
    k["gerekce"] = k["gerekce"][0].upper() + k["gerekce"][1:]
    return k


def karar_dogrula(k, kategorik, tip_kodlari=None):
    """Disaridan gelen (yapay zeka / kullanici) karari gecerli degerlere indirger.
    tip_kodlari verilirse "tip" alani da denetlenir (yalnizca kullanici);
    verilmezse tip alanina hic dokunulmaz."""
    t = {}
    if tip_kodlari is not None:
        t["tip"] = k.get("tip") if k.get("tip") in tip_kodlari else "yok"
    t["kullan"] = k.get("kullan") if k.get("kullan") in KULLAN else "evet"
    eksik = k.get("eksik") if k.get("eksik") in EKSIK else "yok"
    if kategorik and eksik in ("medyan", "sabit", "isaret"):
        eksik = "missing"
    if not kategorik and eksik == "missing":
        eksik = "isaret"
    t["eksik"] = eksik
    try:
        t["eksik_deger"] = (None if k.get("eksik_deger") in (None, "")
                            else float(str(k["eksik_deger"]).replace(",", ".")))
    except (TypeError, ValueError):
        t["eksik_deger"] = None
    if t["eksik"] == "sabit" and t["eksik_deger"] is None:
        t["eksik"] = "medyan"
    t["aykiri"] = k.get("aykiri") if (k.get("aykiri") in AYKIRI and not kategorik) else "yok"
    t["donusum"] = k.get("donusum") if (k.get("donusum") in DONUSUM and not kategorik) else "yok"
    t["ayriklastirma"] = k.get("ayriklastirma") if k.get("ayriklastirma") in AYRIKLASTIRMA else "yok"
    t["yorum"] = str(k.get("yorum") or "")[:500]
    return t


# ===========================================================================
# DOSYALAR (kilitli okuma / yazma; yapay zeka isi ayni dosyayi gunceller)
# ===========================================================================
_DOSYA_KILIT = threading.RLock()
_ONBELLEK = {}              # yol -> (zaman, veri); ayni surecte yazan biz


ONBELLEK_SINIRI = 6         # ayni anda acik calisma sayisi kadar


def _onbellege(yol, veri):
    _ONBELLEK.pop(yol, None)
    _ONBELLEK[yol] = veri
    while len(_ONBELLEK) > ONBELLEK_SINIRI:
        _ONBELLEK.pop(next(iter(_ONBELLEK)))


def _oku(yol):
    from fe_agent.akis_durum import _folder
    with _DOSYA_KILIT:
        if yol in _ONBELLEK:
            return _ONBELLEK[yol]
        try:
            with _folder().get_download_stream(yol) as akis:
                veri = json.loads(akis.read().decode("utf-8") or "{}")
        except Exception:
            veri = {}
        _onbellege(yol, veri)
        return veri


def _yaz(yol, veri):
    from fe_agent.akis_durum import metin_yaz
    with _DOSYA_KILIT:
        metin_yaz(yol, json.dumps(veri, ensure_ascii=False, default=str))
        _onbellege(yol, veri)


def detay_oku(yol):
    return _oku(yol)


def detay_yaz(yol, veri):
    _yaz(yol, veri)


def kararlar_oku(yol):
    return _oku(yol)


def kararlari_yaz(yol, kararlar):
    _yaz(yol, kararlar)


def kullanici_karari(yol, ad, alanlar, kategorik, yeni_karar=None):
    """Paneldeki formdan gelen karar. Kullanicinin karari kalicidir:
    yapay zeka isi bu degiskeni artik degistirmez.
    yeni_karar: tip degistiyse yeni tiple kurulmus kural karari; formun
    eski tipe gore doldurulmus alanlari yerine o yazilir (yorum korunur)."""
    with _DOSYA_KILIT:
        kararlar = dict(_oku(yol))
        eski = kararlar.get(ad) or {}
        if yeni_karar is not None:
            yeni = dict(yeni_karar)
            yeni["yorum"] = str(alanlar.get("yorum", eski.get("yorum", "")) or "")[:500]
            yeni["kaynak"] = "kullanici"
            kararlar[ad] = yeni
            _yaz(yol, kararlar)
            return yeni
        yeni = dict(eski)
        yeni.update(karar_dogrula(dict(eski, **alanlar), kategorik))
        yeni["tip"] = eski.get("tip", "yok")
        yeni["kaynak"] = "kullanici"
        kararlar[ad] = yeni
        _yaz(yol, kararlar)
        return yeni


# ===========================================================================
# YAPAY ZEKA KARARI (arka plan isi, degisken basina ayri karar)
# ===========================================================================
_ISLER = {}
_IS_KILIT = threading.Lock()
IS_SINIRI = 8


def ai_girdisi(detay, kararlar):
    """Dil modeline giden ozet: yalnizca hesaplanmis metrikler, ham veri yok."""
    cikti = []
    for ad, d in detay.items():
        m = d.get("sfa") or {}
        ayri = d.get("ayri") or {}
        cikti.append({
            "ad": ad, "aciklama": str(d.get("aciklama") or "")[:160],
            "tip": m.get("tip"), "tip_kaynak": d.get("tip_kaynak") or m.get("tip"),
            "eksik_orani": m.get("eksik_orani"),
            "eksik_hedef_orani": m.get("eksik_hedef_orani"),
            "hedef_orani": m.get("hedef_orani"),
            "min": m.get("min"), "max": m.get("max"), "medyan": m.get("medyan"),
            "carpiklik": m.get("carpiklik"), "aykiri_payi": m.get("aykiri_payi"),
            "tekil": m.get("tekil"), "c": m.get("c") or {},
            "iv_ham": d.get("ham_iv"), "iv_onerilen": ayri.get("iv"),
            "sekil": d.get("sekil"), "aralik_sayisi": d.get("aralik_sayisi"),
            "araliklar": [(r.get("etiket"), r.get("pay"), r.get("oran"))
                          for r in (ayri.get("satirlar") or [])][:9],
            "tutarlilik": d.get("tutarlilik") or {}, "hassas": d.get("hassas"),
            "sizinti": bool(d.get("sizinti")), "notlar": d.get("notlar") or [],
            "kural": {k: (kararlar.get(ad) or {}).get(k)
                      for k in ("kullan", "eksik", "aykiri", "donusum", "ayriklastirma")},
        })
    return cikti


def ai_baslat(karar_yolu, girdi):
    """Arka planda degisken basina karar. Sonuclar geldikce karar dosyasina
    yazilir; kullanicinin degistirdigi degiskenlere dokunulmaz."""
    from fe_agent import llm
    kimlik = uuid.uuid4().hex[:12]
    kategorik = {g["ad"]: g.get("tip") == "kategorik" for g in girdi}
    with _IS_KILIT:
        for k in sorted(_ISLER, key=lambda k: _ISLER[k]["zaman"])[:-IS_SINIRI or None]:
            if _ISLER[k]["durum"] != "calisiyor":
                _ISLER.pop(k, None)
        _ISLER[kimlik] = {"durum": "calisiyor", "zaman": time.time(), "biten": 0,
                          "toplam": len(girdi), "hata": None, "yol": karar_yolu}

    def isle(parca):
        with _IS_KILIT:
            if _ISLER[kimlik].get("iptal"):
                return
        with _DOSYA_KILIT:
            kararlar = dict(_oku(karar_yolu))
            for ad, k in parca.items():
                eski = kararlar.get(ad) or {}
                if eski.get("kaynak") == "kullanici":
                    continue
                yeni = dict(eski)
                yeni.update(karar_dogrula(k, kategorik.get(ad, False)))
                yeni["tip"] = eski.get("tip", "yok")      # tip kural/kullanici karari
                yeni["yorum"] = eski.get("yorum", "")
                yeni["gerekce"] = str(k.get("gerekce") or "")[:500]
                yeni["kaynak"] = "yapay_zeka"
                kararlar[ad] = yeni
            _yaz(karar_yolu, kararlar)
        with _IS_KILIT:
            _ISLER[kimlik]["biten"] += len(parca)

    def calis():
        try:
            _sonuc, hata = llm.sfa_karar_ver(girdi, isle)
            with _IS_KILIT:
                _ISLER[kimlik].update(durum="bitti", hata=hata)
        except Exception as e:   # pylint: disable=broad-except
            with _IS_KILIT:
                _ISLER[kimlik].update(durum="bitti", hata="%s: %s" % (
                    type(e).__name__, str(e)[:200]))

    threading.Thread(target=calis, daemon=True).start()
    return kimlik


def ai_durdur(kimlik):
    """Kararlar onaylandi ya da SFA yeniden hesaplaniyor: bu isin gelen
    sonuclari artik dosyaya yazilmaz."""
    with _IS_KILIT:
        if kimlik in _ISLER:
            _ISLER[kimlik]["iptal"] = True


def ai_durumu(kimlik):
    with _IS_KILIT:
        d = _ISLER.get(str(kimlik or ""))
        return None if d is None else {k: v for k, v in d.items() if k != "yol"}


# ===========================================================================
# KARARLARIN UYGULANMASI (Analitik Baz Set)
# ===========================================================================
def _ek(adlar):
    return "".join("_" + a for a in adlar)


def uygula(df, tr, kararlar, detay):
    """Kararlari baz sete uygular (yerinde degil, yeni df doner).
    Parametreler (medyan, kirpma sinirlari, donusum olcekleri) TRAIN'den.
    Doner: (df, rapor) rapor = {"dusen", "uretilen", "degisen": {ham: yeni}}."""
    df = df.copy()
    rapor = {"dusen": [], "uretilen": [], "degisen": {}, "doldurulan": 0, "tip": {}}
    for ad, k in (kararlar or {}).items():
        if ad not in df.columns:
            continue
        d = detay.get(ad) or {}
        s = df[ad]
        if k.get("tip") not in (None, "", "yok") and k.get("kullan") != "hayir":
            # TIP ONCE: aralik kesimleri / gruplari zaten yeni tiple hesaplandi
            s = tip_uygula(s, k["tip"])
            df[ad] = s
            rapor["tip"][ad] = k["tip"]
        kategorik = not pd.api.types.is_numeric_dtype(s) or pd.api.types.is_bool_dtype(s)
        if k.get("kullan") == "hayir":
            df = df.drop(columns=[ad])
            rapor["dusen"].append(ad)
            continue
        yeni_kolonlar = {}
        if k.get("ayriklastirma") == "onerilen" and (d.get("kesimler") is not None
                                                     or d.get("gruplar") is not None):
            plan = {"tur": "aralik", "kesimler": d.get("kesimler"),
                    "gruplar": d.get("gruplar"), "etiketler": d.get("etiketler")}
            kaynak = s
            if not kategorik and k.get("eksik") in ("medyan", "sabit"):
                kaynak = s.fillna(_doldurma_degeri(s, tr, k))
            yeni_kolonlar["%s_ARALIK" % ad] = aralik_mod.uygula_seri(kaynak, plan)
            if not kategorik and k.get("eksik") == "isaret":
                yeni_kolonlar["%s_EKSIK" % ad] = s.isna().astype(int)
        elif kategorik:
            if k.get("eksik") == "missing" and s.isna().any():
                df[ad] = s.astype(object).where(s.notna(), "MISSING")
                rapor["doldurulan"] += 1
            continue
        else:
            x = pd.to_numeric(s, errors="coerce")
            ekler = []
            if k.get("eksik") == "isaret" and x.isna().any():
                yeni_kolonlar["%s_EKSIK" % ad] = x.isna().astype(int)
            if x.isna().any():
                x = x.fillna(_doldurma_degeri(x, tr, k))
                rapor["doldurulan"] += 1
            if k.get("aykiri") == "winsor":
                alt, ust = np.nanpercentile(x[tr].dropna(), [100 * KIRPMA, 100 * (1 - KIRPMA)])
                x = x.clip(alt, ust)
                ekler.append("KIRP")
            dn = k.get("donusum")
            if dn == "log":
                x = np.sign(x) * np.log1p(np.abs(x))
                ekler.append("LOG")
            elif dn == "ustel":
                t = x[tr].dropna()
                enk, genis = float(t.min()), float(t.max() - t.min()) or 1.0
                x = np.exp(((x - enk) / genis).clip(-5, 5))
                ekler.append("USTEL")
            elif dn == "sira":
                sirali = np.sort(x[tr].dropna().to_numpy())
                x = pd.Series(np.searchsorted(sirali, x.to_numpy(), side="right")
                              / float(len(sirali) or 1), index=x.index)
                ekler.append("SIRA")
            if not ekler:
                # Ayni ad kalir (yalnizca doldurma); eksik isareti eklenir
                df[ad] = x
                for yeni_ad, seri in yeni_kolonlar.items():
                    df[yeni_ad] = seri
                    rapor["uretilen"].append(yeni_ad)
                continue
            yeni_kolonlar[ad + _ek(ekler)] = x
        # Model degiskenin TEK bir halini gorur: yeni hal varsa ham kolon cikar
        df = df.drop(columns=[ad])
        for yeni_ad, seri in yeni_kolonlar.items():
            df[yeni_ad] = seri
            rapor["uretilen"].append(yeni_ad)
        asil = [a for a in yeni_kolonlar if not a.endswith("_EKSIK")]
        rapor["degisen"][ad] = asil[0] if asil else None
    return df, rapor


def _doldurma_degeri(x, tr, k):
    if k.get("eksik") == "sabit" and k.get("eksik_deger") is not None:
        return float(k["eksik_deger"])
    med = pd.to_numeric(x[tr], errors="coerce").median()
    return 0.0 if pd.isna(med) else float(med)
