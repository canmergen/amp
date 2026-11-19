// Akilli Modelleme Platformu: platformu hic bilmeyen ekiplere bastan sona tanitim (duzenlenebilir pptx)
// Calistirma: NODE_PATH=<node_modules> node sunum_yap.js cikti.pptx
const pptxgen = require("pptxgenjs");
const JSZip = require("jszip");
const fs = require("fs");
const CIKTI = process.argv[2] || "sunum.pptx";

const KIR = "C8102E", KOYU = "262626", GRI = "595959", ACIK = "F2F2F2", BEJ = "F6DDD0", SOLUK = "A6A6A6", KIR2 = "8E0B20";
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5
pres.title = "Akıllı Modelleme Platformu";
pres.theme = { headFontFace: "Calibri", bodyFontFace: "Calibri" };

// ---------------------------------------------------------------- yerlesimler
pres.defineSlideMaster({
  title: "KAPAK",
  background: { color: "FFFFFF" },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 1.75, w: 6.4, h: 1.8, fontSize: 40, bold: true,
      color: KIR, align: "left", valign: "bottom", margin: 0 }, text: "" } },
    { line: { x: 0.6, y: 3.75, w: 1.6, h: 0, line: { color: KIR, width: 2.5 } } },
    { placeholder: { options: { name: "body", type: "body", x: 0.6, y: 3.95, w: 6.4, h: 1.2, fontSize: 20, color: KOYU,
      align: "left", valign: "top", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "alt", type: "body", x: 0.6, y: 5.55, w: 6.4, h: 0.4, fontSize: 13, color: GRI,
      align: "left", valign: "middle", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "gorsel", type: "image", x: 7.4, y: 0.75, w: 5.43, h: 6.0, color: GRI, fontSize: 14,
      align: "center", valign: "middle" }, text: "Kapak görseli" } },
  ],
});
pres.defineSlideMaster({
  title: "AKIS",
  background: { color: "FFFFFF" },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.5, y: 0.28, w: 8.5, h: 0.58, fontSize: 24,
      bold: true, color: KIR, align: "left", valign: "middle", margin: 0 }, text: "" } },
    { line: { x: 0.5, y: 0.92, w: 12.33, h: 0, line: { color: KIR, width: 1 } } },
    { placeholder: { options: { name: "lead", type: "body", x: 0.5, y: 1.0, w: 12.33, h: 0.42, fontSize: 13.5,
      color: GRI, align: "left", valign: "middle", margin: 0 }, text: "" } },
  ],
  slideNumber: { x: 12.35, y: 7.08, w: 0.5, h: 0.25, fontSize: 10, color: SOLUK, align: "right" },
});

// ---------------------------------------------------------------- yardimcilar
let s;
const T = (metin, o) => s.addText(metin, Object.assign({ isTextBox: true, fontFace: "Calibri", fontSize: 11,
  color: KOYU, margin: 0.04, valign: "middle", align: "center" }, o));
function kutu(x, y, w, h, tur, ad) {
  const st = {
    veri: { fill: { color: KIR }, line: { type: "none" } },
    islem: { fill: { color: "FFFFFF" }, line: { color: KIR, width: 1.5 } },
    simdi: { fill: { color: "FFFFFF" }, line: { color: KIR, width: 3.5 } },
    onay: { fill: { color: BEJ }, line: { color: KIR, width: 1.5 } },
    sirada: { fill: { color: "FFFFFF" }, line: { color: KIR, width: 1.5, dashType: "dash" } },
    gri: { fill: { color: ACIK }, line: { type: "none" } },
    soluk: { fill: { color: "FFFFFF" }, line: { color: SOLUK, width: 1.5, dashType: "dash" } },
    cerceve: { fill: { color: "FFFFFF" }, line: { color: SOLUK, width: 1 } },
  }[tur];
  const o = Object.assign({ x, y, w, h, rectRadius: 0.1, objectName: ad }, st);
  if (tur === "veri") o.shadow = { type: "outer", color: "000000", opacity: 0.2, blur: 4, offset: 2, angle: 90 };
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, o);
}
const dik = (x, y, w, h, renk, ad, cizgi) => s.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill: { color: renk },
  line: cizgi ? { color: cizgi, width: 0.75 } : { type: "none" }, objectName: ad });
const ok = (x1, y1, x2, y2, ad, renk) => s.addShape(pres.shapes.LINE, {
  x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1) || 0.001, h: Math.abs(y2 - y1) || 0.001,
  flipH: x2 < x1, flipV: y2 < y1,
  line: { color: renk || KIR, width: 1.25, endArrowType: "triangle" }, objectName: ad || "ok" });
function daire(metin, cx, cy, d, o = {}) {
  s.addShape(pres.shapes.OVAL, { x: cx - d / 2, y: cy - d / 2, w: d, h: d, fill: { color: o.fill || KIR },
    line: o.line || { type: "none" }, objectName: "daire " + (o.ad || metin) });
  T(String(metin), { x: cx - d / 2, y: cy - d / 2, w: d, h: d, fontSize: o.fontSize || 12, bold: true,
    color: o.color || "FFFFFF", margin: 0 });
}
function lejant(ogeler) {
  ogeler.forEach((l, i) => {
    const x = 9.2 + (i % 2) * 1.85, y = 0.22 + Math.floor(i / 2) * 0.32;
    kutu(x, y + 0.04, 0.42, 0.2, l[0], "lejant " + l[1]);
    T(l[1], { x: x + 0.5, y, w: 1.32, h: 0.28, fontSize: 10, color: GRI, align: "left", margin: 0 });
  });
}
const LEJANT = [["veri", "Veri / Çıktı"], ["islem", "İşlem (kod)"], ["onay", "Kullanıcı onayı"], ["sirada", "İsteğe bağlı"]];
const dipnot = (m) => T(m, { x: 0.5, y: 6.62, w: 11.7, h: 0.28, fontSize: 10.5, italic: true, color: GRI, align: "left", margin: 0 });
const etiket = (m, x, y, w) => T(m, { x, y, w: w || 5, h: 0.26, fontSize: 11, bold: true, color: GRI, align: "left", margin: 0 });
function onayPill(cx, y, ad) {
  kutu(cx - 0.4, y, 0.8, 0.26, "onay", "onay " + ad);
  T("onay", { x: cx - 0.4, y, w: 0.8, h: 0.26, fontSize: 10, bold: true, color: KIR, margin: 0 });
}
function islem(x, y, w, h, baslik, kim, aciklama, tur, renk) {
  kutu(x, y, w, h, tur || "islem", baslik);
  const r = [{ text: baslik, options: { bold: true, color: renk || KIR, fontSize: 12.5, breakLine: !!(kim || aciklama) } }];
  if (kim) r.push({ text: kim, options: { fontSize: 9.5, bold: true, color: GRI, breakLine: !!aciklama } });
  if (aciklama) r.push({ text: aciklama, options: { fontSize: 10.5, color: renk ? GRI : KOYU } });
  T(r, { x: x + 0.06, y: y + 0.04, w: w - 0.12, h: h - 0.08, paraSpaceAfter: 2 });
}
function veri(x, y, w, h, baslik, alt) {
  kutu(x, y, w, h, "veri", baslik);
  T(alt ? [{ text: baslik, options: { bold: true, fontSize: 12.5, breakLine: true } }, { text: alt, options: { fontSize: 10.5 } }]
    : [{ text: baslik, options: { bold: true, fontSize: 12.5 } }], { x: x + 0.06, y, w: w - 0.12, h, color: "FFFFFF" });
}
const maddeler = (liste) => liste.map((m, j) => ({ text: m, options: { bullet: { indent: 10 }, breakLine: j < liste.length - 1 } }));
function kart(x, y, w, h, tur, baslik, liste, o = {}) {
  kutu(x, y, w, h, tur, "kart " + baslik);
  T(baslik, { x: x + 0.2, y: y + 0.1, w: w - 0.4, h: 0.34, fontSize: o.baslikBoy || 13, bold: true, color: KIR, align: "left", margin: 0 });
  const govde = typeof liste === "string" ? liste : maddeler(liste);
  T(govde, { x: x + 0.2, y: y + 0.48, w: w - 0.4, h: h - 0.56, fontSize: o.boy || 11, align: "left", valign: "top", margin: 0, paraSpaceAfter: 3 });
}
function yeni(baslik, bolum, ust) {
  s = pres.addSlide({ masterName: "AKIS", sectionTitle: bolum });
  s.addText(baslik, { placeholder: "title" });
  s.addText(ust, { placeholder: "lead" });
  return s;
}

const B1 = "Giriş", B2 = "Nasıl çalışır", B3 = "Yapılanlar", B4 = "Sırada ve durum";

