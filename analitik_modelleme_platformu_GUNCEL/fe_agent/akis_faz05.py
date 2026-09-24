# -*- coding: utf-8 -*-
"""fe_agent/akis_faz05.py - Faz 05 - Modelleme ve Finalizasyon: karsilastirma, algoritma, final.

akis.py bolundu; bu dosya o bolumun aynisidir.
"""

from fe_agent import model as model_mod
from fe_agent import kutuk as katalog_mod
from fe_agent import senaryo as senaryo_mod
from fe_agent import validasyon

from fe_agent.akis_durum import (
    BAZ_ADI, LINEAGE_ADI, _dataset_okunur_mu, _df_oku, _ond, _sayi, _yaz,
    GECERSIZ_BIRLESIM, bolme_ayarlari, bolme_uyarilari, katlar,
    setler,
)


# ===========================================================================
# KAYNAK SECIMI
# ===========================================================================
# Degisken uretimi hic calismadiysa _ENRICHED olusmaz; dogrudan okumak
# yakalanmamis istisna uretiyordu.
def _kaynak(durum):
    """Doner: (dataset_adi | None, zenginlestirilmis_mi)"""
    zengin = "%s_ENRICHED" % durum.get("veri_seti")
    if _dataset_okunur_mu(zengin):
        return zengin, True
    baz = (durum.get("baz") or {}).get("dataset") or durum.get("veri_seti")
    if baz and _dataset_okunur_mu(baz):
        return baz, False
    return None, False


_KAYNAK_YOK = ("Bu adımı çalıştıramadım: ne %s_ENRICHED ne de baz veri seti "
               "okunabiliyor.\n\nDeğişken üretimi adımlarında hiçbir değişken "
               "üretilmediyse zenginleştirilmiş veri seti oluşmaz. Önceki "
               "adıma dönebilir ya da bu adımı geçebilirsiniz.")

_ZENGIN_YOK = ("NOT: %s_ENRICHED veri seti bulunamadı; %s veri setiyle "
               "çalıştım. Yeni değişken üretilmediği için karşılaştırma "
               "yalnızca baz değişkenleri kapsıyor olabilir.")


def _guven_metni(delta, std, ga, basamak=4):
    """Delta'yi standart sapmasi ve guven araligiyla birlikte yazar."""
    if delta is None:
        return "-"
    metin = _ond(delta, basamak)
    if std is not None:
        metin += "  ±%s" % _ond(std, basamak)
    if ga and len(ga) == 2 and ga[0] is not None:
        metin += "  [%s; %s]" % (_ond(ga[0], basamak), _ond(ga[1], basamak))
    return metin


def _sifir_iceriyor(ga):
    return bool(ga) and len(ga) == 2 and ga[0] is not None and ga[1] is not None \
        and float(ga[0]) <= 0.0 <= float(ga[1])

def _bolme_ozeti(durum):
    """Senaryo konfigine giden bolme bilgisi.

    durum["bolme"]["set_kimlikleri"] 50 bine kadar kimlik tasiyabiliyor;
    konfig JSON'una gomulurse dosya sismesi ve senaryo tarafinda gereksiz
    yuk olur. Senaryonun ihtiyaci yalnizca bolme TURU ve sinirlari.
    """
    b = dict(durum.get("bolme") or {})
    kimlikler = b.pop("test_kimlikleri", None)
    setlik = b.pop("set_kimlikleri", None)
    if kimlikler is not None or setlik is not None:
        b["test_kimlik_sayisi"] = len(kimlikler or [])
        if isinstance(setlik, dict):
            b["set_kimlik_sayisi"] = {k: len(v or [])
                                      for k, v in setlik.items()}
        b["bolme_kaynagi"] = "kimlik listesi (durumda saklaniyor)"
    return b


