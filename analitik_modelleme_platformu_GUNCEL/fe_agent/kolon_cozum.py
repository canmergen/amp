"""fe_agent/kolon_cozum.py - 02.1 COZUM ONERILERI (kolon atmadan once).

ILKE: Veri Profili bir kolonu "uretime girmez" diye yakaladiginda kolon
dogrudan atilmaz; once duzeltme yolu onerilir, kullanici secer. Yalniz
hicbir cozum yoksa (gercek kimlik numarasi gibi) kolon disarida kalir.

Cozumler (her biri kolondan YENI bir kolon uretir, ham kolon uretime
girmez):
  hedef_grupla : kategoriler hedef oranina gore siralanir, oranlari
                 istatistiksel olarak ayirt edilemeyen komsular
                 birlestirilir; her grupta egitim satirlarinin en az %5'i,
                 en cok 8 grup (aralik.py ile ayni kural). Az satirli
                 kategoriler once "Seyrek" grubunda toplanir.
                 YALNIZ EGITIM satirlarindan ogrenilir; egitimde
                 gorulmeyen deger "Seyrek" grubuna duser.
  seyrek_grupla: hedefe bakmadan: en sik N deger kalir, gerisi "Diğer".
  onek_grupla  : kod yapisindaki kolon (posta kodu, sube kodu) ilk k
                 karakteriyle gruplanir, sonra hedef_grupla.
  dolu_bayrak  : cok bos kolonda "dolu mu" bayragi (1/0); deger
                 kullanilmaz.
  metin        : serbest metinden ozellik (bkz. metin_ozellik.py).
  cikar        : kolon disarida kalir.

Butun hesaplar tablonun TAMAMINDA, kesin sayimla (orneklem yok).
"""

import re

import numpy as np
import pandas as pd

from fe_agent import aralik as aralik_mod

# Seyrek kategori: egitimde bundan az satiri olan deger tek basina
# oranlanmaz (orani gurultu), "Seyrek" grubuna girer.
SEYREK_MIN_SATIR = 30
# seyrek_grupla: en sik kac deger kalir.
SEYREK_EN_SIK = 20
# Kod oneki: onekle olusan grup sayisi bu araliktaysa onek anlamli.
ONEK_EN_AZ_GRUP, ONEK_EN_COK_GRUP = 2, 200
# Degerlerin bu kadari ayni uzunluktaysa kolon kod yapisinda sayilir.
ONEK_AYNI_UZUNLUK = 0.80
# Serbest metin: farkli degerlerin ortalama sozcuk sayisi ya da uzunlugu.
METIN_SOZCUK, METIN_UZUNLUK = 3.0, 25.0

SEYREK_ETIKET = "Seyrek"
DIGER_ETIKET = "Diğer"
BOS_ETIKET = "Boş"

