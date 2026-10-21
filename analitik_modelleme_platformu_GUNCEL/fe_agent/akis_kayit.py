# -*- coding: utf-8 -*-
"""fe_agent/akis_kayit.py - Adim kayit defteri ve faz agaci."""

from fe_agent.akis_metin import (
    ADIM_ADI, FAZ01_OZET, GRUP_ADI_VERI_SOZLUK, SONRAKI_FAZLAR)
from fe_agent.akis_faz01 import (
    birlestirme_plan, birlestirme_uygula, bolme_girdi, bolme_uygula,
    ham_veri_girdi, ham_veri_plan, ham_veri_uygula, kurulum_girdi,
    kurulum_uygula, mod_girdi, mod_plan, mod_uygula,
    kaynak_sozluk_girdi, kaynak_sozluk_uygula,
    sozluk_tanim_plan, sozluk_tanim_uygula,
    tanimsiz_karar_plan, tanimsiz_karar_uygula,
    sozluk_birlestir_plan, sozluk_birlestir_uygula,
    parca_plan, parca_uygula, kolon_ad_plan, kolon_ad_uygula,
    donem_plan, donem_uygula, sozluk_kontrol_girdi, sozluk_kontrol_uygula,
    aciklama_plan, aciklama_uygula,
    sozluk_uret_plan, sozluk_uret_uygula, tanimlar_girdi,
    tanimlar_uygula, teyit_girdi, teyit_uygula, veri_sec_girdi,
    veri_sec_plan, veri_sec_uygula,
)
from fe_agent.akis_faz02 import (
    baz_plan, baz_uygula, sfa_girdi, sfa_uygula, stabilite_plan,
    stabilite_uygula, veri_profili_plan, veri_profili_uygula,
)
from fe_agent.akis_faz03 import kesif_plan, kesif_uygula, kural_plan, kural_uygula
from fe_agent.akis_faz04 import kalite_plan, kalite_uygula, secim_plan, secim_uygula
from fe_agent.akis_faz05 import (
    algoritma_plan, algoritma_uygula, final_plan, final_uygula,
    katalog_plan, katalog_uygula, model_plan, model_uygula,
)