// =====================================================================
// 0  KAPAK
pres.addSection({ title: B1 });
s = pres.addSlide({ masterName: "KAPAK", sectionTitle: B1 });
s.addText("Akıllı Modelleme Platformu", { placeholder: "title" });
s.addText("Ne amaçlıyor, nasıl çalışıyor, bugüne kadar ne yapıldı", { placeholder: "body" });
s.addText("Ekiplere tanıtım · Kasım 2026", { placeholder: "alt" });
s.addNotes("Kapak görseli için sağdaki yer tutucuya tıklayıp resim ekleyin. Sunum, platformu hiç bilmeyen ekiplere göre sıralandı: " +
  "neden yapıyoruz, nedir, nasıl çalışır, bugüne kadar hangi adımlar geliştirildi, sırada ne var.");

// =====================================================================
// 1  NEDEN
s = yeni("Akıllı Modelleme Platformu · Neden Yapıyoruz", B1,
  "Model geliştirmenin tekrar eden işleri bugün büyük ölçüde elle yürüyor; platform bu işleri tek akışta toplamayı amaçlıyor.");
T("Projenin Amacı", { x: 0.5, y: 1.52, w: 1.6, h: 0.66, fontSize: 15, italic: true, color: KIR, align: "left", margin: 0 });
kutu(2.15, 1.52, 10.68, 0.66, "islem", "amaç");
T("Model geliştirme sürecini yapay zekâ ile hızlandırmak, modele yalnız katkısı ölçülen değişkenleri almak ve harcanan emeği katma değeri yüksek işlere yönlendirmek.",
  { x: 2.3, y: 1.52, w: 10.38, h: 0.66, fontSize: 13 });
etiket("Konu", 0.5, 2.36, 2.4);
etiket("Elle yürütülen süreçte", 3.15, 2.36, 4.3);
etiket("Platformda", 7.9, 2.36, 4.93);
const neden = [
  ["Sözlük ve kolon adları", "Kısaltmalı kolon adları ve eksik ya da tutarsız açıklamalar her çalışmada yeniden çözülür.",
    "Adlar ve açıklamalar bir kez onaylanır, hafızada kalır; sonraki çalışmaya hazır gelir."],
  ["Veri kalitesi", "Kontroller kişiden kişiye değişir; neyin neden çıkarıldığı her zaman kayda geçmez.",
    "Aynı 26 kontrol her çalışmada verinin tamamında yapılır; her karar gerekçesiyle kaydedilir."],
  ["Değişken üretimi", "Dönüşümler için kod elle yazılır; hangilerinin denendiği kişinin deneyimine bağlıdır.",
    "Dönüşümleri yapay zekâ önerir, katkısını kod ölçer, kullanıcı seçer; kod yazmak gerekmez."],
  ["İzlenebilirlik", "Kararların izi dağınık notlarda ve dosyalarda kalır; çalışmayı devralmak zordur.",
    "Her adımın kararı, gerekçesi ve üretim kodu tek yerde durur; çalışma kaldığı yerden açılır."],
];
neden.forEach((n, i) => {
  const y = 2.66 + i * 0.92;
  veri(0.5, y, 2.4, 0.82, n[0]);
  kutu(3.15, y, 4.3, 0.82, "cerceve", "bugün " + n[0]);
  T(n[1], { x: 3.27, y, w: 4.06, h: 0.82, fontSize: 11.5, color: GRI, align: "left" });
  ok(7.48, y + 0.41, 7.87, y + 0.41, "ok " + n[0]);
  kutu(7.9, y, 4.93, 0.82, "islem", "platform " + n[0]);
  T(n[2], { x: 8.02, y, w: 4.69, h: 0.82, fontSize: 11.5, align: "left" });
});
dipnot("Platform şu an sınıflandırma modelleri (0 ve 1 değerli hedef) için açık; farklı veri setlerinde aynı akış kullanılır.");
s.addNotes("Bu slayt neden sorusunu cevaplar. Soldaki sütun elle yürütülen bir model geliştirme sürecindeki tipik durumu, sağdaki sütun platformun bunu nasıl ele aldığını gösterir. " +
  "Soldaki ifadeler genel çerçevedir; kendi ekibinizin durumuna göre düzenleyin. Sağdaki maddelerin hepsi platformda bugün çalışan özelliklerdir.");

// =====================================================================
// 2  NEDIR
s = yeni("Akıllı Modelleme Platformu · Nedir, Nasıl Çalışır", B1,
  "Dataiku içinde çalışan bir web uygulaması: ham veriden modele giden yolu adım adım yürütür; her adımda önerir, onayla ilerler.");
const roller = [
  ["gri", "Yapay zekâ önerir", ["Kolon adlarının ve açıklamalarının anlamı", "Kalite kontrollerinde anlam gerektiren kararlar",
    "Hangi kolona hangi dönüşümün uygulanacağı, gerekçesiyle", "Kullanıcının sorularına cevap"]],
  ["onay", "Kullanıcı onaylar", ["Her öneriyi gerekçesiyle görür", "Değiştirir, ekler ya da çıkarır",
    "Onaylamadığı hiçbir şey uygulanmaz", "İstediği adıma geri dönebilir"]],
  ["islem", "Kod hesaplar", ["Bütün sayım ve ölçümleri verinin tamamında yapar", "Onaylanan düzeltmeleri ve değişkenleri üretir",
    "Yapay zekânın cevabını denetler", "Kararı, gerekçeyi ve üretim kodunu kaydeder"]],
];
roller.forEach((r, i) => {
  const x = 0.5 + i * (3.75 + 0.54);
  kutu(x, 1.6, 3.75, 3.0, r[0], "rol " + r[1]);
  daire(i + 1, x + 0.5, 2.05, 0.5, { fontSize: 16, ad: "rol no " + (i + 1) });
  T(r[1], { x: x + 0.9, y: 1.8, w: 2.7, h: 0.5, fontSize: 17, bold: true, color: KIR, align: "left", margin: 0 });
  T(maddeler(r[2]), { x: x + 0.25, y: 2.5, w: 3.3, h: 2.0, fontSize: 12.5, align: "left", valign: "top", margin: 0, paraSpaceAfter: 8 });
  if (i < 2) ok(x + 3.75 + 0.06, 3.1, x + 3.75 + 0.48, 3.1, "ok rol " + i);
});
etiket("Nerede çalışır", 0.5, 4.88);
const nerede = [
  ["Dataiku içinde", "Tarayıcıdan, Dataiku projesinin içinden açılır"],
  ["Veri Dataiku'dan", "Yetkiniz olan veri setleri listeden seçilir"],
  ["Büyük veri kümede", "Büyük tablolar Spark ile işlenir; örnekleme yapılmaz"],
  ["Kayıt ve hafıza", "Çalışmalar ve onaylanan bilgiler proje klasöründe saklanır"],
];
const nw = (12.33 - 0.75) / 4;
nerede.forEach((n, i) => {
  const x = 0.5 + i * (nw + 0.25);
  kutu(x, 5.18, nw, 1.0, "gri", "nerede " + n[0]);
  T([{ text: n[0], options: { bold: true, fontSize: 12.5, color: KIR, breakLine: true } }, { text: n[1], options: { fontSize: 11 } }],
    { x: x + 0.12, y: 5.18, w: nw - 0.24, h: 1.0, paraSpaceAfter: 2 });
});
dipnot("Yapay zekâ yalnız önerir; sayılar her zaman koddan gelir, karar her zaman kullanıcınındır.");
s.addNotes("Platformun çalışma ilkesi üç role dayanır. Yapay zekâ (bir dil modeli) öneri ve gerekçe üretir. Kullanıcı her öneriyi görür ve onaylar. " +
  "Hesaplamayı, üretimi ve kaydı kod yapar; yapay zekânın cevabı da kodla denetlenir. Dil modeline Dataiku'nun LLM bağlantısı üzerinden erişilir.");

// =====================================================================
// 3  UCTAN UCA AKIS
pres.addSection({ title: B2 });
s = yeni("Akıllı Modelleme Platformu · Uçtan Uca Akış", B2,
  "Beş faz; her faz bir öncekinin çıktısını kullanır. Her fazda yapay zekâ önerir, kullanıcı onaylar, kod uygular.");
