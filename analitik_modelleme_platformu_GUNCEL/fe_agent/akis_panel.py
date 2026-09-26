# -*- coding: utf-8 -*-
"""fe_agent/akis_panel.py - Ust serit ozeti ve Ozet sayfasi govdesi.

akis.py bolundu; bu dosya o bolumun aynisidir.
"""

import pandas as pd

from fe_agent import sfa as sfa_mod
from fe_agent import sozluk_calisma
from fe_agent.akis_metin import (
    BIRLESTIREN_MODLAR, MOD_ADLARI, SOZLUK_URETEN_MODLAR)
from fe_agent.akis_durum import (
    AMP_SOZLUK_ADI, AMP_VERI_ADI, BOLME_ALAN_ACIKLAMA, BOLME_ALAN_BASLIK,
    LINEAGE_ADI, SOZLUK_ADI, TRAIN_KULLANIMI_BASLIK, _ond, _sayi,
    BOLME_BOLUMLERI, BOLME_SATIRLARI,
    BOLME_SOZLUK, GAP_EN_COK, TEKRAR_EN_COK,
    bolme_ayarlari, bolme_etiket, bolme_kisitlari, bolme_ozeti,
    bolme_satir_degeri, bolme_secenek_listesi, bolme_uyarilari,
    KAT_EN_AZ, KAT_EN_COK, ORAN_EN_AZ, ORAN_EN_COK,
    test_donem_anahtari,
    test_donem_secenekleri,
)
from fe_agent.akis_kayit import ADIMLAR, adim_grubu, adim_sirasi, fazlar


# Sozluk YALNIZCA Mod C ve D'de platform tarafindan uretilir; A ve B'de
# kullanicinin hazir sozlugu secmesi beklenir (akis_metin'de tanimli).


def _baz_degisken_sayisi(bz, p):
    """Model adimlarinin kullandigi degisken sayisi.

    bz["kolon"] veri setinin kolon sayisidir (target/id/donem DAHIL);
    bz["kolonlar"] ise modele giren degiskenlerdir (bu uclu HARIC).
    Ust serit ile model ekrani ayni sayiyi gostermeli."""
    kolonlar = bz.get("kolonlar")
    if kolonlar is not None:
        return len(kolonlar)
    return bz.get("kolon") or p.get("kolon_baslangic", 0)


# ===========================================================================
# OZET VE DETAY
# ===========================================================================
# Degeri henuz uretilmemis alanin isareti. Arayuz bunu ∅ olarak cizer.
# ∅ kasitlidir: "bu veri HENUZ GELMEDI" demek. Bos birakmak ya da
# uydurma bir metin yazmak, gelmemis veriyle gelmis veriyi ayirt
# edilemez hale getirirdi. Ne bekledigi aciklama satirlarinda yazar.
BOS_DEGER = "-"


def _liste_adet(x):
    """Liste uzunlugu; liste degilse None. Eski oturumda bu alanlar
    metin olarak gelebiliyor ve len('ABC') sessizce 3 doner."""
    return len(x) if isinstance(x, (list, tuple, set)) else None


def _serit_veri_sozluk_karti(durum):
    """Uzerinde calisilan tablo VE sozlugu - TEK kart.

    Ikisi ayri kart tutacak kadar bilgi tasimiyordu: veri seti adi +
    boyutu, sozluk adi + kapsami. Birlesince kart sag paneldeki
    "VERİ & SÖZLÜK" sekmesiyle ayni adi tasiyor ve tiklayinca oraya
    gidiyor - tiklamanin nereye goturdugu etiketten anlasiliyor.

    Tiklama veri seti BAGLANDIKTAN sonra acilir; sozluk henuz yoksa da
    sekme veri tarafini gosterebiliyor. Sozluk Mod B/C'de LLM tarafindan
    uretilir, o yuzden bos hali moda gore farkli konusur."""
    p = durum.get("profil") or {}
    kolon = _tam(p.get("kolon_baslangic") or p.get("kolon"))
    satir = _tam(p.get("satir"))
    veri_ad = durum.get("veri_seti")
    sozluk_ad = durum.get("sozluk") or durum.get("sozluk_yedek")
    # SERIT DE AYNI KAYNAKTAN: tanim sayisi ve kapsam sag paneldeki
    # kartla ayni hesaptan geliyor (sozluk_kapsami). Eskiden serit
    # profildeki donmus degerleri okuyordu ve iki yuzey ayni anda iki
    # farkli kapsam gosterebiliyordu.
    _kolonlar, _tanimli, _tanimsiz = sozluk_kapsami(durum)
    tanim = len(_tanimli) if _kolonlar else _tam(p.get("sozluk_satir"))
    kapsam = (round(100.0 * len(_tanimli) / len(_kolonlar), 1)
              if _kolonlar else p.get("kapsam"))

    # --- alt satir: sozlugun durumu --------------------------------------
    if sozluk_ad:
        kaynak = sozluk_calisma.kaynak_etiketi(durum) or sozluk_ad
        alt = ("%s · %s tanım · %%%s kapsam"
               % (kaynak, _sayi(tanim), _ond(kapsam, 1))
               if tanim and kapsam is not None
               else ("%s · %s tanım" % (kaynak, _sayi(tanim)) if tanim
                     else str(kaynak)))
    elif durum.get("mod") in SOZLUK_URETEN_MODLAR:
        alt = "sözlük LLM tarafından üretilecek"
    else:
        alt = "sözlük seçilmedi"

    if not (veri_ad and kolon):
        return {"deger": BOS_DEGER, "bos": True,
                "ust": ("kaynak tablolardan oluşturulacak"
                        if durum.get("mod") in BIRLESTIREN_MODLAR
                        else "veri seti seçilmedi"),
                "alt": alt}

    return {"deger": "%s × %s" % (_sayi(satir or 0), _sayi(kolon)),
            "ust": veri_ad,
            "alt": alt,
            "hedef": "ozet",
            "ipucu": ("Veri setinin ve sözlüğün son hâlini görmek, "
                      "kategorileri düzenlemek için tıklayın.")}


def _uretim_kumeleri(durum):
    """kaynak -> uretilen adlar kumesi. Kaynak bilgisi yoksa bos."""
    harita = durum.get("uretilen_kaynak")
    if not isinstance(harita, dict):
        return {}
    kumeler = {}
    for anahtar in ("kural", "kesif"):
        adlar = harita.get(anahtar)
        if isinstance(adlar, (list, tuple, set)) and adlar:
            kumeler[anahtar] = set(adlar)
    return kumeler


def _eleme_noktalari(durum):
    """Elemenin iki noktasi, SIRASIYLA: [(ad, hayatta kalanlar kumesi)].

    Once kalite kontrolu, sonra aday set secimi. Hangi degiskenin
    NEREDE elendigini soyleyebilmek icin ikisi ayri ayri gerekiyor;
    tek bir "final" kumesi "nerede gitti" sorusunu cevaplamiyor."""
    noktalar = []
    gecti = (durum.get("kalite") or {}).get("gecti")
    if isinstance(gecti, (list, tuple, set)):
        noktalar.append(("kalite", set(gecti)))
    secilen = (durum.get("secim") or {}).get("secilen_liste")
    if isinstance(secilen, (list, tuple, set)):
        noktalar.append(("seçim", set(secilen)))
    return noktalar


# Gosterim sirasi ALFABETIK DEGIL, akisin sirasi: once kural tabanli
# uretim calisir, sonra AI kesfi. sorted() "kesif"i one aliyordu.
KAYNAK_SIRASI = ("kural", "kesif")
KAYNAK_ADI = {"kural": "kural", "kesif": "AI"}


def _kaynak_sirali(kumeler):
    return [(k, kumeler[k]) for k in KAYNAK_SIRASI if k in kumeler]


def _uretim_karti(durum):
    """YALNIZCA uretim: kural tabanli ve AI kac degisken uretti.

    Eleme bu kartta YOK. Akisin gercek sirasi once uretim, sonra eleme;
    ikisini tek kartta toplamak iki farkli adimi tek cumleye
    sikistiriyordu."""
    kumeler = _uretim_kumeleri(durum)
    uretilen = _liste_adet(durum.get("uretilen"))

    if not uretilen:
        return {"deger": BOS_DEGER, "bos": True,
                "ust": "kural tabanlı üretim + AI keşfi",
                "alt": "henüz değişken üretilmedi"}

    parcalar = ["%s %s" % (KAYNAK_ADI[k], _sayi(len(v)))
                for k, v in _kaynak_sirali(kumeler)]
    baz = _liste_adet((durum.get("baz") or {}).get("kolonlar"))
    return {
        "deger": _sayi(uretilen),
        "ust": " · ".join(parcalar) if parcalar else "kaynak kırılımı yok",
        "alt": ("baz setteki %s değişken üzerine üretildi" % _sayi(baz)
                if baz else "baz set üzerine üretildi"),
        "ipucu": ("Kural tabanlı üretim ve AI keşfi adımlarında toplam %s "
                  "yeni değişken üretildi. Eleme bu kartta değil, ELEME "
                  "kartında." % _sayi(uretilen)),
    }


def _kaynak_eleme_metni(kumeler, noktalar):
    """'kural 180→38 · AI 132→16' - kaynak basina uretilen ve KALAN."""
    if not kumeler or not noktalar:
        return None
    son_kume = noktalar[-1][1]
    return " · ".join(
        "%s %s→%s" % (KAYNAK_ADI[k], _sayi(len(v)), _sayi(len(v & son_kume)))
        for k, v in _kaynak_sirali(kumeler))


def _nerede_elendi(kumeler, noktalar):
    """'kalitede −122 · seçimde −112' - hangi adimda kac aday dustu."""
    if not noktalar:
        return None
    onceki = set().union(*kumeler.values()) if kumeler else None
    parcalar = []
    for ad, kalan in noktalar:
        if onceki is None:
            break
        dusen = len(onceki - kalan)
        parcalar.append("%sde −%s" % (ad, _sayi(dusen))
                        if ad == "kalite" else "%sde −%s" % (ad, _sayi(dusen)))
        onceki = onceki & kalan
    return " · ".join(parcalar) if parcalar else None


def _eleme_ipucu(kumeler, noktalar):
    """Uzerine gelince gorunen TAM dokum: kaynak x eleme noktasi."""
    if not kumeler or not noktalar:
        return None
    satirlar = []
    for k, v in _kaynak_sirali(kumeler):
        onceki, adimlar = set(v), []
        for ad, kalan in noktalar:
            dusen = len(onceki - kalan)
            onceki = onceki & kalan
            adimlar.append("%sde %s elendi" % (ad, _sayi(dusen)))
        satirlar.append("%s: %s üretildi, %s - geriye %s kaldı"
                        % (KAYNAK_ADI[k], _sayi(len(v)), ", ".join(adimlar),
                           _sayi(len(onceki))))
    return "  |  ".join(satirlar)


