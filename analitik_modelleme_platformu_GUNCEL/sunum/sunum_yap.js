// Akilli Modelleme Platformu: ne yapiyoruz, nerede kaldik (duzenlenebilir pptx)
const pptxgen = require("pptxgenjs");
const CIKTI = process.argv[2] || "sunum2.pptx";

const KIR = "C8102E", KOYU = "262626", GRI = "595959", ACIK = "F2F2F2", BEJ = "F6DDD0", SOLUK = "A6A6A6";
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5
pres.title = "Akıllı Modelleme Platformu";
pres.theme = { headFontFace: "Calibri", bodyFontFace: "Calibri" };

pres.defineSlideMaster({
  title: "AKIS",
  background: { color: "FFFFFF" },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.5, y: 0.28, w: 8.4, h: 0.58, fontSize: 24,
      bold: true, color: KIR, align: "left", valign: "middle", margin: 0 }, text: "" } },
    { line: { x: 0.5, y: 0.92, w: 12.33, h: 0, line: { color: KIR, width: 1 } } },
  ],
  slideNumber: { x: 12.35, y: 7.08, w: 0.5, h: 0.25, fontSize: 10, color: SOLUK, align: "right" },
});

let s;
const T = (metin, o) => s.addText(metin, Object.assign({ isTextBox: true, fontFace: "Calibri", fontSize: 11,
  color: KOYU, margin: 0.04, valign: "middle", align: "center" }, o));
function kutu(x, y, w, h, tur, ad) {
  const st = {
    veri: { fill: { color: KIR }, line: { type: "none" } },
    islem: { fill: { color: "FFFFFF" }, line: { color: KIR, width: 1.5 } },
    onay: { fill: { color: BEJ }, line: { color: KIR, width: 1.5 } },
    sirada: { fill: { color: "FFFFFF" }, line: { color: KIR, width: 1.5, dashType: "dash" } },
    gri: { fill: { color: ACIK }, line: { type: "none" } },
    soluk: { fill: { color: "FFFFFF" }, line: { color: SOLUK, width: 1.25, dashType: "dash" } },
  }[tur];
  const o = Object.assign({ x, y, w, h, rectRadius: 0.1, objectName: ad }, st);
  if (tur === "veri") o.shadow = { type: "outer", color: "000000", opacity: 0.2, blur: 4, offset: 2, angle: 90 };
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, o);
}
const ok = (x1, y1, x2, y2, ad, renk) => s.addShape(pres.shapes.LINE, {
  x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1) || 0.001, h: Math.abs(y2 - y1) || 0.001,
  flipH: x2 < x1, flipV: y2 < y1,
  line: { color: renk || KIR, width: 1.25, endArrowType: "triangle" }, objectName: ad || "ok" });
const cizgi = (x1, y1, x2, y2, ad) => s.addShape(pres.shapes.LINE, {
  x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1) || 0.001, h: Math.abs(y2 - y1) || 0.001,
  line: { color: KIR, width: 1.25 }, objectName: ad || "çizgi" });