lejant([["veri", "Veri / Çıktı"], ["islem", "İşlem (kod)"], ["onay", "Kullanıcı onayı"], ["soluk", "Sırada"]]);
{
  const PX = 2.35, PW = 1.85, PG = (12.83 - PX - 5 * PW) / 4;
  kutu(PX, 1.52, 12.83 - PX, 0.4, "islem", "yapay zekâ bandı");
  T([{ text: "Yapay Zekâ ve Sohbet  ", options: { bold: true, color: KIR } },
    { text: "her adımda öneriyi gerekçesiyle sunar, soruları yanıtlar" }], { x: PX, y: 1.52, w: 12.83 - PX, h: 0.4, fontSize: 11.5 });
  veri(0.5, 2.47, 1.5, 1.45, "Girdi", "Veri seti ve sözlük; hiç değişmez");
  ok(2.0, 3.2, PX - 0.02, 3.2, "ok girdi");
  const fz = [
    ["01 Çalışma Kurulumu", "Veri ve sözlük seçilir; kolonların anlamı ve adları onaylanır; veri bölünür", "Güncel Veri ve Sözlük", "g", "Geliştirildi"],
    ["02 Değişken Mühendisliği", "Kalite kontrol edilir; bilinen dönüşümlerle ve yapay zekâ ile yeni değişkenler üretilir", "Yeni Değişkenler", "s",
      "02.1 geliştirildi · 02.3 sırada"],
    ["03 Veri Anlama ve Hazırlama", "Değişkenlerin hedefle ilişkisi ve zamandaki kararlılığı ölçülür; set sabitlenir", "Analitik Baz Set", "r", "Sırada"],
    ["04 Değişken Değerlendirme", "Hedefi ele veren şüpheli değişkenler ayıklanır; katkısı zayıf olanlar elenir", "Aday Değişken Seti", "r", "Sırada"],
    ["05 Modelleme ve Finalizasyon", "Modeller aynı koşullarda karşılaştırılır; final model doğrulanır ve belgelenir", "Final Model ve Doküman", "r", "Sırada"],
  ];
  fz.forEach((f, i) => {
    const x = PX + i * (PW + PG), cx = x + PW / 2, sirada = f[3] === "r";
    ok(cx, 1.92, cx, 2.02, "ok bant " + i, sirada ? SOLUK : KIR);
    onayPill(cx, 2.03, f[0]);
    ok(cx, 2.29, cx, 2.45, "ok onay " + i, sirada ? SOLUK : KIR);
    islem(x, 2.47, PW, 1.45, f[0], "", f[1], sirada ? "soluk" : f[3] === "s" ? "simdi" : "islem", sirada ? GRI : undefined);
    if (i < 4) ok(x + PW + 0.02, 3.2, x + PW + PG - 0.02, 3.2, "ok faz " + i, i >= 1 ? SOLUK : KIR);
    ok(cx, 3.92, cx, 4.06, "ok çıktı " + i, sirada ? SOLUK : KIR);
    if (sirada) {
      kutu(x, 4.08, PW, 0.52, "soluk", "çıktı " + f[2]);
      T(f[2], { x, y: 4.08, w: PW, h: 0.52, fontSize: 11, bold: true, color: GRI });
    } else veri(x, 4.08, PW, 0.52, f[2]);
    if (f[3] === "s") {
      kutu(x + 0.1, 4.7, PW - 0.2, 0.26, "veri", "şu an");
      T("Şu an: 02.2 üzerinde çalışılıyor", { x: x + 0.1, y: 4.7, w: PW - 0.2, h: 0.26, fontSize: 9, bold: true, color: "FFFFFF", margin: 0 });
      T(f[4], { x, y: 4.98, w: PW, h: 0.24, fontSize: 9.5, color: GRI, margin: 0 });
    } else T(f[4], { x, y: 4.7, w: PW, h: 0.26, fontSize: 10, color: GRI, margin: 0, bold: f[3] === "g" });
  });
  kutu(PX, 5.36, 12.83 - PX, 0.4, "veri", "proje hafızası");
  T([{ text: "Proje Hafızası  ", options: { bold: true } },
    { text: "onaylanan tanımlar, ad parçaları ve kararlar burada tutulur; aynı şey iki kez sorulmaz" }],
    { x: PX, y: 5.36, w: 12.83 - PX, h: 0.4, fontSize: 11.5, color: "FFFFFF" });
  kutu(0.5, 5.95, 12.33, 0.55, "gri", "hedef");
  T([{ text: "Sonunda hedeflenen:  ", options: { bold: true, color: KIR } },
    { text: "kod yazmadan, onaylarla ilerleyen bir süreçle doğrulanmış final model, değişken kataloğu ve model dokümanı." }],
    { x: 0.7, y: 5.95, w: 11.93, h: 0.55, fontSize: 12 });
}
s.addNotes("Bütün yolun haritası. Girdi kullanıcının seçtiği veri seti ve sözlüğüdür; platform ona dokunmaz. Kırmızı kutular her fazın çıktısıdır. " +
  "Düz çerçeveli fazlar geliştirildi, kalın çerçeveli faz üzerinde çalışılıyor, kesik gri çerçeveliler sırada. " +
  "02'nin içinde 02.1 Veri Profili ve Kalite geliştirildi, şu an 02.2 Geleneksel Değişken Üretimi üzerinde çalışıyoruz.");

// =====================================================================
// 4  BIR ADIM NASIL ILERLER
s = yeni("Akıllı Modelleme Platformu · Bir Adım Nasıl İlerler", B2,
  "Her adım aynı sırayı izler; kullanıcı onaylamadan veriye hiçbir şey uygulanmaz.");
etiket("Adımın akışı", 0.5, 1.47);
const dongu = [
  ["Analiz", "kod", "Veri ve önceki kararlar okunur; sayımlar verinin tamamında yapılır.", "islem"],
  ["Öneri", "yapay zekâ ve kod", "Sonuç ve öneri, gerekçesiyle bir kartta gösterilir.", "gri"],
  ["İnceleme", "kullanıcı", "Kartta seçer, değiştirir; isterse sohbetle sorar.", "onay"],
  ["Onay", "kullanıcı", "Onay düğmesi kararı kesinleştirir.", "onay"],
  ["Uygulama ve kayıt", "kod", "Karar veriye uygulanır; gerekçe ve üretim kodu kaydedilir.", "islem"],
];
dongu.forEach((d, i) => {
  const y = 1.78 + i * 0.84;
  daire(i + 1, 0.72, y + 0.36, 0.38, { fontSize: 13, ad: "adım no " + (i + 1) });
  if (i < 4) ok(0.72, y + 0.57, 0.72, y + 0.99, "ok döngü " + i);
  kutu(1.1, y, 5.4, 0.72, d[3], "döngü " + d[0]);
  T([{ text: d[0], options: { bold: true, color: KIR, fontSize: 12.5, breakLine: true } }, { text: d[1], options: { fontSize: 9.5, bold: true, color: GRI } }],
    { x: 1.2, y, w: 1.75, h: 0.72, align: "left", margin: 0 });
  T(d[2], { x: 3.0, y, w: 3.4, h: 0.72, fontSize: 11, align: "left", margin: 0 });
});
kutu(1.1, 6.02, 5.4, 0.46, "sirada", "geri dön");
T([{ text: "Geri Dön  ", options: { bold: true, color: KIR } }, { text: "önceki bir adıma dönülür, oradan yeniden ilerlenir" }],
  { x: 1.2, y: 6.02, w: 5.2, h: 0.46, fontSize: 11, align: "left", margin: 0 });
