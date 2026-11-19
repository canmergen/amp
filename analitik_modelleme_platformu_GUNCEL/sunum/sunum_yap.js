// Akilli Modelleme Platformu tanitim sunumu (duzenlenebilir pptx)
const pptxgen = require("pptxgenjs");
const React = require("react");
const RDS = require("react-dom/server");
const sharp = require("sharp");
const fa = require("react-icons/fa6");
const { applyTheme } = require(process.env.PPTX_SKILL + "/scripts/apply_theme.js") // PPTX_SKILL: pptx araclarinin klasoru;

const CIKTI = process.argv[2] || "sunum.pptx";

const THEME = {
  name: "Akilli Modelleme",
  headFontFace: "Calibri",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "1E2329", lt1: "FFFFFF", dk2: "4B5563", lt2: "F3F4F6",
    accent1: "B01E2E", accent2: "6B7280", accent3: "C27803", accent4: "2E7D4F",
    accent5: "7A1420", accent6: "D9DCE1", hlink: "B01E2E", folHlink: "6B7280",
  },
};
const HEX = THEME.colors;

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5
pres.title = "Akıllı Modelleme Platformu";
pres.subject = "Platform tanıtımı";
pres.author = "Akıllı Modelleme Platformu";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
const C = pres.SchemeColor;

const W = 13.333, X0 = 0.6, CW = 12.133;

// ---------------------------------------------------------------- layouts
pres.defineSlideMaster({
  title: "KAPAK",
  background: { color: HEX.accent1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.8, y: 2.3, w: 11.7, h: 1.4,
      fontSize: 48, bold: true, color: C.background1, valign: "bottom", align: "left", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: 0.8, y: 3.85, w: 11.0, h: 1.2,
      fontSize: 22, color: C.background1, valign: "top", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "alt", type: "body", x: 0.8, y: 6.3, w: 11.0, h: 0.5,
      fontSize: 14, color: C.background1, valign: "middle", margin: 0 }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "BOLUM",
  background: { color: HEX.dk1 },
  objects: [
    { placeholder: { options: { name: "no", type: "body", x: 0.8, y: 1.9, w: 6, h: 1.3,
      fontSize: 72, bold: true, color: C.accent1, valign: "bottom", align: "left", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "title", type: "title", x: 0.8, y: 3.3, w: 11.5, h: 1.0,
      fontSize: 40, bold: true, color: C.background1, valign: "top", align: "left", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: 0.8, y: 4.4, w: 10.5, h: 1.2,
      fontSize: 18, color: C.accent6, valign: "top", margin: 0 }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "ICERIK",
  background: { color: HEX.lt1 },
  margin: [0.5, 0.6, 0.6, 0.6],
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: X0, y: 0.32, w: CW, h: 0.72,
      fontSize: 32, bold: true, color: C.text1, valign: "middle", align: "left", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "lead", type: "body", x: X0, y: 1.04, w: CW, h: 0.55,
      fontSize: 16, color: C.text2, valign: "top", margin: 0 }, text: "" } },
    { text: { text: "Akıllı Modelleme Platformu · Ekiplere tanıtım",
      options: { x: X0, y: 7.02, w: 8, h: 0.3, fontSize: 10, color: C.accent2, margin: 0 } } },
  ],
  slideNumber: { x: 12.2, y: 7.02, w: 0.55, h: 0.3, fontSize: 10, color: C.accent2, align: "right" },
});

// ---------------------------------------------------------------- yardimcilar
const iconCache = {};
async function ikon(ad, renk) {
  const k = ad + renk;
  if (iconCache[k]) return iconCache[k];
  const svg = RDS.renderToStaticMarkup(React.createElement(fa[ad], { color: "#" + renk, size: 256 }));
  const buf = await sharp(Buffer.from(svg)).resize(256, 256).png().toBuffer();
  return (iconCache[k] = "image/png;base64," + buf.toString("base64"));
}
async function ikonDaire(s, ad, x, y, d, ad2) {
  s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: C.accent1 }, line: { type: "none" },
    objectName: (ad2 || ad) + " daire" });
  const p = d * 0.5;
  s.addImage({ data: await ikon(ad, "FFFFFF"), x: x + (d - p) / 2, y: y + (d - p) / 2, w: p, h: p,
    altText: ad2 || ad, objectName: (ad2 || ad) + " ikon" });
}
function kart(s, x, y, w, h, ad, opt = {}) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x, y, w, h, rectRadius: 0.08,
    fill: opt.fill || { color: C.background2 },
    line: opt.line || { type: "none" },
    objectName: ad,
  });
}
function yazi(s, metin, o) {
  s.addText(metin, Object.assign({ isTextBox: true, fontSize: 14, color: C.text1, margin: 0,
    valign: "top", paraSpaceAfter: 0 }, o));
}
function rozet(s, metin, x, y, w, h, o = {}) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: Math.min(h / 2, 0.2),
    fill: { color: o.fill || C.accent1 }, line: { type: "none" }, objectName: "rozet " + metin });
  yazi(s, metin, { x, y, w, h, fontSize: o.fontSize || 12, bold: true, color: o.color || C.background1,
    align: "center", valign: "middle" });
}
function ok(s, x1, y1, x2, y2, o = {}) {
  s.addShape(pres.shapes.LINE, {
    x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1) || 0.001, h: Math.abs(y2 - y1) || 0.001,
    flipH: x2 < x1, flipV: y2 < y1,
    line: { color: o.color || C.accent2, width: o.width || 1.5, endArrowType: o.bas === false ? undefined : "triangle",
      dashType: o.dash || "solid" },
    objectName: o.ad || "ok",
  });
}
function madde(liste, o = {}) {
  return liste.map((t, i) => {
    const r = Array.isArray(t) ? t : [{ text: t }];
    return r.map((p, j) => ({ text: p.text, options: Object.assign({}, o, p.options || {},
      j === 0 ? { bullet: o.bullet === false ? false : { indent: 14 } } : {},
      j === r.length - 1 && i < liste.length - 1 ? { breakLine: true } : {}) }));
  }).flat();
}
function icerik(baslik, ust, bolum) {
  const s = pres.addSlide({ masterName: "ICERIK", sectionTitle: bolum });
  s.addText(baslik, { placeholder: "title" });
  if (ust) s.addText(ust, { placeholder: "lead" });
  return s;
}
function tablo(s, satirlar, o) {
  const bas = satirlar[0].map((h) => ({ text: h, options: { bold: true, color: HEX.lt1, fill: { color: HEX.accent1 },
    align: "center", valign: "middle" } }));
  const govde = satirlar.slice(1).map((r, i) => r.map((c, j) => ({
    text: c, options: Object.assign({ align: "center", valign: "middle", color: HEX.dk1,
      fill: { color: i % 2 ? HEX.lt2 : HEX.lt1 } }, j === 0 && o.ilkKalin ? { bold: true } : {}) })));
  s.addTable([bas, ...govde], Object.assign({ fontSize: 12, fontFace: "Calibri",
    border: { type: "solid", pt: 0.75, color: HEX.accent6 }, margin: [0.04, 0.08, 0.04, 0.08] }, o));
}