function lejant(ogeler) {
  ogeler.forEach((l, i) => {
    const x = 9.2 + (i % 2) * 1.85, y = 0.22 + Math.floor(i / 2) * 0.32;
    kutu(x, y + 0.04, 0.42, 0.2, l[0], "lejant " + l[1]);
    T(l[1], { x: x + 0.5, y, w: 1.32, h: 0.28, fontSize: 10, color: GRI, align: "left", margin: 0 });
  });
}
const LEJANT = [["veri", "Veri / Çıktı"], ["islem", "İşlem (kod)"], ["onay", "Kullanıcı onayı"], ["sirada", "İsteğe bağlı"]];
function dipnot(m) { T(m, { x: 0.5, y: 6.98, w: 11.6, h: 0.3, fontSize: 10.5, italic: true, color: GRI, align: "left", margin: 0 }); }
function onayPill(cx, y, ad) {
  kutu(cx - 0.4, y, 0.8, 0.26, "onay", "onay " + ad);
  T("onay", { x: cx - 0.4, y, w: 0.8, h: 0.26, fontSize: 10, bold: true, color: KIR, margin: 0 });
}
// islem kutusu: baslik + kim + aciklama
function islem(x, y, w, h, baslik, kim, aciklama, tur) {
  kutu(x, y, w, h, tur || "islem", baslik);
  const r = [{ text: baslik, options: { bold: true, color: KIR, fontSize: 12.5, breakLine: true } }];
  if (kim) r.push({ text: kim, options: { fontSize: 9.5, bold: true, color: GRI, breakLine: !!aciklama } });
  if (aciklama) r.push({ text: aciklama, options: { fontSize: 10.5, color: KOYU } });
  T(r, { x: x + 0.06, y: y + 0.04, w: w - 0.12, h: h - 0.08, paraSpaceAfter: 2 });
}
function veri(x, y, w, h, baslik, alt) {
  kutu(x, y, w, h, "veri", baslik);
  T(alt ? [{ text: baslik, options: { bold: true, fontSize: 12.5, breakLine: true } }, { text: alt, options: { fontSize: 10.5 } }]
    : [{ text: baslik, options: { bold: true, fontSize: 12.5 } }], { x: x + 0.06, y, w: w - 0.12, h, color: "FFFFFF" });
}

// =====================================================================
// 1  AMAC VE DURUM
s = pres.addSlide({ masterName: "AKIS" });
s.addText("Akıllı Modelleme Platformu · Nerede Kaldık", { placeholder: "title" });
T("Projenin Amacı", { x: 0.5, y: 1.15, w: 1.6, h: 0.75, fontSize: 15, italic: true, color: KIR, align: "left", margin: 0 });
kutu(2.15, 1.15, 10.68, 0.75, "islem", "amaç");
T("Model geliştirmeyi tek akışta yürütmek: yapay zekâ önerir, kullanıcı onaylar, kod tam veride hesaplar. Modele yalnız katkısı ölçülen değişkenler girer.",
  { x: 2.3, y: 1.15, w: 10.38, h: 0.75, fontSize: 13.5 });

kutu(0.5, 2.15, 12.33, 2.45, "gri", "akış bandı");
const adim = [
  ["01", "Çalışma Kurulumu", "g"], ["02.1", "Veri Profili ve Kalite", "g"], ["02.2", "Geleneksel Değişken Üretimi", "s"],
  ["02.3", "AI Değişken Keşfi", "r"], ["03", "Veri Anlama ve Hazırlama", "r"], ["04", "Değişken Değerlendirme", "r"], ["05", "Modelleme ve Finalizasyon", "r"],
];
const sl = 12.33 / 7;
s.addShape(pres.shapes.LINE, { x: 0.5 + sl / 2, y: 3.08, w: sl * 6, h: 0, line: { color: SOLUK, width: 1.5, dashType: "dash" }, objectName: "akış çizgisi" });
adim.forEach((a, i) => {
  const cx = 0.5 + sl * i + sl / 2, d = a[2] === "s" ? 0.95 : 0.8;
  const renk = a[2] === "g" ? { fill: { color: KIR }, line: { color: KIR, width: 1 } }
    : a[2] === "s" ? { fill: { color: BEJ }, line: { color: KIR, width: 3 } }
    : { fill: { color: "FFFFFF" }, line: { color: SOLUK, width: 1.5, dashType: "dash" } };
  s.addShape(pres.shapes.OVAL, Object.assign({ x: cx - d / 2, y: 3.08 - d / 2, w: d, h: d, objectName: "adım " + a[0] }, renk));
  T(a[0], { x: cx - d / 2, y: 3.08 - d / 2, w: d, h: d, fontSize: a[0].length > 2 ? 14 : 17, bold: true, margin: 0,
    color: a[2] === "g" ? "FFFFFF" : a[2] === "s" ? KIR : SOLUK });
  T(a[1], { x: cx - sl / 2 + 0.05, y: 3.62, w: sl - 0.1, h: 0.55, fontSize: 12, bold: true, color: a[2] === "r" ? GRI : KOYU, valign: "top" });
  T(a[2] === "g" ? "Geliştirildi" : a[2] === "s" ? "Üzerinde çalışılıyor" : "Sırada",
    { x: cx - sl / 2 + 0.05, y: 4.18, w: sl - 0.1, h: 0.28, fontSize: 10.5, bold: a[2] === "s", color: a[2] === "s" ? KIR : GRI });
  if (a[2] === "s") {
    kutu(cx - 0.85, 2.22, 1.7, 0.28, "veri", "şu an buradayız");
    T("Şu an buradayız", { x: cx - 0.85, y: 2.22, w: 1.7, h: 0.28, fontSize: 10.5, bold: true, color: "FFFFFF", margin: 0 });
  }
});