// ekran semasi
etiket("Ekran (şematik)", 6.95, 1.47);
{
  const x0 = 6.95, y0 = 1.78, w0 = 5.88, h0 = 4.7;
  kutu(x0, y0, w0, h0, "cerceve", "ekran çerçevesi");
  dik(x0 + 0.04, y0 + 0.04, 1.5, h0 - 0.08, ACIK, "sol bar");
  const menu = [["Ana Sayfa", 0.22, false], ["Model Platformu", 0.62, true], ["Model Akışı", 0.92, false, true], ["Model Gösterge Paneli", 1.2, false],
    ["Model Değişkenleri", 1.48, false], ["Model Özeti", 1.76, false], ["Arşiv", 3.95, false], ["Yeni Çalışma", 4.23, false]];
  menu.forEach((m) => {
    if (m[3]) dik(x0 + 0.04, y0 + m[1], 0.05, 0.26, KIR, "seçili işaret");
    T(m[0], { x: x0 + (m[1] > 0.7 && m[1] < 2 ? 0.28 : 0.16), y: y0 + m[1], w: 1.3, h: 0.26, fontSize: 9, bold: !!(m[2] || m[3]),
      color: m[3] ? KIR : KOYU, align: "left", margin: 0 });
  });
  const mx = x0 + 1.7, mw = w0 - 1.86;
  kutu(mx, y0 + 0.16, mw, 0.42, "cerceve", "iş akışı barı");
  kutu(mx + 0.08, y0 + 0.23, 0.8, 0.28, "gri", "iş akışı düğmesi");
  T("İş Akışı", { x: mx + 0.08, y: y0 + 0.23, w: 0.8, h: 0.28, fontSize: 9, bold: true, margin: 0 });
  T("bulunulan faz ve adım", { x: mx + 0.98, y: y0 + 0.16, w: 1.7, h: 0.42, fontSize: 9, color: GRI, align: "left", margin: 0 });
  T("tamamlanan / toplam adım", { x: mx + mw - 1.75, y: y0 + 0.16, w: 1.67, h: 0.42, fontSize: 9, color: GRI, align: "right", margin: 0 });
  kutu(mx, y0 + 0.74, mw, 3.0, "islem", "adım bloğu");
  T("Adım bloğu", { x: mx + 0.15, y: y0 + 0.82, w: 2.4, h: 0.28, fontSize: 11.5, bold: true, color: KIR, align: "left", margin: 0 });
  T("sonuç ve öneri, gerekçesiyle", { x: mx + 0.15, y: y0 + 1.1, w: 2.8, h: 0.24, fontSize: 9, color: GRI, align: "left", margin: 0 });
  for (let k = 0; k < 4; k++) {
    const yy = y0 + 1.48 + k * 0.36;
    dik(mx + 0.15, yy, 1.3, 0.22, "E3E3E3", "satır kolon " + k);
    dik(mx + 1.55, yy, 1.45 - (k % 2) * 0.3, 0.22, ACIK, "satır bulgu " + k);
    kutu(mx + mw - 0.95, yy - 0.02, 0.8, 0.26, "onay", "satır karar " + k);
    T("karar", { x: mx + mw - 0.95, y: yy - 0.02, w: 0.8, h: 0.26, fontSize: 8.5, color: KIR, margin: 0 });
  }
  kutu(mx + 0.15, y0 + 3.28, 0.95, 0.32, "cerceve", "geri dön düğmesi");
  T("Geri Dön", { x: mx + 0.15, y: y0 + 3.28, w: 0.95, h: 0.32, fontSize: 9.5, margin: 0 });
  kutu(mx + mw - 1.1, y0 + 3.28, 0.95, 0.32, "veri", "onayla düğmesi");
  T("Onayla", { x: mx + mw - 1.1, y: y0 + 3.28, w: 0.95, h: 0.32, fontSize: 9.5, bold: true, color: "FFFFFF", margin: 0 });
  kutu(mx, y0 + 3.9, mw, 0.42, "cerceve", "sohbet kutusu");
  T("Soru ya da istek yazılır", { x: mx + 0.15, y: y0 + 3.9, w: 2.6, h: 0.42, fontSize: 9.5, italic: true, color: GRI, align: "left", margin: 0 });
  daire(2, mx + mw - 0.3, y0 + 1.02, 0.3, { fontSize: 10.5, ad: "işaret 2" });
  daire(3, mx + mw - 0.3, y0 + 4.11, 0.3, { fontSize: 10.5, ad: "işaret 3" });
  daire(4, mx + mw - 1.3, y0 + 3.44, 0.3, { fontSize: 10.5, ad: "işaret 4" });
}
dipnot("Her model için bir çalışma açılır; çalışma her adımda kaydedilir ve Arşiv'den kaldığı yerden sürdürülür.");
s.addNotes("Kullanıcının platformda gördüğü şey budur: adımlar alt alta bloklar hâlinde ilerler. Her blokta analiz sonucu, öneri ve gerekçesi, kullanıcının karar verdiği alanlar ve onay düğmesi bulunur. " +
  "Sağdaki çizim ekranın şemasıdır; gerçek ekran görüntüsüyle değiştirilebilir. Şemadaki 2, 3 ve 4 numaraları soldaki adımlara karşılık gelir.");

// =====================================================================
// 5  VERI KURALI VE GUVENCELER
s = yeni("Akıllı Modelleme Platformu · Veri Kuralı ve Güvenceler", B2,
  "Seçilen veri setine ve sözlüğe dokunulmaz; platform kendi kopyalarıyla çalışır.");
veri(0.5, 1.62, 3.3, 1.0, "Seçilen Veri Seti ve Sözlük", "kullanıcının verisi; hiçbir şey yazılmaz");
ok(3.82, 2.12, 4.48, 2.12, "ok kopya");
veri(4.5, 1.62, 3.3, 1.0, "Baz Kopya", "birebir kopya; bir kez yazılır, değişmez");
ok(7.82, 2.12, 8.48, 2.12, "ok güncel");
veri(8.5, 1.62, 4.33, 1.0, "Güncel Kopya", "verinin ve sözlüğün en son hâli; her adımda güncellenir");
T("Dataiku'daki adı: <Çalışma>_BAZ_VERI, <Çalışma>_BAZ_SOZLUK", { x: 4.5, y: 2.66, w: 3.3, h: 0.4, fontSize: 9.5, color: GRI, valign: "top" });
T("Dataiku'daki adı: <Çalışma>_UPDT_VERI, <Çalışma>_UPDT_SOZLUK", { x: 8.5, y: 2.66, w: 4.33, h: 0.4, fontSize: 9.5, color: GRI, valign: "top" });
etiket("Güncel kopya adım adım zenginleşir", 0.5, 3.3);
T("kalın çerçeve: üzerinde çalışılan adım · kesik çerçeve: sırada", { x: 6.5, y: 3.3, w: 6.33, h: 0.26, fontSize: 10, color: GRI, align: "right", margin: 0 });
const zen = [["01", "tipler, yeni adlar, bölme", "islem"], ["02.1", "düzeltmeler, çözüm kolonları", "islem"], ["02.2", "yeni değişkenler", "simdi"],
  ["02.3", "yapay zekâ keşfi", "soluk"], ["03", "analitik baz set", "soluk"]];
const zw = (12.33 - 4 * 0.3) / 5;
zen.forEach((z, i) => {
  const x = 0.5 + i * (zw + 0.3), sr = z[2] === "soluk";
  kutu(x, 3.62, zw, 0.66, z[2], "zenginleşme " + z[0]);
  T([{ text: z[0] + "  ", options: { bold: true, color: sr ? GRI : KIR, fontSize: 12 } }, { text: z[1], options: { fontSize: 10.5, color: sr ? GRI : KOYU } }],
    { x: x + 0.05, y: 3.62, w: zw - 0.1, h: 0.66 });
  if (i < 4) ok(x + zw + 0.03, 3.95, x + zw + 0.27, 3.95, "ok zenginleşme " + i, i >= 2 ? SOLUK : KIR);
});
const guv = [
  ["Girdi değişmez", "Seçilen veri setine ve sözlüğe hiçbir şey yazılmaz. Düzeltmeler ve yeni adlar yalnız platformun kopyalarında geçerlidir."],
  ["Tam veri, örneklem yok", "Sayımlar ve ölçümler verinin tamamında yapılır. Büyük tablolar kümede işlenir."],
  ["Sızıntıya karşı sınır", "Doldurma değerleri ve dönüşüm ayarları yalnız eğitim setinden öğrenilir. Geleceğe bakan ya da hedefi ele veren kolonlar ayıklanır."],
  ["Her karar kayıtlı", "Her adımın kararı, gerekçesi ve üretim kodu çalışmanın kaydında durur."],
];
const gw = (12.33 - 0.75) / 4;
guv.forEach((g, i) => kart(0.5 + i * (gw + 0.25), 4.62, gw, 1.8, "gri", g[0], g[1], { boy: 11.5 }));
dipnot("Sızıntı: modelin gerçek kullanımda bilemeyeceği bir bilginin eğitim verisine karışması; model kâğıt üstünde iyi, gerçekte kötü çıkar.");
s.addNotes("Başka ekiplerin ilk sorusu genellikle veriye ne olduğudur. Seçilen tablo ve sözlük yalnız okunur. Platform bir kez birebir kopya alır (baz kopya) ve bütün değişiklikleri güncel kopyaya yazar. " +
  "Geri dönülürse güncel kopya, baz kopyadan kararlar yeniden uygulanarak kurulur. Çalışma adı Dataiku'daki veri seti adlarının önüne gelir.");

// =====================================================================
// 6  01 CALISMA KURULUMU
pres.addSection({ title: B3 });
s = yeni("01 Çalışma Kurulumu · Veri ve Sözlük Hazırlığı", B3,
  "Hangi tabloyla çalışılacağı, kolonların ne anlama geldiği, neyin tahmin edileceği ve verinin nasıl bölüneceği bu fazda belirlenir.");
