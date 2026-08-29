import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright';

const baseUrl = (process.env.RAYONG_WEB_URL || 'http://127.0.0.1:4173').replace(/\/$/, '');
const outputDir = process.env.RAYONG_E2E_OUT || 'artifacts/rayong-compare-e2e';
await mkdir(outputDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 960 }, deviceScaleFactor: 1 });
const pageErrors = [];
const consoleErrors = [];

page.on('pageerror', (error) => pageErrors.push(error.message));
page.on('console', (message) => {
  if (message.type() !== 'error') return;
  const text = message.text();
  if (text.includes('tile.openstreetmap.org') || text.includes('Failed to load resource')) return;
  consoleErrors.push(text);
});

try {
  await page.goto(`${baseUrl}/`, { waitUntil: 'domcontentloaded', timeout: 60_000 });
  await page.waitForFunction(
    () => window.__RAYONG_COMPARE_TEST__?.ready === true,
    undefined,
    { timeout: 60_000 },
  );
  await page.waitForFunction(
    () => window.__RAYONG_COMPARE_TEST__?.plotCount !== null,
    undefined,
    { timeout: 30_000 },
  );

  const initial = await page.evaluate(() => window.__RAYONG_COMPARE_TEST__);
  assert.equal(initial?.mapCount, 2, 'two synchronized MapLibre maps must be ready');
  assert.equal(initial?.beforeYear, '2018');
  assert.equal(initial?.afterYear, '2025');
  assert.equal(initial?.selectedLayer, 'rgb');
  assert.equal(initial?.plotCount, 14, 'validated KMZ-derived plot count must be 14');
  assert.equal(await page.locator('.maplibregl-canvas').count(), 2, 'both map canvases must exist');

  await page.locator('[data-testid="swipe-range"]').evaluate((element) => {
    const input = element;
    input.value = '27';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await page.waitForFunction(() => window.__RAYONG_COMPARE_TEST__?.swipe === 27);
  const clipPath = await page.locator('#after-pane').evaluate((element) => getComputedStyle(element).clipPath);
  assert.match(clipPath, /27%/, 'after map must be clipped at the selected swipe position');

  await page.selectOption('#before-year', '2021');
  await page.waitForFunction(() => window.__RAYONG_COMPARE_TEST__?.beforeYear === '2021');
  assert.equal(await page.locator('.before-label b').textContent(), '2021');

  await page.locator('button[data-layer="mndwi"]').click();
  await page.waitForFunction(() => window.__RAYONG_COMPARE_TEST__?.selectedLayer === 'mndwi');
  assert.match((await page.locator('.compare-meta').textContent()) || '', /MNDWI/);

  await page.locator('button[data-pair="2018-2025"]').click();
  await page.waitForFunction(
    () =>
      window.__RAYONG_COMPARE_TEST__?.beforeYear === '2018' &&
      window.__RAYONG_COMPARE_TEST__?.afterYear === '2025',
  );

  await page.screenshot({
    path: path.join(outputDir, 'rayong-before-after.png'),
    fullPage: true,
  });

  assert.deepEqual(pageErrors, [], `page errors: ${pageErrors.join(' | ')}`);
  assert.deepEqual(consoleErrors, [], `console errors: ${consoleErrors.join(' | ')}`);

  const finalState = await page.evaluate(() => window.__RAYONG_COMPARE_TEST__);
  await writeFile(
    path.join(outputDir, 'state.json'),
    JSON.stringify(finalState, null, 2),
    'utf8',
  );

  console.log(JSON.stringify({
    url: baseUrl,
    initial,
    finalState,
    clipPath,
    screenshot: path.join(outputDir, 'rayong-before-after.png'),
  }, null, 2));
} finally {
  await browser.close();
}
