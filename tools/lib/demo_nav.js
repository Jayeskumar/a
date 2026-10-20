// Shared helpers for the browser tools (qa_sweep.js, record_demos.js, capture_tabs.js):
// find every project, press its demo button and discover its tab-like controls.
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const TAB_SELECTOR = [
  '[role="tab"]', 'nav button', 'nav a[href^="#"]', '.tabs button', '.tab', '.tabs a',
  'button[data-tab]', 'a[data-tab]', '[data-view]', 'header nav a',
].join(',');
const DEMO_RE = /^(▶\s*)?(run demo|load demo|load demo data|load demo notes|load demo farm|demo)$/i;

// pitch.json of every project, with its folder name as `dir`
function projects() {
  return fs.readdirSync(path.join(ROOT, 'projects')).sort()
    .map((d) => path.join(ROOT, 'projects', d, 'pitch.json'))
    .filter((f) => fs.existsSync(f))
    .map((f) => ({ ...JSON.parse(fs.readFileSync(f, 'utf8')), dir: path.basename(path.dirname(f)) }));
}

// Click the project's demo button if it has one; resolves to true if it was clicked.
async function clickDemo(page, settleMs = 2500) {
  const demo = page.getByRole('button', { name: DEMO_RE }).first();
  if (!(await demo.count())) return false;
  await demo.click({ timeout: 5000 }).catch(() => {});
  await page.waitForTimeout(settleMs);
  return true;
}

// Visible tab-like controls as {name (to find it again), label (text without badge counters)}.
async function visibleTabs(page) {
  const tabs = await page.$$eval(TAB_SELECTOR, (els) => els
    .filter((e) => e.offsetParent !== null && (e.innerText || '').trim().length > 0 && (e.innerText || '').trim().length < 40)
    .map((e) => {
      const name = (e.innerText || '').trim().split('\n')[0];
      const badge = [...e.querySelectorAll('*')].map((k) => k.textContent.trim()).find((t) => /^\(?\d+\)?$/.test(t));
      return { name, label: badge && name.endsWith(badge) ? name.slice(0, -badge.length).trim() : name };
    }));
  const seen = new Set();
  return tabs.filter((t) => !seen.has(t.name) && seen.add(t.name));
}

// Group numbered runs of tabs ("Flight 1" .. "Flight 5") so they count as one stop.
function groupTabs(tabs, max = Infinity) {
  const stem = (s) => (s.match(/^(.*\S)\s+\d+$/) || [])[1];
  const groups = [];
  for (const t of tabs) {
    const g = groups[groups.length - 1], st = stem(t.label);
    if (st && g && g.stem === st) g.items.push(t); else groups.push({ stem: st, items: [t] });
  }
  return groups.slice(0, max);
}

const tabLocator = (page, t) => page.locator(TAB_SELECTOR).filter({ hasText: t.name }).first();

module.exports = { ROOT, TAB_SELECTOR, DEMO_RE, projects, clickDemo, visibleTabs, groupTabs, tabLocator };