COZUM_ADI = {
    "hedef_grupla": "Hedef oranına göre grupla",
    "seyrek_grupla": "Seyrek değerleri «Diğer»de topla",
    "onek_grupla": "Kodun ilk karakterleriyle grupla",
    "dolu_bayrak": "«Dolu mu» bayrağı üret",
    "metin": "Metinden özellik çıkar",
    "cikar": "Çıkar",
    "kod_bos_bayrak": "Kodu boş say ve bayrak üret",
    "kod_bos": "Kodu boş say",
    "negatif_bos": "Negatifleri boş say",
    "kirp": "Uçları kırp",
    "birak": "Olduğu gibi bırak",
}
COZUM_ACIKLAMA = {
    "hedef_grupla": ("Hedef oranı birbirine yakın değerler aynı grupta birleşir (en fazla 8 "
                     "grup, her grupta eğitim satırlarının en az %5'i). Gruplar yalnız eğitim "
                     "verisinden öğrenilir; eğitimde görülmeyen değer «Seyrek» grubuna düşer."),
    "seyrek_grupla": ("En sık %d değer olduğu gibi kalır, kalanlar «Diğer» grubunda toplanır. "
                      "Hedefe bakılmaz." % SEYREK_EN_SIK),
    "onek_grupla": ("Değerler kodun ilk karakterleriyle gruplanır (ör. posta kodunun ilk iki "
                    "hanesi il), ardından hedef oranına göre birleştirilir."),
    "dolu_bayrak": ("Kolonun dolu olup olmadığını gösteren 1/0 bayrağı üretilir; boş olması "
                    "da bilgi taşıyabilir. Değerin kendisi kullanılmaz."),
    "metin": ("Metinler sözcüklere ayrılır; hedefle ilişkili sözcükler ve birlikte geçen "
              "sözcüklerden konular çıkarılır, her satır için bayrak ve sayı kolonları "
              "üretilir. Bütün satırlarda kodla yapılır."),
    "cikar": "Kolon değişken üretimine girmez.",
}
COZUM_ACIKLAMA.update({
    "kod_bos_bayrak": ("Özel kod (ör. -1, -999) olan hücreler boş sayılır; kodun olduğu satırlar "
                       "ayrıca 1/0 bayrağıyla işaretlenir. Kodun taşıdığı bilgi (ör. «hiç "
                       "işlem yok») kaybolmaz, sayı gibi de kullanılmaz."),
    "kod_bos": "Özel kod olan hücreler boş sayılır; kodun olduğu satırlar ayrıca işaretlenmez.",
    "negatif_bos": ("Negatif olamayacak bir ölçüdeki negatif değerler hatalı sayılır ve boş "
                    "yapılır; diğer değerler değişmez."),
    "kirp": ("Sınırın üstündeki değerler sınıra çekilir. Sınır yalnız eğitim satırlarından "
             "öğrenilir: sıfır olmayan değerlerin %99'luk değeri (seyrek kolonda sıfırlar "
             "sınırı düşürmesin diye)."),
    "birak": "Kolon değiştirilmeden kullanılır.",
})
# Duzeltme: kolon uretime girer, secilen duzeltme analiz tablosunda
# uygulanir (girdi veri seti degismez). Kontrol -> secenekler, oneri.
DUZELTME_SECENEK = {"gizli_eksik": ["kod_bos_bayrak", "kod_bos", "birak"],
                    "negatif": ["negatif_bos", "birak"],
                    "uc": ["birak", "kirp"]}
DUZELTME_ONERI = {"gizli_eksik": "kod_bos_bayrak", "negatif": "negatif_bos", "uc": "birak"}
DUZELTME_SIRA = ("gizli_eksik", "negatif", "uc")


def duzeltme_ogren(kontrol, secim, x, egitim, kayit=None):
    """Secilen duzeltmenin bilgisi. gizli: {"kod"}; uc/kirp: {"sinir"}
    (egitim satirlarinda sifir olmayan dolu degerlerin %99'u)."""
    kayit = kayit or {}
    if kontrol == "gizli_eksik":
        return {"kod": float(kayit.get("kod"))}
    if kontrol == "uc" and secim == "kirp":
        t = pd.to_numeric(x[egitim], errors="coerce").dropna()
        t = t[t != 0]
        if not len(t):
            return {}
        return {"sinir": float(np.nanpercentile(t.to_numpy(dtype=float), 99))}
    return {}


def duzeltme_uygula(kontrol, secim, x, bilgi):
    """Doner: (yeni seri, bayrak serisi ya da None). Ayni duzeltme iki kez
    uygulansa da sonuc degismez (bayrak ayrica, ham degerden hesaplanir)."""
    if secim == "birak":
        return x, None
    sx = pd.to_numeric(x, errors="coerce")
    if kontrol == "gizli_eksik" and "kod" in bilgi:
        kodlu = sx == float(bilgi["kod"])
        bayrak = kodlu.astype("int8") if secim == "kod_bos_bayrak" else None
        return sx.where(~kodlu), bayrak
    if kontrol == "negatif" and secim == "negatif_bos":
        return sx.where(~(sx < 0)), None
    if kontrol == "uc" and secim == "kirp" and "sinir" in bilgi:
        return sx.clip(upper=float(bilgi["sinir"])), None
    return x, None


# Yeni kolonun adi: <KOLON>_<EK>.
COZUM_EKI = {"hedef_grupla": "GRP", "seyrek_grupla": "GRP", "onek_grupla": "ONEK_GRP",
             "dolu_bayrak": "DOLU", "kod_bos_bayrak": "KOD"}


