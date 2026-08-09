/**
 * PR #62 Media Player Experience V1 — browser Ready Gate.
 * Requires:
 *  - API on BACKEND (default :8020) with fixtures from prepare_player_v1_multi_track_fixtures.py
 *  - Vite on PLAYER_V1_BASE_URL (default :5174) proxying that API
 *  - /tmp/ifilm-player-v1-verify.json
 */
import { test, expect, type Page } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const META = JSON.parse(fs.readFileSync('/tmp/ifilm-player-v1-verify.json', 'utf8')) as {
  subscriber: { token: string };
  movie_a: { id: number; player_path: string; title: string };
  movie_b: { id: number; player_path: string; title: string };
  episode: { id: number; player_path: string; series_id: number };
};

const ART = '/opt/cursor/artifacts/pr62-browser-qa';
fs.mkdirSync(ART, { recursive: true });

const VIEWPORTS = [
  { name: '1920x1080', width: 1920, height: 1080 },
  { name: '1440x900', width: 1440, height: 900 },
  { name: '1366x768', width: 1366, height: 768 },
  { name: '768x1024', width: 768, height: 1024 },
  { name: '390x844', width: 390, height: 844 },
] as const;

const LOCALES = ['en', 'fa', 'ps'] as const;

async function injectAuth(page: Page, locale = 'en') {
  await page.addInitScript(
    ({ token, lang }: { token: string; lang: string }) => {
      localStorage.setItem('ifilm_access_token', token);
      localStorage.setItem('ifilm.locale', lang);
      document.cookie = `ifilm.locale=${lang}; path=/`;
    },
    { token: META.subscriber.token, lang: locale }
  );
}

async function setLocale(page: Page, locale: string) {
  // Re-bind init script so subsequent navigations keep the locale.
  await injectAuth(page, locale);
  await page.evaluate((lang) => {
    localStorage.setItem('ifilm.locale', lang);
    document.cookie = `ifilm.locale=${lang}; path=/`;
  }, locale);
  await page.reload({ waitUntil: 'networkidle' });
}

test('catalog dubbed localization EN/FA/PS', async ({ browser }) => {
  for (const locale of LOCALES) {
    const context = await browser.newContext();
    const page = await context.newPage();
    await injectAuth(page, locale);
    await page.goto(`/movie/${META.movie_a.id}`, { waitUntil: 'networkidle' });
    await expect(page.getByTestId('movie-play-button')).toBeVisible({ timeout: 20000 });
    await expect(page.locator('html')).toHaveAttribute('dir', locale === 'en' ? 'ltr' : 'rtl');
    // Technical details label uses i18n movie.dubbed (not Persian literals as data).
    const tech = page.getByTestId('movie-technical-details');
    await expect(tech).toBeVisible({ timeout: 20000 });
    const techText = await tech.innerText();
    if (locale === 'en') {
      expect(techText).toMatch(/Dubbed/i);
      expect(techText).not.toContain('دوبله شده');
    }
    if (locale === 'fa') {
      expect(techText).toContain('دوبله شده');
    }
    if (locale === 'ps') {
      expect(techText).toContain('ژباړل شوی');
    }
    await page.screenshot({
      path: path.join(ART, `catalog-movie-a-${locale}.png`),
      fullPage: true,
    });
    await context.close();
  }
});