const kartlar = [
  ["gri", "Geliştirilen", [
    "01 Çalışma Kurulumu: veri seti ve sözlük, kolon rolleri, eksik tanımlar, sözlük ve kolon adı kontrolü, bölme",
    "02.1 Veri Profili ve Kalite: 25 kontrol, düzeltme ve çözüm önerileri"]],
  ["onay", "Üzerinde çalışılan", [
    "02.2 Geleneksel Değişken Üretimi: dil modeli birim birim dönüşüm seçer, kod katkısını ölçer, kullanıcı kart ve sohbetle karar verir",
    "Geri bildirimle güncelleniyor"]],
  ["soluk", "Sırada", [
    "02.3 AI Değişken Keşfi",
    "03, 04 ve 05: ilk sürümleri kodda var, bu yapıya göre yeniden ele alınacak"]],
];
const kw = (12.33 - 0.5) / 3;
kartlar.forEach((k, i) => {
  const x = 0.5 + i * (kw + 0.25);
  kutu(x, 4.85, kw, 1.95, k[0], "kart " + k[1]);
  T(k[1], { x: x + 0.2, y: 4.95, w: kw - 0.4, h: 0.35, fontSize: 14, bold: true, color: KIR, align: "left", margin: 0 });
  T(k[2].map((m, j) => ({ text: m, options: { bullet: { indent: 10 }, breakLine: j < k[2].length - 1 } })),
    { x: x + 0.2, y: 5.35, w: kw - 0.4, h: 1.4, fontSize: 11.5, align: "left", valign: "top", margin: 0, paraSpaceAfter: 4 });
});
dipnot("Girdi veri setine ve sözlüğe hiçbir şey yazılmaz; platform kendi kopyalarıyla çalışır, bütün sayımlar örneklemesiz tam veride yapılır.");
s.addNotes("Akış beş fazdan oluşuyor. 01 ve 02.1 geliştirildi; şu an 02.2 Geleneksel Değişken Üretimi üzerinde çalışıyoruz. " +
  "02.3 ve sonrasının (03, 04, 05) ilk sürümleri kodda var ama bu yapıya göre henüz ele alınmadı.");

// =====================================================================
// 2  01 CALISMA KURULUMU
s = pres.addSlide({ masterName: "AKIS" });
s.addText("01 Çalışma Kurulumu · Veri ve Sözlük Hazırlığı", { placeholder: "title" });
lejant(LEJANT);
veri(0.5, 1.6, 1.75, 1.0, "Veri Seti ve Sözlük", "kullanıcı seçer");
const p1 = [
  ["Kolon Rolleri", "Hedef, kimlik ve dönem kolonu; model tipi"],
  ["Eksik Sözlük Tanımları", "Tanımsız kolonlara onaylı tanımlardan ve dil modelinden öneri"],
  ["Sözlük ve Kolon Adı Kontrolü", "Kolon adları parçalara ayrılır, anlamları onaylanır"],
  ["Değişken Listesi ve Tip Kontrolü", "Son gözden geçirme; güncel veri ve sözlük yazılır"],
  ["Örneklem ve Doğrulama", "Train, Test, Validasyon; sızıntı sınırı"],
];
const p1x = 2.6, p1w = 1.85, p1g = (12.83 - p1x - 5 * p1w) / 4;
ok(2.25, 2.1, p1x - 0.02, 2.1, "ok girdi");
p1.forEach((p, i) => {
  const x = p1x + i * (p1w + p1g);
  onayPill(x + p1w / 2, 1.18, p[0]);
  ok(x + p1w / 2, 1.44, x + p1w / 2, 1.58, "ok onay " + i);
  islem(x, 1.6, p1w, 1.0, p[0], "", "", i === 2 ? "sirada" : "islem");
  T(p[1], { x, y: 2.65, w: p1w, h: 0.6, fontSize: 10.5, color: GRI, valign: "top" });
  if (i < 4) ok(x + p1w + 0.02, 2.1, x + p1w + p1g - 0.02, 2.1, "ok adım " + i);
});
// kontrol ayrintisi
const kx = p1x + 2 * (p1w + p1g) + p1w / 2;
cizgi(kx, 3.25, kx, 3.45, "kontrol bağlantı");
kutu(0.5, 3.45, 12.33, 1.95, "sirada", "kontrol çerçevesi");
T([{ text: "Sözlük ve Kolon Adı Kontrolü  ", options: { bold: true, color: KIR } }, { text: "isteğe bağlı · örnek kolon: TRX_OUT_AMT_L30D (gösterim amaçlı)", options: { color: GRI } }],
  { x: 0.7, y: 3.52, w: 11.9, h: 0.32, fontSize: 11.5, align: "left", margin: 0 });
