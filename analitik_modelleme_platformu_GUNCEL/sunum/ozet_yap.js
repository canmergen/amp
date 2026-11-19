// Akilli Modelleme Platformu: tek slaytlik ozet (duzenlenebilir pptx)
const pptxgen = require("pptxgenjs");
const CIKTI = process.argv[2] || "ozet.pptx";

const KIR = "C8102E", KOYU = "262626", GRI = "595959", BEJ = "F6DDD0", YESIL = "2E7D4F", AMBER = "B26B00";
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5
pres.title = "Akıllı Modelleme Platformu";
pres.theme = { headFontFace: "Calibri", bodyFontFace: "Calibri" };
const s = pres.addSlide();
s.background = { color: "FFFFFF" };

const T = (metin, o) => s.addText(metin, Object.assign({ isTextBox: true, fontFace: "Calibri", fontSize: 11,
  color: KOYU, margin: 0.04, valign: "middle", align: "center" }, o));
const kutu = (x, y, w, h, tur, ad) => s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
  x, y, w, h, rectRadius: 0.1, objectName: ad,
  fill: { color: tur === "veri" ? KIR : tur === "onay" ? BEJ : "FFFFFF" },
  line: tur === "veri" ? { type: "none" } : { color: KIR, width: 1.5, dashType: tur === "sirada" ? "dash" : "solid" },
  shadow: tur === "veri" ? { type: "outer", color: "000000", opacity: 0.18, blur: 4, offset: 2, angle: 90 } : undefined,
});
const ok = (x1, y1, x2, y2, ad) => s.addShape(pres.shapes.LINE, {
  x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1) || 0.001, h: Math.abs(y2 - y1) || 0.001,
  line: { color: KIR, width: 1.25, endArrowType: "triangle" }, objectName: ad });

// Baslik ve cizgi
T("Akıllı Modelleme Platformu · Güncel Durum", { x: 0.5, y: 0.28, w: 8.3, h: 0.55, fontSize: 26, bold: true,
  color: KIR, align: "left", margin: 0 });
s.addShape(pres.shapes.LINE, { x: 0.5, y: 0.9, w: 12.33, h: 0, line: { color: KIR, width: 1 }, objectName: "başlık çizgisi" });

// Lejant
[["veri", "Veri / Çıktı"], ["islem", "İşlem (Python)"], ["onay", "İnsan Onayı"], ["sirada", "Sırada"]].forEach((l, i) => {
  const x = 9.15 + (i % 2) * 1.85, y = 0.25 + Math.floor(i / 2) * 0.32;
  kutu(x, y + 0.03, 0.42, 0.2, l[0], "lejant " + l[1]);
  T(l[1], { x: x + 0.5, y, w: 1.3, h: 0.26, fontSize: 10, color: GRI, align: "left", margin: 0 });
});

// Ne yapar
T("Ne yapar", { x: 0.5, y: 1.08, w: 1.4, h: 0.55, fontSize: 15, italic: true, color: KIR, align: "left", margin: 0 });
kutu(1.85, 1.08, 10.98, 0.55, "islem", "ne yapar");
T("Ham veriden final modele kadar model geliştirmeyi Dataiku içinde tek akışta yürütür: yapay zekâ önerir, siz onaylarsınız, kod hesaplar.",
  { x: 1.95, y: 1.08, w: 10.78, h: 0.55, fontSize: 13 });

// Yapay zeka bandi
const PX = 2.35, PW = 1.85, PG = (12.83 - PX - 5 * PW) / 4;
kutu(PX, 1.82, 12.83 - PX, 0.42, "islem", "yapay zeka bandı");
T([{ text: "Yapay Zekâ ve Sohbet  ", options: { bold: true, color: KIR } },
  { text: "her adımda öneriyi gerekçesiyle sunar, sorularınızı yanıtlar", options: { color: KOYU } }],
  { x: PX, y: 1.82, w: 12.83 - PX, h: 0.42, fontSize: 11.5 });

// Girdi
kutu(0.5, 2.85, 1.5, 1.35, "veri", "girdi");
T([{ text: "Girdi", options: { bold: true, fontSize: 12, breakLine: true } },
  { text: "Veri seti ve sözlük", options: { fontSize: 11, breakLine: true } },
  { text: "hiç değişmez", options: { fontSize: 10, italic: true } }],
  { x: 0.5, y: 2.85, w: 1.5, h: 1.35, color: "FFFFFF" });
ok(2.0, 3.52, PX - 0.02, 3.52, "ok girdi");

