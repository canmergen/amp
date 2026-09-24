# -*- coding: utf-8 -*-
"""fe_agent/akis.py - Analitik Modelleme Platformu akis orkestratoru.

Bu dosya artik yalnizca bir CEPHE (facade). Gercek kod su modullerde:

    akis_metin.py    Sabit metinler ve mesaj desenleri
    akis_durum.py    Oturum durumu, veri okuma/yazma, bicimleme
    akis_faz01.py    Faz 01 - Calisma Kurulumu
    akis_faz02.py    Faz 02 - Veri Anlama ve Hazirlama
    akis_faz03.py    Faz 03 - Degisken Muhendisligi
    akis_faz04.py    Faz 04 - Degisken Degerlendirme
    akis_faz05.py    Faz 05 - Modelleme ve Finalizasyon
    akis_kayit.py    Adim kayit defteri ve faz agaci
    akis_panel.py    Ust serit ozeti ve Ozet sayfasi
    akis_sohbet.py   Mesaj yonlendirme ve adim gecisleri

Yardimci moduller (akis_* zincirinin disinda, yapraklar):

    sozluk_calisma.py  Sozlugun oturuma ozel calisma kopyasi; kategori
                       duzenlemesi YALNIZCA bu kopyaya yazar
    dokuman.py         Model Gelistirme Dokumani govdesi ve duzenlemeleri
    docx_yaz.py        Bagimliliksiz .docx uretici (yalnizca dokuman.py)

Bagimlilik yonu TEK YONLUDUR (ustteki alttakini bilmez):

    metin -> durum -> faz01..faz05 -> kayit -> panel -> sohbet

sozluk_calisma akis_durum'un ustunde durur; akis_durum.sozluk_oku onu
GEC IMPORT ile cagirir (modul seviyesinde yazilsa dongu olurdu).

Yeni bir adim eklerken: ilgili faz dosyasina plan/uygula fonksiyonlarini
yaz, sonra akis_kayit.py icindeki ADIMLAR sozlugune kaydet.

webapp backend'i yalnizca bu dosyayi import eder; bolunme oncesi
kullanilan tum isimler burada aynen durur.
"""

# flake8: noqa: F401  (bilerek yeniden ihrac ediliyor)

from fe_agent.akis_metin import (  # noqa
    FAZ01_OZET, GERI_KALIP, KARSILAMA, MOD_ADLARI, MOD_KALIP,
    MOD_SECENEKLERI, PLATFORM_TANIMLARI, SECIM_KALIP, SONRAKI_FAZLAR,
    SORU_KALIP,
)
from fe_agent.akis_durum import (  # noqa
    AMP_KLASOR, AMP_SOZLUK_ADI, AMP_SOZLUK_KOLONLARI, AMP_VERI_ADI,
    BAZ_ADI, HAFIZA_FOLDER, LINEAGE_ADI, OKUMA_LIMITI, SOZLUK_ADI,
    _ad_haritasi, _dataset_var_mi, _df_oku, _folder, _kisa_ad,
    _liste, _nerede, _ond, _plan_adlari_cevir, _sayi, _secim_ayikla,
    _yaz, _yol, bolme_ayarlari, bolme_kaydet, bolme_kisitlari,
    bolme_onerisi, bolme_ozeti,
    bolme_uyarilari, durum_kaydet, durum_yukle, katlar, maskeler,
    modelleme_df, modelleme_kaynagi, setler, yeni_durum,
)
from fe_agent.akis_faz01 import (  # noqa
    EN_FAZLA_TANIMSIZ, TANIM_KALIP, _kurulum_formu, _tanimsiz_oneriler,
    _veri_sec_formu, birlestirme_plan,
    birlestirme_uygula, bolme_girdi, bolme_karti, bolme_kartini_tazele,
    bolme_oneriyi_uygula, bolme_uygula, ham_veri_girdi,
    ham_veri_plan, ham_veri_uygula, kurulum_girdi,
    kurulum_uygula, mod_girdi, mod_plan, mod_uygula,
    oneri_isi_durumu, oneri_isi_iptal,
    sozluk_tanim_plan, sozluk_tanim_uygula,
    sozluk_uret_plan, sozluk_uret_uygula, tanimlar_girdi,
    zorunlu_tanimlar,
    tanimlar_uygula, teyit_girdi, teyit_ozeti, teyit_satirlari,
    TEYIT_EXCEL_ADI, SOZLUK_EXCEL_ADI,
    teyit_excel, teyit_kaydedildi_mi,
    tanimsiz_kolonlari_isaretle,
    amp_ciktilarini_yaz, amp_nerede,
    teyit_kartini_tazele, teyit_uygula, tip_secimi_dogrula,
    veri_sec_girdi, veri_sec_plan, veri_sec_uygula,
)
from fe_agent.akis_faz02 import (  # noqa
    baz_plan, baz_uygula, sfa_plan, sfa_uygula, stabilite_plan,
    stabilite_uygula, veri_profili_plan, veri_profili_uygula,
)
from fe_agent.akis_faz03 import (  # noqa
    _ikili, _tekli, kesif_plan, kesif_uygula, kural_plan,
    kural_uygula,
)
from fe_agent.akis_faz04 import (  # noqa
    kalite_plan, kalite_uygula, secim_plan, secim_uygula,
)
from fe_agent.akis_faz05 import (  # noqa
    ALGORITMALAR, algoritma_plan, algoritma_uygula, final_plan,
    final_uygula, katalog_plan, katalog_uygula, model_plan,
    model_uygula,
)
from fe_agent.akis_kayit import (  # noqa
    adim_grubu,
    ADIMLAR, FAZ01_ADIMLARI, SECIMLI, adim_sirasi, faz_agaci, fazlar,
)
from fe_agent.akis_panel import (  # noqa
    _bolum, bolme_formu, detay, eksik_paneli, feature_tablo,
    hazirlik_paneli, ozet, sfa_paneli, veri_paneli, veri_sozluk_paneli,
)
from fe_agent.dokuman import (  # noqa
    BLOKER_BOLUMLER as DOKUMAN_BLOKER_BOLUMLERI,
    BOLUM_ANAHTARLARI as DOKUMAN_BOLUMLERI,
    DOSYA_ADI as DOKUMAN_DOSYA_ADI,
    ESKI_ANAHTAR_GOCU as DOKUMAN_ANAHTAR_GOCU,
    STATULER as DOKUMAN_STATULERI,
    dokuman, dokuman_bolum_kaydet, dokuman_word,
    goc_uygula as dokuman_goc_uygula,
)
from fe_agent.sozluk_calisma import (  # noqa
    calisma_kopyasi_sil, kategori_yaz, kategori_yaz_toplu,
    kaynak_etiketi as sozluk_kaynak_etiketi,
    kopya_kur as sozluk_kopya_kur, kopya_var_mi as sozluk_kopya_var_mi,
    satir_ekle as sozluk_satir_ekle, tanim_yaz as sozluk_tanim_yaz,
)
from fe_agent.akis_sohbet import (  # noqa
    _adet, _adima_gir, _ekran_durumu, _soru_baglami, _soru_isle,
    _soru_mu, adim_anahtari, adim_basligi, ilk_soru, mesaj_isle,
    mevcut_ekran,
)