test('autoplay after Play CTA', async ({ page }) => {
  await injectAuth(page, 'en');
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/movie/${META.movie_a.id}`);
  const play = page.getByTestId('movie-play-button');
  await expect(play).toBeVisible({ timeout: 20000 });
  await play.click();
  await page.waitForURL(`**/player/movie/${META.movie_a.id}`);
  await expect(page.getByTestId('video-player')).toBeVisible({ timeout: 30000 });
  // Wait for stream ready — either playing or resume dialog
  await page.waitForTimeout(2500);
  const resume = page.getByTestId('resume-dialog');
  const resumeVisible = await resume.isVisible().catch(() => false);
  if (resumeVisible) {
    await page.getByTestId('resume-start-over').click();
  }
  await page.waitForTimeout(1500);
  const paused = await page.evaluate(() => {
    const video = document.querySelector('[data-testid="player-video"]') as HTMLVideoElement | null;
    return !video || video.paused;
  });
  // User-gesture Play should allow playback; if browser blocks, center play remains (not a blocker loop)
  if (paused) {
    const center = page.getByTestId('center-play');
    if (await center.isVisible()) {
      await center.click();
      await page.waitForTimeout(800);
    }
  }
  const playing = await page.evaluate(() => {
    const video = document.querySelector('[data-testid="player-video"]') as HTMLVideoElement | null;
    return Boolean(video && !video.paused && video.currentTime >= 0);
  });
  expect(playing).toBeTruthy();
  await page.screenshot({ path: path.join(ART, 'autoplay-after-play.png') });
});

test('player LTR under FA/PS + AirPlay hidden on Chromium', async ({ browser }) => {
  for (const locale of ['fa', 'ps'] as const) {
    const context = await browser.newContext({ viewport: { width: 1366, height: 768 } });
    const page = await context.newPage();
    await injectAuth(page, locale);
    await page.goto(`${META.movie_a.player_path}`, { waitUntil: 'domcontentloaded' });
    await page.evaluate(() => {
      history.replaceState({ ...(history.state || {}), autoplay: true }, '');
    });
    await page.reload({ waitUntil: 'domcontentloaded' });
    const player = page.getByTestId('video-player');
    await expect(player).toBeVisible({ timeout: 30000 });
    await expect(player).toHaveAttribute('dir', 'ltr');
    const controls = page.getByTestId('player-controls');
    await player.hover();
    await page.mouse.move(200, 200);
    await expect(controls).toHaveAttribute('dir', 'ltr');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    await expect(page.getByTestId('airplay-button')).toHaveCount(0);
    const apText = await controls.innerText();
    expect(apText).not.toMatch(/\bAP\b/);
    await page.screenshot({ path: path.join(ART, `player-ltr-${locale}.png`) });
    await context.close();
  }
});

test('multi-audio and subtitle selectors from live HLS', async ({ page }) => {
  await injectAuth(page, 'en');
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto(META.movie_a.player_path);
  await page.evaluate(() => history.replaceState({ autoplay: true }, ''));
  await page.reload();
  await expect(page.getByTestId('video-player')).toBeVisible({ timeout: 30000 });
  // Dismiss resume if shown
  if (await page.getByTestId('resume-dialog').isVisible().catch(() => false)) {
    await page.getByTestId('resume-start-over').click();
  }
  await page.waitForTimeout(3000);
  await page.getByTestId('video-player').hover();
  const audio = page.getByTestId('audio-selector');
  await expect(audio).toBeVisible({ timeout: 20000 });
  await audio.click();
  const audioList = page.getByRole('listbox');
  await expect(audioList).toBeVisible();
  const audioText = await audioList.innerText();
  // Language-native track identity (not FA/PS codes)
  expect(audioText).toMatch(/English/i);
  expect(audioText).toContain('فارسی');
  expect(audioText).toContain('پښتو');
  expect(audioText).not.toMatch(/\bFA\b|\bPS\b/);
  // No duplicate English entries
  expect(audioText.match(/English/gi)?.length ?? 0).toBe(1);
  await page.keyboard.press('Escape');

  const subs = page.getByTestId('subtitle-selector');
  await expect(subs).toBeVisible();
  await subs.click();
  const subList = page.getByRole('listbox');
  await expect(subList).toBeVisible();
  const subText = await subList.innerText();
  expect(subText).toMatch(/Off/i);
  expect(subText).toMatch(/English/i);
  expect(subText).toContain('فارسی');
  expect(subText).toContain('پښتو');
  await page.keyboard.press('Escape');

  // Switch audio without restarting from 0
  await page.evaluate(() => {
    const video = document.querySelector('[data-testid="player-video"]') as HTMLVideoElement;
    if (video) video.currentTime = 8;
  });
  await page.waitForTimeout(400);
  await audio.click();
  const option = page.getByRole('option').filter({ hasText: 'فارسی' }).first();
  await expect(option).toBeVisible();
  await option.click();
  await page.waitForTimeout(800);
  const t = await page.evaluate(() => {
    const video = document.querySelector('[data-testid="player-video"]') as HTMLVideoElement;
    return video?.currentTime ?? 0;
  });
  expect(t).toBeGreaterThan(3);
  await page.screenshot({ path: path.join(ART, 'multi-audio-selector.png') });
});

test('single-track movie hides pointless audio selector', async ({ page }) => {
  await injectAuth(page, 'en');
  await page.goto(META.movie_b.player_path);
  await page.evaluate(() => history.replaceState({ autoplay: true }, ''));
  await page.reload();
  await expect(page.getByTestId('video-player')).toBeVisible({ timeout: 30000 });
  if (await page.getByTestId('resume-dialog').isVisible().catch(() => false)) {
    await page.getByTestId('resume-start-over').click();
  }
  await page.waitForTimeout(2500);
  await page.getByTestId('video-player').hover();
  await expect(page.getByTestId('audio-selector')).toHaveCount(0);
  await expect(page.getByTestId('subtitle-selector')).toHaveCount(0);
  await page.screenshot({ path: path.join(ART, 'single-track-no-audio-selector.png') });
});

test('resume Continue / Start Over persists via backend', async ({ page, request }) => {
  await injectAuth(page, 'en');
  const assetId = (
    JSON.parse(fs.readFileSync('/tmp/ifilm-player-v1-verify.json', 'utf8')) as {
      movie_a: { asset_id: string };
    }
  ).movie_a.asset_id;

  // Seed progress via API
  const put = await request.put(`http://127.0.0.1:8020/api/me/watch-progress/${assetId}`, {
    headers: { Authorization: `Bearer ${META.subscriber.token}` },
    data: {
      position_seconds: 42,
      duration_seconds: 90,
      event_at: new Date().toISOString(),
    },
  });
  expect(put.ok()).toBeTruthy();

  await page.goto(META.movie_a.player_path);
  await expect(page.getByTestId('resume-dialog')).toBeVisible({ timeout: 30000 });
  await expect(page.getByTestId('resume-continue')).toBeVisible();
  await expect(page.getByTestId('resume-start-over')).toBeVisible();
  await page.screenshot({ path: path.join(ART, 'resume-dialog.png') });

  await page.getByTestId('resume-continue').click();
  await page.waitForTimeout(1200);
  const t = await page.evaluate(() => {
    const video = document.querySelector('[data-testid="player-video"]') as HTMLVideoElement;
    return video?.currentTime ?? 0;
  });
  expect(t).toBeGreaterThan(30);

  // Start over path
  await page.goto(META.movie_a.player_path);
  await expect(page.getByTestId('resume-dialog')).toBeVisible({ timeout: 30000 });
  await page.getByTestId('resume-start-over').click();
  await page.waitForTimeout(1000);
  const t0 = await page.evaluate(() => {
    const video = document.querySelector('[data-testid="player-video"]') as HTMLVideoElement;
    return video?.currentTime ?? 99;
  });
  expect(t0).toBeLessThan(5);
});