# ===========================================================================
# ADIM KAYIT DEFTERI
# ===========================================================================
ADIMLAR = {
    "mod": {
        # Ad TEK KAYNAKTAN (akis_metin.ADIM_ADI): sol panel, sohbet
        # blogu ve kart basligi ayni ifadeyi kullanmali.
        "baslik": ADIM_ADI["mod"],
        "aciklama": "Veri setinin ve değişken sözlüğünün hazır olup "
                    "olmadığına göre başlangıç belirlenir. Sonraki adımlar "
                    "bu seçime göre şekillenir.",
        "otomatik": True,      # secim yapilinca ayrica onay beklemez
        # NOT: "plan" burada BILEREK duruyor ama pratikte CAGRILMIYOR.
        # mod_girdi bos mesajla asla True donmedigi icin _adima_gir plana
        # ulasamiyor; secim yapilinca da "otomatik" bayragi dogrudan
        # uygula'ya gidiyor. Alan, her adimin plan alani tasidigi
        # varsayimini korur (mod_plan mod_uygula ozetini doner, yani
        # yanlislikla cagrilirsa da dogru metni verir).
        "girdi": mod_girdi, "plan": mod_plan, "uygula": mod_uygula},

    "ham_veri": {
        "baslik": "Kaynak Tablolar",
        "aciklama": "Baz veri setini oluşturacak kaynak tablolar seçilir; "
                    "boyutları ve kolon sayıları çıkarılır.",
        # plan=None: FORMUN KENDISI ONAYDIR. Tablolar secilince birlestirme
        # plani dogrudan cikarilir; arada "Planı çıkarayım mı?" yok.
        "girdi": ham_veri_girdi, "plan": None, "uygula": ham_veri_uygula},
    "birlestirme": {
        "baslik": "Birleştirme Planı",
        "aciklama": "Yapay zekâ iskelet tabloyu, bağlantı anahtarlarını ve "
                    "işlem tablolarından üretilecek zaman pencereli "
                    "toplamaları önerir. Point-in-time kuralı uygulanır.",
        "girdi": None, "plan": birlestirme_plan, "uygula": birlestirme_uygula},

    "veri_sec": {
        "baslik": "Baz Veri Seti",
        "aciklama": "Modellemeye girecek baz veri seti seçilir; boyut ve tip "
                    "dağılımı çıkarılır.",
        # plan=None: FORMUN KENDISI ONAYDIR; secimden sonra "Devam edilsin
        # mi?" sorulmaz (ham_veri ile ayni kural).
        "girdi": veri_sec_girdi, "plan": None, "uygula": veri_sec_uygula},

    "sozluk_uret": {
        "baslik": "Sözlük Üretimi",
        "aciklama": "Her kolonun tipi, dağılımı ve örnek değerleri "
                    "incelenir; yapay zekâ ne anlama geldiğini yazar. "
                    "Kimlik benzeri kolonların örnekleri paylaşılmaz.",
        "girdi": None, "plan": sozluk_uret_plan, "uygula": sozluk_uret_uygula},

    "kurulum": {
        "baslik": "Baz Veri Seti ve Baz Sözlük",
        "aciklama": "Analiz edilecek veri seti ve değişken sözlüğü "
                    "seçilir; kapsam oranı hesaplanır.",
        # plan=None: FORMUN KENDISI ONAYDIR. Tanimsiz kolon karari bu
        # adimda DEGIL, "sozluk_tanim" adiminda ve modelleme
        # tanimlarindan SONRA verilir (hedef/kimlik/donem kolonunun
        # tanimi zorunlu, hangileri oldugu once bilinmeli).
        "girdi": kurulum_girdi, "plan": None, "uygula": kurulum_uygula},

    # SOZLUK BIRLESTIRME: birden fazla sozlukte farkli tanimi olan
    # kolonlarda kalacak tanim. Cakisma yoksa sorulmadan gecilir.
    "sozluk_birlestir": {
        "baslik": ADIM_ADI["sozluk_birlestir"],
        "aciklama": "Seçilen sözlüklerde tanımı farklı olan kolonlar listelenir; "
                    "her biri için kalacak tanım seçilir ya da yazılır.",
        "girdi": None, "plan": sozluk_birlestir_plan,
        "uygula": sozluk_birlestir_uygula},

    "kaynak_sozluk": {
        "baslik": "Kaynak Sözlükleri",
        "aciklama": "Her kaynak tablonun değişken sözlüğü seçilir. Nihai "
                    "sözlük birleştirmeden sonra bu sözlüklerden kurulur; "
                    "toplama kolonları kaynak tanımdan türetilir.",
        # plan=None: FORMUN KENDISI ONAYDIR (kurulum ile ayni).
        "girdi": kaynak_sozluk_girdi, "plan": None,
        "uygula": kaynak_sozluk_uygula},

    "sozluk_tanim": {
        "baslik": ADIM_ADI["sozluk_tanim"],
        "aciklama": "Sözlükte tanımı bulunmayan kolonlar için açıklama "
                    "yazılır; tanımsız kalanlar bir sonraki adımda sorulur. "
                    "Hedef, kimlik ve dönem kolonunun tanımı zorunludur.",
        "girdi": None, "plan": sozluk_tanim_plan,
        "uygula": sozluk_tanim_uygula},

    # TANIMSIZ KOLONLAR: Eksik Sozluk Tanimlari'ndan sonra hala tanimsiz
    # olan kolonlarin AMP_VERISETI'nden cikarilip cikarilmayacagi.
    "tanimsiz_karar": {
        "baslik": ADIM_ADI["tanimsiz_karar"],
        "aciklama": "Sözlükte tanımı olmayan kolonlar listelenir. Çıkarılması "
                    "onaylananlar AMP_VERISETI'nden ve AMP_SOZLUK'ten çıkarılır; "
                    "kalanlar veri setinde kalır, sözlükte tanımları boş durur.",
        "girdi": None, "plan": tanimsiz_karar_plan,
        "uygula": tanimsiz_karar_uygula},

    # SOZLUK VE KOLON ADI KONTROLU: iki kartli secim (baslangic secimi
    # gibi). "atla" secilirse sonraki dort adim kendiliginden atlanir.
    "sozluk_kontrol": {
        "baslik": ADIM_ADI["sozluk_kontrol"],
        "aciklama": "Sözlükteki açıklamaların ve kolon adlarının kontrol edilip "
                    "edilmeyeceği seçilir. Kontrol edilirse kolon adlarının "
                    "parçaları, her kolonun kartı ve açıklaması ve yeni kolon "
                    "adları sırayla onaylanır.",
        # plan=None: SECIMIN KENDISI ONAYDIR.
        "girdi": sozluk_kontrol_girdi, "plan": None, "uygula": sozluk_kontrol_uygula},

    # SIRA: sayili zaman parcalari -> rakamsiz ad parcalari -> kolon
    # kartlari (parcalardan) -> kolon adlari (kartlardan). Her adim bir
    # oncekinin onayladigini kesin bilgi olarak kullanir.
    "donem": {
        "baslik": ADIM_ADI["donem"],
        "aciklama": "Kolon adlarındaki sayılı zaman parçalarının (30D, M3, "
                    "3_M) anlamı ve türü onaylanır.",
        "girdi": None, "plan": donem_plan, "uygula": donem_uygula},

    "parca": {
        "baslik": ADIM_ADI["parca"],
        "aciklama": "Kolon adlarındaki öbür parçaların (kısaltmalar ve "
                    "sözcükler) anlamı, türü ve adlarda kullanılacak standart "
                    "yazılışı onaylanır; yazımı farklı aynı parçalar birleşir.",
        "girdi": None, "plan": parca_plan, "uygula": parca_uygula},

    "aciklama": {
        "baslik": ADIM_ADI["aciklama"],
        "aciklama": "Her kolonun kartı onaylı parçalardan kurulur, sözlük "
                    "tanımıyla karşılaştırılır ve tek, açık bir açıklama "
                    "yazılır; her kolon onaylanır.",
        "girdi": None, "plan": aciklama_plan, "uygula": aciklama_uygula},

    "kolon_ad": {
        "baslik": ADIM_ADI["kolon_ad"],
        "aciklama": "Yeni kolon adları onaylı parçaların standart "
                    "yazılışlarıyla Ad Standardı'na göre kurulur; yeni adlar "
                    "yalnız platformun kopyalarında geçerli olur.",
        "girdi": None, "plan": kolon_ad_plan, "uygula": kolon_ad_uygula},

    "tanimlar": {
        "baslik": ADIM_ADI["tanimlar"],
        "aciklama": "Hedef değişken, kimlik kolonu ve dönem kolonu "
                    "belirlenir; hedefin tipi ve dağılımı çıkarılır.",
        # plan=None: FORMUN KENDISI ONAYDIR. Ayri bir "Doğru mu?" ozeti
        # yok — form doldurulup onaylandiginda karar verilmistir ve o uc
        # satir sag paneldeki Veri seti kartinda zaten duruyor.
        "girdi": tanimlar_girdi, "plan": None, "uygula": tanimlar_uygula},

    "teyit": {
        "baslik": ADIM_ADI["teyit"],
        "aciklama": "Değişken listesi ve sözlük tanımları bölme öncesinde "
                    "son kez gözden geçirilir.",
        # plan=None: FORMUN KENDISI ONAYDIR. Kart "son kez gözden geçirin"
        # diyor ve tek dugmesi var; ayri bir "Doğru mu?" asamasi ayni
        # onayi ikinci kez sormak olurdu.
        "girdi": teyit_girdi, "plan": None, "uygula": teyit_uygula},

    "bolme": {
        "baslik": ADIM_ADI["bolme"],
        "aciklama": "Veri setinin eğitim, doğrulama ve test kullanım "
                    "planı belirlenir. Bu sınır sızıntı sınırıdır: "
                    "doldurma, dönüşüm ve eğitim yalnızca geliştirme "
                    "setinden hesaplanır.",
        # plan=None: KARTIN KENDISI ONAYDIR. Kart iki mod tasiyor
        # (Önerilen Ayarlar / Özel Ayarlar) ve tek dugmesi var; ayri bir
        # "Doğru mu?" asamasi ayni onayi ikinci kez sormak olurdu.
        "girdi": bolme_girdi, "plan": None, "uygula": bolme_uygula},

    "veri_profili": {
        "baslik": "Veri Profili ve Kalite",
        "aciklama": "Dataset seviyesinde inceleme: eksik değer, tekil sayısı, "
                    "kardinalite, sabit ve kimlik benzeri kolonlar. Kusurlu "
                    "kolonlardan değişken üretilmez.",
        "girdi": None, "plan": veri_profili_plan, "uygula": veri_profili_uygula},
    "sfa": {
        "baslik": "Tek Değişken Analizi (SFA)",
        "aciklama": "Her değişkenin hedefle ilişkisi ölçülür (IV, beş "
                    "dönüşümle C-value, hedefe göre aralıklar). Eleme "
                    "yapılmaz; yapay zekâ her değişkenin modele hangi "
                    "hâliyle gireceğine karar verir, kararlar sağdaki "
                    "Değişkenler > Dağılım ve SFA bölümünde değiştirilebilir.",
        # plan=None: karar kartinin "Kararları Onayla" dugmesi onaydir.
        "girdi": sfa_girdi, "plan": None, "uygula": sfa_uygula,
        # Kartin mesaji ("sfa kararları: ...") soru sanilip dil modeline gitmesin
        "tanir": lambda m: str(m or "").strip().lower().startswith("sfa kararları")},
    "stabilite": {
        "baslik": "Stabilite Analizi (PSI)",
        "aciklama": "Değişken dağılımlarının zaman içinde kayıp kaymadığı "
                    "ölçülür. Zamansal bölme gerektirir.",
        "girdi": None, "plan": stabilite_plan, "uygula": stabilite_uygula},
    "baz": {
        "baslik": "Analitik Baz Set",
        "aciklama": "Kusurlu kolonlar düşürülür, eksik değerler geliştirme "
                    "setinin istatistikleriyle doldurulur ve set dondurulur.",
        "girdi": None, "plan": baz_plan, "uygula": baz_uygula},

    "kural": {
        "baslik": "Kural Tabanlı Değişken Üretimi",
        "aciklama": "Yapay zekâ hangi aileye fark, oran, log, sıralama veya "
                    "budama uygulanacağını önerir; Python üretir.",
        "girdi": None, "plan": kural_plan, "uygula": kural_uygula},
    "kesif": {
        "baslik": "AI Değişken Keşfi",
        "aciklama": "Kalıpların dışında yeni değişken hipotezleri üretilir; "
                    "güvenlik kontrolünden geçenler çalıştırılır.",
        "girdi": None, "plan": kesif_plan, "uygula": kesif_uygula},

    "kalite": {
        "baslik": "Sızıntı Kontrolü",
        "aciklama": "Analitik baz setteki değişkenlerin hedefle aşırı ilişkisi "
                    "(sızıntı riski) ölçülür; şüpheliler aday sete ve modele "
                    "alınmaz.",
        "girdi": None, "plan": kalite_plan, "uygula": kalite_uygula},
    "secim": {
        "baslik": "Aday Değişken Seti",
        "aciklama": "Yarı-sabit eleme, fazlalık eleme, karşılıklı bilgi ve "
                    "model önem skoru sırayla uygulanır.",
        "girdi": None, "plan": secim_plan, "uygula": secim_uygula},

    "model": {
        "baslik": "Model Karşılaştırması",
        "aciklama": "Baz ve zenginleştirilmiş set aynı bölme, aynı "
                    "rastgelelik tohumu ve aynı yapılandırma altında "
                    "karşılaştırılır.",
        "girdi": None, "plan": model_plan, "uygula": model_uygula},
    "algoritma": {
        "baslik": "Algoritma Seçimi",
        "aciklama": "Dört algoritma aynı değişken seti, aynı bölme ve aynı "
                    "rastgelelik tohumu ile eğitilir; ayrıştırma gücü ve "
                    "eğitim süresi "
                    "karşılaştırılır. Uzun sürdüğü için Dataiku senaryosunda "
                    "çalışır.",
        "girdi": None, "plan": algoritma_plan, "uygula": algoritma_uygula},
    "final": {
        "baslik": "Model Finalizasyonu",
        "aciklama": "Seçilen model son haliyle eğitilir, test setinde "
                    "doğrulanır ve pickle biçiminde kaydedilir.",
        "girdi": None, "plan": final_plan, "uygula": final_uygula},
    "katalog": {
        "baslik": "Değişken Kataloğu",
        "aciklama": "Kabul edilen her değişkenin formülü, kaynağı, kodu, "
                    "kalite ve seçim sonucu kalıcı kataloğa yazılır.",
        "girdi": None, "plan": katalog_plan, "uygula": katalog_uygula},
}

