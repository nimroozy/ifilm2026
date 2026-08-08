/**
 * Production-like browsing waterfall + request-dedup + image audit for PR #58.
 */
import { test, expect, type Page, type Request, type Response } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const BASE = process.env.PERF_BASE_URL || 'http://127.0.0.1:8010';
const OUT = process.env.PERF_ARTIFACT_DIR || '/opt/cursor/artifacts/perf-customer-browsing-v1';
const USER = process.env.PERF_USER || 'mobin_user_001';
const PASS = process.env.PERF_PASS || 'fixture-pass-ok';

type ResourceRow = {
  url: string;
  method: string;
  resourceType: string;
  status: number;
  transferSize: number;
  encodedBodySize: number;
  startTime: number;
  duration: number;
  ttfb: number;
};

type PageMetrics = {
  label: string;
  viewport: { width: number; height: number };
  network?: string;
  navigationStart: number;
  ttfb: number;
  domContentLoaded: number;
  lcp: number | null;
  lcpElement: string | null;
  firstShellVisibleMs: number | null;
  firstPosterVisibleMs: number | null;
  apiRequestCount: number;
  apiUrls: string[];
  duplicateApiUrls: string[];
  totalTransferredBytes: number;
  imageTransferredBytes: number;
  jsTransferredBytes: number;
  cssTransferredBytes: number;
  jsAssetEncodings: Array<{ url: string; encoding: string; transferSize: number; encodedBodySize: number }>;
  slowestRequest: { url: string; duration: number; status: number } | null;
  imageUrls: string[];
  originalTmdbImages: string[];
  heroImageUrls: string[];
};

function ensureOut() {
  fs.mkdirSync(OUT, { recursive: true });
}

function classifyTransfer(entry: PerformanceResourceTiming): number {
  // transferSize is 0 for cached; fall back to encodedBodySize.
  return entry.transferSize || entry.encodedBodySize || 0;
}

