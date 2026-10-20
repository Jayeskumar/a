// Render the combined report to one A4 PDF: a full-bleed cover page, then the body with
// margins and page numbers, joined with pdfunite (poppler-utils).
// Usage: NODE_PATH="$(npm root -g)" node tools/report_pdf.js build/report_cover.html build/QUANTIX2K26_Report.html out.pdf
const path = require('path');
const fs = require('fs');
const { execFileSync } = require('child_process');
const { chromium } = require('playwright');

async function render(browser, input, output, options) {
  const page = await browser.newPage();
  await page.goto('file://' + path.resolve(input), { waitUntil: 'load' });
  await page.waitForFunction(() => window.__diagramsDone === true, null, { timeout: 120000 });
  await page.pdf({ path: output, format: 'A4', printBackground: true, ...options });
  await page.close();
}

(async () => {
  const [cover, body, output] = process.argv.slice(2);
  const tmpCover = output + '.cover.pdf';
  const tmpBody = output + '.body.pdf';
  const browser = await chromium.launch();
  await render(browser, cover, tmpCover, { margin: { top: '0', bottom: '0', left: '0', right: '0' } });
  await render(browser, body, tmpBody, {
    margin: { top: '16mm', bottom: '18mm', left: '15mm', right: '15mm' },
    displayHeaderFooter: true,
    headerTemplate: '<div></div>',
    footerTemplate:
      '<div style="width:100%;font-size:8px;color:#8a90a2;padding:0 15mm;display:flex;justify-content:space-between;font-family:Arial,sans-serif">' +
      '<span>QUANTIX 2K26 · Project Portfolio &amp; Reports</span>' +
      '<span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>',
  });
  await browser.close();
  execFileSync('pdfunite', [tmpCover, tmpBody, output]);
  fs.unlinkSync(tmpCover);
  fs.unlinkSync(tmpBody);
})().catch((e) => { console.error(e); process.exit(1); });
