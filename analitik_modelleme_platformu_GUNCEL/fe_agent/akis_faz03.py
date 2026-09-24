# -*- coding: utf-8 -*-
"""fe_agent/akis_faz03.py - Faz 03 - Degisken Muhendisligi: kural tabanli uretim ve AI kesfi.

akis.py bolundu; bu dosya o bolumun aynisidir.
"""

import dataiku
import numpy as np
import pandas as pd
from fe_agent import llm as llm_mod
from fe_agent import ifade as ifade_mod

from fe_agent.akis_durum import (
    sozluk_oku,
    _dataset_var_mi, _df_oku, _folder, _liste, _sayi, maskeler,
    modelleme_df,
)

try:                                     # _df_oku onbellegi (akis_durum)
    from fe_agent.akis_durum import onbellek_temizle
except ImportError:                      # onbellek yoksa: sessiz gecis
    def onbellek_temizle(ad=None):
        return None


# Plan metinleri her gosterimde yeniden uretilir; sozluk tablosu icin
# tam okuma yerine sinirli okuma yeterli (LLM zaten ilk N satiri kullaniyor).
SOZLUK_LIMITI = 1000
SEMA_LIMITI = 100

# Adim anahtarlari — kod_bloklari girdilerindeki 3. alan (kaynak).
KURAL_KAYNAK = "kural"
KESIF_KAYNAK = "kesif"

# Kural tabanli donusumlerin train'den ogrenilen parametreleri
WINSOR_ALT, WINSOR_UST = 0.01, 0.99
RANK_IZGARA = 100        # train yuzdelik izgarasi: 101 nokta


def _meta_yasak(durum):
    """Hedef / kimlik / donem: uretilen kolonlarda da kaynak kolonlarda da
    kullanilmaz. llm.py zaten eliyor; bu ikinci savunma katmani."""
    m = durum.get("meta") or {}
    return {x for x in (m.get("target"), m.get("id"), m.get("donem")) if x}


def _blok_kaynak(blok):
    return blok[2] if isinstance(blok, (list, tuple)) and len(blok) > 2 else None


def _adim_temizle(durum, *kaynaklar):
    """Adim yeniden calistirildiginda o adima ait kayitlari ONCE siler.

    Boylece "geri dön → yeniden onayla" akisinda durum["uretilen"] ile
    veri setinde gercekten duran kolonlar birbirinden ayrilmaz.
    Doner: silinen kolon adlari kumesi.
    """
    kaynaklar = set(kaynaklar)
    bloklar = durum.get("kod_bloklari") or []
    silinen = set()
    for blok in bloklar:
        if _blok_kaynak(blok) not in kaynaklar:
            continue
        for satir in (blok[1] or []):
            if isinstance(satir, (list, tuple)) and satir and satir[0]:
                silinen.add(satir[0])

    durum["kod_bloklari"] = [b for b in bloklar
                             if _blok_kaynak(b) not in kaynaklar]
    durum["uretilen"] = [a for a in (durum.get("uretilen") or [])
                         if a not in silinen]
    harita = durum.get("uretilen_kaynak")
    if isinstance(harita, dict):
        for k in list(harita):
            harita[k] = [a for a in (harita.get(k) or []) if a not in silinen]
    return silinen


def _kaynaga_yaz(durum, kaynak, adlar):
    """Uretilen degiskeni KIM uretti: kural tabanli mi, AI kesfi mi?

    durum["uretilen"] duz bir ad listesi; hangi degiskenin hangi yoldan
    geldigini tutmuyordu. Ust serit "kural kac tane, AI kac tane, bunlarin
    kaci finalde kaldi" diye sorunca bu ayrim gerekli oldu."""
    harita = durum.get("uretilen_kaynak")
    if not isinstance(harita, dict):
        harita = {}
    mevcut = set(harita.get(kaynak) or [])
    # Adim yeniden calistirilabilir: _adim_temizle o kaynagin eski
    # adlarini zaten dusurdu, burada yalnizca guncel liste birikir.
    harita[kaynak] = sorted(mevcut | set(adlar))
    durum["uretilen_kaynak"] = harita