async function collectMetrics(
  page: Page,
  label: string,
  gotoPath: string,
  opts?: { network?: 'fast3g' }
): Promise<PageMetrics> {
  const apiUrls: string[] = [];
  const reqStarted = new Map<string, number>();
  const responses: { url: string; status: number; duration: number }[] = [];

  page.on('request', (req: Request) => {
    if (req.url().includes('/api/')) {
      apiUrls.push(req.url());
      reqStarted.set(req.url() + '|' + req.method(), Date.now());
    }
  });
  page.on('response', async (res: Response) => {
    if (!res.url().includes('/api/')) return;
    const key = res.url() + '|' + res.request().method();
    const start = reqStarted.get(key) || Date.now();
    responses.push({ url: res.url(), status: res.status(), duration: Date.now() - start });
  });

  if (opts?.network === 'fast3g') {
    const client = await page.context().newCDPSession(page);
    await client.send('Network.emulateNetworkConditions', {
      offline: false,
      downloadThroughput: (1.6 * 1024 * 1024) / 8, // ~1.6 Mbps
      uploadThroughput: (750 * 1024) / 8,
      latency: 150,
    });
  }

  const navStart = Date.now();
  await page.goto(gotoPath, { waitUntil: 'domcontentloaded', timeout: 60_000 });

  let firstShellVisibleMs: number | null = null;
  try {
    await page.locator('[data-testid="customer-header"], [data-testid="customer-shell"]').first().waitFor({
      state: 'visible',
      timeout: 45_000,
    });
    firstShellVisibleMs = Date.now() - navStart;
  } catch {
    firstShellVisibleMs = null;
  }

  // Wait for primary cards or hero.
  const poster = page.locator('[data-testid="media-card"] img, img[src*="tmdb"], img[src*="poster"]').first();
  let firstPosterVisibleMs: number | null = null;
  try {
    await poster.waitFor({ state: 'visible', timeout: 45_000 });
    firstPosterVisibleMs = Date.now() - navStart;
  } catch {
    firstPosterVisibleMs = null;
  }

  // Allow late API/images.
  await page.waitForTimeout(2500);

  const timing = await page.evaluate(() => {
    const nav = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined;
    const resources = performance.getEntriesByType('resource') as PerformanceResourceTiming[];
    const lcpEntries = performance.getEntriesByType('largest-contentful-paint') as Array<
      PerformanceEntry & { element?: Element; url?: string; size?: number }
    >;
    const last = lcpEntries.length ? lcpEntries[lcpEntries.length - 1] : null;
    let lcpElement: string | null = null;
    if (last?.element instanceof HTMLElement) {
      const el = last.element;
      lcpElement = `${el.tagName.toLowerCase()}${el.id ? `#${el.id}` : ''}${
        el.getAttribute('data-testid') ? `[data-testid=${el.getAttribute('data-testid')}]` : ''
      }${el.getAttribute('src') ? ` src=${(el.getAttribute('src') || '').slice(0, 120)}` : ''}`;
    } else if (last?.url) {
      lcpElement = `url:${last.url.slice(0, 160)}`;
    }
    return {
      ttfb: nav ? nav.responseStart : 0,
      domContentLoaded: nav ? nav.domContentLoadedEventEnd : 0,
      lcp: last ? last.startTime : null,
      lcpElement,
      resources: resources.map((r) => ({
        url: r.name,
        resourceType: (r as PerformanceResourceTiming & { initiatorType: string }).initiatorType,
        transferSize: r.transferSize || 0,
        encodedBodySize: r.encodedBodySize || 0,
        decodedBodySize: r.decodedBodySize || 0,
        startTime: r.startTime,
        duration: r.duration,
        ttfb: r.responseStart,
      })),
    };
  });

  // Observe LCP via PerformanceObserver buffer if empty.
  let lcp = timing.lcp;
  let lcpElement = timing.lcpElement;
  if (lcp == null) {
    const observed = await page.evaluate(() => {
      return new Promise<{ lcp: number | null; lcpElement: string | null }>((resolve) => {
        let value: number | null = null;
        let elDesc: string | null = null;
        const po = new PerformanceObserver((list) => {
          const entries = list.getEntries() as Array<
            PerformanceEntry & { element?: Element; url?: string }
          >;
          if (entries.length) {
            const last = entries[entries.length - 1];
            value = last.startTime;
            if (last.element instanceof HTMLElement) {
              elDesc = `${last.element.tagName.toLowerCase()}${
                last.element.getAttribute('data-testid')
                  ? `[data-testid=${last.element.getAttribute('data-testid')}]`
                  : ''
              }`;
            } else if (last.url) {
              elDesc = `url:${last.url.slice(0, 160)}`;
            }
          }
        });
        try {
          po.observe({ type: 'largest-contentful-paint', buffered: true });
        } catch {
          resolve({ lcp: null, lcpElement: null });
          return;
        }
        setTimeout(() => {
          po.disconnect();
          resolve({ lcp: value, lcpElement: elDesc });
        }, 1000);
      });
    });
    lcp = observed.lcp;
    lcpElement = observed.lcpElement;
  }

  const jsAssetEncodings = await page.evaluate(async () => {
    const scripts = Array.from(document.querySelectorAll('script[src], link[rel="modulepreload"]'))
      .map((el) => (el as HTMLScriptElement | HTMLLinkElement).href || (el as HTMLLinkElement).href)
      .filter((u) => u && u.includes('/assets/') && u.endsWith('.js'));
    const out: Array<{ url: string; encoding: string; transferSize: number; encodedBodySize: number }> = [];
    for (const url of scripts.slice(0, 12)) {
      try {
        const res = await fetch(url, { method: 'GET', cache: 'force-cache' });
        const buf = await res.arrayBuffer();
        out.push({
          url,
          encoding: res.headers.get('content-encoding') || 'identity',
          transferSize: Number(res.headers.get('content-length') || buf.byteLength),
          encodedBodySize: buf.byteLength,
        });
      } catch {
        /* ignore */
      }
    }
    return out;
  });

  const rows: ResourceRow[] = timing.resources.map((r) => ({
    url: r.url,
    method: 'GET',
    resourceType: r.resourceType,
    status: 0,
    transferSize: r.transferSize || r.encodedBodySize || 0,
    encodedBodySize: r.encodedBodySize,
    startTime: r.startTime,
    duration: r.duration,
    ttfb: r.ttfb,
  }));

  // Prefer transferSize (wire bytes after compression). Fall back to encodedBodySize.
  const wire = (r: ResourceRow) => r.transferSize || r.encodedBodySize || 0;
  const totalTransferredBytes = rows.reduce((a, r) => a + wire(r), 0);
  const imageTransferredBytes = rows
    .filter((r) => r.resourceType === 'img' || /\.(jpg|jpeg|png|webp|avif)(\?|$)/i.test(r.url))
    .reduce((a, r) => a + wire(r), 0);
  const jsTransferredBytes = rows
    .filter((r) => r.resourceType === 'script' || /\.js(\?|$)/i.test(r.url))
    .reduce((a, r) => a + wire(r), 0);
  const cssTransferredBytes = rows
    .filter((r) => r.resourceType === 'css' || r.resourceType === 'link' || /\.css(\?|$)/i.test(r.url))
    .reduce((a, r) => a + wire(r), 0);

  const slowest =
    responses.sort((a, b) => b.duration - a.duration)[0] ||
    rows
      .slice()
      .sort((a, b) => b.duration - a.duration)
      .map((r) => ({ url: r.url, duration: r.duration, status: r.status }))[0] ||
    null;

  const counts = new Map<string, number>();
  for (const u of apiUrls) counts.set(u, (counts.get(u) || 0) + 1);
  const duplicateApiUrls = [...counts.entries()].filter(([, n]) => n > 1).map(([u]) => u);

  const imageUrls = await page.evaluate(() =>
    Array.from(document.images)
      .map((img) => img.currentSrc || img.src)
      .filter(Boolean)
  );
  const originalTmdbImages = imageUrls.filter((u) => /image\.tmdb\.org\/t\/p\/original\//i.test(u));
  const heroImageUrls = await page.evaluate(() => {
    const hero = document.querySelector('[aria-label="Featured titles"] img');
    return hero ? [(hero as HTMLImageElement).currentSrc || (hero as HTMLImageElement).src] : [];
  });

  return {
    label,
    viewport: page.viewportSize() || { width: 0, height: 0 },
    network: opts?.network,
    navigationStart: navStart,
    ttfb: timing.ttfb,
    domContentLoaded: timing.domContentLoaded,
    lcp,
    lcpElement,
    firstShellVisibleMs,
    firstPosterVisibleMs,
    apiRequestCount: apiUrls.length,
    apiUrls,
    duplicateApiUrls,
    totalTransferredBytes,
    imageTransferredBytes,
    jsTransferredBytes,
    cssTransferredBytes,
    jsAssetEncodings,
    slowestRequest: slowest,
    imageUrls,
    originalTmdbImages,
    heroImageUrls,
  };
}

async function login(page: Page) {
  await page.goto('/login');
  await page.fill('#username', USER);
  await page.fill('#password', PASS);
  await page.locator('form button[type="submit"]').click();
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 30_000 });
}

test.describe.configure({ mode: 'serial' });

test('browser waterfalls desktop + mobile + auth dedup + images', async ({ browser }) => {
  ensureOut();
  const all: PageMetrics[] = [];

  // Desktop anonymous home
  {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await context.newPage();
    all.push(await collectMetrics(page, 'desktop-anon-home', '/'));
    await context.close();
  }

  // Desktop movies / series / detail
  {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await context.newPage();
    all.push(await collectMetrics(page, 'desktop-movies', '/movies'));
    all.push(await collectMetrics(page, 'desktop-series', '/series'));
    // Use a seeded slug if present; otherwise first movie card navigation.
    const detailResp = await page.request.get(`${BASE}/api/movies?page_size=1&sort=newest`);
    const movieId = (await detailResp.json()).data?.[0]?.id;
    expect(movieId).toBeTruthy();
    all.push(await collectMetrics(page, 'desktop-movie-detail', `/movie/${movieId}`));
    await context.close();
  }

  // Desktop authenticated home — expect only /api/me/home for personalization rails
  {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await context.newPage();
    await login(page);
    const metrics = await collectMetrics(page, 'desktop-auth-home', '/');
    all.push(metrics);
    const apiPaths = metrics.apiUrls.map((u) => new URL(u).pathname);
    const homeApis = apiPaths.filter((p) => p.includes('/home') || p.includes('/recommendations') || p.includes('/watchlist') || p.includes('/continue-watching'));
    fs.writeFileSync(
      path.join(OUT, 'auth-home-api-paths.json'),
      JSON.stringify({ apiPaths, homeApis, duplicates: metrics.duplicateApiUrls }, null, 2)
    );
    await context.close();
  }

  // Mobile Fast 3G home
  {
    const context = await browser.newContext({
      viewport: { width: 390, height: 844 },
      isMobile: true,
      hasTouch: true,
    });
    const page = await context.newPage();
    all.push(await collectMetrics(page, 'mobile-fast3g-anon-home', '/', { network: 'fast3g' }));
    await context.close();
  }

  // Image / cache header audit via API host
  const samplePoster = all.flatMap((m) => m.imageUrls).find((u) => u.includes('image.tmdb.org'));
  const cacheHeaders: Record<string, string> = {};
  if (samplePoster) {
    const resp = await fetch(samplePoster, { method: 'GET' }).catch(() => null);
    if (resp) {
      cacheHeaders['cache-control'] = resp.headers.get('cache-control') || '';
      cacheHeaders['url'] = samplePoster;
    }
  }

  const summary = {
    base: BASE,
    pages: all,
    imageAudit: {
      anyOriginalTmdbOnCards: all.some((m) => m.originalTmdbImages.length > 0),
      originals: all.flatMap((m) => m.originalTmdbImages),
      sampleCacheHeaders: cacheHeaders,
    },
    requestDedup: {
      anonHomeApis: all.find((m) => m.label === 'desktop-anon-home')?.apiUrls || [],
      authHomeApis: all.find((m) => m.label === 'desktop-auth-home')?.apiUrls || [],
    },
  };
  fs.writeFileSync(path.join(OUT, 'browser-waterfalls.json'), JSON.stringify(summary, null, 2));

  const anon = all.find((m) => m.label === 'desktop-anon-home')!;
  const auth = all.find((m) => m.label === 'desktop-auth-home')!;
  expect(anon.apiRequestCount).toBeGreaterThan(0);

  // Anonymous home should use catalog/home and not fan-out listMovies.
  const anonPaths = anon.apiUrls.map((u) => new URL(u).pathname);
  expect(anonPaths.some((p) => p.endsWith('/catalog/home'))).toBeTruthy();
  expect(anonPaths.filter((p) => p === '/api/movies' || p.endsWith('/movies')).length).toBe(0);
  expect(anonPaths.filter((p) => p.includes('/collections/featured/home')).length).toBe(0);

  // Authenticated home should use me/home and not duplicate CW/watchlist/recs endpoints.
  const authPaths = auth.apiUrls.map((u) => new URL(u).pathname);
  expect(authPaths.filter((p) => p.endsWith('/me/home')).length).toBe(1);
  expect(authPaths.filter((p) => p.endsWith('/catalog/home')).length).toBe(0);
  expect(authPaths.filter((p) => p.includes('/continue-watching')).length).toBe(0);
  expect(authPaths.filter((p) => p.includes('/watchlist')).length).toBe(0);
  expect(authPaths.filter((p) => p.includes('/recommendations')).length).toBe(0);
  expect(authPaths.filter((p) => p.includes('/collections/featured/home')).length).toBe(0);

  // Cards must not request TMDB /original/ when MediaCard sizing runs.
  const shelfOriginals = all
    .filter((m) => m.label.includes('home') || m.label.includes('movies'))
    .flatMap((m) => m.originalTmdbImages);
  fs.writeFileSync(path.join(OUT, 'image-originals.json'), JSON.stringify(shelfOriginals, null, 2));
  expect(shelfOriginals.length).toBe(0);
});
