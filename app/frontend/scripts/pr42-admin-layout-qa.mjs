/**
 * PR #42 admin responsive layout browser QA.
 * Run against a local vite preview with route mocking (no backend required).
 *
 * Usage:
 *   LABEL=after BASE_URL=http://127.0.0.1:4173 node scripts/pr42-admin-layout-qa.mjs
 */
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';

const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:4173';
const LABEL = process.env.LABEL || 'after';
const OUT_DIR = process.env.OUT_DIR || '/opt/cursor/artifacts/pr42-admin-layout';

const VIEWPORTS = [
  { name: '1366x768', width: 1366, height: 768 },
  { name: '1440x900', width: 1440, height: 900 },
  { name: '1600x900', width: 1600, height: 900 },
  { name: '1920x1080', width: 1920, height: 1080 },
  { name: '2560x1440', width: 2560, height: 1440 },
  { name: '768x1024', width: 768, height: 1024 },
  { name: '390x844', width: 390, height: 844 },
];

const PAGES = [
  { path: '/admin', name: 'dashboard', expectText: [/New Movie/i, /Import TMDB/i] },
  { path: '/admin/movies', name: 'movies', expectText: [/New Movie/i, /Import TMDB/i, /Sample Film/i] },
  { path: '/admin/series', name: 'series', expectText: [/New Series/i, /Import TMDB/i] },
  { path: '/admin/genres', name: 'genres', expectText: [/Genres/i] },
  { path: '/admin/tools/upload', name: 'upload', expectText: [/Upload/i] },
  { path: '/admin/media/processing', name: 'processing', expectText: [/processing/i] },
  { path: '/admin/media/playback-sessions', name: 'playback', expectText: [/Playback/i] },
  { path: '/admin/tools/tmdb', name: 'tmdb', expectText: [/TMDB/i] },
  { path: '/admin/system/updates', name: 'updates', expectText: [/System updates|Permission denied|Updates/i] },
];

function envelope(items, total = items.length) {
  return {
    data: items,
    meta: { total, page: 1, page_size: 20, pages: Math.max(1, Math.ceil(total / 20)) },
  };
}

async function installMocks(page) {
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;
    const method = route.request().method();

    const json = (body, status = 200) =>
      route.fulfill({
        status,
        contentType: 'application/json',
        body: JSON.stringify(body),
      });

    if (p.endsWith('/admin/auth/me') || p.endsWith('/api/admin/auth/me')) {
      return json({
        id: 1,
        username: 'admin',
        email: 'admin@ifilm.demo',
        full_name: 'Admin User',
        is_active: true,
        role_name: 'Super Admin',
        permissions: ['system_updates.read', 'system_updates.manage', 'catalog.manage'],
      });
    }
    if (p.includes('/admin/dashboard') || p.endsWith('/admin/stats') || p.includes('dashboard')) {
      return json({
        total_movies: 12,
        published_movies: 6,
        draft_movies: 6,
        total_series: 3,
        published_series: 2,
        total_seasons: 4,
        total_episodes: 12,
        total_genres: 8,
      });
    }
    if (p.includes('/admin/movies') && method === 'GET' && !/\/movies\/\d+/.test(p)) {
      return json(
        envelope([
          {
            id: 1,
            title: 'Sample Film',
            slug: 'sample-film',
            status: 'published',
            playable: true,
            has_playable_package: true,
            release_year: 2024,
            updated_at: '2024-06-01T00:00:00Z',
            poster_url: '',
            is_featured: true,
            is_trending: false,
          },
          {
            id: 2,
            title: 'Wide Title That Should Truncate Gracefully In The Table Layout',
            slug: 'wide-title',
            status: 'draft',
            playable: false,
            has_playable_package: false,
            release_year: 2023,
            updated_at: '2024-05-01T00:00:00Z',
            poster_url: '',
          },
        ])
      );
    }
    if (p.includes('/admin/series') && method === 'GET' && !/\/series\/\d+/.test(p)) {
      return json(
        envelope([
          {
            id: 10,
            title: 'Sample Series',
            slug: 'sample-series',
            status: 'published',
            season_count: 2,
            episode_count: 6,
            updated_at: '2024-06-01T00:00:00Z',
          },
        ])
      );
    }
    if (p.includes('/admin/genres')) {
      return json(envelope([{ id: 1, name: 'Action', slug: 'action', movie_count: 3, series_count: 1 }]));
    }
    if (p.includes('/admin/media/assets') || p.includes('/media/assets')) {
      return json(envelope([]));
    }
    if (p.includes('/processing') || p.includes('/jobs')) {
      return json(envelope([]));
    }
    if (p.includes('/playback')) {
      return json(envelope([]));
    }
    if (p.includes('/streaming') || p.includes('/status')) {
      return json({ enabled: false, supported_principals: [], subscriber_entitlement: 'n/a' });
    }
    if (p.includes('/system/version') || p.includes('/system/updates')) {
      return json({
        app_version: '1.3.0',
        update_channel: 'stable',
        image_digests: {},
        items: [],
      });
    }
    if (p.includes('/tmdb')) {
      return json({ configured: true, results: [], items: [] });
    }
    // Default empty success for other admin GETs
    if (method === 'GET') {
      return json({ items: [], total: 0, page: 1, page_size: 20, enabled: false });
    }
    return json({ detail: 'mocked' }, 200);
  });
}

