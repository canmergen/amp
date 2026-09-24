# -*- coding: utf-8 -*-
"""fe_agent/akis_faz02.py - Faz 02 - Veri Anlama ve Hazirlama: profil, SFA, stabilite, baz set.

akis.py bolundu; bu dosya o bolumun aynisidir.
"""

import numpy as np
import pandas as pd
from fe_agent import sfa as sfa_mod

from fe_agent.akis_durum import (
    SPLIT_KOLON, _df_oku, _liste, _nerede, _ond, _sayi, _yaz,
    bolme_ayarlari, kolon_ozeti_cikar, kolon_ozeti_tamamla, maskeler,
    modelleme_df, setler,
)


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
    yazildi, yedek = _yaz("%s_PROFIL" % durum["veri_seti"], tablo, "/veri_profili.csv")

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
            "  • eksik değer doldurma ve kodlama kararı\n\n"
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

def sfa_uygula(durum):
    df = modelleme_df(durum)
    tr, _ = maskeler(durum, df)
    adaylar = (durum.get("profil", {}).get("profil_teshis") or {}).get("temiz") or []

    tablo, ozet = sfa_mod.sfa_calistir(df, durum["meta"]["target"], adaylar,
                                       train_maske=tr)
    yazildi, yedek = _yaz("%s_SFA" % durum["veri_seti"], tablo, "/sfa_tablosu.csv")
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

    return ("Analiz tamamlandı. %s değişken ölçüldü, %s tanesi PASS.\n\n"
            "BİLGİ DEĞERİNE GÖRE İLK 12\n%s\n\n%s%s%s\n\nTam tablo %s."
            % (_sayi(ozet["analiz_edilen"]), _sayi(ozet["pass_adet"]),
               "\n".join(satirlar) or "  (tablo boş)",
               _liste("Sızıntı şüphesi (C-value > 0,95):", ozet["sizinti"], 8),
               atlanan_not, not_uyari,
               _nerede(yazildi, yedek)))

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

    yazildi, yedek = _yaz("%s_PSI" % durum["veri_seti"], tablo, "/stabilite.csv")
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
            "  YAZILACAK\n    %s_BAZ%s\n\n"
            "Oluşturayım mı?"
            % (_sayi(len(dusur)),
               _sayi(len(t.get("cok_bos") or [])), _sayi(len(t.get("sabit") or [])),
               _sayi(len(t.get("kimlik_gibi") or [])),
               _sayi(len(t.get("yuksek_kardinalite") or [])),
               _sayi(len(s.get("sizinti") or [])), _sayi(len(st.get("kayan") or [])),
               _sayi(len(tanimsiz)),
               durum["veri_seti"], tanimsiz_not))

def baz_uygula(durum):
    df = modelleme_df(durum)
    tr, _ = maskeler(durum, df)

    # Plan adimi atlanmis olabilir; kumeyi burada da hesapla (savunma).
    tum, _teshis, tanimsiz = _dusurulecek_kume(durum)
    tum = sorted((set(tum) | set(durum.get("_dusurulecek") or []))
                 - _meta_kolonlar(durum))
    dusur = [c for c in tum if c in df.columns]
    tanimsiz_dusen = [c for c in tanimsiz if c in df.columns]
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
    yazildi, yedek = _yaz(baz_ds, df, "/analitik_baz_set.csv")

    durum["haric_kolonlar"] = sorted(set(durum.get("haric_kolonlar") or []) | set(dusur))
    durum["baz"] = {"dataset": yazildi, "doldurma": "medyan (geliştirme seti)",
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

    return ("Analitik baz set hazır: %s, %s kolon.\n"
            "%s kolon düşürüldü, %s kolonda eksik değerler dolduruldu.%s"
            % (baz_ds, _sayi(df.shape[1]), _sayi(len(dusur)),
               _sayi(len(doldurma)), tanimsiz_not))
