// Browser QA sweep over every running demo (start them first with `python run_all.py`).
//
//   NODE_PATH="$(npm root -g)" node tools/qa_sweep.js [out.json] [port ...]
//
// For each project (ports from projects/*/pitch.json): load the page, click its demo button,
// visit every tab-like control at desktop (1440x900) and phone (390x844) sizes, and record
// console errors, uncaught exceptions, failed requests (HTTP >= 400 or network failure) and
// horizontal overflow on phones. Exits non-zero if anything was found.
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..');
const TAB_SELECTOR = [
  '[role="tab"]', 'nav button', 'nav a[href^="#"]', '.tabs button', '.tab', '.tabs a',
  'button[data-tab]', 'a[data-tab]', '[data-view]', 'header nav a',
].join(',');
const DEMO_RE = /^(▶\s*)?(run demo|load demo|load demo data|load demo notes|load demo farm|demo)$/i;

function projects() {
  return fs.readdirSync(path.join(ROOT, 'projects')).sort()
    .map((d) => path.join(ROOT, 'projects', d, 'pitch.json'))
    .filter((f) => fs.existsSync(f))
    .map((f) => ({ ...JSON.parse(fs.readFileSync(f, 'utf8')), dir: path.basename(path.dirname(f)) }));
}

async function visibleTabs(page) {
  return page.$$eval(TAB_SELECTOR, (els) => els
    .filter((e) => e.offsetParent !== null && (e.innerText || '').trim().length > 0 && (e.innerText || '').trim().length < 40)
    .map((e) => (e.innerText || '').trim().split('\n')[0]))
    .then((names) => [...new Set(names)]);
}

async function sweep(browser, p, viewport, label) {
  const issues = [];
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  page.on('console', (m) => { if (m.type() === 'error') issues.push({ kind: 'console', where: page.url(), text: m.text().slice(0, 300) }); });
  page.on('pageerror', (e) => issues.push({ kind: 'exception', where: page.url(), text: String(e.message).slice(0, 300) }));
  page.on('requestfailed', (r) => issues.push({ kind: 'request-failed', text: `${r.method()} ${r.url()} ${r.failure() && r.failure().errorText}` }));
  page.on('response', (r) => { if (r.status() >= 400) issues.push({ kind: 'http', text: `${r.status()} ${r.request().method()} ${r.url()}` }); });
  const url = `http://127.0.0.1:${p.port}/`;
  const visited = [];
  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(1000);
    const demo = page.getByRole('button', { name: DEMO_RE }).first();
    if (await demo.count()) {
      await demo.click({ timeout: 5000 }).catch(() => {});
      await page.waitForTimeout(2500);
    }
    const tabs = await visibleTabs(page);
    for (const name of tabs) {
      const el = page.locator(TAB_SELECTOR).filter({ hasText: name }).first();
      if (!(await el.isVisible().catch(() => false))) continue;
      await el.click({ timeout: 5000 }).catch((e) => issues.push({ kind: 'click', text: `${name}: ${e.message.split('\n')[0]}` }));
      await page.waitForTimeout(1200);
      visited.push(name);
      if (viewport.width < 500) {
        const over = await page.evaluate(() => {
          const w = document.documentElement.clientWidth;
          const sw = document.documentElement.scrollWidth;
          if (sw <= w + 2) return null;
          const wide = [...document.querySelectorAll('body *')]
            .filter((e) => { const r = e.getBoundingClientRect(); return r.right > w + 2 && r.width > 0 && getComputedStyle(e).position !== 'fixed'; })
            .filter((e) => !e.closest('[style*="overflow"], .table-wrap, .scroll-x, pre, table'))
            .slice(0, 3).map((e) => `${e.tagName.toLowerCase()}${e.id ? '#' + e.id : ''}${e.className && typeof e.className === 'string' ? '.' + e.className.split(' ')[0] : ''}`);
          return { scrollWidth: sw, width: w, culprits: wide };
        });
        if (over) issues.push({ kind: 'overflow', text: `tab "${name}": scrollWidth ${over.scrollWidth} > ${over.width}; ${over.culprits.join(', ')}` });
      }
    }
  } catch (e) {
    issues.push({ kind: 'load', text: e.message.split('\n')[0] });
  }
  await ctx.close();
  return { label, visited, issues };
}

(async () => {
  const out = process.argv[2] || path.join(ROOT, 'build', 'qa_sweep.json');
  const ports = process.argv.slice(3).map(Number);
  const list = projects().filter((p) => !ports.length || ports.includes(p.port));
  const browser = await chromium.launch();
  const report = [];
  for (const p of list) {
    const desktop = await sweep(browser, p, { width: 1440, height: 900 }, 'desktop');
    const phone = await sweep(browser, p, { width: 390, height: 844 }, 'phone');
    const n = desktop.issues.length + phone.issues.length;
    console.log(`${p.dir.padEnd(18)} tabs ${String(desktop.visited.length).padStart(2)}  issues ${n}`);
    report.push({ project: p.dir, port: p.port, desktop, phone });
  }
  await browser.close();
  fs.mkdirSync(path.dirname(out), { recursive: true });
  fs.writeFileSync(out, JSON.stringify(report, null, 1));
  const total = report.reduce((s, r) => s + r.desktop.issues.length + r.phone.issues.length, 0);
  console.log(`\n${total} issue(s); details in ${out}`);
  process.exit(total ? 1 : 0);
})();