def _secimi_uygula(ogeler, secim):
    """secim: 0 tabanli indis listesi ya da None/bos -> hepsi."""
    if not secim:
        return list(ogeler)
    istenen = {int(i) for i in secim}
    return [o for i, o in enumerate(ogeler) if i in istenen]


def _uretim_kodu_yaz(durum, hedef):
    """Biriken TUM bloklarla uretim_kodu.py dosyasini yeniden yazar.

    Hem kural hem kesif adiminin sonunda cagrilir; boylece hangi adim
    calisirsa calissin dosya guncel olur ve kural adiminda uretilen
    bloklar da dosyaya girer.
    Doner: (yazildi_mi, hata_metni)
    """
    bloklar = durum.get("kod_bloklari") or []
    if not bloklar:
        return False, None
    try:
        script = ifade_mod.script_olustur(
            kaynak_dataset=(durum.get("baz") or {}).get("dataset")
            or durum["veri_seti"],
            hedef_dataset=hedef, doldurma=None,
            # script_olustur 2'li blok bekliyor; kaynak alani atilir.
            bloklar=[(b[0], b[1]) for b in bloklar])
        _folder().upload_stream("/uretim_kodu.py", script.encode("utf-8"))
        return True, None
    except Exception as e:
        return False, str(e)[:120]


def kural_plan(durum):
    sz = sozluk_oku(durum)   # CSV yedegini de okur
    plan, hata = llm_mod.gelenekse_plan_oner(
        sozluk_df=sz, haric=durum.get("haric_kolonlar", []),
        meta=durum.get("meta", {}))
    durum["plan"] = plan or []

    if hata:
        # Hatayi yutma: kullaniciya goster, adimi ilerletme.
        return ("Dönüşüm planını hazırlayamadım.\n\n  %s\n\n"
                "Tekrar denemek için onaylayın, bu adımı geçebilir ya da "
                "önceki adıma dönebilirsiniz." % hata)

    if not plan:
        return ("Kullanılabilir bir plan çıkaramadım. Bu adımı geçebilir ya da "
                "önceki adıma dönebilirsiniz.")

    kirilim = {}
    for p in plan:
        kirilim[p["donusum"]] = kirilim.get(p["donusum"], 0) + 1

    satirlar = []
    for i, p in enumerate(plan, 1):
        satirlar.append("  %2d. %-24s → %-7s  (%s kolon)"
                        % (i, p["ad"][:24], p["donusum"], _sayi(len(p["kolonlar"]))))
        if p.get("gerekce"):
            satirlar.append("      %s" % p["gerekce"][:88])

    return ("Kolon açıklamalarını inceledim ve %s klasik dönüşüm ailesi "
            "belirledim (%s):\n\n%s\n\n"
            "Toplam yaklaşık %s yeni kolon üretilecek.\n\n"
            "Tümünü uygulamak için onaylayın; bir kısmını seçmek için "
            "numaralarını belirtin (örneğin 1, 3, 5)."
            % (_sayi(len(plan)),
               " · ".join("%s %s" % (v, k) for k, v in sorted(kirilim.items())),
               "\n".join(satirlar),
               _sayi(sum(len(p["kolonlar"]) for p in plan))))

def _ogrenme_serisi(s, ogren_maske):
    """Parametrelerin ogrenilecegi satirlar. Maske yoksa tum satirlar."""
    if ogren_maske is None:
        return s.dropna()
    try:
        return s[ogren_maske].dropna()
    except Exception:
        return s.dropna()


