import { expect, test, type Page } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const ARTIFACT_DIR = process.env.PR46_ARTIFACT_DIR || '/opt/cursor/artifacts/pr46-qa';

const DESKTOP = [
  { name: '1280x720', width: 1280, height: 720 },
  { name: '1366x768', width: 1366, height: 768 },
  { name: '1440x900', width: 1440, height: 900 },
  { name: '1600x900', width: 1600, height: 900 },
  { name: '1920x1080', width: 1920, height: 1080 },
  { name: '2560x1440', width: 2560, height: 1440 },
];

const COMPACT = [
  { name: '1024x768', width: 1024, height: 768 },
  { name: '768x1024', width: 768, height: 1024 },
  { name: '430x932', width: 430, height: 932 },
  { name: '390x844', width: 390, height: 844 },
  { name: '360x800', width: 360, height: 800 },
];

const ROUTES = [
  '/',
  '/movies',
  '/series',
  '/kids',
  '/children',
  '/genres',
  '/dubbed',
  '/subtitled',
  '/new-releases',
  '/about',
  '/contact',
  '/help',
  '/privacy',
  '/terms',
  '/copyright',
];

function ensureDir(dir: string) {
  fs.mkdirSync(dir, { recursive: true });
}

async function setLocale(page: Page, locale: 'en' | 'fa' | 'ps') {
  await page.addInitScript((loc) => {
    localStorage.setItem('ifilm.locale', loc);
    document.cookie = `ifilm.locale=${loc}; path=/`;
  }, locale);
}

async function noPageOverflow(page: Page) {
  const overflow = await page.evaluate(() => {
    const doc = document.documentElement;
    return {
      scrollWidth: doc.scrollWidth,
      clientWidth: doc.clientWidth,
      bodyScrollWidth: document.body.scrollWidth,
    };
  });
  expect(overflow.scrollWidth, JSON.stringify(overflow)).toBeLessThanOrEqual(overflow.clientWidth + 1);
}

function isIgnorableConsole(text: string): boolean {
  return /favicon|Download the React DevTools|Failed to load resource|Content Security Policy|script-src/i.test(
    text
  );
}

async function collectConsoleErrors(page: Page) {
  const errors: string[] = [];
  page.on('pageerror', (err) => errors.push(String(err)));
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  return errors;
}

test.beforeAll(() => {
  ensureDir(ARTIFACT_DIR);
  ensureDir(path.join(ARTIFACT_DIR, 'screenshots'));
});

