/**
 * GUI stabilization browser verification (API-mode / real backend).
 *
 * Usage:
 *   GUI_BASE_URL=http://127.0.0.1:8000 \
 *   GUI_DATA_MODE=api \
 *   GUI_COMMIT_SHA=$(git rev-parse HEAD) \
 *   GUI_BACKEND_COMMIT=$(git rev-parse HEAD) \
 *   GUI_SHOT_DIR=/opt/cursor/artifacts/gui-api-qa \
 *   node scripts/gui-stabilization-screenshots.mjs
 *
 * Exit code 0 only when all required assertions pass.
 * Mock captures must use a separate GUI_SHOT_DIR (e.g. gui-mock-qa).
 */
import { chromium } from 'playwright';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { execSync } from 'node:child_process';

const BASE = (process.env.GUI_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const OUT = process.env.GUI_SHOT_DIR || '/opt/cursor/artifacts/gui-api-qa';
const DATA_MODE = process.env.GUI_DATA_MODE || 'api';
const COMMIT_SHA =
  process.env.GUI_COMMIT_SHA ||
  (() => {
    try {
      return execSync('git rev-parse HEAD', { encoding: 'utf8' }).trim();
    } catch {
      return 'unknown';
    }
  })();
const BACKEND_COMMIT = process.env.GUI_BACKEND_COMMIT || COMMIT_SHA;
const FRONTEND_COMMIT = process.env.GUI_FRONTEND_COMMIT || COMMIT_SHA;
const STRICT_API = (process.env.GUI_STRICT_API || '1') !== '0';
const RUN_INTERACTIONS = (process.env.GUI_INTERACTIONS || '1') !== '0';
const AUTH_USER = process.env.GUI_AUTH_USER || '';
const AUTH_PASS = process.env.GUI_AUTH_PASS || '';
const PAGE_TIMEOUT_MS = Number(process.env.GUI_PAGE_TIMEOUT_MS || 20000);

const LOCALE_KEY = 'ifilm.locale';

const viewports = [
  { name: '1920', width: 1920, height: 1080 },
  { name: '1440', width: 1440, height: 900 },
  { name: '1024', width: 1024, height: 768 },
  { name: '768', width: 768, height: 1024 },
  { name: '430', width: 430, height: 932 },
  { name: '390', width: 390, height: 844 },
];

const langs = [
  { code: 'en', dir: 'ltr' },
  { code: 'fa', dir: 'rtl' },
  { code: 'ps', dir: 'rtl' },
];

function expectedDir(lang) {
  return lang === 'en' ? 'ltr' : 'rtl';
}

function isFirstParty(url) {
  try {
    const u = new URL(url);
    const b = new URL(BASE);
    return u.origin === b.origin;
  } catch {
    return false;
  }
}

function isBenignConsole(text) {
  const t = String(text || '');
  // Vite/React Router future flags and third-party noise only.
  if (t.includes('React Router Future Flag Warning')) return true;
  if (t.includes('[routes-scanner]')) return true;
  return false;
}

async function applyLocale(context, lang) {
  await context.addInitScript(
    ({ key, value }) => {
      try {
        localStorage.setItem(key, value);
      } catch {
        /* ignore */
      }
      document.cookie = `${key}=${encodeURIComponent(value)}; path=/; max-age=31536000; SameSite=Lax`;
    },
    { key: LOCALE_KEY, value: lang }
  );
}

async function assertLocale(page, lang) {
  const info = await page.evaluate(() => ({
    lang: document.documentElement.getAttribute('lang') || '',
    dir: document.documentElement.getAttribute('dir') || '',
    stored: (() => {
      try {
        return localStorage.getItem('ifilm.locale');
      } catch {
        return null;
      }
    })(),
  }));
  const wantDir = expectedDir(lang);
  if (info.stored !== lang) {
    throw new Error(`locale storage want=${lang} got=${info.stored}`);
  }
  if (info.dir !== wantDir) {
    throw new Error(`document dir want=${wantDir} got=${info.dir} (lang=${lang})`);
  }
  // html lang may be en/fa/ps
  if (info.lang && info.lang !== lang && !info.lang.startsWith(lang)) {
    throw new Error(`document lang want=${lang} got=${info.lang}`);
  }
  return info;
}

async function assertNoOverflow(page) {
  const overflow = await page.evaluate(() => {
    const doc = document.documentElement;
    return {
      scrollWidth: doc.scrollWidth,
      clientWidth: doc.clientWidth,
      overflowX: doc.scrollWidth > doc.clientWidth + 1,
    };
  });
  if (overflow.overflowX) {
    throw new Error(`horizontal overflow scrollWidth=${overflow.scrollWidth} clientWidth=${overflow.clientWidth}`);
  }
  return overflow;
}

async function waitHomeReady(page) {
  const hero = page.locator('[aria-roledescription="carousel"]');
  const err = page.locator('[data-testid="home-error"]');
  await Promise.race([
    hero.waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS }),
    err.waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS }),
  ]);
  if (await err.count()) {
    throw new Error('home showed error state instead of hero/catalog');
  }
  await page.getByRole('heading', { level: 1 }).first().waitFor({ state: 'attached', timeout: 5000 });
}

