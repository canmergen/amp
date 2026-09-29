# -*- coding: utf-8 -*-
"""fe_agent/akis_faz02.py - Faz 02 - Veri Anlama ve Hazirlama: profil, SFA, stabilite, baz set.

akis.py bolundu; bu dosya o bolumun aynisidir.
"""

import json

import numpy as np
import pandas as pd
from fe_agent import aralik as aralik_mod
from fe_agent import sfa as sfa_mod

from fe_agent.akis_durum import (
    SPLIT_KOLON, _df_oku, _liste, _nerede, _ond, _sayi, _yaz,
    bolme_ayarlari, kolon_ozeti_cikar, kolon_ozeti_tamamla, maskeler,
    modelleme_df, setler, metin_yaz, set_basligi, sozluk_oku,
)

# SFA'nin aralik onerileri (bkz. aralik.py) calismanin klasorunde; durum
# dosyasini sisirmemek icin ayri JSON. Panel /sfa_aralik ucundan okur.
ARALIK_DOSYA = "sfa_aralik.json"


def _dosya_metni(yol):
    from fe_agent.akis_durum import _folder
    try:
        with _folder().get_download_stream(yol) as akis:
            return akis.read().decode("utf-8")
    except Exception:
        return None


def aralik_oku(durum):
    """SFA aralik onerileri {degisken: sonuc}; yoksa {}."""
    a = (durum.get("sfa") or {}).get("aralik") or {}
    if not a.get("dosya"):
        return {}
    try:
        return json.loads(_dosya_metni(a["dosya"]) or "{}")
    except Exception:
        return {}


def aralik_yolu(durum):
    from fe_agent.akis_faz01 import amp_klasor_adi
    return "/%s/%s" % (amp_klasor_adi(durum), ARALIK_DOSYA)


def _aciklamalar(durum):
    """{kolon: sozluk aciklamasi}: hassas degisken tespiti icin."""
    try:
        from fe_agent import sozluk_calisma
        sz = sozluk_oku(durum)
        ad_k = sozluk_calisma.degisken_kolonu_bul(sz)
        tanim_k = sozluk_calisma.tanim_kolonu_bul(sz)
        if ad_k is None or tanim_k is None:
            return {}
        return {str(a): str(t) for a, t in zip(sz[ad_k], sz[tanim_k].fillna(""))}
    except Exception:
        return {}


def _aralik_hesapla(durum, df, target, adaylar, iv_skorlari):
    """SFA'nin aralik onerileri. Araliklar egitim setinden ogrenilir; diger
    setlerde yalnizca siralamanin korunup korunmadigina bakilir.
    Doner: ozet (durum["sfa"]["aralik"])."""
    s = setler(durum, df)
    test_tanim = bolme_ayarlari(durum).get("test_tanim")
    diger = {set_basligi(ad, test_tanim): s[ad] for ad in ("val", "test", "oot")
             if ad in s and bool(s[ad].any())}
    sonuc = aralik_mod.hesapla(df, target, adaylar, s["egitim"], diger,
                               _aciklamalar(durum), iv_skorlari)
    yol = aralik_yolu(durum)
    metin_yaz(yol, json.dumps(sonuc, ensure_ascii=False, default=str))
    onerilen = [k for k, v in sonuc.items() if v["aralik_sayisi"] > 1]
    return {
        "dosya": yol,
        "degisken": len(sonuc),
        "onerilen": len(onerilen),
        "hassas": sorted(k for k, v in sonuc.items() if v.get("hassas")),
        "tutarsiz": sorted(k for k in onerilen
                           if any(r < aralik_mod.TUTARLILIK_ESIK
                                  for r in (sonuc[k].get("tutarlilik") or {}).values())),
        "eksik_notu": sorted(k for k, v in sonuc.items() if v.get("notlar")),
    }


# Plan metinleri her "Geri Dön" tiklamasinda yeniden uretilir; bu yuzden
# plan fonksiyonlari TAM tablo OKUMAZ. Bir sayiya ihtiyac duyulursa
# durum'daki profil bilgisi kullanilir, yoksa asagidaki limitle sema okunur.
# Tam okuma yalnizca "uygula" adimlarinda yapilir.
SEMA_LIMITI = 200


def _kolon_sayisi(durum):
    """Plan metni icin kolon sayisi. Once durum, sonra sinirli sema okumasi."""
    p = durum.get("profil") or {}
    if p.get("kolon"):
        return int(p["kolon"])
    try:
        return int(_df_oku(durum["veri_seti"], limit=SEMA_LIMITI).shape[1])
    except Exception:
        return 0


def _meta_kolonlar(durum):
    """Baz setten ASLA dusurulmeyecek kolonlar.

    target/id/donem'in yaninda SPLIT_KOLON da korunur: kimlik kolonu yoksa
    (ya da kimlik listesi cok buyukse) gelistirme/test bolmesi veri setine
    bu kolonla KALICI yaziliyor. bolme_hazirla onu haric_kolonlar'a da
    ekledigi icin eskiden baz setten dusuyordu; sonraki her adim
    maskeler() icinde AdimHatasi aliyor ve calisma kurtarilamaz bicimde
    kilitleniyordu (kimlik listesi esigini asan buyuk veri setlerinde).
    """
    m = durum.get("meta") or {}
    korunan = {x for x in (m.get("target"), m.get("id"), m.get("donem")) if x}
    if ((durum.get("bolme") or {}).get("kalici") == "kolon"
            or SPLIT_KOLON in (durum.get("veri_seti_kolonlari") or [])):
        korunan.add(SPLIT_KOLON)
    else:
        # Kalicilik bicimi bilinmiyorsa da guvenli taraf: kolon varsa koru.
        korunan.add(SPLIT_KOLON)
    return korunan


