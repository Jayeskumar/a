// Headless screenshot + console-error check for a running demo.
// Usage: NODE_PATH="$(npm root -g)" node tools/screenshot.js <url> <out.png> [clickSelector ...]
// Each extra argument is a CSS selector clicked in order (waits 800ms after each).
// Exits non-zero if the page logs any console error or uncaught exception.
const { chromium } = require('playwright');

(async () => {
  const [url, out, ...clicks] = process.argv.slice(2);
  if (!url || !out) {
    console.error('usage: screenshot.js <url> <out.png> [clickSelector ...]');
    process.exit(2);
  }
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  await page.goto(url, { waitUntil: 'networkidle' });
  await page.waitForTimeout(800);
  for (const sel of clicks) {
    await page.click(sel);
    await page.waitForTimeout(800);
  }
  await page.screenshot({ path: out, fullPage: false });
  await browser.close();
  if (errors.length) {
    console.error(errors.join('\n'));
    process.exit(1);
  }
  console.log('ok ' + out);
})();