def _metin_mi(s):
    return not pd.api.types.is_numeric_dtype(s) or pd.api.types.is_bool_dtype(s)


def serbest_metin_mi(s):
    """Farkli degerlerin ortalama sozcuk sayisi ya da uzunlugu yuksekse
    kolon serbest metindir (not, aciklama, adres); kategori degildir."""
    if not _metin_mi(s):
        return False
    d = pd.Series(s.dropna().astype(str).unique())
    if not len(d):
        return False
    sozcuk = d.str.split().str.len().mean()
    uzunluk = d.str.len().mean()
    return bool(sozcuk >= METIN_SOZCUK or uzunluk >= METIN_UZUNLUK)


def onek_uzunlugu(s):
    """Kod yapisindaki kolonda anlamli onek uzunlugu: degerlerin cogu ayni
    uzunlukta ve ilk k karakter 2-200 grup veriyorsa en buyuk k. Yoksa
    None."""
    d = s.dropna().astype(str).str.strip()
    d = d[d != ""]
    if not len(d):
        return None
    uz = d.str.len()
    en_cok = uz.value_counts()
    if not len(en_cok) or en_cok.iloc[0] / len(d) < ONEK_AYNI_UZUNLUK:
        return None
    L = int(en_cok.index[0])
    if L < 3:
        return None
    secilen = None
    for k in range(1, L):
        n = int(d.str[:k].nunique())
        if ONEK_EN_AZ_GRUP <= n <= ONEK_EN_COK_GRUP:
            secilen = k
        elif n > ONEK_EN_COK_GRUP:
            break
    return secilen


def _ikili_mi(y):
    if y is None:
        return False
    v = set(pd.to_numeric(y, errors="coerce").dropna().unique().tolist())
    return bool(v) and v <= {0, 1}


# Gruplamanin gercek olup olmadigi: egitim satirlarinin yarisinda ogrenilen
# gruplar diger yarida hedefi ayirmali (AUC'nin 0,5'ten farki z ile).
GRUP_DOGRULAMA_Z = 2.58


def _gruplama_tutarli(x, y, egitim):
    """Doner: (gecerli mi, grup sayisi). Egitim satirlari sirayla ikiye
    ayrilir (tek / cift); A'da ogrenilen grup oranlari B'de hedefi ayirmazsa
    (rastgele kimlikte oldugu gibi) gruplama gurultudur."""
    tam = hedef_grupla_ogren(x, y, egitim)
    if len(tam["gruplar"]) < 2:
        return False, len(tam["gruplar"])
    sira = np.cumsum(egitim.to_numpy()) % 2 == 1
    a = egitim & pd.Series(sira, index=egitim.index)
    b = egitim & ~a
    oa = hedef_grupla_ogren(x, y, a)
    if len(oa["gruplar"]) < 2:
        return False, len(tam["gruplar"])
    oran = {g["no"]: g["oran"] for g in oa["gruplar"]}
    harita = oa["harita"]
    yb = pd.to_numeric(y, errors="coerce")
    gecerli = b & yb.notna()
    skor = _anahtar(x)[gecerli].map(harita).fillna(oa["varsayilan"]).map(oran).astype(float)
    hedef = (yb[gecerli] > 0).astype(int)
    n1, n0 = int(hedef.sum()), int(len(hedef) - hedef.sum())
    if not n1 or not n0:
        return False, len(tam["gruplar"])
    sira_puan = skor.rank(method="average")
    auc = (sira_puan[hedef == 1].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0)
    se = np.sqrt((n1 + n0 + 1) / (12.0 * n1 * n0))
    return bool((auc - 0.5) / se >= GRUP_DOGRULAMA_Z), len(tam["gruplar"])


def _sayi_metni(n):
    return "{:,}".format(int(n)).replace(",", ".")