def _eleme_karti(durum):
    """BUTUN eleme hikayesi: featurelar nereden nereye geldi, NEREDE elendi.

    Iki koldan gelir ve tek hunide birlesir:
      ham kolonlar        -> profil -> SFA
      uretilen degiskenler -> kalite -> aday set secimi
    """
    p = durum.get("profil") or {}
    t = p.get("profil_teshis") or {}
    sfa = durum.get("sfa") or {}

    ham = _tam(p.get("kolon_baslangic") or p.get("kolon"))
    temiz = _liste_adet(t.get("temiz")) if t else None
    sfa_gecen = _tam(sfa.get("pass_adet"))
    uretilen = _liste_adet(durum.get("uretilen"))

    basamaklar = []
    if temiz is not None:
        basamaklar.append(("profil", temiz))
    if sfa_gecen is not None:
        basamaklar.append(("SFA", sfa_gecen))

    kumeler = _uretim_kumeleri(durum)
    noktalar = _eleme_noktalari(durum)
    kalite_gecen = _liste_adet((durum.get("kalite") or {}).get("gecti"))
    if kalite_gecen is not None:
        basamaklar.append(("kalite", kalite_gecen))
    secilen = (durum.get("secim") or {}).get("secilen")
    if secilen is not None:
        basamaklar.append(("final", _tam(secilen, 0)))

    if not basamaklar:
        # ADIM ADLARININ LISTESI DEGIL, KARTIN NE GOSTERECEGI.
        # "profil · SFA · kalite · seçim" dort adim adini yan yana
        # diziyordu; adimlar zaten sol paneldeki is akisinda duruyor ve
        # bu satir kartin dolu halinde ne yazacagini hic anlatmiyordu.
        # Kart doldugunda huniyi gosteriyor: kac degisken girdi, kac
        # tanesi kaldi, hangi adimda dustu. Bos hal de onu soylesin.
        return {"deger": BOS_DEGER, "bos": True,
                "ust": "kaç değişken, nerede elendi",
                "alt": "üretim bittikten sonra eleme adımları başlar"}

    # Uretilenler ANCAK bir elemeye girdikten sonra huni girisine sayilir;
    # aksi halde hic elenmemisken "1.354 → 61" yazip 312 uretilmis
    # degiskenin elendigi izlenimi veriyordu.
    giris = (ham or 0) + ((uretilen or 0) if noktalar else 0)
    cikis = basamaklar[-1][1]

    kaynak_metni = _kaynak_eleme_metni(kumeler, noktalar)
    nerede = _nerede_elendi(kumeler, noktalar)

    return {
        "deger": "%s → %s" % (_sayi(giris), _sayi(cikis)),
        # Ust satir: kaynak basina uretilen -> kalan. Kaynak bilgisi
        # yoksa (eski oturum) ham kolon basamaklari yazilir.
        "ust": kaynak_metni or " · ".join(
            "%s %s" % (ad, _sayi(n)) for ad, n in basamaklar),
        # Alt satir: eleme NEREDE oldu.
        "alt": nerede or ("%s aday elendi" % _sayi(max(giris - cikis, 0))),
        "ipucu": _eleme_ipucu(kumeler, noktalar) or (
            "Basamaklar: " + " · ".join("%s %s" % (ad, _sayi(n))
                                        for ad, n in basamaklar)),
    }


# Ust seritte gosterilecek model metrikleri: (durum anahtari, etiket, basamak)
MODEL_METRIKLERI = (("gini_test", "Gini test", 3),
                    ("gini_oot", "Gini test (zamansal)", 3),
                    ("ks_test", "KS", 3),
                    ("gini_egitim", "Gini eğitim", 3))


def _model_karti(durum):
    """Modelin SONUCU: aday set buyuklugu ve olculen basari."""
    sc = durum.get("secim") or {}
    md = durum.get("model") or {}
    metrik = md.get("metrikler") or {}
    val = (durum.get("validasyon") or {}).get("metrikler") or {}
    metrik = {**metrik, **val}

    secilen = sc.get("secilen")
    if secilen is None:
        secilen = _liste_adet((durum.get("baz") or {}).get("kolonlar"))

    bulunan = [(etiket, _ond(metrik[a], b))
               for a, etiket, b in MODEL_METRIKLERI if metrik.get(a) is not None]

    if secilen is None and not bulunan:
        # "VALIDASYON" DEGIL "TEST".
        # Validasyon seti her calismada OLMAYABILIR: train/val ayrimi
        # yerine capraz dogrulama (CV) secilebiliyor ve o zaman ayri bir
        # val seti kurulmuyor. TEST seti ise her bolme turunde var
        # (zamansal ya da rastgele). Kartin basligi her zaman dogru olan
        # sey olmali.
        return {"deger": BOS_DEGER, "bos": True,
                "ust": "eğitim + test",
                "alt": "Gini ve KS sonuçları burada görünür"}

    if bulunan:
        return {"deger": "%s %s" % (bulunan[0][0], bulunan[0][1]),
                "ust": (" · ".join("%s %s" % x for x in bulunan[1:3])
                        or "%s değişkenli model" % _sayi(_tam(secilen, 0))),
                "alt": ("%s aday değişken" % _sayi(_tam(secilen, 0))
                        if secilen is not None else "")}

    delta = (md.get("delta") or {}).get("auc")
    return {"deger": "%s değişken" % _sayi(_tam(secilen, 0)),
            "ust": "aday değişken seti",
            "alt": ("Δ AUC %s" % _ond(delta, 4)) if delta is not None
                   else "model henüz eğitilmedi"}


def ozet(durum):
    """Ust serit: ÜRETİM · ELEME · MODEL.

    BICIM eskisiyle ayni: kirmizi etiket, koyu deger, iki gri alt satir.

    VERİ & SÖZLÜK KARTI KALDIRILDI. Serit, dar bir kutuda uc satira
    sigdirilmis ozet demek; veri seti adi, boyut, sozluk adi, tanim
    sayisi ve kapsam yuzdesi o kutuya sigmiyordu ve kirpilip
    okunamaz hale geliyordu. Ayni bilgi sag paneldeki VERİ & SÖZLÜK
    sekmesinde TAM ve detayli duruyor; serit artik yalnizca oradan
    okunamayan seyi, yani akisin ILERLEYISINI gosteriyor.
    `_serit_veri_sozluk_karti` SILINMEDI: sekmeye tiklanabilir kart
    dondurmek gerekirse yeri hazir.

    BOS HAL: deger ∅ ("bu veri henüz gelmedi"), aciklama satirlari o
    adimda ne yapilacagini yazar. Boylece ∅ tek basina bir bosluk degil,
    bekleyen bir adim anlatiyor."""
    return {
        # Secilmediyse cip cizilmez; None'i uc katmani bekliyor.
        "veri_seti_cip": durum.get("veri_seti") or None,
        "sozluk_cip": (durum.get("sozluk") or durum.get("sozluk_yedek")
                       or None),
        # SIRA AKISIN GERCEK SIRASI: degisken URETILIR, sonra ELENIR,
        # sonunda MODEL kurulur.
        "kartlar": [
            {"etiket": "ÜRETİM SONUÇLARI", **_uretim_karti(durum)},
            {"etiket": "ELEME SONUÇLARI", **_eleme_karti(durum)},
            {"etiket": "MODEL SONUÇLARI", **_model_karti(durum)},
        ],
    }


def _bolum(baslik, satirlar):
    return {"baslik": baslik, "satirlar": [s for s in satirlar if s]}

