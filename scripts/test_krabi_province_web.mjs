import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';

const baseUrl = (process.env.KRABI_WEB_URL || 'http://127.0.0.1:4173').replace(/\/$/, '');
const outDir = process.env.KRABI_E2E_OUT || 'artifacts/krabi-web-e2e';
const isProductionWrapper = /vercel\.app$/i.test(new URL(baseUrl).hostname);
const dashboardUrl = `${baseUrl}${isProductionWrapper ? '/province-overview.html' : '/index.html'}`;
const beforeAfterUrl = `${baseUrl}${isProductionWrapper ? '/' : '/before-after-map.html'}`;
const dsasUrl = `${baseUrl}/published-dsas.html`;
const wrongProvincePattern = /สมุทรสงคราม|สมุทรสาคร|ระยอง/;

await fs.mkdir(outDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 }, deviceScaleFactor: 1 });
const consoleErrors = [];
page.on('console', (message) => {
  if (message.type() !== 'error') return;
  const text = message.text();
  if (
    text.includes('favicon.ico') ||
    text.includes('server.arcgisonline.com') ||
    text.includes('Failed to load resource: net::ERR_BLOCKED_BY_CLIENT')
  ) return;
  consoleErrors.push(text);
});
page.on('pageerror', (error) => consoleErrors.push(error.message));

const report = {
  baseUrl,
  dashboardUrl,
  beforeAfterUrl,
  dsasUrl,
  dashboard: {},
  beforeAfter: {},
  dsas: {},
  consoleErrors,
};

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function setRange(selector, value) {
  await page.locator(selector).evaluate((element, nextValue) => {
    element.value = String(nextValue);
    element.dispatchEvent(new Event('input', { bubbles: true }));
  }, value);
}