def oneriler(df, teshis, kardinalite_esik=None, y=None, egitim=None):
    """Uretime girmez denen kolonlar icin cozum secenekleri:
    {kolon: {"kontrol", "secenekler": [kod], "oneri": kod, "gerekce",
    "onek": k}}. Sabit ve ayni icerikli kolonlar icin cozum yok (sabit
    bilgi tasimaz; ayni icerikte biri zaten kalir).

    Bir secenek yalniz ise yarayacaksa sunulur: hedef oranina gore
    gruplama egitim satirlarinda en az iki farkli grup veriyorsa, seyrek
    toplama en az iki sik deger varsa (hepsi seyrekse tek degerli kolon
    cikar). Kimlik benzeri listesi once bakilir; kolon iki listede de
    varsa satiri kimlik benzeri kontrolundedir."""
    if egitim is None:
        egitim = pd.Series(True, index=df.index)
    ikili = _ikili_mi(y)
    cikti = {}
    kimlik = [k for k in teshis.get("kimlik_gibi") or [] if k in df.columns]
    yuksek = [k for k in teshis.get("yuksek_kardinalite") or []
              if k in df.columns and k not in kimlik]
    for k in kimlik + yuksek:
        kontrol = "kimlik_gibi" if k in kimlik else "yuksek_kardinalite"
        x = df[k]
        if serbest_metin_mi(x):
            cikti[k] = {"kontrol": kontrol, "secenekler": ["metin", "cikar"], "oneri": "metin",
                        "gerekce": "Değerler serbest metin (uzun, çok sözcüklü); metinden "
                                   "özellik çıkarılabilir."}
            continue
        secenek, gerekce, onek = [], [], None
        if _metin_mi(x) and ikili:
            tamam, ng = _gruplama_tutarli(x, y, egitim)
            if tamam:
                secenek.append("hedef_grupla")
                gerekce.append("Değerler kategori (%s farklı değer); hedef oranı farklı %d "
                               "gruba ayrılabiliyor." % (_sayi_metni(x.nunique()), ng))
        L = onek_uzunlugu(x) if ikili else None
        if L:
            tamam, ng = _gruplama_tutarli(onek_seri(x, L), y, egitim)
            if tamam:
                secenek.append("onek_grupla")
                onek = L
                gerekce.append("Değerler kod yapısında (çoğu aynı uzunlukta); ilk %d karakter "
                               "hedef oranı farklı %d gruba ayrılıyor." % (L, ng))
        if _metin_mi(x):
            tekil = _sayi_metni(x.nunique())
            sayim = _anahtar(x)[egitim].value_counts()
            # Ikili hedefte hedef gruplamasi tutmadiysa degerler hedefi
            # ayirmiyor; sik degerleri korumak da bilgi katmaz.
            if (not ikili or "hedef_grupla" in secenek) \
                    and int((sayim >= SEYREK_MIN_SATIR).sum()) >= 2:
                secenek.append("seyrek_grupla")
                if not gerekce:
                    gerekce.append("Değerler kategori (%s farklı değer); sık değerler korunup "
                                   "kalanlar toplanabilir." % tekil)
        if secenek:
            cikti[k] = {"kontrol": kontrol, "secenekler": secenek + ["cikar"],
                        "oneri": secenek[0], "gerekce": " ".join(gerekce)}
            if onek:
                cikti[k]["onek"] = onek
        else:
            cikti[k] = {"kontrol": kontrol, "secenekler": ["cikar"], "oneri": "cikar",
                        "gerekce": ("Gerçek kimlik numarası gibi; değerlerde kullanılabilir bir "
                                    "yapı bulunmadı." if kontrol == "kimlik_gibi" else
                                    "Değerler hedef oranı farklı gruplara ayrılmıyor: eğitim "
                                    "satırlarının bir yarısında bulunan gruplar diğer yarısında "
                                    "tutmadı.")}
    for k in teshis.get("cok_bos") or []:
        if k not in df.columns or k in cikti:
            continue
        dolu = int(df[k][egitim].notna().sum())
        bos = int(egitim.sum()) - dolu
        yok = {"kontrol": "cok_bos", "secenekler": ["cikar"], "oneri": "cikar"}
        if dolu < SEYREK_MIN_SATIR or bos < SEYREK_MIN_SATIR:
            cikti[k] = dict(yok, gerekce="Eğitim satırlarında dolu ya da boş satır çok az; "
                                         "doluluk bayrağı bilgi taşımaz.")
            continue
        gerekce = "Kolonun dolu olup olmaması hedefle ilişkili olabilir."
        if ikili:
            yb = pd.to_numeric(y, errors="coerce")
            g = egitim & yb.notna()
            d = df[k][g].notna()
            h = (yb[g] > 0).astype(int)
            n1, n0 = int(d.sum()), int((~d).sum())
            if not n1 or not n0:
                cikti[k] = dict(yok, gerekce="Hedefi dolu eğitim satırlarında doluluk ayrımı yok.")
                continue
            p1, p0 = float(h[d].mean()), float(h[~d].mean())
            pp = float(h.mean())
            se = np.sqrt(pp * (1 - pp) * (1.0 / n1 + 1.0 / n0)) if 0 < pp < 1 else 0.0
            yz = lambda v: "%" + ("%.1f" % (v * 100)).replace(".", ",")
            if not se or abs(p1 - p0) / se < GRUP_DOGRULAMA_Z:
                # Doluluk hedefi ayirmiyor: bayrak bilgi tasimaz.
                cikti[k] = dict(yok, gerekce="Eğitim satırlarında hedef oranı dolu satırlarda %s, "
                                             "boş satırlarda %s; fark anlamlı değil, doluluk "
                                             "bayrağı bilgi taşımaz." % (yz(p1), yz(p0)))
                continue
            gerekce = ("Eğitim satırlarında hedef oranı dolu satırlarda %s, boş satırlarda %s; "
                       "doluluk hedefi ayırıyor." % (yz(p1), yz(p0)))
        cikti[k] = {"kontrol": "cok_bos", "secenekler": ["dolu_bayrak", "cikar"],
                    "oneri": "dolu_bayrak", "gerekce": gerekce}
    return cikti