test.describe('Phase 3 desktop chrome', () => {
  for (const vp of DESKTOP) {
    test(`desktop layout ${vp.name}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      const errors = await collectConsoleErrors(page);
      await page.goto('/');
      await expect(page.getByRole('link', { name: 'iFilm' })).toBeVisible();
      await expect(page.getByTestId('desktop-nav')).toBeVisible();
      await expect(page.getByTestId('customer-footer')).toBeVisible();
      await expect(page.getByTestId('mobile-bottom-nav')).toBeHidden();

      const logoBox = await page.getByRole('link', { name: 'iFilm' }).boundingBox();
      const searchBox = await page.getByRole('button', { name: 'Search' }).boundingBox();
      expect(logoBox && searchBox).toBeTruthy();
      if (logoBox && searchBox) {
        expect(logoBox.x + logoBox.width).toBeLessThan(searchBox.x);
      }

      const moreVisible = await page.getByTestId('desktop-nav-more').isVisible().catch(() => false);
      if (vp.width >= 1536) {
        if (!moreVisible) {
          await expect(page.getByTestId('desktop-nav-dubbed')).toBeVisible();
        }
      } else {
        await expect(page.getByTestId('desktop-nav-more')).toBeVisible();
        await expect(page.getByTestId('desktop-nav-dubbed')).toHaveCount(0);
      }

      // No app store badges — Collections is now a legitimate nav destination.
      await expect(page.getByText(/app store|google play/i)).toHaveCount(0);

      await noPageOverflow(page);

      // Active nested route
      await page.goto('/movie/1');
      await expect(page.getByTestId('desktop-nav-movies')).toHaveAttribute('data-active', 'true');

      // Version never undefined text
      const version = page.getByTestId('footer-version');
      if (await version.count()) {
        const text = await version.textContent();
        expect(text || '').not.toMatch(/undefined/i);
      }

      expect(errors.filter((e) => !isIgnorableConsole(e))).toEqual([]);
    });
  }

  test('More menu open/close interactions at 1366', async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    await page.goto('/');
    const more = page.getByTestId('desktop-nav-more');
    await expect(more).toBeVisible();
    await more.click();
    await expect(page.getByTestId('desktop-nav-more-menu')).toBeVisible();
    await page.screenshot({
      path: path.join(ARTIFACT_DIR, 'screenshots', 'desktop-1366-more-open.png'),
      fullPage: false,
    });
    const menuBox = await page.getByTestId('desktop-nav-more-menu').boundingBox();
    expect(menuBox).toBeTruthy();
    if (menuBox) {
      expect(menuBox.x).toBeGreaterThanOrEqual(0);
      expect(menuBox.x + menuBox.width).toBeLessThanOrEqual(1366 + 1);
    }
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('desktop-nav-more-menu')).toHaveCount(0);
    await more.click();
    await expect(page.getByTestId('desktop-nav-more-menu')).toBeVisible();
    // Dismiss via outside click (Radix dismissable layer)
    await page.mouse.click(20, 700);
    await expect(page.getByTestId('desktop-nav-more-menu')).toHaveCount(0);
    await more.click();
    await page.getByTestId('desktop-nav-more-dubbed').click();
    await expect(page).toHaveURL(/\/dubbed/);
    await expect(page.getByTestId('desktop-nav-more-menu')).toHaveCount(0);
  });

  test('keyboard focus and aria-current', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/genres');
    await page.keyboard.press('Tab');
    const focused = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      if (!el) return null;
      const style = window.getComputedStyle(el);
      return {
        tag: el.tagName,
        outline: style.outlineStyle,
        outlineWidth: style.outlineWidth,
        boxShadow: style.boxShadow,
      };
    });
    expect(focused).toBeTruthy();
    await expect(page.getByTestId('desktop-nav-genres')).toHaveAttribute('aria-current', 'page');
  });
});

test.describe('Phase 3 tablet/mobile', () => {
  for (const vp of COMPACT) {
    test(`compact layout ${vp.name}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto('/');
      if (vp.width < 768) {
        await expect(page.getByTestId('mobile-nav-trigger')).toBeVisible();
        await expect(page.getByTestId('mobile-bottom-nav')).toBeVisible();
        await expect(page.getByTestId('desktop-nav')).toBeHidden();
        await page.getByTestId('mobile-nav-trigger').click();
        await expect(page.getByTestId('mobile-nav-sheet')).toBeVisible();
        await expect(page.getByTestId('mobile-nav-genres')).toBeVisible();
        // Escape closes sheet
        await page.keyboard.press('Escape');
        await expect(page.getByTestId('mobile-nav-sheet')).toHaveCount(0);
        // Focus returns to trigger
        await expect(page.getByTestId('mobile-nav-trigger')).toBeFocused();
        // Bottom tab active
        await expect(page.getByTestId('bottom-nav-home')).toHaveAttribute('data-active', 'true');
        await page.getByTestId('bottom-nav-movies').click();
        await expect(page).toHaveURL(/\/movies/);
        await expect(page.getByTestId('bottom-nav-movies')).toHaveAttribute('data-active', 'true');
      } else {
        // tablet widths may show desktop nav (md breakpoint 768)
        await expect(page.getByTestId('customer-footer')).toBeVisible();
      }
      await noPageOverflow(page);
      await page.goto('/privacy');
      await expect(page.getByTestId('privacy-page')).toBeVisible();
      await noPageOverflow(page);
    });
  }
});

test.describe('Phase 3 RTL/LTR', () => {
  for (const locale of ['en', 'fa', 'ps'] as const) {
    test(`locale ${locale}`, async ({ page }) => {
      await setLocale(page, locale);
      await page.setViewportSize({ width: 390, height: 844 });
      await page.goto('/');
      const dir = await page.evaluate(() => document.documentElement.getAttribute('dir'));
      const lang = await page.evaluate(() => document.documentElement.getAttribute('lang'));
      if (locale === 'en') {
        expect(dir).toBe('ltr');
        expect(lang).toBe('en');
      } else {
        expect(dir).toBe('rtl');
        expect(lang).toBe(locale);
      }
      await page.getByTestId('mobile-nav-trigger').click();
      const sheet = page.getByTestId('mobile-nav-sheet');
      await expect(sheet).toBeVisible();
      // No raw translation keys
      const bodyText = await page.locator('body').innerText();
      expect(bodyText).not.toMatch(/\bnav\.\w+\b/);
      expect(bodyText).not.toMatch(/\bfooter\.\w+\b/);
      expect(bodyText).not.toMatch(/\bpages\.\w+\b/);
      await page.screenshot({
        path: path.join(ARTIFACT_DIR, 'screenshots', `mobile-sheet-${locale}.png`),
        fullPage: true,
      });
      await page.keyboard.press('Escape');
      await page.goto('/about');
      await expect(page.getByTestId('about-page')).toBeVisible();
      await expect(page.getByTestId('footer-tmdb')).toContainText(/TMDB/i);
    });
  }
});