# Analiz Merkezi tablolarinda gosterilen satir sayisi. TAM tablo oturum
# JSON'una YAZILMAZ (1.000+ kolonda dosya sismesi olur); tam hali her zaman
# dataset'e / yedek CSV'ye yazilir, oturumda yalnizca bu ilk N satir durur.
PANEL_SATIR = 20

# Null oranina gore kova sinirlari (VERI / EKSIK DEGER sekmesi ozeti).
NULL_AZ = 0.05


def _eksik_ozeti(tablo, satir):
    """profil_cikar tablosundan EKSIK DEGER sekmesinin beslendigi ozet.

    Doner: (ilk20, null_ozet, ek_alanlar). tablo NULL_RATIO'ya gore
    zaten azalan sirali geldigi icin ilk N satir "en cok bos" olanlardir.
    """
    ilk20, ozet = [], {"hic_null_yok": 0, "az": 0, "orta": 0, "asiri": 0}
    toplam_null, null_kolon, en_yuksek, en_yuksek_kolon = 0, 0, 0.0, None

    for _, r in tablo.iterrows():
        oran = float(r["NULL_RATIO"] or 0.0)
        adet = int(r["NULL_COUNT"] or 0)
        toplam_null += adet
        if adet:
            null_kolon += 1
        if oran > en_yuksek:
            en_yuksek, en_yuksek_kolon = oran, str(r["FEATURE"])
        if oran <= 0:
            ozet["hic_null_yok"] += 1
        elif oran <= NULL_AZ:
            ozet["az"] += 1
        elif oran <= sfa_mod.NULL_ESIK:
            ozet["orta"] += 1
        else:
            ozet["asiri"] += 1

    for _, r in tablo.head(PANEL_SATIR).iterrows():
        ilk20.append({
            "FEATURE": str(r["FEATURE"]),
            "TYPE": str(r["TYPE"]),
            "NULL_COUNT": int(r["NULL_COUNT"] or 0),
            "NULL_RATIO": round(float(r["NULL_RATIO"] or 0.0), 4),
            "UNIQUE": int(r["UNIQUE"] or 0),
            "DURUM": str(r["DURUM"]),
        })

    kolon = int(len(tablo))
    hucre = float(satir) * kolon
    ek = {
        "profil_kolon": kolon,
        "null_oran": round(toplam_null / hucre, 4) if hucre else None,
        "null_kolon_adet": null_kolon,
        "null_maks": round(en_yuksek, 4),
        "null_maks_kolon": en_yuksek_kolon,
        "asiri_null_adet": ozet["asiri"],
    }
    return ilk20, ozet, ek


def _sfa_ilk20(tablo):
    """sfa_calistir tablosunun IV'ye gore ilk N satiri (SFA sekmesi)."""
    if tablo is None or not len(tablo):
        return []
    satirlar = []
    for _, r in tablo.head(PANEL_SATIR).iterrows():
        iv, c = r.get("IV"), r.get("C_VALUE")
        satirlar.append({
            "FEATURE": str(r["FEATURE"]),
            "IV": None if pd.isna(iv) else round(float(iv), 4),
            "C_VALUE": None if pd.isna(c) else round(float(c), 4),
            "SFA_RESULT": str(r.get("SFA_RESULT") or ""),
            "NOT": str(r.get("NOT") or ""),
        })
    return satirlar


def _atlanan_notu(ozet, baslik):
    """sfa/stabilite ciktisindaki ATLANDI degiskenleri gorunur kilar."""
    atlanan = ozet.get("atlanan") or []
    if not atlanan:
        return ""
    return "\n\n%s\n  (ölçüm yapılamadı: bu değişkenler sessizce kaybolmadı, " \
           "baz sette korunuyorlar)" % _liste(baslik, atlanan, 12)


# ===========================================================================
# FAZ 02-05 — her modda ayni (onceki surumden degismedi)
# ===========================================================================
def veri_profili_plan(durum):
    return ("Veri setini kolon kolon inceleyeceğim. Bu adımda hedefle "
            "ilişkiye bakmıyorum; yalnızca verinin kendi durumunu "
            "çıkarıyorum:\n\n"
            "  • eksik değer sayısı ve oranı\n"
            "  • tekil değer sayısı ve kardinalite\n"
            "  • sabit ya da neredeyse sabit kolonlar\n"
            "  • kimlik benzeri kolonlar\n\n"
            "%s kolon taranacak. Başlayalım mı?" % _sayi(_kolon_sayisi(durum)))