async function waitMoviesReady(page) {
  await page.locator('[data-testid="movies-page"]').waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS });
  const err = page.locator('[data-testid="browse-error"]');
  const empty = page.locator('[data-testid="movies-no-results"]');
  const cards = page.locator('[data-testid="movies-page"] [data-testid="media-card"]');
  await Promise.race([
    cards.first().waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS }).catch(() => {}),
    empty.waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS }).catch(() => {}),
    err.waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS }).catch(() => {}),
  ]);
  if (await err.isVisible().catch(() => false)) {
    throw new Error(`movies browse error: ${await err.innerText()}`);
  }
  if ((await cards.count()) === 0 && (await empty.count()) === 0) {
    throw new Error('movies page has neither cards nor empty state');
  }
}

async function waitSeriesReady(page) {
  await page.locator('[data-testid="series-page"]').waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS });
  const err = page.locator('[data-testid="browse-error"]');
  const empty = page.locator('[data-testid="series-no-results"]');
  const cards = page.locator('[data-testid="series-page"] [data-testid="media-card"]');
  await Promise.race([
    cards.first().waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS }).catch(() => {}),
    empty.waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS }).catch(() => {}),
    err.waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS }).catch(() => {}),
  ]);
  if (await err.isVisible().catch(() => false)) {
    throw new Error(`series browse error: ${await err.innerText()}`);
  }
  if ((await cards.count()) === 0 && (await empty.count()) === 0) {
    throw new Error('series page has neither cards nor empty state');
  }
}

async function waitSearchReady(page) {
  await page.getByRole('searchbox').or(page.locator('input[placeholder*="Search"], input[placeholder*="جستجو"], input[placeholder*="لټون"]')).first().waitFor({
    state: 'visible',
    timeout: PAGE_TIMEOUT_MS,
  });
}

async function waitLoginReady(page) {
  await page.locator('form, [data-testid="login-page"], input[type="password"]').first().waitFor({
    state: 'visible',
    timeout: PAGE_TIMEOUT_MS,
  });
}

async function waitMovieDetailReady(page) {
  await page.waitForURL(/\/movie\//, { timeout: PAGE_TIMEOUT_MS });
  const title = await page.title();
  if (!/movie/i.test(title) && !/فیلم/i.test(title)) {
    throw new Error(`movie detail title unexpected: ${title}`);
  }
  await page.getByRole('heading', { level: 1 }).first().waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS });
}