# Faz 01'in alt adimlari moda gore degisir.
# "teyit" UC MODDA DA "tanimlar" ile "bolme" arasindadir: bolme sizinti
# sinirini cektigi icin degisken listesi ve sozluk tanimlari en son orada
# degistirilebilir.
FAZ01_ADIMLARI = {
    None: ["mod"],
    # SOZLUK TANIMLARI, MODELLEME TANIMLARINDAN SONRA. Hedef, kimlik ve
    # donem kolonunun sozlukte tanimli olmasi zorunlu; hangi kolonlar
    # oldugu tanimlar adiminda belli oluyor.
    "A":  ["mod", "kurulum", "sozluk_birlestir", "tanimlar", "sozluk_tanim", "tanimsiz_karar",
           "sozluk_kontrol", "donem",
           "parca", "aciklama", "kolon_ad", "teyit", "bolme"],
    # B: nihai veri seti YOK; kaynak tablolar ve HER BIRININ SOZLUGU hazir.
    # Sozlukler birlestirmeden ONCE eslenir, nihai sozluk birlestirmede
    # bunlardan kurulur. Kaynagi tanimsiz kolonlar icin A gibi
    # sozluk_tanim adimi var.
    "B":  ["mod", "ham_veri", "kaynak_sozluk", "birlestirme", "tanimlar",
           "sozluk_tanim", "tanimsiz_karar", "sozluk_kontrol", "donem",
           "parca", "aciklama",
           "kolon_ad", "teyit", "bolme"],
    # C ve D'de sozluk VERIDEN URETILIYOR: her kolon tanim aliyor, yani
    # tanimsiz kolon kalmiyor ve ayri bir "sozluk_tanim" adimina gerek
    # yok. Zorunlu tanim kurali orada yapisi geregi saglaniyor.
    "C":  ["mod", "veri_sec", "sozluk_uret", "tanimlar", "teyit", "bolme"],
    "D":  ["mod", "ham_veri", "birlestirme", "sozluk_uret", "tanimlar",
           "teyit", "bolme"],
}