def veri_profili_uygula(durum):
    df = modelleme_df(durum)
    m = durum["meta"]
    haric = set(durum.get("haric_kolonlar") or []) | {m.get("target"), m.get("id"), m.get("donem")}

    tablo, teshis = sfa_mod.profil_cikar(df, haric=haric)
    yazildi, yedek = _yaz("%s_PROFIL" % durum["veri_seti"], tablo, "/veri_profili.parquet")

    p = durum.get("profil") or {}
    p["profil_teshis"] = teshis
    p["profil_dataset"] = yazildi

    # Feature tablosunun kolon ozeti: veri seti secilirken cikarilmisti,
    # burada tekil sayisi ve kesin null orani ile tamamlaniyor. Ozet hic
    # yoksa (eski oturum) su an okunan tablodan uretiliyor.
    if not p.get("kolon_ozet"):
        p["kolon_ozet"] = kolon_ozeti_cikar(df)
    p["kolon_ozet"] = kolon_ozeti_tamamla(p, tablo, df)

    # EKSIK DEGER sekmesi: yalnizca ilk 20 satir + dagilim ozeti oturuma
    # yazilir; tam tablo yukarida dataset'e / yedege yazildi.
    ilk20, null_ozet, ek = _eksik_ozeti(tablo, p.get("satir") or len(df))
    p["eksik_ilk20"] = ilk20
    p["null_ozet"] = null_ozet
    p.update(ek)
    durum["profil"] = p

    return ("Profil çıkarıldı. %s kolon incelendi, %s tanesi sorunsuz.\n\n"
            "TEKNİK KUSUR TESPİT EDİLENLER\n%s\n\n%s\n\n%s\n\n%s\n\n"
            "Bu kolonlar analitik baz sette düşürülecek. Tam tablo %s."
            % (_sayi(len(tablo)), _sayi(len(teshis["temiz"])),
               _liste("  Eksik oranı %%50 üstünde:", teshis["cok_bos"], 8),
               _liste("  Sabit ya da tek değerli:", teshis["sabit"], 8),
               _liste("  Kimlik benzeri:", teshis["kimlik_gibi"], 8),
               _liste("  Kardinalitesi aşırı yüksek:", teshis["yuksek_kardinalite"], 8),
               _nerede(yazildi, yedek)))

def sfa_plan(durum):
    p = durum.get("profil") or {}
    temiz = len((p.get("profil_teshis") or {}).get("temiz") or [])
    return ("Profili geçen %s değişkenin hedefle tek başına ilişkisini "
            "ölçeceğim:\n\n"
            "  • IV: bilgi değeri         (eşik > %s)\n"
            "  • C-value: tek değişkenli AUC   (eşik > %s)\n"
            "  • eksik değer doldurma ve kodlama kararı\n"
            "  • hedefe göre aralık önerisi: batma oranı artan, azalan ya da U "
            "şeklinde; her aralıkta geliştirme satırlarının en az %%5'i\n\n"
            "SIZINTI SINIRI: hangi satırda ne yapılıyor\n"
            "  • medyan doldurma değeri   : yalnızca geliştirme satırlarından "
            "öğrenilir (%s satır)\n"
            "  • binleme sınırları        : yalnızca geliştirme satırlarından "
            "öğrenilir, tüm satırlara uygulanır\n"
            "  • IV ve C-value ölçümü     : yalnızca geliştirme satırlarında "
            "yapılır\n"
            "  • kategorik hedef oranı    : geliştirme içinde parça dışı "
            "kodlanır, kodlama ve ölçüm aynı satırda yapılmaz\n\n"
            "Yani test satırları skoru hiç görmez: testte güçlü ama "
            "geliştirmede sinyalsiz bir değişken PASS alamaz.\n\n"
            "%s seviyeden fazla kategorik değişkenler ölçüm dışı bırakılır "
            "(ATLANDI) ve size ayrıca listelenir.\n\n"
            "SFA bir eleme kuralı değil: FAIL alan değişken çok değişkenli "
            "modelde anlamlı olabilir.\n\nBaşlayalım mı?"
            % (_sayi(temiz), _ond(sfa_mod.IV_ESIK, 2), _ond(sfa_mod.C_ESIK, 2),
               _sayi((durum.get("bolme") or {}).get("train_satir", 0)),
               _sayi(sfa_mod.KATEGORIK_MAX)))

def _buyuk_veri_engeli(durum, adim):
    """SFA ve aralik hesabi su an pandas'ta: tablo webapp'e tam okunur.
    Veri seti motor esiginin (bkz. motor.py) ustundeyse bellek tasmasin
    diye adim acik bir mesajla durur."""
    from fe_agent import motor
    from fe_agent.akis_durum import AdimHatasi, modelleme_kaynagi
    ad, _amp = modelleme_kaynagi(durum)
    secilen, toplam = motor.sec([ad])
    if secilen == motor.SPARK:
        raise AdimHatasi(
            "%s bu veri setinde henüz çalıştırılamıyor: veri seti büyük "
            "(%s) ve bu adımın Spark sürümü hazır değil. Pandas sınırı "
            "amp_pandas_sinir_gb proje değişkeniyle yükseltilebilir, ama "
            "webapp belleği yetmezse adım yarıda kalır."
            % (adim, motor.boyut_metni(toplam)))