__all__ = [
    "ADIMLAR", "ALGORITMALAR", "BAZ_ADI",
    "AMP_KLASOR", "AMP_SOZLUK_ADI", "AMP_SOZLUK_KOLONLARI",
    "AMP_VERI_ADI",
    "amp_ciktilarini_yaz", "amp_nerede",
    "DOKUMAN_ANAHTAR_GOCU", "DOKUMAN_BLOKER_BOLUMLERI", "DOKUMAN_BOLUMLERI",
    "DOKUMAN_DOSYA_ADI", "DOKUMAN_STATULERI", "EN_FAZLA_TANIMSIZ",
    "FAZ01_ADIMLARI",
    "FAZ01_OZET", "GERI_KALIP", "HAFIZA_FOLDER", "KARSILAMA",
    "LINEAGE_ADI", "MOD_ADLARI", "MOD_KALIP", "MOD_SECENEKLERI",
    "OKUMA_LIMITI", "PLATFORM_TANIMLARI", "SECIMLI", "SECIM_KALIP",
    "SONRAKI_FAZLAR", "SORU_KALIP", "SOZLUK_ADI", "TANIM_KALIP",
    "adim_anahtari", "adim_basligi", "mevcut_ekran",
    "adim_sirasi", "algoritma_plan", "algoritma_uygula", "modelleme_df", "modelleme_kaynagi",
    "baz_plan", "baz_uygula", "birlestirme_plan",
    "birlestirme_uygula", "bolme_ayarlari", "bolme_formu",
    "bolme_girdi", "bolme_kartini_tazele", "bolme_karti",
    "bolme_kaydet", "bolme_kisitlari", "bolme_onerisi",
    "bolme_oneriyi_uygula", "bolme_ozeti", "bolme_uygula",
    "bolme_uyarilari", "detay", "dokuman", "dokuman_bolum_kaydet",
    "dokuman_goc_uygula", "dokuman_word",
    "durum_kaydet", "durum_yukle", "eksik_paneli", "faz_agaci",
    "fazlar", "feature_tablo", "final_plan", "final_uygula",
    "ham_veri_girdi", "hazirlik_paneli",
    "ham_veri_plan", "ham_veri_uygula", "ilk_soru", "kalite_plan",
    "kalite_uygula", "katalog_plan", "katalog_uygula",
    "calisma_kopyasi_sil", "kategori_yaz", "kategori_yaz_toplu",
    "katlar", "kesif_plan", "kesif_uygula", "kural_plan",
    "kural_uygula",
    "adim_grubu",
    "kurulum_girdi", "kurulum_uygula", "maskeler",
    "sozluk_tanim_plan", "sozluk_tanim_uygula", "zorunlu_tanimlar",
    "teyit_satirlari",
    "oneri_isi_durumu", "oneri_isi_iptal",
    "mesaj_isle", "mod_girdi", "mod_plan", "mod_uygula",
    "model_plan", "model_uygula", "ozet", "secim_plan",
    "secim_uygula", "setler", "sfa_paneli", "sfa_plan", "sfa_uygula",
    "sozluk_kaynak_etiketi", "sozluk_kopya_kur", "sozluk_kopya_var_mi",
    "sozluk_satir_ekle", "sozluk_tanim_yaz",
    "sozluk_uret_plan", "sozluk_uret_uygula", "stabilite_plan",
    "stabilite_uygula",
    "tanimlar_girdi", "tanimlar_uygula",
    "TEYIT_EXCEL_ADI", "SOZLUK_EXCEL_ADI",
    "teyit_excel", "teyit_kaydedildi_mi",
    "tanimsiz_kolonlari_isaretle",
    "teyit_girdi", "teyit_kartini_tazele", "teyit_ozeti",
    "teyit_uygula", "tip_secimi_dogrula",
    "veri_paneli", "veri_profili_plan", "veri_profili_uygula",
    "veri_sozluk_paneli",
    "veri_sec_girdi", "veri_sec_plan", "veri_sec_uygula", "yeni_durum",
]