# ---------------------------------------------------------------------------
# OGRENME (yalniz egitim satirlari) ve UYGULAMA
# ---------------------------------------------------------------------------
def _anahtar(s):
    """Kategori anahtari: metin, kirpilmis; bos -> BOS_ETIKET."""
    return s.astype(str).str.strip().where(s.notna(), BOS_ETIKET)


def hedef_grupla_ogren(x, y, egitim):
    """Doner: {"harita": {deger: grup_no}, "gruplar": [{"no", "degerler",
    "n", "oran"}], "varsayilan": grup_no}. x: tum satirlar; y: hedef (0/1);
    egitim: bool maske."""
    xa = _anahtar(x)
    yb = (pd.to_numeric(y, errors="coerce") > 0).astype(int)
    gecerli = egitim & pd.to_numeric(y, errors="coerce").notna()
    xt, yt = xa[gecerli], yb[gecerli]
    sayim = xt.value_counts()
    seyrek = set(sayim[sayim < SEYREK_MIN_SATIR].index)
    xg = xt.where(~xt.isin(seyrek), SEYREK_ETIKET)
    ince = aralik_mod._ince_kategorik(xg, yt)
    toplam = int(len(xg))
    ar = aralik_mod._son_adim(ince, toplam) if ince else []
    harita, gruplar = {}, []
    for i, b in enumerate(ar, start=1):
        degerler = list(b.get("degerler") or [])
        for d in degerler:
            harita[d] = i
        gruplar.append({"no": i, "degerler": degerler, "n": int(b["n"]),
                        "oran": (float(b["kotu"]) / b["n"]) if b["n"] else 0.0})
    # Seyrek degerler ve egitimde gorulmeyenler Seyrek grubunun numarasini alir.
    varsayilan = harita.get(SEYREK_ETIKET)
    if varsayilan is None and gruplar:
        # Seyrek grubu yoksa en kalabalik grup.
        varsayilan = max(gruplar, key=lambda g: g["n"])["no"]
    for d in seyrek:
        harita[d] = varsayilan
    return {"harita": harita, "gruplar": gruplar, "varsayilan": varsayilan}


def seyrek_grupla_ogren(x, egitim):
    xa = _anahtar(x)
    sik = list(xa[egitim].value_counts().index[:SEYREK_EN_SIK])
    return {"harita": {d: d for d in sik}, "varsayilan": DIGER_ETIKET,
            "gruplar": [{"no": d, "degerler": [d]} for d in sik]}


def onek_seri(x, k):
    return x.astype(str).str.strip().str[:int(k)].where(x.notna())