def sfa_uygula(durum):
    _buyuk_veri_engeli(durum, "Tek Değişken Analizi (SFA)")
    df = modelleme_df(durum)
    tr, _ = maskeler(durum, df)
    adaylar = (durum.get("profil", {}).get("profil_teshis") or {}).get("temiz") or []

    tablo, ozet = sfa_mod.sfa_calistir(df, durum["meta"]["target"], adaylar,
                                       train_maske=tr)
    # HEDEFE GORE ARALIK ONERILERI (kullanici karari: SFA bu sureci de
    # kapsar). Tam tabloya da iki kolon eklenir.
    ozet["aralik"] = _aralik_hesapla(durum, df, durum["meta"]["target"], adaylar,
                                     ozet.get("iv_skorlari"))
    try:
        ar = json.loads(_dosya_metni(ozet["aralik"]["dosya"]) or "{}")
    except Exception:
        ar = {}
    if len(tablo):
        tablo["EGILIM"] = tablo["FEATURE"].map(lambda k: (ar.get(str(k)) or {}).get("sekil"))
        tablo["ARALIK_SAYISI"] = tablo["FEATURE"].map(
            lambda k: (ar.get(str(k)) or {}).get("aralik_sayisi"))
    yazildi, yedek = _yaz("%s_SFA" % durum["veri_seti"], tablo, "/sfa_tablosu.parquet")
    ozet["tablo_dataset"] = yazildi
    # SFA sekmesi: IV'ye gore ilk 20 satir (tam tablo dataset'te kalir).
    ozet["ilk20"] = _sfa_ilk20(tablo)
    durum["sfa"] = ozet

    satirlar = ["  %-30s %-12s IV %-7s C %-7s %s"
                % (str(r["FEATURE"])[:30], r["TYPE"], _ond(r["IV"], 3),
                   _ond(r["C_VALUE"], 3), r["SFA_RESULT"])
                for _, r in tablo.head(12).iterrows()]

    # Olcum yapilamayan (ATLANDI) degiskenler sessizce kaybolmasin:
    # 50+ seviyeli kategorikler (il, meslek kodu vb.) burada gorunur kalir.
    atlanan_not = _atlanan_notu(
        ozet, "ÖLÇÜLEMEYEN: %s seviyeden fazla kategorik (ATLANDI):"
        % _sayi(sfa_mod.KATEGORIK_MAX))

    # NOT kolonu dolu satirlar: IV'si guvenilmez bulunanlar
    notlu = 0
    if len(tablo) and "NOT" in tablo.columns:
        notlu = int(sum(1 for _, r in tablo.iterrows()
                        if str(r.get("NOT") or "").strip()
                        and r.get("SFA_RESULT") != "ATLANDI"))
    not_uyari = ("\n\n%s değişkende dağılım yığılmış olduğu için IV güvenilmez "
                 "bulundu; tablodaki NOT kolonunda gerekçesi yazıyor."
                 % _sayi(notlu)) if notlu else ""

    a = ozet.get("aralik") or {}
    aralik_not = ("\n\nARALIK ÖNERİLERİ\n"
                  "  Öneri Olan Değişken : %s\n"
                  "  Hassas Değişken : %s\n"
                  "  Sıralaması Diğer Setlerde Korunmayan : %s\n"
                  "  Eksik Değer Notu Olan : %s\n"
                  "Ayrıntılar sağdaki Değişken Analizi sekmesinde."
                  % (_sayi(a.get("onerilen", 0)),
                     ", ".join(a.get("hassas") or []) or "yok",
                     _sayi(len(a.get("tutarsiz") or [])),
                     _sayi(len(a.get("eksik_notu") or []))))
    return ("Analiz tamamlandı. %s değişken ölçüldü, %s tanesi PASS.\n\n"
            "BİLGİ DEĞERİNE GÖRE İLK 12\n%s\n\n%s%s%s\n\nTam tablo %s.%s"
            % (_sayi(ozet["analiz_edilen"]), _sayi(ozet["pass_adet"]),
               "\n".join(satirlar) or "  (tablo boş)",
               _liste("Sızıntı şüphesi (C-value > 0,95):", ozet["sizinti"], 8),
               atlanan_not, not_uyari,
               _nerede(yazildi, yedek), aralik_not))

def _psi_olculur_mu(durum):
    """PSI hangi sete karsi olculecek? Doner: "test" | None.

    Ayri bir OOT seti YOK: zamansal testte test ZATEN OOT'dur. Bu yuzden
    karsilastirma her zaman gelistirme ↔ test.

    Iki bolmede ayni hesap FARKLI soruyu cevaplar ve ikisi de degerlidir:
      zamansal -> test ileri donemdir; olculen sey ZAMAN kaymasidir.
      rastgele -> test ayni donemden gelir; olculen sey BOLMENIN
                  dengesizligidir ve ~0 beklenir. Sifirdan uzak cikmasi
                  bolmenin kendisinde bir sorun oldugunu soyler.
    Eskiden rastgele bolmede adim tamamen atlaniyordu; o kontrolu de
    kaybetmemek icin artik olculuyor, plan metni hangi soruyu
    cevapladigini yaziyor."""
    b = durum.get("bolme") or {}
    # Satir SAYIMINA baglanmiyoruz: sayim yalnizca bolme adimi calisinca
    # yaziliyor ve ona bagli kalmak, bolmesi belli ama sayimi kaydedilmemis
    # bir oturumda adimi sessizce atlatiyordu. Zamansal bolme ayrica
    # deterministiktir, kalici kayit bile gerektirmez. Test setinin fiilen
    # bos olup olmadigi maske hesaplandiktan SONRA denetleniyor.
    if (bolme_ayarlari(durum)["test_tanim"] == "zamansal"
            or b.get("kalici") or (b.get("satir") or {}).get("test")):
        return "test"
    return None


