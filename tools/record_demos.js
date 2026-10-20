// Record a captioned walkthrough video of every running demo (start them with `python run_all.py`).
//
//   NODE_PATH="$(npm root -g)" node tools/record_demos.js [outDir] [port ...]
//
// Each video (~45 s, 1280x720) shows a title card, clicks the demo button, tours every tab
// with a caption bar and slow scrolling, and ends on a card with the measured results.
// Output: <outDir>/<NN-name>.mp4 (H.264 via ffmpeg) ready to upload as the hackathon "demo link".
// Run it on a scratch copy of the repo: the demos write their own state files as they run.
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..');
const SIZE = { width: 1280, height: 720 };
const TAB_SELECTOR = [
  '[role="tab"]', 'nav button', 'nav a[href^="#"]', '.tabs button', '.tab', '.tabs a',
  'button[data-tab]', 'a[data-tab]', '[data-view]', 'header nav a',
].join(',');
const DEMO_RE = /^(▶\s*)?(run demo|load demo|load demo data|load demo notes|load demo farm|demo)$/i;
const MAX_TABS = 6;

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function projects() {
  return fs.readdirSync(path.join(ROOT, 'projects')).sort()
    .map((d) => path.join(ROOT, 'projects', d, 'pitch.json'))
    .filter((f) => fs.existsSync(f))
    .map((f) => ({ ...JSON.parse(fs.readFileSync(f, 'utf8')), dir: path.basename(path.dirname(f)) }));
}

async function card(page, html, color, ms) {
  await page.evaluate(({ html, color }) => {
    const d = document.createElement('div');
    d.id = '__demo_card';
    d.style.cssText = `position:fixed;inset:0;z-index:2147483647;background:#0b1026;color:#fff;display:flex;
      flex-direction:column;justify-content:center;padding:0 110px;font-family:Arial,Helvetica,sans-serif;
      border-left:0;box-sizing:border-box;opacity:0;transition:opacity .4s`;
    d.innerHTML = `<div style="width:64px;height:6px;border-radius:3px;background:${color};margin-bottom:26px"></div>` + html;
    document.body.appendChild(d);
    requestAnimationFrame(() => { d.style.opacity = '1'; });
  }, { html, color });
  await page.waitForTimeout(ms);
  await page.evaluate(() => { const d = document.getElementById('__demo_card'); if (d) d.remove(); });
}

async function caption(page, text, color) {
  await page.evaluate(({ text, color }) => {
    let c = document.getElementById('__demo_caption');
    if (!c) {
      c = document.createElement('div');
      c.id = '__demo_caption';
      c.style.cssText = `position:fixed;left:50%;bottom:22px;transform:translateX(-50%);z-index:2147483646;
        background:rgba(11,16,38,.88);color:#fff;font:600 19px/1.35 Arial,Helvetica,sans-serif;padding:11px 22px;
        border-radius:12px;max-width:80%;text-align:center;box-shadow:0 6px 24px rgba(0,0,0,.25);pointer-events:none`;
      document.body.appendChild(c);
    }
    c.style.borderBottom = `4px solid ${color}`;
    c.textContent = text;
  }, { text, color });
}

async function tour(page, steps = 4) {
  // scroll the page (or the biggest scrollable panel) down in a few slow steps, then back up
  for (let i = 0; i < steps; i++) {
    const moved = await page.evaluate(() => {
      const before = window.scrollY;
      window.scrollBy({ top: Math.round(window.innerHeight * 0.55), behavior: 'smooth' });
      return before + window.innerHeight < document.documentElement.scrollHeight - 4;
    });
    await page.waitForTimeout(1100);
    if (!moved) break;
  }
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' }));
  await page.waitForTimeout(700);
}

const STOP = new Set(['the', 'and', 'for', 'with', 'your', 'you', 'from', 'into', 'per', 'all', 'how', 'what', 'tab']);
const words = (s) => new Set(String(s).toLowerCase().replace(/[^a-z0-9\s]/g, ' ').split(/\s+/)
  .filter((w) => w.length > 2 && !STOP.has(w)).map((w) => w.replace(/(ing|es|s)$/, '')));

// Pick the feature whose title/description shares the most words with the tab label; none if no overlap.
function matchFeature(tab, features, used) {
  const t = words(tab);
  let best = null, bestScore = 0;
  features.forEach((f, i) => {
    if (used.has(i)) return;
    const fw = words(f.title + ' ' + f.desc);
    const score = [...t].filter((w) => fw.has(w)).length + [...t].filter((w) => words(f.title).has(w)).length;
    if (score > bestScore) { best = i; bestScore = score; }
  });
  if (best === null) return null;
  used.add(best);
  return features[best];
}