def _rank_izgarasi(s_ogren):
    """Train dagiliminin 101 noktali yuzdelik izgarasi (rank referansi)."""
    if len(s_ogren) < 2:
        return None
    try:
        izgara = np.nanpercentile(s_ogren.to_numpy(dtype=float),
                                  np.linspace(0, 100, RANK_IZGARA + 1))
    except Exception:
        return None
    izgara = np.asarray(izgara, dtype=float)
    if not np.isfinite(izgara).all():
        return None
    return [round(float(x), 6) for x in izgara]


def _izgara_rank(s, izgara):
    """Degeri TRAIN izgarasina gore yuzdeye cevirir (0, 1]. NaN -> NaN."""
    ref = np.asarray(izgara, dtype=float)
    v = pd.to_numeric(s, errors="coerce")
    p = np.searchsorted(ref, v.to_numpy(dtype=float),
                        side="right") / float(len(ref))
    return pd.Series(p, index=s.index, dtype=float).where(v.notna())


def _tekli(df, kolonlar, d, ogren_maske=None, kayit=None):
    """Tekli donusumler.

    LEAKAGE: winsorize kesim noktalari ve rank referans dagilimi YALNIZCA
    ogren_maske (train) satirlarindan ogrenilir, sonra TUM satirlara
    uygulanir. Maske verilmezse eski davranis (tum satirlar) korunur.
    kayit verilirse ogrenilen parametreler oraya yazilir.
    """
    y = {}
    for k in kolonlar:
        if k not in df.columns:
            continue
        s = pd.to_numeric(df[k], errors="coerce")
        ogren = _ogrenme_serisi(s, ogren_maske)

        if d == "log":
            y["%s__LOG" % k] = np.log1p(s.clip(lower=0))
        elif d == "rank":
            izgara = _rank_izgarasi(ogren)
            if izgara is None:
                continue
            y["%s__RANK" % k] = _izgara_rank(s, izgara)
            if kayit is not None:
                kayit.setdefault("rank", {})[k] = {
                    "izgara": izgara, "nokta": len(izgara), "kaynak": "train"}
        elif d == "winsor":
            if len(ogren) < 2:
                continue
            alt = float(ogren.quantile(WINSOR_ALT))
            ust = float(ogren.quantile(WINSOR_UST))
            if not (np.isfinite(alt) and np.isfinite(ust)):
                continue
            y["%s__WNS" % k] = s.clip(alt, ust)
            if kayit is not None:
                kayit.setdefault("winsor", {})[k] = {
                    "alt": round(alt, 6), "ust": round(ust, 6),
                    "q": [WINSOR_ALT, WINSOR_UST], "kaynak": "train"}
    return y

def _ikili(df, kolonlar, d, ogren_maske=None, kayit=None):
    """Ikili donusumler: fark ve oran.

    Bu iki donusum satir bazlidir; hicbir GLOBAL istatistik (quantile,
    ortalama, rank) kullanmaz — dolayisiyla train/test sinirini asan bir
    hesap yok. Imza simetri icin ogren_maske/kayit alir.
    """
    y = {}
    for i in range(len(kolonlar) - 1):
        a, b = kolonlar[i], kolonlar[i + 1]
        if a not in df.columns or b not in df.columns:
            continue
        sa = pd.to_numeric(df[a], errors="coerce")
        sb = pd.to_numeric(df[b], errors="coerce")
        if d == "delta":  y["%s__MINUS__%s" % (a, b)] = sa - sb
        elif d == "oran": y["%s__DIV__%s" % (a, b)] = sa / sb.replace(0, np.nan)
    return y

def _rank_kod(k, izgara):
    """Train izgarasini gomen, tek deyimlik ve calistirilabilir rank satiri."""
    ifade_mod.ad_dogrula(k)
    ifade_mod.ad_dogrula("%s__RANK" % k)
    return ('df["%s__RANK"] = pd.Series(np.searchsorted(np.array(%r), '
            '_s(df, "%s").to_numpy(dtype=float), side="right") / %s, '
            'index=df.index).where(_s(df, "%s").notna())'
            % (k, [float(x) for x in izgara], k, float(len(izgara)), k))


