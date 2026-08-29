import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';

const baseUrl = process.env.KRABI_WEB_URL || 'http://127.0.0.1:4173';
const outDir = process.env.KRABI_E2E_OUT || 'artifacts/krabi-web-e2e';
await fs.mkdir(outDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 }, deviceScaleFactor: 1 });
const consoleErrors = [];
page.on('console', (message) => {
  if (message.type() === 'error') consoleErrors.push(message.text());
});
page.on('pageerror', (error) => consoleErrors.push(error.message));

const report = { baseUrl, dashboard: {}, dsas: {}, consoleErrors };

try {
  await page.goto(`${baseUrl}/index.html`, { waitUntil: 'domcontentloaded', timeout: 60_000 });
  await page.waitForFunction(() => window.__KRABI_DASHBOARD_TEST__?.ready === true, null, { timeout: 60_000 });

  const dashboard = await page.evaluate(() => {
    const state = window.__KRABI_DASHBOARD_TEST__;
    const before = document.getElementById('beforeImage');
    const after = document.getElementById('afterImage');
    const stage = document.getElementById('compareStage');
    return {
      state: JSON.parse(JSON.stringify(state)),
      before: { src: before.currentSrc || before.src, width: before.naturalWidth, height: before.naturalHeight },
      after: { src: after.currentSrc || after.src, width: after.naturalWidth, height: after.naturalHeight },
      split: getComputedStyle(stage).getPropertyValue('--split').trim(),
      clipPath: getComputedStyle(after).clipPath
    };
  });

  if (dashboard.before.src === dashboard.after.src) throw new Error('Before and after image URLs are identical');
  if (dashboard.before.width !== 1900 || dashboard.before.height !== 2350) throw new Error(`Unexpected before dimensions: ${dashboard.before.width}x${dashboard.before.height}`);
  if (dashboard.after.width !== 1900 || dashboard.after.height !== 2350) throw new Error(`Unexpected after dimensions: ${dashboard.after.width}x${dashboard.after.height}`);

  const clipBefore = dashboard.clipPath;
  await page.locator('#compareRange').fill('18');
  await page.waitForTimeout(250);
  const sliderResult = await page.evaluate(() => ({
    split: getComputedStyle(document.getElementById('compareStage')).getPropertyValue('--split').trim(),
    clipPath: getComputedStyle(document.getElementById('afterImage')).clipPath,
    label: document.getElementById('splitValue').textContent
  }));
  if (sliderResult.clipPath === clipBefore) throw new Error('Slider did not change after-image clip-path');
  if (sliderResult.split !== '18%') throw new Error(`Slider CSS split is ${sliderResult.split}, expected 18%`);
  report.dashboard = { ...dashboard, sliderResult };
  await page.screenshot({ path: path.join(outDir, 'province-dashboard.png'), fullPage: true });

  await page.goto(`${baseUrl}/published-dsas.html`, { waitUntil: 'domcontentloaded', timeout: 60_000 });
  await page.waitForFunction(() => window.__KRABI_DSAS_TEST__?.ready === true, null, { timeout: 60_000 });
  const dsas = await page.evaluate(() => {
    const state = window.__KRABI_DSAS_TEST__;
    const canvas = document.getElementById('mapCanvas');
    return {
      state: JSON.parse(JSON.stringify({
        ready: state.ready,
        featureCount: state.featureCount,
        drawnCount: state.drawnCount,
        selectedTransectId: state.selectedTransectId,
        imageDimensions: state.imageDimensions,
        error: state.error
      })),
      canvas: { width: canvas.width, height: canvas.height },
      visibleText: document.getElementById('visibleCount').textContent,
      selectedRate: document.getElementById('selectedRate').textContent
    };
  });

  if (dsas.state.featureCount !== 666) throw new Error(`DSAS feature count is ${dsas.state.featureCount}, expected 666`);
  if (dsas.state.drawnCount !== 666) throw new Error(`DSAS drawn count is ${dsas.state.drawnCount}, expected 666`);
  if (!dsas.state.selectedTransectId) throw new Error('No DSAS feature was selected after initialization');
  if (dsas.state.imageDimensions?.[0] !== 1900 || dsas.state.imageDimensions?.[1] !== 2350) throw new Error(`Unexpected DSAS background dimensions: ${dsas.state.imageDimensions}`);
  if (dsas.canvas.width < 500 || dsas.canvas.height < 500) throw new Error(`DSAS canvas is too small: ${dsas.canvas.width}x${dsas.canvas.height}`);

  await page.locator('#showRetreat').click();
  await page.waitForTimeout(200);
  const retreatCount = await page.evaluate(() => window.__KRABI_DSAS_TEST__.drawnCount);
  if (!(retreatCount > 0 && retreatCount < 666)) throw new Error(`Retreat filter returned invalid count: ${retreatCount}`);
  await page.locator('#showAll').click();
  await page.locator('.hotspot').first().click();
  await page.waitForTimeout(200);
  const selectedAfterClick = await page.evaluate(() => window.__KRABI_DSAS_TEST__.selectedTransectId);
  if (!selectedAfterClick) throw new Error('Hotspot click did not select a transect');

  report.dsas = { ...dsas, retreatFilterCount: retreatCount, selectedAfterClick };
  await page.screenshot({ path: path.join(outDir, 'published-dsas.png'), fullPage: true });

  const fatalErrors = consoleErrors.filter((value) => !value.includes('favicon.ico'));
  if (fatalErrors.length) throw new Error(`Browser console errors: ${fatalErrors.join(' | ')}`);
  report.status = 'PASS';
} catch (error) {
  report.status = 'FAIL';
  report.error = error.stack || error.message;
  await page.screenshot({ path: path.join(outDir, 'failure.png'), fullPage: true }).catch(() => {});
  throw error;
} finally {
  await fs.writeFile(path.join(outDir, 'report.json'), JSON.stringify(report, null, 2));
  await browser.close();
}