def stabilite_plan(durum):
    hedef_set = _psi_olculur_mu(durum)
    if hedef_set is None:
        return ("Test seti henüz ayrılmadığı için PSI hesaplanamaz.\n\n"
                "Adımı geçmek için onaylayın.")
    return ("Değişkenlerin zaman içinde kayıp kaymadığını ölçeceğim.\n\n"
            "  • PSI: popülasyon stabilite indeksi (eşik < %s)\n"
            "  • Geliştirme dağılımı referans, %s ile karşılaştırılır\n\n"
            "PSI hedefle ilişkiyi değil, değişkenin kendi davranışının "
            "kararlılığını ölçer.\n\nÇalıştıralım mı?"
            % (_ond(sfa_mod.PSI_ESIK, 2), hedef_set.upper()))

def stabilite_uygula(durum):
    hedef_set = _psi_olculur_mu(durum)
    if hedef_set is None:
        durum["stabilite"] = {"atlandi": True}
        return ("Stabilite analizi atlandı; karşılaştırılacak test seti yok.")

    df = modelleme_df(durum)
    s = setler(durum, df)
    if not int(s["test"].sum()):
        durum["stabilite"] = {"atlandi": True}
        return "Stabilite analizi atlandı; test setinde satır yok."
    adaylar = (durum.get("profil", {}).get("profil_teshis") or {}).get("temiz") or []

    tablo, ozet = sfa_mod.stabilite_calistir(df, adaylar, s["egitim"],
                                             s[hedef_set])
    if tablo is None:
        durum["stabilite"] = {"atlandi": True}
        return "Stabilite analizi yapılamadı."

    yazildi, yedek = _yaz("%s_PSI" % durum["veri_seti"], tablo, "/stabilite.parquet")
    ozet["tablo_dataset"] = yazildi
    ozet["karsilastirma"] = "eğitim ↔ test"
    # Olcumun NE ANLAMA geldigi bolmeye gore degisir; rapor bunu yazmali
    # yoksa rastgele bolmedeki ~0 PSI "model saglam" diye okunur.
    ozet["olcum_turu"] = ("zaman kayması"
                          if bolme_ayarlari(durum)["test_tanim"] == "zamansal"
                          else "bölme dengesi")
    durum["stabilite"] = ozet

    satirlar = ["  %-34s PSI %s" % (c[:34], _ond(v, 3)) for c, v in ozet["en_kotu"]]

    # ATLANDI satirlari: bin bazli PSI anlamli olmayan yuksek seviyeli
    # kategorikler. Bunlar KAYAN degil; duserulmuyorlar, sadece olculemedi.
    atlanan_not = _atlanan_notu(
        ozet, "ÖLÇÜLEMEYEN: %s seviyeden fazla kategorik (ATLANDI):"
        % _sayi(sfa_mod.KATEGORIK_MAX))

    return ("Ölçüm tamamlandı. %s değişkenin %s tanesi kararlı.\n\n"
            "EN ÇOK KAYAN 10\n%s\n\n"
            "Kayma gösteren %s değişken baz sette düşürülecek.%s\nTam tablo %s."
            % (_sayi(ozet["olculen"]), _sayi(ozet["stabil"]),
               "\n".join(satirlar) or "  (yok)", _sayi(len(ozet["kayan"])),
               atlanan_not, _nerede(yazildi, yedek)))

def _dusurulecek_kume(durum):
    """Baz sette DUSURULECEK kolonlarin tam kumesi.

    Teshis listelerine ek olarak durum["haric_kolonlar"] da buraya girer:
    surec disinda tutulan (Mod A'da sozlukte karsiligi olmayan) kolonlar
    profilden de haric tutuldugu icin hicbir teshis listesinde gorunmez;
    yalnizca teshislere bakan eski surum bu kolonlari final modele
    sokuyordu. Hedef / kimlik / donem kolonlari asla dusurulmez.
    Doner: (tum_dusurulecek, teshis_kaynakli, sozlukte_tanimsiz)
    """
    t = (durum.get("profil") or {}).get("profil_teshis") or {}
    s = durum.get("sfa") or {}
    st = durum.get("stabilite") or {}
    korunan = _meta_kolonlar(durum)

    teshis = set(
        (t.get("cok_bos") or []) + (t.get("sabit") or []) +
        (t.get("kimlik_gibi") or []) + (t.get("yuksek_kardinalite") or []) +
        (s.get("sizinti") or []) + (st.get("kayan") or [])) - korunan
    tanimsiz = set(durum.get("haric_kolonlar") or []) - korunan - teshis
    return sorted(teshis | tanimsiz), sorted(teshis), sorted(tanimsiz)


def _plan_satiri(durum):
    plan = durum.get("donusum_plani") or []
    if not plan:
        return ""
    n_ar = sum(1 for p in plan if p["tur"] == "aralik")
    return ("  ÜRETİLECEK (Planlanan Dönüşümler)\n"
            "    %s aralık kolonu, %s eksik işareti kolonu\n\n"
            % (_sayi(n_ar), _sayi(len(plan) - n_ar)))