// ================================================================ SLAYTLAR
(async () => {
  const B0 = "Giriş", B1 = "Genel yapı", B2 = "Fazlar adım adım", B3 = "Platform genelinde";

  // 1 KAPAK ------------------------------------------------------------
  pres.addSection({ title: B0 });
  let s = pres.addSlide({ masterName: "KAPAK", sectionTitle: B0 });
  s.addText("Akıllı Modelleme Platformu", { placeholder: "title" });
  s.addText("Ham veriden doğrulanmış ve belgelenmiş final modele: ne yaptık, nerede yaptık, nasıl çalışıyor",
    { placeholder: "body" });
  s.addText("Ekiplere tanıtım · Kasım 2026", { placeholder: "alt" });
  s.addNotes("Bu sunum platformun güncel hâlini anlatır: amacı, yapısı, beş fazın her adımında ne yapıldığı, " +
    "verinin nerede tutulduğu, yapay zekâ ile kodun iş bölümü ve güvenceler.");

  // 2 TEK CUMLE --------------------------------------------------------
  s = icerik("Platform ne yapar",
    "Model geliştirme sürecinin tamamını Dataiku içinde tek bir webapp'te, izlenebilir ve tekrar edilebilir biçimde yürütür.", B0);
  const k2 = [
    ["FaRoute", "Tek akış", "Veri seti ve sözlük seçiminden final modele, değişken kataloğuna ve model dokümanına kadar beş faz, sıralı adımlar, tek çalışma alanı."],
    ["FaUserCheck", "Onaysız hiçbir şey uygulanmaz", "Her adımda platform analizi yapar, önerisini gerekçesiyle sunar; siz inceler, düzenler ve onaylarsınız. Geri Dön ile önceki karara dönülür."],
    ["FaCalculator", "Sayılar koddan gelir", "Yapay zekâ önerir ve yorumlar. Sayım, ölçüm, değişken üretimi ve model eğitimini kod yapar, verinin tamamında ve örneklemesiz."],
  ];
  for (let i = 0; i < 3; i++) {
    const x = X0 + i * (3.9 + 0.2), y = 2.0;
    kart(s, x, y, 3.9, 4.2, "kart " + k2[i][1]);
    await ikonDaire(s, k2[i][0], x + 0.35, y + 0.4, 0.85, k2[i][1]);
    yazi(s, k2[i][1], { x: x + 0.35, y: y + 1.45, w: 3.2, h: 0.8, fontSize: 20, bold: true, valign: "middle" });
    yazi(s, k2[i][2], { x: x + 0.35, y: y + 2.4, w: 3.2, h: 1.7, fontSize: 15, color: C.text2 });
  }
  s.addNotes("Üç ilke bütün adımlarda geçerlidir. Ekiplere anlatırken en çok soru gelen konu: yapay zekâ " +
    "karar vermez, öneri verir; her sayı kod tarafından tam veride hesaplanır.");

  // 3 ILK TASARIMDAN BUGUNE ---------------------------------------------
  s = icerik("İlk tasarımdan bugüne ne değişti",
    "İlk akış yapay zekânın değişken önermesine odaklanıyordu; bugün süreç veriden final modele kadar uçtan uca.", B0);
  tablo(s, [
    ["Konu", "İlk tasarım", "Bugün"],
    ["Kapsam", "Sözlük sıkıştırma, yapay zekâ ile değişken üretimi, derleme ve model karşılaştırma",
      "Beş faz ve 25 adım (Baz Veri Seti Mevcut başlangıcında): kurulumdan değişken kataloğuna"],
    ["Sözlük", "Açıklamalar yapay zekânın okuyacağı kısa hâle getiriliyordu",
      "Dönem bilgisi, ad parçaları, kolon kartları ve kolon adları adım adım onaylanıyor; onaylanan bilgi hafızada"],
    ["Değişken üretimi", "Koşu başına 6 yapay zekâ önerisi",
      "41 dönüşümlük kural tabanlı üretim (katkısı ölçülerek) ve denetlenen ifadeyle yapay zekâ keşfi"],
    ["Veri kalitesi", "Kabul kararı istatistiksel testle",
      "25 kalite kontrolü, onaylı eşikler, düzeltme ve çözüm önerileri, ayrıca sızıntı kontrolü"],
    ["Veri", "Zenginleştirilmiş yeni veri seti yazılıyordu",
      "Girdiye yazılmaz; her çalışmanın kendi BAZ ve UPDT kopyaları"],
    ["Karar izi", "Kabul ve red kayıtları",
      "Her adımın kararı, gerekçesi ve üretim kodu kayıtlı; Arşiv ve 20 bölümlü model dokümanı"],
  ], { x: X0, y: 1.9, w: CW, colW: [2.1, 4.5, 5.533], fontSize: 13, ilkKalin: true, rowH: 0.62 });
  s.addNotes("İlk tasarımda akış: sözlük sıkıştırma, LLM ile koşu başına 6 değişken, değişken derleme ve " +
    "baz ile zengin modelin karşılaştırılması. Bugünkü yapı bu çekirdeği koruyor ama önüne veri ve sözlük " +
    "hazırlığını, kalite kontrollerini ve kural tabanlı üretimi; arkasına seçim, algoritma karşılaştırması, " +
    "finalizasyon ve dokümantasyonu ekliyor.");

  // 4 BES FAZ ---------------------------------------------------------
  pres.addSection({ title: B1 });
  s = icerik("Beş faz", "Her faz bir öncekinin sonucunu kullanır; adımlar sırayla açılır.", B1);
  const fazlar = [
    ["01", "Çalışma Kurulumu", "Veri seti, sözlük, kolon rolleri ve örneklem tasarımı",
      ["01.1 Başlangıç Seçimi", "01.2 Veri Seti, Sözlük ve Kolon Rolleri", "01.3 Değişken Listesi ve Tip Kontrolü", "01.4 Örneklem ve Doğrulama Tasarımı"]],
    ["02", "Değişken Mühendisliği", "Kalite kontrolü, kural tabanlı ve yapay zekâ destekli üretim",
      ["02.1 Veri Profili ve Kalite", "02.2 Kural Tabanlı Değişken Üretimi", "02.3 AI Değişken Keşfi"]],
    ["03", "Veri Anlama ve Hazırlama", "Hedefle ilişki, zamanda kararlılık ve sabit baz set",
      ["03.1 Tek Değişken Analizi (SFA)", "03.2 Stabilite Analizi (PSI)", "03.3 Analitik Baz Set"]],
    ["04", "Değişken Değerlendirme", "Sızıntının ayıklanması ve aday setin daraltılması",
      ["04.1 Sızıntı Kontrolü", "04.2 Aday Değişken Seti"]],
    ["05", "Modelleme ve Finalizasyon", "Karşılaştırma, seçim, doğrulama ve kayıt",
      ["05.1 Model Karşılaştırması", "05.2 Algoritma Seçimi", "05.3 Model Finalizasyonu", "05.4 Değişken Kataloğu"]],
  ];
  const fw = 2.3, fg = (CW - 5 * fw) / 4;
  ok(s, X0 + fw / 2, 2.3, X0 + 4 * (fw + fg) + fw / 2, 2.3, { bas: false, dash: "dash", color: C.accent6, width: 2, ad: "faz çizgisi" });
  fazlar.forEach((f, i) => {
    const x = X0 + i * (fw + fg);
    s.addShape(pres.shapes.OVAL, { x: x + fw / 2 - 0.45, y: 1.85, w: 0.9, h: 0.9, fill: { color: C.accent1 },
      line: { color: C.background1, width: 3 }, objectName: "faz " + f[0] });
    yazi(s, f[0], { x: x + fw / 2 - 0.45, y: 1.85, w: 0.9, h: 0.9, fontSize: 22, bold: true, color: C.background1, align: "center", valign: "middle" });
    yazi(s, f[1], { x, y: 2.9, w: fw, h: 0.6, fontSize: 17, bold: true, align: "center", valign: "middle" });
    yazi(s, f[2], { x, y: 3.5, w: fw, h: 0.75, fontSize: 12, color: C.text2, align: "center" });
    kart(s, x, 4.35, fw, 2.45, "faz " + f[0] + " adımları");
    yazi(s, madde(f[3], { bullet: false, paraSpaceAfter: 6 }), { x: x + 0.15, y: 4.5, w: fw - 0.3, h: 2.2, fontSize: 12 });
  });
  s.addNotes("01'deki 01.2 satırı bir gruptur: Baz Veri Seti ve Baz Sözlük, Kolon Rolleri, Eksik Sözlük Tanımları " +
    "ve isteğe bağlı Sözlük ve Kolon Adı Kontrolü bu grupta alt adımlar olarak çalışır. Kaynak Tablolar Mevcut " +
    "başlangıcında 01'e Kaynak Tablolar, Kaynak Sözlükleri ve Birleştirme Planı eklenir.");

  // 5 BIR ADIMIN YASAMI -------------------------------------------------
  s = icerik("Bir adım nasıl ilerler", "Her adım aynı döngüyü izler; onaydan önce hiçbir şey veriye yazılmaz.", B1);
  const dongu = [
    ["Analiz", "Kod", "Veri ve önceki kararlar okunur; sayımlar ve ölçümler verinin tamamında yapılır."],
    ["Öneri", "Yapay zekâ ve kod", "Öneri gerekçesiyle kartta sunulur; gerekçe sayıya dayanır."],
    ["İnceleme", "Siz", "Kart üzerinde seçer, düzenler, sorarsınız; sohbetle tartışabilirsiniz."],
    ["Onay", "Siz", "Onay düğmesi kararı kesinleştirir; onaylanmayan karar uygulanmaz."],
    ["Uygulama", "Kod", "Karar veriye uygulanır, gerekçe ve üretim kodu kayda geçer."],
  ];
  const dw = 2.35, dg = (CW - 5 * dw) / 4;
  dongu.forEach((d, i) => {
    const x = X0 + i * (dw + dg);
    s.addShape(i === 0 ? pres.shapes.PENTAGON : pres.shapes.CHEVRON, { x, y: 2.0, w: dw + 0.12, h: 0.95,
      fill: { color: d[1] === "Siz" ? C.accent3 : C.accent1 }, line: { type: "none" }, objectName: "döngü " + d[0] });
    yazi(s, d[0], { x: x + 0.3, y: 2.0, w: dw - 0.45, h: 0.95, fontSize: 17, bold: true, color: C.background1, align: "center", valign: "middle" });
    rozet(s, d[1], x + 0.2, 3.2, dw - 0.4, 0.4, { fill: C.background2, color: C.text1, fontSize: 12 });
    yazi(s, d[2], { x: x + 0.05, y: 3.8, w: dw - 0.1, h: 1.4, fontSize: 14, color: C.text2, align: "center" });
  });
  kart(s, X0, 5.45, CW, 1.3, "geri dön kartı", { fill: { color: C.accent1, transparency: 92 } });
  await ikonDaire(s, "FaArrowRotateLeft", X0 + 0.3, 5.67, 0.85, "Geri Dön");
  yazi(s, [
    { text: "Geri Dön ve Arşiv", options: { bold: true, fontSize: 16, breakLine: true } },
    { text: "Her adımın bloğunda Geri Dön düğmesi vardır; önceki bir karara dönülür ve o adımdan itibaren yeniden ilerlenir. " +
      "Çalışma her adımda kaydedilir, Arşiv'den kaldığı yerden açılır.", options: { fontSize: 14, color: C.text2 } },
  ], { x: X0 + 1.4, y: 5.6, w: CW - 1.7, h: 1.05, valign: "middle" });
  s.addNotes("Turuncu kutular insan onay noktalarıdır. Bazı adımlarda formun kendisi onaydır (ör. Kolon Rolleri), " +
    "bazılarında karar kartının onay düğmesi (ör. Veri Profili ve Kalite, Kural Tabanlı Değişken Üretimi).");

  // 6 MIMARI ----------------------------------------------------------
  s = icerik("Dataiku içinde nerede ne var", "Webapp, kütüphane ve Flow nesneleri; kullanıcı Flow'a elle bir şey eklemez.", B1);
  const mk = [
    [X0, "Webapp ön yüzü", "index.html · style.css · app.js", "Kartlar, tablolar, sohbet, İş Akışı"],
    [X0 + 2.95, "Webapp backend'i", "backend.py", "Uç noktalar, arka plan işleri, kayıt"],
    [X0 + 5.9, "fe_agent kütüphanesi", "Library Editor: python/fe_agent", "Akış ve adımlar, sözlük ve ad, kalite, üretim, analiz, model, doküman"],
  ];
  mk.forEach((m, i) => {
    kart(s, m[0], 2.3, 2.55, 3.1, m[1], { fill: { color: C.background2 } });
    yazi(s, m[1], { x: m[0] + 0.2, y: 2.45, w: 2.15, h: 0.75, fontSize: 17, bold: true, valign: "middle" });
    yazi(s, m[2], { x: m[0] + 0.2, y: 3.25, w: 2.15, h: 0.65, fontSize: 12, color: C.accent1, bold: true });
    yazi(s, m[3], { x: m[0] + 0.2, y: 3.95, w: 2.15, h: 1.35, fontSize: 13, color: C.text2 });
    if (i < 2) ok(s, m[0] + 2.58, 3.85, m[0] + 2.92, 3.85, { ad: "ok mimari " + i });
  });
  const sag = [
    ["Dil modeli", "Dataiku LLM Connections; adı ekranda hiçbir yerde gösterilmez"],
    ["Spark recipe'leri", "Tam veri işleri: profil, BAZ veri, UPDT veri. Webapp kendisi kurar"],
    ["Veri setleri", "<EK>_BAZ_VERI, <EK>_BAZ_SOZLUK, <EK>_UPDT_VERI, <EK>_UPDT_SOZLUK"],
    ["Managed folder'lar", "PROJE_HAFIZASI: çalışmalar ve hafıza. LLM_WEBAPP_GORSEL: görseller"],
  ];
  const sx = X0 + 8.95, sw = CW - 8.95;
  sag.forEach((r, i) => {
    const y = 1.9 + i * 1.0;
    kart(s, sx, y, sw, 0.88, r[0], { fill: { color: C.accent1, transparency: 92 } });
    yazi(s, [{ text: r[0], options: { bold: true, fontSize: 14, breakLine: true } },
      { text: r[1], options: { fontSize: 11, color: C.text2 } }], { x: sx + 0.15, y: y + 0.06, w: sw - 0.3, h: 0.76, valign: "middle" });
    ok(s, X0 + 8.48, 3.85, sx - 0.03, y + 0.44, { ad: "ok hedef " + i });
  });
  yazi(s, [{ text: "Boyut kuralı: ", options: { bold: true } },
    { text: "0,25 GB'a kadar veri pandas ile, üstü Spark ile kümede işlenir (proje değişkeni amp_pandas_sinir_gb). " +
      "fe_agent ya da backend.py değişince webapp backend'i yeniden başlatılır; yalnız ön yüz değişince sayfayı yenilemek yeter." }],
    { x: X0, y: 5.95, w: CW, h: 0.8, fontSize: 13, color: C.text2 });
  s.addNotes("Dosyaların Dataiku'daki yerleri: fe_agent/*.py Library Editor'da python/fe_agent altında; " +
    "index.html, style.css, app.js ve backend.py webapp'in HTML, CSS, JS ve Python sekmelerinde. " +
    "<EK> çalışmanın kısa adıdır (ör. V8).");

  // 7 VERI KURALI -----------------------------------------------------
  s = icerik("Veri kuralı: girdinize dokunulmaz",
    "Seçilen veri setine ve sözlüğe hiçbir şey yazılmaz; her çalışma Flow'a yalnız kendi dört veri setini yazar.", B1);
  const vs = [
    ["<EK>_BAZ_VERI", "Veri seçilince, bir kez", "Seçilen tablonun birebir kopyası; kaynak tablolarla başlandıysa birleştirme sonucu. Bir daha değişmez."],
    ["<EK>_BAZ_SOZLUK", "Sözlük seçilince, bir kez", "Seçilen sözlüğün (birden çoksa birleştirilmiş hâlinin) birebir kopyası. Bir daha değişmez."],
    ["<EK>_UPDT_VERI", "01.3'ten itibaren", "Verinin en son hâli: tip dönüşümleri, yeni adlar, bölme, düzeltmeler ve üretilen değişkenler."],
    ["<EK>_UPDT_SOZLUK", "Her adım sonunda", "Sözlüğün en son hâli; içerik değişmediyse yeniden yazılmaz."],
  ];
  const vw = (CW - 3 * 0.2) / 4;
  vs.forEach((v, i) => {
    const x = X0 + i * (vw + 0.2), baz = i < 2;
    kart(s, x, 1.95, vw, 2.45, v[0], { fill: { color: baz ? C.background2 : C.accent1, transparency: baz ? 0 : 92 } });
    yazi(s, v[0], { x: x + 0.2, y: 2.05, w: vw - 0.4, h: 0.5, fontSize: 15, bold: true, color: baz ? C.text1 : C.accent1, valign: "middle" });
    yazi(s, v[1], { x: x + 0.2, y: 2.55, w: vw - 0.4, h: 0.35, fontSize: 12, bold: true, color: C.text2 });
    yazi(s, v[2], { x: x + 0.2, y: 2.95, w: vw - 0.4, h: 1.4, fontSize: 13, color: C.text2 });
  });
  yazi(s, "UPDT verinin aşamaları: her adım bir öncekinin tablosunun üstüne ekler", { x: X0, y: 4.65, w: CW, h: 0.4, fontSize: 16, bold: true });
  const asama = [["01.3", "Tip dönüşümleri, çıkarılan kolonlar, yeni adlar"], ["01.4", "_SPLIT kolonu (bölme)"],
    ["02.1", "Düzeltmeler ve çözüm kolonları"], ["02.2", "Kural tabanlı üretim"], ["02.3", "Yapay zekâ keşfi"], ["03.3", "Analitik baz set"]];
  const aw = CW / 6;
  ok(s, X0 + aw / 2, 5.45, X0 + 5.5 * aw, 5.45, { bas: false, color: C.accent6, width: 2, ad: "aşama çizgisi" });
  asama.forEach((a, i) => {
    const x = X0 + i * aw;
    rozet(s, a[0], x + aw / 2 - 0.45, 5.25, 0.9, 0.4, { fontSize: 13 });
    yazi(s, a[1], { x: x + 0.05, y: 5.8, w: aw - 0.1, h: 0.9, fontSize: 12, color: C.text2, align: "center" });
  });
  s.addNotes("Geri dönülüp UPDT ileride kalmışsa istenen aşamanın tablosu BAZ veriden kararlar yeniden uygulanarak kurulur. " +
    "Profil, SFA ve PSI tabloları Flow'a veri seti olarak yazılmaz; çalışma klasöründe iç kayıt olarak durur. " +
    "Çalışma kopyalanınca BAZ veri ve sözlük paylaşılır, UPDT kopyaları yeni çalışmanın adına kopyalanır.");

  // 8 YAPAY ZEKA VE KOD -----------------------------------------------
  s = icerik("Yapay zekâ ve kod: iş bölümü", "Yapay zekâ önerir ve yorumlar; hesaplamayı her zaman kod yapar.", B1);
  const iki = [
    ["FaWandMagicSparkles", "Yapay zekânın yaptıkları", [
      "Kaynak tablolar için birleştirme planı önerir",
      "Eksik sözlük tanımlarını, dönem ve ad parçası anlamlarını, açıklama düzeltmelerini önerir",
      "Kalite kontrollerinde anlam gerektiren kararları önerir (gelecek penceresi, gizli eksik, aynı içerikli kolonlardan hangisi kalır)",
      "Hangi birime hangi dönüşümün uygulanacağını gerekçesiyle seçer",
      "Elle düşünülmesi zor değişken hipotezlerini denetlenen ifadeyle yazar",
      "Her değişkenin modele hangi hâliyle gireceğini önerir; sorularınızı yanıtlar"]],
    ["FaGears", "Kodun yaptıkları", [
      "Bütün sayımları, istatistikleri ve ölçümleri verinin tamamında yapar; büyük veri Spark ile",
      "Kolon kartlarını onaylı parçalardan kurar, yapay zekâ cevabını denetler",
      "Dönüşümün birimde mümkün olup olmadığına ve katkısına karar verir",
      "Onaylanan değişkenleri üretir, ifadeleri güvenlik denetiminden geçirir",
      "Bölme, doldurma, eleme ve model eğitimini yapar",
      "Kararları, üretim kodunu, kataloğu ve model dokümanını kaydeder"]],
  ];
  for (let i = 0; i < 2; i++) {
    const x = X0 + i * (5.965 + 0.2);
    kart(s, x, 1.9, 5.965, 4.9, iki[i][1], { fill: { color: i ? C.background2 : C.accent1, transparency: i ? 0 : 92 } });
    await ikonDaire(s, iki[i][0], x + 0.3, 2.1, 0.75, iki[i][1]);
    yazi(s, iki[i][1], { x: x + 1.25, y: 2.1, w: 4.4, h: 0.75, fontSize: 20, bold: true, valign: "middle" });
    yazi(s, madde(iki[i][2], { paraSpaceAfter: 7 }), { x: x + 0.3, y: 3.05, w: 5.4, h: 3.6, fontSize: 14, color: C.text2 });
  }
  s.addNotes("Dil modeli cevap veremezse ya da süre aşılırsa adım kodun kendi kural önerisiyle devam eder; " +
    "yapay zekânın her önerisi kartta öneren bilgisiyle görünür ve değiştirilebilir.");

  // 9 BOLUM: FAZLAR ---------------------------------------------------
  pres.addSection({ title: B2 });
  s = pres.addSlide({ masterName: "BOLUM", sectionTitle: B2 });
  s.addText("01 ile 05", { placeholder: "no" });
  s.addText("Fazlar adım adım", { placeholder: "title" });
  s.addText("Her adımda ne yapılır, kim karar verir ve sonuç nereye yazılır", { placeholder: "body" });

  // 10 FAZ 01 ---------------------------------------------------------
  s = icerik("01 Çalışma Kurulumu", "Hangi tabloyla çalışılacağı, kolonların ne anlama geldiği, hedef ve bölme bu fazda belirlenir.", B2);
  const f1 = [
    ["01.1", "Başlangıç Seçimi", "Baz Veri Seti Mevcut ya da Kaynak Tablolar Mevcut. İkincisinde yapay zekâ iskelet tabloyu, anahtarları ve zaman pencereli toplamaları önerir; her satır yalnız kendi tarihinden önceki bilgiyi görür."],
    ["01.2.1", "Baz Veri Seti ve Baz Sözlük", "Veri seti ve varsa sözlük seçilir; birden çok sözlükte farklı tanımı olan kolonlar 01.2.1.1'de çözülür."],
    ["01.2.2", "Kolon Rolleri", "Model tipi, hedef, kimlik ve dönem kolonu. Bu kolonlar hiçbir dönüşüme girmez."],
    ["01.2.3", "Eksik Sözlük Tanımları", "Tanımsız kolonlara onaylı tanımlardan ve yapay zekâdan öneri. 01.2.3.1'de boş ve tek değerli kolonlar çıkarılır."],
    ["01.2.4", "Sözlük ve Kolon Adı Kontrolü", "İsteğe bağlı dört alt adım: Dönem Bilgisi, Ad Parçaları, Kolon Kartları, Kolon Adları."],
    ["01.3", "Değişken Listesi ve Tip Kontrolü", "Liste, tipler ve tanımlar son kez gözden geçirilir; UPDT veri ve sözlük ilk kez yazılır."],
    ["01.4", "Örneklem ve Doğrulama Tasarımı", "Train, Test ve Validasyon setleri. Bu sınır sızıntı sınırıdır."],
  ];
  const rw = (CW - 0.3) / 2;
  f1.forEach((r, i) => {
    const sut = i < 4 ? 0 : 1, sira = i < 4 ? i : i - 4;
    const x = X0 + sut * (rw + 0.3), y = 1.85 + sira * 1.25;
    kart(s, x, y, rw, 1.12, "adım " + r[0]);
    rozet(s, r[0], x + 0.18, y + 0.33, 0.95, 0.42, { fontSize: 13 });
    yazi(s, [{ text: r[1], options: { bold: true, fontSize: 15, breakLine: true } },
      { text: r[2], options: { fontSize: 12, color: C.text2 } }], { x: x + 1.3, y: y + 0.06, w: rw - 1.45, h: 1.0, valign: "middle" });
  });
  kart(s, X0 + rw + 0.3, 1.85 + 3 * 1.25, rw, 1.12, "B başlangıcı notu", { fill: { color: C.accent3, transparency: 88 } });
  yazi(s, [{ text: "Kaynak Tablolar Mevcut ile başlanırsa", options: { bold: true, fontSize: 14, breakLine: true } },
    { text: "Kaynak Tablolar, Kaynak Sözlükleri ve Birleştirme Planı adımları eklenir; numaralar 01.2 ile 01.7 arasına kayar.", options: { fontSize: 12, color: C.text2 } }],
    { x: X0 + rw + 0.5, y: 1.85 + 3 * 1.25 + 0.06, w: rw - 0.4, h: 1.0, valign: "middle" });
  s.addNotes("Numaralar Baz Veri Seti Mevcut başlangıcına göredir. Hedef, kimlik ve dönem kolonunun sözlük tanımı zorunludur. " +
    "Tablonun önceki seçimleri (roller, sözlük eşleşmesi) hatırlanır ve yeni çalışmada önerilir. Otomatik Pilot başlangıcı şu an kapalıdır.");

  // 11 01.2.4 ---------------------------------------------------------
  s = icerik("01.2.4 Sözlük ve Kolon Adı Kontrolü",
    "Kolon adları parçalarına ayrılır; her parçanın anlamı bir kez onaylanır, açıklamalar ve adlar bu onaylı bilgiden kurulur.", B2);
  kart(s, X0, 1.85, CW, 0.6, "örnek kolon", { fill: { color: C.background2 } });
  yazi(s, [{ text: "Örnek kolon adı:  ", options: { color: C.text2 } }, { text: "TRX_OUT_AMT_L30D", options: { bold: true, fontFace: "Courier New" } },
    { text: "   (gösterim amaçlı)", options: { color: C.text2, fontSize: 12 } }],
    { x: X0 + 0.25, y: 1.85, w: CW - 0.5, h: 0.6, fontSize: 15, valign: "middle" });
  const kt = [
    ["01.2.4.1", "Dönem Bilgisi", "L30D = son 30 gün", "Sayılı zaman parçalarının anlamı ve türü onaylanır. Altı tür: son, önce, sonraki, sonra, çevre, süre. Geleceğe bakan pencere 02.1'de sızıntı olarak sorulur."],
    ["01.2.4.2", "Ad Parçaları", "TRX = işlem, OUT = giden, AMT = tutar", "Kısaltma ve sözcüklerin anlamı, türü ve standart yazılışı onaylanır; farklı yazılan aynı parçalar birleşir."],
    ["01.2.4.3", "Kolon Kartları", "Son 30 günde giden işlemlerin toplam tutarı", "Kart onaylı parçalardan kodla kurulur, sözlük tanımıyla karşılaştırılır; tek açık açıklama yazılır. Sorular toplu, aileler toplu onaylanır."],
    ["01.2.4.4", "Kolon Adları", "Ad Standardı sırasıyla yeni ad", "Yeni ad standart yazılışlarla kurulur; sıra sürükle bırakla belirlenir. Eski ad saklanır, yeni ad yalnız platform kopyalarında geçerli."],
  ];
  const kw = (CW - 3 * 0.3) / 4;
  kt.forEach((k, i) => {
    const x = X0 + i * (kw + 0.3), y = 2.7;
    kart(s, x, y, kw, 3.55, "kontrol " + k[0], { fill: { color: C.background1 }, line: { color: C.accent6, width: 1 } });
    rozet(s, k[0], x + 0.2, y + 0.2, 1.15, 0.38, { fontSize: 12 });
    yazi(s, k[1], { x: x + 0.2, y: y + 0.68, w: kw - 0.4, h: 0.45, fontSize: 17, bold: true });
    kart(s, x + 0.2, y + 1.15, kw - 0.4, 0.72, "örnek " + k[0], { fill: { color: C.accent1, transparency: 92 } });
    yazi(s, k[2], { x: x + 0.3, y: y + 1.15, w: kw - 0.6, h: 0.72, fontSize: 13, bold: true, color: C.accent5, valign: "middle" });
    yazi(s, k[3], { x: x + 0.2, y: y + 2.0, w: kw - 0.4, h: 1.5, fontSize: 12, color: C.text2 });
    if (i < 3) ok(s, x + kw + 0.03, y + 1.5, x + kw + 0.27, y + 1.5, { ad: "ok kontrol " + i });
  });
  yazi(s, [{ text: "Hafıza: ", options: { bold: true } }, { text: "onaylanan dönem kalıpları, parçalar ve tanımlar PROJE_HAFIZASI'na yazılır; aynı parça bir daha sorulmaz. " +
    "Yeni çalışmada önceki onaylı kontrol bütünüyle uygulanabilir." }], { x: X0, y: 6.4, w: CW, h: 0.5, fontSize: 13, color: C.text2 });
  s.addNotes("Örnek kolon adı ve anlamları yalnız gösterim içindir. Kontrol seçilmezse dört alt adım atlanır, açıklamalar ve adlar olduğu gibi kalır. " +
    "Koşullu anlam: bir kalıp, adda belirli bir parça geçtiğinde başka anlama gelebilir (ör. adda RATIO geçerse); bu da kaydedilir. " +
    "Kolon Kartları'nda üç dil modeli çağrısı yazar, denetçi ve karar rolündedir; kod her cevabı denetler.");

  // 12 01.4 -----------------------------------------------------------
  s = icerik("01.4 Örneklem ve Doğrulama Tasarımı", "Veri üç sete ayrılır; bu sınır aynı zamanda sızıntı sınırıdır.", B2);
  const setler = [["Train (MS)", "Modelin öğrendiği set", C.accent1, 0], ["Test (OOS)", "Ayarların seçildiği set", C.accent5, 0], ["Validasyon (OOT)", "Nihai ölçümün yapıldığı, zamanda sonraki set", C.text2, 0]];
  const sw3 = [5.6, 3.0, 3.533];
  let sx3 = X0;
  setler.forEach((t, i) => {
    s.addShape(pres.shapes.RECTANGLE, { x: sx3, y: 2.0, w: sw3[i] - 0.04, h: 0.9, fill: { color: t[2] }, line: { type: "none" }, objectName: "set " + t[0] });
    yazi(s, t[0], { x: sx3, y: 2.0, w: sw3[i] - 0.04, h: 0.9, fontSize: 18, bold: true, color: C.background1, align: "center", valign: "middle" });
    yazi(s, t[1], { x: sx3, y: 3.0, w: sw3[i] - 0.04, h: 0.5, fontSize: 13, color: C.text2, align: "center" });
    sx3 += sw3[i];
  });
  yazi(s, "Çubuktaki genişlikler oran göstermez; oranlar kartta önerilir ya da siz belirlersiniz.", { x: X0, y: 3.45, w: CW, h: 0.35, fontSize: 11, color: C.accent2, italic: true });
  const b4 = [
    ["FaShieldHalved", "Yalnız Train'den öğrenilir", "Doldurma değerleri, kırpma sınırları, dilimler, WoE ve hedef ortalaması, model eğitimi. WoE ve hedef ortalaması Train içinde kat dışı hesaplanır."],
    ["FaClock", "Zamansal ya da kimlik bazlı", "Dönem kolonu varsa zamansal bölme ve aradaki boşluk; kimlik bazlı bölmede aynı müşteri iki tarafta kalmaz."],
    ["FaSliders", "Önerilen ya da özel ayar", "Kart iki modla gelir: Önerilen Ayarlar ve Özel Ayarlar. Tek onay düğmesi vardır; sonuç _SPLIT kolonu olarak UPDT veriye yazılır."],
  ];
  for (let i = 0; i < 3; i++) {
    const x = X0 + i * (3.911 + 0.2);
    kart(s, x, 4.05, 3.911, 2.75, b4[i][1]);
    await ikonDaire(s, b4[i][0], x + 0.25, 4.25, 0.7, b4[i][1]);
    yazi(s, b4[i][1], { x: x + 1.1, y: 4.25, w: 2.6, h: 0.7, fontSize: 16, bold: true, valign: "middle" });
    yazi(s, b4[i][2], { x: x + 0.25, y: 5.1, w: 3.45, h: 1.6, fontSize: 13, color: C.text2 });
  }
  s.addNotes("Bölme tarifi kayda geçer; geri dönülünce tablo BAZ veriden aynı tarifle yeniden kurulur. " +
    "Veri Profili ve Kalite bütün satırlarda çalışır, ama çözüm ve dönüşüm parametreleri yalnız Train satırlarından öğrenilir.");

  // 13 02.1 -----------------------------------------------------------
  s = icerik("02.1 Veri Profili ve Kalite", "Tablonun tamamında 25 kontrol; kusurlu kolonlar için önce çözüm aranır, çözüm yoksa üretime girmez.", B2);
  const akis21 = [["Eşik formu", "Eşikler önerilen değer ve gerekçesiyle sorulur"], ["Kontroller", "Bütün satırlarda, örneklemesiz"],
    ["Karar kartı", "Yeşil sorunsuz, sarı dikkat, kırmızı üretime girmez"], ["Onay", "Düzeltme ve çözüm kolonları UPDT veriye"]];
  akis21.forEach((a, i) => {
    const y = 1.9 + i * 1.05;
    rozet(s, String(i + 1), X0, y + 0.15, 0.5, 0.5, { fontSize: 15 });
    yazi(s, [{ text: a[0], options: { bold: true, fontSize: 15, breakLine: true } }, { text: a[1], options: { fontSize: 12, color: C.text2 } }],
      { x: X0 + 0.7, y, w: 3.0, h: 0.85, valign: "middle" });
    if (i < 3) ok(s, X0 + 0.25, y + 0.68, X0 + 0.25, y + 1.17, { ad: "ok 02.1 " + i });
  });
  const gr = [
    ["Sızıntı", "Çıkar seçili gelir", "Gelecek penceresi, hedefle neredeyse birebir ilişki"],
    ["Düzeltme", "Doğrudan kolona uygulanır", "Özel tarih kodu, metin olarak yazılmış boş, yazım tutarsızlığı, beklenmeyen negatif, uç değer, gizli eksik, ondalık"],
    ["Karar", "Tut ya da Çıkar, sayıyla önerilir", "Neredeyse sabit, dönemde boş ya da sabit, eksik sıçraması, dönemler arası değer kayması, dönemden sonraki tarih"],
    ["Çözüm önerisi", "Ham kolon yerine yeni kolon", "Hedef oranına ya da kod önekine göre gruplama, seyrek değerleri toplama, dolu mu bayrağı, metinden özellik, tarihten gün farkı"],
  ];
  const gx = X0 + 4.0, gw = (CW - 4.0 - 0.2) / 2;
  gr.forEach((g, i) => {
    const x = gx + (i % 2) * (gw + 0.2), y = 1.9 + Math.floor(i / 2) * 2.1;
    kart(s, x, y, gw, 1.95, "grup " + g[0], { fill: { color: i === 0 ? C.accent1 : C.background2, transparency: i === 0 ? 90 : 0 } });
    yazi(s, g[0], { x: x + 0.2, y: y + 0.12, w: gw - 0.4, h: 0.4, fontSize: 16, bold: true, color: i === 0 ? C.accent1 : C.text1 });
    yazi(s, g[1], { x: x + 0.2, y: y + 0.52, w: gw - 0.4, h: 0.3, fontSize: 12, bold: true, color: C.text2 });
    yazi(s, g[2], { x: x + 0.2, y: y + 0.85, w: gw - 0.4, h: 1.05, fontSize: 12, color: C.text2 });
  });
  yazi(s, [{ text: "Öneriyi kim verir: ", options: { bold: true } },
    { text: "çoğunu kod verir, kolonun kendi sayılarına bakarak. Dil modeli yalnız anlam isteyen beş kontrolde ve aynı içerikli kolonlardan hangisinin kalacağında önerir. " +
      "Çözüm seçeneği yalnız işe yarayacaksa sunulur: Train'in bir yarısında öğrenilip öbür yarısında sınanır." }],
    { x: X0, y: 6.2, w: CW, h: 0.7, fontSize: 12, color: C.text2 });
  s.addNotes("Temel kontroller: eksik oranı, sabit, kimlik benzeri, kardinalite, aynı içerikli kolonlar, neredeyse sabit, dönemde boş ya da sabit, " +
    "gizli eksik, sıfır yoğunluğu, beklenmeyen negatif, eksik sıçraması, uç değer, tekrar eden satır ve hedef dağılımı. Ek olarak sızıntı, tarih ve " +
    "ad tabanlı kontroller, neredeyse aynı kolonlar, pencere tutarlılığı ve tutar adet uyumu. Metinden özellik dil modeli kullanmaz: sözcük sayısı, " +
    "sözcüklerin hedef skoru, anlamlı sözcük bayrakları ve konu kolonları kodla, bütün satırlarda üretilir.");

  // 14 02.2 UC ASAMA --------------------------------------------------
  s = icerik("02.2 Kural Tabanlı Değişken Üretimi: üç aşama",
    "Öneriler birim birim yapılır; her dönüşümün aşaması, neye göre üretildiğini söyler.", B2);
  const ua = [
    ["1", "Kolonun kendi dönüşümü", "Tek kolon ya da bir ailenin her penceresi kendi içinde dönüştürülür.",
      "Logaritma, uç kırpma, sıra, z skor, sıfır ve eşik bayrağı, dilim, kategori için risk puanı (WoE) ve hedef ortalaması",
      "TRX_OUT_AMT_L30D → logaritması"],
    ["2", "Aile içi üretim", "Aynı ölçünün farklı pencereleri birbiriyle karşılaştırılır.",
      "Pencereler arası oran ve fark, büyüme, eğilim, düzensizlik, bütün pencere çiftleri, dönem parçaları",
      "TRX_OUT_AMT_L30D bölü TRX_OUT_AMT_L90D"],
    ["3", "Aileler arası üretim", "Anlamlı iki ya da daha çok aile birleştirilir.",
      "Net (gelen eksi giden), oran, ortalama tutar (tutar bölü adet), pay, çarpım, kesişim, yoğunlaşma",
      "TRX_IN_AMT_L30D eksi TRX_OUT_AMT_L30D"],
  ];
  const uw = (CW - 0.4) / 3;
  ua.forEach((u, i) => {
    const x = X0 + i * (uw + 0.2);
    kart(s, x, 1.85, uw, 4.25, "aşama " + u[0]);
    s.addShape(pres.shapes.OVAL, { x: x + 0.25, y: 2.05, w: 0.65, h: 0.65, fill: { color: C.accent1 }, line: { type: "none" }, objectName: "aşama no " + u[0] });
    yazi(s, u[0], { x: x + 0.25, y: 2.05, w: 0.65, h: 0.65, fontSize: 20, bold: true, color: C.background1, align: "center", valign: "middle" });
    yazi(s, u[1], { x: x + 1.05, y: 2.05, w: uw - 1.25, h: 0.65, fontSize: 18, bold: true, valign: "middle" });
    yazi(s, u[2], { x: x + 0.25, y: 2.85, w: uw - 0.5, h: 0.7, fontSize: 13, color: C.text2 });
    yazi(s, "Dönüşümler", { x: x + 0.25, y: 3.6, w: uw - 0.5, h: 0.3, fontSize: 12, bold: true, color: C.accent1 });
    yazi(s, u[3], { x: x + 0.25, y: 3.9, w: uw - 0.5, h: 1.15, fontSize: 13 });
    kart(s, x + 0.25, 5.15, uw - 0.5, 0.75, "örnek aşama " + u[0], { fill: { color: C.background1 }, line: { color: C.accent6, width: 1 } });
    yazi(s, u[4], { x: x + 0.35, y: 5.15, w: uw - 0.7, h: 0.75, fontSize: 12, fontFace: "Courier New", valign: "middle", align: "center" });
  });
  yazi(s, [{ text: "Birim: ", options: { bold: true } },
    { text: "tek kolon, pencere ailesi (aynı ölçünün farklı pencereleri), anlamlı kolon çifti ya da grubu ve satır. Hedef, kimlik, dönem, süreç dışı ve 02.1'de üretime girmeyen kolonlardan üretim yapılmaz. " +
      "Toplam 41 dönüşüm; ağaç ve doğrusal model ayrımı yok, ikisinde de kullanılabilecek bütün dönüşümler tek seferde değerlendirilir." }],
    { x: X0, y: 6.2, w: CW, h: 0.7, fontSize: 12, color: C.text2 });
  s.addNotes("Örnek kolon adları gösterim amaçlıdır. Her dönüşümün kartta sade adı, ne yaptığı, kolon üzerinden örneği, ne zaman işe yaradığı ve " +
    "bu veride neden kullanılabilir ya da kullanılamaz olduğu yazar; bu durumlara göre süzülebilir.");

  // 15 02.2 KARAR ZINCIRI ---------------------------------------------
  s = icerik("02.2 Öneri nasıl kurulur", "Kod birimleri ve uygunluğu belirler, dil modeli seçer, ölçüm doğrular, siz son kararı verirsiniz.", B2);
  const zz = [
    ["Birimler", "Kod", "Aileler, çiftler, gruplar ve tek kolonlar kurulur"],
    ["Uygunluk", "Kod", "Dönüşüm birimde mümkün mü, değilse neden"],
    ["Seçim", "Dil modeli", "Birim başına gerekçeli seçim, üç tur, paralel"],
    ["Katkı ölçümü", "Kod", "Train satırlarında IV ve kaynaklarla ilişki"],
    ["Tamamlama", "Kod", "Yeni bilgi getiren ama seçilmemiş dönüşüm eklenir"],
    ["Karar", "Siz", "Kart ve sohbetle; onayda kod üretir"],
  ];
  const zw = (CW - 5 * 0.15) / 6;
  zz.forEach((z, i) => {
    const x = X0 + i * (zw + 0.15);
    s.addShape(i === 0 ? pres.shapes.PENTAGON : pres.shapes.CHEVRON, { x, y: 1.9, w: zw + 0.1, h: 0.8,
      fill: { color: z[1] === "Siz" ? C.accent3 : C.accent1 }, line: { type: "none" }, objectName: "zincir " + z[0] });
    yazi(s, z[0], { x: x + 0.22, y: 1.9, w: zw - 0.3, h: 0.8, fontSize: 14, bold: true, color: C.background1, align: "center", valign: "middle" });
    yazi(s, z[1], { x, y: 2.8, w: zw, h: 0.3, fontSize: 12, bold: true, color: C.text1, align: "center" });
    yazi(s, z[2], { x: x + 0.05, y: 3.1, w: zw - 0.1, h: 0.9, fontSize: 12, color: C.text2, align: "center" });
  });
  kart(s, X0, 4.15, CW, 0.75, "katkı ölçütü", { fill: { color: C.accent1, transparency: 92 } });
  yazi(s, [{ text: "Yeni bilgi ölçütü: ", options: { bold: true, color: C.accent5 } },
    { text: "IV artışı (en iyi kaynağa göre) en az 0,02 ve kaynaklarla sıra ilişkisi 0,95'ten düşük. Ölçek dönüşümleri (logaritma, kırpma, sıra) IV'yi değiştirmediği için çarpıklık ve uç değere göre önerilir." }],
    { x: X0 + 0.25, y: 4.15, w: CW - 0.5, h: 0.75, fontSize: 13, valign: "middle" });
  const oz = [
    ["FaTableList", "Canlı kart", "Dönüşümler tablosu: uygulanabilir, önerilen, seçili sayıları her tıklamada güncellenir. Son değişiklikler günlüğü ve Geri al."],
    ["FaComments", "Plan üzerine sohbet", "Toplu istekler (ör. bütün oranları kaldır) ölçümle cevaplanır; değişiklikleri kod kurar, siz onaylarsınız. Kısa hafıza tutulur."],
    ["FaFloppyDisk", "Kalıcı kararlar", "Öneriden farklı her seçiminiz ayrı saklanır; plan yeniden kurulunca çıkardığınız geri gelmez."],
  ];
  for (let i = 0; i < 3; i++) {
    const x = X0 + i * (3.911 + 0.2);
    kart(s, x, 5.1, 3.911, 1.75, oz[i][1]);
    await ikonDaire(s, oz[i][0], x + 0.2, 5.25, 0.6, oz[i][1]);
    yazi(s, oz[i][1], { x: x + 0.95, y: 5.25, w: 2.8, h: 0.6, fontSize: 15, bold: true, valign: "middle" });
    yazi(s, oz[i][2], { x: x + 0.2, y: 5.92, w: 3.5, h: 0.9, fontSize: 11.5, color: C.text2 });
  }
  s.addNotes("Dil modeli çağrıları arka plan işinde çalışır, kart beklerken ilerlemeyi gösterir. Aynı birim için önceki öneri tekrar sorulmaz. " +
    "Öğrenilen parametreler (kırpma sınırı, dilim sınırları, WoE haritası) yalnız Train satırlarından alınır ve her kolonun üretim kodu satırına gömülür.");

  // 16 02.3 -----------------------------------------------------------
  s = icerik("02.3 AI Değişken Keşfi", "Dil modeli kod yazmaz; yalnız denetlenen kısıtlı bir ifade yazar.", B2);
  const kz = [["Girdi", "Sözlük ve kolonlar; kusurlu ve üretilmiş kolonlar hariç"], ["Hipotez", "Dil modeli değişken fikri ve ifadesini yazar"],
    ["Denetim", "İfade ağaç olarak ayrıştırılır, düğüm düğüm izin kontrolü"], ["Hesap", "Kod kendi yürütücüsüyle hesaplar, eval yok"], ["Kayıt", "Geçenler UPDT veriye, okunur Python satırıyla"]];
  const kzw = (CW - 4 * 0.3) / 5;
  kz.forEach((k, i) => {
    const x = X0 + i * (kzw + 0.3);
    kart(s, x, 1.9, kzw, 1.7, "keşif " + k[0], { fill: { color: i === 2 ? C.accent1 : C.background2, transparency: i === 2 ? 90 : 0 } });
    yazi(s, k[0], { x: x + 0.15, y: 2.0, w: kzw - 0.3, h: 0.45, fontSize: 16, bold: true, align: "center", color: i === 2 ? C.accent1 : C.text1 });
    yazi(s, k[1], { x: x + 0.15, y: 2.5, w: kzw - 0.3, h: 1.0, fontSize: 12, color: C.text2, align: "center" });
    if (i < 4) ok(s, x + kzw + 0.03, 2.75, x + kzw + 0.27, 2.75, { ad: "ok keşif " + i });
  });
  kart(s, X0, 3.9, 6.0, 2.9, "ifade örnekleri", { fill: { color: C.text1 } });
  yazi(s, "İzin verilen ifade örnekleri", { x: X0 + 0.3, y: 4.05, w: 5.4, h: 0.4, fontSize: 14, bold: true, color: C.background1 });
  yazi(s, "KOL_A / KOL_B\nlog1p(KOL_C) - KOL_D\nclip(KOL_E / (KOL_F + 1), 0, 10)",
    { x: X0 + 0.3, y: 4.55, w: 5.4, h: 1.5, fontSize: 16, fontFace: "Courier New", color: C.background1 });
  yazi(s, "KOL harfleri yer tutucudur.", { x: X0 + 0.3, y: 6.25, w: 5.4, h: 0.35, fontSize: 11, color: C.accent6, italic: true });
  yazi(s, [{ text: "Kurallar", options: { bold: true, fontSize: 16, breakLine: true } },
    ...madde([
      "İzinli fonksiyonlar: log1p, abs, sqrt, rank, clip, fark",
      "İzinli işlemler: toplama, çıkarma, çarpma, bölme",
      "İfadede yalnız var olan ve izinli kolonlar geçebilir; kusurlu kolon geçerse reddedilir",
      "Yapay zekânın yanılgısı koda dönüşemez, sonuç yine tekrar üretilebilir Python'dur",
    ], { fontSize: 14, color: C.text2, paraSpaceAfter: 6 })], { x: X0 + 6.3, y: 3.95, w: CW - 6.3, h: 2.85 });
  s.addNotes("Kural tabanlı adımın kalıplarının dışında kalan, elle düşünülmesi zor değişkenleri bulmak içindir. " +
    "Adım yeniden çalıştırılırsa önceki turun kolonları ve kayıtları temizlenip yenisi yazılır.");

  // 17 FAZ 03 ---------------------------------------------------------
  s = icerik("03 Veri Anlama ve Hazırlama", "Ham ve üretilen bütün değişkenler ölçülür; sonunda modellemeye hazır, sabit bir set oluşur.", B2);
  const f3 = [
    ["03.1", "FaChartColumn", "Tek Değişken Analizi (SFA)", "Her değişkenin hedefle ilişkisi: bilgi değeri (IV), beş dönüşümle ayrıştırma gücü, hedefe göre aralıklar. Eleme yapılmaz; yapay zekâ her değişkenin modele hangi hâliyle gireceğini önerir. Kararlar Model Değişkenleri sayfasında grafikleriyle değiştirilebilir."],
    ["03.2", "FaChartLine", "Stabilite Analizi (PSI)", "Değişken dağılımlarının dönemler arasında kayıp kaymadığı ölçülür; zamanda kararsız değişkenler görünür olur. Zamansal bölme gerektirir."],
    ["03.3", "FaLock", "Analitik Baz Set", "Kusurlu kolonlar düşürülür, SFA kararları uygulanır, eksik değerler yalnız Train istatistikleriyle doldurulur ve set dondurulur. Sonraki bütün adımlar bu sabit set üzerinde çalışır."],
  ];
  for (let i = 0; i < 3; i++) {
    const x = X0 + i * (3.911 + 0.2), f = f3[i];
    kart(s, x, 1.9, 3.911, 4.5, f[2]);
    await ikonDaire(s, f[1], x + 0.3, 2.15, 0.85, f[2]);
    rozet(s, f[0], x + 2.6, 2.37, 1.0, 0.42, { fontSize: 13 });
    yazi(s, f[2], { x: x + 0.3, y: 3.2, w: 3.3, h: 0.75, fontSize: 18, bold: true, valign: "middle" });
    yazi(s, f[3], { x: x + 0.3, y: 4.05, w: 3.3, h: 2.6, fontSize: 13.5, color: C.text2 });
  }
  s.addNotes("03.3'te yazılan tablo UPDT verinin 03.3 aşamasıdır ve 04 ile 05 oradan okur.");

  // 18 FAZ 04 ve 05 ---------------------------------------------------
  s = icerik("04 Değişken Değerlendirme ve 05 Modelleme", "Değişkenler daraltılır, modeller aynı koşullarda karşılaştırılır, seçilen model doğrulanıp kaydedilir.", B2);
  kart(s, X0, 1.9, 5.9, 4.9, "faz 04");
  yazi(s, "04 Değişken Değerlendirme", { x: X0 + 0.3, y: 2.05, w: 5.3, h: 0.5, fontSize: 18, bold: true });
  const el = [["04.1", "Sızıntı kontrolü", "Hedefle aşırı ilişkili değişkenler aday sete alınmaz"], ["04.2", "Yarı sabit eleme", ""],
    ["", "Fazlalık eleme", "Birbirinin tekrarı olan yüksek ilişkili değişkenler"], ["", "Karşılıklı bilgi", "Bilgi katkısı düşük olanlar"], ["", "Model önem skoru", "Kalanlar aday değişken seti"]];
  el.forEach((e, i) => {
    const y = 2.7 + i * 0.8, gen = 5.3 - i * 0.45;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: X0 + 0.3, y, w: gen, h: 0.66, rectRadius: 0.08,
      fill: { color: C.accent1, transparency: 88 - i * 6 }, line: { type: "none" }, objectName: "eleme " + e[1] });
    yazi(s, [{ text: (e[0] ? e[0] + "  " : "") + e[1], options: { bold: true, fontSize: 13, breakLine: !!e[2] } },
      ...(e[2] ? [{ text: e[2], options: { fontSize: 11, color: C.text2 } }] : [])], { x: X0 + 0.45, y, w: gen - 0.3, h: 0.66, valign: "middle" });
  });
  const x5 = X0 + 6.1, w5 = CW - 6.1;
  kart(s, x5, 1.9, w5, 4.9, "faz 05");
  yazi(s, "05 Modelleme ve Finalizasyon", { x: x5 + 0.3, y: 2.05, w: w5 - 0.6, h: 0.5, fontSize: 18, bold: true });
  const m5 = [["05.1", "Model Karşılaştırması", "Baz model ile zenginleştirilmiş model aynı bölme, aynı tohum, aynı ayarlarla; yeni değişkenlerin katkısı ölçülür"],
    ["05.2", "Algoritma Seçimi", "Lojistik regresyon, random forest, gradient boosting ve XGBoost; Dataiku senaryosunda"],
    ["05.3", "Model Finalizasyonu", "Son eğitim, test setinde doğrulama, pickle olarak kayıt"],
    ["05.4", "Değişken Kataloğu", "Kabul edilen her değişkenin formülü, kaynağı, kodu, kalite ve seçim sonucu"]];
  m5.forEach((m, i) => {
    const y = 2.7 + i * 1.0;
    rozet(s, m[0], x5 + 0.3, y + 0.17, 0.85, 0.4, { fontSize: 12 });
    yazi(s, [{ text: m[1], options: { bold: true, fontSize: 14, breakLine: true } }, { text: m[2], options: { fontSize: 11.5, color: C.text2 } }],
      { x: x5 + 1.35, y, w: w5 - 1.6, h: 0.9, valign: "middle" });
  });
  s.addNotes("Seçim adımında karşılıklı bilgi ve model önem skoru Train satırlarıyla hesaplanır; test ve OOT satırlarını görmez. " +
    "Algoritma seçimi uzun sürdüğü için Dataiku senaryosunda çalışır; kimlik bazlı bölmede katlar da gruplu kurulur.");

  // 19 BOLUM: PLATFORM GENELINDE --------------------------------------
  pres.addSection({ title: B3 });
  s = pres.addSlide({ masterName: "BOLUM", sectionTitle: B3 });
  s.addText("Genel", { placeholder: "no" });
  s.addText("Platform genelinde", { placeholder: "title" });
  s.addText("Sayfalar, proje hafızası, güvenceler ve bugünkü durum", { placeholder: "body" });

  // 20 EKRANLAR -------------------------------------------------------
  s = icerik("Sayfalar", "Sol bardaki Model Platformu kümesi; her sayfa açık çalışmanın aynı kayıtlarını okur.", B3);
  const ek = [
    ["FaListCheck", "Model Akışı", "Adımların blok blok ilerlediği çalışma alanı. Her blokta sonuç, öneri ve Geri Dön; üstte İş Akışı ile ilerleme."],
    ["FaGaugeHigh", "Model Gösterge Paneli", "Çalışmanın sayılarla özeti: veri ve sözlük, üretilen ve elenen değişkenler, bölme, validasyon, model sonucu."],
    ["FaTableCells", "Model Değişkenleri", "Veri ve Sözlük (Güncel ve Baz sekmeleri), Dağılım ve SFA grafikleri, Değişken Kontrolleri. SFA kararları burada değişir."],
    ["FaFileWord", "Model Özeti", "Künye ve 20 bölümlü model dokümanı; her açılışta akışın son durumundan üretilir, Word olarak indirilir."],
    ["FaBoxArchive", "Arşiv ve Yeni Çalışma", "Kayıtlı çalışmalar kaldığı yerden açılır; yeni çalışma açılınca eskisi Arşiv'de kalır."],
    ["FaHourglassHalf", "Hazırlanıyor", "Model Sohbeti, Asistanla Sohbet ve modellerden bağımsız Gösterge Paneli."],
  ];
  for (let i = 0; i < 6; i++) {
    const x = X0 + (i % 3) * (3.911 + 0.2), y = 1.9 + Math.floor(i / 3) * 2.5;
    const son = i === 5;
    kart(s, x, y, 3.911, 2.3, ek[i][1], { fill: { color: son ? C.background1 : C.background2 }, line: son ? { color: C.accent6, width: 1, dashType: "dash" } : { type: "none" } });
    await ikonDaire(s, ek[i][0], x + 0.25, y + 0.25, 0.65, ek[i][1]);
    yazi(s, ek[i][1], { x: x + 1.05, y: y + 0.25, w: 2.7, h: 0.65, fontSize: 16, bold: true, valign: "middle" });
    yazi(s, ek[i][2], { x: x + 0.25, y: y + 1.0, w: 3.45, h: 1.2, fontSize: 12.5, color: C.text2 });
  }
  s.addNotes("Arayüzde üç renk modu var: Beyaz, Sepya ve Koyu. Yeni güncellemesi olan bölüm sol barda hafif kırmızı nabızla işaretlenir.");

  // 21 HAFIZA ---------------------------------------------------------
  s = icerik("Proje hafızası: aynı şey iki kez sorulmaz", "Onaylanan bilgi PROJE_HAFIZASI klasörüne yazılır ve sonraki çalışmalarda kesin bağlam olarak kullanılır.", B3);
  tablo(s, [
    ["Ne hatırlanır", "Nerede onaylanır", "Nasıl kullanılır"],
    ["Sözlük tanımları", "01.2.3 Eksik Sözlük Tanımları", "Tanımsız kolona önce onaylı tanım önerilir"],
    ["Dönem kalıpları ve anlamları", "01.2.4.1 Dönem Bilgisi", "Aynı kalıp yeniden sorulmaz; genel ve veri setine özel anlam ayrı tutulur"],
    ["Ad parçaları ve standart yazılış", "01.2.4.2 Ad Parçaları", "Parça anlamı dil modeline kesin bilgi olarak gider"],
    ["Önceki onaylı kontrol", "01.2.4 Sözlük ve Kolon Adı Kontrolü", "Aynı tabloda kontrol bütünüyle yeniden uygulanabilir"],
    ["Tablonun önceki seçimleri", "01.2 kurulum ve roller", "Roller ve sözlük eşleşmesi yeni çalışmada önerilir"],
    ["02.2 kararları ve sohbet özeti", "02.2 Kural Tabanlı Değişken Üretimi", "Öneriden farklı seçimler korunur; sohbet kısa hafızayla sürer"],
    ["Çalışma kayıtları", "Her adım sonunda", "Arşiv'den kaldığı yerden açılır"],
  ], { x: X0, y: 1.9, w: CW, colW: [3.2, 3.6, 5.333], fontSize: 13, ilkKalin: true, rowH: 0.56 });
  s.addNotes("Dil modeli önerileri bağlam imzasıyla önbelleğe alınır: bağlam değişmediyse aynı soru tekrar sorulmaz, değiştiyse yeniden sorulur.");

  // 22 GUVENCELER -----------------------------------------------------
  s = icerik("Güvenceler", "Bütün adımlarda geçerli dört kural.", B3);
  const gv = [
    ["FaDatabase", "Girdi veriniz değişmez", "Seçtiğiniz veri setine ve sözlüğe hiçbir şey yazılmaz; platform yalnız kendi BAZ ve UPDT kopyalarıyla çalışır."],
    ["FaLayerGroup", "Tam veri, örneklem yok", "Profil, sayımlar, ölçümler ve analizler verinin tamamında yapılır; büyük veri Spark ile kümede işlenir."],
    ["FaShieldHalved", "Sızıntı sınırı korunur", "Doldurma, dönüşüm ve eğitim yalnız Train setinden öğrenilir; geleceğe bakan ve hedefle aşırı ilişkili değişkenler modele alınmaz."],
    ["FaClipboardCheck", "Her karar kayıtlı", "Değişkenin kaynağı, dönüşümü, seçim kararı, gerekçesi ve üretim kodu kaydedilir; model dokümanı bu kayıtlardan üretilir."],
  ];
  for (let i = 0; i < 4; i++) {
    const x = X0 + (i % 2) * (5.966 + 0.2), y = 1.9 + Math.floor(i / 2) * 2.5;
    kart(s, x, y, 5.966, 2.3, gv[i][1]);
    await ikonDaire(s, gv[i][0], x + 0.35, y + 0.4, 0.95, gv[i][1]);
    yazi(s, gv[i][1], { x: x + 1.6, y: y + 0.35, w: 4.1, h: 0.55, fontSize: 19, bold: true, valign: "middle" });
    yazi(s, gv[i][2], { x: x + 1.6, y: y + 0.95, w: 4.1, h: 1.25, fontSize: 14, color: C.text2 });
  }
  s.addNotes("Ek olarak dil modelinin adı ve bağlantı kimliği arayüzde hiçbir yerde gösterilmez; backend'in her cevabı bu süzgeçten geçer.");

  // 23 DURUM ----------------------------------------------------------
  s = icerik("Bugünkü durum", "Hangi bölüm hangi düzende çalışıyor.", B3);
  tablo(s, [
    ["Bölüm", "Durum", "Not"],
    ["01 Çalışma Kurulumu", "Çalışıyor", "Baz Veri Seti Mevcut ve Kaynak Tablolar Mevcut başlangıçları büyük veri yoluyla uçtan uca denendi"],
    ["02 ve 03", "Çalışıyor", "BAZ ve UPDT veri düzeninde"],
    ["04 ve 05", "Çalışıyor", "Önceki veri düzeniyle okuyor; UPDT düzenine taşınması bekliyor"],
    ["Otomatik Pilot", "Kapalı", "Kararları yapay zekânın verdiği uçtan uca başlangıç; kartta soluk duruyor"],
    ["Model Sohbeti, Asistanla Sohbet, Gösterge Paneli", "Hazırlanıyor", "Sol barda kilitli"],
  ], { x: X0, y: 1.9, w: CW, colW: [3.6, 1.8, 6.733], fontSize: 13, ilkKalin: true, rowH: 0.7 });
  s.addNotes("Bu tablo kod tabanındaki güncel duruma göre yazıldı.");

  // 24 KAPANIS --------------------------------------------------------
  s = pres.addSlide({ masterName: "KAPAK", sectionTitle: B3 });
  s.addText("Nasıl başlanır", { placeholder: "title" });
  s.addText("Sol barda Model Platformu, ardından Yeni Çalışma. Başlangıç Seçimi'nde verinizin durumunu seçin; platform her adımda önerisini sunar, siz onaylarsınız.",
    { placeholder: "body" });
  s.addText("Gerekenler: Dataiku projesinde webapp, okuma yetkiniz olan veri seti ve varsa değişken sözlüğü", { placeholder: "alt" });

  await pres.writeFile({ fileName: CIKTI });
  await applyTheme(CIKTI, THEME);
  console.log("yazildi", CIKTI);
})().catch((e) => { console.error(e); process.exit(1); });