def ogren(cozum, x, y, egitim, onek=None):
    """Secilen cozumun egitimden ogrenilen bilgisi (uygula'ya verilir)."""
    if cozum == "hedef_grupla":
        return hedef_grupla_ogren(x, y, egitim)
    if cozum == "seyrek_grupla":
        return seyrek_grupla_ogren(x, egitim)
    if cozum == "onek_grupla":
        o = hedef_grupla_ogren(onek_seri(x, onek), y, egitim)
        o["onek"] = int(onek)
        return o
    return {}


def uygula(cozum, x, bilgi):
    """Yeni kolonun degerleri (x ile ayni indeks). hedef ve onek
    gruplamada grup etiketi (G1, G2, ...), seyrekte deger ya da Diğer,
    bayrakta 1/0."""
    if cozum == "dolu_bayrak":
        return x.notna().astype("int8")
    if cozum == "onek_grupla":
        x = onek_seri(x, bilgi.get("onek"))
    if cozum in ("hedef_grupla", "onek_grupla"):
        # Grup etiketi metin ("G1", "G2" ...): sonraki adimlarda kategori
        # olarak ele alinir (grup numarasi bir sayi buyuklugu degil).
        harita = bilgi.get("harita") or {}
        v = _anahtar(x).map(harita).fillna(bilgi.get("varsayilan"))
        return v.map(lambda g: ("G%d" % int(g)) if pd.notna(g) else None)
    if cozum == "seyrek_grupla":
        harita = bilgi.get("harita") or {}
        return _anahtar(x).map(harita).fillna(bilgi.get("varsayilan") or DIGER_ETIKET)
    return None


def yeni_kolon_adi(kolon, cozum, mevcut=()):
    ek = COZUM_EKI.get(cozum)
    if not ek:
        return None
    ad = "%s_%s" % (kolon, ek)
    i = 2
    while ad in mevcut:
        ad = "%s_%s%d" % (kolon, ek, i)
        i += 1
    return ad


def grup_ozeti(bilgi, en_cok=4):
    """Kayit metni: "Grup 1 (%2,1): İstanbul, Ankara +3; Grup 2 ..." """
    parca = []
    for g in bilgi.get("gruplar") or []:
        d = [str(x) for x in g.get("degerler") or []]
        oran = g.get("oran")
        bas = "Grup %s" % g["no"] + ((" (%%%s)" % ("%.1f" % (oran * 100)).replace(".", ","))
                                     if isinstance(oran, float) else "")
        parca.append("%s: %s" % (bas, ", ".join(d[:en_cok]) + (" +%d" % (len(d) - en_cok)
                                                                if len(d) > en_cok else "")))
    return "; ".join(parca)


# ---------------------------------------------------------------------------
# METIN: serbest metinden ozellik (dil modeli yok; bütün satirlarda kodla)
# ---------------------------------------------------------------------------
# Hedefle iliskili sozcuk: egitimde en az bu kadar satirda gecmeli.
METIN_MIN_SATIR = 30
METIN_MIN_PAY = 0.005
# Bayrak kolonu uretilecek en cok sozcuk ve anlamlilik (iki oran z).
METIN_BAYRAK_EN_COK = 10
METIN_Z = 2.58
# Konu: sozluk boyutu ve konu sayisi.
METIN_KONU_SOZLUK = 2000
METIN_KONU_SAYISI = 8
METIN_KAT = 5            # skor: egitim satirlarinda katlama disi (sizinti yok)
_LAPLACE = 0.5
_TR_KUCUK = str.maketrans({"I": "ı", "İ": "i"})
_SOZCUK_RE = r"[a-zçğıöşüâîû]{2,}"
_DUR = set("""ve ile bir bu şu o da de ki mi mı mu mü için gibi olan olarak ama veya ya
yada çok daha en her ne sonra önce kadar ise değil var yok olup olduğu oldu olur
ilgili üzere göre tarafından ayrıca hem ancak fakat çünkü dolayı nedeniyle the and""".split())
_ASCII = str.maketrans({"ç": "C", "ğ": "G", "ı": "I", "ö": "O", "ş": "S", "ü": "U",
                        "â": "A", "î": "I", "û": "U"})


def _sozcukler(x):
    """Her satirin sozcuk kumesi (liste; tekrarlar atilir, sira korunur)."""
    m = x.astype(str).where(x.notna(), "").str.translate(_TR_KUCUK).str.lower()
    return m.str.findall(_SOZCUK_RE).map(
        lambda ls: list(dict.fromkeys(w for w in ls if w not in _DUR)))