def baz_plan(durum):
    t = (durum.get("profil") or {}).get("profil_teshis") or {}
    s = durum.get("sfa") or {}
    st = durum.get("stabilite") or {}

    dusur, _teshis, tanimsiz = _dusurulecek_kume(durum)
    durum["_dusurulecek"] = dusur

    tanimsiz_not = ""
    if tanimsiz:
        tanimsiz_not = ("\n\n%s\n  Bu kolonlar süreç dışında tutulduğu için "
                        "profil ve SFA'ya hiç girmedi; baz sete de "
                        "alınmayacaklar."
                        % _liste("  SÜREÇ DIŞI: sözlükte tanımı olmayan %s kolon:"
                                 % _sayi(len(tanimsiz)), tanimsiz, 10))

    return ("Analitik baz seti oluşturacağım: üretim ve modelleme bu "
            "dondurulmuş set üzerinde yapılacak.\n\n"
            "  DÜŞÜRÜLECEK: %s kolon\n"
            "    eksik %s · sabit %s · kimlik %s · kardinalite %s · "
            "sızıntı %s · kararsız %s · süreç dışı %s\n\n"
            "  DOLDURULACAK\n"
            "    sayısal boşluklar, geliştirme setinin medyanıyla\n\n"
            "%s"
            "  YAZILACAK\n    %s_BAZ%s\n\n"
            "Oluşturayım mı?"
            % (_sayi(len(dusur)),
               _sayi(len(t.get("cok_bos") or [])), _sayi(len(t.get("sabit") or [])),
               _sayi(len(t.get("kimlik_gibi") or [])),
               _sayi(len(t.get("yuksek_kardinalite") or [])),
               _sayi(len(s.get("sizinti") or [])), _sayi(len(st.get("kayan") or [])),
               _sayi(len(tanimsiz)), _plan_satiri(durum),
               durum["veri_seti"], tanimsiz_not))

def _donusumleri_uygula(durum, df):
    """durum["donusum_plani"] -> df'ye yeni kolonlar (yerinde).
    Doner: (yeni kolon adlari, ham hali cikacak hassas kolonlar)."""
    from fe_agent import aralik as aralik_mod
    yeni, hassas = [], []
    for p in durum.get("donusum_plani") or []:
        ad = p.get("ad")
        if ad not in df.columns:
            continue
        hedef = "%s_%s" % (ad, "ARALIK" if p["tur"] == "aralik" else "EKSIK")
        df[hedef] = aralik_mod.uygula_seri(df[ad], p)
        yeni.append(hedef)
        if p["tur"] == "aralik" and p.get("hassas"):
            hassas.append(ad)
    return yeni, sorted(set(hassas) - _meta_kolonlar(durum))


def baz_uygula(durum):
    df = modelleme_df(durum)
    tr, _ = maskeler(durum, df)

    # Plan adimi atlanmis olabilir; kumeyi burada da hesapla (savunma).
    tum, _teshis, tanimsiz = _dusurulecek_kume(durum)
    tum = sorted((set(tum) | set(durum.get("_dusurulecek") or []))
                 - _meta_kolonlar(durum))
    dusur = [c for c in tum if c in df.columns]
    tanimsiz_dusen = [c for c in tanimsiz if c in df.columns]

    # PLANLANAN DONUSUMLER (Aralık Önerileri adiminda kabul edilenler).
    # Eksik degerler doldurulmadan ONCE: eksik isareti ve "Eksik" araligi
    # ancak ham eksiklerden uretilebilir. Hassas degiskende aralik kabul
    # edildiyse ham kolon baz setten cikar.
    yeni_kolonlar, hassas_cikan = _donusumleri_uygula(durum, df)
    dusur = sorted(set(dusur) | {c for c in hassas_cikan if c in df.columns})
    df = df.drop(columns=dusur)

    doldurma = {}
    for k in df.select_dtypes(include=[np.number]).columns:
        med = df.loc[tr, k].median()
        if not pd.isna(med):
            df[k] = df[k].fillna(med)
            doldurma[k] = round(float(med), 4)

    m = durum["meta"]
    baz_kolonlar = [c for c in df.columns
                    if c not in (m.get("target"), m.get("id"), m.get("donem"))]

    # Hedef veri seti akista tanimli degilse adim COKMESIN: hesap korunur,
    # tablo yedek dosyaya yazilir ve kullaniciya acik bir uyari verilir.
    baz_ds = "%s_BAZ" % durum["veri_seti"]
    # Veri seti Flow'da yoksa webapp kurar (kullanici Flow'a bir sey eklemez;
    # kaynak tablonun baglantisinda Parquet). Kurulamazsa eskisi gibi yedek
    # dosyaya yazilir ve uyari verilir.
    try:
        from fe_agent import spark_is
        spark_is.veri_seti_hazirla(baz_ds, durum["veri_seti"])
    except Exception:
        pass
    yazildi, yedek = _yaz(baz_ds, df, "/analitik_baz_set.parquet")

    durum["haric_kolonlar"] = sorted(set(durum.get("haric_kolonlar") or []) | set(dusur))
    durum["baz"] = {"yeni_kolonlar": yeni_kolonlar,
                    "dataset": yazildi, "doldurma": "medyan (geliştirme seti)",
                    "doldurma_degerleri": doldurma,
                    "kolon": int(df.shape[1]), "kolonlar": baz_kolonlar}

    tanimsiz_not = ("\n%s kolon sözlükte tanımı olmadığı (süreç dışı) için "
                    "çıkarıldı: bu kolonlar artık final modele giremez."
                    % _sayi(len(tanimsiz_dusen))) if tanimsiz_dusen else ""

    if not yazildi:
        durum["baz"]["hata"] = ("'%s' veri setine yazılamadı" % baz_ds)
        return ("Analitik baz set HESAPLANDI ama '%s' veri setine yazılamadı.\n"
                "Tablo geçici olarak PROJE_HAFIZASI%s dosyasına kaydedildi.\n\n"
                "%s kolon düşürüldü, %s kolonda eksik değerler dolduruldu.%s\n\n"
                "Dataiku akışında '%s' veri setini oluşturup bu adımı yeniden "
                "çalıştırın; aksi halde sonraki adımlar kaynak veri setiyle "
                "devam eder ve bu temizlik uygulanmamış olur."
                % (baz_ds, yedek, _sayi(len(dusur)), _sayi(len(doldurma)),
                   tanimsiz_not, baz_ds))

    yeni_not = ("\n%s yeni kolon planlanan dönüşümlerden üretildi%s."
                % (_sayi(len(yeni_kolonlar)),
                   ("; hassas olduğu için ham hâli çıkarılan: %s" % ", ".join(hassas_cikan))
                   if hassas_cikan else "")) if yeni_kolonlar else ""
    return ("Analitik baz set hazır: %s, %s kolon.\n"
            "%s kolon düşürüldü, %s kolonda eksik değerler dolduruldu.%s%s"
            % (baz_ds, _sayi(df.shape[1]), _sayi(len(dusur)),
               _sayi(len(doldurma)), tanimsiz_not, yeni_not))