def model_plan(durum):
    baz = (durum.get("baz") or {}).get("kolonlar") or []
    yeni = (durum.get("secim") or {}).get("secilen_liste") or []
    b = durum.get("bolme") or {}
    bolme_ad = ("zamansal - test dönemi %s" % b.get("oot_deger")) \
        if b.get("tur") == "zamansal" else "rastgele %%80 / %%20"
    return ("Asıl soruyu cevaplayacağız: ürettiğimiz değişkenler modele "
            "ölçülebilir katkı sağladı mı?\n\n"
            "  Baz model         : %s değişken\n"
            "  Zenginleştirilmiş : %s değişken   (+%s yeni)\n"
            "  Bölme             : %s\n"
            "  Rastgelelik tohumu: %d (ve sonraki %s tohum)\n"
            "  Metrikler         : ROC-AUC, Gini, KS\n\n"
            "GÜRÜLTÜ BANDI\n"
            "Tek koşudan çıkan fark, koşudan koşuya değişen gürültüyü "
            "taşıyamaz. Bu yüzden ölçüm %s farklı seed ile tekrarlanacak; "
            "farkın ortalaması, standart sapması ve %%95 güven aralığı "
            "birlikte raporlanacak. Güven aralığı sıfırı içeriyorsa katkı "
            "gürültüden ayırt edilemiyor demektir.\n\n"
            "Eğitim birkaç dakika sürebilir. Başlayalım mı?"
            % (_sayi(len(baz)), _sayi(len(baz) + len(yeni)), _sayi(len(yeni)),
               bolme_ad, model_mod.SEED, _sayi(max(model_mod.TEKRAR - 1, 0)),
               _sayi(model_mod.TEKRAR)))

def model_uygula(durum):
    kaynak, zengin = _kaynak(durum)
    if kaynak is None:
        durum["model"] = {"hata": "kaynak veri seti bulunamadı"}
        return _KAYNAK_YOK % durum.get("veri_seti")

    not_metni = "" if zengin else \
        ("\n\n" + _ZENGIN_YOK % (durum.get("veri_seti"), kaynak))

    df = _df_oku(kaynak)
    s = setler(durum, df)

    # Tekrarli olcum YALNIZCA egitim satirlarinda yapilir; test ve OOT
    # satirlari bu adima girmez. Bolme kimlik bazliysa tekrarli bolme de
    # gruplu olmali, yoksa ayni musteri iki tarafta kalir.
    a = bolme_ayarlari(durum)
    kimlik = (durum.get("bolme") or {}).get("kimlik_kolon") \
        or (durum.get("meta") or {}).get("id")
    grup = df[kimlik].astype(str) \
        if a["birim"] == "kimlik" and kimlik and kimlik in df.columns else None

    sonuc = model_mod.karsilastir(
        df, durum["meta"]["target"],
        baz_kolonlar=(durum.get("baz") or {}).get("kolonlar") or [],
        yeni_kolonlar=(durum.get("secim") or {}).get("secilen_liste") or [],
        oot_maske=s["test"],
        # Bolme TURU acikca bildirilir; modul maskenin dolulugundan cikarim
        # yapip rastgele bolmeyi "zamansal (OOT)" diye etiketlemesin.
        bolme_turu=(durum.get("bolme") or {}).get("tur"),
        egitim_maske=s["egitim"], grup=grup)

    durum["model"] = sonuc
    if sonuc.get("hata"):
        return "Karşılaştırmayı tamamlayamadım: %s%s" % (sonuc["hata"], not_metni)

    b, e, d = sonuc["baseline"], sonuc["enhanced"], sonuc["delta"]
    ds = sonuc.get("delta_std") or {}
    ga = sonuc.get("delta_guven_araligi") or {}

    auc_ga = ga.get("auc")
    # SIRA ONEMLI: once "karsilastirma yapildi mi", sonra "sonuc anlamli mi".
    # Yeni kolon yoksa iki model aynidir; delta sifir cikar ve guven araligi
    # [0,0] olur. Bunu gurultu yorumuna sokmak, hic yapilmamis bir olcum
    # hakkinda istatistiksel hukum kurmak demekti.
    if not sonuc.get("karsilastirilabilir", True):
        yorum = ("KARŞILAŞTIRMA YAPILAMADI. %s Katkı ölçümü için önce "
                 "değişken üretimi ve seçimi çalışmalı."
                 % sonuc.get("karsilastirma_notu", ""))
    elif d.get("auc") is None:
        yorum = "Fark ölçülemedi."
    elif _sifir_iceriyor(auc_ga):
        yorum = ("KARAR: Katkı gürültüden AYIRT EDİLEMİYOR. ROC-AUC farkının "
                 "%%95 güven aralığı sıfırı içeriyor; %s koşunun ortalaması "
                 "pozitif olsa bile bu fark rastlantıyla açıklanabilir." %
                 _sayi(sonuc.get("tekrar") or 0))
    elif d["auc"] > 0:
        yorum = ("KARAR: Yeni değişkenler ayrıştırma gücünü artırdı; güven "
                 "aralığı tamamen sıfırın üstünde, katkı gürültüden ayırt "
                 "edilebiliyor.")
    else:
        yorum = ("KARAR: Yeni değişkenler ayrıştırma gücünü DÜŞÜRDÜ; güven "
                 "aralığı tamamen sıfırın altında.")

    nan_not = ""
    if int(sonuc.get("hedef_nan_dusen") or 0) > 0:
        nan_not = ("\n\nHedefi boş olan %s satır eğitimden ve testten "
                   "düşürüldü (0 sınıfına yazılmadı)."
                   % _sayi(sonuc["hedef_nan_dusen"]))

    return ("KARŞILAŞTIRMA SONUCU\n"
            "  Bölme  : %s\n  Eğitim : %s satır      Test : %s satır\n"
            "  Tekrar : %s rastgelelik tohumu (%s)\n\n"
            "                    BAZ         ZENGİN      FARK (ort ± std [%%95 GA])\n"
            "  ROC-AUC           %-11s %-11s %s\n"
            "  Gini              %-11s %-11s %s\n"
            "  KS                %-11s %-11s %s\n\n"
            "  Değişken sayısı   %-11s %-11s %s\n\n"
            "FARK sütunu %s koşunun ORTALAMASIDIR; köşeli parantez %%95 güven "
            "aralığıdır.\n\n%s%s%s"
            % (sonuc["bolme"], _sayi(sonuc["egitim_satir"]),
               _sayi(sonuc["test_satir"]), _sayi(sonuc.get("tekrar") or 0),
               ", ".join(str(s) for s in (sonuc.get("seedler") or [])),
               _ond(b["auc"], 4), _ond(e["auc"], 4),
               _guven_metni(d.get("auc"), ds.get("auc"), ga.get("auc")),
               _ond(b["gini"], 4), _ond(e["gini"], 4),
               _guven_metni(d.get("gini"), ds.get("gini"), ga.get("gini")),
               _ond(b["ks"], 4), _ond(e["ks"], 4),
               _guven_metni(d.get("ks"), ds.get("ks"), ga.get("ks")),
               _sayi(sonuc["baz_kolon"]),
               _sayi(sonuc["baz_kolon"] + sonuc["yeni_kolon"]),
               "+%s" % _sayi(sonuc["yeni_kolon"]),
               _sayi(sonuc.get("tekrar") or 0), yorum, nan_not, not_metni))