async function visibleTabs(page) {
  const names = await page.$$eval(TAB_SELECTOR, (els) => els
    .filter((e) => e.offsetParent !== null && (e.innerText || '').trim().length > 0 && (e.innerText || '').trim().length < 40)
    .map((e) => (e.innerText || '').trim().split('\n')[0]));
  return [...new Set(names)].slice(0, MAX_TABS);
}

async function record(browser, p, outDir) {
  const tmp = fs.mkdtempSync(path.join(outDir, '.rec-'));
  const ctx = await browser.newContext({ viewport: SIZE, recordVideo: { dir: tmp, size: SIZE }, colorScheme: 'light' });
  const page = await ctx.newPage();
  const color = p.color || '#6c4cf1';
  await page.goto(`http://127.0.0.1:${p.port}/`, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(600);

  await card(page, `
    <div style="color:#b9c0e0;font-size:18px;letter-spacing:.14em;text-transform:uppercase;font-weight:bold">${esc(p.domain)}</div>
    <div style="font-size:76px;font-weight:bold;margin:14px 0 10px">${esc(p.name)}</div>
    <div style="font-size:30px;color:#e3e6f5;max-width:960px">${esc(p.tagline)}</div>
    <div style="font-size:21px;color:#b9c0e0;margin-top:34px;max-width:980px">${esc((p.problem || [])[0] || '')}</div>
    <div style="font-size:16px;color:#8a90b4;margin-top:46px">QUANTIX 2K26 · K.S.R. College of Engineering · runs offline: python app.py</div>`, color, 4200);

  const demo = page.getByRole('button', { name: DEMO_RE }).first();
  if (await demo.count()) {
    await caption(page, `Run demo · ${(p.demo_flow || [])[0] || 'loading the demo scenario'}`, color);
    await demo.click({ timeout: 5000 }).catch(() => {});
    await page.waitForTimeout(3500);
  } else {
    await caption(page, (p.demo_flow || [])[0] || p.tagline, color);
    await page.waitForTimeout(1500);
  }
  const tabs = await visibleTabs(page);
  if (!tabs.length) {
    await caption(page, (p.features || []).map((f) => f.title).slice(0, 4).join(' · '), color);
    await tour(page, 6);
  }
  const used = new Set();
  for (const name of tabs) {
    const el = page.locator(TAB_SELECTOR).filter({ hasText: name }).first();
    if (!(await el.isVisible().catch(() => false))) continue;
    const feature = matchFeature(name, p.features || [], used);
    await caption(page, feature ? `${name} — ${feature.title}: ${feature.desc}` : name, color);
    await el.click({ timeout: 5000 }).catch(() => {});
    await page.waitForTimeout(1500);
    await tour(page, 3);
  }
  await caption(page, 'Every number on screen is computed live, offline, by algorithms written from scratch', color);
  await page.waitForTimeout(1500);

  const results = (p.results || []).slice(0, 4).map((r) =>
    `<div style="background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.14);border-radius:14px;padding:18px 22px;min-width:220px;max-width:260px">
       <div style="font-size:40px;font-weight:bold;color:#fff">${esc(r.value)}</div>
       <div style="font-size:16px;color:#c9cde4;margin-top:6px">${esc(r.label)}</div></div>`).join('');
  await card(page, `
    <div style="font-size:44px;font-weight:bold;margin-bottom:26px">${esc(p.name)}: measured results</div>
    <div style="display:flex;gap:18px;flex-wrap:wrap">${results}</div>
    <div style="font-size:18px;color:#b9c0e0;margin-top:40px">Code, report and tests: ${esc(p.dir)} · python app.py → http://localhost:${esc(p.port)}</div>`, color, 4500);

  const video = page.video();
  await ctx.close();
  const webm = await video.path();
  const mp4 = path.join(outDir, `${p.dir}.mp4`);
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-i', webm, '-c:v', 'libx264', '-preset', 'veryfast',
    '-crf', '26', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', mp4]);
  fs.rmSync(tmp, { recursive: true, force: true });
  return mp4;
}

(async () => {
  const outDir = path.resolve(process.argv[2] || path.join(ROOT, 'build', 'videos'));
  const ports = process.argv.slice(3).map(Number);
  fs.mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch();
  for (const p of projects().filter((x) => !ports.length || ports.includes(x.port))) {
    const t0 = Date.now();
    try {
      const f = await record(browser, p, outDir);
      console.log(`${p.dir.padEnd(18)} ${((Date.now() - t0) / 1000).toFixed(0)}s  ${(fs.statSync(f).size / 1e6).toFixed(1)} MB`);
    } catch (e) {
      console.log(`${p.dir.padEnd(18)} FAILED ${e.message.split('\n')[0]}`);
    }
  }
  await browser.close();
})();