# ===========================================================================
# ADIM - ARALIK ONERILERI  (SFA'nin devami)
# ===========================================================================
# Kullanici karari: oneriler yapay zekayla degerlendirilebilmeli ama bunu
# kullanici o anda secer ("yapılmasını istiyor musunuz diye sorsun").
# Kabul / ret sozluk tanimlari kartindaki gibi satir basina kutuyla.
# Kabul edilenler durum["donusum_plani"]'na yazilir; Analitik Baz Set
# adiminda yeni kolon olarak uretilir.
ARALIK_AI_EVET = "aralık: yapay zekâ"
ARALIK_AI_HAYIR = "aralık: kural"
ARALIK_KARAR_ONEK = "aralık kararları:"

ARALIK_SECENEKLERI = [
    {"deger": ARALIK_AI_EVET, "rozet": "1", "baslik": "Yapay Zekâ Değerlendirsin",
     "aciklama": "Her öneriyi metrik kontrolleriyle birlikte yapay zekâ "
                 "inceler; uygulanıp uygulanmamasını gerekçesiyle önerir. "
                 "Yapay zekâ yalnızca aralık tablolarını görür, ham veriyi görmez."},
    {"deger": ARALIK_AI_HAYIR, "rozet": "2", "baslik": "Kural Tabanlı Kalsın",
     "aciklama": "Öneriler hesaplanan metriklere göre işaretlenir; yapay "
                 "zekâ çağrılmaz."},
]


def _aralik_adaylari(durum):
    """Karar kartina girecek satirlar: aralik onerisi olanlar ve eksik
    degeri farkli risk tasiyanlar."""
    tum = aralik_oku(durum)
    satirlar = []
    for ad, v in tum.items():
        kont = aralik_mod.kontroller(v)
        if v.get("aralik_sayisi", 0) > 1:
            satirlar.append({"ad": ad, "tur": "aralik", "v": v, "kontroller": kont})
        if v.get("notlar"):
            satirlar.append({"ad": ad, "tur": "eksik", "v": v, "kontroller": []})
    satirlar.sort(key=lambda s: -((s["v"].get("ayri") or {}).get("iv") or 0))
    return satirlar


def _ai_degerlendir(durum, adaylar):
    from fe_agent import llm as llm_mod
    aciklama = _aciklamalar(durum)
    girdi, gorulen = [], set()
    for a in adaylar:
        if a["ad"] in gorulen:
            continue
        gorulen.add(a["ad"])
        v = a["v"]
        girdi.append({
            "ad": a["ad"], "aciklama": aciklama.get(a["ad"], ""), "tur": v.get("tur"),
            "sekil": v.get("sekil"), "iv": (v.get("ayri") or {}).get("iv"),
            "araliklar": [(s["etiket"], "%.1f%%" % (100 * s["pay"]), "%.2f%%" % (100 * s["oran"]))
                          for s in (v.get("ayri") or {}).get("satirlar") or []],
            "tutarlilik": v.get("tutarlilik"), "hassas": v.get("hassas"),
            "notlar": v.get("notlar"), "kontroller": aralik_mod.kontroller(v)})
    return llm_mod.aralik_degerlendir(girdi)