def _sozcuk_kolon_eki(w):
    return re.sub(r"[^A-Z0-9]", "", w.translate(_ASCII).upper())[:20] or "S"


def metin_ogren(x, y, egitim):
    """Egitim satirlarindan: sozcuklerin WoE'si (skor icin), bayrak
    sozcukleri (hedefle anlamli iliskili) ve konular (sklearn varsa)."""
    yb = (pd.to_numeric(y, errors="coerce") > 0).astype(int)
    gec = egitim & pd.to_numeric(y, errors="coerce").notna()
    sz = _sozcukler(x)
    st, yt = sz[gec], yb[gec]
    n = int(len(st))
    kotu_t = int(yt.sum())
    iyi_t = n - kotu_t
    min_satir = max(METIN_MIN_SATIR, int(np.ceil(METIN_MIN_PAY * n)))
    ex = pd.DataFrame({"w": st, "y": yt}).explode("w").dropna(subset=["w"])
    if not len(ex) or not kotu_t or not iyi_t:
        return {"sozcuk": {}, "bayrak": [], "konu": None, "min_satir": min_satir,
                "not": "Eğitim satırlarında yeterli sözcük ya da hedef çeşitliliği yok."}
    g = ex.groupby("w")["y"].agg(["size", "sum"])
    g = g[g["size"] >= min_satir]
    k = len(g)
    woe = {}
    bayrak = []
    p0 = kotu_t / n
    for w, r in g.iterrows():
        nk, kk = int(r["size"]), int(r["sum"])
        pk = (kk + _LAPLACE) / (kotu_t + _LAPLACE * 2)
        pi = (nk - kk + _LAPLACE) / (iyi_t + _LAPLACE * 2)
        woe[w] = float(np.log(pk / pi))
        n2, k2 = n - nk, kotu_t - kk
        if n2 > 0:
            pa, pb = kk / nk, k2 / n2
            se = np.sqrt(p0 * (1 - p0) * (1.0 / nk + 1.0 / n2))
            z = (pa - pb) / se if se > 0 else 0.0
            if abs(z) >= METIN_Z:
                bayrak.append((abs(z), w, nk, pa))
    bayrak = [{"sozcuk": w, "satir": nk, "oran": pa}
              for _z, w, nk, pa in sorted(bayrak, reverse=True)[:METIN_BAYRAK_EN_COK]]
    bilgi = {"sozcuk": woe, "bayrak": bayrak, "min_satir": min_satir, "konu": None,
             "sozcuk_sayisi": k}
    # KONU: TF-IDF + NMF (yalniz egitim satirlariyla ogrenilir).
    try:
        from sklearn.decomposition import NMF
        from sklearn.feature_extraction.text import TfidfVectorizer
        sozluk = list(g.sort_values("size", ascending=False).index[:METIN_KONU_SOZLUK])
        if len(sozluk) >= METIN_KONU_SAYISI * 2:
            vek = TfidfVectorizer(vocabulary=sozluk, analyzer=lambda ls: ls)
            X = vek.fit_transform(st)
            dolu = np.asarray(X.sum(axis=1)).ravel() > 0
            if int(dolu.sum()) >= METIN_KONU_SAYISI * 10:
                nmf = NMF(n_components=METIN_KONU_SAYISI, init="nndsvd", random_state=0,
                          max_iter=300)
                nmf.fit(X[dolu])
                adlar = [", ".join(sozluk[i] for i in np.argsort(-c)[:4]) for c in nmf.components_]
                bilgi["konu"] = {"sozluk": sozluk, "idf": [float(v) for v in vek.idf_],
                                 "bilesen": nmf.components_.tolist(), "adlar": adlar}
    except Exception as e:      # sklearn yoksa konu uretilmez; nedeni kayitta
        bilgi["konu_notu"] = "Konu çıkarılamadı (%s)." % str(e)[:80]
    return bilgi