def detay(durum):
    m, p = durum.get("meta") or {}, durum.get("profil") or {}
    s, st = durum.get("sfa") or {}, durum.get("stabilite") or {}
    k, sc = durum.get("kalite") or {}, durum.get("secim") or {}
    md, bz = durum.get("model") or {}, durum.get("baz") or {}
    kt, b = durum.get("katalog") or {}, durum.get("bolme") or {}
    bl = durum.get("birlestirme") or {}
    t = p.get("profil_teshis") or {}

    bolumler = []

    if durum.get("mod"):
        # Etiketler TEK kaynaktan (MOD_SECENEKLERI -> MOD_ADLARI) turetilir.
        # Burada ikinci bir sozluk tutulunca A ile C ters eslesmisti.
        ad = MOD_ADLARI.get(durum["mod"], durum["mod"])
        bolumler.append(_bolum("ÇALIŞMA BAŞLANGICI",
                               [("Başlangıç", "%s - %s" % (durum["mod"], ad))]))

    if bl.get("ozet"):
        o = bl["ozet"]
        bolumler.append(_bolum("BİRLEŞTİRME", [
            ("İskelet tablo", o.get("ana_tablo")),
            ("Anahtar", " + ".join(o.get("anahtar") or [])),
            ("Dönem kolonu", o.get("donem_kolon") or "-"),
            ("Kaynak tablo", _sayi(o.get("kaynak_sayisi", 0))),
            ("Eklenen kolon", _sayi(o.get("eklenen_kolon", 0))),
            ("Point-in-time", _sayi(o.get("pit_kolon", 0))),
            ("Soy kütüğü", bl.get("lineage") or LINEAGE_ADI),
        ]))

    if durum.get("sozluk_uretim"):
        o = durum["sozluk_uretim"]
        bolumler.append(_bolum("SÖZLÜK ÜRETİMİ", [
            ("Toplam kolon", _sayi(o.get("toplam", 0))),
            ("Açıklanan", "%s  (%%%s)" % (_sayi(o.get("aciklamali", 0)),
                                          _ond(o.get("kapsam", 0)))),
            ("Dataset", SOZLUK_ADI),
        ]))

    if p.get("kolon"):
        bolumler.append(_bolum("KAYNAK VERİ", [
            ("Veri seti", durum.get("veri_seti")),
            ("Satır", _sayi(p["satir"])),
            ("Kolon", _sayi(p["kolon_baslangic"])),
            ("Sayısal / kategorik", "%s / %s" % (
                _sayi(p.get("sayisal", 0)),
                _sayi(p["kolon_baslangic"] - p.get("sayisal", 0)))),
            ("Sözlük", durum.get("sozluk") or durum.get("sozluk_yedek")),
        ]))

    if m.get("target"):
        bolumler.append(_bolum("MODELLEME TANIMLARI", [
            ("Hedef", m.get("target")),
            ("Hedef tipi", p.get("hedef_ozet")),
            ("Kimlik kolonu", m.get("id")),
            ("Dönem kolonu", m.get("donem") or "belirtilmedi"),
        ]))

    if b.get("tur"):
        bolumler.append(_bolum("BÖLME STRATEJİSİ", [
            ("Tür", "zamansal" if b["tur"] == "zamansal" else "rastgele"),
            ("Test dönemi", b.get("oot_deger") or "-"),
            ("Geliştirme satır", _sayi(b.get("train_satir", 0))),
            ("Test satır", _sayi(b.get("test_satir", 0))),
            ("Rastgelelik tohumu", b.get("seed", "-")),
        ]))

    if t:
        bolumler.append(_bolum("VERİ PROFİLİ", [
            ("Sorunsuz kolon", _sayi(len(t.get("temiz") or []))),
            ("Eksik oranı yüksek", _sayi(len(t.get("cok_bos") or []))),
            ("Sabit", _sayi(len(t.get("sabit") or []))),
            ("Kimlik benzeri", _sayi(len(t.get("kimlik_gibi") or []))),
            ("Kardinalite yüksek", _sayi(len(t.get("yuksek_kardinalite") or []))),
        ]))

    if s.get("analiz_edilen") is not None:
        bolumler.append(_bolum("TEK DEĞİŞKEN ANALİZİ", [
            ("Analiz edilen", _sayi(s["analiz_edilen"])),
            ("PASS", _sayi(s.get("pass_adet", 0))),
            ("Sızıntı şüpheli", _sayi(len(s.get("sizinti") or []))),
        ]))

    if st and not st.get("atlandi"):
        bolumler.append(_bolum("STABİLİTE (PSI)", [
            ("Ölçülen", _sayi(st.get("olculen", 0))),
            ("Kararlı", _sayi(st.get("stabil", 0))),
            ("Kayma gösteren", _sayi(len(st.get("kayan") or []))),
        ]))

    if bz.get("dataset"):
        bolumler.append(_bolum("ANALİTİK BAZ SET", [
            ("Dataset", bz["dataset"]),
            ("Kolon", "%s  →  %s" % (_sayi(p.get("kolon_baslangic", 0)),
                                     _sayi(bz["kolon"]))),
            ("Doldurma", bz.get("doldurma")),
        ]))

    uretilen = len(durum.get("uretilen") or [])
    if uretilen:
        blok = {x[0]: len(x[1]) for x in (durum.get("kod_bloklari") or [])}
        bolumler.append(_bolum("DEĞİŞKEN ÜRETİMİ", [
            ("Toplam üretilen", _sayi(uretilen)),
        ] + [(ad, _sayi(n)) for ad, n in blok.items()]))

    if k:
        bolumler.append(_bolum("KALİTE KONTROLÜ", [
            ("Geçen", _sayi(len(k.get("gecti") or []))),
            ("Elenen", _sayi(uretilen - len(k.get("gecti") or []))),
        ]))

    if sc.get("secilen") is not None:
        bolumler.append(_bolum("ADAY DEĞİŞKEN SETİ", [
            ("Aday", _sayi(sc.get("aday", 0))),
            ("Seçilen", _sayi(sc["secilen"])),
            ("Önem yöntemi", sc.get("onem_yontemi")),
        ]))

    if md and not md.get("hata"):
        bb, e, d = md.get("baseline", {}), md.get("enhanced", {}), md.get("delta", {})
        ds, ga = md.get("delta_std") or {}, md.get("delta_guven_araligi") or {}

        satirlar, gurultulu = [], []
        for etiket, anahtar in (("ROC-AUC", "auc"), ("Gini", "gini"), ("KS", "ks")):
            if bb.get(anahtar) is None and e.get(anahtar) is None:
                continue
            satir = "%s → %s   Δ %s" % (_ond(bb.get(anahtar), 4),
                                        _ond(e.get(anahtar), 4),
                                        _ond(d.get(anahtar), 4))
            if ds.get(anahtar) is not None:
                satir += " ± %s (std)" % _ond(ds[anahtar], 4)
            aralik = ga.get(anahtar)
            if aralik and len(aralik) == 2 and None not in aralik:
                satir += "   %%95 GA [%s ; %s]" % (_ond(aralik[0], 4),
                                                   _ond(aralik[1], 4))
                if float(aralik[0]) <= 0.0 <= float(aralik[1]):
                    gurultulu.append(etiket)
            satirlar.append((etiket, satir))

        if md.get("tekrar"):
            satirlar.append(("Tekrar", "%s farklı rastgelelik tohumu ile ölçüldü"
                             % _sayi(md["tekrar"])))
        if md.get("hedef_nan_dusen"):
            satirlar.append(("Hedefi boş olan satır",
                             "%s satır ölçüm dışı bırakıldı"
                             % _sayi(md["hedef_nan_dusen"])))

        # ONCE karsilastirma yapildi mi: yeni kolon yoksa iki model aynidir,
        # delta mekanik olarak sifirdir ve guven araligi [0,0] cikar. Bunu
        # gurultu yorumuna sokmak hic yapilmamis bir olcum hakkinda
        # istatistiksel hukum kurmak olurdu.
        if not md.get("karsilastirilabilir", True):
            satirlar.append(("Yorum", md.get("karsilastirma_notu")
                             or "Karşılaştırma yapılamadı."))
        # Guven araligi sifiri iceriyorsa katki gurultuden ayirt EDILEMEZ;
        # bunu ortu bas etmeden yaziyoruz.
        elif gurultulu:
            satirlar.append((
                "Yorum",
                "%s için %%95 güven aralığı sıfırı içeriyor: yeni "
                "değişkenlerin katkısı gürültüden ayırt edilemiyor."
                % " ve ".join(gurultulu)))
        elif ga:
            satirlar.append((
                "Yorum",
                "Güven aralıklarının hiçbiri sıfırı içermiyor: ölçülen "
                "katkı rastgelelik tohumu değişiminden ayırt edilebiliyor."))

        bolumler.append(_bolum("MODEL KARŞILAŞTIRMASI", satirlar))

    if kt.get("satir"):
        bolumler.append(_bolum("DEĞİŞKEN KATALOĞU", [
            ("Kayıt", _sayi(kt["satir"])),
            ("Seçili", _sayi(kt.get("secilen", 0))),
        ]))

    if not bolumler:
        bolumler = [_bolum("DURUM", [("Bilgi", "Henüz bir adım tamamlanmadı.")])]

    sira = adim_sirasi(durum.get("mod"))
    return {"bolumler": bolumler,
            "adim": ADIMLAR[sira[durum["i"]]]["baslik"],
            "adim_no": durum["i"] + 1,
            "toplam": len(sira)}


# ===========================================================================
# ANALIZ MERKEZI SEKMELERI
# ---------------------------------------------------------------------------
# validasyon.panel(durum) ile AYNI kalip: durumdan okur, ekranin cizecegi
# JSON'u doner. Hicbiri veri OKUMAZ / HESAPLAMAZ; gosterilen her sayi ilgili
# plan/uygula adiminda zaten hesaplanip durum'a yazilmistir.
#
# Ortak govde:
#   {"durum": "hazir" | "bekliyor",
#    "bekleme_notu": "...",            # yalnizca bekliyor
#    "kartlar": [{"baslik", "not", "satirlar": [{"etiket", "deger"}]}],
#    "tablo":   {"baslik", "kolonlar", "satirlar", "toplam", "gosterilen"}}
#
# Satir degeri None ise ekranda ∅ cikar; kartin "not" alani o satirin hangi
# adimdan sonra dolacagini soyler.
# ===========================================================================

# Panelde gosterilen tablo satiri sayisi (durum'da saklanan ilk N ile ayni).
PANEL_SATIR = 20


def _yuzde(x, b=1):
    """0.0473 -> '%4,7'. None -> None (ekranda ∅)."""
    if x is None:
        return None
    try:
        return "%" + _ond(100.0 * float(x), b)
    except Exception:
        return None


def _yuzde_dogrudan(x, b=2):
    """Zaten yuzde olarak saklanmis deger: 3.21 -> '%3,21'."""
    if x is None:
        return None
    try:
        return "%" + _ond(float(x), b)
    except Exception:
        return None


# --------------------------------------------------------------------------
# BASLIK BUYUK HARFI  -  kart basliklari ve satir etiketleri
# --------------------------------------------------------------------------
# Kullanici karari: "bu yazılarda kelimelerin ilk harfi büyük olacak".
# YALNIZCA ETIKETLER: kart notu ("Boş satırlar … adımından sonra dolar.")
# ve adim aciklamalari CUMLEDIR, onlara dokunulmaz - kullanici bunu
# ayrica soyledi ("Analiz edilecek veri setini de değişken sözlüğünü
# seçin. yazısı zaten olması gerektiği gibi").
#
# Turkce'de baglaclar kucuk kalir; ayrica kisaltmalar ve BUYUK yazilmis
# tablo adlari (MODELLEME_BAZ) oldugu gibi birakilir - str.title() onlari
# "Modelleme_Baz" yapardi.
KUCUK_KALAN = {"ve", "ile", "veya", "ya", "de", "da", "mi", "mı"}


def baslik_bicimi(metin):
    """Her kelimenin ilk harfi buyuk; baglaclar kucuk, BUYUK yazilmis
    sozcukler ve sayilar oldugu gibi."""
    if not metin:
        return metin
    kelimeler = str(metin).split(" ")
    cikti = []
    for i, k in enumerate(kelimeler):
        if not k:
            cikti.append(k)
            continue
        cekirdek = k.strip("()«»,.:;")
        # Zaten BUYUK yazilmis (kisaltma / tablo adi) ya da harf icermiyor
        if cekirdek and (cekirdek.upper() == cekirdek or not cekirdek.isalpha()):
            cikti.append(k)
            continue
        if i and cekirdek.lower() in KUCUK_KALAN:
            cikti.append(k.lower())
            continue
        # Turkce'ye duyarli buyutme: i -> İ
        bas = k[0].replace("i", "İ").upper()
        cikti.append(bas + k[1:])
    return " ".join(cikti)


def _kart(baslik, tanimlar):
    """tanimlar: [(etiket, deger, "dolduran adim")]

    Degeri olmayan satirlar ∅ kalir ve kart notu hangi adimdan sonra
    dolacaklarini yazar. Adim adi None ise o satir icin not uretilmez.

    BASLIK ve ETIKETLER tek yerde Baslik Buyuk Harfine cevriliyor: her
    kartta tek tek yazmak, ilerideki bir kartin sessizce kuralin disinda
    kalmasi demekti."""
    baslik = baslik_bicimi(baslik)
    satirlar, bekleyen = [], []
    for etiket, deger, adim in tanimlar:
        satirlar.append({"etiket": baslik_bicimi(etiket), "deger": deger})
        if deger in (None, "") and adim and adim not in bekleyen:
            bekleyen.append(adim)

    kart = {"baslik": baslik, "satirlar": satirlar}
    if bekleyen:
        # Kartta satir sirasi akis sirasi degil (Mod C'de "Kayıt yeri"
        # satiri "Hedef değişken"den once geliyor); not AKIS SIRASIYLA.
        bekleyen.sort(key=_akis_sirasi)
        kart["not"] = "Boş satırlar %s %s sonra dolar." % (
            _ad_listesi(bekleyen),
            "adımından" if len(bekleyen) == 1 else "adımlarından")
    return kart


def _ad_listesi(adlar):
    """«A» / «A» ve «B» / «A», «B» ve «C».

    Eskiden hepsi " ve " ile baglaniyordu: dort bekleyen adimda cumle
    "«A» ve «B» ve «C» ve «D»" cikiyordu. Turkcede son ikisi "ve" ile,
    oncekiler virgulle baglanir."""
    tirnakli = ["«%s»" % a for a in adlar]
    if len(tirnakli) <= 1:
        return "".join(tirnakli)
    return "%s ve %s" % (", ".join(tirnakli[:-1]), tirnakli[-1])


def _bekleyen_panel(adim, kartlar=None):
    veri = {"durum": "bekliyor",
            "bekleme_notu": "Bu sekme «%s» adımından sonra dolar." % adim,
            "kartlar": kartlar or []}
    return veri