lejant(LEJANT);
{
  veri(0.5, 1.92, 1.5, 0.95, "Veri Seti ve Sözlük", "Dataiku'dan seçilir");
  const bx = 2.3, bw = 1.57, bg = (12.83 - bx - 6 * bw) / 5;
  ok(2.0, 2.4, bx - 0.02, 2.4, "ok girdi");
  const ad = [
    ["Başlangıç ve Veri Seçimi", "Hazır tablo seçilir ya da kaynak tablolar birleştirilir"],
    ["Kolon Rolleri", "Hedef, kimlik ve dönem kolonu belirlenir"],
    ["Eksik Sözlük Tanımları", "Açıklaması olmayan kolonlara öneri getirilir"],
    ["Sözlük ve Kolon Adı Kontrolü", "Adlar ve açıklamalar düzeltilir; sonraki sayfada"],
    ["Değişken Listesi ve Tip Kontrolü", "Liste, tipler ve tanımlar son kez onaylanır"],
    ["Örneklem ve Doğrulama Tasarımı", "Veri eğitim ve ölçüm setlerine ayrılır"],
  ];
  ad.forEach((a, i) => {
    const x = bx + i * (bw + bg);
    onayPill(x + bw / 2, 1.5, a[0]);
    ok(x + bw / 2, 1.76, x + bw / 2, 1.9, "ok onay " + i);
    kutu(x, 1.92, bw, 0.95, i === 3 ? "sirada" : "islem", a[0]);
    T(a[0], { x: x + 0.05, y: 1.92, w: bw - 0.1, h: 0.95, fontSize: 12, bold: true, color: KIR });
    T(a[1], { x, y: 2.92, w: bw, h: 0.52, fontSize: 10, color: GRI, valign: "top", margin: 0 });
    if (i < 5) ok(x + bw + 0.02, 2.4, x + bw + bg - 0.02, 2.4, "ok adım " + i);
  });
  const cw = (12.33 - 0.5) / 3;
  kart(0.5, 3.6, cw, 1.7, "gri", "Kolon rolleri nedir", [
    "Hedef: modelin tahmin edeceği kolon", "Kimlik: müşteriyi ya da kaydı gösteren kolon", "Dönem: kaydın ait olduğu tarih",
    "Bu üç kolon hiçbir dönüşüme girmez"]);
  kart(0.5 + cw + 0.25, 3.6, cw, 1.7, "gri", "Sözlük ve eksik tanımlar", [
    "Sözlük: her kolonun ne anlama geldiğini yazan tablo", "Tanımı olmayan kolona önce onaylı tanım, yoksa yapay zekâ önerisi getirilir",
    "Tamamen boş ve tek değerli kolonlar çıkarılır"]);
  const x3 = 0.5 + 2 * (cw + 0.25);
  kutu(x3, 3.6, cw, 1.7, "gri", "kart bölme");
  T("Veri neden bölünür", { x: x3 + 0.2, y: 3.7, w: cw - 0.4, h: 0.34, fontSize: 13, bold: true, color: KIR, align: "left", margin: 0 });
  const seg = [["Train", 0.5, KIR], ["Test", 0.22, KIR2], ["Validasyon", 0.28, GRI]];
  let sx = x3 + 0.2;
  seg.forEach((g) => {
    const w = (cw - 0.4) * g[1];
    dik(sx, 4.1, w - 0.03, 0.3, g[2], "set " + g[0]);
    T(g[0], { x: sx, y: 4.1, w: w - 0.03, h: 0.3, fontSize: 10, bold: true, color: "FFFFFF", margin: 0 });
    sx += w;
  });
  T("Model Train setinde öğrenir, ayarlar Test setinde seçilir, son ölçüm zamanda sonraki Validasyon setinde yapılır. Başarı böylece modelin görmediği veride ölçülür.",
    { x: x3 + 0.2, y: 4.46, w: cw - 0.4, h: 0.8, fontSize: 10.5, align: "left", valign: "top", margin: 0 });
  etiket("Bu fazın çıktıları", 0.5, 5.4);
  const ck = [["Baz Kopya", "girdinin değişmeyen kopyası"], ["Güncel Veri ve Sözlük", "tipler, tanımlar, yeni adlar"],
    ["Bölme", "her satırın hangi sette olduğu"], ["Proje Hafızası", "onaylanan tanımlar ve anlamlar"]];
  const ckw = (12.33 - 0.75) / 4;
  ck.forEach((c, i) => veri(0.5 + i * (ckw + 0.25), 5.68, ckw, 0.72, c[0], c[1]));
}
dipnot("Kaynak tablolarla başlanırsa birleştirme planını yapay zekâ önerir; her satır yalnız kendi tarihinden önceki bilgiyi görür.");
s.addNotes("01 fazı geliştirildi. Sözlük, her kolonun ne anlama geldiğini yazan tablodur; seçilmesi zorunlu değildir, eksik tanımlar bu fazda tamamlanır. " +
  "Kolon rollerinde şu an sınıflandırma (0 ve 1 değerli hedef) açıktır. Tablonun daha önce onaylanan rolleri yeni çalışmada hazır gelir. " +
  "Eksik tanımda yapay zekâ, kolon adındaki onaylı parçalara ve benzer kolonların tanımlarına bakarak öneri yazar. " +
  "Çubuktaki genişlikler oran göstermez; bölme oranlarını platform önerir, kullanıcı değiştirebilir.");

// =====================================================================
// 7  SOZLUK VE KOLON ADI KONTROLU
s = yeni("01 Çalışma Kurulumu · Sözlük ve Kolon Adı Kontrolü", B3,
  "Yapay zekâ da insan da kolonu adından ve açıklamasından tanır; bu adım her kolonun kesin anlaşılmasını sağlar.");
{
  T("Örnek kolon adı (gösterim amaçlı)", { x: 0.5, y: 1.6, w: 2.9, h: 0.55, fontSize: 11, bold: true, color: GRI, align: "left", margin: 0 });
  const cip = ["TXN", "OUT", "30D", "AMT"];
  cip.forEach((c, i) => {
    const x = 3.45 + i * 1.25;
    kutu(x, 1.6, 1.13, 0.55, c === "30D" ? "onay" : "islem", "parça " + c);
    T(c, { x, y: 1.6, w: 1.13, h: 0.55, fontSize: 15, bold: true, fontFace: "Courier New", color: KIR, margin: 0 });
  });
  ok(8.5, 1.875, 8.95, 1.875, "ok anlam");
  T("Son 30 günde giden işlemlerin tutarı", { x: 9.05, y: 1.6, w: 3.78, h: 0.55, fontSize: 13, bold: true, align: "left", margin: 0 });
  const k4 = [
    ["1. Dönem Bilgisi", "Adlardaki zaman parçalarının anlamı ve yönü onaylanır. Geleceğe bakan parça sızıntı adayıdır.", "30D = son 30 gün"],
    ["2. Ad Parçaları", "Kısaltmaların anlamı ve standart yazılışı onaylanır. Farklı yazılan aynı parçalar birleşir.", "TXN işlem · OUT giden · AMT tutar"],
    ["3. Kolon Kartları", "Onaylı parçalardan her kolonun kartı kurulur, sözlükteki tanımla karşılaştırılır; tek ve açık bir açıklama yazılır.", "Son 30 günde giden işlemlerin tutarı"],
    ["4. Kolon Adları", "Yeni ad standart yazılışlarla ve belirlenen sırayla kurulur. Eski ad saklanır.", [{ text: "TXN_OUT_30D_AMT", options: { breakLine: true } }, { text: "→ TXN_OUT_AMT_L30D" }]],
  ];
  const kw = (12.33 - 3 * 0.35) / 4;
  k4.forEach((k, i) => {
    const x = 0.5 + i * (kw + 0.35);
    kutu(x, 2.5, kw, 2.15, "islem", "kontrol " + k[0]);
    T(k[0], { x: x + 0.15, y: 2.58, w: kw - 0.3, h: 0.34, fontSize: 13, bold: true, color: KIR, align: "left", margin: 0 });
    T(k[1], { x: x + 0.15, y: 2.95, w: kw - 0.3, h: 1.0, fontSize: 11.5, align: "left", valign: "top", margin: 0 });
    kutu(x + 0.12, 3.98, kw - 0.24, 0.55, "gri", "örnek " + k[0]);
    T(k[2], { x: x + 0.15, y: 3.98, w: kw - 0.3, h: 0.55, fontSize: i === 3 ? 9.5 : 10.5, bold: true, margin: 0, fontFace: i === 3 ? "Courier New" : "Calibri" });
    if (i < 3) ok(x + kw + 0.03, 3.57, x + kw + 0.32, 3.57, "ok kontrol " + i);
  });
  kart(0.5, 4.95, 6.04, 1.5, "gri", "Kullanıcıyı yormadan", [
    "Sorular toplu sorulur; bir cevap ilgili bütün kolonlara uygulanır",
    "Adı yalnız sayılarla ayrılan kolonlar aile olarak birlikte onaylanır",
    "Daha önce onaylanan kontrol yeni çalışmada yeniden uygulanabilir"]);
  etiket("Sonuç", 6.79, 4.95);
  const sn = ["Açık ve tek tip açıklamalar", "Standart kolon adları", "Hafızada kalan anlamlar"];
  const sw = (6.04 - 0.4) / 3;
  sn.forEach((m, i) => veri(6.79 + i * (sw + 0.2), 5.28, sw, 1.17, m));
}
dipnot("Bu adım isteğe bağlıdır. Düzeltmeler yalnız platformun kopyalarına yazılır; kaynak tablo ve sözlük değişmez.");
s.addNotes("Bu adım geliştirildi ve platformun en çok emek verilen kısımlarından biridir. Sözlüklerde tanımların bir kısmı eksik ya da hatalı, adlarda kısaltmalar tutarsız olabilir. " +
  "Dört alt adım sırayla çalışır ve her biri bir öncekinin onayladığını kesin bilgi olarak kullanır. Onaylanan anlamlar hafızaya yazılır; aynı parça bir sonraki çalışmada sorulmaz. " +
  "Örnek kolon adı ve anlamları gösterim amaçlıdır.");

