# -*- coding: utf-8 -*-
"""fe_agent/aciklama_duzen.py - KOLON KARTLARI (01.2.4.3).

NE YAPAR
  Her kolonun sozluk aciklamasi ANLAMI DEGISTIRILMEDEN duzeltilir:
  kisaltmalar ve donem acilir, yarim cumle tamamlanir, Turkce duzelir.
  Anlamin kaynagi sirasiyla: kullanicinin notu > aile notu (kardes kolonda
  yazilip aileye uygulanan not) > onayli parca anlamlari (donem bilgisi,
  onayli kisaltmalar, kullanicinin parca cevaplari) > orijinal aciklama.
  Belirsizlik SORU, ad / dagilim celiskisi NOT olarak doner; dil modeli
  aciklamayi tahminle degistirmez (istem: llm.SISTEM_ACIKLAMA_DUZEN).

KOD DENETIMI (denetle)
  Kullanici notundaki sayilar, anlam kartindaki sayilar, Turkce ve yarim
  cumle kodla denetlenir; tutmayan kolon bir kez "DUZELTILECEK" notuyla
  yeniden sorulur, kalan sorun kartta "Kontrol" olarak yazar. Orijinaldeki
  sayinin ve adin donem sayisinin aciklamada olmamasi da kartta yazar.

AILE AKTARIMI (dil modeli cagrisi yok)
  Adi yalniz donem parcalarinin sayisiyla ayrilan kolonlar bir ailedir.
  Ailenin bir kolonu duzenlenince, orijinal aciklamasi o kolonunkinin
  yalniz bu sayilari degistirilmis hali olan kardes ayni duzeltmeyi
  sayilari degistirilerek alir (birebir, kodla). Sartlar tutmazsa kardes
  dil modeline gider.

KAYIT: PROJE_HAFIZASI/<calisma>/ACIKLAMA_DUZENLEME.json
  notlar          {kolon: kullanicinin notu}
  parca_notlari   {PARCA: kullanicinin parca hakkindaki cevabi}
  soru_cevaplari  {kolon: {"soru", "cevap"}}: kolonun sorusuna kullanicinin
                  cevabi (notlar'a dil modeli icin soru ve cevap olarak
                  yazilir; burada kartta gostermek icin)
  aile_notlari    {aile: {"kolon", "not"}}
  sonuclar        {kolon: duzenleme sonucu + girdinin imzasi}
  onay            onaylanan son hal (AMP_SOZLUK ve onerilen sozluk buradan)
  yazilan         {kolon: [onceki, son]}: calisma kopyasina yazilanlar
                  (adima ya da oncesine donulunce geri alinir)
  kabul           {kolon: onaylanan aciklama}: kullanicinin satir onayi;
                  aciklama sonradan degisirse onay gecersiz olur
Girdi veri setine ve sozluge hicbir kosulda yazilmaz."""

import hashlib
import json
import re
import threading
import time
from collections import Counter, OrderedDict
from concurrent import futures

from fe_agent import llm as llm_mod
from fe_agent.akis_durum import _folder

DOSYA_AD = "ACIKLAMA_DUZENLEME.json"
PARCA = 8              # dil modeline tek cagrida giden kolon
PARALEL = 4            # ayni anda calisan cagri (arka plan)
KARDES_ADET = 3        # baglama giden kardes kolon
YAZMA_ARALIGI = 5.0    # sn: kayit dosyasi en cok bu siklikla yazilir
EN_UZUN = 280          # bunun uzerindeki aciklama kartta isaretlenir
IPTAL_YOKLAMA = 0.3    # sn: isci iptali bu aralikla yoklar

_KILIT = threading.RLock()
_DEPOLAR = {}          # klasor -> _Depo
_HAVUZ = futures.ThreadPoolExecutor(max_workers=PARALEL)
# Kullanicinin istedigi tek kolonluk yeniden kontrol arka plan dalgasini
# beklemez: ayri havuz.
_ONCELIK_HAVUZ = futures.ThreadPoolExecutor(max_workers=2)

_SAYI = re.compile(r"(?<!\d)\d+(?!\d)")
_KAYIT_ALANLARI = ("notlar", "parca_notlari", "aile_notlari", "sonuclar", "onay",
                   "yazilan", "kabul", "elle", "soru_cevaplari")
METIN_ALANLARI = ("aciklama", "karar", "soru", "ad_notu", "dagilim_notu", "denetim")


def _norm(metin):
    return re.sub(r"\s+", " ", str(metin or "")).strip()