# ===========================================================================
# ADIM 5.2: ALGORITMA SECIMI   (Dataiku senaryosunda calisir)
# ===========================================================================
ALGORITMALAR = ["Lojistik Regresyon", "Random Forest",
                "Gradient Boosting", "XGBoost"]

def _cv_katlari(durum):
    """(kat_listesi, notlar). Kaynak okunamazsa CV dogrulanamaz, (None, []).

    Katlar BURADA uretilir cunku secim yerinin gercekten var olup olmadigi
    ancak katlari kurmayi DENEYEREK anlasilir: kimlik bazli bolmede gruplu
    kat kurulamiyorsa CV kapanir ve secim yeri val'e (ya da hicbir yere)
    duser. "cv=kfold yazdiysa CV vardir" varsayimi, gruplamasiz katlarla
    sessizce devam etmek demekti."""
    kaynak, _zengin = _kaynak(durum)
    if kaynak is None:
        return None, []
    try:
        return katlar(durum, _df_oku(kaynak))
    except Exception:
        # Bolme henuz kalici degilse setler() acikca duruyor; bu adimin
        # metnini uretmek icin akisi durdurmaya gerek yok.
        return None, []


def _hiperparametre_secimi(durum):
    """(arama_yapilir_mi, secim_yeri_metni, uyari_metni).

    Hiperparametre ancak TEMIZ bir yerde secilebilir: ya egitim icinde CV
    ile ya da val setinde. Ikisi de yoksa arama yapilmaz - egitim setinde
    arama, secilen hiperparametreyi egitim gurultusune uydurur; test
    setinde arama test setini yakar."""
    a = bolme_ayarlari(durum)
    kat_listesi, kat_notlari = (None, [])
    if a["cv"] != "yok":
        kat_listesi, kat_notlari = _cv_katlari(durum)
        if kat_listesi is None or kat_listesi:
            n = len(kat_listesi) if kat_listesi else a["kat"]
            return True, ("eğitim seti içinde %s parçalı çapraz doğrulama"
                          % _sayi(n)), \
                " ".join(kat_notlari)
    if a["val_var"]:
        return True, "doğrulama seti", " ".join(kat_notlari)
    # Metinde arama YAPMIYORUZ: "SABİT".lower() Turkce'de "sabit" vermez
    # (noktali i), kural sessizce hic tetiklenmezdi. Sabit metnin kendisi
    # karsilastiriliyor.
    uyari = [u for u in bolme_uyarilari(durum) if u == GECERSIZ_BIRLESIM]
    return False, "-", " ".join(list(kat_notlari) + uyari[:1]).strip()