def _winsor_kod(k, alt, ust):
    ifade_mod.ad_dogrula(k)
    ifade_mod.ad_dogrula("%s__WNS" % k)
    return ('df["%s__WNS"] = _s(df, "%s").clip(%r, %r)'
            % (k, k, float(alt), float(ust)))


def kural_uygula(durum, secim=None):
    plan = _secimi_uygula(durum.get("plan") or [], secim)
    hedef = "%s_ENRICHED" % durum["veri_seti"]

    # IDEMPOTANS: bu adim yeniden calistiriliyorsa once kendi kayitlarini
    # sil. Kaynak her zaman baz set oldugu icin _ENRICHED uzerine yazilir
    # ve kesif adiminin urettigi kolonlar da veriden dusmus olur; onlarin
    # kayitlarini da temizleyip kullaniciya bildiriyoruz.
    silinen_kural = _adim_temizle(durum, KURAL_KAYNAK)
    silinen_kesif = _adim_temizle(durum, KESIF_KAYNAK)

    if not plan:
        return ("Bu adımda üretim yapılmadı." +
                _yeniden_notu(silinen_kural, silinen_kesif))

    # Hazirlik tablosu varsa ondan okunur; tip donusumleri oraya ZATEN
    # islenmis halde yazildi (baz_uygula modelleme_df ile okuyor).
    # Hazirlik yoksa ham tabloya dusuluyor ve donusumler OKUMADA
    # uygulanmali - yoksa kullanicinin teyitte cevirdigi kolon burada
    # eski tipiyle gorunurdu.
    _baz = (durum.get("baz") or {}).get("dataset")
    df = _df_oku(_baz) if _baz else modelleme_df(durum)
    tr, _te = maskeler(durum, df)            # LEAKAGE SINIRI
    yasak = _meta_yasak(durum)
    ogrenilen = {}

    uretilen, kod_satirlari, elenen = {}, [], []
    for p in plan:
        d = p["donusum"]
        # Ikinci savunma katmani: hedef/kimlik/donem hicbir dönüşüme girmez
        kolonlar = [k for k in (p.get("kolonlar") or [])
                    if k in df.columns and k not in yasak]
        aciklama = "%s: %s" % (p["ad"], p.get("gerekce", ""))

        if d in ("delta", "oran"):
            yeni = _ikili(df, kolonlar, d)
            for i in range(len(kolonlar) - 1):
                a, b = kolonlar[i], kolonlar[i + 1]
                ad = ("%s__MINUS__%s" if d == "delta" else "%s__DIV__%s") % (a, b)
                if ad not in yeni or ad in yasak:
                    continue
                ifd = ("fark(%s, %s)" if d == "delta" else "%s / %s") % (a, b)
                try:
                    kod = ifade_mod.python_kodu(ad, ifd)
                except Exception as e:
                    elenen.append((ad, str(e)[:60]))
                    continue
                uretilen[ad] = yeni[ad]
                kod_satirlari.append((ad, kod, aciklama))
        else:
            yeni = _tekli(df, kolonlar, d, ogren_maske=tr, kayit=ogrenilen)
            for k in kolonlar:
                for sonek, ifd in (("__LOG", "log1p(%s)" % k),):
                    ad = k + sonek
                    if ad not in yeni or ad in yasak:
                        continue
                    try:
                        kod = ifade_mod.python_kodu(ad, ifd)
                    except Exception as e:
                        elenen.append((ad, str(e)[:60]))
                        continue
                    uretilen[ad] = yeni[ad]
                    kod_satirlari.append((ad, kod, aciklama))

                if k + "__RANK" in yeni and (k + "__RANK") not in yasak:
                    try:
                        kod = _rank_kod(
                            k, ogrenilen.get("rank", {})[k]["izgara"])
                    except Exception as e:
                        elenen.append((k + "__RANK", str(e)[:60]))
                    else:
                        uretilen[k + "__RANK"] = yeni[k + "__RANK"]
                        kod_satirlari.append((k + "__RANK", kod, aciklama))

                if k + "__WNS" in yeni and (k + "__WNS") not in yasak:
                    par = ogrenilen.get("winsor", {})[k]
                    try:
                        kod = _winsor_kod(k, par["alt"], par["ust"])
                    except Exception as e:
                        elenen.append((k + "__WNS", str(e)[:60]))
                    else:
                        uretilen[k + "__WNS"] = yeni[k + "__WNS"]
                        kod_satirlari.append((k + "__WNS", kod, aciklama))

    for ad, seri in uretilen.items():
        df[ad] = seri

    try:
        dataiku.Dataset(hedef).write_with_schema(df)
    except Exception as e:
        return ("Üretilen %s kolon hesaplandı ama '%s' veri setine "
                "YAZILAMADI: %s\n\n"
                "Dataiku akışında bu veri setini oluşturup adımı yeniden "
                "çalıştırın. Bu adımda hiçbir değişken kaydedilmedi."
                % (_sayi(len(uretilen)), hedef, str(e)[:120]))
    # Bu yazma _yaz() uzerinden GECMIYOR (hedef dataset yoksa farkli bir
    # hata metni gerekiyor), dolayisiyla onbellek iptalini kendisi yapar.
    # Eskiden her `uygula` adimindan sonra onbellek KOMPLE bosaltiliyordu
    # ve bu kacak gorunmuyordu; o toptan bosaltma kaldirildi (kullanici
    # sikayeti: adimlar dakikalarca suruyordu).
    onbellek_temizle(hedef)      # tablo degisti; bayat kopya okunmasin

    durum["uretilen"] = sorted(set(durum.get("uretilen") or []) | set(uretilen))
    _kaynaga_yaz(durum, KURAL_KAYNAK, uretilen)
    durum["kod_bloklari"] = (durum.get("kod_bloklari") or []) + \
        [["Kural tabanlı üretim", kod_satirlari, KURAL_KAYNAK]]
    # Ogrenilen kesim noktalari ve rank referansi: tekrar uretilebilirlik
    ogr = durum.get("ogrenilen_donusum") or {}
    ogr["kural"] = ogrenilen
    durum["ogrenilen_donusum"] = ogr

    _yazildi, kod_hata = _uretim_kodu_yaz(durum, hedef)

    elenen_not = ("\n\n%s" % _liste(
        "Geçersiz değişken adı nedeniyle elenen %s öneri:" % _sayi(len(elenen)),
        ["%s: %s" % e for e in elenen], 6)) if elenen else ""
    kod_not = ("\n\nÜretim kodu dosyası yazılamadı: %s" % kod_hata) if kod_hata \
        else "\n\nTüm üretimin Python kodu PROJE_HAFIZASI/uretim_kodu.py dosyasında."

    return ("%s dönüşümden %s yeni kolon üretildi ve %s veri setine yazıldı.\n"
            "Winsorize kesim noktaları ve sıralama referans dağılımı "
            "YALNIZCA geliştirme satırlarından öğrenildi.%s%s%s"
            % (_sayi(len(plan)), _sayi(len(uretilen)), hedef,
               _yeniden_notu(silinen_kural, silinen_kesif),
               elenen_not, kod_not))