// Fazlar
const fazlar = [
  ["01 Çalışma Kurulumu", "Veri ve sözlük seçilir, kolon adları ve tanımlar onaylanır, veri bölünür", "UPDT Veri ve Sözlük", true],
  ["02 Değişken Mühendisliği", "25 kalite kontrolü; kural tabanlı ve yapay zekâ ile yeni değişkenler", "Yeni Değişkenler", true],
  ["03 Veri Anlama", "Hedefle ilişki ve zamanda kararlılık ölçülür, set sabitlenir", "Analitik Baz Set", true],
  ["04 Değişken Değerlendirme", "Sızıntı ayıklanır, katkısız değişkenler elenir", "Aday Değişken Seti", false],
  ["05 Modelleme", "Baz ve zengin model, dört algoritma, final model", "Final Model ve Doküman", false],
];
fazlar.forEach((f, i) => {
  const x = PX + i * (PW + PG);
  // onay noktasi
  ok(x + PW / 2, 2.24, x + PW / 2, 2.36, "ok bant " + i);
  kutu(x + PW / 2 - 0.42, 2.37, 0.84, 0.26, "onay", "onay " + f[0]);
  T("onay", { x: x + PW / 2 - 0.42, y: 2.37, w: 0.84, h: 0.26, fontSize: 10, bold: true, color: KIR, margin: 0 });
  ok(x + PW / 2, 2.63, x + PW / 2, 2.83, "ok onay " + i);
  // islem
  kutu(x, 2.85, PW, 1.35, "islem", "faz " + f[0]);
  T([{ text: f[0], options: { bold: true, color: KIR, fontSize: 12, breakLine: true } },
    { text: f[1], options: { fontSize: 10, color: KOYU } }], { x: x + 0.05, y: 2.88, w: PW - 0.1, h: 1.29, paraSpaceAfter: 3 });
  if (i < 4) ok(x + PW + 0.02, 3.52, x + PW + PG - 0.02, 3.52, "ok faz " + i);
  // cikti
  ok(x + PW / 2, 4.2, x + PW / 2, 4.33, "ok çıktı " + i);
  kutu(x, 4.35, PW, 0.5, "veri", "çıktı " + f[2]);
  T(f[2], { x, y: 4.35, w: PW, h: 0.5, fontSize: 11, bold: true, color: "FFFFFF" });
  // durum
  T([{ text: "● ", options: { color: f[3] ? YESIL : AMBER } }, { text: f[3] ? "Yeni düzende çalışıyor" : "Eski düzende çalışıyor" }],
    { x, y: 4.92, w: PW, h: 0.26, fontSize: 9.5, color: GRI, margin: 0 });
});

// Proje hafizasi
kutu(PX, 5.3, 12.83 - PX, 0.42, "veri", "proje hafızası");
T([{ text: "Proje Hafızası  ", options: { bold: true } },
  { text: "onaylı tanımlar, ad parçaları ve kararlar burada; aynı şey iki kez sorulmaz" }],
  { x: PX, y: 5.3, w: 12.83 - PX, h: 0.42, fontSize: 11.5, color: "FFFFFF" });

// Alt uc kutu
const alt = [
  ["islem", "Nereye gelindi", ["Beş fazın hepsi akışta çalışıyor", "01, 02 ve 03 yeni veri düzeninde", "Değişken üretimi katkı ölçümüyle yenilendi"]],
  ["sirada", "Sırada", ["04 ve 05'in yeni veri düzenine taşınması", "Model Sohbeti ve Otomatik Pilot"]],
  ["onay", "Sonunda", ["Kod yazmadan, onaylarla: final model, değişken kataloğu ve Word model dokümanı", "Aynı akış her veri seti ve hedefte"]],
];
const AW = (12.33 - 2 * 0.25) / 3;
alt.forEach((a, i) => {
  const x = 0.5 + i * (AW + 0.25);
  kutu(x, 5.92, AW, 1.0, a[0], "alt " + a[1]);
  T(a[1], { x: x + 0.15, y: 5.97, w: AW - 0.3, h: 0.28, fontSize: 12.5, bold: true, color: KIR, align: "left", margin: 0 });
  T(a[2].map((m, j) => ({ text: m, options: { bullet: { indent: 10 }, breakLine: j < a[2].length - 1 } })),
    { x: x + 0.15, y: 6.26, w: AW - 0.3, h: 0.62, fontSize: 10.5, align: "left", valign: "top", margin: 0 });
});

T("Yapay zekâ yalnız önerir; kararı siz verirsiniz, hesaplamayı ve kaydı kod yapar. Girdi veriye hiçbir şey yazılmaz.",
  { x: 0.5, y: 7.0, w: 12.33, h: 0.3, fontSize: 10, italic: true, color: GRI, align: "left", margin: 0 });

s.addNotes("Ne yapar: veri seti ve sözlükten final modele kadar beş faz. Her fazın başında yapay zekâ önerir, onay noktasında siz karar verirsiniz, " +
  "kod tam veride hesaplar. Kırmızı kutular her fazın çıktısıdır. Nereye gelindi: 01, 02 ve 03 platformun kendi kopyalarıyla (BAZ ve UPDT) çalışıyor; " +
  "04 ve 05 çalışıyor ama önceki veri düzeniyle okuyor. Sonunda: kod yazmadan final model, değişken kataloğu ve 20 bölümlü model dokümanı.");

pres.writeFile({ fileName: CIKTI }).then(() => console.log("yazildi", CIKTI));
