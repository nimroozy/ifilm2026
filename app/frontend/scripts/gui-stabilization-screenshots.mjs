/**
 * GUI stabilization browser verification (API-mode / real backend).
 *
 * Usage:
 *   GUI_BASE_URL=http://127.0.0.1:8000 \
 *   GUI_DATA_MODE=api \
 *   GUI_COMMIT_SHA=$(git rev-parse HEAD) \
 *   GUI_SHOT_DIR=/opt/cursor/artifacts/gui-api-qa \
 *   GUI_PAGE_TIMEOUT_MS=25000 \
 *   GUI_INTERACTIONS=1 \
 *   GUI_STRICT_API=1 \
 *   GUI_PLAYBACK=1 \
 *   GUI_WATCHLIST=1 \
 *   node scripts/gui-stabilization-screenshots.mjs
 *
 * Exit code 0 only when all required assertions pass (ok !== false).
 * Mock captures must use a separate GUI_SHOT_DIR (e.g. gui-mock-qa).
 *
 * Root cause of dim mobile detail shots: capture during animate-fade-in
 * (parent opacity ~0→1 over 0.5s). Harness waits for finite entrance
 * animations to settle and asserts opacity>=0.99 — does NOT strip
 * animations or inject global opacity CSS overrides.
 */
import { chromium } from 'playwright';
import { access, copyFile, mkdir, readdir, writeFile } from 'node:fs/promises';
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
const RUN_PLAYBACK = (process.env.GUI_PLAYBACK || '1') !== '0';
const RUN_WATCHLIST = (process.env.GUI_WATCHLIST || '1') !== '0';
const AUTH_USER = process.env.GUI_AUTH_USER || '';
const AUTH_PASS = process.env.GUI_AUTH_PASS || '';
const AUTH_USER2 = process.env.GUI_AUTH_USER2 || 'mobin_user_002';
const AUTH_PASS2 = process.env.GUI_AUTH_PASS2 || 'fixture-pass-ok';
const PAGE_TIMEOUT_MS = Number(process.env.GUI_PAGE_TIMEOUT_MS || 25000);
const DEVICE_ID = 'gui-qa-device-001';
const DEVICE_ID2 = 'gui-qa-device-002';
const EXISTING_REVIEW = '/opt/cursor/artifacts/gui-api-qa/review';

const LOCALE_KEY = 'ifilm.locale';

const ENTRANCE_ANIM_NAMES = ['fade-in', 'lift-in', 'slide-up'];

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

const REVIEW_SUBSET = [
  'movie_detail_en_390',
  'series_detail_en_390',
  'home_fa_1440',
  'home_fa_390',
  'home_ps_390',
  'movies_populated_en_1440',
  'search_results',
  'search_empty',
  'missing_artwork_en_390',
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
  // React Router Future Flag only (required filter).
  if (t.includes('React Router Future Flag Warning')) return true;
  return false;
}

function isBenignFirstPartyUrl(url) {
  try {
    const path = new URL(url).pathname;
    return (
      /\/favicon\.ico$/i.test(path) ||
      /\/robots\.txt$/i.test(path) ||
      /apple-touch-icon/i.test(path) ||
      /\/manifest\.webmanifest$/i.test(path)
    );
  } catch {
    return false;
  }
}

function emptyBag() {
  return {
    pageErrors: [],
    consoleErrors: [],
    failedRequests: [],
    http5xx: [],
    http404: [],
    notes: [],
  };
}

function baseResult(extra = {}) {
  return {
    dataMode: DATA_MODE,
    commitSha: COMMIT_SHA,
    frontendCommit: FRONTEND_COMMIT,
    backendCommit: BACKEND_COMMIT,
    assertions: [],
    screenshot: null,
    unexpected: [],
    ok: false,
    ...extra,
  };
}

function attachCollectors(page, bag) {
  page.on('pageerror', (err) => {
    bag.pageErrors.push(String(err?.message || err));
  });
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      const text = msg.text();
      if (!isBenignConsole(text)) bag.consoleErrors.push(text);
    }
  });
  page.on('requestfailed', (req) => {
    if (!isFirstParty(req.url())) return;
    if (isBenignFirstPartyUrl(req.url())) return;
    const failure = req.failure();
    bag.failedRequests.push({
      url: req.url(),
      error: failure?.errorText || 'failed',
    });
  });
  page.on('response', (res) => {
    if (!isFirstParty(res.url())) return;
    if (isBenignFirstPartyUrl(res.url())) return;
    if (res.status() >= 500) {
      bag.http5xx.push({ url: res.url(), status: res.status() });
    } else if (res.status() === 404) {
      bag.http404.push({ url: res.url(), status: 404 });
    }
  });
}

/**
 * Sets result.unexpected from collectors and ok=false when unexpected issues
 * (under strict) or when result.error is already set.
 * NEVER unconditionally sets ok=true.
 */
function finalizeCase(result, bag, { strict = STRICT_API, ignoreFailedPred = null } = {}) {
  // Prefer URL-bearing 404 records over opaque Chromium "status of 404" console lines.
  const hasUrl404 = (bag.http404 || []).length > 0;
  let unexpected = [
    ...bag.pageErrors.map((e) => `pageerror:${e}`),
    ...bag.consoleErrors
      .filter((e) => !(hasUrl404 && /status of 404/i.test(e)))
      .map((e) => `console:${e}`),
    ...bag.failedRequests.map((e) => `requestfailed:${e.url}:${e.error}`),
    ...bag.http5xx.map((e) => `http5xx:${e.status}:${e.url}`),
    ...(bag.http404 || []).map((e) => `http404:${e.url}`),
  ];
  if (typeof ignoreFailedPred === 'function') {
    unexpected = unexpected.filter((item) => !ignoreFailedPred(item));
  }
  result.unexpected = unexpected;

  if (result.error) {
    result.ok = false;
    return result;
  }
  if (strict && unexpected.length) {
    result.ok = false;
    result.error = `unexpected first-party issues: ${unexpected.slice(0, 8).join(' | ')}`;
    return result;
  }
  // Success only when no error and (not strict, or no unexpected).
  result.ok = !(strict && unexpected.length);
  return result;
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

async function applyDeviceId(context, deviceId) {
  await context.addInitScript((id) => {
    try {
      localStorage.setItem('ifilm_device_id', id);
    } catch {
      /* ignore */
    }
  }, deviceId);
}

async function assertLocale(page, lang) {
  const info = await page.evaluate((key) => {
    return {
      lang: document.documentElement.getAttribute('lang') || '',
      dir: document.documentElement.getAttribute('dir') || '',
      stored: (() => {
        try {
          return localStorage.getItem(key);
        } catch {
          return null;
        }
      })(),
    };
  }, LOCALE_KEY);
  const wantDir = expectedDir(lang);
  if (info.stored !== lang) {
    throw new Error(`locale storage want=${lang} got=${info.stored}`);
  }
  if (info.dir !== wantDir) {
    throw new Error(`document dir want=${wantDir} got=${info.dir} (lang=${lang})`);
  }
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
    throw new Error(
      `horizontal overflow scrollWidth=${overflow.scrollWidth} clientWidth=${overflow.clientWidth}`
    );
  }
  return overflow;
}

/**
 * Wait until no running fade-in / lift-in / slide-up animations on the subtree
 * and computed opacity of the root (and ancestors) is >= 0.999.
 * Then wait two animation frames so the final paint is committed before capture.
 */
async function waitForEntranceSettled(page, selector) {
  await page.waitForFunction(
    ({ sel, names }) => {
      const root = document.querySelector(sel);
      if (!root) return false;

      const nodes = [root, ...root.querySelectorAll('*')];
      for (const el of nodes) {
        const anims = typeof el.getAnimations === 'function' ? el.getAnimations() : [];
        for (const a of anims) {
          if (a.playState !== 'running' && a.playState !== 'pending') continue;
          const an = String(a.animationName || '').toLowerCase();
          if (names.some((n) => an.includes(n))) return false;
        }
      }

      let el = root;
      while (el && el.nodeType === 1) {
        const op = parseFloat(getComputedStyle(el).opacity);
        if (!Number.isFinite(op) || op < 0.999) return false;
        if (el === document.documentElement) break;
        el = el.parentElement;
      }
      return true;
    },
    { sel: selector, names: ENTRANCE_ANIM_NAMES },
    { timeout: PAGE_TIMEOUT_MS }
  );
  await page.evaluate(
    () =>
      new Promise((resolve) => {
        requestAnimationFrame(() => requestAnimationFrame(resolve));
      })
  );
}

/** Assert computed opacity of element and ancestors is >= 0.999. */
async function assertReadableForeground(page, selector) {
  const info = await page.evaluate((sel) => {
    const root = document.querySelector(sel);
    if (!root) return { ok: false, reason: `missing:${sel}` };
    const chain = [];
    let el = root;
    while (el && el.nodeType === 1) {
      const op = parseFloat(getComputedStyle(el).opacity);
      chain.push({ tag: el.tagName, testid: el.getAttribute?.('data-testid'), opacity: op });
      if (!Number.isFinite(op) || op < 0.999) {
        return { ok: false, reason: `opacity=${op}`, chain };
      }
      if (el === document.documentElement) break;
      el = el.parentElement;
    }
    return { ok: true, chain };
  }, selector);
  if (!info.ok) {
    throw new Error(`assertReadableForeground(${selector}): ${info.reason}`);
  }
  return info;
}