// =====================================================================
// 8  02.1 VERI PROFILI VE KALITE
s = yeni("02.1 Veri Profili ve Kalite · Verinin Kusurlarını Bulma", B3,
  "Değişken üretmeden önce verinin kusurları bulunur; her bulgu için öneri sunulur, karar kullanıcıda kalır.");
lejant(LEJANT.slice(0, 3));
{
  veri(0.5, 1.6, 1.7, 0.95, "Güncel Veri", "01'in çıktısı");
  const px = 2.5, pw = 1.75, pg = 0.3;
  ok(2.2, 2.08, px - 0.02, 2.08, "ok girdi");
  const p3 = [
    ["Kontrol Eşikleri", "onay", "Eşikler önerilen değer ve gerekçesiyle sorulur"],
    ["26 Kontrol", "islem", "Verinin tamamında, örneklemesiz"],
    ["Karar Kartı", "onay", "Her bulguya öneri: tut, çıkar, düzelt ya da çözüm"],
    ["Uygulama", "islem", "Kararlar veriye uygulanır ve kaydedilir"],
  ];
  p3.forEach((p, i) => {
    const x = px + i * (pw + pg);
    kutu(x, 1.6, pw, 0.95, p[1], p[0]);
    T(p[0], { x, y: 1.6, w: pw, h: 0.95, fontSize: 13, bold: true, color: KIR });
    T(p[2], { x, y: 2.6, w: pw, h: 0.5, fontSize: 10, color: GRI, valign: "top", margin: 0 });
    ok(x + pw + 0.02, 2.08, x + pw + pg - 0.02, 2.08, "ok adım " + i);
  });
  veri(px + 4 * (pw + pg), 1.6, 12.83 - (px + 4 * (pw + pg)), 0.95, "Güncel Veri", "düzeltilmiş kolonlar, çözüm kolonları");
  etiket("Ne aranır, bulununca ne olur", 0.5, 3.22);
  const g3 = [
    ["Üretime girmez", "7 kontrol · önce çözüm aranır", "Çoğu boş, sabit, kimlik benzeri, çok kategorili ya da birbirinin kopyası kolonlar. Atmak yerine çözüm önerilir: gruplama, “dolu mu” bayrağı, metinden özellik, tarihten gün farkı."],
    ["Karar kullanıcıda", "7 kontrol · tut ya da çıkar", "Sızıntı şüphesi (geleceğe bakan pencere, hedefi neredeyse birebir veren kolon), neredeyse sabit kolon, bir dönemde boş kolon, dönemler arasında sıçrayan değer."],
    ["Düzeltme", "7 kontrol · kolon yerinde düzeltilir", "-999 gibi özel kodlar, “NULL” diye yazılmış boşlar, aynı kategorinin farklı yazımları, beklenmeyen negatifler, uç değerler."],
    ["Bilgi", "5 kontrol · işlem yapılmaz", "Sıfır yoğunluğu, pencereler arası tutarsızlık, tekrar eden satır, eğitim ve ölçüm setleri arasında çakışma."],
  ];
  const gw3 = (12.33 - 0.75) / 4;
  g3.forEach((g, i) => {
    const x = 0.5 + i * (gw3 + 0.25);
    kutu(x, 3.5, gw3, 1.72, "gri", "grup " + g[0]);
    T([{ text: g[0], options: { bold: true, color: KIR, fontSize: 13, breakLine: true } },
      { text: g[1], options: { bold: true, fontSize: 10.5, color: GRI, breakLine: true } },
      { text: g[2], options: { fontSize: 10.5 } }], { x: x + 0.15, y: 3.56, w: gw3 - 0.3, h: 1.62, align: "left", valign: "top", paraSpaceAfter: 3 });
  });
  const alt = [
    ["Öneriyi kim verir", "Çoğunu kod verir, kolonun kendi sayılarına bakarak; gerekçe sayıyla yazılır. Yapay zekâ yalnız anlam gerektiren yerde devreye girer, örneğin aynı içerikli iki kolondan hangisinin kalacağında."],
    ["Sonuç ne olur", "Onaylanan düzeltmeler güncel veriye uygulanır. Üretime girmeyen kolonlardan yeni değişken üretilmez; çözümün ürettiği yeni kolon sonraki adımlara girer."],
  ];
  alt.forEach((a, i) => {
    const x = 0.5 + i * (6.04 + 0.25);
    kutu(x, 5.42, 6.04, 1.05, "islem", a[0]);
    T([{ text: a[0], options: { bold: true, color: KIR, fontSize: 12.5, breakLine: true } }, { text: a[1], options: { fontSize: 10.5 } }],
      { x: x + 0.15, y: 5.44, w: 5.74, h: 1.01, align: "left", paraSpaceAfter: 2 });
  });
}
dipnot("Kontroller verinin tamamında yapılır; eşikler önerilen değerle gelir, kullanıcı değiştirebilir.");
s.addNotes("02.1 geliştirildi. Kontroller dört grupta toplanır. Karar kartında satırlar renklidir: sorunsuz, dikkat, üretime girmez. " +
  "Çözüm seçeneği yalnız işe yarayacaksa sunulur: eğitim setinin bir yarısında öğrenilir, öbür yarısında hedefi ayırıp ayırmadığına bakılır. " +
  "Öğrenilen her şey (gruplar, sınırlar) yalnız eğitim setinden gelir.");

// =====================================================================
// 9  02.2 NASIL CALISIYOR
s = yeni("02.2 Geleneksel Değişken Üretimi · Nasıl Çalışıyor", B3,
  "Var olan kolonlardan oran, fark, eğilim gibi bilinen dönüşümlerle yeni değişkenler türetilir; hangisinin işe yaradığını ölçüm söyler.");
lejant([["veri", "Veri / Çıktı"], ["islem", "İşlem (kod)"], ["onay", "Kullanıcı onayı"], ["gri", "Yapay zekâ"]]);
{
  const r1y = 1.62, r2y = 3.3, bw = 2.3, bh = 1.34;
  const xs = [2.95, 5.45, 7.95, 10.5];
  veri(0.5, r1y, 2.1, bh, "Güncel Veri ve Onaylı Sözlük", "01 ve 02.1'in çıktısı");
  const ust = [
    ["1. Birimler", "kod", "Kolonlar birlikte değerlendirilecek gruplara ayrılır: tek kolon, aynı ölçünün farklı dönemleri, anlamlı çiftler", "islem"],
    ["2. Uygunluk", "kod", "41 dönüşümden hangileri bu grupta yapılabilir; yapılamıyorsa nedeni yazılır", "islem"],
    ["3. Seçim", "yapay zekâ", "Her grup için dönüşümleri seçer ve gerekçesini yazar", "gri"],
    ["4. Katkı Ölçümü", "kod", "Yeni değişken, türetildiği kolonlardan daha fazla bilgi taşıyor mu ölçülür", "islem"],
  ];
  ok(2.6, r1y + bh / 2, xs[0] - 0.02, r1y + bh / 2, "ok girdi");
  ust.forEach((u, i) => {
    islem(xs[i], r1y, bw, bh, u[0], u[1], u[2], u[3]);
    if (i < 3) ok(xs[i] + bw + 0.02, r1y + bh / 2, xs[i + 1] - 0.02, r1y + bh / 2, "ok üst " + i);
  });
  ok(xs[3] + bw / 2, r1y + bh + 0.02, xs[3] + bw / 2, r2y - 0.02, "ok aşağı");
  const alt2 = [
    ["5. Tamamlama", "kod", "Değer katan ama seçilmemiş dönüşüm eklenir; aynı bilgiyi veren ayıklanır", "islem", xs[3]],
    ["6. Karar", "kullanıcı", "Kartta ve sohbette ekler, çıkarır, sorar; son sözü söyler", "onay", xs[2]],
    ["7. Üretim", "kod", "Onayla birlikte değişkenler üretilir, üretim kodu kaydedilir", "islem", xs[1]],
  ];
  alt2.forEach((u, i) => {
    islem(u[4], r2y, bw, bh, u[0], u[1], u[2], u[3]);
    ok(u[4] - 0.02, r2y + bh / 2, (i < 2 ? alt2[i + 1][4] : xs[0]) + bw + 0.02, r2y + bh / 2, "ok alt " + i);
  });
  veri(xs[0], r2y, bw, bh, "Güncel Veri", "yeni değişkenler ve üretim kodu");
  kart(0.5, 4.95, 6.04, 1.5, "gri", "Karar kartında", [
    "Her dönüşüm sade adı, ne yaptığı ve örneğiyle; bu veride kullanılabilir mi, neden",
    "Her öneride kimin önerdiği ve ölçümün ne dediği",
    "Her değişiklik anında görünür ve geri alınabilir"]);
  kart(6.79, 4.95, 6.04, 1.5, "gri", "Plan üzerine sohbette", [
    "“Bütün oranları kaldır” gibi toplu istekler yazılabilir",
    "Cevaplar ölçüme dayanır; değişikliği kod kurar, kullanıcı onaylar",
    "Önceki konuşmalar kısa bir özetle hatırlanır"]);
}
dipnot("Bu adım üzerinde çalışılıyor; kart ve sohbet geri bildirimle güncelleniyor.");
s.addNotes("Şu an üzerinde çalıştığımız adım. Birim, birlikte değerlendirilen kolon ya da kolon grubudur; örneğin aynı ölçünün son 30, 90 ve 180 günlük kolonları bir pencere ailesidir. " +
  "Katkı ölçümü yalnız eğitim satırlarında yapılır: bilgi değeri (IV) en iyi kaynağa göre en az 0,02 artıyorsa ve kaynaklarla sıra ilişkisi 0,95'in altındaysa dönüşüm yeni bilgi sayılır. " +
  "Ağaç ve doğrusal model ayrımı yoktur; iki modelde de kullanılabilecek dönüşümler tek seferde değerlendirilir.");

