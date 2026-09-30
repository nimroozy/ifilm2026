/**
 * GUI milestone visual capture (mock preview).
 * Usage: node scripts/gui-stabilization-screenshots.mjs
 */
import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';

const BASE = process.env.GUI_BASE_URL || 'http://127.0.0.1:4173';
const OUT = process.env.GUI_SHOT_DIR || '/opt/cursor/artifacts/gui-stabilization';

const viewports = [
  { name: '1920', width: 1920, height: 1080 },
  { name: '1440', width: 1440, height: 900 },
  { name: '1024', width: 1024, height: 768 },
  { name: '768', width: 768, height: 1024 },
  { name: '430', width: 430, height: 932 },
  { name: '390', width: 390, height: 844 },
];

const routes = [
  { path: '/', id: 'home' },
  { path: '/movies', id: 'movies' },
  { path: '/series', id: 'series' },
  { path: '/search', id: 'search' },
  { path: '/login', id: 'login' },
];

const langs = ['en', 'fa', 'ps'];

async function setLang(page, lang) {
  await page.addInitScript((value) => {
    localStorage.setItem('ifilm.locale', value);
    document.cookie = `ifilm.locale=${value}; path=/`;
  }, lang);
}

async function main() {
  await mkdir(OUT, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const report = [];

  for (const lang of langs) {
    for (const vp of viewports) {
      // Representative set: all routes at 1440+en, home+movies at all viewports/langs
      const paths =
        lang === 'en' && vp.name === '1440'
          ? routes
          : routes.filter((r) => ['home', 'movies', 'search'].includes(r.id));

      for (const route of paths) {
        const context = await browser.newContext({
          viewport: { width: vp.width, height: vp.height },
          locale: lang === 'en' ? 'en-US' : lang === 'fa' ? 'fa-IR' : 'ps-AF',
        });
        const page = await context.newPage();
        const consoleErrors = [];
        page.on('console', (msg) => {
          if (msg.type() === 'error') consoleErrors.push(msg.text());
        });
        page.on('pageerror', (err) => consoleErrors.push(String(err)));

        await setLang(page, lang);
        // Also try common selector for in-app language if localStorage key differs
        const url = `${BASE}${route.path}`;
        await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
        // Attempt UI language switch if present
        const langBtn = page.locator('[data-testid="lang-switch"], select[name="lang"], button:has-text("FA"), button:has-text("PS")').first();
        if (await langBtn.count()) {
          try {
            if (lang !== 'en') {
              await page.evaluate((l) => {
                window.dispatchEvent(new CustomEvent('ifilm-set-lang', { detail: l }));
                localStorage.setItem('ifilm_language', l);
              }, lang);
              await page.reload({ waitUntil: 'networkidle' });
            }
          } catch {
            /* ignore */
          }
        }

        await page.waitForTimeout(500);
        const overflow = await page.evaluate(() => {
          const doc = document.documentElement;
          return {
            scrollWidth: doc.scrollWidth,
            clientWidth: doc.clientWidth,
            overflowX: doc.scrollWidth > doc.clientWidth + 1,
            dir: doc.getAttribute('dir') || document.body.getAttribute('dir') || '',
            title: document.title,
          };
        });
        const file = `${route.id}_${lang}_${vp.name}.png`;
        await page.screenshot({ path: path.join(OUT, file), fullPage: false });
        report.push({ file, url, lang, viewport: vp.name, ...overflow, consoleErrors: consoleErrors.slice(0, 5) });
        await context.close();
      }
    }
  }

  // Movie detail if a card link exists
  {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await context.newPage();
    await page.goto(`${BASE}/`, { waitUntil: 'networkidle' });
    const link = page.locator('a[href^="/movie/"]').first();
    if (await link.count()) {
      await link.click();
      await page.waitForLoadState('networkidle');
      await page.screenshot({ path: path.join(OUT, 'movie_detail_en_1440.png'), fullPage: false });
      report.push({ file: 'movie_detail_en_1440.png', title: await page.title() });
    }
    const seriesLink = page.locator('a[href^="/series/"]').first();
    await page.goto(`${BASE}/series`, { waitUntil: 'networkidle' });
    const s = page.locator('a[href^="/series/"]').first();
    if (await s.count()) {
      await s.click();
      await page.waitForLoadState('networkidle');
      await page.screenshot({ path: path.join(OUT, 'series_detail_en_1440.png'), fullPage: false });
      report.push({ file: 'series_detail_en_1440.png', title: await page.title() });
    }
    await context.close();
  }

  await browser.close();
  const summaryPath = path.join(OUT, 'summary.json');
  await import('node:fs/promises').then((fs) => fs.writeFile(summaryPath, JSON.stringify(report, null, 2)));
  console.log(`Wrote ${report.length} captures to ${OUT}`);
  const overflows = report.filter((r) => r.overflowX);
  const titles = report.filter((r) => r.title);
  console.log(`overflow_x_count=${overflows.length}`);
  console.log(`sample_titles=${titles.slice(0, 5).map((t) => t.title).join(' | ')}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