def metin_uygula(x, bilgi, egitim=None, y=None, kolon="METIN"):
    """Yeni kolonlar (DataFrame): <KOL>_SOZCUK (sozcuk sayisi), <KOL>_SKOR
    (sozcuklerin egitimde ogrenilen WoE ortalamasi; egitim satirlarinda
    katlama disi), <KOL>_K_<SOZCUK> bayraklari, <KOL>_KONU."""
    sz = _sozcukler(x)
    out = pd.DataFrame(index=x.index)
    out["%s_SOZCUK" % kolon] = sz.map(len).astype("int32")
    woe = bilgi.get("sozcuk") or {}

    def skor(ls, tablo):
        v = [tablo[w] for w in ls if w in tablo]
        return float(np.mean(v)) if v else 0.0
    s = sz.map(lambda ls: skor(ls, woe))
    # Egitim satirlari: kendi katinin disindaki satirlardan ogrenilen WoE
    # (satirin kendi hedefi skoruna karismaz).
    if egitim is not None and y is not None and bool(egitim.any()):
        kat = pd.Series(np.arange(len(x)) % METIN_KAT, index=x.index)
        for f in range(METIN_KAT):
            maske_ogren = egitim & (kat != f)
            hedef_satir = egitim & (kat == f)
            if not bool(hedef_satir.any()):
                continue
            alt = metin_ogren_woe(sz, y, maske_ogren, bilgi.get("min_satir") or METIN_MIN_SATIR)
            s[hedef_satir] = sz[hedef_satir].map(lambda ls: skor(ls, alt))
    out["%s_SKOR" % kolon] = s.astype(float)
    gor = set(out.columns)
    for b in bilgi.get("bayrak") or []:
        ad = "%s_K_%s" % (kolon, _sozcuk_kolon_eki(b["sozcuk"]))
        while ad in gor:
            ad += "_"
        gor.add(ad)
        out[ad] = sz.map(lambda ls, w=b["sozcuk"]: int(w in ls)).astype("int8")
    k = bilgi.get("konu")
    if k:
        from sklearn.feature_extraction.text import TfidfVectorizer
        vek = TfidfVectorizer(vocabulary=k["sozluk"], analyzer=lambda ls: ls)
        vek.fit([k["sozluk"]])
        vek.idf_ = np.asarray(k["idf"])
        X = vek.transform(sz)
        W = X @ np.asarray(k["bilesen"]).T
        W = np.asarray(W)
        konu = np.where(W.max(axis=1) > 0, W.argmax(axis=1) + 1, 0)
        out["%s_KONU" % kolon] = pd.Series(["K%d" % v if v else "Konu yok" for v in konu],
                                           index=x.index)
    return out


def metin_ogren_woe(sz, y, maske, min_satir):
    yb = (pd.to_numeric(y, errors="coerce") > 0).astype(int)
    gec = maske & pd.to_numeric(y, errors="coerce").notna()
    st, yt = sz[gec], yb[gec]
    kotu_t = int(yt.sum())
    iyi_t = int(len(yt)) - kotu_t
    if not kotu_t or not iyi_t:
        return {}
    ex = pd.DataFrame({"w": st, "y": yt}).explode("w").dropna(subset=["w"])
    g = ex.groupby("w")["y"].agg(["size", "sum"])
    g = g[g["size"] >= min_satir]
    pk = (g["sum"] + _LAPLACE) / (kotu_t + _LAPLACE * 2)
    pi = (g["size"] - g["sum"] + _LAPLACE) / (iyi_t + _LAPLACE * 2)
    return dict(np.log(pk / pi))


def metin_ozeti(bilgi):
    """Kayit metni: bayrak sozcukleri ve konular."""
    parca = []
    b = bilgi.get("bayrak") or []
    if b:
        parca.append("Hedefle ilişkili sözcükler: " + ", ".join(
            "%s (%%%s)" % (x["sozcuk"], ("%.1f" % (x["oran"] * 100)).replace(".", ",")) for x in b))
    k = bilgi.get("konu")
    if k:
        parca.append("Konular: " + "; ".join("K%d: %s" % (i + 1, a) for i, a in enumerate(k["adlar"])))
    elif bilgi.get("konu_notu"):
        parca.append(bilgi["konu_notu"])
    return " ".join(parca) or "Hedefle anlamlı ilişkili sözcük bulunmadı; yalnız sözcük sayısı ve skor üretildi."