def algoritma_plan(durum):
    baz = len((durum.get("baz") or {}).get("kolonlar") or [])
    yeni = len((durum.get("secim") or {}).get("secilen_liste") or [])
    b = durum.get("bolme") or {}
    bolme_ad = ("zamansal - test dönemi %s" % b.get("oot_deger")) \
        if b.get("tur") == "zamansal" else "rastgele %%80 / %%20"
    arama, yer, uyari = _hiperparametre_secimi(durum)

    return ("Hangi algoritmanın bu veriye uyduğunu ölçeceğiz. Dört aday "
            "aynı değişken seti, aynı bölme ve aynı rastgelelik tohumu ile "
            "eğitilecek; "
            "tek fark algoritma olacak.\n\n"
            "  Adaylar    : %s\n"
            "  Değişken   : %s  (%s baz + %s yeni)\n"
            "  Bölme      : %s\n"
            "  Hiperpar.  : %s\n"
            "  Metrikler  : ROC-AUC, Gini, KS, eğitim süresi\n%s\n"
            "Eğitim uzun sürdüğü için '%s' senaryosunu tetikleyeceğim; "
            "webapp sonucu bekleyecek. Senaryo hazır değilse bu adımı "
            "geçebiliriz.\n\n"
            "Başlayalım mı?"
            % (" · ".join(ALGORITMALAR), _sayi(baz + yeni), _sayi(baz),
               _sayi(yeni), bolme_ad,
               ("arama - %s" % yer) if arama else "SABİT (arama yok)",
               ("\nUYARI: %s\n" % uyari) if uyari else "",
               senaryo_mod.senaryo_algoritma_adi()))