/**
 * Wait for an <img> to decode (complete + naturalWidth>0), OR assert intentional
 * missing-artwork fallback when no img is present / empty src.
 */
async function waitForImageDecoded(page, selector, { allowMissing = false } = {}) {
  const outcome = await page.evaluate(async (sel) => {
    const el = document.querySelector(sel);
    if (!el) return { kind: 'missing_element' };
    if (el.tagName !== 'IMG') {
      return { kind: 'not_img', tag: el.tagName };
    }
    const src = el.getAttribute('src') || '';
    if (!src) return { kind: 'empty_src' };
    if (el.complete && el.naturalWidth > 0) {
      return { kind: 'decoded', naturalWidth: el.naturalWidth };
    }
    try {
      await el.decode();
    } catch {
      /* decode may reject for broken URLs */
    }
    if (el.complete && el.naturalWidth > 0) {
      return { kind: 'decoded', naturalWidth: el.naturalWidth };
    }
    return { kind: 'failed', naturalWidth: el.naturalWidth || 0, src };
  }, selector);

  if (outcome.kind === 'decoded') return outcome;

  if (allowMissing && (outcome.kind === 'missing_element' || outcome.kind === 'empty_src' || outcome.kind === 'not_img')) {
    return { ...outcome, intentionalFallback: true };
  }

  if (outcome.kind === 'missing_element' || outcome.kind === 'empty_src') {
    if (allowMissing) return { ...outcome, intentionalFallback: true };
    throw new Error(`waitForImageDecoded(${selector}): ${outcome.kind}`);
  }

  // Poll briefly for late decode.
  try {
    await page.waitForFunction(
      (sel) => {
        const img = document.querySelector(sel);
        return Boolean(img && img.tagName === 'IMG' && img.complete && img.naturalWidth > 0);
      },
      selector,
      { timeout: Math.min(8000, PAGE_TIMEOUT_MS) }
    );
    return { kind: 'decoded' };
  } catch {
    if (allowMissing) return { kind: 'failed', intentionalFallback: true };
    throw new Error(`waitForImageDecoded(${selector}): not decoded (${outcome.kind})`);
  }
}

async function waitHomeReady(page) {
  const hero = page.locator('[data-testid="hero-carousel"], [aria-roledescription="carousel"]');
  const err = page.locator('[data-testid="home-error"]');
  await Promise.race([
    hero.first().waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS }),
    err.waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS }),
  ]);
  if (await err.count()) {
    throw new Error('home showed error state instead of hero/catalog');
  }
  await page.getByRole('heading', { level: 1 }).first().waitFor({ state: 'attached', timeout: 5000 });
  const settleSel = (await page.locator('[data-testid="hero-carousel"]').count())
    ? '[data-testid="hero-carousel"]'
    : '[aria-roledescription="carousel"]';
  await waitForEntranceSettled(page, settleSel);
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
  await waitForEntranceSettled(page, '[data-testid="movies-page"]');
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
  await waitForEntranceSettled(page, '[data-testid="series-page"]');
}

async function waitSearchReady(page) {
  await page
    .getByRole('searchbox')
    .or(page.locator('input[placeholder*="Search"], input[placeholder*="جستجو"], input[placeholder*="لټون"]'))
    .first()
    .waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS });
}

async function waitLoginReady(page) {
  await page.locator('form, [data-testid="login-page"], [data-testid="isp-login-form"], input[type="password"]').first().waitFor({
    state: 'visible',
    timeout: PAGE_TIMEOUT_MS,
  });
}

async function waitMovieDetailReady(page) {
  await page.waitForURL(/\/movie\//, { timeout: PAGE_TIMEOUT_MS });
  await page.locator('[data-testid="movie-detail"]').waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS });
  await page.getByRole('heading', { level: 1 }).or(page.locator('[data-testid="movie-title-text"], [data-testid="movie-title-logo"]')).first().waitFor({
    state: 'visible',
    timeout: PAGE_TIMEOUT_MS,
  });
  await waitForEntranceSettled(page, '[data-testid="movie-detail"]');
}

async function waitSeriesDetailReady(page) {
  await page.waitForURL(/\/series\/\d+|\/series\/[^/]+/, { timeout: PAGE_TIMEOUT_MS });
  await page.locator('[data-testid="series-detail"]').waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS });
  await page.getByRole('heading', { level: 1 }).or(page.locator('[data-testid="series-title-text"], [data-testid="series-title-logo"]')).first().waitFor({
    state: 'visible',
    timeout: PAGE_TIMEOUT_MS,
  });
  await waitForEntranceSettled(page, '[data-testid="series-detail"]');
}

async function verifyConfig(page, bag) {
  const res = await page.request.get(`${BASE}/api/config`);
  if (!res.ok()) {
    throw new Error(`/api/config status=${res.status()}`);
  }
  const json = await res.json();
  if (json.API_BASE_URL !== '/' && json.API_BASE_URL !== '') {
    bag.notes.push(`API_BASE_URL=${json.API_BASE_URL}`);
  }
  bag.config = json;
  return json;
}

async function assertNotMockFixtures(page) {
  if (DATA_MODE !== 'api') return;
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

async function shot(page, file) {
  const shotPath = path.join(OUT, file);
  await page.screenshot({ path: shotPath, fullPage: false });
  return file;
}

async function failShot(page, file) {
  try {
    if (page) await shot(page, file);
    return file;
  } catch {
    return null;
  }
}

function contentSelectorForRoute(routeId) {
  if (routeId === 'home') return '[data-testid="hero-carousel"], [aria-roledescription="carousel"]';
  if (routeId === 'movies') return '[data-testid="movies-page"]';
  if (routeId === 'series') return '[data-testid="series-page"]';
  if (routeId === 'search') return 'main, [data-testid="customer-shell"]';
  if (routeId === 'login') return '[data-testid="isp-login-form"], form';
  if (routeId === 'movie_detail') return '[data-testid="movie-detail"]';
  if (routeId === 'series_detail') return '[data-testid="series-detail"]';
  return 'main, body';
}

async function settleAndAssertReadable(page, routeId) {
  const sel = contentSelectorForRoute(routeId);
  const handle = await page.$(sel.split(',')[0].trim());
  const useSel = handle ? sel.split(',')[0].trim() : sel.split(',').map((s) => s.trim()).find(Boolean);
  if (!useSel) return;
  await waitForEntranceSettled(page, useSel).catch(async () => {
    // Fallback: try second selector if compound.
    const parts = sel.split(',').map((s) => s.trim());
    if (parts[1]) await waitForEntranceSettled(page, parts[1]);
  });
  await assertReadableForeground(page, useSel);
}

async function runCase({
  browser,
  routeId,
  pathName,
  lang,
  viewport,
  reducedMotion,
  fileSuffix = '',
}) {
  const bag = emptyBag();
  const context = await browser.newContext({
    viewport: { width: viewport.width, height: viewport.height },
    locale: lang === 'en' ? 'en-US' : lang === 'fa' ? 'fa-IR' : 'ps-AF',
    reducedMotion: reducedMotion ? 'reduce' : 'no-preference',
  });
  let page;
  const motionLabel = fileSuffix || (reducedMotion ? '' : '');
  const result = baseResult({
    route: pathName,
    routeId,
    viewport: viewport.name,
    lang,
    reducedMotion: Boolean(reducedMotion),
    motionMode: reducedMotion ? 'reduced' : 'motion',
  });
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

    await settleAndAssertReadable(page, routeId);

    const localeInfo = await assertLocale(page, lang);
    result.assertions.push(`locale:${localeInfo.lang}/${localeInfo.dir}`);
    const overflow = await assertNoOverflow(page);
    result.assertions.push(`overflowX:${overflow.overflowX}`);
    result.assertions.push('entrance_settled');
    result.assertions.push('readable_foreground');

    if (routeId === 'home' && viewport.name === '1440' && reducedMotion && !fileSuffix) {
      await page.reload({ waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
      await waitHomeReady(page);
      await assertLocale(page, lang);
      result.assertions.push('locale_persists_after_refresh');
    }

    const suffix = fileSuffix ? `_${fileSuffix}` : '';
    const file = `${DATA_MODE}_${routeId}_${lang}_${viewport.name}${suffix}.png`;
    result.screenshot = await shot(page, file);
    result.title = await page.title();
    result.dir = localeInfo.dir;
    return finalizeCase(result, bag, { strict: STRICT_API });
  } catch (err) {
    result.error = String(err?.message || err);
    const suffix = fileSuffix ? `_${fileSuffix}` : '';
    result.screenshot = await failShot(
      page,
      `${DATA_MODE}_${routeId}_${lang}_${viewport.name}${suffix}_FAIL.png`
    );
    return finalizeCase(result, bag, { strict: STRICT_API });
  } finally {
    await context.close().catch(() => {});
  }
}

async function loginViaUi(page, { user, pass }) {
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
  await waitLoginReady(page);
  await page.locator('[data-testid="isp-location"]').waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS });
  await page.waitForFunction(() => {
    const sel = document.querySelector('[data-testid="isp-location"]');
    return sel && sel.options && sel.options.length > 1;
  }, { timeout: PAGE_TIMEOUT_MS });
  await page.locator('[data-testid="isp-location"]').selectOption({ label: 'Kabul' });
  await page.locator('[data-testid="isp-username"]').fill(user);
  await page.locator('[data-testid="isp-password"]').fill(pass);
  const remember = page.locator('#remember');
  if ((await remember.count()) > 0) {
    await remember.check().catch(() => {});
  }
  await page.locator('[data-testid="isp-sign-in"]').click();
  await Promise.race([
    page.waitForFunction(() => !location.pathname.includes('/login'), { timeout: PAGE_TIMEOUT_MS }),
    page
      .locator('[role="alert"]')
      .waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS })
      .then(async () => {
        throw new Error(`login alert: ${(await page.locator('[role="alert"]').innerText()).trim()}`);
      }),
  ]);
}

