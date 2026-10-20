// Capture up to four screenshots of different views of every running demo, for the pitch decks.
//
//   NODE_PATH="$(npm root -g)" node tools/capture_tabs.js [port ...]
//
// Start the demos first (`python run_all.py`, ideally from a scratch copy: the demos write state
// files). For each project: load it at 1440x900, press its demo button, then screenshot the first
// tab and the next distinct tabs (a numbered run such as "Flight 1..5" counts once, at its last
// step). Apps without tabs are captured at successive scroll positions instead.
// Output: projects/<dir>/docs/shots/<n>.jpg plus shots.json [{file, label}], used by build_decks.js.
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');
const { ROOT, projects, clickDemo, visibleTabs, groupTabs, tabLocator } = require('./lib/demo_nav.js');

const VIEWPORT = { width: 1440, height: 900 };
const MAX_SHOTS = 4;

// Heading of the first section visible in the viewport, as a label for scroll-position shots.
const visibleHeading = (page) => page.evaluate(() => {
  const h = [...document.querySelectorAll('h2, h3')].find((e) => {
    const r = e.getBoundingClientRect();
    return r.top >= 0 && r.top < window.innerHeight * 0.6 && e.offsetParent !== null;
  });
  return h ? h.textContent.replace(/\s+/g, ' ').trim().slice(0, 40) : '';
});

async function capture(browser, p) {
  const ctx = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 1, colorScheme: 'light' });
  const page = await ctx.newPage();
  await page.goto(`http://127.0.0.1:${p.port}/`, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(800);
  await clickDemo(page, 3000);

  const shots = [];
  const outDir = path.join(ROOT, 'projects', p.dir, 'docs', 'shots');
  fs.rmSync(outDir, { recursive: true, force: true });
  fs.mkdirSync(outDir, { recursive: true });
  const snap = async (label) => {
    const file = `${shots.length + 1}.jpg`;
    await page.screenshot({ path: path.join(outDir, file), type: 'jpeg', quality: 80 });
    shots.push({ file, label });
  };

  const groups = groupTabs(await visibleTabs(page));
  if (groups.length >= 2) {
    for (const g of groups) {
      if (shots.length >= MAX_SHOTS) break;
      for (const t of g.items) await tabLocator(page, t).click({ timeout: 5000 }).catch(() => {});
      await page.waitForTimeout(1500);
      await page.evaluate(() => window.scrollTo(0, 0));
      const t = g.items[g.items.length - 1];
      await snap(t.label);
    }
  } else {
    // single-page app: step down the page one viewport at a time
    const height = await page.evaluate(() => document.documentElement.scrollHeight);
    for (let y = 0; shots.length < MAX_SHOTS && y < height - VIEWPORT.height / 3; y += VIEWPORT.height - 120) {
      await page.evaluate((top) => window.scrollTo(0, top), y);
      await page.waitForTimeout(700);
      await snap(y === 0 ? 'Overview' : await visibleHeading(page));
    }
  }
  fs.writeFileSync(path.join(outDir, 'shots.json'), JSON.stringify(shots, null, 2) + '\n');
  await ctx.close();
  return shots;
}

(async () => {
  const ports = process.argv.slice(2).map(Number);
  const browser = await chromium.launch();
  let failed = 0;
  for (const p of projects().filter((x) => !ports.length || ports.includes(x.port))) {
    try {
      const shots = await capture(browser, p);
      console.log(`${p.dir.padEnd(18)} ${shots.map((s) => s.label).join(' | ')}`);
    } catch (e) {
      failed++;
      console.log(`${p.dir.padEnd(18)} FAILED ${e.message.split('\n')[0]}`);
    }
  }
  await browser.close();
  process.exit(failed ? 1 : 0);
})();