def _yeniden_notu(silinen_kural, silinen_kesif):
    """Adim yeniden calistirildiginda neyin gectigini kullaniciya yaz."""
    parcalar = []
    if silinen_kural:
        parcalar.append("Bu adım yeniden çalıştırıldı: önceki turda üretilen "
                        "%s kural tabanlı kolonun kaydı silindi ve yerine "
                        "yenisi yazıldı." % _sayi(len(silinen_kural)))
    if silinen_kesif:
        parcalar.append("Kaynak baz setten yeniden kurulduğu için keşif "
                        "adımında üretilen %s kolon veri setinden düştü; "
                        "kayıtları da temizlendi. Keşif adımına gelince "
                        "yeniden üretilecekler." % _sayi(len(silinen_kesif)))
    return ("\n\n" + "\n".join(parcalar)) if parcalar else ""

def kesif_plan(durum):
    baz = (durum.get("baz") or {}).get("dataset") or durum["veri_seti"]
    kolonlar = list(_df_oku(baz, limit=SEMA_LIMITI).columns)
    sz = sozluk_oku(durum)   # CSV yedegini de okur
    yasak = _meta_yasak(durum)

    ham, hata = llm_mod.kesif_ifade_oner(
        sozluk_df=sz, kolonlar=kolonlar, meta=durum.get("meta", {}),
        sfa_ozet=(durum.get("sfa") or {}).get("en_iyi"))

    if hata:
        # Hatayi yutma: kullaniciya goster, adimi ilerletme.
        durum["hipotez"] = []
        return ("Keşif önerilerini alamadım.\n\n  %s\n\n"
                "Tekrar denemek için onaylayın, bu adımı geçebilir ya da "
                "önceki adıma dönebilirsiniz." % hata)

    gecerli, reddedilen, ad_elenen = [], [], 0
    for o in (ham or []):
        ok, dogrulama_hatasi, kullanilan = ifade_mod.dogrula(o["ifade"], kolonlar)
        if not ok:
            reddedilen.append((o.get("ad", "?"), dogrulama_hatasi))
            continue
        if o.get("ad") in yasak or (set(kullanilan) & yasak):
            reddedilen.append((o.get("ad", "?"), "hedef/kimlik kolonu kullanılamaz"))
            continue
        # LLM'in urettigi ad sablona enjeksiyon yapabilir; ifade.py artik
        # gecersiz adda ValueError firlatiyor. Oneriyi atla, sayisini bildir.
        try:
            o["kod"] = ifade_mod.python_kodu(o["ad"], o["ifade"])
        except Exception as e:
            ad_elenen += 1
            reddedilen.append((o.get("ad", "?"), str(e)[:60]))
            continue
        o["kolonlar"] = kullanilan
        gecerli.append(o)

    durum["hipotez"] = gecerli
    durum["_kesif_ad_elenen"] = ad_elenen
    if not gecerli:
        return ("Bu turda geçerli bir hipotez üretilemedi.\n\n%s\n\n"
                "Adımı geçebilirsiniz."
                % _liste("Kontrolden geçemeyen öneriler:",
                         ["%s: %s" % r for r in reddedilen], 6))

    satirlar = []
    for i, o in enumerate(gecerli, 1):
        satirlar.append("  %2d. %s" % (i, o["ad"]))
        satirlar.append("      %s" % o["ifade"])
        if o.get("gerekce"):
            satirlar.append("      %s" % o["gerekce"][:88])

    red_not = ("\n\n%s" % _liste("Güvenlik kontrolünden geçemeyenler:",
                                 ["%s: %s" % r for r in reddedilen], 5)) if reddedilen else ""
    ad_not = ("\n\nBunların %s tanesi geçersiz değişken adı yüzünden elendi."
              % _sayi(ad_elenen)) if ad_elenen else ""

    return ("Klasik kalıpların dışına çıkarak %s yeni değişken hipotezi "
            "üretildi. Her ifade denetimden geçti.\n\n%s%s%s\n\n"
            "Tümünü uygulamak için onaylayın; seçmek için numaralarını belirtin."
            % (_sayi(len(gecerli)), "\n".join(satirlar), red_not, ad_not))