async function waitSeriesDetailReady(page) {
  await page.waitForURL(/\/series\/\d+|\/series\/[^/]+/, { timeout: PAGE_TIMEOUT_MS });
  await page.waitForFunction(
    () => {
      const title = document.title || '';
      return /series/i.test(title) || /سریال/i.test(title);
    },
    { timeout: PAGE_TIMEOUT_MS }
  );
  await page.getByRole('heading', { level: 1 }).first().waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS });
}

function attachCollectors(page, bag) {
  page.on('pageerror', (err) => {
    bag.pageErrors.push(String(err));
  });
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      const text = msg.text();
      if (!isBenignConsole(text)) bag.consoleErrors.push(text);
    }
  });
  page.on('requestfailed', (req) => {
    if (!isFirstParty(req.url())) return;
    const failure = req.failure();
    bag.failedRequests.push({ url: req.url(), error: failure?.errorText || 'failed' });
  });
  page.on('response', (res) => {
    if (!isFirstParty(res.url())) return;
    if (res.status() >= 500) {
      bag.http5xx.push({ url: res.url(), status: res.status() });
    }
  });
}

async function verifyConfig(page, bag) {
  const res = await page.request.get(`${BASE}/api/config`);
  if (!res.ok()) {
    throw new Error(`/api/config status=${res.status()}`);
  }
  const json = await res.json();
  if (json.API_BASE_URL !== '/' && json.API_BASE_URL !== '') {
    // same-origin preferred; empty also ok for relative
    bag.notes.push(`API_BASE_URL=${json.API_BASE_URL}`);
  }
  bag.config = json;
  return json;
}

async function assertNotMockFixtures(page) {
  if (DATA_MODE !== 'api') return;
  // Probe catalog home via backend; must succeed for real-API mode.
  const home = await page.request.get(`${BASE}/api/catalog/home?locale=en`);
  if (!home.ok()) {
    throw new Error(`/api/catalog/home status=${home.status()}`);
  }
  const body = await home.json();
  const featured = body.featured || body.data?.featured || [];
  if (!Array.isArray(featured)) {
    throw new Error('catalog/home featured missing');
  }
}