// =====================================================================
// 10  02.2 UC ASAMA
s = yeni("02.2 Geleneksel Değişken Üretimi · Üç Aşama", B3,
  "Toplam 41 dönüşüm, neye bakarak üretildiklerine göre üç aşamada toplanır.");
{
  const as = [
    ["1. Kolonun kendi dönüşümü", "18 dönüşüm", "Tek bir kolon kendi içinde dönüştürülür: ölçeği düzeltilir, bayrak ya da dilim üretilir.",
      "Logaritma · uç değerleri kırpma · sıraya çevirme · sıfır mı bayrağı · ondalık dilim · kategorinin risk puanı",
      "TXN_OUT_AMT_L30D → logaritması", "Çok büyük tutarların etkisini sıkıştırır, küçük farkları korur."],
    ["2. Aile içi üretim", "13 dönüşüm", "Aynı ölçünün farklı dönemleri birbiriyle karşılaştırılır.",
      "Kısa dönem bölü uzun dönem · önceki döneme göre büyüme · eğilim · düzensizlik · en yoğun dönemin payı",
      "TXN_OUT_AMT_L30D bölü TXN_OUT_AMT_L90D", "Son 30 günün son 90 güne oranı: harcama hızlanıyor mu, yavaşlıyor mu."],
    ["3. Aileler arası üretim", "10 dönüşüm", "Birbiriyle anlamlı ilişkisi olan farklı kolonlar birleştirilir.",
      "Net akış · işlem başına ortalama tutar · alt kırılımın toplamdaki payı · tek kanala yoğunlaşma · segment içindeki yeri",
      "TXN_IN_AMT_L30D eksi TXN_OUT_AMT_L30D", "Net akış: hesaba giren mi fazla, çıkan mı."],
  ];
  const aw = (12.33 - 0.6) / 3;
  as.forEach((a, i) => {
    const x = 0.5 + i * (aw + 0.3);
    veri(x, 1.58, aw, 0.72, a[0], a[1]);
    kutu(x, 2.42, aw, 0.78, "islem", "ne yapar " + i);
    T(a[2], { x: x + 0.12, y: 2.42, w: aw - 0.24, h: 0.78, fontSize: 11.5, align: "left" });
    etiket("Dönüşümlerden örnekler", x, 3.3, aw);
    kutu(x, 3.58, aw, 0.95, "gri", "dönüşümler " + i);
    T(a[3], { x: x + 0.12, y: 3.58, w: aw - 0.24, h: 0.95, fontSize: 11, align: "left" });
    etiket("Örnek (gösterim amaçlı)", x, 4.63, aw);
    kutu(x, 4.91, aw, 0.52, "islem", "örnek " + i);
    T(a[4], { x: x + 0.06, y: 4.91, w: aw - 0.12, h: 0.52, fontSize: 10.5, fontFace: "Courier New", bold: true, color: KIR, margin: 0 });
    T(a[5], { x, y: 5.47, w: aw, h: 0.42, fontSize: 10.5, color: GRI, align: "left", valign: "top", margin: 0 });
  });
  kutu(0.5, 5.95, 12.33, 0.55, "gri", "hangi dönüşüm kalır");
  T([{ text: "Hangi dönüşüm kalır:  ", options: { bold: true, color: KIR } },
    { text: "türetildiği kolonlardan belirgin biçimde daha fazla bilgi taşıyan ve onların kopyası olmayan. Ölçek dönüşümleri yalnız çarpık ya da uç değerli kolonlarda önerilir." }],
    { x: 0.7, y: 5.95, w: 11.93, h: 0.55, fontSize: 11.5, align: "left" });
}
dipnot("Kolon adları 01'de standartlaştırılan adlardır; örnekler gösterim amaçlıdır.");
s.addNotes("Aşama, dönüşümün neye baktığını söyler. Birinci aşama tek kolonla, ikinci aşama aynı ölçünün farklı dönemleriyle, üçüncü aşama birbiriyle ilişkili farklı kolonlarla çalışır. " +
  "Kartta 41 dönüşümün her biri sade adı, ne yaptığı, bu verideki örneği ve bu veride neden kullanılabilir ya da kullanılamaz olduğuyla listelenir.");

// =====================================================================
// 11  SIRADA
pres.addSection({ title: B4 });
s = yeni("Sırada · 02.3 ile 05 Arası", B4,
  "Bu adımların ilk sürümleri kodda var; 02.2 tamamlandıktan sonra bu yapıya göre sırayla ele alınacak.");
lejant([["veri", "Veri / Çıktı"], ["soluk", "Sırada"]]);
{
  veri(0.5, 1.75, 1.65, 2.2, "Güncel Veri", "02.2'nin çıktısı");
  const sx = 2.5, sw = 2.36, sg = (12.83 - sx - 4 * sw) / 3;
  const sr = [
    ["02.3 AI Değişken Keşfi", "Bilinen kalıpların dışında yeni değişken fikirleri aranır. Yapay zekâ kod yazmaz, yalnız denetlenen bir formül yazar; hesabı kod yapar.", "Yeni değişkenler"],
    ["03 Veri Anlama ve Hazırlama", "Her değişkenin hedefle ilişkisi ve zaman içindeki kararlılığı ölçülür. Eksik değerler doldurulur, set sabitlenir.", "Analitik baz set"],
    ["04 Değişken Değerlendirme", "Hedefi ele veren şüpheli değişkenler ayıklanır. Birbirinin tekrarı olan ve katkısı zayıf değişkenler elenir.", "Aday değişken seti"],
    ["05 Modelleme ve Finalizasyon", "Yalnız ham kolonlarla kurulan model ile yeni değişkenli model aynı koşullarda karşılaştırılır; algoritmalar denenir, seçilen model doğrulanır.", "Final model, katalog, doküman"],
  ];
  ok(2.15, 2.85, sx - 0.02, 2.85, "ok girdi", SOLUK);
  sr.forEach((r, i) => {
    const x = sx + i * (sw + sg);
    kutu(x, 1.75, sw, 2.2, "soluk", r[0]);
    T(r[0], { x: x + 0.12, y: 1.83, w: sw - 0.24, h: 0.6, fontSize: 13, bold: true, color: KOYU, align: "left", margin: 0 });
    T(r[1], { x: x + 0.12, y: 2.47, w: sw - 0.24, h: 1.45, fontSize: 11.5, color: KOYU, align: "left", valign: "top", margin: 0 });
    if (i < 3) ok(x + sw + 0.02, 2.85, x + sw + sg - 0.02, 2.85, "ok sıra " + i, SOLUK);
    ok(x + sw / 2, 3.97, x + sw / 2, 4.2, "ok çıktı " + i, SOLUK);
    kutu(x, 4.22, sw, 0.58, "soluk", "çıktı " + r[2]);
    T(r[2], { x, y: 4.22, w: sw, h: 0.58, fontSize: 11.5, bold: true, color: GRI });
  });
  T("Çıktı", { x: 0.5, y: 4.22, w: 1.65, h: 0.58, fontSize: 11, bold: true, color: GRI, align: "right", margin: 0 });
  kutu(0.5, 5.2, 12.33, 1.15, "gri", "hedef");
  T([{ text: "Sonunda hedeflenen", options: { bold: true, color: KIR, fontSize: 13, breakLine: true } },
    { text: "Yeni değişkenlerin modele katkısı ölçülmüş, her kararı izlenebilen ve belgelenmiş bir final model; yanında değişken kataloğu ve model dokümanı.", options: { fontSize: 12 } }],
    { x: 0.7, y: 5.2, w: 11.93, h: 1.15, align: "left", paraSpaceAfter: 3 });
}
s.addNotes("Bu adımlar henüz bu yapıya göre ele alınmadı; ilk sürümleri kodda duruyor. Anlatırken hedeflenen akış olarak sunun. " +
  "02.3'te yapay zekâ serbest kod değil, yalnız izinli işlemlerden oluşan bir formül yazar; formül kodla denetlenir. " +
  "05'te yeni değişkenlerin katkısı, aynı bölme ve aynı ayarlarla kurulan iki modelin karşılaştırılmasıyla ölçülür.");