def algoritma_uygula(durum):
    arama, yer, uyari = _hiperparametre_secimi(durum)
    kaynak, _zengin = _kaynak(durum)
    if kaynak is None:
        durum["algoritma"] = {"hata": "kaynak veri seti bulunamadı"}
        return _KAYNAK_YOK % durum.get("veri_seti")

    konfig = {
        "veri_seti": kaynak,
        "target": durum["meta"]["target"],
        "baz_kolonlar": (durum.get("baz") or {}).get("kolonlar") or [],
        "yeni_kolonlar": (durum.get("secim") or {}).get("secilen_liste") or [],
        "bolme": _bolme_ozeti(durum),
        "meta": durum.get("meta") or {},
        "adaylar": ALGORITMALAR,
        # Senaryo arama yapip yapmayacagini BURADAN ogrenir; kendi
        # basina karar verirse val'i olmayan bir bolmede egitim setinde
        # arama yapar ve secimi egitim gurultusune uydurur.
        "hiperparametre_arama": arama,
        "hiperparametre_secim_yeri": yer,
        # Senaryo KENDI katlarini kurmamali: kimlik bazli bolmede kendi
        # kurdugu kat gruplamasiz olur ve ayni musteriyi iki tarafta
        # birakir. Gruplama anahtari ve etkin kat sayisi bildiriliyor.
        "cv_etkin": bool((durum.get("bolme") or {}).get("cv_etkin")),
        "cv_grup_kolon": ((durum.get("bolme") or {}).get("kimlik_kolon")
                          if bolme_ayarlari(durum)["birim"] == "kimlik"
                          else None),
    }

    # oturum_id: iki analist ayni anda calistiginda konfig/sonuc dosyalari
    # birbirini ezmesin; senaryo modulu kosu kimligini de dogruluyor.
    sonuc, hata = senaryo_mod.calistir(
        senaryo_mod.senaryo_algoritma_adi(), "algoritma", konfig,
        oturum_id=durum.get("_oturum_id"))

    if hata:
        durum["algoritma"] = {"hata": hata}
        return ("Algoritma karşılaştırması tamamlanamadı.\n\n  %s\n\n"
                "Bu adımı şimdilik atlıyorum; sonuç kabul edilmedi ve "
                "adım ilerletilmedi." % hata)

    # Hiperparametre kararinin nasil alindigi SONUCA yaziliyor: rapor,
    # arama yapilmadigini kosunun kendisinden okuyabilmeli.
    sonuc["hiperparametre_arama"] = arama
    sonuc["hiperparametre_secim_yeri"] = yer
    if uyari:
        sonuc["hiperparametre_uyarisi"] = uyari
    durum["algoritma"] = sonuc

    satirlar = []
    for s in sonuc.get("siralama", []):
        satirlar.append("  %-22s AUC %-8s Gini %-8s KS %-8s %ss"
                        % (s["ad"][:22], _ond(s["auc"], 4), _ond(s["gini"], 4),
                           _ond(s["ks"], 4), _ond(s.get("sure", 0), 1)))

    kazanan = sonuc.get("kazanan") or {}
    hiper_not = ("\n\nHİPERPARAMETRE: arama yapılmadı, adaylar SABİT "
                 "hiperparametrelerle eğitildi.%s"
                 % (" %s" % uyari if uyari else "")) if not arama else \
                ("\n\nHİPERPARAMETRE: arama %s üzerinde yapıldı." % yer)

    return ("Karşılaştırma tamamlandı. %s satırla eğitildi.\n\n"
            "AYRIŞTIRMA GÜCÜNE GÖRE SIRALAMA\n%s\n\n"
            "Önerim: %s - en yüksek ROC-AUC (%s) ve kabul edilebilir "
            "eğitim süresi.%s\n\n"
            "Final modelde bu algoritmayla devam edeceğim. Başka bir "
            "algoritma tercih ederseniz adını yazabilirsiniz."
            % (_sayi(sonuc.get("egitim_satir", 0)),
               "\n".join(satirlar) or "  (sonuç boş)",
               kazanan.get("ad", "-"), _ond(kazanan.get("auc"), 4),
               hiper_not))

# ===========================================================================
# ADIM 5.3: FINAL MODEL   (Dataiku senaryosunda calisir)
# ===========================================================================
def final_plan(durum):
    a = durum.get("algoritma") or {}
    kazanan = (a.get("kazanan") or {}).get("ad")

    if not kazanan:
        return ("Algoritma karşılaştırması yapılmadığı için varsayılan "
                "algoritmayla (Gradient Boosting) devam edeceğim.\n\n"
                "Final modeli eğitip kaydedeyim mi?")

    yeni = len((durum.get("secim") or {}).get("secilen_liste") or [])
    baz = len((durum.get("baz") or {}).get("kolonlar") or [])

    return ("Son adım: seçilen modeli tam veriyle eğitip kullanıma hazır "
            "hale getireceğim.\n\n"
            "  Algoritma    : %s\n"
            "  Değişken     : %s\n"
            "  Doğrulama    : test setinde ölçülecek\n"
            "  Model ayarı  : küçük bir ızgara üzerinde ayarlanacak\n\n"
            "Kaydedilecekler:\n"
            "  %s_FINAL_MODEL    - eğitilmiş model dosyası\n"
            "  %s_FINAL_SKOR     - test seti tahminleri\n"
            "  %s_FINAL_ONEM     - değişken önem sıralaması\n\n"
            "VALİDASYON\n"
            "Senaryo bittiğinde model %s kriterli validasyon kapısından "
            "geçirilecek (Gini, Gini düşüşü, KS, skor PSI, yeni değişken "
            "katkısı). Bunun için senaryonun eğitim ve test skor ile "
            "hedef "
            "dizilerini döndürmesi gerekiyor; dönmezse sonucu boş bırakmam, "
            "eksik alanları açıkça yazarım.\n\n"
            "'%s' senaryosu tetiklenecek. Başlayalım mı?"
            % (kazanan, _sayi(baz + yeni),
               durum["veri_seti"], durum["veri_seti"], durum["veri_seti"],
               _sayi(len(validasyon.ESIKLER)),
               senaryo_mod.senaryo_final_adi()))