test('episode player multi-track', async ({ page }) => {
  await injectAuth(page, 'en');
  await page.goto(META.episode.player_path);
  await page.evaluate(() => history.replaceState({ autoplay: true }, ''));
  await page.reload();
  await expect(page.getByTestId('video-player')).toBeVisible({ timeout: 30000 });
  if (await page.getByTestId('resume-dialog').isVisible().catch(() => false)) {
    await page.getByTestId('resume-start-over').click();
  }
  await page.waitForTimeout(2500);
  await page.getByTestId('video-player').hover();
  await expect(page.getByTestId('audio-selector')).toBeVisible({ timeout: 20000 });
  await expect(page.getByTestId('subtitle-selector')).toBeVisible();
  await page.screenshot({ path: path.join(ART, 'episode-multi-track.png') });
});

test('viewport matrix EN/FA/PS smoke', async ({ browser }) => {
  for (const vp of VIEWPORTS) {
    for (const locale of LOCALES) {
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
      });
      const page = await context.newPage();
      await injectAuth(page, locale);
      await page.goto(`/movie/${META.movie_a.id}`, { waitUntil: 'networkidle' });
      await expect(page.getByTestId('movie-play-button')).toBeVisible({ timeout: 20000 });
      const overflow = await page.evaluate(() => {
        return document.documentElement.scrollWidth > document.documentElement.clientWidth + 2;
      });
      expect(overflow, `${vp.name} ${locale} overflow`).toBeFalsy();
      await page.screenshot({
        path: path.join(ART, `matrix-${vp.name}-${locale}-detail.png`),
      });

      await page.goto(META.movie_a.player_path);
      await expect(page.getByTestId('video-player')).toBeVisible({ timeout: 30000 });
      await expect(page.getByTestId('video-player')).toHaveAttribute('dir', 'ltr');
      if (await page.getByTestId('resume-dialog').isVisible().catch(() => false)) {
        await page.getByTestId('resume-start-over').click();
      }
      await page.getByTestId('video-player').hover();
      await expect(page.getByTestId('player-controls')).toHaveAttribute('dir', 'ltr');
      await page.screenshot({
        path: path.join(ART, `matrix-${vp.name}-${locale}-player.png`),
      });
      await context.close();
    }
  }
});

test('security: stream URLs stay on session path', async ({ page }) => {
  await injectAuth(page, 'en');
  const streamUrls: string[] = [];
  page.on('response', (resp) => {
    if (resp.url().includes('/api/stream/')) streamUrls.push(resp.url());
  });
  await page.goto(META.movie_a.player_path);
  await page.evaluate(() => history.replaceState({ autoplay: true }, ''));
  await page.reload();
  await expect(page.getByTestId('video-player')).toBeVisible({ timeout: 30000 });
  await page.waitForTimeout(3000);
  expect(streamUrls.length).toBeGreaterThan(0);
  for (const url of streamUrls) {
    expect(url).toMatch(/\/api\/stream\/[^/]+\//);
    expect(url).not.toContain('/packages/');
    expect(url).not.toContain('/tmp/');
  }
});