// =====================================================================
// 12  NEREDE KALDIK
s = yeni("Akıllı Modelleme Platformu · Nerede Kaldık", B4,
  "01 ve 02.1 geliştirildi; şu an 02.2 Geleneksel Değişken Üretimi üzerinde çalışıyoruz.");
{
  kutu(0.5, 1.58, 12.33, 2.5, "gri", "akış bandı");
  const adim = [
    ["01", "Çalışma Kurulumu", "g"], ["02.1", "Veri Profili ve Kalite", "g"], ["02.2", "Geleneksel Değişken Üretimi", "s"],
    ["02.3", "AI Değişken Keşfi", "r"], ["03", "Veri Anlama ve Hazırlama", "r"], ["04", "Değişken Değerlendirme", "r"], ["05", "Modelleme ve Finalizasyon", "r"],
  ];
  const sl = 12.33 / 7, cy = 2.55;
  s.addShape(pres.shapes.LINE, { x: 0.5 + sl / 2, y: cy, w: sl * 6, h: 0, line: { color: SOLUK, width: 1.5, dashType: "dash" }, objectName: "akış çizgisi" });
  adim.forEach((a, i) => {
    const cx = 0.5 + sl * i + sl / 2, d = a[2] === "s" ? 0.95 : 0.8;
    const renk = a[2] === "g" ? { fill: { color: KIR }, line: { color: KIR, width: 1 } }
      : a[2] === "s" ? { fill: { color: BEJ }, line: { color: KIR, width: 3 } }
      : { fill: { color: "FFFFFF" }, line: { color: SOLUK, width: 1.5, dashType: "dash" } };
    s.addShape(pres.shapes.OVAL, Object.assign({ x: cx - d / 2, y: cy - d / 2, w: d, h: d, objectName: "adım " + a[0] }, renk));
    T(a[0], { x: cx - d / 2, y: cy - d / 2, w: d, h: d, fontSize: a[0].length > 2 ? 14 : 17, bold: true, margin: 0,
      color: a[2] === "g" ? "FFFFFF" : a[2] === "s" ? KIR : SOLUK });
    T(a[1], { x: cx - sl / 2 + 0.05, y: cy + 0.54, w: sl - 0.1, h: 0.55, fontSize: 12, bold: true, color: a[2] === "r" ? GRI : KOYU, valign: "top" });
    T(a[2] === "g" ? "Geliştirildi" : a[2] === "s" ? "Üzerinde çalışılıyor" : "Sırada",
      { x: cx - sl / 2 + 0.05, y: cy + 1.1, w: sl - 0.1, h: 0.28, fontSize: 10.5, bold: a[2] === "s", color: a[2] === "s" ? KIR : GRI });
    if (a[2] === "s") {
      kutu(cx - 0.85, 1.67, 1.7, 0.28, "veri", "şu an buradayız");
      T("Şu an buradayız", { x: cx - 0.85, y: 1.67, w: 1.7, h: 0.28, fontSize: 10.5, bold: true, color: "FFFFFF", margin: 0 });
    }
  });
  const kw = (12.33 - 0.5) / 3;
  kart(0.5, 4.32, kw, 2.0, "gri", "Geliştirilen", [
    "01 Çalışma Kurulumu: veri seti ve sözlük, kolon rolleri, eksik tanımlar, sözlük ve kolon adı kontrolü, bölme",
    "02.1 Veri Profili ve Kalite: 26 kontrol, düzeltme ve çözüm önerileri"], { baslikBoy: 14, boy: 11.5 });
  kart(0.5 + kw + 0.25, 4.32, kw, 2.0, "simdi", "Üzerinde çalışılan", [
    "02.2 Geleneksel Değişken Üretimi: yapay zekâ dönüşüm seçer, kod katkısını ölçer, kullanıcı kart ve sohbetle karar verir",
    "Açık konular: üretilen değişken sayısı ve yeni bilgi eşiği; kart ve sohbet geri bildirimle güncelleniyor"], { baslikBoy: 14, boy: 11.5 });
  kart(0.5 + 2 * (kw + 0.25), 4.32, kw, 2.0, "soluk", "Sırada", [
    "02.3 AI Değişken Keşfi",
    "03 Veri Anlama, 04 Değişken Değerlendirme, 05 Modelleme: ilk sürümleri kodda var, bu yapıya göre ele alınacak"], { baslikBoy: 14, boy: 11.5 });
}
s.addNotes("Kapanış slaytı. Akış beş fazdan oluşuyor; 01 ve 02.1 geliştirildi, şu an 02.2 üzerinde çalışıyoruz. " +
  "02.3 ve sonrasının ilk sürümleri kodda var ama bu yapıya göre henüz ele alınmadı.");

// ---------------------------------------------------------------- yaz ve kapak gorsel yer tutucusunu resim tipine cevir
(async () => {
  await pres.writeFile({ fileName: CIKTI });
  const zip = await JSZip.loadAsync(fs.readFileSync(CIKTI));
  // KAPAK yerlesimini bul: "Kapak görseli" istemini tasiyan yerlesim
  let yerlesim = null, idx = null;
  for (const ad of Object.keys(zip.files)) {
    if (!/^ppt\/slideLayouts\/slideLayout\d+\.xml$/.test(ad)) continue;
    const x = await zip.file(ad).async("string");
    if (x.includes("Kapak görseli")) {
      const m = x.match(/<p:sp>(?:(?!<\/p:sp>)[\s\S])*Kapak görseli[\s\S]*?<\/p:sp>/);
      const i = m && m[0].match(/idx="(\d+)"/);
      if (i) { yerlesim = ad; idx = i[1]; }
    }
  }
  if (!yerlesim) throw new Error("Kapak yerlesimi bulunamadi");
  const phDesen = new RegExp('<p:ph\\s+idx="' + idx + '"[^>]*/>');
  let lx = await zip.file(yerlesim).async("string");
  lx = lx.replace(phDesen, '<p:ph type="pic" idx="' + idx + '" hasCustomPrompt="1"/>');
  zip.file(yerlesim, lx);
  const sAd = "ppt/slides/slide1.xml";
  let sx = await zip.file(sAd).async("string");
  const spDesen = new RegExp('<p:sp>(?:(?!</p:sp>)[\\s\\S])*<p:ph\\s+idx="' + idx + '"[\\s\\S]*?</p:sp>');
  if (!spDesen.test(sx)) throw new Error("Kapak slaytinda yer tutucu bulunamadi");
  sx = sx.replace(spDesen, '<p:sp><p:nvSpPr><p:cNvPr id="9001" name="Kapak Görseli"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>' +
    '<p:nvPr><p:ph type="pic" idx="' + idx + '"/></p:nvPr></p:nvSpPr><p:spPr/></p:sp>');
  zip.file(sAd, sx);
  // klasor girdisi olmadan yeniden paketle (bulut servislerinde acilis sorunu cikarmasin)
  const temiz = new JSZip();
  for (const ad of Object.keys(zip.files)) {
    if (zip.files[ad].dir) continue;
    temiz.file(ad, await zip.file(ad).async("nodebuffer"), { createFolders: false });
  }
  fs.writeFileSync(CIKTI, await temiz.generateAsync({ type: "nodebuffer", compression: "DEFLATE" }));
  console.log("yazildi", CIKTI);
})().catch((e) => { console.error(e); process.exit(1); });