const k4 = [
  ["Dönem Bilgisi", "L30D = son 30 gün", "Sayılı zaman parçalarının anlamı ve yönü"],
  ["Ad Parçaları", "TRX işlem · OUT giden · AMT tutar", "Kısaltmaların anlamı ve standart yazılışı"],
  ["Kolon Kartları", "Son 30 günde giden işlemlerin toplam tutarı", "Parçalardan kart, tek açık açıklama"],
  ["Kolon Adları", "Ad Standardı sırasıyla yeni ad", "Eski ad saklanır, yalnız kopyalarda geçerli"],
];
const k4w = (11.93 - 3 * 0.35) / 4;
k4.forEach((k, i) => {
  const x = 0.7 + i * (k4w + 0.35);
  kutu(x, 3.92, k4w, 1.35, "islem", "kontrol " + k[0]);
  T([{ text: (i + 1) + ". " + k[0], options: { bold: true, color: KIR, fontSize: 12, breakLine: true } },
    { text: k[1], options: { bold: true, fontSize: 11, breakLine: true } },
    { text: k[2], options: { fontSize: 10, color: GRI } }], { x: x + 0.08, y: 3.94, w: k4w - 0.16, h: 1.31, paraSpaceAfter: 2 });
  if (i < 3) ok(x + k4w + 0.03, 4.6, x + k4w + 0.32, 4.6, "ok kontrol " + i);
});
// ciktilar
const c1 = [["BAZ Veri ve Sözlük", "girdinin kopyası, hiç değişmez"], ["UPDT Veri ve Sözlük", "verinin ve sözlüğün güncel hâli"],
  ["Proje Hafızası", "onaylı dönem, parça ve tanımlar"], ["Bölme (_SPLIT)", "Train, Test, Validasyon"]];
const cw = (12.33 - 3 * 0.25) / 4;
c1.forEach((c, i) => veri(0.5 + i * (cw + 0.25), 5.7, cw, 0.95, c[0], c[1]));
T("Çıktılar", { x: 0.5, y: 5.42, w: 3, h: 0.26, fontSize: 11, bold: true, color: GRI, align: "left", margin: 0 });
dipnot("Onaylanan dönem, parça ve tanımlar hafızaya yazılır; aynı şey bir sonraki çalışmada yeniden sorulmaz.");
s.addNotes("Kaynak tablolarla başlanırsa bu adımlardan önce Kaynak Tablolar, Kaynak Sözlükleri ve Birleştirme Planı gelir. " +
  "Sözlük ve kolon adı kontrolü seçilmezse dört alt adım atlanır. Örnek kolon adı ve anlamları gösterim amaçlıdır.");