def _aralik_karti(durum, adaylar):
    ai = durum.get("_aralik_ai") or {}
    sonuc = ai.get("sonuc") or {}
    onceki = durum.get("donusum_plani")
    onceki_secim = ({(p["ad"], p["tur"]) for p in onceki}
                    if isinstance(onceki, list) else None)
    satirlar = []
    for a in adaylar:
        v = a["v"]
        if a["tur"] == "eksik":
            oneri = (v.get("notlar") or [""])[0]
            varsayilan = True
        else:
            oneri = v.get("oneri") or ""
            varsayilan = all(k["gecti"] for k in a["kontroller"])
        karar = sonuc.get(a["ad"]) if ai.get("acik") else None
        if karar:
            varsayilan = karar["karar"] == "uygula"
        if onceki_secim is not None:
            varsayilan = (a["ad"], a["tur"]) in onceki_secim
        satirlar.append({
            "ad": a["ad"], "tur": a["tur"],
            "donusum": "Aralık" if a["tur"] == "aralik" else "Eksik İşareti",
            "egilim": v.get("sekil") if a["tur"] == "aralik" else "-",
            "oneri": oneri,
            "gerekce": (karar or {}).get("gerekce") or "",
            "kaynak": "yapay_zeka" if karar else "kural",
            "kontroller": a["kontroller"],
            "hassas": v.get("hassas") or "",
            "secili": bool(varsayilan),
        })
    durum["_secim_alani"] = {
        "tip": "aralik_karar",
        "baslik": "Aralık Önerileri",
        "aciklama": ("Uygulanacak önerileri işaretleyin. İşaretlenenler "
                     "Analitik Baz Set adımında yeni kolon olarak üretilir; "
                     "orijinal kolon korunur (hassas değişkende çıkarılır)."),
        "kaynak": "yapay_zeka" if ai.get("acik") else "kural",
        "ai_hata": ai.get("hata") or "",
        "satirlar": satirlar,
        "sablon": ARALIK_KARAR_ONEK + " {liste}",
    }


def aralik_girdi(durum, mesaj, yeniden_sor=False):
    metin = (mesaj or "").strip()
    adaylar = _aralik_adaylari(durum)
    if not adaylar:
        durum["donusum_plani"] = []
        durum["_secim_alani"] = None
        return True, None

    if metin.lower().startswith(ARALIK_KARAR_ONEK) and not yeniden_sor:
        secilen = set()
        for parca in metin[len(ARALIK_KARAR_ONEK):].split(","):
            ad, _, tur = parca.strip().rpartition(":")
            if ad:
                secilen.add((ad.strip(), tur.strip()))
        plan = []
        for a in adaylar:
            if (a["ad"], a["tur"]) not in secilen:
                continue
            v = a["v"]
            kayit = {"ad": a["ad"], "tur": a["tur"], "hassas": v.get("hassas") or ""}
            if a["tur"] == "aralik":
                kayit.update({"kesimler": v.get("kesimler"), "gruplar": v.get("gruplar"),
                              "etiketler": v.get("etiketler"), "sekil": v.get("sekil"),
                              "aralik_sayisi": v.get("aralik_sayisi")})
            plan.append(kayit)
        durum["donusum_plani"] = plan
        durum["_secim_alani"] = None
        return True, None

    if metin in (ARALIK_AI_EVET, ARALIK_AI_HAYIR) and not yeniden_sor:
        ai = {"acik": metin == ARALIK_AI_EVET}
        if ai["acik"]:
            sonuc, hata = _ai_degerlendir(durum, adaylar)
            ai.update(sonuc=sonuc, hata=hata)
        durum["_aralik_ai"] = ai
        durum["_secenekler"] = []
        _aralik_karti(durum, adaylar)
        return False, ""

    if durum.get("_aralik_ai") is not None and not yeniden_sor:
        _aralik_karti(durum, adaylar)
        return False, ""

    # Ilk giris ya da "Geri Dön": once yapay zeka sorusu.
    durum.pop("_aralik_ai", None)
    durum["_secim_alani"] = None
    durum["_secenekler"] = ARALIK_SECENEKLERI
    n_aralik = sum(1 for a in adaylar if a["tur"] == "aralik")
    n_eksik = sum(1 for a in adaylar if a["tur"] == "eksik")
    return False, ("SFA %s değişken için aralık, %s değişken için eksik değer "
                   "işareti önerdi. Önerileri yapay zekâ değerlendirsin mi?"
                   % (_sayi(n_aralik), _sayi(n_eksik)))


def aralik_uygula(durum):
    plan = durum.get("donusum_plani") or []
    n_ar = sum(1 for p in plan if p["tur"] == "aralik")
    n_ek = sum(1 for p in plan if p["tur"] == "eksik")
    hassas = sorted({p["ad"] for p in plan if p.get("hassas") and p["tur"] == "aralik"})
    satirlar = ["Planlanan dönüşümler kaydedildi.",
                "  Aralık : %s değişken" % _sayi(n_ar),
                "  Eksik İşareti : %s değişken" % _sayi(n_ek)]
    if hassas:
        satirlar.append("  Ham Hâli Çıkarılacak : %s" % ", ".join(hassas))
    satirlar.append("Yeni kolonlar Analitik Baz Set adımında üretilecek.")
    return "\n".join(satirlar)