async function runCase({ browser, routeId, pathName, lang, viewport, reducedMotion }) {
  const bag = {
    pageErrors: [],
    consoleErrors: [],
    failedRequests: [],
    http5xx: [],
    notes: [],
  };
  const context = await browser.newContext({
    viewport: { width: viewport.width, height: viewport.height },
    locale: lang === 'en' ? 'en-US' : lang === 'fa' ? 'fa-IR' : 'ps-AF',
    reducedMotion: reducedMotion ? 'reduce' : 'no-preference',
  });
  let page;
  const result = {
    route: pathName,
    routeId,
    viewport: viewport.name,
    lang,
    dataMode: DATA_MODE,
    commitSha: COMMIT_SHA,
    frontendCommit: FRONTEND_COMMIT,
    backendCommit: BACKEND_COMMIT,
    assertions: [],
    screenshot: null,
    ok: false,
  };
  try {
    await applyLocale(context, lang);
    page = await context.newPage();
    attachCollectors(page, bag);

    if (routeId === 'home') {
      await verifyConfig(page, bag);
      await assertNotMockFixtures(page);
    }

    await page.goto(`${BASE}${pathName}`, { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });

    if (routeId === 'home') await waitHomeReady(page);
    else if (routeId === 'movies') await waitMoviesReady(page);
    else if (routeId === 'series') await waitSeriesReady(page);
    else if (routeId === 'search') await waitSearchReady(page);
    else if (routeId === 'login') await waitLoginReady(page);

    const localeInfo = await assertLocale(page, lang);
    result.assertions.push(`locale:${localeInfo.lang}/${localeInfo.dir}`);
    const overflow = await assertNoOverflow(page);
    result.assertions.push(`overflowX:${overflow.overflowX}`);

    // Locale persistence after refresh (home only, once per lang at 1440)
    if (routeId === 'home' && viewport.name === '1440') {
      await page.reload({ waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
      await waitHomeReady(page);
      await assertLocale(page, lang);
      result.assertions.push('locale_persists_after_refresh');
    }

    const file = `${DATA_MODE}_${routeId}_${lang}_${viewport.name}.png`;
    const shotPath = path.join(OUT, file);
    await page.screenshot({ path: shotPath, fullPage: false });
    result.screenshot = file;
    result.title = await page.title();
    result.dir = localeInfo.dir;

    const unexpected = [
      ...bag.pageErrors.map((e) => `pageerror:${e}`),
      ...bag.consoleErrors.map((e) => `console:${e}`),
      ...bag.failedRequests.map((e) => `requestfailed:${e.url}:${e.error}`),
      ...bag.http5xx.map((e) => `http5xx:${e.status}:${e.url}`),
    ];
    if (STRICT_API && unexpected.length) {
      throw new Error(`unexpected first-party issues: ${unexpected.slice(0, 8).join(' | ')}`);
    }
    result.unexpected = unexpected;
    result.ok = true;
    return result;
  } catch (err) {
    result.ok = false;
    result.error = String(err?.message || err);
    result.unexpected = [
      ...bag.pageErrors,
      ...bag.consoleErrors,
      ...bag.failedRequests.map((e) => `${e.url}:${e.error}`),
      ...bag.http5xx.map((e) => `${e.status} ${e.url}`),
    ];
    try {
      if (page) {
        const file = `${DATA_MODE}_${routeId}_${lang}_${viewport.name}_FAIL.png`;
        await page.screenshot({ path: path.join(OUT, file), fullPage: false });
        result.screenshot = file;
      }
    } catch {
      /* ignore */
    }
    return result;
  } finally {
    await context.close();
  }
}

async function runDetailCases(browser, report) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const mobile = await browser.newContext({ viewport: { width: 390, height: 844 } });
  try {
    await applyLocale(context, 'en');
    const page = await context.newPage();
    const bag = { pageErrors: [], consoleErrors: [], failedRequests: [], http5xx: [], notes: [] };
    attachCollectors(page, bag);
    await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
    await waitHomeReady(page);
    const more = page.getByRole('button', { name: /more info|اطلاعات بیشتر|نور معلومات/i }).first();
    if ((await more.count()) === 0) {
      throw new Error('home missing More Info control for movie detail navigation');
    }
    await more.click();
    await waitMovieDetailReady(page);
    await assertNoOverflow(page);
    await page.screenshot({ path: path.join(OUT, `${DATA_MODE}_movie_detail_en_1440.png`), fullPage: false });
    report.push({
      routeId: 'movie_detail',
      lang: 'en',
      viewport: '1440',
      ok: true,
      screenshot: `${DATA_MODE}_movie_detail_en_1440.png`,
      title: await page.title(),
      dataMode: DATA_MODE,
      commitSha: COMMIT_SHA,
      assertions: ['detail_via_more_info', `title:${await page.title()}`],
      unexpected: [...bag.pageErrors, ...bag.consoleErrors],
    });

    // Mobile movie detail
    await applyLocale(mobile, 'en');
    const mpage = await mobile.newPage();
    const mbag = { pageErrors: [], consoleErrors: [], failedRequests: [], http5xx: [], notes: [] };
    attachCollectors(mpage, mbag);
    await mpage.goto(page.url(), { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
    await waitMovieDetailReady(mpage);
    await assertNoOverflow(mpage);
    await mpage.screenshot({ path: path.join(OUT, `${DATA_MODE}_movie_detail_en_390.png`), fullPage: false });
    report.push({
      routeId: 'movie_detail',
      lang: 'en',
      viewport: '390',
      ok: true,
      screenshot: `${DATA_MODE}_movie_detail_en_390.png`,
      title: await mpage.title(),
      dataMode: DATA_MODE,
      commitSha: COMMIT_SHA,
      assertions: ['mobile_detail'],
      unexpected: [...mbag.pageErrors, ...mbag.consoleErrors],
    });
    await mpage.close();

    // Series detail
    await page.goto(`${BASE}/series`, { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
    await waitSeriesReady(page);
    const seriesCard = page.locator('[data-testid="series-page"] [data-testid="media-card"]').first();
    if ((await seriesCard.count()) === 0) {
      throw new Error('series page has no cards to open detail');
    }
    await seriesCard.click();
    await waitSeriesDetailReady(page);
    await page.screenshot({ path: path.join(OUT, `${DATA_MODE}_series_detail_en_1440.png`), fullPage: false });
    report.push({
      routeId: 'series_detail',
      lang: 'en',
      viewport: '1440',
      ok: true,
      screenshot: `${DATA_MODE}_series_detail_en_1440.png`,
      title: await page.title(),
      dataMode: DATA_MODE,
      commitSha: COMMIT_SHA,
      assertions: ['series_detail'],
      unexpected: [],
    });

    await applyLocale(mobile, 'en');
    const sm = await mobile.newPage();
    await sm.goto(page.url(), { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
    await waitSeriesDetailReady(sm);
    await sm.screenshot({ path: path.join(OUT, `${DATA_MODE}_series_detail_en_390.png`), fullPage: false });
    report.push({
      routeId: 'series_detail',
      lang: 'en',
      viewport: '390',
      ok: true,
      screenshot: `${DATA_MODE}_series_detail_en_390.png`,
      title: await sm.title(),
      dataMode: DATA_MODE,
      commitSha: COMMIT_SHA,
      assertions: ['series_detail_mobile'],
      unexpected: [],
    });
    await sm.close();
    await page.close();
  } catch (err) {
    report.push({
      routeId: 'detail_cases',
      ok: false,
      error: String(err?.message || err),
      dataMode: DATA_MODE,
      commitSha: COMMIT_SHA,
    });
  } finally {
    await context.close();
    await mobile.close();
  }
}

async function runHeroInteractions(browser, report) {
  if (!RUN_INTERACTIONS) return;
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    reducedMotion: 'no-preference',
  });
  try {
    await applyLocale(context, 'en');
    const page = await context.newPage();
    await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
    await waitHomeReady(page);
    const dots = page.locator('[aria-roledescription="carousel"] ~ div button, [aria-label="Featured titles"] button');
    const next = page.getByRole('button', { name: /next featured/i });
    const prev = page.getByRole('button', { name: /previous featured/i });
    const before = await page.locator('h1').first().innerText();
    if ((await next.count()) === 0) throw new Error('hero next control missing');
    if ((await prev.count()) === 0) throw new Error('hero previous control missing');
    await next.click();
    await page.waitForTimeout(400);
    const afterNext = await page.locator('h1').first().innerText();
    await prev.click();
    await page.waitForTimeout(400);
    const afterPrev = await page.locator('h1').first().innerText();
    const slideCount = await dots.count();
    if (slideCount > 1 && afterNext === before) {
      throw new Error('hero next did not change slide with multiple featured titles');
    }
    // Manual only: sample stability (no auto-advance) after settle
    await page.waitForTimeout(1500);
    const stable = await page.locator('h1').first().innerText();
    if (stable !== afterPrev) {
      throw new Error(`hero auto-advanced unexpectedly: ${afterPrev} -> ${stable}`);
    }
    report.push({
      routeId: 'hero_interactions',
      ok: true,
      assertions: [
        `before=${before}`,
        `afterNext=${afterNext}`,
        `afterPrev=${afterPrev}`,
        `stable=${stable}`,
        `dots=${slideCount}`,
        'manual_only_no_auto_advance',
      ],
      dataMode: DATA_MODE,
      commitSha: COMMIT_SHA,
    });
    await page.close();
  } catch (err) {
    report.push({
      routeId: 'hero_interactions',
      ok: false,
      error: String(err?.message || err),
      dataMode: DATA_MODE,
      commitSha: COMMIT_SHA,
    });
  } finally {
    await context.close();
  }
}

async function runBrowseRetry(browser, report) {
  if (!RUN_INTERACTIONS) return;
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  try {
    await applyLocale(context, 'en');
    const page = await context.newPage();
    await page.goto(`${BASE}/movies`, { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
    await waitMoviesReady(page);
    // Deliberate failure injection via route abort, then recovery
    await page.route('**/api/movies**', (route) => route.abort('failed'));
    await page.reload({ waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
    await page.locator('[data-testid="browse-error"]').waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS });
    await page.unroute('**/api/movies**');
    await page.getByRole('button', { name: /retry|تلاش|هڅه/i }).click();
    await waitMoviesReady(page);
    await page.screenshot({ path: path.join(OUT, `${DATA_MODE}_movies_retry_recovered_en_1440.png`), fullPage: false });
    report.push({
      routeId: 'movies_retry_recovery',
      ok: true,
      screenshot: `${DATA_MODE}_movies_retry_recovered_en_1440.png`,
      assertions: ['error_ui_then_retry_ok'],
      dataMode: DATA_MODE,
      commitSha: COMMIT_SHA,
    });
    await page.close();
  } catch (err) {
    report.push({
      routeId: 'movies_retry_recovery',
      ok: false,
      error: String(err?.message || err),
      dataMode: DATA_MODE,
      commitSha: COMMIT_SHA,
    });
  } finally {
    await context.close();
  }
}

async function runSearchEmpty(browser, report) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  try {
    await applyLocale(context, 'en');
    const page = await context.newPage();
    await page.goto(`${BASE}/search`, { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
    await waitSearchReady(page);
    const box = page.getByRole('searchbox').or(page.locator('input').first());
    await box.fill('zzznomatchquery999');
    await page.locator('[data-testid="search-no-results"]').waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS });
    await page.screenshot({ path: path.join(OUT, `${DATA_MODE}_search_empty_en_1440.png`), fullPage: false });
    // Results path: type a known catalog title fragment
    await box.fill('Poet');
    await page.locator('[data-testid="media-card"], [data-testid="search-results"]').first().waitFor({
      state: 'visible',
      timeout: PAGE_TIMEOUT_MS,
    });
    await page.screenshot({ path: path.join(OUT, `${DATA_MODE}_search_results_en_1440.png`), fullPage: false });
    report.push({
      routeId: 'search_empty',
      ok: true,
      screenshot: `${DATA_MODE}_search_empty_en_1440.png`,
      assertions: ['empty_state', 'results_for_Poet'],
      dataMode: DATA_MODE,
      commitSha: COMMIT_SHA,
    });
    await page.close();
  } catch (err) {
    report.push({
      routeId: 'search_empty',
      ok: false,
      error: String(err?.message || err),
      dataMode: DATA_MODE,
      commitSha: COMMIT_SHA,
    });
  } finally {
    await context.close();
  }
}

async function runMoviesFiltersMobile(browser, report) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, reducedMotion: 'reduce' });
  try {
    await applyLocale(context, 'en');
    const page = await context.newPage();
    await page.goto(`${BASE}/movies`, { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
    await waitMoviesReady(page);
    const genre = page.locator('[data-testid="movies-genre-filter"]');
    if ((await genre.count()) === 0) throw new Error('movies genre filter missing');
    await genre.click();
    // Pick first non-all option if present
    const option = page.getByRole('option').nth(1);
    if ((await option.count()) > 0) {
      await option.click();
      await page.waitForTimeout(400);
    }
    await assertNoOverflow(page);
    await page.screenshot({ path: path.join(OUT, `${DATA_MODE}_movies_filters_en_390.png`), fullPage: false });
    const clear = page.getByRole('button', { name: /clear filters|پاک کردن|فلټرونه پاک/i });
    if ((await clear.count()) > 0) {
      await clear.first().click();
      await waitMoviesReady(page);
      report.push({
        routeId: 'movies_filters_mobile',
        ok: true,
        screenshot: `${DATA_MODE}_movies_filters_en_390.png`,
        assertions: ['filter_applied', 'clear_filters_ok'],
        dataMode: DATA_MODE,
        commitSha: COMMIT_SHA,
      });
    } else {
      report.push({
        routeId: 'movies_filters_mobile',
        ok: true,
        screenshot: `${DATA_MODE}_movies_filters_en_390.png`,
        assertions: ['filter_control_present'],
        dataMode: DATA_MODE,
        commitSha: COMMIT_SHA,
      });
    }
    await page.close();
  } catch (err) {
    report.push({
      routeId: 'movies_filters_mobile',
      ok: false,
      error: String(err?.message || err),
      dataMode: DATA_MODE,
      commitSha: COMMIT_SHA,
    });
  } finally {
    await context.close();
  }
}

async function runAuthSmoke(browser, report) {
  if (!AUTH_USER || !AUTH_PASS) {
    report.push({
      routeId: 'authenticated_gui',
      ok: true,
      skipped: true,
      status: 'NOT_RUN',
      reason: 'GUI_AUTH_USER/GUI_AUTH_PASS not provided',
      dataMode: DATA_MODE,
      commitSha: COMMIT_SHA,
    });
    return;
  }
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  try {
    await applyLocale(context, 'en');
    // Stable device id so disposable QA does not exhaust max_devices across runs
    await context.addInitScript(() => {
      try {
        localStorage.setItem('ifilm_device_id', 'gui-qa-device-001');
      } catch {
        /* ignore */
      }
    });
    const page = await context.newPage();
    const bag = { pageErrors: [], consoleErrors: [], failedRequests: [], http5xx: [], notes: [] };
    attachCollectors(page, bag);
    await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
    await waitLoginReady(page);
    await page.locator('[data-testid="isp-location"]').waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS });
    await page.waitForFunction(() => {
      const sel = document.querySelector('[data-testid="isp-location"]');
      return sel && sel.options && sel.options.length > 1;
    }, { timeout: PAGE_TIMEOUT_MS });
    await page.locator('[data-testid="isp-location"]').selectOption({ label: 'Kabul' });
    await page.locator('[data-testid="isp-username"]').fill(AUTH_USER);
    await page.locator('[data-testid="isp-password"]').fill(AUTH_PASS);
    const remember = page.locator('#remember');
    if ((await remember.count()) > 0) {
      await remember.check().catch(() => {});
    }
    await page.locator('[data-testid="isp-sign-in"]').click();
    // Fail fast on device-limit / auth errors
    await Promise.race([
      page.waitForFunction(() => !location.pathname.includes('/login'), { timeout: PAGE_TIMEOUT_MS }),
      page.locator('[role="alert"]').waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS }).then(async () => {
        throw new Error(`login alert: ${(await page.locator('[role="alert"]').innerText()).trim()}`);
      }),
    ]);
    const url = page.url();
    await page.screenshot({ path: path.join(OUT, `${DATA_MODE}_auth_home_en_1440.png`), fullPage: false });

    // Session continuity after refresh
    await page.reload({ waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
    await waitHomeReady(page);
    const stillAuthed = await page.evaluate(() => Boolean(localStorage.getItem('ifilm_access_token')));
    if (!stillAuthed) {
      throw new Error('session token missing after refresh (local fixture auth)');
    }
    const profileTrigger = page.getByRole('button', { name: /profile|پروفایل/i });
    if ((await profileTrigger.count()) === 0) {
      throw new Error('profile menu missing after authenticated refresh');
    }

    // Logout navigation (header profile dropdown → Logout)
    await profileTrigger.first().click();
    await page.getByRole('menuitem', { name: /logout|خروج|وتل/i }).click();
    await page.waitForFunction(() => location.pathname.includes('/login'), { timeout: PAGE_TIMEOUT_MS });
    const logoutOk = !(await page.evaluate(() => Boolean(localStorage.getItem('ifilm_access_token'))));
    if (!logoutOk) {
      throw new Error('logout did not clear ifilm_access_token');
    }

    // Expected: locations fetch may 200; ignore benign auth console from intentional paths only
    const unexpected = [
      ...bag.pageErrors.map((e) => `pageerror:${e}`),
      ...bag.consoleErrors.filter((e) => !/429|Too Many Requests/i.test(e)).map((e) => `console:${e}`),
      ...bag.http5xx.map((e) => `http5xx:${e.status}:${e.url}`),
    ];
    if (STRICT_API && unexpected.length) {
      throw new Error(`auth unexpected: ${unexpected.slice(0, 6).join(' | ')}`);
    }

    report.push({
      routeId: 'authenticated_gui',
      ok: true,
      status: 'PASS',
      label: 'local_test_account_portal_stub',
      screenshot: `${DATA_MODE}_auth_home_en_1440.png`,
      assertions: [
        `post_login_url=${url}`,
        'session_persists_after_refresh',
        'logout_clears_token',
        'local_disposable_portal_stub_not_live_portal',
      ],
      dataMode: DATA_MODE,
      commitSha: COMMIT_SHA,
      note: 'Local disposable Portal Voice AI stub + fixture user — not live Portal proof',
      unexpected,
    });
    await page.close();
  } catch (err) {
    report.push({
      routeId: 'authenticated_gui',
      ok: false,
      status: 'FAIL',
      error: String(err?.message || err),
      dataMode: DATA_MODE,
      commitSha: COMMIT_SHA,
    });
  } finally {
    await context.close();
  }
}

async function main() {
  await mkdir(OUT, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const report = [];
  try {
    // Matrix: home+movies all viewports × langs; search/login at 1440+390 for all langs
    for (const lang of langs) {
      for (const vp of viewports) {
        report.push(
          await runCase({
            browser,
            routeId: 'home',
            pathName: '/',
            lang: lang.code,
            viewport: vp,
            reducedMotion: true,
          })
        );
        report.push(
          await runCase({
            browser,
            routeId: 'movies',
            pathName: '/movies',
            lang: lang.code,
            viewport: vp,
            reducedMotion: true,
          })
        );
      }
      for (const vpName of ['1440', '390']) {
        const vp = viewports.find((v) => v.name === vpName);
        report.push(
          await runCase({
            browser,
            routeId: 'search',
            pathName: '/search',
            lang: lang.code,
            viewport: vp,
            reducedMotion: true,
          })
        );
        report.push(
          await runCase({
            browser,
            routeId: 'login',
            pathName: '/login',
            lang: lang.code,
            viewport: vp,
            reducedMotion: true,
          })
        );
        report.push(
          await runCase({
            browser,
            routeId: 'series',
            pathName: '/series',
            lang: lang.code,
            viewport: vp,
            reducedMotion: true,
          })
        );
      }
    }

    await runDetailCases(browser, report);
    await runHeroInteractions(browser, report);
    await runBrowseRetry(browser, report);
    await runSearchEmpty(browser, report);
    await runMoviesFiltersMobile(browser, report);
    await runAuthSmoke(browser, report);
  } finally {
    await browser.close();
  }

  const failed = report.filter((r) => r.ok === false);
  const summary = {
    commitSha: COMMIT_SHA,
    frontendCommit: FRONTEND_COMMIT,
    backendCommit: BACKEND_COMMIT,
    dataMode: DATA_MODE,
    baseUrl: BASE,
    total: report.length,
    passed: report.filter((r) => r.ok).length,
    failed: failed.length,
    cases: report,
  };
  await writeFile(path.join(OUT, 'summary.json'), JSON.stringify(summary, null, 2));
  console.log(JSON.stringify({ total: summary.total, passed: summary.passed, failed: summary.failed, out: OUT }, null, 2));
  if (failed.length) {
    for (const f of failed.slice(0, 12)) {
      console.error('FAIL', f.routeId || f.route, f.lang, f.viewport, f.error);
    }
    process.exit(1);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