// =====================================================================
// 3  02.1 VERI PROFILI VE KALITE
s = pres.addSlide({ masterName: "AKIS" });
s.addText("02.1 Veri Profili ve Kalite", { placeholder: "title" });
lejant(LEJANT);
veri(0.5, 1.6, 1.9, 1.0, "UPDT Veri", "01'in çıktısı");
const p3 = [
  ["Kontrol Eşikleri", "onay", "Eşikler önerilen değer ve gerekçesiyle sorulur"],
  ["25 Kontrol", "islem", "Tablonun tamamında, örneklemesiz"],
  ["Karar Kartı", "onay", "Her bulguya öneri: tut, çıkar, düzelt ya da çözüm"],
  ["Uygulama", "islem", "Kararlar veriye uygulanır, kaydedilir"],
];
const p3x = 2.75, p3w = 1.78, p3g = 0.32;
ok(2.4, 2.1, p3x - 0.02, 2.1, "ok girdi");
p3.forEach((p, i) => {
  const x = p3x + i * (p3w + p3g);
  kutu(x, 1.6, p3w, 1.0, p[1], p[0]);
  T(p[0], { x, y: 1.6, w: p3w, h: 1.0, fontSize: 13, bold: true, color: KIR });
  T(p[2], { x, y: 2.65, w: p3w, h: 0.55, fontSize: 10.5, color: GRI, valign: "top" });
  if (i < 3) ok(x + p3w + 0.02, 2.1, x + p3w + p3g - 0.02, 2.1, "ok adım " + i);
});
const sonx = p3x + 4 * (p3w + p3g) - p3g;
ok(sonx + 0.02, 2.1, 10.93, 2.1, "ok çıktı");
veri(10.95, 1.6, 1.88, 1.0, "UPDT Veri", "düzeltilmiş ve çözüm kolonları");
const g3 = [
  ["Sızıntı", "Çıkar önerilir", "Geleceğe bakan pencere, hedefle neredeyse birebir ilişki"],
  ["Düzeltme", "Kolon yerinde düzeltilir", "Özel tarih kodu, metin olarak yazılmış boş, yazım farkı, beklenmeyen negatif, uç değer, gizli eksik, ondalık"],
  ["Karar", "Tut ya da çıkar", "Neredeyse sabit, dönemde boş ya da sabit, eksik sıçraması, değer kayması, dönemden sonraki tarih"],
  ["Çözüm", "Ham kolon yerine yeni kolon", "Hedef oranına ya da kod önekine göre gruplama, seyrek değerleri toplama, dolu mu bayrağı, metinden özellik, tarihten gün farkı"],
];
const gw = (12.33 - 3 * 0.25) / 4;
T("Kontrol grupları", { x: 0.5, y: 3.32, w: 3, h: 0.26, fontSize: 11, bold: true, color: GRI, align: "left", margin: 0 });
g3.forEach((g, i) => {
  const x = 0.5 + i * (gw + 0.25);
  kutu(x, 3.6, gw, 1.5, "gri", "grup " + g[0]);
  T([{ text: g[0], options: { bold: true, color: KIR, fontSize: 13, breakLine: true } },
    { text: g[1], options: { bold: true, fontSize: 10.5, color: GRI, breakLine: true } },
    { text: g[2], options: { fontSize: 10.5 } }], { x: x + 0.15, y: 3.65, w: gw - 0.3, h: 1.4, align: "left", valign: "top", paraSpaceAfter: 3 });
});
const kim = [["Öneriyi çoğunlukla kod verir", "Kolonun kendi sayılarına bakan kurallarla; gerekçe sayıyla yazılır."],
  ["Dil modeli yalnız anlam gereken yerde", "Geleceğe bakan pencere, hedefle birebir ilişki, dönemden sonraki tarih, gizli ve karışık eksik, aynı içerikli kolonlardan hangisinin kalacağı."]];
kim.forEach((k, i) => {
  const x = 0.5 + i * (6.04 + 0.25);
  kutu(x, 5.4, 6.04, 1.15, "islem", k[0]);
  T([{ text: k[0], options: { bold: true, color: KIR, fontSize: 12.5, breakLine: true } }, { text: k[1], options: { fontSize: 11 } }],
    { x: x + 0.15, y: 5.42, w: 5.74, h: 1.11, align: "left", paraSpaceAfter: 2 });
});
dipnot("Üretime girmeyen kolondan değişken üretilmez; çözüm seçeneği yalnız Train'in bir yarısında öğrenilip öbür yarısında işe yaradıysa sunulur.");

