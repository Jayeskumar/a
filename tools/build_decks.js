// Builds one pitch deck (.pptx) per project from projects/*/pitch.json.
//
//   cd tools && npm install && node build_decks.js            # every project -> ../decks/
//   node build_decks.js ../projects/03-pulseguard/pitch.json  # just one
//   node build_decks.js --out /some/dir path/to/pitch.json
//
// Team details shown on the title and closing slides come from ../team.json (optional):
//   { "team": "Team Name", "members": ["A", "B"], "github": "https://github.com/...", "branch": "main" }
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const sharp = require("sharp");
const fa = require("react-icons/fa");
const { applyTheme } = require("./lib/apply_theme.js");

const ROOT = path.resolve(__dirname, "..");
const W = 13.333;
const H = 7.5;
const M = 0.6; // outer margin

// ---------- colour helpers ----------
const hex = (c) => c.replace("#", "").toUpperCase();
function mix(a, b, t) {
  const pa = [0, 2, 4].map((i) => parseInt(a.slice(i, i + 2), 16));
  const pb = [0, 2, 4].map((i) => parseInt(b.slice(i, i + 2), 16));
  return pa.map((v, i) => Math.round(v + (pb[i] - v) * t).toString(16).padStart(2, "0")).join("").toUpperCase();
}

const INK = "141B34";
const NAVY = "0B1026";
const SURFACE = "F3F4F8";
const MUTED = "5B6478";

function makeTheme(name, brand) {
  return {
    name: `${name} QUANTIX`,
    headFontFace: "Calibri",
    bodyFontFace: "Calibri",
    colors: {
      dk1: INK,
      lt1: "FFFFFF",
      dk2: NAVY,
      lt2: SURFACE,
      accent1: brand, // brand
      accent2: mix(brand, "FFFFFF", 0.88), // brand tint for cards on light slides
      accent3: mix(brand, "000000", 0.35), // brand shade, readable on white
      accent4: MUTED, // captions
      accent5: mix(NAVY, brand, 0.22), // card fill on dark slides
      accent6: mix(brand, "FFFFFF", 0.45), // brand tint, readable on navy
      hlink: mix(brand, "000000", 0.2),
      folHlink: MUTED,
    },
  };
}

// ---------- icons ----------
async function iconPng(Icon, color, size = 256) {
  const svg = renderToStaticMarkup(React.createElement(Icon, { color: "#" + color, size: String(size) }));
  const buf = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}

const FEATURE_ICONS = [fa.FaBolt, fa.FaBrain, fa.FaChartLine, fa.FaShieldAlt, fa.FaMobileAlt, fa.FaCogs];
const INNOVATION_ICONS = [fa.FaLightbulb, fa.FaRocket, fa.FaStar, fa.FaGem];

const shadow = () => ({ type: "outer", color: "000000", opacity: 0.14, blur: 8, offset: 2, angle: 90 });

// "Component -> what it does" or "Algorithm – purpose" → [head, tail]
function splitPair(s) {
  const m = String(s).split(/\s*(?:->|→|–|—|:)\s*|\s+-\s+/);
  if (m.length < 2) return [String(s), ""];
  return [m[0], m.slice(1).join(" – ")];
}

function loadTeam() {
  const p = path.join(ROOT, "team.json");
  const team = { team: "Your Team Name", members: [], github: "github.com/<your-team>/<repo>", branch: "main" };
  if (fs.existsSync(p)) Object.assign(team, JSON.parse(fs.readFileSync(p, "utf8")));
  return team;
}