def imza(*parcalar):
    ham = json.dumps(parcalar, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(ham.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# DEPO (calisma basina bir tane; bellekte + calisma klasorunde)
# ---------------------------------------------------------------------------
class _Depo(object):
    def __init__(self, klasor):
        self.klasor = klasor
        self.notlar = {}
        self.parca_notlari = {}
        self.soru_cevaplari = {}
        self.aile_notlari = {}
        self.sonuclar = {}
        self.onay = {}
        self.yazilan = {}
        self.kabul = {}             # kolon -> kullanicinin onayladigi aciklama (sade)
        self.elle = {}              # kolon -> True: notu kolonun son aciklamasi (dil modeli yazmaz)
        self.girdiler = {}          # kolon -> son girdi
        self.aileler = {}           # aile -> [kolon]
        self.son_imza = {}          # kolon -> son girdinin imzasi
        self.bekleyen = OrderedDict()
        self.ucusta = {}            # kolon -> islenen girdinin imzasi
        self.dalgada = set()        # ucustakilerden arka plan isinin aldiklari
        self.nesil = 0              # her iptalde artar; eski isci kendini bilir
        self.gec = {}               # iptalde yolda kalan kolon -> imza (sonucu gelecek)
        self.sira = {}              # kolon -> son degisikligin sirasi (yoklama farki)
        self.sayac = 0
        self.calisiyor = False
        self.iptal = False
        self.hata = ""
        self.basla = 0.0
        self.biten_is = 0
        self.son_yazma = 0.0

    def dokun(self, kolon):
        self.sayac += 1
        self.sira[kolon] = self.sayac


def _yol(klasor):
    return "/%s/%s" % (str(klasor).strip("/"), DOSYA_AD)


def depo(klasor):
    with _KILIT:
        d = _DEPOLAR.get(klasor)
        if d is None:
            d = _Depo(klasor)
            _yukle(d)
            _DEPOLAR[klasor] = d
        return d


def _yukle(d):
    try:
        with _folder().get_download_stream(_yol(d.klasor)) as akis:
            govde = json.loads(akis.read().decode("utf-8") or "{}")
    except Exception:
        return
    if not isinstance(govde, dict):
        return
    for alan in _KAYIT_ALANLARI:
        deger = govde.get(alan)
        if isinstance(deger, dict):
            setattr(d, alan, deger)


def kaydet(d, zorla=False):
    """Kayit dosyasini yazar (zorla degilse en cok YAZMA_ARALIGI'nda bir).
    Doner: hata metni ya da None."""
    with _KILIT:
        simdi = time.time()
        if not zorla and simdi - d.son_yazma < YAZMA_ARALIGI:
            return None
        d.son_yazma = simdi
        govde = json.dumps({a: getattr(d, a) for a in _KAYIT_ALANLARI},
                           ensure_ascii=False, sort_keys=True)
    try:
        _folder().upload_stream(_yol(d.klasor), govde.encode("utf-8"))
    except Exception as e:
        return "Açıklama düzenleme kaydı yazılamadı (%s)." % str(e)[:120]
    return None


# ---------------------------------------------------------------------------
# AD PARCALARI, AILE, SAYI ESLEMESI
# ---------------------------------------------------------------------------
def toklar(ad):
    from fe_agent import kisaltma_okuma
    return [kisaltma_okuma._ust(p) for p in kisaltma_okuma.parcalar(ad)]


def donem_konumlari(t, desenler=()):
    """Ad parcalarindan onayli donem kalibina uyanlarin sirasi. desenler:
    01.2.4.1'de onaylanan kaliplarin derlenmis desenleri; aralik kalibi
    (<P><NN>_<NN>) ve alt cizgiyle ayrilmis sayi ve tek harf (3_M, M_3)
    iki parcayi birlikte kapsar."""
    konum = set()
    for i, p in enumerate(t):
        if any(r.match(p) for r in desenler):
            konum.add(i)
        # Iki parcali deger: aralik (H00_06), M_3, 3_M ya da iki donem
        # parcasi (14D_28D, kalip <N>D_<N>D). Desenler tam eslesir; ikiliye
        # uyan kalip yoksa parcalar tek tek bakilir.
        if i + 1 < len(t) and any(r.match(p + "_" + t[i + 1]) for r in desenler):
            konum.update((i, i + 1))
    return konum


# DEGISIM TURU: duzenlenen aciklamanin orijinalden farki. "aynen": ayni;
# "yazim": yalniz buyuk / kucuk harf, noktalama ya da Turkce karakter
# (sozcukler ayni); "ek": yalniz sozcuk ekleri (bkz. degisim_turu);
# "degisen": sozcuk eklendi, cikti ya da degisti.
_TR_ASCII = str.maketrans("çğıöşüâîû", "cgiosuaiu")


def _sozcukler(metin, ascii_=False):
    """Kucuk harfli sozcukler. Sira sayisi ("3. ay") ayri sozcuktur
    ("3." -> "3_sira"): "3 ay" ile "3. ay" ayni sayilmaz."""
    m = str(metin or "").replace("I", "ı").replace("İ", "i").lower()
    m = re.sub(r"(\d+)\.(?=\s+[a-zçğıöşüâîû])", r"\1_sira", m)
    if ascii_:
        m = m.translate(_TR_ASCII)
    return re.findall(r"[0-9a-zçğıöşüâîû_]+", m)


# EK DEGISIMI: iki sozcugun ortak govdesi var ve govdeden sonra iki
# tarafta da yalniz bilinen ekler kaliyor ("günde" / "günlük": gün + de /
# lük; "adet" / "adedi": yumusama + i). Karsilastirma Turkce karaktersiz
# yazilisla; govde en az iki harf; ek zinciri en cok uc ek. Anlami
# degistiren ekler (-siz, -li) listede yok: "işlemsiz" ek degisimi sayilmaz.
_EKLER = frozenset({
    "i", "u", "e", "a", "yi", "yu", "ye", "ya", "ni", "nu", "de", "da", "te", "ta",
    "den", "dan", "ten", "tan", "in", "un", "nin", "nun", "yla", "yle", "la", "le",
    "ki", "lik", "luk", "si", "su", "ler", "lar", "n", "y"})
_YUMUSAMA = {"d": "t", "g": "k", "b": "p", "c": "c"}


def _ek_zinciri(m, kalan=3):
    if not m:
        return True
    if not kalan:
        return False
    return any(m.startswith(e) and _ek_zinciri(m[len(e):], kalan - 1) for e in _EKLER)


def _ayni_govde(a, b):
    if a == b:
        return True
    if a.isdigit() or b.isdigit():
        return False
    for k in range(min(len(a), len(b)), 1, -1):
        on_a, on_b = a[:k], b[:k]
        if on_a[:-1] != on_b[:-1]:
            continue
        son_a, son_b = on_a[-1], on_b[-1]
        if son_a != son_b and _YUMUSAMA.get(son_a, son_a) != _YUMUSAMA.get(son_b, son_b):
            continue
        if _ek_zinciri(a[k:]) and _ek_zinciri(b[k:]):
            return True
    return False


def degisim_turu(orijinal, aciklama):
    """"aynen" / "yazim" (yalniz harf, noktalama, Turkce karakter) / "ek"
    (sozcuklerin govdesi ve sirasi ayni, yalniz ekler farkli) / "degisen"."""
    if _norm(orijinal).rstrip(" .") == _norm(aciklama).rstrip(" ."):
        return "aynen"          # yalniz sona nokta eklendi ya da kalkti
    o, a = _sozcukler(orijinal, True), _sozcukler(aciklama, True)
    if o == a:
        return "yazim"
    if len(o) == len(a) and all(_ayni_govde(x, y) for x, y in zip(o, a)):
        return "ek"
    return "degisen"


def ek_acikta(ek, aciklama):
    """Ek bilginin butun sozcukleri aciklamada geciyor mu? (Gosterimde
    tekrar edilmez; veri ve 02'ye giden katalogda kalir.)"""
    e = _sozcukler(ek)
    return bool(e) and set(e) <= set(_sozcukler(aciklama))


def aile_kalibi(aciklamalar):
    """Ailenin aciklama kalibi: butun uyelerin aciklamasi sayilar "[sayı]"
    yapilinca ayniysa o metin; degilse en cok uyenin kalibi. Doner:
    (kalip, uyan sayisi)."""
    sayac = Counter(re.sub(r"\d+", "[sayı]", _norm(a)) for a in aciklamalar if _norm(a))
    if not sayac:
        return "", 0
    kalip, n = sayac.most_common(1)[0]
    return kalip, n


def aile_anahtari(ad):
    """Sayilari "#" yapilmis ad: ayni anahtarli kolonlar yalniz sayilarla
    ayrilir. Aktarim ayrica orijinal aciklamalarin ayni sayilarla
    ayrildigini dogrular (bkz. _aktarilabilir)."""
    return "_".join(re.sub(r"\d+", "#", p) for p in toklar(ad))


def donem_sayilari(ad, desenler=()):
    """Adin onayli donem parcalarindaki sayilar (tam sayi olarak)."""
    t = toklar(ad)
    return [int(x) for i in sorted(donem_konumlari(t, desenler))
            for x in _SAYI.findall(t[i])]


def sayi_haritasi(kaynak_ad, hedef_ad):
    """Ayni ailedeki iki kolonun donem sayilari: {kaynak_sayi: hedef_sayi}.
    Esleme tek anlamli degilse None."""
    a, b = toklar(kaynak_ad), toklar(hedef_ad)
    if len(a) != len(b):
        return None
    harita = {}
    for x, y in zip(a, b):
        if x == y:
            continue
        if re.sub(r"\d+", "#", x) != re.sub(r"\d+", "#", y):
            return None
        for p, q in zip(_SAYI.findall(x), _SAYI.findall(y)):
            if harita.get(p, q) != q:
                return None
            harita[p] = q
    harita = {k: v for k, v in harita.items() if k != v}
    if len(set(harita.values())) != len(harita):
        return None
    return harita


def sayilari_degistir(metin, harita):
    """Sayilari TEK GECISTE degistirir (3->7 ve 7->14 birbirini bozmaz)."""
    if not harita or not metin:
        return metin
    return _SAYI.sub(lambda m: harita.get(m.group(0), m.group(0)), str(metin))


def _aktarilabilir(kaynak, hedef):
    """Kaynak kolonun duzeltmesi hedefe sayilari degistirilerek aktarilabilir
    mi? Doner: sayi haritasi ya da None."""
    if kaynak.get("aile") != hedef.get("aile") or _norm(hedef.get("not")):
        return None
    harita = sayi_haritasi(kaynak["kolon"], hedef["kolon"])
    if harita is None:
        return None
    if _norm(sayilari_degistir(kaynak.get("orijinal"), harita)) != _norm(hedef.get("orijinal")):
        return None
    k_aile = kaynak.get("aile_notu") or {}
    h_aile = hedef.get("aile_notu") or {}
    if _norm(kaynak.get("not")):
        # Kaynagin kendi notu: yalniz kullanici bu notu aileye uyguladiysa.
        if h_aile.get("kolon") != kaynak["kolon"] or _norm(h_aile.get("not")) != _norm(kaynak["not"]):
            return None
    elif _norm(k_aile.get("not")) != _norm(h_aile.get("not")):
        return None
    if list(map(tuple, kaynak.get("parcalar_ozet") or [])) != \
            list(map(tuple, hedef.get("parcalar_ozet") or [])):
        return None
    return harita


def aktar(kaynak, sonuc, hedef):
    """Kaynagin sonucunu hedefe aktarir; olmuyorsa None."""
    harita = _aktarilabilir(kaynak, hedef)
    if harita is None or not sonuc or not sonuc.get("aciklama") or sonuc.get("kaynak") == "hata":
        return None
    yeni = {a: sayilari_degistir(sonuc.get(a) or "", harita) for a in METIN_ALANLARI}
    yeni["parca"] = sonuc.get("parca") or ""
    yeni["ad_eksik"] = [dict(o) for o in sonuc.get("ad_eksik") or []]
    yeni["ek"] = sayilari_degistir(sonuc.get("ek") or "", harita)
    yeni["model"] = sonuc.get("model") or ""
    yeni["kaynak"] = "aile"
    yeni["aile_kaynagi"] = kaynak["kolon"]
    kontrol, kalan = denetle(hedef, yeni)
    if kalan:
        return None
    yeni["kontrol"] = kontrol
    return yeni


# ---------------------------------------------------------------------------
# KOD DENETIMI
# ---------------------------------------------------------------------------
def _sayilar(metin):
    return [int(x) for x in _SAYI.findall(str(metin or ""))]


# SORU CEVABI: kolonun sorusuna verilen cevap dil modeline notla gider:
# "Sorduğun: ... Cevabım: ...". Sayi denetimi yalniz cevap kismina bakar
# (sorudaki sayilar aciklamada olmak zorunda degil).
CEVAP_IMI = "Cevabım:"


def soru_notu(soru, cevap):
    return "Sorduğun: %s %s %s" % (_norm(soru), CEVAP_IMI, _norm(cevap))


def _not_sayi_kismi(notu):
    n = _norm(notu)
    return n.split(CEVAP_IMI, 1)[1] if n.startswith("Sorduğun:") and CEVAP_IMI in n else n


DONEM_KONTROL_BASI = "Adın dönem sayısı açıklamada yok"


def donem_kontrolu(girdi, ack):
    """Adin donem sayilarindan aciklamada olmayanlar (kartta kontrol notu)."""
    var = set(_sayilar(ack))
    eksik = [x for x in dict.fromkeys(girdi.get("donem_sayilari") or []) if x not in var]
    return ["%s: %s." % (DONEM_KONTROL_BASI, ", ".join(map(str, eksik)))] if eksik else []


def guncel_kontrol(girdi, sonuc):
    """Sonucun kontrol notlari; donem sayisi notu guncel girdiyle yeniden
    hesaplanir (kural degisince eski sonuclar yeniden yazdirilmadan)."""
    k = [x for x in (sonuc or {}).get("kontrol") or [] if not str(x).startswith(DONEM_KONTROL_BASI)]
    return k + donem_kontrolu(girdi or {}, (sonuc or {}).get("aciklama") or "")


def denetle(girdi, sonuc):
    """Doner: (kontrol, yeniden). yeniden: dil modeline bir kez daha
    sorulacak sorunlar; kontrol: kartta yazacak bilgi notlari."""
    ack = sonuc.get("aciklama") or ""
    kontrol, yeniden = [], []
    if not ack:
        return kontrol, ["açıklama boş"]
    var = set(_sayilar(ack))
    notu = _norm(girdi.get("not"))
    if notu:
        eksik = [x for x in dict.fromkeys(_sayilar(_not_sayi_kismi(notu))) if x not in var]
        if eksik:
            yeniden.append("kullanıcı notundaki sayı açıklamada yok: %s"
                           % ", ".join(map(str, eksik)))
    else:
        eksik = [x for x in dict.fromkeys(_sayilar(girdi.get("orijinal"))) if x not in var]
        if eksik:
            kontrol.append("Orijinaldeki sayı açıklamada yok: %s." % ", ".join(map(str, eksik)))
    kontrol.extend(donem_kontrolu(girdi, ack))
    # KOLON KARTI kodla kurulur (onayli parcalardan); karttaki sayilar
    # aciklamada gecmeli.
    kart = girdi.get("kart") or {}
    eksik = [x for x in dict.fromkeys(s for v in kart.values() for s in _sayilar(v)) if x not in var]
    if eksik:
        yeniden.append("kolon kartındaki sayı açıklamada yok: %s" % ", ".join(map(str, eksik)))
    for s in llm_mod.aciklama_sorunlari(ack):
        if s.startswith("cümle yarım") or s.startswith("tahmin"):
            yeniden.append(s)
        elif not s.startswith("uzun"):
            kontrol.append(s[:1].upper() + s[1:] + ".")
    if len(ack) > EN_UZUN:
        kontrol.append("Uzun (%d karakter)." % len(ack))
    tr = llm_mod.turkce_sorunu(ack)
    if tr:
        yeniden.append(tr)
    return kontrol, yeniden


def _kontrol_metni(sorun):
    s = str(sorun or "").strip()
    return (s[:1].upper() + s[1:]).rstrip(".") + "."


# ---------------------------------------------------------------------------
# DIL MODELI
# ---------------------------------------------------------------------------
def _llm_girdisi(g, duzeltilecek=None):
    x = {k: g.get(k) for k in ("kolon", "orijinal", "not", "aile_notu", "parcalar", "kart",
                               "kardesler", "dagilim", "rol")}
    if duzeltilecek:
        x["duzeltilecek"] = list(duzeltilecek)
    return x


def _bicimle(g, ham):
    r = dict(ham)
    ack = llm_mod.aciklama_temizle(r.get("aciklama") or "")
    if ack:
        ack = llm_mod.tarza_uydur(ack, {"nokta": True, "buyuk_bas": True})
    r["aciklama"] = ack
    if not r.get("karar"):
        if _norm(g.get("not")):
            r["karar"] = "Notunuz işlendi."
        elif _norm(ack) == _norm(g.get("orijinal")):
            r["karar"] = "Aynen alındı."
        else:
            r["karar"] = "Netleştirildi."
    parca = str(r.get("parca") or "").strip().upper()
    gecerli = set(toklar(g["kolon"]))
    r["parca"] = parca if parca in gecerli else ""
    if not r.get("soru"):
        r["parca"] = ""
    # Ada eklenecek bilgi kartta zaten varsa atilir.
    kart_metni = " ".join(str(v or "") for v in (g.get("kart") or {}).values()).lower()
    r["ad_eksik"] = [o for o in llm_mod.ad_eksik_temizle(r.get("ad_eksik"))
                     if o["anlam"].lower() not in kart_metni]
    r["kaynak"] = "model"
    return r


def _denetim(girdiler, taslak, ork):
    """Ikinci ve ucuncu cagri: denetci taslaklari denetler; sorun buldugu
    kolonlarda karar cagrisi son aciklamayi yazar. taslak yerinde
    guncellenir; her sonuca "denetim" (kartta yazan kisa not) eklenir.
    Denetim ya da karar cevap veremezse taslak kalir ve not bunu yazar."""
    try:
        kon, kh = llm_mod.aciklama_kontrol([_llm_girdisi(g) for g in girdiler], taslak, ork)
    except Exception as e:
        kon, kh = {}, "%s: %s" % (type(e).__name__, str(e)[:200])
    sorunlu = []
    for g in girdiler:
        r = taslak.get(g["kolon"])
        if r is None:
            continue
        k = kon.get(g["kolon"])
        if not k:
            r["denetim"] = "Denetim yapılamadı; açıklama yalnız ilk düzenlemeden geçti."
        elif k["uygun"]:
            r["denetim"] = "Denetim: uygun bulundu."
        else:
            sorunlu.append(g)
    if not sorunlu:
        return
    try:
        son, _h = llm_mod.aciklama_karar([_llm_girdisi(g) for g in sorunlu], taslak,
                                         {g["kolon"]: kon[g["kolon"]] for g in sorunlu}, ork)
    except Exception:
        son = {}
    for g in sorunlu:
        k = kon[g["kolon"]]
        sorun = "; ".join(x.rstrip(".") for x in k["sorunlar"]) or "taslak uygun bulunmadı"
        r3 = son.get(g["kolon"])
        if r3 and r3.get("aciklama"):
            r3 = _bicimle(g, r3)
            r3["ilk_aciklama"] = taslak[g["kolon"]].get("aciklama") or ""
            r3["denetim"] = ("Denetim: %s. Son açıklama denetimle birlikte yazıldı." % sorun)
            taslak[g["kolon"]] = r3
        else:
            r = taslak[g["kolon"]]
            r["denetim"] = "Denetim: %s. Karar verilemedi; ilk düzenleme kaldı." % sorun
            r["_ek_kontrol"] = ["Denetçinin bulduğu sorun çözülmedi: %s." % sorun]


def _isle(girdiler, ork, durdu=None):
    """Bir grup kolonu uc cagriyla duzenletir: yazar taslagi yazar,
    denetci denetler, sorun bulunanlarda karar cagrisi son aciklamayi
    yazar (_denetim). Kod denetiminden gecmeyenler bir kez daha sorulur
    (is iptal edildiyse sonraki cagrilar yapilmaz). Doner: ({kolon:
    sonuc}, hata)."""
    try:
        ham, hata = llm_mod.aciklama_duzenle([_llm_girdisi(g) for g in girdiler], ork)
    except Exception as e:
        ham, hata = {}, "%s: %s" % (type(e).__name__, str(e)[:200])
    sonuc, yeniden, taslak = {}, [], {}
    for g in girdiler:
        r = ham.get(g["kolon"])
        if not r:
            if not hata:
                yeniden.append((g, None, ["dil modeli bu kolon için cevap vermedi"]))
            continue
        taslak[g["kolon"]] = _bicimle(g, r)
    if taslak and not (durdu and durdu()):
        _denetim([g for g in girdiler if g["kolon"] in taslak], taslak, ork)
    for g in girdiler:
        r = taslak.get(g["kolon"])
        if r is None:
            continue
        kontrol, yen = denetle(g, r)
        r["kontrol"] = kontrol + r.pop("_ek_kontrol", [])
        sonuc[g["kolon"]] = r
        if yen:
            yeniden.append((g, r, yen))
    if yeniden and not hata and not (durdu and durdu()):
        try:
            ham2, _h2 = llm_mod.aciklama_duzenle(
                [_llm_girdisi(g, yen) for g, _r, yen in yeniden], ork)
        except Exception:
            ham2 = {}
        for g, r1, yen1 in yeniden:
            r2 = ham2.get(g["kolon"])
            if r2:
                r2 = _bicimle(g, r2)
                if r1 is not None and r1.get("denetim"):
                    r2["denetim"] = r1["denetim"]
                k2, yen2 = denetle(g, r2)
                if r1 is None or len(yen2) <= len(yen1):
                    r2["kontrol"] = k2 + [_kontrol_metni(x) for x in yen2]
                    sonuc[g["kolon"]] = r2
                    continue
            if r1 is not None:
                r1["kontrol"] = r1["kontrol"] + [_kontrol_metni(x) for x in yen1]
    return sonuc, hata


def _hata_sonucu(hata):
    return {"aciklama": "", "karar": "", "ek": "", "soru": "", "parca": "",
            "ad_notu": "", "dagilim_notu": "", "kontrol": [], "model": "",
            "ad_eksik": [], "kaynak": "hata",
            "hata": hata or "Dil modeli bu kolon için açıklama döndürmedi."}


def _sakla(d, girdiler, sonuc, hata):
    with _KILIT:
        for g in girdiler:
            kolon = g["kolon"]
            if d.ucusta.get(kolon) == g["imza"]:
                d.ucusta.pop(kolon, None)
                d.dalgada.discard(kolon)
            if d.gec.get(kolon) == g["imza"]:
                d.gec.pop(kolon, None)
            r = sonuc.get(kolon) or _hata_sonucu(hata)
            r["imza"] = g["imza"]
            # Bu arada girdisi degisen kolonun eski sonucu yazilmaz. Iptalden
            # sonra gelen sonuc da yazilir (duzenlenen satir kalir); ayni
            # girdinin sonucu zaten varsa bitenler iki kez sayilmaz.
            if d.son_imza.get(kolon) == g["imza"]:
                onceki = d.sonuclar.get(kolon) or {}
                if onceki.get("imza") != g["imza"] or onceki.get("kaynak") == "hata":
                    d.biten_is += 1
                d.sonuclar[kolon] = r
                if d.bekleyen.get(kolon, {}).get("imza") == g["imza"]:
                    d.bekleyen.pop(kolon, None)
            d.dokun(kolon)
        if hata:
            d.hata = hata


# ---------------------------------------------------------------------------
# IS
# ---------------------------------------------------------------------------
def _kaynak_bul(d, g):
    """Ailede, bu kolona aktarilabilecek guncel bir sonuc."""
    adaylar = []
    for k2 in d.aileler.get(g.get("aile"), ()):
        if k2 == g["kolon"]:
            continue
        r = d.sonuclar.get(k2)
        g2 = d.girdiler.get(k2)
        if not r or not g2 or r.get("imza") != d.son_imza.get(k2):
            continue
        adaylar.append((r.get("kaynak") != "model", k2, g2, r))
    for _o, _k2, g2, r in sorted(adaylar, key=lambda x: (x[0], x[1])):
        yeni = aktar(g2, r, g)
        if yeni:
            return yeni
    return None


def _dalga_sec(d):
    """Kilit altinda. Once aile aktarimi; sonra dil modeline gidecekler.
    Aktarilmayi bekleyen kardes, ailesinden bu dalgada giden kolonla
    hizaliysa bekletilir. Doner: (giden girdiler, aktarilan sayisi)."""
    aktarilan = 0
    for kolon, g in list(d.bekleyen.items()):
        if kolon in d.ucusta or len(d.aileler.get(g.get("aile"), ())) < 2:
            continue
        yeni = _kaynak_bul(d, g)
        if yeni:
            yeni["imza"] = g["imza"]
            d.sonuclar[kolon] = yeni
            d.bekleyen.pop(kolon, None)
            d.biten_is += 1
            d.dokun(kolon)
            aktarilan += 1
    secilen, aile_giden = [], {}
    for kolon, g in d.bekleyen.items():
        if len(secilen) >= PARCA * PARALEL:
            break
        # Iptalde yolda kalan ayni girdinin cevabi gelecek: yeniden sorulmaz.
        if kolon in d.ucusta or d.gec.get(kolon) == g["imza"]:
            continue
        giden = aile_giden.get(g.get("aile")) or []
        if any(_aktarilabilir(x, g) is not None for x in giden):
            continue
        secilen.append(g)
        aile_giden.setdefault(g.get("aile"), []).append(g)
    return secilen, aktarilan


def _dalga_sonucu(d, grup, f):
    """Havuzdaki grubun sonucu (iptalden sonra gelse de saklanir; kuyrukta
    beklerken iptal edilen grup hic islenmez, satirlari zaten bekleyende)."""
    if f.cancelled():
        with _KILIT:
            for g in grup:
                if d.gec.get(g["kolon"]) == g["imza"]:
                    d.gec.pop(g["kolon"], None)
        return
    try:
        sonuc, hata = f.result()
    except Exception as e:
        sonuc, hata = {}, "%s: %s" % (type(e).__name__, str(e)[:200])
    _sakla(d, grup, sonuc, hata)


def _calis(d, nesil):
    ork = llm_mod.Orkestra(arka=True)

    def durdu():
        with _KILIT:
            return d.iptal or d.nesil != nesil
    try:
        while True:
            with _KILIT:
                if d.iptal or d.nesil != nesil or not d.bekleyen:
                    break
                dalga, aktarilan = _dalga_sec(d)
                for g in dalga:
                    d.bekleyen.pop(g["kolon"], None)
                    d.ucusta[g["kolon"]] = g["imza"]
                    d.dalgada.add(g["kolon"])
                    d.dokun(g["kolon"])
                if not dalga and not aktarilan:
                    # Hepsi baska yolda (oncelikli is) isleniyor.
                    bekle = True
                else:
                    bekle = False
            if bekle:
                time.sleep(1.0)
                continue
            if dalga:
                gruplar = [dalga[i:i + PARCA] for i in range(0, len(dalga), PARCA)]
                kalan = set()
                for grup in gruplar:
                    f = _HAVUZ.submit(_isle, grup, ork, durdu)
                    f.add_done_callback(lambda f, grup=grup: _dalga_sonucu(d, grup, f))
                    kalan.add(f)
                # Iptal edilince dalganin bitmesi beklenmez: kuyruktaki gruplar
                # iptal edilir, suren cagrilarin sonucu gelince saklanir.
                while kalan:
                    _bitti, kalan = futures.wait(kalan, timeout=IPTAL_YOKLAMA)
                    if kalan and durdu():
                        for f in kalan:
                            f.cancel()
                        break
            kaydet(d)
    except Exception as e:
        with _KILIT:
            d.hata = "%s: %s" % (type(e).__name__, str(e)[:200])
    finally:
        with _KILIT:
            if d.nesil == nesil:
                d.calisiyor = False
        kaydet(d, zorla=True)


def _tek_isle(d, g):
    """Kullanicinin istedigi yeniden kontrol (tek kolon, beklemeden). Bu
    sirada not yeniden degistiyse yeni girdi de hemen islenir."""
    try:
        sonuc, hata = _isle([g], llm_mod.Orkestra())
    except Exception as e:
        sonuc, hata = {}, "%s: %s" % (type(e).__name__, str(e)[:200])
    _sakla(d, [g], sonuc, hata)
    tekrar = None
    with _KILIT:
        g2 = d.bekleyen.get(g["kolon"])
        if g2 is not None and g["kolon"] not in d.ucusta:
            d.bekleyen.pop(g["kolon"], None)
            d.ucusta[g["kolon"]] = g2["imza"]
            d.dokun(g["kolon"])
            tekrar = g2
    if tekrar is not None:
        _ONCELIK_HAVUZ.submit(_tek_isle, d, tekrar)
        return
    kaydet(d, zorla=True)


def elle_sonuc(g, metin):
    """Kullanicinin duzenledigi aciklamanin sonucu: metin aynen (yalniz
    tarz: nokta, bas harf), kod denetimi notlari."""
    ack = llm_mod.tarza_uydur(llm_mod.aciklama_temizle(metin), {"nokta": True, "buyuk_bas": True})
    return {"imza": g["imza"], "aciklama": ack, "karar": "Sizin düzenlemeniz.", "ek": "",
            "soru": "", "parca": "", "ad_notu": "", "dagilim_notu": "", "model": "",
            "kaynak": "elle", "kontrol": llm_mod.aciklama_sorunlari(ack)}


def elle_yaz(klasor, kolon, metin):
    """Kolonun aciklamasini kullanici yazdi (bos: kaldirilir, dil modeli
    yeniden yazar). Doner: hata ya da None."""
    d = depo(klasor)
    metin = _norm(metin)
    with _KILIT:
        if metin:
            d.notlar[str(kolon)] = metin
            d.elle[str(kolon)] = True
        else:
            d.notlar.pop(str(kolon), None)
            d.elle.pop(str(kolon), None)
        d.dokun(str(kolon))
    return kaydet(d, zorla=True)


def aileye_elle_yaz(klasor, kolon, uygula=True):
    """Kolonun elle aciklamasi ailesindeki kolonlara sayilari degistirilerek
    yazilir (ya da geri alinir). Sayi eslemesi kurulamayan kolon atlanir.
    Doner: (yazilan kolon sayisi, atlanan kolonlar, hata)."""
    d = depo(klasor)
    with _KILIT:
        metin = d.notlar.get(kolon, "")
        g0 = d.girdiler.get(kolon) or {}
        aile = g0.get("aile")
        uyeler = [k for k in d.aileler.get(aile, []) if k != kolon]
        yazilan, atlanan = 0, []
        for k in uyeler:
            harita = sayi_haritasi(kolon, k)
            if harita is None:
                atlanan.append(k)
                continue
            uyarlanmis = sayilari_degistir(metin, harita)
            if uygula and metin:
                d.notlar[k] = uyarlanmis
                d.elle[k] = True
                yazilan += 1
            elif _norm(d.notlar.get(k)) == _norm(uyarlanmis):
                d.notlar.pop(k, None)
                d.elle.pop(k, None)
                yazilan += 1
            d.dokun(k)
        if uygula and metin:
            d.aile_notlari[str(aile)] = {"kolon": kolon, "not": metin, "elle": True}
        else:
            d.aile_notlari.pop(str(aile), None)
    return yazilan, atlanan, kaydet(d, zorla=True)


def girdileri_ver(klasor, girdiler, oncelikli=(), devam=True, hatalari_yenile=False):
    """Kolonlarin guncel girdileri. Sonucu guncel olmayanlar (girdisi
    degismis ya da hic islenmemis) kuyruga girer; oncelikli kolonlar
    beklemeden ayri islenir. devam=True: durdurulmus is yeniden baslar.
    Doner: kuyruga giren kolon sayisi."""
    d = depo(klasor)
    giren = 0
    with _KILIT:
        d.girdiler = {g["kolon"]: g for g in girdiler}
        aileler = {}
        for g in girdiler:
            aileler.setdefault(g.get("aile"), []).append(g["kolon"])
        d.aileler = aileler
        for g in girdiler:
            kolon = g["kolon"]
            d.son_imza[kolon] = g["imza"]
            # ELLE: kullanicinin duzenledigi aciklama aynen son metin; dil
            # modeline gitmez, kod denetimi yapilir.
            if d.elle.get(kolon) and _norm(d.notlar.get(kolon)):
                r = d.sonuclar.get(kolon)
                if not (r and r.get("imza") == g["imza"] and r.get("kaynak") == "elle"):
                    # Ada eklenecek bilgi dil modelinin son sonucundan kalir.
                    eski_eksik = (d.sonuclar.get(kolon) or {}).get("ad_eksik") or []
                    d.sonuclar[kolon] = elle_sonuc(g, d.notlar[kolon])
                    d.sonuclar[kolon]["ad_eksik"] = list(eski_eksik)
                    d.dokun(kolon)
                d.bekleyen.pop(kolon, None)
                continue
            r = d.sonuclar.get(kolon)
            guncel = bool(r) and r.get("imza") == g["imza"] \
                and not (hatalari_yenile and r.get("kaynak") == "hata")
            if guncel or d.ucusta.get(kolon) == g["imza"]:
                # Guncel ya da ayni girdiyle zaten isleniyor.
                d.bekleyen.pop(kolon, None)
                continue
            if d.bekleyen.get(kolon, {}).get("imza") != g["imza"]:
                d.bekleyen[kolon] = g
                d.dokun(kolon)
                giren += 1
        if devam:
            d.iptal = False
            d.hata = ""
        tek = []
        for kolon in oncelikli:
            g = d.bekleyen.get(kolon)
            if g is not None and kolon not in d.ucusta:
                d.bekleyen.pop(kolon)
                d.ucusta[kolon] = g["imza"]
                d.dokun(kolon)
                tek.append(g)
        if d.bekleyen and not d.calisiyor and not d.iptal:
            d.calisiyor = True
            d.basla = time.time()
            d.biten_is = 0
            threading.Thread(target=_calis, args=(d, d.nesil), daemon=True).start()
    for g in tek:
        _ONCELIK_HAVUZ.submit(_tek_isle, d, g)
    return giren


def iptal(klasor):
    """Isi hemen durdurur: arka plan isinin ucustaki satirlari bekleyene
    doner (durum hemen "durduruldu" olur), isci dalganin bitmesini
    beklemez. Suren cagrinin sonucu sonradan gelirse yine saklanir."""
    d = depo(klasor)
    with _KILIT:
        d.iptal = True
        d.nesil += 1
        d.calisiyor = False
        for kolon in sorted(d.dalgada, reverse=True):
            imza_ = d.ucusta.pop(kolon, None)
            g = d.girdiler.get(kolon)
            if g is not None and imza_ == g["imza"] == d.son_imza.get(kolon) \
                    and kolon not in d.bekleyen:
                d.bekleyen[kolon] = g
                d.bekleyen.move_to_end(kolon, last=False)
                d.gec[kolon] = imza_
            d.dokun(kolon)
        d.dalgada.clear()


def is_durumu(klasor):
    d = depo(klasor)
    with _KILIT:
        calisiyor = d.calisiyor or bool(d.ucusta)
        return {"calisiyor": calisiyor, "bekleyen": len(d.bekleyen),
                "ucusta": len(d.ucusta), "iptal": d.iptal, "hata": d.hata,
                "gelecek": len(d.gec),
                "biten": d.biten_is,
                "toplam": d.biten_is + len(d.bekleyen) + len(d.ucusta),
                "gecen": int(time.time() - d.basla) if calisiyor and d.basla else 0}


def satir_durumu(d, kolon):
    """"isleniyor" / "bekliyor" / "hazir" / "hata" / "yok" (kilit altinda)."""
    if kolon in d.ucusta:
        return "isleniyor"
    if kolon in d.bekleyen:
        return "bekliyor"
    r = d.sonuclar.get(kolon)
    if r and r.get("imza") == d.son_imza.get(kolon):
        return "hata" if r.get("kaynak") == "hata" else "hazir"
    return "yok"


def guncel_sonuc(d, kolon):
    """Kolonun guncel girdisine ait sonuc; yoksa None (kilit altinda)."""
    r = d.sonuclar.get(kolon)
    if r and r.get("imza") == d.son_imza.get(kolon) and r.get("kaynak") != "hata":
        return r
    return None


# ---------------------------------------------------------------------------
# KULLANICI GIRDILERI
# ---------------------------------------------------------------------------
def not_yaz(klasor, kolon, metin):
    d = depo(klasor)
    metin = _norm(metin)
    with _KILIT:
        if metin:
            d.notlar[str(kolon)] = metin
        else:
            d.notlar.pop(str(kolon), None)
        d.dokun(str(kolon))
    return kaydet(d, zorla=True)


def soru_cevabi_yaz(klasor, kolon, soru, cevap):
    """Kolonun sorusuna kullanicinin cevabi: dil modeline not olarak gider
    ve kolon yeniden yazilir (elle aciklama kalkar). Bos cevap kaldirir.
    Doner: hata ya da None."""
    d = depo(klasor)
    kolon, cevap = str(kolon), _norm(cevap)
    with _KILIT:
        if cevap:
            d.notlar[kolon] = soru_notu(soru, cevap)
            d.soru_cevaplari[kolon] = {"soru": _norm(soru), "cevap": cevap}
        else:
            if (d.soru_cevaplari.get(kolon) or {}).get("cevap"):
                d.notlar.pop(kolon, None)
            d.soru_cevaplari.pop(kolon, None)
        d.elle.pop(kolon, None)
        d.dokun(kolon)
    return kaydet(d, zorla=True)


def soru_cevabi(d, kolon):
    """Kartta gosterilecek cevap: not hala o cevapsa {"soru", "cevap"}."""
    x = d.soru_cevaplari.get(kolon) or {}
    if x.get("cevap") and not d.elle.get(kolon) \
            and _norm(d.notlar.get(kolon)) == soru_notu(x.get("soru"), x.get("cevap")):
        return dict(x)
    return None


def parca_notu_yaz(klasor, parca, cevap):
    d = depo(klasor)
    parca = str(parca or "").strip().upper()
    cevap = _norm(cevap)
    with _KILIT:
        if cevap:
            d.parca_notlari[parca] = cevap
        else:
            d.parca_notlari.pop(parca, None)
    return kaydet(d, zorla=True)


def aile_notu_yaz(klasor, aile, kolon, metin):
    d = depo(klasor)
    metin = _norm(metin)
    with _KILIT:
        if metin:
            d.aile_notlari[str(aile)] = {"kolon": str(kolon), "not": metin}
        else:
            d.aile_notlari.pop(str(aile), None)
    return kaydet(d, zorla=True)