def kesif_uygula(durum, secim=None):
    hipotez = _secimi_uygula(durum.get("hipotez") or [], secim)
    hedef = "%s_ENRICHED" % durum["veri_seti"]

    # IDEMPOTANS: bu adimin onceki turda urettigi kolonlarin kaydini sil ve
    # veri setinden de dusur; aksi halde secim degisince eski kolonlar
    # tabloda kalir, durum["uretilen"] ile tablo birbirini tutmaz.
    silinen = _adim_temizle(durum, KESIF_KAYNAK)

    if not hipotez:
        mesaj = "Bu adımda üretim yapılmadı."
        if silinen:
            mesaj += ("\n\nÖnceki turda üretilen %s keşif kolonunun kaydı "
                      "silindi." % _sayi(len(silinen)))
        # Kural adiminin bloklari duruyorsa uretim kodu yine guncel kalsin
        _uretim_kodu_yaz(durum, hedef)
        return mesaj

    kaynak = hedef if _dataset_var_mi(hedef) else \
        ((durum.get("baz") or {}).get("dataset") or durum["veri_seti"])
    df = _df_oku(kaynak)
    eski = [c for c in silinen if c in df.columns]
    if eski:
        df = df.drop(columns=eski)

    yasak = _meta_yasak(durum)
    uretilen, kod_satirlari, hatali = [], [], []
    for h in hipotez:
        if h.get("ad") in yasak:
            hatali.append((h.get("ad", "?"), "hedef/kimlik kolonu üretilemez"))
            continue
        try:
            kod = h.get("kod") or ifade_mod.python_kodu(h["ad"], h["ifade"])
            df[h["ad"]] = ifade_mod.degerlendir(df, h["ifade"])
            uretilen.append(h["ad"])
            kod_satirlari.append((h["ad"], kod,
                                  "%s  |  %s" % (h["ifade"], h.get("gerekce", ""))))
        except Exception as e:
            hatali.append((h["ad"], str(e)[:60]))

    try:
        dataiku.Dataset(hedef).write_with_schema(df)
    except Exception as e:
        return ("Üretilen %s kolon hesaplandı ama '%s' veri setine "
                "YAZILAMADI: %s\n\n"
                "Dataiku akışında bu veri setini oluşturup adımı yeniden "
                "çalıştırın. Bu adımda hiçbir değişken kaydedilmedi."
                % (_sayi(len(uretilen)), hedef, str(e)[:120]))
    # Bu yazma _yaz() uzerinden GECMIYOR (hedef dataset yoksa farkli bir
    # hata metni gerekiyor), dolayisiyla onbellek iptalini kendisi yapar.
    # Eskiden her `uygula` adimindan sonra onbellek KOMPLE bosaltiliyordu
    # ve bu kacak gorunmuyordu; o toptan bosaltma kaldirildi (kullanici
    # sikayeti: adimlar dakikalarca suruyordu).
    onbellek_temizle(hedef)      # tablo degisti; bayat kopya okunmasin

    durum["uretilen"] = sorted(set(durum.get("uretilen") or []) | set(uretilen))
    _kaynaga_yaz(durum, KESIF_KAYNAK, uretilen)
    durum["kod_bloklari"] = (durum.get("kod_bloklari") or []) + \
        [["AI değişken keşfi", kod_satirlari, KESIF_KAYNAK]]

    _yazildi, kod_hata = _uretim_kodu_yaz(durum, hedef)

    hata_not = ("\n\n%s" % _liste("Hesaplanamayanlar:",
                                  ["%s: %s" % h for h in hatali], 5)) if hatali else ""
    yeniden_not = ("\n\nBu adım yeniden çalıştırıldı: önceki turun %s kolonu "
                   "hem kayıttan hem veri setinden kaldırıldı."
                   % _sayi(len(silinen))) if silinen else ""
    kod_not = ("\n\nÜretim kodu dosyası yazılamadı: %s" % kod_hata) if kod_hata \
        else ("\n\nTüm üretimin (kural + keşif) Python kodu "
              "PROJE_HAFIZASI/uretim_kodu.py dosyasında.")

    return ("%s hipotez üretildi ve %s veri setine yazıldı.%s%s%s"
            % (_sayi(len(uretilen)), hedef, hata_not, yeniden_not, kod_not))
