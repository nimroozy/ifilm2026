/**
 * Phase 8 real-browser verification (Chromium / Playwright).
 * Requires API+SPA on http://127.0.0.1:8000 and /tmp/ifilm-phase8-verify.json.
 */
import { test, expect, type ConsoleMessage } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';

const BASE = process.env.PHASE8_BASE_URL || 'http://127.0.0.1:8000';
const META = JSON.parse(fs.readFileSync('/tmp/ifilm-phase8-verify.json', 'utf8')) as {
  movie_id: number;
  media_asset_id: string;
  package_id: string;
  rendition_labels: string[];
  player_path: string;
  watch_path: string;
  subscriber_user: string;
  subscriber_password: string;
  admin_password: string;
};

const TOKEN_RE = /\/api\/stream\/[A-Za-z0-9_-]{20,}/;

function expireSession(sessionId: string) {
  execFileSync(
    'python3',
    [
      '-c',
      `
import os
from pathlib import Path
from datetime import timedelta
for line in Path('/workspace/ifilm2026/app/backend/.env').read_text().splitlines():
    line=line.strip()
    if not line or line.startswith('#') or '=' not in line: continue
    k,v=line.split('=',1); os.environ[k.strip()]=v.strip()
from app.core.config import get_settings
get_settings.cache_clear()
from sqlalchemy import create_engine, text
from app.models.media_assets import utcnow
engine=create_engine(os.environ['DATABASE_URL'])
with engine.begin() as conn:
    conn.execute(
        text("UPDATE media_playback_sessions SET expires_at=:t, status='expired' WHERE id=:id"),
        {"t": utcnow()-timedelta(seconds=10), "id": ${JSON.stringify(sessionId)}},
    )
print('ok')
`,
    ],
    { cwd: '/workspace/ifilm2026/app/backend', stdio: ['ignore', 'pipe', 'pipe'] }
  );
}

async function login(page: import('@playwright/test').Page) {
  await page.goto('/login');
  await page.fill('#username', META.subscriber_user);
  await page.fill('#password', META.subscriber_password);
  await page.locator('form button[type="submit"]').click();
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 20000 });
}

test.describe.configure({ mode: 'serial' });

test('production CSP header on HTML', async ({ request }) => {
  const resp = await request.get('/');
  expect(resp.ok()).toBeTruthy();
  const csp = resp.headers()['content-security-policy'] || '';
  expect(csp).toContain("default-src 'self'");
  expect(csp).toContain("object-src 'none'");
  expect(csp).toContain("base-uri 'self'");
  expect(csp).toContain("frame-ancestors 'none'");
  expect(csp).toContain("form-action 'self'");
  expect(csp).toContain("media-src 'self' blob:");
  expect(csp).toContain("connect-src 'self' blob:");
  expect(csp).toContain("worker-src 'self' blob:");
  expect(csp).not.toContain('unsafe-eval');
});