// =====================================================================
// 4  02.2 NASIL CALISIYOR
s = pres.addSlide({ masterName: "AKIS" });
s.addText("02.2 Geleneksel Değişken Üretimi · Nasıl Çalışıyor", { placeholder: "title" });
lejant([["veri", "Veri / Çıktı"], ["islem", "İşlem (kod)"], ["onay", "Kullanıcı onayı"], ["gri", "Dil modeli"]]);
const r1y = 1.45, r2y = 3.35, bw = 2.3, bh = 1.3;
const xs = [2.95, 5.45, 7.95, 10.5];
veri(0.5, r1y, 2.1, bh, "UPDT Veri ve Onaylı Sözlük", "01 ve 02.1'in çıktısı");
const ust = [
  ["1. Birimler", "kod", "Tek kolon, pencere ailesi, anlamlı kolon çifti ya da grubu", "islem"],
  ["2. Uygunluk", "kod", "41 dönüşümden hangisi bu birimde mümkün, değilse neden", "islem"],
  ["3. Seçim", "dil modeli", "Her birim için dönüşüm seçer, gerekçesini yazar", "gri"],
  ["4. Katkı Ölçümü", "kod, Train satırları", "Yeni bilgi: IV artışı en az 0,02, kaynaklarla ilişki 0,95'ten az", "islem"],
];
ok(2.6, r1y + bh / 2, xs[0] - 0.02, r1y + bh / 2, "ok girdi");
ust.forEach((u, i) => {
  islem(xs[i], r1y, bw, bh, u[0], u[1], u[2], u[3]);
  if (i < 3) ok(xs[i] + bw + 0.02, r1y + bh / 2, xs[i + 1] - 0.02, r1y + bh / 2, "ok üst " + i);
});
ok(xs[3] + bw / 2, r1y + bh + 0.02, xs[3] + bw / 2, r2y - 0.02, "ok aşağı");
const alt2 = [
  ["5. Tamamlama", "kod", "Yeni bilgi getiren ama seçilmemiş dönüşüm eklenir", "islem", xs[3]],
  ["6. Karar", "kullanıcı", "Karar kartı ve sohbetle ekler, çıkarır, sorar", "onay", xs[2]],
  ["7. Üretim", "kod", "Onayda kolonlar üretilir, parametreler Train'den", "islem", xs[1]],
];
alt2.forEach((u, i) => {
  islem(u[4], r2y, bw, bh, u[0], u[1], u[2], u[3]);
  ok(u[4] - 0.02, r2y + bh / 2, (i < 2 ? alt2[i + 1][4] : xs[0]) + bw + 0.02, r2y + bh / 2, "ok alt " + i);
});
veri(xs[0], r2y, bw, bh, "UPDT Veri", "yeni kolonlar ve üretim kodu");
// kart ve sohbet
const kk = [
  ["Karar kartında", ["Dönüşümler tablosu: uygulanabilir, önerilen, seçili sayıları; kullanılabilir mi ve neden",
    "Öneriler tablosu: kendi dönüşümü, aile içi, aileler arası süzgeçleri; öneren ve ölçüm",
    "Son değişiklikler ve Geri al; kararlar anında kaydedilir"]],
  ["Plan üzerine sohbette", ["Toplu istek: \"bütün oranları kaldır\" gibi; kapsamı kod belirler",
    "Cevap ve öneri ölçüme dayanır, değişikliği kod kurar, kullanıcı onaylar",
    "Kısa hafıza tutulur; yapılmayan iş \"yapıldı\" diye yazılmaz"]],
];
kk.forEach((k, i) => {
  const x = 0.5 + i * (6.04 + 0.25);
  kutu(x, 5.1, 6.04, 1.45, "gri", k[0]);
  T(k[0], { x: x + 0.2, y: 5.18, w: 5.6, h: 0.32, fontSize: 13, bold: true, color: KIR, align: "left", margin: 0 });
  T(k[1].map((m, j) => ({ text: m, options: { bullet: { indent: 10 }, breakLine: j < k[1].length - 1 } })),
    { x: x + 0.2, y: 5.52, w: 5.65, h: 1.0, fontSize: 11, align: "left", valign: "top", margin: 0, paraSpaceAfter: 3 });
});
dipnot("Ağaç ve doğrusal model ayrımı yok: iki modelde de kullanılabilecek bütün dönüşümler tek seferde değerlendirilir.");
s.addNotes("Dil modeli birimleri parça parça değerlendirir (üç tur, paralel çağrılar); cevap gelmezse kodun kural önerisi kullanılır. " +
  "Ölçek dönüşümleri (logaritma, kırpma, sıra) IV'yi değiştirmediği için çarpıklık ve uç değere bakılarak önerilir. " +
  "Öneriden farklı her seçim ayrı saklanır; plan yeniden kurulunca kullanıcının çıkardığı dönüşüm geri gelmez.");

