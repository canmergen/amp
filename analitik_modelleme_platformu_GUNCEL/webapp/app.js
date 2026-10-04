/* YÜKLEME HATASI GÖRÜNÜR OLSUN. Bu dosyada bir hata atılırsa geri kalan
   kod çalışmaz ve ekran sessizce BOŞ kalır (kullanıcı bildirimi:
   "refresh bütün ekranı boşalttı"). Hata artık sohbet alanına yazılıyor;
   en sık sebebi index.html / style.css / app.js'in farklı sürümlerde
   yapıştırılmış olması. */
window.addEventListener("error", function (olay) {
    try {
        const alan = document.getElementById("sohbet");
        if (!alan || document.getElementById("yukleme-hatasi")) return;
        const kutu = document.createElement("div");
        kutu.id = "yukleme-hatasi";
        kutu.setAttribute("role", "alert");
        kutu.style.cssText = "margin:12px;padding:10px 14px;border:1px solid #D51115;"
            + "border-radius:6px;background:#FDF1F1;color:#D51115;font-size:13px;line-height:1.5";
        kutu.textContent = "Arayüz yüklenirken bir hata oluştu: "
            + ((olay && olay.message) || "bilinmeyen hata")
            + ". webapp'teki index.html, style.css ve app.js dosyalarının aynı "
            + "sürümden yapıştırıldığını kontrol edip sayfayı yenileyin.";
        alan.appendChild(kutu);
    } catch (e) { /* uyarı da çizilemezse yapacak bir şey yok */ }
});

/* Calisma kimligi: F5 saatlerce suren calismayi silmesin diye kalici.
   Dataiku artifact'inda depolama engellenebilir; o zaman sabit "ana"
   kimligine dusuyoruz — backend anahtari zaten KULLANICI kimliginden
   turetiyor, istemcinin gonderdigi deger yalnizca ayni kullanicinin
   birden fazla calismasini ayiriyor. */
const OTURUM_DEPO_ANAHTARI = "fe_agent_calisma_id";

function depoOku(anahtar) {
    for (const depo of ["sessionStorage", "localStorage"]) {
        try {
            const v = window[depo].getItem(anahtar);
            if (v) return v;
        } catch (e) { /* engelli depolama: yok say */ }
    }
    return null;
}

function depoYaz(anahtar, deger) {
    let yazildi = false;
    for (const depo of ["sessionStorage", "localStorage"]) {
        try { window[depo].setItem(anahtar, deger); yazildi = true; }
        catch (e) { /* engelli depolama: yok say */ }
    }
    return yazildi;
}

/* ÇALIŞMA KİMLİĞİNİ SUNUCU VERİR. Eskiden burada rastgele bir kimlik
   ("ck2m9x1qz") üretiliyordu ve PROJE_HAFIZASI'nda okunmayan dosya
   adlarına dönüşüyordu. Artık kimlik çalışmanın SIRA NUMARASI ("03");
   kayıtlı değilse boş gider ve /karsilama kullanıcının en son
   çalışmasını açıp numarasını döndürür (bkz. oturumAyarla).
   Tarayıcıda eski bir kimlik kayıtlıysa o çalışma aynen açılır.
   let: "Yeni Çalışma" ve "Arşiv" kimliği değiştiriyor; bütün
   istekler değişkeni çağrı anında okuyor. */
let OTURUM_ID = depoOku(OTURUM_DEPO_ANAHTARI) || "";

function oturumAyarla(kimlik) {
    if (!kimlik || kimlik === OTURUM_ID) return;
    OTURUM_ID = String(kimlik);
    depoYaz(OTURUM_DEPO_ANAHTARI, OTURUM_ID);
}

/* Idempotenslik: backend'in isledigi son tur numarasi. Her mesaj
   TUR_NO + 1 ile gider; yanit gelmeden artmaz, boylece timeout sonrasi
   tekrar gonderim ayni turu tasir ve adim IKI KEZ uygulanmaz. */
let TUR_NO = 0;

/* Uzun islemde kullaniciya gosterilecek sinir ve iptal altyapisi */
const ISTEK_ZAMAN_ASIMI = 300000;        // 5 dakika
let geriHedefi = null;                   // geri donulen adim anahtari
let istekKontrol = null;                 // AbortController
let istekDurumu = "";                    // "iptal" | "zamanasimi" | ""
let sonYanitMetni = null;

/* Calismanin nerede saklandigi ve sifirlama dugmesinin adi: metinlerde
   tek kaynaktan kullanilir (backend: fe_agent.akis_durum.HAFIZA_FOLDER). */
const HAFIZA_KLASORU = "PROJE_HAFIZASI";
/* Sembol metne DAHIL: kullanici dugmeyi ekranda ikonuyla ariyor, "Yeni
   calisma baslat" yazisi tek basina Dataiku'nun REFRESH dugmesini de
   tarif ediyordu. */
const YENI_CALISMA_ETIKETI = "⟳ Yeni Çalışma";
const CALISMALARIM_ETIKETI = "Arşiv";

const GORSEL = {
    banner:     getWebAppBackendUrl("gorsel/banner"),
    bot:        getWebAppBackendUrl("gorsel/bot"),
    karsilama:  getWebAppBackendUrl("gorsel/karsilama"),
    dusunme:    getWebAppBackendUrl("gorsel/dusunme"),
    user:       getWebAppBackendUrl("gorsel/user"),
    zeminAcik:  getWebAppBackendUrl("gorsel/zemin_acik"),
    zeminKoyu:  getWebAppBackendUrl("gorsel/zemin_koyu"),
};

const sohbetEl    = document.getElementById("sohbet");
const sohbetAlan  = document.getElementById("sohbet-alani");
const kutuEl      = document.getElementById("kutu");
const gonderEl    = document.getElementById("gonder");
const fazEl       = document.getElementById("faz-listesi");
const sozlukCipEl = document.getElementById("sozluk-cip");
const seritEl     = document.getElementById("ozet-serit");
const bannerEl    = document.getElementById("banner");
/* Ortak aksiyon şeridi KALDIRILDI: düğmeler blokların içine taşındı
   (bkz. blokBasligiEkle / blokOnayEkle). Kalan iki referans giriş
   bölgesinin kilidi için. */
const girisBolge  = document.getElementById("giris-bolge");
const kabukEl     = document.getElementById("kabuk");

const sayfalar    = { calisma: document.getElementById("sayfa-calisma"),
                      ozet:    document.getElementById("sayfa-ozet") };
const sekmeler    = Array.from(document.querySelectorAll(".sekme"));

const analizGovde = document.getElementById("analiz-govde");
const analizSekme = Array.from(document.querySelectorAll(".analiz-sekme"));
const durumRozet = document.getElementById("durum-rozet");

let FAZLAR = [];
let DUZ_ADIMLAR = [];          // sira -> {anahtar, no, baslik, aciklama}
let aktifAdim = 0;
let aktifMod = null;           // "A" | "B" | "C"
let acikFazlar = new Set();
let mesgul = false;

/* Hata olursa tiklanan kart grubunu / secim kartini eski haline dondurur */
let geriAlKilit = null;
/* KONTROLDEN GEÇMEDEN ONAY YOK (kullanıcı kararı). Form kartı
   gönderilince "Kontrol Ediliyor…" der; "✓ Girdiler Onaylandı" ancak
   sunucu girdiyi KABUL EDİNCE yazılır (bkz. gonderimSonucu). Reddederse
   (tablo yok, sözlükte kolon adı ya da açıklama kolonu yok...) kart
   onaylı görünmez: yerine düzeltilebilir yeni form gelir. */
let bekleyenGonderim = null;   // {kart, durumEl, adim, geriAl, ekler?}
/* Yanit sonrasi odaklanilacak yeni etkilesimli oge */
let yeniOdak = null;

/* Analiz Merkezi: backend her yanitta "analiz" gonderir.
   Bagli sekmeler backend verisiyle cizilir; kalanlar (dagilim, iliski)
   henuz hesaplanmiyor ve iskelet olarak duruyor. */
let ANALIZ_VERI = {};
let aktifAnalizSekme = "ozet";

/* Katlanabilir ozet kartlarinin acik/kapali hali: {kart basligi -> bool}.
   Panel her backend yanitinda BASTAN ciziliyor; bu harita cizim disinda
   durmasaydi kullanicinin actigi kart bir sonraki yanitta kendiliginden
   kapanirdi. Oturumluktur, localStorage'a YAZILMAZ. */
/* "ozet" = VERİ & SÖZLÜK sekmesi (data-tab degeri bu).
   EKSİK DEĞER sekmesi kaldirildi; ayni panel govdesi artik "hazirlik"
   anahtariyla geliyor (bkz. akis_panel.hazirlik_paneli). */
/* UC SEKME: "degisken" (DEĞİŞKEN ANALİZİ: dağılım + SFA + eksik değer)
   ve "bolme" (BÖLME & VALİDASYON). */
const BAGLI_SEKMELER = ["ozet", "degisken", "bolme"];

/* Dataset listesi: "yukleniyor" | "hazir" | "bos" | "hata"
   "bos": liste okundu ama proje icinde dataset yok -> elle yazmaya izin ver */
let DATASETLER = [];
let DATASET_DURUMU = "yukleniyor";
const DATASET_DINLEYICILER = [];   // liste gelince formlar kendini tazeler

bannerEl.src = GORSEL.banner;
bannerEl.onerror = () => { bannerEl.style.display = "none"; };


/* ==================== Metin yardımcıları ==================== */
/* Bos deger her yerde ∅ ile gosterilir. Uzun/orta tire (U+2014, U+2013) backend'den,
   LLM'den ya da sabit metinlerden gelse de ekranda normal tireye (-) cevrilir. */
const BOS_SIMGE = "\u2205";          // ∅

function tireSade(s) {
    return String(s === null || s === undefined ? "" : s)
        .replace(/[ \t]*[\u2014\u2013][ \t]*/g, " - ");
}

function degerGoster(v) {
    if (v === null || v === undefined) return BOS_SIMGE;
    const s = String(v).trim();
    if (s === "" || s === "\u2014" || s === "\u2013" || s === "-") return BOS_SIMGE;
    return tireSade(s);
}

/* Cumle duzeni: yalnizca ilk harf buyur. Turkce kurala gore (i -> İ). */
function ilkHarfBuyuk(s) {
    const t = tireSade(s).trim();
    return t ? t.charAt(0).toLocaleUpperCase("tr-TR") + t.slice(1) : "";
}

/* Başlık Büyük Harfi: her kelime büyük başlar, BAĞLAÇLAR hariç.
   Üst şerit satırlarında kullanılıyor ("kural tabanlı üretim + AI keşfi"
   -> "Kural Tabanlı Üretim + AI Keşfi").

   DOKUNULMAYANLAR
     - Zaten büyük harf içeren kelime (AI, SFA, KS, OOT, Gini, Δ AUC):
       kısaltmaları "Ai", "Sfa" yapmak okunurluğu bozar.
     - Rakam içeren kelime (1.042, %3,8): büyük harfi yok.
   İlk kelime bağlaç olsa bile büyük başlar; cümle başı kuralı. */
/* YALNIZCA gerçek bağlaçlar. Listeye "sonra", "göre", "gibi" gibi
   edatlar da konmuştu; sonuç "Üretim Bittikten sonra Eleme Adımları
   Başlar" gibi yarım kalmış başlıklardı. Edatlar büyük başlar. */
const BAGLACLAR = new Set(["ve", "veya", "ile", "ya", "da", "de", "ki"]);

function baslikBuyuk(s) {
    const t = tireSade(s).trim();
    if (!t) return "";
    return t.split(/(\s+)/).map((parca, i) => {
        if (/^\s+$/.test(parca) || parca === "") return parca;
        /* Zaten büyük harf taşıyan ya da rakamlı kelimeye dokunma */
        if (/[A-ZÇĞİÖŞÜ]/.test(parca) || /\d/.test(parca)) return parca;
        const sade = parca.toLocaleLowerCase("tr-TR");
        if (i > 0 && BAGLACLAR.has(sade)) return sade;
        return sade.charAt(0).toLocaleUpperCase("tr-TR") + sade.slice(1);
    }).join("");
}


/* ==================== Tema ==================== */
/* Dataiku artifact'inda localStorage calismadigi icin tercih degiskende
   tutuluyor; sayfa yenilenince acik temaya doner.
   Ikon o an gecilecek temayi gosterir: aydinlikta ay, karanlikta gunes. */
let koyuTema = false;
const temaBtn = document.getElementById("tema-btn");

const AY_IKON = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" '
    + 'stroke="currentColor" stroke-width="2.2" stroke-linecap="round" '
    + 'stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"></path></svg>';

const GUNES_IKON = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" '
    + 'stroke="currentColor" stroke-width="2.2" stroke-linecap="round" '
    + 'stroke-linejoin="round"><circle cx="12" cy="12" r="4.2"></circle>'
    + '<path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4'
    + 'M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"></path></svg>';

function temaUygula() {
    kabukEl.classList.toggle("koyu", koyuTema);
    temaBtn.innerHTML = koyuTema ? GUNES_IKON : AY_IKON;
    temaBtn.title = koyuTema ? "Açık tema" : "Koyu tema";
    sohbetAlan.style.setProperty(
        "--sohbet-gorsel",
        "url('" + (koyuTema ? GORSEL.zeminKoyu : GORSEL.zeminAcik) + "')");
}
temaBtn.onclick = () => { koyuTema = !koyuTema; temaUygula(); };

[GORSEL.zeminAcik, GORSEL.zeminKoyu].forEach(u => { const i = new Image(); i.src = u; });
temaUygula();


/* ==================== Durum rozeti ==================== */
/* Rozet son isteğin sonucunu gosterir; backend cokse yesil kalmaz. */
/* Rozet OTURUMUN DURUMUNU gosterir: webapp arka uca ulasabiliyor mu?
   Eskiden "İşlem sürüyor" da buraya yaziliyordu; o istek-ici bir durum,
   oturumun saglikli olup olmadigiyla ilgisi yok ve her tikta rozet
   oynadigi icin "baglanti mi koptu?" izlenimi veriyordu. Mesguliyet
   zaten gonder dugmesinin ve aksiyonlarin kilitlenmesinden belli. */
const ROZET_METIN = {
    hazir:  "Oturum Aktif",
    hata:   "Bağlantı Yok"
};

function rozetGuncelle(kod) {
    if (!durumRozet) return;
    const metin = ROZET_METIN[kod] || ROZET_METIN.hazir;
    const nokta = durumRozet.querySelector(".nokta-yesil");
    durumRozet.textContent = "";
    if (nokta) durumRozet.appendChild(nokta);
    durumRozet.appendChild(document.createTextNode(" " + metin));
    durumRozet.classList.toggle("hata", kod === "hata");
    durumRozet.title = aktifMod ? ("Çalışma modu: " + aktifMod) : "Çalışma modu seçilmedi";
}


/* ==================== Sayfa geçişi ==================== */
function sayfaAc(ad) {
    Object.keys(sayfalar).forEach(k => sayfalar[k].classList.toggle("gizli", k !== ad));
    sekmeler.forEach(s => s.classList.toggle("aktif", s.dataset.sayfa === ad));
    cekmeceKapat();
    cekmeceButonlari.forEach(b => { b.hidden = (ad !== "calisma"); });
    /* ÖZET her açılışta tazelenir: doküman akışın son durumundan üretiliyor
       ve sekme kapalıyken değişmiş olabilir. */
    if (ad === "ozet") dokumanGetir();
}
sekmeler.forEach(s => { s.onclick = () => sayfaAc(s.dataset.sayfa); });


/* ==================== Dar ekran çekmeceleri ==================== */
/* Dar ekranda sol/sag panel gizlenmiyor; ust bardaki dugmelerle acilan
   cekmeceye donusuyor. */
const panelEl     = document.getElementById("panel");
const analizPanel = document.getElementById("analiz-panel");
const perdeEl     = document.getElementById("cekmece-perde");
const panelBtn    = document.getElementById("panel-btn");
const analizBtn   = document.getElementById("analiz-btn");
const cekmeceButonlari = [panelBtn, analizBtn].filter(Boolean);

function cekmeceKapat() {
    [panelEl, analizPanel].forEach(p => { if (p) p.classList.remove("acik"); });
    cekmeceButonlari.forEach(b => b.setAttribute("aria-expanded", "false"));
    if (perdeEl) perdeEl.hidden = true;
}

function cekmeceAc(panel, buton) {
    if (!panel) return;
    const acik = panel.classList.contains("acik");
    cekmeceKapat();
    if (!acik) {
        panel.classList.add("acik");
        if (buton) buton.setAttribute("aria-expanded", "true");
        if (perdeEl) perdeEl.hidden = false;
    }
}

if (panelBtn)  panelBtn.onclick  = () => cekmeceAc(panelEl, panelBtn);
if (analizBtn) analizBtn.onclick = () => cekmeceAc(analizPanel, analizBtn);
if (perdeEl)   perdeEl.onclick   = cekmeceKapat;
document.addEventListener("keydown", e => {
    if (e.key === "Escape") cekmeceKapat();
});


/* ==================== Panel genişlikleri ====================
   İki yan panelin genişliği kullanıcıya açık: aralarındaki tutamaklar
   sürüklenince --panel-en / --analiz-en değişkenleri #kabuk üzerine
   satır içi yazılıyor. Bütün yerleşim zaten bu iki değişkeni okuduğu
   için (CSS'teki #panel ve #analiz-panel kuralları, çekmece medya
   sorguları dahil) yapıda başka hiçbir şey değişmiyor.

   PANEL TAMAMEN KAPANMIYOR (kullanıcı kararı: "diğer bloğu tamamen
   silmeden"). Üç sınır birden korunuyor:
     - her panelin kendi alt sınırı (PANEL_SINIR / ANALIZ_SINIR),
     - her panelin üst sınırı,
     - ortadaki sohbet sütununa kalan SOHBET_TABAN.
   Üçüncüsü olmazsa iki paneli sonuna kadar açmak sohbeti sıfıra
   indirirdi; alt sınırlar tek başına bunu engellemiyor.

   Tercih depolanıyor (bkz. depoYaz): aynı kullanıcı sayfayı her
   yenilediğinde panelleri yeniden çekmek zorunda kalmasın. Depolama
   engelliyse sessizce varsayılana dönülür - genişlik kritik bir durum
   değil. */
const GENISLIK_DEPO_ANAHTARI = "fe_agent_panel_en";
const PANEL_SINIR  = { enAz: 168, enCok: 520 };
const ANALIZ_SINIR = { enAz: 248, enCok: 640 };
const SOHBET_TABAN = 420;
/* Çekmece eşiği: bunun altında paneller zaten çekmeceye dönüyor ve
   sürüklenecek bir sütun kalmıyor (bkz. style.css medya sorguları). */
const SURUKLEME_ESIGI = 945;

/* Üst çubuktaki "panel genişliklerini sıfırla" düğmesi KALDIRILDI
   (kullanıcı kararı). index.html eski sürümde kalırsa düğme burada
   sökülüyor; tek panel çift tıklamayla varsayılana döner. */
const genislikBtn = null;
{ const eski = document.getElementById("genislik-btn"); if (eski) eski.remove(); }
const tutamakSol = document.getElementById("tutamak-sol");
const tutamakSag = document.getElementById("tutamak-sag");

/* {sol, sag} — null olan "varsayılanda kalsın" demek. */
let panelEni = { sol: null, sag: null };
/* Tutamakların canlı ölçü etiketlerini tazeleyen işlevler. */
const OLCU_TAZELE = [];

function genislikOku() {
    const ham = depoOku(GENISLIK_DEPO_ANAHTARI);
    if (!ham) return;
    try {
        const v = JSON.parse(ham);
        const sayi = (x, s) => (typeof x === "number" && isFinite(x))
            ? Math.round(Math.max(s.enAz, Math.min(s.enCok, x))) : null;
        panelEni = { sol: sayi(v.sol, PANEL_SINIR), sag: sayi(v.sag, ANALIZ_SINIR) };
    } catch (e) { /* bozuk kayit: varsayilana don */ }
}

function genislikYaz() {
    try {
        depoYaz(GENISLIK_DEPO_ANAHTARI, JSON.stringify(panelEni));
    } catch (e) { /* engelli depolama: yok say */ }
}

/* Ölçülen gerçek genişlik: kullanıcı ilk kez sürüklemeye başladığında
   başlangıç noktası clamp() sonucu olmalı, --panel-en'in metni değil
   ("clamp(224px, 21vw, 296px)" sayı değil). */
function suankiEn(el) { return Math.round(el.getBoundingClientRect().width); }

function genislikUygula() {
    if (panelEni.sol === null) kabukEl.style.removeProperty("--panel-en");
    else kabukEl.style.setProperty("--panel-en", panelEni.sol + "px");
    if (panelEni.sag === null) kabukEl.style.removeProperty("--analiz-en");
    else kabukEl.style.setProperty("--analiz-en", panelEni.sag + "px");
    if (genislikBtn)
        genislikBtn.disabled = (panelEni.sol === null && panelEni.sag === null);
    OLCU_TAZELE.forEach(f => f());
}

function genislikSifirla() {
    panelEni = { sol: null, sag: null };
    genislikUygula();
    genislikYaz();
}

/* Bir panelin istenen genişliğini üç sınıra birden oturtur. */
function genislikKirp(taraf, istenen) {
    const sinir = taraf === "sol" ? PANEL_SINIR : ANALIZ_SINIR;
    const oteki = taraf === "sol" ? analizPanel : panelEl;
    /* Karşı panelin O ANKİ genişliği sabit kabul ediliyor: tek tutamak
       sürükleniyor, öteki yerinde duruyor. */
    const otekiEn = oteki ? suankiEn(oteki) : 0;
    const enCokYer = kabukEl.clientWidth - otekiEn - SOHBET_TABAN;
    const enCok = Math.min(sinir.enCok, Math.max(sinir.enAz, enCokYer));
    return Math.round(Math.max(sinir.enAz, Math.min(enCok, istenen)));
}

function tutamakKur(tutamak, taraf, el) {
    if (!tutamak || !el) return;
    let surukleniyor = false;
    let basX = 0, basEn = 0;

    /* Ölçü etiketi (piksel, "varsayılan") KALDIRILDI (kullanıcı kararı):
       sürüklerken ekranda sayı yazmıyor. Yalnızca ne işe yaradığını
       söyleyen ipucu kalıyor. Eski bir sürümden kalmış etiket sökülür. */
    tutamak.querySelectorAll(".tutamak-olcu").forEach(x => x.remove());
    tutamak.title = (taraf === "sol" ? "İş akışı paneli" : "Analiz paneli")
        + ": sürükleyerek genişletin ya da daraltın; "
        + "çift tıklama ilk genişliğe döndürür";

    function bitir() {
        if (!surukleniyor) return;
        surukleniyor = false;
        tutamak.classList.remove("suruklenirken");
        kabukEl.classList.remove("genislik-suruklemede");
        genislikYaz();
    }

    tutamak.addEventListener("pointerdown", (e) => {
        if (window.innerWidth < SURUKLEME_ESIGI) return;
        surukleniyor = true;
        basX = e.clientX;
        basEn = suankiEn(el);
        tutamak.classList.add("suruklenirken");
        kabukEl.classList.add("genislik-suruklemede");
        /* Fare tutamaktan kaysa bile olaylar buraya gelmeye devam etsin;
           yoksa hizli surukleyisde birakma olayi kaciriliyordu. */
        try { tutamak.setPointerCapture(e.pointerId); } catch (x) { /* yok say */ }
        e.preventDefault();
    });

    tutamak.addEventListener("pointermove", (e) => {
        if (!surukleniyor) return;
        /* Sol panel sağa doğru büyür, sağ panel SOLA doğru. */
        const delta = taraf === "sol" ? (e.clientX - basX) : (basX - e.clientX);
        panelEni[taraf] = genislikKirp(taraf, basEn + delta);
        genislikUygula();
    });

    tutamak.addEventListener("pointerup", bitir);
    tutamak.addEventListener("pointercancel", bitir);
    tutamak.addEventListener("lostpointercapture", bitir);

    /* Çift tıklama: yalnızca O paneli varsayılana döndürür. */
    tutamak.addEventListener("dblclick", () => {
        panelEni[taraf] = null;
        genislikUygula();
        genislikYaz();
    });

    /* Klavye: ok tuşlarıyla 16'şar piksel, Home varsayılana döndürür.
       Tutamak tabindex tasiyor; fare kullanamayan da ayarlayabilmeli. */
    tutamak.addEventListener("keydown", (e) => {
        if (window.innerWidth < SURUKLEME_ESIGI) return;
        const yon = e.key === "ArrowLeft" ? -1 : (e.key === "ArrowRight" ? 1 : 0);
        if (yon) {
            const isaret = taraf === "sol" ? yon : -yon;
            panelEni[taraf] = genislikKirp(taraf, suankiEn(el) + isaret * 16);
        } else if (e.key === "Home") {
            panelEni[taraf] = null;
        } else { return; }
        e.preventDefault();
        genislikUygula();
        genislikYaz();
    });
}

/* Pencere daralinca kirpma sinirlari degisir: sohbet sutunu tabanin
   altina dusmesin diye genislikler yeniden oturtuluyor. */
window.addEventListener("resize", () => {
    if (window.innerWidth < SURUKLEME_ESIGI) return;
    let degisti = false;
    ["sol", "sag"].forEach(taraf => {
        if (panelEni[taraf] === null) return;
        const yeni = genislikKirp(taraf, panelEni[taraf]);
        if (yeni !== panelEni[taraf]) { panelEni[taraf] = yeni; degisti = true; }
    });
    if (degisti) { genislikUygula(); genislikYaz(); }
});

if (genislikBtn) genislikBtn.onclick = () => genislikSifirla();
genislikOku();
genislikUygula();
tutamakKur(tutamakSol, "sol", panelEl);
tutamakKur(tutamakSag, "sag", analizPanel);


/* ==================== Aksiyon butonları ==================== */
/* Butonlar yalnizca anlamli olduklarinda gorunur:
   bekleyen "onay"  -> Onayla ve Uygula / Değiştir / Geri Dön
   bekleyen "girdi" -> secim kartta/formda yapilir; ilk adim degilse
                       yalnizca Geri Dön gorunur
   ilk ekran        -> hicbiri */
/* KENDI DUGMESI OLAN KARTLAR: bu tipler birincil/ikincil/üçüncül
   düğmelerini kartın içinde taşıyor. Genel aksiyon satırı da açılırsa
   ekranda aynı işi yapan iki düğme takımı yan yana duruyor ve kullanıcı
   hangisinin ne yaptığını düşünmek zorunda kalıyor. */
const KENDI_DUGMELI_KARTLAR = ["dogrulama", "bolme"];

/* ---- Sohbet kutusunun kilidi ----
   Ekranda bir kart, form ya da seçenek takımı varken kullanıcı bir
   CÜMLE yazmıyor; bir form dolduruyor. Kutu o sırada açık durunca iki
   ayrı "devam etme yolu" görünüyordu ve yazılan cümle çoğu zaman adıma
   ait bilgi içermediği için akış hiç ilerlemiyordu.

   SORU SORMA YOLU KAPANMIYOR: akış her an serbest soru kabul ediyor
   (akis_sohbet._soru_mu). Kutu kilitliyken bunu tamamen kapatmak gerçek
   bir yeteneği yok ederdi; kilidin yanındaki "Soru Sor" düğmesi kutuyu
   o tur için açar. */
/* Sohbet kutusu BÖLME STRATEJİSİ adımına kadar KAPALI (kullanıcı
   kararı: "buradaki bu hareketten sonra devreye direkt alınmalı,
   beklenme mantığına gerek yok").

   Neden o adıma kadar kapalı: kurulum, tanımlar, sözlük ve bölme
   adımlarında karar bir cümleyle değil, bloktaki kartla veriliyor.
   Kutu açık durunca ekranda iki ayrı "devam etme yolu" görünüyor ve
   yazılan cümle çoğu zaman adıma ait bilgi içermediği için akış hiç
   ilerlemiyordu.

   Neden DEĞİŞKEN MÜHENDİSLİĞİ'NDE açık (kullanıcı kararı): faz 01 ve
   02 boyunca her karar kartta veriliyor ve kartın soracağı her şey
   kartın içinde yazılı. Değişken üretimi ise kullanıcının yön vermesi
   gereken ilk adım - "şu değişkeni de üret", "bunu neden elediniz"
   soruları tam orada başlıyor.

   SEBEP KUTUNUN İÇİNDE YAZIYOR: boş ve pasif bir kutu "bozuk mu?"
   diye düşündürüyor. Kilit notu hem kapalı olduğunu hem NE ZAMAN
   açılacağını söylüyor. */
const SOHBET_ACILIS_ADIMI = "kural";    // Faz 03 - Değişken Mühendisliği
/* Kilit metni artık PLACEHOLDER DEĞİL, kutunun üstüne binen bir katman.
   Sebep: placeholder düz metindir, içindeki adım adı kalın yazılamaz.
   Katman <strong> taşıyabiliyor. Düz hâli title ve ekran okuyucu için
   duruyor. */
const KUTU_KILIT_ADIM = "Değişken Mühendisliği";
const KUTU_KILIT_ONCE = "Sohbet, ";
const KUTU_KILIT_SONRA =
    " adımında açılır. O ana kadar seçimler kartlar üzerinden yapılır; "
    + "gerekçeli açıklamalar kartların içinde gösterilir.";
const KUTU_KILIT_IPUCU = KUTU_KILIT_ONCE + KUTU_KILIT_ADIM + KUTU_KILIT_SONRA;
const KUTU_ACIK_IPUCU = "Cevabınızı ya da sorunuzu yazın…";

/* Sohbetin açılacağı adımın sırası. Adım listesi moda göre değiştiği
   için sabit bir sayı yazılmıyor, her çizimde okunuyor. Adım
   bulunamazsa (liste henüz gelmedi) kutu KAPALI kalır: yanlış tarafta
   hata yapmak, akışın başında serbest yazmaya izin vermek yerine biraz
   daha kapalı kalmaktır. */
function sohbetAcilisSirasi() {
    const fazlar = FAZLAR || [];
    for (let i = 0; i < fazlar.length; i++) {
        const adimlar = fazlar[i].adimlar || [];
        for (let j = 0; j < adimlar.length; j++) {
            if (adimlar[j].anahtar === SOHBET_ACILIS_ADIMI)
                return adimlar[j].sira;
        }
    }
    return Infinity;
}

/* Kilit notu katmanini kurar/gunceller. Kutu kilitliyken placeholder
   bos birakilir, yoksa iki metin ust uste biner. */
function kutuKilitNotu(kilit) {
    const kap = kutuEl.parentElement;           // #giris
    if (!kap) return;
    let not = kap.querySelector(".kutu-kilit-not");
    if (!kilit) {
        if (not) not.remove();
        return;
    }
    if (!not) {
        not = elYap("div", "kutu-kilit-not");
        not.appendChild(elYap("span", "", KUTU_KILIT_ONCE));
        not.appendChild(elYap("strong", "", KUTU_KILIT_ADIM));
        not.appendChild(elYap("span", "", KUTU_KILIT_SONRA));
        kap.appendChild(not);
    }
}

function kutuGuncelle(bekleyen) {
    if (bekleyen === undefined) return;       // hata yanitinda durumu koru
    /* "<" : kutu Değişken Mühendisliği adımının KENDİSİNDE açılıyor
       (kullanıcı kararı: "Değişken Mühendisliği kısmında açılacak").
       O adıma gelindiğinde kullanıcı zaten yön vermeye başlıyor;
       kutuyu bir adım daha geciktirmek onu sessiz bırakırdı. */
    const kilit = aktifAdim < sohbetAcilisSirasi();

    kutuEl.disabled = kilit;
    kutuEl.placeholder = kilit ? "" : KUTU_ACIK_IPUCU;
    kutuEl.title = kilit ? KUTU_KILIT_IPUCU : "";
    kutuEl.setAttribute("aria-label", kilit ? KUTU_KILIT_IPUCU : KUTU_ACIK_IPUCU);
    kutuKilitNotu(kilit);
    gonderEl.hidden = kilit;
    girisBolge.classList.toggle("kilitli", kilit);
}


/* ==================== Sol panel: faz ağacı ==================== */
/* Faz agaci secime gore degisir; backend her yanitta guncel halini gonderir. */
function fazlariYukle(liste) {
    FAZLAR = liste || [];
    DUZ_ADIMLAR = [];
    FAZLAR.forEach(f => f.adimlar.forEach(a => { DUZ_ADIMLAR[a.sira] = a; }));
}

/* GRUPLU ADIMLAR SOL PANELDE TEK SATIR (kullanıcı kararı). "Veri Seti ve
   Değişken Sözlüğü", "Modelleme Tanımları" ve "Sözlük Tanımları" sohbette
   zaten TEK blok; iş akışında üç ayrı satır olarak durunca aynı iş üç kez
   sayılıyordu. Satır grubun adını taşır. Adım listesinin kendisi (FAZLAR)
   DOKUNULMADAN kalır: geri dönüş, transkript kırpma ve blok eşleme hep
   tam listeye bakıyor. */
function fazOgeleri(f) {
    const ogeler = [];
    (f.adimlar || []).forEach(a => {
        const son = ogeler[ogeler.length - 1];
        const alt = { anahtar: a.anahtar, sira: a.sira, bitis: a.sira,
                      baslik: a.baslik, aciklama: a.aciklama };
        if (a.grup && son && son.grup === a.grup) {
            son.bitis = a.sira;          // gruba katıl
            son.adimlar.push(a.anahtar);
            son.alt.push(alt);
            return;
        }
        ogeler.push({
            anahtar: a.anahtar, sira: a.sira, bitis: a.sira,
            grup: a.grup || "",
            baslik: a.grup ? (a.grup_baslik || a.baslik) : a.baslik,
            aciklama: a.aciklama,
            adimlar: [a.anahtar],
            alt: [alt]
        });
    });
    ogeler.forEach((o, i) => {
        o.kod = f.no + "." + (i + 1);
        o.alt.forEach((x, j) => { x.kod = o.kod + "." + (j + 1); });
    });
    return ogeler;
}

/* ADIM NUMARASI (kullanıcı kararı: faz altındaki işler 01.1, 01.2 ...
   diye adlandırılsın). Numara sol paneldeki SATIR sırasıdır; gruplu
   satırın içindeki adımlar alt numara alır (01.2.1, 01.2.2). İş akışı,
   sohbet başlıkları, Arşiv ve "kaldığı yerden yüklendi" mesajı aynı
   numarayı kullanır. Doner: {fazIdx, faz, kod, altKod} ya da null. */
function adimKonumu(anahtar) {
    if (!anahtar) return null;
    for (let fi = 0; fi < FAZLAR.length; fi++) {
        const ogeler = fazOgeleri(FAZLAR[fi]);
        for (let oi = 0; oi < ogeler.length; oi++) {
            const j = ogeler[oi].adimlar.indexOf(anahtar);
            if (j === -1) continue;
            const kod = ogeler[oi].kod;
            return { fazIdx: fi, faz: FAZLAR[fi], kod: kod,
                     altKod: ogeler[oi].adimlar.length > 1 ? kod + "." + (j + 1) : kod };
        }
    }
    return null;
}

function numarali(kod, baslik) {
    const b = tireSade(baslik || "");
    return kod ? kod + " " + b : b;
}

/* ANALİTİK SÜREÇ HEP AÇIK (kullanıcı kararı: "açıp kapatılamamalı").
   Başlık düğme değil. index.html eski sürümde kalırsa düğme burada
   pasifleştirilir: ok gizlenir, tıklama bir şey yapmaz. */
const surecBlok = document.getElementById("surec-blok");
const surecBas  = document.getElementById("surec-bas");

function surecGuncelle() {
    if (!surecBlok) return;
    surecBlok.classList.remove("kapali");
    if (surecBas) {
        surecBas.onclick = null;
        surecBas.removeAttribute("aria-expanded");
        surecBas.removeAttribute("title");
        surecBas.style.cursor = "default";
        const ok = surecBas.querySelector(".surec-ok");
        if (ok) ok.remove();
    }
}
surecGuncelle();

function fazlariCiz() {
    surecGuncelle();
    fazEl.innerHTML = "";
    FAZLAR.forEach((f, fi) => {
        /* Gruplu satır tıklanınca grubun İLK adımına döner (grubun
           tamamını yeniden gözden geçirmenin doğru başlangıcı orası). */
        const adimlar = fazOgeleri(f);
        const siralar = f.adimlar.map(a => a.sira);
        const bitis = Math.max.apply(null, siralar);
        const aktifMi = siralar.indexOf(aktifAdim) !== -1;
        const tamamMi = aktifAdim > bitis;
        const acik = acikFazlar.has(fi);

        const kok = document.createElement("div");
        kok.className = "faz"
            + (aktifMi ? " aktif" : "")
            + (tamamMi ? " tamam" : "")
            + (acik ? " acik" : "");

        /* Klavye ile acilabilsin diye buton: Enter/Space dogal calisir */
        const bas = document.createElement("button");
        bas.type = "button";
        bas.className = "faz-bas";
        bas.title = acik ? "Adımları gizle" : "Adımları göster";
        bas.setAttribute("aria-expanded", acik ? "true" : "false");
        bas.setAttribute("aria-controls", "faz-adimlar-" + fi);

        const ok = document.createElement("span");
        ok.className = "faz-ok";
        ok.textContent = "›";
        bas.appendChild(ok);

        const no = document.createElement("span");
        no.className = "faz-no";
        no.textContent = f.no;
        bas.appendChild(no);

        const govde = document.createElement("div");
        govde.className = "faz-govde";
        const ad = document.createElement("div");
        ad.className = "faz-ad";
        ad.textContent = f.baslik;
        govde.appendChild(ad);
        const ozt = document.createElement("div");
        ozt.className = "faz-ozet";
        ozt.textContent = f.ozet;
        govde.appendChild(ozt);
        bas.appendChild(govde);

        /* Sayaç da GRUPLU sayar: ekranda kaç satır varsa payda o. */
        const tamamSayi = adimlar.filter(a => a.bitis < aktifAdim).length;
        const durum = document.createElement("span");
        durum.className = "faz-durum";
        durum.textContent = tamamMi ? "✓" : (tamamSayi + "/" + adimlar.length);
        durum.title = tamamMi
            ? "Faz tamamlandı"
            : tamamSayi + " / " + adimlar.length + " adım tamamlandı";
        bas.appendChild(durum);

        bas.onclick = () => {
            if (acikFazlar.has(fi)) acikFazlar.delete(fi);
            else acikFazlar.add(fi);
            fazlariCiz();
            // Yeniden cizimde odak kaybolmasin (klavye kullanicisi icin)
            const yeni = fazEl.querySelectorAll(".faz-bas")[fi];
            if (yeni) yeni.focus();
        };
        kok.appendChild(bas);

        const liste = document.createElement("ol");
        liste.className = "faz-adimlar";
        liste.id = "faz-adimlar-" + fi;
        /* GRUP SATIRININ ALT ADIMLARI (kullanıcı kararı: "bütün akış sol
           tarafta yer almalı"). Grup satırı (01.2 Veri ve Model
           Tanımları) kalır; altında her adım kendi numarasıyla (01.2.1,
           01.2.2 ...) aynı kurallarla — tamamlandı / aktif / tıklanabilir
           — listelenir. */
        const satirKur = (a) => {
            const li = document.createElement("li");
            // Grup satırı: aktif adım grubun HERHANGİ bir adımıysa aktif.
            const tamamlandi = a.bitis < aktifAdim;
            const aktif = aktifAdim >= a.sira && aktifAdim <= a.bitis;
            if (tamamlandi) li.className = "tamam";
            if (aktif)      li.className = "aktif";

            const isaret = document.createElement("span");
            isaret.className = "adim-isaret";
            isaret.textContent = tamamlandi ? "✓" : "";
            li.appendChild(isaret);

            /* GÖRÜLMÜŞ HER ADIM TIKLANABİLİR — yalnızca tamamlananlar
               değil, İÇİNDE BULUNULAN adım da (tıklayınca formu yeniden
               açar, yani "Değiştir" ile aynı kapı).

               Blok başlığındaki Geri Dön yalnızca METİN ÜRETEN adımlarda
               var; "kurulum" ve "tanımlar" gibi adımlar bilerek metin
               döndürmüyor (karar kartın içinde) ve transkriptte
               dönülebilecek bir blok bırakmıyorlar. Oysa kullanıcının en
               çok geri döneceği yerler tam olarak onlar. İş akışı listesi
               her adımı HER ZAMAN gösteriyor ve F5'ten sonra da duruyor;
               doğrudan o adıma dönmenin güvenilir yolu burası.

               HENÜZ GELİNMEMİŞ adım tıklanmaz: durumu yazılmamış bir
               adımı atlamak, sonraki adımın olmayan bir karara
               dayanması demek olurdu (arka uç da reddediyor, bkz.
               akis_sohbet._hedefe_don). Nedeni ipucunda yazıyor. */
            const gorulmus = a.sira <= aktifAdim;
            if (gorulmus && a.anahtar) {
                const dug = document.createElement("button");
                dug.type = "button";
                dug.className = "adim-git";
                dug.textContent = numarali(a.kod, a.baslik);
                dug.title = (a.sira === aktifAdim
                             ? "\"" + tireSade(a.baslik) + "\" adımını yeniden aç"
                             : "\"" + tireSade(a.baslik) + "\" adımına dön")
                    + (a.aciklama ? ": " + tireSade(a.aciklama) : "");
                /* Blok başlığındaki Geri Dön ile AYNI yol: transkript
                   o adımdan geri sarılır. Ayraç basılmıyor, silinecek
                   satırların arasında kalırdı. */
                dug.onclick = () => {
                    if (mesgul) return;
                    gonder("geri dön", false, { adim: a.anahtar });
                };
                li.appendChild(dug);
            } else {
                li.title = (a.aciklama ? tireSade(a.aciklama) + ", " : "")
                    + "bu adıma henüz gelinmedi";
                const t = document.createElement("span");
                t.textContent = numarali(a.kod, a.baslik);
                li.appendChild(t);
            }
            return li;
        };
        adimlar.forEach(a => {
            const li = satirKur(a);
            if (a.alt && a.alt.length > 1) {
                li.classList.add("grup-satir");
                const altListe = elYap("ol", "faz-alt-adimlar");
                a.alt.forEach(x => altListe.appendChild(satirKur(x)));
                li.appendChild(altListe);
            }
            liste.appendChild(li);
        });
        kok.appendChild(liste);
        fazEl.appendChild(kok);
    });
}

function aktifFaziAc() {
    FAZLAR.forEach((f, fi) => {
        if (f.adimlar.some(a => a.sira === aktifAdim)) acikFazlar.add(fi);
    });
}

/* İş akışı açılışta ayrıca istenmiyor: /karsilama yanıtı fazları
   zaten taşıyor. */


/* ==================== Üst özet kartları ==================== */
/* Veri seti adi ARTIK kart degil, basligin yanindaki cip: dort kartin
   biri onun icin harcaniyordu, oysa ad tek satirlik bir kimlik bilgisi.
   Secim yoksa cip hic cizilmez - bos cip "veri seti yok" demiyor,
   "bir sey bozuldu" izlenimi veriyor. */
const cipEl = document.getElementById("veri-seti-cip");

function cipYaz(el, ad) {
    if (!el) return;
    const metin = tireSade(ad === null || ad === undefined ? "" : String(ad)).trim();
    el.textContent = metin;
    el.title = metin;
    el.hidden = !metin;
}

/* Ust serit: BASTAN SONA ne oldugunu anlatan dort kart.
   Bicim eskisiyle ayni (kirmizi etiket, koyu deger, iki gri alt satir,
   ulasilmamis deger ∅); degisen sey ICERIK. Eski kartlar
   (AŞAMA/KAPSAM/HEDEF/DEĞİŞKEN SETİ) baska panellerin tekrariydi;
   yenisi bir huni: veri neydi, neler elendi, ne uretildi, modele ne girdi. */
function ozetGuncelle(o) {
    if (!o || !o.kartlar) return;
    /* Cipler ARTIK cizilmiyor: VERİ ve SÖZLÜK kartlari ayni bilgiyi
       tasiyor ve ustune tiklanabiliyor. Alanlar govdede duruyor cunku
       seciliVeriSeti() onlari okuyor. */
    cipYaz(cipEl, null);
    cipYaz(sozlukCipEl, null);
    if (!seritEl) return;

    seritEl.innerHTML = "";
    o.kartlar.forEach(k => {
        /* "hedef" dolu kart TIKLANABILIR: sag panelde ilgili sekmeyi
           acar. Hazir olmayan kartta hedef gelmez, tiklama da yoktur —
           yarim bir panel acmaktansa kart ne bekledigini yazar. */
        const tiklanir = !!k.hedef;
        const kart = elYap(tiklanir ? "button" : "div",
                           "ozet-kart" + (tiklanir ? " tiklanir" : ""));
        if (tiklanir) {
            kart.type = "button";
            kart.onclick = () => { sayfaAc("calisma"); analizSekmeAc(k.hedef); };
        }
        if (k.ipucu) kart.title = k.ipucu;
        kart.appendChild(elYap("span", "ozet-etiket", tireSade(k.etiket)));

        const degerMetin = degerGoster(k.deger);
        const deger = elYap("span",
            "ozet-deger" + (degerMetin === BOS_SIMGE ? " bos" : ""), degerMetin);
        deger.title = degerMetin;
        kart.appendChild(deger);

        /* Üst şerit satırları BAŞLIK BÜYÜK HARFİ ile: "kural tabanlı
           üretim + AI keşfi" -> "Kural Tabanlı Üretim + AI Keşfi".
           Kısaltmalar (AI, SFA, KS, OOT) ve sayılar korunur. */
        [["ozet-ust", k.ust], ["ozet-alt", k.alt]].forEach(([sinif, ham]) => {
            const metin = baslikBuyuk(ham);
            const el = elYap("span", sinif, metin);
            if (!k.ipucu) el.title = metin;   // kart ipucusu varsa o kazansin
            kart.appendChild(el);
        });

        seritEl.appendChild(kart);
    });
}


/* ============ ÖZET sayfası: Model Geliştirme Dokümanı ==================
   Sayfa artık kısa bir çalışma özeti değil, Model Risk'e giden dokümanın
   kendisini çizer: künye + 20 numaralı bölüm + ek, her bölümün statüsü,
   kullanıcı düzenlemesi, Word çıktısı.

   NEDEN AYRI UÇTAN ALINIYOR
     Gövde büyük (tablolar + her bölümün düz metin karşılığı). Her sohbet
     turunun yanıtına bindirmek, kullanıcı bu sayfayı hiç açmasa bile her
     yanıta onlarca kilobayt eklerdi; sekme açıldığında bir kez istenir.

   NEDEN TEK BÖLÜM YENİDEN ÇİZİLİYOR
     /dokuman_bolum yalnızca kaydedilen bölümü döndürüyor. Sayfanın
     tamamını yeniden çizmek, kullanıcının on beş bölüm içinde okuduğu
     yeri kaybetmesi demekti. */
const dokBaslikEl      = document.getElementById("dok-baslik");
const dokDamgaEl       = document.getElementById("dok-damga");
const dokTarihEl       = document.getElementById("dok-tarih");
const dokUyariEl       = document.getElementById("dok-uyari");
const dokBolumlerEl    = document.getElementById("dok-bolumler");
const dokWordBtn       = document.getElementById("dok-word");
const dokIndirmeHataEl = document.getElementById("dok-indirme-hata");

/* Arka ucun Content-Disposition'da verdiği adla AYNI (fe_agent.dokuman.
   DOSYA_ADI). Blob ile indirdiğimiz için başlık okunmuyor, ad burada
   yazılmak zorunda. */
const DOKUMAN_DOSYA_ADI = "model_gelistirme_dokumani.docx";

const DOK = {
    govde: null,        // son /dokuman yanıtı
    yukleniyor: false,
    hata: "",
    duzenlenen: null,   // düzenleme kutusu açık olan bölümün anahtarı
    taslak: "",         // textarea'daki yarım metin
    kaydediyor: false,
    bolumHata: {}       // anahtar -> "kaydedilemedi" mesajı
};

/* Künye ve Ekler NUMARASIZDIR (no = null); aradaki 20 bölüm numaralıdır.
   Numarayı koşulsuz yazsaydık bu iki bölüm "null. Künye" diye çiziliyordu. */
function dokBolumAdi(b) {
    return b && b.no ? b.no + ". " + b.baslik : ((b && b.baslik) || "");
}

function dokBolumBul(anahtar) {
    const bolumler = (DOK.govde && DOK.govde.bolumler) || [];
    return bolumler.find(b => b && b.anahtar === anahtar) || null;
}

/* Statü sayıları YERELDE sayılıyor, gövdedeki bloker_sayisi /
   eksik_sayisi / kismi_sayisi alanları yerine: /dokuman_bolum yalnızca
   kaydedilen bölümü döndürüyor, kökteki sayaçlar o yanıtla gelmiyor.
   Aynı listeden sayınca şerit tek bölüm kaydedildiğinde de doğru kalıyor
   (arka uçta da sayaçlar bölüm statülerinden türüyor). */
function dokStatuSay(statu) {
    return ((DOK.govde && DOK.govde.bolumler) || [])
        .filter(b => b && b.statu === statu).length;
}

/* Çağrı kutusu KOŞULU: bölüm kullanıcıya ait ve kullanıcı henüz yazmamış.
   "İçerik boş mu" diye BAKMIYORUZ: platform 18. bölüme (kisit) kendi
   bulduğu açık maddeleri otomatik bir tablo olarak ekliyor, bu yüzden o
   bölüm hiç yazılmamışken bile dolu görünüyordu ve çağrı kaybolmuştu.
   `karma` bölümlerde çağrı çizilmez — platform payı zaten yazılı, geri
   kalanı "Tamamlanması gerekenler" kutusu söyler. */
function dokCagriGerek(b) {
    return !!b && b.kaynak === "kullanici" && !b.duzenlendi;
}


/* ---------------- Bölüm gövdesi: bloklar ---------------- */
function dokBlokCiz(kap, blok) {
    if (!blok || typeof blok !== "object") return;

    if (blok.tur === "liste") {
        const liste = elYap("ul", "dok-liste");
        (blok.ogeler || []).forEach(o => liste.appendChild(elYap("li", "", o)));
        kap.appendChild(liste);
        return;
    }
    if (blok.tur === "tablo") {
        if (blok.baslik)
            kap.appendChild(elYap("div", "dok-tablo-baslik", blok.baslik));
        const sarmal = elYap("div", "dok-tablo");
        sarmal.appendChild(tabloYap(blok));
        kap.appendChild(sarmal);
        return;
    }
    if (blok.tur === "bos") {
        kap.appendChild(elYap("p", "dok-bos", blok.metin));
        return;
    }
    /* paragraf VE tanımadığımız her tür: "metin" alanı paragraf olarak
       çizilir. Bilinmeyen türü sessizce atlamak, arka uca eklenen yeni
       bir bloğun ekranda hiç görünmemesi demekti. */
    kap.appendChild(elYap("p", "dok-p", blok.metin));
}

/* "Tamamlanması gerekenler": bölümde HÂLÂ yazılması gereken maddeler.
   Kullanıcı bölümünde çağrı kutusunun İÇİNE giriyor (sözleşme §7: kutu
   düzenleme çağrısıyla birleşir), diğerlerinde gövdenin altında ayrı
   durur. İki yerde de aynı sınıf: "ne eksik" sorusu tek yerden okunur. */
function dokEksiklerYap(b) {
    const eksikler = (b && b.eksikler) || [];
    if (!eksikler.length) return null;
    const kutu = elYap("div", "dok-eksikler");
    kutu.appendChild(elYap("div", "dok-eksikler-baslik",
                           "Tamamlanması gerekenler"));
    const liste = elYap("ul", "dok-liste dok-eksik-liste");
    eksikler.forEach(m => liste.appendChild(elYap("li", "", m)));
    kutu.appendChild(liste);
    return kutu;
}

function dokCagriYap(b) {
    const kutu = elYap("div", "dok-cagri");
    kutu.appendChild(elYap("div", "dok-cagri-baslik",
                           "Bu bölümü siz yazmalısınız"));
    kutu.appendChild(elYap("p", "dok-cagri-metin",
        "Bu bölümün hesaplanan bir karşılığı yok. Siz yazana kadar "
        + "dokümanda eksik görünür."));
    const eksikler = dokEksiklerYap(b);
    if (eksikler) kutu.appendChild(eksikler);
    const btn = elYap("button", "dok-dugme", "Bu Bölümü Yaz");
    btn.type = "button";
    btn.onclick = () => dokDuzenleAc(b.anahtar);
    kutu.appendChild(btn);
    return kutu;
}

/* Statü rozeti: TAMAM ÇİZİLMEZ. Yirmi iki bölümün çoğuna "TAMAM" rozeti
   koymak, gerçekten bakılması gereken üç beş bölümü gürültüde bırakırdı;
   rozet yalnızca dikkat isteyen bölümde görünür. */
function dokStatuRozetYap(b) {
    if (!b || !b.statu || b.statu === "TAMAM") return null;
    const rozet = elYap("span", "dok-statu dok-statu-" + b.statu, b.statu);
    rozet.title = b.statu_notu || "";
    return rozet;
}

function dokGovdeYap(b) {
    const govde = elYap("div", "dok-govde");
    const cagri = dokCagriGerek(b);

    /* Çağrı çizilecekse "bos" blokları atlanır: o blokların metni zaten
       çağrı kutusunun söylediği şey. Kalan bloklar (örn. 18. bölümün
       otomatik risk tablosu) KORUNUR — platformun hesapladığı şey
       çağrı yüzünden kaybolmamalı. */
    (b.bloklar || [])
        .filter(blok => !(cagri && blok && blok.tur === "bos"))
        .forEach(blok => dokBlokCiz(govde, blok));

    if (cagri) {
        govde.appendChild(dokCagriYap(b));
    } else {
        const eksikler = dokEksiklerYap(b);
        if (eksikler) govde.appendChild(eksikler);
    }
    return govde;
}


/* ---------------- Düzenleme kutusu ---------------- */
function dokDuzenleYap(b) {
    const kutu = elYap("div", "dok-duzen");

    const alan = elYap("textarea", "dok-alan");
    alan.rows = 12;
    alan.value = DOK.taslak;
    alan.disabled = DOK.kaydediyor;
    /* Ad dokBolumAdi'dan: künye ve ek NUMARASIZ (no = null) ve burada
       elle birleştirmek ekran okuyucuya "null. Künye metni" dedirtiyordu. */
    alan.setAttribute("aria-label", tireSade(dokBolumAdi(b)) + " metni");
    alan.oninput = () => { DOK.taslak = alan.value; };
    kutu.appendChild(alan);

    kutu.appendChild(elYap("div", "dok-duzen-not",
        "Kaydettiğiniz metin, doküman yeniden üretildiğinde EZİLMEZ. "
        + "Hesaplanan hâline «özgün hâline dön» ile dönersiniz."));

    const ayak = elYap("div", "dok-ayak");

    const kaydet = elYap("button", "dok-dugme",
                         DOK.kaydediyor ? "Kaydediliyor…" : "Kaydet");
    kaydet.type = "button";
    kaydet.disabled = DOK.kaydediyor;
    kaydet.onclick = () => dokBolumYaz(b.anahtar, alan.value);
    ayak.appendChild(kaydet);

    const vazgec = elYap("button", "dok-mini", "Vazgeç");
    vazgec.type = "button";
    vazgec.disabled = DOK.kaydediyor;
    vazgec.onclick = () => {
        DOK.duzenlenen = null;
        DOK.taslak = "";
        dokBolumTazele(b.anahtar);
    };
    ayak.appendChild(vazgec);

    kutu.appendChild(ayak);
    return kutu;
}

function dokDuzenleAc(anahtar) {
    const b = dokBolumBul(anahtar);
    if (!b) return;
    const onceki = DOK.duzenlenen;

    /* Düzenleme HER ZAMAN bölümün düz metniyle başlar: kullanıcı ekranda
       gördüğü tabloyu/listeyi metin olarak düzeltir, arka uç da aynı
       metni Word'e aynı yoldan yazar. */
    DOK.duzenlenen = anahtar;
    DOK.taslak = b.metin || "";
    DOK.kaydediyor = false;
    delete DOK.bolumHata[anahtar];

    // Aynı anda tek bölüm açık: eskisi yarım taslağıyla ekranda kalmasın.
    if (onceki && onceki !== anahtar) dokBolumTazele(onceki);

    const yeni = dokBolumTazele(anahtar);
    const alan = yeni && yeni.querySelector(".dok-alan");
    if (alan) alan.focus();
}

/* Boş metin = düzenlemeyi sil, bölüm hesaplanan hâline dönsün.
   "Özgün Hâline Dön" ayrı bir uç değil; aynı ucun boş metinli hâli. */
function dokBolumYaz(anahtar, metin) {
    if (DOK.kaydediyor) return;
    DOK.kaydediyor = true;
    delete DOK.bolumHata[anahtar];
    dokBolumTazele(anahtar);

    fetch(getWebAppBackendUrl("dokuman_bolum"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(ftKimlikGovdesi({ anahtar: anahtar, metin: metin }))
    })
    .then(r => r.json())
    .then(d => {
        DOK.kaydediyor = false;
        if (!d || d.tamam !== true || !d.bolum) {
            /* Taslak DURUYOR: kullanıcının yazdığı metin, uç hata
               döndürdü diye ekrandan silinmez. */
            DOK.bolumHata[anahtar] = (d && d.hata) || "Bölüm kaydedilemedi.";
        } else {
            const bolumler = (DOK.govde && DOK.govde.bolumler) || [];
            const yer = bolumler.findIndex(b => b && b.anahtar === anahtar);
            if (yer !== -1) bolumler[yer] = d.bolum;
            /* Uç, tam gövdeyi zaten ürettiği için teslim özetini de
               döndürüyor. Kökü onunla tazeliyoruz: son bloker bu kayıtla
               kapandıysa damga aynı anda yeşile döner, ikinci bir istek
               ya da "beklemede" hâli gerekmez. */
            if (d.teslim && DOK.govde) Object.assign(DOK.govde, d.teslim);
            DOK.duzenlenen = null;
            DOK.taslak = "";
        }
        dokBolumTazele(anahtar);
        dokUyariTazele();
        dokDamgaTazele();
    })
    .catch(e => {
        DOK.kaydediyor = false;
        DOK.bolumHata[anahtar] = "Bölüm kaydedilemedi: " + e;
        dokBolumTazele(anahtar);
    });
}


/* ---------------- Bölüm kutusu ---------------- */
function dokBolumYap(b) {
    const kok = elYap("section", "dok-bolum" + (b.duzenlendi ? " duzenli" : ""));
    kok.dataset.anahtar = b.anahtar;

    const ust = elYap("div", "dok-bolum-ust");
    const sol = elYap("div", "dok-bolum-sol");
    sol.appendChild(elYap("h2", "dok-bolum-baslik", dokBolumAdi(b)));
    const statu = dokStatuRozetYap(b);
    if (statu) sol.appendChild(statu);
    if (b.duzenlendi) {
        const rozet = elYap("span", "dok-rozet", "düzenlendi");
        rozet.title = "Bu bölümü siz yazdınız; yeniden üretim ezmez.";
        sol.appendChild(rozet);
    }
    ust.appendChild(sol);

    // Düzenleme açıkken başlık aksiyonları çizilmez: Kaydet/Vazgeç zaten
    // kutunun altında ve iki ayrı "çıkış" yolu karışıklık yaratıyordu.
    if (DOK.duzenlenen !== b.anahtar) {
        const aksiyon = elYap("div", "dok-aksiyon");

        const duzenle = elYap("button", "dok-mini", "Düzenle");
        duzenle.type = "button";
        duzenle.onclick = () => dokDuzenleAc(b.anahtar);
        aksiyon.appendChild(duzenle);

        if (b.duzenlendi) {
            const geri = elYap("button", "dok-bag", "Özgün Hâline Dön");
            geri.type = "button";
            geri.title = "Yazdığınız metni siler; bölüm hesaplanan hâline döner.";
            geri.disabled = DOK.kaydediyor;
            geri.onclick = () => dokBolumYaz(b.anahtar, "");
            aksiyon.appendChild(geri);
        }
        ust.appendChild(aksiyon);
    }
    kok.appendChild(ust);

    kok.appendChild(DOK.duzenlenen === b.anahtar
                    ? dokDuzenleYap(b) : dokGovdeYap(b));

    const hata = DOK.bolumHata[b.anahtar];
    if (hata) kok.appendChild(elYap("div", "dok-hata", hata));
    return kok;
}

/* Yalnızca bir bölümü yerinde değiştirir; sayfanın kalanına dokunmaz. */
function dokBolumTazele(anahtar) {
    const b = dokBolumBul(anahtar);
    if (!b || !dokBolumlerEl) return null;
    const yeni = dokBolumYap(b);
    const eski = Array.from(dokBolumlerEl.children)
        .find(e => e.dataset && e.dataset.anahtar === anahtar);
    if (eski) dokBolumlerEl.replaceChild(yeni, eski);
    else dokBolumlerEl.appendChild(yeni);
    return yeni;
}


/* ---------------- Üst şerit, damga ve uyarı ---------------- */
/* Teslim damgası doküman başlığının yanında. Bloker varsa kırmızı
   (TASLAK), yoksa yeşil. Kapı ETİKETTEDİR: damga hiçbir düğmeyi
   kapatmaz, yalnızca dokümanın final olarak gönderilip gönderilemeyeceğini
   söyler (bkz. Word düğmesi her hâlde etkin). */
function dokDamgaTazele() {
    if (!dokDamgaEl) return;
    const g = DOK.govde;
    const metin = (g && g.teslim_damgasi) || "";
    if (!metin) {
        dokDamgaEl.hidden = true;
        dokDamgaEl.textContent = "";
        dokDamgaEl.className = "dok-damga";
        return;
    }
    /* Damganın METNİ arka uçtan geliyor; iki cümlesini buraya kopyalasak
       ileride biri değiştiğinde ekran sessizce yalan söylerdi. Bu yüzden
       metin de durum da gövdeden okunur.

       /dokuman_bolum tek bölüm kaydında teslim özetini de döndürüyor ve
       dokBolumYaz onu köke yazıyor; damga bu yüzden kaydın hemen ardından
       doğru. "Bayat damga" diye bir ara hâl YOK — eskiden uç yalnız bölümü
       döndürdüğü için gerekiyordu, uç düzelince gerekçesi kalktı. */
    const taslak = (g.teslim_durumu || "") !== "hazir";
    dokDamgaEl.hidden = false;
    dokDamgaEl.className = "dok-damga " + (taslak ? "taslak" : "hazir");
    dokDamgaEl.textContent = tireSade(metin);
    dokDamgaEl.title = "";
}

/* Uyarı şeridi üç sayıyı birden gösterir: bloker · eksik · kısmi.
   Tek sayılı "N bölüm eksik" şeridi, teslimi ENGELLEYEN bir bölümle
   yalnızca yarım kalmış bir bölümü aynı tonda gösteriyordu. */
function dokUyariTazele() {
    if (!dokUyariEl) return;
    const g = DOK.govde;
    const temizle = () => {
        dokUyariEl.hidden = true;
        dokUyariEl.textContent = "";
        dokUyariEl.className = "dok-uyari";
    };
    if (!g) { temizle(); return; }

    const bloker = dokStatuSay("BLOKER");
    const eksik  = dokStatuSay("EKSIK");
    const kismi  = dokStatuSay("KISMI");
    if (!bloker && !eksik && !kismi) { temizle(); return; }

    dokUyariEl.hidden = false;
    dokUyariEl.className = "dok-uyari" + (bloker ? " bloker" : "");

    const sayilar = "Bloker: " + bloker + " · Eksik: " + eksik
                  + " · Kısmi: " + kismi;
    dokUyariEl.textContent = sayilar + ": " + (bloker
        ? ("bu doküman TASLAK sayılır, validasyona final olarak "
           + "gönderilmemelidir. Çalışma durmaz, Word çıktısı alınabilir.")
        : ("teslimi engelleyen bölüm yok; kalan maddeler validasyon "
           + "sürecinde tamamlanmalıdır."));
}

function dokumanCiz() {
    if (!dokBolumlerEl) return;
    const g = DOK.govde;

    if (dokBaslikEl) dokBaslikEl.textContent = tireSade((g && g.baslik) || "");
    if (dokTarihEl) {
        const tarih = (g && g.olusturma) || "";
        dokTarihEl.textContent = tarih ? "Oluşturma: " + tireSade(tarih) : "";
        dokTarihEl.hidden = !tarih;
    }
    dokDamgaTazele();
    dokUyariTazele();

    dokBolumlerEl.innerHTML = "";
    if (DOK.hata)
        dokBolumlerEl.appendChild(elYap("div", "dok-hata", DOK.hata));
    if (!g) {
        if (!DOK.hata)
            dokBolumlerEl.appendChild(elYap("div", "dok-bos",
                DOK.yukleniyor ? "Doküman hazırlanıyor…"
                               : "Doküman henüz alınmadı."));
        return;
    }
    (g.bolumler || []).forEach(b => {
        if (b) dokBolumlerEl.appendChild(dokBolumYap(b));
    });
}

/* Çalışma sıfırlandığında: elde kalan doküman artık silinmiş bir
   çalışmaya ait. */
function dokumanSifirla() {
    DOK.govde = null;
    DOK.hata = "";
    DOK.duzenlenen = null;
    DOK.taslak = "";
    DOK.kaydediyor = false;
    DOK.bolumHata = {};
    dokIndirmeHataYaz("");
    dokumanCiz();
}

function dokumanGetir() {
    if (DOK.yukleniyor) return;
    DOK.yukleniyor = true;
    DOK.hata = "";
    if (!DOK.govde) dokumanCiz();          // ilk açılışta "hazırlanıyor" notu

    fetch(getWebAppBackendUrl("dokuman")
          + "?oturum_id=" + encodeURIComponent(OTURUM_ID))
        .then(r => r.json())
        .then(d => {
            DOK.yukleniyor = false;
            if (!d || !d.dokuman) {
                /* Eski gövde EKRANDA KALIR: tazeleme başarısız diye
                   kullanıcının okuduğu doküman silinmez. */
                DOK.hata = (d && d.hata) || "Doküman hazırlanamadı.";
            } else {
                DOK.govde = d.dokuman;
                DOK.bolumHata = {};
                /* Açık düzenleme ve yarım taslak KORUNUR: kullanıcının
                   yazdığı metni sekme değişimi silmemeli. */
            }
            dokumanCiz();
        })
        .catch(e => {
            DOK.yukleniyor = false;
            DOK.hata = "Doküman alınamadı: " + e;
            dokumanCiz();
        });
}


/* ---------------- Word çıktısı ---------------- */
function dokIndirmeHataYaz(mesaj) {
    if (!dokIndirmeHataEl) return;
    dokIndirmeHataEl.textContent = mesaj || "";
    dokIndirmeHataEl.hidden = !mesaj;
}

/* Yeni sekmede AÇMIYORUZ: Dataiku webapp'i iframe içinde çalışıyor,
   açılan sekme çoğu kurulumda boş kalıyor ve hata hâlinde kullanıcı
   sunucunun düz metin yanıtını ham sayfa olarak görüyordu. */
function dokDosyaIndir(veri, ad) {
    const adres = URL.createObjectURL(veri);
    const bag = document.createElement("a");
    bag.href = adres;
    bag.download = ad;
    document.body.appendChild(bag);
    bag.click();
    document.body.removeChild(bag);
    // Adres, tarayıcı indirmeyi başlattıktan sonra bırakılır.
    setTimeout(() => {
        try { URL.revokeObjectURL(adres); } catch (e) { /* yok say */ }
    }, 0);
}

function dokWordIndir() {
    if (!dokWordBtn || dokWordBtn.disabled) return;
    dokIndirmeHataYaz("");
    const etiket = dokWordBtn.textContent;
    dokWordBtn.disabled = true;
    dokWordBtn.textContent = "İndiriliyor…";
    const bitir = () => {
        dokWordBtn.disabled = false;
        dokWordBtn.textContent = etiket;
    };

    fetch(getWebAppBackendUrl("dokuman_word")
          + "?oturum_id=" + encodeURIComponent(OTURUM_ID))
        .then(r => {
            /* Uç hata hâlinde .docx değil DÜZ METİN dönüyor; onu dosya
               diye indirmek kullanıcıya açılmayan bir belge vermekti. */
            if (!r.ok) return r.text().then(m => {
                throw new Error(m || ("Sunucu " + r.status + " döndü."));
            });
            return r.blob();
        })
        .then(veri => { dokDosyaIndir(veri, DOKUMAN_DOSYA_ADI); bitir(); })
        .catch(e => {
            bitir();
            dokIndirmeHataYaz("Word dosyası indirilemedi: "
                              + ((e && e.message) || e));
        });
}

if (dokWordBtn) dokWordBtn.onclick = dokWordIndir;


/* ==================== Analiz paneli ==================== */
/* VERİ & SÖZLÜK (ozet), HAZIRLIK (hazirlik), SFA ve VALİDASYON sekmeleri
   backend verisiyle cizilir; asagidaki iskelet YALNIZCA henuz baglanmamis
   sekmeler icindir (dagilim, iliski). */
const ANALIZ_ICERIK = {
    dagilim: {
        kartlar: [
            {grafik: "Histogram"},
            {baslik: "Yüzdelik", satirlar: ["min / p1 / p25 / medyan", "p75 / p99 / maks"]},
            {baslik: "Aykırı değer", satirlar: ["IQR Dışı Oran", "Budama önerisi"]}
        ]
    },
    iliski: {
        kartlar: [
            {baslik: "Korelasyon", satirlar: ["Pearson / Spearman", "Cramér's V",
                                              "Yüksek korelasyon çiftleri"]},
            {grafik: "Korelasyon matrisi"},
            {baslik: "Çoklu doğrusallık", satirlar: ["VIF uyarıları"]}
        ]
    }
};

/* Durum kodu -> cip etiketi (buyuk harf burada yazili; CSS donusturmez) */
const CIP_ETIKET = {
    gecti:    "GEÇTİ",
    kosullu:  "KOŞULLU",
    kaldi:    "KALDI",
    bekliyor: "BEKLİYOR",
    veri_yok: "VERİ YOK",
    // Olculemedi: skorda NaN var ya da bin sayisi yetersiz.
    // "veri yok"tan farkli — hesap denendi ama guvenilir sonuc cikmadi.
    hesaplanamadi: "HESAPLANAMADI"
};

function cipYap(durum) {
    const c = document.createElement("span");
    c.className = "cip " + (CIP_ETIKET[durum] ? durum : "bekliyor");
    c.textContent = CIP_ETIKET[durum] || CIP_ETIKET.bekliyor;
    return c;
}

function elYap(etiket, sinif, metin) {
    const e = document.createElement(etiket);
    if (sinif) e.className = sinif;
    if (metin !== undefined) e.textContent = tireSade(metin);
    return e;
}

/* Backend'e bagli olmayan sekmeler: icerik iskelet, bu acikca yazilir.
   Tiklanamayan sahte aksiyon satirlari YOK.
   "Hazırlanıyor" bilgisi YALNIZCA burada ve sekmenin title'inda durur;
   sekme etiketinin rengiyle anlatilmaz (soluk sekme hata sanildi). */
function hazirlaniyorNotu() {
    const kart = elYap("div", "iskele-kart hazirlaniyor");
    kart.appendChild(elYap("div", "iskele-baslik", "Hazırlanıyor"));
    kart.appendChild(elYap("div", "val-ozet",
        "Bu sekmenin hesapları henüz bağlanmadı; aşağıdaki başlıklar planlanan "
        + "içeriği gösterir. Dolu olan sekmeler: VERİ & SÖZLÜK, HAZIRLIK, SFA, "
        + "VALİDASYON."));
    analizGovde.appendChild(kart);
}

function iskeletCiz(t) {
    hazirlaniyorNotu();
    /* Secici altyapisi kuruldu ama bu sekmelerin hesabi henuz bagli
       degil: secimin neye etki edecegini gostermek icin secilen setin
       ADI yaziliyor (bkz. SOZLESME2 §7). */
    analizGovde.appendChild(elYap("div", "set-kapsam",
        "Seçili kapsam: " + setAdi(AKTIF_SET)
        + " - hesaplar bağlandığında bu sekme o sette gösterilecek."));
    t.kartlar.forEach(k => {
        const kart = elYap("div", "iskele-kart");

        if (k.grafik) {
            kart.appendChild(elYap("div", "iskele-grafik", k.grafik));
        } else {
            kart.appendChild(elYap("div", "iskele-baslik", k.baslik));
            (k.satirlar || []).forEach(s => {
                const satir = elYap("div", "iskele-satir");
                satir.appendChild(elYap("span", "", s));
                satir.appendChild(elYap("span", "iskele-deger", BOS_SIMGE));
                kart.appendChild(satir);
            });
        }
        analizGovde.appendChild(kart);
    });
}

function validasyonCiz(v) {
    if (!v) {
        const kart = elYap("div", "iskele-kart");
        kart.appendChild(elYap("div", "val-ozet",
            "Validasyon bilgisi şu anda görüntülenemiyor. Final model adımı "
            + "tamamlandığında bu sekme kendiliğinden güncellenir."));
        analizGovde.appendChild(kart);
        return;
    }
    if (v.hata) {
        const kart = elYap("div", "iskele-kart val-kart kaldi");
        kart.appendChild(elYap("div", "iskele-baslik", "Validasyon Hesaplanamadı"));
        kart.appendChild(elYap("div", "val-ozet", v.hata));
        analizGovde.appendChild(kart);
        return;
    }

    // 1) Genel sonuc
    const sonuc = elYap("div", "iskele-kart val-kart " + v.genel);
    const ust = elYap("div", "val-sonuc");
    const sol = elYap("div", "");
    const baslik = elYap("div", "iskele-baslik", "Final Model Sonucu");
    baslik.style.marginBottom = "0";
    sol.appendChild(baslik);
    if (v.model) sol.appendChild(elYap("div", "val-model", v.model));
    ust.appendChild(sol);
    ust.appendChild(cipYap(v.genel));
    sonuc.appendChild(ust);
    sonuc.appendChild(elYap("div", "val-ozet", v.ozet || ""));
    analizGovde.appendChild(sonuc);

    // 2) Kriterler
    const liste = elYap("div", "iskele-kart");
    liste.appendChild(elYap("div", "iskele-baslik", "Kriterler"));
    (v.satirlar || []).forEach(s => {
        const satir = elYap("div", "val-satir");
        satir.title = s.aciklama || "";

        const solK = elYap("div", "val-sol");
        solK.appendChild(elYap("div", "val-ad", s.ad));
        solK.appendChild(elYap("div", "val-esik", s.esik));
        satir.appendChild(solK);

        const sagK = elYap("div", "val-sag");
        sagK.appendChild(elYap("div", "val-deger", degerGoster(s.deger)));
        sagK.appendChild(cipYap(s.durum));
        satir.appendChild(sagK);

        liste.appendChild(satir);
    });
    liste.appendChild(elYap("div", "val-not",
        "Açıklama için kriterin üzerine gelin. Eşikler kütüphanedeki "
        + "validasyon.py dosyasında tanımlıdır."));
    analizGovde.appendChild(liste);
}

/* Genel panel cizici: VERİ & SÖZLÜK / HAZIRLIK / SFA sekmeleri.
   Govde: {durum, bekleme_notu, kartlar:[{baslik, not, satirlar}], tablo} */
/* Tablo govdesi: {kolonlar, satirlar}. Panel sekmeleri de OZET sayfasindaki
   dokuman da bu ciktiyi kullanir — iki ayri tablo cizici, iki ayri gorsel
   dil demekti. */
function tabloYap(t) {
    const tablo = elYap("table", "panel-tablo");
    const bas = elYap("thead");
    const basSatir = elYap("tr");
    (t.kolonlar || []).forEach(k => basSatir.appendChild(elYap("th", "", k)));
    bas.appendChild(basSatir);
    tablo.appendChild(bas);

    const govde = elYap("tbody");
    (t.satirlar || []).forEach(s => {
        const tr = elYap("tr");
        (s || []).forEach((h, i) => {
            const td = elYap("td", i === 0 ? "panel-ad" : "", degerGoster(h));
            // Uzun kolon adlari kirpilir; tam degeri tooltip'te durur.
            td.title = tireSade(h === null || h === undefined ? "" : h);
            tr.appendChild(td);
        });
        govde.appendChild(tr);
    });
    tablo.appendChild(govde);
    return tablo;
}

function panelTabloCiz(t) {
    const kart = elYap("div", "iskele-kart");
    if (t.baslik) kart.appendChild(elYap("div", "iskele-baslik", t.baslik));
    kart.appendChild(tabloYap(t));

    if (t.toplam && t.gosterilen && t.toplam > t.gosterilen) {
        kart.appendChild(elYap("div", "val-not",
            t.toplam + " satırın ilk " + t.gosterilen
            + " tanesi gösteriliyor; tam tablo veri setinde."));
    }
    analizGovde.appendChild(kart);
}

function panelCiz(v) {
    if (!v) {
        const kart = elYap("div", "iskele-kart");
        kart.appendChild(elYap("div", "val-ozet",
            "Bu sekmenin verisi şu anda görüntülenemiyor. Sonraki yanıtta "
            + "kendiliğinden güncellenir."));
        analizGovde.appendChild(kart);
        return;
    }
    if (v.hata) {
        const kart = elYap("div", "iskele-kart val-kart kaldi");
        kart.appendChild(elYap("div", "iskele-baslik", "Hesaplanamadı"));
        kart.appendChild(elYap("div", "val-ozet", v.hata));
        analizGovde.appendChild(kart);
        return;
    }

    /* Bolme formu kartlardan ONCE: HAZIRLIK sekmesinin asil kontrolu bu
       ve profil beklemeden gorunmesi gerekiyor - sekme "bekliyor"
       durumundayken de kullanici bolmesini duzenleyebilmeli. */
    if (v.bolme_formu) bolmeFormuCiz(v.bolme_formu);

    if (v.durum === "bekliyor" && v.bekleme_notu) {
        const kart = elYap("div", "iskele-kart hazirlaniyor");
        kart.appendChild(elYap("div", "iskele-baslik", "Henüz Hesaplanmadı"));
        kart.appendChild(elYap("div", "val-ozet", v.bekleme_notu));
        analizGovde.appendChild(kart);
    }

    /* KARTLAR HER ZAMAN ACIK (kullanici karari). Bir sure "sozluk
       teyidi" adiminda katli aciliyorlardi: iki kart acikken tablo
       basligi ekranin altina kayiyordu. Ama teyit artik SOHBET
       BLOGUNDA yapiliyor; sag panel yalnizca aciklama veriyor, orada
       gizlenecek bir karar yok. Katlama hem bilgiyi saklayip hem de
       fazladan bir tiklama istiyordu. */
    (v.kartlar || []).forEach(k => {
        const kart = elYap("div", "iskele-kart");
        kart.appendChild(elYap("div", "iskele-baslik", k.baslik));
        if (k["not"]) kart.appendChild(elYap("div", "panel-not", k["not"]));
        (k.satirlar || []).forEach(s => {
            const satir = elYap("div", "iskele-satir");
            satir.appendChild(elYap("span", "panel-etiket", s.etiket));
            const deger = elYap("span", "iskele-deger", degerGoster(s.deger));
            deger.title = tireSade(s.deger === null || s.deger === undefined
                                   ? "" : s.deger);
            satir.appendChild(deger);
            kart.appendChild(satir);
        });
        analizGovde.appendChild(kart);
    });

    // Feature tablosu kartlardan SONRA gelir: kartlar veri setinin ozeti,
    // tablo tek tek kolonlar. Once genel, sonra ayrinti.
    /* SAG PANEL SALT OKUNUR (kullanici karari). Degisken listesi burada
       yalnizca GORULUYOR; isaretleme ve tanim duzenleme sohbetteki
       sozluk teyidi kartinda yapiliyor. Ayni karari iki yerden
       vermek, hangisinin gecerli oldugunu belirsizlestiriyordu. */
    if (v.feature_tablo) featureTabloCiz(ftSaltOku(v.feature_tablo));
    if (v.tablo) panelTabloCiz(v.tablo);
}


/* ==================== Feature tablosu ==================== */
/* VERİ & SÖZLÜK sekmesinde 1.000'in uzerinde satir olabiliyor. Tum
   satirlari DOM'a basmak paneli kilitliyordu; yalnizca gorunen pencere
   + tampon ciziliyor, kalani bos yer tutucu yukseklik.

   Satir yuksekligi SABIT: sanallastirmanin tek varsayimi bu. Degeri
   style.css'teki .ft-satir yuksekligiyle AYNI olmali, yoksa kaydirma
   ile cizim birbirinden kayar. */
const FT_SATIR_H = 26;
/* Pencerenin altinda ve ustunde hazir tutulan satir: hizli kaydirmada
   bos serit gorunmesin. */
const FT_TAMPON = 6;
/* clientHeight okunamadiginda (panel henuz olculmedi / cekmece kapali)
   kullanilan gorunur yukseklik. Sifir olursa hic satir cizilmez. */
const FT_VARSAYILAN_YUKSEKLIK = 360;

/* Surec disi birakilmis kolonun satir govdesindeki DURUM degeri. Kolon
   olarak artik gosterilmiyor (SOZLESME7 §5) ama satiri soluk cizmek ve
   acilista hangi kutunun isaretli gelecegini bilmek icin okunuyor. */
const FT_DISI = "süreç dışı";

/* ÜÇ KOLON (kullanıcı kararı): "sağ barda da değişken, tip, sözlük
   tanımı yer alsın sadece". NULL %% kolonu, süreç dışı kararının
   VERİLDİĞİ yere - sohbetteki teyit tablosuna - taşındı; orada onay
   kutusunun hemen solunda duruyor. Satır gövdesi null_oran'ı taşımaya
   devam ediyor: satıra tıklayınca açılan detay ve null eşiği süzgeci
   onu okuyor.

   Panel artık karar yeri değil, AÇIKLAMA yeri: düzenleme ve süreç dışı
   işaretleme sohbetteki kartta yapılıyor (bkz. ftSaltOku). */
const FT_ALANLAR = [
    { alan: "feature",   baslik: "DEĞİŞKEN",      sinif: "ft-ad" },
    { alan: "tip",       baslik: "TİP" },
    { alan: "tanim",     baslik: "SÖZLÜK TANIMI", sinif: "ft-tanim" }
];

/* Panel her backend yanitinda yeniden ciziliyor; arama/siralama/secim
   burada durdugu icin cizim arasinda kaybolmuyor. */
const FT = {
    arama: "", nullEsik: "",
    tip: "",                  // panel tip suzgeci ("" = tumu)
    sira: null, yon: 1,
    /* ISARETLI = SUREC DISI. Eski "toplu kategori icin secim" anlami
       kalktı; kutu artik dogrudan bir karar. */
    haric: new Set(),         // surec disi birakilan degisken adlari
    haricBekleyen: false,     // /haric_kolonlar yazimi ucusta mi
    detay: null,              // acik detayin degisken adi
    taslak: new Map(),        // ad -> henuz gonderilmemis tanim metni
    kaydirma: 0,
    hatalar: new Map(),       // degisken -> satirda gosterilecek hata
    bekleyen: new Set(),      // yazmasi ucusta olan degiskenler
    topluNot: "", topluHata: "",
    dom: null, veri: null, suzulmus: [],
    pencere: null            // {ust, alt}: DOM'da duran satir araligi
};

/* Turkce karakter + tanilama duyarsiz arama anahtari: "işlem" ~ "islem",
   "TUTARı" ~ "tutari". Kullanici sozlukteki harfi birebir yazmak
   zorunda kalmasin. */
const FT_HARF = {
    "ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
    "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c",
    "â": "a", "Â": "a", "î": "i", "Î": "i", "û": "u", "Û": "u"
};
function ftSade(s) {
    return String(s === null || s === undefined ? "" : s)
        .replace(/[ıİşŞğĞüÜöÖçÇâÂîÎûÛ]/g, ch => FT_HARF[ch])
        .toLowerCase();
}

/* Binlik ayraci nokta: 1042 -> "1.042". toLocaleString kullanilmiyor,
   Dataiku sunucusunun yerel ayari tarayiciyla ayni olmayabiliyor. */
function ftBinlik(n) {
    /* null/"" -> ∅. Number(null) 0 dondurdugu icin acik kontrol SART:
       "tekil deger yok" ile "tekil deger 0" ayni sey degil. */
    if (n === null || n === undefined || n === "") return BOS_SIMGE;
    const t = Math.round(Number(n));
    if (!isFinite(t)) return BOS_SIMGE;
    return (t < 0 ? "-" : "")
        + String(Math.abs(t)).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

function ftOran(x) {
    if (x === null || x === undefined || x === "") return BOS_SIMGE;
    const s = Number(x);
    if (!isFinite(s)) return BOS_SIMGE;
    return "%" + (s * 100).toFixed(1).replace(".", ",");
}

function ftOndalik(x, b) {
    if (x === null || x === undefined || x === "") return BOS_SIMGE;
    const s = Number(x);
    if (!isFinite(s)) return BOS_SIMGE;
    return s.toFixed(b === undefined ? 3 : b).replace(".", ",");
}

function ftSatirBul(ad) {
    const liste = (FT.veri && FT.veri.satirlar) || [];
    for (let i = 0; i < liste.length; i++)
        if (liste[i].feature === ad) return liste[i];
    return null;
}

/* Filtre ya da siralama degisince mevcut kaydirma konumu anlamini
   yitiriyor: pencere bastan baslamali, yoksa kullanici "sonuc yok"
   sanip bos ekrana bakiyor. */
function ftBasaSar() {
    FT.kaydirma = 0;
    FT.pencere = null;
    FT.gosterilen = 0;
    if (FT.dom && FT.dom.govde) FT.dom.govde.scrollTop = 0;
}

/* ---- Suzme ve siralama ---- */
function ftSuz() {
    const liste = (FT.veri && FT.veri.satirlar) || [];
    const aranan = ftSade(FT.arama).trim();
    const esik = FT.nullEsik === "" ? null : Number(FT.nullEsik) / 100;

    const tip = String(FT.tip || "").trim();

    let sonuc = liste.filter(s => {
        if (aranan && ftSade(s.feature).indexOf(aranan) === -1
            && ftSade(s.tanim).indexOf(aranan) === -1) return false;
        /* TIP SUZGECI tam esleme: "sayısal" secildiginde "sayısal"
           kolonlar gelir. Parca eslemesi yapsaydik gelecekte eklenecek
           bir tip adi baskasini da yakalardi. */
        if (tip && String(s.tip || "").trim() !== tip) return false;
        if (esik !== null && isFinite(esik)) {
            /* null_oran bilinmiyorsa esigi GECTIGI soylenemez: kolon
               eleniyor. Aksi halde profillenmemis kolonlar "eşiği aşan"
               listesine sizip yanlis is emri uretiyordu. */
            if (s.null_oran === null || s.null_oran === undefined) return false;
            if (Number(s.null_oran) <= esik) return false;
        }
        return true;
    });

    if (FT.sira) {
        const alan = FT.sira;
        const sayisal = (FT_ALANLAR.find(a => a.alan === alan) || {}).sayisal;
        const yon = FT.yon;
        sonuc = sonuc.slice().sort((a, b) => {
            const x = a[alan], y = b[alan];
            /* Bos deger yonden BAGIMSIZ olarak sona gider: azalan
               siralamada ∅ yiginini once gostermek tabloyu okunmaz
               yapiyordu. */
            const xBos = x === null || x === undefined || x === "";
            const yBos = y === null || y === undefined || y === "";
            if (xBos && yBos) return 0;
            if (xBos) return 1;
            if (yBos) return -1;
            if (sayisal) return (Number(x) - Number(y)) * yon;
            return String(x).localeCompare(String(y), "tr") * yon;
        });
    }
    FT.suzulmus = sonuc;
}

/* ---- Yazma uclari ---- */
/* Govdede hem oturum_id hem calisma_id gonderiliyor: backend
   _calisma_id() "oturum_id" okuyor, sozlesme "calisma_id" diyor.
   Ikisini de yollamak tek satirlik bedel, eksigi sessiz hata. */
function ftKimlikGovdesi(ek) {
    return Object.assign({ oturum_id: OTURUM_ID, calisma_id: OTURUM_ID }, ek);
}

/* ---- Teyit kartinin kendi kayit yollari ----
   Sag paneldeki tablo FT tekilinin uzerinde calisiyor; teyit karti
   sohbette ve AYNI ANDA ekranda olabiliyor, ikisi tek duruma yazsa
   birbirinin filtresini ve sanal penceresini bozardi. Uclar ayni,
   durum ayri. */
let teyitListesi = null;          // kart kilitlenince satirlari kapatmak icin

/* ---- Excel indirme şeridi ----
   Hem sohbetteki teyit kartı hem sağ panel aynı şeridi kullanıyor;
   ikisi de aynı uca gidiyor, yalnızca `tur` farklı (liste / sozluk).
   Tek bir üretici olması, iki yerde iki ayrı indirme davranışı
   çıkmasını engelliyor.

   SİMGE İNLİNE SVG: dış kaynaktan ikon çekilmiyor (Dataiku webapp'i
   kapalı ağda çalışabiliyor) ve emoji kullanılmıyor - emoji her
   işletim sisteminde başka türlü çiziliyor. */
const EXCEL_SIMGESI =
    '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">'
    + '<path fill="currentColor" d="M9 1H3.5A1.5 1.5 0 0 0 2 2.5v11A1.5 1.5 0'
    + ' 0 0 3.5 15h9a1.5 1.5 0 0 0 1.5-1.5V6L9 1zm0 1.5L12.5 6H9V2.5z"/>'
    + '<path fill="currentColor" d="M4.6 8h1.3l.9 1.5L7.7 8H9L7.5 10.3 9.1'
    + ' 12.8H7.8l-1-1.6-1 1.6H4.5l1.6-2.5L4.6 8z"/></svg>';

/* Dosya adları: uç Content-Disposition da gönderiyor ama blob ile
   indirdiğimiz için başlık okunmuyor, ad burada duruyor (bkz.
   DOKUMAN_DOSYA_ADI ile aynı gerekçe). */
const EXCEL_ADLARI = { liste: "degisken_listesi.xlsx",
                       sozluk: "degisken_sozlugu.xlsx",
                       kisaltma: "kisaltma_onerileri.xlsx" };
/* Tür -> uç. Kısaltma raporu kendi ucundan gelir (teyit kapısı yok). */
const EXCEL_UCLARI = { kisaltma: "kisaltma_excel" };

function excelSeridiYap(tur, etiket, ipucu) {
    const el = elYap("div", "excel-serit");

    const btn = document.createElement("button");
    btn.type = "button";
    /* YEŞİL ve İKİ DURUMLU (kullanıcı kararı): basılabildiğinde koyu
       yeşil, basılamadığında açık yeşil. Şerit artık GİZLENMİYOR -
       gizli bir düğme "bu özellik yok" diye okunuyordu; kilitli ama
       görünür düğme "henüz değil" diyor ve ipucunda neden yazıyor. */
    btn.className = "excel-btn";
    btn.innerHTML = EXCEL_SIMGESI;
    btn.appendChild(document.createTextNode(tireSade(etiket)));
    btn.disabled = true;
    btn.title = tireSade(ipucu || "");
    el.appendChild(btn);

    const hata = elYap("span", "excel-hata");
    hata.hidden = true;
    el.appendChild(hata);

    btn.onclick = () => {
        if (btn.disabled) return;
        hata.hidden = true;
        const eski = btn.lastChild.nodeValue;
        btn.disabled = true;
        btn.lastChild.nodeValue = "İndiriliyor…";
        const bitir = () => {
            btn.disabled = false;
            btn.lastChild.nodeValue = eski;
        };
        fetch(getWebAppBackendUrl(EXCEL_UCLARI[tur] || "degisken_excel")
              + "?tur=" + encodeURIComponent(tur)
              + "&oturum_id=" + encodeURIComponent(OTURUM_ID))
            .then(r => {
                /* Uç hata hâlinde .xlsx değil DÜZ METİN dönüyor; onu
                   dosya diye indirmek açılmayan bir tablo vermekti. */
                if (!r.ok) return r.text().then(m => {
                    throw new Error(m || ("Sunucu " + r.status + " döndü."));
                });
                return r.blob();
            })
            .then(veri => {
                dokDosyaIndir(veri, EXCEL_ADLARI[tur] || "degiskenler.xlsx");
                bitir();
            })
            .catch(e => {
                bitir();
                hata.textContent = "Excel indirilemedi: "
                                   + ((e && e.message) || e);
                hata.hidden = false;
            });
    };

    return { el: el, dugme: btn,
             ac: (acik) => {
                 btn.disabled = !acik;
                 btn.title = acik ? "" : tireSade(ipucu || "");
                 if (!acik) hata.hidden = true;
             } };
}

/* Sohbetteki sözlük teyidi kartının sıralama seçenekleri. Panelden
   farklı: burada KARAR veriliyor, o yüzden "süreç dışı önce" ve
   "tanımı olmayanlar önce" de var - gözden geçirmesi gereken satırları
   başa almak listenin en sık kullanılan halidir. */
const DG_SIRALAMA = [
    { deger: "",            etiket: "Sırala: varsayılan" },
    { deger: "feature:a",   etiket: "Değişken A→Z" },
    { deger: "feature:z",   etiket: "Değişken Z→A" },
    { deger: "tip:a",       etiket: "Tip A→Z" },
    { deger: "disi:z",      etiket: "Süreç dışı önce" },
    { deger: "tanimsiz:a",  etiket: "Tanımı olmayanlar önce" }
];

function teyitHatasi(el, metin) {
    if (!el) return;
    el.textContent = tireSade(metin || "");
    el.hidden = !metin;
}

function tanimKaydet(kolon, giris, hataEl) {
    const eski = giris.dataset.eski === undefined ? giris.defaultValue
                                                  : giris.dataset.eski;
    const deger = (giris.value || "").trim();
    if (deger === (eski || "").trim()) return;
    giris.disabled = true;
    fetch(getWebAppBackendUrl("sozluk_tanim"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(ftKimlikGovdesi({ kolon: kolon, tanim: deger }))
    })
    .then(r => r.json())
    .then(d => {
        giris.disabled = false;
        if (!d || d.tamam !== true) {
            /* Yazildi izlenimi verip sessizce kaybetmek, sozluk
               duzenlemesinde en pahali hata: eski degere DONULUR. */
            giris.value = eski || "";
            teyitHatasi(hataEl, (d && d.hata) || "Tanım yazılamadı.");
            return;
        }
        if (typeof d.tanim === "string") giris.value = d.tanim;
        giris.dataset.eski = giris.value;
        teyitHatasi(hataEl, "");
    })
    .catch(e => {
        giris.disabled = false;
        giris.value = eski || "";
        teyitHatasi(hataEl, "Tanım yazılamadı: " + e);
    });
}

function haricKaydet(kolon, kutu, hataEl) {
    const liste = (teyitListesi ? teyitListesi() : [])
        .filter(r => r.kutu.checked).map(r => r.tr.dataset.kolon);
    kutu.disabled = true;
    fetch(getWebAppBackendUrl("haric_kolonlar"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(ftKimlikGovdesi({ kolonlar: liste }))
    })
    .then(r => r.json())
    .then(d => {
        kutu.disabled = false;
        if (!d || d.tamam !== true) {
            /* Ya hepsi ya hicbiri: uygulanmamis bir kutuyu isaretli
               birakmak, surec disi kararinda en pahali hata. */
            kutu.checked = !kutu.checked;
            kutu.closest("tr").dataset.islem = kutu.checked ? "haric" : "ekle";
            if (kutu._disiCiz) kutu._disiCiz();
            teyitHatasi(hataEl, (d && d.hata) || "Süreç dışı listesi yazılamadı.");
            return;
        }
        /* Kartın özet satırı ("1.042 değişken · 2 süreç dışı · …") uçtan
           taze geliyor ama DOM'a yazılmıyordu: kullanıcı kutuyu
           işaretliyor, sağ paneldeki sayı değişiyor, BAKTIĞI karttaki
           sayı eskisinde kalıyordu. */
        const oz = document.querySelector(".teyit-kart .teyit-ozet");
        if (oz && d.ozet) oz.textContent = tireSade(d.ozet);
        /* Uç, hedef/kimlik/dönem kolonunu listeden ÇIKARMIŞ olabilir
           (tamam:true ama reddedilen dolu). Kutuyu işaretli bırakmak
           "süreç dışı bıraktım" izlenimi verirdi; geri alınıp sebebi
           yazılıyor. */
        if ((d.reddedilen || []).length) {
            (d.reddedilen || []).forEach(k => {
                const t = document.querySelector(
                    '.teyit-kart .dg-satir[data-kolon="' + k + '"]');
                const kk = t && t.querySelector(".dg-ekle");
                if (kk) {
                    /* Uç zorunlu dışı kolonu (tek değerli) GERİ EKLEMİŞ
                       olabilir: kutu sunucunun listesine göre kurulur. */
                    kk.checked = (d.kolonlar || []).indexOf(k) !== -1;
                    t.dataset.islem = kk.checked ? "haric" : "ekle";
                    if (kk._disiCiz) kk._disiCiz();
                }
            });
            teyitHatasi(hataEl, d.hata || "Bu kolon süreç dışı bırakılamaz.");
            return;
        }
        teyitHatasi(hataEl, "");
    })
    .catch(e => {
        kutu.disabled = false;
        kutu.checked = !kutu.checked;
        if (kutu._disiCiz) kutu._disiCiz();
        teyitHatasi(hataEl, "Süreç dışı listesi yazılamadı: " + e);
    });
}

/* TİP DEĞİŞTİRME - sözlük teyidinde.
   Seçenek listesi kartta KÜÇÜK BİR ÖRNEKLE hazırlanıyor; bu istek aynı
   dönüşümü kolonun TAMAMINA uyguluyor. Tek değer bile takılırsa uç
   "tamam:false" döner, seçim ESKİ DEĞERİNE geri alınır ve sebebi satırın
   üstünde yazar. Böylece ekranda görünen tip ile veri setindeki tip
   hiçbir anda ayrışmıyor - kullanıcı "değiştirmemde sorun yoksa
   onaylansın" dediği için onay bu uçta veriliyor. */
/* SATIR RENGİ (kullanıcı kararı: "kırmızı hata varmış gibi gösteriyor").
     karar öncesi : SARI  = açıklama boş
                    MAVİ  = dil modelinin önerisi (değiştirilmemiş)
                    renksiz = kullanıcının yazdığı / değiştirdiği metin
     karar sonrası: YEŞİL = sözlüğe eklendi / düzeltme uygulandı
                    KIRMIZI = eklenmedi / uygulanmadı
   karar: null (karar verilmedi), "evet", "hayir". */
/* Onaylı tanım hafızasından gelen satır: değişken adının yanında çip,
   satır yeşil-mavi değil kendi tonunda (dg-hafiza-satir). */
function hafizaCipi(td, tr, veriSeti) {
    if (!td || !tr) return;
    /* Kısa çip "OT" (Onaylı Tanım); açılımı ve kaynağı ipucunda. */
    const c = elYap("span", "dg-rol dg-hafiza", "OT");
    c.title = "OT: Onaylı Tanım. Daha önce onaylanmış tanım" + (veriSeti ? " (veri seti: " + tireSade(veriSeti) + ")" : "")
        + "; dil modeli çağrılmadı.";
    td.appendChild(c);
    tr.classList.add("dg-hafiza-satir");
}

function dgRenk(tr, metin, oneri, karar) {
    if (!tr) return;
    const m = String(metin || "").trim();
    const o = String(oneri || "").trim();
    tr.classList.toggle("dg-bos", !karar && !m);
    const hafiza = tr.classList.contains("dg-hafiza-satir");
    tr.classList.toggle("dg-llm", !karar && !!m && !!o && m === o && !hafiza);
    tr.classList.toggle("dg-hafiza-renk", !karar && !!m && !!o && m === o && hafiza);
    tr.classList.toggle("dg-eklendi", karar === "evet");
    tr.classList.toggle("dg-eklenmedi", karar === "hayir");
    /* Kullanıcının yazdığı / değiştirdiği metin (01.2 kartlarında yeşil). */
    tr.classList.toggle("dg-duzenlendi", !karar && !!m && m !== o);
}
/* Renk açıklaması: küçük renk kutuları + kısa etiket. */
function dgLejant(ogeler) {
    const kap = elYap("div", "dg-lejant");
    ogeler.forEach(([sinif, metin]) => {
        const o = elYap("span", "dg-lejant-oge");
        o.appendChild(elYap("span", "dg-lejant-kutu " + sinif));
        o.appendChild(document.createTextNode(metin));
        kap.appendChild(o);
    });
    return kap;
}
/* 01.2 SADE RENK (kullanıcı kararı: "renk cümbüşü"): 01.2 kartlarında
   üç anlam var. Renksiz: öneri / normal durum. Sarı: dikkat gerektiren
   (boş, farklı, uyarılı). Yeşil: sizin yazdığınız ya da değiştirdiğiniz.
   Onaylı tanım "OT" çipiyle, seçim kutuyla belli; ayrı renk yok. */
const DG_LEJANT_KARAR = [["dg-l-renksiz", "Dil Modeli Önerisi"],
                         ["dg-l-dikkat", "Boş"],
                         ["dg-l-duzenlendi", "Düzenlendi"]];
const DG_LEJANT_TEYIT = [["dg-l-bos", "Tanım Boş"], ["dg-l-llm", "Dil Modeli Önerisi"]];

function tipKaydet(kolon, sec, tipEl, hataEl) {
    const eski = sec.dataset.eski === undefined ? "" : sec.dataset.eski;
    const kod = sec.value || "";
    if (kod === eski) return;
    sec.disabled = true;
    fetch(getWebAppBackendUrl("tip_degistir"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(ftKimlikGovdesi({ kolon: kolon, kod: kod }))
    })
    .then(r => r.json())
    .then(d => {
        sec.disabled = false;
        if (!d || d.tamam !== true) {
            sec.value = eski;
            if (sec._vurgu) sec._vurgu();
            teyitHatasi(hataEl, (d && d.hata) || "Tip değiştirilemedi.");
            return;
        }
        sec.dataset.eski = kod;
        if (sec._vurgu) sec._vurgu();
        if (tipEl && d.tip) tipEl.textContent = tireSade(d.tip);
        const oz = document.querySelector(".teyit-kart .teyit-ozet");
        if (oz && d.ozet) oz.textContent = tireSade(d.ozet);
        teyitHatasi(hataEl, "");
    })
    .catch(e => {
        sec.disabled = false;
        sec.value = eski;
        if (sec._vurgu) sec._vurgu();
        teyitHatasi(hataEl, "Tip değiştirilemedi: " + e);
    });
}

/* Tek hucre: iyimser yaz, hata donerse ESKI degere don ve satirda goster.
   Kullaniciya yazildi izlenimi verip sessizce kaybetmek, sozluk
   duzenlemesinde en pahali hata. */
/* SOZLESME7 §5: yazilan yer YALNIZCA sozlugun calisma kopyasi; orijinal
   sozluge dokunulmaz. Uc govdesi sozlesmedeki gibi {oturum_id, kolon,
   tanim}. */
function ftTanimYaz(satir, yeni) {
    const ad = satir.feature;
    const eski = satir.tanim === null || satir.tanim === undefined
                 ? "" : String(satir.tanim);
    const deger = String(yeni === null || yeni === undefined ? "" : yeni).trim();

    FT.taslak.delete(ad);
    if (deger === eski) { ftTazele(); return; }

    satir.tanim = deger;
    FT.hatalar.delete(ad);
    FT.bekleyen.add(ad);
    ftTazele();

    fetch(getWebAppBackendUrl("sozluk_tanim"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(ftKimlikGovdesi({ kolon: ad, tanim: deger }))
    })
    .then(r => r.json())
    .then(d => {
        FT.bekleyen.delete(ad);
        if (!d || d.tamam !== true) {
            satir.tanim = eski;
            FT.hatalar.set(ad, (d && d.hata) || "Tanım yazılamadı.");
        } else {
            /* Arka uc kirptiysa/normallestirdiyse EKRAN onu gostersin */
            if (typeof d.tanim === "string") satir.tanim = d.tanim;
            if (d.durum) satir.durum = d.durum;
            if (d.sozluk_kaynak) FT.veri.sozluk_kaynak = d.sozluk_kaynak;
        }
        ftTazele();
    })
    .catch(e => {
        FT.bekleyen.delete(ad);
        satir.tanim = eski;
        FT.hatalar.set(ad, "Tanım yazılamadı: " + e);
        ftTazele();
    });
}

/* Surec disi listesi TEK PARCA gonderilir: uc "su an hangi kolonlar
   disarida" sorusunun tam cevabini alir, artimsal fark degil. Boylece
   kacan bir istek listeyi yarim birakmaz.
   Sira tablo sirasidir; Set'in ekleme sirasi degil. */
function ftHaricListesi() {
    const liste = (FT.veri && FT.veri.satirlar) || [];
    return liste.map(s => s.feature).filter(ad => FT.haric.has(ad));
}

function ftHaricYaz(yeniSet) {
    const eski = new Set(FT.haric);
    FT.haric = new Set(yeniSet);
    FT.topluHata = "";
    FT.topluNot = "";
    FT.haricBekleyen = true;
    ftTazele();

    const kolonlar = ftHaricListesi();

    fetch(getWebAppBackendUrl("haric_kolonlar"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(ftKimlikGovdesi({ kolonlar: kolonlar }))
    })
    .then(r => r.json())
    .then(d => {
        FT.haricBekleyen = false;
        if (!d || d.tamam !== true) {
            /* Ya hepsi ya hicbiri: kullaniciya uygulanmamis bir kutuyu
               isaretli birakmak, surec disi kararinda en pahali hata. */
            FT.haric = eski;
            FT.topluHata = (d && d.hata) || "Süreç dışı listesi yazılamadı.";
        } else {
            if (Array.isArray(d.kolonlar))
                FT.haric = new Set(d.kolonlar.map(k => String(k)));
            ftDurumlariEsle();
            FT.topluNot = ftBinlik(FT.haric.size) + " değişken süreç dışı.";
        }
        ftTazele();
    })
    .catch(e => {
        FT.haricBekleyen = false;
        FT.haric = eski;
        FT.topluHata = "Süreç dışı listesi yazılamadı: " + e;
        ftTazele();
    });
}

/* Satir govdesindeki durum alanini isaretli kutularla ayni hale getirir:
   satirin soluk cizilmesi yazma yanitini beklemeden dogru gorunur. */
function ftDurumlariEsle() {
    ((FT.veri && FT.veri.satirlar) || []).forEach(s => {
        const disiMi = FT.haric.has(s.feature);
        if (disiMi) s.durum = FT_DISI;
        else if (s.durum === FT_DISI) s.durum = "";
    });
}

/* Zaten surec disi olan kolon ISARETLI gelir (SOZLESME7 §5). */
function ftHaricKur(t) {
    FT.haric = new Set();
    ((t && t.satirlar) || []).forEach(s => {
        if (s.durum === FT_DISI) FT.haric.add(s.feature);
    });
    if (Array.isArray(t && t.haric_kolonlar))
        t.haric_kolonlar.forEach(k => FT.haric.add(String(k)));
}

/* ---- Cizim ---- */
function ftOdakAnahtari() {
    const el = document.activeElement;
    if (!el || !el.getAttribute) return null;
    const anahtar = el.getAttribute("data-ft-odak");
    if (!anahtar) return null;
    const bilgi = { anahtar: anahtar };
    try { bilgi.bas = el.selectionStart; bilgi.son = el.selectionEnd; } catch (e) { /* select */ }
    return bilgi;
}

/* Panel her yanitta bastan ciziliyor; arama kutusundaki imlec yerinde
   kalmazsa kullanici yazarken kelimeyi kaybediyor. */
function ftOdakGeriVer(bilgi) {
    if (!bilgi) return;
    const el = analizGovde.querySelector('[data-ft-odak="' + bilgi.anahtar + '"]');
    if (!el) return;
    try {
        el.focus();
        if (bilgi.bas !== undefined && bilgi.bas !== null && el.setSelectionRange)
            el.setSelectionRange(bilgi.bas, bilgi.son);
    } catch (e) { /* odak verilemedi, onemli degil */ }
}

/* Baslik seridi TEK SATIR (SOZLESME7 §5):
   "1.042 degisken \u00b7 2 surec disi \u00b7 <sozluk> (calisma kopyasi)".
   Sozluk adi ayri bir elemanda duruyor (uzun adi kirpabilmek icin), bu
   parca sayilari yaziyor. */
function ftSayacMetni() {
    const toplam = (FT.veri && FT.veri.toplam) || (FT.veri.satirlar || []).length;
    const n = FT.suzulmus.length;
    if (!toplam) return "Gösterilecek değişken yok.";
    const bas = (n === toplam)
        ? ftBinlik(toplam) + " değişken"
        : ftBinlik(n) + " / " + ftBinlik(toplam) + " değişken";
    return bas + " \u00b7 " + ftBinlik(FT.haric.size) + " süreç dışı";
}

function ftSecim(anahtar, secenekler, deger, degisti) {
    const s = document.createElement("select");
    s.className = "ft-secim";
    if (anahtar) s.setAttribute("data-ft-odak", anahtar);
    secenekler.forEach(o => {
        const op = document.createElement("option");
        op.value = o.deger;
        op.textContent = o.etiket;
        s.appendChild(op);
    });
    s.value = deger;
    s.onchange = () => degisti(s.value);
    return s;
}

/* Sıralama seçenekleri. "null_oran" tabloda KOLON olarak yok ama satır
   gövdesinde duruyor; en çok boş kolonu bulmak sık gereken bir iş
   olduğu için sıralamada kalıyor. */
const FT_SIRALAMA = [
    { deger: "",              etiket: "Sırala: varsayılan" },
    { deger: "feature:a",     etiket: "Değişken A→Z" },
    { deger: "feature:z",     etiket: "Değişken Z→A" },
    { deger: "tip:a",         etiket: "Tip A→Z" },
    { deger: "tanim:a",       etiket: "Sözlük tanımı A→Z" },
    { deger: "null_oran:z",   etiket: "Null oranı ↓" },
    { deger: "null_oran:a",   etiket: "Null oranı ↑" }
];

/* Panelde gorunen TIP filtresi secenekleri. Listede fiilen bulunan
   tiplerden uretiliyor: veri setinde tarih kolonu yoksa "tarih"
   secenegini gostermek, sonuc vermeyecek bir filtre sunmak olurdu. */
function ftTipSecenekleri() {
    const tipler = [];
    ((FT.veri && FT.veri.satirlar) || []).forEach(s => {
        const t = String(s.tip || "").trim();
        if (t && tipler.indexOf(t) === -1) tipler.push(t);
    });
    tipler.sort((a, b) => a.localeCompare(b, "tr"));
    return [{ deger: "", etiket: "Tip: tümü" }]
        .concat(tipler.map(t => ({ deger: t, etiket: t })));
}

/* SAG PANEL: ARAMA + TIP SUZGECI + SIRALAMA (kullanıcı kararı).
   "bu kısımda sort filter yok onları da eklememiz lazım buraya"

   NULL EŞİĞİ BURADA YOK: null sütunu panelden kaldırıldı, eşik
   süzgecini görünmeyen bir sütuna bağlamak kullanıcıya nedenini
   göstermeden satır gizlerdi. Null'a göre süzme ve sıralama sohbetteki
   sözlük teyidi kartında (orada sütun duruyor).

   Panel bir KARAR yüzeyi değil, bakma yüzeyi: bu üç kontrol de listeyi
   daraltıp bulmaya yarıyor, hiçbiri veriyi değiştirmiyor.

   Sütun başlığına tıklayarak sıralama DURUYOR; açılır liste onun
   görünür karşılığı, ikisi aynı FT.sira/FT.yon alanını yazıyor. */
function ftFiltreCiz() {
    const kutu = elYap("div", "ft-filtreler");

    const ara = document.createElement("input");
    ara.type = "search";
    ara.className = "ft-ara";
    ara.setAttribute("data-ft-odak", "ara");
    ara.placeholder = "Değişken adı veya sözlük tanımında ara…";
    ara.setAttribute("aria-label", "Değişken adı veya sözlük tanımında ara");
    ara.value = FT.arama;
    ara.oninput = () => { FT.arama = ara.value; ftBasaSar(); ftTazele(); };
    kutu.appendChild(ara);

    const alt = elYap("div", "ft-filtre-alt");

    const tipler = ftTipSecenekleri();
    const tip = ftSecim("tip-suzgec", tipler, FT.tip || "", v => {
        FT.tip = v; ftBasaSar(); ftTazele();
    });
    tip.classList.add("ft-tip-suzgec");
    tip.setAttribute("aria-label", "Tipe göre süz");
    /* Tek tip varsa süzecek bir şey yok: kutu görünür ama pasif -
       gizlemek "filtre neden yok?" sorusunu doğuruyordu. */
    tip.disabled = tipler.length <= 2;
    if (tip.disabled) tip.title = "Listede tek tip var; süzmeye gerek yok.";
    alt.appendChild(tip);

    const sira = ftSecim("sirala", FT_SIRALAMA,
                         FT.sira ? (FT.sira + ":" + (FT.yon === 1 ? "a" : "z")) : "",
                         v => {
        const [alan, yon] = (v || ":").split(":");
        FT.sira = alan || "";
        FT.yon = yon === "z" ? -1 : 1;
        ftBasaSar();
        ftTazele();
    });
    sira.classList.add("ft-sirala");
    sira.setAttribute("aria-label", "Sırala");
    alt.appendChild(sira);

    kutu.appendChild(alt);
    return kutu;
}

/* Toplu surec disi: 1.042 kutuyu tek tek isaretlemek kullaniciyi bogar.
   KAPSAM FILTREYLE ESLESEN SATIRLAR: gorunmeyen 1.000 satiri tek tikla
   surec disi birakmak, geri donusu zor bir kaza olurdu. */
function ftTopluCiz() {
    const kutu = elYap("div", "ft-toplu");
    const gorunen = FT.suzulmus;
    const isaretli = gorunen.filter(s => FT.haric.has(s.feature)).length;

    kutu.appendChild(elYap("span", "ft-toplu-sayi",
        ftBinlik(isaretli) + " / " + ftBinlik(gorunen.length)
        + " değişken süreç dışı"));

    const dugme = (etiket, ipucu, pasif, isle) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "ft-mini";
        b.textContent = etiket;
        b.title = ipucu;
        b.disabled = pasif;
        b.onclick = isle;
        kutu.appendChild(b);
        return b;
    };

    const yazilabilir = !!(FT.veri && FT.veri.duzenlenebilir) && !FT.haricBekleyen;

    dugme("Tümünü Seç", "Filtreyle eşleşen değişkenlerin tümünü süreç dışına al",
          !yazilabilir || !gorunen.length || isaretli === gorunen.length,
          () => {
              const yeni = new Set(FT.haric);
              gorunen.forEach(s => yeni.add(s.feature));
              ftHaricYaz(yeni);
          });

    dugme("Tümünü Temizle", "Filtreyle eşleşen değişkenleri süreç dışından çıkar",
          !yazilabilir || !isaretli,
          () => {
              const yeni = new Set(FT.haric);
              gorunen.forEach(s => yeni.delete(s.feature));
              ftHaricYaz(yeni);
          });

    return kutu;
}

function ftBaslikCiz() {
    const bas = elYap("div", "ft-satir ft-baslik");
    bas.setAttribute("role", "row");

    if (FT.veri && FT.veri.duzenlenebilir) {
        const kap = elYap("span", "ft-hucre ft-sec");
        const tik = document.createElement("input");
        tik.type = "checkbox";
        tik.setAttribute("aria-label", "Görünen satırların tümünü süreç dışına al");
        tik.title = "Filtreyle eşleşen değişkenlerin tümünü süreç dışına al";
        const gorunen = FT.suzulmus;
        tik.checked = gorunen.length > 0
            && gorunen.every(s => FT.haric.has(s.feature));
        tik.disabled = FT.haricBekleyen;
        tik.onchange = () => {
            /* "Tumunu sec" YALNIZCA filtreyle eslesenleri kapsar:
               1.042 satirin tamamini gorunmeden surec disi birakmak,
               geri donusu zor bir kaza demekti. */
            const yeni = new Set(FT.haric);
            if (tik.checked) gorunen.forEach(s => yeni.add(s.feature));
            else gorunen.forEach(s => yeni.delete(s.feature));
            ftHaricYaz(yeni);
        };
        kap.appendChild(tik);
        bas.appendChild(kap);
    }

    FT_ALANLAR.forEach((a, i) => {
        const etiket = ((FT.veri && FT.veri.kolonlar) || [])[i] || a.baslik;
        const h = elYap("span", "ft-hucre ft-bas " + (a.sinif || ""));
        h.setAttribute("role", "columnheader");
        h.setAttribute("data-alan", a.alan);
        h.tabIndex = 0;
        const ok = FT.sira === a.alan ? (FT.yon === 1 ? " ▲" : " ▼") : "";
        h.textContent = etiket + ok;
        h.title = etiket + " sütununa göre sırala";
        const sirala = () => {
            if (FT.sira === a.alan) FT.yon = -FT.yon;
            else { FT.sira = a.alan; FT.yon = 1; }
            ftBasaSar();
            ftTazele();
        };
        h.onclick = sirala;
        h.onkeydown = ev => {
            if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); sirala(); }
        };
        bas.appendChild(h);
    });
    return bas;
}

/* SOZLUK TANIMI hucresi duzenlenebilir (SOZLESME7 §5). Yazilan yer
   sozlugun CALISMA KOPYASI; orijinal sozluk degismez.
   Taslak: tablo sanallastirilmis ve her tazelemede yeniden ciziliyor;
   henuz gonderilmemis metin FT.taslak'ta duruyor, yoksa arada gelen bir
   backend yaniti kullanicinin yazdigini siliyordu. */
function ftTanimHucresi(s) {
    const h = elYap("span", "ft-hucre ft-tanim");
    h.setAttribute("role", "cell");
    h.setAttribute("data-alan", "tanim");

    const deger = FT.taslak.has(s.feature)
        ? FT.taslak.get(s.feature)
        : (s.tanim === null || s.tanim === undefined ? "" : String(s.tanim));

    if (!(FT.veri && FT.veri.duzenlenebilir)) {
        h.textContent = degerGoster(s.tanim);
        /* SEBEBI ARKA UC YAZIYOR: "çalışma kopyası yok" tek başına
           kullanıcıya ne yapacağını söylemiyordu (kullanıcı bildirimi).
           Sözlük hiç bağlanmadıysa hangi adımda bağlanacağı, kopya
           çıkarılamadıysa nedeni yazıyor. */
        h.title = tireSade((FT.veri && FT.veri.duzenleme_notu)
                           || "Tanımlar salt okunur.");
        return h;
    }

    /* TEXTAREA: tanım tamamı okunabilsin diye satır kaydırarak uzar
       (kullanıcı kararı: "tamamen okunabilir düzeyde olmalı"). */
    const giris = document.createElement("textarea");
    giris.rows = 1;
    giris.className = "ft-tanim-giris";
    giris.value = deger;
    giris.placeholder = "Tanım yok";
    giris.setAttribute("data-ft-odak", "tanim:" + s.feature);
    giris.setAttribute("aria-label", s.feature + " sözlük tanımı");
    giris.title = deger;
    giris.onclick = ev => ev.stopPropagation();      // detay acilmasin
    giris.oninput = () => { FT.taslak.set(s.feature, giris.value); ftKutuBoyu(giris); };
    /* Yazma YALNIZ onaylaninca (blur / Enter) gider: her tus vurusunda
       uca istek atmak 1.042 satirlik tabloda kabul edilemez. */
    giris.onchange = () => ftTanimYaz(s, giris.value);
    giris.onkeydown = ev => {
        if (ev.key === "Enter") { ev.preventDefault(); ftTanimYaz(s, giris.value); }
        else if (ev.key === "Escape") { FT.taslak.delete(s.feature); ftTazele(); }
    };
    if (FT.bekleyen.has(s.feature)) { giris.disabled = true; h.classList.add("bekliyor"); }
    h.appendChild(giris);
    return h;
}

function ftSatirCiz(s, i) {
    const hata = FT.hatalar.get(s.feature);
    const satir = elYap("div", "ft-satir"
        + (FT.detay === s.feature ? " acik" : "")
        + (hata ? " hatali" : ""));
    satir.setAttribute("role", "row");
    void i;

    /* ISARETLI = SUREC DISI (SOZLESME7 §5). Satirin soluk gorunmesi de
       bu kutudan geliyor; ayri bir DURUM kolonu yok. */
    const disiMi = FT.haric.has(s.feature);
    if (disiMi) satir.classList.add("ft-disi");

    if (FT.veri && FT.veri.duzenlenebilir) {
        const kap = elYap("span", "ft-hucre ft-sec");
        const tik = document.createElement("input");
        tik.type = "checkbox";
        tik.checked = disiMi;
        tik.disabled = FT.haricBekleyen;
        tik.setAttribute("aria-label", s.feature + " süreç dışına alınsın");
        tik.title = "Süreç dışına al";
        tik.onclick = ev => ev.stopPropagation();   // secim detayi acmasin
        tik.onchange = () => {
            const yeni = new Set(FT.haric);
            if (tik.checked) yeni.add(s.feature);
            else yeni.delete(s.feature);
            ftHaricYaz(yeni);
        };
        kap.appendChild(tik);
        satir.appendChild(kap);
    }

    FT_ALANLAR.forEach(a => {
        if (a.alan === "tanim") { satir.appendChild(ftTanimHucresi(s)); return; }
        let metin;
        if (a.alan === "null_oran") metin = ftOran(s.null_oran);
        else metin = degerGoster(s[a.alan]);
        const h = elYap("span", "ft-hucre " + (a.sinif || "")
                        + (a.sayisal ? " ft-sayi" : ""), metin);
        h.setAttribute("role", "cell");
        h.setAttribute("data-alan", a.alan);
        h.title = tireSade(s[a.alan] === null || s[a.alan] === undefined
                           ? "" : String(s[a.alan]));
        satir.appendChild(h);
    });

    if (hata) {
        /* Hata SATIRIN uzerinde duruyor: toast kullanilmiyor, cunku
           kullanici hangi kolonun yazilamadigini bilmeden 1.042 satirin
           icinde onu bulamiyor. */
        const uyari = elYap("span", "ft-hata", "⚠ " + hata);
        uyari.title = hata;
        satir.appendChild(uyari);
    }

    satir.onclick = () => {
        FT.detay = FT.detay === s.feature ? null : s.feature;
        ftTazele();
    };
    return satir;
}

/* SATIRLAR DEĞİŞKEN YÜKSEKLİKTE (kullanıcı kararı: sözlük tanımı tamamen
   okunabilmeli, kırpılmamalı). Sabit yükseklikli sanal pencere yerine
   PARÇA PARÇA çizim: ilk FT_PARCA satır çizilir, kaydırma sona
   yaklaştıkça bir parça daha eklenir. 1.042 satırın hepsi bir anda DOM'a
   basılmıyor; uzun tanım alt satıra kayıyor. */
const FT_PARCA = 120;

function ftKutuBoyu(el) {
    el.style.height = "auto";
    el.style.height = el.scrollHeight + 2 + "px";
}

function ftSatirEkle(adet) {
    const n = FT.suzulmus.length;
    const bas = FT.gosterilen || 0;
    const son = Math.min(n, bas + adet);
    if (son <= bas) return;
    // Tek parcada baglaniyor: satir satir appendChild her seferinde
    // yerlesimi yeniden hesaplatiyordu.
    const parca = document.createDocumentFragment();
    for (let i = bas; i < son; i++)
        parca.appendChild(ftSatirCiz(FT.suzulmus[i], i));
    FT.dom.yer.appendChild(parca);
    FT.gosterilen = son;
    FT.dom.yer.querySelectorAll("textarea.ft-tanim-giris:not([data-boy])").forEach(t => {
        t.setAttribute("data-boy", "1");
        ftKutuBoyu(t);
    });
}

function ftPencereCiz() {
    const kap = FT.dom.govde;
    const n = FT.suzulmus.length;
    /* Yeniden çizimde kaydırma yeri korunur: içerik boşalınca tarayıcı
       konumu sıfırlıyor. */
    const hedef = kap.scrollTop || FT.kaydirma || 0;
    FT.dom.yer.style.height = "";
    FT.dom.yer.innerHTML = "";

    if (!n) {
        FT.gosterilen = 0;
        FT.dom.yer.appendChild(elYap("div", "ft-bos",
            (FT.veri && (FT.veri.satirlar || []).length)
                ? "Filtrelerle eşleşen kolon yok."
                : "Kolon listesi «Veri Profili ve Kalite» adımından sonra dolar."));
        return;
    }

    const istenen = Math.max(FT.gosterilen || 0, FT_PARCA);
    FT.gosterilen = 0;
    ftSatirEkle(istenen);
    const yukseklik = kap.clientHeight || FT_VARSAYILAN_YUKSEKLIK;
    while (FT.gosterilen < n && kap.scrollHeight < hedef + yukseklik * 2)
        ftSatirEkle(FT_PARCA);
    kap.scrollTop = hedef;
}

/* Her kaydirma olayinda DOM'u yeniden kurmak gereksiz: tampon zaten
   pencerenin altinda ve ustunde satir tutuyor. Cizili aralik gorunen
   araligi hala kapsiyorsa hicbir sey yapilmiyor; boylece bir kaydirma
   icinde ~13 olaydan yalnizca biri cizim yapiyor. */
function ftKaydirmaIsle() {
    const kap = FT.dom.govde;
    if ((FT.gosterilen || 0) >= FT.suzulmus.length) return;
    const yukseklik = kap.clientHeight || FT_VARSAYILAN_YUKSEKLIK;
    if (kap.scrollTop + yukseklik > kap.scrollHeight - yukseklik)
        ftSatirEkle(FT_PARCA);
}

function ftDetayCiz() {
    const kutu = FT.dom.detay;
    kutu.innerHTML = "";
    const s = FT.detay ? ftSatirBul(FT.detay) : null;
    if (!s) { kutu.hidden = true; return; }
    kutu.hidden = false;

    kutu.appendChild(elYap("div", "ft-detay-ad", s.feature));
    /* Satir govdesi sadelesti (SOZLESME7 §5): tekil/ornek gelmeyebilir.
       GELMEYEN ALAN HIC CIZILMEZ - bos "∅" kullaniciya "olculdu ve
       bostu" diye okunuyor. */
    const satirlar = [
        ["Sözlük Tanımı", degerGoster(s.tanim)],
        ["Tip", degerGoster(s.tip)],
        ["Null Oranı", ftOran(s.null_oran)],
        [FT.haric.has(s.feature) ? "Süreç dışı" : "Süreçte",
         FT.haric.has(s.feature) ? "evet" : "hayır"]
    ];
    if (s.tekil !== null && s.tekil !== undefined)
        satirlar.push(["Tekil Değer", ftBinlik(s.tekil)]);
    if (s.ornek !== null && s.ornek !== undefined && s.ornek !== "")
        satirlar.push(["Örnek Değer", degerGoster(s.ornek)]);
    // IV / C yalnizca SFA calistiysa var; yoksa satir HIC cizilmiyor -
    // bos "∅" kullaniciya "hesaplandi ama sifir" diye okunuyordu.
    if (s.iv !== null && s.iv !== undefined) satirlar.push(["IV", ftOndalik(s.iv)]);
    if (s.c !== null && s.c !== undefined) satirlar.push(["C-value", ftOndalik(s.c)]);

    satirlar.forEach(ikili => {
        const sat = elYap("div", "ft-detay-satir");
        sat.appendChild(elYap("span", "ft-detay-etiket", ikili[0]));
        sat.appendChild(elYap("span", "ft-detay-deger", ikili[1]));
        kutu.appendChild(sat);
    });

    const kapat = document.createElement("button");
    kapat.type = "button";
    kapat.className = "ft-mini";
    kapat.textContent = "Kapat";
    kapat.onclick = () => { FT.detay = null; ftTazele(); };
    kutu.appendChild(kapat);
}

/* Filtre/siralama/secim degisince yalnizca degisen parcalar yeniden
   ciziliyor: arama kutusu DOM'da kaliyor, imlec kaybolmuyor. */
function ftTazele() {
    if (!FT.dom || !FT.dom.kok.isConnected) return;
    /* Tanim hucreleri <input>: satirlar her tazelemede yeniden
       ciziliyor, odak ve imlec yeri ayni kutuya geri veriliyor. */
    const odak = ftOdakAnahtari();
    ftSuz();
    FT.dom.sayac.textContent = ftSayacMetni();
    FT.dom.kaynak.textContent = ftKaynakMetni();
    FT.dom.kaynak.title = FT.dom.kaynak.textContent;

    const eskiBaslik = FT.dom.baslik;
    FT.dom.baslik = ftBaslikCiz();
    eskiBaslik.replaceWith(FT.dom.baslik);

    if (FT.dom.toplu) {
        const yeni = ftTopluCiz();
        FT.dom.toplu.replaceWith(yeni);
        FT.dom.toplu = yeni;
    }
    FT.dom.not.textContent = FT.topluNot;
    FT.dom.not.hidden = !FT.topluNot;
    FT.dom.hata.textContent = FT.topluHata;
    FT.dom.hata.hidden = !FT.topluHata;

    FT.pencere = null;
    ftPencereCiz();
    ftDetayCiz();
    ftOdakGeriVer(odak);
}

/* Baslik seridinin son parcasi: sozlugun CALISMA KOPYASI oldugu
   etiketin kendisinde yaziyor (arka uc oyle gonderiyor). "Sözlük: "
   oneki kaldirildi - serit tek satir, her kelime yer tutuyor. */
function ftKaynakMetni() {
    const k = FT.veri && FT.veri.sozluk_kaynak;
    return k ? tireSade(k) : "Sözlük seçilmedi";
}

/* Salt okunur kopya ONBELLEKLENIR: featureTabloCiz gelen govdeyi
   KIMLIGIYLE karsilastirip (FT.veri !== t) filtreleri sifirliyor. Her
   cizimde yeni bir nesne uretseydik kullanicinin yazdigi arama her
   panel tazelemesinde silinirdi. */
const ftSalt = { kaynak: null, veri: null };
function ftSaltOku(t) {
    if (ftSalt.kaynak !== t) {
        ftSalt.kaynak = t;
        ftSalt.veri = Object.assign({}, t, { duzenlenebilir: false });
    }
    return ftSalt.veri;
}

function featureTabloCiz(t) {
    /* Bu cizim YENI backend verisiyle mi, yoksa sekmeye geri donuldugu
       icin mi? Ayni govde tekrar ciziliyorsa yazma hatalari SILINMEZ:
       kullanici baska sekmedeyken donen hatayi hic gormeden kaybediyordu.
       Yeni govde geldiyse hatalar gecersiz - panel zaten sunucudaki son
       hali gosteriyor. */
    if (FT.veri !== t) {
        FT.hatalar.clear();
        FT.bekleyen.clear();
        FT.taslak.clear();
        /* Zaten surec disi olan kolon ISARETLI gelir; kaynak satirin
           kendi durum alani (SOZLESME7 §5). */
        if (!FT.haricBekleyen) ftHaricKur(t);
    }
    FT.veri = t;

    /* KAYNAKTA hic kolon yoksa (yeni calisma, veri seti henuz secilmedi)
       tablo HIC cizilmez. Arama kutusu, kategori/durum filtreleri ve
       esik alani bos bir tablonun ustunde duruyordu; kullanicinin ilk
       gordugu ekran, hicbir seyi olmayan bir filtre takimiydi.
       DIKKAT: bu kontrol SUZME ONCESI satir sayisina bakar — kullanici
       filtreyle 0 satira dusurduyse takim kalmali, yoksa filtreyi geri
       alamaz. */
    if (!(t.satirlar || []).length) {
        FT.dom = null;
        FT.pencere = null;
        return;
    }
    if (!t.duzenlenebilir) { FT.topluHata = ""; FT.topluNot = ""; }

    /* SUZME CIZIMDEN ONCE. Eskiden ftSuz() cizimin SONUNDA cagriliyordu;
       ftTopluCiz() ise ortasinda, yani FT.suzulmus HENUZ DOLMADAN
       okunuyordu. Ilk boyamada toplu satir "0 / 0 değişken süreç dışı"
       yaziyordu — 1.002 kolon süreç dışıyken. Sonraki ftTazele()'lerde
       duzeliyordu, bu yuzden testlerde gorunmedi; kullanicinin gordugu
       ILK ekran yanlisti. */
    ftSuz();

    const kok = elYap("div", "iskele-kart ft-kart");

    /* TEK SATIR serit: "1.042 degisken \u00b7 2 surec disi \u00b7 <sozluk>"
       Kaynak etiketi hep gorunur: hangi sozlugun anlatildigi belli olsun.
       "(calisma kopyasi)" eki KALDIRILDI (kullanici karari) - kopya bir
       uygulama detayi; sozlugun nereden geldigini kartlardaki "Köken"
       satiri anlatiyor. */
    const ust = elYap("div", "ft-ust");
    const sayac = elYap("span", "ft-sayac");
    const kaynak = elYap("span", "ft-kaynak");
    ust.appendChild(sayac);
    ust.appendChild(elYap("span", "ft-ayrac", "\u00b7"));
    ust.appendChild(kaynak);
    kok.appendChild(ust);

    /* EXCEL İNDİRME - sohbetteki kart KAYDEDİLDİKTEN sonra açılır.
       excel_hazir bayrağını arka uç gönderiyor (durum["teyit"] var mı);
       böylece F5'ten sonra da, başka sekmeden dönünce de doğru durumda
       çiziliyor - tarayıcıda tutulan bir bayrak bunu yapamazdı. */
    const ftExcel = excelSeridiYap(
        "sozluk", "Excel İndir",
        /* ADIM ADI YAZILMIYOR: adım başlıkları adım kayıt defterinden
           (akis_kayit.ADIMLAR) geliyor. Burada sabitlenseydi, adım
           yeniden adlandırıldığında bu ipucu sessizce yanlış bir yere
           yönlendirirdi. */
        "Sohbetteki listeyi kaydettikten sonra indirebilirsiniz.");
    ftExcel.ac(!!t.excel_hazir);
    /* ÜST ŞERİDİN YANINDA (kullanıcı kararı): "excel olarak indir kısmı
       da üstteki yazının yanında yer almalı". Kendi satırında dururken
       sayaçla arasında boş bir şerit kalıyordu. */
    ust.appendChild(ftExcel.el);

    kok.appendChild(ftFiltreCiz());

    let toplu = null;
    if (t.duzenlenebilir) { toplu = ftTopluCiz(); kok.appendChild(toplu); }

    const not = elYap("div", "ft-not");
    const hata = elYap("div", "ft-toplu-hata");
    hata.setAttribute("role", "alert");
    kok.appendChild(not);
    kok.appendChild(hata);

    const tablo = elYap("div", "ft-tablo" + (t.duzenlenebilir ? "" : " salt-okunur"));
    tablo.setAttribute("role", "table");
    const baslik = ftBaslikCiz();
    tablo.appendChild(baslik);

    const govde = elYap("div", "ft-govde");
    const yer = elYap("div", "ft-yer");
    govde.appendChild(yer);
    govde.onscroll = () => {
        FT.kaydirma = govde.scrollTop;
        ftKaydirmaIsle();
    };
    tablo.appendChild(govde);
    kok.appendChild(tablo);

    const detay = elYap("div", "ft-detay");
    detay.hidden = true;
    kok.appendChild(detay);

    FT.dom = { kok, sayac, kaynak, baslik, toplu, not, hata, govde, yer, detay };
    analizGovde.appendChild(kok);

    sayac.textContent = ftSayacMetni();
    kaynak.textContent = ftKaynakMetni();
    kaynak.title = kaynak.textContent;
    not.textContent = FT.topluNot; not.hidden = !FT.topluNot;
    hata.textContent = FT.topluHata; hata.hidden = !FT.topluHata;
    govde.scrollTop = FT.kaydirma;      // yanit sonrasi ayni yerde kal
    FT.pencere = null;
    ftPencereCiz();
    ftDetayCiz();
}


/* ==================== Bölme formu ==================== */
/* HAZIRLIK sekmesindeki bolme formu; kaynak: akis_panel.bolme_formu.

   Bolme IKI ASAMA ve EN FAZLA UC SET (egitim / val / test):

     1) test nasil ayrilsin?  -> test_tanim
          "zamansal": son N donem test olur. Bu set ZATEN OOT'dur; ayri
                      bir OOT seti YOKTUR (eski oot_var ekseni kaldirildi).
          "rastgele": test_oran kadar rastgele ayrilir.
     2) kalan train nasil kullanilsin? -> train_kullanimi
          full / val / full_cv / val_cv — arka ucun TEK alani. Eksen
          carpimini ON YUZ HESAPLAMIYOR; val_var ve cv ince ayar olarak
          ayrica duruyor ve elle degistirilirse secim "ozel"e duser. */

/* val_var x cv <-> train_kullanimi. Arka uctaki TRAIN_KULLANIMI ile ayni;
   burada YALNIZCA ince ayar alanlarini aninda dogru gostermek ve secimin
   "ozel"e dustugunu gormek icin duruyor — kaydi yine arka uc cozer. */
const BF_TRAIN_KULLANIMI = {
    full:    { val_var: false, cv: "yok" },
    val:     { val_var: true,  cv: "yok" },
    full_cv: { val_var: false, cv: "kfold" },
    val_cv:  { val_var: true,  cv: "kfold" }
};
const BF_TRAIN_BASLIK = {
    full: "Sadece eğitim", val: "Eğitim + doğrulama",
    full_cv: "Sadece eğitim + çapraz doğrulama",
    val_cv: "Eğitim + doğrulama + çapraz doğrulama"
};

/* Enum degerlerinin ekran adlari. YEDEK listedir: etiketler artik arka
   uctan geliyor (akis_durum.BOLME_SECENEK), cunku ayni terimin iki
   yerde yazilmasi ikisinin ayrisması demekti. Eski bir gövdede
   "secenekler" duz dizi olarak gelirse bu liste devreye giriyor.
   YABANCI TERIM YOK: ekranda kullaniciya gosterilen her sey Turkce
   (kullanici karari). */
const BF_ETIKET = {
    rastgele: "Rastgele", zamansal: "Zamansal",
    satir: "Satır", kimlik: "Kimlik",
    yok: "Yok", kfold: "Parçalı", zaman: "Zaman sıralı",
    son_donem: "Son dönem", secili: "Belirli dönem",
    full: "Sadece eğitim", val: "Eğitim + doğrulama",
    full_cv: "Sadece eğitim + çapraz doğrulama",
    val_cv: "Eğitim + doğrulama + çapraz doğrulama",
    ozel: "Özel"
};

/* Ayni uyariyi arka uc da uretiyor (akis_durum.GECERSIZ_BIRLESIM); burada
   kisasi duruyor cunku kullanici bu birlesimi KAYDETMEDEN once gormeli. */
const BF_GECERSIZ_BIRLESIM =
    "Çapraz doğrulama kapalı ve ayrı bir Test (OOS) seti yok: model ayarlarını "
    + "deneyecek temiz bir yer kalmıyor. Algoritma seçimi sabit "
    + "ayarlarla yapılır (arama yapılmaz) ve bu rapora yazılır.";

/* Bir alanin ekran adi ve tek cumlelik aciklamasi: ONCE arka uctan
   (akis_panel.bolme_formu her alana "etiket" ve "aciklama" koyuyor),
   yoksa yedek listeden. Aciklama, terimin Turkcesini bilmeyen
   kullanici icin var (kullanici karari: "türkçesini bilmeyebilir
   bazıları"). */
const BF_ALAN_YEDEK = {
    test_tanim: "Bölme Türü", oot_adet: "Test Dönem Sayısı",
    test_oran: "Test Oranı",
    train_kullanimi: "Kalan Eğitim Verisinin Kullanımı",
    birim: "Bölme Birimi", val_var: "Doğrulama Seti Kullan",
    val_oran: "Doğrulama Oranı", cv: "Çapraz Doğrulama Yöntemi",
    kat: "Parça Sayısı", katmanla: "Hedefe Göre Katmanla",
    segment_katmanla: "Segment Dağılımı",
    oot_tanim: "Test Dönemi Seçimi", oot_deger: "Test Dönemi",
    seed: "Rastgelelik Tohumu"
};

function bfEtiketi(ad, al) {
    const k = al && al[ad];
    return (k && k.etiket) || BF_ALAN_YEDEK[ad] || ad;
}

function bfAciklamasi(ad, al) {
    const k = al && al[ad];
    return (k && k.aciklama) || "";
}

/* Arka uctan gelen secenek listesini tek bicime cevirir:
   [{anahtar, etiket, aciklama, kilitli}]. Eski govdede duz dizi
   ("rastgele") gelebilir; o da ayni bicime yukseltiliyor. */
function bfSecenekler(alan, ham, yedek) {
    const liste = (ham && ham.length) ? ham : (yedek || []);
    return liste.map(o => (typeof o === "string")
        ? { anahtar: o, etiket: BF_ETIKET[o] || o, aciklama: "", kilitli: false }
        : { anahtar: o.anahtar, etiket: o.etiket || BF_ETIKET[o.anahtar] || o.anahtar,
            aciklama: o.aciklama || "", kilitli: !!o.kilitli });
}

const BF_KILIT_UYARISI =
    "Kaydettiğinizde bu bölmeye dayanan analizler GEÇERSİZ olur: eski "
    + "sonuçlar yeni setleri tarif etmez ve ilgili adımların yeniden "
    + "çalıştırılması gerekir.";

const BF = {
    veri: null,        // backend'in son gonderdigi bolme_formu (kimlik karsilastirmasi)
    alan: null,        // duzenlenen taslak
    acikEksen: false,  // val_var/cv ELLE degistirildi mi (govdeye ayrica gider)
    ozet: null,        // kaydetmeden donen ozet; null ise formdaki ozet gecerli
    uyarilar: null,    // kaydetmeden donen uyarilar; null ise formdaki liste
    hata: "", not: "",
    kaydediyor: false,
    zorlaOnay: false,  // "yine de degistir" birinci adim
    kilitAcik: false   // kullanici kilidi acikca zorladi
};

function bfSayi(x, yedek) {
    const s = Number(String(x === null || x === undefined ? "" : x).replace(",", "."));
    return isFinite(s) ? s : yedek;
}

function bfTam(x, yedek) {
    const s = Math.round(bfSayi(x, NaN));
    return isFinite(s) ? s : yedek;
}

/* (val_var, cv) -> kullanicinin gordugu tek etiket; hicbirine oturmuyorsa
   "ozel" (cv="zaman" boyle). Arka uctaki _train_kullanimi ile ayni kural. */
function bfTrainKullanimi(valVar, cv) {
    const adlar = Object.keys(BF_TRAIN_KULLANIMI);
    for (let i = 0; i < adlar.length; i++) {
        const e = BF_TRAIN_KULLANIMI[adlar[i]];
        if (e.val_var === bfValVar(valVar) && e.cv === cv) return adlar[i];
    }
    return "ozel";
}

/* Backend formundan duzenlenebilir taslak. oot_tanim ic ice geliyor;
   taslakta duzlestiriliyor ki her alan tek bir kontrole bagli kalsin.
   oot_adet TEK yerde tutuluyor: oot_tanim.adet govdeye ondan yazilir,
   yoksa 1. asamadaki kutu ile ince ayar birbirinden kayar. */
/* Backend formundan duzenlenebilir taslak.

   SECIM ALANLARI ANAHTAR TASIR: oot_adet "son:2", test_oran "0.20",
   kat "5" gibi. Arka uc bunlari cozuyor (bkz. akis_durum.bolme_kaydet);
   on yuz yorumlamiyor, oldugu gibi geri gonderiyor. Boylece "hangi
   donemler test olacak" kurali TEK YERDE, arka ucta duruyor. */
/* val_var ve katmanla artik ANAHTAR tasiyor ("kullan"/"kullanma",
   "koru"/"koruma"). Dikkat: "kullanma" JS'te DOGRU bir deger - dogrudan
   !!a.val_var yazmak "Kullanma" secildiginde de aciktir demek olurdu.
   Bu yuzden her okuma bu ikisinden geciyor. */
function bfValVar(v) { return v === true || v === "kullan"; }
function bfKatmanla(v) { return v === true || v === "koru"; }

function bfAlanlar(f) {
    const al = (f && f.alanlar) || {};
    const d = (k, y) => (al[k] && al[k].deger !== undefined && al[k].deger !== null)
        ? al[k].deger : y;
    /* val_var artik "kullan"/"kullanma" anahtari; eski govdede bool
       gelebilir. Taslakta TEK BICIM: anahtar. */
    const valHam = d("val_var", "kullanma");
    const valVar = (valHam === true || valHam === "kullan");
    const cv = d("cv", "kfold");
    /* ORAN TASLAKTA HEP KESİR. Arka uç yüzde gönderiyor (20), ekran
       yüzde gösteriyor, ama taslakta ve gövdede tek biçim olmalı:
       yoksa "değişti mi" karşılaştırması 20 ile 0.2'yi kıyaslayıp her
       çizimde "değişti" diyordu. */
    const oran = (k, yedek) => {
        let v = Number(d(k, yedek));
        if (!isFinite(v) || v <= 0) return yedek;
        return v > 1 ? v / 100 : v;
    };
    return {
        test_tanim: d("test_tanim", "rastgele"),
        oot_adet: d("oot_adet", "son:1"),
        test_oran: oran("test_oran", 0.20),
        train_kullanimi: d("train_kullanimi",
                           bfTrainKullanimi(valVar, cv)),
        birim: d("birim", "satir"),
        val_var: valVar ? "kullan" : "kullanma",
        val_oran: oran("val_oran", 0.20),
        cv: cv,
        kat: d("kat", 5),
        katmanla: d("katmanla", "koru"),
        segment_katmanla: d("segment_katmanla", "koru"),
        seed_tur: d("seed_tur", "sabit"),
        tekrar: d("tekrar", 1),
        gap: d("gap", 0),
        seed: d("seed", 42),
        /* Çoklu tekrarın seed listesi: virgüllü metin ("42, 43, 44"). */
        seedler: String(d("seedler", "") || "")
    };
}

/* /bolme_kaydet govdesindeki "bolme" nesnesi. Ayni bicim karsilastirma
   icin de kullaniliyor: taslak sunucudaki degerlerden farkli mi? */
function bfGovdeDen(a) {
    /* Secim anahtarlari OLDUGU GIBI gidiyor; oot_tanim'i on yuz
       KURMUYOR (eskiden kuruyordu ve "son N dönem" kurali iki yerde
       yazili oluyordu). */
    return {
        test_tanim: a.test_tanim,
        oot_adet: String(a.oot_adet),
        test_oran: String(bfSayi(a.test_oran, 0.20)),
        train_kullanimi: a.train_kullanimi,
        birim: a.birim, katmanla: bfKatmanla(a.katmanla),
        segment_katmanla: bfKatmanla(a.segment_katmanla),
        val_var: bfValVar(a.val_var),
        val_oran: String(bfSayi(a.val_oran, 0.20)),
        cv: a.cv, kat: String(bfTam(a.kat, 5)),
        seed: bfTam(a.seed, 42),
        seed_tur: a.seed_tur, tekrar: String(bfTam(a.tekrar, 1)),
        seedler: bfSeedListesi(a.seedler).join(",")
    };
}

/* Kaydedilecek govde. train_kullanimi HER ZAMAN gider; val_var/cv
   YALNIZCA elle degistirildiyse (ya da hicbir hazir secenege oturmuyorsa)
   eklenir — arka uc acik geleni kazandiriyor, ikisini hep gondermek hazir
   secenegi anlamsizlastirirdi (bkz. akis_durum.bolme_kaydet). */
function bfKayitGovdesi() {
    const g = bfGovdeDen(BF.alan);
    if (!BF.acikEksen && g.train_kullanimi !== "ozel") {
        delete g.val_var;
        delete g.cv;
    }
    return g;
}

function bfDegisti() {
    if (!BF.veri || !BF.alan) return false;
    return JSON.stringify(bfGovdeDen(BF.alan))
        !== JSON.stringify(bfGovdeDen(bfAlanlar(BF.veri)));
}

/* Alanlar pasif mi: kilitli form ya da ucusta bir kayit. */
function bfPasif() {
    if (BF.kaydediyor) return true;
    return !!(BF.veri && BF.veri.kilitli && !BF.kilitAcik);
}

function bfZamansalMi() { return BF.alan.test_tanim === "zamansal"; }

/* Zamansal testte test orani yok: test son N donemdir. */
function bfPaylar() {
    const a = BF.alan;
    const test = bfZamansalMi() ? 0 : bfSayi(a.test_oran, 0.20);
    const val = bfValVar(a.val_var) ? bfSayi(a.val_oran, 0.20) : 0;
    return { train: Math.max(1 - test - val, 0), val: val, test: test };
}

/* Kaydetmeden gorunen ozet: SATIR SAYISI DEGIL, oranlar. Arka ucun
   _bolme_oran_ozeti() bicimiyle ayni okunsun diye tam yuzde yaziliyor;
   satir sayisini on yuz bilmiyor, tahmin uretmek olmayan bir kesinlik
   satardi. */
function bfYuzde(oran) {
    return "%" + Math.round(100 * oran);
}

/* Secili test donemi secenegin ETIKETINDEN okunur: "son:2" ham anahtar,
   kullaniciya gosterilecek metin arka uctaki listede yaziyor. */
function bfDonemEtiketi() {
    const k = (BF.veri && BF.veri.alanlar && BF.veri.alanlar.oot_adet) || {};
    const bulunan = bfSecenekler("oot_adet", k.secenekler, [])
        .find(o => o.anahtar === String(BF.alan.oot_adet));
    return bulunan ? bulunan.etiket : "son dönem";
}

function bfYerelOzet() {
    /* HAZIR BOLME: oran diye bir sey yok, setler tabloda yazili.
       Tahmini yuzde yazmak olmayan bir hesabi varmis gibi gostermekti. */
    if (BF.alan.test_tanim === "hazir")
        return "Setler veri setindeki bölme kolonundan okunacak.";
    const p = bfPaylar();

    /* ZAMANSAL BOLMEDE EGITIM YUZDESI YAZILMAZ. Test donem bazli
       ayrildigi icin orani onceden bilinmiyor; 1 - test - dogrulama
       hesabi test payini 0 sayip "eğitim %100" yaziyordu - acikca
       yanlis bir sayi (kendi ekran kontrolumde yakalandi). */
    if (bfZamansalMi()) {
        const parcalar = ["Validasyon (OOT): " + bfDonemEtiketi()];
        if (p.val) parcalar.push("Test (OOS): eğitimin " + bfYuzde(p.val) + "'i");
        parcalar.unshift("Train (MS): kalan dönemler");
        return parcalar.join(" · ");
    }

    const parcalar = ["Train (MS) " + (p.train ? bfYuzde(p.train) : "-"),
                      "Test (OOS) " + (p.val ? bfYuzde(p.val) : "-"),
                      TEST_OOS2 + " " + (p.test ? bfYuzde(p.test) : "-")];
    return parcalar.join(" · ");
}

/* Arka ucun bolme_uyarilari() ile AYNI metinler: yalnizca ayardan dogan,
   veri okumadan hesaplanabilen uyarilar taslakta da gosteriliyor ki
   kullanici bunlari kaydetmeden once gorsun. Kaydetten sonra ayni
   uyari iki kez gorunmesin diye kaba bir eslestirmeyle ayikliniyor. */
function bfUyariListesi() {
    const kaynak = (BF.uyarilar !== null && BF.uyarilar !== undefined)
        ? BF.uyarilar : ((BF.veri && BF.veri.uyarilar) || []);
    const liste = kaynak.slice();
    const varMi = (re) => liste.some(u => re.test(String(u)));
    const a = BF.alan;

    /* HAZIR BOLME: oranlardan dogan uyarilarin hicbiri gecerli degil,
       setler tabloda yazili. Arka ucun uyarilari (kucuk set vb.)
       duruyor. */
    if (a.test_tanim === "hazir") return liste;

    const p = bfPaylar();
    if (!p.val && a.cv === "yok" && !varMi(/çapraz doğrulama kapalı/))
        liste.push(BF_GECERSIZ_BIRLESIM);

    const testO = p.test, valO = p.val;
    if (testO + valO >= 1 && !varMi(/eğitime satır kalmaz/))
        liste.push(TEST_OOS2 + " (" + bfYuzde(testO) + ") ve Test (OOS) ("
                   + bfYuzde(valO) + ") paylarının toplamı tüm veriyi "
                   + "kaplıyor; eğitime satır kalmaz.");
    else if (testO + valO > 0.6 && !varMi(/ölçüm güvenilir olmayabilir/))
        liste.push("Train (MS) setine verinin yalnızca "
                   + bfYuzde(1 - testO - valO) + "'i kalıyor; ölçüm "
                   + "güvenilir olmayabilir.");
    return liste;
}


/* Sayi alanlari oninput DEGIL onchange dinliyor: yarim yazilmis bir sayi
   ("0,") her tusta ozeti ve uyarilari oynatiyordu. */
function bfSayiKutusu(ad, deger, ek, pasif, degisti) {
    const i = document.createElement("input");
    i.type = "number";
    i.className = "ft-esik-kutu bf-sayi";
    i.setAttribute("data-alan", ad);
    i.setAttribute("data-ft-odak", "bf-" + ad);
    Object.keys(ek || {}).forEach(k => { i[k] = ek[k]; });
    i.value = deger;
    i.disabled = pasif;
    if (!pasif) i.onchange = () => degisti(i.value);
    return i;
}

function bfSecimKutusu(ad, secenekler, deger, pasif, degisti) {
    /* Kilitli secenek listede DURUR ama secilemez: yok etmek "bu seçenek
       hiç yokmuş" demekti, sebebi yazili pasif bir satir ise "neden
       seçemiyorum" sorusunu ekranda cevapliyor. */
    const s = ftSecim("bf-" + ad,
                      secenekler.map(o => ({ deger: o.anahtar, etiket: o.etiket })),
                      deger, degisti);
    s.setAttribute("data-alan", ad);
    Array.prototype.forEach.call(s.options, (op, i) => {
        const o = secenekler[i];
        if (!o) return;
        if (o.kilitli) op.disabled = true;
        if (o.aciklama) op.title = tireSade(o.aciklama);
    });
    s.disabled = pasif;
    if (pasif) s.onchange = null;
    return s;
}

/* Bir form alani: etiket + kontrol + (varsa) aciklama + (varsa) not.

   ACIKLAMA SATIRI KULLANICI KARARI: "türkçesini bilmeyebilir bazıları
   ona da dikkat edelim". Terimin Turkcesi etikette, ne demek oldugu
   hemen altinda tek cumlede yaziyor; gerektiginde cumle sektorde
   yaygin karsiligi da soyluyor. */

/* "42, 43, 44" -> [42, 43, 44]; geçersizler atlanır, tekrarlar tekil. */
function bfSeedListesi(metin) {
    const cikti = [];
    String(metin || "").split(/[,;\s]+/).forEach(x => {
        const v = Math.round(Number(x));
        if (x !== "" && isFinite(v) && cikti.indexOf(v) < 0) cikti.push(v);
    });
    return cikti;
}

/* Ana seed ve tekrar sayısından türeyen liste: 42, 3 -> "42, 43, 44". */
function bfTuretilenSeedler(seed, tekrar) {
    const s0 = bfTam(seed, 42), n = Math.max(bfTam(tekrar, 1), 1);
    const liste = [];
    for (let i = 0; i < n; i++) liste.push(s0 + i);
    return liste.join(", ");
}

function bfDegistir(ad, deger) {
    BF.alan[ad] = deger;
    BF.not = "";
    /* Seed listesi ELLE yazılmadıysa ana seed / tekrar sayısından
       türetilmeye devam eder; elle yazıldıysa tekrar sayısı listeden. */
    if (ad === "seed" || ad === "tekrar" || ad === "seed_tur") {
        /* Çokluya geçince en az iki tekrar (arka uçla aynı kural);
           ilk hazır çip 3. */
        if (ad === "seed_tur" && deger === "coklu" && bfTam(BF.alan.tekrar, 1) < 2)
            BF.alan.tekrar = 3;
        if (!BF.seedlerElle)
            BF.alan.seedler = bfTuretilenSeedler(BF.alan.seed, BF.alan.tekrar);
    }
    if (ad === "seedler") {
        const liste = bfSeedListesi(deger);
        BF.seedlerElle = liste.length >= 2;
        if (liste.length >= 2) BF.alan.tekrar = liste.length;
        else BF.alan.seedler = bfTuretilenSeedler(BF.alan.seed, BF.alan.tekrar);
    }
    // val_var / cv ELLE degistiyse hazir secim artik gecerli degil:
    // etiket (val_var, cv) ikilisinden yeniden turetiliyor, "ozel"
    // olabilir. Arka uca da acik olarak bu ikisi gonderilecek.
    if (ad === "val_var" || ad === "cv") {
        BF.acikEksen = true;
        BF.alan.train_kullanimi = bfTrainKullanimi(
            bfValVar(BF.alan.val_var), BF.alan.cv);
    }
    bfTazele();
}

function bfKilitCiz() {
    const f = BF.veri;
    const kutu = elYap("div", "bf-kilit");
    kutu.appendChild(elYap("div", "bf-kilit-baslik", "Bölme Kilitli"));
    kutu.appendChild(elYap("div", "val-ozet",
        f.kilit_nedeni || "Bölme uygulandı ve sonraki adımlar bu bölme "
        + "üzerinde çalıştı."));

    if (BF.kilitAcik) {
        // Kilit ACIK: ne olacagi kaydetmeden ONCE, tek cumlede yaziyor.
        kutu.appendChild(elYap("div", "bf-zorla-uyari", BF_KILIT_UYARISI));
        const vazgec = document.createElement("button");
        vazgec.type = "button";
        vazgec.className = "ft-mini bf-kilit-vazgec";
        vazgec.textContent = "Kilidi Geri Koy";
        vazgec.onclick = () => {
            BF.kilitAcik = false;
            BF.zorlaOnay = false;
            BF.alan = bfAlanlar(BF.veri);
            BF.acikEksen = false;
            BF.hata = "";
            bfTazele();
        };
        kutu.appendChild(vazgec);
        return kutu;
    }

    /* Iki adimli onay. native confirm() YOK: Dataiku iframe'inde akisi
       bloklar ve ne kaybedilecegini tek satirda anlatamaz. Birinci
       tiklama dugmeyi uyariya cevirir, ikinci tiklama kilidi acar. */
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ft-mini bf-zorla" + (BF.zorlaOnay ? " onay-bekliyor" : "");
    btn.textContent = BF.zorlaOnay
        ? "Evet, analizleri geçersiz kıl" : "Yine de değiştir";
    btn.onclick = () => {
        if (!BF.zorlaOnay) { BF.zorlaOnay = true; bfTazele(); return; }
        BF.zorlaOnay = false;
        BF.kilitAcik = true;
        bfTazele();
    };
    if (BF.zorlaOnay)
        kutu.appendChild(elYap("div", "bf-zorla-uyari", BF_KILIT_UYARISI));
    kutu.appendChild(btn);
    return kutu;
}

/* Alan TASLAKTAN dolayi pasif mi?

   BU DORT ALANDA ARKA UCUN "kilitli" BAYRAGI OKUNMAZ, taslak kazanir.
   Sebep: o bayrak SON KAYDEDILEN hale gore hesaplanmis aynı kuraldır,
   yani kullanıcı "Rastgele"ye tıkladığı anda bayat olur. Kullanıcı Test
   Payı'nı açmak için sunucuya gidip dönmeyi beklememeli.

   Gerçekten dışarıdan gelen kısıtlar (dönem kolonu yok gibi) bu yoldan
   GELMEZ: arka uç o durumda seçenek listesini BOŞ gönderir ve alan
   sabit metin olarak, sebebiyle birlikte çizilir. */
function bfTaslakPasif(ad) {
    const a = BF.alan;
    if (a.test_tanim === "hazir") {
        /* Hazır bölmede setler tabloda yazılı; oran, dönem ve parça
           ayarlarının hiçbiri sonucu değiştirmez. */
        return ad === "oot_adet" || ad === "test_oran";
    }
    if (ad === "oot_adet") return a.test_tanim !== "zamansal";
    if (ad === "test_oran") return a.test_tanim !== "rastgele";
    if (ad === "val_oran") return !bfValVar(a.val_var);
    if (ad === "kat") return a.cv === "yok";
    if (ad === "tekrar" || ad === "seedler") return a.seed_tur !== "coklu";
    if (ad === "gap") return a.test_tanim !== "zamansal";
    return false;
}


/* Önerilen oran, yüzde olarak (çipteki nokta için); yoksa null. */
function bfOneriYuzde(ad) {
    const o = bfOneriDegeri(ad);
    if (o === undefined || o === null) return null;
    let v = Number(o);
    if (!isFinite(v) || v <= 0) return null;
    if (v <= 1) v = v * 100;
    return Math.round(v);
}

/* Arka uç yüzde olarak gönderiyor; eski gövdede kesir gelebilir. */
function bfYuzdeDegeri(ad, k) {
    const ham = (BF.alan && BF.alan[ad] !== undefined && BF.alan[ad] !== null)
        ? BF.alan[ad] : k.deger;
    let v = Number(ham);
    if (!isFinite(v) || v <= 0) return 20;
    if (v <= 1) v = v * 100;
    return Math.round(v);
}

/* SERBEST SAYI ALANI (parça sayısı): aralık dışına taşmayı engeller,
   arasını kullanıcıya bırakır. */


/* Ozet satiri + "kaydedilmedi" notu. Iki modda da ayni. */
function bfOzetCiz(kok) {
    const f = BF.veri || {};
    const degisti = bfDegisti();
    const sunucuOzeti = (BF.ozet !== null && BF.ozet !== undefined)
        ? BF.ozet : (f.ozet || "");
    /* "ozet_kesin": arka uç bölmeyi HESAPLADI mı? Metinden anlaşılmaz,
       bu yüzden gövdede ayrı bir bayrak geliyor. */
    const kesin = !degisti && !!f.ozet_kesin;
    const tahmin = !kesin;
    /* ÖNERİ MODUNDA TAHMİNİ ÖZET ÇİZİLMEZ: planın kendisi zaten satır
       satır yazıyor ("Test Dönemleri: Son dönem", "Eğitim Dönemleri:
       5 dönem"). Aynı bilgiyi bir de altta tekrarlamak, sadeleştirmeye
       çalıştığımız gürültünün ta kendisiydi. Bölme hesaplandıktan sonra
       özet GERÇEK satır sayılarını taşır ve o zaman çizilir. */
    if (tahmin && !bolmeOzellestirildi()) return;
    const ozetEl = elYap("div", "bf-ozet" + (tahmin ? " tahmin" : ""),
                         tahmin ? bfYerelOzet() : sunucuOzeti);
    ozetEl.setAttribute("data-bf", "ozet");
    kok.appendChild(ozetEl);
    if (tahmin) {
        kok.appendChild(elYap("div", "panel-not bf-not",
            degisti ? "Kaydedilmedi - oranların etkisi gösteriliyor; kesin "
                      + "satır sayıları kaydettikten sonra hesaplanır."
                    : "Bölme henüz hesaplanmadı; kesin satır sayıları bu "
                      + "adım çalıştıktan sonra gelir."));
    }
}

/* Uyari kutusu. Hem Önerilen hem Özel modda görünür (kullanıcı
   "Rastgele" seçtiğinde daha anlamlı ama her iki modda da geçerli). */
function bfUyariKutusuCiz(kok) {
    const uyarilar = bfUyariListesi();
    if (!uyarilar.length) return;
    const kutu = elYap("div", "bf-uyarilar");
    kutu.setAttribute("role", "alert");
    uyarilar.forEach(u => kutu.appendChild(elYap("div", "bf-uyari", u)));
    kok.appendChild(kutu);
}

/* Veriden doğan KISITLAR: seçilemeyen seçenek ve SEBEBİ. Uyarıdan
   farkı: uyarı yapılan bir seçimin sonucunu, kısıt yapılamayacak bir
   seçimi anlatır. Kullanıcı "kısıtlar dahilinde seçim yapabilmeli"
   (kullanıcı kararı) - bunun için önce kısıtı görmesi gerekiyor. */
function bfKisitCiz(kok, kisitlar) {
    const liste = kisitlar || (BF.veri && BF.veri.kisitlar) || [];
    if (!liste.length) return;
    const kutu = elYap("div", "bf-kisitlar");
    kutu.appendChild(elYap("div", "bf-kisit-baslik", "Veriden Gelen Kısıtlar"));
    liste.forEach(k => kutu.appendChild(
        elYap("div", "bf-kisit", (k && k.metin) || String(k))));
    kok.appendChild(kutu);
}

/* Not: "Özel Ayarlar" formu artık gruplar halinde değil, iki kartın
   ORTAK satır listesinden çiziliyor (bkz. bolmeSatirOzelCiz). Grup
   kurgusu kaldırıldı - iki kart aynı satırları aynı sırada göstermek
   zorunda ve gruplar bu hizayı bozuyordu. */

function bfTazele() {
    bolmeGovdeTazele();
}

/* Iyimser yazma YOK: bolme hesaplanan bir sey, yazildi saymak yanlis
   satir sayisi gostermek olurdu. Hatada taslak SUNUCUDAKI degerlere
   doner - yarim kalmis bir ayarla devam etmek, kullanicinin ekranda
   gordugu bolme ile veride duran bolmeyi ayirir. */
function bfKaydet(secenek) {
    if (!BF.veri || bfPasif()) return;
    const ayar = secenek || {};
    const geriDon = bfAlanlar(BF.veri);
    /* ONERI MODU: govde gondermiyoruz. Oneri arka ucta hesaplaniyor
       (akis_durum.bolme_onerisi) ve "oneri": true ile aynen
       uygulaniyor. On yuzun oneriyi yeniden kurup gondermesi, iki
       tarafin ayri oneri hesaplamasi ve zamanla ayrismasi demekti. */
    const govde = ayar.oneri ? { oneri: true } : { bolme: bfKayitGovdesi() };
    if (ayar.mod) govde.mod = ayar.mod;
    // Kilitli formda arka uc "onay": true bekliyor (bkz. bolme_kaydet_endpoint).
    if (BF.kilitAcik) govde.onay = true;

    BF.kaydediyor = true;
    BF.hata = ""; BF.not = "";
    let basarili = false;
    bfTazele();

    fetch(getWebAppBackendUrl("bolme_kaydet"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(ftKimlikGovdesi(govde))
    })
    .then(r => r.json())
    .then(d => {
        BF.kaydediyor = false;
        if (!d || d.tamam !== true) {
            BF.alan = geriDon;
            BF.acikEksen = false;
            if (d && d.onay_gerekli) { BF.kilitAcik = false; BF.zorlaOnay = false; }
            BF.hata = (d && d.hata) || "Bölme ayarları kaydedilemedi.";
        } else {
            if (d.bolme_formu) {
                /* Panel verisine de yaziliyor: sekme degistirip geri
                   donuldugunde eski form nesnesi taslagi ESKI degerlere
                   dondururdu. Panel kopyasi SALT OKUNUR isaretleniyor -
                   HAZIRLIK sekmesi artik ozet gosteriyor, form degil
                   (bkz. bolmeFormuCiz). */
                if (ANALIZ_VERI.bolme) {
                    ANALIZ_VERI.bolme.bolme_formu =
                        Object.assign({}, d.bolme_formu, { sadece_ozet: true });
                }
                BF.veri = d.bolme_formu;
            }
            BF.alan = bfAlanlar(BF.veri);
            BF.ozet = d.ozet || "";
            BF.uyarilar = Array.isArray(d.uyarilar) ? d.uyarilar : [];
            BF.acikEksen = false;
            BF.kilitAcik = false;
            BF.zorlaOnay = false;
            /* "Önerilen ayarlar uygulandı." / "Bölme ayarları kaydedildi."
               yazılmaz (kullanıcı kararı: "saçma duruyor"). */
            BF.not = "";
            /* Sohbetteki bolme karti aciksa taze govdeyi o da alir:
               ozet, uyarilar ve kisitlar ayara bagli. */
            if (d.secim_alani && BOLME.kart) BOLME.alan = d.secim_alani;
            basarili = true;
        }
        bfTazele();
        /* Kayit BASARILIYSA devam: "Bu Ayarlarla Devam Et" once kaydedip
           sonra adimi ilerletiyor. Hata varsa ilerlemez - yarim kalmis
           bir ayarla devam etmek, ekranda bir bolme veride baskasi
           demekti. */
        if (basarili && typeof ayar.sonra === "function") ayar.sonra();
    })
    .catch(e => {
        BF.kaydediyor = false;
        BF.alan = geriDon;
        BF.acikEksen = false;
        BF.hata = "Bölme ayarları kaydedilemedi: " + e;
        bfTazele();
    });
}

function bolmeFormuCiz(f) {
    /* HAZIRLIK SEKMESINDE FORM YOK. Seçim "Bölme Stratejisi" adımının
       sohbet kartında yapılıyor; burada yalnızca nasıl ayarlandığını
       yazan salt okunur bir özet kartı var (arka uçta
       akis_panel.bolme_ozet_karti, normal kart olarak geliyor).
       Aynı kararı iki ayrı ekranda vermek, kullanıcının hangisinin
       geçerli olduğunu bilememesi demekti.

       Gövde yine geliyor: üst şeritteki set seçici "Doğrulama"
       düğmesini göstereceğini buradan okuyor (setBolmeAlanlari). */
    void f;
}

/* ==================== Set seçici ==================== */
/* Analiz panelinin tepesindeki Tümü / Eğitim / Doğrulama / Test.

   AYRI BIR "OOT" DUGMESI YOK: bolme artik en fazla uc set uretiyor ve
   zamansal testte test seti ZATEN OOT'dur (bkz. akis_durum.bolme_ayarlari).
   Ayri bir OOT dugmesi olmayan bir seti secilebilir gosterirdi.

   Secim YALNIZCA on yuzde tutulur; /analiz govdesine parametre GECMEZ
   (bkz. SOZLESME2 §7). Bu turda DAGILIM ve ILISKILER hala iskele:
   secilen setin yalnizca ADINI gosterirler. */
/* ETIKETLER TURKCE (kullanici karari): ekranda yabancı terim yok. */
const SET_SECENEKLERI = [
    { anahtar: "tumu",  etiket: "Tümü" },
    { anahtar: "train", etiket: "Train (MS)" },
    { anahtar: "val",   etiket: "Test (OOS)",  alan: "val_var" },
    { anahtar: "test",  etiket: "Validasyon (OOT)" }
];

/* SET ADLARI (kurum karari; yalnizca adlar degisti, kurgu ayni):
   egitim = Train (MS), val = Test (OOS), test = Validasyon (OOT) - rastgele
   bolmede de (arka uc: akis_durum.set_basligi). */
const TEST_OOS2 = "Validasyon (OOT)";

/* Secicinin GORUNDUGU sekmeler. VERİ & SÖZLÜK ve HAZIRLIK her zaman tum
   satirlarda calisiyor; orada pasif gri bir secici birakmak "burada da
   secilebilir ama simdi olmaz" diye okunuyordu - hic cizilmiyor.
   VALİDASYON da listede yok: final metrikleri test setinde, sonda bir
   kez olculur; secilecek bir sey yok. */
/* DEĞİŞKEN ANALİZİ'nde secici DAĞILIM bolumune uygulanir; SFA her zaman
   egitim satirlarinda (bolum basliginin altinda yazar). */
const SET_SECICI_SEKMELER = ["degisken"];
const SET_PASIF_SEKMELER = [];
const SFA_SET_NOTU = "SFA yalnızca eğitim satırlarında ölçülür";

let AKTIF_SET = "tumu";

/* val_var bilgisi HAZIRLIK panelindeki bolme formundan okunur; ikinci
   bir kaynak tutmak iki yerin farkli sey soylemesi demekti. */
function setBolmeAlanlari() {
    const h = ANALIZ_VERI && ANALIZ_VERI.bolme;
    const f = h && h.bolme_formu;
    return (f && f.alanlar) || null;
}

/* Nihai setin etiketi: her bolme turunde Validasyon (OOT). */
function setEtiketi(s) {
    const al = setBolmeAlanlari();
    const tur = al && al.test_tanim && al.test_tanim.deger;
    return (s.anahtar === "test" && tur === "rastgele") ? TEST_OOS2 : s.etiket;
}

function setSecenekleri() {
    const al = setBolmeAlanlari();
    return SET_SECENEKLERI.filter(s =>
        !s.alan || !!(al && al[s.alan] && al[s.alan].deger))
        .map(s => Object.assign({}, s, { etiket: setEtiketi(s) }));
}

function setAdi(anahtar) {
    for (let i = 0; i < SET_SECENEKLERI.length; i++)
        if (SET_SECENEKLERI[i].anahtar === anahtar) return setEtiketi(SET_SECENEKLERI[i]);
    return SET_SECENEKLERI[0].etiket;
}

function setSeciciCiz(tab) {
    if (SET_SECICI_SEKMELER.indexOf(tab) === -1) return;
    const secenekler = setSecenekleri();
    // Val/OOT kapatilmissa secim ustunde asili kalmasin.
    if (!secenekler.some(s => s.anahtar === AKTIF_SET)) AKTIF_SET = "tumu";

    const pasif = SET_PASIF_SEKMELER.indexOf(tab) !== -1;
    // SFA'da gosterilen secim de "train": kilit ancak boyle okunuyor.
    const secili = pasif ? "train" : AKTIF_SET;

    const kok = elYap("div", "set-secici");
    kok.setAttribute("role", "group");
    kok.setAttribute("aria-label", "Analiz kapsamı");

    const dugmeler = elYap("div", "set-dugmeler");
    secenekler.forEach(s => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "set-dugme" + (s.anahtar === secili ? " secili" : "");
        b.setAttribute("data-set", s.anahtar);
        b.setAttribute("aria-pressed", s.anahtar === secili ? "true" : "false");
        b.textContent = s.etiket;
        b.disabled = pasif;
        // Pasifken dinleyici HIC baglanmiyor: disabled bir dugmeye
        // programla gonderilen tiklama tarayicida da her yerde
        // engellenmiyor, secim sessizce degisirdi.
        if (!pasif) b.onclick = () => { AKTIF_SET = s.anahtar; analizCiz(tab); };
        dugmeler.appendChild(b);
    });
    kok.appendChild(dugmeler);
    if (pasif) kok.appendChild(elYap("div", "set-not", SFA_SET_NOTU));
    analizGovde.appendChild(kok);
}


function analizCiz(tab) {
    /* Panel bastan ciziliyor; feature tablosunda yaziyor olabilir.
       Odak ve imlec yeri ayni kontrole geri veriliyor. */
    const odak = ftOdakAnahtari();
    aktifAnalizSekme = tab;
    analizGovde.innerHTML = "";
    if (tab === "degisken") {
        /* Kume secici yalnizca Dağılım bolumune uygulanir: basligin altinda. */
        panelBolumBasligi("Dağılım");
        setSeciciCiz(tab);
        dagilimCiz();
        panelBolumBasligi("Tek Değişken Analizi (SFA)");
        analizGovde.appendChild(elYap("div", "set-not", SFA_SET_NOTU));
        panelCiz(ANALIZ_VERI.sfa);
        if (ANALIZ_VERI.sfa && ANALIZ_VERI.sfa.aralik) aralikCiz();
        panelBolumBasligi("Eksik Değer");
        panelCiz(ANALIZ_VERI.eksik);
        ftOdakGeriVer(odak);
        return;
    }
    setSeciciCiz(tab);
    if (tab === "bolme") {
        panelBolumBasligi("Bölme");
        panelCiz(ANALIZ_VERI.bolme);
        panelBolumBasligi("Validasyon");
        validasyonCiz(ANALIZ_VERI.validasyon);
        return;
    }
    panelCiz(ANALIZ_VERI[tab]);
    ftOdakGeriVer(odak);
}

/* ==================== SFA ekranı (Değişken Analizi sekmesi) ====================
   Kullanıcı kararı: SFA eleme yeri değil; her değişken için ölçütler,
   özellik dağılımı + hedef (1) oranı grafiği (çift eksen, örnek ekrandaki
   gibi) ve yapay zekânın verdiği, kullanıcının değiştirebildiği karar
   (Kullan, Eksik Doldurma, Aykırı Değer, Dönüşüm, Ayrıklaştırma, Yorum).
   Liste /sfa_degiskenler ucundan bir kez çekilir; değişken adına tıklayınca
   /sfa_degisken ile o değişkenin ayrıntısı gelir. */
const ARALIK = { liste: null, detay: {}, filtre: "tumu", ara: "", acik: "", istek: 0,
                 gorunum: "ham" };
const ARALIK_SATIR_SINIRI = 200;
const SEKIL_ETIKET = { "artan": "Artan", "azalan": "Azalan", "U": "U",
                       "ters U": "Ters U", "gruplama": "Gruplama",
                       "düz": "İlişki Yok", "düzensiz": "Düzensiz" };
const SFA_KAYNAK_ETIKET = { yapay_zeka: "Yapay Zekâ", kullanici: "Sizin Kararınız",
                            kural: "Kural" };
const SFA_SECENEK = {
    kullan: [["evet", "Evet"], ["hayir", "Hayır"]],
    eksik: [["yok", "Yok"], ["medyan", "Medyan"], ["sabit", "Sabit Değer"],
            ["isaret", "Eksik İşareti + Medyan"], ["missing", "MISSING Kategorisi"]],
    aykiri: [["yok", "Yok"], ["winsor", "Winsor (%5)"]],
    donusum: [["yok", "Yok"], ["log", "Log"], ["ustel", "Üstel"], ["sira", "Sıra"]],
    ayriklastirma: [["yok", "Yok"], ["onerilen", "Önerilen Aralıklar"]]
};
const SFA_ACIKLAMA =
    "Her değişkenin hedefle ilişkisi Train satırlarında ölçüldü; eleme yapılmadı. "
    + "Yapay zekâ her değişkenin modele hangi hâliyle gireceğine karar verdi. "
    + "Değişken adına tıklayınca ölçütler, grafik ve karar formu açılır; "
    + "değiştirdiğiniz karar yapay zekânın kararının yerine geçer.";

function aralikSifirla() { ARALIK.liste = null; ARALIK.detay = {}; }

function sfaGetir(uc, kolon) {
    return fetch(getWebAppBackendUrl(uc) + "?oturum_id=" + encodeURIComponent(OTURUM_ID)
                 + (kolon ? "&kolon=" + encodeURIComponent(kolon) : ""))
        .then(r => r.json());
}

function ivMetni(v) {
    return (v === null || v === undefined) ? "∅"
        : Number(v).toLocaleString("tr-TR", { minimumFractionDigits: 3, maximumFractionDigits: 3 });
}

function yuzdeMetni(v, basamak) {
    if (v === null || v === undefined) return "∅";
    return "%" + (100 * Number(v || 0)).toLocaleString("tr-TR",
        { minimumFractionDigits: basamak, maximumFractionDigits: basamak });
}

/* Eksen etiketi için kısa sayı: 1.234.567 -> 1,2 Mn; 12.345 -> 12,3 B */
function kisaSayi(v) {
    if (v === null || v === undefined) return "";
    const n = Number(v), m = Math.abs(n);
    const f = (x, b) => x.toLocaleString("tr-TR", { maximumFractionDigits: b });
    if (m >= 1e6) return f(n / 1e6, 1) + " Mn";
    if (m >= 1e4) return f(n / 1e3, 1) + " B";
    if (m >= 100) return f(n, 0);
    if (m >= 1) return f(n, 1);
    return f(n, 3);
}

function aralikCiz() {
    const kap = elYap("div", "aralik-kap");
    analizGovde.appendChild(kap);
    const istek = ++ARALIK.istek;
    if (!ARALIK.liste) {
        kap.appendChild(elYap("div", "dag-not", "SFA sonuçları yükleniyor…"));
        sfaGetir("sfa_degiskenler").then(d => {
            if (istek !== ARALIK.istek || aktifAnalizSekme !== "degisken") return;
            ARALIK.liste = (d && d.degiskenler) || [];
            ARALIK.hata = (d && d.tamam === false) ? d.hata : "";
            analizCiz("degisken");
        }).catch(() => {});
        return;
    }
    if (ARALIK.hata) { kap.appendChild(elYap("div", "dag-not dag-hata", ARALIK.hata)); return; }

    kap.appendChild(elYap("div", "iskele-baslik aralik-baslik", "Değişkenler"));
    kap.appendChild(elYap("div", "aralik-aciklama", SFA_ACIKLAMA));
    const adet = f => ARALIK.liste.filter(f).length.toLocaleString("tr-TR");
    const satir = elYap("div", "aralik-secim");
    [["tumu", "Tümü", () => true],
     ["yapay_zeka", "Yapay Zekâ", o => o.kaynak === "yapay_zeka"],
     ["kullanici", "Sizin", o => o.kaynak === "kullanici"],
     ["girmeyen", "Modele Girmeyen", o => o.karar === "Modele girmez"],
     ["hassas", "Hassas", o => !!o.hassas]].forEach(([k, ad, f]) => {
        const b = elYap("button", "bolme-cip" + (k === ARALIK.filtre ? " secili" : ""),
                        ad + " (" + adet(f) + ")");
        b.type = "button";
        b.onclick = () => { ARALIK.filtre = k; analizCiz("degisken"); };
        satir.appendChild(b);
    });
    kap.appendChild(satir);

    const ara = document.createElement("input");
    ara.className = "ft-ara aralik-ara";
    ara.placeholder = "Değişken ara…";
    ara.value = ARALIK.ara;
    ara.oninput = () => { ARALIK.ara = ara.value; tabloCiz(); };
    kap.appendChild(ara);

    const tabloKap = elYap("div", "aralik-tablo-kap");
    kap.appendChild(tabloKap);

    function suz() {
        const a = ftSade(ARALIK.ara || "");
        const f = ARALIK.filtre;
        return ARALIK.liste.filter(o =>
            (f === "tumu" || (f === "yapay_zeka" && o.kaynak === "yapay_zeka")
             || (f === "kullanici" && o.kaynak === "kullanici")
             || (f === "girmeyen" && o.karar === "Modele girmez")
             || (f === "hassas" && o.hassas))
            && (!a || ftSade(o.ad).includes(a)));
    }

    function tabloCiz() {
        tabloKap.innerHTML = "";
        const liste = suz();
        if (!liste.length) {
            tabloKap.appendChild(elYap("div", "dag-not", "Bu filtreye uyan değişken yok."));
            return;
        }
        const t = elYap("table", "aralik-tablo");
        const bas = elYap("tr");
        [["Değişken", ""], ["IV", "10 aralıkla, Train"], ["C-value", "Ham değerle, Train"],
         ["Karar", "Modele hangi hâliyle girecek"]].forEach(([x, ipucu]) => {
            const th = elYap("th", "", x);
            if (ipucu) th.title = ipucu;
            bas.appendChild(th);
        });
        t.appendChild(bas);
        liste.slice(0, ARALIK_SATIR_SINIRI).forEach(o => {
            const acik = ARALIK.acik === o.ad;
            const tr = elYap("tr", "aralik-satir" + (acik ? " acik" : ""));
            const ad = elYap("td", "aralik-ad");
            ad.appendChild(elYap("span", "aralik-ok", acik ? "▾" : "▸"));
            const link = elYap("button", "aralik-ad-link", o.ad);
            link.type = "button";
            link.title = "Ölçütler, grafik ve karar";
            ad.appendChild(link);
            if (o.hassas) ad.appendChild(elYap("span", "aralik-rozet hassas", "Hassas"));
            if (o.sizinti) ad.appendChild(elYap("span", "aralik-rozet uyari", "Sızıntı Şüphesi"));
            tr.appendChild(ad);
            tr.appendChild(elYap("td", "sayi", ivMetni(o.iv)));
            tr.appendChild(elYap("td", "sayi", ivMetni(o.c)));
            const k = elYap("td", "aralik-karar-hucre");
            k.appendChild(elYap("span", "", o.karar || "∅"));
            if (o.kaynak) k.appendChild(elYap("span", "aralik-kaynak " + o.kaynak,
                                               SFA_KAYNAK_ETIKET[o.kaynak] || o.kaynak));
            tr.appendChild(k);
            tr.onclick = () => { ARALIK.acik = acik ? "" : o.ad; tabloCiz(); };
            t.appendChild(tr);
            if (acik) {
                const dtr = elYap("tr", "aralik-detay-satir");
                const td = elYap("td");
                td.colSpan = 4;
                dtr.appendChild(td);
                t.appendChild(dtr);
                sfaDetayCiz(td, o, tabloCiz);
            }
        });
        tabloKap.appendChild(t);
        if (liste.length > ARALIK_SATIR_SINIRI)
            tabloKap.appendChild(elYap("div", "dag-not", liste.length.toLocaleString("tr-TR")
                + " değişkenden ilk " + ARALIK_SATIR_SINIRI + " tanesi gösteriliyor; aramayla daraltın."));
    }

    tabloCiz();
}

/* Bir değişkenin SFA sayfası: açıklama, ölçütler, grafik, karar formu. */
function sfaDetayCiz(td, ozet, yenidenCiz) {
    const ad = ozet.ad;
    const v = ARALIK.detay[ad];
    if (!v) {
        td.appendChild(elYap("div", "dag-not", "Değişken yükleniyor…"));
        sfaGetir("sfa_degisken", ad).then(d => {
            if (d && d.tamam) { ARALIK.detay[ad] = d.degisken; if (ARALIK.acik === ad) yenidenCiz(); }
            else { td.innerHTML = ""; td.appendChild(elYap("div", "dag-not dag-hata", (d && d.hata) || "Okunamadı.")); }
        });
        return;
    }
    const m = v.sfa || {};
    const kategorik = m.tip === "kategorik";
    const bolum = baslik => td.appendChild(elYap("div", "aralik-bolum", baslik));

    td.appendChild(elYap("div", "aralik-tanim" + (v.aciklama ? "" : " bos"),
        v.aciklama || "Sözlükte bu değişken için açıklama yok."));

    /* ÖLÇÜTLER: örnek ekrandaki tablonun karşılığı, dar panele sığsın diye
       iki sütunlu etiket / değer ızgarası. */
    bolum("Ölçütler");
    const g = elYap("div", "sfa-olcut");
    const hucre = (etiket, deger, ipucu) => {
        const h = elYap("div", "sfa-olcut-hucre");
        h.appendChild(elYap("div", "sfa-olcut-etiket", etiket));
        h.appendChild(elYap("div", "sfa-olcut-deger", deger));
        if (ipucu) h.title = ipucu;
        g.appendChild(h);
    };
    const sayi = x => (x === null || x === undefined) ? "∅"
        : Number(x).toLocaleString("tr-TR", { maximumFractionDigits: 4 });
    hucre("Tip", kategorik ? "Kategorik" : "Sayısal");
    hucre("Eksik Sayısı", sayi(m.eksik_sayisi));
    hucre("Eksik Oranı", yuzdeMetni(m.eksik_orani, 2));
    hucre("Eksikte Hedef Oranı", m.eksik_sayisi ? yuzdeMetni(m.eksik_hedef_orani, 2) : "∅",
          "Eksik satırlarda hedefin 1 olma oranı");
    hucre("Genel Hedef Oranı", yuzdeMetni(m.hedef_orani, 2));
    if (!kategorik) {
        hucre("Min", sayi(m.min));
        hucre("Maks", sayi(m.max));
        hucre("Medyan", sayi(m.medyan));
        hucre("Çarpıklık", sayi(m.carpiklik));
        hucre("Uç Değer Payı", yuzdeMetni(m.aykiri_payi, 2), "Q1 − 3·IQR ve Q3 + 3·IQR dışındaki pay");
    } else {
        hucre("Kategori Sayısı", sayi(m.tekil));
    }
    hucre("IV (10 Aralık)", ivMetni(v.ham_iv));
    hucre("IV (Önerilen)", ivMetni((v.ayri || {}).iv),
          v.aralik_sayisi + " aralık, eksikler ayrı aralıkta");
    hucre("Eğilim", SEKIL_ETIKET[v.sekil] || v.sekil || "∅");
    td.appendChild(g);
    const c = m.c || {};
    const ct = elYap("table", "aralik-bin sfa-c-tablo");
    const cb = elYap("tr");
    const cd = elYap("tr");
    [["ham", "Ham"], ["kirpik", "Kırpılmış"], ["log", "Log"], ["ustel", "Üstel"], ["sira", "Sıra"]]
        .forEach(([k, e]) => {
            cb.appendChild(elYap("th", "", e));
            cd.appendChild(elYap("td", "sayi", ivMetni(c[k])));
        });
    const cbas = elYap("tr");
    const cth = elYap("th", "sfa-c-bas", "C-value");
    cth.colSpan = 5;
    cth.title = "Kırpılmış: Train %5 ve %95 yüzdeliklerinde. Log, üstel ve sıra "
        + "tekdüze dönüşüm olduğu için tek değişkenli C-value'yu değiştirmez.";
    cbas.appendChild(cth);
    ct.appendChild(cbas); ct.appendChild(cb); ct.appendChild(cd);
    td.appendChild(ct);

    /* GRAFİK: çubuk = popülasyon payı (sol eksen), nokta = hedef (1) oranı
       (sağ eksen), çizgiler = eğilim. Görünüm: ham, kırpılmış, önerilen. */
    bolum("Dağılım ve Hedef Oranı");
    const dag = v.dagilim || {};
    const secenekler = kategorik ? [["ham", "Kategoriler"], ["onerilen", "Önerilen Gruplar"]]
        : [["ham", "Ham"], ["kirpik", "Kırpılmış (%5)"], ["onerilen", "Önerilen Aralıklar"]];
    if (!secenekler.some(([k]) => k === ARALIK.gorunum)) ARALIK.gorunum = "ham";
    const gs = elYap("div", "aralik-secim");
    secenekler.forEach(([k, e]) => {
        const b = elYap("button", "bolme-cip" + (k === ARALIK.gorunum ? " secili" : ""), e);
        b.type = "button";
        b.onclick = (ev) => { ev.stopPropagation(); ARALIK.gorunum = k; yenidenCiz(); };
        gs.appendChild(b);
    });
    td.appendChild(gs);
    let binler;
    if (ARALIK.gorunum === "onerilen") {
        binler = ((v.ayri || {}).satirlar || []).map(s => Object.assign({}, s, { eksik: s.etiket === "Eksik" }));
    } else {
        binler = (dag[ARALIK.gorunum] || dag.ham || []).slice();
        if (dag.eksik) binler.unshift(Object.assign({}, dag.eksik, { eksik: true }));
    }
    td.appendChild(sfaGrafik(binler, m.hedef_orani, kategorik,
        ARALIK.gorunum === "onerilen" ? (kategorik ? "Önerilen grup" : "Önerilen aralık")
            : (kategorik ? "Kategori (hedef oranına göre sıralı)" : "Aralık (değerlerin ortalaması)")));
    if (v.oneri && ARALIK.gorunum === "onerilen")
        td.appendChild(elYap("div", "aralik-alt", v.oneri));

    bolum("Karar");
    td.appendChild(sfaKararFormu(v, ozet, yenidenCiz));
}

/* Çift eksenli tek grafik (kullanıcı kararı, örnek ekrandaki gibi):
   çubuk = aralıktaki popülasyon payı (sol eksen), nokta + ince çizgi =
   aralıktaki hedef (1) oranı (sağ eksen), kesikli = doğrusal eğilim,
   noktalı = log eğilim. Eksik aralığı en solda, taralı. */
function sfaGrafik(binler, genelOran, kategorik, eksenAdi) {
    const ns = "http://www.w3.org/2000/svg";
    const kap = elYap("div", "dag-grafik sfa-grafik");
    if (!binler.length) { kap.appendChild(elYap("div", "dag-not", "Gösterilecek değer yok.")); return kap; }
    const lj = elYap("div", "aralik-lejant");
    [["sfa-lj-cubuk", "Popülasyon Payı (sol)"], ["sfa-lj-nokta", "Hedef (1) Oranı (sağ)"],
     ["sfa-lj-lin", "Doğrusal Eğilim"], ["sfa-lj-log", "Log Eğilim"]].forEach(([s, e]) => {
        const o = elYap("span", "aralik-lejant-oge");
        o.appendChild(elYap("span", "sfa-lj " + s));
        o.appendChild(document.createTextNode(e));
        lj.appendChild(o);
    });
    kap.appendChild(lj);

    const W = 420, H = 210, SOL = 36, SAG = 40, UST = 8, ALT = 34;
    const gw = W - SOL - SAG, gh = H - UST - ALT;
    const n = binler.length, slot = gw / n, cw = Math.max(2, Math.min(18, slot * 0.62));
    const payMax = Math.max(1e-9, ...binler.map(b => b.pay || 0)) * 1.1;
    const oranMax = Math.max(1e-9, genelOran || 0, ...binler.map(b => b.oran || 0)) * 1.15;
    const X = i => SOL + slot * (i + 0.5);
    const YP = p => UST + gh - gh * (p / payMax);
    const YO = o => UST + gh - gh * (o / oranMax);
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "Popülasyon payı ve hedef oranı");
    const el = (ad, oz, sinif, metin) => {
        const e = document.createElementNS(ns, ad);
        Object.keys(oz).forEach(k => e.setAttribute(k, oz[k]));
        if (sinif) e.setAttribute("class", sinif);
        if (metin !== undefined) e.textContent = metin;
        svg.appendChild(e);
        return e;
    };
    const desen = document.createElementNS(ns, "defs");
    desen.innerHTML = '<pattern id="sfa-tarama" width="4" height="4" patternUnits="userSpaceOnUse" '
        + 'patternTransform="rotate(45)"><rect width="4" height="4" class="sfa-tarama-zemin"/>'
        + '<line x1="0" y1="0" x2="0" y2="4" class="sfa-tarama-cizgi"/></pattern>';
    svg.appendChild(desen);
    /* Izgara ve eksenler: sol % popülasyon, sağ % hedef */
    [0, 0.5, 1].forEach(f => {
        const y = UST + gh - gh * f;
        el("line", { x1: SOL, x2: W - SAG, y1: y, y2: y }, "sfa-izgara");
        el("text", { x: SOL - 4, y: y + 3, "text-anchor": "end" }, "dag-eksen-yazi", yuzdeMetni(payMax * f, 0));
        el("text", { x: W - SAG + 4, y: y + 3, "text-anchor": "start" }, "dag-eksen-yazi", yuzdeMetni(oranMax * f, 1));
    });
    el("line", { x1: SOL, x2: W - SAG, y1: UST + gh, y2: UST + gh }, "dag-eksen");
    /* Çubuklar */
    binler.forEach((b, i) => {
        const h = Math.max(0, UST + gh - YP(b.pay || 0));
        if (h > 0) {
            const x = X(i) - cw / 2, y = UST + gh - h, r = Math.min(3, cw / 2, h);
            el("path", { d: "M" + x + "," + (UST + gh) + " V" + (y + r) + " Q" + x + "," + y + " " + (x + r) + "," + y
                + " H" + (x + cw - r) + " Q" + (x + cw) + "," + y + " " + (x + cw) + "," + (y + r) + " V" + (UST + gh) + " Z" },
               b.eksik ? "sfa-cubuk eksik" : "sfa-cubuk");
        }
    });
    /* Genel hedef oranı: yatay referans */
    if (genelOran !== null && genelOran !== undefined)
        el("line", { x1: SOL, x2: W - SAG, y1: YO(genelOran), y2: YO(genelOran) }, "aralik-ortalama");
    /* Eğilim çizgileri: eksik hariç, satır ağırlıklı en küçük kareler; x = sıra */
    const dolu = binler.map((b, i) => ({ i, b })).filter(o => !o.b.eksik && o.b.oran !== null && o.b.oran !== undefined);
    const uydur = f => {
        let sw = 0, sx = 0, sy = 0, sxx = 0, sxy = 0;
        dolu.forEach(({ i, b }) => {
            const w = b.n || 1, x = f(i - dolu[0].i);
            sw += w; sx += w * x; sy += w * b.oran; sxx += w * x * x; sxy += w * x * b.oran;
        });
        const pay = sw * sxx - sx * sx;
        if (dolu.length < 2 || !pay) return null;
        const bb = (sw * sxy - sx * sy) / pay;
        return { a: (sy - bb * sx) / sw, b: bb };
    };
    [[x => x, "sfa-lin"], [x => Math.log(1 + x), "sfa-log"]].forEach(([f, sinif]) => {
        const u = uydur(f);
        if (!u) return;
        const yol = dolu.map(({ i }, k) => (k ? "L" : "M") + X(i) + ","
            + YO(Math.max(0, Math.min(oranMax, u.a + u.b * f(i - dolu[0].i)))));
        el("path", { d: yol.join(" ") }, sinif);
    });
    /* Hedef oranı noktaları ve bağlantı çizgisi */
    if (dolu.length > 1)
        el("path", { d: dolu.map(({ i, b }, k) => (k ? "L" : "M") + X(i) + "," + YO(b.oran)).join(" ") }, "sfa-oran-cizgi");
    binler.forEach((b, i) => {
        if (b.oran === null || b.oran === undefined) return;
        el("circle", { cx: X(i), cy: YO(b.oran), r: 3.2 }, b.eksik ? "sfa-nokta eksik" : "sfa-nokta");
    });
    /* X ekseni etiketleri: sığdığı kadar (sayısalda aralığın ortalaması) */
    const adim = Math.max(1, Math.ceil(n / 8));
    binler.forEach((b, i) => {
        if (i % adim && !b.eksik) return;
        let e = b.eksik ? "Eksik" : (kategorik || b.ort === undefined || b.ort === null
            ? String(b.etiket || "") : kisaSayi(b.ort));
        if (e.length > 9) e = e.slice(0, 8) + "…";
        el("text", { x: X(i), y: UST + gh + 12, "text-anchor": "middle" }, "dag-eksen-yazi", e);
    });
    el("text", { x: SOL + gw / 2, y: H - 4, "text-anchor": "middle" }, "dag-eksen-yazi", eksenAdi || "");
    /* Üzerine gelince aralığın tam bilgisi */
    const ipucu = elYap("div", "dag-ipucu");
    ipucu.hidden = true;
    binler.forEach((b, i) => {
        const alan = el("rect", { x: SOL + slot * i, y: UST, width: slot, height: gh }, "dag-vurus");
        alan.addEventListener("mouseenter", () => {
            ipucu.textContent = (b.eksik ? "Eksik" : b.etiket) + " · "
                + Number(b.n || 0).toLocaleString("tr-TR") + " satır (" + yuzdeMetni(b.pay, 1)
                + ") · hedef oranı " + yuzdeMetni(b.oran, 2);
            ipucu.hidden = false;
            const kg = kap.clientWidth, iw = ipucu.offsetWidth;
            const merkez = (X(i) / W) * kg;
            ipucu.style.left = Math.max(0, Math.min(kg - iw, merkez - iw / 2)) + "px";
            ipucu.style.top = (lj.offsetHeight + 4) + "px";
        });
        alan.addEventListener("mouseleave", () => { ipucu.hidden = true; });
    });
    kap.appendChild(svg);
    kap.appendChild(ipucu);
    return kap;
}

/* KARAR FORMU (örnek ekrandaki sağ sütunun karşılığı). Kaydedilen karar
   "Sizin Kararınız" olur; yapay zekâ o değişkeni artık değiştirmez. */
function sfaKararFormu(v, ozet, yenidenCiz) {
    const k = Object.assign({}, v.karar || {});
    const kategorik = (v.sfa || {}).tip === "kategorik";
    const form = elYap("div", "sfa-form");
    form.onclick = e => e.stopPropagation();
    const kaynak = elYap("div", "sfa-form-kaynak");
    kaynak.appendChild(elYap("span", "aralik-kaynak " + (k.kaynak || ""),
                             SFA_KAYNAK_ETIKET[k.kaynak] || "Karar yok"));
    if (k.gerekce) kaynak.appendChild(elYap("span", "sfa-gerekce", tireSade(k.gerekce)));
    form.appendChild(kaynak);

    const alanlar = {};
    const satir = (etiket, anahtar, secenekler) => {
        const s = elYap("label", "sfa-form-satir");
        s.appendChild(elYap("span", "sfa-form-etiket", etiket));
        const sel = document.createElement("select");
        sel.className = "sfa-form-sec";
        secenekler.forEach(([d, e]) => {
            const o = document.createElement("option");
            o.value = d; o.textContent = e;
            sel.appendChild(o);
        });
        sel.value = k[anahtar] || secenekler[0][0];
        s.appendChild(sel);
        form.appendChild(s);
        alanlar[anahtar] = sel;
        return sel;
    };
    /* TİP KARARI YALNIZCA BURADA (kullanıcı kararı: "değişkenlerin
       bütün durumuna orada karar vereceğiz"). Seçenekler verinin tam
       kolonla izin verdiği dönüşümler; ilk seçenek kaynak tip. Tip
       değişince sunucu değişkenin SFA'sını yeni tiple yeniden hesaplar,
       form yeni tipin kararıyla yeniden çizilir. */
    const kaynakTip = v.tip_kaynak || (v.sfa || {}).tip || "";
    const tipSec = satir("Tip", "tip", [["yok", "Kaynak Tip ("
        + (kaynakTip ? kaynakTip.charAt(0).toLocaleUpperCase("tr-TR") + kaynakTip.slice(1) : "-")
        + ")"]].concat((v.tip_secenekleri || []).map(o => [o.kod, tireSade(o.etiket)])));
    if (!(v.tip_secenekleri || []).length) {
        tipSec.disabled = true;
        tipSec.title = "Bu değişkenin verisi başka bir tipe çevrilemiyor.";
    }
    const tipNot = elYap("div", "sfa-form-not",
        "Tip değişince bu değişkenin SFA'sı yeni tiple yeniden hesaplanır; "
        + "diğer alanlar yeni tipe göre yeniden önerilir.");
    tipNot.hidden = true;
    form.appendChild(tipNot);
    tipSec.addEventListener("change", () => {
        tipNot.hidden = tipSec.value === (k.tip || "yok");
    });
    satir("Kullan", "kullan", SFA_SECENEK.kullan);
    const eksikSec = satir("Eksik Doldurma", "eksik", SFA_SECENEK.eksik.filter(([d]) =>
        kategorik ? (d === "yok" || d === "missing") : d !== "missing"));
    const deger = document.createElement("input");
    deger.className = "sfa-form-deger";
    deger.placeholder = "Doldurma değeri";
    deger.value = (k.eksik_deger === null || k.eksik_deger === undefined) ? "" : String(k.eksik_deger).replace(".", ",");
    const degerSatir = elYap("label", "sfa-form-satir");
    degerSatir.appendChild(elYap("span", "sfa-form-etiket", "Doldurma Değeri"));
    degerSatir.appendChild(deger);
    form.appendChild(degerSatir);
    const degerGoster = () => { degerSatir.hidden = eksikSec.value !== "sabit"; };
    eksikSec.onchange = degerGoster;
    degerGoster();
    if (!kategorik) {
        satir("Aykırı Değer", "aykiri", SFA_SECENEK.aykiri);
        satir("Dönüşüm", "donusum", SFA_SECENEK.donusum);
    }
    satir("Ayrıklaştırma", "ayriklastirma", SFA_SECENEK.ayriklastirma);
    const yorum = document.createElement("textarea");
    yorum.className = "sfa-form-yorum";
    yorum.rows = 2;
    yorum.placeholder = "Yorum";
    yorum.value = k.yorum || "";
    const ys = elYap("label", "sfa-form-satir");
    ys.appendChild(elYap("span", "sfa-form-etiket", "Yorum"));
    ys.appendChild(yorum);
    form.appendChild(ys);

    const alt = elYap("div", "sfa-form-alt");
    const durum = elYap("span", "sfa-form-durum");
    const kaydet = elYap("button", "secim-onay sfa-kaydet", "Kaydet");
    kaydet.type = "button";
    kaydet.onclick = () => {
        const karar = { yorum: yorum.value, eksik_deger: deger.value.replace(",", ".") || null };
        Object.keys(alanlar).forEach(a => { karar[a] = alanlar[a].value; });
        kaydet.disabled = true;
        durum.textContent = tipSec.value !== (k.tip || "yok")
            ? "SFA yeni tiple hesaplanıyor…" : "Kaydediliyor…";
        fetch(getWebAppBackendUrl("sfa_karar"), {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ oturum_id: OTURUM_ID, kolon: v.ad || ozet.ad, karar: karar })
        }).then(r => r.json()).then(d => {
            kaydet.disabled = false;
            if (!d || !d.tamam) { durum.textContent = tireSade((d && d.hata) || "Kaydedilemedi."); return; }
            v.karar = d.karar;
            if (d.degisken) {
                /* Tip değişti: detay (ölçütler, grafik, aralıklar) yeni tiple. */
                ARALIK.detay[v.ad || ozet.ad] = d.degisken;
                Object.assign(ozet, d.liste || {});
            }
            ozet.karar = d.ozet;
            ozet.kaynak = "kullanici";
            yenidenCiz();
        }).catch(e => { kaydet.disabled = false; durum.textContent = "Kaydedilemedi: " + e; });
    };
    alt.appendChild(durum);
    alt.appendChild(kaydet);
    form.appendChild(alt);
    return form;
}

/* Birlesik sekmelerde bolum basligi (DEĞİŞKEN ANALİZİ, BÖLME & VALİDASYON) */
function panelBolumBasligi(metin) {
    analizGovde.appendChild(elYap("div", "panel-bolum-baslik", metin));
}

/* ==================== DAĞILIM sekmesi ====================
   Seçilen TEK değişkenin dağılımı, seçilen sette (Tümü / Train /
   Validasyon / Test). Sunucu TAM VERİYLE hesaplıyor (/dagilim);
   sonuç (kolon, set) başına önbellekte, her yeni sunucu yanıtında
   (veri değişmiş olabilir) önbellek boşalıyor. */
const DAGILIM = { kolonlar: null, kolon: "", onbellek: {}, istek: 0 };

function dagilimSifirla() {
    DAGILIM.kolonlar = null;
    DAGILIM.onbellek = {};
}

function dagSayi(x) {
    if (x === null || x === undefined || x === "") return "∅";
    const n = Number(x);
    if (!isFinite(n)) return String(x);
    return n.toLocaleString("tr-TR", { maximumFractionDigits: Math.abs(n) >= 100 ? 2 : 4 });
}

function dagilimGetir(kolon, set) {
    const url = getWebAppBackendUrl("dagilim") + "?oturum_id=" + encodeURIComponent(OTURUM_ID)
        + (kolon ? "&kolon=" + encodeURIComponent(kolon) + "&set=" + encodeURIComponent(set) : "");
    return fetch(url).then(r => r.json());
}

function dagilimCiz() {
    const kap = elYap("div", "dag-kap");
    analizGovde.appendChild(kap);
    const istek = ++DAGILIM.istek;
    const hala = () => istek === DAGILIM.istek && aktifAnalizSekme === "degisken";

    if (!DAGILIM.kolonlar) {
        kap.appendChild(elYap("div", "dag-not", "Değişken listesi yükleniyor…"));
        dagilimGetir("", "")
            .then(d => {
                if (!hala()) return;
                if (!d || d.tamam !== true) {
                    kap.innerHTML = "";
                    kap.appendChild(elYap("div", "dag-not dag-hata",
                        tireSade((d && (d.hata || d.metin)) || "Değişken listesi okunamadı.")));
                    return;
                }
                DAGILIM.kolonlar = d.kolonlar || [];
                if (!DAGILIM.kolonlar.length) {
                    kap.innerHTML = "";
                    kap.appendChild(elYap("div", "dag-not", tireSade(d.not || "Gösterilecek değişken yok.")));
                    return;
                }
                analizCiz("degisken");
            })
            .catch(e => { if (hala()) { kap.innerHTML = ""; kap.appendChild(elYap("div", "dag-not dag-hata", "Değişken listesi okunamadı: " + e)); } });
        return;
    }

    const combo = comboYap("Değişken", () => {
        const v = combo.deger ? combo.deger() : combo.giris.value;
        if (combo.gecerli && combo.gecerli() && v && v !== DAGILIM.kolon) {
            DAGILIM.kolon = v;
            analizCiz("degisken");
        }
    }, DAGILIM.kolon, { liste: DAGILIM.kolonlar, zorunlu: false,
                        placeholder: "Değişken ara…" });
    kap.appendChild(combo.kok);

    const govde = elYap("div", "dag-govde");
    kap.appendChild(govde);
    if (!DAGILIM.kolon) {
        govde.appendChild(elYap("div", "dag-not", "Dağılımını görmek istediğiniz değişkeni seçin."));
        return;
    }
    const anahtar = DAGILIM.kolon + "|" + AKTIF_SET;
    const hazir = DAGILIM.onbellek[anahtar];
    if (hazir) { dagilimGovdeCiz(govde, hazir); return; }

    govde.appendChild(elYap("div", "dag-not", "Hesaplanıyor (tüm satırlar)…"));
    dagilimGetir(DAGILIM.kolon, AKTIF_SET)
        .then(d => {
            if (!hala()) return;
            if (!d || d.tamam !== true || !d.dagilim) {
                govde.innerHTML = "";
                govde.appendChild(elYap("div", "dag-not dag-hata",
                    tireSade((d && (d.hata || d.metin)) || "Dağılım hesaplanamadı.")));
                return;
            }
            DAGILIM.onbellek[anahtar] = d;
            govde.innerHTML = "";
            dagilimGovdeCiz(govde, d);
        })
        .catch(e => { if (hala()) { govde.innerHTML = ""; govde.appendChild(elYap("div", "dag-not dag-hata", "Dağılım hesaplanamadı: " + e)); } });
}

function dagSatir(kap, etiket, deger) {
    const r = elYap("div", "dag-satir");
    r.appendChild(elYap("span", "dag-etiket", etiket));
    r.appendChild(elYap("span", "dag-deger", deger));
    kap.appendChild(r);
}

function dagKart(baslik) {
    const k = elYap("div", "dag-kart");
    k.appendChild(elYap("div", "dag-kart-bas", baslik));
    return k;
}

/* Tek serili çubuk grafiği (SVG). Çubuklar arası 2px boşluk, üst uçlar
   yuvarlak, taban düz; eksen ve ızgara geri planda. Üzerine gelince
   değer ipucu çıkar. ogeler: [{etiket, adet}] */
function dagCubukGrafik(ogeler, altEtiketler) {
    const G = 320, Y = 132, ALT = 18;
    const kap = elYap("div", "dag-grafik");
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "0 0 " + G + " " + (Y + ALT));
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "Dağılım grafiği");
    const enCok = Math.max(1, ...ogeler.map(o => o.adet));
    const toplam = ogeler.reduce((a, o) => a + o.adet, 0) || 1;
    const aralik = 2, en = (G - aralik * (ogeler.length - 1)) / ogeler.length;
    const taban = document.createElementNS(ns, "line");
    taban.setAttribute("x1", 0); taban.setAttribute("x2", G);
    taban.setAttribute("y1", Y); taban.setAttribute("y2", Y);
    taban.setAttribute("class", "dag-eksen");
    svg.appendChild(taban);
    const ipucu = elYap("div", "dag-ipucu");
    ipucu.hidden = true;
    ogeler.forEach((o, i) => {
        const x = i * (en + aralik);
        const h = o.adet ? Math.max(2, (o.adet / enCok) * (Y - 6)) : 0;
        const r = Math.min(4, en / 2, h);
        const y = Y - h;
        if (h > 0) {
            const yol = document.createElementNS(ns, "path");
            yol.setAttribute("d", "M" + x + "," + Y + " V" + (y + r)
                + " Q" + x + "," + y + " " + (x + r) + "," + y
                + " H" + (x + en - r) + " Q" + (x + en) + "," + y + " " + (x + en) + "," + (y + r)
                + " V" + Y + " Z");
            yol.setAttribute("class", "dag-cubuk");
            svg.appendChild(yol);
        }
        /* Vuruş alanı çubuktan büyük: tüm sütun yüksekliği. */
        const alan = document.createElementNS(ns, "rect");
        alan.setAttribute("x", x); alan.setAttribute("y", 0);
        alan.setAttribute("width", en + aralik); alan.setAttribute("height", Y);
        alan.setAttribute("class", "dag-vurus");
        alan.addEventListener("mouseenter", () => {
            ipucu.textContent = o.etiket + ": " + dagSayi(o.adet) + " satır ("
                + dagSayi(Math.round(1000 * o.adet / toplam) / 10) + "%)";
            ipucu.hidden = false;
            /* İpucu grafik kutusunun içinde kalır (kenardaki çubukta
               panelin dışına taşmasın). */
            const kg = kap.clientWidth, iw = ipucu.offsetWidth;
            const merkez = ((x + en / 2) / G) * kg;
            ipucu.style.left = Math.max(0, Math.min(kg - iw, merkez - iw / 2)) + "px";
        });
        alan.addEventListener("mouseleave", () => { ipucu.hidden = true; });
        svg.appendChild(alan);
    });
    (altEtiketler || []).forEach(([konum, metin]) => {
        const t = document.createElementNS(ns, "text");
        t.setAttribute("x", konum === "sol" ? 0 : G);
        t.setAttribute("y", Y + 13);
        t.setAttribute("text-anchor", konum === "sol" ? "start" : "end");
        t.setAttribute("class", "dag-eksen-yazi");
        t.textContent = metin;
        svg.appendChild(t);
    });
    kap.appendChild(svg);
    kap.appendChild(ipucu);
    return kap;
}

function dagilimGovdeCiz(govde, d) {
    const g = d.dagilim || {};
    if (d.set_notu) govde.appendChild(elYap("div", "dag-not", tireSade(d.set_notu)));

    const ozet = elYap("div", "dag-ozet");
    [["Satır", dagSayi(g.n)], ["Boş Oranı", ftOran(g.bos_oran)],
     ["Farklı Değer", dagSayi(g.tekil)], ["Tip", tireSade(g.tip || "")]]
        .forEach(([e, v]) => {
            const t = elYap("div", "dag-tile");
            t.appendChild(elYap("div", "dag-tile-deger", v));
            t.appendChild(elYap("div", "dag-tile-etiket", e));
            ozet.appendChild(t);
        });
    govde.appendChild(ozet);

    if (g.tip === "sayısal" && g.histogram) {
        const k = dagKart("Histogram");
        const ogeler = g.histogram.map(h => ({
            etiket: h.etiket !== undefined ? h.etiket : (dagSayi(h.alt) + " – " + dagSayi(h.ust)),
            adet: h.adet }));
        const ilk = g.histogram[0], son = g.histogram[g.histogram.length - 1];
        const alt = g.histogram_tur === "deger"
            ? [["sol", ilk.etiket], ["sag", son.etiket]]
            : [["sol", dagSayi(ilk.alt)], ["sag", dagSayi(son.ust)]];
        k.appendChild(dagCubukGrafik(ogeler, alt));
        if (g.histogram_disari)
            k.appendChild(elYap("div", "dag-not",
                "Grafik %1–%99 aralığını gösterir; bu aralığın dışında "
                + dagSayi(g.histogram_disari) + " değer var."));
        govde.appendChild(k);

        const y = g.yuzdelik || {};
        const kY = dagKart("Yüzdelik");
        [["Min", y.min], ["%1", y.p1], ["%25", y.p25], ["Medyan", y.medyan],
         ["%75", y.p75], ["%99", y.p99], ["Maks", y.maks], ["Ortalama", g.ortalama]]
            .forEach(([e, v]) => dagSatir(kY, e, dagSayi(v)));
        govde.appendChild(kY);

        const a = g.aykiri || {}, b = g.budama || {};
        const kA = dagKart("Aykırı Değer");
        dagSatir(kA, "IQR Dışı Oran", ftOran(a.oran) + " (" + dagSayi(a.adet) + " değer)");
        dagSatir(kA, "IQR Sınırları", dagSayi(a.alt_sinir) + " / " + dagSayi(a.ust_sinir));
        dagSatir(kA, "Budama Önerisi (%1–%99)", dagSayi(b.alt) + " / " + dagSayi(b.ust));
        dagSatir(kA, "Budamadan Etkilenen", ftOran(b.oran) + " (" + dagSayi(b.adet) + " değer)");
        govde.appendChild(kA);
    } else if (g.kategoriler) {
        const k = dagKart("En Sık Değerler");
        const toplam = (g.n || 0) - (g.bos || 0);
        g.kategoriler.forEach(c => {
            const r = elYap("div", "dag-kat");
            const ust = elYap("div", "dag-kat-ust");
            ust.appendChild(elYap("span", "dag-kat-ad", c.etiket));
            ust.appendChild(elYap("span", "dag-kat-sayi",
                dagSayi(c.adet) + " · " + ftOran(toplam ? c.adet / toplam : 0)));
            r.appendChild(ust);
            const cubuk = elYap("div", "dag-kat-cubuk");
            const dolu = elYap("div", "dag-kat-dolu");
            dolu.style.width = (toplam ? 100 * c.adet / toplam : 0) + "%";
            cubuk.appendChild(dolu);
            r.appendChild(cubuk);
            r.title = c.etiket + ": " + dagSayi(c.adet) + " satır";
            k.appendChild(r);
        });
        if (g.diger) dagSatir(k, "Diğer (" + dagSayi(g.diger_kategori) + " değer)",
                              dagSayi(g.diger) + " satır");
        govde.appendChild(k);
    } else {
        govde.appendChild(elYap("div", "dag-not", "Bu değişkende dolu değer yok."));
    }
}

function analizGuncelle(veri) {
    if (!veri) return;
    ANALIZ_VERI = veri;
    /* Bölme uygulandıysa sohbetteki bölme kartının çubuğu setlerin
       GERÇEK hedef oranlarını yazsın (yalnızca bu iki alan alınır;
       kullanıcının taslağına dokunulmaz). */
    const bf = veri.bolme && veri.bolme.bolme_formu;
    if (bf && BF.veri && BOLME.govde && BOLME.govde.isConnected) {
        BF.veri.set_hedef_oran = bf.set_hedef_oran || {};
        if (bf.segment !== undefined) BF.veri.segment = bf.segment;
        if (bf.hedef_orani !== undefined) BF.veri.hedef_orani = bf.hedef_orani;
        bolmeGovdeTazele();
    }
    /* Veri değişmiş olabilir (süreç dışı, tip dönüşümü, bölme): dağılım
       önbelleği boşalır; sekme açıksa yeniden istenir. */
    dagilimSifirla();
    aralikSifirla();
    // Acik sekme backend verisine bagliysa yeniden ciz
    if (BAGLI_SEKMELER.indexOf(aktifAnalizSekme) !== -1)
        analizCiz(aktifAnalizSekme);
}

/* Sekmeyi disaridan ac: ust seritteki tiklanabilir kartlar bunu cagirir.
   Sekme dugmesinin kendi onclick'ini tekrarlamak yerine tek yerden
   yonetiliyor; aksi halde "aktif" sinifi iki yerde ayri ayri
   ayarlaniyor ve biri unutuluyor. */
function analizSekmeAc(tab) {
    const hedef = Array.from(analizSekme).find(x => x.dataset.tab === tab);
    if (!hedef) return;
    analizSekme.forEach(x => x.classList.toggle("aktif", x === hedef));
    analizCiz(tab);
    /* Dar ekranda analiz paneli cekmece: kart tiklandiysa acilsin,
       yoksa hicbir sey olmuyormus gibi gorunuyor. */
    const panel = document.getElementById("analiz-panel");
    if (panel && getComputedStyle(panel).position === "fixed")
        panel.classList.add("acik");
}

/* ---- Panel genisligi SABIT ----
   Suruklenebilir tutamaklar KALDIRILDI (kullanici istegi): iki panel de
   CSS'teki clamp() degerinde duruyor. Degisken teyit tablosu varsayilan
   genislige zaten sigiyor (bkz. --ft-en), yani surukleme artik hicbir
   ekranda gerekli degil. */

/* ---- Sözlük teyidi: panelin altindaki ikinci birincil dugme ----
   SOZLESME7 §6: ayni dugme hem sohbetteki kartta hem panelin altinda
   duruyor; biri basilinca ikisi de kilitlenir. Iki ayri DOM dugmesi ama
   TEK karar. */
const analizAltEl   = document.getElementById("analiz-alt");
const analizTeyitEl = document.getElementById("analiz-teyit");

const TEYIT = {
    dugmeler: [],        // sohbet karti + panel dugmesi
    gonderildi: false,
    gonder: null         // tiklaninca calisan tek fonksiyon
};

function teyitKilitle(durum) {
    TEYIT.dugmeler.forEach(b => { if (b) b.disabled = durum; });
}

/* Sağ paneldeki ikiz "Teyit Et" düğmesi ARTIK ÇİZİLMİYOR (kullanıcı
   kararı): "sözlük teyidi sağ panelden değil sohbet sekmesinden
   yapılmalı, sağ blok sadece açıklama vermeli". Düğme, teyit kararı
   sağ panelde verilirken anlamlıydı; karar sohbet bloğuna taşınınca
   aynı ekranda iki ayrı yerde duran iki onay düğmesi kaldı ve hangisinin
   ne yaptığı belirsizleşti.

   TEYIT kaydı duruyor: sohbet kartı kendi düğmesini oraya bağlıyor ve
   adım geçince temizliyor. Yalnızca panel düğmesi listeden çıktı. */
function teyitPanelGuncelle(alan, bekleyen) {
    if (analizAltEl) analizAltEl.hidden = true;
    if (bekleyen === undefined) return;        // hata yanitinda durumu koru
    const acik = !!(alan && alan.tip === "teyit" && bekleyen === "girdi");
    if (!acik) {
        /* Adim gecti: dugme kaydi artik hicbir karari temsil etmiyor. */
        TEYIT.dugmeler = [];
        TEYIT.gonder = null;
        TEYIT.gonderildi = false;
    }
}

/* İkiz düğmenin tıklama bağlantısı da KALDIRILDI: şerit hiç açılmıyor,
   ama bağlantı dursaydı görünmeyen bir düğme hâlâ adımı ilerletebilir
   hâlde kalırdı (betikten, erişilebilirlik aracından veya ileride şeridi
   yanlışlıkla açan bir değişiklikten sonra). */

analizSekme.forEach(s => {
    const bagli = BAGLI_SEKMELER.indexOf(s.dataset.tab) !== -1;
    if (!bagli) {
        s.classList.add("hazir-degil");
        s.title = "Hazırlanıyor - bu sekmenin verisi henüz bağlı değil";
    }
    s.onclick = () => analizSekmeAc(s.dataset.tab);
});
analizCiz("ozet");


/* ==================== Metin biçimlendirme ==================== */
/* Balon metni once HTML'den arindirilir (guvenlik), sonra yalnizca
   **kalin** isaretleri <strong>'a cevrilir. */
function htmlKacir(s) {
    return String(s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

/* Girintili "  Etiket : Değer" satırları bir ÇIKTI LİSTESİ'dir, düz
   metin değil: arka uç bir adımın sonucunu böyle yazıyor (kaydedilen
   tablo yolları, birleştirme sayıları, model özeti...). Boşlukla
   hizalanmış metin olarak basılınca sütunlar font genişliğine bağlı
   kalıyor, uzun dosya yolları sarıldığında hizalama tamamen bozuluyor
   ve blok "terminal çıktısı" gibi duruyordu (kullanıcı kararı: "daha
   düzgün bir tasarımda oluşturulmalı").

   Etiket-değer ızgarası hem hizayı garanti ediyor hem de uzun yolların
   kendi hücresinde sarılmasına izin veriyor. Girintili ama İKİ NOKTASI
   OLMAYAN satır, bir önceki değerin ALT SATIRIDIR (ör. "3.000 satır ×
   42 kolon"); o da aynı hücreye giriyor. */
const CIKTI_SATIRI = /^ {2,}(\S[^:]*?)\s*:\s*(.*)$/;
const CIKTI_DEVAM  = /^ {2,}(\S.*)$/;

function ciktiSatirlariBicimle(satirlar) {
    let html = '<div class="metin-cikti">';
    satirlar.forEach(x => {
        if (x.devam) {
            html += '<span class="cikti-ad"></span><span class="cikti-deger">'
                 + x.deger + "</span>";
        } else {
            html += '<span class="cikti-ad">' + x.ad
                 + '</span><span class="cikti-deger">' + x.deger + "</span>";
        }
    });
    return html + "</div>";
}

function metinBicimle(metin) {
    const kacan = htmlKacir(metin || "");
    const kalin = (x) => x.replace(/\*\*([^*\n][^*]*?)\*\*/g, "<strong>$1</strong>");

    const satirlar = kacan.split("\n");
    let cikti = "";
    let kume = [];
    const kumeyiBas = () => {
        if (!kume.length) return;
        cikti += ciktiSatirlariBicimle(kume);
        kume = [];
    };
    /* Izgaranın kendi üst/alt boşluğu var: hemen ardından gelen TEK boş
       satır yutuluyor, yoksa metinle liste arasında iki kat boşluk
       kalıyordu. */
    let yeniKapandi = false;
    satirlar.forEach((satir, i) => {
        const e = CIKTI_SATIRI.exec(satir);
        if (e) {
            /* Izgaranın ÜSTÜNDEKİ tek boş satır da yutuluyor: arka uç
               metinle listeyi boş satırla ayırıyor, ızgaranın kendi üst
               boşluğuyla üst üste binince iki kat aralık oluyordu. */
            if (!kume.length) cikti = cikti.replace(/\n$/, "");
            kume.push({ ad: kalin(e[1]), deger: kalin(e[2]) });
            yeniKapandi = false;
            return;
        }
        /* Devam satırı YALNIZCA bir çıktı listesi açıkken: tek başına
           girintili bir cümle normal metindir. */
        const d = kume.length ? CIKTI_DEVAM.exec(satir) : null;
        if (d) { kume.push({ devam: true, deger: kalin(d[1]) }); return; }
        if (kume.length) { kumeyiBas(); yeniKapandi = true; }
        if (yeniKapandi && satir === "") { yeniKapandi = false; return; }
        yeniKapandi = false;
        cikti += kalin(satir) + (i < satirlar.length - 1 ? "\n" : "");
    });
    kumeyiBas();
    return cikti;
}


/* ==================== Balon kurucu ==================== */
/* Bot balonu bir "balon-sutun" kutusunun icinde durur. Secenek kartlari
   da ayni kutuya eklenir; boylece kartlar balonun genisligini alir.

   AVATAR GERI GELDI (kullanici istegi): akisi ilerleten tarafin bir
   robot oldugu gorunur olsun. Bir kez kaldirilmisti, cunku o zaman
   balonlar --balon-en kadardi ve avatarin actigi 32px'lik girinti iki
   tarafi ortaya dogru itiyordu. Artik bloklar SUTUNUN TAMAMINI
   kapliyor ve her iki tarafta da avatar var; genislik farki kalmadi.

   Gorsel YUKLENMEZSE (folder'da yok, ag hatasi) <img> kendini gizler:
   kirik resim ikonu, olmayan bir seyin yerini tutmaktan kotudur. */
/* ROBOT GÖRSELLERİ (kullanıcı kararı): sohbetteki İLK robot (karşılama)
   el sallayan görsel, normal konuşmada konuşan görsel, arkada iş
   sürerken düşünen görsel (bkz. calismaGostergesi). */
function avatarYap(rol) {
    const img = document.createElement("img");
    img.className = "balon-avatar " + rol;
    const ilk = rol === "bot" && !sohbetEl.querySelector(".balon-avatar.bot");
    img.src = rol === "bot" ? (ilk ? GORSEL.karsilama : GORSEL.bot) : GORSEL.user;
    if (ilk) img.classList.add("karsilama");
    img.alt = "";                 // dekoratif: ekran okuyucu atlasin
    img.setAttribute("aria-hidden", "true");
    img.onerror = () => { img.style.display = "none"; };
    return img;
}
/* ---- Blok başlığı: solda adım adı, SAĞ ÜSTTE "Geri Dön" ----
   Onay düğmeleri sohbetin ALTINDAKI ortak şeritten blokların İÇİNE
   taşındı. Ortak şerit her zaman ekranın en altındaydı: kullanıcı
   transkriptte yukarı çıkıp üç adım önceki bloğu okurken düğmeler
   görüş alanından çıkıyor, hangi bloğa ait oldukları da belirsiz
   kalıyordu. Şimdi her blok kendi kararını taşıyor.

   GERİ DÖN NEDEN BAŞLIKTA: bir eylem değil, bir NAVİGASYON. Onayla
   ve Değiştir bu bloğa ait kararlar, aşağıda dururlar; Geri Dön
   bloktan ÇIKIP o adıma döner, o yüzden başlık hizasında. */
/* "Geri Dön": o adıma DOĞRUDAN döner. Hem blok başlığında hem de
   gruplu blokların alt başlıklarında aynı düğme kullanılıyor. */
function geriDugmesiYap(b) {
    const geri = document.createElement("button");
    geri.type = "button";
    geri.className = "blok-geri";
    /* ← oku: düğmenin ne yaptığı okumadan da anlaşılsın. */
    geri.appendChild(elYap("span", "geri-ok", "←"));
    geri.appendChild(elYap("span", "", "Geri Dön"));
    geri.title = "\"" + tireSade(b.baslik || "") + "\" adımına dön";
    geri.onclick = () => {
        if (mesgul) return;
        /* Adım anahtarı govdede gider; backend YALNIZCA geriye
           atlar (bkz. akis_sohbet._hedefe_don). Serbest metin
           "geri dön" tek adım geri gidiyor, bu doğrudan o adıma.
           AYRAÇ BASILMIYOR: transkript geri sarılacak, o ayraç da
           silinecek satırların arasında kalırdı. */
        gonder("geri dön", false, { adim: b.adim });
    };
    return geri;
}

/* Kartın kendi başlığı ÇİZİLSİN Mİ?
   Her adım bloğu zaten üstünde adımın adını taşıyor (blokBasligiEkle).
   Kart da aynı adı yazınca adım adı iki
   kez tekrar ediyordu. Gruplu blokta ad alt başlıkta duruyor, tekli
   blokta blok başlığında; ikisinde de kart başlığı fazlalık. Bu yüzden
   kart başlığı YALNIZCA bloğun başlığından farklıysa çiziliyor —
   sohbet dışında (blok yokken) kart tek başına durduğu için yazılır. */
function kartBasligiGerekli(alan, blok) {
    if (!blok) return true;
    if (blok.grup) return false;
    const kartAd = ftSade(tireSade((alan && alan.baslik) || ""));
    const blokAd = ftSade(tireSade(blok.baslik || ""));
    return !kartAd || kartAd !== blokAd;
}

function blokBasligiEkle(kap, blok) {
    const b = blok || {};
    if (!b.adim && !b.baslik) return null;

    const bas = elYap("div", "blok-bas");
    /* AVATAR BURADA, balonYap'ta değil: başlık satırını kartlar
       (doğrulama, teyit, form) da kullanıyor. Avatar yalnızca balon
       tarafına eklenince kartlar avatarsız kalıyordu, oysa adımı
       yürüten asistan orada da aynı asistan. */
    bas.appendChild(avatarYap("bot"));
    const konum = b.kod === undefined ? adimKonumu(b.adim) : null;
    bas.appendChild(elYap("span", "blok-ad",
                          numarali(b.kod !== undefined ? b.kod : (konum ? konum.kod : ""),
                                   b.baslik)));
    /* Durum rozetinin yuvası - gruplu bloktaki .alt-bas ile AYNI sınıf.
       Kart kendi başlığını artık çizmediği için ("✓ Girdiler Onaylandı")
       rozetin gidecek bir yeri olmalı; boşken CSS onu gizliyor. */
    bas.appendChild(elYap("span", "alt-rozet"));

    /* ADIM ANAHTARI KABIN ÜZERİNDE: geri dönüşte transkript bu
       işaretten kırpılıyor (bkz. transkriptiKirp). Kart da blok da
       aynı işareti taşımalı, ikisi de birer adım bloğu. */
    if (b.adim) kap.dataset.adim = b.adim;

    /* HER BLOKTA GERİ DÖN, ilk adım dahil. Eskiden adım 0'da
       çizilmiyordu ve "Çalışma Başlangıcı"na dönmenin yolu kalmıyordu;
       oysa oraya dönmek çalışma modunu değiştirmek demek. */
    if (b.adim && b.geri !== false) bas.appendChild(geriDugmesiYap(b));
    kap.appendChild(bas);
    return bas;
}

/* ---- Geri dönüşte transkripti GERİ SAR ----
   Kullanıcı "Veri ve Sözlük" adımına dönünce eskiden o adımın bloğu
   sohbetin EN ALTINA yeniden ekleniyordu: sonraki adımların blokları
   (modelleme tanımları, sözlük teyidi, bölme) yerinde
   kalıyor, dönülen adım ise onların ALTINDA beliriyordu. Ekran "en son
   burada kaldın" demeyi bırakıp yanlış bir sıra gösteriyordu.

   KIRPMA ADIM SIRASINA GÖRE, blok bulmaya göre DEĞİL. İlk denemede
   hedef adımın kendi bloğu aranıyordu; ama "kurulum" ve "tanımlar" gibi
   adımlar bilerek metin döndürmüyor (karar kartın içinde) ve F5 sonrası
   transkriptte hiç blok bırakmıyorlar. Blok aranınca hedef bulunamıyor,
   hiçbir şey silinmiyordu. Artık sıra numarası karşılaştırılıyor:
   hedefe EŞİT ya da ondan SONRAKİ ilk blok ve sonrası siliniyor. */
function adimSirasiHaritasi() {
    const harita = {};
    (FAZLAR || []).forEach(f => (f.adimlar || []).forEach(a => {
        if (a.anahtar !== undefined) harita[a.anahtar] = a.sira;
    }));
    return harita;
}

function transkriptiKirp(adim) {
    const harita = adimSirasiHaritasi();
    const hedef = harita[adim];
    if (hedef === undefined) return false;

    /* GRUPLU BLOKTA KIRPMA ALT BÖLÜM DÜZEYİNDE. Üç adım tek blokta
       duruyor; "Modelleme Tanımları"na dönünce o bloğun tamamını silmek
       "Veri Seti ve Değişken Sözlüğü" seçimini de ekrandan kaldırırdı.
       Önce hedefin kendisi ve sonrası olan alt bölümler silinir; blokta
       hiç alt bölüm kalmazsa satırın tamamı aşağıdaki döngüde gider. */
    Array.from(sohbetEl.querySelectorAll(".adim-blok.gruplu")).forEach(kok => {
        const bolumler = Array.from(kok.querySelectorAll(".alt-bolum"));
        let kalan = 0;
        bolumler.forEach(b => {
            const sira = harita[b.dataset.adim];
            if (sira !== undefined && sira >= hedef) b.remove();
            else kalan++;
        });
        if (kalan) {
            // Kökün adım işareti artık KALAN son alt bölümündür; aksi
            // halde satır düzeyi döngü bu bloğu da silerdi.
            const son = kok.querySelectorAll(".alt-bolum");
            kok.dataset.adim = son.length ? son[son.length - 1].dataset.adim : "";
        } else {
            kok.dataset.adim = "";            // bos blok: satir silinecek
        }
    });

    const cocuklar = Array.from(sohbetEl.children);
    let kesim = -1;
    for (let i = 0; i < cocuklar.length; i++) {
        const kokBlok = cocuklar[i].matches(".adim-blok.gruplu")
            ? cocuklar[i] : cocuklar[i].querySelector(".adim-blok.gruplu");
        if (kokBlok && !kokBlok.querySelectorAll(".alt-bolum").length) {
            kesim = i; break;                 // ici bosalmis gruplu blok
        }
        const isaretli = cocuklar[i].matches("[data-adim]")
            ? cocuklar[i]
            : cocuklar[i].querySelector("[data-adim]");
        if (!isaretli || !isaretli.dataset.adim) continue;
        const sira = harita[isaretli.dataset.adim];
        if (sira !== undefined && sira >= hedef) { kesim = i; break; }
    }
    if (kesim === -1) return false;          // hedef zaten en yeni adım

    /* KESİM NOKTASININ ÜSTÜNE DOKUNULMAZ.
       Önce buradan geriye doğru kullanıcı satırları da siliniyordu
       ("o adıma verilen girdiler" varsayımıyla). Ama bir kullanıcı
       satırının HANGİ adıma ait olduğu DOM'da yazmıyor: ölçümde,
       "Bölme Stratejisi" adımına dönerken önceki iki adımın kullanıcı
       mesajları da silindi. Artık yalnızca hedef adımın bloğundan
       İTİBAREN siliniyor; üstü kullanıcının geçmişi olarak kalıyor.
       (Form ve kart gönderimleri zaten sessiz, yani pratikte kesim
       noktasının üstünde kullanıcı satırı çok az oluyor.) */

    for (let i = cocuklar.length - 1; i >= kesim; i--) {
        sohbetEl.removeChild(cocuklar[i]);
    }
    return true;
}

/* Bloğun ALT düğmeleri: Onayla ve Uygula + Değiştir. Yalnızca plan
   onayı bekleyen (kendi formu olmayan) bloklarda çizilir. */
function blokOnayEkle(kap) {
    if (!kap) return null;              // kap yoksa dugme de yok
    const satir = elYap("div", "blok-dugmeler");

    const onay = document.createElement("button");
    onay.type = "button";
    onay.className = "aksiyon onayla";
    onay.textContent = "Onayla ve Uygula";
    onay.onclick = () => {
        if (mesgul) return;
        satir.remove();                 // karar verildi: düğmeler kalkar
        /* Kullanıcı balonu BASILMAZ (etiket false): bir cümle yazmadı,
           bir düğmeye bastı. Yerine ince bir ayraç satırı düşer. */
        const iz = aksiyonIziEkle(AKSIYON_IZLERI.onayla);
        geriAlKilit = () => { iz.remove(); kap.appendChild(satir); };
        gonder("onay", false);
    };

    const degistir = document.createElement("button");
    degistir.type = "button";
    degistir.className = "aksiyon degistir";
    degistir.textContent = "Değiştir";
    degistir.onclick = () => {
        if (mesgul) return;
        satir.remove();
        /* "DEĞİŞTİR" = AYNI ADIMA DÖNÜŞ, Geri Dön ile aynı yol.
           Düz bir "hayır" mesajı olarak gidince adım yeniden açılıyor
           ama transkriptte AYNI BAŞLIKLI ikinci bir blok beliriyordu,
           araya da "Değiştir seçildi" ayracı giriyordu. Adım anahtarı
           gövdede gidince hem arka uç hem ön yüz o adımdan geri sarıyor:
           tek blok kalıyor ve yeni hâliyle yeniden doluyor. */
        const adim = (kap && kap.dataset) ? kap.dataset.adim : "";
        if (adim) {
            gonder("hayır", false, { adim: adim });
            return;
        }
        const iz = aksiyonIziEkle(AKSIYON_IZLERI.degistir);
        geriAlKilit = () => { iz.remove(); kap.appendChild(satir); };
        gonder("hayır", false);
    };

    satir.appendChild(onay);
    satir.appendChild(degistir);
    kap.appendChild(satir);
    return satir;
}

function balonIcerikYap(rol, metin, hataMi) {
    const balon = document.createElement("div");
    balon.className = "balon" + (hataMi ? " hata" : "");
    if (rol === "bot" && !hataMi) {
        balon.innerHTML = metinBicimle(tireSade(metin));
    } else if (hataMi) {
        balon.textContent = tireSade(metin);
    } else {
        balon.textContent = metin;          // kullanicinin yazdigi aynen kalir
    }
    return balon;
}

/* ---- ADIM BLOĞU: bir adımın BÜTÜN ekranları TEK çerçevede ----
   İş akışı adım adım ilerliyor ve ekran da adım adım gruplanıyor. Ama
   bir adım birden fazla ekran üretebiliyor: "Veri ve Sözlük" önce
   seçim formunu, sonra girdi doğrulama kartını gösteriyor. İkisi ayrı
   blok olarak çizilince ekranda üst üste AYNI başlıklı ("VERİ VE
   SÖZLÜK") ve aynı Geri Dön'ü taşıyan iki kutu duruyordu; adım
   tekrarlanmış gibi görünüyordu.

   Bu fonksiyon o adımın AÇIK kabını döndürür: sohbetin en altındaki
   blok aynı adıma aitse ona eklenir, değilse yeni blok kurulur.
   Başlık ve Geri Dön kabın kendisinde durur, içine giren kartlarda
   değil (bkz. style.css: .adim-blok > .secim-kart çerçevesizdir). */
/* ---- GRUPLU BLOK ----
   Ardışık adımlar (veri seti seçimi → modelleme tanımları → sözlük
   tanımları) sohbette TEK blok olarak görünür. Blok başlığı GRUP adını
   ("Veri ve Sözlük") taşır; her adım bloğun içinde kendi ALT BAŞLIĞINI
   ve kendi "Geri Dön" düğmesini taşır. Sol paneldeki iş akışında
   adımlar AYRI kalır, yani yalnızca modelleme tanımlarına dönmek
   mümkün. Gruplama GÖRSELDİR: adım sırası ve geri dönüş hedefi
   değişmez. */
function grupKabiAl(blok) {
    const son = sohbetEl.lastElementChild;
    let kok = null;
    if (son) {
        const ic = son.classList && son.classList.contains("adim-blok")
            ? son : son.querySelector(".adim-blok");
        if (ic && ic.dataset.grup === blok.grup) kok = ic;
    }
    const konum = adimKonumu(blok.adim);
    if (!kok) {
        fazAyraclariniEkle(blok.adim);
        const satir = elYap("div", "satir bot");
        kok = elYap("div", "balon-sutun adim-blok gruplu");
        kok.dataset.grup = blok.grup;
        /* Grup başlığında Geri Dön YOK: hangi adıma dönüleceği belirsiz
           olurdu. Düğmeler alt başlıklarda, adım adım. */
        blokBasligiEkle(kok, { baslik: blok.grup_baslik || "", geri: false,
                               kod: konum ? konum.kod : "" });
        satir.appendChild(kok);
        sohbetEl.appendChild(satir);
    }

    let bolum = null;
    const bolumler = kok.querySelectorAll(".alt-bolum");
    for (let i = 0; i < bolumler.length; i++) {
        if (bolumler[i].dataset.adim === blok.adim) bolum = bolumler[i];
    }
    if (!bolum) {
        bolum = elYap("div", "alt-bolum");
        bolum.dataset.adim = blok.adim;
        const bas = elYap("div", "alt-bas");
        bas.appendChild(elYap("span", "alt-ad",
                              numarali(konum ? konum.altKod : "", blok.baslik)));
        /* ROZET YUVASI: kartın "✓ Girdiler Onaylandı" göstergesi buraya
           taşınıyor. Kartın kendi başlık satırında kalınca alt başlık
           ile gövde metni arasında koca bir boşluk oluşuyordu; rozet
           tek başına bir satır kaplıyordu. */
        bas.appendChild(elYap("span", "alt-rozet"));
        if (blok.geri !== false) bas.appendChild(geriDugmesiYap(blok));
        bolum.appendChild(bas);
        kok.appendChild(bolum);
    }
    /* Kökün adım işareti EN SON eklenen adımdır: transkriptiKirp
       satır düzeyinde bu işarete bakıyor. */
    kok.dataset.adim = blok.adim;
    return bolum;
}

/* ---- FAZ BİTTİ AYRACI (kullanıcı kararı) ----
   Bir faz bitince sohbete ince bir çizgi ve ortasında kırmızı
   "01 Çalışma Kurulumu Tamamlandı" yazısı basılır. Yeni açılan blok
   sohbetteki son bloktan daha SONRAKİ bir faza aitse aradaki fazlar
   bitmiş demektir. Aynı kural F5'teki yeniden çizimde de çalıştığı için
   ayraç kaybolmaz. Ayraç, ardından gelen adımın işaretini taşır: o adıma
   ya da öncesine dönülünce transkriptle birlikte silinir, faz yeniden
   bitince yeniden basılır. yeniAdim yoksa (akışın sonu) son faz bitmiş
   sayılır. */
function fazAyraclariniEkle(yeniAdim) {
    const bloklar = sohbetEl.querySelectorAll(".adim-blok");
    let onceki = null;
    for (let i = bloklar.length - 1; i >= 0 && !onceki; i--) {
        onceki = adimKonumu(bloklar[i].dataset.adim);
    }
    if (!onceki) return;
    const yeni = yeniAdim ? adimKonumu(yeniAdim) : null;
    // Adım listede yoksa hiçbir faz bitmiş sayılmaz (akışın sonu değil).
    if (yeniAdim && !yeni) return;
    const hedef = yeni ? yeni.fazIdx : FAZLAR.length;
    for (let fi = onceki.fazIdx; fi < hedef; fi++) {
        if (sohbetEl.querySelector('.faz-bitti[data-faz="' + fi + '"]')) continue;
        const f = FAZLAR[fi];
        const sonraki = FAZLAR[fi + 1];
        const ayrac = elYap("div", "faz-bitti");
        ayrac.dataset.faz = String(fi);
        ayrac.dataset.adim = (sonraki && sonraki.adimlar[0])
            ? sonraki.adimlar[0].anahtar : "";
        ayrac.setAttribute("role", "separator");
        ayrac.appendChild(elYap("span", "faz-bitti-metin",
                                f.no + " " + tireSade(f.baslik) + " Tamamlandı"));
        sohbetEl.appendChild(ayrac);
    }
}

function adimKabiAl(blok) {
    if (!blok || !blok.adim) return null;
    if (blok.grup) return grupKabiAl(blok);

    const son = sohbetEl.lastElementChild;
    if (son) {
        const ic = son.classList && son.classList.contains("adim-blok")
            ? son : son.querySelector(".adim-blok");
        if (ic && !ic.dataset.grup && ic.dataset.adim === blok.adim) return ic;
    }

    fazAyraclariniEkle(blok.adim);
    const satir = elYap("div", "satir bot");
    const sutun = elYap("div", "balon-sutun adim-blok");
    sutun.dataset.adim = blok.adim;
    blokBasligiEkle(sutun, blok);
    satir.appendChild(sutun);
    sohbetEl.appendChild(satir);
    return sutun;
}

/* ---- BLOK DURUMU: BEKLENİYOR / TAMAMLANDI ----
   Kullanıcı bildirimi: bütün bloklar aynı kırmızı çerçeveyle durunca
   "şu an hangisindeyim, neyi cevaplıyorum" anlaşılmıyordu. Artık:
     - AKTİF ADIMIN bloğu (ya da gruplu blokta aktif adımın bölümü)
       kırmızı çerçeve + "● Yanıtınız Bekleniyor" etiketi,
     - geçilmiş bloklar gri çerçeve, sessiz başlık ve "✓ Tamamlandı".
   Aktif adım sol paneldeki ile AYNI kaynaktan: DUZ_ADIMLAR[aktifAdim].
   Kart kendi "✓ Girdiler Onaylandı" rozetini taşıyorsa ikinci bir
   "Tamamlandı" yazılmaz: aynı şeyi iki kez söylemesin. */
const BLOK_BEKLIYOR = "● Yanıtınız Bekleniyor";
/* YANIT VERİLDİ, SUNUCU İŞLİYOR (kullanıcı kararı): "Yanıtınız
   Bekleniyor" o sırada yanlış - yanıt zaten verildi. Blok SARI olur,
   kartın kendi rozeti boş kalır; tek etiket bu. */
const BLOK_KONTROL = "● Kontrol Ediliyor";
const BLOK_TAMAM = "✓ Tamamlandı";
/* AÇIKLAMALI ONAY (kullanıcı kararı: "Tamamlandı" neyin tamamlandığını
   söylemiyordu). Adım başına kısa, geçmiş zamanlı bir onay; listede
   olmayan adımda genel "Tamamlandı" kalır. */
const BLOK_TAMAM_METNI = {
    ham_veri: "Kaynak Tablolar Seçildi",
    kaynak_sozluk: "Kaynak Sözlükler Onaylandı",
    birlestirme: "Baz Veri Seti Oluşturuldu",
    veri_sec: "Baz Veri Seti Seçildi",
    sozluk_uret: "Baz Sözlük Oluşturuldu",
    kurulum: "Girdiler Onaylandı",
    tanimlar: "Modelleme Tanımları Onaylandı",
    sozluk_tanim: "Sözlük Tanımları Kaydedildi",
    kisaltma: "Kısaltmalar Onaylandı",
    kolon_ad: "Kolon Adları Belirlendi",
    tanim_kontrol: "Sözlük Tanımları Kontrol Edildi",
    teyit: "Değişken Listesi Kaydedildi",
    bolme: "Bölme Uygulandı",
    veri_profili: "Veri Profili Çıkarıldı",
    sfa: "Tek Değişken Analizi Yapıldı",
    stabilite: "Stabilite Ölçüldü",
    baz: "Analitik Baz Set Hazırlandı",
    kural: "Kural Tabanlı Değişkenler Üretildi",
    kesif: "AI Değişken Keşfi Yapıldı",
    kalite: "Kalite Kontrolü Yapıldı",
    secim: "Aday Değişken Seti Belirlendi",
    model: "Modeller Karşılaştırıldı",
    algoritma: "Algoritma Seçildi",
    final: "Model Finalize Edildi",
    katalog: "Değişken Kataloğu Hazırlandı"
};
function blokTamamMetni(adim) {
    if (adim === "mod")
        return "✓ " + (aktifMod ? aktifMod + " Başlangıcı Seçildi" : "Başlangıç Seçildi");
    return BLOK_TAMAM_METNI[adim] ? "✓ " + BLOK_TAMAM_METNI[adim] : BLOK_TAMAM;
}

function blokDurumEtiketi(bas, durum, adim) {
    if (!bas) return;
    let et = bas.querySelector(":scope > .blok-durum");
    const onayliRozet = durum === "tamam"
        && bas.querySelector(":scope > .alt-rozet .onayli");
    const metin = durum === "bekliyor" ? BLOK_BEKLIYOR
        : durum === "kontrol" ? BLOK_KONTROL
        : (durum === "tamam" && !onayliRozet ? blokTamamMetni(adim) : "");
    if (!metin) { if (et) et.remove(); return; }
    if (!et) {
        et = elYap("span", "blok-durum");
        const rozet = bas.querySelector(":scope > .alt-rozet");
        bas.insertBefore(et, rozet || bas.querySelector(":scope > .blok-geri"));
    }
    if (et.textContent !== metin) et.textContent = metin;
    et.classList.toggle("bekliyor", durum === "bekliyor");
    et.classList.toggle("kontrol", durum === "kontrol");
    et.classList.toggle("tamam", durum === "tamam");
}

function sinifAyarla(el, durum) {
    /* Çerçeve kontrol sırasında da KIRMIZI kalır (kullanıcı kararı);
       sarı yalnızca başlıktaki "Kontrol Ediliyor" etiketi. */
    el.classList.toggle("durum-bekliyor", durum === "bekliyor" || durum === "kontrol");
    el.classList.toggle("durum-tamam", durum === "tamam");
}

function blokDurumlariniTazele() {
    const aktif = (DUZ_ADIMLAR[aktifAdim] || {}).anahtar || "";
    /* Akışın sonu: son adım da geçildiyse son faz bitti. Yalnızca
       sohbetin son bloğu son fazdaysa (yeniden çizim sürerken erken
       basılmasın). */
    if (DUZ_ADIMLAR.length && aktifAdim >= DUZ_ADIMLAR.length) {
        const bloklar = sohbetEl.querySelectorAll(".adim-blok");
        const son = bloklar.length ? adimKonumu(bloklar[bloklar.length - 1].dataset.adim) : null;
        if (son && son.fazIdx === FAZLAR.length - 1) fazAyraclariniEkle(null);
    }
    /* İstek uçuştayken aktif adım "kontrol" (sarı), değilse "bekliyor". */
    const aktifDurum = mesgul ? "kontrol" : "bekliyor";
    sohbetEl.querySelectorAll(".adim-blok").forEach(blok => {
        if (blok.classList.contains("gruplu")) {
            let bekliyorVar = false;
            blok.querySelectorAll(":scope > .alt-bolum").forEach(bolum => {
                const durum = bolum.dataset.adim === aktif ? aktifDurum : "tamam";
                if (durum !== "tamam") bekliyorVar = durum;
                sinifAyarla(bolum, durum);
                blokDurumEtiketi(bolum.querySelector(":scope > .alt-bas"), durum,
                                 bolum.dataset.adim);
            });
            sinifAyarla(blok, bekliyorVar || "tamam");
            return;
        }
        if (!blok.dataset.adim) return;
        const durum = blok.dataset.adim === aktif ? aktifDurum : "tamam";
        sinifAyarla(blok, durum);
        blokDurumEtiketi(blok.querySelector(":scope > .blok-bas"), durum,
                         blok.dataset.adim);
    });
}

/* Sohbete her blok/kart eklenişinde bir kare sonra tazelenir: blokları
   kuran yolların hepsine (canlı yanıt, geçmişten çizim, geri dönüşte
   kırpma) tek tek çağrı serpiştirmek yerine. Yalnızca childList
   izleniyor; sınıf değişimi tetiklemez, döngü olmaz. */
let blokDurumBekleyen = false;
function blokDurumPlanla() {
    if (blokDurumBekleyen) return;
    blokDurumBekleyen = true;
    requestAnimationFrame(() => {
        blokDurumBekleyen = false;
        try { blokDurumlariniTazele(); } catch (e) { /* görsel; akışı bozmasın */ }
    });
}
if (sohbetEl && window.MutationObserver) {
    new MutationObserver(blokDurumPlanla)
        .observe(sohbetEl, { childList: true, subtree: true });
}

function balonYap(rol, metin, hataMi) {
    const satir = document.createElement("div");
    satir.className = "satir " + rol;
    const sutun = document.createElement("div");
    sutun.className = "balon-sutun";
    sutun.appendChild(balonIcerikYap(rol, metin, hataMi));
    satir.appendChild(sutun);
    return satir;
}

/* Sistem bildirimi: "Önceki çalışmanız kaldığı yerden yüklendi."
   BALON DEĞİL. Bunu asistan söylemiyor, uygulama söylüyor; bot balonu
   olarak basılınca başında robot avatarıyla duruyordu ve akışı yürüten
   asistanın bir cümlesi gibi görünüyordu. İnce, nötr bir şerit. */
function sistemNotuEkle(metin) {
    const not = elYap("div", "sistem-notu");
    not.setAttribute("role", "status");
    not.innerHTML = metinBicimle(tireSade(metin));
    sohbetEl.appendChild(not);
    sohbetKaydir();
    return not;
}

/* ==================== Otomatik kaydırma ====================
   KULLANICI KARARI: "veri geldikçe otomatik en aşağı atıyor ... işlemleri
   kendim görmek adına yukarı kaydırıyorum". Kurallar:
   - Yeni içerik gelince sohbet EN ALTA değil, YENİ İÇERİĞİN BAŞINA
     kaydırılır. Zincirleme adımlarda (02.1 çıktısı, ardından 02.2 kartı)
     ilk gelen çıktı ekranda kalır; altındakine kullanıcı kendisi iner.
   - Ekran yalnızca AŞAĞI kaydırılır, asla yukarı çekilmez.
   - Kullanıcı istek sürerken kendisi kaydırdıysa hiç kaydırılmaz.
   - Yeni bir gönderim (kart onayı, mesaj) bu durumu sıfırlar.
   Geçmiş yüklenirken (gönderim yokken) eskisi gibi en alta gider. */
const KAYDIRMA = { ilk: null, kullanici: false };

function kaydirmaBaslat() {
    KAYDIRMA.ilk = sohbetEl.scrollHeight;
    KAYDIRMA.kullanici = false;
}

function sohbetKaydir() {
    if (KAYDIRMA.kullanici) return;
    const enAlt = Math.max(sohbetEl.scrollHeight - sohbetEl.clientHeight, 0);
    const hedef = KAYDIRMA.ilk === null ? enAlt
        : Math.min(Math.max(KAYDIRMA.ilk - 24, 0), enAlt);
    if (hedef > sohbetEl.scrollTop) sohbetEl.scrollTop = hedef;
}

/* Kullanıcının kendi kaydırması: tekerlek, dokunma, klavye, kaydırma
   çubuğu. Programın yaptığı scrollTop ataması bu olayları üretmez. */
["wheel", "touchmove"].forEach(ad => sohbetEl.addEventListener(ad, () => {
    KAYDIRMA.kullanici = true;
}, { passive: true }));
sohbetEl.addEventListener("keydown", e => {
    if (["PageUp", "PageDown", "ArrowUp", "ArrowDown", "Home", "End", " "].includes(e.key)
        && !/^(INPUT|TEXTAREA|SELECT)$/.test((e.target && e.target.tagName) || ""))
        KAYDIRMA.kullanici = true;
});
sohbetEl.addEventListener("pointerdown", e => {
    if (e.target === sohbetEl) KAYDIRMA.kullanici = true;     // kaydırma çubuğu
});

function balonEkle(rol, metin, hataMi, blok) {
    /* Adım bilgisi varsa balon KENDI satirini kurmaz: o adimin acik
       blogunun icine girer. Ayni adimin ikinci ekrani ayni cerceveye
       eklensin diye (bkz. adimKabiAl). */
    const kap = (rol === "bot" && !hataMi) ? adimKabiAl(blok) : null;
    if (kap) {
        kap.appendChild(balonIcerikYap("bot", metin, false));
        if (blok && blok.onay) blokOnayEkle(kap);
        sohbetKaydir();
        return kap.parentElement;
    }
    const satir = balonYap(rol, metin, hataMi);
    sohbetEl.appendChild(satir);
    sohbetKaydir();
    return satir;
}

/* Calisan adimin adi: DUZ_ADIMLAR sira -> adim eslemesinden */
function adimAdi() {
    const a = DUZ_ADIMLAR[aktifAdim];
    return a ? tireSade(a.baslik) : "";
}

function sureBicim(sn) {
    const d = Math.floor(sn / 60);
    const s = sn % 60;
    return d + ":" + (s < 10 ? "0" : "") + s;
}

/* İŞLEM SATIRI (kullanıcı kararı): ayrı bir "yükleniyor" kartı YOK.
   Durumu başlıktaki "● Kontrol Ediliyor" etiketi anlatıyor; aktif adımın
   bloğunun EN ALTINA tek ince satır gelir: "İşlem Devam Ediyor · 0:12 · İptal".
   Satır ilk ISLEM_GECIKME_MS boyunca görünmez: kısa işlemlerde ekranda
   hiçbir şey zıplamaz, yalnızca etiket değişir. Her adımda aynı. */
const ISLEM_GECIKME_MS = 2500;

function aktifBlokKabi() {
    const aktif = (DUZ_ADIMLAR[aktifAdim] || {}).anahtar || "";
    let kap = null;
    if (aktif) {
        const hepsi = sohbetEl.querySelectorAll(
            '.alt-bolum[data-adim="' + aktif + '"], .adim-blok:not(.gruplu)[data-adim="' + aktif + '"]');
        if (hepsi.length) kap = hepsi[hepsi.length - 1];
    }
    if (!kap) {
        const bloklar = sohbetEl.querySelectorAll(".adim-blok");
        if (bloklar.length) {
            kap = bloklar[bloklar.length - 1];
            const bolumler = kap.querySelectorAll(":scope > .alt-bolum");
            if (bolumler.length) kap = bolumler[bolumler.length - 1];
        }
    }
    return kap;
}

function calismaGostergesi(iptalEt) {
    const kap = aktifBlokKabi();
    const satir = elYap("div", "islem-satiri");
    satir.setAttribute("role", "status");
    const sure = elYap("span", "islem-sure", "");
    const iptal = document.createElement("button");
    iptal.type = "button";
    iptal.className = "islem-iptal";
    iptal.textContent = "İptal";
    iptal.title = "İsteği durdur (sunucudaki işlem sürebilir)";
    iptal.onclick = () => {
        iptal.disabled = true;
        iptal.textContent = "İptal ediliyor…";
        if (iptalEt) iptalEt();
    };
    /* DÜŞÜNEN ROBOT: işlem sürerken çalışan bloğun başlığındaki robot
       geçici olarak düşünen hâle geçer. "İşlem Devam Ediyor" satırına
       görsel konmaz (kullanıcı kararı). */
    satir.append(sure, iptal);
    (kap || sohbetEl).appendChild(satir);
    const blokAvatar = kap && kap.parentElement
        ? kap.parentElement.querySelector(".balon-avatar.bot") : null;
    const eskiAvatar = blokAvatar ? blokAvatar.src : null;

    let gecen = 0;
    const yaz = () => { sure.textContent = "İşlem Devam Ediyor · " + sureBicim(gecen); };
    yaz();
    const sayac = setInterval(() => { gecen += 1; yaz(); }, 1000);
    const goster = setTimeout(() => {
        satir.classList.add("gorunur");
        if (blokAvatar && !blokAvatar.classList.contains("karsilama")) blokAvatar.src = GORSEL.dusunme;
        if (!kap) sohbetKaydir();
    }, ISLEM_GECIKME_MS);
    return {
        kaldir() {
            clearInterval(sayac);
            clearTimeout(goster);
            satir.remove();
            if (blokAvatar && eskiAvatar && blokAvatar.src !== eskiAvatar) blokAvatar.src = eskiAvatar;
        }
    };
}


/* ==================== Seçenek kartları ==================== */
/* kilit/secili: GECMISTEN yeniden cizim. Kartlar tiklanmaz, secilen
   kart isaretli kalir; adim zaten tamamlandi. */
function secenekEkle(secenekler, kilit, secili) {
    if (!secenekler || !secenekler.length) return;

    const kok = document.createElement("div");
    kok.className = "secenek-kok";

    secenekler.forEach(s => {
        const kart = document.createElement("button");
        kart.className = "secenek";
        kart.type = "button";

        const rozet = document.createElement("span");
        rozet.className = "secenek-rozet";
        /* Rozet: kart ayrica kisa bir rozet verdiyse o ("1", "2"); mod
           kartlarinda harfin kendisi. */
        rozet.textContent = s.rozet || s.deger;
        kart.appendChild(rozet);

        const govde = document.createElement("div");
        govde.className = "secenek-govde";

        const bas = document.createElement("div");
        bas.className = "secenek-baslik";
        bas.textContent = tireSade(s.baslik);
        govde.appendChild(bas);

        if (s.aciklama) {
            const ack = document.createElement("div");
            ack.className = "secenek-aciklama";
            ack.textContent = tireSade(s.aciklama);
            govde.appendChild(ack);
        }
        kart.appendChild(govde);

        /* KAPALI SEÇENEK (kullanıcı kararı: henüz açılmamış başlangıçlar
           seçilemesin). Soluk durur, tıklanamaz, sağında "Şu An Kapalı". */
        if (s.kapali) {
            kart.classList.add("kapali");
            kart.appendChild(elYap("span", "secenek-kapali", "Şu An Kapalı"));
        }

        if (kilit || s.kapali) {
            kart.disabled = true;
            if (secili && s.deger === secili) kart.classList.add("secili");
        } else {
            kart.onclick = () => {
                if (mesgul) return;
                const kartlar = Array.from(kok.querySelectorAll(".secenek"));
                // Hata olursa kart grubu ESKI ACIK haline donsun
                const onceki = kartlar.map(k => ({
                    el: k, kapali: k.disabled, secili: k.classList.contains("secili")
                }));
                kartlar.forEach(k => {
                    k.disabled = true;
                    k.classList.toggle("secili", k === kart);
                });
                geriAlKilit = () => onceki.forEach(o => {
                    o.el.disabled = o.kapali;
                    o.el.classList.toggle("secili", o.secili);
                });
                gonder(s.deger, false);      // false: kullanici balonu basma
            };
        }

        kok.appendChild(kart);
    });

    const son = sohbetEl.lastElementChild;
    const sutun = (son && son.classList.contains("bot"))
        ? son.querySelector(".balon-sutun") : null;

    if (sutun) {
        sutun.classList.add("secenekli");
        sutun.appendChild(kok);
    } else {
        sohbetEl.appendChild(kok);
    }
    sohbetKaydir();
    if (!kilit) yeniOdak = kok.querySelector(".secenek");
}


/* ==================== Dataset listesi ==================== */
fetch(getWebAppBackendUrl("datasetler"))
    .then(r => r.json())
    .then(d => {
        DATASETLER = (d && d.datasetler) || [];
        /* Bos liste ayri bir durum: hata yokken de "hazir" sayilirsa
           gecerli() daima false doner ve "Devam et" sonsuza kadar gri kalir. */
        if (d && d.hata) DATASET_DURUMU = "hata";
        else DATASET_DURUMU = DATASETLER.length ? "hazir" : "bos";
    })
    .catch(() => { DATASETLER = []; DATASET_DURUMU = "hata"; })
    .finally(() => { DATASET_DINLEYICILER.forEach(f => f()); });


/* ==================== Kolon listesi ==================== */
/* Hedef değişken / kimlik / dönem alanlari VERI SETI DEGIL, secili veri
   setinin KOLONLARINI onerir. Oncelik backend'in gonderdigi
   _secim_alani.kolonlar; o bos gelirse secili veri seti icin /kolonlar
   ucundan cekilir. Istek basarisiz olursa alan SERBEST yazmaya duser:
   kullanici engellenmez, ekranda nedeni yazar. */
let KOLONLAR = [];
let KOLON_DURUMU = "hata";      // "yukleniyor" | "hazir" | "bos" | "hata"
let KOLON_KAYNAGI = null;       // kolonlarin okundugu veri seti adi
const KOLON_DINLEYICILER = [];  // liste gelince acik formlar kendini tazeler

/* Son yanitin ozet/detay govdesi: secili veri setinin adi buradan okunur */
let SON_OZET = null;
let SON_DETAY = null;

function kolonlariDuyur() { KOLON_DINLEYICILER.forEach(f => f()); }

function doluDeger(v) {
    const s = String(v === null || v === undefined ? "" : v).trim();
    if (!s || s === BOS_SIMGE || s === "-" || s === "—" || s === "–") return "";
    return s;
}

/* Secili veri setinin adi: once ust ozet kartlari, sonra ozet sayfasi.
   Backend ayri bir alan gondermiyor; bu iki govde zaten her yanitta gelir. */
function seciliVeriSeti() {
    /* Artik acik bir alan var: ust serit veri setine ayri kart ayirmiyor,
       ad basligin yanindaki cipte duruyor. Kart taramasi yedek olarak
       kaldi - eski govdeyi donduren bir surum hala baglanabilir. */
    const cip = doluDeger(SON_OZET && SON_OZET.veri_seti_cip);
    if (cip) return cip;

    const kartlar = (SON_OZET && SON_OZET.kartlar) || [];
    for (let i = 0; i < kartlar.length; i++) {
        const etiket = String(kartlar[i].etiket || "").toLocaleLowerCase("tr-TR");
        if (etiket.indexOf("veri seti") !== -1) {
            const v = doluDeger(kartlar[i].deger);
            if (v) return v;
        }
    }
    const bolumler = (SON_DETAY && SON_DETAY.bolumler) || [];
    for (let i = 0; i < bolumler.length; i++) {
        const satirlar = bolumler[i].satirlar || [];
        for (let j = 0; j < satirlar.length; j++) {
            const ad = String(satirlar[j][0] || "").toLocaleLowerCase("tr-TR");
            if (ad.indexOf("veri seti") !== -1) {
                const v = doluDeger(satirlar[j][1]);
                if (v) return v;
            }
        }
    }
    return null;
}

/* Kolon kaynagini forma gore hazirlar. Sessizce bos birakmaz:
   kolon adi bulunamazsa durum "hata" olur ve alan serbest yazmaya duser. */
function kolonlariHazirla(alan) {
    const gelen = (alan && alan.kolonlar) || [];
    if (gelen.length) {
        KOLONLAR = gelen.slice();
        KOLON_DURUMU = "hazir";
        KOLON_KAYNAGI = seciliVeriSeti();
        kolonlariDuyur();
        return;
    }

    const veriSeti = seciliVeriSeti();
    if (!veriSeti) {
        // Hangi veri setinin kolonlari sorulacagi bilinmiyor: serbest yaz.
        KOLONLAR = [];
        KOLON_DURUMU = "hata";
        KOLON_KAYNAGI = null;
        kolonlariDuyur();
        return;
    }
    if (KOLON_KAYNAGI === veriSeti
        && (KOLON_DURUMU === "hazir" || KOLON_DURUMU === "yukleniyor")) {
        kolonlariDuyur();       // ayni veri seti icin ikinci kez cekme
        return;
    }

    KOLONLAR = [];
    KOLON_DURUMU = "yukleniyor";
    KOLON_KAYNAGI = veriSeti;
    kolonlariDuyur();

    fetch(getWebAppBackendUrl("kolonlar")
          + "?veri_seti=" + encodeURIComponent(veriSeti))
        .then(r => r.json())
        .then(d => {
            const liste = (d && d.kolonlar) || [];
            if (d && d.hata) { KOLONLAR = []; KOLON_DURUMU = "hata"; }
            else {
                KOLONLAR = liste;
                KOLON_DURUMU = liste.length ? "hazir" : "bos";
            }
        })
        .catch(() => { KOLONLAR = []; KOLON_DURUMU = "hata"; })
        .finally(() => { kolonlariDuyur(); });
}


/* ==================== Seçim formu ==================== */
/* tip "form"  : bir veya iki tekli alan (alan.deger varsa dolu acilir)
   tip "liste" : + ile ekle, − ile cikar coklu liste
   YALNIZCA listedeki veri setleri kabul edilir. Liste okunamadiysa elle
   yazmaya izin verilir; tablo varligi backend'de kontrol edilir. */

/* "SECILDI" DUGMESI YOK. Eskiden kart gonderildikten sonra birincil
   dugmenin uzerine bu yaziliyordu: bir durum bilgisi, dugme kiligindaydi
   — basilabilir gorunuyor, basilinca hicbir sey olmuyordu. Yerine baslik
   satirinin saginda .secim-durum gostergesi var (bir <span>; dugme degil,
   imleci degismez), gonderildikten sonra birincil dugme GIZLENIR. */
/* ROZETLER BAŞLIK BÜYÜK HARFİYLE (kullanıcı kararı: "Girdiler hazır"
   değil "Girdiler Hazır"). Sabit metinler burada öyle yazılı; arka
   uçtan gelen rozet metinleri rozetMetni() ile aynı biçime çevriliyor. */
/* GÖNDERİLMİŞ KART: "✓ Girdiler Onaylandı" (kullanıcı kararı; "Girdiler
   Hazır" belirsizdi: hazır ama gönderilmemiş mi, onaylanmış mı?). Rozet
   YALNIZCA gönderimden sonra çıkar; dolu ama gönderilmemiş kart "2/2
   Seçildi" der ve düğmesi durur. */
const SECIM_HAZIR = "✓ Girdiler Onaylandı";
const secimDurumMetni = (dolu, toplam) => dolu + "/" + toplam + " Seçildi";
const rozetMetni = (metin) => "✓ " + baslikBuyuk(metin);

const GECERSIZ_GOLGE = "0 0 0 var(--halka) var(--amber-halka)";
const LISTE_YUKSEKLIGI = 208;            /* .combo-liste max-height ile ayni */
let KOMBO_SAYAC = 0;

/* Combo kaynaklari. Varsayilan "dataset": mevcut davranis aynen korunur.
   "kolon": secili veri setinin kolonlari. "serbest": liste yok, elle yazilir.
   Liste okunamadiysa ya da bos dondüyse elle yazmaya izin verilir. */
const COMBO_KAYNAKLARI = {
    dataset: {
        liste: () => DATASETLER,
        durum: () => DATASET_DURUMU,
        dinleyiciler: DATASET_DINLEYICILER,
        placeholder: "Veri seti ara…",
        yukleniyor_mesaji: "Veri seti listesi yükleniyor…",
        hata_mesaji: "Veri seti listesi okunamadı - adı elle yazabilirsiniz; "
                     + "erişim, seçimden sonra kontrol edilir.",
        bos_durum_mesaji: "Bu projede veri seti bulunamadı - adı elle "
                          + "yazabilirsiniz; erişim, seçimden sonra kontrol edilir.",
        eslesme_yok: "Eşleşen veri seti yok - listeden bir veri seti seçin.",
        uyari: "Bu ad veri seti listesinde yok"
    },
    kolon: {
        liste: () => KOLONLAR,
        durum: () => KOLON_DURUMU,
        dinleyiciler: KOLON_DINLEYICILER,
        placeholder: "Kolon ara…",
        yukleniyor_mesaji: "Kolon listesi yükleniyor…",
        hata_mesaji: "Kolon listesi okunamadı - adı elle yazabilirsiniz; "
                     + "doğruluğu, seçimden sonra kontrol edilir.",
        bos_durum_mesaji: "Veri setinin kolonları okunamadı - adı elle "
                          + "yazabilirsiniz; doğruluğu, seçimden sonra kontrol edilir.",
        eslesme_yok: "Eşleşen kolon yok",
        uyari: "Bu ad veri setinin kolonları arasında yok"
    },
    serbest: {
        liste: () => [],
        durum: () => "bos",
        dinleyiciler: null,          // tazelenecek liste yok
        placeholder: "Değeri yazın…",
        yukleniyor_mesaji: "",
        hata_mesaji: "Bu alanı elle yazabilirsiniz.",
        bos_durum_mesaji: "Bu alanı elle yazabilirsiniz.",
        eslesme_yok: "",
        uyari: ""
    }
};

/* secenekler = {liste, placeholder, zorunlu, bos_mesaji, kaynak}
   liste       : disaridan sabit liste (verilmezse kaynagin canli listesi)
   placeholder : giris kutusu ipucu
   zorunlu     : false ise alan BOS birakilabilir ("Devam et" beklemez)
   bos_mesaji  : filtreye uyan oge kalmadiginda gosterilecek metin
   kaynak      : "dataset" (varsayilan) | "kolon" | "serbest" */
function comboYap(etiket, degisince, baslangic, secenekler) {
    const s = secenekler || {};
    const kaynak = COMBO_KAYNAKLARI[s.kaynak] || COMBO_KAYNAKLARI.dataset;
    const sabitListe = Array.isArray(s.liste) ? s.liste : null;
    const listeAl = sabitListe ? () => sabitListe : kaynak.liste;
    const durumAl = sabitListe
        ? () => (sabitListe.length ? "hazir" : "bos")
        : kaynak.durum;
    const zorunlu = (s.zorunlu === false) ? false : true;
    const eslesmeYok = s.bos_mesaji || kaynak.eslesme_yok;
    /* Listede GOSTERILMEYECEK adlar (ör. listeye zaten eklenmiş tablolar;
       kullanıcı bildirimi: "önceden seçtiğim tekrardan seçim kısmında
       gözüküyor"). Fonksiyon: her çizimde güncel liste okunur. */
    const haricAl = typeof s.haric === "function" ? s.haric : () => [];

    const no = ++KOMBO_SAYAC;
    const kok = document.createElement("div");
    kok.className = "combo";

    const listeId = "combo-liste-" + no;
    const girisId = "combo-giris-" + no;

    if (etiket) {
        const lbl = document.createElement("label");
        /* TEK SATIR ETİKET (kullanıcı bildirimi: "yazılar iç içe, sıra
           yamuk"). Uzun etiket iki satıra sarınca o alanın kutusu
           diğerlerinden aşağıda kalıyordu. "(İsteğe Bağlı)" küçük ve soluk
           ayrı parça; sığmazsa etiket "…" ile kısalır, tamamı ipucunda. */
        const tam = tireSade(etiket);
        const m = tam.match(/^(.*?)\s*\((İsteğe Bağlı)\)$/);
        lbl.textContent = m ? m[1] : tam;
        if (m) lbl.appendChild(elYap("span", "combo-etiket-ek", " (" + m[2] + ")"));
        lbl.title = tam;
        /* ZORUNLU ALAN: etiketin yanında kırmızı yıldız (kullanıcı kararı).
           Diğerleri isteğe bağlı; ayrıca yazılmıyor. */
        if (zorunlu) {
            const y = elYap("span", "combo-zorunlu", "*");
            y.setAttribute("aria-hidden", "true");
            lbl.appendChild(y);
            lbl.title = tam + " (zorunlu)";
        }
        lbl.htmlFor = girisId;
        kok.appendChild(lbl);
    }

    const giris = document.createElement("input");
    giris.className = "combo-giris";
    giris.id = girisId;
    giris.placeholder = s.placeholder || kaynak.placeholder;
    giris.autocomplete = "off";
    giris.value = baslangic || "";
    giris.setAttribute("role", "combobox");
    giris.setAttribute("aria-autocomplete", "list");
    giris.setAttribute("aria-expanded", "false");
    giris.setAttribute("aria-controls", listeId);
    giris.setAttribute("aria-required", zorunlu ? "true" : "false");

    /* ALAN KAPSAYICISI: giris + ok dugmesi + acilir liste.
       Ok dugmesi `bottom: 1px` ile, liste `top: 100%` ile konumlaniyor
       ve ikisi de .combo'ya gore olculuyordu. Alanin ALTINA bir aciklama
       satiri ("Yalnızca 0/1 değerli kolonlar") eklenince .combo uzadi:
       ok dugmesi o satirin hizasina kaydi, liste de onun altindan
       acilmaya basladi. Kapsayici sayesinde ikisi de ALANA gore
       konumlaniyor; aciklama disarida kaliyor ve hicbir sey kaymiyor. */
    const alanKap = document.createElement("div");
    alanKap.className = "combo-alan";
    alanKap.appendChild(giris);
    kok.appendChild(alanKap);

    /* Listeyi acip kapatan ok dugmesi. Odak listeyi actigi surece bu gereksizdi;
       artik acmanin TEK gorunur yolu bu (klavye: ArrowDown). */
    const okBtn = document.createElement("button");
    okBtn.type = "button";
    okBtn.className = "combo-ok";
    okBtn.tabIndex = -1;                 // Tab sirasini bozmasin; input yeter
    okBtn.setAttribute("aria-label", "Listeyi aç");
    okBtn.title = "Listeyi aç";
    okBtn.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14" '
        + 'fill="none" stroke="currentColor" stroke-width="2.4" '
        + 'stroke-linecap="round" stroke-linejoin="round">'
        + '<polyline points="6 9 12 15 18 9"></polyline></svg>';
    alanKap.appendChild(okBtn);

    const liste = document.createElement("ul");
    liste.className = "combo-liste";
    liste.id = listeId;
    liste.setAttribute("role", "listbox");
    alanKap.appendChild(liste);

    let ogeler = [];          // klavye ile gezilebilen li'ler
    let vurguIndeks = -1;

    function bilgiSatiri(metin) {
        const li = document.createElement("li");
        li.className = "bos";
        li.textContent = metin;
        liste.appendChild(li);
    }

    /* Listedeki adin yazim farkini duzelten arama (buyuk/kucuk harf).
       ftSade kullaniliyor: duz toLowerCase Turkce'de "I" harfini "i"
       yapiyor, yani "ISTANBUL" kolonu "ıstanbul" yazilinca bulunmuyordu.
       ftSade once Turkce harfleri ASCII'ye katliyor, iki taraf da ayni
       kurala giriyor. */
    function bul(ad) {
        const a = ftSade((ad || "").trim());
        if (!a) return null;
        return listeAl().find(x => ftSade(x) === a) || null;
    }

    function gecerli() {
        const yazi = giris.value.trim();
        /* zorunlu:false alan bos birakilabilir; "Devam et" onu beklemez */
        if (!yazi) return !zorunlu;
        const d = durumAl();
        if (d === "hazir") return bul(yazi) !== null;
        if (d === "hata" || d === "bos") return yazi.length > 1;
        return false;                   // "yukleniyor"
    }

    function deger() {
        return bul(giris.value) || giris.value.trim();
    }

    /* Yazili ama listede olmayan ad: turuncu cerceve */
    function isaretle() {
        const hatali = durumAl() === "hazir"
            && giris.value.trim() !== ""
            && bul(giris.value) === null;
        giris.style.boxShadow = hatali ? GECERSIZ_GOLGE : "";
        giris.style.borderColor = hatali ? "var(--amber)" : "";
        giris.title = hatali ? kaynak.uyari : "";
    }

    /* kaydir=false: FARE ile vurgulama listeyi KAYDIRMAZ (kullanici
       bildirimi: yukari kaydirip yarim gorunen ustteki ada gelince liste
       kendiliginden asagi kayiyor, fare baska bir adin uzerine dusuyordu).
       Yalniz klavye (ok tuslari, Home/End) vurguyu gorunur alana getirir. */
    function vurgula(i, kaydir = true) {
        vurguIndeks = i;
        ogeler.forEach((li, k) => {
            const secili = (k === i);
            li.classList.toggle("vurgu", secili);
            li.setAttribute("aria-selected", secili ? "true" : "false");
        });
        if (i >= 0 && ogeler[i]) {
            giris.setAttribute("aria-activedescendant", ogeler[i].id);
            const li = ogeler[i];
            if (!kaydir) return;
            if (li.offsetTop < liste.scrollTop) liste.scrollTop = li.offsetTop;
            else if (li.offsetTop + li.offsetHeight > liste.scrollTop + liste.clientHeight)
                liste.scrollTop = li.offsetTop + li.offsetHeight - liste.clientHeight;
        } else {
            giris.removeAttribute("aria-activedescendant");
        }
    }

    function sec(ad) {
        giris.value = ad;
        kapat();
        isaretle();
        if (degisince) degisince();
    }

    function ciz(filtre) {
        liste.innerHTML = "";
        ogeler = [];
        vurguIndeks = -1;
        giris.removeAttribute("aria-activedescendant");

        const d = durumAl();
        if (d === "yukleniyor") { bilgiSatiri(kaynak.yukleniyor_mesaji); return; }
        if (d === "hata")       { bilgiSatiri(kaynak.hata_mesaji); return; }
        if (d === "bos")        { bilgiSatiri(kaynak.bos_durum_mesaji); return; }

        const f = ftSade(filtre || "");
        const haric = new Set(haricAl().map(ftSade));
        const sonuc = listeAl()
            .filter(x => !haric.has(ftSade(x)) && ftSade(x).includes(f)).slice(0, 80);
        if (!sonuc.length) {
            bilgiSatiri(eslesmeYok);
            return;
        }
        sonuc.forEach((x, i) => {
            const ad = String(x);
            const li = document.createElement("li");
            li.textContent = ad;
            li.id = listeId + "-" + i;
            li.setAttribute("role", "option");
            li.setAttribute("aria-selected", "false");
            li.onmousedown = e => { e.preventDefault(); sec(ad); };
            li.onmousemove = () => { if (vurguIndeks !== i) vurgula(i, false); };
            liste.appendChild(li);
            ogeler.push(li);
        });
    }

    function acikMi() { return liste.classList.contains("acik"); }

    /* Liste asagi sigmiyorsa yukari acilir; yine de tasiyorsa sohbet
       kaydirilir — kart her zaman en altta oldugu icin gerekli. */
    /* LİSTE HER ZAMAN YUKARI AÇILIR (kullanıcı kararı: "bir yukarı bir
       aşağı açılıyor, hep yukarı açılmalı"). Alanın üstünde yer yoksa
       sohbet kaydırılarak yer açılır. */
    function konumla() {
        liste.classList.add("yukari");
        if (!sohbetEl) return;
        const g = giris.getBoundingClientRect();
        const alan = sohbetEl.getBoundingClientRect();
        const yukari = g.top - alan.top;
        const gerekli = Math.min(LISTE_YUKSEKLIGI, liste.scrollHeight + 8);
        if (yukari < gerekli) sohbetEl.scrollTop -= (gerekli - yukari + 8);
    }

    function ac(filtre) {
        ciz(filtre);
        liste.classList.add("acik");
        giris.setAttribute("aria-expanded", "true");
        konumla();
    }

    function kapat() {
        liste.classList.remove("acik");
        liste.classList.remove("yukari");
        giris.setAttribute("aria-expanded", "false");
        vurgula(-1);
    }

    /* Odaklanmak listeyi ACMAZ. Kullanici alana tiklayinca ekranin yarisini
       kaplayan bir liste acilmasi rahatsiz ediciydi; liste artik yalnizca
       ISTENDIGINDE acilir: ok dugmesi, yazmaya baslama ya da ArrowDown. */
    giris.addEventListener("focus", () => {
        giris.style.boxShadow = "";
        giris.style.borderColor = "";
    });
    okBtn.addEventListener("mousedown", e => {
        e.preventDefault();              // input odagi kaybolmasin
        if (acikMi()) { kapat(); }
        else { giris.focus(); ac(gecerli() ? "" : giris.value); }
    });

    giris.addEventListener("input", () => {
        ac(giris.value);
        if (degisince) degisince();
    });
    giris.addEventListener("blur", () => {
        setTimeout(kapat, 130);
        const bulunan = bul(giris.value);
        if (bulunan) giris.value = bulunan;
        isaretle();
        if (degisince) degisince();
    });

    /* Klavye: ok tuslariyla gezinme, Enter ile secim, Escape ile kapatma */
    giris.addEventListener("keydown", e => {
        if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            e.preventDefault();
            if (!acikMi()) { ac(gecerli() ? "" : giris.value); }
            if (!ogeler.length) return;
            const yon = (e.key === "ArrowDown") ? 1 : -1;
            let i = vurguIndeks + yon;
            if (i < 0) i = ogeler.length - 1;
            if (i >= ogeler.length) i = 0;
            vurgula(i);
            return;
        }
        if (e.key === "Home" && acikMi() && ogeler.length) {
            e.preventDefault(); vurgula(0); return;
        }
        if (e.key === "End" && acikMi() && ogeler.length) {
            e.preventDefault(); vurgula(ogeler.length - 1); return;
        }
        if (e.key === "Escape") { kapat(); return; }
        if (e.key === "Tab") { kapat(); return; }
        if (e.key === "Enter") {
            e.preventDefault();
            if (acikMi() && vurguIndeks >= 0 && ogeler[vurguIndeks]) {
                // Vurgulu ogeyi sec; bu Enter'i baska dinleyici (ekle) gormesin
                e.stopImmediatePropagation();
                sec(ogeler[vurguIndeks].textContent);
                return;
            }
            const bulunan = bul(giris.value);
            if (bulunan) giris.value = bulunan;
            kapat();
            isaretle();
            if (degisince) degisince();
        }
    });

    /* Liste sonradan gelirse (dataset ya da kolon) form kendini tazeler */
    if (kaynak.dinleyiciler) kaynak.dinleyiciler.push(() => {
        if (giris.disabled) return;
        const bulunan = bul(giris.value);
        if (bulunan) giris.value = bulunan;
        if (acikMi()) ac(giris.value);
        isaretle();
        if (degisince) degisince();
    });

    isaretle();
    /* dolu(): alan GERCEKTEN dolduruldu mu. gecerli()'den ayri, cunku
       opsiyonel alan bosken de GECERLI sayiliyor — durum gostergesi
       "kac alan dolduruldu" saymali, "kac alan formu engellemiyor"
       degil. */
    function dolu() {
        return gecerli() && giris.value.trim() !== "";
    }

    return { kok, giris, gecerli, dolu, deger, isaretle, ciz: ac };
}

/* ==================== Girdi doğrulama kartı ====================
   tip: "dogrulama" — bu adım sohbet paragrafı değil, bir KARAR EKRANI.
   Özet + kapsam + sözlükte tanımı bulunmayan kolonlar için satır satır
   karar: beş kolonlu tablo (Kolon | Tip | Kategori | Açıklama |
   Sözlüğe ekle). Kutu işaretliyse kolon sözlüğe eklenir, işaretsizse
   hariç tutulur; varsayılan işaretsizdir.

   Kart sohbet balonunun ICINDE degil, kendi karti olarak dogrudan
   sohbete dusuyor (mevcut .secim-kart deseni): adim bos metin
   dondurdugunde balon hic acilmiyor, ekranda "TAMAM" benzeri bir
   gurultu satiri kalmiyor.

   Yeni renk degiskeni TANIMLANMIYOR; kart mevcut paletle ciziliyor,
   koyu tema #kabuk.koyu degisken devriyle kendiliginden calisiyor.
   Ekrandaki her ad kullanicinin kendi verisinden gelir; sabit ornek
   veri seti / sozluk / kolon adi YOK. */
const DG_EKSIK_NOTU = "Sözlüğe eklenecek kolonların ve uygulanacak düzeltmelerin "
    + "açıklaması boş olamaz.";
/* Öneriler akarken açıklama alanları KİLİTLİ (kullanıcı kararı): yarım
   dolmuş bir listede yazmaya başlayıp üstüne öneri düşmesi, yazılanın
   kaybolması demek olurdu. */
const DG_ONERI_NOTU = "Açıklama önerileri hazırlanıyor: %s / %s kolon. "
    + "Öneriler tamamlanana kadar açıklamalar düzenlenemez.";
const DG_ONERI_ARALIK = 1500;      // yoklama aralığı (ms)
const DG_KALIP = {
    haric: "%s Kolonu Hariç Tut ve Devam Et",
    ekle:  "%s Kolonu Sözlüğe Ekle ve Devam Et",
    karma: "Seçimleri Uygula ve Devam Et",
    bos:   "Devam Et"
};

/* POST /mesaj'in "mesaj" alani: insan tarafinda okunabilir TEK satir.
   Sessiz gider - kullanici bir cumle yazmadi, bir form doldurdu. */
function dogrulamaOzetMetni(haricSayisi, ekleSayisi, duzeltSayisi) {
    const parcalar = [];
    if (haricSayisi) parcalar.push(ftBinlik(haricSayisi) + " kolon hariç tutuldu");
    if (ekleSayisi)  parcalar.push(ftBinlik(ekleSayisi) + " kolon sözlüğe eklendi");
    if (duzeltSayisi) parcalar.push(ftBinlik(duzeltSayisi) + " tanım düzeltildi");
    return parcalar.length ? parcalar.join(", ") : "Girdi doğrulama onaylandı.";
}

function dogrulamaKartiEkle(alan, blok) {
    const kart = document.createElement("div");
    kart.className = "secim-kart dg-kart";

    const kalip = Object.assign({}, DG_KALIP, alan.buton_kalip || {});

    /* ---- 1) Baslik satiri: baslik solda, rozet sagda ---- */
    const basSatir = document.createElement("div");
    basSatir.className = "dg-bas";

    const bas = document.createElement("div");
    bas.className = "secim-baslik";
    /* Gruplu blokta ad zaten ALT BAŞLIKTA. */
    bas.textContent = kartBasligiGerekli(alan, blok) ? tireSade(alan.baslik) : "";
    basSatir.appendChild(bas);

    let rozet = null;
    if (alan.rozet) {
        rozet = document.createElement("span");
        rozet.className = "dg-rozet";
        rozet.textContent = rozetMetni(alan.rozet);
        basSatir.appendChild(rozet);
    }
    /* Gruplu blokta başlık satırı boş kalır ve rozet alt başlığa taşınır
       (bkz. rozetiBasligaTasi); görünmez bir satır gövdeyi aşağı itmesin. */
    if (kartBasligiGerekli(alan, blok)) kart.appendChild(basSatir);

    /* ---- 2) Aciklama ---- */
    /* SOZLESME7 §2: arka uc kart aciklamasini artik GONDERMIYOR (baslik
       zaten ayni seyi soyluyordu). Gelmezse hic cizilmez. */
    if (alan.aciklama) {
        const ack = document.createElement("div");
        ack.className = "secim-aciklama dg-aciklama";
        ack.textContent = tireSade(alan.aciklama);
        kart.appendChild(ack);
    }

    /* ---- 3) Ozet bloklari ---- */
    const ozetler = alan.ozet || [];
    if (ozetler.length) {
        const oz = document.createElement("div");
        oz.className = "dg-ozet";
        ozetler.forEach(o => {
            const blok = document.createElement("div");
            blok.className = "dg-ozet-blok";

            const et = document.createElement("div");
            et.className = "dg-ozet-etiket";
            et.textContent = tireSade(o.etiket);
            blok.appendChild(et);

            const dg = document.createElement("div");
            dg.className = "dg-ozet-deger";
            dg.textContent = degerGoster(o.deger);
            /* Uzun ad kisaltiliyor; tamami ipucunda kalsin */
            dg.title = tireSade(o.deger);
            blok.appendChild(dg);

            (o.alt || []).forEach(a => {
                const s = document.createElement("div");
                s.className = "dg-ozet-alt";
                s.textContent = tireSade(a);
                blok.appendChild(s);
            });
            oz.appendChild(blok);
        });
        kart.appendChild(oz);
    }

    /* ---- 4) Kapsam: ince dolu/bos cubuk + kapsam.metin ---- */
    if (alan.kapsam) {
        const kp = document.createElement("div");
        kp.className = "dg-kapsam";

        let yuzde = Number(alan.kapsam.yuzde);
        if (!isFinite(yuzde)) yuzde = 0;
        yuzde = Math.max(0, Math.min(100, yuzde));

        const cubuk = document.createElement("div");
        cubuk.className = "dg-cubuk";
        const dolu = document.createElement("div");
        /* Tam kapsamda yesil, eksik kapsamda amber: ikisi de mevcut palet */
        dolu.className = "dg-cubuk-dolu " + (yuzde >= 100 ? "dg-tam" : "dg-noksan");
        dolu.style.width = yuzde + "%";
        cubuk.appendChild(dolu);
        kp.appendChild(cubuk);

        const mt = document.createElement("div");
        mt.className = "dg-kapsam-metin";
        mt.textContent = tireSade(alan.kapsam.metin);
        kp.appendChild(mt);

        kart.appendChild(kp);
    }

    /* ---- 5) Tanimsiz kolon tablosu ----
       satirlar bos / tanimsiz null ise (kapsam %100) tablo HIC cizilmez;
       birincil dugme buton_kalip.bos ile kalir. */
    const tanimsiz = alan.tanimsiz || null;
    const durumlar = [];          /* satir basina karar: {kolon, islem} */
    const satirElemanlari = [];
    const girisler = [];
    const kutular = [];           /* satir basina <input type="checkbox"> */
    const topluBtnleri = [];
    /* Öneriler hâlâ akıyorsa açıklama alanları ve devam düğmesi kilitli
       kalır (bkz. oneriKilidi). */
    let oneriBekliyor = false;

    if (tanimsiz) {
        const varsayilan = tanimsiz.varsayilan === "ekle" ? "ekle" : "haric";
        /* SOZLESME7 §2: KATEGORI kolonu tamamen kaldirildi. Tanimsiz bir
           kolona kategori atamak, kolonun ne oldugunu bilmeden onu bir
           kovaya koymaktir; govde de artik "kategoriler" gondermiyor. */

        const tbas = document.createElement("div");
        tbas.className = "dg-tablo-bas";

        const tb = document.createElement("div");
        tb.className = "dg-tablo-baslik";
        tb.textContent = tireSade(tanimsiz.baslik);
        tbas.appendChild(tb);

        /* Toplu islem: 200 kutuyu tek tek isaretlemek kullaniciyi bogar.
           Kutu isaretliyse sozluge eklenir, degilse haric tutulur; toplu
           dugmelerin adi da bu yuzden "Tümünü Seç" / "Tümünü Temizle". */
        const toplu = document.createElement("div");
        toplu.className = "dg-toplu";
        [["ekle", "Tümünü Seç"], ["haric", "Tümünü Temizle"]]
            .forEach(cift => {
                const b = document.createElement("button");
                b.type = "button";
                b.className = "dg-toplu-btn";
                b.dataset.islem = cift[0];
                b.textContent = cift[1];
                b.onclick = () => {
                    if (kart.classList.contains("kilitli")) return;
                    durumlar.forEach((s, i) => {
                        if (s.zorunlu) return;   // işareti kaldırılamaz
                        s.islem = cift[0]; kutuCiz(i);
                    });
                    durumTazele();
                };
                toplu.appendChild(b);
                topluBtnleri.push(b);
            });
        /* Toplu düğmeler TABLONUN HEMEN ÜSTÜNDE (kullanıcı kararı: başlık
           satırında notların üstünde kalıp tablodan kopuyordu). Aşağıda,
           tablodan hemen önce ekleniyor. */
        kart.appendChild(tbas);

        /* SOZLESME7 §2: eski UC not satiri (tanimsiz.aciklama,
           kapsam_notu, oneri_notu) TEK satira indi. Uc ayri soluk
           paragraf karti uzatiyordu ve ucu de ayni seyi soyluyordu:
           "tanimsizlar disarida kalir, oneriler dogrulanmamistir".
           Arka uc artik yalnizca tanimsiz["not"] gonderiyor. */
        if (tanimsiz["not"]) {
            const nt = document.createElement("div");
            nt.className = "dg-not";
            nt.textContent = tireSade(tanimsiz["not"]);
            kart.appendChild(nt);
        }
        /* ZORUNLU TANIM UYARISI: hedef, kimlik ve dönem kolonunun
           sözlük tanımı şart. Kutuları kilitli işaretli geliyor;
           kullanıcı SEBEBİNİ de okusun. */
        if (tanimsiz.zorunlu_not) {
            const zn = document.createElement("div");
            zn.className = "dg-not dg-zorunlu-not";
            zn.textContent = tireSade(tanimsiz.zorunlu_not);
            kart.appendChild(zn);
        }
        /* Öneri alınamayan grup varsa NEDENİ burada. Sessiz kalınca
           "model hiçbir şey öneremedi" ile "model hiç çağrılamadı" aynı
           görünüyordu; kullanıcı boş açıklamaların neden boş olduğunu
           bilmeli. */
        if (tanimsiz.oneri_hata) {
            const oh = document.createElement("div");
            oh.className = "dg-oneri-hata";
            oh.textContent = tireSade(tanimsiz.oneri_hata);
            kart.appendChild(oh);
        }

        const ust = elYap("div", "dg-tablo-ust");
        ust.appendChild(dgLejant(DG_LEJANT_KARAR));
        ust.appendChild(toplu);
        kart.appendChild(ust);
        const sar = document.createElement("div");
        sar.className = "dg-tablo-sar";

        const tablo = document.createElement("table");
        tablo.className = "dg-tablo";

        const thead = document.createElement("thead");
        const htr = document.createElement("tr");
        /* Dort kolon, SIRASIYLA (SOZLESME7 §2). Baslik "Kolon" degil
           "Değişken"; "İşlem" degil "Sözlüğe Ekle" — kolon basligi da
           kutunun ne anlama geldigini soylemeli. Baslik Buyuk Harfi
           (§1): tablo basliklarinda her kelime buyuk baslar. */
        /* Kolon başlığı "Seç" (kullanıcı kararı; eskiden "Sözlüğe Ekle"). */
        ["Değişken", "Tip", "Açıklama", "Seç"].forEach(h => {
            const th = document.createElement("th");
            th.textContent = h;
            htr.appendChild(th);
        });
        thead.appendChild(htr);
        tablo.appendChild(thead);

        /* Satir basina DOM: tr + 4 td + input + checkbox.
           200 satir icin sanallastirmaya gerek yok, ama satir basina
           fazlasi da olmamali. */
        const tbody = document.createElement("tbody");
        (tanimsiz.satirlar || []).forEach(sat => {
            const durum = {
                kolon: String(sat.kolon === null || sat.kolon === undefined
                              ? "" : sat.kolon),
                /* ZORUNLU SATIR: hedef, kimlik ve dönem kolonunun sözlük
                   tanımı şart. İşareti kaldırılamaz, açıklaması boş
                   bırakılamaz (bkz. akis_faz01.zorunlu_tanimlar). */
                zorunlu: !!sat.zorunlu,
                /* TEK DEĞERLİ: sözlüğe eklenemez, süreç dışı (kilitli). */
                kilitli: !!sat.kilitli && !sat.zorunlu,
                rol: String(sat.rol || ""),
                islem: sat.zorunlu ? "ekle" : sat.kilitli ? "haric"
                     : ((sat.islem === "ekle" || sat.islem === "haric")
                        ? sat.islem : varsayilan)
            };
            const i = durumlar.push(durum) - 1;

            const tr = document.createElement("tr");
            tr.className = "dg-satir";
            tr.dataset.kolon = durum.kolon;

            const tdK = document.createElement("td");
            tdK.className = "dg-kolon";
            tdK.appendChild(document.createTextNode(durum.kolon));
            tdK.title = durum.kolon;
            /* ONAYLI HAFIZADAN DOLDU: dil modeli çağrılmadı; metin daha
               önce onaylanmış tanım. Kaynağı satırda yazar. */
            if (sat.oneri_kaynak === "hafiza") hafizaCipi(tdK, tr, sat.hafiza_veri_seti);
            if (durum.zorunlu) {
                /* Kolonun NEDEN zorunlu olduğu satırda yazsın; kullanıcı
                   işareti kaldıramayınca sebebini aramamalı. */
                /* Rol çipi Başlık Biçiminde ("Kimlik Kolonu"), kırmızı. */
                tdK.appendChild(elYap("span", "dg-rol dg-rol-zorunlu",
                    tireSade(durum.rol).split(" ").map(k =>
                        k ? k.charAt(0).toLocaleUpperCase("tr") + k.slice(1) : k).join(" ")));
                tr.classList.add("dg-zorunlu");
            }
            tr.appendChild(tdK);

            /* TIP SALT OKUNUR: bu bir oneri degil, veriden okunan
               olgusal bir gercek. Degistirilebilir bir alan olsaydi
               kullanici veriye aykiri bir tip secebilirdi. */
            const tdT = document.createElement("td");
            tdT.className = "dg-tip";
            tdT.textContent = tireSade(sat.tip);
            tr.appendChild(tdT);

            /* Aciklama duzenlenebilir: oneri ile dolu gelir, kullanici
               ustune yazabilir. Oneri yoksa (oneri_kaynak "yok") bos. */
            const tdA = document.createElement("td");
            tdA.className = "dg-aciklama-hucre";
            const giris = document.createElement("input");
            giris.type = "text";
            giris.className = "dg-giris";
            /* GERİ DÖNÜŞTE önceki onaylı metin gelir ve model önerisi
               onu EZMEZ. Vurgu, satırdaki metnin öneriyle aynı olup
               olmadığına göre (bkz. dgRenk). */
            if (sat.onceki) {
                giris.value = tireSade(sat.onceki);
                giris.dataset.dolduruldu = "1";
                giris.dataset.oneriMetin = tireSade(sat.onceki_oneri || "");
            } else {
                giris.value = tireSade(sat.oneri);
                if (sat.oneri) giris.dataset.oneriMetin = tireSade(sat.oneri);
            }
            giris.placeholder = "Açıklama";
            giris.setAttribute("aria-label", durum.kolon + " açıklaması");
            giris._vurgu = () => {
                const karar = kart.classList.contains("kilitli")
                    ? (durum.islem === "ekle" ? "evet" : "hayir") : null;
                dgRenk(tr, giris.value, giris.dataset.oneriMetin || "", karar);
            };
            giris.addEventListener("input", () => {
                giris._vurgu();
                if (kart.classList.contains("kilitli")) return;
                durumTazele();
            });
            giris._vurgu();
            tdA.appendChild(giris);
            tr.appendChild(tdA);
            girisler.push(giris);

            /* SOZLUGE EKLE: isaretli -> sozluge eklenir, isaretsiz ->
               haric tutulur. Iki durumlu dugme KALDIRILDI; "basmam mi
               gerekiyor" belirsizligi ondandi. Kutu kendi durumunu
               gosterir, etiket okumaya gerek yok. */
            const tdI = document.createElement("td");
            tdI.className = "dg-ekle-hucre";
            const kutu = document.createElement("input");
            kutu.type = "checkbox";
            kutu.className = "dg-ekle";
            kutu.setAttribute("aria-label", durum.kolon + " sözlüğe eklensin");
            if (durum.zorunlu) kutu.disabled = true;
            if (durum.kilitli) {
                kutu.disabled = true;
                kutu.title = tireSade(sat.kilit_sebebi || "");
                tdI.title = kutu.title;
                giris.disabled = true;
                tr.classList.add("dg-rol-kilitli");
            }
            kutu.addEventListener("change", () => {
                if (kart.classList.contains("kilitli") || durum.zorunlu
                        || durum.kilitli) {
                    kutuCiz(i); return;
                }
                durum.islem = kutu.checked ? "ekle" : "haric";
                kutuCiz(i);
                durumTazele();
            });
            tdI.appendChild(kutu);
            tr.appendChild(tdI);
            kutular.push(kutu);

            satirElemanlari.push(tr);
            tbody.appendChild(tr);
        });
        tablo.appendChild(tbody);
        sar.appendChild(tablo);
        kart.appendChild(sar);

        durumlar.forEach((s, i) => kutuCiz(i));

        /* EN_FAZLA_TANIMSIZ asildiysa kalanlar ekranda YOK; varsayilan
           isleme tabi olacaklar ve kart bunu acikca yaziyor. */
        if (tanimsiz.kalan) {
            const kalan = document.createElement("div");
            kalan.className = "dg-kalan";
            kalan.textContent = ftBinlik(tanimsiz.kalan)
                + " kolon daha tanımsız; listede gösterilmiyor ve varsayılan "
                + "işleme (hariç tut) tabi olacak.";
            kart.appendChild(kalan);
        }
    }

    /* ---- 5a) Kısaltma Sözlüğü (01.2.4) ----
       Kolon adı kısaltmaları sözlükten kural tabanlı
       çıkarılır; kullanıcı anlamı düzeltip proje genelindeki onaylı
       kısaltma hafızasına kaydeder. Kayıt adım akışından BAĞIMSIZ
       (kendi düğmesi, /kisaltma_kaydet). */
    /* AYRI ADIMLAR (kullanıcı kararı): 01.2.4 Kısaltma Sözlüğü ve 01.2.5
       Kolon Adı Önerileri kendi kartlarında; karar birincil düğmeyle
       adımla birlikte gider (alan.adim). Bölümlerin kendi kaydet
       düğmeleri adım kartında gizlenir. */
    const adimModu = alan.adim || "";
    const kisaErisim = alan.kisaltma
        ? kisaltmaBolumuEkle(kart, alan.kisaltma, !!(blok && blok.kilit), !!adimModu,
                             () => durumTazele()) : null;
    /* Kolon Adı Önerileri: açıklamada anlamı geçen ama adda olmayan
       kısaltmalar için yeni ad (yalnız AMP kopyalarında uygulanır). */
    const kolonAdErisim = (alan.kolon_ad && (alan.kolon_ad.satirlar || []).length)
        ? kolonAdBolumuEkle(kart, alan.kolon_ad, !!(blok && blok.kilit), !!adimModu) : null;

    /* ---- 5b) Sözlükteki tanımların kontrolü ----
       Kullanıcı kararı: sözlükte tanımı OLAN kolonların tanımı da birden
       fazla dil modeliyle denetlenir; yalnızca düzeltilmesi önerilenler
       "Mevcut Tanım / Önerilen Tanım" karşılaştırmasıyla listelenir.
       Satırlar arka plandaki işten yoklamayla gelir (bkz. kontrolIsle);
       kart beklemeden onaylanabilir. Uygula işaretli düzeltme sözlüğün
       ÇALIŞMA KOPYASINA yazılır, girdi sözlüğü değişmez. */
    const kontrol = alan.kontrol || null;
    const kDurumlar = [];            /* {kolon, oneri, tr, giris, kutu} */
    const kGorulen = new Set();
    let kTbody = null, kSar = null, kDurumEl = null, kHataEl = null, kToplu = null;
    /* Sözlük Tanım Kontrolü adımında (kontrol.bekle) devam düğmesi kontrol
       bitene kadar kapalı: adımın işi bu kontrol. */
    let kontrolBekliyor = !!(kontrol && kontrol.bekle && kontrol.toplam && !kontrol.baslamadi);
    /* İSTEĞE BAĞLI KONTROL (kullanıcı kararı): kart "Tanımları Kontrol
       Et" ile açılır; basılmadıkça hiçbir dil modeli çağrılmaz. "Kontrol
       Etmeden Devam Et" her zaman açık (sürerken de: kontrol durdurulur). */
    let kBaslaBtn = null;
    if (kontrol) {
        const kb = elYap("div", "dg-tablo-bas dg-kontrol-bas");
        const kbas = elYap("div", "dg-tablo-baslik", kontrol.baslik || "Sözlükteki Tanımların Kontrolü");
        if (kontrol.bilgi) kbas.appendChild(bolmeBilgiSimgesi(kontrol.bilgi, kontrol.baslik));
        kb.appendChild(kbas);
        kart.appendChild(kb);
        kDurumEl = elYap("div", "dg-not dg-kontrol-durum", "");
        kart.appendChild(kDurumEl);
        kHataEl = elYap("div", "dg-oneri-hata");
        kHataEl.textContent = tireSade(kontrol.hata || "");
        kHataEl.hidden = !kontrol.hata;
        kart.appendChild(kHataEl);
        if (!kontrol.toplam && !(kontrol.satirlar || []).length && !kontrol.hata) {
            kDurumEl.textContent = "Sözlükte kontrol edilecek tanım bulunmadı.";
        } else if (kontrol.baslamadi) {
            kDurumEl.textContent = "Sözlükte tanımı bulunan " + ftBinlik(kontrol.toplam)
                + " kolonun tanımı dil modelleriyle kontrol edilebilir. Bu adım "
                + "isteğe bağlıdır; kontrol etmeden de devam edebilirsiniz.";
            kBaslaBtn = elYap("button", "secim-onay ikincil dg-kontrol-basla",
                              "Tanımları Kontrol Et");
            kBaslaBtn.type = "button";
            kBaslaBtn.onclick = () => kontrolBaslat();
        } else kDurumEl.hidden = true;

        const kUst = elYap("div", "dg-tablo-ust");
        kUst.appendChild(dgLejant([["dg-l-renksiz", "Dil Modeli Önerisi"],
                                   ["dg-l-dikkat", "Boş"],
                                   ["dg-l-duzenlendi", "Düzenlendi"]]));
        kToplu = elYap("div", "dg-toplu");
        [[true, "Tümünü Uygula"], [false, "Tümünü Temizle"]].forEach(([deger, etiket]) => {
            const b = elYap("button", "dg-toplu-btn", etiket);
            b.type = "button";
            b.onclick = () => {
                if (kart.classList.contains("kilitli")) return;
                kDurumlar.forEach(k => { k.kutu.checked = deger; k.vurgu(); });
                durumTazele();
            };
            kToplu.appendChild(b);
            topluBtnleri.push(b);
        });
        kUst.appendChild(kToplu);
        kart.appendChild(kUst);

        kSar = elYap("div", "dg-tablo-sar");
        const kt = elYap("table", "dg-tablo dg-kontrol-tablo");
        const kth = document.createElement("thead");
        const khr = document.createElement("tr");
        ["Değişken", "Mevcut Tanım", "Önerilen Tanım", "Uygula"].forEach(h =>
            khr.appendChild(elYap("th", "", h)));
        kth.appendChild(khr);
        kt.appendChild(kth);
        kTbody = document.createElement("tbody");
        kt.appendChild(kTbody);
        kSar.appendChild(kt);
        kart.appendChild(kSar);
        kSar.hidden = true;
        kUst.hidden = true;
        kSar._ust = kUst;
        (kontrol.satirlar || []).forEach(sat => kontrolSatirEkle(sat));
    }

    function kontrolSatirEkle(sat) {
        const ad = String(sat.kolon === null || sat.kolon === undefined ? "" : sat.kolon);
        if (!kTbody || !ad || kGorulen.has(ad)) return;
        kGorulen.add(ad);
        const oneri = tireSade(sat.oneri || "");
        const tr = elYap("tr", "dg-satir dg-kontrol-satir");
        tr.dataset.kolon = ad;
        const tdK = elYap("td", "dg-kolon", ad);
        tdK.title = ad;
        if (sat.gerekce) tdK.appendChild(bolmeBilgiSimgesi(sat.gerekce, ad));
        if (sat.kaynak === "hafiza") hafizaCipi(tdK, tr, sat.hafiza_veri_seti);
        tr.appendChild(tdK);
        tr.appendChild(elYap("td", "dg-mevcut", sat.mevcut || ""));
        const tdA = elYap("td", "dg-aciklama-hucre");
        const giris = document.createElement("textarea");
        giris.className = "dg-giris dg-metin";
        giris.rows = 1;
        giris.value = tireSade(sat.aciklama !== undefined && sat.aciklama !== ""
                               ? sat.aciklama : oneri);
        giris.setAttribute("aria-label", ad + " önerilen tanım");
        if (sat.modeller) giris.title = "Öneren: " + tireSade(sat.modeller);
        const boyla = () => { giris.style.height = "auto"; giris.style.height = giris.scrollHeight + "px"; };
        tdA.appendChild(giris);
        tr.appendChild(tdA);
        const tdI = elYap("td", "dg-ekle-hucre");
        const kutu = document.createElement("input");
        kutu.type = "checkbox";
        kutu.className = "dg-ekle";
        kutu.checked = sat.islem === "uygula";
        kutu.setAttribute("aria-label", ad + " düzeltmesi uygulansın");
        tdI.appendChild(kutu);
        tr.appendChild(tdI);
        const k = { kolon: ad, oneri, tr, giris, kutu };
        k.vurgu = () => {
            const karar = kart.classList.contains("kilitli")
                ? (kutu.checked ? "evet" : "hayir") : null;
            dgRenk(tr, giris.value, oneri, karar);
        };
        giris.addEventListener("input", () => { boyla(); k.vurgu(); durumTazele(); });
        kutu.addEventListener("change", () => {
            if (kart.classList.contains("kilitli")) { kutu.checked = !kutu.checked; return; }
            k.vurgu(); durumTazele();
        });
        if (kart.classList.contains("kilitli")) { giris.disabled = true; kutu.disabled = true; }
        kDurumlar.push(k);
        kTbody.appendChild(tr);
        kSar.hidden = false;
        if (kSar._ust) kSar._ust.hidden = false;
        k.vurgu();
        requestAnimationFrame(boyla);
    }

    /* Yoklama kaydından tanım kontrolü: yeni satırlar + ilerleme. */
    function kontrolIsle(kayit) {
        if (!kontrol || !kayit) return;
        const dz = kayit.duzeltmeler || {};
        Object.keys(dz).forEach(ad => {
            const d = dz[ad] || {};
            kontrolSatirEkle({ kolon: ad, mevcut: d.mevcut, oneri: d.oneri,
                               gerekce: d.gerekce, modeller: d.modeller, islem: "red",
                               kaynak: d.kaynak, hafiza_veri_seti: d.hafiza_veri_seti });
        });
        const durumK = kayit.kontrol_durum || "yok";
        const toplam = kayit.kontrol_toplam || 0;
        const n = kDurumlar.length;
        let metin = "";
        if (durumK === "bekliyor")
            metin = "Tanım kontrolü açıklama önerilerinden sonra başlayacak ("
                + ftBinlik(toplam) + " kolon).";
        else if (durumK === "calisiyor")
            metin = "Tanım kontrolü sürüyor: " + ftBinlik(kayit.kontrol_biten || 0) + " / "
                + ftBinlik(toplam) + " kolon. " + (kontrol.bekle
                ? "Kontrol bitince devam edebilirsiniz; önerilen düzeltmeler geldikçe listeye eklenir."
                : "Beklemeden devam edebilirsiniz; kontrol edilmemiş tanımlar olduğu gibi kalır.");
        else if (durumK === "bitti")
            metin = ftBinlik(toplam) + " tanım dil modeliyle kontrol edildi; " + (n
                ? "listede " + ftBinlik(n) + " düzeltme önerisi var."
                : "düzeltme gereken tanım bulunmadı.");
        else if (durumK === "yok" && n)
            metin = ftBinlik(n) + " tanım için onaylı tanımla fark bulundu.";
        /* Onaylı tanım hafızasıyla karşılaştırma (dil modeli çağrılmadan). */
        const hz = kontrol.hafiza || {};
        if (hz.ayni || hz.farkli) {
            metin = (metin ? metin + " " : "") + "Onaylı tanım hafızası: "
                + ftBinlik(hz.ayni || 0) + " tanım onaylı tanımla aynı (kontrol edilmedi), "
                + ftBinlik(hz.farkli || 0) + " tanımda onaylı tanım farklı (doğrudan öneri olarak listelendi).";
        }
        if (kDurumEl) { kDurumEl.textContent = metin; kDurumEl.hidden = !metin; }
        if (kHataEl && kayit.kontrol_hata) {
            kHataEl.textContent = tireSade(kayit.kontrol_hata);
            kHataEl.hidden = false;
        }
        kontrolBekliyor = !!kontrol.bekle && (durumK === "bekliyor" || durumK === "calisiyor");
        durumTazele();
    }

    /* ---- 6) Gerekce satiri + dugmeler ---- */
    const gerekce = document.createElement("div");
    gerekce.className = "dg-gerekce";
    gerekce.hidden = true;
    kart.appendChild(gerekce);

    /* YALNIZ BIRINCIL DUGME. "Seçimi Düzenle" ve "Geri" kaldirildi:
       ikisi de ayni yere, veri seti secim formuna goturuyordu. */
    const dugmeler = document.createElement("div");
    dugmeler.className = "onay-dugmeler dg-dugmeler";

    const birincil = document.createElement("button");
    birincil.type = "button";
    birincil.className = "secim-onay dg-birincil";
    dugmeler.appendChild(birincil);
    /* Tanım kontrolü adımı: "Kontrol Etmeden Devam Et" (ikincil) ve
       başlamadıysa "Tanımları Kontrol Et". */
    let atlaBtn = null;
    if (kontrol && kontrol.bekle) {
        if (kBaslaBtn) dugmeler.insertBefore(kBaslaBtn, birincil);
        atlaBtn = elYap("button", "secim-onay ikincil dg-kontrol-atla",
                        "Kontrol Etmeden Devam Et");
        atlaBtn.type = "button";
        atlaBtn.onclick = () => {
            if (mesgul || kart.classList.contains("kilitli")) return;
            const ozet = "Tanım kontrolü yapılmadan devam edildi";
            kartiKilitle(ozet);
            gonder(ozet, false, { dogrulama: { kontrol: [], atla: true } });
        };
        dugmeler.appendChild(atlaBtn);
        /* Başlamadan önce ana düğmenin yapacağı bir şey yok. */
        birincil.hidden = !!kontrol.baslamadi;
    } else if (alan.atla) {
        /* İsteğe bağlı adım (Kısaltma Sözlüğü, Kolon Adı Önerileri). */
        atlaBtn = elYap("button", "secim-onay ikincil dg-kontrol-atla", tireSade(alan.atla));
        atlaBtn.type = "button";
        atlaBtn.onclick = () => {
            if (mesgul || kart.classList.contains("kilitli")) return;
            const ozet = adimModu === "kolon_ad" ? "Kolon adları değiştirilmeden devam edildi"
                : "Kısaltmalar onaylanmadan devam edildi";
            kartiKilitle(ozet);
            gonder(ozet, false, { dogrulama: { atla: true } });
        };
        dugmeler.appendChild(atlaBtn);
    }
    kart.appendChild(dugmeler);

    function kontrolBaslat() {
        if (!kBaslaBtn || kart.classList.contains("kilitli")) return;
        kBaslaBtn.disabled = true;
        fetch(getWebAppBackendUrl("tanim_kontrol_baslat"), {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify(ftKimlikGovdesi({}))
        })
        .then(r => r.json())
        .then(d => {
            if (!d || d.tamam !== true || !d.oneri_is) {
                kBaslaBtn.disabled = false;
                kHataEl.textContent = tireSade((d && d.hata) || "Kontrol başlatılamadı.");
                kHataEl.hidden = false;
                return;
            }
            kontrol.baslamadi = false;
            kontrol.toplam = (d.kontrol && d.kontrol.toplam) || kontrol.toplam;
            if (d.kontrol && d.kontrol.hafiza) kontrol.hafiza = d.kontrol.hafiza;
            kBaslaBtn.remove();
            kBaslaBtn = null;
            birincil.hidden = false;
            kontrolBekliyor = true;
            kDurumEl.textContent = "Tanım kontrolü başlıyor…";
            durumTazele();
            oneriYokla(String(d.oneri_is));
        })
        .catch(e => {
            kBaslaBtn.disabled = false;
            kHataEl.textContent = "Kontrol başlatılamadı: " + e;
            kHataEl.hidden = false;
        });
    }

    function kutuCiz(i) {
        const k = kutular[i];
        if (!k) return;
        const ekleMi = durumlar[i].islem === "ekle";
        k.checked = ekleMi;
        if (satirElemanlari[i]) satirElemanlari[i].dataset.islem = durumlar[i].islem;
        if (girisler[i] && girisler[i]._vurgu) girisler[i]._vurgu();
    }

    /* Birincil dugmenin etiketi seçime gore CANLI hesaplanir. */
    function durumTazele() {
        if (kart.classList.contains("kilitli")) return;

        let haricSayisi = 0, ekleSayisi = 0, eksikSayisi = 0;
        durumlar.forEach((s, i) => {
            const bos = girisler[i] ? girisler[i].value.trim() === "" : true;
            const eksik = (s.islem === "ekle") && bos;
            if (eksik) eksikSayisi++;
            if (s.islem === "ekle") ekleSayisi++; else haricSayisi++;
            if (satirElemanlari[i]) satirElemanlari[i].classList.toggle("dg-noksan", eksik);
            if (girisler[i]) girisler[i].classList.toggle("dg-noksan", eksik);
        });

        /* EKRANDA GORUNMEYEN KOLONLAR DA SAYILIR. EN_FAZLA_TANIMSIZ
           asildiginda kalan kolonlar tabloya cizilmiyor ama arka uc
           onlari VARSAYILAN islemle (hariç) uyguluyor. Etiket yalnizca
           gorunen satirlari sayarsa, 900 tanimsiz kolonlu bir sette
           "200 Kolonu Hariç Tut" yazip 900'unu hariç tutardi — dugmenin
           uzerindeki sayi yaptigi isle tutmuyordu. */
        const gizliHaric = (alan.tanimsiz && alan.tanimsiz.kalan) || 0;
        const toplamHaric = haricSayisi + gizliHaric;

        /* Tanım kontrolü: işaretli düzeltme sayısı; boş metinle
           uygulanacak satır da "eksik" sayılır. */
        let duzeltSayisi = 0;
        kDurumlar.forEach(k => {
            if (!k.kutu.checked) { k.giris.classList.remove("dg-noksan"); return; }
            duzeltSayisi++;
            const bos = k.giris.value.trim() === "";
            if (bos) eksikSayisi++;
            k.giris.classList.toggle("dg-noksan", bos);
        });

        let etiket;
        if (duzeltSayisi > 0) etiket = kalip.karma;
        else if (!durumlar.length && !gizliHaric) etiket = kalip.bos;
        else if (ekleSayisi === 0)   etiket = kalip.haric.replace("%s", ftBinlik(toplamHaric));
        else if (toplamHaric === 0)  etiket = kalip.ekle.replace("%s", ftBinlik(ekleSayisi));
        else                         etiket = kalip.karma;
        birincil.textContent = tireSade(etiket);

        /* Aciklamasi bos "sözlüğe ekle" satiri varsa kaydetmek anlamsiz:
           dugme pasif ve NEDENI ekranda yaziyor. */
        if (oneriBekliyor) return;          // kilit mesajı ekranda kalsın
        if (kontrolBekliyor) {
            birincil.disabled = true;
            gerekce.hidden = true;
            return;
        }
        /* KISALTMA SÖZLÜĞÜ (kullanıcı kararı): dil modeli kontrolü bitmeden
           onaylanamaz; yalnız sözlükten çıkan anlamlar çalışmaya girmesin.
           Beklemek istemeyen "Kısaltmaları Onaylamadan Devam Et"i kullanır. */
        if (adimModu === "kisaltma" && kisaErisim && kisaErisim.bekliyor()) {
            birincil.disabled = true;
            gerekce.hidden = false;
            gerekce.textContent = "Dil modeli kontrolü bitince onaylanabilir. Beklemek "
                + "istemezseniz \"Kısaltmaları Onaylamadan Devam Et\" ile geçebilirsiniz.";
            return;
        }
        birincil.disabled = eksikSayisi > 0;
        gerekce.hidden = eksikSayisi === 0;
        gerekce.textContent = eksikSayisi > 0 ? DG_EKSIK_NOTU : "";
    }

    function girdileriKilitle(kilit) {
        girisler.forEach(g => { g.disabled = kilit; });
        if (atlaBtn) atlaBtn.disabled = kilit;
        if (kBaslaBtn) kBaslaBtn.disabled = kilit;
        kDurumlar.forEach(k => { k.giris.disabled = kilit; k.kutu.disabled = kilit; });
        kutular.forEach((k, i) => {
            // Zorunlu satırın kutusu kilit açılsa da pasif kalır.
            k.disabled = kilit || !!(durumlar[i] && durumlar[i].zorunlu);
        });
        topluBtnleri.forEach(b => { b.disabled = kilit; });
        if (kisaErisim) kisaErisim.kilitle(kilit);
        if (kolonAdErisim) kolonAdErisim.kilitle(kilit);
        birincil.disabled = kilit;
    }

    /* Hata olursa kart ESKI ACIK haline doner; kullanicinin yazdigi
       aciklamalar ve secimleri EKRANDA KALIR (input/select/checkbox
       degerlerine dokunulmuyor, yalnizca disabled kalkiyor).
       Kayit sirasinda kart kilitlenir. Dugmenin uzerine "SECILDI"
       gibi bir DURUM YAZILMAZ: etiket ne yaptigini soylemeye devam
       eder, kilidi kartin sonuk gorunumu ve pasif dugme anlatir. */
    /* Karar verildikten sonra rozet NE YAPILDIGINI yazar. Eskiden arka uç
       bunu ayrı bir sohbet balonu olarak basıyordu ("Veri seti ve sözlük
       bağlandı. 2 kolon sözlüğe eklendi.") — kartın hemen altında, aynı
       kararın tekrarı olarak. Bilgi kaybolmadı, kartın içine taşındı. */
    /* Karar verilince satırlar yeşil / kırmızı olur; geri alınınca
       karar öncesi renklerine döner (bkz. dgRenk). */
    function renkleriTazele() {
        girisler.forEach(g => { if (g._vurgu) g._vurgu(); });
        kDurumlar.forEach(k => k.vurgu());
        if (kDurumEl && kart.classList.contains("kilitli")) kDurumEl.hidden = true;
    }

    function kartiKilitle(ozet) {
        kart.classList.add("kilitli");
        // Karar verildi: öneri yoklaması sürerse boşuna istek gider.
        if (oneriZaman) { clearTimeout(oneriZaman); oneriZaman = null; }
        oneriBekliyor = false;
        kontrolBekliyor = false;
        girdileriKilitle(true);
        const eskiRozet = rozet ? rozet.textContent : "";
        if (rozet && ozet) rozet.textContent = rozetMetni(ozet);
        renkleriTazele();

        geriAlKilit = () => {
            kart.classList.remove("kilitli");
            girdileriKilitle(false);
            if (rozet) rozet.textContent = eskiRozet;
            renkleriTazele();
            durumTazele();
        };
    }

    /* ---- ÖNERİ AKIŞI ----
       1.000 tanımsız kolon gruplara bölünüp onlarca dil modeli çağrısı
       ediyor. Kart HEMEN açılıyor, öneriler geldikçe satırlara düşüyor.
       Öneriler bitene kadar açıklama alanları ve devam düğmesi kilitli:
       yarım dolmuş bir listede yazmaya başlayıp üstüne öneri düşmesi
       yazılanın kaybolması demek olurdu. */
    let oneriZaman = null;
    function oneriKilidi(acik, biten, toplam) {
        oneriBekliyor = !acik;
        girisler.forEach(g => { g.disabled = !acik; });
        topluBtnleri.forEach(b => { b.disabled = !acik; });
        if (!acik) {
            birincil.disabled = true;
            gerekce.hidden = false;
            gerekce.textContent = DG_ONERI_NOTU
                .replace("%s", ftBinlik(biten || 0))
                .replace("%s", ftBinlik(toplam || 0));
        } else {
            durumTazele();
        }
    }

    function onerileriIsle(kayit) {
        const gelen = (kayit && kayit.oneriler) || {};
        durumlar.forEach((s, i) => {
            const g = girisler[i];
            if (!g || g.dataset.dolduruldu === "1") return;
            const k = gelen[s.kolon];
            const ack = k && k.aciklama ? String(k.aciklama) : "";
            if (!ack) return;
            g.value = tireSade(ack);
            g.dataset.dolduruldu = "1";
            /* Sözlük seçilmediyse öneri gelen satır "Sözlüğe Ekle" işaretli
               olur (zorunlu / kilitli satırlar kendi kuralında kalır). */
            if (alan.tanimsiz && alan.tanimsiz.oneri_gelince_ekle
                    && !s.zorunlu && !s.kilitli && s.islem !== "ekle") {
                s.islem = "ekle";
                kutuCiz(i);
            }
            g.dataset.oneriMetin = tireSade(ack);
            if (k.modeller) g.title = "Öneren: " + tireSade(k.modeller);
            if (k.kaynak === "hafiza" && satirElemanlari[i]
                    && !satirElemanlari[i].querySelector(".dg-hafiza")) {
                hafizaCipi(satirElemanlari[i].querySelector(".dg-kolon"),
                           satirElemanlari[i], k.hafiza_veri_seti);
            }
            if (g._vurgu) g._vurgu();
            if (satirElemanlari[i]) satirElemanlari[i].dataset.oneri = "llm";
        });
        if (kayit && kayit.hata) {
            let oh = kart.querySelector(".dg-oneri-hata");
            if (!oh) {
                oh = elYap("div", "dg-oneri-hata");
                kart.insertBefore(oh, dugmeler);
            }
            oh.textContent = tireSade(kayit.hata);
        }
        /* Kullanılamayan model (orkestra diğer modellerle devam etti). */
        if (kayit && kayit.model_notu) {
            let mn = kart.querySelector(".dg-model-notu");
            if (!mn) {
                mn = elYap("div", "dg-not dg-model-notu");
                kart.insertBefore(mn, dugmeler);
            }
            mn.textContent = tireSade(kayit.model_notu);
        }
        kontrolIsle(kayit);
    }

    function oneriYokla(isId) {
        fetch(getWebAppBackendUrl("oneriler")
              + "?is=" + encodeURIComponent(isId)
              + "&oturum_id=" + encodeURIComponent(OTURUM_ID))
            .then(r => r.json())
            .then(k => {
                if (!kart.isConnected) return;       // kart ekrandan kalkti
                onerileriIsle(k);
                const kontrolSuruyor = k.kontrol_durum === "bekliyor"
                    || k.kontrol_durum === "calisiyor";
                if (k.durum === "calisiyor") {
                    oneriKilidi(false, k.biten, k.toplam);
                } else if (oneriBekliyor) {
                    // "bitti" ya da "yok": her iki durumda da kilit acilir.
                    oneriKilidi(true);
                }
                /* Tanım kontrolü kartı KİLİTLEMEZ ama yoklama sürer. */
                if (k.durum === "calisiyor" || kontrolSuruyor)
                    oneriZaman = setTimeout(() => oneriYokla(isId),
                                            DG_ONERI_ARALIK);
                else if (k.durum === "yok" && kontrol && kDurumEl) {
                    kontrolBekliyor = false;
                    durumTazele();
                    kDurumEl.textContent = "Tanım kontrolünün sonucu alınamadı "
                        + "(sunucu yeniden başlamış olabilir). Geri Dön ile adımı "
                        + "yeniden açarak kontrolü tekrar başlatabilirsiniz.";
                    kDurumEl.hidden = false;
                }
            })
            .catch(() => {
                // Yoklama basarisiz: kullaniciyi kilitli birakma, kendi
                // yazabilsin. Sessiz degil — hata satiri zaten varsa durur.
                kontrolBekliyor = false;
                if (kart.isConnected) oneriKilidi(true);
            });
    }

    /* Gonderilen govde: {dogrulama: {haric: [...], ekle: [{kolon,
       aciklama}]}} + sessiz: true. SOZLESME7 §2 ile "kategori" alani
       DUSTU: kart kategori sormuyor, arka uc de satir_ekle'ye bos
       kategori geciyor. */
    birincil.onclick = () => {
        if (mesgul || birincil.disabled) return;
        const karar = { haric: [], ekle: [] };
        durumlar.forEach((s, i) => {
            const ack = girisler[i] ? girisler[i].value.trim() : "";
            if (s.islem === "ekle" && ack !== "")
                karar.ekle.push({ kolon: s.kolon, aciklama: ack });
            else
                karar.haric.push(s.kolon);
        });
        /* Tanım kontrolü: listelenen HER satır gider (uygula işaretli
           olsun olmasın): geri dönüşte daha önce uygulanan düzeltme
           işareti kaldırılınca eski tanım geri yazılır. */
        karar.kontrol = kDurumlar.map(k => ({
            kolon: k.kolon, aciklama: k.giris.value.trim(), uygula: k.kutu.checked }));
        const duzelt = karar.kontrol.filter(k => k.uygula && k.aciklama).length;
        if (kisaErisim) { karar.kisaltma = kisaErisim.deger(); karar.birlesik = kisaErisim.birlesik(); }
        if (kolonAdErisim) karar.kolon_ad = kolonAdErisim.deger();
        let ozet;
        if (adimModu === "kisaltma") {
            const n = (karar.kisaltma || []).filter(k => k.anlam).length;
            ozet = ftBinlik(n) + " kısaltmanın anlamı onaylandı";
        } else if (adimModu === "kolon_ad") {
            const n = (karar.kolon_ad || []).filter(k => k.uygula && k.yeni_ad && k.yeni_ad !== k.kolon).length;
            ozet = n ? ftBinlik(n) + " kolonun adı değiştirilecek" : "Kolon adı değiştirilmedi";
        } else ozet = (!durumlar.length && kontrol)
            ? (duzelt ? ftBinlik(duzelt) + " tanım düzeltildi" : "Düzeltme uygulanmadı")
            : dogrulamaOzetMetni(karar.haric.length, karar.ekle.length, duzelt);
        kartiKilitle(ozet);
        /* Sessiz gider (ikinci parametre false): kullanici bir cumle
           yazmadi, bir form doldurdu. */
        gonder(ozet, false, { dogrulama: karar });
    };

    durumTazele();

    (adimKabiAl(blok) || sohbetEl).appendChild(kart);
    rozetiBasligaTasi(blok, rozet);
    sohbetKaydir();

    /* GECMISTEN yeniden cizim: kart kilitli acilir, rozet karar
       verildigi andaki halini korur (ozet gecirilmiyor). Yoklama da
       BASLAMAZ: o is coktan bitti, tekrar sorulacak bir sey yok. */
    if (blok && blok.kilit) { kartiKilitle(); geriAlKilit = null; return; }

    /* CANLI KART: öneriler / tanım kontrolü arka planda sürüyorsa
       yoklamayı başlat. */
    if (alan.oneri_is && (durumlar.length
            || (kontrol && kontrol.toplam && !kontrol.baslamadi))) {
        if (durumlar.length)
            oneriKilidi(false, 0, alan.oneri_toplam || durumlar.length);
        oneriYokla(String(alan.oneri_is));
    }
    yeniOdak = birincil;
}

function kolonAdBolumuEkle(kart, ka, ilkKilit, adimda) {
    let kilitli = ilkKilit;
    const topluBtn = [];
    const kb = elYap("div", "dg-tablo-bas dg-kontrol-bas");
    const kbas = elYap("div", "dg-tablo-baslik", ka.baslik || "Kolon Adı Önerileri");
    if (ka.bilgi) kbas.appendChild(bolmeBilgiSimgesi(ka.bilgi, ka.baslik));
    kb.appendChild(kbas);
    kart.appendChild(kb);
    const durumEl = elYap("div", "dg-not", "");
    kart.appendChild(durumEl);
    const hataEl = elYap("div", "dg-oneri-hata");
    hataEl.hidden = true;
    kart.appendChild(hataEl);
    const ust = elYap("div", "dg-tablo-ust");
    ust.appendChild(dgLejant([["dg-l-renksiz", "Önerilen"], ["dg-l-duzenlendi", "Düzenlendi"]]));
    const toplu = elYap("div", "dg-toplu");
    const satirlar = [];
    [[true, "Tümünü Seç"], [false, "Tümünü Temizle"]].forEach(([d, e]) => {
        const b = elYap("button", "dg-toplu-btn", e);
        b.type = "button"; b.disabled = kilitli;
        b.onclick = () => satirlar.forEach(x => { x.kutu.checked = d; });
        toplu.appendChild(b);
        topluBtn.push(b);
    });
    const kaydetBtn = elYap("button", "dg-toplu-btn", "Seçilen Adları Kaydet");
    kaydetBtn.type = "button"; kaydetBtn.disabled = kilitli;
    /* Adım kartında kayıt birincil düğmeyle yapılır. */
    if (!adimda) toplu.appendChild(kaydetBtn);
    ust.appendChild(toplu);
    kart.appendChild(ust);
    const sar = elYap("div", "dg-tablo-sar");
    const tablo = elYap("table", "dg-tablo dg-kolonad-tablo");
    const th = document.createElement("thead"), hr = document.createElement("tr");
    ["Mevcut Ad", "Yeni Ad", "Uygula"].forEach(h => hr.appendChild(elYap("th", "", h)));
    th.appendChild(hr); tablo.appendChild(th);
    const tb = document.createElement("tbody");
    tablo.appendChild(tb); sar.appendChild(tablo); kart.appendChild(sar);

    function ciz(liste) {
        tb.textContent = "";
        satirlar.length = 0;
        (liste || []).forEach(r => {
            const tr = elYap("tr", "dg-satir");
            const tdK = elYap("td", "dg-kolon", r.kolon);
            if (r.gerekce) tdK.appendChild(bolmeBilgiSimgesi(tireSade(r.gerekce), r.kolon));
            tr.appendChild(tdK);
            const tdA = elYap("td", "dg-aciklama-hucre");
            const g = document.createElement("input");
            g.type = "text"; g.className = "dg-giris";
            g.value = r.yeni_ad || ""; g.disabled = kilitli;
            g.setAttribute("aria-label", r.kolon + " yeni adı");
            tdA.appendChild(g); tr.appendChild(tdA);
            const tdI = elYap("td", "dg-ekle-hucre");
            const kutu = document.createElement("input");
            kutu.type = "checkbox"; kutu.className = "dg-ekle";
            kutu.checked = !!r.kayitli; kutu.disabled = kilitli;
            tdI.appendChild(kutu); tr.appendChild(tdI);
            const vurgu = () => {
                const m = g.value.trim();
                tr.classList.toggle("dg-duzenlendi", !!m && m !== String(r.oneri || "").trim());
            };
            g.addEventListener("input", () => { vurgu(); if (g.value.trim()) kutu.checked = true; });
            vurgu();
            satirlar.push({ r, g, kutu });
            tb.appendChild(tr);
        });
        const kayitli = (liste || []).filter(r => r.kayitli).length;
        durumEl.textContent = adimda
            ? ftBinlik((liste || []).length) + " kolon için ad önerisi. Uygula işaretli adlar "
              + "Değişken Kontrolü kaydedilince AMP_VERISETI ve AMP_SOZLUK'ta uygulanır."
            : ftBinlik((liste || []).length) + " kolon için ad önerisi; "
              + ftBinlik(kayitli) + " tanesi kaydedildi. Kaydedilen adlar Değişken Kontrolü "
              + "kaydedilince AMP_VERISETI ve AMP_SOZLUK'ta uygulanır.";
    }
    ciz(ka.satirlar);

    kaydetBtn.onclick = () => {
        kaydetBtn.disabled = true;
        hataEl.hidden = true;
        const govde = satirlar.map(x => ({ kolon: x.r.kolon, yeni_ad: x.g.value.trim(),
                                           uygula: x.kutu.checked }));
        fetch(getWebAppBackendUrl("kolon_ad_kaydet"), {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify(ftKimlikGovdesi({ kolonlar: govde }))
        })
        .then(r => r.json())
        .then(d => {
            kaydetBtn.disabled = false;
            if (d && d.kolon_ad) ciz(d.kolon_ad.satirlar);
            if (!d || d.tamam !== true) {
                hataEl.textContent = tireSade((d && d.hata) || "Kolon adları kaydedilemedi.");
                hataEl.hidden = false;
            }
        })
        .catch(e => {
            kaydetBtn.disabled = false;
            hataEl.textContent = "Kolon adları kaydedilemedi: " + e;
            hataEl.hidden = false;
        });
    };
    return {
        deger: () => satirlar.map(x => ({ kolon: x.r.kolon, yeni_ad: x.g.value.trim(),
                                          uygula: x.kutu.checked })),
        /* Kart kilitlenince / Geri Al ile açılınca. */
        kilitle: k => {
            kilitli = k;
            satirlar.forEach(x => { x.g.disabled = k; x.kutu.disabled = k; });
            topluBtn.concat([kaydetBtn]).forEach(b => { b.disabled = k; });
        }
    };
}

function kisaltmaBolumuEkle(kart, ka, ilkKilit, adimda, degisti) {
    let kilitli = ilkKilit;
    const topluBtn = [];
    const kb = elYap("div", "dg-tablo-bas dg-kontrol-bas");
    const kbas = elYap("div", "dg-tablo-baslik", ka.baslik || "Kısaltma Sözlüğü");
    /* "i" YERİNE KISA AÇIKLAMA başlığın altında (kullanıcı kararı). */
    kb.appendChild(kbas);
    kart.appendChild(kb);
    if (ka.aciklama) kart.appendChild(elYap("div", "dg-kisa-aciklama", tireSade(ka.aciklama)));
    /* DURUM BİLGİSİ (kullanıcı kararı): tablonun altında, onay düğmesinin
       üstünde, bilgilendirme kutusu olarak; aşağıda tablodan sonra eklenir. */
    const durumEl = elYap("div", "dg-bilgi-kutu", "");
    const hataEl = elYap("div", "dg-oneri-hata");
    hataEl.hidden = true;
    kart.appendChild(hataEl);
    const satirlar = [];
    const ust = elYap("div", "dg-tablo-ust");
    /* "Önerilen": temel sözlük, sözlükten çıkarım ya da dil modeli
       (kaynağı satırın Kaynak sütununda yazar). */
    /* 01.2 SADE RENK: renksiz aynı / normal, sarı dikkat (anlam boş,
       sözlük ve genel farklı, uyarılı), yeşil sizin düzenlediğiniz. Anlam'a
       hangisinin yazıldığını ✓ gösterir; hafızada onaylı olan "Seç" işaretli. */
    /* Sarı yalnız sözlükteki anlam DEĞİŞTİYSE (dil modeli doğru, ikisi de
       yanlış, yanlış kısaltma), boşsa ya da uyarı varsa; "sözlük doğru" ve
       "ikisi aynı" renksiz (kullanıcı kararı). */
    ust.appendChild(dgLejant([["dg-l-renksiz", "Sözlük Doğru"],
                              ["dg-l-dikkat", "Sözlük Değişti, Öneri Var, Boş ya da Uyarılı"],
                              ["dg-l-duzenlendi", "Düzenlendi"]]));
    const toplu = elYap("div", "dg-toplu");
    const kaydetBtn = elYap("button", "dg-toplu-btn dg-kisaltma-kaydet", "Seçilenleri Hafızaya Kaydet");
    kaydetBtn.type = "button";
    [[true, "Tümünü Seç"], [false, "Tümünü Temizle"]].forEach(([d, e]) => {
        const b = elYap("button", "dg-toplu-btn", e);
        b.type = "button"; b.disabled = kilitli;
        b.onclick = () => satirlar.forEach(x => { if (!x.kutu.disabled) x.kutu.checked = d; });
        toplu.appendChild(b);
        topluBtn.push(b);
    });
    kaydetBtn.disabled = kilitli;
    /* Adım kartında hafızaya kayıt birincil düğmeyle yapılır. */
    if (!adimda) toplu.appendChild(kaydetBtn);
    ust.appendChild(toplu);
    kart.appendChild(ust);
    /* EXCEL (kullanıcı kararı): önerilen anlamlar örnek kolonları ve
       anlamı taşımayan (çelişen) örneklerle birlikte indirilir; dosya
       çalışma klasörüne de yazılır. Son sütun kullanıcının kararı için. */
    const kisaExcel = excelSeridiYap("kisaltma", "Örnekleriyle Excel Olarak İndir", "");
    kisaExcel.ac(true);
    kart.insertBefore(kisaExcel.el, ust);
    const sar = elYap("div", "dg-tablo-sar");
    const tablo = elYap("table", "dg-tablo dg-kisaltma-tablo");
    const th = document.createElement("thead"), hr = document.createElement("tr");
    /* İKİ KAYNAK AYRI SÜTUNDA (kullanıcı kararı): sözlüğün ve dil
       modelinin dediği yan yana; Anlam'a daha mantıklı olan yazılır,
       kullanıcı düzenler. */
    /* Not sütunu kaldırıldı (kullanıcı kararı: çok yer kaplıyor); karar,
       gerekçe ve uyarılar kısaltmanın yanındaki "i"de. */
    /* Anlam sütunu "LLM Karar" (kullanıcı kararı): değer, dil modellerinin
       iki kaynak arasındaki kararıdır; düzenlenebilir. */
    ["Kısaltma", "LLM Sözlük", "LLM Genel", "LLM Karar", "Önerilen Kısaltma", "Seç"]
        .forEach(h => hr.appendChild(elYap("th", "", h)));
    th.appendChild(hr); tablo.appendChild(th);
    const tb = document.createElement("tbody");
    tablo.appendChild(tb); sar.appendChild(tablo); kart.appendChild(sar);
    /* BİRLEŞTİRME ÖNERİLERİ (kullanıcı kararı): her parça ayrı kısaltma;
       hep yan yana geçen ve anlamı karışan parçalar için dil modeli
       birleştirme önerir, kabul kullanıcının. Yalnız öneri varsa görünür. */
    const bSar = elYap("div", "dg-birlesik");
    bSar.appendChild(elYap("div", "dg-tablo-baslik dg-birlesik-baslik", "Birleştirme Önerileri"));
    const bAck = elYap("div", "dg-kisa-aciklama", "");
    bSar.appendChild(bAck);
    const bTablo = elYap("table", "dg-tablo dg-birlesik-tablo");
    const bTh = document.createElement("thead"), bHr = document.createElement("tr");
    ["Kısaltmalar", "Ayrı Anlamlar", "Birlikte Anlam", "Birleştir"]
        .forEach(h => bHr.appendChild(elYap("th", "", h)));
    bTh.appendChild(bHr); bTablo.appendChild(bTh);
    const bTb = document.createElement("tbody");
    bTablo.appendChild(bTb); bSar.appendChild(bTablo);
    bSar.hidden = true;
    kart.appendChild(bSar);
    kart.appendChild(durumEl);
    const bSatirlar = [];
    function birlesikCiz(liste) {
        bTb.textContent = "";
        bSatirlar.length = 0;
        bAck.textContent = tireSade(ka.birlesik_aciklama || "");
        (liste || []).forEach(r => {
            const tr = elYap("tr", "dg-satir");
            const tdK = elYap("td", "dg-kolon dg-kisaltma-ad", (r.parcalar || []).join(" + "));
            const iMetni = [r.gerekce ? "Gerekçe: " + r.gerekce : "",
                            r.kolon ? ftBinlik(r.kolon) + " kolonda yan yana" : "",
                            r.onayli ? "Hafızada onaylı" : ""].filter(Boolean).join("\n\n");
            if (iMetni) tdK.appendChild(bolmeBilgiSimgesi(tireSade(iMetni), r.kisaltma));
            tr.appendChild(tdK);
            tr.appendChild(elYap("td", "dg-kaynak-deger", r.ayri ? tireSade(r.ayri) : BOS_SIMGE));
            const tdA = elYap("td", "dg-aciklama-hucre");
            const g = document.createElement("input");
            g.type = "text"; g.className = "dg-giris";
            g.value = tireSade(r.anlam || ""); g.disabled = kilitli;
            g.setAttribute("aria-label", r.kisaltma + " birlikte anlamı");
            tdA.appendChild(g); tr.appendChild(tdA);
            const tdI = elYap("td", "dg-ekle-hucre");
            const kutu = document.createElement("input");
            kutu.type = "checkbox"; kutu.className = "dg-ekle";
            kutu.checked = !!r.onayli; kutu.disabled = kilitli;
            kutu.setAttribute("aria-label", r.kisaltma + " birleştir");
            tdI.appendChild(kutu); tr.appendChild(tdI);
            /* Öneri sarı (karar sizde); düzenlenirse yeşil. */
            const vurgu = () => {
                const ell = g.value.trim() !== tireSade(r.anlam || "").trim();
                tr.classList.toggle("dg-duzenlendi", ell);
                tr.classList.toggle("dg-farkli", !ell && !r.onayli);
            };
            g.addEventListener("input", vurgu);
            vurgu();
            bSatirlar.push({ r, g, kutu });
            bTb.appendChild(tr);
        });
        bSar.hidden = !(liste || []).length;
    }

    function ciz(liste) {
        tb.textContent = "";
        satirlar.length = 0;
        (liste || []).forEach(r => {
            const tr = elYap("tr", "dg-satir");
            /* ÖRNEKLER KISALTMANIN YANINDA "i" (kullanıcı kararı: ayrı
               sütun gereksiz). Anlamı onaylatan kolon adları ve sözlükteki
               açıklamaları; tanımı anlamı taşıyan yoksa herhangi örnekler
               gelir, kullanıcı çelişkiyi görür. */
            const tdK = elYap("td", "dg-kolon dg-kisaltma-ad", r.kisaltma);
            const orn = r.ornekler || [];
            /* Eski Not sütununun içeriği (karar, gerekçe, uyarı) + örnekler. */
            const notMetni = [r.onayli ? "Hafızada onaylı" : "", r.kanit || "",
                              r.uyari ? "Uyarı: " + r.uyari : ""].filter(Boolean).join("\n\n");
            const iMetni = [notMetni, orn.length ? "Örnek kolonlar:\n\n"
                + orn.map(o => o.kolon + ": " + tireSade(o.tanim)).join("\n\n") : ""]
                .filter(Boolean).join("\n\n");
            if (iMetni) tdK.appendChild(bolmeBilgiSimgesi(tireSade(iMetni), r.kisaltma));
            /* SAYI DEĞERLİ KALIP (kullanıcı bildirimi: harf kısmına inince
               sayının anlamı kayboluyordu): adlardaki biçimler altta. */
            if ((r.sayili || []).length)
                tdK.appendChild(elYap("div", "dg-tip", r.sayili.join(" · ")));
            if (r.uyari) tr.classList.add("dg-uyarili");
            tr.appendChild(tdK);
            /* Kaynak sütunları (salt okunur). Seçilen kaynak işaretlenir. */
            const tdS = elYap("td", "dg-kaynak-deger" + (r.secilen === "sozluk" ? " secili" : "")
                    + (r.bekliyor || !r.sozlukten ? " dg-kaynak-yok" : ""));
            tdS.appendChild(elYap("span", "dg-secim-isaret", "✓"));
            /* LLM Sözlük: dil modelinin tanımlardan okuduğu anlam. Sonucu
               yoksa sözlükteki kelime sayımı (altında belirtilir). */
            tdS.appendChild(document.createTextNode(r.bekliyor ? "bekleniyor…"
                : r.sozlukten ? tireSade(r.sozlukten) : BOS_SIMGE));
            if (r.onceki_sozluk) tdS.appendChild(elYap("div", "dg-tip", "önceki sözlüklerden"));
            else if (!r.bekliyor && r.sozluk_kaynak === "istatistik")
                tdS.appendChild(elYap("div", "dg-tip", "kelime sayımı"));
            tr.appendChild(tdS);
            /* Genel anlamı yok / emin değil / sonuç yok: ∅ (kullanıcı kararı);
               hangisi olduğu "i"deki kararda yazar. */
            const dmMetin = { bekliyor: "bekleniyor…", emin_degil: BOS_SIMGE,
                              bilinmiyor: BOS_SIMGE, yok: BOS_SIMGE };
            const tdD = elYap("td", "dg-kaynak-deger" + (r.secilen === "dil_modeli" ? " secili" : "")
                    + (r.dm_durum && r.dm_durum !== "var" ? " dg-kaynak-yok" : ""));
            tdD.appendChild(elYap("span", "dg-secim-isaret", "✓"));
            tdD.appendChild(document.createTextNode(r.dm_durum && r.dm_durum !== "var"
                ? dmMetin[r.dm_durum] || BOS_SIMGE : tireSade(r.dil_modeli || "")));
            tr.appendChild(tdD);
            const tdA = elYap("td", "dg-aciklama-hucre");
            const g = document.createElement("input");
            g.type = "text"; g.className = "dg-giris";
            /* Dil modeli sonucu gelmemiş satır kilitli (kullanıcı kararı):
               sonuç gelince yoklama satırı açar. */
            /* Sonucu gelmemiş satırda karar boş görünür (kullanıcı
               bildirimi: önce kelime sayımı yazıyor, sonra değişiyordu). */
            g.value = r.bekliyor ? "" : tireSade(r.anlam || "");
            g.disabled = kilitli || !!r.bekliyor;
            if (r.bekliyor) g.placeholder = "bekleniyor…";
            g.setAttribute("aria-label", r.kisaltma + " anlamı");
            if (r.bekliyor) tr.classList.add("dg-bekliyor");
            tdA.appendChild(g);
            /* Sayı değerli kalıpta anlam sayıyla okunur: <K>00 = <anlam> 00. */
            const sayiliEl = elYap("div", "dg-tip", "");
            const sayiliYaz = () => {
                const a = g.value.trim();
                sayiliEl.textContent = a && (r.sayili || []).length
                    ? r.sayili.slice(0, 1).map(b => b + " = " + a + " " + b.replace(/^[A-Z]+/, "").replace(/_/g, "-")).join("")
                      + (r.sayili.length > 1 ? " …" : "") : "";
            };
            if ((r.sayili || []).length) { tdA.appendChild(sayiliEl); g.addEventListener("input", sayiliYaz); sayiliYaz(); }
            tr.appendChild(tdA);
            /* YANILTICI KISALTMA için daha açık kısaltma (dil modeli önerir,
               boşaltılabilir); kabul edilen Kolon Adı Önerileri'ne gider. */
            const tdY = elYap("td", "dg-aciklama-hucre");
            const y = document.createElement("input");
            y.type = "text"; y.className = "dg-giris dg-yeni-kisa";
            y.value = r.yeni_kisaltma || ""; y.maxLength = 24;
            y.disabled = kilitli || !!r.bekliyor;
            y.setAttribute("aria-label", r.kisaltma + " için önerilen kısaltma");
            tdY.appendChild(y);
            /* Yeni kısaltmanın anlamı (bu kolonlardaki gerçek anlam). */
            const yAnlam = elYap("div", "dg-tip", r.yeni_anlam ? "= " + tireSade(r.yeni_anlam) : "");
            tdY.appendChild(yAnlam);
            y.addEventListener("input", () => {
                const b = y.value.toUpperCase().replace(/[^A-Z0-9_]/g, "");
                if (b !== y.value) y.value = b;
                yAnlam.textContent = y.value && (r.yeni_anlam || r.sozlukten)
                    ? "= " + tireSade(r.yeni_anlam || r.sozlukten) : "";
                /* KISALTMA YANLIŞ SEÇİLMİŞ satırda öneri boşaltılırsa
                   kolonlar eski kısaltmayla kalır; anlam bu çalışmada
                   sözlükteki anlama döner (geri yazılınca genel anlama). */
                if (r.secim === "kisaltma_yanlis" && r.sozlukten) {
                    const genel = tireSade(r.anlam || ""), soz = tireSade(r.sozlukten);
                    if (!y.value && g.value.trim() === genel) g.value = soz;
                    else if (y.value && g.value.trim() === soz) g.value = genel;
                    g.dispatchEvent(new Event("input"));
                }
            });
            tr.appendChild(tdY);
            const tdI = elYap("td", "dg-ekle-hucre");
            const kutu = document.createElement("input");
            kutu.type = "checkbox"; kutu.className = "dg-ekle";
            kutu.checked = !!r.onayli; kutu.disabled = kilitli || !!r.bekliyor;
            tdI.appendChild(kutu); tr.appendChild(tdI);
            const vurgu = () => {
                const m = g.value.trim();
                const ayni = v => !!m && m === tireSade(String(v || "")).trim();
                /* Renk, Anlam'daki değerin NEREDEN geldiğine göre: kullanıcı
                   sözlükteki ya da dil modelindeki değeri yazarsa o kaynağın
                   rengine döner; başka bir şey yazarsa yeşil. */
                const dmDen = r.dm_durum === "var" && ayni(r.dil_modeli);
                const sozDen = ayni(r.sozlukten);
                let tur = "";
                if (r.bekliyor) tur = "";
                else if (!m) tur = "bos";
                else if (r.onayli && ayni(r.anlam)) tur = "hafiza";
                /* Kaynaklardan biri ya da DİL MODELİNİN KARARI (ikisi de
                   yanlışsa yazdığı anlam, dokunulmamış) ise renk uyuma göre. */
                else if (dmDen || sozDen || ayni(r.anlam))
                    tur = r.uyum === "ayni" ? "ayni" : r.uyum === "farkli" ? "farkli" : "";
                else tur = "eklendi";
                tr.classList.toggle("dg-bos", tur === "bos");
                tr.classList.toggle("dg-hafiza-renk", tur === "hafiza");
                tr.classList.toggle("dg-llm", tur === "ayni");
                tr.classList.toggle("dg-farkli", tur === "farkli");
                tr.classList.toggle("dg-duzenlendi", tur === "eklendi");
                tdS.classList.toggle("secili", sozDen);
                tdD.classList.toggle("secili", dmDen);
            };
            g.addEventListener("input", vurgu);
            vurgu();
            satirlar.push({ r, g, kutu, y });
            tb.appendChild(tr);
        });
        const onayli = (liste || []).filter(r => r.onayli).length;
        durumEl.textContent = ((liste || []).length
            ? ftBinlik((liste || []).length) + " kısaltma; " + ftBinlik(onayli) + " tanesi hafızada onaylı."
            : "Kolon adlarından güvenilir bir kısaltma çıkarılamadı.")
            + (ka.not ? " " + tireSade(ka.not) : "");
        sar.hidden = ust.hidden = !(liste || []).length;
    }
    ciz(ka.satirlar);
    birlesikCiz(ka.birlesik);

    /* YOKLAMA (kullanıcı bildirimi: bekleme): kart beklemeden gelir; dil
       modeli kontrolü sürüyorsa 5 sn'de bir sorulur, bitince satırlar
       güncellenir. Kullanıcının elle değiştirdiği satır EZİLMEZ. */
    let yoklamaSayisi = 0;
    function yokla() {
        if (kilitli || !document.body.contains(tb)) return;
        if (yoklamaSayisi++ > 200) {
            /* 10 dakikada bitmedi: onay kilidi açılır, not yazar. */
            ka.dm = "zaman_asimi";
            durumEl.textContent += " Dil modeli kontrolü 10 dakikada bitmedi; liste kural tabanlı.";
            if (degisti) degisti();
            return;
        }
        fetch(getWebAppBackendUrl("kisaltma_alani") + "?oturum_id=" + encodeURIComponent(OTURUM_ID))
            .then(r => r.json())
            .then(d => {
                const yeni = d && d.kisaltma;
                if (!yeni) return setTimeout(yokla, 3000);
                ka.not = yeni.not || "";
                ka.dm = yeni.dm;
                const elle = {};
                satirlar.forEach(x => {
                    if (x.r.bekliyor) return;
                    if (x.g.value.trim() !== String(x.r.anlam || "").trim() || x.kutu.checked !== !!x.r.onayli
                            || x.y.value !== String(x.r.yeni_kisaltma || ""))
                        elle[x.r.kisaltma] = { anlam: x.g.value, kutu: x.kutu.checked, yeni: x.y.value };
                });
                ciz(yeni.satirlar);
                satirlar.forEach(x => {
                    const e = elle[x.r.kisaltma];
                    if (e) { x.g.value = e.anlam; x.kutu.checked = e.kutu; x.y.value = e.yeni;
                             x.g.dispatchEvent(new Event("input")); }
                });
                /* Birleştirme önerileri: elle değişen satır ezilmez. */
                const bElle = {};
                bSatirlar.forEach(x => {
                    if (x.g.value.trim() !== tireSade(x.r.anlam || "").trim() || x.kutu.checked !== !!x.r.onayli)
                        bElle[x.r.kisaltma] = { anlam: x.g.value, kutu: x.kutu.checked };
                });
                ka.birlesik_aciklama = yeni.birlesik_aciklama || ka.birlesik_aciklama;
                birlesikCiz(yeni.birlesik);
                bSatirlar.forEach(x => {
                    const e = bElle[x.r.kisaltma];
                    if (e) { x.g.value = e.anlam; x.kutu.checked = e.kutu; x.g.dispatchEvent(new Event("input")); }
                });
                if (yeni.dm === "calisiyor") setTimeout(yokla, 3000);
                if (degisti) degisti();
            })
            .catch(() => setTimeout(yokla, 8000));
    }
    if (ka.dm === "calisiyor") setTimeout(yokla, 3000);

    kaydetBtn.onclick = () => {
        kaydetBtn.disabled = true;
        hataEl.hidden = true;
        const govde = satirlar.map(x => ({ kisaltma: x.r.kisaltma, anlam: x.g.value.trim(),
            cikarilan: x.r.cikarilan || "", kaydet: x.kutu.checked }));
        fetch(getWebAppBackendUrl("kisaltma_kaydet"), {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify(ftKimlikGovdesi({ kisaltmalar: govde }))
        })
        .then(r => r.json())
        .then(d => {
            kaydetBtn.disabled = false;
            if (d && d.kisaltma) ciz(d.kisaltma.satirlar);
            if (!d || d.tamam !== true) {
                hataEl.textContent = tireSade((d && d.hata) || "Kısaltmalar kaydedilemedi.");
                hataEl.hidden = false;
            }
        })
        .catch(e => {
            kaydetBtn.disabled = false;
            hataEl.textContent = "Kısaltmalar kaydedilemedi: " + e;
            hataEl.hidden = false;
        });
    };
    return {
        /* Sonucu gelmemiş (kilitli) satır kelime sayımıyla gider. */
        deger: () => satirlar.map(x => ({ kisaltma: x.r.kisaltma,
            anlam: x.r.bekliyor ? String(x.r.anlam || "").trim() : x.g.value.trim(),
            cikarilan: x.r.cikarilan || "", kaydet: x.kutu.checked,
            yeni_kisaltma: x.y.value.trim(),
            yeni_anlam: x.y.value.trim() ? (x.r.yeni_anlam || x.r.sozlukten || "") : "" })),
        birlesik: () => bSatirlar.map(x => ({ kisaltma: x.r.kisaltma, anlam: x.g.value.trim(),
            kabul: x.kutu.checked })),
        kilitle: k => {
            kilitli = k;
            bSatirlar.forEach(x => { x.g.disabled = k; x.kutu.disabled = k; });
            satirlar.forEach(x => { x.g.disabled = k || !!x.r.bekliyor; x.kutu.disabled = k || !!x.r.bekliyor;
                                    x.y.disabled = k || !!x.r.bekliyor; });
            topluBtn.concat([kaydetBtn]).forEach(b => { b.disabled = k; });
        },
        /* Dil modeli kontrolü sürüyor mu (adım kartında onay kilidi). */
        bekliyor: () => ka.dm === "calisiyor"
    };
}

/* ==================== Aralık Önerileri kartı ====================
   SFA'nın aralık ve eksik işareti önerileri; sözlük tanımları kartıyla
   aynı düzen (kullanıcı kararı): satır başına "Uygula" kutusu, Tümünü Seç /
   Tümünü Temizle, tek birincil düğme. Öneri metninin altında metrik
   kontrolleri (✓ / ✗) ve yapay zekâ seçildiyse gerekçesi yazar. */
/* ---- tip: sfa_karar ----
   SFA adımının kartı. Yapay zekâ arka planda her değişken için karar
   verir; kart ilerlemeyi gösterir ve kararları sağ paneldeki Değişken
   Analizi sekmesine yönlendirir. "Kararları Onayla" akışı ilerletir;
   yapay zekâ bitmeden basılırsa kalan değişkenlerde kural kararı geçer. */
function sfaKartiEkle(alan, blok) {
    const kart = elYap("div", "secim-kart dg-kart sfa-kart");
    const durum = elYap("div", "sfa-kart-durum");
    const cubuk = elYap("div", "sfa-ilerleme");
    const dolgu = elYap("div", "sfa-ilerleme-dolgu");
    cubuk.appendChild(dolgu);
    kart.appendChild(durum);
    kart.appendChild(cubuk);
    const hata = elYap("div", "dg-oneri-hata");
    hata.hidden = true;
    kart.appendChild(hata);

    const dugmeler = elYap("div", "onay-dugmeler dg-dugmeler");
    const ac = elYap("button", "secim-onay ikincil", "Değişken Analizini Aç");
    ac.type = "button";
    ac.onclick = () => analizSekmeAc("degisken");
    const birincil = elYap("button", "secim-onay dg-birincil", alan.buton || "Kararları Onayla");
    birincil.type = "button";
    dugmeler.appendChild(ac);
    dugmeler.appendChild(birincil);
    kart.appendChild(dugmeler);

    function kilitle(evet) {
        kart.classList.toggle("kilitli", evet);
        birincil.disabled = evet;
    }
    birincil.onclick = () => {
        if (mesgul || birincil.disabled) return;
        kilitle(true);
        geriAlKilit = () => kilitle(false);
        gonder(alan.sablon || "sfa kararları: onaylandı", false);
    };
    const toplam = Number(alan.toplam || 0);
    function goster(d) {
        const biten = Math.min(Number((d && d.biten) || 0), toplam || Infinity);
        const calisiyor = d && d.durum === "calisiyor";
        dolgu.style.width = (toplam ? Math.round(100 * biten / toplam) : 0) + "%";
        cubuk.hidden = !calisiyor;
        if (calisiyor)
            durum.textContent = "Yapay zekâ karar veriyor · " + biten.toLocaleString("tr-TR")
                + " / " + toplam.toLocaleString("tr-TR") + " değişken. Kararlar geldikçe "
                + "Değişken Analizi sekmesine düşer; beklemeden onaylarsanız kalan "
                + "değişkenlerde kural tabanlı karar geçerli olur.";
        else if (d && d.durum === "bitti")
            durum.textContent = "Yapay zekâ " + biten.toLocaleString("tr-TR") + " değişken için "
                + "karar verdi. Kararları Değişken Analizi sekmesinde inceleyip değiştirebilirsiniz.";
        else
            durum.textContent = "Kararlar Değişken Analizi sekmesinde; inceleyip "
                + "değiştirebilirsiniz.";
        hata.hidden = !(d && d.hata);
        hata.textContent = (d && d.hata) ? tireSade(d.hata) : "";
    }
    let sonBiten = -1;
    function yokla(isId) {
        fetch(getWebAppBackendUrl("sfa_ai") + "?is=" + encodeURIComponent(isId))
            .then(r => r.json())
            .then(d => {
                if (!kart.isConnected) return;
                goster(d);
                /* Yeni kararlar geldiyse açık SFA listesi tazelenir */
                if (d && d.biten !== sonBiten) {
                    sonBiten = d.biten;
                    /* Açık bir karar formu varsa dokunulmaz: kullanıcının
                       kaydetmediği seçimler silinmesin. */
                    if (aktifAnalizSekme === "degisken" && ARALIK.liste && !ARALIK.acik) {
                        ARALIK.liste = null;
                        ARALIK.detay = {};
                        analizCiz("degisken");
                    }
                }
                if (d && d.durum === "calisiyor" && !kart.classList.contains("kilitli"))
                    setTimeout(() => yokla(isId), 3000);
            })
            .catch(() => {});
    }
    goster(null);
    (adimKabiAl(blok) || sohbetEl).appendChild(kart);
    sohbetKaydir();
    if (blok && blok.kilit) { kilitle(true); geriAlKilit = null; return; }
    if (alan.ai_is) yokla(String(alan.ai_is));
    yeniOdak = birincil;
}

/* ---- tip: teyit (bolme oncesi son gozden gecirme) ----
   SOZLESME7 §6. Kart tek satirlik: baslik, aciklama, ozet ve TEK
   birincil dugme. Asil is sag panelde yapiliyor; kart cizilince
   alan.hedef sekmesi ACILIR ki kullanici nereye bakacagini aramasin. */
/* ==================== Bölme Stratejisi kartı ====================
   EKRAN SIRASI (kullanıcı kararı: "daha basitçe sadece seçimli yan yana
   iki kutuda bir seçim ... altta da genel olarak açıklamalar ... detay
   istenirse bakılabilir tarzda açılabilir bir opsiyonlu sekmeyle, eğer
   istenmiyorsa zaten otomatik kapalı"):

     1. yan yana İKİ SEÇİM KUTUSU  (Önerilen / Özel) - sayfanın merkezi
     2. seçilenin KISA ÖZETİ
     3. tek cümlelik gerekçe
     4. [Detayları göster]  - VARSAYILAN KAPALI
     5. tek birincil düğme

   Önceki sürümde 1. sırada üç paragraf metin, 2. sırada seçim vardı;
   kullanıcı karar vermeden önce okumak zorunda kalıyordu. Uzun anlatım
   (gerekçe maddeleri, kısıtlar, terim karşılıkları) 4. maddedeki açılır
   alana taşındı - kaybolmadı, ikinci plana alındı.

   UYARILAR DETAYA GİRMEDİ, görünür kaldı: "test seti yalnızca 33 satır"
   bir açıklama değil, bir tehlike işareti. Kapalı bir akordeonun altına
   koymak, bozuk bir bölmeyle devam etmenin en kolay yolu olurdu. */
const BOLME = {
    kart: null, govde: null, alan: null, blok: null,
    durumEl: null, onayBtn: null,
    /* Gövde her çizildikten sonra çağrılır: birincil düğmenin pasiflik
       durumu ve etiketi seçilen moda ve kilide bağlı. */
    sonrasi: null,
    mod: "oneri", gonderildi: false,
    /* Seçili panelin birincil düğmesi bunu çağırır (kart düzeyinde ayrı
       bir "Devam Et" düğmesi yok: karar panelin içinde veriliyor). */
    onayla: null,
    gerekceAcik: false,      // "Öneri gerekçesi" açık mı
    sozlukAcik: {},          // panel başına "Detaylar ve Terimler"
    ozelAcik: {}             // hangi sayısal alanda "Özel" kutusu açık
};

/* Kip KALMADI: iki sütun aynı anda ekranda. İşlev, taslağın öneriden
   ayrılıp ayrılmadığını söylüyor - kaydetme yolu buna bağlı. */
function bolmeOzellestirildi() { return bfDegisti(); }

/* ---- TEK LİSTE, ÖNERİLEN DEĞERLER ÖNCEDEN SEÇİLİ ----

   Kullanıcı kararı: iki sütun (Önerilen / Özel) aynı 14 satırı iki kez
   çiziyordu. Şimdi TEK liste: her satırda seçenekler çip olarak yan
   yana, önerilen olan seçili ve yeşil noktayla işaretli. Değiştirmek
   için tıklamak yeterli. Önerilenden sapan satır kehribar renkte ve
   yanında "önerilene dön". Üstte "Veri Bölme Stratejisi" çubuğu her
   tıklamada anında güncellenir; her satırın yanında "i" simgesi, hiç
   bilmeyen için yazılmış açıklamayı fareyle gösterir.

   Kıyas EKRANDAKİ CÜMLE üzerinden değil, HAM DEĞERLER üzerinden: arka
   uç önerinin ham ayarlarını gönderiyor (oneri.ayarlar). */
function bolmeOneriAyari(alan) {
    return (alan && alan.oneri && alan.oneri.ayarlar) || null;
}

function bfOneriDegeri(ad) {
    const o = bolmeOneriAyari(BOLME.alan);
    return o ? o[ad] : undefined;
}

/* Karşılaştırma için tek biçim: oran kesir (4 hane), sayılar tam,
   iki seçenekli alanlar "1"/"0", geri kalanı metin. */
function bfKiyasDeger(ad, v) {
    if (v === undefined || v === null) return "";
    if (ad === "test_oran" || ad === "val_oran") {
        let x = bfSayi(v, 0.20);
        if (x > 1) x = x / 100;          // yüzde de kesir de gelebilir
        return String(Math.round(x * 10000));
    }
    if (ad === "val_var") return bfValVar(v) ? "1" : "0";
    if (ad === "katmanla" || ad === "segment_katmanla") return bfKatmanla(v) ? "1" : "0";
    if (ad === "kat" || ad === "seed" || ad === "tekrar" || ad === "gap")
        return String(bfTam(v, 0));
    if (ad === "seedler") return bfSeedListesi(v).join(",");
    return String(v);
}

/* Bu seçenek önerilen mi? (çipteki yeşil nokta) */
function bfOneriMi(ad, deger) {
    const o = bfOneriDegeri(ad);
    if (o === undefined || o === null) return false;
    return bfKiyasDeger(ad, deger) === bfKiyasDeger(ad, o);
}

/* Alan taslakta öneriden farklı mı? Pasif alan (kullanılmayan pay
   gibi) fark sayılmaz: ekranda görünmüyor, sonucu değiştirmiyor. */
function bfAlanFarkli(ad) {
    if (bfTaslakPasif(ad)) return false;
    /* Seed listesi ana seed'den türetildiği sürece "fark" değil;
       tekrar sayısı zaten kendi satırında sayılıyor. */
    if (ad === "seedler")
        return bfSeedListesi(BF.alan.seedler).join(",")
            !== bfSeedListesi(bfTuretilenSeedler(BF.alan.seed, BF.alan.tekrar)).join(",");
    const o = bfOneriDegeri(ad);
    if (o === undefined || o === null) return false;
    return bfKiyasDeger(ad, BF.alan[ad]) !== bfKiyasDeger(ad, o);
}

function bolmeSatirFarkli(sat) {
    return (sat.alanlar || []).some(bfAlanFarkli);
}

function bolmeGorunurSatirlar(alan) {
    return (alan.satirlar || []).filter(sat => bolmeSatirGorunur(sat));
}

function bolmeFarkSayisi(alan) {
    return bolmeGorunurSatirlar(alan).filter(bolmeSatirFarkli).length;
}

/* Verilen alanları önerilen değere döndürür. val_var / cv değişince
   train_kullanimi ikilisi yeniden türetilir (bkz. bfDegistir). */
function bolmeOnerileneDon(alanlar) {
    if (bfPasif()) return;
    (alanlar || []).forEach(ad => {
        const o = bfOneriDegeri(ad);
        if (o === undefined || o === null) return;
        BF.alan[ad] = o;
        if (BOLME.ozelAcik) delete BOLME.ozelAcik[ad];
    });
    BF.alan.train_kullanimi = bfTrainKullanimi(
        bfValVar(BF.alan.val_var), BF.alan.cv);
    BF.acikEksen = true;
    BF.not = "";
    bfTazele();
}

/* Kart açılırken taslak ÖNERİYLE dolar: form sunucudaki kayıtlı (ya da
   varsayılan) değerleri taşıyor, öneri ise veriden hesaplanıyor; ikisi
   farklı olabilir. Kullanıcı daha önce kendi ayarını kaydettiyse
   (mod "ozel") taslak o ayar kalır. */
function bolmeTaslagiOneriyleDoldur(alan) {
    const o = bolmeOneriAyari(alan);
    if (!o || alan.mod === "ozel" || !BF.alan) return;
    Object.keys(o).forEach(k => {
        if (k in BF.alan && o[k] !== undefined && o[k] !== null) BF.alan[k] = o[k];
    });
    BF.acikEksen = false;
    BF.seedlerElle = bfSeedListesi(BF.alan.seedler).join(",")
        !== bfSeedListesi(bfTuretilenSeedler(BF.alan.seed, BF.alan.tekrar)).join(",");
}

/* ---- ÖZET ÇUBUĞU: "Veri Bölme Stratejisi" ----
   Kartın en görünür yeri. Rastgele bölmede üç setin yüzdesi renkli
   çubukta; zamansal bölmede dönem sırası (eğitim dönemleri · gap · son N
   dönem). Her tıklamada yeniden çizilir. */
function bolmeOzetCubukCiz(kok, alan) {
    const kutu = elYap("div", "bolme-ozet");
    const bas = elYap("div", "bolme-ozet-bas");
    bas.appendChild(elYap("b", "", "Veri Bölme Stratejisi"));
    const fark = bolmeFarkSayisi(alan);
    const sag = elYap("span", "bolme-ozet-sag");
    sag.appendChild(elYap("span", "bolme-rozet " + (fark ? "ozel" : "oneri"),
        fark ? "Önerilenden " + fark + " fark" : "Önerilen ayarlar"));
    /* ÖNERİ GEREKÇESİ ayrı bir açılır düğme değil (kullanıcı kararı):
       rozetin yanındaki "i" simgesinde. */
    const o = alan.oneri || {};
    const maddeler = (o.gerekce || []).map(x => "• " + tireSade(x));
    const gerekce = [o.ozet, maddeler.join("\n")].filter(Boolean).join("\n\n");
    if (gerekce) sag.appendChild(bolmeBilgiSimgesi(gerekce, "Neden bu ayarlar önerildi"));
    bas.appendChild(sag);
    kutu.appendChild(bas);

    const a = BF.alan;
    /* HEDEF ORANI ÇUBUKTA (kullanıcı kararı): "Hedef Dağılımı: Korunsun"
       seçiliyse her setin hedef oranı parçanın içinde yazar. Bölme
       uygulandıysa setlerin gerçek oranı, değilse genel oran (katmanlı
       bölmede her set onu taşır). Zamansal bölmede dönem setlerinin oranı
       önceden bilinmez; yalnızca bölme uygulandıysa yazar. */
    const fv = BF.veri || {};
    const gercek = !bfDegisti() ? (fv.set_hedef_oran || {}) : {};
    const hedefYaz = (ad) => {
        if (!bfKatmanla(a.katmanla)) return "";
        let o = gercek[ad];
        if ((o === undefined || o === null) && !bfZamansalMi()) o = fv.hedef_orani;
        if (o === undefined || o === null) return "";
        return "Hedef %" + (100 * Number(o)).toLocaleString("tr-TR",
            { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    };
    if (a.test_tanim === "hazir") {
        kutu.appendChild(elYap("div", "bolme-ozet-alt",
            "Setler veri setindeki bölme kolonundan okunacak."));
    } else if (bfZamansalMi()) {
        const cubuk = elYap("div", "bolme-cubuk");
        const gap = bfTam(a.gap, 0);
        cubuk.appendChild(bolmeCubukParca("egitim", 60, "Train (MS) · önceki dönemler", hedefYaz("egitim")));
        if (gap) cubuk.appendChild(bolmeCubukParca("gap", 8, "gap " + gap));
        cubuk.appendChild(bolmeCubukParca("test", gap ? 32 : 40,
                                          "Validasyon (OOT) · " + bfDonemEtiketi(), hedefYaz("test")));
        kutu.appendChild(cubuk);
    } else {
        const p = bfPaylar();
        const cubuk = elYap("div", "bolme-cubuk");
        const yz = v => Math.round(100 * v);
        /* TAM AD, KISALTMA YOK (kullanıcı kararı). Parça yüzdeyle
           orantılı büyür ama yazısından dar olamaz (bolmeCubukParca). */
        if (p.train > 0) cubuk.appendChild(bolmeCubukParca("egitim", yz(p.train), "Train (MS) %" + yz(p.train), hedefYaz("egitim")));
        if (p.val > 0) cubuk.appendChild(bolmeCubukParca("val", yz(p.val), "Test (OOS) %" + yz(p.val), hedefYaz("val")));
        if (p.test > 0) cubuk.appendChild(bolmeCubukParca("test", yz(p.test), TEST_OOS2 + " %" + yz(p.test), hedefYaz("test")));
        kutu.appendChild(cubuk);
    }

    /* Tek satır özet: çubukta yer almayan ayarlar. */
    const parcalar = [];
    const al = (BF.veri && BF.veri.alanlar) || {};
    const etiket = (ad) => {
        const sec = bfSecenekler(ad, (al[ad] || {}).secenekler, []);
        const b = sec.find(o => bfKiyasDeger(ad, o.anahtar) === bfKiyasDeger(ad, a[ad]));
        return b ? b.etiket : String(a[ad] || "");
    };
    if (a.test_tanim !== "hazir") {
        parcalar.push(["Ayrım", etiket("test_tanim")]);
        if (bfZamansalMi() && bfValVar(a.val_var))
            parcalar.push(["Test (OOS)", "eğitimin " + bfYuzde(bfSayi(a.val_oran, 0.2)) + "'i"]);
        parcalar.push(["Çapraz Doğrulama",
            a.cv === "yok" ? "Yok" : etiket("cv") + ", " + bfTam(a.kat, 5) + " kat"]);
        parcalar.push(["Hedef Dağılımı", bfKatmanla(a.katmanla) ? "korunuyor" : "korunmuyor"]);
        if (BF.veri && BF.veri.segment && BF.veri.segment.kolon && bfKatmanla(a.katmanla))
            parcalar.push(["Segment Dağılımı", bfKatmanla(a.segment_katmanla) ? "korunuyor" : "korunmuyor"]);
        /* Gruplama OTOMATİK: aynı kimliğin birden fazla satırı
           olabiliyorsa kayıtlar bir arada tutulur; ayar değil, bilgi. */
        if (BF.veri && BF.veri.gruplama_kolonu)
            parcalar.push(["Aynı " + BF.veri.gruplama_kolonu, "bir arada tutulur"]);
    }
    if (a.seed_tur === "coklu")
        parcalar.push(["Seed'ler", bfSeedListesi(a.seedler).join(", ") || bfTuretilenSeedler(a.seed, a.tekrar)]);
    else
        parcalar.push(["Seed", String(bfTam(a.seed, 42))]);
    const alt = elYap("div", "bolme-ozet-alt");
    parcalar.forEach(([k, v]) => {
        const sp = elYap("span", "", k + ": ");
        sp.appendChild(elYap("b", "", v));
        alt.appendChild(sp);
    });
    kutu.appendChild(alt);

    bolmeSegmentTablosu(kutu, a);

    /* Bölme hesaplandıysa (kesin satır sayıları) sunucunun özeti de yazılır. */
    const f = BF.veri || {};
    const sunucu = (BF.ozet !== null && BF.ozet !== undefined) ? BF.ozet : (f.ozet || "");
    if (sunucu && f.ozet_kesin && !bfDegisti())
        kutu.appendChild(elYap("div", "bolme-ozet-kesin", sunucu));
    kok.appendChild(kutu);
}

/* ---- SEGMENT TABLOSU (01.4) ----
   Segment kolonu tanımlıysa her segmentin satır sayısı ve hedef (1) oranı
   tek tabloda. Bölme uygulandıysa her setin (Train / Test / Validasyon)
   satırı ve hedef oranı ayrı kolonda; uygulanmadıysa segmentin toplamı.
   Küçük segmentler (bir sette 50 satırın ya da 20 kötünün altı) sarı. */
const SEGMENT_MIN_SATIR = 50, SEGMENT_MIN_KOTU = 20;

function bolmeSegmentTablosu(kok, a) {
    const s = (BF.veri || {}).segment;
    if (!s || !s.kolon) return;
    const yuzde = (k, n) => (k === null || k === undefined || !n) ? "-"
        : "%" + (100 * k / n).toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const sayi = n => Number(n || 0).toLocaleString("tr-TR");
    const kutu = elYap("div", "bolme-segment");
    const bas = elYap("div", "bolme-segment-bas");
    bas.appendChild(elYap("b", "", "Segmentler"));
    bas.appendChild(elYap("span", "", " · " + s.kolon));
    kutu.appendChild(bas);

    const setler = (!bfDegisti() && s.setler && Object.keys(s.setler).length) ? s.setler : null;
    const tablo = elYap("table", "bolme-segment-tablo");
    const htr = document.createElement("tr");
    let kolonlar;
    if (setler) {
        const tur = a.test_tanim;
        const var_ = k => Object.values(setler).some(x => x && x[k]);
        kolonlar = [["train", "Train (MS)"], ["val", "Test (OOS)"],
                    ["test", tur === "rastgele" ? TEST_OOS2 : "Validasyon (OOT)"]]
            .filter(([k]) => var_(k));
        ["Segment"].concat(kolonlar.map(x => x[1])).forEach(h => htr.appendChild(elYap("th", "", h)));
    } else {
        ["Segment", "Satır", "Pay", "Hedef Oranı"].forEach(h => htr.appendChild(elYap("th", "", h)));
    }
    tablo.appendChild(htr);
    const toplam = (s.ozet || []).reduce((t, x) => t + (x.satir || 0), 0);
    const adlar = setler ? Object.keys(setler).sort((x, y) => {
        const n = k => Object.values(setler[k] || {}).reduce((t, v) => t + (v.satir || 0), 0);
        return n(y) - n(x);
    }) : (s.ozet || []).map(x => x.ad);
    adlar.forEach(ad => {
        const tr = document.createElement("tr");
        tr.appendChild(elYap("td", "", ad));
        let kucuk = false;
        if (setler) {
            kolonlar.forEach(([k]) => {
                const st = (setler[ad] || {})[k] || { satir: 0, pozitif: 0 };
                if (st.satir < SEGMENT_MIN_SATIR || st.pozitif < SEGMENT_MIN_KOTU) kucuk = true;
                tr.appendChild(elYap("td", "sayi", sayi(st.satir) + " · " + yuzde(st.pozitif, st.satir)));
            });
        } else {
            const x = (s.ozet || []).find(o => o.ad === ad) || {};
            tr.appendChild(elYap("td", "sayi", sayi(x.satir)));
            tr.appendChild(elYap("td", "sayi", toplam ? "%" + (100 * x.satir / toplam).toLocaleString("tr-TR", { maximumFractionDigits: 1 }) : "-"));
            tr.appendChild(elYap("td", "sayi", yuzde(x.pozitif, x.satir)));
        }
        if (kucuk) { tr.classList.add("kucuk"); tr.title = "Bir sette " + SEGMENT_MIN_SATIR + " satırın ya da " + SEGMENT_MIN_KOTU + " kötünün altında"; }
        tablo.appendChild(tr);
    });
    kutu.appendChild(tablo);
    if (!setler)
        kutu.appendChild(elYap("div", "bolme-segment-not",
            "Setlere göre satır sayısı ve hedef oranı bölme uygulanınca yazılır."
            + ((bfKatmanla(a.katmanla) && bfKatmanla(a.segment_katmanla))
               ? " Segment dağılımı korunduğu için her segmentin her setteki payı ve hedef oranı aynı tutulur."
               : (bfKatmanla(a.katmanla) ? " Yalnızca genel hedef oranı korunur; segmentlerin setlere dağılımı rastgeledir." : ""))));
    kok.appendChild(kutu);
}

/* Parça: flex-grow = yüzde, flex-basis = yazının kendi genişliği.
   Böylece küçük paylı set bile adını tam gösterir; kalan alan
   yüzdelere göre paylaşılır. Yazı kırpılmaz, kesilmez. */
function bolmeCubukParca(sinif, genislik, metin, alt) {
    /* alt: ikinci satır (hedef oranı); varsa parça iki satırlı çizilir,
       çubuk yine tek sıra kalır. */
    const p = elYap("span", "bolme-cubuk-" + sinif + (alt ? " iki-satir" : ""));
    p.appendChild(elYap("span", "bolme-cubuk-ust", metin));
    if (alt) p.appendChild(elYap("span", "bolme-cubuk-alt", alt));
    p.style.flexGrow = String(Math.max(genislik, 1));
    p.title = alt ? metin + " · " + alt : metin;
    return p;
}

/* ---- KISITLAR: tek satırlık kutu ----
   Kısıt yapılamayacak bir seçimi anlatır (dönem kolonu yok -> zamansal
   bölme yok). Seçeneğin kendisi de üstü çizili ve pasif (bfCipDugmesi);
   burada yalnızca ne yapılacağı yazılıyor. */
function bolmeKisitCiz(kok, alan) {
    const liste = alan.kisitlar || (BF.veri && BF.veri.kisitlar) || [];
    if (!liste.length) return;
    const kutu = elYap("div", "bolme-kisit");
    kutu.appendChild(elYap("span", "bolme-kisit-im", "!"));
    const metin = elYap("div", "bolme-kisit-metin");
    liste.forEach(k => metin.appendChild(elYap("div", "", (k && k.metin) || String(k))));
    kutu.appendChild(metin);
    kok.appendChild(kutu);
}

/* Ayar listesi: dört grup, koşullu satırlar. */
function bolmeAyarlariCiz(alan, pasif) {
    const al = (BF.veri && BF.veri.alanlar) || {};
    const kapali = pasif || bfPasif();
    const kok = elYap("div", "bolme-ayarlar");
    const satirlar = bolmeGorunurSatirlar(alan);
    (alan.bolumler || []).forEach(b => {
        const kendi = satirlar.filter(x => x.bolum === b.anahtar);
        if (!kendi.length) return;
        kok.appendChild(elYap("div", "bolme-grup-baslik", b.baslik || ""));
        kendi.forEach(sat => kok.appendChild(bolmeSatirCiz(sat, al, kapali)));
    });
    return kok;
}

/* Satır görünür mü? KARŞILIĞI OLMAYAN SATIR HİÇ ÇİZİLMEZ: "Validasyon
   büyüklüğü" validasyon seti kapalıyken, "Validasyon (OOT) dönemi" rastgele
   bölmede ekranda duruyor ve ikisi de hiçbir şeyi değiştirmiyordu.
   Koşul taslaktan hesaplanıyor. */
function bolmeSatirGorunur(sat) {
    const k = sat.kosul;
    if (!k || !k.alan) return true;
    const kaynak = BF.alan || {};
    return (k.degerler || []).some(
        v => bfKiyasDeger(k.alan, v) === bfKiyasDeger(k.alan, kaynak[k.alan]));
}

/* Bir satır: etiket | çipler (+ "önerilene dön") | i */
function bolmeSatirCiz(sat, al, pasif) {
    const farkli = bolmeSatirFarkli(sat);
    const s = elYap("div", "bolme-satir" + (farkli ? " farkli" : ""));
    s.setAttribute("data-satir", sat.anahtar || "");
    s.appendChild(elYap("div", "bolme-satir-etiket", sat.etiket || ""));

    const govde = elYap("div", "bolme-satir-govde");
    if (!(sat.alanlar || []).length) {
        /* Veriden gelen, bu adımda seçilemeyen değer: Dönem Kolonu,
           Bölme Kolonu. Modelleme Tanımları adımında belirlendi. */
        const kutu = elYap("div", "bolme-cipler");
        kutu.appendChild(elYap("span", "bolme-cip salt", sat.salt || sat.oneri || "-"));
        govde.appendChild(kutu);
    } else {
        (sat.alanlar || []).forEach(ad => {
            const el = bfCipAlani(ad, al, pasif);
            if (el) govde.appendChild(el);
        });
        if (farkli && !pasif) {
            const geri = document.createElement("button");
            geri.type = "button";
            geri.className = "bolme-geri-al";
            geri.textContent = "önerilene dön";
            geri.title = "Bu satırı önerilen değere döndür";
            geri.onclick = (e) => { e.stopPropagation(); bolmeOnerileneDon(sat.alanlar); };
            govde.appendChild(geri);
        }
    }
    s.appendChild(govde);
    s.appendChild(bolmeBilgiSimgesi(sat.bilgi, sat.etiket));
    return s;
}

/* "i" simgesi: fare üzerine gelince (ya da klavyeyle odaklanınca)
   açıklama açılır. Metin arka uçtan geliyor (akis_durum.BOLME_SATIR_BILGI)
   ve hiç bilmeyen için yazıldı; paragraflar boş satırla ayrılıyor. */
function bolmeBilgiSimgesi(metin, baslik) {
    const kap = elYap("span", "bolme-info" + (metin ? "" : " bos"));
    if (!metin) return kap;
    kap.tabIndex = 0;
    kap.setAttribute("role", "button");
    kap.setAttribute("aria-label", "Açıklama: " + tireSade(baslik || ""));
    kap.appendChild(elYap("span", "bolme-info-i", "i"));
    const tip = elYap("div", "bolme-tip");
    tip.setAttribute("role", "tooltip");
    if (baslik) tip.appendChild(elYap("div", "bolme-tip-bas", baslik));
    String(metin).split(/\n\s*\n/).forEach(par => {
        const p = elYap("div", "bolme-tip-p");
        /* Tek satır sonu: satır kırılır (seçenek listesi gibi). */
        par.split("\n").forEach((satir, i) => {
            if (i) p.appendChild(document.createElement("br"));
            p.appendChild(document.createTextNode(tireSade(satir)));
        });
        tip.appendChild(p);
    });
    kap.appendChild(tip);
    /* Tıklama da açar (dokunmatik ekran): odak simgede kalır. */
    kap.onclick = (e) => { e.stopPropagation(); kap.focus(); };
    /* KONUM SABİT (position: fixed) ve JS ile hesaplanıyor: akış içinde
       çizilen balon kartı uzatıp sayfayı aşağı-yukarı oynatıyordu
       (kullanıcı bildirimi). Aşağıya sığmazsa simgenin ÜSTÜNE açılır;
       sağ kenar simgenin sağına hizalı, ekrandan taşmaz. */
    /* UZUN METİN KAYDIRILABİLİR (kullanıcı bildirimi: "yazı uzunsa aşağı
       kaydıramıyorum, kaydırmaya çalıştığımda kutu kayboluyor"). Balonun
       yüksekliği sınırlı ve kendi içinde kayıyor (style.css .bolme-tip).
       Eskiden fare simgeden balona geçerken aradaki boşlukta balon
       kapanıyordu; kapanma kısa bir gecikmeyle yapılıyor, fare balona
       girerse iptal ediliyor. Tekerlek balonun içindeyken yalnızca
       balonu kaydırıyor; balon açıkken sayfa kayarsa (simge yerinden
       oynar) balon simgeye yeniden hizalanıyor. */
    let kapat = null;
    const acikMi = () => tip.style.display === "block";
    const yerlestir = () => {
        const r = kap.getBoundingClientRect();
        tip.style.display = "block";
        const en = Math.min(tip.offsetWidth, window.innerWidth - 16);
        const boy = tip.offsetHeight;
        let sol = Math.min(r.right - en, window.innerWidth - en - 8);
        sol = Math.max(sol, 8);
        const altYer = window.innerHeight - r.bottom - 8;
        let ust = (boy <= altYer || r.top < boy + 8) ? r.bottom + 6 : r.top - boy - 6;
        ust = Math.max(8, Math.min(ust, window.innerHeight - boy - 8));
        tip.style.left = sol + "px";
        tip.style.top = ust + "px";
    };
    const kaydirinca = (e) => {
        if (e.target === tip || tip.contains(e.target)) return;
        if (acikMi()) yerlestir();
    };
    /* BALON SAYFA GÖVDESİNDE AÇILIR (kullanıcı bildirimi: "i kısmına
       bastığımda yazı okunmuyor"). Onaylanmış kart soluk çiziliyor
       (opacity) ve balon kartın içindeyken o saydamlığı alıp arkasındaki
       yazıyla karışıyordu. Açılınca body'ye taşınır, kapanınca geri
       döner. */
    const ac = () => {
        clearTimeout(kapat);
        if (acikMi()) return;          // açıkken yeniden konumlama sıçratmasın
        if (tip.parentNode !== document.body) {
            tip.classList.toggle("genis", kap.classList.contains("bolme-info-genis"));
            document.body.appendChild(tip);
        }
        tip.scrollTop = 0;
        yerlestir();
        window.addEventListener("scroll", kaydirinca, true);
    };
    const gizle = () => {
        clearTimeout(kapat);
        tip.style.display = "";
        if (tip.parentNode !== kap) kap.appendChild(tip);
        window.removeEventListener("scroll", kaydirinca, true);
    };
    /* Balon artık simgenin içinde değil: fare balona geçince kapanmasın,
       balondan çıkınca kapansın; balona tıklamak odağı simgeden almasın. */
    tip.onmouseenter = () => clearTimeout(kapat);
    tip.onmouseleave = () => {
        clearTimeout(kapat);
        if (document.activeElement === kap) return;
        kapat = setTimeout(gizle, 250);
    };
    tip.onmousedown = (e) => { if (e.target !== tip) e.preventDefault(); };
    kap.onmouseenter = ac;
    kap.onfocus = ac;
    kap.onmouseleave = () => {
        clearTimeout(kapat);
        if (document.activeElement === kap) return;   // tıklanarak açıldıysa açık kalır
        kapat = setTimeout(gizle, 250);
    };
    kap.onblur = gizle;
    return kap;
}

/* ---- ÇİP ALANI ----

   Bir ayarın değer tarafı. Açılır liste yerine seçilebilir çip şeridi
   (kullanıcı kararı: "Dropdown kullanımını çok azalt ... mümkün olan
   her şey segmented selection / selectable chip olsun").

   Üç biçim:
     secenekler <= CIP_EN_COK      -> çip şeridi
     secenekler >  CIP_EN_COK      -> açılır liste (OOT / Test dönemi)
     tip yuzde / sayi              -> hazır çipler + "Özel" -> sayı kutusu

   "Özel" çipi SEÇENEĞİ SINIRLAMIYOR, sadece gizliyor: kullanıcı 1-99
   arasında ne isterse yazabiliyor ("zorunlu olmadıkça özgürlüğümü
   kısıtlama"). Hazır çipler yalnızca sık kullanılan değere tek
   dokunuşla gitmek için. */
const CIP_EN_COK = 4;

function bolmeOzelAcikMi(ad, hazirMi) {
    if (BOLME.ozelAcik && BOLME.ozelAcik[ad] !== undefined)
        return !!BOLME.ozelAcik[ad];
    return !hazirMi;   // değer hazır listede yoksa kutu zaten açık gelir
}

function bolmeOzelAyarla(ad, acik) {
    if (!BOLME.ozelAcik) BOLME.ozelAcik = {};
    BOLME.ozelAcik[ad] = !!acik;
}

function bfCipDugmesi(ad, anahtar, etiket, secili, pasif, sec, aciklama, oneri) {
    const b = document.createElement("button");
    b.type = "button";
    /* "oneri": çipte yeşil nokta - önerilen değer bu. Seçenek çiplerinde
       ham anahtardan, yüzde/sayı çiplerinde çağıranın hesabından. */
    const onerilen = (oneri === undefined) ? bfOneriMi(ad, anahtar) : !!oneri;
    b.className = "bolme-cip" + (secili ? " secili" : "") + (onerilen ? " oneri" : "");
    if (onerilen) b.setAttribute("data-oneri", "1");
    b.setAttribute("data-alan", ad);
    b.setAttribute("data-cip", String(anahtar));
    b.setAttribute("aria-pressed", secili ? "true" : "false");
    b.textContent = etiket;
    b.disabled = !!pasif;
    if (aciklama) b.title = tireSade(aciklama);
    if (!b.disabled) b.onclick = (e) => { e.stopPropagation(); sec(); };
    return b;
}

function bfCipKabi(kutu, notMetni) {
    const kap = elYap("div", "bolme-satir-deger");
    kap.appendChild(kutu);
    if (notMetni) kap.appendChild(elYap("div", "bolme-cip-not", notMetni));
    return kap;
}

/* TASLAKTAN KİLİTLENEN ALANLARDA ARKA UCUN "kilitli" BAYRAĞI OKUNMAZ.
   O bayrak SON KAYDEDİLEN hâle göre hesaplanmış aynı kuraldır, yani
   kullanıcı "Rastgele"ye bastığı anda bayat olur: Test Büyüklüğü
   çipleri, sunucuya gidip dönülene kadar tıklanamaz kalıyordu.
   Gerçekten dışarıdan gelen kısıtlar (dönem kolonu yok gibi) bu yoldan
   gelmez; arka uç o durumda seçenek listesini BOŞ gönderir. */
const BF_TASLAK_ALANLARI = ["oot_adet", "test_oran", "val_oran",
                            "kat", "tekrar", "gap", "seedler"];

function bfCipAlani(ad, al, pasif) {
    const k = (al && al[ad]) || {};
    const taslaktan = BF_TASLAK_ALANLARI.indexOf(ad) >= 0;
    const kapali = pasif || bfTaslakPasif(ad)
        || (!taslaktan && !!k.kilitli);
    /* Kilit sebebi YALNIZCA kilitliyken: alan açıldığı hâlde "bu pay
       kullanılmıyor" yazmak ekranda kendini yalanlamak olurdu. */
    const not = kapali ? (k["not"] || "") : "";

    if (ad === "seed") return bfCipSayi(ad, k, kapali, not, []);
    if (ad === "seedler") return bfMetinAlani(ad, k, kapali,
        "Örnek: 42, 7, 2024 — boş bırakılırsa ana seed'den türetilir.");
    if (k.tip === "yuzde") return bfCipYuzde(ad, k, kapali, not);
    if (k.tip === "sayi") return bfCipSayi(ad, k, kapali, not, k.hazir || []);

    const secenekler = bfSecenekler(ad, k.secenekler, []);
    if (!secenekler.length) {
        const kutu = elYap("div", "bolme-cipler");
        kutu.appendChild(elYap("span", "bolme-cip salt", k["not"] || "-"));
        return bfCipKabi(kutu, "");
    }

    const ham = (BF.alan && BF.alan[ad] !== undefined && BF.alan[ad] !== null)
        ? BF.alan[ad] : k.deger;
    const deger = bfKiyasDeger(ad, ham);

    /* TEK SEÇENEK ya da sabit: salt okunur çip. Tıklayınca tek satır
       açılan bir liste "seçim var" izlenimi verip boşuna uğraştırıyordu. */
    if (k.sabit || secenekler.length === 1) {
        const kutu = elYap("div", "bolme-cipler");
        const secili = secenekler.find(o => bfKiyasDeger(ad, o.anahtar) === deger)
            || secenekler[0];
        kutu.appendChild(elYap("span", "bolme-cip secili salt", secili.etiket));
        return bfCipKabi(kutu, not);
    }

    /* UZUN LİSTE -> açılır liste. "Dropdown yalnızca gerçekten seçenek
       sayısı fazla olduğunda": OOT / Test dönemi 11 seçenek. */
    if (secenekler.length > CIP_EN_COK) {
        const kutu = elYap("div", "bolme-cipler bolme-cipler-liste");
        kutu.appendChild(bfSecimKutusu(
            ad, secenekler,
            (ham === null || ham === undefined) ? "" : String(ham),
            kapali, v => bfDegistir(ad, v)));
        return bfCipKabi(kutu, not);
    }

    const kutu = elYap("div", "bolme-cipler");
    secenekler.forEach(o => {
        kutu.appendChild(bfCipDugmesi(
            ad, o.anahtar, o.etiket,
            bfKiyasDeger(ad, o.anahtar) === deger,
            kapali || o.kilitli,
            () => bfDegistir(ad, o.anahtar),
            o.aciklama));
    });
    /* Kurulamayan seçeneğin sebebi SATIRDA TEKRAR YAZILMAZ: üstteki
       kısıt kutusu aynı cümleyi söylüyor, seçenek de üstü çizili ve
       ipucunda sebep var (o.aciklama / title). */
    return bfCipKabi(kutu, not);
}

/* SERBEST METİN (seed listesi). Değer alandan çıkınca taslağa yazılır. */
function bfMetinAlani(ad, k, kapali, ipucu) {
    const kap = elYap("div", "bolme-satir-deger");
    const sat = elYap("div", "bolme-ozel-kutu");
    const i = document.createElement("input");
    i.type = "text";
    i.className = "ft-esik-kutu bf-metin";
    i.setAttribute("data-alan", ad);
    i.setAttribute("data-ft-odak", "bf-" + ad);
    i.value = String((BF.alan && BF.alan[ad]) || k.deger || "");
    i.placeholder = "42, 43, 44";
    i.disabled = kapali;
    if (!kapali) {
        i.onchange = () => bfDegistir(ad, i.value);
        i.onclick = (e) => e.stopPropagation();
    }
    sat.appendChild(i);
    kap.appendChild(sat);
    if (ipucu) kap.appendChild(elYap("div", "bolme-cip-not", ipucu));
    return kap;
}

/* YÜZDE: hazır çipler (%10 %20 %30) + "Özel" -> 1-99 arası serbest kutu.
   Satır karşılığı ("≈ 2.000 satır") ÖN YÜZDE hesaplanıyor ve yazarken
   anında güncelleniyor; eskiden listeyle birlikte yerinde donup
   kalıyordu. */
function bfCipYuzde(ad, k, kapali, not) {
    const enAz = (k.en_az === undefined || k.en_az === null) ? 1 : Number(k.en_az);
    const enCok = (k.en_cok === undefined || k.en_cok === null) ? 99 : Number(k.en_cok);
    const simdi = bfYuzdeDegeri(ad, k);
    const hazir = (k.hazir || []).map(Number);
    const hazirMi = hazir.indexOf(simdi) >= 0;
    const acik = bolmeOzelAcikMi(ad, hazirMi);

    const kutu = elYap("div", "bolme-cipler");
    const oneriYz = bfOneriYuzde(ad);
    hazir.forEach(h => {
        kutu.appendChild(bfCipDugmesi(
            ad, h, "%" + h, !acik && simdi === h, kapali,
            () => { bolmeOzelAyarla(ad, false); bfDegistir(ad, h / 100); },
            null, oneriYz === h));
    });
    kutu.appendChild(bfCipDugmesi(
        ad, "ozel", "Özel", acik, kapali,
        () => { bolmeOzelAyarla(ad, true); bfTazele(); },
        "Kendi oranınızı yazın (%" + enAz + " - %" + enCok + ").",
        oneriYz !== null && hazir.indexOf(oneriYz) < 0));

    const kap = elYap("div", "bolme-satir-deger");
    kap.appendChild(kutu);

    if (acik) {
        const sat = elYap("div", "bolme-ozel-kutu");
        const i = document.createElement("input");
        i.type = "number";
        i.className = "ft-esik-kutu bf-sayi bf-yuzde-kutu";
        i.setAttribute("data-alan", ad);
        i.setAttribute("data-ft-odak", "bf-" + ad);
        i.min = String(enAz); i.max = String(enCok); i.step = "1";
        i.value = String(simdi);
        i.disabled = kapali;
        sat.appendChild(i);
        sat.appendChild(elYap("span", "bf-yuzde-im", "%"));
        const ipucu = elYap("span", "bf-yuzde-satir", "");
        sat.appendChild(ipucu);

        function satirYaz(v) {
            const toplam = Number(k.toplam_satir) || 0;
            if (!toplam || !(v > 0)) { ipucu.textContent = ""; return; }
            ipucu.textContent = "≈ " + ftBinlik(Math.round(toplam * v / 100))
                + " satır";
        }
        satirYaz(simdi);
        if (!kapali) {
            /* "input": satır karşılığı yazarken anında değişsin.
               "change": değer taslağa ancak alandan çıkınca yazılsın,
               yoksa her tuşta gövde yeniden çizilip odak kayıyordu. */
            i.oninput = () => satirYaz(Number(i.value));
            i.onchange = () => {
                let v = Math.round(Number(i.value));
                if (!isFinite(v)) v = enAz;
                v = Math.max(enAz, Math.min(enCok, v));
                i.value = String(v);
                satirYaz(v);
                bfDegistir(ad, v / 100);
            };
            i.onclick = (e) => e.stopPropagation();
        }
        kap.appendChild(sat);
    }
    if (not) kap.appendChild(elYap("div", "bolme-cip-not", not));
    return kap;
}

/* TAM SAYI: hazır çipler + "Özel" -> aralık içinde serbest kutu.
   hazir_etiket varsa çipin yazısı oradan gelir ("0" -> "Yok"). */
function bfCipSayi(ad, k, kapali, not, hazirHam) {
    /* "|| 2" YAZILMIYOR: boşluk alanının en_az değeri 0 ve JS'te 0 yanlış
       sayılıyor - alt sınır sessizce 2'ye çıksa kullanıcı "boşluk yok"
       diyemezdi. */
    const enAz = (k.en_az === undefined || k.en_az === null) ? 0 : Number(k.en_az);
    const enCok = (k.en_cok === undefined || k.en_cok === null)
        ? 9999 : Number(k.en_cok);
    const ham = (BF.alan && BF.alan[ad] !== undefined && BF.alan[ad] !== null)
        ? BF.alan[ad] : k.deger;
    const simdi = bfTam(ham, enAz);
    const hazir = (hazirHam || []).map(Number);
    const etiketler = k.hazir_etiket || {};
    const hazirMi = hazir.indexOf(simdi) >= 0;
    const acik = hazir.length ? bolmeOzelAcikMi(ad, hazirMi) : true;

    const kap = elYap("div", "bolme-satir-deger");
    if (hazir.length) {
        const kutu = elYap("div", "bolme-cipler");
        const oneriDeger = bfOneriDegeri(ad);
        const oneriTam = (oneriDeger === undefined || oneriDeger === null)
            ? null : bfTam(oneriDeger, NaN);
        hazir.forEach(h => {
            kutu.appendChild(bfCipDugmesi(
                ad, h, etiketler[String(h)] || String(h),
                !acik && simdi === h, kapali,
                () => { bolmeOzelAyarla(ad, false); bfDegistir(ad, h); },
                null, oneriTam === h));
        });
        kutu.appendChild(bfCipDugmesi(
            ad, "ozel", "Özel", acik, kapali,
            () => { bolmeOzelAyarla(ad, true); bfTazele(); },
            "Kendi değerinizi yazın (" + enAz + " - " + enCok + ").",
            oneriTam !== null && isFinite(oneriTam) && hazir.indexOf(oneriTam) < 0));
        kap.appendChild(kutu);
    }

    if (acik) {
        const sat = elYap("div", "bolme-ozel-kutu");
        const i = bfSayiKutusu(ad, simdi,
                               { min: String(enAz), max: String(enCok),
                                 step: "1" }, kapali,
                               v => {
            let x = Math.round(Number(v));
            if (!isFinite(x)) x = enAz;
            bfDegistir(ad, Math.max(enAz, Math.min(enCok, x)));
        });
        if (!kapali) i.onclick = (e) => e.stopPropagation();
        sat.appendChild(i);
        kap.appendChild(sat);
    }
    if (not) kap.appendChild(elYap("div", "bolme-cip-not", not));
    return kap;
}

/* ---- ÖNERİ GEREKÇESİ ----
   VARSAYILAN KAPALI ve SOL PANELİN İÇİNDE. Eskiden seçim ekranının
   üstünde duruyordu ve ekranın dörtte birini metin yiyordu; asıl karar
   olan "hangi panel" aşağı kayıyordu. */
function bolmeGerekceCiz(kok, alan) {
    const o = alan.oneri || {};
    const maddeler = o.gerekce || [];
    if (!maddeler.length && !o.ozet) return;

    const kutu = elYap("div", "bolme-acilir bolme-gerekce"
                       + (BOLME.gerekceAcik ? " acik" : ""));
    kutu.setAttribute("data-bolme", "gerekce");
    const bas = document.createElement("button");
    bas.type = "button";
    bas.className = "bolme-acilir-bas";
    bas.setAttribute("aria-expanded", BOLME.gerekceAcik ? "true" : "false");
    bas.appendChild(elYap("span", "bolme-acilir-ok",
                          BOLME.gerekceAcik ? "▾" : "▸"));
    bas.appendChild(elYap("span", "", o.etiket || "Öneri gerekçesi"));
    bas.onclick = (e) => {
        e.stopPropagation();
        BOLME.gerekceAcik = !BOLME.gerekceAcik;
        bolmeGovdeTazele();
    };
    kutu.appendChild(bas);

    if (BOLME.gerekceAcik) {
        const govde = elYap("div", "bolme-acilir-govde");
        if (o.ozet) govde.appendChild(elYap("div", "bolme-gerekce-ozet", o.ozet));
        if (maddeler.length) {
            const ul = elYap("ul", "bolme-gerekce-liste");
            maddeler.forEach(x => ul.appendChild(elYap("li", "", x)));
            govde.appendChild(ul);
        }
        kutu.appendChild(govde);
    }
    kok.appendChild(kutu);
}

/* ---- "Detaylar ve Terimler" ----
   VARSAYILAN KAPALI, her iki panelin altında, SORU-CEVAP biçiminde.
   Satır başına "?" düğmesi KALDIRILDI (kullanıcı kararı: "her satıra ?
   koyunca görüntü yardım dokümanına dönüyor"). İsteyen buradan okur. */
function bolmeSozlukCiz(kok, alan, panelAnahtari) {
    const sz = alan.sozluk || {};
    const sorular = sz.sorular || [];
    if (!sorular.length) return;

    /* Açıklık durumu PANEL BAŞINA tutuluyor: soldaki sözlüğü açmak
       sağdakini de açsaydı iki panelin yüksekliği eşit kalırdı ama
       kullanıcı basmadığı bir yerin açıldığını görürdü. */
    const anahtar = panelAnahtari || "oneri";
    if (!BOLME.sozlukAcik) BOLME.sozlukAcik = {};
    const acik = !!BOLME.sozlukAcik[anahtar];

    const kutu = elYap("div", "bolme-acilir bolme-sozluk" + (acik ? " acik" : ""));
    kutu.setAttribute("data-bolme", "sozluk");
    kutu.setAttribute("data-sozluk-panel", anahtar);
    const bas = document.createElement("button");
    bas.type = "button";
    bas.className = "bolme-acilir-bas";
    bas.setAttribute("aria-expanded", acik ? "true" : "false");
    bas.appendChild(elYap("span", "bolme-acilir-ok", acik ? "▾" : "▸"));
    bas.appendChild(elYap("span", "", sz.etiket || "Detaylar ve Terimler"));
    bas.onclick = (e) => {
        e.stopPropagation();
        BOLME.sozlukAcik[anahtar] = !acik;
        bolmeGovdeTazele();
    };
    kutu.appendChild(bas);

    if (acik) {
        const govde = elYap("div", "bolme-acilir-govde");
        const dl = elYap("div", "bolme-terimler");
        sorular.forEach(s => {
            dl.appendChild(elYap("div", "bolme-terim-ad", s.soru || ""));
            dl.appendChild(elYap("div", "bolme-terim-ack", s.cevap || ""));
        });
        govde.appendChild(dl);
        kutu.appendChild(govde);
    }
    kok.appendChild(kutu);
}

function bolmeGovdeCiz(kok) {
    const alan = BOLME.alan || {};
    const kilitli = BOLME.gonderildi || !!(BOLME.blok && BOLME.blok.kilit);

    /* UYARILAR EN ÜSTTE: yapılan seçimin sonucunu anlatır ("eğitime
       satır kalmaz"), karar verilmeden görülmeli. */
    bfUyariKutusuCiz(kok);
    /* KİLİT BLOĞU da üstte: bölme kilitliyken önce "neden
       değiştiremiyorum" görülmeli. */
    if (BF.veri && BF.veri.kilitli) kok.appendChild(bfKilitCiz());

    bolmeOzetCubukCiz(kok, alan);
    bolmeKisitCiz(kok, alan);
    kok.appendChild(bolmeAyarlariCiz(alan, kilitli));

    /* Alt satır: yalnızca düğmeler. "Öneri gerekçesi" rozetin yanındaki,
       "Detaylar ve Terimler" giriş cümlesinin yanındaki "i"de
       (kullanıcı kararı: ayrı açılır düğme yok). */
    const alt = elYap("div", "bolme-alt");

    if (!BOLME.gonderildi) {
        const dugmeler = elYap("div", "bolme-alt-dugmeler");
        if (bolmeFarkSayisi(alan) > 0 && !kilitli && !bfPasif()) {
            const geri = document.createElement("button");
            geri.type = "button";
            geri.className = "secim-onay bolme-onay ikincil";
            geri.textContent = "Önerilene Dön";
            geri.title = "Bütün ayarları önerilen değerlere döndür";
            geri.onclick = (e) => {
                e.stopPropagation();
                bolmeOnerileneDon(Object.keys(bolmeOneriAyari(alan) || {}));
            };
            dugmeler.appendChild(geri);
        }
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "secim-onay bolme-onay";
        btn.setAttribute("data-bolme-onay", "1");
        btn.textContent = tireSade(alan.buton || "Bu Ayarları Seç");
        btn.disabled = kilitli || BF.kaydediyor || bfPasif();
        if (btn.disabled && bfPasif())
            btn.title = "Bölme kilitli; değiştirmek için önce kilidi açın.";
        btn.onclick = (e) => {
            e.stopPropagation();
            if (typeof BOLME.onayla === "function") BOLME.onayla();
        };
        dugmeler.appendChild(btn);
        alt.appendChild(dugmeler);
    }
    kok.appendChild(alt);

    if (BF.not) {
        const n = elYap("div", "ft-not", BF.not);
        n.setAttribute("data-bf", "not");
        kok.appendChild(n);
    }
    if (BF.hata) {
        const h = elYap("div", "ft-toplu-hata", BF.hata);
        h.setAttribute("role", "alert");
        h.setAttribute("data-bf", "hata");
        kok.appendChild(h);
    }
}


function bolmeGovdeTazele() {
    if (!BOLME.govde || !BOLME.govde.isConnected) return;
    const odak = ftOdakAnahtari();
    /* TASLAĞA DOKUNULMAZ. BF.veri ve BF.alan yalnızca kart kurulurken
       ve kayıt dönüşünde değişir; burada geri sarılsaydı mod değiştirip
       geri dönmek kullanıcının yarım kalan düzenlemesini silerdi. */
    BOLME.govde.innerHTML = "";
    bolmeGovdeCiz(BOLME.govde);
    if (typeof BOLME.sonrasi === "function") BOLME.sonrasi();
    ftOdakGeriVer(odak);
}

function bolmeKartiEkle(alan, blok) {
    const kart = document.createElement("div");
    kart.className = "secim-kart bolme-kart";

    const basSatir = document.createElement("div");
    basSatir.className = "secim-bas";
    const bas = document.createElement("div");
    bas.className = "secim-baslik";
    bas.textContent = kartBasligiGerekli(alan, blok) ? tireSade(alan.baslik) : "";
    basSatir.appendChild(bas);
    const durumEl = document.createElement("span");
    durumEl.className = "secim-durum";
    basSatir.appendChild(durumEl);
    if (kartBasligiGerekli(alan, blok)) kart.appendChild(basSatir);

    if (alan.aciklama) {
        const ack = elYap("div", "secim-aciklama bolme-giris", tireSade(alan.aciklama));
        /* TERİMLER: "Detaylar ve Terimler" açılırı yerine giriş
           cümlesinin yanındaki "i" (soru - cevap listesi). */
        const sorular = (alan.sozluk && alan.sozluk.sorular) || [];
        if (sorular.length) {
            const metin = sorular.map(q => tireSade(q.soru || "") + "\n" + tireSade(q.cevap || "")).join("\n\n");
            const i = bolmeBilgiSimgesi(metin, (alan.sozluk && alan.sozluk.etiket) || "Terimler");
            i.classList.add("bolme-info-genis");
            ack.appendChild(document.createTextNode(" "));
            ack.appendChild(i);
        }
        kart.appendChild(ack);
    }

    const govde = elYap("div", "bolme-govde");
    kart.appendChild(govde);

    /* KART DÜZEYİNDE "DEVAM ET" DÜĞMESİ YOK. Karar hangi panelin
       seçildiği; onu da o panelin kendi "Bu Ayarları Seç" düğmesi
       veriyor. Altta ikinci bir düğme, hangi ayarın uygulandığını
       düğmenin üstünde söylemeyen ikinci bir yol açıyordu. */
    const gecmisten = !!(blok && blok.kilit);

    BOLME.kart = kart;
    BOLME.govde = govde;
    BOLME.alan = alan;
    BOLME.blok = blok || null;
    BOLME.durumEl = durumEl;
    BOLME.onayBtn = null;
    BOLME.gonderildi = false;
    /* AÇILIR ALANLAR VARSAYILAN KAPALI (kullanıcı kararı). */
    BOLME.gerekceAcik = false;
    BOLME.sozlukAcik = {};
    BOLME.ozelAcik = {};

    if (alan.form) {
        BF.veri = alan.form;
        BF.alan = bfAlanlar(alan.form);
        BF.acikEksen = false;
        BF.ozet = null;
        BF.uyarilar = null;
        BF.hata = ""; BF.not = "";
        BF.kaydediyor = false;
        BF.zorlaOnay = false;
        BF.kilitAcik = false;
        BF.seedlerElle = false;
        /* Taslak öneriyle başlar (geçmişten çizilen kilitli kartta
           kayıtlı ayar gösterilir, öneriyle ezilmez). */
        if (!gecmisten) bolmeTaslagiOneriyleDoldur(alan);
    }

    const butonMetni = tireSade(alan.buton || "Bu Ayarları Seç");

    BOLME.sonrasi = null;
    bolmeGovdeCiz(govde);

    function bolmeKartiKilitle() {
        BOLME.gonderildi = true;
        kart.classList.add("kilitli");
        durumEl.textContent = SECIM_HAZIR;
        durumEl.classList.add("hazir", "onayli");
        /* Panel düğmeleri BOLME.gonderildi ile birlikte hiç çizilmiyor
           (bkz. bolmePanelCiz): kilitli kartta basılabilir bir düğme
           bırakmak adımı ikinci kez geçirmenin yolu olurdu. */
        bolmeGovdeTazele();
    }

    if (gecmisten) {
        bolmeKartiKilitle();
    } else {
        function ilerlet() {
            geriAlKilit = () => {
                BOLME.gonderildi = false;
                kart.classList.remove("kilitli");
                durumEl.textContent = "";
                durumEl.classList.remove("hazir", "onayli");
                bolmeGovdeTazele();
            };
            gonder(butonMetni, false);
        }

        /* "Bu Ayarları Seç": TASLAK ÖNCE KAYDEDİLİR, sonra adım
           ilerler. Taslak öneriyle aynıysa öneri arka uçta uygulanır
           ("oneri": true - iki tarafın ayrı öneri hesaplaması olmasın);
           farklıysa taslak gönderilir. */
        BOLME.onayla = () => {
            if (mesgul || BOLME.gonderildi || bfPasif()) return;
            const sonra = () => { bolmeKartiKilitle(); ilerlet(); };
            const fark = bolmeFarkSayisi(BOLME.alan || {});
            BOLME.mod = fark ? "ozel" : "oneri";
            if (fark === 0 && bfDegisti()) { bfKaydet({ oneri: true, mod: "oneri", sonra }); return; }
            if (fark > 0 && bfDegisti()) { bfKaydet({ mod: "ozel", sonra }); return; }
            sonra();
        };
    }

    (adimKabiAl(blok) || sohbetEl).appendChild(kart);
    rozetiBasligaTasi(blok, durumEl);
    sohbetKaydir();
    if (gecmisten) return;
    yeniOdak = govde.querySelector("[data-bolme-onay]");
}


function teyitKartiEkle(alan, blok) {
    const kart = document.createElement("div");
    kart.className = "secim-kart teyit-kart";

    const basSatir = document.createElement("div");
    basSatir.className = "secim-bas";
    const bas = document.createElement("div");
    bas.className = "secim-baslik";
    /* Gruplu blokta adin adi zaten alt baslikta (bkz. secimAlaniEkle). */
    bas.textContent = kartBasligiGerekli(alan, blok) ? tireSade(alan.baslik) : "";
    basSatir.appendChild(bas);

    /* Gonderim sonrasi kartin kilitli oldugunu anlatan tek isaret;
       secim formundaki .secim-durum ile ayni gosterge. */
    const durumEl = document.createElement("span");
    durumEl.className = "secim-durum";
    basSatir.appendChild(durumEl);
    /* Gruplu blokta başlık satırı boş kalır; rozet alt başlığa taşınır. */
    if (kartBasligiGerekli(alan, blok)) kart.appendChild(basSatir);

    if (alan.aciklama)
        kart.appendChild(elYap("div", "secim-aciklama", tireSade(alan.aciklama)));

    /* Ozet TEK SATIR metin (doğrulama kartindaki bloklu ozet degil):
       "1.042 degisken · 2 surec disi · 1.040 tanimli". Gelmezse hic
       cizilmez. */
    if (alan.ozet) {
        const oz = document.createElement("div");
        oz.className = "teyit-ozet";
        oz.textContent = tireSade(alan.ozet);
        kart.appendChild(oz);
    }

    /* ---- DEĞİŞKEN LİSTESİ ----
       Teyit artık SOHBETTE yapılıyor (kullanıcı kararı): eskiden kart
       kullanıcıyı sağ panele gönderiyordu, karar orada veriliyordu.
       Sağ panel yalnızca açıklama gösteriyor; gözden geçirme ve süreç
       dışı işaretleme burada. Açıklama ve işaret DEĞİŞTİĞİ ANDA
       kaydedilir (panelin kullandığı uçların aynısı), düğme yalnızca
       adımı ilerletir. */
    const dg = alan.degiskenler || null;
    /* EXCEL İNDİRME ŞERİDİ - listenin ÜSTÜNDE, Excel simgesiyle.
       KAYDEDİLENE KADAR GİZLİ (kullanıcı kararı): "kaydedildikten sonra
       istenirse excel formatında indirilebilir halde olsun". Kaydedilmemiş
       bir liste, kullanıcının henüz vermediği kararı dosyaya yazmak
       olurdu - o dosya da ekibe gidip "karar buydu" diye okunurdu.
       Uç de aynı kapıyı tutuyor (bkz. backend /degisken_excel). */
    const excelSerit = excelSeridiYap(
        "liste", "Excel İndir",
        "Listeyi kaydettikten sonra indirebilirsiniz.");
    if (dg && (dg.satirlar || []).length) {
        if (dg["not"]) kart.appendChild(elYap("div", "dg-not", tireSade(dg["not"])));
        /* OTOMATİK İŞARETLEME UYARISI: sözlükte açıklaması olmayan
           kolonlar süreç dışı işaretli açılıyor. Sessiz yapılamaz -
           kullanıcı kutuları kendisinin işaretlediğini sanır ya da fark
           etmeden kolon kaybeder. Amber şerit, "bir şey senin adına
           yapıldı, istersen geri al" demenin yeri. */
        if (alan.otomatik_not) {
            kart.appendChild(elYap("div", "dg-otomatik-not",
                                   tireSade(alan.otomatik_not)));
        }

        /* ARAMA · TİP · SIRALAMA TEK SATIRDA. NULL EŞİĞİ, TİP DEĞİŞİKLİĞİ VE
           NULL ORANI KOLONU KALDIRILDI (kullanıcı kararı: "zaten sfa
           adımında göreceğiz"). Burada yalnızca değişken, tip, sözlük
           tanımı ve süreç dışı kararı var. */
        const filtreKap = elYap("div", "dg-filtreler");

        const ara = document.createElement("input");
        ara.type = "search";
        ara.className = "dg-arama";
        ara.placeholder = "Değişken adı veya tanımda ara…";
        ara.setAttribute("aria-label", "Değişken adı veya tanımda ara");
        filtreKap.appendChild(ara);

        /* TİP SÜZGECİ (kullanıcı kararı): "Tip: Tümü" ve listedeki
           tipler. Tek tip varsa kutu görünür ama pasif - gizlemek
           "filtre neden yok?" sorusunu doğururdu. */
        const tipSec = document.createElement("select");
        tipSec.className = "dg-sirala dg-tip-suzgec";
        tipSec.setAttribute("aria-label", "Tipe göre süz");
        const tipListesi = [];
        (dg.satirlar || []).forEach(sat => {
            const t = tireSade(sat.tip || "").trim();
            if (t && tipListesi.indexOf(t) === -1) tipListesi.push(t);
        });
        tipListesi.sort((a, b) => a.localeCompare(b, "tr"));
        [{ deger: "", etiket: "Tip: Tümü" }]
            .concat(tipListesi.map(t => ({ deger: t, etiket: t })))
            .forEach(o => {
                const op = document.createElement("option");
                op.value = o.deger;
                op.textContent = o.etiket;
                tipSec.appendChild(op);
            });
        tipSec.disabled = tipListesi.length <= 1;
        if (tipSec.disabled) tipSec.title = "Listede tek tip var; süzmeye gerek yok.";
        filtreKap.appendChild(tipSec);

        const sirala = document.createElement("select");
        sirala.className = "dg-sirala";
        sirala.setAttribute("aria-label", "Sıralama");
        DG_SIRALAMA.forEach(o => {
            const op = document.createElement("option");
            op.value = o.deger;
            op.textContent = o.etiket;
            sirala.appendChild(op);
        });
        filtreKap.appendChild(sirala);

        kart.appendChild(filtreKap);

        const hataEl = elYap("div", "dg-oneri-hata");
        hataEl.hidden = true;
        kart.appendChild(hataEl);

        /* TOPLU SÜREÇ DIŞI (kullanıcı kararı: null oranına göre süzüp
           tek tek işaretlemek zorunda kalıyordu). Düğmeler FİLTREDE
           GÖRÜNEN satırlara uygulanır; kilitli satırlara dokunmaz. Tek
           istekle gider; sonuçta kutular sunucunun listesine göre kurulur. */
        const ust = elYap("div", "dg-tablo-ust");
        ust.appendChild(dgLejant(DG_LEJANT_TEYIT));
        const toplu = elYap("div", "dg-toplu");
        const topluDisi = elYap("button", "dg-toplu-btn", "");
        const topluIci = elYap("button", "dg-toplu-btn", "");
        topluDisi.type = topluIci.type = "button";
        topluDisi.title = "Filtrede görünen değişkenlerin hepsini süreç dışı bırak";
        topluIci.title = "Filtrede görünen değişkenlerin hepsini sürece geri al";
        toplu.append(topluDisi, topluIci);
        ust.appendChild(toplu);
        kart.appendChild(ust);

        const sar = elYap("div", "dg-tablo-sar");
        const tablo = elYap("table", "dg-tablo");
        const thead = document.createElement("thead");
        const htr = document.createElement("tr");
        ["Değişken", "Tip", "Sözlük Tanımı", "Süreç Dışı"].forEach(h => {
            const th = document.createElement("th");
            th.textContent = h;
            htr.appendChild(th);
        });
        thead.appendChild(htr);
        tablo.appendChild(thead);

        const tbody = document.createElement("tbody");
        const satirlar = [];
        (dg.satirlar || []).forEach(sat => {
            const ad = String(sat.kolon === null || sat.kolon === undefined
                              ? "" : sat.kolon);
            const tr = elYap("tr", "dg-satir");
            tr.dataset.kolon = ad;
            tr.dataset.islem = sat.disi ? "haric" : "ekle";

            const tdK = elYap("td", "dg-kolon", ad);
            tdK.title = ad;
            tr.appendChild(tdK);
            const tipEl = elYap("td", "dg-tip", tireSade(sat.tip));
            tr.appendChild(tipEl);

            const tdA = elYap("td", "dg-aciklama-hucre");
            const giris = document.createElement("input");
            giris.type = "text";
            giris.className = "dg-giris";
            giris.value = tireSade(sat.tanim);
            giris.placeholder = "Tanım yok";
            giris.setAttribute("aria-label", ad + " sözlük tanımı");
            giris.disabled = !dg.duzenlenebilir;
            /* Odak çıkınca kaydedilir; her tuşta istek göndermek 1.042
               satırlık listede sunucuyu boğardı. */
            giris.onchange = () => tanimKaydet(ad, giris, hataEl);
            giris.addEventListener("input", () => satirVurgu());
            tdA.appendChild(giris);
            tr.appendChild(tdA);

            /* Satır rengi (bkz. dgRenk): tanım boşsa sarı, sözlük
               tanımları adımında dil modelinin önerisiyle eklenen ya da
               düzeltilen tanım değiştirilmediyse mavi. */
            function satirVurgu() {
                dgRenk(tr, giris.value, sat.oneri_tanim || "", null);
            }
            satirVurgu();

            const tdI = elYap("td", "dg-ekle-hucre");
            const kutu = document.createElement("input");
            kutu.type = "checkbox";
            kutu.className = "dg-ekle";
            kutu.checked = !!sat.disi;
            kutu.setAttribute("aria-label", ad + " süreç dışı bırakılsın");
            /* HEDEF / KİMLİK / DÖNEM KİLİTLİ: modelleme tanımlarında
               seçildiler; süreç dışı bırakılmaları modeli hedefsiz ya da
               bölmeyi kimliksiz bırakırdı. Kutu gizlenmiyor, KİLİTLİ
               gösteriliyor ve sebebi ipucunda yazıyor - "neden
               işaretleyemiyorum" sorusu ekranda cevaplanmış oluyor. */
            if (sat.disi_kilitli) {
                kutu.disabled = true;
                kutu.title = tireSade(sat.disi_kilit_sebebi || "");
                tdI.title = kutu.title;
                tr.classList.add("dg-rol-kilitli");
            }
            else if (sat.disi_sebebi) {
                /* Otomatik işaretlenmiş (tek değerli): kilitli değil,
                   neden işaretli geldiği ipucunda yazıyor. */
                kutu.title = tireSade(sat.disi_sebebi);
            }
            /* SÜREÇ DIŞI SATIR ÇİZİLİR (kullanıcı kararı): satırın üstü
               çizili, tip ve tanım alanları kilitli - süreç dışı bir
               kolonda yapılacak bir şey yok. Kilitli olmayan satırda kutu
               açık kalır: işaret kaldırılınca satır geri açılır. */
            kutu._disiCiz = () => {
                const disi = kutu.checked;
                tr.classList.toggle("dg-disi", disi);
                const acik = !disi && !!dg.duzenlenebilir
                    && !kart.classList.contains("kilitli");
                giris.disabled = !acik;
            };
            kutu.onchange = () => {
                tr.dataset.islem = kutu.checked ? "haric" : "ekle";
                kutu._disiCiz();
                haricKaydet(ad, kutu, hataEl);
            };
            tdI.appendChild(kutu);
            tr.appendChild(tdI);
            kutu._disiCiz();

            satirlar.push({ tr: tr, ad: ftSade(ad), tanim: ftSade(sat.tanim || ""),
                            tip: ftSade(sat.tip || ""),
                            tipHam: tireSade(sat.tip || "").trim(),
                            giris: giris, kutu: kutu });
            tbody.appendChild(tr);
        });
        tablo.appendChild(tbody);
        sar.appendChild(tablo);
        kart.appendChild(sar);

        /* SÜZ + SIRALA TEK YERDE: üç kontrol de aynı listeyi
           etkiliyor; ayrı ayrı uygulanırsa biri diğerinin sonucunu
           siler (arama yazıp sonra sıralayınca gizli satırlar geri
           gelirdi). */
        function listeyiUygula() {
            const f = ftSade(ara.value || "");
            const t = tipSec.value;
            satirlar.forEach(r => {
                r.tr.hidden = (!!f && r.ad.indexOf(f) === -1
                                   && r.tanim.indexOf(f) === -1)
                              || (!!t && r.tipHam !== t);
            });
            topluSayilari();

            const [alan, yon] = (sirala.value || ":").split(":");
            if (!alan) return;
            const carpan = yon === "z" ? -1 : 1;
            const anahtar = (r) => {
                if (alan === "tip") return r.tip;
                if (alan === "tanim") return r.tanim;
                if (alan === "disi") return r.kutu.checked ? 1 : 0;
                if (alan === "tanimsiz") return (r.giris.value || "").trim() ? 1 : 0;
                return r.ad;
            };
            const sirali = satirlar.slice().sort((x, y) => {
                const a = anahtar(x), b = anahtar(y);
                /* Boş değer HER İKİ YÖNDE DE SONDA. */
                const aBos = a === null || a === undefined || a === "";
                const bBos = b === null || b === undefined || b === "";
                if (aBos !== bBos) return aBos ? 1 : -1;
                if (aBos) return 0;
                if (a === b) return 0;
                return (a < b ? -1 : 1) * carpan;
            });
            sirali.forEach(r => tbody.appendChild(r.tr));
        }
        ara.oninput = listeyiUygula;
        tipSec.onchange = listeyiUygula;
        sirala.onchange = listeyiUygula;

        /* Görünen ve değiştirilebilir (kilitsiz) satırlar. */
        const degisebilir = () => satirlar.filter(
            r => !r.tr.hidden && !r.kutu.disabled);
        function topluSayilari() {
            const g = degisebilir();
            const disiOlmayan = g.filter(r => !r.kutu.checked).length;
            const disiOlan = g.length - disiOlmayan;
            topluDisi.textContent = "Görünenleri Süreç Dışı Bırak (" + disiOlmayan + ")";
            topluIci.textContent = "Görünenleri Sürece Al (" + disiOlan + ")";
            const kilitli = kart.classList.contains("kilitli") || !dg.duzenlenebilir;
            topluDisi.disabled = kilitli || !disiOlmayan;
            topluIci.disabled = kilitli || !disiOlan;
        }
        function topluUygula(deger) {
            if (kart.classList.contains("kilitli") || !dg.duzenlenebilir) return;
            const hedef = degisebilir().filter(r => r.kutu.checked !== deger);
            if (!hedef.length) return;
            const once = satirlar.map(r => r.kutu.checked);
            hedef.forEach(r => {
                r.kutu.checked = deger;
                r.tr.dataset.islem = deger ? "haric" : "ekle";
                if (r.kutu._disiCiz) r.kutu._disiCiz();
            });
            topluDisi.disabled = topluIci.disabled = true;
            const liste = satirlar.filter(r => r.kutu.checked).map(r => r.tr.dataset.kolon);
            const kur = (kume) => satirlar.forEach((r, i) => {
                r.kutu.checked = kume ? kume.has(r.tr.dataset.kolon) : once[i];
                r.tr.dataset.islem = r.kutu.checked ? "haric" : "ekle";
                if (r.kutu._disiCiz) r.kutu._disiCiz();
            });
            fetch(getWebAppBackendUrl("haric_kolonlar"), {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(ftKimlikGovdesi({ kolonlar: liste }))
            })
            .then(r => r.json())
            .then(d => {
                if (!d || d.tamam !== true) {
                    kur(null);
                    teyitHatasi(hataEl, (d && d.hata) || "Süreç dışı listesi yazılamadı.");
                } else {
                    kur(new Set(d.kolonlar || []));
                    const oz = document.querySelector(".teyit-kart .teyit-ozet");
                    if (oz && d.ozet) oz.textContent = tireSade(d.ozet);
                    teyitHatasi(hataEl, (d.reddedilen || []).length ? (d.hata || "") : "");
                }
                topluSayilari();
            })
            .catch(e => {
                kur(null);
                teyitHatasi(hataEl, "Süreç dışı listesi yazılamadı: " + e);
                topluSayilari();
            });
        }
        topluDisi.onclick = () => topluUygula(true);
        topluIci.onclick = () => topluUygula(false);
        /* Tek tek işaretlemede de sayılar güncel kalsın. */
        tbody.addEventListener("change", e => {
            if (e.target && e.target.classList.contains("dg-ekle")) topluSayilari();
        });
        topluSayilari();

        /* Kart kilitlenince liste SALT OKUNUR kalır: karar verildi. */
        teyitListesi = () => satirlar;
    }

    const onayBtn = document.createElement("button");
    onayBtn.type = "button";
    onayBtn.className = "secim-onay teyit-birincil";
    onayBtn.textContent = tireSade(alan.buton || "Devam Et");
    kart.appendChild(onayBtn);

    /* GECMISTEN yeniden cizim: kart kilitli acilir ve CANLI TEYIT
       DURUMUNA HIC DOKUNULMAZ. Eski bir blogun kartı, sağ paneldeki
       teyit düğmesini ve TEYIT.gonder'i üstlenirse canlı adımın kararı
       yanlış karta bağlanır. */
    /* Ad teyitKartiKilitle: modul duzeyindeki teyitKilitle() sag
       paneldeki ikiz dugmeyi kapatiyor, bu kartin kendisini. */
    function teyitKartiKilitle() {
        kart.classList.add("kilitli");
        durumEl.textContent = SECIM_HAZIR;
        durumEl.classList.add("hazir", "onayli");
        onayBtn.disabled = true;
        onayBtn.hidden = true;
        /* Karar verildi: liste SALT OKUNUR. Arama AÇIK KALIYOR:
           kaydedilmiş listede de kolon aranabilmeli, arama bir karar
           değil. */
        kart.querySelectorAll(".dg-giris, .dg-ekle, .dg-tip-sec")
            .forEach(e => { e.disabled = true; });
        /* KAYDEDİLDİ: Excel indirme buradan itibaren açık. */
        excelSerit.ac(true);
    }

    const gecmisten = !!(blok && blok.kilit);
    if (gecmisten) {
        teyitKartiKilitle();
    } else {
        /* Kart ve panel dugmesi AYNI karari paylasiyor: biri basilinca
           ikisi de kilitlenir, ikinci bir istek gitmez. */
        /* Sag paneldeki ikiz dugme kaldirildi; liste yalnizca kartin
           kendi dugmesini tasiyor (bkz. teyitPanelGuncelle). */
        TEYIT.dugmeler = [onayBtn];
        TEYIT.gonderildi = false;

        TEYIT.gonder = () => {
            if (mesgul || TEYIT.gonderildi) return;
            TEYIT.gonderildi = true;
            teyitKilitle(true);          // sag paneldeki ikiz dugme
            teyitKartiKilitle();         // kartin kendisi ve listesi

            /* Hata olursa kart ESKI ACIK haline donsun; kullanici sikismasin */
            geriAlKilit = () => {
                TEYIT.gonderildi = false;
                teyitKilitle(false);
                kart.classList.remove("kilitli");
                durumEl.textContent = "";
                durumEl.classList.remove("hazir", "onayli");
                onayBtn.disabled = false;
                onayBtn.hidden = false;
                /* Liste de geri acilir: karar uygulanmadi. Arama HER
                   ZAMAN acilir; tanim ve tip hucreleri ise yalnizca
                   sozluk duzenlenebilirse - sozlugun calisma kopyasi
                   yoksa bu hucreler en bastan kapaliydi ve burada
                   acilmalari kullaniciya yazabilecegi izlenimi verirdi. */
                excelSerit.ac(false);   // kayit uygulanmadi
                kart.querySelectorAll(".dg-arama")
                    .forEach(e => { e.disabled = false; });
                kart.querySelectorAll(".dg-ekle")
                    .forEach(e => { e.disabled = false; });
                if (dg && dg.duzenlenebilir) {
                    kart.querySelectorAll(".dg-giris, .dg-tip-sec")
                        .forEach(e => { e.disabled = false; });
                }
                /* Rol kilidi geri acilmaz: o kutular hicbir zaman
                   isaretlenemez. */
                kart.querySelectorAll(".dg-rol-kilitli .dg-ekle")
                    .forEach(e => { e.disabled = true; });
                /* Süreç dışı satırların alanları kapalı kalır. */
                kart.querySelectorAll(".dg-ekle")
                    .forEach(e => { if (e._disiCiz) e._disiCiz(); });
            };

            /* GÖNDERİM KAYDI. Sunucu adımı geri çevirirse (ör. AMP_VERISETI
               yazılamadı) aynı adımın kartı uyarıyla YENİDEN gelir.
               Kayıt yokken eski kart kilitli hâliyle ekranda kalıyor,
               yenisi altına ekleniyordu: liste iki kez görünüyordu
               (kullanıcı bildirimi). gonderimSonucu eski kartı, rozetini
               ve başlıktaki Excel düğmesini kaldırır. */
            bekleyenGonderim = { kart: kart, durumEl: durumEl,
                                 adim: (blok && blok.adim) || "",
                                 geriAl: geriAlKilit,
                                 ekler: [excelSerit.el] };

            /* Sessiz gider (ikinci parametre false): kullanici bir cumle
               yazmadi, bir dugmeye basti. */
            gonder(tireSade(alan.buton || "Devam Et"), false);
        };

        onayBtn.onclick = () => {
            if (mesgul || onayBtn.disabled) return;
            TEYIT.gonder();
        };
    }

    (adimKabiAl(blok) || sohbetEl).appendChild(kart);
    rozetiBasligaTasi(blok, durumEl);
    /* Excel düğmesi BLOK BAŞLIK SATIRINDA, "✓ Girdiler Onaylandı" rozetinin
       yanında (kullanıcı kararı). Kart gövdesinde, listenin üstünde
       dururken hem kendi satırını yiyordu hem de kaydettikten sonra
       kullanıcının baktığı yer başlık satırıydı. */
    rozetYuvasinaEkle(blok, excelSerit.el);
    sohbetKaydir();
    if (gecmisten) return;

    yeniOdak = onayBtn;

    /* Kart cizildi: kullanicinin bakacagi yer sag panel. */
    if (alan.hedef) analizSekmeAc(alan.hedef);
}

/* Kartın durum rozetini ("✓ Girdiler Onaylandı") ALT BAŞLIK satırına taşır.
   Gruplu blokta kartın kendi başlık satırı çizilmiyor; rozet orada
   kalsaydı tek başına bir satır kaplar ve alt başlık ile gövde arasında
   büyük bir boşluk bırakırdı. */
/* Blok başlık satırındaki .alt-rozet yuvasına bir öğe ekler (rozeti
   TAŞIMAZ, yanına koyar). Yuva yoksa sessizce vazgeçer - kart sohbet
   dışında da çizilebiliyor. */
function rozetYuvasinaEkle(blok, el) {
    if (!el || !blok) return;
    const kap = adimKabiAl(blok);
    const yuva = kap && kap.querySelector(
        ".alt-bas .alt-rozet, .blok-bas .alt-rozet");
    if (yuva) yuva.appendChild(el);
}

function rozetiBasligaTasi(blok, el) {
    if (!el || !blok) return;
    /* KART KENDI BASLIK SATIRINI ÇİZDİYSE rozet orada kalır: yanında
       başlık var, tek başına bir satır kaplamıyor. Taşıma yalnızca
       başlık satırı çizilmediğinde gerekli - o zaman rozet boş bir
       satırda asılı kalıyor ve alt başlık ile gövde arasında devasa
       bir boşluk açılıyordu (kullanıcı şikayeti).
       el.isConnected: başlık satırı karta eklenmediyse rozet hâlâ
       DOM dışında duruyor demektir. */
    if (el.isConnected) return;
    const kap = adimKabiAl(blok);
    /* Gruplu blokta kap zaten .alt-bolum, içinde tek .alt-bas var;
       tekli blokta kap bloğun kendisi ve yuva .blok-bas içinde. */
    const yuva = kap && kap.querySelector(
        ".alt-bas .alt-rozet, .blok-bas .alt-rozet");
    if (yuva) yuva.appendChild(el);
}

/* Kart aciklamasi KARTIN ICINDE DUZ METIN olarak duruyor. Bir ara
   balona alinmisti; iki sorun cikti (kullanici geri bildirimi):
   ekrandaki her adim bloguna ikinci bir cerceve ekliyordu ve gercek
   UYARILARI (ornegin "PERIOD tek değer taşıyor") sirandan bir
   aciklamadan ayirt edilemez hale getiriyordu. */
function secimAlaniEkle(alan, blok) {
    if (!alan) return;

    /* Girdi dogrulama kendi duzenini kuruyor (ozet + kapsam + karar tablosu) */
    if (alan.tip === "dogrulama") { dogrulamaKartiEkle(alan, blok); return; }
    /* Sozluk teyidi: tek satirlik kart + sag panelde ikiz dugme */
    if (alan.tip === "teyit") { teyitKartiEkle(alan, blok); return; }
    /* Bolme stratejisi: iki modlu kart (Önerilen / Özel Ayarlar) */
    if (alan.tip === "bolme") { bolmeKartiEkle(alan, blok); return; }
    /* Aralık önerileri: satır başına kabul / ret (sözlük tanımları gibi) */
    if (alan.tip === "sfa_karar") { sfaKartiEkle(alan, blok); return; }

    const kart = document.createElement("div");
    kart.className = "secim-kart";

    /* Baslik satiri: baslik solda, durum gostergesi sagda. */
    const basSatir = document.createElement("div");
    basSatir.className = "secim-bas";

    const bas = document.createElement("div");
    bas.className = "secim-baslik";
    /* GRUPLU BLOKTA KART BASLIGI YOK: adımın adı zaten bloğun ALT
       BAŞLIĞINDA yazıyor ("Modelleme Tanımları"). Kart bir de kendi
       başlığını ("Modelleme tanımları") basınca aynı ad iki kez, üstelik
       iki ayrı yazım biçimiyle görünüyordu. Satır DURUYOR: sağındaki
       "✓ Girdiler Onaylandı" göstergesi ona yaslı. */
    bas.textContent = kartBasligiGerekli(alan, blok) ? tireSade(alan.baslik) : "";
    basSatir.appendChild(bas);

    /* Durum gostergesi: <span>, dugme DEGIL. Kart gonderildikten sonra
       "✓ Girdiler Onaylandı" yazip kalir; kartin kilitli oldugunu anlatan
       tek isaret budur. */
    const durumEl = document.createElement("span");
    durumEl.className = "secim-durum";
    basSatir.appendChild(durumEl);

    /* Gruplu blokta başlık satırı BOŞ kalıyor (ad alt başlıkta, gösterge
       de oraya taşınıyor): satırı hiç çizme, yoksa görünmez bir satır
       gövdeyi aşağı itiyor. */
    if (kartBasligiGerekli(alan, blok)) kart.appendChild(basSatir);

    if (alan.aciklama)
        kart.appendChild(elYap("div", "secim-aciklama", tireSade(alan.aciklama)));

    /* SOZLESME7 §3: karttaki ornek satir KALDIRILDI. Arka uc "ipucu"
       alanini artik gondermiyor; gelse de cizilmez. */

    /* Birincil dugme etiketi ARKA UCTAN gelir (akis_faz01._kurulum_formu
       icindeki "buton" alani); burada sabitlenmez. */
    const onayBtn = document.createElement("button");
    onayBtn.className = "secim-onay";
    onayBtn.type = "button";
    onayBtn.textContent = alan.buton || "Devam et";

    /* Kart tipine ozel ek kilit islemi (combo girisleri, liste
       dugmeleri...). Her tip kendi dalinda dolduruyor; tek bir
       kartiKilitle cagrisi hepsini kapatabilsin diye burada duruyor. */
    let kilitEk = null;

    /* Gonderim: dugme gizlenir, durumu gosterge anlatir. */
    /* gonderim=true: kullanıcı ŞİMDİ gönderdi, sonuç henüz belli değil.
       gonderim=false: geçmişten çizim; adım zaten kabul edilmişti. */
    function kartiKilitle(gonderim) {
        kart.classList.add("kilitli");
        if (gonderim) {
            /* Rozet BOŞ (gizli): durumu blok başlığındaki sarı "Kontrol
               Ediliyor" anlatıyor; ikinci bir etiket yan yana binmesin. */
            durumEl.textContent = "";
            durumEl.classList.remove("hazir", "onayli");
        } else {
            durumEl.textContent = SECIM_HAZIR;
            durumEl.classList.add("hazir", "onayli");
        }
        onayBtn.hidden = true;
        onayBtn.disabled = true;
        if (kilitEk) kilitEk();
    }
    function gonderimiKaydet(geriAl) {
        bekleyenGonderim = { kart: kart, durumEl: durumEl,
                             adim: (blok && blok.adim) || "", geriAl: geriAl };
    }
    function kilidiAc() {
        kart.classList.remove("kilitli");
        onayBtn.hidden = false;
        onayBtn.disabled = false;
    }

    /* ---- tip: liste (coklu, + / −) ---- */
    if (alan.tip === "liste") {
        const secilenler = (alan.degerler || []).slice();

        const rozetler = document.createElement("div");
        rozetler.className = "secim-rozetler";

        const satir = document.createElement("div");
        satir.className = "secim-satir";

        const combo = comboYap(alan.etiket || "Tablo ara", () => ekleDurumu(),
                               "", { kaynak: alan.kaynak, haric: () => secilenler });
        satir.appendChild(combo.kok);

        const ekleBtn = document.createElement("button");
        ekleBtn.className = "secim-yuvarlak ekle";
        ekleBtn.type = "button";
        ekleBtn.title = "Listeye ekle";
        ekleBtn.textContent = "+";
        satir.appendChild(ekleBtn);

        /* SECILENLER USTTE, ARAMA ALTTA (kullanici karari: "seçilen
           tabloları yukarı atması gerekmiyor mu"). Liste yukaridan
           asagiya birikir; yeni ekleme listenin sonuna, arama kutusunun
           hemen ustune duser. */
        kart.appendChild(rozetler);
        kart.appendChild(satir);

        function ekleDurumu() {
            if (kart.classList.contains("kilitli")) return;
            ekleBtn.disabled = !combo.gecerli()
                || secilenler.indexOf(combo.deger()) !== -1;
        }

        function durumTazele() {
            if (kart.classList.contains("kilitli")) return;
            const gerekli = alan.min || 1;
            onayBtn.disabled = secilenler.length < gerekli;
            onayBtn.textContent = (alan.buton || "Devam et")
                + (secilenler.length ? "  (" + secilenler.length + ")" : "");
            durumEl.textContent = secimDurumMetni(secilenler.length, gerekli);
            /* Dolu ama GÖNDERİLMEMİŞ kart yeşil olmaz: yeşil "onaylandı" demek. */
            durumEl.classList.remove("hazir", "onayli");
            ekleDurumu();
        }

        function rozetCiz() {
            rozetler.innerHTML = "";
            secilenler.forEach((ad, i) => {
                const r = document.createElement("div");
                r.className = "secim-rozet";

                const t = document.createElement("span");
                t.textContent = ad;
                t.title = ad;          // uzun ad kisaltilir; tamami ipucunda
                r.appendChild(t);

                const sil = document.createElement("button");
                sil.className = "secim-yuvarlak sil";
                sil.type = "button";
                sil.title = "Listeden çıkar";
                sil.textContent = "−";
                sil.onclick = () => {
                    if (kart.classList.contains("kilitli")) return;
                    secilenler.splice(i, 1);
                    rozetCiz();
                    durumTazele();
                };
                r.appendChild(sil);
                rozetler.appendChild(r);
            });
        }

        function ekle() {
            if (!combo.gecerli()) {
                combo.isaretle();
                combo.ciz(combo.giris.value);
                return;
            }
            const ad = combo.deger();
            if (secilenler.indexOf(ad) !== -1) return;
            secilenler.push(ad);
            combo.giris.value = "";
            combo.isaretle();
            combo.giris.focus();
            rozetCiz();
            durumTazele();
        }

        ekleBtn.onclick = ekle;
        combo.giris.addEventListener("keydown", e => {
            if (e.key === "Enter") { e.preventDefault(); ekle(); }
        });

        onayBtn.onclick = () => {
            if (mesgul || secilenler.length < (alan.min || 1)) return;
            const siller = Array.from(rozetler.querySelectorAll(".secim-yuvarlak.sil"));

            kartiKilitle(true);
            ekleBtn.disabled = true;
            combo.giris.disabled = true;
            siller.forEach(b => { b.disabled = true; });

            /* Hata olursa kart ESKI ACIK haline donsun; kullanici sikismasin */
            geriAlKilit = () => {
                kilidiAc();
                combo.giris.disabled = false;
                siller.forEach(b => { b.disabled = false; });
                durumTazele();
            };
            gonderimiKaydet(geriAlKilit);

            gonder((alan.sablon || "{liste}").replace("{liste}", secilenler.join(", ")),
                   false);
        };

        rozetCiz();
        durumTazele();
        kart.appendChild(onayBtn);

    /* ---- tip: form (bir veya iki tekli alan) ---- */
    } else {
        const govde = document.createElement("div");
        govde.className = "secim-govde";
        const combolar = {};
        const zorunluAlan = {};
        const alanlar = alan.alanlar || [];
        /* HEP TEK SATIR (kullanıcı kararı: "aynı satırda olmalı"): sütun
           sayısı alan sayısı kadar, eşit genişlik. */
        govde.style.gridTemplateColumns =
            "repeat(" + Math.max(1, alanlar.length) + ", minmax(0, 1fr))";
        kilitEk = () => {
            Object.keys(combolar).forEach(k => { combolar[k].giris.disabled = true; });
        };

        /* Kolon kaynakli alan varsa (hedef/kimlik/dönem) once kolon listesi
           hazirlanir: backend'in gonderdigi liste ya da /kolonlar ucu. */
        if (alanlar.some(a => (a.kaynak || "dataset") === "kolon"))
            kolonlariHazirla(alan);

        /* Durum gostergesi: kac alan dolu, kac alan bekleniyor.
           SAYIMA YALNIZ ZORUNLU ALANLAR GIRER. Opsiyonel alan (ör. dönem
           kolonu) bosken de "geçerli" sayildigi icin paydaya katilinca
           hicbir sey secilmemisken "1/3 seçildi" yaziyordu — kullanici
           doldurmadigi bir alani doldurmus gorunuyordu. Düğmenin
           etkinligi yine BUTUN alanlarin gecerliligine bakar: opsiyonel
           alana gecersiz bir deger yazilmissa form yine kilitli kalmali. */
        function durumTazele() {
            if (kart.classList.contains("kilitli")) return;
            const anahtarlar = Object.keys(combolar);
            const zorunlular = anahtarlar.filter(k => zorunluAlan[k]);
            const sayilan = zorunlular.length ? zorunlular : anahtarlar;
            const dolu = sayilan.filter(k => combolar[k].dolu()).length;
            onayBtn.disabled = anahtarlar.some(k => !combolar[k].gecerli());
            durumEl.textContent = secimDurumMetni(dolu, sayilan.length);
            /* Dolu ama GÖNDERİLMEMİŞ kart yeşil olmaz: yeşil "onaylandı" demek. */
            durumEl.classList.remove("hazir", "onayli");
        }

        alanlar.forEach(a => {
            /* Her alan kendi kaynagini kullanir: veri seti mi, kolon mu?
               ALAN BAZLI LISTE: a.secenekler geldiyse o alanda YALNIZCA
               o liste gosterilir. Hedef degisken 0/1 kolonlarla, kimlik
               kolonu tekrarsiz kolonlarla sinirli; ikisini de veri
               setinin 1.042 kolonunun tamami arasindan sectirmek,
               hedefle kimligin yer degistirmesine izin veriyordu. */
            const combo = comboYap(a.etiket, durumTazele, a.deger, {
                kaynak: a.kaynak || "dataset",
                zorunlu: a.zorunlu,
                placeholder: a.placeholder,
                liste: Array.isArray(a.secenekler) ? a.secenekler : undefined
            });
            combolar[a.ad] = combo;
            zorunluAlan[a.ad] = (a.zorunlu !== false);
            govde.appendChild(combo.kok);

            /* Alanin altindaki tek satir: listenin neye gore daraltildigi
               (ipucu) ya da daraltilamadiysa NEDENI (not). Kullanici
               listede aradigi kolonu bulamayinca bunu okumali. */
            const altMetin = tireSade(a["not"] || a.ipucu || "");
            if (altMetin) {
                const alt = elYap("div",
                    "alan-not" + (a["not"] ? " alan-not-uyari" : ""), altMetin);
                /* NOT AYRINTISI "i" SİMGESİNDE (kullanıcı kararı: ayrıntı
                   doğrudan görünmesin). Kısa not ("Dönem kolonu
                   bulunamadı.") yerinde kalır; kolon kolon nedenler
                   simgenin üzerine gelince açılır. */
                const maddeler = Array.isArray(a.not_maddeler) ? a.not_maddeler : [];
                if (a["not"] && maddeler.length) {
                    alt.appendChild(document.createTextNode(" "));
                    alt.appendChild(bolmeBilgiSimgesi(
                        maddeler.map(m => "• " + String(m)).join("\n"),
                        "Neden seçilemiyor"));
                }
                /* ALANIN AÇIKLAMASI "i" SİMGESİNDE (01.4'teki gibi). */
                if (a.bilgi) {
                    alt.appendChild(document.createTextNode(" "));
                    alt.appendChild(bolmeBilgiSimgesi(tireSade(a.bilgi),
                        tireSade(a.etiket || "")));
                }
                combo.kok.appendChild(alt);
            }
        });

        kart.appendChild(govde);

        onayBtn.onclick = () => {
            if (mesgul || onayBtn.disabled) return;
            let metin = alan.sablon || "";
            Object.keys(combolar).forEach(k => {
                const v = combolar[k].deger();
                combolar[k].giris.value = v;
                /* Boş opsiyonel alan anahtar kelimesiyle birlikte düşer
                   ("segment {segment}" -> ""): bir sonraki anahtar kelime
                   değer sanılmasın. */
                /* bos_deger: boş alan yerine yazılan değer (kaynak sözlük
                   formu: sıralı listede boş alan "-" ile yer tutar). */
                metin = v ? metin.replace("{" + k + "}", v)
                          : (alan.bos_deger !== undefined
                             ? metin.replace("{" + k + "}", alan.bos_deger)
                             : metin.replace(new RegExp("\\S+\\s*\\{" + k + "\\}"), ""));
            });
            metin = metin.replace(/\s+/g, " ").trim();
            kartiKilitle(true);
            Object.keys(combolar).forEach(k => { combolar[k].giris.disabled = true; });

            /* Hata olursa form ESKI ACIK haline donsun */
            geriAlKilit = () => {
                kilidiAc();
                Object.keys(combolar).forEach(k => { combolar[k].giris.disabled = false; });
                durumTazele();
            };
            gonderimiKaydet(geriAlKilit);

            gonder(metin, false);
        };

        durumTazele();
        kart.appendChild(onayBtn);
    }

    (adimKabiAl(blok) || sohbetEl).appendChild(kart);
    rozetiBasligaTasi(blok, durumEl);
    sohbetKaydir();

    /* GECMISTEN YENIDEN CIZIM: kart kilitli acilir. Adim zaten
       tamamlandi; kullanici degeri degistirecekse Geri Dön'e basar.
       Odak da verilmez, sayfa eski bir bloga atlamamali. */
    if (blok && blok.kilit) { kartiKilitle(false); return; }
    yeniOdak = kart.querySelector(".combo-giris") || kart.querySelector(".secim-onay");
}


/* ==================== Yanıtı ekrana uygula ==================== */
/* /karsilama, /mesaj ve /sifirla ayni govdeyi dondurur. */
function yanitUygula(d, metin) {
    const hataMi = typeof metin === "string" && metin.startsWith("HATA:");
    yeniOdak = null;
    sonYanitMetni = metin;

    /* GERİ DÖNÜŞTE TRANSKRİPTİ GERİ SAR. Yanıt başarılıysa dönülen
       adımın bloğu ve sonrası silinir; hemen altta o adımın taze hâli
       çizilir, yani blok eski yerinde kalır. Hatada dokunulmaz:
       yarım kalmış bir işlem yüzünden geçmiş silinmemeli. */
    if (geriHedefi && !hataMi) transkriptiKirp(geriHedefi);
    geriHedefi = null;
    /* FAZ LİSTESİ BLOKLARDAN ÖNCE. Mod seçilince adım listesi değişiyor;
       eski listeyle çizilen yeni blok numarasız kalıyor ve faz ayracı
       adımı bulamayıp bütün fazları "Tamamlandı" basıyordu (kullanıcı
       bildirimi). */
    if (d.fazlar) fazlariYukle(d.fazlar);
    /* Secili veri setinin adi bu iki govdeden okunuyor; kolon kaynakli
       form cizilmeden ONCE guncellenmeli. */
    if (d.ozet)  SON_OZET  = d.ozet;
    if (d.detay) SON_DETAY = d.detay;
    /* BOS METIN BALON ACMAZ. Bir adim yalnizca form/kart gonderiyorsa
       (metin "") eskiden ici bos bir bot balonu çiziliyordu:
       asistan bir sey söylemiş gibi görünüyor, ama söylediği hiçbir şey
       yok. Kullanıcı o noktada ekranda henüz konuşmamış da olabiliyor
       (kart tıklaması sessiz gidiyor), o yüzden akış kesintisiz devam
       ediyormuş gibi görünmeli.
       Hata metni HER ZAMAN balon açar: hatanın görünmemesi en kötüsü. */
    /* BLOK BILGISI. Onay bekleyen ve kendi formu olmayan metin blogu
       kendi Onayla/Değiştir düğmelerini taşır; her blok da sağ üstünde
       o adıma dönen Geri Dön'ü taşır. Hata balonu blok olmaz: bir adımın
       kararı değil, bir arıza bildirimi. */
    const kartKendiSoruyor = !!(d.secim_alani
        && KENDI_DUGMELI_KARTLAR.indexOf(d.secim_alani.tip) !== -1);
    const blok = hataMi ? null : {
        adim: d.adim_anahtari || "",
        baslik: d.adim_baslik || "",
        /* BLOK GRUBU: ardışık adımlar tek blokta, alt başlıklarla
           (bkz. grupKabiAl). */
        grup: d.grup_anahtari || "",
        grup_baslik: d.grup_baslik || "",
        /* Her blokta Geri Dön, ilk adım dahil: "Çalışma Başlangıcı"na
           dönmek çalışma modunu değiştirmek demek, kapatılmamalı. */
        geri: true,
        onay: d.bekleyen === "onay" && !kartKendiSoruyor
    };

    /* TEK KAP, TEK BAŞLIK. Bir yanıt hem metin hem kart taşıyabiliyor
       (ör. tanımlar uyarıları + sözlük teyidi kartı) ve bir ADIM birden
       fazla yanıt üretebiliyor (seçim formu, sonra doğrulama kartı).
       Hepsi o adımın TEK bloğuna girer; başlık ve Geri Dön blokta bir
       kez durur (bkz. adimKabiAl). */
    const metinBlok = blok;

    /* BLOK, METİN OLMASA DA KURULUR.
       Adım metin döndürmeyebilir (ekranda zaten kendini anlatan bir
       kart ya da seçenek takımı var). O durumda blok hiç kurulmayınca
       seçenekler kök seviyede, BAŞLIKSIZ ve Geri Dön'süz kalıyordu:
       "Çalışma Başlangıcı"na dönünce ekranda sadece üç kart duruyor,
       hangi adımda olunduğu ve oradan nasıl çıkılacağı görünmüyordu.
       Metin yoksa boş gövdeli blok kurulur; seçenekler onun içine
       girer (secenekEkle son .balon-sutun'u arar). */
    /* BİTEN ADIMIN METNİ KENDİ BLOĞUNA. Bir tur ilerlerken dönen metin
       iki parçadır: biten adımın özeti ve yeni adımın giriş metni.
       Eskiden ikisi tek dizeydi ve tamamı YENİ adımın bloğuna
       yazılıyordu: "Dönem kolonunda tek değer var" uyarısı MODELLEME
       TANIMLARI adımının çıktısıyken SÖZLÜK TANIMLARI bloğunun içinde
       görünüyordu. Arka uç ayrımı gövdede gönderiyor (backend: govde
       ["tamamlanan"]); metin burada kendi adımının bloğuna düşüyor. */
    /* Bir turda birden fazla adım bitebilir (bölme → profil → SFA →
       aralık kartı, onaysız zincir): her birinin metni kendi bloğuna. */
    const bitenler = (d.tamamlananlar && d.tamamlananlar.length)
        ? d.tamamlananlar : (d.tamamlanan ? [d.tamamlanan] : []);
    if (!hataMi) bitenler.forEach(t => {
        if (!t || !t.adim || !(t.metin || "").trim()) return;
        const tAdim = DUZ_ADIMLAR[(adimSirasiHaritasi() || {})[t.adim]] || {};
        balonEkle("bot", t.metin, false, {
            adim: t.adim,
            baslik: t.baslik || tAdim.baslik || "",
            grup: tAdim.grup || "", grup_baslik: tAdim.grup_baslik || "",
            onay: false
        });
    });

    const seceneklerVar = !!(d.secenekler && d.secenekler.length);
    const metinVar = hataMi
        || (typeof metin === "string" && metin.trim() !== "");

    if (metinVar) {
        balonEkle("bot", metin, hataMi, metinBlok);
    } else if (metinBlok && (metinBlok.onay || seceneklerVar)) {
        /* Metin yok ama düğme ya da seçenek var: blok yine kurulur,
           yoksa seçenekler başlıksız ve Geri Dön'süz kalır.

           KAP NULL OLABİLİR: gövde `adim_anahtari` taşımıyorsa (eski
           arka uç, hata yolu) adım bloğu kurulamaz. O zaman düğmeler
           sade bir satıra konur. Eskiden burada blokOnayEkle(null)
           çağrılıyor ve TypeError atıyordu; yanitUygula yarıda kalınca
           panel şeridi ve kartlar hiç çizilmiyordu. */
        const kap = adimKabiAl(metinBlok)
            || balonEkle("bot", "", false, null).querySelector(".balon-sutun");
        if (metinBlok.onay && kap) blokOnayEkle(kap);
    }
    secenekEkle(d.secenekler);          // balon varsa ayni kutuya girer
    secimAlaniEkle(d.secim_alani, blok);
    if (typeof d.tur_no === "number") TUR_NO = Math.max(TUR_NO, d.tur_no);

    if (d.mod !== undefined) aktifMod = d.mod;
    if (d.adim_no !== undefined) {
        aktifAdim = d.adim_no;
        blokDurumPlanla();
        aktifFaziAc();
    }
    fazlariCiz();

    /* Sohbet kutusu: kart/form ekrandayken KILITLI. Kullanıcı o anda
       bir cümle yazmıyor, bir form dolduruyor. */
    kutuGuncelle(d.bekleyen);
    /* Panelin altindaki teyit dugmesi: yalniz adim "teyit" ve
       bekleyen "girdi" iken gorunur. */
    teyitPanelGuncelle(d.secim_alani, d.bekleyen);
    analizGuncelle(d.analiz);
    ozetGuncelle(d.ozet);
    rozetGuncelle(hataMi ? "hata" : "hazir");
}


/* ==================== Gönderme ==================== */
function kilitle(durum) {
    mesgul = durum;
    blokDurumPlanla();
    gonderEl.disabled = durum;
    /* Blokların içindeki düğmeler: istek uçuştayken hepsi pasif.
       Tek bir şerit yerine ekranda birden fazla blok olabiliyor. */
    sohbetEl.querySelectorAll(".blok-dugmeler button, .blok-geri")
            .forEach(b => { b.disabled = durum; });
    /* Sol paneldeki adım bağlantıları da istek uçuştayken pasif. */
    fazEl.querySelectorAll(".adim-git").forEach(b => { b.disabled = durum; });
}

/* Gönderilen form kartının sonucu. AYNI ADIM hâlâ girdi bekliyorsa
   sunucu girdiyi REDDETTİ: yeni bir form geliyorsa eski kart (ve
   başlıktaki rozeti) kaldırılır, yenisi uyarıyla birlikte yerine
   çizilir; form gelmiyorsa eski kart yeniden açılır. Aksi halde girdi
   kabul edildi: rozet "✓ Girdiler Onaylandı" olur. */
/* Döndürdüğü işlev yanıt ÇİZİLDİKTEN SONRA çağrılır. Ret uyarısı o
   anda ekrana geliyor; "red-uyari" işareti alır ki girdi sonunda kabul
   edilince onaylanmış bölümde "onaylanmadı" yazısı kalmasın. */
function gonderimSonucu(g, d) {
    const kap = g.kart.parentElement;
    const reddedildi = d && d.bekleyen === "girdi" && d.adim_anahtari === g.adim;
    if (reddedildi) {
        /* ÖNCEKİ RET UYARISI KALKAR. Her yeni denemede aynı uyarı bir kez
           daha ekleniyor, blokta üst üste üç "AMP_VERISETI Flow'da tanımlı
           değil" satırı birikiyordu (kullanıcı bildirimi). Geçerli olan
           yalnızca son denemenin uyarısı. */
        if (kap) kap.querySelectorAll(":scope > .balon.red-uyari").forEach(b => b.remove());
        const onceki = new Set(kap ? kap.querySelectorAll(":scope > .balon") : []);
        if (d.secim_alani) {
            try { g.durumEl.remove(); g.kart.remove(); } catch (e) { /* yok say */ }
            (g.ekler || []).forEach(el => {
                try { el.remove(); } catch (e) { /* yok say */ }
            });
        } else {
            try { g.geriAl(); } catch (e) { /* yok say */ }
        }
        return () => {
            if (!kap) return;
            kap.querySelectorAll(":scope > .balon").forEach(b => {
                if (!onceki.has(b)) b.classList.add("red-uyari");
            });
        };
    }
    g.durumEl.textContent = SECIM_HAZIR;
    g.durumEl.classList.add("hazir", "onayli");
    if (kap) kap.querySelectorAll(":scope > .balon.red-uyari").forEach(b => b.remove());
    blokDurumPlanla();
    return null;
}

/* Hata/iptal yolunda: tiklanan kart grubunu ve secim kartini eski haline dondur */
function kartlariGeriAl() {
    if (!geriAlKilit) return;
    try { geriAlKilit(); } catch (e) { /* kart ekrandan kalkmis olabilir */ }
    geriAlKilit = null;
}

function istegiIptalEt(neden) {
    bekleyenGonderim = null;
    if (!istekKontrol) return;
    istekDurumu = neden || "iptal";
    try { istekKontrol.abort(); } catch (e) { /* yok say */ }
}

/* Timeout/iptal sonrasi sunucudaki gercek durumu okur: tur numarasi
   eslenir, adim sunucuda tamamlandiysa sonucu ekrana yansitir. */
function sunucudanTazele() {
    return fetch(getWebAppBackendUrl("durum")
                 + "?oturum_id=" + encodeURIComponent(OTURUM_ID))
        .then(r => r.json())
        .then(d => {
            if (!d || d.var !== true) return false;
            if (typeof d.tur_no === "number") TUR_NO = Math.max(TUR_NO, d.tur_no);
            const metin = d.metin || d.cevap;
            if (metin && metin !== sonYanitMetni) {
                yanitUygula(d, metin);
                return true;
            }
            return false;
        })
        .catch(() => false);
}

/* ---- İptal / zaman aşımı sonrası GERÇEKTEN bekleme ----
   Eskiden balon "güncel durum kontrol ediliyor" yazıyor ve
   sunucudanTazele() BİR KEZ, hemen çağrılıyordu. Sunucudaki adım 90
   saniye sürüyorsa o tek kontrol hiçbir şey bulmuyor, sonucu da kimse
   bildirmiyordu: cümle bir şey vaat edip yerine getirmiyordu (kullanıcı
   şikayeti: "hiçbir şey kontrol etmiyoruz ki biz").

   Artık gerçekten yoklanıyor: artan aralıklarla, toplam ~50 saniye.
   Yeni bir sonuç gelirse balon KALDIRILIR - yerini gerçek yanıt alır.
   Gelmezse balon ne olduğunu açıkça yazar; "kontrol ediliyor" diye
   asılı kalmaz. */
const YOKLAMA_ARALIKLARI = [1200, 2500, 4000, 7000, 11000, 15000];

/* UZUN İŞLER (kullanıcı bildirimi: 135 milyon satırlık veride iş 5
   dakikayı aşınca ekran vazgeçip başa dönüyordu). Kısa aralıklar bitince
   yoklama DURMAZ: iş bitene kadar 20 saniyede bir, en fazla 3 saat
   (sunucudaki iş süresi sınırıyla aynı: amp_is_sure) sürer. */
const UZUN_YOKLAMA_ARALIGI = 20000;
const UZUN_YOKLAMA_SURESI = 3 * 60 * 60 * 1000;

function durumuYokla(satir, onEk) {
    if (!satir) return;
    let i = 0;
    const baslangic = Date.now();
    /* Hata balonunun metin tasiyicisi .balon.hata (bkz.
       balonIcerikYap); textContent ile yaziliyor. */
    const yaz = (metin) => {
        const govde = satir.querySelector(".balon") || satir;
        govde.textContent = tireSade(metin);
    };
    const tur = () => {
        /* Kullanıcı yeni bir istek başlattıysa yoklama BİTER: sunucunun
           eski durumunu ekrana basmak, yeni isteğin yanıtını ezerdi. */
        if (mesgul) { satir.remove(); return; }
        sunucudanTazele().then(yeni => {
            if (yeni) { satir.remove(); return; }   // gerçek yanıt geldi
            const gecen = Date.now() - baslangic;
            if (i >= YOKLAMA_ARALIKLARI.length) {
                if (gecen > UZUN_YOKLAMA_SURESI) {
                    yaz(onEk + " 3 saat içinde sonuç gelmedi. Sayfayı "
                        + "yenilediğinizde güncel durum yüklenir - adım İKİ KEZ "
                        + "uygulanmaz.");
                    return;
                }
                yaz("İşlem sürüyor · " + sureBicim(Math.round(
                        (gecen + ISTEK_ZAMAN_ASIMI) / 1000))
                    + ". Büyük veride Spark işi dakikalar sürebilir; bittiğinde "
                    + "sonuç kendiliğinden gelecek, bu sayfayı açık tutmanız yeterli.");
                setTimeout(tur, UZUN_YOKLAMA_ARALIGI);
                return;
            }
            setTimeout(tur, YOKLAMA_ARALIKLARI[i++]);
        });
    };
    tur();
}

/* ekGovde: kartin urettigi YAPILANDIRILMIS karar (ornegin girdi
   dogrulama ekraninin "dogrulama" alani). Sablon metniyle tasinamayan
   secimler gövdeye ayri bir alan olarak giriyor; gövde gelmezse backend
   varsayilan isleme donuyor, eski istemciler kirilmiyor. */
function gonder(metinDisaridan, etiket, ekGovde) {
    if (mesgul) return;
    const metin = (metinDisaridan || kutuEl.value).trim();
    if (!metin) return;

    sayfaAc("calisma");
    /* etiket === false: kart tiklamasi. Ekranda kullanici balonu
       BASILMIYOR; backend'e de "sessiz" diye bildiriliyor ki kayitli
       oturum yeniden yuklendiginde gecmiste "A" gibi tek harflik bir
       kullanici balonu belirmesin. Canli oturumda gizlenen sey, gecmis
       cizilirken ortaya cikiyordu. */
    const sessiz = (etiket === false);
    kaydirmaBaslat();
    if (!sessiz) balonEkle("kullanici", etiket || metin);
    kutuEl.value = "";
    kutuEl.style.height = "auto";
    kilitle(true);
    
    /* Tur numarasi yanit gelmeden ARTMAZ: timeout sonrasi ayni tur tekrar
       gonderilirse backend adimi tekrar uygulamaz, kayitli yaniti doner. */
    const tur = TUR_NO + 1;

    const kontrol = new AbortController();
    istekKontrol = kontrol;
    istekDurumu = "";
    const zamanlayici = setTimeout(() => istegiIptalEt("zamanasimi"),
                                   ISTEK_ZAMAN_ASIMI);
    const gosterge = calismaGostergesi(() => istegiIptalEt("iptal"));

    const govde = { oturum_id: OTURUM_ID, mesaj: metin, tur_no: tur,
                    sessiz: sessiz };
    if (ekGovde) Object.assign(govde, ekGovde);
    /* Geri dönüş mü? Yanıt GELİNCE transkript bu adımdan kırpılacak.
       Şimdi kırpılmıyor: istek hata verirse kullanıcının geçmişini
       silmiş oluruz ve geri getirecek bir şey kalmaz. */
    geriHedefi = (ekGovde && ekGovde.adim) || null;

    fetch(getWebAppBackendUrl("mesaj"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(govde),
        signal: kontrol.signal
    })
    .then(r => r.json())
    .then(d => {
        gosterge.kaldir();
        /* Backend yapilandirilmis hata dondurduyse (HTTP 200 + "HATA:")
           ekranda yeni kart gelmez: tiklanan kartlari geri acmak SART. */
        const hataMi = !!d && (d.hata === true
            || (typeof d.cevap === "string" && d.cevap.startsWith("HATA:")));
        const gonderim = bekleyenGonderim;
        bekleyenGonderim = null;
        if (hataMi) kartlariGeriAl();
        else geriAlKilit = null;        // yanit geldi: eski kartlara donulmeyecek
        const sonra = (gonderim && !hataMi) ? gonderimSonucu(gonderim, d) : null;
        yanitUygula(d, d.cevap);
        if (sonra) sonra();
    })
    .catch(e => {
        gosterge.kaldir();
        bekleyenGonderim = null;
        if (istekDurumu === "sifirla") return;   // sifirlama ekrani zaten kuruyor
        kartlariGeriAl();
        rozetGuncelle("hata");

        if (istekDurumu === "zamanasimi") {
            durumuYokla(balonEkle("bot",
                "İşlem sürüyor · " + sureBicim(Math.round(ISTEK_ZAMAN_ASIMI / 1000))
                + ". Sonucu bekliyorum…", false),
                "İşlem " + sureBicim(Math.round(ISTEK_ZAMAN_ASIMI / 1000))
                + " içinde yanıt vermedi.");
        } else if (istekDurumu === "iptal") {
            durumuYokla(balonEkle("bot",
                "İsteği iptal ettiniz. Sunucudaki işlem sürüyor olabilir; "
                + "sonucu bekliyorum…", true),
                "İsteği iptal ettiniz.");
        } else {
            balonEkle("bot",
                "Bağlantı hatası: " + e + "\n\nSayfayı yenilediğinizde çalışma "
                + "kaldığı yerden yüklenir.", true);
        }
    })
    .finally(() => {
        clearTimeout(zamanlayici);
        const sifirlaniyor = (istekDurumu === "sifirla");
        istekDurumu = "";
        if (istekKontrol === kontrol) istekKontrol = null;
        if (sifirlaniyor) return;       // kilidi sifirlama akisi yonetiyor
        kilitle(false);
        /* Yeni bir kart/form geldiyse odak oraya; yoksa yazi kutusuna.
           ISTISNA: kullanici analiz panelinde (feature tablosunun arama
           kutusunda) yaziyorsa odak ALINMAZ - her yanit imleci sohbete
           cekince kolon aramak imkansizdi. */
        const analizdeYaziyor = analizPanel
            && analizPanel.contains(document.activeElement);
        if (yeniOdak && document.contains(yeniOdak)) {
            /* preventScroll: odak almak tarayıcıyı o elemana (çoğu zaman
               kartın en altındaki düğmeye) kaydırıyordu. */
            try { yeniOdak.focus({ preventScroll: true }); }
            catch (err) { kutuEl.focus({ preventScroll: true }); }
        } else if (!analizdeYaziyor) {
            kutuEl.focus({ preventScroll: true });
        }
        yeniOdak = null;
    });
}

/* Aksiyon butonlari kullanici balonu BASMAZ: "Onayla ve Uygula" yazisi
   kullanici yazmis gibi gorunuyordu. Yerine sohbete sessiz bir ayrac
   (aksiyon izi) dusuyor - bu bir balon degil, ince bir ayrac satiri. */
const AKSIYON_IZLERI = {
    onayla:   "✓ Onaylandı",
    degistir: "Değiştir Seçildi",
    geri:     "Geri Dönüldü"
};

function aksiyonIziEkle(metin) {
    const iz = document.createElement("div");
    iz.className = "aksiyon-izi";
    const yazi = document.createElement("span");
    yazi.textContent = tireSade(metin);
    iz.appendChild(yazi);
    sohbetEl.appendChild(iz);
    sohbetKaydir();
    return iz;
}

gonderEl.onclick = () => gonder();

kutuEl.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); gonder(); }
});
kutuEl.addEventListener("input", () => {
    kutuEl.style.height = "auto";
    kutuEl.style.height = Math.min(kutuEl.scrollHeight, 96) + "px";
});


/* ==================== Karşılama ==================== */
/* Backend kayitli oturumu bulursa sohbet gecmisiyle birlikte devam eder;
   F5 saatlerce suren calismayi silmez. */
/* Kart govdesi saklanamamis (boyut siniri) bir adim icin son care. */
const GECILEN_ADIM_NOTU =
    "Bu adım tamamlandı. Kararı değiştirmek için sağ üstteki Geri Dön.";

/* Kullanicinin GECTIGI her adim icin blok kurar ve o adimin EKRANINI
   BIREBIR yeniden cizer: metni, secenek kartlari, formu ve doldurdugu
   degerler. Arka uc her turda cizilen kart govdesini transkripte de
   yaziyor (backend._gecmise_ekle), formun degerleri de adim biterken
   dolu haliyle guncelleniyor (backend._formu_doldur). Burada ayni
   cizim fonksiyonlari KILITLI olarak calistirilir: gorunum canli
   akistakiyle ayni, ama tiklanacak bir sey yok — adim tamamlandi,
   degistirmek icin Geri Dön var. */
function gecilenBloklariCiz(liste) {
    const satirlar = {};             // adim anahtari -> o adima ait kayitlar
    liste.forEach(g => {
        if (g.rol !== "bot" || !g.adim) return;
        (satirlar[g.adim] = satirlar[g.adim] || []).push(g);
    });

    const cizilen = {};
    for (let i = 0; i < aktifAdim; i++) {
        const a = DUZ_ADIMLAR[i];
        if (!a || !a.anahtar) continue;
        const blok = { adim: a.anahtar, baslik: a.baslik || "",
                       grup: a.grup || "", grup_baslik: a.grup_baslik || "",
                       onay: false, kilit: true };
        let birSey = false;
        (satirlar[a.anahtar] || []).forEach(g => {
            if (typeof g.metin === "string" && g.metin.trim()) {
                balonEkle("bot", g.metin, false, blok);
                birSey = true;
            }
            const e = g.ekran;
            if (!e) return;
            const kartlar = e.secenekler || [];
            if (kartlar.length || e.secim_alani) {
                adimKabiAl(blok);           // kap hazir olsun: kartlar oraya
                if (kartlar.length) secenekEkle(kartlar, true, e.secili);
                if (e.secim_alani) secimAlaniEkle(e.secim_alani, blok);
                birSey = true;
            }
        });
        if (!birSey) balonEkle("bot", GECILEN_ADIM_NOTU, false, blok);
        cizilen[a.anahtar] = true;
    }
    return cizilen;
}

/* REDDEDİLMİŞ FORMLAR GEÇMİŞTEN ÇİZİLMEZ. Girdi reddedilince aynı adım
   aynı formu (aynı başlıkla) yeniden gönderiyor; F5 sonrası eski form
   kilitli, yani "✓ Girdiler Onaylandı" rozetiyle çiziliyordu - oysa o
   girdi kontrolden geçmemişti. Aynı adımda aynı başlıklı daha yeni bir
   form varsa eskisinin kartı düşülür; uyarı metni yerinde kalır. */
function reddedilenFormlariAyikla(liste) {
    const baslik = g => (g && g.rol === "bot" && g.adim && g.ekran
                         && g.ekran.secim_alani && g.ekran.secim_alani.tip === "form")
        ? g.adim + "\u0000" + (g.ekran.secim_alani.baslik || "") : null;
    const sonra = new Set();
    for (let i = liste.length - 1; i >= 0; i--) {
        const b = baslik(liste[i]);
        if (!b) continue;
        if (sonra.has(b)) {
            const ekran = Object.assign({}, liste[i].ekran);
            delete ekran.secim_alani;
            liste[i] = Object.assign({}, liste[i], { ekran: ekran });
        } else {
            sonra.add(b);
        }
    }
    return liste;
}

function gecmisiCiz(gecmis, sonMetin) {
    const liste = reddedilenFormlariAyikla((gecmis || []).slice());

    /* AKTIF ADIMIN SON EKRANI canli ciziliyor (yanitUygula); gecmisten
       ikinci kez cizilmemeli. Ondan ONCEKI ekranlari ise gecmisten
       gelmeli: bir adim birden fazla ekran uretebiliyor (once veri
       seti formu, sonra girdi dogrulama karti) ve canli yanit yalnizca
       SONUNCUSUNU tasiyor. Adimin ortasinda F5 atilinca ilk kart
       kayboluyordu. */
    const aktifAnahtar = (DUZ_ADIMLAR[aktifAdim] || {}).anahtar || "";
    let sonAktif = -1;
    for (let i = liste.length - 1; i >= 0; i--) {
        if (liste[i].rol === "bot" && liste[i].adim === aktifAnahtar) {
            sonAktif = i; break;
        }
    }
    if (sonAktif < 0) {
        const s = liste[liste.length - 1];
        if (s && s.rol === "bot" && s.metin === sonMetin)
            sonAktif = liste.length - 1;
    }

    /* Once GECILMIS adimlarin bloklari, adim sirasina gore. Geri kalan
       kayitlar (kullanici satirlari, aktif adimin onceki ekranlari)
       altina eklenir. */
    const cizilen = gecilenBloklariCiz(liste);

    liste.forEach((g, i) => {
        if (i === sonAktif) return;                     // canli cizilecek
        const hataMi = typeof g.metin === "string" && g.metin.startsWith("HATA:");
        if (g.rol === "bot" && g.adim && cizilen[g.adim]) return;   // yukarida
        /* GECMISTEKI BLOK DA GERI DON TASIR. Kullanıcının en çok geri
           dönmek isteyeceği blok, transkriptte yukarıda kalan eski
           blok; backend adım anahtarını bu yüzden geçmişe de yazıyor
           (backend._gecmise_ekle). Onay düğmesi YOK: o karar verilmiş,
           yeniden onaylanacak bir şey kalmadı. Kart KILITLI: bu ekranın
           kararı verilmiş, sonraki ekran onun üzerine geldi. */
        const gAdim = DUZ_ADIMLAR[(adimSirasiHaritasi() || {})[g.adim]] || {};
        const gBlok = (g.rol === "bot" && g.adim)
            ? { adim: g.adim, baslik: g.adim_baslik || gAdim.baslik || "",
                grup: gAdim.grup || "", grup_baslik: gAdim.grup_baslik || "",
                onay: false, kilit: true }
            : null;
        /* Bos metinli kayit balon acmaz (yalniz kart gonderen adimlar);
           F5 sonrasi ekran canli akistan farkli gorunmemeli. */
        if (hataMi || (typeof g.metin === "string" && g.metin.trim())) {
            balonEkle(g.rol === "kullanici" ? "kullanici" : "bot", g.metin,
                      hataMi, gBlok);
        }
        const e = gBlok && g.ekran;
        if (e && ((e.secenekler || []).length || e.secim_alani)) {
            adimKabiAl(gBlok);              // kap hazir olsun: kartlar oraya
            if ((e.secenekler || []).length)
                secenekEkle(e.secenekler, true, e.secili);
            if (e.secim_alani) secimAlaniEkle(e.secim_alani, gBlok);
        }
    });
}

/* Turkce tarih: gg.aa.yyyy ss:dd. Gecersiz/boş tarihte satir atlanir. */
function tarihBicim(iso) {
    if (!iso) return "";
    const t = new Date(iso);
    if (isNaN(t.getTime())) return "";
    const iki = n => (n < 10 ? "0" : "") + n;
    return iki(t.getDate()) + "." + iki(t.getMonth() + 1) + "." + t.getFullYear()
        + " " + iki(t.getHours()) + ":" + iki(t.getMinutes());
}

/* "Kaldigi yerden yuklendi" mesaji: nereden yuklendigi ve nasil
   sifirlanacagi acikca yazilir. devam_bilgi yoksa kisa mesaj kalir. */
function devamMetni(bilgi) {
    const bas = "**" + (bilgi && bilgi.ad ? bilgi.ad : "Önceki çalışmanız")
        + " kaldığı yerden yüklendi.**";
    if (!bilgi) return bas;

    const parcalar = [];
    const zaman = tarihBicim(bilgi.zaman);
    if (zaman) parcalar.push("Son işlem: " + zaman);

    const adimNo = bilgi.adim_no;
    if (bilgi.faz_no && bilgi.adim) {
        /* Faz içi sıra, Arşiv satırıyla aynı biçimde. */
        parcalar.push(bilgi.faz_no + " " + tireSade(bilgi.faz_baslik || "")
                      + " · " + numarali(bilgi.adim_kodu, bilgi.adim));
    } else if (adimNo !== undefined && adimNo !== null && bilgi.toplam) {
        parcalar.push("Adım " + adimNo + "/" + bilgi.toplam
                      + (bilgi.adim ? " - " + tireSade(bilgi.adim) : ""));
    } else if (bilgi.adim) {
        parcalar.push(tireSade(bilgi.adim));
    }
    if (bilgi.veri_seti) parcalar.push("Veri seti: " + tireSade(bilgi.veri_seti));

    const satirlar = [bas];
    if (parcalar.length) satirlar.push(parcalar.join(" · "));
    satirlar.push("Çalışma, Dataiku'daki " + HAFIZA_KLASORU + " klasöründe sizin "
                  + "kullanıcı adınıza kayıtlı. Sıfırdan başlamak için sağ "
                  + "üstteki **" + YENI_CALISMA_ETIKETI + "** düğmesini kullanın; "
                  + "bu çalışma silinmez, **" + CALISMALARIM_ETIKETI
                  + "** listesinden geri açılır.");
    return satirlar.join("\n");
}

/* Çalışmayı açar: ilk yüklemede ve "Arşiv"dan seçimde AYNI yol.
   kimlik verilirse o çalışma, verilmezse kayıtlı/en son çalışma. */
function calismaAc(kimlik) {
    return fetch(getWebAppBackendUrl("karsilama")
      + "?oturum_id=" + encodeURIComponent(kimlik || OTURUM_ID))
    .then(r => r.json())
    .then(d => {
        oturumAyarla(d.calisma_id);
        const metin = d.metin || d.cevap;
        if (d.devam) {
            /* ADIM LISTESI GECMISTEN ONCE YUKLENIR. gecmisiCiz, gecilmis
               adimlarin bloklarini DUZ_ADIMLAR ve aktifAdim uzerinden
               kuruyor; bunlar normalde yanitUygula'da (yani gecmisten
               SONRA) doluyordu ve liste bos oldugu icin tek bir eski
               blok bile cizilemiyordu. */
            if (d.fazlar) fazlariYukle(d.fazlar);
            if (d.adim_no !== undefined) aktifAdim = d.adim_no;
            // Bilgi satiri en ustte; kartlar son yanitin altinda kalsin.
            // BALON DEGIL, sistem seridi: bunu asistan degil uygulama
            // soyluyor (bkz. sistemNotuEkle).
            sistemNotuEkle(devamMetni(d.devam_bilgi));
            gecmisiCiz(d.gecmis, metin);
        }
        yanitUygula(d, metin);
    })
    .catch(e => {
        rozetGuncelle("hata");
        balonEkle("bot", "Bağlantı hatası: " + e, true);
    });
}


/* ==================== Yeni oturum ==================== */
/* Tum calismayi silen bir islem: sohbet icinde onay kartiyla sorulur.
   native confirm() KULLANILMIYOR - Dataiku iframe'inde akisi bloklar. */
/* Ekrandaki çalışmaya ait her şeyi temizler: Yeni Çalışma ve başka bir
   çalışmaya geçiş aynı temizliği yapıyor. Sunucudaki kayda DOKUNMAZ. */
function ekraniTemizle() {
    /* Dağılım sekmesi önceki çalışmanın kolonlarını göstermesin. */
    dagilimSifirla();
    DAGILIM.kolon = "";
    sohbetEl.innerHTML = "";
    KAYDIRMA.ilk = null;
    KAYDIRMA.kullanici = false;
    aktifAdim = 0;
    aktifMod = null;
    TUR_NO = 0;
    sonYanitMetni = null;
    geriAlKilit = null;
    acikFazlar = new Set();

    /* Doküman önceki çalışmaya aitti: ÖZET bir daha açılana kadar
       ekranda kalmasın, açılınca yenisi istenir. */
    dokumanSifirla();
}

function sifirlaUygula() {
    /* Ucusta bir /mesaj varsa once onu iptal et: gec donen yanit
       sifirlanan durumun uzerine yazmasin. */
    if (mesgul) istegiIptalEt("sifirla");
    kilitle(true);
        fetch(getWebAppBackendUrl("sifirla"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ oturum_id: OTURUM_ID })
    })
    .then(r => r.json())
    .then(d => {
        /* Hata yanıtında ekran ve kimlik OLDUĞU GİBİ kalır: yarım bir
           sıfırlama kullanıcıyı boş ekranla bırakmasın. */
        if (d.hata) {
            balonEkle("bot", d.metin || d.cevap || "Yeni çalışma açılamadı.", true);
            return;
        }
        oturumAyarla(d.calisma_id);
        ekraniTemizle();
        yanitUygula(d, d.metin || d.cevap);
        sayfaAc("calisma");
    })
    .catch(e => {
        rozetGuncelle("hata");
        balonEkle("bot", "Oturum sıfırlanamadı: " + e, true);
    })
    .finally(() => { kilitle(false); });
}

/* ==================== Arşiv (kayıtlı çalışmalar) ==================== */
/* Kayıtlı çalışmaların listesi. Liste her açılışta sunucudan istenir:
   başka bir sekmede ilerlemiş bir çalışmanın adımı eski görünmesin.
   Seçilen çalışma calismaAc ile açılır; sunucudaki hiçbir kayıt
   değişmez, yalnızca ekran o çalışmaya geçer. */
const calismalarBtn   = document.getElementById("calismalar-btn");
const calismalarListe = document.getElementById("calismalar-liste");

function calismalarKapat() {
    if (!calismalarListe || calismalarListe.hidden) return;
    calismalarListe.hidden = true;
    calismalarBtn.setAttribute("aria-expanded", "false");
}

function calismaAltSatiri(c) {
    const parca = [];
    const zaman = tarihBicim(c.zaman);
    if (zaman) parca.push(zaman);
    /* ADIM NUMARASI (sol paneldeki gibi): "01 Çalışma Kurulumu · 01.3
       Değişken Kontrolü". Veri seti adı bu satırdan kaldırıldı
       (kullanıcı kararı). */
    if (c.adim && c.faz_no) {
        parca.push(c.faz_no + " " + tireSade(c.faz_baslik || "")
                   + " · " + numarali(c.adim_kodu, c.adim));
    } else if (c.adim) {
        parca.push(tireSade(c.adim));
    }
    return parca.join(" · ");
}

function calismalarCiz(d) {
    calismalarListe.innerHTML = "";
    if (!d || d.hata) {
        calismalarListe.appendChild(elYap("div", "calisma-bos calisma-hata",
            "Liste okunamadı" + (d && d.hata_kodu ? " (" + d.hata_kodu + ")." : ".")));
        return;
    }
    const liste = d.calismalar || [];
    if (!liste.length) {
        calismalarListe.appendChild(elYap("div", "calisma-bos",
            "Kayıtlı çalışma yok."));
        gizliKlasorleriCiz(d.gizli);
        return;
    }
    liste.forEach(c => {
        const aktif = c.calisma_id === OTURUM_ID;
        const oge = document.createElement("button");
        oge.type = "button";
        oge.className = "calisma-oge" + (aktif ? " aktif" : "");
        oge.setAttribute("role", "menuitem");
        const ad = elYap("div", "calisma-ad", c.ad || ("Çalışma " + c.calisma_id));
        if (aktif) ad.appendChild(elYap("span", "calisma-etiket", "AÇIK"));
        oge.appendChild(ad);
        const alt = c.hata ? c.hata
            : (c.baslamis === false ? "Henüz başlanmadı" : calismaAltSatiri(c));
        if (alt) oge.appendChild(elYap("div", "calisma-alt" + (c.hata ? " calisma-hata" : ""), alt));
        oge.disabled = !!c.hata || aktif;
        if (!oge.disabled) {
            oge.title = "Bu çalışmayı kaldığı yerden aç";
            oge.onclick = () => calismayaGec(c.calisma_id);
        }
        /* SAĞDAKİ DÜĞMELER: Aç ve Sil (kullanıcı kararı: "Kopyala" yerine
           "Aç"; listeden silinebilsin). Satırın kendisine tıklamak da açar;
           Aç düğmesi bunu görünür kılıyor. */
        const satir = elYap("div", "calisma-satir");
        satir.appendChild(oge);
        const dugmeler = elYap("div", "calisma-dugmeler");
        const ac = elYap("button", "calisma-dugme", aktif ? "Açık" : "Aç");
        ac.type = "button";
        ac.disabled = oge.disabled;
        ac.title = aktif ? "Şu an bu çalışmadasınız" : "Bu çalışmayı kaldığı yerden aç";
        if (!ac.disabled) ac.onclick = () => calismayaGec(c.calisma_id);
        dugmeler.appendChild(ac);
        /* Hiç başlamamış (boş) açık çalışmada silinecek bir şey yok. */
        if (c.baslamis !== false || c.hata) {
            const sil = elYap("button", "calisma-dugme sil", "Sil");
            sil.type = "button";
            sil.title = "Bu çalışmayı kalıcı olarak sil";
            sil.onclick = () => calismaSilOnayi(dugmeler, c);
            dugmeler.appendChild(sil);
        }
        satir.appendChild(dugmeler);
        calismalarListe.appendChild(satir);
    });
    gizliKlasorleriCiz(d.gizli);
}

/* LİSTEDE GÖRÜNMEYEN KLASÖRLER (kullanıcı bildirimi: "arşiv kısmında
   bütün folderlar gözükmüyor"). PROJE_HAFIZASI'nda olup listede olmayan
   v-klasörleri nedeniyle yazılır: boş klasör, çalışma dosyası silinmiş
   artık dosyalar, başlanmamış çalışma. "Temizle" klasörü kalıcı siler
   (onaylı, Sil ile aynı uç). */
function gizliKlasorleriCiz(gizli) {
    if (!gizli || !gizli.length) return;
    calismalarListe.appendChild(elYap("div", "calisma-gizli-baslik",
        "Listede Görünmeyen Klasörler (" + gizli.length + ")"));
    gizli.forEach(g => {
        const satir = elYap("div", "calisma-satir calisma-gizli");
        const oge = elYap("div", "calisma-oge");
        oge.appendChild(elYap("div", "calisma-ad", g.ad));
        oge.appendChild(elYap("div", "calisma-alt", tireSade(g.neden || "")));
        satir.appendChild(oge);
        const dugmeler = elYap("div", "calisma-dugmeler");
        const sil = elYap("button", "calisma-dugme sil", "Temizle");
        sil.type = "button";
        sil.title = g.ad + " klasörünü kalıcı olarak sil";
        sil.onclick = () => calismaSilOnayi(dugmeler, { calisma_id: g.ad });
        dugmeler.appendChild(sil);
        satir.appendChild(dugmeler);
        calismalarListe.appendChild(satir);
    });
}

/* SİLME ONAYI AYNI YERDE (Yeni Çalışma ile aynı düzen): Aç ve Sil
   gizlenir, yerinde "Silinsin mi?" ile solda Onayla, sağda Reddet
   belirir. Silme geri alınamaz; tek tıkla olmamalı. */
function calismaSilOnayi(dugmeler, c) {
    const satir = dugmeler.closest(".calisma-satir");
    const eski = Array.from(dugmeler.children);
    eski.forEach(d => { d.hidden = true; });
    const soru = elYap("span", "calisma-sil-soru", "Silinsin mi?");
    const onayla = elYap("button", "calisma-dugme onayla", "Onayla");
    const reddet = elYap("button", "calisma-dugme", "Reddet");
    onayla.type = reddet.type = "button";
    onayla.title = c.calisma_id + " kalıcı olarak silinir; geri alınamaz";
    const geriGetir = () => {
        [soru, onayla, reddet].forEach(d => d.remove());
        eski.forEach(d => { d.hidden = false; });
    };
    reddet.onclick = geriGetir;
    onayla.onclick = () => {
        onayla.disabled = reddet.disabled = true;
        soru.textContent = "Siliniyor…";
        /* BEKLETMEZ (kullanıcı kararı): açık olmayan çalışmanın satırı
           hemen kalkar, silme arkada sürer. Başarısız olursa satır hata
           mesajıyla geri gelir. Açık çalışma silinirken ekran ondan
           ayrılacağı için yanıt beklenir. */
        const aktif = c.calisma_id === OTURUM_ID;
        if (satir && !aktif) satir.hidden = true;
        calismaSil(c.calisma_id, () => {
            if (satir) satir.hidden = false;
            geriGetir();
        }, satir);
    };
    dugmeler.append(soru, onayla, reddet);
    onayla.focus();
}

function calismaSil(kimlik, hataysa, satir) {
    fetch(getWebAppBackendUrl("calisma_sil"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ oturum_id: OTURUM_ID, calisma: kimlik })
    })
    .then(r => r.json())
    .then(d => {
        if (d.hata || !d.tamam) {
            hataysa();
            calismalarListe.insertBefore(
                elYap("div", "calisma-bos calisma-hata",
                      "Silinemedi: " + String(d.metin || d.cevap || "bilinmeyen hata")
                          .replace(/^HATA:\s*/, "")),
                calismalarListe.firstChild);
            return;
        }
        /* Açık çalışma silindiyse en son çalışmaya (yoksa yeni boş
           çalışmaya) geçilir. Değilse YALNIZCA O SATIR kaldırılır; liste
           yeniden istenmez (kullanıcı bildirimi: "her sil tuşuna
           bastığımda arşiv ekranı kapanıp tekrar açılıyor"). */
        if (ARSIV_ONBELLEK && ARSIV_ONBELLEK.calismalar)
            ARSIV_ONBELLEK.calismalar = ARSIV_ONBELLEK.calismalar
                .filter(x => x.calisma_id !== kimlik);
        if (ARSIV_ONBELLEK && ARSIV_ONBELLEK.gizli)
            ARSIV_ONBELLEK.gizli = ARSIV_ONBELLEK.gizli.filter(x => x.ad !== kimlik);
        if (d.sonraki) { calismayaGec(d.sonraki, true); return; }
        if (satir) satir.remove();
        if (!calismalarListe.querySelector(".calisma-satir"))
            calismalarListe.appendChild(elYap("div", "calisma-bos", "Kayıtlı çalışma yok."));
    })
    .catch(e => {
        hataysa();
        calismalarListe.insertBefore(
            elYap("div", "calisma-bos calisma-hata", "Silinemedi: " + e),
            calismalarListe.firstChild);
    });
}

/* Son alınan liste: Arşiv açılınca HEMEN bu çizilir, sunucudan gelen
   taze liste arkadan yerine geçer (kullanıcı beklemez). */
let ARSIV_ONBELLEK = null;
let ARSIV_ISTEK = 0;

function calismalarAc() {
    calismalarListe.hidden = false;
    calismalarBtn.setAttribute("aria-expanded", "true");
    if (ARSIV_ONBELLEK) {
        calismalarCiz(ARSIV_ONBELLEK);
    } else {
        calismalarListe.innerHTML = "";
        calismalarListe.appendChild(elYap("div", "calisma-bos", "Yükleniyor…"));
    }
    const istek = ++ARSIV_ISTEK;
    fetch(getWebAppBackendUrl("calismalar")
          + "?oturum_id=" + encodeURIComponent(OTURUM_ID))
        .then(r => r.json())
        .then(d => {
            if (istek !== ARSIV_ISTEK || calismalarListe.hidden) return;
            /* Silme onayı açıkken liste yeniden çizilmez: kullanıcının
               yarım kalan işlemi elinden alınmasın. */
            if (calismalarListe.querySelector(".calisma-sil-soru")) return;
            if (d && !d.hata) ARSIV_ONBELLEK = d;
            calismalarCiz(d);
        })
        .catch(() => { if (istek === ARSIV_ISTEK && !ARSIV_ONBELLEK) calismalarCiz(null); });
}

function calismayaGec(kimlik, zorla) {
    calismalarKapat();
    if (!kimlik || (kimlik === OTURUM_ID && !zorla)) return;
    /* Uçuşta bir /mesaj varsa önce onu iptal et: geç dönen yanıt yeni
       açılan çalışmanın ekranına yazılmasın. "sifirla" durumu bunu
       zaten sağlıyor (bkz. istegiIptalEt). */
    if (mesgul) istegiIptalEt("sifirla");
    kilitle(true);
    ekraniTemizle();
    sayfaAc("calisma");
    calismaAc(kimlik).finally(() => { kilitle(false); });
}

/* Düğmenin adı "Arşiv" (kullanıcı kararı). index.html eski sürümde
   kalsa da doğru ad görünsün diye burada da yazılıyor. */
if (calismalarBtn) {
    const etiket = calismalarBtn.querySelector(".sifirla-etiket");
    if (etiket) etiket.textContent = CALISMALARIM_ETIKETI;
    calismalarBtn.title = "Kayıtlı çalışmalarınız: açın ya da silin";
}

if (calismalarBtn && calismalarListe) {
    calismalarBtn.onclick = (e) => {
        e.stopPropagation();
        if (calismalarListe.hidden) calismalarAc();
        else calismalarKapat();
    };
    calismalarListe.addEventListener("click", e => e.stopPropagation());
    document.addEventListener("click", calismalarKapat);
    document.addEventListener("keydown", e => { if (e.key === "Escape") calismalarKapat(); });
}

const sifirlaBtn = document.getElementById("sifirla-btn");

/* YENİ ÇALIŞMA ONAYSIZ (kullanıcı kararı: onay adımı "iyice saçmalaştı",
   tamamen kaldırıldı). Basınca yeni çalışma hemen açılır; açık çalışma
   SİLİNMEZ, Arşiv'den geri açılır. index.html eski kalsa da eski onay
   kutusu burada sökülür. */
{ const eski = document.getElementById("yeni-onay"); if (eski) eski.remove(); }
sifirlaBtn.onclick = (e) => {
    e.stopPropagation();
    calismalarKapat();
    sayfaAc("calisma");
    sifirlaUygula();
};


/* AÇILIŞ: soru SORULMAZ (kullanıcı kararı). Tarayıcıda kayıtlı çalışma
   ya da kullanıcının en son çalışması doğrudan açılır; başka bir
   çalışmaya "Arşiv" düğmesinden geçilir. Dosyanın SONUNDA
   çağrılıyor: kullandığı Arşiv sabitleri aşağıda tanımlı. */
calismaAc();