try {
  await page.goto(dashboardUrl, { waitUntil: 'domcontentloaded', timeout: 60_000 });
  await page.waitForFunction(
    () => window.__KRABI_DASHBOARD_TEST__?.ready === true,
    undefined,
    { timeout: 120_000 },
  );

  const dashboard = await page.evaluate(() => {
    const state = window.__KRABI_DASHBOARD_TEST__;
    const before = document.getElementById('beforeImage');
    const after = document.getElementById('afterImage');
    const stage = document.getElementById('compareStage');
    return {
      state: JSON.parse(JSON.stringify(state)),
      title: document.title,
      heading: document.querySelector('h1')?.textContent?.trim() || '',
      bodyText: document.body.innerText,
      before: {
        src: before.currentSrc || before.src,
        width: before.naturalWidth,
        height: before.naturalHeight,
      },
      after: {
        src: after.currentSrc || after.src,
        width: after.naturalWidth,
        height: after.naturalHeight,
      },
      split: getComputedStyle(stage).getPropertyValue('--split').trim(),
      clipPath: getComputedStyle(after).clipPath,
      latestDataDate: document.getElementById('latestDataDate')?.textContent?.trim(),
      mapLink: document.querySelector('a[href="before-after-map.html"]')?.textContent?.trim(),
    };
  });

  assert(dashboard.state.province === 'Krabi', `Dashboard province is ${dashboard.state.province}`);
  assert(dashboard.state.beforeYear === 2018 && dashboard.state.afterYear === 2026,
    `Unexpected dashboard pair ${dashboard.state.beforeYear}-${dashboard.state.afterYear}`);
  assert(dashboard.state.manifest?.current_year_status === 'VALIDATED_SENTINEL2_L2A_YEAR_TO_DATE',
    `Unexpected current-year status ${dashboard.state.manifest?.current_year_status}`);
  assert(/^2026-/.test(dashboard.state.latestDataThrough || ''),
    `Latest data date is not in 2026: ${dashboard.state.latestDataThrough}`);
  assert(dashboard.mapLink, 'Province dashboard has no link to the before-after map');
  assert(/กระบี่|Krabi/i.test(`${dashboard.title} ${dashboard.heading}`), 'Dashboard is not identified as Krabi');
  assert(!wrongProvincePattern.test(dashboard.bodyText), 'Dashboard still contains another province name');
  assert(dashboard.before.src !== dashboard.after.src, 'Before and after image URLs are identical');
  assert(dashboard.after.src.includes('krabi_province_s2_2026_ytd.jpg'),
    `Dashboard does not load the 2026 YTD asset: ${dashboard.after.src}`);
  assert(dashboard.before.width === 1900 && dashboard.before.height === 2350,
    `Unexpected before dimensions ${dashboard.before.width}x${dashboard.before.height}`);
  assert(dashboard.after.width === 1900 && dashboard.after.height === 2350,
    `Unexpected after dimensions ${dashboard.after.width}x${dashboard.after.height}`);

  const dashboardClipBefore = dashboard.clipPath;
  await setRange('#compareRange', 18);
  await page.waitForFunction(
    () => getComputedStyle(document.getElementById('compareStage')).getPropertyValue('--split').trim() === '18%',
  );
  const dashboardSlider = await page.evaluate(() => ({
    split: getComputedStyle(document.getElementById('compareStage')).getPropertyValue('--split').trim(),
    clipPath: getComputedStyle(document.getElementById('afterImage')).clipPath,
    label: document.getElementById('splitValue').textContent,
  }));
  assert(dashboardSlider.clipPath !== dashboardClipBefore, 'Dashboard slider did not change clip-path');
  assert(dashboardSlider.split === '18%', `Dashboard split is ${dashboardSlider.split}`);

  await page.selectOption('#beforeYear', '2024');
  await page.waitForFunction(
    () => window.__KRABI_DASHBOARD_TEST__?.ready === true &&
      window.__KRABI_DASHBOARD_TEST__?.beforeYear === 2024 &&
      window.__KRABI_DASHBOARD_TEST__?.afterYear === 2026,
    undefined,
    { timeout: 120_000 },
  );

  report.dashboard = { ...dashboard, dashboardSlider };
  await page.screenshot({ path: path.join(outDir, 'province-dashboard-2026.png'), fullPage: true });

  await page.goto(beforeAfterUrl, { waitUntil: 'domcontentloaded', timeout: 60_000 });
  await page.waitForFunction(
    () => window.__KRABI_BEFORE_AFTER_TEST__?.ready === true,
    undefined,
    { timeout: 120_000 },
  );

  const mapInitial = await page.evaluate(() => {
    const state = window.__KRABI_BEFORE_AFTER_TEST__;
    const viewport = document.getElementById('afterViewport');
    return {
      state: JSON.parse(JSON.stringify(state)),
      title: document.title,
      heading: document.querySelector('h1')?.textContent?.trim() || '',
      bodyText: document.body.innerText,
      clipPath: getComputedStyle(viewport).clipPath,
      beforeLabel: document.getElementById('beforeLabel').textContent,
      afterLabel: document.getElementById('afterLabel').textContent,
      latestMetric: document.getElementById('latestMetric')?.textContent?.trim(),
      leafletMaps: document.querySelectorAll('.leaflet-container').length,
    };
  });

  assert(mapInitial.state.province === 'Krabi', `Swipe-map province is ${mapInitial.state.province}`);
  assert(mapInitial.state.beforeYear === 2018 && mapInitial.state.afterYear === 2026,
    `Unexpected initial map pair ${mapInitial.state.beforeYear}-${mapInitial.state.afterYear}`);
  assert(mapInitial.state.currentYearStatus === 'VALIDATED_SENTINEL2_L2A_YEAR_TO_DATE',
    `Unexpected map current-year status ${mapInitial.state.currentYearStatus}`);
  assert(/^2026-/.test(mapInitial.state.latestDataThrough || ''),
    `Map latest date is not in 2026: ${mapInitial.state.latestDataThrough}`);
  assert(mapInitial.state.imageDimensions?.[0] === 1900 && mapInitial.state.imageDimensions?.[1] === 2350,
    `Unexpected swipe-map image dimensions ${mapInitial.state.imageDimensions}`);
  assert(mapInitial.leafletMaps === 2, `Expected two Leaflet maps, found ${mapInitial.leafletMaps}`);
  assert(mapInitial.state.mapSync?.delta <= 1e-7,
    `Initial maps are not synchronized: ${mapInitial.state.mapSync?.delta}`);
  assert(/กระบี่|Krabi/i.test(`${mapInitial.title} ${mapInitial.heading}`), 'Swipe map is not identified as Krabi');
  assert(!wrongProvincePattern.test(mapInitial.bodyText), 'Swipe map still contains another province name');
  assert(/2026/.test(mapInitial.afterLabel), `After label is not 2026: ${mapInitial.afterLabel}`);

  const mapClipBefore = mapInitial.clipPath;
  await setRange('#compareRange', 23);
  await page.waitForFunction(() => window.__KRABI_BEFORE_AFTER_TEST__?.split === 23);
  const splitResult = await page.evaluate(() => ({
    split: window.__KRABI_BEFORE_AFTER_TEST__.split,
    clipPath: getComputedStyle(document.getElementById('afterViewport')).clipPath,
    readout: document.getElementById('splitReadout').textContent,
  }));
  assert(splitResult.split === 23, `Swipe-map split is ${splitResult.split}`);
  assert(splitResult.clipPath !== mapClipBefore, 'Swipe-map clip-path did not change');

  await page.selectOption('#beforeYear', '2020');
  await page.waitForFunction(
    () => window.__KRABI_BEFORE_AFTER_TEST__?.ready === true &&
      window.__KRABI_BEFORE_AFTER_TEST__?.beforeYear === 2020 &&
      window.__KRABI_BEFORE_AFTER_TEST__?.afterYear === 2026,
    undefined,
    { timeout: 120_000 },
  );

  await page.check('#showDsas');
  await page.waitForFunction(
    () => window.__KRABI_BEFORE_AFTER_TEST__?.dsasLoaded === true &&
      window.__KRABI_BEFORE_AFTER_TEST__?.dsasVisible === true &&
      window.__KRABI_BEFORE_AFTER_TEST__?.dsasCount === 666,
    undefined,
    { timeout: 90_000 },
  );

  await page.click('#viewKhlongThom');
  await page.waitForFunction(() => window.__KRABI_BEFORE_AFTER_TEST__?.view === 'khlong-thom');
  await page.waitForTimeout(500);
  const mapFinal = await page.evaluate(() => JSON.parse(JSON.stringify(window.__KRABI_BEFORE_AFTER_TEST__)));
  assert(mapFinal.ready === true, 'Final swipe-map state is not ready');
  assert(mapFinal.beforeYear === 2020 && mapFinal.afterYear === 2026,
    `Unexpected final pair ${mapFinal.beforeYear}-${mapFinal.afterYear}`);
  assert(mapFinal.dsasCount === 666, `DSAS count is ${mapFinal.dsasCount}`);
  assert(mapFinal.error === null, `Swipe-map error: ${mapFinal.error}`);
  assert(mapFinal.mapSync?.delta <= 1e-7, `Maps diverged: ${mapFinal.mapSync?.delta}`);

  report.beforeAfter = { mapInitial, splitResult, mapFinal };
  await page.screenshot({ path: path.join(outDir, 'before-after-map-2026.png'), fullPage: true });

  await page.goto(dsasUrl, { waitUntil: 'domcontentloaded', timeout: 60_000 });
  await page.waitForFunction(
    () => window.__KRABI_DSAS_TEST__?.ready === true,
    undefined,
    { timeout: 90_000 },
  );
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
        error: state.error,
      })),
      bodyText: document.body.innerText,
      canvas: { width: canvas.width, height: canvas.height },
    };
  });
  assert(dsas.state.featureCount === 666, `DSAS feature count is ${dsas.state.featureCount}`);
  assert(dsas.state.drawnCount === 666, `DSAS drawn count is ${dsas.state.drawnCount}`);
  assert(dsas.state.selectedTransectId, 'No DSAS feature selected after initialization');
  assert(dsas.state.imageDimensions?.[0] === 1900 && dsas.state.imageDimensions?.[1] === 2350,
    `Unexpected DSAS background dimensions ${dsas.state.imageDimensions}`);
  assert(dsas.canvas.width >= 500 && dsas.canvas.height >= 500,
    `DSAS canvas is too small ${dsas.canvas.width}x${dsas.canvas.height}`);
  assert(!wrongProvincePattern.test(dsas.bodyText), 'DSAS page contains another province name');

  await page.click('#showRetreat');
  await page.waitForTimeout(200);
  const retreatCount = await page.evaluate(() => window.__KRABI_DSAS_TEST__.drawnCount);
  assert(retreatCount > 0 && retreatCount < 666, `Invalid retreat filter count ${retreatCount}`);
  await page.click('#showAll');
  await page.locator('.hotspot').first().click();
  await page.waitForTimeout(200);
  const selectedAfterClick = await page.evaluate(() => window.__KRABI_DSAS_TEST__.selectedTransectId);
  assert(selectedAfterClick, 'Hotspot click did not select a transect');

  report.dsas = { ...dsas, retreatFilterCount: retreatCount, selectedAfterClick };
  await page.screenshot({ path: path.join(outDir, 'published-dsas.png'), fullPage: true });

  assert(consoleErrors.length === 0, `Browser console errors: ${consoleErrors.join(' | ')}`);
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