# ---------------------------------------------------------------------------
# VALIDASYON KOPRUSU
# ---------------------------------------------------------------------------
# Validasyon kapisi skor ve hedef DIZILERI ister; final senaryosunun bunlari
# geri dondurmesi gerekir. Konfigurasyonda ACIKCA talep edilir, gelmezse
# kullaniciya eksik alanlar yazilir - sessizce bos birakilmaz.
VALIDASYON_ISTENEN = [
    "skorlar.egitim.y", "skorlar.egitim.p",
    "skorlar.test.y", "skorlar.test.p",
    "skorlar.oot.y", "skorlar.oot.p",      # OOT bölmesi varsa zorunlu
]

_ZORUNLU_BOLUM = ("egitim", "test")


def _algoritma_adi(durum):
    a = durum.get("algoritma") or {}
    return (a.get("kazanan") or {}).get("ad") or "Gradient Boosting"


def _skor_dizisi(sonuc, bolum, anahtar):
    """sonuc["skorlar"][bolum][anahtar]; duz biçim (ör. "p_test") de kabul."""
    s = sonuc.get("skorlar")
    if isinstance(s, dict):
        b = s.get(bolum)
        if isinstance(b, dict):
            v = b.get(anahtar)
            if v is not None and len(v):
                return list(v)
    v = sonuc.get("%s_%s" % (anahtar, bolum))
    if v is not None and len(v):
        return list(v)
    return None


def _validasyon_uygula(durum, sonuc):
    """metrik_hesapla + kaydet. Doner: (kullaniciya_gosterilecek_metin, olculdu)

    Adim her yeniden calistirildiginda once TEMIZLENIR; boylece geri donusten
    sonra ekranda eski kosunun validasyon sonucu kalmaz.
    """
    validasyon.temizle(durum)

    diziler, eksik = {}, []
    for bolum in ("egitim", "test", "oot"):
        for anahtar in ("y", "p"):
            d = _skor_dizisi(sonuc, bolum, anahtar)
            diziler[(bolum, anahtar)] = d
            if d is None and bolum in _ZORUNLU_BOLUM:
                eksik.append("skorlar.%s.%s" % (bolum, anahtar))

    oot_istendi = (durum.get("bolme") or {}).get("tur") == "zamansal"
    oot_var = diziler[("oot", "y")] is not None and diziler[("oot", "p")] is not None
    oot_uyari = ""
    if oot_istendi and not oot_var:
        oot_uyari = ("\n  UYARI: Bölme zamansal olduğu halde senaryo zaman "
                     "dışı skorları (skorlar.oot.y / skorlar.oot.p) "
                     "döndürmedi; 'Gini (zamansal test)' ve 'Skor PSI' "
                     "kriterleri ölçülemedi.")

    if eksik:
        return ("VALİDASYON ÖLÇÜLEMEDİ\n"
                "Final senaryosu skor dizilerini döndürmediği için 6 kriterli "
                "model kapısı çalıştırılamadı. Senaryo sonucu şu alanları "
                "içermeli:\n%s\n\n"
                "  skorlar = {\n"
                "    \"egitim\": {\"y\": [...], \"p\": [...]},\n"
                "    \"test\":   {\"y\": [...], \"p\": [...]},\n"
                "    \"oot\":    {\"y\": [...], \"p\": [...]}   # zamansal bölmede zorunlu\n"
                "  }\n\n"
                "y = gerçekleşen hedef (1 = kötü), p = kötü olma olasılığı.\n"
                "Senaryo kodu güncellenene kadar VALİDASYON sekmesi boş kalır."
                % "\n".join("  • eksik: %s" % f for f in eksik), False)

    for bolum in ("egitim", "test", "oot"):
        y, p = diziler[(bolum, "y")], diziler[(bolum, "p")]
        if y is not None and p is not None and len(y) != len(p):
            return ("VALİDASYON ÖLÇÜLEMEDİ\n"
                    "Senaryonun döndürdüğü %s dizilerinin boyu tutmuyor "
                    "(y %s, p %s). Aynı satır sırasıyla dönmeleri gerekiyor."
                    % (bolum, _sayi(len(y)), _sayi(len(p))), False)

    # Baz model test Gini'si: yeni degisken katkisi kriterinin referansi
    baz_gini = ((durum.get("model") or {}).get("baseline") or {}).get("gini")

    try:
        metrikler = validasyon.metrik_hesapla(
            diziler[("egitim", "y")], diziler[("egitim", "p")],
            diziler[("test", "y")], diziler[("test", "p")],
            y_oot=diziler[("oot", "y")] if oot_var else None,
            p_oot=diziler[("oot", "p")] if oot_var else None,
            baz_gini_test=baz_gini)
    except Exception as e:                  # pylint: disable=broad-except
        return ("VALİDASYON ÖLÇÜLEMEDİ\nMetrikler hesaplanırken hata oluştu: "
                "%s" % str(e)[:200], False)

    validasyon.kaydet(durum, metrikler,
                      model_adi=sonuc.get("algoritma") or _algoritma_adi(durum))

    p = validasyon.panel(durum)
    satirlar = ["  %-34s %-12s %s" % (s["ad"][:34], s["deger"], s["durum"])
                for s in p.get("satirlar") or []]
    baz_not = "" if baz_gini is not None else \
        ("\n  UYARI: Baz model Gini'si bilinmediği için 'Yeni değişken "
         "katkısı' kriteri ölçülemedi; model karşılaştırma adımını "
         "çalıştırın.")

    return ("VALİDASYON KAPISI - genel sonuç: %s\n  %s\n%s%s%s"
            % (str(p.get("genel")).upper(), p.get("ozet") or "",
               "\n".join(satirlar) or "  (kriter yok)", baz_not, oot_uyari),
            True)


