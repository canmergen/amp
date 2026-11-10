/* YÜKLEME HATASI GÖRÜNÜR OLSUN. Bu dosyada bir hata atılırsa geri kalan
   kod çalışmaz ve ekran BOŞ kalır. Hata sohbet alanına yazılır;
   en sık sebebi index.html / style.css / app.js'in farklı sürümlerde
   yapıştırılmış olmasıdır. */
window.addEventListener("error", function (olay) {
    /* Tarayıcının zararsız ResizeObserver uyarısı hata değildir. */
    if (/ResizeObserver loop/i.test((olay && olay.message) || "")) return;
    try {
        const alan = document.getElementById("sohbet");
        if (!alan || document.getElementById("yukleme-hatasi")) return;
        const kutu = document.createElement("div");
        kutu.id = "yukleme-hatasi";
        kutu.setAttribute("role", "alert");
        kutu.style.cssText = "margin:12px;padding:10px 14px;border:1px solid #D51115;"
            + "border-radius:6px;background:#FDF1F1;color:#D51115;font-size:13.5px;line-height:1.5";
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

/* ÇALIŞMA KİMLİĞİNİ SUNUCU VERİR. Kimlik çalışmanın SIRA NUMARASIdır ("03");
   kayıtlı değilse boş gider ve /karsilama kullanıcının en son
   çalışmasını açıp numarasını döndürür (bkz. oturumAyarla).
   Tarayıcıda kayıtlı bir kimlik varsa o çalışma aynen açılır.
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

const YENI_CALISMA_ETIKETI = "⟳ Yeni Çalışma";
const CALISMALARIM_ETIKETI = "Arşiv";

const GORSEL = {
    kurumLogo:  getWebAppBackendUrl("gorsel/kurum_logo"),
    bot:        getWebAppBackendUrl("gorsel/bot"),
    karsilama:  getWebAppBackendUrl("gorsel/karsilama"),
    dusunme:    getWebAppBackendUrl("gorsel/dusunme"),
    user:       getWebAppBackendUrl("gorsel/user"),
};
/* ÖNCEDEN YÜKLE: avatar görselleri açılışta tarayıcı önbelleğine alınır;
   ilk kullanımda sunucudan inmeleri beklenmez. */
const GORSEL_ON = [GORSEL.bot, GORSEL.dusunme, GORSEL.karsilama, GORSEL.user].map(u => {
    const i = new Image();
    i.src = u;
    return i;
});

const sohbetEl    = document.getElementById("sohbet");
const sohbetAlan  = document.getElementById("sohbet-alani");
const kutuEl      = document.getElementById("kutu");
const gonderEl    = document.getElementById("gonder");
const fazEl       = document.getElementById("faz-listesi");
const sozlukCipEl = document.getElementById("sozluk-cip");
/* Sonuç kartları (ÜRETİM · ELEME · MODEL): MODEL GÖSTERGELERİ sekmesinde
   çizilir (bkz. sonucCiz). */
let SONUC_KARTLARI = [];
/* Analiz alanı durumu ve kararı alanda verilen adımlar (bkz. "Sol bar
   sekmeleri ve analiz alanı"). Burada tanımlı: sayfaAc ilk çağrıldığında
   ustSekmeGuncelle bunları okuyor. */
const PANELDE_KARAR = { sfa_karar: "degisken" };
const ANALIZ_DAR = { acik: false, otoAdim: null, kapatilanAdim: null };
/* Sol bardaki kutu -> sayfa (ustSekmeGuncelle, kutu tıklamaları). */
const UST_SAYFA = { anasayfa: "anasayfa", akis: "calisma", dokuman: "ozet", sohbet: "sohbet", dashboard: "dashboard" };
const katipLogoEl = document.getElementById("katip-logo");
/* Giriş bölgesinin kilidi için. */
const girisBolge  = document.getElementById("giris-bolge");
const kabukEl     = document.getElementById("kabuk");

const sayfalar    = { calisma:   document.getElementById("sayfa-calisma"),
                      ozet:      document.getElementById("sayfa-ozet"),
                      anasayfa:  document.getElementById("sayfa-anasayfa"),
                      sohbet:    document.getElementById("sayfa-sohbet"),
                      dashboard: document.getElementById("sayfa-dashboard") };
const sekmeler    = Array.from(document.querySelectorAll(".sekme"));

const analizGovde = document.getElementById("analiz-govde");
const analizSekme = Array.from(document.querySelectorAll(".analiz-sekme"));

let FAZLAR = [];
let DUZ_ADIMLAR = [];          // sira -> {anahtar, no, baslik, aciklama}
let aktifAdim = 0;
let aktifMod = null;           // "A" | "B" | "C"
let acikFazlar = new Set();
let mesgul = false;

/* Hata olursa tiklanan kart grubunu / secim kartini eski haline dondurur */
let geriAlKilit = null;
/* KONTROLDEN GEÇMEDEN ONAY YOK. Form kartı
   gönderilince "Kontrol Ediliyor" der; "✓ Girdiler Onaylandı" ancak
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
/* "ozet" = MODEL GÖSTERGELERİ sekmesi (data-tab degeri bu). Panel govdesi
   "hazirlik" anahtariyla gelir (bkz. akis_panel.hazirlik_paneli). */
/* SEKMELER: "ozet" (MODEL GÖSTERGELERİ) ve "degisken" (DEĞİŞKENLER). Değişkenler
   kendi seçim panelinde üç görünüme ayrılır (DG.alt): "veri" (Veri ve
   Sözlük), "dagilim" (Dağılım ve SFA), "kontrol" (Değişken Kontrolleri).
   "bolme" verisi MODEL GÖSTERGELERİ'nde çizilir. */
const BAGLI_SEKMELER = ["ozet", "degisken", "bolme"];

/* Dataset listesi: "yukleniyor" | "hazir" | "bos" | "hata"
   "bos": liste okundu ama proje icinde dataset yok -> elle yazmaya izin ver */
let DATASETLER = [];
let DATASET_DURUMU = "yukleniyor";
const DATASET_DINLEYICILER = [];   // liste gelince formlar kendini tazeler

/* KATİP LOGOSU: saydam ve beyaz kenarlar kırpılır (yuvayı boşluk
   değil görsel doldursun). Yüklenemezse gizlenir. */
katipLogoEl.onerror = () => { katipLogoEl.style.display = "none"; solBarOlcekle(); };
katipLogoEl.onload = () => solBarOlcekle();
saydamKirp(GORSEL.kurumLogo, src => { katipLogoEl.src = src; },
           () => { katipLogoEl.style.display = "none"; solBarOlcekle(); }, true);
/* SOL BAR İKONLARI: her satırın yerinde klasördeki çizim (PNG) durur.
   HTML'deki çizgi ikon (SVG) yalnız yer tutar ve görünmez (style.css):
   çizim gelene kadar o yer boş kalır, sonra çizim aynı boyda yerine
   geçer; yüklenemezse yer boş kalır. Kenarlardaki saydam ve beyaz
   boşluk kırpılır. Aynı görsel birden çok
   satırda kullanılabilir: Model Sohbeti ile Katip'le Sohbet aynı, Model
   Göstergeleri ile Gösterge Paneli aynı çizimi kullanır. */
const SOL_BAR_IKONLARI = [
    ['#sol-bar .ust-sekme[data-ust="anasayfa"] > svg.ikon', "anasayfa"],
    ["#sol-bar .ust-kume-ad > svg.ikon", "model_platformu"],
    ['#sol-bar .ust-sekme[data-ust="akis"] > svg.ikon', "model_akisi"],
    ['#sol-bar .ust-sekme[data-tab="ozet"] > svg.ikon', "gosterge_paneli"],
    ['#sol-bar .ust-sekme[data-tab="degisken"] > svg.ikon', "degiskenler"],
    ['#sol-bar .ust-sekme[data-ust="dokuman"] > svg.ikon', "ozet"],
    ['#sol-bar .ust-sekme[data-ust="model_sohbet"] > svg.ikon', "model_sohbeti"],
    ['#sol-bar .ust-sekme[data-ust="sohbet"] > svg.ikon', "katiple_sohbet"],
    ['#sol-bar .ust-sekme[data-ust="dashboard"] > svg.ikon', "gosterge_paneli"],
    ["#tema-btn > svg.ikon", "gorunum"],
    ["#calismalar-btn > svg.sifirla-ikon", "arsiv"],
    ["#sifirla-btn > svg.sifirla-ikon", "yeni_calisma"]
];
const SOL_BAR_GORSEL = {};
function solBarGorseli(ad) {
    if (!SOL_BAR_GORSEL[ad]) SOL_BAR_GORSEL[ad] = new Promise((tamam, hata) =>
        saydamKirp(getWebAppBackendUrl("gorsel/" + ad), tamam, hata, true, true));
    return SOL_BAR_GORSEL[ad];
}
(function solBarIkonlari() {
    SOL_BAR_IKONLARI.forEach(([secici, ad]) => {
        const svg = document.querySelector(secici);
        if (!svg) return;
        solBarGorseli(ad).then(src => {
            const img = document.createElement("img");
            img.className = "ikon-gorsel";
            img.alt = "";
            img.onload = () => { if (svg.isConnected) svg.replaceWith(img); };
            img.src = src;
        }, () => { /* görsel yok: çizgi ikon kalır */ });
    });
    /* Görünüm'ün üstündeki robot (robot_alt): kenarları kırpılır;
       yüklenemezse yer kaplamaz. */
    const robot = document.getElementById("robot-alt");
    if (robot) solBarGorseli("robot_alt").then(src => {
        robot.onload = () => solBarOlcekle();
        robot.src = src;
        robot.classList.add("yuklu");
    }, () => { /* görsel yok */ });
})();

/* Görselin kenarlarındaki saydam boşluğu kırpar (logo yuvada küçük
   kalmasın); kırpılamazsa dosya olduğu gibi. cb(src)
   zeminSil: beyaz zeminli çizimin (sol bar ikonları) zemini saydam
   yapılır; Gri modda ikonun altındaki kâğıt rengi plaka görünsün, beyaz
   bir kare kalmasın. Yalnız
   kenardan başlayıp kenara bağlı beyaz alan silinir; çizginin içinde
   kalan beyazlar (sayfa, kupa, göz) olduğu gibi kalır. Zemini zaten
   saydam olan görselde hiçbir şey değişmez. */
function saydamKirp(url, cb, hata, beyazDa, zeminSil) {
    const ham = new Image();
    ham.onload = () => {
        let src = url;
        try {
            const w = ham.naturalWidth, h = ham.naturalHeight;
            const c = document.createElement("canvas");
            c.width = w; c.height = h;
            const g = c.getContext("2d");
            g.drawImage(ham, 0, 0);
            const veri = g.getImageData(0, 0, w, h);
            const a = veri.data;
            if (zeminSil && beyazZeminiSil(a, w, h)) g.putImageData(veri, 0, 0);
            let x0 = w, y0 = h, x1 = -1, y1 = -1;
            for (let y = 0; y < h; y++) {
                for (let x = 0; x < w; x++) {
                    const i = (y * w + x) * 4;
                    /* beyazDa: saydam kenarın yanında beyaz / çok açık
                       kenar da boşluk sayılır (zemini beyaz görseller). */
                    const dolu = a[i + 3] > 20
                        && !(beyazDa && a[i] > 240 && a[i + 1] > 240 && a[i + 2] > 240);
                    if (dolu) {
                        if (x < x0) x0 = x;
                        if (x > x1) x1 = x;
                        if (y < y0) y0 = y;
                        if (y > y1) y1 = y;
                    }
                }
            }
            if (x1 >= x0 && y1 >= y0 && (x1 - x0 + 1 < w || y1 - y0 + 1 < h)) {
                const k = document.createElement("canvas");
                k.width = x1 - x0 + 1; k.height = y1 - y0 + 1;
                k.getContext("2d").drawImage(c, x0, y0, k.width, k.height, 0, 0, k.width, k.height);
                src = k.toDataURL("image/png");
            }
        } catch (e) { /* kirpilamadi: dosya oldugu gibi */ }
        cb(src);
    };
    ham.onerror = () => { if (hata) hata(); };
    ham.src = url;
}

/* Kenardaki beyaz piksellerden başlayıp yalnız beyaz pikseller
   üzerinden yayılarak bağlı beyaz zemini saydam yapar. Bir şey
   silindiyse true. */
function beyazZeminiSil(a, w, h) {
    const beyaz = i => a[i + 3] > 20 && a[i] > 235 && a[i + 1] > 235 && a[i + 2] > 235;
    const gorulen = new Uint8Array(w * h);
    const yigin = [];
    const ekle = (x, y) => {
        const p = y * w + x;
        if (!gorulen[p] && beyaz(p * 4)) { gorulen[p] = 1; yigin.push(p); }
    };
    for (let x = 0; x < w; x++) { ekle(x, 0); ekle(x, h - 1); }
    for (let y = 0; y < h; y++) { ekle(0, y); ekle(w - 1, y); }
    let silinen = 0;
    while (yigin.length) {
        const p = yigin.pop();
        a[p * 4 + 3] = 0;
        silinen++;
        const x = p % w, y = (p - x) / w;
        if (x > 0) ekle(x - 1, y);
        if (x < w - 1) ekle(x + 1, y);
        if (y > 0) ekle(x, y - 1);
        if (y < h - 1) ekle(x, y + 1);
    }
    return silinen > 0;
}

/* ==================== SOL BAR ÖLÇEĞİ ====================
   Sol barın bütün içeriği (logo, sayfa kümeleri, Görünüm, Arşiv,
   Yeni Çalışma) TEK BAKIŞTA görünür; kaydırma yok. İç kap
   (#sol-bar-ic) tasarım eninde (340 px) doğal boyuyla dizilir.
   Sığdırma oranı, sayfa ölçeği SOL_BAR_TABAN (.88) iken barın
   yüksekliğine sığan orandır (0,6 ile 1,2 kat arası); bar ekranda bu
   boyun --sol-olcek (style.css, %80) katında görünür. Sayfanın geri
   kalanı html zoom'u (--olcek) ile ölçeklendiği için iç kabın kendi
   zoom'u ekrandaki boyun html zoom'una oranıdır. Barın eni de aynı
   orana gelir. Doğal boy Model Platformu açıkken ölçülür: küme
   açılınca bar taşmaz.
   İÇERİK BÜYÜTME: barın eni ve boyu yukarıdaki ölçekle kalır; içindeki
   sayfa satırları ve alttaki Görünüm / Arşiv / Yeni Çalışma düğmeleri
   (yazı, çizim, satır boyu birlikte) ayrıca --sol-icerik (style.css)
   katı büyür. Logo ve robot barın enine bağlı, büyümez. Büyümüş içerik
   barın boyuna sığmazsa ya da bir satırın yazısı satıra sığmazsa kat
   sığana kadar düşer (en az 1).
   Ölçek CSS zoom ile verilir, transform ile değil: zoom içeriği yeni
   boyutunda baştan çizer, yazı ve görseller bulanıklaşmaz. */
const SOL_BAR_TASARIM_EN = 340;
const SOL_BAR_SIGDIRMA = { min: 0.6, max: 1.2 };
const SOL_BAR_TABAN = 0.88;
function solBarOrani() {
    return parseFloat(getComputedStyle(document.documentElement)
                      .getPropertyValue("--sol-olcek")) || 0.8;
}
function solBarIcerikKati() {
    return parseFloat(getComputedStyle(document.documentElement)
                      .getPropertyValue("--sol-icerik")) || 1;
}
function solBarOlcekle() {
    const bar = document.getElementById("sol-bar");
    const ic = document.getElementById("sol-bar-ic");
    if (!bar || !ic || !bar.clientHeight) return;
    const icerik = [...ic.querySelectorAll("#ust-sekmeler, .sol-bar-dugmeler")];
    /* Sol bar yazıları ekranda sabit boyda (style.css: calc(14px /
       --sol-ekran)); --sol-ekran satırların ekrandaki toplam ölçeği.
       Doğal boy ölçülürken 1. */
    const kokStil = document.documentElement.style;
    kokStil.setProperty("--sol-ekran", "1");
    ic.style.zoom = "1";
    ic.style.height = "auto";
    icerik.forEach(e => { e.style.zoom = ""; });
    /* Ölçek açık hâle göre: küme açılıp kapanınca bar boyu değişmesin. */
    const kapali = [...ic.querySelectorAll(".ust-kume.acilir:not(.acik)")];
    kapali.forEach(k => k.classList.add("acik"));
    const dogal = ic.offsetHeight;
    if (!dogal) { kapali.forEach(k => k.classList.remove("acik")); return; }
    const kok = ekranOlcegi();
    const sigdirma = Math.max(SOL_BAR_SIGDIRMA.min, Math.min(SOL_BAR_SIGDIRMA.max,
        bar.clientHeight * kok / (SOL_BAR_TABAN * dogal)));
    const olcek = SOL_BAR_TABAN * sigdirma * solBarOrani() / kok;
    ic.style.height = (bar.clientHeight / olcek) + "px";
    ic.style.zoom = String(olcek);
    const satirlar = [...ic.querySelectorAll(
        ".ust-sekme, .ust-kume-ad, #tema-btn, #calismalar-btn, #sifirla-btn")];
    const sigar = () => ic.scrollHeight <= ic.clientHeight + 1
        && satirlar.every(e => e.scrollWidth <= e.clientWidth);
    let kat = Math.max(1, solBarIcerikKati());
    for (;;) {
        icerik.forEach(e => { e.style.zoom = String(kat); });
        kokStil.setProperty("--sol-ekran", String(kok * olcek * kat));
        if (kat <= 1 || sigar()) break;
        kat = Math.max(1, Math.round((kat - 0.02) * 100) / 100);
    }
    kapali.forEach(k => k.classList.remove("acik"));
    document.documentElement.style.setProperty("--sol-bar-en",
        Math.round(SOL_BAR_TASARIM_EN * olcek) + "px");
    konturGuncelle();
}

/* GÖRSEL KONTURU (index.html: SVG filtreleri; style.css: GÖRSEL KONTURU).
   Kontur ekranda her görselde KONTUR_PX kalınlıkta olsun diye her
   filtrenin bulanıklığı görselin durduğu yerin toplam ölçeğine bölünür:
   sayfa (html zoom), sol bar (iç kabın zoom'u da) ve sol bar satırları
   (içerik büyütmesi de). Eşik maskede alfa 0,07'de: düz bir kenarda dış
   hat bulanıklığın 1,476 katı uzağa düşer. */
const KONTUR_PX = 1.2;
const KONTUR_ORAN = 1.476;
function konturGuncelle() {
    const kok = ekranOlcegi();
    const ic = document.getElementById("sol-bar-ic");
    const icZ = parseFloat(ic && ic.style.zoom) || 1;
    const icerik = document.getElementById("ust-sekmeler");
    const icerikZ = parseFloat(icerik && icerik.style.zoom) || 1;
    [["kontur-ana", kok], ["kontur-sol", kok * icZ], ["kontur-sol-ic", kok * icZ * icerikZ]]
        .forEach(([id, olcek]) => {
            const b = document.querySelector("#" + id + " feGaussianBlur");
            if (b) b.setAttribute("stdDeviation", (KONTUR_PX / KONTUR_ORAN / olcek).toFixed(3));
        });
}
window.addEventListener("resize", () => {
    clearTimeout(solBarOlcekle._z);
    solBarOlcekle._z = setTimeout(solBarOlcekle, 60);
});
requestAnimationFrame(solBarOlcekle);
if (document.fonts && document.fonts.ready) document.fonts.ready.then(solBarOlcekle);
/* Dataiku sayfası (iframe) pencere olayı olmadan da boyut değiştirebiliyor:
   sol barın boyu her değiştiğinde yeniden ölçeklenir. */
if (window.ResizeObserver) {
    let sonBoy = 0;
    new ResizeObserver(() => {
        const bar = document.getElementById("sol-bar");
        if (bar && bar.clientHeight !== sonBoy) { sonBoy = bar.clientHeight; solBarOlcekle(); }
    }).observe(document.getElementById("sol-bar"));
}

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
/* YALNIZCA gerçek bağlaçlar; edatlar ("sonra", "göre", "gibi") büyük başlar. */
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


/* ==================== Renk modu (beyaz / sepya / koyu) ==================== */
/* Sol bardaki Görünüm düğmesi. Üç mod: "acik" (Beyaz), "sepya" ve
   "koyu". Sepya ve koyu modda #kabuk.sepya / #kabuk.koyu renk
   değişkenlerini devralır. Anahtardaki bir simgeye basınca o mod
   seçilir; düğmenin başka bir yerine basınca sıradaki moda geçilir.
   Seçim bu tarayıcıda hatırlanır; okunamazsa Beyaz başlar. Eski "gri"
   kaydı Koyu olarak açılır. */
const TEMA_ANAHTAR = "amp_renk_modu";
const TEMA_MODLARI = ["acik", "sepya", "koyu"];
const TEMA_ADI = { acik: "Beyaz", sepya: "Sepya", koyu: "Koyu" };
let temaModu = "acik";
const temaBtn = document.getElementById("tema-btn");

function temaUygula(kaydet) {
    kabukEl.classList.toggle("sepya", temaModu === "sepya");
    kabukEl.classList.toggle("koyu", temaModu === "koyu");
    if (temaBtn) {
        temaBtn.title = "Görünüm: " + TEMA_ADI[temaModu];
        temaBtn.setAttribute("aria-label", "Görünüm: " + TEMA_ADI[temaModu]);
    }
    if (kaydet) {
        try { localStorage.setItem(TEMA_ANAHTAR, temaModu); }
        catch (e) { /* depolama kapalı: yalnız bu oturum */ }
    }
}
if (temaBtn) temaBtn.onclick = e => {
    const simge = e.target.closest && e.target.closest("[data-mod]");
    temaModu = simge ? simge.dataset.mod
        : TEMA_MODLARI[(TEMA_MODLARI.indexOf(temaModu) + 1) % TEMA_MODLARI.length];
    temaUygula(true);
};
try {
    let kayit = localStorage.getItem(TEMA_ANAHTAR);
    if (kayit === "gri") kayit = "koyu";
    temaModu = TEMA_MODLARI.indexOf(kayit) !== -1 ? kayit : "acik";
} catch (e) { temaModu = "acik"; }
temaUygula(false);

/* ==================== Sayfa geçişi ==================== */
function sayfaAc(ad) {
    const onceki = acikSayfa();
    Object.keys(sayfalar).forEach(k => {
        if (sayfalar[k]) sayfalar[k].classList.toggle("gizli", k !== ad);
    });
    sekmeler.forEach(s => s.classList.toggle("aktif", s.dataset.sayfa === ad));
    cekmeceKapat();
    cekmeceButonlari.forEach(b => { b.hidden = (ad !== "calisma"); });
    /* ÖZET her açılışta tazelenir: doküman akışın son durumundan üretiliyor
       ve sekme kapalıyken değişmiş olabilir. */
    if (ad === "ozet") dokumanGetir();
    /* Çalışma sayfası açılışta gizli (Ana Sayfa önde): sohbet gizliyken
       kaydırılamadığı için ilk gösterilişinde kaldığı yere (en alta)
       kaydırılır. */
    if (ad === "calisma" && !sayfaAc.calismaGoruldu) {
        sayfaAc.calismaGoruldu = true;
        requestAnimationFrame(() => {
            sohbetEl.scrollTop = Math.max(sohbetEl.scrollHeight - sohbetEl.clientHeight, 0);
        });
    }
    if (ad !== onceki) kumeleriEsle(ad);
    ustSekmeGuncelle();
}
sekmeler.forEach(s => { s.onclick = () => sayfaAc(s.dataset.sayfa); });


/* ==================== Dar ekran çekmeceleri ==================== */
/* Dar ekranda sol/sag panel gizlenmiyor; sol bardaki dugmeyle acilan
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

/* İŞ AKIŞI BÖLMESİ (Jupyter'deki gezinme bölmesi gibi). Bardaki "İş
   Akışı" düğmesi faz listesini barın altında, solda bölme olarak açar;
   bölme alanın en altına kadar uzanır ve sohbet sağa kayar. Kapatılana
   kadar AÇIK KALIR (dışarıya basmak, adıma gitmek kapatmaz); yine İş
   Akışı düğmesiyle kapanır. Seçim
   bu tarayıcıda hatırlanır; okunamazsa bölme kapalı başlar. */
const AKIS_ACIK_ANAHTAR = "amp_akis_acik";
const akisMenuEl = document.getElementById("akis-menu");
const akisBtn    = document.getElementById("akis-btn");
function akisMenuAc(ac, kaydet) {
    if (!akisBtn || !sohbetAlan) return;
    sohbetAlan.classList.toggle("akis-acik", ac);
    if (akisMenuEl) akisMenuEl.classList.toggle("acik", ac);
    akisBtn.setAttribute("aria-expanded", ac ? "true" : "false");
    akisBtn.title = ac ? "İş akışını kapat" : "İş akışını göster";
    if (kaydet) {
        try { localStorage.setItem(AKIS_ACIK_ANAHTAR, ac ? "1" : "0"); }
        catch (e) { /* depolama kapalı: yalnız bu oturum */ }
    }
    if (ac) {
        /* Açılışta bulunulan adım görünür olsun. */
        const aktif = panelEl && panelEl.querySelector(".faz-adimlar li.aktif");
        if (aktif) aktif.scrollIntoView({ block: "nearest" });
    }
}
if (akisBtn) akisBtn.onclick = () => akisMenuAc(!sohbetAlan.classList.contains("akis-acik"), true);
(function akisBolmeIlk() {
    let ilk = false;
    try { ilk = localStorage.getItem(AKIS_ACIK_ANAHTAR) === "1"; } catch (e) { ilk = false; }
    akisMenuAc(ilk, false);
})();
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

   PANEL TAMAMEN KAPANMIYOR. Üç sınır birden korunuyor:
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

/* index.html eski sürümde kalırsa düğme burada
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
function suankiEn(el) { return Math.round(el.getBoundingClientRect().width / ekranOlcegi()); }

/* Ekran ölçeği (style.css: html { zoom: var(--olcek) }). Fare konumu,
   getBoundingClientRect ve innerWidth / innerHeight EKRAN pikseliyle
   gelir; style.left / top / width ve offsetWidth / offsetHeight TASARIM
   pikseliyle. Ekran pikseli bu orana bölünerek tasarım pikseline,
   tasarım pikseli bu oranla çarpılarak ekran pikseline çevrilir. */
function ekranOlcegi() {
    return parseFloat(getComputedStyle(document.documentElement).zoom) || 1;
}

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
    /* İş akışı yan sütun değil (barın açılır bölmesi): sağ
       panelin karşısında sütun yok. */
    const oteki = taraf === "sol" ? analizPanel : null;
    /* Karşı panelin O ANKİ genişliği sabit kabul ediliyor: tek tutamak
       sürükleniyor, öteki yerinde duruyor. */
    const otekiEn = oteki && getComputedStyle(oteki).position !== "fixed" ? suankiEn(oteki) : 0;
    /* Yer: çalışma sayfasının eni (sol bar hariç). */
    const enCokYer = sayfalar.calisma.clientWidth - otekiEn - SOHBET_TABAN;
    const enCok = Math.min(sinir.enCok, Math.max(sinir.enAz, enCokYer));
    return Math.round(Math.max(sinir.enAz, Math.min(enCok, istenen)));
}

function tutamakKur(tutamak, taraf, el) {
    if (!tutamak || !el) return;
    let surukleniyor = false;
    let basX = 0, basEn = 0;

    /* Tutamak yalnızca ne işe yaradığını söyleyen ipucunu taşır; varsa
       .tutamak-olcu etiketi sökülür. */
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
        /* Fare tutamaktan kaysa bile olaylar buraya gelmeye devam etsin. */
        try { tutamak.setPointerCapture(e.pointerId); } catch (x) { /* yok say */ }
        e.preventDefault();
    });

    tutamak.addEventListener("pointermove", (e) => {
        if (!surukleniyor) return;
        /* Sol panel sağa doğru büyür, sağ panel SOLA doğru. */
        const delta = (taraf === "sol" ? (e.clientX - basX) : (basX - e.clientX)) / ekranOlcegi();
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
/* Kendi onay düğmesi kartın EN ALTINDA olan kartlar: blok ayrıca
   "Onayla ve Uygula / Değiştir" taşımaz (02.1 karar kartı ve eşik formu
   dahil; yoksa genel düğmeler metnin altına, kartın üstüne düşüyordu). */
const KENDI_DUGMELI_KARTLAR = ["dogrulama", "bolme", "profil", "profil_esik"];

/* ---- Sohbet kutusunun kilidi ----
   Ekranda bir kart, form ya da seçenek takımı varken kullanıcı bir
   CÜMLE yazmıyor; bir form dolduruyor.

   SORU SORMA YOLU KAPANMIYOR: akış her an serbest soru kabul ediyor
   (akis_sohbet._soru_mu). Kutu kilitliyken bunu tamamen kapatmak gerçek
   bir yeteneği yok ederdi; kilidin yanındaki "Soru Sor" düğmesi kutuyu
   o tur için açar. */
/* Sohbet kutusu BÖLME STRATEJİSİ adımına kadar KAPALI.

   Neden o adıma kadar kapalı: kurulum, tanımlar, sözlük ve bölme
   adımlarında karar bir cümleyle değil, bloktaki kartla veriliyor.


   Neden DEĞİŞKEN MÜHENDİSLİĞİ'NDE açık: faz 01 ve
   Veri Profili boyunca her karar kartta veriliyor ve kartın soracağı her
   şey kartın içinde yazılı. Değişken üretimi ise kullanıcının yön vermesi
   gereken ilk adım - "şu değişkeni de üret", "bunu neden elediniz"
   soruları tam orada başlıyor.

   SEBEP KUTUNUN İÇİNDE YAZIYOR: boş ve pasif bir kutu "bozuk mu?"
   diye düşündürüyor. Kilit notu hem kapalı olduğunu hem NE ZAMAN
   açılacağını söylüyor. */
const SOHBET_ACILIS_ADIMI = "kural";    // Faz 02 - Değişken Mühendisliği (2.2)
/* Kilit metni PLACEHOLDER DEĞİL, kutunun üstüne binen bir katman.
   Sebep: placeholder düz metindir, içindeki adım adı kalın yazılamaz.
   Katman <strong> taşıyabiliyor. Düz hâli title ve ekran okuyucu için
   duruyor. */
const KUTU_KILIT_ADIM = "02. Değişken Mühendisliği";   // SOHBET_ACILIS_ADIMI'nın fazı
const KUTU_KILIT_ONCE = "Sohbet, ";
const KUTU_KILIT_SONRA =
    " adımında açılır. O ana kadar seçimler kartlar üzerinden yapılır; "
    + "gerekçeli açıklamalar kartların içinde gösterilir.";
const KUTU_KILIT_IPUCU = KUTU_KILIT_ONCE + KUTU_KILIT_ADIM + KUTU_KILIT_SONRA;
const KUTU_ACIK_IPUCU = "Cevabınızı ya da sorunuzu yazın";

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
    altBloklariniGuncelle();
}

/* ATLANAN ALT ADIMIN BLOĞU GİZLİ. «Kontrol Edilmeden Geçilsin»
   seçilince 01.2.4.1 - 01.2.4.4 kapalı kalır; her birinin "atlandı"
   satırı sohbette de görünmez (kontrol bloğu bunu zaten yazıyor).
   Karar değişince (kontrol adımına dönülünce) bloklar zaten
   transkriptten kırpılıyor. */
function altBlokGizle(el) {
    const konum = adimKonumu(el.dataset.adim);
    el.classList.toggle("alt-gizli", satirAtlandi(konum && konum.satir));
}

function altBloklariniGuncelle() {
    if (!sohbetEl) return;
    sohbetEl.querySelectorAll(".alt-bolum[data-adim]").forEach(altBlokGizle);
}

/* GRUPLU ADIMLAR SOL PANELDE TEK SATIR. "Veri Seti ve
   Değişken Sözlüğü", "Kolon Rolleri" ve "Eksik Sözlük Tanımları" sohbette
   zaten TEK blok. Satır grubun adını taşır. Adım listesinin kendisi (FAZLAR)
   DOKUNULMADAN kalır: geri dönüş, transkript kırpma ve blok eşleme hep
   tam listeye bakıyor. */
function fazOgeleri(f) {
    const ogeler = [];
    const yer = {};                     // anahtar -> {satir, oge}
    (f.adimlar || []).forEach(a => {
        const son = ogeler[ogeler.length - 1];
        const alt = { anahtar: a.anahtar, sira: a.sira, bitis: a.sira,
                      baslik: a.baslik, aciklama: a.aciklama,
                      adimlar: [a.anahtar], cocuk: [], ust: null,
                      altDurum: a.alt_durum || "" };
        /* ALT ADIM (bkz. akis_kayit.ALT_ADIMLAR): üst adımın satırının
           altına girer ve 01.2.4.1 gibi alt numara alır. Üst adım ve onu
           taşıyan satır, alt adımların bittiği yere kadar sürer. */
        const ust = a.ust ? yer[a.ust] : null;
        if (ust) {
            alt.ust = ust.satir;
            ust.satir.cocuk.push(alt);
            [ust.satir, ust.oge].forEach(s => {
                s.bitis = a.sira;
                if (s.adimlar.indexOf(a.anahtar) === -1) s.adimlar.push(a.anahtar);
            });
            yer[a.anahtar] = { satir: alt, oge: ust.oge };
            return;
        }
        if (a.grup && son && son.grup === a.grup) {
            son.bitis = a.sira;          // gruba katıl
            son.adimlar.push(a.anahtar);
            son.alt.push(alt);
            yer[a.anahtar] = { satir: alt, oge: son };
            return;
        }
        const oge = {
            anahtar: a.anahtar, sira: a.sira, bitis: a.sira,
            grup: a.grup || "",
            baslik: a.grup ? (a.grup_baslik || a.baslik) : a.baslik,
            aciklama: a.aciklama,
            adimlar: [a.anahtar],
            alt: [alt]
        };
        ogeler.push(oge);
        yer[a.anahtar] = { satir: alt, oge: oge };
    });
    const kodla = (s, kod) => {
        s.kod = kod;
        s.cocuk.forEach((c, k) => kodla(c, kod + "." + (k + 1)));
    };
    ogeler.forEach((o, i) => {
        o.kod = f.no + "." + (i + 1);
        /* Tek adımlı satırın adımı satırın numarasını taşır. */
        if (o.alt.length > 1) o.alt.forEach((x, j) => kodla(x, o.kod + "." + (j + 1)));
        else kodla(o.alt[0], o.kod);
    });
    return ogeler;
}

function adimSatiriBul(satirlar, anahtar) {
    for (let i = 0; i < satirlar.length; i++) {
        if (satirlar[i].anahtar === anahtar) return satirlar[i];
        const ic = adimSatiriBul(satirlar[i].cocuk || [], anahtar);
        if (ic) return ic;
    }
    return null;
}

/* Alt adımın üst adımında «Kontrol Edilmeden Geçilsin» seçildiyse
   adım atlanmıştır: sol panelde tıklanmaz, sohbetteki bloğu gizlenir. */
function satirAtlandi(s) {
    return !!(s && s.ust && s.ust.altDurum === "atlandi");
}

/* ADIM NUMARASI. Numara sol paneldeki SATIR sırasıdır; gruplu
   satırın içindeki adımlar alt numara alır (01.2.1, 01.2.2), alt
   adımlar bir kademe daha (01.2.4.1). İş akışı, sohbet başlıkları,
   Arşiv ve "kaldığı yerden yüklendi" mesajı aynı numarayı kullanır.
   Doner: {fazIdx, faz, kod, altKod, satir} ya da null. */
function adimKonumu(anahtar) {
    if (!anahtar) return null;
    for (let fi = 0; fi < FAZLAR.length; fi++) {
        const ogeler = fazOgeleri(FAZLAR[fi]);
        for (let oi = 0; oi < ogeler.length; oi++) {
            if (ogeler[oi].adimlar.indexOf(anahtar) === -1) continue;
            const kod = ogeler[oi].kod;
            const satir = adimSatiriBul(ogeler[oi].alt, anahtar);
            return { fazIdx: fi, faz: FAZLAR[fi], kod: kod,
                     altKod: satir ? satir.kod : kod, satir: satir };
        }
    }
    return null;
}

/* Ön yüzde yazılan adım atfı, arka ucun akis_atif.adim'i ile aynı
   biçim: **02.1 Veri Profili ve Kalite** (metinYaz kalın yazar). */
function adimAtfi(anahtar, yedekAd) {
    const k = adimKonumu(anahtar);
    const a = DUZ_ADIMLAR.find(x => x && x.anahtar === anahtar);
    return "**" + numarali(k && k.altKod, a ? a.baslik : yedekAd) + "**";
}

function numarali(kod, baslik) {
    const b = tireSade(baslik || "");
    return kod ? kod + " " + b : b;
}

function fazlariCiz() {
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
        /* GRUP SATIRININ ALT ADIMLARI. Grup satırı (01.2 Veri Seti, Sözlük ve Kolon
           Rolleri) kalır; altında her adım kendi numarasıyla (01.2.1,
           01.2.2 ...) aynı kurallarla — tamamlandı / aktif / tıklanabilir
           — listelenir. */
        const satirKur = (a) => {
            const li = document.createElement("li");
            /* ATLANAN ALT ADIM: «Kontrol Edilmeden Geçilsin» seçildi.
               Tamamlandı sayılmaz ve tıklanmaz (sohbetteki bloğu gizli). */
            if (satirAtlandi(a)) {
                li.className = "atlandi";
                li.title = duzMetin(a.baslik) + ": atlandı (Sözlük ve Kolon Adı "
                    + "Kontrolü'nde «Kontrol Edilmeden Geçilsin» seçildi)";
                li.appendChild(elYap("span", "adim-isaret"));
                li.appendChild(elYap("span", "", numarali(a.kod, a.baslik)));
                return li;
            }
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
                dug.title = "\"" + tireSade(a.baslik) + "\" bloğuna git"
                    + (a.aciklama ? ": " + tireSade(a.aciklama) : "");
                /* YALNIZ GEZİNME: tıklama adıma GERİ DÖNMEZ, sohbet o
                   adımın bloğuna kayar ve blok kısa süre vurgulanır. Adıma
                   geri dönmek bloğun kendi "Geri Dön" düğmesiyle yapılır;
                   listeye basmak kararları sıfırlamaz. */
                dug.onclick = () => adimBloguneGit(a.anahtar, a.adimlar);
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
        /* ALT ADIMLI SATIR (01.2.4 ve altında 01.2.4.1 ...). Aç/kapa oku
           YOK: alt adımlar yalnız «Sözlük ve Kolon Adları Kontrol
           Edilsin» seçildiğinde (altDurum "acik") kendiliğinden listelenir;
           seçilmediyse ya da «Kontrol Edilmeden Geçilsin» dendiyse hiç
           görünmez. */
        const altlariEkle = (li, x) => {
            if (!x.cocuk || !x.cocuk.length || x.altDurum !== "acik") return;
            li.classList.add("grup-satir", "ust-satir");
            const ic = elYap("ol", "faz-alt-adimlar");
            x.cocuk.forEach(c => {
                const cli = satirKur(c);
                altlariEkle(cli, c);
                ic.appendChild(cli);
            });
            li.appendChild(ic);
        };
        adimlar.forEach(a => {
            const li = satirKur(a);
            if (a.alt && a.alt.length > 1) {
                li.classList.add("grup-satir");
                const altListe = elYap("ol", "faz-alt-adimlar");
                a.alt.forEach(x => {
                    const xli = satirKur(x);
                    altlariEkle(xli, x);
                    altListe.appendChild(xli);
                });
                li.appendChild(altListe);
            } else if (a.alt && a.alt.length === 1) {
                altlariEkle(li, a.alt[0]);
            }
            liste.appendChild(li);
        });
        kok.appendChild(liste);
        fazEl.appendChild(kok);
    });
    akisBarGuncelle();
}

/* İŞ AKIŞI BARI YAZISI: bulunulan faz ve adım (iş akışı listesindeki
   numara ve adla), sağda tamamlanan adım sayısı (listedeki gibi gruplu
   sayılır). Başlangıç seçilmeden önce faz listesi yoksa boş kalır. */
function akisBarGuncelle() {
    const konumEl = document.getElementById("akis-konum");
    const ilerEl = document.getElementById("akis-ilerleme");
    if (!konumEl || !ilerEl) return;
    konumEl.innerHTML = "";
    ilerEl.textContent = "";
    if (!FAZLAR || !FAZLAR.length) return;
    let toplam = 0, tamam = 0, faz = null, adim = null;
    FAZLAR.forEach(f => {
        const ogeler = fazOgeleri(f);
        toplam += ogeler.length;
        tamam += ogeler.filter(a => a.bitis < aktifAdim).length;
        ogeler.forEach(a => {
            if (!adim && aktifAdim >= a.sira && aktifAdim <= a.bitis) { faz = f; adim = a; }
        });
    });
    if (faz) {
        konumEl.appendChild(elYap("span", "akis-faz", faz.no + " " + tireSade(faz.baslik)));
        const ayrac = elYap("span", "akis-ayrac", "›");
        ayrac.setAttribute("aria-hidden", "true");
        konumEl.appendChild(ayrac);
        konumEl.appendChild(elYap("span", "akis-adim", numarali(adim.kod, adim.baslik)));
    } else if (toplam && tamam >= toplam) {
        konumEl.appendChild(elYap("span", "akis-faz", "Bütün adımlar tamamlandı"));
    }
    if (toplam) ilerEl.textContent = tamam + " / " + toplam + " adım";
}

/* Sohbette bir adımın bloğunu bulur ve oraya kaydırır. Gruplu adımlar
   tek blokta alt bölüm olarak durur (.alt-bolum[data-adim]); tek
   adımlar kendi bloğundadır (.adim-blok[data-adim]). Aynı adım birden
   çok kez görülmüşse (geri dönüş) en sonuncusu. Grup satırına basılınca
   grubun ilk bulunan adımı. */
function adimBloguneGit(anahtar, grupAdimlari) {
    const adaylar = [anahtar].concat(grupAdimlari || []).filter(Boolean);
    let hedef = null;
    for (let i = 0; i < adaylar.length && !hedef; i++) {
        const sec = '.alt-bolum[data-adim="' + adaylar[i] + '"], .adim-blok[data-adim="' + adaylar[i] + '"]';
        const hepsi = sohbetEl.querySelectorAll(sec);
        if (hepsi.length) hedef = hepsi[hepsi.length - 1];
    }
    if (!hedef) return;
    hedef.scrollIntoView({ block: "start", behavior: "smooth" });
    hedef.classList.remove("blok-vurgu");
    void hedef.offsetWidth;            // animasyon yeniden başlasın
    hedef.classList.add("blok-vurgu");
    setTimeout(() => hedef.classList.remove("blok-vurgu"), 1600);
}

function aktifFaziAc() {
    FAZLAR.forEach((f, fi) => {
        if (f.adimlar.some(a => a.sira === aktifAdim)) acikFazlar.add(fi);
    });
}

/* İş akışı açılışta ayrıca istenmiyor: /karsilama yanıtı fazları
   zaten taşıyor. */


/* ==================== Üst özet kartları ==================== */
/*
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

/* Sonuç kartları (ÜRETİM · ELEME · MODEL) sağ bloğun MODEL GÖSTERGELERİ
   sekmesinde çizilir. Burada yalnız saklanır, sekme açıksa yeniden
   çizilir. */
function ozetGuncelle(o) {
    if (!o || !o.kartlar) return;
    /* Cipler cizilmez: VERİ ve SÖZLÜK kartlari ayni bilgiyi
       tasiyor ve ustune tiklanabiliyor. Alanlar govdede duruyor cunku
       seciliVeriSeti() onlari okuyor. */
    cipYaz(cipEl, null);
    cipYaz(sozlukCipEl, null);
    SONUC_KARTLARI = o.kartlar;
    if (aktifAnalizSekme === "ozet") analizCiz(aktifAnalizSekme);
}

/* SONUÇ KARTLARI MODEL GÖSTERGELERİ'nde çizilir: üretim ve eleme "Değişken
   Sayıları", model "Model Sonucu" başlığı altında. on_ekler: hangi kartlar
   ("ÜRETİM", "ELEME", "MODEL"; kartın etiketinin başı). Biçim: kırmızı
   etiket, koyu değer, iki alt satır, ulaşılmamış değer ∅. "hedef" dolu kart
   TIKLANABİLİR: ilgili sekmeyi açar. */
function sonucCiz(on_ekler) {
    const kartlar = SONUC_KARTLARI.filter(k => on_ekler.some(
        o => String(k.etiket || "").toLocaleUpperCase("tr").indexOf(o) === 0));
    if (!kartlar.length) {
        analizGovde.appendChild(elYap("div", "set-not",
            "Sonuç akış ilerledikçe burada görünür."));
        return;
    }
    kartlar.forEach(k => {
        const tiklanir = !!k.hedef;
        const kart = elYap(tiklanir ? "button" : "div", "sonuc-kart");
        if (tiklanir) {
            kart.type = "button";
            kart.onclick = () => { sayfaAc("calisma"); analizSekmeAc(k.hedef); };
        }
        if (k.ipucu) kart.title = k.ipucu;
        kart.appendChild(elYap("span", "ozet-etiket", tireSade(k.etiket)));
        const degerMetin = degerGoster(k.deger);
        kart.appendChild(elYap("span",
            "ozet-deger" + (degerMetin === BOS_SIMGE ? " bos" : ""), degerMetin));
        /* Satırlar BAŞLIK BÜYÜK HARFİ ile: "kural tabanlı üretim + AI
           keşfi" -> "Kural Tabanlı Üretim + AI Keşfi". Kısaltmalar (AI,
           SFA, KS, OOT) ve sayılar korunur. */
        [["ozet-ust", k.ust], ["ozet-alt", k.alt]].forEach(([sinif, ham]) => {
            const metin = baslikBuyuk(ham);
            if (metin) kart.appendChild(elYap("span", sinif, metin));
        });
        analizGovde.appendChild(kart);
    });
}


/* ============ ÖZET sayfası: Model Geliştirme Dokümanı ==================
   Sayfa Model Risk'e giden dokümanın kendisini çizer: künye + 20 numaralı bölüm + ek, her bölümün statüsü,
   kullanıcı düzenlemesi, Word çıktısı.

   NEDEN AYRI UÇTAN ALINIYOR
     Gövde büyük (tablolar + her bölümün düz metin karşılığı). Her sohbet
     turunun yanıtına bindirmek, kullanıcı bu sayfayı hiç açmasa bile her
     yanıta onlarca kilobayt eklerdi; sekme açıldığında bir kez istenir.

   NEDEN TEK BÖLÜM YENİDEN ÇİZİLİYOR
     /dokuman_bolum yalnızca kaydedilen bölümü döndürüyor. Sayfanın
     tamamını yeniden çizmek, kullanıcının bölümler içinde okuduğu
     yeri kaybetmesi demek olur. */
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
   Numara koşulsuz yazılsa bu iki bölümün adı "null." ile başlardı. */
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
   "İçerik boş mu" diye BAKILMAZ: platform bazı kullanıcı bölümlerine
   (örn. 18.) otomatik içerik koyar.
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
       bir bloğun ekranda hiç görünmemesi demek olur. */
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
       elle birleştirmek ekran okuyucuya "null." okuturdu. */
    alan.setAttribute("aria-label", tireSade(dokBolumAdi(b)) + " metni");
    alan.oninput = () => { DOK.taslak = alan.value; };
    kutu.appendChild(alan);

    kutu.appendChild(elYap("div", "dok-duzen-not",
        "Kaydettiğiniz metin, doküman yeniden üretildiğinde EZİLMEZ. "
        + "Hesaplanan hâline «özgün hâline dön» ile dönersiniz."));

    const ayak = elYap("div", "dok-ayak");

    const kaydet = elYap("button", "dok-dugme",
                         DOK.kaydediyor ? "Kaydediliyor" : "Kaydet");
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
       doğru. "Bayat damga" diye bir ara hâl YOK. */
    const taslak = (g.teslim_durumu || "") !== "hazir";
    dokDamgaEl.hidden = false;
    dokDamgaEl.className = "dok-damga " + (taslak ? "taslak" : "hazir");
    metinYaz(dokDamgaEl, metin);
    dokDamgaEl.title = "";
}

/* Uyarı şeridi üç sayıyı birden gösterir: bloker · eksik · kısmi. */
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

    if (dokBaslikEl) metinYaz(dokBaslikEl, (g && g.baslik) || "");
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
                DOK.yukleniyor ? "Doküman hazırlanıyor"
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
    metinYaz(dokIndirmeHataEl, mesaj || "");
    dokIndirmeHataEl.hidden = !mesaj;
}


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
    dokWordBtn.textContent = "İndiriliyor";
    const bitir = () => {
        dokWordBtn.disabled = false;
        dokWordBtn.textContent = etiket;
    };

    fetch(getWebAppBackendUrl("dokuman_word")
          + "?oturum_id=" + encodeURIComponent(OTURUM_ID))
        .then(r => {
            /* Uç hata hâlinde .docx değil DÜZ METİN dönüyor; onu dosya
               diye indirmek kullanıcıya açılmayan bir belge vermek olur. */
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
    if (metin !== undefined) metinYaz(e, metin);
    return e;
}

/* ADIM ATIFLARI KALIN. Arka uç "nerede ne olacağını" söyleyen
   cümlelerde adımı **01.2.3 Eksik Sözlük Tanımları** biçiminde
   işaretler. İşaret yalnız kelime sınırında tanınır (a**2 gibi bir
   ifade işaret sayılmaz); işaretli parça <strong>, gerisi düz metin
   olarak yazılır. */
const KALIN_ISARET = /(^|[\s«("'(])\*\*(\S(?:[^*\n]*?\S)?)\*\*(?=$|[\s.,;:!?»)"'’'])/g;

function metinYaz(el, metin) {
    const s = tireSade(metin);
    el.textContent = "";
    let son = 0;
    s.replace(KALIN_ISARET, (tam, on, ic, yer) => {
        el.appendChild(document.createTextNode(s.slice(son, yer) + on));
        const k = document.createElement("strong");
        k.textContent = ic;
        el.appendChild(k);
        son = yer + tam.length;
        return tam;
    });
    el.appendChild(document.createTextNode(s.slice(son)));
    return el;
}

/* title ve aria-label düz metindir: işaret düşer, metin kalır. */
function duzMetin(metin) {
    return tireSade(metin).replace(KALIN_ISARET, "$1$2");
}

/* Backend'e bagli olmayan sekmeler: icerik iskelet, bu acikca yazilir.
   Tiklanamayan sahte aksiyon satirlari YOK.
   "Hazırlanıyor" bilgisi YALNIZCA burada ve sekmenin title'inda durur;
   sekme etiketinin rengiyle anlatilmaz (soluk sekme hata gibi gorunur). */
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
    /* Bu sekmelerin hesabi henuz bagli degil: secimin neye etki edecegini gostermek icin secilen setin
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
   dokuman da bu ciktiyi kullanir: tek tablo cizici, tek gorsel dil. */
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
            td.title = duzMetin(h === null || h === undefined ? "" : h);
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

    /* KARTLAR HER ZAMAN ACIK: teyit SOHBET
       BLOGUNDA yapiliyor; sag panel yalnizca aciklama veriyor, orada
       gizlenecek bir karar yok. */
    (v.kartlar || []).forEach(k => {
        const kart = elYap("div", "iskele-kart");
        const bas = elYap("div", "iskele-baslik", k.baslik);
        /* Kaynak, kayıt yeri gibi ikincil bilgiler satır değil "i"de. */
        if (k.bilgi) bas.appendChild(bolmeBilgiSimgesi(tireSade(k.bilgi), k.baslik));
        kart.appendChild(bas);
        if (k["not"]) kart.appendChild(elYap("div", "panel-not", k["not"]));
        (k.satirlar || []).forEach(s => {
            const satir = elYap("div", "iskele-satir");
            satir.appendChild(elYap("span", "panel-etiket", s.etiket));
            const deger = elYap("span", "iskele-deger", degerGoster(s.deger));
            deger.title = duzMetin(s.deger === null || s.deger === undefined
                                   ? "" : s.deger);
            satir.appendChild(deger);
            kart.appendChild(satir);
        });
        analizGovde.appendChild(kart);
    });

    // Feature tablosu kartlardan SONRA gelir: kartlar veri setinin ozeti,
    // tablo tek tek kolonlar. Once genel, sonra ayrinti.
    /* SAG PANEL SALT OKUNUR. Degisken listesi burada
       yalnizca GORULUYOR; isaretleme ve tanim duzenleme sohbetteki
       sozluk teyidi kartinda yapiliyor. */
    if (v.feature_tablo) featureTabloCiz(ftSaltOku(v.feature_tablo));
    if (v.tablo) panelTabloCiz(v.tablo);
}


/* ==================== Feature tablosu ==================== */
/* VERİ & SÖZLÜK sekmesinde 1.000'in uzerinde satir olabiliyor.  Yalnizca gorunen pencere
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
   olarak gosterilmiyor (SOZLESME7 §5) ama satiri soluk cizmek ve
   acilista hangi kutunun isaretli gelecegini bilmek icin okunuyor. */
const FT_DISI = "süreç dışı";

/* ÜÇ KOLON: değişken, tip, sözlük tanımı. NULL % kolonu, süreç dışı
   kararının VERİLDİĞİ yerde - sohbetteki teyit tablosunda - onay
   kutusunun hemen solunda duruyor. Satır gövdesi null_oran'ı taşıyor:
   satıra tıklayınca açılan detay ve null eşiği süzgeci onu okuyor.

   Panel karar yeri değil, AÇIKLAMA yeri: düzenleme ve süreç dışı
   işaretleme sohbetteki kartta yapılıyor (bkz. ftSaltOku). */
/* Kolon kartı alanları (akis KART_ADLARI ile aynı sıra). */
const FT_KART_ALANLARI = [["konu", "Konu"], ["yon", "Yön"], ["nitelik", "Nitelik"], ["zaman", "Zaman"],
                          ["olcu", "Ölçü"], ["istatistik", "İstatistik"], ["karsilastirma", "Karşılaştırma"],
                          ["birim", "Birim"], ["diger", "Diğer"]];
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
    kolonSz: {},              // alan -> Excel tarzi kolon suzgeci (bkz. szMenuAc)
    sira: null, yon: 1,
    /* ISARETLI = SUREC DISI: kutu dogrudan bir karar. */
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
/* Arama, tip, null eşiği ve kolon süzgeçleri. haricAlan verilirse o
   kolonun süzgeci atlanır: süzgeç menüsünün değer listesi, Excel'deki
   gibi DİĞER süzgeçlerden geçen satırlardan kurulur. */
function ftSuzListe(haricAlan) {
    const liste = (FT.veri && FT.veri.satirlar) || [];
    const aranan = ftSade(FT.arama).trim();
    const esik = FT.nullEsik === "" ? null : Number(FT.nullEsik) / 100;

    const tip = String(FT.tip || "").trim();
    const kolonSz = Object.keys(FT.kolonSz)
        .filter(a => a !== haricAlan && szAktif(FT.kolonSz[a]))
        .map(a => [a, FT.kolonSz[a]]);

    return liste.filter(s => {
        for (const [a, sz] of kolonSz) if (!szUyar(s[a], sz)) return false;
        if (aranan && ftSade(s.feature).indexOf(aranan) === -1
            && ftSade(s.yeni_ad).indexOf(aranan) === -1
            && ftSade(s.tanim).indexOf(aranan) === -1) return false;
        /* TIP SUZGECI tam esleme: "sayısal" secildiginde "sayısal"
           kolonlar gelir. Parca eslemesi yapsaydik gelecekte eklenecek
           bir tip adi baskasini da yakalardi. */
        if (tip && String(s.tip || "").trim() !== tip) return false;
        if (esik !== null && isFinite(esik)) {
            /* null_oran bilinmiyorsa esigi GECTIGI soylenemez: kolon
               eleniyor. */
            if (s.null_oran === null || s.null_oran === undefined) return false;
            if (Number(s.null_oran) <= esik) return false;
        }
        return true;
    });
}

function ftSuz() {
    let sonuc = ftSuzListe(null);

    if (FT.sira) {
        const alan = FT.sira;
        const sayisal = (FT_ALANLAR.find(a => a.alan === alan) || {}).sayisal;
        const yon = FT.yon;
        sonuc = sonuc.slice().sort((a, b) => {
            const x = a[alan], y = b[alan];
            
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
                       aciklama: "onerilen_sozluk.xlsx",
                       onizleme: "veri_onizleme.xlsx" };
/* Tür -> uç. Önerilen sözlük kendi ucundan gelir (teyit kapısı yok). */
const EXCEL_UCLARI = { aciklama: "aciklama_excel",
                       onizleme: "veri_onizleme_excel" };

/* govdeFn verilirse indirme POST: gövde o an ekranda görünen süzülmüş
   hâli taşır, dosyada "Tümü" ve "Filtrelenmiş" iki ayrı sayfa olur. */
function excelSeridiYap(tur, etiket, ipucu, govdeFn) {
    const el = elYap("div", "excel-serit");

    const btn = document.createElement("button");
    btn.type = "button";
    /* YEŞİL ve İKİ DURUMLU: basılabildiğinde koyu
       yeşil, basılamadığında açık yeşil.  Kilitli ama
       görünür düğme "henüz değil" diyor ve ipucunda neden yazıyor. */
    btn.className = "excel-btn";
    btn.innerHTML = EXCEL_SIMGESI;
    btn.appendChild(document.createTextNode(tireSade(etiket)));
    btn.disabled = true;
    btn.title = duzMetin(ipucu || "");
    el.appendChild(btn);

    const hata = elYap("span", "excel-hata");
    hata.hidden = true;
    el.appendChild(hata);

    btn.onclick = () => {
        if (btn.disabled) return;
        hata.hidden = true;
        const eski = btn.lastChild.nodeValue;
        btn.disabled = true;
        btn.lastChild.nodeValue = "İndiriliyor";
        const bitir = () => {
            btn.disabled = false;
            btn.lastChild.nodeValue = eski;
        };
        const uc = getWebAppBackendUrl(EXCEL_UCLARI[tur] || "degisken_excel");
        (govdeFn
            ? fetch(uc, { method: "POST",
                          headers: { "Content-Type": "application/json" },
                          body: JSON.stringify(Object.assign(
                              { tur: tur, oturum_id: OTURUM_ID }, govdeFn())) })
            : fetch(uc + "?tur=" + encodeURIComponent(tur)
                    + "&oturum_id=" + encodeURIComponent(OTURUM_ID)))
            .then(r => {
                /* Uç hata hâlinde .xlsx değil DÜZ METİN dönüyor; onu
                   dosya diye indirmek açılmayan bir tablo vermek olur. */
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
                metinYaz(hata, "Excel indirilemedi: " + ((e && e.message) || e));
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
    metinYaz(el, metin || "");
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
        
        const oz = document.querySelector(".teyit-kart .teyit-ozet");
        if (oz && d.ozet) metinYaz(oz, d.ozet);
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
   hiçbir anda ayrışmıyor; onay bu uçta veriliyor. */
/* SATIR RENGİ.
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

/* 01.2.3 AİLE: tanım aynı ailedeki bir kolonun tanımından sayılar
   değiştirilerek aktarıldı (dil modeli bu kolon için çağrılmadı). */
function aileCipi(td, tr, kaynak) {
    if (!td || !tr || tr.querySelector(".dg-aile-cip")) return;
    const c = elYap("span", "dg-rol dg-aile-cip", "Aileden");
    c.title = "Aileden: " + (kaynak ? kaynak + " kolonunun" : "ailedeki bir kolonun")
        + " tanımından sayılar değiştirilerek aktarıldı; bu kolon için dil modeli çağrılmadı.";
    td.appendChild(c);
    tr.classList.add("dg-aile-kaynak");
}

function dgRenk(tr, metin, oneri, karar) {
    if (!tr) return;
    const m = String(metin || "").trim();
    const o = String(oneri || "").trim();
    tr.classList.toggle("dg-bos", !karar && !m);
    const hafiza = tr.classList.contains("dg-hafiza-satir");
    const aile = !hafiza && tr.classList.contains("dg-aile-kaynak");
    tr.classList.toggle("dg-llm", !karar && !!m && !!o && m === o && !hafiza && !aile);
    tr.classList.toggle("dg-hafiza-renk", !karar && !!m && !!o && m === o && hafiza);
    tr.classList.toggle("dg-aile-renk", !karar && !!m && !!o && m === o && aile);
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
/* 01.2 RENK: mavi dil modeli
   önerisi, mor onaylı tanım (hafızada), sarı boş,
   yeşil sizin yazdığınız ya da değiştirdiğiniz. */
const DG_LEJANT_KARAR = [["dg-l-llm", "Dil Modeli Önerisi"],
                         ["dg-l-aile", "Aileden"],
                         ["dg-l-hafiza", "Onaylı Tanım"],
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
        if (tipEl && d.tip) metinYaz(tipEl, d.tip);
        const oz = document.querySelector(".teyit-kart .teyit-ozet");
        if (oz && d.ozet) metinYaz(oz, d.ozet);
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

/* ==================== EXCEL TARZI KOLON SÜZGECİ ====================
   Değişken Listesi ve Veri Önizleme başlıklarındaki ▾ düğmesi: Excel'in
   otomatik süzgeci gibi bir menü açar - sıralama, koşula göre süzme
   (metin: içerir / ile başlar ...; sayı: > < arasında ...) ve aranabilir
   değer listesi (Tümünü Seç, her değerin satır sayısı, "(Boş)").
   Listede yalnız DİĞER süzgeçlerden geçen satırların değerleri çıkar
   (Excel'de de öyle). Süzgeç yalnız ekranı daraltır, veriye dokunmaz.

   Süzgeç nesnesi: { secili: Set(anahtar) | null, kosul: {op, a, b, sayisal} | null } */
const SZ_BOS = "\u0000bos";
const SZ_SAYI = /^-?\d+(\.\d+)?([eE][-+]?\d+)?$/;
const SZ_SIMGE =
    '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor"'
    + ' stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    + '<path d="M3 5h18l-7 8.5V19l-4 2v-7.5L3 5z"/></svg>';
const SZ_KOSUL_METIN = [
    { deger: "", etiket: "Koşul yok" },
    { deger: "icerir", etiket: "İçerir" }, { deger: "icermez", etiket: "İçermez" },
    { deger: "baslar", etiket: "İle başlar" }, { deger: "biter", etiket: "İle biter" },
    { deger: "esit", etiket: "Eşittir" }, { deger: "esit_degil", etiket: "Eşit değildir" },
    { deger: "bos", etiket: "Boş" }, { deger: "dolu", etiket: "Dolu" }
];
const SZ_KOSUL_SAYI = [
    { deger: "", etiket: "Koşul yok" },
    { deger: "esit", etiket: "Eşittir (=)" }, { deger: "esit_degil", etiket: "Eşit değildir (≠)" },
    { deger: "buyuk", etiket: "Büyüktür (>)" }, { deger: "buyuk_esit", etiket: "Büyük veya eşit (≥)" },
    { deger: "kucuk", etiket: "Küçüktür (<)" }, { deger: "kucuk_esit", etiket: "Küçük veya eşit (≤)" },
    { deger: "arasinda", etiket: "Arasında (uçlar dahil)" },
    { deger: "bos", etiket: "Boş" }, { deger: "dolu", etiket: "Dolu" }
];
const SZ_KISA = { icerir: "içerir", icermez: "içermez", baslar: "ile başlar",
    biter: "ile biter", esit: "=", esit_degil: "≠", buyuk: ">", buyuk_esit: "≥",
    kucuk: "<", kucuk_esit: "≤", arasinda: "arasında", bos: "boş", dolu: "dolu" };

function szBosMu(v) { return v === null || v === undefined || v === ""; }
function szAnahtar(v) { return szBosMu(v) ? SZ_BOS : String(v); }
function szSayiMi(v) { return SZ_SAYI.test(String(v).trim()); }
/* Virgüllü ondalık da kabul: "1,5" -> 1.5 */
function szSayi(s) {
    const t = String(s === null || s === undefined ? "" : s).trim().replace(",", ".");
    return t === "" ? NaN : Number(t);
}
/* Kolon sayısal mı: dolu değerlerinin TAMAMI sayı gibi okunuyorsa. */
function szSayisalMi(degerler) {
    let dolu = 0;
    for (const v of degerler) {
        if (szBosMu(v)) continue;
        if (!szSayiMi(v)) return false;
        dolu++;
    }
    return dolu > 0;
}

function szKosulUyar(v, k) {
    if (!k || !k.op) return true;
    const bos = szBosMu(v);
    if (k.op === "bos") return bos;
    if (k.op === "dolu") return !bos;
    if (bos) return k.op === "icermez" || k.op === "esit_degil";
    if (k.sayisal) {
        const x = Number(v), a = szSayi(k.a), b = szSayi(k.b);
        if (!isFinite(x)) return false;
        switch (k.op) {
            case "esit": return x === a;
            case "esit_degil": return x !== a;
            case "buyuk": return x > a;
            case "buyuk_esit": return x >= a;
            case "kucuk": return x < a;
            case "kucuk_esit": return x <= a;
            case "arasinda": return x >= Math.min(a, b) && x <= Math.max(a, b);
        }
        return true;
    }
    const s = ftSade(v), a = ftSade(k.a);
    switch (k.op) {
        case "icerir": return s.indexOf(a) !== -1;
        case "icermez": return s.indexOf(a) === -1;
        case "baslar": return s.startsWith(a);
        case "biter": return s.endsWith(a);
        case "esit": return s === a;
        case "esit_degil": return s !== a;
    }
    return true;
}
function szUyar(v, sz) {
    if (!sz) return true;
    if (sz.secili && !sz.secili.has(szAnahtar(v))) return false;
    return szKosulUyar(v, sz.kosul);
}
function szAktif(sz) { return !!(sz && (sz.secili || (sz.kosul && sz.kosul.op))); }
function szDegerAdi(k) { return k === SZ_BOS ? "(Boş)" : k; }

/* Çip metni: "TİP: sayısal, kategorik" / "BAKIYE: > 1000" */
function szOzet(sz) {
    const p = [];
    const k = sz.kosul;
    if (k && k.op) {
        if (k.op === "bos" || k.op === "dolu") p.push(SZ_KISA[k.op]);
        else if (k.op === "arasinda") p.push(k.a + " – " + k.b);
        else p.push(SZ_KISA[k.op] + " " + k.a);
    }
    if (sz.secili) {
        const d = [...sz.secili].map(szDegerAdi);
        p.push(d.length <= 3 ? d.join(", ") : ftBinlik(d.length) + " değer");
    }
    return p.join(" · ");
}

/* Başlıktaki ▾ düğmesi. Tık sıralamaya gitmesin diye yayılım durur. */
function szDugme(etiket, aktif, ac) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "sz-btn" + (aktif ? " aktif" : "");
    b.innerHTML = SZ_SIMGE;
    b.title = etiket + " · süz ve sırala" + (aktif ? " (süzgeç açık)" : "");
    b.setAttribute("aria-label", etiket + " kolonunu süz ve sırala");
    b.setAttribute("aria-haspopup", "dialog");
    b.onclick = ev => { ev.stopPropagation(); ac(b); };
    b.onkeydown = ev => ev.stopPropagation();
    return b;
}

let SZ_MENU = null;
function szMenuKapat() {
    if (!SZ_MENU) return;
    SZ_MENU.remove();
    SZ_MENU = null;
    document.removeEventListener("mousedown", szDisTik, true);
    document.removeEventListener("keydown", szTus, true);
}
function szDisTik(ev) { if (SZ_MENU && !SZ_MENU.contains(ev.target)) szMenuKapat(); }
function szTus(ev) { if (ev.key === "Escape") { ev.stopPropagation(); szMenuKapat(); } }

/* o: { baslik, degerler (diğer süzgeçlerden geçen satırların değerleri),
        sayisal, mevcut (süzgeç | undefined), sirala(yon), uygula(sz | null) } */
const SZ_LISTE_SINIRI = 2000;
function szMenuAc(dugme, o) {
    const ayniDugme = SZ_MENU && SZ_MENU._dugme === dugme;
    szMenuKapat();
    if (ayniDugme) return;                 // ikinci tık kapatır
    const sayac = new Map();
    o.degerler.forEach(v => { const k = szAnahtar(v); sayac.set(k, (sayac.get(k) || 0) + 1); });
    const anahtarlar = [...sayac.keys()].sort((a, b) => {
        if (a === SZ_BOS) return 1;
        if (b === SZ_BOS) return -1;
        if (o.sayisal) return Number(a) - Number(b);
        return a.localeCompare(b, "tr");
    });
    const mevcut = o.mevcut || {};
    const secim = new Set(mevcut.secili ? anahtarlar.filter(k => mevcut.secili.has(k)) : anahtarlar);

    const m = elYap("div", "sz-menu");
    m.setAttribute("role", "dialog");
    m.setAttribute("aria-label", o.baslik + " süzgeci");
    m._dugme = dugme;
    m.appendChild(elYap("div", "sz-baslik", o.baslik));

    /* ---- Sıralama ---- */
    const sir = elYap("div", "sz-sirala");
    [[1, o.sayisal ? "Küçükten Büyüğe" : "A → Z"], [-1, o.sayisal ? "Büyükten Küçüğe" : "Z → A"]]
        .forEach(([yon, et]) => {
            const b = elYap("button", "sz-mini", (yon === 1 ? "↑ " : "↓ ") + et);
            b.type = "button";
            b.onclick = () => { szMenuKapat(); o.sirala(yon); };
            sir.appendChild(b);
        });
    m.appendChild(sir);

    /* ---- Koşul ---- */
    m.appendChild(elYap("div", "sz-bolum", o.sayisal ? "Sayı Koşulu" : "Metin Koşulu"));
    const kosulKap = elYap("div", "sz-kosul");
    const op = document.createElement("select");
    op.className = "ft-secim";
    op.setAttribute("aria-label", "Koşul");
    (o.sayisal ? SZ_KOSUL_SAYI : SZ_KOSUL_METIN).forEach(x => {
        const e = document.createElement("option");
        e.value = x.deger; e.textContent = x.etiket; op.appendChild(e);
    });
    const k0 = mevcut.kosul || {};
    op.value = k0.op || "";
    const giris = ph => {
        const g = document.createElement("input");
        g.type = "text"; g.className = "ft-ara sz-giris"; g.placeholder = ph;
        g.onkeydown = ev => { if (ev.key === "Enter") { ev.preventDefault(); uygula(); } };
        return g;
    };
    const ga = giris(o.sayisal ? "Değer" : "Metin"), gb = giris("ve");
    ga.value = k0.a || ""; gb.value = k0.b || "";
    kosulKap.appendChild(op); kosulKap.appendChild(ga); kosulKap.appendChild(gb);
    const girisGoster = () => {
        ga.hidden = !op.value || op.value === "bos" || op.value === "dolu";
        gb.hidden = op.value !== "arasinda";
    };
    op.onchange = () => { girisGoster(); if (!ga.hidden) ga.focus(); };
    girisGoster();
    m.appendChild(kosulKap);

    /* ---- Değer listesi ---- */
    m.appendChild(elYap("div", "sz-bolum", "Değerler"));
    const ara = document.createElement("input");
    ara.type = "search"; ara.className = "ft-ara sz-ara";
    ara.placeholder = "Değerlerde ara";
    ara.setAttribute("aria-label", "Değerlerde ara");
    m.appendChild(ara);
    const liste = elYap("div", "sz-liste");
    m.appendChild(liste);
    let gorunen = anahtarlar;
    const listeCiz = () => {
        liste.textContent = "";
        const q = ftSade(ara.value).trim();
        gorunen = q ? anahtarlar.filter(k => ftSade(szDegerAdi(k)).indexOf(q) !== -1) : anahtarlar;
        const tum = elYap("label", "sz-satir sz-tum");
        const tk = document.createElement("input");
        tk.type = "checkbox";
        const secili = gorunen.filter(k => secim.has(k)).length;
        tk.checked = gorunen.length > 0 && secili === gorunen.length;
        tk.indeterminate = secili > 0 && secili < gorunen.length;
        tk.onchange = () => {
            gorunen.forEach(k => tk.checked ? secim.add(k) : secim.delete(k));
            listeCiz();
        };
        tum.appendChild(tk);
        tum.appendChild(elYap("span", "sz-ad", q ? "(Arama Sonuçlarının Tümü)" : "(Tümünü Seç)"));
        tum.appendChild(elYap("span", "sz-adet", ftBinlik(gorunen.length)));
        liste.appendChild(tum);
        gorunen.slice(0, SZ_LISTE_SINIRI).forEach(k => {
            const s = elYap("label", "sz-satir" + (k === SZ_BOS ? " sz-bos" : ""));
            const c = document.createElement("input");
            c.type = "checkbox";
            c.checked = secim.has(k);
            c.onchange = () => {
                c.checked ? secim.add(k) : secim.delete(k);
                const n = gorunen.filter(x => secim.has(x)).length;
                tk.checked = n === gorunen.length;
                tk.indeterminate = n > 0 && n < gorunen.length;
            };
            s.appendChild(c);
            const ad = elYap("span", "sz-ad", szDegerAdi(k));
            ad.title = szDegerAdi(k);
            s.appendChild(ad);
            s.appendChild(elYap("span", "sz-adet", ftBinlik(sayac.get(k))));
            liste.appendChild(s);
        });
        if (gorunen.length > SZ_LISTE_SINIRI)
            liste.appendChild(elYap("div", "sz-not", "İlk " + ftBinlik(SZ_LISTE_SINIRI)
                + " değer gösteriliyor; aramayla daraltın."));
        if (!gorunen.length) liste.appendChild(elYap("div", "sz-not", "Eşleşen değer yok."));
    };
    let zam = null;
    ara.oninput = () => { clearTimeout(zam); zam = setTimeout(listeCiz, 120); };
    ara.onkeydown = ev => { if (ev.key === "Enter") { ev.preventDefault(); clearTimeout(zam); listeCiz(); uygula(); } };
    listeCiz();

    const hata = elYap("div", "sz-hata");
    hata.hidden = true;
    m.appendChild(hata);

    /* ---- Alt düğmeler ---- */
    const alt = elYap("div", "sz-alt");
    const temizle = elYap("button", "sz-mini", "Süzgeci Kaldır");
    temizle.type = "button";
    temizle.disabled = !szAktif(o.mevcut);
    temizle.onclick = () => { szMenuKapat(); o.uygula(null); };
    const iptal = elYap("button", "sz-mini", "İptal");
    iptal.type = "button";
    iptal.onclick = szMenuKapat;
    const tamam = elYap("button", "sz-mini sz-birincil", "Uygula");
    tamam.type = "button";
    alt.appendChild(temizle);
    alt.appendChild(elYap("span", "sz-bosluk"));
    alt.appendChild(iptal);
    alt.appendChild(tamam);
    m.appendChild(alt);

    function uygula() {
        const hataYaz = t => { hata.textContent = t; hata.hidden = false; };
        let kosul = null;
        if (op.value) {
            kosul = { op: op.value, a: ga.value.trim(), b: gb.value.trim(), sayisal: !!o.sayisal };
            const degerGerek = op.value !== "bos" && op.value !== "dolu";
            if (degerGerek && kosul.a === "") return hataYaz("Koşul için bir değer yazın.");
            if (op.value === "arasinda" && kosul.b === "") return hataYaz("Aralığın iki ucunu da yazın.");
            if (o.sayisal && degerGerek && (!isFinite(szSayi(kosul.a))
                || (op.value === "arasinda" && !isFinite(szSayi(kosul.b)))))
                return hataYaz("Sayı koşulu için sayı yazın (ondalık ayırıcı nokta ya da virgül).");
        }
        /* Arama açıkken Uygula: Excel'deki gibi yalnız arama sonuçlarından
           işaretli olanlar kalır. */
        const q = ftSade(ara.value).trim();
        const kume = q ? gorunen.filter(k => secim.has(k)) : anahtarlar.filter(k => secim.has(k));
        if (!kume.length) return hataYaz("En az bir değer işaretleyin.");
        const secili = (!q && kume.length === anahtarlar.length) ? null : new Set(kume);
        szMenuKapat();
        o.uygula(secili || kosul ? { secili: secili, kosul: kosul } : null);
    }
    tamam.onclick = uygula;

    /* Tema değişkenleri #kabuk altında tanımlı: menü oraya eklenir. */
    (document.getElementById("kabuk") || document.body).appendChild(m);
    /* Hesap ekran pikseliyle; konum tasarım pikseline çevrilerek yazılır. */
    const z = ekranOlcegi();
    const r = dugme.getBoundingClientRect();
    const en = m.offsetWidth * z, boy = m.offsetHeight * z;
    let x = r.left, y = r.bottom + 4;
    if (x + en > window.innerWidth - 8) x = Math.max(8, window.innerWidth - en - 8);
    if (y + boy > window.innerHeight - 8) y = Math.max(8, r.top - boy - 4);
    m.style.left = (x / z) + "px";
    m.style.top = (y / z) + "px";
    SZ_MENU = m;
    document.addEventListener("mousedown", szDisTik, true);
    document.addEventListener("keydown", szTus, true);
    ara.focus();
}

/* Etkin süzgeç çipleri + "Filtreleri Temizle". ogeler: [{etiket, kaldir}] */
function szCiplarCiz(kap, ogeler, hepsiniTemizle) {
    kap.textContent = "";
    kap.hidden = !ogeler.length;
    if (!ogeler.length) return;
    kap.appendChild(elYap("span", "sz-cip-baslik", "Süzgeçler:"));
    ogeler.forEach(x => {
        const c = elYap("span", "sz-cip");
        const t = elYap("span", "sz-cip-ad", x.etiket);
        t.title = x.etiket;
        c.appendChild(t);
        const k = elYap("button", "sz-cip-kaldir", "×");
        k.type = "button";
        k.title = "Bu süzgeci kaldır";
        k.setAttribute("aria-label", x.etiket + " süzgecini kaldır");
        k.onclick = x.kaldir;
        c.appendChild(k);
        kap.appendChild(c);
    });
    const t = elYap("button", "sz-temizle", "Filtreleri Temizle");
    t.type = "button";
    t.onclick = hepsiniTemizle;
    kap.appendChild(t);
}

/* SAG PANEL: ARAMA + TIP SUZGECI + SIRALAMA.

   Null'a göre süzme ve sıralama sohbetteki
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
    ara.placeholder = "Değişken adı veya sözlük tanımında ara";
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
               geri donusu zor bir kaza olurdu. */
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
        h.appendChild(elYap("span", "sz-etiket", etiket + ok));
        h.title = etiket + " sütununa göre sırala";
        /* Excel tarzı süzgeç düğmesi (▾): sıralama, koşul, değer listesi. */
        h.appendChild(szDugme(etiket, szAktif(FT.kolonSz[a.alan]), b => szMenuAc(b, {
            baslik: etiket,
            degerler: ftSuzListe(a.alan).map(s => s[a.alan]),
            sayisal: false,
            mevcut: FT.kolonSz[a.alan],
            sirala: yon => { FT.sira = a.alan; FT.yon = yon; ftBasaSar(); ftTazele(); },
            uygula: sz => {
                if (sz) FT.kolonSz[a.alan] = sz; else delete FT.kolonSz[a.alan];
                ftBasaSar(); ftTazele();
            }
        })));
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
   Taslak FT.taslak'ta durur: tablo her tazelemede yeniden ciziliyor. */
function ftTanimHucresi(s) {
    const h = elYap("span", "ft-hucre ft-tanim");
    h.setAttribute("role", "cell");
    h.setAttribute("data-alan", "tanim");

    const deger = FT.taslak.has(s.feature)
        ? FT.taslak.get(s.feature)
        : (s.tanim === null || s.tanim === undefined ? "" : String(s.tanim));

    if (!(FT.veri && FT.veri.duzenlenebilir)) {
        h.textContent = degerGoster(s.tanim);
        /*
           Sözlük hiç bağlanmadıysa hangi adımda bağlanacağı, kopya
           çıkarılamadıysa nedeni yazıyor. */
        h.title = duzMetin((FT.veri && FT.veri.duzenleme_notu)
                           || "Tanımlar salt okunur.");
        return h;
    }

    /* TEXTAREA: tanım tamamı okunabilsin diye satır kaydırarak uzar. */
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
        /* 01.2.4.4'te adı değişen kolon: yeni ad, altında soluk eski ad
           (AMP_VERISETI 01.3'te yeni adla yazılır). */
        if (a.alan === "feature" && s.yeni_ad) {
            const h = elYap("span", "ft-hucre " + (a.sinif || ""));
            h.setAttribute("role", "cell");
            h.setAttribute("data-alan", a.alan);
            h.appendChild(elYap("span", "ft-yeni-ad", s.yeni_ad));
            h.appendChild(elYap("span", "ft-eski-ad", "eski: " + s.feature));
            h.title = s.yeni_ad + " (eski adı " + s.feature + ")";
            satir.appendChild(h);
            return;
        }
        let metin;
        if (a.alan === "null_oran") metin = ftOran(s.null_oran);
        else metin = degerGoster(s[a.alan]);
        const h = elYap("span", "ft-hucre " + (a.sinif || "")
                        + (a.sayisal ? " ft-sayi" : ""), metin);
        h.setAttribute("role", "cell");
        h.setAttribute("data-alan", a.alan);
        h.title = duzMetin(s[a.alan] === null || s[a.alan] === undefined
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

/* SATIRLAR DEĞİŞKEN YÜKSEKLİKTE. Çizim PARÇA PARÇA: ilk FT_PARCA satır çizilir, kaydırma sona
   yaklaştıkça bir parça daha eklenir. 1.042 satırın hepsi bir anda DOM'a
   basılmıyor; uzun tanım alt satıra kayıyor. */
const FT_PARCA = 120;

/* TOPLU YÜKSEKLİK: çok satırlı açıklama kutuları (1.000'i aşan satır)
   yüksekliklerini TEK karede, tek yerleşim hesabıyla alır: önce hepsine
   "auto" yazılır, sonra hepsi okunur, sonra hepsine yazılır. Kutu kutu
   yaz ve oku sırası her kutuda bütün sayfayı yeniden yerleştirir;
   1.038 satırlı tabloda sayfa saniyelerce donuyordu.
   el._boyKenar === false: yüksekliğe kenarlık eklenmez. */
const BOYLA_KUYRUK = new Set();
let boylaPlanli = false;
function boylaPlanla(el) {
    if (!el) return;
    BOYLA_KUYRUK.add(el);
    if (boylaPlanli) return;
    boylaPlanli = true;
    requestAnimationFrame(() => {
        boylaPlanli = false;
        const ogeler = [...BOYLA_KUYRUK].filter(e => e.isConnected);
        BOYLA_KUYRUK.clear();
        ogeler.forEach(e => { e.style.height = "auto"; });
        const olcu = ogeler.map(e => [e, e._boyKenar === false ? 0 : e.offsetHeight - e.clientHeight, e.scrollHeight]);
        olcu.forEach(([e, kenar, yuk]) => { if (yuk) e.style.height = (yuk + kenar) + "px"; });
    });
}
/* Tek gözcü: genişliği değişen kutular toplu ölçülür (kutu başına ayrı
   ResizeObserver yerine). */
const BOYLA_GOZCU = window.ResizeObserver ? new ResizeObserver(girdiler => {
    girdiler.forEach(g => {
        const e = g.target, en = g.contentRect.width;
        if (e._sonEn === en) return;
        e._sonEn = en;
        boylaPlanla(e);
    });
}) : null;

function ftKutuBoyu(el) {
    el.style.height = "auto";
    el.style.height = el.scrollHeight + 2 + "px";
}

function ftSatirEkle(adet) {
    const n = FT.suzulmus.length;
    const bas = FT.gosterilen || 0;
    const son = Math.min(n, bas + adet);
    if (son <= bas) return;
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
                : "Kolon listesi " + adimAtfi("veri_profili", "Veri Profili ve Kalite") + " adımından sonra dolar."));
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

    kutu.appendChild(elYap("div", "ft-detay-ad", s.yeni_ad || s.feature));
    if (s.yeni_ad) kutu.appendChild(elYap("div", "ft-eski-ad", "Eski adı: " + s.feature
        + ". Yeni ad Kolon Adları adımında onaylandı; AMP_VERISETI bu adla yazılır."));
    /* Satir govdesinde (SOZLESME7 §5) tekil/ornek gelmeyebilir.
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
    // IV / C yalnizca SFA calistiysa var.
    if (s.iv !== null && s.iv !== undefined) satirlar.push(["IV", ftOndalik(s.iv)]);
    if (s.c !== null && s.c !== undefined) satirlar.push(["C-value", ftOndalik(s.c)]);
    /* KOLON KARTI (Kolon Kartları adımında onaylanan): orijinal açıklama
       (güncel tanımdan farklıysa), kart alanları, ek bilgi ve not. */
    const kart = s.kart || {};
    if (kart.orijinal && kart.orijinal.trim() !== String(s.tanim || "").trim())
        satirlar.push(["Orijinal Açıklama", kart.orijinal]);
    FT_KART_ALANLARI.forEach(([alan, ad]) => {
        if (kart.kart && kart.kart[alan]) satirlar.push(["Kart: " + ad, kart.kart[alan]]);
    });
    if (kart.ek) satirlar.push(["Ek Bilgi", kart.ek]);
    if (kart.not) satirlar.push(["Notunuz", kart.not]);

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

/* ==================== 01.2.4 SONUÇLARI (Değişken Listesi'nin altında) ====
   Sözlük ve Kolon Adı Kontrolü'nde onaylananlar, açılır bölümlerde:
   Dönem Bilgisi, Ad Parçaları, Kolon Adları kuralları ve Kolon Kartları.
   Yalnız onaylanan bölüm görünür. Yer tutucular ekranda [sayı]. Açık /
   kapalı durumu yeniden çizimde korunur (OZ0124_ACIK). */
const OZ0124_ACIK = new Set();
function ozet0124Ciz(o, satirlar) {
    const kartli = satirlar.filter(s => s.kart && (s.kart.kart || s.kart.orijinal)).length;
    const yeniAdli = satirlar.filter(s => s.yeni_ad).length;
    if (!(o.donem || []).length && !(o.parcalar || []).length && !o.kolon_ad && !kartli) return null;
    const kok = elYap("div", "oz0124");
    const bas = elYap("div", "oz0124-bas", "Sözlük ve Kolon Adı Kontrolü sonuçları");
    bas.appendChild(bolmeBilgiSimgesi("01.2.4 adımlarında onaylananlar. Tablodaki açıklamalar ve yeni adlar "
        + "bunlarla güncel; AMP_VERISETI ve AMP_SOZLUK Değişken Listesi ve Tip Kontrolü onayında bu hâliyle "
        + "yazılır. Girdi veri setiniz ve sözlüğünüz değişmez.", "Sözlük ve Kolon Adı Kontrolü sonuçları"));
    kok.appendChild(bas);
    const bolum = (anahtar, baslik, ozet, icerik, bilgi) => {
        const d = document.createElement("details");
        d.className = "oz0124-bolum";
        d.open = OZ0124_ACIK.has(anahtar);
        d.addEventListener("toggle", () => { if (d.open) OZ0124_ACIK.add(anahtar); else OZ0124_ACIK.delete(anahtar); });
        const sm = document.createElement("summary");
        sm.appendChild(elYap("span", "oz0124-baslik", baslik));
        if (bilgi) {
            /* i'ye basmak bölümü açıp kapatmasın (summary'nin varsayılan işi). */
            const i_ = bolmeBilgiSimgesi(bilgi, baslik);
            i_.addEventListener("click", e => e.preventDefault());
            sm.appendChild(i_);
        }
        if (ozet) sm.appendChild(elYap("span", "oz0124-ozet", ozet));
        d.appendChild(sm);
        const ic = elYap("div", "oz0124-ic");
        icerik(ic);
        d.appendChild(ic);
        kok.appendChild(d);
    };
    const tablo = (basliklar, satirlar_, sinif) => {
        const t = elYap("table", "dg-tablo oz0124-tablo " + (sinif || ""));
        const th = document.createElement("thead"), hr = document.createElement("tr");
        basliklar.forEach(b => hr.appendChild(elYap("th", "", b)));
        th.appendChild(hr); t.appendChild(th);
        const tb = document.createElement("tbody");
        satirlar_.forEach(h => {
            const tr = document.createElement("tr");
            h.forEach(x => {
                const td = document.createElement("td");
                if (x instanceof Node) td.appendChild(x); else td.textContent = x;
                tr.appendChild(td);
            });
            tb.appendChild(tr);
        });
        t.appendChild(tb);
        const sar = elYap("div", "dg-tablo-sar");
        sar.appendChild(t);
        return sar;
    };
    /* Dönem Bilgisi */
    if ((o.donem || []).length) {
        bolum("donem", "Dönem Bilgisi", ftBinlik(o.donem.length) + " kalıp", ic => {
            ic.appendChild(elYap("div", "oz0124-not", "Kolon adlarındaki dönem kalıpları ve anlamları. Özel durumlar: "
                + "kendi anlamı olan değerler, gruptan ayrılan değerler ve adda bir parça geçince geçerli anlam."));
            ic.appendChild(tablo(["Kalıp", "Anlam", "Zaman Türü", "Özel Durumlar"], o.donem.map(d => {
                const ozel = elYap("div", "oz0124-liste");
                Object.entries(d.degerler || {}).forEach(([dg, an]) =>
                    ozel.appendChild(elYap("div", "", dg + ": " + an)));
                if ((d.ayrilan || []).length) ozel.appendChild(elYap("div", "", "Gruptan ayrılan: " + d.ayrilan.join(", ")));
                Object.entries(d.kosullu || {}).forEach(([p, an]) =>
                    ozel.appendChild(elYap("div", "", "Adda " + p + " geçerse: " + donemAnlamGoster(d.kalip, an))));
                if (!ozel.childNodes.length) ozel.textContent = "Yok";
                return [donemSayiGoster(d.kalip), donemAnlamGoster(d.kalip, d.anlam), d.tur || "", ozel];
            })));
        }, "Kolon adlarındaki sayı içeren zaman parçaları (3D, 30D, 3D_7D). Aynı biçimdekiler tek kalıpta "
            + "toplanır: 3D, 7D ve 30D, [sayı]D kalıbıdır. Kalıba bir kez anlam yazılır, sayı yerine [sayı] "
            + "konur («[sayı] gün»); her kolona kendi sayısıyla uygulanır (30D: 30 gün). Yönü ve kapsamı "
            + "(son 30 gün, 30 gün önce, sonraki 30 gün ...) her kolonda ayrıdır; kolon kartlarında "
            + "belirlenir.\n\n"
            + "Zaman türü: Pencere (veri bir aralıktaki bütün zamanlardan toplanır), Zaman Noktası, Zaman Birimi, "
            + "Zaman Ölçüsü. [sayı]D gibi sayı ve birimden oluşan kalıpta tür kolona göredir.\n\n"
            + "Özel durumlar: bir değerin kendi anlamı (360D: son 1 yıl), gruptan ayrılan değerler ve adda bir "
            + "parça geçince geçerli anlam (adda RATIO geçerse 3D_7D: son 3 gün ile son 7 gün).\n\n"
            + "Kolon kartının Zaman alanı, açıklamalardaki dönem kontrolü ve yeni adda yazılış (3D, L3D olur) "
            + "buradan gelir.");
    }
    /* Ad Parçaları */
    if ((o.parcalar || []).length) {
        bolum("parca", "Ad Parçaları", ftBinlik(o.parcalar.length) + " parça", ic => {
            ic.appendChild(elYap("div", "oz0124-not", "Kolon adlarındaki kısaltmaların onaylı anlamı ve türü; "
                + "kolon sayısı adında o parça geçen kolon sayısıdır."));
            const ara = document.createElement("input");
            ara.type = "text"; ara.className = "dg-giris oz0124-ara";
            ara.placeholder = "Parça ya da anlam ara"; ara.setAttribute("aria-label", "Parça ya da anlam ara");
            const yer = elYap("div", "");
            const ciz = () => {
                const q = ftSade(ara.value);
                const l = o.parcalar.filter(x => !q || ftSade(x.parca).indexOf(q) !== -1 || ftSade(x.anlam).indexOf(q) !== -1);
                yer.textContent = "";
                yer.appendChild(l.length ? tablo(["Parça", "Anlam", "Tür", "Kolon"],
                    l.map(x => [x.parca, x.anlam, x.tur, ftBinlik(x.kolon)]))
                    : elYap("div", "oz0124-not", "Aramayla eşleşen parça yok."));
            };
            ara.oninput = ciz;
            if (o.parcalar.length > 15) ic.appendChild(ara);
            ic.appendChild(yer);
            ciz();
        }, "Kolon adlarındaki dönem dışı kısaltmalar (TXN, GDN, CNT, RATIO). Her birinin onaylı bir anlamı "
            + "(TXN: işlem) ve türü var: Konu, Yön, Nitelik, Ölçü, İstatistik, Zaman, Karşılaştırma, Birim, Diğer.\n\n"
            + "Ör. TXN_GDN_3D_CNT: TXN işlem (Konu), GDN giden (Yön), CNT adet (Ölçü); 3D Dönem Bilgisi'nden "
            + "gelir (son 3 gün).\n\n"
            + "Kolon kartları, açıklama düzeltme ve yeni adlar (Ad Standardı sırası ve standart yazılış) bu "
            + "parçalardan kurulur.");
    }
    /* Kolon Adları kuralları */
    if (o.kolon_ad) {
        const k = o.kolon_ad;
        bolum("kolon_ad", "Kolon Adları", ftBinlik(k.degisen || 0) + " kolonun adı değişti", ic => {
            ic.appendChild(elYap("div", "oz0124-not", "Yeni adlar bu kurallarla kuruldu. Tabloda adı değişen kolonun "
                + "yeni adı, altında eski adı yazar."));
            if ((k.sira || []).length) ic.appendChild(elYap("div", "oz0124-satir",
                "Ad Standardı sırası: " + k.sira.map((y, i) => (i + 1) + ". " + y).join(" · ")));
            if ((k.yazilis || []).length) ic.appendChild(tablo(["Dönem Kalıbı", "Yeni Adda Yazılış"],
                k.yazilis.map(x => [donemSayiGoster(x.kalip), donemAdGoster(x.yazilis)])));
            if ((k.eklenen || []).length) ic.appendChild(tablo(["Ada Eklenen Bilgi", "Kısaltma", "Tür", "Kolon"],
                k.eklenen.map(x => [x.anlam, x.kisaltma, x.tur, ftBinlik(x.kolon)])));
        });
    }
    /* Kolon Kartları */
    if (kartli) {
        bolum("kart", "Kolon Kartları", ftBinlik(kartli) + " kolon", ic => {
            ic.appendChild(elYap("div", "oz0124-not", "Her kolonun adındaki parçalardan kurulan kartı (konu, yön, "
                + "zaman, ölçü ve diğerleri), düzeltmeden önceki açıklaması ve notunuz: yukarıdaki tabloda kolonun "
                + "satırına tıklayınca altta açılan detayda görünür."
                + (yeniAdli ? " Adı değişen " + ftBinlik(yeniAdli) + " kolonda detayda eski ad da yazar." : "")));
        });
    }
    return kok;
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
    ftCiplarCiz();
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

/* Etkin süzgeç çipleri: arama, tip ve kolon süzgeçleri; her biri tek
   tıkla kalkar, "Filtreleri Temizle" hepsini kaldırır (sıralama kalır). */
function ftCiplarCiz() {
    if (!FT.dom || !FT.dom.ciplar) return;
    const kok = FT.dom.kok;
    const ogeler = [];
    const ad = alan => {
        const i = FT_ALANLAR.findIndex(a => a.alan === alan);
        return ((FT.veri && FT.veri.kolonlar) || [])[i]
            || (FT_ALANLAR[i] || {}).baslik || alan;
    };
    if (FT.arama.trim()) ogeler.push({ etiket: "Arama: " + FT.arama.trim(), kaldir: () => {
        FT.arama = ""; const g = kok.querySelector('[data-ft-odak="ara"]'); if (g) g.value = "";
        ftBasaSar(); ftTazele(); } });
    if (FT.tip) ogeler.push({ etiket: "Tip: " + FT.tip, kaldir: () => {
        FT.tip = ""; const g = kok.querySelector(".ft-tip-suzgec"); if (g) g.value = "";
        ftBasaSar(); ftTazele(); } });
    Object.keys(FT.kolonSz).forEach(a => {
        if (!szAktif(FT.kolonSz[a])) return;
        ogeler.push({ etiket: ad(a) + ": " + szOzet(FT.kolonSz[a]), kaldir: () => {
            delete FT.kolonSz[a]; ftBasaSar(); ftTazele(); } });
    });
    szCiplarCiz(FT.dom.ciplar, ogeler, () => {
        FT.arama = ""; FT.tip = ""; FT.kolonSz = {};
        const g = kok.querySelector('[data-ft-odak="ara"]'); if (g) g.value = "";
        const t = kok.querySelector(".ft-tip-suzgec"); if (t) t.value = "";
        ftBasaSar(); ftTazele();
    });
}

/* Baslik seridinin son parcasi: sozlugun CALISMA KOPYASI oldugu
   etiketin kendisinde yaziyor (arka uc oyle gonderiyor). */
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
       icin mi?
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
       tablo HIC cizilmez: bos bir filtre takimi gosterilmez.
       DIKKAT: bu kontrol SUZME ONCESI satir sayisina bakar — kullanici
       filtreyle 0 satira dusurduyse takim kalmali, yoksa filtreyi geri
       alamaz. */
    if (!(t.satirlar || []).length) {
        FT.dom = null;
        FT.pencere = null;
        return;
    }
    if (!t.duzenlenebilir) { FT.topluHata = ""; FT.topluNot = ""; }

    /* SUZME CIZIMDEN ONCE: ilk ekran da suzulmus listeyi gosterir. */
    ftSuz();

    const kok = elYap("div", "iskele-kart ft-kart");

    /* TEK SATIR serit: "1.042 degisken \u00b7 2 surec disi \u00b7 <sozluk>"
       Kaynak etiketi hep gorunur: hangi sozlugun anlatildigi belli olsun.
        Sozlugun nereden geldigini kartlardaki "Köken"
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
        "Sohbetteki listeyi kaydettikten sonra indirebilirsiniz.",
        /* İki sayfa: Tümü + panelde arama/tip/sıralamadan sonra görünen. */
        () => ({ suzulmus: FT.suzulmus.map(s => s.feature) }));
    /* Panel listesi salt okunur bir görünüm: Excel her zaman açık
       (Veri Önizleme ile aynı). Sohbetteki karar listesinin Excel'i
       kaydetme kapısına bağlı kalır. */
    ftExcel.ac(true);
    /* Excel düğmesi ÜST ŞERİDİN YANINDA. */
    ust.appendChild(ftExcel.el);

    kok.appendChild(ftFiltreCiz());
    const ciplar = elYap("div", "sz-ciplar");
    kok.appendChild(ciplar);

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
    /* 01.2.4 SONUÇLARI: tablonun altında, onaylanan bölümler. */
    const ozet0124 = ozet0124Ciz(t.ozet_0124 || {}, t.satirlar || []);
    if (ozet0124) kok.appendChild(ozet0124);

    FT.dom = { kok, sayac, kaynak, baslik, toplu, not, hata, govde, yer, detay, ciplar };
    ftCiplarCiz();
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
          "zamansal": son N donem test olur. Bu set ZATEN OOT'dur.
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

/* Enum degerlerinin ekran adlari. YEDEK listedir: etiketler arka
   uctan geliyor (akis_durum.BOLME_SECENEK). Eski bir gövdede
   "secenekler" duz dizi olarak gelirse bu liste devreye giriyor.
   YABANCI TERIM YOK: ekranda kullaniciya gosterilen her sey Turkce. */
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
   kullanici icin var. */
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
/* val_var ve katmanla ANAHTAR tasiyor ("kullan"/"kullanma",
   "koru"/"koruma"). Dikkat: "kullanma" JS'te DOGRU bir deger - dogrudan
   !!a.val_var yazmak "Kullanma" secildiginde de aciktir demek olurdu.
   Bu yuzden her okuma bu ikisinden geciyor. */
function bfValVar(v) { return v === true || v === "kullan"; }
function bfKatmanla(v) { return v === true || v === "koru"; }

function bfAlanlar(f) {
    const al = (f && f.alanlar) || {};
    const d = (k, y) => (al[k] && al[k].deger !== undefined && al[k].deger !== null)
        ? al[k].deger : y;
    /* val_var "kullan"/"kullanma" anahtari; eski govdede bool
       gelebilir. Taslakta TEK BICIM: anahtar. */
    const valHam = d("val_var", "kullanma");
    const valVar = (valHam === true || valHam === "kullan");
    const cv = d("cv", "kfold");
    /* ORAN TASLAKTA HEP KESİR. */
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
       KURMUYOR. */
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
       Tahmini yuzde yazmak olmayan bir hesabi varmis gibi gostermek olur. */
    if (BF.alan.test_tanim === "hazir")
        return "Setler veri setindeki bölme kolonundan okunacak.";
    const p = bfPaylar();

    /* ZAMANSAL BOLMEDE EGITIM YUZDESI YAZILMAZ. Test donem bazli
       ayrildigi icin orani onceden bilinmiyor. */
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
       hiç yokmuş" demek olur, sebebi yazili pasif bir satir ise "neden
       seçemiyorum" sorusunu ekranda cevapliyor. */
    const s = ftSecim("bf-" + ad,
                      secenekler.map(o => ({ deger: o.anahtar, etiket: o.etiket })),
                      deger, degisti);
    s.setAttribute("data-alan", ad);
    Array.prototype.forEach.call(s.options, (op, i) => {
        const o = secenekler[i];
        if (!o) return;
        if (o.kilitli) op.disabled = true;
        if (o.aciklama) op.title = duzMetin(o.aciklama);
    });
    s.disabled = pasif;
    if (pasif) s.onchange = null;
    return s;
}

/* Bir form alani: etiket + kontrol + (varsa) aciklama + (varsa) not.

   ACIKLAMA SATIRI Terimin Turkcesi etikette, ne demek oldugu
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
       5 dönem"). Aynı bilgiyi bir de altta tekrarlamak gürültü olur. Bölme hesaplandıktan sonra
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
   seçimi anlatır. Kısıtlar dahilinde seçim yapabilmek için önce kısıt
   görünmeli. */
function bfKisitCiz(kok, kisitlar) {
    const liste = kisitlar || (BF.veri && BF.veri.kisitlar) || [];
    if (!liste.length) return;
    const kutu = elYap("div", "bf-kisitlar");
    kutu.appendChild(elYap("div", "bf-kisit-baslik", "Veriden Gelen Kısıtlar"));
    liste.forEach(k => kutu.appendChild(
        elYap("div", "bf-kisit", (k && k.metin) || String(k))));
    kok.appendChild(kutu);
}

/* Not: "Özel Ayarlar" formu iki kartın ORTAK satır listesinden
   çiziliyor (bkz. bolmeSatirOzelCiz). */

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
       tarafin ayri oneri hesaplamasi ve zamanla ayrismasi demek olur. */
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
                   HAZIRLIK sekmesi ozet gosteriyor, form degil
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
               yazılmaz. */
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
           demek olur. */
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
       geçerli olduğunu bilememesi demek olur.

       Gövde yine geliyor: üst şeritteki set seçici "Doğrulama"
       düğmesini göstereceğini buradan okuyor (setBolmeAlanlari). */
    void f;
}

/* ==================== Set seçici ==================== */
/* Analiz panelinin tepesindeki Tümü / Eğitim / Doğrulama / Test.

   AYRI BIR "OOT" DUGMESI YOK: bolme en fazla uc set uretir ve
   zamansal testte test seti ZATEN OOT'dur (bkz. akis_durum.bolme_ayarlari).

   Secim YALNIZCA on yuzde tutulur; /analiz govdesine parametre GECMEZ
   (bkz. SOZLESME2 §7). */
/* ETIKETLER TURKCE: ekranda yabancı terim yok. */
const SET_SECENEKLERI = [
    { anahtar: "tumu",  etiket: "Tümü" },
    { anahtar: "train", etiket: "Train (MS)" },
    { anahtar: "val",   etiket: "Test (OOS)",  alan: "val_var" },
    { anahtar: "test",  etiket: "Validasyon (OOT)" }
];

/* SET ADLARI:
   egitim = Train (MS), val = Test (OOS), test = Validasyon (OOT) - rastgele
   bolmede de (arka uc: akis_durum.set_basligi). */
const TEST_OOS2 = "Validasyon (OOT)";

/* Secicinin GORUNDUGU sekmeler. VERİ & SÖZLÜK ve HAZIRLIK her zaman tum
   satirlarda calisiyor.
   VALİDASYON da listede yok: final metrikleri test setinde, sonda bir
   kez olculur; secilecek bir sey yok. */
/* DEĞİŞKEN ANALİZİ'nde secici DAĞILIM bolumune uygulanir; SFA her zaman
   egitim satirlarinda (bolum basliginin altinda yazar). */
const SET_SECICI_SEKMELER = ["degisken"];
const SET_PASIF_SEKMELER = [];
const SFA_SET_NOTU = "SFA yalnızca eğitim satırlarında ölçülür";

let AKTIF_SET = "tumu";

/* val_var bilgisi HAZIRLIK panelindeki bolme formundan okunur (tek kaynak). */
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


/* ==================== DEĞİŞKENLER SEÇİM ŞERİDİ ====================
   Değişkenler sekmesinin solunda HEP KAPALI ince şerit: üç dikey düğme
   (Veri ve Sözlük · Dağılım ve SFA · Değişken Kontrolleri). Açılan bir
   panel yok; basılan görünüm sağda çizilir. Seçim tarayıcıda hatırlanır.
   Şerit yalnız Değişkenler sekmesinde görünür (analizCiz başında). */
const DG_ALT_ANAHTAR = "amp_dg_alt";
const DG_ALTLAR = ["veri", "dagilim", "kontrol"];
const DG = { alt: "veri" };
try {
    const a = localStorage.getItem(DG_ALT_ANAHTAR);
    if (DG_ALTLAR.indexOf(a) !== -1) DG.alt = a;
} catch (e) { /* depolama kapalı */ }
const dgPanelEl = document.getElementById("dg-panel");

function dgDagilimAcik() { return aktifAnalizSekme === "degisken" && DG.alt === "dagilim"; }
function dgPanelGoster(goster) {
    if (!dgPanelEl) return;
    dgPanelEl.hidden = !goster;
    dgPanelEl.querySelectorAll("[data-alt]").forEach(b => {
        const aktif = b.dataset.alt === DG.alt;
        b.classList.toggle("aktif", aktif);
        if (aktif) b.setAttribute("aria-current", "true"); else b.removeAttribute("aria-current");
    });
}
/* Görünüm seç: Değişkenler sekmesi açık değilse açılır. */
function dgAc(alt) {
    if (DG_ALTLAR.indexOf(alt) === -1) return;
    DG.alt = alt;
    try { localStorage.setItem(DG_ALT_ANAHTAR, alt); } catch (e) { /* yok */ }
    if (aktifAnalizSekme === "degisken" && !kabukEl.classList.contains("analiz-dar")) {
        analizCiz("degisken");
        analizGovde.scrollTop = 0;
    } else {
        analizSekmeAc("degisken");
    }
}
if (dgPanelEl) dgPanelEl.querySelectorAll("[data-alt]").forEach(b => {
    b.onclick = () => dgAc(b.dataset.alt);
});


/* ==================== YENİ GÜNCELLEME ROZETİ (Model Değişkenleri) ====
   Model Değişkenleri'nin beş bölümünden her biri bir birimdir. Birimin
   içeriği her sunucu yanıtında bir imzaya indirgenir; imza, kullanıcının
   o bölümü en son GÖRDÜĞÜ imzadan farklıysa bölüm "yeni" sayılır. Sol
   bardaki Model Değişkenleri satırının (Model Platformu kapalıyken
   başlığının) zemini sayı yerine yavaşça kırmızılaşıp açılır; görünüm
   şeridindeki düğmelerde o görünümün sayısı durur.
   GÖRÜLDÜ: bölümün başlığı ekranda 0,1 sn göründüğünde; sayı her bölümde
   bir azalır, hepsi görülünce rozet kalkar.
   İmzalar çalışma başına bu tarayıcıda saklanır (yalnız kolaylık).
   Çalışma bu tarayıcıda ilk kez açıldığında o anki içerik görülmüş
   sayılır; yalnız ondan sonraki değişiklikler rozete girer. */
const GUNCELLEME_BIRIMLERI = [
    { ad: "veri_seti", alt: "veri" },
    { ad: "sozluk", alt: "veri" },
    { ad: "dagilim", alt: "dagilim" },
    { ad: "sfa", alt: "dagilim" },
    { ad: "eksik", alt: "kontrol" }
];
const GORULEN_ONEK = "amp_gorulen_";
const GUNCELLEME = { imza: {}, gorulen: null, calisma: null, izleyici: null };

function metinOzeti(x) {
    const m = JSON.stringify(x === undefined ? null : x);
    let h = 5381;
    for (let i = 0; i < m.length; i++) h = ((h << 5) + h + m.charCodeAt(i)) | 0;
    return (h >>> 0).toString(36) + ":" + m.length;
}

/* Birimin içeriği yoksa imzası da yok (bölüm henüz dolmadı). */
function birimImzalari(v) {
    const hazir = p => p && !p.hata && p.durum === "hazir" && (p.kartlar || []).length;
    const o = (v && v.ozet) || {};
    const imza = {};
    if (hazir(o)) {
        imza.veri_seti = metinOzeti((o.kartlar || []).filter(k => k.baslik === "Veri Seti"));
        imza.dagilim = metinOzeti([imza.veri_seti, hazir(v.bolme) ? v.bolme.kartlar : null]);
    }
    const ft = o.feature_tablo;
    if (ft && (ft.satirlar || []).length) imza.sozluk = metinOzeti(ft.satirlar);
    if (hazir(v && v.sfa)) imza.sfa = metinOzeti(v.sfa.kartlar);
    if (hazir(v && v.eksik)) imza.eksik = metinOzeti(v.eksik.kartlar);
    return imza;
}

function gorulenKaydet() {
    try { localStorage.setItem(GORULEN_ONEK + GUNCELLEME.calisma, JSON.stringify(GUNCELLEME.gorulen)); }
    catch (e) { /* depolama kapalı: yalnız bu oturum */ }
}

function guncellemeleriTazele(veri) {
    const imza = birimImzalari(veri);
    if (GUNCELLEME.calisma !== OTURUM_ID) {
        GUNCELLEME.calisma = OTURUM_ID;
        let kayit = null;
        try { kayit = JSON.parse(localStorage.getItem(GORULEN_ONEK + OTURUM_ID) || "null"); }
        catch (e) { kayit = null; }
        GUNCELLEME.gorulen = kayit && typeof kayit === "object" ? kayit : Object.assign({}, imza);
        gorulenKaydet();
    }
    GUNCELLEME.imza = imza;
    rozetleriCiz();
}

function yeniBirimler() {
    return GUNCELLEME_BIRIMLERI.filter(b => GUNCELLEME.imza[b.ad]
        && GUNCELLEME.gorulen && GUNCELLEME.imza[b.ad] !== GUNCELLEME.gorulen[b.ad]);
}

function rozetYaz(el, sayi, etiket) {
    if (!el) return;
    /* SOL BAR: sayı yok; satırın zemini yavaşça kırmızılaşıp açılır
       (style.css .guncel-nabiz). Bölümler görülünce kalkar. */
    if (el.closest("#sol-bar")) {
        let n = el.querySelector(":scope > .guncel-nabiz");
        el.classList.toggle("guncel-var", !!sayi);
        if (!sayi) {
            if (n) n.remove();
            el.removeAttribute("data-guncel");
            return;
        }
        if (!n) {
            n = elYap("span", "guncel-nabiz");
            n.setAttribute("aria-hidden", "true");
            el.insertBefore(n, el.firstChild);
        }
        el.dataset.guncel = "Görülmemiş güncelleme var (" + sayi + " " + etiket + ")";
        el.setAttribute("aria-description", el.dataset.guncel);
        return;
    }
    let r = el.querySelector(":scope > .guncelleme-rozet");
    if (!sayi) { if (r) r.remove(); return; }
    if (!r) {
        r = elYap("span", "guncelleme-rozet");
        el.insertBefore(r, el.querySelector(":scope > svg.ok"));    // okun solunda
    }
    r.textContent = sayi > 9 ? "9+" : String(sayi);
    r.title = sayi + " " + etiket;
    r.setAttribute("aria-label", sayi + " " + etiket);
}

function rozetleriCiz() {
    const yeni = yeniBirimler();
    rozetYaz(document.querySelector('#sol-bar .ust-sekme[data-tab="degisken"]'),
             yeni.length, "bölümde görülmemiş güncelleme");
    /* Model Platformu kapalıyken sayı başlığında görünür (style.css). */
    rozetYaz(document.querySelector("#sol-bar .ust-kume-ad"),
             yeni.length, "bölümde görülmemiş güncelleme (Model Değişkenleri)");
    if (dgPanelEl) dgPanelEl.querySelectorAll("[data-alt]").forEach(b => {
        rozetYaz(b, yeni.filter(x => x.alt === b.dataset.alt).length,
                 "bölümde görülmemiş güncelleme");
    });
}

/* Bölüm başlığı çizildikçe izlenir; ekranda 0,1 sn kalınca görüldü. */
function guncellemeIzle(birim, el) {
    if (!el || typeof IntersectionObserver === "undefined") return;
    if (!GUNCELLEME.izleyici) {
        const sayac = new Map();
        GUNCELLEME.izleyici = new IntersectionObserver(girisler => girisler.forEach(g => {
            const ad = g.target.dataset.birim;
            clearTimeout(sayac.get(g.target));
            if (!g.isIntersecting) return;
            sayac.set(g.target, setTimeout(() => {
                if (!g.target.isConnected || !GUNCELLEME.gorulen) return;
                if (!GUNCELLEME.imza[ad] || GUNCELLEME.gorulen[ad] === GUNCELLEME.imza[ad]) return;
                GUNCELLEME.gorulen[ad] = GUNCELLEME.imza[ad];
                gorulenKaydet();
                rozetleriCiz();
            }, 100));
        }), { threshold: 0.9 });
    }
    el.dataset.birim = birim;
    GUNCELLEME.izleyici.observe(el);
}

function analizCiz(tab) {
    /* Panel bastan ciziliyor; feature tablosunda yaziyor olabilir.
       Odak ve imlec yeri ayni kontrole geri veriliyor. */
    const odak = ftOdakAnahtari();
    aktifAnalizSekme = tab;
    /* Eski bölüm başlıkları silinecek; izleme yeni çizimle yeniden kurulur. */
    if (GUNCELLEME.izleyici) GUNCELLEME.izleyici.disconnect();
    analizGovde.innerHTML = "";
    /* Seçim şeridi YALNIZ Değişkenler'de: her çizimin başında (erken
       dönen Model Göstergeleri dahil) ayarlanır. */
    dgPanelGoster(tab === "degisken");
    /* MODEL GÖSTERGELERİ ("ozet"): ÇALIŞMA DÜZEYİ, her bilgi bir sayı ya da özet.
       Veri seti ve sözlük kartları, değişken sayıları (üretim / eleme),
       bölme, validasyon ve model sonucu. Değişken listesi burada değil. */
    if (tab === "ozet") {
        const o = ANALIZ_VERI.ozet;
        panelBolumBasligi("Veri Seti ve Sözlük");
        panelCiz(o ? Object.assign({}, o, { feature_tablo: null }) : o);
        panelBolumBasligi("Değişken Sayıları");
        sonucCiz(["ÜRETİM", "ELEME"]);
        panelBolumBasligi("Bölme");
        panelCiz(ANALIZ_VERI.bolme);
        panelBolumBasligi("Validasyon");
        validasyonCiz(ANALIZ_VERI.validasyon);
        panelBolumBasligi("Model Sonucu");
        sonucCiz(["MODEL"]);
        ftOdakGeriVer(odak);
        return;
    }
    /* VERİ VE SÖZLÜK: modelleme tablosunun O ANKİ hâli (teyitten sonra
       AMP_VERISETI) ve sözlük listesi (AMP_SOZLUK). Başlıklar tablonun
       adını taşır; her sunucu yanıtında yeniden okunur (adımlar
       ilerledikçe son hâl). */
    if (tab === "degisken" && DG.alt === "veri") {
        const o = ANALIZ_VERI.ozet;
        const veriBaslik = elYap("div", "panel-bolum-baslik",
            "Veri Seti" + (ONIZLEME.veri && ONIZLEME.veri.kaynak_ad
                           ? " · " + ONIZLEME.veri.kaynak_ad : ""));
        analizGovde.appendChild(veriBaslik);
        guncellemeIzle("veri_seti", veriBaslik);
        const onizKap = elYap("div", "iskele-kart vo-kart");
        analizGovde.appendChild(onizKap);
        const sk = o && o.feature_tablo && o.feature_tablo.sozluk_kaynak;
        panelBolumBasligi("Sözlük" + (sk ? " · " + sk : ""), "sozluk");
        if (o && o.feature_tablo) featureTabloCiz(ftSaltOku(o.feature_tablo));
        else analizGovde.appendChild(elYap("div", "set-not",
            "Sözlük listesi veri seti seçildikten sonra burada görünür."));
        onizlemeCiz(onizKap, veriBaslik);
        ftOdakGeriVer(odak);
        return;
    }
    /* DAĞILIM VE SFA: değişken düzeyinde dağılım ve tek değişken analizi. */
    if (tab === "degisken" && DG.alt === "dagilim") {
        /* Kume secici yalnizca Dağılım bolumune uygulanir: basligin altinda. */
        panelBolumBasligi("Dağılım", "dagilim");
        setSeciciCiz(tab);
        dagilimCiz();
        panelBolumBasligi("Tek Değişken Analizi (SFA)", "sfa");
        analizGovde.appendChild(elYap("div", "set-not", SFA_SET_NOTU));
        panelCiz(ANALIZ_VERI.sfa);
        if (ANALIZ_VERI.sfa && ANALIZ_VERI.sfa.aralik) aralikCiz();
        ftOdakGeriVer(odak);
        return;
    }
    /* DEĞİŞKEN KONTROLLERİ: eksik değer. */
    if (tab === "degisken") {
        panelBolumBasligi("Eksik Değer", "eksik");
        panelCiz(ANALIZ_VERI.eksik);
        ftOdakGeriVer(odak);
        return;
    }
    setSeciciCiz(tab);
    panelCiz(ANALIZ_VERI[tab]);
    ftOdakGeriVer(odak);
}

/* ==================== SFA ekranı (Değişken Analizi sekmesi) ====================
   SFA eleme yeri değil; her değişken için ölçütler,
   özellik dağılımı + hedef (1) oranı grafiği (çift eksen) ve yapay zekânın verdiği, kullanıcının değiştirebildiği karar
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

/* Eksen etiketini kelime aralarından satırlara böler (kelime kesilmez,
   kısaltma yok): her satır yaklaşık `uzunluk` karakter, en çok iki satır;
   ikinci satır sığmasa da kalan kelimeleri taşır. */
function eksenSatirlari(metin, uzunluk) {
    const kelimeler = String(metin || "").split(/\s+/).filter(Boolean);
    if (!kelimeler.length) return [""];
    const satirlar = [kelimeler[0]];
    kelimeler.slice(1).forEach(k => {
        const son = satirlar[satirlar.length - 1];
        if (satirlar.length < 2 && (son + " " + k).length > uzunluk) satirlar.push(k);
        else satirlar[satirlar.length - 1] = son + " " + k;
    });
    return satirlar;
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
        kap.appendChild(elYap("div", "dag-not", "SFA sonuçları yükleniyor"));
        sfaGetir("sfa_degiskenler").then(d => {
            if (istek !== ARALIK.istek || !dgDagilimAcik()) return;
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
    ara.placeholder = "Değişken ara";
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
        td.appendChild(elYap("div", "dag-not", "Değişken yükleniyor"));
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

    /* ÖLÇÜTLER: dar panele sığsın diye iki sütunlu etiket / değer ızgarası. */
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

/* Çift eksenli tek grafik:
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

    const W = 420, H = 210, SOL = 36, SAG = 40, UST = 8, ALT = 46;   // iki satirlik eksen etiketi
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
        /* KISALTMA YOK: uzun etiket kelime aralarından alt satıra geçer
           (en çok iki satır; kelime bölünmez). */
        const t = el("text", { x: X(i), y: UST + gh + 12, "text-anchor": "middle" }, "dag-eksen-yazi", "");
        eksenSatirlari(e, 10).forEach((parca, k) => {
            const ts = document.createElementNS("http://www.w3.org/2000/svg", "tspan");
            ts.setAttribute("x", X(i));
            if (k) ts.setAttribute("dy", "1.1em");
            ts.textContent = parca;
            t.appendChild(ts);
        });
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
    eksenYazisiniSabitle(svg);
    kap.appendChild(ipucu);
    return kap;
}

/* KARAR FORMU. Kaydedilen karar "Sizin Kararınız" olur; yapay zekâ o
   değişkeni bundan sonra değiştirmez. */
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
    /* TİP KARARI YALNIZCA BURADA. Seçenekler verinin tam
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
            ? "SFA yeni tiple hesaplanıyor" : "Kaydediliyor";
        fetch(getWebAppBackendUrl("sfa_karar"), {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ oturum_id: OTURUM_ID, kolon: v.ad || ozet.ad, karar: karar })
        }).then(r => r.json()).then(d => {
            kaydet.disabled = false;
            if (!d || !d.tamam) { metinYaz(durum, (d && d.hata) || "Kaydedilemedi."); return; }
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
function panelBolumBasligi(metin, birim) {
    const el = elYap("div", "panel-bolum-baslik", metin);
    analizGovde.appendChild(el);
    if (birim) guncellemeIzle(birim, el);
    return el;
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

/* Tanımsız Kolonlar satırının tekrar oranı hücresi: tekrar eden satırın
   bütün satırlara oranı; adet ipucunda. Sıfır olmayan çok küçük oran
   "%0,0" gibi görünmesin diye ilk anlamlı basamağa kadar yazılır. */
function tanimsizTekrarHucresi(sat) {
    const td = elYap("td", "dg-sayi-hucre tk-sag");
    const n = Number(sat.tekrar), r = Number(sat.tekrar_oran);
    if (sat.tekrar === null || sat.tekrar === undefined || !isFinite(n)) return td;
    if (sat.tekrar_oran === null || sat.tekrar_oran === undefined || !isFinite(r)) {
        metinYaz(td, ftBinlik(n) + " satır");
        return td;
    }
    let yazi = ftOran(r);
    if (n > 0 && r < 0.0005) {
        const b = Math.min(6, Math.max(2, 1 - Math.floor(Math.log10(r * 100))));
        yazi = "%" + (r * 100).toFixed(b).replace(".", ",");
    }
    metinYaz(td, yazi);
    td.title = n > 0 ? ftBinlik(n) + " satırın değeri kendinden önceki bir satırla aynı"
                     : "Her satırın değeri farklı";
    return td;
}

/* Profil değerinin yazısı; saati gece yarısı olan tarih yalnız gün
   olarak yazılır (tarih olmayan değer aynen). */
function tarihGoster(v) {
    return degerGoster(String(v).replace(/^(\d{4}-\d{2}-\d{2})[ T]00:00:00$/, "$1"));
}

/* Tanımsız Kolonlar satırının değer hücresi: en sık 10 değer, her biri
   adediyle. Sayısal değer yerel biçimle yazılır. Kişisel veri taşıyan
   kolonda değer gösterilmez. Uzun değer kısaltılmaz, satıra sarar. */
function tanimsizDegerHucresi(sat) {
    const td = elYap("td", "dg-deger-hucre");
    if (sat.gizli) {
        td.appendChild(elYap("span", "dg-deger-yok", "Kişisel veri olduğu için değerler gösterilemez."));
        return td;
    }
    const liste = sat.degerler || [];
    if (!liste.length) {
        td.appendChild(elYap("span", "dg-deger-yok", BOS_SIMGE));
        return td;
    }
    liste.forEach(([deger, adet]) => {
        /* "değer (adet)": adet parantez içinde ve soluk; değerle karışmaz. */
        const c = elYap("span", "dg-deger");
        const yazi = sat.sayisal && typeof deger === "number" ? dagSayi(deger) : tarihGoster(deger);
        c.appendChild(elYap("span", "dg-deger-ad", yazi));
        c.appendChild(elYap("span", "dg-deger-adet", "(" + ftBinlik(adet) + ")"));
        c.title = String(deger) + ": " + ftBinlik(adet) + " satır";
        td.appendChild(c);
    });
    return td;
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
    const hala = () => istek === DAGILIM.istek && dgDagilimAcik();

    if (!DAGILIM.kolonlar) {
        kap.appendChild(elYap("div", "dag-not", "Değişken listesi yükleniyor"));
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
                        placeholder: "Değişken ara" });
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

    govde.appendChild(elYap("div", "dag-not", "Hesaplanıyor (tüm satırlar)"));
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

/* GRAFİK EKSEN YAZILARI: grafikler sabit bir çizim alanında (viewBox)
   çizilip kabın enine göre büyür ya da küçülür; eksen yazıları bununla
   birlikte büyümesin diye boyları grafiğin o anki büyütme oranına
   bölünür: ekranda her genişlikte EKSEN_YAZI_PX. Grafiğin eni
   değişince (panel genişleyince, pencere boyu değişince) yeniden
   hesaplanır. */
const EKSEN_YAZI_PX = 10.8;      /* 12 px x --ekran-kat (.9) */
const EKSEN_GOZCU = window.ResizeObserver ? new ResizeObserver(girdiler => {
    girdiler.forEach(g => eksenYazisiOlcekle(g.target));
}) : null;
function eksenYazisiOlcekle(svg) {
    const vb = svg.viewBox && svg.viewBox.baseVal;
    const en = svg.getBoundingClientRect().width;      // ekran pikseli
    if (!vb || !vb.width || !en) return;
    svg.style.setProperty("--eksen-yazi", (EKSEN_YAZI_PX * vb.width / en).toFixed(2) + "px");
}
function eksenYazisiniSabitle(svg) {
    if (EKSEN_GOZCU) EKSEN_GOZCU.observe(svg);
    requestAnimationFrame(() => eksenYazisiOlcekle(svg));
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
    eksenYazisiniSabitle(svg);
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

/* ==================== VERİ SETİ ÖNİZLEMESİ (Veri ve Sözlük sekmesi) ====
   Veri setinin BÜTÜN kolonları, ilk 10 satır; dönem kolonu seçildiyse her
   dönemin ilk 10 satırı (dönem başlıklarıyla, zaman sırasında). Görünüş
   Değişken Listesi ile aynı: üst şerit (sayaç · kaynak · Excel), arama,
   tip / dönem süzgeci ve sıralama, başlığı yapışkan tablo. Tablonun en
   yüksekliği listenin kaydırma penceresi kadar; az satırda kendi boyunda
   kalır (altta boşluk bırakmaz). Veri tek kez istenir; analiz verisi
   yenilenince sıfırlanır. Arama/süzme/sıralama yalnız ekranı daraltır,
   veriye dokunmaz. */
const ONIZLEME = { veri: null, istek: 0 };
function onizlemeSifirla() { ONIZLEME.veri = null; ONIZLEME.istek++; }

/* Süzgeç durumu çizimler arasında korunur (FT ile aynı mantık). */
const VO = { arama: "", tip: "", donem: "", kolSira: "", satirKol: null, yon: 1,
             kolonSz: {} };      // kolon adı -> Excel tarzı satır süzgeci
const VO_BOS_DONEM = "__bos__";
const VO_KOL_SIRALAMA = [
    { deger: "",  etiket: "Sırala: tablo sırası" },
    { deger: "a", etiket: "Kolon A→Z" },
    { deger: "z", etiket: "Kolon Z→A" }
];

/* Sözlük tanımı ve tip: Değişken Listesi'nin satırlarından (aynı kaynak). */
function voSozlukHaritasi() {
    const h = new Map();
    ((FT.veri && FT.veri.satirlar) || []).forEach(s => h.set(String(s.feature), s));
    return h;
}

/* Sayı gibi okunuyorsa sayı olarak, değilse Türkçe alfabeyle karşılaştır;
   boş değer her iki yönde de sonda. */
function voKarsilastir(x, y, yon) {
    const xb = x === null || x === undefined || x === "";
    const yb = y === null || y === undefined || y === "";
    if (xb && yb) return 0;
    if (xb) return 1;
    if (yb) return -1;
    const nx = Number(x), ny = Number(y);
    if (isFinite(nx) && isFinite(ny)) return (nx - ny) * yon;
    return String(x).localeCompare(String(y), "tr") * yon;
}

/* Görünen kolonlar (indis) ve satır grupları ({etiket, g, satirlar: [indis]}). */
function voSuz(d) {
    const kol = d.kolonlar || [];
    const harita = voSozlukHaritasi();
    const aranan = ftSade(VO.arama).trim();
    const donemIdx = d.donem ? kol.indexOf(d.donem) : -1;
    let kolIdx = [];
    kol.forEach((k, i) => {
        /* Dönem kolonu hep görünür: süzülen kolonların hangi döneme ait
           olduğu satırda okunabilsin. */
        if (i === donemIdx) { kolIdx.push(i); return; }
        const s = harita.get(k);
        if (aranan && ftSade(k).indexOf(aranan) === -1
            && ftSade(s && s.tanim).indexOf(aranan) === -1) return;
        if (VO.tip && String((s && s.tip) || "").trim() !== VO.tip) return;
        kolIdx.push(i);
    });
    if (VO.kolSira) {
        const yon = VO.kolSira === "z" ? -1 : 1;
        kolIdx.sort((a, b) => {
            if (a === donemIdx) return -1;
            if (b === donemIdx) return 1;
            return kol[a].localeCompare(kol[b], "tr") * yon;
        });
    }
    const satirlar = d.satirlar || [];
    const uyar = voSatirSuzgeci(d, null);
    const satirSuzulu = voSatirSuzuluMu(d);
    const sirala = idx => {
        const k = VO.satirKol === null ? -1 : kol.indexOf(VO.satirKol);
        if (k === -1) return idx;
        return idx.slice().sort((a, b) =>
            voKarsilastir((satirlar[a] || [])[k], (satirlar[b] || [])[k], VO.yon) || a - b);
    };
    const gruplar = [];
    if (d.donem && (d.gruplar || []).length) {
        let bas = 0;
        d.gruplar.forEach(g => {
            const idx = [];
            for (let n = 0; n < g.gosterilen; n++) idx.push(bas + n);
            bas += g.gosterilen;
            const anahtar = g.donem === null ? VO_BOS_DONEM : String(g.donem);
            if (VO.donem && VO.donem !== anahtar) return;
            const kalan = idx.filter(uyar);
            /* Satır süzgeci açıkken hiç satırı kalmayan dönem gizlenir. */
            if (satirSuzulu && !kalan.length) return;
            gruplar.push({ g: g, satirlar: sirala(kalan) });
        });
    } else {
        gruplar.push({ g: null, satirlar: sirala(satirlar.map((_, i) => i).filter(uyar)) });
    }
    return { kolIdx, gruplar, satirSuzulu };
}

/* Kolon süzgeçlerinden satır sınaması (haricKolon atlanır). */
function voSatirSuzgeci(d, haricKolon) {
    const kol = d.kolonlar || [], satirlar = d.satirlar || [];
    const liste = Object.keys(VO.kolonSz)
        .filter(k => k !== haricKolon && szAktif(VO.kolonSz[k]) && kol.indexOf(k) !== -1)
        .map(k => [kol.indexOf(k), VO.kolonSz[k]]);
    return ri => {
        const r = satirlar[ri] || [];
        for (const [i, sz] of liste) if (!szUyar(r[i] === undefined ? null : r[i], sz)) return false;
        return true;
    };
}
function voSatirSuzuluMu(d) {
    const kol = d.kolonlar || [];
    return Object.keys(VO.kolonSz).some(k => szAktif(VO.kolonSz[k]) && kol.indexOf(k) !== -1);
}
/* Süzgeç menüsünün değer listesi: seçili dönem(ler)de, DİĞER kolon
   süzgeçlerinden geçen satırların bu kolondaki değerleri. */
function voAdayDegerler(d, k) {
    const kol = d.kolonlar || [], satirlar = d.satirlar || [];
    const ki = kol.indexOf(k);
    const uyar = voSatirSuzgeci(d, k);
    const sonuc = [];
    const ekle = ri => { if (uyar(ri)) { const v = (satirlar[ri] || [])[ki]; sonuc.push(v === undefined ? null : v); } };
    if (d.donem && (d.gruplar || []).length) {
        let bas = 0;
        d.gruplar.forEach(g => {
            const anahtar = g.donem === null ? VO_BOS_DONEM : String(g.donem);
            if (!VO.donem || VO.donem === anahtar)
                for (let n = 0; n < g.gosterilen; n++) ekle(bas + n);
            bas += g.gosterilen;
        });
    } else {
        satirlar.forEach((_, ri) => ekle(ri));
    }
    return sonuc;
}

function onizlemeCiz(kap, baslikEl) {
    const ciz = d => {
        if (baslikEl && d && d.kaynak_ad)
            baslikEl.textContent = "Veri Seti · " + d.kaynak_ad;
        kap.textContent = "";
        if (!d || d.hata || d.tamam === false) {
            kap.appendChild(elYap("div", "dag-not dag-hata",
                tireSade((d && (d.hata || d.metin)) || "Önizleme okunamadı.")));
            return;
        }
        const kol = d.kolonlar || [];
        if (!kol.length) {
            kap.appendChild(elYap("div", "dag-not", tireSade(d.not || "Veri seti seçildikten sonra dolar.")));
            return;
        }
        const satirlar = d.satirlar || [];
        /* Önceki veride olmayan dönem seçimi / sıralama kolonu düşer. */
        const donemler = (d.gruplar || []).map(g => g.donem === null ? VO_BOS_DONEM : String(g.donem));
        if (!d.donem || donemler.indexOf(VO.donem) === -1) VO.donem = "";
        if (VO.satirKol !== null && kol.indexOf(VO.satirKol) === -1) VO.satirKol = null;
        Object.keys(VO.kolonSz).forEach(k => { if (kol.indexOf(k) === -1) delete VO.kolonSz[k]; });
        /* Sayısal kolon: sağa yaslı, süzgeçte sayı koşulları. Bir kez. */
        if (!d._sayisal) d._sayisal = kol.map((_, i) => szSayisalMi(satirlar.map(r => r[i])));
        let suz = voSuz(d);

        /* ---- Üst şerit: sayaç · kaynak · Excel ---- */
        const ust = elYap("div", "ft-ust");
        const sayac = elYap("span", "ft-sayac");
        const kaynak = elYap("span", "ft-kaynak");
        ust.appendChild(sayac);
        ust.appendChild(elYap("span", "ft-ayrac", "·"));
        ust.appendChild(kaynak);
        const excel = excelSeridiYap("onizleme", "Excel İndir", "",
            () => ({
                imza: d.imza,
                kolonlar: suz.kolIdx.map(i => kol[i]),
                satirlar: [].concat.apply([], suz.gruplar.map(gr => gr.satirlar))
            }));
        excel.ac(!!d.imza);
        ust.appendChild(excel.el);
        kap.appendChild(ust);

        /* ---- Arama + tip / dönem süzgeci + kolon sıralaması ---- */
        const filtre = elYap("div", "ft-filtreler");
        const ara = document.createElement("input");
        ara.type = "search";
        ara.className = "ft-ara";
        ara.placeholder = "Kolon adı veya sözlük tanımında ara";
        ara.setAttribute("aria-label", "Kolon adı veya sözlük tanımında ara");
        ara.value = VO.arama;
        let zamanlayici = null;
        ara.oninput = () => {
            clearTimeout(zamanlayici);
            zamanlayici = setTimeout(() => { VO.arama = ara.value; tazele(); }, 150);
        };
        filtre.appendChild(ara);
        const alt = elYap("div", "ft-filtre-alt");
        const tipler = ftTipSecenekleri();
        const tip = ftSecim("", tipler, tipler.some(o => o.deger === VO.tip) ? VO.tip : "",
                            v => { VO.tip = v; tazele(); });
        if (tip.value !== VO.tip) VO.tip = tip.value;
        tip.classList.add("ft-tip-suzgec");
        tip.setAttribute("aria-label", "Tipe göre süz");
        tip.disabled = tipler.length <= 2;
        if (tip.disabled) tip.title = tipler.length <= 1
            ? "Tip bilgisi Değişken Listesi dolunca gelir."
            : "Listede tek tip var; süzmeye gerek yok.";
        alt.appendChild(tip);
        if (d.donem && (d.gruplar || []).length) {
            const ds = ftSecim("", [{ deger: "", etiket: "Dönem: tümü" }].concat(
                d.gruplar.map(g => ({ deger: g.donem === null ? VO_BOS_DONEM : String(g.donem),
                                      etiket: g.donem === null ? "Dönemi boş" : String(g.donem) }))),
                VO.donem, v => { VO.donem = v; tazele(); });
            ds.classList.add("ft-tip-suzgec");
            ds.setAttribute("aria-label", "Döneme göre süz");
            alt.appendChild(ds);
        }
        const sira = ftSecim("", VO_KOL_SIRALAMA, VO.kolSira, v => { VO.kolSira = v; tazele(); });
        sira.classList.add("ft-sirala");
        sira.setAttribute("aria-label", "Kolonları sırala");
        alt.appendChild(sira);
        filtre.appendChild(alt);
        kap.appendChild(filtre);
        const ciplar = elYap("div", "sz-ciplar");
        kap.appendChild(ciplar);

        const sar = elYap("div", "vo-sar");
        kap.appendChild(sar);

        function ciplarCiz() {
            const ogeler = [];
            if (VO.arama.trim()) ogeler.push({ etiket: "Kolon araması: " + VO.arama.trim(),
                kaldir: () => { VO.arama = ""; ciz(d); } });
            if (VO.tip) ogeler.push({ etiket: "Tip: " + VO.tip, kaldir: () => { VO.tip = ""; ciz(d); } });
            if (VO.donem) ogeler.push({ etiket: "Dönem: " + (VO.donem === VO_BOS_DONEM ? "Dönemi boş" : VO.donem),
                kaldir: () => { VO.donem = ""; ciz(d); } });
            Object.keys(VO.kolonSz).forEach(k => {
                if (!szAktif(VO.kolonSz[k])) return;
                ogeler.push({ etiket: k + ": " + szOzet(VO.kolonSz[k]),
                    kaldir: () => { delete VO.kolonSz[k]; tazele(); } });
            });
            szCiplarCiz(ciplar, ogeler, () => {
                VO.arama = ""; VO.tip = ""; VO.donem = ""; VO.kolonSz = {}; ciz(d);
            });
        }
        function tabloCiz() {
            sar.textContent = "";
            const { kolIdx, gruplar } = suz;
            sayac.textContent = (kolIdx.length < kol.length
                ? ftBinlik(kolIdx.length) + " / " : "") + ftBinlik(kol.length) + " kolon";
            const gs = gruplar.reduce((t, gr) => t + gr.satirlar.length, 0);
            kaynak.textContent = (d.donem
                ? "Dönem kolonu " + d.donem + " · "
                  + (VO.donem ? "1 / " : "") + ftBinlik((d.gruplar || []).length)
                  + " dönem · her dönemin ilk 10 satırı · "
                : "ilk 10 satır · ")
                + (suz.satirSuzulu ? ftBinlik(gs) + " / " + ftBinlik(satirlar.length)
                                   : ftBinlik(gs)) + " satır";
            ciplarCiz();
            kaynak.title = kaynak.textContent;
            const aramaKolon = kolIdx.filter(i => kol[i] !== d.donem);
            if (!aramaKolon.length && (VO.arama || VO.tip)) {
                sar.appendChild(elYap("div", "ft-bos", "Aramayla eşleşen kolon yok."));
                return;
            }
            const t = elYap("table", "vo-tablo");
            const th = document.createElement("thead"), hr = document.createElement("tr");
            hr.appendChild(elYap("th", "vo-no", "#"));
            kolIdx.forEach(i => {
                const k = kol[i];
                const ok = VO.satirKol === k ? (VO.yon === 1 ? " ▲" : " ▼") : "";
                const h = elYap("th", "vo-bas" + (k === d.donem ? " vo-donem-kol" : "")
                                + (d._sayisal[i] ? " vo-sayi" : ""));
                const ic = elYap("span", "vo-bas-ic");
                ic.appendChild(elYap("span", "sz-etiket", k + ok));
                ic.appendChild(szDugme(k, szAktif(VO.kolonSz[k]), b => szMenuAc(b, {
                    baslik: k,
                    degerler: voAdayDegerler(d, k),
                    sayisal: d._sayisal[i],
                    mevcut: VO.kolonSz[k],
                    sirala: yon => { VO.satirKol = k; VO.yon = yon; tazele(); },
                    uygula: sz => { if (sz) VO.kolonSz[k] = sz; else delete VO.kolonSz[k]; tazele(); }
                })));
                h.appendChild(ic);
                h.title = k + " · satırları bu kolona göre sırala";
                h.tabIndex = 0;
                const sirala = () => {
                    if (VO.satirKol === k) VO.yon = -VO.yon;
                    else { VO.satirKol = k; VO.yon = 1; }
                    tazele();
                };
                h.onclick = sirala;
                h.onkeydown = ev => {
                    if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); sirala(); }
                };
                hr.appendChild(h);
            });
            th.appendChild(hr); t.appendChild(th);
            const tb = document.createElement("tbody");
            gruplar.forEach(gr => {
                if (gr.g) {
                    const g = gr.g;
                    const tr = elYap("tr", "vo-grup");
                    const td = document.createElement("td");
                    td.appendChild(elYap("span", "vo-grup-ad",
                        (g.donem === null ? "Dönemi boş" : g.donem)
                        + " · " + ftBinlik(g.satir) + " satır" + (g.satir > g.gosterilen
                            ? " · ilk " + g.gosterilen + " gösteriliyor" : "")
                        + (suz.satirSuzulu ? " · süzgeçle " + ftBinlik(gr.satirlar.length) : "")));
                    td.colSpan = kolIdx.length + 1;
                    tr.appendChild(td); tb.appendChild(tr);
                }
                gr.satirlar.forEach((ri, n) => {
                    const r = satirlar[ri] || [];
                    const tr = document.createElement("tr");
                    tr.appendChild(elYap("td", "vo-no", String(n + 1)));
                    kolIdx.forEach(i => {
                        const v = r[i] === undefined ? null : r[i];
                        const td = elYap("td", (v === null ? "vo-bos" : "")
                            + (kol[i] === d.donem ? " vo-donem-kol" : "")
                            + (d._sayisal[i] ? " vo-sayi" : ""), v === null ? BOS_SIMGE : v);
                        if (v !== null && v.length > 24) td.title = v;
                        tr.appendChild(td);
                    });
                    tb.appendChild(tr);
                });
            });
            t.appendChild(tb); sar.appendChild(t);
            if (!gs) sar.appendChild(elYap("div", "ft-bos", "Süzgeçlerle eşleşen satır yok."));
        }
        function tazele() {
            suz = voSuz(d);
            const x = sar.scrollLeft;
            tabloCiz();
            sar.scrollLeft = x;
        }
        tabloCiz();
    };
    if (ONIZLEME.veri) { ciz(ONIZLEME.veri); return; }
    kap.appendChild(elYap("div", "dag-not", "Önizleme yükleniyor"));
    const istek = ++ONIZLEME.istek;
    fetch(getWebAppBackendUrl("veri_onizleme") + "?oturum_id=" + encodeURIComponent(OTURUM_ID))
        .then(r => r.json())
        .then(d => {
            if (istek !== ONIZLEME.istek) return;
            if (d && d.tamam !== false && !d.hata) ONIZLEME.veri = d;
            if (kap.isConnected) ciz(d);
        })
        .catch(e => { if (kap.isConnected) ciz({ hata: "Önizleme okunamadı: " + e }); });
}

function analizGuncelle(veri) {
    if (!veri) return;
    ANALIZ_VERI = veri;
    guncellemeleriTazele(veri);
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
    onizlemeSifirla();
    // Acik sekme backend verisine bagliysa yeniden ciz
    if (BAGLI_SEKMELER.indexOf(aktifAnalizSekme) !== -1)
        analizCiz(aktifAnalizSekme);
}

/* Sekmeyi disaridan ac: ust seritteki tiklanabilir kartlar bunu cagirir.
   "aktif" sinifi tek yerden yonetilir. */
/* otomatik: akış kendisi açtıysa (analizOtoGuncelle). Kullanıcı başka
   bir sayfadaysa (ör. Ana Sayfa) oradan koparılmaz; analiz alanı açık
   işaretlenir, Model Akışı'na dönünce açık görünür. */
function analizSekmeAc(tab, otomatik) {
    const hedef = Array.from(analizSekme).find(x => x.dataset.tab === tab);
    if (!hedef) return;
    analizSekme.forEach(x => x.classList.toggle("aktif", x === hedef));
    /* HIZ: blok kapalıyken içerik zaten çizili duruyor (veri gelince
       analizGuncelle yeniden çizer); aynı sekme baştan çizilmez, büyük
       tablolarda açılış yavaşlamaz. */
    if (tab !== aktifAnalizSekme || !analizGovde.childElementCount) analizCiz(tab);
    /* Analiz alanı çalışma sayfasının içinde: başka sayfa açıksa önce
       oraya dönülür. Sonra alan açılır (animasyonsuz). */
    if (acikSayfa() !== "calisma" && !otomatik) sayfaAc("calisma");
    analizAcikYaz(true);
}

/* ==================== Sol bar sekmeleri ve analiz alanı ====================
   Sol barda (MODEL PLATFORMU kümesi): MODEL AKIŞI · MODEL GÖSTERGELERİ ·
   DEĞİŞKENLER · ÖZET. Kodda MODEL AKIŞI = "akis" (AKIŞ).
   AKIŞ ana ekran (iş akışı + sohbet). Üç analiz sekmesinden birine
   basınca analiz alanı sol barın sağındaki bütün alanı kaplar
   (style.css: #analiz-panel); AKIŞ'a basınca yukarı kapanır
   (#kabuk.analiz-dar). ÖZET doküman sayfasıdır.

   KENDİLİĞİNDEN AÇILMA: kararı ANALİZ ALANINDA verilen adım gelince.
   Adım kartın tipiyle tanınıyor: PANELDE_KARAR. Şu an yalnız SFA
   (değişken kararları DEĞİŞKENLER'de veriliyor); o sırada alanın altında
   "Kararları Onayla" da durur (analizAltGuncelle). Kararı sohbetteki
   kartta verilen adımlar alanı AÇMAZ. Adım geçince (SFA onaylanınca)
   alan kapanır, AKIŞ'a dönülür. Kullanıcı SFA sırasında AKIŞ'a dönerse
   aynı adımda alan tekrar kendiliğinden açılmaz (kapatilanAdim). */
/* PANELDE_KARAR ve ANALIZ_DAR dosyanın başında tanımlı (sayfaAc ilk
   çağrıldığında da hazır olsunlar). */

function analizAcikYaz(acik) {
    ANALIZ_DAR.acik = !!acik;
    kabukEl.classList.toggle("analiz-dar", !ANALIZ_DAR.acik);
    ustSekmeGuncelle();
}

/* Sol bardaki seçili kutu: açık sayfa ÇALIŞMA ise analiz alanı açıksa o
   sekme, değilse AKIŞ; öteki sayfalarda o sayfanın kutusu. */
function acikSayfa() {
    return Object.keys(sayfalar).find(k => sayfalar[k] && !sayfalar[k].classList.contains("gizli"))
        || "calisma";
}
function ustSekmeGuncelle() {
    const sayfa = acikSayfa();
    document.querySelectorAll(".ust-sekme").forEach(b => {
        let aktif;
        if (b.dataset.ust === "akis") aktif = sayfa === "calisma" && !ANALIZ_DAR.acik;
        else if (b.dataset.ust) aktif = sayfa === UST_SAYFA[b.dataset.ust];
        else aktif = sayfa === "calisma" && ANALIZ_DAR.acik && b.dataset.tab === aktifAnalizSekme;
        b.classList.toggle("aktif", aktif);
        if (aktif) b.setAttribute("aria-current", "page");
        else b.removeAttribute("aria-current");
    });
}

function analizDaralt(kullanici) {
    if (kullanici && ANALIZ_DAR.otoAdim)
        ANALIZ_DAR.kapatilanAdim = ANALIZ_DAR.otoAdim;
    analizAcikYaz(false);
}

/* Her sunucu yanıtında çağrılır (hata yanıtı hariç). alan: secim_alani,
   adim: adim_anahtari, bekleyen: "girdi" / "onay" / null. */
function analizOtoGuncelle(alan, adim, bekleyen) {
    if (bekleyen === undefined || !adim) return;
    const tab = alan && PANELDE_KARAR[alan.tip];
    if (tab && bekleyen === "girdi") {
        if (ANALIZ_DAR.otoAdim !== adim) {
            ANALIZ_DAR.otoAdim = adim;
            if (ANALIZ_DAR.kapatilanAdim !== adim) {
                if (tab === "degisken") DG.alt = "dagilim";    // SFA kararları
                analizSekmeAc(tab, true);
            }
        }
        analizAltGuncelle(alan.tip);
        return;
    }
    analizAltGuncelle(null);
    /* Aynı adımda kart taşımayan bir yanıt (ör. ara mesaj) bloğu
       kapatmaz; yalnız adım değişince kapanır. */
    if (ANALIZ_DAR.otoAdim && adim !== ANALIZ_DAR.otoAdim) {
        ANALIZ_DAR.otoAdim = null;
        ANALIZ_DAR.kapatilanAdim = null;
        analizDaralt(false);
    }
}

/* ANA SAYFA, AKIŞ, ÖZET, SOHBET, DASHBOARD kutuları. Esc analiz alanını kapatır
   (AKIŞ'a döner). */
document.querySelectorAll(".ust-sekme[data-ust]").forEach(b => {
    b.onclick = () => {
        if (b.classList.contains("kapali")) return;   // henüz açılmadı
        analizDaralt(true);
        sayfaAc(UST_SAYFA[b.dataset.ust] || "calisma");
    };
});
document.addEventListener("keydown", e => {
    if (e.key === "Escape" && ANALIZ_DAR.acik) analizDaralt(true);
});

/* ==================== ANA SAYFA ====================
   Üstteki görsel (anasayfa_aciklama) yüklenemezse yeri kapanır. Kart ve
   sayfa simgeleri sol barın çizimleri (beyaz zemini saydam). Ana Sayfa
   yalnız tanıtır, sayfalar sol bardan açılır. */
(function anaSayfaKur() {
    const kok = document.getElementById("sayfa-anasayfa");
    if (!kok) return;
    /* Üst bölüm görseli: saydam kenarları kırpılır; çizim yazının
       altında bloğun iç eninin tamamını kaplar. */
    const hero = document.getElementById("as-hero-img");
    if (hero) {
        const yok = () => hero.parentElement.classList.add("yok");
        hero.onerror = yok;
        hero.onload = () => {
            if (hero.naturalHeight) hero.style.setProperty("--gorsel-oran",
                hero.naturalWidth / hero.naturalHeight);
            anaSayfaSigdir();
        };
        saydamKirp(getWebAppBackendUrl("gorsel/anasayfa_aciklama"),
                   src => { hero.src = src; }, yok);
    }
    /* İLK EKRAN SIĞDIRMA: üst bölüm ve Çalışma Alanları kartları sayfanın
       yüksekliğini tam doldurur; ne kaydırma çubuğu açılır ne altta boşluk
       kalır. Görselin eni (dolayısıyla boyu, oranı sabit) kartların alt
       kenarıyla sayfanın altı arasında sayfanın alt iç boşluğu kalacak
       şekilde ayarlanır: en az bloğun
       iç eninin %30'u, en çok %100'ü. Görsel en çok enine ulaştıktan sonra
       artan yükseklikle önce başlık büyür (en çok 1,15 kat), kalanı üst
       bölüme eklenir (içerik dikeyde ortalı). Ölçüler
       ekrandaki (yakınlaştırılmış) boyutlarla oranlanır; ölçek farkı
       sonucu değiştirmez. Açılan kart açıklaması kartların altında kaldığı
       için hesaba girmez. Dar ekranda (1100 px altı) yapılmaz. */
    const heroBlok = kok.querySelector(".as-hero");
    const kartAlani = kok.querySelector(".as-kartlar");
    const darEkran = window.matchMedia("(max-width: 1100px)");
    function anaSayfaSigdir() {
        if (!hero || !heroBlok || !kartAlani) return;
        hero.style.width = "";
        heroBlok.style.minHeight = "";
        heroBlok.style.removeProperty("--baslik-k");
        if (darEkran.matches || !kok.clientHeight || !hero.naturalWidth
            || hero.parentElement.classList.contains("yok")) return;
        const varsayilan = 94;
        const iR = hero.getBoundingClientRect();
        if (!iR.height) return;
        const olcek = iR.height / hero.offsetHeight;   /* ekran px / sayfa px */
        /* +2 px: yuvarlamadan doğan 1 px'lik kaydırmayı önler */
        const altPay = ((parseFloat(getComputedStyle(kok.firstElementChild).paddingBottom) || 0) + 2) * olcek;
        const fazla = kartAlani.getBoundingClientRect().bottom + altPay
                      - kok.getBoundingClientRect().bottom;
        let yuzde = varsayilan * (iR.height - fazla) / iR.height;
        yuzde = Math.max(30, Math.min(100, yuzde));
        hero.style.width = yuzde + "%";
        const kalanOlc = () => kok.getBoundingClientRect().bottom
                               - (kartAlani.getBoundingClientRect().bottom + altPay);
        if (yuzde >= 100) {
            /* Görsel tam ende: kalan boşluğun önce bir kısmıyla başlık
               büyür (en çok 1,15 kat), artanı üst bölüme eklenir. */
            const baslik = heroBlok.querySelector(".as-baslik");
            const bY = baslik ? baslik.getBoundingClientRect().height : 0;
            let kalan = kalanOlc();
            if (bY && kalan > 1) {
                heroBlok.style.setProperty("--baslik-k",
                    Math.min(1.15, 1 + kalan / bY).toFixed(3));
                kalan = kalanOlc();
            }
            if (kalan > 1) heroBlok.style.minHeight =
                (heroBlok.offsetHeight + kalan / olcek) + "px";
        }
    }
    if (window.ResizeObserver) new ResizeObserver(anaSayfaSigdir).observe(kok);
    window.addEventListener("resize", anaSayfaSigdir);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(anaSayfaSigdir);
    kok.querySelectorAll("img[data-as-ikon]").forEach(img => {
        solBarGorseli(img.dataset.asIkon).then(src => { img.src = src; },
            () => img.classList.add("yok"));
    });
    /* Kart açıklamaları: karta basınca (ya da klavyede Enter / Boşluk)
       kart seçilir ve kartların altında o alanın açıklaması açılır,
       yeniden basınca ikisi de kalkar; aynı anda tek kart seçili.
       Açılan açıklama, sayfanın üst kenarı kartlarla açıklama başlığı
       arasındaki boşluğun ortasına gelecek şekilde kaydırılır: başlık
       ekranın tepesine yapışmaz, üstünde kartlarla arasındaki boşluğun
       yarısı kadar pay kalır. */
    const kartlar = Array.from(kok.querySelectorAll(".as-kart[data-ayrinti]"));
    const ayrintilar = Array.from(kok.querySelectorAll(".as-ayrinti[data-alan]"));
    function ayrintiAc(alan) {
        const acikMi = kartlar.some(k => k.dataset.ayrinti === alan
                                         && k.classList.contains("secili"));
        const hedef = acikMi ? null : alan;
        kartlar.forEach(k => {
            const sec = k.dataset.ayrinti === hedef;
            k.classList.toggle("secili", sec);
            k.setAttribute("aria-expanded", sec ? "true" : "false");
        });
        ayrintilar.forEach(a => { a.hidden = a.dataset.alan !== hedef; });
        const gorunen = ayrintilar.find(a => !a.hidden);
        if (gorunen) {
            const kartAlt = kok.querySelector(".as-kartlar").getBoundingClientRect().bottom;
            const ustu = gorunen.getBoundingClientRect().top;
            const hedef = kok.scrollTop + ((kartAlt + ustu) / 2 - kok.getBoundingClientRect().top)
                          / ekranOlcegi();
            kok.scrollTo({ top: Math.max(0, hedef), behavior: "smooth" });
        }
    }
    kartlar.forEach(k => {
        k.onclick = () => ayrintiAc(k.dataset.ayrinti);
        k.onkeydown = e => {
            if (e.key === "Enter" || e.key === " ") { e.preventDefault(); ayrintiAc(k.dataset.ayrinti); }
        };
    });
    /* Uygulama Ana Sayfa ile açılır (index.html'de görünen sayfa); sol
       barda da Ana Sayfa seçili görünsün. */
    sayfaAc("anasayfa");
})();

/* MODEL PLATFORMU kümesi başta kapalı; başlığa basınca içindeki sayfalar
   açılır ve Model Akışı seçilir (o an kümenin sayfalarından biri zaten
   açıksa o kalır); yeniden basınca küme kapanır, açık sayfa değişmez.
   Açılır kümeler açık sayfayı izler (kumeleriEsle): sol bardan ya da
   başka bir yoldan kümenin dışındaki bir sayfaya geçilince küme kapanır,
   içindeki bir sayfaya geçilince (Yeni Çalışma, Arşiv'den çalışma
   açma) açılır. Yalnız sayfa değişince uygulanır: aynı sayfadayken
   başlıktan kapatılan küme kendiliğinden yeniden açılmaz. */
function kumeAyarla(kume, acik) {
    kume.classList.toggle("acik", acik);
    const ad = kume.querySelector(".ust-kume-ad");
    if (ad) ad.setAttribute("aria-expanded", acik ? "true" : "false");
}
function kumeIcindeMi(kume, sayfa) {
    return [...kume.querySelectorAll(".ust-sekme[data-ust]")]
        .some(b => UST_SAYFA[b.dataset.ust] === sayfa);
}
function kumeleriEsle(sayfa) {
    document.querySelectorAll("#sol-bar .ust-kume.acilir").forEach(kume => {
        const icerde = kumeIcindeMi(kume, sayfa);
        if (kume.classList.contains("acik") !== icerde) kumeAyarla(kume, icerde);
    });
}
function kumeAcKapa(kume) {
    const acik = !kume.classList.contains("acik");
    kumeAyarla(kume, acik);
    if (!acik) return;
    const akis = kume.querySelector('.ust-sekme[data-ust="akis"]');
    if (akis && !kumeIcindeMi(kume, acikSayfa())) akis.click();
}
document.querySelectorAll(".ust-kume.acilir > .ust-kume-ad").forEach(ad => {
    ad.onclick = () => kumeAcKapa(ad.parentElement);
});

/* SFA sırasında analiz alanının altındaki "Kararları Onayla": sohbetteki
   SFA kartının birincil düğmesine basar (tek karar, iki düğme). Kart
   kendi düğmesini SFA_ONAY_DUGMESI'ne kaydeder (sfaKartiEkle). */
let SFA_ONAY_DUGMESI = null;
function analizAltGuncelle(tip) {
    const alt = document.getElementById("analiz-alt");
    const teyit = document.getElementById("analiz-teyit");
    const sfa = document.getElementById("analiz-sfa-onay");
    if (!alt || !sfa) return;
    const goster = tip === "sfa_karar" && SFA_ONAY_DUGMESI && SFA_ONAY_DUGMESI.isConnected;
    sfa.hidden = !goster;
    if (teyit) teyit.hidden = !!goster;
    if (goster) {
        alt.hidden = false;
        sfa.textContent = SFA_ONAY_DUGMESI.textContent;
        sfa.disabled = SFA_ONAY_DUGMESI.disabled;
    } else if (teyit) {
        alt.hidden = true;
    }
}
{
    const sfa = document.getElementById("analiz-sfa-onay");
    if (sfa) sfa.onclick = () => {
        if (SFA_ONAY_DUGMESI && !SFA_ONAY_DUGMESI.disabled) {
            SFA_ONAY_DUGMESI.click();
            sfa.disabled = true;
        }
    };
}

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

/* Sağ panelde ikiz "Teyit Et" düğmesi çizilmez: sözlük teyidi sohbetteki
   karttan yapılır, panel yalnızca açıklama verir.

   TEYIT kaydı: sohbet kartı kendi düğmesini oraya bağlar, adım geçince
   kayıt temizlenir. */
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



analizSekme.forEach(s => {
    const bagli = BAGLI_SEKMELER.indexOf(s.dataset.tab) !== -1;
    if (!bagli) {
        s.classList.add("hazir-degil");
        s.title = "Hazırlanıyor - bu sekmenin verisi henüz bağlı değil";
    }
    s.onclick = () => analizSekmeAc(s.dataset.tab);
});
analizCiz("ozet");
analizAcikYaz(false);


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
   tablo yolları, birleştirme sayıları, model özeti...).

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
    
    let yeniKapandi = false;
    satirlar.forEach((satir, i) => {
        const e = CIKTI_SATIRI.exec(satir);
        if (e) {
            
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
   Bloklar SUTUNUN TAMAMINI kaplar ve her iki tarafta da avatar vardir.

   Gorsel YUKLENMEZSE (folder'da yok, ag hatasi) <img> kendini gizler:
   kirik resim ikonu, olmayan bir seyin yerini tutmaktan kotudur. */
/* ROBOT GÖRSELLERİ: sohbetteki İLK robot (karşılama)
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
   Onay düğmeleri blokların İÇİNDE: her blok kendi kararını taşır.

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
   Gruplu blokta ad alt başlıkta duruyor, tekli
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
       (doğrulama, teyit, form) da kullanıyor. */
    bas.appendChild(avatarYap("bot"));
    const konum = b.kod === undefined ? adimKonumu(b.adim) : null;
    bas.appendChild(elYap("span", "blok-ad",
                          numarali(b.kod !== undefined ? b.kod : (konum ? konum.kod : ""),
                                   b.baslik)));
    /* Durum rozetinin yuvası - gruplu bloktaki .alt-bas ile AYNI sınıf.
       Kart kendi başlığını çizmediği için rozeti ("✓ Girdiler Onaylandı")
       burada durur; boşken CSS onu gizliyor. */
    bas.appendChild(elYap("span", "alt-rozet"));

    /* ADIM ANAHTARI KABIN ÜZERİNDE: geri dönüşte transkript bu
       işaretten kırpılıyor (bkz. transkriptiKirp). Kart da blok da
       aynı işareti taşımalı, ikisi de birer adım bloğu. */
    if (b.adim) kap.dataset.adim = b.adim;

    /* HER BLOKTA GERİ DÖN, ilk adım dahil. */
    if (b.adim && b.geri !== false) bas.appendChild(geriDugmesiYap(b));
    kap.appendChild(bas);
    return bas;
}

/* KIRPMA ADIM SIRASINA GÖRE, blok bulmaya göre DEĞİL: "kurulum" ve
   "tanımlar" gibi adımlar bilerek metin döndürmüyor (karar kartın içinde)
   ve F5 sonrası transkriptte hiç blok bırakmıyorlar. Sıra numarası
   karşılaştırılır: hedefe EŞİT ya da ondan SONRAKİ ilk blok ve sonrası
   silinir. */
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
       duruyor; "Kolon Rolleri"na dönünce o bloğun tamamını silmek
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

    /* KESİM NOKTASININ ÜSTÜNE DOKUNULMAZ: bir kullanıcı satırının HANGİ
       adıma ait olduğu DOM'da yazmıyor. Yalnızca hedef adımın bloğundan
       İTİBAREN silinir; üstü kullanıcının geçmişi olarak kalır.
       (Form ve kart gönderimleri sessiz, yani pratikte kesim
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
           Adım anahtarı
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
        metinYaz(balon, metin);
    } else {
        balon.textContent = metin;          // kullanicinin yazdigi aynen kalir
    }
    return balon;
}

/* ---- ADIM BLOĞU: bir adımın BÜTÜN ekranları TEK çerçevede ----
   İş akışı adım adım ilerliyor ve ekran da adım adım gruplanıyor. Ama
   bir adım birden fazla ekran üretebiliyor: "Veri ve Sözlük" önce
   seçim formunu, sonra girdi doğrulama kartını gösteriyor.

   Bu fonksiyon o adımın AÇIK kabını döndürür: sohbetin en altındaki
   blok aynı adıma aitse ona eklenir, değilse yeni blok kurulur.
   Başlık ve Geri Dön kabın kendisinde durur, içine giren kartlarda
   değil (bkz. style.css: .adim-blok > .secim-kart çerçevesizdir). */
/* ---- GRUPLU BLOK ----
   Ardışık adımlar (veri seti seçimi → kolon rolleri → sözlük
   tanımları) sohbette TEK blok olarak görünür. Blok başlığı GRUP adını
   ("Veri ve Sözlük") taşır; her adım bloğun içinde kendi ALT BAŞLIĞINI
   ve kendi "Geri Dön" düğmesini taşır. Sol paneldeki iş akışında
   adımlar AYRI kalır, yani yalnızca Kolon Rolleri adımına dönmek
   mümkün. Gruplama GÖRSELDİR: adım sırası ve geri dönüş hedefi
   değişmez. */
/* GEÇİLMİŞ ADIMIN KABI TEKTİR. Sohbette geçilmiş bir adımın bloğu (ya da
   gruplu bloktaki bölümü) zaten varsa, o adıma ait her şey ORAYA girer;
   sohbetin sonuna yeni blok açılmaz. Yenilemede geçmişten çizilen kartların
   geç gelen yanıtları (ör. kararlı kartın yeniden kurulması) aktif adımın
   altına düşmesin. Aktif ve sonraki adımlar eski davranışta kalır: canlı
   akışta aynı adımın yeni yanıtı kullanıcı satırının altına yeni blokla
   gelir. */
function gecilmisAdimKabi(blok) {
    if (!sohbetEl || !blok || !blok.adim) return null;
    const sira = (adimSirasiHaritasi() || {})[blok.adim];
    if (sira === undefined || sira >= aktifAdim) return null;
    const ad = CSS.escape(blok.adim);
    if (blok.grup) {
        const bolumler = sohbetEl.querySelectorAll('.adim-blok.gruplu .alt-bolum[data-adim="' + ad + '"]');
        return bolumler.length ? bolumler[bolumler.length - 1] : null;
    }
    const bloklar = [...sohbetEl.querySelectorAll('.adim-blok[data-adim="' + ad + '"]')]
        .filter(b => !b.dataset.grup);
    return bloklar.length ? bloklar[bloklar.length - 1] : null;
}

function grupKabiAl(blok) {
    const varOlan = gecilmisAdimKabi(blok);
    if (varOlan) return varOlan;
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
        altBlokGizle(bolum);
        const bas = elYap("div", "alt-bas");
        bas.appendChild(elYap("span", "alt-ad",
                              numarali(konum ? konum.altKod : "", blok.baslik)));
        /* ROZET YUVASI: kartın "✓ Girdiler Onaylandı" göstergesi buraya
           taşınıyor. */
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

/* ---- FAZ BİTTİ AYRACI ----
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
    const varOlan = gecilmisAdimKabi(blok);
    if (varOlan) return varOlan;

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
     - AKTİF ADIMIN bloğu (ya da gruplu blokta aktif adımın bölümü)
       kırmızı çerçeve + "● Yanıtınız Bekleniyor" etiketi,
     - geçilmiş bloklar gri çerçeve, sessiz başlık ve "✓ Tamamlandı".
   Aktif adım sol paneldeki ile AYNI kaynaktan: DUZ_ADIMLAR[aktifAdim].
   Kart kendi "✓ Girdiler Onaylandı" rozetini taşıyorsa ikinci bir
   "Tamamlandı" yazılmaz: aynı şeyi iki kez söylemesin. */
const BLOK_BEKLIYOR = "● Yanıtınız Bekleniyor";
/* YANIT VERİLDİ, SUNUCU İŞLİYOR: "Yanıtınız
   Bekleniyor" o sırada yanlış - yanıt zaten verildi. Blok SARI olur,
   kartın kendi rozeti boş kalır; tek etiket bu. */
const BLOK_KONTROL = "● Kontrol Ediliyor";
const BLOK_TAMAM = "✓ Tamamlandı";
/* AÇIKLAMALI ONAY. Adım başına kısa, geçmiş zamanlı bir onay; listede
   olmayan adımda genel "Tamamlandı" kalır. */
const BLOK_TAMAM_METNI = {
    ham_veri: "Kaynak Tablolar Seçildi",
    kaynak_sozluk: "Kaynak Sözlükler Onaylandı",
    birlestirme: "Baz Veri Seti Oluşturuldu",
    veri_sec: "Baz Veri Seti Seçildi",
    sozluk_uret: "Baz Sözlük Oluşturuldu",
    kurulum: "Girdiler Onaylandı",
    tanimlar: "Kolon Rolleri Onaylandı",
    sozluk_tanim: "Eksik Sözlük Tanımları Kaydedildi",
    tanimsiz_karar: "Tanımsız ve Sorunlu Kolonlar Kararı Verildi",
    sozluk_birlestir: "Sözlük Tanımları Seçildi",
    parca: "Ad Parçaları Onaylandı",
    kolon_ad: "Kolon Adları Belirlendi",
    teyit: "Değişken Listesi Kaydedildi",
    bolme: "Bölme Uygulandı",
    veri_profili: "Veri Profili Çıkarıldı",
    sfa: "Tek Değişken Analizi Yapıldı",
    stabilite: "Stabilite Ölçüldü",
    baz: "Analitik Baz Set Hazırlandı",
    kural: "Kural Tabanlı Değişkenler Üretildi",
    kesif: "AI Değişken Keşfi Yapıldı",
    kalite: "Sızıntı Kontrolü Yapıldı",
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
    /* Kartın kendi rozeti başlığa taşındıysa (ör. "46 Kısaltmanın Anlamı
       Onaylandı") adımın genel "Tamamlandı" rozeti ikinci kez çizilmez. */
    const onayliRozet = durum === "tamam"
        && [...bas.querySelectorAll(":scope > .alt-rozet > *")]
            .some(x => x.classList.contains("onayli") || x.textContent.trim());
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
    /* Çerçeve kontrol sırasında da KIRMIZI kalır;
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
   BALON DEĞİL. Bunu asistan söylemiyor, uygulama söylüyor. İnce, nötr bir şerit. */
function sistemNotuEkle(metin) {
    const not = elYap("div", "sistem-notu");
    not.setAttribute("role", "status");
    not.innerHTML = metinBicimle(tireSade(metin));
    sohbetEl.appendChild(not);
    sohbetKaydir();
    return not;
}

/* ==================== Otomatik kaydırma ====================
   Kurallar:
   - Yeni içerik gelince sohbet EN ALTA değil, YENİ İÇERİĞİN BAŞINA
     kaydırılır. Zincirleme adımlarda (02.1 çıktısı, ardından 02.2 kartı)
     ilk gelen çıktı ekranda kalır; altındakine kullanıcı kendisi iner.
   - Ekran yalnızca AŞAĞI kaydırılır, asla yukarı çekilmez.
   - Kullanıcı istek sürerken kendisi kaydırdıysa hiç kaydırılmaz.
   - Yeni bir gönderim (kart onayı, mesaj) bu durumu sıfırlar.
   Geçmiş yüklenirken (gönderim yokken) en alta gider. */
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

/* İŞLEM SATIRI: ayrı bir "yükleniyor" kartı YOK.
   Durumu başlıktaki "● Kontrol Ediliyor" etiketi anlatıyor; aktif adımın
   bloğunun EN ALTINA tek ince satır gelir: "İşlem Devam Ediyor · 0:12 · İptal".
   Satır ve düşünen avatar ilk ISLEM_GECIKME_MS boyunca görünmez: anında
   dönen işlemlerde ekran yanıp sönmez. Kısa: daha uzun gecikme
   işlemin başladığını geç gösterir. Her adımda aynı. */
const ISLEM_GECIKME_MS = 250;

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

/* DÜŞÜNEN AVATAR: bir işlem sürerken (sohbet isteği, açıklama
   önerileri, kısaltma okuması) bulunduğu bloğun avatarı düşünen hâle
   geçer. Aynı blokta birden fazla işlem sürebildiği için sayaçla tutulur;
   son işlem bitince eski görsel geri gelir. */
function avatarDusunsun(el, acik) {
    const blok = el && el.closest ? el.closest(".adim-blok") : null;
    const av = blok ? blok.querySelector(".balon-avatar.bot") : null;
    if (!av || av.classList.contains("karsilama")) return;
    const n = Math.max(0, (Number(av.dataset.dusun) || 0) + (acik ? 1 : -1));
    av.dataset.dusun = String(n);
    if (n > 0) {
        if (!av.dataset.normal) av.dataset.normal = av.src;
        av.src = GORSEL.dusunme;
    } else if (av.dataset.normal) {
        av.src = av.dataset.normal;
        delete av.dataset.normal;
    }
}

/* Kart içi işlem satırları için: durum değişince avatara bildirir. */
function dusunmeIzleyici(el) {
    let acik = false;
    return function (yeni) {
        yeni = !!yeni;
        if (yeni === acik || (yeni && !el.isConnected)) return;
        acik = yeni;
        avatarDusunsun(el, yeni);
    };
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
        iptal.textContent = "İptal ediliyor";
        if (iptalEt) iptalEt();
    };
    /* DÜŞÜNEN ROBOT: işlem sürerken çalışan bloğun başlığındaki robot
       geçici olarak düşünen hâle geçer. "İşlem Devam Ediyor" satırına
       görsel konmaz. */
    satir.append(sure, iptal);
    (kap || sohbetEl).appendChild(satir);
    const dusun = dusunmeIzleyici(satir);

    let gecen = 0;
    const yaz = () => { sure.textContent = "İşlem Devam Ediyor · " + sureBicim(gecen); };
    yaz();
    const sayac = setInterval(() => { gecen += 1; yaz(); }, 1000);
    const goster = setTimeout(() => {
        satir.classList.add("gorunur");
        dusun(true);
        if (!kap) sohbetKaydir();
    }, ISLEM_GECIKME_MS);
    return {
        kaldir() {
            clearInterval(sayac);
            clearTimeout(goster);
            dusun(false);
            satir.remove();
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
        metinYaz(bas, s.baslik);
        govde.appendChild(bas);

        if (s.aciklama) {
            const ack = document.createElement("div");
            ack.className = "secenek-aciklama";
            metinYaz(ack, s.aciklama);
            govde.appendChild(ack);
        }
        kart.appendChild(govde);

        /* KAPALI SEÇENEK. Soluk durur, tıklanamaz, sağında "Şu An Kapalı". */
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
        /* GRUPLU BLOKTA kartlar adımın KENDİ alt bölümüne girer (sondaki
           alt bölüm, bu adımınki): "Geri Dön" alt bölümü silince kartlar
           da onunla birlikte gider. */
        const bolumler = sutun.classList.contains("gruplu")
            ? sutun.querySelectorAll(":scope > .alt-bolum") : [];
        (bolumler.length ? bolumler[bolumler.length - 1] : sutun).appendChild(kok);
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
    /* Ad once basligin yanindaki cipten (veri_seti_cip) okunur. Kart
       taramasi, cip alani olmayan eski govde bicimi icin yedektir. */
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
          + "?veri_seti=" + encodeURIComponent(veriSeti)
          + "&oturum_id=" + encodeURIComponent(OTURUM_ID))
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

/* "SECILDI" DUGMESI YOK: baslik
   satirinin saginda .secim-durum gostergesi var (bir <span>; dugme degil,
   imleci degismez), gonderildikten sonra birincil dugme GIZLENIR. */
/* ROZETLER BAŞLIK BÜYÜK HARFİYLE. Sabit metinler burada öyle yazılı; arka
   uçtan gelen rozet metinleri rozetMetni() ile aynı biçime çevriliyor. */
/* GÖNDERİLMİŞ KART: "✓ Girdiler Onaylandı". Rozet
   YALNIZCA gönderimden sonra çıkar; dolu ama gönderilmemiş kart "2/2
   Seçildi" der ve düğmesi durur. */
const SECIM_HAZIR = "✓ Girdiler Onaylandı";
const secimDurumMetni = (dolu, toplam) => dolu + "/" + toplam + " Seçildi";
const rozetMetni = (metin) => "✓ " + baslikBuyuk(metin);

const GECERSIZ_GOLGE = "0 0 0 var(--halka) var(--amber-halka)";
const LISTE_YUKSEKLIGI = 208;            /* .combo-liste max-height ile ayni */
let KOMBO_SAYAC = 0;

/* Combo kaynaklari. Varsayilan "dataset": projedeki veri setleri.
   "kolon": secili veri setinin kolonlari. "serbest": liste yok, elle yazilir.
   Liste okunamadiysa ya da bos dondüyse elle yazmaya izin verilir. */
const COMBO_KAYNAKLARI = {
    dataset: {
        liste: () => DATASETLER,
        durum: () => DATASET_DURUMU,
        dinleyiciler: DATASET_DINLEYICILER,
        placeholder: "Veri seti ara",
        yukleniyor_mesaji: "Veri seti listesi yükleniyor",
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
        placeholder: "Kolon ara",
        yukleniyor_mesaji: "Kolon listesi yükleniyor",
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
        placeholder: "Değeri yazın",
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
   kaynak      : "dataset" (varsayilan) | "kolon" | "serbest"
   secilince   : listeden seçilince (tık ya da Enter) çağrılır; verilirse
                 alanın değeri yerine bu karar verir (çoklu alan) */
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
    /* Listede GOSTERILMEYECEK adlar (ör. listeye zaten eklenmiş tablolar).
       Fonksiyon: her çizimde güncel liste okunur. */
    const haricAl = typeof s.haric === "function" ? s.haric : () => [];

    const no = ++KOMBO_SAYAC;
    const kok = document.createElement("div");
    kok.className = "combo";

    const listeId = "combo-liste-" + no;
    const girisId = "combo-giris-" + no;

    if (etiket) {
        const lbl = document.createElement("label");
        /* TEK SATIR ETİKET. "(İsteğe Bağlı)" küçük ve soluk
           ayrı parça; sığmazsa etiket kısalır, tamamı ipucunda. */
        const tam = tireSade(etiket);
        const m = tam.match(/^(.*?)\s*\((İsteğe Bağlı)\)$/);
        lbl.textContent = m ? m[1] : tam;
        if (m) lbl.appendChild(elYap("span", "combo-etiket-ek", " (" + m[2] + ")"));
        lbl.title = tam;
        /* ZORUNLU ALAN: etiketin yanında kırmızı yıldız.
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
       Ok dugmesi ve liste ALANA gore konumlanir; alanin altindaki
       aciklama satiri ("Yalnızca 0/1 değerli kolonlar") disarida kalir. */
    const alanKap = document.createElement("div");
    alanKap.className = "combo-alan";
    alanKap.appendChild(giris);
    kok.appendChild(alanKap);

    /* Listeyi acip kapatan ok dugmesi: acmanin TEK gorunur yolu
       (klavye: ArrowDown). */
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

    /* kaydir=false: FARE ile vurgulama listeyi KAYDIRMAZ.
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
        /* Çoklu alan seçileni kendi listesine ekler (bkz. cokluYap). */
        if (s.secilince) { s.secilince(ad); return; }
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

    /* LİSTE HER ZAMAN YUKARI AÇILIR. Alanın üstünde yer yoksa
       sohbet kaydırılarak yer açılır. */
    function konumla() {
        liste.classList.add("yukari");
        if (!sohbetEl) return;
        const g = giris.getBoundingClientRect();
        const alan = sohbetEl.getBoundingClientRect();
        const yukari = (g.top - alan.top) / ekranOlcegi();
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

    /* Odaklanmak listeyi ACMAZ; liste yalnizca ISTENDIGINDE acilir:
       ok dugmesi, yazmaya baslama ya da ArrowDown. */
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
            if (bulunan && s.secilince) { s.secilince(bulunan); return; }
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
   tanımsız kalır ve 01.2.3.1 Tanımsız Kolonlar'da sorulur; varsayılan
   işaretsizdir.

   Kart sohbet balonunun ICINDE degil, kendi karti olarak dogrudan
   sohbete dusuyor (mevcut .secim-kart deseni): adim bos metin
   dondurdugunde balon hic acilmiyor, ekranda "TAMAM" benzeri bir
   gurultu satiri kalmiyor.

   Kart genel paletin renk degiskenleriyle cizilir. Ekrandaki her ad
   kullanicinin kendi verisinden gelir; sabit ornek veri seti / sozluk /
   kolon adi YOK. */
const DG_EKSIK_NOTU = "Sözlüğe eklenecek kolonların ve uygulanacak düzeltmelerin "
    + "açıklaması boş olamaz.";
/* Öneriler akarken açıklama alanları KİLİTLİ: yarım
   dolmuş bir listede yazmaya başlayıp üstüne öneri düşmesi, yazılanın
   kaybolması demek olurdu. */
const DG_ONERI_NOTU = "Öneriler gelince açıklamalar düzenlenebilir. Beklemek "
    + "istemezseniz İptal ile durdurup kendiniz yazabilirsiniz.";
const DG_ONERI_ARALIK = 1500;      // yoklama aralığı (ms)
const DG_KALIP = {
    haric: "%s Kolonu Tanımsız Bırak ve Devam Et",
    ekle:  "%s Kolonu Sözlüğe Ekle ve Devam Et",
    karma: "Seçimleri Uygula ve Devam Et",
    bos:   "Devam Et"
};

/* POST /mesaj'in "mesaj" alani: insan tarafinda okunabilir TEK satir.
   Sessiz gider - kullanici bir cumle yazmadi, bir form doldurdu. */
function dogrulamaOzetMetni(haricSayisi, ekleSayisi, duzeltSayisi) {
    const parcalar = [];
    if (haricSayisi) parcalar.push(ftBinlik(haricSayisi) + " kolon tanımsız bırakıldı");
    if (ekleSayisi)  parcalar.push(ftBinlik(ekleSayisi) + " kolon sözlüğe eklendi");
    if (duzeltSayisi) parcalar.push(ftBinlik(duzeltSayisi) + " tanım düzeltildi");
    return parcalar.length ? parcalar.join(", ") : "Girdi doğrulama onaylandı.";
}

function dogrulamaKartiEkle(alan, blok, yerine) {
    /* yerine: verilirse yeni kart bu kartın YERİNE konur (geçmişten çizilen
       kartın güncel kararlarla yeniden kurulması). Verilmezse kart adımın
       kabına eklenir. Kartın ait olduğu adım: karar yalnız bu adım
       ekrandayken uygulanır. */
    const kartAdim = (blok && blok.adim) || "";
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
    /* Gelmezse hic cizilmez. */
    if (alan.aciklama) {
        const ack = document.createElement("div");
        ack.className = "secim-aciklama dg-aciklama";
        metinYaz(ack, alan.aciklama);
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
            metinYaz(et, o.etiket);
            /* Sayının arkasındaki adlar "i" içinde. */
            if (o.bilgi) et.appendChild(bolmeBilgiSimgesi(o.bilgi, o.etiket));
            blok.appendChild(et);

            const dg = document.createElement("div");
            dg.className = "dg-ozet-deger";
            dg.textContent = degerGoster(o.deger);
            /* Uzun ad kisaltiliyor; tamami ipucunda kalsin */
            dg.title = duzMetin(o.deger);
            blok.appendChild(dg);

            (o.alt || []).forEach(a => {
                const s = document.createElement("div");
                s.className = "dg-ozet-alt";
                metinYaz(s, a);
                blok.appendChild(s);
            });
            oz.appendChild(blok);
        });
        kart.appendChild(oz);
    }
    if (alan.uyari) kart.appendChild(elYap("div", "dg-oneri-hata", tireSade(alan.uyari)));

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
        metinYaz(mt, alan.kapsam.metin);
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

        const tbas = document.createElement("div");
        tbas.className = "dg-tablo-bas";

        const tb = document.createElement("div");
        tb.className = "dg-tablo-baslik";
        metinYaz(tb, tanimsiz.baslik);
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
        /* Toplu düğmeler TABLONUN HEMEN ÜSTÜNDE. Aşağıda,
           tablodan hemen önce ekleniyor. */
        kart.appendChild(tbas);

        /* SOZLESME7 §2: arka uc TEK not satiri gonderir (tanimsiz["not"]). */
        if (tanimsiz["not"]) {
            const nt = document.createElement("div");
            nt.className = "dg-not dg-cizgisiz";
            metinYaz(nt, tanimsiz["not"]);
            kart.appendChild(nt);
        }
        /* ZORUNLU TANIM UYARISI: hedef, kimlik ve dönem kolonunun
           sözlük tanımı şart. Kutuları kilitli işaretli geliyor;
           kullanıcı SEBEBİNİ de okusun. */
        if (tanimsiz.zorunlu_not) {
            const zn = document.createElement("div");
            zn.className = "dg-not dg-zorunlu-not dg-cizgisiz";
            metinYaz(zn, tanimsiz.zorunlu_not);
            kart.appendChild(zn);
        }
        /* Öneri alınamayan grup varsa NEDENİ burada.  Kullanıcı boş açıklamaların neden boş olduğunu
           bilmeli. */
        if (tanimsiz.oneri_hata) {
            const oh = document.createElement("div");
            oh.className = "dg-oneri-hata";
            metinYaz(oh, tanimsiz.oneri_hata);
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
        /* Dort kolon, SIRASIYLA (SOZLESME7 §2). Baslik Buyuk Harfi
           (§1): tablo basliklarinda her kelime buyuk baslar. */
        /* Kolon başlığı "Seç". */
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
        /* AİLE: adı yalnız sayılarla ayrılan kolonlar bir başlığın altında
           alt alta (arka uç sırayı aile aile gönderir). */
        const aileUyeleri = {};
        (tanimsiz.satirlar || []).forEach(sat => {
            if (sat.aile) (aileUyeleri[sat.aile] = aileUyeleri[sat.aile] || []).push(String(sat.kolon));
        });
        const kolonSirasi = {};
        let sonAile = "";
        (tanimsiz.satirlar || []).forEach(sat => {
            const aileK = sat.aile && (aileUyeleri[sat.aile] || []).length > 1 ? sat.aile : "";
            if (aileK && aileK !== sonAile) {
                const bt = elYap("tr", "dg-aile-bas-satir");
                const btd = elYap("td");
                btd.colSpan = 4;
                const bk = elYap("div", "dg-aile-bas");
                bk.appendChild(elYap("span", "dg-aile-etiket", "Aile"));
                bk.appendChild(elYap("b", "dg-aile-ad", ackAileAdi(aileK)));
                bk.appendChild(elYap("span", "dg-aile-sayi", ftBinlik(aileUyeleri[aileK].length) + " kolon"));
                bk.appendChild(bolmeBilgiSimgesi(
                    "Bu kolonların adı yalnız sayılarla ayrılır. Dil modeli aileden bir kolonun "
                    + "tanımını yazar; diğerlerine sayılar değiştirilerek aktarılır (satırda «Aileden»).\n\n"
                    + "Aktarım güvenli değilse kolon dil modeline ayrıca sorulur: tanımda adda geçmeyen "
                    + "bir sayı varsa ya da dönemin anlamı değere özelse (saat 00 ile 06 arası gece, "
                    + "06 ile 12 arası sabah gibi).\n\n"
                    + "Bir kolonun açıklamasını değiştirince altında «Ailenin N kolonuna uygula» düğmesi "
                    + "çıkar; düzeltme kardeşlere sayıları değiştirilerek uygulanır.", "Aile"));
                btd.appendChild(bk);
                bt.appendChild(btd);
                tbody.appendChild(bt);
            }
            sonAile = aileK;
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
            tr.className = "dg-satir" + (aileK ? " dg-aile-uye" : "");
            tr.dataset.kolon = durum.kolon;
            kolonSirasi[durum.kolon] = i;

            const tdK = document.createElement("td");
            tdK.className = "dg-kolon";
            tdK.appendChild(document.createTextNode(durum.kolon));
            tdK.title = durum.kolon;
            /* ONAYLI HAFIZADAN DOLDU: dil modeli çağrılmadı; metin daha
               önce onaylanmış tanım. Kaynağı satırda yazar. */
            if (sat.oneri_kaynak === "hafiza") hafizaCipi(tdK, tr, sat.hafiza_veri_seti);
            if (sat.oneri_kaynak === "aile") aileCipi(tdK, tr, sat.aile_kaynagi);
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
            metinYaz(tdT, sat.tip);
            tr.appendChild(tdT);

            /* Aciklama duzenlenebilir: oneri ile dolu gelir, kullanici
               ustune yazabilir. Oneri yoksa (oneri_kaynak "yok") bos. */
            const tdA = document.createElement("td");
            tdA.className = "dg-aciklama-hucre";
            /* ÇOK SATIRLI: kutu içeriğe göre uzar, uzun açıklama kesilmez.
               Enter yeni satır açmaz. */
            const giris = document.createElement("textarea");
            giris.rows = 1;
            giris.className = "dg-giris dg-metin";
            /* Yükseklik = içerik + kenarlık; genişlik değişince ("i"
               eklenince, pencere daralınca) yeniden ölçülür. */
            /* Toplu ölçüm (boylaPlanla): öneriler yüzlerce satıra aynı
               anda gelince de sayfa tek seferde yerleşir. Yazarken
               (input) yalnız bu kutu hemen ölçülür. */
            giris._boylaHemen = () => {
                if (!giris.isConnected) return;
                giris.style.height = "auto";
                const kenar = giris.offsetHeight - giris.clientHeight;
                if (giris.scrollHeight) giris.style.height = (giris.scrollHeight + kenar) + "px";
            };
            giris._boyla = () => boylaPlanla(giris);
            if (BOYLA_GOZCU) BOYLA_GOZCU.observe(giris);
            giris.addEventListener("keydown", e => { if (e.key === "Enter") e.preventDefault(); });
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
            /* AİLEYE UYGULA: açıklama değişince kardeşlere sayıları
               değiştirilerek uygulanır (arka uç tanim_aile_uygula). */
            const kardesler = aileK ? aileUyeleri[aileK].filter(k => k !== durum.kolon) : [];
            let aileBtn = null, aileNot = null;
            const aileDugmesiTazele = () => {
                if (!aileBtn) return;
                const v = giris.value.trim();
                aileBtn.hidden = kart.classList.contains("kilitli") || !v
                    || v === String(giris.dataset.oneriMetin || "").trim();
            };
            giris.addEventListener("input", () => {
                giris._boylaHemen();
                giris._vurgu();
                aileDugmesiTazele();
                if (aileNot) aileNot.hidden = true;
                if (kart.classList.contains("kilitli")) return;
                durumTazele();
            });
            giris._vurgu();
            boylaPlanla(giris);
            /* Açıklama kutusu + öneri gelince "i": açıklamanın nereden
               geldiği (modele giden özet, bağlam, adaylar, modeller). */
            const kapA = elYap("div", "dg-anlam-kap");
            kapA.appendChild(giris);
            tdA.appendChild(kapA);
            if (kardesler.length) {
                const aKap = elYap("div", "dg-aile-uygula");
                aileBtn = elYap("button", "dg-toplu-btn dg-aile-btn",
                                "Ailenin " + ftBinlik(kardesler.length) + " kolonuna uygula");
                aileBtn.type = "button";
                aileBtn.title = "Bu açıklamayı ailedeki öbür kolonlara, adlarındaki sayılar değiştirilerek yazar.";
                aileNot = elYap("div", "dg-aile-not");
                aileNot.hidden = true;
                aileBtn.onclick = () => {
                    if (kart.classList.contains("kilitli")) return;
                    aileBtn.disabled = true;
                    fetch(getWebAppBackendUrl("tanim_aile_uygula"), {
                        method: "POST", headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ oturum_id: OTURUM_ID, kolon: durum.kolon,
                                               aciklama: giris.value, hedefler: kardesler })
                    })
                    .then(r => r.json())
                    .then(d => {
                        aileBtn.disabled = false;
                        if (!d || d.tamam !== true) {
                            aileNot.textContent = "Uygulanamadı: " + tireSade((d && d.hata) || "bilinmeyen hata") + ".";
                            aileNot.hidden = false;
                            return;
                        }
                        const metinler = d.metinler || {};
                        let n = 0;
                        Object.keys(metinler).forEach(k => {
                            const j = kolonSirasi[k];
                            if (j === undefined || !girisler[j] || girisler[j].disabled) return;
                            const hg = girisler[j];
                            hg.value = tireSade(metinler[k]);
                            hg.dataset.dolduruldu = "1";
                            if (hg._boyla) hg._boyla();
                            const hs = durumlar[j];
                            if (hs && !hs.zorunlu && !hs.kilitli && durum.islem === "ekle" && hs.islem !== "ekle") {
                                hs.islem = "ekle";
                                kutuCiz(j);
                            }
                            if (hg._vurgu) hg._vurgu();
                            n++;
                        });
                        const atl = d.atlanan || {};
                        const atlAd = Object.keys(atl);
                        aileNot.textContent = ftBinlik(n) + " kolona uygulandı."
                            + (atlAd.length ? " " + ftBinlik(atlAd.length) + " kolona uygulanamadı: "
                               + atlAd.map(k => k + " (" + tireSade(atl[k]) + ")").join("; ") + "." : "");
                        aileNot.hidden = false;
                        durumTazele();
                    })
                    .catch(e => {
                        aileBtn.disabled = false;
                        aileNot.textContent = "Uygulanamadı: " + e + ".";
                        aileNot.hidden = false;
                    });
                };
                aKap.append(aileBtn, aileNot);
                tdA.appendChild(aKap);
                aileDugmesiTazele();
            }
            tr.appendChild(tdA);
            girisler.push(giris);

            /* SOZLUGE EKLE: isaretli -> sozluge eklenir, isaretsiz ->
               haric tutulur. Kutu kendi durumunu gosterir, etiket
               okumaya gerek yok. */
            const tdI = document.createElement("td");
            tdI.className = "dg-ekle-hucre";
            const kutu = document.createElement("input");
            kutu.type = "checkbox";
            kutu.className = "dg-ekle";
            kutu.setAttribute("aria-label", durum.kolon + " sözlüğe eklensin");
            if (durum.zorunlu) kutu.disabled = true;
            if (durum.kilitli) {
                kutu.disabled = true;
                kutu.title = duzMetin(sat.kilit_sebebi || "");
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
                + " kolon daha tanımsız; listede gösterilmiyor ve tanımsız kalacak.";
            kart.appendChild(kalan);
        }
    }

    /* ---- 5') Tanımsız Kolonlar (01.2.3.1) ----
       Sözlükte hâlâ tanımı olmayan kolonlar: işaretli satır AMP_VERISETI'nden
       ve AMP_SOZLUK'ten çıkarılır, işaretsiz satır veri setinde kalır ve
       sözlükte tanımı boş durur. Kilitli satır (tek değerli) hep çıkar.
       Her satır işaretli gelir. Satırda kolonun en sık 10 değeri (adediyle)
       ve sayısal kolonda min, maks, medyan, ortalama durur: hepsi tam
       tablo profilinden. */
    const cikar = alan.cikar || null;
    const cDurumlar = [];            /* {kolon, islem, kilitli, kutu, tr} */
    if (cikar) {
        const cbas = elYap("div", "dg-tablo-bas");
        const cb = elYap("div", "dg-tablo-baslik");
        metinYaz(cb, cikar.baslik || "");
        cbas.appendChild(cb);
        kart.appendChild(cbas);
        if (cikar["not"]) {
            const nt = elYap("div", "dg-not dg-cizgisiz");
            metinYaz(nt, cikar["not"]);
            kart.appendChild(nt);
        }
        const cUst = elYap("div", "dg-tablo-ust");
        const cToplu = elYap("div", "dg-toplu");
        [["cikar", "Tümünü Seç"], ["kalsin", "Tümünü Temizle"]].forEach(([islem, etiket]) => {
            const b = elYap("button", "dg-toplu-btn", etiket);
            b.type = "button";
            b.onclick = () => {
                if (kart.classList.contains("kilitli")) return;
                cDurumlar.forEach(c => { if (!c.kilitli) { c.islem = islem; cKutuCiz(c); } });
                durumTazele();
            };
            cToplu.appendChild(b);
            topluBtnleri.push(b);
        });
        cUst.appendChild(cToplu);
        kart.appendChild(cUst);

        const cSar = elYap("div", "dg-tablo-sar");
        const ct = elYap("table", "dg-tablo dg-cikar-tablo");
        /* Kolonlar: [başlık, genişlik sınıfı, hizalama, ipucu]. Genişlik
           <col> sınıfından gelir (CSS sıraya bağlı değil); başlık ve
           hücre aynı hizada durur. Min, Med, Mean, Max yan yana. */
        const KOLONLAR = [
            ["Değişken", "tk-ad", ""], ["Tip", "tk-tip", ""],
            ["Boş Oranı", "tk-oran", "tk-sag", "Boş hücrelerin bütün satırlara oranı (tam tablo)."],
            ["Tekrar Oranı", "tk-oran", "tk-sag", "Değeri kendinden önceki bir satırla aynı olan satırların bütün satırlara oranı; boş hücre de değer sayılır (tam tablo). Adedi ipucunda."],
            ["Tekil Değer", "tk-oran", "tk-sag", "Farklı değer sayısı (boş hariç, tam tablo)."],
            ["En Sık Değerler", "tk-deger", "", "En sık 10 değer; parantez içinde o değeri taşıyan satır adedi (tam tablo)."],
            ["Min", "tk-ist", "tk-sag"], ["Med", "tk-ist", "tk-sag", "Medyan"],
            ["Mean", "tk-ist", "tk-sag", "Ortalama (sonlu değerler)"], ["Max", "tk-ist", "tk-sag"],
            ["Çıkar", "tk-cikar", "tk-orta"]];
        const cg = document.createElement("colgroup");
        KOLONLAR.forEach(([, gen]) => { const col = document.createElement("col"); col.className = gen; cg.appendChild(col); });
        ct.appendChild(cg);
        const cth = document.createElement("thead");
        const chr = document.createElement("tr");
        KOLONLAR.forEach(([h, , hiza, ipucu]) => {
            const th = elYap("th", hiza, h);
            if (ipucu) th.title = ipucu;
            chr.appendChild(th);
        });
        cth.appendChild(chr);
        ct.appendChild(cth);
        const cTbody = document.createElement("tbody");
        const eksikler = new Set();     /* eski profilde olmayan alanlar */
        /* GRUPLAR: Tamamen Boş, Tek Değerli (kilitli, hep çıkar), Sözlükte
           Tanımı Bulunmayan; her grup bir başlık satırının altında. */
        const cGruplar = {};
        (cikar.gruplar || []).forEach(g => { cGruplar[g.anahtar] = g; });
        let cSonGrup = "";
        (cikar.satirlar || []).forEach(sat => {
            const ad = String(sat.kolon === null || sat.kolon === undefined ? "" : sat.kolon);
            const g = cGruplar[sat.grup];
            if (g && sat.grup !== cSonGrup) {
                const gtr = elYap("tr", "dg-cikar-grup-satir");
                const gtd = elYap("td");
                gtd.colSpan = KOLONLAR.length;
                const gk = elYap("div", "dg-cikar-grup");
                gk.appendChild(elYap("b", "", g.baslik));
                gk.appendChild(elYap("span", "dg-aile-sayi", ftBinlik(g.sayi) + " kolon"));
                if (g.aciklama) gk.appendChild(bolmeBilgiSimgesi(g.aciklama, g.baslik));
                gtd.appendChild(gk);
                gtr.appendChild(gtd);
                cTbody.appendChild(gtr);
            }
            cSonGrup = sat.grup || "";
            const tr = elYap("tr", "dg-satir dg-cikar-satir");
            tr.dataset.kolon = ad;
            const tdK = elYap("td", "dg-kolon", ad);
            tdK.title = ad + (sat.sorun ? "\n" + duzMetin(sat.sorun) : "");
            /* Sorunlu kolon sözlükte de tanımsızsa bunu da söyler. */
            if (sat.sorun && sat.tanimsiz) {
                const tc = elYap("span", "dg-rol", "Tanımsız");
                tc.title = "Sözlükte tanımı da yok.";
                tdK.appendChild(tc);
            }
            tr.appendChild(tdK);
            const tdT = elYap("td", "dg-tip");
            metinYaz(tdT, sat.tip || "");
            tr.appendChild(tdT);
            tr.appendChild(elYap("td", "dg-sayi-hucre tk-sag",
                sat.null_oran === null || sat.null_oran === undefined ? "" : ftOran(sat.null_oran)));
            tr.appendChild(tanimsizTekrarHucresi(sat));
            tr.appendChild(elYap("td", "dg-sayi-hucre tk-sag",
                sat.tekil === null || sat.tekil === undefined ? "" : ftBinlik(sat.tekil)));
            tr.appendChild(tanimsizDegerHucresi(sat));
            ["min", "medyan", "ortalama", "max"].forEach(alan => {
                const td = elYap("td", "dg-sayi-hucre tk-sag");
                const v = sat[alan];
                const yok = v === null || v === undefined || v === "";
                if (sat.sayisal && !sat.gizli) {
                    metinYaz(td, dagSayi(v));
                    if (alan === "ortalama" && yok) eksikler.add("ortalama");
                } else if (sat.tarih && !sat.gizli && alan !== "ortalama") {
                    metinYaz(td, yok ? BOS_SIMGE : tarihGoster(v));
                    if (alan === "medyan" && yok) eksikler.add("tarih medyanı");
                }
                if (!yok && td.textContent) td.title = String(v);
                tr.appendChild(td);
            });
            const tdI = elYap("td", "dg-ekle-hucre");
            const kutu = document.createElement("input");
            kutu.type = "checkbox";
            kutu.className = "dg-ekle";
            kutu.setAttribute("aria-label", ad + " veri setinden çıkarılsın");
            const c = { kolon: ad, kilitli: !!sat.kilitli, kutu: kutu, tr: tr,
                        islem: sat.kilitli ? "cikar" : (sat.islem === "cikar" ? "cikar" : "kalsin") };
            if (c.kilitli) {
                kutu.disabled = true;
                kutu.title = duzMetin(sat.kilit_sebebi || "");
                tdI.title = kutu.title;
                tr.classList.add("dg-rol-kilitli");
            }
            kutu.addEventListener("change", () => {
                if (kart.classList.contains("kilitli") || c.kilitli) { cKutuCiz(c); return; }
                c.islem = kutu.checked ? "cikar" : "kalsin";
                cKutuCiz(c);
                durumTazele();
            });
            tdI.appendChild(kutu);
            tr.appendChild(tdI);
            cTbody.appendChild(tr);
            cDurumlar.push(c);
            cKutuCiz(c);
        });
        ct.appendChild(cTbody);
        cSar.appendChild(ct);
        kart.appendChild(cSar);
        if (eksikler.size) {
            const ad = [...eksikler].join(" ve ");
            const nt = elYap("div", "dg-not dg-cizgisiz");
            metinYaz(nt, "Bu çalışmanın veri seti profili " + ad + " hesaplanmadan önce çıkarıldı. "
                + ilkHarfBuyuk(ad) + ", profili yeni çıkarılan çalışmalarda görünür.");
            kart.appendChild(nt);
        }
    }
    function cKutuCiz(c) {
        c.kutu.checked = c.islem === "cikar";
        c.tr.dataset.islem = c.islem;
    }

    /* ---- 5'') Sözlük Birleştirme (01.2.1.1) ----
       Seçilen sözlüklerde tanımı farklı olan kolonlar. Her satırda
       sözlüklerin tanımları seçenek olarak durur; en altta "Kendim
       yazayım". Seçilen tanım AMP_SOZLUK'e gider. */
    const birlesim = alan.birlesim || null;
    const bDurumlar = [];          /* {kolon, kaynak, metin, radyolar, giris, tr} */
    if (birlesim) {
        const bbas = elYap("div", "dg-tablo-bas");
        const bb = elYap("div", "dg-tablo-baslik");
        metinYaz(bb, birlesim.baslik || "");
        bbas.appendChild(bb);
        kart.appendChild(bbas);
        if (birlesim["not"]) {
            const nt = elYap("div", "dg-not dg-cizgisiz");
            metinYaz(nt, birlesim["not"]);
            kart.appendChild(nt);
        }
        const bUst = elYap("div", "dg-tablo-ust");
        const bToplu = elYap("div", "dg-toplu");
        (birlesim.sozlukler || []).forEach(sz => {
            const b = elYap("button", "dg-toplu-btn", "Tümünde " + sz + " Tanımı");
            b.type = "button";
            b.title = "Tanımı " + sz + " sözlüğünde olan her kolonda o tanım seçilir.";
            b.onclick = () => {
                if (kart.classList.contains("kilitli")) return;
                bDurumlar.forEach(d => {
                    if (d.secenekler.some(x => x.sozluk === sz)) { d.kaynak = sz; bCiz(d); }
                });
                durumTazele();
            };
            bToplu.appendChild(b);
            topluBtnleri.push(b);
        });
        bUst.appendChild(bToplu);
        kart.appendChild(bUst);

        const bSar = elYap("div", "dg-tablo-sar");
        const bt = elYap("table", "dg-tablo dg-birlesim-tablo");
        const bth = document.createElement("thead");
        const bhr = document.createElement("tr");
        ["Değişken", "Tanım"].forEach(h => bhr.appendChild(elYap("th", "", h)));
        bth.appendChild(bhr);
        bt.appendChild(bth);
        const bTbody = document.createElement("tbody");
        const grupAdi = "dgb-" + Math.random().toString(36).slice(2);
        (birlesim.satirlar || []).forEach((sat, si) => {
            const ad = String(sat.kolon === null || sat.kolon === undefined ? "" : sat.kolon);
            const tr = elYap("tr", "dg-satir dg-birlesim-satir");
            tr.dataset.kolon = ad;
            const tdK = elYap("td", "dg-kolon", ad);
            tdK.title = ad;
            tr.appendChild(tdK);
            const tdS = elYap("td", "");
            const kap = elYap("div", "dg-birlesim-secenekler");
            tdS.appendChild(kap);
            const d = { kolon: ad, secenekler: sat.secenekler || [], kaynak: String(sat.kaynak || ""),
                        metin: String(sat.metin || ""), radyolar: [], giris: null, tr: tr };
            const ad_ = grupAdi + "-" + si;
            d.secenekler.forEach(x => {
                const lb = elYap("label", "dg-birlesim-secenek");
                const r = document.createElement("input");
                r.type = "radio";
                r.name = ad_;
                r.value = x.sozluk;
                r.addEventListener("change", () => {
                    if (kart.classList.contains("kilitli")) { bCiz(d); return; }
                    d.kaynak = x.sozluk; bCiz(d); durumTazele();
                });
                const kay = elYap("span", "dg-birlesim-kaynak", x.sozluk);
                kay.title = x.sozluk;
                lb.append(r, kay, elYap("span", "dg-birlesim-metin", tireSade(x.tanim || "")));
                kap.appendChild(lb);
                d.radyolar.push(r);
            });
            const lb = elYap("label", "dg-birlesim-secenek dg-birlesim-elle");
            const r = document.createElement("input");
            r.type = "radio";
            r.name = ad_;
            r.value = "";
            const g = document.createElement("input");
            g.type = "text";
            g.className = "dg-giris dg-birlesim-giris";
            g.placeholder = "Tanımı kendiniz yazın";
            g.setAttribute("aria-label", ad + " tanımı");
            g.value = d.metin;
            r.addEventListener("change", () => {
                if (kart.classList.contains("kilitli")) { bCiz(d); return; }
                d.kaynak = ""; bCiz(d); g.focus(); durumTazele();
            });
            /* Kutuya yazmak bu seçeneği seçer. */
            g.addEventListener("input", () => {
                if (kart.classList.contains("kilitli")) return;
                d.metin = g.value; d.kaynak = ""; bCiz(d); durumTazele();
            });
            lb.append(r, elYap("span", "dg-birlesim-kaynak", "Kendim yazayım"), g);
            kap.appendChild(lb);
            d.radyolar.push(r);
            d.giris = g;
            tr.appendChild(tdS);
            bTbody.appendChild(tr);
            bDurumlar.push(d);
            bCiz(d);
        });
        bt.appendChild(bTbody);
        bSar.appendChild(bt);
        kart.appendChild(bSar);
    }
    function bCiz(d) {
        d.radyolar.forEach(r => { r.checked = r.value === d.kaynak; });
        const eksik = !d.kaynak && !d.metin.trim();
        d.giris.classList.toggle("dg-noksan", eksik);
        d.tr.classList.toggle("dg-noksan", eksik);
    }

    /* ---- 5a) Sözlük ve Kolon Adı Kontrolü'nün dört adımı (01.2.4.1 Dönem
       Bilgisi, 01.2.4.2 Ad Parçaları, 01.2.4.3 Kolon Kartları, 01.2.4.4
       Kolon Adları). Ayrı adımlar, kendi kartlarında; karar birincil
       düğmeyle adımla birlikte gider (alan.adim). */
    const adimModu = alan.adim || "";
    /* TASLAK: Dönem Bilgisi, Ad Parçaları ve Kolon Adları kartı değişince
       onaylanmamış son hâl proje hafızasına gider (bekleyerek, aynı hâl
       bir kez); 01.2.4'te önceki kontrol seçilince kaldığı yerden açılır. */
    let taslakZ = null, taslakSon = "", dokunuldu = false;
    /* Yalnız kullanıcı kartta bir şey değiştirdiyse (açılış ve yoklama
       taslak sayılmaz). */
    ["input", "change", "click"].forEach(t => kart.addEventListener(t, () => { dokunuldu = true; }, true));
    const taslakPlanla = () => {
        if (!dokunuldu || (blok && blok.kilit) || !["donem", "parca", "kolon_ad"].includes(adimModu)) return;
        clearTimeout(taslakZ);
        taslakZ = setTimeout(() => {
            if (!kart.isConnected || kart.classList.contains("kilitli")) return;
            let karar;
            try {
                karar = adimModu === "donem" && donErisim
                    ? { donem: donErisim.deger(), donem_ayrik: donErisim.ayrik() }
                    : adimModu === "parca" && parcaErisim ? { parca: parcaErisim.deger() }
                    : adimModu === "kolon_ad" && kolonAdErisim ? { kolon_ad: kolonAdErisim.deger() }
                    : null;
            } catch (e) { karar = null; }
            if (!karar) return;
            const govde = JSON.stringify({ oturum_id: OTURUM_ID, adim: adimModu, karar });
            if (govde === taslakSon) return;
            taslakSon = govde;
            fetch(getWebAppBackendUrl("kontrol_taslak"), {
                method: "POST", headers: { "Content-Type": "application/json" }, body: govde
            }).catch(() => { taslakSon = ""; });
        }, 1500);
    };
    /* Dönem Bilgisi (01.2.4.1) */
    const donErisim = alan.donem
        ? donemBolumuEkle(kart, alan.donem, !!(blok && blok.kilit),
                          () => { durumTazele(); taslakPlanla(); }) : null;
    /* Kolon Kartları (01.2.4.3) */
    const acikErisim = alan.aciklama_duzen
        ? aciklamaBolumuEkle(kart, alan.aciklama_duzen, !!(blok && blok.kilit), () => durumTazele())
        : null;
    /* Ad Parçaları (01.2.4.2) */
    const parcaErisim = alan.parca
        ? parcaBolumuEkle(kart, alan.parca, !!(blok && blok.kilit),
                          () => { durumTazele(); taslakPlanla(); }) : null;
    /* Kaldırılan Kısaltma Sözlüğü'nün eski kayıttaki kartı: yalnız not. */
    if (alan.kisaltma) kart.appendChild(elYap("div", "dg-kisa-aciklama",
        "Bu kart önceki sürümle oluşturuldu; ayrıntısı gösterilmiyor."));
    /* Kolon Adları: onaylı parçaların standart yazılışlarıyla kodla
       kurulan adlar (yalnız AMP kopyalarında uygulanır). */
    const kolonAdErisim = alan.kolon_ad
        ? kolonAdBolumuEkle(kart, alan.kolon_ad, !!(blok && blok.kilit), !!adimModu,
                            () => { durumTazele(); taslakPlanla(); }) : null;
    /* Eski kayıtlardaki Kısaltma Birleştirme kartı (geçmişten çizim):
       yalnız not. */
    if (alan.birlesik) kart.appendChild(elYap("div", "dg-kisa-aciklama",
        "Bu kart önceki sürümle oluşturuldu; ayrıntısı gösterilmiyor."));

    /* ---- 5b) Sözlükteki tanımların kontrolü ----
       sözlükte tanımı OLAN kolonların tanımı da birden
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
    /* İSTEĞE BAĞLI KONTROL: kart "Tanımları Kontrol
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
        metinYaz(kHataEl, kontrol.hata || "");
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
        kUst.appendChild(dgLejant([["dg-l-llm", "Dil Modeli Önerisi"],
                                   ["dg-l-hafiza", "Onaylı Tanım"],
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
        const boyla = () => { giris.style.height = "auto"; giris.style.height = giris.scrollHeight + "px"; };
        giris._boyKenar = false;
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
        boylaPlanla(giris);
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
            metinYaz(kHataEl, kayit.kontrol_hata);
            kHataEl.hidden = false;
        }
        kontrolBekliyor = !!kontrol.bekle && (durumK === "bekliyor" || durumK === "calisiyor");
        durumTazele();
    }

    /* ---- 5c) İşlem satırı: açıklama önerileri sürerken süre ve İptal
       (Kolon Kartları'ndakiyle aynı). İptal önerileri durdurur, gelenler
       kalır, kart kilidi açılır. ---- */
    const oIler = elYap("div", "islem-satiri dg-ilerleme");
    oIler.setAttribute("role", "status");
    const oIlerMetin = elYap("span", "islem-sure", "");
    const oIptal = elYap("button", "islem-iptal", "İptal");
    oIptal.type = "button";
    oIptal.title = "Dil modelini durdur; gelen öneriler kalır";
    oIler.append(oIlerMetin, oIptal);
    kart.appendChild(oIler);
    /* SÜRE: başlangıç anı bir kez sabitlenir (sunucunun bildirdiği geçen
       süreden), sonra saatten hesaplanır; yoklama ile ileri geri oynamaz. */
    let oBas = Date.now(), oBasSabit = false, oSayac = null, oBiten = 0, oToplam = 0;
    function oIlerYaz() {
        const gecen = Math.max(0, Math.floor((Date.now() - oBas) / 1000));
        oIlerMetin.textContent = "İşlem Devam Ediyor · Açıklama Önerileri · "
            + ftBinlik(oBiten) + " / " + ftBinlik(oToplam) + " Kolon · " + sureBicim(gecen);
    }
    const oDusun = dusunmeIzleyici(kart);
    function oIlerGoster(acik) {
        oIler.classList.toggle("gorunur", acik);
        oDusun(acik && kart.isConnected);
        if (acik && !oSayac) {
            oSayac = setInterval(() => {
                if (!kart.isConnected) { clearInterval(oSayac); oSayac = null; oDusun(false); return; }
                oDusun(true);
                oIlerYaz();
            }, 1000);
        } else if (!acik && oSayac) { clearInterval(oSayac); oSayac = null; }
        if (acik) oIlerYaz();
    }
    oIptal.onclick = () => {
        if (!alan.oneri_is) return;
        oIptal.disabled = true;
        oIptal.textContent = "İptal ediliyor";
        fetch(getWebAppBackendUrl("oneri_iptal"), {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify(ftKimlikGovdesi({ is: String(alan.oneri_is) }))
        })
        .then(r => r.json())
        .then(() => { clearTimeout(oneriZaman); oneriYokla(String(alan.oneri_is)); })
        .catch(() => { oIptal.disabled = false; oIptal.textContent = "İptal"; });
    };

    /* ---- 6) Gerekce satiri + dugmeler ---- */
    const gerekce = document.createElement("div");
    gerekce.className = "dg-gerekce";
    gerekce.hidden = true;
    kart.appendChild(gerekce);

    /* YALNIZ BIRINCIL DUGME. */
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
            gonder(ozet, false, { dogrulama: { kontrol: [], atla: true, adim: kartAdim } });
        };
        dugmeler.appendChild(atlaBtn);
        /* Başlamadan önce ana düğmenin yapacağı bir şey yok. */
        birincil.hidden = !!kontrol.baslamadi;
    } else if (alan.atla) {
        /* İsteğe bağlı adım ("Değiştirmeden devam" düğmesi olan kart). */
        atlaBtn = elYap("button", "secim-onay ikincil dg-kontrol-atla", tireSade(alan.atla));
        atlaBtn.type = "button";
        atlaBtn.onclick = () => {
            if (mesgul || kart.classList.contains("kilitli")) return;
            const ozet = adimModu === "kolon_ad" ? "Yeni adlar uygulanmadan devam edildi"
                : "Açıklamalar değiştirilmeden devam edildi";
            kartiKilitle(ozet);
            gonder(ozet, false, { dogrulama: { atla: true, adim: kartAdim } });
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
                metinYaz(kHataEl, (d && d.hata) || "Kontrol başlatılamadı.");
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
            kDurumEl.textContent = "Tanım kontrolü başlıyor";
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

        /* Sözlük Birleştirme: tanımı boş kalan satır onayı durdurur. */
        if (birlesim) {
            const eks = bDurumlar.filter(d => !d.kaynak && !d.metin.trim()).length;
            metinYaz(birincil, kalip.bos);
            birincil.disabled = eks > 0;
            gerekce.hidden = eks === 0;
            gerekce.textContent = eks ? ftBinlik(eks) + " satırda «Kendim yazayım» seçili ama "
                + "tanım boş: yazın ya da bir sözlüğün tanımını seçin." : "";
            return;
        }
        /* Tanımsız Kolonlar: etiket çıkarılacak kolon sayısıyla. */
        if (cikar) {
            const n = cDurumlar.filter(c => c.islem === "cikar").length;
            metinYaz(birincil, n ? kalip.cikar.replace("%s", ftBinlik(n)) : kalip.kalsin);
            birincil.disabled = false;
            gerekce.hidden = true;
            return;
        }

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
           onlari VARSAYILAN islemle (hariç) uyguluyor. */
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
        metinYaz(birincil, etiket);

        /* Aciklamasi bos "sözlüğe ekle" satiri varsa kaydetmek anlamsiz:
           dugme pasif ve NEDENI ekranda yaziyor. */
        if (oneriBekliyor) return;          // kilit mesajı ekranda kalsın
        if (kontrolBekliyor) {
            birincil.disabled = true;
            gerekce.hidden = true;
            return;
        }
        /* KISALTMA SÖZLÜĞÜ: dil modeli kontrolü bitmeden
           onaylanamaz; yalnız sözlükten çıkan anlamlar çalışmaya girmesin.
           Beklemek istemeyen "Kısaltmaları Onaylamadan Devam Et"i kullanır. */
        /* DÖNEM BİLGİSİ: model yorumu bitmeden, anlamı boş satır ve
           kaydedilmemiş satır kaldıkça onaylanamaz. */
        if (adimModu === "donem" && donErisim) {
            const bek = donErisim.bekliyor(), eks = donErisim.eksik(), yok = donErisim.adlardaYok();
            const kon = donErisim.kontrol(), kay = donErisim.kaydedilmemis();
            const dur = bek || eks > 0 || yok > 0 || kon > 0 || kay > 0;
            birincil.disabled = dur;
            gerekce.hidden = !dur;
            gerekce.textContent = bek ? "Dil modeli yorumunu bitirince onaylanabilir."
                : yok > 0 ? ftBinlik(yok) + " satırdaki kalıp kolon adlarında geçmiyor: bu adımda "
                    + "yalnız adlarda geçen dönem parçaları eklenir. Satırdaki «Yalnız Hafızaya "
                    + "Ekle» ile hafızaya yazabilir ya da «Çıkar» ile silebilirsiniz."
                : eks > 0 ? ftBinlik(eks) + " satırda anlam (elle satırda kalıp) boş: anlamını "
                    + "yazın ya da satırı çıkarın. Tabloda kalan her satır hafızaya kaydedilir."
                : kon > 0 ? ftBinlik(kon) + " satırda yer tutucu geçersiz: satırdaki «Kontrol» "
                    + "notuna bakın."
                : kay > 0 ? ftBinlik(kay) + " satır kaydedilmedi: onaylamadan önce her satırı "
                    + "«Kaydet» ile kaydedin ya da satırı çıkarın."
                : "";
            return;
        }
        /* AÇIKLAMA DÜZENLEME: dil modeli düzenlerken onaylanamaz (İptal
           ile durdurulursa düzenlenmeyenlerin orijinali kalır). Cevapsız
           soru onayı durdurmaz; bilgi olarak yazar. */
        if (adimModu === "aciklama" && acikErisim) {
            const bek = acikErisim.bekliyor(), s = acikErisim.sayac();
            const durdu = acikErisim.durduruldu();
            const onaysiz = Number(s.onaysiz || 0);
            /* Onay bekleyen varsa etkin aşamaya göre tek adım yazılır. */
            const as = acikErisim.asama ? acikErisim.asama() : null;
            const asamaYazi = !as || !as.kalan ? ""
                : "Aşama " + as.n + " / " + as.toplam + " (" + as.ad + "): " + (as.kod === 1
                    ? ftBinlik(as.aile) + " aile onay bekliyor. Yukarıdaki kutularda «Aileyi Onayla»ya basın; "
                      + "kutuda adı yazan kolonları tek tek onaylayın."
                    : as.kod === 2
                    ? ftBinlik(as.kalan) + " kolon onay bekliyor. Yukarıda «Biçim Değişikliklerini Onayla»ya basın."
                    : as.kod === 4
                    ? ftBinlik(as.kalan) + " kolonda soru cevapsız. Sorunun altına cevabınızı yazıp «Cevabı "
                      + "Uygula»ya basın ya da açıklama böyle de doğruysa onaylayın."
                    : as.kod === 5
                    ? ftBinlik(as.kalan) + " kolonda kontrol notu var. Her kolonun notunu okuyup onaylayın."
                    : ftBinlik(as.kalan) + " kolon onay bekliyor. Her kolonu okuyup onay kutusunu işaretleyin.");
            const ev = acikErisim.soruEvresi ? acikErisim.soruEvresi() : null;
            birincil.disabled = bek || onaysiz > 0 || !!ev;
            gerekce.textContent = ev && ev.cevapsiz
                ? "Önce yukarıdaki Toplu Sorular: " + ftBinlik(ev.cevapsiz) + " soru cevap bekliyor. "
                  + "Hepsi cevaplanınca kolonlar açılır."
                : ev && !bek && ev.kaymaSurer
                ? "Dil modeli açıklamaları orijinalleriyle karşılaştırıyor; bitince kolonlar açılır."
                : ev && !bek && ev.kosulSurer && !ev.kayma
                ? "Cevabınızdan Dönem Bilgisi için koşullu anlam çıkarılıyor; bitince kolonlar açılır."
                : ev && !bek && ev.kayma
                ? "Önce yukarıdaki Anlamı Kayan Aileler: " + ftBinlik(ev.kayma) + " aile karar bekliyor."
                : bek
                ? "Dil modeli " + ftBinlik(Number(s.bekleyen || 0)) + " kolonu düzenliyor; bitince "
                  + "onaylanabilir. Beklemek istemezseniz İptal'e basın."
                : onaysiz > 0 ? (asamaYazi || ftBinlik(onaysiz) + " kolon onay bekliyor. Her kolonu "
                  + "kontrol edip onaylayın.")
                : durdu ? ftBinlik(Number(s.bekleyen || 0)) + " kolon düzenlenmedi; onaylarsanız "
                  + "orijinal açıklamaları kalır."
                : Number(s.soru || 0) > 0 ? ftBinlik(Number(s.soru)) + " kolonda cevapsız soru var; "
                  + "o kolonlarda açıklama yalnız kesin bilgiyle yazıldı."
                : "";
            gerekce.hidden = !gerekce.textContent;
            return;
        }
        /* KOLON ADLARI: her aile onaylanmalı; sorunlu ad onaylanamaz. */
        if (adimModu === "kolon_ad" && kolonAdErisim) {
            const on = kolonAdErisim.onaysiz(), sor = kolonAdErisim.sorunlu();
            const ek = kolonAdErisim.ekOnaysiz ? kolonAdErisim.ekOnaysiz() : 0;
            const sk = kolonAdErisim.sonKontrolSuruyor ? kolonAdErisim.sonKontrolSuruyor() : false;
            birincil.disabled = on > 0 || sor > 0 || ek > 0 || sk;
            gerekce.textContent = sk ? "Son kontrol sürüyor: dil modeli parça türlerini yeni adlar ve onaylı "
                    + "açıklamalarla karşılaştırıyor. Bitince adlar gerekirse yeniden kurulur; ailelerin onayını "
                    + "ondan sonra verin."
                : sor > 0 ? ftBinlik(sor) + " yerde ad, kısaltma ya da dönem yazılışı sorunu var."
                : ek > 0 ? "Ada eklenecek " + ftBinlik(ek) + " parça onay bekliyor. Önce yukarıdaki «Ada "
                    + "Eklenecek Parçalar»ı onaylayın; adlar buna göre kurulur."
                : on > 0 ? ftBinlik(on) + " aile onay bekliyor. Her aile için yeni adı ya da eski adın "
                    + "kalmasını onaylayın." : "";
            gerekce.hidden = !gerekce.textContent;
            return;
        }
        /* AD PARÇALARI: dil modeli bitmeden, onaysız satır, eksik ya da
           hatalı satır ve kararsız yazım çifti kaldıkça onaylanamaz. */
        if (adimModu === "parca" && parcaErisim) {
            const bek = parcaErisim.bekliyor(), on = parcaErisim.onaysiz();
            const es = parcaErisim.esBekleyen(), sor = parcaErisim.sorunlu();
            const cak = parcaErisim.cakisma();
            birincil.disabled = bek || on > 0 || es > 0 || sor > 0 || cak;
            gerekce.textContent = bek ? "Dil modeli parçaları yorumlamayı bitirince onaylanabilir. "
                    + "Beklemek istemezseniz İptal'e basın."
                : sor > 0 ? ftBinlik(sor) + " satırda eksik ya da hatalı bilgi var: süzgeçte «Eksik ya da Hatalı»yı seçin."
                : cak ? "Aynı gruptaki çiftlerde adlarda kullanılacak yazılış farklı seçilmiş: Yazım Sorunları'nda birini seçin."
                : on > 0 ? ftBinlik(on) + " parça onay bekliyor. Her parça kontrol edilip onaylanmalı."
                : es > 0 ? ftBinlik(es) + " yazım çifti karar bekliyor (Yazım Sorunları)."
                : "";
            gerekce.hidden = !gerekce.textContent;
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
        cDurumlar.forEach(c => { c.kutu.disabled = kilit || c.kilitli; });
        bDurumlar.forEach(d => { d.radyolar.forEach(r => { r.disabled = kilit; }); d.giris.disabled = kilit; });
        kutular.forEach((k, i) => {
            // Zorunlu satırın kutusu kilit açılsa da pasif kalır.
            k.disabled = kilit || !!(durumlar[i] && durumlar[i].zorunlu);
        });
        topluBtnleri.forEach(b => { b.disabled = kilit; });
        if (parcaErisim) parcaErisim.kilitle(kilit);
        if (kolonAdErisim) kolonAdErisim.kilitle(kilit);
        if (donErisim) donErisim.kilitle(kilit);
        if (acikErisim) acikErisim.kilitle(kilit);
        birincil.disabled = kilit;
    }

    /* Hata olursa kart ESKI ACIK haline doner; kullanicinin yazdigi
       aciklamalar ve secimleri EKRANDA KALIR (input/select/checkbox
       degerlerine dokunulmuyor, yalnizca disabled kalkiyor).
       Kayit sirasinda kart kilitlenir. Dugmenin uzerine "SECILDI"
       gibi bir DURUM YAZILMAZ: etiket ne yaptigini soylemeye devam
       eder, kilidi kartin sonuk gorunumu ve pasif dugme anlatir. */
    /* Karar verildikten sonra rozet NE YAPILDIGINI yazar
       (ör. "2 kolon sözlüğe eklendi."). */
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
    function oneriKilidi(acik, biten, toplam, gecen) {
        oneriBekliyor = !acik;
        girisler.forEach(g => { g.disabled = !acik; });
        topluBtnleri.forEach(b => { b.disabled = !acik; });
        if (!acik) {
            birincil.disabled = true;
            gerekce.hidden = false;
            gerekce.textContent = DG_ONERI_NOTU;
            oBiten = biten || 0; oToplam = toplam || 0;
            if (!oBasSabit && gecen !== undefined && gecen !== null) {
                oBas = Date.now() - gecen * 1000;
                oBasSabit = true;
            }
            oIlerGoster(true);
        } else {
            oIlerGoster(false);
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
            if (g._boyla) g._boyla();
            g.dataset.dolduruldu = "1";
            /* Sözlük seçilmediyse öneri gelen satır "Sözlüğe Ekle" işaretli
               olur (zorunlu / kilitli satırlar kendi kuralında kalır). */
            if (alan.tanimsiz && alan.tanimsiz.oneri_gelince_ekle
                    && !s.zorunlu && !s.kilitli && s.islem !== "ekle") {
                s.islem = "ekle";
                kutuCiz(i);
            }
            g.dataset.oneriMetin = tireSade(ack);
            /* KONTROL ET: model kural dışı bir ifade yazdıysa metin
               budanmaz; satır işaretlenir, nedeni ipucunda. */
            if (k.uyari && satirElemanlari[i]
                    && !satirElemanlari[i].querySelector(".dg-uyari")) {
                const td = satirElemanlari[i].querySelector(".dg-kolon");
                if (td) {
                    const c = elYap("span", "dg-rol dg-uyari", "Kontrol Et");
                    c.title = "Önerilen açıklamayı kontrol edin: " + tireSade(k.uyari) + ".";
                    td.appendChild(c);
                }
            }
            if (k.kaynak === "hafiza" && satirElemanlari[i]
                    && !satirElemanlari[i].querySelector(".dg-hafiza")) {
                hafizaCipi(satirElemanlari[i].querySelector(".dg-kolon"),
                           satirElemanlari[i], k.hafiza_veri_seti);
            }
            if (k.kaynak === "aile" && satirElemanlari[i])
                aileCipi(satirElemanlari[i].querySelector(".dg-kolon"), satirElemanlari[i], k.aile_kaynagi);
            if (g._vurgu) g._vurgu();
            if (satirElemanlari[i]) satirElemanlari[i].dataset.oneri = "llm";
        });
        if (kayit && kayit.hata) {
            let oh = kart.querySelector(".dg-oneri-hata");
            if (!oh) {
                oh = elYap("div", "dg-oneri-hata");
                kart.insertBefore(oh, dugmeler);
            }
            metinYaz(oh, kayit.hata);
        }
        /* Kullanılamayan model (orkestra diğer modellerle devam etti). */
        if (kayit && kayit.model_notu) {
            let mn = kart.querySelector(".dg-model-notu");
            if (!mn) {
                mn = elYap("div", "dg-not dg-model-notu");
                kart.insertBefore(mn, dugmeler);
            }
            metinYaz(mn, kayit.model_notu);
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
                    oneriKilidi(false, k.biten, k.toplam, k.gecen);
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
       aciklama}]}} + sessiz: true. Kart kategori sormaz (SOZLESME7 §2);
       arka uc satir_ekle'ye bos kategori gecer. */
    birincil.onclick = () => {
        if (mesgul || birincil.disabled) return;
        /* Alanı bırakmadan onaya basılan not önce kaydedilip kontrol edilir. */
        if (adimModu === "aciklama" && acikErisim && acikErisim.kaydedilmemis() > 0) {
            birincil.disabled = true;
            gerekce.hidden = false;
            gerekce.textContent = "Notunuz kontrol ediliyor; bitince onaylayın.";
            return;
        }
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
        if (parcaErisim) karar.parca = parcaErisim.deger();
        if (kolonAdErisim) karar.kolon_ad = kolonAdErisim.deger();
        if (donErisim) { karar.donem = donErisim.deger(); karar.donem_ayrik = donErisim.ayrik(); }
        if (acikErisim) karar.aciklama = true;
        if (cikar) karar.cikar = cDurumlar.filter(c => c.islem === "cikar").map(c => c.kolon);
        if (birlesim) karar.birlesim = bDurumlar.map(d => ({
            kolon: d.kolon, kaynak: d.kaynak, metin: d.kaynak ? "" : d.metin.trim() }));
        let ozet;
        if (birlesim) {
            const elle = bDurumlar.filter(d => !d.kaynak).length;
            ozet = ftBinlik(bDurumlar.length) + " kolonun tanımı seçildi"
                + (elle ? ", " + ftBinlik(elle) + " tanesini siz yazdınız" : "");
        } else if (cikar) {
            const n = karar.cikar.length, k = cDurumlar.length - n;
            ozet = n && k ? ftBinlik(n) + " kolon veri setinden çıkarıldı, " + ftBinlik(k) + " kolon kaldı"
                : n ? ftBinlik(n) + " kolon veri setinden çıkarıldı"
                : "Tanımsız kolonların hepsi veri setinde kaldı";
        } else if (adimModu === "aciklama") {
            const s = acikErisim ? acikErisim.sayac() : {};
            ozet = ftBinlik(Number(s.toplam || 0)) + " kolon kartı onaylandı, "
                + ftBinlik(Number(s.degisen || 0)) + " açıklama düzeltildi";
        } else if (adimModu === "donem") {
            const n = (karar.donem || []).filter(k => k.anlam).length;
            const h = (karar.donem || []).filter(k => k.anlam && k.kaydet).length;
            ozet = ftBinlik(n) + " dönem kalıbı onaylandı" + (h ? ", " + ftBinlik(h) + " tanesi hafızaya" : "");
        } else if (adimModu === "parca") {
            const sy = parcaErisim ? parcaErisim.sayilar() : {};
            ozet = ftBinlik(Number(sy.parca || 0)) + " parça onaylandı"
                + (sy.ayni ? ", " + ftBinlik(sy.ayni) + " yazım çifti birleşti" : "")
                + (sy.degisen ? ", " + ftBinlik(sy.degisen) + " parçanın yazılışı değişecek" : "");
        } else if (adimModu === "kolon_ad") {
            const sy = kolonAdErisim ? kolonAdErisim.sayilar() : {};
            ozet = ftBinlik(Number(sy.aile || 0)) + " aile onaylandı, "
                + ftBinlik(Number(sy.degisen || 0)) + " kolonun adı değişecek";
        } else ozet = (!durumlar.length && kontrol)
            ? (duzelt ? ftBinlik(duzelt) + " tanım düzeltildi" : "Düzeltme uygulanmadı")
            : dogrulamaOzetMetni(karar.haric.length, karar.ekle.length, duzelt);
        kartiKilitle(ozet);
        /* Sessiz gider (ikinci parametre false): kullanici bir cumle
           yazmadi, bir form doldurdu. */
        karar.adim = kartAdim;
        gonder(ozet, false, { dogrulama: karar });
    };

    durumTazele();

    /* YERİNDE DEĞİŞTİRME: adimKabiAl sohbetteki SON bloğa bakar; yanıt
       geldiğinde son blok başka bir adımın olabilir (ör. F5 sonrası aktif
       02.3) ve kart en alta yeni bir blokta düşerdi. */
    /* Değiştirilecek kart bu arada ekrandan kalktıysa (çalışma değişti,
       transkript kırpıldı) yenisi hiçbir yere eklenmez. */
    if (yerine && !yerine.isConnected) return;
    const yerKap = yerine ? yerine.parentNode : null;
    if (yerKap) yerine.replaceWith(kart);
    else (adimKabiAl(blok) || sohbetEl).appendChild(kart);
    rozetiBasligaTasi(blok, rozet, yerKap);
    if (!yerKap) sohbetKaydir();

    /* GECMISTEN yeniden cizim: kart kilitli acilir, rozet karar
       verildigi andaki halini korur (ozet gecirilmiyor). Yoklama da
       BASLAMAZ: o is coktan bitti, tekrar sorulacak bir sey yok. */
    if (blok && blok.kilit) {
        kartiKilitle(); geriAlKilit = null;
        /* BİTEN ADIMIN KARARLI KARTI: Dönem Bilgisi, Ad Parçaları ve
           Kolon Adları geçmişten çizilince sunucudaki GÜNCEL kararlardan
           yeniden kurulur (/karar_alani); transkriptteki kopya eski kalsa
           da kararlar görünür. Kurulamazsa kartın altında nedeni yazar. */
        const bolum = ["donem", "parca", "kolon_ad"].find(k => alan[k]);
        if (bolum && !alan._kararli && alan.adim === bolum) {
            fetch(getWebAppBackendUrl("karar_alani") + "?oturum_id=" + encodeURIComponent(OTURUM_ID)
                  + "&adim=" + encodeURIComponent(bolum))
                .then(r => r.json())
                .then(d => {
                    if (!kart.isConnected) return;
                    if (d && d.tamam && d.alan && d.alan[bolum]) {
                        const yeni = Object.assign({}, alan, d.alan, { _kararli: true, rozet: "" });
                        /* Eski kartın YERİNE (sohbetin sonuna değil). */
                        dogrulamaKartiEkle(yeni, blok, kart);
                    } else if (d && d.hata) {
                        kart.appendChild(elYap("div", "dg-oneri-hata",
                            "Bu kart verilen kararlarla yeniden kurulamadı; ilk hâli görünüyor. (" + tireSade(d.hata) + ")"));
                    }
                })
                .catch(() => {});
        }
        return;
    }

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

/* ==================== 01.2.4.2 Ad Parçaları ====================
   Kolon adlarındaki sayısız parçalar: anlam, tür, standart yazılış ve
   satır onayı. Yazım Sorunları sekmesinde yazımı yakın ya da anlamı aynı
   çıkan çiftler: Aynı / Farklı. "Aynı" denen gruptaki parçalar adlarda
   seçilen yazılışı ve onun satırındaki anlamı alır. Her satır ve her çift
   onaylanmadan birincil düğme açılmaz. 5000 kolonda yüzlerce parça
   olabilir: süzgeç, arama ve sayfalama; örnek tanımlar "i"ye basınca
   sunucudan gelir. */
const PARCA_SAYFA = 100;
const PARCA_STANDART = /^[A-Z][A-Z0-9]{0,11}$/;
const PARCA_SUZGECLER = [
    ["hepsi", "Tümü"], ["onaysiz", "Onaylanmadı"], ["kontrol", "Kontrol Edin"],
    ["hafiza", "Hafızadan"], ["duzen", "Düzenlendi"], ["sorun", "Eksik ya da Hatalı"]];

function parcaBolumuEkle(kart, pa, ilkKilit, degisti) {
    let kilitli = ilkKilit;
    const sade = !!pa.sade;
    /* TÜR ARKA PLANDA: ekranda seçilmez. Dil modelinin (ya da hafızanın)
       türü kalır; anlamda [parça] varsa tür Ek'tir. Ek önerilen satırın
       anlamı [parça] olmadan düzenlenirse tür Diğer olur; asıl tür 01.2.4.4
       son kontrolünde düzeltilir. */
    const EK_YER_RE = /\[\s*par[çc]a\s*\]/i;
    const turBul = (anlam, tur) => EK_YER_RE.test(anlam || "") ? "ek"
        : (!tur || tur === "ek") ? "diger" : tur;

    /* ÖZET + "i" (yönerge ve sütunlar) */
    const ozetSatir = elYap("div", "dg-donem-ozet");
    const ozetEl = elYap("span", "", "");
    ozetSatir.appendChild(ozetEl);
    const bilgiMetni = [(pa.yonerge || []).join("\n\n"), pa.sutunlar || ""].filter(Boolean).join("\n\n");
    if (bilgiMetni) ozetSatir.appendChild(bolmeBilgiSimgesi(tireSade(bilgiMetni), pa.baslik || "Ad Parçaları"));
    kart.appendChild(ozetSatir);
    const notEl = elYap("div", "dg-bilgi-kutu", "");
    notEl.hidden = true;
    kart.appendChild(notEl);

    /* İLERLEME + İPTAL + düşünen robot */
    const ilerEl = elYap("div", "islem-satiri dg-ilerleme");
    ilerEl.setAttribute("role", "status");
    const ilerMetin = elYap("span", "islem-sure", "");
    const ilerIptal = elYap("button", "islem-iptal", "İptal");
    ilerIptal.type = "button";
    ilerIptal.title = "Dil modelini durdur; yorumlanan parçalar kalır, kalanların anlamını siz yazarsınız";
    ilerIptal.onclick = () => {
        ilerIptal.disabled = true;
        ilerIptal.textContent = "İptal ediliyor";
        fetch(getWebAppBackendUrl("parca_iptal"), {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify(ftKimlikGovdesi({}))
        })
        .then(r => r.json())
        .then(d => { if (d && d.parca) yeniVeri(d.parca); })
        .catch(() => {})
        .then(() => { ilerIptal.disabled = false; ilerIptal.textContent = "İptal"; });
    };
    ilerEl.append(ilerMetin, ilerIptal);
    kart.appendChild(ilerEl);
    let ilerBas = Date.now() - ((pa.ilerleme && pa.ilerleme.gecen) || 0) * 1000;
    const ilerDusun = dusunmeIzleyici(kart);
    const ilerSayac = setInterval(() => {
        const acik = pa.dm === "calisiyor" && !kilitli && kart.isConnected;
        ilerEl.classList.toggle("gorunur", acik);
        ilerDusun(acik);
        if (acik) {
            const il = pa.ilerleme || {};
            ilerMetin.textContent = "Dil modeli parçaları yorumluyor"
                + (il.toplam ? ": " + ftBinlik(il.biten || 0) + " / " + ftBinlik(il.toplam) : "")
                + " · " + sureBicim(Math.max(0, Math.floor((Date.now() - ilerBas) / 1000)));
        }
        if (pa.dm !== "calisiyor" && kart.isConnected) clearInterval(ilerSayac);
    }, 1000);

    /* SEKMELER */
    const sekmeBar = elYap("div", "dg-sekmeler");
    sekmeBar.setAttribute("role", "tablist");
    const panolar = {}, sekmeDugme = {};
    [["parca", "Parçalar"], ["yazim", "Yazım Sorunları"]].forEach(([ad, etiket]) => {
        const b = elYap("button", "dg-sekme", "");
        b.type = "button";
        b.setAttribute("role", "tab");
        b.append(elYap("span", "", etiket), elYap("span", "dg-sekme-sayi", ""));
        b.onclick = () => sekmeAc(ad);
        sekmeBar.appendChild(b);
        sekmeDugme[ad] = b;
        panolar[ad] = elYap("div", "dg-sekme-pano");
        panolar[ad].setAttribute("role", "tabpanel");
    });
    function sekmeAc(ad) {
        Object.keys(panolar).forEach(k => {
            panolar[k].hidden = k !== ad;
            sekmeDugme[k].classList.toggle("secili", k === ad);
            sekmeDugme[k].setAttribute("aria-selected", k === ad ? "true" : "false");
        });
    }
    kart.appendChild(sekmeBar);
    Object.values(panolar).forEach(pn => kart.appendChild(pn));
    sekmeAc("parca");

    /* ---- KARAR HALİ ----
       satir: parca -> {anlam, tur, standart, onay} (kullanıcının son hâli;
       yoklamada kaybolmaz). es: anahtar -> {karar, standart, onay}. */
    const satir = {}, duzenlendi = new Set();
    const es = {};
    function satirAl(r) {
        if (!satir[r.parca]) satir[r.parca] = { anlam: tireSade(r.anlam || ""), tur: r.tur || "diger",
                                                standart: r.standart || r.parca, onay: !!r.onay };
        return satir[r.parca];
    }
    function esAl(e) {
        if (!es[e.anahtar]) es[e.anahtar] = { karar: e.karar || "", standart: e.standart || e.a,
                                              onay: !!e.onay };
        return es[e.anahtar];
    }
    /* Yoklama: kullanıcının dokunmadığı satır sunucunun son önerisini alır. */
    function yeniVeri(yeni) {
        pa.dm = yeni.dm; pa.not = yeni.not || ""; pa.ilerleme = yeni.ilerleme;
        (yeni.satirlar || []).forEach(r => {
            if (!duzenlendi.has(r.parca) && satir[r.parca] && !satir[r.parca].onay) {
                const s = satir[r.parca];
                s.anlam = tireSade(r.anlam || ""); s.tur = r.tur || "diger"; s.standart = r.standart || r.parca;
            }
        });
        (yeni.esler || []).forEach(e => { esAl(e); });
        pa.satirlar = yeni.satirlar || [];
        pa.esler = yeni.esler || [];
        tumunuCiz();
        if (degisti) degisti();
    }

    /* "AYNI" GRUPLARI: aynı denen çiftlerin birleşimi; grubun yazılışı
       çiftlerde seçilen standart. parca -> {uyeler, std} */
    function gruplar() {
        const ust = {};
        const bul = x => { while ((ust[x] = ust[x] || x) !== x) x = ust[x]; return x; };
        (pa.esler || []).forEach(e => {
            if (esAl(e).karar === "ayni") { const a = bul(e.a), b = bul(e.b); if (a !== b) ust[b] = a; }
        });
        const g = {};
        Object.keys(ust).forEach(x => { (g[bul(x)] = g[bul(x)] || []).push(x); });
        const harita = {};
        Object.values(g).forEach(uyeler => {
            if (uyeler.length < 2) return;
            uyeler.sort();
            const secilen = (pa.esler || []).filter(e => esAl(e).karar === "ayni" && uyeler.includes(e.a))
                .map(e => esAl(e).standart).filter(Boolean);
            const std = secilen.length ? secilen[0] : uyeler[0];
            uyeler.forEach(p => { harita[p] = { uyeler, std, cakisma: new Set(secilen).size > 1 }; });
        });
        return harita;
    }
    /* Satırın geçerli değerleri (aynı grubun üyesi standart satırdan alır). */
    function etkin(p, grup) {
        const s = satir[p] || {};
        const g = grup[p];
        if (g && g.std !== p && satir[g.std]) {
            const k = satir[g.std];
            return { anlam: k.anlam, tur: k.tur, standart: k.standart, onay: s.onay, uye: g.std };
        }
        return { anlam: s.anlam, tur: s.tur, standart: s.standart, onay: s.onay, uye: "" };
    }
    function sorunlar(grup) {
        /* Onayı durduranlar: satır başına metin. */
        const sor = {};
        const sahip = {};
        (pa.satirlar || []).forEach(r => {
            const e = etkin(r.parca, grup);
            const kim = grup[r.parca] ? grup[r.parca].std : r.parca;
            const st = (e.standart || "").trim();
            (sahip[st] = sahip[st] || new Set()).add(kim);
        });
        (pa.satirlar || []).forEach(r => {
            if (r.bekliyor && pa.dm === "calisiyor" && !duzenlendi.has(r.parca)) return;
            const e = etkin(r.parca, grup);
            const st = (e.standart || "").trim();
            const ekSay = ((e.anlam || "").match(/\[\s*par[çc]a\s*\]/gi) || []).length;
            if (!(e.anlam || "").trim()) sor[r.parca] = "Anlam boş.";
            /* EK: anlamda bir kez [parça] (arkasındaki parçanın yeri) ve ekin kendisi. */
            else if (e.tur === "ek" && (ekSay !== 1 || !(e.anlam || "").replace(/\[\s*par[çc]a\s*\]/gi, "").trim()))
                sor[r.parca] = ekSay > 1 ? "Anlamda [parça] bir kez yazılır."
                    : ekSay ? "[parça] ile birlikte eki de yazın (ör. [parça]lık, [parça] başına)."
                    : "Bu parça arkasındaki parçaya bağlanan bir ek gibi duruyor (PER_DAY: günlük). "
                    + "Anlamı [parça] ile yazın: [parça]lık, [parça] başına, [parça] bazında. Ek "
                    + "değilse anlamı kendi sözcüğüyle düzeltin.";
            else if (!PARCA_STANDART.test(st))
                sor[r.parca] = "Standart yazılış geçersiz: büyük harfle başlar, yalnız büyük harf ve rakam, en çok 12 karakter.";
            else if (sahip[st] && sahip[st].size > 1)
                sor[r.parca] = st + " standardını anlamı farklı başka bir parça da alıyor ("
                    + Array.from(sahip[st]).filter(x => x !== (grup[r.parca] ? grup[r.parca].std : r.parca)).join(", ")
                    + "). Aynıysa Yazım Sorunları'nda «Aynı» deyin, değilse birini değiştirin.";
        });
        return sor;
    }

    /* ---- PARÇALAR SEKMESİ ---- */
    const pUst = elYap("div", "dg-tablo-ust dg-parca-ust");
    const ara = document.createElement("input");
    ara.type = "search"; ara.className = "dg-giris dg-parca-ara";
    ara.placeholder = "Parça ya da anlam ara";
    ara.setAttribute("aria-label", "Parça ara");
    const suz = document.createElement("select");
    suz.className = "dg-parca-suz";
    suz.setAttribute("aria-label", "Süzgeç");
    PARCA_SUZGECLER.forEach(([d, a]) => { const o = document.createElement("option"); o.value = d; o.textContent = a; suz.appendChild(o); });
    const gorOnay = elYap("button", "dg-toplu-btn", "Görünenleri Onayla");
    gorOnay.type = "button";
    gorOnay.title = "Bu sayfada görünen ve eksiği olmayan satırlar onaylanır. «Kontrol edin» "
        + "satırları toplu onaylanmaz; tek tek bakıp onaylayın.";
    const sayfaEl = elYap("div", "dg-parca-sayfa");
    pUst.append(ara, suz, gorOnay, sayfaEl);
    if (!sade) panolar.parca.appendChild(pUst);
    const pSar = elYap("div", "dg-tablo-sar dg-parca-sar");
    const pTablo = elYap("table", "dg-tablo dg-parca-tablo");
    const pTh = document.createElement("thead"), pHr = document.createElement("tr");
    ["Parça", "Anlam", "Standart", "Onay"].forEach(h => {
        const th = elYap("th", "", h);
        /* Standart'ın ne olduğu başlığın "i"sinde. */
        if (h === "Standart") th.appendChild(bolmeBilgiSimgesi(
            "Parçanın yeni kolon adlarında (01.2.4.4 Kolon Adları) yazılacağı biçim. Çoğunlukla "
            + "parçanın kendisidir. Aynı şeyi anlatan farklı yazılışları tek yazılışta toplamak için "
            + "değiştirilir (ör. TRX yerine TXN). Parçadan farklıysa kutu sarı görünür ve altında "
            + "\"Adlarda X yerine Y\" yazar. Girdi veri setindeki adlar değişmez.", "Standart"));
        pHr.appendChild(th);
    });
    pTh.appendChild(pHr); pTablo.appendChild(pTh);
    const pTb = document.createElement("tbody");
    pTablo.appendChild(pTb); pSar.appendChild(pTablo);
    panolar.parca.appendChild(pSar);
    let sayfa = 0;
    ara.addEventListener("input", () => { sayfa = 0; parcaCiz(); });
    suz.addEventListener("change", () => { sayfa = 0; parcaCiz(); });

    function durumMetni(r, e, sor) {
        const bekliyor = !!r.bekliyor && pa.dm === "calisiyor" && !satir[r.parca].onay && !duzenlendi.has(r.parca);
        if (bekliyor) return ["Dil modeli yorumluyor", false];
        if (sor) return ["Kontrol edin", true];
        if (e.uye) return [e.uye + " ile aynı; anlamı ve yazılışı o satırdan", false];
        if (duzenlendi.has(r.parca) || (r.oneri && (e.anlam !== tireSade(r.oneri.anlam || "")
            || e.standart !== (r.oneri.standart || r.parca))))
            return ["Düzenlendi", false];
        if (r.kontrol) return ["Kontrol edin", true];
        /* Önerinin kaynağı (hafıza, dil modeli, kanıt sayısı) yazılmaz. */
        if (r.kaynak === "hafiza" || r.kaynak === "model") return ["", false];
        return ["Anlamı siz yazın", true];
    }
    function goruneni() {
        const grup = gruplar(), sor = sorunlar(grup);
        const q = ara.value.trim().toLocaleUpperCase("tr");
        const sz = suz.value;
        return { grup, sor, liste: (pa.satirlar || []).filter(r => {
            const e = etkin(r.parca, grup);
            if (q && r.parca.indexOf(q) === -1
                && (e.anlam || "").toLocaleUpperCase("tr").indexOf(q) === -1) return false;
            if (sz === "onaysiz") return !e.onay;
            if (sz === "kontrol") return !!r.kontrol;
            if (sz === "hafiza") return r.kaynak === "hafiza";
            if (sz === "duzen") return durumMetni(r, e, "")[0] === "Düzenlendi";
            if (sz === "sorun") return !!sor[r.parca];
            return true;
        }) };
    }
    function parcaCiz() {
        const { grup, sor, liste } = goruneni();
        const sayfaSay = Math.max(1, Math.ceil(liste.length / PARCA_SAYFA));
        if (sayfa >= sayfaSay) sayfa = sayfaSay - 1;
        const gorunen = liste.slice(sayfa * PARCA_SAYFA, (sayfa + 1) * PARCA_SAYFA);
        pTb.textContent = "";
        gorunen.forEach(r => pTb.appendChild(satirCiz(r, grup, sor)));
        if (!gorunen.length) {
            const tr = elYap("tr", "dg-bos-tablo");
            const td = elYap("td", "", (pa.satirlar || []).length
                ? "Bu süzgeçte parça yok." : "Kolon adlarında yorumlanacak parça yok.");
            td.colSpan = 4; tr.appendChild(td); pTb.appendChild(tr);
        }
        sayfaEl.textContent = "";
        if (liste.length > PARCA_SAYFA) {
            const geri = elYap("button", "dg-toplu-btn", "Önceki");
            geri.type = "button"; geri.disabled = sayfa === 0;
            geri.onclick = () => { sayfa--; parcaCiz(); };
            const ileri = elYap("button", "dg-toplu-btn", "Sonraki");
            ileri.type = "button"; ileri.disabled = sayfa >= sayfaSay - 1;
            ileri.onclick = () => { sayfa++; parcaCiz(); };
            sayfaEl.append(geri, elYap("span", "dg-parca-sayfa-no",
                ftBinlik(sayfa * PARCA_SAYFA + 1) + " ile " + ftBinlik(Math.min(liste.length, (sayfa + 1) * PARCA_SAYFA))
                + " arası · " + ftBinlik(liste.length)), ileri);
        }
        /* Toplu onay "Kontrol edin" satırlarını atlar: onlar tek tek onaylanır. */
        const topluOlur = r => !satir[r.parca].onay && !sor[r.parca] && !r.kontrol;
        gorOnay.disabled = kilitli || pa.dm === "calisiyor" || !gorunen.some(topluOlur);
        gorOnay.onclick = () => {
            if (kilitli || pa.dm === "calisiyor") return;
            gorunen.filter(topluOlur).forEach(r => { satir[r.parca].onay = true; });
            tumunuCiz(); if (degisti) degisti();
        };
        ozetYaz(grup, sor);
    }
    /* Örnekler satırın altında, tablo genişliğinde açılır. */
    function ornekGoster(tr, r, dugme) {
        if (dugme._acik) { dugme._acik.remove(); dugme._acik = null; dugme.textContent = "Örnekler"; return; }
        const dtr = elYap("tr", "dg-donem-detay");
        const dtd = elYap("td", "");
        dtd.colSpan = 4;
        const kutu = elYap("div", "dg-parca-ornek", "Örnekler yükleniyor");
        dtd.appendChild(kutu); dtr.appendChild(dtd);
        tr.after(dtr);
        dugme._acik = dtr;
        dugme.textContent = "Örnekleri Kapat";
        fetch(getWebAppBackendUrl("parca_ornek") + "?oturum_id=" + encodeURIComponent(OTURUM_ID)
              + "&parca=" + encodeURIComponent(r.parca))
            .then(x => x.json())
            .then(d => {
                const orn = (d && d.ornekler) || [];
                kutu.textContent = "";
                if (!orn.length) { kutu.textContent = "Örnek tanım bulunamadı."; return; }
                kutu.appendChild(elYap("div", "dg-parca-ornek-bas", "Dil modelinin baktığı örnek tanımlar"));
                orn.forEach(o => {
                    const sat = elYap("div", "dg-parca-ornek-satir");
                    sat.append(elYap("span", "dg-parca-ornek-kolon", o.kolon),
                               elYap("span", "", tireSade(o.tanim || "Tanım yok")));
                    kutu.appendChild(sat);
                });
            })
            .catch(() => { kutu.textContent = "Örnekler okunamadı."; });
    }
    function satirCiz(r, grup, sor) {
        const s = satirAl(r);
        const e = etkin(r.parca, grup);
        const calisiyor = pa.dm === "calisiyor";
        const kapali = kilitli || sade;
        const tr = elYap("tr", "dg-satir dg-parca-satir");
        tr.dataset.parca = r.parca;
        /* PARÇA */
        const tdP = elYap("td", "dg-kolon");
        const pBas = elYap("div", "dg-parca-ad");
        pBas.appendChild(elYap("span", "dg-donem-kalip", r.parca));
        if (!sade) {
            const ib = elYap("button", "dg-baglanti dg-parca-ornek-ac", "Örnekler");
            ib.type = "button";
            ib.title = "Bu parçanın geçtiği kolonlardan örnek ad ve sözlük tanımları";
            ib.onclick = () => ornekGoster(tr, r, ib);
            pBas.appendChild(ib);
        }
        tdP.appendChild(pBas);
        let alt = ftBinlik(r.kolon || 0) + " kolonda";
        if (r.tanimsiz) alt += " · " + ftBinlik(r.tanimsiz) + " tanımsız";
        if ((r.birlikte || []).length) alt += " · yanında: " + r.birlikte.map(b => b[0]).join(", ");
        tdP.appendChild(elYap("div", "dg-donem-tur-not", alt));
        tr.appendChild(tdP);
        /* ANLAM */
        const tdA = elYap("td", "dg-aciklama-hucre");
        const [et, dikkat] = sade ? ["", false] : durumMetni(r, e, sor[r.parca]);
        const durumEl = elYap("div", "dg-donem-durum" + (dikkat ? " dikkat" : ""), et);
        durumEl.hidden = !et;
        tdA.appendChild(durumEl);
        const g = document.createElement("input");
        g.type = "text"; g.className = "dg-giris dg-parca-anlam";
        g.value = e.anlam || "";
        g.placeholder = r.bekliyor && calisiyor ? "" : "Anlamı yazın";
        g.disabled = kapali || !!e.uye || (r.bekliyor && calisiyor && !duzenlendi.has(r.parca));
        g.setAttribute("aria-label", r.parca + " anlamı");
        tdA.appendChild(g);
        if (!sade) {
            if (sor[r.parca]) tdA.appendChild(elYap("div", "dg-donem-soru", tireSade(sor[r.parca])));
            if (r.soru) tdA.appendChild(elYap("div", "dg-donem-soru", "Soru: " + tireSade(r.soru)));
            if (r.celiski) tdA.appendChild(elYap("div", "dg-donem-not", "Ad ile tanımlar çelişiyor: " + tireSade(r.celiski)));
            if (r["not"]) tdA.appendChild(elYap("div", "dg-donem-not", "Not: " + tireSade(r["not"])));
        }
        tr.appendChild(tdA);
        /* STANDART */
        const tdS = elYap("td", "");
        const st = document.createElement("input");
        st.type = "text"; st.className = "dg-giris dg-parca-std";
        st.value = e.standart || "";
        st.maxLength = 12;
        st.disabled = g.disabled;
        st.setAttribute("aria-label", r.parca + " standart yazılışı");
        st.classList.toggle("dg-noksan", !sade && !PARCA_STANDART.test((e.standart || "").trim()));
        /* Standart parçadan farklıysa sarı: yeni adlarda parça değişecek. */
        const stFarkBoya = () => st.classList.toggle("dg-parca-std-farkli", !sade
            && st.value.trim() !== r.parca && PARCA_STANDART.test(st.value.trim()));
        stFarkBoya();
        tdS.appendChild(st);
        if (!sade && (e.standart || "") !== r.parca && PARCA_STANDART.test(e.standart || ""))
            tdS.appendChild(elYap("div", "dg-donem-tur-not", "Adlarda " + r.parca + " yerine " + e.standart));
        tr.appendChild(tdS);
        /* ONAY */
        const tdO = elYap("td", "dg-ekle-hucre");
        const k = document.createElement("input");
        k.type = "checkbox"; k.className = "dg-ekle";
        k.checked = !!s.onay;
        k.disabled = kapali || (calisiyor && r.bekliyor && !duzenlendi.has(r.parca)) || (!s.onay && !!sor[r.parca]);
        k.title = sor[r.parca] ? "Önce eksiği giderin" : "Satırı onayla";
        k.setAttribute("aria-label", r.parca + " onay");
        tdO.appendChild(k);
        tr.appendChild(tdO);
        tr.classList.toggle("dg-donem-dikkat", !sade && dikkat && !s.onay);
        tr.classList.toggle("dg-parca-onayli", !!s.onay);
        /* Değişiklik onayı kaldırır. */
        const degis = () => {
            if (g.value !== s.anlam) s.tur = turBul(g.value, s.tur);
            s.anlam = g.value; s.standart = st.value.toUpperCase().trim();
            s.onay = false; duzenlendi.add(r.parca);
            tumunuCiz(tr); if (degisti) degisti();
        };
        g.addEventListener("change", degis);
        st.addEventListener("input", () => { const p = st.selectionStart; st.value = st.value.toUpperCase(); st.setSelectionRange(p, p); stFarkBoya(); });
        st.addEventListener("change", degis);
        k.addEventListener("change", () => {
            if (kapali) { k.checked = !k.checked; return; }
            s.onay = k.checked; tumunuCiz(tr); if (degisti) degisti();
        });
        return tr;
    }

    /* ---- YAZIM SORUNLARI SEKMESİ ---- */
    const yNot = elYap("p", "dg-donem-pano-not",
        "Yazımı birbirine yakın ya da anlamı aynı çıkan parçalar. Aynı şeyi anlatıyorlarsa «Aynı» "
        + "deyip adlarda kullanılacak yazılışı seçin; diğerleri o yazılışın anlamını alır. "
        + "Değilse «Farklı» deyin.");
    if (!sade) panolar.yazim.appendChild(yNot);
    const yUst = elYap("div", "dg-tablo-ust");
    const yOnay = elYap("button", "dg-toplu-btn", "Kararı Verilenleri Onayla");
    yOnay.type = "button";
    if (!sade) { yUst.appendChild(yOnay); panolar.yazim.appendChild(yUst); }
    const ySar = elYap("div", "dg-tablo-sar dg-parca-sar");
    const yTablo = elYap("table", "dg-tablo dg-parca-es-tablo");
    const yTh = document.createElement("thead"), yHr = document.createElement("tr");
    ["Parçalar", "Neden", "Karar", "Adlarda Kullanılacak", "Onay"].forEach(h => yHr.appendChild(elYap("th", "", h)));
    yTh.appendChild(yHr); yTablo.appendChild(yTh);
    const yTb = document.createElement("tbody");
    yTablo.appendChild(yTb); ySar.appendChild(yTablo);
    panolar.yazim.appendChild(ySar);
    function esCiz() {
        const grup = gruplar();
        yTb.textContent = "";
        const kapali = kilitli || sade || pa.dm === "calisiyor";
        (pa.esler || []).forEach(e => {
            const k = esAl(e);
            const tr = elYap("tr", "dg-satir dg-parca-es-satir");
            const tdP = elYap("td", "");
            [e.a, e.b].forEach(p => {
                const r = (pa.satirlar || []).find(x => x.parca === p) || {};
                const sat = elYap("div", "dg-parca-es-parca");
                sat.append(elYap("span", "dg-donem-kalip", p),
                           elYap("span", "dg-donem-tur-not", ftBinlik(r.kolon || 0) + " kolon"
                                 + (satir[p] && satir[p].anlam ? " · " + satir[p].anlam : "")));
                /* "i": parçanın geçtiği ilk üç kolon ve tanımı (aynı mı, hangi
                   yazılış kullanılsın diye karşılaştırmak için). */
                const orn = (e.ornek && e.ornek[p]) || [];
                if (orn.length) sat.appendChild(bolmeBilgiSimgesi(tireSade("Geçtiği kolonlardan örnekler:\n"
                    + orn.map(([k, t]) => k + ": " + (t || "Tanım yok")).join("\n")), p));
                tdP.appendChild(sat);
            });
            tr.appendChild(tdP);
            tr.appendChild(elYap("td", "dg-donem-olasi-neden", e.neden || ""));
            const tdK = elYap("td", "");
            const bol = elYap("div", "dg-segment");
            [["ayni", "Aynı"], ["farkli", "Farklı"]].forEach(([d, a]) => {
                const b = elYap("button", k.karar === d ? "secili" : "", a);
                b.type = "button"; b.disabled = kapali;
                b.setAttribute("aria-pressed", k.karar === d ? "true" : "false");
                b.onclick = () => {
                    if (kapali) return;
                    k.karar = d; k.onay = true;
                    tumunuCiz(); if (degisti) degisti();
                };
                bol.appendChild(b);
            });
            tdK.appendChild(bol);
            tr.appendChild(tdK);
            const tdS = elYap("td", "");
            if (k.karar === "ayni") {
                const g = grup[e.a] || { uyeler: [e.a, e.b], std: k.standart };
                const sec = document.createElement("select");
                sec.className = "dg-donem-tur";
                sec.setAttribute("aria-label", e.a + " ve " + e.b + " için adlarda kullanılacak yazılış");
                g.uyeler.forEach(p => { const o = document.createElement("option"); o.value = p; o.textContent = p; sec.appendChild(o); });
                sec.value = g.std;
                sec.disabled = kapali;
                sec.onchange = () => {
                    /* Grubun bütün çiftleri aynı yazılışı alır. */
                    (pa.esler || []).forEach(x => { if (esAl(x).karar === "ayni" && g.uyeler.includes(x.a)) esAl(x).standart = sec.value; });
                    tumunuCiz(); if (degisti) degisti();
                };
                tdS.appendChild(sec);
                if (g.uyeler.length > 2) tdS.appendChild(elYap("div", "dg-donem-tur-not",
                    "Aynı grupta: " + g.uyeler.join(", ")));
            } else tdS.appendChild(elYap("span", "dg-donem-tur-not", k.karar === "farkli" ? "Her biri kendi yazılışıyla" : ""));
            tr.appendChild(tdS);
            const tdO = elYap("td", "dg-ekle-hucre");
            const kt = document.createElement("input");
            kt.type = "checkbox"; kt.className = "dg-ekle";
            kt.checked = !!k.onay; kt.disabled = kapali || !k.karar;
            kt.setAttribute("aria-label", e.a + " ve " + e.b + " onay");
            kt.onchange = () => { if (kapali) { kt.checked = !kt.checked; return; } k.onay = kt.checked; tumunuCiz(); if (degisti) degisti(); };
            tdO.appendChild(kt);
            tr.appendChild(tdO);
            tr.classList.toggle("dg-donem-dikkat", !sade && !(k.karar && k.onay));
            tr.classList.toggle("dg-parca-onayli", !!(k.karar && k.onay));
            yTb.appendChild(tr);
        });
        if (!(pa.esler || []).length) {
            const tr = elYap("tr", "dg-bos-tablo");
            const td = elYap("td", "", pa.dm === "calisiyor"
                ? "Dil modelinin yorumu geldikçe anlamı aynı çıkan parçalar burada görünür."
                : "Yazımı yakın ya da anlamı aynı parça bulunmadı.");
            td.colSpan = 5; tr.appendChild(td); yTb.appendChild(tr);
        }
        yOnay.disabled = kapali || !(pa.esler || []).some(e => esAl(e).karar && !esAl(e).onay);
        yOnay.onclick = () => {
            if (kapali) return;
            (pa.esler || []).forEach(e => { const k = esAl(e); if (k.karar) k.onay = true; });
            tumunuCiz(); if (degisti) degisti();
        };
    }

    function ozetYaz(grup, sor) {
        const ss = pa.satirlar || [], ee = pa.esler || [];
        const onayli = ss.filter(r => satir[r.parca] && satir[r.parca].onay).length;
        const kontrol = ss.filter(r => r.kontrol && !(satir[r.parca] || {}).onay).length;
        const esBekle = ee.filter(e => !(esAl(e).karar && esAl(e).onay)).length;
        const sorun = Object.keys(sor).length;
        const p = [ftBinlik(ss.length) + " parça", ftBinlik(onayli) + " onaylı"];
        if (kontrol) p.push(ftBinlik(kontrol) + " kontrol edilecek");
        if (sorun) p.push(ftBinlik(sorun) + " eksik ya da hatalı");
        if (ee.length) p.push(ftBinlik(ee.length) + " yazım çifti" + (esBekle ? ", " + ftBinlik(esBekle) + " karar bekliyor" : ""));
        ozetEl.textContent = p.join(" · ");
        sekmeDugme.parca.lastChild.textContent = ftBinlik(ss.length - onayli);
        sekmeDugme.yazim.lastChild.textContent = ftBinlik(esBekle);
        sekmeDugme.parca.title = ftBinlik(ss.length - onayli) + " parça onay bekliyor";
        sekmeDugme.yazim.title = ftBinlik(esBekle) + " çift karar bekliyor";
    }
    /* odak: yeniden çizimde odakta kalacak satır (değişikliğin yapıldığı). */
    function tumunuCiz(odakTr) {
        const odakP = odakTr && odakTr.dataset ? odakTr.dataset.parca : null;
        const odakSinif = document.activeElement && document.activeElement.className;
        parcaCiz();
        esCiz();
        notEl.textContent = pa.not ? tireSade(pa.not) : "";
        notEl.hidden = !notEl.textContent;
        if (odakP) {
            const tr = pTb.querySelector('tr[data-parca="' + CSS.escape(odakP) + '"]');
            const el = tr && odakSinif ? tr.querySelector("." + String(odakSinif).split(" ").filter(c => c.indexOf("dg-parca-") === 0)[0]) : null;
            if (el && el.focus) el.focus();
        }
    }
    (pa.satirlar || []).forEach(satirAl);
    (pa.esler || []).forEach(esAl);
    tumunuCiz();

    let yoklamaSayisi = 0;
    function yokla() {
        if (kilitli || !document.body.contains(pTb)) return;
        if (yoklamaSayisi++ > 600) return;
        fetch(getWebAppBackendUrl("parca_alani") + "?oturum_id=" + encodeURIComponent(OTURUM_ID))
            .then(r => r.json())
            .then(d => {
                const yeni = d && d.parca;
                if (!yeni) return setTimeout(yokla, 3000);
                if (kart.contains(document.activeElement) && document.activeElement.tagName !== "BUTTON") {
                    yoklamaSayisi--;
                    return setTimeout(yokla, 1500);
                }
                yeniVeri(yeni);
                if (yeni.dm === "calisiyor") setTimeout(yokla, 3000);
            })
            .catch(() => setTimeout(yokla, 8000));
    }
    if (pa.dm === "calisiyor" && !sade) setTimeout(yokla, 3000);

    return {
        deger: () => {
            const grup = gruplar();
            return {
                satirlar: (pa.satirlar || []).map(r => {
                    const e = etkin(r.parca, grup);
                    return { parca: r.parca, anlam: (e.anlam || "").trim(), tur: e.tur || "diger",
                             standart: (e.standart || "").trim(), onay: !!(satir[r.parca] || {}).onay };
                }),
                esler: (pa.esler || []).map(e => ({ anahtar: e.anahtar, karar: esAl(e).karar,
                                                     standart: esAl(e).standart, onay: !!esAl(e).onay }))
            };
        },
        /* Onayı durduranlar. */
        onaysiz: () => (pa.satirlar || []).filter(r => !(satir[r.parca] || {}).onay).length,
        esBekleyen: () => (pa.esler || []).filter(e => !(esAl(e).karar && esAl(e).onay)).length,
        sorunlu: () => Object.keys(sorunlar(gruplar())).length,
        cakisma: () => Object.values(gruplar()).some(g => g.cakisma),
        sayilar: () => {
            const v = (pa.satirlar || []).length;
            const deg = (pa.satirlar || []).filter(r => { const e = etkin(r.parca, gruplar()); return (e.standart || "") !== r.parca; }).length;
            return { parca: v, ayni: (pa.esler || []).filter(e => esAl(e).karar === "ayni").length, degisen: deg };
        },
        kilitle: k => { kilitli = k; tumunuCiz(); },
        bekliyor: () => pa.dm === "calisiyor"
    };
}

/* ==================== 01.2.4.4 Kolon Adları ====================
   Adları KOD kurar: onaylı parçaların standart yazılışları Ad
   Standardı'ndaki yer sırasına dizilir. Üstte Ad Standardı (yerlerin
   sırası, ← → ile değişir; adlar sunucuda yeniden kurulur). Satırlar
   ailedir (adı yalnız sayılarla ayrılan kolonlar): Yeni Ad ya da Eski Ad
   Kalsın, ve onay. Her aile onaylanmadan birincil düğme açılmaz. */
const KAD_SAYFA = 100;
const KAD_AD = /^[A-Za-z][A-Za-z0-9_]*$/;

function kolonAdBolumuEkle(kart, ka, ilkKilit, adimda, degisti) {
    let kilitli = ilkKilit;
    const kb = elYap("div", "dg-tablo-bas dg-kontrol-bas");
    const kbas = elYap("div", "dg-tablo-baslik", ka.baslik || "Kolon Adları");
    kb.appendChild(kbas);
    kart.appendChild(kb);
    const bos = { deger: () => ({}), kilitle: () => {}, bekliyor: () => false,
                  onaysiz: () => 0, sorunlu: () => 0, sayilar: () => ({}) };
    /* Eski kayıtlardaki kart (aile yapısı yok): yalnız not. */
    if (!ka.sira) {
        kart.appendChild(elYap("div", "dg-kisa-aciklama",
            "Bu kart önceki sürümle oluşturuldu; ayrıntısı gösterilmiyor."));
        return bos;
    }
    if (ka.bilgi) kbas.appendChild(bolmeBilgiSimgesi(tireSade(ka.bilgi), ka.baslik || "Kolon Adları"));
    /* Önceki kontrolden gelen karar ya da taslak (01.2.4 önceki onaylı kontrol). */
    if (ka.not && !ilkKilit) kart.appendChild(elYap("div", "dg-bilgi-kutu", tireSade(ka.not)));
    const adExcel = excelSeridiYap("aciklama", "Önerilen Sözlüğü İndir",
        "Eski ve yeni adlar, orijinal ve düzeltilmiş açıklamalar, kolon kartı");
    adExcel.ac(true);
    kb.appendChild(adExcel.el);

    const yerAdi = {};
    (ka.yerler || []).forEach(y => { yerAdi[y.kod] = y.ad; });
    let sira = (ka.sira || []).slice();
    const satirlar = (ka.satirlar || []).map(r => ({ aile: r.aile, kolonlar: r.kolonlar || [],
                                                    secim: r.secim || "yeni", onay: !!r.onay }));
    const korunan = ka.korunan || [];

    /* ---- AD STANDARDI ---- */
    const stKap = elYap("div", "dg-kad-standart");
    const stBas = elYap("div", "dg-kad-standart-bas");
    stBas.append(elYap("span", "dg-kad-standart-ad", "Ad Standardı"),
                 elYap("span", "dg-donem-tur-not", (ka.standart_kayitli ? "Hafızadaki standart" : "Varsayılan sıra")
                       + " · büyük harf · ayraç _"));
    const stSira = elYap("div", "dg-kad-sira");
    stKap.append(stBas, stSira);
    kart.appendChild(stKap);
    const stOrnek = elYap("div", "dg-donem-tur-not dg-kad-ornek", "");
    stKap.appendChild(stOrnek);
    let onizleSayac = 0;
    /* SIRA: parçalar tutup sürüklenerek dizilir (fare ve dokunmatik;
       pointer olayları). Sürüklerken öteki parçalar canlı kayar, numaralar
       güncellenir; bırakınca sıra değiştiyse adlar yeniden kurulur. Klavye:
       parçaya odaklanıp sol / sağ ok tuşu bir öne / arkaya taşır. */
    function siraCiz(odakYer) {
        stSira.textContent = "";
        stSira.setAttribute("role", "list");
        sira.forEach((y, i) => {
            const c = elYap("span", "dg-kad-yer" + (kilitli ? "" : " suruklenir"));
            c.dataset.yer = y;
            c.setAttribute("role", "listitem");
            if (!kilitli) {
                c.tabIndex = 0;
                c.title = "Tutup sürükleyerek yerini değiştirin (klavyede sol ve sağ ok tuşları).";
                c.setAttribute("aria-label", (i + 1) + ". " + (yerAdi[y] || y)
                    + ". Yerini değiştirmek için tutup sürükleyin ya da sol ve sağ ok tuşlarını kullanın.");
                c.appendChild(elYap("span", "dg-kad-tutamak", "⠿"));
                c.addEventListener("pointerdown", e => surukleBasla(e, c));
                c.addEventListener("keydown", e => {
                    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
                    e.preventDefault();
                    tasi(i, e.key === "ArrowLeft" ? -1 : 1);
                });
            }
            c.appendChild(elYap("span", "dg-kad-yer-ad", (i + 1) + ". " + (yerAdi[y] || y)));
            stSira.appendChild(c);
        });
        if (odakYer) {
            const o = stSira.querySelector('[data-yer="' + CSS.escape(odakYer) + '"]');
            if (o) o.focus();
        }
        const ilk = satirlar.find(r => r.kolonlar.length && r.kolonlar[0][0] !== r.kolonlar[0][1]);
        stOrnek.textContent = ilk ? "Örnek: " + ilk.kolonlar[0][0] + " → " + ilk.kolonlar[0][1] : "";
    }
    function siraNumarala() {
        [...stSira.children].forEach((c, i) => {
            const ad = c.querySelector(".dg-kad-yer-ad");
            if (ad) ad.textContent = (i + 1) + ". " + (yerAdi[c.dataset.yer] || c.dataset.yer);
        });
    }
    function surukleBasla(e, c) {
        if (kilitli || (e.pointerType === "mouse" && e.button !== 0)) return;
        e.preventDefault();
        c.focus();
        const ilk = sira.slice();
        let oynadi = false;
        const x0 = e.clientX, y0 = e.clientY;
        const hareket = ev => {
            if (!oynadi && Math.abs(ev.clientX - x0) + Math.abs(ev.clientY - y0) < 4) return;
            oynadi = true;
            c.classList.add("surukleniyor");
            /* Bırakılacak yer: imlecin önünde kalan ilk parça (satır satır). */
            let once = null;
            for (const o of stSira.children) {
                if (o === c) continue;
                const r = o.getBoundingClientRect();
                if (ev.clientY < r.top || (ev.clientY <= r.bottom && ev.clientX < r.left + r.width / 2)) { once = o; break; }
            }
            if (once) { if (c.nextSibling !== once) stSira.insertBefore(c, once); }
            else if (stSira.lastChild !== c) stSira.appendChild(c);
            siraNumarala();
        };
        const bitir = () => {
            window.removeEventListener("pointermove", hareket);
            window.removeEventListener("pointerup", bitir);
            window.removeEventListener("pointercancel", bitir);
            c.classList.remove("surukleniyor");
            if (!oynadi) return;
            sira = [...stSira.children].map(x => x.dataset.yer);
            siraCiz(c.dataset.yer);
            if (JSON.stringify(sira) !== JSON.stringify(ilk)) onizle();
        };
        window.addEventListener("pointermove", hareket);
        window.addEventListener("pointerup", bitir);
        window.addEventListener("pointercancel", bitir);
    }
    function tasi(i, yon) {
        if (kilitli) return;
        const j = i + yon;
        if (j < 0 || j >= sira.length) return;
        [sira[i], sira[j]] = [sira[j], sira[i]];
        siraCiz(sira[j]);
        onizle();
    }
    /* Ad Standardı ya da ada eklenecek parça değişince adlar sunucuda
       yeniden kurulur (kaydedilmez). */
    function onizle() {
        const no = ++onizleSayac;
        stKap.classList.add("yukleniyor");
        ekKap.classList.add("yukleniyor");
        tkKap.classList.add("yukleniyor");
        dyKap.classList.add("yukleniyor");
        fetch(getWebAppBackendUrl("kolon_ad_onizle"), {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify(ftKimlikGovdesi({ sira: sira, eklenecekler: ekDeger(),
                                                   turler: Object.assign({}, turSecim),
                                                   donem_yazilis: dyDeger() }))
        })
        .then(r => r.json())
        .then(d => {
            if (no !== onizleSayac) return;
            const k = d && d.kolon_ad;
            if (!k) { tkYoklaKur(); return; }
            if (k.son_kontrol) skAl(k.son_kontrol);
            (k.donem_yazilis || []).forEach(x => {
                const y = dyler.find(z => dyAnahtar(z) === dyAnahtar(x));
                if (y) { y.hata = x.hata || ""; y.ornek_yeni = x.ornek_yeni || ""; y.ornekler = x.ornekler || []; }
            });
            const harita = {};
            (k.satirlar || []).forEach(r => { harita[r.aile] = r.kolonlar; });
            /* Ad değişen ailenin onayı kalkar (yeni adı görülmedi). */
            satirlar.forEach(r => {
                const yeni = harita[r.aile];
                if (!yeni) return;
                if (JSON.stringify(yeni) !== JSON.stringify(r.kolonlar) && r.secim === "yeni") r.onay = false;
                r.kolonlar = yeni;
            });
            (k.eklenecekler || []).forEach(e => {
                const x = ekler.find(y => y.anahtar === e.anahtar);
                if (x) x.gecerli = !!e.gecerli;
            });
            /* Sıradaki odak (klavyeyle taşıma sürerken) yeniden çizimde kalır. */
            const odakYer = stSira.contains(document.activeElement) ? document.activeElement.dataset.yer : null;
            tabloCiz(); siraCiz(odakYer); ekCiz(); tkCiz(); dyNotlar();
            if (degisti) degisti();
            tkYoklaKur();
        })
        .catch(() => { tkYoklaKur(); })
        .then(() => { if (no === onizleSayac) { stKap.classList.remove("yukleniyor"); ekKap.classList.remove("yukleniyor"); tkKap.classList.remove("yukleniyor"); dyKap.classList.remove("yukleniyor"); } });
    }

    /* ---- DÖNEM YAZILIŞLARI ----
       01.2.4.1'de onaylanan dönem kalıplarının yeni addaki yazılışı (ör.
       [sayı]D için L[sayı]D: 30D yeni adda L30D). Yazılış değişince adlar
       hemen yeniden kurulur; boşsa kalıp aynen kalır. Onayda hafızaya
       yazılır. dyler: [{kalip, deger (ekrandaki), ornek, ornek_yeni, hata,
       kolon}]. */
    const dyler = (ka.donem_yazilis || []).map(x => Object.assign({}, x, { deger: donemAdGoster(x.yazilis) }));
    /* Satır anahtarı: birimli kalıpta kalıp ve anlam türü ("<N>D|son"),
       ötekilerde kalıp. */
    const dyAnahtar = x => x.anahtar || x.kalip;
    const dyKap = elYap("div", "dg-kad-ek dg-kad-dy");
    dyKap.hidden = !dyler.length;
    kart.appendChild(dyKap);
    const dyDeger = () => {
        const o = {};
        dyler.forEach(x => { if (!x.belirsiz) o[dyAnahtar(x)] = donemAdIc(x.kalip, x.deger); });
        return o;
    };
    const dyHata = x => donemAdHatasi(x.kalip, x.deger);
    const dyNotEl = {};
    /* ÖRNEK KOLONLAR (i balonu): kalıbın geçtiği 3 kolon; eski ad, bu
       kartın kurduğu yeni ad (yazılış, standart sıra ve eklenecekler
       uygulanmış) ve 01.2.4.3'te onaylanan açıklama. Adlar kurulunca
       (önizleme) yenilenir. */
    const dyOrnEl = {};
    function dyOrnekYaz(x) {
        const kap = dyOrnEl[dyAnahtar(x)];
        if (!kap) return;
        kap.textContent = "";
        const orn = x.ornekler || [];
        if (!orn.length) return;
        const i_ = bolmeBilgiSimgesi(orn.map(([eski, dg, yeni, ac]) => eski + "\nYeni ad: " + yeni
            + "\nAçıklaması: " + (ac ? tireSade(ac) : "Sözlükte açıklaması yok.")).join("\n\n"),
            donemSayiGoster(x.kalip) + " geçen " + ftBinlik(x.kolon || 0) + " kolon"
            + (orn.length < (x.kolon || 0) ? "dan " + orn.length + " örnek" : ""));
        i_.classList.add("bolme-info-genis");
        kap.appendChild(i_);
    }
    /* YÖN EKSİĞİ: Dönem Bilgisi'ndeki anlamın yönü (son, önce, sonra)
       yeni addaki yazılışta da yoksa satırda uyarı, başlıkta sayı. */
    const dyYonEksik = x => {
        const ic = donemAdIc(x.kalip, x.deger) || x.kalip;
        const onek = new Set([...String(ic).matchAll(/([A-Z]+)<N/g)].map(m => m[1]));
        return (x.yon_eksik || []).filter(e => !(e.harfler || []).some(h => onek.has(h)));
    };
    const dyYonEl = {};
    let dyUyariEl = null;
    function dyYonTazele() {
        if (!dyUyariEl) return;
        const n = dyler.filter(x => dyYonEksik(x).length).length;
        dyUyariEl.hidden = !n;
        dyUyariEl.textContent = n ? ftBinlik(n) + " kalıbın Dönem Bilgisi'ndeki anlamında yeni adda "
            + "olmayan yön bilgisi var (son, önce, sonra); satırdaki öneriyi kullanabilir ya da "
            + "yazılışı kendiniz belirleyebilirsiniz. Yazılış boş kalırsa adlar bu bilgiyi taşımaz." : "";
    }
    function dyNotYaz(x) {
        const el = dyNotEl[dyAnahtar(x)];
        if (!el) return;
        const h = dyHata(x);
        el.classList.toggle("dg-donem-ad-hata", !!h);
        const tr = el.closest("tr");
        if (tr) tr.classList.toggle("dg-donem-dikkat", !!h);
        const ic = donemAdIc(x.kalip, x.deger);
        el.textContent = h ? h
            : !ic ? "Kalıp yeni adda aynen kalır" + (x.ornek ? " (ör. " + x.ornek + ")." : ".")
            : x.ornek ? "Ör. " + x.ornek + " → " + donemAdDoldur(x.kalip, ic, x.ornek) : "";
        const yel = dyYonEl[dyAnahtar(x)];
        if (yel) {
            const eksik = dyYonEksik(x);
            const anlam = x.anlam ? " (Dönem Bilgisi'ndeki anlam: «" + donemAnlamGoster(x.kalip, x.anlam) + "»)" : "";
            yel.textContent = "";
            yel.className = "dg-donem-tur-not";
            if (eksik.length) {
                yel.classList.add("dg-donem-yon-eksik");
                yel.appendChild(document.createTextNode("Anlamdaki " + eksik.map(e => "«" + e.sozcuk + "»").join(", ")
                    + " bilgisi bu yazılışta yok" + anlam + "."));
                if (x.oneri && !kilitli && donemAdIc(x.kalip, x.deger) !== x.oneri) {
                    const b = elYap("button", "dg-toplu-btn dg-dy-oneri", "Öneriyi Yaz: " + donemSayiGoster(x.oneri));
                    b.type = "button";
                    b.onclick = () => {
                        x.deger = donemAdGoster(x.oneri);
                        const gi = el.closest("td") && el.closest("td").querySelector("input");
                        if (gi) gi.value = x.deger;
                        dyNotYaz(x); dyYonTazele();
                        if (degisti) degisti();
                        if (!dyHata(x)) onizle();
                    };
                    yel.appendChild(b);
                }
            } else if (x.oneri_dolu && donemAdIc(x.kalip, x.deger) === x.oneri) {
                yel.textContent = "Önerildi: anlamdaki " + (x.yon_eksik || []).map(e => "«" + e.sozcuk + "»").join(", ")
                    + " bilgisi eski yazılışta yoktu" + anlam + ". Değiştirebilirsiniz.";
            }
        }
        dyYonTazele();
    }
    const dyNotlar = () => dyler.forEach(x => { dyNotYaz(x); dyOrnekYaz(x); });
    function dyCiz() {
        dyKap.textContent = "";
        if (!dyler.length) return;
        const bas = elYap("div", "dg-kad-standart-bas");
        const baslik = elYap("span", "dg-kad-standart-ad", "Dönem Yazılışları · " + ftBinlik(dyler.length));
        baslik.appendChild(bolmeBilgiSimgesi("Dönem Bilgisi'nde onaylanan kalıpların yeni adlardaki "
            + "yazılışı. Kalıbın sayıları yerine [sayı] yazın; sırayla kalıbın sayıları gelir. Ör. "
            + "[sayı]D için L[sayı]D yazılırsa 30D yeni adda L30D olur; [sayı]D_[sayı]D için "
            + "BTWN_[sayı]D_[sayı]D yazılırsa 3D_6D yeni adda BTWN_3D_6D olur. Sayıları kutunun "
            + "altındaki düğmelerle de ekleyebilirsiniz; imlecin olduğu yere boşluksuz eklenir. Aynı sayıyı tekrar "
            + "yazmak için [sayı 1], [sayı 2]; hesap için [sayı 1 × sayı 2] yazın (ör. [sayı]D_X[sayı] "
            + "için L[sayı 1]D_P[sayı 1 × sayı 2]D ile 7D_X2 yeni adda L7D_P14D olur). Boş bırakılırsa "
            + "kalıp aynen kalır. Kolonlar'daki i'de kalıbın geçtiği 3 kolon, eski ve yeni adıyla ve "
            + "Kolon Kartları'nda onaylanan açıklamasıyla görünür (yeni ad bu karttaki yazılış, Ad Standardı "
            + "ve eklenecek parçalarla kurulur). Yazılışı değiştirince aşağıdaki adlar hemen yeniden kurulur; "
            + "onaylayınca hafızaya yazılır ve sonraki çalışmalarda dolu gelir. Girdi veri setiniz ve "
            + "sözlüğünüz değişmez.", "Dönem Yazılışları"));
        bas.append(baslik, elYap("span", "dg-donem-tur-not", "Kalıbın yeni addaki yazılışı; boşsa aynen kalır."));
        dyKap.appendChild(bas);
        dyUyariEl = elYap("div", "dg-donem-uyari dg-dy-uyari", "");
        dyUyariEl.hidden = true;
        dyKap.appendChild(dyUyariEl);
        const turlu = dyler.some(x => x.tur);
        const t = elYap("table", "dg-tablo dg-kad-dy-tablo" + (turlu ? " dg-kad-dy-turlu" : ""));
        const h = document.createElement("thead"), hr = document.createElement("tr");
        (turlu ? ["Kalıp", "Anlam", "Kolonlar", "Yeni Adda"] : ["Kalıp", "Kolonlar", "Yeni Adda"])
            .forEach(x => hr.appendChild(elYap("th", "", x)));
        h.appendChild(hr); t.appendChild(h);
        const b = document.createElement("tbody");
        dyler.forEach(x => {
            const tr = elYap("tr", "dg-satir" + (x.belirsiz ? " dg-dy-belirsiz" : ""));
            tr.appendChild(elYap("td", "dg-kolon", donemSayiGoster(x.kalip)));
            /* ANLAM: birimli kalıpta her anlam türü ayrı satır, ayrı
               yazılış (son: L[sayı]D, sonraki: N[sayı]D, sonra: A[sayı]D
               ...); altında kapsadığı günler. */
            if (turlu) {
                const tdT = elYap("td", "");
                if (x.tur) {
                    tdT.appendChild(elYap("b", "", x.tur_ad || ""));
                    tdT.appendChild(elYap("div", "dg-kad-dy-tur", donemAnlamGoster(x.kalip, x.tur_anlam || "")));
                    if (x.tur_kapsam) tdT.appendChild(elYap("div", "dg-kad-dy-tur",
                                                            donemAnlamGoster(x.kalip, x.tur_kapsam)));
                } else tdT.appendChild(elYap("span", "dg-kad-dy-tur", donemAnlamGoster(x.kalip, x.anlam || "")));
                tr.appendChild(tdT);
            }
            const tdK = elYap("td", "", ftBinlik(x.kolon || 0) + " kolon" + (x.ornek ? " · ör. " + x.ornek : ""));
            const ornKap = elYap("span", "dg-kad-dy-orn");
            dyOrnEl[dyAnahtar(x)] = ornKap;
            tdK.appendChild(ornKap);
            tr.appendChild(tdK);
            const td = elYap("td", "");
            const g = document.createElement("input");
            g.type = "text"; g.className = "dg-giris dg-donem-ad-giris";
            g.value = x.deger || "";
            g.placeholder = "Boş: kalıp aynen";
            g.disabled = kilitli || !!x.belirsiz;
            /* BELİRSİZ: 01.2.4.3'te dönem anlamı seçilmeyen kolonlar; dönem
               kısmı aynen kalır (yazılış verilmez). */
            if (x.belirsiz) {
                td.appendChild(elYap("div", "dg-donem-tur-not", "Bu kolonlarda dönemin anlamı belirlenmedi; "
                    + "adda dönem kısmı aynen kalır. Anlamı 01.2.4.3 Kolon Kartları'nda seçebilirsiniz."));
                tr.appendChild(td);
                b.appendChild(tr);
                dyOrnekYaz(x);
                return;
            }
            g.setAttribute("aria-label", donemSayiGoster(x.kalip) + " yeni adda yazılış");
            const not = elYap("div", "dg-donem-tur-not", "");
            dyNotEl[dyAnahtar(x)] = not;
            const yonNot = elYap("div", "dg-donem-tur-not", "");
            dyYonEl[dyAnahtar(x)] = yonNot;
            /* Kutudan çıkınca adlar yeniden kurulur (geçersizse kurulmaz).
               Sayı ekle düğmesiyle yapılan değişiklik "change" doğurmaz;
               bu yüzden değişiklik işaretlenir, kutudan çıkınca bakılır. */
            let kirli = false;
            g.oninput = () => { x.deger = g.value; kirli = true; dyNotYaz(x); if (degisti) degisti(); };
            g.onblur = () => { if (kirli && !dyHata(x)) { kirli = false; onizle(); } };
            td.append(g);
            if (!kilitli) td.appendChild(donemSayiDugmeleri(() => x.kalip, g, true));
            td.appendChild(not);
            td.appendChild(yonNot);
            tr.appendChild(td);
            tr.classList.toggle("dg-donem-dikkat", !!dyHata(x));
            b.appendChild(tr);
            dyNotYaz(x);
            dyOrnekYaz(x);
        });
        t.appendChild(b);
        const sar_ = elYap("div", "dg-tablo-sar");
        sar_.appendChild(t);
        dyKap.appendChild(sar_);
    }

    /* ---- SON KONTROL: PARÇA TÜRLERİ ----
       Tür 01.2.4.2'de seçilmez (arka planda). Adlar kurulunca dil modeli
       her parçanın türünü yeni addaki yerine ve Kolon Kartları'nda
       onaylanan açıklamaya göre denetler; açıkça yanlış olanı düzeltir ve
       adlar düzeltilmiş türle kurulur. Her düzeltmede tür değiştirilebilir
       (önceki türe dönmek dahil); başka bir parçanın türü de buradan
       değiştirilebilir. turSecim: parca -> tür (dil modelinin düzeltmeleri
       ve kullanıcının seçimleri; sunucuya gider). */
    let sk = ka.son_kontrol || null;
    const turSecim = Object.assign({}, (sk && sk.secim) || {});
    const elle = new Set(Object.keys(turSecim).filter(p => !((sk && sk.oneriler) || []).some(o => o.parca === p)));
    const tkKap = elYap("div", "dg-kad-ek dg-kad-tur");
    tkKap.hidden = !sk;
    kart.appendChild(tkKap);
    const tkTurAdi = k => (((sk && sk.turler) || []).find(t => t.kod === k) || {}).ad || k;
    const tkSuruyor = () => !!(sk && sk.durum === "calisiyor") && !kilitli;
    function skAl(yeni) {
        sk = yeni;
        /* Yeni gelen düzeltme kullanıcının seçimi yoksa kendiliğinden geçerli. */
        (sk.oneriler || []).forEach(o => {
            if (!(o.parca in turSecim)) turSecim[o.parca] = o.oneri;
            elle.delete(o.parca);
        });
    }
    let tkYokla = null;
    function tkYoklaKur() {
        /* Kart ilk çizimde henüz sayfada değil; sayfadan kalkmışsa yoklama durur. */
        if (tkYokla || !tkSuruyor()) return;
        tkYokla = setTimeout(() => { tkYokla = null; if (tkSuruyor() && tkKap.isConnected) onizle(); }, 3000);
    }
    function tkSecimDegis(p, t) {
        if (kilitli || turSecim[p] === t) return;
        turSecim[p] = t;
        tkCiz(); onizle();
    }
    function tkCiz() {
        tkKap.textContent = "";
        tkKap.hidden = !sk;
        if (!sk) return;
        const oneriler = sk.oneriler || [];
        const parcalar = sk.parcalar || [];
        const bas = elYap("div", "dg-kad-standart-bas");
        const baslik = elYap("span", "dg-kad-standart-ad", "Son Kontrol: Parça Türleri");
        baslik.appendChild(bolmeBilgiSimgesi("Parçanın türü (konu, ölçü, istatistik gibi) yeni addaki "
            + "yerini belirler. Tür Ad Parçaları'nda seçilmez; burada dil modeli her parçanın türünü "
            + "yeni addaki yerine ve Kolon Kartları'nda onayladığınız açıklamaya bakarak denetler, "
            + "açıkça yanlış olanı düzeltir. Adlar düzeltilmiş türle kurulur. Bir düzeltmeyi "
            + "beğenmezseniz türü seçip değiştirin (önceki türüne dönmek dahil). Başka bir parçanın "
            + "türünü de alttan değiştirebilirsiniz. Onaylayınca türler proje hafızasına yazılır.",
            "Son Kontrol"));
        bas.appendChild(baslik);
        let durumMetni;
        if (kilitli) durumMetni = (sk.uygulanan || []).length ? "Onayda türü değişen parçalar:"
            : oneriler.length || elle.size ? "" : "Türlerde değişiklik yapılmadı.";
        else if (sk.durum === "calisiyor")
            durumMetni = "Dil modeli parça türlerini yeni adlar ve onaylı açıklamalarla karşılaştırıyor: "
                + ftBinlik(sk.biten || 0) + " / " + ftBinlik(sk.toplam || 0) + ". Bitince adlar gerekirse "
                + "yeniden kurulur.";
        else if (sk.durum === "yok") durumMetni = "";
        else if (oneriler.length)
            durumMetni = "Dil modeli " + ftBinlik(oneriler.length) + " parçanın türünü düzeltti; adlar "
                + "düzeltilmiş türle kuruldu. Uymayanı aşağıdan değiştirin.";
        else durumMetni = sk.hata && !sk.toplam ? "" : "Bütün parça türleri yeni adlar ve onaylı açıklamalarla uyumlu.";
        if (!kilitli && sk.hata) durumMetni = (durumMetni ? durumMetni + " " : "")
            + "Dil modeli bazı parçalara bakamadı; onların türü Ad Parçaları'ndaki gibi kaldı.";
        if (durumMetni) bas.appendChild(elYap("span", "dg-donem-tur-not", durumMetni));
        tkKap.appendChild(bas);
        /* Onaylanmış kart: onayda değişen türler (kayıttan). */
        if (kilitli && (sk.uygulanan || []).length) {
            const t = elYap("table", "dg-tablo dg-kad-tur-tablo");
            const h = document.createElement("thead"), hr = document.createElement("tr");
            ["Parça", "Anlam", "Tür", "Neden"].forEach(x => hr.appendChild(elYap("th", "", x)));
            h.appendChild(hr); t.appendChild(h);
            const b = document.createElement("tbody");
            sk.uygulanan.forEach(x => {
                const tr = elYap("tr", "dg-satir");
                tr.append(elYap("td", "dg-kolon", x.parca), elYap("td", "", tireSade(x.anlam || "")),
                          elYap("td", "", tkTurAdi(x.eski) + " yerine " + tkTurAdi(x.yeni)),
                          elYap("td", "", x.kaynak === "dil_modeli" ? tireSade(x.neden || "Dil modelinin düzeltmesi.")
                                : "Sizin değişikliğiniz."));
                b.appendChild(tr);
            });
            t.appendChild(b);
            const sar_ = elYap("div", "dg-tablo-sar");
            sar_.appendChild(t);
            tkKap.appendChild(sar_);
            return;
        }
        const satirP = oneriler.map(o => o.parca).concat(Array.from(elle).filter(p => !oneriler.some(o => o.parca === p)));
        if (satirP.length) {
            const t = elYap("table", "dg-tablo dg-kad-tur-tablo");
            const h = document.createElement("thead"), hr = document.createElement("tr");
            ["Parça", "Anlam", "Tür", "Neden"].forEach(x => hr.appendChild(elYap("th", "", x)));
            h.appendChild(hr); t.appendChild(h);
            const b = document.createElement("tbody");
            satirP.forEach(p => {
                const o = oneriler.find(x => x.parca === p);
                const pb = parcalar.find(x => x.parca === p) || {};
                const eski = o ? o.eski : pb.tur;
                const tr = elYap("tr", "dg-satir");
                const t1 = elYap("td", "dg-kolon");
                const ad = elYap("div", "dg-kad-ad", p);
                if (o && (o.ornek || []).length) ad.appendChild(bolmeBilgiSimgesi(
                    "Baktığı kolonlar (eski ad → yeni ad):\n" + o.ornek.join("\n"), p));
                t1.appendChild(ad);
                const t2 = elYap("td", "", tireSade((o ? o.anlam : pb.anlam) || ""));
                const t3 = elYap("td", "");
                const sec = document.createElement("select");
                sec.className = "dg-donem-tur dg-kad-tur-sec";
                sec.setAttribute("aria-label", p + " türü");
                (sk.turler || []).forEach(x => {
                    const op = document.createElement("option");
                    op.value = x.kod;
                    op.textContent = x.ad + (x.kod === eski ? " (önceki)" : "");
                    sec.appendChild(op);
                });
                sec.value = turSecim[p] || eski || "";
                sec.disabled = kilitli;
                sec.onchange = () => tkSecimDegis(p, sec.value);
                t3.appendChild(sec);
                const t4 = elYap("td", "");
                if (o) {
                    t4.appendChild(elYap("div", "dg-donem-tur-not", "Dil modeli: " + tkTurAdi(o.eski)
                        + " yerine " + tkTurAdi(o.oneri)));
                    if (o.neden) t4.appendChild(elYap("div", "", tireSade(o.neden)));
                } else {
                    t4.appendChild(elYap("div", "dg-donem-tur-not", "Sizin değişikliğiniz; önceki türü "
                        + tkTurAdi(eski) + "."));
                    if (!kilitli) {
                        const kal = elYap("button", "dg-baglanti", "Değişikliği Kaldır");
                        kal.type = "button";
                        kal.onclick = () => { delete turSecim[p]; elle.delete(p); tkCiz(); onizle(); };
                        t4.appendChild(kal);
                    }
                }
                tr.append(t1, t2, t3, t4);
                tr.classList.toggle("dg-parca-onayli", !!o && turSecim[p] === o.oneri);
                b.appendChild(tr);
            });
            t.appendChild(b);
            const sar_ = elYap("div", "dg-tablo-sar");
            sar_.appendChild(t);
            tkKap.appendChild(sar_);
        }
        /* Başka bir parçanın türünü değiştir. */
        const kalanP = parcalar.filter(x => !satirP.includes(x.parca));
        if (!kilitli && sk.durum !== "calisiyor" && kalanP.length) {
            const ekS = elYap("div", "dg-kad-tur-ekle");
            const ps = document.createElement("select");
            ps.className = "dg-donem-tur";
            ps.setAttribute("aria-label", "Türü değişecek parça");
            const ilk = document.createElement("option");
            ilk.value = ""; ilk.textContent = "Parça seçin";
            ps.appendChild(ilk);
            kalanP.forEach(x => {
                const op = document.createElement("option");
                op.value = x.parca; op.textContent = x.parca + " · " + tireSade(x.anlam) + " · " + tkTurAdi(x.tur);
                ps.appendChild(op);
            });
            const bt = elYap("button", "dg-toplu-btn", "Türünü Değiştir");
            bt.type = "button"; bt.disabled = true;
            ps.onchange = () => { bt.disabled = !ps.value; };
            bt.onclick = () => {
                const x = kalanP.find(y => y.parca === ps.value);
                if (!x || kilitli) return;
                elle.add(x.parca);
                turSecim[x.parca] = x.tur;
                tkCiz();
                const sel = tkKap.querySelector('select[aria-label="' + CSS.escape(x.parca) + ' türü"]');
                if (sel) sel.focus();
            };
            ekS.append(elYap("span", "dg-donem-tur-not", "Başka bir parçanın türü yanlışsa:"), ps, bt);
            tkKap.appendChild(ekS);
        }
    }

    /* ---- ADA EKLENECEK PARÇALAR ----
       Kolon Kartları'nda açıklamada olup adda karşılığı olmayan kısa
       bilgiler. Her birinde kısaltma, Ekle / Ekleme ve onay. */
    const ekler = (ka.eklenecekler || []).map(e => Object.assign({}, e));
    const ekKap = elYap("div", "dg-kad-ek");
    ekKap.hidden = !ekler.length;
    kart.appendChild(ekKap);
    const KAYNAK_ADI = { parca: "onaylı ad parçalarından", hafiza: "parça hafızasından",
                         dil_modeli: "dil modelinin önerisi" };
    const ekDeger = () => ekler.map(e => ({ anahtar: e.anahtar, kisaltma: e.kisaltma,
                                            secim: e.secim, onay: !!e.onay }));
    const ekGecerli = e => e.secim === "ekleme" || /^[A-Z][A-Z0-9]{0,11}$/.test(e.kisaltma || "");
    function ekCiz() {
        ekKap.textContent = "";
        if (!ekler.length) return;
        const bas = elYap("div", "dg-kad-standart-bas");
        bas.append(elYap("span", "dg-kad-standart-ad", "Ada Eklenecek Parçalar · " + ftBinlik(ekler.length)),
                   elYap("span", "dg-donem-tur-not", "Kolon Kartları'nda açıklamada olup adda karşılığı olmayan "
                         + "bilgiler. Kısaltmayı kontrol edin, «Ekle» ya da «Ekleme» seçip onaylayın."));
        /* TOPLU ONAY: onaylanmamış ve onaylanabilir (kısaltması geçerli ya
           da «Ekleme» seçili) satırlar seçili hâliyle onaylanır; kısaltması
           geçersiz olan atlanır. */
        const ekOnaylanir = ekler.filter(e => !e.onay && ekGecerli(e));
        const ekAtlanan = ekler.filter(e => !e.onay && !ekGecerli(e)).length;
        if (ekOnaylanir.length || ekAtlanan) {
            const hb = elYap("button", "dg-toplu-btn", "Hepsini Onayla · " + ftBinlik(ekOnaylanir.length));
            hb.type = "button";
            hb.disabled = kilitli || !ekOnaylanir.length;
            hb.title = "Onaylanmamış satırlar seçili hâliyle («Ekle» ya da «Ekleme») onaylanır."
                + (ekAtlanan ? " Kısaltması geçersiz " + ftBinlik(ekAtlanan) + " satır atlanır; önce kısaltmasını düzeltin." : "");
            hb.onclick = () => {
                if (kilitli) return;
                ekOnaylanir.forEach(e => { e.onay = true; });
                ekCiz(); if (degisti) degisti();
            };
            bas.appendChild(hb);
            if (ekAtlanan) bas.appendChild(elYap("span", "dg-donem-soru", ftBinlik(ekAtlanan)
                + " satırın kısaltması geçersiz; düzeltmeden onaylanamaz."));
        }
        ekKap.appendChild(bas);
        const t = elYap("table", "dg-tablo dg-kad-ek-tablo");
        const h = document.createElement("thead"), hr = document.createElement("tr");
        ["Bilgi", "Kolonlar", "Kısaltma", "Karar", "Onay"].forEach(x => hr.appendChild(elYap("th", "", x)));
        h.appendChild(hr); t.appendChild(h);
        const b = document.createElement("tbody");
        ekler.forEach(e => {
            const tr = elYap("tr", "dg-satir");
            const t1 = elYap("td", "");
            t1.append(elYap("div", "dg-kad-ad", e.anlam), elYap("div", "dg-donem-tur-not", e.tur_ad || e.tur));
            const t2 = elYap("td", "");
            t2.append(elYap("div", "", ftBinlik(e.kolon_sayisi) + " kolon"),
                      elYap("div", "dg-donem-tur-not", (e.ornek || []).join(", ")
                            + (e.kolon_sayisi > (e.ornek || []).length ? " ve diğerleri" : "")));
            const t3 = elYap("td", "");
            const g = document.createElement("input");
            g.type = "text"; g.className = "dg-giris dg-kad-ek-giris";
            g.value = e.kisaltma || ""; g.maxLength = 12;
            g.disabled = kilitli || e.secim === "ekleme";
            g.setAttribute("aria-label", e.anlam + " kısaltması");
            g.onchange = () => {
                const v = g.value.trim().toLocaleUpperCase("tr").replace(/[^A-Z0-9]/g, "");
                g.value = v;
                if (v === e.kisaltma) return;
                e.kisaltma = v; e.onay = false;
                ekCiz(); onizle();
            };
            t3.appendChild(g);
            t3.appendChild(elYap("div", "dg-donem-tur-not", e.oneri
                ? "Öneri: " + e.oneri + " (" + (KAYNAK_ADI[e.kaynak] || "öneri") + ")"
                : "Kısaltma bulunamadı; yazın."));
            if (e.secim === "ekle" && !ekGecerli(e)) t3.appendChild(elYap("div", "dg-donem-soru",
                "Büyük harfle başlamalı; en çok 12 harf ve rakam."));
            const t4 = elYap("td", "");
            const seg = elYap("div", "dg-segment");
            [["ekle", "Ekle"], ["ekleme", "Ekleme"]].forEach(([dd, aa]) => {
                const bt = elYap("button", e.secim === dd ? "secili" : "", aa);
                bt.type = "button"; bt.disabled = kilitli;
                bt.setAttribute("aria-pressed", e.secim === dd ? "true" : "false");
                bt.onclick = () => {
                    if (kilitli || e.secim === dd) return;
                    e.secim = dd; e.onay = false;
                    ekCiz(); onizle();
                };
                seg.appendChild(bt);
            });
            t4.appendChild(seg);
            const t5 = elYap("td", "dg-ekle-hucre");
            const k = document.createElement("input");
            k.type = "checkbox"; k.className = "dg-ekle";
            k.checked = !!e.onay; k.disabled = kilitli || (!e.onay && !ekGecerli(e));
            k.setAttribute("aria-label", e.anlam + " onay");
            k.onchange = () => { if (kilitli) { k.checked = !k.checked; return; } e.onay = k.checked; ekCiz(); if (degisti) degisti(); };
            t5.appendChild(k);
            tr.append(t1, t2, t3, t4, t5);
            tr.classList.toggle("dg-parca-onayli", !!e.onay);
            b.appendChild(tr);
        });
        t.appendChild(b);
        const sar_ = elYap("div", "dg-tablo-sar");
        sar_.appendChild(t);
        ekKap.appendChild(sar_);
    }

    /* ---- ÜST: arama, süzgeç, toplu onay, sayfa ---- */
    const ust = elYap("div", "dg-tablo-ust dg-parca-ust");
    const ara = document.createElement("input");
    ara.type = "search"; ara.className = "dg-giris dg-parca-ara";
    ara.placeholder = "Kolon adı ara";
    ara.setAttribute("aria-label", "Kolon adı ara");
    const suz = document.createElement("select");
    suz.className = "dg-parca-suz";
    suz.setAttribute("aria-label", "Süzgeç");
    [["hepsi", "Tümü"], ["onaysiz", "Onaylanmadı"], ["degisen", "Adı Değişen"],
     ["ayni", "Adı Aynı Kalan"], ["sorun", "Sorunlu"]].forEach(([d, a]) => {
        const o = document.createElement("option"); o.value = d; o.textContent = a; suz.appendChild(o); });
    /* TOPLU ONAY (bütün sayfalar): arama ve süzgeçle görünen listenin
       sorunu olmayan, onaylanmamış aileleri seçili hâliyle (Yeni Ad ya da
       Eski Ad Kalsın) onaylanır; sorunlu aile atlanır. */
    const gorOnay = elYap("button", "dg-toplu-btn", "");
    gorOnay.type = "button";
    const sayfaEl = elYap("div", "dg-parca-sayfa");
    ust.append(ara, suz, gorOnay, sayfaEl);
    kart.appendChild(ust);
    if (korunan.length) kart.appendChild(elYap("div", "dg-donem-tur-not",
        "Yeniden adlandırılmayan rol kolonları: " + korunan.join(", ") + "."));
    const sar = elYap("div", "dg-tablo-sar dg-parca-sar");
    const tablo = elYap("table", "dg-tablo dg-kolonad-tablo dg-kad-tablo");
    const th = document.createElement("thead"), hr = document.createElement("tr");
    ["Eski Ad", "Yeni Ad", "Karar", "Onay"].forEach(h => hr.appendChild(elYap("th", "", h)));
    th.appendChild(hr); tablo.appendChild(th);
    const tb = document.createElement("tbody");
    tablo.appendChild(tb); sar.appendChild(tablo); kart.appendChild(sar);
    let sayfa = 0;
    ara.addEventListener("input", () => { sayfa = 0; tabloCiz(); });
    suz.addEventListener("change", () => { sayfa = 0; tabloCiz(); });

    /* SORUNLAR: yeni ad geçersiz, iki kolon aynı adı alıyor ya da yeni ad
       adı değişmeyen başka bir kolonun adı. */
    function sorunlar() {
        const sonAd = new Map(), say = new Map(), sor = {};
        satirlar.forEach(r => r.kolonlar.forEach(([e, y]) => {
            const ad = r.secim === "eski" ? e : y;
            sonAd.set(e, ad);
            say.set(ad, (say.get(ad) || 0) + 1);
        }));
        korunan.forEach(k => say.set(k, (say.get(k) || 0) + 1));
        satirlar.forEach(r => {
            const m = [];
            r.kolonlar.forEach(([e, y]) => {
                const ad = sonAd.get(e);
                if (!KAD_AD.test(ad)) m.push(ad + ": harfle başlamalı; yalnız harf, rakam ve _");
                else if (say.get(ad) > 1) m.push(ad + " adını birden fazla kolon alıyor");
            });
            if (m.length) sor[r.aile] = m.slice(0, 3).join(". ") + (m.length > 3 ? " ve " + (m.length - 3) + " sorun daha" : "") + ".";
        });
        return sor;
    }
    const degisir = r => r.kolonlar.some(([e, y]) => e !== y);
    function gorunen() {
        const sor = sorunlar();
        const q = ara.value.trim().toLocaleUpperCase("tr");
        const sz = suz.value;
        return { sor, liste: satirlar.filter(r => {
            if (q && !r.kolonlar.some(([e, y]) => e.toLocaleUpperCase("tr").includes(q)
                                      || y.toLocaleUpperCase("tr").includes(q))) return false;
            if (sz === "onaysiz") return !r.onay;
            if (sz === "degisen") return degisir(r);
            if (sz === "ayni") return !degisir(r);
            if (sz === "sorun") return !!sor[r.aile];
            return true;
        }) };
    }
    function tabloCiz() {
        const { sor, liste } = gorunen();
        const sayfaSay = Math.max(1, Math.ceil(liste.length / KAD_SAYFA));
        if (sayfa >= sayfaSay) sayfa = sayfaSay - 1;
        const parca = liste.slice(sayfa * KAD_SAYFA, (sayfa + 1) * KAD_SAYFA);
        tb.textContent = "";
        parca.forEach(r => tb.appendChild(satirCiz(r, sor[r.aile])));
        if (!parca.length) {
            const tr = elYap("tr", "dg-bos-tablo");
            const td = elYap("td", "", satirlar.length ? "Bu süzgeçte aile yok." : "Yeniden adlandırılacak kolon yok.");
            td.colSpan = 4; tr.appendChild(td); tb.appendChild(tr);
        }
        sayfaEl.textContent = "";
        if (liste.length > KAD_SAYFA) {
            const geri = elYap("button", "dg-toplu-btn", "Önceki");
            geri.type = "button"; geri.disabled = sayfa === 0;
            geri.onclick = () => { sayfa--; tabloCiz(); };
            const ileri = elYap("button", "dg-toplu-btn", "Sonraki");
            ileri.type = "button"; ileri.disabled = sayfa >= sayfaSay - 1;
            ileri.onclick = () => { sayfa++; tabloCiz(); };
            sayfaEl.append(geri, elYap("span", "dg-parca-sayfa-no",
                ftBinlik(sayfa * KAD_SAYFA + 1) + " ile " + ftBinlik(Math.min(liste.length, (sayfa + 1) * KAD_SAYFA))
                + " arası · " + ftBinlik(liste.length)), ileri);
        }
        const onaylanir = liste.filter(r => !r.onay && !sor[r.aile]);
        const sorunlu = liste.filter(r => !r.onay && sor[r.aile]).length;
        const suzulu = !!ara.value.trim() || suz.value !== "hepsi";
        gorOnay.textContent = (suzulu ? "Bu Listedekilerin Hepsini Onayla" : "Sorunsuzların Hepsini Onayla")
            + " · " + ftBinlik(onaylanir.length);
        gorOnay.title = (suzulu ? "Arama ve süzgeçle listelenen" : "Bütün") + " sayfalardaki onaylanmamış ve "
            + "sorunu olmayan " + ftBinlik(onaylanir.length) + " aile seçili hâliyle (Yeni Ad ya da Eski Ad Kalsın) onaylanır."
            + (sorunlu ? " Sorunlu " + ftBinlik(sorunlu) + " aile atlanır; süzgeçte «Sorunlu»yu seçip tek tek bakın." : "");
        gorOnay.disabled = kilitli || !onaylanir.length;
        gorOnay.onclick = () => {
            if (kilitli) return;
            onaylanir.forEach(r => { r.onay = true; });
            tabloCiz(); if (degisti) degisti();
        };
    }
    function satirCiz(r, sorun) {
        const tr = elYap("tr", "dg-satir dg-kad-satir");
        const ilk = r.kolonlar[0] || ["", ""];
        const n = r.kolonlar.length;
        const tdE = elYap("td", "dg-kolon");
        tdE.appendChild(elYap("div", "dg-kad-ad", ilk[0]));
        const tdY = elYap("td", "");
        const yeniAd = elYap("div", "dg-kad-ad" + (r.secim === "eski" ? " dg-kad-pasif" : ""), ilk[1]);
        tdY.appendChild(yeniAd);
        if (n > 1) {
            const ac = elYap("button", "dg-baglanti dg-kad-aile", "Ailede " + ftBinlik(n) + " kolon");
            ac.type = "button";
            ac.title = "Adı yalnız sayılarla ayrılan kolonlar; hepsi aynı kurala göre adlandırılır.";
            let acik = null;
            ac.onclick = () => {
                if (acik) { acik.remove(); acik = null; return; }
                acik = elYap("tr", "dg-donem-detay");
                const td = elYap("td", "");
                td.colSpan = 4;
                const kutu = elYap("div", "dg-parca-ornek");
                r.kolonlar.forEach(([e, y]) => {
                    const s = elYap("div", "dg-parca-ornek-satir");
                    s.append(elYap("span", "dg-parca-ornek-kolon", e), elYap("span", "", r.secim === "eski" ? e : y));
                    kutu.appendChild(s);
                });
                td.appendChild(kutu); acik.appendChild(td);
                tr.after(acik);
            };
            tdE.appendChild(ac);
        }
        if (ilk[0] === ilk[1] && n === 1) tdY.appendChild(elYap("div", "dg-donem-tur-not", "Ad standarda uygun; aynı kalır."));
        if (sorun) tdY.appendChild(elYap("div", "dg-donem-soru", sorun));
        tr.append(tdE, tdY);
        const tdK = elYap("td", "");
        const seg = elYap("div", "dg-segment");
        [["yeni", "Yeni Ad"], ["eski", "Eski Ad Kalsın"]].forEach(([d, a]) => {
            const b = elYap("button", r.secim === d ? "secili" : "", a);
            b.type = "button"; b.disabled = kilitli;
            b.setAttribute("aria-pressed", r.secim === d ? "true" : "false");
            b.onclick = () => {
                if (kilitli || r.secim === d) return;
                r.secim = d; r.onay = false;
                tabloCiz(); if (degisti) degisti();
            };
            seg.appendChild(b);
        });
        tdK.appendChild(seg);
        tr.appendChild(tdK);
        const tdO = elYap("td", "dg-ekle-hucre");
        const k = document.createElement("input");
        k.type = "checkbox"; k.className = "dg-ekle";
        k.checked = r.onay; k.disabled = kilitli || (!r.onay && !!sorun);
        k.title = sorun ? "Önce sorunu giderin" : "Aileyi onayla";
        k.setAttribute("aria-label", ilk[0] + " onay");
        k.onchange = () => { if (kilitli) { k.checked = !k.checked; return; } r.onay = k.checked; tabloCiz(); if (degisti) degisti(); };
        tdO.appendChild(k);
        tr.appendChild(tdO);
        tr.classList.toggle("dg-parca-onayli", r.onay);
        tr.classList.toggle("dg-donem-dikkat", !r.onay && !!sorun);
        return tr;
    }
    siraCiz();
    dyCiz();
    ekCiz();
    tkCiz();
    tabloCiz();
    tkYoklaKur();
    return {
        deger: () => ({ sira: sira.slice(), eklenecekler: ekDeger(), turler: Object.assign({}, turSecim),
                        donem_yazilis: dyDeger(),
                        aileler: satirlar.map(r => ({ aile: r.aile, secim: r.secim, onay: r.onay })) }),
        sonKontrolSuruyor: tkSuruyor,
        onaysiz: () => satirlar.filter(r => !r.onay).length,
        ekOnaysiz: () => ekler.filter(e => !e.onay).length,
        sorunlu: () => Object.keys(sorunlar()).length + ekler.filter(e => !ekGecerli(e)).length
            + dyler.filter(dyHata).length,
        sayilar: () => {
            let deg = 0;
            satirlar.forEach(r => { if (r.secim === "yeni") deg += r.kolonlar.filter(([e, y]) => e !== y).length; });
            return { aile: satirlar.length, degisen: deg };
        },
        kilitle: k => { kilitli = k; siraCiz(); dyCiz(); ekCiz(); tkCiz(); tabloCiz(); if (!k) tkYoklaKur(); },
        bekliyor: () => false
    };
}

/* ==================== 01.2.4.3 Kolon Kartları ====================
   Her kolonun kartı onaylı ad parçalarından (arka uçta kodla) kurulur;
   açıklaması karttan ve tanımdan dil modeliyle yazılır, satır onaylanır.
   Satırlar arka plandaki işten yoklamayla gelir; satır, düzenlemesi
   bitince açılır. "Sizin Düzenlemeniz"e yazılan not alandan çıkınca
   kaydedilir ve o kolon beklemeden yeniden kontrol edilir. Aynı parça
   hakkındaki sorular "Toplu Sorular"da bir kez sorulur. Kart geçmişten
   çizilirse onaylanan hal salt okunur gelir. */
const ACK_SAYFA = 150;
const ACK_YOKLAMA = 2500;
const ACK_KART_ADLARI = [["konu", "Konu"], ["yon", "Yön"], ["nitelik", "Nitelik"],
                         ["zaman", "Zaman"], ["olcu", "Ölçü"], ["istatistik", "İstatistik"],
                         ["karsilastirma", "Karşılaştırma"], ["birim", "Birim"], ["diger", "Diğer"]];
/* Açıklamada olup adda karşılığı olmayan bilgi: kart çipi (01.2.4.4'te
   kısaltmasıyla onaylanıp ada eklenir). */
function adEksikCipi(e) {
    const et = (ACK_KART_ADLARI.find(([a]) => a === e.tur) || [e.tur, e.tur])[1];
    const c = elYap("span", "dg-acik-kart-oge dg-acik-kart-eksik");
    c.title = "Açıklamada var, adda karşılığı yok; 01.2.4.4 Kolon Adları'nda kısaltmasıyla onaylanıp ada eklenir.";
    c.append(elYap("span", "dg-acik-kart-et", et + ":"), document.createTextNode(" " + tireSade(e.anlam)),
             elYap("span", "dg-acik-kart-eksik-not", " · ada eklenecek"));
    return c;
}
const ACK_SUZGECLER = [["tumu", "Tümü", "toplam"], ["onaysiz", "Onaylanmadı", "onaysiz"],
                       ["degisen", "Değişen", "degisen"], ["yazim", "Yalnız Yazım", "yazim"],
                       ["ekdegisim", "Yalnız Ek", "ek_degisim"],
                       ["ek", "Ek Bilgi", "ek"],
                       ["soru", "Soru Var", "soru"], ["ad", "Ad / Dağılım Notu", "ad"],
                       ["kontrol", "Kontrol Gereken", "kontrol"],
                       ["elle", "Düzenledikleriniz", "elle"], ["hata", "Düzenlenemedi", "hata"]];

function ackSade(m) {
    return String(m || "").replace(/\s+/g, " ").trim();
}
/* DÜZENLEME ALANININ TABANI: sizin düzenlemeniz, yoksa dil modelinin
   önerisi (satır hazırsa). Alan bununla dolar; farklı bırakılırsa
   düzenleme sayılır. */
/* Kullanıcının elle yazdığı açıklama (soruya cevap notu değil; eski kayıtta
   elle bilgisi yok, not elle sayılır). */
const ackElleNot = v => !!v.not && v.elle !== false;
/* Aile anahtarı ekranda: "#" sayı yeri; birden çok sayı varsa numaralı
   (TXN_[sayı 1]D_[sayı 2]D_RATIO), adın sırasıyla. */
function ackAileAdi(a) {
    const adet = (String(a || "").match(/#/g) || []).length;
    let i = 0;
    return String(a || "").replace(/#/g, () => adet > 1 ? "[sayı " + (++i) + "]" : "[sayı]");
}
function ackTaban(v) {
    if (ackElleNot(v)) return tireSade(v.not);
    return v.durum === "hazir" ? tireSade(v.aciklama || "") : "";
}
/* SÖZCÜK FARKI: yeni metnin sözcükleri, eskide karşılığı olmayanlar
   işaretli ([sözcük, yeni_mi]). Karşılaştırma küçük harf ve noktalamasız
   (en uzun ortak dizi). */
function ackSozcukFarki(eski, yeni) {
    const anah = w => w.replace(/I/g, "ı").replace(/İ/g, "i").toLocaleLowerCase("tr")
        .replace(/[^0-9a-zçğıöşüâîû]/g, "");
    const ys = String(yeni || "").split(/\s+/).filter(Boolean);
    const es = String(eski || "").split(/\s+/).filter(Boolean).map(anah);
    const ya = ys.map(anah);
    const n = es.length, m = ya.length;
    const dp = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
    for (let i = n - 1; i >= 0; i--)
        for (let j = m - 1; j >= 0; j--)
            dp[i][j] = es[i] === ya[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    const ortak = new Array(m).fill(false);
    for (let i = 0, j = 0; i < n && j < m;) {
        if (es[i] === ya[j]) { ortak[j] = true; i++; j++; }
        else if (dp[i + 1][j] >= dp[i][j + 1]) i++;
        else j++;
    }
    return ys.map((w, j) => [w, !ortak[j] && !!ya[j]]);
}
/* Ailenin açıklama kalıbı: sayılar [sayı] yapılınca en çok üyede aynı
   olan metin ve kaç üyede tuttuğu. */
function ackAileKalibi(aciklamalar) {
    const say = new Map();
    aciklamalar.map(a => ackSade(a)).filter(Boolean)
        .forEach(a => { const k = a.replace(/\d+/g, "[sayı]"); say.set(k, (say.get(k) || 0) + 1); });
    let kalip = "", n = 0;
    say.forEach((v, k) => { if (v > n) { kalip = k; n = v; } });
    return [kalip, n];
}

function aciklamaBolumuEkle(kart, aa, ilkKilit, degisti) {
    let kilitli = ilkKilit;
    const veriler = new Map();        // kolon -> satır verisi (sunucudan)
    const sira = [];                  // kolonların veri setindeki sırası
    const el = new Map();             // kolon -> satır elemanları
    let son = 0, dm = ilkKilit ? "bitti" : "calisiyor", sayac = {}, sorular = [], kayma = null;
    let hataMetni = "", saltOkunur = !!ilkKilit, ilerleme = null, atlandi = false;
    let suzgec = "tumu", arama = "", gosterilen = ACK_SAYFA;
    let yoklamaZaman = null, yuklendi = false;

    /* ---- Başlık, yönerge, Excel ---- */
    const kb = elYap("div", "dg-tablo-bas dg-kontrol-bas");
    const kbas = elYap("div", "dg-tablo-baslik", aa.baslik || "Kolon Kartları");
    if (aa.sutunlar) kbas.appendChild(bolmeBilgiSimgesi(tireSade(aa.sutunlar), "Sütunlar"));
    kb.appendChild(kbas);
    const excel = excelSeridiYap("aciklama", "Önerilen Sözlüğü İndir",
        "Orijinal ve düzeltilmiş açıklamalar, notlarınız, ek bilgi ve kolon kartı");
    excel.ac(true);
    kb.appendChild(excel.el);
    kart.appendChild(kb);
    if (aa.yonerge && aa.yonerge.length) {
        const yl = elYap("ol", "dg-yonerge");
        aa.yonerge.forEach(m => yl.appendChild(elYap("li", "", tireSade(m))));
        kart.appendChild(yl);
    }
    if (aa.uyari) kart.appendChild(elYap("div", "dg-oneri-hata", tireSade(aa.uyari)));
    /* Önceki kontrolden gelen onaylar (01.2.4 önceki onaylı kontrol). */
    if (aa.onceki_not) kart.appendChild(elYap("div", "dg-bilgi-kutu", tireSade(aa.onceki_not)));

    /* ---- İlerleme: süre, sayı, İptal / Devam (Dönem Bilgisi'ndeki
       işlem satırının aynısı) ---- */
    const ilerEl = elYap("div", "islem-satiri dg-ilerleme dg-acik-ilerleme");
    ilerEl.setAttribute("role", "status");
    const ilerMetin = elYap("span", "islem-sure", "");
    const iptalBtn = elYap("button", "islem-iptal", "İptal");
    iptalBtn.type = "button";
    iptalBtn.title = "Dil modelini durdur; düzenlenen satırlar kalır";
    ilerEl.append(ilerMetin, iptalBtn);
    kart.appendChild(ilerEl);
    const durumEl = elYap("div", "dg-bilgi-kutu dg-acik-durum", "");
    durumEl.hidden = true;
    const devamBtn = elYap("button", "dg-toplu-btn", "Kaldığı Yerden Devam Et");
    devamBtn.type = "button";
    kart.appendChild(durumEl);
    let ilerBas = Date.now(), ilerSabit = false;
    const ilerSayac = setInterval(() => {
        if (!kart.isConnected) { clearInterval(ilerSayac); return; }
        ilerYaz();
    }, 1000);

    /* ---- Toplu sorular ---- */
    const soruKap = elYap("div", "dg-acik-sorular");
    soruKap.hidden = true;
    kart.appendChild(soruKap);
    /* SORU EVRESİ: önce yalnız Toplu Sorular görünür. Dil modeli
       düzenlemeyi bitirip cevapsız soru kalmayınca aşamalar, arama ve
       tablo açılır (1 Aileler ile başlanır). Cevap verilince ilgili
       kolonlar yeniden düzenlenir; yeni soru çıkarsa evre sürer. Salt
       okunur kartta evre yok. */
    /* ANLAMI KAYAN AİLELER: toplu sorular cevaplanıp dil modeli bitince
       sunucu her ailenin bir kolonunda orijinal ile yeni açıklamayı
       karşılaştırır; anlamı açıkça kayan aileler burada sorulur. Cevap
       ailenin bütün kolonlarına gider ve dil modeli aileyi yeniden yazar
       ya da «Yeni Açıklama Doğru» denir. */
    const kaymaKap = elYap("div", "dg-acik-kayma");
    kaymaKap.hidden = true;
    kart.appendChild(kaymaKap);
    const evreNot = elYap("div", "dg-bilgi-kutu dg-acik-evre-not", "");
    evreNot.hidden = true;
    kart.appendChild(evreNot);
    const cevapsizSoru = () => (sorular || []).filter(s => s.soru_kolon > 0 && !s.cevap).length;
    const dmSurer = () => dm !== "iptal" && (dm === "calisiyor" || Number(sayac.bekleyen || 0) > 0);
    const kaymaBekleyen = () => kayma ? Number(kayma.bekleyen || 0) : 0;
    const kaymaSurer = () => !!kayma && kayma.durum === "calisiyor";
    /* Kayan ailenin cevabından koşullu anlam önerisi hazırlanıyor. */
    const kosulSurer = () => !!kayma && !!kayma.oneri_suruyor;
    /* Kararı bekleyen koşullu anlam önerisi olan aileler (ailenin kendi
       kararı verilmiş). */
    const kosulBekleyen = () => ((kayma && kayma.aileler) || [])
        .filter(x => x.karar && x.kosul && x.kosul.durum === "hazir" && !x.kosul.karar).length;
    const soruEvresi = () => !saltOkunur && (!yuklendi || cevapsizSoru() > 0 || dmSurer()
                                             || kaymaSurer() || kosulSurer() || kaymaBekleyen() > 0);
    function evreCiz() {
        const evre = soruEvresi();
        kart.classList.toggle("dg-acik-soru-evresi", evre);
        /* Yüklenirken "Satırlar yükleniyor" görünür; sonra evrede gizli. */
        if (evre && yuklendi) bosEl.hidden = true;
        evreNot.hidden = !evre || !yuklendi;
        if (evreNot.hidden) return;
        const n = cevapsizSoru();
        if (!n && !dmSurer() && (kaymaSurer() || kosulSurer() || kaymaBekleyen())) {
            const kb = kosulBekleyen(), ab = Math.max(0, kaymaBekleyen() - kb);
            evreNot.textContent = kaymaSurer()
                ? "Dil modeli her ailenin açıklamasını orijinaliyle karşılaştırıyor: "
                  + ftBinlik(kayma.biten || 0) + " / " + ftBinlik(kayma.toplam || 0)
                  + ". Anlamı kayan aile çıkarsa yukarıda sorulur; bitince kolonlar açılır."
                : (ab ? ftBinlik(ab) + " ailenin açıklamasında anlam kaymış. Yukarıda her aile için "
                        + "doğru anlamı yazın ya da yeni açıklama doğruysa «Yeni Açıklama Doğru»ya basın. "
                      : "")
                  + (kb ? ftBinlik(kb) + " ailenin cevabından Dönem Bilgisi için koşullu anlam önerildi. "
                        + "Yukarıda «Kaydet» ya da «Kaydetme»ye basın. " : "")
                  + (kosulSurer() ? "Cevabınızdan Dönem Bilgisi için koşullu anlam çıkarılıyor. " : "")
                  + "Hepsi bitince kolonlar açılır.";
            return;
        }
        evreNot.textContent = n
            ? ftBinlik(n) + " soru cevabınızı bekliyor. Önce yukarıdaki Toplu Sorular'ı cevaplayın; "
              + "cevabınız o parçanın geçtiği bütün kolonlarda kullanılır ve o kolonlar yeniden "
              + "düzenlenir. " + (dmSurer() ? "Dil modeli düzenlemeyi bitirip bütün sorular "
              : "Bütün sorular ") + "cevaplanınca kolonlar açılır."
            : (sorular || []).length
            ? "Bütün sorular cevaplandı. Dil modeli kolonları cevaplarınızla düzenliyor; bitince "
              + "kolonlar açılır. Yeni soru çıkarsa burada görünür."
            : "Dil modeli kolonları düzenliyor. Toplu soru çıkarsa burada görünür; düzenleme bitip "
              + "cevaplanacak soru kalmayınca kolonlar açılır.";
    }

    /* ---- Süzgeçler + arama ---- */
    const ust = elYap("div", "dg-tablo-ust dg-acik-ust");
    const suzKap = elYap("div", "dg-acik-suzgec");
    const suzBtn = {};
    ACK_SUZGECLER.forEach(([k, et]) => {
        const b = elYap("button", "dg-acik-cip", et);
        b.type = "button";
        b.onclick = () => { suzgec = k; gosterilen = ACK_SAYFA; suzgecCiz(); tabloCiz(); };
        suzBtn[k] = b;
        suzKap.appendChild(b);
    });
    const ara = document.createElement("input");
    ara.type = "search"; ara.className = "dg-giris dg-acik-ara";
    ara.placeholder = "Kolon ya da açıklama ara";
    ara.setAttribute("aria-label", "Açıklama ara");
    ara.addEventListener("input", () => {
        arama = ara.value.trim().toLocaleLowerCase("tr");
        gosterilen = ACK_SAYFA;
        tabloCiz();
    });
    /* TOPLU ONAY: görünen ve dikkat notu olmayan hazır satırlar. Soru,
       ad / dağılım notu, kontrol notu ya da hata olan satır tek tek
       onaylanır. */
    const topluOnay = elYap("button", "dg-toplu-btn", "Görünenleri Onayla");
    topluOnay.type = "button";
    topluOnay.title = "Görünen ve notu olmayan satırlar onaylanır. Soru, ad ya da dağılım notu ve "
        + "kontrol notu olan satırları tek tek bakıp onaylayın.";
    topluOnay.onclick = () => {
        if (kilitli || saltOkunur) return;
        const kolonlar = gorunenler().filter(topluOlur).map(v => v.kolon);
        if (!kolonlar.length) return;
        topluOnay.disabled = true;
        kolonlar.forEach(k => { const v = veriler.get(k); if (v) { v.onayli = true; satirGuncelle(v); } });
        islem({ islem: "onay", kolonlar: kolonlar, onay: true })
            .then(d => { if (d && d.hata) durumYaz(d.hata, true); yoklaHemen(); })
            .catch(() => yoklaHemen())
            .finally(() => { topluOnay.disabled = false; });
        if (degisti) degisti();
    };
    /* BİÇİM DEĞİŞİKLİKLERİ: açıklaması orijinaliyle aynı, yalnız yazımı
       ya da ekleri değişen bütün satırlar (görünsün görünmesin) tek
       düğmeyle onaylanır; bilgi değişmedi. Soru, not ya da kontrol notu
       olan satır yine tek tek. */
    const bicimOnay = elYap("button", "dg-toplu-btn", "");
    bicimOnay.type = "button";
    bicimOnay.title = "Açıklaması orijinaliyle aynı ya da yalnız yazımı veya ekleri değişen, notu olmayan "
        + "bütün satırlar onaylanır.";
    const bicimSatirlari = () => sira.map(k => veriler.get(k))
        .filter(v => v && topluOlur(v) && asamaOf(v) === 2);
    bicimOnay.onclick = () => {
        if (kilitli || saltOkunur) return;
        const kolonlar = bicimSatirlari().map(v => v.kolon);
        if (!kolonlar.length) return;
        bicimOnay.disabled = true;
        kolonlar.forEach(k => { const v = veriler.get(k); if (v) { v.onayli = true; satirGuncelle(v); } });
        islem({ islem: "onay", kolonlar: kolonlar, onay: true })
            .then(d => { if (d && d.hata) durumYaz(d.hata, true); yoklaHemen(); })
            .catch(() => yoklaHemen())
            .finally(() => { bicimDurum(); });
        if (degisti) degisti();
    };
    /* HEPSİNİ ONAYLA: hazır kolonlar (aşama sırası dahil) iki tıklamayla
       onaylanır: birinci tıklama ne onaylanacağını yazar, ikinci onaylar.
       Cevapsız sorusu ya da kontrol notu olan kolonlar AYRILIR: onaylanmaz,
       listede kalır ve tek tek bakılır (aşamalar onlarla sürer). Dil
       modelinin düzenlediği kolon bitince ayrıca onaylanır. native
       confirm() yok (iframe akışı durur). */
    let hepsiSor = false;
    const hepsiOnay = elYap("button", "dg-toplu-btn dg-acik-hepsi", "");
    hepsiOnay.type = "button";
    hepsiOnay.title = "Hazır kolonlar onaylanır. Cevapsız sorusu ya da kontrol notu olan kolonlar "
        + "ayrılır; listede kalır, onlara tek tek bakın.";
    const hepsiUyari = elYap("div", "dg-acik-hepsi-uyari", "");
    hepsiUyari.hidden = true;
    const hepsiMetin = elYap("span", "", "");
    const hepsiVazgec = elYap("button", "dg-baglanti", "Vazgeç");
    hepsiVazgec.type = "button";
    hepsiVazgec.onclick = () => { hepsiSor = false; hepsiDurum(); };
    hepsiUyari.append(hepsiMetin, hepsiVazgec);
    /* Sorunsuz aşamalarda (1 ile 3) o üç aşamanın onaysız hazır kolonları;
       Ayrılanlar listesinde yalnız o listenin kolonları. */
    const ayriGorulen = () => !saltOkunur && yuklendi && AYRI(gorulenAsama());
    const hepsiSatirlari = () => {
        const g = ayriGorulen() ? gorulenAsama() : 0;
        return sira.map(k => veriler.get(k)).filter(v => v && !v.onayli
            && (v.durum === "hazir" || v.durum === "hata") && (g ? asamaOf(v) === g : !AYRI(asamaOf(v))));
    };
    hepsiOnay.onclick = () => {
        if (kilitli || saltOkunur) return;
        const kolonlar = hepsiSatirlari().map(v => v.kolon);
        if (!kolonlar.length) return;
        if (!hepsiSor) { hepsiSor = true; hepsiDurum(); return; }
        hepsiSor = false;
        hepsiOnay.disabled = true;
        kolonlar.forEach(k => { const v = veriler.get(k); if (v) v.onayli = true; });
        tabloYenidenCiz();
        islem({ islem: "onay", kolonlar: kolonlar, onay: true })
            .then(d => { if (d && d.hata) durumYaz(d.hata, true); yoklaHemen(); })
            .catch(() => yoklaHemen())
            .finally(() => { hepsiDurum(); });
        if (degisti) degisti();
    };
    function hepsiDurum() {
        const sat = hepsiSatirlari(), n = sat.length;
        if (!n || kilitli) hepsiSor = false;
        hepsiOnay.hidden = saltOkunur;
        hepsiOnay.disabled = kilitli || !n;
        const ayriL = ayriGorulen();
        hepsiOnay.textContent = hepsiSor ? "Evet, " + ftBinlik(n) + " Kolonu Onayla"
            : (ayriL ? "Bu Listedekilerin Hepsini Onayla · " : "Sorunsuzların Hepsini Onayla · ") + ftBinlik(n);
        hepsiOnay.title = ayriL ? "Bu listedeki onaysız kolonlar ekranda göründüğü gibi onaylanır."
            : "Sorunsuz kolonlar (Aileler, Biçim Değişiklikleri, Değişenler) onaylanır. Cevapsız Soru ve "
              + "Kontrol Notu listelerindeki kolonlar onaylanmaz.";
        hepsiOnay.classList.toggle("onay-bekliyor", hepsiSor);
        hepsiUyari.hidden = !hepsiSor;
        if (!hepsiSor) return;
        const bek = sira.filter(k => { const v = veriler.get(k); return v && bekliyorMu(v); }).length;
        const s4 = asamaSatirlari(4).filter(v => !v.onayli).length;
        const s5 = asamaSatirlari(5).filter(v => !v.onayli).length;
        hepsiMetin.textContent = ayriL
            ? ftBinlik(n) + " kolon (" + asamaBilgi(gorulenAsama())[1] + " listesi) ekranda göründüğü gibi "
              + "onaylanacak" + (gorulenAsama() === 4 ? "; bu kolonlarda dil modelinin sorusu cevapsız kaldı" : "")
              + ". Emin değilseniz "
            : ftBinlik(n) + " sorunsuz kolonun açıklaması ekranda göründüğü gibi onaylanacak"
              + (s4 || s5 ? ". " + [s4 ? "«Cevapsız Soru» listesindeki " + ftBinlik(s4) : "",
                                     s5 ? "«Kontrol Notu» listesindeki " + ftBinlik(s5) : ""].filter(Boolean).join(" ve ")
                + " kolon onaylanmaz; onlara o listelerde bakın" : "")
              + (bek ? ". Dil modelinin düzenlediği " + ftBinlik(bek) + " kolon bitince ayrıca onaylanır" : "")
              + ". Emin değilseniz ";
    }
    function bicimDurum() {
        hepsiDurum();
        const n = bicimSatirlari().length;
        bicimOnay.textContent = "Biçim Değişikliklerini Onayla · " + ftBinlik(n);
        bicimOnay.hidden = saltOkunur || gorulenAsama() !== 2;
        bicimOnay.disabled = kilitli || !n;
    }
    /* Süzgeç düğmeleri ve «Görünenleri Onayla» gösterilmez: aşamalar ve
       aile, biçim ve hepsini onaylama düğmeleri aynı işi görür. */
    ust.append(ara, bicimOnay, hepsiOnay);

    /* ---- AŞAMALAR ----
       Onay sırayla: 1 Aileler (adı yalnız sayıyla ayrılan kolonlar), 2
       Biçim Değişiklikleri (aile dışı; açıklaması aynı ya da yalnız yazımı
       veya ekleri değişen), 3 Değişenler (kalan: anlamı değişen, sorulu,
       düzenlenemeyen). Tablo yalnız seçili aşamanın satırlarını gösterir;
       bir aşama, öncekinin bütün satırları onaylanınca açılır (önceki
       aşama sonradan eksik kalırsa geri ona dönülür). Biten aşamaya geri
       bakılabilir. Salt okunur kartta aşama yok. */
    const ASAMALAR = [
        [4, "Cevapsız Soru", "Bu kolonlarda dil modeli bir şey soruyor; açıklama yalnız kesin bilgiyle "
            + "yazıldı. Her satırda sorunun altına cevabınızı yazıp «Cevabı Uygula»ya basın: dil modeli "
            + "açıklamayı cevabınızla yeniden yazar, soru kalkarsa kolon kendi listesine geçer. Cevabını "
            + "bilmediğiniz soruda açıklamayı okuyup onay kutusunu işaretleyin. Bu liste bitince Kontrol "
            + "Notu açılır."],
        [5, "Kontrol Notu", "Bu kolonlarda kodun kontrol notu var (satırdaki «Kontrol:» notu). Notu okuyun; "
            + "açıklama doğruysa onay kutusunu işaretleyin, değilse «Sizin Düzenlemeniz»de düzeltin. Bu liste "
            + "bitince Aileler açılır."],
        [1, "Aileler", "Her ailede açıklamayı okuyun; doğruysa «Aileyi Onayla»ya basın. Kutuda adı "
            + "yazan kolonları «Kolonları Aç ve Tek Tek Bak» ile açıp tek tek onaylayın. Aileler "
            + "bitince sonraki aşama açılır."],
        [2, "Biçim Değişiklikleri", "Bu kolonlarda bilgi değişmedi; yalnız yazım ya da ek düzeltildi. "
            + "Listeye göz atıp «Biçim Değişikliklerini Onayla»ya basın. Bitince sonraki aşama açılır."],
        [3, "Değişenler", "Bu kolonlarda açıklamanın anlamı değişti. Her kolonu okuyup onay kutusunu "
            + "işaretleyin."]];
    /* SIRA: önce SORUNLULAR (Cevapsız Soru, Kontrol Notu), sonra SORUNSUZLAR
       (Aileler, Biçim Değişiklikleri, Değişenler); bir aşama öncekinin
       bütün kolonları onaylanınca (ya da sorusu cevaplanıp listeden
       çıkınca) açılır. Kod numaraları: 1 Aileler, 2 Biçim, 3 Değişenler,
       4 Cevapsız Soru, 5 Kontrol Notu. Satırı olmayan aşama görünmez;
       sekme numarası görünen sıradır. */
    const AYRI = n => n >= 4;
    const asamaBilgi = n => ASAMALAR.find(x => x[0] === n);
    const asamaSirasi = n => ASAMALAR.findIndex(x => x[0] === n);
    let secilenAsama = null;
    const asamaBar = elYap("div", "dg-acik-asamalar");
    asamaBar.setAttribute("role", "tablist");
    const asamaNot = elYap("div", "dg-donem-pano-not dg-acik-asama-not", "");
    const asamaBtn = {};
    const grupEt = { 4: elYap("span", "dg-acik-asama-grup", "Önce sorunlular"),
                     1: elYap("span", "dg-acik-asama-grup", "Sonra sorunsuzlar") };
    ASAMALAR.forEach(([n, ad]) => {
        if (grupEt[n]) asamaBar.appendChild(grupEt[n]);
        const b = elYap("button", "dg-acik-asama", "");
        b.type = "button";
        b.setAttribute("role", "tab");
        b.onclick = () => {
            if (b.disabled) return;
            secilenAsama = n === aktifAsama() ? null : n;
            hepsiSor = false;
            gosterilen = ACK_SAYFA; suzgec = "tumu";
            suzgecCiz(); tabloCiz();
        };
        asamaBtn[n] = b;
        asamaBar.appendChild(b);
    });
    /* Dönem anlamı belirsiz kolon da soru sayılır (Cevapsız Soru). */
    const donemBelirsiz = v => v.durum === "hazir" && (v.donem_turleri || []).some(x => !x.tur);
    const asamaOf = v => (v.durum === "hazir" && v.soru) ? 4
        : donemBelirsiz(v) ? 4
        : (v.soru_cevabi && bekliyorMu(v)) ? 4
        : (v.durum === "hazir" && (v.kontrol || []).length) ? 5
        : (v.aile && Number(v.aile_boyu || 1) > 1) ? 1
        : (v.durum === "hazir" && ["aynen", "yazim", "ek"].includes(v.degisim)) ? 2 : 3;
    /* Satırı olmayan aşama görünmez (yüklenmeden önce sorunsuz üçü). */
    const gorunurAsamalar = () => {
        const g = ASAMALAR.map(x => x[0]).filter(n => asamaSatirlari(n).length);
        return g.length ? g : [1, 2, 3];
    };
    const asamaNo = n => gorunurAsamalar().indexOf(n) + 1;
    const asamaSatirlari = n => sira.map(k => veriler.get(k)).filter(v => v && asamaOf(v) === n);
    /* Aşama bitti: satırlarının hepsi onaylı. 2. aşama, dil modeli aile
       dışı satırları bitirmeden bitmiş sayılmaz (bekleyen satır biçim
       değişikliği çıkabilir). */
    function asamaBitti(n) {
        if (!yuklendi) return false;
        if (asamaSatirlari(n).some(v => !v.onayli)) return false;
        if (n === 2 && sira.some(k => { const v = veriler.get(k); return v && asamaOf(v) !== 1 && bekliyorMu(v); }))
            return false;
        return true;
    }
    function aktifAsama() {
        const g = gorunurAsamalar();
        for (const n of g) if (!asamaBitti(n)) return n;
        return g[g.length - 1];
    }
    function gorulenAsama() {
        const a = aktifAsama();
        if (secilenAsama !== null && (asamaSirasi(secilenAsama) > asamaSirasi(a)
                                      || !gorunurAsamalar().includes(secilenAsama))) secilenAsama = null;
        return secilenAsama === null ? a : secilenAsama;
    }
    function asamaCiz() {
        asamaBar.hidden = asamaNot.hidden = saltOkunur;
        if (saltOkunur) return;
        const a = aktifAsama(), g = gorulenAsama();
        const gor = gorunurAsamalar();
        grupEt[4].hidden = !gor.some(AYRI);
        grupEt[1].hidden = !gor.some(n => !AYRI(n));
        ASAMALAR.forEach(([n, ad, ack]) => {
            const satir = asamaSatirlari(n);
            const onayli = satir.filter(v => v.onayli).length;
            const b = asamaBtn[n];
            b.hidden = !gor.includes(n);
            b.textContent = asamaNo(n) + " · " + ad + " · " + ftBinlik(onayli) + " / " + ftBinlik(satir.length);
            b.classList.toggle("ayri", AYRI(n));
            b.disabled = asamaSirasi(n) > asamaSirasi(a);
            b.title = b.disabled ? "Önceki aşama bitince açılır." : "";
            b.classList.toggle("secili", n === g);
            b.classList.toggle("bitti", asamaBitti(n));
            b.setAttribute("aria-selected", n === g ? "true" : "false");
            if (n === g) asamaNot.textContent = AYRI(n)
                ? ftBinlik(satir.length) + " kolon, " + ftBinlik(onayli) + " tanesi onaylı. " + ack : ack;
        });
        if (g === 1) {
            const aileler = new Map();
            asamaSatirlari(1).forEach(v => (aileler.get(v.aile) || aileler.set(v.aile, []).get(v.aile)).push(v));
            const biten = [...aileler.values()].filter(u => u.every(v => v.onayli)).length;
            asamaNot.textContent = ftBinlik(aileler.size) + " aile (" + ftBinlik(asamaSatirlari(1).length)
                + " kolon), " + ftBinlik(biten) + " aile onaylı. " + asamaBilgi(1)[2];
        }
    }
    kart.appendChild(asamaBar);
    kart.appendChild(asamaNot);
    kart.appendChild(ust);
    kart.appendChild(hepsiUyari);

    /* ---- Tablo ---- */
    const sar = elYap("div", "dg-tablo-sar dg-acik-sar");
    const tablo = elYap("table", "dg-tablo dg-acik-tablo");
    const th = document.createElement("thead"), hr = document.createElement("tr");
    ["Kolon", "Orijinal", "Sizin Düzenlemeniz", "Kart ve Açıklama", "Onay"]
        .forEach(h => hr.appendChild(elYap("th", "", h)));
    th.appendChild(hr); tablo.appendChild(th);
    const tb = document.createElement("tbody");
    tablo.appendChild(tb); sar.appendChild(tablo); kart.appendChild(sar);
    const dahaBtn = elYap("button", "dg-toplu-btn dg-acik-daha", "");
    dahaBtn.type = "button";
    dahaBtn.hidden = true;
    dahaBtn.onclick = () => { gosterilen += ACK_SAYFA; tabloCiz(); };
    kart.appendChild(dahaBtn);
    const bosEl = elYap("div", "dg-not dg-cizgisiz dg-acik-bos", "Satırlar yükleniyor");
    kart.appendChild(bosEl);
    evreCiz();

    /* ---- Sunucu işlemleri ---- */
    function islem(govde) {
        return fetch(getWebAppBackendUrl("aciklama_islem"), {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify(ftKimlikGovdesi(govde))
        }).then(r => r.json());
    }
    /* İptal sunucuda hemen işler; yanıt gelince durum beklemeden yoklanır.
       Düğme, iş yeniden başlayana dek "İptal ediliyor" kalır. */
    function iptalSifirla() { iptalBtn.disabled = kilitli; iptalBtn.textContent = "İptal"; }
    iptalBtn.onclick = () => {
        iptalBtn.disabled = true;
        iptalBtn.textContent = "İptal ediliyor";
        islem({ islem: "iptal" }).then(() => yokla()).catch(() => iptalSifirla());
    };
    devamBtn.onclick = () => {
        devamBtn.disabled = true;
        islem({ islem: "devam" }).then(d => {
            if (d && d.hata) durumYaz(d.hata, true);
            yoklaHemen();
        }).catch(() => {}).finally(() => { devamBtn.disabled = false; });
    };

    function bekliyorMu(v) {
        return v.durum === "bekliyor" || v.durum === "isleniyor" || v.durum === "yok";
    }

    /* ---- Satır ---- */
    function satirKur(v) {
        const tr = elYap("tr", "dg-satir dg-acik-satir");
        const tdK = elYap("td", "dg-kolon");
        tdK.appendChild(elYap("div", "dg-acik-kolon", v.kolon));
        if (v.rol) tdK.appendChild(elYap("span", "dg-rol", tireSade(v.rol)));
        const aileEl = elYap("div", "dg-acik-aile", "");
        tdK.appendChild(aileEl);
        tr.appendChild(tdK);
        const tdO = elYap("td", "dg-acik-orijinal");
        tdO.textContent = v.orijinal ? tireSade(v.orijinal) : "(boş)";
        tdO.classList.toggle("dg-acik-bos", !v.orijinal);
        tr.appendChild(tdO);
        const tdN = elYap("td", "dg-aciklama-hucre dg-acik-not-hucre");
        let giris = null;
        if (!saltOkunur) {
            giris = document.createElement("textarea");
            giris.className = "dg-giris dg-acik-giris";
            giris.rows = 2;
            giris.placeholder = "Dil modelinin önerisi gelince burada; değiştirebilirsiniz";
            giris.value = ackTaban(v);
            giris.setAttribute("aria-label", v.kolon + " için düzenlemeniz");
            giris.addEventListener("blur", () => notKaydet(v.kolon));
            giris.addEventListener("input", () => { if (degisti) degisti(); });
            tdN.appendChild(giris);
        } else {
            tdN.appendChild(elYap("div", "dg-acik-salt", ackElleNot(v) ? tireSade(v.not) : ""));
        }
        const aileBtn = elYap("button", "dg-toplu-btn dg-acik-aile-btn", "");
        aileBtn.type = "button";
        aileBtn.hidden = true;
        aileBtn.onclick = () => aileyeUygula(v.kolon);
        tdN.appendChild(aileBtn);
        const notBilgi = elYap("div", "dg-acik-not", "");
        notBilgi.hidden = true;
        tdN.appendChild(notBilgi);
        tr.appendChild(tdN);
        const tdD = elYap("td", "dg-acik-duzeltilmis");
        tr.appendChild(tdD);
        const tdOn = elYap("td", "dg-ekle-hucre");
        const onayK = document.createElement("input");
        onayK.type = "checkbox"; onayK.className = "dg-ekle";
        onayK.setAttribute("aria-label", v.kolon + " onay");
        onayK.addEventListener("change", () => {
            const v2 = veriler.get(v.kolon);
            if (kilitli || saltOkunur || !v2 || bekliyorMu(v2)) { onayK.checked = !onayK.checked; return; }
            v2.onayli = onayK.checked;
            satirGuncelle(v2);
            islem({ islem: "onay", kolonlar: [v.kolon], onay: onayK.checked })
                .then(d => { if (d && d.hata) durumYaz(d.hata, true); yoklaHemen(); })
                .catch(() => yoklaHemen());
            if (degisti) degisti();
        });
        tdOn.appendChild(onayK);
        tr.appendChild(tdOn);
        const e = { tr, tdD, giris, aileBtn, aileEl, notBilgi, onayK };
        el.set(v.kolon, e);
        satirGuncelle(v);
        return tr;
    }

    function duzeltilmisCiz(td, v) {
        td.textContent = "";
        if (v.durum === "isleniyor") {
            td.appendChild(elYap("div", "dg-acik-bekliyor", v.soru_cevabi
                ? "Dil modeli açıklamayı cevabınızla yeniden yazıyor" : "Dil modeli düzenliyor"));
            if (v.soru_cevabi) td.appendChild(elYap("div", "dg-acik-soru-cevap-not",
                "Cevabınız: " + tireSade(v.soru_cevabi.cevap)));
            return;
        }
        if (bekliyorMu(v)) {
            td.appendChild(elYap("div", "dg-acik-bekliyor", "Sırada"));
            return;
        }
        if (v.durum === "hata") {
            const h = elYap("div", "dg-oneri-hata",
                "Dil modeli bu kolonu düzenleyemedi; onaylarsanız "
                + (ackElleNot(v) ? "notunuz" : "orijinal açıklama") + " kalır.");
            if (v.hata) h.title = duzMetin(v.hata);
            td.appendChild(h);
            return;
        }
        kartCiz(td, v);
        /* DEĞİŞEN SÖZCÜKLER: orijinalde karşılığı olmayan sözcükler
           vurgulu (yalnız yazım düzeltilende vurgu yok; süzgeci ayrı). */
        const m = elYap("div", "dg-acik-metin", "");
        if (v.degisim === "degisen") {
            ackSozcukFarki(tireSade(v.orijinal || ""), tireSade(v.aciklama || "")).forEach(([w, yeni], i) => {
                if (i) m.appendChild(document.createTextNode(" "));
                m.appendChild(yeni ? elYap("mark", "dg-acik-yeni", w) : document.createTextNode(w));
            });
        } else m.textContent = tireSade(v.aciklama || "");
        td.appendChild(m);
        /* Ek bilgi açıklamada zaten geçiyorsa tekrar yazılmaz (veride kalır). */
        if (v.ek && !v.ek_acikta) td.appendChild(elYap("div", "dg-acik-ek", "Ek bilgi: " + tireSade(v.ek)));
        if (v.karar) {
            let k = tireSade(v.karar);
            if (v.kaynak === "aile" && v.aile_kaynagi)
                k += " (" + v.aile_kaynagi + " kolonundan sayılar değiştirilerek aktarıldı)";
            td.appendChild(elYap("div", "dg-acik-karar", k));
        }
        /* Denetim: ikinci dil modeli çağrısının sonucu (uygun bulundu ya
           da bulduğu sorun ve son açıklamanın buna göre yazıldığı). */
        if (v.denetim) td.appendChild(elYap("div", "dg-acik-karar", tireSade(v.denetim)));
        if (v.soru) td.appendChild(elYap("div", "dg-donem-soru",
            "Soru: " + tireSade(v.soru) + (v.parca ? " (Toplu Sorular: " + v.parca + ")" : "")));
        soruCevapCiz(td, v);
        donemTurCiz(td, v);
        if (v.ad_notu) td.appendChild(elYap("div", "dg-acik-not", "Ad: " + tireSade(v.ad_notu)));
        if (v.dagilim_notu) td.appendChild(elYap("div", "dg-acik-not",
                                                  "Dağılım: " + tireSade(v.dagilim_notu)));
        (v.kontrol || []).forEach(k => td.appendChild(elYap("div", "dg-acik-kontrol",
                                                             "Kontrol: " + tireSade(k))));
    }
    /* DÖNEM ANLAMI (birimli kalıplar, ör. 30D): bu kolonda dönemin hangi
       anlamda kullanıldığı (son, önce, sonra, süre ya da eklenen tür).
       Belirlenmişse kaynağıyla tek satır ve "Değiştir"; belirsizse sarı
       kutuda seçenek düğmeleri. Seçim ailenin dönemi belirsiz kolonlarına
       da uygulanabilir; dil modeli açıklamayı seçilen anlamla yeniden
       yazar. 01.2.4.4'te kolonun adı bu anlamın yazılışıyla kurulur. */
    const donemAcik = new Set();
    const donemAile = new Map();
    function donemTurCiz(td, v) {
        const liste = v.donem_turleri || [];
        if (!liste.length) return;
        liste.forEach(x => {
            const kutu = elYap("div", "dg-acik-donem" + (x.tur ? "" : " belirsiz"));
            const anahtar = v.kolon + "|" + x.deger;
            const acik = !x.tur || donemAcik.has(anahtar);
            const bas = elYap("div", "dg-acik-donem-bas");
            if (x.tur) {
                bas.appendChild(elYap("span", "", "Dönem: " + x.deger + " bu kolonda "));
                bas.appendChild(elYap("b", "", "«" + tireSade(x.metin) + "»"));
                const sec_ = (x.secenekler || []).find(o => o.tur === x.tur);
                if (sec_ && sec_.kapsam) bas.appendChild(elYap("span", "dg-acik-donem-kapsam", " (" + sec_.kapsam + ")"));
                if (x.kaynak_adi) bas.appendChild(elYap("span", "dg-acik-donem-kaynak", " · " + x.kaynak_adi));
                if (!kilitli && !saltOkunur) {
                    const dg = elYap("button", "dg-baglanti", acik ? "Vazgeç" : "Değiştir");
                    dg.type = "button";
                    dg.onclick = () => {
                        if (donemAcik.has(anahtar)) donemAcik.delete(anahtar); else donemAcik.add(anahtar);
                        const v2 = veriler.get(v.kolon);
                        if (v2) satirGuncelle(v2);
                    };
                    bas.appendChild(dg);
                }
            } else {
                bas.appendChild(elYap("span", "", "Dönem anlamı belirsiz: " + x.deger + " bu kolonda hangi anlamda? "
                    + "Açıklamada yön ya da kapsam açık değil; seçmezseniz yeni adda dönem kısmı aynen kalır."));
            }
            kutu.appendChild(bas);
            if (acik && !kilitli && !saltOkunur) {
                const dugmeler = elYap("div", "dg-acik-donem-secenek");
                (x.secenekler || []).forEach(o => {
                    /* Seçenek: anlamı ve altında kapsadığı günler (ör. son 3
                       gün / bugünden önceki 1., 2., 3. gün). */
                    const b = elYap("button", "dg-acik-donem-dugme" + (o.tur === x.tur ? " secili" : ""), "");
                    b.appendChild(elYap("span", "dg-acik-donem-metin", tireSade(o.metin)));
                    if (o.kapsam) b.appendChild(elYap("span", "dg-acik-donem-kapsam", o.kapsam));
                    b.title = o.ad;
                    b.type = "button";
                    b.onclick = () => {
                        if (kilitli) return;
                        const aileye = donemAile.has(anahtar) ? donemAile.get(anahtar) : true;
                        donemAcik.delete(anahtar);
                        const v2 = veriler.get(v.kolon);
                        if (v2) {
                            v2.donem_turleri = (v2.donem_turleri || []).map(y => y.deger === x.deger
                                ? Object.assign({}, y, { tur: o.tur, metin: o.metin, kaynak: "secim", kaynak_adi: "Sizin seçiminiz" }) : y);
                            satirGuncelle(v2);
                        }
                        islem({ islem: "donem_tur", kolon: v.kolon, deger: x.deger, tur: o.tur, aileye: aileye })
                            .then(d => {
                                if (d && d.hata) durumYaz(d.hata, true);
                                else if (d && d.kolon_sayisi > 1) durumYaz(ftBinlik(d.kolon_sayisi)
                                    + " kolonda dönem anlamı «" + tireSade(o.metin) + "» olarak işaretlendi; "
                                    + "açıklamalar bu anlamla yeniden yazılıyor.", false);
                                yoklaHemen();
                            })
                            .catch(() => yoklaHemen());
                        if (degisti) degisti();
                    };
                    dugmeler.appendChild(b);
                });
                kutu.appendChild(dugmeler);
                if (Number(v.aile_boyu || 1) > 1) {
                    const et = elYap("label", "dg-acik-donem-aile");
                    const c = document.createElement("input");
                    c.type = "checkbox";
                    c.checked = donemAile.has(anahtar) ? donemAile.get(anahtar) : true;
                    c.onchange = () => donemAile.set(anahtar, c.checked);
                    et.append(c, elYap("span", "", "Ailenin dönemi belirsiz öbür kolonlarına da uygula"));
                    kutu.appendChild(et);
                }
            }
            td.appendChild(kutu);
        });
    }

    /* SORUYA CEVAP: sorulu satırda cevap kutusu. Cevap soruyla birlikte dil
       modeline gider; kolon beklemeden yeniden yazılır (soru kalkarsa
       kolon sorunsuz listesine geçer). Verilen cevap altta yazar; dil
       modeli yine soru sorarsa yeni soru ve önceki cevap birlikte görünür.
       Yazılan ama uygulanmayan cevap yeniden çizimde kaybolmaz. */
    const cevapTaslak = new Map();
    function soruCevapCiz(td, v) {
        const sc = v.soru_cevabi;
        if (sc && !v.soru) {
            td.appendChild(elYap("div", "dg-acik-soru-cevap-not", "Sorusuna cevabınız: " + tireSade(sc.cevap)
                + " (açıklama buna göre yazıldı)"));
            return;
        }
        if (!v.soru || saltOkunur) return;
        const kutu = elYap("div", "dg-acik-satir-cevap");
        if (sc) kutu.appendChild(elYap("div", "dg-acik-soru-cevap-not",
            "Önceki cevabınız: " + tireSade(sc.cevap) + ". Dil modeli yine soruyor; cevabı netleştirin."));
        const g = document.createElement("input");
        g.type = "text"; g.className = "dg-giris";
        g.placeholder = "Cevabınız";
        g.title = "Dil modeli açıklamayı cevabınıza göre yeniden yazar.";
        g.value = cevapTaslak.has(v.kolon) ? cevapTaslak.get(v.kolon) : "";
        g.disabled = kilitli;
        g.setAttribute("aria-label", v.kolon + " sorusuna cevabınız");
        g.addEventListener("input", () => cevapTaslak.set(v.kolon, g.value));
        const b = elYap("button", "dg-toplu-btn", "Cevabı Uygula");
        b.type = "button";
        b.disabled = kilitli;
        const uygula = () => {
            const cevap = g.value.trim();
            if (!cevap || kilitli) return;
            b.disabled = true;
            cevapTaslak.delete(v.kolon);
            const v2 = veriler.get(v.kolon);
            if (v2) { v2.soru_cevabi = { soru: v2.soru, cevap: cevap }; v2.durum = "isleniyor"; satirGuncelle(v2); }
            islem({ islem: "soru", kolon: v.kolon, cevap: cevap })
                .then(d => { if (d && d.hata) durumYaz(d.hata, true); yoklaHemen(); })
                .catch(() => yoklaHemen());
            if (degisti) degisti();
        };
        b.onclick = uygula;
        g.addEventListener("keydown", ev => { if (ev.key === "Enter") { ev.preventDefault(); uygula(); } });
        const sat = elYap("div", "dg-acik-soru-giris");
        sat.append(g, b);
        kutu.appendChild(sat);
        td.appendChild(kutu);
    }
    /* KOLON KARTI: onaylı ad parçalarından (kodla); açıklamanın üstünde. */
    function kartCiz(td, v) {
        const kartV = v.kart || {};
        const alanlar = ACK_KART_ADLARI.filter(([a]) => kartV[a]);
        const eksik = v.durum === "hazir" ? (v.ad_eksik || []) : [];
        if (!alanlar.length && !eksik.length) return;
        const kk = elYap("div", "dg-acik-kart");
        alanlar.forEach(([a, et]) => {
            const c = elYap("span", "dg-acik-kart-oge");
            c.appendChild(elYap("span", "dg-acik-kart-et", et + ":"));
            c.appendChild(document.createTextNode(" " + tireSade(kartV[a])));
            kk.appendChild(c);
        });
        eksik.forEach(e => kk.appendChild(adEksikCipi(e)));
        td.appendChild(kk);
    }
    /* Toplu onaya giren satır: hazır, onaysız, cevapsız sorusu ve kontrol
       notu yok (ad ve dağılım notu bilgi; toplu onayı durdurmaz). */
    function topluOlur(v) {
        return v.durum === "hazir" && !v.onayli && !v.soru && !(v.kontrol || []).length;
    }
    /* Görünen satırlar: kapalı ailenin üyeleri görünmez. */
    let cizilenler = [];
    function gorunenler() {
        return cizilenler.map(k => veriler.get(k)).filter(Boolean);
    }

    function satirGuncelle(v) {
        const e = el.get(v.kolon);
        if (!e) return;
        const kilit = kilitli || saltOkunur || bekliyorMu(v);
        e.onayK.checked = !!v.onayli;
        e.onayK.disabled = kilitli || saltOkunur || bekliyorMu(v);
        e.tr.classList.toggle("dg-parca-onayli", !!v.onayli);
        if (e.giris) {
            if (document.activeElement !== e.giris && ackSade(e.giris.value) !== ackSade(ackTaban(v)))
                e.giris.value = ackTaban(v);
            e.giris.disabled = kilit;
        }
        duzeltilmisCiz(e.tdD, v);
        e.tr.classList.toggle("dg-acik-degisti", v.durum === "hazir" && v.degisim === "degisen");
        e.tr.classList.toggle("dg-acik-sorulu", !!v.soru && v.durum === "hazir");
        e.tr.classList.toggle("dg-acik-kontrollu", !!(v.kontrol || []).length && v.durum === "hazir");
        e.tr.classList.toggle("dg-duzenlendi", ackElleNot(v));
        const aile = Number(v.aile_boyu || 1);
        e.aileEl.textContent = aile > 1 ? "Aile: " + ftBinlik(aile) + " kolon" : "";
        e.aileEl.title = aile > 1 ? "Adı yalnız sayılarla ayrılan kolonlar" : "";
        /* Notu aileye uygula / geri al */
        if (!saltOkunur && aile > 1 && ackElleNot(v)) {
            e.aileBtn.hidden = false;
            e.aileBtn.dataset.uygula = v.aileye_uygulandi ? "0" : "1";
            e.aileBtn.textContent = v.aileye_uygulandi
                ? "Ailedeki " + ftBinlik(aile - 1) + " Kolondan Geri Al"
                : "Ailedeki " + ftBinlik(aile - 1) + " Kolona da Uygula";
            e.aileBtn.disabled = kilit;
        } else e.aileBtn.hidden = true;
        e.notBilgi.hidden = !v.aile_notu_kaynagi;
        e.notBilgi.textContent = v.aile_notu_kaynagi
            ? v.aile_notu_kaynagi + " kolonundaki notunuz bu kolona da uygulandı." : "";
        const ab = aileBas.get(v.aile);
        if (ab) ab.guncelle();
        asamaTazele();
    }
    /* Onay değişince aşama çubuğu; aktif aşama değiştiyse tablo da. */
    let sonAktif_ = null;
    function asamaTazele() {
        if (!yuklendi || saltOkunur) return;
        hepsiDurum();
        const a = aktifAsama();
        if (a !== sonAktif_) {
            const ilk = sonAktif_ === null;
            sonAktif_ = a;
            if (!ilk) { gosterilen = ACK_SAYFA; suzgec = "tumu"; suzgecCiz(); tabloYenidenCiz(); return; }
        }
        asamaCiz();
    }

    /* ---- AİLELER ----
       Adı yalnız sayılarla ayrılan kolonlar (aynı ölçümün farklı dönemleri)
       bir başlık altında: ailenin anahtarı, ortak kart, açıklama kalıbı
       (sayılar [sayı]), onay sayısı. Tümü süzgecinde ve aramasız üyeler
       kapalı gelir; "Kolonları Aç ve Tek Tek Bak" açar. "Aileyi Onayla" kalıba uyan,
       notu olmayan hazır üyeleri onaylar; soru, not ya da kalıba uymayan
       üye tek tek bakılır. */
    const aileBas = new Map();         // aile -> {tr, guncelle}
    const acikAileler = new Set();
    /* Ailenin bu aşamadaki üyeleri: sorulu ve notlu üyeler Ayrılanlar'da. */
    const aileUyeleri = a => sira.map(k => veriler.get(k))
        .filter(v => v && v.aile === a && (saltOkunur || asamaOf(v) === 1));
    const aileAyrilan = a => saltOkunur ? [] : sira.map(k => veriler.get(k))
        .filter(v => v && v.aile === a && AYRI(asamaOf(v)));
    function aileDurumu(a) {
        const uyeler = aileUyeleri(a);
        const hazir = uyeler.filter(v => v.durum === "hazir");
        const [kalip, uyan] = ackAileKalibi(hazir.map(v => v.aciklama));
        const kalibaUyar = v => v.durum === "hazir" && ackSade(v.aciklama).replace(/\d+/g, "[sayı]") === kalip;
        const ortak = ACK_KART_ADLARI.filter(([k]) => {
            const d = new Set(hazir.map(v => ackSade((v.kart || {})[k])));
            return d.size === 1 && !d.has("");
        }).map(([k, et]) => [et, (hazir[0].kart || {})[k]]);
        const onaylanacak = uyeler.filter(v => !v.onayli && topluOlur(v) && kalibaUyar(v));
        const tek = uyeler.filter(v => !v.onayli && v.durum === "hazir" && !(topluOlur(v) && kalibaUyar(v)));
        /* Ada eklenecek bilgiler: kaç hazır üyede geçtiği ile. */
        const eksikM = new Map();
        hazir.forEach(v => (v.ad_eksik || []).forEach(e => {
            const k = e.tur + "|" + e.anlam;
            const x = eksikM.get(k) || { e, n: 0 };
            x.n++; eksikM.set(k, x);
        }));
        const eksik = [...eksikM.values()];
        return { uyeler, hazir, kalip, uyan, ortak, onaylanacak, tek, eksik,
                 onayli: uyeler.filter(v => v.onayli).length,
                 bekleyen: uyeler.filter(bekliyorMu).length };
    }
    function aileBasKur(a) {
        const tr = elYap("tr", "dg-acik-aile-bas");
        const td = elYap("td", "");
        td.colSpan = 5;
        tr.appendChild(td);
        /* AİLE KUTUSU: hangi kolonlar (değişen değerler), neyin
           onaylandığı (aile açıklaması ve ortak kart), tek düğme. */
        const guncelle = () => {
            const d = aileDurumu(a);
            const acik = aileAcikMi(a);
            const tamam = d.uyeler.length > 0 && d.onayli === d.uyeler.length;
            td.textContent = "";
            const kutu = elYap("div", "dg-acik-aile-kutu" + (tamam ? " tamam" : ""));
            const ust_ = elYap("div", "dg-acik-aile-ust");
            ust_.append(elYap("span", "dg-acik-aile-ad", ackAileAdi(a)),
                        elYap("span", "dg-acik-aile-durum" + (tamam ? " tamam" : ""),
                              tamam ? "✓ Onaylandı · " + ftBinlik(d.uyeler.length) + " kolon"
                                    : ftBinlik(d.onayli) + " / " + ftBinlik(d.uyeler.length) + " kolon onaylı"));
            kutu.appendChild(ust_);
            kutu.appendChild(elYap("div", "dg-acik-aile-uyeler",
                ftBinlik(d.uyeler.length) + " kolon: " + aileDegerleri(a, d.uyeler).join(" · ")));
            if (d.kalip) {
                const ack = elYap("div", "dg-acik-aile-ack");
                ack.appendChild(elYap("div", "dg-acik-aile-et",
                    d.uyan === d.hazir.length && d.hazir.length === d.uyeler.length
                        ? "Aile açıklaması (bütün kolonlarda aynı, yalnız [sayı] değişir)"
                        : "Aile açıklaması (" + ftBinlik(d.uyan) + " / " + ftBinlik(d.uyeler.length) + " kolonda aynı)"));
                ack.appendChild(elYap("div", "dg-acik-aile-metin", tireSade(d.kalip)));
                kutu.appendChild(ack);
            }
            if (d.ortak.length || d.eksik.length) {
                const kk = elYap("div", "dg-acik-kart dg-acik-aile-kart");
                d.ortak.forEach(([et, deger]) => {
                    const c = elYap("span", "dg-acik-kart-oge");
                    c.append(elYap("span", "dg-acik-kart-et", et + ":"), document.createTextNode(" " + tireSade(deger)));
                    kk.appendChild(c);
                });
                d.eksik.forEach(({ e, n }) => {
                    const c = adEksikCipi(e);
                    if (n < d.hazir.length) c.appendChild(document.createTextNode(
                        " (" + ftBinlik(n) + " / " + ftBinlik(d.hazir.length) + " kolonda)"));
                    kk.appendChild(c);
                });
                kutu.appendChild(kk);
            }
            if (d.bekleyen) kutu.appendChild(elYap("div", "dg-acik-not",
                ftBinlik(d.bekleyen) + " kolonun açıklamasını dil modeli henüz yazmadı."));
            const ayr = aileAyrilan(a);
            if (ayr.length) {
                const s4 = ayr.filter(v => asamaOf(v) === 4), s5 = ayr.filter(v => asamaOf(v) === 5);
                kutu.appendChild(elYap("div", "dg-acik-not",
                    "Bu ailenin " + ftBinlik(ayr.length) + " kolonu ayrıldı, burada yok: "
                    + [s4.length ? ftBinlik(s4.length) + " tanesi «Cevapsız Soru» listesinde ("
                        + aileDegerleri(a, s4).join(", ") + ")" : "",
                       s5.length ? ftBinlik(s5.length) + " tanesi «Kontrol Notu» listesinde ("
                        + aileDegerleri(a, s5).join(", ") + ")" : ""].filter(Boolean).join(", ") + "."));
            }
            if (d.tek.length) {
                const adlar = d.tek.slice(0, 4).map(v => v.kolon).join(", ") + (d.tek.length > 4 ? " ve diğerleri" : "");
                /* Neden toplu onaya girmiyor: her kolonun ilk sebebi. */
                const sebep = new Map();
                d.tek.forEach(v => {
                    const s_ = v.durum !== "hazir" ? "düzenlenemedi" : "açıklaması kalıptan farklı";
                    sebep.set(s_, (sebep.get(s_) || 0) + 1);
                });
                const neden = [...sebep].map(([k, n]) => k + ": " + ftBinlik(n)).join(", ");
                kutu.appendChild(elYap("div", "dg-acik-aile-uyari", d.onaylanacak.length
                    ? ftBinlik(d.tek.length) + " kolon toplu onaya girmiyor (" + neden + "); kolonları açıp "
                      + "tek tek onaylayın: " + adlar + "."
                    : d.onayli
                    ? "Toplu onaylanacak kolon kalmadı; kalan " + ftBinlik(d.tek.length) + " kolon ("
                      + neden + ") tek tek onaylanır: " + adlar + "."
                    : "Bu ailenin kolonları toplu onaylanamıyor (" + neden + "); kolonları açıp tek tek "
                      + "onaylayın: " + adlar + "."));
            }
            const dug = elYap("div", "dg-acik-aile-dugme");
            if (!saltOkunur && !tamam && d.onaylanacak.length) {
                const onayla = elYap("button", "dg-toplu-btn dg-acik-aile-onay",
                    "Aileyi Onayla · " + ftBinlik(d.onaylanacak.length) + " kolon");
                onayla.type = "button";
                onayla.disabled = kilitli || !d.onaylanacak.length;
                onayla.title = "Aile açıklaması bu kolonların hepsi için doğruysa basın. Açıklaması "
                    + "kalıba uyan ve notu olmayan kolonlar onaylanır.";
                onayla.onclick = () => aileyiOnayla(a);
                dug.appendChild(onayla);
            }
            if (!saltOkunur && d.onayli) {
                const kaldir = elYap("button", "dg-baglanti", "Onayı Kaldır");
                kaldir.type = "button";
                kaldir.disabled = kilitli;
                kaldir.onclick = () => aileOnayKaldir(a);
                dug.appendChild(kaldir);
            }
            const goster = elYap("button", "dg-baglanti", acik ? "Kolonları Kapat" : "Kolonları Aç ve Tek Tek Bak");
            goster.type = "button";
            goster.onclick = () => { if (acik) acikAileler.delete(a); else acikAileler.add(a); tabloYenidenCiz(); };
            dug.appendChild(goster);
            kutu.appendChild(dug);
            td.appendChild(kutu);
            tr.classList.toggle("dg-parca-onayli", tamam);
        };
        guncelle();
        const x = { tr, guncelle };
        aileBas.set(a, x);
        return x;
    }
    /* Ailenin kolonlarını ayıran değerler (adın sayılı parçaları: 3D, 7D). */
    function aileDegerleri(a, uyeler) {
        const k = a.split("_");
        return uyeler.map(v => {
            const t = String(v.kolon).split("_");
            if (t.length !== k.length) return v.kolon;
            const d = t.filter((x, i) => k[i].indexOf("#") !== -1);
            return d.length ? d.join("_") : v.kolon;
        });
    }
    function aileOnayKaldir(a) {
        if (kilitli || saltOkunur) return;
        const kolonlar = aileUyeleri(a).filter(v => v.onayli).map(v => v.kolon);
        if (!kolonlar.length) return;
        kolonlar.forEach(k => { const v = veriler.get(k); if (v) { v.onayli = false; satirGuncelle(v); } });
        const ab = aileBas.get(a); if (ab) ab.guncelle();
        asamaTazele();
        islem({ islem: "onay", kolonlar: kolonlar, onay: false })
            .then(d => { if (d && d.hata) durumYaz(d.hata, true); yoklaHemen(); })
            .catch(() => yoklaHemen());
        if (degisti) degisti();
    }
    function aileAcikMi(a) {
        return acikAileler.has(a) || suzgec !== "tumu" || !!arama;
    }
    function aileyiOnayla(a) {
        if (kilitli || saltOkunur) return;
        const kolonlar = aileDurumu(a).onaylanacak.map(v => v.kolon);
        if (!kolonlar.length) return;
        kolonlar.forEach(k => { const v = veriler.get(k); if (v) { v.onayli = true; satirGuncelle(v); } });
        const ab = aileBas.get(a); if (ab) ab.guncelle();
        asamaTazele();
        islem({ islem: "onay", kolonlar: kolonlar, onay: true })
            .then(d => { if (d && d.hata) durumYaz(d.hata, true); yoklaHemen(); })
            .catch(() => yoklaHemen());
        if (degisti) degisti();
    }
    /* Odak tablodaysa da (başlık düğmesi) yeniden çizer. */
    function tabloYenidenCiz() {
        if (tb.contains(document.activeElement)) document.activeElement.blur();
        tabloCiz();
    }

    function notKaydet(kolon) {
        const e = el.get(kolon), v = veriler.get(kolon);
        if (!e || !e.giris || !v || kilitli || saltOkunur) return;
        const metin = e.giris.value.trim();
        /* Öneri (ya da önceki düzenleme) aynen kaldıysa kayıt yok. Alan
           boşaltılırsa düzenleme kalkar, öneriyi dil modeli yeniden yazar. */
        if (ackSade(metin) === ackSade(ackTaban(v))) return;
        if (!metin && !ackElleNot(v)) { e.giris.value = ackTaban(v); return; }
        v.not = metin;
        v.elle = true;
        v.durum = "isleniyor";
        satirGuncelle(v);
        islem({ islem: "not", kolon: kolon, metin: metin, tam: true })
            .then(d => {
                if (d && d.hata) durumYaz(d.hata, true);
                yoklaHemen();
            })
            .catch(() => yoklaHemen());
        if (degisti) degisti();
    }

    function aileyeUygula(kolon) {
        const e = el.get(kolon);
        if (!e || kilitli) return;
        e.aileBtn.disabled = true;
        islem({ islem: "aile", kolon: kolon, uygula: e.aileBtn.dataset.uygula !== "0" })
            .then(d => {
                if (d && d.hata) durumYaz(d.hata, true);
                yoklaHemen();
            })
            .catch(() => yoklaHemen());
    }

    /* ---- Süzgeç ---- */
    function uyar(v, k_) {
        if (!saltOkunur && asamaOf(v) !== gorulenAsama()) return false;
        return suzgecUyar(v, k_ === undefined ? suzgec : k_) && aramaUyar(v);
    }
    function aramaUyar(v) {
        if (!arama) return true;
        return [v.kolon, v.orijinal, v.aciklama, v.not].join(" ")
            .toLocaleLowerCase("tr").includes(arama);
    }
    function suzgecUyar(v, suzgec) {
        const hazir = v.durum === "hazir";
        if (suzgec === "onaysiz" && v.onayli) return false;
        if (suzgec === "ek" && !(hazir && v.ek && !v.ek_acikta)) return false;
        if (suzgec === "degisen" && !(hazir && v.degisim === "degisen")) return false;
        if (suzgec === "yazim" && !(hazir && v.degisim === "yazim")) return false;
        if (suzgec === "ekdegisim" && !(hazir && v.degisim === "ek")) return false;
        if (suzgec === "soru" && !(hazir && v.soru)) return false;
        if (suzgec === "ad" && !(hazir && (v.ad_notu || v.dagilim_notu))) return false;
        if (suzgec === "kontrol" && !(hazir && (v.kontrol || []).length)) return false;
        if (suzgec === "elle" && !v.not) return false;
        if (suzgec === "hata" && v.durum !== "hata") return false;
        return true;
    }

    function tabloCiz() {
        /* Yazılan alan ekranda kalsın: odak tablodaysa yeniden çizim beklenir. */
        if (tb.contains(document.activeElement)) return;
        const uyan = sira.map(k => veriler.get(k)).filter(v => v && uyar(v));
        tb.textContent = "";
        /* Aileler (iki ya da daha çok uyan üye) bir arada; sayfa aileyi bölmez. */
        const gruplar = [], gIdx = new Map();
        const ayriListe = !saltOkunur && AYRI(gorulenAsama());
        uyan.forEach(v => {
            /* Ayrılanlar listesinde aile kutusu yok: her kolon kendi satırında. */
            const a = !ayriListe && v.aile && Number(v.aile_boyu || 1) > 1 ? v.aile : null;
            if (!a) { gruplar.push({ a: null, uyeler: [v] }); return; }
            if (!gIdx.has(a)) { gIdx.set(a, gruplar.length); gruplar.push({ a, uyeler: [] }); }
            gruplar[gIdx.get(a)].uyeler.push(v);
        });
        cizilenler = [];
        let sayilan = 0, gi = 0;
        for (; gi < gruplar.length && sayilan < gosterilen; gi++) {
            const g = gruplar[gi];
            sayilan += g.uyeler.length;
            const satirCiz_ = v => {
                const e = el.get(v.kolon);
                tb.appendChild(e ? e.tr : satirKur(v));
                cizilenler.push(v.kolon);
            };
            if (!g.a || g.uyeler.length < 2) {
                g.uyeler.forEach(v => { satirCiz_(v); el.get(v.kolon).tr.classList.remove("dg-acik-aile-uye"); });
                continue;
            }
            const ab = aileBas.get(g.a) || aileBasKur(g.a);
            ab.guncelle();
            tb.appendChild(ab.tr);
            if (aileAcikMi(g.a)) {
                /* Açılan ailenin kolonları kendi sütun başlığıyla. */
                const alt = elYap("tr", "dg-acik-alt-bas");
                ["Kolon", "Orijinal", "Sizin Düzenlemeniz", "Kart ve Açıklama", "Onay"]
                    .forEach(h => alt.appendChild(elYap("th", "", h)));
                tb.appendChild(alt);
                g.uyeler.forEach(v => { satirCiz_(v); el.get(v.kolon).tr.classList.add("dg-acik-aile-uye"); });
            }
        }
        const kalan = uyan.length - Math.min(uyan.length, sayilan);
        const kalanAile = gruplar.slice(gi).filter(g => g.a && g.uyeler.length > 1).length;
        dahaBtn.hidden = kalan <= 0;
        dahaBtn.textContent = kalanAile && kalanAile === gruplar.length - gi
            ? "Daha Fazla Aile Göster (" + ftBinlik(kalanAile) + " aile daha)"
            : "Daha Fazla Göster (" + ftBinlik(kalan) + " satır daha)";
        /* Aileler aşamasında üst sütun başlığı yok (kutular kendini anlatır). */
        th.hidden = !saltOkunur && gorulenAsama() === 1;
        topluOnay.hidden = saltOkunur;
        topluOnay.disabled = kilitli || !gorunenler().some(topluOlur);
        bicimDurum();
        bosEl.hidden = !(yuklendi && !uyan.length);
        bosEl.textContent = sira.length ? "Bu süzgece uyan satır yok."
            : atlandi ? "Açıklamalar değiştirilmeden geçildi." : "Düzenlenecek kolon yok.";
        if (!yuklendi) { bosEl.hidden = false; bosEl.textContent = "Satırlar yükleniyor"; }
    }

    function suzgecCiz() {
        asamaCiz();
        /* Sayılar görülen aşamanın satırlarından (salt okunurda bütün kart). */
        const satirlar_ = sira.map(k => veriler.get(k))
            .filter(v => v && (saltOkunur || asamaOf(v) === gorulenAsama()));
        ACK_SUZGECLER.forEach(([k, et, sk]) => {
            const b = suzBtn[k];
            const n = satirlar_.filter(v => suzgecUyar(v, k)).length;
            b.textContent = et + " · " + ftBinlik(n);
            b.classList.toggle("secili", suzgec === k);
            b.hidden = k !== "tumu" && !n && suzgec !== k;
        });
    }

    /* ---- Anlamı kayan aileler ---- */
    const kaymaTaslak = new Map();
    function kaymaCiz() {
        kaymaKap.textContent = "";
        const liste = (kayma && kayma.aileler) || [];
        kaymaKap.hidden = saltOkunur || !kayma || cevapsizSoru() > 0 || (!liste.length && !kaymaSurer());
        if (kaymaKap.hidden) return;
        const bas = elYap("div", "dg-kisa-tablo-baslik", "Anlamı Kayan Aileler · "
            + (kaymaSurer() ? "karşılaştırılıyor" : ftBinlik(kaymaBekleyen()) + " karar bekliyor"));
        bas.appendChild(bolmeBilgiSimgesi(
            "Dil modeli her ailenin bir kolonunda sözlükteki orijinal açıklamayı yeni açıklamayla "
            + "karşılaştırır. Yalnız anlamın açıkça değiştiği aileler burada sorulur (dönem, hesap ya "
            + "da ölçülen şey farklı); yazım ve netleştirme sorulmaz. Doğru anlamı yazarsanız ailenin "
            + "bütün kolonlarına, her kolonun kendi sayılarına uyarlanarak gider ve dil modeli ailenin "
            + "açıklamalarını yeniden yazar. Yeni açıklama doğruysa «Yeni Açıklama Doğru»ya basın. "
            + "Cevabınız bir dönem kalıbının adda belirli bir parça geçince farklı anlam taşıdığını "
            + "gösteriyorsa (ör. RATIO geçince 3D_7D son 3 gün ile son 7 gün) altında Dönem Bilgisi'ne "
            + "koşullu anlam olarak kaydetmek önerilir; öneri sayılarla doğrulanır, kaydetmek sizin kararınız.",
            "Anlamı Kayan Aileler"));
        kaymaKap.appendChild(bas);
        if (kaymaSurer()) kaymaKap.appendChild(elYap("div", "dg-acik-ornek",
            "Karşılaştırılıyor: " + ftBinlik(kayma.biten || 0) + " / " + ftBinlik(kayma.toplam || 0) + " aile."));
        liste.forEach(x => {
            const kutu = elYap("div", "dg-acik-soru");
            const ust_ = elYap("div", "dg-acik-soru-ust");
            ust_.appendChild(elYap("span", "dg-donem-kalip", x.kolon_sayisi > 1
                ? ackAileAdi(x.anahtar) : x.kolon));
            ust_.appendChild(elYap("span", "dg-acik-soru-sayi", ftBinlik(x.kolon_sayisi) + " kolon"));
            if (x.karar) ust_.appendChild(elYap("span", "dg-rozet-kucuk", x.yaziliyor ? "Yeniden yazılıyor"
                : x.karar === "dogru" ? "Yeni açıklama doğru" : "Cevaplandı"));
            kutu.appendChild(ust_);
            if (x.neden) kutu.appendChild(elYap("div", "dg-donem-soru", tireSade(x.neden)));
            if (x.kolon_sayisi > 1) kutu.appendChild(elYap("div", "dg-acik-ornek", "Örnek kolon: " + x.kolon));
            /* KULLAN: karar verilmemiş ailede orijinal ve yeni açıklama
               tıklanınca "Ailenin doğru anlamı" kutusuna yazılır; imleç
               sonda, kullanıcı üstünde düzeltip «Cevabı Uygula» der. */
            let girdi = null;
            const metinSatiri = (etiket, metin) => {
                const sat = elYap("div", "dg-acik-ornek");
                if (x.karar || kilitli || !metin) {
                    sat.textContent = etiket + ": " + metin;
                    return sat;
                }
                sat.classList.add("dg-acik-kullan-satir");
                sat.appendChild(document.createTextNode(etiket + ": "));
                const yaz = () => {
                    if (!girdi) return;
                    girdi.value = metin;
                    kaymaTaslak.set(x.anahtar, metin);
                    girdi.focus();
                    girdi.setSelectionRange(metin.length, metin.length);
                };
                const m = elYap("button", "dg-acik-kullan-metin", metin);
                m.type = "button";
                m.title = "Kutuya yaz; üstünde düzeltebilirsiniz";
                m.onclick = yaz;
                const b = elYap("button", "dg-toplu-btn dg-acik-kullan", "Bunu Kullan");
                b.type = "button";
                b.title = m.title;
                b.onclick = yaz;
                sat.append(m, b);
                return sat;
            };
            kutu.appendChild(metinSatiri("Orijinal", tireSade(x.orijinal || "")));
            if (x.aciklama) kutu.appendChild(metinSatiri("Yeni açıklama", tireSade(x.aciklama)));
            if (x.karar) {
                const sat = elYap("div", "dg-acik-soru-yol", x.karar === "dogru"
                    ? "Yeni açıklamanın doğru olduğunu söylediniz."
                    : "Cevabınız: " + tireSade(x.cevap) + (x.yaziliyor
                        ? " Ailenin açıklamaları buna göre yeniden yazılıyor."
                        : " Ailenin açıklamaları buna göre yazıldı."));
                if (!kilitli) {
                    const geri = elYap("button", "dg-baglanti", "Kararı Değiştir");
                    geri.type = "button";
                    geri.onclick = () => kaymaIslem(x, "", "", geri);
                    sat.appendChild(document.createTextNode(" "));
                    sat.appendChild(geri);
                }
                kutu.appendChild(sat);
                const ko = kosulKutusu(x);
                if (ko) kutu.appendChild(ko);
                kaymaKap.appendChild(kutu);
                return;
            }
            kutu.appendChild(elYap("div", "dg-acik-soru-yol",
                "Ailenin doğru anlamını " + (x.kolon_sayisi > 1 ? "örnek kolonun sayılarıyla " : "")
                + "yazın (ör. «son 3 gündeki işlem adedinin son 7 gündeki işlem adedine oranı»)"
                + (x.kolon_sayisi > 1 ? "; sayılar her kolonda kendi dönemine uyarlanır" : "")
                + ". Yeni açıklama doğruysa «Yeni Açıklama Doğru»ya basın."));
            const satir = elYap("div", "dg-acik-soru-giris");
            const g = document.createElement("input");
            g.type = "text"; g.className = "dg-giris";
            g.placeholder = "Ailenin doğru anlamı";
            g.value = kaymaTaslak.get(x.anahtar) || "";
            g.disabled = kilitli;
            g.setAttribute("aria-label", x.anahtar + " doğru anlamı");
            g.addEventListener("input", () => kaymaTaslak.set(x.anahtar, g.value));
            girdi = g;
            const b = elYap("button", "dg-toplu-btn", "Cevabı Uygula");
            b.type = "button"; b.disabled = kilitli;
            b.onclick = () => { if (g.value.trim()) kaymaIslem(x, "cevap", g.value.trim(), b); };
            g.addEventListener("keydown", ev => { if (ev.key === "Enter") { ev.preventDefault(); b.click(); } });
            const dogru = elYap("button", "dg-toplu-btn", "Yeni Açıklama Doğru");
            dogru.type = "button"; dogru.disabled = kilitli;
            dogru.onclick = () => kaymaIslem(x, "dogru", "", dogru);
            satir.append(g, b, dogru);
            kutu.appendChild(satir);
            kaymaKap.appendChild(kutu);
        });
    }
    /* KOŞULLU ANLAM ÖNERİSİ: ailenin cevabından Dönem Bilgisi'ne (01.2.4.1)
       koşullu anlam. Dil modeli çıkarır, kod sayılarla doğrular; kaydetmek
       kullanıcının kararı. */
    function kosulKutusu(x) {
        const o = x.kosul;
        if (!o || o.durum === "yok") return null;
        const kutu = elYap("div", "dg-acik-kosul");
        if (o.durum === "calisiyor") {
            kutu.appendChild(elYap("div", "dg-acik-ornek",
                "Cevabınızdan Dönem Bilgisi için koşullu anlam çıkarılıyor."));
            return kutu;
        }
        if (o.durum === "hata" || o.durum === "dogrulanamadi") {
            kutu.appendChild(elYap("div", "dg-acik-ornek", "Cevabınızdan Dönem Bilgisi için koşullu anlam "
                + "önerilmedi. " + tireSade(donemNedenGoster(o.neden || ""))));
            return kutu;
        }
        const kal = donemSayiGoster(o.kalip), anl = donemAnlamGoster(o.kalip, o.anlam);
        const kural = "adında " + o.parca + " geçen kolonlarda " + kal + " «" + anl + "» demek";
        if (o.durum === "zaten") {
            kutu.appendChild(elYap("div", "dg-acik-ornek", "Dönem Bilgisi'nde bu koşullu anlam zaten var: "
                + kural + "."));
            return kutu;
        }
        const islemDugmesi = (yazi, karar, sinif) => {
            const b = elYap("button", sinif || "dg-toplu-btn", yazi);
            b.type = "button"; b.disabled = kilitli;
            b.onclick = () => kosulIslem(x, karar, b);
            return b;
        };
        if (o.karar) {
            const sat = elYap("div", "dg-acik-soru-yol", o.karar === "kaydet"
                ? "Dönem Bilgisi'ne kaydedildi: " + kural + ". Adında " + o.parca + " ve " + kal + " geçen "
                  + ftBinlik(o.kolon_sayisi) + " kolonun kartı ve açıklaması bu anlamla yeniden yazılıyor."
                : "Koşullu anlam Dönem Bilgisi'ne kaydedilmedi.");
            if (!kilitli) {
                sat.appendChild(document.createTextNode(" "));
                sat.appendChild(islemDugmesi(o.karar === "kaydet" ? "Geri Al" : "Kararı Değiştir", "",
                                             "dg-baglanti"));
            }
            kutu.appendChild(sat);
            return kutu;
        }
        kutu.appendChild(elYap("div", "dg-acik-kosul-bas",
            "Dönem Bilgisi'ne de koşullu anlam olarak kaydedilsin mi?"));
        kutu.appendChild(elYap("div", "dg-acik-ornek", "Cevabınıza göre " + kural + "."
            + (o.neden ? " " + tireSade(donemNedenGoster(o.neden)) : "")));
        kutu.appendChild(elYap("div", "dg-acik-ornek", "Örnek kolon " + o.kolon + " (" + o.deger + "): şu an «"
            + tireSade(o.genel) + "», kaydedilirse «" + tireSade(o.dolu) + "»."));
        if (o.mevcut) kutu.appendChild(elYap("div", "dg-acik-ornek", "Dönem Bilgisi'nde " + o.parca
            + " için şu an «" + donemAnlamGoster(o.kalip, o.mevcut) + "» yazıyor; kaydedilirse bunun yerine geçer."));
        const etki = elYap("div", "dg-acik-ornek", "Kaydedilirse adında " + o.parca + " ve " + kal + " geçen "
            + ftBinlik(o.kolon_sayisi) + " kolonun kartı ve açıklaması bu anlamla yeniden yazılır; "
            + "sonraki çalışmalarda da hafızadan gelir.");
        const orn = o.ornekler || [];
        if (orn.length) {
            const i_ = bolmeBilgiSimgesi(orn.map(([ad, dg, dolu]) => ad + "\n" + dg + ": «" + tireSade(dolu) + "»")
                .join("\n\n"), "Etkilenen kolonlardan örnek");
            i_.classList.add("bolme-info-genis");
            etki.appendChild(i_);
        }
        kutu.appendChild(etki);
        if (o.uymayan_sayisi) {
            const u = elYap("div", "dg-acik-kosul-uyari", ftBinlik(o.uymayan_sayisi)
                + " kolonun sözlük açıklamasındaki sayılar bu anlamla tutmuyor; kaydetmeden önce bakın:");
            (o.uymayan || []).forEach(([ad, dolu, orj]) => u.appendChild(elYap("div", "dg-acik-ornek",
                ad + ": bu anlamla «" + tireSade(dolu) + "», açıklaması «" + tireSade(orj) + "»")));
            if (o.uymayan_sayisi > (o.uymayan || []).length) u.appendChild(elYap("div", "dg-acik-ornek",
                "ve " + ftBinlik(o.uymayan_sayisi - o.uymayan.length) + " kolon daha."));
            kutu.appendChild(u);
        }
        const sat = elYap("div", "dg-acik-soru-giris");
        sat.append(islemDugmesi("Kaydet", "kaydet"), islemDugmesi("Kaydetme", "kaydetme"));
        kutu.appendChild(sat);
        return kutu;
    }
    function kosulIslem(x, karar, dugme) {
        if (kilitli || saltOkunur) return;
        dugme.disabled = true;
        islem({ islem: "kosul", aile: x.anahtar, karar: karar })
            .then(d => {
                if (d && d.hata) durumYaz(d.hata, true);
                else if (karar === "kaydet") durumYaz("Koşullu anlam Dönem Bilgisi'ne kaydedildi; "
                    + ftBinlik(x.kosul.kolon_sayisi) + " kolon yeniden yazılıyor.", false);
                yoklaHemen();
            })
            .catch(() => yoklaHemen())
            .finally(() => { dugme.disabled = false; });
    }
    function kaymaIslem(x, karar, cevap, dugme) {
        if (kilitli || saltOkunur) return;
        dugme.disabled = true;
        if (karar) kaymaTaslak.delete(x.anahtar);
        islem({ islem: "kayma", aile: x.anahtar, karar: karar, cevap: cevap })
            .then(d => {
                if (d && d.hata) durumYaz(d.hata, true);
                else if (karar === "cevap") durumYaz("Cevabınız ailenin " + ftBinlik(x.kolon_sayisi)
                    + " kolonuna uygulandı; açıklamalar yeniden yazılıyor.", false);
                yoklaHemen();
            })
            .catch(() => yoklaHemen())
            .finally(() => { dugme.disabled = false; });
    }

    /* ---- Toplu sorular ---- */
    function sorulariCiz() {
        soruKap.textContent = "";
        const liste = saltOkunur ? [] : (sorular || []);
        soruKap.hidden = !liste.length;
        if (!liste.length) return;
        const acik = liste.filter(s => s.soru_kolon > 0 && !s.cevap).length;
        const bas = elYap("div", "dg-kisa-tablo-baslik",
                          "Toplu Sorular · " + ftBinlik(acik) + " cevapsız");
        bas.appendChild(bolmeBilgiSimgesi(
            "Dil modeli parçanın onaylı anlamını (Ad Parçaları) biliyor; burada o anlamın "
            + "yetmediği yeri soruyor (ör. RATIO oran, ama hangi dönem hangisine bölünüyor). "
            + "Aynı parça hakkındaki sorular bir kez sorulur. Cevabınız o parçanın geçtiği "
            + "bütün kolonlarda dil modeline kesin bilgi olarak verilir ve o kolonlar yeniden "
            + "düzenlenir. Cevap yalnız dil modelinin anlaması içindir: karta ve açıklamaya "
            + "kopyalanmaz; kartta parçanın onaylı anlamı kalır.",
            "Toplu Sorular"));
        soruKap.appendChild(bas);
        liste.forEach(s => {
            const kutu = elYap("div", "dg-acik-soru");
            const ust_ = elYap("div", "dg-acik-soru-ust");
            ust_.appendChild(elYap("span", "dg-donem-kalip", s.parca));
            /* Onaylı anlam: soru bunu sormuyor, bunun yetmediği yeri soruyor. */
            if (s.anlam) ust_.appendChild(elYap("span", "dg-acik-soru-anlam",
                "Onaylı anlamı: " + tireSade(s.anlam)));
            ust_.appendChild(elYap("span", "dg-acik-soru-sayi",
                ftBinlik(s.kolon_sayisi) + " kolonda geçiyor"
                + (s.soru_kolon ? " · " + ftBinlik(s.soru_kolon) + " kolonda soru" : "")));
            if (s.cevap) ust_.appendChild(elYap("span", "dg-rozet-kucuk", "Cevaplandı"));
            kutu.appendChild(ust_);
            /* Farklı sorular ayrı ayrı, her biri hangi kolonlardan geldiğiyle. */
            (s.sorular || []).forEach(q => {
                const metin = typeof q === "string" ? q : q.soru;
                const sk = elYap("div", "dg-acik-soru-satir");
                sk.appendChild(elYap("div", "dg-donem-soru", tireSade(metin)));
                if (typeof q !== "string" && (q.kolonlar || []).length)
                    sk.appendChild(elYap("div", "dg-acik-ornek", ftBinlik(q.kolon_sayisi) + " kolon: "
                        + q.kolonlar.join(", ") + (q.kolon_sayisi > q.kolonlar.length ? " ve diğerleri" : "")));
                kutu.appendChild(sk);
            });
            if (s.soru_sayisi > (s.sorular || []).length)
                kutu.appendChild(elYap("div", "dg-acik-ornek", "ve " + ftBinlik(s.soru_sayisi - s.sorular.length)
                    + " farklı soru daha"));
            if (!(s.sorular || []).length && (s.ornek || []).length)
                kutu.appendChild(elYap("div", "dg-acik-ornek", "Örnek: " + s.ornek.join(", ")));
            kutu.appendChild(elYap("div", "dg-acik-soru-yol",
                ((s.sorular || []).length ? "Dil modeli " + (s.anlam ? "«" + tireSade(s.anlam) + "» anlamının" : "bu parçanın")
                    + " yetmediği yeri soruyor (yukarıdaki " + ((s.sorular || []).length > 1 ? "sorular" : "soru") + "). " : "")
                + "Cevabı " + s.parca + " geçen " + ftBinlik(s.kolon_sayisi) + " kolonun hepsinde geçerli bir kural "
                + "olarak yazın (ör. «adda önce gelen dönemin değeri sonrakine bölünür»); belirli bir dönem ya da "
                + "sayı yazmayın. Cevap dil modelinin anlaması içindir, karta ve açıklamaya kopyalanmaz. Tek "
                + "kolona özel bilgi için o kolonun «Sizin Düzenlemeniz» alanını kullanın."));
            const satir = elYap("div", "dg-acik-soru-giris");
            const g = document.createElement("input");
            g.type = "text"; g.className = "dg-giris";
            g.value = tireSade(s.cevap || "");
            g.placeholder = "Cevabınız (bütün " + s.parca + " kolonları için geçerli kural)";
            g.disabled = kilitli;
            g.setAttribute("aria-label", s.parca + " için cevabınız");
            const etiket = s.cevap ? "Cevabı Güncelle" : "Cevabı Uygula";
            const b = elYap("button", "dg-toplu-btn", etiket);
            b.type = "button";
            b.disabled = kilitli;
            /* Cevapta sayı varsa (belirli dönem, örnek kolon) ilk tıklama
               uyarır; ikinci tıklama uygular. */
            const uyari = elYap("div", "dg-acik-soru-uyari", "");
            uyari.hidden = true;
            let sorgu = false;
            g.addEventListener("input", () => {
                if (!sorgu) return;
                sorgu = false; uyari.hidden = true; b.textContent = etiket; b.classList.remove("onay-bekliyor");
            });
            b.onclick = () => {
                const cevap = g.value.trim();
                if (!cevap && !s.cevap) return;
                if (/\d/.test(cevap) && !sorgu) {
                    sorgu = true;
                    uyari.hidden = false;
                    uyari.textContent = "Cevabınızda sayı var (" + (cevap.match(/\d+/g) || []).slice(0, 4).join(", ")
                        + "). Bu cevap " + s.parca + " geçen " + ftBinlik(s.kolon_sayisi) + " kolonun hepsinde "
                        + "kullanılır; belirli bir dönem ya da örnek başka kolonları yanıltabilir. Genel "
                        + "yazmak için cevabı düzeltin ya da yine de uygulamak için düğmeye bir kez daha basın.";
                    b.textContent = "Yine de Uygula";
                    b.classList.add("onay-bekliyor");
                    return;
                }
                sorgu = false; uyari.hidden = true; b.textContent = etiket; b.classList.remove("onay-bekliyor");
                b.disabled = true;
                islem({ islem: "parca", parca: s.parca, cevap: cevap })
                    .then(d => {
                        if (d && d.hata) durumYaz(d.hata, true);
                        else durumYaz(s.parca + " için cevabınız " + ftBinlik(d.kolon_sayisi || 0)
                                      + " kolona uygulandı; bu kolonlar yeniden düzenleniyor.", false);
                        yoklaHemen();
                    })
                    .catch(() => yoklaHemen())
                    .finally(() => { b.disabled = false; });
            };
            satir.append(g, b);
            kutu.appendChild(satir);
            kutu.appendChild(uyari);
            soruKap.appendChild(kutu);
        });
    }

    function durumYaz(metin, hata) {
        metinYaz(durumEl, metin || "");
        durumEl.classList.toggle("dg-acik-hata", !!hata);
        durumEl.hidden = !metin;
    }

    function ilerYaz() {
        const calisiyor = dm === "calisiyor" && !saltOkunur;
        ilerEl.classList.toggle("gorunur", calisiyor && !kilitli);
        if (!calisiyor) return;
        const p = ilerleme || {};
        const gecen = Math.max(0, Math.floor((Date.now() - ilerBas) / 1000));
        ilerMetin.textContent = "Dil modeli açıklamaları düzenliyor · "
            + ftBinlik(Number(sayac.hazir || 0)) + " / " + ftBinlik(Number(sayac.toplam || 0))
            + " kolon hazır · " + sureBicim(gecen);
        if (p.gecen !== undefined && !ilerSabit) { ilerBas = Date.now() - p.gecen * 1000; ilerSabit = true; }
    }

    /* ---- Yoklama ---- */
    function isle(a) {
        dm = a.dm || "bitti";
        saltOkunur = !!a.salt_okunur || !!ilkKilit;
        atlandi = !!a.atlandi;
        sayac = a.sayac || {};
        sorular = a.sorular || [];
        kayma = a.kayma || null;
        hataMetni = a.hata || "";
        ilerleme = a.ilerleme || null;
        if (!ilerleme) ilerSabit = false;
        (a.satirlar || []).forEach(v => {
            if (!veriler.has(v.kolon)) sira.push(v.kolon);
            veriler.set(v.kolon, v);
            satirGuncelle(v);
        });
        son = Math.max(son, Number(a.son || 0));
        yuklendi = true;
        if (sonAktif_ === null && !saltOkunur) sonAktif_ = aktifAsama();
        suzgecCiz();
        tabloCiz();
        sorulariCiz();
        kaymaCiz();
        evreCiz();
        if (dm !== "calisiyor") iptalSifirla();
        if (dm === "iptal") {
            const gelecek = Number(a.gelecek || 0);
            durumYaz("Dil modeli durduruldu; " + ftBinlik(Number(sayac.bekleyen || 0))
                     + " kolon düzenlenmedi. Onaylarsanız bu kolonların orijinal açıklaması kalır."
                     + (gelecek ? " İptal anında gönderilmiş " + ftBinlik(gelecek)
                        + " kolonun cevabı gelirse tabloya eklenir." : ""),
                     false);
            durumEl.appendChild(devamBtn);
        } else if (hataMetni && Number(sayac.hata || 0)) {
            durumYaz(hataMetni, true);
            devamBtn.textContent = "Düzenlenemeyenleri Yeniden Dene";
            durumEl.appendChild(devamBtn);
        } else if (durumEl.contains(devamBtn)) durumYaz("", false);
        ilerYaz();
        if (degisti) degisti();
    }

    function zamanla(ms) {
        if (yoklamaZaman) clearTimeout(yoklamaZaman);
        yoklamaZaman = setTimeout(yokla, ms);
    }
    function yoklaHemen() { zamanla(300); }
    function yokla() {
        yoklamaZaman = null;
        if (!kart.isConnected) return;
        fetch(getWebAppBackendUrl("aciklama_alani") + "?oturum_id=" + encodeURIComponent(OTURUM_ID)
              + "&son=" + encodeURIComponent(String(saltOkunur ? 0 : son)))
            .then(r => r.json())
            .then(d => {
                const a = d && d.aciklama;
                if (!a) { durumYaz((d && d.hata) || "Satırlar alınamadı.", true); zamanla(8000); return; }
                isle(a);
                const surer = !saltOkunur && ((dm === "calisiyor" || Number(sayac.bekleyen || 0) > 0)
                    && dm !== "iptal" || kaymaSurer() || kosulSurer());
                /* İptal anında yolda olan cevaplar sonradan gelir; gelene dek
                   seyrek yoklanır (sayılar ve onay gerekçesi güncel kalsın). */
                if (surer) zamanla(ACK_YOKLAMA);
                else if (!saltOkunur && dm === "iptal" && Number(a.gelecek || 0) > 0)
                    zamanla(ACK_YOKLAMA * 2);
            })
            .catch(() => zamanla(8000));
    }
    /* İlk yoklama kart sayfaya eklendikten sonra (bu fonksiyon döndüğünde
       kart henüz DOM'da değil). */
    zamanla(0);

    /* Kaydedilmemiş notlar (alan bırakılmadan onaya basıldıysa). */
    function kaydedilmemis() {
        let n = 0;
        el.forEach((e, kolon) => {
            const v = veriler.get(kolon);
            if (e.giris && v && ackSade(e.giris.value) !== ackSade(ackTaban(v))
                    && (e.giris.value.trim() || ackElleNot(v))) {
                n++;
                notKaydet(kolon);
            }
        });
        return n;
    }

    return {
        bekliyor: () => !saltOkunur && dm !== "iptal"
            && (dm === "calisiyor" || Number(sayac.bekleyen || 0) > 0),
        durduruldu: () => dm === "iptal",
        sayac: () => Object.assign({}, sayac),
        /* Etkin aşama ve onay bekleyenleri (alttaki gerekçe için). */
        /* Soru evresi: cevapsız soru sayısı (alttaki gerekçe için). */
        soruEvresi: () => soruEvresi() ? { cevapsiz: cevapsizSoru(), surer: dmSurer(),
                                           kayma: kaymaBekleyen(), kaymaSurer: kaymaSurer(),
                                           kosulSurer: kosulSurer() } : null,
        asama: () => {
            if (!yuklendi || saltOkunur) return null;
            const n = aktifAsama(), bekleyen = asamaSatirlari(n).filter(v => !v.onayli);
            return { n: asamaNo(n), kod: n, ad: asamaBilgi(n)[1], toplam: gorunurAsamalar().length,
                     kalan: bekleyen.length, aile: new Set(bekleyen.map(v => v.aile)).size };
        },
        kaydedilmemis: kaydedilmemis,
        kilitle: k => {
            kilitli = k;
            veriler.forEach(v => satirGuncelle(v));
            sorulariCiz();
            kaymaCiz();
            evreCiz();
            iptalBtn.disabled = k || iptalBtn.textContent !== "İptal";
            devamBtn.disabled = k;
            ilerYaz();
        }
    };
}

/* ==================== 01.2.4.1 Dönem Bilgisi ====================
   Kolon adlarındaki dönem parçalarının kalıpları (kod bulur, anlam
   vermez); anlamı dil modeli tanımlardan okuyarak önerir, kullanıcı
   onaylar ya da düzeltir. Dönem bilgisi olmayan satır "Çıkar" ile
   çıkarılır (altta listelenir, geri alınabilir); tabloda kalan bütün
   satırlar onayda dönem bilgisi olur ve hafızaya yazılır. Altta kolon
   adlarındaki bütün kısaltmalar düz liste; tıklanan kısaltma elle dönem
   satırı olarak eklenir. Model yorumlarken satırlar görünür ama
   kilitlidir; yoklamayla tazelenir.

   DURUM: satırlar renksiz; anlamın üstündeki tek satır etiket nereden
   geldiğini yazar (dil modeli ve kanıtı, hafıza, düzenlendi, kontrol). */

/* YER TUTUCU KONTROLÜ (arka uçtaki donem.yer_tutucu_hatasi ile aynı
   kural): kalıptaki <N> için "N", <NN> için "NN" yazılır; başka biçim
   ya da kalıpta olmayan yer tutucu hata. */
/* Köşeli biçim (<N>, <N#1>) kendi sınırını taşır: harfe bitişik de yer
   tutucudur ("<N>gün"); harf sınırı yalnız çıplak N / NN için aranır
   (yoksa "<N>gün" içindeki N tek başına yakalanıp "<3>gün" olurdu). İlk
   grup (önceki karakter) artık hep boş; çağıranlar onu aynen geri yazar. */
const DONEM_YT_ADAY = /()(<\s*[Nn]\s*#[^<>]{1,60}>|<\s*[Nn]{1,2}\s*>|(?<![0-9A-Za-zÇĞİÖŞÜçğıöşü])[Nn]{1,2}(?![0-9A-Za-zÇĞİÖŞÜçğıöşü]))/g;
/* SIRA NUMARALI VE HESAPLI YER TUTUCU (akis: donem.formul_* ile aynı
   kural): <N#k> kalıbın k'inci sayısı (ekranda "[sayı k]"); <N#formül>
   formülde $k kalıbın k'inci sayısı, tam sayılar ve + - * (ekranda
   "[sayı 1 × sayı 2]"). */
const DONEM_FORMUL = /^\s*(\$\d+|\d+)(\s*[-+*]\s*(\$\d+|\d+))*\s*$/;
function donemYtIcerik(y) {
    const m = /^<\s*[Nn]\s*#(.*)>$/.exec(String(y || ""));
    return m ? m[1].trim() : null;
}
function donemFormulHatasi(ic, adet) {
    if (/^\d+$/.test(ic)) return +ic >= 1 && +ic <= adet ? "" : "kalıpta " + ic + ". sayı yok";
    if (!DONEM_FORMUL.test(ic)) return "hesap anlaşılmadı";
    const kotu = (ic.match(/\$(\d+)/g) || []).map(x => +x.slice(1)).filter(k => k < 1 || k > adet);
    return kotu.length ? "kalıpta " + kotu[0] + ". sayı yok" : "";
}
function donemFormulHesapla(ic, sirali) {
    if (/^\d+$/.test(ic)) { const k = +ic; return k >= 1 && k <= sirali.length ? sirali[k - 1] : null; }
    if (!DONEM_FORMUL.test(ic)) return null;
    const t = ic.match(/\$\d+|\d+|[-+*]/g);
    const deger = x => {
        if (x[0] !== "$") return +x;
        const k = +x.slice(1);
        if (k < 1 || k > sirali.length) throw new Error(x);
        return +sirali[k - 1];
    };
    try {
        const terim = [], isl = [];
        let cur = deger(t[0]);
        for (let i = 1; i < t.length; i += 2) {
            if (t[i] === "*") cur *= deger(t[i + 1]);
            else { terim.push(cur); isl.push(t[i]); cur = deger(t[i + 1]); }
        }
        terim.push(cur);
        let s = terim[0];
        isl.forEach((op, i) => { s = op === "+" ? s + terim[i + 1] : s - terim[i + 1]; });
        return String(s);
    } catch (e) { return null; }
}
function donemFormulGorunur(ic) {
    if (/^\d+$/.test(ic)) return "[sayı " + ic + "]";
    return "[" + ic.replace(/\s+/g, "").replace(/\$(\d+)/g, "sayı $1")
        .replace(/([-+*])/g, (_t, op) => " " + (op === "*" ? "×" : op) + " ") + "]";
}
/* SAYI EKLE: anlam kutusunun altında kalıbın sayıları için düğmeler
   ([sayı 1], [sayı 2]; tek sayılı kalıpta [sayı]). Basınca imlecin olduğu
   yere eklenir (kutu odakta değilse sona); kutunun kendi değişiklik
   işleyicisi çalışır. yenile(): kalıp değişince düğmeleri yeniden kurar.
   bitisik: önüne ve arkasına boşluk konmaz (yeni adda yazılış:
   BTWN_[sayı 1]D). */
function donemSayiDugmeleri(kalipFn, hedef, bitisik) {
    const kap = elYap("div", "dg-donem-sayi-ekle");
    const ciz = () => {
        kap.textContent = "";
        const n = donemYtAdedi(kalipFn());
        kap.hidden = !n || hedef.disabled;
        if (kap.hidden) return;
        kap.appendChild(elYap("span", "dg-donem-tur-not", "Sayı ekle:"));
        const etiketler = n > 1 ? Array.from({ length: n }, (_x, j) => "[sayı " + (j + 1) + "]") : [DONEM_SAYI];
        etiketler.forEach(t => {
            const b = elYap("button", "dg-donem-sayi-btn", t);
            b.type = "button";
            b.title = t + " imlecin olduğu yere eklenir.";
            /* Düğmeye basmak odağı kutudan almasın (imleç yerinde kalsın). */
            b.addEventListener("mousedown", e => e.preventDefault());
            b.onclick = () => {
                const odak = document.activeElement === hedef;
                const bas = odak ? hedef.selectionStart : hedef.value.length;
                const son = odak ? hedef.selectionEnd : bas;
                const once = hedef.value.slice(0, bas), sonra = hedef.value.slice(son);
                const ek = bitisik ? t : (once && !/\s$/.test(once) ? " " : "") + t
                    + (!/^[\s,.;:)]/.test(sonra) ? " " : "");
                hedef.focus();
                hedef.setRangeText(ek, bas, son, "end");
                hedef.dispatchEvent(new Event("input", { bubbles: true }));
            };
            kap.appendChild(b);
        });
    };
    ciz();
    kap.yenile = ciz;
    return kap;
}
function donemYtAdedi(kalip) {
    const k = String(kalip || "").replace(/\s+/g, "").toUpperCase();
    return /^<N>([A-Z]{1,3})$/.test(k) ? 1 : (k.match(/<NN>|<N\d>|<N>/g) || []).length;
}
function donemYerTutucuHatasi(kalip, anlam) {
    const k = String(kalip || "").replace(/\s+/g, "").toUpperCase();
    const izinli = new Set();
    if (k.indexOf("<NN>") !== -1) { izinli.add("NN"); izinli.add("<NN>"); }
    if (/<N\d?>/.test(k)) { izinli.add("N"); izinli.add("<N>"); }
    const kotu = [];
    const adet = donemYtAdedi(k);
    String(anlam || "").replace(DONEM_YT_ADAY, (_t, _on, y) => {
        const ic = donemYtIcerik(y);
        if (ic !== null) {
            if (!donemFormulHatasi(ic, adet)) return _t;
            y = donemFormulGorunur(ic);
        } else y = y.replace(/\s+/g, "");
        if (!izinli.has(y) && kotu.indexOf(y) === -1) kotu.push(y);
        return _t;
    });
    /* Tanınmayan sıra numaralı yazım (<NN1>, <N3>) da hata. */
    (String(anlam || "").match(/<\s*[Nn]{1,2}\s*\d+\s*>/g) || []).forEach(y => {
        y = y.replace(/\s+/g, "");
        if (kotu.indexOf(y) === -1) kotu.push(y);
    });
    if (kotu.length && adet > 1) for (let i = 1; i <= adet; i++) izinli.add("[sayı " + i + "]");
    if (!kotu.length) return "";
    if (!izinli.size) return "Anlamda yer tutucu var (" + kotu.join(", ")
        + ") ama kalıpta sayı yer tutucusu yok; yerine değeri yazın.";
    /* Kullanılabilenler ekrandaki gibi: tek sayılı kalıpta [sayı], çok
       sayılıda [sayı 1], [sayı 2] (içerideki N, NN yazılmaz). */
    const gor = adet > 1 ? Array.from({ length: adet }, (_x, j) => "[sayı " + (j + 1) + "]") : [DONEM_SAYI];
    return "Anlamda geçersiz yer tutucu: " + kotu.join(", ") + ". Bu kalıpta kullanılabilenler: "
        + gor.join(", ") + ".";
}

/* KALIP DESENİ (akis: donem.kalip_deseni ile aynı kural): <N> sayı, <NN>
   en az iki basamaklı sayı, <N2> tam iki basamaklı sayı (H<N2>: H00,
   H06; H000 uymaz). Anlamda <N2> için de "N" yazılır. Aile kalıbı
   ("<N>M") aynı harf ile sayının bütün yazılışlarına uyar: 3M, M3, 3_M,
   M_3. Geçersizse null. */
const DONEM_AILE = /^<N>([A-Z]{1,3})$/;
const regKacis = x => x.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
function donemKalipDeseni(kalip) {
    const k = String(kalip || "").replace(/\s+/g, "").toUpperCase();
    if (!k) return null;
    const a = DONEM_AILE.exec(k);
    const desen = a
        ? "(?:\\d+" + regKacis(a[1]) + "|" + regKacis(a[1]) + "\\d+|\\d+_" + regKacis(a[1])
          + "|" + regKacis(a[1]) + "_\\d+)"
        : regKacis(k).replace(/<NN>/g, "\\d{2,}").replace(/<N(\d)>/g, "\\d{$1}").replace(/<N>/g, "\\d+");
    try { return new RegExp("^" + desen + "$"); } catch (e) { return null; }
}
/* Değerin kalıbın yer tutucularına düşen sayıları: [[yer tutucu, sayı]]
   (kalıpta geçtikleri sırayla); uymuyorsa null. */
function donemSayiEslesmesi(kalip, deger) {
    const k = String(kalip || "").replace(/\s+/g, "").toUpperCase();
    const d = String(deger || "").replace(/\s+/g, "").toUpperCase();
    if (DONEM_AILE.test(k)) {
        const re = donemKalipDeseni(k);
        return re && re.test(d) ? [["<N>", d.match(/\d+/)[0]]] : null;
    }
    const turler = k.match(/<NN>|<N\d>|<N>/g);
    if (!turler) return null;
    const desen = regKacis(k).replace(/<NN>/g, "(\\d{2,})").replace(/<N(\d)>/g, "(\\d{$1})")
        .replace(/<N>/g, "(\\d+)");
    let m;
    try { m = new RegExp("^" + desen + "$").exec(d); } catch (e) { return null; }
    /* Tam basamaklı <N2> anlamda "N" ile yazılır. */
    return m ? turler.map((t, i) => [t === "<NN>" ? t : "<N>", m[i + 1]]) : null;
}

/* Kalıbın anlamındaki yer tutucuları değerin sayılarıyla doldurur
   (akis: donem.deger_anlami ile aynı kural): <N>D "<N> gün boyunca" +
   30D -> "30 gün boyunca". Değer kalıba uymuyorsa anlam aynen döner. */
function donemDegerAnlami(kalip, anlam, deger) {
    anlam = String(anlam || "");
    if (!anlam) return anlam;
    const es = donemSayiEslesmesi(kalip, deger);
    if (!es) return anlam;
    const sayilar = {};
    es.forEach(([t, sayi]) => {
        const y = t.replace(/[<>]/g, "");
        (sayilar[y] = sayilar[y] || []).push(sayi);
    });
    const sayac = {};
    return anlam.replace(DONEM_YT_ADAY, (t, on, y) => {
        const ic = donemYtIcerik(y);
        if (ic !== null) {
            const h = donemFormulHesapla(ic, es.map(x => x[1]));
            return h === null ? t : on + h;
        }
        const yy = y.replace(/[\s<>]/g, "").toUpperCase();
        const l = sayilar[yy];
        if (!l) return t;
        const i = sayac[yy] || 0;
        sayac[yy] = i + 1;
        return on + l[Math.min(i, l.length - 1)];
    });
}

/* Kalıp hücresi: aile satırında adlarda geçen yazılışlar ("<N>M · M<N> ·
   <N>_M"); anlam hepsine uygulanır. */
function donemKalipEtiketi(r) {
    const y = r.yazilislar || [];
    const el = elYap("span", "dg-donem-kalip",
                     donemSayiGoster(y.length ? y.join(" · ") : r.kalip));
    el.title = (y.length ? y.join(" · ") : r.kalip)
        + (y.length > 1 ? "\nAynı harf ile sayının yazılışları; anlam hepsine uygulanır." : "");
    return el;
}

/* [SAYI] GÖSTERİMİ: kalıpta ve anlamda sayı yer tutucusu (<N>, <NN>, N,
   NN) ekranda "[sayı]" yazar; tam basamaklı <N2> kalıpta "[2 haneli
   sayı]" yazar (H<N2> ile H<N3> ayrı görünsün), anlamda "[sayı]".
   Kalıpta birden çok sayı varsa en baştan numaralı yazar: kalıp
   "[sayı 1]D_[sayı 2]D", anlamda sırayla "[sayı 1]", "[sayı 2]" (anlamın
   k'inci düz yer tutucusu kalıbın k'inci sayısıdır). İçeride yer tutucu
   olarak saklanır; numaralar sırayla ve birer kez geçiyorsa düz yer
   tutucuya döner (hafıza ve Kolon Kartları aynı kalır). */
const DONEM_SAYI = "[sayı]";
const DONEM_SAYI_RE = /\[\s*say[ıi]\s*\]/gi;
/* Dil modelinin gerekçesindeki yer tutucular ekranda: <N1> "[sayı 1]",
   <N> "[sayı]". */
function donemNedenGoster(metin) {
    return String(metin || "").replace(/<\s*N{1,2}\s*#?\s*(\d)\s*>/g, "[sayı $1]").replace(/<\s*N{1,2}\s*>/g, "[sayı]");
}
/* YAZILIŞTA OLMAYAN YÖN: kalıbın anlamındaki yön sözcüğü (son, önce,
   sonra) yazılışta o yönü taşıyan bir harfle (L[sayı]D) karşılanmıyorsa
   eksik. yon: arka uçtan {kelimeler: {sözcük: tür}, harfler: {tür:
   [harf]}, oneri: {tür: harf}} (akis_faz01.yon_bilgisi). Döner:
   {eksik: [[sözcük, tür]], oneri: yeni yazılış ya da ""}. */
function donemYazilistaYok(kalip, anlam, yon) {
    const sonuc = { eksik: [], oneri: "" };
    /* Yalnız sayılı kalıp: sayısız kalıpta (TMSNCLST, MONTH) "son", "ilk"
       adın kendi harflerinde durur (LST, FRST). */
    if (!yon || !kalip || !anlam || String(kalip).indexOf("<N") < 0) return sonuc;
    const onek = new Set([...String(kalip).matchAll(/([A-Z]+)<N/g)].map(m => m[1]));
    const gorulen = new Set();
    (String(anlam).toLocaleLowerCase("tr-TR").match(/[a-zçğıöşü]+/g) || []).forEach(w => {
        const t = (yon.kelimeler || {})[w];
        if (!t || gorulen.has(w)) return;
        gorulen.add(w);
        if (!((yon.harfler || {})[t] || []).some(h => onek.has(h))) sonuc.eksik.push([w, t]);
    });
    if (sonuc.eksik.length) {
        const harf = (yon.oneri || {})[sonuc.eksik[0][1]] || "";
        const y = String(kalip).replace(/(?<![A-Z])(<N[^>]*>)(?=[A-Z])/g, harf + "$1");
        sonuc.oneri = y !== kalip ? y : "";
    }
    return sonuc;
}

function donemSayiGoster(metin) {
    /* " · " ile birleştirilmiş yazılışlar (aile) ayrı ayrı numaralanır. */
    return String(metin || "").split(" · ").map(k => {
        const adet = (k.match(/<NN?>|<N\d>/g) || []).length;
        let i = 0;
        return k.replace(/<N(\d)>|<NN?>/g, (t, h) => {
            i++;
            const no = adet > 1 ? " " + i : "";
            return h ? "[" + h + " haneli sayı" + no + "]" : "[sayı" + no + "]";
        });
    }).join(" · ");
}
function donemAnlamGoster(kalip, anlam) {
    const k = String(kalip || "").replace(/\s+/g, "").toUpperCase();
    if (!/<NN?>|<N\d>/.test(k)) return String(anlam || "");
    const adet = DONEM_AILE.test(k) ? 1 : (k.match(/<NN>|<N\d>|<N>/g) || []).length;
    let i = 0;
    return String(anlam || "").replace(DONEM_YT_ADAY, (t, on, y) => {
        const ic = donemYtIcerik(y);
        if (ic !== null) return on + donemFormulGorunur(ic);
        i++;
        return on + (adet > 1 ? "[sayı " + Math.min(i, adet) + "]" : DONEM_SAYI);
    });
}
/* Numaralı yer tutucular 1, 2, ..., n sırayla ve birer kez geçiyorsa
   (hesap yok) düz yer tutucuya döner: "[sayı 1] ile [sayı 2]" ile
   "[sayı] ile [sayı]" içeride aynıdır. */
function donemDuzYerTutucu(ic, turler) {
    const refs = ic.match(/<N#[^<>]*>/g) || [];
    if (!refs.length || refs.length !== turler.length) return ic;
    if (!refs.every((r, j) => r === "<N#" + (j + 1) + ">")) return ic;
    if ((ic.match(/<NN>|<N\d?>/g) || []).length) return ic;
    let j = 0;
    return ic.replace(/<N#\d+>/g, () => turler[j++]);
}
/* Ekrandaki "[sayı 1]", "[sayı 1 × sayı 2]", "[sayı 1 + 3]" iç hâle. */
const DONEM_EKRAN_FORMUL = /^\s*(say[ıi]\s*\d+|\d+)(\s*[-+*×xX]\s*(say[ıi]\s*\d+|\d+))*\s*$/i;
function donemFormulIc(metin) {
    return String(metin || "").replace(/\[([^\[\]]+)\]/g, (t, ic) => {
        const tek = /^\s*say[ıi]\s*(\d+)\s*$/i.exec(ic);
        if (tek) return "<N#" + tek[1] + ">";
        if (!/say[ıi]\s*\d+/i.test(ic) || !DONEM_EKRAN_FORMUL.test(ic)) return t;
        return "<N#" + ic.replace(/say[ıi]\s*(\d+)/gi, "$$$1").replace(/[×xX]/g, "*").replace(/\s+/g, "") + ">";
    });
}
/* Ekrandaki anlamın iç hâli: k'inci [sayı] kalıbın k'inci yer tutucusu
   olur (aile kalıbında <N>). */
function donemAnlamIc(kalip, metin) {
    const k = String(kalip || "").replace(/\s+/g, "").toUpperCase();
    const turler = DONEM_AILE.test(k) ? ["<N>"]
        : (k.match(/<NN>|<N\d>|<N>/g) || []).map(t => t === "<NN>" ? t : "<N>");
    if (!turler.length) return String(metin || "");
    let i = 0;
    return donemDuzYerTutucu(donemFormulIc(metin)
        .replace(DONEM_SAYI_RE, () => turler[Math.min(i++, turler.length - 1)]), turler);
}
/* YENİ ADDA YAZILIŞ: kalıbın Kolon Adları adımında yeni addaki yazılışı
   (ör. [sayı]D_[sayı]D için BTWN_[sayı]D_[sayı]D). Ekranda her yer
   tutucu "[sayı]"; içeride k'inci [sayı] kalıbın k'inci yer tutucusu. */
/* Yeni adda yazılışta da sıra numaralı ve hesaplı yer tutucu: [sayı 1],
   [sayı 1 × sayı 2] (içeride <N#1>, <N#$1*$2>). */
const DONEM_AD_YT = /<N#[^<>]{1,60}>|<NN>|<N\d?>/g;
function donemAdGoster(sablon) {
    const duz = (String(sablon || "").match(/<NN>|<N\d?>/g) || []).length;
    let i = 0;
    return String(sablon || "").replace(DONEM_AD_YT, t => {
        const ic = donemYtIcerik(t);
        if (ic !== null) return donemFormulGorunur(ic);
        i++;
        return duz > 1 ? "[sayı " + i + "]" : DONEM_SAYI;
    });
}
function donemAdIc(kalip, metin) {
    const k = String(kalip || "").replace(/\s+/g, "").toUpperCase();
    const turler = DONEM_AILE.test(k) ? ["<N>"] : (k.match(/<NN>|<N\d>|<N>/g) || []);
    let i = 0;
    return donemDuzYerTutucu(donemFormulIc(String(metin || ""))
        .replace(DONEM_SAYI_RE, t => turler.length ? turler[Math.min(i++, turler.length - 1)] : t)
        .replace(/\s+/g, "").toUpperCase(), turler);
}
/* Geçersizse hata metni; boş yazılış geçerli (kalıp aynen kalır). */
function donemAdHatasi(kalip, metin) {
    const k = String(kalip || "").replace(/\s+/g, "").toUpperCase();
    const ic = donemAdIc(k, metin);
    if (!ic) return "";
    const nKalip = DONEM_AILE.test(k) ? 1 : (k.match(/<NN>|<N\d>|<N>/g) || []).length;
    const duz = ic.replace(/<N#[^<>]{1,60}>/g, "<N>");
    if (!/^(?:[A-Z0-9_]|<NN>|<N\d?>)+$/.test(duz) || !/^[A-Z<]/.test(ic))
        return "Yalnız harf, rakam, alt çizgi ve [sayı] yazılabilir; harfle ya da [sayı] ile başlar.";
    const numarali = (ic.match(/<N#[^<>]{1,60}>/g) || []).map(donemYtIcerik);
    for (const n of numarali) {
        const h = donemFormulHatasi(n, nKalip);
        if (h) return "Yazılışta " + donemFormulGorunur(n) + ": " + h + ".";
    }
    const nAd = (ic.replace(/<N#[^<>]{1,60}>/g, "").match(/<NN>|<N\d?>/g) || []).length;
    if (numarali.length) return nAd > nKalip ? "Yazılışta " + nAd + " sıralı [sayı] var, kalıpta " + nKalip + "." : "";
    if (nAd !== nKalip)
        return "Yazılışta " + nAd + " [sayı] var, kalıpta " + nKalip + "; aynı sayıda olmalı.";
    return "";
}
/* Değer yazılışla: 3D_6D + BTWN_<N>D_<N>D -> BTWN_3D_6D. */
function donemAdDoldur(kalip, ic, deger) {
    const es = donemSayiEslesmesi(kalip, deger);
    if (!ic || !es) return String(deger || "");
    let i = 0;
    const sirali = es.map(x => x[1]);
    return ic.replace(DONEM_AD_YT, t => {
        const n = donemYtIcerik(t);
        if (n !== null) { const h = donemFormulHesapla(n, sirali); return h === null ? t : h; }
        return es[Math.min(i++, es.length - 1)][1];
    });
}

/* Zaman bilgisi türleri: ad ve kutunun altında görünen açıklama. */
const DONEM_TURLERI = [
    ["pencere", "Pencere", "Sayı bir aralık; veri o aralıktaki bütün zamanlardan toplanır (H00_06: 00:00 ile "
        + "06:00 arası; L30D: bugünden önceki 1. ile 30. gün arası)."],
    ["nokta", "Zaman Noktası", "Sayı belirli bir an ya da sıra (M3: yılın 3. ayı ya da 3 ay önceki ay)."],
    ["birim", "Zaman Birimi", "Sayısız zaman birimi (DAY: gün, MONTH: ay)."],
    ["olcu", "Zaman Ölçüsü", "Değerin kendisi bir süre (TMSNCFRST: ilk işlemden bu yana geçen süre)."]
];

function donemBolumuEkle(kart, da, ilkKilit, degisti) {
    let kilitli = ilkKilit;
    /* BAŞLIK: yönerge ve sütun açıklamaları başlıktaki "i"de. Altında tek
       satır özet, sonra üç sekme: Kalıplar (karar tablosu), Adaylar
       (adlarda bulunup tabloda olmayan bütün kalıplar, kalıp olma
       olasılığıyla) ve Tüm Parçalar (kolon adlarındaki bütün parçalar;
       buradan kalıplara alınır ya da kalıplardan çıkarılır). Sayısız parçalar Ad Parçaları'nda. */
    /* Adımın adı blok başlığında; kartta ayrıca başlık yok. */
    const ozetSatir = elYap("div", "dg-donem-ozet");
    const ozetEl = elYap("span", "", "");
    ozetSatir.appendChild(ozetEl);
    const bilgiMetni = [(da.yonerge || []).join(" "), da.sutunlar || ""].filter(Boolean).join("\n\n");
    if (bilgiMetni) ozetSatir.appendChild(bolmeBilgiSimgesi(tireSade(bilgiMetni), da.baslik || "Dönem Bilgisi"));
    kart.appendChild(ozetSatir);
    const sar = elYap("div", "dg-tablo-sar dg-kisa-sar dg-donem-sar");
    const tablo = elYap("table", "dg-tablo dg-donem-tablo");
    const th = document.createElement("thead"), hr = document.createElement("tr");
    ["Kalıp", "Adlarda Geçen", "Anlam", "Kayıt"]
        .forEach(h => hr.appendChild(elYap("th", "", h)));
    th.appendChild(hr); tablo.appendChild(th);
    const tb = document.createElement("tbody");
    tablo.appendChild(tb); sar.appendChild(tablo);
    const durumEl = elYap("div", "dg-bilgi-kutu", "");
    durumEl.hidden = true;
    kart.appendChild(durumEl);
    /* "Yalnız Hafızaya Ekle" sonucu (yeniden çizimde kaybolmaz). */
    const bilgiEl = elYap("div", "dg-donem-bilgi", "");
    bilgiEl.hidden = true;
    function bilgiYaz(m, hata) {
        metinYaz(bilgiEl, m || "");
        bilgiEl.classList.toggle("hata", !!hata);
        bilgiEl.hidden = !m;
    }
    const ilerEl = elYap("div", "islem-satiri dg-ilerleme");
    ilerEl.setAttribute("role", "status");
    const ilerMetin = elYap("span", "islem-sure", "");
    /* İPTAL: dil modelini durdurur; yorumlananlar kalır, yorumlanmayanlar
       Adaylar'a düşer ve anlamları elle yazılır. */
    const ilerIptal = elYap("button", "islem-iptal", "İptal");
    ilerIptal.type = "button";
    ilerIptal.title = "Dil modelini durdur; yorumlanan kalıplar kalır, kalanlar Adaylar'a düşer";
    ilerIptal.onclick = () => {
        ilerIptal.disabled = true;
        ilerIptal.textContent = "İptal ediliyor";
        fetch(getWebAppBackendUrl("donem_iptal"), {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify(ftKimlikGovdesi({}))
        })
        .then(r => r.json())
        .then(d => {
            const yeni = d && d.donem;
            if (yeni) {
                da.dm = yeni.dm; da.not = yeni.not || ""; da.satirlar = yeni.satirlar;
                ciz(yeni.satirlar); kilitDurumu(); if (degisti) degisti();
            }
            ilerIptal.disabled = false; ilerIptal.textContent = "İptal";
        })
        .catch(() => { ilerIptal.disabled = false; ilerIptal.textContent = "İptal"; });
    };
    ilerEl.append(ilerMetin, ilerIptal);
    kart.appendChild(ilerEl);
    /* SEKMELER */
    const sekmeBar = elYap("div", "dg-sekmeler");
    sekmeBar.setAttribute("role", "tablist");
    const panolar = {}, sekmeDugme = {};
    let aktifSekme = "kalip";
    [["kalip", "Kalıplar"], ["olasi", "Adaylar"], ["parca", "Tüm Parçalar"]].forEach(([ad, etiket]) => {
        const b = elYap("button", "dg-sekme", "");
        b.type = "button";
        b.setAttribute("role", "tab");
        b.append(elYap("span", "", etiket), elYap("span", "dg-sekme-sayi", ""));
        b.onclick = () => sekmeAc(ad);
        sekmeBar.appendChild(b);
        sekmeDugme[ad] = b;
        panolar[ad] = elYap("div", "dg-sekme-pano");
        panolar[ad].setAttribute("role", "tabpanel");
    });
    function sekmeAc(ad) {
        aktifSekme = ad;
        Object.keys(panolar).forEach(k => {
            panolar[k].hidden = k !== ad;
            sekmeDugme[k].classList.toggle("secili", k === ad);
            sekmeDugme[k].setAttribute("aria-selected", k === ad ? "true" : "false");
        });
    }
    kart.appendChild(sekmeBar);
    Object.values(panolar).forEach(pn => kart.appendChild(pn));
    panolar.kalip.append(sar);
    sekmeAc("kalip");
    let ilerBas = Date.now() - ((da.ilerleme && da.ilerleme.gecen) || 0) * 1000;
    /* DÜŞÜNEN ROBOT: dil modeli yorumlarken bloğun robotu düşünen hâlde. */
    const ilerDusun = dusunmeIzleyici(kart);
    const ilerSayac = setInterval(() => {
        const acik = da.dm === "calisiyor" && !kilitli && kart.isConnected;
        ilerEl.classList.toggle("gorunur", acik);
        ilerDusun(acik);
        if (acik) ilerMetin.textContent = "Dil modeli dönem kalıplarını yorumluyor · "
            + sureBicim(Math.max(0, Math.floor((Date.now() - ilerBas) / 1000)));
        if (da.dm !== "calisiyor" && kart.isConnected) clearInterval(ilerSayac);
    }, 1000);

    const parcalar = da.parcalar || [];
    /* Elle yazılan kalıbın adlardaki karşılıkları: <N> sayı, <NN> en az
       iki basamaklı sayı; yoksa parça aynen aranır. */
    function adlardaBul(kalip) {
        const re = donemKalipDeseni(kalip);
        if (!re) return [];
        return parcalar.filter(p => re.test(p.parca))
            .map(p => ({ deger: p.parca, kolon: p.kolon }));
    }
    /* Adlarda geçen değer çipleri; durumOf verilirse çip değerin durumunu
       gösterir: kendi anlamı (yeşil çerçeve), dönem değil (üstü çizili). */
    function degerCiz(td, deg, durumOf) {
        td.textContent = "";
        deg.forEach(d => {
            const durum = durumOf ? durumOf(d.deger) : "kalip";
            const c = elYap("span", "dg-kisa-cip dg-durum-" + durum, d.deger + " · " + ftBinlik(d.kolon));
            c.title = ftBinlik(d.kolon) + " kolonun adında"
                + (durum === "ozel" ? " · kendi anlamı var" : durum === "disi" ? " · dönem değil" : "");
            /* Değerin geçtiği örnek kolonlar ve sözlük tanımları ("i"). */
            if ((d.ornek || []).length) {
                c.appendChild(bolmeBilgiSimgesi(d.ornek.map(o => o.kolon + ": "
                    + (tireSade(o.tanim || "") || "(sözlükte tanım yok)")).join("\n\n"),
                    d.deger + " geçen kolonlar"));
                c.classList.add("dg-cip-bilgili");
            }
            td.appendChild(c);
        });
    }

    const satirlar = [];              // tabloda görünen satırlar
    const cikanlar = [];              // çıkarılanlar: {r, anah}
    const olasilar = [];              // emin olunamayanlar (tabloda değil): {r, anah}
    const duzen = {};                 // anahtar -> {anlam, kalip, cikar}: yoklamada kaybolmasın
    const anahtarOf = r => r.elle ? (r.id || ("elle:" + r.kalip)) : r.kalip;
    /* ANLAMI DİL MODELİ YAZAR: tablodaki bir satırın anlamı boşsa
       (tabloya alındı, Tüm Parçalar'dan eklendi, elle kalıp yazıldı)
       /donem_anlam ile dil modeline yazdırılır. Kullanıcı anlamı silip boş
       bıraktıysa URETIM_BEKLE_MS bekler; o sürede yazmaya başlarsa
       vazgeçilir. Gelen anlam yalnız kutu hâlâ boşsa yazılır. Aynı anda en
       çok URETIM_ES_ZAMANLI istek. URETIM: anahtar -> {durum: "sayac" |
       "calisiyor" | "bitti" | "hata", kalip, anlam, tur, kanit, not,
       kaynak, hata}. */
    const URETIM = {};
    /* KAYIT: satır tek tek kaydedilir (/donem_kaydet, hafızaya yazar).
       KAYIT[anahtar] kaydedilen hâlin imzası (anlam, tür, hariç ikililer,
       değer anlamları, dönem olmayan değerler); satır değişince imza tutmaz
       ve "Kaydet" yeniden açılır. Hafızadan gelen, dokunulmamış satır
       kaydedilmiş sayılır. */
    const KAYIT = {};
    /* ONCEKI[anahtar]: bu kartta ilk kaydetmeden önceki hafıza kaydı (Kaydı
       Geri Al bunu yazar). KAYIT_ACIK: kaydı geri alınan satırlar
       (hafızadan gelse de kendiliğinden kaydedilmiş sayılmaz). */
    const ONCEKI = {};
    const KAYIT_ACIK = new Set();
    /* KAYIT_ANLAM[anahtar]: satırın hafızadaki (kaydedilmiş) anlamı, iç
       hâliyle: hafızadan gelen satırda hafızadaki anlam, Kaydet'te
       kaydedilen, Kaydı Geri Al'da önceki kayıt. Koşul önerileri bununla
       hazırlanır (kutudaki kaydedilmemiş yazıyla değil). */
    const KAYIT_ANLAM = {};
    /* Yakın anlam uyarısı kullanıcı "farklılar" dediği ikililerde çıkmaz. */
    const YAKIN_TAMAM = new Set();
    /* Hafızadan gelen satıra kullanıcı dokunmadı mı? duzen'e çizimde
       kendiliğinden giren "ayrilan" (hafızadakinin kopyası) dokunma sayılmaz. */
    const DUZEN_DEGISIKLIK = ["anlam", "kalip", "zaman_tur", "haric", "deger_anlam", "cikar", "aileye_kat",
                              "kosullu"];
    const dokunulmadi = (r, anah) => {
        const dz = duzen[anah];
        if (!dz) return true;
        if (DUZEN_DEGISIKLIK.some(k => dz[k] !== undefined)) return false;
        return JSON.stringify(dz.ayrilan || {}) === JSON.stringify(r.ayrilan || {});
    };
    /* YAKIN ANLAM: iki anlamın kelimeleri (sayı ve yer tutucu, dolgu
       sözcükler hariç; yer tutucu kelime sayılır) ortak oranı
       ANLAM_YAKIN_ESIGI ve üstü. Kaydedilen bir satıra
       yakın anlamlı, kaydedilmemiş satırlar dil modeline yeniden yazdırılır. */
    const ANLAM_YAKIN_ESIGI = 0.6;
    const ANLAM_DOLGU = new Set(["ve", "ile", "bir", "için", "olan", "de", "da", "bu", "gibi", "göre"]);
    /* Kelime sayımı: sayı yer tutucusu "#" kelimesi sayılır (kaç tane
       geçtiği de: "saat [sayı]:00" ile "saat [sayı]:00 ile saat [sayı]:00
       arası" ayrı), rakamlar ve dolgu sözcükler sayılmaz. */
    function anlamKelimeleri(v) {
        const say = new Map();
        String(v || "").toLocaleLowerCase("tr")
            .replace(/\[\s*say[ıi]\s*\]|<\s*n{1,2}\d?\s*>/g, " # ").replace(/[0-9]/g, " ")
            .replace(/[^a-zçğıöşü#\s]/g, " ").split(/\s+/)
            .filter(w => w && (w === "#" || w.length > 1) && !ANLAM_DOLGU.has(w))
            .forEach(w => say.set(w, (say.get(w) || 0) + 1));
        return say;
    }
    /* YAKIN: ortak kelime oranı (çoklu küme; ortak / birleşim) eşik ve
       üstü. Biri öbürünün içinde diye yakın sayılmaz ("gün" ile "[sayı]
       gün boyunca" yakın değil). */
    function anlamYakin(a, b) {
        const A = anlamKelimeleri(a), B = anlamKelimeleri(b);
        if (!A.size || !B.size) return false;
        let ortak = 0, birlesim = 0;
        new Set([...A.keys(), ...B.keys()]).forEach(w => {
            ortak += Math.min(A.get(w) || 0, B.get(w) || 0);
            birlesim += Math.max(A.get(w) || 0, B.get(w) || 0);
        });
        return ortak / birlesim >= ANLAM_YAKIN_ESIGI;
    }
    /* Dil modeline bağlam: kaydedilmiş öbür satırların anlamları. */
    const kayitliAnlamlar = haric => satirlar
        .filter(x => x.anah !== haric && x.kayitliMi() && x.anlam().trim())
        .map(x => ({ kalip: String(x.kalipNe() || "").toUpperCase(), anlam: x.anlam().trim() }));
    const URETIM_BEKLE_MS = 8000;
    const URETIM_ES_ZAMANLI = 3;
    const uretimKuyruk = [];
    let uretimAktif = 0;
    function uretimSirala() {
        while (uretimAktif < URETIM_ES_ZAMANLI && uretimKuyruk.length) {
            uretimAktif++;
            uretimKuyruk.shift()().finally(() => { uretimAktif--; uretimSirala(); });
        }
    }
    const satirBul = anah => satirlar.find(x => x.anah === anah);
    const anlamBosMu = (anah, r) => {
        const dz = duzen[anah];
        const v = dz && dz.anlam !== undefined ? dz.anlam : (r ? r.anlam : "");
        return !String(v || "").trim();
    };
    function uretimBaslat(anah, kalip, zorla, onceki) {
        const u = URETIM[anah];
        if (u && u.zamanlayici) clearTimeout(u.zamanlayici);
        URETIM[anah] = { durum: "calisiyor", kalip, zorla: !!zorla, onceki: onceki || "" };
        const kayitli = kayitliAnlamlar(anah);
        const x0 = satirBul(anah); if (x0) x0.boya();
        uretimKuyruk.push(() => fetch(getWebAppBackendUrl("donem_anlam"), {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ oturum_id: OTURUM_ID, kalip, kayitli })
        })
        .then(res => res.json())
        .then(d => {
            if (!URETIM[anah] || URETIM[anah].kalip !== kalip || URETIM[anah].durum !== "calisiyor") return;
            if (d && d.tamam && d.anlam) {
                const zorla0 = URETIM[anah].zorla, onceki0 = URETIM[anah].onceki;
                URETIM[anah] = Object.assign({ durum: "bitti", kalip, onceki: onceki0 }, d);
                const x = satirBul(anah);
                if (x) x.uretimYaz(d, zorla0);
                else if (anlamBosMu(anah, null)) {
                    duzen[anah] = Object.assign(duzen[anah] || {}, { anlam: d.anlam });
                    if (d.tur && duzen[anah].zaman_tur === undefined) duzen[anah].zaman_tur = d.tur;
                }
            } else {
                URETIM[anah] = { durum: "hata", kalip,
                                 hata: tireSade((d && (d.hata || d.mesaj)) || "Dil modeli anlam yazmadı.") };
                const x = satirBul(anah); if (x) x.boya();
            }
        })
        .catch(() => {
            if (!URETIM[anah] || URETIM[anah].kalip !== kalip) return;
            URETIM[anah] = { durum: "hata", kalip, hata: "Bağlantı kurulamadı." };
            const x = satirBul(anah); if (x) x.boya();
        }));
        uretimSirala();
    }
    /* Kullanıcı anlamı sildi: bir süre bekle, hâlâ boşsa yazdır. */
    function uretimSayac(anah, kalip) {
        const u = URETIM[anah];
        if (u && u.zamanlayici) clearTimeout(u.zamanlayici);
        const z = setTimeout(() => {
            const x = satirBul(anah);
            const bos = x ? !x.anlam().trim() : anlamBosMu(anah, null);
            if (bos && URETIM[anah] && URETIM[anah].durum === "sayac" && !kilitli && da.dm !== "calisiyor")
                uretimBaslat(anah, kalip);
        }, URETIM_BEKLE_MS);
        URETIM[anah] = { durum: "sayac", kalip, zamanlayici: z };
    }
    function uretimVazgec(anah) {
        const u = URETIM[anah];
        if (u && u.durum === "sayac") { clearTimeout(u.zamanlayici); delete URETIM[anah]; }
    }
    /* DÖNEM OLMAYAN DEĞERLER: {değer: {anlam, cikar}} (gruptan ayrılan).
       Düzenleme duzen'de tutulur (yoklamada kaybolmaz); ilk okumada
       satırdan kopyalanır. */
    function grupAyrilan(r, anah) {
        const dz = duzen[anah] = duzen[anah] || {};
        if (!dz.ayrilan) dz.ayrilan = JSON.parse(JSON.stringify(r.ayrilan || {}));
        return dz.ayrilan;
    }
    /* Onaya giden dönem olmayan değerler. */
    function ayrilanCikti(r, anah) {
        const ayr = grupAyrilan(r, anah), cikti = {};
        Object.keys(ayr).forEach(dg => {
            if (ayr[dg] && ayr[dg].cikar) cikti[dg] = { anlam: "", cikar: true };
        });
        return cikti;
    }
    const cikarildi = (r, anah) => (duzen[anah] && duzen[anah].cikar !== undefined)
        ? duzen[anah].cikar : !!r.cikar;
    /* AİLEYE KATILAN: ailesinden ayrılmış yazılış satırı ("M<N>") ailesine
       geri katıldı; satır tablodan kalkar, değerleri aile satırına geçer. */
    const katildi = (r, anah) => (duzen[anah] && duzen[anah].aileye_kat !== undefined)
        ? duzen[anah].aileye_kat : !!r.aileye_kat;
    const katilanlar = [];            // {r, anah}
    const aileTablodaMi = aile => (da.satirlar || []).some(s => s.kalip === aile && !s.aile);
    function aileyeKat(anah, kat) {
        if (kilitli || da.dm === "calisiyor") return;
        duzen[anah] = Object.assign(duzen[anah] || {}, { aileye_kat: kat });
        ciz(da.satirlar);
        if (degisti) degisti();
    }

    function satirCiz(r) {
        /* Kalıbı bir grubun kalıbı olan elle satır (sonradan yoklamayla ya
           da kayıttan gelse de) grup satırıdır: kalıp etiket, değerler
           adlardan. */
        if (r.elle && !r.grup && parcalar.some(p => p.grup && p.grup === String(r.kalip || "").toUpperCase()))
            r = Object.assign({}, r, { grup: true, degerler: (r.degerler || []).length ? r.degerler
                                                                : adlardaBul(r.kalip) });
        const calisiyor = da.dm === "calisiyor";
        const tr = elYap("tr", "dg-satir" + (r.elle ? " dg-donem-elle" : ""));
        const anah = anahtarOf(r);
        tr.dataset.anahtar = anah;
        const dz = duzen[anah] || null;
        /* KALIP + örnekler "i"de; elle eklenen satırda kalıp yazılır. */
        const tdK = elYap("td", "dg-kolon");
        let kg = null;
        /* Gruptan eklenen satır (r.grup) elle olsa da kalıbı yazılmaz:
           etiket olarak durur, değerleri gruptan gelir. */
        if (r.elle && !r.grup) {
            kg = document.createElement("input");
            kg.type = "text"; kg.className = "dg-giris dg-donem-kalip-giris";
            kg.value = dz && dz.kalip !== undefined ? dz.kalip : (r.kalip || "");
            kg.placeholder = "Kalıp (ör. PREVD)";
            kg.disabled = kilitli || calisiyor;
            kg.setAttribute("aria-label", "Kalıp");
            tdK.appendChild(kg);
        } else {
            tdK.appendChild(donemKalipEtiketi(r));
            /* Ailesinden ayrılan yazılış: hangi aileden ayrıldığı ve
               ailesine geri katma. */
            if (r.aile) {
                const not = elYap("div", "dg-donem-aile-not",
                                   donemSayiGoster(r.aile) + " ailesinden ayrı anlamlı yazılış");
                if (aileTablodaMi(r.aile)) {
                    const kat = elYap("button", "dg-baglanti dg-donem-aile-btn", "Aileye Kat");
                    kat.type = "button";
                    kat.disabled = kilitli || calisiyor;
                    kat.title = "Bu yazılış da " + r.aile + " anlamını alır; değerleri aile satırına geçer.";
                    kat.onclick = () => aileyeKat(anah, true);
                    not.append(" · ", kat);
                }
                tdK.appendChild(not);
            }
            /* Aileye katılan yazılışlar: geri alınabilir. */
            (r.katilan || []).forEach(c => {
                const not = elYap("div", "dg-donem-aile-not", donemSayiGoster(c.r.kalip) + " aileye katıldı · ");
                const geri = elYap("button", "dg-baglanti dg-donem-aile-btn", "Geri Al");
                geri.type = "button";
                geri.disabled = kilitli || calisiyor;
                geri.title = c.r.kalip + " yeniden ayrı satırda, kendi anlamıyla durur.";
                geri.onclick = () => aileyeKat(c.anah, false);
                not.appendChild(geri);
                tdK.appendChild(not);
            });
        }
        /* ZAMAN BİLGİSİ TÜRÜ: dil modeli önerir, kullanıcı değiştirir;
           seçili türün ne demek olduğu kutunun altında yazar. */
        const turSec = document.createElement("select");
        turSec.className = "dg-donem-tur";
        turSec.setAttribute("aria-label", (r.kalip || "Kalıp") + " türü");
        DONEM_TURLERI.forEach(([d, a]) => {
            const o = document.createElement("option");
            o.value = d; o.textContent = a;
            turSec.appendChild(o);
        });
        turSec.value = (dz && dz.zaman_tur) || r.zaman_tur || "pencere";
        turSec.disabled = kilitli || calisiyor;
        const turNot = elYap("div", "dg-donem-tur-not", "");
        const turNotYaz = () => {
            turNot.textContent = (DONEM_TURLERI.find(t => t[0] === turSec.value) || [, , ""])[2];
        };
        turNotYaz();
        turSec.onchange = () => {
            duzen[anah] = Object.assign(duzen[anah] || {}, { zaman_tur: turSec.value });
            turNotYaz(); boya(); sekmeSayilari(); if (degisti) degisti();
        };
        const orn = r.ornekler || [];
        if (orn.length) tdK.appendChild(bolmeBilgiSimgesi(
            tireSade("Dil modelinin baktığı örnek tanımlar:\n"
                     + orn.map(o => o.kolon + ": " + o.tanim).join("\n")), r.kalip));
        /* Bekleyen satırda tür henüz belli değil: kutu yerine kısa not. */
        if (r.bekliyor && calisiyor) tdK.appendChild(elYap("div", "dg-donem-tur-not",
                                                            "Tür dil modelinin yorumundan sonra gelir."));
        /* Birimli kalıpta (ör. [sayı]D) aralık mı tek gün mü olduğu kolona
           göre değişir: kalıbın tek zaman türü yok, her kolonun anlam
           türünden gelir (Anlam türleri). */
        else if (r.birimli) tdK.appendChild(elYap("div", "dg-donem-tur-not",
            "Zaman türü kolona göre: aralık ya da tek gün oluşu her kolonun anlam türünden gelir."));
        else tdK.append(turSec, turNot);
        /* Yeni adda yazılış burada değil, 01.2.4.4 Kolon Adları'nda
           (adlar orada kurulur). */
        tr.appendChild(tdK);
        /* ADLARDA GEÇEN: bütün değerler ve kolon sayıları. Altında
           BİRLİKTE GEÇTİĞİ ikililer: çipe tıklamak o ikiliyi hariç tutar
           (kalıp o ikilinin içinde dönem sayılmaz) ya da geri dahil eder. */
        const tdD = elYap("td", "dg-kisa-hucre");
        const haric = new Set(dz && dz.haric ? dz.haric : (r.haric || []));
        const birlikteBilgi = () => {
            if (!kg) return { liste: r.birlikte || [], tek: r.tek };
            const k = kg.value.trim().toUpperCase();
            const pp = parcalar.find(p => p.parca === k);
            return { liste: (pp && pp.birlikte) || [], tek: pp ? pp.tek : 0 };
        };
        function birlikteCiz() {
            const eski = tdD.querySelector(".dg-donem-birlikte");
            if (eski) eski.remove();
            const bb = birlikteBilgi();
            const gecerli = new Set(bb.liste.map(x => x[0]));
            Array.from(haric).forEach(ik => { if (!gecerli.has(ik)) haric.delete(ik); });
            if (!bb.liste.length) return;
            const kap = elYap("div", "dg-donem-birlikte");
            const bas = elYap("span", "dg-donem-birlikte-bas", "Birlikte geçtiği");
            bas.appendChild(bolmeBilgiSimgesi("Bu kısaltmanın kolon adlarında hep yan yana geçtiği "
                + "ikililer. Bir ikili birlikte başka bir anlam taşıyorsa (ör. birim ya da oran) "
                + "üzerine tıklayıp hariç tutun: kalıp o ikilinin içinde dönem sayılmaz, tek "
                + "başına geçtiği yerlerde dönem kalır. Tekrar tıklayınca dahil olur.", "Birlikte geçtiği"));
            kap.appendChild(bas);
            const k = kilitli || da.dm === "calisiyor";
            bb.liste.forEach(([ik, n]) => {
                const h = haric.has(ik);
                const b = elYap("button", "dg-kisa-cip dg-birlikte-cip" + (h ? " haric" : ""),
                                ik + " · " + ftBinlik(n) + (h ? " · Hariç" : ""));
                b.type = "button";
                b.disabled = k;
                b.title = h ? ik + " içinde dönem sayılmaz. Tıklayın: dahil et."
                            : ik + " içinde de dönem sayılır. Tıklayın: hariç tut.";
                b.onclick = () => {
                    if (kilitli || da.dm === "calisiyor") return;
                    if (haric.has(ik)) haric.delete(ik); else haric.add(ik);
                    kaydet();
                };
                kap.appendChild(b);
            });
            kap.appendChild(elYap("span", "dg-donem-tek",
                                  "tek başına " + ftBinlik(Number(bb.tek || 0)) + " kolon"));
            tdD.appendChild(kap);
        }
        function elleSay() {
            if (!kg) return;
            const k = kg.value.trim();
            const bulunan = adlardaBul(k);
            degerCiz(tdD, bulunan, degerDurumu);
            if (k && !bulunan.length) {
                /* ADLARDA GEÇMEYEN KALIP: bu çalışmada bir kolonu etkilemez;
                   onaylayınca anlamıyla hafızaya yazılır, adında geçen bir
                   veri seti geldiğinde tabloya hazır gelir. */
                const c = elYap("span", "dg-kisa-cip dg-adda-yok", "Adlarda yok · hafızaya yazılır");
                c.title = "Bu çalışmadaki kolon adlarında geçmiyor. Onaylayınca anlamıyla hafızaya "
                    + "yazılır; adında bu kalıp geçen bir veri setinde tabloya hazır gelir.";
                tdD.appendChild(c);
                /* YALNIZ HAFIZAYA EKLE: onayı beklemeden şimdi hafızaya yazar
                   (bu çalışmayı etkilemez); yazılınca satır tablodan kalkar. */
                const hb = elYap("button", "dg-toplu-btn dg-donem-hafiza", "Yalnız Hafızaya Ekle");
                hb.type = "button";
                hb.disabled = kilitli || da.dm === "calisiyor";
                hb.title = "Bu çalışmayı etkilemez; kalıp anlamıyla hafızaya yazılır, adında bu "
                    + "kalıp geçen bir veri setinde tabloya hazır gelir.";
                hb.onclick = () => {
                    const anlamV = anlamAl().trim();
                    if (!anlamV) { bilgiYaz("Önce anlamı yazın.", true); g.focus(); return; }
                    const yt = donemYerTutucuHatasi(k, anlamV);
                    if (yt) { bilgiYaz(k.toUpperCase() + ": " + yt, true); return; }
                    hb.disabled = true;
                    fetch(getWebAppBackendUrl("donem_hafiza_ekle"), {
                        method: "POST", headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ oturum_id: OTURUM_ID, kalip: k, anlam: anlamV })
                    })
                    .then(r => r.json())
                    .then(d => {
                        const ok = !!(d && d.tamam);
                        bilgiYaz((d && (d.mesaj || d.hata)) || "Hafızaya yazılamadı.", !ok);
                        if (ok) cikBtn.onclick(); else hb.disabled = false;
                    })
                    .catch(() => { bilgiYaz("Hafızaya yazılamadı (bağlantı).", true); hb.disabled = false; });
                };
                tdD.appendChild(hb);
            }
        }
        /* DEĞERLERİN DURUMU: "kalip" kalıbın anlamına uyar, "ozel" kendi
           anlamı (dgAnlam), "disi" dönem değil (ayrilanlar, cikar). */
        const ayrilanlar = grupAyrilan(r, anah);
        const dgAnlam = Object.assign({}, (dz && dz.deger_anlam) || r.deger_anlam || {});
        Object.keys(ayrilanlar).forEach(dg => {
            if (ayrilanlar[dg] && !ayrilanlar[dg].cikar) {
                if (ayrilanlar[dg].anlam) dgAnlam[dg] = ayrilanlar[dg].anlam;
                delete ayrilanlar[dg];
            }
        });
        const degerDurumu = dg => (ayrilanlar[dg] && ayrilanlar[dg].cikar) ? "disi"
            : dgAnlam[dg] !== undefined ? "ozel" : "kalip";
        if (kg) elleSay(); else degerCiz(tdD, r.degerler || [], degerDurumu);
        birlikteCiz();
        tr.appendChild(tdD);
        /* ANLAM: model önerisi; kullanıcı düzeltir. Soru / not / kontrol altında. */
        const tdA = elYap("td", "dg-aciklama-hucre");
        /* DURUM: renk yerine anlamın üstünde tek satır etiket (Dil modeli
           · kanıt, Hafızadan, Düzenlendi, Kontrol edin, Yorumlanıyor). */
        const durumCip = elYap("div", "dg-donem-durum", "");
        tdA.appendChild(durumCip);
        /* Dil modelinin yazdığı anlamın notu ya da "Yeniden dene". */
        const uretimNot = elYap("div", "dg-donem-not", "");
        const g = document.createElement("textarea");
        g.className = "dg-giris dg-donem-anlam";
        g.rows = 2;
        const kalipNe = () => kg ? kg.value.trim() : r.kalip;
        /* İç hâl (yer tutuculu) ile ekran hâli ([sayı]) arasında çeviri. */
        const anlamAl = () => donemAnlamIc(kalipNe(), g.value);
        const anlamYaz = v => { g.value = donemAnlamGoster(kalipNe(), v); };
        anlamYaz(dz && dz.anlam !== undefined ? dz.anlam : tireSade(r.anlam || ""));
        g.placeholder = r.bekliyor ? "" : "Anlamı yazın";
        g.disabled = kilitli || calisiyor;
        g.setAttribute("aria-label", (r.kalip || "Kalıp") + " anlamı");
        tdA.appendChild(g);
        if (r.soru) tdA.appendChild(elYap("div", "dg-donem-soru", "Soru: " + tireSade(r.soru)));
        if (r.celiski) tdA.appendChild(elYap("div", "dg-donem-not",
                                              "Ad ile tanımlar çelişiyor: " + tireSade(r.celiski)));
        if (r.not) tdA.appendChild(elYap("div", "dg-donem-not", "Not: " + tireSade(r.not)));
        if (r.uyari) {
            const u = elYap("div", "dg-donem-uyari", "Dikkat: " + tireSade(r.uyari));
            if (r.uyari_ayrinti) u.appendChild(bolmeBilgiSimgesi(tireSade(r.uyari_ayrinti), "Dikkat"));
            tdA.appendChild(u);
        }
        /* YAZILIŞTA YOK: anlamdaki yön (son, önce, sonra) kalıbın
           yazılışında yok. Anlam bu veri setinde doğru olabilir; adın onu
           taşıması 01.2.4.4'teki yeni yazılışla olur. Anlam yazıldıkça
           yenilenir. */
        const yonEl = elYap("div", "dg-donem-uyari dg-donem-yon", "");
        tdA.appendChild(yonEl);
        const yonCiz = () => {
            const y = donemYazilistaYok(kalipNe(), anlamAl(), da.yon);
            yonEl.hidden = !y.eksik.length;
            if (!y.eksik.length) { yonEl.textContent = ""; return; }
            const sozler = y.eksik.map(e => "«" + e[0] + "»").join(", ");
            /* BİRİMLİ KALIP: yön kalıba değil kolona aittir; onayda anlamdan
               çıkarılır, her kolonda açıklamasından belirlenir. */
            if (r.birimli) {
                yonEl.textContent = "Yön kalıba yazılmaz: " + sozler + " bu kalıbın anlamından onaylayınca çıkarılır. "
                    + "Kalıbın anlamı birimdir; yönü her kolonda açıklamasından belirlenir (Anlam türleri).";
                return;
            }
            yonEl.textContent = "Yazılışta yok: " + sozler + ". " + donemSayiGoster(kalipNe())
                + " yazılışı bunu söylemiyor; adın bu bilgiyi taşıması için 01.2.4.4 Kolon Adları'nda"
                + " yeni adda yazılışı belirleyin" + (y.oneri ? " (öneri: " + donemSayiGoster(y.oneri) + ")." : ".");
        };
        g.addEventListener("input", yonCiz);
        yonCiz();
        /* HAFIZA NOTU: yazılışın kendi (yönsüz) anlamı ve öbür veri
           setlerinde kullanıldığı anlam. */
        if (r.hafiza_genel || (r.hafiza_vs && Object.keys(r.hafiza_vs).length)) {
            const vs = Object.entries(r.hafiza_vs || {})
                .map(([v, an]) => v + " veri setinde «" + donemAnlamGoster(r.kalip, an) + "»");
            tdA.appendChild(elYap("div", "dg-donem-not",
                "Hafıza: " + (r.hafiza_genel ? "yazılışın kendi anlamı «"
                    + donemAnlamGoster(r.kalip, r.hafiza_genel) + "» (yön belirtmez)" : "")
                + (vs.length ? (r.hafiza_genel ? "; " : "") + vs.join(", ") + " anlamında kullanıldı" : "") + "."));
        }
        const kontrolEl = elYap("div", "dg-donem-kontrol");
        kontrolEl.hidden = true;
        tdA.appendChild(kontrolEl);
        tdA.appendChild(uretimNot);
        const yakinEl = elYap("div", "dg-donem-uyari dg-donem-yakin", "");
        yakinEl.hidden = true;
        tdA.appendChild(yakinEl);
        /* ANLAM TÜRLERİ (birimli kalıp, ör. [sayı]D): kalıbın anlamı birim
           ("[sayı] gün"); her kolonda yönü ve kapsamı ayrı. Her tür bir yön
           (geçmiş, gelecek, iki yönlü, yönsüz) ve bir biçimle (pencere:
           aralığın tamamı, nokta: yalnız uçtaki gün) tanımlı; Kapsam
           sütunu kapsadığı günleri somut yazar. Sabit türler: son, önce,
           sonraki, sonra, çevre, süre; sizin eklediğiniz türler de yön ve
           biçim taşır. Sayılar bütün tanımlardan (yön yazmayan tanım
           belirsiz sayılır). */
        let ozelTurler = (dz && Array.isArray(dz.ozel_turler)) ? dz.ozel_turler.slice()
            : (r.anlam_turleri || []).filter(t => t.ozel)
                .map(t => ({ tur: t.tur, ad: t.ad, anlam: t.anlam, yon: t.yon || "", bicim: t.bicim || "" }));
        if (r.birimli) {
            if (r.birim_notu) tdA.appendChild(elYap("div", "dg-donem-not", tireSade(r.birim_notu)));
            const dt = elYap("div", "dg-donem-turler");
            tdA.appendChild(dt);
            const turAnlami = (t, b) => t === "son" ? ("son " + b).trim() : t === "once" ? (b + " önce").trim()
                : t === "sonraki" ? ("sonraki " + b).trim() : t === "sonra" ? (b + " sonra").trim()
                : t === "cevre" ? (b + " öncesi ve sonrası").trim() : t === "takvim" ? takvimAnlami(b)
                : t === "sure" ? b : "";
            const YON_SOZ = new Set(["son", "önce", "önceki", "öncesi", "öncesine", "önceye", "geçmiş", "geçen",
                "sonra", "sonraki", "sonrası", "sonrasına", "gelecek", "önümüzdeki", "izleyen", "ileriki",
                "kadar", "boyunca", "süresince", "süreyle"]);
            /* TAKVİM: sayı takvimdeki yeri gösterir (sunucuda
               donem_tur.takvim_anlami): ay -> yılın [sayı]. ayı, gün ->
               ayın [sayı]. günü ... */
            const TAKVIM = { "gün": ["ayın", "günü"], "hafta": ["yılın", "haftası"], "ay": ["yılın", "ayı"],
                             "çeyrek": ["yılın", "çeyreği"], "saat": ["günün", "saati"], "dakika": ["saatin", "dakikası"] };
            const TAKVIM_YALIN = Object.fromEntries(Object.entries(TAKVIM).map(([b_, [, e]]) => [e, b_]).concat([["yılı", "yıl"]]));
            const birimSoz = b => (b.replace(/<[^<>]*>/g, " ").toLocaleLowerCase("tr").match(/[a-zçğıöşüâîû]+/g) || [])
                .find(w => !YON_SOZ.has(w) && w !== "ve") || "";
            const takvimAnlami = (b, n) => {
                const bs = birimSoz(b); n = n || "<N>";
                if (!bs) return "";
                if (bs === "yıl") return n + " yılı";
                return TAKVIM[bs] ? TAKVIM[bs][0] + " " + n + ". " + TAKVIM[bs][1] : n + ". " + bs;
            };
            const birimAl = () => {
                const a_ = anlamAl();
                const m = a_.match(/(<N\d*>|<NN>)\s*(\.\s*)?([^\s.,;<>]+)/);
                if (m) {
                    const e = m[3].toLocaleLowerCase("tr");
                    if (TAKVIM_YALIN[e] && (m[2] || e === "yılı")) return m[1] + " " + TAKVIM_YALIN[e];
                }
                return birimYonsuz(a_);
            };
            const birimYonsuz = a_ => a_.replace(/±\s*/g, "").split(/\s+/)
                .filter(w => w && !YON_SOZ.has(w.toLocaleLowerCase("tr").replace(/[.,;]/g, ""))).join(" ")
                .replace(/^ve\s+|\s+ve$/g, "").trim();
            /* Kapsam: sunucudaki donem_tur.kapsam_metni ile aynı metin
               (bugün = referans tarihi, pencereye dahil değil). */
            const kapsamYaz = (yon, bicim, b) => {
                const bs = birimSoz(b);
                if (!bs || !yon) return "";
                const n = "<N>";
                if (yon === "takvim") return bicim === "pencere" && TAKVIM[bs]
                    ? "bugünden bağımsız; " + TAKVIM[bs][0] + " 1. ile " + n + ". " + TAKVIM[bs][1] + " arası"
                    : "bugünden bağımsız; yalnız " + takvimAnlami(b);
                if (yon === "yonsuz" || bicim === "uzunluk")
                    return "tarih aralığı değil, bir sürenin uzunluğu (" + n + " " + bs + ")";
                if (yon === "gecmis") return bicim === "pencere" ? "bugünden önceki 1. ile " + n + ". " + bs + " arası"
                    : "yalnız " + n + " " + bs + " öncesi";
                if (yon === "gelecek") return bicim === "pencere" ? "bugünden sonraki 1. ile " + n + ". " + bs + " arası"
                    : "yalnız " + n + " " + bs + " sonrası";
                if (yon === "iki") return bicim === "pencere" ? n + " " + bs + " öncesinden " + n + " " + bs + " sonrasına"
                    : "yalnız " + n + " " + bs + " öncesi ve " + n + " " + bs + " sonrası";
                return "";
            };
            const YONLER = [["gecmis", "Geçmiş"], ["gelecek", "Gelecek"], ["iki", "İki yönlü"],
                            ["takvim", "Takvim (bugünden bağımsız)"], ["yonsuz", "Yönsüz"]];
            const BICIMLER = [["pencere", "Pencere: aralığın tamamı"], ["nokta", "Nokta: yalnız uçtaki gün"]];
            let ekleAcik = false, ekleHata = "";
            /* Formda yazılanlar yeniden çizimde (hata gösterilince) kalır. */
            let ekleDeger = { ad: "", anlam: "", yon: "", bicim: "" };
            const dtCiz = () => {
                dt.textContent = "";
                const bas = elYap("div", "dg-donem-turler-bas", "Anlam türleri");
                bas.appendChild(bolmeBilgiSimgesi("Bu kalıp sayı ve zaman biriminden oluşur; tek başına "
                    + "belirsizdir: geçmişe mi geleceğe mi bakar, aralığın tamamını mı yoksa yalnız uçtaki günü mü "
                    + "kapsar, yoksa takvimdeki bir yeri mi gösterir (yılın 3. ayı)? Her tür bunu yön ve biçimle "
                    + "kesinleştirir; Kapsam sütunu kapsadığı günleri yazar "
                    + "(bugün referans tarihidir, aralığa dahil değildir).\n\n"
                    + "Kalıbın anlamı birim olarak yazılır; her kolonun türü açıklamasından belirlenir "
                    + "(01.2.4.3 Kolon Kartları). Açıklamasında yön ya da kapsam açık olmayan kolon orada size "
                    + "sorulur. 01.2.4.4 Kolon Adları'nda her türün ayrı yeni ad yazılışı olur (ör. son için "
                    + "L[sayı]D, sonraki için N[sayı]D). Sayılar bütün kolonların tanımından, kesin sayımla.",
                    "Anlam türleri"));
                dt.appendChild(bas);
                const b = birimAl();
                const say = r.tur_sayim || {};
                const t = elYap("table", "");
                const th = document.createElement("thead"), thr = document.createElement("tr");
                ["Tür", "Anlam", "Kapsam", "Kolon", ""].forEach(x => thr.appendChild(elYap("th", "", x)));
                th.appendChild(thr); t.appendChild(th);
                const tb = document.createElement("tbody");
                const satirlar_ = (r.anlam_turleri || []).filter(x => !x.ozel)
                    .map(x => ({ tur: x.tur, ad: x.ad, anlam: turAnlami(x.tur, b), yon: x.yon, bicim: x.bicim, ozel: false }))
                    .concat(ozelTurler.map(x => Object.assign({}, x, { ozel: true })));
                satirlar_.forEach(x => {
                    const tr_ = document.createElement("tr");
                    tr_.appendChild(elYap("td", "dg-dt-ad", x.ad));
                    tr_.appendChild(elYap("td", "", donemAnlamGoster(kalipNe(), x.anlam)));
                    const kap = kapsamYaz(x.yon, x.bicim, b);
                    const tdK_ = elYap("td", "dg-dt-kapsam", kap ? donemAnlamGoster(kalipNe(), kap) : "");
                    /* Önceki sürümde eklenen türde yön ya da biçim yok: burada
                       seçilir (seçilmeden onay sunucuda hata verir). */
                    if (!kap && x.ozel && !kilitli && !calisiyor) {
                        const sY = document.createElement("select"), sB = document.createElement("select");
                        [[sY, [["", "Yön seçin"]].concat(YONLER), x.yon], [sB, [["", "Biçim seçin"]].concat(BICIMLER), x.bicim]]
                            .forEach(([sc, l, v]) => {
                                sc.className = "dg-giris";
                                l.forEach(([d, a]) => { const o = document.createElement("option"); o.value = d; o.textContent = a; sc.appendChild(o); });
                                sc.value = v || "";
                            });
                        sY.setAttribute("aria-label", x.ad + " yönü"); sB.setAttribute("aria-label", x.ad + " biçimi");
                        sB.disabled = sY.value === "yonsuz";
                        const yaz = () => {
                            const yon = sY.value, bicim = yon === "yonsuz" ? "uzunluk" : sB.value;
                            ozelTurler = ozelTurler.map(y => y.tur === x.tur ? Object.assign({}, y, { yon: yon, bicim: bicim }) : y);
                            duzen[anah] = Object.assign(duzen[anah] || {}, { ozel_turler: ozelTurler.slice() });
                            dtCiz(); boya(); if (degisti) degisti();
                        };
                        sY.onchange = yaz; sB.onchange = yaz;
                        tdK_.append(sY, sB);
                    } else if (!kap) tdK_.textContent = "Belirtilmedi";
                    tr_.appendChild(tdK_);
                    const n = Number(say[x.tur] || 0);
                    const tdS = elYap("td", "", x.ozel ? "Kolon kartlarında seçilir" : ftBinlik(n) + " kolon");
                    const orn = (r.tur_ornek || {})[x.tur] || [];
                    if (orn.length) tdS.appendChild(bolmeBilgiSimgesi(orn.map(o => o[0] + " (" + o[1] + ")\n"
                        + (o[2] ? tireSade(o[2]) : "Tanımı yok")).join("\n\n"), x.ad + " anlamındaki kolonlar"));
                    tr_.appendChild(tdS);
                    const tdI = elYap("td", "");
                    if (x.ozel && !kilitli && !calisiyor) {
                        const kal = elYap("button", "dg-baglanti", "Kaldır");
                        kal.type = "button";
                        kal.onclick = () => {
                            ozelTurler = ozelTurler.filter(y => y.tur !== x.tur);
                            duzen[anah] = Object.assign(duzen[anah] || {}, { ozel_turler: ozelTurler.slice() });
                            dtCiz(); boya(); if (degisti) degisti();
                        };
                        tdI.appendChild(kal);
                    }
                    tr_.appendChild(tdI);
                    tb.appendChild(tr_);
                });
                t.appendChild(tb);
                dt.appendChild(t);
                const nb = Number(say.belirsiz || 0);
                if (nb) {
                    const be = elYap("div", "dg-dt-belirsiz", ftBinlik(nb) + " kolonun tanımında yön ya da kapsam açık "
                        + "değil (belirsiz); 01.2.4.3 Kolon Kartları'nda size sorulur.");
                    const orn = (r.tur_ornek || {}).belirsiz || [];
                    if (orn.length) be.appendChild(bolmeBilgiSimgesi(orn.map(o => o[0] + " (" + o[1] + ")\n"
                        + (o[2] ? tireSade(o[2]) : "Tanımı yok")).join("\n\n"), "Türü belirsiz kolonlar"));
                    dt.appendChild(be);
                }
                if (kilitli || calisiyor) return;
                if (!ekleAcik) {
                    const eb = elYap("button", "dg-toplu-btn", "Tür Ekle");
                    eb.type = "button";
                    eb.onclick = () => {
                        ekleAcik = true; ekleHata = ""; ekleDeger = { ad: "", anlam: "", yon: "", bicim: "" }; dtCiz();
                    };
                    dt.appendChild(eb);
                    return;
                }
                const f = elYap("div", "dg-dt-ekle");
                const adG = document.createElement("input");
                adG.type = "text"; adG.className = "dg-giris"; adG.placeholder = "Türün adı (ör. Ay başından)";
                const anG = document.createElement("input");
                anG.type = "text"; anG.className = "dg-giris"; anG.placeholder = "Anlamı (ör. ay başından [sayı] gün)";
                const secYap = (liste, ilk, etiket) => {
                    const sc = document.createElement("select");
                    sc.className = "dg-giris"; sc.setAttribute("aria-label", etiket);
                    const o0 = document.createElement("option"); o0.value = ""; o0.textContent = ilk; sc.appendChild(o0);
                    liste.forEach(([v, a]) => { const o = document.createElement("option"); o.value = v; o.textContent = a; sc.appendChild(o); });
                    return sc;
                };
                const yonS = secYap(YONLER, "Yön seçin", "Yön");
                const bicS = secYap(BICIMLER, "Biçim seçin", "Biçim");
                adG.value = ekleDeger.ad; anG.value = ekleDeger.anlam;
                yonS.value = ekleDeger.yon; bicS.value = ekleDeger.bicim;
                const sakla = () => {
                    ekleDeger = { ad: adG.value, anlam: anG.value, yon: yonS.value, bicim: bicS.value };
                };
                adG.oninput = sakla; anG.oninput = sakla;
                const kapOn = elYap("div", "dg-dt-kapsam-onizle", "");
                const onizle = () => {
                    bicS.disabled = yonS.value === "yonsuz";
                    const k = kapsamYaz(yonS.value, yonS.value === "yonsuz" ? "uzunluk" : bicS.value, birimAl());
                    kapOn.textContent = k && (yonS.value === "yonsuz" || bicS.value)
                        ? "Kapsam: " + donemAnlamGoster(kalipNe(), k) : "";
                };
                yonS.onchange = () => { sakla(); onizle(); };
                bicS.onchange = () => { sakla(); onizle(); };
                onizle();
                const ek = elYap("button", "dg-toplu-btn", "Ekle");
                ek.type = "button";
                const vz = elYap("button", "dg-baglanti", "Vazgeç");
                vz.type = "button";
                vz.onclick = () => { ekleAcik = false; dtCiz(); };
                ek.onclick = () => {
                    const ad = adG.value.trim().replace(/\s+/g, " ");
                    const anlam = donemAnlamIc(kalipNe(), anG.value.trim());
                    const yon = yonS.value, bicim = yon === "yonsuz" ? "uzunluk" : bicS.value;
                    if (!ad || !anlam) { ekleHata = "Adı ve anlamı yazın."; dtCiz(); return; }
                    if (anlam.indexOf("<N") === -1) { ekleHata = "Anlamda [sayı] olmalı."; dtCiz(); return; }
                    if (!yon || !bicim) { ekleHata = "Yön ve biçimi seçin."; dtCiz(); return; }
                    let kod = ad.toLocaleLowerCase("tr").replace(/ç/g, "c").replace(/ğ/g, "g").replace(/ı/g, "i")
                        .replace(/ö/g, "o").replace(/ş/g, "s").replace(/ü/g, "u").replace(/[^a-z0-9]+/g, "_")
                        .replace(/^_+|_+$/g, "").slice(0, 20) || "tur";
                    if (!/^[a-z]/.test(kod)) kod = "t_" + kod;
                    const kullanilan = new Set(["son", "once", "sonraki", "sonra", "cevre", "takvim", "sure", "belirsiz"]
                        .concat(ozelTurler.map(y => y.tur)));
                    let k2 = kod, i = 2;
                    while (kullanilan.has(k2)) k2 = kod + "_" + (i++);
                    ozelTurler.push({ tur: k2, ad: ad, anlam: anlam, yon: yon, bicim: bicim });
                    duzen[anah] = Object.assign(duzen[anah] || {}, { ozel_turler: ozelTurler.slice() });
                    ekleAcik = false; ekleHata = "";
                    dtCiz(); boya(); if (degisti) degisti();
                };
                f.append(adG, anG, yonS, bicS, ek, vz);
                dt.appendChild(f);
                dt.appendChild(kapOn);
                if (ekleHata) dt.appendChild(elYap("div", "dg-dt-hata", ekleHata));
            };
            dtCiz();
            g.addEventListener("input", dtCiz);
        }
        /* DEĞERLER (yalnız sayı yer tutucusu olan kalıpta): Anlam hücresinde
           bir örnek ve "Değerleri Düzenle"; açılınca grup satırının hemen
           altında, tablo genişliğinde değer paneli. Her değerin durumu
           bölmeli düğmeyle seçilir: Kalıba Uyar / Kendi Anlamı / Dönem
           Değil. Anlam kutusu yalnız Kendi Anlamı seçiliyken yazılır ve
           yazılan yalnız o değerde kalır; Kalıba Uyar'da kutu kalıbın
           anlamını gösterir (kalıbın anlamı satırın anlam kutusundan
           değişir). */
        const ornekEl = elYap("div", "dg-donem-ornek");
        const dgAc = elYap("button", "dg-donem-deger-ac", "");
        dgAc.type = "button";
        tdA.insertBefore(dgAc, g.nextSibling);
        tdA.insertBefore(ornekEl, dgAc);
        /* SAYI EKLE: anlam kutusunun altında kalıbın sayıları için düğmeler
           ([sayı 1], [sayı 2]); basınca imlecin olduğu yere eklenir. Kalıp
           değişince (elle satır) dgCiz yeniler. */
        const sayiEkle = donemSayiDugmeleri(kalipNe, g);
        tdA.insertBefore(sayiEkle, ornekEl);
        /* KOŞULLARI DÜZENLE (Değerleri Düzenle'nin yanında): adda belirli
           bir parça geçerse kalıbın anlamı (ör. [sayı 1]D_[sayı 2]D, adda
           RATIO geçerse "son [sayı 1] gün ile son [sayı 2] gün"). Panel değer
           paneliyle aynı düzende, satırın altında: her parçanın durumu
           Kalıba Uyar / Kendi Anlamı. Kolon Kartları'nda o parçanın geçtiği
           kolonun kartı kendi anlamıyla kurulur. kosMap: PARÇA -> anlam
           (içeride yer tutuculu; yazılırken boş olabilir). */
        const kosMap = Object.assign({}, (dz && dz.kosullu) || r.kosullu || {});
        /* Adaylar: kalıbın geçtiği adlardaki harf parçaları, çok geçen önce:
           [parça, kolon sayısı, örnek değer, örnekler ([ad, değer, açıklama])]. */
        const kosAday = r.kosul_adaylari || [];
        const kosAdayBul = p => kosAday.find(x => x[0] === String(p || "").trim().toUpperCase());
        const KOS_TABLO_ADET = 50;
        let kosAcik = !!(dz && dz.kosAcik);
        let kosAra = "";
        const kosCikti = () => {
            const o = {};
            Object.entries(kosMap).forEach(([p, a]) => { if (String(a || "").trim()) o[p] = String(a).trim(); });
            return o;
        };
        const kosHata = a => !String(a || "").trim() ? "" : donemYerTutucuHatasi(kalipNe(), a);
        const kosDegisti = () => {
            duzen[anah] = Object.assign(duzen[anah] || {}, { kosullu: kosCikti() });
            boya(); sekmeSayilari(); if (degisti) degisti();
        };
        const kosAc = elYap("button", "dg-donem-deger-ac dg-donem-kosul-ac", "");
        kosAc.type = "button";
        kosAc.title = "Kolon adında belirli bir parça geçince bu kalıbın anlamı farklıysa burada yazın (ör. RATIO).";
        const duzenDugmeleri = elYap("div", "dg-donem-duzenle");
        tdA.insertBefore(duzenDugmeleri, dgAc);
        duzenDugmeleri.append(dgAc, kosAc);
        const dgKap = elYap("div", "");
        const kosKap = elYap("div", "dg-donem-kosul-kap");
        /* Parçanın örnek kolonları (i balonu): parçanın ve kalıbın birlikte
           geçtiği 3 kolon, sözlük açıklaması ve (kendi anlamı yazıldıysa)
           o anlamla kolonun dönemi. */
        const kosOrnekBalonu = (aday, anlam) => {
            const orn = (aday && aday[3]) || [];
            if (!orn.length) return elYap("span", "bolme-info bos");
            const kal = donemSayiGoster(kalipNe());
            const anl = String(anlam || "").trim() && !kosHata(anlam) ? anlam : anlamAl().trim();
            const par = orn.map(([ad, dg, tn]) => ad
                + "\nAçıklaması: " + (tn || "Sözlükte açıklaması yok.")
                + "\n" + dg + (anl ? ": " + donemDegerAnlami(kalipNe(), anl, dg) : ""));
            const bas = "Adında " + aday[0] + " ve " + kal + " geçen " + ftBinlik(aday[1]) + " kolon"
                + (orn.length < aday[1] ? "dan " + orn.length + " örnek" : "");
            const i_ = bolmeBilgiSimgesi(par.join("\n\n"), bas);
            i_.classList.add("dg-donem-kosul-i", "bolme-info-genis");
            return i_;
        };
        /* KOŞUL ÖNERİLERİ: kalıbın anlamıyla sözlük açıklamaları uyuşmayan
           parçalar için arka uçta hazırlanan koşullu anlam önerileri
           (akis donem_kosul_onerisi). Kalıbın KAYDEDİLMİŞ anlamıyla
           (KAYIT_ANLAM) ve Koşulları Düzenle paneli açılınca istenir;
           kaydedilmiş anlam değişince (Kaydet, Kaydı Geri Al) panel açıksa
           yeniden istenir; hazırlanırken yoklanır. Panel hiç açılmayan ya
           da kaydedilmemiş kalıp için istenmez.
           Öneri yalnız gösterilir: «Öneriyi Al» Kendi Anlamı'na yazar,
           kullanıcı düzeltir. */
        let kosOneri = null, kosOneriAnlam = null, kosOneriZaman = null;
        const kosOneriVar = (p, o) => !!o && !(p in kosMap && String(kosMap[p] || "").trim() === o.anlam);
        const kosOneriListesi = () => (kosOneri && kosOneri.durum === "hazir" && kosOneri.oneriler) || {};
        function kosOneriGonder(an, yeniden) {
            clearTimeout(kosOneriZaman);
            fetch(getWebAppBackendUrl("donem_kosul_oneri"), {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ oturum_id: OTURUM_ID, kalip: String(kalipNe() || "").toUpperCase(), anlam: an,
                    kaliplar: satirlar.map(s_ => String((s_.kalipNe && s_.kalipNe()) || "").toUpperCase()),
                    yeniden: !!yeniden })
            })
            .then(res => res.json())
            .then(d => {
                if (kosOneriAnlam !== an || !tr.isConnected) return;
                kosOneri = d && d.durum ? d : { durum: "hata", hata: (d && d.hata) || "" };
                if (kosOneri.durum === "yok") kosOneri = null;
                kosCiz();
                if (kosOneri && kosOneri.durum === "calisiyor")
                    kosOneriZaman = setTimeout(() => { if (kosOneriAnlam === an) kosOneriGonder(an); }, 2500);
            })
            .catch(() => {
                if (kosOneriAnlam !== an || !tr.isConnected) return;
                kosOneri = { durum: "hata", hata: "" }; kosCiz();
            });
        }
        function kosOneriIste(yeniden) {
            const an = String(KAYIT_ANLAM[anah] || "").trim();
            if (kilitli || !kosAday.length) {
                clearTimeout(kosOneriZaman);
                if (kosOneri) { kosOneri = null; kosOneriAnlam = null; kosCiz(); }
                return;
            }
            /* Kaydedilmiş anlam yok: öneri hazırlanmaz, panel nedenini yazar. */
            if (!an || donemYerTutucuHatasi(kalipNe(), an)) {
                clearTimeout(kosOneriZaman);
                kosOneri = { durum: "kayitsiz" }; kosOneriAnlam = null; kosCiz();
                return;
            }
            if (!yeniden && kosOneriAnlam === an) return;
            kosOneriAnlam = an;
            kosOneri = { durum: "calisiyor", biten: 0, toplam: 0 };
            kosOneriGonder(an, yeniden);
        }
        function kosButonCiz() {
            const n = Object.keys(kosCikti()).length;
            const on = Object.entries(kosOneriListesi()).filter(([p, o]) => kosOneriVar(p, o)).length;
            kosAc.textContent = "";
            kosAc.append(elYap("span", "dg-donem-deger-ac-ad", (kosAcik ? "▾ " : "▸ ") + "Koşulları Düzenle"),
                         elYap("span", "dg-donem-deger-ozet", ftBinlik(kosAday.length) + " parça"
                               + (n ? " · " + ftBinlik(n) + " kendi anlamı" : "")
                               + (on ? " · " + ftBinlik(on) + " öneri"
                                  : kosOneri && kosOneri.durum === "calisiyor" ? " · öneriler hazırlanıyor" : "")));
            kosAc.setAttribute("aria-expanded", kosAcik ? "true" : "false");
            kosAc.hidden = !kosAday.length && !Object.keys(kosMap).length;
        }
        /* Paneldeki öneri durumu: hazırlanıyor, alınamadı ya da kaç kolonun
           açıklamasına bakıldığı; hiçbir parçaya bağlanamayan uyumsuz
           kolonlar i balonunda (elle bakılsın). */
        function kosOneriDurumu() {
            if (!kosOneri) return null;
            const el = elYap("div", "dg-donem-kosul-oneri-durum");
            if (kosOneri.durum === "kayitsiz") {
                el.textContent = "Öneriler kalıbın kaydedilmiş anlamıyla hazırlanır. Önce satırı «Kaydet» ile "
                    + "kaydedin; kaydedince öneriler burada görünür.";
                return el;
            }
            /* Kutudaki anlam kaydedilenden farklı: öneriler kaydedilene göre. */
            const fark = kosOneriAnlam && anlamAl().trim().replace(/\s+/g, " ")
                !== String(kosOneriAnlam).replace(/\s+/g, " ");
            if (fark) el.appendChild(elYap("div", "dg-donem-kosul-uyari", "Öneriler kaydedilmiş anlama göre: «"
                + donemAnlamGoster(kalipNe(), kosOneriAnlam) + "». Kutudaki değişikliği kaydedince yeniden hazırlanır."));
            const yaz = t => el.insertBefore(document.createTextNode(t), el.firstChild);
            if (kosOneri.durum === "calisiyor") {
                yaz("Sözlük açıklamaları kalıbın kaydedilmiş anlamıyla karşılaştırılıyor"
                    + (kosOneri.toplam ? ": " + ftBinlik(kosOneri.biten || 0) + " / " + ftBinlik(kosOneri.toplam) + " kolon" : "")
                    + ". Öneriler bitince burada görünür.");
                return el;
            }
            if (kosOneri.durum === "hata") {
                const b = elYap("button", "dg-baglanti", "Yeniden Dene");
                b.type = "button";
                b.onclick = () => kosOneriIste(true);
                el.insertBefore(b, el.firstChild);
                yaz("Öneriler alınamadı. ");
                return el;
            }
            const o = kosOneri, n = Object.keys(o.oneriler || {}).length;
            if (!o.kontrol) { yaz("Bu kalıbın geçtiği kolonların sözlükte açıklaması yok; öneri yapılamadı."); return el; }
            yaz("Sözlükte açıklaması olan " + ftBinlik(o.kontrol) + " kolon kalıbın kaydedilmiş anlamıyla karşılaştırıldı: "
                + ftBinlik(o.uyumlu) + " uyumlu, " + ftBinlik(o.uyumsuz) + " uyumsuz, " + ftBinlik(o.belirsiz) + " belirsiz. "
                + (n ? ftBinlik(n) + " parça için öneri var; satırında «Öneriyi Al» ile alıp düzeltebilirsiniz."
                     : "Öneri yok.")
                + (o.eksik ? " " + ftBinlik(o.eksik) + " kolona dil modeli cevap vermedi." : ""));
            if (o.aciklanamayan_sayisi) {
                const u = elYap("div", "dg-donem-kosul-uyari", ftBinlik(o.aciklanamayan_sayisi)
                    + " uyumsuz kolon hiçbir parçaya bağlanamadı; elle bakın.");
                const i_ = bolmeBilgiSimgesi((o.aciklanamayan || []).map(([ad, dg, tn, dolu]) => ad
                    + "\nAçıklaması: " + tn + "\n" + dg + ", kalıbın anlamıyla: " + dolu).join("\n\n")
                    + (o.aciklanamayan_sayisi > (o.aciklanamayan || []).length
                       ? "\n\nve " + ftBinlik(o.aciklanamayan_sayisi - o.aciklanamayan.length) + " kolon daha." : ""),
                    "Parçaya bağlanamayan uyumsuz kolonlar");
                i_.classList.add("bolme-info-genis");
                u.appendChild(i_);
                el.appendChild(u);
            }
            return el;
        }
        /* Parça satırındaki öneri: anlam, neden, kaç kolon, i balonunda
           örnekler ve «Öneriyi Al» (Kendi Anlamı'na yazar, kutu odaklanır). */
        /* Parça satırındaki öneri. Alınmadıysa: kural, neden, somut bir
           örnek kolon (açıklaması, öneriyle ve kaydedilmiş anlamla) ve
           «Öneriyi Al». Alındıysa kısa satır; kutudaki yazı öneriden
           farklıysa «Tekrar Öner» önerilen yazıya döndürür. */
        const kosKutuOdak = p => {
            const yeni = kosKap.querySelector('input[aria-label="' + CSS.escape(p + " koşullu anlamı") + '"]');
            if (!yeni) return;
            /* İmleç sona: yazı seçili gelmez, yazmaya başlamak öneriyi silmez. */
            yeni.focus();
            const n = yeni.value.length;
            yeni.setSelectionRange(n, n);
        };
        function kosOneriSatiri(p, o, kilit) {
            const oneriYazi = donemAnlamGoster(kalipNe(), o.anlam);
            const alindi = p in kosMap;
            const el = elYap("div", "dg-donem-kosul-oneri" + (alindi ? " alindi" : ""));
            const oneriAl = yaz => {
                const b = elYap("button", "dg-toplu-btn", yaz);
                b.type = "button"; b.disabled = kilit;
                b.title = "Önerilen yazı bu parçanın kendi anlamı olur; sonra kutuda istediğiniz gibi değiştirebilirsiniz.";
                b.onclick = () => {
                    if (kilitli || da.dm === "calisiyor") return;
                    kosMap[p] = o.anlam;
                    kosCiz(); kosDegisti();
                    kosKutuOdak(p);
                };
                return b;
            };
            if (alindi) {
                if (!kosOneriVar(p, o)) {
                    el.appendChild(elYap("div", "dg-donem-tur-not",
                        "Öneri alındı. Yukarıdaki kutuda yazıyı istediğiniz gibi değiştirebilirsiniz."));
                    return el;
                }
                el.appendChild(elYap("div", "dg-donem-tur-not", "Önerilen yazı: «" + oneriYazi + "». Kutudaki yazı "
                    + "öneriden farklı; öneriye dönmek için «Tekrar Öner»e basın."));
                el.appendChild(oneriAl("Tekrar Öner"));
                return el;
            }
            const bas = elYap("div", "dg-donem-kosul-oneri-bas");
            bas.appendChild(elYap("span", "dg-donem-kosul-oneri-ad", "Öneri: "));
            bas.appendChild(document.createTextNode("adında " + p + " geçen kolonlarda bu kalıp «" + oneriYazi + "» demek."));
            el.appendChild(bas);
            el.appendChild(elYap("div", "dg-donem-tur-not", "Neden: adında " + p + " geçen " + ftBinlik(o.uyumsuz)
                + " kolonun sözlük açıklaması kalıbın kaydedilmiş anlamıyla («"
                + donemAnlamGoster(kalipNe(), kosOneriAnlam || "") + "») uyuşmuyor, bu öneriyle uyuşuyor."
                + (o.toplam > o.uyumsuz ? " Parça " + ftBinlik(o.toplam) + " kolonda geçiyor; ötekilerinin açıklaması "
                   + "yok ya da dönemi söylemiyor." : "")
                + (o.neden ? " " + tireSade(donemNedenGoster(o.neden)) : "")
                + ((o.ayni || []).length ? " Aynı kolonlarda " + o.ayni.join(", ") + " de geçiyor." : "")));
            const orn = o.ornekler || [];
            if (orn.length) {
                const [ad, dg, tn, dolu] = orn[0];
                const ornEl = elYap("div", "dg-donem-tur-not", "Ör. " + ad + ": açıklaması «" + tireSade(tn)
                    + "»; öneriyle «" + dolu + "», şimdiki anlamla «"
                    + donemDegerAnlami(kalipNe(), kosOneriAnlam || "", dg) + "».");
                if (orn.length > 1) {
                    const i_ = bolmeBilgiSimgesi(orn.map(([ad_, dg_, tn_, dolu_]) => ad_ + "\nAçıklaması: " + tn_
                        + "\n" + dg_ + ", öneriyle: " + dolu_ + "\n" + dg_ + ", şimdiki anlamla: "
                        + donemDegerAnlami(kalipNe(), kosOneriAnlam || "", dg_)).join("\n\n"),
                        "Öneriye dayanak olan kolonlar");
                    i_.classList.add("bolme-info-genis");
                    ornEl.appendChild(i_);
                }
                el.appendChild(ornEl);
            }
            el.appendChild(oneriAl("Öneriyi Al"));
            return el;
        }
        function kosCiz() {
            kosButonCiz();
            kosKap.textContent = "";
            if (!kosAcik || kosAc.hidden) return;
            const k = kilitli || da.dm === "calisiyor";
            const panel = elYap("div", "dg-donem-panel");
            const bas = elYap("div", "dg-donem-panel-bas");
            bas.appendChild(elYap("span", "dg-donem-panel-ad", donemSayiGoster(kalipNe()) + " koşulları"));
            bas.appendChild(elYap("span", "dg-donem-panel-ipucu",
                "Kolon adında bu parçalardan biri geçerse kalıbın anlamı. Kalıba Uyar: o kolonlarda da kalıbın "
                + "anlamı kullanılır. Kendi Anlamı: o parçanın geçtiği kolonlarda kalıp burada yazdığınız anlamı "
                + "alır; sayıları altındaki düğmelerle ekleyin."));
            panel.appendChild(bas);
            const od = kosOneriDurumu();
            if (od) panel.appendChild(od);
            const ara = document.createElement("input");
            ara.type = "text"; ara.className = "dg-giris dg-donem-kosul-ara";
            ara.placeholder = "Parça ara"; ara.setAttribute("aria-label", "Parça ara");
            ara.value = kosAra;
            panel.appendChild(ara);
            const tablo = elYap("table", "dg-tablo dg-donem-deger-tablo dg-donem-kosul-tablo");
            const th = document.createElement("thead"), hr = document.createElement("tr");
            hr.append(elYap("th", "", "Parça"), elYap("th", "", "Kolon"), elYap("th", "", "Anlam"));
            const thD = elYap("th", "", "Durum");
            thD.appendChild(bolmeBilgiSimgesi("Kalıba Uyar: adında bu parça geçen kolonlarda da kalıbın anlamı "
                + "kullanılır. Kendi Anlamı: adında bu parça geçen kolonlarda kalıp burada yazdığınız anlamı alır "
                + "(ör. RATIO geçince «son [sayı 1] gün ile son [sayı 2] gün»). Bir kolonun adında kendi anlamı "
                + "olan birden çok parça geçerse alfabede önce gelen kullanılır.", "Durum"));
            hr.appendChild(thD);
            th.appendChild(hr);
            const govde = document.createElement("tbody");
            tablo.append(th, govde);
            panel.appendChild(tablo);
            const alt = elYap("div", "dg-donem-tur-not", "");
            panel.appendChild(alt);
            /* Kendi anlamı olanlar önce; hafızadan gelen ama adlarda bu kalıpla
               geçmeyen parça da listede (kolon 0). */
            const hepsi = kosAday.concat(Object.keys(kosMap).filter(p => !kosAdayBul(p)).map(p => [p, 0, "", []]));
            const onl = kosOneriListesi();
            const sirali = hepsi.filter(x => x[0] in kosMap)
                .concat(hepsi.filter(x => !(x[0] in kosMap) && onl[x[0]]))
                .concat(hepsi.filter(x => !(x[0] in kosMap) && !onl[x[0]]));
            const satirlariCiz = () => {
                govde.textContent = "";
                const q = kosAra.trim().toLocaleUpperCase("tr");
                const uyan = sirali.filter(x => !q || x[0].indexOf(q) !== -1);
                uyan.slice(0, KOS_TABLO_ADET).forEach(x => {
                    const p = x[0];
                    const durum = p in kosMap ? "ozel" : "kalip";
                    const satir = elYap("tr", "dg-donem-deger dg-durum-" + durum);
                    satir.appendChild(elYap("td", "", "")).appendChild(elYap("span", "dg-kisa-cip dg-durum-" + durum, p));
                    const tdK = elYap("td", "dg-donem-deger-kolon", ftBinlik(x[1]));
                    let ornI = kosOrnekBalonu(x, kosMap[p]);
                    tdK.appendChild(ornI);
                    satir.appendChild(tdK);
                    const tdG = elYap("td", "");
                    const gi = document.createElement("input");
                    gi.type = "text";
                    gi.className = "dg-giris dg-donem-deger-giris";
                    gi.setAttribute("aria-label", p + " koşullu anlamı");
                    tdG.appendChild(gi);
                    const not = elYap("div", "dg-donem-tur-not", "");
                    let onEl = null;
                    if (durum === "kalip") {
                        gi.value = donemAnlamGoster(kalipNe(), anlamAl());
                        gi.disabled = true;
                        gi.title = "Kalıbın anlamından gelir. Bu parça için başka anlam yazmak için Kendi Anlamı'na basın.";
                    } else {
                        gi.value = donemAnlamGoster(kalipNe(), kosMap[p]);
                        gi.placeholder = "Bu parça geçince anlamı";
                        gi.disabled = k;
                        const notYaz = () => {
                            const h = kosHata(kosMap[p]);
                            gi.classList.toggle("dg-noksan", !!h);
                            not.classList.toggle("dg-donem-ad-hata", !!h);
                            not.textContent = h ? h : x[2] && String(kosMap[p] || "").trim()
                                ? "Ör. " + x[2] + " → " + donemDegerAnlami(kalipNe(), kosMap[p], x[2])
                                : !x[1] ? "Bu parça bu kalıpla birlikte adlarda geçmiyor." : "";
                        };
                        notYaz();
                        gi.addEventListener("input", () => {
                            kosMap[p] = donemAnlamIc(kalipNe(), gi.value);
                            notYaz();
                            const y = kosOrnekBalonu(x, kosMap[p]); ornI.replaceWith(y); ornI = y;
                            /* Öneriyle aynı mı değil mi: öneri kutusu yenilenir. */
                            if (onEl) { const o_ = kosOneriSatiri(p, onl[p], k); onEl.replaceWith(o_); onEl = o_; }
                            kosButonCiz(); kosDegisti();
                        });
                        /* Kendi anlamı boş bırakılıp kutudan çıkılırsa parça kalıba döner. */
                        gi.addEventListener("change", () => {
                            if (gi.value.trim()) return;
                            delete kosMap[p];
                            kosCiz(); kosDegisti();
                        });
                        if (!k) tdG.appendChild(donemSayiDugmeleri(kalipNe, gi));
                    }
                    tdG.appendChild(not);
                    if (onl[p]) { onEl = kosOneriSatiri(p, onl[p], k); tdG.appendChild(onEl); }
                    satir.appendChild(tdG);
                    const tdS = elYap("td", "");
                    const seg = elYap("div", "dg-segment");
                    seg.setAttribute("role", "radiogroup");
                    seg.setAttribute("aria-label", p + " durumu");
                    [["kalip", "Kalıba Uyar"], ["ozel", "Kendi Anlamı"]].forEach(([deg, ad]) => {
                        const b = elYap("button", deg === durum ? "secili" : "", ad);
                        b.type = "button";
                        b.setAttribute("role", "radio");
                        b.setAttribute("aria-checked", deg === durum ? "true" : "false");
                        b.disabled = k;
                        b.onclick = () => {
                            if (kilitli || da.dm === "calisiyor" || deg === durum) return;
                            if (deg === "ozel") kosMap[p] = anlamAl().trim();
                            else delete kosMap[p];
                            kosCiz(); kosDegisti();
                            if (deg === "ozel") kosKutuOdak(p);
                        };
                        seg.appendChild(b);
                    });
                    tdS.appendChild(seg);
                    satir.appendChild(tdS);
                    govde.appendChild(satir);
                });
                if (!uyan.length) {
                    const tr_ = elYap("tr", "dg-bos-tablo");
                    const td_ = elYap("td", "", "«" + kosAra.trim() + "» bu kalıpla birlikte adlarda geçmiyor.");
                    td_.colSpan = 4; tr_.appendChild(td_); govde.appendChild(tr_);
                }
                alt.textContent = uyan.length > KOS_TABLO_ADET
                    ? ftBinlik(uyan.length - KOS_TABLO_ADET) + " parça daha var; aradığınızı yukarıdaki kutuya yazın." : "";
            };
            ara.oninput = () => { kosAra = ara.value; satirlariCiz(); };
            satirlariCiz();
            kosKap.appendChild(panel);
        }
        /* Panel açık kurulduysa (yeniden çizim) bütün satırlar kurulduktan
           sonra istenir (kalıp listesi tam olsun). */
        setTimeout(() => { if (kosAcik) kosOneriIste(); }, 0);
        /* Kaydedilmiş anlam değişti (Kaydet, Kaydı Geri Al): panel açıksa
           yeni anlamla istenir; kapalıysa eski öneri düşer, panel açılınca
           istenir. */
        const kosOneriYenile = () => {
            if (kosAcik) { kosOneriIste(); return; }
            clearTimeout(kosOneriZaman);
            kosOneri = null; kosOneriAnlam = null; kosButonCiz();
        };
        kosAc.onclick = () => {
            kosAcik = !kosAcik;
            duzen[anah] = Object.assign(duzen[anah] || {}, { kosAcik });
            if (kosAcik) kosOneriIste();
            dgCiz();
            if (kosAcik) { const a_ = kosKap.querySelector(".dg-donem-kosul-ara"); if (a_) a_.focus(); }
        };
        const detay = elYap("tr", "dg-donem-detay");
        const detayTd = elYap("td", "");
        detayTd.colSpan = 4;
        detay.appendChild(detayTd);
        detayTd.append(dgKap, kosKap);
        let dgAcik = !!(dz && dz.dgAcik);
        const kalipSimdi = () => kg ? kg.value.trim() : r.kalip;
        const degerListesi = () => kg ? adlardaBul(kg.value) : (r.degerler || []);
        const otoAnlam = dg => donemDegerAnlami(kalipSimdi(), anlamAl().trim(), dg);
        function dgKaydet() {
            duzen[anah] = Object.assign(duzen[anah] || {}, {
                deger_anlam: Object.assign({}, dgAnlam), ayrilan: ayrilanlar });
        }
        function dgOzet(liste) {
            const say = { ozel: 0, disi: 0 };
            liste.forEach(d => { const s = degerDurumu(d.deger); if (say[s] !== undefined) say[s]++; });
            return ftBinlik(liste.length) + " değer"
                + (say.ozel ? " · " + ftBinlik(say.ozel) + " kendi anlamı" : "")
                + (say.disi ? " · " + ftBinlik(say.disi) + " dönem değil" : "");
        }
        function dgCiz() {
            sayiEkle.yenile();
            kosCiz();
            const liste = degerListesi();
            const var_ = /<N{1,2}>|<N\d>/i.test(kalipSimdi() || "") && liste.length > 0;
            const gecen = new Set(liste.map(d => d.deger));
            /* Adlarda artık geçmeyen değerin kendi anlamı düşer. Kalıbın
               anlamıyla aynı kendi anlamı burada silinmez (kullanıcı
               Kendi Anlamı'na basıp yazmaya başlıyor); onayda arka uç
               saklamaz. */
            Object.keys(dgAnlam).forEach(dg => { if (!gecen.has(dg)) delete dgAnlam[dg]; });
            ornekEl.hidden = dgAc.hidden = !var_;
            detay.hidden = !((var_ && dgAcik) || (kosAcik && !kosAc.hidden));
            dgKap.textContent = "";
            /* Ayır: yer tutuculu kalıpta dönem sayılan iki ya da daha çok değer. */
            const ab = tr.querySelector(".dg-donem-ayir");
            if (ab) ab.hidden = !(var_ && liste.filter(d => degerDurumu(d.deger) !== "disi").length > 1);
            /* Adlarda Geçen çipleri durumu gösterir (elle satırı elleSay çizer). */
            if (!kg) { degerCiz(tdD, liste, degerDurumu); birlikteCiz(); }
            if (!var_) return;
            const ilk = liste.find(d => degerDurumu(d.deger) === "kalip") || liste[0];
            const ornekAnlam = otoAnlam(ilk.deger);
            ornekEl.textContent = ornekAnlam ? "Örnek: " + ilk.deger + " → " + ornekAnlam : "";
            /* Kalıpta birden çok sayı varsa [sayı] sırayla 1., 2. sayıyı alır;
               aynı sayıyı tekrar yazmanın yolu [sayı 1], [sayı 2]. */
            const ytAdet = donemYtAdedi(kalipSimdi());
            if (ornekAnlam && ytAdet > 1) ornekEl.appendChild(elYap("div", "dg-donem-tur-not",
                "Kalıpta " + ytAdet + " sayı var: " + Array.from({ length: ytAdet }, (_x, j) => "[sayı " + (j + 1) + "]")
                .join(", ") + ", kalıptaki sırasıyla. Bir sayıyı birden çok yazabilir ya da hesap yazabilirsiniz: "
                + "[sayı 1 × sayı 2], [sayı 1 + sayı 1] (ör. son [sayı 1] günden son [sayı 1 × sayı 2] gün önceye kadar)."));
            ornekEl.hidden = !ornekAnlam;
            dgAc.textContent = "";
            dgAc.append(elYap("span", "dg-donem-deger-ac-ad", (dgAcik ? "▾ " : "▸ ") + "Değerleri Düzenle"),
                        elYap("span", "dg-donem-deger-ozet", dgOzet(liste)));
            dgAc.setAttribute("aria-expanded", dgAcik ? "true" : "false");
            if (!dgAcik) return;
            const k = kilitli || da.dm === "calisiyor";
            const panel = elYap("div", "dg-donem-panel");
            const bas = elYap("div", "dg-donem-panel-bas");
            bas.appendChild(elYap("span", "dg-donem-panel-ad", r.kalip ? donemSayiGoster(r.kalip) + " değerleri" : "Değerler"));
            bas.appendChild(elYap("span", "dg-donem-panel-ipucu",
                "Kalıbın anlamı her değere kendi sayısıyla uygulanır. Bir değere özel anlam yazmak "
                + "için önce o satırda Kendi Anlamı'na basın; yazdığınız yalnız o değerde kalır."));
            panel.appendChild(bas);
            const tablo = elYap("table", "dg-tablo dg-donem-deger-tablo");
            const th = document.createElement("thead"), hr = document.createElement("tr");
            hr.append(elYap("th", "", "Değer"), elYap("th", "", "Kolon"), elYap("th", "", "Anlam"));
            const thD = elYap("th", "", "Durum");
            thD.appendChild(bolmeBilgiSimgesi("Kalıba Uyar: değerin anlamı kalıbın anlamından gelir. "
                + "Kendi Anlamı: değere özel anlam (ör. 360D: son 1 yıl); kalıp değişse de kalır. "
                + "Dönem Değil: değer bu gruba yanlış girmiş; dönem bilgisi sayılmaz. Bütün değerler "
                + "dönem değilse kalıbı Çıkar ile çıkarın.", "Durum"));
            hr.appendChild(thD);
            th.appendChild(hr);
            tablo.appendChild(th);
            const govde = document.createElement("tbody");
            const donemKalan = liste.filter(d => degerDurumu(d.deger) !== "disi").length;
            liste.forEach(d => {
                const durum = degerDurumu(d.deger);
                const satir = elYap("tr", "dg-donem-deger dg-durum-" + durum);
                satir.appendChild(elYap("td", "", "")).appendChild(
                    elYap("span", "dg-kisa-cip dg-durum-" + durum, d.deger));
                satir.appendChild(elYap("td", "dg-donem-deger-kolon", ftBinlik(d.kolon)));
                const tdG = elYap("td", "");
                const gi = document.createElement("input");
                gi.type = "text";
                gi.className = "dg-giris dg-donem-deger-giris";
                gi.setAttribute("aria-label", d.deger + " anlamı");
                if (durum === "disi") {
                    gi.value = "";
                    gi.placeholder = "Dönem bilgisi değil";
                    gi.disabled = true;
                } else if (durum === "kalip") {
                    /* Kalıba uyan değerin anlamı kalıptan gelir; burada
                       yazılmaz. Özel anlam için önce Kendi Anlamı. */
                    gi.value = otoAnlam(d.deger);
                    gi.disabled = true;
                    gi.title = "Kalıbın anlamından gelir. Bu değere özel anlam yazmak için Kendi Anlamı'na basın.";
                } else {
                    gi.value = dgAnlam[d.deger];
                    gi.placeholder = otoAnlam(d.deger) || "Anlamı yazın";
                    gi.disabled = k;
                    const ytKontrol = () => {
                        const yt = durum === "ozel" && !!donemYerTutucuHatasi("", gi.value.trim());
                        gi.classList.toggle("dg-noksan", yt);
                        gi.title = yt ? "Değerin anlamında yer tutucu olamaz; sayıyı yazın." : "";
                    };
                    ytKontrol();
                    gi.addEventListener("input", () => {
                        dgAnlam[d.deger] = gi.value.trim();
                        ytKontrol();
                        dgKaydet(); boya(); if (degisti) degisti();
                    });
                    /* Kendi anlamı boş bırakılıp kutudan çıkılırsa değer
                       kalıba döner. */
                    gi.addEventListener("change", () => {
                        if (gi.value.trim()) return;
                        delete dgAnlam[d.deger];
                        dgKaydet(); dgCiz(); boya(); if (degisti) degisti();
                    });
                }
                tdG.appendChild(gi);
                satir.appendChild(tdG);
                /* DURUM: bölmeli düğme (Görünüm anahtarıyla aynı dil). */
                const tdS = elYap("td", "");
                const seg = elYap("div", "dg-segment");
                seg.setAttribute("role", "radiogroup");
                seg.setAttribute("aria-label", d.deger + " durumu");
                [["kalip", "Kalıba Uyar"], ["ozel", "Kendi Anlamı"], ["disi", "Dönem Değil"]].forEach(([deg, ad]) => {
                    const b = elYap("button", deg === durum ? "secili" : "", ad);
                    b.type = "button";
                    b.setAttribute("role", "radio");
                    b.setAttribute("aria-checked", deg === durum ? "true" : "false");
                    b.disabled = k || (deg === "disi" && durum !== "disi" && donemKalan <= 1);
                    if (deg === "disi" && durum !== "disi" && donemKalan <= 1)
                        b.title = "Grupta dönem olarak en az bir değer kalır; bütün değerler dönem değilse kalıbı Çıkar ile çıkarın.";
                    b.onclick = () => {
                        if (kilitli || da.dm === "calisiyor" || deg === durum) return;
                        const simdiki = gi.value.trim();
                        delete ayrilanlar[d.deger];
                        delete dgAnlam[d.deger];
                        if (deg === "ozel") dgAnlam[d.deger] = simdiki || otoAnlam(d.deger);
                        if (deg === "disi") ayrilanlar[d.deger] = { anlam: "", cikar: true };
                        dgKaydet(); dgCiz(); boya(); if (degisti) degisti();
                        if (deg === "ozel") {
                            const yeni = detay.querySelector('tr.dg-donem-deger input[aria-label="'
                                + CSS.escape(d.deger + " anlamı") + '"]');
                            if (yeni) { yeni.focus(); yeni.select(); }
                        }
                    };
                    seg.appendChild(b);
                });
                tdS.appendChild(seg);
                satir.appendChild(tdS);
                govde.appendChild(satir);
            });
            tablo.appendChild(govde);
            panel.appendChild(tablo);
            dgKap.appendChild(panel);
        }
        dgAc.onclick = () => {
            dgAcik = !dgAcik;
            duzen[anah] = Object.assign(duzen[anah] || {}, { dgAcik });
            dgCiz();
        };
        tr.appendChild(tdA);
        /* ÇIKAR */
        const tdS = elYap("td", "dg-ekle-hucre");
        const cikBtn = elYap("button", "dg-toplu-btn dg-donem-cikar", "Çıkar");
        cikBtn.type = "button";
        cikBtn.disabled = kilitli || calisiyor;
        cikBtn.title = r.elle ? "Elle eklenen satırı sil"
            : r.kaynak === "hafiza"
                ? "Dönem bilgisinden çıkar: kullanılmaz ve onaylayınca hafızadan da silinir. Tablonun altından geri alınabilir."
                : "Dönem bilgisinden çıkar: kullanılmaz ve hafızaya yazılmaz. Tablonun altından geri alınabilir.";
        cikBtn.setAttribute("aria-label", (r.kalip || "Kalıp") + " çıkar");
        /* KAYDET: bu satırı onayı beklemeden hafızaya yazar. */
        const kaydetBtn = elYap("button", "dg-toplu-btn dg-donem-kaydet", "Kaydet");
        kaydetBtn.type = "button";
        kaydetBtn.title = "Bu satırı şimdi hafızaya kaydet. Kaydedilmemiş satırlardan anlamı buna "
            + "yakın olanları dil modeli yeniden yazar.";
        kaydetBtn.setAttribute("aria-label", (r.kalip || "Kalıp") + " kaydet");
        tdS.appendChild(kaydetBtn);
        tdS.appendChild(cikBtn);
        /* AYIR: yer tutuculu kalıp (grup ya da aile) yanlış gruplandıysa
           değerlerine ayrılır; her değer kendi satırında, kendi anlamıyla. */
        const ayirBtn = elYap("button", "dg-toplu-btn dg-donem-ayir", "Ayır");
        ayirBtn.type = "button";
        ayirBtn.disabled = kilitli || calisiyor;
        ayirBtn.title = "Grubu değerlerine ayırır: her değer kendi satırında, kalıbın anlamından "
            + "çıkan (ya da kendi) anlamıyla durur. Yeniden grup olarak Tüm Parçalar'dan alınabilir.";
        ayirBtn.hidden = true;
        tdS.appendChild(ayirBtn);
        tr.appendChild(tdS);
        const x = { r, g, tr, kg, anah, cikBtn, haric, kaydetBtn };
        ayirBtn.onclick = () => ayir(x);
        const kalipDegeri = () => kg ? kg.value.trim() : r.kalip;
        x.yt = () => /\[\s*say[ıi]\s*\]/i.test(anlamAl())
            ? "Kalıpta sayı yok; [sayı] yerine değeri yazın."
            : donemYerTutucuHatasi(kalipDegeri(), anlamAl().trim());
        x.anlam = anlamAl;
        function boya() {
            const v = anlamAl().trim();
            const yt = x.yt();
            const dikkat = !v || !!yt || (kg && !kg.value.trim());
            const oneriHaric = (r.haric_oneri || []).slice().sort().join("|");
            /* Ekran biçiminde karşılaştırılır: öneri "N gün", kutu "[sayı]
               gün" yazar; ikisi aynı anlam. */
            const duz0 = g.value.trim() !== donemAnlamGoster(kalipNe(), tireSade(r.oneri || "")).trim()
                || Array.from(haric).sort().join("|") !== oneriHaric
                || turSec.value !== (r.zaman_tur || "pencere");
            /* Uyarılı satır (yalnız ikili içinde geçen kalıp) dokunulana
               kadar dikkat çizgisi taşır; anlamı ya da hariç durumu
               değişince karar sizindir. Onayı durdurmaz. */
            const disiOnce = Object.keys(r.ayrilan || {}).filter(dg => (r.ayrilan[dg] || {}).cikar).sort();
            const disiSimdi = Object.keys(ayrilanlar).filter(dg => ayrilanlar[dg].cikar).sort();
            const dgOnce = JSON.stringify([Object.entries(r.deger_anlam || {}).sort(), disiOnce]);
            const dgSimdi = JSON.stringify([Object.entries(dgAnlam).sort(), disiSimdi]);
            const uyarili = !!r.uyari && !duz0 && dgOnce === dgSimdi;
            const duz = !dikkat && (duz0 || dgOnce !== dgSimdi);
            /* Renk yok: durum anlamın üstündeki etikette yazar; dikkat
               isteyen satırın solunda ince amber çizgi. */
            const bekliyor = !!r.bekliyor && da.dm === "calisiyor";
            const u = URETIM[anah];
            const uYaziyor = !v && u && (u.durum === "calisiyor" || u.durum === "sayac");
            /* Ekran biçiminde karşılaştırılır ("N" ile "[sayı]" aynı). */
            const uUretti = !!(u && u.durum === "bitti" && v
                && g.value.trim().replace(/\s+/g, " ")
                   === donemAnlamGoster(kalipNe(), tireSade(u.anlam || "")).trim().replace(/\s+/g, " "));
            tr.classList.toggle("dg-donem-dikkat", !bekliyor && !uYaziyor && (dikkat || uyarili));
            let et = "", dikkatEt = false;
            uretimNot.textContent = "";
            if (bekliyor) et = "Dil modeli yorumluyor";
            else if (uYaziyor && u.durum === "calisiyor") et = "Dil modeli anlamı yazıyor";
            else if (u && u.durum === "calisiyor" && u.zorla)
                et = "Kaydedilen bir anlama yakın: dil modeli yeniden yazıyor";
            else if (uYaziyor) et = "Anlam boş: birkaç saniye içinde dil modeli yazacak";
            else if (!v && u && u.durum === "hata") {
                et = "Dil modeli yazamadı: " + u.hata; dikkatEt = true;
                const yd = elYap("button", "dg-baglanti", "Yeniden dene");
                yd.type = "button";
                yd.disabled = kilitli || da.dm === "calisiyor";
                yd.onclick = () => { const kk = kalipNe(); if (kk) uretimBaslat(anah, kk); };
                uretimNot.appendChild(yd);
            }
            else if (!dikkat && x.kayitliMi()) {
                et = "Kaydedildi";
            }
            else if (uUretti && !(kg && !kg.value.trim()) && !yt) {
                /* Önerinin kaynağı yazılmaz; dil modelinin notu kalır. */
                et = "";
                if (u.not) uretimNot.textContent = "Not: " + tireSade(u.not);
            }
            else if (dikkat) { et = !v ? "Anlam boş: yazın ya da satırı çıkarın" : "Kontrol edin"; dikkatEt = true; }
            else if (duz) et = "Düzenlendi";
            /* Önerinin kaynağı (hafıza, dil modeli, kanıt, elle) yazılmaz. */
            else et = "";
            /* Yakın anlamla yeniden yazıldı: önceki anlam ve Geri Al. */
            if (u && u.durum === "bitti" && u.onceki && uUretti) {
                const ont = elYap("div", "dg-donem-onceki",
                    "Kaydedilen bir anlama yakın olduğu için yeniden yazıldı. Önceki: "
                    + donemAnlamGoster(kalipNe(), tireSade(u.onceki)) + " · ");
                const ga = elYap("button", "dg-baglanti", "Geri Al");
                ga.type = "button";
                ga.disabled = kilitli || da.dm === "calisiyor";
                ga.onclick = () => { const on = u.onceki; u.onceki = ""; anlamYaz(on); kaydet(); };
                ont.appendChild(ga);
                uretimNot.appendChild(ont);
            }
            /* Kaydedilmemiş satır kaydedilmiş bir anlama yakınsa uyarı. */
            const yakin = !x.kayitliMi() && v ? satirlar.find(o => o !== x && o.kayitliMi()
                && !YAKIN_TAMAM.has(anah + "|" + o.anah) && anlamYakin(v, o.anlam())) : null;
            yakinEl.textContent = "";
            if (yakin) {
                yakinEl.appendChild(document.createTextNode(
                    "Bu anlam, kaydedilen " + donemSayiGoster(yakin.kalipNe()) + " satırının anlamına («"
                    + donemAnlamGoster(yakin.kalipNe(), yakin.anlam()) + "») çok benziyor. İki kalıp "
                    + "farklı şeyler anlatıyorsa bu satırın anlam kutusunu farkı gösterecek biçimde "
                    + "düzeltin; aynı şeyi anlatıyorlarsa birini çıkarın. "));
                const tm = elYap("button", "dg-baglanti", "Farklılar, Uyarıyı Kaldır");
                tm.type = "button";
                tm.onclick = () => { YAKIN_TAMAM.add(anah + "|" + yakin.anah); boya(); };
                yakinEl.appendChild(tm);
            }
            yakinEl.hidden = !yakin;
            durumCip.classList.toggle("kayitli", et === "Kaydedildi");
            /* Kaydedilmiş satırda düğme "Kaydı Geri Al" (etiket "Kaydedildi"). */
            const kayitli = x.kayitliMi();
            kaydetBtn.disabled = kilitli || da.dm === "calisiyor" || kaydetBtn.dataset.gidiyor === "1"
                || (!kayitli && (!v || !!yt || (kg && !kg.value.trim())));
            kaydetBtn.textContent = kaydetBtn.dataset.gidiyor === "1" ? "Bekleyin"
                : kayitli ? "Kaydı Geri Al" : "Kaydet";
            kaydetBtn.classList.toggle("dg-donem-geri-al", kayitli);
            kaydetBtn.title = kayitli
                ? "Kaydı geri alır: hafıza kaydetmeden önceki hâline döner, satır yeniden düzenlenip kaydedilebilir."
                : "Bu satırı şimdi hafızaya kaydet. Kaydedilmemiş satırlardan anlamı buna yakın olanlar "
                  + "dil modeline yeniden yazdırılır.";
            hepsiDurum();
            durumCip.textContent = et; durumCip.hidden = !et;
            durumCip.classList.toggle("dikkat", dikkatEt);
            kontrolEl.textContent = yt ? "Kontrol: " + yt : "";
            kontrolEl.hidden = !yt;
        }
        const kaydet = () => {
            duzen[anah] = Object.assign(duzen[anah] || {}, {
                anlam: anlamAl(), kalip: kg ? kg.value : undefined, haric: Array.from(haric),
                deger_anlam: Object.assign({}, dgAnlam) });
            elleSay(); dgCiz(); boya(); if (degisti) degisti();
        };
        g.addEventListener("input", () => {
            kaydet();
            /* Silip boş bıraktı: bir süre bekle, sonra dil modeli yazar. */
            const kk = kalipNe();
            if (!g.value.trim() && kk) uretimSayac(anah, kk); else uretimVazgec(anah);
            boya();
        });
        if (kg) {
            let kgZ = null;
            kg.addEventListener("input", () => {
                kaydet();
                /* Elle yazılan kalıp: yazmayı bırakınca anlam boşsa yazdır. */
                clearTimeout(kgZ);
                kgZ = setTimeout(() => {
                    const kk = kg.value.trim().toUpperCase();
                    if (kk && !anlamAl().trim() && kg.isConnected) uretimBaslat(anah, kk);
                }, 1500);
            });
            /* Elle yazılan parça ayrılmamış bir grubun ikinci parçasıysa
               grup kendiliğinden birleşir (otoGrupla). */
            kg.addEventListener("change", () => {
                const g = grupOf(kg.value);
                if (g && !ayrikGruplar.has(g) && (grupUyeSatirlari(g).length > 1
                        || satirlar.some(x => satirKalibi(x) === g))) ciz(da.satirlar);
            });
        }
        cikBtn.onclick = () => {
            if (kilitli || da.dm === "calisiyor") return;
            duzen[anah] = Object.assign(duzen[anah] || {}, {
                anlam: anlamAl(), kalip: kg ? kg.value : undefined, cikar: true,
                haric: Array.from(haric), deger_anlam: Object.assign({}, dgAnlam) });
            const i = elleYeni.findIndex(e => e.id === anah);
            if (i !== -1) elleYeni.splice(i, 1);          // yeni elle satır: silinir
            ciz(da.satirlar);
            if (degisti) degisti();
        };
        x.dgAnlam = dgAnlam;
        x.detay = detay;
        x.turSec = turSec;
        x.boya = () => boya();
        x.kosullu = kosCikti;
        x.kosOneriYenile = kosOneriYenile;
        x.kosulHata = () => Object.values(kosMap).some(a => !!kosHata(a));
        x.satirCikti = () => ({
            kalip: String(kalipNe() || "").toUpperCase(), anlam: anlamAl().trim(),
            elle: !!r.elle, cikar: false, haric: Array.from(haric).sort(),
            deger_anlam: Object.assign({}, dgAnlam), ayrilan: ayrilanCikti(r, anah),
            zaman_tur: turSec.value, kosullu: kosCikti(),
            ozel_turler: r.birimli ? ozelTurler.map(y => ({ tur: y.tur, ad: y.ad, anlam: y.anlam,
                                                            yon: y.yon || "", bicim: y.bicim || "" })) : [] });
        x.imza = () => {
            const c = x.satirCikti();
            return JSON.stringify([c.kalip, c.anlam.replace(/\s+/g, " "), c.zaman_tur, c.haric,
                Object.entries(c.deger_anlam).sort(), Object.keys(c.ayrilan).sort(),
                Object.entries(c.kosullu).sort(), c.ozel_turler.map(y => [y.tur, y.ad, y.anlam, y.yon, y.bicim])]);
        };
        x.kayitliMi = () => KAYIT[anah] !== undefined && KAYIT[anah] === x.imza();
        /* KAYDET: satır onayı beklemeden hafızaya yazılır. toplu: Hepsini
           Kabul Et'ten (yakın anlamlar yeniden yazdırılmaz, mesaj toplu
           yazılır). Doner: Promise<{ok, mesaj}>. */
        x.kaydetIstek = toplu => {
            if (kilitli || da.dm === "calisiyor" || x.kayitliMi() || kaydetBtn.dataset.gidiyor === "1")
                return Promise.resolve({ ok: false, mesaj: "" });
            const satir = x.satirCikti();
            kaydetBtn.dataset.gidiyor = "1"; boya();
            return fetch(getWebAppBackendUrl("donem_kaydet"), {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ oturum_id: OTURUM_ID, satir })
            })
            .then(res => res.json())
            .then(d => {
                delete kaydetBtn.dataset.gidiyor;
                if (!(d && d.tamam)) {
                    const m = (d && (d.mesaj || d.hata)) || "Kaydedilemedi.";
                    if (!toplu) bilgiYaz(m, true);
                    boya(); return { ok: false, mesaj: m };
                }
                KAYIT[anah] = x.imza();
                KAYIT_ACIK.delete(anah);
                KAYIT_ANLAM[anah] = satir.anlam;
                x.kosOneriYenile();
                /* Geri almada yazılacak: bu karttaki İLK kayıttan önceki hâl. */
                if (ONCEKI[anah] === undefined && d.onceki) ONCEKI[anah] = d.onceki;
                let yakinlar = [];
                if (!toplu) {
                    /* YAKIN ANLAMLAR: kaydedilmemiş satırlardan anlamı bu
                       satıra yakın olanlar dil modeline yeniden yazdırılır
                       (kaydedilen anlamlar bağlam olarak gider). */
                    yakinlar = satirlar.filter(o => o !== x && !o.kayitliMi()
                        && o.anlam().trim() && anlamYakin(satir.anlam, o.anlam()));
                    yakinlar.forEach(o => {
                        const kk = String(o.kalipNe() || "").toUpperCase();
                        if (kk) uretimBaslat(o.anah, kk, true, o.anlam().trim());
                    });
                    bilgiYaz(donemSayiGoster(satir.kalip) + " kaydedildi." + (yakinlar.length
                        ? " Anlamı buna yakın " + ftBinlik(yakinlar.length) + " satır yeniden yazılıyor: "
                          + yakinlar.map(o => donemSayiGoster(o.kalipNe())).join(", ") + "." : ""), false);
                }
                satirlar.forEach(o => o.boya());
                if (degisti) degisti();
                return { ok: true, mesaj: "" };
            })
            .catch(() => {
                delete kaydetBtn.dataset.gidiyor;
                if (!toplu) bilgiYaz("Kaydedilemedi (bağlantı).", true);
                boya(); return { ok: false, mesaj: "bağlantı kurulamadı" };
            });
        };
        /* KAYDI GERİ AL: bu kartta kaydedildiyse hafıza kaydetmeden önceki
           hâline döner (yoktuysa silinir); hafızadan gelip bu kartta
           kaydedilmediyse hafızaya dokunulmaz, satır yeniden açılır. İki
           durumda da satır kaydedilmemiş sayılır, Kaydet yeniden açılır. */
        x.kaydiGeriAl = () => {
            if (kilitli || da.dm === "calisiyor" || kaydetBtn.dataset.gidiyor === "1") return;
            const ac = m => {
                delete KAYIT[anah]; KAYIT_ACIK.add(anah);
                bilgiYaz(m, false);
                satirlar.forEach(o => o.boya());
                if (degisti) degisti();
            };
            const onceki = ONCEKI[anah];
            if (!onceki) {
                ac(donemSayiGoster(kalipNe()) + " yeniden açıldı. Hafızadaki kaydı değişmedi; "
                   + "değiştirip yeniden kaydedin ya da Çıkar ile çıkarın.");
                return;
            }
            kaydetBtn.dataset.gidiyor = "1"; boya();
            fetch(getWebAppBackendUrl("donem_kayit_geri"), {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ oturum_id: OTURUM_ID, onceki })
            })
            .then(res => res.json())
            .then(d => {
                delete kaydetBtn.dataset.gidiyor;
                if (!(d && d.tamam)) {
                    bilgiYaz((d && (d.mesaj || d.hata)) || "Kayıt geri alınamadı.", true); boya(); return;
                }
                /* Hafıza önceki hâline döndü: kaydedilmiş anlam da o (yoktuysa silindi). */
                if (String(onceki.anlam || "").trim()) KAYIT_ANLAM[anah] = String(onceki.anlam).trim();
                else delete KAYIT_ANLAM[anah];
                delete ONCEKI[anah];
                ac(d.mesaj || (donemSayiGoster(kalipNe()) + " kaydı geri alındı."));
                x.kosOneriYenile();
            })
            .catch(() => { delete kaydetBtn.dataset.gidiyor; bilgiYaz("Kayıt geri alınamadı (bağlantı).", true); boya(); });
        };
        kaydetBtn.onclick = () => { if (x.kayitliMi()) x.kaydiGeriAl(); else x.kaydetIstek(false); };
        x.kalipNe = kalipNe;
        x.otoAnlam = otoAnlam;
        x.degerListesi = degerListesi;
        x.degerDurumu = degerDurumu;
        /* Tüm Parçalar'dan: bir değeri gruptan çıkar (dönem değil) ya da geri al. */
        x.degerCikar = (dg, cik) => {
            if (kilitli || da.dm === "calisiyor") return;
            delete ayrilanlar[dg];
            delete dgAnlam[dg];
            if (cik) ayrilanlar[dg] = { anlam: "", cikar: true };
            dgKaydet(); dgCiz(); boya();
            if (kg) elleSay(); else degerCiz(tdD, r.degerler || [], degerDurumu);
            birlikteCiz();
            if (degisti) degisti();
        };
        /* Dil modelinin yazdığı anlam: kutu hâlâ boşsa yazılır; tür
           kullanıcı değiştirmediyse dil modelininki olur. */
        x.uretimYaz = (d, zorla) => {
            if (zorla || !anlamAl().trim()) anlamYaz(tireSade(d.anlam || ""));
            /* Gruplanan satırdan gelen değer anlamı kalıbın anlamıyla aynı
               çıkıyorsa kendi anlamı sayılmaz (Kalıba Uyar olur). */
            let dgDegisti = false;
            Object.keys(dgAnlam).forEach(dg => {
                if (String(dgAnlam[dg]).trim() === String(otoAnlam(dg) || "").trim()) {
                    delete dgAnlam[dg]; dgDegisti = true;
                }
            });
            if (dgDegisti) { dgKaydet(); dgCiz(); }
            if (d.tur && !(duzen[anah] && duzen[anah].zaman_tur)
                    && DONEM_TURLERI.some(t => t[0] === d.tur)) {
                turSec.value = d.tur; turNotYaz();
                duzen[anah] = Object.assign(duzen[anah] || {}, { zaman_tur: d.tur });
            }
            kaydet(); sekmeSayilari();
        };
        if (KAYIT[anah] === undefined && r.kaynak === "hafiza" && dokunulmadi(r, anah) && !KAYIT_ACIK.has(anah))
            KAYIT[anah] = x.imza();
        if (!(anah in KAYIT_ANLAM) && r.kaynak === "hafiza" && String(r.oneri || "").trim())
            KAYIT_ANLAM[anah] = String(r.oneri).trim();
        dgCiz();
        satirlar.push(x);
        boya();
        /* İLK ÇİZİMDE ANLAM BOŞ: hemen yazdır (daha önce yazdırılmadıysa). */
        {
            const kk = kalipNe();
            const u = URETIM[anah];
            if (kk && !anlamAl().trim() && !(r.bekliyor && calisiyor) && !kilitli && !calisiyor
                    && (!u || u.kalip !== kk.toUpperCase() && u.kalip !== kk))
                setTimeout(() => uretimBaslat(anah, kk.toUpperCase()), 0);
        }
        tb.appendChild(tr);
        tb.appendChild(detay);
    }

    /* ÇIKARILANLAR: tablonun altında; tıklanınca satır geri gelir. */
    const cikKap = elYap("div", "dg-donem-cikanlar");
    const cikBas = elYap("span", "dg-donem-cikanlar-bas", "");
    const cikListe = elYap("span", "dg-donem-cikanlar-liste");
    cikKap.appendChild(cikBas);
    cikKap.appendChild(cikListe);
    sar.after(cikKap);
    cikKap.after(bilgiEl);
    function geriAl(anah) {
        if (kilitli || da.dm === "calisiyor") return;
        duzen[anah] = Object.assign(duzen[anah] || {}, { cikar: false });
        ciz(da.satirlar);
        const tr = tb.querySelector('tr[data-anahtar="' + CSS.escape(anah) + '"]');
        if (tr) { tr.scrollIntoView({ block: "nearest" }); const t = tr.querySelector("textarea"); if (t) t.focus(); }
        if (degisti) degisti();
    }
    /* ADAYLAR: adlarda bulunup tabloda olmayan bütün kalıplar, kalıp olma
       olasılığıyla (r.olasilik): Orta (dil modeli zaman bilgisi dedi ama
       emin değil), Düşük (dil modeli zaman bilgisi değil dedi), Yorumlanmadı
       (dil modeli bakamadı). Sıra: olasılık, sonra kolon sayısı. Üstteki
       çiplerle süzülür. "Tabloya Al" ile Kalıplar sekmesine geçer. */
    const OLASILIK = {
        orta: ["Orta", "Dil modeli zaman bilgisi dedi ama emin değil."],
        bakilmadi: ["Yorumlanmadı", "Dil modeli bu kalıba bakamadı."],
        dusuk: ["Düşük", "Dil modeli zaman bilgisi değil dedi."]
    };
    const OLASILIK_SIRA = { orta: 0, bakilmadi: 1, dusuk: 2 };
    const olasilikOf = r => OLASILIK[r.olasilik] ? r.olasilik : "orta";
    let adaySuzgec = "tumu";
    const olaNot = elYap("p", "dg-donem-pano-not",
        "Kolon adlarında bulunup tabloda olmayan bütün kalıplar, kalıp olma olasılığıyla. "
        + "Zaman bilgisi olanları tabloya alın; anlamını Kalıplar sekmesinde kontrol edersiniz. "
        + "Tabloya almadıklarınız kullanılmaz ve hafızaya yazılmaz.");
    const olaSuz = elYap("div", "dg-donem-aday-suz");
    const olaTablo = elYap("table", "dg-tablo dg-donem-olasi-tablo");
    const olaBasR = document.createElement("tr");
    ["Kalıp", "Adlarda Geçen", "Olasılık", "Dil Modeli", ""].forEach(h => olaBasR.appendChild(elYap("th", "", h)));
    const olaTh = document.createElement("thead");
    olaTh.appendChild(olaBasR);
    const olaTb = document.createElement("tbody");
    olaTablo.append(olaTh, olaTb);
    panolar.olasi.append(olaNot, olaSuz, olaTablo);
    function olasilariCiz() {
        olaTb.textContent = "";
        const k = kilitli || da.dm === "calisiyor";
        const say = { tumu: olasilar.length, orta: 0, bakilmadi: 0, dusuk: 0 };
        olasilar.forEach(c => { say[olasilikOf(c.r)]++; });
        if (adaySuzgec !== "tumu" && !say[adaySuzgec]) adaySuzgec = "tumu";
        olaSuz.textContent = "";
        [["tumu", "Tümü"], ["orta", "Orta Olasılık"], ["bakilmadi", "Yorumlanmadı"],
         ["dusuk", "Düşük Olasılık"]].forEach(([deg, ad]) => {
            if (deg !== "tumu" && !say[deg]) return;
            const b = elYap("button", "bolme-cip" + (adaySuzgec === deg ? " secili" : ""),
                            ad + " · " + ftBinlik(say[deg]));
            b.type = "button";
            b.onclick = () => { adaySuzgec = deg; olasilariCiz(); };
            olaSuz.appendChild(b);
        });
        olaSuz.hidden = !olasilar.length;
        const liste = olasilar
            .filter(c => adaySuzgec === "tumu" || olasilikOf(c.r) === adaySuzgec)
            .sort((a, b) => (OLASILIK_SIRA[olasilikOf(a.r)] - OLASILIK_SIRA[olasilikOf(b.r)])
                || ((b.r.kolon || 0) - (a.r.kolon || 0)) || String(a.r.kalip).localeCompare(String(b.r.kalip)));
        liste.forEach(c => {
            const ol = olasilikOf(c.r);
            const tr = elYap("tr", "dg-satir dg-donem-aday-" + ol);
            const tdK = elYap("td", "dg-kolon");
            tdK.appendChild(donemKalipEtiketi(c.r));
            tr.appendChild(tdK);
            const tdD = elYap("td", "dg-kisa-hucre");
            degerCiz(tdD, c.r.degerler || []);
            tr.appendChild(tdD);
            /* OLASILIK: rozet; kanıt yalnız dil modelinin saydığı örnek
               tanımlardan (uydurma yüzde yok). */
            const tdO = elYap("td", "dg-donem-olasilik-hucre");
            tdO.appendChild(elYap("span", "dg-donem-olasilik dg-donem-olasilik-" + ol, OLASILIK[ol][0]));
            tr.appendChild(tdO);
            /* DİL MODELİ: neden emin değil ya da neden dönem değil; önerdiği
               anlam varsa. */
            const tdN = elYap("td", "dg-donem-olasi-neden");
            const neden = c.r.soru ? tireSade(c.r.soru)
                : c.r.uyari ? tireSade(c.r.uyari)
                : c.r.not ? tireSade(c.r.not) : OLASILIK[ol][1];
            tdN.appendChild(elYap("div", "", neden));
            if (c.r.anlam) tdN.appendChild(elYap("div", "dg-donem-ornek",
                (ol === "dusuk" ? "Dil modelinin yorumu: " : "Önerilen anlam: ")
                + donemAnlamGoster(c.r.kalip, tireSade(c.r.anlam))));
            tr.appendChild(tdN);
            const tdB = elYap("td", "dg-ekle-hucre");
            const b = elYap("button", "dg-toplu-btn", "Tabloya Al");
            b.type = "button";
            b.disabled = k;
            b.onclick = () => { geriAl(c.anah); sekmeAc("kalip"); };
            tdB.appendChild(b);
            tr.appendChild(tdB);
            olaTb.appendChild(tr);
        });
        if (!olasilar.length) {
            const tr = elYap("tr", "dg-bos-tablo");
            const td = elYap("td", "", da.dm === "calisiyor"
                ? "Dil modeli kalıpları değerlendiriyor; tabloya girmeyenler burada görünecek."
                : "Adlarda bulunan bütün kalıplar tabloda.");
            td.colSpan = 5; tr.appendChild(td); olaTb.appendChild(tr);
        }
    }
    /* TÜM PARÇALAR: kolon adlarındaki bütün parçalar (yalnız rakamlar hariç;
       sayılı parça ve P_NN ikilisi de). Durum: Kalıp (tablodaki bir kalıbın
       kendisi), Kalıp değeri (tablodaki bir kalıbın değeri), Dönem değil
       (değer gruptan çıkarılmış), Aday (Adaylar ya da çıkarılanlar). Tek
       düğme: kalıplardaysa çıkarır, değilse kalıplara alır (Adaylar'daki
       kalıbı tabloya alır; hiçbir kalıba uymayanı kendisi olarak elle
       ekler, anlamını dil modeli yazar). Arama ve süzgeç; sayfa başına
       PARCA_SAYFA satır. */
    const PARCA_SAYFA = 150;
    let parcaAra = "", parcaSuz = "tumu", parcaGoster = PARCA_SAYFA;
    const parNot = elYap("p", "dg-donem-pano-not",
        "Kolon adlarındaki bütün parçalar, kaç kolonda geçtiğiyle. Kalıplarda olanı buradan "
        + "çıkarabilir, olmayanı kalıplara alabilirsiniz; anlamı boşsa dil modeli yazar. "
        + "Sayı içermeyen parçaların anlamı ayrıca bir sonraki adımda Ad Parçaları'nda da sorulur.");
    const parUst = elYap("div", "dg-donem-aday-suz dg-donem-parca-ust");
    const parAra = document.createElement("input");
    parAra.type = "search"; parAra.className = "ft-ara dg-donem-parca-ara";
    parAra.placeholder = "Parça ara";
    parAra.setAttribute("aria-label", "Parça ara");
    parAra.addEventListener("input", () => { parcaAra = parAra.value.trim().toUpperCase(); parcaGoster = PARCA_SAYFA; parcalariCiz(); });
    const parCipler = elYap("span", "dg-donem-parca-cipler");
    parUst.append(parAra, parCipler);
    const parTablo = elYap("table", "dg-tablo dg-donem-parca-tablo");
    const parBasR = document.createElement("tr");
    ["Parça", "Kolon", "Örnek Kolon", "Durum", ""].forEach(h => parBasR.appendChild(elYap("th", "", h)));
    const parTh = document.createElement("thead");
    parTh.appendChild(parBasR);
    const parTb = document.createElement("tbody");
    parTablo.append(parTh, parTb);
    const parDaha = elYap("button", "dg-toplu-btn dg-donem-parca-daha", "");
    parDaha.type = "button";
    parDaha.onclick = () => { parcaGoster += PARCA_SAYFA; parcalariCiz(); };
    panolar.parca.append(parNot, parUst, parTablo, parDaha);
    function parcaDurumHaritasi() {
        const h = new Map();
        satirlar.forEach(x => {
            const kal = String(x.kalipNe() || "").toUpperCase();
            if (kal) h.set(kal, { tip: "kalip", x });
            (x.degerListesi() || []).forEach(d => {
                if (h.has(d.deger)) return;
                h.set(d.deger, { tip: x.degerDurumu(d.deger) === "disi" ? "disi" : "deger", x });
            });
        });
        /* İKİ PARÇALI DEĞERİN PARÇALARI (H00_06'daki H00): kendi başına
           kalıp olmasa da kalıp değerinin içinde; "Kalıplarda" sayılır. */
        satirlar.forEach(x => (x.degerListesi() || []).forEach(d => {
            if (x.degerDurumu(d.deger) === "disi" || String(d.deger).indexOf("_") === -1) return;
            String(d.deger).split("_").forEach(pr => {
                if (!h.has(pr)) h.set(pr, { tip: "parca", x, deger: d.deger });
            });
        }));
        olasilar.concat(cikanlar).forEach(c => {
            if (!h.has(c.r.kalip)) h.set(c.r.kalip, { tip: "aday", c });
            (c.r.degerler || []).forEach(d => {
                if (!h.has(d.deger)) h.set(d.deger, { tip: "aday", c });
                String(d.deger).split("_").forEach(pr => { if (!h.has(pr)) h.set(pr, { tip: "aday", c }); });
            });
        });
        return h;
    }
    function parcaEylem(p, du) {
        if (kilitli || da.dm === "calisiyor") return;
        if (!du) {
            /* Ayrılmamış bir grubun parçası grubuyla alınır. */
            if (p.grup && grupUyeleri(p.grup).length > 1 && !ayrikGruplar.has(p.grup)) {
                grupAl(p.grup); sekmeAc("parca"); return;
            }
            elleEkle(p.parca); sekmeAc("parca"); return;
        }
        if (du.tip === "kalip") { du.x.cikBtn.onclick(); return; }
        if (du.tip === "deger") {
            const etkin = (du.x.degerListesi() || []).filter(d => du.x.degerDurumu(d.deger) !== "disi");
            if (etkin.length <= 1) du.x.cikBtn.onclick(); else du.x.degerCikar(p.parca, true);
            parcalariCiz(); return;
        }
        if (du.tip === "disi") { du.x.degerCikar(p.parca, false); parcalariCiz(); return; }
        if (du.tip === "parca") return;
        if (du.tip === "aday") { geriAl(du.c.anah); sekmeAc("parca"); }
    }
    function parcalariCiz() {
        parTb.textContent = "";
        const k = kilitli || da.dm === "calisiyor";
        const h = parcaDurumHaritasi();
        const icinde = p => { const du = h.get(p.parca); return !!du && (du.tip === "kalip" || du.tip === "deger" || du.tip === "parca"); };
        const say = { tumu: parcalar.length, ic: 0, dis: 0 };
        parcalar.forEach(p => { if (icinde(p)) say.ic++; else say.dis++; });
        parCipler.textContent = "";
        [["tumu", "Tümü"], ["ic", "Kalıplarda"], ["dis", "Kalıplarda Olmayan"]].forEach(([deg, ad]) => {
            const b = elYap("button", "bolme-cip" + (parcaSuz === deg ? " secili" : ""), ad + " · " + ftBinlik(say[deg]));
            b.type = "button";
            b.onclick = () => { parcaSuz = deg; parcaGoster = PARCA_SAYFA; parcalariCiz(); };
            parCipler.appendChild(b);
        });
        /* GRUPLU LİSTE: iki ya da daha çok üyeli grup bir başlık satırı ve
           altında üyeleri; grup aramaya ya da süzgece bir üyesi uyarsa
           görünür. Sıra: kolon sayısı (grubun kesin kolon sayısı). */
        const uyar = p => (!parcaAra || p.parca.includes(parcaAra)
                           || (p.grup && p.grup.includes(parcaAra)))
            && (parcaSuz === "tumu" || (parcaSuz === "ic") === icinde(p));
        const grupUye = new Map();
        parcalar.forEach(p => { if (p.grup) (grupUye.get(p.grup) || grupUye.set(p.grup, []).get(p.grup)).push(p); });
        const ogeler = [];
        const gorulenGrup = new Set();
        parcalar.forEach(p => {
            const uyeler = p.grup ? grupUye.get(p.grup) : null;
            if (uyeler && uyeler.length > 1) {
                if (gorulenGrup.has(p.grup)) return;
                gorulenGrup.add(p.grup);
                if (!uyeler.some(uyar)) return;
                ogeler.push({ grup: p.grup, uyeler: uyeler.slice().sort((x, y) => x.parca.localeCompare(y.parca, "tr", { numeric: true })),
                              kolon: Number(p.grup_kolon || 0) });
            } else if (uyar(p)) ogeler.push({ p, kolon: p.kolon });
        });
        ogeler.sort((x, y) => (y.kolon - x.kolon)
            || String(x.grup || x.p.parca).localeCompare(String(y.grup || y.p.parca)));
        const parcaSatiri = (p, uye) => {
            const du = h.get(p.parca) || null;
            const tr = elYap("tr", "dg-satir" + (du && du.tip !== "aday" && du.tip !== "disi" ? " dg-donem-parca-ic" : "")
                                   + (uye ? " dg-donem-parca-uye" : ""));
            tr.appendChild(elYap("td", "dg-kolon", p.parca));
            tr.appendChild(elYap("td", "dg-donem-parca-sayi", ftBinlik(p.kolon)));
            tr.appendChild(elYap("td", "dg-donem-parca-ornek", (p.ornekler || []).slice(0, 2).join(", ")));
            const durumMetni = !du ? ""
                : du.tip === "kalip" ? "Kalıp"
                : du.tip === "deger" ? "Kalıp değeri: " + donemSayiGoster(du.x.kalipNe())
                : du.tip === "disi" ? "Dönem değil: " + donemSayiGoster(du.x.kalipNe())
                : du.tip === "parca" ? "Kalıp değerinin parçası: " + du.deger + " (" + donemSayiGoster(du.x.kalipNe()) + ")"
                : "Adaylarda: " + donemSayiGoster(du.c.r.kalip);
            tr.appendChild(elYap("td", "dg-donem-olasi-neden", durumMetni));
            const tdB = elYap("td", "dg-ekle-hucre");
            const ic = du && (du.tip === "kalip" || du.tip === "deger");
            const b = elYap("button", "dg-toplu-btn" + (ic ? " dg-donem-cikar" : ""), ic ? "Kalıplardan Çıkar" : "Kalıplara Al");
            b.type = "button";
            b.disabled = k || (du && du.tip === "parca");
            if (du && du.tip === "parca") b.hidden = true;
            b.title = ic ? (du.tip === "deger"
                    ? p.parca + " " + donemSayiGoster(du.x.kalipNe()) + " kalıbında dönem değil sayılır."
                    : p.parca + " dönem bilgisinden çıkarılır.")
                : du && du.tip === "aday" ? donemSayiGoster(du.c.r.kalip) + " tabloya alınır."
                : du && du.tip === "disi" ? p.parca + " yeniden " + donemSayiGoster(du.x.kalipNe()) + " kalıbının değeri olur."
                : uye && !ayrikGruplar.has(p.grup)
                  ? p.parca + " grubuyla birlikte alınır (" + donemSayiGoster(p.grup) + "). Yalnız bazı "
                    + "parçaları almak için Kalıplar'da grubu Ayır'ın."
                  : p.parca + " kalıp olarak eklenir; anlamını dil modeli yazar.";
            b.onclick = () => parcaEylem(p, du);
            tdB.appendChild(b);
            tr.appendChild(tdB);
            parTb.appendChild(tr);
        };
        const grupSatiri = o => {
            const uyeDurum = o.uyeler.map(p => h.get(p.parca) || null);
            const icSay = uyeDurum.filter(du => du && (du.tip === "kalip" || du.tip === "deger" || du.tip === "parca")).length;
            const parcaIc = uyeDurum.length > 0 && uyeDurum.every(du => du && du.tip === "parca");
            const ayri = grupUyeSatirlari(o.grup);
            const grupTabloda = satirlar.some(x => satirKalibi(x) === o.grup);
            const adaylar = new Set(uyeDurum.filter(du => du && du.tip === "aday").map(du => du.c.anah));
            const tumIc = icSay === o.uyeler.length;
            const tr = elYap("tr", "dg-satir dg-donem-parca-grup" + (tumIc ? " dg-donem-parca-ic" : ""));
            const tdA = elYap("td", "dg-kolon");
            tdA.appendChild(elYap("div", "", donemSayiGoster(o.grup)));
            tdA.appendChild(elYap("div", "dg-donem-grup-alt", "grup · " + ftBinlik(o.uyeler.length) + " parça"));
            tr.appendChild(tdA);
            const tdK = elYap("td", "dg-donem-parca-sayi", ftBinlik(o.kolon));
            tdK.title = "Üyelerin geçtiği farklı kolon sayısı";
            tr.appendChild(tdK);
            tr.appendChild(elYap("td", "dg-donem-parca-ornek", o.uyeler.map(p => p.parca).join(", ")));
            const durum = parcaIc ? "Kalıp değerlerinin parçası (" + donemSayiGoster(uyeDurum[0].x.kalipNe()) + ")"
                : grupTabloda ? "Grup kalıbı tabloda"
                : ayri.length ? "Ayrıldı: " + ftBinlik(ayri.length) + " parça ayrı kalıp"
                : tumIc ? "Kalıplarda"
                : icSay ? ftBinlik(icSay) + " / " + ftBinlik(o.uyeler.length) + " parça kalıplarda"
                : adaylar.size === 1 ? "Adaylarda: " + donemSayiGoster(uyeDurum.find(du => du && du.tip === "aday").c.r.kalip)
                : "";
            tr.appendChild(elYap("td", "dg-donem-olasi-neden", durum));
            const tdB = elYap("td", "dg-ekle-hucre");
            const cikar = grupTabloda || (tumIc && !ayri.length);
            const b = elYap("button", "dg-toplu-btn" + (cikar ? " dg-donem-cikar" : ""),
                            cikar ? "Grubu Kalıplardan Çıkar" : ayri.length ? "Grup Olarak Al" : "Grubu Kalıplara Al");
            b.type = "button";
            b.disabled = k || parcaIc;
            /* İki parçalı değerlerin içindeki parçalar: değeri Kalıplar'da yönetin. */
            if (parcaIc) b.hidden = true;
            b.title = cikar ? "Grubun bütün parçaları dönem bilgisinden çıkarılır."
                : ayri.length ? "Ayrı alınan parçalar tek kalıpta (" + donemSayiGoster(o.grup) + ") birleşir."
                : "Grup tek kalıp olarak (" + donemSayiGoster(o.grup) + ") eklenir; anlamını dil modeli yazar.";
            b.onclick = () => {
                if (kilitli || da.dm === "calisiyor") return;
                if (cikar) grubuCikar(o);
                else { grupAl(o.grup); sekmeAc("parca"); }
                parcalariCiz();
            };
            tdB.appendChild(b);
            tr.appendChild(tdB);
            parTb.appendChild(tr);
            o.uyeler.forEach(p => parcaSatiri(p, true));
        };
        /* Sayfa: PARCA_SAYFA parça; grup bölünmez. */
        let gosterilen = 0, kalan = 0;
        ogeler.forEach(o => {
            const n = o.grup ? o.uyeler.length : 1;
            if (gosterilen >= parcaGoster) { kalan += n; return; }
            gosterilen += n;
            if (o.grup) grupSatiri(o); else parcaSatiri(o.p, false);
        });
        if (!ogeler.length) {
            const tr = elYap("tr", "dg-bos-tablo");
            const td = elYap("td", "", parcalar.length ? "Aramaya uyan parça yok." : "Kolon adlarında parça bulunmadı.");
            td.colSpan = 5; tr.appendChild(td); parTb.appendChild(tr);
        }
        parDaha.hidden = kalan <= 0;
        parDaha.textContent = "Daha fazla göster · " + ftBinlik(kalan) + " parça daha";
    }
    function cikanlariCiz() {
        cikListe.textContent = "";
        cikBas.textContent = "Çıkarılanlar · " + ftBinlik(cikanlar.length);
        cikBas.appendChild(bolmeBilgiSimgesi("Çıkarılan kalıplar dönem bilgisi olarak kullanılmaz "
            + "ve hafızaya yazılmaz. Hafızadan gelen kalıp onaylayınca hafızadan da silinir. "
            + "Geri almak için üzerine tıklayın.", "Çıkarılanlar"));
        const k = kilitli || da.dm === "calisiyor";
        cikanlar.forEach(c => {
            const b = elYap("button", "dg-parca-oge dg-donem-geri", c.r.kalip);
            b.type = "button";
            b.disabled = k;
            const anlam = (duzen[c.anah] && duzen[c.anah].anlam !== undefined)
                ? duzen[c.anah].anlam : (c.r.anlam || "");
            const hafizada = c.r.kaynak === "hafiza";
            b.title = (anlam ? tireSade(anlam) + "\n" : "")
                + (c.r.soru ? "Dil modeli: " + tireSade(c.r.soru) + "\n" : "")
                + (hafizada ? "Onaylayınca hafızadan silinir.\n" : "") + "Tıklayın: geri al";
            /* Hafızadan gelen kalıp onayla hafızadan da silinir: görünür yazılır. */
            if (hafizada) b.appendChild(elYap("span", "dg-donem-sil-not", "hafızadan silinecek"));
            b.onclick = () => geriAl(c.anah);
            cikListe.appendChild(b);
        });
        cikKap.hidden = !cikanlar.length;
    }

    /* Özet satırı ve sekme sayıları. */
    function sekmeSayilari() {
        sekmeDugme.kalip.lastChild.textContent = ftBinlik(satirlar.length);
        sekmeDugme.olasi.lastChild.textContent = ftBinlik(olasilar.length);
        sekmeDugme.parca.lastChild.textContent = ftBinlik(parcalar.length);
        const tur = { pencere: 0, nokta: 0, birim: 0, olcu: 0, kolona: 0 };
        satirlar.forEach(x => {
            if (x.r.bekliyor && da.dm === "calisiyor") return;     // tür henüz yok
            if (x.r.birimli) { tur.kolona++; return; }             // tür kolona göre
            if (x.turSec && tur[x.turSec.value] !== undefined) tur[x.turSec.value]++;
        });
        const parca = [ftBinlik(satirlar.length) + " kalıp"];
        const turParca = [[tur.pencere, "pencere"], [tur.nokta, "zaman noktası"],
                          [tur.birim, "zaman birimi"], [tur.olcu, "zaman ölçüsü"],
                          [tur.kolona, "türü kolona göre"]]
            .filter(([n]) => n).map(([n, a]) => ftBinlik(n) + " " + a);
        if (turParca.length) parca[0] += " (" + turParca.join(", ") + ")";
        const bekleyen = satirlar.filter(x => x.r.bekliyor && da.dm === "calisiyor").length;
        if (bekleyen) parca.push(ftBinlik(bekleyen) + " yorumlanıyor");
        if (olasilar.length) parca.push(ftBinlik(olasilar.length) + " aday");
        if (cikanlar.length) parca.push(ftBinlik(cikanlar.length) + " çıkarılan");
        ozetEl.textContent = parca.join(" · ");
    }
    /* Elle eklenen ve henüz kaydedilmemiş satırlar (yoklamada kalır). */
    const elleYeni = [];
    let elleSayac = 0;
    function ciz(liste) {
        otoGrupla(liste);
        tb.textContent = "";
        satirlar.length = 0;
        cikanlar.length = 0;
        olasilar.length = 0;
        katilanlar.length = 0;
        const kat = {};               // aile -> [{r, anah}]
        (liste || []).forEach(r => {
            const anah = anahtarOf(r);
            if (r.aile && aileTablodaMi(r.aile) && katildi(r, anah)) {
                (kat[r.aile] = kat[r.aile] || []).push({ r, anah });
                katilanlar.push({ r, anah });
            }
        });
        (liste || []).forEach(r0 => {
            const anah = anahtarOf(r0);
            if (katilanlar.some(c => c.anah === anah)) return;
            /* Aile satırı katılan yazılışların değerleriyle çizilir. */
            const k = kat[r0.kalip];
            const r = k ? Object.assign({}, r0, {
                degerler: (r0.degerler || []).concat(...k.map(c => c.r.degerler || [])),
                yazilislar: ((r0.yazilislar || []).length ? r0.yazilislar : [r0.kalip])
                    .concat(k.map(c => c.r.kalip)),
                katilan: k }) : r0;
            if (cikarildi(r, anah)) {
                if (r.olasi) olasilar.push({ r, anah });     // olası: tabloya alınmadı
                else if (!r.elle) cikanlar.push({ r, anah }); // elle satır çıkarılınca silinir
            } else satirCiz(r);        });
        elleYeni.forEach(satirCiz);
        gruplariDiz();
        if (!satirlar.length) {
            const tr = elYap("tr", "dg-bos-tablo");
            const td = elYap("td", "", da.dm === "calisiyor"
                ? "Dil modeli kalıpları değerlendiriyor; dönem olduğu kesin olanlar burada görünecek."
                : olasilar.length && !cikanlar.length
                    ? "Kesin zaman bilgisi bulunmadı; Adaylar sekmesindeki kalıplardan zaman bilgisi olanları tabloya alın."
                    : (liste || []).length
                        ? "Bütün satırlar çıkarıldı; onaylarsanız dönem bilgisi boş kalır."
                        : "Dönem bilgisi taşıyan parça bulunmadı.");
            td.colSpan = 4; tr.appendChild(td); tb.appendChild(tr);
        }
        cikanlariCiz();
        olasilariCiz();
        parcalariCiz();
        sekmeSayilari();
        durumEl.textContent = da.not ? tireSade(da.not) : "";
        durumEl.hidden = !durumEl.textContent;
    }
    /* GRUPLAR: yalnız sayıları farklı parçalar (H00, H06, H12) bir grup;
       grubun kalıbı parçanın "grup" alanı (arka uç donem.parca_gruplari:
       sayılardan biri başta sıfırla yazılıyorsa basamak sayısı sabit,
       H<N2>; H000 ayrı grup). Grubun kolon sayısı kesin (grup_kolon).
       GRUPLAMA KENDİLİĞİNDEN: aynı gruptan iki ya da daha çok parça ayrı
       satırda kalmaz, grubun kalıbında birleşir; tek parça alınırken de
       grubuyla alınır. Kullanıcı grubu Ayır'la böldüyse (ayrikGruplar)
       parçalar ayrı durur; grup yeniden alınınca birleşir. */
    const ayrikGruplar = new Set(da.ayrik || []);
    const grupOf = k => {
        const p = parcalar.find(x => x.parca === String(k || "").trim().toUpperCase());
        return (p && p.grup) || null;
    };
    const grupUyeleri = g => parcalar.filter(p => p.grup === g);
    const satirKalibi = x => String(x.kalipNe() || "").trim().toUpperCase();
    /* Ayrı ayrı duran aynı grup parçaları (yer tutucusuz kalıp satırları). */
    const grupUyeSatirlari = g => satirlar.filter(x => {
        const k = satirKalibi(x);
        return k && !k.includes("<") && grupOf(k) === g;
    });
    /* Veri düzeyinde birleştirme: üyeler {anah, kalip, anlam, tur}. Üye
       satırlar kalkar (elle olanlar silinir, hafızadan gelenler
       Çıkarılanlar'a geçer); grubun kalıbı tek satır olur (tabloda varsa
       ona katılır). Üyelerin yazılı anlamları değerlerin kendi anlamı, en
       çok seçilen tür grubun türü olur. */
    function grupBirlestir(g, uyeler) {
        const dgYeni = {}, turSay = {};
        uyeler.forEach(u => {
            if (u.anlam) dgYeni[u.kalip] = u.anlam;
            if (u.tur) turSay[u.tur] = (turSay[u.tur] || 0) + 1;
            duzen[u.anah] = Object.assign(duzen[u.anah] || {}, { cikar: true });
            const i = elleYeni.findIndex(e => e.id === u.anah);
            if (i !== -1) elleYeni.splice(i, 1);
        });
        const tur = Object.keys(turSay).sort((a, b) => turSay[b] - turSay[a])[0];
        ayrikGruplar.delete(g);
        const var_ = satirlar.find(x => satirKalibi(x) === g)
            || elleYeni.find(e => e.kalip === g && !(duzen[e.id] && duzen[e.id].cikar));
        if (var_ && var_.anah) {
            /* Tablodaki grup satırına katılırken kalıbın anlamından çıkanla
               aynı anlam kendi anlamı sayılmaz. */
            Object.keys(dgYeni).forEach(dg => {
                if (String(var_.otoAnlam(dg) || "").trim() === dgYeni[dg]) delete dgYeni[dg];
            });
            duzen[var_.anah] = Object.assign(duzen[var_.anah] || {}, {
                deger_anlam: Object.assign({}, var_.dgAnlam, dgYeni) });
        } else if (var_) {
            var_.deger_anlam = Object.assign({}, var_.deger_anlam || {}, dgYeni);
        } else {
            const id = "elle-yeni-" + (++elleSayac);
            elleYeni.push({ kalip: g, anlam: "", oneri: "", elle: true, grup: true, id,
                            degerler: adlardaBul(g), ornekler: [], deger_anlam: dgYeni,
                            zaman_tur: tur || "pencere" });
            if (tur) duzen[id] = { zaman_tur: tur };
        }
    }
    /* ciz'den önce: ayrılmamış bir grubun iki ya da daha çok parçası ayrı
       satırdaysa (elle yazıldı, hafızadan geldi) ya da grubun kalıbı
       tablodayken bir parçası ayrı satırdaysa kendiliğinden birleşir. */
    function otoGrupla(liste) {
        const uye = new Map();
        const ekle = (r, anah) => {
            const dz = duzen[anah] || {};
            if (dz.cikar) return;
            const k = String((r.elle && dz.kalip !== undefined ? dz.kalip : r.kalip) || "").trim().toUpperCase();
            const g = k && !k.includes("<") ? grupOf(k) : null;
            if (!g || ayrikGruplar.has(g)) return;
            const anlam = String(dz.anlam !== undefined ? dz.anlam : (r.anlam || "")).trim();
            (uye.get(g) || uye.set(g, []).get(g)).push({ anah, kalip: k, anlam, tur: dz.zaman_tur || r.zaman_tur || "" });
        };
        (liste || []).forEach(r => { if (!cikarildi(r, anahtarOf(r))) ekle(r, anahtarOf(r)); });
        elleYeni.forEach(r => ekle(r, r.id));
        /* Grubun kalıbı zaten tablodaysa tek parça da ona katılır. */
        const grupTablodaMi = g => (liste || []).some(r => r.kalip === g && !cikarildi(r, anahtarOf(r)))
            || elleYeni.some(e => e.kalip === g && !(duzen[e.id] && duzen[e.id].cikar));
        const katilan = [];
        uye.forEach((u, g) => {
            if (u.length > 1 || grupTablodaMi(g)) {
                grupBirlestir(g, u);
                katilan.push(u.map(x => x.kalip).join(", ") + " → " + donemSayiGoster(g));
            }
        });
        if (katilan.length) bilgiYaz("Aynı gruptan parçalar grubunda birleşti: " + katilan.join("; ")
            + ". Yanlışsa grubun satırında «Ayır».", false);
    }
    /* KALIPLAR SEKMESİNDE AYRIK GRUP: Ayır ile bölünen grubun ayrı
       satırları yan yana dizilir; üstlerinde grup başlığı ve "Grup Olarak
       Al" (yeniden birleştirir). */
    function gruplariDiz() {
        const gruplar = new Map();
        satirlar.forEach(x => {
            const k = satirKalibi(x);
            const g = k && !k.includes("<") ? grupOf(k) : null;
            if (g) (gruplar.get(g) || gruplar.set(g, []).get(g)).push(x);
        });
        gruplar.forEach((uyeler, g) => {
            if (uyeler.length < 2) return;
            const bas = elYap("tr", "dg-donem-grup-bas");
            const td = elYap("td", "");
            td.colSpan = 4;
            td.appendChild(elYap("span", "dg-donem-grup-ad", donemSayiGoster(g) + " grubu"));
            td.appendChild(elYap("span", "dg-donem-grup-ozet",
                "ayrıldı: " + uyeler.map(satirKalibi).join(", ") + " ayrı satırlarda"));
            const b = elYap("button", "dg-toplu-btn dg-donem-grupla", "Grup Olarak Al");
            b.type = "button";
            b.disabled = kilitli || da.dm === "calisiyor";
            b.title = "Tek kalıpta (" + donemSayiGoster(g) + ") birleşir; her parçanın yazılı anlamı o "
                + "değerin kendi anlamı olarak kalır.";
            b.onclick = () => grupAl(g);
            td.appendChild(b);
            bas.appendChild(td);
            tb.insertBefore(bas, uyeler[0].tr);
            let son = bas;
            uyeler.forEach(x => {
                x.tr.classList.add("dg-donem-grup-uye");
                son.after(x.tr); son = x.tr;
                if (x.detay) { son.after(x.detay); son = x.detay; }
            });
        });
    }
    /* GRUBU AL: ayrı satırlar varsa birleşir; üyelerin hepsi tek bir
       adayın değeriyse o aday tabloya alınır; değilse grubun kalıbı tek
       satır olarak eklenir (anlamını dil modeli yazar). */
    function grupAl(g) {
        if (kilitli || da.dm === "calisiyor") return;
        const ayri = grupUyeSatirlari(g);
        const h = parcaDurumHaritasi();
        const uyeDurum = grupUyeleri(g).map(p => h.get(p.parca) || null);
        const adaylar = new Set(uyeDurum.filter(du => du && du.tip === "aday").map(du => du.c.anah));
        const icSay = uyeDurum.filter(du => du && (du.tip === "kalip" || du.tip === "deger")).length;
        if (!ayri.length && !icSay && adaylar.size === 1 && uyeDurum.every(du => du && du.tip === "aday")) {
            ayrikGruplar.delete(g);
            geriAl([...adaylar][0]);
            return;
        }
        grupBirlestir(g, ayri.map(x => ({ anah: x.anah, kalip: satirKalibi(x), anlam: x.anlam().trim(),
                                          tur: x.turSec.value })));
        ciz(da.satirlar);
        bilgiYaz(donemSayiGoster(g) + " grubu tek satırda (" + grupUyeleri(g).map(p => p.parca).join(", ")
            + ")." + (ayri.length ? " Ayrı satırların anlamları değerlerin kendi anlamı oldu." : ""), false);
        if (degisti) degisti();
    }
    /* AYIR: yer tutuculu satır değerlerine ayrılır. Her değer kendi
       satırında, kendi anlamıyla (kendi anlamı yoksa kalıbın anlamından
       çıkan); tür satırın türü. Satır tablodan kalkar; değerlerin grupları
       ayrık sayılır (kendiliğinden yeniden birleşmez). */
    function ayir(x) {
        if (kilitli || da.dm === "calisiyor") return;
        const anlam = x.anlam().trim(), tur = x.turSec.value;
        const degerler = x.degerListesi().filter(d => x.degerDurumu(d.deger) !== "disi");
        degerler.forEach(d => { const g = grupOf(d.deger); if (g) ayrikGruplar.add(g); });
        duzen[x.anah] = Object.assign(duzen[x.anah] || {}, { cikar: true });
        const i = elleYeni.findIndex(e => e.id === x.anah);
        if (i !== -1) elleYeni.splice(i, 1);
        degerler.forEach(d => {
            const id = "elle-yeni-" + (++elleSayac);
            const an = x.dgAnlam[d.deger] !== undefined ? x.dgAnlam[d.deger]
                : (anlam ? x.otoAnlam(d.deger) : "");
            elleYeni.push({ kalip: d.deger, anlam: "", oneri: "", elle: true, id, degerler: [],
                            ornekler: [], zaman_tur: tur });
            duzen[id] = { zaman_tur: tur, anlam: an };
        });
        ciz(da.satirlar);
        bilgiYaz(donemSayiGoster(satirKalibi(x)) + " değerlerine ayrıldı: "
            + degerler.map(d => d.deger).join(", ") + ". Yeniden grup olarak almak için "
            + "«Grup Olarak Al».", false);
        if (degisti) degisti();
    }
    /* GRUBU KALIPLARDAN ÇIKAR: grup kalıbı satırı ve grubun ayrı satırları
       tablodan çıkar; başka bir kalıbın değeri olan üyeler o kalıpta dönem
       değil sayılır (Tüm Parçalar'daki tek parça eylemiyle aynı). */
    function grubuCikar(o) {
        if (kilitli || da.dm === "calisiyor") return;
        const gs = satirlar.find(x => satirKalibi(x) === o.grup);
        if (gs) gs.cikBtn.onclick();
        o.uyeler.forEach(p => {
            const du = parcaDurumHaritasi().get(p.parca);
            if (du && (du.tip === "kalip" || du.tip === "deger")) parcaEylem(p, du);
        });
        bilgiYaz(donemSayiGoster(o.grup) + " grubu dönem bilgisinden çıkarıldı.", false);
    }
    function elleEkle(kalip) {
        if (kilitli || da.dm === "calisiyor") return;
        const k = (kalip || "").toUpperCase();
        /* Çıkarılanlardaysa geri alınır; tabloda zaten varsa o satıra gidilir. */
        const cik = k && (cikanlar.find(c => c.r.kalip === k) || olasilar.find(c => c.r.kalip === k));
        if (cik) { geriAl(cik.anah); return; }
        const var_ = k && satirlar.find(x => (x.kg ? x.kg.value.trim().toUpperCase() : x.r.kalip) === k);
        if (var_) { (var_.g || var_.kg).focus(); var_.tr.scrollIntoView({ block: "nearest" }); return; }
        const id = "elle-yeni-" + (++elleSayac);
        elleYeni.push({ kalip: k, anlam: "", oneri: "", elle: true, id, degerler: [], ornekler: [] });
        ciz(da.satirlar);
        const son = tb.querySelector('tr[data-anahtar="' + id + '"]');
        if (son) {
            const hedef = son.querySelector(k ? "textarea" : ".dg-donem-kalip-giris");
            if (hedef) hedef.focus();
            son.scrollIntoView({ block: "nearest" });
        }
        if (degisti) degisti();
    }
    const ekleBtn = elYap("button", "dg-toplu-btn dg-donem-ekle", "+ Dönem Kalıbı Ekle");
    ekleBtn.type = "button";
    ekleBtn.title = "Listede olmayan bir dönem kalıbını anlamıyla ekleyin. Kolon adlarında geçmese de "
        + "onaylayınca hafızaya yazılır ve sonraki çalışmalarda kullanılır.";
    ekleBtn.onclick = () => elleEkle("");
    bilgiEl.after(ekleBtn);
    /* HEPSİNİ KABUL ET: kaydedilmemiş bütün satırlar sırayla kaydedilir
       (Kaydet ile aynı; yakın anlamlar yeniden yazdırılmaz). Kaydedilemeyen
       satırlar (anlam boş, yer tutucu geçersiz) nedeniyle yazılır. */
    const hepsiBtn = elYap("button", "dg-toplu-btn dg-donem-hepsi", "Hepsini Kabul Et");
    hepsiBtn.type = "button";
    hepsiBtn.title = "Tablodaki kaydedilmemiş bütün satırları şimdiki anlam ve türleriyle hafızaya kaydeder.";
    let hepsiGidiyor = false;
    /* Boş elle satır (kalıp ve anlam boş) sayılmaz. */
    const kaydedilecekler = () => satirlar.filter(x => !x.kayitliMi()
        && !(x.kg && !x.kg.value.trim() && !x.anlam().trim()));
    function hepsiDurum() {
        const bekleyen = kaydedilecekler();
        hepsiBtn.disabled = kilitli || da.dm === "calisiyor" || hepsiGidiyor || !bekleyen.length;
        hepsiBtn.textContent = hepsiGidiyor ? "Kaydediliyor" : "Hepsini Kabul Et"
            + (bekleyen.length ? " · " + ftBinlik(bekleyen.length) : "");
    }
    hepsiBtn.onclick = () => {
        if (kilitli || da.dm === "calisiyor" || hepsiGidiyor) return;
        const liste = kaydedilecekler();
        if (!liste.length) return;
        hepsiGidiyor = true; hepsiDurum();
        const olmayan = [];
        let ok = 0;
        liste.reduce((zincir, x) => zincir.then(() => x.kaydetIstek(true).then(s => {
            if (s.ok) ok++;
            else olmayan.push(donemSayiGoster(x.kalipNe() || "(boş kalıp)") + (s.mesaj ? ": " + s.mesaj : ""));
        })), Promise.resolve()).then(() => {
            hepsiGidiyor = false; hepsiDurum();
            bilgiYaz(ftBinlik(ok) + " satır kaydedildi." + (olmayan.length
                ? " Kaydedilemeyen " + ftBinlik(olmayan.length) + " satır: " + olmayan.join("; ") + "." : ""),
                olmayan.length > 0);
            satirlar.forEach(o => o.boya());
            if (degisti) degisti();
        });
    };
    ekleBtn.after(hepsiBtn);

    ciz(da.satirlar);

    let yoklamaSayisi = 0;
    function yokla() {
        if (kilitli || !document.body.contains(tb)) return;
        if (yoklamaSayisi++ > 300) return;
        fetch(getWebAppBackendUrl("donem_alani") + "?oturum_id=" + encodeURIComponent(OTURUM_ID))
            .then(r => r.json())
            .then(d => {
                const yeni = d && d.donem;
                if (!yeni) return setTimeout(yokla, 3000);
                if (tb.contains(document.activeElement)) {
                    yoklamaSayisi--;
                    return setTimeout(yokla, 1500);
                }
                da.dm = yeni.dm; da.not = yeni.not || ""; da.satirlar = yeni.satirlar;
                ciz(yeni.satirlar);
                kilitDurumu();
                if (yeni.dm === "calisiyor") setTimeout(yokla, 3000);
                if (degisti) degisti();
            })
            .catch(() => setTimeout(yokla, 8000));
    }
    if (da.dm === "calisiyor") setTimeout(yokla, 3000);

    function kilitDurumu() {
        const k = kilitli || da.dm === "calisiyor";
        ekleBtn.disabled = k;
        cikListe.querySelectorAll("button").forEach(b => { b.disabled = k; });
        olaTb.querySelectorAll("button").forEach(b => { b.disabled = k; });
        parTb.querySelectorAll("button").forEach(b => { b.disabled = k; });
        hepsiDurum();
    }
    kilitDurumu();
    /* Elle satır: kalıp ve anlam ikisi de boşsa yok sayılır. */
    const bosElle = x => x.kg && !x.kg.value.trim() && !x.anlam().trim();
    const acik = () => satirlar.filter(x => !bosElle(x));
    return {
        /* Tabloda kalanlar + çıkarılanlar (cikar: true). */
        deger: () => acik().map(x => ({
            kalip: x.kg ? x.kg.value.trim() : x.r.kalip, anlam: x.anlam().trim(),
            elle: !!x.r.elle, cikar: false, haric: Array.from(x.haric),
            deger_anlam: Object.assign({}, x.dgAnlam), ayrilan: ayrilanCikti(x.r, x.anah),
            zaman_tur: x.turSec.value, kosullu: x.kosullu() }))
            .concat(katilanlar.map(c => ({
                kalip: c.r.kalip, aileye_kat: true, cikar: false, elle: false, anlam: "" })))
            .concat(cikanlar.map(c => ({
                kalip: c.r.kalip, cikar: true, elle: false,
                ayrilan: ayrilanCikti(c.r, c.anah),
                zaman_tur: (duzen[c.anah] && duzen[c.anah].zaman_tur) || c.r.zaman_tur || "pencere",
                haric: (duzen[c.anah] && duzen[c.anah].haric) || c.r.haric || [],
                deger_anlam: (duzen[c.anah] && duzen[c.anah].deger_anlam) || c.r.deger_anlam || {},
                kosullu: (duzen[c.anah] && duzen[c.anah].kosullu) || c.r.kosullu || {},
                anlam: ((duzen[c.anah] && duzen[c.anah].anlam !== undefined)
                    ? duzen[c.anah].anlam : (c.r.anlam || "")).trim() }))),
        /* Onayı durduran: tabloda kalan satırda anlam (elle satırda kalıp) boş. */
        eksik: () => acik().filter(x => !x.anlam().trim() || (x.kg && !x.kg.value.trim())).length,
        /* Onayı durduran: anlamdaki yer tutucu geçersiz. */
        kontrol: () => acik().filter(x => (x.anlam().trim() && x.yt())
            || Object.values(x.dgAnlam || {}).some(v => donemYerTutucuHatasi("", v))
            || (x.kosulHata && x.kosulHata())).length,
        /* Onayı durduran: tabloda kaydedilmemiş satır (her satır «Kaydet»
           ile tek tek kaydedilir; hafızadan gelen, dokunulmamış satır
           kaydedilmiş sayılır). */
        kaydedilmemis: () => acik().filter(x => !x.kayitliMi()).length,
        /* Ayır ile bölünen gruplar (onayda tablonun geçmişine yazılır). */
        ayrik: () => [...ayrikGruplar],
        /* Onayı durduran: elle yazılan kalıp kolon adlarında geçmiyor. */
        adlardaYok: () => satirlar.filter(x => x.kg && x.kg.value.trim()
                                          && !adlardaBul(x.kg.value).length).length,
        bos: () => satirlar.filter(x => !x.kg && !x.anlam().trim()).length,
        kilitle: k => {
            kilitli = k;
            const c = da.dm === "calisiyor";
            satirlar.forEach(x => { x.g.disabled = k || c; x.cikBtn.disabled = k || c; x.boya();
                                    if (x.turSec) x.turSec.disabled = k || c;
                                    if (x.detay) x.detay.querySelectorAll("input, button")
                                        .forEach(i => { i.disabled = k || c || i.closest(".dg-durum-disi") !== null
                                            && i.tagName === "INPUT"; });
                                    if (x.kg) x.kg.disabled = k || c;
                                    x.tr.querySelectorAll(".dg-birlikte-cip, .dg-donem-aile-btn")
                                        .forEach(b => { b.disabled = k || c; }); });
            kilitDurumu();
        },
        bekliyor: () => da.dm === "calisiyor"
    };
}

/* ==================== Aralık Önerileri kartı ====================
   SFA'nın aralık ve eksik işareti önerileri; sözlük tanımları kartıyla
   aynı düzen: satır başına "Uygula" kutusu, Tümünü Seç /
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
    const ac = elYap("button", "secim-onay ikincil", "Dağılım ve SFA'yı Aç");
    ac.type = "button";
    ac.onclick = () => dgAc("dagilim");
    const birincil = elYap("button", "secim-onay dg-birincil", alan.buton || "Kararları Onayla");
    birincil.type = "button";
    dugmeler.appendChild(ac);
    dugmeler.appendChild(birincil);
    kart.appendChild(dugmeler);
    /* Analiz alanının altındaki ikiz düğme buna basar (analizAltGuncelle). */
    SFA_ONAY_DUGMESI = birincil;

    function kilitle(evet) {
        kart.classList.toggle("kilitli", evet);
        birincil.disabled = evet;
        const ikiz = document.getElementById("analiz-sfa-onay");
        if (ikiz && SFA_ONAY_DUGMESI === birincil) ikiz.disabled = evet;
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
                + "Değişkenler > Dağılım ve SFA bölümüne düşer; beklemeden onaylarsanız kalan "
                + "değişkenlerde kural tabanlı karar geçerli olur.";
        else if (d && d.durum === "bitti")
            durum.textContent = "Yapay zekâ " + biten.toLocaleString("tr-TR") + " değişken için "
                + "karar verdi. Kararları Değişkenler > Dağılım ve SFA bölümünde inceleyip değiştirebilirsiniz.";
        else
            durum.textContent = "Kararlar Değişkenler > Dağılım ve SFA bölümünde; inceleyip "
                + "değiştirebilirsiniz.";
        hata.hidden = !(d && d.hata);
        metinYaz(hata, (d && d.hata) || "");
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
                    if (dgDagilimAcik() && ARALIK.liste && !ARALIK.acik) {
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
   EKRAN SIRASI:

     1. yan yana İKİ SEÇİM KUTUSU  (Önerilen / Özel) - sayfanın merkezi
     2. seçilenin KISA ÖZETİ
     3. tek cümlelik gerekçe
     4. [Detayları göster]  - VARSAYILAN KAPALI
     5. tek birincil düğme

   Uzun anlatım (gerekçe maddeleri, kısıtlar, terim karşılıkları)
   4. maddedeki açılır alanda.

   UYARILAR DETAYDA DEĞİL, görünür: "test seti yalnızca 33 satır"
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

/* İşlev, taslağın öneriden ayrılıp ayrılmadığını söylüyor - kaydetme
   yolu buna bağlı. */
function bolmeOzellestirildi() { return bfDegisti(); }

/* ---- TEK LİSTE, ÖNERİLEN DEĞERLER ÖNCEDEN SEÇİLİ ----

   TEK liste: her satırda seçenekler çip olarak yan
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
    /* ÖNERİ GEREKÇESİ ayrı bir açılır düğme değil:
       rozetin yanındaki "i" simgesinde. */
    const o = alan.oneri || {};
    const maddeler = (o.gerekce || []).map(x => "• " + tireSade(x));
    const gerekce = [o.ozet, maddeler.join("\n")].filter(Boolean).join("\n\n");
    if (gerekce) sag.appendChild(bolmeBilgiSimgesi(gerekce, "Neden bu ayarlar önerildi"));
    bas.appendChild(sag);
    kutu.appendChild(bas);

    const a = BF.alan;
    /* HEDEF ORANI ÇUBUKTA: "Hedef Dağılımı: Korunsun"
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
        /* TAM AD, KISALTMA YOK. Parça yüzdeyle
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

/* Satır görünür mü?
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
           Bölme Kolonu. Kolon Rolleri adımında belirlendi. */
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
            p.appendChild(metinYaz(document.createElement("span"), satir));
        });
        tip.appendChild(p);
    });
    kap.appendChild(tip);
    /* Tıklama da açar (dokunmatik ekran): odak simgede kalır. */
    kap.onclick = (e) => { e.stopPropagation(); kap.focus(); };
    /* Aşağıya sığmazsa simgenin ÜSTÜNE açılır;
       sağ kenar simgenin sağına hizalı, ekrandan taşmaz. */
    /* UZUN METİN KAYDIRILABİLİR. Balonun
       yüksekliği sınırlı ve kendi içinde kayıyor (style.css .bolme-tip).
        Kapanma kısa bir gecikmeyle yapılıyor, fare balona
       girerse iptal ediliyor. Tekerlek balonun içindeyken yalnızca
       balonu kaydırıyor; balon açıkken sayfa kayarsa (simge yerinden
       oynar) balon simgeye yeniden hizalanıyor. */
    let kapat = null;
    const acikMi = () => tip.style.display === "block";
    const yerlestir = () => {
        /* Hesap ekran pikseliyle; konum tasarım pikseline çevrilerek yazılır. */
        const z = ekranOlcegi();
        const r = kap.getBoundingClientRect();
        tip.style.display = "block";
        const en = Math.min(tip.offsetWidth * z, window.innerWidth - 16);
        const boy = tip.offsetHeight * z;
        let sol = Math.min(r.right - en, window.innerWidth - en - 8);
        sol = Math.max(sol, 8);
        const altYer = window.innerHeight - r.bottom - 8;
        let ust = (boy <= altYer || r.top < boy + 8) ? r.bottom + 6 : r.top - boy - 6;
        ust = Math.max(8, Math.min(ust, window.innerHeight - boy - 8));
        tip.style.left = (sol / z) + "px";
        tip.style.top = (ust / z) + "px";
    };
    const kaydirinca = (e) => {
        if (e.target === tip || tip.contains(e.target)) return;
        if (!kap.isConnected) return gizle();
        if (acikMi()) yerlestir();
    };
    /* SİMGE SAYFADAN KALKARSA BALON DA KALKAR. */
    let bekci = null;
    /* BALON SAYFA GÖVDESİNDE AÇILIR. Açılınca body'ye taşınır, kapanınca geri
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
        clearInterval(bekci);
        bekci = setInterval(() => { if (!kap.isConnected) gizle(); }, 300);
    };
    const gizle = () => {
        clearTimeout(kapat);
        clearInterval(bekci);
        tip.style.display = "";
        if (tip.parentNode !== kap) kap.appendChild(tip);
        window.removeEventListener("scroll", kaydirinca, true);
    };
    /* Balon simgenin içinde değil: fare balona geçince kapanmasın,
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


   Üç biçim:
     secenekler <= CIP_EN_COK      -> çip şeridi
     secenekler >  CIP_EN_COK      -> açılır liste (OOT / Test dönemi)
     tip yuzde / sayi              -> hazır çipler + "Özel" -> sayı kutusu

   "Özel" çipi SEÇENEĞİ SINIRLAMIYOR, sadece gizliyor: kullanıcı 1-99
   arasında ne isterse yazabiliyor. Hazır çipler yalnızca sık kullanılan değere tek
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
    if (aciklama) b.title = duzMetin(aciklama);
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

    /* TEK SEÇENEK ya da sabit: salt okunur çip. */
    if (k.sabit || secenekler.length === 1) {
        const kutu = elYap("div", "bolme-cipler");
        const secili = secenekler.find(o => bfKiyasDeger(ad, o.anahtar) === deger)
            || secenekler[0];
        kutu.appendChild(elYap("span", "bolme-cip secili salt", secili.etiket));
        return bfCipKabi(kutu, not);
    }

    /* UZUN LİSTE -> açılır liste, yalnızca seçenek sayısı fazla
       olduğunda: OOT / Test dönemi 11 seçenek. */
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
   anında güncelleniyor. */
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
*/
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
   VARSAYILAN KAPALI ve SOL PANELİN İÇİNDE. */
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
   İsteyen buradan okur. */
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
*/
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
        metinYaz(btn, alan.buton || "Bu Ayarları Seç");
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
       veriyor. */
    const gecmisten = !!(blok && blok.kilit);

    BOLME.kart = kart;
    BOLME.govde = govde;
    BOLME.alan = alan;
    BOLME.blok = blok || null;
    BOLME.durumEl = durumEl;
    BOLME.onayBtn = null;
    BOLME.gonderildi = false;
    /* AÇILIR ALANLAR VARSAYILAN KAPALI. */
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
        metinYaz(oz, alan.ozet);
        kart.appendChild(oz);
    }

    /* ---- DEĞİŞKEN LİSTESİ ----
       Teyit SOHBETTE yapılıyor:
       Sağ panel yalnızca açıklama gösteriyor; gözden geçirme ve süreç
       dışı işaretleme burada. Açıklama ve işaret DEĞİŞTİĞİ ANDA
       kaydedilir (panelin kullandığı uçların aynısı), düğme yalnızca
       adımı ilerletir. */
    const dg = alan.degiskenler || null;
    /* EXCEL İNDİRME ŞERİDİ - listenin ÜSTÜNDE, Excel simgesiyle.
       KAYDEDİLENE KADAR GİZLİ: kaydedilmemiş bir liste, kullanıcının henüz vermediği kararı dosyaya yazmak
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

        /* ARAMA · TİP · SIRALAMA TEK SATIRDA. Burada yalnızca değişken, tip, sözlük
           tanımı ve süreç dışı kararı var. */
        const filtreKap = elYap("div", "dg-filtreler");

        const ara = document.createElement("input");
        ara.type = "search";
        ara.className = "dg-arama";
        ara.placeholder = "Değişken adı veya tanımda ara";
        ara.setAttribute("aria-label", "Değişken adı veya tanımda ara");
        filtreKap.appendChild(ara);

        /* TİP SÜZGECİ: "Tip: Tümü" ve listedeki
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

        /* TOPLU SÜREÇ DIŞI. Düğmeler FİLTREDE
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
            /* HEDEF / KİMLİK / DÖNEM KİLİTLİ: Kolon Rolleri adımında
               seçildiler; süreç dışı bırakılmaları modeli hedefsiz ya da
               bölmeyi kimliksiz bırakırdı. Kutu gizlenmiyor, KİLİTLİ
               gösteriliyor ve sebebi ipucunda yazıyor - "neden
               işaretleyemiyorum" sorusu ekranda cevaplanmış oluyor. */
            if (sat.disi_kilitli) {
                kutu.disabled = true;
                kutu.title = duzMetin(sat.disi_kilit_sebebi || "");
                tdI.title = kutu.title;
                tr.classList.add("dg-rol-kilitli");
            }
            else if (sat.disi_sebebi) {
                /* Otomatik işaretlenmiş (tek değerli): kilitli değil,
                   neden işaretli geldiği ipucunda yazıyor. */
                kutu.title = duzMetin(sat.disi_sebebi);
            }
            /* SÜREÇ DIŞI SATIR ÇİZİLİR: satırın üstü
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
                    if (oz && d.ozet) metinYaz(oz, d.ozet);
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
    metinYaz(onayBtn, alan.buton || "Devam Et");
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
        /* liste yalnizca kartin
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
                GonderimSonucu eski kartı, rozetini
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
       yanında. */
    rozetYuvasinaEkle(blok, excelSerit.el);
    sohbetKaydir();
    if (gecmisten) return;

    yeniOdak = onayBtn;

    /* Kart cizildi: kullanicinin bakacagi yer sag panel. */
    if (alan.hedef) analizSekmeAc(alan.hedef, true);
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

function rozetiBasligaTasi(blok, el, kap0) {
    if (!el || !blok) return;
    /* KART KENDI BASLIK SATIRINI ÇİZDİYSE rozet orada kalır: yanında
       başlık var, tek başına bir satır kaplamıyor.
       el.isConnected: başlık satırı karta eklenmediyse rozet hâlâ
       DOM dışında duruyor demektir. */
    if (el.isConnected) return;
    /* kap0: kartın yerinde değiştirildiği kap (adimKabiAl sondaki bloğa bakar). */
    const kap = kap0 ? (kap0.closest(".alt-bolum") || kap0.closest(".adim-blok") || kap0) : adimKabiAl(blok);
    /* Gruplu blokta kap zaten .alt-bolum, içinde tek .alt-bas var;
       tekli blokta kap bloğun kendisi ve yuva .blok-bas içinde. */
    const yuva = kap && kap.querySelector(
        ".alt-bas .alt-rozet, .blok-bas .alt-rozet");
    if (yuva) yuva.appendChild(el);
}

/* ==================== 02.1 Veri Profili kartı ====================
   Üstte sayılar (satır, incelenen, sorunsuz, bilgi notu olan, kararınızı
   bekleyen, üretime girmeyen), altında eksik değer dağılımı, kontroller
   tablosu (Kontrol, Neye Bakıldı, Bulunan, Ne Olacak) ve hedef dağılımı.
   Bulunan sayıya basınca kolonlar açılır (kolon, açıklama, bulgu). Karar
   isteyen kontrollerde (Neredeyse Sabit, Dönemde Boş ya da Sabit) her
   kolon için Tut ya da Çıkar seçilir; karar kartın altındaki düğmeyle
   gider. Bütün sayılar tablonun tamamından. */
function pfYuzde(x) {
    if (x === null || x === undefined || x === "") return BOS_SIMGE;
    const v = Number(x);
    if (!isFinite(v)) return BOS_SIMGE;
    const y = Math.round(v * 10000) / 100;
    return "%" + (Number.isInteger(y) ? String(y) : String(y).replace(".", ","));
}

/* Aynı içerikli kolon grupları: her grubun başında grup satırı (kaç kolon,
   dil modelinin önerisi ve gerekçesi), altında üyeler. Karar modunda her
   üyede "Kalsın" seçeneği (grupta tek seçim); seçilmeyenler çıkar.
   Kilitli kartta Kaldı ya da Çıkarıldı yazar. */
function pfAyniTablosu(gruplar, secim, oneri, kararModu, kart, cizenler, ciz) {
    const it = elYap("table", "dg-tablo pf-ic-tablo pf-ayni-tablo");
    const icg = document.createElement("colgroup");
    ["pf-i-ad", "pf-i-acik", "pf-i-oneri", "pf-i-karar"].forEach(c => {
        const col = document.createElement("col"); col.className = c; icg.appendChild(col);
    });
    it.appendChild(icg);
    const ith = elYap("tr");
    ["Kolon", "Açıklama", "Dil Modeli", kararModu ? "Kalsın" : "Sonuç"].forEach(b => ith.appendChild(elYap("th", "", b)));
    const ithead = elYap("thead"); ithead.appendChild(ith); it.appendChild(ithead);
    const itb = elYap("tbody");
    gruplar.forEach((g, gi) => {
        const bt = elYap("tr", "pf-ayni-grup");
        const btd = elYap("td");
        btd.colSpan = 4;
        const bb = elYap("div", "pf-ayni-grup-bas");
        bb.appendChild(elYap("b", "", "Grup " + ftBinlik(gi + 1)));
        bb.appendChild(elYap("span", "pf-ayni-grup-sayi", ftBinlik(g.uyeler.length) + " kolon, değerleri birebir aynı"));
        btd.appendChild(bb);
        if (g.gerekce) {
            const ger = elYap("div", "pf-ayni-gerekce");
            ger.textContent = (g.kaynak === "dil modeli" ? "Dil modelinin önerisi " + g.oneri + ": " : "")
                + tireSade(g.gerekce);
            btd.appendChild(ger);
        }
        bt.appendChild(btd);
        itb.appendChild(bt);
        g.uyeler.forEach(u => {
            const r = elYap("tr", "pf-ayni-uye");
            r.appendChild(elYap("td", "pf-kolon-ad", u.ad));
            r.appendChild(elYap("td", "pf-kolon-acik", u.aciklama || BOS_SIMGE));
            const oTd = elYap("td", "pf-ayni-oneri");
            if (u.ad === g.oneri && g.kaynak === "dil modeli") oTd.appendChild(elYap("span", "pf-ayni-cip", "Önerilen"));
            else if (u.ad === g.oneri) oTd.appendChild(elYap("span", "pf-ayni-cip pasif", "Öneri alınamadı"));
            r.appendChild(oTd);
            const kTd = elYap("td", "pf-karar-hucre");
            if (kararModu) {
                const et = elYap("label", "pf-ayni-sec");
                const rd = document.createElement("input");
                rd.type = "radio";
                rd.name = "pf-ayni-" + g.id + "-" + Math.random().toString(36).slice(2, 7);
                rd.value = u.ad;
                rd.onchange = () => {
                    if (kart.classList.contains("kilitli")) return;
                    secim[g.id] = u.ad;
                    ciz();
                };
                et.append(rd, elYap("span", "", "Kalsın"));
                kTd.appendChild(et);
                cizenler.push(() => {
                    const kalir = secim[g.id] === u.ad;
                    rd.checked = kalir;
                    rd.disabled = kart.classList.contains("kilitli");
                    r.classList.toggle("kalir", kalir);
                    r.classList.toggle("cikar", !kalir);
                });
            } else {
                const kalir = (g.secim || g.oneri) === u.ad;
                kTd.appendChild(elYap("span", "pf-karar-sonuc " + (kalir ? "tut" : "cikar"), kalir ? "Kaldı" : "Çıkarıldı"));
                r.classList.toggle("kalir", kalir);
                r.classList.toggle("cikar", !kalir);
            }
            r.appendChild(kTd);
            itb.appendChild(r);
        });
    });
    it.appendChild(itb);
    const kap = elYap("div", "pf-ic-kap pf-ayni-kap");
    kap.appendChild(it);
    return kap;
}

const PF_NE_OLACAK_SINIF = { girmez: "pf-sonuc-girmez", karar: "pf-sonuc-karar", bilgi: "pf-sonuc-bilgi" };

function profilKartiEkle(alan, blok) {
    const kart = elYap("div", "secim-kart pf-kart");
    const kararModu = !!alan.karar_bekliyor && !(blok && blok.kilit);

    /* Karar durumu: kolon -> "tut" | "cikar". Bir kolon iki karar
       kontrolünde birden geçebilir; iki satır aynı kararı gösterir. */
    const kararlar = {};
    const kararCizenler = [];
    (alan.kontroller || []).filter(k => k.sonuc === "karar")
        .forEach(k => (k.kolonlar || []).forEach(c => { kararlar[c.ad] = c.karar || "tut"; }));
    const kararCiz = () => kararCizenler.forEach(f => f());
    /* Aynı içerikli gruplar: grup id -> kalacak kolon (dil modeli önerisi
       ya da önceki seçim). */
    const ayniSecim = {};
    const ayniOneri = {};
    (alan.kontroller || []).forEach(k => (k.gruplar || []).forEach(g => {
        ayniSecim[g.id] = g.secim || g.oneri;
        ayniOneri[g.id] = g.oneri;
    }));

    /* Başlık + i */
    const bas = elYap("div", "pf-bas");
    bas.appendChild(elYap("b", "pf-baslik", "Veri Profili"));
    const h = alan.haric || {};
    const disari = [];
    if (h.hedef) disari.push("hedef (" + h.hedef + ")");
    if (h.kimlik) disari.push("kimlik (" + h.kimlik + ")");
    if (h.donem) disari.push("dönem (" + h.donem + ")");
    const disariMetni = (disari.length ? disari.join(", ") + " kolonları" : "")
        + (h.surec_disi ? (disari.length ? " ve " : "") + "süreç dışı bırakılan "
                          + ftBinlik(h.surec_disi) + " kolon" : "");
    const bilgi = [
        "Modelleme tablosundaki her kolon tablonun tamamı üzerinden incelenir; örneklem kullanılmaz, sayımlar kesindir.",
        "Kontrollerin sonucu üç türlüdür. Değişken üretimine girmez: kolondan değişken üretilmez ve kolon "
            + tireSade(alan.dusme_atif || "") + " adımında veri setinden çıkarılır. Kararınıza bırakılır: kolonu siz tutar ya da çıkarırsınız. Bilgi için gösterilir: kolon üretime girer, bulgu yalnız bilmeniz için.",
        disariMetni ? "İncelemeye alınmayanlar: " + disariMetni + "." : "",
        alan.kayit ? "Profil tablosunun tamamı: " + alan.kayit : ""
    ].filter(Boolean).join("\n\n");
    bas.appendChild(bolmeBilgiSimgesi(bilgi, "Veri Profili"));
    kart.appendChild(bas);

    /* Sayılar */
    const karolar = elYap("div", "pf-karolar");
    const karo = (etiket, deger, sinif) => {
        const k = elYap("div", "pf-karo" + (sinif ? " " + sinif : ""));
        k.appendChild(elYap("div", "pf-karo-deger", ftBinlik(deger)));
        k.appendChild(elYap("div", "pf-karo-etiket", etiket));
        karolar.appendChild(k);
    };
    karo("Satır", alan.satir);
    karo("İncelenen Kolon", alan.kolon);
    karo("Sorunsuz", alan.temiz, Number(alan.temiz) ? "tamam" : "");
    karo("Bilgi Notu Olan", alan.bilgi || 0, Number(alan.bilgi) ? "bilgi" : "");
    if (kararModu) karo("Kararınızı Bekleyen", alan.bekleyen || 0, Number(alan.bekleyen) ? "karar" : "");
    karo("Üretime Girmeyen", alan.kusurlu, Number(alan.kusurlu) ? "sorun" : "");
    karolar.style.setProperty("--pf-karo-sayi", String(karolar.children.length));
    kart.appendChild(karolar);
    if (alan.esik_notu) kart.appendChild(elYap("div", "pf-not pf-esik-notu", alan.esik_notu));

    /* Türler */
    const tr = alan.turler || {};
    const turParca = [["sayısal", "sayısal"], ["kategorik", "kategorik"], ["tarih", "tarih"]]
        .filter(([a]) => Number(tr[a] || 0) > 0)
        .map(([a, ad]) => ftBinlik(tr[a]) + " " + ad);
    if (turParca.length) {
        const ts = elYap("div", "pf-satir");
        ts.appendChild(elYap("span", "pf-satir-ad", "Türler"));
        ts.appendChild(elYap("span", "", turParca.join(" · ")));
        kart.appendChild(ts);
    }

    /* Eksik değer dağılımı */
    const e = alan.eksik || {};
    const es = alan.eksik_esik || {};
    const azY = pfYuzde(es.az), asY = pfYuzde(es.asiri);
    const dilimler = [
        ["yok", "Eksik yok", Number(e.yok || 0)],
        ["az", azY + " ve altı", Number(e.az || 0)],
        ["orta", azY + " ile " + asY + " arası", Number(e.orta || 0)],
        ["asiri", asY + " üstü", Number(e.asiri || 0)]
    ];
    const top = dilimler.reduce((t, d) => t + d[2], 0);
    const eb = elYap("div", "pf-bolum");
    const ebBas = elYap("div", "pf-bolum-bas");
    ebBas.appendChild(elYap("span", "pf-bolum-ad", "Eksik Değer Oranına Göre Kolonlar"));
    eb.appendChild(ebBas);
    if (top > 0) {
        const cubuk = elYap("div", "pf-cubuk");
        cubuk.setAttribute("role", "img");
        cubuk.setAttribute("aria-label", dilimler.map(d => d[1] + ": " + ftBinlik(d[2]) + " kolon").join(", "));
        dilimler.forEach(([a, ad, n]) => {
            if (!n) return;
            const p = elYap("span", "pf-dilim pf-" + a);
            p.style.flexGrow = String(n);
            p.title = ad + ": " + ftBinlik(n) + " kolon (" + pfYuzde(n / top) + ")";
            cubuk.appendChild(p);
        });
        eb.appendChild(cubuk);
        const lj = elYap("div", "pf-lejant");
        dilimler.forEach(([a, ad, n]) => {
            const l = elYap("span", "pf-lejant-oge" + (n ? "" : " sifir"));
            l.appendChild(elYap("span", "pf-renk pf-" + a));
            l.appendChild(elYap("span", "", ad));
            l.appendChild(elYap("b", "", ftBinlik(n)));
            lj.appendChild(l);
        });
        eb.appendChild(lj);
        if (alan.eksik_maks_kolon && Number(alan.eksik_maks) > 0) {
            const en = elYap("div", "pf-not");
            metinYaz(en, "Eksik değeri olan kolon: **" + ftBinlik(alan.eksik_kolon) + "**. En çok eksik olan: **"
                + alan.eksik_maks_kolon + "** (" + pfYuzde(alan.eksik_maks) + ").");
            eb.appendChild(en);
        }
    }
    kart.appendChild(eb);

    /* Kontroller */
    const kb = elYap("div", "pf-bolum");
    const kbBas = elYap("div", "pf-bolum-bas");
    kbBas.appendChild(elYap("span", "pf-bolum-ad", "Kontroller"));
    kb.appendChild(kbBas);
    const tablo = elYap("table", "dg-tablo pf-tablo");
    const cg = document.createElement("colgroup");
    ["pf-k-ad", "pf-k-kural", "pf-k-bulunan", "pf-k-sonuc"].forEach(c => {
        const col = document.createElement("col"); col.className = c; cg.appendChild(col);
    });
    tablo.appendChild(cg);
    const thead = elYap("thead");
    const htr = elYap("tr");
    ["Kontrol", "Neye Bakıldı", "Bulunan", "Ne Olacak"].forEach(b => htr.appendChild(elYap("th", "", b)));
    thead.appendChild(htr);
    tablo.appendChild(thead);
    const tbody = elYap("tbody");

    const kararDugmesi = (ad) => {
        const grup = elYap("div", "pf-karar");
        grup.setAttribute("role", "group");
        grup.setAttribute("aria-label", ad + " kararı");
        const btnler = [["tut", "Tut"], ["cikar", "Çıkar"]].map(([d, etiket]) => {
            const b = elYap("button", "pf-karar-btn pf-karar-" + d, etiket);
            b.type = "button";
            b.onclick = () => {
                if (kart.classList.contains("kilitli")) return;
                kararlar[ad] = d;
                kararCiz();
            };
            grup.appendChild(b);
            return [d, b];
        });
        kararCizenler.push(() => btnler.forEach(([d, b]) => {
            const secili = kararlar[ad] === d;
            b.classList.toggle("secili", secili);
            b.setAttribute("aria-pressed", secili ? "true" : "false");
        }));
        return grup;
    };

    (alan.kontroller || []).forEach(k => {
        /* SATIR RENGİ: yeşil sorunsuz (bulgu yok), sarı dikkat (kararınıza
           bırakılan ya da bilgi notu), kırmızı üretime girmez, gri
           uygulanmadı. Açılan liste satırı da aynı renkte, girintili. */
        const nBul = Number(k.sayi || 0);
        const renk = k.uygulandi === false ? "pf-r-pasif" : !nBul ? "pf-r-tamam"
            : k.sonuc === "girmez" ? "pf-r-sorun" : "pf-r-dikkat";
        const satir = elYap("tr", "pf-kontrol " + renk + (k.uygulandi === false ? " pf-uygulanmadi" : ""));
        satir.appendChild(elYap("td", "pf-kontrol-ad", k.ad));
        satir.appendChild(elYap("td", "pf-kural", k.kural));
        const bulunan = elYap("td", "pf-sonuc");
        const neOlacak = elYap("td", "pf-ne-olacak");
        satir.append(bulunan, neOlacak);
        const n = Number(k.sayi || 0);
        const birim = k.birim || "kolon";

        if (k.uygulandi === false) {
            const u = elYap("span", "pf-durum pasif");
            u.append(elYap("span", "pf-durum-ikon", "○"), elYap("span", "", "Uygulanmadı"));
            bulunan.appendChild(u);
            neOlacak.appendChild(elYap("span", "pf-sebep", k.sebep || ""));
            tbody.appendChild(satir);
            return;
        }
        /* Bulgu yoksa "Ne Olacak" sönük: renk yalnız bulunan kolon varken. */
        /* Bulgu yoksa yapılacak bir şey yok: "İşlem yok" (sönük). */
        neOlacak.appendChild(n ? elYap("span", "pf-ne " + (PF_NE_OLACAK_SINIF[k.sonuc] || ""), k.ne_olacak || "")
                               : elYap("span", "pf-ne pf-sonuc-sessiz", "İşlem yok"));
        if (!n) {
            const ok = elYap("span", "pf-durum tamam");
            ok.append(elYap("span", "pf-durum-ikon", "✓"), elYap("span", "", "Yok"));
            bulunan.appendChild(ok);
            tbody.appendChild(satir);
            return;
        }
        const tur = k.sonuc === "girmez" ? "sorun" : (k.sonuc === "karar" ? "karar" : "bilgi");
        const dg = elYap("button", "pf-durum " + tur);
        dg.type = "button";
        dg.setAttribute("aria-expanded", "false");
        dg.append(elYap("span", "pf-durum-ikon", tur === "bilgi" ? "i" : "!"),
                  elYap("span", "", ftBinlik(n) + " " + birim), elYap("span", "pf-ok", "▾"));
        bulunan.appendChild(dg);

        const detay = elYap("tr", "pf-detay " + renk);
        detay.hidden = true;
        const td = elYap("td");
        td.colSpan = 4;
        const kararli = k.sonuc === "karar";
        const gruplu = (k.gruplar || []).length > 0;
        if (kararli && kararModu) {
            const ust = elYap("div", "pf-toplu");
            ust.appendChild(elYap("span", "pf-toplu-not", "Bu kontroldeki bütün kolonlar için:"));
            [["tut", "Hepsini Tut"], ["cikar", "Hepsini Çıkar"]].forEach(([d, et]) => {
                const b = elYap("button", "dg-toplu-btn", et);
                b.type = "button";
                b.onclick = () => {
                    if (kart.classList.contains("kilitli")) return;
                    (k.kolonlar || []).forEach(c => { kararlar[c.ad] = d; });
                    kararCiz();
                };
                ust.appendChild(b);
            });
            td.appendChild(ust);
        }
        if (gruplu) {
            td.appendChild(pfAyniTablosu(k.gruplar, ayniSecim, ayniOneri, kararModu, kart, kararCizenler, kararCiz));
            detay.appendChild(td);
            const acG = (acik) => {
                detay.hidden = !acik;
                dg.setAttribute("aria-expanded", acik ? "true" : "false");
                dg.classList.toggle("acik", !!acik);
            };
            dg.onclick = () => acG(detay.hidden);
            if (kararModu) acG(true);
            tbody.appendChild(satir);
            tbody.appendChild(detay);
            return;
        }
        const it = elYap("table", "dg-tablo pf-ic-tablo");
        const icg = document.createElement("colgroup");
        const sutunlar = birim === "satır"
            ? [["Tekrar", "pf-i-ad"], ["Bulgu", "pf-i-bulgu"]]
            : [["Kolon", "pf-i-ad"], ["Açıklama", "pf-i-acik"], ["Bulgu", "pf-i-bulgu"]]
                .concat(kararli ? [["Karar", "pf-i-karar"]] : []);
        sutunlar.forEach(([, c]) => { const col = document.createElement("col"); col.className = c; icg.appendChild(col); });
        it.appendChild(icg);
        const ith = elYap("tr");
        sutunlar.forEach(([b]) => ith.appendChild(elYap("th", "", b)));
        const ithead = elYap("thead"); ithead.appendChild(ith); it.appendChild(ithead);
        const itb = elYap("tbody");
        (k.kolonlar || []).forEach(c => {
            const r = elYap("tr");
            r.appendChild(elYap("td", "pf-kolon-ad", c.ad));
            if (birim !== "satır") r.appendChild(elYap("td", "pf-kolon-acik", c.aciklama || BOS_SIMGE));
            r.appendChild(elYap("td", "pf-bulgu", c.bulgu || ""));
            if (kararli) {
                const kt = elYap("td", "pf-karar-hucre");
                if (kararModu) kt.appendChild(kararDugmesi(c.ad));
                else kt.appendChild(elYap("span", "pf-karar-sonuc " + (c.karar === "cikar" ? "cikar" : "tut"),
                                          c.karar === "cikar" ? "Çıkarıldı" : "Tutuldu"));
                r.appendChild(kt);
            }
            itb.appendChild(r);
        });
        it.appendChild(itb);
        const kap = elYap("div", "pf-ic-kap");
        kap.appendChild(it);
        td.appendChild(kap);
        detay.appendChild(td);
        const ac = (acik) => {
            detay.hidden = !acik;
            dg.setAttribute("aria-expanded", acik ? "true" : "false");
            dg.classList.toggle("acik", acik);
        };
        dg.onclick = () => ac(detay.hidden);
        /* Karar bekleyen kontroller açık gelir. */
        if (kararli && kararModu) ac(true);
        tbody.appendChild(satir);
        tbody.appendChild(detay);
    });
    tablo.appendChild(tbody);
    const tsar = elYap("div", "pf-tablo-sar");
    tsar.appendChild(tablo);
    kb.appendChild(tsar);
    kart.appendChild(kb);

    /* Hedef dağılımı */
    const hd = alan.hedef;
    if (hd && (hd.siniflar || []).length) {
        const hb = elYap("div", "pf-bolum");
        const hbBas = elYap("div", "pf-bolum-bas");
        hbBas.appendChild(elYap("span", "pf-bolum-ad", "Hedef Dağılımı (" + hd.kolon + ")"));
        hb.appendChild(hbBas);
        const st = elYap("table", "dg-tablo pf-hedef-tablo");
        const sth = elYap("tr");
        ["Sınıf", "Satır", "Pay"].forEach(b => sth.appendChild(elYap("th", "", b)));
        const sthead = elYap("thead"); sthead.appendChild(sth); st.appendChild(sthead);
        const stb = elYap("tbody");
        hd.siniflar.forEach(c => {
            const r = elYap("tr");
            r.append(elYap("td", "pf-kolon-ad", c.deger), elYap("td", "", ftBinlik(c.satir)),
                     elYap("td", "", pfYuzde(c.pay)));
            stb.appendChild(r);
        });
        st.appendChild(stb);
        const ssar = elYap("div", "pf-tablo-sar");
        ssar.appendChild(st);
        hb.appendChild(ssar);
        hb.appendChild(elYap("div", "pf-not", Number(hd.bos)
            ? "Hedefi boş satır: " + ftBinlik(hd.bos) + ". Bu satırlar modelde kullanılamaz."
            : "Hedefi boş satır yok."));
        if ((hd.donemler || []).length) {
            const siniflar = hd.siniflar.map(c => c.deger);
            const gosterilen = hd.ikili ? ["1"] : siniflar;
            const dt = elYap("table", "dg-tablo pf-hedef-tablo");
            const dth = elYap("tr");
            ["Dönem", "Satır"].concat(gosterilen.map(c => hd.ikili ? "Hedef = 1 oranı" : "Sınıf " + c + " payı"))
                .forEach(b => dth.appendChild(elYap("th", "", b)));
            const dthead = elYap("thead"); dthead.appendChild(dth); dt.appendChild(dthead);
            const dtb = elYap("tbody");
            hd.donemler.forEach(d => {
                const r = elYap("tr");
                r.append(elYap("td", "pf-kolon-ad", d.donem), elYap("td", "", ftBinlik(d.satir)));
                gosterilen.forEach(c => r.appendChild(elYap("td", "", pfYuzde((d.paylar || {})[c] || 0))));
                dtb.appendChild(r);
            });
            dt.appendChild(dtb);
            const dsar = elYap("div", "pf-tablo-sar pf-hedef-donem");
            dsar.appendChild(dt);
            hb.appendChild(elYap("div", "pf-alt-baslik", "Dönem Başına"));
            hb.appendChild(dsar);
        }
        kart.appendChild(hb);
    }

    /* Karar düğmesi */
    if (kararModu) {
        const alt = elYap("div", "pf-karar-alt");
        const ozetEl = elYap("div", "pf-karar-ozet");
        const btn = elYap("button", "secim-onay", "Kararları Onayla ve Devam Et");
        btn.type = "button";
        const ozetYaz = () => {
            const adlar = Object.keys(kararlar);
            const cik = adlar.filter(a => kararlar[a] === "cikar").length;
            const gid = Object.keys(ayniSecim);
            const farkli = gid.filter(g => ayniSecim[g] !== ayniOneri[g]).length;
            const parca = [];
            if (adlar.length) parca.push(ftBinlik(adlar.length) + " kolon için karar: "
                + ftBinlik(adlar.length - cik) + " tutulacak, " + ftBinlik(cik) + " çıkarılacak.");
            if (gid.length) parca.push(ftBinlik(gid.length) + " aynı içerikli grupta kalacak kolon seçildi"
                + (farkli ? " (" + ftBinlik(farkli) + " grupta öneriden farklı)." : " (hepsi dil modelinin önerisi)."));
            ozetEl.textContent = parca.join(" ");
        };
        kararCizenler.push(ozetYaz);
        btn.onclick = () => {
            if (mesgul || btn.disabled) return;
            const cikar = Object.keys(kararlar).filter(a => kararlar[a] === "cikar");
            const tut = Object.keys(kararlar).length - cikar.length;
            kart.classList.add("kilitli");
            btn.hidden = true;
            btn.disabled = true;
            geriAlKilit = () => {
                kart.classList.remove("kilitli");
                btn.hidden = false;
                btn.disabled = false;
            };
            const gidler = Object.keys(ayniSecim);
            const ozet = [Object.keys(kararlar).length
                    ? ftBinlik(tut) + " kolon tutuldu, " + ftBinlik(cikar.length) + " kolon çıkarıldı" : "",
                gidler.length ? ftBinlik(gidler.length) + " aynı içerikli grupta seçim yapıldı" : ""]
                .filter(Boolean).join("; ");
            gonder(ozet || "Kararlar onaylandı", false,
                   { dogrulama: { adim: "veri_profili", cikar: cikar, ayni: Object.assign({}, ayniSecim) } });
        };
        alt.append(ozetEl, btn);
        kart.appendChild(alt);
    }
    kararCiz();

    if (alan.kayit) kart.appendChild(elYap("div", "pf-kayit", "Profil tablosu: " + alan.kayit));

    (adimKabiAl(blok) || sohbetEl).appendChild(kart);
}

/* ==================== 02.1 Kontrol eşikleri formu ====================
   Profil çıkarılmadan önce eşikler sorulur: her kontrolün eşiği,
   değiştirilebilir kutuda; varsayılan yanında. Varsayılandan farklı
   satır vurgulanır. Gönderim: {"dogrulama": {"adim": "veri_profili",
   "esikler": {anahtar: ekrandaki sayı}}}. Kilitli halde (onaylandı ya da
   yenileme) kutular salt okunur. */
function pfEsikSayi(metin) {
    const t = String(metin == null ? "" : metin).trim().replace("%", "").replace(/\s+/g, "");
    if (!t) return NaN;
    /* Türkçe yazım: 1.000 binlik, 0,5 ondalık. */
    const sade = t.indexOf(",") >= 0 ? t.replace(/\./g, "").replace(",", ".")
        : (/^\d{1,3}(\.\d{3})+$/.test(t) ? t.replace(/\./g, "") : t);
    return /^-?\d+(\.\d+)?$/.test(sade) ? Number(sade) : NaN;
}

function pfEsikYaz(v) {
    const n = Number(v);
    if (!isFinite(n)) return "";
    return Number.isInteger(n) ? String(n) : String(n).replace(".", ",");
}

function profilEsikKartiEkle(alan, blok) {
    const kart = elYap("div", "secim-kart pf-kart pf-esik-kart");
    const kilitli = !!alan.kilitli || !!(blok && blok.kilit);
    if (kilitli) kart.classList.add("kilitli");

    const bas = elYap("div", "pf-bas");
    bas.appendChild(elYap("b", "pf-baslik", kilitli ? "Onaylanan Kontrol Eşikleri" : "Kontrol Eşikleri"));
    bas.appendChild(bolmeBilgiSimgesi(
        "Veri profilindeki kontroller bu eşiklerle yapılır. Bir eşiği değiştirirseniz kontrol "
        + "değiştirdiğiniz değerle çalışır; değiştirmediğiniz eşikler varsayılan kalır.\n\n"
        + "Yüzdeli eşikler yüzde olarak yazılır (ör. 99 yazılırsa %99). Ondalık için virgül kullanılabilir.",
        "Kontrol Eşikleri"));
    kart.appendChild(bas);

    const hataEl = elYap("div", "pf-esik-hata");
    hataEl.hidden = !alan.hata;
    hataEl.textContent = alan.hata || "";
    kart.appendChild(hataEl);

    const tablo = elYap("table", "dg-tablo pf-esik-tablo");
    const cg = document.createElement("colgroup");
    ["pf-e-kontrol", "pf-e-anlam", "pf-e-deger", "pf-e-vars"].forEach(c => {
        const col = document.createElement("col"); col.className = c; cg.appendChild(col);
    });
    tablo.appendChild(cg);
    const thead = elYap("thead");
    const htr = elYap("tr");
    ["Kontrol", "Eşik", "Değer", "Varsayılan"].forEach(b => htr.appendChild(elYap("th", "", b)));
    thead.appendChild(htr);
    tablo.appendChild(thead);
    const tbody = elYap("tbody");
    const girisler = [];
    (alan.satirlar || []).forEach(r => {
        const tr = elYap("tr", "pf-esik-satir");
        tr.appendChild(elYap("td", "pf-kontrol-ad", r.kontrol));
        tr.appendChild(elYap("td", "pf-kural", r.anlam));
        const td = elYap("td", "pf-esik-hucre");
        const kutu = elYap("span", "pf-esik-kutu");
        /* Birim yuvaları sabit genişlikte: kutular alt alta hizalı. */
        kutu.appendChild(elYap("span", "pf-esik-birim on", r.birim === "yuzde" ? "%" : ""));
        const g = document.createElement("input");
        g.type = "text";
        g.inputMode = "decimal";
        g.className = "pf-esik-giris";
        g.value = pfEsikYaz(r.deger);
        g.setAttribute("aria-label", r.kontrol + " eşiği");
        g.disabled = kilitli;
        kutu.appendChild(g);
        kutu.appendChild(elYap("span", "pf-esik-birim son",
                               (r.birim === "puan" || r.birim === "kat") ? r.birim_adi : ""));
        td.appendChild(kutu);
        const uyari = elYap("div", "pf-esik-uyari");
        uyari.hidden = true;
        td.appendChild(uyari);
        tr.appendChild(td);
        tr.appendChild(elYap("td", "pf-esik-vars", r.varsayilan_metni || pfEsikYaz(r.varsayilan)));
        const denetle = () => {
            const v = pfEsikSayi(g.value);
            let mesaj = "";
            if (!isFinite(v)) mesaj = "Sayı yazın";
            else if (v < Number(r.en_az) || v > Number(r.en_cok))
                mesaj = pfEsikYaz(r.en_az) + " ile " + pfEsikYaz(r.en_cok) + " arasında olmalı";
            uyari.textContent = mesaj;
            uyari.hidden = !mesaj;
            tr.classList.toggle("hatali", !!mesaj);
            tr.classList.toggle("degisti", !mesaj && Math.abs(v - Number(r.varsayilan)) > 1e-9);
            return { ok: !mesaj, v: v };
        };
        g.addEventListener("input", () => { denetle(); ozetYaz(); });
        girisler.push({ r: r, g: g, denetle: denetle });
        tbody.appendChild(tr);
    });
    tablo.appendChild(tbody);
    const sar = elYap("div", "pf-tablo-sar");
    sar.appendChild(tablo);
    kart.appendChild(sar);

    const alt = elYap("div", "pf-karar-alt");
    const ozetEl = elYap("div", "pf-karar-ozet");
    function ozetYaz() {
        const sonuc = girisler.map(x => x.denetle());
        const degisen = sonuc.filter((x, i) => x.ok && Math.abs(x.v - Number(girisler[i].r.varsayilan)) > 1e-9).length;
        const hatali = sonuc.filter(x => !x.ok).length;
        ozetEl.textContent = hatali
            ? ftBinlik(hatali) + " eşik hatalı; düzeltmeden devam edilemez."
            : (degisen ? ftBinlik(degisen) + " eşik varsayılandan farklı; kontroller bu değerlerle "
                         + (kilitli ? "yapıldı." : "yapılır.")
                       : (kilitli ? "Kontroller varsayılan eşiklerle yapıldı." : "Bütün eşikler varsayılan."));
        ozetEl.classList.toggle("hatali", !!hatali);
        return { hatali: hatali, degisen: degisen };
    }
    alt.appendChild(ozetEl);
    if (!kilitli) {
        const dugmeler = elYap("div", "pf-esik-dugmeler");
        const vars = elYap("button", "dg-toplu-btn", "Varsayılanlara Dön");
        vars.type = "button";
        vars.onclick = () => {
            if (kart.classList.contains("kilitli")) return;
            girisler.forEach(x => { x.g.value = pfEsikYaz(x.r.varsayilan); });
            ozetYaz();
        };
        const btn = elYap("button", "secim-onay", alan.buton || "Eşikleri Onayla ve Profili Çıkar");
        btn.type = "button";
        btn.onclick = () => {
            if (mesgul || btn.disabled) return;
            const oz = ozetYaz();
            if (oz.hatali) { const ilk = girisler.find(x => !x.denetle().ok); if (ilk) ilk.g.focus(); return; }
            const esikler = {};
            girisler.forEach(x => { esikler[x.r.anahtar] = x.denetle().v; });
            kart.classList.add("kilitli");
            girisler.forEach(x => { x.g.disabled = true; });
            dugmeler.hidden = true;
            geriAlKilit = () => {
                kart.classList.remove("kilitli");
                girisler.forEach(x => { x.g.disabled = false; });
                dugmeler.hidden = false;
            };
            const ozet = oz.degisen ? ftBinlik(oz.degisen) + " eşik değiştirilerek onaylandı"
                                    : "Eşikler varsayılan değerlerle onaylandı";
            gonder(ozet, false, { dogrulama: { adim: "veri_profili", esikler: esikler } });
        };
        dugmeler.append(vars, btn);
        alt.appendChild(dugmeler);
    }
    kart.appendChild(alt);
    ozetYaz();

    (adimKabiAl(blok) || sohbetEl).appendChild(kart);
}

/* Kart aciklamasi KARTIN ICINDE DUZ METIN olarak duruyor. */
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
    /* 02.1 Kontrol eşikleri: profil çıkarılmadan önce */
    if (alan.tip === "profil_esik") { profilEsikKartiEkle(alan, blok); return; }
    /* 02.1 Veri Profili: sonuç; gerekirse Tut ya da Çıkar kararı */
    if (alan.tip === "profil") { profilKartiEkle(alan, blok); return; }

    const kart = document.createElement("div");
    kart.className = "secim-kart";

    /* Baslik satiri: baslik solda, durum gostergesi sagda. */
    const basSatir = document.createElement("div");
    basSatir.className = "secim-bas";

    const bas = document.createElement("div");
    bas.className = "secim-baslik";
    /* GRUPLU BLOKTA KART BASLIGI YOK: adımın adı zaten bloğun ALT
       BAŞLIĞINDA yazıyor ("Kolon Rolleri"). Satır DURUYOR: sağındaki
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

    /* Arka uctan "ipucu" alani gelse de cizilmez. */

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

        /* SECILENLER USTTE, ARAMA ALTTA. Liste yukaridan
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
        /* HEP TEK SATIR: sütun
           sayısı alan sayısı kadar, eşit genişlik. */
        govde.style.gridTemplateColumns =
            "repeat(" + Math.max(1, alanlar.length) + ", minmax(0, 1fr))";
        kilitEk = () => {
            Object.keys(combolar).forEach(k => { combolar[k].giris.disabled = true; });
            tipDugmeleri.forEach(x => { x.b.disabled = true; });
        };

        /* MODEL TİPİ (Kolon Rolleri): kartın ilk seçimi, alanların üstünde.
           Arka uç her tipin hedef listesini gönderiyor; tip değişince hedef
           alanının listesi (hedefListe, yerinde güncellenir) ve alt notu
           değişir. Sonraki adımları hazır olmayan tip KAPALI: soluk durur,
           tıklanmaz, açıklamasının altında "Şu An Kapalı".
           Her kartın köşesinde "i": tip nedir, ne için kullanılır, örnek.
           Simge kartın DIŞINDA (kutunun köşesinde) durur: kapalı kartın
           solukluğu ve tıklanmazlığı ona geçmez, açıklama her tipte okunur. */
        const pr = alan.problem || null;
        let problem = (pr && pr.deger) || "";
        const tipDugmeleri = [];
        let eslesmeler = [];          // Baz Sözlük eşleşmesi (aşağıda)

        /* ÇOKLU ALAN (Baz Sözlük): seçilenler kutunun içinde etiket olarak
           durur, × ile çıkar; kutuya basınca liste açılır, seçilen eklenir
           (aynı ad iki kez eklenmez, listede seçilenler görünmez). Boş
           kutuda Backspace son etiketi siler. Değer "A + B". */
        function cokluYap(a) {
            const secilen = (a.degerler || []).slice();
            const o = { coklu: true, secilen: secilen, otomatik: false };
            const combo = comboYap(a.etiket, durumTazele, "", {
                kaynak: a.kaynak || "dataset",
                zorunlu: a.zorunlu,
                placeholder: a.placeholder,
                haric: () => secilen,
                secilince: ad => ekle(ad)
            });
            const kutu = combo.giris.parentElement;
            kutu.classList.add("coklu-alan");
            const cipler = elYap("div", "coklu-cipler");
            kutu.insertBefore(cipler, combo.giris);
            function ciz() {
                cipler.innerHTML = "";
                secilen.forEach((ad, i) => {
                    const c = elYap("span", "coklu-cip");
                    c.appendChild(elYap("span", "coklu-ad", ad));
                    const x = document.createElement("button");
                    x.type = "button";
                    x.className = "coklu-sil";
                    x.textContent = "×";
                    x.setAttribute("aria-label", ad + " çıkar");
                    x.onmousedown = e => e.preventDefault();
                    x.onclick = e => {
                        e.stopPropagation();
                        if (kart.classList.contains("kilitli")) return;
                        secilen.splice(i, 1);
                        o.otomatik = false;
                        ciz();
                        durumTazele();
                    };
                    c.appendChild(x);
                    cipler.appendChild(c);
                });
                combo.giris.placeholder = secilen.length
                    ? "Sözlük ekle" : (a.placeholder || "");
            }
            function ekle(ad) {
                if (secilen.indexOf(ad) === -1) secilen.push(ad);
                combo.giris.value = "";
                o.otomatik = false;
                ciz();
                durumTazele();
            }
            kutu.addEventListener("mousedown", e => {
                if (combo.giris.disabled || e.target === combo.giris
                    || e.target.closest(".coklu-sil, .combo-ok, .combo-liste")) return;
                e.preventDefault();
                combo.giris.focus();
                combo.ciz(combo.giris.value);
            });
            combo.giris.addEventListener("click", () => {
                if (!combo.giris.disabled) combo.ciz(combo.giris.value);
            });
            combo.giris.addEventListener("keydown", e => {
                if (e.key === "Backspace" && !combo.giris.value && secilen.length) {
                    secilen.pop();
                    o.otomatik = false;
                    ciz();
                    durumTazele();
                }
            });
            o.kok = combo.kok;
            o.giris = combo.giris;
            o.isaretle = combo.isaretle;
            /* Yazılıp eklenmemiş metin varsa form gönderilmez. */
            o.gecerli = () => !combo.giris.value.trim();
            o.dolu = () => secilen.length > 0;
            o.deger = () => secilen.join(" + ");
            o.ata = liste => { secilen.splice(0, secilen.length, ...liste); ciz(); };
            ciz();
            return o;
        }
        const hedefListe = [];
        let hedefAlt = null;
        const tipBul = d => ((pr && pr.tipler) || []).find(t => t.deger === d) || null;
        if (pr) {
            const etk = elYap("div", "problem-etiket", pr.etiket || "Model Tipi");
            const y = elYap("span", "combo-zorunlu", "*");
            y.setAttribute("aria-hidden", "true");
            etk.appendChild(y);
            kart.appendChild(etk);
            const satir = elYap("div", "problem-secim");
            satir.setAttribute("role", "radiogroup");
            satir.setAttribute("aria-label", pr.etiket || "Model Tipi");
            (pr.tipler || []).forEach((t, i) => {
                const b = document.createElement("button");
                b.type = "button";
                b.className = "secenek problem-tip";
                b.setAttribute("role", "radio");
                b.appendChild(elYap("span", "secenek-rozet", String(i + 1)));
                const g = elYap("div", "secenek-govde");
                g.appendChild(elYap("div", "secenek-baslik", t.baslik));
                if (t.turkce) g.appendChild(elYap("div", "problem-turkce", t.turkce));
                g.appendChild(elYap("div", "secenek-aciklama", t.aciklama));
                b.appendChild(g);
                if (!t.hazir) {
                    b.classList.add("kapali");
                    b.disabled = true;
                    /* Etiket açıklamanın altında: sağda dursa metni daraltır. */
                    g.appendChild(elYap("span", "secenek-kapali", "Şu An Kapalı"));
                }
                const kutu = elYap("div", "problem-kutu");
                kutu.appendChild(b);
                if (t.bilgi) kutu.appendChild(bolmeBilgiSimgesi(t.bilgi,
                    t.baslik + (t.turkce ? " (" + t.turkce + ")" : "")));
                b.onclick = () => {
                    if (mesgul || !t.hazir || kart.classList.contains("kilitli")) return;
                    tipSec(t.deger, true);
                };
                tipDugmeleri.push({ b: b, t: t });
                satir.appendChild(kutu);
            });
            kart.appendChild(satir);
        }

        function tipSec(deger, kullanici) {
            const t = tipBul(deger);
            if (!t || !t.hazir) return;
            problem = deger;
            tipDugmeleri.forEach(x => {
                const sec = x.t.deger === deger;
                x.b.classList.toggle("secili", sec);
                x.b.setAttribute("aria-checked", sec ? "true" : "false");
            });
            hedefListe.length = 0;
            (t.hedef.secenekler || []).forEach(k => hedefListe.push(k));
            const hc = combolar.target;
            if (hc) {
                if (kullanici && hc.giris.value && hedefListe.indexOf(hc.deger()) === -1)
                    hc.giris.value = "";
                hc.giris.disabled = !!t.hedef.yok;
                if (t.hedef.yok) hc.giris.value = "";
                hc.isaretle();
            }
            if (hedefAlt) {
                metinYaz(hedefAlt, t.hedef["not"] || t.hedef.ipucu || "");
                hedefAlt.classList.toggle("alan-not-uyari", !!t.hedef["not"]);
            }
            durumTazele();
        }

        /* Kolon kaynakli alan varsa (hedef/kimlik/dönem) once kolon listesi
           hazirlanir: backend'in gonderdigi liste ya da /kolonlar ucu. */
        if (alanlar.some(a => (a.kaynak || "dataset") === "kolon"))
            kolonlariHazirla(alan);

        /* Durum gostergesi: kac alan dolu, kac alan bekleniyor.
           SAYIMA YALNIZ ZORUNLU ALANLAR GIRER. Düğmenin
           etkinligi yine BUTUN alanlarin gecerliligine bakar: opsiyonel
           alana gecersiz bir deger yazilmissa form yine kilitli kalmali. */
        function onerileriTazele() {
            eslesmeler.forEach(o => {
                const d = combolar[o.a.oneri_alani].deger();
                if (d !== o.kaynakDeger) {
                    o.kaynakDeger = d;
                    const varMi = ad => DATASET_DURUMU !== "hazir"
                        || DATASETLER.indexOf(ad) !== -1;
                    const liste = ((o.a.oneriler || {})[d] || []).filter(varMi);
                    if (!o.c.secilen.length || o.c.otomatik) {
                        o.c.ata(liste);
                        o.c.otomatik = liste.length > 0;
                    }
                }
                if (o.alt) metinYaz(o.alt, o.c.otomatik
                    ? (o.a.oneri_notu || "") : (o.a.ipucu || ""));
            });
        }

        function durumTazele() {
            if (kart.classList.contains("kilitli")) return;
            onerileriTazele();
            const anahtarlar = Object.keys(combolar);
            const zorunlular = anahtarlar.filter(k => zorunluAlan[k]);
            const sayilan = zorunlular.length ? zorunlular : anahtarlar;
            const dolu = sayilan.filter(k => combolar[k].dolu()).length;
            const tip = pr ? tipBul(problem) : null;
            onayBtn.disabled = anahtarlar.some(k => !combolar[k].gecerli())
                || (pr && !(tip && tip.hazir));
            /* Model tipi de zorunlu bir seçim: sayaca girer. */
            durumEl.textContent = pr
                ? secimDurumMetni(dolu + (problem ? 1 : 0), sayilan.length + 1)
                : secimDurumMetni(dolu, sayilan.length);
            /* Dolu ama GÖNDERİLMEMİŞ kart yeşil olmaz: yeşil "onaylandı" demek. */
            durumEl.classList.remove("hazir", "onayli");
        }

        alanlar.forEach(a => {
            /* Her alan kendi kaynagini kullanir: veri seti mi, kolon mu?
               ALAN BAZLI LISTE: a.secenekler geldiyse o alanda YALNIZCA
               o liste gosterilir. Hedef degisken 0/1 kolonlarla, kimlik
               kolonu tekrarsiz kolonlarla sinirli. */
            /* Model tipli kartta hedef alanı tipin listesini kullanır. */
            const hedefTipli = pr && a.ad === "target";
            if (hedefTipli) (a.secenekler || []).forEach(k => hedefListe.push(k));
            const combo = a.coklu ? cokluYap(a) : comboYap(a.etiket, durumTazele, a.deger, {
                kaynak: a.kaynak || "dataset",
                zorunlu: a.zorunlu,
                placeholder: a.placeholder,
                liste: hedefTipli ? hedefListe
                     : Array.isArray(a.secenekler) ? a.secenekler : undefined
            });
            if (hedefTipli && !problem) combo.giris.disabled = true;
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
                /* NOT AYRINTISI "i" SİMGESİNDE. Kısa not ("Dönem kolonu
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
                if (hedefTipli) hedefAlt = alt;
            }
        });

        /* EŞLEŞEN SÖZLÜK (Baz Sözlük). "oneriler", kaynak alanın (Baz
           Veri Seti) değerine göre o veri setinin en son eşlendiği
           sözlükleri taşır. Veri seti değişince bunlar seçili gelir; alan
           boşsa ya da içindekiler de kendiliğinden gelmişse. Kullanıcının
           eklediği ya da çıkardığı seçim ezilmez. Kendiliğinden
           seçildiğinde alanın altındaki satır bunu söyler. Projede artık
           olmayan tablo seçilmez; açılışta dolu gelen seçime dokunulmaz. */
        eslesmeler = alanlar
            .filter(a => a.coklu && a.oneri_alani && a.oneriler
                         && combolar[a.ad] && combolar[a.oneri_alani])
            .map(a => ({ a: a, c: combolar[a.ad],
                         kaynakDeger: combolar[a.oneri_alani].deger(),
                         alt: combolar[a.ad].kok.querySelector(".alan-not") }));

        kart.appendChild(govde);
        if (pr && problem) tipSec(problem, false);

        onayBtn.onclick = () => {
            if (mesgul || onayBtn.disabled) return;
            let metin = (alan.sablon || "").replace("{problem}", problem);
            Object.keys(combolar).forEach(k => {
                const v = combolar[k].deger();
                if (!combolar[k].coklu) combolar[k].giris.value = v;
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
                tipDugmeleri.forEach(x => { x.b.disabled = !x.t.hazir; });
                if (pr && problem) tipSec(problem, false);
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
*/
    if (d.fazlar) fazlariYukle(d.fazlar);
    /* Secili veri setinin adi bu iki govdeden okunuyor; kolon kaynakli
       form cizilmeden ONCE guncellenmeli. */
    if (d.ozet)  SON_OZET  = d.ozet;
    if (d.detay) SON_DETAY = d.detay;
    /* BOS METIN BALON ACMAZ. Bir adim yalnizca form/kart gonderiyorsa
       (metin "") Kullanıcı o noktada ekranda henüz konuşmamış da olabiliyor
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
       kart ya da seçenek takımı var).
       Metin yoksa boş gövdeli blok kurulur; seçenekler onun içine
       girer (secenekEkle son .balon-sutun'u arar). */
    /* BİTEN ADIMIN METNİ KENDİ BLOĞUNA. Bir tur ilerlerken dönen metin
       iki parçadır: biten adımın özeti ve yeni adımın giriş metni.
       Arka uç ayrımı gövdede gönderiyor (backend: govde
       ["tamamlanan"]); metin burada kendi adımının bloğuna düşüyor. */
    /* Bir turda birden fazla adım bitebilir (bölme → profil → SFA →
       aralık kartı, onaysız zincir): her birinin metni kendi bloğuna. */
    const bitenler = (d.tamamlananlar && d.tamamlananlar.length)
        ? d.tamamlananlar : (d.tamamlanan ? [d.tamamlanan] : []);
    if (!hataMi) bitenler.forEach(t => {
        if (!t || !t.adim || !(t.metin || "").trim()) return;
        const tAdim = DUZ_ADIMLAR[(adimSirasiHaritasi() || {})[t.adim]] || {};
        const tBlok = {
            adim: t.adim,
            baslik: t.baslik || tAdim.baslik || "",
            grup: tAdim.grup || "", grup_baslik: tAdim.grup_baslik || "",
            onay: false
        };
        balonEkle("bot", t.metin, false, tBlok);
        /* Biten adımın kartı kendi bloğunda: 02.1 Veri Profili; önceki
           onaylı kontrolle kendiliğinden onaylanan 01.2.4 adımında
           uygulanan kararlar (kilitli, salt okunur). */
        if (t.secim_alani)
            secimAlaniEkle(t.secim_alani, t.secim_alani.onceki
                ? Object.assign({}, tBlok, { kilit: true }) : tBlok);
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
           sade bir satıra konur. */
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
    /* Sağ blok: kararı blokta verilen adımda (SFA) kendiliğinden genişler,
       adım geçince şeride döner. */
    if (!hataMi) analizOtoGuncelle(d.secim_alani, d.adim_anahtari, d.bekleyen);
    ozetGuncelle(d.ozet);
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
        /* ÖNCEKİ RET UYARISI KALKAR. Geçerli olan
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

/* Sonuç artan aralıklarla yoklanır, toplam ~50 saniye.
   Yeni bir sonuç gelirse balon KALDIRILIR - yerini gerçek yanıt alır.
   Gelmezse balon ne olduğunu açıkça yazar; "kontrol ediliyor" diye
   asılı kalmaz. */
const YOKLAMA_ARALIKLARI = [1200, 2500, 4000, 7000, 11000, 15000];

/* UZUN İŞLER. Kısa aralıklar bitince
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
        metinYaz(govde, metin);
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
       BASILMIYOR. */
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

        if (istekDurumu === "zamanasimi") {
            durumuYokla(balonEkle("bot",
                "İşlem sürüyor · " + sureBicim(Math.round(ISTEK_ZAMAN_ASIMI / 1000))
                + ". Sonucu bekliyorum", false),
                "İşlem " + sureBicim(Math.round(ISTEK_ZAMAN_ASIMI / 1000))
                + " içinde yanıt vermedi.");
        } else if (istekDurumu === "iptal") {
            durumuYokla(balonEkle("bot",
                "İsteği iptal ettiniz. Sunucudaki işlem sürüyor olabilir; "
                + "sonucu bekliyorum", true),
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
           kutusunda) yaziyorsa odak ALINMAZ: her yanit imleci sohbete
           cekerse kolon aranamaz. */
        const analizdeYaziyor = analizPanel
            && analizPanel.contains(document.activeElement);
        if (yeniOdak && document.contains(yeniOdak)) {
            
            try { yeniOdak.focus({ preventScroll: true }); }
            catch (err) { kutuEl.focus({ preventScroll: true }); }
        } else if (!analizdeYaziyor) {
            kutuEl.focus({ preventScroll: true });
        }
        yeniOdak = null;
    });
}

/* Sohbete sessiz bir ayrac
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
    metinYaz(yazi, metin);
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
   aynı formu (aynı başlıkla) yeniden gönderiyor. Aynı adımda aynı başlıklı daha yeni bir
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

/* ESKİ KARAR KARTLARI ÇİZİLMEZ. Aynı adımın kartı birden fazla kez
   gönderilebilir (adıma Geri Dön, onayda hata, soru turu). Onayla
   yalnız SONUNCUSU verilen kararlarla güncellenir (backend
   _biten_adimi_guncelle); öncekiler ilk hâlinde kalır ve yenilemede
   kararlar kaydolmamış gibi görünürdü. Aynı adımda aynı türden daha yeni
   bir karar kartı varsa eskisinin kartı düşülür; metni yerinde kalır. */
const KARAR_KART_BOLUMLERI = ["tanimsiz", "kontrol", "cikar", "birlesim", "donem", "parca",
                              "aciklama_duzen", "kolon_ad"];
function eskiKararKartlariniAyikla(liste) {
    const anahtar = g => {
        const a = g && g.rol === "bot" && g.adim && g.ekran && g.ekran.secim_alani;
        if (!a || a.tip !== "dogrulama") return null;
        return g.adim + "\u0000" + (a.adim || "") + "\u0000"
            + KARAR_KART_BOLUMLERI.filter(k => a[k]).join(",");
    };
    const sonra = new Set();
    for (let i = liste.length - 1; i >= 0; i--) {
        const k = anahtar(liste[i]);
        if (!k) continue;
        if (sonra.has(k)) {
            const ekran = Object.assign({}, liste[i].ekran);
            delete ekran.secim_alani;
            liste[i] = Object.assign({}, liste[i], { ekran: ekran });
        } else sonra.add(k);
    }
    return liste;
}

function gecmisiCiz(gecmis, sonMetin) {
    const liste = eskiKararKartlariniAyikla(reddedilenFormlariAyikla((gecmis || []).slice()));

    /* AKTIF ADIMIN SON EKRANI canli ciziliyor (yanitUygula); gecmisten
       ikinci kez cizilmemeli. Ondan ONCEKI ekranlari ise gecmisten
       gelmeli: bir adim birden fazla ekran uretebiliyor (once veri
       seti formu, sonra girdi dogrulama karti) ve canli yanit yalnizca
       SONUNCUSUNU tasiyor. */
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
                  + "kullanıcı adınıza kayıtlı. Sıfırdan başlamak için sol "
                  + "alttaki **" + YENI_CALISMA_ETIKETI + "** düğmesini kullanın; "
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
               kuruyor. */
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
       Değişken Listesi ve Tip Kontrolü".
*/
    if (c.adim && c.faz_no) {
        parca.push(c.faz_no + " " + tireSade(c.faz_baslik || "")
                   + " · " + numarali(c.adim_kodu, c.adim));
    } else if (c.adim) {
        parca.push(tireSade(c.adim));
    }
    return parca.join(" · ");
}

/* ARŞİV SATIRI (sade): solda çalışmanın adı (açık olanda "Açık"), sağda
   çöp kutusu ikonu. Satıra basınca çalışma açılır; son adım ve tarih
   satırın üstüne gelince görünür (title). Silme onayı aynı satırda:
   "Silinsin mi?" + Sil / Vazgeç. */
const COP_IKON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    + 'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    + '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v6M14 11v6"></path></svg>';

function arsivSatiri(ad, aciklama, aktif, acilabilir, ac, silBilgi, silBaslik) {
    const satir = elYap("div", "calisma-satir" + (aktif ? " aktif" : ""));
    const oge = document.createElement("button");
    oge.type = "button";
    oge.className = "calisma-oge";
    oge.setAttribute("role", "menuitem");
    oge.appendChild(elYap("span", "calisma-ad", ad));
    if (aktif) oge.appendChild(elYap("span", "calisma-etiket", "Açık"));
    oge.disabled = !acilabilir;
    oge.title = (aciklama ? aciklama + "\n" : "")
        + (aktif ? "Şu an bu çalışmadasınız" : acilabilir ? "Tıklayın: kaldığı yerden aç" : "");
    if (acilabilir && ac) oge.onclick = ac;
    satir.appendChild(oge);
    const dugmeler = elYap("div", "calisma-dugmeler");
    if (silBilgi) {
        const sil = elYap("button", "calisma-cop");
        sil.type = "button";
        sil.innerHTML = COP_IKON;
        sil.title = silBaslik;
        sil.setAttribute("aria-label", silBaslik);
        sil.onclick = () => calismaSilOnayi(dugmeler, silBilgi);
        dugmeler.appendChild(sil);
    }
    satir.appendChild(dugmeler);
    return satir;
}

function calismalarCiz(d) {
    calismalarListe.innerHTML = "";
    if (!d || d.hata) {
        calismalarListe.appendChild(elYap("div", "calisma-bos calisma-hata",
            "Liste okunamadı" + (d && d.hata_kodu ? " (" + d.hata_kodu + ")." : ".")));
        return;
    }
    const liste = d.calismalar || [];
    if (!liste.length)
        calismalarListe.appendChild(elYap("div", "calisma-bos", "Kayıtlı çalışma yok."));
    liste.forEach(c => {
        const aktif = c.calisma_id === OTURUM_ID;
        const alt = c.hata ? c.hata
            : (c.baslamis === false ? "Henüz başlanmadı" : calismaAltSatiri(c));
        /* Hiç başlamamış (boş) açık çalışmada silinecek bir şey yok. */
        const silinir = c.baslamis !== false || c.hata;
        calismalarListe.appendChild(arsivSatiri(
            c.ad || ("Çalışma " + c.calisma_id), tireSade(alt || ""), aktif,
            !c.hata && !aktif, () => calismayaGec(c.calisma_id),
            silinir ? c : null, "Bu çalışmayı kalıcı olarak sil"));
    });
    gizliKlasorleriCiz(d.gizli);
}

/* LİSTEDE GÖRÜNMEYEN KLASÖRLER: PROJE_HAFIZASI'nda olup listede olmayan
   v-klasörleri (çalışma dosyası silinmiş artık dosyalar, başlanmamış
   çalışma). Nedeni satırın üstüne gelince görünür; çöp kutusu klasörü
   kalıcı siler (onaylı, Sil ile aynı uç). Boş klasör listelenmez. */
function gizliKlasorleriCiz(gizli) {
    if (!gizli || !gizli.length) return;
    calismalarListe.appendChild(elYap("div", "calisma-gizli-baslik",
        "Diğer Klasörler · " + gizli.length));
    gizli.forEach(g => {
        const satir = arsivSatiri(g.ad, tireSade(g.neden || ""), false, false, null,
            { calisma_id: g.ad }, g.ad + " klasörünü kalıcı olarak sil");
        satir.classList.add("calisma-gizli");
        calismalarListe.appendChild(satir);
    });
}

/* SİLME ONAYI AYNI SATIRDA: ad ve çöp kutusu gizlenir, yerinde
   "Silinsin mi?" ile Sil / İptal belirir. Silme geri alınamaz; tek
   tıkla olmamalı. */
function calismaSilOnayi(dugmeler, c) {
    const satir = dugmeler.closest(".calisma-satir");
    const eski = Array.from(dugmeler.children);
    eski.forEach(d => { d.hidden = true; });
    if (satir) satir.classList.add("onayda");
    const soru = elYap("span", "calisma-sil-soru", "Silinsin mi?");
    soru.title = c.calisma_id + " kalıcı olarak silinir";
    const onayla = elYap("button", "calisma-dugme onayla", "Sil");
    const reddet = elYap("button", "calisma-dugme", "İptal");
    onayla.type = reddet.type = "button";
    onayla.title = c.calisma_id + " kalıcı olarak silinir; geri alınamaz";
    const geriGetir = () => {
        [soru, onayla, reddet].forEach(d => d.remove());
        eski.forEach(d => { d.hidden = false; });
        if (satir) satir.classList.remove("onayda");
    };
    reddet.onclick = geriGetir;
    onayla.onclick = () => {
        onayla.disabled = reddet.disabled = true;
        soru.textContent = "Siliniyor";
        /* BEKLETMEZ: açık olmayan çalışmanın satırı
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
           yeniden istenmez. */
        if (ARSIV_ONBELLEK && ARSIV_ONBELLEK.calismalar)
            ARSIV_ONBELLEK.calismalar = ARSIV_ONBELLEK.calismalar
                .filter(x => x.calisma_id !== kimlik);
        if (ARSIV_ONBELLEK && ARSIV_ONBELLEK.gizli)
            ARSIV_ONBELLEK.gizli = ARSIV_ONBELLEK.gizli.filter(x => x.ad !== kimlik);
        if (d.sonraki) { calismayaGec(d.sonraki, true); return; }
        if (satir) satir.remove();
        const gb = calismalarListe.querySelector(".calisma-gizli-baslik");
        if (gb) {
            const n = calismalarListe.querySelectorAll(".calisma-gizli").length;
            if (n) gb.textContent = "Diğer Klasörler · " + n; else gb.remove();
        }
        /* Dosyalar silindi ama Dataiku boş klasörü bıraktı: hata değil, not. */
        if (d.not) calismalarListe.insertBefore(
            elYap("div", "calisma-bos calisma-not", d.not), calismalarListe.firstChild);
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
        calismalarListe.appendChild(elYap("div", "calisma-bos", "Yükleniyor"));
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

/* Düğmenin adı "Arşiv"; index.html'deki etiketten bağımsız olarak
   burada yazılır. */
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

/* YENİ ÇALIŞMA ONAYSIZ. Basınca yeni çalışma hemen açılır; açık çalışma
   SİLİNMEZ, Arşiv'den geri açılır. index.html'de eski onay kutusu
   varsa burada kaldırılır. */
{ const eski = document.getElementById("yeni-onay"); if (eski) eski.remove(); }
sifirlaBtn.onclick = (e) => {
    e.stopPropagation();
    calismalarKapat();
    sayfaAc("calisma");
    sifirlaUygula();
};


/* AÇILIŞ: soru SORULMAZ. Tarayıcıda kayıtlı çalışma
   ya da kullanıcının en son çalışması doğrudan açılır; başka bir
   çalışmaya "Arşiv" düğmesinden geçilir. Dosyanın SONUNDA
   çağrılıyor: kullandığı Arşiv sabitleri aşağıda tanımlı. */
calismaAc();