# ===========================================================================
# BLOK GRUPLARI
# ===========================================================================
# Ardisik adimlar sohbette TEK BLOK olarak gorunur; her adim blogun
# icinde kendi ALT BASLIGINI ve kendi "Geri Dön" dugmesini tasir. Sol
# paneldeki is akisinda adimlar AYRI kalir: boylece
# yalnizca modelleme tanimlarina donmek mumkun oluyor.
#
# Gruplama yalnizca GORSELDIR; adim sirasi, sayimi ve geri donus hedefi
# degismez.
ADIM_GRUPLARI = {
    "kurulum":     "veri_sozluk",
    "sozluk_birlestir": "veri_sozluk",
    "tanimlar":    "veri_sozluk",
    "sozluk_tanim": "veri_sozluk",
    "tanimsiz_karar": "veri_sozluk",
    "sozluk_kontrol": "veri_sozluk",
    "donem": "veri_sozluk",
    "parca": "veri_sozluk",
    "aciklama": "veri_sozluk",
    "kolon_ad": "veri_sozluk",
    # C modu: veri seti secimi + sozluk uretimi + modelleme tanimlari
    "veri_sec":    "veri_sozluk",
    "sozluk_uret": "veri_sozluk",
    # B ve D modunda ham tablolar ve birlestirme AYRI kalir: onlar veri
    # hazirlama isi, sozluk ve tanimlar ayri bir karar kumesi.
}

