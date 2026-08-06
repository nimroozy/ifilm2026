/**
 * PR #43 public catalog browser QA against live staging (real TMDB seed).
 *
 * Usage:
 *   BASE_URL=http://127.0.0.1:8080 LABEL=after node scripts/pr43-public-catalog-qa.mjs
 */
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';

const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:8080';
const LABEL = process.env.LABEL || 'after';
const OUT_DIR = process.env.OUT_DIR || '/opt/cursor/artifacts/pr43-phase2-live/screenshots';

const VIEWPORTS = [
  { name: '1366x768', width: 1366, height: 768 },
  { name: '1440x900', width: 1440, height: 900 },
  { name: '1920x1080', width: 1920, height: 1080 },
  { name: '390x844', width: 390, height: 844 },
  { name: '768x1024', width: 768, height: 1024 },
];

const FAKE_TITLE_PATTERNS = [
  /ocean horizon/i,
  /neon circuit/i,
  /solid color/i,
  /demo movie/i,
  /fake demo/i,
];

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

async function collectText(page) {
  return page.evaluate(() => document.body?.innerText || '');
}

async function run() {
  ensureDir(OUT_DIR);
  const browser = await chromium.launch({ headless: true });
  const findings = [];
  const results = [];

  for (const vp of VIEWPORTS) {
    const context = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
      deviceScaleFactor: 1,
    });
    const page = await context.newPage();
    const row = { viewport: vp.name, home: 'pending', movie: 'pending', notes: [] };

    try {
      await page.goto(`${BASE_URL}/`, { waitUntil: 'networkidle', timeout: 60000 });
      await page.waitForTimeout(1500);
      const homeText = await collectText(page);
      for (const re of FAKE_TITLE_PATTERNS) {
        if (re.test(homeText)) {
          findings.push({ severity: 'HIGH', viewport: vp.name, issue: `Fake title matched ${re}` });
        }
      }
      const hasReal = /Inception|Interstellar|Luca|Star Wars|Finding Nemo/i.test(homeText);
      if (!hasReal) {
        findings.push({ severity: 'HIGH', viewport: vp.name, issue: 'Expected TMDB titles missing on home' });
        row.notes.push('missing TMDB titles');
      }
      // Hero backdrop should not be a flat random color placeholder card only.
      const heroImg = page.locator('img').first();
      if (await heroImg.count()) {
        const src = (await heroImg.getAttribute('src')) || '';
        if (src && !src.includes('/artwork/') && !src.startsWith('data:')) {
          row.notes.push(`hero_src=${src.slice(0, 80)}`);
        }
      }
      const homeShot = path.join(OUT_DIR, `${LABEL}_home_${vp.name}.png`);
      await page.screenshot({ path: homeShot, fullPage: false });
      row.home = homeShot;

      // Movie detail with demo clip
      await page.goto(`${BASE_URL}/movie/inception`, { waitUntil: 'networkidle', timeout: 60000 });
      await page.waitForTimeout(1000);
      const movieText = await collectText(page);
      const hasDemoCta = /Play Demo Clip/i.test(movieText);
      const hasFullMovie = /Watch Full Movie/i.test(movieText);
      const hasTrailer = /Watch Trailer/i.test(movieText);
      if (!hasDemoCta) {
        findings.push({ severity: 'HIGH', viewport: vp.name, issue: 'Inception missing Play Demo Clip' });
      }
      if (hasFullMovie) {
        findings.push({ severity: 'HIGH', viewport: vp.name, issue: 'Inception shows Watch Full Movie for demo clip' });
      }
      row.notes.push(`demoCta=${hasDemoCta}`, `fullMovie=${hasFullMovie}`, `trailer=${hasTrailer}`);
      const movieShot = path.join(OUT_DIR, `${LABEL}_movie_inception_${vp.name}.png`);
      await page.screenshot({ path: movieShot, fullPage: false });
      row.movie = movieShot;

      // Trailer-only published title
      await page.goto(`${BASE_URL}/movie/fight-club`, { waitUntil: 'networkidle', timeout: 60000 });
      await page.waitForTimeout(800);
      const fightText = await collectText(page);
      if (!/Watch Trailer|Full Movie Unavailable/i.test(fightText)) {
        findings.push({
          severity: 'MEDIUM',
          viewport: vp.name,
          issue: 'Fight Club missing trailer/unavailable CTA',
        });
      }
      if (/Watch Full Movie/i.test(fightText)) {
        findings.push({ severity: 'HIGH', viewport: vp.name, issue: 'Fight Club shows Watch Full Movie' });
      }
      const fightShot = path.join(OUT_DIR, `${LABEL}_movie_fight-club_${vp.name}.png`);
      await page.screenshot({ path: fightShot, fullPage: false });
      row.notes.push(`fightTrailer=${/Watch Trailer/i.test(fightText)}`);
    } catch (err) {
      findings.push({ severity: 'BLOCKER', viewport: vp.name, issue: String(err) });
      row.notes.push(`error=${err}`);
    }

    results.push(row);
    await context.close();
  }

  await browser.close();
  const report = { label: LABEL, baseUrl: BASE_URL, results, findings };
  const reportPath = path.join(OUT_DIR, `${LABEL}_report.json`);
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
  const blockers = findings.filter((f) => f.severity === 'BLOCKER' || f.severity === 'HIGH');
  process.exit(blockers.length ? 1 : 0);
}

run().catch((err) => {
  console.error(err);
  process.exit(2);
});