# --------------------------------------------------------------------------
# VERI sekmesi  (app.js'te data-tab="ozet")
# --------------------------------------------------------------------------
# ADIM ADLARI SOL PANELDEN OKUNUR.
# Kart notu "Boş satırlar «X» adımından sonra dolar" diyor; X sol
# paneldeki is akisinda AYNEN bulunmali. Eskiden burada dort ad elle
# yaziliydi ("Veri Seti", "Veri ve Sözlük", "Modelleme Tanımları") ve
# sol panel o adimlari "Veri ve Model Tanımları" adli TEK satirda
# gosterdigi icin kullaniciya listede olmayan adimlar soyleniyordu.
# Artik ad, adim anahtarindan sol panelin kurallariyla (gruplu adim ->
# grup adi) uretiliyor; biri degisince oteki de degisir.
def sol_panel_adi(anahtar):
    """Adimin sol paneldeki is akisinda gorunen adi.

    Gruplu adimlar (kurulum, veri_sec, sozluk_uret, tanimlar,
    sozluk_tanim) sol panelde grubun adiyla TEK satirdir; app.js
    fazlariCiz ayni kurali uyguluyor."""
    _grup, grup_baslik = adim_grubu(anahtar)
    if grup_baslik:
        return grup_baslik
    return (ADIMLAR.get(anahtar) or {}).get("baslik") or anahtar


# Veri setini hangi adim getiriyor - moda gore. B ve D'de tablo
# birlestirme planindan uretiliyor; A ve C'de gruplu adimda seciliyor.
VERI_ADIMI_ANAHTARI = {"A": "kurulum", "B": "birlestirme",
                       "C": "veri_sec", "D": "birlestirme"}
# Sozlugu hangi adim getiriyor: A'da kurulumda, B'de ayri adimda hazir
# sozluk secilir; C ve D'de veriden uretilir.
SOZLUK_ADIMI_ANAHTARI = {"A": "kurulum", "B": "sozluk_sec",
                         "C": "sozluk_uret", "D": "sozluk_uret"}


def _veri_adimi(durum):
    return sol_panel_adi(VERI_ADIMI_ANAHTARI.get(
        (durum or {}).get("mod"), "kurulum"))


def _sozluk_adimi(durum):
    return sol_panel_adi(SOZLUK_ADIMI_ANAHTARI.get(
        (durum or {}).get("mod"), "kurulum"))


TANIM_ADIMI = sol_panel_adi("tanimlar")
# AMP_VERISETI / AMP_SOZLUK teyit "Kaydet ve Devam Et" ile yaziliyor
# (bkz. akis_faz01.teyit_uygula); "Kayıt yeri" satiri o adimdan sonra dolar.
KAYIT_ADIMI = sol_panel_adi("teyit")
PROFIL_ADIMI = sol_panel_adi("veri_profili")
SFA_ADIMI = sol_panel_adi("sfa")
BOLME_ADIMI = sol_panel_adi("bolme")

# Sol paneldeki adlarin akis sirasi, uc modun birlesimi. Faz 01'de
# modlar farkli adim tasiyor ama ortak adimlarin sirasi aynı.
_AKIS_ADLARI = []
for _a in (["mod", "ham_veri", "birlestirme", "kurulum", "veri_sec",
            "sozluk_sec", "sozluk_uret", "tanimlar", "sozluk_tanim",
            "teyit", "bolme"]
           + [a for a in adim_sirasi(None) if a != "mod"]):
    if sol_panel_adi(_a) not in _AKIS_ADLARI:
        _AKIS_ADLARI.append(sol_panel_adi(_a))
del _a


def _akis_sirasi(ad):
    """Adin sol paneldeki sirasi; listede yoksa en sona."""
    try:
        return _AKIS_ADLARI.index(ad)
    except ValueError:
        return len(_AKIS_ADLARI)


def _tam(x, yedek=None):
    """Sayiya cevrilemeyen degeri PATLAMADAN yedek'e dusurur.

    durum JSON'dan okunur; eski bir oturum dosyasinda ya da elle
    duzeltilmis bir kayitta sayisal alan metin gelebilir. Panelin
    tamami .get() ile korunmusken burada ham int() kalmisti; tek bir
    bozuk alan butun VERI sekmesini dusuruyordu."""
    if x is None:
        return yedek
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return yedek


def _oran(pay, payda):
    """pay/payda - payda 0, None ya da metin ise None."""
    p, b = _tam(pay), _tam(payda)
    if p is None or not b:
        return None
    return p / float(b)


def _tip_dagilimi(p):
    """'812 / 218 / 12' - sayisal / kategorik / tarih.

    Tarih kolonlari eskiden kategorige sayiliyordu; kategorik artik
    kolon - sayisal - tarih olarak hesaplanir."""
    kolon = _tam(p.get("kolon_baslangic") or p.get("kolon"))
    if not kolon:
        return None
    sayisal = _tam(p.get("sayisal"), 0)
    tarih = _tam(p.get("tarih"), 0)
    kategorik = max(kolon - sayisal - tarih, 0)
    return "%s / %s / %s" % (_sayi(sayisal), _sayi(kategorik), _sayi(tarih))


def _duplicate_metni(p):
    adet = _tam(p.get("duplicate"))
    if adet is None:
        return None
    oran = _oran(adet, p.get("satir"))
    if oran is None:
        return _sayi(adet)
    return "%s  (%s)" % (_sayi(adet), _yuzde(oran, 2))


def _donem_araligi(p):
    if not p.get("donem_min"):
        return None
    if p.get("donem_min") == p.get("donem_maks"):
        return "%s  (tek dönem)" % p["donem_min"]
    return "%s-%s  (%s dönem)" % (p["donem_min"], p["donem_maks"],
                                    _sayi(p.get("donem_adet") or 0))


# --------------------------------------------------------------------------
# KOKEN  -  veri seti ve sozluk NEREDEN geldi
# --------------------------------------------------------------------------
# Kartlar eskiden yalnizca ham adlari ve "(çalışma kopyası)" ekini
# gosteriyordu. Ikisi de kullaniciya bir sey anlatmiyordu: kopya bir
# uygulama detayi, ham ad ise "bunu ben mi sectim, platform mu uretti"
# sorusunu cevaplamiyordu - uc calisma baslangicinda (A/B/C) ayni satir
# tamamen farkli seyler anlatiyor. Artik her kart iki satir konusuyor:
#   ad     -> uzerinde calisilan tablonun / sozlugun adi
#   köken  -> hangi baslangicta, neyden turedigi (+ sozlukte teyit durumu)
# PLATFORMUN KENDI ADLARI. Kart artik kaynak tablonun HAM ADINI bir
# "ad" satirinda gostermiyor (kullanici karari: "hala sağda sözlük ve
# veri setinin orijinal adları duruyor, dediğim açıklama tipinde
# yazmamışsın"). Ham ad tek basina "bunu ben mi sectim, platform mu
# uretti" sorusunu cevaplamiyordu; uc calisma baslangicinda (A/B/C)
# ayni satir tamamen farkli seyler anlatiyordu.
#
# Yeni duzen iki satir:
#   ad    -> platformun uzerinde calistigi seyin ADI (her modda ayni)
#   köken -> NEREDEN geldigi, ORIJINAL ADIYLA birlikte, cumle olarak
# Adlar akis_durum'dan geliyor: burada bir ETIKET degil, GERCEKTEN
# yazilan tablonun adi duruyor (bkz. akis_faz01.amp_ciktilarini_yaz).
# Bir sure "Modelleme Tablosu" yaziyordu ve ortada o adla kaydedilmis
# hicbir sey yoktu - kullanici "bunu bu adla cekebilir miyim" diye
# sorunca cevap hayirdi.
PLATFORM_VERI_ADI = AMP_VERI_ADI
PLATFORM_SOZLUK_ADI = AMP_SOZLUK_ADI


def _adim_gecildi(durum, anahtar):
    """anahtar adimi TAMAMLANDI mi? Adim o modun listesinde yoksa False.

    teyit_adiminda_mi ile ayni kaynaga (adim_sirasi) bakar; oradaki soru
    "su an bu adimda miyiz", buradaki "bu adimi geride mi biraktik"."""
    try:
        sira = adim_sirasi(durum.get("mod"))
        return int(durum.get("i") or 0) > list(sira).index(anahtar)
    except (IndexError, KeyError, TypeError, ValueError):
        return False


def _kaynak_tablolar(durum):
    """Mod C: birlestirme planindaki tablo adlari, iskelet basta.

    Plan kullanicinin onayladigi haliyle durum'da duruyor; lineage
    tablosunu okumaya gerek yok."""
    plan = (durum.get("birlestirme") or {}).get("plan")
    if not isinstance(plan, dict):
        return []
    adlar = []
    ana = plan.get("ana_tablo")
    if isinstance(ana, dict) and ana.get("ad"):
        adlar.append(str(ana["ad"]))
    for k in plan.get("kaynaklar") or []:
        if isinstance(k, dict) and k.get("ad") and str(k["ad"]) not in adlar:
            adlar.append(str(k["ad"]))
    return adlar


# Kart satiri tek satir; dort addan sonrasi sayiya dokuluyor. Tam liste
# lineage tablosunda duruyor ve adim metninde adresi veriliyor.
KOKEN_TABLO_SINIRI = 4


def _kayit_yeri(durum, anahtar):
    """AMP ciktisinin NEREYE yazildigi - sohbete geri donmeden bulunsun.

    Kullanici "sonradan da cekebileyim" dedi; adin ne oldugunu bilmek
    yetmiyor, akistaki veri setine mi yoksa PROJE_HAFIZASI icindeki
    klasore mi yazildigi da lazim. Teyit kaydedilmeden once bos kalir
    ve kart "«Değişken Kontrolü» adımından sonra dolar" notunu gosterir."""
    from fe_agent import akis_faz01
    kayit = ((durum or {}).get("amp_cikti") or {}).get(anahtar)
    return akis_faz01.amp_nerede(kayit)


def _veri_kokeni(durum):
    """Veri setinin nereden geldigi - tek satir, moda gore.

    ORIJINAL AD BURADA gecer, ayri bir "ad" satirinda degil: kullanici
    hangi tablodan gelindigini bilmeli ama onu bir baslik gibi degil,
    kokenin parcasi olarak gormeli."""
    if durum.get("mod") in BIRLESTIREN_MODLAR:
        adlar = _kaynak_tablolar(durum)
        if not durum.get("veri_seti"):
            # Birlestirme henuz CALISMADI: "Oluşturuldu" demek yanlis;
            # satir bos kalir ve kart notu hangi adimda dolacagini soyler.
            return None
        if not adlar:
            return "Kaynak Tablolardan Oluşturuldu"
        gorunen = ", ".join(adlar[:KOKEN_TABLO_SINIRI])
        if len(adlar) > KOKEN_TABLO_SINIRI:
            gorunen += " ve %s tablo daha" % _sayi(len(adlar) - KOKEN_TABLO_SINIRI)
        return "Kaynak Tablolardan Oluşturuldu: %s" % gorunen
    if durum.get("veri_seti"):
        return "Hazır Veri Seti Seçildi: %s" % durum["veri_seti"]
    return None