GRUP_BASLIKLARI = {
    "veri_sozluk": GRUP_ADI_VERI_SOZLUK,
}


def adim_grubu(anahtar):
    """Adimin blok grubu. Gruplu degilse (None, "")."""
    grup = ADIM_GRUPLARI.get(anahtar or "")
    if not grup:
        return None, ""
    return grup, GRUP_BASLIKLARI.get(grup, "")

# ===========================================================================
# ALT ADIMLAR
# ===========================================================================
# Sozluk ve Kolon Adi Kontrolu'nun dort adimi sol panelde ve sohbet
# basliklarinda kontrolun ALTINDA gorunur (01.2.4.1 - 01.2.4.4). Kontrol
# yapilsin secilene kadar kapali durur; yapilmasin secilirse atlanir ve
# kapali kalir. Yalnizca GORSELDIR: adim sirasi, sayimi ve geri donus
# hedefi degismez. Sozluk Birlestirme kurulumun, Tanimsiz Kolonlar Eksik
# Sozluk Tanimlari'nin altindadir.
ALT_ADIMLAR = {
    "sozluk_birlestir": "kurulum",
    "tanimsiz_karar": "sozluk_tanim",
    "donem": "sozluk_kontrol",
    "parca": "sozluk_kontrol",
    "aciklama": "sozluk_kontrol",
    "kolon_ad": "sozluk_kontrol",
}