test.describe('Phase 3 routes and content', () => {
  test('direct navigation, titles, 404, browse pages', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const errors = await collectConsoleErrors(page);

    for (const route of ROUTES) {
      const res = await page.goto(route);
      expect(res?.ok() || res?.status() === 200).toBeTruthy();
      const title = await page.title();
      expect(title).toMatch(/iFilm/);
      expect(title).not.toMatch(/undefined/i);
      expect(title).not.toBe('iFilm Admin');
      if (route === '/kids') {
        await expect(page).toHaveURL(/\/children/);
      }
    }

    await page.goto('/this-route-does-not-exist-pr46');
    await expect(page.getByTestId('not-found-page')).toBeVisible();
    await page.goBack();
    await page.goForward();

    await page.goto('/genres');
    await expect(page.getByTestId('genres-browse-page')).toBeVisible();
    // Empty genre cards must not appear with count 0
    const genreCards = page.locator('[data-testid^="genre-card-"]');
    const count = await genreCards.count();
    for (let i = 0; i < count; i += 1) {
      const c = await genreCards.nth(i).getAttribute('data-count');
      expect(Number(c)).toBeGreaterThan(0);
    }

    await page.goto('/dubbed');
    await expect(page.getByTestId('catalog-shelf-dubbed')).toBeVisible();
    await page.goto('/new-releases');
    await expect(page.getByTestId('catalog-shelf-new')).toBeVisible();

    // Footer links + safe rel
    await page.goto('/');
    await expect(page.getByTestId('footer-social-website')).toHaveAttribute('rel', /noopener/);
    await expect(page.getByTestId('footer-social-facebook')).toHaveAttribute('href', 'https://www.facebook.com/mobinnetict');
    await expect(page.getByTestId('footer-link-copyright')).toBeVisible();
    await expect(page.getByText(/app store|google play/i)).toHaveCount(0);

    // Screenshots required by QA brief
    await page.screenshot({
      path: path.join(ARTIFACT_DIR, 'screenshots', 'desktop-home-en.png'),
      fullPage: true,
    });
    await page.goto('/genres');
    await page.screenshot({
      path: path.join(ARTIFACT_DIR, 'screenshots', 'desktop-genres-en.png'),
      fullPage: true,
    });
    await page.goto('/dubbed');
    await page.screenshot({
      path: path.join(ARTIFACT_DIR, 'screenshots', 'desktop-dubbed-en.png'),
      fullPage: true,
    });
    await page.goto('/new-releases');
    await page.screenshot({
      path: path.join(ARTIFACT_DIR, 'screenshots', 'desktop-new-releases-en.png'),
      fullPage: true,
    });

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/');
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.screenshot({
      path: path.join(ARTIFACT_DIR, 'screenshots', 'mobile-390-footer.png'),
      fullPage: true,
    });

    const hardErrors = errors.filter((e) => !isIgnorableConsole(e));
    expect(hardErrors).toEqual([]);
  });

  test('pashto bottom navigation screenshot', async ({ page }) => {
    await setLocale(page, 'ps');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/');
    await expect(page.getByTestId('mobile-bottom-nav')).toBeVisible();
    await page.screenshot({
      path: path.join(ARTIFACT_DIR, 'screenshots', 'mobile-pashto-bottom-nav.png'),
      fullPage: false,
    });
  });
});

test.describe('Phase 3 accessibility smoke', () => {
  test('landmarks and sheet semantics', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/');
    await expect(page.locator('header')).toHaveCount(1);
    await expect(page.locator('main')).toHaveCount(1);
    await expect(page.getByRole('contentinfo')).toHaveCount(1);
    await page.getByTestId('mobile-nav-trigger').click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    // Focus trap: tab stays inside dialog
    for (let i = 0; i < 8; i += 1) {
      await page.keyboard.press('Tab');
    }
    const inside = await page.evaluate(() => {
      const dialogEl = document.querySelector('[role="dialog"]');
      return !!(dialogEl && dialogEl.contains(document.activeElement));
    });
    expect(inside).toBe(true);
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);

    // Duplicate IDs
    const dupes = await page.evaluate(() => {
      const seen = new Map<string, number>();
      document.querySelectorAll('[id]').forEach((el) => {
        const id = el.id;
        seen.set(id, (seen.get(id) || 0) + 1);
      });
      return [...seen.entries()].filter(([, n]) => n > 1).map(([id]) => id);
    });
    expect(dupes).toEqual([]);
  });
});