def _sozluk_kokeni(durum):
    """Sozlugun nereden geldigi + teyit durumu - tek satir, moda gore.

    Teyit durumu YALNIZCA uretilen sozluklerde yaziliyor: hazir sozlukte
    "teyit" adimi sozlugu dogrulamak degil, kolon tipi/surec disi karari
    vermek icin var."""
    mod = durum.get("mod")
    uretilen = mod in SOZLUK_URETEN_MODLAR
    if not (durum.get("sozluk") or durum.get("sozluk_yedek")):
        return "Dil Modeli Tarafından Oluşturulacak" if uretilen else None
    if not uretilen:
        return "Hazır Sözlük Seçildi: %s" % sozluk_calisma.sozluk_adi(durum)
    koken = ("Sıfırdan, Dil Modeli Tarafından Oluşturuldu" if mod == "D"
             else "Veri Setinden Dil Modeli Tarafından Oluşturuldu")
    return "%s; %s" % (koken, "Teyit Edildi" if _adim_gecildi(durum, "teyit")
                       else "Teyit Edilecek")


def veri_paneli(durum):
    """VERI sekmesi. Tek seferde dolmaz: veri seti secilince boyutlar,
    tanimlar girilince hedef satirlari, profil calisinca null orani dolar."""
    p = durum.get("profil") or {}
    kolon = _tam(p.get("kolon_baslangic") or p.get("kolon"))
    satir = _tam(p.get("satir"))

    boyut = ("%s × %s" % (_sayi(satir), _sayi(kolon))
             if satir and kolon else None)

    kimlik_dup = _tam(p.get("duplicate_kimlik"))
    veri_adimi = _veri_adimi(durum)
    # HEDEF DEGISKEN AYRI KART DEGIL: hedef, veri setinin bir kolonu -
    # ayri kart olunca "baska bir kaynak" gibi okunuyordu. Tek kartta,
    # boyut/tip satirlarindan SONRA geliyor.
    veri_kart = _kart("Veri Seti", [
        # HAM AD DEGIL platformun adi; hangi tablodan gelindigi
        # "Köken" satirinda, cumle icinde yaziyor.
        ("Veri Seti", PLATFORM_VERI_ADI if durum.get("veri_seti") else None,
         veri_adimi),
        ("Köken", _veri_kokeni(durum), veri_adimi),
        ("Kayıt yeri", _kayit_yeri(durum, "veri"), KAYIT_ADIMI),
        ("Satır × kolon", boyut, veri_adimi),
        ("Sayısal / kategorik / tarih", _tip_dagilimi(p), veri_adimi),
        ("Tekrarlı satır", _duplicate_metni(p), veri_adimi),
        ("Kimlik bazlı tekrar",
         None if kimlik_dup is None else _sayi(kimlik_dup), TANIM_ADIMI),
        ("Toplam null oranı", _yuzde(p.get("null_oran"), 2), PROFIL_ADIMI),
        ("Hedef değişken",
         (durum.get("meta") or {}).get("target"), TANIM_ADIMI),
        ("Hedef tipi ve dağılımı", p.get("hedef_ozet"), TANIM_ADIMI),
        ("Hedef oranı", _yuzde_dogrudan(p.get("event_rate")), TANIM_ADIMI),
        ("Dönem aralığı", _donem_araligi(p), TANIM_ADIMI),
    ])

    kartlar = [veri_kart]
    if not satir:
        return _bekleyen_panel(veri_adimi, kartlar)
    return {"durum": "hazir", "kartlar": kartlar}


# --------------------------------------------------------------------------
# VERI & SOZLUK sekmesi  (app.js'te data-tab="ozet")
# --------------------------------------------------------------------------
# NEDEN AYRI BIR FONKSIYON
#   veri_paneli hala duruyor ve KULLANILIYOR (hazirlik_paneli ile birlikte
#   test edilebilir kucuk parca olarak). veri_sozluk_paneli onun ciktisini
#   ALIR, uzerine sozluk kartini ve feature tablosunu ekler. Boylece iki
#   sekme arasinda kart kopyalamak gerekmiyor.
#
# NEDEN TABLO BURADA URETILIYOR, VERI OKUNMUYOR
#   feature_tablo veri setinin BUTUN kolonlarini listeler - 1.042 satir
#   olabilir - ve her /analiz cagrisinda yeniden uretilir. Kaynagi
#   durum["profil"]["kolon_ozet"] (profil adiminda bir kez cikarildi),
#   sozluk calisma kopyasi (kucuk CSV, kisa omurlu onbellekli) ve
#   durum["sfa"]["ilk20"]. Hicbir yerde veri seti okunmaz.
# --------------------------------------------------------------------------

# IV / C degerleri durum'da yalnizca SFA'nin ilk N satiri icin duruyor
# (tam tablo dataset'te). Tabloda gorunmeyen satirlarin iv/c alani
# sozlesme geregi null kalir.
#
# TABLO NEDEN DORT KOLON
#   Bu panel artik bolme oncesi SON TEYIT yuzeyi: kullanici burada
#   kolonu gorur, tanimini duzeltir, surec disina alir. Sekiz kolonluk
#   tablo bu uc isi bogduruyordu - KATEGORI, TEKIL, ORNEK ve DURUM
#   kolonlari kaldirildi. Kategori artik hic sorulmuyor; DURUM satirin
#   govdesinde KALIYOR (surec disi satir soluk ciziliyor) ama kendi
#   kolonu yok. "FEATURE" basligi da "DEĞİŞKEN" oldu: ekranin geri
#   kalani ve sozluk bu kelimeyi kullaniyor.
# UC KOLON (kullanici karari): "sağ barda da değişken, tip, sözlük
# tanımı yer alsın sadece". NULL %% kolonu KARARIN VERILDIGI yere,
# sohbetteki teyit tablosuna tasindi - surec disi birakma karari orada
# veriliyor ve oran tam o kutunun solunda duruyor. Satir govdesi
# null_oran'i tasimaya devam ediyor: satira tiklaninca acilan detayda
# ve null esigi suzgecinde kullaniliyor.
FEATURE_KOLONLARI = ["DEĞİŞKEN", "TİP", "SÖZLÜK TANIMI"]

DURUM_TANIMLI = "tanımlı"
DURUM_YOK = "sözlükte yok"
DURUM_HARIC = "süreç dışı"


def _sozluk_kayitlari(durum):
    """Sozlukten {degisken: (tanim, kategori)} haritasi + kaynak bilgisi.

    Doner: (harita, kategoriler, tanim_sayisi, kopya_mi).
    Ayni degisken sozlukte iki kez geciyorsa ILK satir kazanir; ikincisi
    sessizce yutulmaz, kategori yazma tarafinda her iki satir da
    guncelleniyor (bkz. sozluk_calisma._uygula)."""
    tablo, kopya_mi = sozluk_calisma.sozluk_tablosu(durum)
    if tablo is None or not len(tablo):
        return {}, [], 0, kopya_mi

    ad_kolon = sozluk_calisma.degisken_kolonu_bul(tablo)
    tanim_kolon = sozluk_calisma.tanim_kolonu_bul(tablo)
    kat_kolon = sozluk_calisma.kategori_kolonu_bul(tablo)
    if ad_kolon is None:
        return {}, [], int(len(tablo)), kopya_mi

    harita, kategoriler = {}, []
    for _, r in tablo.iterrows():
        ad = str(r[ad_kolon]).strip()
        if not ad or ad in harita:
            continue
        # BOS TANIM "nan" DEGILDIR. Calisma kopyasi CSV olarak
        # saklaniyor; bos bir hucre pd.read_csv'den NaN olarak donuyor ve
        # duz str() ile "nan" yaziliyordu. Tanim hucresi artik
        # duzenlenebilir oldugu icin (kullanici yanlis bir tanimi
        # silebilir) bu yol gercekten kullaniliyor.
        tanim = ""
        if tanim_kolon:
            ham = r[tanim_kolon]
            tanim = "" if pd.isna(ham) else str(ham).strip()
        kategori = sozluk_calisma.kategori_sadelestir(
            r[kat_kolon] if kat_kolon else None)
        harita[ad] = (tanim or None, kategori)
        if kategori not in kategoriler:
            kategoriler.append(kategori)

    kategoriler = sorted(k for k in kategoriler
                         if k != sozluk_calisma.KATEGORISIZ)
    kategoriler.append(sozluk_calisma.KATEGORISIZ)
    return harita, kategoriler, int(len(tablo)), kopya_mi


def _sfa_haritasi(durum):
    """FEATURE -> (iv, c). Kaynak: durum["sfa"]["ilk20"]."""
    harita = {}
    for r in ((durum.get("sfa") or {}).get("ilk20") or []):
        if isinstance(r, dict) and r.get("FEATURE"):
            harita[str(r["FEATURE"])] = (r.get("IV"), r.get("C_VALUE"))
    return harita


def _kolon_listesi(durum, sozluk_harita):
    """Tabloda satir acilacak kolonlar, veri setindeki SIRAYLA.

    Once profil adiminin birakttigi kolon ozeti; o yoksa (veri seti henuz
    okunmadi) sozlukteki degiskenler. Ikisi de yoksa tablo bos kalir."""
    ozet = (durum.get("profil") or {}).get("kolon_ozet") or []
    if ozet:
        return [o for o in ozet if isinstance(o, dict) and o.get("ad")]
    # Veri seti henuz profillenmedi: sozluk ne diyorsa onu goster.
    return [{"ad": ad, "tip": None, "null_oran": None, "tekil": None,
             "ornek": None} for ad in sozluk_harita]


def _duzenleme_notu(durum, kopya_mi):
    """Tanim hucresi neden salt okunur? Duzenlenebilirse bos dize."""
    if kopya_mi:
        return ""
    if not sozluk_calisma.sozluk_adi(durum):
        return ("Sözlük henüz bağlanmadı; tanımlar salt okunur. "
                "«Veri ve Model Tanımları» adımında bir sözlük seçin.")
    return ("Sözlük çalışma kopyası oluşturulamadı (proje hafızasına "
            "yazılamıyor); tanımlar salt okunur. Orijinal sözlüğe "
            "hiçbir koşulda yazılmaz.")