def final_uygula(durum):
    kaynak, _zengin = _kaynak(durum)
    if kaynak is None:
        durum["final"] = {"hata": "kaynak veri seti bulunamadı"}
        validasyon.temizle(durum)
        return _KAYNAK_YOK % durum.get("veri_seti")

    konfig = {
        "veri_seti": kaynak,
        "cikti_onek": durum["veri_seti"],
        "target": durum["meta"]["target"],
        "baz_kolonlar": (durum.get("baz") or {}).get("kolonlar") or [],
        "yeni_kolonlar": (durum.get("secim") or {}).get("secilen_liste") or [],
        "bolme": _bolme_ozeti(durum),
        "meta": durum.get("meta") or {},
        "algoritma": _algoritma_adi(durum),
        # Validasyon kapisinin ihtiyaci: senaryo bu alanlari sonuca yazmali
        "istenen_ciktilar": list(VALIDASYON_ISTENEN),
        "validasyon_gerekli": True,
    }

    sonuc, hata = senaryo_mod.calistir(
        senaryo_mod.senaryo_final_adi(), "final", konfig,
        oturum_id=durum.get("_oturum_id"))

    if hata:
        durum["final"] = {"hata": hata}
        # Basarisiz kosudan sonra eski validasyon sonucu ekranda kalmasin
        validasyon.temizle(durum)
        return ("Final model üretilemedi.\n\n  %s\n\n"
                "Bu adımı şimdilik atlıyorum; sonuç kabul edilmedi ve adım "
                "ilerletilmedi. VALİDASYON sekmesi temizlendi." % hata)

    durum["final"] = sonuc
    val_metni, _olculdu = _validasyon_uygula(durum, sonuc)

    m = sonuc.get("metrikler") or {}
    onem = ["  %-34s %s" % (c[:34], _ond(v, 4))
            for c, v in (sonuc.get("en_onemli") or [])[:10]]

    return ("Final model hazır.\n\n"
            "  Algoritma      : %s\n"
            "  Eğitim / test  : %s / %s satır\n"
            "  Değişken       : %s\n\n"
            "TEST SETİ PERFORMANSI\n"
            "  ROC-AUC        : %s\n  Gini           : %s\n"
            "  KS             : %s\n\n"
            "EN ÖNEMLİ 10 DEĞİŞKEN\n%s\n\n"
            "Model %s veri setine, tahminler %s veri setine yazıldı.\n\n%s"
            % (sonuc.get("algoritma"), _sayi(sonuc.get("egitim_satir", 0)),
               _sayi(sonuc.get("test_satir", 0)),
               _sayi(sonuc.get("kolon_sayisi", 0)),
               _ond(m.get("auc"), 4), _ond(m.get("gini"), 4), _ond(m.get("ks"), 4),
               "\n".join(onem) or "  (önem bilgisi yok)",
               sonuc.get("model_dataset", "-"), sonuc.get("skor_dataset", "-"),
               val_metni))

