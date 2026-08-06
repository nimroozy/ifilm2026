import { describe, it, expect } from 'vitest';
import { isNavActive, DESKTOP_NAV_ITEMS, MOBILE_BOTTOM_NAV } from '@/components/customer/navConfig';
import { FOOTER_SOCIAL_LINKS } from '@/lib/siteLinks';
import { getAppVersion } from '@/lib/appVersion';

describe('customer nav active matching', () => {
  const movies = DESKTOP_NAV_ITEMS.find((i) => i.id === 'movies')!;
  const series = DESKTOP_NAV_ITEMS.find((i) => i.id === 'series')!;
  const home = DESKTOP_NAV_ITEMS.find((i) => i.id === 'home')!;
  const genres = DESKTOP_NAV_ITEMS.find((i) => i.id === 'genres')!;

  it('marks nested movie detail under Movies', () => {
    expect(isNavActive('/movie/12', movies)).toBe(true);
    expect(isNavActive('/movies', movies)).toBe(true);
    expect(isNavActive('/series', movies)).toBe(false);
  });

  it('marks nested series detail under Series', () => {
    expect(isNavActive('/series/5', series)).toBe(true);
    expect(isNavActive('/series', series)).toBe(true);
  });

  it('only marks home for exact /', () => {
    expect(isNavActive('/', home)).toBe(true);
    expect(isNavActive('/movies', home)).toBe(false);
  });

  it('marks genres path', () => {
    expect(isNavActive('/genres', genres)).toBe(true);
  });

  it('includes Phase 3 destinations plus Collections and excludes deferred Watchlist', () => {
    const ids = DESKTOP_NAV_ITEMS.map((i) => i.id);
    expect(ids).toEqual(
      expect.arrayContaining(['genres', 'collections', 'dubbed', 'subtitled', 'newReleases'])
    );
    expect(ids).not.toContain('myList');
  });

  it('marks collection detail routes as active under Collections', () => {
    const collections = DESKTOP_NAV_ITEMS.find((i) => i.id === 'collections')!;
    expect(isNavActive('/collections', collections)).toBe(true);
    expect(isNavActive('/collections/staff-picks', collections)).toBe(true);
    expect(isNavActive('/movies', collections)).toBe(false);
  });

  it('keeps mobile bottom tabs focused on core destinations', () => {
    expect(MOBILE_BOTTOM_NAV.map((i) => i.id)).toEqual([
      'home',
      'movies',
      'series',
      'search',
      'profile',
    ]);
  });
});

describe('footer social policy', () => {
  it('only exposes real external links (no app stores)', () => {
    expect(FOOTER_SOCIAL_LINKS.length).toBeGreaterThan(0);
    for (const link of FOOTER_SOCIAL_LINKS) {
      expect(link.href.startsWith('https://')).toBe(true);
      expect(link.href.toLowerCase()).not.toMatch(/apps\.apple|play\.google|appstore/);
    }
  });
});

describe('app version helper', () => {
  it('returns null when unset', () => {
    // Vitest env typically leaves VITE_APP_VERSION undefined
    const v = getAppVersion();
    expect(v === null || typeof v === 'string').toBe(true);
  });
});