def feature_tablo(durum):
    """VERI & SOZLUK sekmesindeki duzenlenebilir degisken tablosu.

    Bicimleme YAPILMAZ: null_oran ham oran (0–1), iv/c yoksa None.
    Ekranin sanallastirdigi ham veridir.

    Satir govdesi tablo kolonlariyla birlikte sadelesti: kategori, tekil
    ve ornek deger artik ne kolon ne de alan. "durum" alan olarak KALDI -
    surec disi satiri soluk cizmek ve onay kutusunu isaretli getirmek
    icin gerekiyor; kendi kolonu yok. iv/c SFA'dan gelir, tablonun degil
    satir detayinin verisidir."""
    sozluk_harita, _kategoriler, _, kopya_mi = _sozluk_kayitlari(durum)
    sfa_harita = _sfa_haritasi(durum)
    haric = set(durum.get("haric_kolonlar") or [])

    satirlar = []
    for o in _kolon_listesi(durum, sozluk_harita):
        ad = str(o.get("ad"))
        tanim, _kategori = sozluk_harita.get(
            ad, (None, sozluk_calisma.KATEGORISIZ))
        if ad in haric:
            satir_durum = DURUM_HARIC
        elif ad in sozluk_harita:
            satir_durum = DURUM_TANIMLI
        else:
            satir_durum = DURUM_YOK
        iv, c = sfa_harita.get(ad, (None, None))
        satirlar.append({
            "feature": ad,
            "tip": o.get("tip"),
            "tanim": tanim,
            "null_oran": o.get("null_oran"),
            "durum": satir_durum,
            "iv": iv,
            "c": c,
        })

    return {
        "kolonlar": list(FEATURE_KOLONLARI),
        "satirlar": satirlar,
        "toplam": len(satirlar),
        # Sozluk tanimi YALNIZCA calisma kopyasina yazilabilir. Kopya
        # yoksa hucre salt-okunur olmali; aksi halde kullanici yazdigini
        # saniyor. Kopya kayipsa sozluk_tablosu onu YENIDEN KURMAYI
        # deniyor (bkz. sozluk_calisma._kopyayi_kurtar); buraya False
        # dusuyorsa gercekten yazacak yer yok.
        "duzenlenebilir": bool(kopya_mi),
        # SEBEP DE GIDIYOR: "çalışma kopyası yok" tek basina kullaniciya
        # ne yapacagini soylemiyordu.
        "duzenleme_notu": _duzenleme_notu(durum, kopya_mi),
        # PLATFORMUN ADI, ham ad degil: hemen yanindaki kart da
        # "Sözlük: AMP_SOZLUK" diyor. Serit ham adi gosterince ayni
        # ekranda iki farkli ad duruyordu ve hangisinin uzerinde
        # calisildigi belirsizdi. Hangi sozlukten gelindigi kartin
        # "Köken" satirinda yaziyor.
        "sozluk_kaynak": (PLATFORM_SOZLUK_ADI
                          if sozluk_calisma.sozluk_adi(durum) else None),
    }


def sozluk_kapsami(durum):
    """Sozluk kapsami, VERI SETIYLE KARSILASTIRILARAK.

    Doner: (kolonlar, tanimli, tanimsiz)
      kolonlar : veri setinin kolon adlari (profil kolon ozetinden)
      tanimli  : bunlardan sozlukte DOLU bir aciklamasi olanlar
      tanimsiz : adi sozlukte hic gecmeyen YA DA aciklamasi BOS olanlar

    ACIK ISIM VE TEK KAYNAK
      Ayni soru uc yerde soruluyordu - sag paneldeki kapsam satiri,
      teyit kartinin ozeti ve aciklamasi olmayan kolonlarin isaretlenmesi.
      Uc ayri kural uc farkli sayi uretiyordu. Hepsi buradan geciyor.

    NEDEN "ADI GECIYOR" YETMIYOR
      Sozlukte satiri olup ACIKLAMASI BOS olan kolon tanimli sayilmaz:
      kullanici icin "tanım yok" demek, o kolonun ne oldugunu
      bilmiyor olmak demek. Sozlukte bos bir satir bunu degistirmiyor.

    Kolon ozeti henuz yoksa (veri seti okunmadan once) uc bos liste
    doner; cagiran taraf ∅ gosterir."""
    p = (durum or {}).get("profil") or {}
    ozet = p.get("kolon_ozet")
    kolonlar = [str(o["ad"]) for o in (ozet if isinstance(ozet, list) else [])
                if isinstance(o, dict) and o.get("ad")]
    if not kolonlar:
        return [], [], []
    harita, _kat, _adet, _kopya = _sozluk_kayitlari(durum)
    tanimli, tanimsiz = [], []
    for ad in kolonlar:
        kayit = harita.get(ad)
        # harita[ad] = (tanim or None, kategori) - bos tanim None gelir
        if kayit and kayit[0]:
            tanimli.append(ad)
        else:
            tanimsiz.append(ad)
    return kolonlar, tanimli, tanimsiz


def _sozluk_karti(durum):
    # KAPSAM CANLI HESAPLANIR ve VERI SETIYLE KARSILASTIRILIR. Eskiden
    # durum["profil"]["kapsam"] okunuyordu; o deger kurulum_plan'da BIR
    # KEZ, sozluge kolon eklenmeden once hesaplaniyor ve bir daha
    # guncellenmiyordu. "Tanım sayısı" da sozlugun SATIR SAYISIYDI -
    # sozlukte veri setinde olmayan kolonlar varsa sayi sisiyor ve
    # kapsamla celisiyordu. Uc satir da artik ayni kaynaktan
    # (sozluk_kapsami) geliyor, dolayisiyla birlikte hareket ediyorlar.
    kolonlar, tanimli, tanimsiz = sozluk_kapsami(durum)
    kapsam = (round(100.0 * len(tanimli) / len(kolonlar), 1)
              if kolonlar else None)

    sozluk_adimi = _sozluk_adimi(durum)
    return _kart("Değişken Sözlüğü", [
        # HAM AD DEGIL platformun adi; hangi sozlukten gelindigi
        # "Köken" satirinda, cumle icinde yaziyor.
        ("Sözlük",
         PLATFORM_SOZLUK_ADI if sozluk_calisma.sozluk_adi(durum) else None,
         sozluk_adimi),
        ("Köken", _sozluk_kokeni(durum), sozluk_adimi),
        ("Kayıt yeri", _kayit_yeri(durum, "sozluk"), KAYIT_ADIMI),
        ("Tanım sayısı", _sayi(len(tanimli)) if kolonlar else None,
         sozluk_adimi),
        ("Kapsam", _yuzde_dogrudan(kapsam, 1), sozluk_adimi),
        ("Sözlükte olmayan değişken sayısı",
         _sayi(len(tanimsiz)) if kolonlar else None, sozluk_adimi),
    ])


def teyit_adiminda_mi(durum):
    """Bolme oncesi sozluk teyidi adimi ACIK mi?

    Panelin o adimda NASIL cizilecegini belirliyor (bkz.
    veri_sozluk_paneli / kart_kat). Adim anahtarina bakar, kartin
    ekranda olup olmadigina degil: kullanici sekme degistirip geri
    gelse de ayni cevabi verir."""
    try:
        sira = adim_sirasi(durum.get("mod"))
        return sira[int(durum.get("i") or 0)] == "teyit"
    except (IndexError, KeyError, TypeError, ValueError):
        return False


def veri_sozluk_paneli(durum):
    """VERI & SOZLUK sekmesi: veri_paneli kartlari + sozluk karti + tablo.

    KARTLAR KATLANMAZ (kullanici karari). Bir sure teyit adiminda katli
    aciliyorlardi; sebep, iki kart acikken tablonun ekranin altina
    kaymasiydi. Ama sozluk teyidi artik SOHBET BLOGUNDA yapiliyor; bu
    panel yalnizca aciklama veriyor, burada gizlenecek bir karar yok."""
    temel = veri_paneli(durum)
    veri = dict(temel)
    veri["kartlar"] = list(temel.get("kartlar") or []) + [_sozluk_karti(durum)]
    tablo = feature_tablo(durum)
    # EXCEL INDIRME KAPISI: liste ancak sozluk teyidi KAYDEDILDIKTEN
    # sonra indirilebilir (kullanici karari). Kaydedilmemis bir liste,
    # henuz verilmemis karari dosyaya yazmak olurdu. Bayrak tabloyla
    # birlikte geliyor ki panel her cizimde dogru durumu gostersin.
    tablo["excel_hazir"] = bool(durum.get("teyit"))
    veri["feature_tablo"] = tablo
    return veri


# --------------------------------------------------------------------------
# EKSIK DEGER sekmesi
# --------------------------------------------------------------------------
def _en_yuksek_null(p, en_yuksek):
    """En cok bos kolon. Hicbir kolonda null yoksa oran degil, bu gercek
    yazilir - "%0,0 - -" satiri hatali hesap izlenimi veriyordu."""
    if en_yuksek is None:
        return None
    if not en_yuksek or not p.get("null_maks_kolon"):
        return "null içeren kolon yok"
    return "%s  -  %s" % (_yuzde(en_yuksek, 1), p["null_maks_kolon"])


def eksik_paneli(durum):
    """EKSIK DEGER sekmesi. Kaynak: veri_profili_uygula'nin durum'a yazdigi
    ilk 20 satir ve null dagilim ozeti; tam tablo dataset'te kalir."""
    p = durum.get("profil") or {}
    ilk20 = p.get("eksik_ilk20")
    if not p.get("null_ozet") and not ilk20:
        return _bekleyen_panel(PROFIL_ADIMI)

    n = p.get("null_ozet") or {}
    toplam_kolon = _tam(p.get("profil_kolon"), 0)
    nullu_olan = _tam(p.get("null_kolon_adet"))
    en_yuksek = p.get("null_maks")
    nullu_oran = _oran(nullu_olan, toplam_kolon)

    ozet_kart = _kart("Eksik değer özeti", [
        ("İncelenen kolon", _sayi(toplam_kolon), PROFIL_ADIMI),
        ("Null içeren kolon",
         None if nullu_olan is None
         else "%s  (%s)" % (_sayi(nullu_olan),
                            _yuzde(nullu_oran, 1) if nullu_oran is not None
                            else "-"), PROFIL_ADIMI),
        ("Toplam null oranı", _yuzde(p.get("null_oran"), 2), PROFIL_ADIMI),
        ("En yüksek null oranı", _en_yuksek_null(p, en_yuksek), PROFIL_ADIMI),
        ("Aşırı null eşiğini aşan", _sayi(_tam(p.get("asiri_null_adet"), 0)),
         PROFIL_ADIMI),
    ])

    dagilim_kart = _kart("Null oranı dağılımı", [
        ("Hiç null yok", _sayi(_tam(n.get("hic_null_yok"), 0)), PROFIL_ADIMI),
        ("Az  (≤ %5)", _sayi(_tam(n.get("az"), 0)), PROFIL_ADIMI),
        ("Orta  (%5-%50)", _sayi(_tam(n.get("orta"), 0)), PROFIL_ADIMI),
        ("Aşırı  (> %50)", _sayi(_tam(n.get("asiri"), 0)), PROFIL_ADIMI),
    ])

    satirlar = [[r.get("FEATURE"), r.get("TYPE"),
                 _sayi(_tam(r.get("NULL_COUNT"), 0)),
                 _yuzde(r.get("NULL_RATIO"), 1) or "-",
                 _sayi(_tam(r.get("UNIQUE"), 0)),
                 r.get("DURUM") or ""]
                for r in (ilk20 or [])]

    return {
        "durum": "hazir",
        "kartlar": [ozet_kart, dagilim_kart],
        "tablo": {
            "baslik": "Null Oranına Göre İlk %d Kolon" % len(satirlar),
            "kolonlar": ["FEATURE", "TİP", "NULL", "NULL ORANI",
                         "TEKİL", "DURUM"],
            "satirlar": satirlar,
            "toplam": toplam_kolon,
            "gosterilen": len(satirlar),
        },
    }