// =====================================================================
// 5  02.2 UC ASAMA
s = pres.addSlide({ masterName: "AKIS" });
s.addText("02.2 · Üç Aşama, 41 Dönüşüm", { placeholder: "title" });
const asamalar = [
  ["1. Kolonun kendi dönüşümü", "18 dönüşüm", "Kolonun dağılımı: çarpıklık, uç değer, sıfır yoğunluğu, kategori sayısı",
    "Logaritma · işaretli logaritma · karekök · kare · çarpıklık düzeltme · uç değer kırpma · sıraya çevirme · z skor · medyana göre ölçekleme · artı eksi sıfır · sıfır bayrağı · eşik bayrağı · ondalık dilim · iş kuralı aralıkları · kategori sıklığı · kategori başına 0/1 · risk puanı (WoE) · temerrüt oranı",
    "TRX_OUT_AMT_L30D → logaritması"],
  ["2. Aile içi üretim", "13 dönüşüm", "Aynı ölçünün farklı pencereleri: kısa ve uzun dönem, eğilim, düzen",
    "Kısa bölü uzun dönem · kısa eksi uzun dönem · günlük ortalamaların oranı · büyüme · eğilim · düzensizlik · art arda artış · en yoğun dönemin payı · bütün pencere çiftlerinin oranı ve farkı · dönem dilimleri, payları ve oranları",
    "TRX_OUT_AMT_L30D bölü TRX_OUT_AMT_L90D"],
  ["3. Aileler arası üretim", "10 dönüşüm", "Anlamlı ilişki: gelen ve giden, tutar ve adet, alt kırılım ve toplam, segment",
    "Net akış · iki kolonun oranı · işlem başına ortalama tutar · alt kırılımın payı · çarpım · iki kategorinin birleşimi · tek kanala yoğunlaşma · segment içindeki yeri · segment medyanına oran · satırdaki boş alan sayısı",
    "TRX_IN_AMT_L30D eksi TRX_OUT_AMT_L30D"],
];
const aw = (12.33 - 2 * 0.3) / 3;
asamalar.forEach((a, i) => {
  const x = 0.5 + i * (aw + 0.3);
  veri(x, 1.2, aw, 0.85, a[0], a[1]);
  T("Neye bakar", { x, y: 2.2, w: aw, h: 0.28, fontSize: 11, bold: true, color: GRI, align: "left", margin: 0 });
  kutu(x, 2.5, aw, 0.85, "islem", "neye bakar " + i);
  T(a[2], { x: x + 0.12, y: 2.5, w: aw - 0.24, h: 0.85, fontSize: 11.5, align: "left" });
  T("Dönüşümler", { x, y: 3.5, w: aw, h: 0.28, fontSize: 11, bold: true, color: GRI, align: "left", margin: 0 });
  kutu(x, 3.8, aw, 1.5, "gri", "dönüşümler " + i);
  T(a[3], { x: x + 0.12, y: 3.85, w: aw - 0.24, h: 1.4, fontSize: 11, align: "left", valign: "top" });
  T("Örnek (gösterim amaçlı)", { x, y: 5.5, w: aw, h: 0.28, fontSize: 11, bold: true, color: GRI, align: "left", margin: 0 });
  kutu(x, 5.8, aw, 0.6, "onay", "örnek " + i);
  T(a[4], { x: x + 0.08, y: 5.8, w: aw - 0.16, h: 0.6, fontSize: 11.5, fontFace: "Courier New", bold: true, color: KIR });
});
dipnot("Kartta her dönüşümün sade adı, ne yaptığı, bu verideki örneği ve bu veride neden kullanılabilir ya da kullanılamaz olduğu yazar.");