test('Chrome playback + quality + controls + token safety + cleanup + expiry refresh', async ({
  page,
  request,
}) => {
  const consoleLines: string[] = [];
  const cspViolations: string[] = [];
  page.on('console', (msg: ConsoleMessage) => {
    const text = msg.text();
    consoleLines.push(text);
    if (/content security policy|refused to|csp/i.test(text)) cspViolations.push(text);
  });

  type SessionBody = {
    id: string;
    playback_token: string;
    master_playlist_url: string;
    media_asset_id: string;
  };
  const sessions: SessionBody[] = [];
  const streamUrls: string[] = [];

  page.on('response', async (resp) => {
    const url = resp.url();
    if (url.includes('/api/stream/')) streamUrls.push(url);
    if (
      url.includes('/api/playback/sessions') &&
      resp.request().method() === 'POST' &&
      !url.includes('revoke') &&
      resp.status() === 201
    ) {
      sessions.push((await resp.json()) as SessionBody);
    }
  });

  await login(page);

  // Movie details → Watch
  await page.goto(META.watch_path);
  const playBtn = page.getByRole('button', { name: /پخش|play|watch/i }).first();
  await expect(playBtn).toBeVisible({ timeout: 20000 });
  await playBtn.click();
  await page.waitForURL(`**${META.player_path}`);

  await expect(page.getByTestId('video-player')).toBeVisible({ timeout: 20000 });
  await expect.poll(() => sessions.length, { timeout: 20000 }).toBeGreaterThan(0);
  expect(sessions[0].media_asset_id).toBe(META.media_asset_id);

  await page.waitForFunction(() => {
    const v = document.querySelector('[data-testid="player-video"]') as HTMLVideoElement | null;
    return Boolean(v && v.readyState >= 2 && v.duration > 0);
  }, undefined, { timeout: 45000 });

  const controls = page.getByTestId('player-controls');
  const play = () => controls.getByRole('button', { name: 'Play', exact: true });
  const pause = () => controls.getByRole('button', { name: 'Pause', exact: true });

  await play().click();
  await page.waitForFunction(() => {
    const v = document.querySelector('[data-testid="player-video"]') as HTMLVideoElement | null;
    return Boolean(v && !v.paused && v.currentTime >= 0);
  }, undefined, { timeout: 20000 });

  // Quality: Auto + 240p + 360p
  const quality = page.getByTestId('quality-selector');
  await expect(quality).toBeVisible();
  await quality.click();
  const optionTexts = (await page.locator('[role="option"]').allTextContents()).map((t) =>
    t.trim()
  );
  expect(optionTexts).toEqual(['Auto', '240p', '360p']);
  await page.getByRole('option', { name: '240p' }).click();
  await expect(quality).toContainText('240p');
  await quality.click();
  await page.getByRole('option', { name: '360p' }).click();
  await expect(quality).toContainText('360p');
  await quality.click();
  await page.getByRole('option', { name: 'Auto' }).click();
  await expect(quality).toContainText('Auto');

  // Seek / pause / mute / speed
  await page.evaluate(() => {
    const v = document.querySelector('[data-testid="player-video"]') as HTMLVideoElement;
    v.currentTime = 2.5;
  });
  await page.waitForTimeout(400);
  const seeked = await page.evaluate(
    () => (document.querySelector('[data-testid="player-video"]') as HTMLVideoElement).currentTime
  );
  expect(seeked).toBeGreaterThan(2);

  await pause().click();
  await expect
    .poll(async () =>
      page.evaluate(
        () => (document.querySelector('[data-testid="player-video"]') as HTMLVideoElement).paused
      )
    )
    .toBe(true);
  await play().click();

  await controls.getByRole('button', { name: 'Mute', exact: true }).click();
  await expect(controls.getByRole('button', { name: 'Unmute', exact: true })).toBeVisible();
  await controls.getByRole('button', { name: 'Unmute', exact: true }).click();

  await page.getByLabel('Playback speed').selectOption('1.5');
  await expect
    .poll(async () =>
      page.evaluate(
        () =>
          (document.querySelector('[data-testid="player-video"]') as HTMLVideoElement).playbackRate
      )
    )
    .toBe(1.5);
  await page.getByLabel('Playback speed').selectOption('1');

  await controls.getByRole('button', { name: 'Enter fullscreen', exact: true }).click();
  await page.keyboard.press('Escape');
  await controls.getByRole('button', { name: 'Picture in picture', exact: true }).click();

  // Keyboard
  await page.keyboard.press('Space');
  await page.keyboard.press('Space');
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('m');

  // Mobile viewport
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByTestId('video-player').click();
  await expect(page.getByTestId('player-controls')).toBeVisible();

  const dir = await page.evaluate(() => document.documentElement.getAttribute('dir'));
  expect(dir).toBe('rtl');

  const firstToken = sessions[0].playback_token;
  const ui = await page.locator('body').innerText();
  expect(ui).not.toContain(firstToken);
  expect(ui).not.toMatch(/\/api\/stream\/[A-Za-z0-9_-]{16,}/);

  const storage = await page.evaluate(() => ({
    local: { ...localStorage },
    session: { ...sessionStorage },
  }));
  expect(JSON.stringify(storage)).not.toContain(firstToken);
  expect(JSON.stringify(storage)).not.toMatch(TOKEN_RE);
  expect(consoleLines.join('\n')).not.toContain(firstToken);

  // Anonymous package path rejected
  const anon = await request.get(
    `/media/packages/${META.media_asset_id}/${META.package_id}/master.m3u8`
  );
  expect(anon.status()).toBe(404);

  expect(streamUrls.some((u) => u.includes('master.m3u8'))).toBeTruthy();
  expect(streamUrls.some((u) => /\/\d+p\/index\.m3u8/.test(u) || u.includes('/240p/') || u.includes('/360p/'))).toBeTruthy();
  expect(streamUrls.some((u) => u.includes('segment_'))).toBeTruthy();

  // --- Expiry refresh (real 410) ---
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.getByTestId('video-player').click();
  if (await play().isVisible().catch(() => false)) await play().click();
  await page.getByLabel('Seek').fill('1.2');
  await page.waitForTimeout(500);
  const posBefore = await page.evaluate(
    () => (document.querySelector('[data-testid="player-video"]') as HTMLVideoElement).currentTime
  );
  const sessionsBefore = sessions.length;
  const expiredSession = sessions[sessions.length - 1];
  expireSession(expiredSession.id);

  // Force network by switching quality (reloads fragments against expired token)
  await quality.click();
  await page.getByRole('option', { name: '240p' }).click();
  await page.waitForTimeout(500);
  await quality.click();
  await page.getByRole('option', { name: '360p' }).click();

  await expect
    .poll(() => sessions.length, { timeout: 25000 })
    .toBeGreaterThan(sessionsBefore);
  expect(sessions.length - sessionsBefore).toBe(1);
  expect(sessions[sessions.length - 1].playback_token).not.toBe(firstToken);

  await page.waitForFunction(() => {
    const v = document.querySelector('[data-testid="player-video"]') as HTMLVideoElement | null;
    return Boolean(v && v.readyState >= 2);
  }, undefined, { timeout: 30000 });

  const posAfter = await page.evaluate(
    () => (document.querySelector('[data-testid="player-video"]') as HTMLVideoElement).currentTime
  );
  // Restored near prior position (allow tolerance for seek/clamp)
  expect(Math.abs(posAfter - posBefore)).toBeLessThan(3);

  // No second automatic refresh loop: expire again and expect error (bound=1 already used)
  const secondId = sessions[sessions.length - 1].id;
  const secondToken = sessions[sessions.length - 1].playback_token;
  const countAfterFirstRefresh = sessions.length;
  expireSession(secondId);
  // Force network past the buffer so hls.js surfaces the 410
  await page.evaluate(() => {
    const v = document.querySelector('[data-testid="player-video"]') as HTMLVideoElement;
    v.currentTime = Math.max(0, (v.duration || 8) - 0.25);
  });
  await quality.click();
  await page.getByRole('option', { name: '240p' }).click();
  await page.waitForTimeout(500);
  await quality.click();
  await page.getByRole('option', { name: '360p' }).click();
  await page.waitForTimeout(2000);
  expect(sessions.length).toBe(countAfterFirstRefresh);
  await expect(page.getByTestId('player-error')).toBeVisible({ timeout: 20000 });
  const err = await page.getByTestId('player-error').innerText();
  expect(err).not.toContain(secondToken);
  expect(err).not.toMatch(TOKEN_RE);

  // --- Explicit revocation: no refresh ---
  await page.goto(META.player_path);
  await expect(page.getByTestId('player-video')).toBeVisible({ timeout: 20000 });
  await page.waitForFunction(() => {
    const v = document.querySelector('[data-testid="player-video"]') as HTMLVideoElement | null;
    return Boolean(v && v.readyState >= 2);
  }, undefined, { timeout: 45000 });
  const beforeRevoke = sessions.length;
  const revokeTarget = sessions[sessions.length - 1];
  const adminLogin = await request.post('/api/admin/auth/login', {
    data: { username: 'admin', password: META.admin_password },
  });
  expect(adminLogin.ok()).toBeTruthy();
  const adminToken = (await adminLogin.json()).access_token as string;
  const rev = await request.post(`/api/admin/playback/sessions/${revokeTarget.id}/revoke`, {
    headers: { Authorization: `Bearer ${adminToken}` },
  });
  expect(rev.ok()).toBeTruthy();
  await page.getByTestId('quality-selector').click();
  await page.getByRole('option', { name: '240p' }).click();
  await page.waitForTimeout(2500);
  await expect(page.getByTestId('player-error')).toBeVisible({ timeout: 20000 });
  expect(sessions.length).toBe(beforeRevoke);

  // Route-change cleanup → fresh session
  const beforeNav = sessions.length;
  await page.goto(META.watch_path);
  await page.waitForTimeout(700);
  await page.goto(META.player_path);
  await expect(page.getByTestId('video-player')).toBeVisible({ timeout: 20000 });
  await expect.poll(() => sessions.length).toBeGreaterThan(beforeNav);

  expect(cspViolations).toEqual([]);

  fs.writeFileSync(
    '/tmp/ifilm-phase8-browser-report.json',
    JSON.stringify(
      {
        ok: true,
        sessions: sessions.length,
        streamHits: streamUrls.length,
        renditions: META.rendition_labels,
        cspViolations,
        dir,
        consoleHadToken: consoleLines.join('\n').includes(firstToken),
      },
      null,
      2
    )
  );
});