# --------------------------------------------------------------------------
# HAZIRLIK sekmesi
# --------------------------------------------------------------------------
# EKSIK DEGER sekmesi kaldirildi; icerigi buraya tasindi. eksik_paneli
# SILINMEDI: hem tek basina test ediliyor hem de bu sekme onu kaynak
# olarak kullaniyor. Iki yerde ayni kart kodunu tutmak, birinin sessizce
# eskimesi demekti.
# --------------------------------------------------------------------------
def _donusum_karti(durum):
    """Planlanan donusumler.

    Donusumun KENDISI bu turda yok; veri sozlesmesi ve bos liste hazir.
    Kart bos gorunmesin diye listenin bos hali acikca yaziliyor -
    "henüz tanımlanmadı" ile "hesaplanamadı" ayni sey degil."""
    hz = durum.get("hazirlik")
    adimlar = (hz or {}).get("adimlar") or []
    if not adimlar:
        return {"baslik": "Planlanan Dönüşümler",
                "not": "Dönüşüm tanımlandıkça bu kart dolar.",
                "satirlar": [{"etiket": "Durum",
                              "deger": "Henüz dönüşüm tanımlanmadı"}]}

    satirlar = []
    for sira, adim in enumerate(adimlar, 1):
        if isinstance(adim, dict):
            etiket = adim.get("ad") or adim.get("baslik") or "Adım %d" % sira
            deger = adim.get("aciklama") or adim.get("ozet") or "-"
        else:
            etiket, deger = "Adım %d" % sira, str(adim)
        satirlar.append({"etiket": etiket, "deger": deger})
    return {"baslik": "Planlanan Dönüşümler", "satirlar": satirlar}


# Bolme degistirilince gecersiz kalan adimlarin durum anahtarlari.
# Profil BURADA YOK: profil tum satirlarda olculuyor, bolmeden etkilenmiyor.
BOLME_BAGIMLI = ("sfa", "stabilite", "baz", "kalite", "secim", "model",
                 "final")


def _bolme_kilidi(durum):
    """(kilitli, neden). Bolme uygulanmis VE bolmeye bagli bir adim
    calismissa form kilitlenir: degistirmek o analizleri gecersiz kilar."""
    b = durum.get("bolme") or {}
    if not b.get("kalici"):
        return False, ""
    calisan = [k for k in BOLME_BAGIMLI if durum.get(k)]
    if not calisan:
        return False, ""
    return True, ("Bölme uygulandı ve sonraki adımlar bu bölme üzerinde "
                  "çalıştı (%s). Bölmeyi değiştirmek bu analizleri geçersiz "
                  "kılar; devam etmeden önce onayınızı isterim."
                  % ", ".join(ADIMLAR.get(k, {}).get("baslik") or k
                              for k in calisan))


def bolme_formu(durum):
    """Bolme Stratejisi kartinin ÖZEL AYARLAR formu.

    Alanlarin degerleri bolme_ayarlari()'ndan geliyor; form ile fiilen
    uygulanan bolme ayni kaynaktan okunmali, yoksa kullanici ekranda
    baska, veride baska bir bolme gorur.

    SAYI KUTUSU YERINE SECIM LISTESI (kullanici karari): oranlar, test
    donemleri ve parca sayisi artik somut seceneklerden seciliyor ve
    listeler VERIDEN uretiliyor - yalnizca yapilabilir olanlar cikiyor.
    Tek secenek kaliyorsa alan "sabit" isaretleniyor ve on yuz onu
    acilir liste degil duz metin olarak ciziyor."""
    a = bolme_ayarlari(durum)
    m = durum.get("meta") or {}
    p = durum.get("profil") or {}
    satir = p.get("satir")
    kilitli, neden = _bolme_kilidi(durum)
    kisitlar = bolme_kisitlari(durum)
    hazir = durum.get("_hazir_bolme") if isinstance(
        durum.get("_hazir_bolme"), dict) else None

    def _kisit(alan, secenek=None):
        """O alanin (ve varsa o secenegin) kisit metni; yoksa bos dize."""
        for k in kisitlar:
            if k["alan"] == alan and (secenek is None
                                      or k["secenek"] == secenek):
                return k["metin"]
        return ""

    def _kilitli_secenekler(alan):
        return [k["secenek"] for k in kisitlar
                if k["alan"] == alan and k["secenek"]]

    # Her alan ETIKETINI ve ACIKLAMASINI da tasiyor: ekranda terimin
    # Turkcesi yaziyor ve altinda ne demek oldugu gunluk dille
    # anlatiliyor (bkz. akis_durum.BOLME_ALAN_ACIKLAMA).
    def _alan(ad, deger, **ek):
        kayit = {"deger": deger,
                 "etiket": BOLME_ALAN_BASLIK.get(ad, ad),
                 "aciklama": BOLME_ALAN_ACIKLAMA.get(ad, "")}
        kayit.update(ek)
        return kayit

    def _secim(ad, deger, secenekler, **ek):
        """Secim alani. Tek secenek varsa "sabit": kullanici secemez ama
        ne oldugunu okur - tiklayinca tek satir cikan bir acilir liste
        secim varmis gibi gorunuyordu."""
        kayit = _alan(ad, deger, secenekler=secenekler, **ek)
        kayit["sabit"] = len(secenekler) <= 1
        return kayit

    # ---- 1. asama: test nasil ayrilsin --------------------------------
    test_kilit = _kilitli_secenekler("test_tanim")
    test_secenekleri = ["zamansal", "rastgele"]
    if hazir:
        # Hazir bolme YALNIZCA tabloda varsa listede: olmayan bir
        # secenegi kilitli gostermek, kullaniciya hic kuramayacagi bir
        # yol oneriyordu.
        test_secenekleri.insert(0, "hazir")
    test_tanim = _alan("test_tanim", a["test_tanim"],
                       secenekler=bolme_secenek_listesi(
                           "test_tanim", test_secenekleri, test_kilit),
                       kilitli_secenekler=test_kilit)
    test_tanim["not"] = _kisit("test_tanim")
    if hazir:
        test_tanim["not"] = (test_tanim["not"] + " " if test_tanim["not"]
                             else "") + _hazir_bolme_notu(hazir)

    # ---- test donemleri: SOMUT secenekler -----------------------------
    donem_secenekleri = test_donem_secenekleri(durum)
    donem_alani = _secim("oot_adet", test_donem_anahtari(a),
                         donem_secenekleri,
                         kilitli=not bool(m.get("donem"))
                                 or a["test_tanim"] != "zamansal")
    if not donem_secenekleri:
        donem_alani["not"] = ("Zamansal bölme için en az iki dönem "
                              "gerekiyor.")
    elif donem_alani["kilitli"] and a["test_tanim"] == "rastgele":
        donem_alani["not"] = ("Rastgele bölmede dönem bilgisi "
                              "kullanılmıyor.")

    # ---- oranlar: hazir yuzdeler --------------------------------------
    # ORAN ARTIK SERBEST (kullanici karari: "bu sampling sayısını 1-99
    # arası verebilme özgürlüğüm olmalı ... zorunlu olmadıkça özgürlüğümü
    # kısıtlama"). Hazir liste (%10/%15/%20/%25/%30) kaldirildi; sinir
    # yalnizca matematiksel olan. Satir karsiligi on yuzde ANINDA
    # hesaplaniyor, "yaklasik 2.000 satir" yazisi sabit kalmiyor.
    # HAZIR CIPLER + "Özel": ekran secim ekrani gibi dursun ama serbest
    # yazma ozgurlugu kalksin istemiyoruz (kullanici karari). Deger
    # hazir ciplerden birine esitse o cip secili, degilse "Özel" secili
    # ve sayi kutusu aciliyor.
    test_oran = _alan("test_oran", int(round(100 * a["test_oran"])),
                      tip="yuzde", hazir=[10, 20, 30],
                      en_az=int(round(100 * ORAN_EN_AZ)),
                      en_cok=int(round(100 * ORAN_EN_COK)),
                      toplam_satir=satir,
                      kilitli=a["test_tanim"] != "rastgele")
    if test_oran["kilitli"]:
        # KILITLI ALAN SEBEBINI YAZAR. Soluk bir "%20" tek basina
        # "neden dokunamiyorum" sorusunu doguruyordu.
        test_oran["not"] = ("Zamansal bölmede OOT / Test dönemlere göre "
                            "ayrılıyor; bu pay kullanılmıyor.")
    val_oran = _alan("val_oran", int(round(100 * a["val_oran"])),
                     tip="yuzde", hazir=[10, 20, 30],
                     en_az=int(round(100 * ORAN_EN_AZ)),
                     en_cok=int(round(100 * ORAN_EN_COK)),
                     toplam_satir=satir,
                     kilitli=not a["val_var"])
    if val_oran["kilitli"]:
        val_oran["not"] = ("Doğrulama seti kapalı; açarsanız bu pay "
                           "kullanılır.")

    birim_kisit = _kisit("birim", "kimlik")
    birim = _alan("birim", a["birim"],
                  secenekler=bolme_secenek_listesi(
                      "birim", ["satir", "kimlik"],
                      _kilitli_secenekler("birim")),
                  kilitli=not bool(m.get("id")))
    if birim_kisit:
        birim["not"] = birim_kisit

    # ONAY KUTUSU YERINE IKI SECENEKLI LISTE: "Koru / Koruma" ne
    # secildigini okunur biçimde soyluyor; tek basina bir kare
    # "işaretli ne demek" sorusunu doguruyordu.
    katmanla = _alan("katmanla", "koru" if a["katmanla"] else "koruma",
                     secenekler=[
                         {"anahtar": "koru", "etiket": "Korunsun",
                          "aciklama": "Hedef oranı setler arasında "
                                      "benzer tutulur."},
                         {"anahtar": "koruma", "etiket": "Korunmasın",
                          "aciklama": "Kayıtlar hedefe bakılmadan "
                                      "dağıtılır."}])
    katmanla_kisit = _kisit("katmanla")
    if katmanla_kisit:
        katmanla["not"] = katmanla_kisit

    # HAZIR BOLMEDE ince ayarlarin cogu ANLAMSIZ: setler tabloda yazili,
    # oran da birim de katmanlama da onu degistirmez. Kilitleniyor ki
    # kullanici etkisi olmayan bir kutuyu cevirip sonuc beklemesin.
    if a["test_tanim"] == "hazir":
        for kayit in (birim, katmanla, test_oran, donem_alani):
            kayit["kilitli"] = True
            kayit["not"] = ("Bölme veri setinde hazır olduğu için bu ayar "
                            "kullanılmıyor.")

    return {
        "duzenlenebilir": not kilitli,
        "alanlar": {
            "test_tanim": test_tanim,
            "oot_adet": donem_alani,
            "test_oran": test_oran,
            "train_kullanimi": _alan(
                "train_kullanimi", a["train_kullanimi"],
                secenekler=bolme_secenek_listesi(
                    "train_kullanimi", ["full", "val", "full_cv", "val_cv"]),
                basliklar=TRAIN_KULLANIMI_BASLIK),
            "birim": birim,
            "val_var": _alan("val_var",
                             "kullan" if a["val_var"] else "kullanma",
                             secenekler=[
                                 {"anahtar": "kullan", "etiket": "Kullan",
                                  "aciklama": "Eğitim verisinden ayrı bir "
                                              "değerlendirme seti ayrılır."},
                                 {"anahtar": "kullanma",
                                  "etiket": "Kullanma",
                                  "aciklama": "Ayrı bir doğrulama seti "
                                              "açılmaz."}]),
            "seed_tur": _alan("seed_tur", a["seed_tur"],
                              secenekler=bolme_secenek_listesi(
                                  "seed_tur", ["sabit", "coklu"])),
            "tekrar": _alan("tekrar", a["tekrar"], tip="sayi",
                            hazir=[3, 5, 10],
                            en_az=2, en_cok=TEKRAR_EN_COK,
                            kilitli=a["seed_tur"] != "coklu"),
            "gap": _alan("gap", a["gap"], tip="sayi",
                         hazir=[0, 1, 2],
                         hazir_etiket={"0": "Yok", "1": "1 dönem",
                                       "2": "2 dönem"},
                         en_az=0, en_cok=GAP_EN_COK,
                         kilitli=a["test_tanim"] != "zamansal"),
            "val_oran": val_oran,
            "cv": _alan("cv", a["cv"],
                        secenekler=bolme_secenek_listesi(
                            "cv", ["yok", "kfold", "zaman"],
                            _kilitli_secenekler("cv"))),
            "kat": _alan("kat", a["kat"], tip="sayi", hazir=[3, 5, 10],
                         en_az=KAT_EN_AZ, en_cok=KAT_EN_COK,
                         kilitli=a["cv"] == "yok",
                         **({"not": "Çapraz doğrulama kapalı."}
                            if a["cv"] == "yok" else {})),
            "katmanla": katmanla,
            "seed": _alan("seed", a["seed"]),
        },
        "ozet": bolme_ozeti(durum),
        # Ozet GERCEK satir sayilarini mi tasiyor yoksa beklenen dagilimi
        # mi? On yuz bunu metinden anlayamaz; oneri modunda tahmini ozeti
        # HIC cizmiyor (plan listesi zaten ayni bilgiyi satir satir
        # yaziyor), kesin sayilari ise gosteriyor.
        "ozet_kesin": bool((durum.get("bolme") or {}).get("satir")),
        "uyarilar": bolme_uyarilari(durum),
        "kisitlar": kisitlar,
        "kilitli": kilitli,
        "kilit_nedeni": neden,
    }