// =====================================================================
// 6  02.2 YAPILANLAR VE ACIK KONULAR
s = pres.addSlide({ masterName: "AKIS" });
s.addText("02.2 · Yapılanlar ve Açık Konular", { placeholder: "title" });
const yap = [
  ["İlk sürüm", "Birim bazında öneri, 28 dönüşüm, kart ve sohbet"],
  ["Kapsam", "Aileler arası birimler, bütün pencere çiftleri, dönem dilimleri; 41 dönüşüm"],
  ["Katkı ölçümü", "Kararlar ve gerekçeler IV ve benzerlik sayısına dayanıyor"],
  ["Kalıcı kararlar", "Seçimler anında kaydediliyor, plan yenilenince geri gelmiyor"],
  ["Tek mod", "Ağaç ve doğrusal ayrımı kalktı; değer katan seçilmemiş dönüşümü kod ekliyor"],
  ["Anlaşılır kart", "Sade adlar ve örnekler, kullanılabilir mi ve neden, canlı sayılar, değişiklik günlüğü, üç aşamalı öneriler"],
  ["Sohbet", "Toplu değişiklik, onayla uygulama, \"yapıldı\" denetimi, hafıza"],
];
T("Bu bölümde yapılanlar", { x: 0.5, y: 1.15, w: 7.3, h: 0.35, fontSize: 14, bold: true, color: KIR, align: "left", margin: 0 });
cizgi(0.72, 1.75, 0.72, 1.75 + 6 * 0.74, "zaman çizgisi");
yap.forEach((y, i) => {
  const yy = 1.6 + i * 0.74;
  s.addShape(pres.shapes.OVAL, { x: 0.6, y: yy + 0.03, w: 0.24, h: 0.24, fill: { color: KIR }, line: { color: "FFFFFF", width: 1.5 }, objectName: "nokta " + y[0] });
  T([{ text: y[0], options: { bold: true, fontSize: 12.5, breakLine: true } }, { text: y[1], options: { fontSize: 11, color: GRI } }],
    { x: 1.05, y: yy - 0.04, w: 6.75, h: 0.7, align: "left", valign: "top", margin: 0 });
});
kutu(8.2, 1.15, 4.63, 5.65, "onay", "açık konular");
T("Açık konular", { x: 8.45, y: 1.3, w: 4.2, h: 0.35, fontSize: 14, bold: true, color: KIR, align: "left", margin: 0 });
const acik = [
  ["Kolon sayısı", "Ölçümle tamamlama kolon sayısını artırır; gerekirse yeni bilgi eşiği (IV artışı 0,02) yükseltilir"],
  ["Geri bildirim turları", "Kart ve sohbet kullanıcı geri bildirimiyle güncellenmeye devam ediyor"],
  ["Sonraki adım", "02.2 tamamlanınca 02.3 AI Değişken Keşfi"],
];
acik.forEach((a, i) => {
  const yy = 1.85 + i * 1.4;
  T([{ text: a[0], options: { bold: true, fontSize: 12.5, breakLine: true } }, { text: a[1], options: { fontSize: 11, color: KOYU } }],
    { x: 8.45, y: yy, w: 4.15, h: 1.1, align: "left", valign: "top", margin: 0, paraSpaceAfter: 2 });
});
dipnot("02.2 bitmiş değil; bu sayfa şu anki hâlini gösterir.");

pres.writeFile({ fileName: CIKTI }).then(() => console.log("yazildi", CIKTI));