async function measurePage(page) {
  return page.evaluate(() => {
    const doc = document.documentElement;
    const body = document.body;
    const scrollWidth = Math.max(doc.scrollWidth, body.scrollWidth);
    const clientWidth = doc.clientWidth;
    const overflowX = scrollWidth > clientWidth + 1;

    const root = document.querySelector('[data-testid="admin-layout-root"]');
    const actions = document.querySelector('[data-testid="admin-page-header-actions"]');
    const actionLinks = actions
      ? Array.from(actions.querySelectorAll('a,button')).map((el) => {
          const r = el.getBoundingClientRect();
          return {
            text: (el.textContent || '').trim().replace(/\s+/g, ' '),
            left: r.left,
            right: r.right,
            top: r.top,
            bottom: r.bottom,
            clippedRight: r.right > window.innerWidth + 1,
            clippedLeft: r.left < -1,
            visible: r.width > 0 && r.height > 0,
          };
        })
      : [];

    const stickyActions = Array.from(
      document.querySelectorAll('[data-testid^="movie-actions-"], [aria-label="Row actions"]')
    ).map((el) => {
      const r = el.getBoundingClientRect();
      return {
        clippedRight: r.right > window.innerWidth + 1,
        visible: r.width > 0 && r.height > 0,
      };
    });

    return {
      scrollWidth,
      clientWidth,
      overflowX,
      dir: root?.getAttribute('dir') || doc.getAttribute('dir'),
      lang: root?.getAttribute('lang') || doc.getAttribute('lang'),
      hasSidebar: !!document.querySelector('[data-testid="admin-desktop-sidebar"]'),
      hasMobileList: !!document.querySelector('[data-testid="movies-mobile-list"]'),
      hasDesktopTable: !!document.querySelector('[data-testid="movies-table-desktop"]'),
      actionLinks,
      stickyActions,
      anyActionClipped: actionLinks.some((a) => a.clippedRight || a.clippedLeft),
      anyRowActionClipped: stickyActions.some((a) => a.clippedRight),
    };
  });
}

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const report = { label: LABEL, baseUrl: BASE_URL, generatedAt: new Date().toISOString(), results: [] };
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });

  for (const vp of VIEWPORTS) {
    for (const pageDef of PAGES) {
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        deviceScaleFactor: 1,
      });
      const page = await context.newPage();
      await installMocks(page);
      await page.addInitScript(() => {
        localStorage.setItem('ifilm_admin_token', 'qa-mock-token');
      });

      const url = `${BASE_URL}${pageDef.path}`;
      let navError = null;
      try {
        await page.goto(url, { waitUntil: 'networkidle', timeout: 45000 });
        // Wait for admin shell
        await page.waitForSelector('[data-testid="admin-layout-root"], [data-testid="admin-page-header"], h1', {
          timeout: 15000,
        });
        await page.waitForTimeout(400);
      } catch (err) {
        navError = String(err);
      }

      const metrics = navError ? null : await measurePage(page);
      const shotName = `${LABEL}_${pageDef.name}_${vp.name}.png`;
      const shotPath = path.join(OUT_DIR, shotName);
      if (!navError) {
        await page.screenshot({ path: shotPath, fullPage: false });
      }

      const textOk =
        !navError &&
        (
          await Promise.all(
            pageDef.expectText.map(async (re) => {
              try {
                await page.getByText(re).first().waitFor({ timeout: 5000 });
                return true;
              } catch {
                return false;
              }
            })
          )
        ).every(Boolean);

      const pass =
        !navError &&
        metrics &&
        !metrics.overflowX &&
        !metrics.anyActionClipped &&
        !metrics.anyRowActionClipped &&
        metrics.dir === 'ltr' &&
        (metrics.lang === 'en' || metrics.lang === 'en-US' || metrics.lang === 'en') &&
        textOk;

      report.results.push({
        viewport: vp.name,
        page: pageDef.name,
        path: pageDef.path,
        screenshot: navError ? null : shotName,
        pass,
        navError,
        textOk,
        metrics,
      });

      await context.close();
      process.stdout.write(
        `${pass ? 'PASS' : 'FAIL'} ${LABEL} ${vp.name} ${pageDef.name}` +
          (metrics ? ` overflowX=${metrics.overflowX} clipped=${metrics.anyActionClipped}` : ` err=${navError}`) +
          '\n'
      );
    }
  }

  await browser.close();
  const summaryPath = path.join(OUT_DIR, `${LABEL}-report.json`);
  fs.writeFileSync(summaryPath, JSON.stringify(report, null, 2));
  const failed = report.results.filter((r) => !r.pass);
  console.log(`\nWrote ${summaryPath}`);
  console.log(`Total ${report.results.length}, failed ${failed.length}`);
  if (failed.length) {
    for (const f of failed.slice(0, 20)) {
      console.log(' FAIL detail', f.viewport, f.page, f.navError || f.metrics);
    }
    process.exitCode = 1;
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