def katalog_plan(durum):
    return ("Son adım: çalışmanın kalıcı çıktısını oluşturacağım.\n\n"
            "Her değişken için: formül, kaynak kolonlar, üretim yöntemi, "
            "çalıştırılabilir Python kodu, gerekçe, kalite ve seçim sonucu, "
            "modele katkısı.\n\nKataloğu oluşturalım mı?")

def katalog_uygula(durum):
    # oturum_id her satira KOSU_ID olarak yazilir; ayni tabloda birden
    # fazla kosunun satiri ayirt edilebilsin.
    tablo = katalog_mod.olustur(durum, oturum_id=durum.get("_oturum_id"))
    yazildi, yedek = _yaz("%s_KATALOG" % durum["veri_seti"], tablo,
                          "/degisken_katalogu.csv")

    secilen = int((tablo["SECIM"] == "SECILDI").sum()) if len(tablo) else 0
    atlanan = int(getattr(tablo, "attrs", {}).get("atlanan_satir") or 0)
    durum["katalog"] = {"dataset": yazildi, "satir": int(len(tablo)),
                        "secilen": secilen, "atlanan": atlanan}

    md = durum.get("model") or {}
    d = (md.get("delta") or {}).get("auc")
    ga = (md.get("delta_guven_araligi") or {}).get("auc")
    std = (md.get("delta_std") or {}).get("auc")
    katki = _guven_metni(d, std, ga)
    if not md.get("karsilastirilabilir", True):
        katki += "  (baz ve zengin model aynı - katkı ölçülmedi)"
    elif _sifir_iceriyor(ga):
        katki += "  (güven aralığı sıfırı içeriyor - gürültüden ayırt edilemiyor)"

    # MODELLEME_BAZ ve MODELLEME_LINEAGE YALNIZCA Mod C'de (birlestirme
    # adiminda) uretilir; Mod A'da bu iki veri seti yoktur.
    ek = ""
    if durum.get("mod") == "C":
        ek = "\n  %s\n  %s" % (BAZ_ADI, LINEAGE_ADI)

    atlanan_not = ""
    if atlanan > 0:
        atlanan_not = ("\n\nUYARI: Kataloğa yazılamayan %s bozuk kayıt "
                       "atlandı (eksik anahtar ya da beklenmeyen biçim). "
                       "Katalog bu satırları içermiyor." % _sayi(atlanan))

    return ("Katalog oluşturuldu: %s kayıt, %s tanesi seçili.\n\n"
            "ÇALIŞMA ÖZETİ\n"
            "  Veri seti      : %s\n  Hedef          : %s\n"
            "  Üretilen       : %s değişken\n  Kaliteyi geçen : %s\n"
            "  Seçilen        : %s\n  Model katkısı  : Δ ROC-AUC %s\n\n"
            "ÇIKTILAR\n  %s\n  PROJE_HAFIZASI/uretim_kodu.py%s%s\n\n"
            "Çalışma tamamlandı."
            % (_sayi(len(tablo)), _sayi(secilen),
               durum["veri_seti"], (durum.get("meta") or {}).get("target"),
               _sayi(len(durum.get("uretilen") or [])),
               _sayi(len((durum.get("kalite") or {}).get("gecti") or [])),
               _sayi(secilen), katki,
               ("%s veri seti" % yazildi) if yazildi else "PROJE_HAFIZASI%s" % yedek,
               ek, atlanan_not))