def _hazir_bolme_notu(hazir):
    """Tabloda bulunan bolmeyi tek cumlede anlatir."""
    sayim = hazir.get("sayim") or {}
    parcalar = []
    for ad in ("egitim", "val", "test", "oot"):
        n = sayim.get(ad)
        if n:
            parcalar.append("%s %s" % ({"egitim": "eğitim",
                                        "val": "doğrulama",
                                        "test": "test",
                                        "oot": "test"}[ad], _sayi(int(n))))
    return ("Veri setinde hazır bölme bulundu (%s): %s. Kolonlara "
            "dokunulmaz, yalnızca okunur."
            % (", ".join(hazir.get("kolonlar") or []),
               " · ".join(parcalar) if parcalar else "-"))


def bolme_satirlari(durum, oneri_ayarlari=None):
    """Karsilastirma tablosunun satirlari.

    Her satir: {anahtar, etiket, bolum, ipucu, alanlar, salt, kosul,
                oneri}
      "alanlar" -> sag sutundaki kontrolleri kuran form alan adlari
      "salt"    -> kontrol yok, iki sutunda da ayni okunur deger
                   (Dönem Kolonu, Bölme Kolonu)
      "kosul"   -> satirin GORUNME kosulu; on yuz taslaktan aninda
                   hesapliyor (bkz. akis_durum.BOLME_SATIRLARI)
      "oneri"   -> ONERILEN panelin salt okunur degeri

    Satir basina "?" YOK: aciklamalar tek bir "Detaylar ve Terimler"
    alaninda (kullanici karari - her satira soru isareti koyunca ekran
    yardim dokumanina donuyordu)."""
    a_oneri = dict(bolme_ayarlari(durum))
    if isinstance(oneri_ayarlari, dict):
        a_oneri.update(oneri_ayarlari)
        if "oot_tanim" in oneri_ayarlari:
            a_oneri["oot_tanim"] = oneri_ayarlari["oot_tanim"]

    satirlar = []
    for tanim in BOLME_SATIRLARI:
        kayit = {
            "anahtar": tanim["anahtar"],
            "etiket": tanim["etiket"],
            "bolum": tanim["bolum"],
            "alanlar": list(tanim["alanlar"]),
            "oneri": bolme_satir_degeri(tanim["anahtar"], a_oneri, durum),
        }
        if tanim.get("salt"):
            kayit["salt"] = bolme_satir_degeri(tanim["anahtar"],
                                               bolme_ayarlari(durum), durum)
        if tanim.get("kosul"):
            kayit["kosul"] = {"alan": tanim["kosul"]["alan"],
                              "degerler": list(tanim["kosul"]["degerler"])}
        satirlar.append(kayit)
    return satirlar


def bolme_sozlugu():
    """"Detaylar ve Terimler": soru - cevap listesi. Kullanicinin
    soracagi bicimde yazili ("Kat sayısı neyi değiştirir?")."""
    return [{"soru": soru, "cevap": cevap} for soru, cevap in BOLME_SOZLUK]


def bolme_ozet_karti(durum):
    """HAZIRLIK sekmesindeki SALT OKUNUR bolme ozeti.

    Hazirlik sekmesi artik SECIM YAPILAN yer degil: secim "Bölme
    Stratejisi" adiminda, sohbet kartinda yapiliyor. Burada yalnizca
    nasil ayarlandigi yaziyor. Ayni karari iki ayri ekranda vermek,
    kullanicinin hangisinin gecerli oldugunu bilememesi demekti."""
    a = bolme_ayarlari(durum)
    b = durum.get("bolme") or {}
    donemler = list(durum.get("_donemler") or [])

    satirlar = [("Bölme Türü", bolme_etiket("test_tanim", a["test_tanim"]),
                 BOLME_ADIMI)]
    if a["test_tanim"] == "zamansal":
        satirlar.append(("Test Dönemi",
                         "Son %d dönem%s" % (int(a["oot_tanim"]["adet"]),
                                             (" (%s)" % donemler[-1])
                                             if donemler else ""),
                         BOLME_ADIMI))
    else:
        satirlar.append(("Geliştirme / Test",
                         "%%%d / %%%d"
                         % (round(100 * (1 - float(a["test_oran"]))),
                            round(100 * float(a["test_oran"]))),
                         BOLME_ADIMI))
    satirlar.append(("Kalan Verinin Kullanımı",
                     bolme_etiket("train_kullanimi", a["train_kullanimi"]),
                     BOLME_ADIMI))
    if a["cv"] != "yok":
        satirlar.append(("Çapraz Doğrulama",
                         "%s · %d parça" % (bolme_etiket("cv", a["cv"]),
                                            int(a["kat"])),
                         BOLME_ADIMI))
    satirlar.append(("Bölme Birimi", bolme_etiket("birim", a["birim"]),
                     BOLME_ADIMI))
    satirlar.append(("Hedefe Göre Katmanlama",
                     "Açık" if a["katmanla"] else "Kapalı", BOLME_ADIMI))
    satirlar.append(("Rastgelelik Tohumu", str(a["seed"]), BOLME_ADIMI))
    satirlar.append(("Setler", bolme_ozeti(durum),
                     None if b.get("satir") else BOLME_ADIMI))

    kart = _kart(BOLME_ADIMI, satirlar)
    kart["not"] = ("Ayarlar «" + BOLME_ADIMI + "» adımında, sohbet kartı "
                   "üzerinden değiştirilir.")
    return kart


def hazirlik_paneli(durum):
    """HAZIRLIK sekmesi: bolme OZETI + eksik deger ozeti + donusumler."""
    temel = eksik_paneli(durum)
    veri = dict(temel)
    veri["kartlar"] = (list(temel.get("kartlar") or [])
                       + [bolme_ozet_karti(durum), _donusum_karti(durum)])
    # FORM ARTIK BURADA CIZILMIYOR (bkz. bolme_ozet_karti). Alan listesi
    # yine gonderiliyor: ust seritteki set secici "Doğrulama" dugmesini
    # gosterip gostermeyecegini buradan okuyor ve ikinci bir kaynak
    # tutmak iki yerin farkli sey soylemesi demekti.
    veri["bolme_formu"] = dict(bolme_formu(durum), sadece_ozet=True)
    return veri


# --------------------------------------------------------------------------
# SFA sekmesi
# --------------------------------------------------------------------------
def sfa_paneli(durum):
    """SFA sekmesi. Kaynak: durum["sfa"] ozeti + sfa_uygula'nin yazdigi
    IV'ye gore ilk 20 satir; tam tablo dataset'te kalir."""
    s = durum.get("sfa") or {}
    if s.get("analiz_edilen") is None:
        return _bekleyen_panel(SFA_ADIMI)

    olculen = _tam(s.get("analiz_edilen"), 0)
    gecen = _tam(s.get("pass_adet"), 0)
    atlanan = len(s.get("atlanan") or [])
    sizinti = len(s.get("sizinti") or [])
    pass_oran = _oran(gecen, olculen)

    ozet_kart = _kart("Tek değişken analizi", [
        ("Ölçülen değişken", _sayi(olculen), SFA_ADIMI),
        ("PASS", "%s  (%s)" % (_sayi(gecen),
                               _yuzde(pass_oran, 1)
                               if pass_oran is not None else "-"), SFA_ADIMI),
        ("Atlanan (ölçülemedi)", _sayi(atlanan), SFA_ADIMI),
        ("Sızıntı şüpheli", _sayi(sizinti), SFA_ADIMI),
        ("Tam tablo", s.get("tablo_dataset") or "proje hafızası", None),
    ])

    esik_kart = _kart("Eşikler", [
        ("IV", "> %s" % _ond(sfa_mod.IV_ESIK, 2), None),
        ("C-value", "> %s" % _ond(sfa_mod.C_ESIK, 2), None),
        ("Sızıntı şüphesi", "C-value > %s" % _ond(sfa_mod.SIZINTI_ESIK, 2), None),
        ("Kategorik seviye sınırı", _sayi(sfa_mod.KATEGORIK_MAX), None),
    ])

    satirlar = [[r.get("FEATURE"),
                 _ond(r.get("IV"), 3),
                 _ond(r.get("C_VALUE"), 3),
                 r.get("SFA_RESULT") or "",
                 r.get("NOT") or ""]
                for r in (s.get("ilk20") or [])]

    veri = {"durum": "hazir", "kartlar": [ozet_kart, esik_kart]}
    if satirlar:
        veri["tablo"] = {
            "baslik": "Bilgi Değerine Göre İlk %d Değişken" % len(satirlar),
            "kolonlar": ["FEATURE", "IV", "C-VALUE", "SONUÇ", "NOT"],
            "satirlar": satirlar,
            "toplam": olculen + atlanan,
            "gosterilen": len(satirlar),
        }
    return veri