// ---------- deck ----------
async function buildDeck(pitchPath, outDir, team) {
  const pitch = JSON.parse(fs.readFileSync(pitchPath, "utf8"));
  const projDir = path.dirname(pitchPath);
  const brand = hex(pitch.color || "#6C4CF1");
  const THEME = makeTheme(pitch.name, brand);
  const T = THEME.colors;

  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE";
  pres.title = `${pitch.name} – ${pitch.tagline}`;
  pres.subject = `QUANTIX 2K26 · ${pitch.domain}`;
  pres.author = team.team;
  pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
  const C = pres.SchemeColor;

  const footer = `QUANTIX 2K26 · ${pitch.name}`;
  pres.defineSlideMaster({
    title: "Dark",
    background: { color: C.text2 },
    objects: [],
  });
  pres.defineSlideMaster({
    title: "Content",
    background: { color: C.background1 },
    margin: [0.4, M, 0.6, M],
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: M, y: 0.35, w: W - 2 * M, h: 0.85, fontSize: 36, bold: true, color: C.text1, align: "left", valign: "middle", margin: 0 }, text: "" } },
      { text: { text: footer, options: { x: M, y: H - 0.5, w: 6, h: 0.3, fontSize: 10, color: C.accent4, margin: 0 } } },
    ],
    slideNumber: { x: W - M - 0.6, y: H - 0.5, w: 0.6, h: 0.3, fontSize: 10, color: C.accent4, align: "right" },
  });

  const shotPath = path.join(projDir, "docs", "screenshot.png");
  const hasShot = fs.existsSync(shotPath);
  function screenshot(slide, x, y, w, name) {
    const h = w / 1.6;
    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: x - 0.06, y: y - 0.06, w: w + 0.12, h: h + 0.12, rectRadius: 0.08, fill: { color: C.background1 }, line: { color: C.background2, width: 1 }, shadow: shadow(), objectName: name + " frame" });
    if (hasShot) {
      slide.addImage({ path: shotPath, x, y, w, h, objectName: name, altText: `${pitch.name} screenshot` });
    } else {
      slide.addText("Screenshot: run the app and capture docs/screenshot.png", { x, y, w, h, align: "center", valign: "middle", fontSize: 14, color: C.accent4, fill: { color: C.background2 }, isTextBox: true, objectName: name });
    }
    return h;
  }
  function bullets(items) {
    return items.map((t, i) => ({ text: t, options: { bullet: { indent: 18 }, breakLine: i < items.length - 1, paraSpaceAfter: 10 } }));
  }

  const icons = {
    problem: await iconPng(fa.FaExclamationTriangle, "FFFFFF"),
    solution: await iconPng(fa.FaLightbulb, "FFFFFF"),
    features: await Promise.all(FEATURE_ICONS.map((I) => iconPng(I, "FFFFFF"))),
    innovation: await Promise.all(INNOVATION_ICONS.map((I) => iconPng(I, "FFFFFF"))),
    impact: await iconPng(fa.FaGlobeAsia, "FFFFFF"),
    business: await iconPng(fa.FaRupeeSign, "FFFFFF"),
    check: await iconPng(fa.FaCheck, "FFFFFF"),
  };
  function iconCircle(slide, img, x, y, d, name) {
    slide.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: C.accent1 }, line: { type: "none" }, objectName: name + " circle" });
    const p = d * 0.25;
    slide.addImage({ data: img, x: x + p, y: y + p, w: d - 2 * p, h: d - 2 * p, objectName: name + " icon" });
  }

  // 1. Title
  pres.addSection({ title: "Introduction" });
  let s = pres.addSlide({ masterName: "Dark", sectionTitle: "Introduction" });
  s.addText(pitch.domain.toUpperCase(), { x: M, y: 1.2, w: 6.2, h: 0.4, fontSize: 12, bold: true, charSpacing: 2, color: C.accent6, margin: 0, isTextBox: true, objectName: "Domain" });
  s.addText(pitch.name, { x: M, y: 1.7, w: 6.4, h: 1.3, fontSize: 60, bold: true, color: C.background1, margin: 0, fontFace: THEME.headFontFace, isTextBox: true, objectName: "Product name" });
  s.addText(pitch.tagline, { x: M, y: 3.05, w: 6.0, h: 1.1, fontSize: 22, color: C.background1, margin: 0, valign: "top", isTextBox: true, objectName: "Tagline" });
  const teamLine = team.members && team.members.length ? `${team.team} · ${team.members.join(", ")}` : team.team;
  s.addText([
    { text: teamLine, options: { breakLine: true, bold: true } },
    { text: "QUANTIX 2K26 · 24-hour hackathon · K.S.R. College of Engineering" },
  ], { x: M, y: 5.6, w: 6.2, h: 0.8, fontSize: 14, color: C.accent6, margin: 0, valign: "bottom", isTextBox: true, objectName: "Team" });
  screenshot(s, 7.3, 1.9, 5.4, "Hero screenshot");
  s.addNotes(`Open with the one-line promise: ${pitch.tagline}. Introduce the team, then go straight to the problem.`);

  // 2. Problem
  pres.addSection({ title: "Problem & solution" });
  s = pres.addSlide({ masterName: "Content", sectionTitle: "Problem & solution" });
  s.addText("The problem", { placeholder: "title" });
  iconCircle(s, icons.problem, M, 1.45 + 2.1, 0.6, "Problem");
  s.addText(bullets(pitch.problem), { x: M + 0.85, y: 1.45, w: 6.4, h: 4.8, fontSize: 20, color: C.text1, valign: "middle", margin: 0, isTextBox: true, objectName: "Problem bullets" });
  const stats = (pitch.stats || []).slice(0, 3);
  const statH = 1.55;
  const statGap = 0.3;
  const statTop = 1.45 + (4.8 - (stats.length * statH + (stats.length - 1) * statGap)) / 2;
  stats.forEach((st, i) => {
    const y = statTop + i * (statH + statGap);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 8.3, y, w: 4.4, h: statH, rectRadius: 0.12, fill: { color: C.accent2 }, line: { type: "none" }, objectName: `Stat ${i + 1} card` });
    s.addText(st.value, { x: 8.55, y: y + 0.12, w: 3.9, h: 0.8, fontSize: 40, bold: true, color: C.accent3, margin: 0, valign: "middle", isTextBox: true, objectName: `Stat ${i + 1} value` });
    s.addText(st.label, { x: 8.55, y: y + 0.92, w: 3.9, h: 0.55, fontSize: 13, color: C.text1, margin: 0, valign: "top", isTextBox: true, objectName: `Stat ${i + 1} label` });
  });
  s.addNotes("Problem: " + pitch.problem.join(" ") + (stats.length ? " Key numbers: " + stats.map((x) => `${x.value} ${x.label}`).join("; ") + "." : ""));

  // 3. Solution
  s = pres.addSlide({ masterName: "Content", sectionTitle: "Problem & solution" });
  s.addText(`Our solution: ${pitch.name}`, { placeholder: "title" });
  iconCircle(s, icons.solution, M, 1.45 + 2.1, 0.6, "Solution");
  s.addText(bullets(pitch.solution), { x: M + 0.85, y: 1.45, w: 5.2, h: 4.8, fontSize: 20, color: C.text1, valign: "middle", margin: 0, isTextBox: true, objectName: "Solution bullets" });
  screenshot(s, 7.05, 1.75, 5.65, "Solution screenshot");
  s.addNotes("Solution: " + pitch.solution.join(" "));

  // 4. Features grid
  pres.addSection({ title: "Product" });
  s = pres.addSlide({ masterName: "Content", sectionTitle: "Product" });
  s.addText("Key features", { placeholder: "title" });
  const feats = (pitch.features || []).slice(0, 6);
  const cols = feats.length <= 4 ? 2 : 3;
  const rows = Math.ceil(feats.length / cols);
  const gap = 0.3;
  const cw = (W - 2 * M - (cols - 1) * gap) / cols;
  const ch = Math.min(2.4, (5.2 - (rows - 1) * gap) / rows);
  feats.forEach((f, i) => {
    const x = M + (i % cols) * (cw + gap);
    const y = 1.5 + Math.floor(i / cols) * (ch + gap);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: cw, h: ch, rectRadius: 0.12, fill: { color: C.background2 }, line: { type: "none" }, objectName: `Feature ${i + 1} card` });
    iconCircle(s, icons.features[i % icons.features.length], x + 0.3, y + 0.3, 0.6, `Feature ${i + 1}`);
    s.addText(f.title, { x: x + 1.1, y: y + 0.3, w: cw - 1.35, h: 0.6, fontSize: 18, bold: true, color: C.text1, valign: "middle", margin: 0, isTextBox: true, objectName: `Feature ${i + 1} title` });
    s.addText(f.desc, { x: x + 0.3, y: y + 1.05, w: cw - 0.6, h: ch - 1.25, fontSize: 14, color: C.accent4, valign: "top", margin: 0, isTextBox: true, objectName: `Feature ${i + 1} text` });
  });
  s.addNotes("Features: " + feats.map((f) => `${f.title}: ${f.desc}`).join(". "));

  // 5. Architecture (stacked layers)
  s = pres.addSlide({ masterName: "Content", sectionTitle: "Product" });
  s.addText("System architecture", { placeholder: "title" });
  const layers = (pitch.architecture || []).slice(0, 6);
  const lgap = 0.22;
  const lh = Math.min(0.85, (5.25 - (layers.length - 1) * lgap) / layers.length);
  layers.forEach((l, i) => {
    const [head, tail] = splitPair(l);
    const y = 1.45 + i * (lh + lgap);
    const fill = i % 2 === 0 ? C.accent2 : C.background2;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: M, y, w: 8.2, h: lh, rectRadius: 0.1, fill: { color: fill }, line: { type: "none" }, objectName: `Layer ${i + 1}` });
    s.addText([
      { text: head, options: { bold: true, color: C.accent3 } },
      { text: tail ? "   " + tail : "", options: { color: C.text1 } },
    ], { x: M + 0.3, y, w: 7.7, h: lh, fontSize: 15, valign: "middle", margin: 0, isTextBox: true, objectName: `Layer ${i + 1} text` });
    if (i < layers.length - 1) {
      s.addShape(pres.shapes.DOWN_ARROW, { x: M + 4.0, y: y + lh + 0.02, w: 0.22, h: lgap - 0.04, fill: { color: C.accent4 }, line: { type: "none" }, objectName: `Arrow ${i + 1}` });
    }
  });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 9.2, y: 1.45, w: W - M - 9.2, h: 5.25, rectRadius: 0.12, fill: { color: C.text2 }, line: { type: "none" }, objectName: "Tech card" });
  s.addText("Tech stack", { x: 9.5, y: 1.7, w: 3.0, h: 0.5, fontSize: 18, bold: true, color: C.background1, margin: 0, isTextBox: true, objectName: "Tech title" });
  s.addText(bullets(pitch.tech || []), { x: 9.5, y: 2.3, w: 3.0, h: 3.0, fontSize: 14, color: C.background1, valign: "top", margin: 0, isTextBox: true, objectName: "Tech list" });
  s.addText("Runs fully offline · no installs · python app.py", { x: 9.5, y: 5.6, w: 3.0, h: 0.85, fontSize: 13, italic: true, color: C.accent6, valign: "bottom", margin: 0, isTextBox: true, objectName: "Offline note" });
  s.addNotes("Architecture top to bottom: " + layers.join(". ") + ". Stack: " + (pitch.tech || []).join(", ") + ".");

  // 6. Algorithms
  s = pres.addSlide({ masterName: "Content", sectionTitle: "Product" });
  s.addText("Algorithms built from scratch", { placeholder: "title" });
  const algos = (pitch.algorithms || []).slice(0, 6);
  const acols = algos.length > 3 ? 2 : 1;
  const arows = Math.ceil(algos.length / acols);
  const aw = (W - 2 * M - (acols - 1) * 0.3) / acols;
  const ah = Math.min(2.0, (5.2 - (arows - 1) * 0.25) / arows);
  algos.forEach((a, i) => {
    const [head, tail] = splitPair(a);
    const x = M + (i % acols) * (aw + 0.3);
    const y = 1.5 + Math.floor(i / acols) * (ah + 0.25);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: aw, h: ah, rectRadius: 0.1, fill: { color: C.background2 }, line: { type: "none" }, objectName: `Algorithm ${i + 1} card` });
    s.addText(String(i + 1).padStart(2, "0"), { x: x + 0.25, y, w: 0.8, h: ah, fontSize: 28, bold: true, color: C.accent1, valign: "middle", margin: 0, isTextBox: true, objectName: `Algorithm ${i + 1} number` });
    s.addText([
      { text: head, options: { bold: true, fontSize: 17, color: C.text1, breakLine: !!tail } },
      { text: tail, options: { fontSize: 14, color: C.accent4 } },
    ], { x: x + 1.1, y, w: aw - 1.3, h: ah, valign: "middle", margin: 0, isTextBox: true, objectName: `Algorithm ${i + 1} text` });
  });
  s.addNotes("Algorithms: " + algos.join(". ") + ". Stress that nothing is a black box: every decision can be explained on screen.");

  // 7. Innovation
  pres.addSection({ title: "Why us" });
  s = pres.addSlide({ masterName: "Content", sectionTitle: "Why us" });
  s.addText("What makes it different", { placeholder: "title" });
  const inn = (pitch.innovation || []).slice(0, 4);
  // 4 items -> 2x2 grid; up to 3 -> full-width rows
  const icols = inn.length === 4 ? 2 : 1;
  const irows = Math.ceil(inn.length / icols);
  const iw = (W - 2 * M - (icols - 1) * 0.3) / icols;
  const ih = Math.min(2.35, (5.2 - (irows - 1) * 0.3) / irows);
  inn.forEach((t, i) => {
    const x = M + (i % icols) * (iw + 0.3);
    const y = 1.5 + Math.floor(i / icols) * (ih + 0.3);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: iw, h: ih, rectRadius: 0.12, fill: { color: i % 3 === 0 ? C.accent2 : C.background2 }, line: { type: "none" }, objectName: `Innovation ${i + 1} card` });
    iconCircle(s, icons.innovation[i], x + 0.35, y + (ih - 0.75) / 2, 0.75, `Innovation ${i + 1}`);
    s.addText(t, { x: x + 1.35, y, w: iw - 1.65, h: ih, fontSize: 20, color: C.text1, valign: "middle", margin: 0, isTextBox: true, objectName: `Innovation ${i + 1} text` });
  });
  s.addNotes("Differentiators: " + inn.join(" "));

  // 8. Results
  s = pres.addSlide({ masterName: "Content", sectionTitle: "Why us" });
  s.addText("Measured results", { placeholder: "title" });
  const res = (pitch.results || []).slice(0, 4);
  const rw = (W - 2 * M - (res.length - 1) * 0.3) / Math.max(res.length, 1);
  res.forEach((r, i) => {
    const x = M + i * (rw + 0.3);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.6, w: rw, h: 2.6, rectRadius: 0.12, fill: { color: C.text2 }, line: { type: "none" }, shadow: shadow(), objectName: `Result ${i + 1} card` });
    const base = res.length > 3 ? 40 : 48;
    const len = String(r.value).length;
    const valueSize = len <= 6 ? base : len <= 9 ? Math.round(base * 0.75) : Math.round(base * 0.6);
    s.addText(r.value, { x: x + 0.25, y: 1.8, w: rw - 0.5, h: 1.2, fontSize: valueSize, bold: true, color: C.accent6, align: "center", valign: "middle", margin: 0, fit: "shrink", isTextBox: true, objectName: `Result ${i + 1} value` });
    s.addText(r.label, { x: x + 0.25, y: 3.0, w: rw - 0.5, h: 1.0, fontSize: 14, color: C.background1, align: "center", valign: "top", margin: 0, isTextBox: true, objectName: `Result ${i + 1} label` });
  });
  s.addText("Measured on held-out data generated by the project (see REPORT.md for method). Real-world performance needs field validation.", { x: M, y: 4.55, w: W - 2 * M, h: 0.5, fontSize: 12, italic: true, color: C.accent4, margin: 0, isTextBox: true, objectName: "Results caveat" });
  const imp = (pitch.impact || []).slice(0, 3);
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: M, y: 5.2, w: W - 2 * M, h: 1.5, rectRadius: 0.12, fill: { color: C.accent2 }, line: { type: "none" }, objectName: "Impact strip" });
  iconCircle(s, icons.impact, M + 0.3, 5.6, 0.7, "Impact");
  s.addText([{ text: "Impact  ", options: { bold: true, color: C.accent3 } }, { text: imp.join("  ·  "), options: { color: C.text1 } }], { x: M + 1.3, y: 5.2, w: W - 2 * M - 1.6, h: 1.5, fontSize: 15, valign: "middle", margin: 0, isTextBox: true, objectName: "Impact text" });
  s.addNotes("Results: " + res.map((r) => `${r.value} ${r.label}`).join("; ") + ". Impact: " + imp.join(" "));

  // 9. Live demo flow
  pres.addSection({ title: "Demo" });
  s = pres.addSlide({ masterName: "Content", sectionTitle: "Demo" });
  s.addText("Live demo in 3 minutes", { placeholder: "title" });
  const steps = (pitch.demo_flow || []).slice(0, 7);
  const sh = Math.min(0.72, (5.2 - (steps.length - 1) * 0.12) / steps.length);
  steps.forEach((t, i) => {
    const y = 1.5 + i * (sh + 0.12);
    s.addShape(pres.shapes.OVAL, { x: M, y: y + (sh - 0.5) / 2, w: 0.5, h: 0.5, fill: { color: C.accent1 }, line: { type: "none" }, objectName: `Step ${i + 1} dot` });
    s.addText(String(i + 1), { x: M, y: y + (sh - 0.5) / 2, w: 0.5, h: 0.5, fontSize: 16, bold: true, color: C.background1, align: "center", valign: "middle", margin: 0, isTextBox: true, objectName: `Step ${i + 1} number` });
    s.addText(t, { x: M + 0.75, y, w: 5.6, h: sh, fontSize: 16, color: C.text1, valign: "middle", margin: 0, isTextBox: true, objectName: `Step ${i + 1} text` });
  });
  screenshot(s, 7.2, 1.75, 5.5, "Demo screenshot");
  s.addText(`python app.py  →  http://localhost:${pitch.port}`, { x: 7.2, y: 5.4 + 0.1, w: 5.5, h: 0.5, fontSize: 14, fontFace: "Courier New", color: C.accent3, align: "center", margin: 0, isTextBox: true, objectName: "Run command" });
  s.addNotes("Switch to the browser now. " + steps.map((t, i) => `${i + 1}. ${t}`).join(" "));

  // 10. Business & scale
  pres.addSection({ title: "Roadmap" });
  s = pres.addSlide({ masterName: "Content", sectionTitle: "Roadmap" });
  s.addText("Feasibility, business model & roadmap", { placeholder: "title" });
  const colW = (W - 2 * M - 0.3) / 2;
  const roadmap = [["Business model", icons.business, (pitch.business || []).slice(0, 5)], ["Future scope", icons.solution, (pitch.future || []).slice(0, 5)]];
  const cardH = Math.min(5.2, 1.6 + 0.62 * Math.max(...roadmap.map((r) => r[2].length)));
  roadmap.forEach(([title, img, items], i) => {
    const x = M + i * (colW + 0.3);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.5, w: colW, h: cardH, rectRadius: 0.12, fill: { color: i === 0 ? C.background2 : C.accent2 }, line: { type: "none" }, objectName: `${title} card` });
    iconCircle(s, img, x + 0.35, 1.8, 0.6, title);
    s.addText(title, { x: x + 1.15, y: 1.8, w: colW - 1.5, h: 0.6, fontSize: 20, bold: true, color: C.text1, valign: "middle", margin: 0, isTextBox: true, objectName: `${title} title` });
    s.addText(bullets(items), { x: x + 0.4, y: 2.7, w: colW - 0.8, h: cardH - 1.4, fontSize: 16, color: C.text1, valign: "top", margin: 0, isTextBox: true, objectName: `${title} list` });
  });
  s.addNotes("Business: " + (pitch.business || []).join(" ") + " Next: " + (pitch.future || []).join(" "));

  // 11. Thank you
  s = pres.addSlide({ masterName: "Dark", sectionTitle: "Roadmap" });
  s.addText("Thank you", { x: M, y: 1.6, w: 7, h: 1.2, fontSize: 60, bold: true, color: C.background1, margin: 0, isTextBox: true, objectName: "Thanks" });
  s.addText(`${pitch.name} · ${pitch.tagline}`, { x: M, y: 2.9, w: 7, h: 0.9, fontSize: 20, color: C.accent6, margin: 0, valign: "top", isTextBox: true, objectName: "Thanks tagline" });
  s.addText([
    { text: "Code  ", options: { bold: true, color: C.accent6 } },
    { text: `${team.github}/tree/${team.branch}/${pitch.dir}`, options: { color: C.background1, breakLine: true } },
    { text: "Run  ", options: { bold: true, color: C.accent6 } },
    { text: `cd ${pitch.dir} && python app.py`, options: { color: C.background1, fontFace: "Courier New" } },
  ], { x: M, y: 4.3, w: 11.5, h: 1.0, fontSize: 15, margin: 0, valign: "top", paraSpaceAfter: 8, isTextBox: true, objectName: "Links" });
  s.addText("Questions?", { x: M, y: 5.8, w: 6, h: 0.7, fontSize: 26, bold: true, color: C.accent6, margin: 0, isTextBox: true, objectName: "Questions" });
  s.addNotes("Close with the impact line, invite questions. Keep the demo tab open in case judges want to try it.");

  fs.mkdirSync(outDir, { recursive: true });
  const outFile = path.join(outDir, `${path.basename(projDir)}.pptx`);
  await pres.writeFile({ fileName: outFile });
  await applyTheme(outFile, THEME);
  return outFile;
}

(async () => {
  const args = process.argv.slice(2);
  let outDir = path.join(ROOT, "decks");
  const oi = args.indexOf("--out");
  if (oi >= 0) {
    outDir = path.resolve(args[oi + 1]);
    args.splice(oi, 2);
  }
  let files = args.map((a) => path.resolve(a));
  if (!files.length) {
    const pdir = path.join(ROOT, "projects");
    files = fs.readdirSync(pdir).sort().map((d) => path.join(pdir, d, "pitch.json")).filter((f) => fs.existsSync(f));
  }
  const team = loadTeam();
  for (const f of files) console.log("built", await buildDeck(f, outDir, team));
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