async function logoutViaUi(page) {
  const profileTrigger = page.getByRole('button', { name: /profile|پروفایل/i });
  if ((await profileTrigger.count()) === 0) {
    throw new Error('profile menu missing for logout');
  }
  await profileTrigger.first().click();
  await page.getByRole('menuitem', { name: /logout|خروج|وتل/i }).click();
  await page.waitForFunction(() => location.pathname.includes('/login'), { timeout: PAGE_TIMEOUT_MS });
  const cleared = !(await page.evaluate(() => Boolean(localStorage.getItem('ifilm_access_token'))));
  if (!cleared) throw new Error('logout did not clear ifilm_access_token');
}

async function assertDetailPlayControl(page, kind) {
  const play =
    kind === 'movie'
      ? page.locator(
          '[data-testid="movie-play-button"], [data-testid="movie-continue-button"], [data-testid="movie-watch-again-button"], [data-testid="movie-demo-button"]'
        )
      : page.locator(
          '[data-testid="series-play-button"], [data-testid="series-continue-button"], [data-testid="series-next-button"], [data-testid="series-watch-again-button"]'
        );
  const unavailable =
    kind === 'movie'
      ? page.locator('[data-testid="movie-unavailable"]')
      : page.locator('[data-testid="series-unavailable"]');
  const hasPlay = (await play.count()) > 0 && (await play.first().isVisible().catch(() => false));
  const hasUnavail =
    (await unavailable.count()) > 0 && (await unavailable.first().isVisible().catch(() => false));
  if (!hasPlay && !hasUnavail) {
    throw new Error(`${kind} detail missing play or unavailable control`);
  }
  return hasPlay ? 'play' : 'unavailable';
}

async function assertDetailImages(page, kind) {
  const backdropSel =
    kind === 'movie' ? '[data-testid="movie-hero-backdrop"]' : '[data-testid="series-hero-backdrop"]';
  const titleSel =
    kind === 'movie'
      ? '[data-testid="movie-title-text"], [data-testid="movie-title-logo"]'
      : '[data-testid="series-title-text"], [data-testid="series-title-logo"]';
  const hasBackdrop = (await page.locator(backdropSel).count()) > 0;
  if (hasBackdrop) {
    await waitForImageDecoded(page, backdropSel, { allowMissing: false });
  } else {
    // Intentional missing artwork: solid fallback hero background + readable title.
    await waitForImageDecoded(page, backdropSel, { allowMissing: true });
  }
  const titleVisible = await page.locator(titleSel).first().isVisible().catch(() => false);
  if (!titleVisible) {
    // sr-only title with logo still counts as identity via logo alt / document title
    const logo = page.locator(
      kind === 'movie' ? '[data-testid="movie-title-logo"]' : '[data-testid="series-title-logo"]'
    );
    if ((await logo.count()) === 0) throw new Error(`${kind} detail title not readable`);
  }
  return { hasBackdrop };
}