def alt_adim_durumu(ust, durum, sira):
    """Ust adimin alt adimlari: "acik" (kontrol yapilacak), "atlandi"
    (kontrol yapilmayacak) ya da "" (karar yok; kapali). Karar ust adim
    gecildiginde gecerlidir: ust adima donulunce alt adimlar yeniden
    kapanir. sira: ust adimin adim_sirasi icindeki yeri."""
    durum = durum or {}
    if int(durum.get("i") or 0) <= sira:
        return ""
    if ust == "sozluk_kontrol":
        return {"yap": "acik", "atla": "atlandi"}.get(durum.get("sozluk_kontrol"), "")
    return "acik"

SECIMLI = {"kural", "kesif"}

def adim_sirasi(mod=None):
    """Moda gore duz adim listesi."""
    return FAZ01_ADIMLARI.get(mod, FAZ01_ADIMLARI[None]) + \
        [a for f in SONRAKI_FAZLAR for a in f["adimlar"]]

def fazlar(mod=None):
    """Sol paneldeki hiyerarsi."""
    return [{"no": "01", "baslik": "Çalışma Kurulumu",
             "ozet": FAZ01_OZET,
             "adimlar": FAZ01_ADIMLARI.get(mod, FAZ01_ADIMLARI[None])}] + \
        SONRAKI_FAZLAR

def _satirlar(f):
    """Fazin sol paneldeki satirlari; app.js fazOgeleri ile ayni kural.
    Ardisik ayni gruptaki adimlar tek satirdir, alt adimlar ust
    adimlarinin altina girer. Her satir: [(anahtar, [alt adimlar])]."""
    satirlar, gruplar = [], []
    for a in f["adimlar"]:
        ust = ALT_ADIMLAR.get(a)
        uye = next((u for s in satirlar for u in s if u[0] == ust), None) \
            if ust else None
        if uye:
            uye[1].append(a)
            continue
        grup = ADIM_GRUPLARI.get(a)
        if grup and gruplar and gruplar[-1] == grup:
            satirlar[-1].append((a, []))
            continue
        satirlar.append([(a, [])])
        gruplar.append(grup)
    return satirlar


def adim_kodu(anahtar, mod=None, satir=False):
    """Adimin is akisindaki numarasi: 01.2.3, 01.2.4.1, 03.3. Gruplu
    satirin icindeki adim alt numara alir; tek adimli satirin adimi
    satirin numarasini tasir. satir=True ise adimin SATIRININ numarasi
    (01.2). Adim bu modun akisinda yoksa bos dize."""
    for f in fazlar(mod):
        for i, uyeler in enumerate(_satirlar(f), 1):
            kod = "%s.%d" % (f["no"], i)
            for j, (u, cocuklar) in enumerate(uyeler, 1):
                ukod = kod if len(uyeler) == 1 else "%s.%d" % (kod, j)
                if u == anahtar:
                    return kod if satir else ukod
                for k, c in enumerate(cocuklar, 1):
                    if c == anahtar:
                        return kod if satir else "%s.%d" % (ukod, k)
    return ""


def adim_atfi(anahtar, mod=None, satir=False):
    """Mesajlarda adima atif, numarali ve kalin:
    "**01.2.3 Eksik Sözlük Tanımları**". satir=True ise adimin sol
    paneldeki satiri: "**01.2 Veri Seti, Sözlük ve Kolon Rolleri**".
    On yuz ** isaretini kalin yazar."""
    _grup, grup_baslik = adim_grubu(anahtar)
    ad = grup_baslik if satir and grup_baslik else \
        (ADIMLAR.get(anahtar) or {}).get("baslik") or anahtar
    kod = adim_kodu(anahtar, mod, satir)
    return "**%s**" % ("%s %s" % (kod, ad) if kod else ad)


def faz_atfi(no):
    """Faza atif: "**02. Değişken Mühendisliği**"."""
    for f in SONRAKI_FAZLAR:
        if f["no"] == no:
            return "**%s. %s**" % (no, f["baslik"])
    return ""


def faz_agaci(mod=None, durum=None):
    """Sol panelin agaci. durum verilirse alt adimli adimlar alt
    adimlarinin acik mi kapali mi oldugunu da tasir (bkz. ALT_ADIMLAR)."""
    ustler = set(ALT_ADIMLAR.values())
    cikti, sayac = [], 0
    for f in fazlar(mod):
        adimlar = []
        for a in f["adimlar"]:
            sayac += 1
            grup, grup_baslik = adim_grubu(a)
            oge = {"anahtar": a, "sira": sayac - 1,
                   "no": "%s.%d" % (f["no"].lstrip("0"), len(adimlar) + 1),
                   "baslik": ADIMLAR[a]["baslik"],
                   "aciklama": ADIMLAR[a].get("aciklama", ""),
                   # Blok grubu: on yuz ardisik adimlari tek
                   # blokta, alt basliklarla ciziyor.
                   "grup": grup or "",
                   "grup_baslik": grup_baslik,
                   # Alt adimsa ust adiminin anahtari.
                   "ust": ALT_ADIMLAR.get(a, "")}
            if a in ustler:
                oge["alt_durum"] = alt_adim_durumu(a, durum, sayac - 1)
            adimlar.append(oge)
        cikti.append({"no": f["no"], "baslik": f["baslik"],
                      "ozet": f["ozet"], "adimlar": adimlar})
    return cikti