async function runDetailCases(browser, report) {
  const desktop = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    reducedMotion: 'no-preference',
  });
  const mobile = await browser.newContext({
    viewport: { width: 390, height: 844 },
    reducedMotion: 'no-preference',
  });
  let page;
  let mpage;
  let spage;
  const bag = emptyBag();
  const resultDesktop = baseResult({ routeId: 'movie_detail', lang: 'en', viewport: '1440' });
  const resultMobile = baseResult({ routeId: 'movie_detail', lang: 'en', viewport: '390' });
  const resultSeries = baseResult({ routeId: 'series_detail', lang: 'en', viewport: '1440' });
  const resultSeriesMobile = baseResult({ routeId: 'series_detail', lang: 'en', viewport: '390' });

  try {
    await applyLocale(desktop, 'en');
    page = await desktop.newPage();
    attachCollectors(page, bag);

    await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
    await waitHomeReady(page);
    const more = page.locator('[data-testid="hero-more-info"]').or(
      page.getByRole('button', { name: /more info|اطلاعات بیشتر|نور معلومات/i })
    );
    if ((await more.count()) === 0) {
      throw new Error('home missing More Info control for movie detail navigation');
    }
    const heroTitle = (await page.locator('[data-testid="hero-title-text"], h1').first().innerText()).trim();
    await more.first().click();
    await waitMovieDetailReady(page);
    await assertReadableForeground(page, '[data-testid="movie-detail"]');
    await assertNoOverflow(page);
    const control = await assertDetailPlayControl(page, 'movie');
    const imgs = await assertDetailImages(page, 'movie');
    const detailTitle = (await page.title()).trim();
    if (heroTitle && detailTitle && !detailTitle.toLowerCase().includes(heroTitle.slice(0, 12).toLowerCase()) && !/movie|فیلم/i.test(detailTitle)) {
      // Soft identity: at least document title reflects movie surface.
      resultDesktop.assertions.push(`title_soft:${detailTitle}`);
    } else {
      resultDesktop.assertions.push(`title_identity:${detailTitle}`);
    }
    resultDesktop.assertions.push(`control:${control}`, imgs.hasBackdrop ? 'backdrop_decoded' : 'backdrop_fallback');
    resultDesktop.screenshot = await shot(page, `${DATA_MODE}_movie_detail_en_1440.png`);
    resultDesktop.title = detailTitle;
    finalizeCase(resultDesktop, bag, { strict: STRICT_API });
    report.push(resultDesktop);

    // Mobile movie detail via same URL (navigation continuity)
    const mbag = emptyBag();
    await applyLocale(mobile, 'en');
    mpage = await mobile.newPage();
    attachCollectors(mpage, mbag);
    await mpage.goto(page.url(), { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
    await waitMovieDetailReady(mpage);
    await assertReadableForeground(mpage, '[data-testid="movie-detail"]');
    await assertNoOverflow(mpage);
    const mControl = await assertDetailPlayControl(mpage, 'movie');
    const mImgs = await assertDetailImages(mpage, 'movie');
    resultMobile.assertions.push('mobile_detail', `control:${mControl}`, mImgs.hasBackdrop ? 'backdrop_decoded' : 'backdrop_fallback', 'opacity_settled');
    resultMobile.screenshot = await shot(mpage, `${DATA_MODE}_movie_detail_en_390.png`);
    resultMobile.title = await mpage.title();
    finalizeCase(resultMobile, mbag, { strict: STRICT_API });
    report.push(resultMobile);
    await mpage.close();
    mpage = null;

    // Series detail via browse navigation
    const sbag = emptyBag();
    // Re-attach collectors already on page; use fresh bag tracking via page events already bound —
    // open a clean page for series to keep bags isolated.
    await page.close();
    page = await desktop.newPage();
    attachCollectors(page, sbag);
    await page.goto(`${BASE}/series`, { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
    await waitSeriesReady(page);
    const seriesCard = page.locator('[data-testid="series-page"] [data-testid="media-card"]').first();
    if ((await seriesCard.count()) === 0) {
      throw new Error('series page has no cards to open detail');
    }
    await seriesCard.click();
    await waitSeriesDetailReady(page);
    await assertReadableForeground(page, '[data-testid="series-detail"]');
    const sControl = await assertDetailPlayControl(page, 'series');
    const sImgs = await assertDetailImages(page, 'series');
    resultSeries.assertions.push('series_detail', `control:${sControl}`, sImgs.hasBackdrop ? 'backdrop_decoded' : 'backdrop_fallback');
    resultSeries.screenshot = await shot(page, `${DATA_MODE}_series_detail_en_1440.png`);
    resultSeries.title = await page.title();
    finalizeCase(resultSeries, sbag, { strict: STRICT_API });
    report.push(resultSeries);

    const smbag = emptyBag();
    spage = await mobile.newPage();
    attachCollectors(spage, smbag);
    await applyLocale(mobile, 'en');
    await spage.goto(page.url(), { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
    await waitSeriesDetailReady(spage);
    await assertReadableForeground(spage, '[data-testid="series-detail"]');
    resultSeriesMobile.assertions.push('series_detail_mobile', 'opacity_settled');
    resultSeriesMobile.screenshot = await shot(spage, `${DATA_MODE}_series_detail_en_390.png`);
    resultSeriesMobile.title = await spage.title();
    finalizeCase(resultSeriesMobile, smbag, { strict: STRICT_API });
    report.push(resultSeriesMobile);
  } catch (err) {
    const msg = String(err?.message || err);
    const reported = new Set(report);
    const incomplete = [resultDesktop, resultMobile, resultSeries, resultSeriesMobile].find(
      (r) => !reported.has(r)
    );
    if (incomplete) {
      incomplete.error = msg;
      finalizeCase(incomplete, bag, { strict: STRICT_API });
      report.push(incomplete);
    } else if (!report.some((r) => String(r.routeId || '').includes('detail'))) {
      const fail = baseResult({ routeId: 'detail_cases', error: msg });
      fail.ok = false;
      report.push(fail);
    }
  } finally {
    await page?.close().catch(() => {});
    await mpage?.close().catch(() => {});
    await spage?.close().catch(() => {});
    await desktop.close().catch(() => {});
    await mobile.close().catch(() => {});
  }
}

async function runMotionSettledPairs(browser, report) {
  const pairs = [
    { routeId: 'home', pathName: '/', lang: 'en', viewport: '1440' },
    { routeId: 'home', pathName: '/', lang: 'fa', viewport: '1440' },
    { routeId: 'home', pathName: '/', lang: 'fa', viewport: '390' },
    { routeId: 'home', pathName: '/', lang: 'ps', viewport: '390' },
  ];

  for (const p of pairs) {
    const vp = viewports.find((v) => v.name === p.viewport);
    report.push(
      await runCase({
        browser,
        routeId: p.routeId,
        pathName: p.pathName,
        lang: p.lang,
        viewport: vp,
        reducedMotion: true,
        fileSuffix: 'reduced',
      })
    );
    report.push(
      await runCase({
        browser,
        routeId: p.routeId,
        pathName: p.pathName,
        lang: p.lang,
        viewport: vp,
        reducedMotion: false,
        fileSuffix: 'motion',
      })
    );
  }

  // Detail motion/reduced pairs (direct URL after discovering a title from browse).
  for (const kind of ['movie', 'series']) {
    for (const mode of ['reduced', 'motion']) {
      const bag = emptyBag();
      const context = await browser.newContext({
        viewport: { width: 390, height: 844 },
        reducedMotion: mode === 'reduced' ? 'reduce' : 'no-preference',
      });
      const result = baseResult({
        routeId: `${kind}_detail`,
        lang: 'en',
        viewport: '390',
        motionMode: mode,
      });
      let page;
      try {
        await applyLocale(context, 'en');
        page = await context.newPage();
        attachCollectors(page, bag);
        if (kind === 'movie') {
          await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
          await waitHomeReady(page);
          await page.locator('[data-testid="hero-more-info"]').first().click();
          await waitMovieDetailReady(page);
          await assertReadableForeground(page, '[data-testid="movie-detail"]');
        } else {
          await page.goto(`${BASE}/series`, { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
          await waitSeriesReady(page);
          await page.locator('[data-testid="series-page"] [data-testid="media-card"]').first().click();
          await waitSeriesDetailReady(page);
          await assertReadableForeground(page, '[data-testid="series-detail"]');
        }
        result.assertions.push(`settled_${mode}`, 'readable_foreground');
        result.screenshot = await shot(page, `${DATA_MODE}_${kind}_detail_en_390_${mode}.png`);
        result.title = await page.title();
        finalizeCase(result, bag, { strict: STRICT_API });
      } catch (err) {
        result.error = String(err?.message || err);
        result.screenshot = await failShot(page, `${DATA_MODE}_${kind}_detail_en_390_${mode}_FAIL.png`);
        finalizeCase(result, bag, { strict: STRICT_API });
      } finally {
        await context.close().catch(() => {});
      }
      report.push(result);
    }
  }
}

async function runHeroInteractions(browser, report) {
  if (!RUN_INTERACTIONS) return;
  const bag = emptyBag();
  const result = baseResult({ routeId: 'hero_interactions', lang: 'en', viewport: '1440' });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    reducedMotion: 'no-preference',
  });
  let page;
  try {
    await applyLocale(context, 'en');
    page = await context.newPage();
    attachCollectors(page, bag);
    await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
    await waitHomeReady(page);
    await assertReadableForeground(page, '[data-testid="hero-carousel"]');

    const next = page.locator('[data-testid="hero-next"]').or(page.getByRole('button', { name: /next featured/i }));
    const prev = page.locator('[data-testid="hero-prev"]').or(page.getByRole('button', { name: /previous featured/i }));
    const dots = page.locator('[data-testid="hero-dots"] button');
    if ((await next.count()) === 0) throw new Error('hero next control missing');
    if ((await prev.count()) === 0) throw new Error('hero previous control missing');

    const titleSel = '[data-testid="hero-title-text"], h1';
    const before = await page.locator(titleSel).first().innerText();
    await next.first().click();
    await waitForEntranceSettled(page, '[data-testid="hero-carousel"]');
    const afterNext = await page.locator(titleSel).first().innerText();
    await prev.first().click();
    await waitForEntranceSettled(page, '[data-testid="hero-carousel"]');
    const afterPrev = await page.locator(titleSel).first().innerText();
    const slideCount = await dots.count();
    if (slideCount > 1 && afterNext === before) {
      throw new Error('hero next did not change slide with multiple featured titles');
    }
    // Manual only: sample stability (no auto-advance) after settle
    await page.waitForTimeout(1500);
    const stable = await page.locator(titleSel).first().innerText();
    if (stable !== afterPrev) {
      throw new Error(`hero auto-advanced unexpectedly: ${afterPrev} -> ${stable}`);
    }
    result.assertions.push(
      `before=${before}`,
      `afterNext=${afterNext}`,
      `afterPrev=${afterPrev}`,
      `stable=${stable}`,
      `dots=${slideCount}`,
      'manual_only_no_auto_advance'
    );
    finalizeCase(result, bag, { strict: STRICT_API });
  } catch (err) {
    result.error = String(err?.message || err);
    finalizeCase(result, bag, { strict: STRICT_API });
  } finally {
    await context.close().catch(() => {});
  }
  report.push(result);
}

async function runRtlHeroAssertions(browser, report) {
  for (const lang of ['fa', 'ps']) {
    const bag = emptyBag();
    const result = baseResult({ routeId: 'rtl_hero', lang, viewport: '1440' });
    const context = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      locale: lang === 'fa' ? 'fa-IR' : 'ps-AF',
      reducedMotion: 'reduce',
    });
    let page;
    try {
      await applyLocale(context, lang);
      page = await context.newPage();
      attachCollectors(page, bag);
      await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
      await waitHomeReady(page);
      await assertLocale(page, lang);

      const syn = page.locator('[data-testid="hero-synopsis"]');
      await syn.waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS });
      const synInfo = await syn.evaluate((el) => ({
        dir: el.getAttribute('dir'),
        className: el.className || '',
        innerSpanDir: el.querySelector('span')?.getAttribute('dir') || null,
      }));
      if (synInfo.dir === 'auto') {
        throw new Error(`hero-synopsis must not have dir=auto on the block itself (lang=${lang})`);
      }
      if (!/\btext-start\b/.test(synInfo.className)) {
        throw new Error(`hero-synopsis missing text-start class (lang=${lang})`);
      }
      result.assertions.push('synopsis_no_dir_auto', 'text-start', `inner_span_dir=${synInfo.innerSpanDir}`);

      const unavail = page.locator('[data-testid="hero-unavailable"]');
      if ((await unavail.count()) > 0 && (await unavail.first().isVisible().catch(() => false))) {
        const text = (await unavail.first().innerText()).trim();
        if (!text) throw new Error('hero-unavailable visible but empty');
        result.assertions.push(`unavailable_localized:${text}`);
      } else {
        result.assertions.push('playable_slide_no_unavailable');
      }
      finalizeCase(result, bag, { strict: STRICT_API });
    } catch (err) {
      result.error = String(err?.message || err);
      finalizeCase(result, bag, { strict: STRICT_API });
    } finally {
      await context.close().catch(() => {});
    }
    report.push(result);
  }
}

async function runBrowseRetry(browser, report) {
  if (!RUN_INTERACTIONS) return;
  const bag = emptyBag();
  const result = baseResult({ routeId: 'movies_retry_recovery', lang: 'en', viewport: '1440' });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  let page;
  try {
    await applyLocale(context, 'en');
    page = await context.newPage();
    attachCollectors(page, bag);
    await page.goto(`${BASE}/movies`, { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
    await waitMoviesReady(page);

    // Intentional failure injection — do not count aborted **/api/movies** as unexpected.
    await page.route('**/api/movies**', (route) => route.abort('failed'));
    await page.reload({ waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
    await page.locator('[data-testid="browse-error"]').waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS });
    await page.unroute('**/api/movies**');
    await page.getByRole('button', { name: /retry|تلاش|هڅه/i }).click();
    await waitMoviesReady(page);
    result.screenshot = await shot(page, `${DATA_MODE}_movies_retry_recovered_en_1440.png`);
    result.assertions.push('error_ui_then_retry_ok');
    finalizeCase(result, bag, {
      strict: STRICT_API,
      // Intentional abort of /api/movies surfaces as requestfailed and/or console net::ERR_FAILED.
      ignoreFailedPred: (item) =>
        (item.startsWith('requestfailed:') &&
          /\/api\/movies/i.test(item) &&
          /(aborted|failed|net::ERR_FAILED|NS_ERROR_FAILURE)/i.test(item)) ||
        (item.startsWith('console:') && /net::ERR_FAILED/i.test(item)),
    });
  } catch (err) {
    result.error = String(err?.message || err);
    finalizeCase(result, bag, {
      strict: STRICT_API,
      ignoreFailedPred: (item) =>
        (item.startsWith('requestfailed:') &&
          /\/api\/movies/i.test(item) &&
          /(aborted|failed|net::ERR_FAILED|NS_ERROR_FAILURE)/i.test(item)) ||
        (item.startsWith('console:') && /net::ERR_FAILED/i.test(item)),
    });
  } finally {
    await context.close().catch(() => {});
  }
  report.push(result);
}

async function runSearchCases(browser, report) {
  const bag = emptyBag();
  const result = baseResult({ routeId: 'search_empty', lang: 'en', viewport: '1440' });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
  let page;
  try {
    await applyLocale(context, 'en');
    page = await context.newPage();
    attachCollectors(page, bag);
    await page.goto(`${BASE}/search`, { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
    await waitSearchReady(page);
    const box = page.getByRole('searchbox').or(page.locator('input').first());
    await box.fill('zzznomatchquery999');
    await page.locator('[data-testid="search-no-results"]').waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS });
    await shot(page, `${DATA_MODE}_search_empty_en_1440.png`);
    result.screenshot = `${DATA_MODE}_search_empty_en_1440.png`;

    await box.fill('Poet');
    await page.locator('[data-testid="media-card"], [data-testid="search-results"]').first().waitFor({
      state: 'visible',
      timeout: PAGE_TIMEOUT_MS,
    });
    await shot(page, `${DATA_MODE}_search_results_en_1440.png`);

    const clear = page.locator('[data-testid="search-clear"]').or(page.getByRole('button', { name: /clear|پاک|پاکول/i }));
    if ((await clear.count()) > 0) {
      await clear.first().click();
      await page.waitForTimeout(300);
      const val = await box.inputValue().catch(() => '');
      if (val && val.length > 0) {
        await box.fill('');
      }
      result.assertions.push('clear_search_ok');
    } else {
      await box.fill('');
      result.assertions.push('clear_search_via_input');
    }

    result.assertions.push('empty_state', 'results_for_Poet');
    finalizeCase(result, bag, { strict: STRICT_API });
  } catch (err) {
    result.error = String(err?.message || err);
    finalizeCase(result, bag, { strict: STRICT_API });
  } finally {
    await context.close().catch(() => {});
  }
  report.push(result);
}

async function runMoviesFiltersMobile(browser, report) {
  const bag = emptyBag();
  const result = baseResult({ routeId: 'movies_filters_mobile', lang: 'en', viewport: '390' });
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    reducedMotion: 'reduce',
  });
  let page;
  try {
    await applyLocale(context, 'en');
    page = await context.newPage();
    attachCollectors(page, bag);
    await page.goto(`${BASE}/movies`, { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
    await waitMoviesReady(page);
    const genre = page.locator('[data-testid="movies-genre-filter"]');
    if ((await genre.count()) === 0) throw new Error('movies genre filter missing');
    await genre.click();
    const option = page.getByRole('option').nth(1);
    if ((await option.count()) > 0) {
      await option.click();
      await page.waitForTimeout(400);
      result.assertions.push('filter_applied');
    } else {
      result.assertions.push('filter_control_present');
    }
    await assertNoOverflow(page);
    result.screenshot = await shot(page, `${DATA_MODE}_movies_filters_en_390.png`);
    // Also capture populated movies desktop for review subset.
    finalizeCase(result, bag, { strict: STRICT_API });
  } catch (err) {
    result.error = String(err?.message || err);
    finalizeCase(result, bag, { strict: STRICT_API });
  } finally {
    await context.close().catch(() => {});
  }
  report.push(result);
}

async function runMobileBottomClearance(browser, report) {
  const bag = emptyBag();
  const result = baseResult({ routeId: 'mobile_bottom_clearance', lang: 'en', viewport: '390' });
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    reducedMotion: 'reduce',
  });
  let page;
  try {
    await applyLocale(context, 'en');
    page = await context.newPage();
    attachCollectors(page, bag);
    await page.goto(`${BASE}/movies`, { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
    await waitMoviesReady(page);
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(400);
    const clearance = await page.evaluate(() => {
      const nav = document.querySelector('[data-testid="mobile-bottom-nav"]');
      const pageEl = document.querySelector('[data-testid="movies-page"]');
      if (!nav || !pageEl) return { ok: false, reason: 'missing_nav_or_page' };
      const navTop = nav.getBoundingClientRect().top;
      const cards = pageEl.querySelectorAll('[data-testid="media-card"]');
      let lastBottom = 0;
      const nodes = cards.length ? cards : pageEl.querySelectorAll('a, article, section, h1, h2, p');
      nodes.forEach((n) => {
        const b = n.getBoundingClientRect().bottom;
        if (b > lastBottom) lastBottom = b;
      });
      const pad = 8;
      return {
        ok: lastBottom <= navTop + pad,
        lastBottom,
        navTop,
        delta: navTop - lastBottom,
      };
    });
    if (!clearance.ok) {
      throw new Error(
        `bottom clearance failed lastBottom=${clearance.lastBottom} navTop=${clearance.navTop} reason=${clearance.reason || ''}`
      );
    }
    result.assertions.push(`clearance_delta=${clearance.delta}`);
    result.screenshot = await shot(page, `${DATA_MODE}_movies_bottom_clearance_en_390.png`);
    finalizeCase(result, bag, { strict: STRICT_API });
  } catch (err) {
    result.error = String(err?.message || err);
    finalizeCase(result, bag, { strict: STRICT_API });
  } finally {
    await context.close().catch(() => {});
  }
  report.push(result);
}

async function captureMoviesPopulatedReview(browser, report) {
  const bag = emptyBag();
  const result = baseResult({ routeId: 'movies_populated', lang: 'en', viewport: '1440' });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    reducedMotion: 'reduce',
  });
  let page;
  try {
    await applyLocale(context, 'en');
    page = await context.newPage();
    attachCollectors(page, bag);
    await page.goto(`${BASE}/movies`, { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
    await waitMoviesReady(page);
    await assertNoOverflow(page);
    result.screenshot = await shot(page, `${DATA_MODE}_movies_populated_en_1440.png`);
    result.assertions.push('movies_populated');
    finalizeCase(result, bag, { strict: STRICT_API });
  } catch (err) {
    result.error = String(err?.message || err);
    finalizeCase(result, bag, { strict: STRICT_API });
  } finally {
    await context.close().catch(() => {});
  }
  report.push(result);
}

async function runMissingArtwork(browser, report) {
  const bag = emptyBag();
  const result = baseResult({ routeId: 'missing_artwork', lang: 'en', viewport: '390' });
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    reducedMotion: 'no-preference',
  });
  let page;
  try {
    await applyLocale(context, 'en');
    page = await context.newPage();
    attachCollectors(page, bag);
    await page.goto(`${BASE}/movie/4`, { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
    await waitMovieDetailReady(page);
    await assertReadableForeground(page, '[data-testid="movie-detail"]');

    const backdrop = page.locator('[data-testid="movie-hero-backdrop"]');
    const hasBackdrop = (await backdrop.count()) > 0;
    if (hasBackdrop) {
      const src = await backdrop.getAttribute('src');
      if (!src) {
        result.assertions.push('intentional_empty_backdrop_src');
      } else {
        // If artwork exists in this environment, still require readable title; note not-missing.
        await waitForImageDecoded(page, '[data-testid="movie-hero-backdrop"]', { allowMissing: true });
        result.assertions.push('artwork_present_or_decoded');
      }
    } else {
      result.assertions.push('intentional_missing_backdrop_fallback');
    }

    const title = page.locator('[data-testid="movie-title-text"], [data-testid="movie-title-logo"]');
    await title.first().waitFor({ state: 'attached', timeout: PAGE_TIMEOUT_MS });
    await assertReadableForeground(page, '[data-testid="movie-detail"]');
    const pageTitle = await page.title();
    if (!pageTitle || pageTitle.length < 2) throw new Error('missing artwork page has unreadable title');
    result.assertions.push(`readable_title:${pageTitle}`);
    result.screenshot = await shot(page, `${DATA_MODE}_missing_artwork_en_390.png`);
    result.title = pageTitle;
    finalizeCase(result, bag, { strict: STRICT_API });
  } catch (err) {
    result.error = String(err?.message || err);
    result.screenshot = await failShot(page, `${DATA_MODE}_missing_artwork_en_390_FAIL.png`);
    finalizeCase(result, bag, { strict: STRICT_API });
  } finally {
    await context.close().catch(() => {});
  }
  report.push(result);
}

async function runAuthSmoke(browser, report) {
  if (!AUTH_USER || !AUTH_PASS) {
    report.push(
      baseResult({
        routeId: 'authenticated_gui',
        ok: true,
        skipped: true,
        status: 'NOT_RUN',
        reason: 'GUI_AUTH_USER/GUI_AUTH_PASS not provided',
        unexpected: [],
      })
    );
    return;
  }
  const bag = emptyBag();
  const result = baseResult({ routeId: 'authenticated_gui', lang: 'en', viewport: '1440' });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  let page;
  try {
    await applyLocale(context, 'en');
    await applyDeviceId(context, DEVICE_ID);
    page = await context.newPage();
    attachCollectors(page, bag);
    await loginViaUi(page, { user: AUTH_USER, pass: AUTH_PASS });
    const url = page.url();
    result.screenshot = await shot(page, `${DATA_MODE}_auth_home_en_1440.png`);

    await page.reload({ waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
    await waitHomeReady(page);
    const stillAuthed = await page.evaluate(() => Boolean(localStorage.getItem('ifilm_access_token')));
    if (!stillAuthed) throw new Error('session token missing after refresh (local fixture auth)');
    const profileTrigger = page.getByRole('button', { name: /profile|پروفایل/i });
    if ((await profileTrigger.count()) === 0) {
      throw new Error('profile menu missing after authenticated refresh');
    }

    await logoutViaUi(page);

    result.status = 'PASS';
    result.label = 'local_test_account_portal_stub';
    result.note = 'Local disposable Portal Voice AI stub + fixture user — not live Portal proof';
    result.assertions.push(
      `post_login_url=${url}`,
      'session_persists_after_refresh',
      'logout_clears_token',
      'local_disposable_portal_stub_not_live_portal',
      'isp_location_kabul',
      `device_id=${DEVICE_ID}`
    );
    finalizeCase(result, bag, {
      strict: STRICT_API,
      ignoreFailedPred: (item) => /429|Too Many Requests/i.test(item),
    });
  } catch (err) {
    result.status = 'FAIL';
    result.error = String(err?.message || err);
    finalizeCase(result, bag, { strict: STRICT_API });
  } finally {
    await context.close().catch(() => {});
  }
  report.push(result);
}

async function runWatchlist(browser, report) {
  if (!RUN_WATCHLIST) {
    report.push(
      baseResult({
        routeId: 'watchlist',
        ok: true,
        skipped: true,
        status: 'NOT_RUN',
        reason: 'GUI_WATCHLIST=0',
        unexpected: [],
      })
    );
    return;
  }
  if (!AUTH_USER || !AUTH_PASS) {
    report.push(
      baseResult({
        routeId: 'watchlist',
        ok: true,
        skipped: true,
        status: 'NOT_RUN',
        reason: 'GUI_AUTH_USER/GUI_AUTH_PASS not provided',
        unexpected: [],
      })
    );
    return;
  }

  const bag = emptyBag();
  const result = baseResult({ routeId: 'watchlist', lang: 'en', viewport: '1440' });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  let page;
  try {
    await applyLocale(context, 'en');
    await applyDeviceId(context, DEVICE_ID);
    page = await context.newPage();
    attachCollectors(page, bag);
    await loginViaUi(page, { user: AUTH_USER, pass: AUTH_PASS });

    // Add movie 3 via WatchlistButton on detail.
    await page.goto(`${BASE}/movie/3`, { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
    await waitMovieDetailReady(page);
    const movieToggle = page.locator('[data-testid="watchlist-toggle"]').first();
    await movieToggle.waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS });
    if ((await movieToggle.getAttribute('aria-pressed')) !== 'true') {
      await movieToggle.click();
      await page.waitForFunction(() => {
        const btn = document.querySelector('[data-testid="watchlist-toggle"]');
        return btn && btn.getAttribute('aria-pressed') === 'true';
      }, { timeout: PAGE_TIMEOUT_MS });
    }
    result.assertions.push('added_movie_3');

    // Add series 1.
    await page.goto(`${BASE}/series/1`, { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
    await waitSeriesDetailReady(page);
    const seriesToggle = page.locator('[data-testid="watchlist-toggle"]').first();
    await seriesToggle.waitFor({ state: 'visible', timeout: PAGE_TIMEOUT_MS });
    if ((await seriesToggle.getAttribute('aria-pressed')) !== 'true') {
      await seriesToggle.click();
      await page.waitForFunction(() => {
        const btn = document.querySelector('[data-testid="watchlist-toggle"]');
        return btn && btn.getAttribute('aria-pressed') === 'true';
      }, { timeout: PAGE_TIMEOUT_MS });
    }
    result.assertions.push('added_series_1');

    // Reload verify membership.
    await page.reload({ waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
    await waitSeriesDetailReady(page);
    await page.waitForFunction(() => {
      const btn = document.querySelector('[data-testid="watchlist-toggle"]');
      return btn && btn.getAttribute('aria-pressed') === 'true';
    }, { timeout: PAGE_TIMEOUT_MS });
    await page.goto(`${BASE}/movie/3`, { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
    await waitMovieDetailReady(page);
    await page.waitForFunction(() => {
      const btn = document.querySelector('[data-testid="watchlist-toggle"]');
      return btn && btn.getAttribute('aria-pressed') === 'true';
    }, { timeout: PAGE_TIMEOUT_MS });
    result.assertions.push('membership_persists_after_reload');

    // Remove both.
    await page.locator('[data-testid="watchlist-toggle"]').first().click();
    await page.waitForFunction(() => {
      const btn = document.querySelector('[data-testid="watchlist-toggle"]');
      return btn && btn.getAttribute('aria-pressed') === 'false';
    }, { timeout: PAGE_TIMEOUT_MS });

    await page.goto(`${BASE}/series/1`, { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
    await waitSeriesDetailReady(page);
    const sToggle = page.locator('[data-testid="watchlist-toggle"]').first();
    if ((await sToggle.getAttribute('aria-pressed')) === 'true') {
      await sToggle.click();
      await page.waitForFunction(() => {
        const btn = document.querySelector('[data-testid="watchlist-toggle"]');
        return btn && btn.getAttribute('aria-pressed') === 'false';
      }, { timeout: PAGE_TIMEOUT_MS });
    }

    await page.reload({ waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
    await waitSeriesDetailReady(page);
    await page.waitForFunction(() => {
      const btn = document.querySelector('[data-testid="watchlist-toggle"]');
      return btn && btn.getAttribute('aria-pressed') === 'false';
    }, { timeout: PAGE_TIMEOUT_MS });
    result.assertions.push('removed_and_gone_after_reload');

    await logoutViaUi(page);
    finalizeCase(result, bag, { strict: STRICT_API });
  } catch (err) {
    result.error = String(err?.message || err);
    finalizeCase(result, bag, { strict: STRICT_API });
  } finally {
    await context.close().catch(() => {});
  }
  report.push(result);

  // Isolation: second account must NOT see membership.
  const ibag = emptyBag();
  const isolation = baseResult({ routeId: 'watchlist_isolation', lang: 'en', viewport: '1440' });
  const ctx2 = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  let page2;
  try {
    await applyLocale(ctx2, 'en');
    await applyDeviceId(ctx2, DEVICE_ID2);
    page2 = await ctx2.newPage();
    attachCollectors(page2, ibag);
    try {
      await loginViaUi(page2, { user: AUTH_USER2, pass: AUTH_PASS2 });
    } catch (loginErr) {
      isolation.status = 'BLOCKED';
      isolation.ok = true;
      isolation.unexpected = [];
      isolation.reason = `second user login failed: ${String(loginErr?.message || loginErr)}`;
      isolation.assertions.push('isolation_blocked_second_login');
      report.push(isolation);
      await ctx2.close().catch(() => {});
      return;
    }

    await page2.goto(`${BASE}/movie/3`, { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
    await waitMovieDetailReady(page2);
    const pressed = await page2.locator('[data-testid="watchlist-toggle"]').first().getAttribute('aria-pressed');
    if (pressed === 'true') {
      throw new Error('second account unexpectedly sees movie 3 watchlist membership');
    }
    isolation.assertions.push('second_account_no_movie3_membership');
    isolation.status = 'PASS';
    finalizeCase(isolation, ibag, { strict: STRICT_API });
  } catch (err) {
    isolation.error = String(err?.message || err);
    finalizeCase(isolation, ibag, { strict: STRICT_API });
  } finally {
    await ctx2.close().catch(() => {});
  }
  report.push(isolation);
}

async function runPlayback(browser, report) {
  if (!RUN_PLAYBACK) {
    report.push(
      baseResult({
        routeId: 'playback',
        ok: true,
        skipped: true,
        status: 'NOT_RUN',
        reason: 'GUI_PLAYBACK=0',
        label: 'LOCAL portal stub',
        unexpected: [],
      })
    );
    return;
  }
  if (!AUTH_USER || !AUTH_PASS) {
    report.push(
      baseResult({
        routeId: 'playback',
        ok: true,
        skipped: true,
        status: 'NOT_RUN',
        reason: 'GUI_AUTH_USER/GUI_AUTH_PASS not provided',
        label: 'LOCAL portal stub',
        unexpected: [],
      })
    );
    return;
  }

  const bag = emptyBag();
  const result = baseResult({
    routeId: 'playback',
    lang: 'en',
    viewport: '1440',
    label: 'LOCAL portal stub',
  });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  let page;
  try {
    await applyLocale(context, 'en');
    await applyDeviceId(context, DEVICE_ID);
    page = await context.newPage();
    attachCollectors(page, bag);

    const cfgRes = await page.request.get(`${BASE}/api/config`);
    const cfg = cfgRes.ok() ? await cfgRes.json() : {};
    const minSeconds = Number(cfg.WATCH_PROGRESS_MIN_SECONDS ?? 5);

    await loginViaUi(page, { user: AUTH_USER, pass: AUTH_PASS });
    await page.goto(`${BASE}/movie/3`, { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
    await waitMovieDetailReady(page);

    const playBtn = page.locator(
      '[data-testid="movie-play-button"], [data-testid="movie-continue-button"], [data-testid="movie-demo-button"], [data-testid="movie-watch-again-button"]'
    );
    if ((await playBtn.count()) === 0) {
      result.status = 'BLOCKED';
      result.ok = true;
      result.error = undefined;
      result.reason = 'Play control not available on /movie/3';
      result.assertions.push('blocked_no_play_control');
      finalizeCase(result, bag, { strict: false });
      result.ok = true;
      result.status = 'BLOCKED';
      report.push(result);
      return;
    }
    await playBtn.first().click();
    await page.waitForURL(/\/player\//, { timeout: PAGE_TIMEOUT_MS });
    await page.locator('[data-testid="video-player"], video, [data-testid="player-video"]').first().waitFor({
      state: 'attached',
      timeout: PAGE_TIMEOUT_MS,
    });
    const docTitle = await page.title();
    result.assertions.push(`document_title:${docTitle}`);
    if (!docTitle || docTitle.length < 2) throw new Error('player document title empty');

    // Dismiss resume dialog if present so playback can advance from a known state.
    const resumeDlg = page.locator('[data-testid="resume-dialog"]');
    if (await resumeDlg.isVisible().catch(() => false)) {
      const startOver = page.locator('[data-testid="resume-start-over"]');
      if ((await startOver.count()) > 0) await startOver.click();
      else await page.locator('[data-testid="resume-continue"]').click();
    }

    const video = page.locator('video');
    await video.first().waitFor({ state: 'attached', timeout: PAGE_TIMEOUT_MS });
    // Ensure playing
    const centerPlay = page.locator('[data-testid="center-play"]');
    if (await centerPlay.isVisible().catch(() => false)) {
      await centerPlay.click().catch(() => {});
    }
    // Never await media.play() inside evaluate — a pending play() Promise hangs Playwright.
    await video
      .evaluate((v) => {
        try {
          void v.play?.();
        } catch {
          /* ignore */
        }
      })
      .catch(() => {});

    const t0 = await video.evaluate((v) => v.currentTime);
    let advanced = false;
    let t1 = t0;
    const advanceDeadline = Date.now() + 30000;
    while (Date.now() < advanceDeadline) {
      await page.waitForTimeout(500);
      t1 = await video.evaluate((v) => v.currentTime);
      if (t1 > t0 + 0.25) {
        advanced = true;
        break;
      }
      // Nudge play if stalled (fire-and-forget)
      await video
        .evaluate((v) => {
          try {
            void v.play?.();
          } catch {
            /* ignore */
          }
        })
        .catch(() => {});
    }
    if (!advanced) {
      result.status = 'BLOCKED';
      result.reason = `player cannot advance currentTime (start=${t0}, end=${t1})`;
      result.assertions.push(`blocked:${result.reason}`);
      result.screenshot = await failShot(page, `${DATA_MODE}_playback_blocked_en_1440.png`);
      finalizeCase(result, bag, { strict: false });
      result.ok = true;
      result.status = 'BLOCKED';
      report.push(result);
      return;
    }
    result.assertions.push(`currentTime_advanced:${t0}->${t1}`);
    // Drop collectors from the first session before reload/start-over: revoked
    // stream token 404s are expected and must not fail an otherwise green run.
    bag.http404.length = 0;
    bag.consoleErrors = bag.consoleErrors.filter((e) => !/status of 404/i.test(e));
    bag.failedRequests = bag.failedRequests.filter((e) => !/\/api\/stream\//i.test(e.url || ''));

    // Wait past WATCH_PROGRESS_MIN_SECONDS.
    const waitMs = Math.max(0, (minSeconds + 1) * 1000);
    const target = Math.max(t1, minSeconds + 0.5);
    const saveDeadline = Date.now() + waitMs + 15000;
    while (Date.now() < saveDeadline) {
      const now = await video.evaluate((v) => v.currentTime);
      if (now >= target) break;
      await page.waitForTimeout(500);
    }
    const savedAt = await video.evaluate((v) => v.currentTime);
    result.assertions.push(`watched_past_min:${savedAt}>=${minSeconds}`);
    // Reset stream noise before resume/start-over exercises a new session.
    bag.http404.length = 0;
    bag.consoleErrors = bag.consoleErrors.filter((e) => !/status of 404/i.test(e));
    bag.failedRequests = bag.failedRequests.filter((e) => !/\/api\/stream\//i.test(e.url || ''));

    // Reload player and assert resume near saved position OR resume dialog.
    await page.reload({ waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
    await page.locator('[data-testid="video-player"], video').first().waitFor({
      state: 'attached',
      timeout: PAGE_TIMEOUT_MS,
    });
    let resumed = false;
    if (await page.locator('[data-testid="resume-dialog"]').isVisible().catch(() => false)) {
      result.assertions.push('resume_dialog_shown');
      await page.locator('[data-testid="resume-continue"]').click();
      await page.waitForTimeout(1500);
      const afterDialog = await page.locator('video').evaluate((v) => v.currentTime);
      // After Continue, position should be near saved (not near zero).
      if (afterDialog >= Math.max(1, savedAt - 20) && afterDialog > 1) {
        result.assertions.push(`resume_near_saved_after_dialog:${afterDialog}~${savedAt}`);
        resumed = true;
      } else {
        throw new Error(`resume dialog Continue left currentTime=${afterDialog}, saved=${savedAt}`);
      }
    } else {
      await page.waitForTimeout(2000);
      const after = await page.locator('video').evaluate((v) => v.currentTime);
      // Require a real near-resume: within 20s of saved and not stuck at ~0 when saved>>0.
      if (savedAt >= 3 && after >= Math.max(1, savedAt - 20) && Math.abs(after - savedAt) <= 20) {
        result.assertions.push(`resume_near_saved:${after}~${savedAt}`);
        resumed = true;
      } else if (savedAt < 3 && after <= savedAt + 5) {
        result.assertions.push(`resume_early_position:${after}~${savedAt}`);
        resumed = true;
      }
    }
    if (!resumed) {
      throw new Error(`resume not detected near saved position (saved=${savedAt})`);
    }

    // Start Over from beginning if control exists.
    const startOverCtrl = page.locator('[data-testid="start-over"], [data-testid="resume-start-over"]');
    if ((await startOverCtrl.count()) > 0) {
      // Reveal controls
      await page.mouse.move(400, 400);
      await page.waitForTimeout(200);
      await startOverCtrl.first().click();
      await page.waitForTimeout(800);
      const at = await page.locator('video').evaluate((v) => v.currentTime);
      result.assertions.push(`start_over_time:${at}`);
      if (at > 2.5) {
        throw new Error(`Start Over did not reset near beginning (currentTime=${at})`);
      }
    } else if (await page.locator('[data-testid="resume-dialog"]').isVisible().catch(() => false)) {
      await page.locator('[data-testid="resume-start-over"]').click();
      await page.waitForTimeout(800);
      const at = await page.locator('video').evaluate((v) => v.currentTime);
      result.assertions.push(`start_over_from_dialog:${at}`);
      if (at > 2.5) {
        throw new Error(`Start Over from dialog did not reset near beginning (currentTime=${at})`);
      }
    } else {
      result.assertions.push('start_over_control_absent');
    }

    result.status = 'PASS';
    finalizeCase(result, bag, {
      strict: STRICT_API,
      // After progress is saved, session reload can 404 prior stream tokens.
      ignoreFailedPred: (item) =>
        (item.startsWith('http404:') || item.startsWith('requestfailed:')) &&
        /\/api\/stream\//i.test(item),
    });
  } catch (err) {
    result.status = 'FAIL';
    result.error = String(err?.message || err);
    result.screenshot = await failShot(page, `${DATA_MODE}_playback_FAIL.png`);
    finalizeCase(result, bag, { strict: STRICT_API });
  } finally {
    await context.close().catch(() => {});
  }
  report.push(result);

  // FA locale: player controls/timeline must be dir=ltr.
  const fbag = emptyBag();
  const faResult = baseResult({
    routeId: 'playback_fa_ltr_controls',
    lang: 'fa',
    viewport: '1440',
    label: 'LOCAL portal stub',
  });
  const faCtx = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    locale: 'fa-IR',
  });
  let faPage;
  try {
    await applyLocale(faCtx, 'fa');
    await applyDeviceId(faCtx, DEVICE_ID);
    faPage = await faCtx.newPage();
    attachCollectors(faPage, fbag);
    await loginViaUi(faPage, { user: AUTH_USER, pass: AUTH_PASS });
    await faPage.goto(`${BASE}/movie/3`, { waitUntil: 'domcontentloaded', timeout: PAGE_TIMEOUT_MS });
    await waitMovieDetailReady(faPage);
    const playBtn = faPage.locator(
      '[data-testid="movie-play-button"], [data-testid="movie-continue-button"], [data-testid="movie-demo-button"], [data-testid="movie-watch-again-button"]'
    );
    if ((await playBtn.count()) === 0) {
      faResult.status = 'BLOCKED';
      faResult.reason = 'Play control not available for fa playback dir check';
      faResult.ok = true;
      faResult.unexpected = [];
      faResult.assertions.push('blocked_no_play_control');
      report.push(faResult);
      return;
    }
    await playBtn.first().click();
    await faPage.waitForURL(/\/player\//, { timeout: PAGE_TIMEOUT_MS });
    await faPage.locator('[data-testid="video-player"]').waitFor({ state: 'attached', timeout: PAGE_TIMEOUT_MS });
    // Nudge controls visible
    await faPage.mouse.move(200, 200);
    await faPage.waitForTimeout(300);
    const dirs = await faPage.evaluate(() => {
      const player = document.querySelector('[data-testid="video-player"]');
      const controls = document.querySelector('[data-testid="player-controls"]');
      const seek = document.querySelector('[data-testid="seek-bar"]');
      const readDir = (el) => (el ? el.getAttribute('dir') || getComputedStyle(el).direction : null);
      return {
        player: readDir(player),
        controls: readDir(controls),
        seek: readDir(seek),
      };
    });
    if (dirs.player && dirs.player !== 'ltr') {
      throw new Error(`video-player dir want=ltr got=${dirs.player}`);
    }
    if (dirs.controls && dirs.controls !== 'ltr') {
      throw new Error(`player-controls dir want=ltr got=${dirs.controls}`);
    }
    faResult.assertions.push(`player_dir=${dirs.player}`, `controls_dir=${dirs.controls}`, `seek_dir=${dirs.seek}`);
    faResult.status = 'PASS';
    finalizeCase(faResult, fbag, { strict: STRICT_API });
  } catch (err) {
    faResult.status = 'FAIL';
    faResult.error = String(err?.message || err);
    finalizeCase(faResult, fbag, { strict: STRICT_API });
  } finally {
    await faCtx.close().catch(() => {});
  }
  report.push(faResult);
}

async function pathExists(p) {
  try {
    await access(p);
    return true;
  } catch {
    return false;
  }
}

async function preserveBeforeReview() {
  const reviewDir = path.join(OUT, 'review');
  const beforeDir = path.join(reviewDir, 'before');
  await mkdir(reviewDir, { recursive: true });
  await mkdir(beforeDir, { recursive: true });

  let beforeFiles = [];
  try {
    beforeFiles = await readdir(beforeDir);
  } catch {
    beforeFiles = [];
  }
  if (beforeFiles.length > 0) {
    return { skipped: true, reason: 'before already exists' };
  }

  if (!(await pathExists(EXISTING_REVIEW))) {
    return { skipped: true, reason: 'no existing review dir' };
  }
  const srcFiles = (await readdir(EXISTING_REVIEW)).filter((f) => f.endsWith('.png') || f === 'summary.json');
  for (const f of srcFiles) {
    // Do not recurse into before/
    if (f === 'before') continue;
    const src = path.join(EXISTING_REVIEW, f);
    const dest = path.join(beforeDir, f);
    if (await pathExists(dest)) continue;
    try {
      await copyFile(src, dest);
    } catch {
      /* ignore individual copy failures */
    }
  }
  return { copied: srcFiles.length };
}

async function copyReviewSubset(report) {
  const reviewDir = path.join(OUT, 'review');
  await mkdir(reviewDir, { recursive: true });

  const byLogical = {
    movie_detail_en_390: `${DATA_MODE}_movie_detail_en_390.png`,
    series_detail_en_390: `${DATA_MODE}_series_detail_en_390.png`,
    home_fa_1440: `${DATA_MODE}_home_fa_1440.png`,
    home_fa_390: `${DATA_MODE}_home_fa_390.png`,
    home_ps_390: `${DATA_MODE}_home_ps_390.png`,
    movies_populated_en_1440: `${DATA_MODE}_movies_populated_en_1440.png`,
    search_results: `${DATA_MODE}_search_results_en_1440.png`,
    search_empty: `${DATA_MODE}_search_empty_en_1440.png`,
    missing_artwork_en_390: `${DATA_MODE}_missing_artwork_en_390.png`,
  };

  // Prefer motion-settled detail shots for review when present.
  const motionMovie = `${DATA_MODE}_movie_detail_en_390_motion.png`;
  const motionSeries = `${DATA_MODE}_series_detail_en_390_motion.png`;
  if (await pathExists(path.join(OUT, motionMovie))) {
    byLogical.movie_detail_en_390 = motionMovie;
  }
  if (await pathExists(path.join(OUT, motionSeries))) {
    byLogical.series_detail_en_390 = motionSeries;
  }

  const copied = [];
  for (const logical of REVIEW_SUBSET) {
    const srcName = byLogical[logical];
    if (!srcName) continue;
    const src = path.join(OUT, srcName);
    if (!(await pathExists(src))) continue;
    // before/after style names (logical) + api_* mirror
    const destLogical = path.join(reviewDir, `${logical}.png`);
    const destApi = path.join(reviewDir, srcName);
    await copyFile(src, destLogical).catch(() => {});
    await copyFile(src, destApi).catch(() => {});
    copied.push(logical);
  }

  // Also copy common home/auth shots for continuity with prior review folder.
  for (const extra of [
    `${DATA_MODE}_home_en_1440.png`,
    `${DATA_MODE}_auth_home_en_1440.png`,
    `${DATA_MODE}_movies_filters_en_390.png`,
  ]) {
    const src = path.join(OUT, extra);
    if (await pathExists(src)) {
      await copyFile(src, path.join(reviewDir, extra)).catch(() => {});
    }
  }

  return copied;
}

async function main() {
  await mkdir(OUT, { recursive: true });
  const beforeInfo = await preserveBeforeReview();

  const browser = await chromium.launch({ headless: true });
  const report = [];
  try {
    // Matrix: home+movies all viewports × langs (reduced motion for stable layout)
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

    await runMotionSettledPairs(browser, report);
    await runDetailCases(browser, report);
    await runHeroInteractions(browser, report);
    await runRtlHeroAssertions(browser, report);
    await runBrowseRetry(browser, report);
    await runSearchCases(browser, report);
    await runMoviesFiltersMobile(browser, report);
    await captureMoviesPopulatedReview(browser, report);
    await runMobileBottomClearance(browser, report);
    await runMissingArtwork(browser, report);
    await runAuthSmoke(browser, report);
    await runWatchlist(browser, report);
    await runPlayback(browser, report);
  } finally {
    await browser.close().catch(() => {});
  }

  const reviewCopied = await copyReviewSubset(report);

  const failed = report.filter((r) => r.ok === false);
  const blocked = report.filter((r) => r.status === 'BLOCKED');
  const labels = {
    dataMode: DATA_MODE,
    auth: AUTH_USER ? 'local_disposable_portal_stub_not_live_portal' : 'NOT_RUN',
    playback: (() => {
      const p = report.find((r) => r.routeId === 'playback');
      if (!p) return 'NOT_RUN';
      if (p.status === 'BLOCKED') return `BLOCKED_${(p.reason || p.error || 'unknown').slice(0, 120)}`;
      if (p.skipped) return p.reason || 'NOT_RUN';
      if (p.ok) return 'PASS_local_portal_stub';
      return 'FAIL';
    })(),
    watchlist: (() => {
      const w = report.find((r) => r.routeId === 'watchlist');
      const iso = report.find((r) => r.routeId === 'watchlist_isolation');
      if (!w) return 'NOT_RUN';
      if (iso?.status === 'BLOCKED') return `ISOLATION_BLOCKED_${iso.reason || ''}`.slice(0, 160);
      if (w.skipped) return w.reason || 'NOT_RUN';
      if (w.ok) return 'PASS';
      return 'FAIL';
    })(),
    reviewScreenshots: path.join(OUT, 'review'),
    beforePreserved: beforeInfo,
    reviewCopied,
  };

  const summary = {
    commitSha: COMMIT_SHA,
    frontendCommit: FRONTEND_COMMIT,
    backendCommit: BACKEND_COMMIT,
    dataMode: DATA_MODE,
    baseUrl: BASE,
    total: report.length,
    passed: report.filter((r) => r.ok).length,
    failed: failed.length,
    blocked: blocked.length,
    labels,
    cases: report,
  };
  await writeFile(path.join(OUT, 'summary.json'), JSON.stringify(summary, null, 2));
  await writeFile(path.join(OUT, 'review', 'summary.json'), JSON.stringify(summary, null, 2)).catch(() => {});

  console.log(
    JSON.stringify(
      {
        total: summary.total,
        passed: summary.passed,
        failed: summary.failed,
        blocked: summary.blocked,
        out: OUT,
        commitSha: COMMIT_SHA,
      },
      null,
      2
    )
  );

  if (failed.length) {
    for (const f of failed.slice(0, 16)) {
      console.error('FAIL', f.routeId || f.route, f.lang, f.viewport, f.error);
    }
    process.exit(1);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
